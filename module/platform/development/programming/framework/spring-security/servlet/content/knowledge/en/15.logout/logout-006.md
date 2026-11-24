# Redirect Logout for Web and Status-Code Responses for APIs

> **Scope:** Spring Security 6 on the **Servlet stack**, Java 17+, HTTP form login, and HTTP APIs. This lesson explains `LogoutFilter`, `LogoutHandler`, `LogoutSuccessHandler`, why **websites typically redirect after logout** (HTTP 302 + `Location`) while **APIs typically return an HTTP status** (such as `204 No Content`), and how to configure each URL group using `SecurityFilterChain`. The example runs on Spring Boot 3.3.5 and includes important caveats on CSRF, `HttpSession`, cookies, remember-me, and stateless tokens.

## 1. Logout Is More Than Sending the User Back to the Login Page

Logout is a **server- and client-side process** to terminate or invalidate the authentication state managed by the application. In traditional web apps, this usually includes invalidating `HttpSession`, clearing `SecurityContext`, cleaning up related cookies or tokens, and redirecting the browser to an appropriate page. In APIs, clients usually expect a **programmatically parseable HTTP status** rather than HTML from a login page.

Two illustrative experiences:

```text
WEB - Browser using form login and JSESSIONID

POST /logout + CSRF token + session cookie
    -> LogoutFilter runs LogoutHandlers
    -> HTTP 302 Location: /login?logout
    -> Browser automatically issues GET /login?logout
    -> Displays login page / logout notice


API - Client sends POST with a valid CSRF token (in the demo)

POST /api/logout
    -> LogoutFilter runs the API chain's LogoutHandlers
    -> HTTP 204 No Content
    -> Client handles the status and clears held credentials/tokens if appropriate
    -> No redirect to an HTML page
```

**Separate three concerns:**

1. **Cleanup:** clear context, invalidate session, and revoke cookies/tokens if the mechanism supports it.
2. **Protocol outcome:** redirect for browsers or return a status code for APIs.
3. **True credential revocation:** server-side sessions can be destroyed; with self-contained tokens, HTTP Basic, or copied remember-me cookies, “receiving status 204” **does not automatically mean** tokens/credentials were revoked.

Therefore, a “successful logout” requirement must specify both **what the server processes** and **what the client does next**. Never merely swap status 302 for 204 and assume the system has solved the entire token-revocation problem.

## 2. Components in Spring Security Servlet

| Component | Role |
| --- | --- |
| `SecurityFilterChain` | Defines security filters/handlers for each web or API URL group |
| `LogoutFilter` | Matches requests against the logout URL/matcher, runs `LogoutHandler`s, then invokes `LogoutSuccessHandler` |
| `LogoutHandler` | Performs cleanup: clearing context, session, cookies, and state/remote tokens per config |
| `SecurityContextLogoutHandler` | Normally invalidates `HttpSession` and clears `SecurityContext` as configured |
| `CsrfLogoutHandler` | Handles CSRF tokens on logout when CSRF is configured |
| `CookieClearingLogoutHandler` | Can delete additional declared cookies |
| Remember-me logout handler | Deletes remember-me cookies or records per the corresponding implementation |
| `LogoutSuccessHandler` | Decides the **post-cleanup HTTP response**: redirect, status, body, etc. |
| `SimpleUrlLogoutSuccessHandler` | Success handler using a target URL, typically producing a redirect |
| `HttpStatusReturningLogoutSuccessHandler` | Success handler returning an HTTP status instead of a redirect |
| `AuthenticationEntryPoint` | Handles **login challenges** when unauthenticated; not a logout success handler |

Interfaces to remember:

```java
// Abbreviated signatures to understand the contract (defined by Spring Security).
public interface LogoutHandler {
    void logout(HttpServletRequest request,
                HttpServletResponse response,
                Authentication authentication);
}

public interface LogoutSuccessHandler {
    void onLogoutSuccess(HttpServletRequest request,
                         HttpServletResponse response,
                         Authentication authentication)
            throws IOException, ServletException;
}
```

In Spring Security 6, the Servlet API uses `jakarta.servlet.*` instead of `javax.servlet.*`.

**Error-handling mindset:** `LogoutHandler` should perform stable cleanup; by Spring Security's design, do not use exceptions in handlers as a routine navigation mechanism or default way to signal logout completion to clients. If a remote token-revocation service must be called, establish a clear error strategy before returning a success status. `LogoutSuccessHandler` only decides the response **after** logout handlers run and does not by itself guarantee all access tokens were invalidated.

## 3. Where Does `LogoutFilter` Run and Why Does It Matter?

