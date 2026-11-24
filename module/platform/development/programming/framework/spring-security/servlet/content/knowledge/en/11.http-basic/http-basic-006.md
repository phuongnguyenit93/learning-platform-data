# CSRF When Browsers Automatically Send HTTP Basic Credentials

> Scope: **Spring Security on the Servlet stack** (Spring MVC, `SecurityFilterChain`, `HttpSecurity`), HTTP Basic in browsers, Java 17+, Spring Boot 3.x, and Spring Security 6.x. The focus is **CSRF risk when browsers auto-attach credentials**, not a general overview of all authentication types.

## 1. Key Point: HTTP Basic Does Not Automatically Eliminate CSRF

**Cross-Site Request Forgery (CSRF)** occurs when an attacker's website causes a victim's browser to send a request to a target website, and the target website treats that request as performed by the authenticated victim. What matters is not merely whether cookies exist, but **whether the browser automatically attaches a credential that the target website trusts**.

With **HTTP Basic authentication**, a browser may store/cache the credential pair after the user enters credentials for an origin and protection space. On subsequent matching requests, the browser may **automatically send the `Authorization: Basic ...` header** without the malicious page's JavaScript knowing the username/password. Exact behavior depends on the browser, authentication cache, URL scope, and user-agent policy; **never assume every browser sends Basic preemptively in every situation**.

Even so, if a browser **can automatically attach Basic credentials to a cross-site request**, the target website can face CSRF risks similar to a session-cookie app. That is why Spring Security's documentation and defaults do not treat “using HTTP Basic” as enough to declare all POSTs safe from CSRF.

**Quick rules of thumb:**

- **Browser auto-carries credentials** (session cookies, cached HTTP Basic, or equivalent ambient authority) → evaluate CSRF seriously.
- **Dedicated client explicitly attaching credentials per request**, e.g., a service calling an API with an `Authorization` header that a malicious website cannot make a browser attach automatically → the CSRF surface may differ; only exempt when **proven** the API does not accept browser auto-sent credentials.
- **Stateless does not mean CSRF-safe.** CSRF is about **how the browser constructs and authenticates requests**, not whether the server uses login sessions.
- **CORS is not a CSRF defense mechanism.** CORS mainly controls whether JavaScript on another origin can read responses and cross-origin fetch rules; a cross-site HTML form can still submit a request even if JavaScript cannot read the response.
- **SameSite cookies do not solve HTTP Basic on their own:** the SameSite attribute applies to cookies, not a policy disabling browser auto-sent Authorization headers.

## 2. How Does HTTP Basic Run in Servlet?

HTTP Basic uses an HTTP authentication challenge/response mechanism. For a request lacking credentials to a protected resource, the server may respond:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="example"
```

The browser may display a username/password prompt, remember them for the matching scope, and send:

```http
GET /profile HTTP/1.1
Host: app.example
Authorization: Basic <base64-of-username-colon-password>
```

The Base64 string is **only an encoding, not encryption or hashing**. When transmitting HTTP Basic over a network, **HTTPS/TLS is mandatory in real deployments** to protect credentials. Never log raw Authorization headers, and never place Basic strings in URLs, JavaScript telemetry, or public config files.

In Spring Security Servlet, the high-level flow is:

```text
Browser HTTP request
        |
        v
Servlet FilterChainProxy selects SecurityFilterChain
        |
        +--> SecurityContext and related filters
        |
        +--> CsrfFilter (if request is in protected scope)
        |      |
        |      +--> POST/PUT/PATCH/DELETE missing or invalid CSRF token
        |                -> 403, may stop before Basic authentication
        |
        +--> BasicAuthenticationFilter (when chain enables httpBasic)
        |      |
        |      +--> extracts Basic Authorization credentials if present
        |      +--> passes unauthenticated token to AuthenticationManager
        |      +--> AuthenticationProvider verifies credential
        |      +--> saves SecurityContext per policy
        |
        +--> AuthorizationFilter
        |      |
        |      +--> authenticated()/hasRole(...)/... rules
        |
        v
