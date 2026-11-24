# CsrfWebFilter, ServerCsrfTokenRepository, and the CSRF Token Lifecycle in Spring Security Reactive

## 1. Problem, Scope, and Objectives

**Cross-Site Request Forgery (CSRF)** occurs when an untrusted web page attempts to make a victim's browser send a state-changing request to an application where the victim is logged in. The browser may automatically attach session cookies or certain cached credentials, making the server treat the request as coming from a legitimate user even though the user did not intentionally trigger the action.

In **Spring WebFlux** applications, Spring Security provides **CsrfWebFilter** to validate a CSRF token on protected requests. The expected token is managed via the **ServerCsrfTokenRepository** contract; the token sent to the browser or JavaScript is exposed from the request appropriately via **ServerCsrfTokenRequestHandler**.

This lesson answers:

1. How does CSRF differ from **authentication**, **authorization**, **CORS**, **XSS**, and session fixation?
2. Where does **CsrfWebFilter** filter requests, which HTTP methods does it apply to, and when does it return 403?
3. What do **ServerCsrfTokenRepository.generateToken**, **saveToken**, and **loadToken** do? Why do they return `Mono`?
4. How is the token generated and saved; how is it read, placed into forms/headers, and compared?
5. How do **WebSessionServerCsrfTokenRepository** and **CookieServerCsrfTokenRepository** differ?
6. Why does Spring Security 6+ use **XorServerCsrfTokenRequestAttributeHandler** by default, and how does it relate to BREACH?
7. When is the token generated on demand (deferred/lazy), and why do GETs typically avoid reading the token?
8. How to write a **Java 17+ WebFlux** demo with `GET /csrf` and a CSRF-protected `POST`, preserving session cookies with curl.
9. How to test the repository lifecycle with `StepVerifier` and real HTTP behavior with `WebTestClient`.
10. What happens when a session expires, a user logs in/out, tokens mismatch, or an SPA uses a cookie token?

**Focus:** A CSRF token must be **bound to an appropriate trusted context**, not just a random string self-declared by the client. Both the client-submitted token and the server-managed expected token must be verified, without opening overly broad CSRF exemptions.

## 2. What is CSRF: a browser-based example

Suppose Alice is logged into a bank site and holds a `SESSION` cookie. The bank site allows money transfers via `POST /transfers`. A malicious page can build an auto-submitting form:

~~~html
<form action="https://bank.example/transfers" method="post">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="100">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

If the browser sends the session cookie to `bank.example` in that request context, and the server only checks the cookie without another CSRF binding, the action can execute against the user's intent. Cookies may be restricted by SameSite and browser policies, but **SameSite should not be treated as an absolute replacement for CSRF tokens** across all deployment models.

The **synchronizer token pattern** measure:

- When the trusted application serves a page/form, it provides a token that a malicious site cannot read under the Same-Origin Policy absent configuration flaws or XSS.
- The browser sends the token in a **form field** or a **header actively added by same-origin JavaScript**.
- `CsrfWebFilter` compares the browser-supplied token against the expected token from the repository.
- When missing or wrong, the request does not reach the state-changing handler.

~~~text
Alice's browser                         WebFlux server
      |                                       |
      | GET /csrf or page with form           |
      +-------------------------------------->|
      |                                       | load token, or generate + save
      |<---------- token + session cookie ----+
      |                                       |
      | POST /api/notes                       |
      | Cookie: SESSION=...                   |
      | X-CSRF-TOKEN: issued token            |
      +-------------------------------------->|
      |                                       | CsrfWebFilter:
      |                                       |  load expected token
      |                                       |  resolve submitted token
      |                                       |  compare
      |<------------------- 200 or 403 -------+
~~~

Another origin cannot read the `GET /csrf` response unless the system opens CORS to it; nor does it know the token to send in a custom header. **CORS is not a substitute for CSRF**, and XSS on the trusted origin itself can steal or use the token. Therefore XSS prevention and cookie policies remain necessary.

### 2.1. CSRF vs. authentication and authorization

| Check | Question | Example |
| --- | --- | --- |
| Authentication | Does the caller possess valid credentials? | Login cookie/HTTP Basic |
| Authorization | What is the caller allowed to do? | ROLE_ADMIN, owner/tenant |
| CSRF | Does a state-changing request reflect legitimate intent from the user's frontend, in an auto-sent credential model? | POST with valid CSRF token |
| CORS | Which browser origins are allowed to read or send controlled cross-origin requests? | Access-Control-Allow-Origin |
| XSS | Is malicious script running inside the trusted origin? | Script reading tokens, performing actions |
| Session fixation | Is the session ID rotated appropriately before and after login? | WebSession.changeSessionId |

A POST with a valid password and sufficient role can still receive **403 due to missing CSRF**. Conversely, having a valid CSRF token **does not** mean the caller is authenticated or authorized; authentication/authorization still decide separately.

## 3. WebFlux architecture: where does CsrfWebFilter sit?

For Spring Security Reactive, **SecurityWebFilterChain** contains WebFilters handling authentication, authorization, CSRF, and other mechanisms. `CsrfWebFilter` implements **org.springframework.web.server.WebFilter**, working with **ServerWebExchange**, **WebFilterChain**, and **Mono<Void>**.

Do not confuse it with Servlet's `CsrfFilter`:

| Servlet Spring Security | Reactive Spring Security |
| --- | --- |
| CsrfFilter | **CsrfWebFilter** |
| CsrfTokenRepository | **ServerCsrfTokenRepository** |
| HttpServletRequest/HttpServletResponse | **ServerWebExchange** |
| HttpSessionCsrfTokenRepository | **WebSessionServerCsrfTokenRepository** |
| CookieCsrfTokenRepository | **CookieServerCsrfTokenRepository** |
| CsrfTokenRequestHandler | **ServerCsrfTokenRequestHandler** |
| HttpSecurity.csrf(...) | **ServerHttpSecurity.csrf(...)** |

