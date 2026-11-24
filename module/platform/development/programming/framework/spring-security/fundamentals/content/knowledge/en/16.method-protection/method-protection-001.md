# Why Does the Service Layer Still Need Authorization Checks Beyond HTTP Rules?

> **Scope:** Spring Security – fundamentals → **Method protection**. The goal of this lesson is to understand the limitations of URL/HTTP-based authorization and how to protect business logic at the service layer, where an action can be invoked through multiple execution paths.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain why `authorizeHttpRequests` rules are not enough to protect every service call.
2. Distinguish authorization checks at the **HTTP boundary**, **service method**, and **data access/domain boundary**.
3. Use `@EnableMethodSecurity` and `@PreAuthorize` to block calls to a Spring-managed service before business logic runs.
4. Understand the role of Spring AOP proxies, `AuthorizationManagerBeforeMethodInterceptor`, and why self-invocation can bypass annotations.
5. Build authorization checks based on permissions, **owner**, **tenant**, and server-verified data; avoid IDOR/BOLA vulnerabilities.
6. Test the same policy both over HTTP and by calling the service bean directly.
7. Analyze cases involving jobs, event/message consumers, `@Async`, transactions, and WebFlux applications.

## 2. The Core Problem: HTTP Is Only One Entry Point

In Spring MVC, a common configuration looks like this:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").hasAuthority("DOCUMENT_READ")
    .anyRequest().denyAll()
);
~~~

The snippet above is part of a Servlet `SecurityFilterChain` configuration; it **checks HTTP requests passing through the security filter chain**. This is an important layer of protection, but it does not automatically attach the `DOCUMENT_READ` condition to every way `DocumentService.read(...)` can be called.

Suppose the service can be used from:

- `DocumentController`: requests called by browsers or mobile apps;
- `DocumentExportJob`: scheduled jobs or background tasks;
- `DocumentMessageConsumer`: Kafka/RabbitMQ message handling;
- `AdminTool`: CLI, batch, or internal integrations;
- another service within the same application;
- a new HTTP controller added later.

If permissions are only placed on `/api/documents/**`, the policy depends on every caller remembering to configure its endpoint properly. A caller via a message broker or a direct Java method call **is not an HTTP request**, so URL matchers are never evaluated. Even within HTTP, a new route or a misconfigured security filter chain can accidentally open a path into the same business operation.

**Principle:** *When an operation carries business authority or affects sensitive data, authorization should be checked at a trusted boundary close to that operation.* HTTP and method authorization should complement each other.

### Two-Layer Protection Diagram

~~~text
HTTP Client                 Scheduled Job / Message / Internal Bean
    |                                      |
    v                                      |
SecurityFilterChain                        |
    | authorizeHttpRequests                |
    | (route, method, coarse permission)   |
    v                                      v
Controller  -------------------------> Spring service proxy
                                          |
                                          v
                                 @PreAuthorize / policy
                                    |          |
                                  DENY       ALLOW
                                    |          |
                                    v          v
                           AccessDenied   Business method
                                            |
                                            v
                                   Repository / database
                                   (tenant/owner scope)
~~~

Spring method security only works when it is **enabled** and the call goes through the appropriate interceptor/proxy. An ordinary call to a `new DocumentService(...)` object outside Spring or self-invocation bypassing the proxy may not be intercepted; a later section explains how to fix this.

## 3. Distinguishing Three Places to Put Rules

| Layer | Best-known input | Example | What it protects |
| --- | --- | --- | --- |
| HTTP request | Path, HTTP method, authentication, verified headers | `GET /api/documents/**` requires `DOCUMENT_READ` | The corresponding HTTP entry point |
| Service method | Business action, method arguments, principal, domain state | `readDocument(id)` only for owner in the same tenant | Any caller **going through the secured Spring proxy** |
| Repository / database / domain | Actual record, real tenant ID, real owner, state/version | Query with `tenant_id = ?` condition; policy on update | Scope and integrity of the processed data |

The three layers solve three different problems. HTTP authorization can reject invalid requests early, but `hasAuthority("DOCUMENT_READ")` does not know **which document** the user wants to read without looking up the document. The service method has the `id`, business context, and repository to check owner/tenant. Data access should apply scope conditions directly in queries for large datasets or multi-tenant systems to reduce the risk of leaking a row.

A good rule typically takes the form:

~~~text
ALLOW readDocument(user, documentId)
    when user is authenticated
     AND user has DOCUMENT_READ
     AND document exists
     AND document belongs to an allowed tenant
     AND (user is owner OR has valid share/management permission)
    otherwise: DENY
~~~

