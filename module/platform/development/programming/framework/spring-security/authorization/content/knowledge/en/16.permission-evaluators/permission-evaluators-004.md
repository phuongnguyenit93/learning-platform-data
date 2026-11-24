# hasPermission with targetId, targetType, and permission

> **Scope:** Spring Security – authorization, **PermissionEvaluator** group. The focus is the three-argument expression `hasPermission(targetId, targetType, permission)` when the application knows a resource's **ID** but does not yet have a loaded domain object. This lesson uses method security on Spring Boot Servlet, Java 17+, and a custom `PermissionEvaluator`. Spring code examples target Spring Security 6.x/7.x with matching APIs; the standalone Java 17 simulation uses plain JDK.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Write and understand `@PreAuthorize("hasPermission(#p0, 'Document', 'read')")` with its three parts: ID, resource type, and requested permission.
2. Distinguish the three-argument overload from `hasPermission(targetObject, permission)` and both overloads on the `PermissionEvaluator` interface.
3. Know that `Authentication` is passed by the framework to the evaluator, while `targetId`/`targetType`/`permission` come from the expression; never trust a client-supplied ID as proof of authorization.
4. Configure `DefaultMethodSecurityExpressionHandler` to invoke the actual evaluator; avoid missing evaluator registration causing all checks to deny.
5. Design an evaluator that does not leak data when the resource does not exist, belongs to another tenant, lacks ACL entries, or receives an unsupported permission.
6. Test with `@WithMockUser` and Spring bean proxies to verify authorized users, unauthorized users, wrong tenants, wrong ID types, and invalid data sources are all handled properly.
7. Evaluate permission-lookup performance, transaction boundaries, and race-condition risks between pre-method checks and subsequent data reads/writes.

## 2. Scenario: only an ID, no domain object yet

Suppose a client calls:

~~~text
GET /api/documents/42
Authorization: Basic ... or Bearer ...
~~~

The controller receives `42` from the path and forwards it to the service. **Before the method runs**, the application may not have loaded the `Document` from the database yet. However, view permission may depend on the ACL, owner, tenant, and share list of document ID 42 itself.

Instead of calling the service and only checking the result afterward, we can write:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document readDocument(Long id) {
    return documentStore.find(id).orElseThrow();
}
~~~

`#p0` is the first parameter of the protected method, i.e. `id`. `'Document'` is an **application-defined resource-type key**. `'read'` is the requested permission. Spring Security retrieves `Authentication` from the security context and invokes the registered `PermissionEvaluator`; the evaluator decides whether to allow or deny **before the method body runs**.

If the evaluator denies, the method call is blocked. In a typical web request, an authorization failure for an authenticated user is usually represented as HTTP 403; for resources whose existence should stay hidden, an application may design a consistent 404 policy. Do not infer that every `hasPermission` false automatically becomes 404.

## 3. Two expressions corresponding to two overloads

### 3.1. Expression receiving an existing object

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document inspectLoadedDocument(Document document) {
    return document;
}
~~~

The **two-argument** expression has the form:

~~~text
hasPermission(targetDomainObject, permission)
~~~

and maps to the interface method:

~~~java
boolean hasPermission(Authentication authentication,
                      Object targetDomainObject,
                      Object permission);
~~~

Suitable when the caller already has a **trusted** domain object. If the object was deserialized from client JSON, the `owner` and `tenant` fields could be forged; the evaluator must reload the trusted record or use another verification mechanism. Never treat an object merely “having an owner field” as proof it belongs to the logged-in user.

### 3.2. Expression receiving ID, type, and permission

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document readDocument(Long id) {
    return documentStore.find(id).orElseThrow();
}
~~~

The **three-argument** expression has the form:

~~~text
hasPermission(targetId, targetType, permission)
~~~

and maps to:

~~~java
boolean hasPermission(Authentication authentication,
                      Serializable targetId,
                      String targetType,
                      Object permission);
~~~

The interface is in package `org.springframework.security.access.PermissionEvaluator`. The `Authentication` parameter is provided by the framework; **do not** add Authentication to the expression. When the expression has three arguments, Spring Security routes to the ID–type–permission overload; when it has only two arguments, it routes to the object–permission overload.

