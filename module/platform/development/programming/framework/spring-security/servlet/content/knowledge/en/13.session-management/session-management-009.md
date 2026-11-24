# Session cookies: Secure, HttpOnly, SameSite, path, and lifetime

## 1. Session cookies in Spring Security Servlet

In a **Spring Boot 3.x / Spring Security 6.x application on the Servlet stack**, form login typically relies on **HttpSession**. The server retains session state (potentially including `SecurityContext` and `Authentication`); the browser holds a cookie containing the **session identifier**, defaulting typically to `JSESSIONID` with embedded Tomcat. The browser automatically attaches the cookie on matching requests so the server locates the session again.

~~~text
Browser                              Spring Security + Tomcat
   |                                         |
   | POST /login, credentials + CSRF         |
   |---------------------------------------->|
   |                                         | authenticates user
   |                                         | protects against session fixation
   |                                         | creates/updates HttpSession
   |<----------------------------------------|
   | Set-Cookie: JSESSIONID=<opaque>;        |
   |             Path=/; Secure;             |
   |             HttpOnly; SameSite=Lax      |
   |                                         |
   | GET /private                            |
   | Cookie: JSESSIONID=<opaque>             |
   |---------------------------------------->|
   |                                         | finds still-valid session
   |                                         | applies authorization
   |<----------------------------------------|
   | 200 or redirect/error per policy        |
~~~

`<opaque>` is a placeholder, not a real session ID. **A session ID is a sensitive credential:** anyone obtaining a valid ID can reuse the session unless other mitigations exist. Never print, share, or record real values in logs, URLs, issues, or docs.

Distinctions to make:

| Component | Nature |
| --- | --- |
| `HttpSession` | **Server-side** session, with lifetime, invalidation, and storage |
| Cookie `JSESSIONID` | A reference token held and sent back by the browser to locate the session |
| `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` | Conditions governing how browsers store/send/access the cookie |
| `Max-Age`, `Expires` | Cookie lifetime in the **browser** |
| `server.servlet.session.timeout` | Session inactivity duration on the **server**, not cookie Max-Age |
| Spring Security | Authentication, security context, CSRF, session fixation, authorization, and logout |

The model above applies to **session authentication**. If an API uses Bearer headers or Spring WebFlux, examine the corresponding mechanism; do not copy Servlet configs and assume identical behavior.

## 2. Reading the Set-Cookie header properly

Example:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=example-session; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

`example-session` is purely illustrative. The **`Set-Cookie`** header sent by the server declares the cookie and its attributes. The **`Cookie`** header in requests from the browser normally contains only name/value pairs:

~~~http
GET /private HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=example-session
~~~

Browsers decide whether to send it based on URL, site/origin, expiration, and privacy policy. On non-browser clients, those rules may not be enforced the same way; therefore **cookie attributes do not replace backend authorization**.

| Attribute | Meaning | What must not be misunderstood |
| --- | --- | --- |
| `Secure` | Browser only sends cookie over secure transport, typically HTTPS | Does not set up TLS itself or encrypt the cookie in memory |
| `HttpOnly` | Blocks ordinary JavaScript from reading the cookie via `document.cookie` | Does not neutralize XSS or CSRF |
| `SameSite=Strict` | Blocks many cross-site cookie transmissions | Can break deep links and SSO/callbacks |
| `SameSite=Lax` | Allows same-site and certain safe top-level navigations | Does not replace CSRF tokens; GET can still carry cookies |
| `SameSite=None` | Allows cross-site within browser policies | Requires `Secure`; third-party cookies can still be blocked |
| `Path` | Limits which request paths may send the cookie | Not an access control or strong boundary between untrusted apps |
| `Domain` | Hostname/subdomain scope | Host-only is usually safer than an overly broad Domain |
| `Max-Age` | Relative cookie retention time, **in seconds** on the wire | Does not extend `HttpSession` itself |
| `Expires` | Timestamp when the cookie expires | Subject to clock differences and browser policies |

## 3. Secure: HTTPS and reverse proxies

### 3.1. What does Secure protect?

~~~http
Set-Cookie: JSESSIONID=opaque; Secure; HttpOnly; Path=/
~~~

