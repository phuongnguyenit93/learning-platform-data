# @PostAuthorize and Checking Objects After Method Return

> **Scope:** Spring Security 6 on the Servlet stack, Java 17+, and Spring MVC. The main topic is `@PostAuthorize`: checking permissions **after a method returns** via `returnObject` in Spring Expression Language (SpEL). This lesson distinguishes `@PreAuthorize`, `@PostAuthorize`, and `@PostFilter`, explains how to verify document ownership, covers the limitations of blocking after a method executes, and provides a runnable Spring Boot 3.3.5 example with `MockMvc`.

## 1. Why Authorize After Loading an Object?

Suppose a system stores documents:

- Alice may read documents **owned by Alice**.
- Bob may read documents **owned by Bob**.
- Auditor has audit permission and may read both Alice's and Bob's documents.
- Guest has no permission to read documents.
- A logged-in user who is not the owner must be denied even with a valid password.

Example records:

| ID | ownerUsername | Title |
| --- | --- | --- |
| 42 | `alice` | Alice private report |
| 43 | `bob` | Bob private note |

The request `GET /documents/42` only carries ID 42. You cannot tell ownership from the URL alone; you must **load the document from a trusted server source**, inspect its actual owner attribute, and compare it with the user's identity. If the client sends `X-Owner: alice` and the application trusts it immediately, that is not a security mechanism.

With `@PostAuthorize`, Spring Security can inspect the **object the service just returned** before passing it back to the controller:

```text
GET /documents/42 + Basic credentials
        |
        v
Authentication filter verifies username/password
        |
        v
AuthorizationFilter checks HTTP policy
        |
        v
Controller calls Spring-managed DocumentService bean
        |
        +--> @PreAuthorize: checks operation-type permission
        |
        v
DocumentService.findDocument(42)
  - retrieves document from server source
  - returns DocumentView(id=42, ownerUsername=alice, ...)
        |
        v
@PostAuthorize inspects returnObject
        |
        +-- Owner alice or has DOCUMENT_AUDIT -> GRANT
        |                                  |
        |                                  v
        |                             Controller receives DTO -> HTTP 200
        |
        +-- Bob, not owner, no audit -> DENY
                                           |
                                           v
                                       typically HTTP 403
```

**Timing is the key point:** `@PostAuthorize` runs **after the method body has executed**. It protects **returning the result to the caller**, and does not automatically prevent side effects already performed in the method body.

## 2. What Is @PostAuthorize?

`@PostAuthorize` is a Spring Security method-authorization annotation. It uses a SpEL expression to decide whether a method invocation **is allowed to return the result it just produced**.

Minimal example:

```java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView findDocument(long id) {
    return documentRepository.findById(id);
}
```

This is an **explanatory fragment**; it is not a standalone Java program because `DocumentView` and `documentRepository` still need to be defined. The full runnable example is in section 9.

In the expression above:

- `returnObject` is the actual return value the method just produced.
- `returnObject.ownerUsername` is a property on the object, typically read by SpEL through the `getOwnerUsername()` getter.
- `authentication` is the current `Authentication` from the Spring Security context.
- `authentication.name` is typically the result of `Authentication.getName()`, i.e., the user's identifier.
- `==` is comparison in SpEL, not password verification or token signature verification.

If the document belongs to the current user, the result is allowed to reach the caller. Otherwise, Spring Security triggers access-denied behavior. For a user authenticated via HTTP Basic, the HTTP result is typically **403 Forbidden**.

### Related APIs and Classes

| Component | Role |
| --- | --- |
| `@EnableMethodSecurity` | Enables method-security infrastructure on Spring-managed beans |
| `@PostAuthorize` | Defines the authorization expression **after** the method |
| `@PreAuthorize` | Defines the authorization expression **before** the method |
| `AuthorizationManagerAfterMethodInterceptor` | A Spring Security 6 method-security component that evaluates post-invocation checks |
| `PostAuthorizeAuthorizationManager` | Authorization logic corresponding to the PostAuthorize expression |
| `SecurityContextHolder` | Holds the context and `Authentication` for current processing |
| `AccessDeniedException` | Exception family for denied access handled by security/exception handling |
| `ExceptionTranslationFilter` | In the HTTP Servlet flow, converts access-denied/unauthenticated errors into entry point or access-denied responses |
| `AuthorizationFilter` | Enforces HTTP path policies, **separate** from method-security interceptors |

`@PostAuthorize` **is not a Servlet filter**. It applies at method invocations via Spring AOP/advisors, protecting logic reused across different controllers.

