# Configuring Secure, HttpOnly, SameSite, and Session Cookie Expiration

## 1. Context: What Role Does a Session Cookie Play in WebFlux?

A Spring WebFlux application can create a `WebSession` to maintain state across HTTP requests. The server manages the session data, while the browser typically holds a **cookie containing the session ID**. With Spring Security Reactive, certain interactive authentication mechanisms, CSRF tokens, or business components may use `WebSession`. Therefore, session cookie configuration is part of **session and logout** design, not merely HTTP header decoration.

A response may include:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=opaque-session-id; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

Where:
- `SESSION=opaque-session-id` is the **session identifier**, not the password itself, user object, or permissions.
- `Secure` restricts sending the cookie over unencrypted connections (typically HTTPS only).
- `HttpOnly` restricts page JavaScript from reading the cookie via `document.cookie`.
- `SameSite` governs cookie transmission in same-site/cross-site request scenarios.
- `Max-Age` is the **browser-side cookie** lifetime.
- `server.reactive.session.timeout` governs the **server-side WebSession** idle timeout, which is not equivalent to `Max-Age`.

These attributes **do not replace** authentication, authorization, CSRF protection, XSS protection, HTTPS, or invalidating the session upon logout. They are distinct control layers.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish the session cookie from `WebSession` and the security context.
2. Choose `Secure`, `HttpOnly`, and `SameSite=Strict/Lax/None` based on browser flows.
3. Understand `Max-Age` / `Expires`, session cookies, `maxIdleTime`, and absolute session lifetime.
4. Configure **Spring Boot Reactive** properly via `server.reactive.session.*`; avoid confusing it with Servlet configuration.
5. Customize `CookieWebSessionIdResolver` when special requirements apply.
6. Write a Java 17+ WebFlux + Spring Security Reactive example with CSRF tokens, cookie flags, and session invalidation.
7. Inspect `Set-Cookie`, test timeout/invalidation, and understand how Spring Security logout differs from merely deleting a cookie.
8. Identify risks when setting cookie `Domain`/`Path`, running HTTPS behind a reverse proxy, using `SameSite=None`, or equating client-side TTL with login lifetime.

## 2. A Session Has Two Sides: ID Cookie and Server Data

Conceptual flow:

~~~text
Browser                                       Spring WebFlux server
   |                                                  |
   | POST /session/start (+ CSRF, authentication)     |
   |------------------------------------------------->|
   |                         WebSession created/started|
   |                         Session store saves data |
   |                                                  |
   | Set-Cookie: SESSION=<opaque-id>; ...             |
   |<-------------------------------------------------|
   |                                                  |
   | GET /session/state                               |
   | Cookie: SESSION=<opaque-id>                      |
   |------------------------------------------------->|
   |                         Look up session by ID    |
   |                         Read stored data         |
   |                                                  |
   | 200 + session state                              |
   |<-------------------------------------------------|
~~~

The cookie only needs to contain an **unpredictable ID**; it does not need to contain the entire profile or `SecurityContext`. This has two consequences:

- If an attacker captures an **active session ID** and the server accepts it, they may be able to **hijack the session** in a session-based login design. Thus, the cookie must be protected in transit, in storage, in logs, and upon expiration.
- If the server has **invalidated/expired** the session, a lingering old cookie **does not resurrect** deleted data. The browser may continue sending the old ID while the cookie remains alive, yet the server must reject it or treat it as an invalid session.

### 2.1. WebSession differs from SecurityContext

| Component | Responsibility |
| --- | --- |
| `WebSession` | Holds session ID, attributes, creation/access time, idle timeout, and WebFlux session lifecycle |
| `WebSessionStore` / Spring Session | Stores/retrieves session data in memory, Redis, or another configured store |
| `CookieWebSessionIdResolver` | Writes/reads the **session ID cookie** from request/response |
| `ServerSecurityContextRepository` | Strategy to load/save **SecurityContext** for Spring Security Reactive |
| `WebSessionServerSecurityContextRepository` | An implementation that stores `SecurityContext` in `WebSession` |
| `NoOpServerSecurityContextRepository` | Does not save/load `SecurityContext` via repository across requests |
| `ReactiveSecurityContextHolder` | Allows downstream code to read the security context of the current reactive subscription |
| `ServerCsrfTokenRepository` | Manages CSRF tokens; may use `WebSession` separately |

Not every application with a `SESSION` cookie uses **session login**. For example, an API using Basic auth on every request can still create a `WebSession` just to hold a CSRF token or other data. Conversely, a stateless JWT API might create no `WebSession` at all, even though Spring Security still populates a `SecurityContext` for the current request.

Cookie flags are a policy at the **ID transport layer**. Logout must handle both the validity of **server-side session data** and the appropriate authentication state.

## 3. The Secure Attribute

`Secure` instructs the browser not to send the cookie over unencrypted HTTP connections; the cookie is sent in appropriate HTTPS contexts. This is an essential control to avoid leaking the session ID over unencrypted transport.

Example:

~~~http
Set-Cookie: SESSION=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Do not confuse `Secure` with encrypting the cookie.** The cookie value remains a plain data string; TLS protects the transport channel during HTTPS connections. `Secure` does not stop same-origin JavaScript from using the browser to send requests with the cookie, does not prevent XSS, does not replace HSTS, and does not guarantee the server handles sessions properly.

### 3.1. Production configuration

In Spring Boot for WebFlux:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: true
~~~

