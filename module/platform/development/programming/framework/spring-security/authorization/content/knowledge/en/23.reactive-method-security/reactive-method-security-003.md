# @PreAuthorize, @PostAuthorize, and Per-Annotation Support Boundaries in Reactive Method Security

## 1. The Problem: When Should Permissions Be Checked?

A Spring WebFlux application handles these operations:

- Reading a document belonging to a tenant.
- Reading a document that has an owner or is shared.
- Listing documents the user is actually allowed to view.
- Renaming a document if the user has EDIT permission.
- Exporting data, sending notifications, or writing to a database.

On the controller, `GET /api/tenants/t1/docs/101` may be protected with `authenticated()`. That **does not yet** prove Alice is allowed to view Document#101. The record might belong to another tenant, another owner, or be locked.

**Reactive Method Security** lets Spring enforce checks at **methods of Spring-managed beans**:

```java
@PreAuthorize("@docGuard.canEnter(authentication, #tenant, #id)")
@PostAuthorize("@docGuard.canReadReturned(authentication, returnObject)")
public Mono<Doc> read(
        @P("tenant") String tenant, @P("id") Long id) {
    return repository.findById(id);
}
```

This snippet **illustrates policy**, not a standalone Java file. It asks two distinct questions:

1. **Before allowing execution**: does the caller have access to the tenant, document ID, and appropriate state? `@PreAuthorize`.
2. **After obtaining the result value**: does the actually returned document match ownership or sharing rules? `@PostAuthorize`.

The second approach is useful for preventing data leaks in **read-only methods**, yet dangerous if used to "protect" a mutation that already wrote to the DB, sent an email, or called an external API before being rejected.

### Learning Objectives

After this chapter, you will be able to:
- Enable `@EnableReactiveMethodSecurity` properly for Spring Security 6.5.x.
- Explain **Reactor Context, subscription, and proxies** in reactive authorization checks.
- Distinguish the timing and semantics of `@PreAuthorize` vs. `@PostAuthorize`.
- Recognize support boundaries for `@PreFilter`, `@PostFilter`, `@Secured`, JSR-250, and return value types.
- Use SpEL expressions with `Boolean` or `Mono<Boolean>` matching `AuthorizationManager` capabilities.
- Block mutations **before side effects**, without treating post-checks as a rollback mechanism.
- Write tests with `WebTestClient` and `StepVerifier`; verify 401/403, tenant/owner/share, and zero writes on pre-check deny.
- Avoid conflating method authorization with HTTP authorization or filtering data after pagination.

## 2. How Does Reactive Method Security Differ from Servlet?

Spring Security has two configuration branches that learners must not mix together.

| WebFlux/Reactive | Servlet/MVC | Meaning |
|---|---|---|
| `@EnableReactiveMethodSecurity` | `@EnableMethodSecurity` | Enables the respective method interceptors |
| `ServerHttpSecurity` | `HttpSecurity` | Configures HTTP security |
| `SecurityWebFilterChain` | `SecurityFilterChain` | HTTP filter chain |
| `ReactiveSecurityContextHolder` | `SecurityContextHolder` | Safely retrieves context across a reactive pipeline |
| `Mono<T>` and `Flux<T>` | Usually synchronous `T`, `List<T>` | Method/return types suited to the reactive API |
| `AuthorizationManagerBeforeReactiveMethodInterceptor` | Servlet before-method interceptor | Pre-method authorization |
| `AuthorizationManagerAfterReactiveMethodInterceptor` | Servlet after-method interceptor | Result-based authorization |

On **Reactor**, a publisher describes work that can be subscribed to later and executed asynchronously. Never assume ThreadLocal `SecurityContextHolder` still holds the right principal when a pipeline switches schedulers or threads.

Spring Security integrates the security context into the **Reactor Context** via `ReactiveSecurityContextHolder`. WebFlux HTTP security sets the authenticated user's context for each request; when testing services directly, `@WithMockUser` with reactive test support or `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` supplies the appropriate context.

### 2.1. Why Return Mono/Flux?

Spring Security 6.5 documentation states that in a typical reactive setup, protected methods should return `org.reactivestreams.Publisher` such as `Mono` or `Flux` so they integrate with Reactor Context. The `AuthorizationManager` branch supports additional reactive return types, including Kotlin coroutines under appropriate configuration, yet you **cannot assume** methods returning synchronous `Doc`, `void`, `CompletableFuture`, or `suspend` all behave identically.

For Java 17 WebFlux, a **reliable baseline pattern** is:
- `Mono<Doc>` for reading a single document.
- `Flux<Doc>` for lists.
- `Mono<Void>`, `Mono<Doc>`, or `Mono<Result>` for mutations that are pre-checked and guarded inside the reactive pipeline.

Never declare a synchronous `void delete(...)` method and expect `@PostAuthorize` to re-check after a fire-and-forget reactive operation.

### 2.2. Which Annotation Enables It?

With Spring Security 6.5:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {
}
```

This is an illustrative configuration snippet; the full example is in section 7.

Since Spring Security 6.0, `@EnableReactiveMethodSecurity` defaults to `useAuthorizationManager=true`. Therefore you do not need to write `useAuthorizationManager=true` explicitly to "turn on" this mode in 6.5. The new engine uses Spring AOP and interceptors for pre/post authorization and filtering.

**Adding `spring-boot-starter-security` alone does not enable Method Security.** Enable it with the annotation/config and verify that beans are actually Spring-managed.

## 3. @PreAuthorize: Checking Permissions Before the Target Method Executes

`@PreAuthorize` uses **SpEL** to make decisions based on the principal, method arguments, authorities, and bean logic. Example:

```java
@PreAuthorize("hasAuthority('docs:edit')")
public Mono<Doc> rename(Long id, String newTitle) {
    return repository.rename(id, newTitle);
}
```

This is an illustrative example. It checks a general authority but **does not** check object owner or tenant, so it is insufficient for production protection.

A more complete rule:

```java
@PreAuthorize(
    "@docGuard.canEdit(authentication, #tenant, #id)"
)
public Mono<Doc> rename(
        @P("tenant") String tenant,
        @P("id") Long id,
        String title) {
    // ...
}
```

`@P` lets Spring Security resolve `#tenant` and `#id` reliably even when the compiler does not retain parameter names. `authentication` is the `Authentication` verified by Spring Security; never build it from client headers like `X-User` or `X-Role`.

