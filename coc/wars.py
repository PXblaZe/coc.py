"""
MIT License

Copyright (c) 2019-2020 mathsman5133

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import typing

from .iterators import LeagueWarIterator
from .miscmodels import try_enum, Timestamp
from .utils import get
from .war_clans import WarClan, ClanWarLeagueClan
from .war_attack import WarAttack

if typing.TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from .war_members import ClanWarMember  # noqa


class ClanWar:
    """Represents a Current Clash of Clans War

    Attributes
    -----------
    state:
        :class:`str`: The clan's current war state.
    preparation_start_time:
        :class:`Timestamp`: The :class:`Timestamp` that preparation day started at.
    start_time:
        :class:`Timestamp`: The :class:`Timestamp` that battle day starts at.
    end_time:
        :class:`Timestamp`: The :class:`Timestamp` that battle day ends at.
    team_size:
        :class:`int`: The number of players on each side of the war.
    war_tag:
        :class:`str`: The war's unique tag. This is ``None`` unless this is a Clan League War (CWL).
    league_group:
        :class:`ClanWarLeagueGroup`: The war's league group. This is ``None`` unless this is a Clan League War.
    """

    __slots__ = (
        "state",
        "preparation_start_time",
        "start_time",
        "end_time",
        "team_size",
        "war_tag",
        "_client",
        "clan_tag",
        "clan",
        "opponent",
        "league_group",
        "_response_retry",
    )

    def __init__(self, *, data, client, **kwargs):
        self._response_retry = data.get("_response_retry")
        self._client = client
        self.clan_tag = kwargs.pop("clan_tag", None)
        self._from_data(data)
        self.clan_tag = self.clan_tag or self.clan and self.clan.tag
        self.league_group = kwargs.pop("league_group", None)

    def _from_data(self, data: dict) -> None:
        data_get = data.get

        self.state = data_get("state")
        self.team_size = data_get("teamSize", 0)
        self.preparation_start_time = try_enum(Timestamp, data=data_get("preparationStartTime"))
        self.start_time = try_enum(Timestamp, data=data_get("startTime"))
        self.end_time = try_enum(Timestamp, data=data_get("endTime"))
        self.war_tag = data_get("tag")

        clan_data = data_get("clan")
        # annoying bug where if you request a war with a clan tag that clan could be the opponent or clan,
        # depending on the way the game stores it internally. This isn't very helpful as we always want it
        # from the perspective of the tag we provided, so switch them around if it isn't correct.
        if clan_data and clan_data.get("tag", self.clan_tag) == self.clan_tag:
            self.clan = try_enum(WarClan, data=clan_data, client=self._client, war=self)
            self.opponent = try_enum(WarClan, data=data_get("opponent"), client=self._client, war=self)
        else:
            self.clan = try_enum(WarClan, data=data_get("opponent"), client=self._client, war=self)
            self.opponent = try_enum(WarClan, data=clan_data, client=self._client, war=self)

    @property
    def attacks(self) -> typing.List[WarAttack]:
        """List[:class:`WarAttack`]: Returns all attacks this war, sorted by attack order."""
        return sorted([*self.clan.attacks, *self.opponent.attacks], key=lambda x: x.order, reverse=True)

    @property
    def members(self) -> typing.List["ClanWarMember"]:
        """List[:class:`ClanWarMember`]: A list of members that are in the war."""
        return sorted([*self.clan.members, *self.opponent.members], key=lambda x: (not x.is_opponent, x.map_position))

    @property
    def type(self) -> typing.Optional[str]:
        """:class:`str`: Returns either ``friendly``, ``random`` or ``cwl``.

        This will returns ``None`` if the clan is not in war, or ``cwl`` if the clan is in a league war.

        Possibilities for the length of preparation time for a friendly war include:
        15 minutes, 30 minutes, 1 hour, 2 hours, 4 hours, 6 hours, 8 hours, 12 hours,
        16 hours, 20 hours or 24 hours.
        """
        if self.war_tag:
            return "cwl"

        if not self.start_time:
            return None

        prep_list = [
            15 * 60,
            30 * 60,
            60 * 60,
            2 * 60 * 60,
            4 * 60 * 60,
            6 * 60 * 60,
            8 * 60 * 60,
            12 * 60 * 60,
            16 * 60 * 60,
            20 * 60 * 60,
            24 * 60 * 60,
        ]
        if (self.start_time.time - self.preparation_start_time.time).seconds in prep_list:
            return "friendly"

        return "random"

    @property
    def status(self) -> str:
        """:class:`str`: Returns the war status, based off the home clan.

        Strings returned are determined by result and state, as listed below:

        +------------+-------------+
        | ``inWar``  | ``warEnded``|
        +------------+-------------+
        | ``winning``| ``won``     |
        +------------+-------------+
        | ``tied``   | ``tie``     |
        +------------+-------------+
        | ``losing`` | ``lost``    |
        +------------+-------------+
        """
        # pylint: disable=too-many-return-statements
        if self.state == "inWar":
            if self.clan.stars > self.opponent.stars:
                return "winning"

            if self.clan.stars == self.opponent.stars:
                if self.clan.destruction > self.opponent.destruction:
                    return "winning"
                if self.clan.destruction == self.opponent.destruction:
                    return "tied"

            return "losing"

        if self.state == "warEnded":
            if self.clan.stars > self.opponent.stars:
                return "won"

            if self.clan.stars == self.opponent.stars:
                if self.clan.destruction > self.opponent.destruction:
                    return "won"
                if self.clan.destruction == self.opponent.destruction:
                    return "tie"

            return "lost"

        return ""

    @property
    def is_cwl(self) -> bool:
        """:class:`bool`: Returns a boolean indicating if the war is a Clan War League (CWL) war."""
        return self.type == "cwl"

    def get_member(self, tag: str) -> typing.Optional["ClanWarMember"]:
        """Return a :class:`ClanWarMember` with the tag provided. Returns ``None`` if not found.

        Example
        --------
        .. code-block:: python3

            war = await client.get_current_war('clan_tag')
            member = war.get_member('player_tag')

        Returns
        --------
        Optional[:class:`ClanWarMember`]: The member who matches the tag provided.
        """

        home_member = self.clan.get_member(tag)
        if home_member:
            return home_member

        away_member = self.opponent.get_member(tag)
        return away_member

    def get_member_by(self, **attrs):
        """Returns the first :class:`WarMember` that meets the attributes passed

        This will return the first member matching the attributes passed.

        An example of this looks like:

        .. code-block:: python3

            member = ClanWar.get_member(tag='tag')

        This search implements the :func:`coc.utils.get` function
        """
        return get(self.members, **attrs)

    def get_attack(self, attacker_tag: str, defender_tag: str) -> typing.Optional[WarAttack]:
        """Return the :class:`WarAttack` with the attacker tag and defender tag provided.

        If the attack was not found, this will return ``None``.

        Returns
        --------
        The attack with the correct attacker and defender tags: :class:`WarAttack`: """
        attacker = self.get_member(attacker_tag)
        if not attacker:
            return None

        attacks = attacker.attacks
        if len(attacks) == 0:
            return None
        return get(attacks, defender_tag=defender_tag)

    def get_defenses(self, defender_tag: str) -> typing.List[WarAttack]:
        """Return a :class:`list` of :class:`WarAttack` for the defender tag provided.

        If the player has no defenses, this will return an empty list.

        Returns
        --------
        The player's defenses: :class:`list`[:class:`WarAttack`]"""
        defender = self.get_member(defender_tag)
        # we could do a global lookup on all attacks in the war but this is faster as we have to lookup half the attacks
        if defender.is_opponent:
            # we need to get home clan's attacks on this base
            return list(filter(lambda x: x.defender_tag == defender_tag, self.clan.attacks))

        return list(filter(lambda x: x.defender_tag == defender_tag, self.opponent.attacks))


