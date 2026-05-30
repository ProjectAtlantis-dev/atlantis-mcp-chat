This set of folders is essentially a multiuser human + bot chat system (game = chat)

These files are dynamically loaded by the Atlantis MCP system (~/work/aud/atlantis-mcp-server) but we are NOT allowed to modify that system!!

The MCP loader will publish functions according to the various decorators. These functions can also interact with the Atlantis cloud system () via atlantis.xxx library usually to run commands because it's better to just run commands directly than overload atlantis.py with methods that do the same thing.

The /Data folder holds live data for each game

The /Game folder is static assets - Bots, Locations etc

Bot = a character/persona/engine unit. The bot primary key is its sid.
Slot = when user binds their id (sid) to a Bot. Any game can have a mix of humans or bots.
Camera = when user binds their browser (terminal) to a Location. Cameras can also move with Slots.

Bot responses can be triggered by chat or tick.

Chat callback must pull transcript and figure out where chat happened, who spoke, and who was listening if anyone, then decide who should respond. If a bot should respond, then send the package off to Open Router or whatever.
