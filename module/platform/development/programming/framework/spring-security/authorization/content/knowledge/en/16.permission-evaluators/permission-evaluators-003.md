# hasPermission with an Already-Loaded Object

> **Topic:** Spring Security – authorization → **PermissionEvaluator**. This lesson focuses on the `hasPermission(domainObject, permission)` expression when the domain object is already in memory, how to configure `PermissionEvaluator`, the difference between checking before and after method execution, and what you must do to avoid trusting a caller-constructed object. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x; the core concepts still apply to current versions when configured and tested against the right version.

## 1. The problem: permission on which exact object?

Suppose a document system holds the following data:

| ID | Owner | Shared? | Locked for editing? |
| --- | --- | --- | --- |
| 101 | `alice` | No | No |
| 202 | `bob` | No | No |
| 303 | `alice` | Yes | No |
| 404 | `alice` | No | Yes |

Business requirements:

- `READ`: the owner may read; others may only read shared documents **and** must hold the `DOC_SHARED_READ` authority.
- `EDIT`: must be the owner **and** hold the `DOC_EDIT` authority, and the document must not be locked.
- Anonymous callers, missing authentication data, nonexistent IDs, forged objects, or undefined permissions must all be denied.

`hasAuthority('DOC_EDIT')` only checks a user's authority; it cannot answer **whether a specific document belongs to that user or is locked**. `hasPermission` is a hook that delegates **per-domain-object** decisions to Java, where you can evaluate the user, resource, and business policy.

Two key expressions:

~~~java
// Illustrates a method receiving an object that already exists BEFORE the call.
@PreAuthorize("hasPermission(#document, 'EDIT')")
public void prepareEdit(@P("document") Document document) {
    // Runs only when PermissionEvaluator allows it.
}
~~~

~~~java
// Illustrates a method that LOADS the object itself and checks before returning to the caller.
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(long id) {
    // Load from repository...
}
~~~

The two snippets above are **illustrative signatures** and do not compile standalone; the full example later includes complete packages, classes, configuration, and tests.

## 2. The two overloads of `PermissionEvaluator`

Spring Security defines the `org.springframework.security.access.PermissionEvaluator` interface with two methods that serve different roles:

~~~java
// ABBREVIATED API SHAPE, DO NOT RECREATE THE LIBRARY INTERFACE.
boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission);

boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission);
~~~

| SpEL | Java method invoked | Scenario |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | `document` is already present in input |
| `hasPermission(returnObject, 'READ')` | Same domain-object overload | Object was just loaded and returned by the method |
| `hasPermission(filterObject, 'READ')` | Same domain-object overload, repeated per element | `@PreFilter`/`@PostFilter` |
| `hasPermission(#id, 'Document', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Only ID + type name known, no object yet |

`Authentication` is passed **implicitly** by Spring Security to the evaluator. Therefore, in annotations you only write `hasPermission(object, permission)` or `hasPermission(id, type, permission)`. Do not add `authentication` to the SpEL call and mismatch the argument count.

The object overload simply **receives the existing object**; it does not automatically fetch data from a database. If you want to query an ACL or verify owner/tenant, your evaluator implementation must do that itself.

The ID overload is used when only the resource's key is available. `targetType` is an object type identifier consistent with how permissions are looked up (often the class name, though the application may define another convention). Never assume the ID overload delegates to the object overload or vice versa. In the example, the ID overload **intentionally returns false** because this lesson only implements the policy for an already-loaded domain object; that is a safe choice instead of implicitly granting access.

### The `permission` parameter has type `Object`

SpEL passes `'READ'` as a String. However, the `permission` parameter in `PermissionEvaluator` has type `Object` because the framework allows other permission representations, such as ACL permission objects or enums. When designing your own evaluator, check both the type and value and reject unknown actions. Do not convert everything with `toString()` and accidentally accept a disallowed object.

In this example, the two strings `'READ'` and `'EDIT'` form the explicit contract; any other value returns false.

## 3. From annotation to permission decision

~~~text
Caller invokes a bean wrapped by a Spring AOP proxy
              |
              v
@PreAuthorize / @PostAuthorize / @PostFilter
              |
              v
MethodSecurityExpressionHandler
              |
              v
SpEL: hasPermission(domainObject, 'READ')
              |
              v
PermissionEvaluator.hasPermission(
    authentication, domainObject, "READ"
)
              |
          +---+---+
          |       |
        true    false
          |       |
        Allow   Deny
~~~

`@EnableMethodSecurity` registers the interceptors that enforce annotations on Spring bean methods. Merely adding the `spring-boot-starter-security` dependency **does not automatically activate Method Security**. Callers must go through the proxy; `new MyService(...)` or self-invocation `this.someMethod()` inside the target can bypass the interceptor.

For `hasPermission`, putting `@Component` on an evaluator only creates a Java bean. **You must attach the evaluator to `DefaultMethodSecurityExpressionHandler`** so the expression root knows to use it for object permission decisions. Spring Security documentation illustrates this when wiring `AclPermissionEvaluator` into Method Security.

## 4. Choosing when to check: pre, post, or per-element

### 4.1. `@PreAuthorize` when the object is already passed in

~~~java
@PreAuthorize("hasPermission(#doc, 'EDIT')")
public String prepare(@P("doc") Document doc) {
    return "ready:" + doc.id();
}
~~~

Spring extracts `#doc` from the parameter and evaluates the expression **before** the method body executes. If the caller lacks permission, the method does not run. This is the right choice for actions with side effects, **provided the input object comes from verified data or the evaluator re-verifies it**.