Spring MVC controller (if permitted)
```

This is a **conceptual diagram**, not a list of every filter or an immutable ordering guarantee across all configurations. Spring Security has many extension points and can run multiple `SecurityFilterChain`s by matcher. When CSRF is enabled, a POST missing a token can be rejected **even when** it carries valid HTTP Basic credentials.

Specifically: `http.httpBasic(...)` configures Basic authentication. It **does not implicitly mean** `http.csrf(...disable...)`; those are two separate decisions.

## 3. Attack Mechanism: The Browser Acting as Identity Carrier

Suppose `https://accounts.example` has:

- `GET /settings`: view configuration.
- `POST /settings/email`: change the user's contact email address.
- A security chain accepting HTTP Basic.
- A POST endpoint checking only `authenticated()`, with no CSRF check or equivalent origin-binding check.

The user has authenticated to the target app and the browser still caches Basic credentials. Later, the victim opens `https://untrusted.example` controlled by an attacker. That page can contain an HTML form submitting a POST to the target site:

```html
<!-- Illustrates the request submission mechanism; address and data are fictional. -->
<form action="https://accounts.example/settings/email" method="post">
  <input type="hidden" name="email" value="changed@example.invalid">
  <button type="submit">Continue</button>
</form>
```

A cross-origin page **can submit an HTML form** within normal browser constraints; it does not require CORS response-reading privileges to trigger a state-changing action. The malicious page cannot read the victim's Basic password and does not necessarily get to set a custom `Authorization` header itself. The risk arises when **the browser automatically reuses cached Basic credentials on the request to the target origin**.

```text
        User already logged in with Basic to accounts.example
                                |
                   Browser may cache credentials
                                |
                        Opens untrusted.example
                                |
                  Malicious page creates HTML form POST
                                |
                                v
Browser sends request to accounts.example
    [may automatically attach Authorization: Basic ...]
                                |
                                v
                 Backend sees a valid principal
                                |
                    If checking only authenticated()
                                |
                    Action may be executed
```

A valid, unpredictable **CSRF token** bound to a trusted context controlled by the target website distinguishes a POST originating from a legitimate workflow from a POST initiated by an external page. This is a common defense; production designs also need appropriate Origin/Referer or Fetch Metadata controls and XSS prevention.

### A Counterintuitive Claim

Someone might argue:

> "My website doesn't use session cookies; every request needs a Basic header. CSRF only happens with cookies, so no CSRF token is needed."

That argument is **missing a condition**. A more accurate statement is: "If an attacker-controlled web origin cannot cause a browser to automatically attach a credential accepted by the API and no other ambient credential exists, CSRF risk on that call path drops substantially." With **browser-cached Basic**, that condition **may not hold**.

## 4. Conditions, Limits, and What Should Not Be Claimed Absolutely

Exploitability depends on several factors:

1. **Are credentials already in the browser?** The browser might not have them or may have cleared its cache after closing, logout, or realm changes.
2. **HTTP authentication scope**: origin, scheme, port, realm, and path/protection space can affect whether the browser reuses Basic credentials.
3. **Does the browser auto-send the Basic header on that cross-site request?** User agents differ in behavior and safeguards. Some do not attach preemptively, some re-prompt on challenge, and some restrict third-party contexts.
4. **Can the request be issued from an HTML form?** Actions accepting a plain POST form have a different surface from actions requiring JSON + custom headers.
5. **Does the server validate a CSRF token or origin binding?** When properly validated, valid credentials alone are not enough to execute the action.
6. **Does the action have real impact?** A read-only GET has lower CSRF impact than a POST changing email, password, payout address, or access rights. Even so, GET **must never** be used for state-changing operations.

Do not conclude “every browser will auto-send Basic credentials on every cross-site POST”; nor conclude the opposite, that modern browsers have automatically eliminated the risk. **Anti-CSRF design must not gamble on a browser's authentication cache behavior.**

## 5. CORS, SOP, Preflight, and SameSite Are Not the Same Thing

### 5.1. Same-Origin Policy Blocks Reading Responses, Not Always Sending Requests

Same-Origin Policy (SOP) typically prevents scripts from `untrusted.example` from reading responses from `accounts.example`. Yet browsers support longstanding cross-origin operations: form submissions, navigations, image loads, and certain other requests. Because CSRF **only needs the server to perform the action**, an attacker does not necessarily need to see the response.

