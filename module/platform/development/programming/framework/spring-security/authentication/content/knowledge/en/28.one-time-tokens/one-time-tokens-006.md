# Magic Links, Public URLs, and Redirect Destination Restrictions

> **Context:** Spring Security Authentication, **One-Time Tokens** group. This lesson explains how to generate email sign-in links (magic links), construct safe public URLs when the application sits behind a reverse proxy, and restrict post-login redirects to prevent token leaks, domain spoofing, and open redirects. Examples apply to Java 17+, Spring Boot 3.x, and Spring Security 6.4–6.5 on the **Servlet stack**.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish magic links from passwords, OAuth access tokens, TOTP, and Spring Security One-Time Tokens (OTT); explain the lifecycle request → generate token → send link → submit token → sign in.
2. Construct the **public base URL** from trusted configuration, never from `Host`, `Forwarded`, `X-Forwarded-Host`, or user-supplied URLs.
3. Prevent **Host Header Injection**, sending magic links to an attacker's hostname, leaking tokens via redirects and referrers, and URLs containing credentials.
4. Allow redirects only to **approved internal destinations**, using a server-side destination key instead of forwarding `next` or `returnUrl` directly to `Location`.
5. Configure `oneTimeTokenLogin()` in Spring Security 6.5, a custom `OneTimeTokenGenerationSuccessHandler`, and a secure email service.
6. Design tokens with sufficient entropy, short TTLs, **atomic single use**, protection against automated email link scanning, rate limiting, and user-enumeration prevention.
7. Test end-to-end both the application and the reverse proxy when running behind a load balancer, CDN, or API gateway.

## 2. What a Magic Link Actually Is

A **magic link** is a URL containing a **one-time secret** sent to a communication channel the application considers trusted enough for sign-in, typically a registered email mailbox verified per product policy. Whoever holds the link can present that secret to the server to complete login. This is a form of **possession-based authentication**: access to the mailbox or link-delivery system becomes part of the security boundary.

An example link looks like:

```text
https://app.example.org/login/ott?token=b64url_random_secret_example
              ↑                  ↑
        Public origin      One-time secret
```

The string in the example is for illustration only; **never use fixed or predictable tokens in production**.

A **One-Time Token (OTT)** is a server-issued random value bound to an identity and expiration, consumed once; it differs from **TOTP/HOTP** (one-time passwords computed from a seed/counter/time) and differs from **OAuth2 access tokens** (credentials granting API access under a grant). A magic link is a **transport mechanism for OTT** from the server to the user.

A link-request submission does not authenticate the sender; the user is authenticated only when a **valid token is consumed by the server and accepted by account policies**. Nor are all emails equally trustworthy: if a mailbox is compromised, forwarded, shared, or unverified, a magic link can become an account-takeover path.

### Overall Flow

```text
User's browser
   │ 1. POST /ott/generate, enters username/email
   ▼
Spring Security / application
   │ 2. Rate-limit, check account status/verified address
   │ 3. Generate random OTT; store hash + subject + purpose + expiresAt
   │ 4. Build URL from statically configured public origin
   │ 5. Send link via email; return neutral notice
   ▼
User's mailbox
   │ 6. User opens link over HTTPS
   ▼
GET /login/ott?token=...
   │ 7. Landing page must not casually consume token
   │    on email-scanner/link-prefetch
   │ 8. User actively confirms, POSTs token + CSRF
   ▼
OneTimeTokenService.consume(...)
   │ 9. Verify unexpired/unused/right purpose,
   │    consume atomically
   │ 10. Check active account, create Authentication/session
   ▼
Application
   │ 11. Redirect to a path chosen from an allowlist
   ▼
/dashboard or /orders (same trusted origin)
```

The Spring Security OTT DSL provides token generation/consumption components and login integration. Sending email, managing contacts, public URLs, anti-spam/anti-scanner policies, and business redirects still require appropriate configuration or implementation.

## 3. Two Types of Absolute URLs That Must Never Be Confused

### 3.1. Public URL Used in Email

This is the address the recipient **actually accesses from the Internet**. For example:

```text
https://login.example.org/login/ott?token=...
```

It must come from **trusted deployment-environment configuration**, e.g., `app.magic-link.public-origin=https://login.example.org`, managed by the deployment system. Behind a reverse proxy, the internal hostname might be `web-07.internal:8080`, while the public domain is `login.example.org`.

### 3.2. Post-Login Destination

