# `@PostAuthorize` and Decisions Based on `returnObject` in Spring Security

> **Topic:** Spring Security — **Post-Method Authorization Checks**. This lesson explains how `@PostAuthorize` controls **the result that a Spring-managed method is about to return**, the role of the SpEL variable `returnObject`, its relationship with `@PreAuthorize`, ownership handling (owner), null/404 errors, side effect risks, how to test, and limitations when used for real-world APIs. Examples use **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x** with Spring MVC/Servlet.

## 1. The core question: the object has been read, should it be returned to the caller?

Suppose a method returns a document:

~~~java
public Document readDocument(String id) {
    return repository.findById(id);
}
~~~

Two people can both log in and both be allowed to call the “read document” feature, yet that does **not** mean person A is allowed to receive data belonging to person B.

For example:

| Caller | Document | Owner | Return decision |
| --- | --- | --- | --- |
| Alice | A-1 | Alice | ALLOW |
| Alice | B-1 | Bob | DENY |
| Bob | B-1 | Bob | ALLOW |
| Bob | A-1 | Alice | DENY |

If we only use `@PreAuthorize("isAuthenticated()")` or HTTP `authenticated()`, we have not yet enforced the ownership rule. One way to express this in method security is:

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document readDocument(String id) {
    return repository.load(id);
}
~~~

This is a **Spring fragment**, not independently runnable; it requires `Document` with an `owner` property, a real `repository`, and method security configuration.

**Meaning:** the method is invoked to create/load a `Document`; afterward Spring Security evaluates the SpEL expression. If `Document.owner` matches the caller's identity, the result **is returned**. If it does not match, Spring Security **denies returning the result** and typically throws `AccessDeniedException` (or an appropriate derived exception such as `AuthorizationDeniedException`).

**Key point to remember:** `@PostAuthorize` is a **post-check**. It does not prevent the target method from having executed; it prevents **returning the result** if the policy is not satisfied.

## 2. Enabling `@PostAuthorize` with `@EnableMethodSecurity`