For production, provide end-to-end HTTPS along appropriate trust boundaries, use HSTS when the system is ready, and configure TLS termination/reverse proxies consistently. If TLS terminates at a load balancer and HTTP runs on the internal network, that still needs to be a controlled network and trust path; avoid exposing the application to the Internet over plain HTTP.

**Caution with reverse proxies:** if the framework infers security from the request scheme and the reverse proxy misreports it, the cookie may lack `Secure`. Explicitly setting `secure: true` for production reduces reliance on that inference. If processing `Forwarded` or `X-Forwarded-*`, trust only headers normalized by a **trusted proxy**; never accept forged values directly from clients.

### 3.2. Local HTTP: why is a separate profile needed?

Local demos at `http://localhost:8080` typically lack TLS. If cookies always have `Secure` enabled, browsers/tools may not send the cookie as expected in HTTP flows; some browsers make an exception for localhost, yet tests should not be built around that exception.

A clear verification approach is:
- **Production:** `secure: true` and mandatory HTTPS.
- **Local HTTP profile:** `secure: false` solely for experimentation.
- **Production testing:** verify `Set-Cookie` includes `Secure` on HTTPS responses/suitable mock environments.

Never copy a local profile to public environments or disable `Secure` to "work around" a production proxy bug.

## 4. The HttpOnly Attribute

`HttpOnly` tells the browser not to allow ordinary JavaScript APIs such as `document.cookie` to read the cookie value. This helps reduce the chance of the session ID being stolen directly by malicious script running on the page.

Example:

~~~http
Set-Cookie: SESSION=opaque-id; Path=/; Secure; HttpOnly
~~~

**What HttpOnly DOES NOT do:**
- It does not stop the browser from automatically sending the cookie with valid HTTP requests.
- It does not stop same-origin JavaScript from calling `fetch("/api/transfer", ...)`, causing the browser to attach the cookie.
- It does not replace XSS prevention: a malicious script can still perform unauthorized actions without reading the cookie.
- It does not solve CSRF: another site can trigger requests and the browser may attach the cookie if SameSite/CSRF policies do not block it.
- It does not encrypt or sign the cookie.

**Recommendation:** cookies holding a login session ID should set `HttpOnly=true`. If an SPA needs to read a CSRF token from a separate cookie, there are cases where the **CSRF token cookie** requires `HttpOnly=false` by design. That **does not** mean disabling `HttpOnly` on the **session ID cookie**.

## 5. The SameSite Attribute: Strict, Lax, and None

`SameSite` signals to the browser whether to send the cookie when a request originates in a **cross-site** context. It reduces the surface for certain cookie-based CSRF attacks, yet **it is not an access control mechanism** and does not replace CSRF tokens when the threat model demands them.

| Value | High-level browser behavior | When appropriate | Risks / trade-offs |
| --- | --- | --- | --- |
| `Strict` | Restricts sending the cookie on cross-site requests | Internal/sensitive apps, flows not needing cookies when arriving from another site | Users arriving via links/email/IdP redirects may temporarily "lose session" |
| `Lax` | Allows certain top-level cross-site navigations with safe methods, typically GET; restricts many cross-site POSTs/subresources | Many traditional websites balancing protection and navigation | Does not block all CSRF; GET must have no side effects |
| `None` | Allows sending the cookie in cross-site contexts per browser policy | Approved cross-site needs, e.g. certain embeddings/SSO | **Must include Secure** in modern browsers; may still be blocked by third-party cookie policies |

**Same-site differs from same-origin.** Two subdomains have different origins yet can belong to the same site under browser definitions. Therefore, `SameSite` does not replace origin checks, CORS, CSRF tokens, subdomain isolation, or application isolation policies.

### 5.1. Intentional default choice

For a typical browser application:
- Start evaluating with `SameSite=Lax`.
- If high security is required and login/session is not needed in cross-site flows, consider `Strict`.
- Only use `None` when cross-site flows are genuinely required; in that case, `Secure=true`, HTTPS, and CSRF/CORS controls must be carefully engineered.
- Do not rely on "browser defaults". Explicitly declare the policy your product supports and inspect real responses.

When using OAuth2/OIDC Login or SSO via redirects/cross-site POSTs, test the cookies required for `state`/`nonce` and IdP flows. Unplanned `Strict` or `SameSite` changes can break authentication. Different cookies may need different policies; do not force every cookie into one rule if actual flows differ.

### 5.2. Does SameSite replace CSRF tokens?

No. Specifically:
- `Lax` still permits certain cross-site navigational requests; a GET endpoint with side effects is a serious bug.
- Origins on the same site but different subdomains may fall outside the protection scope you expect.
- Browser behaviors, exceptions, and login architectures vary.
- With `SameSite=None`, cookies can be sent in even more cross-site contexts.
- XSS on a trusted origin can send requests with the user's privileges.

Spring Security WebFlux provides `CsrfWebFilter` and `ServerCsrfTokenRepository` to protect unsafe HTTP methods if the application uses authentication credentials sent automatically by the browser.

## 6. Domain, Path, Name, and Cookie Prefixes

Beyond the three core flags, the scope of a session cookie must be constrained.