## 3. Differences Between @PreAuthorize, @PostAuthorize, and @PostFilter

| Annotation | Timing | Available Data | Core Meaning |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before method body runs | Principal, authorities, method arguments | Allowed to **call** the method? |
| `@PostAuthorize` | After method body returns successfully | All of the above **and returnObject** | Allowed to **receive the result**? |
| `@PostFilter` | After method returns a supported collection/type | `filterObject` per element | Keep/drop elements per rule |
| `@PreFilter` | Before method, with suitable input collection | `filterObject` from argument | Filter input before body runs |

Example with two complementary constraints:

```java
@PreAuthorize("hasAnyAuthority('DOCUMENT_READ','DOCUMENT_AUDIT')")
@PostAuthorize("hasAuthority('DOCUMENT_AUDIT') or " +
               "returnObject.ownerUsername == authentication.name")
public DocumentView findDocument(long id) {
    // Retrieve document from server-side store.
}
```

Here **@PreAuthorize** blocks users lacking read permission before querying. **@PostAuthorize** inspects the specific document just loaded. Both conditions must be satisfied; the auditor has an intentionally granted exception branch.

Steps for Bob:

```text
Bob is logged in, has DOCUMENT_READ
   -> HTTP authenticated(): grant
   -> PreAuthorize has DOCUMENT_READ: grant
   -> method loads document 42: ownerUsername=alice
   -> PostAuthorize: lacks DOCUMENT_AUDIT and bob != alice
   -> deny, controller does not receive document, HTTP typically 403
```

Bob's password is correct so he **does not get 401** for bad credentials; this is an **authorization failure**, not an authentication failure.

### Do Not Confuse PostAuthorize with List Filtering

A method returning `List<DocumentView>` is not automatically filtered item-by-item by `@PostAuthorize`. That annotation decides on the **entire return object**, whereas `@PostFilter` can filter elements of supported collection types:

```java
// Illustrative fragment: not an optimal design when data is large.
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<DocumentView> findAllDocuments() {
    return repository.findAll();
}
```

Drawback: the service **already loaded all documents** before filtering. This can leak via logs, waste memory, distort pagination/total counts, or cross tenant boundaries in other branches. In real applications, **prefer queries conditioned on verified owner/tenant directly in the database**, then use method security as an additional safeguard.

## 4. Writing Expressions with returnObject

Examples of expressions depending on the return value:

| SpEL Expression | Meaning |
| --- | --- |
| `returnObject.ownerUsername == authentication.name` | Current user is the owner of the result |
| `hasAuthority('DOCUMENT_AUDIT') or returnObject.ownerUsername == authentication.name` | Auditor **or** owner may receive the object |
| `returnObject.tenantId == principal.tenantId` | Result shares the tenant attached to a trusted principal |
| `returnObject != null and returnObject.ownerUsername == authentication.name` | Allow only non-null objects belonging to the user |
| `returnObject.isPublic() or hasRole('ADMIN')` | Public object or user has admin role, if class/role mapping actually supports it |

Important notes:

1. **Property names must actually exist.** If the DTO has `getOwnerUsername()`, use `ownerUsername`; do not write `returnObject.owner` if the class has no owner property.
2. **Never trust client data** to determine owner/tenant. Results must come from a server-side repository or trusted authoritative source.
3. **Multi-tenant accounts:** comparing username alone may be insufficient if the same username appears across organizations. In that case use a stable user ID, tenant ID, membership, and trusted service policy.
4. **Null:** if the method returns null and the expression dereferences a property, an expression error can occur. Define a clear not-found contract.
5. **Optional:** if the method returns `Optional<DocumentView>`, `returnObject` represents the wrapper, not `DocumentView` automatically. Handle Optional in the expression/policy bean or change the API to return the DTO and throw 404.
6. **Collections:** PostAuthorize decides on the entire result; it does not implicitly iterate items.
7. **Getter side effects:** avoid getters that call remote services or mutate state; SpEL may invoke getters during evaluation.

### Explicit JavaBean DTO

```java
public final class DocumentView {
    private final long id;
    private final String ownerUsername;

    public DocumentView(long id, String ownerUsername) {
        this.id = id;
        this.ownerUsername = ownerUsername;
    }

    public long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }
}
```

This is a syntactically standalone DTO fragment without package/build files. JavaBean getters make property access in SpEL and JSON serializers straightforward. The runnable project below includes a DTO class that also carries `title`.

### Handle Non-Existent Documents with an Explicit Error

```java
DocumentView result = repository.findById(id);
if (result == null) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found");
}
return result;
```

