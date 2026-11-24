# The `PermissionEvaluator` Contract and `Authentication` Context in Spring Security

## 1. What does `hasPermission` check?

Spring Security can check coarse-grained permissions using `hasAuthority('document:read')`. However, that authority only states that the user **has the capability to read documents in general**; it does not answer whether this user is allowed to read **document 11**.

Suppose:

- `alice` has authority `document:read` and owns document `11`.
- `bob` also has authority `document:read` but owns document `12`.
- `carol` owns document `13`, yet was not granted authority `document:read`.
- Users may send an ID or an entire object/DTO from the client; client-supplied `owner` data can be tampered with.

To check permissions per resource, Method Security provides the `hasPermission(...)` expression. The expression **delegates the decision** to a `PermissionEvaluator`. The evaluator receives the **authenticated identity** and the **resource/permission** from the expression system and returns `true` or `false`.

The core focus of this article is the **API contract of `PermissionEvaluator` and how `Authentication` is passed accurately**, not merely how to write annotations. We will understand where each argument comes from, how to handle principal types, `anonymous` cases, `null` targets, how to register the evaluator, and how to test through a Spring proxy.

After this lesson, you will be able to:

1. Correctly implement **both overloads** of `PermissionEvaluator`.
2. Explain why `Authentication` appears in the Java interface but is not written as an argument to `hasPermission(...)` in SpEL.
3. Distinguish `getName()`, `getPrincipal()`, `getAuthorities()`, and `isAuthenticated()`.
4. Wire the evaluator into `DefaultMethodSecurityExpressionHandler` via a Spring bean.
5. Implement permission decisions based on server-side data, **never trusting** `owner`/`tenant` in a client DTO.
6. Handle `null`, anonymous users, invalid IDs/resource types, and unsupported permissions using the **fail closed** principle.
7. Write a standalone Java 17+ / Spring Boot application and tests verifying permission checks by both object and ID.

**Scope:** Spring Security 6.x on Spring Boot 3.x, using Spring Method Security and Spring AOP proxies. The ACL module is one option for providing an evaluator, but is **not required** to implement this interface.

## 2. `PermissionEvaluator` is a contract, not an authorization database

The interface lives at `org.springframework.security.access.PermissionEvaluator`. In Spring Security 6.x, its two core methods are:

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

The snippet above shows the **abbreviated contract signatures** for study, not a Spring Security source file; when implementing it, `import` the actual interface from the library.

| Argument | Type | Meaning |
| --- | --- | --- |
| `authentication` | `Authentication` | Identity currently used by Spring Security to evaluate access |
| `targetDomainObject` | `Object` | Target object already in hand (may be `null`) |
| `targetId` | `Serializable` | Object ID when no instance is available to pass directly |
| `targetType` | `String` | Domain object type: class name or consistent alias understood by the evaluator/ACL |
| `permission` | `Object` | Permission representation (`"read"`, `"write"`, enum, mask…), depending on the application contract |
| Return value | `boolean` | `true`: allow; `false`: deny |

**Commitments that must be respected:**

- The normal contract expects `authentication` to be provided and **non-`null`**; a defensive evaluator should still deny access when encountering unexpected input.
- For the object overload, `targetDomainObject` **can be `null`** and the implementation **should return `false`**; the application can explicitly check for null in SpEL if desired.
- `permission` is passed **verbatim from the expression**. If the expression passes the string `'read'`, the evaluator receives `String "read"`; if it passes an enum/object, the evaluator receives that corresponding type. Do not assume every permission is a `String` if your policy supports multiple types.
- For the ID overload, **`targetType` is a conventional string**: Spring does not automatically look up an entity/repository from an arbitrary name. When using ACL, this string must match ACL's `ObjectIdentity` creation mechanism.
- The interface **does not implement** permission rules itself, does not read a database, and does not guarantee the record stays protected after returning `true`. The policy source and concurrency handling remain the application's responsibility.

### 2.1. Two SpEL call forms map to two Java signatures

**Form 1 — with an object:**

```java
@PreAuthorize("hasPermission(#document, 'read')")
public String readByObject(@P("document") Document document) {
    // Runs only after the evaluator grants permission.
    return store.require(document.id()).content();
}
```

Under the hood, Spring invokes the signature:

```text
hasPermission(
    Current Authentication,
    document,
    "read"
)
```

**Form 2 — with only ID and resource type:**

