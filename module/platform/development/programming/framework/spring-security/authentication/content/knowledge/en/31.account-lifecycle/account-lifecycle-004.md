# Requesting Password Resets Without Revealing Account Existence

The **Forgot Password** feature exposes a public form where users enter an email address or username. It is also a prime location for **account enumeration**: an attacker submits many addresses and infers which accounts are registered from HTTP status codes, messages, response times, or secondary clues.

The goal of the **password reset request** step is: **anyone who has not proven account ownership must not be able to tell via the public endpoint whether a valid identifier exists, is locked, uses SSO, or is eligible for password recovery**. The system can still send instructions to the verified contact channel of an eligible account, without reflecting lookup or mail-sending outcomes in the HTTP response.

This lesson separates anti-enumeration from the full reset-token lifecycle, focusing on uniform responses, avoiding timing side-channels, asynchronous internal processing, rate limiting, Spring Security Servlet, illustrative Java 17+ code, and security testing.

## 1. How Does Account Enumeration Happen?

Suppose a client sends:

~~~http
POST /auth/password-reset-requests HTTP/1.1
Content-Type: application/json

{"identifier":"lan@example.org"}
~~~

An insecure implementation returns:

~~~text
lan@example.org       -> 200 "Password reset email sent"
nobody@example.org    -> 404 "Account not found"
locked@example.org    -> 403 "Account is locked"
sso-only@example.org  -> 409 "Account uses SSO"
~~~

These messages let strangers probe which users belong to the system. Combined with leaked email lists, attackers can target phishing, credential stuffing, social engineering, or organizational reconnaissance.

A more secure response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{"message":"If an eligible matching account exists, instructions will be sent through the registered contact method."}
~~~

For any syntactically valid request, return the **same status code, body, schema, headers, and redirect behavior** regardless of whether the account exists. `202 Accepted` means the request was **accepted for processing**, not that an email was guaranteed to be sent. Returning `200 OK` with a uniform response is also a valid option.

Neutral wording must never state “an email has been sent” as an unconditional fact for every input, and must never pass a client-visible flag such as `accountExists`.

## 2. Channels That Can Leak Account Existence

You cannot prevent enumeration merely by changing one message string. Examine every observable channel:

| Channel | How it leaks | Defense |
| --- | --- | --- |
| HTTP status | Existing returns 200, missing returns 404 | Same status for all valid inputs |
| Body / JSON | `accountExists`, `mailSent`, differing text | Identical schema/message, no internal flags |
| Redirect | Real users redirected to a different page | Same `Location` and navigation rules |
| Headers/cookies | Differing `Set-Cookie`, `Retry-After`, or `Cache-Control` | Uniform HTTP envelope |
| Response length | Showing a masked email for existing accounts | Never expose contact data |
| Latency | Existing users send SMTP synchronously; missing ones return instantly | Decouple lookup/send from the HTTP path |
| Rate limiting | Only real users get throttled per account | Enforce limits for both known and unknown identifiers |
| CAPTCHA | Triggered only if the email is registered | Trigger based on abuse signals, not existence |
| Resend/status page | Reveals whether an email was queued/sent | Never expose send status publicly |
| Login/registration APIs | Different errors per account state | Use generic errors per policy |
| Side effects | Reset request locks the real account | Never mutate account state before token verification |

Even when both responses have identical bodies, if an existing account takes 400 ms to send via SMTP while an unknown account returns in 10 ms, an attacker can repeat requests and classify accounts statistically.

**The goal is not making every HTTP request take the exact same number of microseconds.** The goal is eliminating reliable, large-scale exploitable differences; test latency distributions under realistic load.

## 3. Recommended Architecture: Accept the Request First, Look Up the User Later

An easier-to-defend design uses **uniform HTTP intake** followed by an **internal worker**:

~~~text
Client / Browser
     |
     | POST identifier
     v
Reset Request Controller
     | Validate syntax/size
     | Throttle by input/source, no user lookup
     | Enqueue a reset-intent for every valid identifier
     v
  202 + generic response
     :
     : Separate processing queue
     v
