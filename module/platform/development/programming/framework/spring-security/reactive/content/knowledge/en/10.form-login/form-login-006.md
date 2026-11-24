# ServerRequestCache and Restoring the Original Request After Form Login

**Topic:** Spring Security – reactive / Spring WebFlux  
**Section:** Form login (*form login*)  
**Objective:** Understand why a user accessing a login-protected page is sent to the login page and then returned to the exact original URL; learn how to configure `ServerRequestCache`, verify sessions and CSRF, distinguish *restoring a URL via redirect* from *replaying the entire HTTP request*, and recognize security risks.

Scenario: an unauthenticated user opens `GET /members/report?period=Q1`. The app requires authentication and sends them to `/login`. After entering the right username/password, the expected experience is returning to `/members/report?period=Q1`, rather than always going to the home page. In Spring Security WebFlux, **`ServerRequestCache` stores the interrupted request**, and **`RedirectServerAuthenticationSuccessHandler` chooses the redirect target after successful authentication**. These two components work alongside security filters, WebSession, and the security context.

A key WebFlux detail: the common default implementation `WebSessionServerRequestCache` **only saves the request URL**; it does not retain and re-execute the original body, headers, or write operations. The browser typically issues **a new GET** when following the post-login redirect. Understand this limitation before designing checkout pages, file uploads, payment POSTs, or SPAs.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the journey *anonymous GET → save URL in WebSession → redirect to login → POST username/password + CSRF → authenticate → redirect to saved URL → new GET with logged-in session*.
2. Distinguish `ServerRequestCache`, `WebSessionServerRequestCache`, `ServerRequestCacheWebFilter`, `RedirectServerAuthenticationSuccessHandler`, and `ServerSecurityContextRepository`.
3. Wire the **same `ServerRequestCache` instance** into `ServerHttpSecurity.requestCache(...)` and the success handler when customizing, avoiding policy mismatches.
4. Know why requests save **GET** only by default, why POSTs do not have their body restored or re-executed automatically, and the meaning of related markers like `continue`.
5. Test the flow using a browser, `curl` with a cookie jar, and `WebTestClient`, keeping CSRF protection intact.
6. Handle direct logins with no waiting request, multiple tabs sharing a session, expired sessions, proxy rewrites, and open-redirect prevention.

## 2. Roles in the Saved-Request Lifecycle

| WebFlux Component | Primary Responsibility | Do Not Misunderstand |
| --- | --- | --- |
| `SecurityWebFilterChain` | Holds Spring Security WebFilters applied to requests | Does not imply all URLs are permitted |
| `ServerHttpSecurity.authorizeExchange(...)` | Determines which URLs require authentication/permissions | Does not save request bodies itself |
| `ServerRequestCache` | Contract for saving/reading a request to support post-auth redirects | Not a database message queue or response cache |
| `WebSessionServerRequestCache` | Saves requested URL info into `WebSession`; considers GET by default | Does not save raw POST bodies for re-execution |
| `ServerRequestCacheWebFilter` | Matches an incoming returning request against the saved request per cache policy | Does not replace the authentication filter |
| `RedirectServerAuthenticationSuccessHandler` | On login success, prioritizes saved redirect URL; otherwise uses fallback, default `/` | Does not verify passwords itself |
| `WebSessionServerSecurityContextRepository` | Saves and loads `SecurityContext` for subsequent requests | Not identical to `ServerRequestCache` |
| `CsrfWebFilter` | Protects state-changing operations, including POST login | Not a pre-login URL-saving mechanism |

Do not confuse these **WebFlux** APIs with the Servlet counterparts: `HttpSessionRequestCache`, `RequestCacheAwareFilter`, `SavedRequestAwareAuthenticationSuccessHandler`, `HttpSecurity`, `SecurityFilterChain`. Similar names belong to a different stack and cannot be copied directly into reactive code.

### 2.1. A Typical Path

```text
[1] Anonymous browser
    GET /members/report?period=Q1
       |
       v
[2] Spring Security: URL requires authenticated()
       |
       +--> WebSessionServerRequestCache.saveRequest(exchange)
       |       saves URI into browser A's WebSession
       |
       +--> RedirectServerAuthenticationEntryPoint
               HTTP 302 Location: /login
               Set-Cookie: SESSION=...  (if session is created)
       |
       v
[3] Browser GET /login with SESSION cookie
       |
       +--> login page displays form + hidden CSRF token
       |
       v
[4] Browser POST /login:
        username=reader&password=reader123&_csrf=<token>
        Cookie: SESSION=...
       |
       +--> CSRF is verified
       +--> ReactiveAuthenticationManager verifies credentials
       +--> SecurityContext is saved per configured mechanism
       |
       +--> RedirectServerAuthenticationSuccessHandler
               queries requestCache.getRedirectUri(exchange)
               HTTP 302 Location: /members/report?period=Q1[&continue...]
       |
       v
[5] Browser GETs target URL with authenticated session
       |
       +--> ServerRequestCacheWebFilter checks matching request
       +--> Session's SecurityContext is loaded
       +--> authorizeExchange permits
       |
       v
[6] 200: report:Q1:reader
```

