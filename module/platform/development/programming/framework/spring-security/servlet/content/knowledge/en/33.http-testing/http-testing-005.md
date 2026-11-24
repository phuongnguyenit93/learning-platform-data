# HTTP Testing: CSRF, Invalid Tokens, and State-Changing Operations in Spring Security Servlet

## 1. The Problem to Test

A Spring MVC API can authenticate users properly and enforce roles completely, yet still face **Cross-Site Request Forgery (CSRF)** risks if a browser automatically attaches a session cookie or another credential to a request triggered by a malicious site. For operations that create, update, or delete data, an HTTP-valid request does not prove the user **intentionally** initiated that operation.

When CSRF protection is enabled in Spring Security Servlet, requests using HTTP methods considered **unsafe** typically must supply a valid CSRF token. In HTTP testing, distinguish at a minimum:

1. Do data-reading GET requests require a CSRF token?
2. How are POST, PUT, PATCH, and DELETE without a CSRF token blocked?
3. Is a present-but-**invalid** CSRF token rejected just like a missing token?
4. With a valid CSRF token yet **not logged in**, can data be modified?
5. With a valid CSRF token, logged in, yet **lacking authority**, what happens?
6. When rejected, do the controller/service genuinely **produce zero side effects**?
7. If an API uses `Authorization: Bearer` explicitly added by JavaScript, does the CSRF policy differ from a session/cookie-based API?

This lesson focuses on **Servlet HTTP testing with MockMvc and spring-security-test** (Spring Boot 3.x, Spring Security 6.x, Java 17+). The example builds a small REST API with `@SpringBootTest`, `@AutoConfigureMockMvc`, a real `SecurityFilterChain`, demo HTTP Basic, and an in-memory store to verify that rejected requests never mutate state.

**Distinguish upfront:** a CSRF token is not a session ID, OAuth 2.0 access token, JWT, ID token, or password. It is a dedicated value confirming that a state-changing request originated from the properly protected browser/session context as designed. A valid token does not replace authentication or authorization.

## 2. Why Does CSRF Exist Even When Login Is Already Implemented?

A typical scenario:

~~~text
1. User logs in at https://bank.example.org.
2. Browser holds a session cookie belonging to bank.example.org.
3. User opens a page from another domain controlled by an attacker.
4. The malicious page causes the browser to send a POST to bank.example.org/transfer.
5. Depending on cookie policy, the browser may automatically send the session cookie along.
6. If the server only checks cookie -> authenticated, the request may execute.
7. If the server also requires a valid CSRF token, the attacker normally
   cannot forge the token bound to the protected session.
~~~

In real environments, cookie `SameSite` attributes, CORS, form design, and browser restrictions alter exploitability. However, **SameSite/CORS are not a default replacement for CSRF protection**. `SameSite` helps reduce risk, yet not every model is protected by a single cookie attribute alone; CORS primarily governs cross-origin reads/access from JavaScript rather than blocking every browser-initiated request.

For session-based login, cookies are **credentials automatically sent by the browser**. That is the source of CSRF risk. HTTP Basic requires similar evaluation because browsers may remember credentials and automatically attach them on subsequent calls to the origin.

Conversely, a completely stateless Resource Server API that only accepts access tokens from an `Authorization` header **explicitly** attached by the client application and does not rely on auto-sent cookies has a different CSRF threat model. Still, never conclude "REST APIs are always exempt from CSRF" or "using JWT automatically prevents CSRF". A JWT stored in an auto-sent cookie still creates CSRF risk.

## 3. Safe HTTP Methods and State-Changing Operations

Spring Security has a default CSRF matcher based on HTTP method. By common convention, **GET, HEAD, TRACE, OPTIONS** are treated as methods not needing a CSRF token, while other methods must be protected. Specifically in a REST API:

| Method | Standard purpose | Default CSRF | Example |
| --- | --- | --- | --- |
| GET | Read data | Typically not required | GET /api/items/5 |
| HEAD | Read headers | Typically not required | HEAD /api/items/5 |
| OPTIONS | Probe options/preflight | Typically not required | OPTIONS /api/items |
| POST | Create or trigger action | Valid token required | POST /api/items |
| PUT | Replace resource | Valid token required | PUT /api/items/5 |
| PATCH | Partial update | Valid token required | PATCH /api/items/5 |
| DELETE | Delete resource | Valid token required | DELETE /api/items/5 |

