"""Single source of the app version; the release workflow checks the git tag and extension manifest against it."""
VERSION = "0.6.0"
NAME = "Free-to-Download"

# Browser extensions allowed to pair automatically, by their fixed extension ID.
# The first is fixed by the public "key" in browser-extension/manifest.json (Load unpacked).
# Add the Chrome Web Store / Edge Add-ons IDs here once those listings exist.
EXTENSION_IDS = (
    "peokmobebldmdpbnlnbgolckefjcndkf",
)
