# Choosing an AuthorizationManager When Built-In Rules Are Not Enough

## 1. Scenario and Design Question

Spring Security provides built-in ways to write common authorization rules:

- `permitAll()`, `denyAll()`, `authenticated()`: allow, block, or require authentication.
- `hasAuthority("DOC_READ")`, `hasRole("ADMIN")`: check permissions held in `Authentication`.
- `requestMatchers(...)`: bind policies to groups of HTTP requests.
- `@PreAuthorize("...")`, `@PostAuthorize("...")`: check at method boundaries.
- `RoleHierarchy`, `PermissionEvaluator`, beans invoked via SpEL: extend common checks.

Those options are often sufficient. However, some real-world questions look like this:

> A user has the `DOC_READ` authority, belongs to tenant A, and requests document 42. Does document 42 belong to tenant A, is it unlocked, is the user a share recipient or the owner, and does the current policy permit the action?

A single authority check cannot on its own know the owner or document status. Embedding too many SpEL expressions directly into configuration also makes policies hard to read and hard to test. In this case, you can write Java logic and place it into an **`AuthorizationManager<T>`**. This is the interface Spring Security uses to ask a component whether an `Authentication` is allowed to access an object `T`.

**This lesson focuses on the decision to choose `AuthorizationManager` when built-in rules are not enough**, including alternatives, defining a manager with the right target type, combining built-in managers with custom policy, attaching to HTTP/method security, fail-closed behavior, testing, and operations.

The intended conclusion is not "whenever you have custom business logic, write a custom manager." Choose a custom manager **only when its benefits in policy modeling, reuse, and testability clearly outweigh simpler mechanisms**.

## 2. Where Does `AuthorizationManager` Sit?

In modern Spring Security, `AuthorizationManager` is the abstraction for an authorization decision. For Servlet applications:

```text
HTTP request
  |
  v
SecurityFilterChain
  |
  v
Authentication filters -> SecurityContext / Authentication
  |
  v
AuthorizationFilter
  |
  v
RequestMatcher selects the matching rule
  |
  v
AuthorizationManager<RequestAuthorizationContext>
  |
  +-- GRANT -> allow request to proceed
  |
  +-- DENY  -> AccessDeniedException -> response via exception handling
```

For method security:

```text
Caller -> Spring AOP proxy of service
            |
            v
 AuthorizationManagerBeforeMethodInterceptor
            |
            v
 AuthorizationManager<MethodInvocation>
            |
        GRANT / DENY
            |
            v
       Target method (if allowed)
```

Both contexts use the `AuthorizationManager` model, but **the input type differs**:

| Enforcement point | Manager type | Provided data |
| --- | --- | --- |
| HTTP Servlet `authorizeHttpRequests` | `AuthorizationManager<RequestAuthorizationContext>` | `HttpServletRequest`, path variables extracted by the matcher |
| Before service invocation | `AuthorizationManager<MethodInvocation>` | Target, method, arguments |
| After service invocation | `AuthorizationManager<MethodInvocationResult>` | Method invocation along with return value |
| Messaging or Reactive | Corresponding context types | Depends on integration and runtime |

**Do not confuse** `AuthorizationManager<RequestAuthorizationContext>` with `AuthorizationManager<MethodInvocation>`. They share the same interface, but the type parameter `T` determines what information the manager can read and where it is attached.

### Role and Boundaries

`AuthorizationManager` decides **allow/deny**. It does not authenticate users itself, run SQL in a transaction on its own, create an AOP proxy by itself, replace data validation rules, or automatically apply everywhere just because it has `@Component`.

On the web side, `AuthorizationFilter` invokes the manager via the `.access(...)` rule. On the method side, an appropriate interceptor/advisor invokes the manager when the call passes through a Spring proxy.

## 3. When Are Built-In Rules Still the Better Answer?

Before writing your own manager, ask: "What data does the rule actually depend on?"

| Need | Preferred option | Need custom manager? |
| --- | --- | --- |
| Public API or completely blocked | `permitAll` / `denyAll` | No |
| Must be logged in to access | `authenticated` | No |
| Require exact authority `INVOICE_READ` | `hasAuthority` | No |
| ADMIN can view all endpoints in a group | `hasRole` + matchers | Usually no |
| Higher roles imply lower roles | `RoleHierarchy` | Usually no |
| Require both `APPROVE` and `FINANCE` | `AuthorizationManagers.allOf(...)` or equivalent built-in config | Usually no |
| Only one of two groups may access | `AuthorizationManagers.anyOf(...)` | Usually no |
| Method needs a simple owner check | `@PreAuthorize("@policy.canRead(authentication,#p0)")` | Possibly no |
| Already have domain permissions via `hasPermission` | `PermissionEvaluator` | Possibly no |
| Rule coordinates tenant, owner, status, exceptions, multiple data sources | Java policy or custom `AuthorizationManager` | May fit |
| Must use the same custom authorization engine across many HTTP routes | Custom `AuthorizationManager<RequestAuthorizationContext>` | Fits |
| Need a Java policy for service methods with a dedicated pointcut | `AuthorizationManager<MethodInvocation>` and advisor | Fits |
| Delegate decisions to an external policy engine/PDP | Custom manager with timeout, audit, fail-closed | Fits, requires operational design |
| Only need to validate body, amount, email format | Bean validation/business validation | Do not turn input errors into permissions |
| Need to distinguish HTTP 400/409/422 status codes | Validation/exception handling in web/application layer | Not the sole responsibility of the manager |