### 3.1. Safe Pre-Check for Mutations

The goal is that unauthorized callers **never reach write logic**:

```text
Subscriber starts request
  ├── Reactive Method Security: @PreAuthorize
  │      ├── false/error -> AccessDeniedException
  │      └── true
  └── Target publisher
         └── Conditional DML check and mutation
```

Below, `DocGuard.canEdit(...)` returns `Mono<Boolean>` from `Mono.fromSupplier(...)` (simplified for demo data). This demonstrates that Spring Security 6.5 supports reactive boolean decisions from a SpEL bean under the `AuthorizationManager` mechanism.

Standalone expression example:

```java
@PreAuthorize("@reactivePolicy.allowed(authentication, #id)")
Mono<Doc> update(@P("id") Long id) {
    return repository.update(id);
}
```

When the bean returns `Mono<Boolean>`, authorization composes directly into the pipeline. Never call `block()` inside the policy bean to wait on JDBC/HTTP, as doing so blocks the event loop and can cause deadlocks or drop throughput.

### 3.2. Pre-Check Does Not Completely Solve TOCTOU

If owner/tenant permissions change after the check and before the `UPDATE`, a request could run under a stale decision. Spring Security annotations **do not create an atomic transaction** with storage. Appropriate solutions depend on domain needs:
- Use SQL `UPDATE ... WHERE id=? AND tenant_id=? AND owner_id=?` or permission predicates.
- Check affected row counts and optimistic versions.
- Use row locks/transaction isolation if needed.
- Re-evaluate permissions at write time inside the transaction.
- For external effects, use a transactional outbox or compensating workflow.

Method-level checks and data-layer guards are **two complementary layers**, not replacements for each other.

## 4. @PostAuthorize: Checking the Output Value, Too Late for Side Effects

`@PostAuthorize` inspects the method's result, typically using the SpEL variable `returnObject`. Example:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Doc> readOwned(Long id) {
    return repository.findById(id);
}
```

This is an illustrative snippet. With a `Doc` having an `owner` getter/property, the expression decides whether the principal owns the returned object. In the runnable example, we replace this with `@docGuard.canReadReturned(authentication, returnObject)` to support owner, share, and tenant binding together.

### 4.1. When Is It Useful?

- The method only reads a record and returns `Mono<Doc>`.
- Performing the read triggers no external side effects.
- You need to verify properties of the **actual returned result**: owner, visibility, state, tenant.
- Avoid trusting only user-supplied resource IDs.

A denied result **is not returned to the caller**; typically the subscriber receives `AccessDeniedException`, and in WebFlux HTTP, exception translation returns 403 for authenticated users.

### 4.2. Danger on Mutations

```java
// COUNTEREXAMPLE: do not use post-check to guard write operations.
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Doc> transferOwner(Long id, String newOwner) {
    return repository.changeOwner(id, newOwner);
}
```

Even though the post-check rejects the result, the DB update may **already have executed**. Reactive sequencing does not roll back network calls, published messages, or database transactions just because the response is later denied. Therefore:
- Use `@PreAuthorize` on writes, deletes, exports, and approvals.
- Use tenant-/owner-qualified transactions and updates.
- Never equate an HTTP 403 with "nothing happened".
- Even on `GET`, avoid reading external secrets or emitting sensitive events **before** a post-check.

### 4.3. @PostAuthorize Is Not a Filter for Flux

`@PostAuthorize` answers "may this method result/value be returned?". It is not a pagination model or row-level filter for every record in a large `Flux`. When an API lists many documents with different owners, use:
- Authorization inside the repository/query before pagination.
- In small demos, `Flux.filter(...)` using the principal from the Reactor Context.
- If choosing `@PostFilter`, verify the return type and support in your exact version and thoroughly test its semantics.

Never use `@PostAuthorize("true")` to mask policy bugs on a method that already performed writes.

## 5. Per-Annotation Support Boundaries in Reactive Method Security 6.5

It is **incorrect** to say WebFlux "only has `@PreAuthorize` and lacks `@PostAuthorize` or filtering". In `AuthorizationManager` mode, Spring Security 6.5 documents reactive interceptors for all four types. However, **having an interceptor** does not mean every data shape, collection, stream, or method signature behaves identically to Servlet.

| Annotation | Timing | Support/Usage in Spring Security 6.5 | Key Limitations to Remember |
|---|---|---|---|
| `@PreAuthorize` | Before target method | Yes, SpEL with role/authority/params/bean; beans can return `Boolean` or `Mono<Boolean>` under AuthorizationManager | Must be intercepted by Spring AOP; no `block()`; does not replace guarded writes |
| `@PostAuthorize` | After result is produced | Yes, evaluates `returnObject`, suited to read-only `Mono<T>` | Does not prevent side effects already run; not per-item paging |
| `@PreFilter` | Before passing arguments to method | Reactive filtering interceptor available under AuthorizationManager | Depends on parameter type; Collection args must support removal, not arbitrary `Flux`; avoid immutable collections |
| `@PostFilter` | On result after invocation | Reactive filtering interceptor available under AuthorizationManager | Do not filter large datasets **after** querying/paging; verify return types and semantics via integration tests |
| `@Secured` | Legacy-style role check | Exists in method security but uses a separate mechanism/config style, not the primary choice here | Do not assume equivalence with `@PreAuthorize` or default enablement; test if using legacy |
| `@RolesAllowed`/`@PermitAll`/`@DenyAll` | JSR-250 style | Reactive AuthorizationManager docs note JSR-250 integration | Must verify config/dependencies/placement and test the actual advisor |
| `@EnableMethodSecurity` | Enables Servlet-style method interceptors | **Not the annotation chosen for this reactive demo** | Use `@EnableReactiveMethodSecurity` and reactive context |
| `@EnableReactiveMethodSecurity` | Configuration | Enables reactive interceptors; `useAuthorizationManager` defaults to `true` in 6.x | Requires Spring-managed proxy; needs compatible method/return shapes |

### 5.1. PreFilter Has Different Constraints Than PostFilter

Per `@PreFilter`'s contract, the filtered argument is typically a **mutable Java Collection supporting removal**. An immutable `List.of(...)` can fail when filtered, and arrays are not supported by the classic `@PreFilter` contract. If a method takes multiple collection arguments, specify `filterTarget` with resolvable parameter names.

Architecture pattern (must be tested on your specific version):

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public Mono<Integer> importOwned(
        @P("documents") java.util.List<Doc> documents) {
    return Mono.just(documents.size());
}
```

