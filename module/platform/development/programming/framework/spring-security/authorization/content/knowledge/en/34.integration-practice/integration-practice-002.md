# Protecting HTTP Endpoints by READ, WRITE, ADMIN and Testing Every Method

## 1. Practice Objectives

When building an API with Spring Boot and Spring Security, the requirement “some users can read, others can write, administrators can manage” cannot be solved with `authenticated()` alone. You must clearly define the **HTTP method**, **resource path**, **caller authority**, and **permission on the specific object**. Then test both permitted and denied requests.

This practice uses **Java 17+, Spring Boot 3.x, Spring Security 6.x**, `SecurityFilterChain`, `authorizeHttpRequests`, and `MockMvc`. Illustrative policy:

- `READ`: can read documents via `GET`/`HEAD`; cannot create, edit, delete, or enter the admin area.
- `WRITE`: can read **and** create/edit/delete documents, but cannot enter the admin area.
- `ADMIN`: can read/write documents and view admin APIs.
- Without a matching authority: denied; unauthenticated requests receive a challenge according to the configured authentication mechanism.
- Unlisted paths or methods: **deny by default**.

Here `READ`, `WRITE`, `ADMIN` are **raw `GrantedAuthority` strings**, without automatically adding a `ROLE_` prefix. We explicitly specify that WRITE and ADMIN can also READ using `hasAnyAuthority`, as Spring Security does not automatically infer this hierarchy. In a real system, read, write, and admin permissions usually have more specific names such as `DOCUMENT_READ`, `DOCUMENT_WRITE`, `TENANT_ADMIN`.

**Scope limitation:** this example focuses on protection at the HTTP layer. A request allowed to WRITE is not necessarily allowed to modify **every** document: permissions by owner, tenant, ACL, status, and business rules must still be checked in the service/repository layer. HTTP authorization is the first layer, not the entire policy.

## 2. Designing the Permission Matrix Before Writing Code

Assume the following hypothetical API:

| HTTP Method | Path | Action | Allowed Authorities | Success Outcome |
| --- | --- | --- | --- | --- |
| `GET` | `/api/documents/{id}` | Read content | READ, WRITE, ADMIN | 200 |
| `HEAD` | `/api/documents/{id}` | Read HTTP metadata, return no body | READ, WRITE, ADMIN | 200 |
| `POST` | `/api/documents` | Create document | WRITE, ADMIN | 201 |
| `PUT` | `/api/documents/{id}` | Replace content | WRITE, ADMIN | 200 |
| `PATCH` | `/api/documents/{id}` | Partial update | WRITE, ADMIN | 200 |
| `DELETE` | `/api/documents/{id}` | Delete document | WRITE, ADMIN | 204 |
| `GET` | `/api/admin/reports` | Read admin reports | ADMIN | 200 |
| Other | Any path/method without a policy | Unsupported or unauthorized | Nobody per illustrative config | Denied |

A few details to understand upfront:

1. **HTTP methods have semantics.** GET and HEAD are designed to be safe (no business side effects); PUT is usually idempotent, PATCH depends on semantics; DELETE is usually idempotent regarding resource state. Idempotency does not dictate authorization. Never perform data mutations in GET/HEAD.
2. **HEAD is a distinct method at the HTTP layer.** Spring MVC can serve HEAD via `@GetMapping`, but a request matcher with `HttpMethod.GET` should not be assumed to automatically cover HEAD. We list HEAD explicitly.
3. **OPTIONS is commonly used for CORS preflight.** Preflight is not a write command; CORS determines whether a browser can send cross-origin requests, not authorization for the actual request. Configure `http.cors(...)` and allowed origins/methods/headers when the frontend is on another origin. Never open all OPTIONS or all endpoints just to “fix CORS errors.”
4. **TRACE/CONNECT and unexpected methods** must not be granted access automatically; the example ends with `anyRequest().denyAll()`. In real configurations, handle health, error, static assets, and preflight endpoints deliberately, without letting a permissive wildcard swallow them.
5. **Order specific rules before broad rules.** Spring Security evaluates `requestMatchers` rules in declaration order and applies the first match. Putting `requestMatchers("/api/**").authenticated()` before WRITE/ADMIN rules allows any logged-in user through the HTTP layer for endpoints that should require WRITE.

