# @PreAuthorize: Checking Authorization Before Method Execution in Spring Security

An API may be protected at the URL layer, yet the same business logic can still be invoked from multiple places: a REST Controller, a scheduled job, an event handler, or another service component. When only `GET /documents/**` or `POST /documents/**` is guarded, policies easily become fragmented or leave non-HTTP call paths unprotected. Spring Security's **`@PreAuthorize`** attaches an authorization condition to **method invocation**, preventing the method body from running when the caller lacks sufficient permissions.

For example, `DocumentService.editDocument(100L)` may only run when the user holds the `DOC_EDIT` permission **and** is genuinely the owner of document 100. Spring Security evaluates the condition before forwarding the call to the target method. If denied, the data write inside the body is not executed through the intercepted call.

This lesson belongs to **Method protection** in **Spring Security - fundamentals**. We will explore what `@PreAuthorize` is, how to enable it, expression syntax, the proxy/interceptor mechanism, parameter- and record-level authorization, testing real behavior, and call paths that can defeat the annotation. The main examples use **Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x**.

## 1. What Problem Does @PreAuthorize Solve?

Consider a service:

~~~java
public void deleteDocument(long id) {
    repository.deleteById(id);
}
~~~

If this call runs before checking identity and permissions, the deletion has already happened. You could add `if` logic directly inside the method, but when multiple operations share the same rule, authorization code becomes repetitive and easy to miss.

With method security:

~~~java
@PreAuthorize("hasAuthority('DOC_DELETE')")
public void deleteDocument(long id) {
    repository.deleteById(id);
}
~~~

Spring Security checks whether the caller holds a `GrantedAuthority` equal to `DOC_DELETE` **before** allowing the method body to execute through the security interceptor. Note that the snippet above is **illustrative code**, since `repository` is not defined; a complete application example appears later.

Why add this layer when HTTP security already exists?

| URL-level authorization | Method-level authorization with `@PreAuthorize` |
| --- | --- |
| Protects a request matching an HTTP method/path or other matcher | Protects method calls on a Spring-managed bean |
| Suitable for protecting HTTP entry points | Suitable for protecting business boundaries |
| Rules usually live in `SecurityFilterChain` | Rules live directly on service methods/classes |
| Easy to inspect permitted URL paths | Can use parameters such as `#documentId`, `#owner` |
| Does not automatically protect non-HTTP service calls | Protects calls going through the method-security proxy with an appropriate `Authentication` |

The two layers can **complement each other**. Having `@PreAuthorize` is no reason to skip HTTP authentication, and declaring `hasRole` on an endpoint is no reason to skip checking permission for an action on specific data.

## 2. When Is the Condition Checked?

Model for a Java/Spring MVC application with Spring AOP-based method security:

~~~text
Controller / bean A
      |
      | calls documentService.editDocument(100)
      v
Spring-managed proxy of DocumentService
      |
      v
AuthorizationManagerBeforeMethodInterceptor
      |
      +--> Reads current Authentication
      |
      +--> Evaluates @PreAuthorize expression
              |
              +--> true  -> calls real method -> runs business logic
              |
              +--> false -> throws access denied error
                             -> DOES NOT call real method
~~~

Spring Security 6.x uses a before-invocation interceptor (e.g., `AuthorizationManagerBeforeMethodInterceptor` with the corresponding manager for `@PreAuthorize`). The expression is evaluated in a context containing `Authentication`, method parameters, and Spring Security's authorization helper functions.

Key points:

1. `@PreAuthorize` is evaluated **every time a matching call passes through the interceptor**. It is not a one-time startup check.
2. If the condition is `true`, the call proceeds into the method body; the method may still fail due to business rules, data errors, or additional checks.
3. If the condition is `false`, the method body does not execute along the protected call path; Spring Security typically throws `AccessDeniedException` or a corresponding subtype.
4. If no valid authentication context exists, the outcome can be an unauthenticated error or an access-denied error depending on the execution path and exception handling. **Do not hardcode an assumption of HTTP 403 for every case.**
5. Any lookups executed **inside the expression or policy bean** may still have run before the condition returned `false`. "Target method did not run" does not mean "zero work occurred."

A plain `new DocumentService()` call does not pass through a Spring bean/proxy, so the annotation will not enforce itself. This is the most important fact for testing `@PreAuthorize` properly.

