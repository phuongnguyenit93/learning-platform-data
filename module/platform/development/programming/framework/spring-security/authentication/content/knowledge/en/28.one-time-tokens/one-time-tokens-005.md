# OneTimeTokenGenerationSuccessHandler and Application-Managed Token Delivery

## 1. Concept and Boundary of Responsibilities

Spring Security Servlet 6.4+ provides **One-Time Token (OTT)** login via `HttpSecurity.oneTimeTokenLogin(...)`. Users request a one-time token, receive it via email/SMS or another channel, and submit the token to sign in. **Spring Security handles generating and consuming OTTs, but does not automatically send tokens to users** because the framework does not know the application's email system, SMS provider, or verified contact addresses.

That is the role of `OneTimeTokenGenerationSuccessHandler`: receive the token after successful generation, deliver it through a trusted channel chosen by the application, and return an appropriate response. This handler is **not an `AuthenticationSuccessHandler`**, and generation success **does not mean the user is signed in**.

Four independent parts:

1. `GenerateOneTimeTokenFilter` receives `POST /ott/generate` and creates `GenerateOneTimeTokenRequest`.
2. `OneTimeTokenService.generate(...)` generates/stores `OneTimeToken` bound to username, secret value, and expiration.
3. `OneTimeTokenGenerationSuccessHandler.handle(...)` processes the new token: looks up the verified email, sends the magic link, and redirects to a generic notice page.
4. `OneTimeTokenAuthenticationFilter` runs when the user submits the token; `OneTimeTokenService.consume(...)` checks existence, expiry, and single-use; only then does it create an `Authentication` and save the SecurityContext as configured.

```text
Browser POST /ott/generate (username + CSRF)
  -> GenerateOneTimeTokenFilter
  -> OneTimeTokenService.generate(...)
  -> OneTimeTokenGenerationSuccessHandler
       -> verified contact lookup -> email/SMS/queue
       -> redirect /ott/sent (not signed in)

User receives link -> GET /login/ott?token=<secret>
  -> default page renders form with pre-filled token
  -> POST /login/ott (token + CSRF)
  -> OneTimeTokenAuthenticationFilter
  -> OneTimeTokenService.consume(...)
       -> invalid / used / expired: reject
       -> valid: Authentication succeeds
```

**GET on the magic link does not automatically consume the token** when using the default submit page. The login POST processes the credential, preventing certain situations where email scanners/link-previewers automatically click GET and burn the token.

### OTT Differs from OTP/TOTP

| Mechanism | Who Generates? | Who Sends? | When Used |
| --- | --- | --- | --- |
| Spring Security OTT | Server generates on demand | Application delivers each token | Login via magic link/single-use code |
| TOTP/HOTP | Authenticator/device computes from shared secret | Individual codes not sent; requires initial secret provisioning | Authentication using time/counter-based codes |
| OAuth2 access token | Authorization server | Via OAuth2 protocol | Calling resource APIs, not an OTT login token |
| CSRF token | Application/framework | Passed via form/cookie per config | Request forgery protection, not an OTT credential |

An OTT is a secret credential. Anyone holding an unused, unexpired secret can attempt to sign in: **do not log tokens, do not include tokens in the generation response, and do not send them to client-declared emails instead of verified contacts**.

## 2. The Interface and Two Types of Success Handlers

Servlet interface:

```java
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.authentication.ott.OneTimeToken;
```

Core signature (inside a class implementing the interface):

```java
@Override
public void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        OneTimeToken oneTimeToken)
        throws IOException, ServletException {
    // Deliver or delegate token delivery, then return HTTP response.
}
```

Parameters:

- `request` / `response` from Jakarta Servlet, used to complete the generation request.
- `oneTimeToken.getUsername()`: the username that requested the OTT. **Look up the verified contact from the database** using the username; never trust an arbitrary email/phone number entered by the form submitter.
- `oneTimeToken.getTokenValue()`: the raw secret for building the magic link or sending via SMS; must be kept confidential.
- `oneTimeToken.getExpiresAt()`: expiration `Instant`, which can be included in the email. Changing email wording **does not change the token's expiry**.

`RedirectOneTimeTokenGenerationSuccessHandler` only performs a redirect:

```java
OneTimeTokenGenerationSuccessHandler redirect =
    new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");
redirect.handle(request, response, oneTimeToken);
```

This is a snippet in a handler context, not a standalone Java program. It does not send email, consume the token, or create an `Authentication`. Typically, after sending or durably enqueuing, the application invokes the redirect handler to display a page saying "If a valid account exists, check your email".

| Component | When It Runs | Responsibility |
| --- | --- | --- |
| `OneTimeTokenGenerationSuccessHandler` | After generation | Deliver token and send response |
| `RedirectOneTimeTokenGenerationSuccessHandler` | When invoked | Redirect, does not send secret |
| `OneTimeTokenService` | During generate/consume | Create and verify tokens, single-use |
| `AuthenticationSuccessHandler` | After successful login | Navigate after authentication completes |

**Common layering mistake:** implementing `AuthenticationSuccessHandler` to send the magic link. That handler runs too late; the application must configure `tokenGenerationSuccessHandler(...)` or register a `OneTimeTokenGenerationSuccessHandler` bean.

## 3. Default URLs and TTL in Spring Security Servlet 6.5

- `POST /ott/generate`: generation filter. Form requests require a CSRF token when CSRF is enabled.
- `GET /login/ott`: default token submission page, reads the `token` query param and populates the form.
- `POST /login/ott`: authenticates the OTT, requires proper CSRF.
- Default `OneTimeTokenService` may be `InMemoryOneTimeTokenService`; multi-node production should consider `JdbcOneTimeTokenService` or a reliable shared store.
- Generation requests in 6.5 documentation typically default to expiring after **5 minutes**, customizable via `GenerateOneTimeTokenRequestResolver` / `OneTimeTokenService` per policy.

DSL option names may vary across 6.5/7.x release lines; this lesson uses the stable `tokenGenerationSuccessHandler(...)` method. Always check the API of the exact dependency version in use.

## 4. Security Principles Before Writing Code

**Verified contact:** If an attacker requests an OTT for Alice and sets `recipient=attacker@example.test`, sending to that input turns OTT into account takeover. Only use contacts bound to Alice that were **previously verified**.

**Canonical URL:** Do not construct magic links from raw `Host`/`X-Forwarded-Host` request headers. Attackers can perform **Host header poisoning**, causing Alice's email to contain a link pointing to an attacker-controlled host. Use a fixed HTTPS URL from trusted configuration or a tenant-to-origin allowlist.

**Anti-user-enumeration:** The browser should see the same generic message regardless of whether the username exists. Account for email-sending timing side channels (a real email takes longer than a missing account), rate limiting, and monitoring—not just status/body.

**Token in URL:** Magic links with `?token=...` can leak via reverse proxy logs, browser history, referrers, or analytics. Enable HTTPS, `Referrer-Policy: no-referrer`, disable third-party assets on token-receiving pages whenever possible, redact logs, and use short TTLs.

**Asynchronous delivery:** If using a queue/outbox to avoid waiting on SMTP, the token is still a secret inside the job. Protect it with ACLs/encryption/TTLs, and do not store raw tokens in logs or uncontrolled dead-letter queues. A "delivery request accepted" response does not mean the email reached the inbox or that the user is signed in.

## 5. Java 17+ / Spring Boot Servlet: Handler Sending a Magic Link

The example uses Spring Boot 3.x, Spring Security 6.5.x, and a local test SMTP server (e.g., Mailpit on port 1025). Do not use test addresses to send real email. Dependencies in a Spring Boot project with compatible Gradle plugin and BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  mail:
    host: localhost
    port: 1025

app:
  security:
    public-base-url: http://localhost:8080
```

Production must switch to an HTTPS origin and SMTP with TLS/credentials/monitoring. Place all of the following code in `src/main/java/example/OttApplication.java`:

```java
package example;

import java.io.IOException;
import java.util.Map;
import java.util.Optional;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // Demo account; only OTT enabled, password form login not enabled.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-for-ott")
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, MagicLinkHandler handler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/login/ott", "/ott/generate",
                    "/ott/sent", "/error").permitAll()
                .anyRequest().authenticated())
            .oneTimeTokenLogin(ott ->
                ott.tokenGenerationSuccessHandler(handler))
            .build();
    }
}

