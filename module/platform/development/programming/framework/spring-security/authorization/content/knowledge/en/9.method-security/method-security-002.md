# Enabling `@EnableMethodSecurity` and Annotation Groups in Spring Security

> **Scope:** Spring Security 6.5, Spring Boot 3.5.x, Java 17+, Servlet/Spring MVC. This lesson covers how to enable **method-level authorization**, classify **@PreAuthorize / @PostAuthorize / @PreFilter / @PostFilter**, **@Secured**, and **@RolesAllowed / @PermitAll / @DenyAll**, explain proxy/AOP behavior, configure flags, and write tests proving policies are actually enforced.

## 1. Why Do We Need Method Security?

An HTTP rule might only require the user to be logged in:

~~~java
// Fragment inside http.authorizeHttpRequests(...):
.requestMatchers("/api/**").authenticated()
~~~

However, the same service can be called from multiple controllers or other Spring beans. Method security protects the **service action**, not just a single path:

~~~java
@Service
class InvoiceService {
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approve(String invoiceId) {
        return "approved " + invoiceId;
    }
}
~~~

This is a **Spring fragment**, not a standalone Java program. When method security is enabled and invoked through a Spring proxy, someone lacking `invoice:approve` cannot execute the method. Spring Security may throw `AccessDeniedException` or a subclass such as `AuthorizationDeniedException`. In HTTP with an authenticated user, these typically become **403 Forbidden**.

| Checkpoint | Purpose | Example |
| --- | --- | --- |
| HTTP security | Restrict HTTP URL/method | `/api/**` requires authentication |
| Method security | Restrict functional invocation | `@PreAuthorize("hasRole('ADMIN')")` |
| Domain security | Restrict specific resource | Does the user belong to invoice 42's tenant? |

**HTTP ALLOW does not cancel method security.** Conversely, `@PermitAll` on a service does not bypass HTTP `authenticated()` if the HTTP filter already blocked the request earlier.

## 2. Enabling Method Security: Not Enabled Automatically by Spring Boot Starter Security

Spring Boot Starter Security protects the web layer via HTTP configuration, but **does not automatically enable method authorization**. You must declare:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityMethodConfig {
}
~~~

Or place `@EnableMethodSecurity` directly on the `@SpringBootApplication` main class. In standard proxy configuration, Spring Security registers method interceptors/advisors to inspect annotations on Spring-managed methods.

### Three Groups and Enable/Disable Flags

| Flag in `@EnableMethodSecurity` | Default Value | Annotation Group |
| --- | :---: | --- |
| `prePostEnabled` | **true** | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` |
| `securedEnabled` | **false** | `@Secured` |
| `jsr250Enabled` | **false** | `@RolesAllowed`, `@PermitAll`, `@DenyAll` |

These examples are **mutually exclusive alternatives**; do not place all four on one class:

~~~java
@EnableMethodSecurity
// Pre/post by default.

@EnableMethodSecurity(securedEnabled = true)
// Pre/post + @Secured.

@EnableMethodSecurity(jsr250Enabled = true)
// Pre/post + JSR-250.

@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
// All three groups.
~~~

**Easy-to-forget detail:** `@EnableMethodSecurity(securedEnabled = true)` **still leaves the pre/post group enabled**. To enable only `@Secured`, explicitly set `prePostEnabled = false`. Setting this flag in a system that uses `@PreAuthorize` will disable those pre/post rules.

### Importing the Right Packages

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.annotation.Secured;

import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

With Spring Boot 3 / Spring Security 6, use the **`jakarta.annotation.security`** namespace; do not use `javax.annotation.security` from the Spring Boot 2 era.

## 3. Four Pre/Post Annotations and Evaluation Positions

### `@PreAuthorize` — Checked Before Running Business Logic

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String readReport() {
    return "report";
}
~~~

The SpEL expression is evaluated before invoking the target method. If DENY, the business logic does not run through the proxy. You can use `hasRole('ADMIN')`, `hasAuthority('report:read')`, `authentication.name`, method parameters, and custom beans.

A more complex example:

~~~java
@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #invoiceId)")
public void approveInvoice(String invoiceId) {
    // Perform the update after authorization succeeds.
}
~~~

This is a fragment requiring an `invoicePolicy` bean with the matching API. For SpEL `#invoiceId`, the compiler configuration must preserve parameter names (usually `-parameters`) or you must use `@P` when needed.