`LogoutFilter` typically sits **before authentication filters** such as `UsernamePasswordAuthenticationFilter` or `BasicAuthenticationFilter` in the security chain. It matches requests via a `RequestMatcher`, runs the logout handlers, and calls the success handler.

```text
HTTP POST /logout or POST /api/logout
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
Appropriate SecurityFilterChain (web / api)
    |
    v
CsrfFilter (checks CSRF if required by policy)
    |
    v
LogoutFilter
    |
    |-- Does the request match the logout matcher?
    |        |
    |        +-- No -> continue to authentication/authorization filters
    |        |
    |        +-- Yes
    |             |
    |             v
    |       LogoutHandler(s)
    |       - clean SecurityContext/session/cookies per config
    |             |
    |             v
    |       LogoutSuccessHandler
    |       - Web: 302 Location
    |       - API: 204 No Content
    |             |
    |             v
    |       Complete HTTP response
    |
    +-- Not logout -> other controllers/filters continue
```

Because `LogoutFilter` runs early, **a downstream `authorizeHttpRequests().authenticated()` rule does not necessarily guard the logout URL like a controller endpoint**. A logout request can be handled before reaching `AuthorizationFilter`. If an API requires “only authenticated users may revoke their own token,” the design must identify/verify credentials **before the revocation step**, or use a separately protected endpoint/revocation flow. Do not rely solely on `anyRequest().authenticated()`.

With session-based form login, logging out does not require the server to see a password in the request: the current session/context provides identity. With stateless Basic, if `LogoutFilter` runs before `BasicAuthenticationFilter`, a `POST /api/logout` request can receive 204 without ever running Basic authentication. That is reasonable if the endpoint merely signals “client should discard credentials,” yet **insufficient** if business logic requires genuine token revocation.

## 4. Web Logout: Typically a 302 Redirect to a Confirmation Page

With browsers and form login, users expect to return to the login page or a public screen. Spring Security provides the Java DSL:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout")
        .permitAll()
);
```

This is a configuration **fragment** inside a `SecurityFilterChain` method, not a standalone Java class.

When form login and CSRF are enabled by default:

1. A user with a valid session sends **`POST /logout`** with a valid CSRF token.
2. `CsrfFilter` checks the token; requests with an invalid token are typically rejected with 403 before logout runs.
3. `LogoutFilter` runs configured logout handlers; defaults typically invalidate the session, clear `SecurityContext`, and handle CSRF tokens and related cookies per present handlers.
4. The success handler sends a redirect, e.g., **302** with `Location: /login?logout`.
5. The browser automatically issues a GET to the target URL and renders the login page with the corresponding notice.

```http
HTTP/1.1 302 Found
Location: /login?logout
```

Only the two relevant lines are shown; responses may also carry security headers and `Set-Cookie` depending on the system. `Location` may be an absolute URL or relative path depending on proxies/context paths.

### Does `GET /logout` Always Log Out?

**No.** When CSRF is enabled, Spring Security usually renders a **logout confirmation page** for `GET /logout`; actual logout takes effect on **POST**. Do not use a side-effecting GET link to “work around” browsers needing a CSRF token. When building your own form, create `method="post" action="/logout"` and send a valid `_csrf` token.

HTML example with Thymeleaf/Spring MVC (this is a **view fragment**, not served by the controller in the Java example below):

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="SERVER_PROVIDED_CSRF_TOKEN" />
  <button type="submit">Log out</button>
</form>
```

The value in the HTML snippet is a **placeholder representing server-provided data**, not a valid token you can copy and run. When using Spring Security's default logout confirmation page, the framework handles tokens for the demo; you do not need to copy this HTML fragment manually.

### Post-Logout URL and Open Redirects

`logoutSuccessUrl("/login?logout")` works well when the URL is a fixed application path. Never blindly take `?next=https://example-attacker.test` from the request and redirect to it without validating against an internal allowlist. That can introduce an **open redirect** and send users away from the trusted site.

When using `SimpleUrlLogoutSuccessHandler` or a custom success handler, verify the generated URL respects context paths, reverse proxies, and trusted forwarded headers. Never let the client choose the logout redirect domain without strict binding policies.

## 5. API Logout: Returning an HTTP Status Without Automatic HTML Redirects

An API client such as a mobile app, backend service, or SPA usually expects:

- **`204 No Content`** when the server finishes cleanup per contract with no body.
- Or **`200 OK`** with JSON if the API needs extra metadata/status.
- **`401`** if the design requires authentication and credentials are invalid, in flows authenticating prior to revocation.
- **`403`** if authentication is valid but authorization/CSRF fails, per security contract.
- **`400`/`409`/`503`** for request/state/dependency errors under your policy; do not blindly treat every revocation failure as 204.

