# Splitting Security Chains for REST APIs, Login UI, and Admin Endpoints in Spring Security WebFlux

## Lesson Objectives

When a WebFlux application serves a **REST API**, a **form-based login UI**, and **admin endpoints** at the same time, each group typically needs different authentication mechanisms and access policies. This lesson shows how to split configuration into multiple `SecurityWebFilterChain` beans in **reactive Spring Security**, instead of cramming all rules and login mechanisms into a single chain.

After this lesson, you will be able to:

1. Identify the exact roles of `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity`, `securityMatcher`, and `@Order`.
2. Design three chains with clear responsibilities: REST API, web pages/form login, and admin zone.
3. Predict which chain receives `/api/**`, `/app/**`, `/login`, `/admin/**`, and undescribed paths.
4. Separate HTTP Basic/Bearer authentication from form login and determine session and CSRF scope.
5. Build a Java 17+ Spring Boot WebFlux example and test **200/401/403/redirect** as well as ordering/matcher bugs.

**Scope:** The lesson focuses on **splitting and selecting security chains**. JWT/OAuth2 authentication and Actuator management context configuration are noted as extensions; the runnable sample app uses HTTP Basic for API/admin so it can be tested directly with `curl`, and form login for UI.

## 1. Three layers to understand before splitting chains

In Spring Security WebFlux, the overall flow is:

```text
HTTP request
   |
   v
Global WebFlux WebFilter chain
   |
   v
Spring Security WebFilterChainProxy (a WebFilter)
   |
   +-- evaluate SecurityWebFilterChain beans by @Order
   |      |
   |      +-- each chain's securityMatcher(request)
   |      |
   |      +-- pick the FIRST matching CHAIN
   |             |
   |             +-- run that chain's security WebFilters
   |                    (authentication, authorization,
   |                     CSRF, exception translation... as configured)
   |
   v
Remaining WebFilterChain -> route handler -> HTTP response
```

- **`WebFilterChainProxy`** is the entry point into reactive Spring Security from WebFlux's `WebFilter` infrastructure; it iterates over security chains and inserts the chosen chain's filters into the processing path.
- **`SecurityWebFilterChain`** is a pair of **applicability condition** + **set of security WebFilters**. It is built from `ServerHttpSecurity.build()`, not an endpoint or a controller.
- **`securityMatcher(...)`** is the condition stating **which chain a request belongs to**.
- **`authorizeExchange(...)`** defines **access permissions after the chain has been selected**.
- **`@Order` on a `SecurityWebFilterChain` bean** defines **chain selection order**: smaller numeric values have higher priority; the first matching chain wins.
- **`SecurityWebFiltersOrder`** governs the order of filters inside a single chain; `@Order` on a global `WebFilter` is yet another ordering mechanism.

**Critical rule:** If the selected chain requires `authenticated()` and authentication fails, Spring Security **does not automatically jump to the next chain**. Match first, then run that chain's policy. Only requests that have not matched any chain continue to be tested against subsequent chains.

## 2. Defining responsibility boundaries for the three endpoint groups

A practical design can divide them as follows:

| Group | Illustrative paths | Chain priority | Authentication mechanism | Authorization rules |
| --- | --- | --- | --- | --- |
| Admin | `/admin/**` | 1 — `adminChain` | Dedicated HTTP Basic in demo; in production may need MFA, restricted network, or dedicated token | `hasRole("ADMIN")` |
| REST API | `/api/**` | 2 — `apiChain` | HTTP Basic in demo; in production typically Bearer/OAuth2 Resource Server | `authenticated()` or specific roles/scopes |
| UI and form login | `/login`, `/app/**`, `/public/**` | 3 — `webChain` (fallback) | Form login + web session | Public for login/static; app pages require login; remaining paths denied |

Placing **admin first, API second, UI last** embodies "specific matchers first, catch-all last". Even if `/admin/**` does not overlap `/api/**` so swapping the first two chains does not change current results, deliberate ordering protects against future path growth—such as moving admin under `/api/admin/**` or adding combined matchers.

If the system uses `/api/admin/**`, the broader `/api/**` condition would also match admin endpoints. In that case, the **`/api/admin/**` chain must come before** `/api/**`, or the API chain itself must include a fine-grained `hasRole("ADMIN")` rule. Never assume a later admin chain will "upgrade" permissions for a request that already entered the API chain.