Risk: a DTO or record deserialized from a JSON request can carry an arbitrary `owner = "alice"`. If the evaluator merely checks `doc.owner().equals(authentication.getName())`, a caller can forge the owner. This lesson verifies the snapshot against a trusted store before evaluating policy.

### 4.2. `@PostAuthorize` when the method just loaded the object

~~~java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(long id) {
    return store.findById(id).orElse(null);
}
~~~

`returnObject` is the value returned by the target method. The expression executes **after** the target reads the data but **before** the proxy returns the value to the caller. If permission is denied, an `AccessDeniedException` is normally thrown. Since there is no write operation, this read case suits post-authorization.

Never use post-authorization as the sole protection for methods that **delete, modify, create financial transactions, or send notifications**: by the time the evaluator checks, those side effects may already have occurred. Also, do not log sensitive data inside the method body before post-authorization runs.

### 4.3. `@PostFilter` on a loaded collection of objects

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> listVisible() {
    return new ArrayList<>(store.findAll());
}
~~~

`filterObject` represents each element. The evaluator is called separately for each object to retain permitted elements. We allocate a new `ArrayList` because some filtering pipelines mutate the collection. Never return a shared cached list directly and let the filter mutate it.

For large queries and pagination, push permission criteria into the database query. Loading all data and filtering afterward can be slow, skew page sizes, and waste memory.

### 4.4. Quick decision table

| When is the data available? | Check approach | Consequence |
| --- | --- | --- |
| Before method body, object from trusted source | `@PreAuthorize("hasPermission(#doc,'EDIT')")` | Blocks action early |
| After method body finishes loading | `@PostAuthorize("hasPermission(returnObject,'READ')")` | Good for read operations |
| Collection already constructed | `@PostFilter("hasPermission(filterObject,'READ')")` | Filters element-by-element; suitable for small sets |
| Only ID known, no object yet | ID overload or load/check in service/repository | Do not pretend it is a loaded object |
| Writing sensitive data | Pre-authorization + conditional transaction/update | Enforces permission and state constraints at write time |

## 5. Complete example on Spring Boot 3.x / Java 17+

The files use package `demo.permissionobject`. The Gradle project already has the Spring Boot/Java plugins and Spring Boot dependency management. To focus on Method Security mechanics, the example uses only services and an in-memory store without creating HTTP endpoints.

### 5.1. Dependencies