This is the **page shown after the token has been authenticated**, e.g., `/dashboard` or `/orders`. This destination is a **navigation** decision, not an authentication secret. Because the destination can come from a UI button or a `next` parameter, the server must validate it independently. Without control, an attacker can abuse the real domain to craft phishing links that send users to another website.

| Data | Example | Trusted Source |
|---|---|---|
| Canonical public origin | `https://login.example.org` | Approved server/deployment configuration |
| Random token | Base64url of 32 SecureRandom bytes | Server-side token service |
| Email recipient address | Verified login email bound to local account | Trusted user store |
| Post-login page | `/dashboard`, `/orders` | Server-side allowlist or server-mapped destination key |
| `Host`, `X-Forwarded-Host` | Headers brought by network path | **Not** trusted by default to build email URLs |
| Client-supplied `next`, `returnUrl`, `redirect_uri` | `https://evil.example` | **Never** pass directly into response `Location` |

**Distinction:** OAuth/OIDC `redirect_uri` is a callback URL registered with an IdP, whereas a magic-link **post-login destination** is an in-application page. Both need restrictions, though they do not share the same naive validation mechanism across all contexts.

## 4. Host Header Injection: Why Links Must Not Be Built from Requests

Error-prone pattern:

```java
// Do NOT use when issuing magic links to email
String root = request.getScheme() + "://" +
              request.getServerName();
String url = root + "/login/ott?token=" + token;
```

If the reverse proxy does not protect `Host` or forwarding headers, a request can make the application believe its hostname is `attacker.example`. The legitimate user's email then receives a link containing the login secret but pointing to an attacker-controlled domain. The user clicks the link, the token is sent to the attacker, and the attacker can replay the token against the real application before it expires.

Even when the request arrives over HTTPS, if the hostname is accepted from the client, **HTTPS does not stop header manipulation**.

### Attack Example

```http
POST /ott/generate HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
Content-Type: application/x-www-form-urlencoded

username=mai
```

A vulnerable system generates the email:

```text
https://attacker.example/login/ott?token=SECRET_FOR_MAI
```

The path and token look legitimate, yet the hostname has been replaced. The expected result with proper defense is:

```text
https://login.example.org/login/ott?token=SECRET_FOR_MAI
```

**Most important defense:** do not use `request.getRequestURL()`, `ServletUriComponentsBuilder.fromCurrentRequest()`, `UrlUtils.buildFullRequestUrl(request)`, or hostnames derived from `Forwarded`/`X-Forwarded-*` to **determine the origin in magic links sent by email** without a strict trust boundary. Those APIs may be useful in controlled contexts, but they cannot prove headers are trustworthy on their own.

Alongside a canonical URL in the application, infrastructure needs:

- The proxy accepts only public `Host` values in the served-domains allowlist; requests with unknown hosts are rejected.
- The proxy **strips and resets** `Forwarded`, `X-Forwarded-Host`, and `X-Forwarded-Proto` from untrusted client sources; the app accepts forwarding metadata only from allowed proxies.
- The backend has no other public path bypassing the proxy or exposing internal HTTP ports.
- Do not enable trusting all forwarded headers on a backend that can be reached directly.
- Public domain TLS certificates, hostnames, HSTS, and DNS are properly operated.

Depending on needs, `server.forward-headers-strategy=framework` or similar may be necessary for certain Spring Boot redirects/cookies behind a proxy, but **it does not replace explicitly configuring a canonical public origin** for token-bearing links.

### What About Multiple Domains/Tenants?

Do not take `tenantDomain` from a query string or client `Host` and assemble links arbitrarily. Maintain a mapping of **server-verified tenant ID → admin-configured canonical HTTPS origin**. When issuing an OTT, select the domain from the user's tenant record and permitted issuer/route; never let users pass an arbitrary domain string. Verify domain ownership, prevent subdomain takeover, and govern tenant domain changes.

## 5. Open Redirect: Restricting Redirect Destinations

**Open redirect** occurs when the server takes a caller-supplied URL directly as the redirect target. Bad example:

```java
// DO NOT USE: attacker picks any Location
response.sendRedirect(request.getParameter("next"));
```

A misleading URL:

```text
https://login.example.org/login/complete?next=https://evil.example/phishing
```

Users see the trusted domain first, yet after signing in they can be redirected to a spoofed website. If code appends `token`, email, session ID, or sensitive query params to `next`, an open redirect also leaks credentials. Open redirects are sometimes used to bypass callback allowlists in other flows or craft deceptively trustworthy phishing URLs.