In particular, an HTML form with `method="post"` and `application/x-www-form-urlencoded` can be sent cross-site without a CORS preflight, unlike a `fetch()` with custom headers. Hence setting strict `Access-Control-Allow-Origin` headers is **not enough** to ensure a form POST never reaches the server.

### 5.2. Cross-Origin Fetch and Preflight

A cross-origin `fetch` sending `Authorization` or custom headers normally obeys CORS/preflight rules; malicious JavaScript **cannot read** credentials stored for another origin just by knowing the URL. Yet this is **no** general guarantee against HTML forms or browser ambient authentication.

If an API requires a custom `X-CSRF-TOKEN` header and validates the CSRF token server-side, another attacker site faces an added barrier; still, the core strength comes from **the valid token not being known to the attacker**, not merely the header name. If a server opens CORS carelessly and lets untrusted origins access credentialed responses or token endpoints, the policy can be undermined.

### 5.3. SameSite Is Not a Property of Basic Authorization

`SameSite=Lax`/`Strict` are **cookie** attributes. They can reduce when cookies are sent cross-site, yet **do not directly govern** whether the browser auto-sends `Authorization: Basic ...`. Therefore, an app “without auth cookies” cannot cite SameSite as its sole reason to disable CSRF.

If an application uses both Basic and session cookies, analyze **both** mechanisms. Using `SessionCreationPolicy.STATELESS` also does not prove there are no ambient Basic credentials.

### 5.4. Origin, Referer, and Fetch Metadata

Browser requests can carry `Origin`, `Referer`, and Fetch Metadata headers such as `Sec-Fetch-Site`. These are useful signals for rejecting unsafe cross-site requests in many architectures, though you must account for browser support, redirects, proxies, privacy policies, and legitimate flows. **Do not merely check that a header exists** and assume non-browser clients cannot spoof it. When using such a policy, validate server-side and write tests for missing headers, invalid origins, cross-origin/cross-site requests, and valid cases.

## 6. How Does Spring Security Servlet Protect Against CSRF?

In standard Spring Security Servlet setups, `CsrfFilter` is enabled by default. Java configuration:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is a **configuration fragment**, requiring appropriate imports/`@Configuration`/`@Bean`. Without `csrf(...disable...)`, CSRF protection remains active.

The default protection rule typically applies to **every method not in the safe list** `GET`, `HEAD`, `TRACE`, `OPTIONS` (e.g., `POST`, `PUT`, `PATCH`, `DELETE`). A method being treated as safe in the filter **does not make a state-mutating GET safe**. The backend must genuinely keep GET/HEAD free of business side effects.

Related components:

- **`CsrfFilter`**: blocks protected requests lacking a valid token.
- **`CsrfTokenRepository`**: supplies/stores/loads the expected CSRF token. Standard web configs may use `HttpSessionCsrfTokenRepository`.
- **`CsrfTokenRequestHandler`**: exposes the token on the request and resolves the submitted token; Spring Security 6 features deferred tokens and masking/BREACH protection for rendering.
- **`CsrfToken`**: holds the header name, parameter name, and token value so forms/JavaScript submit per contract.
- **`AccessDeniedHandler`**: handles responses for access denials such as missing/invalid CSRF tokens, typically returning status 403.

**Very common confusion:** HTTP Basic authentication can be completely valid, yet a POST missing a CSRF token still returns **403**. That is not proof of a wrong password or a `DaoAuthenticationProvider` error.

### Paths of Opposing Requests

```text
GET /form + Basic credential
    -> not an unsafe method
    -> may render HTML form with CSRF token
    -> status 200 if user is valid

POST /change + Basic credential
    -> unsafe method
    -> missing CSRF token
    -> CsrfFilter rejects (typically 403)
    -> state change is NOT executed

POST /change + Basic credential + valid CSRF token
    -> passes CsrfFilter
    -> Basic credential verified
    -> authorization authenticated()
    -> controller executes and returns 200
```

If a request lacks Basic credentials and lacks a CSRF token, it may be blocked by CSRF **before** the HTTP Basic entry point returns 401. Never infer from “no 401” that HTTP Basic was disabled.

## 7. When Can You Consider Disabling or Ignoring CSRF?