```java
@PreAuthorize("hasPermission(#id, 'Document', 'read')")
public String readById(@P("id") Long id) {
    // Runs only after the evaluator grants permission.
    return store.require(id).content();
}
```

Spring invokes:

```text
hasPermission(
    Current Authentication,
    id,
    "Document",
    "read"
)
```

The two Java annotation snippets above are **illustrative fragments**, assuming `Document`, `store`, and `@P` as in the full program in section 7.

**There is no `authentication` argument in SpEL's `hasPermission(...)`.** The Method Security expression root retrieves `Authentication` from the call's security context and passes it to `PermissionEvaluator` as the first argument. You do not need to require controllers to accept `Authentication` in a request body.

### 2.2. How do `hasAuthority`, `hasRole`, and `hasPermission` differ?

| Expression | Question | Decision source |
| --- | --- | --- |
| `hasAuthority('document:read')` | Does the caller hold this exact authority? | `Authentication.getAuthorities()` |
| `hasRole('EDITOR')` | Does the caller hold the corresponding role (typically `ROLE_EDITOR`)? | `Authentication.getAuthorities()` + role prefix |
| `hasPermission(#doc, 'read')` | Is the caller allowed this permission on the object? | `PermissionEvaluator` and policy data |
| `hasPermission(#id, 'Document', 'read')` | Is the caller allowed this permission on the object with this ID/type? | `PermissionEvaluator` and policy data |

An evaluator can combine a **general authority** with **object-specific conditions**, as in the example. Never assume that the string `'read'` in a permission automatically matches `document:read` in `GrantedAuthority`. The mapping is a **rule you must define yourself**.

## 3. What is `Authentication` and where does it come from?

`Authentication` belongs to `org.springframework.security.core.Authentication`, extending `Principal` and `Serializable`. It represents an authentication request or an authenticated principal. Once a valid authentication mechanism finishes processing, the token is normally placed into `SecurityContext`, accessed via `SecurityContextHolder`.

Flow in a typical Servlet application:

```text
HTTP request
   |
   v
Spring Security filter chain
   |-- validate session / JWT / authentication provider
   |-- build trusted Authentication
   v
SecurityContextHolder -> SecurityContext -> Authentication
                                          |
                                          v
                                    Method Security
                                    @PreAuthorize SpEL
                                          |
                                          v
                                      hasPermission(...)
                                          |
                                          v
                                    PermissionEvaluator
```

If a scheduler or message consumer invokes a protected method, **Method Security can still be used without an HTTP request**; however, it requires a valid security context/identity established by the application through a trusted mechanism. Never treat a background job as `ADMIN` implicitly without an explicit authorization model.

Key APIs to know:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Object principal = authentication.getPrincipal();
var authorities = authentication.getAuthorities();
boolean authenticated = authentication.isAuthenticated();
```

This is an illustrative snippet; **check `authentication != null` before dereferencing**.

### 3.1. `getName()` and `getPrincipal()` are not identical

- `getName()` returns the name represented by `Authentication` per the `Principal` contract. With username/password it is usually the username; with JWT/OIDC it may be the subject, a configured claim, or another identifier.
- `getPrincipal()` returns an object: it could be `UserDetails`, `Jwt`, `OAuth2User`, a username string, or a custom principal. **Never blindly cast** the principal to `String` or an application class.
- `getAuthorities()` returns `GrantedAuthority` instances, such as `document:read`. It does not inherently contain per-record permissions unless the system maps them that way.
- `getDetails()` holds additional authentication details such as request metadata depending on the provider; **never automatically treat details as a trusted identity/tenant**.
- `getCredentials()` often holds secrets or authentication proof. **Do not use credentials as cache keys, and do not log them**.

In multi-tenant applications, extract a **stable internal subject ID** and verified tenant from the principal/claims or repository. Never use unverified `X-User` or `X-Tenant` request headers as the source of authorization decisions. If `getName()` is not the stable ID used by policy, write an adapter that resolves the proper subject from the chosen `Authentication` type.

### 3.2. `isAuthenticated() == true` does not necessarily mean a real user

There is a common pitfall:

```java
if (authentication != null && authentication.isAuthenticated()) {
    return true;
}
```

The check above is **not sufficient** to grant document read access. `AnonymousAuthenticationToken` in Spring Security can report `isAuthenticated() == true` per the token's contract, even though the caller is only an anonymous user.

Use `AuthenticationTrustResolver` to distinguish anonymous users:

```java
AuthenticationTrustResolver trustResolver =
    new AuthenticationTrustResolverImpl();