**Do not confuse `hasRole('ADMIN')` with the literal `ADMIN`**: by default `hasRole('ADMIN')` checks the authority `ROLE_ADMIN`, whereas `hasAuthority('report:read')` requires the exact string `report:read`.

### `@PostAuthorize` — Checked After Obtaining the Result

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document findDocument(String id) {
    return repository.load(id);
}
~~~

`returnObject` is the value returned by the target method. It lets you check whether the caller is the owner of the loaded data. This is a fragment requiring a model and repository.

**Risk:** the method has already run **before** the post-check. `@PostAuthorize` is not suitable as the sole guard for **write/delete** methods, because the database or side effects may already have been modified before the denial. Prefer `@PreAuthorize` and domain checks for write operations.

### `@PreFilter` — Filtering an Input Collection

~~~java
@PreFilter("filterObject.owner == authentication.name")
public int countMine(List<Document> documents) {
    return documents.size();
}
~~~

`filterObject` represents each collection element. Spring filters before the target method processes it. If there are multiple collection parameters, specify `filterTarget`. This example requires a **mutable list**, such as `new ArrayList<>(...)`; immutable `List.of(...)` does not work when the framework needs to remove elements.

### `@PostFilter` — Filtering an Output Collection

~~~java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> visibleDocuments() {
    return new ArrayList<>(repository.findSome());
}
~~~

`@PostFilter` does not necessarily DENY the entire call; it filters the returned elements. Suitable for examples or small collections. For large tables/multi-tenant data, **filter at the database/query** before loading, avoiding loading unauthorized data and breaking pagination.

### Distinguishing AUTHORIZE and FILTER

| Annotation | Input or Output? | Allows/Denies Whole Call? |
| --- | --- | --- |
| `@PreAuthorize` | Before execution | Yes |
| `@PostAuthorize` | After execution | Yes, based on the result |
| `@PreFilter` | Parameter collection | Filters elements |
| `@PostFilter` | Returned collection | Filters elements |

## 4. The `@Secured` Group (Legacy)

`@Secured` works when `securedEnabled = true`:

~~~java
@Secured("ROLE_MANAGER")
public String approveReview() {
    return "manager review";
}
~~~

Do not write SpEL expressions in `@Secured`:

~~~java
// Wrong intent:
@Secured("hasRole('MANAGER')")

// Correct if using the default role prefix:
@Secured("ROLE_MANAGER")
~~~

When multiple roles are listed, the normal semantics require satisfying **at least one** role, not ANDing multiple conditions. If you need to check tenant, owner, action, and role, use `@PreAuthorize` + a policy bean or an appropriate `AuthorizationManager`.

**Mandatory negative test:** If you forget `securedEnabled = true`, a user lacking the role can still enter the method. A test that only proves a manager gets 200 will not catch that bug.

## 5. The JSR-250/Jakarta Group: `@RolesAllowed`, `@PermitAll`, `@DenyAll`

To enable this group:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

The annotations in Boot 3:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Example:

~~~java
@RolesAllowed("ADMIN")
public String auditSettings() { return "audit"; }

@PermitAll
public String help() { return "help"; }

@DenyAll
public String blocked() { return "blocked"; }
~~~

- `@RolesAllowed("ADMIN")` checks the `ADMIN` role using the default prefix, typically corresponding to `ROLE_ADMIN`.
- `@PermitAll` adds no barrier in the JSR-250 interceptor; **it does not bypass HTTP authentication, CSRF, or other interceptors**.
- `@DenyAll` denies according to JSR-250 policy; **it has no effect** if this annotation group has not been enabled.

