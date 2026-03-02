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
| `meow add rule <tour> <bans>` | Adds bans to a tour. Must follow challenge code format, e.g. `+Chien-Pao, -Flutter Mane` | Room Owner Only |
| `meow remove rule <tour> <bans>` | Removes bans from a tour | Room Owner Only |

---

### Say

| Command | Description |
|--------|-------------|
| `meow say <message>` | Posts an image of a cat saying your message. Has built-in censorship | 

---

## Notes

- Ban formatting for `add`/`remove rule` must match the challenge code format exactly, e.g. `+Chien-Pao, -Flutter Mane`
- `meow show set` usage: `meow show set <pokemon> [format] [set filter] [extra filters]`
- `meow say` will refuse to send messages that are flagged by the profanity filter