**Do not use the method name as sole proof an endpoint is safe.** By HTTP design, GET and HEAD must not perform business state-changing side effects. If `GET /delete-account` actually deletes an account, the default CSRF matcher may not block it; the bug to fix is **designing an endpoint with side effects on GET**.

TRACE may be classified as safe in default CSRF logic yet blocked by `HttpFirewall` or the servlet container for other reasons. Do not enable TRACE merely to test CSRF, and never claim every TRACE request is accepted by Spring Security.

Having a valid CSRF token on a POST does not by itself make the request permitted. That method must still pass authentication, authorization, input validation, and business invariants.

## 4. Where CsrfFilter Sits in Spring Security

Overview of the flow:

~~~text
Client HTTP request
     |
     v
Servlet container
     |
     v
DelegatingFilterProxy("springSecurityFilterChain")
     |
     v
FilterChainProxy -> SecurityFilterChain
     |
     +--> Filter setting up SecurityContext
     |
     +--> CsrfFilter
     |        |
     |        +--> Checks if method requires CSRF
     |        |
     |        +--> Fetches expected token from CsrfTokenRepository
     |        |
     |        +--> Reads submitted token from header/parameter
     |        |
     |        +--> Validates match
     |                 |
     |                 +--> missing/invalid: AccessDenied, usually HTTP 403
     |                 +--> valid: passes request down the filter chain
     |
     +--> Other Authentication / Authorization filters
     |
     v
DispatcherServlet -> Controller -> Service
~~~

The diagram explains functionality and does not list every filter. The relative order of authentication and exception-handling components depends on version/configuration. **`CsrfFilter` can reject a request before authorization runs**, so for a POST missing both login and a CSRF token, the response can be **403** from CSRF rather than 401 as you might guess from authentication.

Key concepts:

- **CsrfTokenRepository:** mechanism managing the expected token bound to the request/session/configured store. On the Servlet stack, a common implementation is `HttpSessionCsrfTokenRepository`; `CookieCsrfTokenRepository` serves cookie-based models when configured properly.
- **CsrfTokenRequestHandler:** how the app exposes the CSRF token as a request attribute and resolves the submitted token from the HTTP request. Spring Security 6 handles deferred tokens and token masking mechanisms suited to mitigate risks like BREACH in certain setups.
- **CsrfFilter:** decides whether a request needs a token and compares the expected token against the submitted value.
- **AccessDeniedHandler:** typically returns HTTP 403 on missing/invalid CSRF tokens; custom configurations may produce different responses.
- **SecurityContext / AuthorizationFilter:** determines identity and permissions after the request passes the relevant preceding security checks.

When a request is rejected at `CsrfFilter`, the controller should not run and data must not be modified. That is why tests assert not only HTTP 403, but also **zero side effects**.

## 5. Distinguishing Missing Tokens, Invalid Tokens, Valid Tokens, and Access Permissions

An important matrix for `POST /api/items`. Suppose the endpoint requires `ROLE_EDITOR`, CSRF protection is enabled, and the system uses HTTP Basic for demo authentication:

| Authentication | CSRF | Typical outcome | Is item created? |
| --- | --- | --- | --- |
| None | None | 403 at CSRF filter | No |
| None | Valid | 401 at authentication/authorization | No |
| ROLE_EDITOR | None | 403 | No |
| ROLE_EDITOR | Invalid token | 403 | No |
| ROLE_VIEWER | Valid | 403 due to missing `ROLE_EDITOR` | No |
| ROLE_EDITOR | Valid | 201 Created if request/body valid | Yes |
| ROLE_EDITOR | Valid, yet body fails validation | 4xx per validation | No, if handled properly |

These statuses are expectations **for the demo configuration** below. Do not treat them as universal constants across every API: entry points, `AccessDeniedHandler`, servlet containers, proxies, custom filters, and app rules can yield different statuses. To confirm whether 403 came from CSRF or authorization, check whether the request carried a valid token, safe logs/exceptions, and which filter handled it.

**An invalid CSRF token** differs from **an invalid OAuth access token**. An invalid CSRF token is usually rejected 403 by `CsrfFilter` when the request requires protection. A Bearer JWT with a bad signature or expired timestamp belongs to authentication, typically 401. If both are wrong, whichever layer runs first determines the first response; never infer a single root cause from status alone.

