# Empty Results, Error Signals, and Denial Semantics in Reactive Method Security

## 1. "No Result" Does Not Always Mean the Same Thing

A Spring WebFlux application has two distinct asynchronous streams:

1. **The authorization decision stream** for `@PreAuthorize`, `@PostAuthorize`, or a custom `ReactiveAuthorizationManager`.
2. **The data stream** from a repository or service returning a document or list to the user.

In the decision stream:

```java
Mono.just(true)  // Explicit ALLOW.
Mono.just(false) // Explicit DENY.
Mono.empty()     // No decision emitted: may mean ABSTAIN.
Mono.error(ex)   // Evaluation error, NOT a decision.
```

In the data stream:

```java
Mono.just(doc) // A document is emitted.
Mono.empty()   // No document emitted.
Mono.error(ex) // Query or pipeline failed.
Flux.empty()   // List has 0 items.
```

**Never equate** a policy `Mono.empty()` with a repository `Mono.empty()`. Spring Security 6.5 specifies that a bean invoked by a method authorization expression may return `Mono.empty()` to express *abstain*: **no authorization decision was made**. That is not `Mono.just(false)`, and how multiple decisions combine depends on the interceptor/manager configuration.

If your API rule is **"permit only when an explicit ALLOW decision exists"**, normalize every abstain, error, and timeout into an **explicit DENY** at the policy boundary:

```java
return remoteDecision
    .timeout(Duration.ofMillis(300))
    .onErrorResume(error -> Mono.just(false))
    .defaultIfEmpty(false);
```

This is an **illustrative snippet** requiring imports and a valid `Mono<Boolean> remoteDecision`. The final answer is strictly `true` or `false`. Record the error cause in dedicated metrics/logs; never use `onErrorReturn(true)` as a fallback.

### Four Questions to Separate

- **Is the caller allowed to invoke this operation?** → Method Security; allow/deny decision.
- **Does a resource exist within the verified scope?** → repository; may be empty/not-found.
- **Are any items in a list readable?** → `Flux.empty()` can be valid.
- **Is the policy service or database failing?** → `onError`; never infer allow or "not found".

Lesson goals: understand Reactor signal semantics; handle abstain/errors in `@PreAuthorize`/`@PostAuthorize`; avoid fail-open; distinguish 401/403/404/503/200 `[]`; test with `StepVerifier` and `WebTestClient`; build a Java 17/Spring Boot 3.5.6 demo.

## 2. Reactor Signals: Value, Complete, Error

A typical `Mono<T>` ends in one of three ways:

```text
Mono.just(value)
  onSubscribe -> onNext(value) -> onComplete

Mono.empty()
  onSubscribe -> onComplete

Mono.error(exception)
  onSubscribe -> onError(exception)
```

`onNext` and `onError` are not equivalent. `Mono.empty()` does not emit a `null` value; under Reactor's contract, `Mono.just(null)` is illegal. If a nullable value must become a `Mono`, use `Mono.justOrEmpty(value)`, then **decide in business logic** what an empty result means.

`Flux<T>` can emit multiple `onNext` signals followed by `onComplete` or `onError`. Once a `Flux` has already streamed several documents over HTTP and then hits an error, bytes already sent **cannot be retracted**.

### 2.1. Stream-by-Stream Matrix

| Stream | Signal | Meaning | Recommended Behavior |
|---|---|---|---|
| `Mono<Boolean>` authorization | `true` | Explicit allow | Proceed if other guards pass |
| `Mono<Boolean>` authorization | `false` | Explicit deny | Block before method |
| `Mono<Boolean>` authorization | Empty | Abstain / undecided | Map to `false` in policies requiring explicit allow |
| `Mono<Boolean>` authorization | Error | PDP/logic unavailable | Never allow; map to deny or propagate fail-closed error |
| `Mono<Document>` data | Document | One record emitted | Return only after authorization passes |
| `Mono<Document>` data | Empty | No record emitted | 404 or empty response per API contract |
| `Mono<Document>` data | Error | Data/pipeline failure | 5xx / proper error handler, never call it not found |
| `Flux<Document>` data | Empty | 0 items | Typically 200 `[]` if LIST is authorized |
| `Flux<Document>` data | Error after items | Incomplete stream | Watch for streaming data leaks |

**Conclusion:** The `empty` symbol describes **signal shape**, not any specific HTTP status or authorization decision.

## 3. ABSTAIN Is Not DENY

Spring Security Reactive Method Security uses `ReactiveSecurityContextHolder` to retrieve `Authentication` from Reactor Context; `@EnableReactiveMethodSecurity` enables reactive method interceptors. In Spring Security 6.5, beans invoked from SpEL can return `Boolean` or `Mono<Boolean>`; `Mono.empty()` can signal **abstain**.

```java
@Component("policy")
public class Policy {
    public Mono<Boolean> decide(Long documentId) {
        if (documentId == null) {
            return Mono.empty(); // Undecided.
        }
        return Mono.just(documentId == 101L);
    }
}

@PreAuthorize("@policy.decide(#documentId)")
public Mono<Document> read(
        @P("documentId") Long documentId) {
    // ...
}
```

This is an **illustrative pattern**, not a standalone runnable class. `Mono.empty()` inside expressions/managers must not be relied on as a "guaranteed deny". If the application's policy requires an explicit allow, use:

```java
public Mono<Boolean> strictDecision(Mono<Boolean> source) {
    return source
        .timeout(Duration.ofMillis(300))
        .onErrorResume(error -> Mono.just(false))
        .defaultIfEmpty(false);
}
```

Then:
- `Mono.just(true)` → emits `true`.
- `Mono.just(false)` → emits `false`.
- `Mono.empty()` → emits `false`.
- `Mono.error(ex)` → emits `false`.
- `Mono.never()` → times out → emits `false`.

Never use an **OR combiner** that accidentally grants access when a mandatory policy abstains. When multiple advisors exist, define clearly which checks are mandatory: tenant membership, resource owner/share, classification, MFA, and scoped admin roles. Composition must uphold **deny by default**.

### 3.1. Do Not Swallow Exceptions into Abstain

```java
// Dangerous COUNTEREXAMPLE on a decision stream.
return pdp.check(user, document)
    .onErrorComplete();
```

`onErrorComplete()` turns an error into an empty completion with no value. On an authorization stream, that becomes **ABSTAIN**, not an explicit deny.

An even worse counterexample:

```java
// COUNTEREXAMPLE: FAIL-OPEN.
return pdp.check(user, document)
    .onErrorReturn(true)
    .defaultIfEmpty(true);
```

If the PDP loses connectivity or lacks a rule, the code returns **true**. This cannot be treated as a safe way to preserve availability for sensitive documents.

### 3.2. Do Not Let Exceptions Destroy Observability

A security adapter can fail closed while still recording the cause:

```java
return pdp.check(user, document)
    .timeout(Duration.ofMillis(300))
    .doOnError(error -> log.warn(
        "PDP unavailable for resourceId={}", document.id(), error))
    .onErrorResume(error -> Mono.just(false))
    .defaultIfEmpty(false);
```

`doOnError` only observes/logs; `onErrorResume` replaces the error stream with a DENY decision. Production systems should categorize `POLICY_DENY`, `POLICY_ABSTAIN`, `POLICY_TIMEOUT`, and `POLICY_ERROR` while avoiding logging tokens or sensitive document content.

## 4. Timing of @PreAuthorize and @PostAuthorize

`@PreAuthorize` checks **before the target method executes**. `@PostAuthorize` checks the **result after the method** and before delivering it to the caller (for publishers, evaluating the emitted value). They are not equivalent with respect to side effects.

```text
Subscriber
    |
    v
@PreAuthorize
    | false -> deny/error, target does not run
    | empty -> abstain; do not use to enforce deny
    | error -> failure; must fail-closed
    v allow
Target Mono/Flux
    | value -> @PostAuthorize(returnObject)
    | empty -> no Doc to check owner
    | error -> data/pipeline error
    v
Caller receives data / 403 / 404 / 5xx per contract
```

This is a **logical diagram**. Exact handling of empty and result values depends on return type, interceptor, and Spring Security version; do not assume a post-check runs when a publisher emits no value.

### 4.1. Read-Only Methods Can Use Post-Checks

```java
@PreAuthorize("@guard.canEnter(authentication, #tenant, #id)")
@PostAuthorize(
    "@guard.canReadReturned(authentication, returnObject)"
)
public Mono<Document> inspect(
        @P("tenant") String tenant,
        @P("id") Long id) {
    return repository.fetch(tenant, id);
}
```

`canEnter` blocks wrong tenants before fetching. `canReadReturned` verifies owner/share against the **actual** emitted document. If post-denied, the caller never sees the document, though the repository **may have already read it**. That is why `@PostAuthorize` alone cannot reduce backend reads or guard mutations.

### 4.2. Mutations Must Be Pre-Checked

```java
@PreAuthorize("@guard.canEdit(authentication, #tenant, #id)")
public Mono<Document> rename(
        @P("tenant") String tenant,
        @P("id") Long id, String title) {
    return Mono.defer(() -> repository.rename(tenant, id, title));
}
```

If policy denies, write logic must not execute. With a real database, combine guarded updates, tenant predicates, optimistic locking, and transactions. **Never** rely solely on `@PostAuthorize` for `DELETE`, ownership transfers, sending emails, or publishing events: denying after side effects does not roll them back.

### 4.3. Empty Data Does Not Replace Permissions

For a read that passed pre-check, the repository can still return `Mono.empty()` if the record was deleted or no match exists. Appropriate lookup mapping:

```java
return repository.findVisibleByTenantAndId(tenant, id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

This snippet requires repository code and imports to run. Returning 404 **after enforcing scope** is completely different from returning `Mono.empty()` in a policy and assuming the user lacks permission.

### 4.4. Empty Lists Are Not Forbidden

```java
@PreAuthorize("@guard.canList(authentication, #tenant)")
public Flux<Document> list(String tenant) {
    return repository.findVisibleDocuments(tenant);
}
```

If the user has LIST permission yet zero readable documents exist, `Flux.empty()` is a valid result, usually HTTP **200 `[]`**. Conversely, if the user lacks LIST permission, `@PreAuthorize` denies and usually returns 403.

## 5. Mapping to HTTP: 401, 403, 404, 503, 200 `[]`

| Event | Common Status | Distinction to Keep Clear |
|---|---|---|
| Anonymous hits endpoint requiring login | 401 (HTTP Basic/Bearer) or redirect | Authentication incomplete |
| Authenticated caller denied by method | 403 | Principal exists, lacks permission |
| Record absent after lookup in valid scope | 404 | Data empty |
| Cross-tenant ID | 403 or deliberate 404 | Consistent anti-enumeration |
| PDP timeout/unavailable | Fail-closed 403 or fail-closed 503 | Return no content; emit error metrics |
| Database failure | 5xx | Never disguise as "not found" |
| Permitted LIST with zero items | 200 `[]` | Zero results, not denial |
| POST blocked by CSRF filter | 403 | Does not mean method policy denied |

`ExceptionTranslationWebFilter` and custom handlers affect the HTTP status. **You cannot map every error signal to 403** and keep accurate semantics. In the demo, PDP errors map to `false` so Spring Security returns 403; production systems may choose 503 so clients know availability is degraded while still blocking access.

## 6. Java 17, Spring Boot 3.5.6, Spring Security 6.5.x Demo Code

A WebFlux project with `DecisionGateway` simulating a PDP returning **true**, **false**, **`Mono.empty()`**, and **`Mono.error()`**; `DocumentGate` normalizes them to an explicit `Boolean`. It uses `@PreAuthorize` for READ/EDIT and pairs `@PostAuthorize` on a read-only `INSPECT` endpoint. `WebTestClient` tests HTTP outcomes and `StepVerifier` asserts exact `Mono` signals.

### 6.1. Directory Tree

```text
reactive-decision-demo/
  pom.xml
  src/main/java/com/example/decision/
    DecisionApplication.java
    SecurityConfig.java
    Document.java
    DocumentCatalog.java
    DecisionGateway.java
    SimulatedDecisionGateway.java
    DocumentGate.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/decision/
    ReactiveDecisionTest.java
```

### 6.2. pom.xml

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
  <artifactId>reactive-decision-demo</artifactId>
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

Only the WebFlux starter is included; **do not** add the Servlet MVC starter. Spring Boot manages the compatible Spring Security version. Tests use `mockUser`/`@WithMockUser` and do not verify real JWTs or passwords.

### 6.3. Application and SecurityConfig

**`src/main/java/com/example/decision/DecisionApplication.java`**

```java
package com.example.decision;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DecisionApplication {
    public static void main(String[] args) {
        SpringApplication.run(DecisionApplication.class, args);
    }
}
```

**`src/main/java/com/example/decision/SecurityConfig.java`**

```java
package com.example.decision;

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
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/api/tenants/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

The HTTP chain requires authentication; service-level annotations enforce tenant and object permissions. CSRF remains enabled by default, so `PUT` tests pass `csrf()`.

### 6.4. Document Record

**`src/main/java/com/example/decision/Document.java`**

```java
package com.example.decision;

public record Document(
    Long id, String tenant, String owner,
    String state, String title) {}
```

### 6.5. DocumentCatalog: Canonical Data, Fetch/Update Counters

**`src/main/java/com/example/decision/DocumentCatalog.java`**

```java
package com.example.decision;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentCatalog {
    private final ConcurrentMap<Long, Document> docs =
        new ConcurrentHashMap<>();

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice","bob","manager"),
        "t2", Set.of("carol","dave")
    );

    private final Set<String> adminBindings = Set.of(
        "t1:manager"
    );

    private final Set<String> viewers = Set.of("101:bob");
    private final AtomicInteger fetched = new AtomicInteger();
    private final AtomicInteger updated = new AtomicInteger();

    public DocumentCatalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        docs.put(101L, new Document(
            101L,"t1","alice","ACTIVE","Owner memo"));
        docs.put(102L, new Document(
            102L,"t1","alice","ACTIVE","Private plan"));
        docs.put(103L, new Document(
            103L,"t1","alice","ACTIVE","ABSTAIN example"));
        docs.put(104L, new Document(
            104L,"t1","alice","ACTIVE","ERROR example"));
        docs.put(105L, new Document(
            105L,"t1","alice","ACTIVE","DENY example"));
        docs.put(106L, new Document(
            106L,"t1","alice","ACTIVE","ALLOW example"));
        docs.put(107L, new Document(
            107L,"t1","alice","ARCHIVED","Old report"));
        docs.put(201L, new Document(
            201L,"t2","carol","ACTIVE","South report"));
        fetched.set(0);
        updated.set(0);
    }

    public Document peek(Long id) {
        return id == null ? null : docs.get(id);
    }

    public boolean member(String tenant, String user) {
        Set<String> users = members.get(tenant);
        return users != null && user != null
            && users.contains(user);
    }

    public boolean adminBinding(String tenant, String user) {
        return tenant != null && user != null
            && adminBindings.contains(tenant + ":" + user);
    }

    public boolean viewer(Long id, String user) {
        return id != null && user != null
            && viewers.contains(id + ":" + user);
    }

    public List<Document> forTenant(String tenant) {
        return docs.values().stream()
            .filter(doc -> doc.tenant().equals(tenant))
            .sorted(Comparator.comparing(Document::id))
            .toList();
    }

    public Mono<Document> fetch(String tenant, Long id) {
        return Mono.defer(() -> {
            fetched.incrementAndGet();
            Document doc = peek(id);
            return doc != null && doc.tenant().equals(tenant)
                ? Mono.just(doc) : Mono.empty();
        });
    }

    public synchronized Document rename(
            String tenant, Long id, String title) {
        Document old = peek(id);
        if (old == null
                || !old.tenant().equals(tenant)
                || !"ACTIVE".equals(old.state())) {
            return null;
        }
        Document changed = new Document(
            id, old.tenant(), old.owner(), old.state(), title);
        docs.put(id, changed);
        updated.incrementAndGet();
        return changed;
    }

    public int fetchedCount() { return fetched.get(); }
    public int updatedCount() { return updated.get(); }
}
```

