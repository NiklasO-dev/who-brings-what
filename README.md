# Who Brings What?

A simple web app for coordinating potlucks and shared events. One person creates an event, defines suggested must-have items, and shares a link. Guests add what they'll bring, join existing items, and leave comments.

No user accounts — access works through secret links. All event content is **encrypted in the database** with a per-event encryption key (AES-256-GCM).

## Features

- **Create an event** with a title and optional organizer email
- **Per-event encryption** — titles, items, names, and comments encrypted at rest
- **Admin link** — manage presets, moderate entries/comments, export, share QR
- **Guest link** — add items, join others ("I'll bring salad too"), comment
- **Preset items** — organizer defines must-haves guests can sign up for
- **Share page** with QR code and printable handout
- **Export / print** table with all items, people, and comments
- **Automatic cleanup** of old events (configurable)
- **English and German** UI, dark mode

## Quick Start

```bash
cd who-brings-what
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Open http://localhost:8001

## Docker / Podman

```bash
podman-compose -f docker-compose.local.yml up --build
```

Local clean rebuild:

```bash
podman-compose -f docker-compose.local.yml down && podman rmi localhost/who-brings-what_wbw-app:latest 2>/dev/null; podman build --no-cache -t who-brings-what_wbw-app . && podman-compose -f docker-compose.local.yml up -d
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_BASE_URL` | `http://localhost:8001` | Public URL for generated links |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/event.db` | SQLite connection string |
| `ADMIN_PASSWORD` | `change-this-password` | Site admin dashboard (`/admin`) |
| `EVENT_MAX_AGE_DAYS` | `548` | Days until active events are deleted |
| `DONE_EVENT_CLEANUP_DAYS` | `30` | Days until done events are cleaned up |
| `SMTP_*` | *(empty)* | Optional email on event creation |

## How to use

### Organizer

1. Create an event at `/`
2. Bookmark the **admin link**
3. Add preset items (salad, drinks, …)
4. Share the **guest link** or print the QR handout
5. Moderate, export, mark done, or delete when finished

### Guest

1. Open the guest link
2. Enter encryption key if needed
3. Enter your name (saved in browser)
4. Add items, join existing ones, leave comments

## License

MIT — see [LICENSE](LICENSE).
