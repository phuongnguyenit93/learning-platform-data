# Separating Browser Login Behavior from JSON API Responses in Spring Security Reactive

## 1. Objectives

A Spring WebFlux system may simultaneously serve **web pages for browser users** and **REST APIs for mobile apps, SPAs, or other services**. Although both require authentication, the two client groups usually need completely different behavior:

- **Browsers accessing HTML pages:** when unauthenticated, redirect to `/login`; users submit a form and may be returned to the requested page; on a wrong password, display the login page with a notice; use cookies/WebSession and CSRF protection.
- **APIs returning JSON:** when credentials are missing, return **401** with a JSON body; when authenticated but lacking permissions, return **403** with JSON; never redirect to HTML, never unexpectedly emit a login form page in the response; API clients handle statuses and data per the published contract.

This lesson explains how to **separate policies and mechanisms**, rather than merely changing `Content-Type` on a login page. You will understand `SecurityWebFilterChain`, `ServerHttpSecurity`, `securityMatcher`, `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and the difference between authentication failure and authorization denial; then build a Java 17+ project with two endpoint groups exhibiting verifiable behavior.

**Key takeaway:** to return responses suited to each client type, define **clear boundaries for security chains and authentication mechanisms**. Never use the presence of an `Accept: application/json` header as a mechanism for deciding access permissions.

## 2. Four Scenarios That Must Be Separated

| Event | Browser HTML | REST API JSON |
| --- | --- | --- |
| **Unauthenticated** request to a private resource | Typically **302** and `Location: /login`; browser displays login page | **401 Unauthorized** with JSON error code, never redirects to HTML |
| **Submitting wrong credentials** | Form login failure usually redirects to `/login?error` | If a dedicated login API exists, return 401/400 with an appropriate JSON error code; Basic/Bearer API failures typically return 401 |
| **Logged in but lacking role/permission** | Typically **403** or a friendly HTML error page, not bounced to login as anonymous | **403 Forbidden** with JSON, never turned into HTML login |
| **Successful login** | With form login, usually redirects to saved request or landing page; retains context in WebSession if using sessions | API returns JSON/token or contract response; no redirect. With Bearer resource servers, every request verifies the token |

A common mistake: applying `.formLogin()` across the entire application, causing unauthenticated `GET /api/orders` requests to redirect to `/login` instead of returning JSON 401. Frontend `fetch()` may auto-follow the redirect and receive HTTP 200 HTML, then fail when parsing `response.json()`. Worse, the client fails to detect session expiration properly and may confuse authentication errors with JSON errors.

You also should not return 401 for every access denial: **401** means valid authentication is required; **403** means an identity exists but lacks permission under the rules. Some invalid CSRF cases also return 403, yet that is a request protection layer rather than missing a role.

## 3. Where the Separation Sits in WebFlux Architecture

~~~text
                   Incoming HTTP request
                              |
                              v
                     WebFilterChainProxy
                              |
                selects SecurityWebFilterChain by
                securityMatcher and @Order
                              |
              +---------------+----------------+
              |                                |
              v                                v
        /api/** chain                    Browser chain
        @Order(1)                        @Order(2), fallback
              |                                |
      HTTP Basic/Bearer (demo: Basic)    formLogin
      formLogin disabled                 httpBasic disabled
      JSON entry point                   Redirect entry point
      JSON accessDeniedHandler           WebSession context
      no request-cache redirect          CSRF for login/logout/form
              |                                |
        /api/public: 200                  /: public HTML
        /api/me: 401/200                  /web/home: 302 -> /login
        /api/admin: 403/200              POST /login -> redirect
~~~

Two matcher levels are not the same:

1. **`http.securityMatcher(...)`:** decides whether the **entire chain** runs for the request. With `/api/**` on a high-priority chain, browser form-login filters **never need** to process API requests.
2. **`authorizeExchange(...).pathMatchers(...)`:** decides **access permissions** within the selected chain. This is not how you stop `formLogin` or other filters in the chain from activating.

Spring Security reactive supports multiple `SecurityWebFilterChain` beans; this is normal configuration, not a duplicate-bean bug. `@Order` controls which chain is evaluated first. A fallback chain with no specialized matcher can protect the remaining URLs. If **no chain matches**, URLs may fall outside Spring Security's protection — a major risk when separating APIs and browsers.

### Why Not Rely Only on the Accept Header?

`Accept` expresses the representation the client prefers, yet:

- A browser can send `Accept: application/json` in `fetch()` while still using a session cookie.
- A script or bot can send `Accept: text/html` even when calling an API.
- A request with `Accept: */*` does not tell you reliably whether it is an app, browser, or backend.
- `Accept` is not proof of identity, nor is it a criterion for granting permissions or toggling CSRF.

Content negotiation can **format** responses after policy is decided, whereas choices of scheme, session/cookie, CSRF, OAuth2/JWT, and security chains must be based on **explicitly designed routes and access contracts**.

## 4. Reactive Components to Understand

| Component | Role | Where Used? |
| --- | --- | --- |
| `SecurityWebFilterChain` | Defines filters for a request region | One bean for API, one bean for HTML |
| `ServerHttpSecurity` | WebFlux Security configuration DSL | Builds each chain |
| `PathPatternParserServerWebExchangeMatcher` | Matches URLs at the chain level | E.g., `/api/**` |
| `ServerAuthenticationEntryPoint` | Initiates authentication when a request needs identity | HTML: redirect; API: 401 JSON |
| `ServerAccessDeniedHandler` | Handles authenticated users lacking permissions | API: 403 JSON |
| `ServerAuthenticationFailureHandler` | Handles a **failed authentication attempt** | API Basic wrong password: JSON; form login wrong: redirect |
| `ServerAuthenticationSuccessHandler` | Handles successful authentication | Form: redirect; JSON login: JSON response |
| `ServerSecurityContextRepository` | Saves/reads `SecurityContext` across requests, if any | Browser usually WebSession; stateless Basic API can use NoOp |
| `ServerRequestCache` | Remembers original URL to redirect back after login | Useful for browsers; unnecessary for APIs |
| `CsrfWebFilter` | Protects state-changing requests in CSRF-exposed contexts | Especially needed for forms/cookies |

Distinguish the three handler types specifically:

- `authenticationEntryPoint` handles requests with **no accepted authentication yet** at a step requiring login (e.g., API request missing credentials, or browser needing redirection to the login page).
- `authenticationFailureHandler` handles a **failed authentication attempt** (wrong password, invalid token, etc.). Do not merely set an entry point in `exceptionHandling` and assume every authentication filter automatically uses it.
- `accessDeniedHandler` handles **access denied** after a valid identity lacks sufficient authorities. A request rejected by the CSRF filter may use its own error handler; configure it if you want API CSRF errors to return JSON too.

## 5. Runnable Two-Chain Separation Configuration

We will build a single project with two URL regions:

- Browser: `/` public; `/web/home` requires login; `/web/admin` requires `ROLE_ADMIN`; Spring Security generates `GET /login` and handles `POST /login`.
- API: `GET /api/public` public; `GET /api/me` requires login; `GET /api/admin` requires `ROLE_ADMIN`. Success responses are JSON. 401/403 responses return fixed JSON bodies, **never redirecting to `/login`**.

To avoid needing OAuth2/JWT infrastructure in this practice exercise, the API demonstrates using **HTTP Basic** with two local users. HTTP Basic **is not** a good default choice for every SPA; it simply makes authentication boundaries and responses easy to observe. In production, choose Bearer/OAuth2 or an appropriate API mechanism, evaluating token expiry, CORS/CSRF, and browser characteristics. Section `11` discusses moving to API tokens or JSON login.

### 5.1. Maven Project, Java 17+

Create a Spring Initializr project with Maven, Java **17+**, Spring Boot **4.1.2**, group `com.example`, artifact `browser-api-security`. Select **Spring Reactive Web** and **Spring Security** dependencies.

Minimal complete `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>browser-api-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

The Spring Boot BOM manages Spring Framework, Spring Security, and Reactor versions automatically; **do not** add separate versions for individual Spring modules. For the Boot 3.5 line, use the parent/BOM from that line and verify corresponding APIs.

### 5.2. One Complete Java File

Create `src/main/java/com/example/browserapi/BrowserApiSecurityApplication.java` with:

~~~java
package com.example.browserapi;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class BrowserApiSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrowserApiSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer123!"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123!"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint unauthorized = (exchange, error) ->
                writeJson(exchange, HttpStatus.UNAUTHORIZED, "unauthorized");

        ServerAccessDeniedHandler denied = (exchange, error) ->
                writeJson(exchange, HttpStatus.FORBIDDEN, "forbidden");

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(rules -> rules
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(unauthorized)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        unauthorized)))
                .formLogin(form -> form.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler(denied))
                .csrf(csrf -> csrf.accessDeniedHandler(denied))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .requestCache(cache -> cache
                        .requestCache(NoOpServerRequestCache.getInstance()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/", "/web/public").permitAll()
                        .pathMatchers("/web/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    private static Mono<Void> writeJson(
            ServerWebExchange exchange, HttpStatus status, String error) {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        String json = "{\"error\":\"" + error + "\"}";
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class DemoController {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="en"><head><meta charset="UTF-8">
                    <title>Browser Demo</title></head>
                    <body>
                      <h1>Public Web Page</h1>
                      <a href="/web/home">Go to private page</a>
                    </body></html>
                    """);
        }

        @GetMapping(value = "/web/public",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webPublic() {
            return Mono.just("<h1>PUBLIC_HTML</h1>");
        }

        @GetMapping(value = "/web/home",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webHome() {
            return Mono.just("<h1>WEB_HOME</h1>");
        }

        @GetMapping(value = "/web/admin",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> webAdmin() {
            return Mono.just("<h1>WEB_ADMIN</h1>");
        }

        @GetMapping(value = "/api/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiPublic() {
            return Mono.just(Map.of(
                    "message", "PUBLIC_JSON"));
        }

        @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiMe(Principal principal) {
            return Mono.just(Map.of(
                    "user", principal.getName(),
                    "mode", "http-basic"));
        }

        @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiAdmin() {
            return Mono.just(Map.of(
                    "message", "ADMIN_JSON"));
        }
    }
}
~~~

**This is a complete demo project in a single class**, utilizing Java 17 text blocks. The file, package, and public class match. Spring Boot's WebFlux starter provides the server and matching JSON codecs; controllers do not need to manually write HTTP responses for successful API calls.

### 5.3. Explaining Each Configuration Decision

**API Chain:**

- `@Order(1)` and `securityMatcher("/api/**")`: all API URLs in the example enter the higher-priority chain.
- `formLogin(...disable())`: the API produces no redirects or login form pages; there is no form login filter in this chain.
- `httpBasic(...)`: Basic parser/manager handles username/password for the demo. `authenticationEntryPoint` is set explicitly to turn the "unauthenticated" response into JSON; `authenticationFailureHandler` ensures wrong Basic credentials also receive JSON.
- `exceptionHandling(...)`: when authorization requires authentication or denies a role, uses the corresponding **JSON entry point / access denied handler**.
- `csrf(csrf -> csrf.accessDeniedHandler(denied))`: **keeps CSRF protection active**; when an unsafe request lacks a token, this chain's CSRF handler returns JSON 403 instead of HTML content. The example uses GET only to avoid implying Basic APIs in browsers are immune to CSRF.
- `NoOpServerSecurityContextRepository`: does not save API Basic authentication into WebSession. Basic credentials are checked per request carrying the header; requests without the header do not "inherit" a browser login merely from sharing a host.
- `NoOpServerRequestCache`: the API does not save requests for post-form-login redirects.

**Browser Chain:**

- `@Order(2)` with no specialized `securityMatcher`: protects URLs **outside `/api/**`** as the fallback.
- `httpBasic(...disable())`: reduces the risk of browsers popping up a native Basic login dialog instead of showing the form.
- `formLogin(withDefaults())`: Spring Security generates default `GET /login` and handles `POST /login` from the HTML form; success typically redirects to the saved request or root page; failure goes to `/login?error`.
- Keeps default CSRF protection. The browser submits the login form containing a CSRF token and retains the session cookie per Spring Security's mechanism.
- `authorizeExchange` protects `/web/home` and requires a role on `/web/admin`. For `/web/public`, `permitAll` allows public HTML.

**User source:** `MapReactiveUserDetailsService` holds two illustrative users encoded with `PasswordEncoder`. User `viewer` has `ROLE_USER`, and user `admin` has `ROLE_ADMIN`. Demo passwords in source are for local use only; never use sample accounts or hardcoded secrets in production.

### 5.4. A Note on HTTP Basic and WWW-Authenticate

The API example intentionally returns JSON 401 **without sending a Basic challenge** so browsers do not pop up an HTTP Basic dialog. This illustrates UX separation and **is not a standard HTTP Basic pattern for every client**: per HTTP semantics, a 401 response for an HTTP authentication scheme needs an appropriate `WWW-Authenticate` challenge; some standard clients require this header. Therefore for production APIs, choose a mechanism designed for APIs (typically OAuth2 Bearer) and return `WWW-Authenticate: Bearer ...` per standard alongside JSON when policy allows, or design a transparent JSON login/session endpoint. Never drop the challenge without evaluating protocol/client compatibility.

The JSON handlers above are educational samples. In real applications, not only 401/403 but also validation errors, 404, 405, 415, 500, etc., need a standardized, centralized JSON contract.

## 6. Running and Verifying Both Paths

In the directory containing `pom.xml`, use the Maven wrapper from Spring Initializr:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Windows: `.\mvnw.cmd clean package` and `.\mvnw.cmd spring-boot:run`; if no wrapper is present, use an installed Maven. Default port is `http://localhost:8080` unless configured otherwise.

### 6.1. Browser: Public Pages and Redirects

Open `http://localhost:8080/`: receives public page HTML with a link to `/web/home`.

Open `http://localhost:8080/web/home` while not logged in: the browser is redirected to `/login`; this is the default HTML page generated by Spring Security (not JSON).

Log in with `viewer` / `viewer123!` on the form. On success, Spring Security can return you to the requested page; visiting `/web/home` shows `WEB_HOME`. Opening `/web/admin` as viewer returns **403** because it lacks `ROLE_ADMIN`. Log out using Spring Security's built-in logout feature or use a separate browser session and log in as `admin` / `admin123!`; admin visiting `/web/admin` receives HTML with `WEB_ADMIN`.

When not logged in, the following command typically shows **302 Found** with `Location` pointing to the login page:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/web/home
~~~

Use `curl -i` without `-L` if you want to observe the original redirect: `-L` follows redirects and may show you only the HTTP 200 of the login HTML page.

### 6.2. REST API: JSON Without Redirects

The commands below use `curl` and the JSON API. Replace `curl` with `curl.exe` in Windows PowerShell if `curl` is aliased to another cmdlet:

~~~bash
# Public API, no credentials
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/public

# Private API, no credentials
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/me

# Private API, wrong Basic password
curl -i -u viewer:wrong \
  -H "Accept: application/json" \
  http://localhost:8080/api/me

# Private API, valid viewer
curl -i -u 'viewer:viewer123!' \
  -H "Accept: application/json" \
  http://localhost:8080/api/me

# Viewer lacks ROLE_ADMIN
curl -i -u 'viewer:viewer123!' \
  http://localhost:8080/api/admin

# Admin has ROLE_ADMIN
curl -i -u 'admin:admin123!' \
  http://localhost:8080/api/admin
~~~

In shells that do not support `\` line continuations, put each command on a single line. Expected results:

| Request | HTTP Status | Typical JSON Body |
| --- | --- | --- |
| `GET /api/public` (anonymous) | **200** | `{"message":"PUBLIC_JSON"}` |
| `GET /api/me` (anonymous) | **401** | `{"error":"unauthorized"}` |
| `GET /api/me` (Basic wrong password) | **401** | `{"error":"unauthorized"}` |
| `GET /api/me` (viewer) | **200** | `{"user":"viewer","mode":"http-basic"}` |
| `GET /api/admin` (viewer) | **403** | `{"error":"forbidden"}` |
| `GET /api/admin` (admin) | **200** | `{"message":"ADMIN_JSON"}` |

Successful JSON bodies may vary in **key order** because `Map.of` does not guarantee serialization order. In tests, **parse JSON and compare field values**, rather than comparing rigid serialized text as a single string. The 401/403 JSON error bodies are produced by `writeJson(...)` with a single `error` field.

To confirm there is no redirect, verify **no 3xx status and no `Location: /login`** on the tested APIs. Also check `Content-Type: application/json`. Do not draw conclusions from a single 200 after `curl -L` or browser `fetch` auto-followed a redirect.

### 6.3. When the Same Logged-In Browser Calls the API

Because the two chains use separate mechanisms, the demo API uses `NoOpServerSecurityContextRepository`; having a logged-in WebSession in the browser does not automatically authenticate `GET /api/me` **unless the Basic header is sent**. This illustrates **separating browser sessions from API credentials**.

If your product genuinely wants an SPA using a session cookie to call `/api/**`, **do not mechanically apply `NoOpServerSecurityContextRepository` or the "APIs don't need CSRF" rule**. In that case the API uses cookies for authentication and needs a matching security context repository, CSRF header, SameSite/cookie attributes, CORS with credentials, and corresponding rules. Separating HTML/JSON responses is still achievable, yet the **authentication mechanism is different**.

## 7. CSRF, CORS, and Cookies: JSON Does Not Make an API Automatically Safe

### 7.1. Browser Form Login Must Handle CSRF

Spring Security WebFlux enables CSRF protection by default for unsafe HTTP methods. Login forms are also exposed to login CSRF risks. Spring Security's default login page already integrates a CSRF token; when building your own login page with Thymeleaf/HTML, you must place a valid token into the form:

~~~html
<form method="post" action="/login">
  <label>Username <input name="username" autocomplete="username"></label>
  <label>Password <input name="password" type="password"
                         autocomplete="current-password"></label>
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Sign in</button>
</form>
~~~

This is **sample HTML for explanation**; do not use `TOKEN_FROM_SERVER` literally. When using Spring Security and Thymeleaf properly integrated, the framework can insert the token into the form automatically; self-rendered HTML must pull `CsrfToken` from `ServerWebExchange` or an equivalent mechanism. Never disable CSRF system-wide just to make form login run.

### 7.2. JSON APIs Using Cookie Sessions Still Carry CSRF Risk

A JSON body does not eliminate CSRF when browsers automatically send session cookies. For example, an SPA calling `POST /api/profile` with `credentials: "include"` must be protected against CSRF via token/header or thoroughly analyzed defenses. Choosing `Content-Type: application/json` is not a shield against all CSRF, given other side-effect vectors and CORS configuration risks.

Conversely, a server-to-server API accepting only Bearer tokens from an `Authorization` header explicitly set by the client—using no cookies or automatic browser credentials—may have a different CSRF model. Disable CSRF on an API chain only after proving that assumption holds, never by copying `csrf.disable()` onto every REST API.

### 7.3. CORS and Credentials

CORS determines which browser origins can read HTTP responses. An overly broad CORS configuration paired with cookie credentials can leak data. Never use `Access-Control-Allow-Origin: *` together with credentials. For cookie-backed APIs, set an explicit origin allowlist, decide whether `Access-Control-Allow-Credentials` is needed, and align `Secure`, `HttpOnly`, and `SameSite` cookie policies with the authentication flow.

CORS does not replace authentication/authorization; a request from a cross-origin script blocked from reading the response can still cause side effects if the backend fails to protect POST/PUT/DELETE sufficiently.

## 8. If You Need a Custom HTML Login Form

In the browser chain, you can replace:

~~~java
.formLogin(Customizer.withDefaults())
~~~

with:

~~~java
.formLogin(form -> form
        .loginPage("/signin"))
~~~

This is a **replacement snippet in the browser chain**, not a standalone Java class. When using `loginPage("/signin")`, Spring Security no longer auto-generates the default HTML page as before. The application must serve **GET /signin**, an error page at `/signin?error`, form submission **POST /signin**, and an appropriate CSRF token. You must declare `/signin` publicly accessible:

~~~java
.authorizeExchange(rules -> rules
        .pathMatchers("/", "/signin", "/web/public").permitAll()
        .pathMatchers("/web/admin").hasRole("ADMIN")
        .anyExchange().authenticated())
~~~

Do not change `loginPage` and forget to build the HTML handler: browsers may enter a redirect loop or hit 404 instead of a form. Do not reuse `/api/login` for an HTML form if the JSON API contract requires different bodies and statuses.

Default form login success uses `RedirectServerAuthenticationSuccessHandler`, which can redirect to a saved request or `/`; failure uses the corresponding handler and redirects to `/signin?error`. If you want to change destinations:

~~~java
.formLogin(form -> form
        .authenticationSuccessHandler(
                new RedirectServerAuthenticationSuccessHandler("/web/home"))
        .authenticationFailureHandler(
                new RedirectServerAuthenticationFailureHandler("/signin?error"))
        .loginPage("/signin"))
~~~

This is a **configuration snippet** requiring handler imports from `org.springframework.security.web.server.authentication`. Note: setting a fixed redirect success handler alters saved-request restoration behavior; weigh your app's UX before using it. Never include passwords or detailed authentication exceptions in URLs/query strings.

## 9. If You Need JSON Login for an API, Do Not Use Default formLogin

There are two distinct architectural patterns learners easily mix up:

**Approach A — API authenticating every request with Bearer/OAuth2:** the client obtains an access token from an identity provider/authorization server, calls `/api/**` with `Authorization: Bearer ...`, and the server validates the token. There is no HTML form login in the API chain. Missing/invalid tokens typically return 401 with `WWW-Authenticate: Bearer` per the resource server mechanism; valid tokens lacking scope/role return 403. This is usually the right architecture for mobile and machine-to-machine clients.

**Approach B — API with a JSON login endpoint:** the application defines `POST /api/auth/login` accepting JSON credentials, invokes `ReactiveAuthenticationManager`, returns JSON success/failure, and establishes a session/token per the chosen model. Do not merely add a controller returning `{"ok":true}` after checking a password; you must design all of:

- A `ServerAuthenticationConverter` that parses JSON bodies properly, validates schemas, and handles malformed input.
- An `AuthenticationWebFilter` or matching authentication mechanism whose matcher applies only to `POST /api/auth/login`.
- Non-redirecting `ServerAuthenticationSuccessHandler` and `ServerAuthenticationFailureHandler` returning JSON with stable error codes, without revealing whether a user exists.
- Saving and reusing `SecurityContext` via `ServerSecurityContextRepository` **if** using sessions; or issuing tokens and validating tokens on every request if stateless.
- CSRF protection when using cookie sessions; rate limiting, brute-force defenses, HTTPS, session fixation, cookie policies, logout/revocation, login failure tests, and token security.
- If using Bearer JWTs, evaluate where tokens are issued and where the resource server verifies issuer/signature/audience/expiration; never roll JWTs signed with a simple secret without a threat model.

**Changing only the authentication success handler does not turn form-urlencoded credentials into JSON input.** The default form login converter expects form fields like `username` and `password`; JSON payloads require a dedicated converter or endpoint. You also should not force a form-login chain to return 200 JSON while keeping redirect entry points on other URLs, as the frontend will observe inconsistent behavior.

### Reusable JSON Error Response Pattern

In the sample Java class in section 5, `writeJson(...)` illustrates a helper for writing standardized error codes. If using `Problem Details` per RFC 9457 in a real product, you can output a response like:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

And a similar response with `status: 403` and `title: "Forbidden"`. This is a **schema sample**, not output from the demo code (the demo outputs only `{"error":"..."}`). Set `Content-Type: application/problem+json` only when genuinely adhering to the Problem Details specification; do not label arbitrary JSON objects as Problem Details.

### Distinguishing HTTP Errors from Business Information

401/403 in WebFlux security are security-layer errors. 400 from malformed JSON, 422 from invalid data, 404 from nonexistent routes, and 500 from system failures are normally handled by appropriate handlers/controller advice or exception mappers. Never catch every `Throwable` and return 401 JSON; doing so masks infrastructure failures and misleads diagnostics.

## 10. Common Pitfalls

### Pitfall 1 — Putting formLogin on a Chain Covering the API

~~~java
// Configuration lacking boundaries; may redirect APIs to /login.
http.authorizeExchange(r -> r.anyExchange().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

This is a **problem-identification snippet**, not a standalone project. If this chain covers `/api/**`, anonymous API requests can be redirected to HTML login. Split chains with `securityMatcher` or design entry points with explicit matchers.

### Pitfall 2 — Setting Only a JSON accessDeniedHandler

If you fix only 403, **unauthenticated** API requests may still redirect to `/login`. You must handle **401 entry point**, **authentication failure**, and **access denied**. For unsafe requests subject to CSRF, check the CSRF handler too.

### Pitfall 3 — Disabling formLogin Without Adding an Authentication Mechanism

After `formLogin(disable)`, the application still needs Basic/Bearer/or a custom authentication filter per design. Otherwise, private APIs may keep returning 401 even when clients send tokens that no filter processes. JSON handlers do not perform authentication.

### Pitfall 4 — Using @Primary to Pick a Chain

`@Primary` selects a bean for type-based injection; it is not an HTTP router. Spring Security selects `SecurityWebFilterChain` by `@Order` and `securityMatcher`. Two chain beans with different names are valid; matchers and order determine behavior.

### Pitfall 5 — Placing the Fallback Chain Before the API Chain

If a match-all chain has higher precedence than the API chain, it can intercept `/api/**` first. Consequently, the JSON API gets redirected or governed by the wrong browser policy. Test `GET /api/me` directly as anonymous, wrong password, and under-privileged user to catch this bug.

### Pitfall 6 — Relying Entirely on Accept or X-Requested-With

These headers can be spoofed or altered. Using them for content formatting can make sense, yet **never** rely on them to trust that a request is authenticated or to decide whether to disable CSRF. API and browser routes, cookies/tokens, origins, request methods, and policies must be designed independently.

### Pitfall 7 — Disabling CSRF Globally Just Because of JSON APIs

Form login and cookie-based sessions require CSRF protection. Calling `csrf.disable()` on a broad chain leaves login/logout and POST forms exposed to attack. Identify which chain is genuinely stateless with no browser-sent credentials, and consider disabling only when the threat model permits.

### Pitfall 8 — Using a 200 HTML Response to Mask 401

`fetch` can auto-follow redirects and show only HTTP 200 from `/login`. When the frontend calls `response.json()`, parsing fails. Ensure the API returns 401/403 directly with the right `Content-Type` and JSON body per contract, and write frontend code checking `response.ok`/`response.status`.

### Pitfall 9 — JSON Exception Handler Leaking Stack Traces

Never output `AuthenticationException.getMessage()` directly in the body to clients. Messages can reveal whether a user exists, account status, or internal details. Return generic error codes; write structured internal logs without passwords/tokens.

### Pitfall 10 — Confusing SecurityFilterChain with SecurityWebFilterChain

`HttpSecurity`, `SecurityFilterChain`, Servlet `AuthenticationEntryPoint`, and `OncePerRequestFilter` are not the APIs for Spring WebFlux. Reactively, use `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerAuthenticationEntryPoint`, `WebFilter`, and reactive handlers returning `Mono<Void>`.

## 11. Pre-Deployment Test Matrix

| Test | Input | Required Result |
| --- | --- | --- |
| Public HTML | `GET /` anonymous | 200, `text/html` |
| Anonymous private browser | `GET /web/home` | Redirect to `/login`, not JSON |
| Browser login page | `GET /login` | HTML containing form and CSRF token |
| Browser login failure | `POST /login` wrong credentials, valid CSRF | Redirect or HTML error page per config |
| Browser login success | `POST /login` right credentials, valid CSRF | Redirect to right target; valid session cookie |
| Browser role mismatch | Viewer visits `/web/admin` | 403, not treated as login failure |
| Public API | `GET /api/public` anonymous | 200, `application/json` |
| Anonymous private API | `GET /api/me` | **401 JSON**, no redirect |
| API wrong credentials | Basic wrong password | **401 JSON**, no redirect |
| API authenticated user | Viewer calls `/api/me` | 200 JSON with username |
| API insufficient role | Viewer calls `/api/admin` | **403 JSON**, no redirect |
| API admin | Admin calls `/api/admin` | 200 JSON |
| API spoofed Accept | `GET /api/me` with `Accept: text/html` | Still picks API chain, does not return form login |
| Browser spoofed Accept | `GET /web/home` with `Accept: application/json` | Still picks browser chain; policy unchanged |
| Unsafe API request | POST missing CSRF token (when cookies/CSRF active) | 403 JSON or per explicit policy, never silently bypassed |
| Unknown route | `GET /api/unknown` | Clear 401/404 contract; never redirects to HTML |

**Key testing point:** never rely on status alone. Verify `Location`, `Content-Type`, JSON schema, presence/absence of cookies, and behavior after the browser has logged in. With Spring WebFlux you can use `WebTestClient` and Spring Security test utilities to test login, CSRF, and authorities; compare JSON by fields rather than key ordering.

A good sequence: test chain routing first (`/api/**` vs browser), test 401 entry point, then 401 failure handler, 403 access denied, and finally form login success and CSRF with a separate cookie jar.

## 12. Operations and Security Checklist

1. Clear URL boundaries: `/api/**` never leaks into the form login chain; browser fallback covers all protected UI URLs.
2. API authentication follows the published mechanism: Basic here is illustrative, while Bearer/IdP usually suits production better; never accept JWTs without a validator.
3. API 401 and 403 consistently return JSON; never return redirects/HTML for defined security errors.
4. Browser still has a login page, proper success/failure redirects, and no redirect loops.
5. CSRF is preserved for form/cookie requests; CORS and cookie policies are evaluated separately.
6. Explicit strategies exist for access token expiry, revocation, logout, and session timeouts.
7. Never log credentials, session cookies, access tokens, or refresh tokens; audit successes/failures safely.
8. Differences among 401, 403, and CSRF 403 are distinguishable in telemetry and tests.
9. Non-security app errors (validation, 404, 500) have their own JSON error contract.
10. Test browsers, API clients, cookie-using SPAs, and non-browser clients **each according to its model**; do not apply one test suite to everything.

## 13. Self-Check Questions

**Q1.** Why does `.formLogin()` on all URLs easily cause `fetch("/api/me")` to throw a JSON error?

**Answer:** anonymous requests can redirect to the HTML login page; `fetch` follows the redirect and fails when trying to parse HTML as JSON. APIs should return 401 JSON directly per contract.

**Q2.** Is putting `@Order(1)` on the API chain enough by itself?

**Answer:** No. The chain must have a `securityMatcher` targeting `/api/**` accurately; the browser fallback goes afterwards, and authorization rules must be right inside each chain. If the matcher is wrong, requests can hit another chain or go unprotected.

**Q3.** Why must both entry point and authentication failure handler be configured for a Basic API?

**Answer:** "No credentials yet for a login-required resource" and "submitted invalid Basic credentials" follow two different handling paths. To get JSON for both, configure both the entry point and the authentication filter failure handler.

**Q4.** Viewer is authenticated yet calls `/api/admin`. Why 403 instead of 401?

**Answer:** Viewer has a valid identity yet lacks `ROLE_ADMIN`; this is an authorization-denied decision.

**Q5.** If an API returns JSON, can CSRF be disabled automatically?

**Answer:** No. You must know whether browsers automatically send cookies/sessions or cached credentials. The CSRF threat model is independent of the JSON format.

**Q6.** Does changing the `Content-Type` of `/login` to JSON solve the problem?

**Answer:** No. Redirect flows, request caches, form-urlencoded login, session repositories, and failure/success handlers can still follow HTML behavior; JSON login requires designing proper converters/filters/handlers and authorization mechanisms.

**Q7.** Can stateless API tokens and browser sessions coexist in the same application?

**Answer:** Yes. Two `SecurityWebFilterChain`s with clear matchers and order are a standard approach; the API uses tokens, the browser uses form login/sessions, and each chain has matching entry points, authorization, and CSRF/context policies.

## 14. Official Documentation

- [Spring Security — WebFlux Security and Multiple Chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Spring Security — ServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html)
- [Spring Security — ServerAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html)
- [Spring Security — ServerAuthenticationEntryPointFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security — Cross Site Request Forgery for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Boot — Security in Web Applications](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
