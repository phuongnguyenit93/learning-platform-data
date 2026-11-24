# CSRF Attack Mechanics and Conditions Under Which Browsers Auto-Send Credentials

## Learning Objectives

After this lesson, you will be able to:

1. Explain what **Cross-Site Request Forgery (CSRF)** is, why it targets the *authority of an authenticated browser* rather than stealing passwords, and distinguish CSRF from XSS, CORS, and clickjacking.
2. Describe the full set of conditions required for an attack: there is a state-changing operation, the victim's browser holds a credential that is sent with the request, the attacker can construct a valid request, and the server lacks a mechanism to verify user intent.
3. Distinguish `origin`, `site`, `SameSite=Strict/Lax/None` cookies, domain/path, top-level navigation, form POST, and `fetch(..., { credentials: "include" })`; do not confuse **CORS preventing reading a response** with **CORS preventing sending a request**.
4. Point out why session cookies, HTTP Basic cached in the browser, client certificates, and tokens stored in cookies can lead to CSRF; and why Bearer tokens actively attached in headers by JS generally have a different threat model.
5. Understand Spring Security WebFlux's *synchronizer token pattern* for CSRF tokens: `CsrfWebFilter`, `WebSessionServerCsrfTokenRepository`, `CsrfToken`, `XorServerCsrfTokenRequestAttributeHandler`, and protection of unsafe HTTP methods.
6. Build a Java 17+ / Spring Boot 3.x example with form login, an HTML form containing a real CSRF token, a reactive form-handling controller, and `WebTestClient` verifying blocked vs. allowed requests.
7. Design defense-in-depth: CSRF tokens, no state changes via GET, SameSite cookies, Origin/Referer/Fetch Metadata, protecting login/logout, preventing XSS, and not arbitrarily disabling CSRF.

> Scope: Spring Security **WebFlux reactive**. Examples use `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession`, Reactor, and `WebTestClient`. Examples using `HttpSecurity`, `HttpSessionCsrfTokenRepository`, or Servlet `Filter` belong to the Spring MVC/Servlet stack and must not be mechanically copied to WebFlux.

---

## 1. What is CSRF?

**CSRF** is a technique where a page or context controlled by an attacker causes **the victim's browser** to send a request to another application, abusing credentials that the browser automatically attaches to the request by default. If the server only looks at the cookie/HTTP authentication and trusts that the request originated from the user's own intent, it may perform unwanted changes.

An example of a conceptually valid scenario:

- A user is logged into `https://app.example.test` via a session cookie.
- The application has an endpoint `POST /settings/notifications` to change account settings.
- The user opens a page outside the application's control, such as `https://attacker.invalid`.
- That page can create a POST form pointing to `https://app.example.test/settings/notifications`.
- **If** the browser sends the valid cookie/session for that request and the server does not require a matching CSRF token/Origin, the operation may execute under the victim's identity.

The **"if"** condition is crucial: in modern browsers, `SameSite=Lax` or `Strict` cookies usually prevent cross-site POSTs from a different site from carrying cookies. However, `SameSite=None; Secure` cookies, **same-site** but **cross-origin** scenarios, implementation exceptions, cookie policies, or other ambient authentication mechanisms can change the outcome. An HTML sample containing a form **does not by itself prove** that every environment is vulnerable.

### CSRF does not necessarily read the response

A malicious page may not be able to view the document or response body returned by the target application due to the **same-origin policy/CORS**. However, to change state, an attacker usually only needs to *send* the request; they do not need to successfully read the response body.

For example, if a request alters notification preferences or initiates a fund transfer request, the impact occurs on the server side even if the browser prevents another page's JavaScript from reading the result.

### Conceptual attack model

```text
Victim logs into app.example.test
   |
   +--> Browser holds app's cookie/session
   |
   +--> Victim opens attacker.invalid page
                |
                +--> Page creates a request to app.example.test
                |
                +--> Browser decides whether to send cookie/Basic/cert
                       based on URL, SameSite, credentials mode, policy ...
                |
                +--> Server receives request:
                      - Is there a valid credential?
                      - Is CSRF token/Origin verified?
                      - Are HTTP method and data accepted?
                |
                +--> If trusting credential without checking intent:
                       operation may execute as victim
```

This is a defensive diagram, not a guide to attacking real systems. URLs under `.test` or `.invalid` domains in this lesson are strictly for conceptual illustration.

## 2. Four key conditions for CSRF to succeed

Having "an application with cookies" does not automatically mean there is a CSRF vulnerability. Evaluate all four conditions together:

| Condition | Verification question | If not met |
| --- | --- | --- |
| **1. State-changing endpoint** | Is there a POST/PUT/PATCH/DELETE that mutates data, or a GET misused to cause side effects? | There is no exploitable operation on that request |
| **2. Browser auto-sends credential** | Are session cookies, cached Basic credentials, client certificates, or similar credentials attached when the request targets the destination? | The request may be anonymous and unable to perform authenticated actions |
| **3. Attacker can craft a syntactically valid request** | Can a form/navigation/fetch be crafted satisfying the endpoint's method, Content-Type, and data validation? | The server rejects the request before business logic |
| **4. Missing intent-binding barrier** | Is there no valid CSRF token, appropriate Origin/Fetch Metadata check, or other reliable anti-CSRF barrier? | The server rejects the request despite valid credentials |

In practice, account permissions, session state, resource-level authorization, rate limiting, and transaction re-authentication also come into play. **CSRF bypasses user intent; it does not escalate roles on its own.** A victim without ADMIN privileges cannot be turned into an ADMIN solely via a CSRF form if the server checks authorization properly.