This is **pseudocode**, not Java yet. In many systems, whether a document does not exist or the user lacks permission to know it exists also requires a consistent 403/404 response strategy to avoid leaking IDs. Never trust `tenantId` or `owner` merely because the client sent them in a path, header, or body.

## 4. Reasons to Add Checks at the Service Layer

### 4.1. Same Business Logic, Multiple Entry Points

At the HTTP boundary, `authorizeHttpRequests` applies to request matchers. However, jobs, event listeners, command handlers, and internal calls do not pass through the Servlet `AuthorizationFilter`. If rules live only in controllers or HTTP configuration, each entry point can end up with a different policy.

A service-level policy creates a shared checkpoint for calls going through the bean proxy. When a background flow needs special privileges, design a trusted identity/service principal or an explicit policy for system actions. Never simply disable method security just to let a job run.

### 4.2. URL Rules Struggle to Express Per-Record Permissions

`GET /api/documents/101` and `GET /api/documents/201` both match `/api/documents/**`. However, document 101 might belong to tenant A and document 201 to tenant B. The `DOCUMENT_READ` permission only expresses the *action type*; the condition for *which object* requires the actual data.

If you rely solely on `hasAuthority("DOCUMENT_READ")` and then call `findById(id)` without checking the tenant, an attacker with a valid account can swap the ID to retrieve someone else's document (**BOLA / Broken Object Level Authorization**, or IDOR in many contexts).

### 4.3. Controllers and URLs Can Be Reorganized

An application may add admin routes, a `/v2` version, GraphQL resolvers, or a public integration API. Each URL will need its own policy, yet the permission to read or edit a document should stay consistent at the service layer. Placing rules on methods reduces risk when routing changes or logic is reused.

### 4.4. Avoid Guarding Only the Caller While Leaving Side Effects Unprotected

For example, `transferMoney`, `approveInvoice`, or `deleteAccount`: permissions must be verified **before** transferring funds, updating the DB, or calling an external system. If the service executes without checking on its own, another caller can trigger side effects even if the main HTTP endpoint is protected.

### 4.5. Business Policies Need Business Context

Rules may depend on state:

- Only the owner may edit while the document is in `DRAFT`;
- Only an approver in the same tenant may approve invoices within their limit;
- `CONFIDENTIAL` data requires an additional permission;
- Locked users or users whose permissions were revoked cannot continue executing.

These conditions belong to the domain/policy service and are hard to maintain if copied across multiple controllers or URL matcher expressions.

### 4.6. Enabling HTTP-Independent Testing

You can test `DocumentService.read(101)` directly with `@WithMockUser` and assert `AccessDeniedException` when permissions are missing. This test protects the business boundary even when endpoints change. HTTP integration tests are still needed to verify that routing and the security chain work properly.

### 4.7. Reducing Dependence on Error-Prone Configuration

Mistakes such as overly broad matchers, wrong route ordering, forgetting to protect a new route, misconfiguring `securityMatcher` across multiple `SecurityFilterChain`s, or getting the dispatcher policy wrong can all compromise HTTP protection. Method security provides an independent layer that limits the blast radius, though it must itself be configured and tested carefully.

**Technical conclusion:** Service authorization does not make HTTP authorization redundant. The HTTP layer rejects invalid requests early, while the service protects business operations when invoked via different paths.

## 5. Spring Security's Method Security Mechanism

Enable the feature on a configuration class:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

This is a fragment and requires the corresponding Spring imports. `spring-boot-starter-security` **does not enable method security automatically** just because you added the dependency. In Spring Security 6.x/7.x, `@EnableMethodSecurity` is the standard API; `@EnableGlobalMethodSecurity` is the legacy approach.

Example:

~~~java
@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public Document read(long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

This illustrative snippet requires `Document`, `repository`, and imports in a real application—it is not a standalone runnable file. `@PreAuthorize` expresses a condition required **before invoking the method**. If the user does not satisfy it, the method will not be executed through Spring AOP method-security interceptors.

Typical flow:

~~~text
Caller --> Spring-managed service proxy
            |
            v
  AuthorizationManagerBeforeMethodInterceptor
            |
            v
     evaluate @PreAuthorize
            |
          PASS? -------- no ---> AccessDeniedException
            |
           yes
            |
            v
      execute service method
            |
            v
        return result
~~~

Spring Security uses the `AuthorizationManager` mechanism and corresponding interceptors, such as `PreAuthorizeAuthorizationManager`. Most applications do not need to create these interceptors manually; `@EnableMethodSecurity` activates them.

### @PreAuthorize, @PostAuthorize, and @PostFilter

| Annotation | Timing | Suitable use case | Warning |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before method body | Edit/delete/approve rights, permissions, and method arguments | Checking the true owner may require a prior lookup |
| `@PostAuthorize` | After method body, inspects `returnObject` | Authorization based on the retrieved result | Method side effects have already occurred before denial |
| `@PreFilter` | Filters certain input collections before invocation | Filtering inputs by policy | Not suitable for every input type or large volumes |
| `@PostFilter` | Filters result collection | Certain small lists | May have already loaded too many rows before filtering |
| `@Secured` / `@RolesAllowed` | Before invocation | Simple role rules | Requires explicit enabling flags; less flexible than SpEL |

**Do not use `@PostAuthorize` for money transfers or data deletion** assuming Spring will undo side effects when authorization fails. Check permissions before mutation, and coordinate transactions with resource-scoped queries.

### Expression Examples

~~~java
@PreAuthorize("hasAuthority('INVOICE_APPROVE')")
public void approve(long invoiceId) { /* ... */ }

@PreAuthorize("hasRole('ADMIN') or hasAuthority('USER_MANAGE')")
public void deactivateUser(long userId) { /* ... */ }

@PreAuthorize("hasAuthority('DOCUMENT_READ') and @documentPolicy.canRead(authentication, #p0)")
public String readDocument(long documentId) { /* ... */ }
~~~

The methods above are syntax examples and do not run standalone. `#p0` references the parameter at position 0 in a Spring Method Security expression, avoiding reliance on parameter name metadata in unconfigured builds. `@documentPolicy` points to the Spring bean named `documentPolicy`; `authentication` is provided by the security expression root. With builds configured to preserve parameter names, `#documentId` can be used for readability.

## 6. When Is a Role-Only @PreAuthorize Insufficient?

Example:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

This policy ensures the caller has permission to **read documents in general**, but does not constrain **which document is being read**. If there are 10,000 documents belonging to multiple customers, any user holding `DOCUMENT_READ` could read all of them if they know the IDs.

To be complete, you need:

1. General permission for the `READ` action.
2. Trusted tenant scope of the principal.
3. Document owner or valid sharing relationship.
4. Document state conditions (deleted, locked, unpublished, etc.) if required by business rules.
5. Controlled handling for missing objects and repository errors.

Same tenant is **not enough** if only the owner is allowed to read. Matching owner name is **not enough** if the tenant differs. The `ADMIN` role does not automatically imply cross-tenant privileges: cross-tenant access is a separate policy that must be explicitly granted and audited.

## 7. Runnable Demo: HTTP Rule + Service Rule + Ownership

The sample application uses **Java 17**, **Spring Boot 3.5.7**, **Spring MVC/Servlet**, **Spring Security 6.5 line**, and Maven. Its purpose is to show that HTTP only checks `DOCUMENT_READ`, while the service additionally checks owner and tenant. WebFlux is not used in this demo so that the Servlet `SecurityFilterChain` and `SecurityContextHolder` model stands out clearly.

### Project Structure

~~~text
document-authorization/
  pom.xml
  src/main/java/com/example/authz/
    AuthzApplication.java
    SecurityConfig.java
    DocumentStore.java
    TenantDirectory.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/authz/
    DocumentAuthorizationTests.java
~~~

Create each file with the exact path/package. Use an installed Maven 3.9+ and JDK 17+, or generate the Maven Wrapper via Spring Initializr. In the demo, users, tenants, and documents are stored in memory for clarity; production systems use a controlled data store and identity provider.

### File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>document-authorization</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
~~~

### File AuthzApplication.java

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzApplication.class, args);
    }
}
~~~

### File DocumentStore.java

~~~java
package com.example.authz;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Document(
        long id, String tenantId, String owner, String body
    ) {}

    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101, "north", "alice", "alice-document-101"),
        102L, new Document(102, "north", "bob", "bob-document-102"),
        201L, new Document(201, "south", "carol", "carol-document-201")
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }
}
~~~

Each document has an ID, tenant, and owner stored on the server. `DocumentStore` is an illustrative repository; replacing it with a real database requires proper query and transaction design.

### File TenantDirectory.java

~~~java
package com.example.authz;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, String> tenantByUser = Map.of(
        "alice", "north",
        "bob", "north",
        "carol", "south"
    );

    public Optional<String> tenantOf(String username) {
        return Optional.ofNullable(tenantByUser.get(username));
    }
}
~~~

The user's tenant scope is retrieved from a **server-managed** directory, without trusting arbitrary query params or headers set by the client. In production, tenant information can come from a database or a JWT claim signed by a trusted issuer and fully validated by the resource server for signature, audience, issuer, and expiry.

### File DocumentPolicy.java