### 5.1. Prefer Destination Keys Over Accepting URLs

The easiest design to control: the UI sends only a **short destination key** such as `dashboard` or `orders`; the server maps this key to an internal path:

```text
dashboard  → /dashboard
orders     → /orders
profile    → /account/profile
invalid    → /dashboard
```

When creating the token, the validated destination key can be stored in the server-side intent record or flow-bound session. Once the token is consumed successfully, the server retrieves the approved destination key and calls `sendRedirect("/orders")`. Never read a fresh destination key from a callback and change the target without validation.

**Advantage:** no need to parse every possible URL representation. Strings like `https://evil.example`, `//evil.example`, `%2F%2Fevil.example`, or paths with backslashes, userinfo, or control characters will not match any allowed key.

### 5.2. If Business Requirements Force Accepting URLs

Allow only URLs the application genuinely needs; prefer **relative paths on the same origin**, restricted path prefixes/endpoints, or canonical origins with **HTTPS scheme + exact host + appropriate port + no userinfo**. Parse using a URI parser, rejecting paths starting with `//`, backslashes, dangerous encoded delimiters, Unicode/control chars, abnormal dot-segments, and any variant that changes host upon browser interpretation. Normalize and compare canonical forms per tested safe rules. Avoid string-matching patterns like:

- `url.startsWith("https://login.example.org")`: bypassed by `https://login.example.org.evil.example`.
- `url.contains("example.org")`: accepts an attacker domain containing that substring.
- Checking only a leading `/`: `//evil.example` is a **protocol-relative URL**, not a safe internal path.
- Client-side-only validation: server redirects can still be invoked directly.
- Checking only at magic-link issuance: the callback/finish handler might have `next` tampered with after login.

### 5.3. Access Control After Redirect Is a Separate Check

Even a valid internal destination like `/admin` is not accessible to every logged-in user. Endpoint/service authorization must still check roles/permissions. A redirect allowlist only decides navigation, not privileges. Avoid passing tokens in post-login URLs or embedding them in the `Location` of the next step.

## 6. How Must One-Time Tokens Be Generated and Stored?

### 6.1. Generating Tokens with Sufficient Entropy

A common choice is **32 random bytes from a CSPRNG**, encoded as unpadded Base64url. That provides roughly **256 bits of entropy** before encoding. Do not use:

- `Math.random()`, timestamps, sequential IDs, or username/email to craft tokens.
- Signed JWTs without single-use state while calling them "one-time magic links" without checking `jti`/revocation.
- Hardcoded demo tokens or indefinitely reusable tokens; URLs can be forwarded, scanned, or leaked in logs.

