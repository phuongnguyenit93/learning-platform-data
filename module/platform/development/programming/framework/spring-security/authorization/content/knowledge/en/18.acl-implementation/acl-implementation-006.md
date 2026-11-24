# `AclPermissionEvaluator` and `hasPermission` Integration in Spring Security

## 1. The Problem: A General Authority Does Not Decide Access to Individual Documents

An API exposes `readDocument(11L)`. The caller is logged in and has the `document:read` authority. However, in a document management system:

- `alice` may read document `11` but not document `12`.
- `bob` may read both `11` and `12` because matching ACEs exist.
- `carol` has a `READ` ACE on document `13` yet **lacks the general `document:read` authority**; the application wants her denied.
- `root` is the ACL owner of several documents yet **does not automatically hold a `READ` ACE**.
- A client can submit an object claiming an owner, title, and ID; client-submitted metadata is untrusted for granting access.

`hasAuthority('document:read')` only answers whether the caller has read capability **at the feature level**. It does not answer whether the caller has `READ` permission on **Document#11**. Spring Security provides `hasPermission(...)` for per-object authorization.

`AclPermissionEvaluator` is the `PermissionEvaluator` implementation provided by the **spring-security-acl** module. It connects **Spring Method Security**'s `hasPermission` expressions with ACL data loaded via `AclService` and **ACE/SID/Permission** evaluation.

Lesson objectives:

1. Understand the **two `hasPermission` overloads** and when each is chosen.
2. Distinguish `Authentication`, `Sid`, `ObjectIdentity`, `Permission`, `Acl`, and `AccessControlEntry`.
3. Register `AclPermissionEvaluator` on `DefaultMethodSecurityExpressionHandler` properly, rather than merely defining a bean.
4. Understand `ObjectIdentityImpl`, the domain object's `getId()` requirement, and `targetType` precision.
5. Write `@PreAuthorize`, `@PostAuthorize`, and `@PostFilter` with `hasPermission` expressions.
6. Run a Java 17+ / Spring Boot 3.5.x demo using the **real ACL engine** with an in-memory `AclService` so no database is required.
7. Write integration tests proving the object overload, ID overload, authority + ACL AND combination, denials, and forged object payloads.
8. Transition the architecture to real JDBC ACLs while controlling tenancy, caching, consistency, and performance.

**Scope:** Spring Security 6.5.x with Spring Boot 3.5.x, with Method Security backed by Spring AOP proxies. The demo has no HTTP endpoints; `@PreAuthorize` still executes when invoking a Spring-managed service with a valid `SecurityContext`. When using Spring Security 7.x, cross-check the API docs for your deployment version.

## 2. What Is `AclPermissionEvaluator`—and What Is It Not?

The root `PermissionEvaluator` interface belongs to package `org.springframework.security.access`:

```java
public interface PermissionEvaluator {

    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        java.io.Serializable targetId,
        String targetType,
        Object permission
    );
}
```

This is an **abbreviated API signature** for learning, not a standalone Java file. `AclPermissionEvaluator` lives in package `org.springframework.security.acls` and implements both signatures.

`AclPermissionEvaluator` **does not decide on its own** who an owner is from controller payloads, does not verify passwords, and does not auto-create ACLs. It uses:

- `AclService` to read the ACL bound to an `ObjectIdentity`.
- `ObjectIdentityRetrievalStrategy` to derive an identity from a **domain object instance**.
- `ObjectIdentityGenerator` to construct an identity from an **ID and type**.
- `SidRetrievalStrategy` to extract matching SIDs from `Authentication`.
- `PermissionFactory` to convert permission names/masks into `Permission`.
- `Acl.isGranted(...)` together with `PermissionGrantingStrategy` to evaluate ACEs, deny/grant rules, and inheritance.

`AclService` can be backed by JDBC or another implementation. **Simply adding the `spring-security-acl` dependency is not enough**: the application must create/persist ACLs, configure the service/lookup, and wire the evaluator into Method Security.

### 2.1. Two Java Signatures and Two SpEL Expressions

