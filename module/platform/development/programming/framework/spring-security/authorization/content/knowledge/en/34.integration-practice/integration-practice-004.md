# Checking Ownership with @PreAuthorize and a Policy Bean

## 1. Real-World Problem and Objectives

A Spring Security application exposes **GET /api/documents/{id}** and **PATCH /api/documents/{id}/title**. Both users are logged in, yet Alice may only read and edit Alice's documents; Bob may only read and edit Bob's documents. In a multi-tenant application, even two accounts with the same role must not access across tenants.

Using **authenticated()** alone in HTTP security is insufficient: that condition answers “is the caller logged in?”, not “is this person the **owner of the document with this ID**?”. Likewise, **hasRole('USER')** does not distinguish Alice from Bob because they share the same role.

We place a guard at the service layer:

~~~java
@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
public DocumentView read(long documentId) {
    // Runs only after the policy bean permits it.
}
~~~

Here **@PreAuthorize** is the pre-invocation interception mechanism; **@documentPolicy** is a dedicated Spring bean for authorization checks, receiving the authenticated **Authentication** and the **document ID** to look up owner/tenant data from server-side storage. If the policy returns **false**, Spring Security denies the call before the method body runs.

Target outcomes:

- Alice reads/edits document 101 owned by Alice: **ALLOW**.
- Alice reads/edits document 102 owned by Bob, even in the same tenant: **DENY**.
- Carol from tenant B reads document 101 in tenant A: **DENY**.
- An unauthenticated request: blocked at the HTTP authentication layer.
- Missing document: policy **fails closed**, never confirming ownership just because an ID was supplied.
- Sensitive methods are invoked through a Spring-managed proxy; test both HTTP and service paths to prevent bypasses.

This practice uses **Java 17+**, **Spring Boot 3.3.x**, **Spring Security 6.x**, and **MockMvc**. Illustrative data/credentials are for local or test use only; never copy them directly to production.

## 2. Threat Model: IDOR/BOLA Even When Authenticated

Sample data in the application:

| Document ID | Tenant | Owner ID | Initial Title |
| --- | --- | --- | --- |
| 101 | tenant-a | alice | Alpha |
| 102 | tenant-a | bob | Beta |
| 201 | tenant-b | carol | Gamma |

The logged-in identity comes from **SecurityContext**, not from the request body. Common vulnerability scenario:

~~~text
Alice logs in
      |
      v
GET /api/documents/102
      |
      v
Controller calls repository.findById(102)
      |
      v
Returns Bob's document because only authenticated() was checked
~~~

This is **IDOR (Insecure Direct Object Reference)** or **BOLA (Broken Object Level Authorization)**: a user changes a resource ID to access an object outside their permissions.

This flaw cannot be fixed merely by obscuring or making IDs hard to guess, using UUIDs, hiding UI buttons, or restricting to a generic **ROLE_USER**. An unpredictable ID can still leak via logs, share links, or APIs; authorization decisions must evaluate the **caller and the specific resource**.

### 2.1. The Lesson's Owner-Only Rule

Illustrative rule:

~~~text
ALLOW if and only if:
  - the caller is validly authenticated;
  - the account is recognized by the server and still within allowed scope;
  - the document exists in trusted data;
  - the account's tenant equals the document's tenant;
  - the document's owner ID equals the caller's ID.
Otherwise: DENY.
~~~

There is no ADMIN exception in this policy. If a real problem allows tenant administrators, shared collaborators, or delegates to access, **additional rules must be defined and tested explicitly**, never implicitly assuming a powerful role crosses all tenants.

Note that **user ID** should be a stable identifier in the identity system, not necessarily a display username. The demo uses usernames **alice/bob/carol** as account keys for clarity; production should use verified immutable subject IDs/tenants from an IdP or server account directory.

## 3. How Do @PreAuthorize and a Policy Bean Work Together?

Spring Security method security must be enabled with **@EnableMethodSecurity** in the application context. In Spring Security 6, merely adding the spring-boot-starter-security dependency **does not automatically enable** method-level checks.

When another bean calls **DocumentService.read(101)** through a Spring AOP proxy:

~~~mermaid
flowchart TD
    A["HTTP request + Authentication"] --> B["Controller receives documentId"]
    B --> C["Spring proxy of DocumentService"]
    C --> D["@PreAuthorize calls documentPolicy bean"]
    D --> E["Read trusted principal/account"]
    E --> F["Read tenant and owner from DocumentStore"]
    F --> G{"Same tenant and matching owner?"}
    G -->|No| H["AccessDeniedException / HTTP 403"]
    G -->|Yes| I["Execute DocumentService.read or rename"]
    I --> J["Return DTO or update document"]
~~~

An expression such as:

~~~java
@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
~~~

is interpreted by its parts:

| Syntax | Meaning |
| --- | --- |
| **@PreAuthorize** | Spring Security evaluates the condition **before running the method body** |
| **@documentPolicy** | Looks up the Spring bean named **documentPolicy** from the application context |
| **isOwner(...)** | Calls the bean's public method to enforce business policy |
| **authentication** | The **Authentication** object currently in the security context |
| **#p0** | First argument of the protected method, here documentId |
| Boolean result | **true** permits, **false** denies |

**#p0** is useful when parameter names are not retained during compilation. You can use **#documentId** if the Java compiler preserves parameter names via **-parameters**, or use Spring Security's **@P** annotation; however, do not assume parameter names are always available in every project. In this example, **#p0** avoids that dependency.

**Why place logic in a dedicated bean?** The expression stays short, readable, and reusable; the policy is independently testable; the service keeps only business logic. Moreover, the code retrieves account/tenant/owner from trusted data sources instead of trusting an **ownerId** value sent by the client.

## 4. Complete Runnable Java 17+ Project

The demo runs locally without a database to avoid dependencies outside the lesson. **AccountDirectory** simulates the identity/tenant source, and **DocumentStore** simulates the document table. In a real system, both sources must come from verified data and be appropriately protected.

Directory structure:

~~~text
owner-policy-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ownership/
    │   ├── OwnerPolicyApplication.java
    │   ├── SecurityConfig.java
    │   ├── AccountDirectory.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/ownership/
        └── OwnershipAuthorizationTest.java
~~~

### 4.1. Gradle Configuration

**settings.gradle**

~~~groovy
rootProject.name = 'owner-policy-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dependencies include Spring MVC for REST controllers, Spring Security for filters and **@PreAuthorize**, Spring AOP for proxies, and spring-security-test for **MockMvc**, HTTP Basic, and **@WithMockUser**. When working on a real project, use your organization's dependency management and supported versions; the versions above are just for this Spring Boot 3.3.x-compatible example.

### 4.2. Enabling Method Security in the Context

**src/main/java/example/ownership/OwnerPolicyApplication.java**

~~~java
package example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class OwnerPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnerPolicyApplication.class, args);
    }
}
~~~

Key point to remember: **@EnableMethodSecurity** must be active in the context containing **DocumentService**; placing the annotation on a configuration class not scanned/imported by Spring will not protect the service. Default configuration enables **@PreAuthorize** support. Never set **prePostEnabled = false** when the application relies on this annotation.

### 4.3. HTTP Security Configuration and Test Identities

**src/main/java/example/ownership/SecurityConfig.java**

