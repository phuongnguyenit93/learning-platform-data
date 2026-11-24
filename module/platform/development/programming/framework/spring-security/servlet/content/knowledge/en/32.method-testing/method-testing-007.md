# Testing @PreAuthorize, @PostAuthorize, and Parameter-Based Authorization

> **Context:** Spring Security on the **Servlet stack**, Spring Boot 3.x, Spring Security 6.x, Java 17+, and JUnit 5. The goal is testing **method-level authorization**, specifically `@PreAuthorize` (pre-invocation check), `@PostAuthorize` (post-invocation check), and expressions using **method parameters** or **resource ownership**. Do not confuse these with testing only URL paths in `SecurityFilterChain`.

## 1. Why Must We Protect and Test Directly at the Method Level?

A Spring MVC application typically has three places where a request can be checked for permissions:

1. **HTTP filter chain:** `authorizeHttpRequests(...)` checks URL/HTTP method and authentication status before requests reach controllers.
2. **Method security:** `@PreAuthorize`, `@PostAuthorize`, and related interceptors inspect method calls on Spring-managed beans.
3. **Business authorization:** policies based on resource, owner, tenant, object state, sharing permissions, or workflows invoked from method security/services.

Relying solely on `requestMatchers("/admin/**").hasRole("ADMIN")` does not necessarily protect a service if it is also called from batch jobs, message listeners, other controllers, or internal flows. Method security adds a policy enforcement layer right where business logic runs.

Examples requiring testing:

- User `alice` can read `alice`'s profile page, but cannot use `/owners/bob` to read `bob`'s data.
- An administrator with `ROLE_ADMIN` can read multiple users' pages if policy permits.
- When reading a document, the app only discovers the **true owner** after loading the object from the repository; `@PostAuthorize` can check `returnObject.owner()` before returning the result to the caller.
- Unauthenticated users must not bypass parameter-comparison expressions by picking a username matching the anonymous name.
- Tests must prove **the method itself is blocked** before/after invocation, not just that an HTTP endpoint returned 403 due to another filter.

## 2. Distinguishing @PreAuthorize and @PostAuthorize

### 2.1. @PreAuthorize: Deciding Before the Method Body Runs

`@PreAuthorize` evaluates a Spring Security expression to decide whether to allow an invocation **before executing the method body**:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report exportReport() {
    return reportRepository.loadReport();
}
```

If the principal lacks `ROLE_ADMIN`, the method body does not run. This fits rules whose inputs are known before invocation: roles, authorities, owner parameters, verified tenants, or the result of an authorization service.

A parameter-based expression:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
public String readProfile(@P("owner") String owner) {
    return "profile:" + owner;
}
```

Rule: admins can read; authenticated users can only read profiles matching their own name. `@P("owner")` declares the parameter name for the security expression, avoiding total reliance on parameter name metadata if builds omit `-parameters`.

**Why include `isAuthenticated()`?** `authentication.name` can hold the anonymous placeholder name under default configuration. Checking only `#owner == authentication.name` risks allowing an anonymous principal that happens to match that string. `isAuthenticated()` in Spring Security expression semantics excludes anonymous via `AuthenticationTrustResolver`; do not infer from `Authentication#isAuthenticated()`, since an anonymous token can return true for that method.

### 2.2. @PostAuthorize: Deciding After the Method Body Has Run

`@PostAuthorize` evaluates an expression after the method has **returned a result normally**, with `returnObject` referring to the return value:

```java
@PostAuthorize("hasRole('ADMIN') or (isAuthenticated() and returnObject.owner() == authentication.name)")
public DocumentView readDocument(String id) {
    return documentRepository.load(id);
}
```

When a document belongs to `alice`, user `bob` may trigger the repository load, yet the call through the security proxy still throws `AccessDeniedException` **before returning the object to the caller** if policy forbids reading. `returnObject.owner()` here invokes the accessor of a Java record used as the return type; with traditional POJO getters, use the corresponding property access.

**Crucial limitation:** `@PostAuthorize` **does not prevent the method body from running**. If the method transfers funds, deletes records, calls external APIs, sends emails, or writes to the database, side effects can happen **before** the caller is denied. Never use post-authorization as the sole guard for operations with side effects. For write/update/delete operations, use `@PreAuthorize` or check policy before performing any irreversible action.

### 2.3. Comparison Table