There is no good rule saying “all APIs using Basic disable CSRF”. Map out **which paths can be called by a browser with automatic credentials**:

| Client type / mechanism | How credentials reach the request | How to think about CSRF |
| --- | --- | --- |
| Browser using HTTP Basic with cached credentials | Browser can auto-send credentials for protected origin | **Keep CSRF protection** for unsafe operations |
| Browser using session cookies | Cookies are normally auto-sent by browser per policy | **Keep CSRF protection** per browser threat model |
| SPA using cookie-based auth | Browser auto-sends valid cookies; JS sends body/headers | Needs CSRF token + cookie/Origin/Fetch Metadata policy |
| Machine-to-machine API accepting only client-attached bearer tokens | Attacker website does not implicitly hold a token to auto-send | Can be designed without CSRF tokens if ambient credentials are truly rejected |
| CLI/native mobile client explicitly sending `Authorization: Basic` | Client code supplies header per request | Browser CSRF may not be primary threat, yet TLS/credential hygiene still required |
| Same endpoint accepts both browser Basic and machine tokens | Browsers still have an auto-credential path | **Do not exempt CSRF just because one non-browser client exists** |
| State-changing requests via GET | Should not exist | Fix the HTTP design; do not rely on GET skipping the CSRF filter |

**Before disabling:** inspect reverse proxies, browser clients, login challenges, session cookies, basic-auth caches, and endpoints that could receive default credentials. A loose claim like “this is a stateless REST API” is **insufficient**.

### Only Exempt Routes That Truly Do Not Use Browser Credentials

Spring Security can customize matchers to ignore CSRF on specific endpoints. Example syntax:

```java
.csrf(csrf -> csrf.ignoringRequestMatchers("/machine/**"))
```

This is a **fragment** for `HttpSecurity`, not advice to enable in every app. Consider it only when `/machine/**` is independently secured by a mechanism **that does not accept ambient browser credentials**, backed by a threat model and tests. If the route still accepts browser-cached Basic, ignoring CSRF can create a vulnerability. With multiple filter chains, matchers must also cover the right chain and HTTP methods.

Avoid `.csrf(csrf -> csrf.disable())` across an entire web chain just to make `curl -X POST` easier. Test clients can supply a CSRF token instead of weakening production.

## 8. Spring Boot 3.x / Java 17+ Example: HTTP Basic Plus CSRF Form Token

To observe clearly, let's build a small Servlet app with:

- `GET /form`: returns an HTML form with a **hidden CSRF token** generated by Spring Security.
- `POST /change`: increments a demo counter representing a **state-changing** operation; not payment logic.
- `GET /status`: reads the counter.
- All URLs require a Basic-authenticated user.
- **Default CSRF protection stays enabled** so POSTs without a token are blocked.

### 8.1. Dependencies

