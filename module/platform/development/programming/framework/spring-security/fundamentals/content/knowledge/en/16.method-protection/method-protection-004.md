# @PostAuthorize: Checking Authorization Based on the Return Value

> **Spring Security fundamentals → Method protection.** `@PostAuthorize` is a **method security** mechanism for evaluating authorization **after the method has executed and produced a return value, but before that value is handed to the caller**. This lesson clarifies check timing, how to use the `returnObject` variable in SpEL, how to combine it with `@PreAuthorize` and object-level authorization, and a critical limitation: **denial at the post-check stage does not mean operations inside the method never occurred**.

## 1. The Problem: Same Read Permission, Not the Same Data

Suppose Alice and Bob both hold the `DOC_READ` authority in a document system. Both can call the read-document endpoint:

- Document `id = 1` has `owner = alice`.
- Document `id = 2` has `owner = bob`.
- Alice calls `GET /api/documents/1` → allowed.
- Alice calls `GET /api/documents/2` → **must not receive the contents of Bob's document**, even though Alice also has `DOC_READ`.

Using `@PreAuthorize("hasAuthority('DOC_READ')")` alone is insufficient because both Alice and Bob satisfy the coarse condition. An intuitive way to learn this is checking the owner of the **retrieved object**:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView findById(long id) {
    return repository.findById(id);
}
```

This is an **illustrative snippet placed inside a Spring-managed service**; `DocumentView` and `repository` are application-defined. `@PreAuthorize` checks the authority **before** invoking `findById`. If that passes, the method runs and builds `DocumentView`; `@PostAuthorize` then checks whether the returned object's `owner` matches the authenticated username.

**Understand its true nature:** `@PostAuthorize` is not a SQL filter, does not rewrite `id`, and does not stop the repository from executing the query. It is a **gate after the method produces a result**, deciding whether to return that result to the caller or raise an access-denied error.

## 2. Execution Mechanism: Before → Method → After

When method security is enabled, Spring Security implements method interceptors via Spring AOP, typically proxying Spring-managed beans. For a method carrying both annotations, the typical flow is:

```text
Caller (Controller or another service)
             |
             v
Spring proxy / method security
             |
   @PreAuthorize expression
       |              |
       | deny         | grant
       v              v
  Method not     Method is called
  called          |
                  v
             Result is created
                  |
                  v
          @PostAuthorize expression
              |              |
              | deny         | grant
              v              v
       AccessDeniedException   Return result
              |              |
         HTTP mapping       Caller handles
         per context        the value
```

Specifically:

1. A call **passes through the Spring proxy** to enter the protected method.
2. `@PreAuthorize` (if present) evaluates conditions on Authentication, parameters, and policies before execution. If denied, the method does not run.
3. The method may query the database, call an API, write logs, update caches, or do other work.
4. If the method **returns normally**, Spring Security evaluates `@PostAuthorize` against that result.
5. If the post-check expression returns **true**, the caller receives the result. If **false**, method authorization denies access and typically throws `AccessDeniedException`; when handling HTTP through Spring Security, exception-handling config determines the response, commonly **403 for an authenticated principal**.
6. If the method throws an exception before returning, there is no normal return value for this post-check path to evaluate; exception handling still needs an appropriate policy.

**Do not confuse ordering:** "`@PostAuthorize` runs afterward" does not mean "code inside the method is automatically rolled back on failure." Undoing transactions, database writes, sent emails, published messages, and external side effects is never guaranteed by this annotation alone.

## 3. SpEL Conditions and the Meaning of `returnObject`

`@PostAuthorize` takes a **Spring Expression Language (SpEL)** expression that evaluates to a Boolean to decide access. Its standout variable is `returnObject`, meaning **the object the method just returned** under the active interceptor's semantics.

Example:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView read(long id) { /* read document */ }
```

- `returnObject`: the returned `DocumentView` object.
- `returnObject.owner`: the `owner` property read by SpEL via a JavaBean getter or matching property accessor.
- `authentication`: the `Authentication` object of the protected invocation.
- `authentication.name`: the current principal name determined by Spring Security, **not a username sent by the client in a request body**.
- `==`: equality comparison per SpEL semantics; the Boolean result decides allow vs. deny.

### 3.1. Useful Expressions