| Criterion | @PreAuthorize | @PostAuthorize |
| --- | --- | --- |
| Evaluation timing | Before method body | After method returns normally |
| Available data | Authentication, roles, authorities, method parameters, security beans/policies | All pre-invocation data, plus `returnObject` |
| Does the method run when unauthorized? | No | It may have run, and then the result is blocked |
| Best suited for | Blocking access before action; rules based on parameters/pre-checked objects | Reading data when owner/policy is known only from the result |
| Suitable for DB write commands? | Usually appropriate | Should not be used as the sole guard |
| Typical denial error | `AccessDeniedException`, body never ran | `AccessDeniedException` after body ran |
| What tests must verify | Repository not called / no side effects on denial | Result not returned to caller; clarity on what already executed |
| Common misconception | "Method protection means every caller goes through the proxy." | "Method denied means the method never ran." |

If the method throws an exception before returning a value, the `@PostAuthorize` expression may **not execute** for that outcome. Therefore test both normal return paths and exception paths. When a method can return `null`, an expression calling `returnObject.owner()` directly must handle null or enforce a non-null contract.

## 3. Enabling Method Security Properly

In Spring Security 6, place `@EnableMethodSecurity` on a Spring configuration class:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // ...
}
```

`@EnableMethodSecurity` enables the method-security interceptor infrastructure (in standard config, pre/post annotations are supported). Do not rely solely on `@EnableWebSecurity` or `http.authorizeHttpRequests(...)` to activate method annotations.

**Runtime check:** if `@EnableMethodSecurity` is forgotten, annotations remain in source yet method bodies execute unchecked. A unit test calling `new DocumentService()` directly also lacks a Spring AOP proxy, so tests may "pass" service logic without testing method security at all.

Common requirements:

- Use Spring-managed beans, e.g. `@Service`, obtained via `@Autowired`/constructor injection.
- Intercepted methods should generally be **public** and invoked by callers **from outside the proxy**. Do not rely on annotations on private methods or internal self-invocation for protection.
- Proxy infrastructure may use JDK or CGLIB proxies depending on classes/interfaces/config; final methods and non-proxiable designs must be evaluated.
- For projects upgrading from older versions, `@EnableGlobalMethodSecurity` is replaced by `@EnableMethodSecurity` in modern Spring Security 6 configuration.
- For the reactive stack, separate infrastructure applies (`@EnableReactiveMethodSecurity`). This article covers **Servlet** only.

### 3.1. What Data Can Security Expressions Read?

Common expression names:

- `authentication`: the current Spring `Authentication`.
- `principal`: the principal inside authentication.
- `hasRole('ADMIN')`: typically looks for authority `ROLE_ADMIN`.
- `hasAuthority('SCOPE_reports.read')`: matches a specific authority without adding a role prefix.
- `isAuthenticated()`: per Spring Security semantics, normally rejects anonymous.
- `#owner` or `#id`: parameter mapped by Spring expression parameter name discovery.
- `returnObject`: useful only post-invocation in `@PostAuthorize`.
- `@policyBean.canRead(authentication, #id)`: invokes a managed policy bean, keeping complex expressions out of annotations.

**Never treat frontend input as the source of truth for permissions:** `#owner` is merely a request parameter that an attacker can alter. Expressions must compare against verified identity or server-side policy lookups. A `documentId` sent by a user **does not prove** the user owns that document.

### 3.2. Parameter Name Discovery and @P

An expression like `#owner == authentication.name` requires mapping variable `owner` to the right argument:

```java
@PreAuthorize("#owner == authentication.name")
public String read(String owner) { ... }
```

This may work when the build preserves `-parameters` metadata, yet fail or evaluate false when metadata is absent. With Spring Security, an explicit approach is `@P`:

```java
import org.springframework.security.core.parameters.P;

@PreAuthorize("isAuthenticated() and #owner == authentication.name")
public String read(@P("owner") String name) {
    return "profile:" + name;
}
```

Here the Java method parameter is `name`, while the Spring method-security expression knows it as `owner` thanks to `@P("owner")`. With multiple arguments, name them clearly and write tests passing the right parameters. Enabling `-parameters` also helps the framework infer parameter names:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Still, when you proactively use `@P`, the rule is explicit right in source rather than depending exclusively on compiler flags.

## 4. End-to-End Example: Owner Parameter and Return-Value Authorization

We build a Spring Boot 3.4.x + Java 17 app with three test users:

- `alice`: `ROLE_USER`.
- `bob`: `ROLE_USER`.
- `admin`: `ROLE_ADMIN`.

The service exposes two methods:

1. `readOwnerPage(owner)` protected with `@PreAuthorize`. Admins can read any owner; regular users can read only their own name.
2. `readDocument(id)` protected with `@PostAuthorize`. The service loads the document, then checks the `owner` field on the result.

A Spring MVC API can invoke the service, yet method-level tests must call **the service bean through its proxy**, rather than only verifying that URL filters block requests.

### 4.1. Project Layout