Example of **misordered** rules:

```java
// Do not use: broad rule swallows the specific rules that follow.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
        .hasAuthority("WRITE")
    .anyRequest().denyAll()
)
```

The `DELETE` rule below never gets a chance to decide for URLs already matched by `/api/**`. Declare specific scopes, test real requests, and keep default deny.

## 3. Spring Boot Project Structure

The files below form a **runnable example in a Maven Spring Boot 3.x project with JDK 17+**. Choose a Spring Boot 3.x version still supported/patched in your organization; the dependency snippet below assumes the project has a Spring Boot parent/BOM, avoiding pinning versions incompatible with the app lifecycle.

Maven dependencies in `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The application uses package `com.example.httpauth`, containing these files:

```text
src/main/java/com/example/httpauth/
  HttpAuthorizationApplication.java
  SecurityConfig.java
  DocumentController.java
  AdminController.java
src/test/java/com/example/httpauth/
  HttpAuthorizationIntegrationTest.java
```

This is a **demo API without database persistence** to focus on HTTP checks. Endpoints return fixed strings; when moving to production, controllers must call services with resource-level permissions, validation, transactions, and proper persistence.

### 3.1. Startup Class

`HttpAuthorizationApplication.java`:

```java
package com.example.httpauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }
}
```

Spring Boot scans beans in this package. `SecurityConfig` and controllers reside in the same package for automatic discovery.

### 3.2. SecurityFilterChain: Controlling by Method and Authority

`SecurityConfig.java`:

```java
package com.example.httpauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAnyAuthority("READ", "WRITE", "ADMIN")
                .requestMatchers(HttpMethod.HEAD, "/api/documents/*")
                    .hasAnyAuthority("READ", "WRITE", "ADMIN")

                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.PUT, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")
                .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                    .hasAnyAuthority("WRITE", "ADMIN")

                .requestMatchers("/api/admin/**")
                    .hasAuthority("ADMIN")

                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Key points to note:

- `authorizeHttpRequests` defines request-based authorization. In Spring Security 6, this API uses the modern `AuthorizationManager`-based mechanism.
- `requestMatchers(HttpMethod, path)` requires **matching both method and path simultaneously**. The `/api/documents/*` pattern here applies to resources one segment after `documents/`; subresources like `/api/documents/1/comments` are not automatically granted access. New routes and policies must be declared when building such features.
- `hasAnyAuthority("READ", "WRITE", "ADMIN")` is OR logic: having **at least one** authority in the set suffices. Role inheritance is not inferred automatically.
- `/api/admin/**` has a separate rule; users with WRITE but without ADMIN still cannot view admin reports. Never place a broad `authenticated()` before it.
- `anyRequest().denyAll()` ensures unclassified routes cannot pass through the authorization layer. A nonexistent route may return 403 (if denied by the filter before reaching MVC) rather than 404; design an explicit error contract per product.
- `httpBasic(...)` illustrates an easy-to-use authentication mechanism for tests/labs. `formLogin` is disabled. For production using JWT/OAuth2, apply the corresponding resource-server configuration; **authorization policies must still be retained**.
- We **do not disable CSRF**. With HTTP Basic/cookies/sessions where browsers can send credentials automatically, CSRF requires serious consideration. By default Spring Security checks tokens on state-changing requests such as POST/PUT/PATCH/DELETE. In tests, use `.with(csrf())` to verify the actual permission rules instead of getting blocked earlier by CSRF. For pure Bearer-token APIs not automatically sent by browsers and not using cookie auth, a different CSRF policy may be considered after threat modeling — never copy `csrf.disable()` out of habit.

To have accounts for HTTP Basic when running the real application, a properly configured `UserDetailsService`/IdP and trusted authority assignment are needed. Subsequent tests use Spring Security Test to attach a principal directly to the request, so they are **not** tests of real password/JWT authentication.

### 3.3. Controllers Covering All HTTP Methods