~~~java
package com.example.authz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore store;
    private final TenantDirectory directory;

    public DocumentPolicy(DocumentStore store, TenantDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String username = authentication.getName();

        return directory.tenantOf(username)
            .flatMap(tenant -> store.findById(id)
                .filter(doc -> doc.tenantId().equals(tenant)
                    && doc.owner().equals(username)))
            .isPresent();
    }
}
~~~

`canRead` returns `true` when the caller has a valid identity, the document exists, belongs to the same tenant, and matches the owner. The general permission check is placed in the service's `@PreAuthorize`. If no document or valid tenant is found, the policy **denies**. This sample has no sharing or admin privileges; if added, you must explicitly define and test the policy rather than implicitly assuming an admin role has all permissions.

### File DocumentService.java

~~~java
package com.example.authz;

import java.util.NoSuchElementException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize(
        "hasAuthority('DOCUMENT_READ') and "
        + "@documentPolicy.canRead(authentication, #p0)"
    )
    public String read(long id) {
        return store.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document missing"))
            .body();
    }
}
~~~

This is the **linchpin of the demo**: even when a caller does not pass through the HTTP filter, if the caller invokes `DocumentService` via the Spring proxy, `@PreAuthorize` still enforces the policy. The policy uses `#p0` to receive `id`, calls the Spring-managed `DocumentPolicy`, and only then allows the method to read the body. Every authorized caller must satisfy both the permission and the owner/tenant condition.

In this demo version, a non-existent document is denied by `DocumentPolicy`, so the route typically returns 403 instead of reaching `NoSuchElementException`. In production, design consistent 403/404 rules and error handling; do not fake 404 errors if business requirements need authorized admins to distinguish missing records.

### File DocumentController.java

~~~java
package com.example.authz;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/docs")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String read(@PathVariable("id") long id) {
        return service.read(id);
    }
}
~~~

The controller only forwards the request to the service and does not perform owner/tenant checks itself. The HTTP rule remains the first line of defense; the business policy resides in `DocumentService`. If a second controller is added using the same service, the service-level rule is still enforced when the bean is called through its proxy.