Simplified flow:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    +--> CsrfWebFilter
    |      |
    |      +--> Determine if request requires CSRF
    |      |
    |      +--> Expose Mono<CsrfToken> as exchange attribute
    |      |
    |      +--> If safe method: no submitted token required
    |      |
    |      +--> If unsafe method:
    |             load expected token
    |             resolve token from header/form parameter
    |             compare, missing/invalid -> 403
    |
    +--> Authentication / Authorization
    |
    v
Controller or RouterFunction -> service
~~~

Exact filter ordering and exception paths depend on configuration/version; never assume a 403 always comes from an authorization rule. `CsrfWebFilter` can reject before the controller is invoked; hence **`@RestControllerAdvice` is not a substitute for `CsrfWebFilter`**.

### 3.1. Safe and unsafe HTTP methods

By default, CSRF protection applies to unsafe HTTP methods. Methods considered safe by the default matcher:

- GET
- HEAD
- TRACE
- OPTIONS

Methods such as POST, PUT, PATCH, and DELETE must send an appropriate token when CSRF is enforced.

| Request | Needs CSRF under default matcher? | Notes |
| --- | --- | --- |
| GET /catalog | No | GET must be read-only |
| HEAD /catalog | No | HEAD must not mutate data |
| OPTIONS /catalog | No | May be a CORS preflight |
| POST /api/notes | **Yes** | Writes data |
| PUT /api/notes/42 | **Yes** | Modifies data |
| PATCH /api/notes/42 | **Yes** | Partially modifies data |
| DELETE /api/notes/42 | **Yes** | Deletes data |

**Never put important side effects into GET** just because GET is exempt from CSRF. For example, `GET /logout/now` or `GET /transfer-money` is a dangerous design: an attacker can trigger GET via links, images, navigations, or crawlers. Use semantically proper unsafe methods and enforce CSRF when browser-based credentials are used.

### 3.2. What does a CSRF 403 mean?

If a POST lacks a token, `CsrfWebFilter` can return **403 Forbidden**. This is insufficient to conclude the user lacks `ROLE_ADMIN`. Distinguish the states clearly:

1. **Missing CSRF token**: request is rejected at CSRF; data must not be updated.
2. **Token mismatches repository**: request is rejected at CSRF.
3. **Valid token but no credentials**: CSRF passes; authentication/authorization can still return 401 or redirect to login.
4. **Valid token, valid credentials, missing role**: authorization can return 403.
5. **Valid token, valid credentials, sufficient authority**: handler can process and return the business status code.

A POST test carrying only an `Authorization` header while missing CSRF often gets 403; this **does not prove** the endpoint's authentication or role policy is configured properly.

## 4. The ServerCsrfTokenRepository contract

The interface **org.springframework.security.web.server.csrf.ServerCsrfTokenRepository** defines three reactive operations:

~~~java
Mono<CsrfToken> generateToken(ServerWebExchange exchange);
Mono<Void> saveToken(ServerWebExchange exchange, CsrfToken token);
Mono<CsrfToken> loadToken(ServerWebExchange exchange);
~~~

These are illustrative signatures, not a standalone Java class. **CsrfToken** carries at least three values:

~~~java
String headerName = token.getHeaderName();
String parameterName = token.getParameterName();
String value = token.getToken();
~~~

Each method has a distinct responsibility:

| Method | Role | When used |
| --- | --- | --- |
| generateToken(exchange) | Generate a new token | No expected token exists yet or a new token is needed |
| saveToken(exchange, token) | Persist token in repository | After generation or when lifecycle demands |
| loadToken(exchange) | Read expected token | Rendering token or validating submitted token |
| saveToken(exchange, null) | Delete stored token | Invalidate/clear token per strategy |

In the reactive contract:

- **generateToken** returns **Mono<CsrfToken>**; do not assume calling the method immediately produces data if the publisher is not subscribed to.
- **saveToken** returns **Mono<Void>**, which must be composed and awaited in the reactive chain; never call **subscribe()** manually inside a request handler.
- **loadToken** returns a `Mono` that may **complete empty** when no token exists yet.
- **saveToken(exchange, null)** means removing the saved token per the repository contract.
- The token is a **sensitive value for CSRF protection**; never put it in application logs, URLs, analytics, or public caches.

If replacing the default repository, a custom implementation must store and read the exact same value, avoid blocking the event loop, have sufficient cryptographic entropy, support expiration/rotation, and fail closed when the backend is unavailable. Never write a repository that "always returns a fixed token" or merely compares the submitted token with itself.

### 4.1. Is CsrfToken an Authentication or session ID?

No. A CSRF token **does not prove the user is Alice**, does not grant `ROLE_USER`, and does not grant access. Nor is it the `WebSession` ID or a password. Keep them distinct:

- **Authentication**: identity verified by the framework.
- **SecurityContext**: authentication context for the request/session.
- **CSRF token**: anti-forgery proof by design.
- **SESSION cookie**: ID helping the server locate session state.

An attacker who knows or guesses a username cannot forge a valid CSRF token for the victim's session by calling `generateToken` on a separate session.

## 5. CSRF token lifecycle from absence to expiration

### 5.1. No-token state

When a browser first opens the app, the repository may not yet contain an expected token in the session. **Having no token** is a valid state before a token is requested.

With `WebSessionServerCsrfTokenRepository`, the token is stored in **WebSession**; if absent, `loadToken` completes empty. `CsrfWebFilter` can wire a **load-or-generate** publisher so a new token is generated and saved **only when genuinely needed**.

An ordinary GET like `/public/ping` that does not read the token avoids generating/saving a token just to serve a read-only request.

### 5.2. Token requested to render a form or API response

For example `GET /csrf`:

1. `CsrfWebFilter` lets the safe method pass the submitted-token check.
2. Request attribute **CsrfToken.class.getName()** holds the **Mono<CsrfToken>** published by the request token handler.
3. The controller or view **subscribes via the reactive chain** by returning the corresponding `Mono`.
4. The repository looks up the expected token; if absent, a new token is generated and saved.
5. The client receives the value to send back alongside the session cookie.

