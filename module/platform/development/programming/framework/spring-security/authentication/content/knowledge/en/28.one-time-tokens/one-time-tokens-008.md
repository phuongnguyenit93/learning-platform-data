# Preventing Account Enumeration, Rate-Limiting Requests, and Protecting Tokens from Logs and Browser History

## 1. Scope and Why the Entire Lifecycle of a One-Time Token Must Be Protected

**One-time tokens** commonly appear in features such as password reset, email verification, invitation acceptance, sensitive-action confirmation, or login via links (*magic links*). A valid token can grant its holder permission to perform **a time-limited action** without knowing the old password. Thus, even if it only exists for a few minutes, a token remains a **secret with credential-level value**.

An account recovery flow can be attacked **even when tokens are generated with strong cryptography**, due to three distinct classes of flaws:

1. **Account enumeration:** a "forgot password" endpoint responds differently when an email exists, or exhibits measurable differences in HTTP status, size, redirect, timing, rate-limiting, or error messages. Attackers build a list of real accounts.
2. **Delivery request abuse (*message flooding/abuse*):** an attacker sends thousands of requests to one email/phone number, causing spam, SMS charges, quota exhaustion, UX disruption, or abusing resends to invalidate the user's valid token.
3. **Token leakage through operations and browsers:** a token placed in a query string can be recorded in reverse-proxy access logs, APM, application errors, analytics, browser history, `Referer`, or support tools. An unexpired, unused token can be hijacked.

Controls must be designed **end-to-end** from receiving the request through delivery, opening the link, completing the action, revoking tokens, and auditing. Merely adding a CAPTCHA or setting a 15-minute TTL **is not enough** to replace the remaining defensive boundaries.

### Reference Model

~~~text
[Anonymous client]
        |
        | POST /account/recovery/request { email }
        v
[Gateway / abuse control]
  - rate limit by IP, identifier, tenant, global
  - prevent request floods, never trust spoofed IP headers
        |
        v
[Application request service]
  - normalize identifier consistently
  - do NOT reveal whether account exists
  - look up user, check policy
  - send only if eligible
  - return uniform public response
        |
        v
[Token issuer / DB / queue]
  - CSPRNG, high-entropy secret
  - store hash/HMAC + purpose + userId + expiry
  - enqueue email/SMS in a controlled manner
        |
        v
[Recipient]
  - receives link/code over side channel
  - opens clean page with no third-party tracking
  - consumes token only upon user confirmation via POST
        |
        v
[Atomic token consume + business action]
  - verify purpose, expiry, used/revoked
  - correct user and permission for the action
  - mark used inside transaction
  - complete change / create limited session
  - redirect to a URL containing no token
~~~

Three mandatory questions: **Who is allowed to request delivery? Where can the token leak? How do we ensure exactly one request actually consumes the token?**

## 2. Understanding Account Enumeration Correctly

Account enumeration is observing responses or side effects to learn whether an attacker-tested identifier belongs to a real account. Attackers often do not need a password; a list of valid emails supports spear phishing, password spraying, credential stuffing, or customer data harvesting.

Example **that must not be designed**:

~~~http
POST /account/recovery/request
Content-Type: application/json

{"email":"lan@example.test"}
~~~

~~~json
{"exists": true, "message": "Sent link to this account"}
~~~

For a non-existent email, the server returns `404 {"exists":false}`. By probing an email list, outsiders identify exact accounts. Enumeration also occurs when **both return `200`** yet differ in body, `Location`, headers, processing time, or cooldown state.

### What Should the Public Response Look Like?

For a syntactically valid identifier, return the exact same response **regardless of whether the email exists**:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{"message":"If the information matches an eligible account, we will send instructions."}
~~~

The critical piece is **identical HTTP status, identical public structure and wording, and identical redirect/cooldown policies** across existing, non-existent, locked, or ineligible accounts, unless there is a specific security reason accepted by the threat model. Never return `accountExists`, `hasMfa`, `emailVerified`, `userStatus`, or `maskedEmail` only on the existing-account branch.

**`202 Accepted` does not mean an email was definitely sent.** It reflects that the server accepted the request for processing per policy. For a non-existent account, the system creates no token and sends no email while still returning the same public message.

Syntax validation errors (e.g., an email missing `@`) may be reported under the same rule for **every identifier with the same syntax error**; that difference is not existence enumeration by itself. Once input is valid, however, never let the account-lookup result leak into the response.

### Leakage Channels Beyond JSON

| Observable Channel | Bad Example | Mitigation |
|---|---|---|
| HTTP status | `200` for real account, `404` for unknown account. | Uniform public response. |
| Body / UI message | "Email not found"; showing account name hint. | Generic phrasing, no hints of real accounts. |
| Redirect | `302 /sent` for real account, `200 /form` for unknown account. | Unified navigation for the same request class. |
| Response size | Existing branch returns extra metadata. | Shared template/schema. |
| Timing | Missed lookup returns immediately; real account sends SMTP synchronously adding 800 ms. | Offload delivery to a queue and minimize branch divergence. |
| Rate-limit | Existing identifier gets cooldown, non-existent does not. | Apply quotas to **every valid identifier**, even without an account. |
| Email/SMS / notifications | An attacker-owned mailbox tests delivery directly. | Delivery to a mailbox is inherent to the flow; do not expand into an endpoint revealing others' existence. |
| Token inspection endpoint | Shows "user X is resetting password" before verifying token. | Return only minimal token status, never leak profile info. |
| Public telemetry | `X-Account-Found: true`, differing error codes. | Never expose account state in client-facing headers/analytics. |

The goal is not to promise **strictly identical** millisecond latency across the Internet; the goal is to eliminate observable logical differences, minimize systematic timing signals, and test using appropriate statistics.