| In SpEL | In evaluator | Role |
| --- | --- | --- |
| Not passed explicitly | `Authentication authentication` | User/authorities from the security context |
| `#p0` | `Serializable targetId` | Resource identifier, typically `Long`/`UUID`/`String` if supported by the implementation |
| `'Document'` | `String targetType` | Distinguishes the domain/object type the ID belongs to |
| `'read'` | `Object permission` | Specific permission: read, edit, delete, approve... |

**Important:** `targetType` is not automatically converted into a class by Spring to check arbitrary permissions. It is simply a string interpreted by the evaluator or ACL implementation. The application must establish a consistent type convention, such as `'Document'` or `'com.example.Document'`, and handle unknown types with DENY.

### 3.3. Why is targetType necessary?

A system may simultaneously have Document ID 42, Invoice ID 42, and Project ID 42. Checking only `42` without a type could query the wrong ACL or share permissions across unrelated domains.

~~~text
(authentication=alice, targetId=42, targetType="Document", permission="read")
≠
(authentication=alice, targetId=42, targetType="Invoice",  permission="read")
~~~

Combining type keys and IDs into a consistent resource identity is essential; in multi-tenant applications, the tenant also typically belongs in the **permission lookup scope**. Never rely on an ID being “long/random enough” in place of authorization checks.

## 4. Evaluation flow from annotation to PermissionEvaluator

~~~text
HTTP request or other caller
       |
       v
Spring bean proxy of DocumentService
       |
       v
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
       |
       +-- read #p0 from MethodInvocation (Long ID)
       +-- obtain Authentication from SecurityContext
       +-- invoke MethodSecurityExpressionHandler
       |        |
       |        +-- PermissionEvaluator.hasPermission(
       |                authentication, id, "Document", "read")
       |             |
       |             +-- select policy by type/permission
       |             +-- query trusted metadata/ACL/tenant
       |             +-- GRANT or DENY (boolean)
       |
       +-- false: block method, throw access denied error
       |
       +-- true: execute body of readDocument(id)
                     |
                     +-- fetch resource and return permitted data
~~~

Because `@PreAuthorize` runs before the method body when the proxy intercepts successfully, the evaluator itself must access whatever data source is needed for the decision (such as a repository or ACL service). Spring does not automatically pass an unloaded `Document` into the ID overload.

**Do not confuse “permission evaluation” with “identity authentication.”** Authentication and feature-level authorities may be determined in the filter chain, yet the evaluator still needs to check authorization for **that exact record**.

### 4.1. When does the annotation not run?

- The method is invoked via `this.readDocument(id)` from the same bean in normal proxy mode: self-invocation does not pass through the Spring proxy.
- An instance is created with `new DocumentService(...)` in a test: it is not a Spring-managed proxy.
- `@EnableMethodSecurity` is missing: annotations are not automatically activated just by adding `spring-boot-starter-security`.
- An evaluator bean exists without being wired into the appropriate `MethodSecurityExpressionHandler`: expressions may fall back to the default deny-all evaluator.
- Trying to use URL authorization instead of service authorization: the same service can be called from jobs, message listeners, or other endpoints.

## 5. Policy of a well-designed PermissionEvaluator

An evaluator receives `Authentication`, ID, type, and permission, and must use **trusted data** to determine the outcome. Example rules for `Document`:

~~~text
canReadDocument(actor, id):
  is actor genuinely authenticated?
  does actor hold "document:read"?
  is id a supported ID type and > 0?
  is type exactly "Document"?
  is permission exactly "read"?
  does record id exist in trusted store?
  does actor have valid tenant scope for the record?
  is actor the owner (or holds a valid shared ACL)?
  if any required condition fails => DENY
~~~

In a real system, questions about ownership and ACLs may be decomposed into smaller policies. The core principle here is **without proof of permission, do not grant access**.

| Evaluator input/condition | Intentional handling |
| --- | --- |
| `targetId == null` | DENY; never treat as “all resources” |
| `targetId` has non-canonical type (e.g., evaluator accepts only `Long` but receives `Integer`) | DENY or perform strict designed conversion; never guess |
| `targetType == null` or not `Document` | DENY |
| `permission` missing / not in allow-list | DENY |
| Invalid authentication or missing authority | DENY |
| Record/ACL not found | DENY in permission layer; HTTP mapping designed separately |
| Record belongs to another tenant | DENY, return no sensitive metadata |
| Record in matching tenant but not authorized | DENY |
| Repository connection error | Fail safely; never catch error and return true |
| Valid proof of permission | GRANT, after which the method still obeys business/transaction constraints |