This fragment shows the service **throwing 404 instead of returning null**. When a method throws an exception rather than returning a value normally, `@PostAuthorize` has no successful return value to evaluate. This avoids SpEL errors on null and keeps the API contract clear, though returning 403 vs 404 still warrants evaluation regarding resource-existence disclosure.

## 5. Security Processing Flow: From URL to Method

For a Spring MVC request:

```text
HTTP GET /documents/42
         |
         v
Servlet FilterChainProxy -> SecurityFilterChain
         |
         v
BasicAuthenticationFilter
  - reads Basic header
  - AuthenticationManager/Provider verifies password
  - stores Authentication in SecurityContext
         |
         v
AuthorizationFilter
  - /documents/{id} requires authenticated()
         |
         v
DispatcherServlet -> DocumentController
         |
         v
DocumentService Proxy
         |
         +--> PreAuthorizeAuthorizationManager
         |      - Checks DOCUMENT_READ or DOCUMENT_AUDIT
         |      - Deny => method does not run
         |
         v
Target method findDocument(42)
  - reads Map/DB
  - builds DocumentView
  - returns object
         |
         +--> PostAuthorizeAuthorizationManager / after interceptor
         |      - compares returnObject.ownerUsername with Authentication
         |      - Grant or Deny
         |
         v
Caller receives DTO or exception
         |
         v
HTTP 200, 403, or specific errors like 404
```

If the request lacks Basic credentials, the HTTP `authenticated()` rule blocks early; the Basic entry point typically returns **401 Unauthorized** with `WWW-Authenticate`. If credentials are valid yet the method policy denies, HTTP typically returns **403 Forbidden**. Specific statuses still depend on authentication entry points, exception handlers, and filter chain configuration.

**Having a SecurityContext for the current request does not imply a long-lived login session.** In the demo, `SessionCreationPolicy.STATELESS` does not retrieve authentication from an HTTP session; yet method security still works because the Basic filter authenticates the **current request**.

## 6. Why Is PostAuthorize Not a Safe Solution for Write Operations?

This is the most critical mistake to avoid. With `@PostAuthorize`, **the method body has already executed** before permissions are checked. If the body modifies a database, sends an email, publishes a Kafka event, or calls a payment system, a 403 response **does not guarantee** the changes were rolled back.

### Counter-Example

```java
// ANTI-PATTERN: do not put in production.
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView deleteDocument(long id) {
    DocumentView result = repository.deleteAndReturn(id);
    emailService.sendDeletionNotice(result);
    return result;
}
```

Suppose Bob invokes deletion on Alice's document:

1. The method deletes the document.
2. The method sends a notification email.
3. The method returns the deleted object.
4. `@PostAuthorize` sees the owner is not Bob and denies access.
5. The response may be 403, **yet the document/email has already been affected**.

Some transactions might roll back under specific configurations/orderings, but you cannot rely on that as a default security mechanism: transaction advice has ordering, external side effects do not participate in rollback, and committed changes do not reverse themselves.

### Better Design

```text
POST/DELETE request
   |
   v
@PreAuthorize checks operation permission
   |
   v
Service + transaction:
   - Load real resource with tenant/owner/scope from server
   - Re-verify permission and domain state before mutating
   - Use lock / optimistic locking / conditional update as needed
   - Perform changes within transaction
   - Emit audit/outbox event per policy
   |
   v
Return result
```

For sensitive operations like order approvals, money transfers, or record deletions, **prefer checking permissions before the action**, combined with domain-level checks inside the transaction to avoid **TOCTOU (time of check/time of use)** bugs. Never use PostAuthorize as the sole barrier.

## 7. @EnableMethodSecurity, Proxies, and Self-Invocation

Spring Security 6 typically enables method authorization via:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // SecurityFilterChain, UserDetailsService, ...
}
```

Or explicitly:

```java
@EnableMethodSecurity(prePostEnabled = true)
```

Imports:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

`@EnableWebSecurity` and HTTP `SecurityFilterChain` do not automatically replace `@EnableMethodSecurity`. If method security is not enabled, annotations can sit in code with no interceptor running.

### Calling Through a Spring-Managed Bean

Method security relies on Spring proxies/advisors in common setups:

- The service must be a Spring-managed bean (e.g., `@Service`).
- The controller receives the service via constructor injection.
- Calls must go through the Spring-provided bean/proxy.
- Do not manually `new DocumentService()` and expect annotations to work.
- Be cautious with private/final methods, proxy configuration, and non-intercepted classes/methods.
- Do not assume calling a method from the same class goes through the proxy.

Self-invocation anti-pattern:

```java
@Service
public class DocumentService {
    public DocumentView outer(long id) {
        return this.findDocument(id);
    }