**Comparing ADMIN intent**: `@PreAuthorize("hasRole('ADMIN')")`, `@Secured("ROLE_ADMIN")`, and `@RolesAllowed("ADMIN")` can produce equivalent results under default prefix configuration, but require different **activation flags**. With a custom role prefix/hierarchy, test every consumer.

## 6. Spring AOP and Self-Invocation: Why Annotations Sometimes Do Not Run

In standard proxy mode:

~~~text
Spring controller
       |
       v
Spring proxy of the service
       |-- PreAuthorize, Secured, JSR-250 ... (if applicable)
       |-- DENY -> AccessDeniedException
       v
Target service method
       |-- PostAuthorize / PostFilter ... (if applicable)
       v
Caller receives result
~~~

The diagram only shows the main flow, not the complete order of every advisor. Cases to verify:

- **self-invocation:** `this.securedMethod()` inside the same instance usually **does not go through the proxy**, and can bypass the guard.
- Objects instantiated with `new Service()` do not belong to the Spring `ApplicationContext` and are not proxied as beans.
- `private`/`final` methods, final classes, or unsuitable proxy types may not be intercepted; design methods to be proxyable and test them.
- Methods **without annotations** are not automatically denied just because `@EnableMethodSecurity` is enabled.
- `@Async` and work on other threads do not automatically carry the right `SecurityContext`; propagation must be designed explicitly.
- Class/interface annotations have inheritance and override rules; multiple interfaces carrying conflicting policies can make the configuration invalid.

An annotation of the same type on a method can **override** the corresponding class-level annotation. With multiple **different annotation types** on one invocation, interceptors can evaluate sequentially, requiring all applicable conditions to pass. Do not repeat two `@PreAuthorize` annotations on the same method; use one combined expression:

~~~java
@PreAuthorize("hasRole('MANAGER') and hasAuthority('task:approve')")
public String approveTask() {
    return "approved";
}
~~~

## 7. Spring Boot Java 17+ Application Demonstrating All Three Groups

### Dependencies and Sample Data

Use Spring Boot **3.5.x / Java 17+**, Maven, with `spring-boot-starter-web` and `spring-boot-starter-security`; add test dependencies in section 9.

| User | Authorities from UserDetailsService |
| --- | --- |
| Alice | `ROLE_USER` |
| Bob | `ROLE_MANAGER` |
| Carol | `ROLE_ADMIN` |
| Dave | `report:read` |

**No role hierarchy is configured** in the demo: ADMIN does not automatically imply MANAGER and USER. This keeps the verification results of each annotation group clear.

### Complete Runnable Code

Create **`src/main/java/com/example/methodsecurity/MethodSecurityApplication.java`**:

~~~java
package com.example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
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
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("MANAGER")
            .build();
        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();
        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .authorities("report:read")
            .build();
        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    public static final class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }
        public String getId() { return id; }
        public String getOwner() { return owner; }
    }

    @Service
    static class DocumentService {

        @PreAuthorize("hasRole('USER')")
        public String userArea() { return "user area"; }

        @PreAuthorize("hasAuthority('report:read')")
        public String reportArea() { return "report area"; }

        @Secured("ROLE_MANAGER")
        public String managerArea() { return "manager area"; }

        @RolesAllowed("ADMIN")
        public String adminArea() { return "admin area"; }

        @PermitAll
        public String help() { return "help"; }

        @DenyAll
        public String blocked() { return "must not be returned"; }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Document readDocument(String id) {
            return new Document(id, "alice");
        }

        @PreFilter("filterObject.owner == authentication.name")
        public int countInput(List<Document> input) {
            return input.size();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> visibleDocuments() {
            return new ArrayList<>(List.of(
                new Document("a1", "alice"),
                new Document("b1", "bob"),
                new Document("a2", "alice")
            ));
        }

        public String noAnnotation() {
            return "no method annotation";
        }
    }

    @RestController
    static class Api {

        private final DocumentService service;
        Api(DocumentService service) { this.service = service; }

        @GetMapping("/public/ping")
        String ping() { return "pong"; }

        @GetMapping("/api/pre/user")
        String preUser() { return service.userArea(); }

        @GetMapping("/api/pre/report")
        String preReport() { return service.reportArea(); }

        @GetMapping("/api/secured/manager")
        String securedManager() { return service.managerArea(); }

        @GetMapping("/api/jsr/admin")
        String jsrAdmin() { return service.adminArea(); }

        @GetMapping("/api/jsr/permit")
        String jsrPermit() { return service.help(); }

        @GetMapping("/api/jsr/deny")
        String jsrDeny() { return service.blocked(); }

        @GetMapping("/api/post/document/{id}")
        Document document(@PathVariable("id") String id) {
            return service.readDocument(id);
        }

        @GetMapping("/api/filter/input")
        int filterInput() {
            List<Document> docs = new ArrayList<>(List.of(
                new Document("a1", "alice"),
                new Document("b1", "bob"),
                new Document("a2", "alice")
            ));
            return service.countInput(docs);
        }

        @GetMapping("/api/filter/output")
        List<Document> filterOutput() {
            return service.visibleDocuments();
        }

        @GetMapping("/api/no-annotation")
        String unannotated() { return service.noAnnotation(); }
    }
}
~~~