boolean realAuthenticated =
    authentication != null
    && authentication.isAuthenticated()
    && !trustResolver.isAnonymous(authentication);
```

This is an illustrative snippet requiring imports for `org.springframework.security.authentication.AuthenticationTrustResolver` and `AuthenticationTrustResolverImpl`. Additional policies may distinguish **remember-me**, recent authentication, or MFA for sensitive operations. Never treat `isAuthenticated()` as sufficient proof for object-level access.

### 3.3. Context is managed per execution thread

In standard Servlet configurations, `SecurityContextHolder` binds context per thread by default. Spring Security actively populates and clears it during the request flow. If you offload work to `@Async`, an executor, `CompletableFuture`, or a manually spawned thread, authentication is **not automatically propagated**.

For async tasks that genuinely need the caller's identity, use `DelegatingSecurityContext...` mechanisms or propagation patterns supported by Spring Security, clearly defining scope and cleanup timing. Do not use `MODE_INHERITABLETHREADLOCAL` as a blanket solution for long-lived thread pools without understanding identity-leakage risks.

In the command-line example below, we create the context explicitly and **clear it in `finally`** to avoid leaking identity to another task. That is a simulation technique for the demo, **not** a guide for authenticating real users manually.

## 4. Every Method Security call receives its own `Authentication`

With `@PreAuthorize`, the typical flow is:

```text
Caller -> Spring-managed service proxy
             |
             v
       @PreAuthorize interceptor
             |
             v
    Security expression evaluation
      |-- read MethodInvocation & arguments
      |-- obtain Supplier<Authentication>
      |-- evaluate hasPermission(...)
             |
             v
      PermissionEvaluator
             |
       true / false
        |      |
        v      v
      body   AccessDeniedException
```

`PermissionEvaluator` is usually a **Spring singleton bean** reused across many requests. Therefore the evaluator **must not store the current request's `Authentication` in a mutable field** and reuse it later: that causes race conditions and can expose another user's identity.

Correct:

```java
@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {
    return policy.canAccess(authentication, target, permission);
}
```

Flawed design:

```java
// Snippet DO NOT USE:
private Authentication currentAuthentication;