In `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not directly mix Spring Security 7 with Spring Boot 3 in this sample. Use the versions selected by Boot's dependency management.

### 5.2. Application

**`src/main/java/demo/permissionobject/PermissionObjectApplication.java`**

~~~java
package demo.permissionobject;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionObjectApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionObjectApplication.class, args);
    }
}
~~~

### 5.3. Loaded domain object

**`src/main/java/demo/permissionobject/Document.java`**

~~~java
package demo.permissionobject;

public record Document(
        long id,
        String owner,
        String title,
        boolean shared,
        boolean locked) {
}
~~~

A `record` provides `equals/hashCode` based on all components. This is an **immutable snapshot** for illustration in this lesson; real systems can use JPA entities, projections, or DTOs constructed from trusted data. Never use a client-supplied copy as the source of truth.

### 5.4. Simulated store

**`src/main/java/demo/permissionobject/DocumentStore.java`**

~~~java
package demo.permissionobject;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101L, "alice", "Draft A", false, false),
        202L, new Document(202L, "bob", "Private B", false, false),
        303L, new Document(303L, "alice", "Shared Guide", true, false),
        404L, new Document(404L, "alice", "Locked Draft", false, true)
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public List<Document> findAll() {
        return documents.values().stream()
                .sorted(Comparator.comparingLong(Document::id))
                .toList();
    }
}
~~~

`findAll()` sorts by ID so tests do not depend on `Map` iteration order. `toList()` creates an unmodifiable list; the service copies it into an `ArrayList` before `@PostFilter` processes it.

### 5.5. Evaluator granting permission only for verified object snapshots

**`src/main/java/demo/permissionobject/DocumentPermissionEvaluator.java`**

~~~java
package demo.permissionobject;

import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    public DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!isRealUser(authentication)) {
            return false;
        }
        if (!(targetDomainObject instanceof Document supplied)) {
            return false;
        }
        if (!(permission instanceof String action)) {
            return false;
        }

        // Verify ID and snapshot against the trusted source.
        // Do not trust caller-supplied owner/shared/locked fields.
        return store.findById(supplied.id())
                .filter(stored -> stored.equals(supplied))
                .map(stored -> canPerform(authentication, stored, action))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {
        // ID form is not implemented in this lesson -> deny by default.
        return false;
    }

    private boolean canPerform(
            Authentication authentication,
            Document document,
            String action) {
        boolean owner = document.owner().equals(authentication.getName());

        return switch (action) {
            case "READ" -> owner
                    || (document.shared()
                        && hasAuthority(authentication, "DOC_SHARED_READ"));
            case "EDIT" -> owner
                    && !document.locked()
                    && hasAuthority(authentication, "DOC_EDIT");
            default -> false;
        };
    }

    private boolean hasAuthority(Authentication authentication, String name) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> name.equals(a.getAuthority()));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

**Explaining the evaluation flow:**

1. If the user is unauthenticated or an anonymous token, return false.
2. If the object is not a `Document` (including `null`), return false.
3. If permission is not a `String`, return false.
4. Verify the object by `id` against the record from `DocumentStore`. If nonexistent or the snapshot differs, return false.
5. Evaluate the READ/EDIT policy based on **the stored record**, not caller-supplied fields.
6. Unsupported permissions hit `default -> false`.

Re-reading the store in step 4 prevents the sample from trusting a forged object. It also adds an extra lookup; in real JPA/SQL, you can optimize by querying an owner/tenant projection, checking row versions, or structuring transactions to avoid stale snapshots. Never skip source-data verification when an API accepts untrusted DTOs.

### 5.6. Registering the expression handler

**`src/main/java/demo/permissionobject/MethodSecurityConfig.java`**

~~~java
package demo.permissionobject;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
~~~

`@Bean static` is the pattern used by the Spring Security reference to publish the expression handler early enough for Method Security configuration. The handler receives the `PermissionEvaluator` via the bean factory method parameter and calls `setPermissionEvaluator(...)`.

If your project already defines a custom expression handler for a role hierarchy, expression root, or ACLs, **integrate into the existing configuration** instead of creating multiple handler beans where it is unclear which one is active. If multiple `PermissionEvaluator` beans exist, use `@Qualifier` to select the exact one.

### 5.7. Service using `returnObject` and `filterObject`

**`src/main/java/demo/permissionobject/DocumentQueryService.java`**

~~~java
package demo.permissionobject;

import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentStore store;

    public DocumentQueryService(DocumentStore store) {
        this.store = store;
    }

    @PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
    public Document read(long id) {
        return store.findById(id).orElse(null);
    }

    @PostFilter("hasPermission(filterObject, 'READ')")
    public List<Document> listVisible() {
        return new ArrayList<>(store.findAll());
    }
}
~~~

In `read`, the object is **loaded first** and then passed to the evaluator via `returnObject`. If it returns null or the policy evaluates to false, the result is blocked by the proxy. In `listVisible`, the evaluator is invoked for each element of the small in-memory collection.

The example chooses to return null in `read` to illustrate handling `returnObject != null`. In real applications, distinguishing 404 for nonexistent documents from 403 for unauthorized documents requires defining an HTTP contract and avoiding leaking resource existence per business requirements.

### 5.8. Service using `#doc` on a loaded parameter