    @PostAuthorize("returnObject.ownerUsername == authentication.name")
    public DocumentView findDocument(long id) {
        return repository.load(id);
    }
}
```

This is an **anti-pattern fragment**, needing repository/DTO to compile. Calling `this.findDocument(id)` on the same object can bypass the AOP proxy in standard proxy mode; `@PostAuthorize` does not run. Have another Spring bean call the injected DocumentService, or use a design with trusted security checks.

**Real testing is vital:** a test where "Alice gets 200" is not enough, because a service without method security also gives Alice 200. A test where "Bob gets 403 reading Alice's document" is what catches missing proxies/annotations.

## 8. Ownership Policy: Roles/Permissions and Audit Exception

With Alice's document 42 and Bob's document 43:

```text
User alice:
  authorities = [DOCUMENT_READ]

User bob:
  authorities = [DOCUMENT_READ]

User auditor:
  authorities = [DOCUMENT_AUDIT]

User guest:
  authorities = [ROLE_GUEST]
```

Policy:

```text
PRE:
    user has DOCUMENT_READ OR DOCUMENT_AUDIT

POST:
    user has DOCUMENT_AUDIT
    OR document.ownerUsername == authentication.name

FINAL:
    PRE AND POST
```

Expected outcomes:

| Caller / Document | Pre Check | Post Check | Outcome |
| --- | --- | --- | --- |
| Alice /42 | Grant: READ | Grant: owner Alice | 200 |
| Alice /43 | Grant: READ | Deny: owner Bob | 403 |
| Bob /42 | Grant: READ | Deny: owner Alice | 403 |
| Bob /43 | Grant: READ | Grant: owner Bob | 200 |
| Auditor /42 | Grant: AUDIT | Grant: AUDIT | 200 |
| Guest /42 | Deny: no permission | Method does not run | 403 |
| Anonymous /42 | HTTP deny | Method does not run | 401 with Basic |
| Alice /999 | Grant | Method throws 404 | 404 |

Important detail: role `ROLE_GUEST` is not automatically mapped to `DOCUMENT_READ`. Likewise, `ROLE_ADMIN` does not automatically gain wildcard permissions unless the application explicitly defines/maps them. Never use client-supplied roles or an `X-Admin: true` header to grant permissions.

### If ownerUsername Is Not Unique Across Tenants

In multi-tenant systems, two users with the same username can exist in different tenants. Comparing a username string **is not enough** to isolate data. Use a verified user ID, trusted tenant ID, resource scope, membership, and security policies in service/DB. A rule like `ownerUsername == authentication.name` is only appropriate when the identity namespace and ownership model truly match that assumption.

## 9. Runnable Project: Spring Boot 3.3.5, Java 17, and MockMvc

The example below uses Spring MVC Servlet, HTTP Basic, method security, and an immutable Map containing two documents. Because the goal is authorization after **reading**, there are no mutations or side effects.

### 9.1. Directory Structure

```text
post-authorize-demo/
├── pom.xml
├── src/main/java/example/postauthorize/
│   ├── PostAuthorizeApplication.java
│   ├── SecurityConfig.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/example/postauthorize/
    └── DocumentAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>post-authorize-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. PostAuthorizeApplication.java

```java
package example.postauthorize;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.postauthorize;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password(hash)
                .authorities("DOCUMENT_READ").build(),
            User.withUsername("bob").password(hash)
                .authorities("DOCUMENT_READ").build(),
            User.withUsername("auditor").password(hash)
                .authorities("DOCUMENT_AUDIT").build(),
            User.withUsername("guest").password(hash)
                .authorities("ROLE_GUEST").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/documents/{id}")
                    .authenticated()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // Basic only; do not redirect to form login in the demo.
        http.formLogin(form -> form.disable());

        // Keep default CSRF: demo endpoints only use GET.
        return http.build();
    }
}
```

Notes:

1. `@EnableMethodSecurity` enables @PreAuthorize and @PostAuthorize on Spring service beans.
2. The HTTP `authenticated()` rule only proves valid identity; **it does not determine the owner**.
3. `httpBasic` lets you test each request with username/password. HTTP Basic **is unsafe over unencrypted networks**; `localhost` here is only a lab, while production uses HTTPS.
4. `STATELESS` does not pull `SecurityContext` from an HTTP session, yet authentication still exists for the current request and is used by method security.
5. `NullRequestCache` avoids saving URLs needing login for a browser form-login flow; this project has no form login.
6. CSRF remains at its default, and the demo only has GET. If you add POST/DELETE, apply CSRF according to how clients send credentials; never disable it indiscriminately.
7. Shared-hash/in-memory `UserDetailsService` is only for teaching; production needs durable and secure account, permission, and password-hash stores.