### What is NOT part of CSRF

- The attacker **does not need to know the password** if the browser automatically carries the credential.
- The attacker **does not need to steal the session cookie** to trigger CSRF. Stealing a cookie is a different class of attack (session hijacking).
- The attacker **does not need to read the response**; the data write action may have already happened.
- The attacker cannot assume they can arbitrarily set `Authorization` or `X-CSRF-TOKEN` headers on a cross-site HTML form. That is the benefit of tokens/headers that are not auto-attached.
- CSRF does not replace XSS: an XSS flaw on the application itself can execute same-origin scripts, read tokens accessible to scripts, and bypass certain CSRF protections.

## 3. Which credentials do browsers "auto-send"?

There are multiple credential types, and not all behave like cookies.

### 3.1. Session cookies and WebSession

When an application uses session-based authentication, after login the browser typically holds a cookie containing a **session ID**, not the raw password. When sending a matching request to the server, the browser may auto-attach the cookie based on Domain, Path, Secure, SameSite, and cookie policy.

Spring WebFlux typically uses the `SESSION` cookie for the default `WebSession`, though this name is configurable and may differ when using Spring Session. Do not assume the name is `JSESSIONID` as in Servlet stacks.

Crucially: the browser attaches cookies based on **request destination and cookie rules**, not on whether the originating page is trusted. A valid cookie does not prove the user intentionally clicked a button in the target application.

### 3.2. Browser-cached HTTP Basic

With HTTP Basic, the browser can cache credentials for a protection realm and automatically resend the Authorization header on matching requests. Therefore, **HTTP Basic running in a browser is not inherently immune to CSRF**. Risk depends on the browser, auth mechanism, credential scope, and request.

An API called solely by non-browser clients that explicitly set `Authorization` each time generally has a different model. Never deduce "no CSRF possible" from "uses Basic" if browsers and cached Basic credentials are involved.

### 3.3. TLS client certificates and other ambient mechanisms

If the browser has already selected a client certificate for an mTLS connection and can automatically reuse that certificate when connecting to the target, the credential can also accompany the request without the attacker knowing the private key. Similarly, mechanisms that auto-attach credentials at the network/browser layer must be evaluated in the threat model.

### 3.4. JWT/refresh tokens placed in cookies

A JWT does not automatically prevent CSRF just because it is a "stateless" token. If the server trusts a JWT sent **in a cookie**, and the browser auto-attaches that cookie in a cross-site request according to policy, the request can still carry valid authentication.

Conversely, if the frontend only keeps a Bearer token in memory and explicitly sets:

```javascript
fetch("/api/profile", {
  headers: { Authorization: "Bearer " + accessToken }
});
```

then an ordinary cross-site page does not know `accessToken` to craft the same header. In this situation, classic CSRF risk is **generally lower**, though you must still protect against XSS, token leakage, misconfigured CORS, refresh token cookies, and other credential mechanisms. Never conclude "SPA/JWT is always safe from CSRF".

### Comparison table

| Authentication type | Can browser auto-send? | Implications for CSRF |
| --- | --- | --- |
| Session cookie | Yes, if cookie rules allow | Requires CSRF protection for unsafe actions |
| JWT in HttpOnly cookie | Yes, if cookie rules allow | Must still evaluate CSRF |
| HTTP Basic cached in browser | Possibly | Do not treat Basic as safe by default |
| Browser mTLS client certificate | Possibly | CSRF remains a risk to analyze |
| Bearer header attached by trusted JS from memory | Not automatically from attacker page | Classic CSRF is less favorable; XSS/token theft is a separate risk |
| Server-to-server-only API key | Not a browser credential | Typically not subject to traditional browser CSRF |

## 4. Same-origin and same-site are two different concepts

To know whether a cookie is sent, you must distinguish **origin** from **site**.

**Origin** consists of *scheme + host + port*. For example:

- `https://app.example.test` and `https://api.example.test`: different origins.
- `https://app.example.test:443` and `https://app.example.test:8443`: different origins.
- `https://app.example.test` and `http://app.example.test`: different origins.

**Site** in `SameSite` cookies typically evaluates scheme and registrable domain (*schemeful same-site*). For example:

- `https://app.example.test` and `https://evil.example.test`: may be **same site** yet **different origins**.
- `https://app.example.test` and `https://attacker.invalid`: **different sites**.
- `http://app.example.test` and `https://app.example.test`: different sites under schemeful same-site.

Domain examples may depend on the public suffix list; in production, evaluate actual domains and browser policies rather than judging by whether hostnames look "similar".

**Consequence:** `SameSite=Strict` or `Lax` protects many cross-*site* scenarios, but **is not a mechanism that blocks every cross-*origin* request**. A compromised sibling subdomain under the same site can initiate a same-site request to the main application. Thus, SameSite cannot completely replace CSRF token/Origin verification.

### Cookie domain/path

A host-only cookie is sent only to the host that issued it, not to all subdomains. A cookie with `Domain=example.test` has a broader scope. However, when a page from `evil.example.test` sends a request **to `app.example.test`**, the browser selects cookies based on the **request destination `app.example.test`**, not by giving cookies to the evil page. Therefore, the app's host-only cookie can still travel to the app in a request initiated by a sibling subdomain, if SameSite and other conditions allow it.

The `Path` attribute determines matching request paths; it is not a security boundary against an application that can choose any request path. Use host-only cookies, the `__Host-` prefix where appropriate, Secure/HttpOnly/SameSite, and minimal domain scope to reduce risk surface.

## 5. Cookie SameSite=Strict, Lax, None and their limitations