## 3. Limiting Timing Side Channels When Sending Email/SMS

Common mistake:

~~~java
// Do NOT use this pattern on a public endpoint:
if (repository.findByEmail(email).isEmpty()) {
    return ResponseEntity.notFound().build();
}
smtpClient.sendResetEmail(email); // request waits on SMTP
return ResponseEntity.ok().build();
~~~

Even if both branches are changed to `200`, the real-account path waits on the SMTP call while the unknown-account path returns immediately. An attacker can collect multiple response samples to infer the difference.

Designs should:

1. Accept and run syntax and quota checks along the same processing path.
2. Push eligible work onto a **message queue/outbox** or internal processor whose latency does not strongly depend on account existence.
3. Decouple email delivery from HTTP response time. Ensure account lookup/policy checks do not create glaringly divergent branches; run the same initial workflow and perform real delivery inside a worker.
4. Have the delivery job **send only** when the account exists, is eligible, and quota allows. Never send emails to arbitrary addresses just to equalize response time.
5. For throttling, evaluate **quota keys independent of "account exists"** and never return distinct responses for known vs. unknown accounts.

**Do not treat `Thread.sleep(1000)` as an enumeration fix.** Fixed sleeps enable DoS, real timing still varies by branch, and collecting multiple samples can still expose distributional differences. An asynchronous queue decouples the request path from SMTP, though you must still check whether account/quota lookups diverge.

Timing illustration to measure:

~~~text
Known account:    parse + quota + enqueue ack + HTTP 202
Unknown account:  parse + quota + enqueue ack + HTTP 202

Worker:
  -> lookup account
  -> (known + allowed): issue token + enqueue mail
  -> (unknown/blocked): no mail
  -> audit with protected metadata
~~~

In real systems, workers and request handlers must agree on how identifiers and quotas are normalized; never expose another endpoint publicly reporting job status "mail sent/not sent".

## 4. Rate Limiting Must Protect Against Both Account Guessing and Inbox Spam

High-entropy tokens are hard to **guess directly**, yet attackers need not guess: repeatedly requesting password resets floods the victim's inbox or burns SMS budget. Request quotas are therefore a mandatory security design control.

**Never rate-limit by IP alone** because attackers can use botnets or rotating IPs; conversely, a corporate NAT/VPN IP may represent thousands of legitimate users. Never limit by email alone because attackers can vary emails or exploit normalization quirks. Combine multiple dimensions.

| Limit Dimension | What It Controls | Notes |
|---|---|---|
| **IP/client network** | Floods from a single network source or proxy. | NAT/shared IPs: avoid overly harsh org-wide lockouts. |
| **Normalized account identifier** | Spamming one mailbox/identifier across rotating IPs. | Apply even to identifiers **with no account**; consider HMACing identifiers in the rate-limit store. |
| **Authenticated user / session** | Post-login or post-captcha abuse. | Recovery requests are usually anonymous, so you cannot rely solely on sessions. |
| **Tenant / domain / organization** | Protects system and per-customer quotas. | Do not turn domain limits into an easy DoS vector against a tenant. |
| **Global endpoint / delivery provider** | Protects SMTP/SMS quotas and costs. | Requires backpressure and sensible worker retries. |
| **Device / behavioral signals** | Aids automation detection and risk scoring. | Cookies/device fingerprints can be cleared/spoofed; consider privacy. |

### A Sample Policy (Values Must Be Tuned)

~~~text
POST /account/recovery/request

- Per normalized identifier: max 3 issuances in 60 minutes.
- Resend cooldown for the same identifier: 60 seconds.
- Per IP: short-window limit + separate burst allowance.
- Per tenant / system-wide: cost thresholds and queue size caps.
- On abuse signals: CAPTCHA/Turnstile challenge or elevated risk action.
- Always return a uniform public message for emails with/without an account.
~~~

The numbers above are **examples only**. Choose them based on real traffic, accessibility needs, NATs, SMS costs, email latency, and threat model. Never let bad actors sending repeated reset requests lock out an account's normal login. **Reset spam must not disable an account before a valid token is presented**, unless under a dedicated incident-response policy.

**Important:** if someone clicks "Resend" repeatedly, do not suddenly reveal "This address already has an active token". The frontend can display a generic "If eligible, instructions will be sent" with a UI cooldown, while real quotas are enforced server-side.

### Distributed Quotas and IP Attribution

In multi-instance Spring Boot, an in-process `ConcurrentHashMap` **is not a shared rate limiter**. Use a distributed store (such as Redis) or a gateway limiter with atomic operations/TTLs and race-free updates. Behind a reverse proxy, take client IPs from forwarded headers **only when the proxy is trusted and strips/overwrites client-sent headers**. Never trust an arbitrary `X-Forwarded-For` header from the Internet to bypass rate limits.

For identifiers, you can compute `HMAC(quotaPepper, normalizedIdentifier)` as the Redis key to avoid storing raw emails long-term; manage `quotaPepper` separately from token peppers. Even when HMACed, operational metadata still needs retention and access-control policies.

## 5. Token Brute-Force Protection: Distinct from Delivery Limits

There are two independent surfaces:

- **Request endpoint:** attackers trigger many emails/SMS requesting new tokens (spam and enumeration).
- **Verify/consume endpoint:** attackers guess many codes or token strings to seize a session or change a password.

With a **32-byte (256-bit) random token** generated by a CSPRNG, random guessing is practically impossible; yet you must still throttle floods to protect CPU/DB and monitor misuse. With a **6-digit code**, there are only one million possibilities, requiring strict failed-attempt limits per identifier/challenge, short TTLs, cooldowns, *challenge*-level lockouts (without locking the whole account), and monitoring.