### 9.5. DocumentService.java

```java
package example.postauthorize;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final Map<Long, DocumentView> documents = Map.of(
            42L, new DocumentView(42L, "alice", "Alice private report"),
            43L, new DocumentView(43L, "bob", "Bob private note")
    );

    @PreAuthorize("hasAnyAuthority('DOCUMENT_READ', 'DOCUMENT_AUDIT')")
    @PostAuthorize("hasAuthority('DOCUMENT_AUDIT') or " +
                   "returnObject.ownerUsername == authentication.name")
    public DocumentView findDocument(long id) {
        DocumentView result = documents.get(id);
        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
        return result;
    }

    // Immutable DTO with JavaBean getters so SpEL and Jackson can read properties.
    public static final class DocumentView {
        private final long id;
        private final String ownerUsername;
        private final String title;

        public DocumentView(long id, String ownerUsername, String title) {
            this.id = id;
            this.ownerUsername = ownerUsername;
            this.title = title;
        }

        public long getId() {
            return id;
        }

        public String getOwnerUsername() {
            return ownerUsername;
        }

        public String getTitle() {
            return title;
        }
    }
}
```

For Alice calling ID 42, both pre and post grant. For Bob calling ID 42, pre grants yet post denies because the object's owner is Alice. For guest, pre denies and the method **does not run**. Auditor can read thanks to `DOCUMENT_AUDIT` in both pre and post. Calling ID 999 throws 404 rather than returning null.

**Read-only side effects only:** `Map.of` holds immutable records, keeping focus on PostAuthorize semantics. In production, `DocumentService` typically queries a database/repository with explicit tenant/owner scoping and clear transaction/lazy-loading handling.

### 9.6. DocumentController.java

```java
package example.postauthorize;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/documents/{id}")
    public DocumentService.DocumentView getDocument(@PathVariable long id) {
        return documents.findDocument(id);
    }
}
```

The controller calls the service **through dependency injection**. When Spring creates the method-security proxy for the service, `documents.findDocument(id)` passes through the interceptors. If access is denied, the DTO **never reaches Jackson serialization**. Never manually `new DocumentService()` inside the controller.

### 9.7. DocumentAuthorizationTest.java

```java
package example.postauthorize;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public:ok"));
    }

    @Test
    void anonymousCannotReadDocument() throws Exception {
        mvc.perform(get("/documents/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerOwnDocument() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("alice"))
                .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void bobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("bob", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadAcrossOwners() throws Exception {
        mvc.perform(get("/documents/43")
                .with(httpBasic("auditor", "demo123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void guestIsDeniedByPreAuthorize() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("guest", "demo123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingIdReturnsNotFoundForReader() throws Exception {
        mvc.perform(get("/documents/999")
                .with(httpBasic("alice", "demo123")))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongPasswordGetsUnauthorized() throws Exception {
        mvc.perform(get("/documents/42")
                .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Because `httpBasic(...)` sends Basic headers to MockMvc, the tests exercise both authentication and the actual policies in the security chain/method proxy. This is not a performance benchmark. In particular, **the test where Bob gets 403** is a crucial regression test: if `@EnableMethodSecurity` is removed or calls bypass the proxy, this test catches that the policy is not enforced.

### 9.8. Running

Use JDK 17+ and Maven in the directory with `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` runs JUnit/MockMvc; `mvn spring-boot:run` starts the application. With default configuration, embedded Tomcat serves at `http://localhost:8080`. Only use HTTP Basic over plain HTTP on localhost for the lesson; real deployments must use **HTTPS**.

## 10. Checking HTTP with curl

### 10.1. Public 200

```bash
curl -s http://localhost:8080/public
```

Expected body:

```text
public:ok
```

### 10.2. Anonymous 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/documents/42
```

Output:

```text
401
```

The user did not send Basic credentials, so the HTTP layer blocks **before** invoking the method.

### 10.3. Alice Can Read Document 42: 200

```bash
curl -s -u alice:demo123 http://localhost:8080/documents/42
```

Expected JSON:

```json
{"id":42,"ownerUsername":"alice","title":"Alice private report"}
```

### 10.4. Bob Cannot Read Document 42: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:demo123 http://localhost:8080/documents/42
```

Output:

```text
403
```

Bob has `DOCUMENT_READ`, yet is not owner Alice; `@PostAuthorize` denies after the method loads the result. **403 does not mean Bob entered the wrong password**.