Note that errors differ from permission outcomes. If a repository is unreachable, code may throw an exception to signal a system fault; the key rule is **never turn an infrastructure failure into GRANT or return unverified data**. Do not return `false` and mask every failure as a lack-of-permission error if the application needs observability/remediation.

### 5.1. The permission string is an internal protocol

`Object permission` can be a string, enum, or another permission object if the evaluator understands it. The example below **intentionally accepts only the exact string `"read"`**. `"READ"`, `"write"`, or an object whose `toString() == "read"` is not automatically allowed through. Use an exact allow-list and write tests for unsupported permissions.

If you use the Spring ACL module with `AclPermissionEvaluator` and `BasePermission`, permission representation and mapping differ from this simple string example. Do not mix this demo pattern with ACL bitmasks without integrating `AclService`.

## 6. Configuring MethodSecurityExpressionHandler

To tell Spring Security which `PermissionEvaluator` implementation to use, expose a `MethodSecurityExpressionHandler` and call `setPermissionEvaluator`. The standard pattern uses a `static @Bean` so the handler is registered early before method-security configuration initializes:

~~~java
// Snippet inside a @Configuration class with @EnableMethodSecurity.
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator permissionEvaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(permissionEvaluator);
    return handler;
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
~~~

Spring Security does not require the ACL module to implement `PermissionEvaluator` yourself. You can use your application's own repository/ACL; in that case your own code is responsible for canonicalizing type, ID, and permission.

When implementing full ACL, Spring Security provides `AclPermissionEvaluator` paired with `AclService`; that requires separate dependencies, ACL schema, and service/cache/permission factory configuration. Simply calling `hasPermission(...)` **does not create ACL tables** or automatically load and verify owners.

## 7. Complete Spring Boot example: checking by ID, type, and permission

This example uses an in-memory repository to demonstrate a testable policy. Each Document has an ID, tenant, and owner; to read it, a user must simultaneously hold the `document:read` authority, permission in the tenant, and be the owner. In production, use verified stable principal/tenant claims, real ACL/owner policies, and tenant-scoped repository queries.

Two-file layout:

~~~text
src/main/java/demo/permission/PermissionDemoApplication.java
src/test/java/demo/permission/PermissionDemoApplicationTest.java
~~~

### 7.1. Spring Boot application

Save the following as `src/main/java/demo/permission/PermissionDemoApplication.java` in a Spring Boot Servlet project (Java 17+) with `spring-boot-starter-web` and `spring-boot-starter-security`. The file contains one public application class and package-private types in the same package:

~~~java
package demo.permission;

import java.io.Serializable;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                         "/api/documents/*")
                            .hasAuthority("document:read")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo")
                        .authorities("document:read", "tenant:alpha")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo")
                        .authorities("document:read", "tenant:beta")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}demo")
                        .authorities("tenant:alpha")
                        .build());
        // {noop} is ONLY for demos; production must use a secure encoder.
    }
}

record Document(long id, String tenant, String owner, String title) {
}

@Component
class DocumentStore {
    private final Map<Long, Document> data = Map.of(
            1L, new Document(1L, "alpha", "alice", "Plan A"),
            2L, new Document(2L, "beta",  "bob",   "Plan B"),
            3L, new Document(3L, "alpha", "alice", "Plan C")
    );

    Optional<Document> find(Long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component
class DocumentPermissionEvaluator implements PermissionEvaluator {
    private final DocumentStore store;

    DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(Authentication authentication,
                                 Object targetDomainObject,
                                 Object permission) {
        // Do not trust owner/tenant on a caller-supplied object.
        // Re-check the stored object by its real ID.
        if (!(targetDomainObject instanceof Document doc)) {
            return false;
        }
        return store.find(doc.id())
                .map(saved -> isAllowed(authentication, saved, permission))
                .orElse(false);
    }

    @Override
    public boolean hasPermission(Authentication authentication,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        // "Document" is the application-defined type name.
        // Accept only properly bound/canonicalized Long IDs.
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id) || id <= 0) {
            return false;
        }
        return store.find(id)
                .map(saved -> isAllowed(authentication, saved, permission))
                .orElse(false);
    }

