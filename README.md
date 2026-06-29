# Abstrait

This repository is a multi-user human and bot chat system. A game is the chat
session.

## Entry Flow

The normal user flow starts from the Home folder:

1. `homepage.first_menu()` shows the first menu.
2. The user chooses the game path.
3. `runner.game_find_or_create()` decides whether to create a new game, join an
   existing game, or resume a game.
4. Once a game key is selected, `runner.game_init(game_key)` prepares the active
   chat window for that game.

`game_init()` is responsible for the setup that must be true before chat can
work:

- Ensure the caller is in the game.
- Ensure the chat callback is configured.
- Create or load the game roster.
- Let the user edit/select their roster slot if needed.
- Let the user set the terminal camera.
- Let the owner start the game.

## Concepts

- **Bot**: A character, persona, and engine unit. The bot primary key is its
  `sid`.
- **Slot**: A game roster slot. A slot can be assigned to either a human or a
  bot, so any game can mix humans and bots.
- **Camera**: A terminal/browser viewport bound to a location. Cameras can also
  follow roster slots.

## Bot Responses

Bot responses can be triggered by chat or by tick.

The chat callback must:

1. Pull the transcript.
2. Determine where the chat happened.
3. Determine who spoke.
4. Determine who was listening, if anyone.
5. Decide who should respond.
6. If a bot should respond, send the package to OpenRouter or the configured
   model provider.

## Runtime

These files are dynamically loaded by the Atlantis MCP system:

`~/work/aud/atlantis-mcp-server`

Do not modify that system from this repository.

MCP server log:

`~/work/aud/atlantis-mcp-server/python-server/runServer.log`

The MCP loader publishes functions according to their decorators. These
functions can interact with the Atlantis cloud system through the `atlantis.*`
library, usually by running commands directly rather than adding duplicate
wrapper methods to `atlantis.py`.

## Repository Layout

- `Data/` holds live data for each game.
- `Game/` holds static assets such as bots and locations.
