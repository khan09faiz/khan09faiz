# Contact page

The form on `index.html` is served by GitHub Pages and posts to
[Web3Forms](https://web3forms.com), which forwards each submission to an email
address. No backend, no server, no secrets in the repo — the access key is a
public submit-only token.

## Setup (once, about a minute)

1. Go to <https://web3forms.com>, enter `khan09faiz@gmail.com`, and submit.
2. Check that inbox for the **access key** (a UUID) and copy it.
3. In `index.html`, replace `REPLACE_WITH_YOUR_WEB3FORMS_KEY` with the key.
4. In the repo: **Settings → Pages → Source: `main` branch, `/docs` folder.**

The page then lives at <https://khan09faiz.github.io/khan09faiz/> — the URL the
contact card in the README links to.

## What arrives in the inbox

Every submission carries the enquiry type the sender picked (freelance /
full-time / something else), their name, organisation, email, optional phone or
LinkedIn, and the message. Replying to the email replies to the sender.

## Alternatives

Web3Forms is the least-friction option, not the only one. [Formspree](https://formspree.io)
and [Getform](https://getform.io) work the same way — swap the `fetch` URL and the
hidden key field. If you would rather own the whole path, move this form into the
Next.js portfolio and post to an API route that calls [Resend](https://resend.com)
with a server-side key.

## Spam

The hidden `botcheck` field is a honeypot: bots fill it in, humans never see it,
and Web3Forms drops anything that has it set. If spam ever gets through, turn on
the captcha option in the Web3Forms dashboard.