The numbers, URL paths, and headers in the diagram are **illustrative**, not a byte-for-byte HTTP transcript: `Location` may be a relative or absolute URI, the redirect status may be 302 or a variant depending on the redirect strategy, cookies may be re-issued or rotated, and the cache may append a `continue` marker. Still, the core rule is that **the target address reflects the original URL** while the saved request remains valid in the same session.

## 3. What Does WebSessionServerRequestCache Actually Store?

The `ServerRequestCache` interface belongs to package `org.springframework.security.web.server.savedrequest` and provides:

```java
Mono<Void> saveRequest(ServerWebExchange exchange);
Mono<URI> getRedirectUri(ServerWebExchange exchange);
Mono<ServerHttpRequest> removeMatchingRequest(ServerWebExchange exchange);
```

These are **abbreviated signatures for learning**, not an interface to re-implement yourself. Meaning:

- `saveRequest(exchange)`: saves the request requiring authentication to restore after login. The `Mono` only takes effect when **subscribed** in the pipeline; calling the method and ignoring the `Mono` may save nothing.
- `getRedirectUri(exchange)`: reads the URI suggested for the redirect. With `WebSessionServerRequestCache`, the URI typically includes a query marker used to detect the target request when the user follows the redirect.
- `removeMatchingRequest(exchange)`: when the current request matches the saved request per cache rules, retrieves the saved request and removes the consumed entry. It is **not** a "replay POST request" action.

`WebSessionServerRequestCache` uses `WebSession` to store the URL. Per the API docs, this implementation currently **stores only the requested URL** and by default `setSaveRequestMatcher` matches **GET** requests. That avoids accidentally re-running methods that mutate state; it also means old POST form payloads, multipart uploads, bearer tokens, or request bodies **are not preserved** for retransmission.

### 3.1. Why Is There a `continue` Parameter?

Some Spring Security versions append a default query marker named `continue` to the redirect URI. It helps `removeMatchingRequest` recognize that the incoming GET request is returning from a saved request, rather than querying the session cache on **every** HTTP request. The marker may be appended as `?continue` or `&continue` depending on whether the URL already has a query string.

Example:

```text
Original URL:
  /members/report?period=Q1

Post-login Location may be:
  /members/report?period=Q1&continue

New GET from browser:
  /members/report?period=Q1&continue
```

Do not write tests requiring `Location` to **equal the exact original string** if the cache added a marker. Compare the URI path and business query parameters that must be preserved, and inspect the final response. The marker is not an authentication token, CSRF token, or access permission: unauthenticated users cannot view a resource merely by adding `?continue` themselves.

**One session typically holds only one saved target per cache at a time.** If a user opens multiple tabs requiring login and then signs in on another tab, the restored URL may be whichever request was saved most recently depending on timing. Do not use this mechanism in place of a per-tab workflow/transaction table.

### 3.2. What Role Does the Session Cookie Play?

Browser A must carry the **same WebSession** across the initial protected request, login page, POST login, and return redirect. If the `SESSION` cookie is deleted, blocked by the browser, scoped to another domain/path, expired, or altered by a proxy with wrong attributes, the success handler may fail to find the saved URL and fall back to the default page. If the session ID is rotated after login to defend against session fixation, the browser must use the newly issued cookie.

In the WebFlux/Boot demo below, `WebSession` is usually identified by a cookie named `SESSION`. Real systems can customize the cookie name, session store (e.g., Spring Session Redis), SameSite/Secure/HttpOnly flags, domain, and timeout. Never put session IDs into URLs to "fix" redirect issues.

## 4. Distinguishing Three Post-Login Outcomes

| Scenario | Saved Request | After Successful Login |
| --- | --- | --- |
| User opens a protected URL first, then logs in within the same session | Present and valid | Redirects to the protected URL (may include `continue` marker) |
| User opens `/login` directly and logs in | None | Redirects to the fallback configured on the success handler; default `/` |
| Session/cookie changed or expired before POST login | Old URL not found | Login needs valid CSRF/session; if auth succeeds but cache is lost, uses fallback |
| Wrong password | Old request may still wait | Usually redirects to `/login?error`; resource **not** shown yet |
| POST to a protected endpoint before login | Not saved by default per GET matcher | Does not replay POST or body; app must redesign the flow |
| Login succeeds but role is insufficient for original URL | Saved URL may still be used | After redirect, request may receive **403**, not granted access by default |