**What the example proves:**

1. `@EnableMethodSecurity` on the main app registers all three groups (pre/post, Secured, JSR-250).
2. HTTP only requires `authenticated()` for `/api/**`. Logged-in users still must pass the method guard.
3. `DocumentService` is Spring-managed. The controller **injects the bean** and calls through the proxy, rather than using `new` or `this.securedMethod()`.
4. Alice (`ROLE_USER`) passes `@PreAuthorize("hasRole('USER')")`; Dave (`report:read`) passes `@PreAuthorize("hasAuthority('report:read')")`.
5. Bob (`ROLE_MANAGER`) passes `@Secured("ROLE_MANAGER")`; Carol (`ROLE_ADMIN`) passes `@RolesAllowed("ADMIN")`.
6. `@PermitAll` on the service only permits at the JSR-250 layer; HTTP still requires credentials for `/api/jsr/permit`.
7. `@DenyAll` blocks every user, including Carol.
8. `@PostAuthorize` only lets the caller receive the document if the owner is Alice, after the method has produced the result.
9. `@PreFilter`/`@PostFilter` demonstrate filtering elements by `authentication.name`.
10. Unannotated methods still execute for authenticated users — protect them explicitly if sensitive.

All endpoints are **GET** to avoid mixing up method authorization results with POST CSRF checks. When building real write endpoints, verify both CSRF (depending on credential model) and domain policies before side effects.

## 8. Expected HTTP Result Matrix

| Principal | Pre USER | Pre report | Secured MANAGER | JSR ADMIN | JSR Permit | JSR Deny |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 | 401 | 401 | 401 |
| Alice — USER | **200** | 403 | 403 | 403 | **200** | 403 |
| Bob — MANAGER | 403 | 403 | **200** | 403 | **200** | 403 |
| Carol — ADMIN | 403 | 403 | 403 | **200** | **200** | 403 |
| Dave — report:read | 403 | **200** | 403 | 403 | **200** | 403 |

Columns correspond to URLs `/api/pre/user`, `/api/pre/report`, `/api/secured/manager`, `/api/jsr/admin`, `/api/jsr/permit`, `/api/jsr/deny`. HTTP Basic typically returns 401 for anonymous on protected endpoints and 403 for authenticated users lacking permission. Form login configurations may redirect with 302.

| Endpoint | Alice | Bob | Carol |
| --- | --- | --- | --- |
| `/api/post/document/a1` | 200 | 403 | 403 |
| `/api/filter/input` | `2` | `1` | `0` |
| `/api/filter/output` | JSON 2 documents | JSON 1 document | Empty JSON |
| `/api/no-annotation` | 200 | 200 | 200 |

There is no role hierarchy, so ADMIN **does not automatically inherit** MANAGER/USER. Do not assume "admin has all permissions" unless that relationship is explicitly declared.

### Testing with curl

~~~bash
# Start the Maven app at the project root:
./mvnw spring-boot:run

# Public endpoint:
curl -i http://localhost:8080/public/ping

