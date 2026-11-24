# `hasPermission`: Authorization by Direct Object or Object Identifier

## 1. Problem and goals

In Spring Security, `hasRole('EDITOR')` or `hasAuthority('document:write')` checks a caller's general permissions. However, having permission to edit documents **does not mean** being allowed to edit **every** document. For example:

- `alice` may read and edit document `#1`, which she owns.
- `bob` may read and edit document `#2`, which he owns.
- Both hold the `USER` role; checking `hasRole('USER')` alone cannot distinguish document `#1` from `#2`.

`hasPermission(...)` is a Spring Security expression function that asks a `PermissionEvaluator`: **does the currently authenticated user hold a specific permission on this specific object?**

After this lesson, you will be able to:
1. Distinguish between `hasPermission(targetObject, permission)` and `hasPermission(targetId, targetType, permission)`.
2. Understand how `Authentication`, the object/ID, resource type, and permission are passed to `PermissionEvaluator`.
3. Integrate a custom `PermissionEvaluator` with `@EnableMethodSecurity` and `@PreAuthorize`.
4. Test ownership-based authorization, denial cases, and forged inputs.
5. Recognize the limits of pre-invocation checks, post-invocation checks, ACLs, and performance implications.

**Scope:** object-level authorization in Spring Security Method Security. This lesson focuses on the two `hasPermission` signatures; full ACL administration and enterprise authorization architecture are natural extensions.

## 2. Two ways to call `hasPermission`

### 2.1. Object already available: `hasPermission(targetObject, permission)`

```java
@PreAuthorize("hasPermission(#document, 'read')")
public String readTitle(@P("document") Document document) {
    // Only runs when PermissionEvaluator allows reading the object.
    return document.title();
}
```

This expression passes **the `document` object** and the `'read'` permission. Spring Security retrieves the caller's `Authentication` from the security context and delegates the decision to:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);
```

This form fits when the method receives a **trusted** domain object loaded on the server side, or when `PermissionEvaluator` can extract the ID from the object to cross-check against trusted server data.

**Important warning:** if the object is a client-submitted JSON/DTO, fields like `owner` can be forged. Checking `document.owner().equals(authentication.getName())` on a client DTO does not prove the caller owns the database record. The complete example below always looks up the owner in server-side storage.

### 2.2. Only identifier available: `hasPermission(targetId, targetType, permission)`

```java
@PreAuthorize("hasPermission(#id, 'Document', 'write')")
public void rename(@P("id") Long id, String title) {
    // Only runs after verifying the caller has write permission on Document/id.
}
```

This expression uses **three arguments**, corresponding to the evaluator signature:

```java
boolean hasPermission(
    Authentication authentication,
    java.io.Serializable targetId,
    String targetType,
    Object permission
);
```

Components:

| Component | Meaning | Example |
| --- | --- | --- |
| `#id` | Record ID, must be compatible with `Serializable` | `1L` |
| `'Document'` | Resource type name understood by the evaluator | `Document` |
| `'write'` | Permission to check | `write` |
| `Authentication` | Currently logged-in user, supplied automatically by Spring | `alice` |

`targetType` is a **string**, not a Java `Class` object automatically mapped by Spring. With a custom evaluator, you can use a stable alias like `'Document'`; if using the ACL framework, the type identifier convention must stay consistent with your ACL configuration (often the class name). Just because a client supplies ID `1` does not mean that ID belongs to the declared resource type or permission.

### 2.3. Which form should you choose?

| Criterion | With object | With ID only |
| --- | --- | --- |
| Syntax | `hasPermission(#document, 'read')` | `hasPermission(#id, 'Document', 'read')` |
| Java signature | `(Authentication, Object, Object)` | `(Authentication, Serializable, String, Object)` |
| Input argument | Domain object/DTO | ID and resource type |
| Typical situation | Service already received entity from server layer | Controller/service receives ID from URL or command |
| Security requirement | Verify trustworthy origin of the object | Look up real permissions using ID and type |
| Potential cost | ACL check or lookup by object/ID | May need to load record/ACL from data store |

Both forms ask **the same permission policy**, just through two different signatures. Keep the underlying decision logic unified rather than letting the two forms return contradictory answers for the same record.

## 3. Processing flow and components

