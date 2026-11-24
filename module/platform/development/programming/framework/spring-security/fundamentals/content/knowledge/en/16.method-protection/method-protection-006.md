# SpEL with Authentication, Principal, Parameters, and Policy Beans

## 1. Learning Objectives and Scope

Spring Security does more than check whether a user holds a fixed role. In real business logic, access often depends simultaneously on the **authenticated identity**, **arguments passed to the invoked method**, and **data trusted by the system**. Spring Expression Language (SpEL) lets you express these conditions inside annotations like `@PreAuthorize`.

After this lesson, you can:

1. Understand SpEL in method security and how Spring Security evaluates expressions prior to method execution.
2. Properly use `authentication`, `principal`, `authentication.name`, `hasRole`, `hasAuthority`, and logical operators.
3. Reference method arguments via `#documentId`, `@P`, parameter names compiled with `-parameters`, or positional aliases `#p0`/`#a0`.
4. Invoke Spring policy beans with syntax like `@documentPolicy.canRead(authentication, #documentId)` to keep business logic testable.
5. Handle allowed and denied requests, distinguish 401 from 403, and recognize the limits of `@PreAuthorize`, `@PostAuthorize`, and proxy-based interception.
6. Run a complete example with **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**, then verify with `curl` and `MockMvc` tests.

**Context:** this lesson belongs to *Method protection* in *Spring Security - fundamentals*. The main example uses Spring MVC/Servlet; Spring WebFlux uses reactive method security and a different security context storage model. Many SpEL expressions share the same concepts, but thread/security context handling must not be copied verbatim from Servlet to reactive stacks.

## 2. Why Do We Need SpEL When hasRole Already Exists?

Suppose an API manages two documents:

| Document ID | Owner |
| --- | --- |
| `101` | `alice` |
| `202` | `bob` |

Both users Alice and Bob have the `USER` role. A rule based purely on role:

```java
@PreAuthorize("hasRole('USER')")
public Document readDocument(long documentId) {
    // ...
}
```

does not distinguish document 101 owned by Alice from document 202 owned by Bob. Without further checks in the service, anyone with role USER could read someone else's data — an **IDOR / broken object-level authorization** risk.

A better condition:

```java
@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    // ...
}
```

**This is an illustrative fragment** requiring `Document`, a `documentPolicy` bean, the `@P` import, and a real Spring-managed service. It states: *admins with administrative privileges may read; ordinary users may read only when the policy bean confirms the caller has rights on this document ID*.

Key components:

- `hasRole('ADMIN')`: function supplied by Spring Security, checking for `ROLE_ADMIN` under the default prefix.
- `or`: SpEL logical OR; under normal evaluation, the second operand is skipped if the first already evaluates to true.
- `@documentPolicy`: references a bean named `documentPolicy` managed by the Spring ApplicationContext.
- `authentication`: the active authentication object in the invocation's context.
- `#documentId`: the method parameter named `documentId`, not a global variable or a value read automatically from the URL.

**Never trust client-supplied claims:** sending `owner=alice` in an HTTP request does not prove the client is Alice or owns the document. The policy bean must retrieve ownership from server-side data or an equivalently trusted source.

## 3. Where Is SpEL Evaluated?

In a Servlet application with `@EnableMethodSecurity`, Spring Security sets up interceptors via Spring AOP for method authorization. With `@PreAuthorize`, the condition is evaluated **before** the business method runs.

```text
HTTP request / other caller
          │
          ▼
Spring Security authenticates request / builds Authentication
          │
          ▼
Spring bean proxy (method security)
          │
          ├─ finds @PreAuthorize annotation
          │
          ├─ creates SpEL evaluation context
          │     ├─ authentication / principal / authorities
          │     ├─ method arguments (#documentId, #username...)
          │     └─ beans in ApplicationContext (@documentPolicy)
          │
          └─ evaluates expression
                 ├─ true  → invokes business method
                 └─ false → denies (does not run method)
          │
          ▼
Result or error propagates through HTTP / active caller
```

Points to distinguish:

- **HTTP security:** `SecurityFilterChain` applies request rules such as `anyRequest().authenticated()`.
- **Method security:** `@PreAuthorize` applies to method calls on a Spring-managed bean wrapped by the corresponding interceptor.
- **Resource authorization:** logic checking permissions on document ID 101/202 usually lives in a policy bean or data-access service, evaluating ownership, tenant, state, and other constraints.