class ClanWarLogEntry:
    """Represents a Clash of Clans War Log Entry

    .. note::

        Please see the :class:`WarClan` documention for a full list of missing attributes,
        as the clan and opponent attributes are only partially filled by the API.

        If the :attr:`ClanWarLogEntry.type` is ``cwl``, the :attr:`WarClan.attack_count`, :attr:`WarClan.stars`
        and :attr:`WarClan.destruction` are all a total which over the period of that CWL season.

        In addition, if it is a CWL entry, ``opponent`` and ``result`` will be ``None``.


    Attributes
    -----------
    result:
        :class:`str`: The result of the war - ``win`` or ``loss``
    end_time:
        :class:`Timestamp`: The :class:`Timestamp` that the war ended at.
    team_size:
        :class:`int`: The number of players on each side of the war.
    clan:
        :class:`WarClan`: The home clan.
    opponent:
        :class:`WarClan`: The opposition clan.
    """

    __slots__ = ("result", "end_time", "team_size", "clan", "opponent", "_client")

    def __init__(self, *, data, client, **_):
        self._client = client

        self._from_data(data)

    def _from_data(self, data: dict) -> None:
        data_get = data.get

        self.result = data_get("result")
        self.end_time = try_enum(Timestamp, data=data_get("endTime"))
        self.team_size = data_get("teamSize")

        self.clan = self._fake_load_clan(data_get("clan"))
        self.opponent = self._fake_load_clan(data_get("opponent"))

    def _fake_load_clan(self, data):
        if not (data and data.get("tag")):  # CWL seasons have an opposition with only badges and no tag/name.
            return None

        data["teamSize"] = self.team_size
        return try_enum(WarClan, data=data, client=self._client, war=None)

    @property
    def is_league_entry(self) -> bool:
        """:class:`bool`: Boolean indicating if the entry is a Clan War League (CWL) entry."""
        return self.result is None or self.opponent is None