```text
Caller (HTTP controller / service / test)
                |
                v
        Spring-managed proxy
                |
                v
  @PreAuthorize("hasPermission(...)")
                |
                v
 Spring Method Security expression
  - reads current Authentication
  - extracts #document or #id
  - resolves 'read'/'write' permission
                |
                v
        PermissionEvaluator
      /                    \
 (object, permission)   (id, type, permission)
      \                    /
       v                  v
     Trusted ACL / DB / policy service
                |
          true / false
                |
        +-------+--------+
        |                |
      true             false
        |                |
  enter method body  deny invocation
                     AccessDeniedException
```

With `@PreAuthorize`, the decision happens **before the method body is invoked**. If the expression evaluates to `false`, the interceptor rejects the call; the target method does not run. In a web application, security exception handling can translate this outcome into HTTP 403 or another response depending on authentication state and configuration.

`hasPermission` is neither a standalone annotation nor a built-in SQL query. Spring Security provides **the hook to call the evaluator**; the application must define the actual permission policy or integrate a built-in evaluator (such as `AclPermissionEvaluator`).

> Simple rule of thumb: **role/authority** usually states what capability a user has; **object permission** answers what action that user may perform on a specific resource.

## 4. Configuring Method Security and `PermissionEvaluator`

Enable method security with `@EnableMethodSecurity`. To make `hasPermission` execute your application's rules, register your `PermissionEvaluator` on `DefaultMethodSecurityExpressionHandler`:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
```

Corresponding imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Use `static @Bean` for the expression handler per Spring Security guidance so the bean is ready early when method security configuration initializes. `PermissionEvaluator` can be a Spring-managed `@Component` or `@Bean`.

Without configuring an appropriate granting evaluator, `hasPermission` **does not automatically know** your system's ownership or ACL data; the default `DenyAllPermissionEvaluator` denies permission checks. Never assume merely adding the expression automatically protects records.

`@EnableMethodSecurity` works via Spring AOP in standard proxy configurations; you must invoke methods through a **Spring bean/proxy**, not call `new Service()` or self-invoke `this.securedMethod(...)` within the same bean and expect annotations to apply.

## 5. Complete Java 17+ example: both forms sharing one policy

This example is a command-line Spring Boot application requiring no HTTP server or database. `DocumentStore` simulates server data:

- ID `1` is owned by `alice`.
- ID `2` is owned by `bob`.
- `DocumentPermissionEvaluator` checks `read`/`write` permissions against **server-stored data**, ignoring any owner property sent by the caller.
- `DocumentService.readTitle(document)` uses the **object** form.
- `DocumentService.rename(id, title)` uses the **ID + targetType** form.

To keep illustrative APIs fixed, the example uses **Java 17, Spring Boot 3.3.13 / Spring Security 6.x**. This is an illustrative version; new projects should pick a currently supported Spring Boot release line. The classes and files below form a standalone program.

### 5.1. Project structure

```text
permission-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PermissionDemoApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPermissionEvaluator.java
    │   └── DocumentService.java
    └── test/java/demo/
        └── DocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

No ACL module is needed to run this example: this is a custom evaluator using an in-memory ownership rule.

### 5.2. Domain object and trusted data store

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(Long id, String owner, String title) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> documents = new ConcurrentHashMap<>();

    public DocumentStore() {
        documents.put(1L, new Document(1L, "alice", "Alpha"));
        documents.put(2L, new Document(2L, "bob", "Beta"));
    }

    public Document find(Long id) {
        return documents.get(id);
    }

    public Document rename(Long id, String newTitle) {
        Document updated = documents.computeIfPresent(
            id,
            (key, old) -> new Document(old.id(), old.owner(), newTitle)
        );
        if (updated == null) {
            throw new NoSuchElementException("Document not found: " + id);
        }
        return updated;
    }
}
```

In a real application, `DocumentStore` corresponds to a repository or database permission/ACL lookup layer. Here ownership is kept on the server; an `owner` inside a caller-supplied object is never trusted for authorization.

### 5.3. Implementing both `PermissionEvaluator` signatures

**`src/main/java/demo/DocumentPermissionEvaluator.java`:**

```java
package demo;