**Practical order of consideration:**

1. Built-in rules and existing managers.
2. Combine managers with `allOf`/`anyOf` or use a hierarchy.
3. Move business logic into a Java policy bean and invoke it from `@PreAuthorize`, if there are only a few attachment points.
4. Create a custom `AuthorizationManager<T>` when you need a formal extension point, reuse across many places, complex policies, or complete separation from expressions.
5. Customize framework advisors/`AuthorizationManagerFactory` when you need an **infrastructure-wide policy**, not just a single business rule.

There is no threshold such as "if an expression exceeds 100 characters, switch to a manager." The decision depends on scope, input data, testability, and the policy's change lifecycle.

## 4. The `AuthorizationManager<T>` Contract

Spring Security 6.5+ and 7.x provide the core API:

```java
AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T object);
```

`Authentication` is supplied via `Supplier`; `T` is the object to check. `AuthorizationResult` indicates the decision through `isGranted()`. A common way to return a result is `new AuthorizationDecision(true)` or `new AuthorizationDecision(false)`.

An **integration snippet** illustrating a manager that only checks an authority without reading the HTTP request:

```java
public final class DocumentReadManager<T>
        implements AuthorizationManager<T> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            T context) {
        Authentication auth = authentication.get();

        boolean allowed = auth != null
                && auth.isAuthenticated()
                && auth.getAuthorities().stream()
                    .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

To compile this snippet in the corresponding Spring Security application, imports are required:

```java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

This snippet is **intentionally simple to show the contract**; in a real application, checking only `DOC_READ` should use `AuthorityAuthorizationManager.hasAuthority("DOC_READ")`. Writing a custom class here is redundant.

### `authorize`, `check`, `verify`, and Undecided Results

- `authorize(...)` is the API to use in new code. Spring Security 6.5 marked `check(...)` deprecated; avoid writing new integrations that only override `check`.
- `verify(...)` uses the manager's decision and throws an error when denied, typically `AccessDeniedException`.
- `AuthorizationResult.isGranted()` distinguishes allow from deny.
- Some managers may return `null` to **abstain**, meaning they make no decision. This is an intentional contract, not an appropriate default for every rule.
- Once a policy has determined it is responsible for checking that route/method, errors such as ID parse failure, missing data, tenant mismatch, or an unavailable PDP should be **explicitly denied** or converted into a defined operational error. Do not return `null` merely because error handling is incomplete.

`AuthorizationManager` is a functional interface, so a lambda can be used:

```java
AuthorizationManager<RequestAuthorizationContext> manager =
        (authentication, context) -> {
            boolean allowed = /* policy check goes here */;
            return new AuthorizationDecision(allowed);
        };
```

The snippet above only illustrates the signature; `/* policy check goes here */` is not a standalone runnable boolean expression. In the complete example in section 8, we implement it in full.

### Benefit of `Supplier<Authentication>`

Spring Security can defer fetching `Authentication`. A simple manager like `permitAll` does not necessarily call `authentication.get()`. A custom manager should only read authentication when the policy needs it. Do not assume the supplier always returns a `UserDetails` principal: JWT systems may have a `JwtAuthenticationToken` or another authentication type; rely on stable contracts such as `Authentication#getName`, authorities, and properly validated claims.

## 5. Choose the Right Context Before Writing Policy

### 5.1. At the HTTP Layer

An HTTP manager receives `RequestAuthorizationContext`, which has:

- `getRequest()`: `HttpServletRequest`.
- `getVariables()`: path variables extracted by the request matcher, for example `id` from `/documents/{id}` when supported by the matcher.

It fits policies needing HTTP method, path, IP, header, principal, or route-level permissions. However, note: **headers and query/body values from the client are not self-proving trustworthy data** to assert that a user owns a resource. For owner/tenant, look up a server-side repository or policy service.

Do not parse a JSON body from `HttpServletRequest` inside an authorization filter just to make a decision, because you easily hit already-read streams, payload size issues, encoding issues, and duplicate reads. If a policy mainly depends on a validated DTO or a domain object loaded from the DB, method security/application service usually has better context.