- `Domain`: if omitted, the cookie is normally **host-only**, reducing unintended sharing with subdomains. Setting `Domain=.example.test` opens the scope to multiple subdomains; the leading dot generally has no special security meaning in modern browsers.
- `Path`: restricts the URL paths for which the browser sends the cookie. `Path` **is not** a strong authorization/security boundary between apps sharing a host; do not use it in place of authentication and authorization.
- `Name`: WebFlux typically uses `SESSION` for the session cookie, though it can be changed. Do not confuse it with `JSESSIONID` commonly seen in Servlet apps.
- `__Host-` prefix (when deliberately used): requires `Secure`, `Path=/`, and **no `Domain`**, binding the cookie more tightly to the host on supporting browsers.
- `__Secure-` prefix: requires `Secure`, without automatically imposing the `Path`/`Domain` constraints of `__Host-`.

Do not set a broad `Domain` merely because frontend and API live on different subdomains: serving auth endpoints on the same host or using a BFF design can reduce the need to share session cookies. If cross-origin is genuinely needed, handle CORS, `credentials`, and CSRF explicitly.

**Warning on "cookie shadowing":** two cookies with the same name but different `Domain`/`Path` can be sent by the browser simultaneously. The app or proxy may pick the unintended cookie. When changing scope/name, plan for clearing stale cookies and verify exact request headers.

## 7. Max-Age, Expires, Session Cookies, and Server Expiration

There are **at least two independent clocks**:

1. **Browser-side cookie lifetime**: `Max-Age` / `Expires` controls how long the browser keeps and sends the ID.
2. **Server-side session validity**: `WebSession.getMaxIdleTime()` or store configuration determines how much inactivity passes before the session is considered expired.

**Do not equate them.** A cookie may still be valid in the browser while the server has already deleted the session. Conversely, the server may still retain session data while the browser has deleted the cookie, leaving the client without the ID to reach it.

### 7.1. Max-Age and Expires

- `Max-Age=1800` instructs the cookie to last 1,800 seconds from issuance/setting per browser handling.
- `Max-Age=0` normally tells the browser to delete the cookie.
- A negative or omitted `Max-Age` indicates a **session cookie**, usually cleared when the browser session ends; browser session restore can keep cookies alive depending on the browser.
- `Expires` is an absolute client-side timestamp.
- When both `Max-Age` and `Expires` are present, `Max-Age` takes precedence under modern cookie standards.

A "session cookie" (with no fixed browser expiration) **differs from** "a server session valid only until the tab closes". Browsers may restore sessions, and servers have their own timeouts. Do not rely on "closing the browser" as a reliable logout mechanism.

### 7.2. Idle timeout

In Spring WebFlux:

~~~java
// Illustrative API:
WebSession session = ...;
session.setMaxIdleTime(Duration.ofMinutes(10));
Duration maxIdleTime = session.getMaxIdleTime();
~~~

`maxIdleTime` is the maximum inactivity period between accesses for which the session remains valid according to the store. It is not an "absolute lifetime since login" regardless of activity.

Example:
- 10:00 server saves the session.
- 10:08 browser sends a request with the valid session ID: last access time is updated per the session store mechanism.
- 10:15 the session can still be valid since only 7 minutes elapsed since last access, if idle policy = 10 minutes.
- If no further access happens by 10:30, the server can treat the session as expired; exact physical deletion timing depends on the store/cleanup.

Do not treat the physical cleanup time in Redis/database as the sole proof of when the session **stopped being accepted**.

### 7.3. Absolute expiration is a separate policy

Many systems need a hard cap from login time, such as 8 hours regardless of user activity. `server.reactive.session.timeout` normally represents an **idle timeout**, not an automatic absolute lifetime.

Achieving an absolute lifetime requires a dedicated mechanism: storing a session/login creation timestamp, enforcing the policy on each request and invalidating when exceeded, or using a session/token system supporting corresponding absolute TTLs. When using refresh/remember-me, distinguish the lifetimes of the session, cookie, refresh token, and access token.

### 7.4. Why is Max-Age not the authentication lifetime?

Example:
- Cookie `Max-Age=30m`.
- `WebSession` idle timeout = 10m.
- Browser does not use the session for 11 minutes.

The browser may still send the cookie ID, yet the server considers the session expired. Proper behavior is to require re-authentication or start a fresh session per policy—**never** accept stale authentication data just because the cookie's `Max-Age` has not elapsed.

Conversely, increasing cookie `Max-Age` does not extend the server-side `WebSession` lifetime. Any statement about "login duration" must specify which clock is being referenced.

## 8. Configuring Spring Boot Reactive via application.yml

Spring Boot provides the **`server.reactive.session.*`** property group for WebFlux applications. Here is a concrete policy example for study:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
        max-age: 30m

spring:
  application:
    name: secure-session-cookie-demo
~~~

Meaning:
- `timeout: 10m`: 10-minute `WebSession` idle timeout.
- `cookie.max-age: 30m`: browser keeps the cookie up to 30 minutes per cookie rules, **not** a 30-minute server session.
- `secure: true`: only send the cookie in an appropriate secure context; production requires HTTPS.
- `http-only: true`: blocks reading the session ID from ordinary JavaScript.
- `same-site: lax`: restricts some cross-site requests while supporting top-level navigation flows.
- `path: /`: cookie is sent for requests across the whole host per `Path`; use only when intended.
- `name: SESSION`: cookie name, not a specific ID or value.

**The 10m and 30m values are illustrative only**; production systems must select timeouts based on risk, usage patterns, data sensitivity, user supportability, and internal compliance.

### 8.1. Right Reactive namespace, not Servlet

In WebFlux:

~~~properties
server.reactive.session.timeout=10m
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
server.reactive.session.cookie.max-age=30m
~~~

Do not use `server.servlet.session.cookie.*` expecting to configure WebFlux's `WebSession`. The Servlet namespace belongs to Servlet/MVC applications; even under Spring Boot, the two stacks use different session types and components.

### 8.2. Local profile for running HTTP on a personal machine

Create `src/main/resources/application-local.yml`:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: false
~~~

Run with the `local` profile **only when testing over localhost HTTP**. In staging/production environments, HTTPS must be used with `secure: true`, and the `local` profile must never be activated outside developer machines.

**Configuration precedence:** profile-specific properties override values in `application.yml`. After deploying, always inspect the actual `Set-Cookie` header, because a custom `WebSessionIdResolver` bean or Spring Session integration can alter behavior.

### 8.3. Other properties

Spring Boot Reactive also offers options such as `cookie.domain`, `cookie.path`, and `cookie.name`. Do not set `Domain` if only host-only is needed. Never include private data or user information in the cookie name.

When using Spring Session (e.g., Redis), check the specific documentation/configuration because the session store, expiration, and cookie ID resolver may be configured by Spring Session itself. Session configuration for Servlet Redis and Reactive Redis **are not the same instructions**.

## 9. Java Configuration via CookieWebSessionIdResolver

In a plain Spring WebFlux application or when a custom resolver policy is needed, you can define a `WebSessionIdResolver` bean:

~~~java
// Illustrative configuration snippet to place in a separate @Configuration.
// Do not add this bean alongside the Boot example if only property binding is needed.

@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

    resolver.setCookieName("SESSION");
    resolver.setCookieMaxAge(Duration.ofMinutes(30));

    resolver.addCookieInitializer(builder ->
            builder.path("/")
                   .secure(true)
                   .httpOnly(true)
                   .sameSite("Lax"));

    return resolver;
}
~~~

Required imports when placing in a class:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;
~~~

`setCookieMaxAge` controls the `Max-Age` of the session ID cookie; `addCookieInitializer` lets you configure `ResponseCookie` attributes. It **does not** mean `setCookieMaxAge(Duration.ofMinutes(30))` changes `WebSession.getMaxIdleTime()`.

If declaring a resolver bean, do not simultaneously expect other `server.reactive.session.cookie.*` properties to override it without checking headers: in many setups, a custom bean replaces the auto-configured resolver. Pick one clear source of configuration and verify actual header output.

## 10. Runnable Java 17+ Demo: Session Cookie, CSRF, and Invalidation

This example runs on **Spring Boot 3.5.7, Java 17, Gradle**, Spring WebFlux, and Spring Security Reactive. It demonstrates creating/using/deleting a `WebSession`, while making clear that **HTTP Basic is re-verified on every request** in the example and is not stored in `WebSession`.

We deliberately use:
- HTTP Basic with a mock user for protected endpoints.
- `NoOpServerSecurityContextRepository` so authentication is not saved across requests.
- Default CSRF protection for POST.
- `WebSession` holding only a `demoActive` marker and the CSRF token.
- Cookie flags in `application.yml`.
- `POST /demo/session/end` to call `WebSession.invalidate()`.

Hence this is a **cookie/session lifecycle demo**, not a full form-login session authentication example. A later section explains Spring Security logout.

Structure:

~~~text
secure-session-cookie-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── SessionController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-local.yml
    └── test/java/demo/
        └── SessionCookieTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'secure-session-cookie-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-webflux` provides WebFlux/Netty by default, `spring-boot-starter-security` adds the security chain, and `spring-security-test` supports CSRF testing and authentication mocks.

Spring Boot 3.5.7 is a real version used to illustrate the API. For production projects, always upgrade to a supported branch with approved security patches; do not treat choosing this illustrative version as a recommendation to pin it forever.

### 10.2. Two cookie configuration files

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
        max-age: 30m
~~~

`src/main/resources/application-local.yml`:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: false
~~~

Do not change `http-only: true` in the local profile: JavaScript has no reason to read the **session ID**. Local only disables `Secure` because the lab uses localhost HTTP.

### 10.3. DemoApplication

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. Security configuration: Basic auth without saving authentication to WebSession

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

Explanation:
- Every demo endpoint requires Basic authentication, including the endpoint issuing CSRF tokens.
- `NoOpServerSecurityContextRepository` does not retain `SecurityContext` for the next request. `WebSession` itself can still exist for the marker/CSRF.
- `csrf(Customizer.withDefaults())` keeps CSRF protection active for POST.
- `{noop}` is only for local learning; in real products use a strong `PasswordEncoder` and secure user/password management.
- The demo uses HTTP Basic rather than a login form to avoid implementing a form-login sequence inside the same example. Clearing `WebSession` **does not** make the browser forget HTTP Basic credentials.

### 10.5. Controller with start/state/end and token