With Spring Security 6+, **XorServerCsrfTokenRequestAttributeHandler** normally emits a **masked** token; this value may differ between two renders even when the raw expected token in the repository has not changed.

### 5.3. Unsafe request submits the token

For example `POST /api/notes` from a same-origin client:

1. Browser sends the **SESSION cookie** identifying the corresponding `WebSession`.
2. JavaScript obtains the previous token value from `GET /csrf` or a form.
3. Client adds the header advertised by **CsrfToken.getHeaderName()**, typically **X-CSRF-TOKEN** with the WebSession repository.
4. `CsrfWebFilter` uses the request handler to extract the submitted token from the appropriate header or form parameter.
5. With XOR masking, the handler decodes the masked value back to the raw token for comparison.
6. The repository supplies the expected token from the request's `WebSession`.
7. If it matches and is not rejected by other filters, the request proceeds to the handler.
8. Authentication, authorization, validation, and business logic remain separate barriers.

If the client sends **a token from another session**, or the cookie expired leaving the server without an expected token, the request is rejected per CSRF policy.

### 5.4. Can a token be reused after a successful POST?

In the synchronizer token pattern, **the raw token stored in the session can be reused across multiple unsafe requests**, until lifecycle/rotation/expiry changes it. A CSRF token is **not necessarily a one-time token**, and you should not demand a fresh token after every single POST unless your application policy requires it.

With XOR masking, the value rendered to the client may differ between two GETs while mapping to the same raw token stored in `WebSession`. Therefore **never compare two masked token strings directly to conclude the repository rotated the token**.

### 5.5. Expired token or invalidated session

When `WebSession` expires, the app loses the expected token bound to that session. A POST using the old cookie/token may receive 403. Proper UX:

- Inform the user that the session expired or prompt to reload the form.
- Obtain a **new CSRF token** from the backend through a valid flow.
- Do not silently replay write operations multiple times if duplicate side effects are possible.
- For authenticated apps, re-verify authentication/session.
- Test session loss and logout under actual deployment conditions.

### 5.6. Login and logout

Form login POST and logout POST are also typically **unsafe requests** protected by CSRF. When authentication or logout changes/destroys the session, or the app's mechanism rotates the token, **the client needs to fetch the new token** before the next POST.

Do not mechanically apply all details of Servlet's **CsrfAuthenticationStrategy/CsrfLogoutHandler** to WebFlux: reactive uses its own components and exact behavior depends on version, logout handler, and session repository. Test that old tokens cannot accidentally be reused after session revocation, and that new tokens are properly issued for the new session.

Do not use **GET /logout** as a state-changing endpoint to "dodge CSRF", unless the product explicitly understands and accepts the risk; protected POST logout remains the standard choice.

## 6. CsrfWebFilter and ServerCsrfTokenRequestHandler

`CsrfWebFilter` does more than fetch tokens from the repository; it also exposes the token to views/controllers and **resolves the submitted value** from the request. That role belongs to **ServerCsrfTokenRequestHandler** and its resolver.

Key classes to know:

- **ServerCsrfTokenRequestAttributeHandler**: places the token in a request attribute and resolves the token from the request (header/form parameter) per configuration.
- **XorServerCsrfTokenRequestAttributeHandler**: an extension that masks the token on render and decodes it upon submission; used by default since Spring Security 6.0 to help mitigate BREACH risk in compressed responses.
- **CsrfWebFilter.DEFAULT_CSRF_MATCHER**: default matcher determining which methods require CSRF checking.
- **ServerHttpSecurity.CsrfSpec**: DSL for specifying repository, request handler, or matcher.

A typical minimal configuration:

~~~java
return http
        .csrf(csrf -> csrf
                .csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
        .build();
~~~

The snippet above must reside **inside an application's `@Bean SecurityWebFilterChain` method** alongside proper authentication/authorization rules; it is not a standalone runnable file.

### 6.1. Exchange attribute holds Mono<CsrfToken>

Spring Security WebFlux documents the attribute under key:

~~~java
CsrfToken.class.getName()
~~~

Accessible in a controller:

~~~java
Mono<CsrfToken> csrfToken =
        exchange.getAttribute(CsrfToken.class.getName());

if (csrfToken == null) {
    return Mono.error(
            new IllegalStateException("CSRF filter not configured"));
}

return csrfToken.map(token -> Map.of(
        "headerName", token.getHeaderName(),
        "token", token.getToken()));
~~~

This illustrative snippet is the body of a method taking `ServerWebExchange exchange` and returning `Mono<Map<String,String>>`. The complete program is in Section 9.

**Important:** reading the request attribute **must not be equated** with reading the raw token directly from the session. The `CsrfToken` provided to views by the request handler may be **XOR-masked**. To make forms work with the default handler, submit back the exact rendered value rather than grabbing a raw token from the repository and inventing your own encoding/decoding.

### 6.2. Why does masking relate to BREACH?

In applications returning compressed HTML, if a secret token appears repeatedly in responses, compression-length side-channel attacks can infer sensitive data. The XOR token request handler injects randomness into the rendered token value, reducing token leakage risk through response compression.

Table:

| Value | Where it lives | Meaning |
| --- | --- | --- |
| Raw expected token | WebSession/token repository | Original value to validate against |
| Masked token | HTML/form/GET /csrf via request handler | Value client submits back |
| Header/form value | Subsequent HTTP request | Handler resolves/unmasks to compare with raw |
| SESSION cookie | Browser | Identifies the session used to locate raw token |

**Do not disable BREACH protection just so clients can copy a raw token from a cookie.** If switching to `CookieServerCsrfTokenRepository` for an SPA, ensure compatibility between the cookie token (possibly raw) and the request handler (which expects masked tokens by default). Mismatched configs easily cause every POST to return 403 or tempt developers to disable protection wrongly.

## 7. Two common repositories

### 7.1. WebSessionServerCsrfTokenRepository — the default

This is the standard choice when an application uses **WebSession**:

- Expected token is stored in the server-side session, bound to session state.
- Token sent to the client is not proof of login.
- Requests must carry the matching session cookie so the server can read the expected token.
- If the session is lost/expired, the old token is no longer valid for that session.
- JavaScript does not need to read a token cookie; masked tokens can be supplied in HTML or a `GET /csrf` endpoint.
- With multiple replicas, a WebFlux-compatible shared session store is needed when cross-node sessions are required.

Explicitly declaring the default:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        new WebSessionServerCsrfTokenRepository()))
~~~

