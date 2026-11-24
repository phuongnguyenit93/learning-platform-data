# `csrf()` and Missing, Invalid, or Valid Token Cases

## 1. Context and goals

**Topic:** `csrf()` and missing, invalid, or valid token cases.  
**Knowledge group:** HTTP Testing.  
**Module:** Spring Security - reactive.  
**Example environment:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux, WebTestClient, JUnit 5.

CSRF (*Cross-Site Request Forgery*) is the risk that an untrusted site causes a logged-in user's browser to send a state-changing request to the application. When a browser automatically attaches a session cookie or ambient credentials, the server can mistake a forged request for the user's intent.

The CSRF token mechanism requires state-changing requests to carry a value that browsers do not attach automatically like cookies. In Spring WebFlux, `CsrfWebFilter` validates the token via `ServerCsrfTokenRepository` and `ServerCsrfTokenRequestHandler` before allowing the request to perform an action.

This lesson focuses on **controlled HTTP testing**. A thorough test must verify simultaneously:

1. **HTTP status**: missing/invalid CSRF tokens normally lead to 403; a valid token combined with proper authentication/authorization leads to the business status.
2. **Zero side effects** when a request is blocked: no counter increments, no DB writes, and no events emitted.
3. **Cause isolation**: 401 from missing authentication, 403 from a CSRF token failure, or 403 from missing role/scope can look similar unless the test controls the other conditions.

### After this lesson you will know how to

- Distinguish `ServerHttpSecurity.csrf(...)` in the application from `SecurityMockServerConfigurers.csrf()` in **Spring Security Test**.
- Configure `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` and use `mutateWith(csrf())` the WebFlux way.
- Test GET, POST, PUT, PATCH, and DELETE with missing/invalid/valid tokens.
- Test authentication and authorization independently of CSRF.
- Use the default `WebSessionServerCsrfTokenRepository`, fetch a CSRF token via GET, and submit it back with the **same `SESSION` cookie** to test close to a real browser.
- Understand `XorServerCsrfTokenRequestAttributeHandler` (masked tokens against BREACH), `CookieServerCsrfTokenRepository`, and SPA considerations.
- Test swapping tokens between two sessions, tampered tokens, or tokens sent without a cookie/session.
- Recognize what the test mutator does **not** simulate: cookie flags, SameSite, CORS, login/logout rotation, and proxies.
- Build a Java 17+ WebFlux project with 19 sample HTTP tests, a common-errors checklist, and exercises.

You do not need to disable CSRF to make tests run. Code has been reviewed statically; Gradle execution results can only be confirmed after running in a real project.

## 2. What is CSRF, and why are browser sessions at risk?

Suppose an attacker page creates a form:

~~~html
<form method="post" action="https://bank.example.invalid/transfer">
  <input type="hidden" name="amount" value="500">
  <input type="hidden" name="destination" value="attacker">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

When a user visits this page, the browser may send credential cookies to `bank.example.invalid` depending on cookie/SameSite policy. A server that checks only the session without requiring a CSRF token risks executing an unintended transaction.

CSRF token defense relies on two distinct factors:
- **Session cookie** indicates the login context and can be attached automatically by the browser.
- **CSRF token** must be read by the client from a trusted page/response and explicitly submitted in a form field or header.

A CSRF token is **not a password** and does not authenticate a user on its own. A valid token for an unauthenticated user still does not grant access to an endpoint requiring authentication.

**CORS differs from CSRF:** Browsers may be blocked from reading cross-origin responses while still being able to submit certain form requests. Configuring CORS alone does not replace CSRF protection. SameSite cookies and Origin/Referer checks are defense-in-depth layers; neither should be treated as complete protection on its own across all session flows.

### 2.1. Methods protected by default

| HTTP method | Requires CSRF by default? | Notes |
|---|---|---|
| GET | No | Should be read-only with no side effects |
| HEAD | No | Not used to mutate data |
| OPTIONS | No | CORS/preflight still has its own policy |
| TRACE | Not by default matcher | Typically restrict TRACE at infrastructure level |
| POST | Yes | Create, login, logout, submit |
| PUT | Yes | Replace |
| PATCH | Yes | Partial update |
| DELETE | Yes | Remove |

Spring Security classifies "unsafe" based on HTTP method, **not endpoint name**. For instance, `POST /health` if permitted by routing is still subject to CSRF protection by default; `GET /deleteAccount` does not require CSRF under the default matcher even though the action is unsafe—the flaw is using GET in the design.

### 2.2. HTTP states to distinguish

Suppose endpoint `POST /api/mutations` requires a user with role EDITOR:

| Condition | Expected outcome | Controller invoked? |
|---|---|---|
| EDITOR + no CSRF token | 403 Forbidden | No |
| EDITOR + wrong token | 403 Forbidden | No |
| EDITOR + valid token | 201 Created | Yes |
| No authentication + valid token | 401 Unauthorized | No |
| Authenticated VIEWER + valid token | 403 Forbidden | No |
| Public GET `/health` no auth, no token | 200 OK | GET is read-only |
| Protected GET `/api/mutations` no auth | 401 Unauthorized | No |
| Protected GET `/api/mutations` + EDITOR, no CSRF | 200 OK | GET is read-only |

If both authentication and CSRF are missing, filter ordering may produce 403 first instead of 401. **To test CSRF, always supply valid Authentication**; to test 401, supply valid CSRF and intentionally omit credentials. This prevents tests from passing for the wrong reason.

## 3. Distinguishing the two `csrf()` calls

### 3.1. `ServerHttpSecurity.csrf(...)` — the real application

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .anyExchange().authenticated())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

The code above is a **snippet**, requiring imports and proper authentication config. `ServerHttpSecurity.csrf(...)` configures `CsrfWebFilter`. In Spring Security WebFlux, CSRF is **enabled by default**; declaring it explicitly makes clear what tests are protecting.

The following configuration **bypasses** CSRF rather than creating valid tokens:

~~~java
// Anti-pattern if the goal is testing CSRF:
.csrf(csrf -> csrf.disable())
~~~

A negative POST test missing a token that still returns 201 because CSRF is disabled signals a vulnerability or policy change, not a passing test.

### 3.2. `SecurityMockServerConfigurers.csrf()` — test-only

In `spring-security-test` for reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
    .post().uri("/api/mutations")
    .exchange()
    .expectStatus().isCreated();
~~~

This is a **snippet** that passes only when authentication/authorization, request body, and controller all succeed. `mutateWith(csrf())` adds a **valid CSRF test context** for the request in mock WebFlux. It does not require hardcoding a token, does not authenticate a user for you, and does not grant roles.

**Common wrong import:** `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf` is for Servlet/MockMvc, not `WebTestClient`. Servlet examples may show `csrf().useInvalidToken()`; do not copy that helper verbatim into WebFlux. Reactive negative tests send a wrong raw header alongside the expected token repository/session or simply send a raw invalid header without calling the valid `csrf()` mutator.

### 3.3. `WebTestClient` setup must be right

Spring Security documentation specifies:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

This is a **snippet** used in tests with an injected `ApplicationContext`. `apply(springSecurity())` registers Spring Security reactive test support for the mock server. If the client is wrongly created with `bindToController(...)` without attaching the security chain, negative CSRF tests can pass/fail for the wrong reasons. If using a real HTTP server with `@SpringBootTest(RANDOM_PORT)`, do not assume test mutators behave like a browser; use **tokens/cookies issued by the real server**.

## 4. Token repositories and request handlers

### 4.1. CSRF WebFlux pipeline

~~~text
POST /api/mutations
    |
    v
CsrfWebFilter:
    - does method require CSRF?
    - load/generate expected token from ServerCsrfTokenRepository
    - resolve token sent by client via header/form
    - compare tokens via request handler
    |
    +--- missing/mismatch -> 403 -> business logic not called
    |
    +--- match -> Authentication/Authorization
                        |
                        +--- no user -> 401
                        +--- insufficient role -> 403
                        +--- valid -> controller/service -> 201
~~~

The default `WebSessionServerCsrfTokenRepository` stores the expected token in `WebSession`. When the session expires or is rotated/invalidated, the old token normally stops working. A CSRF token obtained from session A cannot be used with session B.

### 4.2. Deferred token and exchange attribute

`CsrfWebFilter` puts a `Mono<CsrfToken>` into `ServerWebExchange` under key:

~~~java
CsrfToken.class.getName()
~~~

Tokens may be generated/saved **lazily**, meaning if you open a GET endpoint without rendering/subscribing to the token, there may not yet be a `SESSION` cookie and expected token for the next POST. That is why the demo adds a `GET /csrf-token` endpoint that subscribes to the `Mono` and returns the exposed token.

### 4.3. XOR/BREACH masking

Since Spring Security 6.0, WebFlux's default `XorServerCsrfTokenRequestAttributeHandler` mitigates BREACH risk when tokens are rendered into compressed responses. It exposes a **masked token** with randomness; when a request sends the token back, the handler unmasks it and compares against the expected secret in the repository.

Implications for tests:

- Never hardcode a global token.
- Never assert that exposed token strings are equal across multiple GETs.
- Send back **the exact token value returned by GET** with the **exact same session**.
- A random raw header like `X-CSRF-TOKEN: wrong` does not become valid just because the header is present.
- If swapping the request handler/repository, test the masked-vs-raw protocol explicitly.
- Never disable XOR/masking just because writing negative tests feels inconvenient.