An appropriate success handler:

```java
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT))
);
```

This is a **fragment** requiring imports for `HttpStatus`, `HttpStatusReturningLogoutSuccessHandler`, and `HttpSecurity`. The handler returns a status code instead of 302, without telling the client to follow `Location`. `204 No Content` **carries no response body**, so do not write JSON alongside status 204. If JSON is needed, choose 200 and an appropriate custom handler.

API response example:

```http
HTTP/1.1 204 No Content
```

**Important limitation:** the HTTP status only reports the endpoint's outcome per contract. With HTTP Basic, if the client still holds valid username/password, subsequent requests can still authenticate. With an unexpired self-contained JWT, deleting the token client-side **does not revoke stolen copies**. With opaque tokens or server-stored refresh tokens, a logout/revoke endpoint can actually delete/revoke records, yet requires dedicated logic — `HttpStatusReturningLogoutSuccessHandler` **does not revoke tokens by itself**.

### 5.1. 204 or 200?

| Goal | Typical HTTP response | Clarification needed |
| --- | --- | --- |
| Logout complete, no body needed | **204 No Content** | Do not return JSON or a redirect |
| Logout complete, confirmation data needed | **200 OK** + JSON | Must not include secrets or full tokens |
| Web browser needs login/logout notice page | **302 Found** + `Location` | Browser follows redirect |
| Unauthenticated request to auth-required revoke endpoint | **401** | Requires an authentication layer before the action |
| Missing/invalid CSRF token on cookie-based logout | **403** | Cleanup may not have run |
| Downstream revocation fails | Policy-appropriate error status | Do not report 204 success if contract requires true revocation |

**Idempotency:** clients should treat logout as a repeatable operation that does not corrupt data. For web sessions, a second logout without a session can still show the login page. For APIs, an “ensure signed out” endpoint may return 204 even when already logged out, provided that is an explicit contract choice rather than an unexamined assumption for all APIs.

### 5.2. Why Don't APIs Usually Redirect?

REST/HTTP clients may automatically follow `302`, accidentally calling `GET /login` and receiving HTML instead of the expected status. Some clients strip or forward cookies or `Authorization` headers across redirects per library rules, causing risks and integration bugs. Returning a status code directly simplifies client code and keeps API responses UI-independent.

Simply naming a path `/api/**` does not make Spring Security switch from redirects to status codes automatically; you must configure the right **logout success handler** or controller endpoint on the API chain.

## 6. CSRF: Both Web Logout and API Logout Need a Threat Model

Logout mutates authentication state, so **use POST** and protect against third-party sites triggering logout on the user's behalf while browsers automatically send credentials/cookies.

For web form login / cookie sessions:

- Keep default CSRF active.
- The browser sends the session cookie and server-issued CSRF token.
- `GET /logout` (if present) should only show a confirmation form with no side effects.
- `POST /logout` missing/wrong token normally receives **403**; never replace it with an unprotected GET logout.

For APIs, two models are common:

1. **Browser clients with cookies or cached HTTP Basic auto-sending credentials:** evaluate CSRF and apply CSRF tokens just like web.
2. **Backends/mobile apps or Bearer tokens sent explicitly in `Authorization` headers:** a different CSRF policy may apply **only if** you prove requests cannot be forged cross-site by browsers carrying credentials under your threat model.

Do not write `csrf.disable()` for every API without examining the client. The runnable example in section 8 **keeps CSRF in both chains**, using `CookieCsrfTokenRepository` and a `GET /api/csrf` endpoint on the API so clients fetch the token and cookie for `POST /api/logout`. This is a more complete demo than disabling CSRF merely to test with `curl`.

### API Using `CookieCsrfTokenRepository` in the Example

`CookieCsrfTokenRepository` stores the CSRF token in a cookie (e.g., `XSRF-TOKEN`), and Spring Security matches it against the token sent by the client in a header like `X-XSRF-TOKEN`. With Spring Security 6's default token masking, the value exposed to the client via `CsrfToken.getToken()` can differ from the raw cookie value; **use the server token returned by the demo endpoint** rather than reading the cookie and assuming the raw cookie value works with every handler.

Because the client retrieves the token via a legitimate same-origin request and sends back both the header and cookie, CSRF protection distinguishes it from a cross-site HTML form that cannot arbitrarily read the token. When moving to a cross-origin frontend, configure CORS/origins and credentials carefully, and never open `Access-Control-Allow-Origin: *` for sensitive data.

## 7. Two Independent `SecurityFilterChain`s: Web and API

In an application serving both web browsers and APIs, split the chains explicitly:

```text
            HTTP request
                 |
                 v
           FilterChainProxy
                 |
        +--------+---------+
        |                  |
   path /api/**          other paths
        |                  |
        v                  v
   API chain @Order(1)   WEB chain @Order(2)
   - HTTP Basic          - Form login
   - STATELESS           - IF_REQUIRED/session
   - Cookie CSRF         - Web CSRF
   - /api/logout         - /logout
   - 204 No Content      - 302 /login?logout
```

In Spring Security, **only the first matching chain is selected**. `http.securityMatcher("/api/**")` defines the chain's scope, whereas `authorizeHttpRequests().requestMatchers(...)` defines authorization inside that chain. Hence the API chain must precede the WEB fallback; otherwise API requests could be redirected to `/login` by the web chain.

Easy-to-miss detail: an app has **two distinct logout URLs**, each belonging to `LogoutFilter` in its respective chain. Never set `logoutSuccessUrl` only on the web chain and expect `/api/logout` to return 204.

### Handling the Web Session When an API Logout Request Carries Cookies

Even when the API chain uses `SessionCreationPolicy.STATELESS`, `SecurityContextLogoutHandler` can still see an existing `HttpSession` through the Servlet API during logout. If the API must not log out the web session too, explicitly set:

```java
// Fragment for the API chain to avoid API logout invalidating the web HttpSession.
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .invalidateHttpSession(false)
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT))
);
```

This fragment is used in section 8's example. **`STATELESS` by itself is not equivalent to “no logout handler will ever touch an existing session.”** When both web and API must sign out together, define clear boundaries first, then explicitly invalidate the web session or revoke tokens in a unified flow.

## 8. Runnable Example: Spring Boot 3.3.5 + Java 17+

The lab builds a Servlet application with:

- Web form login: `GET /dashboard` requires login; `POST /logout` redirects to `/login?logout`.
- API HTTP Basic: `GET /api/me` requires Basic credentials; `GET /api/csrf` issues a token for `POST /api/logout`; `POST /api/logout` returns **204** with no redirect.
- API is configured `STATELESS`; API logout does not automatically invalidate the web session.
- The demo has one user `lan` / `demo123`, role `USER`. **Use on localhost for learning only**; never hard-code real accounts.

### 8.1. Project Structure

```text
logout-web-api-demo/
├── pom.xml
└── src/main/java/example/logoutdemo/
    ├── LogoutDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>logout-web-api-demo</artifactId>
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
```

### 8.3. `LogoutDemoApplication.java`

```java
package example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 8.4. `SecurityConfig.java`: Two Chains with Two Success Handlers

```java
package example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        http.requestCache(cache -> cache.requestCache(new NullRequestCache()));

        // API retains CSRF. Token is issued at GET /api/csrf
        // and POST /api/logout must return matching header + cookie.
        http.csrf(csrf -> csrf
                .csrfTokenRepository(new CookieCsrfTokenRepository())
        );

        http.logout(logout -> logout
                .logoutUrl("/api/logout")
                // API logout DOES NOT automatically invalidate the web session
                // if the client happens to send the web UI's JSESSIONID cookie too.
                .invalidateHttpSession(false)
                .logoutSuccessHandler(
                        new HttpStatusReturningLogoutSuccessHandler(
                                HttpStatus.NO_CONTENT))
        );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/dashboard").authenticated()
                .anyRequest().authenticated()
        );

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
        );

        http.formLogin(Customizer.withDefaults());

        // Default web logout: POST /logout with valid CSRF,
        // invalidates session + clears SecurityContext, then redirects.
        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
        );

        return http.build();
    }
}
```

**Reading the code along the flow:**

1. `@Order(1)` and `securityMatcher("/api/**")` force `/api/logout` into the API chain; `@Order(2)` web chain is the fallback for other URLs.
2. API `httpBasic()` is only the authentication mechanism **for requests passing through the Basic filter**. Since `LogoutFilter` runs before the Basic filter, `POST /api/logout` can be processed without Basic credentials; this demo does not claim to revoke or verify credentials at the logout endpoint.
3. `SessionCreationPolicy.STATELESS` does not use `HttpSession` to obtain the API's `SecurityContext`. `invalidateHttpSession(false)` in API logout avoids accidentally invalidating the web session when a client also sends the web cookie.
4. `NullRequestCache` avoids saving requests and form-login redirects for the API. API logout uses `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)`, so no HTML page is returned.
5. `CookieCsrfTokenRepository` lets GET receive the CSRF token/cookie and POST send the token via header. `CsrfFilter` checks before `LogoutFilter`; CSRF failures typically return 403.
6. Web uses form login `IF_REQUIRED` and default CSRF. `logoutSuccessUrl("/login?logout")` redirects the browser after handlers complete.
7. The example does not register `LogoutFilter` twice via `addFilterBefore`. The `logout(...)` DSL configures the built-in filter per chain.
8. Each HTTP request executes **only the first matching chain**, so API settings must never be copied blindly from the web chain.

### 8.5. `DemoController.java`

```java
package example.logoutdemo;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home:public";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication auth) {
        return "dashboard:" + auth.getName();
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication auth) {
        return "api:" + auth.getName();
    }

    @GetMapping("/api/csrf")
    public String apiCsrf(CsrfToken token) {
        // Demo: return CSRF token per Spring Security 6 mechanism.
        // Same-origin endpoint; do not open CORS arbitrarily.
        return token.getToken();
    }
}
```

There is no `@PostMapping("/logout")` or `@PostMapping("/api/logout")` in the controller. Both POSTs are handled by **`LogoutFilter`**, via `logoutUrl` in the matching security chain.

`GET /api/csrf` is an endpoint for this lab; in production, select an appropriate CSRF token distribution design with origin/CORS protection and prevent proxies/CDNs from caching tokens in ways that leak them to other clients. Never treat CSRF tokens as access tokens or usernames/passwords.

### 8.6. Running the Application

From the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Use JDK 17+ and Maven 3.9+; upon startup, embedded Tomcat listens by default on `http://localhost:8080`. HTTP on localhost is for demo use only. **Production requires HTTPS** to protect session cookies, CSRF tokens, and Basic credentials.