| Type | Strength / Use Case | Additional Controls |
|---|---|---|
| Base64url URL token from 32-byte CSPRNG | High entropy; used for password reset/email verify. | TTL, single-use, purpose binding, no URL leaks, HTTPS, rate-limit request/consume. |
| Email/SMS 6–8 digit PIN | Easy to type manually, but vastly smaller guessing space. | Atomic attempt counter, per-challenge lockout, send quota, HMAC/pepper at rest, anti-reuse. |
| Email magic link | Short-lived login right based on mailbox access. | Same as URL token, plus device/session binding per threat model and care with link scanners. |
| Email verification token | Proves ability to receive mail at that address within the flow. | Bind to account + address being verified; never grant high roles or change ownership automatically. |

Never cross token purposes. A `VERIFY_EMAIL` token must not work at `RESET_PASSWORD`, and an `ACCEPT_INVITATION` token must not grant an admin session unless the flow is explicitly designed, verified, and authorized.

## 6. Generating and Storing One-Time Tokens Without Keeping Plaintext

For recovery links, the server should generate an **unguessable** secret with `SecureRandom`. For example, 32 random bytes encoded as unpadded Base64url yield 43 characters. Never use `Math.random()`, timestamps, incremental IDs, emails, or hashed emails as tokens.

~~~java
byte[] bytes = new byte[32];                       // 256 bits
new java.security.SecureRandom().nextBytes(bytes);
String token = java.util.Base64.getUrlEncoder()
        .withoutPadding().encodeToString(bytes); // 43 chars
~~~

The code above is a **Java 17 snippet**, not a standalone program.

Storage pattern:

~~~text
Client receives raw secret exactly once
             |
             v
Server computes:
  verifier = SHA-256("one-time-token:v1:" || rawSecret)
             |
             v
Database:
  token_id (optional selector / internal id)
  verifier (not rawSecret)
  subject_user_id
  purpose
  expires_at
  consumed_at
  revoked_at
  sent_to_address_version / desired email (if relevant)
  created_at, channel, issuer_context
~~~

With 256 bits of entropy, one-way SHA-256 is generally suitable for strong random tokens under the threat model; HMAC-SHA-256 with an off-DB pepper adds isolation if the DB leaks. **Do not use fast unsalted SHA-256 for short PINs as if they were 256-bit secrets**: PINs need dedicated offline brute-force defenses and online limits.

**Never store plaintext tokens in the DB, queue payloads, job logs, or long-lived event streams.** To send emails, workers sometimes must handle the plaintext token briefly; restrict permissions, retention, logs, and transport from queue to mailer. If an email job must carry the raw token in a queue for a period, that is still secret storage—minimize lifetime, encrypt, restrict access, or issue inside the worker with a proper transaction.

The token is a **credential**, distinct from a public `token_id` used for lookup. A public ID never proves the user received the email. Binding tokens to **user ID, purpose, expiresAt, and context** prevents using tokens on the wrong action or wrong account.

## 7. Single-Use: Must Be Atomic, Not Just Checking a `used` Flag Before Updating

A familiar race condition bug:

~~~text
Request A: SELECT used_at == NULL  -> true
Request B: SELECT used_at == NULL  -> true
Request A: change password, UPDATE used_at
Request B: change password, UPDATE used_at
~~~

Both requests "succeed" because check and update are not inside one atomic boundary. The system must ensure **only one valid consume operation** wins, even across multiple concurrent application instances.

Example PostgreSQL SQL using `UPDATE ... RETURNING` to claim the token:

~~~sql
UPDATE one_time_tokens
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE token_verifier = :computed_verifier
   AND purpose = 'PASSWORD_RESET'
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_user_id;
~~~

If zero rows return, the token is no longer valid for this operation. **The predicates must belong to the same atomic UPDATE**, backed by a unique index/constraint on the verifier.

**One more critical step:** when a token resets a password, marking it consumed and **updating the password hash** must occur in **the same database transaction**, after validating password policy. If the password update fails and the transaction rolls back, the consume mark rolls back too. When external mail/auditing cannot join the same transaction, use an outbox/event to avoid half-baked states. For databases and distributed systems, also evaluate idempotency, isolation, and retry behavior.

An already-used token must lose validity even before `expires_at`. An expired token still sitting in the DB must not pass; periodic cleanup is operational maintenance, not a substitute for expiry predicates during consumption.

### Recommended Lifecycle

~~~text
ISSUED  ── delivered ──►  PENDING
                             |
               +-------------+-------------+
               |             |             |
           valid POST      time limit     revoked
               |             |             |
               v             v             v
            CONSUMED       EXPIRED       REVOKED
               |
        cannot redeem again

GET link  -> show recovery page, NO state mutation
POST form -> check proof + business action atomically
~~~

Depending on business rules, you can cap outstanding tokens per account and set a resend policy: keep old tokens until expiry or revoke on reissue. **If every anonymous request automatically revokes prior tokens, an attacker can flood requests to invalidate the link the user just received.** Pick a policy with cooldowns, rate limits, and clear UX; never apply "new token always deletes all old tokens" without evaluating DoS.

## 8. Standalone Java 17: Issuing Tokens, Storing Hashes, and Consuming Once

