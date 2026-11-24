# SpEL: authentication, principal, Method Parameters, and Policy Beans in Spring Security Servlet

## 1. Learning Objectives

Spring Security can block an HTTP request before a controller, yet a user being allowed to call an endpoint does not mean they may read **every document**, edit **every order**, or access **every tenant's data**. To enforce permissions directly at business operations, Spring Security supports **method security**: placing SpEL (Spring Expression Language) expressions on Spring bean methods using `@PreAuthorize`, `@PostAuthorize`, and related mechanisms.

Four building blocks to master:

1. **`authentication`:** the current `Authentication` object, holding identity, authorities, and authentication state.
2. **`principal`:** the object representing the user inside `authentication.getPrincipal()`; its actual type depends on the login mechanism.
3. **Method parameters:** `#documentId`, `#username`, or `#p0` from arguments passed into the method.
4. **Policy bean:** `@documentPolicy.canRead(authentication, #documentId)` invokes a Spring bean to enforce permission policies more complex than a role check.

This lesson applies to **Spring Security Servlet / Spring MVC**, Spring Security 6.x, and Java 17+. Examples run on Spring Boot 3.3.5 as a consistent API baseline for learning; **do not assume that version is the latest or still under support**. For real products, pick a supported release and check matching APIs.

**Expected outcome:** know how to write valid expressions, understand what supplies data to SpEL, avoid confusing identity with client-sent input, place policies at the right layer, avoid internal calls that bypass proxies, and prove via tests that users cannot access someone else's records merely by guessing IDs.

## 2. Method Security Complements HTTP Authorization

A request typically flows through:

```text
GET /docs/10
    |
Servlet FilterChain -> Spring Security
    |
SecurityContextHolder holds the request's Authentication
    |
AuthorizationFilter / authorizeHttpRequests
    |
DispatcherServlet -> DocumentController
    |
DocumentService bean (Spring-created proxy)
    |
@PreAuthorize expression
    |
ALLOW -> execute DocumentService.read(10)
DENY  -> AccessDeniedException -> handled by security chain
```

`authorizeHttpRequests` answers "does this path/method require login or which role?". Method security answers a deeper question: **"is the authenticated user allowed to invoke this operation with these specific arguments?"**

Examples:

```java
@PreAuthorize("hasRole('ADMIN')")
public void deleteAnyDocument(long documentId) { ... }

@PreAuthorize("authentication.name == #username")
public String readOwnProfile(String username) { ... }

@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document read(long documentId) { ... }
```

These are **annotation/method fragments**, not a standalone program. In a real app, you need `@EnableMethodSecurity`, Spring-managed beans, an appropriate security context, and Java classes with full imports.

**An HTTP role check does not replace object-level authorization.** If `GET /docs/{id}` only requires `authenticated()`, user Bob can guess Alice's `id=10`. If the service has an ownership-checking policy, the request passes HTTP authorization yet is denied at the business boundary.

For tasks invoked from scheduled jobs, listeners, or non-web service calls, method security can protect the same service when an appropriate authentication context is present. Conversely, HTTP matchers never run on non-HTTP entry points. Design caller identity/authorization for those tasks explicitly.

## 3. Enable @EnableMethodSecurity in the Right Place