**`src/main/java/demo/permissionobject/DocumentActionService.java`**

~~~java
package demo.permissionobject;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentActionService {

    @PreAuthorize("hasPermission(#doc, 'EDIT')")
    public String prepareEdit(@P("doc") Document doc) {
        return "edit:" + doc.id();
    }
}
~~~

`@P("doc")` makes the SpEL parameter name explicit, avoiding complete reliance on the `-parameters` compiler flag. The method only builds a preview string with no side effects. The `EDIT` rule is evaluated before the method body, and the evaluator verifies the record against the repository so it never grants permission based on a DTO with an altered owner.

Do not treat `prepareEdit` as a database update command. When implementing real writes, enforce owner/tenant/locked/version constraints inside the transaction and update statement; a guard at call entry alone cannot prevent races between check time and write time.

## 6. Integration tests through the Spring proxy

The tests below let Spring create the application context and inject real services, completely different from calling `new SomeService(...)`. `@WithMockUser` provides the `Authentication` for each test.

**`src/test/java/demo/permissionobject/DocumentMethodSecurityTest.java`**

~~~java
package demo.permissionobject;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = PermissionObjectApplication.class)
class DocumentMethodSecurityTest {
    @Autowired
    private DocumentQueryService query;

    @Autowired
    private DocumentActionService actions;