Java 17 example for generating a token (standalone helper class; must use a server-side store in deployment):

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class MagicTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private MagicTokenGenerator() {}

    public static String newToken() {
        byte[] bytes = new byte[32]; // 256 bits
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
```

**Never print real tokens to logs**. The secret in the URL is a credential; anyone holding the URL during its validity window can try to sign in.

### 6.2. Storing Hashes and Required Metadata

For a self-implemented token store, store the **SHA-256/HMAC-SHA-256 of the random token** instead of the raw token, paired with:

- internal `user_id`/username resolved from the trusted account store;
- exact `purpose`, e.g., `MAGIC_LOGIN`, never reusing the same token for password reset, email change, or MFA;
- short `expires_at` (e.g., a few minutes per policy), `consumed_at`, `created_at`;
- flow/session reference, tenant, and destination key if policy requires;
- safe audit info, avoiding storing full URLs/tokens in logs.

The raw token is used only for email delivery and matching at consumption time; the app hashes the submitted token and queries the row. For high-security systems with multiple secret types, consider HMAC with a secret-manager key so hash patterns are not exposed; with 256-bit random tokens, SHA-256 already resists offline brute force in practice given proper rate limiting and transport encryption.

### 6.3. Atomic Token Consumption

In multi-worker/multi-node systems, ensure **two requests with the same token cannot both succeed**. Illustrative PostgreSQL table:

```sql
CREATE TABLE magic_login_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    purpose VARCHAR(30) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX magic_login_expiry_idx
    ON magic_login_tokens(expires_at);
```

After computing `:sha256_of_presented_token` in the backend, an atomic consumption statement:

```sql
UPDATE magic_login_tokens
SET consumed_at = now()
WHERE token_hash = :sha256_of_presented_token
  AND purpose = 'MAGIC_LOGIN'
  AND consumed_at IS NULL
  AND expires_at > now()
RETURNING local_user_id;
```

PostgreSQL lets only one transaction update the unconsumed row; competing transactions find the predicate unsatisfied. If no row is returned, the token is wrong, expired, or already used; the client receives a neutral error. Then verify the local account is still active/allowed to log in, create a secure session, and avoid TOCTOU per policy. When spanning multiple services/transactions, avoid marking a token consumed and then failing while accidentally leaving an inconsistent session.

**Do not use**:

```text
SELECT token WHERE consumed=false
if found:
    grantLogin()
    UPDATE consumed=true
```

Two concurrent requests can both succeed on `SELECT` before either runs `UPDATE`. Redis can use `GETDEL`/atomic Lua or a suitable transaction; the requirement remains **one accepted consumption** cluster-wide.

### 6.4. Expiration and Error Handling

A link may expire before email delivery or user click; allow **requesting a new link** with rate limiting and clear messaging without extending the expired token's TTL. Old tokens may be invalidated upon issuing a new one per policy, balancing multi-tab/device UX.

If a user is disabled/locked or their email is no longer verified, do not let OTT bypass account status. Some Spring Security OTT versions/configurations may require adding a `UserDetailsChecker`/policy to check account status; never assume a valid token satisfies every business condition by default.

## 7. Spring Security 6.5: Using One-Time Token Login

Spring Security 6.4+ includes the `oneTimeTokenLogin()` DSL for Servlet applications. Standard flow:

1. A POST to `/ott/generate` (default) requests a token for a username.
2. `OneTimeTokenService.generate(...)` creates the token.
3. A custom `OneTimeTokenGenerationSuccessHandler` **delivers the token via email/SMS**.
4. The link takes the user to the submit page, defaulting to `GET /login/ott?token=...`; the default page populates the token into a form.
5. **POST `/login/ott`** processes the token. When CSRF is enabled, the form submission needs a CSRF token like any other POST.
6. `OneTimeTokenService.consume(...)` verifies and consumes the token; the provider performs authentication; successful login establishes the security context/session per config.

**Crucial point:** by default, **GET** to the submit page is not a promise that you can casually log in over GET; Spring Security 6.5 configures the processing endpoint as **POST**. Email scanners may hit GET to inspect links, so never attach consumption logic to your GET endpoint.

### 7.1. Gradle Dependencies

In a Spring Boot 3.x project with compatible plugin/BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

You must supply a `UserDetailsService`/user store and mail transport (`spring.mail.*` or mail service). If using a JDBC token store, add JDBC/DataSource and configure the schema and transactions properly. Spring Security defaults to `InMemoryOneTimeTokenService`, useful for **single-node** testing; multi-node production should use a shared store with safe consumption (Spring Security offers `JdbcOneTimeTokenService` or a custom store).

### 7.2. Statically Configured Canonical Public Origin

`src/main/resources/application.yml`:

```yaml
app:
  magic-link:
    public-origin: ${MAGIC_LINK_PUBLIC_ORIGIN:https://login.example.org}

spring:
  mail:
    host: ${SMTP_HOST:localhost}
    port: ${SMTP_PORT:1025}
```

In production, `MAGIC_LINK_PUBLIC_ORIGIN` is managed at deployment time; the default above is an example and must be replaced with the real TLS domain. Never allow users to change the origin via requests, headers, or email inputs.

### 7.3. SecurityFilterChain for OTT

`src/main/java/com/example/security/OttSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OttSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            MagicLinkGenerationHandler generationHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/login/ott", "/ott/sent", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(generationHandler));

        return http.build();
    }
}
```

This is a configuration class inside a Spring Boot app that has `@SpringBootApplication`, a database/user repository, and a mail service—not a standalone program runnable with `javac`. `oneTimeTokenLogin` adds token generation/submission filters; mail delivery is delegated to `generationHandler`. Before deployment, verify request matchers, customized login paths, CSRF, account status, and public pages. **Do not disable all CSRF** just to make POST `/ott/generate` or `/login/ott` easier to hit.

If you want to keep password login alongside it, `formLogin` can be useful; if the product is magic-link-only, design the login page and configuration appropriately rather than copying a two-method setup unintentionally.

### 7.4. Handler Sending Magic Links Using Configured Origin

Example **Spring Boot-integrated** handler implementation. It builds links from the verified `public-origin` and sends only to a verified login address looked up from the user store; it never takes recipient addresses or link domains from request inputs.

File `src/main/java/com/example/security/MagicLinkGenerationHandler.java`:

```java
package com.example.security;