Reset Worker
     | Lookup account in identity store
     | Absent / ineligible -> do not send
     | Eligible account -> generate token/TTL
     | Send to verified recovery address
     v
Internal audit / metric, not exposed in public response
~~~

**All syntactically valid identifiers must traverse the exact same HTTP path.** The controller never waits to learn whether email dispatch succeeded before responding. The worker has visibility into account state, but its results stay internal.

If the queue itself fails, the system may return a shared temporary error such as 503 for all affected requests rather than pretending the request was queued. Distinguish **queue failure** from **missing account** in internal telemetry, never in public responses.

### Anti-Example: Same Text, Different Timing

~~~java
// Wrong: look up account and send email synchronously.
var account = users.findByEmail(email);
if (account.isPresent()) {
    mailer.sendResetInstructions(account.get());
}
return "If a matching account exists, instructions will be sent.";
~~~

The body is identical, yet the existing-account branch pays mail-sending latency. A similar mistake—calling `future.join()` to wait for email dispatch—carries the same risk. The primary fix is **neither querying the account nor waiting on SMTP on the request path**.

Adding a fixed `Thread.sleep(500)` is insufficient: mail providers sometimes take longer than the sleep, leaking the difference, and sleeping wastes server threads. Random padding, if used at all, is only supplementary after removing branching behavior.

## 4. Syntax Validation Must Not Become an Account Lookup

You may reject malformed payloads:

- Invalid JSON or missing required fields;
- Blank, oversized, or syntactically invalid identifiers per documented rules;
- Requests exceeding payload size limits;
- Abuse detected by IP, device/session, or other signals.

However, **syntactically valid identifiers** must receive the exact same generic response regardless of database presence.

| Input | Assessment | HTTP behavior |
| --- | --- | --- |
| `lan@example.org` | Valid format, account may exist | Generic 202 |
| `unknown@example.org` | Valid format, account may not exist | Generic 202 |
| `disabled@example.org` | Locked/disabled account | Generic 202 |
| `sso@example.org` | SSO-only account | Generic 202 |
| JSON missing a brace | Malformed syntax | May return 400 |
| Multi-MB string | Exceeds general limit | May return 413 or 400 |

Never return `404 Not Found` to say an email is unregistered. Never display a partially masked recovery email (such as `l***@example.org`) before the user proves ownership of the account.

**Identifier canonicalization** must match the identity store: handle Unicode, whitespace, and system username/email conventions consistently. Never apply Gmail-specific dot/plus-tag stripping across all providers, as that can merge two distinct addresses into one account. Incorrect canonicalization also breaks rate limiting or sends instructions to the wrong user.

## 5. Uniform HTTP Responses Without Sensitive Reflection

A clean public contract:

~~~json
{
  "message": "If an eligible matching account exists, instructions will be sent through the registered contact method."
}
~~~

Fields that must NOT appear in an unauthenticated response:

~~~json
{
  "accountExists": true,
  "accountType": "LOCAL_PASSWORD",
  "maskedEmail": "l***@example.org",
  "resetTokenGenerated": true,
  "mailDeliveryStatus": "QUEUED"
}
~~~

Avoid reflecting the submitted email back in the response unless necessary, especially without proper HTML escaping (XSS risk). Any request ID or correlation ID must be independent of lookup outcomes and must not feed a public “check email progress” API.

Also check HTTP headers and routing:

- Identical HTTP status for known, unknown, and disabled accounts when syntax is valid.
- `Content-Type`, `Cache-Control`, `Location`, `Set-Cookie`, and body schema do not vary by account.
- Never return dedicated endpoints or paths exclusively for SSO-only users.
- Never auto-redirect based on an email domain or tenant found in the database.
- Never embed hidden variables in HTML/JavaScript revealing existence.
- Never output debug exception stack traces exposing account status.

In SPAs, frontend messages must also remain uniform across retries, navigation, and page reloads.

## 6. Rate Limiting: Preventing Both Enumeration and Email Flooding

Even an endpoint returning a single generic message can be abused without rate limits to probe millions of emails or flood a victim's inbox with reset emails.