Seeded data:
- Alice/Bob/manager belong to tenant `t1`; Carol/Dave belong to `t2`.
- Bob has VIEWER access on Document#101, but cannot read Document#102.
- Document#103 receives PDP **ABSTAIN**, #104 **ERROR**, #105 **DENY**, #106 **ALLOW**.
- Document#107 is `ARCHIVED`; canonical data checks alone deny it.
- Document#201 belongs to tenant `t2`.
- `fetchedCount` tracks how many times the read/inspect body was subscribed to.
- `updatedCount` proves no mutation occurs when pre-checks deny.

All fixtures are in-memory; production requires a data store with tenant-qualified queries, transactions, and consistency guarantees.

### 6.6. DecisionGateway with Four Signal Types

**`src/main/java/com/example/decision/DecisionGateway.java`**

```java
package com.example.decision;

import reactor.core.publisher.Mono;

public interface DecisionGateway {
    Mono<Boolean> check(
        String principal, String action, Document doc);
}
```

**`src/main/java/com/example/decision/SimulatedDecisionGateway.java`**

```java
package com.example.decision;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class SimulatedDecisionGateway implements DecisionGateway {
    @Override
    public Mono<Boolean> check(
            String principal, String action, Document doc) {
        return switch (doc.id().intValue()) {
            case 103 -> Mono.empty(); // ABSTAIN.
            case 104 -> Mono.error(
                new IllegalStateException("PDP unavailable"));
            case 105 -> Mono.just(false); // DENY.
            default -> Mono.just(true);   // ALLOW.
        };
    }
}
```

This is a **simulated PDP**, not an OPA/OpenFGA HTTP client. The key takeaway is **how publisher states behave**. A real remote PDP requires service-to-service authentication, response schema validation, timeouts, caching, and auditing.

### 6.7. DocumentGate: Fail-Closed Policy

**`src/main/java/com/example/decision/DocumentGate.java`**

```java
package com.example.decision;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("gate")
public class DocumentGate {
    private static final Logger LOG =
        LoggerFactory.getLogger(DocumentGate.class);

    private final DocumentCatalog catalog;
    private final DecisionGateway gateway;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocumentGate(
            DocumentCatalog catalog, DecisionGateway gateway) {
        this.catalog = catalog;
        this.gateway = gateway;
    }

    private static boolean authority(
            Authentication auth, String required) {
        if (auth == null) return false;
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) return true;
        }
        return false;
    }

    private boolean authenticated(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !trust.isAnonymous(auth);
    }

    private boolean admin(Authentication auth, String tenant) {
        return authority(auth, "ROLE_TENANT_ADMIN")
            && catalog.adminBinding(tenant, auth.getName());
    }

    // Canonical tenant, membership, and resource state.
    public boolean canEnter(
            Authentication auth, String tenant, Long id) {
        if (!authenticated(auth)
                || tenant == null || tenant.isBlank()) {
            return false;
        }
        Document doc = catalog.peek(id);
        return doc != null
            && tenant.equals(doc.tenant())
            && "ACTIVE".equals(doc.state())
            && catalog.member(tenant, auth.getName());
    }

    private boolean localRead(Authentication auth, Document doc) {
        return auth.getName().equals(doc.owner())
            || catalog.viewer(doc.id(), auth.getName())
            || admin(auth, doc.tenant());
    }

    private Mono<Boolean> remote(
            Authentication auth, Document doc, String action) {
        return Mono.defer(() ->
                gateway.check(auth.getName(), action, doc))
            .timeout(Duration.ofMillis(300))
            .doOnError(error -> LOG.warn(
                "Decision error action={} id={}",
                action, doc.id(), error))
            .onErrorResume(error -> Mono.just(false))
            .defaultIfEmpty(false);
    }

    public Mono<Boolean> canRead(
            Authentication auth, String tenant, Long id) {
        if (!canEnter(auth, tenant, id)) {
            return Mono.just(false);
        }
        Document doc = catalog.peek(id);
        if (!localRead(auth, doc)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "read");
    }

    public Mono<Boolean> canReadReturned(
            Authentication auth, Document doc) {
        if (doc == null
                || !canEnter(auth, doc.tenant(), doc.id())) {
            return Mono.just(false);
        }
        Document current = catalog.peek(doc.id());
        if (current == null || !current.equals(doc)
                || !localRead(auth, doc)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "read");
    }

    public Mono<Boolean> canEdit(
            Authentication auth, String tenant, Long id) {
        if (!canEnter(auth, tenant, id)) {
            return Mono.just(false);
        }
        Document doc = catalog.peek(id);
        boolean editorOwner =
            auth.getName().equals(doc.owner())
            && authority(auth, "ROLE_EDITOR");
        if (!editorOwner && !admin(auth, tenant)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "edit");
    }

    public boolean canList(
            Authentication auth, String tenant) {
        return authenticated(auth)
            && tenant != null
            && catalog.member(tenant, auth.getName())
            && (authority(auth, "ROLE_READER")
                || admin(auth, tenant));
    }
}
```