This is the difference between **authentication** and **authorization**: the success handler only knows login succeeded; it cannot guarantee the user has permission for every resource they intended to view. Controllers/services must still enforce authorization when the request returns.

## 5. Sample Spring Boot WebFlux Configuration, Java 17+

We build an application with:

- Public `GET /welcome`: post-direct-login page returning `welcome`.
- `GET /members/report?period=Q1` for logged-in users, returning `report:Q1:reader`.
- `GET /admin/overview` for admins only, to test 403 after logging in with the right password but the wrong role.
- Spring Security's default `GET /login` page and `POST /login` processing.
- `WebSessionServerRequestCache` sharing the **exact same instance** between the request-cache policy and the success handler, with `/welcome` as fallback.
- CSRF **kept enabled by default**; browsers/forms must send a valid token. Never disable CSRF just to make tests easier.

Demo accounts: `reader / reader123` (role `USER`), `admin / admin123` (role `ADMIN`). Use on **localhost** only; never use plaintext passwords in real applications.

### 5.1. Project Structure

```text
reactive-saved-request/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/saved/
    │   │   ├── SavedRequestApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── PageController.java
    │   └── resources/application.properties
    └── test/java/demo/saved/
        └── SavedRequestTests.java
```

The example uses **JDK 17+** and **Spring Boot 3.5.7** as a dependency baseline to reproduce the syntax. Versions are for learning; in real products, choose a supported Spring Boot/Spring Security patch release with no known security vulnerabilities.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-saved-request</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

Do not add `spring-boot-starter-web` (Spring MVC Servlet) to a WebFlux lesson. This ensures the example focuses on `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession`, and reactive WebFilters.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-saved-request
server.port=8080
```

### 5.2. Application Entry Point

`src/main/java/demo/saved/SavedRequestApplication.java`:

```java
package demo.saved;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SavedRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: Sharing the Same ServerRequestCache on Both Sides

`src/main/java/demo/saved/SecurityConfig.java`:

```java
package demo.saved;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.security.web.server.savedrequest.WebSessionServerRequestCache;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerRequestCache serverRequestCache() {
        WebSessionServerRequestCache cache = new WebSessionServerRequestCache();
        // Keep default GET matcher; do not auto-save POST/PUT/DELETE.
        return cache;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ServerRequestCache serverRequestCache) {

        RedirectServerAuthenticationSuccessHandler success =
            new RedirectServerAuthenticationSuccessHandler();

        // If no URL is waiting, go to /welcome instead of /.
        success.setLocation(URI.create("/welcome"));

        // Same cache instance as the chain's requestCache.
        success.setRequestCache(serverRequestCache);

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/welcome").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/admin/overview")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/members/report")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .requestCache(cache -> cache.requestCache(serverRequestCache))
            .formLogin(form -> form.authenticationSuccessHandler(success))
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
```

Reading the config decision by decision:

1. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates password hashes instead of `{noop}`. `MapReactiveUserDetailsService` is for demo purposes only; production uses a real user store and encoding.
2. `@EnableWebFluxSecurity` configures security for WebFlux, and `formLogin` enables form authentication with the generated login page. Because `form.loginPage(...)` **is not called**, the default `/login` page is created by Spring Security; if you customize `loginPage`, you must render the login form and error page yourself.
3. `@Bean ServerRequestCache` supplies a `WebSessionServerRequestCache` instance. This is the request cache, not a database cache or `SecurityContext`.
4. `.requestCache(cache -> cache.requestCache(serverRequestCache))` wires the cache into detecting login-required requests and the chain's saved-request WebFilter.
5. `RedirectServerAuthenticationSuccessHandler` uses the **same cache** on successful login with `/welcome` as fallback. Even without custom configuration, the handler has default saved-request handling with fallback `/`, yet sharing the instance makes the custom policy explicit.
6. `httpBasic(...disable())` is only so the browser demo clearly shows form login instead of an HTTP Basic challenge. Real apps can support multiple schemes but must design entry points/matchers carefully.
7. `.anyExchange().denyAll()` protects unpermitted routes; form login is handled by Spring Security in the appropriate filter. CSRF is not disabled, because **POST login needs CSRF protection**.