When `Secure` is set, browsers normally **do not send the cookie over unencrypted HTTP**. On production websites, requiring TLS/HTTPS and configuring `Secure` is fundamental to reducing the risk of exposing session identifiers in transit.

However, `Secure` does not:
- Turn an HTTP site into HTTPS; TLS must be provided by the app/proxy/ingress.
- Guarantee the session ID cannot be stolen via XSS, logs, backups, or infrastructure bugs.
- Encrypt the cookie value on disk or in browser memory.
- Replace HSTS, mixed-content handling, or session fixation protection.
- Act as an authorization mechanism for the backend.

Spring Boot 3 configuration:

~~~properties
server.servlet.session.cookie.secure=true
~~~

Some browsers make exceptions for `Secure` cookies on `localhost`, but **never rely on exceptions when designing production**. If local HTTP cannot retain login, use a separate local profile rather than disabling `Secure` for Internet-facing environments.

### 3.2. External HTTPS, internal HTTP

~~~text
Browser --HTTPS--> Ingress / Reverse proxy --private HTTP--> Spring Boot
                       TLS termination                        Tomcat
~~~

If the proxy terminates TLS, Tomcat may receive plain HTTP requests and not know the browser's public URL is HTTPS. Some redirect URLs, scheme detection, or cookie policies can break as a result.

One option when sitting behind a **controlled proxy**:

~~~properties
server.forward-headers-strategy=framework
server.servlet.session.cookie.secure=true
~~~

`forward-headers-strategy=framework` is **not mandatory** in every deployment. The proxy must **strip and reset** client-supplied `Forwarded`/`X-Forwarded-*` headers, and the backend must restrict untrusted direct access. Trusting attacker-supplied headers can lead to forged schemes/hosts/redirects.

**Verify** on public responses that `Set-Cookie` actually includes `Secure`. Do not just read config files and assume it works.

## 4. HttpOnly: reducing cookie exposure via JavaScript

~~~http
Set-Cookie: JSESSIONID=opaque; HttpOnly; Secure; Path=/
~~~

`HttpOnly` blocks normal JavaScript from reading the cookie value via `document.cookie`:

~~~javascript
console.log(document.cookie);
~~~

A `JSESSIONID` cookie marked `HttpOnly` will not appear through that API. However, an XSS script **can still issue requests** to the same origin with the browser automatically attaching the `HttpOnly` cookie, and then read responses permitted by the same-origin policy. Thus `HttpOnly` **does not replace** XSS defenses, CSP, CSRF protection, authorization, or input validation.

Notes:
- Developer Tools can still display the cookie; that does not mean web JavaScript read it.
- If the session ID is stolen by another route, `HttpOnly` does not invalidate the session.
- Do not disable `HttpOnly` on `JSESSIONID` so an SPA can read the session ID; frontends normally do not need to read that credential.
- A cookie serving a JavaScript-readable CSRF token pattern may have a different policy, which must not be applied to the session cookie.

Property:

~~~properties
server.servlet.session.cookie.http-only=true
~~~

## 5. SameSite: Strict, Lax, None and how it differs from CORS

### 5.1. Site is not the same as origin

An origin is defined by scheme, hostname, and port; a site is typically based on scheme and registrable domain (schemeful SameSite). Therefore:

~~~text
https://app.example.com -> https://api.example.com
  Different origins, yet potentially the same site.

https://app.example.com -> https://external.test
  Different sites.

https://app.example.com -> http://app.example.com
  Under schemeful SameSite, can be treated as different sites.
~~~

**CORS and SameSite are different**. Cross-origin JavaScript needs CORS for credentialed requests if permitted by the backend; yet two different origins can still be same-site. CORS does not automatically prevent CSRF from cross-site HTML forms.

### 5.2. SameSite=Strict

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

The browser may withhold the cookie when a user clicks a link from another site to an already logged-in page, making the app temporarily treat the user as logged out. Email deep links, SSO, OIDC/SAML, or payment callbacks can be impacted. `Strict` fits apps that genuinely need no cross-site cookie navigation and have tested all relevant flows.

### 5.3. SameSite=Lax

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