Combine rate limits across dimensions:

| Dimension | Purpose |
| --- | --- |
| IP / network range | Curb source-based automation |
| Normalized identifier | Prevent bombarding a single mailbox |
| Session / browser flow | Block rapid repeated submissions by users/bots |
| Trusted tenant | Protect an organization's quota |
| Global system throughput | Protect queues, mailers, and databases from overload |
| Actual emails sent | Cap cost and email bombing inside the worker |

**Per-identifier quotas must apply equally to existing and non-existent emails.** If registered addresses hit 429 after a few tries while unknown ones keep returning 202, the rate limiter itself becomes an enumeration oracle.

When storing identifiers as Redis rate-limit keys, protect them using something like an **HMAC of the normalized identifier with a server-side key**, avoiding plaintext emails in logs and metrics. Keep normalization identical across lookup and throttling.

CAPTCHA or progressive challenges may trigger on automation signals, never on account existence. Nor should reset requests lock the account against login: an attacker must not be able to lock a victim out merely by submitting their email.

**Availability tradeoff:** an overly strict per-email cap lets an attacker block a victim from resetting their own password. Design cooldowns, bot defenses, reliable support paths, quotas, and metrics around your threat model rather than picking one rigid threshold for every service.

## 7. Worker Sends Only to Verified Recovery Addresses

Inside the worker, an internal flow can look like:

~~~text
consume ResetIntent
  |
  +-- lookup normalized identifier
  |
  +-- account does not exist -> finish internally
  |
  +-- account ineligible for local reset -> finish or handle per policy
  |
  +-- fetch account's verifiedRecoveryContact
  |
  +-- generate random token, bind accountId + purpose + TTL
  |
  +-- store token verifier, single-use state
  |
  +-- send link to verifiedRecoveryContact via mail service
  |
  +-- internal audit without exposing in HTTP response
~~~

Never send a reset link to a `destinationEmail` supplied by the requester unless it is already the verified address bound to the account under policy. Unauthenticated callers can supply any email; letting them pick the destination is an account takeover vulnerability.

Special cases:

| Account state | Worker behavior |
| --- | --- |
| Local-password account + verified email | May issue token and send to verified email |
| Non-existent identifier | Do not send, do not disclose |
| Disabled/locked account | Do not auto-unlock; follow recovery policy |
| SSO/OIDC/SAML-only | Do not create a local password against policy; optionally send separate guidance over verified channel |
| No verified recovery contact | Never send token to an unverified contact |
| Unactivated invited account | Never auto-activate an account via a reset request |
| Multiple accounts sharing identifier | Never pick randomly; enforce identity-ambiguity policy |

Regardless of which branch the worker takes, the public HTTP response **has already completed** and leaks none of it.

The queue holds PII: restrict read access, bound retention, encrypt if required, keep identifiers and raw tokens out of logs, protect dead-letter queues, and avoid infinite email-sending retries.

## 8. Java 17+: Simulating Identical Responses for Known and Unknown Accounts

The following program simulates HTTP intake and a worker within **one JVM**, using an internal queue to prove both requests take the same intake path. **There is no HTTP server, real email, or real token**; it demonstrates only “do not look up the account before returning the generic response.”

Create file **ResetRequestDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Queue;
import java.util.Set;

public class ResetRequestDemo {
    private static final String GENERIC =
            "If an account is eligible, reset instructions will be sent.";

    record Intent(String identifier) {}

    private final Queue<Intent> pending = new ArrayDeque<>();
    private final Set<String> accounts =
            new HashSet<>(Set.of("lan@example.org"));

    String requestReset(String identifier) {
        if (identifier == null || identifier.isBlank()) {
            throw new IllegalArgumentException("Invalid input format");
        }
        pending.add(new Intent(identifier));
        return GENERIC;
    }

    void runWorker() {
        while (!pending.isEmpty()) {
            Intent intent = pending.remove();
            if (accounts.contains(intent.identifier())) {
                // Production worker would issue a one-time reset token
                // and send it to the account's verified recovery address.
            }
        }
    }