| Expression in annotation | Java overload | Context |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | `Document` instance already available |
| `hasPermission(#id, 'demo.Document', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Only ID and resource type available |
| `hasPermission(returnObject, 'READ')` | Object overload | Used with `@PostAuthorize` |
| `hasPermission(filterObject, 'READ')` | Object overload | Used with `@PostFilter`/`@PreFilter` |

In the **object** form, the ACL evaluator extracts the object identity from the object itself; the default `ObjectIdentityImpl(Object)` constructor requires the instance to expose **`public getId()`**. A Java record that only has an `id()` accessor without `getId()` **does not satisfy this default**, unless you configure a matching `ObjectIdentityRetrievalStrategy`.

In the **ID** form, `targetType` must match the exact type used when persisting the ACL, typically the **fully qualified class name** such as `"demo.Document"`; `targetId` is a `Serializable` such as `Long`. There is no automatic entity resolution by arbitrary short names.

**Why doesn't the annotation take an `Authentication` argument?** The Method Security expression root retrieves the call's authentication from Spring Security and passes it to the evaluator. Callers cannot submit their own name in a request to be treated as authenticated.

### 2.2. Default Permission Names: Use `'READ'`, Do Not Guess `'read'`

`DefaultPermissionFactory` registers by default the public static field names of `BasePermission`, such as `READ`, `WRITE`, `CREATE`, `DELETE`, and `ADMINISTRATION`. That is why examples use the uppercase string **`'READ'`**.

Base permission bits:

| Permission | Mask |
| --- | ---: |
| `BasePermission.READ` | 1 |
| `BasePermission.WRITE` | 2 |
| `BasePermission.CREATE` | 4 |
| `BasePermission.DELETE` | 8 |
| `BasePermission.ADMINISTRATION` | 16 |

Do not treat `'read'`, `'READ'`, and `'view'` as equivalent unless `PermissionFactory` is explicitly configured with mappings. For custom permissions, register a matching factory and test the masks, names, and real ACEs. Avoid turning unknown-permission errors into a default `READ`.

### 2.3. ACL Owner Does Not Equal READ Permission

`Acl.getOwner()` returns the SID representing the ACL administrator per the implementation and policy. `AclPermissionEvaluator` queries specific permissions through ACEs and the granting strategy. **The ACL owner does not automatically have `READ` on the data.**

Likewise, `BasePermission.ADMINISTRATION` does not implicitly include `READ`. If business rules allow system admins to read every object, encode that in a dedicated policy and test it explicitly; never infer it from ACL administration rights.

## 3. Flow from `@PreAuthorize` to ACE

```text
Caller -> Spring-managed DocumentService proxy
                    |
                    v
            @PreAuthorize advice
                    |
           extract MethodInvocation
           extract Authentication
                    |
                    v
           SpEL hasPermission(...)
                    |
                    v
             AclPermissionEvaluator
                  /         \
                 v           v
     ObjectIdentity        SIDs + Permission
     from object/ID         from auth + factory
                 \           /
                  v         v
              AclService.readAclById(...)
                         |
                         v
                   Acl.isGranted(...)
                         |
                         v
              PermissionGrantingStrategy
                 |         |
               GRANT    DENY/no decision
                 |         |
                allow     deny or exception
                 |
                 v
       DocumentService method body
```

Essential requirements:

1. `@EnableMethodSecurity` must be enabled.
2. Annotations must be placed on methods/classes that Spring Security can intercept.
3. Callers must invoke through a **Spring-managed proxy**, never via `new Service(...)` or self-invocation `this.securedMethod(...)`.
4. The expression handler must use the right evaluator, not the default `DenyAllPermissionEvaluator`.
5. `AclService` must load the matching `ObjectIdentity` with SIDs/ACEs seeded or stored in the database.
6. The permission factory must recognize the name/mask in the annotation.
7. Tenant rules, feature-level authorities, and business policies must be combined at the appropriate boundaries.

**With `@PreAuthorize`, the method body never runs when the expression denies access.** This suits read/write operations that must be blocked before side effects. `@PostAuthorize` checks only **after** the body finishes, so it should not be the sole protection on operations with side effects.

## 4. `Authentication`, SIDs, and Trusted Identity Sources

`AclPermissionEvaluator` receives the current call's `Authentication`. An `Authentication` may carry:

- `getName()`: identifier presented by the provider (username, token subject, or system mapping).
- `getPrincipal()`: may be `UserDetails`, `Jwt`, `OAuth2User`, or a custom principal; never assume it is a `String`.
- `getAuthorities()`: `GrantedAuthority` instances issued by the identity provider or verified by the application.
- `isAuthenticated()`: token status; distinguish anonymous callers from real users per policy.

`SidRetrievalStrategy` can derive `PrincipalSid` and `GrantedAuthoritySid` from the authentication. An ACL containing `PrincipalSid("alice")` differs from `GrantedAuthoritySid("ROLE_EDITOR")`; both **SID type and value** must match. Never use a username that is only unique within a single tenant as a global SID if collisions across tenants are possible.

Security principles:

- User/tenant must be verified server-side; never read an `X-User` header or DTO `owner` field and trust it.
- With JWTs, define how `sub`/issuer/tenant map to a stable subject ID and SID consistently across ACL creation and evaluation.
- `AnonymousAuthenticationToken` can report `isAuthenticated() == true`; never treat such a token as a real user. Spring expressions' `isAuthenticated()` distinguishes anonymous tokens; use it alongside explicit authority policies.
- Never store a request's authentication in a mutable field on a singleton evaluator or custom ACL service.
- For `@Async`/thread pools, the security context does not propagate automatically; use explicit propagation if authorization runs in background tasks.

## 5. Core Configuration So `hasPermission` Actually Calls the ACL Evaluator

Spring Security provides a mechanism to customize the expression handler. Minimal example:

```java
@Configuration
@EnableMethodSecurity
class AclExpressionSecurityConfig {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

This is a **configuration fragment** requiring imports and a real `AclService`; the full program is in section 7. `static @Bean` lets Spring publish the expression handler early, before Method Security configuration classes initialize advisors.

**Common trap:** defining an `AclPermissionEvaluator` bean without calling `handler.setPermissionEvaluator(...)`. Then `hasPermission` may still use the default deny-all evaluator or another handler, causing deny tests to pass while allow tests always fail. Always write **both allow and deny tests**.

Application code using it:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'demo.Document', 'READ')"
)
public String readById(@P("id") Long id) {
    return repository.require(id).getTitle();
}
```

`@P("id")` from `org.springframework.security.access.method.P` lets SpEL resolve the parameter name reliably even without the `-parameters` compiler flag. `hasAuthority` requires the feature capability, `hasPermission` requires the object ACE, and `and` requires both.

This is also why you should **not** rely solely on `hasPermission` when the app needs an independent feature-level authority. An ACE may still exist even after the organization revokes the caller's access to the read feature.

## 6. `ObjectIdentity`: The Piece That Breaks Correct Configs

### 6.1. Objects Must Expose a Matching ID

If the object overload uses default identity extraction, the domain object can be declared as:

```java
package demo;

