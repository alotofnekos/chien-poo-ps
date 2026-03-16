# Meow (Pokemon Showdown Bot)

A Pokemon Showdown chat bot with automated tour scheduling, tour creation, set lookup, team showing interface, and cats.

---

## Commands

All commands are prefixed with `meow` (case-insensitive).

### General

| Command | Description |
|--------|-------------|
| `meow` | Meows back at you |
| `meow uptime` | Shows how long the bot has been running |
| `meow help` | Shows the command list | 

---

### Tournament Management

| Command | Description |
|--------|-------------|
| `meow start <gen>` | Starts a tour for the given gen. E.g. `meow start SV` starts a Gen 9 Mono tour |
| `meow next tn` | Shows the next scheduled tournight and when it will be hosted | 
| `meow cancel next tn` | Cancels the next scheduled tournight | 
| `meow uncancel next tn` | Undoes a cancellation of the next tournight |

---

### Show

| Command | Description |
|--------|-------------|
| `meow show cat` | Posts a random cat image |
| `meow show potd` | Shows the Pokemon of the Day |
| `meow show schedule` | Shows Meow's automated tour schedule |
| `meow show set <pokemon> [format] [set filter] [extra filters]` | Shows sets for a given Pokemon, optionally filtered by format or other criteria |
| `meow show bans <tourname>` | Shows the rules and bans for a given tour |
| `meow show paste <pokepaste url>` | Shows the team from a given PokePaste URL |

---

### Rule Management

| Command | Description | Required Rank |
|--------|-------------|---------------|
| `meow add tour [internalname] using [tour type] [as name]` | Adds a tour that meow can create. Take note that you need to use add rules / misc commands separately. Tour type is the main format (i.e. gen9monotype) and internalname is what you want meow to call it through Meow start command | Room Owner Only |
| `meow remove tour [internalname]` | Removes a tour from Meow. Tour must have no rules / misc commands before being deleted (i.e. use remove rule / remove misc commands first) | Room Owner Only |
| `meow add rule <tour> <bans>` | Adds bans to a tour. Must follow challenge code format, e.g. `+Chien-Pao, -Flutter Mane` | Room Owner Only |
| `meow remove rule <tour> <bans>` | Removes bans from a tour | Room Owner Only |
| `meow add misc command <tour> <command>` | Adds misc commands to a tour| Room Owner + Moderator Only |
| `meow remove misc command <tour> <command>` | Removes misc commands to a tour| Room Owner + Moderator Only |

---

### Say

| Command | Description |
|--------|-------------|
| `meow say <message>` | Posts an image of a cat saying your message. Has built-in censorship | 

---