Key points:
1. The client supplies `tenant` in the URL, yet `canEnter` verifies canonical record/tenant and server-side membership.
2. `READ` also requires owner/share/tenant-scoped admin.
3. `remote` uses `defaultIfEmpty(false)` for ABSTAIN.
4. `onErrorResume(...false)` handles ERROR, including timeouts from `timeout(...)`.
5. No `block()`, `onErrorReturn(true)`, or `defaultIfEmpty(true)`.
6. Methods invoked via SpEL return **explicit true/false** or a `Mono<Boolean>` that always emits a boolean; abstain is never intentionally leaked to the interceptor.
7. `canReadReturned` validates the exact returned object while cross-checking the canonical snapshot.
8. `canList` separates list permission from per-item permissions.

In production, logs should include correlation IDs, policy versions, and reason categories. Never return stack traces, JWTs, owner details, or internal PDP details to clients. Use non-blocking clients for remote policies and R2DBC for data access in high-throughput reactive apps.

### 6.8. Service: Pre-Deny, Post-Deny, Empty Data

**`src/main/java/com/example/decision/DocumentService.java`**

```java
package com.example.decision;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {
    private final DocumentCatalog catalog;
    private final DocumentGate gate;

    public DocumentService(
            DocumentCatalog catalog, DocumentGate gate) {
        this.catalog = catalog;
        this.gate = gate;
    }

    @PreAuthorize("@gate.canRead(authentication, #tenant, #id)")
    public Mono<Document> read(
            @P("tenant") String tenant, @P("id") Long id) {
        return catalog.fetch(tenant, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found")));
    }

    // Read-only: pre-check scope, then post-check emitted value.
    @PreAuthorize("@gate.canEnter(authentication, #tenant, #id)")
    @PostAuthorize(
        "@gate.canReadReturned(authentication, returnObject)")
    public Mono<Document> inspect(
            @P("tenant") String tenant, @P("id") Long id) {
        return catalog.fetch(tenant, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found")));
    }

    private Flux<Document> visible(String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .flatMapMany(context ->
                Flux.fromIterable(catalog.forTenant(tenant))
                    .filterWhen(doc -> gate.canRead(
                        context.getAuthentication(),
                        tenant, doc.id())));
    }

    @PreAuthorize("@gate.canList(authentication, #tenant)")
    public Flux<Document> list(@P("tenant") String tenant) {
        return visible(tenant);
    }

    @PreAuthorize("@gate.canList(authentication, #tenant)")
    public Mono<Document> lookup(
            @P("tenant") String tenant, String title) {
        return visible(tenant)
            .filter(doc -> doc.title().equals(title))
            .next();
    }

    // Mutations must have a pre-check, not only a post-check.
    @PreAuthorize("@gate.canEdit(authentication, #tenant, #id)")
    public Mono<Document> rename(
            @P("tenant") String tenant,
            @P("id") Long id, String title) {
        return Mono.defer(() -> {
            if (title == null || title.isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title required"));
            }
            Document changed = catalog.rename(tenant, id, title);
            if (changed == null) {
                return Mono.error(
                    new AccessDeniedException("Resource changed"));
            }
            return Mono.just(changed);
        });
    }
}
```

**From the code:**
- `read` on Doc#103/104/105 is **pre-denied**, so `fetch` never runs (`fetchedCount == 0`).
- `inspect` for Bob on Doc#102 passes the scope pre-check and fetches the doc, yet is post-denied due to missing READ permission (`fetchedCount == 1`, and the caller still receives 403).
- `list` for Dave in `t2` with `ROLE_READER` has no permitted items: returns `Flux.empty()`, and the controller returns 200 `[]`.
- `lookup` is authorized, yet finds no matching title in the visible set: returns `Mono.empty()`, which the controller maps to 404.
- `rename` executes write logic only after the pre-check; if the PDP abstains or errors, `updatedCount == 0`.

**Limitation:** `visible(...)` runs `filterWhen` over all in-memory tenant docs and may issue multiple PDP calls. On large databases, filter permissions inside the query/batch before pagination and counting; this demo illustrates signal semantics only.

### 6.9. Controller: Mapping Data Outcomes

**`src/main/java/com/example/decision/DocumentController.java`**

```java
package com.example.decision;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants")
public class DocumentController {
    public record RenameBody(String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{tenant}/docs/{id}")
    public Mono<Document> read(
            @PathVariable String tenant, @PathVariable Long id) {
        return service.read(tenant, id);
    }

    @GetMapping("/{tenant}/docs/{id}/inspect")
    public Mono<Document> inspect(
            @PathVariable String tenant, @PathVariable Long id) {
        return service.inspect(tenant, id);
    }

    @GetMapping("/{tenant}/docs")
    public Flux<Document> list(@PathVariable String tenant) {
        return service.list(tenant);
    }

    @GetMapping("/{tenant}/lookup")
    public Mono<Document> lookup(
            @PathVariable String tenant,
            @RequestParam String title) {
        return service.lookup(tenant, title)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "No visible document")));
    }

    @PutMapping("/{tenant}/docs/{id}")
    public Mono<Document> rename(
            @PathVariable String tenant,
            @PathVariable Long id,
            @RequestBody RenameBody input) {
        return service.rename(tenant, id, input.title());
    }
}
```

Neither owner nor edit permissions are taken from the body. The `lookup` endpoint returns 404 only after `@PreAuthorize` verifies LIST permission. GET `docs/{id}` returns 403 for cross-tenant IDs per demo policy; production APIs may unify on 404 to reduce enumeration.

## 7. JUnit, WebTestClient, and StepVerifier Testing Each Signal