The following example runs on **plain JDK 17**, without Spring. Tokens are genuinely random and therefore **not printed to screen**. The database is simulated with a `ConcurrentHashMap` in one process; `computeIfPresent` makes single-record consumption atomic in this demo. Production must use DB transactions/unique constraints (or a distributed atomic store) for multi-instance correctness and to couple consumption with the business action.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public class OneTimeTokenSafetyDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final ConcurrentHashMap<String, Ticket> TOKENS =
            new ConcurrentHashMap<>();
    private static final Duration TTL = Duration.ofMinutes(15);

    record Ticket(String userId, String purpose, Instant expiresAt) {}

    static String verifier(String rawToken) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String input = "one-time-token:v1:" + rawToken;
            byte[] result = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(result);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 missing", e);
        }
    }

    static String issue(String userId, String purpose, Instant now) {
        while (true) {
            byte[] random = new byte[32];          // 256-bit secret
            RNG.nextBytes(random);
            String raw = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(random);
            Ticket record = new Ticket(userId, purpose, now.plus(TTL));

            if (TOKENS.putIfAbsent(verifier(raw), record) == null) {
                return raw; // issued once to the authorized recipient
            }
        }
    }

    static Optional<String> consume(
            String raw, String expectedPurpose, Instant now) {
        if (raw == null || !raw.matches("[A-Za-z0-9_-]{43}")) {
            return Optional.empty();
        }

        AtomicReference<String> acceptedUser = new AtomicReference<>();
        TOKENS.computeIfPresent(verifier(raw), (digest, ticket) -> {
            if (!ticket.purpose().equals(expectedPurpose)) {
                return ticket;     // do not consume token for wrong purpose
            }
            if (!now.isBefore(ticket.expiresAt())) {
                return null;       // expired: delete record, grant no access
            }
            acceptedUser.set(ticket.userId());
            return null;           // consumed: remove atomically
        });
        return Optional.ofNullable(acceptedUser.get());
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String reset = issue("usr-1042", "PASSWORD_RESET", now);
        System.out.println("token length: " + reset.length());
        System.out.println("first use: " +
            consume(reset, "PASSWORD_RESET", now.plusSeconds(20))
                .orElse("DENIED"));
        System.out.println("replay: " +
            consume(reset, "PASSWORD_RESET", now.plusSeconds(21))
                .orElse("DENIED"));

        String expired = issue("usr-1042", "PASSWORD_RESET", now);
        System.out.println("expired: " +
            consume(expired, "PASSWORD_RESET", now.plus(TTL))
                .orElse("DENIED"));

        String email = issue("usr-1042", "VERIFY_EMAIL", now);
        System.out.println("wrong purpose: " +
            consume(email, "PASSWORD_RESET", now.plusSeconds(30))
                .orElse("DENIED"));
        System.out.println("correct purpose: " +
            consume(email, "VERIFY_EMAIL", now.plusSeconds(31))
                .orElse("DENIED"));
    }
}
~~~

Save as `OneTimeTokenSafetyDemo.java` and run:

~~~bash
javac OneTimeTokenSafetyDemo.java
java OneTimeTokenSafetyDemo
~~~

Exact stdout:

~~~text
token length: 43
first use: usr-1042
replay: DENIED
expired: DENIED
wrong purpose: DENIED
correct purpose: usr-1042
~~~

Explanation: 32-byte token -> 43 Base64url characters; the hash only looks up the record; `computeIfPresent` lets only one thread remove a valid record before a second thread sees it. Wrong purpose does not consume; expiration right at the boundary is blocked. A fixed `Instant` makes stdout deterministic, while **the token itself is not fixed**.

**Limitations of the demo:** `ConcurrentHashMap` lives only on one JVM; there is no database, rate limit, password hashing, email, transaction with a business action, request protection, CSRF, or multi-replica coordination. `consume` returns an internal ID to demonstrate mechanics; production must never return that ID in a public response before the token is properly authenticated/authorized per flow. Never use this snippet as a complete password reset system.

## 9. Tokens in URLs: Why They Easily End Up in Logs and History

An email might contain a link:

~~~text
https://accounts.example.test/recovery/open?token=<opaque-random-token>
~~~

The `<opaque-random-token>` string is an illustrative placeholder, not a real credential. When a user opens the link, the token can appear in many places:

- **Browser address bar and history:** users may copy it, take screenshots, sync history across devices, or let extensions observe URLs.
- **HTTP request target:** reverse proxies, CDNs, WAFs, API gateways, and server access logs can record path + query **before Spring Security ever runs**.
- **APM/tracing/error reporting:** span names, request URLs, exception logs, request dumps, and crash reports may include raw queries.
- **`Referer` header:** when a page with a sensitive URL loads assets or navigates, a loose referrer policy can send the full URL (especially same-origin). Browser defaults do not promise zero token leaks across all request types.
- **Analytics, third-party scripts, pixels:** scripts running on the page can read `window.location.href` and send it externally. Some email clients/security scanners also visit links before the user.
- **Screenshots/helpdesk/recordings:** users accidentally attach screenshots or tickets containing the URL.
- **Link preview/antivirus bots:** email security systems may open links automatically to scan them; if GET consumes the token, the user cannot use it, or someone else gains conditions to trigger the action.

**Moving the token from query to path does not solve the problem.** URL paths are still recorded by access logs and browser history. Avoid concluding "HTTPS protects tokens from logs": HTTPS only protects data in transit between endpoints, not endpoint/observability systems that see the plaintext request.

### Direct Mitigations