### 5.2. At the Method Layer

A method manager receives `MethodInvocation`: `getMethod()`, `getArguments()`, `getThis()`, etc. It can inspect already Java-bound/validated arguments and decide at the service boundary. For the manager to run, you need **a method interceptor/advisor or corresponding annotation configuration**, and the call must go through a Spring AOP proxy.

For policies that depend on the return value, post-invocation method security uses `MethodInvocationResult`. Do not protect write operations solely by checking after side effects have already occurred.

### 5.3. Sharing One Policy, Multiple Adapters

If the same rule "user X may view document Y in tenant Z" is needed at both HTTP **and** service layers, extract the business logic into a plain Java service:

```text
HTTP AuthorizationManager<RequestAuthorizationContext>
                |
                v
       DocumentAccessPolicy
                ^
                |
Method AuthorizationManager<MethodInvocation>
```

The two managers are responsible for **extracting information from the context** and passing it to `DocumentAccessPolicy`. The policy uses trusted authentication and repository data. Do not duplicate two permission algorithms that can drift apart; nor force every adapter into a single `AuthorizationManager<Object>` with many `instanceof` checks across contexts.

## 6. When Should You Compose Built-In Managers?

Spring Security provides the `AuthorizationManagers` combinator, for example:

```java
AuthorizationManagers.allOf(
    AuthorityAuthorizationManager.hasAuthority("DOC_READ"),
    documentOwnerAuthorizationManager
)
```

Intended policy meaning: **has read authority AND satisfies owner condition**. With the OR option:

```java
AuthorizationManagers.anyOf(
    AuthorityAuthorizationManager.hasRole("SUPPORT"),
    documentOwnerAuthorizationManager
)
```

This means the SUPPORT group is allowed under its own rule, or the user is the owner. **Warning:** letting SUPPORT access documents of all tenants is a sensitive security decision; it must have clear business requirements, auditing, and cross-tenant tests.

Composition lets you reuse simple parts instead of reimplementing them inside a custom manager. When a manager can `abstain`, you must understand how the combinator handles undecided cases and test all allow/deny/abstain combinations. **Never put a required rule in an OR branch where another branch could accidentally bypass it.**

### HTTP Matcher Rules Are Ordered

`authorizeHttpRequests` evaluates rules in declaration order; the first matching rule can decide access for the request. Placing `anyRequest().permitAll()` too early can prevent specialized rules from ever being applied.

To reduce accidental permission leaks, put specific rules first and a strict catch-all:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

This is an **integration configuration snippet**, not a standalone Java file. `anyRequest().denyAll()` only makes sense if the team has enumerated every route that needs access; actuator, static resources, and error/forward dispatches must be accounted for according to the application architecture.

## 7. Model the Policy Before Coding

Suppose a document system has server-side fields: `documentId`, `tenantId`, `ownerId`, `status`; the user has `subjectId`, allowed tenants, and authorities.

Business requirement:

> Allow reading a document when the caller is authenticated, has `DOC_READ`, the document exists, belongs to the same tenant, is in a readable state, and the caller is the owner or has a share grant; deny all other cases.

Break down the conditions:

```text
ALLOW =
    authenticated
    AND has(DOC_READ)
    AND document_exists
    AND tenant_matches
    AND readable_state
    AND (is_owner OR has_share_grant)
```

Additional decisions to make:

- Do exception privileges for admin/support apply across tenants?
- Must deleted, locked, or suspended documents be denied?
- Should a non-existent ID and an existing ID without permission return the same response to avoid enumeration?
- If the repository errors/times out, how do we fail closed?
- How long can permission results be cached; when does revocation take effect?
- If checking and writing a document together, permissions and state can change between the two steps; how are transactions/locking/versioning used for consistency?
- What must audit logs record to explain decisions without leaking sensitive data?

Answering those questions before choosing an implementation avoids cramming an incomplete policy into a few-line lambda.

## 8. Spring Boot 3.5.16, Java 17 Example: Custom HTTP AuthorizationManager

The example **can be compiled and run in a Maven project**. To keep the exercise self-contained without a DB, the "data repository" is replaced by an immutable server-side `Map<Long, String>`: document `42` belongs to `alice`, document `7` belongs to `bob`.

Demo policy: the caller must have authority `DOC_READ` **and** be the owner of the requested document. We use the built-in manager for the authority, a custom manager for ownership, and combine them with `allOf`.

**Version note:** Spring Boot `3.5.16` is a released version using Spring Security 6.x, suitable for demonstrating the API. The Boot 3.5 line has reached end of OSS support; for production projects, choose a still-supported Spring Boot/Security branch and verify the APIs before deploying. The example application uses HTTP Basic with `{noop}` passwords **for instructional purposes only**, not as a real-world security mechanism.