    private boolean isAllowed(Authentication authentication,
                              Document document, Object permission) {
        if (authentication == null || !authentication.isAuthenticated()
                || !("read".equals(permission))) {
            return false;
        }

        boolean hasReadAuthority = authentication.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));
        boolean inTenant = authentication.getAuthorities().stream()
                .anyMatch(a -> ("tenant:" + document.tenant())
                        .equals(a.getAuthority()));
        boolean isOwner = document.owner().equals(authentication.getName());

        return hasReadAuthority && inTenant && isOwner;
    }
}

@Service
class DocumentService {
    private final DocumentStore store;

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('document:read') and "
            + "hasPermission(#p0, 'Document', 'read')")
    public Document readDocument(Long id) {
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    // Same evaluator, this time via the object-based overload.
    @PreAuthorize("hasPermission(#p0, 'read')")
    public Document readAlreadyLoaded(Document candidate) {
        // Never return caller-constructed candidate data.
        return store.find(candidate.id()).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document get(@PathVariable Long id) {
        return service.readDocument(id);
    }
}
~~~

**Notes to avoid misunderstandings:**

- `@PreAuthorize` executes on `DocumentService` through a Spring proxy. The controller and evaluator are separate beans so the HTTP→service call goes through the proxy.
- `#p0` reliably addresses the first parameter without requiring Java compilation with `-parameters`. With names like `#id`, ensure parameter-name discovery is compatible.
- `DocumentPermissionEvaluator` implements **both overloads**. Implementing only the object overload when calling the three-argument expression leaves the ID path incomplete; or if the ID overload always returns false, the three-argument expression will always deny.
- In-memory data is only illustrative. Having the object overload reload from the store prevents callers from spoofing owner/tenant on a self-constructed object. For real objects already loaded from a trusted repository, an evaluator may avoid duplicate lookups depending on the threat model.
- `readDocument` performs one lookup in the evaluator and one in the service body. With a DB, consider queries combining permissions/data or appropriate transactions/locking to avoid double queries and races.
- The demo's GET endpoint is still not a complete multi-tenant resource API: service-level permission checks and repository scoping are necessary across every access path.

### 7.2. Required dependencies

The block below is an excerpt of `build.gradle` from a project that **already includes the Spring Boot Gradle plugin, dependency management, and Java 17+**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

You cannot copy only the block above and run it as a complete `build.gradle`. Once a project is generated with Spring Initializr, you can run `./gradlew bootRun` on Unix or `gradlew.bat bootRun` on Windows.

### 7.3. Calling the endpoint

Assuming the application runs on `localhost:8080`:

~~~bash
curl -i -u alice:demo http://localhost:8080/api/documents/1
curl -i -u alice:demo http://localhost:8080/api/documents/2
curl -i -u bob:demo http://localhost:8080/api/documents/2
curl -i -u viewer:demo http://localhost:8080/api/documents/1
curl -i http://localhost:8080/api/documents/1
~~~

Expected outcomes in the sample HTTP Basic setup:

| Request | URL permission | ID/type/permission evaluator | Result |
| --- | --- | --- | --- |
| Alice reads ID 1 | Alice has `document:read` | Owner Alice, tenant alpha, permission read | HTTP 200, JSON Document 1 |
| Alice reads ID 2 | Passes URL | Owner Bob, tenant beta → DENY | HTTP 403 |
| Bob reads ID 2 | Passes URL | Owner Bob, tenant beta → GRANT | HTTP 200, JSON Document 2 |
| Viewer reads ID 1 | Lacks `document:read` | Method never invoked | HTTP 403 |
| Anonymous reads ID 1 | Unauthenticated | Method never invoked | Typically HTTP 401 with Basic |
| Alice reads ID 999 | Passes URL | Nonexistent record → false | HTTP 403 due to `@PreAuthorize` in demo |

The last row is intentional: in the example `readDocument(999)`, the evaluator returns false before the method body can throw 404. Do not mistake this for a rule that every application must return 403 for nonexistent resources. For APIs that must conceal existence, design consistent 404 responses at a layer with full context and test both “nonexistent” and “exists but unauthorized.”

## 8. Integration test verifying the right overload

Place the test in `src/test/java/demo/permission/PermissionDemoApplicationTest.java`:

~~~java
package demo.permission;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionDemoApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void aliceReadsOwnDocumentById() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void aliceCannotReadBobDocument() throws Exception {
        mvc.perform(get("/api/documents/2"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob",
                  authorities = {"document:read", "tenant:beta"})
    void bobReadsOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "viewer",
                  authorities = {"tenant:alpha"})
    void featureAuthorityIsRequired() throws Exception {
        mvc.perform(get("/api/documents/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void forgedLoadedObjectIsDenied() {
        Document forged = new Document(
                2L, "alpha", "alice", "Forged");
        assertThrows(AccessDeniedException.class,
                () -> service.readAlreadyLoaded(forged));
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"document:read", "tenant:alpha"})
    void unknownDocumentIdIsDeniedBeforeMethodBody() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }
}
~~~

The tests above verify:
- Method security actually runs through the Spring bean/proxy.
- Overload `hasPermission(#p0, 'Document', 'read')` uses ID and type.
- Overload `hasPermission(#p0, 'read')` is not fooled by an object with a forged owner.
- The demo's URL + resource-level permission contract and “nonexistent” behavior.
- HTTP responses via `MockMvc`; direct service unit tests can catch `AccessDeniedException` instead of HTTP 403.

These tests require `spring-security-test`, Spring Boot Test, Spring Web, and Spring Security. On Spring Boot 4, some dependencies or MockMvc auto-configuration packages may differ; this example targets Spring Boot 3.x/Spring Security 6.x for a clear runnable baseline. When upgrading versions, keep the behavioral tests rather than assuming package names stay unchanged.

### 8.1. Direct unit tests on the evaluator for dirty-data cases

Alongside integration tests, write non-web tests for `DocumentPermissionEvaluator`:

| Input | Expected |
| --- | --- |
| Alice, `1L`, `"Document"`, `"read"` | true |
| Alice, `2L`, `"Document"`, `"read"` | false |
| Alice, `1L`, `"Invoice"`, `"read"` | false |
| Alice, `Integer.valueOf(1)`, `"Document"`, `"read"` | false because the demo accepts only Long |
| Alice, `1L`, `"Document"`, `"write"` | false |
| Alice, `null` ID or permission | false per designed policy/null-handling |
| Principal loses `document:read` authority | false |
| Principal lacks tenant alpha | false |
| Document deleted/moved to another tenant between check and read | Never return unauthorized data; enforce protection at read/write point |
| Database failure/timeout | Fail closed / logged exception, never allow due to error |

Especially for `String` IDs passed by an API, decide whether to **convert before evaluating the expression** (controller binding to Long) or support canonical strings inside the evaluator. Never call `String.valueOf` on arbitrary Objects and try to match IDs, as that can create collisions or bypass validation.

## 9. Standalone Java 17: explaining the meaning of the three parameters

This example does not require Spring; it simulates the `Authentication + ID + type + permission` policy to verify GRANT/DENY cases with plain JDK. Save as `PermissionIdDemo.java`:

~~~java
import java.io.Serializable;
import java.util.Map;
import java.util.Set;

public class PermissionIdDemo {
    record Actor(String name, String tenant, Set<String> permissions) {}
    record Doc(long id, String tenant, String owner) {}

    static final Map<Long, Doc> DOCUMENTS = Map.of(
            1L, new Doc(1L, "alpha", "alice"),
            2L, new Doc(2L, "beta", "bob"));

    static boolean hasPermission(Actor actor, Serializable targetId,
                                 String targetType, Object permission) {
        if (actor == null || !(targetId instanceof Long id)
                || !"Document".equals(targetType)
                || !"read".equals(permission)
                || !actor.permissions().contains("document:read")) {
            return false;
        }

        Doc doc = DOCUMENTS.get(id);
        return doc != null
                && doc.tenant().equals(actor.tenant())
                && doc.owner().equals(actor.name());
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "alpha",
                Set.of("document:read"));
        Actor bob = new Actor("bob", "beta",
                Set.of("document:read"));

        System.out.println("alice-id1=" +
                hasPermission(alice, 1L, "Document", "read"));
        System.out.println("alice-id2=" +
                hasPermission(alice, 2L, "Document", "read"));
        System.out.println("bob-id2=" +
                hasPermission(bob, 2L, "Document", "read"));
        System.out.println("wrong-type=" +
                hasPermission(alice, 1L, "Invoice", "read"));
        System.out.println("wrong-permission=" +
                hasPermission(alice, 1L, "Document", "write"));
        System.out.println("wrong-id-type=" +
                hasPermission(alice, Integer.valueOf(1), "Document", "read"));
        System.out.println("missing-id=" +
                hasPermission(alice, 999L, "Document", "read"));
    }
}
~~~