In Spring Security 6, typical configuration is:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // SecurityFilterChain, UserDetailsService, PasswordEncoder...
}
```

`@EnableMethodSecurity` enables the interceptors needed to evaluate expressions on methods; it enables `@PreAuthorize` and `@PostAuthorize` by default. Legacy code may have `@EnableGlobalMethodSecurity(prePostEnabled = true)`; when migrating to Security 6, adopt the current API and review version differences.

**Without `@EnableMethodSecurity`, annotations on services may not execute at all.** A controller still requiring `authenticated()` can mislead learners into thinking ownership policies are active when only HTTP rules are running.

Method security operates primarily via **Spring AOP proxies/interceptors**. Key principles:

- Annotations should be placed on public methods of Spring-managed service beans.
- Callers must invoke **through the injected bean/proxy**, rather than `new DocumentService(...)` expecting Spring interception.
- Calling `this.read(...)` or another `@PreAuthorize` method **within the same instance** is *self-invocation*, which bypasses the proxy in standard proxy mode.
- Private/final methods, final classes, interfaces, and class-based proxies each have different constraints; never rely on method security for an untested code path.
- Place policy decisions on the **actual entry method invoked by external callers**. If business logic has multiple entry points (HTTP, jobs, messages), enforce at the service/resource boundary rather than only on controllers.
- Never place `@PreAuthorize` on a service method while letting a controller call the repository directly and bypass the protected service.

Spring Security handles both HTTP and method-level denials. With HTTP Basic as in the example project, unauthenticated clients typically receive **401**; authenticated clients whose method expression returns false typically receive **403**. With form login, unauthenticated requests may be redirected rather than returning 401.

## 4. Method Security SpEL Expression Context

A `@PreAuthorize` expression is not ordinary Java code. It is **SpEL** evaluated by Spring Security against a root object and variables provided by method security.

| Expression | Common Meaning | Notes |
|---|---|---|
| `authentication` | `Authentication` from SecurityContext | Property of root expression; typically no `#` prefix needed |
| `authentication.name` | Identity per `Authentication.getName()` | Often easier than casting principal |
| `authentication.authorities` | Current authorities | Not synonymous with per-resource permissions |
| `principal` | `authentication.principal` | Type varies across Basic/form/JWT/OIDC/custom |
| `principal.username` | Username if principal has this property, e.g. UserDetails | Can fail when principal is a String or another object |
| `isAuthenticated()` | Caller has non-anonymous authentication per Spring Security semantics | Does not guarantee MFA or latest account state |
| `hasRole('ADMIN')` | Has ADMIN role under default role prefix | Typically maps to `ROLE_ADMIN` |
| `hasAuthority('document:read')` | Has the exact authority string | Does not automatically add prefix |
| `#documentId` | Argument named documentId on intercepted method | Requires reliable parameter-name discovery |
| `#p0` or `#a0` | Positional argument 0 | Less expressive than names and fragile if parameters reorder |
| `@documentPolicy` | Spring bean named documentPolicy | Bean name must exist and method must be callable |
| `returnObject` | Return value of the method in `@PostAuthorize` | Not usable as return value in `@PreAuthorize` |

**Two distinct prefixes:**

- `#parameterName`: references an argument variable in the evaluation context.
- `@beanName`: references a bean from the Spring ApplicationContext.

Do not write `#documentPolicy.canRead(...)` when aiming for a Spring bean, and do not write `@documentId` when aiming for a method parameter. The example expression `"@documentPolicy.canRead(authentication, #documentId)"` uses both in their proper places.

### Authentication: Who Was Authenticated?

`Authentication` typically exposes:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Collection<? extends GrantedAuthority> roles =
    authentication.getAuthorities();
Object principal = authentication.getPrincipal();
```

This is an illustrative snippet outside an annotation; in Spring Security, `authentication` is injected into the expression context when evaluating method authorization. `getName()` may return a username or another identifier depending on the token.

**Never assume `authentication.isAuthenticated() == true` means a real user.** Some anonymous Authentication instances technically report authenticated; use `isAuthenticated()` on the method-security expression root to apply the framework's anonymous-distinguishing semantics. In production security, also check assurance levels, disabled/locked accounts, or session revocation as required.

Example:

```java
@PreAuthorize("isAuthenticated() and authentication.name == #username")
public String profile(String username) {
    return "PROFILE:" + username;
}
```

If the request is authenticated as `alice`, the user cannot change the path to `/profiles/bob` to fetch Bob's data; `authentication.name` comes from the verified SecurityContext, while `#username` comes from the argument.

### Principal: What Is the Current Object?

`principal` is the object stored in Authentication, yet **there is no single fixed Java class across all login mechanisms**:

- Form login/DAO providers or HTTP Basic with `UserDetailsService` typically use a `UserDetails` object with `getUsername()`.
- A custom AuthenticationProvider may use a domain user object or minimal principal.
- JWT/OIDC Authentication typically holds a principal/token object different from `UserDetails`.
- An anonymous principal may be a string such as `anonymousUser`.

Example when the system guarantees principal is UserDetails:

```java
@PreAuthorize("principal.username == #username or hasRole('ADMIN')")
public String viewProfile(String username) {
    return "PROFILE:" + username;
}
```

If you refactor to JWT and `principal.username` is no longer a matching property, the expression may fail to behave as expected. **A more resilient choice for current user ID is a standardized principal or `authentication.name` with a clear identity contract**. In multi-tenant systems, username alone is usually insufficient; use an immutable user ID and tenant ID from trusted authentication sources.

Never access `principal.password` in SpEL or return it in responses. Never include secrets, raw tokens, or unnecessary PII in exceptions/logs upon policy denial.

## 5. Method Arguments: #documentId, #username, #p0, and Parameter Names

Suppose we have:

```java
@PreAuthorize("authentication.name == #ownerName")
public void updateDocument(long documentId, String ownerName, String text) {
    // Business operation.
}
```

