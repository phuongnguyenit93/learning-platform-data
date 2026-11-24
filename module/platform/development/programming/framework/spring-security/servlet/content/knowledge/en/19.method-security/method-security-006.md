# @Secured and @RolesAllowed with Corresponding Configuration Flags

In **Spring Security for Servlet applications**, permission checks do not occur only at HTTP URLs. A controller, service, or business component can be called from multiple paths: an HTTP request, a scheduler, a message listener, another service, or an internal tool. **Method security** lets you declare authorization conditions directly on Spring-managed methods or classes. Two common annotations are Spring Security's `@Secured` and JSR-250/Jakarta's `@RolesAllowed`.

Both look similar because both require roles, yet three points are mandatory to understand before deploying:

1. **They are not automatically enabled by `@EnableMethodSecurity` alone.** In Spring Security 6, you must explicitly enable `securedEnabled = true` for `@Secured` and `jsr250Enabled = true` for `@RolesAllowed`.
2. **Role syntax usually differs:** by default `@Secured("ROLE_ADMIN")` references the authority with the `ROLE_` prefix directly, whereas `@RolesAllowed("ADMIN")` is typically mapped to `ROLE_ADMIN` via Spring Security's default role prefix.
3. **Annotations only take effect when the call goes through the method-security interceptor mechanism** (typically a Spring AOP proxy). Calling another method on the same object via `this`, instantiating objects with `new`, or calling private methods will not automatically be intercepted like an external call through a proxy.

This lesson uses **Java 17+, Spring Boot 3.x, and Spring Security 6.x (Servlet/MVC)**. It covers the execution mechanism, comparison tables, right/wrong configurations, a Spring Boot demonstration program with `@Secured`/`@RolesAllowed`/`@PermitAll`/`@DenyAll`, MockMvc and method-security tests, a standalone Java 17 program simulating permission decisions, production pitfalls, security considerations, and a checklist. The examples use simple roles to focus on annotations; when permissions depend on ownership, tenant, or object data, advanced policies such as `@PreAuthorize` or an appropriate `AuthorizationManager` are required.

## 1. HTTP Security Differs from Method Security

HTTP security protects Servlet request entry points; method security protects **method invocations on Spring-managed beans**.

~~~text
HTTP client
    |
    v
Spring Security FilterChainProxy
    |-- Authentication filters -> Authentication + authorities
    |-- AuthorizationFilter  -> HTTP URL/method allowed?
    |
    v
Spring MVC Controller
    |
    v
Spring AOP method-security proxy
    |-- @Secured / @RolesAllowed / @PreAuthorize interceptor
    |-- read Authentication from SecurityContext
    |-- check authorities/policy
    |-- grant: invoke target method
    |-- deny: AccessDeniedException / AuthorizationDeniedException
    |
    v
Service method
    |
    v
Repository / domain logic
~~~

The diagram illustrates the flow **when a Spring proxy and appropriate security interceptors are present**. A call within the same instance, or a bean not managed by Spring, may bypass the proxy even though the source code carries annotations.

### Why Two Layers?

| Layer | What It Does Well | Limitations |
| --- | --- | --- |
| `authorizeHttpRequests(...)` | Enforces URLs, HTTP methods, request matchers, login/authority requirements before controllers | Does not automatically protect a service if invoked from batch/queue or other APIs |
| `@Secured`/`@RolesAllowed` | Requires roles at intercepted Spring bean method invocation points | Unaware of HTTP routes or object ownership; relies on proxies and authentication context |
| `@PreAuthorize` | Expresses complex conditions involving parameters, principal, and policy beans | Requires care with expressions, bean naming, and trusted data; more complex |
| Rules inside service/repository | Can check ownership, tenant, data state, and consistency | Must be invoked consistently from all usage paths |

For applications needing strict control, **HTTP gates and method security are complementary layers**. For example, the filter requires `authenticated()` for the whole API, while administrative service methods require `ROLE_ADMIN`.

### An Important Question

Can you add `@Secured("ROLE_ADMIN")` to one service method and remove all HTTP security? **Do not reason that way.** Beyond that method there are other controllers, pre-call logic, static resources, or public routes; method security does not replace the request firewall, CSRF, authentication, HTTP headers, or routing policy.

## 2. What Is @Secured?

`@Secured` lives in the Spring Security package:

~~~java
import org.springframework.security.access.annotation.Secured;
~~~

The annotation takes authority/role strings, typically `ROLE_ADMIN` or `ROLE_USER`:

~~~java
@Secured("ROLE_ADMIN")
public String viewAuditLog() {
    return "audit log";
}
~~~

If the bean is protected by the method-security interceptor and the current authentication lacks the required authority, the call is denied before the method body runs.

### @Secured Uses Authority Strings

Example user authority data:

~~~text
admin   -> ["ROLE_ADMIN"]
auditor -> ["ROLE_AUDITOR"]
member  -> ["ROLE_USER"]
~~~

Rule:

~~~java
@Secured("ROLE_ADMIN")
public String adminOnly() {
    return "only admin";
}
~~~

Only `ROLE_ADMIN` is granted in this example. If an authenticated username only has `ROLE_USER`, the method must be denied.

### Multiple Roles: OR or AND?

~~~java
@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
public String reports() {
    return "reports";
}
~~~

For this annotation, multiple values mean **at least one of the listed authorities is required** — an OR policy, not all of them simultaneously. Either admin or auditor can call it. If business logic requires **both** conditions, or combines role + tenant + resource state, use a more expressive mechanism instead of assuming an array means AND.

### Class-Level and Method-Level

`@Secured` can be placed on a class to declare a default for applicable methods:

~~~java
@Secured("ROLE_ADMIN")
@Service
public class AdminTasks {
    public String overview() {
        return "overview";
    }
}
~~~

This is a fragment: `@Service` and `@Secured` imports are required, not a complete file. When adding method-level annotations on the same class or mixing annotation types, metadata resolution and interceptor behavior can depend on framework/version. Pick a consistent convention and **test every public method**, rather than treating class-level annotations as an excuse to skip review.

**Do not use `@Secured` as an expression language string:** `@Secured("hasRole('ADMIN')")` does not mean `@PreAuthorize("hasRole('ADMIN')")`. `@Secured` takes authority/role names and does not evaluate SpEL.