**Note on state:** The request cache saves the waiting target, while authentication is stored/restored by the **security context repository** (matching form login/WebSession defaults in Spring Security WebFlux). These are two separate tasks. Clearing the request cache does not mean logging out; clearing `SecurityContext` does not automatically mean the saved URL disappears immediately if the cache still holds it.

### 5.4. Controller Seeing the User After the Browser Returns

`src/main/java/demo/saved/PageController.java`:

```java
package demo.saved;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(value = "/welcome",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> welcome() {
        return Mono.just("welcome");
    }

    @GetMapping(value = "/members/report",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> report(
            @RequestParam(defaultValue = "Q1") String period) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(username -> "report:" + period + ":" + username);
    }

    @GetMapping(value = "/admin/overview",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

`/members/report` reads the principal from the Reactor Context of the request being processed by WebFlux; it does not rely on `ThreadLocal currentUser` or a singleton field. Query param `period` demonstrates that the destination URL retains query parameters. This is a plain-text body for the practice exercise; real applications must also validate inputs, check per-report permissions, page contents, tenants, and data-level authorization.

## 6. Testing the Journey in a Browser

Run:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Wait for the application to start on port `8080`; if the port is occupied, change `server.port` and adjust URLs accordingly.

In a **fresh incognito/private** browser window:

1. Open `http://localhost:8080/members/report?period=Q1`. Because you are not logged in, the browser must redirect to `/login`. In **DevTools → Network**, observe the request to `/members/report?period=Q1` returning a redirect, the `Location` response header, and `Set-Cookie` if a session was created.
2. On the login page, inspect the `username`/`password` form. Spring Security's generated login page adds a hidden CSRF input; you do not need to paste tokens manually when using the page's form.
3. Enter `reader` / `reader123`. After logging in, the browser must redirect back to the protected path you opened; the URL may gain a `continue` marker. The returned body is `report:Q1:reader`.
4. Reload the opened URL in the same session; since the browser holds a logged-in session, it receives `200` without re-entering the password. Inspect the cookie; do not assume credentials are stored in the URL.
5. Close the incognito session, open a **new session with no saved request**, visit `http://localhost:8080/login` directly, and log in. The expected fallback result is `/welcome` with body `welcome`.
6. Using the `reader` account, try `/admin/overview`: even after a valid login, it returns `403` due to lacking the ADMIN role. Redirects do not elevate permissions.

**Do not look only at the final URL.** Some browsers auto-follow redirects, so Network will show multiple requests with different statuses. Inspect the first response, the POST login, and the GET after redirect. Browser cache, extensions, cookie policies, or other open tabs can make a test look like "the request wasn't saved" even when the server works properly.

## 7. Testing Request-Cache with curl, Cookie Jar, and CSRF

`curl` does **not** persist cookies across commands by default, nor does it auto-follow redirects without `-L`. To simulate a single browser session, use `-c` (write cookies) and `-b` (read cookies). Example:

```bash
# Step 1: anonymous request; observe 302 and save SESSION cookie
curl -i -c cookies.txt \
  'http://localhost:8080/members/report?period=Q1'

# Step 2: reuse the same cookie to open login page and read hidden CSRF token
curl -i -b cookies.txt -c cookies.txt \
  'http://localhost:8080/login'
```

Key result: the first request redirects to `/login`. In the login page HTML, find the hidden input named `_csrf` and **extract the real token of the current session**. The token below is a **display placeholder** and must be replaced with the actual value just issued by the page:

```bash
# Step 3: replace TOKEN_FROM_LOGIN_FORM with the real token
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=reader' \
  --data-urlencode 'password=reader123' \
  --data-urlencode '_csrf=TOKEN_FROM_LOGIN_FORM' \
  'http://localhost:8080/login'
```

This is a *guide command with a runtime token placeholder*, not a command that succeeds if pasted literally with `TOKEN_FROM_LOGIN_FORM`. Use the token from the real form; never hardcode tokens in documentation or reuse them across two sessions. A successful response typically redirects to `/members/report?period=Q1` (possibly with a marker) and may issue a new cookie.

Afterwards, follow the exact `Location` returned by the server (using the updated cookie jar):

```bash
curl -i -b cookies.txt \
  'http://localhost:8080/members/report?period=Q1'
```

Expect body `report:Q1:reader` if `cookies.txt` retained the post-login security session. The final step intentionally uses the original URL to verify authentication; to test **saved-request matching handling**, call the exact `Location` URL from the login response. Do not use `curl -L` blindly when debugging form POSTs: you need to observe each redirect and prevent the tool from changing method/body unexpectedly.