The browser sends the cookie on same-site requests and **certain top-level cross-site navigations using safe methods**, typically GET when a user clicks a link from another site. Ordinary cross-site POSTs do not carry `Lax` cookies when explicitly declared.

**GET must never perform risky state changes**: if `GET /delete-account` deletes an account, a cross-site top-level link can still carry a `Lax` cookie. Follow HTTP safe-method rules and require CSRF tokens for state-changing operations.

Some browsers apply Lax-by-default when the `SameSite` attribute is **omitted**, with various exceptions. That does not mean every browser always treats an omitted `SameSite` identically to an explicit `SameSite=Lax`.

### 5.4. SameSite=None

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=None
~~~

May be required for iframes or cross-site integrations. Modern browsers require `SameSite=None` to be paired with `Secure`; otherwise the cookie may be rejected. Even with `Secure`, browsers may still block third-party cookies due to tracking prevention, partitioning, and privacy controls.

When using `None` for session authentication, **CSRF must be handled explicitly**; never disable CSRF just to send cookies cross-site. For credentialed CORS, never use wildcard `Access-Control-Allow-Origin: *` to share credentials. Allow only trusted origins while still enforcing authorization, CSRF, and cookie policies.

### 5.5. Choosing SameSite per real flow

| Use case | Consideration | What to test |
| --- | --- | --- |
| Typical web session where users follow links from external sites | `Lax` | CSRF, external links, redirects, and login |
| Internal portal not relying on external navigation | `Strict` | SSO, deep links, and email links |
| App embedded in a cross-site iframe | `None + Secure` | Third-party cookie blocking, CORS, CSRF |
| SPA on one subdomain, API on another subdomain of the same site | Can use `Lax` | Origin, CORS credentials, cookie host/Domain |
| SSO/OIDC/SAML callback | Depends on redirect/binding | GET/POST callbacks and browser behavior |

Spring Boot configuration:

~~~properties
server.servlet.session.cookie.same-site=lax
~~~

Common values are `strict`, `lax`, and `none`. Check your Spring Boot/container version and inspect real responses, especially when Spring Session uses its own cookie serializer.

## 6. Path and Domain: scoping, not authorization

### 6.1. Path

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Browsers typically send the cookie to `/portal` and `/portal/profile`, but not to `/portals` or `/admin`. Cookie Path matching respects `/` segment boundaries rather than matching any arbitrary string starting with `/portal`.

**Path is not a strong security boundary**. You cannot use `Path=/admin` in place of `SecurityFilterChain` or `hasRole("ADMIN")`. Two untrusted apps on the same host still share other cookie, same-origin, and shared-host risks; separate by origin/host and backend policies when needed.

Configuration:

~~~properties
server.servlet.session.cookie.path=/
~~~

For an application mounted under `/portal`, you can use:

~~~properties
server.servlet.context-path=/portal
server.servlet.session.cookie.path=/portal
~~~

If a reverse proxy rewrites paths, the browser only knows the public URL, not the internal servlet path. Ensure `Path` matches the URL the browser calls. Too narrow a `Path` causes “logged in then bounced back to login” bugs because the cookie is not sent to authenticated endpoints.

### 6.2. Domain and host-only cookies

When `Domain` is omitted, the cookie is normally **host-only**. When `Domain=example.com` is set, the cookie can be sent to the domain and matching subdomains. A broad Domain expands cookie exposure and does not by itself create shared login across distinct servers.

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

This header omits `Domain`, suitable when the app only needs the current host. With SPAs/APIs on different origins within the same site, credentials can be sent to the API's own hostname per CORS/credential policy without needing a broad `Domain`.

The `__Host-` cookie name prefix is a browser-enforced hardening measure requiring `Secure`, `Path=/`, and no `Domain`; do not rename the session cookie arbitrarily unless container/proxy/session store are configured consistently.

### 6.3. Cookie deletion must match name/Path/Domain

~~~http
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; Secure; HttpOnly
~~~

A cookie deletion directive must match the scope of the issued cookie. If the original cookie had `Path=/portal` yet logout sends deletion for `Path=/`, the browser may retain the original cookie. Cookies sharing the same name with different Domain/Path values can coexist, complicating debugging.

**Deleting the browser cookie alone is insufficient**: you must invalidate `HttpSession` on the server so a stolen session ID can no longer be replayed.