    int pendingCount() {
        return pending.size();
    }

    public static void main(String[] args) {
        ResetRequestDemo service = new ResetRequestDemo();

        String first = service.requestReset("lan@example.org");
        String second = service.requestReset("unknown@example.org");

        System.out.println("Response A = " + first);
        System.out.println("Response B = " + second);
        System.out.println("Responses equal = " + first.equals(second));
        System.out.println("Queued intents = " + service.pendingCount());

        service.runWorker();
        System.out.println("Queue empty = " + (service.pendingCount() == 0));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ResetRequestDemo.java
java ResetRequestDemo
~~~

Exact stdout:

~~~text
Response A = If an account is eligible, reset instructions will be sent.
Response B = If an account is eligible, reset instructions will be sent.
Responses equal = true
Queued intents = 2
Queue empty = true
~~~

Analysis:

- Request intake performs no account lookup; it simply enqueues both valid identifiers.
- Identical messages are returned for both.
- The worker checks account existence afterward; no `mailSent` status goes back to the caller.
- `ArrayDeque` is neither thread-safe nor distributed; **never use this queue in production**.
- The program does not prove uniform HTTP latency, CAPTCHA/rate limiting, email delivery, token cryptography, or Spring security. It is a lab illustrating the architectural boundary.

## 9. Applying This with Spring Security Servlet

Spring Security provides the filter chain, authorization checks, CSRF protection, and `PasswordEncoder`, while the application must build the forgot-password request flow, queue, worker, mailer, and reset token store.

Spring Boot Servlet Java 17+ controller example:

~~~java
package demo.security.reset;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/auth")
public class PasswordResetRequestController {
    private static final String GENERIC_MESSAGE =
            "If an eligible matching account exists, "
            + "instructions will be sent through the registered contact method.";

    public interface ResetIntake {
        void enqueue(String identifier);
    }

    public record Request(String identifier) {}

    private final ResetIntake intake;

    public PasswordResetRequestController(ResetIntake intake) {
        this.intake = intake;
    }

    @PostMapping("/password-reset-requests")
    public ResponseEntity<Map<String, String>> requestReset(
            @RequestBody Request request) {

        if (request == null || request.identifier() == null
                || request.identifier().isBlank()
                || request.identifier().length() > 254) {
            return ResponseEntity.badRequest().body(
                    Map.of("message", "Invalid request data."));
        }

        // Intake normalizes, runs anti-abuse checks, and enqueues along one path
        // independent of whether the identifier has an account.
        intake.enqueue(request.identifier());

        return ResponseEntity.accepted().body(
                Map.of("message", GENERIC_MESSAGE));
    }
}
~~~

This is a structurally valid Spring class, **not a standalone app runnable with `javac`**. It needs Spring Boot, Spring Web/Security, and a bean implementing `ResetIntake`. That implementation must validate/canonicalize input, throttle independently of existence, enqueue uniformly, and fail closed on queue failures. Never implement `ResetIntake` with a synchronous `findByEmail()` followed by SMTP delivery, as that reintroduces a timing oracle.

HTTP authorization configuration snippet:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                org.springframework.http.HttpMethod.POST,
                "/auth/password-reset-requests").permitAll()
        .anyRequest().authenticated());
~~~

This is a **DSL fragment inside `SecurityFilterChain`**. `permitAll()` only means anonymous callers are not required to be logged in; it **does not disable CSRF or abuse protection**. For session/cookie browser forms, include CSRF tokens as required by Spring Security. If designing a sessionless reset API, evaluate CSRF/cross-origin risks and mail-bombing defenses per your threat model; never disable CSRF application-wide indiscriminately.

**Note on 400:** the example returns 400 for blank input or length >254, never because an account does not exist. If the login identifier can be a username rather than an email, adjust length bounds and validation rules to fit actual policy.

## 10. Reset Tokens Are Narrow-Purpose Credentials

A generic request response is not secure enough if reset links are guessable or reusable. Once the worker finds an eligible account, the token must be:

1. Generated from a CSPRNG (e.g., 32 random bytes).
2. Bound to **`userId`**, purpose `PASSWORD_RESET`, and an expiration time.
3. Stored as a secure verifier, such as a SHA-256 digest or HMAC of a high-entropy token.
4. **Single-use**, consumed atomically to prevent races and replays.
5. Enforced by a server-side TTL (for example, 20 minutes as an illustrative policy).
6. Protected against brute force and revocable when needed.
7. Never allowed to create a login session or change the password upon issuance alone.

Illustrative PostgreSQL table:

~~~sql
CREATE TABLE password_reset_token (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    token_digest BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
~~~

When the user submits the token to set a new password, verify the digest, expiry, unused state, account policy, and password policy; mark consumed and update the password hash in one consistent transaction. Two concurrent requests must never both succeed with the same token.

Java generator (utility snippet, without persistence):

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class ResetTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String create() {
        byte[] raw = new byte[32];
        RANDOM.nextBytes(raw);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);
    }
}
~~~

A 32-byte random token encoded as unpadded Base64URL has 43 characters. Never log raw tokens, and never put them into monitoring or exceptions.

**`PasswordEncoder` differs from token hashing:** human-chosen passwords have low entropy and need slow salted/cost-tuned hashing (e.g., algorithms configured via `DelegatingPasswordEncoder`). A 256-bit random reset token can store its verifier using a fast cryptographic digest under proper controls. Never store plaintext passwords.

## 11. Recovery Links: Avoiding Host Header Injection and Token Leakage

Never construct links using a host supplied by a public request:

~~~java
// Wrong: attacker can manipulate the Host header.
String link = "https://" + request.getHeader("Host")
        + "/reset-password?token=" + token;
~~~

If an attacker controls the `Host` header, a real account's recovery email could point the user to an attacker-controlled site and leak the token. Instead, use a **trusted configured public base URL**, such as `https://accounts.example.org`, approved for that deployment environment.

Related safeguards:

- Serve the reset page over HTTPS only;
- Set `Referrer-Policy: no-referrer` on pages carrying the token;
- Do not load analytics or third-party scripts that could read the token;
- Configure reverse proxies and access logs not to record query tokens;
- Never let the requester supply arbitrary callback/redirect URLs;
- Send only to the account's verified recovery contact;
- Optionally transition into a scoped recovery session after verifying the token to keep the token out of the URL.

**Never change the password during the link's GET request**. GET should render a form or start the verification flow; password mutation must occur only after an explicit action validating the token and new password.

After a successful password change, revoke old sessions/refresh tokens per policy, send a security notification, and require normal login. **Never auto-login just because a reset token was redeemed**; the token's sole purpose is updating the password.

## 12. Special Account States

| State | What the worker should do | Public response |
| --- | --- | --- |
| Local-password account with verified recovery contact | May send link | Generic 202 |
| Account does not exist | Do not send | Generic 202 |
| Locked/disabled account | Do not auto-unlock; follow recovery policy | Generic 202 |
| SSO/OIDC/SAML-only | Do not create local password; send internal guidance if needed | Generic 202 |
| Unverified recovery email | Do not send link to unverified email | Generic 202 |
| Unactivated account | Do not auto-activate on request | Generic 202 |
| Non-unique username/email | Do not arbitrarily pick an account | Generic 202 |

Never lock an account because an unauthenticated caller submitted a reset request. Never rely on request input to choose which account gets emailed if multiple records share an identifier.

The account owner may need notifications about completed resets or recovery activity per policy, but those notifications go over a separate verified channel, never as the public result of the request.

## 13. Indirect Leak Points Often Overlooked

Even a system with a generic forgot-password response can leak existence through:

- A registration page returning “email already exists”;
- Login returning “user does not exist” differently from “wrong password”;
- A resend endpoint returning “no pending reset”;
- A public “check password reset status” page;
- CAPTCHA appearing only for real accounts;
- Per-account rate limits tracked only for real users;
- Differing `Retry-After` headers, response sizes, or cookies;
- Mail bounces/rejections reflected synchronously in HTTP responses;
- Logs/traces/debug output leaking `foundUser=true`;
- Filenames or redirect URLs branching by identity provider.