public final class Document {

    private final Long id;
    private final String title;

    public Document(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

This is also the **Java file used in the complete demo** later. `getId()` lets `ObjectIdentityImpl(Object)` read the ID via reflection and use the class name `demo.Document`. When passing an ID in an expression, use **`'demo.Document'`** to match.

If the model uses a Java record:

```java
public record DocumentRecord(Long id, String title) {
}
```

A record only has `id()`; to use the object overload with the default retrieval strategy, add a `getId()` method or customize the strategy to read `id()`. The `getId` signature must be public and return a suitable `Serializable`.

### 6.2. Identity in ACL Storage Must Match Type

An ACL created like this:

```java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 11L);
```

has type `demo.Document` and `Long` ID 11. If an expression uses:

```java
hasPermission(#id, 'Document', 'READ')
```

while the database stores `demo.Document`, the lookup may fail to find the ACL. If IDs are `UUID`/String instead of Long, align the schema, mapping, and serialization across every write and read path. Never derive a canonical ACL type from a UI label.

### 6.3. An Object Sent by the Client Is No Proof of Ownership

Suppose Bob submits:

```json
{
  "id": 11,
  "title": "Self-claimed data belonging to bob",
  "owner": "bob"
}
```

A default Spring ACL evaluator builds the identity from **object type and ID**, then loads server-side ACEs. It must never use forged `owner` or `title` fields from the client to grant access. Once `@PreAuthorize` allows entry, the demo method body **loads the real record from the repository**, never returning the caller-supplied object verbatim.

In real systems, object identities may be tenant-scoped; ID + type alone is insufficient if IDs are only unique per tenant. Use globally unique IDs or a trusted tenant namespace for ACL/object identities, and enforce tenant checks in the service/repository.

## 7. Complete Spring Boot 3.5.8 / Java 17+ Demo

The demo uses Spring Security's real ACL classes while replacing JDBC `AclService` with an in-memory ACL store **strictly for learning and testing**. As a result, it genuinely exercises:

- `AclPermissionEvaluator` and both overloads.
- `DefaultMethodSecurityExpressionHandler`.
- `@EnableMethodSecurity`, `@PreAuthorize`, and `@PostFilter`.
- `AclImpl`, `BasePermission`, `PrincipalSid`, and `DefaultPermissionGrantingStrategy`.
- Extracting object identities from `Document.getId()` and from `(id, type)`.
- Combining general authorities with object-specific permissions.

This demo does not replace the JDBC ACL schema/service and has no HTTP endpoints. See section 9 for running against a real database.

### 7.1. Project Structure

```text
acl-has-permission-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── AclPermissionDemoApplication.java
    │   ├── Document.java
    │   ├── DocumentRepository.java
    │   ├── InMemoryAclService.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceSecurityTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'acl-has-permission-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-acl'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot plugin BOM manages Spring dependency versions. The example needs no `spring-boot-starter-web` because it runs via `CommandLineRunner`; Method Security applies to Spring services without directly depending on an HTTP controller. You need a Gradle environment able to download dependencies and JDK 17+.

### 7.2. Domain Class with `getId()`

**`src/main/java/demo/Document.java`:**

```java
package demo;

public final class Document {

    private final Long id;
    private final String title;

    public Document(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

`Document.getId()` is needed for the object overload via `ObjectIdentityImpl(Object)`. `title` is purely display data; it plays no part in ACE evaluation in the demo.

### 7.3. Server-Side Document Data

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {

    private final Map<Long, Document> documents = Map.of(
        11L, new Document(11L, "Alpha"),
        12L, new Document(12L, "Beta"),
        13L, new Document(13L, "Gamma")
    );

    public Document require(Long id) {
        Document document = id == null ? null : documents.get(id);
        if (document == null) {
            throw new NoSuchElementException("No document " + id);
        }
        return document;
    }

    public List<Document> all() {
        List<Document> result = new ArrayList<>(documents.values());
        result.sort(Comparator.comparing(Document::getId));
        return result;
    }
}
```

`all()` returns a **mutable** list so `@PostFilter` can remove elements in the demo. Data is created and stored server-side; methods receiving an object from callers **never return the caller-submitted payload directly**.

### 7.4. In-Memory `AclService` Using Real `AclImpl`

**`src/main/java/demo/InMemoryAclService.java`:**

```java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class InMemoryAclService implements AclService {

    private final Map<ObjectIdentity, Acl> stored;

    public InMemoryAclService() {
        var changeStrategy = new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_BOOTSTRAP")
        );
        var grantStrategy =
            new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger()
            );

        // Demo data seeding only.
        // Production: use MutableAclService/transactions and a real actor.
        SecurityContext before = SecurityContextHolder.getContext();
        SecurityContext bootstrap = SecurityContextHolder.createEmptyContext();
        bootstrap.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "bootstrap", "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_ACL_BOOTSTRAP"))
            )
        );
        SecurityContextHolder.setContext(bootstrap);

        try {
            Map<ObjectIdentity, Acl> mutable = new HashMap<>();

            AclImpl first = create(
                11L, changeStrategy, grantStrategy
            );
            first.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("alice"), true
            );
            first.insertAce(
                1, BasePermission.READ,
                new PrincipalSid("bob"), true
            );
            mutable.put(first.getObjectIdentity(), first);

            AclImpl second = create(
                12L, changeStrategy, grantStrategy
            );
            second.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("bob"), true
            );
            mutable.put(second.getObjectIdentity(), second);

            AclImpl third = create(
                13L, changeStrategy, grantStrategy
            );
            third.insertAce(
                0, BasePermission.READ,
                new PrincipalSid("carol"), true
            );
            mutable.put(third.getObjectIdentity(), third);

            stored = Map.copyOf(mutable);
        } finally {
            // Restore the pre-bootstrap SecurityContext,
            // leaving no privileged actor active after initialization.
            SecurityContextHolder.setContext(before);
        }
    }

    private static AclImpl create(
            Long id,
            AclAuthorizationStrategyImpl changes,
            DefaultPermissionGrantingStrategy grants) {

        return new AclImpl(
            new ObjectIdentityImpl(Document.class, id),
            id,
            changes,
            grants,
            null,  // No parent ACL
            null,  // Do not restrict the set of loaded SIDs
            false, // Do not inherit ACEs
            new PrincipalSid("root") // ACL owner
        );
    }

    @Override
    public Acl readAclById(ObjectIdentity oid) {
        Acl acl = stored.get(oid);
        if (acl == null) {
            throw new NotFoundException("No ACL for " + oid);
        }
        return acl;
    }

    @Override
    public Acl readAclById(ObjectIdentity oid, List<Sid> sids) {
        // Demo returns the full ACL without filtering by SID.
        return readAclById(oid);
    }

    @Override
    public Map<ObjectIdentity, Acl> readAclsById(
            List<ObjectIdentity> objects) {
        return readAclsById(objects, null);
    }

    @Override
    public Map<ObjectIdentity, Acl> readAclsById(
            List<ObjectIdentity> objects, List<Sid> sids) {

        Map<ObjectIdentity, Acl> result = new HashMap<>();
        for (ObjectIdentity oid : objects) {
            result.put(oid, readAclById(oid, sids));
        }
        return result;
    }

    @Override
    public List<ObjectIdentity> findChildren(ObjectIdentity parent) {
        // Demo has no parent/child ACLs.
        return List.of();
    }
}
```

**Key points of the demo:**

- Uses the real `AclImpl`, `BasePermission`, `DefaultPermissionGrantingStrategy`, and `PrincipalSid`; the evaluator invokes real ACL logic.
- `AclService` is just a **mock storage adapter**. It ignores the `sids` filter parameter, which the `AclService` contract allows because SID optimization is optional; JDBC services have their own loading and caching mechanisms.
- Each ACL has owner `root`, with no `READ` ACE created for `root`.
- `Document#11`: `alice` and `bob` have `READ`.
- `Document#12`: only `bob` has `READ`.
- `Document#13`: `carol` has `READ`, yet the service layer also checks a general authority.
- The bootstrap block creates a privileged `Authentication` **only to seed ACLs in a learning program**; never copy this into production controllers or authentication flows.
- Every object identity uses `new ObjectIdentityImpl(Document.class, id)`, corresponding to type `"demo.Document"`. This ensures both overloads look up the same ACL.