## 3. Method Security Must Be Explicitly Enabled

Adding the `spring-boot-starter-security` dependency alone **does not automatically enable method protection**. On Spring Security 6.x, enable it as follows:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Once `@EnableMethodSecurity` is present, Spring Security scans for methods/classes carrying authorization annotations such as `@PreAuthorize` and configures the appropriate interceptor mechanism. The example above is a standalone configuration class that can live in a package scanned by Spring Boot.

Version notes:

- With Spring Security 6.x, prefer `@EnableMethodSecurity`.
- Older docs/articles may show `@EnableGlobalMethodSecurity(prePostEnabled = true)`; that is the legacy configuration and should not be blindly copied to 6.x projects.
- `@EnableMethodSecurity` supports `@PreAuthorize`/`@PostAuthorize` by default; `@Secured` or JSR-250 have separate opt-in flags if needed. This lesson focuses on `@PreAuthorize`.
- You do not need `@EnableMethodSecurity` on every service; declaring it once on a configuration class loaded into the `ApplicationContext` is normally enough.

**How to verify it is enabled:** a test calling a restricted method through a Spring bean as a user lacking permission must fail with an error; if it still returns a result, check your configuration, annotation placement, and whether the call passes through a proxy.

## 4. @PreAuthorize Expression Syntax

The annotation accepts a **Spring Expression Language (SpEL)** string combining security expressions provided by Spring Security:

~~~java
@PreAuthorize("isAuthenticated()")
public String getProfile() { /* ... */ }

@PreAuthorize("hasRole('ADMIN')")
public void rebuildIndex() { /* ... */ }

@PreAuthorize("hasAuthority('DOC_READ')")
public String readDocument(long id) { /* ... */ }

@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
public String exportDocuments() { /* ... */ }
~~~

The methods above are **expression** illustrations, not a standalone compilable Java file because their bodies are elided.

| Expression | Meaning |
| --- | --- |
| `isAuthenticated()` | The user is authenticated and not anonymous; in default setups this usually includes remember-me |
| `isFullyAuthenticated()` | Fully authenticated, excluding anonymous and remember-me per the trust resolver |
| `isAnonymous()` | The identity is recognized as anonymous |
| `hasRole('ADMIN')` | Holds authority `ROLE_ADMIN` under the default role prefix |
| `hasAuthority('DOC_READ')` | Holds an authority strictly equal to `DOC_READ` |
| `hasAnyRole('ADMIN', 'EDITOR')` | Holds at least one of the listed roles |
| `hasAnyAuthority('DOC_READ', 'DOC_ADMIN')` | Holds at least one of the listed authorities |
| `authentication.name` | Name of the current `Authentication` |
| `principal` | The principal object in the authentication context |
| `#id` | The method parameter named `id` (when parameter names are supplied/discovered properly) |
| `@documentPolicy.isOwner(authentication, #id)` | Calls the Spring bean named `documentPolicy` to verify data-level permission |

Important distinction:

~~~text
hasRole('ADMIN')             usually checks ROLE_ADMIN
hasAuthority('ROLE_ADMIN')   checks exact ROLE_ADMIN
hasAuthority('ADMIN')        checks exact ADMIN
~~~

If a user holds authority `DOC_EDIT` without `ROLE_DOC_EDIT`, `hasAuthority('DOC_EDIT')` can pass while `hasRole('DOC_EDIT')` fails. Never mix up roles and authorities simply because their display names look similar.

### Combining Conditions

Use `and`, `or`, and `!` in SpEL:

~~~java
@PreAuthorize("hasAuthority('DOC_EDIT') and #owner == authentication.name")
public void editOwnedDocument(String owner) { /* ... */ }

@PreAuthorize("hasRole('ADMIN') or hasAuthority('REPORT_VIEW')")
public String viewReport() { /* ... */ }
~~~

The first condition requires **both** edit permission and `owner` matching the current username. However, if `owner` is passed directly from a client-controlled request, an attacker can simply supply their own name. **Never compare against a client-declared value as proof of resource ownership.** Load the real owner from a trusted data source by ID, as shown in section 6.

Using single quotes for strings inside SpEL keeps Java code readable. Avoid expressions like `hasRole(ADMIN)` with an undefined identifier; `hasRole('ADMIN')` is the standard form.