Audit the **entire authentication, registration, and recovery lifecycle**, not just a single route.

## 14. Testing: Status, Body, Timing, and Side Effects

| Test case | Expected result |
| --- | --- |
| Valid existing email | Generic 202 |
| Non-existent email with valid format | Identical status/body/headers |
| Disabled/locked account | Identical response, no auto-unlock |
| SSO-only account | Identical response, no local password created |
| Unverified recovery email | Identical response, no link sent to unverified contact |
| Invalid JSON or oversized payload | Generic format error, independent of account |
| Rate-limiting known vs unknown identifier | Identical throttling rules |
| Slow SMTP provider | Does not slow down known-account responses selectively |
| Queue outage | Generic infrastructure error, no account oracle |
| 100 requests for same email | Does not send 100 emails indefinitely; quota/dedup applies |
| Reset request | Does not alter password, sessions, or account status |
| Invalid, expired, or used token | Cannot change password |
| Two concurrent requests with same token | At most one consume succeeds |
| Malicious `Host` header | Link still uses trusted base URL |
| Token in query/referrer/logs | Prevented or redacted |
| Resend/status API | Does not reveal account existence |
| Known/unknown latency distribution | No reliable statistical oracle |

### MockMvc: Comparing Two Cases

Spring Boot Servlet test snippet with `MockMvc` and a stub `ResetIntake`:

~~~java
var a = mockMvc.perform(post("/auth/password-reset-requests")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"identifier\":\"lan@example.org\"}")
        .with(csrf()))
        .andReturn().getResponse();

var b = mockMvc.perform(post("/auth/password-reset-requests")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"identifier\":\"unknown@example.org\"}")
        .with(csrf()))
        .andReturn().getResponse();

assertEquals(202, a.getStatus());
assertEquals(a.getStatus(), b.getStatus());
assertEquals(a.getContentAsString(), b.getContentAsString());
~~~

This is a **test snippet**, not standalone runnable with `javac`; it needs MockMvc setup and JUnit/Spring Security test static imports. A complete test also compares headers, verifies the worker queue received both intents, and confirms no account lookup happened on the HTTP request thread.

To measure timing, send interleaved known/unknown/disabled requests after JIT and cache warm-up, recording latency histograms, medians, and p95 under varied loads—including slow SMTP/queues. Do not draw conclusions from just a few manual requests.

## 15. Pre-Deployment Checklist

1. Do responses for existing, non-existent, locked, and SSO-only accounts share **identical status/body/headers/redirects**?
2. Does HTTP intake avoid synchronous account lookups and synchronous SMTP calls?
3. Do all valid identifiers enter the same queue/pipeline before the worker decides whether to send mail?
4. Is throttling by IP and normalized identifier applied to **both known and unknown** identifiers?
5. Are differing CAPTCHAs, `Retry-After` headers, or errors avoided for existing accounts?
6. Are queue PII, worker retries, quotas, and infrastructure errors properly protected?
7. Are links sent only to verified account contacts, never to stranger-supplied destinations?
8. Do reset tokens have random entropy, TTL, single-use, account/purpose binding, and rate limits?
9. Do reset URLs use a trusted base host, HTTPS, `no-referrer`, and token redaction?
10. Are passwords/sessions updated only after verifying both the token and policies?
11. Is an appropriate `PasswordEncoder` used alongside post-completion security notifications?
12. Are latency, response envelopes, sibling endpoints, and abuse/DoS cases tested?

**Conclusion:** “Not revealing account existence” must be a property of the **entire reset-request pipeline**, not just one message string. Public responses stay neutral; user lookup, token issuance, and mail dispatch belong in an internal worker. Only by combining uniform execution paths, timing side-channel defenses, rate limits, and secure tokens can you stop attackers from enumerating which accounts use your service.

### References

- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Spring Security — Password Storage / PasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- NIST SP 800-63B-4 — Account Recovery: https://pages.nist.gov/800-63-4/sp800-63b.html