**Do not use Servlet's `HttpSessionCsrfTokenRepository` in WebFlux.** Despite similar names, they serve different contracts.

### 7.2. CookieServerCsrfTokenRepository — an option for SPAs

**CookieServerCsrfTokenRepository** stores the expected token in an **XSRF-TOKEN** cookie per the common Angular convention, and by default reads the submitted token from the **X-XSRF-TOKEN** header or **_csrf** parameter.

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

**withHttpOnlyFalse()** lets JavaScript read the cookie, but makes the cookie token more exposed to XSS reads. When JavaScript **does not need to read the cookie directly**, prefer the default constructor and keep `HttpOnly`.

Important for Spring Security 6+:

- **Cookie tokens** and **XOR-masked tokens** can have different formats.
- Directly copying the raw `XSRF-TOKEN` cookie value into the `X-XSRF-TOKEN` header requires a **compatible request handler**, otherwise the default XOR handler may fail decoding.
- Do not assume a one-line cookie repository config suffices for every SPA.
- Test thoroughly with browsers, CORS, SameSite, Secure, and session/credential policies.
- Cookies are not equivalent to an independent, signed, or subdomain-cookie-injection-proof raw token; understand the threat model.

The demo below intentionally uses **WebSessionServerCsrfTokenRepository** and `GET /csrf` to avoid mixing raw cookie tokens with masked request values.

### 7.3. Should you write a custom repository?

Only if there is a clear requirement, such as distributed state where `WebSession` or standard cookies cannot be used. You must ensure:

1. Generate unpredictable tokens using an appropriate cryptographic entropy source.
2. Store tokens bound to the right session/trusted identifier.
3. Never let clients arbitrarily set their own expected token.
4. Delete tokens properly on invalidation.
5. Use non-blocking `Mono` APIs so the event loop is never blocked.
6. Prevent token leakage via logs, URLs, analytics, and CDNs.
7. Test concurrent requests, session rotation, expiration, and multi-instance behavior.
8. Ensure compatibility with the configured request handler.

Do not write a custom repository merely to "have reactive code" when Spring Security already provides standard ones.

## 8. Default configuration, options, and trust boundaries

According to Spring Security WebFlux documentation:

- **CSRF is enabled by default** in standard security configurations.
- **WebSessionServerCsrfTokenRepository** is the default repository.
- **XorServerCsrfTokenRequestAttributeHandler** is the default request handler since Spring Security 6.
- The CSRF token is exposed as **Mono<CsrfToken>** in an exchange attribute.
- GET/HEAD/TRACE/OPTIONS require no submitted token under the default matcher; unsafe methods do.
- Form POSTs and Ajax/JSON POSTs carry the token differently yet both must match the expected token.

### 8.1. When can CSRF exemptions be configured?

There is no "always disable CSRF for REST APIs" rule. The decision depends on whether **the browser auto-sends credentials**:

| Client/authentication pattern | Could CSRF be relevant? | Notes |
| --- | --- | --- |
| Browser + session cookie | **Yes** | Browser can auto-send cookies |
| Browser + cached HTTP Basic credentials | **Potentially** | Browser can automatically resend credentials |
| Browser + cookie containing auth/JWT token | **Yes** | A JWT in a cookie is still an auto-sent credential |
| API accepting only Bearer tokens in Authorization explicitly added by client, no cookies | Typically reduces classic CSRF risk | Still evaluate CORS, XSS, token storage, and architecture |
| Backend-to-backend without browser cookies | Usually outside browser CSRF model | Must still authenticate and authorize |
| Website using GET to mutate state | Flawed design | Fix HTTP semantics rather than toggling CSRF |

When multiple `SecurityWebFilterChain` beans exist, evaluate CSRF separately per chain based on endpoints and credential mechanisms. If exempting a path set, exempt **only the exact methods/routes needed** and test that other write routes remain protected.

### 8.2. CORS preflight is not a business action

`OPTIONS` can appear as a CORS preflight, usually carrying no credentials. If CORS is not configured before authentication, the frontend may report errors before sending the real POST. Do not fix this by `permitAll` on all unsafe methods; configure CORS, origins, headers, and credential policies based on the threat model.

### 8.3. CSRF does not replace SameSite, Origin checks, or XSS defense

CSRF tokens work best when combined with:

- HTTPS/TLS, appropriate `Secure` and `HttpOnly` cookies.
- Intentional `SameSite`, restricted cookie `Domain` and `Path`.
- Never opening CORS credentials to untrusted origins.
- HTML escaping, Content Security Policy, and XSS prevention.
- Real authentication and authorization.
- Rate limiting, anomaly monitoring, and session invalidation.
- For sensitive operations, Origin/Referer checks at an appropriate layer as defense-in-depth.

Never log tokens or session IDs in request/response logging. Headers can contain secrets and require masking.

## 9. Runnable Java 17+ project: WebFlux + WebSession CSRF

This demo uses **Spring Boot 3.5.16**, Java 17+, Gradle 8.4+ (Gradle 8.14 works), and Spring Security reactive managed by Spring Boot.

Test account: **alice / alice-pass** with `ROLE_USER`. Sample password is for localhost experimentation only.

Demo goals:

- `GET /public/ping`: public, no CSRF required.
- `GET /csrf`: public, supplies token for same-origin frontend use.
- `GET /api/notes/count`: requires authentication, read-only.
- `POST /api/notes`: requires authentication **and** a valid CSRF token; increments an in-memory counter to prove state mutation occurred.

A POST rejected by `CsrfWebFilter` **must not increment the counter**.

Structure:

~~~text
webflux-csrf-lifecycle/
├── settings.gradle
├── build.gradle
├── src/main/java/example/csrf/CsrfLifecycleApplication.java
├── src/main/java/example/csrf/SecurityConfig.java
├── src/main/java/example/csrf/CsrfController.java
├── src/test/java/example/csrf/CsrfHttpTest.java
└── src/test/java/example/csrf/CsrfRepositoryTest.java
~~~

### 9.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-csrf-lifecycle'
~~~

### 9.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add `spring-boot-starter-web` simultaneously if you want to observe the exact WebFlux WebFilter pipeline. The Spring Boot BOM keeps Spring Security, Reactor, and Spring Framework versions compatible. Use a pinned Gradle Wrapper in team projects.

### 9.3. CsrfLifecycleApplication.java

~~~java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfLifecycleApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

~~~java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/csrf").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                // Keep CSRF enabled and make the default token repository explicit.
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Explanation:**

1. WebFlux `SecurityWebFilterChain` applies to both Controllers and RouterFunctions passing through the chain.
2. `GET /csrf` has `permitAll` so clients can obtain a token before logging in, but **`permitAll` does not bypass `CsrfWebFilter`**.
3. `/api/**` requires valid Authentication.
4. `CsrfWebFilter` uses the `WebSession` repository with no CSRF exemption for `POST /api/notes`.
5. No custom request handler is configured, preserving **default XOR/BREACH protection**.
6. The demo uses HTTP Basic to avoid adding form-login boilerplate; the session cookie here stores the expected **CSRF token**, not a replacement for username/password authentication.
7. A POST missing or mismatching the CSRF token is blocked even with valid HTTP Basic credentials.
8. **Do not disable CSRF** to make examples easier to run; tests will supply real tokens via the real mechanism.
9. `PasswordEncoder` hashes with BCrypt when building `UserDetails`. Sample passwords in code are strictly for learning, never production.

### 9.5. CsrfController.java

~~~java
package example.csrf;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    private final AtomicInteger savedCount = new AtomicInteger();

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        // GET /csrf must not cache the token.
        exchange.getResponse().getHeaders()
                .setCacheControl("no-store");

        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter not configured"));
        }

        // Subscribed indirectly when Spring WebFlux subscribes to the response Mono.
        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "parameterName", value.getParameterName(),
                "token", value.getToken()));
    }

    @GetMapping("/api/notes/count")
    public Mono<Map<String, Integer>> count() {
        return Mono.just(Map.of("count", savedCount.get()));
    }

    @PostMapping("/api/notes")
    public Mono<Map<String, String>> create(Mono<Principal> principal) {
        return principal.map(actor -> Map.of(
                "owner", actor.getName(),
                "id", Integer.toString(savedCount.incrementAndGet())));
    }
}
~~~

**Why does `/csrf` return the token in the response?** Same-origin clients need the token prepared by the request handler. It is not an authentication credential for logging in; `GET /csrf` having `permitAll` does not mean websites on arbitrary origins can read the JSON thanks to Same-Origin Policy/CORS. **Never configure `Access-Control-Allow-Origin: *` with credentials** for such an API.

**Why not call `repository.generateToken()` in the controller?** Doing so can easily create a token detached from the expected token managed by `CsrfWebFilter`, especially with XOR masking present. Use the `Mono<CsrfToken>` placed on the exchange by the filter to stay synchronized.

**Why use `AtomicInteger`?** This is purely in-memory dummy data to prove POST mutates state; production requires a repository, transactions, resource-level authorization, and replay protection where needed.

**Why return a `Map` with `headerName`/`parameterName`/`token`?** It saves learners from hardcoding header names. With `WebSessionServerCsrfTokenRepository`, default names are typically **X-CSRF-TOKEN** and **_csrf**. The returned token is masked by the request handler; the client must send back this exact value.

### 9.6. Running the app

~~~bash
gradle bootRun
~~~

Requires JDK 17+ and Gradle compatible with Spring Boot 3.5.16. By default Spring Boot listens on `http://localhost:8080` unless configured otherwise.

**Test HTTP Basic over localhost only for learning.** Production must use HTTPS/TLS, proper secret management, secure cookies, and appropriate authentication mechanisms. HTTP Basic Base64 does not securely encrypt passwords.

## 10. Curl practice: same cookie, same CSRF token

Examples use Bash, curl, and Python 3 to parse JSON. If `jq` is installed, `jq -r` can extract the token instead of Python.

### 10.1. GET /csrf creates or loads the expected token

~~~bash
curl -sS \
  -c session.cookies \
  http://localhost:8080/csrf \
  -o csrf.json

cat csrf.json
~~~

The body looks like:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "session-scoped-masked-token-value"
}
~~~

Actual token strings **do not have a fixed value** and include XOR-masking randomness. Never put real tokens into logs, tickets, screenshots, or version control.

`session.cookies` holds the corresponding session cookie, usually named **SESSION** in default WebFlux; real apps may customize name, path, SameSite, Secure, or use another resolver.

Set variables:

~~~bash
CSRF_TOKEN="$(python3 -c 'import json; print(json.load(open("csrf.json"))["token"])')"
CSRF_HEADER="$(python3 -c 'import json; print(json.load(open("csrf.json"))["headerName"])')"
~~~

### 10.2. Missing token -> 403 despite valid password

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -X POST \
  http://localhost:8080/api/notes
~~~

Expected result: **403 Forbidden**. Not because Alice lacks a role; the request provided no token for `CsrfWebFilter` to verify.

### 10.3. Wrong token -> 403

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: invalid-token-value" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Expected result: **403 Forbidden**. An arbitrary value does not match the expected raw token. In some versions, the request handler also rejects tokens lacking valid masking structure; what matters is **the write operation is never executed**.