| Expression | Meaning | Applicability condition |
|---|---|---|
| `returnObject.owner == authentication.name` | Lets the owner receive the object | Object is non-null; owner accurately reflects principal |
| `returnObject == null || returnObject.owner == authentication.name` | Lets missing result pass through; checks owner if present | Method returns null when not found; handler can return 404 |
| `hasAuthority('DOC_READ') && returnObject.owner == authentication.name` | Requires action right **and** owner match in post-check | Better to move coarse right check to `@PreAuthorize` to avoid wasted DB reads |
| `hasRole('ADMIN') || returnObject.owner == authentication.name` | Admin or owner can read | Cross-owner admin policy must genuinely be business-approved |
| `@documentPolicy.canRead(authentication, returnObject)` | Calls an authorization bean for complex policies | `documentPolicy` bean exists; API and null handling verified |

Spring Security supports SpEL functions such as `hasAuthority(...)`, `hasRole(...)`, and the `hasPermission(...)` hook. **`hasPermission` does not automatically understand every domain's ACL**: to use a custom permission evaluator, you must register/configure the corresponding evaluation mechanism and test it.

When writing `returnObject.owner`, make sure the object exposes a getter/property SpEL can actually access. For a Java class with `getOwner()`, `owner` is a standard JavaBean property. When using Java records, projections, proxies, maps, nullable/`Optional` values, or wrapper DTOs, verify the return type and how SpEL accesses that member. Never copy an expression across different return types without testing.

### 3.2. Nulls and Missing Resources

When a method can return `null`, the following expression easily fails with a property-access error:

```java
@PostAuthorize("returnObject.owner == authentication.name")
```

Decide explicit semantics:

```java
@PostAuthorize("returnObject == null || returnObject.owner == authentication.name")
```

In this example, `null` means "record not found" and is allowed through so the controller can return 404. However, if **a record exists outside the user's permission**, the owner post-check may return 403; thus, the caller can distinguish "does not exist" from "exists but forbidden." In many sensitive APIs, querying **scoped from the start** and returning 404 for both cases leaks less information.

If the method returns `Optional<DocumentView>`, `returnObject` is a wrapper per the method contract; do not assume `returnObject.owner` points straight to the inner object. Choose a clean API, handle empty intentionally, and test the expression on the exact return type.

### 3.3. Returning a List Is Not Like Returning a Single Object

`@PostAuthorize` does not automatically iterate over every element of `List<DocumentView>` to check ownership. An expression on `returnObject` must apply to the **List object itself** or call a policy examining the entire list. `@PostFilter` can filter elements after the method returns a collection, yet for large lists prefer **filtering with a predicate in the database query**: post-filtering after loading wastes resources, breaks pagination/counts, risks cache/log exposure, and does not make the underlying query safer.

### 3.4. ResponseEntity, DTOs, Entities, and Async Values

Placing `@PostAuthorize` on a service returning a **domain object/DTO** is usually cleaner to evaluate than on a controller returning `ResponseEntity<...>`: if annotated on a method returning `ResponseEntity`, `returnObject` is the response wrapper, not automatically its `body`. Avoid relying on internal wrapper structures hidden from reviewers.

With JPA entities having lazy relationships, reading properties during post-check can trigger extra database queries or persistence-context errors; fetch needed authorization data upfront, keep transactions clear, and never accidentally expose entities via serialization.

## 4. How Do `@PreAuthorize` and `@PostAuthorize` Complement Each Other?

| Criterion | `@PreAuthorize` | `@PostAuthorize` |
|---|---|---|
| Timing | Before the method runs | After the method creates its return value |
| Convenient checks | Authentication, roles/authorities, parameters, policies known before reading data | Properties of the result object, owner/visibility known after loading |
| When denied | Method normally has not executed | Method **has already executed**; caller does not receive result |
| Typical cost | Can avoid unnecessary DB reads and remote calls | May have already performed DB queries/CPU/I/O |
| Risk with writes | Reduces side-effect risk when rules are right | **Unsuitable as the sole control** for mutations |
| Example | `hasAuthority('DOC_READ')` | `returnObject.owner == authentication.name` |