## 3. @RolesAllowed: JSR-250/Jakarta Security Annotations

`@RolesAllowed` belongs to the standardized annotation family (in Spring Boot 3 / Jakarta namespace):

~~~java
import jakarta.annotation.security.RolesAllowed;
~~~

Example:

~~~java
@RolesAllowed("ADMIN")
public String manageTeams() {
    return "team management";
}
~~~

In standard Spring Security 6.x configurations, `@RolesAllowed("ADMIN")` is evaluated with the default `ROLE_` prefix, meaning the `ROLE_ADMIN` authority is required. **This prefix is a configuration convention**, not something the Java compiler generates automatically.

### Roles in @RolesAllowed

~~~java
@RolesAllowed({"ADMIN", "AUDITOR"})
public String readReports() {
    return "reports";
}
~~~

Here **either role** suffices, matching OR semantics. Do not mistake this array for AND.

### @PermitAll and @DenyAll in JSR-250

The JSR-250 family also includes:

~~~java
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;

@PermitAll
public String publicMessage() {
    return "public";
}

@DenyAll
public String disabledOperation() {
    return "disabled";
}
~~~

- `@PermitAll` permits any principal according to the corresponding JSR-250 method-security rule (it does not open URLs if HTTP policy still denies).
- `@DenyAll` rejects method calls through the JSR-250 interceptor, even if the user holds ROLE_ADMIN.
- These two annotations only have effect when **JSR-250 method security is enabled** in configuration. For methods requiring authentication at the HTTP layer, `@PermitAll` does not override the filter's `authenticated()` requirement.

Do not place `@PermitAll` and `@DenyAll` on the same method. Avoid mixing `@PermitAll` with `@Secured` on one method to "combine" results without fully understanding interceptors/ordering; define one clear policy and test it.

### Jakarta vs javax

On Spring Boot 3, Spring Framework 6, and Spring Security 6, use:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Older Boot 2 tutorials sometimes used `javax.annotation.security.RolesAllowed`. Do not copy `javax.annotation.*` imports into a Jakarta project assuming they will be recognized. Having `javax.annotation-api` on the classpath does not make `javax` annotations equivalent to `jakarta` for interceptors compiled against the newer API.

## 4. Corresponding Configuration: The Most Important Step

From Spring Security 6 onward, modern method security is enabled with `@EnableMethodSecurity`.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
~~~

This is a complete Java configuration file if saved as `MethodSecurityConfig.java` with imports (package omitted for brevity). In real applications, `@EnableMethodSecurity` can be placed on the configuration class containing SecurityFilterChain.

### Default Flags of @EnableMethodSecurity

| Feature | Flag | Common Default in Spring Security 6 | Want to Use It? |
| --- | --- | --- | --- |
| `@PreAuthorize` / `@PostAuthorize` and pre/post family | `prePostEnabled` | `true` | No need to specify explicitly if keeping default |
| `@Secured` | `securedEnabled` | `false` | **Must set true** |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `jsr250Enabled` | `false` | **Must set true** |

Key point: writing `@EnableMethodSecurity` alone **does not mean** either `@Secured` or `@RolesAllowed` is enforced. This is a silent security failure: annotations look reassuring in code reviews while no interceptor is active.

### Single-Mechanism Configurations

If using only Spring Security `@Secured`:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

If using only Jakarta `@RolesAllowed` and the JSR-250 family:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

If using both:

~~~java
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
~~~

All the lines above are **fragments** placed on an appropriate `@Configuration`/bootstrap class, not standalone runnable Java files. Do not enable `securedEnabled` and assume JSR-250 is active; nor enable `jsr250Enabled` and assume Spring `@Secured` is active.

### Legacy @EnableGlobalMethodSecurity

Older Spring Security 5 guides used:

~~~java
// Legacy API; do not use as the primary configuration in Spring Security 6 lessons.
@EnableGlobalMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

In Spring Security 6, `@EnableMethodSecurity` is the preferred modern approach. When migrating an older project to Spring Security 6, review custom beans/interceptors and integration tests rather than just renaming the annotation and assuming every rule still executes.

## 5. The ROLE_ Prefix and Mapping Roles to Authorities

Spring Security distinguishes **role name** from **GrantedAuthority**. Under common defaults:

~~~text
User.roles("ADMIN")             -> GrantedAuthority: ROLE_ADMIN
@Secured("ROLE_ADMIN")          -> compared against authority ROLE_ADMIN
@RolesAllowed("ADMIN")          -> role ADMIN -> authority ROLE_ADMIN
hasRole("ADMIN")                -> authority ROLE_ADMIN
hasAuthority("ROLE_ADMIN")      -> authority ROLE_ADMIN
~~~

These are **common defaults**, which can change if an application configures custom role prefixes or authority mappings. With external identity providers, authorities might be `SCOPE_admin`, `ROLE_ADMIN`, `ADMIN`, or another scheme.

### Correct Example When Creating Users in Spring Security

~~~java
UserDetails admin = User.withUsername("admin")
    .password(passwordEncoder.encode("demo-password"))
    .roles("ADMIN")
    .build();
~~~

`roles("ADMIN")` automatically adds the `ROLE_` prefix, giving admin `ROLE_ADMIN`. **Do not** call `roles("ROLE_ADMIN")` expecting it to stay intact as an arbitrary authority; the builder enforces rules against double prefixes and may reject values already starting with `ROLE_`.

To declare the full authority explicitly:

~~~java
UserDetails admin = User.withUsername("admin")
    .password(passwordEncoder.encode("demo-password"))
    .authorities("ROLE_ADMIN")
    .build();
~~~

The use of `roles` and `authorities` must remain consistent with the application's authentication provider contract.

### A Common Mistake

~~~java
// Likely wrong: user only has ROLE_ADMIN
@Secured("ADMIN")
public void manage() {
    // ...
}
~~~

Spring `@Secured` checks the literal authority name per the configured policy. If the principal holds `ROLE_ADMIN` while the annotation asks for `ADMIN`, the method can be denied. Conversely, with `@RolesAllowed("ADMIN")`, Spring Security's default JSR-250 setup typically prepends the prefix to match `ROLE_ADMIN`.

### What If the Role Prefix Is Customized?

An application may configure a non-default role prefix or authority mapping via `GrantedAuthorityDefaults` or corresponding method-authorization components. In that case verify **all** of:

- The actual authorities present in `Authentication.getAuthorities()`.
- How `@Secured`, `@RolesAllowed`, and HTTP `hasRole(...)` interpret roles.
- Consistency across role hierarchies, claim mappings, database roles, and test fixtures.

Do not assume changing a single bean automatically synchronizes every method/HTTP mechanism across versions. Write tests based on the exact authority strings returned by the provider.

## 6. Spring AOP Proxy: When Does the Annotation Actually Run?

Method security is normally implemented using **Spring AOP interception**. Calls must pass through the Spring-created proxy for the bean holding the protected method.

~~~text
Controller bean
      |
      | service.adminOperation()
      v
Spring proxy  ------------> Method security advisor/interceptor
                                   |
                                   +-- check authorities
                                   |
                              ALLOW / DENY
                                   |
                                   v
                              Target service method
~~~

If code uses `new AdminService()` instead of a bean from ApplicationContext, that object has no Spring method-security proxy.

### Self-Invocation Is a Major Trap

~~~java
@Service
public class UnsafeWorkflow {

    public String outer() {
        // Calls within the same instance usually DO NOT pass through the proxy.
        return this.restricted();
    }

    @Secured("ROLE_ADMIN")
    public String restricted() {
        return "sensitive";
    }
}
~~~

This is a **risk example**, not a recommended implementation. If a controller calls `outer()` on the bean and `outer()` has no rule, `this.restricted()` usually skips the method interceptor even though `restricted()` has `@Secured`. Consequence: direct calls to restricted() via the proxy are blocked, yet paths via outer() may escape the same check.

**Better solution:** move the restricted operation into **another bean** and inject it so calls execute through the bean proxy. Or place policies at external entry points and business services by design. Avoid tricks like self-injecting proxies, `AopContext.currentProxy()`, or tangling control flow just to dodge self-invocation when the architecture can be separated cleanly.

### Common Limitations

- **Private methods** must not be relied upon as secure interception points for proxy method security, as proxies usually do not intercept private calls.
- **Final classes/final methods** can cause restrictions with class-based proxies; behavior depends on proxy type and interfaces.
- **Methods on interfaces** may be proxied differently from class methods; choose a consistent annotation placement and test in the real project.
- **Non-public methods** behave differently between JDK dynamic proxies and CGLIB; for predictable behavior, use public methods on regular Spring beans.
- **Direct internal calls** via `this`, constructor invocations, static methods, and objects created with `new` are not protected like external proxy calls.
- **@Async/threads** may lack the original request's SecurityContext; protecting methods in async flows requires deliberate context propagation or service identities rather than relying on accidental ThreadLocals.

A test checking only that annotations exist in source or bytecode **is not enough**. Test actual calls through the Spring bean and assert AccessDeniedException/403 when permissions are missing.

## 7. Complete Example: Spring Boot, @Secured, and @RolesAllowed

We build an application with three demo accounts:

| User | Authorities from UserDetailsService | Purpose |
| --- | --- | --- |
| `admin` | ROLE_ADMIN | Allowed to call admin methods |
| `auditor` | ROLE_AUDITOR | Allowed to view admin/auditor methods |
| `member` | ROLE_USER | Only uses appropriate public/user routes |

Endpoints:

| Endpoint | Service Method Annotation | Expectation |
| --- | --- | --- |
| GET /api/secured/admin | `@Secured("ROLE_ADMIN")` | Admin only |
| GET /api/jsr250/admin | `@RolesAllowed("ADMIN")` | Admin only |
| GET /api/secured/report | `@Secured({"ROLE_ADMIN","ROLE_AUDITOR"})` | Admin or auditor |
| GET /api/jsr250/report | `@RolesAllowed({"ADMIN","AUDITOR"})` | Admin or auditor |
| GET /api/jsr250/locked | `@DenyAll` | Nobody |
| GET /api/public/info | `@PermitAll` + HTTP permitAll | Even anonymous can access |

The HTTP configuration lets requests reach controllers if authenticated (except public/info). **Method security** then checks roles at the service. This clean separation lets tests distinguish HTTP from method security.

### 7.1. Maven Dependencies

In a Spring Boot 3.x project with compatible parent/BOM and build plugins, `pom.xml` declares:

~~~xml
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
        <groupId>jakarta.annotation</groupId>
        <artifactId>jakarta.annotation-api</artifactId>
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
~~~

Do not copy old `javax.annotation-api` dependencies for use with `jakarta.annotation.security.RolesAllowed`. The Boot BOM manages compatible versions. If a project uses a different Spring Boot version, check the actual APIs and Java toolchain.

### 7.2. Main Class

Create `src/main/java/com/example/methodroles/MethodRolesApplication.java`:

~~~java
package com.example.methodroles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodRolesApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: Enabling Both Mechanisms

Create `src/main/java/com/example/methodroles/SecurityConfig.java`:

~~~java
package com.example.methodroles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // DEMO PASSWORDS. DO NOT hardcode production credentials.
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password(encoder.encode("admin-demo-password"))
                .roles("ADMIN").build(),
            User.withUsername("auditor")
                .password(encoder.encode("auditor-demo-password"))
                .roles("AUDITOR").build(),
            User.withUsername("member")
                .password(encoder.encode("member-demo-password"))
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/info").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF: the example only uses GET.
        // Protected method paths will still be checked by method security.
        return http.build();
    }
}
~~~

Points that must not be overlooked:

1. `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` is the **activation condition** for both annotation types; do not just put `@EnableMethodSecurity` without parameters.
2. `User.withUsername(...).roles("ADMIN")` creates the `ROLE_ADMIN` authority under the standard role prefix.
3. The HTTP rule requires authenticated for everything else and **does not automatically give admin blanket permissions**; service annotations decide which methods can be invoked.
4. `httpBasic()` is only for easy testing with HTTP clients; production needs HTTPS, strong password policies, MFA/identity per threat model, rate limiting, and no test credentials.
5. `csrf` remains enabled for state-changing methods. Only GET is used in the demo; that is no reason to disable CSRF application-wide.
6. Do not use overly broad public routes like `/api/**.permitAll()`. Public access is limited to GET /api/public/info via a specific route; to constrain the HTTP method more strictly, declare `requestMatchers(HttpMethod.GET, "/api/public/info")` per policy, especially if POST is added to that path later.