@Override
public boolean hasPermission(
        Authentication authentication,
        Object target,
        Object permission) {
    this.currentAuthentication = authentication;
    return evaluateLater(target, permission);
}
```

With concurrent requests, the `currentAuthentication` field gets overwritten. Keep the evaluator **stateless with respect to per-request identity** and pass `Authentication` as a parameter; any authorization caching must be keyed by principal/tenant/resource/action and include invalidation when permissions change.

### 4.1. `PermissionEvaluator` is not `AuthenticationManager`

- `AuthenticationManager`/`AuthenticationProvider` determines **who is calling** and produces/verifies authentication.
- `PermissionEvaluator` determines **what an authenticated principal may do on a resource**.
- `AuthorizationManager` is the modern general-purpose authorization mechanism used by Spring Security at request and method levels. `hasPermission` is a hook inside **Method Security expression evaluation** that delegates to `PermissionEvaluator`.
- `AclPermissionEvaluator` is an implementation integrating Spring Security's ACL system; the interface does not require you to use the ACL library.

Never let `PermissionEvaluator` check passwords itself, perform token login, or construct a `UsernamePasswordAuthenticationToken` solely from a client-supplied ID. Clear separation of responsibilities makes policies easier to audit and test.

## 5. How to wire `PermissionEvaluator` into Method Security

**Two separate steps** are required:

1. Enable Method Security with `@EnableMethodSecurity`.
2. Register the evaluator on the `MethodSecurityExpressionHandler` used by Spring Security.

Configuration example:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Use a `@Bean static` method so the expression handler is published **early** when Spring Security initializes method security configuration classes. Having a `@Component PermissionEvaluator` bean **without attaching it to the expression handler** does not ensure SpEL will use your implementation.

If you do not configure an evaluator for your policy, `hasPermission` does not automatically infer owners or ACLs. `DefaultMethodSecurityExpressionHandler` uses a deny-all evaluator (`DenyAllPermissionEvaluator`) as its conservative default. Always test at least one **allowed** path and one **denied** path, because testing only denial cases can “pass” even if your evaluator was never invoked.

`@EnableMethodSecurity` must be on a configuration class loaded into the `ApplicationContext`. Callers must invoke the **Spring-managed** service bean. Instantiating with `new`, self-invoking `this.protectedMethod(...)`, or placing annotations on methods that cannot be intercepted by the proxy will prevent enforcement as expected.

## 6. Policy design: where can trusted arguments come from?

Divide inputs into two categories:

**Trusted after server-side verification:** `Authentication` produced by a security filter/provider, database records, repository metadata, ACLs, tenants, and permissions originating from a verified administrative system.

**Never trust automatically:** IDs, objects/DTOs, `claimedOwner`, `tenantId`, roles, quotas, and usernames sent in the request. Clients can modify all of those values.

Consider a DTO sent by a client:

```json
{
  "id": 11,
  "owner": "bob",
  "content": "Self-filled content"
}
```

If the database establishes that `id=11` belongs to `alice`, `bob` **must not** be granted read permission merely because the object claims `owner=bob`. A safe evaluator may take the **ID from the object** while looking up the **real owner from the repository** before deciding. Moreover, once permitted, the service must return **server-stored content**, not echo back client-supplied content.

In multi-tenant applications, identical owner names across two tenants are normal; rules should also check the verified tenant. For sensitive data, policies must also address sharing, status, field-level permissions, and revocation.

| Case | Expected evaluator behavior |
| --- | --- |
| `targetDomainObject == null` | `false` |
| Object is not of the domain type | `false` |
| `targetId == null` or ID does not exist | `false` |
| `targetType` differs from supported types | `false` |
| Permission not in defined set | `false` |
| Missing or anonymous `Authentication` | `false` |
| Principal has authority but does not own record | `false` |
| Principal owns record but lacks authority | `false` |
| Principal has authority **and** resource policy allows access | `true` |

**Fail closed** does not mean silently swallowing every infrastructure error under `false` without recording it. In production, database/ACL failures need proper observability and error handling, yet a failure must never turn into `true`.

## 7. Complete example: one `PermissionEvaluator` for both object and ID

The example uses **Java 17 + Spring Boot 3.5.8 / Spring Security 6.x**. The app runs with Gradle and needs no HTTP server or database. In-memory data keeps the contract and identity clear.

Demo rules:

- Only allow permission `"read"` on resource type `Document`.
- The caller must hold the exact authority `"document:read"`.
- The caller must be the owner **according to the server record**, not the passed-in object.
- `alice` owns `11`, `bob` owns `12`, `carol` owns `13`.
- Any missing authentication/object/permission must be denied.

### 7.1. File structure

```text
permission-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PermissionContextApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPermissionEvaluator.java
    │   └── DocumentReadService.java
    └── test/java/demo/
        └── DocumentReadServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'permission-context-demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This configuration builds with Gradle (create a Gradle Wrapper if the project does not have one yet). Spring Boot `3.5.8` is a fixed version chosen for the demo, which does not mean a new production project should pick this patch over a newer supported patch release.

### 7.2. Domain object and trusted data source

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(Long id, String owner, String content) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> records = Map.of(
        11L, new Document(11L, "alice", "Alpha"),
        12L, new Document(12L, "bob", "Beta"),
        13L, new Document(13L, "carol", "Gamma")
    );

    public Document find(Long id) {
        return id == null ? null : records.get(id);
    }

    public Document require(Long id) {
        Document found = find(id);
        if (found == null) {
            throw new NoSuchElementException("Document not found: " + id);
        }
        return found;
    }
}
```

`DocumentStore` acts as an in-memory database. A real system should look up by `(tenant, id)` and enforce ownership/ACL on server-side data. The `require` API is called by the service **only after Method Security has granted access**.

### 7.3. Implementing both overloads properly

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

        // Use only the ID to look up the REAL record; never trust document.owner().
        return allowed(authentication, document.id(), permission);
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

        return allowed(authentication, id, permission);
    }

    private boolean allowed(
            Authentication authentication,
            Long id,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasGeneralReadAuthority =
            authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    "document:read".equals(authority.getAuthority()));

        if (!hasGeneralReadAuthority) {
            return false;
        }

        Document fromServer = store.find(id);
        return fromServer != null
            && authentication.getName().equals(fromServer.owner());
    }
}
```

**Explaining the contract:**