`#ownerName` is a **method argument**. It may originate from a URL, query, request body, or internal caller — **it is not trustworthy data merely because it was passed into a Java method**.

Wrong example:

```java
// Insufficient security if ownerName is self-declared by the client.
@PreAuthorize("authentication.name == #ownerName")
public void updateAnyDocument(long documentId, String ownerName) {
    repository.update(documentId);
}
```

Attacker Alice merely sends `ownerName=alice` while `documentId` is Bob's document; the expression still evaluates to true. **Comparing Authentication against an argument does not prove the argument reflects the true owner in the database.** That is a classic root cause of BOLA/IDOR vulnerabilities.

Better:

```java
@PreAuthorize("@documentPolicy.canEdit(authentication, #documentId)")
public void updateDocument(long documentId, String text) {
    // Policy looks up documentId's owner in a trusted data source.
}
```

The policy bean inspects current authoritative data instead of trusting a client-sent `ownerName`.

### Parameter Name Discovery

For `#documentId` to resolve accurately, Spring Security must know Java parameter names. In Java compilation, enable `-parameters` in the Maven compiler plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Many Boot parent projects already configure support, yet declaring it explicitly clarifies intent and avoids environment dependence. Other options include the `@P` parameter-naming annotation per your Spring Security version's API. Without parameter names, `#p0`/`#a0` can reference the first argument, though it breaks easily if parameter order changes.

**Prefer named parameters so code reviews clearly reflect business intent**, and add integration tests that fail if the expression fails to receive the ID. Do not assume SpEL evaluation/parse errors always fail safely as denials across every setup; errors can raise server exceptions and require clear diagnostics.

### Avoiding Nulls and Type Confusion

If `#documentId` is a nullable `Long`, the policy must handle null. For missing records or invalid IDs, **returning false** during permission checks is generally safer than letting NPE/SpEL errors leak into the service. If the policy fails due to a repository outage, never mask every exception as "unauthorized"; distinguish outages from insufficient permissions in monitoring.

An overly complex expression with chained nested property accesses is prone to NPEs and hard to test. Whenever DB lookups, tenant/ownership resolution, document states, ACLs, or time checks are required, move the logic into a **policy bean** rather than cramming it into an annotation string.

## 6. Policy Beans: Domain-Oriented Authorization

A bean like `@documentPolicy` should:

1. Accept **trusted Authentication from the security context**.
2. Accept **resource ID** from the method argument.
3. Fetch **current resource state** from the repository/database.
4. Check account/tenant/role/owner/permissions per business policy.
5. Return a **boolean** authorization decision without mutating data prior to deciding.
6. Be unit-tested separately for missing resources, unauthorized users, tenant mismatches, and unexpected authorities.

Syntax:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document read(long documentId) { ... }

@PreAuthorize("hasAnyRole('EDITOR', 'ADMIN') and "
        + "@documentPolicy.canEdit(authentication, #documentId)")
public Document update(long documentId, String body) { ... }
```

These two methods are **example fragments**. In Java annotations, concatenating string literals with `+` as above is a compile-time constant, so it is valid; the runnable project below uses single string literals for convenience.

Benefits of a policy bean over long expressions:

- Debuggable and unit-testable like normal Java code.
- Queries repositories by immutable ID and tenant scope rather than relying on forged client inputs.
- Reusable across multiple service methods sharing the same policy.
- Avoids inconsistent duplication of `hasRole`/`principal`/owner checks.
- Easy to extend with caching, metrics, and transaction awareness when needed.

**Check-timing warning:** `@PreAuthorize` runs before the method; if the policy reads owner/permissions and data changes before the mutation runs, TOCTOU (time of check/time of use) can occur. For sensitive financial updates or data locks, re-check permissions **inside the transaction or in conditional update statements**, rather than treating a pre-service annotation as full transaction isolation.

## 7. @PreAuthorize vs @PostAuthorize, @PreFilter, @PostFilter

| Mechanism | Timing | Suitable Use | Limitations |
|---|---|---|---|
| `@PreAuthorize` | Before running method | Block requests when caller lacks role/permission for ID | Policy has no returnObject and may need DB lookup |
| `@PostAuthorize` | After method returns result | Check owner of loaded object before returning to caller | Method has already run; **do not use to guard side effects** |
| `@PreFilter` | Before method, filters compatible input collection | Filter a supported input collection | May alter semantics of batch operations |
| `@PostFilter` | After method, filters compatible output collection | Demo filtering small results | Pays cost of loading unauthorized data; does not replace DB tenant filters |

Data-reading example:

```java
@PostAuthorize("returnObject != null and "
    + "(returnObject.owner() == authentication.name or hasRole('ADMIN'))")