An endpoint can pass the HTTP `authenticated()` rule and still be denied by `@PreAuthorize`. These are two decisions at two distinct layers.

**Activation:** adding the Spring Security dependency **does not automatically enable** `@PreAuthorize`. You need `@EnableMethodSecurity` on a Spring configuration (or equivalent method-security setup). In modern Spring Security, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are supported by default once method security is enabled, while `@Secured` or JSR-250 need extra flags if used.

### Authentication State in HTTP Calls

If a user is **not logged in** and an HTTP rule requires authentication, HTTP Basic typically returns **401 Unauthorized**. If the user **is logged in** but SpEL returns false, the typical response is **403 Forbidden**. Actual status codes also depend on the authentication mechanism, exception handling, CSRF, and other filters. Never attribute every 403 to SpEL without identifying which layer denied it.

For calls from schedulers, message listeners, or direct tests where **there is no HTTP request**, the caller must handle the method-security exception; do not assume an HTTP status or security context exists automatically as in a web request.

## 4. Built-in Variables: authentication and principal

Method security exposes a set of properties and methods on the **expression root**. Two commonly confused items:

| In SpEL | Nature | Useful examples | Notes |
| --- | --- | --- | --- |
| `authentication` | Current `Authentication` | `authentication.name`, `authentication.authorities` | May represent anonymous or another auth type; never treat as client-supplied data |
| `principal` | `authentication.principal` | `principal.username` when principal is `UserDetails` | Concrete type depends on auth mechanism; not every principal has `username` |
| `hasRole('ADMIN')` | Security expression function | Checks authority `ROLE_ADMIN` | Role prefix is configurable; defaults to `ROLE_` |
| `hasAuthority('document:read')` | Security expression function | Matches exact authority | Does not infer authority from role names |
| `isAuthenticated()` | Checks recognized security state | Disallows anonymous | Differs from reading `authentication.authenticated` directly |

### authentication.name

`authentication.name` is SpEL syntax calling `Authentication#getName()`, making it convenient for matching **identity names**:

```java
@PreAuthorize("authentication.name == #username")
public String getMyProfile(@P("username") String username) {
    return "profile " + username;
}
```

If `alice` calls `getMyProfile("alice")`, the condition holds; if Alice passes `"bob"`, it fails. However, **comparing names** makes sense only when the data truly uses that name as a trusted identifier. If the system has mutable display names, tenants, subject IDs, or overlapping usernames across organizations, compare stable IDs inside a policy bean.

### principal.username

With standard `UserDetailsService` + HTTP Basic, the authenticated principal may be `org.springframework.security.core.userdetails.User` — a `UserDetails` with `getUsername()`. Thus:

```java
@PreAuthorize("hasRole('USER') and principal.username == #username")
public String getUserView(@P("username") String username) {
    return "user-view " + username;
}
```

can work in that setup. With JWT/OAuth2/OIDC or custom principals, however, `principal` may be a `Jwt`, `OAuth2User`, `UserDetails`, or another type depending on the implementation. **Do not copy `principal.username` blindly across every system**: evaluation can fail if that property does not exist. Prefer `authentication.name` or a policy bean that knows how to interpret identities in your specific system.

In particular, SpEL method security's `principal` **is not the same thing as the `@AuthenticationPrincipal` annotation** on controller parameters; the controller annotation injects the principal into a handler method, whereas the SpEL root is the context for evaluating authorization expressions.

### Authorities Are Permission Names, Not Client Claims

Spring Security uses `GrantedAuthority` values like `ROLE_USER`, `ROLE_ADMIN`, or `document:read`. `hasRole('ADMIN')` normally checks for `ROLE_ADMIN`, while `hasAuthority('document:read')` requires that exact string. Holding `ROLE_ADMIN` does not automatically imply holding `document:read` unless the system grants/maps that permission or configures a role hierarchy.

## 5. Referencing Method Parameters: #name, @P, -parameters, and #p0

The syntax `#documentId` references a **method parameter whose name Spring Security has discovered**. The `#` symbol denotes a variable reference in SpEL:

```java
@PreAuthorize("#owner == authentication.name")
public void read(@P("owner") String owner) {
    // ...
}
```

Distinguish three elements: the Java parameter name `owner`, the name `"owner"` supplied by the method-security discoverer, and the SpEL variable `#owner`. In the snippet above, `@P` fixes the name for the expression, avoiding dependence on bytecode retaining parameter names.

### Three Common Approaches

**Approach 1 — `@P("documentId")` (explicit):**

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public String read(@P("documentId") long id) {
    return "reading " + id;
}
```

This is a **fragment** needing a `documentPolicy` bean and a Spring-managed service; the Java name is `id`, yet SpEL uses `#documentId` thanks to `@P`.

**Approach 2 — compiling with `-parameters` and using the Java name:**

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

With Java source:

```java
@PreAuthorize("authentication.name == #username")
public String self(String username) {
    return username;
}
```

`-parameters` lets Java reflection retain parameter names in bytecode. Some build plugins enable this automatically depending on the environment; projects should verify their real build setup, especially when expressions sit on interfaces or precompiled code.

**Approach 3 — positional aliases `#p0` or `#a0`:**

```java
@PreAuthorize("authentication.name == #p0")
public String self(String username) {
    return username;
}
```

`#p0`/`#a0` corresponds to the first parameter; `#p1`/`#a1` to the second. This avoids name discovery, but is less self-documenting and fragile if parameter order changes.

Spring Security can also discover names from annotations like Spring Data's `@Param` or other metadata. This lesson uses `@P` so examples remain accurate and independent of compiler flags.

**Common mistake:** writing `#documentId` in the expression when the method only declares `long id` with no `@P("documentId")` and no parameter name metadata. SpEL may see null/undefined values, causing denials or bean-invocation errors; never "fix" this by removing the resource check.

## 6. Why Use a Policy Bean?

Simple conditions like `hasRole('ADMIN')` fit neatly inline inside the annotation. Real checks, however, often need database reads, tenant matching, status checks, sharing grants, and active policies. Cramming everything into long SpEL strings makes logic hard to review and unit test.

A policy bean keeps the expression's intent crystal clear:

```java
@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    // ...
}
```

Bean with the exact name `documentPolicy`:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(Authentication authentication, long documentId) {
        // Look up document and ownership from a trusted server source
        return false;
    }
}
```

The two snippets above are **fragments**, not a complete program; returning false merely illustrates the policy signature. Section `7` provides a full implementation with sample data and tests.

### Data Flow and Trust Boundaries

```text
HTTP GET /api/documents/202
   ├─ Document ID from path: 202  ────> method parameter #documentId
   └─ Valid credentials ──────────────> Authentication (name=alice, ROLE_USER)
                                               │
                                               ▼
@documentPolicy.canRead(authentication, 202)
                                               │
                                       owners[202] = "bob"
                                               │
                                  alice != bob → false → 403
```

Admin accounts pass through the `hasRole('ADMIN')` branch per application policy; ordinary users rely on `canRead`. This is a **role + resource ownership** model, not pure RBAC.

**Policy beans must fail closed:** missing documents, missing identity, invalid tenant data, or permission-lookup errors must deny access. Never write `return true` on a database timeout or null `owner`. If a policy relies on data changing concurrently during a transaction, handle race conditions and ensure the authorization check stays consistent with the final operation.

### Writing Readable Expressions

- `and`/`&&`: all conditions must hold.
- `or`/`||`: at least one condition holds.
- `!`: negation.
- `==`/`!=`: equality/inequality.
- Parentheses `(...)`: group conditions to avoid operator-precedence mistakes.
- `@beanName.method(...)`: invoke a Spring bean by name.
- `#paramName`: parameter variable.
- `authentication` or `principal`: properties on the security expression root, **without** a `#` prefix in standard usage.

A review-friendly expression:

```java
@PreAuthorize(
    "hasRole('ADMIN') or " +
    "(hasRole('USER') and @documentPolicy.canRead(authentication, #documentId))"
)
```

This is an **annotation fragment**: in a real app it must sit above a method with a matching bean. If `hasRole('USER')` is not an actual business requirement, omit it; do not add roles merely to make an expression look "safer."

## 7. Runnable Example: Java 17 and Spring Boot Application