### 8.1. Structure

```text
custom-manager-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       └── CustomManagerApplication.java
    └── test/
        └── java/demo/
            └── DocumentAuthorizationTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>custom-manager-demo</artifactId>
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

### 8.3. `src/main/java/demo/CustomManagerApplication.java`

```java
package demo;

import java.util.Map;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomManagerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomManagerApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, DocumentOwnerAuthorizationManager owner)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
                .access(AuthorizationManagers.allOf(
                    AuthorityAuthorizationManager.hasAuthority("DOC_READ"),
                    owner))
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}demo")
                .authorities("DOC_READ")
                .build(),
            User.withUsername("bob")
                .password("{noop}demo")
                .authorities("DOC_READ")
                .build(),
            User.withUsername("charlie")
                .password("{noop}demo")
                .authorities("OTHER")
                .build()
        );
    }
}

@Component
final class DocumentOwnerAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    // Simulated server-side data; in production, use a trusted repository.
    private final Map<Long, String> owners =
            Map.of(42L, "alice", 7L, "bob");

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        String rawId = context.getVariables().get("id");
        if (rawId == null || !rawId.matches("[1-9][0-9]*")) {
            return new AuthorizationDecision(false);
        }

        final long documentId;
        try {
            documentId = Long.parseLong(rawId);
        } catch (NumberFormatException invalidOrOverflow) {
            return new AuthorizationDecision(false);
        }

        String owner = owners.get(documentId);
        if (owner == null) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authenticationSupplier.get();
        boolean granted = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)
                && owner.equals(auth.getName());

        return new AuthorizationDecision(granted);
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    @GetMapping("/{id}")
    String read(@PathVariable long id) {
        return "document-" + id;
    }
}
```

**Code walkthrough:**

1. `SecurityFilterChain` applies the rule to GET `/api/documents/{id}`. The rule combines `hasAuthority("DOC_READ")` and `DocumentOwnerAuthorizationManager`. Other HTTP requests are denied by `denyAll` in the demo.
2. `RequestAuthorizationContext.getVariables().get("id")` retrieves the path variable extracted by a supporting matcher. If missing, not a positive integer, or overflowing, the manager returns deny.
3. `owners` is server-side data; the caller cannot claim ownership by adding an `X-Owner` header.
4. The manager calls `authenticationSupplier.get()` when it needs to verify identity, checks for anonymous, and compares against the owner.
5. `new AuthorizationDecision(false)` demonstrates fail-closed behavior: a non-existent ID or missing permission is never granted access.
6. The controller **does not check permissions itself** because requests must pass through the filter chain. In production, the service layer should still enforce domain permission checks when it can be invoked from other entry points such as batch jobs, events, or messaging.
7. The `Map` and `{noop}` plaintext passwords are used intentionally so the demo is easy to run. Production needs trusted owner/tenant data, a proper password encoder, HTTPS, auditing, and real business logic.

Note that the matcher defines variable `{id}`; if you switch to a matcher that does not supply path variables or rename `{id}` to `{documentId}` without updating the manager, the rule will deny due to the missing variable. Write integration tests for the actual matcher configuration.

### 8.4. Running the Application

On a machine with JDK 17+ and Maven, inside the directory containing `pom.xml`:

```bash
mvn -q clean package
java -jar target/custom-manager-demo-1.0.0.jar
```

In another terminal:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo \
  http://localhost:8080/api/documents/42

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo \
  http://localhost:8080/api/documents/7

curl -s -o /dev/null -w '%{http_code}\n' -u bob:demo \
  http://localhost:8080/api/documents/7

curl -s -o /dev/null -w '%{http_code}\n' -u charlie:demo \
  http://localhost:8080/api/documents/42
```

Expected HTTP status results for the four commands above (one line printed per command):

```text
200
403
200
403
```

An allowed GET returns body `document-42` for `alice/42` and `document-7` for `bob/7`. `alice/7` is denied because she is not the owner; `charlie/42` is denied at the `DOC_READ` authority check.

When unauthenticated, default HTTP Basic may return `401 Unauthorized`. In applications with session/login or custom exception handlers, the exact HTTP status depends on entry point and access-denied handling configuration. Do not assume one fixed set of status codes across all systems.

### 8.5. `MockMvc` Integration Tests

File `src/test/java/demo/DocumentAuthorizationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerWithAuthorityCanRead() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("document-42"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void readerCannotReadOtherOwnersDocument() throws Exception {
        mvc.perform(get("/api/documents/7"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "charlie", authorities = "OTHER")
    void ownerRuleCannotBypassAuthorityRule() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void secondOwnerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/7"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void unknownDocumentIsDenied() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
mvn -q test
```