**Clean up the demo cookie file** after practicing because session cookies are usable credentials. On Windows PowerShell, `curl` may alias another command; invoke `curl.exe`. With HTTP Basic people often send `-u`, whereas **form login in this lesson uses POST form + CSRF + SESSION cookie**, not sending Basic on every request.

## 8. Runnable WebTestClient + StepVerifier Test Suite

We test at two levels:

- **Standalone RequestCache:** `saveRequest` and `getRedirectUri` store/read the right URL, and the default matcher does not save POSTs. `MockServerWebExchange` lets us test without opening a port.
- **HTTP integration:** `@SpringBootTest(RANDOM_PORT)` runs a real server and checks anonymous redirects, browser session cookies, the CSRF token from `/login`, succeeding and returning to the saved target, and direct login using fallback. Use `WebTestClient` to send requests like a real client rather than mocking a user to hide HTTP authentication steps.

`src/test/java/demo/saved/SavedRequestTests.java`:

```java
package demo.saved;

import java.net.URI;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.security.web.server.savedrequest.WebSessionServerRequestCache;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SavedRequestTests {

    @Autowired
    WebTestClient client;

    private static String sessionCookie(
            EntityExchangeResult<?> response, String previous) {
        ResponseCookie cookie = response.getResponseCookies()
            .getFirst("SESSION");
        return cookie == null ? previous : cookie.getValue();
    }

    private static String csrfFromLoginPage(String html) {
        assertNotNull(html, "Login page HTML not found");

        // Find hidden _csrf input regardless of attribute order.
        Pattern input = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>");
        Matcher tag = input.matcher(html);
        assertTrue(tag.find(), "Input named _csrf not found");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "CSRF input value not found");
        return value.group(1);
    }

    @Test
    void cacheSavesGetUrlAndReturnsRedirectUri() {
        WebSessionServerRequestCache cache =
            new WebSessionServerRequestCache();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/members/report?period=Q1"));

        StepVerifier.create(
                cache.saveRequest(exchange)
                    .then(cache.getRedirectUri(exchange)))
            .assertNext(uri -> {
                assertEquals("/members/report", uri.getPath());
                assertTrue(uri.getRawQuery().contains("period=Q1"));
            })
            .verifyComplete();
    }

    @Test
    void defaultCacheDoesNotSavePostRequest() {
        WebSessionServerRequestCache cache =
            new WebSessionServerRequestCache();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.post("/members/submit"));

        StepVerifier.create(
                cache.saveRequest(exchange)
                    .then(cache.getRedirectUri(exchange)))
            .verifyComplete();
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() {
        client.get().uri("/members/report?period=Q1")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void anonymousVisitorCanOpenGeneratedLoginPage() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> assertTrue(html.contains("username")));
    }

    @Test
    void loginWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void savedGetIsRestoredAfterValidFormLogin() {
        // 1: Saved URL is created in the anonymous session.
        EntityExchangeResult<byte[]> initial =
            client.get().uri("/members/report?period=Q1")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String session = sessionCookie(initial, null);
        assertNotNull(session, "WebSession cookie missing");

        // 2: Open login form in THIS exact session.
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .cookie("SESSION", session)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        session = sessionCookie(page, session);
        String csrf = csrfFromLoginPage(page.getResponseBody());

        // 3: POST credentials + CSRF token + cookie of same session.
        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "reader")
                    .with("password", "reader123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location, "Missing Location after login");

        URI destination = URI.create(location);
        assertEquals("/members/report", destination.getPath());
        assertNotNull(destination.getRawQuery());
        assertTrue(destination.getRawQuery().contains("period=Q1"));

        // 4: Session ID may change on login; use the new one if present.
        String loggedInSession = sessionCookie(login, session);

        // Follow Spring's Location to test matching saved request.
        client.get().uri(destination)
            .cookie("SESSION", loggedInSession)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:Q1:reader");
    }

    @Test
    void directLoginWithoutSavedRequestUsesFallback() {
        EntityExchangeResult<String> page =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String session = sessionCookie(page, null);
        assertNotNull(session);
        String csrf = csrfFromLoginPage(page.getResponseBody());

        EntityExchangeResult<byte[]> login =
            client.post().uri("/login")
                .cookie("SESSION", session)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "reader")
                    .with("password", "reader123")
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = login.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertEquals("/welcome", URI.create(location).getPath());
    }
}
```

Run from the project directory:

```bash
mvn test
```

With only the class above, the target is **7 passing tests**. The test suite is presented to run in a learning project; this material **does not claim to have executed it** on your machine. Execution time and Maven log output depend on the runtime. The tests assert statuses and body/Location values rather than hardcoding all raw HTTP headers.