**Annotation example only**, not part of the runnable demo as it omits imports and `Doc`. It can strip unauthorized elements before the method processes them, yet **silent filtering** is often unsuitable for batch business updates: it is safer to validate all IDs, report rejected records explicitly, and execute transactions under an explicit policy.

### 5.2. PostFilter Differs from PostAuthorize

`@PostFilter` uses `filterObject` to evaluate each element for supported shapes, whereas `@PostAuthorize` uses `returnObject` to evaluate the method result. Illustrative example:

```java
@PostFilter("filterObject.owner == authentication.name")
public Flux<Doc> listOwned() {
    return repository.findAll();
}
```

This is a **conceptual pattern**, not a default production solution for every reactive repository. To use it reliably, verify behavior against your exact Spring Security version, return type, and tests. Even when filtering succeeds, `findAll()` still reads all tenants and can leak total counts/timing, cause N+1 queries, and break pagination. For large datasets, **filtering via tenant/permission predicates in the database before paging** remains safer.

### 5.3. Legacy and Version-Specific Configuration

The official docs describe `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` starting in Spring Security 5.8 and note that 6.0+ defaults to `true`. If a project is still on 5.x legacy, separately verify configuration, interceptors, and reactive expression support.

`@Secured` and JSR-250 do not replace every capability of `@PreAuthorize`; owner/tenant/resource-based expressions should generally use policy beans with `@PreAuthorize`. Never assume merely placing an annotation on an interface guarantees Spring AOP interception in every setup—especially with `final` classes, self-invocation, proxy modes, and Kotlin `final` classes.

## 6. Reactive Semantics: Subscription, Reactor Context, and Exceptions

### 6.1. Execution Timing

`Mono.defer(...)` describes a unit of work executed when a subscriber subscribes. With reactive method interceptors, Spring Security coordinates authorization inside the publisher rather than via an external blocking check.

```text
HTTP request ─> WebFlux Authentication
                │
                └── Reactor Context
                      │
Subscriber ───────────┤
                      v
               @PreAuthorize
                   │
               ALLOW/DENY
                   │ allow
                   v
             Mono.defer(...) / service logic
                   │
               value Doc
                   │
               @PostAuthorize
                   │
              ALLOW/DENY
                   │ allow
                   v
              HTTP body to client
```

This is a **behavioral model**. Never treat Java method invocation time and subscription time as the same event. In particular, never execute eager side effects before constructing the publisher:

```java
// COUNTEREXAMPLE: synchronous/eager write before returning Mono.
@PreAuthorize("hasAuthority('docs:edit')")
public Mono<Void> unsafe(Long id) {
    someBlockingRepository.deleteById(id);
    return Mono.empty();
}
```

Use `Mono.defer` and reactive repository/transaction guards appropriately. Annotations provide no magical rollback when code executes incompatible eager side effects.

### 6.2. SecurityContextHolder vs ReactiveSecurityContextHolder

In imperative servlet code, `SecurityContextHolder` typically relies on `ThreadLocal`. WebFlux can switch threads within a pipeline, so prefer:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMapMany(authentication ->
        repository.findVisibleTo(authentication.getName()));
```

This is an illustrative snippet (requiring repository bean and imports). Spring Security manages the Reactor Context in the HTTP pipeline. When calling methods from scheduled jobs, reactive tests, or non-HTTP entry points, explicitly establish/propagate verified security context; never forge a principal from a request body.

### 6.3. Empty and Null Semantics

- `Mono.empty()` emits no value; many `@PostAuthorize` expressions inspecting `returnObject` are meaningful only when the publisher emits a value. Never use empty to "bypass deny", because resource protection belongs to pre-checks and service policies.
- `Mono.error(...)` propagates an error to the subscriber; never convert errors into allow with `onErrorResume(e -> Mono.just(secret))`.
- An authorization bean returning `Mono.empty()` may mean **abstain** depending on the manager/combiner. For sensitive resources, design to **deny when no explicit allow decision exists**.
- If an expression bean calls HTTP/DB, handle null responses, timeouts, and invalid data with fail-closed policies and bounded timeouts.
- Never call `block()` on the WebFlux event loop to compute a decision for a reactive annotation.

## 7. Java 17 / Spring Boot 3.5.6 Project Verifying @PreAuthorize and @PostAuthorize

This standalone project uses Spring WebFlux, Spring Security 6.5.x managed by Spring Boot 3.5.6, an in-memory document store, a policy bean, services returning `Mono`/`Flux`, and tests via `WebTestClient`/`StepVerifier`. It avoids JPA/blocking DBs so reactive semantics are not obscured. The production section covers moving to R2DBC.

### 7.1. Directory Tree

```text
reactive-method-security-demo/
  pom.xml
  src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    SecurityConfig.java
    Doc.java
    DocCatalog.java
    DocGuard.java
    DocService.java
    DocController.java
  src/test/java/com/example/reactiveauth/
    ReactiveMethodSecurityTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-method-security-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

**Important:** the demo does not include `spring-boot-starter-web` (Servlet/MVC). Having both starters can cause Spring Boot to pick an unintended stack. `spring-security-test` provides `mockUser`/`csrf`; `reactor-test` provides `StepVerifier`.

### 7.3. Main Application

**`src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java`**

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
```

### 7.4. SecurityConfig

**`src/main/java/com/example/reactiveauth/SecurityConfig.java`**

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain webFluxChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/tenants/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityWebFilterChain` only ensures the caller is authenticated on `/api/tenants/**` and denies all remaining HTTP routes. **Object-level checks** are performed by `DocService`. Both are included to illustrate defense-in-depth; never assume an authenticated request may read every document.

The demo does not need real user/password declarations because integration tests inject principals via `mockUser(...)`. If running standalone with `mvn spring-boot:run`, Spring Boot auto-configuration may generate a development password; that is not a production authorization mechanism.