### File SecurityConfig.java

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/docs/**")
                    .hasAuthority("DOCUMENT_READ")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("carol123"))
            .authorities("DOCUMENT_READ")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }
}
~~~

Here:

- `@EnableMethodSecurity` **enables method checking**; if this annotation is forgotten, `@PreAuthorize` on the service will not take effect as expected.
- HTTP GET `/api/docs/**` only checks that the user has `DOCUMENT_READ`. A user with this authority still has to pass the service's owner/tenant check.
- `anyRequest().denyAll()` acts as a default deny for other routes in the demo.
- `httpBasic` makes quick experimentation easy. HTTPS is required if Basic credentials are sent over a network; localhost is for learning only.
- `InMemoryUserDetailsManager` and sample passwords are not suitable for production. Use an identity provider and proper password/secret management.
- The demo only exposes GET; therefore CSRF is not disabled. If adding POST/PUT/DELETE, decide on a CSRF policy suitable for cookie/session or stateless APIs and test it.

**Do not add `spring-boot-starter-webflux` to this demo.** Spring WebFlux requires `SecurityWebFilterChain`/`@EnableReactiveMethodSecurity` and a reactive security context mechanism different from Servlet.

## 8. Running the Application and Observing the Difference

From the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

If you generated the Maven Wrapper from Spring Initializr, you can use `./mvnw test` and `./mvnw spring-boot:run`; on PowerShell use `.\mvnw.cmd test` and `.\mvnw.cmd spring-boot:run`. When Spring Boot is listening on `localhost:8080`, use another terminal:

~~~bash
curl -i http://localhost:8080/api/docs/101
curl -i -u alice:alice123 http://localhost:8080/api/docs/101
curl -i -u bob:bob123 http://localhost:8080/api/docs/101
curl -i -u carol:carol123 http://localhost:8080/api/docs/101
curl -i -u bob:bob123 http://localhost:8080/api/docs/102
curl -i -u carol:carol123 http://localhost:8080/api/docs/201
curl -i -u alice:alice123 http://localhost:8080/api/docs/999
~~~

On PowerShell, `curl` may be an alias for `Invoke-WebRequest` in some versions; you can call `curl.exe` with the same arguments above.

Results **expected from the code** (not build logs executed in this document):

| Request | Expected HTTP | Response body on success | Reason |
| --- | --- | --- | --- |
| Anonymous → 101 | 401 | — | Unauthenticated; HTTP requires `DOCUMENT_READ` |
| Alice → 101 | 200 | `alice-document-101` | Has authority, same tenant, and is owner |
| Bob → 101 | 403 | — | Bob has authority, same tenant, but is not owner |
| Carol → 101 | 403 | — | Carol has authority, but different tenant and not owner |
| Bob → 102 | 200 | `bob-document-102` | Bob is owner, correct tenant |
| Carol → 201 | 200 | `carol-document-201` | Carol is owner, correct tenant |
| Alice → 999 | 403 in demo | — | Policy does not find record, so it fails closed |

The 401/403 results come from the default security entry point and access-denied handling combined with HTTP Basic and method security; error response headers/body may vary by version/configuration. When applying this to a real product, test the system's own status codes and API error contract.

### What Error Happens If Only HTTP Rules Are Kept?

Suppose `@EnableMethodSecurity` or `@PreAuthorize` is temporarily removed from the service in a test environment. Alice and Bob both have `DOCUMENT_READ`, so the HTTP rule lets Bob into `/api/docs/101`. If the service directly calls `store.findById(101)` without checking ownership, Bob will retrieve Alice's document content. This is the exact vulnerability that service-level authorization solves.

Do not deploy experiments with disabled policies to environments holding real data. Use known test data, restore the policy, and keep regression tests to prevent the bug from returning.

## 9. Testing Both HTTP and Direct Service Calls

With `pom.xml` above already containing `spring-boot-starter-test` and `spring-security-test`, add the following file.

### File DocumentAuthorizationTests.java

~~~java
package com.example.authz;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void aliceCanReadHerDocumentOverHttp() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-document-101"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
    void bobCannotReadAlicesDocumentOverHttp() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
    void bobCannotReadAlicesDocumentDirectlyThroughService() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void aliceCanReadDirectlyThroughService() {
        assertEquals("alice-document-101", service.read(101));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "DOCUMENT_READ")
    void tenantBoundaryIsEnforced() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "SOME_OTHER_RIGHT")
    void ownerWithoutReadAuthorityIsRejected() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }
}
~~~

**Explanation of the two test types:**

- `MockMvc` constructs mock requests inside Spring Test, passing through the Servlet security filter chain. It verifies HTTP rules and status responses.
- The `service.read(...)` tests invoke the **Spring-managed service proxy** injected by the container. There is no HTTP request here; if `AccessDeniedException` is still thrown, the method-security boundary is working.
- `@WithMockUser` sets up a mock security principal used in tests. It **does not test** real Basic credentials authentication or JWT validation; testing that requires appropriate integration tests.
- Owner and tenant tests verify business policies. The test where the owner lacks the authority proves that owner-only does not automatically substitute for permission.
- Production also requires testing repository failures, sharing permissions, transaction boundaries, policy caches, and missing-resource cases.

The test snippet above is sample code for learners to run with Maven; a "pass" result is only expected when configuration and environment match. Run the actual tests in your project before considering the demo verified.

## 10. Why Is a Direct Call Still Blocked?

With an injected bean:

~~~java
@Service
public class ExportService {
    private final DocumentService documents;

    public ExportService(DocumentService documents) {
        this.documents = documents;
    }

    public String exportOne(long id) {
        return documents.read(id);
    }
}
~~~

This is an illustrative fragment and is not part of the demo app. `ExportService` calls `DocumentService` through the reference Spring gives it, which is typically a proxy with security advisors. If the current principal lacks sufficient rights, `documents.read(id)` is denied before running the body. This keeps the business policy enforced when the service is used by exporters, jobs, or consumers.

However, **method security does not automatically create an identity for a job**. A scheduled job running outside HTTP usually has no user `Authentication`. If it is a job with system privileges, define a distinct system principal/authority, validate its execution source and resource scope, or call an operation dedicated to system processes protected by a different boundary. Never implicitly assign `ROLE_ADMIN` to every background thread or remove annotations just to avoid errors.

### AccessDeniedException Outside HTTP

When an exception is thrown inside the HTTP security filter chain, `ExceptionTranslationFilter` can translate it into an appropriate 401/403. But when a job calls a service directly, there is no HTTP response to translate into. The caller must handle `AccessDeniedException` according to context: stop the user's job, return an error to message handling, write an audit log, and decide between retry or dead-letter. Swallowing the exception and continuing mutation defeats access control.

## 11. Limitation of Spring AOP Proxy: Self-Invocation

Consider the following class:

~~~java
@Service
class DangerousDocumentService {

    public String wrapper(long id) {
        return this.securedRead(id);
    }

    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public String securedRead(long id) {
        return "data";
    }
}
~~~

This is **illustrative code**, not part of the demo project. In standard Spring AOP proxy setups, the call `this.securedRead(id)` happens **inside the same object**, bypassing the proxy, so the method-security interceptor may not be invoked. Calling `securedRead(...)` from another bean through the Spring proxy, however, is checked.

Applicable solutions:

1. Extract the protected method into a separate service bean; callers inject that bean and call through its proxy.
2. Place the policy directly inside the domain service at the mutation point if it is a mandatory invariant regardless of AOP mechanics.
3. For special cases, evaluate AspectJ weaving per Spring Security documentation, which comes with higher configuration and testing overhead.

Do not rely on `AopContext.currentProxy()` as a default fix: it couples business code to AOP and harms maintainability. Organize code so security boundaries are explicit.

Other proxy issues to remember: `final` classes/methods in certain proxy types, non-proxyable methods, objects manually instantiated with `new`, callbacks detached from Spring, and differences between interface proxies and class proxies. Test the **actual** call path instead of only reading annotations and assuming they are enforced.

## 12. Transactions, Concurrency, and Data Changing Between Checks

In the demo, `DocumentPolicy.canRead` looks up the document first and `DocumentService.read` looks it up again later. Because in-memory data is immutable, the result is stable. In production, there can be a window between check and use (TOCTOU — *time of check to time of use*).

Example:

~~~text
T1: policy reads document 101 -> owner=alice, status=DRAFT
T2: admin moves document to another tenant or locks document
T3: service still updates document 101 based on T1 result
~~~

To reduce risk:

- Perform both the check and the mutation within an appropriate transaction, considering isolation, locking, or versioning depending on business consistency needs.
- For sensitive writes, combine authorization conditions with the SQL update, e.g. `UPDATE ... WHERE id=? AND tenant_id=? AND owner_id=? AND status='DRAFT'`, then check the row count. This is an **illustrative SQL pattern**, not a substitute for transaction design.
- Avoid fetching broad datasets and filtering in memory; scoped queries `WHERE tenant_id = :tenant AND owner_id = :owner` are generally safer and more efficient with proper indexes.
- If permissions can be revoked immediately, consider token TTL, cache invalidation, policy versioning, and concurrency semantics.
- Distinguish "insufficient permissions" from "DB error": system errors should fail closed regarding data access, without necessarily pretending to be 403; returning a 5xx service error allows operations to monitor it.

Both `@Transactional` and `@PreAuthorize` can rely on Spring AOP. Advice ordering and transaction boundaries can affect when state is read. Test cases where data changes concurrently, and do not assume authorization queries always execute in the same transaction as mutations. This must be designed intentionally; no single annotation solves it completely.

## 13. Service Authorization Is Not Just About Roles

A policy can be expressed as:

~~~text
subject  = (principalId, tenant, permissions, accountState)
action   = read | update | approve | delete
resource = (resourceId, owner, tenant, classification, status)
context  = (time, risk, MFA assurance, delegation, policyVersion)
decision = grant | deny
~~~

Control models are often combined:

- **RBAC:** `ROLE_MANAGER` has permission to approve invoices within its assigned scope.
- **ABAC:** approval is constrained by amount, status, tenant, and the user's approval limit.
- **ReBAC:** the user is an owner, collaborator, or has been shared the resource.
- **Permission-based:** authorities like `DOCUMENT_READ` and `DOCUMENT_UPDATE` let rules express exact actions.

For example, a role name like `ADMIN` should have a clearly defined meaning, especially in multi-tenant systems. Do not use `hasRole("ADMIN")` as a wildcard if tenant A's admin must not touch tenant B. A "cross-tenant system admin" model requires separate permissions, an audit trail, and a strict provisioning process.

### Where to Place Policies

For short policies, `@PreAuthorize("hasAuthority('DOCUMENT_READ')")` is easy to read. For complex owner/tenant/approval logic, use a bean like `DocumentPolicy` and call it from the expression. If logic is shared outside Spring, extract it into a plain Java domain-level service taking a `PrincipalContext` and resource for independent testing; the `@PreAuthorize` adapter simply forwards context into the policy. This avoids embedding all business logic in long SpEL strings.

## 14. Non-HTTP Execution Paths Need Dedicated Identity Design

| Entry point | Automatically runs through HTTP filter? | Needs attention |
| --- | --- | --- |
| REST controller | Yes, if request matches a `SecurityFilterChain` | HTTP rule + service rule |
| GraphQL resolver over HTTP | HTTP request can be checked, but fields/operations need their own policies | Resolver/service rule |
| Scheduled job | No | System identity or dedicated policy |
| Message listener | No | Validate producer, context, consumer authorization, service rule |
| Command-line runner | No | Operator/system principal and execution permissions |
| Internal service bean | No | Call via proxy and propagate appropriate context |
| Async task | No HTTP filter per callback | Security context propagation |
| WebFlux handler | Has WebFlux reactive filter chain | Separate reactive method/security context |

**SecurityContextHolder does not automatically follow you across every new thread.** On the Servlet stack, the default strategy is typically `ThreadLocal`-based. `@Async`/`CompletableFuture`/executor code can lose or accidentally use the wrong context if handled manually. When propagating identity is needed, use Spring Security's concurrency integration mechanisms (such as appropriate `DelegatingSecurityContext...` wrappers) and test cancellation and thread-reuse flows. Never copy raw credentials or tokens across threads without understanding their lifecycle and scope.

With WebFlux, use `@EnableReactiveMethodSecurity`, `SecurityWebFilterChain`, and `ReactiveSecurityContextHolder`; methods typically return reactive types like `Mono`/`Flux`. Do not copy code using `SecurityContextHolder`/Servlet `HttpSecurity` to a reactive stack expecting the context to remain accurate. Reactive authorization has its own asynchronous model and must not block the event loop with synchronous database policy clients.

## 15. Common Counterarguments

### "We already have Spring Security at the gateway, why must the service check?"

The gateway can validate tokens and block URL groups, but it usually does not know individual record states or specific ownership. Internally, there may also be jobs, events, rerouted APIs, or another system calling the service directly. The backend must establish the principal from a trusted source and enforce policies against its own resources. Never treat a self-declared HTTP header as an identity simply because the request came from an internal network.

### "Every controller calls this service, do we still need annotations?"

If all current call paths are properly protected, the system **may** be safe within that scope. However, service-level annotations serve as a directly testable checkpoint and prevent regressions when routes or callers change. For sensitive actions, placing policies near business logic reduces reliance on conventions across controllers. More importantly, annotations must actually run through the proxy and policies must inspect the right resources.

### "Isn't it wasteful to allow the URL and then deny in the service?"

The HTTP layer performs cheap coarse-grained permission checks and rejects early; the service checks business state where sufficient data exists. Both layers may have some overlapping checks, but policies must stay synchronized. Do not duplicate every rule into two independent versions that are hard to maintain: share a policy component or intentionally managed permission mappings.

### "Can @PostAuthorize be used to check the returned owner?"

It can be used for **some read-only methods** if the result must be inspected after loading. However, the data has already been fetched into memory and the method may have caused side effects before being denied. For updates, deletes, or approvals, prefer `@PreAuthorize` and/or queries constrained by owner/tenant before mutation. For large lists, filter at the repository instead of `@PostFilter`ing the entire result.

### "Does method security intercept every Java call?"

No. Under the typical proxy mechanism, it intercepts method invocations passing through the appropriate Spring AOP proxy. Self-invocation, non-Spring-managed objects, or calls outside interception scope can bypass it. Therefore, critical policies may require repository/database constraints and integration tests for call paths.

### "When there is no logged-in user, can a job create its own Authentication?"

Do not grant broad permissions arbitrarily. If a job has a legitimate business role, define a system principal/authority, verify which person or component is allowed to trigger the job, and record an audit log. If an operation falls outside user permissions, separate it into a system operation with its own trust boundary instead of impersonating a real user.

## 16. Common Mistakes List

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Protecting only URLs, letting service read any ID | IDOR/BOLA via other callers or new routes | Service/resource authorization and query scoping |
| Forgetting `@EnableMethodSecurity` | Annotations do not execute as expected | Enable configuration and add service-level tests |
| Using only `hasAuthority`, ignoring owner/tenant | Users with general permission read others' data | Use business policies backed by trusted data |
| Trusting client-supplied tenant | Cross-tenant access | Use server-validated identity/tenant |
| `this.securedMethod()` from the same bean | Can bypass Spring proxy | Separate bean boundaries or explicit checks |
| Creating service manually with `new` | Bypasses Spring-managed proxy | Inject Spring-managed beans |
| Using `@PostAuthorize` after mutation | Late decision; side effects already occurred | Pre-authorization + transactional constraints |
| Swallowing `AccessDeniedException` and continuing | Neutralizes enforcement | Stop the operation and handle per context |
| Granting `ROLE_ADMIN` to all background jobs | Overly broad privilege escalation | Dedicated system identity/permissions |
| Treating `SecurityContextHolder` like an immutable global | Wrong identity across async/thread switches | Propagate context via proper mechanisms |
| Mixing permissions and role prefixes arbitrarily | Policy mismatches | Standardize authorities and write tests |
| Fetching all rows and filtering in Java | Data exposure risk, high RAM usage | Scope at the query/repository layer |
| Never testing direct service calls | Testing only URLs misses proxy/policy issues | Unit/integration test the service boundary |
| Ignoring transactions/concurrent writes | TOCTOU between check and use | Transactions/locking/conditional updates |
| Treating 403 and 404 identically everywhere | Leaks or wrongly hides resource existence | Design an intentional error contract |
| Disabling CSRF to avoid 403 on POST | May open CSRF vulnerabilities | Distinguish CSRF vs authorization and fix properly |

## 17. Practical Workflow for Protecting a Real Service

1. **List entry points:** HTTP routes, jobs, message consumers, internal callers, new APIs; do not assume there is only one controller.
2. **Identify action and resource:** `readDocument`, `approveInvoice`, `deleteCustomer`; do the method arguments provide enough info to identify the resource ID?
3. **Define the policy:** principal, permissions, owner/tenant, state, delegation, default deny, and dependent error handling.
4. **Configure HTTP:** only permit genuinely public routes; clear method/path request rules, correct matcher order, catch-all `denyAll` or explicit authentication policy.
5. **Configure method security:** `@EnableMethodSecurity`, annotations on public service methods called through Spring proxies, custom policy beans for complex logic.
6. **Constrain data access:** query by tenant/owner, classify 403/404, use transactions/locking for mutations.
7. **Test:** authenticated/anonymous, valid/invalid permissions, owner/other, same/cross tenant, missing resources, alternate callers, and direct service invocation.
8. **Observe at runtime:** controlled logging of authorization denials, error metrics, appropriate security events; never log passwords or tokens.
9. **Review on changes:** new endpoints, new event consumers, role mapping changes, proxy/async/transaction changes, tenancy schema changes.

A service with multiple call paths especially needs a test proving "the decision remains correct when **there is no HTTP request**." This directly tests the core thesis of this lesson.

## 18. Exercises and Self-Check Questions

**Exercise 1 — Explain in one sentence.** Why doesn't `.requestMatchers("/api/orders/**").hasAuthority("ORDER_READ")` protect `OrderService.findById(...)` when a message consumer calls the method?

**Exercise 2 — Spot the BOLA.** Both Alice and Bob have `ORDER_READ`. `findById(101)` reads any order ID. Write a rule based on trusted `tenantId` and `ownerId`. If you only check `user.tenantId == order.tenantId`, what data exposure scenario remains?

**Exercise 3 — Find the proxy bug.** A `run()` method in `DocumentService` calls `this.delete(id)`, while `delete` has `@PreAuthorize("hasAuthority('DOCUMENT_DELETE')")`. Why is there a bypass risk? Replace the design with another service bean called through a proxy and write a test proving an unauthorized user is blocked.

**Exercise 4 — Direct-call test.** In the demo, add a test with `@WithMockUser(username="carol", authorities="DOCUMENT_READ")` calling `service.read(102)` directly. What is the expected result? Why is the call still denied even when HTTP filters do not run?

**Exercise 5 — Transaction layer.** A user is allowed to edit a record in `DRAFT` state, but the record changes to `LOCKED` after the check. Explain how to use a conditional update or optimistic locking to ensure the update does not happen when the state is no longer valid.

**Exercise 6 — Background job.** A report-export job needs to call a service protected by `@PreAuthorize`. How would you design a system principal so the job has only the `REPORT_EXPORT` permission within its allowed tenant, without using broad admin rights?

**Exercise 7 — API scope.** If the frontend hides the delete button for users lacking `DOCUMENT_DELETE`, can the backend omit the service check? Why or why not?

**Answer hints:**

- Exercise 1: Consumers invoke Java methods without passing through HTTP filters; policies must be enforced at the service/domain boundary.
- Exercise 2: Same tenant is insufficient if owner/collaborator access is required; use real resource data and specific policies.
- Exercise 3: Self-invocation bypasses the proxy in standard Spring AOP; call through a bean proxy or use explicit domain checks.
- Exercise 4: `AccessDeniedException`; the policy matches the record's tenant and owner against the principal.
- Exercise 5: Transaction and `WHERE id = ... AND status = 'DRAFT' AND tenant_id = ...` combined with appropriate version/row count checks.
- Exercise 6: Tenant-scoped system principal, least-privilege permissions, caller auditing; never assign ROLE_ADMIN arbitrarily.
- Exercise 7: No; clients can send HTTP requests directly and many callers do not go through the UI.

## 19. Summary and Official Documentation

HTTP rules know **which request** is entering the application; the service knows **which business operation** is executing and **which resource** is being processed. Placing authorization in the service ensures every valid caller passes through a clear, testable policy while HTTP filters continue providing early protection at ingress.

To protect properly in practice, you must satisfy four conditions simultaneously: **valid identity**, **valid permission**, **valid resource/tenant/owner**, and **correct enforcement point via proxy or domain boundary**. `@PreAuthorize` is a powerful tool, but it does not replace data-level constraints, transaction design, or testing actual call paths.

References:

- [Spring Security – Method Security, Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Test Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Framework – AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot 3.5.7 – Official Release Announcement](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now)