## 7. Max-Age, Expires, and server session lifetime

### 7.1. Browser session cookie

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Omitting both `Max-Age` and `Expires` creates a browser-session cookie. The browser manages retention under its own rules, which may survive restarts via session restore; closing a single tab does not necessarily erase the cookie.

### 7.2. Persistent cookie

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600
~~~

`Max-Age=3600` over HTTP tells the browser to retain the cookie for roughly **3600 seconds (1 hour)** from receipt. `Expires` is an absolute timestamp, while `Max-Age` typically takes precedence when both are present under modern cookie rules.

**Never set Max-Age=0 to create a browser-session cookie:** `Max-Age=0` is a deletion directive. If you want a session cookie, **omit max-age configuration completely**.

Spring Boot property `server.servlet.session.cookie.max-age=1h` uses duration syntax rather than raw seconds as in the HTTP header. Extending cookie retention **does not automatically extend the server-side session lifetime**.

### 7.3. Server HttpSession idle timeout

~~~properties
server.servlet.session.timeout=20m
~~~

In common Servlet container setups, this is an **idle timeout**: the session expires after roughly 20 minutes of inactivity, depending on repository/container mechanics. Valid requests can refresh last-access time, so this is **not an absolute session lifetime**. If policy requires re-authentication 8 hours after login regardless of activity, implement a separate absolute-expiration policy.

### 7.4. Two independent clocks

~~~text
Cookie: Max-Age = 2h
HttpSession: idle timeout = 20m
After 30 minutes of inactivity:
   Browser may still send the unexpired cookie.
   Server has already expired the session -> user is no longer logged in.

Cookie: browser-session, no Max-Age
HttpSession: idle timeout = 20m
   Browser may still hold the old cookie.
   Server still retains authority to reject the expired session.

Cookie: Max-Age = 10m
HttpSession: idle timeout = 20m
   Browser may stop sending the cookie before server timeout.
   Server must still clean up and revoke per policy.
~~~

`Remember-me` in Spring Security can use a separate cookie/token to auto-relogin when `HttpSession` expires; it has its own lifecycle and risks rather than just setting a huge `JSESSIONID` `Max-Age`.

With **Spring Session Redis/JDBC**, timeouts and storage may be governed by `SessionRepository` and `spring.session.timeout`. Do not assume Tomcat's `server.servlet.session.timeout` property is always the final authority.

## 8. Spring Boot 3 configuration templates per environment

### 8.1. Production HTTPS

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m

# Do not set cookie.max-age -> browser-session cookie.
# Do not set cookie.domain if only a host-only cookie is needed.
~~~

This configuration suits a standard session-based web app at root context served over HTTPS. If multiple apps share a host or Spring Session is used, adjust scoping/serializers accordingly. **Never** copy-paste blindly and assume every SSO/cross-site use case works.

### 8.2. Local HTTP profile for testing only

~~~properties
# src/main/resources/application-local.properties
server.servlet.session.cookie.secure=false
~~~

Enable this profile only in local environments without real data. Production must use HTTPS and `Secure=true`. Keep `SameSite=Lax`; avoid `SameSite=None` with `Secure=false` because many browsers will block it.

### 8.3. Persistent cookie variant (non-default)

~~~properties
server.servlet.session.cookie.max-age=1h
server.servlet.session.timeout=20m
~~~

This keeps the cookie in the browser for up to an hour while the server can expire the session after 20 minutes idle. For remember-me/revocation/rotation, use proper mechanisms rather than `max-age` alone.

### 8.4. Cross-site variant (requires threat model)

~~~properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
~~~

Use only when browsers must send cookies in cross-site contexts and CSRF, CORS, HTTPS, and third-party browser compatibility have been verified.

## 9. Runnable Java 17+ project: form login and observing Set-Cookie

Example uses **Spring Boot 3.3.13**, Spring Security 6, Spring MVC, embedded Tomcat, and Maven. It intentionally creates an `HttpSession` on `GET /session-demo` to observe the cookie; this endpoint is **for learning only** and must not be exposed publicly on the Internet as-is since public session creation can consume resources.

### 9.1. File structure