```text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/methodsecurity/
    │   ├── MethodSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentView.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/methodsecurity/
        ├── DocumentServiceSecurityTest.java
        └── DocumentControllerSecurityTest.java
```

### 4.2. Gradle Dependencies

`settings.gradle`:

```groovy
rootProject.name = 'method-security-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

`spring-security-test` supplies annotations like `@WithMockUser` and `@WithAnonymousUser` as well as `SecurityMockMvcRequestPostProcessors`. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Spring test/MockMvc. Spring Boot manages compatible dependency versions.

### 4.3. Spring Boot Application

`src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
```

### 4.4. SecurityConfig

`src/main/java/com/example/methodsecurity/SecurityConfig.java`:

```java
package com.example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
```

**Why do URLs only require `authenticated()`?** We want to test the method genuinely denying `bob` from reading `alice`'s document, rather than a URL rule blocking upfront. `/owners/{owner}` and `/documents/{id}` are valid HTTP paths requiring login; **the service** decides permissions by owner/result. In production, both URL rules and method security can be applied together, while tests make clear which layer is responsible.

Test passwords use `DelegatingPasswordEncoder` and do not store production passwords. HTTP Basic in this demo requires HTTPS outside localhost. All routes are GET, preserving default CSRF protection.

### 4.5. Return Record

`src/main/java/com/example/methodsecurity/DocumentView.java`:

```java
package com.example.methodsecurity;

public record DocumentView(String id, String owner, String title) {
}
```

The Java record provides accessor `owner()`. This is the `returnObject` evaluated by `@PostAuthorize` in the example.

### 4.6. Spring-Managed Service and Intercepted Methods

`src/main/java/com/example/methodsecurity/DocumentService.java`:

```java
package com.example.methodsecurity;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final Map<String, DocumentView> documents = Map.of(
            "d-alice", new DocumentView("d-alice", "alice",
                    "Notes for Alice"),
            "d-bob", new DocumentView("d-bob", "bob",
                    "Notes for Bob")
    );

    @PreAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and #owner == authentication.name)
            """)
    public String readOwnerPage(@P("owner") String owner) {
        return "profile:" + owner;
    }

    @PostAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and returnObject.owner() == authentication.name)
            """)
    public DocumentView readDocument(@P("id") String id) {
        DocumentView document = documents.get(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }
}
```

**Key points:**

- `@Service` registers the class as a Spring-managed bean; the method security interceptor applies when callers invoke the bean proxy.
- `@PreAuthorize` checks **before** the body; `alice` cannot call `readOwnerPage("bob")` without `ROLE_ADMIN`.
- `@P("owner")` tells the expression which parameter is `#owner`; the real username sits on `authentication.name`.
- `@PostAuthorize` checks **after** `readDocument` fetches the object. For `readDocument("d-alice")`, `bob` is denied after the object is loaded, and the controller never receives the object.
- `readDocument` is **read-only** and does not write to a DB or emit messages; this is an appropriate case for illustrating post-authorization. Never copy this annotation verbatim onto a method with side effects.
- When a document does not exist, the body throws `NoSuchElementException` before producing a return value for `@PostAuthorize`. The controller below maps this exception to HTTP 404; that is a **not-found error**, not proof of authorization.
- The demo uses an in-memory `Map` so test runs are deterministic without external DB or service dependencies.

Although the Java text block above produces a SpEL string with newlines/indentation, the syntax remains valid for Spring Security's parser. If you prefer minimalism or your project config avoids text blocks, write it as a single string:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
```

### 4.7. Spring MVC Controller

`src/main/java/com/example/methodsecurity/DocumentController.java`:

```java
package com.example.methodsecurity;