Run:

~~~bash
javac --release 17 PermissionIdDemo.java
java PermissionIdDemo
~~~

**Exact stdout:**

~~~text
alice-id1=true
alice-id2=false
bob-id2=true
wrong-type=false
wrong-permission=false
wrong-id-type=false
missing-id=false
~~~

Core mechanism: the same ID with the wrong **targetType**, wrong **permission**, or wrong ID data type is denied before or during lookup; a feature-level authority alone does not replace object-level permission. This is an illustrative model **not** Spring's `PermissionEvaluator` implementation, yet it independently validates what each parameter means.

## 10. Edge cases of the ID overload

### 10.1. targetId must be Serializable

The Java signature takes `Serializable`: `Long`, `String`, and `UUID` implement Serializable; a custom ID class must implement it and provide proper equality/serialization semantics. In SpEL, `hasPermission(targetId, targetType, permission)` accepts Object and forwards per the framework contract; never assume any arbitrary Object can be cast to `Serializable` safely.

Common pitfalls:
- `1L` in Java boxes to Long, whereas `1` boxes to Integer. The sample evaluator accepts only Long so `Integer(1)` is denied.
- `@PathVariable Long id` gives the method an explicit type. If accepting `String id`, convert strictly and return a 400 error before checking permissions.
- If an ID is a UUID, align the evaluator on `UUID` consistently across controller, repository, and ACL; do not convert to String ad hoc in random places.
- If a domain uses composite keys, define an explicit ID type or a different expression/policy; never concatenate strings in ways that can collide.