// Demo: source of contacts already verified.
// Production: replace with a user directory and emailVerified check.
@Component
class VerifiedEmailDirectory {
    private final Map<String, String> contacts =
        Map.of("alice", "alice@example.test");

    Optional<String> verifiedEmail(String username) {
        return Optional.ofNullable(contacts.get(username));
    }
}

@Component
class MagicLinkHandler implements OneTimeTokenGenerationSuccessHandler {
    private final MailSender mail;
    private final VerifiedEmailDirectory directory;
    private final String publicBaseUrl;

    private final OneTimeTokenGenerationSuccessHandler redirect =
        new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    MagicLinkHandler(
            MailSender mail,
            VerifiedEmailDirectory directory,
            @Value("${app.security.public-base-url}") String publicBaseUrl) {
        this.mail = mail;
        this.directory = directory;
        this.publicBaseUrl = publicBaseUrl;
    }

    @Override
    public void handle(
            HttpServletRequest req,
            HttpServletResponse res,
            OneTimeToken token) throws IOException, ServletException {

        Optional<String> email =
            directory.verifiedEmail(token.getUsername());

        if (email.isPresent()) {
            String link = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .encode().build().toUriString();

            SimpleMailMessage msg = new SimpleMailMessage();
            msg.setFrom("no-reply@shop.example.test");
            msg.setTo(email.get());
            msg.setSubject("One-time sign-in link");
            msg.setText("Sign in at:\n" + link
                + "\nExpires at: " + token.getExpiresAt()
                + "\nIf you did not request this, please ignore this email.");
            mail.send(msg);
        }

        // Both known and unknown usernames receive the same redirect.
        redirect.handle(req, res, token);
    }
}

@RestController
class OttPageController {
    @GetMapping("/ott/sent")
    ResponseEntity<String> sent() {
        return ResponseEntity.ok(
            "If the account is eligible, please check your verified email."
        );
    }

    @GetMapping("/private")
    ResponseEntity<String> privatePage() {
        return ResponseEntity.ok("You are signed in.");
    }
}
```

Detailed explanation:

1. `.oneTimeTokenLogin(...)` enables the generation/authentication flow. `tokenGenerationSuccessHandler(handler)` hands new tokens to the application for delivery; no custom `OneTimeTokenService` is required if using the default.
2. `VerifiedEmailDirectory` is a test map, **not** production email-verification logic. Never trust an address supplied by the request. The username only looks up the server-side record and verified contact.
3. `MailSender` is auto-configured by Spring Boot when the mail starter and SMTP settings are present; `SimpleMailMessage` sends plain text. The `example.test` sender domain is for demos, not production.
4. The handler reads `getTokenValue()` and builds the URL from the trusted `publicBaseUrl`. It never reads the browser-supplied host to construct links.
5. When there is no verified email, nothing is sent, yet the same redirect is returned. This is necessary but not sufficient against timing enumeration: production needs rate limiting/queues/monitoring.
6. `RedirectOneTimeTokenGenerationSuccessHandler` sends the post-generation response. Redirecting does not authenticate the user, consume the token, or log the token.
7. CSRF is **not** disabled; forms submitting `POST /ott/generate` and `POST /login/ott` must carry valid CSRF tokens.

Example request (not real credentials):

```http
POST /ott/generate HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-id>

username=alice&_csrf=<valid-csrf-token>
```

If generation/sending succeeds, the response is typically **302** to `/ott/sent`; the secret travels only via email. The sample email contains a link like `http://localhost:8080/login/ott?token=ONE-TIME-SECRET`. The user opens the GET form and then submits POST token with CSRF; only then does login happen if the token is valid.

## 6. Testing the Handler with JUnit and Mockito

The following tests use only a mock mail sender and mock servlet objects; no real SMTP is called. Place in `src/test/java/example/MagicLinkHandlerTest.java`.