`DocumentController.java`:

```java
package com.example.httpauth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return "read:" + id;
    }

    // Spring MVC supports HEAD for GET mappings.
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public String create() {
        return "created";
    }

    @PutMapping("/{id}")
    public String replace(@PathVariable String id) {
        return "replaced:" + id;
    }

    @PatchMapping("/{id}")
    public String edit(@PathVariable String id) {
        return "patched:" + id;
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        // Demo without data persistence.
    }
}
```

`AdminController.java`:

```java
package com.example.httpauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    @GetMapping("/reports")
    public String reports() {
        return "admin-report";
    }
}
```

The sample API **has no** endpoints for `OPTIONS`, `TRACE`, or other subresource paths. Nor are they `permitAll`. When adding CORS preflight for a frontend application, CORS configuration must specify explicit origins, methods, and headers; a successfully handled preflight does not grant permission to execute GET/WRITE afterward.

### 3.4. Why Not Only Write @PreAuthorize on Controllers?

At the HTTP layer, `SecurityFilterChain` clearly reveals **rules by HTTP verb**. `@PreAuthorize` is useful on service/controller methods for deeper logic checks, for example:

```java
@PreAuthorize("@documentPolicy.canEdit(authentication, #tenantId, #id)")
public void editDocument(UUID tenantId, UUID id, EditRequest request) {
    // Service performs conditional update checking owner/tenant/version.
}
```

The snippet above is only an **illustrative fragment**, requiring separately defined `documentPolicy` bean, DTOs, and service. It does not replace GET/POST/PUT/PATCH/DELETE mappings or database constraints. In a multi-tenant system, `documentPolicy` must verify the current tenant/resource/owner/ACL on the server. Never use client-supplied ownerId, role, or tenantId as proof of permission.

## 4. Integration Testing Each HTTP Method with MockMvc

A useful test must pass through the **Spring Security filter chain**; never just call the controller directly with `new DocumentController()`, nor mock `SecurityFilterChain`. We use `@SpringBootTest` and `@AutoConfigureMockMvc` to load the real configuration while substituting the principal via Spring Security Test.

The test source set needs the `spring-security-test` dependency, especially for `user(...)` and `csrf()`.

`HttpAuthorizationIntegrationTest.java`:

```java
package com.example.httpauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    private void expect(HttpMethod method, String path,
                        String authority, int httpStatus) throws Exception {
        MockHttpServletRequestBuilder builder = request(method, path)
                .with(user("test-user")
                    .authorities(new SimpleGrantedAuthority(authority)));

        if (method == HttpMethod.POST
                || method == HttpMethod.PUT
                || method == HttpMethod.PATCH
                || method == HttpMethod.DELETE) {
            builder.with(csrf());
        }

        mvc.perform(builder).andExpect(status().is(httpStatus));
    }

    @Test
    void readAndHeadMatrix() throws Exception {
        expect(HttpMethod.GET, "/api/documents/d1", "READ", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.GET, "/api/documents/d1", "NONE", 403);

        expect(HttpMethod.HEAD, "/api/documents/d1", "READ", 200);
        expect(HttpMethod.HEAD, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.HEAD, "/api/documents/d1", "NONE", 403);
    }

    @Test
    void postMatrix() throws Exception {
        expect(HttpMethod.POST, "/api/documents", "WRITE", 201);
        expect(HttpMethod.POST, "/api/documents", "ADMIN", 201);
        expect(HttpMethod.POST, "/api/documents", "READ", 403);
    }

    @Test
    void putMatrix() throws Exception {
        expect(HttpMethod.PUT, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.PUT, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.PUT, "/api/documents/d1", "READ", 403);
    }

    @Test
    void patchMatrix() throws Exception {
        expect(HttpMethod.PATCH, "/api/documents/d1", "WRITE", 200);
        expect(HttpMethod.PATCH, "/api/documents/d1", "ADMIN", 200);
        expect(HttpMethod.PATCH, "/api/documents/d1", "READ", 403);
    }

    @Test
    void deleteMatrix() throws Exception {
        expect(HttpMethod.DELETE, "/api/documents/d1", "WRITE", 204);
        expect(HttpMethod.DELETE, "/api/documents/d1", "ADMIN", 204);
        expect(HttpMethod.DELETE, "/api/documents/d1", "READ", 403);
    }

    @Test
    void adminIsSeparateFromWrite() throws Exception {
        expect(HttpMethod.GET, "/api/admin/reports", "ADMIN", 200);
        expect(HttpMethod.GET, "/api/admin/reports", "WRITE", 403);
        expect(HttpMethod.GET, "/api/admin/reports", "READ", 403);
    }

    @Test
    void unmatchedRouteIsDeniedEvenToAdmin() throws Exception {
        expect(HttpMethod.GET, "/api/documents/d1/comments", "ADMIN", 403);
    }

    @Test
    void unauthenticatedReadGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/documents/d1"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfFailsEvenForAuthorizedWriter() throws Exception {
        mvc.perform(post("/api/documents")
                .with(user("writer").authorities(
                        new SimpleGrantedAuthority("WRITE"))))
           .andExpect(status().isForbidden());
    }
}
```