| SameSite | Does cross-site form POST usually send cookie? | Does cross-site top-level GET navigation usually send cookie? | Notes |
| --- | --- | --- | --- |
| `Strict` | No | No | Stricter, but can disrupt logins arriving from external links |
| `Lax` | Usually **no** | **Yes** for safe top-level navigation | Does not protect endpoints that mutate state via GET |
| `None; Secure` | Possibly, depending on third-party cookie policy/browser | Possibly | Suits some cross-site flows, requires full CSRF defense |
| SameSite omitted | Browser-dependent; many apply default Lax | Browser-dependent | Do not treat default behavior as a stable contract |

**Important exception:** some browsers apply a "Lax-allowing-unsafe" window for recently created cookies when an explicit SameSite attribute is missing. Do not assume every cross-site POST is always blocked simply because a cookie lacks configuration.

**SameSite is only an additional layer**, not a sole control. State-changing operations via GET can still be abused despite Lax cookies because browsers send cookies on top-level GET navigations. When same-site but cross-origin, SameSite also permits cookies under site semantics.

### Example of why state-changing GET is dangerous

Suppose an application is poorly designed:

```http
GET /account/delete?confirm=true HTTP/1.1
Host: app.example.test
Cookie: SESSION=...
```

A top-level navigation link from another site can carry the Lax cookie and trigger the mutation. This is an **anti-pattern**, not an endpoint you should build. Move state-changing actions to POST/DELETE, enforce corresponding CSRF checks, verify authorization, and add confirmation/re-authentication steps for high-risk actions.

**HTTP principle:** GET, HEAD, OPTIONS, and TRACE are considered safe in the default CSRF model, so applications must not silently turn them into write, delete, or money-transfer commands. "Safe" is an obligation of the app, not just a method label.

## 6. HTML forms, navigation, and fetch behave differently

### 6.1. Cross-origin HTML forms

Browsers allow page A to create an HTML form with `action` pointing to page B and submit it via POST. Forms can use common content types such as `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`; traditional forms **do not require JavaScript permission to read B's response**.

An illustration of a forged request using fictional domains, **not targeting any real system**:

```html
<!-- Defensive example only illustrating that forms can submit cross-origin -->
<form method="post"
      action="https://app.example.test/settings/notifications">
  <input type="hidden" name="enabled" value="false">
  <button type="submit">Continue</button>
</form>
```

This can only lead to state mutation if credentials are sent per browser policy, the endpoint accepts form submissions, and the server lacks appropriate CSRF/Origin verification. The attacker does not automatically read the response or forge a valid CSRF token.

### 6.2. fetch() and credentials mode

With the Fetch API, the default credentials mode is `same-origin`; a cross-origin `fetch` normally **does not send cookies/HTTP credentials** unless specified.

```javascript
// JavaScript from an arbitrary origin (browser API illustration):
fetch("https://api.example.test/settings", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ enabled: false })
});
```

- `credentials: "include"` asks the browser to send permitted credentials, but **does not bypass** SameSite, third-party cookie blocking, or cookie Domain/Path/Secure rules.
- `Content-Type: application/json` usually triggers a **CORS preflight** before the actual cross-origin fetch. If preflight is not approved, the browser may not send the actual request.
- Form-encoded or *simple requests* can be sent without a preflight; do not conclude from JSON/fetch behavior that all CSRF is blocked.
- CORS governs JS access to responses and part of preflighted request conditions; it is not a general replacement for CSRF protection.

### 6.3. Why "we enabled CORS" is not enough

CORS is a browser policy governing how scripts from another origin access resources. CORS is not backend authorization and does not render an already-sent form-based request harmless. If an API allows cookies and unsafe operations via form/simple requests, the server must still verify the legitimacy of the change.

**Distinguish clearly:**

| Statement | True/False |
| --- | --- |
| "CORS can prevent JS from another page from reading the response" | True depending on policy and conditions |
| "If CORS blocks reading the response, the request cannot have side effects" | **False** |
| "Every cross-site POST requires a preflight" | **False** |
| "fetch credentials include bypasses SameSite" | **False** |
| "If the browser does not auto-send credentials and the attacker has no token, classic CSRF is unlikely" | True assuming no other ambient credentials |
| "The server must still check authorization on every request" | True, CSRF does not replace authentication/authorization |

## 7. Synchronizer Token Pattern

Idea: the server generates an unpredictable random token bound to the appropriate session or context. The application delivers the token to a trusted page, then requires the client to send the token back **in a location the browser does not automatically add to every cross-site request**, such as a hidden form field or a request header.

Flow:

```text
Logged-in browser
   |
   | GET form page from real app
   v
Server issues/stores session's expected CSRF token
   |
   | HTML contains hidden _csrf field or JS reads meta
   v
Browser sends POST with:
   - cookie/session (browser may auto-attach)
   - _csrf / X-CSRF-TOKEN (provided by trusted page)
   |
   v
CsrfWebFilter compares actual token with expected token
   |
   +--> Valid: request proceeds to authentication/authorization/controller
   +--> Missing/invalid: rejected, typically 403
```

An attacker page on another origin may attempt to submit a form with the cookie, but **lacks the valid expected token**. The same-origin policy prevents an ordinary attacker from reading the target origin's HTML to extract the token. Thus the server asks not only "is the cookie valid?" but also "does the request carry anti-forgery data issued by the server?".

### How is a token different from a cookie?