### 10.4. Valid token and cookie -> success

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Expected body:

~~~json
{"owner":"alice","id":"1"}
~~~

`id` is `1` if this is the first valid POST since server startup; if other POSTs ran earlier, `id` increments with the counter. Automated tests should assert owner and status rather than hardcoding IDs if parallel tests run.

### 10.5. Verify state changed

~~~bash
curl -sS -u alice:alice-pass \
  http://localhost:8080/api/notes/count
~~~

If only one valid POST ran since startup, the body will be:

~~~json
{"count":1}
~~~

The two earlier POST requests rejected by CSRF did not increment `count`. This demonstrates the difference between requests stopped by security filters and requests actually reaching the controller.

### 10.6. Valid token but wrong password

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:wrong-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Expected result: **401 Unauthorized** from HTTP Basic, because CSRF passed while authentication failed. This proves **a CSRF token does not replace a password**.

### 10.7. Omitting the matching session cookie

~~~bash
curl -i -sS \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Expected result: **403 Forbidden** because the server cannot locate the expected token of the session that previously issued it. A token alone cannot pass CSRF validation when using `WebSessionServerCsrfTokenRepository`.

**Note:** `session.cookies` and `csrf.json` contain sensitive demo session data; delete them after testing, never commit them, and never publish them.

### 10.8. Observing masked value changes

You can run `GET /csrf` a second time with the same cookie:

~~~bash
curl -sS \
  -b session.cookies \
  -c session.cookies \
  http://localhost:8080/csrf
~~~

A returned token value may differ due to **XOR masking**, which is not proof that the raw token inside `WebSession` rotated. To inspect the expected raw token in tests, use an internal test repository and avoid exposing it to clients.

## 11. Real HTTP testing with WebTestClient

Integration tests must observe both the **session cookie** and the **token JSON**, sending POST requests through the security filters. Do not only unit-test the Controller directly.

File **src/test/java/example/csrf/CsrfHttpTest.java**:

~~~java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfHttpTest {

    @Autowired
    WebTestClient client;

    private record Ticket(
            String sessionId,
            String headerName,
            String token) {
    }

    private Ticket newTicket() {
        EntityExchangeResult<Map> result =
                client.get().uri("/csrf")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(Map.class)
                        .returnResult();

        Map body = result.getResponseBody();
        assertNotNull(body);

        ResponseCookie sessionCookie =
                result.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        String header = (String) body.get("headerName");
        String token = (String) body.get("token");
        assertNotNull(header);
        assertNotNull(token);

        return new Ticket(sessionCookie.getValue(), header, token);
    }

    @Test
    void publicGetDoesNotRequireCsrf() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedGetNeedsAuthenticationNotCsrf() {
        client.get().uri("/api/notes/count")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/notes/count")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsForbidden() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void tokenFromOtherSessionIsForbidden() {
        Ticket a = newTicket();
        Ticket b = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", a.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(a.headerName(), b.token())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameSessionAndTokenAllowPost() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void csrfDoesNotReplaceAuthentication() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void tokenWithoutSessionCookieCannotBeReused() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Run after creating the project properly:

~~~bash
gradle test
~~~

**Expected result:** seven tests in `CsrfHttpTest` PASS when the default WebFlux session resolver uses cookie name `SESSION` and dependencies are compatible. Do not hardcode tokens or session IDs, as they are random values.

Explaining **`newTicket()`**:

1. Calls `GET /csrf` to **subscribe** to `Mono<CsrfToken>` in the response.
2. Uses `WebTestClient` to read the JSON token and `Set-Cookie` for `WebSession`.
3. Builds a `Ticket` holding the matching session ID and advertised header name.
4. Sends back both **cookie** and **header** on the next POST request.
5. When a token from session B is paired with session A's cookie, the test expects 403.

**Limitation:** this integration test assumes the default session cookie. In systems using Spring Session, custom `WebSessionIdResolver`, proxies, or different cookie names, adjust tests to match actual deployment configuration. Never change production cookie names just to simplify tests.

### 11.1. SecurityMockServerConfigurers.csrf() as another option

The **spring-security-test** library provides:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
~~~

When `WebTestClient` is bound and properly configured with **`springSecurity()`** on a mock exchange, **`mutateWith(csrf())`** can supply a valid CSRF token for testing. This is convenient for testing individual URL/controller rules without managing a cookie jar.

However, when the goal is verifying **the real lifecycle of CSRF tokens and session cookies**, do not rely solely on mock `csrf()`: it can skip verifying that clients obtain real tokens from `GET /csrf`, retain cookies, and submit them back in the right session. Thus this lesson uses the end-to-end test above without adding `spring-security-test` to the main project.

### 11.2. A POST test with a wrong token can return 403 before checking roles

A note when writing POST authorization tests: to prove `ROLE_USER` lacks write permission, **supply a valid CSRF token** first; otherwise 403 may come from the token rather than the role rule. You can structure tests as follows:

| Test | Token | Authentication | Expected |
| --- | --- | --- | --- |
| POST missing token | Missing | valid alice | 403 CSRF |
| POST wrong token | Token B + cookie A | valid alice | 403 CSRF |
| POST valid token + wrong credentials | Token A + cookie A | wrong alice | 401 authentication |
| POST valid token + valid credentials | Token A + cookie A | valid alice | 200 |
| GET /api/notes/count | Not needed | valid alice | 200 |

This cleanly separates the three barriers—CSRF, authentication, and authorization—instead of seeing 403 and guessing the cause.

## 12. Testing the repository lifecycle directly with StepVerifier

To understand **generate -> save -> load -> delete** precisely, you can test `ServerCsrfTokenRepository` independently of the HTTP server using **MockServerWebExchange** and **MockWebSession** from `spring-test`.

File **src/test/java/example/csrf/CsrfRepositoryTest.java**:

~~~java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

import reactor.test.StepVerifier;

class CsrfRepositoryTest {

    @Test
    void generateSaveLoadAndDelete() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();

        MockWebSession session = new MockWebSession();

        MockServerWebExchange exchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/csrf"))
                .session(session)
                .build();

        // Initially the session has no expected token.
        StepVerifier.create(repository.loadToken(exchange))
                .verifyComplete();

        AtomicReference<CsrfToken> created = new AtomicReference<>();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .doOnNext(created::set)
                        .flatMap(token ->
                                repository.saveToken(exchange, token)
                                        .then(repository.loadToken(exchange))))
                .assertNext(loaded -> {
                    assertNotNull(created.get());
                    assertEquals(
                            created.get().getToken(),
                            loaded.getToken());
                    assertEquals(
                            created.get().getHeaderName(),
                            loaded.getHeaderName());
                    assertEquals(
                            created.get().getParameterName(),
                            loaded.getParameterName());
                })
                .verifyComplete();

        // saveToken(null) requests removing the expected token.
        StepVerifier.create(
                repository.saveToken(exchange, null)
                        .then(repository.loadToken(exchange)))
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** `CsrfRepositoryTest` PASSES. Running the full project executes **8 tests** total: 7 HTTP tests and 1 repository test. Gradle prints `BUILD SUCCESSFUL` when files are placed properly and runtime/dependencies are valid.

**What this test proves:**

- No token -> `loadToken` completes empty.
- `generateToken` creates a `CsrfToken`.
- `saveToken` and `loadToken` operate on the same `WebSession`.
- `saveToken(exchange, null)` removes the token from the repository.
- Operations must be composed in `Mono` and subscribed via `StepVerifier`.

**What this test does NOT prove:** XOR-masked tokens in HTML, cookies received by browsers, `CsrfWebFilter` rejecting real HTTP requests, CORS, or gateway behavior. That is why combining it with `CsrfHttpTest` is necessary.

### 12.1. Why never call block() in WebFlux?

In a reactive request handler, calling **`block()`** to read a token can block the event loop or throw scheduler errors. Correct:

~~~java
return tokenMono.map(value -> Map.of(
        "token", value.getToken()));
~~~

Avoid:

~~~java
// Wrong in a WebFlux handler: blocks the thread, prone to failing under load.
CsrfToken csrf = tokenMono.block();
return Mono.just(Map.of("token", csrf.getToken()));
~~~

In unit tests, `StepVerifier` can verify a `Mono` without blocking or manual `subscribe()`. In application code, the framework subscribes to the returned publisher as part of the request lifecycle.

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `HttpSessionCsrfTokenRepository` in WebFlux | Wrong servlet/reactive stack | Use `WebSessionServerCsrfTokenRepository` |
| Calling `generateToken` without saving | Server lacks matching expected token | Let `CsrfWebFilter` manage it or compose `save` |
| Calling `saveToken` and discarding the `Mono` | Side effect may never execute | Compose publishers; never manually subscribe |
| Sending token without session cookie | Server cannot find client's expected token | Keep cookie matching the session |
| Using another session's token | CSRF mismatch | Token and session must match |
| Reading raw token from repo and sending to default XOR handler | May fail masked format validation | Read token from request attribute/form |
| Copying raw `XSRF-TOKEN` cookie into header when handler expects masked | 403, or forces custom handler | Design an appropriate SPA token request handler |
| Assuming every GET generates/saves a token | Unnecessary session writes | Understand deferred/lazy `Mono` and request only when needed |
| Assuming token rotates after every POST | Client needlessly refreshes continuously | Distinguish raw tokens from masked representations |
| Assuming the same masked token remains valid after logout | Session/expected token may be gone | Fetch a new token upon session change |
| Thinking `permitAll` disables CSRF on public POSTs | Public endpoints can still be checked by `CsrfWebFilter` | Configure CSRF per method/threat model |
| Setting `csrf.disable()` API-wide because test POST returned 403 | Opens vulnerability when browsers send cookies | Keep CSRF and test sending valid tokens |
| Using GET to perform write operations | Bypasses default CSRF matcher | Switch to POST/PUT/PATCH/DELETE |
| Not checking CSRF on login/logout | Login CSRF, logout CSRF | Keep protection on form and POST logout |
| Confusing CSRF 403 with `ROLE_ADMIN` 403 | Misleading debugging | Test tokens and authorities separately |
| Logging tokens/session cookies while debugging | Session credential leakage | Mask logs; never print real tokens |
| Treating SameSite/CORS as absolute CSRF guarantees | Attack paths may remain | Threat model and defense-in-depth |
| Setting token cookie `HttpOnly=false` when JS doesn't need to read it | Expands token-reading surface | Keep `HttpOnly` unless SPA cookie reading is required |
| Using in-memory session repository behind multi-node load balancer | POST routed to another node misses token | Spring Session / shared session store |
| Disabling BREACH masking just to read raw tokens easily | Reduces protection on compressed responses | Keep XOR and use a compatible request handler |
| Using only `mutateWith(csrf())` to test lifecycle | Skips real cookies/tokens | Add end-to-end tests via `GET /csrf` |

## 14. Production notes: SPA, session timeout, multiple instances

### 14.1. Where does an SPA obtain the token?

Two common patterns exist:

**Pattern A: session repository + GET /csrf**

- Expected token lives in `WebSession`.
- Same-origin SPA calls `GET /csrf` and receives the masked token and header name.
- SPA sends the token in unsafe request headers while the browser sends the matching session cookie.
- When the session expires or is revoked, the SPA requests a new token via a safe flow.
- Never grant permissive CORS credentials to untrusted origins.

**Pattern B: cookie repository + JavaScript reading XSRF-TOKEN**

- `CookieServerCsrfTokenRepository` provides a token cookie.
- JS needs to read the cookie -> may use `withHttpOnlyFalse()`, accepting the trade-off.
- With Spring Security 6+, review the request handler so raw header tokens work properly alongside XOR masking.
- Cookie Domain, SameSite, Secure, path, subdomain trust, and CORS matter greatly.
- If cookie-based authentication is used, unsafe requests must still be protected.

Do not switch from A to B merely to eliminate one `GET /csrf` without evaluating threat models, XSS, and cookie injection.

### 14.2. Session timeout

Suppose a token is rendered in a long-open form: after 30 minutes the session expires and the user clicks Save. The server may return 403 because the expected token is gone. Good UX:

- Do not silently retry write requests repeatedly.
- Inform the user the session expired and prompt to reload/re-authenticate.
- Fetch a fresh token from the new session or appropriate auth sequence.
- For important forms, consider safe client-side draft saving without resubmitting before verifying identity.

### 14.3. Multiple instances and Spring Session

`WebSession` stored in each node's local memory does not guarantee tokens work across nodes. If a load balancer routes `GET /csrf` to replica A and `POST /api/notes` to replica B, the repository may fail to find the token.

Required:

- Use a shared session store supporting reactive, such as Spring Session configured with Redis when appropriate.
- Synchronize secrets/cookie configurations.
- Verify session expiry, TTL, invalidation, and CSRF token persistence.
- Do not rely on sticky sessions as the sole measure hiding long-term inconsistency.
- Test across multiple replicas with the same cookie and token.

### 14.4. File upload/multipart

For multipart uploads, if the token resides only in the body, the system may have to process the body before actually verifying CSRF. Sending the token in an **HTTP header** is advantageous because it allows validation before reading/uploading large payloads at the handler level. Upload size limits and content-type checks are still necessary.

### 14.5. Do not expose tokens outside the trust boundary

`GET /csrf` in the demo is `permitAll` so same-origin clients can prepare a form, yet tokens must never be sent to third-party analytics, referrer URLs, public CDN caches, or CORS responses to untrusted websites. Session cookies must also restrict Domain/Path and enforce appropriate Secure/HttpOnly/SameSite flags.

If XSS is suspected, **a CSRF token cannot stop scripts executing inside the trusted origin**. Preventing XSS via output escaping, safe templates/DOM, and CSP is a separate requirement.

## 15. Self-check questions and exercises

1. Is `CsrfWebFilter` a Servlet or WebFlux filter? Which exchange type does its request-handling signature use?
2. What are the three main methods of `ServerCsrfTokenRepository`? What are each method's `Mono` return types?
3. What does `saveToken(exchange, null)` mean?
4. Where does `WebSessionServerCsrfTokenRepository` store the expected token?
5. Why might `GET /public/ping` not create a token even though CSRF protection is enabled?
6. In Spring Security 6+, why can the token rendered in a form differ between two requests?
7. If session A's valid token is sent alongside session B's cookie, what is the expected security outcome?
8. Why is adding a valid token without matching credentials still insufficient to POST to a protected endpoint?
9. Why can a POST missing CSRF return 403 even if the user holds the right role?
10. What need does `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` address and what is its trade-off?
11. Why should CSRF tokens not be placed in URL query strings or written to logs?
12. Should CSRF be disabled for all REST APIs? What does the answer depend on?
13. Is the token in `WebSession` retained across multiple POSTs or always rotated after one request?
14. When `WebSession` expires, what error can an old form encounter?
15. Why is using only `mutateWith(csrf())` insufficient to test the cookie lifecycle?
16. When `GET /csrf` and `POST /api/notes` hit two different server instances, what infrastructure condition must be met?
17. Why do login/logout POSTs also require CSRF?
18. Can CSRF, CORS, and XSS replace one another?

**Suggested answers:**

1. WebFlux `WebFilter`, using `ServerWebExchange`/`WebFilterChain`/`Mono<Void>`.
2. `generateToken` -> `Mono<CsrfToken>`, `saveToken` -> `Mono<Void>`, `loadToken` -> `Mono<CsrfToken>`.
3. Deletes the expected token from the repository per the contract.
4. The request's `WebSession`.
5. Deferred token; nobody subscribed to or requested the token.
6. `XorServerCsrfTokenRequestAttributeHandler` masks with randomness to mitigate BREACH risk; the raw expected token may remain unchanged.
7. Mismatch/403 if session B holds a different token.
8. CSRF is not authentication; credentials and authorization are still required.
9. `CsrfWebFilter` can reject before or independently of role checks.
10. Allows JS to read the `XSRF-TOKEN` cookie at the cost of losing `HttpOnly` benefits, requiring XSS consideration.
11. URLs/logs can leak via caching/referrers/logs.
12. No; it depends on whether browser credentials are auto-sent and the threat model.
13. The raw token is normally reused within the same session until lifecycle changes; it is not one-time by default.
14. Expected token no longer exists, old POST is rejected; obtain a new token/session.
15. Mock tokens do not verify that session cookies and repositories operate end-to-end.
16. Shared session store or consistent state persistence across replicas.
17. To prevent login CSRF and logout CSRF.
18. No; they address distinct classes of risk.

## 16. References

- Spring Security — CSRF for WebFlux (6.5): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — CsrfWebFilter Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security — ServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security — WebSessionServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security — CookieServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html
- Spring Security — XorServerCsrfTokenRequestAttributeHandler Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security — Reactive CSRF Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Framework — MockServerWebExchange.Builder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.Builder.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Conclusion:** In Spring Security WebFlux, **CsrfWebFilter** decides which requests require CSRF and rejects unsafe requests lacking a valid token; **ServerCsrfTokenRepository** handles generating/saving/loading the expected token; **ServerCsrfTokenRequestHandler** exposes/decodes the client-submitted token value. With the default `WebSession` design, the lifecycle is **GET needing token -> load or generate/save -> render masked token -> client sends header/form with matching session cookie -> CsrfWebFilter validates -> business handler runs**. Keep default protection whenever browsers auto-send credentials, understand the difference between raw tokens and XOR masking, and test both reactive publishers and real HTTP requests instead of disabling CSRF just to make a POST succeed.