### 7.5. Doc Model

**`src/main/java/com/example/reactiveauth/Doc.java`**

```java
package com.example.reactiveauth;

public record Doc(
        Long id,
        String tenant,
        String owner,
        String state,
        String title) {}
```

This is a Java 17 record. The example delegates `returnObject` inspection to `@docGuard`, so it does not depend on how SpEL resolves record accessors.

### 7.6. DocCatalog — Canonical In-Memory Data

**`src/main/java/com/example/reactiveauth/DocCatalog.java`**

```java
package com.example.reactiveauth;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class DocCatalog {

    private final ConcurrentMap<Long, Doc> docs =
        new ConcurrentHashMap<>();

    private final Map<String, Set<String>> memberships = Map.of(
        "t1", Set.of("alice", "bob", "manager"),
        "t2", Set.of("carol", "dave")
    );

    private final Set<String> admins = Set.of(
        "t1:manager"
    );

    private final Set<String> viewers = Set.of(
        "101:bob"
    );

    private final AtomicInteger reads = new AtomicInteger();
    private final AtomicInteger writes = new AtomicInteger();

    public DocCatalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        docs.put(101L, new Doc(
            101L, "t1", "alice", "ACTIVE", "Owner memo"));
        docs.put(102L, new Doc(
            102L, "t1", "alice", "ACTIVE", "Project notes"));
        docs.put(103L, new Doc(
            103L, "t1", "manager", "ACTIVE", "Manager secret"));
        docs.put(104L, new Doc(
            104L, "t1", "alice", "ARCHIVED", "Old draft"));
        docs.put(201L, new Doc(
            201L, "t2", "carol", "ACTIVE", "Other tenant"));
        reads.set(0);
        writes.set(0);
    }

    public Doc find(Long id) {
        return id == null ? null : docs.get(id);
    }

    public boolean member(String tenant, String username) {
        Set<String> users = memberships.get(tenant);
        return users != null && username != null
            && users.contains(username);
    }

    public boolean adminBinding(String tenant, String username) {
        return tenant != null && username != null
            && admins.contains(tenant + ":" + username);
    }

    public boolean viewer(Long id, String username) {
        return id != null && username != null
            && viewers.contains(id + ":" + username);
    }

    public List<Doc> docsInTenant(String tenant) {
        return docs.values().stream()
            .filter(doc -> doc.tenant().equals(tenant))
            .sorted(Comparator.comparing(Doc::id))
            .toList();
    }

    public void recordRead() {
        reads.incrementAndGet();
    }

    public int readCount() {
        return reads.get();
    }

    public int writeCount() {
        return writes.get();
    }

    public synchronized Doc rename(
            Long id, String expectedTenant, String title) {
        Doc old = find(id);
        if (old == null
                || !expectedTenant.equals(old.tenant())
                || !"ACTIVE".equals(old.state())) {
            return null;
        }
        Doc updated = new Doc(
            old.id(), old.tenant(),
            old.owner(), old.state(), title);
        docs.put(id, updated);
        writes.incrementAndGet();
        return updated;
    }
}
```

Records are seeded server-side. The `readCount` and `writeCount` counters highlight **the difference between pre-deny and post-deny**:
- Pre-deny does not subscribe to the `Mono.defer` reading the method body; `readCount=0` is expected.
- Post-deny may have already read the result before blocking the response; `readCount=1` is expected, while the client receives no document.
- Pre-denied mutations never call `rename`; `writeCount=0`.

**Warning:** This in-memory repository lacks real database transactions and isolation; production requires transactions, optimistic locking, and strict tenant/action `WHERE` clauses.

### 7.7. DocGuard — Membership, Owner, Viewer, and Admin Binding

**`src/main/java/com/example/reactiveauth/DocGuard.java`**

```java
package com.example.reactiveauth;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("docGuard")
public class DocGuard {

    private final DocCatalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocGuard(DocCatalog catalog) {
        this.catalog = catalog;
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    private boolean authenticated(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !trust.isAnonymous(auth);
    }

    private boolean scopedAdmin(Authentication auth, String tenant) {
        return hasAuthority(auth, "ROLE_TENANT_ADMIN")
            && catalog.adminBinding(tenant, auth.getName());
    }

    // Pre-check: correct tenant, state, and membership.
    public boolean canEnter(
            Authentication auth, String tenant, Long id) {
        if (!authenticated(auth) || tenant == null) {
            return false;
        }
        Doc doc = catalog.find(id);
        return doc != null
            && tenant.equals(doc.tenant())
            && "ACTIVE".equals(doc.state())
            && catalog.member(tenant, auth.getName());
    }

    // Post-check: read permission on actual returned result.
    public boolean canReadReturned(
            Authentication auth, Doc doc) {
        if (!authenticated(auth) || doc == null
                || !"ACTIVE".equals(doc.state())
                || !catalog.member(doc.tenant(), auth.getName())) {
            return false;
        }
        return auth.getName().equals(doc.owner())
            || catalog.viewer(doc.id(), auth.getName())
            || scopedAdmin(auth, doc.tenant());
    }

    public boolean canList(Authentication auth, String tenant) {
        return authenticated(auth)
            && tenant != null
            && catalog.member(tenant, auth.getName())
            && hasAuthority(auth, "docs:list");
    }

    // Async-compatible SpEL result for @PreAuthorize.
    public Mono<Boolean> canEdit(
            Authentication auth, String tenant, Long id) {
        return Mono.fromSupplier(() -> {
            if (!canEnter(auth, tenant, id)) {
                return false;
            }

            Doc doc = catalog.find(id);
            if (doc == null) {
                return false;
            }

            boolean ownerWithEditAuthority =
                auth.getName().equals(doc.owner())
                && hasAuthority(auth, "docs:edit");

            return ownerWithEditAuthority
                || scopedAdmin(auth, tenant);
        });
    }
}
```

Key controls:
- Header `X-Tenant-Id`, path, and body **never grant authority**. The tenant in the route is a selector; it is verified against the canonical document tenant and server-side membership.
- `ROLE_TENANT_ADMIN` is valid only within the tenant where the user has a binding (`t1:manager`).
- Bob holds a viewer grant on Document#101, which **does not** grant edit rights.
- `canEdit` returns `Mono<Boolean>` to stay reactive without calling `block()`.
- Missing document, wrong tenant, missing membership, archived state, or wrong role/grant → deny.