### 10.5. Auditor Can Read Document 42: 200

```bash
curl -s -u auditor:demo123 http://localhost:8080/documents/42
```

JSON:

```json
{"id":42,"ownerUsername":"alice","title":"Alice private report"}
```

Auditor passes the `DOCUMENT_AUDIT` branch of both @PreAuthorize and @PostAuthorize.

### 10.6. Guest Blocked Before Method: 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u guest:demo123 http://localhost:8080/documents/42
```

Output:

```text
403
```

Guest is authenticated, yet lacks both DOCUMENT_READ and DOCUMENT_AUDIT, so `@PreAuthorize` denies.

### 10.7. Non-Existent ID: 404

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:demo123 http://localhost:8080/documents/999
```

Output:

```text
404
```

This is the `ResponseStatusException(HttpStatus.NOT_FOUND)` branch from the service, not PostAuthorize on a null object.

### 10.8. Wrong Password: 401

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:incorrect http://localhost:8080/documents/42
```

Output:

```text
401
```

### Summary Expectation Table

| Request | HTTP Authentication | @PreAuthorize | @PostAuthorize | Result |
| --- | --- | --- | --- | --- |
| GET /public anonymous | Not required | Not applicable | Not applicable | 200 |
| GET /documents/42 anonymous | Missing | Does not run | Does not run | 401 |
| GET /documents/42 alice | Valid | Grant | Owner grant | 200 |
| GET /documents/42 bob | Valid | Grant | Owner deny | 403 |
| GET /documents/42 auditor | Valid | Grant | Audit grant | 200 |
| GET /documents/42 guest | Valid | Deny | Does not run | 403 |
| GET /documents/999 alice | Valid | Grant | Method throws 404 | 404 |
| GET /documents/42 alice wrong password | Failed | Does not run | Does not run | 401 |

These statuses and bodies are **expectations for the demo app**, not a guarantee that every Spring Security configuration uses the same entry point/exception handler. With form login, missing authentication can result in a **302 redirect** instead of 401.

## 11. Document Exists Yet Unauthorized: 403 or 404?

In the example, Bob reading document 42 (which exists) gets 403; accessing ID 999 gets 404. An attacker could use this difference to infer **which IDs exist**. This is an existence-disclosure risk in some systems.

Design approaches:

1. Keep 403/404 per the API contract when resource existence is non-sensitive and auditing is thorough.
2. For sensitive data, query directly scoped by user/tenant, and if not found within the allowed scope, return a uniform not-found response.
3. Design controlled custom access-denied handling if the product requires hiding existence, while avoiding mapping every error to 404 without analysis.
4. Never return DTOs or messages containing title/owner to unauthorized users.
5. Test both **non-owner** and **nonexistent ID** to verify the response policy.

Conditional pseudo-query:

```text
findByIdAndTenantIdAndOwnerId(
    documentId,
    trustedTenantIdFromPrincipal,
    trustedUserIdFromPrincipal)