### 4.4. `CookieServerCsrfTokenRepository` for SPAs

Spring WebFlux also offers `CookieServerCsrfTokenRepository`. Defaults are cookie name `XSRF-TOKEN`, header name `X-XSRF-TOKEN`, and form parameter `_csrf`. When a real frontend needs JavaScript to read the CSRF cookie, snippet:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

This is a snippet and does **not** mean every cookie should disable `HttpOnly`. Login/session cookies still require appropriate `HttpOnly`, `Secure`, and `SameSite`.

**Important:** In Spring Security 6.x, the cookie may store the **raw token**, while the default XOR request handler expects a masked token in the header/form. An SPA that copies the raw cookie straight into the header may require a custom `ServerCsrfTokenRequestHandler`. Do not assume `withHttpOnlyFalse()` alone makes every AJAX setup work; test the real browser flow and CSRF token refreshes across login/logout.

## 5. Java 17+ and Gradle WebFlux demo

Create a Spring Initializr project (Gradle Groovy, Java 17+, Boot 3.5.x, Reactive Web, Security, Test). The `dependencies` block in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

This is only the **dependencies block**; keep the plugins, Java toolchain, repositories, and Gradle wrapper generated by Initializr. Do not add `spring-boot-starter-web` when WebFlux is needed inbound; having both MVC and WebFlux in Boot 3.x can cause Servlet to take precedence.

Structure:

~~~text
src/main/java/demo/csrf/
  CsrfLearningApplication.java
  SecurityConfig.java
  MutationStore.java
  MutationController.java
  CsrfTokenController.java
src/test/java/demo/csrf/
  CsrfHttpTests.java
~~~

### 5.1. `CsrfLearningApplication.java`

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfLearningApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfLearningApplication.class, args);
    }
}
~~~

### 5.2. `SecurityConfig.java`

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails editor = User.withUsername("learner")
            .password(encoder.encode("study-pass"))
            .roles("EDITOR")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(editor, viewer);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/csrf-token").permitAll()
                .pathMatchers("/api/mutations", "/api/mutations/**")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Explanation:
- `httpBasic` is the test/non-browser demo mechanism for valid credentials; production browsers typically use session cookies/form login or a dedicated token workflow.
- Passwords are hashed using the delegating encoder, avoiding `{noop}` in the test application.
- Role `EDITOR` requires `ROLE_EDITOR`, which `VIEWER` lacks.
- CSRF is explicitly enabled, protecting POST/PUT/PATCH/DELETE.
- `GET /csrf-token` is public solely to issue a session-bound CSRF token; **it grants no authentication**. If production exposes a similar endpoint, enforce proper CORS, caching, `SameSite`, and privacy policies.
- Never disable CSRF or `permitAll` mutation routes.
- Demo HTTP Basic credentials are for localhost only; production must use TLS and secret management.

### 5.3. `MutationStore.java`: asserting zero side effects

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MutationStore {

    public record Receipt(String operation, int totalMutations) {
    }

    private final AtomicInteger counter = new AtomicInteger();

    public int count() {
        return counter.get();
    }

    public void resetForTest() {
        counter.set(0);
    }

    public Mono<Receipt> mutate(String operation) {
        return Mono.fromSupplier(() ->
            new Receipt(operation, counter.incrementAndGet()));
    }
}
~~~

The store is simply an in-memory counter standing in for a database. When security filters reject a request, the business `Mono` must not be subscribed to, so the counter must stay at **0**. If production uses a DB, event bus, or email sender, add assertions ensuring transactional/event side effects truly never happen.

### 5.4. `MutationController.java`: HTTP methods to test

~~~java
package demo.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MutationController {

    public record MutationCommand(String value) {
    }

    public record CounterView(int mutations) {
    }

    private final MutationStore store;

    public MutationController(MutationStore store) {
        this.store = store;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/mutations")
    public Mono<CounterView> list() {
        return Mono.just(new CounterView(store.count()));
    }

    @PostMapping("/api/mutations")
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<MutationStore.Receipt> create(
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("POST"));
    }

    @PutMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> put(
            @PathVariable int id,
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("PUT"));
    }

    @PatchMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> patch(
            @PathVariable int id,
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("PATCH"));
    }

    @DeleteMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> delete(
            @PathVariable int id) {
        return store.mutate("DELETE");
    }
}
~~~

Path variables and bodies in the demo are accepted to model HTTP without storing real records. Real products need validation/ACLs and business error handling. `GET /api/mutations` only reads the counter; unsafe methods increment the counter exactly once when allowed.