public Document loadDocument(long id) {
    return repository.findById(id).orElse(null);
}
```

This is an illustrative snippet using a record with an `owner()` method. It only makes sense for intentional reads where sensitive-data loading risks are controlled; **never put @PostAuthorize on money-transfer/grant-role/delete methods** expecting it to block the operation, because business code finishes executing before the expression is checked.

For large lists or multi-tenant queries, prefer **WHERE tenant_id = ... AND allowed...** in queries or data-access policies directly in the service rather than returning all records and `@PostFilter`ing. Post-read filtering causes memory/time/side-channel issues and broken pagination.

Spring Security also offers expressions like `hasPermission(...)` when wired with an appropriate `PermissionEvaluator`, though **no domain evaluator is provided by default**. A policy bean is a transparent solution for many applications without full ACL infrastructure.

## 8. Complete Example: Spring Boot 3.3.5 / Java 17 / Maven

The demo application has these endpoints:

| Endpoint | Who Has Access | Policy |
|---|---|---|
| `GET /public` | Anyone | HTTP `permitAll` |
| `GET /docs/{documentId}` | Document owner or ADMIN | `@documentPolicy.canRead(authentication, #documentId)` |
| `PUT /docs/{documentId}` | Owner with ROLE_EDITOR or ADMIN | `hasAnyRole` combined with `@documentPolicy.canEdit` |
| `GET /profiles/{username}` | User with matching username or ADMIN | `principal.username == #username or hasRole('ADMIN')` |

Learning dataset:

```text
Document 10: owner alice, body "alice-note"
Document 11: owner bob,   body "bob-note"

User alice: ROLE_READER, ROLE_EDITOR
User bob:   ROLE_READER
User admin: ROLE_ADMIN
```

A user can pass the HTTP `authenticated()` rule yet still be blocked by `@PreAuthorize` when the ID does not belong to them. Admin may read/edit all under the **demo policy**, whereas multi-tenant production systems must never assume a superuser automatically reads every tenant.

The project uses an in-memory repository for reproducibility; **do not use it as a production storage/transaction design**. Passwords in source are dummy fixtures, never for real use.

### 8.1. Directory Structure

```text
method-spel-demo/
├── pom.xml
└── src/
    ├── main/java/example/methodspel/
    │   ├── MethodSpelApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentRepository.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   ├── ProfileService.java
    │   └── ApiController.java
    └── test/java/example/methodspel/
        └── MethodSpelTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-spel-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`<parameters>true</parameters>` helps SpEL resolve `#documentId`/`#username` accurately from method declarations. The Spring Boot parent manages security dependency versions; do not manually add mismatched versions of `spring-security-core`.

### 8.3. Main Class

File `src/main/java/example/methodspel/MethodSpelApplication.java`:

```java
package example.methodspel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSpelApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSpelApplication.class, args);
    }
}
```

### 8.4. SecurityConfig: @EnableMethodSecurity Required

File `src/main/java/example/methodspel/SecurityConfig.java`:

```java
package example.methodspel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("READER", "EDITOR")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("READER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

HTTP security here only decides public vs authenticated. **It does not allow Bob to view all docs automatically:** DocumentService's policy decides owner/role. HTTP Basic is used so 401/403 are clearly visible in MockMvc, not as a recommendation to send passwords over unencrypted HTTP. Spring Boot may create or use an HttpSession depending on security context/session policy; the example does not claim to be stateless.

CSRF **is not disabled**. PUT tests require `with(csrf())` to distinguish CSRF errors from method permissions.

### 8.5. DocumentRepository and Data Record

File `src/main/java/example/methodspel/DocumentRepository.java`:

```java
package example.methodspel;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {
    private final Map<Long, Document> documents =
        new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(10L, new Document(10L, "alice", "alice-note"));
        documents.put(11L, new Document(11L, "bob", "bob-note"));
    }

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document replaceBody(long id, String newBody) {
        return documents.computeIfPresent(id,
            (key, old) -> new Document(old.id(), old.owner(), newBody));
    }
}