### 8.1. Why Do HTTP Tests Need Real Cookies and Tokens?

`RANDOM_PORT` starts a real HTTP server; the test client must send the **same session cookie** to look up the saved request and receive the security context. Default CSRF protection requires form POSTs to carry a token matching the session. Do not use `mockUser` or `mutateWith(csrf())` on a client going over a real network and assume they are transmitted as trusted info to the server; mock helpers are suited for `WebTestClient` bound to an application context with `springSecurity()`.

`csrfFromLoginPage` parses HTML rendered by Spring Security's generated login page. The regex serves as a **test helper for the demo page**, not a long-term HTML parser for production; if you replace the login page with a custom template, update the selector/token field accordingly. Use a proper HTML parser for your project when higher durability is needed.

`cacheSavesGetUrlAndReturnsRedirectUri` tests the cache directly without relying on login or a browser. Only `savedGetIsRestoredAfterValidFormLogin` proves the **complete journey**: session, CSRF, authentication, redirect with right path/query, and controller content with a real principal. Testing only the redirect to `/login` is not enough to confirm the saved request is read back after logging in.

### 8.2. Testing a Wrong Password with a Waiting Request

When a user has a saved URL and enters a wrong password, default form login usually redirects to `/login?error`; the resource must not be shown, and the saved request only remains meaningful while still in the same session and retained by the cache policy. Test:

- POST login with a valid CSRF token but wrong password: must not receive `200` from the protected resource.
- Next, re-enter the right password using a valid CSRF token/current cookie: verify the saved URL is preserved if the cache still holds the entry.
- If the session expired between attempts, the CSRF token may be stale and POST returns 403. Do not interpret this 403 as missing roles on the saved target.

**Do not** drop CSRF just to write a non-standard "happy path". Spring Security WebFlux protects POST login against login CSRF by default; use the token from the form or an explicitly designed API token.

## 9. Redirect URL Only — Do Not Replay POST, DELETE, or Bodies Automatically

This is the most important security and business boundary.

Suppose an unauthenticated user sends:

```http
POST /checkout/confirm HTTP/1.1
Content-Type: application/json

{"orderId":"A123","amount":999}
```

`WebSessionServerRequestCache` evaluates GET by default and **does not auto-save this POST**, so after login there is no replay of the POST along with its body. Even if you wrote a custom cache for POST, a browser following a 302 might issue a GET instead of a POST and lose the body; more importantly, automatically replaying an order/payment operation could create **duplicate side effects** or bypass CSRF checks.

For long input forms or checkout flows, safe design approaches typically include:

1. Have the user log in **before** submitting state-changing commands; or hold draft data safely on the client and resubmit after login.
2. If a business step must be preserved, create a server-side **draft ID** bound to the session/user/tenant, TTL, access checks, and replay protection; after login, ask the user to confirm again before POSTing.
3. Use an **idempotency key** for sensitive commands, with server-side validation and proper transactions to prevent double processing.
4. Never serialize raw bodies/PII or request Authorization headers into the saved request cache.
5. For non-GET methods, design UI/business state recovery explicitly; **do not alter the default GET matcher just to "avoid losing the form"**.

## 10. If You Do Not Want to Save Pre-Login Requests

Some applications are stateless APIs without browser sessions, or do not want to store pre-login URL history. In that case, use `NoOpServerRequestCache` in WebFlux and align the success handler/failure behavior consistently.

**Illustrative configuration fragment** (not a standalone runnable Java file; requires imports and the chain bean):

```java
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.savedrequest.ServerRequestCache;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

ServerRequestCache noSavedRequests = NoOpServerRequestCache.getInstance();

RedirectServerAuthenticationSuccessHandler success =
    new RedirectServerAuthenticationSuccessHandler("/welcome");
success.setRequestCache(noSavedRequests);

http
    .requestCache(cache -> cache.requestCache(noSavedRequests))
    .formLogin(form -> form.authenticationSuccessHandler(success));
```

`NoOpServerRequestCache` is an implementation that neither saves nor retrieves saved requests. When there is no saved URL, successful login always uses the handler's default location (per policy). Truly stateless JSON APIs should typically return **appropriate 401/403** instead of form redirects and pick a matching token/HTTP Basic mechanism; do not expose browser form login on all APIs merely because of framework defaults.

If a single application serves both browser HTML and JSON APIs, separate `SecurityWebFilterChain`s using appropriate matchers and `@Order`. Avoid letting browser cache/redirect settings cause API clients to receive unexpected HTML/302s, or having a catch-all chain shadow the login path.