```java
package example;

import java.time.Instant;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.ott.DefaultOneTimeToken;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class MagicLinkHandlerTest {
    @Test
    void sendsToVerifiedEmailAndNeverReturnsToken() throws Exception {
        MailSender mail = mock(MailSender.class);
        VerifiedEmailDirectory directory =
            mock(VerifiedEmailDirectory.class);

        when(directory.verifiedEmail("alice"))
            .thenReturn(Optional.of("alice@example.test"));

        var handler = new MagicLinkHandler(
            mail, directory, "https://login.example.test");
        var req = new MockHttpServletRequest("POST", "/ott/generate");
        var res = new MockHttpServletResponse();

        handler.handle(req, res, new DefaultOneTimeToken(
            "secret-abc", "alice",
            Instant.parse("2030-01-01T12:05:00Z")));

        ArgumentCaptor<SimpleMailMessage> captured =
            ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mail).send(captured.capture());

        SimpleMailMessage sent = captured.getValue();
        assertNotNull(sent.getText());
        assertEquals("alice@example.test", sent.getTo()[0]);
        assertTrue(sent.getText().contains(
            "https://login.example.test/login/ott?token=secret-abc"));

        assertEquals(302, res.getStatus());
        assertEquals("/ott/sent", res.getRedirectedUrl());
        assertFalse(res.getContentAsString().contains("secret-abc"));
    }

    @Test
    void unknownUserReceivesSameRedirectButNoMail()
            throws Exception {
        MailSender mail = mock(MailSender.class);
        VerifiedEmailDirectory directory =
            mock(VerifiedEmailDirectory.class);

        when(directory.verifiedEmail("unknown"))
            .thenReturn(Optional.empty());

        var handler = new MagicLinkHandler(
            mail, directory, "https://login.example.test");
        var res = new MockHttpServletResponse();

        handler.handle(
            new MockHttpServletRequest("POST", "/ott/generate"),
            res,
            new DefaultOneTimeToken(
                "secret-other", "unknown",
                Instant.parse("2030-01-01T12:05:00Z")));

        verifyNoInteractions(mail);
        assertEquals(302, res.getStatus());
        assertEquals("/ott/sent", res.getRedirectedUrl());
        assertFalse(res.getContentAsString().contains("secret-other"));
    }
}
```

Run tests in a Spring Boot module with the Gradle wrapper:

```bash
./gradlew test --tests "example.MagicLinkHandlerTest"
```

On Windows: `.\gradlew.bat test --tests "example.MagicLinkHandlerTest"`.

If the tests pass, we confirm the handler invokes the mock mail sender with the right link, never returns the secret in the HTTP response, and sends no mail for an unknown username. These tests **do not prove** that real emails reach inboxes, that the user owns the mailbox, or that the token authenticates successfully.

### Separate Single-Use Test for the Service

`OneTimeTokenService` is not the delivery handler. A separate test:

```java
package example;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;
import org.springframework.security.authentication.ott.OneTimeTokenService;
import static org.junit.jupiter.api.Assertions.*;

class OneTimeTokenConsumptionTest {
    @Test
    void consumesExactlyOnce() {
        OneTimeTokenService service = new InMemoryOneTimeTokenService();
        OneTimeToken token = service.generate(
            new GenerateOneTimeTokenRequest(
                "alice", Duration.ofMinutes(5)));

        var credential = new OneTimeTokenAuthenticationToken(
            token.getTokenValue());

        OneTimeToken first = service.consume(credential);
        OneTimeToken second = service.consume(credential);

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }
}
```

Run `./gradlew test --tests "example.OneTimeTokenConsumptionTest"`. There is no fixed business stdout in these tests. An in-memory test does not prove atomic consumption across multiple nodes; to verify production behavior, run integration tests against real JDBC/storage.

## 7. Lost Emails, Expiration, Multi-Node, and Account Privileges

**Delivery failures:** the handler in the example calls `mail.send(...)` synchronously. When SMTP throws an exception, the OTT may already have been generated while the user never received the email. In production, enqueue the job into a durable queue/outbox before returning the generic notice page. Jobs containing raw tokens must be protected as credentials: encrypted, access-restricted, short TTL, and never placed in logs or uncontrolled dead-letter queues. Have bounded retry policies and handle duplicate/delayed emails.

**Expiration:** `OneTimeToken.getExpiresAt()` is the expiry enforced by the service. Emails arriving after the token expires must be rejected; never "extend" it by changing the email text. Allow requesting a new token subject to rate limits.

**Replay:** a successful first consume must prevent further use of the token; with a distributed store, consume must be atomic so two parallel requests cannot both authenticate.