~~~java
package example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/documents/**")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("carol")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build()
        );
    }
}
~~~

**Why is HTTP only authenticated()?** That is intentional for testing: Alice, Bob, and Carol all have **ROLE_USER**, so the HTTP layer only verifies login; **DocumentPolicy** must genuinely block cross-owner/cross-tenant access. If an HTTP rule blocked all USERs, a broken method policy could remain hidden in tests.

**Do not use {noop} passwords in production.** InMemoryUserDetailsManager and illustrative passwords are only for local environments. Production requires a secure PasswordEncoder, a proper identity system, TLS transport, and secrets management. CSRF stays enabled by default in the demo; PATCH requests require a valid CSRF token.

### 4.4. AccountDirectory: Mapping Principal to Trusted User ID and Tenant

**src/main/java/example/ownership/AccountDirectory.java**

~~~java
package example.ownership;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory {
    public record Account(String id, String tenantId) {
    }

    private final Map<String, Account> accounts = Map.of(
            "alice", new Account("alice", "tenant-a"),
            "bob", new Account("bob", "tenant-a"),
            "carol", new Account("carol", "tenant-b")
    );

    public Optional<Account> findByLogin(String login) {
        return Optional.ofNullable(accounts.get(login));
    }
}
~~~

The example uses **authentication.getName()** as login to look up the account in a **server**-managed source. In production, logins can change and collide across realms; prefer immutable IDs/issuers/verified tenants. If a tenant is selected at login, the server must verify the user has membership in that tenant before setting the security context. **Never read tenantId from a JSON body and treat permission as verified.**

### 4.5. DocumentStore: Server-Stored Owner and Tenant Data

**src/main/java/example/ownership/DocumentStore.java**

~~~java
package example.ownership;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
public class DocumentStore {
    public record Document(
            long id, String tenantId, String ownerId, String title) {
    }

    private final Map<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public Optional<Document> find(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document rename(long id, String newTitle) {
        Document result = documents.computeIfPresent(id, (key, old) ->
                new Document(
                        old.id(), old.tenantId(), old.ownerId(), newTitle
                )
        );
        if (result == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return result;
    }

    public void reset() {
        documents.clear();
        documents.putAll(Map.of(
                101L, new Document(
                        101, "tenant-a", "alice", "Alpha"),
                102L, new Document(
                        102, "tenant-a", "bob", "Beta"),
                201L, new Document(
                        201, "tenant-b", "carol", "Gamma")
        ));
    }
}
~~~

**Map<Long, Document>** fits the example because IDs are globally unique across the app. If IDs are only unique **within each tenant**, never look up a document by bare ID and infer the tenant from the request; use a composite key **(tenantId, documentId)** from the verified tenant. With a real database, use proper indexes/query scoping and tenant constraints at the data layer.

The **rename** method has no permission checks because it represents an internal storage operation. Every public entry point must go through the protected service layer; in larger systems, owner/tenant constraints can also be added directly in the SQL UPDATE statement to prevent races and bypass paths around the service. Never expose DocumentStore directly as a controller.

### 4.6. DocumentPolicy: Policy Bean Checking Ownership

**src/main/java/example/ownership/DocumentPolicy.java**

~~~java
package example.ownership;

import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final AccountDirectory accounts;
    private final DocumentStore documents;

    public DocumentPolicy(AccountDirectory accounts,
                          DocumentStore documents) {
        this.accounts = accounts;
        this.documents = documents;
    }

    public boolean isOwner(Authentication authentication, long documentId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        Optional<AccountDirectory.Account> account =
                accounts.findByLogin(authentication.getName());

        if (account.isEmpty()) {
            return false;
        }

        return documents.find(documentId)
                .map(document ->
                        document.tenantId().equals(
                                account.get().tenantId())
                        && document.ownerId().equals(
                                account.get().id()))
                .orElse(false);
    }
}
~~~

Key implementation decisions:

1. **Fail closed:** null/anonymous auth, unrecognized account, and missing document all return **false**.
2. **Do not trust client-supplied owner ID:** ownerId/tenantId are read from DocumentStore.
3. **Check both tenant and owner:** avoids confusing owners with matching IDs/usernames across tenants, or using an account with the right role in a different tenant.
4. **Compare stable IDs with equals:** never compare display names or object references.
5. **Policy returns only a boolean:** never pass the whole Document directly into SpEL, logs, or responses. This reduces the risk of leaking contents prior to authorization.

If the application supports shared users, groups, or per-tenant admins, extend methods such as **canRead / canEdit**, rather than just adding a global role and dropping the tenant check. Every rule requires thorough positive/negative tests.

### 4.7. DocumentService: Attaching @PreAuthorize at the Business Boundary

**src/main/java/example/ownership/DocumentService.java**

~~~java
package example.ownership;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(long id, String title) {
    }

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public DocumentView read(long documentId) {
        return store.find(documentId)
                .map(DocumentService::toView)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public DocumentView rename(long documentId, String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        return toView(store.rename(documentId, newTitle));
    }

    private static DocumentView toView(DocumentStore.Document document) {
        return new DocumentView(document.id(), document.title());
    }
}
~~~

**@PreAuthorize** is placed on **both read and rename**. A method with only READ permission does not automatically protect a write method; rules should be applied to **every sensitive action**. Here the owner is allowed both, though real business rules may differ.

**#p0** is always the first parameter **documentId** in both methods. If parameter order changes later, the expression must be updated and tested. You may use the parameter name **#documentId** when supported by the compiler, but do not change the syntax without testing. When **@PreAuthorize** returns false, the **rename** body is never entered, so no title mutation happens.

**Do not protect only a private helper and call it via this:** Spring AOP proxies cannot intercept ordinary self-invocation. Service classes and methods in the example are Spring-managed, public, and non-final, called from the controller via dependency injection.

### 4.8. DocumentController: Receiving Only ID and Data to Update

**src/main/java/example/ownership/DocumentController.java**

~~~java
package example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    public record RenameRequest(String title) {
    }

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView get(@PathVariable long id) {
        return service.read(id);
    }

    @PatchMapping("/{id}/title")
    public DocumentService.DocumentView rename(
            @PathVariable long id, @RequestBody RenameRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

The controller **does not accept ownerId/tenantId to make authorization decisions**. It only takes the document ID from the path and the new title from the request body; the policy uses account/owner/tenant from trusted server sources. If a client attempts to add an **ownerId** field to the JSON, that field is never used as authorization evidence in this architecture.

## 5. Regression Tests with Spring Security Test and MockMvc

Test both endpoints and direct service invocations. A test running only an authorized user can stay green even when the annotation does not work; **testing denial of non-owners** is mandatory.

**src/test/java/example/ownership/OwnershipAuthorizationTest.java**

~~~java
package example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentStore store;
    @Autowired DocumentService service;

    @BeforeEach
    void restoreFixtures() {
        store.reset();
    }

    @Test
    void methodSecurityIsAppliedThroughProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.title").value("Alpha"));
    }

    @Test
    void otherOwnerInSameTenantIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantAccessIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("carol", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameOwnDocument() throws Exception {
        mvc.perform(patch("/api/documents/101/title")
                        .with(httpBasic("alice", "demo-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Updated\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated"));

        assertEquals("Updated", store.find(101L).orElseThrow().title());
    }

    @Test
    void nonOwnerCannotRenameOrCauseSideEffect() throws Exception {
        mvc.perform(patch("/api/documents/102/title")
                        .with(httpBasic("alice", "demo-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Stolen\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Beta", store.find(102L).orElseThrow().title());
    }

    @Test
    void anonymousCallerMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get("/api/documents/999")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceInvocationStillRejectsNonOwner() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
        assertEquals(101L, service.read(101L).id());
    }
}
~~~

Run on a machine with JDK 17+ and Gradle 8.x compatible with Spring Boot 3.3.x, from the **owner-policy-demo** directory:

~~~bash
gradle test
~~~

If the project has a generated Gradle wrapper, use **./gradlew test** on Linux/macOS or **gradlew.bat test** on Windows. The example above does not bundle wrapper binaries; therefore **gradle test** requires Gradle to be installed. You can run the app:

~~~bash
gradle bootRun
~~~

Then try locally (only while using the mock data):

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/documents/101
curl -i -u alice:demo-pass http://localhost:8080/api/documents/102
~~~

Expected outcome: the first request returns **HTTP 200** and JSON containing **id=101, title=Alpha**; the second request returns **HTTP 403**. **This is the expected result based on the sample code, not stdout from an executed run.**

### 5.1. Why Does Each Test Matter?

| Scenario | Identity/Request | Expectation | What It Proves |
| --- | --- | --- | --- |
| Right owner | alice → GET 101 | 200 | The owner can still perform valid operations |
| Wrong owner, same tenant | alice → GET 102 | 403 | Same role does not grant cross-owner read access |
| Different tenant | carol → GET 101 | 403 | Admins/users of another tenant cannot enter either |
| Right owner updates | alice → PATCH 101 with CSRF | 200, title changes | Both authorization and valid business logic work |
| Wrong owner updates | alice → PATCH 102 with CSRF | 403, title unchanged | Blocked **before side effects** |
| Unauthenticated | anonymous → GET 101 | 401 with HTTP Basic | Authentication is enforced |
| Missing document | alice → GET 999 | 403 per fail-closed policy | Does not confirm permissions for nonexistent IDs |
| Direct service call | @WithMockUser(alice) → read(102) | AccessDeniedException | Prevents endpoint tests from masking method security bugs |
| Service proxy | @Autowired bean | isAopProxy=true | Interceptor infrastructure is applied to the service |

**HTTP status explanation:** when a logged-in user is blocked by **@PreAuthorize**, method security throws **AccessDeniedException** in the request flow; Spring Security translates this to HTTP **403**. When a request lacks valid authentication and uses HTTP Basic, it typically receives **401** with an authentication challenge. When calling the service outside HTTP, you observe the Java exception instead of a status code.

**Why does PATCH need a CSRF token in tests?** Spring Security enables CSRF protection by default for state-changing requests. If you omit **.with(csrf())**, the PATCH test may still return 403 yet **due to CsrfFilter**, failing to prove the owner policy ran. The test supplies a valid CSRF token to pinpoint that authorization blocks non-owners.

### 5.2. Counter-Evidence When Configuration Breaks

Try in a separate test branch/working copy and then restore:

1. Remove **@EnableMethodSecurity** from the application class: a user can call **DocumentService** without the interceptor enforcing the policy. **directServiceInvocationStillRejectsNonOwner** must fail; wrong-owner HTTP tests also stop returning 403 as expected.
2. Keep method security but remove **@PreAuthorize** from **rename**: **nonOwnerCannotRenameOrCauseSideEffect** must catch the ability to modify unauthorized documents.
3. Try changing the policy to compare **documentId** directly with an ownerId input from the request: tests involving other owners' documents must detect the flaw or fixtures must be expanded to prove clients cannot self-grant permissions.
4. Put sensitive methods into one service and call **this.protectedMethod()** inside an unprotected method: direct target tests may differ from internal call paths. Test every entry point, or move guard logic into an injected bean.

Checking only 200 for Alice is **insufficient**. If annotations are not enabled, Alice can still read 101, positive tests remain green, yet Bob can read Alice's document.

## 6. Anti-Patterns to Avoid

### 6.1. Trusting ownerId Sent by the Client

**Unsafe:**

~~~java
// Wrong: "ownerId" can be self-declared by the client.
@PreAuthorize("authentication.name == #p1")
public void update(long documentId, String ownerId) {
    // Does not look up the actual owner of documentId.
}
~~~

An attacker simply passes an ownerId matching their own name. **The right policy must read ownerId from a trusted database/repository** for the requested document and check the corresponding tenant. You may use a document ID from the client to **look up the object**; never use an ownerId from the client to **determine permission**.

### 6.2. Checking Only Role Without Checking Ownership

~~~java
// Insufficient for an "owner-only" rule.
@PreAuthorize("hasRole('USER')")
public DocumentView read(long id) {
    // Alice and Bob both have ROLE_USER.
}
~~~

A role can be an additional condition, e.g., **hasAuthority('DOCUMENT_READ') and @documentPolicy.isOwner(authentication, #p0)**. However, a global role **does not** replace owner/tenant checks when the policy requires them.

### 6.3. Protecting Only the Controller or One Endpoint

If the service is unprotected, a scheduled job, message consumer, GraphQL resolver, or second controller can call the repository directly. Placing policy at the appropriate **service boundary** promotes reuse, though you still must inventory every business entry point.

Conversely, **@PreAuthorize** on a service does not replace SecurityFilterChain for authentication, CSRF, CORS, and other HTTP policies. Check both layers.

### 6.4. Calling a Protected Method via this

~~~java
@Service
class UnsafeDocumentService {
    public String publicEntry(long id) {
        return this.ownerOnly(id);
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public String ownerOnly(long id) {
        return "sensitive";
    }
}
~~~

This snippet is only an **anti-pattern illustration**, not part of the runnable files in section 4. With proxy-based Spring AOP, **this.ownerOnly(id)** is an internal call on the target, **bypassing the proxy**, so the method annotation may be skipped. Fix this by moving the sensitive method into a **separate Spring bean** and calling it through a dependency-injected bean; or move the policy to the actual entry-point method invoked by external callers.

Do not expect **private/final** annotated methods to be intercepted by proxies like ordinary public methods. Simply having the annotation in source code does not guarantee the interceptor runs.

### 6.5. Using @PostAuthorize Instead of @PreAuthorize on Writes

**@PostAuthorize** evaluates after the method executes; for write operations, side effects may already have occurred before denial. For updates/deletes/approvals, use **@PreAuthorize** or a pre-side-effect policy check, combined with commit-time checks if security requirements are strict. For read queries, @PostAuthorize is sometimes suitable to inspect the returned object, though be cautious if the method body has side effects, logs sensitive data, or triggers lazy loading.

### 6.6. Returning ALLOW When Lookup Fails

Avoid patterns that **catch Exception and return true** or “if document not found, allow through.” If owner, tenant, or principal cannot be resolved, **there is no basis to grant access**. Explicitly define how missing data, backend errors, or timeouts behave: the policy can deny or return an appropriate system error, never silently turning errors into ALLOW.

### 6.7. Ignoring Multi-Tenancy

If resource IDs are not globally unique, **findById(id)** is insufficient to select the right resource. When accepting tenant in a URL or header, verify that the caller is actually permitted to operate in that tenant. In real applications, build repository queries like **findByTenantIdAndId(trustedTenantId, id)** and still apply the owner/ACL policy afterward.

## 7. Production Hardening: Races, Performance, and Consistency

### 7.1. TOCTOU Between Authorization Check and Update

The flow **@PreAuthorize → read ACL → call method → update DB** can exhibit a gap between **time-of-check** and **time-of-use**. If ownership or tenant membership changes in between, the earlier decision may no longer hold.

Depending on requirements, you may need:
- Transactions with an appropriate isolation level or row locks.
- Conditional updates, e.g., logical SQL:

~~~sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_subject;
~~~

- Check **updated row count** to confirm the operation was truly valid; never let clients supply **trusted_tenant** or **authenticated_subject** without authentication.
- With shared ACLs, policy versions, parent folders, or complex relationships, the transaction must cover all relevant authorization facts.

The SQL above is only a **conceptual template** for a real database, not part of the Java in-memory demo.

### 7.2. Double Data Lookup

The demo reads the document in **DocumentPolicy**, then the service reads it again to return a DTO or update. In production, this can cause DB overhead and races. Several strategies:
- Use owner/tenant-conditional repository queries to both scope data and reduce round-trips.
- Use consistent transactions/snapshots for required policy facts.
- Move policy into a dedicated **AuthorizationManager** or specialized service with clear responsibilities.
- If caching authorization results, the key must distinguish at least all factors the policy depends on: subject, tenant, resource, action, and corresponding role/ACL/policy version/revision, paired with a reliable revocation strategy.

**Never cache isOwner results solely by documentId**, as Alice's ALLOW could be reused for Bob. Nor treat TTL as proof that newly revoked permissions take effect immediately.

### 7.3. Returning 403 or 404?

The demo chooses **403** for both existing-but-unauthorized IDs and nonexistent IDs. This is simple and avoids confirming permissions when objects are absent, though hiding existence also requires evaluating timing, messages, and other endpoints.

Many APIs choose **404** for both “does not exist” and “not permitted to view” to reduce information disclosure. You can design policies/repositories to hide unavailable resources, yet it must be **consistent** system-wide without leaking through bodies, search, counts, caches, processing time, and audits. Never confuse “returning 404” with having properly enforced authorization.

### 7.4. READ and EDIT Permissions Are Not Always Identical

The owner-only example uses the same **isOwner** for both actions to keep the lesson focused. In real domains you might have:
- Owner can READ and EDIT.
- Collaborator can READ but not EDIT.
- Tenant-admin can view documents within their tenant without crossing tenants.
- A locked document disallows EDIT even for a valid owner.

In those cases, use **canRead(authentication, id)** and **canEdit(authentication, id)** or pass a server-determined trusted **Action**. Never assume every owner can delete or approve every object.

### 7.5. Optimizing Audits Without Leaking Data

Audit sensitive denials/grants with appropriate fields: request ID, internal subject ID, tenant scope, resource type/ID (per organizational security standards), action, policy version, and outcome. Avoid logging access tokens, session cookies, passwords, full ACLs, or document contents. Distinguish **unauthenticated**, **non-owner**, **cross-tenant**, and **unknown resource** in access-controlled security logs if policy allows, while limiting disclosure in public responses.

## 8. Review Checklist and Additional Tests

| Question | Expected Outcome |
| --- | --- |
| Is **@EnableMethodSecurity** enabled in the right application context? | Yes; negative service tests still throw AccessDeniedException |
| Is the service created by Spring and invoked via proxy? | Yes; verified with AopUtils and actual call paths |
| Does the **documentPolicy** bean exist with matching public method signature? | Yes; SpEL has no bean/argument errors |
| Where are Principal ID/tenant obtained from? | Trusted server source, not self-declared body |
| Where are resource owner and tenant obtained from? | Trusted DB/repository, not client-sent URL or DTO |
| Are both subject tenant and resource tenant checked? | Yes; cross-tenant DENY |
| Is a valid owner blocked when the action is forbidden? | Policy exists per actual action |
| Nonexistent ID or unrecognized account? | Never ALLOW; consistent fail-closed handling |
| Is permission enforced before writing? | Yes; failed PATCH has no side effects |
| Do PATCH requests include valid CSRF to test the policy? | Yes; avoids false 403 from CSRF |
| Do other paths/consumers call the repository directly? | No service bypasses or equivalent guard exists |
| Are races handled if owner/ACL changes mid-request? | Mitigations match threat model and SLA |
| Do test fixtures include same-tenant Alice/Bob and cross-tenant Carol? | Yes, with positive/negative tests |
| Are policy lookups instrumented and sensitive data kept out of logs? | Yes, without leaking secrets |

### 8.1. Topic-Aligned Extension Exercises

1. Add action **DELETE** while disallowing owners from deleting documents in **LOCKED** state; switch from **isOwner** to **canDelete** with trusted state lookup. Test that the owner is still denied when the document is locked.
2. Add account **dave** in tenant-a and document 301 owned by dave; verify Alice cannot read that document despite sharing the same role and tenant.
3. Add subject **tenant-admin** who can READ documents in their own tenant yet cannot EDIT unless they are the owner. Never use a global ADMIN role to skip tenant checks.
4. Migrate the repository to Spring Data JPA; design conditional owner/tenant queries, handle transactions/TOCTOU, and check updated row counts.
5. Use **@P("documentId")** on the service parameter instead of **#p0**, then re-verify the expression with tests. Ensure method-security parameter discovery recognizes the marked name.
6. Add **direct bean invocation** tests from a simulated consumer instead of HTTP to prove the service guard is reusable.
7. Write a counter-evidence test by temporarily removing @PreAuthorize: negative tests and DB state tests must FAIL, then restore the source.

## 9. Summary

To enforce ownership checks reliably in Spring Security, combine:

1. **@EnableMethodSecurity** to activate method-level interceptors.
2. **@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")** on **sensitive service methods**, called through a Spring proxy.
3. **A dedicated policy bean** using Authentication and looking up owner/tenant from a **trusted server data source**, returning false when grounds for permission are missing.
4. **HTTP authentication + service authorization + data-access constraints** as complementary defense layers.
5. **Testing ALLOW and DENY** within the same tenant, across tenants, write methods with side effects, direct service calls, and nonexistent resources.

The key is not merely annotating source code for neatness, but proving every real call goes through the policy and a user **cannot grant themselves ownership by changing an ID or spoofing ownerId**.

### Official Documentation and Further Reading

- Spring Security 6.5 — Method Security, bean authorization, method parameters: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — AOP Proxying Mechanisms and self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Testing MockMvc Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP API Security — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