1. **Never log tokens** at any hop: proxy/CDN, ingress, WAF, app, APM, analytics. Configure access logs to record **route templates/paths without secrets** and strip/redact query strings on sensitive endpoints; audit retry/error logs too.
2. On responses containing recovery forms or context, set `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; consider strict CSP and `X-Robots-Tag: noindex, nofollow`. Never load third-party images/scripts/trackers on token-bearing pages.
3. **Do not use GET to consume tokens.** GET only renders a confirmation page or exchanges the token into a protected, scoped recovery session; the actual action executes via POST after user input/confirmation.
4. Once safe context is established, **redirect to a clean URL** or call `history.replaceState` early to drop the token from the current address bar/history entry. This reduces future leakage, though it **cannot erase requests/logs/synced history already recorded**.
5. Minimize TTL, bind purpose, enforce one-time consumption, and implement invalidation/revocation policies to shrink the exploitation window if leaked.
6. Never include tokens in `Referer`, analytics routes, event names, error titles, dashboard filters, or request IDs.

### Illustrative Headers for a Recovery Page

~~~http
HTTP/1.1 200 OK
Referrer-Policy: no-referrer
Cache-Control: no-store
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
X-Robots-Tag: noindex, nofollow
Content-Type: text/html; charset=UTF-8
~~~

Pick a realistic CSP matching your frontend; do not enable unchecked inline scripts merely to call `replaceState`. `Cache-Control: no-store` primarily prevents **response caching** and does not erase URLs from browser history or server logs. `Referrer-Policy` governs `Referer` on subsequent requests originating from the document, without removing tokens from the **initial request** to the server.

### Cleaning URLs with JavaScript (Architecture-Dependent)

~~~javascript
// Run only inside a trusted first-party recovery page.
// The raw token must already be captured into a safe recovery flow before cleaning the URL.
const url = new URL(window.location.href);
const token = url.searchParams.get("token");

if (token) {
    url.searchParams.delete("token");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    // Perform user action in a separate step; do not auto-consume on load.
}
~~~

This is a **browser-side snippet**, not a complete security configuration: the `token` variable still lives in memory, the page already sent the initial URL to the server, and any script running prior to this snippet could have read the token. Never let trackers/analytics run before URL sanitization; better yet, **do not put tokens anywhere they can run**.

A variant putting the token in a **URL fragment** (`#token=...`) keeps the fragment out of the HTTP request target sent to the server; trusted frontend code reads the fragment and submits the token via HTTPS POST. This still carries risks in the address bar, history, extensions, and JavaScript; it is not safe by default for every app and requires evaluating link scanners and mobile deep links. For simple flows, a server-side redirect to a clean URL combined with headers and log redaction is often easier to govern.

## 10. Avoiding Token Consumption on GET: Email Scanners and Link Previews

Email security gateways and mail clients can **visit URLs automatically** to check for phishing or render previews. If the server executes reset/verify/login directly on HTTP GET, bots can accidentally consume the token before the user ever sees the email.

**Incorrect** pattern:

~~~http
GET /account/recovery/open?token=...   -> mark used = true; change password
~~~

Recommended pattern:

~~~text
GET  /account/recovery/open?token=...
  -> return first-party page, do not change password/activate account
  -> no auto-POST, no auto-login
  -> no-referrer + no-store headers, no third-party content

User actively enters new password / clicks confirm
  |
  v
POST /account/recovery/complete
  -> appropriate CSRF/origin policy
  -> validate password + token purpose/TTL
  -> atomic consume + update password in transaction
  -> revoke old sessions/refresh tokens per policy
  -> 303 redirect to clean URL
~~~

For magic link login, you can exchange the token for a **scoped confirmation session** after requiring user interaction; avoid creating a full authenticated session just because a bot fetched GET. Every variant must define clearly **when privileges are granted** and handle link prefetching.

If using **manually entered codes** instead of URL tokens, users can open a secret-free form URL and type the code themselves. In return, short codes require strong attempt limits; never treat a 6-digit PIN as having the same security as a 256-bit secret.

## 11. Generating Recovery URLs Without Host Header Injection

In web apps, an often-overlooked flaw is constructing emailed links from network inputs:

~~~text
https://{request.getServerName()}/recovery/open?token=...
~~~

When proxies/header forwarding are misconfigured, attackers can manipulate `Host` or `X-Forwarded-Host`. The email carries a real token yet points to an attacker-controlled domain: the user clicks the link and sends the token to the attacker.

**Use a configured and controlled base URL**, such as `https://accounts.company.example`, or a strict allowlist by verified tenant. Never splice anonymous request-supplied hostnames into password-reset emails. Validate HTTPS and exact redirect URLs; never accept arbitrary `returnTo` parameters that turn the endpoint into an open redirect.

~~~java
// Illustrative snippet (Spring app or plain Java):
String resetBaseUrl = "https://accounts.company.example";
String link = resetBaseUrl + "/recovery/open?token="
    + java.net.URLEncoder.encode(
        token, java.nio.charset.StandardCharsets.UTF_8);
~~~

Optional `URLEncoder` uses form-style encoding; pure Base64url tokens are usually already URL-safe. Generate URLs solely from a **trusted configured origin**, never request headers. This snippet requires a system-issued `token` variable and is an **integration snippet**, not standalone. Emails must be sent via a controlled system, avoiding wrapping tokens in unnecessary template tracking URLs.

## 12. Spring Security: Structuring Request and Consume Endpoints

In Spring Boot 3.x/Spring Security 6.x (Servlet), the two main layers are:

- **Controller** receives form/recovery requests, returns consistent public responses, and delegates to services; never implement cryptography in controllers.
- **Application service** owns normalization, quotas, issuance, message queuing, token validation, password updates, transactional consumption, and auditing.
- **SecurityFilterChain** applies anonymous-access policies for public forms, while CSRF/cookie security, session handling, and security headers remain properly configured; **`permitAll()` does not automatically disable CSRF**.

Controller example **illustrating integration**, not a standalone `javac` program; requires Spring MVC and an application-implemented `RecoveryUseCases` interface:

~~~java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/account/recovery")
public class RecoveryController {
    private final RecoveryUseCases recovery;

    public RecoveryController(RecoveryUseCases recovery) {
        this.recovery = recovery;
    }