## 9. Verifying the WEB Flow: POST Logout → 302 Redirect

Use a fresh browser window without a session to test:

1. Open `http://localhost:8080/dashboard`; unauthenticated, the browser is typically redirected to `/login`.
2. Log in with `lan` / `demo123` on Spring Security's default form.
3. Verify `/dashboard` returns:

```text
dashboard:lan
```

4. Visit `GET /logout`. When CSRF is enabled, Spring Security typically shows a **logout confirmation page**. Click the logout button on that page to submit POST with the CSRF token.
5. The browser redirects to `/login?logout`; in the Network panel, observe the POST logout response is **302**.
6. After logging out, visit `/dashboard` again and verify the browser must log in again. Distinguish between the session cookie being invalidated and the browser still keeping an old `JSESSIONID` value in its cookie store.

**Do not use `curl -I /logout` to simulate logout**, because `-I` sends HEAD rather than POST with CSRF. Also do not use `GET /logout` as a test asserting the session was destroyed.

Example response shape:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login?logout
```

These are the expected header lines. Additional `Set-Cookie` and cache/security headers may appear; `Location` may be a relative path and context paths/proxies affect the URL.

### If Web Logout Returns 403 After Login

Verify the POST request has the right CSRF token, the session cookie is sent, the form action matches `/logout` in the web chain, and reverse proxies do not corrupt origin/scheme. Never fix it by disabling CSRF app-wide or enabling unprotected GET logout.

## 10. Verifying the API Flow: `POST /api/logout` → 204

The lab uses `CookieCsrfTokenRepository`, so before POST you must fetch the token and save the cookie. These commands are for a POSIX shell:

```bash
# Fetch the server-issued CSRF token + XSRF-TOKEN cookie on the same origin.
csrf_token="$(curl -s -c api-cookies.txt http://localhost:8080/api/csrf)"

# Send API logout POST with cookie and token in header.
curl -i -b api-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/logout
```

With the demo configuration, expected response:

```http
HTTP/1.1 204 No Content
```

A 204 response has no body and no `Location` redirect; other headers (such as a cleared or updated CSRF cookie) may appear depending on logout handlers. Clients must not expect a JSON body on status 204.

**Why didn't the command need `--user`?** `LogoutFilter` handles the logout URL **before** the Basic authentication filter. Receiving 204 in the demo confirms the POST with a valid CSRF token was accepted by the logout flow; it **does not confirm** username/password from `Authorization` were checked or that a real token was revoked. This is intentional to avoid falsely teaching that every `/api/logout` call automatically revokes stateless credentials.

Test missing or invalid CSRF:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8080/api/logout
```

Expect **403** with the demo's CSRF config. Logout cleanup has not run because `CsrfFilter` rejects before `LogoutFilter`.

After the API logout returns 204, you can still call the API with valid HTTP Basic credentials:

```bash
curl -s -u lan:demo123 http://localhost:8080/api/me
```

Expected output:

```text
api:lan
```

**This is not a bug in the demo.** Username/password remain valid credentials; HTTP Basic has no session access token for `LogoutFilter` to destroy. If an API needs genuine logout/revocation, change the authentication mechanism or add appropriate credential locking/revocation policies. Never document 204 as “invalidating Basic passwords.”