The example lets two users read **only the documents they own**, while admins can read any existing document. It also includes two extra routes comparing `authentication.name` and `principal.username`.

- `alice`: role `USER`, owns document `101`.
- `bob`: role `USER`, owns document `202`.
- `admin`: role `ADMIN`, allowed to read both documents.
- `GET /public`: public.
- `GET /api/documents/{documentId}`: owned by caller or role ADMIN.
- `GET /api/users/{username}/self`: matches `authentication.name`.
- `GET /api/users/{username}/profile`: requires role USER and `principal.username` equal to the parameter.

### 7.1. Project Structure and Gradle

```text
spel-method-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/spelmethod/
    │   ├── SpelMethodApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/spelmethod/
        └── SpelMethodSecurityTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spel-method-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
```

In this example, service method parameters are named via `@P`, avoiding dependence on `-parameters`. Controller `@PathVariable` annotations specify explicit names to avoid metadata reliance during Spring MVC binding. Gradle resolves Spring dependencies; do not compile/run with bare `javac`/`java` missing libraries on the classpath.

### 7.2. Main Application

**`src/main/java/com/example/spelmethod/SpelMethodApplication.java`**

```java
package com.example.spelmethod;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpelMethodApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpelMethodApplication.class, args);
    }
}
```

### 7.3. Enabling HTTP Security and Method Security

**`src/main/java/com/example/spelmethod/SecurityConfiguration.java`**

```java
package com.example.spelmethod;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob123")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
```

Explanation:

1. `@EnableMethodSecurity` is required for `@PreAuthorize` to take effect on service beans.
2. `/api/**` at the HTTP layer requires only **authentication**; fine-grained checks on user, document ID, and role happen in the service layer.
3. `anyRequest().denyAll()` blocks routes not explicitly listed in the HTTP policy.
4. `httpBasic(withDefaults())` lets us observe 401 responses when credentials are missing; `formLogin` is disabled to avoid login-form redirects. CSRF stays at default, needing no change because the demo endpoints are GET-only.
5. `{noop}` and demo passwords are **for learning only**; never store plaintext passwords or use these accounts in production. Real apps must use proper password encoders, identity stores, and HTTPS.

### 7.4. Ownership Policy Bean

**`src/main/java/com/example/spelmethod/DocumentPolicy.java`**

```java
package com.example.spelmethod;

import java.util.Map;
import java.util.Objects;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final Map<Long, String> owners = Map.of(
        101L, "alice",
        202L, "bob"
    );

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null ||
            authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String owner = owners.get(documentId);
        return owner != null && Objects.equals(owner, authentication.getName());
    }

    public String ownerOf(long documentId) {
        return owners.get(documentId);
    }
}
```

`@Component("documentPolicy")` registers the bean with the exact name referenced in SpEL `@documentPolicy`. When `DocumentService.readDocument(101)` is invoked, the expression passes `authentication` and `#documentId` into `canRead`.

In this example, `owners` is an immutable `Map` for predictable output, not a real document storage system. With a database, the policy must load resource/owner from the server and check tenant/visibility per business rules; never trust IDs, owners, or roles supplied by the client. If the identity does not match or the document does not exist, `canRead` returns false.

The `authentication instanceof AnonymousAuthenticationToken` check is an extra safeguard in the example; the HTTP layer already blocks anonymous access on `/api/**`. Checking `Authentication.isAuthenticated()` alone **is not enough to distinguish** anonymous users in all cases, because anonymous authentication can also be marked authenticated. When writing general policies, use `AuthenticationTrustResolver` or official mechanisms to classify trust levels.

### 7.5. Service Containing Three Expression Styles

**`src/main/java/com/example/spelmethod/DocumentService.java`**

```java
package com.example.spelmethod;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentPolicy documentPolicy;

    public DocumentService(DocumentPolicy documentPolicy) {
        this.documentPolicy = documentPolicy;
    }

    @PreAuthorize(
        "hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)"
    )
    public String readDocument(@P("documentId") long documentId) {
        String owner = documentPolicy.ownerOf(documentId);
        if (owner == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"
            );
        }
        return "document " + documentId + " owner=" + owner;
    }

    @PreAuthorize("authentication.name == #username")
    public String self(@P("username") String username) {
        return "self " + username;
    }

    @PreAuthorize("hasRole('USER') and principal.username == #username")
    public String profile(@P("username") String username) {
        return "profile " + username;
    }
}
```

