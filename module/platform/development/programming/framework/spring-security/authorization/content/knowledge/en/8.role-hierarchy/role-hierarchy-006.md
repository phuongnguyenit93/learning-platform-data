# Testing Role Hierarchy Separately at HTTP and Method Layers

In Spring Security, defining **`ROLE_ADMIN > ROLE_STAFF > ROLE_USER`** means that when an authorization mechanism **is configured to use `RoleHierarchy`**, a user holding `ROLE_ADMIN` can satisfy requirements targeting `ROLE_STAFF` and `ROLE_USER`. However, an application can enforce authorization at **two independent boundaries**: `authorizeHttpRequests` in the HTTP filter chain and `@PreAuthorize` at the method/service layer. Therefore, you cannot test a single API call succeeding and conclude that role hierarchy is active **everywhere**.

Typical scenario: `GET /api/reports/summary` requires `STAFF` in `SecurityFilterChain`; the backing service also has `@PreAuthorize("hasRole('STAFF')")`. At login, the principal carries only `ROLE_ADMIN`. If the HTTP manager understands **ADMIN ⇒ STAFF** while the method expression handler does not use the corresponding hierarchy, the request passes HTTP and hits **403 at the service**. Conversely, if method security has the hierarchy while the HTTP manager does not, the request is blocked by the filter and **never reaches the service**.

This lesson focuses on **configuring, verifying, and diagnosing separate role hierarchy enforcement** in **Spring Security 6.5 / Spring Boot 3.x (Servlet)**, with notes on Spring Security 7.x. It includes Spring Java configurations, `MockMvc`/service test examples, and a **standalone Java 17 program** illustrating all four on/off combinations across the two layers.

## 1. Role hierarchy is implication, not copying roles into Authentication

Suppose you declare:

~~~text
ROLE_ADMIN > ROLE_STAFF
ROLE_STAFF > ROLE_USER
~~~

The `>` symbol means **implies**:

~~~text
ROLE_ADMIN
    |
    v
ROLE_STAFF
    |
    v
ROLE_USER
~~~

For a user granted solely `ROLE_ADMIN`, a hierarchy-aware manager treats that user as satisfying `ROLE_STAFF` and `ROLE_USER` via **transitive closure**. Conversely, `ROLE_USER` does not infer up to `ROLE_STAFF` or `ROLE_ADMIN`. Relationships absent from the graph are never inferred automatically.

In Spring Security, roles are conventionally represented as `GrantedAuthority` strings prefixed with **`ROLE_`**. Thus:

- `hasRole("STAFF")` checks for `ROLE_STAFF` under default conventions.
- `hasAuthority("ROLE_STAFF")` matches the exact string **`ROLE_STAFF`**.
- `hasAuthority("ORDER_READ")` checks business authority `ORDER_READ` without prepending `ROLE_`.
- `@WithMockUser(roles = "ADMIN")` in Spring Security Test normally creates **`ROLE_ADMIN`**, unlike `@WithMockUser(authorities = "ADMIN")`.

With a hierarchy, authority checks in components **wired with `RoleHierarchy`** evaluate derived authorities as well. `RoleHierarchy` **does not mutate** `Authentication.getAuthorities()`; code manually calling `authentication.getAuthorities().contains(...)` or checking role names via `Set.contains` **does not inherit** the relationship unless you invoke the reachable authorities lookup.

For example, when a principal only holds `ROLE_ADMIN`, `@PreAuthorize("hasRole('STAFF')")` can evaluate to **true** if the method expression handler is configured with the hierarchy, while logging `Authentication.getAuthorities()` still prints only `ROLE_ADMIN`. There is no contradiction: one is the **granted input**, and the other is an **implication-aware decision**.

## 2. Two independent checkpoints: HTTP and method/service

The typical path of an HTTP request invoking a service looks like this:

~~~text
HTTP GET /api/reports/summary
         |
         v
SecurityFilterChain
    AuthorizationFilter
    authorizeHttpRequests
    requestMatchers("/api/reports/**").hasRole("STAFF")
         |
         +-- DENY -> 401/403 handling, controller never runs
         |
         +-- ALLOW
              |
              v
          ReportController
              |
              v
          Spring AOP method interceptor
          @PreAuthorize("hasRole('STAFF')")
              |
              +-- DENY -> AccessDeniedException, service body never runs
              |
              +-- ALLOW
                   |
                   v
                ReportService.summary()
                   |
                   v
                HTTP response
~~~

Both checks have **different secured objects and configuration mechanisms**:

| Characteristic | HTTP authorization | Method authorization |
| --- | --- | --- |
| Main hook | `SecurityFilterChain` / `authorizeHttpRequests`. | `@EnableMethodSecurity` + AOP interceptor. |
| Protected target | HTTP request / request authorization context. | `MethodInvocation`, arguments, or return value. |
| Typical rule | `.requestMatchers("/api/reports/**").hasRole("STAFF")`. | `@PreAuthorize("hasRole('STAFF')")`. |
| How hierarchy is wired | Managers used in request authorization must apply `RoleHierarchy`; in standard 6.5 DSL, the hierarchy bean is integrated per official docs. | `DefaultMethodSecurityExpressionHandler` must be configured with `RoleHierarchy` for `@PreAuthorize`/`@PostAuthorize` expressions. |
| Enabled by default? | Spring Boot + Security builds a default filter chain unless replaced by a custom bean; custom rules must be declared. | **No**: Spring Boot Starter Security does not enable method security automatically. |
| Testable outside HTTP? | No; requires an HTTP request entering the chain. | Yes: call the service through its Spring proxy from jobs, consumers, other controllers, or tests. |
| Where failure appears? | Before the controller. | After passing HTTP (if initiated via HTTP), or directly at the service when invoked elsewhere. |

If a request enters over HTTP and calls a proxy-protected method, **both conditions must allow** for business logic to execute. This **does not mean configuring one layer automatically covers the other**: enabling hierarchy on one layer proves nothing about the other layer.

Specifically for `@PreAuthorize`, `hasRole` inside SpEL is evaluated by **method security's** expression handler and is never replaced by HTTP matchers. When invoking the service from a message consumer without HTTP, only **method/domain** rules actually run.

## 3. Outcome matrix when hierarchy is enabled at one or both layers

Consider one user holding `ROLE_ADMIN`, a `ROLE_STAFF` requirement, and `ROLE_ADMIN > ROLE_STAFF`:

| HTTP understands hierarchy? | Method understands hierarchy? | HTTP request passes filter? | Proxied service call permitted? | Combined request outcome |
| --- | --- | --- | --- | --- |
| Yes | Yes | **ALLOW** | **ALLOW** | Reaches service (unless another policy denies). |
| Yes | No | **ALLOW** | **DENY** | Likely 403 at method layer. |
| No | Yes | **DENY** | **ALLOW** if service called directly from a valid entry point | HTTP request blocked before controller. |
| No | No | **DENY** | **DENY** | Request blocked. |

Meanwhile, a user granted **`ROLE_STAFF` directly** passes both `hasRole("STAFF")` checks even if hierarchy is completely inactive. Therefore, **testing with a STAFF user never proves inheritance works**. You must test a user holding only **ROLE_ADMIN** accessing **STAFF**, plus a **ROLE_USER** being denied STAFF.

To test transitivity, verify `ROLE_ADMIN > ROLE_STAFF > ROLE_USER`: a user with only ADMIN must satisfy USER on each hierarchy-enabled layer. To test the reverse direction, invoke an ADMIN endpoint as USER and assert **DENY**.

A 200 response alone is also insufficient: the HTTP rule might be `permitAll`, the controller might not call a `@PreAuthorize`-protected service, or the Spring AOP proxy might be bypassed. Tests must hit **both checkpoints**.

## 4. Defining one shared, reusable RoleHierarchy