`src/main/java/demo/SessionController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    @GetMapping(path = "/demo/session/state",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> state(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> Boolean.TRUE.equals(
                        session.getAttribute("demoActive"))
                        ? "active" : "absent");
    }

    @PostMapping(path = "/demo/session/start",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> start(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    session.getAttributes()
                            .put("demoActive", Boolean.TRUE);
                    return "started";
                });
    }

    @PostMapping(path = "/demo/session/end",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> end(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(WebSession::invalidate)
                .thenReturn("ended");
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is unavailable"));
        }

        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "token", value.getToken()));
    }
}
~~~

**Lifecycle explanation:**
- `state` only checks the marker. If the session lacks the marker, it returns `absent`. It does not try to create a login session.
- `start` adds the `demoActive` attribute. Under the `WebSession` contract, adding an attribute marks the session as started; the framework saves it when the response commits, so a session ID cookie can be emitted.
- `end` calls `invalidate()` and waits for the `Publisher` to complete before returning `ended`. Never manually clear a cookie string to pretend to log out.
- `csrf` reads the `Mono<CsrfToken>` provided by the security filter via exchange attribute. In Spring Security 6.x, the emitted token may be masked by the request handler; the client must send back the exact issued value.
- There is no `block()` or manual `subscribe()` in the WebFlux controller.

**This is not yet "logging out of HTTP Basic"** because Basic credentials live in the browser/client. `end` only deletes the illustrative `WebSession`; endpoints still require Basic credentials on new requests. For real account logout with session-based authentication, configure Spring Security Logout and invalidate the corresponding authentication/session.

## 11. Running the Demo and Inspecting Set-Cookie

Run in the directory containing `build.gradle`:

~~~bash
gradle bootRun --args='--spring.profiles.active=local'
~~~

With the Gradle Wrapper, replace `gradle` with `./gradlew` on Linux/macOS or `gradlew.bat` on Windows. The command uses localhost HTTP, so the **local profile** disabled `Secure`. In production, this profile will not be used.

Open another terminal with `curl` and `jq`:

~~~bash
# 1. GET /csrf: fetch token and save WebSession cookie to jar.
curl -i -u learner:localpass \
  -c session-cookies.txt \
  http://localhost:8080/csrf

# 2. Save JSON token to file + update cookie jar.
curl -sS -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# 3. Prepare header name + token issued by server.
HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# 4. Start demo session with CSRF token and current cookie jar.
curl -i -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST http://localhost:8080/demo/session/start

# 5. Read state stored in WebSession.
curl -i -u learner:localpass \
  -b session-cookies.txt \
  http://localhost:8080/demo/session/state

# 6. Invalidate WebSession, still sending Basic + CSRF token.
curl -i -u learner:localpass \
  -b session-cookies.txt -c session-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST http://localhost:8080/demo/session/end

# 7. New request: session marker is gone.
curl -i -u learner:localpass \
  -b session-cookies.txt \
  http://localhost:8080/demo/session/state
~~~

**Expected results while cookie/token are valid:**

| Operation | HTTP | Result |
| --- | --- | --- |
| GET `/csrf` with valid Basic | `200 OK` | JSON containing `headerName`, `token`; may emit session cookie when token is saved |
| POST `/demo/session/start` with CSRF + Basic | `200 OK` | Body `started` |
| GET `/demo/session/state` with same cookie | `200 OK` | Body `active` |
| POST `/demo/session/end` with CSRF + Basic | `200 OK` | Body `ended` |
| GET `/demo/session/state` after invalidate | `200 OK` | Body `absent` |

**Why does it still return 200 after invalidate?** Because the example requires Basic on **every** request; the client still passes `-u learner:localpass`. That is fresh per-request authentication, **not** the old `WebSession` still being valid. The `demoActive` marker is gone, fulfilling the experiment's goal.

### 11.1. Inspecting the local cookie

In the local profile, the header may look like:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Max-Age=1800; HttpOnly; SameSite=Lax
~~~

`Secure` **does not appear** because the local profile sets `secure: false`. Session ID values are random, with no fixed stdout value. Header formatting and attribute order may vary; inspect with a cookie parser or search for expected attributes rather than exact full-string matching.

### 11.2. Inspecting the production configuration

In HTTPS tests or production without the local profile active, the cookie must include `Secure`:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

If `Max-Age=1800` is set while server idle timeout is 10 minutes, do not conclude "the user stays logged in for 30 minutes". Those are two different clocks.

### 11.3. Missing CSRF token on POST

Try:

~~~bash
curl -i -u learner:localpass \
  -b session-cookies.txt \
  -X POST http://localhost:8080/demo/session/start
~~~

With default CSRF protection, a POST without a valid token normally receives **403 Forbidden**, even with valid HTTP Basic. Never disable CSRF to "fix" 403 in browser applications.

### 11.4. Note on Windows PowerShell environment

Commands containing `$(jq ...)` use Bash shell syntax; on Windows PowerShell they do not work directly like that. You can use WSL/Git Bash or PowerShell `ConvertFrom-Json` to extract the two JSON fields. The lesson content is OS-independent, though shell syntax must match your actual terminal.

Never use real credentials in shell history or logs. Only use demo user/password values on a personal machine to observe behavior.

## 12. Testing Cookie Flags with WebTestClient

`WebTestClient` combined with `spring-security-test` can inspect WebFlux application responses without needing a browser. The test below deliberately uses the default profile (`application.yml`, `Secure=true`), not the local profile, to verify production cookie configuration.

`src/test/java/demo/SessionCookieTest.java`:

~~~java
package demo;

import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionCookieTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void sessionCookieHasIntendedSecurityAttributes() {
        EntityExchangeResult<String> result =
                client.mutateWith(csrf())
                        .post().uri("/demo/session/start")
                        .headers(h -> h.setBasicAuth(
                                "learner", "localpass"))
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(String.class)
                        .isEqualTo("started")
                        .returnResult();

        List<String> setCookieValues = result.getResponseHeaders()
                .get(HttpHeaders.SET_COOKIE);

        assertTrue(setCookieValues != null
                && !setCookieValues.isEmpty());

        String cookie = setCookieValues.stream()
                .filter(value -> value.startsWith("SESSION="))
                .findFirst().orElseThrow();

        String lower = cookie.toLowerCase(Locale.ROOT);
        assertTrue(lower.contains("secure"));
        assertTrue(lower.contains("httponly"));
        assertTrue(lower.contains("samesite=lax"));
        assertTrue(lower.contains("max-age=1800"));
        assertTrue(lower.contains("path=/"));
    }

    @Test
    void stateEndpointRejectsAnonymousRequest() {
        client.get().uri("/demo/session/state")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void startWithoutCsrfIsForbidden() {
        client.post().uri("/demo/session/start")
                .headers(h -> h.setBasicAuth(
                        "learner", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expectation:** the tests verify `Secure`, `HttpOnly`, `SameSite=Lax`, `Max-Age=1800`, `Path=/`, along with matching 401/403 results. The `SESSION` values in `Set-Cookie` are not compared against a fixed string because session IDs are random. This is instructional test code, **not a claim that tests were run on the learner's machine**.

**Limitations of mock unit/integration tests:** seeing `Secure` in tests does not prove the production reverse proxy serves HTTPS properly, nor do tests prove browsers send cookies per `SameSite` in every scenario. Real network/browser testing, TLS termination, and cookie policies must be verified in the deployment environment.

If a Spring Session environment swaps the resolver or cookie writer, tests may show different behavior: that is why you should inspect `Set-Cookie` on the **actual deployed application**, not just read YAML.

## 13. Session Timeout, Runtime Override, and Logout

### 13.1. Changing idle timeout for an individual WebSession

If a business flow wants a session to have a shorter idle time than the default:

~~~java
// Illustrative snippet inside a reactive handler:
return exchange.getSession()
        .map(session -> {
            session.setMaxIdleTime(Duration.ofMinutes(5));
            session.getAttributes().put("sensitiveFlow", Boolean.TRUE);
            return "started-sensitive-flow";
        });
~~~

Import `java.time.Duration`; this is a snippet inside a request-handling method, not a standalone Java class. Adjusting the session's `maxIdleTime` does not alter the `Max-Age` of an already issued cookie and does not create an absolute timeout.

### 13.2. Logout must handle both server and client

In **session-based authentication**, proper logout typically:
1. Validates the logout request, with CSRF protection as required.
2. Clears/invalidates the security context according to the authentication mechanism.
3. **Invalidates `WebSession`** or removes session authentication state in the appropriate store.
4. Instructs the browser to delete the session cookie via `Set-Cookie` with matching `Name`/`Domain`/`Path` and `Max-Age=0` when needed.
5. Accounts for remember-me tokens, refresh tokens, concurrent sessions, and identity provider state per policy.
6. Avoids caching sensitive responses; logout cannot "recall" data already displayed or cached earlier.

Spring Security Reactive provides logout in `ServerHttpSecurity`. When using a real WebFlux login flow, it can be enabled/customized:

~~~java
// Configuration snippet; must be placed in a real SecurityWebFilterChain.
return http
        .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
~~~

Spring Security WebFlux's default logout flow must be understood via the handler and matcher of your deployed version; **when CSRF is enabled, do not expose `GET /logout` to delete sessions**. POST logout needs a valid token. If customizing the logout URL, test CSRF, status/redirect, and invalidation using a browser or `WebTestClient`.

### 13.3. Cookie deletion and server-side invalidation differ

A cookie-clearing response may look like:

~~~http
Set-Cookie: SESSION=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

This instructs the client to delete the cookie for the matching `Name`/`Domain`/`Path`. However:
- If you only delete the cookie while the session ID **remains valid** on the server, someone holding a copy of the ID can keep using it. Therefore, you must invalidate/revoke server-side.
- If you only invalidate the session while the client keeps the cookie, the browser may send the old ID, yet the server will not accept it again.
- If the clearing cookie's `Path`/`Domain` **does not match** the created cookie, the browser may retain the old cookie; this is a common misconfiguration.
- Clearing cookies also cannot make the browser forget cached **HTTP Basic credentials**; `WebSession` logout and Basic logout are separate issues.
- In a stateless JWT design, deleting cookies or `WebSession` does not automatically revoke issued tokens if the token remains valid and continues to be sent.

### 13.4. Session fixation

If an application supports logging in to transition from an anonymous to an authenticated session, it must protect against **session fixation**: an attacker tries to make a victim use a session ID known in advance to the attacker, then exploits it after the victim logs in.

`WebSession.changeSessionId()` generates a new session ID for an existing session. In Spring Security, verify the actual session fixation protection of the version/flow in use; do not randomly insert ID rotation at the wrong point where CSRF, form flows, or context could be lost. The key takeaway is **rotate the ID at appropriate privilege-escalation boundaries**, rather than relying on cookie flags to replace this defense.

### 13.5. Concurrent sessions and absolute policy

One person may have multiple devices/browsers. Deleting one `WebSession` **does not automatically** log out all devices. If logout-all is required, you need a mechanism to enumerate/revoke all sessions or tokens per policy (e.g., Spring Session with a store carrying sufficient metadata, token revocation, or centralized identity management).

An idle timeout can be extended by activity. If security requires re-logging in at most every N hours, an independent **absolute lifetime** must be added. Cookie `Max-Age` is not the sole reliable mechanism for that requirement.

## 14. HTTPS Reverse Proxy, Spring Session Redis, and Multi-Instance Deployment

### 14.1. Reverse proxy

Diagram:

~~~text
Browser --HTTPS--> Load Balancer / Reverse Proxy --(trusted hop)--> WebFlux
             ^                                           |
             |                                           v
             +----------- Set-Cookie: ... Secure ... ----+
~~~

Do not treat internal proxy-to-app HTTP traffic as a reason to drop `Secure` on browser cookies. If the app infers scheme from headers, the proxy must normalize/overwrite `Forwarded` / `X-Forwarded-Proto` properly; never trust headers from public clients. You may need to set `server.forward-headers-strategy` per actual infrastructure layout and enable it only when a trusted proxy is in place.

**An important check** is that the actual response from the public origin to the browser has the right flags and stable HTTPS, with no mixed content or HTTP redirects leaking session IDs.

### 14.2. Multiple instances and session stores

If `WebSession` is stored in-memory within one instance, requests routed to another instance may not see session data (unless sticky sessions are used). For scaling out, use Spring Session WebFlux + Redis or an equivalent reactive store.

Spring Session provides `WebSession` integration for Redis and a cookie resolver mechanism. When using Spring Session:
- Distinguish **TTL in Redis**, `WebSession.maxIdleTime`, **cookie `Max-Age`**, and absolute login TTL.
- Ensure logout/invalidation deletes the session in the shared store.
- Verify activity/expiration updates per the specific implementation.
- Do not use `HttpSession`/Servlet guides in place of `WebSession`/Reactive.
- Check the active `WebSessionIdResolver` bean; a custom resolver may affect default property binding.

**Never put session IDs or raw cookies into metrics labels/logs.** To trace errors, use an independent correlation ID, not authentication tokens/IDs.

### 14.3. Deploying cookies across subdomains or cross-site

With frontend `app.example.test` and API `api.example.test`:
- Do not rush to set `Domain=.example.test` on the session cookie; this exposes the cookie to many subdomains.
- Consider host-only cookies with a Backend-for-Frontend pattern or a same-origin reverse proxy.
- If cross-origin/cross-site is genuinely required, explicitly define the CORS allowlist, browser `credentials` mode, CSRF tokens, `SameSite`, and third-party cookie policies.
- `SameSite=None` requires `Secure` in modern browsers, yet **does not guarantee** browsers will allow third-party cookies through because additional blocking policies may apply.
- Test OAuth2/OIDC redirect flows on supported browsers if login spans multiple sites.

## 15. Typical Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `server.servlet.session.cookie.*` in WebFlux | Property names belong to Servlet configuration | Use `server.reactive.session.cookie.*` |
| Setting `Secure=false` in HTTPS production because internal proxy uses HTTP | Leaks ID if client traverses an unencrypted channel | Keep `Secure=true`, configure proxy/TLS properly |
| Thinking `HttpOnly` prevents CSRF | Browsers still send cookies automatically | Combine CSRF tokens and proper `SameSite` policy |
| Thinking `HttpOnly` blocks all XSS | XSS can still issue requests carrying the cookie | XSS prevention, CSP, output encoding |
| Using `SameSite=None` without enabling `Secure` | Cookie may be rejected by browsers | Use `Secure` + HTTPS and evaluate third-party policies |
| Using `SameSite=Strict` without testing SSO | Redirect flows may drop the cookie | Test IdP redirects; pick policy per use case |
| Disabling CSRF because `SameSite=Lax` is set | `Lax` does not block every forged request | Keep CSRF when using browser ambient credentials |
| Thinking `Max-Age=30m` guarantees the session lives 30m | Server has separate idle/absolute timeouts | Design and test the separate clocks |
| Setting a 12h cookie with no server expiration | Session token can be abused for too long | Configure appropriate idle and absolute expiry |
| Deleting browser cookie while leaving server session valid | Old ID may still be replayed | Invalidate/revoke server-side |
| Invalidating session while Basic credentials remain | Basic browser cache is separate from `WebSession` | Design an appropriate logout flow |
| Logging out via GET | GET can be triggered cross-site | Use POST and CSRF |
| JavaScript reading session ID to obtain CSRF token | Breaks `HttpOnly` protection for the session | Separate the CSRF-token cookie/endpoint from the session cookie |
| Overly broad `Domain` | Cookie travels to unnecessary subdomains | Prefer host-only and minimal `Path`/`Domain` |
| Trusting client-supplied `Forwarded` headers | Can be spoofed for scheme/origin | Trust only a trusted reverse proxy |
| Checking only YAML without inspecting `Set-Cookie` | Beans/proxies/versions may alter headers | Inspect actual HTTP headers |
| Logging `SESSION` ID or placing it in URLs | Leaks a bearer-like session identifier | Redact tokens; keep session IDs out of URLs/traces |
| Changing session store without checking Redis TTL | Sessions expire or survive unexpectedly | Align policies and monitor the store |

## 16. Implementation and Verification Checklist

### Client-side cookie
- [ ] The **session ID** cookie has `Secure` in HTTPS production.
- [ ] `HttpOnly` is enabled for the session ID.
- [ ] `SameSite` is chosen deliberately: `Strict`/`Lax`/`None`, covering SSO flows and browser compatibility.
- [ ] `Path` and `Domain` are minimal; prefer host-only unless subdomain sharing is required.
- [ ] `Max-Age` or session-cookie lifetime matches policy, not confused with server timeout.
- [ ] Old cookies with the same name/path/domain do not cause shadowing during migrations.
- [ ] Browser DevTools confirms `Set-Cookie` responses and `Cookie` requests match expectations.
- [ ] Session IDs are never exposed in console/logs/queries/analytics.

### Server-side session
- [ ] `server.reactive.session.timeout` has a reasonable idle timeout value.
- [ ] Where absolute lifetime is needed, a separate enforcement policy and tests exist.
- [ ] Session invalidation actually removes state in `WebSession` store/Redis, across multiple instances.
- [ ] At appropriate authentication/privilege boundaries, verify session fixation/rotation.
- [ ] Multi-device logout and token revocation are designed separately if required.
- [ ] Do not infer "stateless" merely from seeing no cookie or using a no-op `SecurityContextRepository`.

### Security and operations
- [ ] CSRF protection remains appropriate for unsafe browser actions.
- [ ] GET/HEAD have no side effects.
- [ ] HTTPS and trusted proxy/forwarded headers are configured properly.
- [ ] Resource authorization is enforced independently of session cookie flags.
- [ ] A `secure:false` local profile is never deployed to public systems.
- [ ] Run Spring Security/WebFlux tests and real browser tests; test supported browsers.
- [ ] Safe monitoring exists for login failures, expired sessions, and logouts, without logging session IDs.

## 17. Self-Check Questions

**Question 1.** Does `Secure` encrypt cookie contents?

> No. It restricts sending the cookie over insecure HTTP channels; HTTPS/TLS is needed to protect transport.

**Question 2.** Does `HttpOnly` prevent same-origin JavaScript from making requests with the cookie?

> No. It restricts reading the cookie via ordinary JavaScript; the browser can still attach the cookie to requests.

**Question 3.** Can `SameSite=Lax` replace CSRF tokens?

> No. `Lax` only restricts certain cross-site scenarios and still has exceptions/limits; CSRF protection is needed per the threat model.

**Question 4.** Why does `SameSite=None` normally require `Secure`?

> Modern browsers require `None` cookies to carry `Secure`; even over HTTPS they may still be blocked by third-party cookie policies.

**Question 5.** If cookie `Max-Age=30m` while `WebSession` idle timeout is 10 minutes, can a request still have a session after 15 minutes of inactivity?

> The cookie may still be sent, yet the server must treat the `WebSession` as expired once it exceeds the store's idle timeout; never accept the old ID to restore authentication.

**Question 6.** Which configuration namespace does Spring Boot WebFlux use?

> `server.reactive.session.*`; not `server.servlet.session.*`.

**Question 7.** Why is `NoOpServerSecurityContextRepository` not enough to claim "no session exists"?

> Because the CSRF token repository, controllers, and other WebFlux components can still create a `WebSession`.

**Question 8.** Why is deleting the cookie in the browser without invalidating the server session insufficient for logout?

> Because a previously copied session ID can still be accepted by the server if the session has not been revoked.

**Question 9.** A browser keeps sending HTTP Basic after `WebSession.invalidate()`. Is invalidation broken?

> Not necessarily. Basic credentials may remain in the browser's cache; they are independent of `WebSession`.

**Question 10.** How do `Max-Age` and `maxIdleTime` differ?

> `Max-Age` is how long the client stores/sends the cookie; `maxIdleTime` is the idle duration before the server-side `WebSession` is considered expired.

**Question 11.** When should `CookieWebSessionIdResolver.addCookieInitializer` be used?

> When customizing the session ID cookie per a specialized policy or without suitable auto-configuration, while checking for conflicts with Spring Boot/Spring Session.

**Question 12.** Why should you avoid setting `Domain=.example.test` just for convenience across all subdomains?

> Because it widens cookie scope, increasing the risk of abuse by weak or untrusted subdomains; prefer host-only cookies and origin isolation.

## 18. Summary

In Spring Security Reactive, **the session cookie is the transport vehicle for the session ID**, while `WebSession`/`SecurityContext` and the session store determine whether associated data or privileges remain valid.

Five rules to remember:

1. **Production HTTPS:** set `Secure=true` for the session ID cookie.
2. **Keep IDs unreadable by scripts:** keep `HttpOnly=true` on the session cookie.
3. **Constrain cross-site purposefully:** generally start with `SameSite=Lax`, evaluating `Strict`/`None` based on real SSO/iframe/cross-site needs.
4. **Manage both lifetimes:** cookie `Max-Age` and server `maxIdleTime` are two distinct clocks; absolute login lifetime needs its own policy.
5. **Real logout must revoke the session:** invalidate server-side state, delete the cookie with matching scope when needed, and handle Basic/JWT/refresh tokens or other device sessions separately.

For Spring Boot WebFlux, use `server.reactive.session.cookie.*` and `server.reactive.session.timeout`, inspect `Set-Cookie` in real environments, and continue protecting CSRF/XSS, authorization, TLS, and session fixation as distinct layers.

### Official references

- Spring Boot 3.5 — Common Application Properties, `server.reactive.session` group: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework Javadoc — `WebSession`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Framework Javadoc — `CookieWebSessionIdResolver`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
- Spring Session Reference — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session Reference — Common Configurations: https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — Set-Cookie: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- RFC 6265bis — HTTP State Management Mechanism (draft/current evolution): https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html