**Test explanation:**

- The helper method creates a request by `HttpMethod` and **an actual authority in the test SecurityContext**. Using `SimpleGrantedAuthority("READ")` differs from `roles("READ")`, because `roles` prepends `ROLE_` by default.
- `GET`/`HEAD` do not require a CSRF token; `POST`/`PUT`/`PATCH`/`DELETE` get `.with(csrf())`. When `POST` gets 403 with READ, the test is verifying **missing WRITE permission**, not accidentally missing CSRF.
- `status().is(201)`, `is(204)`, or `is(403)` are MockMvc assertions. `@SpringBootTest` does not have to start an external HTTP server, yet the filter chain and MVC still participate.
- The anonymous GET test expects 401 because `httpBasic()` is enabled; do not rigidly expect 401 for every authentication model, especially form login or custom entry points.
- Testing missing CSRF with a WRITE user demonstrates that **passing authorization does not bypass request-forgery protection**.
- The unmatched route test proves the default rule does not “expose” undeclared endpoints. With other configurations, error dispatches or 404 handling may need adjustments to match the API contract.

Run using the Maven wrapper in a project containing the files above:

```bash
./mvnw test -Dtest=HttpAuthorizationIntegrationTest
```

Or if Maven is already installed:

```bash
mvn test -Dtest=HttpAuthorizationIntegrationTest
```

On Windows, use `mvnw.cmd` accordingly. **Expected result:** 9 test methods execute and all pass in a Spring Boot 3.x/Security 6.x environment with compatible dependencies. Maven/JUnit log formatting depends on version, so do not treat a hypothetical stdout snippet as fixed output; only require all assertions to pass. Checks inside a single method make multiple HTTP requests, so **the number of HTTP requests tested exceeds the number of test methods**.

**Pitfall to avoid:** calling `@WithMockUser` or `user(...)` constructs a test principal; it does **not** verify HTTP Basic passwords, token signatures, issuers, audiences, authority converters, or real IdP configs. Separate authentication tests are required before moving to production.

### 4.1. When a 403 Test Is Actually Only Blocked by CSRF

A very common testing mistake:

```java
// This test does not prove role READ is denied by the WRITE rule:
mvc.perform(post("/api/documents")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("READ"))))
   .andExpect(status().isForbidden());
```

Because the request lacks CSRF, it may be blocked before reaching the authorization rule. Even if the configuration accidentally wrote `.permitAll()` for POST, this test could still pass. To test the policy, include `.with(csrf())` and assert 403; then write an independent test confirming CSRF protects write endpoints per the threat model.

Similarly, an anonymous GET test returning 401 does not prove the GET rule requires READ: even a broad `authenticated()` rule blocks anonymous users. You must test an **authenticated user who lacks the required authority**.

### 4.2. Checking the Response Body When Needed

The demo controller returns `"read:d1"` for GET; you can add:

```java
mvc.perform(get("/api/documents/d1")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("READ"))))
   .andExpect(status().isOk())
   .andExpect(content().string("read:d1"));
```