Three mechanisms illustrated:

- `readDocument`: combines role, policy bean, and the request's actual ID. `ADMIN` passes the expression, whereas regular users must hold ownership; an unknown document ID still returns **404** once admin is authorized because the business method checks existence.
- `self`: compares only the authenticated name `authentication.name` against parameter `#username`.
- `profile`: checks both role USER and `principal.username`. This works in the demo because the principal is a `UserDetails` returned by `InMemoryUserDetailsManager`. If an app uses JWT/OIDC, adjust the condition for the actual principal type.

These methods are **public methods of a Spring-managed service**. Calls from the controller go through the Spring proxy, so `@PreAuthorize` is evaluated. For a call like `this.readDocument(id)` from another method inside `DocumentService` itself, the proxy interceptor may not run; section `10` analyzes the self-invocation bug.

### 7.6. Controller Calling the Protected Bean

**`src/main/java/com/example/spelmethod/DocumentController.java`**

```java
package com.example.spelmethod;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/documents/{documentId}")
    public String document(@PathVariable("documentId") long documentId) {
        return service.readDocument(documentId);
    }

    @GetMapping("/api/users/{username}/self")
    public String self(@PathVariable("username") String username) {
        return service.self(username);
    }

    @GetMapping("/api/users/{username}/profile")
    public String profile(@PathVariable("username") String username) {
        return service.profile(username);
    }
}
```

The controller only accepts inputs and binds paths; the service is responsible for protecting methods. Never trust `username` in the URL for authorization: `username` is merely the comparison target, whereas **identity** comes from the system-verified `Authentication`.

### 7.7. Running and Observing HTTP Behavior

Requires JDK 17+ and Gradle 8.x compatible with Spring Boot 3.3. Inside the `spel-method-demo` directory:

```bash
gradle test
gradle bootRun
```

If you have a compatible Gradle Wrapper, you can use `./gradlew test` and `./gradlew bootRun` (Linux/macOS) or `gradlew.bat test` and `gradlew.bat bootRun` (Windows). `gradle bootRun` starts the app on default port 8080 if free and unconfigured otherwise.

In a second terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/documents/101
curl -i -u alice:alice123 http://localhost:8080/api/documents/101
curl -i -u alice:alice123 http://localhost:8080/api/documents/202
curl -i -u bob:bob123 http://localhost:8080/api/documents/202
curl -i -u admin:admin123 http://localhost:8080/api/documents/202
curl -i -u alice:alice123 http://localhost:8080/api/users/alice/self
curl -i -u alice:alice123 http://localhost:8080/api/users/bob/self
curl -i -u alice:alice123 http://localhost:8080/api/users/alice/profile
curl -i -u admin:admin123 http://localhost:8080/api/users/admin/profile
```

**Expected results table (demo config, GET):**

| Request | Identity | Outcome | Checkpoint |
| --- | --- | --- | --- |
| `/public` | Anonymous | 200 | `permitAll` |
| `/api/documents/101` | Anonymous | 401 | HTTP `authenticated()` |
| `/api/documents/101` | Alice | 200 | `canRead(alice, 101) == true` |
| `/api/documents/202` | Alice | 403 | `canRead(alice, 202) == false` |
| `/api/documents/202` | Bob | 200 | `canRead(bob, 202) == true` |
| `/api/documents/202` | Admin | 200 | `hasRole('ADMIN')` |
| `/api/users/alice/self` | Alice | 200 | `authentication.name == #username` |
| `/api/users/bob/self` | Alice | 403 | Names differ |
| `/api/users/alice/profile` | Alice | 200 | `hasRole('USER')` and `principal.username` match |
| `/api/users/admin/profile` | Admin | 403 | Has `ROLE_ADMIN` only, not `ROLE_USER` |

Expected success response bodies derived from source code:

```text
GET /public (anonymous)                 -> public
GET /api/documents/101 (alice)          -> document 101 owner=alice
GET /api/documents/202 (bob)            -> document 202 owner=bob
GET /api/documents/202 (admin)          -> document 202 owner=bob
GET /api/users/alice/self (alice)       -> self alice
GET /api/users/alice/profile (alice)    -> profile alice
```