### 7.8. DocService — Pre + Post for READ, Pre Only for Mutation

**`src/main/java/com/example/reactiveauth/DocService.java`**

```java
package com.example.reactiveauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocService {

    private final DocCatalog catalog;
    private final DocGuard guard;

    public DocService(DocCatalog catalog, DocGuard guard) {
        this.catalog = catalog;
        this.guard = guard;
    }

    // Two layers: pre-check tenant/state; post-check owner/share.
    @PreAuthorize(
        "@docGuard.canEnter(authentication, #tenant, #id)"
    )
    @PostAuthorize(
        "@docGuard.canReadReturned(authentication, returnObject)"
    )
    public Mono<Doc> read(
            @P("tenant") String tenant,
            @P("id") Long id) {

        return Mono.defer(() -> {
            catalog.recordRead();
            return Mono.justOrEmpty(catalog.find(id));
        });
    }

    // List has its own authority and filters each document per caller.
    @PreAuthorize(
        "@docGuard.canList(authentication, #tenant)"
    )
    public Flux<Doc> list(@P("tenant") String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMapMany(auth -> Flux.fromIterable(
                    catalog.docsInTenant(tenant)
                )
                .filter(doc -> guard.canReadReturned(auth, doc)));
    }

    // Do not use @PostAuthorize to guard mutations!
    @PreAuthorize(
        "@docGuard.canEdit(authentication, #tenant, #id)"
    )
    public Mono<Doc> rename(
            @P("tenant") String tenant,
            @P("id") Long id,
            String title) {

        return Mono.defer(() -> {
            if (title == null || title.isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title required"));
            }

            Doc updated = catalog.rename(id, tenant, title);
            if (updated == null) {
                return Mono.error(new AccessDeniedException(
                    "Resource changed"));
            }
            return Mono.just(updated);
        });
    }
}
```

**Why does this design fit the topic?**

- `read` uses both annotations: `@PreAuthorize` blocks queries against other tenants or archived docs, while `@PostAuthorize` checks owner/share on the emitted object.
- Bob belongs to `t1` but is not shared on Document#102: **pre-pass**, the document is read, **post-deny**. A post-denied result is never returned to the client, though the internal read **did happen**.
- Alice belongs to `t1` and tries to read `t2`'s Document#201 via route `t1`: **pre-deny**, so the method body never executes.
- `list` requires the distinct `docs:list` authority and filters records within the tenant. This is an in-memory demo; large datasets must filter in the query before pagination.
- `rename` uses **pre-check only**, with no post-check after writing. Edit permission is resolved via `Mono<Boolean>`.
- `Mono.defer` ensures method logic executes only upon subscription, with no eager side effects prior to reactive authorization.

In production, `catalog.rename` must be replaced by a conditional `UPDATE` checking tenant/owner/permission plus optimistic locking or transactions. The demo does not guarantee atomicity across concurrent membership changes.

### 7.9. REST Controller — Client Paths/IDs Are Only Selectors

**`src/main/java/com/example/reactiveauth/DocController.java`**

```java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants")
public class DocController {

    public record RenameBody(String title) {}

    private final DocService service;

    public DocController(DocService service) {
        this.service = service;
    }

    @GetMapping("/{tenant}/docs/{id}")
    public Mono<Doc> read(
            @PathVariable("tenant") String tenant,
            @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @GetMapping("/{tenant}/docs")
    public Flux<Doc> list(
            @PathVariable("tenant") String tenant) {
        return service.list(tenant);
    }

    @PutMapping("/{tenant}/docs/{id}")
    public Mono<Doc> rename(
            @PathVariable("tenant") String tenant,
            @PathVariable("id") Long id,
            @RequestBody RenameBody body) {
        return service.rename(
            tenant, id, body.title());
    }
}
```

The controller never assumes `/api/tenants/t1` proves the user belongs to `t1`; it is merely an input to `DocGuard`. `@RequestBody` on the rename endpoint accepts only `title` and exposes no fields to alter `owner` or `tenant`.

## 8. Integration Tests: Proving Pre and Post Differ

