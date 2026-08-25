# Gaming News Watch

Polls gaming press-release channels and publications, alerts you on Telegram
the moment something new is published. Runs on GitHub Actions, so there's no
server to pay for or maintain, and no button to click.

## How it works

- `feeds.json` lists the RSS feeds to watch, split into `primary` (official
  company newsrooms and trade press) and `secondary` (publications known for
  breaking scoops before official announcements).
- `monitor.py` checks each feed, compares entries against `seen.json`
  (the running memory of what's already been alerted), and sends a Telegram
  message for anything new.
- `.github/workflows/watch.yml` runs `monitor.py` on a schedule (every 15
  minutes) using GitHub's free Actions minutes, and commits the updated
  `seen.json` back to the repo so state persists between runs.

Cost: $0. GitHub Actions gives 2,000 free minutes/month on a private repo,
this job takes well under a minute per run, so a 15-minute cadence uses a
small fraction of that.

## Setup (about 10 minutes)

1. **Create a Telegram bot**
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
     follow the prompts. You'll get a token that looks like
     `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   - Send your new bot any message, then visit
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser to
     find your `chat.id` in the JSON response. That's your `TELEGRAM_CHAT_ID`.

2. **Create a private GitHub repo** and push these files to it.

3. **Add two repo secrets** (Settings -> Secrets and variables -> Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. **Enable Actions** on the repo (Actions tab -> enable). The workflow will
   start running on its schedule. You can also trigger it manually the first
   time via Actions -> Gaming News Watch -> Run workflow, just to confirm it
   works.

5. First run only records current state and sends no alerts (so you don't
   get 200 messages of "breaking news" that's actually six months old).
   Every run after that only alerts on genuinely new entries.

## About the feed list

I've verified the `primary` feeds resolve. A couple of the `secondary` ones
(VGC, IGN) I've included based on known URL patterns but haven't confirmed
live, RSS URLs occasionally get restructured. If one comes back empty in the
Action logs, open the site in a browser, look for its RSS icon or check
`sitename.com/feed`, and swap the URL in `feeds.json`. For sites with no
public RSS at all (Nintendo's official newsroom is the main gap), a service
like rss.app can generate a feed from any webpage, free tier covers a
handful of feeds.

Adding more sources later is just adding an entry to `feeds.json`, no code
changes needed.

## The honest limit on "before other publications"

RSS gets you the alert the second something is *publicly* posted, which
already beats manually checking sites. But outlets like IGN or Bloomberg
sometimes publish ahead of a public press release because they're on an
embargo list or have a direct PR relationship, that's not something a bot
can scrape, it comes from being in the room.

Given your PR background, the highest-leverage move alongside this bot is
getting yourself onto the actual embargo/press lists for the publishers and
platform holders you cover (most have a press contact page for exactly
this). That closes the gap RSS can't.

## Next step

Once this is alerting reliably, the natural follow-on is a short style
guide/script for turning an alert into a fast, publishable piece, headline
conventions, how much to quote vs. paraphrase, standard structure. Happy to
build that whenever you're ready.
