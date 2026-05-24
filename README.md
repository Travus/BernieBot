# BernieBot
This is BernieBot, the custom bot used in the Official NicoB Discord server. The bot is based on the [Travus Bot Base](https://github.com/Travus/Travus_Bot_Base). The bot is written, maintained, and run by [Travus](https://github.com/Travus). For contact see [the contact section](#contact).  
The bot is currently in development.

### Running the bot
BernieBot is not a standalone application — it is a set of modules loaded by the [Travus Bot Base](https://github.com/Travus/Travus_Bot_Base) (TBB) at runtime.

For local development, `dev-compose.yml` builds TBB from a sibling checkout and overlay-mounts each module file individually (so TBB's own `modules/dev.py` stays visible):

```
docker compose -f dev-compose.yml up
```

Module-specific settings (channel/role IDs, etc.) are not stored in this repo; they are set at runtime via TBB's `config` command and persisted in the database.

### Assembling modules on the host
On the server, `scripts/assemble_modules.sh` builds the live module set that gets bind-mounted into the bot container. It:

- discovers every repo under the repositories directory that has a non-empty `modules/` folder
- optionally tars the current modules into a dated backup
- prompts per repo whether to include its modules
- copies each selected repo's entire `modules/` tree
- aborts before changing anything if two selected repos provide the same file or directory name

```
./scripts/assemble_modules.sh
```


### Contact
If you need to get in contact with me for any reason, feel free to send me a message via Discord, Twitter, or leave an issue on this repository if applicable. That said, your best bet is probably to reach me on Discord. You can also reach me at berniebot@travus.dev.  
> Discord: travus  
> Twitter: [@RealTravus](https://twitter.com/realtravus)  
> [Open a GitHub Issue](https://github.com/Travus/BernieBot/issues/new)  
> Email: berniebot@travus.dev  
---

<br>

### Credits
*BernieBot* is made my [Travus](https://github.com/Travus).  
The [Travus Bot Base](https://github.com/Travus/Travus_Bot_Base) is made by [Travus](https://github.com/Travus).  
[Discord.py](https://github.com/Rapptz/discord.py) is made by [Rapptz](https://github.com/Rapptz) and the other contributors to the project.  

*BernieBot* is made under the [MIT License](LICENSE.md), meaning you are welcome to change, redistribute, and use it however you see fit. I am not liable for any problems you may encounter by using the bot base.