**`src/test/java/com/example/decision/ReactiveDecisionTest.java`**

```java
package com.example.decision;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveDecisionTest {
    @Autowired ApplicationContext context;
    @Autowired DocumentCatalog catalog;
    @Autowired DocumentGate gate;
    @Autowired DecisionGateway gateway;
    @Autowired DocumentService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        catalog.reset();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private static String path(String tenant, long id) {
        return "/api/tenants/" + tenant + "/docs/" + id;
    }

    private WebTestClient as(String username, String... roles) {
        String[] actual = roles.length == 0
            ? new String[]{"USER"} : roles;
        return client.mutateWith(mockUser(username).roles(actual));
    }

    private WebTestClient asCsrf(
            String username, String... roles) {
        return as(username, roles).mutateWith(csrf());
    }

    private static Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void anonymousReadGets401() {
        client.get().uri(path("t1",101))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownerWithAllowReadsDocument() {
        as("alice").get().uri(path("t1",101))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Owner memo");
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void sharedViewerReadsDocument() {
        as("bob").get().uri(path("t1",101))
            .exchange().expectStatus().isOk();
    }

    @Test
    void crossTenantRequestDeniedBeforeFetch() {
        as("alice").get().uri(path("t2",201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void forgedTenantPathDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void archivedDocumentDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",107))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void unknownDocumentDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",999))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void abstainBecomesDenyBeforeFetch() {
        as("alice").get().uri(path("t1",103))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void errorBecomesDenyBeforeFetch() {
        as("alice").get().uri(path("t1",104))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void explicitDenyBeforeFetch() {
        as("alice").get().uri(path("t1",105))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void explicitAllowPermitsFetch() {
        as("alice").get().uri(path("t1",106))
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void missingShareDeniedAtPreCheck() {
        as("bob").get().uri(path("t1",102))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void postDeniedAfterFetch() {
        as("bob").get().uri(path("t1",102)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postAllowsSharedViewer() {
        as("bob").get().uri(path("t1",101)+"/inspect")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postAbstainFailsClosedAfterFetch() {
        as("alice").get().uri(path("t1",103)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postErrorFailsClosedAfterFetch() {
        as("alice").get().uri(path("t1",104)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void fakeAdminRoleWithoutTenantBindingDenied() {
        as("bob","TENANT_ADMIN")
            .get().uri(path("t1",102))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void boundAdminReadsOwnTenant() {
        as("manager","TENANT_ADMIN")
            .get().uri(path("t1",102))
            .exchange().expectStatus().isOk();
    }

    @Test
    void boundAdminCannotCrossTenant() {
        as("manager","TENANT_ADMIN")
            .get().uri(path("t2",201))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listWithoutRoleIsForbidden() {
        as("bob").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listFiltersUnreadableDocuments() {
        as("bob","READER").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void emptyFluxIsNotForbidden() {
        as("dave","READER").get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void allowedLookupButEmptyMonoBecomes404() {
        as("dave","READER")
            .get().uri("/api/tenants/t2/lookup?title=missing")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void listPermissionMissingDoesNotMeanEmpty() {
        as("dave").get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void ownerEditorCanRenameWithCsrf() {
        asCsrf("alice","EDITOR")
            .put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Updated\"}")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.updatedCount());
    }

    @Test
    void noEditRolePreventsMutation() {
        asCsrf("alice").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void viewerCannotEditEvenWithRole() {
        asCsrf("bob","EDITOR").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void abstainBeforeEditNeverWrites() {
        asCsrf("alice","EDITOR").put().uri(path("t1",103))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void errorBeforeEditNeverWrites() {
        asCsrf("alice","EDITOR").put().uri(path("t1",104))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void csrfBlocksOtherwiseAllowedMutation() {
        as("alice","EDITOR").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void rawAbstainPublisherHasNoValue() {
        StepVerifier.create(
            gateway.check("alice","read",catalog.peek(103L)))
            .verifyComplete();
    }

    @Test
    void rawErrorPublisherEmitsError() {
        StepVerifier.create(
            gateway.check("alice","read",catalog.peek(104L)))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void normalizedAbstainYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",103L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedErrorYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",104L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedExplicitDenyYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",105L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedAllowYieldsTrue() {
        StepVerifier.create(gate.canRead(alice(),"t1",106L))
            .expectNext(true).verifyComplete();
    }

    @Test
    @WithMockUser(username = "bob")
    void directServicePostDenyEmitsAccessDenied() {
        StepVerifier.create(service.inspect("t1",102L))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServicePreDenyEmitsAccessDenied() {
        StepVerifier.create(service.read("t1",103L))
            .expectError(AccessDeniedException.class)
            .verify();
        assertEquals(0, catalog.fetchedCount());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result from source code:** the tests accurately verify allow/deny/abstain/error, HTTP 401/403/404/200 `[]`, pre- vs. post-fetch behavior, and zero writes on pre-deny. This is an **authored and reviewed test suite, not yet executed via Maven**; treat assertions as verified only after running in an environment with matching dependencies.

Tests use `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` so requests pass through WebFlux filters; `mockUser` supplies a mock principal. `StepVerifier.verifyComplete()` on a raw `Mono.empty()` proves only that the publisher completed without emitting a value; `expectNext(false)` proves the adapter **emitted an explicit deny decision**; `expectError(...)` proves an error signal occurred. These are three distinct states and are not interchangeable.

## 8. Analyzing Key Outcomes

### 8.1. Why Was Doc#103 Denied Before Fetch?

For Alice:
- Authentication is valid; `t1` membership matches; document is `ACTIVE` and Alice is the owner.
- Gateway returns `Mono.empty()` (ABSTAIN).
- `DocumentGate.remote` applies `defaultIfEmpty(false)`.
- `@PreAuthorize` receives `false` → blocks the target service.
- HTTP returns 403, `fetchedCount == 0`.

If you remove `defaultIfEmpty(false)`, the application falls back to the interceptor's abstain semantics. Never rely on that behavior to enforce denial.

### 8.2. Why Was Doc#104 Also Denied Before Fetch?

Gateway emits `IllegalStateException("PDP unavailable")` via `Mono.error`. `doOnError` records the metric/log; `onErrorResume(...Mono.just(false))` keeps it fail-closed. The request gets no data, yet monitoring must see this as a **PDP outage**, not an intentional permission policy denial.

### 8.3. Why Was inspect Doc#102 Read Before Returning 403?

`inspect` pre-checks only tenant/state, so Bob in `t1` clears that stage. `catalog.fetch` emits Document#102, then `@PostAuthorize` detects Bob is not owner/share/admin. The result is withheld from the caller while the fetch counter increments. That is the **effect of post-authorization**, not a rollback.

### 8.4. Why Did Dave's t2 LIST Return 200 `[]` While LOOKUP Returned 404?

Dave holds `ROLE_READER` and `t2` membership, so he is allowed to invoke both operations. However, Carol owns Doc#201 and Dave has no share; per-object filtering yields empty results.
- `Flux.empty()` from `LIST` → empty JSON array, 200.
- `Mono.empty()` from `LOOKUP` → controller `switchIfEmpty(...NOT_FOUND)`, 404.
- If Dave lacked `ROLE_READER` → `@PreAuthorize` denies with 403.

Never use `200 []` as a substitute for 403, or 403 as a substitute for every empty result.

## 9. Production: Error Signals, Consistency, and Large Datasets

### 9.1. Queries Scoped by Tenant and Permission

In the demo, `catalog` is in RAM. In a real database, avoid `findById(id)` when multiple tenants share storage. SQL template:

```sql
SELECT d.id, d.tenant_id, d.owner_id, d.state, d.title
FROM document d
WHERE d.id = :documentId
  AND d.tenant_id = :verifiedTenant
  AND d.state = 'ACTIVE';