The tests send real requests through `SecurityFilterChain`, exercising both authority and ownership rather than calling `DocumentController.read(42)` directly. Calling the controller directly would **bypass the request authorization filter**, because the manager is attached at the HTTP layer.

**Why does the "unknownDocument" test return 403?** In the demo, the policy returns deny when the ID is not in `owners`. A production API may prefer not to reveal whether a resource exists or define its own policy to return `404`; this must be coordinated between policy and exception handling rather than throwing an ad-hoc exception inside the policy that leaks existence.

## 9. How to Attach a Custom AuthorizationManager to Method Security?

The HTTP manager in section 8 only protects HTTP requests. If the same service can be called directly by a job, listener, or another service, a boundary is needed at the method level.

Suppose you have:

```java
@Service
public class ApprovalService {
    public void approve(long documentId) {
        // Persist approval state using the application repository.
    }
}
```

The **least complex** option may still be a policy bean:

```java
@PreAuthorize("hasAuthority('DOC_APPROVE') and " +
              "@approvalPolicy.canApprove(authentication, #p0)")
public void approve(long documentId) {
    // ...
}
```

These are **integration snippets**, not standalone runnable code because `approvalPolicy` and the repository belong to the application. They show that when only one method has custom Java rules, you can avoid writing a new `AuthorizationManager<MethodInvocation>`.

If you need a **Java advisor applied across multiple methods** or want to replace how annotations produce decisions, you can create a `MethodInvocation`-typed manager.

### 9.1. Custom Method Manager

```java
@Component
public final class ApprovalAuthorizationManager
        implements AuthorizationManager<MethodInvocation> {

    private final ApprovalPolicy policy;

    public ApprovalAuthorizationManager(ApprovalPolicy policy) {
        this.policy = policy;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        if (invocation.getArguments().length != 1
                || !(invocation.getArguments()[0] instanceof Long id)) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authentication.get();
        boolean granted = auth != null
                && auth.isAuthenticated()
                && policy.canApprove(auth, id);

        return new AuthorizationDecision(granted);
    }
}
```

Required imports:

```java
import java.util.function.Supplier;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

`ApprovalPolicy` is an application bean. It checks permissions from server-side data (tenant, owner, status, role, etc.) and returns a boolean. This is an **illustrative integration snippet**, not claimed to run standalone without implementing `ApprovalPolicy`.

Key point: the manager inspects **method arguments** in `MethodInvocation`, without re-parsing HTTP requests. Because the method parameter is `long`, reflection arguments box it as `Long`. If the method signature or parameter order changes, the policy and tests must be updated.

### 9.2. Attaching the Manager to an Advisor with a Pointcut

```java
@Configuration
@EnableMethodSecurity
public class ApprovalMethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor approvalAdvisor(ApprovalAuthorizationManager manager) {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public * demo.ApprovalService.approve(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut, manager);
    }
}
```

Main imports:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

The code assumes the real package and class match `demo.ApprovalService`, are Spring-managed, non-`final`, and invoked through a proxy. Method Security infrastructure must be properly initialized; this advisor applies only to the specified pointcut.

**Caution when combining:** if the same method has both `@PreAuthorize` and a custom advisor, **multiple** checks may run. Do not silently turn "OR" into "AND" or vice versa via advisor ordering. Define the policy explicitly and test every branch. If you want to **replace** the default `@PreAuthorize`/`@PostAuthorize` advisors, Spring Security provides `@EnableMethodSecurity(prePostEnabled = false)` followed by registering corresponding interceptors, but that affects method security application-wide; do not use it just to fix a single method.

### 9.3. Why Not Attach the HTTP Manager Directly to Methods?

Because `RequestAuthorizationContext` knows the servlet request and path variables; `MethodInvocation` knows the Java method and its arguments. When sharing a policy, extract ID/user from each context type and delegate to a shared `ApprovalPolicy` or `DocumentAccessPolicy`. Separating adapters is intentional to avoid coupling web and service layers and to avoid protecting the HTTP path while leaving schedulers exposed.

## 10. When Should Framework Managers Be Replaced at the Infrastructure Level?

There is a major difference between:

- **Business policy:** "a document may only be viewed by a user belonging to its tenant with read permission."
- **System-wide convention:** "every `hasRole` rule must also treat special role X as satisfied" or "all pre-authorization must go through a single decision engine."

For method-level policies affecting only a subset of services, a custom advisor or policy bean is usually enough. For policies that change how the framework builds `AuthorizationManager` instances for expressions/roles, newer Spring Security versions provide **`AuthorizationManagerFactory`** as the customization hook.

In Spring Security 7, the method security documentation includes examples of creating a custom `AuthorizationManagerFactory<MethodInvocation>` to tailor the managers produced for `hasRole`/`hasAnyRole`. That is a better path than copying entire framework interceptors just to change one convention. Check the API and registration style for your **exact version**, because recommended factories and setters differ between Spring Security 6.x and 7.x.

Illustrative goal diagram (not standalone runnable Java):

```text
Application policy convention
          |
          v