A read method can use **both**, requiring all conditions to be satisfied:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject == null || returnObject.owner == authentication.name")
public DocumentView read(long id) {
    return repository.findById(id);
}
```

Logical sequence: a caller lacking `DOC_READ` is denied immediately without hitting the repository. A caller with `DOC_READ` but the wrong owner is denied after the repository returns the object. An authorized caller with matching owner receives the result. Use `@PreAuthorize` to avoid wasting I/O when early denial is possible.

**Distinguish action-level vs. object-level:** `DOC_READ` is permission to *read a resource type*; `owner == authentication.name` is just one policy for a *specific record*. Real products may also have tenant membership, status, ACLs, sharing grants, admin roles, and field-level permissions. Never assume owner-only is a complete policy for every system.

## 5. Runnable Spring Boot Example: Authorizing Read Results

This example uses **Spring Boot 3.x, Java 17+, Spring Security 6.x, and Servlet MVC**. It needs no real database: dummy data lives in a `Map` to focus on `@PostAuthorize` behavior. There are three users: Alice, Bob, and Viewer.

| User | Demo password | Authorities | Document read outcome |
|---|---|---|---|
| `alice` | `demo123` | `DOC_READ` | Reads doc 1; denied doc 2 |
| `bob` | `demo123` | `DOC_READ` | Reads doc 2; denied doc 1 |
| `viewer` | `demo123` | `PROFILE_READ` | Fails `@PreAuthorize` for reading documents |

### 5.1. Creating the Project and Dependencies

Create a **Spring Boot 3.x, Java 17+** project via Spring Initializr with Gradle, Spring Web, and Spring Security. Ensure the `dependencies` block in `build.gradle` contains:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the **dependencies block**, not the full build file: keep the Spring Boot plugin, Java configuration, repositories, and BOM from the generated project. Run using the project's Gradle Wrapper after creating the full structure.

### 5.2. A Complete Single Java File

Place `src/main/java/example/postauth/PostAuthorizeApplication.java`:

```java
package example.postauth;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/*"
                ).authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .authorities("DOC_READ").build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo123")
            .authorities("DOC_READ").build();
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}demo123")
            .authorities("PROFILE_READ").build();
        return new InMemoryUserDetailsManager(alice, bob, viewer);
    }
}

// Package-private record in the same file; Spring/Jackson can still
// serialize the components in this example.
record DocumentView(long id, String owner, String title) {
    // Explicit JavaBean getter for SpEL property "owner".
    public String getOwner() {
        return owner;
    }
}

@Service
class DocumentService {
    private final Map<Long, DocumentView> documents = Map.of(
        1L, new DocumentView(1L, "alice", "Alice plan"),
        2L, new DocumentView(2L, "bob", "Bob notes")
    );

    @PreAuthorize("hasAuthority('DOC_READ')")
    @PostAuthorize(
        "returnObject == null || returnObject.owner == authentication.name"
    )
    public DocumentView findById(long id) {
        // This is a read-only operation.
        return documents.get(id);
    }
}

@RestController
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    public ResponseEntity<DocumentView> get(
            @PathVariable long id) {
        DocumentView document = service.findById(id);
        if (document == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(document);
    }
}
```

The file has one `public class` matching the file name and package-private top-level classes/records in the same package. `@EnableMethodSecurity` enables interceptors for `@PreAuthorize` and `@PostAuthorize`; simply adding the Security starter **does not automatically enable method security**.

**Why is the annotation placed on `DocumentService`?** `DocumentController` receives `DocumentService` from Spring via constructor injection, so calls to `service.findById(...)` pass through the Spring-managed bean/proxy. When `findById(2)` returns `DocumentView(owner="bob")` while the principal is Alice, the post-check interceptor denies access **before the controller receives the object to render JSON**. Calling a manually instantiated `new DocumentService()` or self-calling within the same class via `this` in standard proxy mode can bypass method advice.

**Security of demo data:** `{noop}` is a non-encrypting password encoder, **for local demos only**. Use a proper password encoder, identity provider, TLS, secret protection, and auditing in real applications. Map data only simulates reads; it does not automatically protect SQL queries, tenants, or caches. The DTO returns the `owner` field for observation; real products must choose projections based on field-level viewing rights.

### 5.3. Running the App and Sending Requests

In the Boot project containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

The default HTTP port is 8080 unless occupied or changed by configuration. Send the requests:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/1
curl -i -u viewer:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/2
curl -i -u bob:demo123 http://localhost:8080/api/documents/2
curl -i -u alice:demo123 http://localhost:8080/api/documents/99
```

| Request | Expected status | Why |
|---|---|---|
| Anonymous `GET /public/ping` | 200, `ok` | HTTP `permitAll` |
| Anonymous `GET /api/documents/1` | 401 | HTTP requires login, HTTP Basic entry point |
| Viewer `GET /api/documents/1` | 403 | HTTP passes; `@PreAuthorize` blocks due to missing `DOC_READ` |
| Alice `GET /api/documents/1` | 200, JSON contains `"owner":"alice"` | Passes pre-check and post-check |
| Alice `GET /api/documents/2` | 403 | Bob's object was read, but post-check blocks returning it |
| Bob `GET /api/documents/2` | 200, JSON contains `"owner":"bob"` | Owner matches |
| Alice `GET /api/documents/99` | 404 | Method returns null, expression lets null pass, controller returns not found |

Do not pin exact JSON property ordering, response headers, or error bodies: these can vary by Jackson/Spring Boot/Spring Security versions and configuration. In the demo, `403` for Bob's document can reveal that the document exists; section 7 presents a safer query design.

### 5.4. Integration Test Verifying Both Layers of Method Security

Create `src/test/java/example/postauth/PostAuthorizeApplicationTest.java`:

```java
package example.postauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PostAuthorizeApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void httpAndMethodAuthorization() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());

        // Logged in, but lacks permission to call the method: pre-check blocks.
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("viewer", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        // Has DOC_READ, but different owner: post-check blocks.
        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));

        mvc.perform(get("/api/documents/99")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void directServiceCallStillUsesMethodProxy() {
        assertThat(service.findById(1).getOwner()).isEqualTo("alice");
        assertThatThrownBy(() -> service.findById(2))
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

Run:

```bash
./gradlew test
```

On Windows use `.\gradlew.bat test`. The first test goes through the **real HTTP/filter chain** with MockMvc, observing statuses; the second invokes the **Spring-injected service**, checking `AccessDeniedException` directly instead of mocking logic. If you simply call `new DocumentService()` and invoke methods, there is no Spring AOP interceptor, so the result proves nothing about annotation enforcement.

Lesson from the test: when Alice reads Bob's doc, the mock repository returned the object **before** `@PostAuthorize` denied it. The controller never got the value, yet a read operation still occurred. That is why protecting data earlier matters in real apps.

## 6. Why Shouldn't `@PostAuthorize` "Protect" Write Operations?

Examine this anti-pattern, **solely for risk analysis, not a runnable class**:

```java
// Design to avoid:
@PostAuthorize("returnObject.owner == authentication.name")
public Invoice approveAndReturnInvoice(long invoiceId) {
    Invoice invoice = repository.load(invoiceId);
    invoice.setStatus(APPROVED);
    repository.save(invoice);       // May have already written to DB.
    eventPublisher.publish(invoice); // May have already published event.
    return invoice;
}
```

Suppose the caller is not the owner. The post-check can deny **after** `save` and `publish` have already run. An `AccessDeniedException` cannot unsend emails, retract published events, undo external requests, or erase logs. With transactions, advice/commit/rollback ordering depends on AOP and transaction-manager configuration; **do not rely on `@Transactional` as a safe side-effect prevention mechanism**.

A better design: **read needed data → verify permission before mutating → execute conditional mutation inside a transaction**.

Illustrative **business skeleton (not standalone runnable)** using an explicit authorizer:

```java
@PreAuthorize("hasAuthority('INVOICE_APPROVE')")
@Transactional
public void approve(long id, Authentication authentication) {
    Invoice invoice = repository.findForUpdate(id)
        .orElseThrow(InvoiceNotFoundException::new);

    approvalPolicy.requireCanApprove(authentication, invoice);
    invoice.approve();

    // If using raw SQL, WHERE should include tenant/status/version.
    repository.save(invoice);
}
```

Check for race conditions/TOCTOU: permissions, membership, or state can change between steps; use transactions/locking, optimistic versioning, or conditional updates to preserve invariants. `@PreAuthorize` checks the authority before entering the method, and the object-based policy runs **before writing**. Correctness belongs to transaction and database design, not annotations alone.

**Rule:** `@PostAuthorize` makes the most sense for **read-only methods** returning a single object whose decision depends on attributes known only after querying. For writes, side-effecting commands, or streaming, enforce authorization before execution and/or via data/transaction constraints.

## 7. Authorizing at the Data Source Is Usually Better Than Post-Checking

`@PostAuthorize` is useful for learning ownership concepts or adding an extra layer of defense, yet it has three limits for sensitive data systems:

1. **Already read an unauthorized object:** data can appear in caches, traces, debuggers, logs, or pass through other components before the post-check prevents the caller from receiving it.
2. **Leaking record existence:** querying an existing ID hits post-check and returns 403, whereas a missing ID returns 404. That difference can enable ID enumeration.
3. **Wasted I/O and poor scalability:** the method loads the full object before evaluating policy; complex queries, lists, and pagination get even costlier.

In multi-tenant applications, prefer queries scoped by server-verified **tenant + owner/ACL**, for example:

```sql
SELECT id, tenant_id, owner_username, title
FROM documents
WHERE id = :id
  AND tenant_id = :authorizedTenant
  AND owner_username = :authenticatedUsername;
```

Parameters must be bound safely. `authorizedTenant` comes from verified tenant membership, not straight from a client header. If the caller lacks permission to view the record, the query returns empty; the API can return 404 per product policy while recording an appropriate audit event.

You may also need policies like "members of a group can read," "document shared with viewer," or "managers only approve within the same tenant." Simple owner checks are then insufficient: use a policy service or suitable ACL/ABAC/ReBAC, and **push expressible predicates down into the query** to protect reads, lists, counts, and exports.

Defense across layers complements one another:

```text
HTTP authentication / coarse-grained route
    → @PreAuthorize: does caller have permission to perform read?
    → Query by tenant/owner/ACL: can caller see the record?
    → @PostAuthorize: post-check object invariant if still needed
    → DTO/serialization: which fields can caller view?
```

`@PostAuthorize` is therefore a **conditional layer of defense**, not a substitute for scoped queries or data controls during updates/deletes.

## 8. When Using `hasPermission` or a Dedicated Policy Bean

Complex applications should not cram all logic into hard-to-test SpEL strings:

```java
@PostAuthorize(
    "returnObject == null || " +
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentView findOne(long id) {
    return repository.findOne(id);
}
```

This is a **structural pattern example**, requiring a `documentPolicy` bean and a `canRead(Authentication, DocumentView)` method written by the project. Moving policy into Java methods provides clear advantages: independent unit tests, logging/auditing explaining denial reasons, and reuse across query predicates and other actions.

You may also see syntax like:

```java
@PostAuthorize("hasPermission(returnObject, 'read')")
```

However, `hasPermission` relies on a `PermissionEvaluator` (or authorization integration) configured properly for your domain. It **does not automatically read an owner column or ACL list**. For nullable results, special object types, or services running without HTTP context, design explicit interpretation rules and test them.

**Do not stack ambiguous rules:** When both `@PreAuthorize` and `@PostAuthorize` are present, each annotation runs its own interceptor and both must allow access. When multiple permissions interact, prefer one readable policy over complex duplicated conditions across many classes.

## 9. AOP/Proxy Pitfalls: Annotated Yet Never Executed

A frequent bug:

```java
@Service
class DocumentService {
    public DocumentView entry(long id) {
        return findById(id); // this.findById(): self-invocation
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public DocumentView findById(long id) {
        return repository.findById(id);
    }
}
```

This is an **illustrative snippet**; `repository` is an assumed field. When `entry` calls `findById` **on the same instance**, the call can go straight to the method without passing through the Spring proxy; the `@PostAuthorize` interceptor therefore does not run under standard Spring AOP proxy mechanics. The same holds for objects constructed with `new` outside the container or methods unproxyable under the active proxy mode.

A cleaner design is having callers invoke **a Spring-injected service bean**, splitting protected use cases into separate beans if needed, and testing through the real bean in the ApplicationContext. Do not fix this by creating arbitrary manual proxies or pushing all policies up to the controller.

Diagnostic checklist:

- Is `@EnableMethodSecurity` enabled on an appropriate configuration?
- Does the method live on a Spring-managed bean rather than a manually constructed object?
- Do callers invoke through the proxy rather than `this`?
- Are method modifiers/bean types compatible with the proxy mechanism?
- Is the annotation placed on the method/class/interface as supported by Spring Security?
- Does an Authentication exist in the execution thread (HTTP, scheduled job, async, message consumer)?
- Do tests verify **a denied caller** through the real bean rather than only testing permitted callers?
- Are `@PreAuthorize`/`@PostAuthorize` applied to methods returning the type expected by the expression?

Method security does not automatically guard **unannotated** methods. You still need catch-all HTTP rules and protection on critical domain entry points.

## 10. Error Outputs and HTTP Codes: 403, 404, or 401?

In the HTTP Basic example:

- Unauthenticated call to a route requiring `authenticated()`: typically **401** with the appropriate challenge.
- Authenticated, missing `DOC_READ`: denied by `@PreAuthorize`, typically **403**.
- Authenticated, holds `DOC_READ`, but result belongs to another user: denied by `@PostAuthorize`, typically **403**.
- Authorized, no result, and expression lets null pass: controller can return **404**.

With form login/sessions, bearer JWTs, custom authentication entry points, or exception handlers, status/redirect/body behavior can differ. In **non-HTTP** flows (jobs, consumers, direct service calls), `AccessDeniedException` does not turn into an HTTP response: callers must handle it properly rather than swallowing the error and continuing business logic.

If hiding resource existence is required, choose to return **404 for out-of-scope objects** directly from the query. Do not arbitrarily distinguish 403 vs. 404 on the same policy when that lets callers enumerate IDs. Internal audit logs should capture the exact reason without leaking sensitive permission/secret details in public errors.

## 11. Reactive/WebFlux: Same Principle, Different Context

Spring Security also supports reactive method security, but you must use WebFlux/Reactor configuration and semantics:

- Servlet/MVC: `@EnableMethodSecurity`, Spring AOP method interceptors, typically using `SecurityContextHolder` in imperative flows.
- WebFlux: `@EnableReactiveMethodSecurity` (in Spring Security 6 `useAuthorizationManager = true` can be used), context tied to Reactor subscription and `ReactiveSecurityContextHolder`.
- Protected methods in reactive pipelines should return an appropriate reactive type like `Mono<T>` or `Flux<T>`; do not read the principal from an arbitrary `ThreadLocal` expecting it to survive async boundaries.
- Reactive `@PostAuthorize` can inspect emitted results per framework integration, yet details around empty publishers, multi-element publishers, cancellation, and errors must match your Spring Security version and be verified with `WebTestClient`/reactive tests.
- Non-blocking **does not eliminate** post-check caveats: reading/streaming/task execution and side effects may already have started before the policy evaluates; prefer filtering scope at the reactive repository or before emitting streams.

Conceptual configuration example (not a standalone runnable program):

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Never mix Servlet `SecurityFilterChain` with reactive `SecurityWebFilterChain`, or imperative `@EnableMethodSecurity` with a reactive stack without verifying the active web stack. Test the same ownership expression explicitly on `Mono.empty()`, `Mono.just(value)`, and another user's data if used in a reactive service.

## 12. Real-World Scenarios: When to Use vs. Avoid `@PostAuthorize`?

| Scenario | Reasonable to use `@PostAuthorize`? | Explanation |
|---|---|---|
| Read a single loaded object, owner-only view | Can be helpful | Checks result after read; consider query scoping to avoid out-of-scope reads |
| Read data with owner/tenant and complex sharing rules | Can serve as an extra layer | Should have a policy bean and DB predicates |
| Search 100,000 documents returning a List | Should not be primary filter | Post-filtering is costly and breaks pagination/counts |
| `approvePayment` modifying balance | Do not use as sole control | Mutation may already be complete when post-check denies |
| Send email or publish event | Avoid checking rights at the end | External side effects cannot be rolled back by an exception |
| Return `ResponseEntity<DocumentView>` from controller | Use with caution | `returnObject` is the wrapper, not automatically the inner DTO |
| Service with multiple callers (HTTP, job, listener) | Method security is useful | But each caller needs clear identity and context |
| Read JPA entity with lazy properties | Must test transaction/persistence context | SpEL may trigger queries or lazy-loading errors |
| Multi-tenant data | Owner-only check is insufficient | Tenant membership, ACLs, field-level rules, and query scoping are essential |
| Reactive `Mono<DocumentView>` | Usable with reactive method security | Test semantics and context for your version |

**When to use:** a read-only use case with a small result where owner/permission is known only after loading, needing an explicit post-check integrated with method security. **When to avoid:** write commands, side-effecting operations, large lists, or data that must be restricted in the query itself.

## 13. Common Mistakes When Writing Expressions

| Mistake | Consequence | Fix |
|---|---|---|
| Not enabling `@EnableMethodSecurity` | Annotations may not execute | Enable config; write negative tests through Spring bean |
| Putting only `@PostAuthorize` on write methods | Side effects can happen before denial | Authorize before mutation; protect transactions |
| `returnObject.owner` when returning null | Evaluation can error out | Check null explicitly; define 404/403 behavior |
| Comparing `returnObject.owner` to user-submitted body field | Trusts unverified input | Compare against `authentication.name` or verified identity |
| Returning `Optional/ResponseEntity` while inspecting as domain object | Wrong property type, unintended denials | Return DTO directly or handle wrapper explicitly |
| Using `hasRole('DOC_READ')` when authority is `DOC_READ` | `hasRole` expects `ROLE_DOC_READ` by default | Use `hasAuthority('DOC_READ')` for plain authorities |
| Equating post-check with a SQL filter | DB already read out-of-scope records | Scope predicates in DB; keep post-check as supplement |
| Assuming 403 for every access denied case | Authentication/entry point varies by config | Test 401/403/404 along actual flows |
| Self-invocation inside service | Can bypass proxy/interceptor | Call via Spring bean/proxy; split services |
| Filtering lists via single-object post-check | Fails to inspect elements or wastes memory | Use scoped queries and proper pagination |
| Duplicating complex SpEL everywhere | Policy drift, hard to audit/test | Use an authorizer bean with a clean API |
| Not testing after changing DTOs | Property names in SpEL may change/disappear | Regression test both allow and deny cases |

## 14. Code Review Checklist and Self-Check Exercises

### Checklist

- [ ] Distinguished action-level rights before method execution from object-level rights after returning.
- [ ] `@EnableMethodSecurity` is enabled; method is invoked via a Spring-managed proxy.
- [ ] `returnObject` matches the actual return type; null/Optional/wrapper cases are handled intentionally.
- [ ] SpEL properties are accessible and do not trigger unwanted lazy queries.
- [ ] Expressions use trusted principal/tenant values; never read privilege info from self-declared input.
- [ ] Never rely on `@PostAuthorize` as the sole gate before mutations, event publishing, or side-effecting I/O.
- [ ] When out-of-scope reads must be prevented, queries include tenant/owner/ACL predicates.
- [ ] Tested separately: anonymous 401, missing authority 403, wrong owner 403/404 per policy, matching owner 200, missing record 404.
- [ ] Tested directly via Spring-injected service, not only mocked controllers.
- [ ] Evaluated 403 vs. 404, large lists, field-level visibility, and cache/logging impact.
- [ ] For reactive code, verified Reactor Context, Publisher types, and version-specific tests.

### Exercises

1. In the example, Alice has `DOC_READ` and reads `id=2`. **Does the method run?** Yes: `@PreAuthorize` allows it, `findById` creates `DocumentView(owner="bob")`, and then `@PostAuthorize` denies it.
2. Viewer reads `id=1`. **Does the method run?** No: missing `DOC_READ`, so `@PreAuthorize` blocks beforehand.
3. Alice reads `id=99`. **Why does she get 404?** `findById` returns null, the expression lets null pass, and the controller converts it to `notFound()`. Removing the null branch changes behavior and must be tested.
4. Is changing `@PostAuthorize` to `@PreAuthorize("returnObject.owner == authentication.name")` valid? No: **before** the method runs, there is no return object to evaluate.
5. To return 404 for both non-existent documents and documents not owned by Alice, where should that be designed? Prefer a **scoped query** so both return empty; do not merely alter error messages after post-check.
6. If calling `this.findById(2)` from another method in the same bean, is the annotation guaranteed to protect it? No, you cannot rely on that under default Spring proxies; refactor the call through a bean and test.
7. If a user has read permission but the document contains a secret field, does `@PostAuthorize` strip the secret field automatically? No. You need dedicated projections/DTOs or field-level authorization.

## 15. Official Documentation

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `returnObject`, proxies, and how before/after interceptors run.
- [Spring Security — Authorizing HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP route protection complementing method security.
- [Spring Security — Method Security Test](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` and testing method authorization.
- [Spring Security — MockMvc Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): verifying 401/403/200 responses against real endpoints.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context-based method security.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation limitations and how AOP proxies work.

The sample lesson uses Spring Boot 3.x / Spring Security 6.x and Java 17+. Verify dependencies/APIs against your real application version and replace demo passwords with proper credential management.