    @Autowired
    private DocumentStore store;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadLoadedDocument() {
        assertEquals(101L, query.read(101L).id());
        assertEquals(303L, query.read(303L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void anotherOwnerCannotReadPrivateDocument() {
        assertThrows(AccessDeniedException.class, () -> query.read(101L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_SHARED_READ")
    void sharedReaderCanReadSharedDocument() {
        assertEquals(303L, query.read(303L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void sharedDocumentStillRequiresAuthority() {
        assertThrows(AccessDeniedException.class, () -> query.read(303L));
    }

    @Test
    @WithMockUser(username = "alice")
    void absentDocumentIsDenied() {
        assertThrows(AccessDeniedException.class, () -> query.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDenied() {
        assertThrows(AccessDeniedException.class, () -> query.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EDIT")
    void ownerCanPrepareEditWhenUnlocked() {
        Document trusted = store.findById(101L).orElseThrow();
        assertEquals("edit:101", actions.prepareEdit(trusted));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerWithoutEditAuthorityIsDenied() {
        Document trusted = store.findById(101L).orElseThrow();
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(trusted));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_EDIT")
    void lockedDocumentCannotBeEdited() {
        Document locked = store.findById(404L).orElseThrow();
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(locked));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_EDIT")
    void forgedOwnerDoesNotGrantPermission() {
        Document forged = new Document(101L, "bob", "Draft A", false, false);
        assertThrows(AccessDeniedException.class, () -> actions.prepareEdit(forged));
    }

    @Test
    @WithMockUser(username = "alice")
    void postFilterReturnsOnlyAllowedObjects() {
        List<Long> ids = query.listVisible().stream().map(Document::id).toList();
        assertEquals(List.of(101L, 303L, 404L), ids);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_SHARED_READ")
    void postFilterIncludesOwnedAndShared() {
        List<Long> ids = query.listVisible().stream().map(Document::id).toList();
        assertEquals(List.of(202L, 303L), ids);
    }
}
~~~

**What the tests prove:**

- `@PostAuthorize` evaluates the loaded object and blocks returning another user's data.
- `@PreAuthorize` protects the action requiring EDIT as soon as the object is received, while the evaluator verifies the canonical state.
- `@PostFilter` invokes the evaluator for each domain object.
- Anonymous users, nonexistent IDs, unsuitable authorities, objects with altered owners, and locked documents are all denied.

If test code uses `new DocumentQueryService(store)`, annotations may not be processed by a Spring proxy; that is why method security tests must run against injected beans.

## 7. Unit-testing the evaluator and the ID overload

**`src/test/java/demo/permissionobject/DocumentPermissionEvaluatorTest.java`**

~~~java
package demo.permissionobject;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPermissionEvaluatorTest {
    private final DocumentStore store = new DocumentStore();
    private final DocumentPermissionEvaluator evaluator =
            new DocumentPermissionEvaluator(store);

    private Authentication auth(String user, String... authorities) {
        List<SimpleGrantedAuthority> granted = java.util.Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return new UsernamePasswordAuthenticationToken(user, "unused", granted);
    }

    @Test
    void knownPermissionOnLoadedObject() {
        Document doc = store.findById(101L).orElseThrow();
        assertTrue(evaluator.hasPermission(auth("alice"), doc, "READ"));
        assertFalse(evaluator.hasPermission(auth("bob"), doc, "READ"));
    }

    @Test
    void editRequiresAllConditions() {
        Document draft = store.findById(101L).orElseThrow();
        Document locked = store.findById(404L).orElseThrow();

        assertTrue(evaluator.hasPermission(auth("alice", "DOC_EDIT"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("alice"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("bob", "DOC_EDIT"), draft, "EDIT"));
        assertFalse(evaluator.hasPermission(auth("alice", "DOC_EDIT"), locked, "EDIT"));
    }

    @Test
    void unknownActionWrongTypeAndNullFailClosed() {
        Authentication alice = auth("alice", "DOC_EDIT");
        Document doc = store.findById(101L).orElseThrow();

        assertFalse(evaluator.hasPermission(alice, doc, "DELETE"));
        assertFalse(evaluator.hasPermission(alice, doc, Integer.valueOf(7)));
        assertFalse(evaluator.hasPermission(alice, "not-document", "READ"));
        assertFalse(evaluator.hasPermission(alice, null, "READ"));
        assertFalse(evaluator.hasPermission(null, doc, "READ"));
    }

    @Test
    void objectWithFakeOwnerIsRejected() {
        Document fake = new Document(101L, "bob", "Draft A", false, false);
        assertFalse(evaluator.hasPermission(auth("bob"), fake, "READ"));
    }

    @Test
    void idOverloadIsDeliberatelyDenied() {
        assertFalse(evaluator.hasPermission(
                auth("alice"), 101L, "Document", "READ"));
    }
}
~~~

The three-argument constructor `UsernamePasswordAuthenticationToken(user, credentials, authorities)` builds an authenticated token to test **Java logic**. Unit tests do not know whether Spring registered the expression handler; keep the integration tests from section 6.

### Running from the Gradle project

On macOS/Linux:

~~~text
./gradlew test --tests demo.permissionobject.DocumentPermissionEvaluatorTest --tests demo.permissionobject.DocumentMethodSecurityTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.permissionobject.DocumentPermissionEvaluatorTest --tests demo.permissionobject.DocumentMethodSecurityTest
~~~

The examples do not print with `System.out.println`, so there is no fixed business stdout. When dependencies/configuration are correct and all assertions pass, Gradle finishes `test` successfully. This is sample code for the learner to run in a compatible project; do not treat merely reading the source as having executed the tests.

## 8. Tracing each execution path to understand timing

### 8.1. `alice` reads document 101 via `@PostAuthorize`

~~~text
1. Caller invokes query.read(101) through the proxy.
2. Method body loads Document(101, owner=alice, ...) from store.
3. @PostAuthorize inspects returnObject.
4. SpEL invokes hasPermission(returnObject, 'READ').
5. Evaluator verifies snapshot 101 against store.
6. owner=alice => true.
7. Proxy returns Document to caller.
~~~

### 8.2. `bob` reads document 101

~~~text
1. Method body still loads Document 101.
2. @PostAuthorize receives returnObject.
3. Evaluator verifies snapshot but owner != bob, shared=false.
4. Returns false.
5. Proxy throws AccessDeniedException, does not return Document.
~~~

Precisely because loading occurred before step 3, post-authorization **cannot prevent internal work** or side effects. Only use this approach when the read method is safe or additional guards are designed.

### 8.3. `bob` passes a forged object into `@PreAuthorize`

~~~text
1. Caller constructs Document(id=101, owner=bob, ...).
2. Calls actions.prepareEdit(fake) through the proxy.
3. @PreAuthorize invokes hasPermission(#doc, 'EDIT').
4. Evaluator loads canonical record for ID 101 -> owner=alice.
5. Forged snapshot does not match canonical record -> false.
6. prepareEdit does not run.
~~~

If the evaluator only looked at the `owner` field on the caller-supplied object, forged data could trick the check. The goal of `PermissionEvaluator` is not to “trust every object already in hand,” but to **centralize object-permission logic in a place that can consult trusted data**.

## 9. Limitations to understand before real deployment

### 9.1. Null objects

The `PermissionEvaluator` Javadoc allows `targetDomainObject` to be null and recommends returning false. The example uses `instanceof`, so null becomes false. The `returnObject != null and hasPermission(...)` expression clarifies the intent to reject null and avoids dereference exceptions.

### 9.2. Do not misunderstand authority/role

`hasRole('ADMIN')` normally checks for authority `ROLE_ADMIN` with the default prefix; `hasAuthority('DOC_EDIT')` checks for `DOC_EDIT` verbatim. In the example, the evaluator compares authorities directly without adding a role prefix. If a system supports cross-tenant admin access or role overrides, express it as an explicit policy and test the precedence/exception branches.

### 9.3. Object provenance and trust boundaries

A domain object loaded from a repository inside a method differs from a record built from client JSON. For caller-supplied objects, the risk is **insecure direct object reference (IDOR)** or spoofing owner, tenant, or state. Verification can mean querying state from the database by ID and actor/tenant, comparing immutable versions, or accepting only references produced via trusted use cases; choose what fits the real design.

### 9.4. Multiple tenants

If a document carries `tenantId`, check same-tenant from verified claims/principal **before** applying owner/shared exceptions. Never use a client-sent `tenantId` query parameter/header as proof. When adding ADMIN rights, decide explicitly whether admins cross tenants or only administer within their own tenant; a missing pair of parentheses in `admin || sameTenant` can accidentally over-grant access.

### 9.5. Repeated queries, lazy JPA, and transactions

An evaluator can be called in bulk inside `@PostFilter`. If every element queries the database again, query counts can spike rapidly. With JPA, accessing lazy relations during post-authorization may occasionally run outside the transaction depending on advisor ordering. Prefer conditional database queries, minimal projections, batch lookups, or policy services using appropriate read transactions. Measure query counts and execution time; avoid “caching allow” solely by ID while forgetting actor, tenant, action, and policy version.

### 9.6. Time-of-check to time-of-use (TOCTOU) gap

Risky sequence:

~~~text
T1: Evaluator sees document 101 belongs to alice, locked=false -> allow.
T2: Another transaction changes owner or sets locked=true.
T3: Service writes document based on stale check result.
~~~

This is `time-of-check/time-of-use` (TOCTOU): state can change between check time and use time. For sensitive updates, combine pre-authorization with owner/tenant/locked/version conditions at the database, transactions/optimistic locking, or appropriate locks. Never rely on `@PostAuthorize` to protect an already-committed action.

Conceptual SQL example:

~~~sql
UPDATE documents
SET title = :new_title
WHERE id = :id
  AND owner_id = :authenticated_user_id
  AND tenant_id = :trusted_tenant_id
  AND locked = FALSE;
~~~

Check the affected row count to know whether the update executed; parameters must be bound safely and identity must come from a trusted authentication.

### 9.7. Official ACL vs. custom evaluator

`PermissionEvaluator` is a general contract. When an application needs per-record sharing, access control lists, and user/group permissions, you can use `AclPermissionEvaluator` in Spring Security's ACL module. When policies are simpler and driven by owner/state/tenant, a custom evaluator like the example can fit better. ACL's `BasePermission.READ` and this sample's String `'READ'` are not automatically equivalent; you must configure mappings per implementation.

### 9.8. Proxies and internal calls

`@PreAuthorize`/`@PostAuthorize` run when calls go through a Spring AOP proxy. If a method in the same bean calls `this.read(...)`, `read`'s own annotation may not be applied. Place enforcement guards at public service boundaries, invoke through beans injected from the Spring Context, and write integration tests with authorized/unauthorized users to prove the guard works.

## 10. Common troubleshooting table

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `hasPermission` is always false | Handler does not have custom evaluator attached | Configure `MethodSecurityExpressionHandler` and `setPermissionEvaluator` |
| Evaluator unit tests pass but service does not block | Missing `@EnableMethodSecurity` or call bypasses proxy | Write integration tests through Spring bean and unauthorized user |
| `#doc` is null | Wrong variable name or missing parameter metadata | Use `@P("doc")`, or enable `-parameters` properly |
| `returnObject` is null | Object does not exist or method returns null | Check for null and design 403/404 handling appropriately |
| Someone else changes owner and gets access | Trusting client-sent object/DTO directly | Verify canonical stored record and tenant from trusted source |
| ID overload does not work | Only object overload implemented | Separately implement `hasPermission(Authentication, Serializable, String, Object)` |
| Unknown permission is still allowed | Permissive default or arbitrary casting | Check exact permissions, `default -> false` |
| Post-authorization blocks after data already changed | Using `@PostAuthorize` on action with side effects | Use pre-authorization and transaction/database conditions |
| `@PostFilter` filters very slowly | Each object queries the repository again | Use conditional queries, batching, and measure query count |
| Tests let owner without EDIT authority through | Checking only ownership and forgetting authority | Clearly separate READ and EDIT, write negative tests |
| Owner cannot edit locked record | `locked` policy blocks as designed | Adjust requirements if a separate unlock action is needed |
| JPA lazy loading fails | Evaluator runs outside transaction boundary | Design clear policy/transaction queries |
| Version upgrade changes permissions | Different proxy/advisor configuration or permission mapping | Run regression tests through the Spring Context |

## 11. Practice exercises

**Exercise 1 – Add DELETE.** The `DELETE` permission requires the owner, authority `DOC_DELETE`, an unlocked document, and an unshared document. Add tests missing each condition, ensuring any single failed branch denies access.

**Exercise 2 – Forged object.** Construct `Document(101,"bob",...)` while ID 101 in the store still belongs to alice. Write a test for caller bob proving the evaluator does not trust the altered owner field. Compare with a dangerous implementation that only checks properties on the caller-supplied object.

**Exercise 3 – ID overload.** Implement `hasPermission(#id,'Document','READ')` checking targetType, ID, and repository lookup; compare results with the object overload, including nonexistent IDs.

**Exercise 4 – Tenant.** Add `tenantId` to Document and the trusted principal. Create two documents in different tenants with owners sharing the same username; test that cross-tenant reads fail.

**Exercise 5 – Update operation.** Build a write service with `@PreAuthorize` and an update conditioned on owner/tenant/locked/version. Test the case where state changes after the permission check, ensuring no invalid update occurs.

**Exercise 6 – Pagination.** Replace `@PostFilter` with a repository query that reads only documents permitted for the principal; compare query count, total record counts, and performance on large datasets.

**Completion criteria:** recognize the domain-object overload; explain `#doc`, `returnObject`, and `filterObject`; register the evaluator on the expression handler; include allow/deny tests through the Spring proxy; never trust the owner of a client-sent object; use transactions/queries to enforce real state when writing data.

## References

- Spring Security – **Method Security**, `@PreAuthorize`, `@PostAuthorize`, `@PostFilter`, and `hasPermission`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Domain Object Security (ACLs)**, example configuring `PermissionEvaluator` and expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security – **PermissionEvaluator API**, both overloads and null-object handling: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
- Spring Security – **Testing Method Security**, `@WithMockUser` and `@WithAnonymousUser`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