~~~text
session-cookie-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sessioncookie/
    │   │   ├── SessionCookieApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-local.properties
    └── test/java/com/example/sessioncookie/
        └── SessionCookieIntegrationTest.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>session-cookie-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/com/example/sessioncookie/SessionCookieApplication.java`**

~~~java
package com.example.sessioncookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/sessioncookie/SecurityConfig.java`**

~~~java
package com.example.sessioncookie;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/session-demo", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .deleteCookies("JSESSIONID"))
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Default `formLogin` provides the login page and requires a CSRF token on POST. `logout` is configured to invalidate `HttpSession` and send a `JSESSIONID` deletion directive matching the demo's root path; if changing context path/Domain or using Spring Session, review cookie deletion carefully.

**`src/main/java/com/example/sessioncookie/DemoController.java`**

~~~java
package com.example.sessioncookie;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/session-demo")
    public Map<String, String> createSession(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("demo", "created");
        // Never include session.getId() in the response: session ID is a secret.
        return Map.of("status", "session-created");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

**`src/main/resources/application.properties`**

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m

# DO NOT set server.servlet.session.cookie.max-age.
~~~

**`src/main/resources/application-local.properties`**

~~~properties
# Local HTTP only, never deploy to production.
server.servlet.session.cookie.secure=false
~~~

### 9.2. Integration test observing Set-Cookie from embedded Tomcat

**`src/test/java/com/example/sessioncookie/SessionCookieIntegrationTest.java`**

~~~java
package com.example.sessioncookie;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionCookieIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Test
    void sessionCookieHasExpectedFlags() {
        ResponseEntity<String> response = rest.getForEntity(
            "http://localhost:" + port + "/session-demo", String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();

        String setCookie = response.getHeaders()
            .getFirst(HttpHeaders.SET_COOKIE);
        assertThat(setCookie).isNotBlank();

        String lower = setCookie.toLowerCase(Locale.ROOT);
        assertThat(lower).contains("jsessionid=");
        assertThat(lower).contains("; path=/");
        assertThat(lower).contains("; secure");
        assertThat(lower).contains("; httponly");
        assertThat(lower).contains("; samesite=lax");

        // Browser-session cookie, no Max-Age/Expires.
        assertThat(lower).doesNotContain("max-age=");
        assertThat(lower).doesNotContain("expires=");
    }
}
~~~

This test uses a **real HTTP server and reads the response header**; it does not check whether a browser accepts and sends a `Secure` cookie over HTTP. `secure=true` intentionally emits the `Secure` attribute in `Set-Cookie` even though the embedded test runs over HTTP. To verify real browser behavior, use HTTPS or the `local` profile. If CI activates the `local` profile, the `Secure` flag assertion would differ, so the test runs without that profile by default.

### 9.3. Running Maven and viewing results

Requires Java 17+, Maven, and dependency download access:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Expected result:** tests pass if the project is created completely and the environment matches. The code in this document **has not been executed via Maven here**.

While the server runs, run:

~~~bash
curl -i http://localhost:8080/session-demo
~~~

Expected response:

~~~http
HTTP/1.1 200
Set-Cookie: JSESSIONID=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"status":"session-created"}
~~~

Cookie attribute order and other headers may vary, so the test checks flag presence rather than exact literal header matching.

To log in manually with a browser over **local HTTP**, run the local profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

PowerShell may require quoting the argument `"-Dspring-boot.run.profiles=local"`. Visit `http://localhost:8080/login` with demo user `alice` / `demo-pass`, then open `/private`. The `local` profile sets `Secure=false` strictly for learning; production requires HTTPS and `Secure=true`.

## 10. Inspecting and debugging in the browser

In DevTools **Network**, inspect the response `Set-Cookie`. In **Application/Storage → Cookies**, verify whether the browser accepted the cookie and check its actual attributes. On the next request, inspect whether a `Cookie` header matches the URL, scheme, site, and Path.

Diagnostic steps:

1. Did the server emit `Set-Cookie` with the right name and attributes?
2. Did the browser log a warning rejecting the cookie (`Secure` over HTTP, `SameSite=None` without `Secure`, third-party blocking)?
3. Does the stored cookie have the right Domain/Path to be sent to the endpoint?
4. Did the browser send the cookie on the next request? If yes yet the user remains anonymous, check server-side `HttpSession`.
5. Was the session invalidated, timed out, or routed to another node by a load balancer?
6. After logout, is the old session ID still accepted by the server?
7. With SSO/iframes, inspect the entire redirect/callback chain, not just the first request.

Using `curl -c cookies.txt` writes a cookie jar containing **real session IDs** to disk. Use only in test environments and never share or commit that file. `curl` does not fully simulate browser `SameSite`/third-party behavior.

### Common scenarios

| Symptom | Suspected cause |
| --- | --- |
| Login returns 302 yet browser saves no cookie | HTTPS/Secure mismatch, browser blocked cookie |
| Cookie saved yet not sent to `/portal` | Mismatched Path/Domain/host |
| Cookie sent yet user loses login | Server session expired, different store/node, context not persisted |
| Works locally, fails behind reverse proxy | Scheme/forwarded headers or path rewrite |
| Clicking link from email does not open already logged-in page | `SameSite=Strict` on cross-site navigation |
| Cross-site iframe loses login | `SameSite` Lax/Strict or third-party restrictions |
| Browser still holds cookie after idle timeout | Browser cookie lifetime differs from `HttpSession` TTL |
| Still accessible with old ID after logout | Server did not invalidate session, or remember-me/another token exists |

## 11. Coordinating with Spring Security: fixation, CSRF, logout

**Session fixation protection:** If an attacker tricks a browser into using a pre-known session ID, keeping that same ID after login can be dangerous. Spring Security session authentication typically defends by rotating the session ID at login depending on the mechanism; custom logins must invoke `SessionAuthenticationStrategy` and save the security context properly.

~~~text
Before login: JSESSIONID=A (not yet authenticated)
After login:  JSESSIONID=B (authenticated, ID rotated)
~~~

This illustrates the protection policy, not a guarantee that every authentication type always rotates IDs.

**CSRF:** Session cookies are attached automatically by browsers. `SameSite=Lax` helps reduce CSRF risk but **does not replace CSRF tokens**, especially when GET is allowed in certain cross-site navigations or browser policies change. Spring Security Servlet normally enables CSRF by default; do not disable it just because an endpoint returns JSON if authentication still relies on session cookies.

**Logout:** Must invalidate `HttpSession` on the server, clear the security context, send cookie deletion matching Path/Domain, and handle remember-me/SSO/other refresh tokens. Clearing the browser cookie without invalidating the server session does not prevent replay of a stolen identifier.

**Cross-site APIs:** Do not arbitrarily disable CSRF because an API is REST. If browsers send cookies automatically for authentication, CSRF must be evaluated separately. CORS, `SameSite`, and CSRF serve distinct roles.

## 12. Spring Session and multiple servers

With default Tomcat, `HttpSession` normally lives on a single instance. If a load balancer routes a request to a node unaware of the session, the user can be bounced back to login even though the cookie is intact. Using **Spring Session Redis/JDBC** or a shared session store solves multi-instance session management, but TTL, security, cookie serializers, and logout must be configured consistently.

Spring Session may use cookie name **`SESSION`** instead of `JSESSIONID`. Do not hardcode tests/middleware to Tomcat's default cookie name. Check `spring.session.timeout`, the session repository, cookie name, `SameSite`/`Secure`/`HttpOnly`/`Path`/`Domain`, and actual cookie deletion; `server.servlet.session.cookie.*` properties may no longer be the sole control source.

Behind a TLS-terminating proxy, the backend must trust `Forwarded` headers **only from trusted sources**. When changing context paths or domains, verify both public URLs and cookie scoping rather than adjusting Spring Security rules alone.