**`src/test/java/com/example/reactiveauth/ReactiveMethodSecurityTest.java`**

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveMethodSecurityTest {

    @Autowired ApplicationContext context;
    @Autowired DocCatalog catalog;
    @Autowired DocService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        catalog.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private static String docPath(String tenant, long id) {
        return "/api/tenants/" + tenant + "/docs/" + id;
    }

    private WebTestClient as(String username, String... authorities) {
        return client.mutateWith(
            mockUser(username).authorities(authorities)
        );
    }

    private WebTestClient asWithCsrf(
            String username, String... authorities) {
        return as(username, authorities).mutateWith(csrf());
    }

    @Test
    void anonymousReadNeedsAuthentication() {
        client.get().uri(docPath("t1", 101))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnDocument() {
        as("alice").get().uri(docPath("t1", 101))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.title").isEqualTo("Owner memo");
    }

    @Test
    void viewerCanReadSharedDocument() {
        as("bob").get().uri(docPath("t1", 101))
            .exchange().expectStatus().isOk();
    }

    @Test
    void preAuthorizeDeniesOtherTenantBeforeRead() {
        as("alice").get().uri(docPath("t2", 201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesForgedPathTenant() {
        as("alice").get().uri(docPath("t1", 201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesArchivedDocument() {
        as("alice").get().uri(docPath("t1", 104))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void preAuthorizeDeniesUnknownDocument() {
        as("alice").get().uri(docPath("t1", 999))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.readCount());
    }

    @Test
    void postAuthorizeDeniesUnsharedDocumentAfterFetch() {
        as("bob").get().uri(docPath("t1", 102))
            .exchange().expectStatus().isForbidden();

        // The method created/subscribed to the result before the post-check.
        assertEquals(1, catalog.readCount());
    }

    @Test
    void postAuthorizeDeniedContentIsNotReturned() {
        as("bob").get().uri(docPath("t1", 103))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void scopedTenantAdminMayReadPrivateDocument() {
        as("manager", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t1", 103))
            .exchange().expectStatus().isOk();
    }

    @Test
    void adminRoleWithoutServerBindingDoesNotGrantRead() {
        as("bob", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t1", 103))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void scopedAdminCannotReadAnotherTenant() {
        as("manager", "ROLE_TENANT_ADMIN")
            .get().uri(docPath("t2", 201))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listRequiresDistinctAuthority() {
        as("bob").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listFiltersDocumentsUsingResultPermission() {
        as("bob", "docs:list")
            .get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void ownerListOmitsArchivedAndUnsharedOthers() {
        as("alice", "docs:list")
            .get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1].id").isEqualTo(102)
            .jsonPath("$[2]").doesNotExist();
    }

    @Test
    void listCannotCrossTenantEvenWithAuthority() {
        as("bob", "docs:list")
            .get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void editRequiresDocsEditAuthority() {
        asWithCsrf("alice")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"No grant\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void ownerWithEditAuthorityCanRename() {
        asWithCsrf("alice", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Revised\"}")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Revised");

        assertEquals(1, catalog.writeCount());
        assertEquals("Revised", catalog.find(101L).title());
    }

    @Test
    void viewerWithEditStringCannotEditUnownedObject() {
        asWithCsrf("bob", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Forbidden\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void editChecksCanonicalTenantBeforeMutation() {
        asWithCsrf("alice", "docs:edit")
            .put().uri(docPath("t1", 201))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Wrong tenant\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void boundAdminMayEditOwnTenant() {
        asWithCsrf("manager", "ROLE_TENANT_ADMIN")
            .put().uri(docPath("t1", 102))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Managed\"}")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.writeCount());
    }

    @Test
    void adminRoleCannotEditAnotherTenant() {
        asWithCsrf("manager", "ROLE_TENANT_ADMIN")
            .put().uri(docPath("t2", 201))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Forbidden\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void missingCsrfBlocksOtherwiseAllowedEdit() {
        as("alice", "docs:edit")
            .put().uri(docPath("t1", 101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"No CSRF\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.writeCount());
    }

    @Test
    void unknownRouteDeniedByHttpFilter() {
        as("alice").get().uri("/internal/diagnostics")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceReadUsesReactiveSecurityContext() {
        StepVerifier.create(service.read("t1", 101L))
            .expectNextMatches(doc ->
                doc.id().equals(101L)
                    && doc.owner().equals("alice"))
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "bob")
    void directServiceCallGetsPostAuthorizationError() {
        StepVerifier.create(service.read("t1", 102L))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceCallGetsPreAuthorizationError() {
        StepVerifier.create(service.read("t2", 201L))
            .expectError(AccessDeniedException.class)
            .verify();
        assertEquals(0, catalog.readCount());
    }
}
```

Why do these tests accurately test **Reactive Method Security**?
1. `WebTestClient.bindToApplicationContext(...)` wires up the context's real WebFlux handlers and security WebFilters.
2. `apply(springSecurity())` activates reactive security testing support.
3. `mockUser(...)` injects test principal/authorities onto the request; it does not verify real passwords or JWT signatures.
4. `csrf()` lets the `PUT` pass the CSRF filter so the 403/200 outcome reflects **method-level edit permissions**.
5. `@WithMockUser` + `StepVerifier` tests the **Spring-managed service bean** directly without going through the HTTP controller. The Spring Security documentation officially covers reactive method-security testing with `StepVerifier`.
6. `readCount` and `writeCount` distinguish **pre-check vs. post-check timing**: pre-deny does not fetch, post-deny fetches without returning the result, and pre-deny on a mutation performs zero writes.

### 8.1. Running the Tests

In the directory containing `pom.xml`:

```bash
mvn test
```

**Expected outcome:** these JUnit tests pass when run with the dependencies and versions specified in the lesson. This is an **expectation from authoring and code review**, not a claim that Maven was executed here. Run them on your development machine or CI to catch version mismatches, reactive interceptor ordering differences, or test configuration issues.

`@WithMockUser` and `mockUser(...)` test **authorization**, not JWT issuer, audience, signature, password strength, or a production IdP.

### 8.2. Interpreting Key Results

| Scenario | Pre | Post | Internal Data | HTTP/Test |
|---|---|---|---|---|
| Alice reads Document#101 | Allow | Allow | Reads one record | 200 |
| Bob reads shared Document#101 | Allow | Allow | Reads one record | 200 |
| Bob reads unshared Document#102 | Allow | Deny | Read occurred, not emitted to client | 403 |
| Alice uses `t1` path to read `t2` Doc#201 | Deny | Not executed | Not fetched | 403 |
| Alice reads archived Doc#104 | Deny | Not executed | Not fetched | 403 |
| Bob edits Doc#101 without ownership | Deny | Not used | No write | 403 |
| Alice with `docs:edit` edits Doc#101 | Allow | Not used | Written once | 200 |
| Alice without `docs:edit` edits Doc#101 | Deny | Not used | No write | 403 |
| Alice sends PUT without CSRF token | Blocked by WebFilter | Service not called | No write | 403 |
| Bob lists with `docs:list` | Allow | Not used | Returns only readable Doc#101 | 200 |
| Anonymous reads any protected API | Blocked by HTTP auth | Service not called | Not read | 401 |

**Special note:** The table showing post-check denying *after reading* explains why `@PostAuthorize` is not an option for protecting side effects. Never treat HTTP status alone as proof of transaction rollback or untouched data.

## 9. Beyond the Demo: Getting Production Right

### 9.1. R2DBC and Repositories with Tenant Predicates

With a real database, do not write:

```java
return repository.findById(documentId);
```

if a multi-tenant API could retrieve another tenant's record by ID alone. Use queries constrained by tenant and permission:

```sql
SELECT id, tenant_id, owner_id, state, title
FROM document
WHERE id = :documentId
  AND tenant_id = :verifiedTenant;
```

For listing:

```sql
SELECT d.id, d.tenant_id, d.owner_id, d.state, d.title
FROM document d
WHERE d.tenant_id = :verifiedTenant
  AND d.state = 'ACTIVE'
  AND (
       d.owner_id = :authenticatedUser
       OR EXISTS (
            SELECT 1 FROM document_share s
            WHERE s.document_id = d.id
              AND s.user_id = :authenticatedUser
              AND s.permission = 'READ'
       )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

These SQL snippets are **logical templates** (omitting schema/connection configuration). Add verified admin bindings if business rules permit admins to read. `:verifiedTenant` must be a tenant validated against `Authentication` and membership, never a raw header.

Never query across all tenants and call `Flux.filter(...)` after pagination; doing so wastes bandwidth, breaks page totals, and leaks metadata.

### 9.2. @Transactional in Reactive Flows

Spring Framework supports reactive transactions via `ReactiveTransactionManager`, operating through the Reactor Context. Never mix an imperative `PlatformTransactionManager` with a reactive pipeline and expect rollbacks to behave properly.

For writes:

```java
@PreAuthorize("@docGuard.canEdit(authentication, #tenant, #id)")
@Transactional
public Mono<Integer> update(
        @P("tenant") String tenant,
        @P("id") Long id) {
    return databaseClient.sql(
        """
        UPDATE document
        SET title = :title
        WHERE id = :id AND tenant_id = :tenant
        """
    ).bind("title", "Revised")
     .bind("id", id)
     .bind("tenant", tenant)
     .fetch().rowsUpdated();
}
```

This is an **architectural template**, requiring injected `DatabaseClient`, reactive transaction manager, imports, parameter names, and proper permission guards to run. In production, add owner/role/ACL predicates, expected version checks, and assert `rowsUpdated == 1`.

**Never** convert the annotation to `@PostAuthorize("returnObject > 0")` to protect a mutation: the `UPDATE` may already have run, so post-checks must never be the sole boundary. Always combine pre-checks, guarded updates, and transactions.

### 9.3. Do Not Perform Blocking Work Inside Expressions

SpEL beans may return `Boolean` for fast in-memory rules; however, if database or HTTP lookups are required, keep them in a non-blocking pipeline returning `Mono<Boolean>`. Never write:

```java
@PreAuthorize("@policy.remoteCheck(authentication, #id).block()")
```

That is a **counterexample**: `.block()` on the event loop is a performance trap. Have `@policy.remoteCheck(...)` return `Mono<Boolean>` in a supported version, configure timeouts, and fail closed when the service is unavailable.

### 9.4. Subscriptions and Side Effects Outside Transactions

A reactive publisher can:
- Never be subscribed to: no data read, no DML executed.
- Be subscribed to multiple times: can re-execute side effects if it is a cold publisher.
- Be canceled mid-flight: may finish partially or have already sent external requests.
- Switch schedulers: Reactor Context propagates where Reactor supports it, whereas custom ThreadLocals do not.

Use idempotency keys, managed retries, cancellation handling, and transaction boundaries. `@PreAuthorize` does not prevent "retrying and sending an email twice" if business logic lacks idempotency. Across a database and message broker, consider a transactional outbox.

### 9.5. @PreFilter / @PostFilter and Collection Shapes

When using filtering annotations, write **compatibility tests** for:
- Mutable vs. immutable `List`.
- `Mono<List<T>>`, `Flux<T>`, plain collections: which types are actually intercepted and how filtering behaves on your pinned version.
- Empty collections, nulls, arrays.
- Nested/group/tenant denials.
- Paging, counts, sorting, and timing effects.

Do not assume Servlet-identical behavior in all cases. An annotation supported at the API level that goes untested with the actual return/argument types can cause runtime failures or faulty filtering.

### 9.6. Annotations on Interfaces, Classes, and Self-Invocation

Method Security uses Spring AOP by default. Cases to test:
- Calling a service via an injected bean: goes through the proxy.
- Calling `this.read(...)` inside the same class: self-invocation can bypass advice.
- Manually creating `new DocService(...)`: no Spring proxy.
- `private` or `final` methods, Kotlin `final` classes, interface default methods: depends on proxy configuration, not intercepted automatically.
- Overlapping/conflicting annotations on interface and implementation: AuthorizationManager checks for conflicting annotations; review to keep policies unambiguous.
- Class-level annotations alongside method-level ones: test precedence/inheritance; never assume two rules are OR'd.

If AspectJ weaving or custom advisors are required, that is an advanced configuration that must be tested for your specific version rather than assumed from this demo.

### 9.7. Caching and Principal-Specific Results

Caching `Doc` by `docId` without tenant separation, or caching authorization decisions by username without action/permissions/version, risks serving stale permissions after revocation. Every cached authorization decision must track principal, tenant, resource, action, version, and TTL; sensitive data requires explicit invalidation/revocation SLAs.

### 9.8. Security Outside HTTP

Message consumers, schedulers, and async jobs have no implicit HTTP `SecurityContext`. Calling a Spring service proxy without establishing a trusted `Authentication`/Reactor Context gives method guards no basis to grant access (normally resulting in deny). For system-initiated tasks, establish an explicit service identity and capability rather than using `System.setProperty("admin", true)` or bypassing annotations.

## 10. Common Mistakes

| Mistake | Risk | Fix |
|---|---|---|
| Using `@EnableMethodSecurity` instead of `@EnableReactiveMethodSecurity` without understanding the stack | Advisor/context mismatch | Use version-appropriate reactive config and integration tests |
| Adding only `starter-security` and assuming method annotations work | Annotations stay inactive | Enable `@EnableReactiveMethodSecurity` |
| Method returns `void` or sync value while relying on Reactor Context | Behavior differs from Publisher | Use `Mono`/`Flux` or a version-supported/tested return type |
| Using `@PostAuthorize` alone on `DELETE`/`UPDATE` | DML runs before deny | `@PreAuthorize` + guarded DML |
| Using `@PostAuthorize` to filter every record in a large `Flux` | Broken pagination/semantics | Filter at the repository before paging |
| Assuming `@PreFilter` works arbitrarily on arrays/`List.of`/`Flux` | Runtime errors or wrong data | Check contract, mutable collections, and integration tests |
| Treating `hasRole('ADMIN')` as cross-tenant access | Cross-tenant escalation | Scope tenant membership and admin bindings |
| Policy bean reads owner from request body | Client self-asserts ownership | Canonical resource lookup |
| Calling `block()` inside reactive SpEL | Blocks the event loop | Non-blocking `Mono<Boolean>` |
| Catching exceptions and defaulting to allow | Bypass when PDP fails | Fail closed, timeouts, and observability |
| Calling methods via `this.method()` | Bypasses proxy | Invoke Spring-managed service bean |
| Manually calling `new` on an annotated service | No method interceptor | Inject Spring bean |
| Checking only HTTP routes while ignoring resource IDs | BOLA/IDOR | Object-level policies in service and DB |
| Treating a post-check 403 as "zero side effects" | DB/email may already be mutated | Pre-checks, transactions, outbox |
| Reading arbitrary `SecurityContextHolder` in Reactor | Wrong principal on thread switches | `ReactiveSecurityContextHolder` |
| Skipping negative-path, multi-tenant, and cancellation tests | Hard-to-spot security bugs | `WebTestClient`, `StepVerifier`, concurrency/revocation tests |
| Assuming "Admin always has every role" | Broken authority mapping | Explicit role hierarchy and scoping |
| Failing to pin/test Spring Security versions | Subtle annotation behavior differences | Version matrix and contract tests |

## 11. Code Review Checklist

- [ ] Spring Boot actually runs WebFlux, without accidentally pulling in Servlet auto-configuration.
- [ ] `@EnableReactiveMethodSecurity` is enabled and default `AuthorizationManager` mode is verified.
- [ ] Protected methods live on Spring-managed beans and are invoked via AOP proxies.
- [ ] Java reactive methods return `Mono`/`Flux` or types verified as supported in the project's version.
- [ ] `Authentication` comes from the Reactor Context, never self-asserted via headers/body.
- [ ] `@PreAuthorize` precedes every side-effecting mutation.
- [ ] `@PostAuthorize` is used only where reading the result before checking is acceptable, never assuming rollback.
- [ ] SpEL beans do not block the event loop; errors and empty decisions fail safely.
- [ ] `@PreFilter`/`@PostFilter` are tested on the exact collection/publisher types and never replace DB filtering for large datasets.
- [ ] Tenant membership and canonical record tenant are cross-checked before granting access.
- [ ] Owner/share/role/admin bindings are checked per action; membership alone never grants every record.
- [ ] Reactive transaction manager and guarded `UPDATE`/`DELETE` with affected-row checks are used.
- [ ] Methods combining `@PreAuthorize` and `@PostAuthorize` have tests proving ordering and semantics.
- [ ] CSRF, CORS, JWT authentication, and route-level security are not confused with method authorization.
- [ ] `WebTestClient` 401/403/200 tests, direct `StepVerifier` tests, and positive/negative tenant/object tests are present.
- [ ] Cache invalidation/revocation, retries, subscriptions, and async contexts are reviewed.
- [ ] Class/interface/meta-annotations are reviewed for inheritance and conflicts.

## 12. Self-Check Questions

**Question 1.** In a reactive app, why use `@EnableReactiveMethodSecurity` instead of only `@EnableMethodSecurity`?

**Answer:** Reactive method security must integrate with Reactor Context and reactive method interceptors; `@EnableMethodSecurity` primarily configures the Servlet/imperative method security branch. Differences must be verified against your stack and version.

**Question 2.** Bob in tenant `t1` reads an existing, active, unshared document. `@PreAuthorize` tenant check passes; `@PostAuthorize` owner/share check denies. Should you assume the DB was never read?

**Answer:** No. Post-checks run after a result is available to inspect, so the read work may already have happened. The content is blocked from returning to the client, but it is not a pre-check.

**Question 3.** Can `@PostAuthorize` be used as the sole protection layer for `DELETE`?

**Answer:** No. Deletes or side effects can execute before the post-check denies. Use `@PreAuthorize`, transactions, and guarded deletes.

**Question 4.** Does Spring Security 6.5 Reactive Method Security completely lack support for `@PreFilter`/`@PostFilter`?

**Answer:** No. AuthorizationManager mode includes reactive filtering interceptors. However, argument/return value types and filter semantics must be tested against your exact version and contract.

**Question 5.** Why can `List.of(...)` be an unsuitable input for `@PreFilter`?

**Answer:** The classic `@PreFilter` contract requires a Java `Collection` supporting element removal. `List.of(...)` is immutable, so filtering it directly can fail.

**Question 6.** Can a bean called from `@PreAuthorize` return `Mono<Boolean>`?

**Answer:** Yes, under Spring Security 6.5's reactive `AuthorizationManager` mechanism; this is the right approach for asynchronous/non-blocking policy logic. Never call `block()` to force it into a boolean.

**Question 7.** Why is `@PostFilter` after `findAll()` a poor strategy for a paginated report of millions of rows?

**Answer:** The repository already reads huge datasets or wrong tenants, permissions filter too late, total counts/pagination become inaccurate, and it invites N+1 issues. Push tenant and permission predicates into the DB before paging.

## 13. Official Documentation Sources

- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`, beans returning `Boolean`/`Mono<Boolean>`, the four reactive pre/post interceptors, and AuthorizationManager mode.
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html): `@WithMockUser` and `StepVerifier` for Spring bean methods.
- [Spring Security 6.5 — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `bindToApplicationContext` and `springSecurity()`.
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, roles, authorities.
- [Spring Security 6.5 — Reactive Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()` when testing POST/PUT/DELETE.
- [Spring Security 6.5 — PostAuthorizeReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): evaluating return values of reactive methods.
- [Spring Security 6.5 — PreFilterAuthorizationReactiveMethodInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html): argument-filtering interceptor.
- [Spring Security 6.5 — PostFilterAuthorizationReactiveMethodInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html): return-object-filtering interceptor.
- [Spring Security 6.5 — EnableReactiveMethodSecurity annotation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html): `useAuthorizationManager` defaults to `true` in 6.5.
- [Spring Framework — Declarative Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction context and reactive transaction semantics.

**Remember:** In Reactive Method Security, **`@PreAuthorize` blocks before processing**, whereas **`@PostAuthorize` checks an already-produced result and cannot guarantee rollback of side effects**. Spring Security 6.5 supports pre/post authorization and reactive filtering interceptors, yet **return types, collection shapes, Reactor Context, and proxies** determine whether they are used correctly. Use `Mono`/`Flux`, canonical tenant and object policies, non-blocking `Mono<Boolean>` when needed, guarded database queries, and test pre-deny, post-deny, and data mutations alike.