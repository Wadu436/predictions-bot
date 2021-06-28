import config

# Don't modify this
TORTOISE_ORM = {
    "connections": {"default": config.database},
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],
            "default_connection": "default",
        },
    },
}