## 13. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| `Secure` encrypts cookies stored on the user's machine | `Secure` controls sending cookies over HTTPS/secure transport |
| `HttpOnly` makes the app immune to XSS/CSRF | Only blocks ordinary JS from reading the cookie directly |
| `Strict` is always better than `Lax` | `Strict` can break deep links and SSO |
| `Lax` replaces CSRF tokens | No: top-level GETs and many other scenarios still need CSRF protection |
| `None` guarantees iframe login works | Requires `Secure`; browsers may still block third-party cookies |
| `Path` is an authorization layer | `Path` only filters where the browser sends cookies |
| Broad `Domain` automatically creates SSO | Shared cookies do not mean shared server-side sessions |
| No `Max-Age` means closing a tab deletes the cookie | Browser-session cookies can survive via session restore |
| `Max-Age=0` means never expires | It is usually a cookie-deletion directive |
| Session `timeout=20m` means browser deletes cookie after 20m | That is the server-side idle timeout |
| Deleting the cookie is enough for logout | Must invalidate the session on the server |
| Spring Session always uses `JSESSIONID` | Cookie name/serializer may differ |
| HTTPS proxy always makes `Secure` cookies work automatically | Must configure and test actual `Set-Cookie` |

## 14. Implementation checklist

1. Enable HTTPS in production, with `Secure=true` and `HttpOnly=true` on session cookies.
2. Choose `SameSite` per flow: standard web logins can use `Lax`; test SSO/iframes/cross-site callbacks.
3. Keep cookies host-only unless a broad domain is required, and set `Path` to match public URLs.
4. Never set `Max-Age=0` to create a browser-session cookie; omit `Max-Age`/`Expires` for browser-session lifetime.
5. Define server idle timeout and, if needed, a separate absolute session lifetime.
6. Keep CSRF protection for cookie-based auth, defend against XSS, and enforce authorization.
7. Defend against session fixation at login, invalidate the server session at logout, and delete cookies with matching scope.
8. If using Spring Session/multi-node, verify repository/TTL/cookie serializer/rotation.
9. Test in real browsers, not solely via `curl` or properties files.
10. Never log or share session IDs; if cookie/session compromise is suspected, revoke first then investigate.

## 15. Self-check questions

**1.** What does `Secure` do, and does it replace HTTPS?

**Answer:** `Secure` restricts browsers from sending cookies over insecure connections. It does not provide HTTPS itself and does not protect cookies stolen elsewhere.

**2.** Why does `HttpOnly` not prevent all CSRF/XSS?

**Answer:** It prevents JavaScript from reading the cookie directly, yet browsers still attach cookies automatically, and XSS scripts can still issue same-origin requests.

**3.** How do `SameSite` `Strict` and `Lax` differ when a user clicks a link from another site?

**Answer:** `Strict` normally withholds cookies on initial cross-site navigation; `Lax` can send them on safe top-level navigations such as GET.

**4.** Why might a browser reject `SameSite=None`?

**Answer:** Modern browsers require `Secure`, and third-party/privacy restrictions can still block it.

**5.** Does `Path=/portal` automatically require `ROLE_ADMIN` on `/portal/admin`?

**Answer:** No. `Path` only selects URLs that receive the cookie; authorization is Spring Security/server's job.

**6.** Does `server.servlet.session.timeout=20m` force the browser to delete `JSESSIONID` after exactly 20 minutes?

**Answer:** No. It is a server idle timeout; browser cookies have their own lifecycle.

**7.** Why must `Max-Age=0` not be used to “create a cookie lasting only for the browser session”?

**Answer:** `Max-Age=0` normally instructs the browser to delete the cookie immediately. For a session cookie, omit `Max-Age`/`Expires`.

**8.** After logout, the client deletes `JSESSIONID` while the server does not invalidate the session. Is it secure?

**Answer:** No. An exposed old session ID can continue to be used; server-side revocation/invalidation is mandatory.

**9.** With Spring Session Redis, is the cookie name guaranteed to be `JSESSIONID`?

**Answer:** No. Cookie name, serializer, TTL, and controlling properties can differ; inspect actual `Set-Cookie` and the repository.

**10.** Why can an app behind an HTTPS reverse proxy still emit cookies incorrectly?

**Answer:** The backend may only see an internal HTTP scheme; explicit `Secure` policies and forwarded headers from trusted proxies are required.

**Takeaway:** **`Secure` controls transport, `HttpOnly` restricts JavaScript cookie reading, `SameSite` governs cross-site sending, `Path`/`Domain` bound scope, and `Max-Age`/`Expires` determine browser cookie lifetime. `HttpSession` has its own server-side idle timeout and invalidation.**