**Multi-node:** `InMemoryOneTimeTokenService` is only useful for single-JVM dev/test. Node A generating a token and node B receiving the submit may fail to find it, or restarts lose state. Use `JdbcOneTimeTokenService` or an appropriately designed shared store.

**Locked accounts:** an unused token is not enough to prove a user may sign in if the account was just disabled/locked/expired. Enforce account policies during authentication; verify `OneTimeTokenAuthenticationProvider` behavior on your exact version and configure the necessary checker.

**Query token leaks:** magic links carry the secret in the URL, easily recorded in browser/proxy analytics. HTTPS, no-referrer, restricting third-party assets, query redaction, and preventing link-previewers from consuming tokens are essential safeguards.

### Integration Tests Needed

| Scenario | Outcome to Verify |
| --- | --- |
| Verified user requests OTT | Sent to right verified contact; generic HTTP response contains no secret |
| Non-existent user or unverified email | No secret sent to client-chosen address; no account existence leaked |
| Spoofed Host header | Magic link still uses canonical origin from configuration |
| SMTP fail/bounce | Recovery/retry works without leaking raw token |
| Expired token | Cannot sign in even if email remains |
| Already-used token | Second attempt must fail |
| Two concurrent consume requests | Only one succeeds against real store |
| Repeated generation attempts | Rate limit, active token cap, and delayed mail handled |
| Invalid or missing CSRF | POST generate/login rejected per policy |
| Disabled account | Cannot sign in against policy |
| Node A generates, node B consumes | Token found and consumed atomically in shared store |
| Successful login | Has Authentication/session; generation redirect alone does not create login |

## 8. Common Mistakes

1. **Assuming Spring sends tokens automatically:** Spring does not know your email/SMS provider; a handler is required.
2. **Using AuthenticationSuccessHandler to send the link:** that runs after login succeeds, not after token generation.
3. **Returning the raw token in the `/ott/generate` response:** the requester could obtain the secret instead of the account owner.
4. **Letting the form specify an arbitrary recipient address:** an attacker requests another user's token and receives it at their own email.
5. **Trusting the Host header to build magic links:** host poisoning can redirect users to an attacker's site.
6. **Failing to prevent user enumeration:** differences in body/status/timing can expose valid account names.
7. **Calling consume immediately after send:** the token is burned before the email ever reaches the user.
8. **Using an in-memory store in a multi-node cluster:** tokens can vanish on restarts or across load-balanced nodes.
9. **No rate limiting:** enables mail bombing, spam, and resource exhaustion.
10. **Testing only with Mockito without testing SMTP, expiry, CSRF, and single-use:** does not prove safe real-world operation.

## 9. Completion Checklist

- [ ] `OneTimeTokenGenerationSuccessHandler` receives the token after generation and properly uses `getUsername()`, `getTokenValue()`, and `getExpiresAt()`.
- [ ] Looks up verified email/SMS from the user directory; never trusts client-supplied addresses.
- [ ] Magic link URL uses a canonical HTTPS origin; protected against Host header poisoning.
- [ ] Token never appears in generation responses, logs, analytics, or external redirects.
- [ ] Returns a generic notice page; anti-enumeration, rate limiting, and email monitoring are in place.
- [ ] CSRF is properly enabled on POST generate/submit, and GET links do not auto-consume.
- [ ] Token expiry/single-use/replay handled by the service; tested expiry and double consume.
- [ ] Shared store if multi-node; tested account status and SMTP outages.
- [ ] Generation success is clearly distinguished from authentication success.

**Conclusion:** `OneTimeTokenService` generates/consumes OTTs; `OneTimeTokenGenerationSuccessHandler` is the **application's responsibility to securely deliver the token to the right account owner**. There is no secure email magic link without verified-contact lookup, URL protection, error handling, and abuse prevention.

## 10. Official Documentation

- Spring Security 6.5 — One-Time Token Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- `OneTimeTokenGenerationSuccessHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/ott/OneTimeTokenGenerationSuccessHandler.html
- `RedirectOneTimeTokenGenerationSuccessHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/ott/RedirectOneTimeTokenGenerationSuccessHandler.html
- `OneTimeToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeToken.html
- `OneTimeTokenService` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html
- Spring Security 6.5 — Servlet CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