### Lab Result Table

| Test | Expected result | Meaning |
| --- | --- | --- |
| Unauthenticated, visit `/dashboard` | 302 to login | Web requires form login |
| Web login with `lan` | 302 to saved URL or target | Creates session authentication |
| `GET /dashboard` logged in | 200 `dashboard:lan` | Session auth valid |
| `GET /logout` | Logout confirmation page | Does not destroy session on GET |
| `POST /logout` + cookie/CSRF | 302 to `/login?logout` | Web cleanup and redirect |
| `GET /dashboard` after web logout | 302 to login | Web session lost authentication |
| `POST /api/logout` missing CSRF | 403 | `CsrfFilter` rejects |
| `POST /api/logout` valid CSRF/cookie | 204, no body/redirect | API logout response succeeds |
| `GET /api/me` without Basic header | 401 | Stateless API requires credentials on this route |
| `GET /api/me` with valid Basic after 204 | 200 `api:lan` | 204 does not revoke Basic passwords |

## 11. Logout Differs Across Sessions, Remember-Me, JWTs, and Opaque Tokens

### 11.1. Web Session

A web session is server-side state, so `SecurityContextLogoutHandler` can invalidate `HttpSession`, stopping the current session ID from accessing the old `SecurityContext`. This usually constitutes **real logout** for session-based authentication.

Some apps also use Spring Session/Redis session stores, other devices, or SSO sessions. Logging out the current session **does not automatically destroy** all sessions on other devices or an Identity Provider session. If global logout is needed, add the corresponding flow.

### 11.2. Remember-Me Cookie

If remember-me is enabled, the remember-me cookie can restore the user after the session is destroyed. Thus the logout flow must integrate `RememberMeServices` to delete the cookie and, for persistent remember-me, clean up token records. Spring Security can attach a remember-me logout handler as configured.

However, deleting the browser cookie **does not guarantee revocation of a stolen cookie copy** if using a still-unexpired signed token-based remember-me token. Per-device revocation demands an appropriate token store/revocation design.

### 11.3. Bearer JWT

Self-contained JWTs generally remain valid until expiry (assuming signature, issuer, audience, and other checks pass). `SecurityContextLogoutHandler` cannot “erase” an already-issued JWT from the world. Clients can delete their local copy; if immediate revocation is needed, use a denylist/revocation mechanism, short-lived access tokens with refresh-token rotation/revocation, or corresponding IdP policies.

### 11.4. Opaque/Refresh Tokens with a Server-Side Store

If the server controls token records, you can build a logout endpoint that **authenticates the token first**, locates the exact token or token family to revoke, updates the token store atomically, and returns 204/200 on success. Define idempotency and error handling for token-store failures.

A design-illustration fragment:

```text
POST /api/logout + Bearer access/refresh token
    -> authentication filter verifies token
    -> controller/service uses trusted principal or token ID
    -> revoke server-side token/refresh-token family (if any)
    -> clear context/credentials per policy
    -> 204 No Content once contract completes
```

**The snippet above is an architectural illustration, not behavior generated automatically by `http.logout()`.** In a stateless bearer API, if a controller needs an already-verified `Authentication` before revocation, use a controller/service endpoint protected through the authentication/authorization chain rather than `LogoutFilter` running before authentication filters. Real-world design also depends on the authorization server, token type, and provider revocation capabilities.

## 12. Redirect Handler and Status Handler: Controlled Customization

### 12.1. Using `SimpleUrlLogoutSuccessHandler`

When web post-logout URL selection logic is needed, Spring Security provides `SimpleUrlLogoutSuccessHandler`. For a fixed URL, however, `logoutSuccessUrl("/login?logout")` is usually shorter and less error-prone.

```java
// Replacement fragment for logoutSuccessUrl when creating an explicit handler.
SimpleUrlLogoutSuccessHandler handler = new SimpleUrlLogoutSuccessHandler();
handler.setDefaultTargetUrl("/login?logout");
http.logout(logout -> logout.logoutSuccessHandler(handler));
```

This fragment requires importing `org.springframework.security.web.authentication.logout.SimpleUrlLogoutSuccessHandler`; do not set multiple success handlers simultaneously and expect all of them to run. If your code picks a URL dynamically per request, prevent open redirects and avoid leaking sensitive details in query parameters.

### 12.2. Returning JSON 200 for an API

If the client requires a body, use a custom handler:

```java
// Replacement fragment for HttpStatusReturningLogoutSuccessHandler.
// Use when the API contract requires a JSON body.
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .invalidateHttpSession(false)
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"status\":\"signed_out\"}");
        })
);
```