A session cookie is usually auto-attached by the browser to requests. If you only issue a **CSRF cookie** and check solely for the presence of that cookie without requiring an independent value in a header/form, an attacker can still rely on the browser sending the cookie. With double-submit cookie, the server must compare **the cookie against the token submitted via header/form**, and stronger variants bind the token to the session (signed/session-bound double submit) to defend against cookie injection.

Do not place a static CSRF token inside HTML cached publicly for everyone. Do not put the token in URLs unnecessarily because URLs easily leak into logs, browser history, and Referer headers. Tokens must be managed via the framework's repository mechanism and session lifecycle.

## 8. How Spring Security WebFlux protects against CSRF by default

In Spring Security 6.x WebFlux:

- `CsrfWebFilter` is configured by Spring Security when CSRF is enabled (default).
- **Unsafe HTTP methods** such as POST, PUT, PATCH, and DELETE require a token under the default matcher; safe methods (GET/HEAD/OPTIONS/TRACE) typically skip token verification.
- The default repository is `WebSessionServerCsrfTokenRepository`: the expected token is stored in `WebSession`.
- Since Spring Security 6.0, `XorServerCsrfTokenRequestAttributeHandler` is used by default to mask outgoing token values to mitigate BREACH risk. The HTML token value may differ from the raw value stored in the repository because it is processed by the request handler; do not write manual comparisons.
- The token is exposed as `Mono<CsrfToken>` in a `ServerWebExchange` attribute under key `CsrfToken.class.getName()`. Laziness means the view/controller must access/subscribe to the appropriate publisher if the token needs to be rendered.
- By default, Spring Security WebFlux form login/logout also require CSRF on POST. Login CSRF and logout CSRF are distinct threats, not just data-mutation APIs.
- For SPAs/JSON, the token generally needs to be sent in an HTTP header like `X-CSRF-TOKEN`/`X-XSRF-TOKEN` depending on the repository/handler, rather than relying only on a form field.

**In this hands-on lesson, we keep default CSRF enabled. Do not "fix" HTTP 403 errors with `csrf.disable()`.**

### Why can GET /login be viewed while POST /login needs a token?

GET only retrieves the form; POST submits credentials and creates/changes login state. Login CSRF can force a victim's browser to log into an attacker-controlled account and perform actions under that account, causing identity confusion or leaking data into the attacker's account. Therefore Spring Security requires a token on POST login by default.

Logout CSRF is similar: a forged request can force the victim to log out, disrupting work or assisting another attack chain. `LogoutWebFilter` handles POST by default instead of turning a GET link into an immediate logout.

### CSRF vs. Authorization

A request with a **valid** CSRF token still requires authentication and authorization. The token proves the request likely reflects valid intent within the session context; it does not replace roles, ownership, rate limiting, or data validation. Conversely, a logged-in user with the required role can still receive 403 if a POST lacks CSRF.

## 9. Java 17+ Spring Boot WebFlux example: keeping default CSRF

The example below simulates toggling a setting (enabling/disabling notifications). Data is stored solely in an **AtomicInteger** so side effects are easy to observe; this is not a multi-user production persistence model.

### 9.1. Dependencies and project structure

For a Gradle project with the Spring Boot plugin and dependency management configured, include:

**`build.gradle`** (dependencies block):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Do not add `spring-boot-starter-web` for a pure reactive demo: if both MVC and WebFlux are on the classpath, Spring Boot typically selects Servlet. The project targets Java 17+, compatible with Spring Boot 3.x and Spring Security 6.x.

Files:

```text
src/main/java/example/csrf/
    CsrfDemoApplication.java
    SecurityConfiguration.java
    SettingsFormController.java
    SettingsController.java
src/main/resources/templates/
    settings-form.html
src/test/java/example/csrf/
    CsrfWebFluxTest.java
```

### 9.2. Main class

**`src/main/java/example/csrf/CsrfDemoApplication.java`**:

```java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

### 9.3. SecurityWebFilterChain and demo user

**`src/main/java/example/csrf/SecurityConfiguration.java`**:

```java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("local-test-password"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                .build();
    }
}
```

- `@EnableWebFluxSecurity` configures security for WebFlux, not Servlet `HttpSecurity`.
- `formLogin(Customizer.withDefaults())` provides the default login page at `GET /login` and handles `POST /login`.
- `httpBasic(basic -> basic.disable())` keeps the demo consistent with session cookie/form login instead of HTTP Basic prompts; this does **not** disable CSRF.
- `anyExchange().authenticated()` protects the settings form page and update endpoint; `GET /public/ping` is a public endpoint.
- **There is no `csrf.disable()` call**: the CSRF WebFilter continues enforcing checks on unsafe requests.
- The sample user password is for localhost/testing only. Production must load users from a managed source, store strong password hashes, and use HTTPS.

### 9.4. GET form page and Spring-issued token

To ensure the token is passed to the template, the controller retrieves the `Mono<CsrfToken>` placed by `CsrfWebFilter` on `ServerWebExchange`.

**`src/main/java/example/csrf/SettingsFormController.java`**:

```java
package example.csrf;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.result.view.Rendering;
import reactor.core.publisher.Mono;

@Controller
public class SettingsFormController {

    @GetMapping("/settings-form")
    public Mono<Rendering> form(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        return token.map(csrf -> Rendering.view("settings-form")
                .modelAttribute("_csrf", csrf)
                .build());
    }
}
```

The controller returns a publisher so Spring subscribes during the request. Do not call `block()`, do not fabricate fake tokens, and do not pass this token in link query strings.

**`src/main/resources/templates/settings-form.html`**:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Notification Settings</title>
</head>
<body>
<main>
    <h1>Change Notification Settings</h1>
    <form method="post" action="/settings/notifications">
        <label for="enabled">Receive notifications?</label>
        <select id="enabled" name="enabled">
            <option value="true">Yes</option>
            <option value="false">No</option>
        </select>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Save</button>
    </form>
</main>
</body>
</html>
```