import java.io.IOException;
import java.net.URI;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public final class MagicLinkGenerationHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final JavaMailSender mail;
    private final LoginContactDirectory contacts;
    private final URI publicOrigin;

    private final OneTimeTokenGenerationSuccessHandler sent =
        new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    public MagicLinkGenerationHandler(
            JavaMailSender mail,
            LoginContactDirectory contacts,
            @Value("${app.magic-link.public-origin}") String origin) {
        this.mail = mail;
        this.contacts = contacts;
        this.publicOrigin = checkedOrigin(origin);
    }

    private static URI checkedOrigin(String configured) {
        URI uri = URI.create(configured);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty())) {
            throw new IllegalArgumentException(
                "Magic-link origin must be HTTPS scheme + host only");
        }
        return uri;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       OneTimeToken token)
            throws IOException, ServletException {

        // Look up verified login email from the application's user store.
        // Null: do not reveal account existence to the client.
        String address = contacts.verifiedLoginEmail(token.getUsername());

        if (address != null) {
            String magicLink = UriComponentsBuilder
                .fromUri(this.publicOrigin)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .encode()
                .build()
                .toUriString();

            SimpleMailMessage message = new SimpleMailMessage();
            message.setTo(address);
            message.setSubject("One-time sign-in link");
            message.setText(
                "Open sign-in link: " + magicLink +
                "\nIf you did not request this, please ignore this email.");

            this.mail.send(message);
        }

        // Return UI confirmation flow without leaking whether username exists.
        this.sent.handle(request, response, token);
    }
}
```

Add the user repository contract so the class compiles once a real implementation exists:

```java
package com.example.security;

public interface LoginContactDirectory {
    // Returns a verified email for an account still eligible to receive a link.
    // Returns null when no valid address exists.
    String verifiedLoginEmail(String username);
}
```

**You must provide a Spring bean of `LoginContactDirectory`** accessing a secure user store; the handler above compiles in a project with matching dependencies, but cannot run standalone without the bean, SMTP/IdP, or Spring Boot components. Account status must be checked at both link issuance and consumption, and the issuance endpoint must be rate-limited. The example does not attempt real email delivery when SMTP is unconfigured.

**Why is `checkedOrigin` strict?** It rejects `http://`, empty hosts, userinfo like `user@host`, queries/fragments, and arbitrary base paths. This pattern intentionally supports origins **without a context path**. If the app runs under `/portal`, add a separate configured `public-base-path`, validate it canonically, and construct URLs with a URI builder; never take paths from inbound requests. Origin validation must run at application startup rather than waiting for the first email send to discover misconfiguration.

**Do not modify header forwarding solely to solve magic-link generation** because the origin comes from configuration. However, secure cookies, OAuth redirects, and other URLs in the app must still be handled/verified properly by the proxy.

### 7.5. What Remains to Complete for Production

- When a user does not exist, return the same UI notice and manage response speed/latency to avoid user enumeration; never send mail to a requester-entered address unless it belongs to a verified account.
- Depending on the default `OneTimeTokenService` or custom service, control TTL (Spring Security 6.5 defaults to about **5 minutes**, customizable via `GenerateOneTimeTokenRequestResolver`).
- Use a shared token store for multiple instances; enforce atomic single-use and never log raw token values.
- Block tokens used for the wrong purpose, expired/revoked tokens, locked accounts, or sensitive email changes.
- Handle SMTP/queue failures per policy so they neither leak user existence nor cause unintended account lockouts.
- Do not use `UriComponentsBuilder.fromCurrentRequest()` to pull the origin from an attacker's request, even though framework documentation examples may show building URLs from the request for simple illustration.

## 8. Standalone Java 17: Building Magic Links and Choosing Safe Redirects

The following example runs directly with `javac`/`java`, **without Spring**. It only demonstrates **building a link on a fixed origin and mapping redirect keys**, without generating random OTTs, sending emails, or authenticating users. The token in `main` is a **hardcoded placeholder string for demo purposes**—never use it as a real credential.