In Spring Security 6.5, declare a `RoleHierarchy` bean using `RoleHierarchyImpl.fromHierarchy(...)`. Example creating an explicit graph:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class RoleHierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_STAFF
                ROLE_STAFF > ROLE_USER
                """);
    }
}
~~~

This is **Spring configuration**, requiring Spring Security dependencies and Java 17+. `RoleHierarchyImpl` computes reachable authorities through direct and transitive edges. Defining **one unified bean** reduces the risk that HTTP obeys one hierarchy while services obey another.

In Spring Security versions offering the builder, you can also declare it as:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
            .role("ADMIN").implies("STAFF")
            .role("STAFF").implies("USER")
            .build();
}
~~~

These two snippets are **alternatives** for declaring the same `RoleHierarchy` bean; do not register two default beans with colliding names. The `withDefaultRolePrefix` builder intentionally uses `ROLE_`. If an organization uses a custom role prefix, align `GrantedAuthorityDefaults`, raw authorities, the hierarchy builder, and both HTTP and method tests. Never change the prefix in only one layer expecting uniform behavior.

**Verify the graph itself:** invoke `RoleHierarchy#getReachableGrantedAuthorities` with an input containing `new SimpleGrantedAuthority("ROLE_ADMIN")`. Expected results include `ROLE_ADMIN`, `ROLE_STAFF`, and `ROLE_USER`. This is a **unit test of the hierarchy**, not proof that web filters or method expression handlers use that bean.

## 5. Wiring hierarchy into HTTP authorization

In Spring Security **6.5**, Authorization Architecture documentation supports a `RoleHierarchy` bean for `HttpSecurity#authorizeHttpRequests`; with the standard DSL, you can declare:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpRoleHierarchyConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasRole("STAFF")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/profile/**")
                    .hasRole("USER")
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a **Spring Boot / Spring Security 6.5 configuration class** and belongs in the same application context as the `RoleHierarchy` bean, authentication source, and real controllers. `httpBasic` illustrates unauthenticated rejection; JWT applications can substitute `oauth2ResourceServer` with proper authority mapping.

For a user holding only `ROLE_ADMIN`:

- `GET /api/reports/summary` requires `STAFF`; if the HTTP manager uses `RoleHierarchy`, it **proceeds** to the controller.
- `GET /api/profile/me` requires `USER`; ADMIN ⇒ STAFF ⇒ USER also lets it proceed.
- `GET /api/admin/users` requires `ADMIN`; direct authority already suffices.
- `POST /api/reports/summary` is **not implicitly allowed** by the GET rule; with no matching rule it falls into `denyAll`.
- A user with only `ROLE_USER` does not gain `ROLE_STAFF` or `ROLE_ADMIN`.

With `authorizeHttpRequests`, **the first matching matcher wins**. Putting a broad `requestMatchers("/api/**").authenticated()` before the reports rule prevents HTTP from enforcing STAFF on reports, even when role hierarchy is properly configured. That can produce misleading inheritance test results. Matcher ordering and HTTP methods must be checked separately.

### With manually constructed managers, do not assume the bean is used

Beyond `.hasRole("STAFF")` in the DSL, an application may instantiate `AuthorityAuthorizationManager` manually:

~~~java
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

AuthorityAuthorizationManager<RequestAuthorizationContext> staffRequired =
        AuthorityAuthorizationManager.hasRole("STAFF");

staffRequired.setRoleHierarchy(roleHierarchy);

// Put into authorizeHttpRequests DSL:
// .requestMatchers("/api/reports/**").access(staffRequired)
~~~

This snippet is **not a complete class** and assumes `roleHierarchy` was injected. Key takeaway: `AuthorityAuthorizationManager` exposes `setRoleHierarchy(...)`; whenever instantiating a manager manually, verify whether a real hierarchy was passed in. Per the 6.5 API, `AuthorityAuthorizationManager` defaults to `NullRoleHierarchy` if unconfigured, so a manually constructed manager compares only direct authorities even if a `RoleHierarchy` bean sits in the application context.

Other custom components (custom `AuthorizationManager`, permission evaluators, or lambdas iterating `authentication.getAuthorities()`) also **do not inherit transitivity** unless their implementation applies the hierarchy. Testing a standard-DSL URL does not guarantee a custom manager on another URL behaves identically.

### Multiple SecurityFilterChain beans must also be tested separately

If the application defines separate chain beans for `/api/**` and `/admin/**`, `FilterChainProxy` picks the **first matching chain** by `@Order` and runs only that chain's rules. If one chain uses a hierarchy-aware manager while another uses a raw-authority manager without hierarchy, the two URL regions behave differently. Identify **which chain is matched** and which manager holds the role hierarchy, rather than just checking for a global `RoleHierarchy` bean.

## 6. Wiring hierarchy into method security — the commonly missed step

Spring Boot Starter Security **does not enable method security automatically**. Enable it in configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityEnabler {
}
~~~

For `@PreAuthorize` and `@PostAuthorize`, Spring Security uses `MethodSecurityExpressionHandler`. Spring Security 6.5 documentation instructs publishing a **`static` expression handler bean** wired with the same `RoleHierarchy`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class HierarchicalMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
~~~

**Why `static`?** Spring Security needs to see the handler before initializing method-security configuration classes. Official docs recommend this to prevent the bean from being published too late. Never instantiate a handler with `new` inside a service expecting `@PreAuthorize` to switch to it automatically.

Service example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('STAFF')")
    public String summary() {
        return "summary";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String audit() {
        return "audit";
    }
}
~~~

When another Spring bean invokes `reportService.summary()` **through the proxy**, a user with only `ROLE_ADMIN` is permitted if the method handler has ADMIN ⇒ STAFF; a user with only `ROLE_USER` is denied. Calling `reportService.audit()` allows only ADMIN or a role explicitly declared to imply ADMIN.

**AOP proxy limits:** calling `this.summary()` from another method in the same instance, or instantiating `new ReportService()` outside Spring, can **bypass the method-security interceptor**. Then a “method test PASS” can be a false positive unless proxy invocation is verified. Use container-managed beans and test that missing permissions throw `AccessDeniedException`.

`@PreAuthorize` is not the sole answer for every business rule. Role hierarchy only describes authority relationships; access to the **specific report, branch, tenant, owner, and resource state** still requires domain policies.

## 7. Combining both layers in a real endpoint

Controller injecting the service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/reports/summary")
    public String summary() {
        return reportService.summary();
    }
}
~~~

Assume the application registers **all** of these components together:

1. `RoleHierarchy` bean defining ADMIN ⇒ STAFF ⇒ USER.
2. `SecurityFilterChain` from section 5 requiring `hasRole("STAFF")` on `GET /api/reports/**`.
3. `@EnableMethodSecurity` and `MethodSecurityExpressionHandler` from section 6.
4. Spring-managed `ReportService` injected into the controller.
5. Authentication producing an `Authentication` containing strictly `ROLE_ADMIN` for admin.

When ADMIN calls the endpoint:

~~~text
REQUEST GET /api/reports/summary
    |
    +-- HTTP: hasRole(STAFF) with hierarchy
    |           ROLE_ADMIN => ROLE_STAFF => ALLOW
    |
    +-- Controller calls service bean through proxy
                |
                +-- @PreAuthorize hasRole(STAFF) with method hierarchy
                           ROLE_ADMIN => ROLE_STAFF => ALLOW
                |
                +-- ReportService.summary() returns "summary"
~~~

If you remove the **method handler** while keeping `@EnableMethodSecurity`, depending on config/version the request can pass HTTP and get denied at `@PreAuthorize`. If you remove **`@EnableMethodSecurity`**, the method annotation may **not run at all**; a 200 response then proves nothing about method hierarchy. Switching HTTP to `permitAll` likewise renders a 200 useless as proof of HTTP hierarchy.

In Spring Security 6.5 with the setup above, role hierarchy works across both HTTP and pre/post method expressions. Still, generalizing “one bean automatically covers the whole project” **is false** across APIs, versions, custom managers, and interceptors. Actually test each enforcement point.

## 8. Testing RoleHierarchy alone before testing the layers

Start with the graph, testing an input containing only `ROLE_ADMIN`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.beans.factory.annotation.Autowired;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RoleHierarchyGraphTest {

    @Autowired
    RoleHierarchy hierarchy;

    @Test
    void adminReachesStaffAndUser() {
        Set<String> actual = hierarchy.getReachableGrantedAuthorities(
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")))
            .stream().map(a -> a.getAuthority())
            .collect(Collectors.toSet());

        assertEquals(Set.of("ROLE_ADMIN", "ROLE_STAFF", "ROLE_USER"), actual);
    }
}
~~~

This is a **Spring/JUnit test snippet** and must live in a test class managed by a Spring Test context (e.g., adding `@SpringBootTest`) so `@Autowired` is injected. Do not copy the class verbatim expecting `hierarchy` to inject in plain JUnit. This test verifies graph mapping **but does not verify whether HTTP or method managers actually use it**.

With multiple relationships, test both positive and negative directions, for example:

| Directly granted principal | Required role/authority | Reachable? |
| --- | --- | --- |
| `ROLE_ADMIN` | `ROLE_ADMIN` | Yes: direct. |
| `ROLE_ADMIN` | `ROLE_STAFF` | Yes: one hop. |
| `ROLE_ADMIN` | `ROLE_USER` | Yes: transitive. |
| `ROLE_STAFF` | `ROLE_USER` | Yes: one hop. |
| `ROLE_STAFF` | `ROLE_ADMIN` | **No**: does not infer backwards. |
| `ROLE_USER` | `ROLE_STAFF` | **No**. |
| Unauthenticated | `ROLE_STAFF` | Never granted implicitly. |

Never use only ADMIN across all tests: include STAFF, USER, and anonymous cases to verify the hierarchy is not over-exposed, especially when adding new roles.

## 9. Testing HTTP hierarchy with MockMvc: proving the filter accepts inherited roles

With the controller/service from sections 6–7 and `SecurityFilterChain` from section 5, use `MockMvc` to verify **a user with only ROLE_ADMIN** can reach the STAFF endpoint. Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpHierarchyIT {
    @Autowired MockMvc mvc;

    @Test
    void adminCanEnterStaffReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("summary"));
    }

    @Test
    void userCannotEnterStaffReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(user("user").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

This requires `spring-boot-starter-test` and `spring-security-test`, along with the controller/service and proper configuration. It is **test code inside a Spring Boot project**, not runnable with plain JDK. If `spring-security-test` is not integrated with the MVC test context, simulated principals may not flow through the filter properly; use `@SpringBootTest` and `@AutoConfigureMockMvc` or configure filters on your test slice.

**Important proof-scope note:** this test hits a real endpoint, so 200 proves the **combined** allowance of all layers. To isolate **HTTP hierarchy** alone:

- Use a test endpoint having only an HTTP rule and **no method annotation**, or
- Unit test the `AuthorizationManager` used by the HTTP rule directly, or
- Use instrumentation/spies to confirm whether the controller ran in each case rather than guessing from an ambiguous 403.

For instance, a fixture endpoint with only `/api/reports/**` HTTP rules and no protected service call: if admin with only ADMIN succeeds while USER gets 403 **before the controller**, that proves the HTTP manager sees ADMIN ⇒ STAFF.

If `ROLE_STAFF` returns 200, that only proves direct matching, **not** that `RoleHierarchy` works. When using `with(user(...).roles("ADMIN"))`, ensure the test fixture does not accidentally add STAFF too so the initial principal carries strictly `ROLE_ADMIN`.

## 10. Testing method hierarchy directly: bypassing HTTP

To test `@PreAuthorize` independently of the filter chain, inject the service **via its Spring proxy** and invoke it inside a test security context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodHierarchyIT {

    @Autowired ReportService reports;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminInheritsStaffAtMethod() {
        assertEquals("summary", reports.summary());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallStaffMethod() {
        assertThrows(AccessDeniedException.class, reports::summary);
    }

    @Test
    @WithMockUser(roles = "STAFF")
    void staffCannotCallAdminMethod() {
        assertThrows(AccessDeniedException.class, reports::audit);
    }
}
~~~

This suite sends **no HTTP requests**. If the first test passes and both negative tests deny properly, you have evidence that method security is active and applying the role hierarchy as intended. If `@EnableMethodSecurity` is missing, the `assertThrows` cases immediately expose it (the methods run instead of throwing). Still, if a service is guarded by another custom interceptor or `@PreAuthorize` is overridden, inspect the actual bean and configuration.

A subtle mistake is calling `reports.summary()` on a manually instantiated `new` service in a unit test instead of a Spring bean: annotations do not run, so **that test cannot confirm method security**. With `@SpringBootTest`, inject the Spring-managed proxy. `@WithMockUser` populates the context on the test thread, but does not automatically propagate it across executors if the service also launches `@Async` tasks.

### Testing method enforcement across multiple entry points

Method security matters because services can be invoked from HTTP controllers, message listeners, batch jobs, or other services. When an entry point bypasses HTTP, `authorizeHttpRequests` rules never run; `@PreAuthorize` remains the gatekeeper if calls go through the proxy with an `Authentication`. If a background job has no user context, design explicit service identity/authorization rather than abusing role hierarchy to grant ADMIN by default.

## 11. Why can a single RoleHierarchy bean still diverge in enforcement?

There are at least seven independent causes:

1. **Method security not enabled:** `@EnableMethodSecurity` was forgotten. `@PreAuthorize` never runs even when the HTTP manager uses the hierarchy properly.
2. **Missing custom MethodSecurityExpressionHandler:** HTTP may use the `RoleHierarchy` bean while method SpEL does not automatically pick it up in your configuration/version. Spring Security 6.5 docs instruct registering a `static MethodSecurityExpressionHandler` with `setRoleHierarchy`.
3. **Custom HTTP AuthorizationManager:** a custom manager or manually constructed `AuthorityAuthorizationManager` forgot `setRoleHierarchy`, so `hasRole("STAFF")` there checks only raw `ROLE_STAFF`.
4. **Wrong matcher or wrong SecurityFilterChain:** the request hit an earlier broad `authenticated()`/`permitAll()` rule, or a different chain matched. A 200 test may not even touch the `STAFF` rule.
5. **Method call bypassed Spring proxy:** internal `this.method()` self-invocation, manual `new`, or reflection/framework callbacks skipping the interceptor.
6. **Authorities have mismatched prefix:** principal holds `ADMIN` while `hasRole("ADMIN")` expects `ROLE_ADMIN`, or a JWT scope creates `SCOPE_admin` rather than `ROLE_ADMIN`.
7. **Other method annotations use separate managers:** `@Secured` and `@RolesAllowed` use different interceptors/managers than `@PreAuthorize`. Enabling them without verifying hierarchy wiring on those managers causes divergence from SpEL.

In setups with multiple application contexts or child contexts, `RoleHierarchy` and expression handler beans must live in **the exact context where security configuration initializes**. If config lives in an unscanned package, seeing source files alone does not prove the bean exists.

**Diagnostic order:** test the reachable graph first; then test HTTP independently; then test methods directly; finally test the integrated endpoint. This sequence pinpoints **the exact misaligned layer** without weakening security to guess.

## 12. `@Secured` and `@RolesAllowed` must be tested separately

`@PreAuthorize` and `@PostAuthorize` are **pre/post expressions**. Spring Security also supports:

- `@Secured("ROLE_STAFF")`, requiring `@EnableMethodSecurity(securedEnabled = true)`.
- JSR-250's `@RolesAllowed("STAFF")`, importing `jakarta.annotation.security.RolesAllowed` on Spring Boot 3 and requiring `@EnableMethodSecurity(jsr250Enabled = true)`.

Example:

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
class ExtraMethodAnnotationsConfig {
}
~~~

This is **one method-security configuration option** if the application uses both annotations. If `@EnableMethodSecurity` already exists on another configuration class, do not scatter duplicate annotations: consolidate the flags in **one unified configuration point** as needed.

These annotations do not necessarily share `MethodSecurityExpressionHandler`:

| Service rule style | Component to inspect | How to verify |
| --- | --- | --- |
| `@PreAuthorize("hasRole('STAFF')")` | `PreAuthorizeAuthorizationManager` + `MethodSecurityExpressionHandler`. | Test service directly: ADMIN passes STAFF, USER fails STAFF. |
| `@PostAuthorize(...)` | `PostAuthorizeAuthorizationManager` + expression handler. | Use post-checks only where appropriate; never rely on them to undo side effects. |
| `@Secured("ROLE_STAFF")` | `SecuredAuthorizationManager` when securedEnabled. | Test `@Secured`-annotated service separately. |
| `@RolesAllowed("STAFF")` | `Jsr250AuthorizationManager` when jsr250Enabled. | Test `@RolesAllowed`-annotated service separately. |

Spring Security 6.5 Authorization Architecture docs describe role hierarchy support for both filter-based and these method-based styles. Still, if an app customizes interceptors, uses legacy code, or adds custom managers, never assume they share the hierarchy; **test every annotation type in use**.

For JSR-250, `@PermitAll` and `@DenyAll` are standalone rules, not role equivalents. An ADMIN ⇒ STAFF hierarchy can never turn `@DenyAll` into ALLOW.

## 13. Distinguishing RoleHierarchy from other forms of “inherited access”

`RoleHierarchy` solves **authority reachability**; it does not generate business rules or guarantee every condition across the app uses the hierarchy:

| Mechanism | Example | What does role hierarchy do? |
| --- | --- | --- |
| `hasRole("STAFF")` in hierarchy-aware HTTP DSL | ADMIN ⇒ STAFF | Lets ADMIN pass the STAFF rule. |
| `@PreAuthorize("hasRole('STAFF')")` with hierarchy-wired handler | ADMIN ⇒ STAFF | Lets the method execute. |
| Raw `Authentication.getAuthorities()` | Contains only `ROLE_ADMIN` | **Does not mutate** base authorities. |
| JWT `scope`/`scp` mapped to `SCOPE_read` | Holds only `SCOPE_read` | Does not convert to `ROLE_STAFF`; needs explicit mapping/edges. |
| `hasPermission(order, 'write')` / custom policy | Order belongs to tenant A | Does not check owner/tenant/state automatically. |
| Feature flag / subscription plan | Only premium users can export | Requires a dedicated rule, never inferred from role. |
| UI menu rendered for ADMIN | “Export” button is visible | Does not prove server enforces permissions properly. |
| Non-HTTP job with no SecurityContext | Scheduler invokes service | Requires proper authentication/service identity and policy. |

If the permission model uses `ROLE_ADMIN > REPORT_READ`, `RoleHierarchyImpl` can express role-to-permission edges and hierarchy-aware managers can evaluate `hasAuthority("REPORT_READ")`. However, this is an **architectural choice**, not automatic behavior. Document permission meanings clearly and test exact prefixes. Never use role hierarchy to accidentally let STAFF perform actions business intends only for ADMIN.

In multi-tenant systems, an admin of **shop-A** must not read **shop-B** reports simply because `ROLE_ADMIN > ROLE_STAFF`. When roles are tenant-scoped, include tenant context in policies or express scoped authorities explicitly; do not mix system-wide role edges with per-resource permissions.

## 14. Standalone Java 17 example: four hierarchy states across two layers

The following example **uses no Spring libraries** and **does not replace Spring Boot testing**. It models a role graph via `Map<String, Set<String>>`, traverses inheritance with BFS, and toggles two flags: `httpHierarchy`/`methodHierarchy`. Its purpose is to visualize **exactly why HTTP and method layers must be tested separately**.

Rules:

- Direct principals hold ADMIN, STAFF, or USER; inherited roles are never inserted into the base set.
- When a layer's hierarchy flag is enabled, that layer checks direct roles **or** roles reachable via the graph.
- When the flag is disabled, that layer checks direct roles only.
- ADMIN ⇒ STAFF ⇒ USER is one-way; no reverse inference.
- Tenant condition is an independent policy; hierarchy never makes cross-tenant access valid.

Save exact file **`RoleHierarchyLayersDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Set;

public class RoleHierarchyLayersDemo {
    private static final Map<String, Set<String>> INHERITS = Map.of(
            "ROLE_ADMIN", Set.of("ROLE_STAFF"),
            "ROLE_STAFF", Set.of("ROLE_USER"));

    static boolean allowed(Set<String> granted, String required,
                           boolean useHierarchy) {
        if (granted == null || granted.isEmpty()) return false;
        if (!useHierarchy) return granted.contains(required);
        Deque<String> queue = new ArrayDeque<>(granted);
        Set<String> visited = new java.util.HashSet<>();
        while (!queue.isEmpty()) {
            String role = queue.removeFirst();
            if (!visited.add(role)) continue;
            if (role.equals(required)) return true;
            queue.addAll(INHERITS.getOrDefault(role, Set.of()));
        }
        return false;
    }

    static String compare(Set<String> granted, String required,
                          boolean httpHierarchy, boolean methodHierarchy) {
        return "HTTP=" + allowed(granted, required, httpHierarchy)
                + ", METHOD=" + allowed(granted, required, methodHierarchy);
    }

    public static void main(String[] args) {
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> staff = Set.of("ROLE_STAFF");
        Set<String> user = Set.of("ROLE_USER");

        System.out.println("ADMIN -> STAFF, both on: "
                + compare(admin, "ROLE_STAFF", true, true));
        System.out.println("ADMIN -> STAFF, only HTTP: "
                + compare(admin, "ROLE_STAFF", true, false));
        System.out.println("ADMIN -> STAFF, only method: "
                + compare(admin, "ROLE_STAFF", false, true));
        System.out.println("ADMIN -> STAFF, both off: "
                + compare(admin, "ROLE_STAFF", false, false));
        System.out.println("ADMIN -> USER, both on: "
                + compare(admin, "ROLE_USER", true, true));
        System.out.println("STAFF -> ADMIN, both on: "
                + compare(staff, "ROLE_ADMIN", true, true));
        System.out.println("USER -> USER, both off: "
                + compare(user, "ROLE_USER", false, false));
        System.out.println("Anonymous -> STAFF, both on: "
                + compare(Set.of(), "ROLE_STAFF", true, true));
        System.out.println("Raw ADMIN authorities contain STAFF: "
                + admin.contains("ROLE_STAFF"));
        System.out.println("ADMIN -> STAFF across tenant? "
                + (allowed(admin, "ROLE_STAFF", true)
                        && "shop-a".equals("shop-b")));
    }
}
~~~

Compile and run with **JDK 17 or newer**:

~~~bash
javac --release 17 RoleHierarchyLayersDemo.java
java RoleHierarchyLayersDemo
~~~

Exact output:

~~~text
ADMIN -> STAFF, both on: HTTP=true, METHOD=true
ADMIN -> STAFF, only HTTP: HTTP=true, METHOD=false
ADMIN -> STAFF, only method: HTTP=false, METHOD=true
ADMIN -> STAFF, both off: HTTP=false, METHOD=false
ADMIN -> USER, both on: HTTP=true, METHOD=true
STAFF -> ADMIN, both on: HTTP=false, METHOD=false
USER -> USER, both off: HTTP=true, METHOD=true
Anonymous -> STAFF, both on: HTTP=false, METHOD=false
Raw ADMIN authorities contain STAFF: false
ADMIN -> STAFF across tenant? false
~~~

**Explanation:** the “only HTTP” and “only method” lines show two forms of **inconsistent configuration**. The line “Raw ADMIN authorities contain STAFF: false” reminds us that `ROLE_STAFF` need not exist in the raw principal even when policy computes inheritance properly. The tenant line shows that reaching STAFF alone does not authorize cross-tenant resources.

`Set.of("ROLE_ADMIN")` is a simulated role set, not a Spring `Authentication`. The BFS helper illustrates graph logic only; in production, **use `RoleHierarchyImpl` and Spring Security's authorization managers**, never copy demo traversal logic into security filters.

## 15. Where to place tests to separate an HTTP bug from a method bug

Here is a **checkpoint-oriented test matrix**, avoiding the mistake of equating “one passing request” with “both layers work”:

| Test case | HTTP/MockMvc test | Method/service test | What it proves |
| --- | --- | --- | --- |
| Admin with only `ROLE_ADMIN`, STAFF required | GET endpoint needing STAFF → passes filter | Service call `@PreAuthorize(STAFF)` → ALLOW | Inheritance at **each** layer. |
| STAFF requires STAFF | ALLOW | ALLOW | Direct authority match; **does not prove inheritance**. |
| USER requires STAFF | DENY | `AccessDeniedException` | No upward escalation. |
| Admin requires USER via ADMIN ⇒ STAFF ⇒ USER | ALLOW | ALLOW | Transitivity. |
| Anonymous requires STAFF | 401/redirect with appropriate entry point | DENY when unauthenticated | No implicit access. |
| Admin requests role outside graph | DENY | DENY | No undeclared role inference. |
| Admin has implied ROLE_STAFF on cross-tenant report | HTTP may ALLOW by role | Service/domain policy must DENY | Hierarchy **never overrides data checks**. |
| Self-invocation calls annotated method | HTTP may ALLOW | Test catches proxy bypass | Annotations alone are not proof of safety. |
| App uses `@Secured` / `@RolesAllowed` | Not directly tied | Test each annotation separately | Every manager must be verified. |
| Chain A, chain B, or unmatched route | Verify active chain and rule | Does not replace HTTP tests | No URL range slips past `SecurityFilterChain`. |

**Strongest strategy:** test an HTTP route backed solely by web rules and a fixture handler without method annotations; test a method-secured service directly through its proxy; then test the end-to-end HTTP→controller→service path. Whenever a test fails, you immediately know **which configuration layer** needs fixing.

An HTTP failure can return **403 before the controller**, whereas a method failure normally throws **`AccessDeniedException`** from the AOP interceptor, which a web exception handler may translate into 403. Thus **two identical-looking 403 responses do not prove the same root cause**. Use isolated fixtures/traces to tell them apart.

## 16. Version differences between Spring Security 6.5 and 7.x

Main examples in this lesson use **Spring Security 6.5 APIs and documentation**. In **Spring Security 7.x**, docs introduce `AuthorizationManagerFactory<T>` and `DefaultAuthorizationManagerFactory<T>` to construct/configure request- and method-based `AuthorizationManager` instances through one shared mechanism. You can configure `RoleHierarchy`, `rolePrefix`, and related properties on the factory, making it the recommended path for 7.x applications.

Do not copy 7.x `DefaultAuthorizationManagerFactory` examples verbatim into a Spring Security **6.5** project where that API does not exist. Conversely, do not assume a 6.x codebase's bean/custom manager setup behaves identically after a major upgrade. In particular, verify:

- **How role hierarchy reaches HTTP managers** (standard DSL, bean, custom manager, or factory).
- **Which expression handler method `@PreAuthorize`/SpEL uses**.
- Whether `@Secured`, JSR-250, and other annotations are enabled.
- HTTP chain paths and matchers, especially if upgrading `RequestMatcher` APIs at the same time.
- Custom `ROLE_` prefixes and JWT/DB authority mappings.
- Whether manually instantiated custom `AuthorizationManager` instances inspect reachable authorities.

Correct policy must be proven by **integration tests running against the exact version your project uses**, not a blanket claim that Spring “picks up role hierarchy automatically”.

## 17. Troubleshooting procedure when an API returns 403 despite admin's higher role

Suppose ADMIN is denied at `GET /api/reports/summary` when STAFF access was expected. Proceed in order:

1. **Verify raw auth:** does the principal hold `ROLE_ADMIN` with exact spelling/prefix, or only `ADMIN` or `SCOPE_admin`?
2. **Verify the graph:** does `RoleHierarchy.getReachableGrantedAuthorities([ROLE_ADMIN])` contain `ROLE_STAFF`?
3. **Verify the HTTP chain:** which `SecurityFilterChain` matched the URL; did an earlier broad `authenticated()` rule or custom `access(...)` shadow `/api/reports/**`?
4. **Test the HTTP rule in isolation:** use a fixture or manager test keeping the ADMIN principal with strictly one role. Never open `permitAll` to mask a bug.
5. **Check method security:** is `@EnableMethodSecurity` enabled; does `MethodSecurityExpressionHandler` have `setRoleHierarchy` and is Spring using it?
6. **Check proxy invocation:** does the controller inject Spring-managed `ReportService`, or is `this.summary()` bypassing the proxy?
7. **Check the annotation:** `@PreAuthorize`, `@Secured`, or `@RolesAllowed`? Each has its own interceptor/manager and enablement flag.
8. **Check domain policies:** did the service legitimately DENY due to tenant, owner, report status, or feature flags?
9. **Check other filters:** did CSRF, JWT authentication, CORS, or a custom filter return 403 before `AuthorizationFilter`? `permitAll` is not a cure-all for 403s.
10. **Re-test both ALLOW and DENY:** ADMIN needing STAFF must pass, USER needing STAFF must still fail, and cross-tenant ADMIN must still be blocked from private reports.

In dev/test environments, security debug logging/tracing helps identify the denying phase. Never log JWTs, cookies, passwords, or personal data just to inspect a user's roles. Use test fixtures and request correlation IDs when analyzing multi-layer requests.

### Production rollout checklist for role hierarchy

- [ ] Hierarchy is defined as **one clear, auditable relationship** with no accidental path granting high privileges.
- [ ] `RoleHierarchy` bean exists in the active security **application context**.
- [ ] HTTP `authorizeHttpRequests` applies the hierarchy to appropriate rules; custom managers are wired explicitly when needed.
- [ ] `@EnableMethodSecurity` is enabled; `MethodSecurityExpressionHandler` uses the right hierarchy.
- [ ] `@Secured` and JSR-250 (if used) are enabled, configured, and tested independently.
- [ ] `ROLE_` and `hasRole`/`hasAuthority` align consistently with JWT/DB/`UserDetails`.
- [ ] Tests verify higher roles inherit lower roles and lower roles **cannot** reach higher roles at both HTTP and method layers.
- [ ] Direct proxy tests on services confirm annotations are never bypassed.
- [ ] End-to-end HTTP→service endpoint tests catch divergence between layers.
- [ ] Separate tests verify owner/tenant/non-role conditions.
- [ ] Regression tests run on every Spring Security upgrade or role graph change.

**Conclusion:** `RoleHierarchy` is an **authority relationship structure**, while its enforcement depends on each **access checkpoint**. For Servlet/Spring Boot applications, verify **HTTP `authorizeHttpRequests`** and **method `@PreAuthorize` through Spring proxies** separately, then test the combined path. An ADMIN passing HTTP while failing at the method layer (or vice versa) signals mismatched layer configurations — never a reason to relax access rules. Always keep data-scope and tenant checks independent of role inheritance.

### Official references

- [Spring Security 6.5 — Authorization Architecture: Hierarchical Roles](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Method Security: RoleHierarchy and MethodSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — AuthorityAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security 7.1 — AuthorizationManagerFactory and Hierarchical Roles](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