These are **body text** only, not full status lines or headers. Do not assume 401/403 JSON error structures are fixed; they vary by response config and entry point. For `admin`, `principal.username` may equal `"admin"`, yet the `profile` expression still fails because `hasRole('USER')` is false; role ADMIN **does not implicitly** inherit USER.

### 7.8. Automated Testing with MockMvc

**`src/test/java/com/example/spelmethod/SpelMethodSecurityTest.java`**

```java
package com.example.spelmethod;

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
class SpelMethodSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestCannotReadDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk())
            .andExpect(content().string("document 101 owner=alice"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isOk())
            .andExpect(content().string("document 202 owner=bob"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadDocumentOwnedByAnotherUser() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void authenticationNameMatchesOnlyCurrentUser() throws Exception {
        mvc.perform(get("/api/users/alice/self"))
            .andExpect(status().isOk())
            .andExpect(content().string("self alice"));

        mvc.perform(get("/api/users/bob/self"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void principalUsernameMustAlsoMatch() throws Exception {
        mvc.perform(get("/api/users/alice/profile"))
            .andExpect(status().isOk())
            .andExpect(content().string("profile alice"));

        mvc.perform(get("/api/users/bob/profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminDoesNotAutomaticallyHaveUserRole() throws Exception {
        mvc.perform(get("/api/users/admin/profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void missingDocumentIsNotFoundForAdmin() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isNotFound());
    }
}
```

The test suite covers two layers of protection:

- **Anonymous → 401**: HTTP rule `authenticated()` blocks before the service.
- **Authenticated but unauthorized → 403**: method-security SpEL blocks before the method runs.
- **Authorized → 200**: policy bean or identity expression matches.
- **Admin reads non-existent ID → 404**: admin passes authorization, yet business logic checks resource existence.

`@WithMockUser` creates a mock security context for tests, defaulting to a Spring Security `User` principal and authorities like `ROLE_USER`. It does not exercise `InMemoryUserDetailsManager` login/password checking. `curl -u` above tests requests using HTTP Basic with demo credentials.

## 8. Common SpEL Expressions in Method Protection

| Condition | Example | Meaning |
| --- | --- | --- |
| User must be logged in | `@PreAuthorize("isAuthenticated()")` | Requires a recognized authenticated identity |
| Specific role required | `@PreAuthorize("hasRole('ADMIN')")` | Requires `ROLE_ADMIN` under default prefix |
| Fine-grained authority required | `@PreAuthorize("hasAuthority('document:read')")` | Matches granted authority |
| One of several permissions required | `@PreAuthorize("hasAnyAuthority('document:read','document:audit')")` | Logical OR across authorities |
| Identity match | `@PreAuthorize("authentication.name == #username")` | Compares authenticated name against parameter |
| Principal has matching property | `@PreAuthorize("principal.username == #username")` | Only when principal exposes `username` |
| Combining role and business logic | `@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication,#id)")` | Calls policy bean with resource ID |
| Combining conditions | `@PreAuthorize("hasRole('EDITOR') and #documentId > 0")` | Both conditions hold; does not replace object check |

**Note:** for `hasPermission(...)`, Spring Security needs an appropriate permission evaluation mechanism (such as `PermissionEvaluator`). Without configuring object-permission evaluation, do not assume `hasPermission(#id, 'read')` automatically knows who owns a document. In many applications, an explicit policy bean is clearer.

### When Is @PostAuthorize Needed?