**Do not equate chain separation with account separation.** The simple example shares one `ReactiveUserDetailsService` across all three chains; in real systems, different chains can use different `ReactiveAuthenticationManager` beans or identity providers. Even with a shared user store, the admin area's policy must still be tested independently.

## 3. Two questions about matchers and authorization

Suppose we have:

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/admin/**"))
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().hasRole("ADMIN"));
```

This snippet has **two decision layers**:

1. `securityMatcher("/admin/**")`: does the request belong to the zone handled by this chain? If not, the proxy tries the next chain.
2. `anyExchange().hasRole("ADMIN")`: once the chain is selected, does the principal hold the `ROLE_ADMIN` authority? If not, the request is denied or challenged according to this chain's mechanism.

By contrast, writing:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
```

in a chain **without `securityMatcher`** means the chain has a default matcher matching all requests; `pathMatchers` only controls permissions **inside the chain**. When such a chain comes first, it can "swallow" all `/api/**` and `/login` requests so later chains are never selected.

### Three-step design rule

- Step 1: list **URL groups, HTTP methods**, and authentication mechanisms for each group.
- Step 2: define `securityMatcher` for each specific chain; set explicit `@Order` values and add **one final fallback chain**.
- Step 3: inside each chain, define `authorizeExchange` with **specific rules first** and `anyExchange()` last; test valid URLs, neighboring URLs, and non-matching URLs.

If no security chain matches, `WebFilterChainProxy` can let the request proceed **without going through any chain's security filter set**. Therefore, never assume "no match means 403". A denying fallback path is an essential barrier, especially when protecting admin endpoints.

## 4. Complete example: Java 17+, Spring Boot 3.3.x, and WebFlux

The example builds a small app with these routes:

- `GET /api/data` returns `API_OK`, requiring valid HTTP Basic.
- `GET /admin/report` returns `ADMIN_OK`, only for accounts holding `ROLE_ADMIN` via HTTP Basic.
- `GET /app/home` returns minimal HTML after form login; without a valid session, the browser is redirected to the login page.
- `GET /public/ping` and `GET /` are public.
- `GET /login` and `POST /login` belong to **webChain**, handled by Spring Security form login; no custom `/login` handler is written in the demo.

### 4.1. File structure

```text
security-chain-split/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          SecurityChainSplitApplication.java
    test/
      java/
        example/
          SecurityChainSplitApplicationTests.java
```

Create `settings.gradle`:

```groovy
rootProject.name = 'security-chain-split'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot's BOM keeps Spring Framework, Spring Security, and Reactor versions aligned. Do not carelessly mix Servlet Spring Security dependencies/types such as `HttpSecurity`/`SecurityFilterChain` into this reactive example.

### 4.2. Application and three security chains

Create `src/main/java/example/SecurityChainSplitApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SecurityChainSplitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainSplitApplication.class, args);
    }

    @GetMapping("/api/data")
    public String data() {
        return "API_OK";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "ADMIN_OK";
    }

    @GetMapping(value = "/app/home", produces = MediaType.TEXT_HTML_VALUE)
    public String home() {
        return "<html><body><h1>APP_HOME</h1></body></html>";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/")
    public String index() {
        return "Public home; visit /app/home or /login";
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/admin/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().hasRole("ADMIN"))
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            // No securityMatcher specified:
            // default matcher covers everything else.
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/login", "/public/**").permitAll()
                .pathMatchers("/app/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(withDefaults())
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}view")
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password("{noop}admin")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(viewer, operator);
    }
}
```

**Why does this design make sense for the lesson?**

**`adminChain`:** matcher `/admin/**`, priority 1, requires `ROLE_ADMIN` and HTTP Basic. Account `viewer` authenticates successfully but only has `ROLE_USER`, so it still receives 403. Account `operator` holds `ROLE_ADMIN` and is allowed in.

**`apiChain`:** matcher `/api/**`, priority 2, requires any authenticated user; disables form login so an API call lacking credentials receives an HTTP Basic challenge instead of being redirected to a login screen.

**`webChain`:** omits `securityMatcher`, so it applies to requests that matched neither chain above. It enables form login; `GET /login` is served by Spring Security's default generated page when no custom login page is provided, and `POST /login` processes submitted credentials. `/app/**` requires a logged-in session; `/public/**` allows guests; remaining URLs hit `denyAll()`.

**`NoOpServerSecurityContextRepository` on API/admin:** does not store or restore `SecurityContext` via this repository between requests on these two chains, since the demo goal is for API/admin to require credentials per request. `webChain` does not use `NoOp` so form login can maintain login state via web session. Note that **NoOp does not disable all `WebSession` creation**: for example, the default CSRF token repository may still use a session. This is the difference between **not persisting SecurityContext** and **being completely stateless**.

**`{noop}` passwords are strictly for the demo** to make `curl` testing easy; real apps use an appropriate password encoder, real identity store, and HTTPS. HTTP Basic here lets the lesson run without standing up an OAuth Authorization Server/JWK. For a real REST API, if clients are browsers or scope-based authorization is needed, consider Bearer tokens/OAuth2 Resource Server and matching CSRF rules.

### 4.3. Running and observing results

From the `security-chain-split` directory, using JDK 17+ and a Gradle version compatible with the Boot plugin:

```bash
gradle bootRun
```

If the project includes a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Open another terminal and run the independent commands:

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/data

curl -i -u viewer:view http://localhost:8080/api/data

curl -i -u viewer:view http://localhost:8080/admin/report

curl -i -u operator:admin http://localhost:8080/admin/report

curl -i http://localhost:8080/app/home

curl -i http://localhost:8080/login
```

Expected results when the app runs successfully (ignoring headers and version-dependent HTML details):

| Request | Chain | Expected HTTP | Explanation |
| --- | --- | --- | --- |
| `GET /public/ping`, no credentials | `webChain` | 200, body `PONG` | Public |
| `GET /api/data`, no credentials | `apiChain` | 401 + `WWW-Authenticate` | API requires Basic |
| `GET /api/data`, Basic `viewer:view` | `apiChain` | 200, body `API_OK` | Authenticated |
| `GET /admin/report`, Basic `viewer:view` | `adminChain` | 403 | Valid identity, missing `ROLE_ADMIN` |
| `GET /admin/report`, Basic `operator:admin` | `adminChain` | 200, body `ADMIN_OK` | Sufficient role |
| `GET /app/home`, no session | `webChain` | 302 to `/login` | UI uses form login |
| `GET /login` | `webChain` | 200, default HTML login | Login path in the right chain |

Understand the limits: the table above relies on **this exact demo configuration**. 401/403/302 responses in another app may differ if the entry point, access-denied handler, matcher, or authentication mechanism changes. Never deduce HTTP status codes from `@Order` alone.

Try logging in interactively: open `http://localhost:8080/app/home` in a browser, follow the redirect to `/login`, sign in with `viewer/view` or `operator/admin`, and visit again. Logging in via form maintains a browser session for `/app/**`. That **does not mean** you can access `/api/data` or `/admin/report` using that session: those two chains chose `NoOpServerSecurityContextRepository` and disabled form login, so they require credentials in a form each chain accepts.

## 5. Why must /login live inside the UI chain?

Form login is not just **a single HTML page**. It spans all of these paths:

```text
GET /app/home (unauthenticated)
      |
      v
webChain: authentication required
      |
      v
redirect to GET /login
      |
      v
webChain: render form + CSRF token
      |
      v
user POST /login (username, password, CSRF)
      |
      v
webChain: authenticate, save SecurityContext to web session
      |
      v
post-login redirect -> request /app/home with session
```

Because `WebFilterChainProxy` picks only **one chain per request**, both `GET /login` and `POST /login` must be covered by the chain that has `formLogin(...)`. If you attach `securityMatcher("/app/**")` to the web chain and leave `/login` outside the matcher, browsers may see another chain's response or `POST /login` may not be processed by the right filter.

**Wrong** configuration example:

```java
@Bean
@Order(3)
SecurityWebFilterChain brokenWebChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/app/**"))
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .formLogin(withDefaults())
        .build();
}
```

If no other chain serves `/login`, login requests do not hit the proper form-processing filter. Even with a fallback chain, splitting matchers across login and web requires consistent alignment of URLs, CSRF, success/failure handlers, login processing, and the security context repository.

**How to avoid:** For a typical UI, a default `webChain` covering the remainder includes `/app/**`, `/login`, `/logout`, and required static assets. If you need a custom login URL such as `/signin`, ensure the GET page, POST processing endpoint, error URL, and page assets all pass through the right chain; avoid redirect loops (`/signin` requiring login itself).

### What does a public login page mean?

`permitAll()` on `/login` only lets unauthenticated users view the page or submit requests to the endpoint; it **does not skip** username/password or CSRF checks on `POST /login`. The login filter and CSRF filter have separate responsibilities. Do not use Servlet-style `web.ignoring` for WebFlux; to make resources public, use deliberate `permitAll()` rules in the appropriate chain.

## 6. CSRF and sessions: splitting chains does not automatically make things safe

A common mistake is seeing a REST API use JSON or HTTP Basic and disabling `csrf` unconditionally. In Spring Security WebFlux, **CSRF is enabled by default**; WebFlux form login and POST logout rely on this protection.

### Decision table

| Scenario | CSRF analysis |
| --- | --- |
| Browser form login + cookie session | **Keep CSRF** for login, logout, and state-changing requests; forms must submit the token |
| REST API accepting only client-set Bearer tokens in headers, no auto-sent cookies/credentials | Typically does not rely on CSRF under this auth model; disable only after verifying the actual auth interface |
| REST API using HTTP Basic from a browser | Browsers can automatically resend cached Basic credentials; **do not assume it is immune to CSRF** |
| Admin endpoints performing POST/PUT/DELETE | Protect with CSRF if browser credentials can be attached automatically; also enforce roles, auditing, and sensitive-action controls |
| API accepting cookie sessions even when returning JSON | Faces the same CSRF risk as a website; the `/api/**` path gives no automatic protection |

In the runnable example, **CSRF is not disabled** on any chain: only safe GET endpoints exist so focus stays on chain splitting. If you add `POST /api/orders` or `POST /admin/restart`, plain Basic requests without a CSRF token may receive 403. That is an effect of the **CSRF policy**, not selecting the wrong security chain. For a pure Bearer production API, you can disable CSRF **only on the chain verified to have no auto-attached credential risk**, for example:

```java
// Configuration fragment only; DO NOT use if the API accepts Basic
// auto-attached by browsers, cookie sessions, or similar mechanisms.
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"))
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(withDefaults()));
```

The fragment above **is not standalone/immediately runnable** because it needs the OAuth2 Resource Server dependency and a valid `ReactiveJwtDecoder`/issuer/JWK. It shows where to apply the policy once Bearer authentication architecture is in place. Never copy `csrf.disable()` alone while ignoring the credential-type condition.

### Distinguishing web session, security context, and token

- **Web session** may hold the security context, CSRF token, and other data.
- **SecurityContext** represents the request's authentication info; it can be loaded/saved by `ServerSecurityContextRepository`.
- **NoOpServerSecurityContextRepository** prevents saving/reading the security context through this repository; it does not mean no session exists at any layer.
- **CSRF token** is anti-forgery proof, completely distinct from an access token or session cookie.
- **Authentication** (logging in successfully) still requires **Authorization** (having permission for the endpoint).

Maintaining sessions for the UI while requiring per-request credentials for API and admin is this demo's design choice. Real systems also need to review domains, cookies, proxies, CORS, MFA, admin access-source restrictions, auditing, and token/session lifetimes.

## 7. Separating the admin zone properly

In the example, "admin endpoints" are application controllers under `/admin/**`. Controls include:

1. A dedicated matcher so all `/admin/**` requests select `adminChain`.
2. HTTP Basic authentication on the admin chain.
3. Authorization `hasRole("ADMIN")`, checking the actual `ROLE_ADMIN` authority.
4. A `denyAll()` fallback so forgotten URLs are not opened automatically.
5. Tests covering regular accounts, admin accounts, and missing credentials.

**`hasRole("ADMIN")` is not equivalent to checking `username.equals("admin")`.** Spring Security follows a role-prefix convention: users created with `.roles("ADMIN")` receive the `ROLE_ADMIN` authority. If an application stores plain `ADMIN` authorities, use `hasAuthority("ADMIN")` or map authorities properly; never infer permissions from usernames.

**Admin REST endpoints do not automatically become actuator endpoints.** If using Spring Boot Actuator at `/actuator/**`, those have their own routes and registration mechanism; a `/admin/**` matcher **does not** protect `/actuator/**`. If Actuator shares the context/port, define policies for its actual paths (such as EndpointRequest-style matchers via the appropriate Spring Boot API); if using a **separate management port/context**, verify the management context's security rather than assuming the main app's chains run on that port.

Never rely on "renaming the URL to `/secret/admin`" as a security control: hidden paths do not replace roles, strong authentication, network segmentation, or auditing. For highly sensitive actions (deleting data, granting privileges, restarting), add business-level confirmation/authorization; the ADMIN role alone may not suffice.

## 8. Ordering mistakes and scope gaps

### 8.1. Broad chain placed first

```java
// WARNING: wrong example, illustrating the root cause.
@Bean
@Order(1)
SecurityWebFilterChain tooBroad(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .formLogin(withDefaults())
        .build();
}
```

This chain without `securityMatcher` matches all URLs, including `/admin/report` and `/api/data`. When placed first, the admin and API chains never get a chance to be selected, breaking both challenges and admin policy. **Fix:** move the catch-all chain to the end and ensure the fallback chain enforces deny-by-default rules.

### 8.2. API matcher covering admin without the role check

```text
Chain 1: /api/** -> authenticated()
Chain 2: /api/admin/** -> hasRole("ADMIN")
Request: /api/admin/delete
Result: Chain 1 matches first; Chain 2 is NOT evaluated next.
```

**Fix:** place `/api/admin/**` before `/api/**`, or fold the role rule into the API chain via `pathMatchers("/api/admin/**").hasRole("ADMIN")` before `anyExchange()`.

### 8.3. Root path not matching the pattern

With `PathPatternParserServerWebExchangeMatcher("/admin/**")`, do not guess how different versions/routers normalize `/admin`, `/admin/`, matrix/semicolon paths, or encoded paths. Test **both the root URL and subpath URLs**, along with real HTTP methods. In this sample, `/admin` has no handler and hits the `denyAll()` fallback, so there is no unintended grant via pattern mismatch.

If business logic needs to protect both `/admin` **and** `/admin/**` under the same chain, use a combined matcher (such as `OrServerWebExchangeMatcher`) or a version-appropriate matcher rather than relying on an untested single pattern.

### 8.4. Disabling form login on the wrong chain

If you enable `formLogin` only on `webChain` but put `/login` under the `/api/**` matcher, GET/POST login requests may enter the Basic chain, leading to 401/404 or missing form handling. Fix the URL boundaries and ensure the login page, processing URL, and error redirect all flow through a compatible chain.

### 8.5. No chain matches

An application defining only two chains `/admin/**` and `/api/**` leaves `/app/**`, `/login`, and `/public/**` outside those chains. **No match does not automatically produce DENY.** If no other security chain matches, requests may continue to handlers. This is why a final chain with a broad matcher and `anyExchange().denyAll()` is needed for undefined paths.

### 8.6. Separating authentication while accidentally sharing sessions

If the API chain can read `SecurityContext` from a web session, a user logged in via the UI could accidentally be treated as authenticated by the API even when you meant to require separate API credentials. Do not assume simply enabling `httpBasic()` guarantees complete session isolation; check `ServerSecurityContextRepository`, credential extraction, and actual filters. The demo chooses `NoOp` for API/admin while the browser chain uses sessions for forms.

## 9. Testing chain separation with WebTestClient

Create `src/test/java/example/SecurityChainSplitApplicationTests.java` to verify actual behavior instead of just counting beans:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityChainSplitApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsPublic() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void apiRequiresCredentials() {
        client.get().uri("/api/data")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void apiAcceptsValidBasicCredentials() {
        client.get().uri("/api/data")
            .headers(h -> h.setBasicAuth("viewer", "view"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("API_OK");
    }

    @Test
    void adminDeniesUserWithoutAdminRole() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth("viewer", "view"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminAcceptsAdminRole() {
        client.get().uri("/admin/report")
            .headers(h -> h.setBasicAuth("operator", "admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ADMIN_OK");
    }

    @Test
    void browserAppRedirectsToLogin() {
        client.get().uri("/app/home")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void generatedLoginPageIsReachable() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Run:

```bash
gradle test
```

Or use the Wrapper as in the run section. These tests check route behavior **with the real `SecurityWebFilterChain`**. They do not fully test form POST/CSRF (which requires sending a valid CSRF token and verifying cookies/sessions), nor do they replace JWT validation or load tests. Add dedicated tests when replacing HTTP Basic with Bearer.

For chains with sensitive roles, always include at least one **negative** test proving regular accounts are rejected. Testing endpoints only with an admin account will miss a bug where `authenticated()` accidentally lets every logged-in user in.

## 10. Design and implementation checklist

| Check item | Verification question |
| --- | --- |
| URL coverage | Does every endpoint fall into the right chain? Are unrecognized paths denied? |
| Precedence | Do specific chains precede general chains? Are there overlapping matchers to test? |
| Login | Do `GET /login` and `POST /login` flow through the form-login chain? Any redirect loops? |
| Authorization | Does the admin zone require a specific role/authority or merely `authenticated()`? |
| Authentication | Which Basic/Bearer credentials does the API accept? Does UI use form sessions? Any unintended session reuse? |
| CSRF | Are there POST/PUT/DELETE operations with auto-attached browser credentials? |
| Errors | Does missing auth return the right challenge/redirect? Is missing permission blocked? |
| Operations | Do admin endpoints have auditing, HTTPS, rate limiting, secret management, and network access control? |
| Testing | Have public URLs, login-required URLs, admin URLs, unmatched URLs, and wrong-role cases all been tested? |

### Common mistakes

- **Using Servlet classes instead of WebFlux:** `SecurityFilterChain`/`HttpSecurity` are not `SecurityWebFilterChain`/`ServerHttpSecurity`. Avoid mixing packages and threading models.
- **Putting the catch-all at `@Order(1)`:** specific chains will never be selected.
- **Treating `pathMatchers` as chain selection:** it only selects rules inside the already chosen chain.
- **Matching only `/app/**` and forgetting `/login`:** browsers get stuck on the login page or POST.
- **Protecting admin with `authenticated()`:** regular users could also access admin. Use business roles/authorities.
- **Disabling CSRF because a URL starts with `/api/`:** URIs and JSON do not eliminate CSRF risk if browsers auto-send credentials.
- **Assuming NoOp repository eliminates all sessions:** CSRF and other components can still use web sessions.
- **Believing multiple chains merge automatically:** Spring Security uses the **first matching chain**, not a union of permissions from all chains.
- **Testing only HTTP 200:** lacking 401, 403, redirect, and out-of-matcher tests makes bypasses hard to spot.
- **Ignoring Actuator on another port:** a chain for `/admin/**` does not protect Boot's management endpoints.

## 11. Self-check questions

**Question 1.** Why put `@Order(1)` on `/admin/**` and `@Order(3)` on the default chain?  
**Answer:** So the proxy evaluates the admin matcher first. Once the admin chain matches, only its filters/policies apply; the default chain does not run additionally.

**Question 2.** Does `GET /api/data` without credentials in the example redirect to `/login`?  
**Answer:** No. The request enters `apiChain`, which enables HTTP Basic and disables form login; the expected result is a 401 challenge.

**Question 3.** Can someone who logged into `/app/home` automatically access `/admin/report` via the session cookie?  
**Answer:** Not in the demo design. `adminChain` does not use a session repository to load `SecurityContext` and checks the ADMIN role using its own authentication mechanism. Browser login does not substitute for roles either.

**Question 4.** Why must `/login` belong to `webChain`?  
**Answer:** It is the URL that renders and processes the form. The chain with `formLogin` must handle related requests, including POST login and CSRF validation.

**Question 5.** With only two chains `/admin/**` and `/api/**`, is `/app/home` automatically blocked with 403?  
**Answer:** Do not assume so. If no chain matches, requests can pass through to handlers without going through the defined chains' security filters. A clear fallback/defensive chain is required.

**Question 6.** If switching to OAuth2 Resource Server, is enabling `jwt()` on the API chain enough?  
**Answer:** Not yet. You need the dependency, `ReactiveJwtDecoder`/issuer configuration, signature verification, audience checks, and appropriate authority/scope mapping; test 401/403, CSRF, and refresh/revocation per your concrete architecture.

**Conclusion:** Splitting chains in reactive Spring Security means separating **matcher scope**, **authentication mechanisms**, and **authorization policies**. For REST APIs, form-login UIs, and admin endpoints, create clearly ordered `SecurityWebFilterChain` beans, place a **denying fallback chain** last, ensure `/login` lives in the right chain, and test wrong-permission cases. Each request passes through **one selected security chain**.

## References

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `@Order`, `securityMatcher`, and first-match selection.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html) — token mechanics, WebSession, login/logout, state-changing operations.
- [Spring Security — OAuth2 Resource Server for WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html) — Bearer tokens, JWT, and token-based API protection.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — configuring authentication, authorization, CSRF, form login, and context repositories.
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html) — repository that does not persist `SecurityContext`.
- [Spring Boot — WebFlux Security Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html) — how Boot coordinates application security configuration.