**Important:** the code above uses `requestMatchers("/api/public/info")` without restricting the HTTP method, though the controller only defines GET and `anyRequest().authenticated()` covers other URLs. In production, if a strict method allowlist policy is needed, replace it with the `HttpMethod.GET` version to avoid permitting a POST on the same path at the HTTP layer before MVC handles it. Method protection must still be evaluated independently; other HTTP method routes may be added later.

### 7.4. MethodProtectedService: Annotations Placed on the Service

Create `src/main/java/com/example/methodroles/MethodProtectedService.java`:

~~~java
package com.example.methodroles;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.stereotype.Service;

@Service
public class MethodProtectedService {

    @Secured("ROLE_ADMIN")
    public String securedAdmin() {
        return "secured-admin-ok";
    }

    @RolesAllowed("ADMIN")
    public String rolesAllowedAdmin() {
        return "roles-allowed-admin-ok";
    }

    @Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
    public String securedReport() {
        return "secured-report-ok";
    }

    @RolesAllowed({"ADMIN", "AUDITOR"})
    public String rolesAllowedReport() {
        return "roles-allowed-report-ok";
    }

    @DenyAll
    public String locked() {
        return "locked-should-not-run";
    }

    @PermitAll
    public String publicInfo() {
        return "public-ok";
    }
}
~~~

All methods are **public**, the class is non-final, Spring creates the bean, and the controller injects the bean. With both mechanisms enabled, the Spring method-security interceptor checks roles before calling the method body. `locked()` should never execute through the proxy, even for admin.

This lesson intentionally **avoids placing multiple conflicting annotation types on the same method**. Each endpoint expresses a clear contract. When migrating a large codebase, if a method has `@Secured` and `@PreAuthorize` or overlapping class/method annotations, review combined interceptor semantics, ordering, and tests; never assume one annotation "overrides" another across all configurations.

### 7.5. Controller Calling Service Through the Bean Proxy

Create `src/main/java/com/example/methodroles/MethodRolesController.java`:

~~~java
package com.example.methodroles;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MethodRolesController {

    private final MethodProtectedService service;

    public MethodRolesController(MethodProtectedService service) {
        this.service = service;
    }

    @GetMapping("/api/secured/admin")
    public String securedAdmin() {
        return service.securedAdmin();
    }

    @GetMapping("/api/jsr250/admin")
    public String rolesAllowedAdmin() {
        return service.rolesAllowedAdmin();
    }

    @GetMapping("/api/secured/report")
    public String securedReport() {
        return service.securedReport();
    }

    @GetMapping("/api/jsr250/report")
    public String rolesAllowedReport() {
        return service.rolesAllowedReport();
    }

    @GetMapping("/api/jsr250/locked")
    public String locked() {
        return service.locked();
    }

    @GetMapping("/api/public/info")
    public String publicInfo() {
        return service.publicInfo();
    }
}
~~~

Because the controller injects the Spring-managed `MethodProtectedService`, the call `service.securedAdmin()` goes through the method-security interceptor when enabled. If the controller manually runs `new MethodProtectedService()` or calls a method without going through the proxy, annotation conditions may not be enforced.

### 7.6. Running and Observing Expected Behavior

Run the application with the Maven wrapper in a configured Boot 3.x project:

~~~bash
./mvnw spring-boot:run
~~~

A few HTTP requests **for localhost/demo only**:

~~~bash
# curl -u will prompt for the password if omitted after :
curl -i -u admin http://localhost:8080/api/secured/admin
curl -i -u member http://localhost:8080/api/secured/admin
curl -i -u admin http://localhost:8080/api/jsr250/admin
curl -i -u auditor http://localhost:8080/api/jsr250/report
curl -i -u admin http://localhost:8080/api/jsr250/locked
curl -i http://localhost:8080/api/public/info
~~~

Expected results (when entering the corresponding demo password):

| Request | Typical Result | Meaning |
| --- | --- | --- |
| Admin GET /api/secured/admin | 200, `secured-admin-ok` | `@Secured` accepts ROLE_ADMIN |
| Member GET /api/secured/admin | 403 | Authenticated yet lacks ROLE_ADMIN |
| Admin GET /api/jsr250/admin | 200, `roles-allowed-admin-ok` | `@RolesAllowed("ADMIN")` accepts ROLE_ADMIN |
| Auditor GET /api/jsr250/report | 200, `roles-allowed-report-ok` | Role array is OR |
| Admin GET /api/jsr250/locked | 403 | `@DenyAll` blocks |
| Anonymous GET /api/public/info | 200, `public-ok` | HTTP permitAll + JSR-250 PermitAll |
| Anonymous GET /api/secured/admin | 401 (HTTP Basic) | No authentication, blocked by HTTP entry point |

Status codes depend on the application's AuthenticationEntryPoint/AccessDeniedHandler; the example uses default HTTP Basic. What matters is that the **allow/deny decision** is right, not memorizing that every denial always returns the exact same status.

## 8. Spring Boot/MockMvc Testing: Do Not Just Read Annotations

When method security is missing a configuration flag, annotations still appear in source code yet requests may succeed unexpectedly. Therefore tests must verify **actual calls through the bean proxy**, even after the HTTP layer lets authenticated requests through.

Create `src/test/java/com/example/methodroles/MethodRolesIntegrationTest.java`:

~~~java
package com.example.methodroles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodRolesIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void securedAllowsAdminAndDeniesMember() throws Exception {
        mvc.perform(get("/api/secured/admin")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-admin-ok"));

        mvc.perform(get("/api/secured/admin")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void rolesAllowedUsesJakartaAndAdminRole() throws Exception {
        mvc.perform(get("/api/jsr250/admin")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("roles-allowed-admin-ok"));

        mvc.perform(get("/api/jsr250/admin")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anyListedRoleIsEnough() throws Exception {
        mvc.perform(get("/api/secured/report")
                .with(httpBasic("auditor", "auditor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-report-ok"));

        mvc.perform(get("/api/jsr250/report")
                .with(httpBasic("auditor", "auditor-demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("roles-allowed-report-ok"));

        mvc.perform(get("/api/jsr250/report")
                .with(httpBasic("member", "member-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void denyAllRejectsEvenAdmin() throws Exception {
        mvc.perform(get("/api/jsr250/locked")
                .with(httpBasic("admin", "admin-demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicMethodIsAnonymousAccessible() throws Exception {
        mvc.perform(get("/api/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void anonymousCannotReachProtectedMethod() throws Exception {
        mvc.perform(get("/api/secured/admin"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### Why Does This Test Suite Catch Missing Flags?

- If `securedEnabled = true` is forgotten while `jsr250Enabled = true` is on, member GET /api/secured/admin passes HTTP `authenticated()` and calls the service **without any @Secured check**, returning 200; the test expecting 403 fails.
- If `jsr250Enabled = true` is forgotten while `securedEnabled = true` is on, member GET /api/jsr250/admin and admin GET /api/jsr250/locked are not checked by the JSR-250 interceptor; the tests catch it.
- If both are disabled, positive tests can still pass because the method body runs, whereas **negative tests** fail — which is why testing only that admin is allowed is insufficient.
- HTTP Basic tests also verify username/password validation by the provider; however, to test pure method security, `@WithMockUser` can be used in the appropriate scope.

These conclusions apply when no **other authorization mechanism** simultaneously blocks those endpoints; if HTTP rules already required ROLE_ADMIN, a test where member gets 403 at the filter would not prove method security is active. The lesson intentionally sets the general HTTP rule to `authenticated()` so roles are tested at the method level.

### A Direct Bean Test with @WithMockUser

Create `src/test/java/com/example/methodroles/MethodSecurityBeanTest.java`:

~~~java
package com.example.methodroles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodSecurityBeanTest {

    @Autowired MethodProtectedService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminMayCallSecured() {
        assertEquals("secured-admin-ok", service.securedAdmin());
        assertEquals("roles-allowed-admin-ok",
                     service.rolesAllowedAdmin());
    }

    @Test
    @WithMockUser(roles = "USER")
    void memberCannotCallSecuredOrJsr250() {
        assertThrows(AccessDeniedException.class,
                     () -> service.securedAdmin());
        assertThrows(AccessDeniedException.class,
                     () -> service.rolesAllowedAdmin());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void denyAllBlocksAdmin() {
        assertThrows(AccessDeniedException.class,
                     () -> service.locked());
    }
}
~~~

`@WithMockUser(roles = "ADMIN")` creates a test Authentication with authority `ROLE_ADMIN` per Spring Security Test convention. It does **not** prove HTTP Basic/password verification ran. Direct bean tests are very useful for testing the method proxy, though they do not replace MockMvc integration tests when verifying authentication/HTTP mappings.

**This test calls the Spring-injected bean, not `new MethodProtectedService()`.** That matters: an object created with `new` skips the Spring proxy and can produce different results.

### A Negative Test for Self-Invocation

If a service has an `outer()` method calling `this.securedAdmin()`, test that path separately. Never assume testing `service.securedAdmin()` through the proxy proves all internal code paths are protected. The best approach is usually extracting sensitive methods into another bean or adding checks at the appropriate business boundary, then testing the real entry point.

## 9. 401, 403 Decisions and AOP Pitfalls

In the HTTP Basic demo application:

| Scenario | Typical Result | Why |
| --- | --- | --- |
| Anonymous GET /api/secured/admin | 401 | HTTP `authenticated()` rule triggers Basic entry point |
| Member passes HTTP yet method requires ADMIN | 403 | Method-security interceptor denies role |
| Admin with ROLE_ADMIN calls @Secured admin | 200 | Manager grants |
| Admin calls @DenyAll | 403 | JSR-250 interceptor denies |
| Public method @PermitAll yet HTTP URL demands authentication | Possibly 401 for anonymous | HTTP filter blocks before method |
| Method interceptor not enabled | Possibly 200 unexpectedly | Annotation is in source yet never executes |
| Method code throws its own runtime exception | Depends on error handler | Not every exception is an authorization denial |

In many Spring Security versions, when method security denies access it throws an exception in the `AccessDeniedException` family (such as `AuthorizationDeniedException`). `ExceptionTranslationFilter` normally converts exceptions thrown inside the Servlet filter chain to the appropriate `AccessDeniedHandler`/AuthenticationEntryPoint. Calling the method directly in a service test yields the exception rather than an HTTP status.

**Never catch AccessDeniedException and return sensitive data** thinking that is how to handle UI errors. If you want a 403/JSON response, handle it in an appropriate error response layer while keeping the authorization denial intact.

### HTTP Checks and Method Checks Can Both Run

A request may pass the HTTP filter due to a valid role yet be blocked by method security due to a different permission. That is not a contradiction; it is defense in depth. However, if two places hold diverging policies, users can encounter confusing errors. Keep a clear role model, test both HTTP and methods, and never grant `permitAll()` to an entire API just to protect it at the method level.

## 10. Comparing @Secured, @RolesAllowed, and @PreAuthorize

| Criterion | @Secured | @RolesAllowed | @PreAuthorize |
| --- | --- | --- | --- |
| Annotation source | Spring Security | Jakarta JSR-250 | Spring Security |
| Import | `org.springframework.security.access.annotation.Secured` | `jakarta.annotation.security.RolesAllowed` | `org.springframework.security.access.prepost.PreAuthorize` |
| Separate enable flag | `securedEnabled=true` | `jsr250Enabled=true` | `prePostEnabled=true` (typically enabled by default) |
| Common value | `"ROLE_ADMIN"` | `"ADMIN"` | `"hasRole('ADMIN')"` |
| Multiple roles | OR | OR | Can use AND/OR depending on expression |
| Object ownership/tenant | Cannot express directly via expressions | Cannot express directly via expressions | Can call policy beans/compare parameters against trusted data |
| Has @PermitAll/@DenyAll in same family? | No | Yes | Has other pre/post expressions/annotations, not identical |
| Best suited for | Legacy/simple fixed authorities | Standard role-based declarations | Flexible rules, object-level, combined conditions |

Example of a rule requiring both a role and a business condition:

~~~java
// Example fragment in a Spring bean with method security enabled.
@PreAuthorize("hasRole('ADMIN') and @tenantPolicy.canEdit(authentication, #projectId)")
public void editProject(long projectId) {
    // ...
}
~~~

This is **not** a runnable file: it requires a Spring-managed `tenantPolicy` bean, a matching `canEdit(...)` contract, a real service method, reliable parameter-name metadata, `@EnableMethodSecurity` configuration, and policy testing against a DB. Never allow a client-declared `projectId` alone to serve as proof of ownership; tenant/owner data must come from a trusted store.

For more complex conditions, sometimes a custom `AuthorizationManager<MethodInvocation>` or a shared policy service is easier to test/maintain than a long SpEL string.

### When to Keep @Secured or @RolesAllowed?

- Existing codebases with simple role-based checks wanting concise declarations.
- Requirements to use Jakarta JSR-250 for consistency across modules.
- Policies that are strictly "has at least one listed role" without needing access to parameters/records.

Never force all owner/tenant rules into static roles; `ROLE_USER` does not prove a user may edit **any** project.

## 11. Standalone Java 17: Simulating Role Mapping

To see the difference between `@Secured("ROLE_ADMIN")` and `@RolesAllowed("ADMIN")`, the following program simulates checking authorities with the default prefix. It **does not use Spring Security**, does not run annotation interceptors, and does not prove a method is protected by a Spring proxy. Its only purpose is to isolate the **role name → authority** logic and OR semantics.

Save `RoleAnnotationPolicyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Set;

public class RoleAnnotationPolicyDemo {

    record DemoUser(String name, Set<String> authorities) {}

    static boolean secured(DemoUser user, String... authorityNames) {
        if (user == null) {
            return false;
        }
        return Arrays.stream(authorityNames)
                .anyMatch(user.authorities()::contains);
    }

    static boolean rolesAllowed(DemoUser user, String... roleNames) {
        if (user == null) {
            return false;
        }
        return Arrays.stream(roleNames)
                .map(role -> role.startsWith("ROLE_")
                        ? role : "ROLE_" + role)
                .anyMatch(user.authorities()::contains);
    }

    static String label(boolean granted) {
        return granted ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        DemoUser admin = new DemoUser(
                "admin", Set.of("ROLE_ADMIN"));
        DemoUser auditor = new DemoUser(
                "auditor", Set.of("ROLE_AUDITOR"));
        DemoUser member = new DemoUser(
                "member", Set.of("ROLE_USER"));

        System.out.println("admin @Secured: " +
                label(secured(admin, "ROLE_ADMIN")));
        System.out.println("admin @RolesAllowed: " +
                label(rolesAllowed(admin, "ADMIN")));
        System.out.println("auditor any role: " +
                label(rolesAllowed(auditor, "ADMIN", "AUDITOR")));
        System.out.println("member any role: " +
                label(rolesAllowed(member, "ADMIN", "AUDITOR")));
        System.out.println("member @Secured ADMIN: " +
                label(secured(member, "ROLE_ADMIN")));
        System.out.println("unknown principal: " +
                label(rolesAllowed(null, "ADMIN")));
        System.out.println("raw authority mismatch: " +
                label(secured(admin, "ADMIN")));
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac RoleAnnotationPolicyDemo.java
java RoleAnnotationPolicyDemo
~~~

**Exact** stdout:

~~~text
admin @Secured: ALLOW
admin @RolesAllowed: ALLOW
auditor any role: ALLOW
member any role: DENY
member @Secured ADMIN: DENY
unknown principal: DENY
raw authority mismatch: DENY
~~~

Observations:

- The `@Secured` model uses the exact authority name declared; `ADMIN` does not automatically become `ROLE_ADMIN`.
- The `@RolesAllowed` model adds the prefix by convention when needed.
- Having **at least one** role in the list is sufficient.
- A missing principal or one lacking the required authority is denied.
- This is an **explanatory** model, not a full replica of Jsr250AuthorizationManager or SecuredAuthorizationManager; real implementations have dedicated role prefix, role hierarchy, authentication trust, and proxy semantics.

## 12. Configuration and Upgrade Pitfalls

### 12.1. Missing securedEnabled Flag

~~~java
// NOT ENOUGH if the application needs @Secured:
@EnableMethodSecurity
~~~

By default pre/post authorization is enabled in common setups, but secured annotations are not enabled automatically. A `@Secured("ROLE_ADMIN")` method can execute for `member` if no other protection exists. Fix:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Run negative tests: `member` calling the admin service must be denied.

### 12.2. Missing jsr250Enabled Flag

~~~java
// NOT ENOUGH if the application needs @RolesAllowed/@DenyAll/@PermitAll:
@EnableMethodSecurity(securedEnabled = true)
~~~

Fix:

~~~java
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
~~~

If a `@DenyAll` method can still be called by admin, that is a strong signal that the JSR-250 interceptor is inactive or the call bypassed the proxy.

### 12.3. Using the Wrong Import

In Boot 3, use `jakarta.annotation.security.RolesAllowed`; do not mechanically copy `javax.annotation.security.RolesAllowed` from older articles. Even if the import still compiles due to an old Java EE dependency, Spring Security's modern Jakarta JSR-250 setup will not recognize that annotation.

### 12.4. Mistyping the ROLE_ Prefix

`@Secured("ADMIN")` with principal `ROLE_ADMIN` can deny. `@RolesAllowed("ADMIN")` with principal `ROLE_ADMIN` typically allows under the default prefix. Conversely, if the identity system issues authority `ADMIN` without a prefix, configure a consistent role mapping rather than patching individual annotations arbitrarily.

### 12.5. Using @Secured as SpEL

~~~java
// SEMANTICALLY WRONG: @Secured does not parse hasRole(...) expressions.
@Secured("hasRole('ADMIN')")
public void operation() {}
~~~

If you need SpEL, use `@PreAuthorize("hasRole('ADMIN')")` with pre/post method security enabled. This is an error-illustration fragment, not recommended logic.

### 12.6. Assuming Role Lists Mean AND

`@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})` and `@RolesAllowed({"ADMIN", "AUDITOR"})` express **OR**. To require multiple conditions simultaneously, use an explicit policy; unit-test that a member holding only one role is not granted access if business rules truly require two roles.

### 12.7. Ignoring Self-Invocation

An unannotated method calling `this.securedMethod()` can bypass the interceptor. Separate bean responsibilities, inject proxies properly, or enforce at business boundaries. Test the real call path rather than only calling securedMethod() directly through the proxy.

### 12.8. Placing Annotations on Private/Final Methods

Proxy-based method security has limitations with private/final methods and non-proxied methods. Use public non-final methods for primary enforcement points, place them on Spring-managed beans, and verify actual proxy behavior when interfaces/AspectJ/interface annotations are involved.

### 12.9. Instantiating Services with new

~~~java
// DANGEROUS if expecting annotations to run automatically:
MethodProtectedService service = new MethodProtectedService();
service.securedAdmin();
~~~

A manually constructed object is not a Spring proxy. In tests, inject `@Autowired MethodProtectedService`. In the application, use constructor injection instead of `new` to avoid bypassing the container.

### 12.10. HTTP Layer Blocks First, Causing "False Green" Tests

If the HTTP rule already enforces `hasRole("ADMIN")` on `/api/secured/admin`, `member` gets 403 at the filter even when `@Secured` is off. Test the service bean directly with `@WithMockUser` or set the HTTP gate to `authenticated()` like the demo, so you know method security truly made the decision.

### 12.11. Unintentionally Mixing Multiple Annotations

Putting `@Secured`, `@PreAuthorize`, or `@RolesAllowed` on the same method simultaneously can activate multiple interceptors/policies; the outcome is not necessarily "last annotation wins". Define a clear contract and test against a role matrix. Best to avoid conflicting annotations on one method.

### 12.12. Forgetting @Async and SecurityContext

Request SecurityContext is typically thread-bound. When a protected method executes on an executor thread, it does not automatically share the same Authentication. Spring Security provides proper context propagation mechanisms, but they must be used intentionally while avoiding leaking user context into long-lived background jobs beyond policy. Without a trusted identity, never auto-grant.

### 12.13. Relying on Role USER for Object-Level Access

A role is only a coarse attribute; it does not prove an order/project belongs to the user. If `getInvoice(long id)` only has `@RolesAllowed("USER")`, users can attempt to access other users' invoices. Object-level checks from trusted server data, such as tenant/owner, are required at the service or policy layer.

### 12.14. Changing Authority Mapping Without Updating Tests

An identity provider migration may change authorities from `ROLE_ADMIN` to `admin` or scopes. Old annotations will deny or behave differently. In tests, assert actual authorities and `@Secured`/`@RolesAllowed` behavior rather than only checking Authentication.isAuthenticated().

## 13. Advanced: Inheritance, Proxy Order, and Transactions

### Class-Level Security in Hierarchies

Annotations can be declared on classes or methods depending on Target and library; Spring Security resolves security metadata across methods/classes when the proxy runs. With interface inheritance, method overrides, bridge methods, overloaded methods, and multi-interface beans, annotation resolution can become complex. Place rules on **concrete service methods** or a tested convention, and write tests for every inheritance case actually used; never assume an annotation on an arbitrary interface will be discovered under every setup.

### Self-Invocation and Transactional Proxies

Both `@Transactional` and method security can use AOP interception. Calling via `this` typically bypasses proxy-related behavior for both. If a transactional method calls a restricted method on the same instance, never assume the restricted method's interceptor runs automatically. Extract a separate bean or adjust the architecture.

### AOP Advisor Ordering

Method security and transaction advice have ordering; depending on configuration, authorization may happen before or inside the transaction. For policies reading data, account for race conditions and database consistency. Do not try to micro-optimize advisor ordering before having clear business policies and tests.

### Exceptions and API Responses

In API applications, a denied method typically triggers AccessDeniedException, which Servlet exception translation may convert into 403/JSON. If the service is invoked by a message consumer, the exception may trigger message retry or DLQ routing via its own mechanism; there is no HTTP status in that context. Decide fail-closed handling for each entry point without swallowing exceptions and continuing business logic anyway.

## 14. Production-Grade Testing Guide

### 14.1. Two-Annotation Test Matrix

| Identity | @Secured ROLE_ADMIN | @RolesAllowed ADMIN | Multi-role ADMIN/AUDITOR | @DenyAll |
| --- | --- | --- | --- | --- |
| Admin | Allow | Allow | Allow | Deny |
| Auditor | Deny | Deny | Allow | Deny |
| Member | Deny | Deny | Deny | Deny |
| Anonymous | Deny | Deny | Deny | Deny |

Tests should include at least one **positive** and one **negative** case for **each annotation type**. Besides HTTP tests, test service beans directly to catch missing flags that an HTTP gate might accidentally mask.

### 14.2. Controlled Tests for Missing Configuration

In a test/laboratory environment, you can spin up an isolated application context with only default `@EnableMethodSecurity`, inject a bean with `@Secured`/`@RolesAllowed`, and observe the difference. This is an **experiment to demonstrate the mechanism**, not a deployment config. Never intentionally drop flags in production for comparison.

### 14.3. Testing Directly from Controllers and Other Service Callers

A service may be invoked from controllers, schedulers, or message handlers. Those callers have different authentication contexts. For non-HTTP callers, establish a legitimate principal/service identity rather than injecting an arbitrary admin Authentication to make tests pass. If business logic needs the original user's identity, propagate it through trusted layers with controlled lifecycles.

### 14.4. Testing Role Changes and Permission Revocation

Authorities are typically loaded at authentication time. When a user's role is revoked in the DB/IdP, active Authentication/sessions may still hold stale authorities until refreshed/reauthenticated per policy. Method annotations do not perform real-time role revocation on their own. Design authority lifecycles, token/session expiry, or dynamic policy queries when rapid revocation is required.

### 14.5. Testing API Versions and Non-HTTP Paths

If a service method is called from multiple controllers or API interfaces, method security increases coverage—but only when those call paths go through the proxy. Test new routes/versions and direct calls from another Spring-managed bean to prevent bypasses. Never let controllers instantiate services manually or call internal methods around rules.

### 14.6. Safe Logging/Auditing

You can log permission denial events (method name, request ID, policy key, result) with minimal information. Never log passwords, bearer tokens, session IDs, Authentication objects containing credentials, sensitive method arguments, or user data the caller was unauthorized to read. An AccessDeniedException does not prove malicious intent; user-facing responses should remain neutral.

## 15. Questions and Practice Exercises

**Exercise 1.** A project uses `@EnableMethodSecurity` with no arguments and has a `@Secured("ROLE_ADMIN")` method. Tests show `member` can still call the method. Where is the mistake?

**Answer:** `securedEnabled` is off by default in standard Spring Security 6 configuration. You need `@EnableMethodSecurity(securedEnabled=true)`, ensure the bean/proxy is used, and write direct negative tests.

**Exercise 2.** A service uses `@RolesAllowed("ADMIN")`, yet only `securedEnabled=true` is enabled. Is that enough?

**Answer:** No. `@RolesAllowed` belongs to JSR-250 and requires `jsr250Enabled=true`. The two flags are independent.

**Exercise 3.** What authority does `User.withUsername("admin").roles("ADMIN")` create by default in Spring Security?

**Answer:** `ROLE_ADMIN`. Thus `@Secured("ROLE_ADMIN")` and `@RolesAllowed("ADMIN")` can both grant when their mechanisms are enabled with the default prefix.

**Exercise 4.** Why might `@Secured("ADMIN")` deny a principal holding `ROLE_ADMIN`?

**Answer:** `@Secured` takes a literal authority name; `ADMIN` differs from `ROLE_ADMIN`. Role/authority mappings must be aligned.

**Exercise 5.** With `@RolesAllowed({"ADMIN","AUDITOR"})`, is a user who only has ROLE_AUDITOR permitted?

**Answer:** Yes, because the role array here has OR semantics (any one of the listed roles), not AND.

**Exercise 6.** `@DenyAll` is placed on a method, yet admin can still call it. What are the first two things to check?

**Answer:** Whether `jsr250Enabled=true` is enabled, and whether the call goes through a Spring proxy. Also check the `jakarta.annotation.security.DenyAll` import, public method visibility, and Spring bean management.

**Exercise 7.** `@PermitAll` is placed on a service method. An anonymous GET /private request still receives 401; why?

**Answer:** The HTTP SecurityFilterChain may require `authenticated()` before the controller invokes the method. `@PermitAll` only permits at the JSR-250 method-security layer, not bypassing HTTP authorization.

**Exercise 8.** A controller runs `new MethodProtectedService()` and calls `securedAdmin()`. Is this safe?

**Answer:** It cannot be considered safe because the object is not a Spring AOP proxy; the annotation may not be checked. Inject the bean from ApplicationContext and test it.

**Exercise 9.** A bean has `outer()` calling `this.securedAdmin()`, while `outer()` is unannotated. Direct test `bean.securedAdmin()` is denied, yet `bean.outer()` succeeds. Why?

**Answer:** Self-invocation within the same instance typically bypasses proxy interception. Extract the protected method into another bean or enforce at the appropriate boundary.

**Exercise 10.** Is `@Secured("hasRole('ADMIN')")` equivalent to `@PreAuthorize("hasRole('ADMIN')")`?

**Answer:** No. `@Secured` does not parse SpEL `hasRole(...)`, whereas `@PreAuthorize` evaluates authorization expressions. Pick the right API and enable it accordingly.

**Exercise 11.** A test only asserts that admin GET /api/secured/admin returns 200. Does that prove `securedEnabled` is on?

**Answer:** No. If the flag is off, the method can still execute and return 200. You need a test where `member` is denied when HTTP only requires authenticated, or a direct bean test with `@WithMockUser` to prove the interceptor ran.

**Exercise 12.** A service has `@RolesAllowed("USER")` and `getInvoice(id)`. Alice has ROLE_USER yet can read Bob's invoice. What went wrong?

**Answer:** Role USER does not verify object ownership. You need an owner/tenant policy backed by server data (in the service/AuthorizationManager/PreAuthorize as appropriate), plus negative-object tests.

**Exercise 13.** After a user's ROLE_ADMIN is revoked in the DB, an existing login session can still call `@Secured` admin methods. Is the annotation broken?

**Answer:** Not necessarily. Authentication may hold authorities loaded at login; you need appropriate refresh/revocation/session invalidation or dynamic policy checks. Annotations do not automatically re-query the DB on every call in every architecture.

**Exercise 14.** Why might a method in a scheduled job annotated with `@RolesAllowed("ADMIN")` be denied even though HTTP admin tests pass?

**Answer:** Background threads may lack the HTTP user's Authentication. Define a trusted service identity/context propagation model rather than turning the job into an arbitrary admin to dodge policies.

## 16. Implementation and Operations Checklist

- [ ] Use Spring Boot 3/Spring Security 6 with `jakarta.annotation.security.*` imports, avoiding legacy `javax.annotation.*` namespaces from older guides.
- [ ] If using `@Secured`, enable `@EnableMethodSecurity(securedEnabled=true)`.
- [ ] If using `@RolesAllowed`/`@PermitAll`/`@DenyAll`, enable `@EnableMethodSecurity(jsr250Enabled=true)`.
- [ ] If using both, enable **both flags** and write negative tests for each mechanism.
- [ ] Align `ROLE_` prefix, `roles(...)`, `authorities(...)`, and identity provider mappings.
- [ ] Treat multiple values in these annotations as **OR**, not AND.
- [ ] Never use `@Secured` as SpEL; use `@PreAuthorize`/appropriate policy services for complex rules.
- [ ] Place enforcement points on public methods of Spring-managed beans, called through proxies.
- [ ] Never rely on private/final/self-invoked methods or objects created with `new` for access protection.
- [ ] Extract sensitive methods into appropriate beans to avoid self-invocation bypasses.
- [ ] Test both Spring-injected service beans directly and HTTP MockMvc, covering allow and deny cases.
- [ ] Do not let HTTP hasRole rules mask method-security errors in tests meant to prove annotations work.
- [ ] Distinguish HTTP authentication/authorization from method security and avoid blanket permitAll.
- [ ] Never trust user-supplied role/tenant headers; authorities must come from a trusted authentication provider.
- [ ] When policies depend on resources, enforce owner/tenant and consistency at service/data boundaries.
- [ ] For @Async/schedulers/queues, design identity/context propagation and test every entry point.
- [ ] Review on Spring Security 6 minor upgrades, AOP proxy modes, role hierarchies, and authority revocation.
- [ ] Keep auditing minimal; never log credentials or sensitive method arguments.

**Conclusion:** `@Secured` and `@RolesAllowed` both help protect **method invocations** using roles/authorities, yet belong to **two independently enabled mechanisms**. In Spring Security 6, use `@EnableMethodSecurity(securedEnabled=true, jsr250Enabled=true)` if using both, keep the `ROLE_` prefix consistent, test **negative cases** to prove annotations are actually running, and never overlook proxy/self-invocation limits or object-level rules beyond simple role checks.