AuthorizationManagerFactory<MethodInvocation>
          |
          +-- hasRole("EDITOR") -> manager per internal convention
          +-- hasAnyRole(...)  -> manager per internal convention
          |
          v
Method security annotations / advisors
```

Do not use `AuthorizationManagerFactory` just to handle "owner of document 42", as doing so pushes a business rule into global infrastructure.

## 11. Immutable Policy vs. Dynamic Data: Avoiding TOCTOU Bugs

Custom managers often query the database: `policy.canRead(authentication, docId)`. That is a check at **a single point in time**.

For **read** operations, checks can be placed at HTTP or service layers, though leaking data before the check must be avoided. For **write** operations, if the manager checks owner/state and the write transaction runs afterwards, the resource can change owner or state in between (time-of-check/time-of-use).

Example:

```text
T1: AuthorizationManager reads owner = alice -> GRANT
T2: Admin transfers owner to bob
T3: alice's service writes update -> may exceed current permissions
```

How to handle this depends on your consistency contract:

- Re-check sensitive permissions and state inside the business transaction, using locking or optimistic versioning when needed.
- Ensure the repository only modifies records matching the required tenant/owner condition (conditional update) or verifies the version.
- Do not assume `@Transactional` automatically makes two before/after queries immune to races; transaction isolation and locking must be chosen explicitly.
- For distributed systems/remote PDPs, define permission freshness, token lifetime, cache TTL, invalidation, and compensation mechanisms when a shared transaction is impossible.

`AuthorizationManager` makes the authorization decision, while **atomicity and data consistency** remain the responsibility of application/transaction/storage design.

## 12. When the Decision Source Is an External Service

Some systems use a standalone policy engine (for example OPA, or an internal RBAC/ABAC service). The custom manager acts as an adapter:

```text
Spring Security interceptor
  -> Custom AuthorizationManager
      -> normalize subject + resource + action + tenant
      -> call PDP/authorization service
      -> verify response/version/signature if required by contract
      -> return GRANT or DENY