The snippet above requires the static import `org.springframework.test.web.servlet.result.MockMvcResultMatchers.content` in the test class. With real data, besides status you must assert **no data from other owners/tenants is leaked**, the body is filtered to the proper scope, and sensitive fields are absent from the response.

## 5. Adding Tests for Deny-by-Default, HEAD, and OPTIONS

### 5.1. HEAD Is Not GET in Method Matchers

In HTTP, HEAD equals GET in metadata without sending a response body. Many servers/MVC frameworks map HEAD to GET handlers, yet the Security matcher still sees the HEAD method. If you only declare:

```java
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("READ")
.anyRequest().denyAll()
```

then HEAD has no permit rule in this example. You can either **allow HEAD with the same READ permission** via a dedicated matcher, or intentionally block HEAD and test that behavior. Do not consider HEAD safe for letting anonymous users read private resource metadata: headers like `Content-Length`, `ETag`, and processing timing can leak information.

### 5.2. OPTIONS and CORS Preflight

With cross-origin browsers, a preflight OPTIONS request may send:

```http
OPTIONS /api/documents/d1 HTTP/1.1
Origin: https://frontend.example
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,authorization
```

CORS preflight usually does not carry credentials the way actual requests do. If the application uses a cross-origin frontend, configure Spring CORS for allowed origins/methods/headers and integrate with Spring Security, such as a properly provided `CorsConfigurationSource` paired with `http.cors(Customizer.withDefaults())`. **Do not** fix 401 errors on preflight by opening `/api/**` to all methods.

An accepted preflight only states that the origin may attempt PATCH; the actual PATCH request must still pass authentication, CSRF (if applicable), `WRITE` authorization, and resource-level policy. With specific CORS origins, never arbitrarily combine wildcards with credentials.

The sample API does not enable CORS explicitly; that is a demo scoping decision, not a missing permission bug. If the product has a frontend on another origin, add CORS configuration and test both OPTIONS preflight and actual requests. When handling OPTIONS, test both allowed and disallowed origins, disallowed methods/headers, and CORS response headers.

### 5.3. Method Override and Secondary Routing

Some frameworks/proxies support HTTP method override via headers/form parameters. Then the method seen at the Security layer and MVC layer may differ depending on filter order. Enable override mechanisms only when truly needed, configure consistently, and test that a READ user cannot use POST + override to execute DELETE.

If there are routes such as `/api/documents/{id}/download`, `/api/documents/{id}/share`, `/api/documents/{id}/attachments`, `/api/admin/users/{id}/roles`, classify each **action** individually instead of using a broad wildcard for the whole API. In particular, download/export may require a separate permission, not necessarily equivalent to READ metadata.

## 6. Distinguishing HTTP Authorization from Object-Level Authorization

Someone with `WRITE` can perform the functional category “edit document” yet **does not by default own every document**. We recommend splitting the policy into layers:

1. **Authentication:** caller is authenticated; authorities are mapped from a trusted source.
2. **HTTP authorization:** do the method and URL belong to the actor's READ/WRITE/ADMIN action set?
3. **Resource/tenant authorization:** does the document belong to the selected tenant, and does the actor actually have owner/ACL/membership and operation rights?
4. **Workflow authorization:** does the current state permit the action? For example, a LOCKED document may no longer allow EDIT even if the actor has WRITE.
5. **Data write guard:** immediately before writing, guard against races if owner/tenant/status/role changed between check and update.
6. **Response/side-effect filtering:** never output cross-tenant data, never emit success events when a transaction fails or is denied.

A repository pattern when updating might look like this (Spring Data JPA illustrative snippet, requiring corresponding entity and repository):

```java
@Modifying
@Query("""
    update Document d
       set d.title = :title,
           d.version = d.version + 1
     where d.id = :documentId
       and d.tenantId = :tenantId
       and d.ownerId = :actorId
       and d.status = :expectedStatus
       and d.version = :expectedVersion
""")
int updateOwnedDocument(
        UUID documentId,
        UUID tenantId,
        String actorId,
        String title,
        DocumentStatus expectedStatus,
        long expectedVersion);
```