class ClanWarLeagueGroup:
    """Represents a Clan War League (CWL) Group

    Attributes
    -----------
    state:
        :class:`str`: The current state of the league group (`inWar`, `preparation` etc.)
    season:
        :class:`str`: The current season of the league group
    number_of_rounds:
        :class:`int`: The number of rounds this league group contains.
    rounds:
        List[List[:class:`str`]]: A list of lists containing all war tags for each round.

        .. note::

            This only returns the current or past rounds. Any future rounds filled with #0 war tags will not appear.

            To find the number of rounds in this season, use :attr:`LeagueGroup.number_of_rounds`.

    """

    __slots__ = ("state", "season", "rounds", "number_of_rounds", "_client", "__iter_clans", "_clans")

    def __repr__(self):
        attrs = [
            ("state", self.state),
            ("season", self.season),
        ]
        return "<%s %s>" % (self.__class__.__name__, " ".join("%s=%r" % t for t in attrs),)

    def __init__(self, *, data, client, **_):
        self._client = client
        self._clans = []
        self._from_data(data)

    def _from_data(self, data: dict) -> None:
        data_get = data.get

        self.state = data_get("state")
        self.season = data_get("season")

        rounds = data_get("rounds")
        self.number_of_rounds = len(rounds)
        # the API returns a list and the rounds that haven't started contain war tags of #0 (not sure why)...
        # we want to get only the valid rounds
        self.rounds = [n["warTags"] for n in rounds if n["warTags"][0] != "#0"]

        self.__iter_clans = (ClanWarLeagueClan(data=data, client=self._client) for data in data_get("clans", []))

    @property
    def clans(self) -> typing.List[ClanWarLeagueClan]:
        """List[class:`LeagueClan`]: Returns all participating clans."""
        clans = self._clans
        if clans:
            return clans

        self._clans = clans = list(self.__iter_clans)
        return clans

    def get_wars(
        self, round_index: int = -2, cache: bool = True, cls: typing.Type[ClanWar] = ClanWar
    ) -> LeagueWarIterator:
        """Returns war information for every war in a league round.

        This will return an AsyncIterator of :class:`ClanWar`.

        Example
        --------

        .. code-block:: python3

            group = await client.get_league_group('clan_tag')

            async for war in group.get_wars():
                print(war.clan_tag)

        Parameters
        ------------
        round_index: Optional[:class:`int`] - Indicates the round number to get wars from.
                     These rounds can be found with :attr:`LeagueGroup.rounds` and defaults
                     to the current round in-war (index of -2). For leagues on day 1, this will be
                     an index of -1.
        cache: Optional[:class:`bool`] Indicates whether to search
               the cache before making an HTTP request
        cls: Type[:class:`ClanWar`]: The constructor used to create the league war.
                                     This should inherit from :class:`ClanWar`.

        Returns
        ---------
        AsyncIterator of :class:`ClanWar`: All wars in the given round.
        """
        if len(self.rounds) == 1 and abs(round_index) > 1:
            # account for day 1 where there is only 1 round - prep day 1.
            round_index = -1

        tags = (n for n in self.rounds[round_index])
        return LeagueWarIterator(client=self._client, tags=tags, cache=cache, cls=cls)