This is a fragment for an **alternative option** in the API chain. With a 200 response, a JSON body can help some clients, yet never return credentials, stack traces, or token records in the response. If you truly want **204**, use a status-only handler with no body as in section 8.

### 12.3. Cookie Cleanup Does Not Equal Server-Side Cookie Invalidation

You can configure:

```java
// Fragment: add when the app knows the exact cookie name/path.
http.logout(logout -> logout
        .deleteCookies("JSESSIONID", "remember-me")
        .logoutSuccessUrl("/login?logout"));
```

This example explains `CookieClearingLogoutHandler`, not a mandate to delete every cookie by name in all environments. A cookie is only deleted by the browser if the `Set-Cookie` response has compatible domain/path and attributes. Invalidating `HttpSession` on the server is what renders the old session invalid; the browser retaining a cookie ID does not revive a server-side session.

For remember-me, prefer properly configuring/integrating `RememberMeServices` so the logout handler knows the matching cookie or token repository rather than only adding `deleteCookies` and neglecting server-side persistent tokens.

## 13. Security Rules for Logout

- **CSRF:** logout is a state-changing action. Cookie-based browsers need a valid CSRF token; never turn `GET /logout` into an unprotected logout action.
- **HTTPS:** protect session cookies, Basic credentials, CSRF tokens, and all bearer tokens from interception in transit. Use `Secure`/`HttpOnly`/`SameSite` per threat model.
- **Caching:** post-logout, sensitive pages should not be cached uncontrollably by browsers/proxies. Check `Cache-Control` and prevent sensitive data from appearing via history/back cache per policy.
- **Idempotency:** define clearly how repeated logouts should respond. Avoid accidentally causing side effects on another account from an unauthenticated logout request.
- **No leaks:** never place session IDs, `Authorization` headers, access/refresh tokens, or passwords in `Location` URLs or logs.
- **Per-device state:** current web logout differs from all-devices logout and from token/SSO session revocation; name APIs clearly.
- **SSO/OIDC:** local logout does not automatically log out of an Identity Provider; back-channel/front-channel logout or OIDC RP-initiated logout are separate flows to verify with the provider.
- **`SecurityContext` and browsers:** `SecurityContextHolder` is request-scoped; destroying the session and context does not make browsers forget cached Basic passwords.
- **Open-redirect defense:** redirect only to safe/controlled URLs; never trust arbitrary target parameters.
- **Honest status codes:** return “revoked” only if the token was actually revoked per contract; `HttpStatusReturningLogoutSuccessHandler` does not do this automatically.

## 14. Common Errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Web POST logout returns 403 | Missing/wrong CSRF token or mismatched session cookie | `CsrfFilter`, form action, hidden CSRF, `SameSite`/cookie |
| `GET /logout` does not destroy session | With CSRF enabled, GET only shows confirmation page | Use POST with valid token |
| Web logout returns 204 instead of redirect | Request hit the API chain or API handler registered on web | `securityMatcher`, `@Order`, logout matcher |
| API logout returns 302 to HTML login | Request entered web chain or uses default redirect success handler | API chain match, `HttpStatusReturningLogoutSuccessHandler` |
| API logout with valid CSRF still lets user call API | Basic credentials or JWT remain valid | Distinguish status cleanup from credential revocation |
| `POST /api/logout` without auth still returns 204 | `LogoutFilter` runs before `BasicAuthenticationFilter` | If authenticated token revocation is needed, use a protected flow/service |
| API logout kills the web session too | Logout handler sees/invalidates existing `HttpSession` | Check `invalidateHttpSession(false)` on API chain, or unify policy |
| After web logout, returning to `/dashboard` still returns 200 | Session/context not cleared, client sends another cookie/token, or remember-me auto-logins | Debug session invalidation, `SecurityContextRepository`, remember-me |
| `Set-Cookie` sent yet browser keeps cookie | Domain/path/`SameSite`/`Secure` mismatch | Inspect cookie attributes, context path, proxy |
| 204 returned yet client still follows redirect | Proxy/API gateway/custom handler or misbehaving frontend | Network traces, endpoint handler, gateway |
| Changed logout URL then GET/POST gives 404 | URL lies outside `securityMatcher` or conflicts with controller matcher | Exact chain, `logoutUrl`, request method |
| JWT logout only clears context; stolen token still works | JWT has no denylist/revocation | Design revocation/rotation/TTL |
| Logout repeatedly fails with 401 | Endpoint demands auth at wrong layer, missing credential, or gateway blocks upstream | Security chain order, gateway policy, endpoint contract |

### Systematic Debugging Workflow

