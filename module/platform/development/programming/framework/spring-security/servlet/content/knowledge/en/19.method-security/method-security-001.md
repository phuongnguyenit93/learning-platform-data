# Why Service-Layer Protection Is Needed Alongside HTTP Rules in Spring Security Servlet

## Objectives

When building a Spring Security Servlet application, we usually start with HTTP rules:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
~~~

Those rules are essential: they control requests **passing through the corresponding SecurityFilterChain** before reaching Spring MVC. However, they are not enough to guarantee that every business operation is safe. The same method to read an invoice, change an order status, or view a document can be called from many places: a REST controller, an MVC page, a scheduled job, a message consumer, a GraphQL resolver, a batch worker, a new controller, or another service. URL rules do not automatically run on Java calls that do not go through the HTTP filter chain.

**Service-layer protection (service-layer authorization, method security)** brings access policy close to where actions are executed and data is retrieved. In Spring Security, we can enable @EnableMethodSecurity and then use @PreAuthorize, @PostAuthorize, and appropriate AuthorizationManager implementations on Spring-managed beans. More importantly, the policy must check permissions on the **actual data object**, not just whether the caller is "logged in" or "has role USER".

After this lesson, you will be able to:

1. Distinguish HTTP authorization from method/service authorization.
2. Explain why .authenticated() or a URL role rule does not automatically prevent unauthorized record access (IDOR/BOLA).
3. Identify entrypoints that do not go through controllers and the risks when adding new endpoints.
4. Understand @EnableMethodSecurity, @PreAuthorize, SpEL, Authentication, and AuthorizationManager.
5. Build a Java 17+, Spring Boot 3.x / Spring Security 6.x example with Spring MVC, H2, Spring Data JPA, and service-level ownership policy.
6. Test both HTTP requests using MockMvc and direct calls to the service bean.
7. Understand the limitations of Spring AOP proxies: self-invocation, final/private methods, manual bean instantiation, and async threads.
8. Combine service-level controls with database queries, transactions, tenant isolation, auditing, and the deny-by-default principle.

The context is **Spring Security Servlet**. Method security does not strictly depend on a Servlet request, so it itself helps protect certain non-web calls. Authentication sources and how SecurityContext propagates must be designed appropriately for each entrypoint; method annotations do not create a trustworthy identity on their own.

## 1. What Class of Problems Do HTTP Rules Solve?

A request from a browser typically follows this flow:

~~~text
HTTP client
    |
Servlet container
    |
Spring Security FilterChainProxy
    |
Selected SecurityFilterChain
    |
Authentication filters -> Authentication
    |
AuthorizationFilter / authorizeHttpRequests rules
    |
DispatcherServlet
    |
Controller
    |
Service
    |
Repository / Database
~~~

For example: .requestMatchers("/api/**").authenticated() ensures that a request has a valid Authentication when accessing a path matching the rule. However, it does **not** answer whether alice is allowed to read an invoice belonging to bob. For the URL GET /api/invoices/102, even though both alice and bob have role USER, only one of them is the owner of the invoice.

HTTP rules are useful for:

- Blocking anonymous requests early, before entering a controller.
- Granting access by URL and HTTP method, for example /admin/** requires ADMIN.
- Defining a policy covering all HTTP endpoints via .anyRequest().denyAll() or an appropriate rule.
- Combining with CSRF, session policy, authentication entrypoint, access denied handler, and security headers.
- Separating an API chain and a web chain for different authentication mechanisms.

However, HTTP matchers only operate **on requests passing through that chain**. They do not cover every call to a service bean. Furthermore, securityMatcher and requestMatchers are different: securityMatcher selects the scope of a SecurityFilterChain, while requestMatchers inside authorizeHttpRequests selects authorization rules within that chain.

### A Common Anti-Pattern

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll());
~~~

Controller:

~~~java
@GetMapping("/api/documents/{id}")
public DocumentDto document(@PathVariable Long id) {
    return documentService.read(id);
}
~~~

If documentService.read(id) only calls repository.findById(id) without checking owner/tenant/permission, then **any logged-in user** can try changing the id in the URL to view someone else's data. The HTTP layer is still "correct" according to the .authenticated() policy, but business authorization is missing.

This is an example of **Broken Object Level Authorization (BOLA)** or **Insecure Direct Object Reference (IDOR)**: the caller does not need to forge Authentication, only change a data identifier that the client is allowed to supply.

## 2. Why Do We Need a Second Layer of Protection?

Consider an application with a business service:

~~~text
             REST Controller ----\
             MVC Controller ------\
             Scheduled Job --------> DocumentService.read(documentId)
             Message Consumer -----/
             Another Service -----/
                                        |
                                   Repository / DB
~~~

When the policy lives only in the REST controller or SecurityFilterChain:

- A new controller might call the service and forget the same ownership rule.
- A batch worker might be granted overly broad permissions or use an uncontrolled system identity.
- A GraphQL resolver might not use the /api/documents/{id} route expected by the HTTP rule.
- Unit/integration tests calling the service bean directly might bypass security if the service is not protected.
- An internal endpoint added by another team might only check .authenticated(), creating a new entry path to the same data.

When the **service bean is protected with method security**, permission requirements are checked at the method invocation boundary via the Spring AOP proxy. Even if the HTTP controller only checks authentication, the read(documentId) call still enforces a policy close to the business logic. If a second controller calls the same proxied service, the policy is still applied.

The key point: **defense in depth** is not two identical lines of configuration. Each layer should protect what it knows best:

| Layer | Appropriate Decision |
| --- | --- |
| Servlet security chain | Which requests must be authenticated? Which coarse roles may call the endpoint? |
| Service/method | Is the caller allowed to perform this use case? Allowed to view/modify data with this ID? |
| Repository/SQL | Only retrieve rows belonging to the verified owner/tenant; handle concurrency |
| Database | Constraints, transactions, row-level security when supported by the DBMS and architecture |
| Audit/observability | Who performed which action; do not expose tokens or private data |

One layer failing does not mean the remaining layers will always save the system. For example, calling a helper directly within the same bean can bypass method security proxies; therefore critical policies also require query scoping, clear architecture, and tests.

## 3. Specific Scenarios Where HTTP-Only Is Not Enough

### 3.1. Changing the ID in the URL

Alice has a valid account and tries:

~~~text
GET /api/documents/101   -> alice's document
GET /api/documents/102   -> bob's document
~~~

With .authenticated(), both requests can pass the HTTP layer. The service must ask **who owns document 102**, whether the caller has permission via tenant/sharing, and whether they hold valid admin privileges.

### 3.2. Endpoints Added Later

Initially there is only:

~~~text
GET /api/documents/{id} -> DocumentService.read(id)
~~~

Later a developer adds:

~~~text
GET /internal/export/{id} -> DocumentService.read(id)
~~~

If the developer only checks the new endpoint with a simple role, ownership is forgotten. With @PreAuthorize protecting read() on the service, the new controller must still satisfy the policy when calling the method through the proxy.

### 3.3. Non-HTTP Work

A @Scheduled job or message listener has no browser HttpServletRequest/Authentication. HTTP authorization **does not run** when it calls DocumentService directly. Method security can protect the service, but the job must have an explicitly designed principal or use a dedicated API for system tasks. Do not "fix" this by stuffing ROLE_ADMIN into SecurityContextHolder for every background job.

### 3.4. Multi-Entrypoint APIs

An application has REST, GraphQL, and websocket handlers; each has different authentication/authorization points. If critical business logic is protected at the service, the policy can be reused, but you must consider **context propagation** and how each entrypoint authenticates. Never assume the right SecurityContext is present on every thread.

### 3.5. Permissions Depending on Data State

For example, order management: the owner may edit only when status is DRAFT; an operator may approve only when authorized and status is SUBMITTED. An HTTP rule hasRole('USER') does not know record state or owner relationships. This is an **object- and state-level** policy, which should live near the use case/transaction where the data is read.

## 4. Enabling Method Security in Spring Security 6

Since Spring Security 6, use:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

This configuration requires importing org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity and org.springframework.context.annotation.Configuration. Do not assume that adding the Spring Security dependency or declaring a SecurityFilterChain will **automatically enable** @PreAuthorize; method security must be explicitly enabled.

Once enabled:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportAll() {
        return "protected report";
    }
}
~~~

When the Spring-managed bean ReportService is called **through a Spring proxy**, Spring Security evaluates the expression **before** running the method body. For an unauthorized user, AccessDeniedException is thrown and the method body is not executed.

Key concepts:

- **@PreAuthorize:** checks before invoking the method, used when the decision can be made from Authentication and parameters.
- **@PostAuthorize:** checks after the method has run, and can use returnObject. Useful in some situations, though it may consume resources or cause side effects before denying.
- **@PreFilter / @PostFilter:** filters collections/arrays/streams as supported by Spring Security; performance and already-loaded data must be considered.
- **Authentication:** the verified identity and authorities according to the mechanism in use.
- **SpEL:** security expressions such as hasRole('ADMIN') or @documentPolicy.canRead(#documentId, authentication).
- **AuthorizationManager:** the abstraction that decides allow/deny; managers can be used directly in HTTP and method security across different contexts.

Each API has its own scope and evaluation timing. **@PreAuthorize does not automatically check ownership** if your expression is just isAuthenticated().

### Method Parameters in SpEL

If you want to use #documentId, Spring must determine the method parameter name. You can use the compiler with -parameters or Spring Security's supporting annotation. To keep the example explicit, we use:

~~~java
@PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
public DocumentDto read(@P("documentId") Long documentId) {
    // ...
}
~~~

Here @P is org.springframework.security.access.method.P, which specifies the parameter name for expression evaluation. Do not assume #documentId will always have a value if you do not use -parameters, @P, or a compatible discovery mechanism. In actual source code there must be a bean named documentPolicy.

## 5. Why Record-Level Permissions Often Require Querying Data

The USER role is only an attribute of the caller; it does not tell you who owns a document:

~~~text
Authentication:
  name = alice
  authorities = [ROLE_USER]

Document 101:
  ownerUsername = alice
  title = Alice notes

Document 102:
  ownerUsername = bob
  title = Bob plans
~~~

Simple owner rule:

~~~text
Allow reading document if:
  (document.ownerUsername == authentication.name)
  OR caller has ROLE_ADMIN

Allow editing title if:
  document.ownerUsername == authentication.name
  (in this example, ADMIN does not automatically have edit permission)
~~~

This is a **business rule chosen for this lesson**, not a Spring Security default policy. In real applications, permissions may depend on tenant ID, ACLs, groups, data classification, timing, order state, and sharing agreements.

Do not use an ownerUsername value sent by the client in the JSON body to evaluate permissions; an attacker could send ownerUsername=alice in bob's request. The policy must fetch the owner from the **database or a trusted source of truth**, and the caller from the verified Authentication.

**Do not treat an ID in the URL as a secret**. Even if it is a hard-to-guess UUID, the document still needs authorization when accessed. An unguessable ID can still leak via logs, shared URLs, or frontend bugs.

## 6. Complete Example: Java 17, Spring Boot, Spring Security, and H2

We build a Spring MVC application with:

- GET /api/documents/{documentId}: HTTP only requires authenticated; the service checks owner or ADMIN.
- PUT /api/documents/{documentId}: HTTP only requires authenticated; the service only allows the **owner** to change the title.
- Two accounts alice, bob, and an admin account, using encoded passwords.
- An H2 in-memory database with document 101 belonging to alice and 102 belonging to bob.
- @EnableMethodSecurity activating @PreAuthorize at the service layer.
- @Component("documentPolicy") looking up the owner from the database.
- To illustrate defense-in-depth, **the service also scopes the data query by owner in the regular-user branch**, reducing risk if the policy is called down the wrong path.
- MockMvc HTTP tests and direct tests against the proxied DocumentService.

The example uses Java 17+, Spring Boot 3.3.5, and Spring Security 6.x via dependency management. Do not use demo users/passwords in production.

### 6.1. Project Structure

~~~text
service-authorization-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (if the Gradle Wrapper has been generated)
  src/main/java/dev/example/serviceauth/
    ServiceAuthorizationApplication.java
    SecurityConfig.java
    DocumentEntity.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/dev/example/serviceauth/
    DocumentAuthorizationIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'service-authorization-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot automatically configures the in-memory H2 datasource and Hibernate DDL for the embedded DB suitable for a demo project; there is no need to put a database password in source code. For a real database, a migration tool such as Flyway/Liquibase, transactions, and proper infrastructure secret protection are required.

### 6.2. Main and Seed Data

File src/main/java/dev/example/serviceauth/ServiceAuthorizationApplication.java:

~~~java
package dev.example.serviceauth;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceAuthorizationApplication.class, args);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            if (!repository.existsById(101L)) {
                repository.save(
                        new DocumentEntity(101L, "alice", "Alice notes"));
            }
            if (!repository.existsById(102L)) {
                repository.save(
                        new DocumentEntity(102L, "bob", "Bob plans"));
            }
        };
    }
}
~~~

Fixed IDs make test results deterministic. With in-memory H2, data lives for the application's lifecycle and must not be used as a durable document store. In production, do not seed users/documents using this demo approach.

### 6.3. Entity and Repository

File src/main/java/dev/example/serviceauth/DocumentEntity.java:

~~~java
package dev.example.serviceauth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "demo_documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected DocumentEntity() {
    }

    public DocumentEntity(Long id, String ownerUsername, String title) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

File src/main/java/dev/example/serviceauth/DocumentRepository.java:

~~~java
package dev.example.serviceauth;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    boolean existsByIdAndOwnerUsername(
            Long id, String ownerUsername);

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);
}
~~~

Spring Data JPA derives queries from method names based on entity property names. findByIdAndOwnerUsername helps restrict returned data to the owner. The repository does not inherently trust identity; **the caller must pass ownerUsername from an authenticated Authentication**, not from an uncontrolled request body/URL.

To avoid over-relying on usernames that may change, production systems should typically store a stable ownerUserId/tenantId and map the principal to that ID.

### 6.4. SecurityConfig: HTTP Layer and Enabling Method Security

File src/main/java/dev/example/serviceauth/SecurityConfig.java:

~~~java
package dev.example.serviceauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents/*")
                        .authenticated()
                        .requestMatchers(
                                HttpMethod.PUT, "/api/documents/*")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

At the HTTP layer, only authentication is required for matching GET/PUT URLs. This is an intentional choice to illustrate service-level ownership, **not** a recommendation that an entire API only needs authenticated().

Because CSRF is not disabled, PUT requests in tests require a valid CSRF token. When browser cookies/sessions are present, CSRF is an essential concern independent of method security. For a genuinely stateless bearer-token API, the CSRF policy may differ, but it must be evaluated based on the credential-bearing mechanism rather than disabling it arbitrarily.

Method security is enabled with @EnableMethodSecurity. Every call through the Spring proxy of DocumentService to public methods annotated with @PreAuthorize is checked, including calls that do not originate from an MVC controller.

### 6.5. Object-Level Permission Check Component

File src/main/java/dev/example/serviceauth/DocumentPolicy.java:

~~~java
package dev.example.serviceauth;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Long documentId, Authentication authentication) {
        if (!isRealUser(authentication) || documentId == null) {
            return false;
        }

        if (hasAdminRole(authentication)) {
            return repository.existsById(documentId);
        }

        return repository.existsByIdAndOwnerUsername(
                documentId, authentication.getName());
    }

    public boolean canWrite(Long documentId, Authentication authentication) {
        return isRealUser(authentication)
                && documentId != null
                && repository.existsByIdAndOwnerUsername(
                        documentId, authentication.getName());
    }

    public boolean hasAdminRole(Authentication authentication) {
        return isRealUser(authentication)
                && authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Key takeaways:

1. **The policy takes documentId from the method parameter but retrieves the owner from the database.**
2. authentication.getName() is verified by Spring Security via HTTP Basic in the demo, not from a client-supplied owner query parameter.
3. canRead allows the owner or role ADMIN; canWrite allows only the owner. That is a sample policy; do not assume admin always has all permissions.
4. If documentId is null or Authentication is absent, the policy **denies**, never defaulting to permit.
5. Checking AnonymousAuthenticationToken is necessary because isAuthenticated() on an anonymous token is not proof that a real user logged in.
6. Checking ROLE_ADMIN relies on the actual authority; the role prefix must be consistent with the identity system.
7. The policy only checks before the method executes. **Data conditions can change** between existsBy... and reading the record; transaction/race issues will be analyzed in section 10.

In real products, do not use username as a global owner key if multiple tenants exist. Use a stable subject/userId, tenant boundaries, and sharing permissions backed by a trusted data source.

### 6.6. DocumentService: Method Security Conditions and Scoped Queries

File src/main/java/dev/example/serviceauth/DocumentService.java:

~~~java
package dev.example.serviceauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    public DocumentService(
            DocumentRepository repository, DocumentPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
    @Transactional(readOnly = true)
    public DocumentView read(@P("documentId") Long documentId) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        DocumentEntity doc = visibleToCurrentUser(
                documentId, authentication);
        return asView(doc);
    }

    @PreAuthorize("@documentPolicy.canWrite(#documentId, authentication)")
    @Transactional
    public DocumentView rename(
            @P("documentId") Long documentId, String newTitle) {

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) {
            throw new AccessDeniedException("No authenticated caller");
        }

        DocumentEntity doc =
                repository.findByIdAndOwnerUsername(
                        documentId, authentication.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));

        doc.rename(newTitle.trim());
        return asView(doc);
    }

    private DocumentEntity visibleToCurrentUser(
            Long documentId, Authentication authentication) {

        if (authentication == null) {
            throw new AccessDeniedException("No authenticated caller");
        }

        if (policy.hasAdminRole(authentication)) {
            return repository.findById(documentId)
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        }

        return repository.findByIdAndOwnerUsername(
                        documentId, authentication.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));
    }

    private static DocumentView asView(DocumentEntity doc) {
        return new DocumentView(
                doc.getId(), doc.getOwnerUsername(), doc.getTitle());
    }

    public record DocumentView(
            Long id, String ownerUsername, String title) {
    }
}
~~~

Notes:

- @PreAuthorize checks permissions at the point of calling the method through the proxy, **before the body runs**.
- @P("documentId") provides a stable parameter name for the #documentId expression.
- @Transactional places JPA operations within a transaction when the method executes.
- read uses the owner condition in the **actual query**, except for admin who is allowed to view existing documents. This is an extra layer of protection if the service policy is called improperly.
- rename only queries records matching the caller's ownerUsername; it does not accept ownerUsername from the client.
- The entity is managed within the transaction; when title changes, Hibernate JPA dirty checking persists the change at transaction commit.
- The DocumentView record is a Java 17 type for returning simple data, avoiding exposing the JPA entity directly in the response.
- The non-existent/non-owned branch throws AccessDeniedException to avoid confirming the existence of someone else's ID; a specific policy may decide on 404 instead of 403 if the API contract requires it.
- The EnableMethodSecurity import in this file is unused; it can be removed when cleaning up in an IDE and does not affect Java compilation.
- The demo has no multi-tenancy or complex permission sharing; the same principles must be applied with real data keys.

**Important:** Using @Transactional alongside @PreAuthorize does not automatically make the permission check and update **strictly atomic**. Especially if the owner, tenant, or state can be modified concurrently by another transaction, you need locking, a version column, conditional update queries, or appropriate transaction isolation. Do not claim "having the annotations prevents all race conditions".

### 6.7. MVC Controller: Thin, Not Deciding Ownership Instead of the Service

File src/main/java/dev/example/serviceauth/DocumentController.java:

~~~java
package dev.example.serviceauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable Long documentId) {
        return service.read(documentId);
    }

    @PutMapping("/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable Long documentId,
            @RequestBody RenameRequest request) {
        return service.rename(documentId, request.title());
    }

    public record RenameRequest(String title) {
    }
}
~~~

The controller only receives the identifier and body and delegates the work to the service bean injected by Spring via constructor. It does not need to call policy.canRead(...) manually every time because the service already enforces the policy at the method entry point, yet **HTTP rules are still kept** to block anonymous/disallowed URLs early.

This example does not add a separate method to bypass the service. In a real application, every controller/resolver must go through the same protected service entrypoint, rather than calling the repository directly and sending data back to the client.

### 6.8. Running the Application

Create the project with the exact structure and Gradle Wrapper, then run:

~~~bash
./gradlew bootRun
~~~

On PowerShell/Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Once Boot is running on localhost:8080, try GET:

~~~bash
curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u bob:bob-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u admin:admin-demo-pass \
  http://localhost:8080/api/documents/101

curl -i http://localhost:8080/api/documents/101
~~~

Typical results:

| Request | Expected Result |
| --- | --- |
| alice reads document 101 | 200, JSON with id=101 and ownerUsername=alice |
| bob reads document 101 | 403, does not return alice's content |
| admin reads document 101 | 200 per the ADMIN branch in canRead |
| anonymous reads document 101 | 401 per HTTP Basic |
| alice reads bob's document 102 | 403 |
| bob edits alice's document 101 | 403 (with PUT and valid CSRF, service denies permission) |
| alice edits document 101 | 200 when PUT has valid JSON and configured CSRF token |

Do not confuse a 403 error from CSRF with an ownership error. With HTTP Basic and default CSRF, a curl PUT command without a CSRF token may be rejected by CsrfFilter **before** DocumentService runs. Therefore the test suite uses spring-security-test csrf() to isolate the service policy. When deploying a purely stateless bearer-token API, CSRF must be evaluated separately based on the authentication mechanism; do not copy a disable(csrf) snippet mechanically.

## 7. Testing: Passing HTTP Is Not Enough, Call the Service Directly

File src/test/java/dev/example/serviceauth/DocumentAuthorizationIntegrationTest.java:

~~~java
package dev.example.serviceauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void ownerCanReadOwnDocumentThroughHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.ownerUsername").value("alice"));
    }

    @Test
    void otherUserCannotReadDocumentThroughHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadByExplicitBusinessPolicy() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void anonymousMustAuthenticateFirst() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userCannotModifySomeoneElsesDocument() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Unauthorized change\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameWithValidCsrf() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated Alice title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                        .value("Updated Alice title"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .contentType("application/json")
                        .content("{\"title\":\"No CSRF\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void proxiedServiceRejectsDirectCallFromNonOwner() {
        assertThatThrownBy(() -> service.read(101L))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void proxiedServiceAllowsDirectCallFromOwner() {
        service.read(101L);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCannotWriteByAccident() {
        assertThatThrownBy(() -> service.rename(
                101L, "Not authorized"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The most important tests for this lesson:

- HTTP request from bob to ID 101 gets 403, even though bob passed the .authenticated() rule in SecurityFilterChain.
- **Direct call** to DocumentService.read(101L) from a test with @WithMockUser bob also throws AccessDeniedException. No HTTP request, controller, or URL matcher is involved; this proves method security resides at the service entrypoint.
- alice and admin are granted read access under two policy branches; admin does not implicitly have write access.
- PUT with valid CSRF allows evaluating the service permission, avoiding mistaking CsrfFilter for an ownership guard.

Because a test modifies the title of record 101, if you want to test the initial title value across multiple tests, reset the data or use independent transactions/fixtures. The assertions here focus on id/owner instead of assuming test execution order.

This is a sample test suite for a default Boot/H2 project. When using a real database, you can add integration tests with Testcontainers to verify query scoping, tenant boundaries, transaction isolation, and indexes. Do not claim that a purely mocked unit test suite proves production data safety.

## 8. Why Not Put @PreAuthorize Only on the Controller?

A controller can use @PreAuthorize to block requests:

~~~java
@PreAuthorize("hasRole('ADMIN')")
@GetMapping("/admin/report")
public Report report() {
    return reportService.create();
}
~~~

This is useful for protecting the controller method, but reportService.create() can still be called from elsewhere without going through the controller. If a use case is meant only for ADMIN regardless of entrypoint, that policy should be expressed at the **service boundary** or in a domain authorization layer used by all entrypoints.

It is not necessary to remove all annotations from controllers. You can use:

- HTTP rules for authentication requirements and coarse roles;
- Controller-level @PreAuthorize when an endpoint has transport/contract-specific requirements;
- Service-level @PreAuthorize to protect shared business logic;
- Repository query scoping/transactions for real data.

What matters is having **a clear source of truth for business permissions**, avoiding duplicating two ACL expressions that may drift over time.

### Is Checking Only a Role at the Service Enough?

For example:

~~~java
@PreAuthorize("hasRole('USER')")
public DocumentDto read(Long documentId) {
    return repository.findById(documentId)
            .map(this::toDto)
            .orElseThrow();
}
~~~

If both alice and bob have ROLE_USER, this annotation does not prevent alice from reading bob's record. You need **record-level authorization**, such as checking ownerId, tenantId, sharing permissions, or a policy service as in the demo.

### Is Passing ownerUsername From the Controller Trustworthy?

You should not write:

~~~java
@PreAuthorize("#ownerUsername == authentication.name")
public DocumentDto read(Long documentId, String ownerUsername) {
    return repository.findById(documentId)
            .map(this::toDto)
            .orElseThrow();
}
~~~

if ownerUsername here is passed by the client and has not been verified against the database. An attacker can call read(102, "alice") while logged in as alice and pass the expression, even though record 102 belongs to bob. **Comparing the caller to a self-declared parameter is not object ownership verification.**

## 9. Method Security Works via Spring AOP Proxies: Limitations to Know

Spring Security method security defaults to method interception based on Spring AOP proxies. This brings policy reuse benefits, but you need to understand **how calls pass through the proxy**.

### 9.1. Self-Invocation Does Not Go Through the Proxy

For example:

~~~java
@Service
public class DemoService {

    public String outer() {
        return inner(); // Direct call on this, typically bypasses the proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String inner() {
        return "sensitive";
    }
}
~~~

If a caller invokes demoService.outer() through the proxy, outer itself has no rule, while the call to inner() via this.inner() occurs inside the bean and **usually does not go through the AOP proxy**. Therefore @PreAuthorize on inner may not be enforced for this call path.

This is one of the biggest risks when thinking "putting an annotation on a method automatically secures every call path".

Preferred solutions:

1. Place the policy on the **public entrypoint** that callers actually invoke.
2. Extract the secured use case into a separate bean/service and inject that bean so callers go through the proxy.
3. Avoid instantiating services with new instead of obtaining them from the Spring container.
4. Write tests exercising the real path through the Spring bean, not just calling the method on a plain object.
5. When using AspectJ weaving instead of AOP proxies, semantics may differ, but that is a separate architectural configuration requiring testing.

### 9.2. Private, Final, and Proxy Strategy

Private methods are not public join points commonly intercepted by Spring AOP proxies. Final methods or final classes may not be proxied under subclassing strategies (CGLIB); interface proxies have their own limitations. With Kotlin, you typically must account for classes/methods being final by default. Do not place the **sole rule** protecting data on a private helper and expect Spring Security to intercept every call.

Keep business services with clear public methods and proper Spring beans; use tests calling the bean directly through the container to prove annotations are applied.

### 9.3. @Transactional and @PreAuthorize Are Not the Same

Both annotations may be backed by proxies/advisors, but they have different responsibilities:

- @PreAuthorize decides who is allowed to execute the method.
- @Transactional manages transactions when the method is called through an appropriate proxy.
- Neither annotation replaces database constraints or business-data concurrency checks.

Advisor ordering and transaction scope can vary by configuration; do not assume the policy check and update happen as one atomic operation just because they are on the same method. For sensitive operations, consider conditional update queries checking owner/tenant/state, optimistic locking (@Version), pessimistic locks, or RDBMS row-level security depending on the threat model.

### 9.4. @Async, New Threads, and Message Handlers

SecurityContextHolder typically uses a ThreadLocal strategy. When switching to @Async or spawning another thread, the HTTP request's Authentication does **not automatically** appear in the new thread safely. You can use DelegatingSecurityContextAsyncTaskExecutor or corresponding propagation components, but you must understand which principal is propagated and the context lifecycle.

Do not pass broad ADMIN privileges to a background job just to bypass @PreAuthorize. A system job should have a **service identity** with explicit permissions, separate auditing, and operate through controlled entrypoints. If a job acts on behalf of a user, design bounded and audited delegation/impersonation.

### 9.5. Method Security Exceptions Outside HTTP

When @PreAuthorize denies access, Spring Security typically throws AccessDeniedException or a related exception. In an HTTP request, ExceptionTranslationFilter together with an appropriate handler/entrypoint can turn it into 401/403/redirect. In a scheduled job or message listener, **there is no Servlet response**: exceptions must be handled according to job/message semantics (retry, dead-letter, alert, fail closed).

Do not catch AccessDeniedException and "let it pass" or fall back to returning all data just to avoid UI errors. If returning 404 is needed to hide resource existence, that is an API contract decision backed by risk analysis, not skipping the check.

## 10. When Permission Checks Depend on Mutable Data: Timing Issues

Consider the following scenario:

~~~text
T1: DocumentPolicy.existsByIdAndOwnerUsername(101, "alice") => true
T2: Another transaction changes the owner of 101 to bob
T3: DocumentService.read(101) reads the new content
~~~

If step T3 calls repository.findById without restricting the owner and without rechecking, alice may see data in a state where ownership has already changed. From a transaction perspective, this is **time-of-check to time-of-use (TOCTOU)** or an authorization race.

The demo uses findByIdAndOwnerUsername in the service for regular users to increase defense, but under different isolation levels and concurrency strategies you still need to analyze transaction boundaries. For ownership transfers, money transfers, approvals, or sensitive updates, use:

- Direct queries with owner/tenant conditions attached:
  
~~~sql
SELECT id, owner_username, title
FROM demo_documents
WHERE id = :id
  AND owner_username = :authenticated_username;
~~~

- Conditional UPDATE instead of load-then-check-then-update in flows requiring atomicity:

~~~sql
UPDATE demo_documents
SET title = :new_title
WHERE id = :id
  AND owner_username = :authenticated_username;
~~~

- Locks/versioning to prevent lost updates, and verify the number of updated rows.
- For multi-tenancy, include tenant_id in every query and add appropriate indexes.
- Clearly define admin rights, shared access, revoked access, and object state at **execution time**.

In the SQL snippets, :authenticated_username must come from the verified SecurityContext/identity provider; do not use request.queryParam("owner"). If database row-level security is enabled, the session/database principal and SQL policies must also be managed properly; do not assume RLS is enabled automatically by a Java annotation.

### Why Is @PostAuthorize Sometimes Less Suitable?

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentDto load(Long id) {
    return repository.findById(id).map(this::toDto)
            .orElseThrow();
}
~~~

The load method has already executed and loaded data **before** post-authorization denies it. It may fit some read-only use cases, but for methods with side effects, checking after writing is too late; for large collections, loading too much data beforehand and then filtering is also inefficient.

Prefer @PreAuthorize when sufficient information exists to decide permissions before the method, combined with repository query scoping. When you must rely on returnObject, understand transactions/side effects, exceptions, and the risk of data leaking through logs/caches. Do not return sensitive entities externally before they are authorized.

## 11. Tenant Isolation and Object-Level Permissions

In multi-tenant SaaS, comparing usernames alone is usually insufficient. For example, two tenants may both have an account named "alice". A document with ownerUsername=alice does not state which tenant it belongs to. Real-world policies should rely on **stable IDs** for users and tenants:

~~~text
Caller: userId=U1, tenantId=T1
Document 501: ownerUserId=U1, tenantId=T1 => usually allowed
Document 502: ownerUserId=U1, tenantId=T2 => must check tenant boundary
Document 503: ownerUserId=U2, tenantId=T1 => depends on sharing/role
~~~

Do not take tenantId from an arbitrary request header and let it override the tenant of the verified principal. If users are allowed to switch tenants, there must be a selection mechanism that validates membership and roles/permissions for the chosen tenant.

In services/repositories, use verified parameters and conditional queries. If the app uses Hibernate filters, global query predicates, or RLS, check that all code paths (native SQL, batch, async, admin) obey the policy; never blindly trust a framework interceptor completely.

For object-level sharing, policies may need to check ACLs/permissions in the database. Avoid loading private data too early or populating a shared cache without partitioning by principal/tenant.

## 12. Unusual APIs and Uncovered HTTP Route Cases

### 12.1. URL Changes or Multiple SecurityFilterChains

If a controller moves from /api/documents/** to /v2/documents/** without updating the security config, HTTP authorization may apply a different rule. A service method that still has a protective annotation will preserve the ownership policy, but that does not mean the new endpoint is automatically safe in every aspect (CSRF, authentication entrypoint, header policy).

When using multiple SecurityFilterChains, FilterChainProxy picks the **first chain** matching the request; a rule in chain A does not protect a request handled by chain B. Therefore you must test both HTTP chain selection and method security.

### 12.2. A Controller Calling a Repository Directly

~~~java
@GetMapping("/debug/documents/{id}")
public DocumentEntity debug(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

If a controller calls the repository **without going through DocumentService**, @PreAuthorize on the service does not run. Service-layer protection is effective when the architecture is consistent: data access paths must go through protected use cases/services, and sensitive data queries also need query scoping/RLS.

Do not claim "simply annotating one service makes all controllers automatically safe". Audit repository injections in controllers, batch exports, administrative backdoors, and bypass code paths.

### 12.3. Method Security Does Not Solve All Access Control Problems

A service that lets users read documents by owner can still suffer from:

- Mass assignment: the client can modify ownerUserId or tenantId due to uncontrolled field binding.
- Data leakage in logs/errors/cache/tracing.
- Unsafe object deserialization or SQL injection in repositories.
- Private data appearing on another endpoint that does not go through the service.
- BOLA in list/search operations due to queries not filtering by the right tenant.
- Broken function-level authorization: a role is allowed to read but not delete/approve.
- CSRF/clickjacking/session fixation belonging to other web protection layers.
- Privilege escalation via background service accounts or trusted-header configuration.

Method security is an important layer of **access-control architecture**, not a replacement for all security controls.

## 13. Troubleshooting Guide When Method Security "Does Not Work"

### Issue 1 — Forgetting @EnableMethodSecurity

Symptom: @PreAuthorize is on the method, yet unauthorized requests still execute. Cause: method security is not enabled, or the config is not loaded into the application context. Fix: add @EnableMethodSecurity on the appropriate @Configuration class, and test the real Spring-managed service bean directly.

### Issue 2 — Creating the Service with new

~~~java
DocumentService service = new DocumentService(repository, policy);
~~~

This code instantiates a plain Java object manually and **does not go through the Spring AOP proxy**. The @PreAuthorize annotation is not intercepted as it is on an @Autowired bean. In the sample application, the controller receives DocumentService via constructor injection from Spring.

### Issue 3 — Self-Invocation Inside the Same Bean

A public method calling another method via this.inner() can bypass the security proxy. Extract the protected operation into a separate bean or move the rule to the public entrypoint, and test the real call path.

### Issue 4 — @PreAuthorize Only Uses hasRole('USER')

The USER role does not verify owner or tenant. Add a policy checking the object from the DB and the verified principal. Test with another user's ID, not only the same user.

### Issue 5 — Wrong Parameter Name in SpEL

#documentId is null or expression evaluation fails when -parameters/@P metadata is missing. Use @P("documentId"), and test calling the service directly with concrete IDs and authentication.

### Issue 6 — Wrong Role Prefix

User.withUsername(...).roles("ADMIN") creates ROLE_ADMIN; hasRole('ADMIN') typically checks ROLE_ADMIN. If the app uses authorities without a prefix, expressions and mappings must be consistent. Do not fix it by removing the role check.

### Issue 7 — Only Testing the Controller with a Mock Service

If @WebMvcTest uses @MockBean DocumentService and does not test the real service, HTTP tests can pass without running method authorization at all. Add @SpringBootTest + real DocumentService or a focused method-security integration test.

### Issue 8 — Data Ownership Changes Between Check and Use

A policy checking existsBy... first and querying later can hit a race if another transaction changes the owner. Combine owner-scoped queries, conditional updates, versioning/locks, and transaction design.

### Issue 9 — @Async Does Not See Authentication

New threads do not receive the ThreadLocal context like request threads do. Controlled propagation or a dedicated service identity is required; do not blindly grant broad permissions to avoid exceptions.

### Issue 10 — User Data Exposed on Another Path

The service is protected, but a controller uses the repository directly or a batch export bypasses it. Audit all entrypoints, module boundaries, query scoping, and run negative tests across multiple entry paths.

### Issue 11 — Swallowing AccessDeniedException

A catch (Exception e) returning a default document or retrying under ADMIN can bypass the policy. Never turn access denied into "allow"; return an error appropriate for the entrypoint and record safe audit logs.

### Issue 12 — Using ownerUsername from Request JSON

The client can forge ownerUsername. Retrieve the document's owner from the DB and the verified identity from Authentication; never compare two strings both supplied by the client.

### Issue 13 — Over-Reliance on @PostAuthorize on Methods with Side Effects

Checking permissions after the method runs does not automatically undo side effects. Use pre-authorization or appropriate validation/transactions/compensating actions; do not post-filter sensitive data after it has already been serialized/returned.

### Issue 14 — Authorization in Both HTTP and Service Causes Confusing Status Codes

If the HTTP rule denies first, the service never runs. If HTTP lets it through and @PreAuthorize denies, web security handles the exception as 403/challenge depending on Authentication. Do not rely solely on status code to infer which layer rejected; use tests and telemetry without leaking secrets.

## 14. Production Checklist for Service-Level Authorization

1. **Identify sensitive use cases:** view, edit, delete, export data, transfer ownership, approve, access PII.
2. **Define HTTP rules:** coarse method/path/role, authentication entry point, deny-by-default, and multiple SecurityFilterChains.
3. **Enable @EnableMethodSecurity** and test annotations on real Spring-managed service beans.
4. **Write policies by object/tenant/permission**, not just authenticated or role USER.
5. **Never trust self-declared ID/owner/tenant** in URL, query, header, or body as the sole basis for granting access.
6. **Choose a stable principal ID**, mapping JWT subject/email/username accurately per the identity provider.
7. **Ensure all entrypoints go through protected services:** REST, MVC, GraphQL, background jobs, messages, new controllers.
8. **Prevent proxy bypasses:** no manual new of protected beans, no blind self-invocation, no sole policies on private/final methods.
9. **Combine query scoping/transactions** and DB constraints to protect objects against IDOR and races.
10. **Use @PreAuthorize at the right time**, carefully evaluating @PostAuthorize/@PostFilter when data is large or side effects exist.
11. **Design job/system identity permissions** and safe context propagation for async execution.
12. **Test positive and negative cases:** owner, other user, admin, anonymous, other tenant, non-existent document, revoked permission.
13. **Test both layers:** MockMvc on HTTP endpoints and direct calls to service beans from the Spring context.
14. **Instrument and audit:** who was denied, which resource class; do not log passwords, tokens, cookies, or secrets.
15. **Audit bypass paths:** controllers calling repositories directly, exports, scheduled tasks, caches, and native queries.
16. **Regression check after framework upgrades:** verify @EnableMethodSecurity, SpEL parameter binding, proxy/AOP behavior, SecurityFilterChain, and exception mapping.
17. **Least privilege:** service accounts do not default to ADMIN; admins may read without necessarily being allowed to edit.
18. **Control transactions and update permissions:** concurrent owner/state changes must enforce policy at operation time.
19. **Do not rely on HTTP status alone** to determine which layer handled the request; use test traces and business invariants.
20. **Document policies near the code** and conduct periodic security reviews when adding features or endpoints.

## 15. Self-Check Questions

**Question 1.** If the URL /api/documents/** only requires .authenticated(), is user alice automatically allowed to view bob's document?

**Answer:** The HTTP rule only requires login; it does not check ownership. If the service lacks protection, alice can read bob's data by changing the ID. Object-level authorization is required.

**Question 2.** Why is @PreAuthorize on DocumentService helpful when a new controller is added?

**Answer:** If the new controller calls the service bean through the Spring proxy, the service policy is still evaluated, even if the new controller does not repeat the ownership logic.

**Question 3.** Is @EnableMethodSecurity enabled automatically when configuring SecurityFilterChain?

**Answer:** Do not assume so. Method security must be explicitly enabled in config; test annotations on a real bean to verify.

**Question 4.** Is @PreAuthorize("hasRole('USER')") sufficient to prevent IDOR?

**Answer:** No. Many users share role USER, yet permissions on individual records can differ; you must verify owner/tenant/permission.

**Question 5.** If this.securedMethod() is called from within the same bean, does the annotation always run?

**Answer:** No. Internal calls typically bypass the Spring AOP proxy. Place the rule on a public entrypoint or extract the protected operation into an injected bean.

**Question 6.** Why do tests using @WithMockUser to call the service directly provide distinct value compared to MockMvc?

**Answer:** They prove method-level authorization is independent of HTTP URLs and controllers. If only MockMvc passes, an HTTP rule might have blocked the request while the service itself remained unprotected.

**Question 7.** If the client sends ownerUsername="alice" in JSON, can the service rely on it to verify ownership?

**Answer:** No. The client controls the body, so you must fetch the real owner from the database and the caller from the verified Authentication.

**Question 8.** Is @PostAuthorize suitable for controlling a money-transfer method?

**Answer:** Usually unsuitable as the sole check, because the method causes side effects before permissions are evaluated; pre-checks, transactions, and database constraints are required.

**Question 9.** Is it enough if canRead checks ownership with existsBy... and then calls findById afterward?

**Answer:** You must consider races: ownership can change between the two steps. Combine owner-scoped queries, transaction/isolation, or locking according to business security requirements.

**Question 10.** A service method is called from a @Scheduled job with no HTTP request. Where does SecurityContext come from?

**Answer:** The job needs an explicit service identity/delegation model. There is no HTTP SecurityFilterChain creating Authentication automatically; async/thread contexts also require propagation or a dedicated identity.

**Question 11.** Why can having the same username across two tenants cause a policy failure?

**Answer:** Username is not necessarily a globally unique identifier. You need stable userId and tenantId from trusted sources, checking both in business queries/policies.

**Question 12.** What happens if a controller calls the repository directly instead of a service annotated with @PreAuthorize?

**Answer:** Method security on the service does not run. You need a consistent entrypoint architecture, restricted bypass paths, and supplementary database/query scoping.

## Conclusion

**HTTP authorization protects the web entry gate; service-layer authorization protects business use cases and data where multiple call paths converge.** The two layers do not duplicate roles. HTTP rules stop anonymous callers and invalid methods/URLs early. Method security ensures **who may read/modify a specific object**, even when the service is called from another controller or a non-HTTP entrypoint.

In Spring Security Servlet, use **@EnableMethodSecurity + @PreAuthorize** on public service methods called through Spring proxies, applying policies based on trusted Authentication and ownership/tenant data from the database. Combine owner-scoped queries, transactions, and direct bean tests to avoid the illusion that "presence of an annotation means security is sufficient".

A solid design does not ask only "is the request logged in?", but also **"is this principal, in this context, allowed to perform this action on this exact piece of data?"**.