import java.io.Serializable;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentStore store;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public DocumentPermissionEvaluator(DocumentStore store) {
        this.store = store;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Document document)) {
            return false;
        }

        // Fetch the REAL record by ID; do not trust owner from the input object.
        return allowed(
            authentication,
            store.find(document.id()),
            permission
        );
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return allowed(authentication, store.find(id), permission);
    }

    private boolean allowed(
            Authentication authentication,
            Document storedDocument,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)
                || storedDocument == null) {
            return false;
        }

        if (!"read".equals(permission) && !"write".equals(permission)) {
            return false;
        }

        return authentication.getName().equals(storedDocument.owner());
    }
}
```

Specific design choices:

1. The object form only accepts `Document`, then **re-fetches the record by `document.id()`**.
2. The ID form only accepts `targetType == "Document"` and `Long` IDs.
3. Both delegate to `allowed(...)`, so the same user, same record, and same permission always yield the same result.
4. If unauthenticated, anonymous, target invalid, record missing, or permission unsupported, it returns `false` (**fail closed**).
5. This lesson grants the owner both `read` and `write`; a real policy may differentiate editors, viewers, document status, shared users, tenants, and more.

Do not confuse `permission` with `GrantedAuthority`: in this example `'read'` and `'write'` are strings interpreted by **the evaluator**, not `ROLE_READ` or authorities automatically mapped by Spring.

### 5.4. Service using both forms in `@PreAuthorize`

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#document, 'read')")
    public String readTitle(@P("document") Document document) {
        // Read server-managed data; do not return the title field from a forged DTO.
        return store.find(document.id()).title();
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'write')")
    public Document rename(@P("id") Long id, String newTitle) {
        return store.rename(id, newTitle);
    }
}
```

`@P("document")` and `@P("id")` make parameter names explicit in SpEL even when the build does not retain parameter names. You can use `-parameters` instead; however, make sure SpEL names match the names discovered by Spring Security.

`readTitle` illustrates authorization on an **already-present object**, while `rename` illustrates the ID-only case; both deny before the method body runs if the evaluator returns `false`.

### 5.5. Configuration, simulated security context, and calling through a Spring bean

**`src/main/java/demo/PermissionDemoApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    CommandLineRunner demonstrate(DocumentStore store, DocumentService service) {
        return args -> {
            try {
                authenticateAs("alice");

                System.out.println("OBJECT alice/1: "
                    + service.readTitle(store.find(1L)));

                System.out.println("ID alice/1: "
                    + service.rename(1L, "Alpha edited").title());

                try {
                    service.rename(2L, "Unauthorized change");
                    throw new IllegalStateException("Access should be denied");
                } catch (AccessDeniedException expected) {
                    System.out.println("ID alice/2: DENIED");
                }

                authenticateAs("bob");
                System.out.println("ID bob/2: "
                    + service.rename(2L, "Beta edited").title());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticateAs(String username) {
        var auth = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContextHolder.getContext().setAuthentication(auth);
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
```

On Windows use `.\gradlew.bat bootRun`. If no Gradle Wrapper is generated and Gradle is installed, use `gradle bootRun`. The four lines printed by the demo code, alongside Spring Boot logs, should be:

```text
OBJECT alice/1: Alpha
ID alice/1: Alpha edited
ID alice/2: DENIED
ID bob/2: Beta edited
```

Interpretation:

- `alice` successfully reads `Document(1, alice, Alpha)` via the object signature.
- `alice` successfully renames ID `1` via the ID/type signature.
- `alice` cannot rename ID `2` because the server record shows the owner is `bob`; `AccessDeniedException` is caught for illustration.
- `bob` successfully renames ID `2` even though both hold the same `ROLE_USER`.

**Example limitation:** manually constructing `UsernamePasswordAuthenticationToken` is **for demo/test simulation only**. Real applications must authenticate callers with proper Spring Security configuration (session, JWT resource server, etc.) and never accept a self-declared username to mint an authenticated token.

## 6. Integration testing: testing calls through the proxy

**`src/test/java/demo/DocumentServiceTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceTest {

    @Autowired DocumentService service;
    @Autowired DocumentStore store;

    @Test
    @WithMockUser(username = "alice")
    void objectFormUsesTrustedOwner() {
        assertEquals(
            store.find(1L).title(),
            service.readTitle(store.find(1L))
        );

        // Even though the object claims owner is alice, ID 2 actually belongs to bob.
        var forged = new Document(2L, "alice", "Forged");
        assertThrows(
            AccessDeniedException.class,
            () -> service.readTitle(forged)
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void idFormAllowsOwnerButRejectsOtherOwner() {
        assertEquals(
            "Allowed edit",
            service.rename(1L, "Allowed edit").title()
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.rename(2L, "Should not persist")
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void idFormAllowsBobOnHisOwnDocument() {
        assertEquals(
            "Bob edit",
            service.rename(2L, "Bob edit").title()
        );
    }
}
```

