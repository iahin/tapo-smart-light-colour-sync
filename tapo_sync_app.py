from tapo_sync.config import load_env_defaults
from tapo_sync.gui import TapoSyncApp


def main() -> None:
    app = TapoSyncApp(load_env_defaults())
    app.mainloop()


if __name__ == "__main__":
    main()