1. Confirm the **HTTP method**, path, cookies, CSRF header, and `Authorization` scheme—without logging secret values.
2. Confirm the selected chain via `FilterChainProxy`, `/api/**` or web fallback matcher, and `LogoutFilter` in that chain.
3. Check whether **`CsrfFilter`** passed the request; if 403 before logout, cleanup has not run.
4. Confirm `LogoutHandler` executed session invalidation/context clearing/cookie or token revocation as required.
5. Confirm `LogoutSuccessHandler` actually ran: web redirect or API status.
6. Inspect `Location`, `Set-Cookie`, and response status/body rather than inferring from the post-redirect page.
7. Send a **fresh post-logout request** to a protected resource: the web session is gone, whereas API Basic may still succeed when credentials remain valid.
8. If remember-me, JWT, SSO, or token stores are present, verify revocation mechanisms separately rather than just local logout.

In development, you can safely enable logging:

```properties
logging.level.org.springframework.security=DEBUG
```

Never enable logging of raw `Authorization`, passwords, CSRF tokens, session IDs, or refresh tokens in production.

## 15. Self-Study Questions

1. **How does `LogoutHandler` differ from `LogoutSuccessHandler`?** The first cleans up security state; the second decides the HTTP response.
2. **Why does web usually return 302 after logout?** The browser needs to navigate to a login or public page.
3. **Why do APIs usually return 204?** Clients want a machine-readable status without an HTML redirect or body.
4. **Does default `GET /logout` invalidate the session when CSRF is enabled?** Usually no, it displays a confirmation page; POST with CSRF executes logout.
5. **What does a CSRF failure cause?** Potentially 403 before `LogoutFilter` runs.
6. **If API logout returns 204, do Basic passwords expire?** No. Basic credentials remain valid unless the server changes/revokes them.
7. **Does `LogoutFilter` run before or after `BasicAuthenticationFilter`?** Normally **before**, so the logout URL does not necessarily have a Basic-authenticated principal.
8. **Does `STATELESS` automatically stop an API logout handler from invalidating an existing web `HttpSession`?** No; explicit logout handler policy is needed.
9. **Why use `invalidateHttpSession(false)` in the demo API chain?** To avoid accidentally destroying a web session when a web cookie is present, without claiming to revoke tokens.
10. **Can `204 No Content` carry a JSON body?** No; if a body is needed, choose 200 or another status.
11. **Does logout automatically revoke an unexpired JWT?** No, revocation/denylists or a different token lifecycle design is needed.
12. **If web logout succeeded yet sensitive pages still appear via the Back button?** Inspect browser caching/controls, and test a real network request to check whether the server still permits access.
13. **Are single-device logout and all-devices logout the same?** No; session/token stores and logout contracts must define them separately.
14. **What is a post-logout open redirect?** Letting the client choose a redirect URL to an external domain without validation.
15. **When should an API controller be used instead of `LogoutFilter`?** When you must authenticate a bearer token first, check permissions, and revoke by token ID in a dedicated service.

## 16. Implementation Checklist

- [ ] Separate web and API into distinct `SecurityFilterChain`s when they have different logout responses.
- [ ] Web: use POST logout with CSRF, clean up session/context, and redirect to a safe fixed URL.
- [ ] API: define success status (`204` with no body or `200` with JSON), avoiding HTML redirects.
- [ ] Distinguish `LogoutHandler` performing cleanup from `LogoutSuccessHandler` returning the HTTP response.
- [ ] Do not rely on `authorizeHttpRequests().authenticated()` by default to guard a URL already handled earlier by `LogoutFilter`.
- [ ] If API logout must not destroy the web session, set `invalidateHttpSession(false)` and inspect other handlers.
- [ ] Apply CSRF according to client/credential type; never disable it globally just because an API uses Basic or `STATELESS`.
- [ ] If logout is advertised as “revoking tokens,” actually implement revocation and return errors when revocation fails.
- [ ] Enforce HTTPS and cookie security; avoid open redirects, tokens in URLs, and logging secrets.
- [ ] For remember-me, verify logout handlers clear cookies/persistent token repositories properly.
- [ ] For JWT/SSO, distinguish local logout from global logout or token revocation.
- [ ] Test the logout request, redirect/status, and **new protected requests after logout**, not only 302/204.
- [ ] Test web/API using real clients; ensure CSRF cookies and tokens are sent properly.

**Summary:** in Spring Security Servlet, **`LogoutFilter`** intercepts logout requests, **`LogoutHandler`** instances clean up state, and **`LogoutSuccessHandler`** decides the response. **Web** typically uses a `302 /login?logout` redirect; **APIs** typically return `204 No Content` or status/JSON per contract. Session policies, CSRF, and revocation of Basic/JWT/remember-me credentials must be designed independently — **a success status code is not proof that all credentials have been invalidated**.