In a Spring Boot 3.x project with the Gradle plugin/dependency management, you need:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/main/java/example/basiccsrf/BasicCsrfApplication.java`:

```java
package example.basiccsrf;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicCsrfApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            // Do not disable CSRF.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    private final AtomicInteger changes = new AtomicInteger();

    @GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
    String form(HttpServletRequest request) {
        // CsrfFilter provides the request attribute when CSRF is enabled.
        CsrfToken token =
            (CsrfToken) request.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF token is unavailable");
        }

        // Spring Security 6 may use a masked token for HTML forms.
        return """
            <!doctype html>
            <html lang="en">
            <body>
              <h1>Safe change form</h1>
              <form action="/change" method="post">
                <input type="hidden" name="%s" value="%s">
                <button type="submit">Record a change</button>
              </form>
            </body>
            </html>
            """.formatted(token.getParameterName(), token.getToken());
    }

    @GetMapping(value = "/status",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String status() {
        return "change-count=" + changes.get();
    }

    @PostMapping(value = "/change",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    String change() {
        return "change-count=" + changes.incrementAndGet();
    }
}
```

**Why this code compiles:** the Java file has one public top-level class matching `BasicCsrfApplication.java`, two package-private classes, and imports using the `jakarta.servlet` namespace for Spring Boot 3. `AtomicInteger` serves purely as in-JVM demo state, not a persistent database or real business logic.

**Why does GET /form have a token?** `CsrfFilter` exposes a `CsrfToken` under a request attribute named by class or parameter depending on the request handler. Reading `token.getToken()` materializes the token when deferred loading is used. The hidden form input reads `token.getParameterName()` (typically `_csrf` by default) and the value from the request rather than guessing a token in JavaScript.

Spring Security 6's default configuration may render a masked token (for BREACH mitigation). Always use **the token value Spring Security exposes for the request**—do not Base64/URL-encode a fixed token yourself, and do not assume the raw token and masked token are identical strings.

When a user visits `/form` in a browser for the first time, the server may return a 401 Basic challenge; after entering credentials, the browser displays the form. On submit, the token travels in the body and the browser may attach the cached Basic Authorization. Spring Security requires **both valid authentication and a valid token** for the POST.

This is a **learning-only** demo. Production must enable HTTPS, review header/cookie policies, protect credentials, and avoid storing demo passwords in real configs.

### 8.2. Running the Demo

In the Gradle project with wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Once the server listens on `http://localhost:8080`, open a browser:

```text
http://localhost:8080/form
```

The browser may show a Basic login dialog. Enter `learner` and `demo-pass`. After the form loads, click **Record a change**. The POST request carries the valid hidden CSRF token and the browser may automatically send the Basic credentials for that origin. The expected result is body `change-count=1` on the first change.

To view the state:

```text
http://localhost:8080/status
```

It should show `change-count=1` after the first valid POST; the counter increments on each successful POST within the same server process. This is **expected behavior from the code**, not a report of execution in this article.

### 8.3. Why Can't curl -u Alone Perform a Valid POST Immediately?

`curl -u` sends Basic credentials, yet **does not automatically supply a valid CSRF token and token storage context**. Therefore:

```bash
curl -i -u learner:demo-pass -X POST http://localhost:8080/change
```

**Expected:** HTTP 403 due to missing CSRF token, even when the Basic password is right. The POST is rejected before the controller increments the counter; `change-count` should not change.

A client wanting to POST validly must fetch a CSRF token from a server-provided endpoint/form, preserve any cookie or session holding the expected token when used, and submit the token in the right location. The demo's browser form does this; in automated tests, `spring-security-test` offers the `.with(csrf())` helper.

In this basic-auth demo, the GET form request can create an HTTP session **to store the CSRF token** even though primary authentication is Basic. Distinguish *a session storing CSRF state* from *a session serving as login proof*. Never infer “using Basic guarantees no JSESSIONID”.

## 9. MockMvc: Proving Valid Basic Auth Still Cannot Bypass CSRF

Create `src/test/java/example/basiccsrf/BasicCsrfSecurityTest.java`:

```java
package example.basiccsrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicCsrfSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsForProtectedGetRequiresBasicAuth()
            throws Exception {
        mvc.perform(get("/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetIsAllowedWithoutCsrfToken()
            throws Exception {
        mvc.perform(get("/status")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(startsWith("change-count=")));
    }

    @Test
    void basicCredentialsDoNotBypassCsrfOnPost()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndBasicCredentialsAllowPost()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string(startsWith("change-count=")));
    }

    @Test
    void invalidCsrfIsRejectedEvenWithCorrectPassword()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void htmlFormRendersCsrfParameter()
            throws Exception {
        mvc.perform(get("/form")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void crossSiteOriginLabelDoesNotReplaceTokenValidation()
            throws Exception {
        mvc.perform(post("/change")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("Origin", "https://untrusted.example")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test
```

The statuses and assertions are **expected behavior of the Spring Boot/Spring Security setup described**, not a report of executed tests. MockMvc does not simulate a real browser caching HTTP Basic credentials; `httpBasic(...)` **explicitly attaches a Basic header** to the test request to simulate a browser carrying credentials. The test with `Origin: https://untrusted.example` is not automatic proof of a separate Origin filter: it is **CSRF token validation** that rejects the tokenless POST.

**Crucial point when testing CSRF:** keep CSRF enabled in the security chain and supply a valid token with `.with(csrf())`; never disable CSRF just to make a POST test return 200. Test both missing and invalid tokens, and verify the state-changing controller **is not invoked** on rejected branches.

## 10. Why Did the Example Use an HTML Form Instead of Exposing a JSON API?

An HTML form demonstrates what a browser can do **without cross-origin response-reading permission**. For a JSON API using `fetch`, browsers add CORS/same-origin rules, custom headers, and credential modes; yet you cannot infer from that that `application/x-www-form-urlencoded` endpoints are safe.

If a product uses an SPA calling an API, define an explicit **CSRF token contract**:

- If auth relies on cookies/sessions or auto-sent Basic, keep CSRF mitigation for unsafe requests.
- Expose the CSRF token via a server-rendered page, same-origin endpoint, or suitable repository/cookie; only trusted code should read it.
- If using `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript reads the token from a cookie, understand XSS constraints, SameSite, token refresh, and Spring Security 6 `CsrfTokenRequestHandler`/BREACH handling. A JS-readable token cookie is **not** a password, yet XSS can still steal it; protect the frontend and pick the right request handler for sending raw tokens back.
- With automatic HTTP Basic prompts, if the browser does not retain the session cookie holding the expected CSRF token or the SPA omits the token in the proper header/parameter, POSTs can return 403 even while Basic credentials remain in the browser cache.
- Never hardcode a static CSRF token across users or sessions; never put tokens into URL query strings where logs/history/referrers can record them.

### CSRF Tokens and Token Cookies Are Not Login Cookies

A session cookie may only hold where the server stores the CSRF token; another cookie may serve as the repository for the token. Neither proves Basic credentials were converted into cookie authentication. Distinguish **protecting operation integrity** from **verifying identity**.

## 11. Defense in Depth When HTTP Basic Serves Browsers

CSRF tokens are a foundational control; real deployments need a sensible set of safeguards:

| Safeguard | Goal | Do not misunderstand |
| --- | --- | --- |
| Synchronized CSRF token in request/session or valid repository | Reject unsafe cross-site actions lacking a valid secret | Does not replace authentication; does not fully prevent XSS |
| `Origin`/`Referer` validation | Constrain request source on critical actions | Must handle missing headers, redirects, and proxies; don't just match an arbitrary substring |
| Fetch Metadata policy (`Sec-Fetch-Site`, etc.) | Distinguish same-origin/same-site/cross-site per browser | Needs fallbacks and legitimate exceptions |
| Never mutate state on GET | Reduce abuse via links, images, navigation | GET is not token-checked by default |
| HTTPS, HSTS | Protect Basic credentials and data in transit | TLS does not stop CSRF from malicious pages |
| Restrict permissions via `authorizeHttpRequests` and method security | Only authorized users execute actions | Even authenticated users can suffer CSRF |
| Rate limiting, auditing | Mitigate brute force/abuse and aid investigation | Does not replace CSRF tokens |
| `SameSite`, `Secure`, `HttpOnly` cookies when cookies exist | Reduce certain cookie/session surfaces | Does not restrict browser Basic Authorization by itself |
| Strict CORS allowlist | Limit browser script access to resources/responses | Does not block cross-origin HTML forms |
| CSP, output encoding, XSS prevention | Mitigate XSS that could steal/forge CSRF tokens | Cannot be skipped just because CSRF tokens exist |

Specifically, if the same URL is called by both web browsers and API clients, apply **a security policy protecting the highest-risk client**, or cleanly separate routes and authentication mechanisms. Never put `/api/**` on a CSRF exemption list while letting browser Basic run on it merely because the path says “api”.

## 12. Distinguishing 401, 403, and 405 Response Codes

An error status alone is not enough to tell whether the fault is a password or CSRF:

| Request | Typical status | Cause / handling point |
| --- | --- | --- |
| GET protected URL, no Basic credential | 401 + `WWW-Authenticate` | Basic `AuthenticationEntryPoint` invites authentication |
| GET protected URL, valid Basic | 200 if controller/rules allow | Basic authentication succeeds; GET needs no CSRF by default |
| POST protected URL, valid Basic, **no** CSRF | 403 | `CsrfFilter` rejects before action |
| POST protected URL, valid Basic, invalid CSRF | 403 | `CsrfFilter` token validation fails |
| POST protected URL, valid Basic, valid CSRF | 200/2xx from controller if permitted | Authentication + CSRF + authorization all pass |
| POST protected URL, wrong Basic, valid CSRF | 401 typically | Authentication fails; details per entry point |
| POST to GET-only endpoint, valid CSRF | Possibly 405 or other response | No matching handler, after traversing security filters |
| POST authenticated user missing role, valid CSRF | 403 typically | Authorization blocks, **not** CSRF |

In custom setups, status/response may differ. Inspect status **together with** filter logs, rules, headers, and tests to pinpoint the cause.

### Procedure for Debugging 403 with Basic

1. Confirm the request hits the expected `SecurityFilterChain` by URL and matcher.
2. Confirm the HTTP method; POST/PUT/PATCH/DELETE may require CSRF.
3. Check whether the CSRF token exists, is sent in the right parameter/header, and matches the repository/session.
4. Check that token-related cookies/sessions are sent by the browser on the corresponding request.
5. Inspect the Basic header only in development in a **redacted** form; never print credentials.
6. If CSRF passed, check provider/password/locked account and then authorities/authorization.
7. If behind a reverse proxy, check `Origin`/scheme/host and public paths—do not hastily open CORS globally or disable CSRF.
8. Test the exact scenario in both a browser and a non-browser client, because credential behavior differs.

## 13. Does `SessionCreationPolicy.STATELESS` Remove CSRF?

A configuration often seen in APIs:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
```

This is only a **fragment** needing imports. It governs how Spring Security uses HTTP sessions for the security context in that configuration. It **does not directly change** whether browsers auto-attach `Authorization: Basic` within cached scopes. Hence if a browser can auto-send Basic credentials, a stateless API **can still face CSRF**.

When CSRF protection is needed in a stateless app, choose a compatible `CsrfTokenRepository` and client token transport; do not assume the default session repository fits every stateless design. Separate questions to answer are:

- Where does authentication state live?
- Where does expected CSRF token state live?
- How does the browser/client obtain and return the token?
- Can the API accept credentials automatically carried by a browser?

Only after answering these four questions should you decide your CSRF matchers/repository/policy.

## 14. Common Mistakes and Corrections

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| “Basic doesn't use cookies so it's immune to CSRF” | Overlooks browser-cached Basic credentials | Consider **ambient credentials**, not just cookies |
| “No server session means no CSRF” | Confuses sessions with browser behavior | Evaluate auto-sent credentials per request |
| “CORS blocked it so cross-site POST won't reach the server” | Forgets HTML forms can submit requests | Use server-side CSRF mitigation |
| “SameSite=Lax blocks Basic” | SameSite does not apply to Authorization headers | Apply explicit CSRF policy for Basic |
| “Valid Basic auth means the request must succeed” | POST can still be rejected by the CSRF filter | Check token and method |
| “POST 403 means wrong password” | Debugs the wrong filter | Distinguish CSRF 403 from Basic 401 |
| “Disable CSRF on the whole chain so curl works” | Opens cross-site state-changing attack path | Use browser forms or CSRF-aware clients |
| “Any X-CSRF-TOKEN header is enough” | Header can be forged or lack token binding | Server must validate a **valid token value** |
| “JSON API is always safe even if accepting browser Basic” | Misjudges content types, CORS, alternate routes | Separate mechanisms and test request formats/policies |
| “Clients can pass CSRF tokens in URL query strings” | Tokens can leak in logs/referrers | Use form fields/headers over HTTPS |
| “An Origin header check alone is enough” | Unprepared for older browsers/missing headers | Use defense in depth and tested policies |
| “With CSRF tokens, XSS is harmless” | XSS can read tokens and trigger valid actions | Defend against XSS independently |

## 15. Self-Check Questions

**Question 1.** An app does not use form login, only `.httpBasic()`. The browser has cached Basic credentials; the user visits an external site that submits a POST form to a settings-changing URL. Should CSRF be considered?

**Answer:** Yes. If the browser automatically attaches Basic credentials to the POST to the app, the request can be authenticated as the user. `httpBasic()` does not prove CSRF safety by itself.

**Question 2.** A developer says CORS does not grant response-reading permission to a malicious site, so that site cannot alter data with an HTML form POST. Where is the flaw?

**Answer:** CORS/SOP generally prevents reading cross-origin responses, yet does not necessarily block sending cross-site HTML forms. CSRF only needs the server action to execute; reading the response is unnecessary.

**Question 3.** A POST contains a valid `Authorization: Basic ...` header but lacks `_csrf` on a chain with CSRF still enabled. What does Spring Security typically return?

**Answer:** 403 from `CsrfFilter`, before the controller executes the action. Valid authentication does not replace a CSRF token.

**Question 4.** Why is `SameSite=Strict` on a session cookie not a valid argument to disable CSRF for HTTP Basic?

**Answer:** SameSite controls cookies, not Basic headers that a browser may auto-send. Evaluate every credential type accepted by the backend.

**Question 5.** A service-to-service API accepts only bearer tokens explicitly attached to `Authorization` by service code, accepting neither cookies nor browser Basic. Must every POST carry a CSRF token?

**Answer:** Not necessarily. If the threat model proves an attacker web origin cannot make a browser auto-attach a valid credential and no other ambient auth exists, a tightly scoped CSRF exemption can be designed. Authentication, authorization, TLS, input validation, and other defenses are still needed.

**Question 6.** What happens if a browser submits the demo's form, but a developer removed the hidden `_csrf` input?

**Answer:** The POST to `/change` may carry valid Basic credentials, yet `CsrfFilter` rejects it for missing the token. The counter does not increment.

**Question 7.** Why does a MockMvc test with `httpBasic(...)` not prove every browser auto-sends Basic in cross-site forms?

**Answer:** The test merely constructs an HTTP request with a Basic header and checks how Spring Security reacts when that request reaches the server. Cache/challenge/protection-space behavior belongs to real browsers and must be assessed separately for exploitability.

**Question 8.** If a resource mutates state via GET, can you rely solely on the default CSRF filter to protect it?

**Answer:** No. Spring Security treats GET as a safe method by default and does not require a CSRF token. Change the endpoint to an appropriate unsafe method and apply CSRF/authorization.

## 16. Design and Acceptance Checklist

- [ ] Inventory every HTTP Basic path accessed by **browsers** and whether browsers can auto-send credentials.
- [ ] For state-changing POST/PUT/PATCH/DELETE, enable CSRF validation or a proven equivalent mitigation.
- [ ] Never mutate data on GET, HEAD, or other safe methods.
- [ ] Never use CORS or SameSite as the sole reason to exempt HTTP Basic from CSRF.
- [ ] Identify exact `CsrfTokenRepository`, request handler, and token placement (form parameter/header).
- [ ] Forms/templates submit the actual token issued by Spring Security for the right session/context.
- [ ] Tests: valid Basic but missing token → 403; wrong token → 403; valid Basic + token → action allowed.
- [ ] Tests: principal lacking permission is still blocked even with valid CSRF; unauthenticated users cannot bypass Basic.
- [ ] Multiple `SecurityFilterChain` configurations do not omit state-changing paths or login/challenges.
- [ ] If CSRF exclusions exist, prove those routes do **not** accept ambient browser credentials and are properly scoped.
- [ ] XSS defenses, CSRF token leak protection, HTTPS, and credential redaction in logs are in place.
- [ ] Account for differences across browser versions, HTTP auth caches, realms, protection spaces, and cookie/third-party restrictions.
- [ ] Regression tests cover cross-origin forms and Origin/Fetch Metadata policies if applied.
- [ ] Threat model docs specify permitted client types and trust assumptions for each credential mechanism.

## Conclusion

**HTTP Basic is not a default CSRF exemption.** The decisive point is whether browsers can **automatically carry cached Basic credentials** when an external site triggers a request to a protected origin. CORS limits reading responses, SameSite mainly governs cookies, and statelessness describes only part of server state; none of them replaces an anti-CSRF policy on its own.

In Spring Security Servlet, keep `CsrfFilter` for unsafe browser requests, use tokens supplied by `CsrfTokenRepository` and the request handler, and combine them with authorization, HTTPS, XSS prevention, and suitable Origin/Fetch Metadata controls. Only skip CSRF on routes proven not to accept browser auto-sent credentials. **Verify actual behavior with missing/invalid/valid token tests instead of inferring safety from the label “HTTP Basic” or “stateless API”.**