```

Key principles:

- Send only the required identity/claims and resource metadata; avoid forwarding raw tokens or unnecessary personal data.
- Set tight deadlines/timeouts, limit concurrency and connection pools so authorization does not become a bottleneck.
- Decide **fail-closed** if the authorization service cannot confirm the policy. If the application chooses to return `503` instead of `403` when the policy service fails, design exception handling to distinguish system failures from denials; never grant access on timeout.
- Define cache keys including subject, tenant, resource, action, policy version, and attributes affecting the decision. TTL must align with permission revocation requirements.
- Audit allow/deny, latency, system reason, and policy version with minimal data. Never log secrets or full JWTs.
- Test circuit breakers, bounded retries, network errors, malformed JSON parsing, policy changes, and slow responses.

A manager may call an external PDP; it **must not create resources, mutate ACLs, grant roles, or modify the database** merely to make a decision. Decision logic should avoid side effects and remain repeatable for the same inputs and policy state.

## 13. Common Pitfalls When Writing a Custom AuthorizationManager

### Pitfall 1: Using a custom manager to check a single authority

```java
boolean allow = auth.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("DOC_READ"));
```

If that is the only condition, use `AuthorityAuthorizationManager.hasAuthority("DOC_READ")`. A custom class only adds lines of code and more surface to test.

### Pitfall 2: Not wiring the manager anywhere

```java
@Component
class CustomAuthz implements AuthorizationManager<RequestAuthorizationContext> {
    // ...
}
```

Registering a bean **does not mean the manager automatically protects all requests**. You must explicitly wire `.access(customAuthz)` on the matching rule; similarly, a method manager requires an advisor/interceptor.

### Pitfall 3: Allowing when data is insufficient

```java
if (document == null) {
    return new AuthorizationDecision(true); // Wrong for a policy that requires the document.
}
```

When owner, tenant, or policy is undetermined, deny according to contract. Do not treat ID parse errors, missing principals, or repository timeouts as reasons to pass through.

### Pitfall 4: Confusing `abstain` with deny

`null` means undecided, not deny. For an adapter attached directly to a sensitive endpoint, explicitly return `AuthorizationDecision(false)` when conditions are not met. If intentionally using abstain in a composition, test the behavior of the outer manager and fallback.

### Pitfall 5: Comparing owner with a client header

```java
String owner = request.getHeader("X-Owner"); // Client can spoof this.
```

A malicious user can send arbitrary values. Only use authenticated identity/tenant and owner fetched from trusted data.

### Pitfall 6: Ignoring tenant

If `documentId` is only unique within a tenant, querying `findById(id)` without tenant filtering can grant cross-tenant access, especially when IDs overlap. The policy must treat tenant as part of resource identity or query scope.

### Pitfall 7: Reading the request body in the filter to inspect fields

Reading the body stream inside an authorization manager can leave no data for the controller, cause deserialization failures, consume excessive RAM, or allow abuse via large payloads. For complex domain data, method security and validation at the application layer are more appropriate.

### Pitfall 8: Relying solely on `Authentication.isAuthenticated()`

An anonymous authentication token can have `isAuthenticated() == true`. Understand authentication semantics and do not equate "has a context" with "is authorized." Use authorities/roles and check anonymous/fullyAuthenticated as required.

### Pitfall 9: Forgetting proxies in method security

Annotations or custom advisors only take effect when calls pass through a Spring proxy. `new Service()` or `this.securedMethod()` can bypass security advice in proxy mode. The usual fix is injecting the bean and keeping service boundaries clear.

### Pitfall 10: Applying the same manager to every request without restricting matchers

`anyRequest().access(manager)` can intercept static assets, health checks, login callbacks, actuator, and error dispatches. If the policy is only for documents, restrict with `requestMatchers("/api/documents/**")` and define a fallback. Test route coverage.

### Pitfall 11: Testing by calling the manager directly and assuming the endpoint is secure

Unit testing the manager proves the algorithm. Integration testing through `MockMvc` or the method proxy proves **config/pointcut/bean wiring** actually triggers the manager. Sensitive policies need both.

### Pitfall 12: Mixing authorization with validation/business conflicts

If an invoice is already paid and editing it causes a state conflict, many systems choose 409 rather than 403. Clearly distinguish "this user lacks permission" from "the operation is invalid for the current state." Some states may belong to authorization policy, yet still require a clear error API contract.

## 14. Testing with a Decision Matrix

Custom managers must be tested at two levels.

**Level 1 — Policy unit tests:** invoke the manager directly with mocked `Authentication`/`RequestAuthorizationContext` and a fake repository; test allow, deny, null/anonymous, non-existent resource, tenant mismatch, malformed ID, PDP timeout, and data edge cases.

**Level 2 — Wiring integration tests:** send real HTTP requests through the Spring Security filter chain or invoke the Spring bean method through the AOP proxy; verify matching routes/pointcuts, exceptions/HTTP statuses, combined advisors, and principal/tenant propagation.

Minimum matrix for the document example:

| Authentication | Authority | Resource | Other condition | Result |
| --- | --- | --- | --- | --- |
| alice | DOC_READ | Doc 42, owner alice | valid | ALLOW |
| alice | DOC_READ | Doc 7, owner bob | valid | DENY |
| alice | OTHER | Doc 42, owner alice | valid | DENY |
| anonymous | None | Doc 42 | unauthenticated | DENY |
| alice | DOC_READ | Non-existent Doc 999 | owner not found | DENY |
| alice | DOC_READ | Unparseable ID | invalid path data | DENY |
| alice tenant A | DOC_READ | Doc tenant B | owner might match | DENY |
| alice | DOC_READ | Doc 42 | PDP/repository timeout | DENY or defined system error, never ALLOW |
| admin | ADMIN | Doc tenant B | exception branch | ALLOW only if explicitly permitted by policy |

Specifically include a **negative-path** test: temporarily remove `.access(ownerManager)` in a test environment and verify that the owner mismatch test fails. This ensures the test actually verifies the manager is wired, not just that the endpoint always returns 200.

Update/delete must be tested separately because `DOC_READ` must not implicitly grant `DOC_WRITE`. For the same path with different HTTP methods, configure distinct matchers by `HttpMethod`.

## 15. Performance, Observability, and Maintenance

Because a manager can be invoked on **every request or every method invocation**, measure its cost:

- Only call `authentication.get()` and repositories when actually needed; avoid DB reads for public routes.
- Avoid N+1 queries when checking lists in a loop if batching is possible.
- Set explicit timeouts when calling a PDP; track deny rates, backend errors, and p95/p99 latency.
- Consider caching keyed by tenant + resource + action + policy version, not username alone.
- Avoid caching allow decisions too long such that revoked permissions remain effective.
- Log decision ID/method/resource at an appropriate level; never log passwords, access tokens, or full bodies.
- When policies change, version them and run regression tests for both prior and new permissions.
- Maintain a clear inventory of matchers/advisors mapped to each policy; avoid overlapping hidden rules that make decisions hard to explain.
- Restrict special admin privileges, audit overrides separately, and always enforce tenant checks if required by the organization.
- Across multiple instances, caches/policy backends must stay consistent within committed bounds.

A well-written `AuthorizationManager` is usually a **thin adapter**: extract context, delegate to a domain policy, and convert the outcome into an `AuthorizationResult`. Logic with hundreds of branches should live in focused business classes with dedicated unit tests.

## 16. Version Considerations and Legacy Mechanisms

Spring Security 6/7 uses `AuthorizationManager` in place of older extension points like `AccessDecisionManager` and `AccessDecisionVoter` in modern authorization flows. When reading older documentation that suggests writing an `AccessDecisionVoter` or extending `GlobalMethodSecurityConfiguration`, cross-check the API against your running version.

Key points to note:

- Spring Security 6.5 provides `authorize(...)` and `AuthorizationResult`; `check(...)` is deprecated. Base new implementations on `authorize`.
- `authorizeHttpRequests` uses `AuthorizationFilter` and `AuthorizationManager`; the older `authorizeRequests` configuration relies on a different mechanism.
- `@EnableMethodSecurity` enables modern method security compatible with `AuthorizationManager`. Spring Boot Starter Security alone **does not** enable method-level authorization.
- HTTP `AuthorizationManager<RequestAuthorizationContext>` and method `AuthorizationManager<MethodInvocation>` are two distinct adapters.
- Spring Security 7 expands `AuthorizationManagerFactory` for customizing how built-in rules build managers; consult documentation for your exact version before copying code.
- For reactive systems, do not copy Servlet `HttpSecurity` / `RequestAuthorizationContext` verbatim: use the reactive security DSL and corresponding authorization types.

Do not upgrade frameworks simply by swapping packages/imports. Re-run tests covering allow/deny, composed rules, anonymous access, matchers, authentication, transactions, and exception handling.

## 17. Review Questions

**1. If you only want to check `DOC_READ`, do you need a custom manager?** No. Use `hasAuthority("DOC_READ")`. A custom manager is only needed when part of the policy cannot be clearly expressed with built-in rules or when a shared adapter is needed.

**2. When is `@PreAuthorize("@policy.check(authentication,#p0)")` sufficient?** When the policy applies to a few service methods, no custom advisor/pointcut is needed, and calling a policy bean is straightforward. The Java logic inside the bean can still be unit-tested.

**3. Does a custom manager run automatically because it is `@Component`?** No. You must wire `.access(manager)` in HTTP security or create a corresponding method advisor/interceptor.

**4. Why not write a single shared manager for both HTTP and methods?** Because the context types carry different data and have different lifecycles. Share the **domain policy** and write a thin adapter for each layer.

**5. Should `null` be returned when a document is not found?** If the manager is responsible for protecting that resource, usually return an **explicit DENY**. `null` means abstain and should only be used when the decision-combining framework is designed for that scenario.

**6. Does a custom manager replace transactions?** No. For writes, consistency, concurrent changes, and transactions must be handled separately. An allow at T1 does not guarantee data remains unchanged at T2.

**7. Can a manager call an external policy API?** Yes, but it requires timeouts, fail-closed behavior, auditing, sensible caching, and failure handling; never grant access when the PDP fails to return a trustworthy result.

**8. Why is testing the manager directly not enough?** It does not prove the request matcher, `SecurityFilterChain`, proxy, or advisor is wired. Integration tests through the real entry point are required.

## 18. Selection and Implementation Checklist

- [ ] Described the policy with clear conditions and agreed on missing/deny/abstain behavior.
- [ ] Tried `hasAuthority`/`hasRole`, matchers, `RoleHierarchy`, `AuthorizationManagers.allOf/anyOf`.
- [ ] For method security, evaluated a Java bean invoked from `@PreAuthorize` before writing a custom advisor.
- [ ] Chose the right `AuthorizationManager<T>` for HTTP, method, or another context.
- [ ] Wired the manager to the right matcher/advisor; did not merely create a bean.
- [ ] Policy checks identity, tenant, and resource from trusted server-side data, defaulting to deny.
- [ ] Distinguished authorization errors from data/business errors; HTTP statuses are defined in the API contract.
- [ ] Standalone policy produces no side effects; external PDP has timeouts, fail-closed behavior, and monitoring.
- [ ] Have both decision unit tests and integration tests proving routes/pointcuts are genuinely protected.
- [ ] Checked proxy/self-invocation for methods, and transactions/TOCTOU for writes.
- [ ] Checked the active Spring Security version and avoided unnecessary legacy/deprecated APIs.
- [ ] Admin overrides, tenant isolation, auditing, and permission changes are tested as distinct use cases.

**Key takeaway:** Choose a custom `AuthorizationManager` when you need a **clear, properly context-typed, reusable, and independently testable authorization decision unit**. Keep using built-in managers for simple checks; move business logic into Java policies; and attach the manager at the exact HTTP/method boundary so Spring Security actually enforces that decision.

## References

- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security and custom AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — JavaDoc AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — Method Security and AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Boot 3.5.16 release notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)