```

This describes the concept, not a built-in method automatically present on every repository. If an auditor needs access to read all documents, a dedicated explicitly authorized query/policy is required.

## 12. Multi-Tenant, JPA Lazy Loading, and Performance

### Multi-Tenant

Comparing `ownerUsername == authentication.name` is only suitable when usernames are sufficiently unique and serve as trusted business principals. For multi-tenant systems, prefer checking:

```text
user has DOCUMENT_READ
AND document.tenantId == trustedPrincipal.tenantId
AND document.ownerId == trustedPrincipal.userId
```

You can use a policy bean:

```java
// Illustrative fragment: requires a real documentPolicy bean.
@PostAuthorize("@documentPolicy.canRead(authentication, returnObject)")
public DocumentView findDocument(long id) {
    return repository.load(id);
}
```

The `documentPolicy` bean must compare owner/tenant against server data, never trusting client-sent `X-Owner: true` or `X-Tenant-Id`. When users belong to multiple tenants, membership/allowedTenants must come from a verified source.

### JPA Lazy Loading

If `returnObject` is a JPA entity and the expression reads `returnObject.owner.username`, evaluation can trigger **lazy loading**. If the persistence context is closed, an error can occur; if still open, it can issue unpredictable extra queries. A DTO/projection containing the needed owner/tenant fields is usually easier to test. When complex logic is needed, a policy bean can query repositories with explicit scoping.

### Cost of Reading Before Denial

Bob having DOCUMENT_READ still causes the method to load document 42 before PostAuthorize denies it. For very large documents or expensive databases/remote APIs, consider checking ownership from cheaper metadata before loading the payload, or scoping the query by owner/tenant upfront.

**PostAuthorize is not a data-access optimization strategy.** It is an authorization layer based on the return object; performance and minimizing data exposure at the data layer still need to be addressed.

## 13. Optional, Collections, Async, and Other Return Values

### Optional

If a method returns `Optional<DocumentView>`, `returnObject` is the Optional wrapper. The expression `returnObject.ownerUsername` does not directly read DocumentView's owner. Use a policy method supporting Optional or change the service contract to return a DTO / throw 404. Never ignore null/empty paths.

### List / Page

With `List<DocumentView>`, PostAuthorize allows or denies the entire collection. If you want to filter individual elements after the method returns, `@PostFilter` can be an option for supported types, though it does not replace scoped queries. With pagination, post-load filtering can make `totalElements`, offset/size, and ordering inconsistent.

### Async / Reactive

If a method returns a `CompletableFuture` or publisher, the moment the Java object is returned is not necessarily when async data finishes. Reactive method security and Servlet synchronous method security have distinct support/differences. This lesson applies only to **synchronous methods in a Spring MVC Servlet application**. Do not copy expressions and assume they inspect values inside publishers across all versions.

### Void Methods

A `void` method has no useful return data for checking ownership. If it performs mutations, you should definitely not rely on PostAuthorize. Use `@PreAuthorize` and domain validation before side effects.

## 14. Testing the Method-Security Proxy Directly

MockMvc tests the whole request through the security chain. If you want to isolate method checks from HTTP Basic, write an integration test injecting the service bean and setting test authentication with `@WithMockUser`:

```java
// Supplementary fragment in a @SpringBootTest with injected DocumentService documents.
@Test
@WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
void bobCannotReadAliceDocumentViaServiceProxy() {
    assertThatThrownBy(() -> documents.findDocument(42L))
            .isInstanceOf(AccessDeniedException.class);
}
```

This is a **fragment**, requiring imports for `@WithMockUser`, `@Test`, `AccessDeniedException`, and AssertJ `assertThatThrownBy`, plus the `documents` bean. It directly tests the proxy advice instead of going through the controller. `@WithMockUser` does not verify real passwords; to also test the auth provider, use `httpBasic(...)` as in the runnable test suite in section 9.

**Key QA point:** testing only grant cases will not catch disabled method security. There must be at least one **deny** case (Bob non-owner and guest without permission) and one **allow** case (Alice owner or auditor).

## 15. Overall Security and Debugging

`@PostAuthorize` is one piece of a layered architecture:

- Authentication filters verify identity with valid credentials.
- HTTP authorization controls URLs/methods.
- `@PreAuthorize` checks broad operation permissions before the method.
- `@PostAuthorize` controls returning results based on the loaded object.
- Database/services continue enforcing tenant, ownership, and business invariants.
- Exception handling and logging ensure denied data is not disclosed.

### Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Bob can read Alice's document | Missing `@EnableMethodSecurity`, self-invocation, non-proxied bean | Run Bob 403 negative test, check Spring DI |
| Gets 403 yet DB row was deleted | PostAuthorize placed on a mutation | Move permission/owner checks before mutation and transaction |
| Error on property ownerUsername | DTO missing getter, typo, Optional/null result | Inspect actual return type and getter |
| Alice has right password yet still 403 | Missing pre permission, different owner, tenant mismatch | Check authorities and who owns the resource |
| Anonymous receives 401 | HTTP Basic entry point rejects missing credentials | Normal behavior |
| Guest gets 403 before service runs | PreAuthorize denies | Expected per policy |
| Non-existent ID causes 500 | Returned null then SpEL dereferenced | Throw 404 before return or handle null intentionally |
| Cross-tenant reads wrong document | Compared username only, no tenant check | Use trusted principal ID and tenant ID |
| Owner/title leaked in error body | Custom exception handler/log accidentally echoes result | Inspect responses and logging |
| Lazy JPA property fails | PostAuthorize reads relation outside transaction | Use DTO/projection or appropriate fetch |
| List post-filter breaks pagination | Loaded all items then filtered in Java | Scope query in DB |
| Method security skipped on this.method() | Self-invocation bypasses proxy | Extract bean, call via injected proxy |
| Service method returns 403 after email sent | Side effect ran before post check | Design pre-check/outbox or transaction |
| 200 tests pass yet permissions are inactive | Only positive tests exist | Add negative non-owner tests |

### Diagnostic Procedure

1. Confirm the request enters the intended `SecurityFilterChain`, credentials are verified, and a valid `Authentication` exists.
2. Confirm `@EnableMethodSecurity` is enabled and calls go through the **Spring-managed proxy**.
3. Confirm `@PreAuthorize` checks coarse permissions early and is not skipped.
4. Confirm return object type, property getters, and the `returnObject` expression match.
5. Compare the principal's identity against **server-side** owner/tenant, never relying on client headers.
6. Separate 401 (unauthenticated), 403 (insufficient permission), and 404 (resource missing) per contract.
7. Check side effects, transaction boundaries, lazy JPA, and self-invocation bugs.
8. Run negative integration tests and verify responses do not include blocked DTOs.

In development you can enable logging:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log raw passwords, Authorization headers, JWTs, session cookies, or full denied DTOs in production.

## 16. Self-Review Questions

1. **Does PostAuthorize run before or after the method?** After the method has returned a value successfully.
2. **What is returnObject?** The actual return value of the method exposed to SpEL.
3. **Can @PreAuthorize read the current returnObject?** No; the method has not run yet.
4. **Why can Bob have DOCUMENT_READ and still get 403?** He passed the pre-check yet failed the post-check because he is not the owner.
5. **What allows Auditor to read someone else's document?** The `DOCUMENT_AUDIT` permission explicitly granted in the policy.
6. **When is Guest blocked for lacking permission?** At PreAuthorize before reading the object.
7. **Should PostAuthorize alone be used for delete/money-transfer?** No; mutations/side effects can happen before denial.
8. **Does PostAuthorize roll back an already-sent email?** Not guaranteed.
9. **What if a DTO has an ownerUsername field without a getter?** SpEL property access may fail depending on type/visibility; explicit getters are safer.
10. **If a method returns Optional<DocumentView>, can you use returnObject.ownerUsername directly?** No, returnObject is the Optional.
11. **Does @PostAuthorize automatically filter a List element by element?** No; @PostFilter has different semantics.
12. **How dangerous is omitting @EnableMethodSecurity?** Method-security annotations may not execute at all.
13. **Why can self-invocation bypass?** A `this.method()` call does not go through the Spring proxy.
14. **Is owner username enough for multi-tenancy?** Usually not; trusted IDs/tenant are needed.
15. **What can 403 vs 404 reveal?** It can disclose whether a resource ID exists.
16. **Which branches should MockMvc tests cover?** 200 owner, 403 non-owner, 200 auditor, 403 guest, 401 anonymous, 404 missing ID.
17. **Can PostAuthorize still be used when an API is STATELESS?** Yes, because Authentication exists within the current request.
18. **If a method throws 404 before returning an object, what does PostAuthorize check?** There is no successful return value to evaluate; the exception follows its own flow.

## 17. Checklist for Real Projects

- [ ] Enable `@EnableMethodSecurity` in Spring Security configuration.
- [ ] Place `@PostAuthorize` on **Spring-managed service methods** called through proxies.
- [ ] Use `returnObject` with real properties/getters and an explicit return type.
- [ ] Never use client-supplied owner/tenant/role to decide permissions.
- [ ] Combine with `@PreAuthorize` to block users lacking permissions before the method.
- [ ] Do not rely solely on `@PostAuthorize` to protect mutations or side effects.
- [ ] For write operations, check permission + owner/tenant/domain state **before** mutating and inside a transaction when appropriate.
- [ ] If an ID does not exist, define the 404/null/Optional policy before applying SpEL.
- [ ] For multi-tenancy, use trusted principal user IDs and tenant scopes, not just usernames.
- [ ] With JPA, consider DTOs/projections to avoid lazy-loading inside expressions.
- [ ] With large collections, filter data in queries rather than relying on @PostFilter after loading.
- [ ] Have no ad-hoc proxy registration logic or self-invocation bypassing method advice.
- [ ] Control HTTP 401/403/404, existence-leak risks, and error responses.
- [ ] Test both grant and deny; ensure DTOs never leak via logs/errors.
- [ ] Configure HTTPS and token/session/CSRF suitable for actual HTTP clients.
- [ ] For async/reactive methods, study the corresponding interceptor/context propagation before applying synchronous patterns.

**Conclusion:** `@PostAuthorize` inspects the **result a service produced** using the SpEL variable `returnObject`. It is especially useful for **read methods** where permissions depend on the owner, tenant, or attributes of the loaded resource. Pair it with `@PreAuthorize` for upfront permission checks; use Spring-managed proxies, trusted server data, and negative tests. Because PostAuthorize runs **after method execution**, it **does not automatically prevent, revoke, or reverse side effects** of the method.