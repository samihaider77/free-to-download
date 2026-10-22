# Free-to-Download browser extension

Adds a **Download this video** button over web videos and sends your choice to the Free-to-Download desktop app.

## Install (Chrome; Edge and Brave use the same steps)

1. Install and open the Free-to-Download app.
2. Open `chrome://extensions`, switch on **Developer mode**, click **Load unpacked** and select this folder.
3. In the app, click **Browser → Copy pairing token**. Open the extension's **Settings** (toolbar icon → Settings), paste the token and save.

## What it does

- **Video button**: appears over videos on the page. Its menu offers quality choices (on YouTube, LinkedIn and similar sites) and any HLS/DASH streams or video files noticed while the video played.
- **Right-click menu**: *Download with Free-to-Download* on links, images, audio and video.
- **Toolbar popup**: send pasted URLs, scan the current page for links, or download the video on the current page.

## Privacy

- Requests go only to the app on your own computer (`127.0.0.1`), authenticated with the pairing token.
- Detected media addresses are kept in temporary session storage per tab (at most 60, for up to 30 minutes), cleared when the tab navigates or closes, and sent to the app only when you click.
- No cookies or login headers are read or sent, and nothing is sent anywhere else.

## Limits

DRM-protected video and live streams are not supported. Videos that require you to be logged in, anti-bot checks, or expired links may fail.