## 5. Scope of Application: Beans, Methods, and Annotation Placement

In practice, `@PreAuthorize` must sit on a Spring-managed method or class:

~~~java
@Service
public class BillingService {

    @PreAuthorize("hasAuthority('INVOICE_READ')")
    public String readInvoice(long id) {
        return "invoice:" + id;
    }
}
~~~

This is a `@Service` bean; when another bean injects `BillingService` and calls `readInvoice` through the proxy, the condition is evaluated. If a class is not created by Spring (instantiated with `new`), there is no guarantee any Spring AOP interceptor will run.

You can place the annotation at class level to apply a default across eligible methods:

~~~java
@Service
@PreAuthorize("hasRole('AUDITOR')")
public class AuditService {
    public String inspect(long id) {
        return "audit:" + id;
    }
}
~~~

When mixing rules across class, interface, and method levels, check your Spring Security version's annotation inheritance/precedence semantics and avoid ambiguous rules. When actions require distinct permissions, **placing annotations explicitly on each method** is usually easier to audit.

Do not expect Spring AOP proxies to guard calls to `private`, `static`, or `final` methods, or direct calls on `this`. With `final` classes or methods, depending on the proxy type, the application may fail to create a proxy or fail to intercept the call; design security boundaries on proxyable methods and verify them with tests.

## 6. Complete Example: Protecting Document Editing by Owner

The learning project tests three rules:

1. Users with `DOC_READ` can call `readDocument(id)`.
2. Only users with `DOC_EDIT` **and** who are the true owner of the document can call `editDocument(id)`.
3. Users with role `ADMIN` can call `audit()`.

The example uses an in-memory owner store for easy execution, clearly demonstrating **authentication-context permissions + record-level permissions from a trusted data source**. It does not implement a database, controller, or real login authentication.

### 6.1. Source Structure

~~~text
method-security-demo/
├── build.gradle
├── settings.gradle
├── src/main/java/example/methodsecurity/
│   ├── MethodSecurityApplication.java
│   ├── DocumentPolicy.java
│   └── DocumentService.java
└── src/test/java/example/methodsecurity/
    └── DocumentServiceSecurityTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'method-security-demo'
~~~

### 6.3. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The example pins a specific Spring Boot 3.3.x release to illustrate the API. Projects may use a compatible Gradle wrapper and Java 17+. For an existing Spring Boot project, merge only the needed dependencies/configurations; do not add duplicate plugin version declarations when the project already defines them.

### 6.4. MethodSecurityApplication.java

~~~java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

The main class both boots Spring Boot and enables method security. Since this sample app has no web starter, tests focus on **service calls** without starting an HTTP server.

### 6.5. DocumentPolicy.java: Data-Source-Backed Authorization

~~~java
package example.methodsecurity;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Simulated data from a server-side document store.
    private final Map<Long, String> ownerById =
            Map.of(100L, "lan", 200L, "minh");

    public boolean isOwner(Authentication auth, long id) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        String recordedOwner = ownerById.get(id);
        return recordedOwner != null
                && recordedOwner.equals(auth.getName());
    }
}
~~~

In a real application, `ownerById` would be a lookup from a protected, consistent data store, never based on a client-supplied `owner` parameter. The security expression in `DocumentService` also checks `DOC_EDIT`, so an anonymous identity cannot slip through merely by matching a name. If reusing `DocumentPolicy` as a standalone authorization check elsewhere, add authentication trust-level checks (e.g., via `AuthenticationTrustResolver`) and suitable resource policies.

A non-existent ID returns `false`. This is a safe choice for the example; production systems also need a policy for returning 404/403 and avoiding resource-existence disclosure.

### 6.6. DocumentService.java: Protecting Method Bodies

~~~java
package example.methodsecurity;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final AtomicInteger editCounter = new AtomicInteger();

    @PreAuthorize("hasAuthority('DOC_READ')")
    public String readDocument(long id) {
        return "document:" + id;
    }

    @PreAuthorize(
        "hasAuthority('DOC_EDIT') and @documentPolicy.isOwner(authentication, #id)"
    )
    public String editDocument(@P("id") long id) {
        editCounter.incrementAndGet();
        return "edited:" + id;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String audit() {
        return "audit:allowed";
    }

    public int editCount() {
        return editCounter.get();
    }

    public void resetEditCount() {
        editCounter.set(0);
    }
}
~~~