### 5.5. `CsrfTokenController.java`: fetching a real token from `WebSession`

~~~java
package demo.csrf;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfTokenController {

    public record CsrfResponse(String headerName, String token) {
    }

    @GetMapping("/csrf-token")
    public Mono<CsrfResponse> issue(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not active"));
        }

        return token.map(t ->
            new CsrfResponse(t.getHeaderName(), t.getToken()));
    }
}
~~~

Spring Security WebFlux places the token `Mono` in the request attribute. Returning `Mono<CsrfResponse>` from the controller triggers loading/subscription during the response, allowing the session repository to generate/save the CSRF token. The default `WebSessionServerCsrfTokenRepository` saves the expected token in `WebSession`, and the client receives a `SESSION` cookie when the session starts.

In Spring 6.x, `t.getToken()` has passed through the request handler and may be a **masked token**. Send back that exact exposed value via header `t.getHeaderName()` with the **same session**.

**Never** place CSRF tokens in shared public caches or log them, and never allow hostile origins to CORS-read a credentialed `/csrf-token`. While not a bearer credential by itself, leaking tokens can weaken CSRF defense if an attacker also controls session context.

## 6. `WebTestClient` tests: 19 clear scenarios

Uses `@SpringBootTest(webEnvironment=MOCK)` and `WebTestClient` bound to `ApplicationContext` with `springSecurity()`. The `csrf()` mutator is used for positive paths; raw headers/sessions are used for negative and browser-like cases.

File `src/test/java/demo/csrf/CsrfHttpTests.java`:

~~~java
package demo.csrf;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.MOCK)
class CsrfHttpTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MutationStore store;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        store.resetForTest();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private void editor(HttpHeaders headers) {
        headers.setBasicAuth("learner", "study-pass");
    }

    private void viewer(HttpHeaders headers) {
        headers.setBasicAuth("viewer", "viewer-pass");
    }

    private WebTestClient.ResponseSpec post(
            WebTestClient web, boolean withAuth) {

        var request = web.post()
            .uri("/api/mutations")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"));

        if (withAuth) {
            request.headers(this::editor);
        }
        return request.exchange();
    }

    @Test
    void healthGetDoesNotRequireCsrf() {
        client.get().uri("/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
        assertEquals(0, store.count());
    }

    @Test
    void authenticatedGetWorksWithoutCsrf() {
        client.get().uri("/api/mutations")
            .headers(this::editor)
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.mutations").isEqualTo(0);
        assertEquals(0, store.count());
    }

    @Test
    void unauthenticatedGetIsUnauthorized() {
        client.get().uri("/api/mutations")
            .exchange().expectStatus().isUnauthorized();
        assertEquals(0, store.count());
    }

    @Test
    void postMissingCsrfIsForbidden() {
        post(client, true)
            .expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void postInvalidCsrfHeaderIsForbidden() {
        client.post().uri("/api/mutations")
            .headers(this::editor)
            .header("X-CSRF-TOKEN", "not-valid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void postValidCsrfIsCreated() {
        post(client.mutateWith(csrf()), true)
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("POST")
            .jsonPath("$.totalMutations").isEqualTo(1);
        assertEquals(1, store.count());
    }

    @Test
    void csrfDoesNotReplaceAuthentication() {
        post(client.mutateWith(csrf()), false)
            .expectStatus().isUnauthorized();
        assertEquals(0, store.count());
    }

    @Test
    void csrfDoesNotReplaceAuthorization() {
        client.mutateWith(csrf())
            .post().uri("/api/mutations")
            .headers(this::viewer)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void putMissingCsrfIsForbidden() {
        client.put().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void patchMissingCsrfIsForbidden() {
        client.patch().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void deleteMissingCsrfIsForbidden() {
        client.delete().uri("/api/mutations/1")
            .headers(this::editor)
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void putValidCsrfWorks() {
        client.mutateWith(csrf())
            .put().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    @Test
    void patchValidCsrfWorks() {
        client.mutateWith(csrf())
            .patch().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    @Test
    void deleteValidCsrfWorks() {
        client.mutateWith(csrf())
            .delete().uri("/api/mutations/1")
            .headers(this::editor)
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    private record Issued(
            String session, CsrfTokenController.CsrfResponse token) {
    }

    private Issued issue() {
        EntityExchangeResult<CsrfTokenController.CsrfResponse> reply =
            client.get().uri("/csrf-token")
                .exchange().expectStatus().isOk()
                .expectBody(CsrfTokenController.CsrfResponse.class)
                .returnResult();

        ResponseCookie cookie = reply.getResponseCookies()
            .getFirst("SESSION");

        assertNotNull(cookie);
        assertNotNull(reply.getResponseBody());
        assertNotNull(reply.getResponseBody().token());
        assertNotNull(reply.getResponseBody().headerName());

        return new Issued(
            cookie.getValue(), reply.getResponseBody());
    }

    private WebTestClient.ResponseSpec postWithSession(
            String cookie, String header, String token) {

        return client.post().uri("/api/mutations")
            .cookie("SESSION", cookie)
            .header(header, token)
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange();
    }

    @Test
    void issuedTokenAndMatchingSessionAreAccepted() {
        Issued issued = issue();

        postWithSession(
            issued.session(),
            issued.token().headerName(),
            issued.token().token())
            .expectStatus().isCreated();

        assertEquals(1, store.count());
    }

    @Test
    void missingTokenWithExistingSessionIsForbidden() {
        Issued issued = issue();

        client.post().uri("/api/mutations")
            .cookie("SESSION", issued.session())
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void tamperedTokenWithExistingSessionIsForbidden() {
        Issued issued = issue();

        postWithSession(
            issued.session(),
            issued.token().headerName(),
            issued.token().token() + "-tampered")
            .expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void tokenOfSessionADoesNotMatchSessionB() {
        Issued a = issue();
        Issued b = issue();

        assertNotEquals(a.session(), b.session());

        postWithSession(
            b.session(),
            a.token().headerName(),
            a.token().token())
            .expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void issuedTokenWithoutSessionIsForbidden() {
        Issued issued = issue();

        client.post().uri("/api/mutations")
            .headers(this::editor)
            .header(
                issued.token().headerName(),
                issued.token().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();

        assertEquals(0, store.count());
    }
}
~~~

### 6.1. Why are there 19 test methods?

**Safe methods + authentication group (3):** public GET needs no token; protected GET with authentication needs no token; protected GET missing auth returns 401.

**POST missing/invalid/valid group (5):** Basic EDITOR without CSRF → 403; wrong raw header → 403; `mutateWith(csrf())` → 201; valid CSRF without authentication → 401; valid CSRF with VIEWER role → 403.

**PUT/PATCH/DELETE group (6):** all three methods missing tokens return 403 and do not mutate; with valid CSRF they return 200 and increment the counter once.

**Repository/session group (5):** GET fetches expected token and `SESSION`; POST with same valid session → 201; missing token → 403; tampered token → 403; token from session A with cookie B → 403; token present without session cookie → 403.

Total **3 + 5 + 6 + 5 = 19**. Every negative test asserts `store.count()==0`, and every successful mutation asserts `store.count()==1`.

**The `csrf()` test helper does not prove browser behavior:** It supplies a valid token via a test-only hook. It is `issue()` and `postWithSession()` that show the session-backed expected token and exposed header actually align. Even then, mock `WebTestClient` does not enforce browser `SameSite`/CORS/cookie policies like Chrome/Firefox; run browser E2E tests when integrating a frontend.

### 6.2. Limitations of the shared store

`MutationStore` is a singleton in the Spring context, and the test resets `AtomicInteger` before each test. JUnit 5 does not run in parallel by default unless configured. If CI enables parallel test execution, isolate the context/store per test or run this suite sequentially to avoid races and false failures.

### 6.3. Do not use `mockUser` to "fake" everything

Reactive Spring Security Test also offers `mockUser()`:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("learner").roles("EDITOR"))
    .mutateWith(csrf())
    .post().uri("/api/mutations")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("value", "demo"))
    .exchange().expectStatus().isCreated();
~~~

This is a snippet inside a test class that already has the imports. `mockUser()` mocks Authentication; `csrf()` mocks a valid token. They are independent:
- `mockUser()` does not automatically supply a CSRF token.
- `csrf()` does not create a user or role.
- Testing solely with both mock mutators can miss bugs in password encoders, session cookies, or browser integration.
- This lab also uses real HTTP Basic in the mock server and GET CSRF/session to raise confidence.

## 7. Running the project and quick tests

In the project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Public health:

~~~bash
curl -i http://localhost:8080/health
~~~

Expect HTTP 200, body `ok`. On the protected endpoint:

~~~bash
curl -i \
  -u learner:study-pass \
  -H "Content-Type: application/json" \
  -d '{"value":"demo"}' \
  http://localhost:8080/api/mutations
~~~

Expect **403 Forbidden** because there is no CSRF token, even with valid Basic credentials. Use demo credentials only on localhost; HTTP Basic on public networks must go over TLS with secret management.

To succeed with real CSRF:
1. GET `/csrf-token`, save the JSON `token`/`headerName`.
2. Save the `SESSION` cookie from that response.
3. POST `/api/mutations` with the **same cookie**, `headerName=token` value, and valid Basic credentials.
4. Expect 201, counter incremented once.

Run tests:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

**Note:** Tests are expected to PASS on the described stack, though the code has only been statically checked for structure and APIs; this lesson does not claim Gradle was executed.

## 8. Why do missing/invalid token tests sometimes return unexpected statuses?

### 8.1. 401 vs 403 due to filter ordering

If a POST omits **both Authorization and CSRF**, `CsrfWebFilter` may reject it before Basic authentication runs. The response is then 403. That does not prove the endpoint requires no authentication.

How to isolate factors in tests:
- To test CSRF, send valid Basic EDITOR credentials and only omit/corrupt the token.
- To test 401, supply a valid token via `mutateWith(csrf())` and omit Authorization.
- To test roles, send valid Basic VIEWER credentials and a valid CSRF token.
- To test success, send both Basic EDITOR + valid CSRF.

### 8.2. Mock client bypassing the right security chain

Mistake:

~~~java
// Binds only the controller without integrating security:
WebTestClient.bindToController(new MutationController(store))
    .build();
~~~

Without `SecurityWebFilterChain`, a POST request can pass even without CSRF. Never write that test and conclude the app is protected. This lesson uses `bindToApplicationContext(context).apply(springSecurity())` to attach real WebFlux security.

### 8.3. Missing and wrong tokens both give 403 for different reasons

CSRF missing: the request has no header/form token.  
CSRF wrong: a token is present but does not match the expected token or fails XOR decoding.  
Both usually return 403, yet the security policy must block both. Write separate tests instead of asserting only one case.

### 8.4. Missing session cookie or token from another session

In a `WebSession` repository, a token may have been issued under session A. If a new request omits `SESSION` or sends session B, the server loads a different expected token; token A is invalid. Positive-path tests must capture the cookie from GET and send it back accurately.

### 8.5. Login/logout and token rotation

Spring Security login/logout can regenerate/clear the token repository or rotate session state. If the frontend keeps using a pre-login/pre-logout token, unsafe requests can return 403. Tests should include:
- Login POST must carry a CSRF token under cookie-based policies.
- After authentication succeeds, fetch a fresh token before mutating.
- Logout POST with missing/wrong CSRF is rejected.
- Logout/expiry renders old tokens unusable once the session is invalidated.
- Multi-tab and session timeout flows handle token reload UX properly.
- Never disable CSRF on login/logout just because the frontend hit a 403.

### 8.6. Masked tokens and SPA cookies

With Spring Security 6.x's default `XorServerCsrfTokenRequestAttributeHandler`, the exposed token changes due to masking; if an SPA reads the raw `XSRF-TOKEN` cookie and sends it straight back in `X-XSRF-TOKEN`, the request handler must support the matching representation. Any custom handler for raw headers vs masked forms must be tested carefully against your exact version. Never confuse Servlet's `CsrfTokenRequestHandler` with reactive `ServerCsrfTokenRequestHandler`.

## 9. Forms and JSON: two ways to send valid tokens

HTML form:

~~~html
<form action="/profile" method="post">
  <input type="text" name="displayName" value="Alice">
  <input type="hidden" name="_csrf"
         value="<server-exposed-token-for-current-session>">
  <button type="submit">Save</button>
</form>
~~~

`_csrf` is only valid when rendered dynamically into the response (e.g., Thymeleaf/Spring Security form integration); a hardcoded literal like above is not for production.

JSON/AJAX:

~~~http
POST /api/mutations HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <token-from-trusted-response>
Cookie: SESSION=<same-session>

{"value":"demo"}
~~~

For JSON, place the token in a header. Never pass the token in URL query parameters because URLs leak into logs, traces, caches, analytics, and browser history. For multipart forms, reading the body to extract the token carries resource-consumption trade-offs; WebFlux provides `tokenFromMultipartDataEnabled(true)`—do not enable it unless needed.

**Actual header name:** Session repositories normally return `X-CSRF-TOKEN`; `CookieServerCsrfTokenRepository` normally uses `X-XSRF-TOKEN`. Use `CsrfToken.getHeaderName()` or the real contract instead of guessing.

## 10. When might CSRF not be needed?

CSRF is primarily a risk when browsers **automatically send** credentials such as session cookies. If an API truly accepts only Bearer tokens placed manually in the `Authorization` header, never stores tokens in cookies, and browsers never auto-attach credentials, the CSRF threat model differs. However:
- A JWT stored in a cookie still carries CSRF risk.
- HTTP Basic in browsers can act as an ambient credential.
- If cookie/session login coexists in the same app, carefully separate `SecurityWebFilterChain`s for API vs browser routes.
- Disabling CSRF across the entire app because of one machine API is overly broad.
- CORS, XSS, access token theft, same-origin protections, and authorization must be analyzed separately.

If security architecture determines CSRF is unnecessary on a Bearer-only endpoint, scope the matcher/chain carefully after review while keeping negative tests for authentication/audience/scope and preserving CSRF protection on cookie routes. Never make that decision mechanically based on labels like "REST" or "stateless".

## 11. Troubleshooting

| Symptom | Possible cause | Fix |
|---|---|---|
| POST missing CSRF still returns 201 | `csrf.disable()`, wrong chain, test lacks security wiring | Negative test + `bindToApplicationContext` + `springSecurity` |
| POST with valid `csrf()` still returns 403 | Missing role, wrong route, bad test setup | Isolate authn/authorization; check `SecurityWebFilterChain` |
| POST missing both auth and token returns 403 | CSRF filter blocks before authn | Test authn with valid CSRF |
| Protected GET returns 401 without CSRF | Authentication required, not CSRF | Send Basic/`mockUser` for GET |
| POST with `X-CSRF-TOKEN: abc` still returns 403 | Header value mismatches repo/handler | Send the valid token and matching session |
| CSRF token on GET lacks `SESSION` cookie | Token `Mono` was not subscribed/saved | Expose token and inspect `WebSession` |
| Token A with `SESSION` B returns 403 | Expected token differs | Working protection; test mismatch |
| Tokens differ between two GETs | Randomness in XOR/BREACH masked token | Do not assert string equality |
| SPA raw cookie rejected in header | XOR handler expects masked token | Design appropriate custom reactive handler |
| Login/logout causes POST 403 | Old token cleared/rotated | Fetch fresh token |
| POST after session timeout rejected | Expected token/session expired | Refresh token/login, handle idempotency |
| Tests with `mockUser` pass, prod Basic fails | `MockUser` bypasses credential verification | Add real-auth tests |
| Test GET deletes data without CSRF | Wrong HTTP method | Use POST/DELETE for mutations |
| Wrong token yet counter increments | Side effect ran before security or fire-and-forget | Place action after authz; avoid manual `subscribe` |
| Flaky CI tests | Shared counter with parallel tests | Test isolation, reset, and serialize |
| CORS failure mistaken for CSRF | Wrong browser preflight/cookie flags | Verify CORS/SameSite/credentials separately |
| CSRF token leaked in query/logs | Token sent over wrong channel | Use header/form body, redact |
| `WebTestClient` `csrf()` copied from Servlet | Wrong import | Use `SecurityMockServerConfigurers.csrf` |
| New route does not require CSRF | Wrong multi-chain matcher/ordering | Test each path and HTTP verb |
| Authenticated VIEWER + valid CSRF gets 403 | Missing EDITOR role | Expected authorization layer behavior |

## 12. Exercises with answers

### Exercise 1 — How do the two `csrf()` calls differ?
**Answer:** `ServerHttpSecurity.csrf(...)` enables/configures the protective filter in the application; `SecurityMockServerConfigurers.csrf()` provides a valid CSRF test context for `WebTestClient`.

### Exercise 2 — POST with valid Basic but no CSRF?
**Answer:** Normally 403, and the service does not run. Valid authentication does not substitute for a CSRF token.

### Exercise 3 — POST with an invalid header?
**Answer:** 403. Merely having the header is not enough; it must match the expected token per repository and handler.

### Exercise 4 — POST with valid `csrf()` but no auth?
**Answer:** Normally 401 in the Basic auth demo. A CSRF token does not establish identity.

### Exercise 5 — POST with valid `csrf` but VIEWER role?
**Answer:** 403 due to authorization. Assert both status and zero side effects.

### Exercise 6 — Protected GET without CSRF?
**Answer:** Not required by default because GET is a safe method, though Authentication/Role is still required.

### Exercise 7 — Does DELETE require CSRF?
**Answer:** Yes under the default CSRF matcher, just like POST/PUT/PATCH. Do not assume DELETE is inherently safe just from REST semantics.

### Exercise 8 — Why assert `counter==0` after 403?
**Answer:** To guarantee the request triggered no business side effects, not just that it returned a status code.

### Exercise 9 — Session A's token sent with session B's cookie?
**Answer:** With a `WebSession` repository, session B's expected token differs from A's, so it must be rejected.

### Exercise 10 — What if there is no `SESSION` cookie?
**Answer:** With session-stored tokens, the request cannot load the prior session's expected token, so the old token is rejected.

### Exercise 11 — Why can exposed CSRF tokens change across GETs?
**Answer:** XOR masking adds randomness to reduce BREACH risk; never compare masked strings as fixed constants.

### Exercise 12 — Does `CookieServerCsrfTokenRepository` mean any `X-XSRF-TOKEN` request automatically passes?
**Answer:** No. The header must hold the valid token, and the request handler must match raw/masked representations, session/cookie policy, and permissions.

### Exercise 13 — Can CORS replace CSRF?
**Answer:** No; CORS restricts browsers from reading cross-origin responses, rather than verifying intent on unsafe requests.

### Exercise 14 — Can an app storing JWTs in cookies disable CSRF because it is "stateless"?
**Answer:** Not automatically. Cookies are still auto-sent by browsers; CSRF must be evaluated per threat model.

### Exercise 15 — Does `@WithMockUser` automatically add CSRF?
**Answer:** No. Mock authentication and the CSRF test mutator are separate mechanisms.

### Exercise 16 — Do login and logout need CSRF?
**Answer:** Yes in browser session flows. Login/logout POSTs require CSRF, and tokens normally need refreshing after authentication/session changes.

### Exercise 17 — When should real browser E2E be used?
**Answer:** When verifying `SameSite`/`Secure`/`HttpOnly`, CORS, cookie domain/path, SPA token refresh, and behavior behind a real reverse proxy.

### Exercise 18 — Should a 403 test be fixed with `csrf.disable()`?
**Answer:** Not if the goal is verifying CSRF. That removes the security control and creates a false positive.

## 13. Project QA checklist

- [ ] Tests use WebFlux `WebTestClient`, not Servlet MockMvc `csrf()` imports.
- [ ] In-memory client binds `ApplicationContext` and calls `apply(springSecurity())`.
- [ ] CSRF filter remains enabled, never disabled to make tests pass.
- [ ] Read-only GET without a token still works when authenticated.
- [ ] POST missing token + EDITOR -> 403, counter=0.
- [ ] POST wrong token + EDITOR -> 403, counter=0.
- [ ] POST `mutateWith(csrf())` + EDITOR -> 201, counter=1.
- [ ] Valid token + no auth -> 401.
- [ ] Valid token + VIEWER -> 403.
- [ ] PUT/PATCH/DELETE missing token -> 403.
- [ ] PUT/PATCH/DELETE valid token -> 200 and proper side effect.
- [ ] Tests cover GET `/csrf-token` returning `SESSION` + token, and POST with same session succeeding.
- [ ] Tests cover tampered tokens, cross-session tokens, and missing cookies/sessions.
- [ ] Default XOR handler and `WebSession` repository behavior are verified.
- [ ] If SPA cookie repository is used, raw-vs-masked token handling is tested.
- [ ] Login/logout/session expiry and CSRF refresh are tested when relevant.
- [ ] CORS/`SameSite`/`HttpOnly`/`Secure` are not conflated with mock `WebTestClient`.
- [ ] HTTP 401 is distinct from 403, and CSRF rejection is distinct from role rejection.
- [ ] Never log CSRF tokens, `SESSION` cookies, `Authorization`, or PII.
- [ ] Never execute state-changing actions via GET.
- [ ] No async/fire-and-forget business side effects execute after rejection.
- [ ] Test and production security chains do not diverge unintentionally.
- [ ] Build/test on Java 17+ with compatible Boot/Security versions.

## 14. Summary

~~~text
APPLICATION:
  ServerHttpSecurity.csrf(...) -> enables CSRF checking
  CsrfWebFilter                -> rejects missing/wrong token
  WebSessionServerCsrfTokenRepository -> expected token per SESSION
  XorServerCsrfTokenRequestAttributeHandler -> masked value

WEBFLUX TEST:
  WebTestClient.bindToApplicationContext(ctx)
    .apply(springSecurity()).configureClient().build()

  POST + EDITOR + no csrf             -> 403, no side effect
  POST + EDITOR + wrong csrf          -> 403, no side effect
  POST + EDITOR + mutateWith(csrf())  -> 201, side effect once
  POST + valid csrf + no auth         -> 401
  POST + valid csrf + VIEWER          -> 403

REAL SESSION TEST:
  GET /csrf-token -> response token + SESSION cookie
  POST token + matching SESSION -> 201
  POST tampered/missing token -> 403
  POST token(A) + SESSION(B) -> 403
  POST token(A) without SESSION -> 403
~~~

**Takeaway:** `csrf()` in Spring Security Reactive Test supplies a **valid CSRF token for tests**, rather than disabling protection. A trustworthy test suite covers **missing, invalid, and valid** cases, isolates Authentication/Authorization, guarantees **zero side effects on 403**, and verifies a real flow using a **CSRF token paired with a session cookie**.

## 15. References

- [Spring Security 6.5 — Testing with CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [SecurityMockServerConfigurers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [CsrfWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
