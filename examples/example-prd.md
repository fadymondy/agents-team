# Sample PRD: e-Shop

A small e-commerce SaaS for boutique sellers. Sellers list products, buyers check out via Stripe, both interact through a web app and a mobile companion. This PRD is the input to `/team-gen` — see [`example-team.json`](example-team.json) for the team it produces and [`README.md`](README.md) for how to run it.

## Product overview

**e-Shop** lets a small seller (1–5 person business) list up to 200 products, take payments through Stripe, fulfill orders manually, and email buyers about shipping. The buyer side is a public storefront with cart + checkout + order tracking.

We're shipping a v1 with the smallest deliverable that proves the model: a single seller can list products, a buyer can buy one, money lands in the seller's account, and the seller knows it shipped. Everything else is post-v1.

## Services

- **`api`** — REST + WebSocket backend. Owns auth, product catalog, order state machine, Stripe webhooks. TypeScript on Node 20, Postgres 16, deployed on GCP Cloud Run.
- **`web`** — public storefront + seller dashboard. React 19 + TanStack Router. Deployed on Vercel.
- **`payments`** — thin service that owns the Stripe integration: webhook receiver, idempotency keys, refund flow. TypeScript on Node 20.
- **`mobile`** — buyer companion app: order tracking + push notifications. Flutter, iOS + Android.

## Tech stack

- **Languages:** TypeScript (api, web, payments), Dart (mobile)
- **DB:** Postgres 16; one instance, shared across services through the api layer
- **Auth:** session cookies on web (api owns the session store); JWT on mobile
- **Payments:** Stripe (Connect Express for sellers, Checkout for buyers)
- **CI/CD:** GitHub Actions; Cloud Run for api/payments, Vercel for web, Codemagic for mobile
- **Observability:** Sentry + a small homegrown error log dashboard

## Constraints

- **Regulated**: handles PII (buyer addresses) and payment data (PCI-adjacent via Stripe). Security review is mandatory pre-release.
- **Multi-locale**: launching in English first; Spanish v1.1, Arabic v1.2.
- **Always-on monitor**: buyer-facing; downtime is revenue lost. Need a background watcher catching error-rate spikes.
- **Small team**: 1 founder + 1 contractor. Generated team must reflect that — lean, no overlapping mandates.

## Team size hint

Lean — 6–8 specialists max. Skip dedicated tech-leader for v1; orchestrator + domain engineers + qa + security + devops + monitor is enough.

## Acceptance for the team

- An orchestrator routing across api/web/payments/mobile.
- One domain engineer per service.
- A designer who owns the storefront UX.
- A QA engineer with Playwright for web + integration tests.
- A security engineer focused on auth + PCI surface.
- A devops engineer owning Cloud Run + Vercel pipelines.
- An always-on monitor.
- Skills: `/meet` (decision-making), `/evaluate-agent` (agent quality), `/shop-status` (daily team check), `/shop-deploy` (controlled releases).

This is the team `example-team.json` describes, generated and self-evaluated end-to-end.