import java.util.Map;
import java.util.NoSuchElementException;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("result", "public");
    }

    @GetMapping("/owners/{owner}")
    public Map<String, String> ownerPage(@PathVariable String owner) {
        return Map.of("result", service.readOwnerPage(owner));
    }

    @GetMapping("/documents/{id}")
    public DocumentView document(@PathVariable String id) {
        return service.readDocument(id);
    }

    @ExceptionHandler(NoSuchElementException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Map<String, String> notFound() {
        return Map.of("error", "not_found");
    }
}
```

The controller does not hand-code `if ("alice".equals(...))`. It delegates requests to the method-security-protected service bean and only maps `NoSuchElementException` to 404. On unauthorized calls, `AccessDeniedException` is handled by Spring Security's standard exception translation into the matching HTTP response (usually 403 for an authenticated user).

**Important distinction:** in a real app, differing 403 vs. 404 codes can inadvertently reveal whether a document exists. The demo focuses on illustrating the interceptor, whereas production may require anti-enumeration policies, checking permissions by ID **before loading**, or returning consistent errors per the data model.

## 5. Writing Method-Level Tests with Spring Security Test

The tests below obtain `DocumentService` from **Spring `ApplicationContext`**, calling through the method-security proxy. They do not use HTTP, so they pinpoint whether `@PreAuthorize` and `@PostAuthorize` themselves are working.

### 5.1. What Does @WithMockUser Do?

`@WithMockUser` from `spring-security-test` populates a simulated authentication in the test security context, for example:

```java
@WithMockUser(username = "alice", roles = "USER")
```

It sets user `alice` with authority `ROLE_USER`. It **does not** submit passwords through a login form/LDAP/HTTP Basic and does not run password encoders. Its purpose is testing method-security expressions against an established security context.

Key cases to remember:

- `@WithMockUser(username = "admin", roles = "ADMIN")` creates `ROLE_ADMIN`.
- `@WithMockUser(username = "alice", authorities = "SCOPE_read")` creates exact authority `SCOPE_read`, **without** adding `ROLE_`.
- `@WithMockUser` defaults to username `user` and role `USER` if omitted; specify them explicitly to prevent tests from using an unintended identity.
- `@WithAnonymousUser` simulates an anonymous context, verifying `isAuthenticated()` and role checks properly.
- If a real principal from `UserDetailsService` is needed, use `@WithUserDetails`, though that still does not become a real password authentication test.

### 5.2. Complete Tests for @PreAuthorize and @PostAuthorize

`src/test/java/com/example/methodsecurity/DocumentServiceSecurityTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService service;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnPage() {
        assertThat(service.readOwnerPage("alice"))
                .isEqualTo("profile:alice");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCannotReadOthersPage() {
        assertThatThrownBy(() -> service.readOwnerPage("bob"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadAnyOwnerPage() {
        assertThat(service.readOwnerPage("bob"))
                .isEqualTo("profile:bob");
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadOwnerPage() {
        assertThatThrownBy(() -> service.readOwnerPage("alice"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadOwnDocument() {
        DocumentView result = service.readDocument("d-alice");
        assertThat(result.owner()).isEqualTo("alice");
        assertThat(result.title()).isEqualTo("Notes for Alice");
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void userCannotReadOthersDocument() {
        assertThatThrownBy(() -> service.readDocument("d-alice"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadOthersDocument() {
        DocumentView result = service.readDocument("d-alice");
        assertThat(result.owner()).isEqualTo("alice");
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadDocument() {
        assertThatThrownBy(() -> service.readDocument("d-alice"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Why are these genuine method-security tests?** `DocumentService` is autowired from Spring; both annotations are intercepted. URL filters do not participate. If `@EnableMethodSecurity` is omitted, the negative tests fail because the service still returns data instead of throwing `AccessDeniedException` — a valuable test signal.

The tests explicitly cover both **allowed** and **denied** cases rather than only the happy path. This group also verifies `@P("owner")` works. On an ownership-based service, testing arguments not belonging to the user catches IDOR bugs if the owner check is accidentally dropped.

### 5.3. Expected Results Matrix

| Test principal | Method/Call | What Is Tested | Expected Outcome |
| --- | --- | --- | --- |
| alice / USER | `readOwnerPage("alice")` | Owner param matches | Allowed |
| alice / USER | `readOwnerPage("bob")` | Owner param mismatches | `AccessDeniedException` before body |
| admin / ADMIN | `readOwnerPage("bob")` | Admin override rule | Allowed |
| anonymous | `readOwnerPage("alice")` | No valid identity | `AccessDeniedException` |
| alice / USER | `readDocument("d-alice")` | Owner from result matches | Allowed |
| bob / USER | `readDocument("d-alice")` | Owner from result differs | `AccessDeniedException` after body |
| admin / ADMIN | `readDocument("d-alice")` | Admin rule | Allowed |
| anonymous | `readDocument("d-alice")` | Unauthenticated | `AccessDeniedException` |

Similar tests apply to tenants, departments, project membership, organizations, approval state, or resource permissions, provided **expressions reflect server-verified permissions** rather than trusting client-supplied parameters.

## 6. Testing Over HTTP with MockMvc: URL Filters and Method Security Working Together

To verify HTTP responses are correct, write Servlet web-layer integration tests. Spring Boot offers `@SpringBootTest` + `@AutoConfigureMockMvc`; `spring-security-test` supports `httpBasic(...)`. Unlike `@WithMockUser` direct service tests, HTTP Basic here also exercises the path through the authentication mechanism.

### 6.1. Test Class

`src/test/java/com/example/methodsecurity/DocumentControllerSecurityTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentControllerSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("public"));
    }

    @Test
    void unauthenticatedOwnerRouteGets401() throws Exception {
        mvc.perform(get("/owners/alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanAccessOwnOwnerPage() throws Exception {
        mvc.perform(get("/owners/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result")
                        .value("profile:alice"));
    }

    @Test
    void aliceCannotAccessBobOwnerPage() throws Exception {
        mvc.perform(get("/owners/bob")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/d-alice")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAliceDocument() throws Exception {
        mvc.perform(get("/documents/d-alice")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void missingDocumentGets404() throws Exception {
        mvc.perform(get("/documents/not-found")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isNotFound());
    }
}
```

**Explaining HTTP status codes in this configuration:**

- `401 Unauthorized`: request lacked valid credentials; the `HTTP Basic` entry point demands authentication **before calling the service**.
- `403 Forbidden`: user is authenticated, yet the service method-security rule denied access.
- `404 Not Found`: controller mapped `NoSuchElementException` when the document did not exist. This is a demo policy, not a universal outcome for every service.
- `200 OK`: both HTTP authentication and method-level policy permitted the call.

In an app using `formLogin()`, unauthenticated requests may receive `302` redirecting to the login page instead of 401. Therefore **do not copy HTTP Basic status assertions verbatim** into a form-login app without adjusting for its entry point.

### 6.2. Running Tests

If the project was created with the Gradle Wrapper:

```bash
# Linux/macOS
./gradlew test

# Windows PowerShell
.\gradlew.bat test
```

When the application, JDK, dependencies, and Gradle Wrapper match the example, all 8 service tests and 7 HTTP tests should pass. This is **the example's expectation**, not a claim that the command was executed in your environment. There is no fixed Gradle JSON stdout because logs and timings vary by machine/version.

### 6.3. Why Not Just Use standaloneSetup?

A controller test built solely via:

```java
MockMvcBuilders.standaloneSetup(new DocumentController(service)).build();
```

does not automatically include the Spring Security filter chain, context, authentication manager, and method-security proxy like production. If `service` is also `new DocumentService()`, the test **bypasses the interceptor** completely. Such tests work for MVC binding or simple JSON checks, yet cannot prove `@PreAuthorize` or `@PostAuthorize` executed.

To test method security, use a Spring context with `@EnableMethodSecurity` and proxied beans; to test HTTP security, use `MockMvc` integrated with `springSecurity()`/filter chain (in the Boot example, `@AutoConfigureMockMvc` handles proper wiring).

## 7. Verifying That @PreAuthorize Blocks the Body While @PostAuthorize Runs After the Body

Tests should not ask only "was an exception thrown?" when execution order itself is a security requirement.

### 7.1. With @PreAuthorize

A service may call a repository:

```java
@PreAuthorize("hasRole('ADMIN')")
public void deleteDocument(String id) {
    documentRepository.deleteById(id);
}
```

If the user lacks the role, the body must not execute. In a Spring-integrated test, use a mock/spy repository and verify **`deleteById` was never called** when invoking the method via its proxy. This matters far more than seeing 403 at a controller: 403 could come from another filter, or the body might have executed if the annotation was bypassed.

Pseudocode assertion for a test with a managed `@MockitoBean`/Mockito repository:

```java
assertThatThrownBy(() -> service.deleteDocument("d1"))
        .isInstanceOf(AccessDeniedException.class);

verify(documentRepository, never()).deleteById(anyString());
```

This is a **conditional testing snippet**, not part of the sample project above (which has no delete repository or mock bean). When using a mock repository in Spring Boot 3.4+, inject the mock properly into the target bean instead of instantiating the service with `new` and bypassing the proxy.

### 7.2. With @PostAuthorize

A `@PostAuthorize`-annotated method is checked **after** returning its value. If the method performed external calls, metrics, queries, or side effects, blocking the final return value **does not undo those steps**.

You can use a spy/metric to test that `findById` ran even when the result was denied, yet **never treat a design with side effects as "safe" just because a test passed**. For mutations, verify permissions **before** writing or enforce business authorization in the service prior to mutation. Transaction rollback cannot undo a sent email or an external API call.

**Null/exception cases:** if a method returns `null`, `returnObject.owner()` can trigger an evaluation error; when a method throws `NoSuchElementException`, post-authorization has no result to inspect. Test those branches per your service contract, not just the happy path.

## 8. Testing Parameter-Based Authorization: Common Patterns

### 8.1. Comparing a Parameter to the Username

```java
@PreAuthorize("isAuthenticated() and #owner == authentication.name")
public ProfileView profile(@P("owner") String owner) { ... }
```

Pros: concise when the owner string matches `authentication.name` in format and trust. Cons: usernames can change; unsuitable when account ID/subject/tenant differs from username. With OIDC, use a verified, properly mapped stable subject rather than treating email as the default permission key.

Minimum tests: matching owner, different owner, anonymous, admin rule if present, null/empty input, and case differences if required by policy.

### 8.2. Resource-ID-Based Authorization

Suppose the caller passes `documentId`, while the owner resides in the DB. Access cannot be granted simply because the client passed a document ID. A policy bean can decide:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(@P("documentId") String id) {
    return repository.findRequired(id);
}
```

This is an **architectural snippet**; running it requires a bean named `documentPolicy`, a `canRead(Authentication, String)` method, and a matching repository. It checks permissions **before the method body** and avoids loading/exposing the full object before `@PostAuthorize`. However, if the policy lookup and body lookup happen at different times, evaluate **TOCTOU** (time-of-check/time-of-use) risks when owners/ACLs can change concurrently; for writes, consider transactions/locking/conditional updates.

Example policy signature:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication auth, String documentId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        // Continue checking anonymous trust, account, tenant, ACL,
        // and ownership using server-side data.
        return repository.mayRead(auth.getName(), documentId);
    }
}
```

This is a **conceptual pattern**, not a runnable file in the demo, since `DocumentRepository` is an undefined business contract here. In particular, `auth.isAuthenticated()` alone is **not enough** to exclude anonymous: production policies need `AuthenticationTrustResolver` or checks on recognized principal types. Never copy this snippet verbatim and assume it is a complete ACL.

### 8.3. Tenant-Based Authorization

```java
@PreAuthorize("""
        isAuthenticated() and
        @tenantPolicy.canAccess(authentication, #tenantId)
        """)
public InvoiceView invoice(
        @P("tenantId") String tenantId,
        @P("invoiceId") String invoiceId) { ... }
```

The rule must not only verify the user belongs to the tenant, but also ensure `invoiceId` **actually belongs to that tenant**. Otherwise a bypass occurs: a user authorized for tenant A submits an `invoiceId` belonging to tenant B. Tests must intentionally pass **a valid `tenantId` + an `invoiceId` from another tenant**.

### 8.4. Roles and Authorities

- `hasRole('ADMIN')` typically compares against `ROLE_ADMIN`.
- `hasAuthority('DOC_READ')` compares against the exact authority `DOC_READ`.
- `hasAnyAuthority('DOC_READ', 'DOC_AUDIT')` checks for one of the specified authorities.
- `hasPermission(...)` works properly only when a `PermissionEvaluator`/expression handler is configured for your application architecture; it does not magically know your DB ACL.

Using `@WithMockUser(roles = "ADMIN")` to test `hasAuthority('ADMIN')` **can fail** because the actual authority is `ROLE_ADMIN`. Use `authorities = "ADMIN"` if the policy expects exact authority `ADMIN`, or fix the policy to use role semantics. Never grant extra production permissions just to make a test pass.

### 8.5. Parameter and State Test Matrix

| Case | Condition | Expected Outcome |
| --- | --- | --- |
| Matching owner | alice calls `readOwnerPage("alice")` | Allowed |
| Wrong owner | alice calls `readOwnerPage("bob")` | Denied |
| Admin role | admin calls `readOwnerPage("bob")` | Allowed if admin policy permits |
| Anonymous | anonymous calls `readOwnerPage("alice")` | Denied |
| Null/empty owner | Invalid parameter | Validation/authorization per contract; no implicit grant |
| Case mismatch | `Alice` vs. `alice` | Accepted only if identity policy explicitly defines it |
| Matching tenant, other-tenant object | Tenant A user submits ID from B | Denied |
| Object ownership transferred | Permission changes between check and use | Concurrency/transaction protection policy |
| Principal changed after refresh | Session/token holds stale account/roles | Verify authority source and revocation policy |
| Public endpoint calling protected service | Caller unauthenticated | Method security still blocks |

## 9. Parameter-Based Authorization and IDOR/BOLA Vulnerabilities

**IDOR** (Insecure Direct Object Reference) or **BOLA** (Broken Object Level Authorization) occurs when an endpoint accepts an object ID without verifying the client is authorized for **that specific object**.

Wrong:

```java
@GetMapping("/documents/{id}")
public DocumentView get(@PathVariable String id) {
    return repository.findRequired(id);
}
```

The endpoint may require login yet still let any user read any document whose ID they know. **Being logged in does not mean owning every object.**

Safer:

- Use `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` with a proper policy/check before querying.
- Or `@PostAuthorize` checking `returnObject.owner()` on **read-only** methods, understanding the body already ran.
- For write commands, verify actor, tenant, and owner/ACL prior to mutation; consider atomic conditional updates.
- Protect against discovering non-existent object IDs with a consistent 403/404 policy per your threat model, without leaking object existence via response or timing differences.
- Test same-tenant different-owner, different-tenant same-username, guessed IDs, low roles, and locked accounts.

**Never treat hard-to-guess IDs** (random UUIDs) as authorization. An ID is only a reference; permission is a separate decision.

## 10. Mistakes That Leave Tests Green While Production Is Unprotected

### 10.1. Self-Invocation Bypasses the Proxy

A bean with a protected method:

```java
@Service
public class ReportService {
    public String publicEntry() {
        return secretReport(); // internal call via this
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String secretReport() {
        return "sensitive";
    }
}
```

Under the default proxy-based AOP model, `this.secretReport()` may **not go through the proxy**; the annotation is not enforced for that internal call. If tests only invoke `reportService.secretReport()` through the bean proxy, tests pass while `publicEntry()` can bypass protection.

The fix is designing clear protected public entry points, moving secured methods to another bean when appropriate, and testing **real call paths**. Never rely solely on an annotation existing in source.

### 10.2. Unit Tests Using new or @InjectMocks

```java
DocumentService service = new DocumentService();
service.readOwnerPage("bob");
```

This invokes a plain Java object directly, **with no method-security interceptor**. Similarly, a Mockito `@InjectMocks` service is not automatically wrapped by a Spring method-security proxy. Plain unit tests are great for business logic, yet **do not test annotation authorization**. When verifying proxy interceptors, use a Spring context with `@EnableMethodSecurity` and obtain the managed bean.

### 10.3. Test Configuration Does Not Enable Method Security

If a test slice only loads controllers/repositories without importing the config enabling method security, negative cases may fail to trigger annotations properly. `@SpringBootTest` in the demo provides the full context. With test slices like `@WebMvcTest` or minimal contexts, import the right configuration, beans, and Spring Security test integration. Never assume one test slice covers every production layer.

### 10.4. Using @WithMockUser and Assuming Passwords Were Checked

`@WithMockUser` skips the real login flow and does not verify BCrypt, HTTP Basic, session cookies, OIDC token validation, or LDAP. Method policy tests should use it for speed and clarity; authentication tests need separate integration tests. **Never equate** "mock user has `ROLE_ADMIN`" with "production provider surely maps roles properly".

### 10.5. Testing Only Success Without Testing Failure

If all tests run as admin, ownership boundaries are never tested. Use a matrix with same role but different owner, anonymous, disabled user, non-existent object, mismatched tenant, and missing authority. For parameter-based permissions, negative tests are the most critical part.

### 10.6. Using @PostAuthorize to Guard Data-Writing Methods

Dangerous example:

```java
@PostAuthorize("hasRole('ADMIN')")
public void sendTransfer() {
    transferClient.transferFunds();
}
```

The funds transfer may already have occurred before the check; a `void` method also has no useful return value. Never use this pattern. Check permissions **before** executing side effects and at the right business/transaction layer. Tests must prove no side effects happen when the user lacks permission.

## 11. Exception Handling and HTTP Status Codes

When a method is denied by the Spring Security method interceptor, `AccessDeniedException` or a compatible subtype is typically thrown. Direct service tests can assert that exact exception. Through the Servlet HTTP filter chain, `ExceptionTranslationFilter` can translate the outcome into a response depending on authentication and entry point:

| Scenario | Direct Method Invocation | HTTP via Demo's Basic Config |
| --- | --- | --- |
| Authenticated user, missing method permission | `AccessDeniedException` | Usually 403 |
| Anonymous user, HTTP route requires auth | Service may not be reached | Usually 401 from Basic authentication entry point |
| Authorized user, method executes normally | Returns result | 200 if controller succeeds |
| Document does not exist | Demo's `NoSuchElementException` | 404 via controller handler |
| Business method throws another exception | Method-specific exception | Status depends on controller/error mapping |

**A 403 status from `MockMvc` does not by itself prove `@PreAuthorize` ran**: the request might have been blocked by a URL rule, CSRF, or another filter. Therefore add **direct service tests** to prove the method interceptor is working.

403/401 exceptions also do not guarantee a properly formatted API JSON response; if a uniform error body is required, configure `AccessDeniedHandler`, `AuthenticationEntryPoint`, and consistent business error handling without leaking sensitive information.

## 12. Mock Users, UserDetails, and Custom Test Principals

In real systems, the principal may be a custom `UserDetails`, `JwtAuthenticationToken`, `OidcUser`, or carry tenant IDs/permissions beyond username. An expression `principal.tenantId == #tenantId` requires a matching principal in tests.

Main approaches:

1. **`@WithMockUser`:** enough for simple username, role, and authority rules.
2. **`@WithUserDetails`:** fetches principal via `UserDetailsService` in the test context; useful when rules read `UserDetails` fields and need the matching principal type.
3. **Custom `@WithSecurityContext` annotation:** builds a typed `Authentication`/principal for testing expressions using domain claims; avoid spoofing unverified data on requests.
4. **HTTP `MockMvc` with `httpBasic(...)` or suitable security test request post-processors:** tests the integration layer.
5. **Tests with real tokens against a trusted mock provider/decoder or test IdP:** when verifying issuer, subject, scope mapping, and method security together rather than just mocking a user.

Never commit secrets, raw JWTs, refresh tokens, or real user data into public test fixtures. Use fake data and test empty/different-role permissions explicitly.

## 13. Complete Checklist for Method Security Testing

- [ ] Application enables `@EnableMethodSecurity` in the Spring context used by tests.
- [ ] Service is a Spring-managed bean; methods are called **through the proxy**, not via `new`/self-invocation.
- [ ] At least one positive and one negative test exist for every `@PreAuthorize`/`@PostAuthorize` expression.
- [ ] `@PreAuthorize` tests verify the method body or side effects **do not execute** when denied.
- [ ] `@PostAuthorize` tests recognize the method already ran; use it for read-only results, never as the sole guard for mutations.
- [ ] Test users with the same role but **a different owner**, not just admin vs. anonymous.
- [ ] Test `@P`/parameter name discovery and compiler `-parameters` if relying on reflection.
- [ ] Test with/without `ROLE_` prefix and `hasAuthority` according to policy.
- [ ] Do not allow anonymous bypass simply because `authentication.name` matches a parameter string.
- [ ] Test tenant/object relationships to prevent BOLA when clients pass IDs.
- [ ] Test missing/null resources and error mapping without exposing sensitive object info.
- [ ] Test roles/authorities on custom principals or OIDC/JWT per trust boundaries.
- [ ] Test direct service calls and the HTTP layer separately to distinguish interceptors from URL filters.
- [ ] Test internal call paths/self-invocation and entry points that could bypass proxies.
- [ ] Keep mock data stable, without real users/secrets in test sources.
- [ ] For DB writes, use transactions and verify zero side effects when denied.

## 14. Self-Check

**1.** How do `@PreAuthorize` and `@PostAuthorize` differ?  
**Answer:** pre checks before the body; post checks after the body returns a result and can inspect `returnObject`. Post cannot prevent side effects from already occurring.

**2.** Why must `@WithMockUser(username="alice")` reading `/owners/bob` fail?  
**Answer:** the method rule compares the request's owner argument with `authentication.name`; `alice` and `bob` differ, and the user is not an admin.

**3.** If a user has `ROLE_ADMIN`, is `hasAuthority('ADMIN')` guaranteed to pass?  
**No.** `hasAuthority` matches exact strings; `hasRole('ADMIN')` normally adds the `ROLE_` prefix.

**4.** Can `new DocumentService()` be used to test `@PreAuthorize`?  
**Not sufficient.** Direct calls lack the Spring interceptor; tests must go through the Spring-managed proxy.

**5.** Why should a `DELETE` operation not rely solely on `@PostAuthorize`?  
**Answer:** the `DELETE` may already have executed before the post-check. Verify permissions prior to mutation and assert no side effects occurred.

**6.** Does `@WithMockUser` prove a user can log in via real HTTP Basic?  
**No.** It is a mocked security context and does not verify passwords. A separate HTTP authentication integration test is needed.

**7.** If a service is only called via `this.securedMethod()`, what can happen?  
**Answer:** self-invocation normally skips the Spring proxy and can bypass the method-security interceptor. Test the real call path.

**8.** Beyond username, what must ownership method testing account for?  
**Answer:** real object owner and tenant, account state, null/missing objects, changing policies, check timing, and IDOR/BOLA.

## Conclusion

`@PreAuthorize` protects **before** a method runs and fits role, authority, parameter, or policy-bean checks. `@PostAuthorize` inspects **the result after** the method runs, suited for certain read operations whose permissions depend on `returnObject`, yet it does not stop side effects that already happened.

A trustworthy test suite calls **Spring-managed proxies** with `@EnableMethodSecurity`, includes positive/negative tests for owners, admins, anonymous users, and parameters, uses `@WithMockUser` for method expressions, adds `MockMvc` for HTTP behavior, and verifies self-invocation, parameter discovery, role prefixes, and object-level authorization. Above all: **HTTP 403 is an observable outcome, while proving method security requires testing the interceptor itself and pre-/post-call effects.**