**Do not use this snippet as production ACL storage**: there is no database, persistence, transactions, tenancy, grant/owner mutation lifecycle, concurrency invalidation, or real auditing. The demo keeps ACLs immutable after bootstrap per its design.

### 7.5. Spring Service Wired with `hasPermission`

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.List;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:read') and " +
        "hasPermission(#id, 'demo.Document', 'READ')"
    )
    public String readById(@P("id") Long id) {
        return repository.require(id).getTitle();
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:read') and " +
        "hasPermission(#document, 'READ')"
    )
    public String readByObject(@P("document") Document document) {
        // Trust only the ID when fetching the REAL record; never return caller-supplied title.
        return repository.require(document.getId()).getTitle();
    }

    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:browse')"
    )
    @PostFilter(
        "hasAuthority('document:read') and " +
        "hasPermission(filterObject, 'READ')"
    )
    public List<Document> visibleDocuments() {
        return repository.all();
    }
}
```

`readById` uses the `(Authentication, Serializable, String, Object)` overload, while `readByObject` uses `(Authentication, Object, Object)`. Sharing the same canonical identity and ACL, both reach the same decision for the same ID.

`visibleDocuments` uses `@PostFilter`: after obtaining the list, Method Security evaluates the expression **for each element**. The `hasAuthority` condition is also checked in the filter so a user with `document:browse` but without `document:read` **does not see objects solely via an ACE**. This filtering suits small demos; production should push authorization predicates or batch ACL lookups down to the data layer to avoid N+1 queries and broken pagination.

**Never** call `this.readById(...)` from inside the same bean expecting advice to run. All CLI/test calls obtain `DocumentService` from Spring so invocations go through the proxy.

### 7.6. Enabling Method Security and Running Multiple Principals

**`src/main/java/demo/AclPermissionDemoApplication.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class AclPermissionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AclPermissionDemoApplication.class, args);
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator aclPermissionEvaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(aclPermissionEvaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(DocumentService documents) {
        return args -> {
            try {
                signIn("alice", "document:read", "document:browse");
                System.out.println("ALICE_ID_11: "
                    + documents.readById(11L));
                System.out.println("ALICE_OBJECT_11: "
                    + documents.readByObject(
                        new Document(11L, "caller-supplied-fake")));
                System.out.println("ALICE_VISIBLE: "
                    + ids(documents.visibleDocuments()));
                denied("ALICE_ID_12", () -> documents.readById(12L));

                signIn("bob", "document:read", "document:browse");
                System.out.println("BOB_ID_12: "
                    + documents.readById(12L));
                System.out.println("BOB_VISIBLE: "
                    + ids(documents.visibleDocuments()));

                signIn("carol", "document:browse");
                denied("CAROL_ID_13", () -> documents.readById(13L));
                System.out.println("CAROL_VISIBLE: "
                    + ids(documents.visibleDocuments()));

                signIn("root", "document:read", "document:browse");
                denied("ROOT_OWNER_NO_READ", () -> documents.readById(11L));

                anonymous();
                denied("ANONYMOUS_ID_11", () -> documents.readById(11L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::getId).toList();
    }

    private static void signIn(String name, String... authorityNames) {
        var authorities = Arrays.stream(authorityNames)
            .map(SimpleGrantedAuthority::new)
            .toList();
        var auth = new UsernamePasswordAuthenticationToken(
            name, "demo-only", authorities
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void anonymous() {
        var token = new AnonymousAuthenticationToken(
            "demo-key", "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@Profile("!test")` prevents the CLI scenario from running when integration tests activate the `test` profile. Each user switch creates a fresh `SecurityContext`, and the `finally` block clears the context at the end.

**Warning:** building a `UsernamePasswordAuthenticationToken` with preset authorities is **strictly for simulation**. Real applications must never build authenticated tokens from HTTP client-supplied usernames/roles; use an authentication provider or validated bearer tokens/sessions.

### 7.7. Run Command and Expected Output

In the project directory, if the Gradle Wrapper is present:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

If there is no wrapper yet, use a compatible installed Gradle version to generate it or run `gradle bootRun`.

**Expected lines printed by the program itself**, excluding Spring Boot logs:

```text
ALICE_ID_11: Alpha
ALICE_OBJECT_11: Alpha
ALICE_VISIBLE: [11]
ALICE_ID_12: DENIED
BOB_ID_12: Beta
BOB_VISIBLE: [11, 12]
CAROL_ID_13: DENIED
CAROL_VISIBLE: []
ROOT_OWNER_NO_READ: DENIED
ANONYMOUS_ID_11: DENIED
```

Explanation by group:

- Alice has the authority and a READ ACE on `#11`, so reading by **ID or object** succeeds. Even though the client object supplies a fake title, the service returns the server title `Alpha`.
- Alice has no READ ACE on `#12`, so she is denied. The list after `@PostFilter` contains only `#11`.
- Bob has READ ACEs on both `#11`/`#12` plus the authority, so he sees two documents.
- Carol has a READ ACE on `#13` yet lacks the general `document:read` authority, so the read method is denied and the list filters down to empty.
- Root is the ACL owner, simulated with `document:read`, yet still lacks a READ ACE on `#11`, so access is denied.
- Anonymous fails `isAuthenticated()` and cannot enter the method.

**These lines are expected from the source logic, not a claim of execution in this environment.** What you verify when running is that both overloads and the filter use the **same** registered `AclPermissionEvaluator`; if every allow case is denied, inspect the expression handler and `ObjectIdentity` configuration before altering policy.

## 8. Integration Tests with `@WithMockUser`

Create **`src/test/java/demo/DocumentServiceSecurityTest.java`**:

```java
package demo;

import java.io.Serializable;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Autowired
    AclPermissionEvaluator evaluator;

    private static List<Long> ids(List<Document> docs) {
        return docs.stream().map(Document::getId).toList();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:browse"}
    )
    void bothHasPermissionOverloadsAgree() {
        assertEquals("Alpha", documents.readById(11L));
        assertEquals("Alpha", documents.readByObject(
            new Document(11L, "forged-title")));

        assertEquals(List.of(11L), ids(documents.visibleDocuments()));
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(12L));
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"document:read", "document:browse"}
    )
    void permissionsDifferBetweenUsers() {
        assertEquals("Alpha", documents.readById(11L));
        assertEquals("Beta", documents.readById(12L));
        assertEquals(
            List.of(11L, 12L),
            ids(documents.visibleDocuments())
        );
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:browse")
    void aclGrantIsNotEnoughWithoutGeneralAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(13L));
        assertEquals(List.of(), ids(documents.visibleDocuments()));
    }

    @Test
    @WithMockUser(
        username = "root",
        authorities = {"document:read", "document:browse"}
    )
    void aclOwnerDoesNotAutomaticallyHaveReadAce() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(11L));
        assertEquals(List.of(), ids(documents.visibleDocuments()));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.readById(11L));
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:browse"}
    )
    void evaluatorRejectsNullAndUnsupportedPermission() {
        var authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertFalse(evaluator.hasPermission(
            authentication, (Object) null, "READ"
        ));

        assertFalse(evaluator.hasPermission(
            authentication, (Serializable) 12L,
            "demo.Document", "READ"
        ));

        assertTrue(evaluator.hasPermission(
            authentication, (Serializable) 11L,
            "demo.Document", "READ"
        ));
    }
}
```

Run:

```bash
./gradlew test
```

Why are these tests meaningful?

- `@SpringBootTest` loads the real configuration: `@EnableMethodSecurity`, expression handler, evaluator, and ACL service.
- `@WithMockUser` populates `Authentication` for each test via `spring-security-test`.
- `@Autowired DocumentService` invokes through a **Spring-managed proxy**, so annotations execute. Instantiating `new DocumentService(repository)` would bypass advice.
- The suite has **both allow and deny cases**; if the evaluator is not wired to the handler, allow paths fail instead of only deny tests passing.
- The forged-title object test still returns the server title; ACLs never use client payload data to grant access.
- The root test confirms ACL owner is not READ; Carol's test confirms an individual ACE does not replace feature authorities.

For production, also test `WRITE`, `DELETE`, `ADMINISTRATION`, explicit DENY ACEs, group SIDs, parent ACLs, missing ACLs, missing SIDs, cross-tenant attempts, revocation, and stale caches.

## 9. Moving from In-Memory `AclService` to JDBC ACL

In a real Spring Boot application, you do not use an `InMemoryAclService` holding ACLs per process. Replace it with `JdbcMutableAclService` and its dependencies:

```text
Method Security
   |
   v
AclPermissionEvaluator
   |
   v
AclService / JdbcMutableAclService
   |
   +--> AclCache / SpringCacheBasedAclCache
   |
   +--> BasicLookupStrategy
                |
                v
         DataSource + ACL schema
                |
                v
     AclImpl + ACE/SID/owner/parent
```

### 9.1. Required ACL Tables

| Table | Role |
| --- | --- |
| `acl_sid` | Principal SIDs or granted-authority SIDs |
| `acl_class` | Domain object type names |
| `acl_object_identity` | Object ID, owner SID, parent ACL, inheritance |
| `acl_entry` | ACE order, SID, permission mask, grant/deny, and audit flags |

JDBC ACL records are not created automatically when saving a JPA entity. The application must implement the **ACL lifecycle**: creating an ACL when an object is created, adding ACEs, updating/revoking ACEs, updating owners, and deleting ACLs when objects are deleted. Use the official DB-compatible schema along with transactions, constraints, and indexes.

### 9.2. JDBC Configuration Template

This is an **integration configuration snippet**, not a file to drop alongside `InMemoryAclService`. It assumes you removed the in-memory bean and already have a DataSource, driver, and ACL schema:

```java
@Configuration
@EnableMethodSecurity
class JdbcAclConfiguration {

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy grants,
            AclAuthorizationStrategy changes) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"), grants, changes);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy changes,
            PermissionGrantingStrategy grants) {
        return new BasicLookupStrategy(
            dataSource, cache, changes, grants);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(
            dataSource, lookup, cache);
    }
}
```

Key imports for the snippet:

```java
import javax.sql.DataSource;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

**Important note on imports:** `AclAuthorizationStrategy` is `org.springframework.security.acls.domain.AclAuthorizationStrategy`, whereas `PermissionGrantingStrategy` and `AclCache` live in `org.springframework.security.acls.model`. `LookupStrategy` is an interface in `org.springframework.security.acls.jdbc`, not in `model`.

Additional Gradle dependencies needed:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework:spring-context-support'
    runtimeOnly 'com.h2database:h2'
}
```

This is only an **incremental dependency snippet** for a project that already has Spring Security/ACL and dependency management; use the proper driver for a real DB. `JdbcMutableAclService` requires the full JDBC ACL schema, identity-generation configuration, and database-compatible SQL.

### 9.3. Creating ACEs with `MutableAclService`

```java
// CODE SNIPPET inside an authorized, transactional admin service.
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 11L);
MutableAcl acl = mutableAclService.createAcl(oid);

acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("alice"),
    true
);

mutableAclService.updateAcl(acl);
```

**Do not re-run this snippet on an existing ACL**: `createAcl` is designed for an identity without an ACL yet. To update ACEs, read the existing `MutableAcl`, modify it, and call `updateAcl`.

Mutators on `AclImpl` use `AclAuthorizationStrategy` to guard ACL modification rights, separate from `PermissionGrantingStrategy` used to evaluate READ on the object. Services must also verify tenant, recipient, allowed permission types, self-grant rules, auditing, and transactions. Never let clients send a `username` and spin up a privileged token to seed ACEs in production.

### 9.4. Custom Permission Factories and SID Strategies

`AclPermissionEvaluator` provides setters:

```java
evaluator.setPermissionFactory(permissionFactory);
evaluator.setSidRetrievalStrategy(sidRetrievalStrategy);
evaluator.setObjectIdentityRetrievalStrategy(objectStrategy);
evaluator.setObjectIdentityGenerator(identityGenerator);
```

The snippet above is **illustrative**; the strategy variables must be created/configured beforehand. When custom masks or tenant-scoped SIDs are needed, those strategies must stay consistent from **ACE creation** through **evaluation**.

For instance, if the business has an `"EXPORT"` or `"APPROVE"` permission, do not simply change the annotation string and expect the framework to guess it. Define non-conflicting `Permission` masks, `PermissionFactory` mappings, ACEs, and tests.

If a domain object uses a record `id()` without `getId()`, consider a custom `ObjectIdentityRetrievalStrategy` rather than relying on default reflection. Keep `ObjectIdentity` stable across versions/schemas so ACLs never become orphaned.

## 10. `@PreAuthorize`, `@PostAuthorize`, `@PostFilter`: Choosing the Right Boundary

### 10.1. `@PreAuthorize`: ID Known Before Execution

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document find(Long id) {
    return repository.require(id);
}
```

Ideal when the ID is known and you want to block **before loading or writing data**. In production, combine it with `isAuthenticated`, `hasAuthority`, and tenant policies. For operations with side effects, **before-method** authorization is essential.

### 10.2. `@PostAuthorize`: Object Only Known After Execution

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'READ')"
)
public Document loadDocument(Long id) {
    return repository.require(id);
}
```

Fits when the decision requires the returned instance. It **does not** prevent the method body from running, so never rely on it as the sole guard for data-mutating commands that already commit. If repository objects contain lazy associations, account for loading costs and avoid leaking metadata through exceptions/logs.

### 10.3. `@PostFilter`: Filtering Element by Element

```java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> findAllDocuments() {
    return new ArrayList<>(repository.findAll());
}
```

This is an **illustrative snippet**, assuming the repository has `findAll`. In the demo in section 7, the list is mutable so the interceptor can remove items. An ACL evaluator hitting the database **per element** can cause N+1 queries, especially on large lists.

In real systems, prefer set-based SQL/ACL queries, batch `AclService.readAclsById(...)`, or a batch-capable authorization service rather than `findAll` followed by post-filtering everything. If pagination occurs **before** `@PostFilter`, page sizes and `totalElements` will be wrong. Push authorization predicates into queries **before pagination** whenever possible.

### 10.4. `@PreFilter`: Filtering Input Elements

```java
@PreFilter("hasPermission(filterObject, 'WRITE')")
public void processDocuments(List<Document> documents) {
    // Receives only the elements remaining after filtering.
}
```

This snippet is not standalone. For batch updates requiring **all-or-nothing** semantics, `@PreFilter` may be inappropriate because it **drops unauthorized items** instead of rejecting the entire operation. Check semantics and transaction rules before using it.

## 11. Security Risks When Integrating `AclPermissionEvaluator`

### 11.1. Missing ACL Does Not Mean Public

If `AclService` cannot find an identity or finds no matching ACE, never fall back to `permitAll`. `AclPermissionEvaluator` and the ACL mechanism handle `NotFoundException`; at the application boundary, missing permissions or missing data must **fail closed**, never turning exceptions into `allow=true`.

Similarly, invalid permission names, wrong `targetType`, unverified authentication, or missing SIDs are never grounds to grant access.

### 11.2. Never Substitute ACL Owner for Permission

A developer might write:

```java
// DO NOT use unless business rules explicitly grant READ to the ACL owner.
return acl.getOwner().equals(new PrincipalSid(auth))
    || acl.isGranted(permissions, sids, false);
```

This opens a new READ bypass based solely on the ACL owner. If business rules genuinely require owners to read, specify and test that rule explicitly; never treat it as default Spring ACL behavior.

### 11.3. Combine Feature Authorities and Object Permissions with AND

In the demo:

```java
hasAuthority('document:read')
and hasPermission(#id, 'demo.Document', 'READ')
```

ensures both conditions must hold. Never use OR when callers are expected to have both the general authority **and** an individual ACE. OR can bypass ACLs or let a user with an ACE retain access after their feature authority is revoked.

### 11.4. Tenant Is an Additional Boundary

`ObjectIdentity` normally comprises a class and an ID. If IDs are only unique **per tenant**, two tenants can share `"demo.Document", 11`, causing identity collisions. Use globally unique IDs or define a trusted namespace for ACL/object identities, and enforce tenant checks in the service/repository. An ACL grant alone does not prove the caller is operating in the right tenant if identities are not isolated.

If documents have field-level visibility, `READ` on the object does not automatically permit viewing **every field**. Apply field-level policies or construct properly redacted DTOs.

### 11.5. ACL Cache Can Go Stale After Revocation

`SpringCacheBasedAclCache` can cache ACEs and owners. On grants, revocations, ownership transfers, or parent ACL changes, invalidate properly. In a cluster, node A's local cache does not automatically invalidate node B's. If you also cache `(user, object, action)` decisions, track permission versions and TTLs; keying caches solely by object ID is dangerous.

### 11.6. TOCTOU on Write Operations

`@PreAuthorize` checks permissions at time T1, while `UPDATE`/`DELETE` executes at T2. If owner, tenant, or ACL changes in between, you face a **time of check, time of use** race. For critical operations, re-check conditions inside the transaction/update, use locking/versioning as needed, and verify affected row counts. Never assume `@Transactional` alone suffices if the isolation level is inadequate.

### 11.7. Protect More Than Just Controllers

Services can be invoked from HTTP controllers, schedulers, message listeners, or other services. Protect critical business boundaries with Spring Method Security or appropriate `AuthorizationManager`s; watch out for self-invocation and proxies. Test through the Spring context to prove advice actually runs.

## 12. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `hasPermission` denies even users with an ACE | `AclPermissionEvaluator` not wired to handler | Define `static @Bean MethodSecurityExpressionHandler`, call `setPermissionEvaluator` |
| ID form works, object form fails | Object lacks `getId()` or wrong retrieval strategy | Add public `getId()` or customize strategy |
| Object form works, ID form finds no ACL | `targetType` mismatches canonical class name | Use `"demo.Document"` or exact mapping |
| `'read'` not recognized | Factory registers `READ`, no `read` alias | Use `'READ'` or configure `PermissionFactory` |
| Wrong user still sees data | Skipped tenant/authority or trusted DTO owner | AND with authority/tenant policies, query server data |
| ACL owner can read without a READ ACE | Code bypasses using `Acl.getOwner()` | Separate ACL admin from object permissions |
| Missing ACL still lets request succeed | Fail-open fallback | Deny or handle infrastructure errors properly |
| `@PreAuthorize` never runs | Missing `@EnableMethodSecurity`, `new` call, self-invocation | Invoke through Spring-managed proxy |
| Anonymous user granted access | Checking only token `isAuthenticated()` or stray ACE | Use security expressions/identity policies distinguishing anonymous |
| 1,000-item list is slow | `@PostFilter` doing per-item ACL lookups | SQL/batch ACL, proper pagination |
| Stale READ after revocation | Stale ACL cache or decision cache | Invalidate after commit and across nodes |
| `UnloadedSidException` | ACL loaded a SID subset then evaluated another SID | Load needed SIDs or fail closed |
| `NotFoundException` | Insufficient ACL/ACE data to decide | Never turn exception into allow; verify identity and ACL |
| Missing access after username/tenant change | Stored SID mapping no longer matches | Stable IDs, tenant namespaces, and ACE migration |
| Custom `PermissionFactory` grants wrong rights | Mask/name mismatches stored data | Test mappings against real ACEs |
| Only deny tests pass while allow tests fail | Evaluator not invoked or ACL missing | Test allow and deny, trace bean + identity |
| `@PostAuthorize` fails to block writes | Post-check runs after body | Use pre-checks and DB consistency for side effects |

### Quick Debugging Checklist

1. Are you calling the real Spring bean/proxy? `AopUtils.isAopProxy(service)` only helps confirm the proxy; still test real behavior.
2. Is `@EnableMethodSecurity` loaded?
3. Is there a custom `MethodSecurityExpressionHandler` calling `setPermissionEvaluator` with the **right bean**?
4. Does the expression use the object or ID overload? Does the object have `public getId()`? Does `targetType` match the class in the ACL?
5. Does the permission factory map `'READ'` to `BasePermission.READ`?
6. Does `Authentication` have principals/authorities/SIDs matching the stored ACLs?
7. Does `AclService` load the right `ObjectIdentity`, ACEs, parent, and SIDs?
8. Is any extra authority/tenant/status rule making `and` evaluate to false?
9. Have ACL/permission decision caches been invalidated?
10. Do tests cover allow, deny, anonymous, missing object, cross-tenant, and update/revoke cases?

## 13. Self-Check Exercises

1. **Which overload does `hasPermission(#doc, 'READ')` call?**  
   `(Authentication, Object targetDomainObject, Object permission)`, using object identity retrieval.

2. **Which overload does `hasPermission(#id, 'demo.Document', 'READ')` call?**  
   `(Authentication, Serializable targetId, String targetType, Object permission)`, using the identity generator.

3. **Why isn't `Authentication` passed as a SpEL parameter?**  
   The Method Security expression root retrieves the current authentication and passes it to the evaluator.

4. **You have an `AclPermissionEvaluator` bean yet `hasPermission` still denies: what do you check first?**  
   Whether the expression handler called `setPermissionEvaluator` and whether the bean was registered early enough.

5. **Can a Java record with only an `id()` accessor use the default object overload?**  
   Do not assume so. `ObjectIdentityImpl(Object)` requires `getId()`; add the method or customize the strategy.

6. **Is using `'Document'` instead of `'demo.Document'` safe?**  
   It may fail to find the stored `ObjectIdentity`. Keep canonical types consistent.

7. **Is `BasePermission.ADMINISTRATION` equivalent to `READ`?**  
   No. ACL administration and reading domain objects are two separate checks.

8. **Carol has a READ ACE yet lacks `document:read`; under an AND policy, what happens?**  
   Denied, due to insufficient feature authority.

9. **Why shouldn't a client-sent title be returned directly after authorization succeeds?**  
   Because it is untrusted data; the service should fetch the real record from the server using the protected ID.

10. **Why can `@PostFilter` on 1,000 objects cause N+1 queries?**  
    Because each element may trigger a separate ACL lookup in the evaluator.

11. **Is `@PostAuthorize` sufficient to protect write operations?**  
    No. Post-authorization runs after the method body executes and side effects may already have occurred.

12. **If an API uses tenant-scoped IDs, what must you do with ACL `ObjectIdentity`?**  
    Ensure identities are unique per tenant by design and verify the tenant from principal/server data.

13. **If an ACE is revoked without updating the cache, what is the risk?**  
    Callers may receive decisions from stale permissions; ensure invalidation aligns with transactions and clusters.

14. **What test proves both overloads consult the same ACL?**  
    With the same principal and ID, assert `readById`/`readByObject` both allow or both deny, alongside a forged-object test.

## 14. Official References

1. [Spring Security 6.5 — ACLs](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): ACL model and configuration templates for evaluator/Method Security/JDBC.
2. [Spring Security 6.5 — `AclPermissionEvaluator` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): both overloads and strategy setters.
3. [Spring Security 6.5 — `PermissionEvaluator` interface](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html): object and ID contracts.
4. [Spring Security 6.5 — `ObjectIdentityImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/ObjectIdentityImpl.html): constructor from object requiring `getId()`, or from class + ID.
5. [Spring Security 6.5 — `DefaultPermissionFactory`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/DefaultPermissionFactory.html): permission name/mask mapping.
6. [Spring Security 6.5 — `AclService`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html): reading one or multiple ACLs, optionally by SID.
7. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, SpEL, and static expression handlers.
8. [Spring Security 6.5 — `AclImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html): ACEs, owner, permission strategy, inheritance.
9. [Spring Security — Spring AOP proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation and interception boundaries.

**Conclusion:** `AclPermissionEvaluator` is the bridge from **`hasPermission(...)` in Method Security** to **stored ACLs**. The object path needs `getId()` or a matching identity strategy; the ID path needs a canonical type; both require a permission factory, SIDs from a trusted authentication, and the right `AclService`. Combine ACLs with authority and tenant policies using AND, test through Spring proxies, and manage caches/transactions whenever permissions change.