Actor ID must come from the server-verified principal; `tenantId` is a membership-verified selector and must match the record; current `ownerId`/`status` are checked in the database; `expectedVersion` prevents overwriting concurrent changes. The illustrative code does not define the full transaction/policy. For memberships that can change mid-request, a separate consistency mechanism is needed if rules require immediate revocation.

**HTTP READ/WRITE/ADMIN tests only prove layer 2.** There must be integration tests against a real DB for layers 3–6, covering Bob's documents, other tenants, mid-request ownership transfers, status changes, stale versions, and audit/side effects.

## 7. Extended Test Matrix for Production Readiness

| Group | Scenario | What Must Be Asserted |
| --- | --- | --- |
| Authentication | Anonymous GET document | 401/challenge per configuration |
| READ | READ sends GET document | Succeeds 200 when resource policy permits |
| READ | READ sends HEAD document | Succeeds 200, returns no body |
| READ | Logged-in user with authority NONE sends GET | 403, returns no data |
| WRITE | READ sends POST with CSRF | 403 due to missing WRITE, no data created |
| WRITE | READ sends PUT with CSRF | 403, data unchanged |
| WRITE | READ sends PATCH with CSRF | 403, data unchanged |
| WRITE | READ sends DELETE with CSRF | 403, data not deleted |
| WRITE | WRITE sends valid POST/PUT/PATCH/DELETE | Each method succeeds per contract |
| ADMIN | WRITE sends GET /api/admin/reports | 403 even though WRITE can read/edit documents |
| ADMIN | ADMIN sends GET /api/admin/reports | 200 |
| Default deny | ADMIN calls undeclared GET /api/documents/d1/comments | Denied instead of matched by wildcard |
| CSRF | WRITE sends POST missing/invalid CSRF token | 403 when CSRF protects the endpoint |
| Role prefix | Principal has ROLE_READ while policy checks READ | Does not pass by default unless mapped properly |
| Tenant | Tenant A's WRITE updates tenant B's document | HTTP may pass, resource policy/DB must deny |
| Owner | WRITE attempts to edit another user's document | No data written |
| Status | WRITE attempts to edit a LOCKED document | Denied per workflow |
| Concurrency | Owner changes between precheck and write | No unauthorized write |
| CORS | OPTIONS preflight from allowed/blocked origins | CORS policy and actual request remain independent |
| Method override | READ tries calling DELETE via override | No bypass |
| Cache | Alice's READ decision cached, Bob requests same ID | Do not reuse Alice's ALLOW |

For endpoints that actually mutate the DB, assert not only HTTP status but also **updated row count, before/after content, owner/tenant/status, audit, and outbox events**. If tests only verify 403 from missing CSRF or anonymous requests, a route matcher bug can still slip through.

Run integration tests with a production-like configuration, plus separate unit tests for policy services. Also verify:
- Whether URL encoding, trailing slashes, context paths, path matching, and new routes alter matcher scope.
- Ordering of multiple `SecurityFilterChain` beans if the app has more than one chain. A request binds to the first chain whose `securityMatcher` matches; another chain may have different rules. Test actual requests rather than only reading the config.
- By default, method security `@PreAuthorize` only takes effect when enabled and called through a Spring proxy, so never rely solely on `this.securedMethod()` from the same bean.
- Whether authentication/authority mapping is flawed due to JWT converters, role prefixes, stale permission caches, or impersonation.

## 8. Common Mistakes and How to Detect Them

**Mistake 1 — Using `authenticated()` instead of a READ/WRITE/ADMIN policy.** Any logged-in user can edit/delete if rules are too broad. Fix: define and test authorities per method.

**Mistake 2 — Protecting only GET, forgetting HEAD.** HEAD can be served by Spring MVC from a GET handler, yet Security method matchers treat it as a distinct condition. Fix: add dedicated HEAD rules and tests.

**Mistake 3 — Using `hasRole("WRITE")` when the principal only has authority `WRITE`.** `hasRole` typically checks `ROLE_WRITE`, whereas `hasAuthority("WRITE")` checks the exact string `WRITE`. Fix: standardize permission names and converters; never mix the two conventions arbitrarily.