## 6. spring-security-test and MockMvc: The Testing Toolkit

With Spring Security Test, a request post-processor named **`csrf()`** imported from `SecurityMockMvcRequestPostProcessors` adds a valid CSRF token to a MockMvc request. Common variants:

~~~java
// Attach a valid CSRF token to the request:
.with(csrf())

// Send the submitted token as an HTTP header:
.with(csrf().asHeader())

// Deliberately send an invalid CSRF token:
.with(csrf().useInvalidToken())

// Send an invalid value via header:
.with(csrf().asHeader().useInvalidToken())
~~~

These lines are fragments for `MockHttpServletRequestBuilder`, not a standalone runnable Java program.

**`with(csrf())` is not a login action**. It only sets up the CSRF condition for the mock request. If the endpoint requires authentication, add `@WithMockUser`, `httpBasic(...)`, or another authentication mechanism to the test. Conversely, **`@WithMockUser` does not automatically add a CSRF token**; a POST with mocked authentication can still return 403 for missing a token.

The test helper creates/attaches tokens in MockMvc to exercise the security filter; it is **not proof that the production frontend implements the token-fetching flow properly**, cookies, sessions, SameSite, XSRF headers, or token rotation. Verifying a real browser/client requires separate HTTP integration tests.

For `application/json` APIs, you can use POST/PUT/PATCH with `contentType(MediaType.APPLICATION_JSON)` and `with(csrf())`. This demo uses **`text/plain`** to keep controller and test code short and focused on CSRF. CSRF does not depend on whether the request body is JSON, form, multipart, or text/plain.

## 7. Creating the Sample Project: Dependencies and File Structure

Java 17+ project using Spring Boot 3.x, Spring MVC, and Spring Security 6.x.

In `build.gradle` (Groovy), with Boot plugin and dependency management already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Files:

~~~text
src/main/java/demo/csrfhttp/
    CsrfHttpApplication.java
    SecurityConfig.java
    ItemStore.java
    ItemController.java

src/test/java/demo/csrfhttp/
    CsrfHttpIntegrationTest.java
~~~

This is a runnable example inside a Spring Boot project with the matching build plugin, dependency repositories, and Gradle wrapper. Spring Boot manages Security versions; do not arbitrarily mix versions outside the BOM.

The sample app uses an **in-memory store** without a database so tests can verify whether creation/update/deletion occurred. Data is lost on restart; it is not a production persistence design.

## 8. Spring Boot Entry Point

File `src/main/java/demo/csrfhttp/CsrfHttpApplication.java`:

~~~java
package demo.csrfhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfHttpApplication.class, args);
    }
}
~~~

`@SpringBootApplication` performs component scanning in package `demo.csrfhttp`, including `SecurityConfig`, `ItemStore`, and `ItemController`. You do not need to write a custom servlet filter to handle CSRF yourself.

## 9. SecurityConfig: Keeping CSRF Protection and Authorization Independent

File `src/main/java/demo/csrfhttp/SecurityConfig.java`:

~~~java
package demo.csrfhttp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
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
                .requestMatchers(HttpMethod.GET, "/api/items/public")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.PUT, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.PATCH, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.DELETE, "/api/items/**")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("EDITOR")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-password"))
                .roles("VIEWER")
                .build()
        );
    }
}
~~~

Key decisions:

1. **`.csrf(Customizer.withDefaults())`** keeps default CSRF protection active. Spring Security Servlet typically enables CSRF by default in an `HttpSecurity` chain; it is written explicitly here to prevent misunderstanding.
2. `GET /api/items/public` is public, which does not mean create/update/delete operations are permitted.
3. POST/PUT/PATCH/DELETE require `ROLE_EDITOR`. Bob has `ROLE_VIEWER`, so even with a valid CSRF token he is blocked by authorization.
4. `GET /api/items/{id}` requires authentication, yet by default does not require a CSRF token because it is a read operation.
5. **HTTP Basic** supplies demo credentials to test the authentication path beyond `@WithMockUser`. Never use unencrypted HTTP Basic in production; always require HTTPS.
6. `PasswordEncoder` uses the delegating encoder, and demo users live in memory. This is not a production account-management approach.
7. Do not call `csrf.disable()` or set broad `ignoringRequestMatchers` just to make POST tests pass; doing so prevents negative tests from checking the intended policy.