Save `MagicLinkUrlPolicyDemo.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public final class MagicLinkUrlPolicyDemo {

    private static final URI PUBLIC_ORIGIN =
        URI.create("https://login.example.org");

    private static final Map<String, String> DESTINATIONS = Map.of(
        "dashboard", "/dashboard",
        "orders", "/orders",
        "profile", "/account/profile"
    );

    private MagicLinkUrlPolicyDemo() {}

    static String magicLink(String token) {
        if (token == null
                || !token.matches("[A-Za-z0-9_-]{20,256}")) {
            throw new IllegalArgumentException("Invalid token format");
        }
        return PUBLIC_ORIGIN + "/login/ott?token=" +
            URLEncoder.encode(token, StandardCharsets.UTF_8);
    }

    static String redirectPath(String requestedKey) {
        return DESTINATIONS.getOrDefault(requestedKey, "/dashboard");
    }

    public static void main(String[] args) {
        // Illustrative token only, with no real entropy.
        String demoToken = "AbCdEf0123456789_XyZabcdefghijklmN";

        System.out.println("Link: " + magicLink(demoToken));
        System.out.println("Allowed: " + redirectPath("orders"));
        System.out.println("External: " +
            redirectPath("https://evil.example"));
        System.out.println("Protocol-relative: " +
            redirectPath("//evil.example"));
        System.out.println("Encoded: " +
            redirectPath("%2F%2Fevil.example"));
    }
}
```

Commands:

```bash
javac MagicLinkUrlPolicyDemo.java
java MagicLinkUrlPolicyDemo
```

Exact stdout:

```text
Link: https://login.example.org/login/ott?token=AbCdEf0123456789_XyZabcdefghijklmN
Allowed: /orders
External: /dashboard
Protocol-relative: /dashboard
Encoded: /dashboard
```

**Explanation:**

- `PUBLIC_ORIGIN` is a fixed canonical origin, independent of `HttpServletRequest`.
- `magicLink` checks the base64url **format** of the token; a regex **does not prove the token has entropy or is unused**. Production must use a CSPRNG token issued by Spring OTT/service.
- `URLEncoder` safely encodes the token in the query parameter; the example token uses only base64url characters, so the result is unchanged.
- `redirectPath` maps only a **key** to a fixed path. Any unknown string, including external and protocol-relative URLs, falls back to `/dashboard`. The application must still enforce authorization on the chosen path.
- Never construct magic link URLs via `PUBLIC_ORIGIN.resolve(userInput)`: `URI.resolve` can switch to an external origin if input is absolute/protocol-relative. Concatenate only a **fixed path** with the encoded token.

If an already-authenticated session requests `/orders`, a server-side redirect handler can call `response.sendRedirect(redirectPath(destinationKey))`; this only illustrates destination selection policy and does not replace Spring Security's authentication components.

## 9. Magic Links Leak Easily If URLs Are Handled Poorly

### 9.1. A Token-Bearing URL Is a Credential

When a token sits in a query string, it can appear in:

- Browser history, the address bar, or screenshots.
- Reverse proxies, access logs, APM, crash reports, analytics, or automated tracing.
- The `Referer` header sent to third-party resources if the token-bearing page loads external images, scripts, fonts, or follows external links without a protective referrer policy.
- Email forwarding systems, anti-spam scanners, link rewriting, and shared computers.
- Redirect chains if code accidentally appends the prior full URL or token-bearing query into the next step's `Location`.

On `/login/ott`, set at least:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

Use a strict Content-Security-Policy compatible with the UI to restrict third-party scripts/resources. On token-bearing pages, avoid loading third-party analytics; prevent full URLs from hitting logs or telemetry. On the other hand, `no-referrer` does not erase browser history, proxy logs, or email scanners: reduce token exposure across every layer.

### 9.2. Email Link Scanners (Link Prefetch)

Many email security systems automatically issue `GET` requests to links to scan for malware. If the app **consumes the token immediately on GET**, scanners can "sign in" or invalidate the token before the real user ever clicks it. Common mitigations:

1. GET only displays a confirmation page containing the token submission form, without creating a login session immediately.
2. The user actively submits **POST** with the token and proper CSRF token per policy.
3. The server consumes the token atomically and then creates the session; the UI does not auto-submit on page load or trigger via third-party JavaScript.
4. Account for scanners altering URLs/queries, link rewriting, or mobile environments opening in a different browser. Do not bind rigidly to the originating browser unless the product has designed a matching cross-device mechanism.

Spring Security 6.5 defaults to a `GET /login/ott` page and a `POST /login/ott` authentication endpoint, so preserve this boundary when customizing the UI. Even though scanners do not POST in many cases, never assume all scanners only issue GET; model the threat and support a "request new link" fallback.

### 9.3. Removing the Token from UI After Login