1. The `Object` method accepts only a `Document`. When target is `null` or another type, `instanceof` returns `false`; no `NullPointerException` occurs.
2. The `Serializable, String` method requires `targetType` to be exactly `"Document"` and ID to be `Long`. If a system uses UUIDs, add a `UUID` branch and a dedicated convention.
3. Both overloads call **the exact same `allowed(...)`**, avoiding one invocation path allowing what the other denies for the same record.
4. `authentication` is used **immediately during the call**; it is never placed into a mutable field. `Authentication` can have various implementation classes; the logic uses `getName()` and `getAuthorities()` per the interface.
5. `isAuthenticated()` alone is insufficient because anonymous can return `true`; `AuthenticationTrustResolver` blocks anonymous callers.
6. Unrecognized permissions, missing authorities, nonexistent records, or mismatched owners all return `false`.
7. `owner`/`content` fields on the caller-supplied object **do not decide authorization**. Only the record returned by `store.find(id)` is used to grant access.

If your project has multiple resource types, do not only check `"Document"` and allow everything else. Split policies per type or use a permission-routing registry; reject any unsupported type.

### 7.4. Service using both forms of `hasPermission`

**`src/main/java/demo/DocumentReadService.java`:**

```java
package demo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {

    private final DocumentStore store;

    public DocumentReadService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasPermission(#document, 'read')")
    public String readByObject(@P("document") Document document) {
        // Return the real server content after access is granted.
        return store.require(document.id()).content();
    }

    @PreAuthorize("hasPermission(#id, 'Document', 'read')")
    public String readById(@P("id") Long id) {
        return store.require(id).content();
    }
}
```

`@P` helps Spring Security resolve parameter names accurately in SpEL, even when compilation does not preserve Java parameter names. Do not confuse `@P` (Spring Security annotation) with `@Param` in JPA. You may use `-parameters` where appropriate, but the annotation makes the example easily reproducible.

With `readByObject`, a caller **might send an object with a forged owner**. The evaluator uses only the ID to look up the real owner, and the method body also returns content from the store. With `readById`, the caller only passes the ID; the evaluator selects the second overload. Regardless of which form is called, authorization must return the same decision for the same record.

### 7.5. Spring Boot application, expression handler, and security context