Run:

```bash
./gradlew test
```

Tests use `@WithMockUser` from `spring-security-test`. Each test calls `@Autowired DocumentService`, meaning calls pass through the Spring bean wrapped with the method-security interceptor. They prove:

- The object signature allows a real owned object and denies an object with a forged owner.
- The ID signature permits edits by the true owner and rejects another owner.
- Changing the current user changes the decision on the same resource type.

You should also test `null` targets, non-existent IDs, unsupported `targetType`s, unknown permissions, and anonymous users. Never test by calling `new DocumentService(store)` and concluding `@PreAuthorize` protects it, because doing so bypasses the proxy.

## 7. `hasPermission` in other annotations

`hasPermission` is a SpEL function usable with other method security annotations whenever the data and evaluation timing fit.

### 7.1. `@PostAuthorize` — checking the return value

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'read')"
)
public Document findDocument(Long id) {
    return documentStore.find(id);
}
```

`returnObject` is the object returned by the method. The check runs **after the method body executes**, fitting queries that need to load the object before deciding read permission. Never use `@PostAuthorize` as the sole protection for operations with side effects: data mutations may have already occurred before the result is denied. For writes, prefer pre-invocation checks and data-layer constraints.

This snippet illustrates syntax inside a bean with `documentStore` injected; it is not a standalone Java file.

### 7.2. `@PreFilter` — filtering input per object

```java
@PreFilter("hasPermission(filterObject, 'write')")
public void updateAllowed(java.util.List<Document> documents) {
    // Receives only the elements remaining after filtering.
}
```

`filterObject` represents each input element. Depending on collection type and Spring's execution, the input list may be mutated; supply a mutable list supporting element removal and clarify whether the business accepts **partial processing**. Filtering does not deny the entire call.

### 7.3. `@PostFilter` — filtering output per object

```java
@PostFilter("hasPermission(filterObject, 'read')")
public java.util.List<Document> listVisibleDocuments() {
    return new java.util.ArrayList<>(documentStore.findAll());
}
```

`@PostFilter` returns the filtered result set to the caller. This is syntax-only; `findAll()` must be provided by your application's repository. Loading an **entire** table and filtering record-by-record can incur high query and memory costs; for large datasets, filter right in the query by tenant, owner, permissions, or ACLs.

### 7.4. Combining global authorities with object permissions

```java
@PreAuthorize(
    "hasAuthority('document:write') and " +
    "hasPermission(#id, 'Document', 'write')"
)
public void updateDocument(@P("id") Long id) {
    // ...
}
```

The first condition requires a general authority; the second requires permission **on that exact ID**. These are independent conditions combined with `and` so access is granted only when both hold. Ensure the authentication layer assigns the right `GrantedAuthority`; evaluator permissions remain a distinct concept from authorities.

## 8. Common errors and fixes

| Issue | Why it happens | Fix |
| --- | --- | --- |
| Every `hasPermission` call is denied | No granting evaluator registered; default is deny-all | Configure `MethodSecurityExpressionHandler.setPermissionEvaluator(...)` |
| Annotation has no effect | Method security not enabled; service created via `new`; self-invocation | Enable `@EnableMethodSecurity`; invoke via Spring bean/proxy |
| `#id` or `#document` fails to resolve | SpEL cannot discover parameter names | Use `@P("id")`, `@P("document")`, or compile with `-parameters` |
| ID form always returns `false` | `targetType` mismatch, ID type mismatch, second overload unimplemented | Align `targetType`, ID type, and both overloads |
| Object form permits wrong user | Trusting client-sent `owner` instead of true owner | Look up server-managed record/ACL before granting permission |
| Data modified despite `@PostAuthorize` | Check runs after method body already caused side effects | Use `@PreAuthorize`, transactions, and data constraints on writes |
| `read`/`write` permissions behave unexpectedly | Evaluator handles different casing/names or ignores unknown permissions | Define clear permission sets, default-deny, and test |
| Slow queries on long lists | Calling evaluator and querying ACL N times | Filter in DB, batch queries, cache properly, or paginate |
| Missing object still allowed | Evaluator logic defaults to true on null/not found | Return `false` when target, type, permission, or user is missing |
| User denied yet mutation occurred | Permission changed between check and update (TOCTOU) | Re-verify/constrain inside transaction or conditional update statement |