    @PostMapping("/request")
    public ResponseEntity<Map<String, String>> request(
            @RequestParam("email") String email) {
        // Normalize + apply quota to both existing and non-existent emails.
        // Queue work; do NOT send mail synchronously.
        recovery.acceptRequestWithoutLeakingAccountStatus(email);
        return ResponseEntity.accepted().body(Map.of(
            "message",
            "If the information matches an eligible account, "
              + "we will send instructions."));
    }

    @PostMapping("/complete")
    public ResponseEntity<Map<String, String>> complete(
            @RequestParam("token") String token,
            @RequestParam("newPassword") String newPassword) {
        // Service validates and commits consume + password update
        // inside the same transaction.
        if (!recovery.consumeAndResetPassword(token, newPassword)) {
            return ResponseEntity.badRequest().body(Map.of(
                "message", "Link is invalid or has expired."));
        }
        return ResponseEntity.ok(Map.of(
            "message", "Password updated."));
    }
}
~~~

~~~java
// Application contract to implement with DB, queue, rate limiter,
// password encoder, and transactions; not a runnable app.
public interface RecoveryUseCases {
    void acceptRequestWithoutLeakingAccountStatus(String email);
    boolean consumeAndResetPassword(String rawToken, String newPassword);
}
~~~

**What must be implemented before production:**

- `acceptRequestWithoutLeakingAccountStatus` validates input, normalizes identifiers **consistently with registration rules**, applies multi-dimensional quotas, safely stores the job or outbox, creates no mail when the account does not exist, and leaks no lookup result to the caller.
- `consumeAndResetPassword` validates token, purpose, expiry, used/revoked, password policy, resolves internal user, hashes password with an appropriate `PasswordEncoder` (e.g., Argon2id/bcrypt/scrypt per config), and **atomically consumes alongside the password update**. Never substitute plain SHA-256 for password hashing.
- If using sessions/cookies, preserve **CSRF protection** on POST forms and use proper CSRF tokens/Origin controls. Recovery tokens do not automatically replace all CSRF controls; never disable CSRF site-wide "to make the form work".
- For active sessions after a password reset, decide to invalidate old sessions, refresh tokens, and remember-me tokens. Revocation must be explicitly implemented; do not assume Spring Security automatically revokes all sessions across all devices.
- If tokens appear in request bodies, redact bodies/exception logs. If tokens appear in GET URLs, also redact queries at gateways, proxies, and apps; **controllers cannot control logs written upstream**.
- APIs may return HTTP 400 for invalid/expired tokens, yet must avoid leaking accounts or publicly distinguishing "user X's token" from "user Y's token".

### A Minimal SecurityFilterChain Configuration to Understand Scope