// Java 17 record, used only within package example.methodspel.
record Document(long id, String owner, String body) {}
```

This is a data fixture for tests. Record `Document` is intentionally not `public`; controller/service/policy reside in the **same package**, so Java code can use it. Tests call `reset()` before each test so body updates do not affect other tests. There are no transactions, tenant IDs, persistence, or auditing in this demo repository.

### 8.6. DocumentPolicy: Fetching Owner from Repository, Not from Client

File `src/main/java/example/methodspel/DocumentPolicy.java`:

```java
package example.methodspel;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository documents;

    public DocumentPolicy(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (!isRealUser(authentication)) {
            return false;
        }

        return documents.findById(documentId)
            .map(document -> isAdmin(authentication)
                || document.owner().equals(authentication.getName()))
            .orElse(false);
    }

    public boolean canEdit(Authentication authentication, long documentId) {
        // Role gate lives in @PreAuthorize on the service.
        // This policy only verifies resource ownership/admin.
        return canRead(authentication, documentId);
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean isAdmin(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    }
}
```

Key points:

- Bean name `documentPolicy` is explicitly declared with `@Component("documentPolicy")`, so SpEL references `@documentPolicy`.
- The bean receives `Authentication` from the method expression rather than accepting a client-passed username as the caller.
- The document's owner is retrieved **from the repository**. Alice cannot send `documentId=11` and claim `owner=alice` to get through.
- Non-existent document → `Optional.empty()` → policy returns false; this is **deny-by-default**. An app may choose to return 404 instead of 403 to prevent resource-existence leakage, yet that must be designed consistently rather than inferring 403 means a document definitely exists.
- Technical `isAuthenticated()` is insufficient when an anonymous token is present; the policy guards against `AnonymousAuthenticationToken`. HTTP/method expressions also perform their own checks.
- `canEdit` does not check role EDITOR on its own; the role requirement is expressed on the service method. Thus **if another service later calls canEdit without a role gate, the policy will not block a user holding only READER**. Production can bundle role + ownership + tenant together in one policy method to avoid omissions; this example separates them to show SpEL composition.

In real business logic, policies must handle immutable user IDs, tenant IDs, account status, updated roles, ownership, ACLs, document visibility, and transactions. Never treat a Java boolean returning true as a guarantee against races/concurrent updates if data can change while the method runs.

### 8.7. DocumentService: Method Authorization on a Spring-Managed Service

File `src/main/java/example/methodspel/DocumentService.java`:

```java
package example.methodspel;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("isAuthenticated() and @documentPolicy.canRead(authentication, #documentId)")
    public Document read(long documentId) {
        return documents.findById(documentId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN') and @documentPolicy.canEdit(authentication, #documentId)")
    public Document update(long documentId, String body) {
        Document updated = documents.replaceBody(documentId, body);
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return updated;
    }
}
```

Pay attention to both **expressions** and **method arguments**:

- `#documentId` must be discovered properly via `-parameters`. The first parameter `documentId` is not a principal; it is only a resource ID.
- `authentication` comes from the security context. The policy looks up the owner in the repository, never from the body.
- `isAuthenticated() and ...` uses short-circuiting, avoiding calling the policy for anonymous callers in the read expression.
- `hasAnyRole('EDITOR','ADMIN') and ...` blocks Bob (only READER) before reaching the edit policy. Alice has EDITOR yet still cannot edit Bob's document 11. Admin bypasses ownership **only under this demo policy**.
- The policy runs before the method. If denied, `documents.replaceBody` **does not run**, so there are no side effects from the business method.
- An unexpected repository error inside the policy may raise a different exception than AccessDenied; never blindly mask DB timeouts as "wrong password" or "access denied".

In production, if updates must be safe against concurrent changes, use transactions and enforce owner/tenant conditions in the update statement or use appropriate locking; demo tests do not replace those guarantees.

### 8.8. ProfileService: Using principal Directly

File `src/main/java/example/methodspel/ProfileService.java`:

```java
package example.methodspel;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    @PreAuthorize("principal.username == #username or hasRole('ADMIN')")
    public String viewProfile(String username) {
        return "PROFILE:" + username;
    }
}
```

In the demo, Basic authentication uses `InMemoryUserDetailsManager` and the principal is a `UserDetails` with `getUsername()`. Bob cannot view `/profiles/alice`; Admin is permitted. If the app switches to another principal type, update the expression or standardize the principal rather than blindly assuming `principal.username` exists.

An expression less coupled to the principal class is `authentication.name == #username`, provided `getName()` truly represents the corresponding username. For multi-tenancy or renameable accounts, prefer immutable IDs.

### 8.9. ApiController: Only Calls Injected Service Beans

File `src/main/java/example/methodspel/ApiController.java`:

```java
package example.methodspel;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    private final DocumentService documents;
    private final ProfileService profiles;

    public ApiController(DocumentService documents,
                         ProfileService profiles) {
        this.documents = documents;
        this.profiles = profiles;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/docs/{documentId}")
    public String read(@PathVariable long documentId) {
        Document d = documents.read(documentId);
        return "DOC:" + d.id() + ":" + d.body();
    }

    @PutMapping("/docs/{documentId}")
    public String update(@PathVariable long documentId,
                         @RequestBody String body) {
        Document d = documents.update(documentId, body);
        return "UPDATED:" + d.id() + ":" + d.body();
    }

    @GetMapping("/profiles/{username}")
    public String viewProfile(@PathVariable String username) {
        return profiles.viewProfile(username);
    }
}
```

The controller does not check ownership via query parameters and does not mark Authentication valid itself. **The Spring-injected service bean** is the boundary where Spring AOP applies `@PreAuthorize`. If a controller calls the repository directly, the policy is bypassed — so test the real call path.

### 8.10. MockMvc + Method-Security Integration Tests

File `src/test/java/example/methodspel/MethodSpelTest.java`:

```java
package example.methodspel;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSpelTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentRepository repository;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        repository.reset();
    }

    @Test
    void publicEndpointDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousCannotReadProtectedDocument() throws Exception {
        mvc.perform(get("/docs/10"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnDocumentButNotBobsDocument() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("DOC:10:alice-note"));

        mvc.perform(get("/docs/11")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocumentButNotAlicesDocument() throws Exception {
        mvc.perform(get("/docs/11")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("DOC:11:bob-note"));

        mvc.perform(get("/docs/10")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadBothDocuments() throws Exception {
        mvc.perform(get("/docs/10")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/docs/11")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void aliceEditorCanUpdateOwnDocumentWithCsrf() throws Exception {
        mvc.perform(put("/docs/10")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("revised"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:10:revised"));
    }

    @Test
    void aliceEditorCannotUpdateSomeoneElsesDocument() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("stolen"))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobReaderCannotUpdateEvenHisOwnDocument() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("new"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminMayUpdateDocumentsUnderDemoPolicy() throws Exception {
        mvc.perform(put("/docs/11")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("approved"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:11:approved"));
    }

    @Test
    void validUserWithoutCsrfCannotPut() throws Exception {
        mvc.perform(put("/docs/10")
                .with(httpBasic("alice", "alice-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("changed"))
            .andExpect(status().isForbidden());
    }

    @Test
    void profileExpressionUsesPrincipalAndArgument() throws Exception {
        mvc.perform(get("/profiles/alice")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("PROFILE:alice"));

        mvc.perform(get("/profiles/alice")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/profiles/alice")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void missingDocumentFailsClosedInPolicy() throws Exception {
        mvc.perform(get("/docs/999")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER"})
    void directBeanCallIsProtectedWithoutMvc() {
        assertThatThrownBy(() -> service.read(10L))
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

**14 test cases** prove:

- Missing/invalid HTTP Basic credentials → 401.
- Alice/Bob can read their own docs yet get 403 when changing the ID to the other user's doc.
- Admin can read both under the demo policy.
- Updating requires **all of** role EDITOR/ADMIN, ownership policy, **and CSRF**: Alice can edit her own doc, cannot edit Bob's; Bob lacks EDITOR so cannot edit even his own doc; Admin edits per the demo policy.
- Alice's PUT without CSRF returns 403 from the CSRF filter; **do not** use that case as proof that the method policy denied it.
- `principal.username == #username` lets Alice and Admin through while blocking Bob.
- Non-existent docs are denied by the policy before the method accesses the repository; the demo returns 403 without revealing whether the ID exists.
- Directly calling the **Spring-injected** service with `@WithMockUser` still goes through the interceptor. This tests something distinct from HTTP authorization, catching if method security was left disabled.

The tests are designed to run on Spring Boot 3.3.5 and Java 17. **This article does not claim they were executed in a live environment.** Because the in-memory repository is reset in `@BeforeEach`, JUnit tests do not run in parallel by default; if a project enables parallel tests or receives external traffic, resetting global shared state requires different isolation.

### 8.11. Run Commands and Observed Results

In the `method-spel-demo` directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Maven test reports are expected to record **14 tests** with no failures/errors once dependencies resolve and the code matches the structure above. This is a testing target, not observed stdout.

If the dev app runs on localhost:8080:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/docs/10
curl -i -u alice:alice-pass http://localhost:8080/docs/10
curl -i -u bob:bob-pass http://localhost:8080/docs/10
curl -i -u admin:admin-pass http://localhost:8080/docs/11
```

Expected statuses/bodies:

```text
/public (anonymous)           -> 200 PUBLIC_OK
/docs/10 (anonymous)          -> 401
/docs/10 (alice)              -> 200 DOC:10:alice-note
/docs/10 (bob)                -> 403
/docs/11 (admin)              -> 200 DOC:11:bob-note
```

Do not use a 403 response from a CSRF-less curl PUT to conclude the user lacks a role. To test updates, use configured MockMvc `with(csrf())` or build a client that acquires/sends CSRF tokens per the real application. Never deploy fixture accounts/passwords to production and never put real credentials on command lines or in logs.

## 9. Distinguishing authentication, principal, and method arguments via Bug Examples

### 9.1. Confusing principal with a userId Parameter

Wrong:

```java
@PreAuthorize("#userId != null")
public Secret getSecret(String userId) { ... }
```

The client can always send a non-null ID. No identity/ownership check is performed at all. Take the principal/user ID from Authentication and verify resource ownership from a trusted source.

### 9.2. Trusting a Username Self-Declared in the Request Body

Wrong:

```java
@PreAuthorize("authentication.name == #claimedOwner")
public void delete(long documentId, String claimedOwner) { ... }
```

An attacker can supply their own name as `claimedOwner` even when `documentId` belongs to someone else. You need `@policy.canDelete(authentication, #documentId)` with the policy looking up the real record.

### 9.3. Calling an Annotated Method Within the Same Class

Wrong in standard proxy architecture:

```java
@Service
class DocumentFacade {
    public void flow(long id) {
        this.deleteProtected(id); // self-invocation may bypass the proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteProtected(long id) {
        // Business mutation.
    }
}
```

You can fix this by placing the protected method in another injected Spring bean, or enforcing the policy directly at the entry method; do not reach for `self-injection` tricks unless you understand bean lifecycles, circular dependencies, and testing. AOP/proxy behavior must be verified in your configured version.

### 9.4. @PostAuthorize Protecting an Already-Executed Operation

Wrong:

```java
@PostAuthorize("hasRole('ADMIN')")
public void transferMoney() {
    bank.transfer(...); // already ran before post-authorization checked
}
```

Post-authorization happens **after the method**, so it cannot stop earlier side effects. Use `@PreAuthorize` and authorization inside the transaction/business layer for sensitive actions.

### 9.5. Principal Class Changes After Migration

`principal.username` may work for `UserDetails` yet fail for a JWT principal, a custom `String` principal, or another adapter. SpEL failing to find a property can throw an evaluation exception rather than neatly returning false. Standardize principals or use `authentication.name` with a consistent identity contract and test with real login mechanisms.

### 9.6. Confusing Role and Authority Prefixes

`hasRole('ADMIN')` checks authority `ROLE_ADMIN` by default, while `hasAuthority('ADMIN')` checks literal `ADMIN`. If JWT authority mapping produces `SCOPE_documents.read`, use the exact authority or an appropriate converter; never randomly switch `hasRole` upon seeing a 403.

### 9.7. Protecting Only the Controller While the Service Has Other Callers

If annotations exist only on controllers while the service is called by message listeners, batch jobs, or other endpoints, new entry paths may skip the controller. Enforce protection at the service/resource boundary and grant special privileges to internal callers only through audited designs.

### 9.8. Incorrect Policy Caching Causing Stale Permissions

Roles/permissions or ownership in the DB can change after a user logs in; `authentication.authorities` in a session SecurityContext may hold a stale snapshot. When policies need real-time revocation, implement session revocation/revalidation, security versions, or live lookups. Caching `canRead` results by `documentId` **without including user/tenant/permissions version** can grant another user's permissions.

## 10. Designing Policies for Multi-Tenancy and Record-Level Access

In multi-organization applications, a rule like:

```java
@PreAuthorize("hasAuthority('document:read')")
public Document read(long documentId) { ... }
```

only proves the caller has permission for the **operation type**, not that the document belongs to the right **tenant**. Policies should verify:

1. Authentication reflects a verified current user ID.
2. Tenant ID is not trusted merely because it sits in the request path/body; verify user-to-tenant membership from a trusted source.
3. Document ID exists and the document belongs to the matching tenant.
4. Role/permission for the action plus document state conditions (locked, processing, owner).
5. If the action mutates data, conditions still hold at update/transaction time.
6. All denials are audited appropriately without disclosing another tenant's document.

Directional logic example, **not a standalone source file**:

```java
public boolean canEdit(Authentication auth, long documentId) {
    // 1. Verify auth and userId from a trusted principal.
    // 2. Fetch document with tenant scope from repository.
    // 3. Check role, owner, business state.
    // 4. Return false when user is unauthorized or resource mismatches.
    return permissionService.isAllowed(auth, documentId, "EDIT");
}
```

At implementation level, `permissionService` is an injected dependency, not a built-in variable. If this policy queries the DB frequently, use proper queries/indexes/transactions and properly keyed caches; **never** choose "load all documents then PostFilter" for large datasets.

## 11. Testing and Observing Method Security in Production

Your test suite should cover:

- **Authentication boundary:** unauthenticated requests, bad credentials, anonymous/remember-me, expired sessions.
- **Argument binding:** `#documentId` has the real value; reordering or renaming method arguments must cause tests to catch breakage.
- **Object ownership:** Alice cannot read/edit Bob's doc even though Alice has role EDITOR.
- **Role + policy:** right role with wrong owner is denied; right owner lacking role is also denied.
- **Bean resolution:** `@documentPolicy` is Spring-managed and returns false when the resource is missing.
- **Proxy boundary:** calling the injected bean directly still denies when permissions are missing; also test non-controller entry paths.
- **Return value policy:** if using `@PostAuthorize`, ensure read methods have no side effects executed prior to denial.
- **Concurrency:** permissions/owner/tenant change mid-update; verify transaction policies.
- **Async:** `SecurityContextHolder` is typically thread-bound; async execution needs explicit propagation rather than assuming context carries over to worker threads.
- **Observability:** log request ID, sufficient principal identifier, scoped resource ID, policy name, and outcome; never log raw passwords, JWTs, cookies, or sensitive attributes.

**To debug a 403 response**, first distinguish whether it came from HTTP AuthorizationFilter, CSRF, or method security. In development environments you can enable appropriate Spring Security logs and test methods via bean injection. Never blindly set `permitAll` or disable CSRF to hide errors.

## 12. Summary Checklist

- [ ] `@EnableMethodSecurity` is enabled and annotations are verified to be intercepted.
- [ ] Understand `authentication` is Authentication, `principal` is the inner token/user object, `#argument` is a method parameter, and `@bean` is a Spring bean.
- [ ] Never assume every principal has `username`; establish an appropriate principal type contract.
- [ ] Enable `-parameters` or specify parameter names explicitly; test SpEL argument binding.
- [ ] Rules comparing the user only against client-supplied input **do not replace** repository ownership checks.
- [ ] Use `@PreAuthorize` before methods with side effects; never rely on `@PostAuthorize` for mutations.
- [ ] Policy beans handle nulls, missing resources, roles, tenants, and trusted data sources.
- [ ] Enforce transactions/revalidation at sensitive action points to reduce TOCTOU.
- [ ] Never call protected methods via `this.method()` when relying on proxy-based interception.
- [ ] HTTP authorization, CSRF, method security, and object-level authorization are tested distinctly.
- [ ] Include direct tests on injected beans, spoofed username/owner tests, and missing-role-despite-ownership tests.
- [ ] Never cache permissions without user/tenant/version in keys; never log raw credentials.

### Self-Check Questions

**1.** In `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")`, how do `@` and `#` differ?  
**Answer:** `@documentPolicy` accesses a Spring bean; `#documentId` accesses a method argument. `authentication` is a built-in property of the method-security expression context.

**2.** Does `principal.username` always work with JWT/OIDC?  
**Answer:** No. Principal class depends on the authentication mechanism. Standardize the principal or use Authentication APIs under an agreed identity contract.

**3.** Why can `authentication.name == #ownerName` fail to stop unauthorized document reads?  
**Answer:** `#ownerName` can be supplied by an attacker; you must check the true owner in the DB based on `documentId`.

**4.** A user has `ROLE_EDITOR` yet is not the owner; with an expression combining the role and `@policy.canEdit`, what should happen?  
**Answer:** It is denied; both the role condition and the resource-level permission must pass.

**5.** If `@EnableMethodSecurity` is omitted while `anyRequest().authenticated()` remains, what is the risk?  
**Answer:** Endpoints still require login, yet ownership checks at methods stop running, leading to IDOR/BOLA.

**6.** Why is `@PostAuthorize` insufficient to protect money transfers?  
**Answer:** It runs after the method executes; side effects have already occurred.

**7.** Why might calling `this.read(10)` inside the same service fail to check annotations?  
**Answer:** Internal calls can bypass the Spring AOP proxy. Restructure boundaries or enforce policies at the true entry point.

**8.** Why does a `403` test for a PUT missing CSRF not prove the method policy works?  
**Answer:** `CsrfFilter` can block before reaching the controller/service. Testing method permissions requires valid CSRF along with the right credentials/roles.

**Conclusion:** SpEL in Spring Security method security connects **identity from `authentication/principal`**, **method arguments**, and **policy beans querying trusted data**. This combination enables per-resource access control, yet it is only safe when method interceptors are enabled, parameter names resolve properly, client-supplied owners are never trusted, and policies are verified at service/transaction boundaries.