### 10.2. targetType is not an automatic “class lookup”

`'Document'` is just a string. If Spring ACL is configured with fully qualified class names like `com.example.domain.Document`, passing `'Document'` may fail to match the ACL. If your custom evaluator accepts `'Document'`, it works, **provided the exact same convention is used at every call site**.

Never turn a request-supplied `targetType` into `Class.forName`, an SQL table name, or an unrestricted type resolver. For public APIs, select the type from the route/server policy instead of letting clients specify arbitrary types. Use an allow-list to prevent bypasses, confused deputy attacks, or cross-domain data access.

### 10.3. permission is an Object, not a user authority

`'read'` expresses the **desired action on Document ID X**. It is not necessarily the GrantedAuthority `document:read`; an evaluator may require a general authority *and* a per-resource ACL. For example:

~~~text
GrantedAuthority "document:read"      -> allowed to use the feature
PermissionEvaluator("Document", 42, "read")
                                       -> allowed on record 42
~~~

Someone may hold the authority to read documents yet lack permission on documents in another tenant. Conversely, an ACL entry granting read access does not replace authentication, account-lock checks, or feature-level policies.

### 10.4. Nonexistent vs. unauthorized

Returning `hasPermission(...) == false` when an ACL/record does not exist is a safe default. However, if code returns 403 for nonexistent resources and 404 for existing unauthorized ones, callers can probe existence from the differing responses. Place resource-hiding/distinguishing policies where full context is available and test for consistent status codes. Never leak title, owner, tenant, or status inside evaluator messages.

### 10.5. Permissions can change between check and execution

When the evaluator loads Document ID 42 to check permission and the service reads it again, another transaction could alter owner/tenant or revoke the ACL. `@PreAuthorize` does not start a transaction automatically, freeze data, or guarantee the earlier result remains valid.

For read-only operations, you can apply tenant/owner predicates inside the query to enforce scope at query time. For write operations, check permission inside the transaction tied to the update, use optimistic/pessimistic locking or conditional updates, and verify the updated row count; choose an appropriate isolation level. Never place the sole guard at the controller and ignore the data layer.