Here `action="/settings/notifications"` is intentionally used instead of `th:action` to demonstrate **one explicit hidden CSRF input** via the model. If `th:action` is used with Spring/Thymeleaf CSRF integration, the engine may insert the token automatically; avoid rendering two inputs with the same name and inspect the final HTML. For deployments with a context path, the form action must be generated with the proper base path (e.g., using a Thymeleaf URL expression). Never hardcode literal tokens or copy a token from one session to another.

When a browser performs `GET /settings-form` from the real application, the server renders HTML with a valid token and the browser maintains the corresponding session cookie. A form crafted by an attacker's page cannot guess the valid token for this session.

### 9.5. State-changing endpoint and observing side effects

**`src/main/java/example/csrf/SettingsController.java`**:

```java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SettingsController {

    private final AtomicInteger acceptedChanges = new AtomicInteger();

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/settings/status")
    public Mono<String> status() {
        return Mono.fromSupplier(
                () -> "updates=" + acceptedChanges.get());
    }

    @PostMapping(
            path = "/settings/notifications",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> change(ServerWebExchange exchange) {
        return exchange.getFormData().map(form -> {
            String enabled = form.getFirst("enabled");
            if (!"true".equals(enabled) && !"false".equals(enabled)) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "enabled must be true or false");
            }
            acceptedChanges.incrementAndGet();
            return "notifications=" + enabled;
        });
    }

    // Used to verify simulated data in same-package tests.
    void resetForTests() {
        acceptedChanges.set(0);
    }

    int updateCount() {
        return acceptedChanges.get();
    }
}
```

**WebFlux note:** `ServerWebExchange.getFormData()` returns `Mono<MultiValueMap<String,String>>`. That is the explicit way to retrieve the `enabled` field from the **form body**. Do not mistakenly assume `@RequestParam` in WebFlux automatically reads form-encoded bodies in every case like Servlet MVC; in WebFlux it primarily binds request query parameters. This lesson uses `getFormData()` to avoid ambiguity.

`acceptedChanges` is purely an **in-memory shared counter to illustrate side effects**, not a per-user configuration table. A real system must store settings per user ID/tenant and enforce owner/authorization checks in the service or database; a CSRF token **does not replace resource-level authorization**.

### 9.6. When is the controller invoked?

If a POST request arrives:

- **Missing CSRF token**: `CsrfWebFilter` rejects earlier; `change(...)` **does not** increment the counter.
- **Valid token but unauthenticated**: authentication/authorization rejects or redirects to login; `change(...)` does not write data.
- **Authenticated, valid token, valid form**: request passes the security chain; counter increments by 1.
- **Authenticated, valid token, but invalid `enabled`**: controller returns 400; counter does not increment.
- **GET /settings/status**: does not change the counter, only displays its value.

This is a verifiable distinction. The browser auto-sending a cookie only gives the request an identity; the token and authorization also determine whether the action executes.

## 10. Testing with WebTestClient: missing CSRF, valid CSRF, and side effects

Spring Security Test supports `WebTestClient` via `springSecurity()`, `mockUser(...)`, and `csrf()`. The test below builds a mock server from ApplicationContext to invoke WebFlux security filters and controllers **without opening a real port**.

**`src/test/java/example/csrf/CsrfWebFluxTest.java`**:

```java
package example.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfWebFluxTest {

    @Autowired ApplicationContext context;
    @Autowired SettingsController settings;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        settings.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicGetDoesNotNeedCsrf() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() {
        client.get().uri("/settings/status")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches("Location", ".*login.*");
    }

    @Test
    void authenticatedSafeGetNeedsNoCsrf() {
        client.mutateWith(mockUser("learner"))
                .get().uri("/settings/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("updates=0");
    }

    @Test
    void defaultLoginPageExists() {
        client.get().uri("/login")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(html.contains("username")));
    }

    @Test
    void customFormContainsCsrfInput() {
        client.mutateWith(mockUser("learner"))
                .get().uri("/settings-form")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(html.contains("name=\"_csrf\"")));
    }

    @Test
    void authenticatedPostWithoutCsrfIsBlocked() {
        client.mutateWith(mockUser("learner"))
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "false"))
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, settings.updateCount());
    }

    @Test
    void authenticatedPostWithCsrfChangesState() {
        client.mutateWith(mockUser("learner"))
                .mutateWith(csrf())
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "false"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("notifications=false");

        assertEquals(1, settings.updateCount());
    }

    @Test
    void invalidFormIsRejectedEvenWithCsrf() {
        client.mutateWith(mockUser("learner"))
                .mutateWith(csrf())
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "invalid"))
                .exchange()
                .expectStatus().isBadRequest();

        assertEquals(0, settings.updateCount());
    }

    @Test
    void loginPostWithoutCsrfIsBlocked() {
        client.post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void loginPostWithCsrfCanAuthenticate() {
        client.mutateWith(csrf())
                .post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-test-password"))
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Run from the project directory containing the Gradle Wrapper:

```bash
./gradlew test --tests example.csrf.CsrfWebFluxTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.csrf.CsrfWebFluxTest
```

**Expected result:** 10 tests PASS when the project has compatible files and dependencies. This is an expectation from the example code, **not** evidence that tests were executed in the workspace.

### What has and has not been verified

- The GET tests show that safe methods do not need a CSRF token and protected endpoints still require authentication.
- The POST test without a token using `mockUser` proves **authentication does not replace CSRF**; 403 and counter 0 show the controller executed no side effect.
- The POST test with `csrf()` proves a valid token combined with authentication permits the update.
- The login POST test without CSRF shows **login is also an unsafe action**.
- `mockUser(...)` is a mocked Authentication in tests, **not proof that a real browser auto-attached a cookie**. Proving cookie/SameSite behavior requires browser integration tests under controlled origins/sites.
- Spring Security Test's `csrf()` supplies a valid CSRF token for the mock request; the test does not verify byte-for-byte token randomness or session storage details.
- Tests share a single context and counter, running sequentially by default. If enabling parallel tests, isolate instances/test state or avoid resetting a shared counter.

## 11. Real browser testing: verifying when cookies auto-send

To inspect auto-sending conditions, set up a **test environment under your own control**, with the main application and another origin or same-site cross-origin host. Never test against third-party accounts or systems.

Defensive scenario:

1. Access the main application over HTTPS and log in with a real browser.
2. Open DevTools -> Application/Storage -> Cookies, observe the cookie's **name**, `Domain`, `Path`, `Secure`, `HttpOnly`, and `SameSite`; do not share raw cookie values.
3. On the other test origin, submit a simulated POST form to a non-sensitive test endpoint on **your own test system**.
4. In DevTools -> Network, check whether the request is sent and whether the cookie is attached per SameSite/domain/path/browser policy; avoid exporting HAR files containing credentials.
5. Enable Spring Security CSRF: a POST missing the token must be rejected, even if the browser attaches the cookie.
6. Submit a POST from the application's real form containing the token: allowed when logged in and authorized.
7. Repeat with another origin that is same-site (sibling subdomain test) to observe that SameSite is not equivalent to same-origin.
8. Verify GET requests cause no data mutation; if any do, fix the endpoint design.

**Never look solely at HTTP 403 and conclude the cookie was sent.** A 403 can come from CSRF before the authentication step. Inspect credential-sending conditions separately and control non-sensitive test data.

### Browser observation table by scenario

| Source -> destination | Cookie | Request type | Common expectation |
| --- | --- | --- | --- |
| Same origin, logged in | Valid cookie | Real POST form + CSRF token | Passes both authentication and CSRF |
| Cross-site, Strict cookie | Strict cookie usually not sent | Form POST | Usually missing session, plus CSRF still protects |
| Cross-site, Lax cookie | Lax cookie usually not sent | Form POST | Many browsers block ambient credentials; exceptions depend on policy |
| Cross-site, Lax cookie | Lax cookie may be sent | Top-level GET | Extremely dangerous if GET mutates state |
| Cross-site, None; Secure cookie | Cookie may be sent if browser allows | Form POST | CSRF token must block forged request |
| Cross-origin but same-site | Cookie may be sent | Form POST | SameSite does not block solely for different origin |
| Cross-origin fetch, default | Usually excludes cross-origin credentials | `fetch()` | Default credentials mode is `same-origin` |
| Cross-origin fetch, include | Cookie sent only if policy allows | `fetch(... credentials:"include")` | Does not bypass SameSite/third-party blocking |

These are common rules, not a guarantee that every browser, embedded webview, or policy behaves identically. Results also depend on redirects, scheme, cookie set-time, domain, third-party cookie restrictions, and how the server handles requests.

## 12. Origin, Referer, and Fetch Metadata: additional defense

A CSRF request can be further prevented by checking the request source:

- `Origin` indicates the originating origin in many modern request types. The server can require it to match a **trusted origin** for state-changing operations.
- `Referer` can help verify the source where applicable, but may be absent due to privacy/referrer policies; do not bypass checks for every request missing the header without an explicit policy.
- `Sec-Fetch-Site` distinguishes `same-origin`, `same-site`, `cross-site`, and `none` in supporting browsers. `Sec-Fetch-Mode`/`Sec-Fetch-Dest` help define policies that intentionally block cross-site unsafe navigation/fetch.
- Fetch Metadata headers are **defense-in-depth** and must account for older clients, browser limitations, proxies, and allowed integrations.
- If legitimate cross-origin access is needed (e.g., SSO or embedded apps), use an explicit allowlist, test thoroughly, and avoid arbitrary wildcard origins.

**Do not replace tokens with "only check if Referer contains the domain name" via substring matching**: strings can spoof hostnames (e.g., `app.example.test.attacker.invalid`). When checking Origin, parse scheme/host/port and match the exact origin; ensure reverse proxy/forwarded headers are configured securely.

## 13. SPA, JSON API, and CookieServerCsrfTokenRepository

For an SPA using session cookies, the browser can send `fetch` requests with cookies. The application's trusted JavaScript needs a way to obtain the token and put it into a header, typically `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on configuration.

In Spring Security WebFlux, the repository can be replaced with `CookieServerCsrfTokenRepository` for suitable SPA patterns. However:

1. A CSRF cookie can be read by client-side JavaScript if configured accordingly (non-HttpOnly); that is a **trade-off**, not a default setting to enable system-wide.
2. SameSite, Secure, Path, Domain, and trusted origins must be evaluated together.
3. Since Spring Security 6.x, the default `XorServerCsrfTokenRequestAttributeHandler` processes tokens for HTML/BREACH protection. Raw tokens in cookies and masked tokens in forms/headers may need handling via the appropriate request handler; **do not just swap the repository and expect every SPA to work automatically**.
4. If the frontend uses a Bearer token in a header with **no auto-sent cookie/Basic/mTLS**, classic browser CSRF may not apply in the same way; do not disable CSRF if the system still issues session cookies or refresh token cookies usable on unsafe endpoints.
5. Avoid creating a public `GET /csrf` endpoint that returns tokens/cookies with overly permissive CORS allowing an attacker website to read the token. A CSRF token is not an API key, but if disclosed cross-origin it loses its defensive value.
6. When tokens expire or sessions time out, the UI may encounter 403; provide controlled token refresh/re-login flows rather than disabling CSRF or reverting to default permit.