`@PostAuthorize` belongs to the **pre/post method security** group. This group is enabled by default when you have:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` can be placed on the `@SpringBootApplication` main class instead of a separate configuration class. Spring Boot Starter Security **does not automatically enable method-level authorization** if the corresponding configuration is not present.

### 2.1. Which annotations are enabled?

| Annotation | Processing point | Default in `@EnableMethodSecurity` |
| --- | --- | --- |
| `@PreAuthorize` | Before the target method runs | Enabled |
| `@PostAuthorize` | After the target returns a result | Enabled |
| `@PreFilter` | Filters input collection | Enabled |
| `@PostFilter` | Filters output collection | Enabled |
| `@Secured` | Checks role/authority before method | Requires `securedEnabled = true` |
| `@RolesAllowed` | Checks JSR-250 role | Requires `jsr250Enabled = true` |

`@EnableMethodSecurity(prePostEnabled = false)` will also disable `@PostAuthorize` in the default group. Do not set this flag just because you want to “remove an unused annotation”; it can cause already-written policies to **no longer be checked**.

### 2.2. Imports and annotation placement

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document read(String id) {
        // ...
        return null;
    }
}
~~~

This is an **annotation illustration fragment only** (not a usable implementation: the method returns null). The full application in section 9 uses real in-memory data, does not return null, and includes tests.

Protection should be placed at the **service layer** so the same policy is enforced when the service is called from multiple controllers or other beans. Controllers can still have their own guards, but should not be treated as the sole boundary.

## 3. Lifecycle of a call with `@PostAuthorize`

When the Spring AOP proxy receives a call:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |-- authentication / HTTP authorization
    |-- DENY -> 401 or 403 depending on context
    v
Controller
    |
    v
Spring proxy of DocumentService
    |
    +-- @PreAuthorize (if present)
    |       |-- DENY -> DO NOT run target method
    |       v ALLOW
    +-- target method executes
    |       +-- reads data, may produce side effects
    |       +-- returns Document
    v
@PostAuthorize
    |-- SpEL reads returnObject + Authentication
    |-- DENY -> AccessDeniedException (does not return Document)
    v ALLOW
Controller / serializer -> HTTP response
~~~

The diagram emphasizes the **timing of the check**; the actual filter chain/interceptors may contain many other components.

Spring Security 6.5 uses `AuthorizationManagerAfterMethodInterceptor` for `@PostAuthorize` and `PostAuthorizeAuthorizationManager` to evaluate the expression. `returnObject` represents **the object that the target method returned**, not the request body, not an input parameter, and not the JSON after serialization.

**Important takeaway from the diagram:** when Alice reads B-1, the target method **already retrieved B-1 into the JVM**, but the post-check denies returning that object through the proxied call. This is a leak-prevention mechanism at the boundary, but it does not prove that the method caused no prior effects.

## 4. What is `returnObject` in SpEL?

### 4.1. Comparing with the authenticated principal

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document find(String id) {
    return repository.load(id);
}
~~~

SpEL evaluates as follows:

1. `returnObject`: the `Document` object just returned by the method.
2. `returnObject.owner`: the `owner` property accessed by Spring Expression Language (e.g., getter `getOwner()`).
3. `authentication`: the current `Authentication` from `SecurityContext`.
4. `authentication.name`: the authenticated username, independent of any username value filled in by the client in the URL.
5. `==`: compares the two values according to SpEL semantics, determining ALLOW/DENY.

With a POJO:

~~~java
public class Document {
    private final String id;
    private final String owner;

    public Document(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() { return id; }
    public String getOwner() { return owner; }
}
~~~

This is a **standalone runnable POJO class**, whereas the previous annotation snippet requires Spring. The `getOwner()` getter helps SpEL/Jackson recognize the `owner` property. Avoid relying on private field names without verifying property access behavior in your actual configuration.

### 4.2. Checking owner or granting access to someone with audit permission

A business policy can allow the owner to read the document and allow an auditor to read it for auditing purposes:

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name or hasAuthority('document:audit')"
)
public Document read(String id) {
    return repository.load(id);
}
~~~

**Explanation:** an authenticated user can receive the result when they are the owner **or** have the literal authority `document:audit`. There is no need to assume `ROLE_ADMIN` automatically has every permission. Audit permission is an **explicitly granted** policy exception, which must have a business justification and appropriate logging/auditing.

Once an expression starts accessing properties of `returnObject`, you must pay attention to null values, the return type, and whether the owner field is trustworthy.

### 4.3. Combining with `@PreAuthorize`

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject.owner == authentication.name or hasAuthority('document:audit')"
)
public Document read(String id) {
    return repository.load(id);
}
~~~

The two annotations create **two independent checks**:

- **Pre-step:** lacking `document:read` → not allowed to execute the method.
- **Post-step:** even with `document:read`, only allowed to receive the result if owner or having `document:audit`.

This does not mean `@PostAuthorize` can “re-grant permission” to a user already denied by `@PreAuthorize`. A DENY at the pre-check stops before there is any `returnObject` to evaluate.

### 4.4. Checking additional properties of the return value

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name and returnObject.status == 'ACTIVE'"
)
public Document readActive(String id) {
    return repository.load(id);
}
~~~

This is a **fragment** requiring `Document` to have a `status` property and a real repository. The condition here ensures only the owner receives a document in the ACTIVE state. Do not assume this expression automatically checks tenant or all other governance rules.

## 5. Null values, Optional, and exceptions: don't write fragile SpEL

### 5.1. When a method can return null

The expression:

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
~~~

is unsafe if the method sometimes returns `null`: accessing `owner` can cause an expression evaluation error. You should clearly decide what “not found” means:

- If not found is a business error, **throw an appropriate exception** in the target method (for example HTTP 404 in the demo web/service layer) instead of returning null.
- If returning null is mandatory, the expression needs an explicit null guard, and you must agree on whether **null is ALLOW or DENY**.
- If the requirement is not to disclose whether a resource exists, an appropriate 403/404 policy and guarded lookup are needed, rather than simply throwing 404 based on ID.

Example **disallowing null**:

~~~java
@PostAuthorize(
    "returnObject != null and returnObject.owner == authentication.name"
)
public Document nullableRead(String id) {
    return repository.findOrNull(id);
}
~~~

This is a fragment; do not use it if the controller contract expects null to be represented as 404. `and` skips accessing `owner` when `returnObject` is null, and decides DENY for null.

Example **accepting null because there is no data**:

~~~java
@PostAuthorize(
    "returnObject == null or returnObject.owner == authentication.name"
)
public Document optionalLikeRead(String id) {
    return repository.findOrNull(id);
}
~~~

This is also a fragment. ALLOWing null does **not** mean data access is permitted; it only allows an absent result. However, 404/204 behavior when receiving null must be designed by the API layer and tested.

### 5.2. `Optional<Document>` is not `Document`

If a method returns `Optional<Document>`, `returnObject` is normally the **Optional wrapper**, not the object contained inside. Therefore:

~~~java
// INCORRECT if the method returns Optional<Document>:
@PostAuthorize("returnObject.owner == authentication.name")
~~~

is not the way to check the owner of the `Document` inside the Optional. You need to design a policy expression/bean that checks `isPresent`, handles `empty`, or switch to a “throw exception if not found” contract and return `Document` directly. Example using an explicit policy bean:

~~~java
// Fragment: the documentPolicy bean must be implemented by the application.
@PostAuthorize("@documentPolicy.mayReceive(authentication, returnObject)")
public Optional<Document> findOptional(String id) {
    return repository.findOptional(id);
}
~~~

This is a **fragment**, not a built-in API named `documentPolicy`. The bean must accept the exact type `Optional<Document>`, check `isPresent()` before `get()`, evaluate owner/tenant, and decide the empty result as agreed.

### 5.3. Exceptions when the target method does not return normally

If the method throws an exception (such as `DocumentNotFoundException` or `ResponseStatusException(404)`) **before returning**, the normal post-check interceptor **has no normal returnObject result to evaluate**. `@PostAuthorize` cannot be treated as the default security mechanism for all error branches.

This matters if the response is 403 for a document that exists but does not belong to the user, versus 404 for a non-existent ID; distinguishing them can leak the existence of IDs. You must clearly determine whether the API should use 403, a “hide resource” 404, or a single intentional response, matching the threat model and consistent on real data.

## 6. Important limitations of post-checks

### 6.1. Post-checks do not roll back all side effects

Consider the following code:

~~~java
// DO NOT use as the sole barrier for write operations:
@PostAuthorize("returnObject.owner == authentication.name")
public Document changeOwner(String id, String newOwner) {
    Document document = repository.load(id);
    document.setOwner(newOwner);
    repository.save(document); // DB write may have already occurred!
    return document;
}
~~~

This is an **anti-pattern**. If Spring denies after the method has already written to the DB, we cannot assume side effects have been rolled back. The proxy advice ordering of `@Transactional` and `@PostAuthorize` can affect transaction timing; changing bean/advisor ordering is not a simple fix for all external side effects such as messages, emails, payments, or caches.

The Spring Security documentation **does not recommend `@PostAuthorize` as the primary barrier in database-writing code**. A better approach is to check permissions **before mutating** and combine with domain constraints:

~~~java
// Illustrative fragment: requires documentPolicy bean and real repository.
@PreAuthorize("@documentPolicy.canModify(authentication, #id)")
@Transactional
public void rename(String id, String title) {
    Document document = repository.loadForUpdate(id);
    document.rename(title);
    repository.save(document);
}
~~~

The goal of the fragment is the order of **checking permissions before the write operation**, not an absolute safety guarantee: you must avoid time-of-check/time-of-use races, check tenant/owner inside an appropriate transaction, and handle concurrently changing resource states. For financial/sensitive actions, auditing and domain-level idempotency/authorization mechanisms remain critical.

### 6.2. Post-checks for reads are not always free of side effects either

A query may write an access log, create a cache entry, increment a counter, emit an event, or load sensitive data into memory. If the post-check DENYs, those side effects **may have already occurred**; you should not rely on a 403 response to assert that nothing was touched.

Post-checks are useful when you need to inspect an object's properties to decide whether to allow/disallow **returning the result**, yet you should still scope the initial query by tenant/scope whenever possible.

### 6.3. Does not replace object-, tenant-, or field-level policies

`returnObject.owner == authentication.name` is just one condition:

- It does not determine which tenant the resource belongs to.
- It does not prove the owner still holds permission after revocation.
- It does not prevent leaks from logs/events created inside the method.
- It does not grant permission on individual data fields (e.g., an account number might only be partially viewable).
- It does not ensure pagination/list filtering at the database layer.

In larger systems, domain-level checks must be combined with scoped queries and condition checks at the time of execution.

## 7. Comparison with related annotations

| Mechanism | Input compared | Timing | Outcome when failed |
| --- | --- | --- | --- |
| `@PreAuthorize` | Authentication, method parameters, bean policy | **Before** target method | Usually DENY entire call |
| `@PostAuthorize` | Authentication, **returnObject** after method runs | **After** target method | Usually DENY **entire result** |
| `@PreFilter` | Elements of **input** collection | Before target method | Removes failing elements |
| `@PostFilter` | Elements of **output** collection | After target method | Removes failing elements |
| `@AuthorizeReturnObject` | Proxy on returned object/nested methods | When object or getter is used | Can protect individual members via annotations |

### 7.1. How does `@PostAuthorize` differ from `@PostFilter`?

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document getOne(String id) { /* returns a Document */ }

@PostFilter("filterObject.owner == authentication.name")
public List<Document> getSome() { /* returns a collection */ }
~~~

This is a **conceptual fragment**, not standalone code. With `getOne`, if the object does not belong to the caller, **the entire call is denied**. With `getSome`, Spring can **filter out non-matching elements** from the returned collection, without necessarily denying the entire call.

With large datasets, `@PostFilter` after loading does not replace a `WHERE tenant_id = ... AND ...` query in the database. If the list is paginated first and filtered afterward, page counts and page boundaries can also become confusing or leak metadata.

### 7.2. `@AuthorizeReturnObject` is a different mechanism

In Spring Security 6.5, `@AuthorizeReturnObject` can request proxying a returned object so that methods/properties on that object carry their own protection annotations. Unlike `@PostAuthorize`: the latter decides **whether to return the whole method result or not**, whereas the return-value proxying mechanism can check **operations on the returned object**.

There is no need to introduce `@AuthorizeReturnObject` in basic examples if you only need to return or deny a `Document`. If you use it, you must pay attention to nested types, serialization, final/value types, and AOT hints according to the running version.

### 7.3. `@HandleAuthorizationDenied` changes denial behavior

Spring Security 6.5 supports `@HandleAuthorizationDenied` and `MethodAuthorizationDeniedHandler` to customize what value is returned when method authorization is denied, such as returning null or masking information in a controlled way. This is an **extension mechanism**, not enabled by default for all `@PostAuthorize` annotations. Returning a denied object inadvertently is a vulnerability; extra care is required with masking/partial responses.

In this lesson, examples use the default DENY behavior to analyze 403 clearly.

## 8. Standalone Java 17: simulating before and after reading

To firmly grasp the order, run a Java 17 example **without Spring**. It intentionally returns transparent strings “DENY:pre” and “DENY:post”; real Spring Security HTTP does not return these strings by default.

Create the file **`PostAuthorizeFlowDemo.java`**:

~~~java
import java.util.Map;

public class PostAuthorizeFlowDemo {

    record Document(String id, String owner) {}

    private static final Map<String, Document> DOCUMENTS = Map.of(
        "A-1", new Document("A-1", "alice"),
        "B-1", new Document("B-1", "bob")
    );

    static String read(
            String username,
            boolean hasReadPermission,
            boolean auditor,
            String id
    ) {
        // Simulate @PreAuthorize.
        if (!hasReadPermission) {
            return "DENY:pre";
        }

        // Target method has executed the read.
        Document result = DOCUMENTS.get(id);
        if (result == null) {
            return "NOT_FOUND";
        }

        // Simulate @PostAuthorize on returnObject.
        if (!username.equals(result.owner()) && !auditor) {
            return "DENY:post";
        }
        return "ALLOW:" + result.id();
    }

    public static void main(String[] args) {
        System.out.println("alice->A-1: "
            + read("alice", true, false, "A-1"));
        System.out.println("alice->B-1: "
            + read("alice", true, false, "B-1"));
        System.out.println("bob->B-1: "
            + read("bob", true, false, "B-1"));
        System.out.println("auditor->B-1: "
            + read("auditor", true, true, "B-1"));
        System.out.println("guest->A-1: "
            + read("guest", false, false, "A-1"));
        System.out.println("alice->X-9: "
            + read("alice", true, false, "X-9"));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac PostAuthorizeFlowDemo.java
java PostAuthorizeFlowDemo
~~~

**Deterministic stdout of the program:**

~~~text
alice->A-1: ALLOW:A-1
alice->B-1: DENY:post
bob->B-1: ALLOW:B-1
auditor->B-1: ALLOW:B-1
guest->A-1: DENY:pre
alice->X-9: NOT_FOUND
~~~

Meaning:

- `guest` is denied **before** looking up the document map.
- Alice queries B-1 and looks up the document, but the post-check prevents receiving the result.
- Auditor is allowed to read B-1 thanks to an explicit permission in the simulated policy.
- A non-existent document is handled as a separate error branch, not automatically becoming ALLOW or DENY based on owner.

This example **simulates logic**, not Spring AOP, SpEL, or HTTP exception translation. The next section uses real Spring Security.

## 9. Complete Java 17+ Spring Boot application

### 9.1. Application functionality

A document API has two records:

| ID | Owner | Title |
| --- | --- | --- |
| `A-1` | `alice` | `Plan A` |
| `B-1` | `bob` | `Plan B` |

Accounts:

| Principal | Direct GrantedAuthority |
| --- | --- |
| `alice` | `document:read` |
| `bob` | `document:read` |
| `auditor` | `document:read`, `document:audit` |
| `charlie` | `ROLE_USER` |

Endpoints:

- `GET /public/ping`: public.
- `GET /api/documents/{id}`: requires authentication at HTTP, requires `document:read` at `@PreAuthorize`, and requires **owner or document:audit** at `@PostAuthorize`.
- `GET /api/unlisted`: even though a controller exists, HTTP `denyAll()` still blocks it.
- `GET /api/documents/X-9`: illustrates **404 when the document does not exist**, if the pre-check has passed.

The example only uses **GET**, so default CSRF does not interfere with the 403 cases (CSRF mainly applies to write methods like POST/PUT/PATCH/DELETE). Demo passwords must not be used in production.

### 9.2. Maven project

Create a Spring Boot **3.5.x** project with Java **17+**, dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (test scope)
- `spring-security-test` (test scope)

Use Spring Boot's dependency management; do not manually pick an incompatible combination of Spring Framework/Security versions.

### 9.3. Complete application code

Create the file **`src/main/java/com/example/postauth/PostAuthApplication.java`**:

~~~java
package com.example.postauth;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(PostAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("document:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("document:read")
            .build();

        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("demo789"))
            .authorities("document:read", "document:audit")
            .build();

        UserDetails charlie = User.withUsername("charlie")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, auditor, charlie
        );
    }

    public static class Document {
        private final String id;
        private final String owner;
        private final String title;

        public Document(String id, String owner, String title) {
            this.id = id;
            this.owner = owner;
            this.title = title;
        }

        public String getId() { return id; }
        public String getOwner() { return owner; }
        public String getTitle() { return title; }
    }

    @Service
    public static class DocumentService {
        private final Map<String, Document> documents = Map.of(
            "A-1", new Document("A-1", "alice", "Plan A"),
            "B-1", new Document("B-1", "bob", "Plan B")
        );

        // Only for tests proving the method ran before the post-check.
        private final AtomicInteger readCount = new AtomicInteger();

        @PreAuthorize("hasAuthority('document:read')")
        @PostAuthorize(
            "returnObject.owner == authentication.name or "
          + "hasAuthority('document:audit')"
        )
        public Document read(String id) {
            Document result = documents.get(id);
            if (result == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                );
            }

            readCount.incrementAndGet();
            return result;
        }

        public int getReadCount() {
            return readCount.get();
        }
    }

    @RestController
    static class Api {
        private final DocumentService service;

        Api(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/documents/{id}")
        Document document(@PathVariable("id") String id) {
            return service.read(id);
        }

        @GetMapping("/api/unlisted")
        String unlisted() {
            return "must not be returned";
        }
    }
}
~~~

### 9.4. Code analysis in exact protection order

**HTTP layer:** `GET /api/documents/{id}` requires an authenticated identity. If an anonymous user sends a request, HTTP Basic normally returns `401`. `/api/unlisted` is blocked by `anyRequest().denyAll()`, regardless of role.

**Pre-method layer:** `@PreAuthorize("hasAuthority('document:read')")` blocks Charlie (who only has `ROLE_USER`) **before the document is read**. Being logged in does not mean having business permission.

**Post-method layer:** when Alice reads `B-1`, the method finds `Document(owner="bob")` and increments the read counter, but `@PostAuthorize` denies returning the object. Auditor can view Alice's/Bob's documents thanks to `document:audit`, **not** thanks to an implied ADMIN role.

**Non-existent document:** the service throws `ResponseStatusException(404)` before a normal return result exists. That branch is not a `@PostAuthorize` ALLOW. In a real API, the 403/404 policy should be designed so as not to leak other people's document IDs.

**Read counter:** only serves to illustrate that the target method **did execute** when denied by the post-check. In production, avoid unnecessary side effects before authorization and do not use this counter as security data.

## 10. ALLOW and DENY verification matrix

With the same HTTP GET method:

| Request | Anonymous | Alice | Bob | Auditor | Charlie |
| --- | :---: | :---: | :---: | :---: | :---: |
| `GET /public/ping` | **200** | **200** | **200** | **200** | **200** |
| `GET /api/documents/A-1` | 401 | **200** | 403 | **200** | 403 |
| `GET /api/documents/B-1` | 401 | 403 | **200** | **200** | 403 |
| `GET /api/documents/X-9` | 401 | **404** | **404** | **404** | 403 |
| `GET /api/unlisted` | 401* | 403 | 403 | 403 | 403 |

`*` For anonymous and `denyAll()` in the sample HTTP Basic configuration, the result is typically `401` due to the authentication entry point. An authenticated user receiving `403` is a DENY result at HTTP authorization. A different `AuthenticationEntryPoint`/filter configuration may change the status; this is **expected for the demo application**.

**Looking at the key cases:**

- Alice A-1 **200**, Alice B-1 **403**: the expression relies on the real **returnObject.owner**, not just URL parameters.
- Bob B-1 **200**, Bob A-1 **403**: same rule for another principal.
- Auditor A-1/B-1 **200**: the OR branch `hasAuthority('document:audit')` is verified.
- Charlie A-1/B-1 **403**: missing `document:read`, so blocked before target.
- Alice/Bob/Auditor X-9 **404**: method throws not-found; no return object to post-check.
- Any authenticated user hitting unlisted **403**: HTTP fallback denial.

### Body for the allowed case

`GET /api/documents/A-1` with Alice returns JSON similar to:

~~~json
{
  "id": "A-1",
  "owner": "alice",
  "title": "Plan A"
}
~~~

This is the expected body serialized by controller/Jackson for the `Document` class, not a string generated by `@PostAuthorize`. If denied, that document JSON **is not returned** to the caller via the proxied call path.

## 11. Manual testing with curl

At the root of the Maven project:

~~~bash
# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt:
mvnw.cmd spring-boot:run
~~~

Once the app is running at `http://localhost:8080`:

~~~bash
# Public and anonymous:
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/A-1

# Owner has permission to receive the result:
curl -i -u alice:demo123 http://localhost:8080/api/documents/A-1
curl -i -u bob:demo456 http://localhost:8080/api/documents/B-1

# User has document:read but is not the owner:
curl -i -u alice:demo123 http://localhost:8080/api/documents/B-1
curl -i -u bob:demo456 http://localhost:8080/api/documents/A-1

# Auditor allowed via OR policy:
curl -i -u auditor:demo789 http://localhost:8080/api/documents/B-1

# Charlie is authenticated but lacks document:read:
curl -i -u charlie:demo000 http://localhost:8080/api/documents/A-1

# Document does not exist / URL has no policy:
curl -i -u alice:demo123 http://localhost:8080/api/documents/X-9
curl -i -u auditor:demo789 http://localhost:8080/api/unlisted
~~~

The expected codes respectively include 200, 401, 403, 404 as in the matrix. Do not hard-compare “Forbidden” body text across environments because exception handlers/error controllers may customize formatting. Do not use Basic credentials over unencrypted HTTP in production; real environments must use HTTPS and trusted user/authority sources.

## 12. Writing the MockMvc + Spring Security Test suite

### 12.1. Testing dependencies

In `pom.xml` you need:

~~~xml
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
~~~

This is a fragment inside `<dependencies>` of the Maven POM. If the project already has `spring-boot-starter-test`, do not add a duplicate. Spring Boot manages dependency versions to align with Spring Security.

### 12.2. Complete test class

Create the file **`src/test/java/com/example/postauth/PostAuthApplicationTests.java`**:

~~~java
package com.example.postauth;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PostAuthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PostAuthApplication.DocumentService service;

    @ParameterizedTest
    @CsvSource({
        // username,password,path,expectedStatus
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/documents/A-1,401",
        "anonymous,none,/api/unlisted,401",

        "alice,demo123,/api/documents/A-1,200",
        "alice,demo123,/api/documents/B-1,403",
        "alice,demo123,/api/documents/X-9,404",
        "alice,demo123,/api/unlisted,403",

        "bob,demo456,/api/documents/B-1,200",
        "bob,demo456,/api/documents/A-1,403",
        "bob,demo456,/api/documents/X-9,404",

        "auditor,demo789,/api/documents/A-1,200",
        "auditor,demo789,/api/documents/B-1,200",
        "auditor,demo789,/api/documents/X-9,404",
        "auditor,demo789,/api/unlisted,403",

        "charlie,demo000,/api/documents/A-1,403",
        "charlie,demo000,/api/documents/B-1,403",
        "charlie,demo000,/api/documents/X-9,403"
    })
    void httpAuthorizationMatrix(
            String username, String password,
            String path, int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }
        mvc.perform(request).andExpect(status().is(expectedStatus));
    }

    @Test
    void ownerReceivesDocumentJson() throws Exception {
        mvc.perform(get("/api/documents/A-1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("A-1"))
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.title").value("Plan A"));
    }

    @Test
    void nonOwnerCannotReceiveDocument() throws Exception {
        mvc.perform(get("/api/documents/B-1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadAcrossOwners() throws Exception {
        mvc.perform(get("/api/documents/B-1")
                .with(httpBasic("auditor", "demo789")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/documents/A-1")
                .with(httpBasic("alice", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void postDenyHappensAfterTargetMethodRan() {
        int before = service.getReadCount();

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("B-1")
        );

        // Read B-1 but did not return it to the caller.
        assertEquals(before + 1, service.getReadCount());
    }

    @Test
    @WithMockUser(username = "charlie", authorities = "ROLE_USER")
    void preDenyHappensBeforeTargetMethodRan() {
        int before = service.getReadCount();

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("A-1")
        );

        // Missing document:read, target method did not run.
        assertEquals(before, service.getReadCount());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void directlyCallingSpringBeanEnforcesPostAuthorize() {
        PostAuthApplication.Document doc = service.read("B-1");
        assertEquals("B-1", doc.getId());

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("A-1")
        );
    }
}
~~~

**A note about the tests:** the `org.junit.jupiter.api.Assertions` import in the example is not needed directly because static imports are used; it can be removed to clean up IDE warnings. Test cases can run independently in standard Maven/JUnit execution; if **parallel test execution** is enabled and tests share the same bean counter, separate synchronization/test design is required to avoid flaky results.

### 12.3. Why are there two layers of tests?

**MockMvc + `httpBasic`** tests the entire flow HTTP → Authentication → HTTP rule → method proxy → JSON/status. The 200/403/404 tests distinguish owner, auditor, missing document, and default deny.

**`@WithMockUser` + direct Spring bean calls** test the method independently of the controller and allow measuring `readCount`:

- Alice has `document:read` and reads B-1: counter **increments by 1**, then `AccessDeniedException` → proves the post-check executes after the target ran.
- Charlie lacks `document:read`: counter **does not increment** → proves the pre-check blocks before the target runs.
- Bob reading B-1 receives the Document; reading A-1 throws an exception.

A critical condition is that `service` must be **injected from the Spring ApplicationContext**. If you instantiate `new DocumentService()`, calls do not go through the Spring AOP proxy and `@PostAuthorize` has no chance to check; such a test does not prove security.

### 12.4. Running the tests

~~~bash
# Linux/macOS:
./mvnw test

# Windows:
mvnw.cmd test
~~~

All cases are expected to pass in a project with the proper dependencies and no other custom security/exception handlers. **Do not fabricate test logs**: actual results, exit codes, and JUnit/Maven reports are what confirm the application works.

## 13. Scenarios beyond the example: APIs returning collections, multiple roles, and complex data

### 13.1. When a method returns a List

`@PostAuthorize` makes one decision for **the entire return value**. If you want “a list containing only the caller's documents”, there are two strategies:

1. Prefer querying data with tenant/owner constraints **directly in the repository**, e.g., a condition `owner_id = current_user_id`.
2. For small collections and appropriate purposes, use `@PostFilter("filterObject.owner == authentication.name")` to remove non-matching elements.

Do not use `@PostAuthorize("returnObject.owner == ...")` on `List<Document>` as if the list had an owner property. If you want a policy “caller may only receive the whole list if every element is valid”, write an appropriate expression/authorization bean and test empty lists, mixed lists, and null.

### 13.2. When a method returns a DTO instead of an entity

If the method returns `DocumentDto(id, owner, title)`, the expression must point to the property **of the DTO actually returned**, not an entity that disappeared before reaching the post-check. Ensure `owner` in the DTO comes from trusted server data, not taken from a client-submitted request.

Also guard against out-of-scope data being logged or cached during DTO mapping. Returning a DTO does not automatically make the system secure if the permission field is computed incorrectly.

### 13.3. Deeply nested owner fields

For example:

~~~java
@PostAuthorize(
    "returnObject != null and returnObject.project != null "
  + "and returnObject.project.tenantId == authentication.name"
)
public Document readInTenant(String id) {
    return repository.load(id);
}
~~~

This is only a **fragment**; it requires the corresponding `project`/`tenantId` model. Do not use `authentication.name` as a tenant ID in production if the principal is a username while tenant is a separate concept. When a policy has multiple conditions, move it to a bean `@documentPolicy.canRead(authentication, returnObject)` for clear Java testing and strict null control.

### 13.4. When using role hierarchy

If Spring Security is configured with `RoleHierarchy`, a `hasRole(...)` expression in `@PostAuthorize` can use the corresponding reachable authorities when the expression handler applies the hierarchy. However, **do not automatically infer** that a high role has permission to read all documents: combine owner, tenant, and audit permissions according to the real policy.

### 13.5. When using Spring Security Reactive

This lesson uses **Servlet/Spring MVC and Spring AOP**. With WebFlux/Reactor, returning `Mono`/`Flux` and the reactive context differ; you must read the reactive method security documentation to handle subscription timing, publisher values, and authorization. Do not copy MockMvc/Servlet tests and assume they verify reactive behavior.

## 14. Common implementation mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing `@PostAuthorize` without enabling `@EnableMethodSecurity` | Annotation is not checked | Enable method security and test DENY |
| Treating `returnObject` as request body or input parameter | SpEL checks the wrong object | Use the exact return value type |
| Using `returnObject.owner` when the method returns null | Expression can fail | Decide null/404 contract and add guard |
| Using `returnObject.owner` when the method returns Optional/List | Wrong return value structure | Use wrapper policy or filtering |
| Comparing owner against an ID self-declared by the client as “me” | Easily spoofed | Use `authentication.name`/server-side identity |
| Using only `@PostAuthorize` on write commands | Side effect already occurred before DENY | Pre-check + domain policy before writing |
| Trusting `@Transactional` to always roll back post-check DENY | Depends on advisor/transaction timing | Verify transaction design and test side effects |
| Reading the whole tenant before post-checking | Risk of data/cache leak and wasted cost | Scoped queries, least privilege |
| Using `@PostAuthorize` instead of `@PostFilter` for lists | Entire list DENYed or SpEL error | Choose mechanism per contract |
| Calling `this.read(...)` within the same service | May bypass proxy | Call through injected Spring bean |
| Instantiating service with `new` | Not protected by Spring AOP | Use bean from context |
| Placing annotation on non-interceptable method | Policy does not run | Check proxy/interface/final/private |
| Relying on HTTP `authenticated()` alone to protect document IDs | Users read others' data | Add owner/tenant checks |
| Not testing anonymous/wrong password | Confuses authentication with authorization | Add 401 tests |
| Not testing documents not owned by caller | Fails to catch IDOR | Add 403 negative tests |
| Mistaking CSRF 403 on POST for post-check denial | Debugging the wrong layer | Separate CSRF and method security |
| Returning 404 for missing ID, 403 for existing ID not owned by user unintentionally | Leaks resource existence | Design responses per threat model |
| Giving auditor overly broad permissions | Reads data beyond purpose | Grant scoped audit permission, log/audit |

### Pre-production deployment checklist

1. Is the method called through a Spring-managed proxy and is `@EnableMethodSecurity` active?
2. What type is `returnObject`: POJO, DTO, null, Optional, or List?
3. Are owner/tenant based on trusted server data and real identity?
4. Is there `@PreAuthorize` or an early permission check to reduce the risk of loading unnecessary data?
5. If the target method has side effects, is there a **pre-write** policy and transactional/domain check?
6. Are HTTP 401, method 403, CSRF 403, and domain 404 separated properly in tests?
7. Are owner ALLOW, non-owner DENY, auditor access, null/not-found, and default deny all tested?
8. If multi-tenant/list/search is supported, are queries filtered by data scope?
9. Do you avoid logging sensitive data when the post-check denies?
10. If replacing SpEL with a custom bean or custom annotation, are there direct bean tests and proxy integration tests?

## 15. Self-check questions

**Q1.** What is `returnObject` in `@PostAuthorize`?  
**Answer:** The value the target method has returned, being evaluated for whether it may be delivered to the caller.

**Q2.** Does `@PostAuthorize` run before or after the target method?  
**Answer:** After the method returns a normal result.

**Q3.** Why does Alice, who has `document:read`, still get 403 when reading B-1?  
**Answer:** `@PreAuthorize` allows calling the method, but `returnObject.owner` is Bob; Alice lacks `document:audit`, so the post-check DENYs.

**Q4.** Why is Auditor allowed to read B-1?  
**Answer:** Because the explicit policy allows the `hasAuthority('document:audit')` branch, not because “auditor is always admin”.

**Q5.** Should `@PostAuthorize` be attached as the sole authorization check for a money transfer or record deletion method?  
**Answer:** No, because the operation may already have executed before the post-check denies.

**Q6.** Can `@PostAuthorize("returnObject.owner == ...")` be used directly when a method returns `Optional<Document>`?  
**Answer:** It should not: `returnObject` is the Optional wrapper; you need a policy accepting that exact type or change the return contract.

**Q7.** Why does null need to be handled explicitly?  
**Answer:** Accessing properties on null can cause the expression to error. ALLOW/DENY/not-found must be defined explicitly.

**Q8.** How do `@PostAuthorize` and `@PostFilter` differ when a method returns a list?  
**Answer:** PostAuthorize makes a decision for the entire return value; PostFilter filters individual elements inside the collection.

**Q9.** When Alice is DENYed after the target already read B-1, is it guaranteed that B-1's data never entered memory/cache/logs?  
**Answer:** No. The post-check prevents returning the result via the proxy; it does not erase all side effects that already occurred.

**Q10.** What does the `readCount` test prove?  
**Answer:** When denied by the post-check, the target method already ran and the counter incremented; when denied by the pre-check, the counter did not increment.

**Q11.** Is a method not called through a Spring AOP proxy protected by `@PostAuthorize`?  
**Answer:** It should not be considered protected. You must test the real bean and avoid self-invocation and `new`-instantiated objects.

**Q12.** Why should `@PreAuthorize("hasAuthority('document:read')")` also be added?  
**Answer:** To reject callers lacking business permission before loading the object, rather than always performing the read and checking afterward.

**Q13.** Does `@PostAuthorize` directly return a Forbidden JSON message?  
**Answer:** No. It makes a decision at the proxy; the exception handling/HTTP mechanism is responsible for producing the response per configuration.

**Q14.** Can post-checks automatically handle the branch where the target method throws 404?  
**Answer:** When there is no normal return result, there is no corresponding `returnObject` to evaluate; lookup/error branches must be protected by a separate policy.

**Q15.** Is adding `@PostAuthorize` enough to prevent IDOR/BOLA in a multi-tenant system?  
**Answer:** No. You need tenant/ACL/ownership checks, query filtering, field restrictions, race handling, and non-leaking responses.

**Key takeaway:** **`@PostAuthorize` checks the object returned by the method** via the SpEL variable **`returnObject`**, which is very useful for ownership problems on **read operations**. Combine with pre-checks to restrict access early, do not rely on post-checks as the sole protection for data writes, and always test **allowed properly / denied properly / not found properly**.

## Official documentation

- Spring Security 6.5 — Method Security, section **Authorization Method Results with `@PostAuthorize`** and interceptor diagrams: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — `PostAuthorize` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html
- Spring Security 6.5 — `PostAuthorizeAuthorizationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostAuthorizeAuthorizationManager.html
- Spring Security 6.5 — `AuthorizationManagerAfterMethodInterceptor` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html
- Spring Security 6.5 — Testing HTTP Basic with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — Spring MVC test with method security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/