```

After a tenant-qualified query, still enforce owner/share/admin action permissions. For large lists, push `READ` conditions into the query before pagination and counting, rather than fetching everything and calling `Flux.filterWhen` with a PDP RPC per record. That eliminates N+1 calls, prevents broken pagination, and reduces metadata leaks.

### 9.2. Conditional Updates

```sql
UPDATE document
SET title = :title
WHERE id = :documentId
  AND tenant_id = :verifiedTenant
  AND owner_id = :authenticatedPrincipal
  AND state = 'ACTIVE';
```

This SQL template is restricted to the owner; if `EDITOR` shares or admins exist, add matching tenant/action predicates. Verify affected-row count `= 1` along with versions/transactions to mitigate TOCTOU. `@PreAuthorize` does not make SQL atomic with PDP decisions on its own.

### 9.3. Do Not Stream Data First and Check Afterward

If a `Flux<Document>` sends 100 records over HTTP and hits an error on item 101, the response already contains 100 records. Therefore:
- Authorize the operation before streaming.
- Filter/restrict the source query so cross-tenant rows are never read or emitted.
- For all-or-nothing semantics, validate scope before streaming while watching memory bounds.
- Never use `onErrorContinue` casually to skip permission errors.
- For per-row remote PDPs, use batch checks, guarded SQL, or a reviewed model.

### 9.4. Transactions and Side Effects

`@PostAuthorize` on a `Mono` method that already wrote to the DB does not roll back emails, webhooks, message brokers, or transactions. Writes/deletes must use `@PreAuthorize`, guarded updates, `ReactiveTransactionManager`/`TransactionalOperator` when using R2DBC, and a transactional outbox for external events.

### 9.5. Timeouts, Retries, and Caching

A PDP can return `Mono.never()` if a dependency hangs. Without a timeout, the subscription can hang forever. Configure bounded timeouts, capped retries, circuit breakers, and alerts. For caches:
- Key by principal, tenant, resource, action, and policy version.
- Define revocation SLAs and invalidation.
- Stale cache entries must never recreate permissions after membership revocation.
- Never fall back to allow on expiration or PDP downtime unless backed by an explicit security proof.

### 9.6. Do Not Block the Event Loop

Method authorization beans can return `Mono<Boolean>`. Never call `block()` inside SpEL or on the Reactor event loop to force a decision from a DB or HTTP call. Use non-blocking clients, `timeout`, and publishers. When a data source only offers blocking JDBC, design a bounded scheduler and thread pool or migrate to R2DBC; never run blocking calls unguarded on the event loop.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating PDP empty as guaranteed `false` | Misinterpreted ABSTAIN | `defaultIfEmpty(false)` |
| Converting PDP error with `onErrorComplete()` | Error turns into abstain | `onErrorResume(...false)` + audit |
| `onErrorReturn(true)` | Fail-open | Never allow on outage |
| HTTP 200 from PDP = allow | Response missing `result`/`allowed` passes | Explicit boolean `true` only |
| Repository empty = access denied | Confusing 404 with 403 | Clear contract by empty source |
| `Flux.empty()` = user lacks LIST permission | Confusing `200 []` with 403 | Authorize LIST beforehand |
| Swallowing DB error into empty | Hides outages and cache bugs | Preserve 5xx signals |
| `@PostAuthorize` for mutations | Side effects happen before deny | `@PreAuthorize` and guarded DML |
| Protecting HTTP routes only | Object-level BOLA/IDOR | Tenant + owner/share action checks |
| Calling `block()` in policies | Stalls event loop | Non-blocking `Mono<Boolean>` |
| `Mono.never()` without timeout | Hung requests | Bounded timeout |
| Unbounded retries | PDP outage becomes retry storm | Retry budget |
| `filterWhen` after pagination | N+1, wrong page/counts | SQL scoping before paging |
| Ignoring Reactor Context | Wrong/lost principal across async | `ReactiveSecurityContextHolder` |
| Cache missing tenant/action/version | Stale permissions, cross-tenant | Complete cache keys and revoke invalidation |
| Testing only `true`/`false` | Misses abstain/error bugs | Test all 4 signals and pre/post counters |
| Treating post-deny as rollback | Updates/emails may already have run | Pre-checks, transactions, outbox |

## 11. Review Checklist

- [ ] Clearly separate **empty data**, **decision abstain**, and **error signals**.
- [ ] `@EnableReactiveMethodSecurity` is enabled and methods are called through Spring proxies.
- [ ] `Authentication` comes from Reactor/Spring Security, never self-asserted headers.
- [ ] Remote decision contract grants ALLOW only on explicit `true`.
- [ ] `Mono.empty()`, errors, and timeouts from the PDP become explicit denies in mandatory policies.
- [ ] Logs/metrics distinguish policy deny, abstain, timeout, and error.
- [ ] No `defaultIfEmpty(true)` or `onErrorReturn(true)` in any authorization path.
- [ ] `@PreAuthorize` precedes writes, deletes, and external side effects.
- [ ] `@PostAuthorize` is used only where reading the result before authorizing the response is acceptable.
- [ ] Empty lookup/list results map to 404 / `200 []` per business contract.
- [ ] HTTP 401/403/404/503 are tested with the actual authentication mechanism.
- [ ] Canonical tenant, membership, and owner/share are verified.
- [ ] Never query all tenants and filter after pagination.
- [ ] Guarded DB updates, affected-row checks, and concurrency controls are in place.
- [ ] `WebTestClient` negative tests cover roles, tenants, and CSRF.
- [ ] `StepVerifier` tests distinguish value, empty, error, and `false`.
- [ ] Tested PDP disconnect, abstain, timeout, permission revocation, and stale cache scenarios.
- [ ] Unauthorized data is never streamed prior to checks.
- [ ] Blocking SDKs are never invoked on the WebFlux event loop.

## 12. Self-Check Questions

**1.** Is `Mono.empty()` from a policy bean the same as `Mono.just(false)`?

**Answer:** No. Spring Security 6.5 can interpret it as abstain. If an explicit allow is required, normalize empty → `false`.

**2.** Is `Mono.error(TimeoutException)` equivalent to a valid deny decision?

**Answer:** No, it is a failure signal. The system must fail closed while still recording it as an outage/timeout rather than a normal policy denial.

**3.** Why is `onErrorComplete()` dangerous in a decision stream?

**Answer:** It turns errors into empty/abstain, which can skip mandatory denial in a combiner lacking an explicit rule.

**4.** A user has LIST permission, yet no matching documents exist. What should be returned?

**Answer:** Usually `200 []`, because `Flux.empty()` after authorizing LIST represents zero items.

**5.** Reading a document returns `Mono.empty()` after verifying tenant and permissions. Can you return 404?

**Answer:** Yes, if the API contract defines not-found. Never use this result in place of an authorization decision for an unauthorized user.

**6.** A post-check denies after the repository already fetched the record; can you assume the repository read nothing?

**Answer:** No. `@PostAuthorize` checks after a result is produced; data may already have been read, and prior side effects do not roll back automatically.

**7.** How do `StepVerifier.verifyComplete()` on a raw empty PDP and `expectNext(false).verifyComplete()` on a normalized decision differ?

**Answer:** The first emits no value; the second emits an explicit deny and then completes. They represent different Reactor semantics.

## 13. Official Documentation

- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`/`@PostAuthorize`, beans returning `Mono<Boolean>`, and `Mono.empty()` as abstain.
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html): `@WithMockUser`, `StepVerifier`.
- [Spring Security 6.5 — WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `springSecurity()`, `bindToApplicationContext`.
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, roles/authorities.
- [Spring Security 6.5 — Reactive Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()`.
- [Spring Security 6.5 — PostAuthorizeReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): after-method authorization manager.
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorReturn`, `onErrorResume`, and `onErrorComplete`.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier`, asserting completion/error/value.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): protecting every resource ID.

**Remember:** In Reactive Method Security, **ABSTAIN is not DENY**, **ERROR is not an authorization decision**, and **empty data is not automatically 403**. Permit only on an **explicit allow**, normalize empty/error/timeout from the PDP to fail closed, guard mutations with `@PreAuthorize`, use `@PostAuthorize` appropriately for read-only results, and verify each signal separately with `StepVerifier` alongside HTTP statuses via `WebTestClient`.