### Conceptual example of a valid same-origin fetch

```javascript
// Runs from trusted JavaScript loaded by your application.
// csrfToken is issued by the backend and received by the frontend over a valid channel.
fetch("/api/settings", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ theme: "dark" })
});
```

This is an **illustrative snippet**, not runnable standalone: `csrfToken` and the `/api/settings` endpoint are not defined in the demo project. For JSON APIs, choose a repository/handler so the backend validates the right header; avoid copying form-encoded examples without adapting to the SPA architecture.

## 14. Special cases: login, logout, upload, and GET with wrong semantics

### 14.1. Login CSRF

A login CSRF attack can force a victim's browser to log into another account. While this does not always let the attacker hijack the victim's own account, it can cause the victim to act and save data under the attacker's account. Because login changes authentication state, `POST /login` needs a token. Spring Security WebFlux handles this by default when CSRF is enabled.

### 14.2. Logout CSRF

If logout is permitted via GET, an attacker can use navigation/image/link elements to log the user out. Default WebFlux logout requires `POST /logout` and CSRF. Do not switch the matcher to GET just for an easier logout button; use a POST form or application JavaScript sending a POST with the token.

### 14.3. Multipart upload

Multipart bodies are sometimes processed/written to temporary files before the CSRF token inside the body is checked. With JavaScript, sending the token in a header reduces this risk. Spring Security WebFlux offers `tokenFromMultipartDataEnabled(true)` when extracting the token from multipart bodies is needed, but you must weigh the impact and enforce permission/upload limits. Do not assume enabling multipart CSRF has zero body-processing cost.

### 14.4. State-changing GET

This is a design flaw that causes damage despite the default CSRF filter because safe methods normally skip token checks. The fix is to **change the HTTP method and semantics**, not merely append a token to a GET URL. Never use GET to delete accounts, transfer money, reset passwords, or grant privileges.

### 14.5. Stateless does not mean immune

A self-contained JWT stored in a cookie can still be auto-sent to the backend. A "stateless" system using JWT cookies still needs CSRF evaluation. Server statelessness does not determine whether the browser sends credentials; **how credentials are delivered in the request** is the deciding factor.

## 15. When should you customize CSRF in Spring Security WebFlux?

### 15.1. Keep defaults for browser apps

If the app has form login, session cookies, and state-changing requests, **keeping default CSRF** is the right starting point. Templates must include the token properly in forms/headers. Test 403 on missing tokens and success with actual tokens.

### 15.2. Exempting a specific endpoint

Certain machine-to-machine webhooks or endpoints authenticated by dedicated signatures **without browser cookies** may not need CSRF tokens. You can configure `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` with an appropriate matcher, but you must prove there are no ambient credentials and avoid accidentally exempting browser-facing endpoints.

Do not copy a `permitAll` matcher as justification to skip CSRF: public endpoints can also mutate state. Separate threat modeling and integration tests are required.

### 15.3. Disable CSRF completely only when the threat model permits

An API serving solely non-browser clients, authenticated via Bearer tokens **explicitly supplied only in headers**, with no auto-sent sessions/cookies/Basic credentials, may choose to disable CSRF after a risk assessment. That does not apply universally to WebFlux or all REST APIs; especially if browser auth, login, or refresh cookies are added later, prior assumptions may no longer hold.

Configuring `.csrf(csrf -> csrf.disable())` removes the framework's CSRF barrier, so use it only with justification, review, documentation, and tests. In the **main demo, this is not used**.

## 16. Common mistakes

| Symptom or misconception | Problem | How to fix |
| --- | --- | --- |
| "We have CORS so we're safe from CSRF" | Browsers can send forms/simple requests even if scripts cannot read responses | Use CSRF tokens/Origin and safe HTTP methods |
| "JWT prevents CSRF" | A JWT in a cookie is still auto-sent by the browser | Distinguish cookie-stored tokens from Bearer headers |
| "Basic Auth prevents CSRF" | Browsers can auto-attach cached Basic credentials | Evaluate ambient Basic auth in browsers |
| "SameSite=Lax blocks all CSRF" | Cross-site top-level GET sends cookies; same-site cross-origin can still send | Never mutate state via GET; keep tokens |
| "SameSite protects all subdomains" | Same-site different origin can still send cookies to target | Origin/CSRF tokens, subdomain governance |
| "Disable CSRF because POST got 403" | Removes defense line instead of fixing the form | Fetch token, keep cookie, send proper hidden field/header |
| "CSRF token is the same as session cookie" | Cookies are auto-attached; tokens must go via non-auto-attached fields/headers | Synchronizer token pattern |
| "Once authenticated, POST should succeed" | Authentication does not prove intent to perform that POST | Require CSRF for unsafe methods |
| "Every cross-origin fetch sends cookies" | Fetch defaults to `same-origin` | Understand credentials mode and cookie policy |
| "credentials include bypasses SameSite" | Browsers still enforce SameSite/third-party cookie policies | Evaluate cookie attributes |
| "JSON is immune to CSRF" | Weak Content-Type checks, misrouting, polyglot forms, or bad CORS can break assumptions | Strict Content-Type, tokens/Origin, real request tests |
| "GET deletes data but is still safe" | CSRF filters typically skip GET | Use proper unsafe methods and tokens |
| "Only check Referer contains domain string" | Vulnerable to hostname spoofing and missing headers | Exact Origin matching and clear fallback policy |
| "Just use `CookieServerCsrfTokenRepository` and done" | Raw/masked tokens, headers, and cookie flags must match | Configure SPA per Spring Security version |
| "Token must be in URL query string" | Leaks via logs, history, Referer | Use form body or header |
| "Cross-origin forms cannot POST" | HTML forms can send requests without reading responses | Rely on tokens/Origin and authz instead of CORS |
| "Testing HTTP 403 proves cookies weren't sent" | 403 may come from CSRF before auth | Inspect request cookies/credentials separately |
| "CSRF protection replaces authorization" | Having a token does not mean permission to modify a resource | Still check role/owner/tenant |
| "XSS is unrelated" | Same-origin XSS can abuse tokens and credentials | Prevent XSS, use CSP, output encoding |
| "HttpOnly cookies block CSRF" | HttpOnly only stops JS reading the cookie; browser still sends it | HttpOnly + CSRF token + SameSite |