# Anonymous does not pass HTTP authenticated():
curl -i http://localhost:8080/api/jsr/permit

# Pre/post group:
curl -i -u alice:demo123 http://localhost:8080/api/pre/user
curl -i -u bob:demo456 http://localhost:8080/api/pre/user
curl -i -u dave:demo000 http://localhost:8080/api/pre/report

# Legacy @Secured and JSR-250:
curl -i -u bob:demo456 http://localhost:8080/api/secured/manager
curl -i -u carol:demo789 http://localhost:8080/api/jsr/admin
curl -i -u carol:demo789 http://localhost:8080/api/jsr/deny

# Post-check owner and filter results:
curl -i -u alice:demo123 http://localhost:8080/api/post/document/a1
curl -i -u bob:demo456 http://localhost:8080/api/post/document/a1
curl -i -u alice:demo123 http://localhost:8080/api/filter/input
curl -i -u bob:demo456 http://localhost:8080/api/filter/output
~~~

On Windows, you can run `mvnw.cmd spring-boot:run`. For ALLOWED GET requests, the controller returns bodies such as `user area`, `report area`, `manager area`, `admin area`, filter counts, or JSON documents. Sample passwords are for learning only; real environments must use HTTPS and secret management.

## 9. MockMvc: Writing Tests to Catch Forgotten Annotation Activation

### Test Dependencies

In `pom.xml`, child elements of `<dependencies>`:

~~~xml
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
~~~

If the project already has `starter-test`, do not add a duplicate. Use compatible versions managed by the Spring Boot BOM.

### Complete Test Class

Create **`src/test/java/com/example/methodsecurity/MethodSecurityApplicationTests.java`**:

~~~java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // user,password,path,expected status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/jsr/permit,401",
        "anonymous,none,/api/pre/user,401",

        "alice,demo123,/api/pre/user,200",
        "alice,demo123,/api/pre/report,403",
        "alice,demo123,/api/secured/manager,403",
        "alice,demo123,/api/jsr/admin,403",
        "alice,demo123,/api/jsr/permit,200",
        "alice,demo123,/api/jsr/deny,403",

        "bob,demo456,/api/pre/user,403",
        "bob,demo456,/api/pre/report,403",
        "bob,demo456,/api/secured/manager,200",
        "bob,demo456,/api/jsr/admin,403",
        "bob,demo456,/api/jsr/permit,200",
        "bob,demo456,/api/jsr/deny,403",

        "carol,demo789,/api/pre/user,403",
        "carol,demo789,/api/pre/report,403",
        "carol,demo789,/api/secured/manager,403",
        "carol,demo789,/api/jsr/admin,200",
        "carol,demo789,/api/jsr/permit,200",
        "carol,demo789,/api/jsr/deny,403",

        "dave,demo000,/api/pre/user,403",
        "dave,demo000,/api/pre/report,200",
        "dave,demo000,/api/secured/manager,403",
        "dave,demo000,/api/jsr/admin,403",
        "dave,demo000,/api/jsr/permit,200",
        "dave,demo000,/api/jsr/deny,403"
    })
    void authorizationMatrix(
        String username, String password, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder req = get(path);
        if (!"anonymous".equals(username)) {
            req.with(httpBasic(username, password));
        }
        mvc.perform(req).andExpect(status().is(expected));
    }

    @Test
    void postAuthorizeChecksOwner() throws Exception {
        mvc.perform(get("/api/post/document/a1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.id").value("a1"));

        mvc.perform(get("/api/post/document/a1")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void preFilterChangesInput() throws Exception {
        mvc.perform(get("/api/filter/input")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("2"));
        mvc.perform(get("/api/filter/input")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("1"));
    }

    @Test
    void postFilterChangesOutput() throws Exception {
        mvc.perform(get("/api/filter/output")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.length()").value(2))
            .andExpect(jsonPath("$[0].owner").value("alice"));

        mvc.perform(get("/api/filter/output")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.length()").value(1))
            .andExpect(jsonPath("$[0].id").value("b1"));
    }

    @Test
    void unannotatedDoesNotImplyDeny() throws Exception {
        mvc.perform(get("/api/no-annotation")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("no method annotation"));
    }

    @Test
    void denyAllBlocksAdmin() throws Exception {
        mvc.perform(get("/api/jsr/deny")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordIs401() throws Exception {
        mvc.perform(get("/api/pre/user")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Cases that catch misconfigurations:**

- If `securedEnabled` is not enabled, Alice can slip into `/api/secured/manager`: the 403 test catches the bug.
- If `jsr250Enabled` is not enabled, Bob can slip into `/api/jsr/admin` and Carol can enter `/api/jsr/deny`: negative tests catch the bug.
- If `prePostEnabled` is disabled, unauthorized cases on `@PreAuthorize`/`@PostAuthorize` are no longer blocked.
- If `@PreFilter`/`@PostFilter` do not run, counts and returned JSON are wrong.
- Anonymous gets 401 even though the method has `@PermitAll` because the HTTP guard still requires authentication.

Run:

~~~bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

These are the **expected results** of the sample code, not a claim that tests were executed. Evaluate using actual Maven/JUnit output and exit codes. All endpoints are GET, so no CSRF token is needed in the demo to distinguish the source of a 403.

### Testing the Service Directly with `@WithMockUser`

You can inject the service proxy in a Spring test and use:

~~~java
// Fragment in a test with a Spring context:
@Autowired
MethodSecurityApplication.DocumentService service;

@Test
@WithMockUser(roles = "USER")
void userCanCallService() {
    assertEquals("user area", service.userArea());
}
~~~

Needs imports for `@WithMockUser` and `assertEquals`. This is a **fragment**, not a standalone test class. Do not use `new DocumentService()` to test method security, because a manually created object does not go through the proxy. `@WithMockUser` mocks Authentication for the test method, while `httpBasic` also verifies `UserDetailsService`/password mapping.

## 10. Combining Annotations, Migration, and Multi-Tier Architecture

### Multiple Annotations in Effect Together

For a read-only method, you may need both a permission and an owner check:

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document readOne(String id) {
    return repository.load(id);
}
~~~

This is a fragment requiring a real repository and `Document`. `@PreAuthorize` checks before, `@PostAuthorize` checks after, and both conditions must pass. Do not repeat **two `@PreAuthorize`** annotations on the same method: use one SpEL expression with `and` or delegate to a policy bean.

### Migrating `@EnableGlobalMethodSecurity`

Modern Spring Security replaces `@EnableGlobalMethodSecurity` with `@EnableMethodSecurity`, using the `AuthorizationManager` API and Spring AOP advisors more directly:

~~~java
// Old:
@EnableGlobalMethodSecurity(prePostEnabled = true)

// New:
@EnableMethodSecurity
~~~

Old case enabling **only `@Secured`**:

~~~java
// Old:
@EnableGlobalMethodSecurity(securedEnabled = true)

// New: preserve intent of @Secured only:
@EnableMethodSecurity(
    securedEnabled = true,
    prePostEnabled = false
)
~~~

These are **mutually exclusive configuration fragments**. Migration must re-verify flags, role prefixes, method expression handlers, custom voters/managers, AOP proxies, and DENY tests.

### Some Advanced Capabilities

Spring Security 6.5 also supports meta-annotations (e.g., defining a custom `@CanReadInvoice` built on `@PreAuthorize`), custom authorization beans, `@AuthorizeReturnObject` to protect properties of returned objects, and `@HandleAuthorizationDenied` to handle denials via supported APIs. These are useful for specific business logic, **but do not replace** the fundamental groups or the principle of least privilege.

## 11. Implementation Checklist and Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Adding `@PreAuthorize` without `@EnableMethodSecurity` | Method may go unchecked | Enable method security, test 403 |
| Forgetting `securedEnabled=true` | `@Secured` is ignored | Enable opt-in |
| Forgetting `jsr250Enabled=true` | `@RolesAllowed`/`@DenyAll` are ignored | Enable opt-in |
| Accidentally setting `prePostEnabled=false` | `@PreAuthorize`/filters stop working | Review configuration |
| Mixing up Jakarta and Javax in Boot 3 | Migration/build/annotation errors | Use the right package |
| Method calls `this.secured()` | **self-invocation** bypasses proxy | Use Spring bean proxy |
| Object created with `new` | No interceptor | Inject bean |
| Inappropriate `private`/`final` usage | Proxy may fail to intercept | Ensure method is interceptable |
| Using `@PostAuthorize` on write operations | Side effects may already have occurred | Preauthorize before writing |
| Using `@PostFilter` to filter large datasets | High memory usage, broken pagination | Filter at DB/query |
| `@PermitAll` while HTTP requires auth | Anonymous still gets 401 | Understand multiple layers |
| Testing only ALLOW | Permission gaps go unnoticed | Write negative tests |
| Ignoring tenant/owner | IDOR/BOLA risk | Domain-level policy |
| Seeing 403 on POST and guessing missing role | Could be CSRF | Distinguish filter vs method |
| No HTTP fallback | New endpoints may be exposed | Design proper default deny |

**Short checklist:** Are all three groups configured properly? Is the service a bean? Is there a proxy? Are guards placed on sensitive operations? Did you test 200/401/403? Did you check owner/tenant and CSRF for write operations? Do roles have matching prefixes? Do background tasks have a valid `SecurityContext`? Did you re-test after changing annotations/configuration?

## 12. Self-Check

**Question 1.** Which group does `@EnableMethodSecurity` enable by default?  
**Answer:** `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.

**Question 2.** What must be enabled for `@Secured` to be checked?  
**Answer:** `securedEnabled = true`.

**Question 3.** What must be enabled for `@RolesAllowed`, `@PermitAll`, `@DenyAll`?  
**Answer:** `jsr250Enabled = true`; in Boot 3 use the Jakarta namespace.

**Question 4.** Does `@PostAuthorize` guarantee side effects will not happen when permission is missing?  
**Answer:** No. The method has already executed before the post-check.

**Question 5.** Is `@Secured("hasRole('ADMIN')")` valid SpEL?  
**Answer:** Not as intended; use `@Secured("ROLE_ADMIN")`.

**Question 6.** Does `@PermitAll` on a method bypass HTTP `authenticated()`?  
**Answer:** No.

**Question 7.** Why is `this.securedMethod()` dangerous?  
**Answer:** Self-invocation can bypass the method security proxy/interceptor.

**Question 8.** When `@PreFilter` receives an immutable `List.of(...)`, should you assume the framework can modify the list?  
**Answer:** No. Use a mutable collection when the filter needs to remove elements.

**Question 9.** Which test catches that `jsr250Enabled` is not enabled?  
**Answer:** Testing a non-admin user getting 403 on `@RolesAllowed`, and even admin getting 403 on `@DenyAll`.

**Question 10.** Does enabling method security automatically DENY all unannotated methods?  
**Answer:** No. You must design coverage across HTTP/method/domain.

**Question 11.** Why are both ALLOW and DENY tests needed?  
**Answer:** An inactive annotation can still give an authorized user 200; only testing an unauthorized user getting 403 detects a missing guard.

**Question 12.** Does migrating from `@EnableGlobalMethodSecurity(securedEnabled=true)` to `@EnableMethodSecurity(securedEnabled=true)` keep the same default flags?  
**Answer:** Not necessarily. The new annotation enables pre/post by default; if you want `@Secured` only, set `prePostEnabled=false`.

**Conclusion:** `@EnableMethodSecurity` is the **activation** step, while annotations only have value when interceptors are registered and calls pass properly through Spring AOP. Pre/post are enabled by default; `@Secured` and JSR-250 require opt-in. Everything must be verified with a **proper allow / proper deny** permission matrix.

## Official Documentation

- Spring Security 6.5 — Method Security (annotations, proxies, migration): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — EnableMethodSecurity API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html
- Spring Security 6.5 — MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/
- Spring Security 6.5 — HTTP Basic test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — HTTP authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