### 10.6. N+1 queries and list-level permission checks

If you use:

~~~java
@PostFilter("hasPermission(filterObject.id(), 'Document', 'read')")
public List<Document> listAll() {
    return repository.findAll();
}
~~~

the evaluator can query the ACL **per element**, causing N+1 queries and loading unauthorized data into memory before filtering. For large datasets, use DB queries already scoped by tenant/owner/ACL, batch ACL lookups, or row-level security; use `@PostFilter` as an extra defense where the contract fits. Pagination and total record counts will be wrong if filtering occurs after fetching a page.

### 10.7. When using Spring's AclPermissionEvaluator

The Spring Security ACL module implements `PermissionEvaluator` with `AclService`, ACL entries, and object identities. It is a dedicated solution for complex per-object permissions; it requires the `spring-security-acl` dependency, ACL schema, and proper service/cache/permission factory configuration.

This lesson's in-memory custom evaluator **has no ACL inheritance**, no `BasePermission` bitmasks, and no persistence, auditing, or tenant routing beyond what the code explicitly writes. Never assume that merely wiring `AclPermissionEvaluator` without preparing ACL data will magically infer entity owners.

## 11. Choosing between @PreAuthorize and @PostAuthorize when needing a target object

### 11.1. Using ID before the call

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document loadById(Long id) {
    // Only enters the method if the evaluator allows it.
}
~~~

Suitable when the ID suffices to look up metadata/ACL and you want to block access before the service loads/returns the resource. If both evaluator and service query the DB, there is extra cost; consider combined policy queries or transactions to avoid races.

### 11.2. Using the object after the call

~~~java
@PostAuthorize("hasPermission(returnObject, 'read')")
public Document loadThenCheck(Long id) {
    return store.find(id).orElseThrow();
}
~~~

Here the body runs first, then the evaluator receives `returnObject`. This can be convenient when permission depends on properties of the loaded object. However, the body has already run, and if it wrote to the DB or emitted events, post-authorization will not automatically undo all side effects. For mutations, prefer pre-authorization and checks close to the write.

### 11.3. Do not use the wrong overload

~~~java
// A target object, two arguments:
@PreAuthorize("hasPermission(#p0, 'read')")

// An ID, three arguments:
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
~~~

If a `Long` ID is passed to the two-argument **object** overload, the evaluator receives `Long` as a targetDomainObject without an explicit type; the custom evaluator above only supports `Document` objects and will return false. That is not a Spring bug—it comes from writing the wrong expression variant.

## 12. Common mistakes and fixes

### Mistake 1 — Writing three arguments while only implementing the object overload

The interface requires two methods; if the ID overload always returns false or is unimplemented, every call through `hasPermission(id, type, permission)` is denied. Implement both overloads per contract or intentionally separate support, with tests ensuring the expression hits the ID branch.

### Mistake 2 — Confusing targetType with automatic class resolution

`"Document"` is an application-chosen literal. Spring does not automatically turn it into an entity and look up its owner; the evaluator/ACL resolver does that. Use an allow-list and consistent type conventions.

### Mistake 3 — Treating hard-to-guess IDs as access control

Being able to guess a UUID does not mean permission to view a resource. Check principal, tenant, owner/ACL, and permission at a trusted layer; never rely on ID entropy as your sole security model.

### Mistake 4 — Reading tenant from a header and trusting it immediately

A client can send `X-Tenant: victim`. Compare any tenant selector against the principal's and record's trusted tenant; restrict repository queries by tenant to avoid cross-tenant data leaks.

### Mistake 5 — Turning every error into true to “avoid blocking business”

An ACL/DB timeout must never result in GRANT. Handle errors observably and fail closed per your threat model; never swallow exceptions and return true or fall back to admin.

### Mistake 6 — Failing to handle null and ID types

A null `targetId` or an `Integer` instead of `Long` must be rejected or cleanly normalized. Avoid blind casts that throw uninformative `ClassCastException`s or accidentally match a different resource.

### Mistake 7 — Trusting client data in the object overload

`hasPermission(candidate, 'read')` that only checks `candidate.owner == authentication.name` is vulnerable to owner spoofing. Verify the target comes from a trusted data store or use the ID overload + lookup inside the evaluator.