The sample configuration does not pin `SessionCreationPolicy.STATELESS`. CSRF models commonly use `HttpSessionCsrfTokenRepository`; if you apply a stateless policy to a session/cookie app, redesign the CSRF token repository and client flow rather than just flipping a flag.

## 10. In-Memory Store to Measure Side Effects

File `src/main/java/demo/csrfhttp/ItemStore.java`:

~~~java
package demo.csrfhttp;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;

@Component
public class ItemStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<Long, String> items =
        new ConcurrentHashMap<>();

    public long create(String name) {
        long id = sequence.incrementAndGet();
        items.put(id, name);
        return id;
    }

    public String find(long id) {
        return items.get(id);
    }

    public boolean update(long id, String name) {
        return items.replace(id, name) != null;
    }

    public boolean delete(long id) {
        return items.remove(id) != null;
    }

    public int count() {
        return items.size();
    }

    public void clearForTests() {
        items.clear();
        sequence.set(0);
    }
}
~~~

`ItemStore` is intentionally simple, with no transactions and no database. Any POST/PUT/PATCH/DELETE request that actually reaches the controller modifies `items`. Tests can inspect data before/after to catch a request that should have been blocked yet still executed.

`clearForTests()` is a utility for the test example and must not be exposed as an HTTP endpoint for clients to call. When using a database in a real project, verify repository state and transaction boundaries appropriately; never assume HTTP 403 automatically proves a method caused no side effects if an earlier custom filter ran.

## 11. Controller for GET, POST, PUT, PATCH, DELETE

File `src/main/java/demo/csrfhttp/ItemController.java`:

~~~java
package demo.csrfhttp;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemStore store;

    public ItemController(ItemStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "ok");
    }

    @GetMapping("/{id}")
    public ResponseEntity<Item> get(@PathVariable long id) {
        String name = store.find(id);
        if (name == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @PostMapping(consumes = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<Item> create(@RequestBody String name) {
        long id = store.create(name);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new Item(id, name));
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Item> replace(
            @PathVariable long id, @RequestBody String name) {
        if (!store.update(id, name)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Item> patch(
            @PathVariable long id, @RequestBody String name) {
        if (!store.update(id, name)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(id, name));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (!store.delete(id)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    public record Item(long id, String name) {}
}
~~~

In this example both PUT and PATCH replace the whole `name` field solely to show that both are **state-changing methods** requiring CSRF protection. In a real API, PUT and PATCH have distinct full vs. partial replacement contracts and require proper validation, concurrency control, ownership checks, and idempotency.

Never use GET to create, modify, or delete items. `GET /api/items/public` only returns status. Successful POST returns `201 Created`; successful PUT/PATCH returns `200 OK`; successful DELETE returns `204 No Content`. When an item does not exist, the controller returns 404. These business statuses only appear **after security filters allow the request to reach the controller**.

## 12. Full Tests: MockMvc + CSRF + Authorization + Side Effects

File `src/test/java/demo/csrfhttp/CsrfHttpIntegrationTest.java`:

~~~java
package demo.csrfhttp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfHttpIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ItemStore store;

    @BeforeEach
    void resetItems() {
        store.clearForTests();
    }

    @Test
    void getPublicWithoutCsrfIsAllowed() throws Exception {
        mvc.perform(get("/api/items/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postMissingCsrfIsForbiddenWithoutSideEffect()
            throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postInvalidCsrfIsForbiddenWithoutSideEffect()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void postValidCsrfCreatesOneItem() throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Notebook"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("Notebook"));

        assertEquals(1, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void csrfSentAsHeaderAlsoWorks() throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf().asHeader())
                .contentType(MediaType.TEXT_PLAIN)
                .content("From header"))
            .andExpect(status().isCreated());

        assertEquals(1, store.count());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Not logged in"))
            .andExpect(status().isUnauthorized());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "bob", roles = "VIEWER")
    void validCsrfDoesNotReplaceAuthorization()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Not editor"))
            .andExpect(status().isForbidden());

        assertEquals(0, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void missingCsrfRejectsPutPatchAndDelete()
            throws Exception {
        long id = store.create("Before");

        mvc.perform(put("/api/items/{id}", id)
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PUT"))
            .andExpect(status().isForbidden());

        mvc.perform(patch("/api/items/{id}", id)
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PATCH"))
            .andExpect(status().isForbidden());

        mvc.perform(delete("/api/items/{id}", id))
            .andExpect(status().isForbidden());

        assertEquals("Before", store.find(id));
        assertEquals(1, store.count());
    }

    @Test
    @WithMockUser(username = "alice", roles = "EDITOR")
    void validCsrfAllowsPutPatchAndDelete()
            throws Exception {
        long id = store.create("Before");

        mvc.perform(put("/api/items/{id}", id)
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PUT"))
            .andExpect(status().isOk());

        assertEquals("After PUT", store.find(id));

        mvc.perform(patch("/api/items/{id}", id)
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("After PATCH"))
            .andExpect(status().isOk());

        assertEquals("After PATCH", store.find(id));

        mvc.perform(delete("/api/items/{id}", id)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertNull(store.find(id));
        assertEquals(0, store.count());
    }

    @Test
    void actualHttpBasicAndValidCsrfAllowPost()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Authenticated"))
            .andExpect(status().isCreated());

        assertEquals(1, store.count());
    }
}
~~~

This test class uses **`SpringBootTest`, `AutoConfigureMockMvc`, JUnit 5, and `spring-security-test`**. With the classes and dependencies listed above, it starts the Web `ApplicationContext`, using the real `SecurityFilterChain`, real CSRF configuration, and real controller. No mocking of `CsrfFilter` or disabling security is needed.

**Analysis of the ten tests:**

1. `getPublicWithoutCsrfIsAllowed`: proves public GET needs no token and returns the right status.
2. `postMissingCsrfIsForbiddenWithoutSideEffect`: a user with `ROLE_EDITOR` but missing a CSRF token still gets 403; the store stays empty.
3. `postInvalidCsrfIsForbiddenWithoutSideEffect`: same role yet invalid token; still 403 and creates no item.
4. `postValidCsrfCreatesOneItem`: valid CSRF and role; POST reaches the controller, returns 201, and item count increments.
5. `csrfSentAsHeaderAlsoWorks`: supplies the token via Spring Security Test's header mode; also permitted.
6. `validCsrfDoesNotReplaceAuthentication`: valid CSRF but no user; HTTP Basic entry point rejects with 401.
7. `validCsrfDoesNotReplaceAuthorization`: Bob has `ROLE_VIEWER`, not `ROLE_EDITOR`; 403 from authorization.
8. `missingCsrfRejectsPutPatchAndDelete`: all three modify/delete operations are blocked, data stays untouched.
9. `validCsrfAllowsPutPatchAndDelete`: valid token and role allow PUT, PATCH, and DELETE; state is verified after each step.
10. `actualHttpBasicAndValidCsrfAllowPost`: uses `httpBasic(...)` to authenticate through `SecurityFilterChain` instead of `@WithMockUser`; still requires a CSRF token simultaneously.

Each test uses `@BeforeEach` to clear memory and avoid run-order dependencies. The examples are expected to run sequentially under standard JUnit settings; if a project enables parallel execution, isolate `ItemStore` per test or use appropriate locking so tests never share state.

`@Transactional` or database rollback is not used in the demo because `ItemStore` has no persistence; production repository tests must verify proper transaction and commit/rollback semantics.

## 13. Why Is Asserting 403 Not Enough?

A test writing only:

~~~java
mvc.perform(post("/api/items"))
    .andExpect(status().isForbidden());
~~~

does not fully prove the intended policy because:

- The request could be blocked for **not logging in**, for **CSRF**, for **lacking a role**, or by another filter.
- If a controller produced a side effect before an exception was translated into 403 in a custom flow, data could still be mutated.
- If the endpoint does not exist or routing is wrong, the test may not even be hitting the right resource.
- A 403 status could also be returned by custom application code unrelated to `CsrfFilter`.

To **isolate CSRF**, set an authenticated user **with the required role** and vary only the submitted CSRF token: missing, invalid, and valid. Then assert both the response and state. To isolate roles, keep a valid CSRF token and vary authority between `ROLE_EDITOR` and `ROLE_VIEWER`. To isolate authentication, keep a valid CSRF token and omit credentials.

This is a per-axis testing model:

~~~text
Axis A - Authentication
  anonymous <-> authenticated

Axis B - Authorization
  ROLE_VIEWER <-> ROLE_EDITOR

Axis C - CSRF
  missing <-> invalid <-> valid

Axis D - HTTP method
  GET <-> POST <-> PUT <-> PATCH <-> DELETE

Axis E - Side effects
  unchanged <-> created/updated/deleted
~~~

A good test states clearly which axis is being varied. Never break all factors at once and then assume 403 proves every individual check works.

## 14. Valid Tokens in MockMvc Do Not Fully Simulate a Browser Session

`with(csrf())` is built to test Spring Security logic. It **does not** guarantee the frontend actually knows how to fetch the token, pass the right cookie, use the right session, or obtain a fresh token after login/logout.

In a session-based browser app:

1. The server issues or makes the CSRF token available per the configured mechanism.
2. The client obtains the token via HTML form, meta tag, response attribute, or a securely designed token endpoint.
3. The client submits the token in a form parameter or server-allowed request header.
4. The browser sends the session cookie for the corresponding user/session.
5. The server compares the client-submitted token with the expected token in the session or repository.
6. Upon login/logout or lifecycle changes, the token may be cleared/rotated and the client must refresh it.

With Spring Security 6's default CSRF configuration, there are also details around **deferred CSRF tokens** and **token masking via `CsrfTokenRequestHandler`**. If an SPA submits a raw token read from a cookie, the header request handler must be configured accordingly. Do not assume that merely adding `CookieCsrfTokenRepository.withHttpOnlyFalse()` is always enough for every Spring Security 6 SPA: resolving/decoding a header token may need a different handler than masked request-attribute tokens, and tokens must be refreshed after authentication.

Thoroughly testing a cookie/session app requires real HTTP steps: extract the token/cookie from a prior response, keep a cookie jar, submit the CSRF token in form/header, test a token from **another session**, test an expired token after logout, and confirm the server rejects them.

MockMvc helpers are convenient yet do not check the risk of **CSRF tokens leaking or colliding across two sessions**. Include integration tests simulating at least two distinct sessions when your app policy relies heavily on sessions.

## 15. Multipart, JSON, and Form Requests Do Not Make CSRF Disappear

CSRF applies per **HTTP request** and token mechanism, not simply by content type.

- HTML form POSTs usually send `_csrf` as a hidden field alongside the session cookie.
- AJAX/JSON requests can send CSRF via a header such as `X-CSRF-TOKEN` per the configured repository/handler.
- Multipart uploads require considering body parsing and multipart/CSRF filter ordering to locate the token, upload limits before authentication, and expensive request handling.
- PUT/PATCH/DELETE using a JSON body still need CSRF if the app relies on auto-sent credentials.

MockMvc example for a JSON POST:

~~~java
mvc.perform(post("/api/items")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isCreated());
~~~

**The snippet above illustrates a controller accepting the right JSON schema**, and is not directly usable with `ItemController` in section 11 because the demo controller only consumes `text/plain`. To run the JSON example, the controller must declare a `@RequestBody` DTO matching the JSON and remove `consumes=text/plain`.

When testing negative cases, keep the request body **valid** for the controller so you do not accidentally trigger a 400/415 body error instead of a CSRF error. Likewise, when intentionally testing invalid validation, supply valid CSRF token and authentication to prove the failure came from validation.

## 16. When Should CSRF Not Be Enabled for Every Request?

An API that solely uses `Authorization: Bearer` headers **explicitly** sent by a JavaScript/mobile app and does not rely on auto-sent cookie/session credentials may not share the same CSRF threat model. For a stateless Resource Server, there are valid cases to disable CSRF on the API chain:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(org.springframework.security.config.Customizer.withDefaults())
        )
        .build();
}
~~~

This snippet is a **standalone illustrative configuration** for a Bearer JWT Resource Server, not a drop-in replacement for the demo `SecurityConfig` class. Running it requires properly configured JWT decoder/issuer, resource-server dependencies, and verifying the API accepts no automatic cookie/session authentication path. Do not copy this into a form-login application and assume it is protected.

If the same system has both a **session/cookie web UI** and a **Bearer API**, split `SecurityFilterChain` beans with appropriate matchers: keep CSRF for the browser chain, and evaluate disabling CSRF only on the API chain whose threat model is verified. Even then, chain ordering, fallback rules, cookie sharing, and authentication mechanisms must be tested so no endpoint is left exposed.

**Never disable CSRF because a test got 403.** That 403 might be flagging a genuine bug in how the frontend submits requests. The goal of testing is to preserve the right protection and catch dangerous changes, not to force every POST to return 2xx.

## 17. An Extended Matrix for Regression Testing

Once baseline tests exist, expand according to business needs:

| Test case | Setup | Expectation |
| --- | --- | --- |
| POST missing token | `ROLE_EDITOR`, valid body | 403; no item created |
| POST fake token | `ROLE_EDITOR`, `csrf().useInvalidToken()` | 403; no item created |
| POST token via header | `ROLE_EDITOR`, `csrf().asHeader()` | 201; creates one item |
| PUT missing token | `ROLE_EDITOR`, item exists | 403; old name unchanged |
| PATCH missing token | `ROLE_EDITOR`, item exists | 403; old name unchanged |
| DELETE missing token | `ROLE_EDITOR`, item exists | 403; item still exists |
| POST valid token, not logged in | Anonymous | 401 with HTTP Basic; no item created |
| POST valid token, lacking role | `ROLE_VIEWER` | 403; no item created |
| POST valid token, valid role | `ROLE_EDITOR` | 201; item created |
| PUT/PATCH/DELETE valid token | `ROLE_EDITOR`, item exists | 200/200/204; corresponding state |
| Public GET without token | Anonymous | 200; no state change |
| Private GET unauthenticated | Anonymous | 401 |
| Private GET authenticated | `ROLE_VIEWER` or `ROLE_EDITOR` | 200 if item exists |
| POST wrong credentials + valid token | Wrong HTTP Basic | 401, no state change |
| POST token from another session | Real cookie/session test | Rejected if policy is session-bound |
| Request body fails validation | Valid auth, CSRF, and role | Validation error; no data written |
| CORS preflight OPTIONS | Valid origin, method, headers | Outcome per CORS policy, not treated as POST |
| Invalid POST request via proxy | Deployment environment | Rejected at proper layer; no side effects |

Do not force a single fixed status code across every row if the app uses a custom `AccessDeniedHandler` or custom entry point. In practice, capture both the response result and evidence of whether the controller/service ran; include request ID/correlation ID when tracing is present.

For large-scale HTTP testing, stratify into layers:

1. **MockMvc:** fast, tests security filter logic, controllers, and side effects in Spring TestContext.
2. **Embedded servlet container integration:** tests cookies, sessions, token issuance, form encoding, and real HTTP clients.
3. **Browser end-to-end:** tests frontend token refresh after login/logout, AJAX requests, SameSite/CORS, and CSRF state.
4. **Deployment smoke tests:** tests reverse proxies, ingress, HTTPS, and production policies.

## 18. Common Mistakes

**Mistake 1 — Treating `@WithMockUser` as sufficient for POST.** False. The annotation creates a simulated `Authentication` without adding a CSRF token. Add `with(csrf())` for happy-path tests; omit or corrupt the token for rejection tests.

**Mistake 2 — Treating `csrf()` as logging in.** False. A CSRF token proves the request satisfies anti-forgery checks; it does not establish who the principal is or which roles they hold.

**Mistake 3 — Assuming 403 always means missing role.** False: `CsrfFilter` can return 403 for missing/invalid tokens. Keep authentication/role valid when testing CSRF to isolate the cause.

**Mistake 4 — Request missing both authentication and CSRF token yet expecting 401.** `CsrfFilter` may reject before authorization, making 403 reasonable. To test authentication, supply a valid CSRF token first.

**Mistake 5 — Testing only POST and forgetting PUT, PATCH, DELETE.** All of these methods mutate data and need the same CSRF policy in applicable models.

**Mistake 6 — Using GET to mutate data.** The default CSRF matcher usually ignores GET. Fix the API semantics and use POST/PUT/PATCH/DELETE properly.

**Mistake 7 — Testing status without testing side effects.** Verify the store/repository does not write when a request is rejected; a 403 status alone does not prove business safety.

**Mistake 8 — Enabling `csrf.disable()` to make tests pass.** That removes the very protection this lesson tests. Disable it only when the threat model genuinely warrants it, such as a Bearer-only API with no auto-attached credentials.

**Mistake 9 — Using `csrf().useInvalidToken()` alongside other errors.** If the role is also wrong or the endpoint does not exist, 403/404 may not isolate CSRF. Control one variable at a time.

**Mistake 10 — Thinking CORS is enough to prevent CSRF.** CORS does not block all cross-origin requests; `SameSite` helps reduce risk yet does not replace CSRF policies in all scenarios.

**Mistake 11 — Thinking MockMvc tokens fully simulate cookies/SPAs.** `with(csrf())` is a test helper. Test token issuance, cookie jars, request handlers, and real token rotation separately.

**Mistake 12 — Confusing a bad CSRF token with a bad Bearer access token.** One belongs to `CsrfFilter`, the other to authentication. HTTP status depends on policy and filter order.

**Mistake 13 — Form or AJAX tokens reading the wrong header name.** Check `CsrfTokenRepository`, `CsrfTokenRequestHandler`, and request attributes/parameters/headers, especially with SPAs on Spring Security 6.

**Mistake 14 — Leaking test state between tests.** Use isolated fixtures, reset state, or apply clear transaction/rollback strategies so tests remain independent. When running in parallel, isolate in-memory stores/databases properly.

**Mistake 15 — Concluding MockMvc proves production safety.** MockMvc does not cover every browser/proxy/container interaction. Run real HTTP tests for cookies, SameSite, sessions, and deployment config.

## 19. Checklist Before Accepting an API with State-Changing Operations

- [ ] Clearly identified which requests use auto-sent cookie/session/Basic credentials and which are Bearer-only.
- [ ] GET/HEAD only read data, with zero state-changing side effects.
- [ ] POST/PUT/PATCH/DELETE are protected per the appropriate CSRF policy.
- [ ] Negative tests cover both missing CSRF tokens and invalid tokens.
- [ ] Positive tests cover valid tokens when authenticated and authorized.
- [ ] Separate tests verify valid token without authentication and valid token without authority.
- [ ] 401 and 403 are not conflated into a single cause.
- [ ] Assertions verify data remains **unchanged** on blocked requests.
- [ ] MockMvc tests include `spring-security-test`, `@AutoConfigureMockMvc`, and the right filter chain.
- [ ] `@WithMockUser` is never used to claim real password/JWT validation was tested.
- [ ] SPAs follow a token fetch/submit flow compatible with Spring Security 6's token repository and request handler.
- [ ] Cookies, SameSite, CORS, sessions, and HTTPS are tested in a production-like environment.
- [ ] CSRF is never disabled globally on browser endpoints just to bypass 403 errors.
- [ ] Authentication, role/authority, and object-level permission rules are tested independently of CSRF.
- [ ] Credentials, session IDs, Bearer tokens, or sensitive raw CSRF tokens are never written to public logs.

## 20. Self-Check and Conclusion

**Question 1.** Alice has `ROLE_EDITOR` and sends `POST /api/items` without a CSRF token. Expected outcome?

In the demo configuration, `CsrfFilter` blocks with HTTP 403, and `ItemStore` receives no new item. Valid authentication does not substitute for an anti-forgery token.

**Question 2.** A POST carries a valid CSRF token yet has no Basic authentication. Result?

With the example's Basic entry point, HTTP 401 and no item created. A valid CSRF token is not a login credential.

**Question 3.** Bob is logged in with `ROLE_VIEWER` and sends a valid token. Can he POST to create an item?

No. The `hasRole("EDITOR")` rule requires `ROLE_EDITOR`, so authorization denies with 403. A valid token does not grant roles.

**Question 4.** Why test PUT, PATCH, and DELETE instead of only POST?

They also mutate state and must fall under CSRF protection in session/cookie models. Missing a single method in a rule or custom configuration can leave a security gap.

**Question 5.** Does `with(csrf())` prove the web UI fetches the token properly after login and sends the right session cookie?

No. It prepares a mock token for the MockMvc request. Real HTTP/browser tests are required to verify token issuance, session binding, and lifecycle.

**Question 6.** When a POST returns 403, what should you check to find the cause?

Check authentication, roles, submitted CSRF token, expected token repository/handler, selected filter chain, and safe logs/exceptions. Vary one axis at a time in tests and inspect side effects.

**Conclusion:** HTTP testing for CSRF must go beyond "POST returns 403". Separate **missing token**, **invalid token**, **valid token**, **authentication**, **authorization**, and **state mutation** into independent cases. Use MockMvc with `csrf()`, `csrf().useInvalidToken()`, and `@WithMockUser` or `httpBasic(...)`, then verify the controller/service **does not mutate data when blocked**. For browser/cookie apps, supplement with session and token-lifecycle tests outside MockMvc. That verifies both filter correctness and CSRF's protective effect across create, update, and delete operations.