~~~java
// Spring Security 6.x, integration snippet:
// request/complete endpoints must allow anonymous access,
// while default web form CSRF remains active.
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/recovery/**").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

This example is **incomplete** as a full app: you still need `@Bean` wiring, CSRF token exposure to forms, GET URLs, login for other routes, the recovery service, response headers, password policies, and persistent storage. Do not copy it and accidentally replace an existing chain config. Spring Security supports CSP/Referrer-Policy/cache headers; proxies/CDNs/analytics must still be configured separately, not just the filter chain.

## 13. Should Expiration Time and "Sent" Status Be Shown?

You can publish a generic sentence such as "If an eligible account exists, check your email in a few minutes" and the token validity window (e.g., 15 minutes per policy). Do not:

- Display a **partially masked recovery address** only when the account exists, such as `l***@company.example`, before the user proves account ownership.
- State "email pending", "sent at 10:32", "3rd send attempt", or "account unverified" on a public endpoint if it differs by account status.
- Expose a public `GET /request-status?email=...` endpoint distinguishing job success/failure per user.
- Return different `Retry-After` values based on whether a real account has quota while an unknown account does not; enforce quotas uniformly per identifier regardless of lookup.
- Include internal codes like `USER_NOT_FOUND` or `LOCKED_ACCOUNT` in JSON responses and merely hide the message in the frontend.

For **already logged-in** users who passed strong authentication, specific email/2FA management status can be shown per policy. The account-enumeration problem here mainly applies to **anonymous recovery endpoints**, where the caller has not been authorized to view account details.

### Resends and Multiple Outstanding Tokens

Two common policies:

1. **Keep one active token for a short period and ignore rapid resends:** reduces email flooding, though raw tokens cannot be re-sent if the server only stores hashes. Do not try to "recover" the secret. You can keep an upcoming delivery job in a secure queue under controlled windows or ask the user to wait and issue a fresh token after cooldown.
2. **Issue a new token and allow a bounded number to coexist:** helps with delayed/out-of-order emails, requiring caps on active tokens and expiry plus proper revocation once the action completes. If new tokens revoke old ones, anonymous attackers can cause DoS via reset spam.

Either policy requires rate limits, cooldowns, and generic messages. After a successful password change, invalidate **related password-reset tokens for that account** per policy so old links stop working; handle races with appropriate transactions/locking.

## 14. Handling Email/SMS Delivery Without Leaking Tokens

Tokens usually pass through mailers/SMS providers, yet systems can still minimize exposure:

- Only send to **linked addresses verified per policy**; never let anonymous callers swap `sendTo` to steal another user's token.
- Email templates carry the exact domain/origin, branding, and a reminder not to share links. Omit passwords and unnecessary sensitive account details.
- If using email marketing open/click tracking, **disable link rewriting/tracking redirects for reset links**. An intermediary tracking domain would receive the full token.
- Account for email previews/security scanners: if a bot GETs the link, no action should execute.
- Queues need encryption and ACLs per threat model, short retention, and no dumping of email payloads to debug logs; raw token copies in retry queues/DLQs are also secrets.
- If emails bounce, hit suppression lists, or SMS providers fail, never leak account existence via public endpoints; monitor internally per policy.
- Handle delivery errors at the worker level with backoff and bounded retries to avoid spam; avoid resending multiple secrets or vaguely reusing an expired token.

**Email is not guaranteed to be a strong enough sole factor** for admin/financial accounts. MFA, trusted devices, extra verification steps, or audited manual support may be necessary. If resetting a password also wipes MFA, build a separate higher-assurance flow.

## 15. Distinguishing HTTP, Browser, and Logging Controls

A secure design inspects **every leak surface**, rather than adding one header and calling it done.

| Surface | Risk | Corresponding Control |
|---|---|---|
| Email/SMS | Others accessing mailbox, mail forwarding, link tracking. | Short TTL, recipient policy, no tracking URLs, MFA/risk policy. |
| Link opened in browser | History/address bar/clipboard/extensions. | One-time TTL, clean URL redirect, optionally fragment/POST flow where suitable. |
| CDN/WAF/reverse proxy | Access logs capture full request URI/query. | Redact tokens/queries by route at **every hop**; control log ACLs/retention. |
| Spring MVC/HTTP server | Request dumps, debug logs, exceptions contain tokens. | Structured logging allowlisting fields; never log sensitive bodies/headers/queries. |
| Frontend SPA | Analytics, session replay, third-party scripts read URL. | First-party-only recovery page, CSP, analytics exclusion, early URL cleanup. |
| Browser Referer | Path/params leak on fetches/navigations. | `Referrer-Policy: no-referrer`, zero third-party resources. |
| Browser/proxy cache | Caches pages with sensitive data. | `Cache-Control: no-store` on recovery forms/sensitive responses. |
| DB, queue, backups | Plaintext tokens remain in copies. | Store one-way verifiers; queue retention/ACL/encryption; scrub backups/logs per policy. |
| Audit/support | Operators see raw tokens in tickets. | Log request IDs/credential metadata, never raw secrets. |

**You cannot "wipe all traces" using `history.replaceState` alone.** It only alters the current browser's history entry; it does not recall URLs already sent to proxies, mail services, extensions, or screenshots. Defense-in-depth and short lifetimes are essential.

### What Should Safe Logs Look Like?

Instead of:

~~~text
GET /account/recovery/open?token=Vn...full-token... 200 145ms
~~~

Log:

~~~json
{
  "event": "recovery_page_view",
  "route": "/account/recovery/open",
  "requestId": "req-b793",
  "result": "rendered",
  "durationMs": 145
}
~~~

If token correlation is needed for investigations, log a **dedicated random non-authenticating ID** or a keyed HMAC/truncated token fingerprint using a separate tracking key and retention policy after a privacy review. **Never log raw tokens or full verifier values**. Pseudonymize emails/usernames as well when sufficient for operations.

A log showing only HTTP codes does not prove tokens are unleaked: inspect the log pipeline from **ingress through APM, frontend monitoring, backups, and DLQs**. Security reviews should run automated log-redaction tests with a synthetic canary token, never a real user's token.

## 16. Illustrative Scenario: Enterprise Sending Password Reset Links

Suppose an HR system has account `lan@company.example`. An attacker tries to enumerate accounts and flood requests:

### Scenario A — Attacker Probes an Email List

~~~text
POST /account/recovery/request email=lan@company.example
POST /account/recovery/request email=nobody@company.example
~~~

Both syntactically valid requests must yield equivalent public responses. Identifier quotas must count against both addresses; the worker only emails eligible real accounts. There is no `/recovery/status` URL letting the attacker see whether a mail job was created.

### Scenario B — Attacker Spams One Person Across Hundreds of IPs

IP-only rate limiting fails. The system limits by normalized identifier, IP/network, tenant, and global queue. Exceeding quota only **pauses/throttles token issuance** or triggers a challenge, without locking Lan's account or changing her password. Monitoring records the spike without storing plaintext emails unnecessarily.

### Scenario C — Lan Receives Email, but an Email Scanner Opens the Link First

GET only renders/performs minimal checks **without consuming** the token. Lan opens the link, enters a new password, and submits POST; the transaction consumes it exactly once. If the scanner hits GET multiple times, the token is not invalidated by link previews. If two POSTs race, only one succeeds.

### Scenario D — Reverse Proxy Accidentally Logs Tokens in Query Logs

Even when the DB stores only hashes, a proxy can still log full secret-bearing URLs. Fix the access-log template/redaction; audit retention/access to exposed logs and **revoke potentially exposed tokens** per incident response. `Cache-Control: no-store` does not fix proxy logs.

### Scenario E — User Clicks "Resend" Repeatedly

The system enforces a cooldown and generic message rather than minting unlimited new tokens. If the backend issues new tokens, it must handle out-of-order emails so users are not stranded; if it keeps one active token, it cannot read the raw token back from a DB hash to resend it. Resend design must reflect that reality.

### Scenario F — Password Successfully Changed

After a successful POST, the token is consumed, older reset tokens are invalidated per policy, old sessions/refresh tokens are handled per policy, and auditing logs the event without credentials. Send a security notification to the registered notification channel (without any token) and redirect the browser to a clean URL.

## 17. Test Suite Covering All Three Risks

| Group | Test Case | Expected Result |
|---|---|---|
| Enumeration | Email with account vs. without account. | Consistent public HTTP code/body/redirect/headers. |
| Enumeration | Active account vs. unverified disabled account. | No status leaked via anonymous endpoints. |
| Enumeration | Multi-sample timing analysis. | No clear systematic skew from synchronous SMTP/lookup branches. |
| Enumeration | Rate limit with non-existent identifier. | Does not bypass quotas or differ publicly from real accounts. |
| Quota | Same identifier, multiple IPs. | Identifier limiter still takes effect. |
| Quota | Shared NAT IP, many legitimate users. | Policy avoids over-blocking, with fallbacks/monitoring. |
| Quota | Multiple parallel instances. | Atomic quota counting in a shared store. |
| Quota | Attacker clicks resend repeatedly. | No mailbox flooding, no self-lockout, consistent token policy. |
| Token | Secret generated with CSPRNG. | Sufficient entropy and format; not derived from timestamp/email. |
| Token | Wrong purpose check. | `VERIFY_EMAIL` token cannot reset a password. |
| Token | After expiration. | Rejected even if DB cleanup has not run. |
| Token | Concurrent double-submit. | Only one transaction consumes and applies the business action. |
| Token | Password reset transaction fails. | Consumed token rolls back; no partial state. |
| Token | Already used, resubmitted verbatim. | Rejected (replay). |
| Token | Repeated wrong PIN entries. | Attempt limit blocks online guessing. |
| Browser | GET URL from email scanner. | Does not change password, log in, or consume on GET. |
| Browser | Recovery page loads third-party resources. | No tracking; CSP/referrer policy blocks URL leaks. |
| Browser | Flow completes. | Redirect/`replaceState` to clean URL; no secret left in app URL. |
| Logs | Request URL carries a canary token. | Token absent from proxy/CDN/APM/exception/server logs. |
| Cache | Recovery response. | Has `Cache-Control: no-store`; no accidental sensitive caching. |
| Phishing | Spoofed Host or forwarded host. | Reset link uses allowed origin; never points token to unknown domain. |
| Email | Link tracking rewrite. | Token never passes through third-party URLs. |
| Privacy | Analytics and session replay. | Never records tokens, password bodies, or unnecessary emails. |
| Lifecycle | Account already reset. | Invalidates sessions/tokens per policy and sends security notification. |
| Infrastructure | SMTP/queue/store failure. | Fails closed, never floods tokens or leaks account status. |

**Do not test only endpoint HTTP status codes.** Include integration tests spanning limiters, DB transactions, mailers, Spring Security filters, gateway logging, and browser/headless runs to catch leaks invisible to Java unit tests. Log-leakage tests should use synthetic tokens in controlled environments, never sending real emails to outsiders.

## 18. Pre-Release Deployment Checklist

### Request Endpoint Design

- [ ] Anonymous requests return the same public message, schema, and status for existing/non-existent identifiers.
- [ ] Input normalization matches registration rules; never guess email rules like stripping dots/`+tag` across all domains.
- [ ] No synchronous email/SMS on the public response path; avoid easily observable timing divergence.
- [ ] Rate limit by IP, normalized identifier (including non-existent accounts), tenant, and global using an atomic distributed store.
- [ ] Never lock accounts merely for receiving excessive recovery requests; add monitoring/challenges on abuse.
- [ ] Expose no public status/email-existence endpoint.

### Token and Consumption Design

- [ ] High-entropy CSPRNG, unguessable secret; store hash/HMAC instead of plaintext when only matching is needed.
- [ ] Bind token to user, purpose, expiry, state, and context; never reuse across reset/verify/invite.
- [ ] Check expiry/revoked/consumed at consumption time, not only on GET render.
- [ ] Business change and mark-used happen in the same database transaction, safe under concurrent requests.
- [ ] Only POST (or an intentional equivalent) causes side effects; GET never consumes tokens due to link scanners.
- [ ] On success, revoke tokens/sessions per policy so old links cannot be reused.

### HTTP, Browser, and Operations Design

- [ ] HTTPS and fixed/allowlisted reset URL origin, never read from client Host headers.
- [ ] `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, strict CSP on recovery pages; no third-party scripts/trackers.
- [ ] Log redaction at CDN/WAF/reverse proxy/app/APM/queue, not solely in controllers.
- [ ] Consider clean URLs/redirects/`history.replaceState`, while recognizing their limits against already-recorded logs/history.
- [ ] Form POSTs and sessions/cookies have proper CSRF/origin controls; never disable CSRF site-wide.
- [ ] Emails do not rewrite links through tracking domains and never expose raw tokens in analytics/support.
- [ ] Tests cover concurrency, replay, rate limits, false positives, timing, and log canaries.
- [ ] Incident response procedure exists: detecting token leaks, revoking, cleanup, rotation, and auditing leak channels.

## 19. Conclusion

The three protective layers for one-time tokens must operate **together**:

1. **Anti-enumeration:** request endpoints reveal nothing about account existence/status via status, body, redirects, timing, or quotas.
2. **Anti-delivery-abuse:** multi-dimensional limits, distinguishing request quotas from verify attempts, protecting mailbox/SMS providers, and never turning reset spam into account lockouts.
3. **Anti-token-leak:** CSPRNG + TTL + atomic one-time consumption, storing verifiers instead of plaintext, keeping tokens out of logs/Referer/analytics/cache/history as far as controllable, side-effect-free GETs, and clean post-flow URLs.

**Key takeaway:** a cryptographically strong token is no longer safe if written into human-readable logs, and a generic endpoint no longer blocks enumeration if timing/quotas reveal account existence. Designs must be measured and tested **from proxy to database, from mailer to browser**, not merely by inspecting controller code.

## References

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): generic responses, timing, account abuse, secure reset tokens, URLs, and Referrer-Policy.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account enumeration via messages and timing.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing (distinct from random token hashing).
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle and revocation.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data that must not be logged.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): controlling `Referer` sent by browsers.
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): caching and the `no-store` directive.
- [MDN — History.replaceState](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState): replacing the current history entry's URL.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF on state-changing requests.
- [Spring Security — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): security headers and policies.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generating high-entropy secrets.
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key operations in single-JVM simulations.