`@PostAuthorize` evaluates **after the method runs**, with access to `returnObject`:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document loadDocument(long id) {
    // only return Document to caller when owner matches
}
```

This is an **illustrative fragment**, requiring a `Document` class with an `owner` property and a method inside a Spring-managed bean. It is useful when the condition depends on the returned object. However, the data has already been loaded and the method has executed **before** the policy decides. Never use `@PostAuthorize` alone to guard operations with **side effects** such as transferring funds, deleting records, or sending emails — once the method triggers side effects, denying afterward may be too late. For read-only queries, consider avoiding unnecessary loads of sensitive data upfront by placing policies at the service/data-access layer.

`@PreFilter`/`@PostFilter` support filtering collections via expressions in suitable scenarios; they do not replace owner/tenant checks in DB queries for large datasets.

## 9. Common Expression and Parameter Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `principal.username` with all JWT/OIDC setups | Principal lacks a `username` field | Check actual principal type; use `authentication.name` or policy bean |
| Writing `#documentId` when Java method has `id` without `@P` | Parameter discovery cannot find the referenced name | Add `@P("documentId")` or compile with `-parameters` |
| Writing `@documentPolicy` when bean has another name | Bean cannot be resolved | Name the bean explicitly via `@Component("documentPolicy")` or `@Bean("documentPolicy")` |
| Using `hasRole('ROLE_ADMIN')` with default prefix | Wrong syntax/role prefix | Use `hasRole('ADMIN')` or `hasAuthority('ROLE_ADMIN')` |
| Using only `hasRole('USER')` for owner-scoped documents | Another user with role USER reads the object | Policy must check owner/tenant/state by resource ID |
| Using only `authentication.authenticated` | Can misinterpret anonymous authentication | Use `isAuthenticated()` or an appropriate trust resolver |
| Reading owner/role from client query/header/body | Client input can be forged | Decide using Authentication and trusted server data |
| Not enabling `@EnableMethodSecurity` | `@PreAuthorize` annotation is inactive | Enable method security and test denied cases |
| Calling `this.securedMethod(...)` inside the same bean | Bypasses AOP proxy under default proxy mode | Call through another Spring-managed bean or redesign service boundaries |
| Annotating objects created with `new` | Not Spring-managed or proxied | Use dependency injection and managed beans |
| Writing huge expressions with multiple DB queries | Hard to review, hard to test, adds latency | Move rules into a small policy bean separating authz and queries |
| Using `@PostAuthorize` on data-writing methods | Decision happens after side effects | Use `@PreAuthorize` / appropriate transactional authorization |
| Ignoring tenant or resource state | Permissions leak beyond intended scope | Check object-level/tenant/state in policy |
| Testing only 200 cases | Fails to catch disabled method security | Test 401, 403, 404, and users with wrong roles |

### Notes on Self-Invocation and Proxies

Spring Method Security typically executes via Spring AOP proxies. A snippet like:

```java
@Service
class ExampleService {
    public String outer(long id) {
        return inner(id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String inner(long id) {
        return "restricted";
    }
}
```

is an **error-explaining fragment**, not a safe example. The call `outer() -> inner()` via `this` usually bypasses `inner`'s proxy, so the annotation can be skipped. Enforce controls at **entry points** intercepted by Spring, split beans when needed, and verify with tests along real call paths. Never assume that merely putting an annotation on any Java method protects it in every scenario.

### Notes on Multithreading and Reactive

In Servlet apps, the security context is typically managed per execution via `SecurityContextHolder`. Switching threads with `@Async` or manually spawned threads without proper context propagation can prevent expressions from seeing `Authentication` as expected. With WebFlux/Reactor, Spring Security uses reactive context (Reactor `Context`/`ReactiveSecurityContextHolder`) and requires reactive method security configuration. Never copy `ThreadLocal` blindly into reactive pipelines.

### Never Build Dynamic SpEL from User Input

The `@PreAuthorize("...")` annotation is an **expression written and reviewed in code**. Never concatenate raw HTTP input into SpEL source for the parser to execute; doing so turns untrusted input into expressions accessing unintended objects/beans. Pass user data as **bound parameters** (`#documentId`, `#username`) and let policy beans decide access.

## 10. When Designing Real Policies, What Must Be Checked?

A method like `readDocument(long id)` may require more conditions than username matching:

1. **Identity**: user/subject ID from a verified `Authentication`.
2. **Role/permission**: whether the user holds the right authority for the `read` action.
3. **Ownership/share**: does the user own the document or hold a valid sharing grant?
4. **Tenant boundary**: do the document and user belong to the same organization or allowed tenant?
5. **Resource state**: is the document deleted, locked, still draft, or expired?
6. **Session/token validity**: can an old token/session still be used if permissions were revoked?
7. **Consistency**: does the policy evaluate against the same data version/state as the protected operation?
8. **Audit**: log sensitive accesses and denials (never log tokens, passwords, cookies, or sensitive content).