After authentication and session creation, redirect to a path **containing no token**, such as `/dashboard`; configure session fixation protection, appropriate `Secure`, `HttpOnly`, `SameSite` cookies, and session timeouts. You can clean the landing page URL once the token has entered a safe flow, and never keep OTTs in long-lived client-side storage. Never store OTTs in `localStorage`, convenience cookies, or history-tracked paths.

## 10. Testing the Application and Reverse Proxy

Real-world testing must cover **email issuance**, **opening the link**, and **post-login redirects**. Unit-testing Java without testing the proxy does not verify Host poisoning.

| Test Case | Expected Result |
|---|---|
| Valid user requests token | Email sent to verified login email with canonical HTTPS URL |
| Non-existent username | Returns neutral notice, does not leak account existence |
| Request sends `Host: evil.example` | Email still has origin `https://login.example.org` or gateway rejects request |
| Request sends `X-Forwarded-Host: evil.example` | Does not affect email URL; proxy strips spoofed metadata |
| Backend runs at `http://web-07.internal:8080` | Email still has public domain, never internal host/port |
| Public origin configured as `http://` | Fails fast at boot, never issues HTTP links |
| Public origin has userinfo, query, fragment, or unsupported path | Fails fast, refuses to use that origin |
| Non-existent/expired token | Does not log in, allows requesting a new link |
| Already-used token | Cannot be used a second time |
| Two POSTs with same token hit two nodes | At most one request consumes successfully |
| User disabled before clicking link | No Authentication/signed-in session created |
| Email scanner only issues GET | Token is not auto-consumed |
| POST without CSRF while CSRF enabled | Blocked per policy |
| Client requests `next=https://evil.example` | Does not redirect externally |
| Client requests `next=//evil.example` | Does not redirect externally |
| Client requests `next=%2F%2Fevil.example` | Does not redirect externally |
| Client requests `next=https://login.example.org.evil.example` | Does not redirect externally |
| Client requests key `orders` | Redirects to approved internal `/orders` path |
| User lacks permissions for approved page | Authorization returns 403/denies properly, grants no privilege |
| Login page loads external scripts/analytics | Full token must never be sent via referrer/logs |
| Repeated link requests by email/IP | Rate-limited/anti-spam without helping enumerate users |
| Logout then replay used OTT | Does not sign in; does not resurrect token |
| User changes verified email | Sends only to the currently recorded channel per policy |

### Integration Scenarios to Run

**Test A — Host Header Injection.** Send the same `/ott/generate` request with the public `Host`, an unknown Host, and spoofed `Forwarded`/`X-Forwarded-Host`. Use a test mail catcher to inspect the sent link. Compare **scheme + host + port + path** against the configured canonical public origin; do not merely assert `contains("example.org")`.

**Test B — Open redirect.** Start with a valid destination key, then try external URLs, URLs starting with `//`, encoded slashes, mixed case, tabs/newlines, queries containing tokens, and URLs with `@` userinfo. After consume, response `Location` contains only an allowed internal path and no token value. When using a key map, every unknown input falls back to the default path.

**Test C — Atomic one-time.** Issue one token in a shared store and have two clients/workers POST it concurrently. Exactly one request may use the token; the other is rejected. Inspect the DB to confirm `consumed_at` is not reset and the user never gets two sessions from one token due to a race.

**Test D — Scanner and anti-leak.** Hit GET with a simulated bot and verify no login session is created; perform a normal form POST checking CSRF and redirect. Inspect response headers, proxy access logs, tracing, and JavaScript tracking: none may record the raw token.

**Test E — Cross-tenant/multi-environment.** Use staging and production, or two independent domains/tenants. A magic link issued by tenant A must point to A's origin, cannot be consumed on tenant B, and must not mix sessions/roles across tenants.

## 11. Checklist for Deploying Magic Links to Production