## 17. Secure implementation checklist

1. **Inventory state-changing actions**: POST/PUT/PATCH/DELETE, and especially fix any GET with side effects.
2. **Classify all authentication sources**: session, Basic, JWT cookie, refresh token cookie, client certificate, custom cookies. Identify what the browser auto-sends.
3. **Define origin/site/cookie settings**: Domain, Path, Secure, HttpOnly, SameSite, TLS proxy, and target browser policies.
4. **Keep CSRF tokens** for unsafe requests with ambient credentials. Ensure forms/meta/headers receive tokens via trusted channels, bound to the session, without cross-origin leakage.
5. **Verify login/logout** also require CSRF; do not allow GET to log out.
6. **Defense in depth**: SameSite, Origin/Referer when reliable, Fetch Metadata, Content-Type validation, rate limiting for sensitive operations.
7. **Keep authentication/authorization complete**: a valid token does not replace owner/tenant/role checks.
8. **Prevent cross-origin token reading**: review CORS, token endpoints, CDN/template caching, XSS flaws, and session sharing.
9. **Test with browsers and WebTestClient**: safe GET, POST missing token, wrong token, valid token, anonymous, session timeout, and browser cookie policies.
10. **Monitoring and error handling**: distinguish `CsrfException`/403 from wrong password or role-based 403, never log raw tokens/cookies/passwords, include correlation IDs.
11. **Test across environments**: reverse proxy, HTTPS, subdomains, multi-instance/session stores, legitimate cross-origin SPAs.
12. **Review on auth changes**: switching from Bearer-only to cookies or enabling form login can completely change the CSRF threat model.

## 18. Questions and self-practice exercises

1. A victim has a `SameSite=Strict` session cookie and is on `attacker.invalid`. When the page submits a cross-site POST to the app, is the cookie sent? What happens if the attacker controls a **same-site** subdomain?
2. A bank uses `GET /transfer?amount=100` to transfer money. Why might `SameSite=Lax` still fail to protect it?
3. An SPA calls APIs using `Authorization: Bearer ...` stored in memory, without cookies or Basic auth. Explain how classic CSRF differs from an SPA storing a JWT in an HttpOnly cookie.
4. Write a `WebTestClient` test that sends a POST with `mockUser` **without `csrf()`**: assert 403 and no side effect occurred.
5. Use `csrf()` in a test and assert the POST is processed. Why does this test not prove a cross-site browser sends cookies?
6. Open the Thymeleaf form in the demo, inspect whether hidden `_csrf` is rendered and the session cookie matches. Then remove the hidden field in a test environment: what happens?
7. Create a test page on a different origin, submit a form to a **demo-only** endpoint, and compare browser cookie settings Strict/Lax/None. Record Site, Origin, and method.
8. Add an endpoint `POST /admin/settings` requiring ADMIN. Supply a valid token while logged in as USER; prove CSRF does not bypass authorization.
9. Simulate session timeout: the token on the old form is no longer valid; design how the UI safely informs the user and fetches a new form/token.
10. If scaling the app to multiple instances with WebSession shared via a backend store, identify where the expected CSRF token is kept and the impact of session invalidation.
11. Add a Fetch Metadata policy in a test environment and test same-origin, same-site, cross-site, and clients omitting the header. Do not treat headers as the sole solution.
12. Write a short threat model document stating: which credentials are auto-sent? Which unsafe actions exist? Which browsers? Where is the CSRF token? How are cookies and CORS configured? What are the deny status codes and logging behavior?

## Summary

**CSRF succeeds only when the browser can send valid credentials to an application without the origin page's cooperation, and the server mistakes "a request with identity" for "a user intending to perform an action".** All four conditions must be examined together: a state-changing action, ambient credentials being sent, a forgeable request, and missing CSRF/source verification.

In Spring Security WebFlux, the standard defense is **keeping `CsrfWebFilter` enabled by default**, keeping the expected token in WebSession, rendering the actual token in forms or headers, and rejecting unsafe requests lacking the token. CORS, SameSite, HttpOnly, JWT, and HTTPS each have distinct roles but do not replace comprehensive CSRF protection. Tests must verify not only HTTP status codes, but also **no side effect** when CSRF fails.

## Official References

- [Spring Security 6.5 — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — CSRF and browser credential auto-sending](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Testing WebFlux / WebTestClient](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — Testing CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [MDN — CSRF](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