**Mistake 4 — Write tests missing `csrf()`.** The 403 test passes even though the configuration actually lets READ perform WRITE operations. Fix: test authorization with a valid CSRF token, and test CSRF separately.

**Mistake 5 — Broad wildcards or rules placed before specific rules.** `/api/**` with authenticated/permitAll can render subsequent rules ineffective. Fix: inspect ordering and default deny; test authenticated users lacking the authority.

**Mistake 6 — Assuming ADMIN automatically gets all permissions because of the name “admin”.** If you only configure `hasAuthority("WRITE")`, a user with only `ADMIN` will not pass. Fix: define intentional hierarchy (`hasAnyAuthority`, role hierarchy, or explicit authority assignment). The current example grants ADMIN read/write **explicitly**.

**Mistake 7 — Relying on the frontend hiding the Delete button.** HTTP requests can be sent directly; the client does not control server policy. Fix: authorize in filters/services and test the real API.

**Mistake 8 — Treating HTTP WRITE as owning every document.** Cross-tenant/IDOR happens when only roles are checked. Fix: resource-level policy in services and conditions/transactions guarding the DB.

**Mistake 9 — Ignoring CORS preflight or opening too wide to fix CORS.** OPTIONS is not real permission for PATCH; CORS origin does not replace authentication. Fix: configure CORS accurately and keep authorization rules on actual requests.

**Mistake 10 — Testing only positive cases.** If everyone gets access due to `permitAll()`, 200 tests still pass. Fix: one positive and at least one negative test for **every HTTP method** and sensitive route.

## 9. Advanced Exercises

Start with the sample code, then add three verification steps:

1. Try removing the `DELETE` rule from the configuration. With `anyRequest().denyAll()`, `deleteMatrix` must fail on cases expecting WRITE/ADMIN to get 204. That proves undeclared endpoints are not open by default.
2. Try changing the POST rule to `.authenticated()`. `postMatrix` with READ and a valid CSRF token must fail, because READ will get 201 instead of 403. This proves negative tests catch real configuration mistakes, not just CSRF.
3. Add endpoint `GET /api/documents/{id}/history` and a separate authority `HISTORY_READ`. Before adding the matcher, tests must be blocked by default deny; afterward, only HISTORY_READ can view it and READ/WRITE are not automatically permitted if security requirements forbid it.

Going further, combine `MockMvc` with a test database, two tenants, documents with different owners, and a `canEdit` policy. Use two transactions/latches to verify that transferring ownership or revoking membership before write time is not bypassed by HTTP authorization executed at the start of the request.

## 10. Lesson Completion Checklist

- [ ] Clearly documented whether READ, WRITE, ADMIN are **authorities**, or mapped properly if the app uses roles with the `ROLE_` prefix.
- [ ] Have a method × path × action × allowed authorities table, including HEAD and ADMIN routes.
- [ ] Specific rules precede broad rules; ends with `anyRequest().denyAll()`.
- [ ] Positive and negative tests exist for GET, HEAD, POST, PUT, PATCH, DELETE, and ADMIN.
- [ ] POST/PUT/PATCH/DELETE tests include a CSRF token when testing authorization; CSRF has separate tests.
- [ ] Anonymous tests are distinct from authenticated-but-forbidden tests.
- [ ] Real tests go through the Spring Security filter chain, not just plain controller calls.
- [ ] If cross-origin is used, CORS/preflight is configured with appropriate origins/methods/headers and actual requests are tested.
- [ ] Resource/tenant/owner/status are checked in service/DB in real business logic.
- [ ] Write operations protect against concurrency, not relying solely on ALLOW at request entry.
- [ ] Did not overlook other filter chains, new URL patterns, method override, permission caches, and response caches.

**Conclusion:** Design permissions by **HTTP method + path + authority**, then use `SecurityFilterChain` to block requests upfront. Testing must cover **permitted and denied cases for every method**, while ensuring CSRF does not mask authorization bugs. Finally, always separate action-type permissions at HTTP from permissions on actual resources in services and databases.