## 11. Securing Saved Redirects: Open Redirect, Cookies, Proxy, Query

**Never trust any client-supplied redirect URL without validation.** If an app allows `?returnTo=https://example-attacker.test` and the success handler uses it directly, attackers can send users to their domain right after login. Allow redirects only within an explicit allowlist or application-owned relative paths, enforcing host/scheme constraints and proxy policies. Never treat an unfamiliar `Location` as safe just because the user just authenticated.

**CookieServerRequestCache is not the same as WebSessionServerRequestCache.** There is an implementation that stores the saved URI in a client-side cookie. Spring Security disclosed **CVE-2026-41706** for certain versions of `CookieServerRequestCache`/`CookieRequestCache` due to open-redirect risk when cookie values can be controlled. If using a cookie-backed request cache, check the advisory and upgrade to a patched version; this demo configuration uses `WebSessionServerRequestCache` and does not illustrate cookie-backed saved redirects. Reference: https://spring.io/security/cve-2026-41706/.

**Proxy and HTTPS:** A load balancer may terminate TLS, rewrite paths, or inject `Forwarded`/`X-Forwarded-*` headers. If configured without trust boundaries, redirects can use the wrong scheme/host/port, causing loops or redirecting to unintended domains. Accept forwarded headers only from trusted proxies, validate host allowlists, enable HTTPS outside localhost, and test URLs from a real browser through the actual ingress path.

**Session:** Protect the `SESSION` cookie with `HttpOnly`, `Secure` on HTTPS, and `SameSite` suited to the login flow, managing session fixation, timeouts, and logout. Spring Session/Redis changes where data is stored, not the rule that "a saved URL belongs to a specific session". After logout, do not keep a stale saved URL around to be returned to another user sharing the browser.

**Query parameters:** Saved URLs can contain business queries like `?period=Q1` and may show up in browser history, Referer headers, and proxy/access logs. Never put access tokens, passwords, reset secrets, or private data into query parameters just because the cache preserves the URL. Avoid logging full saved URLs if queries contain sensitive data.

## 12. Easily Confused Real-World Scenarios

| Symptom | Possibilities to Check | Proper Verification |
| --- | --- | --- |
| Login succeeds but always goes to `/welcome` | No saved URL, different session, missing cookie, saved request overwritten | Inspect initial protected request, session cookie, login POST, and `Location` |
| Redirects to another tab's URL | Two tabs share WebSession; newer saved URL overwrites older one | Reproduce with separate tabs/windows; consider workflow-specific state |
| Login page renders yet POST returns 403 | Missing/invalid CSRF token, session rotated/expired | Re-GET login with same cookie, extract fresh token, check form action |
| Right password yet POST returns `/login?error` | Authentication failure, user store, password encoder | Inspect safe server logs, username/password hash, and response flow |
| Login succeeds then GET to old URL returns 403 | User lacks role/permission for saved resource | Check `hasRole` and data permissions; do not broaden `permitAll` |
| Login succeeds then GET to old URL returns 404 | URL/resource does not exist or route rewritten | Check routing/path/query; saved request does not guarantee resource still exists |
| Browser receives 302 but API client expects JSON | Form-login entry point applied to API | Separate chains or explicit negotiation for API vs. web |
| Redirect URL contains `continue` | Cache uses marker for saved-request matching | Compare path + business query, check target response; do not treat marker as credential |
| Pre-login form POST is not replayed | Default cache stores GET URIs only | Design draft/idempotency and intentional resubmission |
| Redirects to HTTP instead of HTTPS | Reverse proxy/Forwarded headers misconfigured | Check trusted forwarded headers, TLS, and reverse-proxy config |
| External `?returnTo=...` sends users off-site | Unvalidated redirect parameter/cookie | Block external origins, patch affected Security versions |
| Target page returns 200 but wrong user | Broken SecurityContext/session isolation or business data caching | Assert body/user/tenant with real principals, not just HTTP status |

### 12.1. When Tests Only See a 302 Code

A 302 response could mean "going to login", "login succeeded to saved URL", "login failed to `/login?error`", or an HTTPS redirect at a proxy. **The same status does not imply the same outcome.** Always inspect `Location`, cookies, request method, and final response.

### 12.2. Why Is Spring Security's Default Login Page Sufficient for the Demo?

Default form login generates `GET /login`, accepts credentials at `POST /login`, and protects with CSRF when security config is active. This isolates the saved-request topic without needing Thymeleaf or custom HTML. When a project uses its own login page, ensure **form action and field names match**, render the CSRF token, make login and error URLs public, and re-test post-auth redirects.

