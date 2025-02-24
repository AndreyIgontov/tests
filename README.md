# Tests

## Background
Hi Adil. I remember last time I had an interview at Procurify, I showcased not my best performance in terms of tests.
I have experience with testing, but unfortunately my current workplace does not encourage writing tests, so I might be a little rusty.
It's a great shame in my opinion because me and my colleagues already suffered a lot of issues caused by lack of test coverage, but unfortunately I don't have enough authority to pitch this to higher management.
In my previous place of work we were writing a lot of tests and I still remember my first task being to cover a huge chunk of codebase with tests to familiarize myself with it.

## About
Taking into account the background above I decided to showcase how I would cover one of the classes from an abandoned service of ours.
The class itself is responsible for the interaction with VMware vCenter to perform operations on virtual machines and related infrastructure.
Unfortunately I didn't have enough of my free time to make it 100% coverage, but I hope you'll get the idea.

P.S. I really don't like the camel case function names and absence of @staticmethod decorators in the VSphere class, but it's a codestyle that we're forced to use.

## How to Run

Build the image:
```bash
docker build -t cgi-tests .
```

Run tests:
```bash
docker run --rm cgi-tests
```