Policy beans should return clear results and fail closed. With a DB, prefer embedding authorization checks in queries or inside appropriate transactions when data can change concurrently. When a resource is not found, choose 404/403 per your anti-enumeration policy; avoid letting clients infer that someone else's document exists.

**Do not treat annotations as the entire security design.** Method-level authorization protects business logic across multiple call paths, but must be paired with the HTTP layer, trusted identity sources, and controlled data access.

## 11. Knowledge Self-Check

**Question 1.** How are `authentication` and `principal` similar and different?

**Answer:** `authentication` is the authentication object containing name, authorities, status, and principal. `principal` is typically `authentication.getPrincipal()`; its concrete type depends on the login mechanism. With the demo user store it has a `username` property; with JWT/OIDC do not assume that.

**Question 2.** Why does `#documentId` have `#` while `authentication` does not?

**Answer:** `#documentId` is a parameter variable in the SpEL evaluation context, whereas `authentication` is a property on the security expression root. `@documentPolicy` starts with `@` because it references a Spring bean.

**Question 3.** If Alice has role USER and calls `readDocument(202)`, what happens in the demo?

**Answer:** `hasRole('ADMIN')` is false; the policy reads owner for ID 202 as Bob, compares against authenticated name Alice, and returns false. The method does not run and the HTTP request typically returns 403.

**Question 4.** Why can admin read ID 202 yet cannot call `/api/users/admin/profile` in the demo?

**Answer:** The document-reading method includes `hasRole('ADMIN')`. The profile method requires `hasRole('USER') and principal.username == #username`. Admin does not implicitly possess `ROLE_USER`, so profile is denied.

**Question 5.** When should you use `@P` instead of `-parameters`?

**Answer:** When you want explicit SpEL names independent of compiler metadata, especially on API/interface methods or projects with varied build setups. Both can work; `@P` makes expression parameter names explicit.

**Question 6.** Does writing `@PreAuthorize("hasRole('USER')")` protect each user's private documents?

**Answer:** No. Every user with role USER passes that rule. You must check resource ID/owner/tenant/state in a policy or authorization service.

**Question 7.** Why is `@PostAuthorize` unsuitable as the sole protection for data deletion?

**Answer:** Because the method executes before `@PostAuthorize` inspects the return value; side effects may already have occurred. Check permissions before the action and ensure transaction/consistency controls.

**Question 8.** Why can adding `@PreAuthorize` to a method and calling it via `this.method()` fail to protect it?

**Answer:** Internal calls can bypass the AOP proxy so the interceptor never runs. Design call paths through a Spring bean proxy and test real behavior.

**Question 9.** In a `@WithMockUser` test, does Alice being allowed prove Alice's password was verified?

**Answer:** No. `@WithMockUser` constructs a mock Authentication for testing authorization and does not perform HTTP Basic login. Test HTTP Basic separately with `curl -u` or integration tests using real credentials.

**Question 10.** Why shouldn't a policy trust an `owner` claim sent in a JSON body?

**Answer:** Clients can tamper with the body. Ownership must be based on documents looked up on the server and the verified identity, never on the caller's self-declared claims.

## 12. Conclusion

- **SpEL in method security** lets you check identity, authorities, method arguments, and business beans.
- **`authentication` is the active Authentication; `principal` is the inner principal**, whose type varies by authentication mechanism.
- Method parameters use **`#name`**; ensure names are discoverable via `@P`, `-parameters`, or matching aliases.
- **`@documentPolicy.canRead(authentication, #documentId)`** moves resource/ownership checks out of long expressions and keeps logic testable.
- **`@EnableMethodSecurity`** and invocation through a **Spring-managed proxy** are essential for `@PreAuthorize` to work in the demo setup.
- **403** from method security differs from **401** from HTTP authentication; test both allowed and denied cases.
- Real object-level permissions must consider **owner, tenant, state, token lifecycle, and consistency**, not just roles.
- The demo uses plaintext accounts/passwords for learning only; production apps need trusted identities, safe secret/password handling, and controlled logging.

### Official References

- Spring Security 6.5 — Method Security (SpEL, @PreAuthorize, @PostAuthorize, parameter discovery, @P): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests (relationship between HTTP and method security): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — @WithMockUser and testing method security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc testing integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework — Spring Expression Language (SpEL): https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