1. Single origin managed via configuration: **HTTPS + exact public host**, validated at startup; multi-tenant setups must use a trusted mapping.
2. Reverse proxy blocks unknown Hosts, strips spoofed forwarded headers, and prevents direct public access to the backend.
3. Issue links only to verified contacts in the user store; link-request responses reveal nothing about account existence.
4. Use high-entropy CSPRNG tokens, short TTLs, explicit purposes, hashed storage, transactional/atomic consumption, and cross-node anti-replay.
5. Check that the user is not locked/disabled right at consumption; never treat a valid OTT as admin rights or an authorization bypass.
6. GET landing never consumes the token; POST uses CSRF protection, creates secure sessions/cookies, and rotates session IDs on login.
7. Never use `next`, `returnUrl`, or `Location` from raw requests; apply destination key → internal path mapping; enforce authorization on every endpoint.
8. Token pages set `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; restrict third-party resources, URL logging, and client storage.
9. Rate-limit/detect abuse on OTP generation and token submission; monitor email delivery, scanners, replay, brute force, and anomalous IPs.
10. Test end-to-end on staging through real CDN/load balancers, including Host poisoning, open redirects, multi-node single-use, TTL, account status, and token leaks.

## 12. Common Pitfalls

| Misconception / Mistake | Consequence | Fix |
|---|---|---|
| "We already have TLS, so trust any Host header." | Attacker controls the origin in emailed links | Take origin from server config, validate Host at proxy |
| "Spring examples build URLs from the request, so production is fine too." | Breaks trust boundary when proxy receives spoofed headers | Use an approved canonical public origin; verify network path |
| "An unguessable token alone is enough." | Token leaks/replays or gets reused | Short TTL, hashed store, atomic single-use, protect logs/referrers |
| "Auto-logging in on GET magic links is more convenient." | Email scanners can consume the token | GET landing does not consume; POST confirms with CSRF |
| "Redirecting to a client-provided URL is harmless." | Open-redirect phishing and credential leaks | Server-side destination key allowlist |
| "Allowing URLs starting with the company domain." | `company.example.evil.example` still slips through | Exact canonical URI matching or key map |
| "Every path on the same domain is safe." | Paths may cross privileges or trigger sensitive actions | Redirect allowlist plus per-resource authorization |
| "Removing the link from the UI revokes the token." | Tokens in emails/logs remain usable | Revoke in the token store/consumption state |
| "In-memory token service suffices for a cluster." | Restarts/other nodes lose tokens or fail to block replay | Shared durable store with atomic consume |
| "Sending to whatever email the requester types is fine." | Enables login to unverified contacts and spam | Pick verified email from user store and rate-limit |

## 13. Knowledge Self-Check

**Question 1.** Why must magic links not be created with `request.getServerName()` when an API sits behind a reverse proxy?  
**Answer:** Host/forwarded metadata can be influenced by clients when trust boundaries or proxies are misconfigured. Token-bearing links would be redirected to an attacker's domain; always use a canonical public origin from server configuration.

**Question 2.** Is `returnUrl=//evil.example` an internal path because it starts with `/`?  
**Answer:** No. It is a protocol-relative URL that can direct browsers to an external host. Use fixed destination keys mapped to internal paths, or a strict parser and policy.

**Question 3.** Why can a "single-use" token implemented with `SELECT` then `UPDATE` still be replayed?  
**Answer:** Two competing requests can both read the unused state before updating. Use atomic consumption in the database/Redis or a proper transaction.

**Question 4.** Why shouldn't tokens be consumed on GET when opening the email?  
**Answer:** Email scanners/link prefetchers can automatically issue GET before the user does. GET should only render the form, while POST performs consumption and session creation.

**Question 5.** Does `Referrer-Policy: no-referrer` alone stop all magic-link leaks?  
**Answer:** No. It limits referrer leaks; you still need to address browser history, proxy logs, analytics, email forwarding, redirect chains, and mailbox protection.

**Question 6.** What if a user has logged in successfully and requests redirecting to `/admin` via an approved key?  
**Answer:** `/admin` authorization must still check current permissions; a destination allowlist grants no extra authorities.

**Question 7.** When using `oneTimeTokenLogin()`, which parts must the application build itself?  
**Answer:** Token delivery via email/SMS, selecting verified emails, canonical URLs, rate limiting, redirect control, account status policies, shared storage across multiple nodes, and proxy/scanner testing.

## References

- [Spring Security 6.5 — One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, `OneTimeTokenService`, generate/submit endpoints, token delivery handler, and default TTL.
- [Spring Security 6.5 — OneTimeTokenLoginConfigurer Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html): `tokenGenerationSuccessHandler`, `loginProcessingUrl`, `tokenGeneratingUrl`, and OTT configuration.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): token entropy, expiry/single-use, preventing Host Header Injection, HTTPS, and referrer leaks (similar principles apply to magic links).
- [OWASP — Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): open redirects and destination allowlists.
- [Spring Security — Proxy Server Configuration](https://docs.spring.io/spring-security/reference/servlet/appendix/proxy-server.html): handling URLs/cookies and forwarded headers behind a reverse proxy.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication, user enumeration, and login flow protection.