### 12.3. Why Not Delete Sessions or Disable CSRF to Fix Redirect Bugs?

Because the session carries browser recognition and the security context, while CSRF protects POST login. Removing these layers breaks correctness or security instead of fixing the bug. If you need stateless auth, that is a different architecture: bearer tokens/401 APIs, without browser saved requests of this kind.

## 13. Operations and Testing Checklist When Changing Configuration

1. Specify **which routes are saved**: GET by default is a sound baseline; avoid URLs containing PII or methods with side effects.
2. Decide whether `ServerRequestCache` uses WebSession or another mechanism; if customized, share the instance with `RedirectServerAuthenticationSuccessHandler`.
3. Keep the generated/custom login page and `POST /login` working with CSRF; verify a valid fallback path such as `/welcome`.
4. Use an incognito browser to open a protected GET and observe `302 Location: /login` plus session cookie.
5. Log in within the **same cookie/session** and receive a redirect to the saved path/query; test both the marker and final response.
6. Log in directly with no saved URL and confirm it goes to the designed default target.
7. Test wrong passwords, missing/wrong CSRF, expired sessions, logout, insufficient roles, and changed/deleted URLs.
8. Test multiple tabs and proxies outside dev; distinguish last-saved behavior from session affinity.
9. Verify open-redirect defenses, cookie security, HTTPS, Forwarded headers, query secrets, and relevant security patches.
10. Do not treat saved requests as a way to preserve POST bodies; design separate draft/idempotency handling for transactional workflows.

## 14. Self-Check Questions

**Q1.** Does `ServerRequestCache` store the password from POST login?  
**No**, as `WebSessionServerRequestCache` is used here. The cache saves the pre-authentication request URL; CSRF/login forms handle credentials separately.

**Q2.** A user clicks login directly with no prior protected URL. Where do they go after login?  
To the **fallback location** of `RedirectServerAuthenticationSuccessHandler`: `/` by default, `/welcome` in this example.

**Q3.** Why can the post-login redirect URL carry `continue`?  
It is a marker that helps check whether a new request matches the saved request and avoids looking up the session on every request, **not an authentication token**.

**Q4.** After a valid login, the original URL returns 403. Did the request cache fail?  
**Not necessarily.** The saved URL may be exact, yet the user lacks the role/permission for the page; authentication and authorization are two separate steps.

**Q5.** Can the request cache be used to replay a money-transfer POST with its old body?  
**You should not.** By default the cache saves GET URLs; POSTs require proper workflow/state/idempotency design and user confirmation, not automatic replay.

**Q6.** Two tabs sharing a session store two different targets; will redirects always return to the first tab?  
**Not guaranteed.** One session can have a newer saved entry overwrite an older one depending on timing; build a separate workflow model if per-tab guarantees are required.

**Q7.** When writing a `WebTestClient` integration test, can you send only username/password without a CSRF token?  
**No** with default CSRF. You must extract a valid token from the login page and send it with the matching cookie, or use the proper mock helper for that test type.

**Q8.** Can you let clients pass `returnTo=https://outside.example` and redirect to it verbatim after login?  
**No.** That creates an open-redirect/phishing risk; allow only trusted relative URLs/allowlists and validate proxy headers.

**Q9.** Do `WebSessionServerRequestCache` and `WebSessionServerSecurityContextRepository` serve the same function?  
**No.** One holds the waiting URL; the other holds the `Authentication`/`SecurityContext` for subsequent requests.

**Q10.** Is testing 302 alone enough to prove request restoration works?  
**No.** You must assert that `Location` matches the saved URL/path/query and perform a follow-up GET with the logged-in session, observing the right response body/principal.

### Official Reference Documentation

- Spring Security, `ServerRequestCache` API (WebFlux): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/ServerRequestCache.html
- Spring Security, `WebSessionServerRequestCache` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/savedrequest/WebSessionServerRequestCache.html
- Spring Security, `RedirectServerAuthenticationSuccessHandler` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Security, `ServerHttpSecurity` / requestCache: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security, `FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security advisory, *CVE-2026-41706* (CookieServerRequestCache): https://spring.io/security/cve-2026-41706/

**Remember:** When an authentication-required **GET** is interrupted, `WebSessionServerRequestCache` holds the **URL** tied to the WebSession; form login authenticates and stores `SecurityContext`; `RedirectServerAuthenticationSuccessHandler` prioritizes the saved target and sends the browser back **via a new HTTP request**. This feature improves navigation UX; it **does not replay POST bodies**, does not bypass CSRF, and does not grant permissions beyond the destination page's policy.