A safe convention is **fail closed**: if `targetId` cannot be resolved, `targetType` is unrecognized, the caller is unauthenticated, or `permission` is unknown, deny access. Never use `return true` as a fallback to "fix" configuration bugs.

## 9. Direct object, ID, and ACL: choosing where policy lives

`PermissionEvaluator` is a strategy interface. You can:

1. **Write a custom evaluator** using owner, organization, tenant, or sharing lists stored in the database. Section 5 is a simplified version.
2. **Use Spring Security ACL** when each domain object carries its own permission/ACE list. `AclPermissionEvaluator` integrates with `hasPermission(...)` expressions, though it requires the ACL library, ACL store (`AclService`), object identities, permission masks, and related setup. Enabling `@EnableMethodSecurity` alone does not create ACLs.
3. **Use a dedicated authorization bean** in SpEL, such as `@documentAuthorization.canWrite(authentication, #id)`, if policy logic is richer than the `PermissionEvaluator` interface. This still requires thorough tests and trusted server data.

With ACLs, `targetType` in the ID form must match the ACL `ObjectIdentity`/mapping. With a custom evaluator like this lesson's, an alias `'Document'` is completely valid because the evaluator itself defines how it is interpreted.

### Cost and consistency

With `hasPermission(#id, 'Document', 'write')`, the evaluator typically reads permissions or metadata before the service runs. Between that check and the update, ownership/ACLs could change. In multi-user systems, consider transactions, conditional updates (`UPDATE ... WHERE id = ? AND owner_id = ?`), optimistic locking, or equivalent mechanisms. `@PreAuthorize` is a pre-invocation gate; **it does not provide DB atomicity on its own**.

With hundreds or thousands of objects, per-object checks can trigger N+1 queries. When policy permits, push owner/tenant predicates down to the repository or use batched ACL lookups and caching with proper expiration/invalidation.

### Multi-tenancy

In multi-tenant applications, `authentication.name.equals(owner)` is rarely enough. You must also check the principal's tenant **and** the record's tenant from trusted sources; never accept a caller-supplied tenant ID as proof of authorization.

## 10. Self-check exercises

1. **Which overload does `hasPermission(#document, 'read')` dispatch to?** → Overload `(Authentication, Object targetDomainObject, Object permission)`.
2. **Which overload does `hasPermission(#id, 'Document', 'write')` dispatch to?** → Overload `(Authentication, Serializable targetId, String targetType, Object permission)`.
3. **Who supplies `Authentication` to the evaluator?** → Spring Security retrieves it from the current security context during expression evaluation; you do not pass `authentication` manually in the annotation.
4. **A client sends `{id:2, owner:"alice"}` when record `#2` actually belongs to `bob`; should `alice` be allowed to edit?** → No. Check server-side owner/ACL, never trust the DTO.
5. **Is adding `hasPermission` without configuring a granting evaluator enough?** → No. The expression is only the hook; an actual policy is required, and the default deny-all does not infer ownership.
6. **Which annotation should you choose to check write permission before a mutation?** → Usually `@PreAuthorize` combined with safe data-layer constraints. `@PostAuthorize` evaluates after the method body.
7. **Must `targetType = 'Document'` be a fully qualified class name?** → Not with a custom evaluator; it is a string interpreted by the evaluator. With ACL or other frameworks, follow the framework's naming convention.
8. **Why do tests need `@Autowired DocumentService`?** → To invoke through the Spring proxy, where Method Security interceptors are actually applied.

## 11. Official Documentation

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): enabling method security, SpEL, `hasPermission`, expression parameters, and configuring expression handlers.
- [Spring Security — `PermissionEvaluator` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): the two `hasPermission` signatures, `Serializable` type, `targetType`, `permission`, and behavior for null objects.
- [Spring Security — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACLs and `AclPermissionEvaluator` integration.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` and testing authorization on Spring beans.

**Key takeaway:** `hasPermission(object, permission)` is for when you have the object; `hasPermission(id, type, permission)` is for when you have the ID. Both delegate the decision to `PermissionEvaluator` with the current `Authentication`. Decision safety depends on the evaluator using **server-trusted permissions and data**, failing closed on unknown cases, and ensuring write operations cannot bypass checks when data changes.