Key points to note:

- `@Service` makes Spring instantiate the object and allows it to create a proxy carrying interceptors.
- `@PreAuthorize("hasAuthority('DOC_READ')")` guards the read operation.
- `editDocument` runs only when the caller both holds `DOC_EDIT` and receives `true` from the `documentPolicy` bean.
- `@documentPolicy` in SpEL references the Spring bean named `documentPolicy`, not a Java static method call syntax.
- `authentication` in the expression is the current `Authentication` object. `#id` is the method's `id` parameter, explicitly named with `@P("id")`.
- `@P` uses the package `org.springframework.security.core.parameters.P`. This avoids relying on compiler flags preserving parameter names and avoids the legacy deprecated `org.springframework.security.access.method.P` import.
- `AtomicInteger` is solely for tests proving **the body did not run** when permissions are missing. In production apps, never use an in-memory counter as security evidence or business state.
- `editCount` and `resetEditCount` are **test-only observation hooks**; do not expose such methods in real services.

When `@PreAuthorize` denies access, the counter **does not increment** because `editCounter.incrementAndGet()` resides inside the target method body.

### 6.7. DocumentServiceSecurityTest.java: Real Testing Through the Proxy

~~~java
package example.methodsecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService documents;

    @BeforeEach
    void reset() {
        documents.resetEditCount();
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_READ")
    void readerCanRead() {
        assertEquals("document:100", documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void editorCannotReadWithoutReadAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void ownerCanEditWithCorrectAuthority() {
        assertEquals("edited:100", documents.editDocument(100L));
        assertEquals(1, documents.editCount());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "DOC_EDIT")
    void nonOwnerCannotEditEvenWithEditAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(100L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_READ")
    void ownerCannotEditWithoutEditAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(100L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void unknownDocumentIsNotEditable() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(999L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadDocument() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleCanAudit() {
        assertEquals("audit:allowed", documents.audit());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void normalRoleCannotAudit() {
        assertThrows(AccessDeniedException.class, documents::audit);
    }
}
~~~

In these tests, `@Autowired DocumentService` is a Spring-supplied bean, so `documents.editDocument(...)` travels through the authorization check. `@WithMockUser` builds a mock identity in the test context; `@WithAnonymousUser` simulates an anonymous guest. No database users need to be created merely to test method-security conditions.

Run from a directory with a compatible Gradle wrapper:

~~~bash
./gradlew test --tests '*DocumentServiceSecurityTest'
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "*DocumentServiceSecurityTest"
~~~

**Expected outcome from the code:** all **9 tests** pass. In the two missing-authority tests and one wrong-owner test, `editCount()==0` proves the `editDocument` body did not run. This is the **expected outcome based on the Spring Security 6.3.x contract**, not stdout/test output executed here. To verify in a real project, ensure compatible dependencies and wrapper are present and run the command.

If tests fail, diagnose errors in the proxy, annotations, expressions, test authentication setup, or `ApplicationContext` configuration; do not look solely for HTTP statuses since this test suite invokes the service bean directly.

## 7. Explaining the Parameter-Based Authorization Chain Accurately

Key expression:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_EDIT') and @documentPolicy.isOwner(authentication, #id)"
)
public String editDocument(@P("id") long id) {
    // ...
}
~~~

Suppose a request arrives to edit document 100:

| Caller | Authority | Stored owner | Requested ID | Outcome |
| --- | --- | --- | --- | --- |
| `lan` | `DOC_EDIT` | `lan` | 100 | Method invocation allowed |
| `minh` | `DOC_EDIT` | `lan` | 100 | Denied, wrong owner |
| `lan` | `DOC_READ` | `lan` | 100 | Denied, missing `DOC_EDIT` |
| `lan` | `DOC_EDIT` | No document 999 | 999 | Denied, policy returns false |
| Anonymous | No `DOC_EDIT` | `lan` | 100 | Denied |

The `and` operator requires both sides to be true. The authority only grants the **action type** (editing documents), while `DocumentPolicy` checks the **specific resource**. Using only `hasAuthority('DOC_EDIT')` allows an editor to modify someone else's document; using only `#owner == authentication.name` with a client-sent `owner` lets an attacker declare themselves the owner.

A policy may require additional checks, such as whether the document is unlocked, whether the user belongs to the same organization, whether the account is active, and whether authentication strength is sufficient. For multi-step conditions or database queries, extract them into a clearly named policy bean for easy unit testing and to avoid overly long SpEL expressions.

### Parameter Name Discovery in SpEL

The name `#id` works only if the system can resolve the matching parameter. Spring Security supports several sources:

- Spring Security's `@P("id")` on the parameter.
- Parameter name info compiled via Java's `-parameters` flag.
- Certain class-level metadata/debug information; do not rely on this when interfaces or build environments change.

Positional aliases like `#p0` or `#a0` work in supported contexts, but explicit names are more readable and maintainable. The main example uses `@P("id")`, keeping `#id` independent of compiler flags.

If an expression references `#id` but parameter name discovery fails to find it, comparisons/checks can yield wrong values or SpEL evaluation can fail. Always test parameter-dependent branches rather than assuming everything works just because Spring Boot starts up.

## 8. Checking Expressions by Identity and Role

Some common patterns:

~~~java
// Valid logged-in user.
@PreAuthorize("isAuthenticated()")
public String accountOverview() { /* ... */ }

// Admin only under the ROLE_ADMIN convention.
@PreAuthorize("hasRole('ADMIN')")
public void reconfigureSystem() { /* ... */ }

// Holds either read or admin authority.
@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
public String viewLibrary() { /* ... */ }

// Authenticated and holds edit permission.
@PreAuthorize("isAuthenticated() and hasAuthority('DOC_EDIT')")
public void createDraft() { /* ... */ }
~~~

These are **illustrative signatures**; replace `/* ... */` with real bodies inside a Spring bean when using them. With default prefix settings, `hasRole('ADMIN')` checks `ROLE_ADMIN`; `hasAuthority('DOC_ADMIN')` checks the exact string `DOC_ADMIN`.

`isAuthenticated()` and `isFullyAuthenticated()` are not synonymous when remember-me is configured in Spring Security. For sensitive operations, decide whether remember-me sessions are allowed; `isFullyAuthenticated()` does **not** prove the user recently completed MFA or re-authenticated within the last few minutes. Step-up authentication policies must check explicit evidence when required.

## 9. Preventing Self-Invocation Bugs: Internal Calls Bypassing the Proxy

This is the most common pitfall when applying method security with Spring AOP:

~~~java
@Service
public class UnsafeReportService {

    public void runReport() {
        exportSensitiveReport(); // Internal call on this.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void exportSensitiveReport() {
        // Assume this is a sensitive operation.
    }
}
~~~

Another bean calls `runReport()` through the proxy, yet the call `this.exportSensitiveReport()` from inside the object normally **does not go back through the proxy**. Thus, the annotation on `exportSensitiveReport` may **not be checked** along that call path. Annotating the sensitive method does not automatically guard internal call paths.

A cleaner design is moving the protected method to **another bean** and calling it via the injected bean:

~~~java
@Service
public class ReportOperations {

    @PreAuthorize("hasRole('ADMIN')")
    public void exportSensitiveReport() {
        // Operation requiring ADMIN role.
    }
}

@Service
public class ReportCoordinator {

    private final ReportOperations operations;

    public ReportCoordinator(ReportOperations operations) {
        this.operations = operations;
    }

    public void runReport() {
        operations.exportSensitiveReport();
    }
}
~~~

The two classes above are two illustrative Java source files; add `package` and `@Service` imports as appropriate for your application. Here `ReportCoordinator` calls the **Spring-injected `ReportOperations` bean**, letting the interceptor apply `@PreAuthorize`. AspectJ weaving is an option if self-invocation truly must be intercepted, though it is a different deployment model requiring separate configuration and testing.

Similar easy-to-miss scenarios:

- Instantiating beans with `new` instead of injecting Spring beans.
- Calling `private` or `final` methods directly on the target object.
- Calling an annotated method through an unproxied/unwoven path.
- Placing `@PreAuthorize` on an interface or superclass with unexpected annotation lookup behavior.
- Tests constructing objects manually and assuming annotations are enforced.

**Tests should invoke the exact entry path used by the application**, through a Spring bean, and confirm business state remains unchanged when unauthorized.

## 10. Differences from @PostAuthorize, @Secured, and URL Checks

| Mechanism | Check timing/layer | Suitable use case |
| --- | --- | --- |
| `@PreAuthorize` | Before target method via interceptor | Permissions by identity, role, parameters, record-level rights |
| `@PostAuthorize` | After target method finishes; can inspect return value | Authorization needing the method's return value |
| `@Secured` | Simple annotation-based role/authority check | Cases not needing complex SpEL |
| `authorizeHttpRequests(...)` | When HTTP request passes through security filter chain | Method/path protection, HTTP entry points |
| Business checks inside service | While service executes business logic | State constraints, ownership, dynamic transaction policies |

`@PostAuthorize` cannot replace `@PreAuthorize` for create/update/delete operations with side effects: checking only after the body finishes means data may already have been written before insufficiency is detected. Therefore, **use `@PreAuthorize` before side-effecting operations** whenever authorization can be decided upfront.

`@PreAuthorize` also does not eliminate the need for validation, transactions, data constraints, and auditing. Permissions can change between check and write; for critical operations, consider transactional consistency, re-checking inside the same transaction scope, or proper data constraints.

## 11. When Does Authorization Actually Block the Operation?

To distinguish **denial by @PreAuthorize** from **errors in the method body**, consider:

~~~java
@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
public void approvePayment() {
    validatePayment();
    transferMoney();
}
~~~

Calls through the proxy have two outcomes:

1. Without `PAYMENT_APPROVE`: the `approvePayment` body is not called; `validatePayment` and `transferMoney` do not run along that path.
2. With `PAYMENT_APPROVE`: the body runs, yet `validatePayment` can still throw an error or `transferMoney` can still fail. `@PreAuthorize` **does not guarantee business transactions succeed**.

If authorization is placed inside the body after doing work:

~~~java
public void approvePayment() {
    transferMoney();   // Already caused side effects.
    checkPermission(); // Check comes too late.
}
~~~

then even if `checkPermission()` throws, side effects may already have occurred and not all external systems support rollback. Using `@PreAuthorize` before invocation sets a clearer control boundary, though state-dependent security logic still requires combining transaction controls and data constraints.

Additional note: beans invoked inside `@documentPolicy...` expressions can still run queries/logic to decide permissions; avoid giving such beans irreversible create/delete side effects.

## 12. HTTP Status When @PreAuthorize Denies: 401 or 403?

`@PreAuthorize` is a **method-layer check** and does not directly produce HTTP responses. When the call originates from an HTTP request, the exception can be handled by Spring Security's filter chain or another exception handler.

| Situation | Typical HTTP response | Why |
| --- | --- | --- |
| Unauthenticated caller invokes restricted action | 401 with HTTP Basic/Bearer, or login redirect | Decided by `AuthenticationEntryPoint`/login config |
| Authenticated but missing authority | 403 | `AccessDeniedException` handled as access denial |
| Authenticated, holds authority, and resource policy allows | Request proceeds to method body | Controller/Service determines final response |
| Authorized, but business logic throws an error | Other 4xx/5xx per cause/handler | Not an outcome of `@PreAuthorize` |
| Method invoked from worker/scheduler outside HTTP | Exception raised at call site | No HTTP response to map to a status code |

Do not design unit tests expecting only `HTTP 403`, since direct bean calls yield **Java exceptions**. To verify HTTP statuses, add Controller HTTP tests alongside real filters and exception handlers.

In HTTP integration, ordering matters too: URL security or CSRF may reject a request **before** the Controller ever calls the service. Receiving a 403 does not by itself prove `@PreAuthorize` was the layer that denied it.

## 13. Use with Controllers and Multiple Entry Points

Suppose a REST Controller calls a protected service:

~~~java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{id}")
    public String read(@PathVariable long id) {
        return documents.readDocument(id);
    }

    @PutMapping("/{id}")
    public String edit(@PathVariable long id) {
        return documents.editDocument(id);
    }
}
~~~

This is a **Servlet/MVC integration snippet**, not part of the non-web app in section 6. To use it, add `spring-boot-starter-web`, import the appropriate Controller annotations, and configure a `SecurityFilterChain` for your login strategy.

The benefit is that any call path **genuinely passing through the `DocumentService` bean** applies the same policy:

~~~text
HTTP Controller ──┐
                  ├──> DocumentService proxy ──> @PreAuthorize ──> method body
Message handler ──┤
                  │
Other Spring bean ┘
~~~

However, if a scheduled job, message consumer, or CLI lacks a suitable `Authentication` in context, the call can be denied. Never turn off method security just so internal tasks run. Grant explicit service-account/system-thread permissions or deliberately separate identity-bearing and system-only operations.

Another point: a caller might bypass `DocumentService` and hit a repository or another bean directly to mutate data. Annotations on `DocumentService` cannot control those paths. Architecture design must define clean business boundaries and restrict data-write paths that circumvent them.

## 14. @PreAuthorize in WebFlux: Same Purpose, Different Context

In Spring WebFlux, **reactive method security** has its own configuration and security context retrieval:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

A reactive service can protect a method returning `Mono<T>` or `Flux<T>`:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> readDocument(long id) {
    return reactiveRepository.findById(id).map(Document::content);
}
~~~

The snippet above is **illustrative** and requires a repository bean, `Document` type, and a real WebFlux app. In reactive stacks, evaluation and enforcement attach to the Publisher chain and Reactor context; do not rely on ThreadLocal `SecurityContextHolder` as if context automatically crosses all threads. In particular, constructing a `Mono` without subscribing does not mean the reactive task has executed.

To test reactive method security, use `@EnableReactiveMethodSecurity`, `StepVerifier`, and establish an appropriate reactive authentication context. Do not copy Servlet's `@EnableMethodSecurity` configuration verbatim and assume everything works identically in WebFlux.

## 15. Testing Gaps That "Authorized-Only" Tests Often Miss

A thorough method-security test suite should cover at least:

| Scenario | Objective |
| --- | --- |
| Holds required authority | Method returns expected data |
| Missing authority | Denial thrown; body does not execute |
| Holds ADMIN role | Correct `ROLE_ADMIN` mapping |
| Lacks ADMIN role | Cannot invoke administrative actions |
| Has action authority, wrong document owner | Cannot edit someone else's document |
| Is document owner, lacks edit authority | Cannot rely solely on ownership |
| Non-existent resource ID | Clear and safe policy rule |
| Anonymous | Not accidentally granted access |
| Called via Spring bean along real path | Annotation actually enforced by interceptor |
| Self-invocation | Detect call paths that might bypass the proxy |
| Same operation via HTTP and messaging | No entry point accidentally bypasses policy |

In tests, prioritize observing **data state or side-effect indicators showing whether the body ran** alongside exceptions. An HTTP-layer exception could come from CSRF or URL filters before the method is invoked; service tests should prove the `@PreAuthorize` boundary independently.

Avoid `@WithMockUser` in HTTP tests hitting a real server in a separate thread/process while expecting the mock identity to propagate to the server. For end-to-end HTTP, authenticate in the actual request (HTTP Basic, Bearer token, cookies, etc.).

## 16. Common Mistakes and Fixes

**Mistake 1 — Forgetting `@EnableMethodSecurity`.** Spring Boot can start normally and methods still execute despite missing permissions. Enable method security and add real denial tests.

**Mistake 2 — Instantiating services with `new`.** Annotations do not enforce themselves on objects outside Spring. Inject beans from the `ApplicationContext` and test those exact beans.

**Mistake 3 — Self-invocation.** Public method A in the same class calls B annotated with `@PreAuthorize`. Internal calls via `this` usually bypass the proxy. Extract B to another bean or choose an interception model proven by tests.

**Mistake 4 — Confusing `hasRole` with `hasAuthority`.** `hasRole('ADMIN')` looks for `ROLE_ADMIN` by default; `hasAuthority('ADMIN')` looks for exact `ADMIN`. Verify actual strings inside `GrantedAuthority`.

**Mistake 5 — Using client-declared fields as proof of ownership.** `#owner == authentication.name` is unsafe if `owner` comes from the client. Fetch the real owner from the database by ID and compare.

**Mistake 6 — Wrong SpEL parameter name.** `#documentId` will not resolve if compile metadata/code does not expose that name. Use `@P` or configure `-parameters`, then test per-ID rules.

**Mistake 7 — Annotating unproxyable methods.** Private/final/static methods or final classes may not be intercepted under the active proxy mode. Move checks to a public/proxyable boundary and test.

**Mistake 8 — Treating `@PreAuthorize` as a complete replacement for HTTP security.** HTTP entry points still need authentication, request filtering, and CSRF/CORS as appropriate; methods may also be invoked outside HTTP.

**Mistake 9 — Using only `@PostAuthorize` for writes.** Checking after execution can be too late. Use `@PreAuthorize` for conditions decidable upfront, combined with transactions and proper state checks.

**Mistake 10 — Treating `fullyAuthenticated` as proof of MFA.** It classifies authentication state per Spring Security, not recent re-authentication or multi-factor verification.

**Mistake 11 — Writing overly long expressions or expressions with side effects.** Move data lookups into a policy bean with clean methods, and never mutate data during permission evaluation.

**Mistake 12 — Testing through Controllers without knowing what blocked the call.** If URL filters, CSRF, and method security are all active, test the service bean directly first, then add HTTP tests.

**Mistake 13 — Ignoring data changes between check and write.** Ownership or document state can change concurrently. Critical actions require appropriate transactions, locks, or data constraints to prevent time-of-check/time-of-use drift.

## 17. Self-Check Questions

**1.** A Spring Boot app has `spring-boot-starter-security` and a service with `@PreAuthorize`, but `@EnableMethodSecurity` is not enabled. Can you trust that the annotation is definitely running?

**Answer:** No. Method security is not enabled automatically by the starter alone; you must configure `@EnableMethodSecurity` and test a call through the Spring bean.

**2.** A user has `ROLE_ADMIN` but lacks `DOC_EDIT`. Can `hasRole('ADMIN')` be true while `hasAuthority('DOC_EDIT')` is false?

**Answer:** Yes. They check two different authorities. Each business requirement must use the matching condition.

**3.** Why is `@PreAuthorize("hasAuthority('DOC_EDIT')")` insufficient to restrict document editing to owners?

**Answer:** The authority only indicates permission to edit that resource type. To restrict specific records, you must verify ownership/record permissions by ID using trusted data.

**4.** If a service calls its own `@PreAuthorize`-annotated method via `this`, does the annotation always execute?

**Answer:** No. With standard Spring AOP proxies, self-invocation bypasses the proxy. You must change bean boundaries or the interception mechanism.

**5.** When `@PreAuthorize` denies a call, has the body incremented counters or written data?

**Answer:** If the call is properly protected by the proxy and denied **before invoking the target method**, the body has not run. However, lookups performed inside the authorization expression itself may already have executed.

**6.** Should direct service tests expect HTTP 403 or a Java exception?

**Answer:** A Java exception (typically `AccessDeniedException` when authenticated but lacking permission). HTTP status codes only appear when an HTTP request and matching exception handler are involved.

**7.** Can `@PreAuthorize` inspect `#id`?

**Answer:** Yes, if parameter names are properly discovered, e.g., via `@P("id")` or compiling with `-parameters`; always test with different IDs.

**8.** Does `@PreAuthorize` guarantee the method body will not fail or roll back all side effects?

**Answer:** No. It only gates pre-invocation conditions; subsequent failures and transactional consistency remain the responsibility of business logic.

## 18. Summary of the Operating Model

~~~text
Does caller have an appropriate Authentication?
        |
        v
Called via Spring-managed bean/proxy?
        |
        v
Method security enabled and annotation recognized?
        |
        v
Evaluate @PreAuthorize expression
   - Coarse permission: hasAuthority, hasRole...
   - Specific permission: @documentPolicy.isOwner(..., #id)
        |
        +--> DENY: exception; target method body not called
        |
        +--> ALLOW: forward call to body
                    business checks, transactions, data processing
~~~

**Rule to remember:** `@PreAuthorize` protects **calls to Spring-managed methods** using a **condition evaluated before running the body**. Reliable protection requires all three factors: **enabling interceptors**, **calling through the right bean/proxy**, and **writing expressions backed by trusted authorities and verified data**.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/method-security.html): enabling, `@PreAuthorize` calls, parameters, and proxy limitations.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/6.3/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, and testing via Spring beans.
- [Spring Security — Method Authorization API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/method/PreAuthorizeAuthorizationManager.html): before-method authorization manager.
- [Spring Security — @PreAuthorize API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/access/prepost/PreAuthorize.html): annotation and SpEL conditions.
- [Spring Security — Annotation @P](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/core/parameters/P.html): naming parameters for expressions.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy semantics and self-invocation in Spring AOP.