### Mistake 8 — Allowing access based on feature authority without resource ACL

`hasAuthority('document:read')` does not prove a user may view every document. Combine the authority with per-resource permissions or enforce explicit query scoping/ACLs.

### Mistake 9 — Forgetting @EnableMethodSecurity or calling via self-invocation

Tests using `new Service` or `this.securedMethod()` can bypass proxies. Ensure beans are called through Spring and write DENY tests to catch inactive annotations.

### Mistake 10 — Reading/writing after check while forgetting races/transactions

Permission holds at t1, but owner/tenant changes at t2; the method still operates on t2 data. Check at the point of access/write within transaction boundaries or use conditional queries and locking.

### Mistake 11 — Returning inconsistent status codes or error details

“Unauthorized” is typically 403, “unauthenticated” is typically 401, and “hide existence” may be 404, yet method security alone does not guarantee uniform responses. Design exception handling and HTTP tests to prevent enumeration.

### Mistake 12 — Using @PostFilter on thousands of items instead of properly scoped queries

Evaluating `hasPermission` per element can trigger N+1 queries, break totals/pagination, and increase load. Apply scoping/filtering in DB queries, batch ACL checks, and reserve post-filtering for reasonable sizes.

## 13. Practical testing checklist

| Test case | Expected |
| --- | --- |
| User with authority, tenant, owner, and read permission | Allows the right document |
| User lacking authority | DENY, even if owner matches |
| User with authority but wrong tenant | DENY |
| User with authority and tenant but wrong owner | DENY |
| Wrong target type | DENY |
| Wrong or unsupported permission | DENY |
| Null / wrong-type / nonexistent ID | DENY or controlled input error |
| Domain object with forged owner | DENY if stored data does not confirm |
| Real evaluator not configured | DENY/GRANT tests catch misrouted calls |
| User invokes service through bean proxy | Annotations actually enforced |
| Self-invoked method | Bypass risk detected and refactored |
| Concurrent ACL or tenant change | Never returns/writes unauthorized data per transaction policy |
| Large list dataset | No N+1 / over-fetch or broken pagination |
| Database/ACL provider failure | Fail closed, monitored, no data leaked |

**Exercise:** Alice has authority `document:read` and tenant alpha. Document ID 42 is in tenant beta. Should `@PreAuthorize("hasPermission(#id, 'Document', 'read')")` return true if Alice knows the exact ID 42?

**Answer:** No. Knowing a valid ID is not permission. The evaluator must read owner/tenant/ACL from trusted data and deny when Alice is outside the scope. If the resource must be hidden, the API must design consistent 403/404 responses without putting document 42's metadata in error messages.

**Advanced exercise:** Alice passes the evaluator for a valid Document ID 1, but her ACL is revoked right before the service reads it again. Is `@PreAuthorize` alone enough?

**Answer:** It does not guarantee safety when data changes between check and use. Permissions must be enforced at the actual read/write site or inside a transaction with scoping/locking and a consistent policy, especially for update/delete operations.

## 14. Technical summary

The three-argument expression `hasPermission(targetId, targetType, permission)` expresses authorization on an **unloaded** resource using its ID and an application/ACL-defined type name. Spring calls `PermissionEvaluator.hasPermission(Authentication, Serializable, String, Object)`; the evaluator must check identity, resource scope, ACL, and action against trusted data, then deliberately return true/false.

The two-argument expression `hasPermission(targetObject, permission)` uses the object overload, which is safe only when the object is already trusted or re-verified. Both depend on `MethodSecurityExpressionHandler`, Spring proxies, and enabling `@EnableMethodSecurity`. Most importantly: **ID + type + permission is only a request to check authorization; it is not proof that permission was granted**.

## Official documentation

- [Spring Security API – PermissionEvaluator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): the two overloads, `Serializable targetId` and `targetDomainObject` parameters, and permission semantics.
- [Spring Security API – SecurityExpressionOperations](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/SecurityExpressionOperations.html): `hasPermission(target, permission)` and `hasPermission(targetId, targetType, permission)`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP, and expression customization.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): examples of `AclPermissionEvaluator`, `AclService`, ACL records, and `static @Bean` `MethodSecurityExpressionHandler`.
- [DefaultMethodSecurityExpressionHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html): expression handler for method security.