**`src/main/java/demo/PermissionContextApplication.java`:**

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
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PermissionContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(PermissionContextApplication.class, args);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(DocumentReadService service) {
        return args -> {
            try {
                authenticateAs("alice", "document:read");

                // Intentionally pass owner=bob; ID 11 actually belongs to alice.
                System.out.println("ALICE_OBJECT_11: "
                    + service.readByObject(
                        new Document(11L, "bob", "fake-content")));

                System.out.println("ALICE_ID_11: "
                    + service.readById(11L));

                expectDenied("ALICE_ID_12",
                    () -> service.readById(12L));

                authenticateAs("bob", "document:read");

                System.out.println("BOB_ID_12: "
                    + service.readById(12L));

                // Bob spoofs owner=bob for alice's document ID 11.
                expectDenied("BOB_FORGED_OBJECT_11",
                    () -> service.readByObject(
                        new Document(11L, "bob", "fake-content")));

                authenticateAs("carol");

                // Carol owns #13 but lacks document:read.
                expectDenied("CAROL_NO_AUTHORITY_13",
                    () -> service.readById(13L));

                authenticateAs("alice", "document:read");
                expectDenied("MISSING_ID_99",
                    () -> service.readById(99L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticateAs(
            String username,
            String... authorityNames) {

        List<SimpleGrantedAuthority> authorities =
            Arrays.stream(authorityNames)
                .map(SimpleGrantedAuthority::new)
                .toList();

        var authentication = new UsernamePasswordAuthenticationToken(
            username, "demo-only", authorities
        );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

In this program, `UsernamePasswordAuthenticationToken` is constructed directly with a list of `GrantedAuthority` **only to simulate principals in a learning environment**. Never do this with usernames/roles sent directly by an HTTP client; production applications must use a verified authentication mechanism and populate the context properly.

`@Profile("!test")` prevents the demonstration runner from executing when Spring Boot integration tests activate the `test` profile. A fresh context is created when switching users and cleared in `finally`, avoiding leaking identities between simulation runs.

### 7.6. Running the program and reading the output

In the project root directory:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```bash
.\gradlew.bat bootRun
```

If there is no Gradle Wrapper yet but a compatible Gradle version is installed: use `gradle bootRun` or generate the wrapper before running. Aside from Spring Boot logs, the **seven lines printed by the program** must be:

```text
ALICE_OBJECT_11: Alpha
ALICE_ID_11: Alpha
ALICE_ID_12: DENIED
BOB_ID_12: Beta
BOB_FORGED_OBJECT_11: DENIED
CAROL_NO_AUTHORITY_13: DENIED
MISSING_ID_99: DENIED
```

Analysis:

1. `alice` calls the object overload with `Document(11, owner=bob, content=fake)`, yet the evaluator still looks up the real owner `alice` from the server; it returns the real content `Alpha`.
2. `alice` calls the overload taking ID `11L` and type `"Document"`; the result is also `Alpha`. Both invocation paths agree.
3. `alice` has the authority but **does not own** `12`: denied.
4. `bob` is allowed to read `12` because he owns it and holds the authority.
5. `bob` spoofs `owner=bob` for an object with ID `11`: denied because the store establishes that the real owner is `alice`.
6. `carol` owns `13` but lacks the authority: denied; ownership alone does not substitute for the authority under this policy.
7. ID `99` does not exist: denied per fail closed.

This is a **security context simulation without HTTP**: it demonstrates that Method Security can obtain `Authentication` from `SecurityContextHolder` even when the application has no web endpoints.

## 8. Integration test: verifying the evaluator and proxy actually work

Create **`src/test/java/demo/DocumentReadServiceTest.java`**:

```java
package demo;

import java.io.Serializable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DocumentReadServiceTest {

    @Autowired
    DocumentReadService service;

    @Autowired
    PermissionEvaluator evaluator;

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void supportsBothOverloadsAndIgnoresForgedOwner() {
        assertEquals("Alpha", service.readById(11L));

        // Owner/content from the object are not used as evidence.
        assertEquals("Alpha", service.readByObject(
            new Document(11L, "bob", "invented")));

        var auth =
            SecurityContextHolder.getContext().getAuthentication();
        assertFalse(evaluator.hasPermission(
            auth,
            (Object) null,
            "read"
        ));
        assertFalse(evaluator.hasPermission(
            auth,
            (Serializable) 11L,
            "UnknownType",
            "read"
        ));
        assertFalse(evaluator.hasPermission(
            auth,
            (Serializable) 11L,
            "Document",
            "write"
        ));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void deniesCrossOwnerAccessDespiteForgedDto() {
        assertEquals("Beta", service.readById(12L));

        assertThrows(AccessDeniedException.class,
            () -> service.readById(11L));

        assertThrows(AccessDeniedException.class,
            () -> service.readByObject(
                new Document(11L, "bob", "fake")));
    }

    @Test
    @WithMockUser(username = "carol", roles = "USER")
    void deniesOwnerWhoLacksReadAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(13L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:read")
    void allowsOwnerWithReadAuthority() {
        assertEquals("Gamma", service.readById(13L));
    }

    @Test
    @WithAnonymousUser
    void deniesAnonymousCaller() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void deniesMissingIdAndNullTarget() {
        assertThrows(AccessDeniedException.class,
            () -> service.readById(99L));

        assertThrows(AccessDeniedException.class,
            () -> service.readByObject(null));
    }
}
```

Run:

```bash
./gradlew test
```

The tests use `@SpringBootTest` to build an ApplicationContext, `@ActiveProfiles("test")` to skip the CLI demo, and `@WithMockUser`/`@WithAnonymousUser` from `spring-security-test`. Injecting `DocumentReadService` from Spring ensures calls go through the bean/proxy and `@PreAuthorize` annotations execute.

Direct tests on `evaluator` prove three critical contracts: **null objects**, **wrong target types**, and **unsupported permissions** all return `false`. Tests through the service prove Method Security actually invokes the evaluator with the `Authentication` of each principal. If you merely instantiate `new DocumentReadService(store)`, annotations will not intercept calls and the authorization tests become meaningless.

All tests share an **immutable** (read-only) in-memory store, so there are no mutations causing test-order dependencies.

## 9. `Authentication` in SpEL is not a service parameter

You can write a combined condition:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'Document', 'read')"
)
public String readById(@P("id") Long id) {
    // ...
}
```

This is an **illustrative alternative** for `readById`, not code to add simultaneously to the demo file. The `hasAuthority` expression inspects `Authentication.getAuthorities()` while `hasPermission` invokes the evaluator; using `and` requires both. In the full example, the evaluator already checks the authority itself so every call path stays consistent, making an extra `hasAuthority` in SpEL **valid redundancy but unnecessary**.

You can reference `authentication.name` in a security expression:

```java
@PreAuthorize(
    "authentication.name == #owner and " +
    "hasPermission(#id, 'Document', 'read')"
)
```

However, this snippet **should not be used with a client-supplied `#owner`**: such a comparison only verifies the user can type their own name. Object authorization must compare against the owner of the server record.

### `@PostAuthorize` and `returnObject`

If an object is only loaded after the method runs:

```java
@PostAuthorize(
    "returnObject != null and hasPermission(returnObject, 'read')"
)
public Document load(Long id) {
    return store.find(id);
}
```

This is an illustrative snippet in a service with `store`. `returnObject` is the method's return value. `@PostAuthorize` checks **after** the method completes; do not use it as the sole guard for operations whose side effects already wrote to the database. In the section 7 example, `@PreAuthorize` is appropriate because the method only needs the ID/object beforehand.

### `@PreFilter` and `@PostFilter`

`hasPermission(filterObject, 'read')` can filter elements individually with `@PreFilter`/`@PostFilter`:

```java
@PostFilter("hasPermission(filterObject, 'read')")
public java.util.List<Document> visibleDocuments() {
    return new java.util.ArrayList<>(repository.findAll());
}
```

This is an **illustrative snippet**, requiring a `repository` with `findAll()`. Avoid loading entire datasets and filtering item-by-item for very large collections; the evaluator may trigger N+1 queries. Prefer filtering by owner/tenant/ACL at the repository level when policy allows, while still enforcing access boundaries properly.

## 10. Common mistakes when implementing `PermissionEvaluator`

| Mistake | Impact | Fix |
| --- | --- | --- |
| Implementing only one overload properly | Object form works while ID form always fails or vice versa | Implement both; test both expressions |
| Not attaching the evaluator to the expression handler | `hasPermission` does not use the application policy | `@Bean static MethodSecurityExpressionHandler` + `setPermissionEvaluator(...)` |
| Relying solely on `isAuthenticated()` | Anonymous tokens may be treated as authenticated | Use `AuthenticationTrustResolver`, add explicit policy |
| Casting `getPrincipal()` to `String` regardless of provider | `ClassCastException` with `UserDetails`, JWT, or OAuth2 principals | Use APIs suited to the token type or a principal adapter |
| Reading owner/tenant from a client DTO | Cross-user or cross-tenant access | Look up permissions/owner from server-side storage |
| Returning `true` for unknown targets | Grants access on unknown IDs/types/permissions | Fail closed with `false` |
| Wrong `targetType` | ID overload always denies or reads the wrong type | Define canonical types, consistent with ACL/repositories |
| Storing `Authentication` in a singleton field | Race conditions and identity leakage across requests | Pass `auth` as a parameter per invocation |
| Testing with an object created via `new` | Bypasses the proxy and `@PreAuthorize` | Test using the Spring-managed bean |
| Self-invocation `this.readById(id)` | Interceptor does not run for internal calls | Separate security services or go through the Spring proxy |
| Reading `SecurityContext` on the wrong thread | Missing auth or wrong principal in async code | Use proper security-context propagation |
| Caching permissions for too long | Revoked permissions still allow access | Key by user/tenant/target/action; add invalidation and TTL |
| Checking only before update | Permissions/owner/ACL change between check and write | Use conditional updates, transactions/locks/versioning |
| Abusing `getName()` as a cross-tenant ID | Username collisions across tenants | Use a stable principal ID and a trusted tenant |

**Key diagnostic question:** was the method **intercepted**, or was the evaluator **invoked and returned false**? Those are two different problems. An `AccessDeniedException` after a call can originate from policy or another layer; test/trace the exact call path, while avoiding logging tokens, credentials, or sensitive data.

## 11. Data security, transactions, and performance

### 11.1. ACL and custom evaluators

Spring Security includes `AclPermissionEvaluator` as an implementation capable of checking ACLs by object identity and permission mask. It requires configuring ACL storage, identities, permissions, and corresponding lookups; the `PermissionEvaluator` interface **has no direct dependency** on ACL. A custom evaluator like the demo fits well when authorization depends on owner, organization, tenant, state, or domain-specific policy.

`targetType` in ACL usually needs to reflect class names or configured `ObjectIdentity` mappings; an alias like `"Document"` only makes sense when the evaluator/ACL understands it.

### 11.2. Do not let permission decisions rely on a stale snapshot

A `hasPermission` call might query the owner at `t1`; between then and the update at `t2`, permissions/owner/tenant could change. This is a **TOCTOU (time of check, time of use)** risk. For write operations, guard the condition directly inside the transaction/update statement:

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :documentId
  AND owner_id = :trustedPrincipalId
  AND tenant_id = :trustedTenantId;
```

This is **illustrative SQL**, to be adapted to your schema and business logic. Check the affected row count to verify the update succeeded. Complex policies may require locks, versioning, isolation levels, or re-checking permissions against the updated data state. `@PreAuthorize` does not automatically replace consistency conditions in the database.

### 11.3. Checking N items can trigger N queries

If `PermissionEvaluator` queries the database for each object and `@PostFilter` filters 1,000 documents, there is a risk of 1,000 ACL/owner lookups. Consider pushing predicates down into queries, batching ACL lookups, paginating, and caching with proper invalidation. Never cache a single `allowed=true` result across all principals for performance; policy caches must include full user scope and permission version.

### 11.4. Do not treat `Authentication` itself as eternal data

Token authorities may be issued at login time, while object permissions can change in the database. If a document is unshared or permissions are revoked, the policy must observe updates in line with business sensitivity. For long-lived JWTs or multi-instance systems, consider revocation, ACL versioning, and clear caching policies.

## 12. Self-check exercises

1. **Which overload does `hasPermission(#document, 'read')` use?**  
   `(Authentication, Object targetDomainObject, Object permission)`.

2. **Which overload does `hasPermission(#id, 'Document', 'read')` use?**  
   `(Authentication, Serializable targetId, String targetType, Object permission)`.

3. **Why does the annotation not include an `Authentication` argument?**  
   The Method Security expression root retrieves authentication from the call's security context and supplies it to the evaluator.

4. **Is `getPrincipal()` always a `String` username?**  
   No; depending on the provider it may be `UserDetails`, `Jwt`, `OAuth2User`, or another object.

5. **Does `isAuthenticated() == true` prove the caller is not an anonymous user?**  
   No. Check `AuthenticationTrustResolver` and your authorization policy.

6. **A client sends object ID 11 with owner = bob while the server stores owner = alice. Is `bob` granted access?**  
   No. Self-reported owner data must not be trusted; the evaluator must check the server record.

7. **Is Spring Security ACL required to implement `PermissionEvaluator`?**  
   No. The interface can use your application's own policy/repository.

8. **If `targetDomainObject` is `null`, what should the evaluator do?**  
   Return `false`, unless the expression already handles null explicitly in a clear policy branch.

9. **If a `PermissionEvaluator` bean exists but `hasPermission` is always denied, what should you check?**  
   Whether `MethodSecurityExpressionHandler` has the evaluator attached; whether `@EnableMethodSecurity`, proxies, SpEL names, type/ID/permission, and policy data match.

10. **Why must `Authentication` not be stored in a field of a singleton evaluator?**  
    Because concurrent requests can run simultaneously, leaking or mixing information across different principals.

11. **Why is an owner check before a method insufficient for a highly sensitive update?**  
    Because permission state can change between check and update; appropriate write-time/transactional conditions are needed.

12. **Can a job without an HTTP request use `hasPermission`?**  
    Yes, if called through a Spring proxy and a trusted security context/identity is properly established.

## 13. Official documentation and key takeaways

- [Spring Security — `PermissionEvaluator` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): the two signatures, `targetDomainObject`, `Serializable`, `targetType`, `permission`, and `boolean` return contract.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `hasPermission`, SpEL, expression handler configuration, proxies, and testing.
- [Spring Security — `Authentication` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html): `getName`, `getPrincipal`, authorities, and `isAuthenticated`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): roles/authorities and authorization mechanisms.
- [Spring Security — `AuthenticationTrustResolver` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): distinguishing anonymous callers and authentication levels.
- [Spring Security — Method Security Tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`.
- [Spring Security — ACL](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): the ACL option when per-domain-object permissions are needed.

**Conclusion:** `PermissionEvaluator` is an **object-level decision contract**, not an authentication engine. `Authentication` comes from Spring Security for the **current call**, not from a client DTO; the `hasPermission` expression passes it to the matching overload automatically. A solid evaluator handles both object and ID forms, never trusts self-declared owner/tenant fields, denies unknown cases, and never stores identity in singleton state. Finally, always test through Spring-managed proxies and protect data consistency when state or permissions change.