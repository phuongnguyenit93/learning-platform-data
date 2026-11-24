# FilterSecurityInterceptor vs. AuthorizationFilter in Spring Security

## 1. Objectives and Migration Context

In **Servlet-based** Spring Security, both **FilterSecurityInterceptor** and **AuthorizationFilter** enforce **HTTP request-level authorization**: before forwarding a request to a controller, they determine whether the request is allowed to proceed. The core differences lie in the **decision-making model**, **configuration API**, **how Authentication is retrieved**, and **how permissions are applied across dispatches**.

- **FilterSecurityInterceptor (FSI)** belongs to the legacy model based on **SecurityMetadataSource → ConfigAttribute → AccessDecisionManager / AccessDecisionVoter**.
- **AuthorizationFilter (AF)** belongs to the modern model based on **AuthorizationManager**, typically configured via **authorizeHttpRequests**. This model is more unified with authorization approaches across other parts of Spring Security.
- When migrating from **authorizeRequests** to **authorizeHttpRequests** in Spring Security 6.x, HTTP authorization checks are performed by **AuthorizationFilter** instead of **FilterSecurityInterceptor**.
- Both belong to the Servlet filter layer, distinct from method security via **@PreAuthorize**. Changing the HTTP filter does not automatically enforce fine-grained permissions per user, tenant, owner, or data object in the service layer.

This lesson explains the mechanisms, compares both classes, covers safe migration rules in Spring Security 6.x/Spring Boot 3.x, provides runnable Java examples, shows how to inspect the filter chain, and highlights common pitfalls when changing versions.

**Version scope:** runnable examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**. APIs may be deprecated or adjusted in newer major versions; when upgrading to Spring Security 7+, consult the official migration guide for the target version rather than assuming every legacy snippet still works.

## 2. Position of Both Filters in Spring Security

In a Spring MVC application, a request passes through servlet filters invoked by the container. **DelegatingFilterProxy** delegates to the **springSecurityFilterChain** bean; this bean is a **FilterChainProxy**, which selects the first **SecurityFilterChain** matching the request in priority order. Each SecurityFilterChain contains multiple Security Filters for authentication, CSRF, exception handling, and authorization.

~~~text
HTTP request
    |
    v
Servlet container / DelegatingFilterProxy
    |
    v
FilterChainProxy ("springSecurityFilterChain")
    |
    +-- Select matching SecurityFilterChain via securityMatcher
            |
            +-- CSRF, authentication, security context, ...
            +-- ExceptionTranslationFilter
            +-- AuthorizationFilter  [authorizeHttpRequests]
            |            or
            +-- FilterSecurityInterceptor [legacy authorizeRequests]
            |
            v
        DispatcherServlet -> Controller -> Service
~~~

This diagram is a **simplified logical view**, not an exhaustive list of every filter or the exact order for an arbitrary application. Which filters are active depends on configuration (HTTP Basic, form login, OAuth2, custom filters...). **AuthorizationFilter typically sits at the end of the Spring Security chain** in the standard configuration of the new model, after authentication and other protective filters. **ExceptionTranslationFilter** translates security exceptions into authentication entry points or access-denied responses.

There are **two distinct matching levels**:

1. **FilterChainProxy selects the chain** using **securityMatcher** and the order of **SecurityFilterChain** beans.
2. **The authorization filter inside the chain** applies **requestMatchers** rules from **authorizeHttpRequests** (or the corresponding legacy mechanism).

If no SecurityFilterChain matches, the request may go **unprotected by Spring Security**. If a chain matches but rules are too broad or misordered, authorization outcomes may diverge from intended policy. This holds true for both the old and new models; upgrading the filter does not fix misconfigured matchers.

## 3. How FilterSecurityInterceptor Works

### 3.1. Legacy components

In the legacy model, **FilterSecurityInterceptor** inherits the mechanism of intercepting a secure object and checking permissions across multiple components:

1. Receives **HttpServletRequest, HttpServletResponse, FilterChain** wrapped in a **FilterInvocation**.
2. Reads **Authentication** from **SecurityContextHolder**.
3. Queries **FilterInvocationSecurityMetadataSource / SecurityMetadataSource** to obtain **ConfigAttribute**s for the request, such as required roles or conditional expressions.
4. Passes Authentication, the secure object, and ConfigAttributes to **AccessDecisionManager**.
5. **AccessDecisionManager** applies a decision strategy, potentially combining **AccessDecisionVoter**s. Examples in legacy configurations include **AffirmativeBased**, **RoleVoter**, and **WebExpressionVoter**.
6. If denied, throws **AccessDeniedException**; if granted, proceeds down the FilterChain.

~~~mermaid
flowchart TD
    A["HTTP request / FilterInvocation"] --> B["FilterSecurityInterceptor"]
    B --> C["SecurityContextHolder: Authentication"]
    B --> D["SecurityMetadataSource: ConfigAttribute"]
    C --> E["AccessDecisionManager"]
    D --> E
    E --> F{"Decision"}
    F -->|Allow| G["Continue FilterChain"]
    F -->|Deny| H["AccessDeniedException"]
~~~

These classes, voters, and strategies are real mechanics of the legacy system; **you should not arbitrarily register an AccessDecisionManager** in a new AuthorizationManager configuration. When migrating custom voters, clarify the original policy first and translate how the decision is expressed.

### 3.2. Legacy HTTP DSL configuration

In Spring Security versions that retain compatible APIs, **authorizeRequests** configures web rules using the legacy model. The following snippet is for **identification and comparison**, not for new code:

~~~java
// Legacy: only for projects/versions that still support authorizeRequests.
http.authorizeRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

In the new configuration, replace with **authorizeHttpRequests**:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

**Do not migrate via find-and-replace on the method name alone and skip testing.** You must check specific matchers, rule ordering, custom access logic, dispatch types, multiple SecurityFilterChains, anonymous/authenticated states, and custom filters.

Legacy **antMatchers/mvcMatchers** APIs have changed across Spring Security versions; when migrating from 5.x code, do not copy matcher methods removed in 6.x verbatim. Use **requestMatchers** with appropriate types and test actual paths.

## 4. How AuthorizationFilter Works

In the new model, **AuthorizationFilter** uses **AuthorizationManager** to produce a decision:

1. Creates a **Supplier<Authentication>** that reads the identity from **SecurityContextHolder** only when actually needed.
2. Invokes **AuthorizationManager** with the supplier and current request; rules configured via **authorizeHttpRequests** are resolved through the request matcher mechanism.
3. If denied, throws **AccessDeniedException** (or the version-compatible denial exception); **ExceptionTranslationFilter** handles it according to the authentication context.
4. If allowed, the filter invokes the next step in the chain.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["AuthorizationFilter"]
    B --> C["Supplier of Authentication"]
    B --> D["AuthorizationManager: match request + apply rule"]
    C --> D
    D --> E{"Allowed?"}
    E -->|Yes| F["Continue FilterChain"]
    E -->|No| G["AccessDeniedException"]
    G --> H["ExceptionTranslationFilter: entry point or 403"]
~~~

**Lazy authentication lookup** is a notable difference: for a **permitAll** rule, the system may not need to look up Authentication to decide. That does not mean bypassing the entire security filter chain; authentication, CSRF, or custom filters placed earlier may still run depending on configuration.

### 4.1. What is AuthorizationManager?

**AuthorizationManager** expresses authorization behavior based on a **Supplier<Authentication>** and a secure object or request context. Spring Security 6.x includes standard implementations such as:

- **AuthorityAuthorizationManager**: checks authorities/roles.
- **AuthenticatedAuthorizationManager**: checks authenticated status.
- **RequestMatcherDelegatingAuthorizationManager**: selects the matching rule for an HttpServletRequest.
- **WebExpressionAuthorizationManager**: supports migrating legacy HTTP SpEL expressions when needed.
- Custom **AuthorizationManager**s to check specialized permission data.

Define rules via **authorizeHttpRequests**:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers(HttpMethod.GET, "/reports/**").hasAuthority("REPORT_READ")
        .anyRequest().denyAll()
);
~~~

Using this snippet in a real Java class requires importing **org.springframework.http.HttpMethod**. **hasRole("ADMIN")** checks the **ROLE_ADMIN** authority by default convention, whereas **hasAuthority("REPORT_READ")** checks the exact authority name. Do not infer that a user with ROLE_ADMIN automatically has REPORT_READ unless your authorities configuration grants it.

In **authorizeHttpRequests**, rules are evaluated in declaration order and **the first matching rule decides**. Place **/admin/** before a broad **/** rule, avoid letting **permitAll** cover protected resources, and use **anyRequest().denyAll()** when policy requires default-deny.

## 5. Comparison Table: FilterSecurityInterceptor vs. AuthorizationFilter

| Criterion | FilterSecurityInterceptor (legacy) | AuthorizationFilter (modern) |
| --- | --- | --- |
| Functional group | Servlet request authorization | Servlet request authorization |
| Common configuration style | **authorizeRequests** / legacy XML | **authorizeHttpRequests** |
| Decision API | **AccessDecisionManager** and **AccessDecisionVoter**s | **AuthorizationManager** |
| Policy data | **SecurityMetadataSource / ConfigAttribute** | AuthorizationManagers and request matchers |
| Target object | **FilterInvocation** | **HttpServletRequest** evaluated via manager |
| Authentication | Typically read immediately in the legacy interception flow | **Supplier<Authentication>**, supports deferred lookup |
| Public rules | Supports permitAll | Supports permitAll with beneficial lazy lookup |
| Expressions and rules | Legacy expression voter/metadata | Built-in managers, **WebExpressionAuthorizationManager** if SpEL is needed |
| Custom rules | Voters, decision managers, security metadata | Custom **AuthorizationManager** |
| Dispatch | Had once-per-request options/settings in legacy setups | **Evaluates dispatches passing through the filter by default**, including FORWARD/ERROR; dispatcher types must be checked |
| Direction in 6.x | Legacy compatibility/migration | Recommended configuration approach |

**Similarities:** both decide access before a controller processes the request; both rely on identity/authorities provided by the authentication layer; both can lead to **AccessDeniedException**; both require proper security chains, matchers, and policies. Neither replaces **object-level authorization** checks such as owner/tenant/ACL when business rules demand them.

**Do not conclude one class is inherently more secure from its class name alone.** An AuthorizationFilter configured with faulty matchers or overly broad permitAll still exposes data; a FilterSecurityInterceptor setup with proper rules can still enforce valid protection. The benefit of the new model is a cleaner, more extensible API aligned with Spring Security's long-term direction; migration still requires policy verification.

## 6. Migration Pitfall: DispatcherType Differences

In Servlets, a single request may undergo multiple **dispatches**. For example:

- **REQUEST**: the initial HTTP reception.
- **FORWARD**: internal server forward to another controller/view.
- **ERROR**: container error path handling, typically **/error**.
- **INCLUDE** and **ASYNC**: depending on application usage and filter registration in the servlet container.

Per Spring Security 6.x documentation, **AuthorizationFilter checks permissions on every dispatch it receives** by default, not just the initial REQUEST. If a request is permitted on **/reports/7** and the application forwards to another URL, rules can be evaluated again against the current path and dispatcher type. Some legacy setups were configured to check once per request, so differences can surface after migration.

### 6.1. Post-upgrade error example

Suppose a user is allowed to access **GET /documents/7**. The controller forwards to **/WEB-INF/views/document.jsp**, but the new rules only permit **/documents/** and set **anyRequest().denyAll()**. If the FORWARD dispatch passes through the Spring Security filter chain, the forward may be denied, preventing the view from rendering.

Similarly, if a backend error occurs and the container dispatches to **/error**, and **/error** is also blocked, the user may see a confusing error page or status that masks the original error.

### 6.2. Handling intentionally

If the application uses forwarding/view rendering and internal error paths are trusted, consider a dispatcher type rule:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(authorize -> authorize
        .dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
            .permitAll()
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/documents/**").authenticated()
        .anyRequest().denyAll()
);
~~~

**This is a policy choice, not a mandatory rule for all applications.** Permitting all FORWARD/ERROR dispatches changes the access surface; evaluate internal forward targets, how the container registers filters, endpoints with side effects, and your trust model. If stricter control is needed, configure specific URLs/dispatcher types or an appropriate custom rule. Never apply **permitAll()** broadly to **/error** or **/** just to turn tests green without evaluating security impact.

For ASYNC/ERROR/FORWARD, **only dispatcher types actually routed through the security filter by the servlet container** are subject to rules. Test against your real filter registration and container rather than relying solely on general descriptions.

## 7. Runnable Spring Boot 3.3.x Example with AuthorizationFilter

Build an application with **Java 17**, Spring Boot **3.3.5**, Spring Security 6.x, Spring MVC, and HTTP Basic. Policy:

- **GET /public/ping**: public.
- **GET /reports/{id}**: only users with authority **REPORT_READ**.
- **GET /admin/panel**: only users with **ROLE_ADMIN**.
- All other paths: **DENY**.
- Tests verify that SecurityFilterChain contains **AuthorizationFilter** and does not contain **FilterSecurityInterceptor** in the new setup.

The example uses mock accounts with **{noop}** strictly for local/test runs; real applications must use proper password encoding, identity provider configuration, and no hardcoded credentials.

### 7.1. Structure

~~~text
authorization-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/security/
    │   ├── AuthorizationFilterDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── AuthorizationFilterTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'authorization-filter-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
~~~

**src/main/java/demo/security/AuthorizationFilterDemoApplication.java**

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationFilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationFilterDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/security/SecurityConfig.java**

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .hasAuthority("REPORT_READ")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader-pass")
                        .authorities("REPORT_READ")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .authorities("VIEWER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("ADMIN")
                        .build()
        );
    }
}
~~~

Because policy is configured with **authorizeHttpRequests**, the framework builds **AuthorizationFilter**. Spring Security's default CSRF protection remains enabled: the demo only has GET endpoints; when testing mutating methods, supply a valid CSRF token if the app uses sessions/cookies. CSRF is a separate layer from authorization and can return 403 before authorization rules are evaluated.

**src/main/java/demo/security/DemoController.java**

~~~java
package demo.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/reports/{id}")
    public String report(@PathVariable long id) {
        return "report:" + id;
    }

    @GetMapping("/admin/panel")
    public String admin() {
        return "admin";
    }
}
~~~

This controller intentionally returns static strings to focus on **HTTP route authorization**; if real reports have an owner/tenant, **hasAuthority("REPORT_READ")** is insufficient to enforce per-report permissions. Add checks in the service/repository layer or a custom AuthorizationManager aligned with resource policy.

### 7.2. Testing the security filter chain and HTTP behavior

**src/test/java/demo/security/AuthorizationFilterTest.java**

~~~java
package demo.security;

import jakarta.servlet.Filter;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.access.intercept.FilterSecurityInterceptor;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFilterTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy springSecurityFilterChain;

    @Test
    void usesAuthorizationFilterInsteadOfLegacyInterceptor() {
        List<Filter> filters = springSecurityFilterChain
                .getFilterChains()
                .stream()
                .flatMap(chain -> chain.getFilters().stream())
                .toList();

        assertTrue(filters.stream()
                .anyMatch(AuthorizationFilter.class::isInstance));
        assertFalse(filters.stream()
                .anyMatch(FilterSecurityInterceptor.class::isInstance));
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousUserMustAuthenticateForReport() throws Exception {
        mvc.perform(get("/reports/7"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutReportAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/reports/7")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void reportReaderCanAccessReport() throws Exception {
        mvc.perform(get("/reports/7")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:7"));
    }

    @Test
    void readerCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void unlistedPathIsDeniedByDefault() throws Exception {
        mvc.perform(get("/not-listed")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void reportPostIsDeniedAfterValidCsrfCheck() throws Exception {
        mvc.perform(post("/reports/7")
                        .with(httpBasic("reader", "reader-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }
}
~~~

Run inside the project directory with JDK 17+ and a compatible Gradle version (e.g., Gradle wrapper 8.5 if included in the project):

~~~bash
gradle test
~~~

Expected result is **9 tests PASS** when all files are created accurately. This reflects design and source analysis, not captured stdout from an executed build. You can also run the app with **gradle bootRun** and test endpoints on **localhost:8080** using HTTP Basic. Sample passwords are for learning only.

**Why does the POST test include .with(csrf())?** Without a CSRF token, **CsrfFilter** can block before **AuthorizationFilter** with HTTP 403. Adding a valid token ensures the test actually reaches the **GET /reports/** rule and then **anyRequest().denyAll()**, proving POST is denied. **403** alone does not tell which filter made the decision: you must understand the processing path and also test filter presence.

Checking the filter list verifies the configuration creates the expected class, while 401/403/200 tests prove behavior; **checking only the class without checking policies is insufficient**.

## 8. Migrating from Legacy Components to AuthorizationManager

### 8.1. Migration workflow

1. **Inventory current policy:** document all routes, HTTP methods, roles, authorities, expressions, rule order, any custom voters/AccessDecisionManagers, security chains, and XML configs.
2. **Identify target framework versions:** DSLs and matchers differ across Spring Security 5.x, 6.x, and 7.x. Do not pick an API merely because a blog post worked on another version.
3. **Switch to authorizeHttpRequests** in each migrated SecurityFilterChain, mapping simple rules to **permitAll**, **authenticated**, **hasRole**, **hasAuthority**, and **access**.
4. **Migrate custom policies:** replace dependencies on **ConfigAttribute**, **AccessDecisionVoter**, or custom AccessDecisionManager with a business-equivalent **AuthorizationManager**. There is no one-to-one mechanical rename for every custom voter.
5. **Verify matching and order:** securityMatcher selects the chain; requestMatchers select permissions inside the chain. Ordering can determine whether an endpoint is public or blocked.
6. **Check dispatcher types** (FORWARD/ERROR/ASYNC), **/error** paths, and view rendering if the app uses forwards.
7. **Create regression tests** for anonymous users, authenticated users with and without roles, multiple tenants, HTTP methods, paths with slashes/encoding, and custom security chains.
8. **Observe the filter chain and logs:** verify the right filter is active; exclude unneeded legacy configuration and closely review custom filters anchored on old filter positions.
9. **Run tests on a production-like runtime**, including reverse proxy/path rewriting and error dispatches if applicable; roll out only after matching expected behavior.

### 8.2. Simple role-check migration example

**Before — legacy expression (illustrative):**

~~~java
// Legacy system: uses AccessDecisionManager and expression voter.
http.authorizeRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

**After — AuthorizationManager:**

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Both can express the same policy in versions that still support both. However, migration still requires verifying **anonymous users**, USER role, ADMIN role, and relevant dispatchers. For complex legacy rules previously relying on SpEL, **WebExpressionAuthorizationManager** can serve as an initial migration step before moving to a custom type-safe AuthorizationManager.

### 8.3. Request-level custom AuthorizationManager

The following pattern illustrates writing a rule beyond built-in managers. This is an **integration snippet**, not a standalone program; import types matching your Spring Security version and provide **HttpSecurity** inside a SecurityFilterChain bean:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Spring Security 6.x: rule allowing only authority REPORT_READ.
AuthorizationManager<RequestAuthorizationContext> readReport =
        (authentication, context) -> new AuthorizationDecision(
                authentication.get().getAuthorities().stream()
                        .anyMatch(a -> a.getAuthority().equals("REPORT_READ"))
        );

http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").access(readReport)
        .anyRequest().denyAll()
);
~~~

In a real environment, the manager must handle **null/anonymous Authentication** per policy; if checking owner/tenant, retrieve resource metadata from a trusted source and handle request paths safely. The snippet above only shows 6.x **AuthorizationManager** syntax; against null Authentication, it must be hardened before production use. The built-in **hasAuthority("REPORT_READ")** remains preferable for simple rules like this example, as it already covers standard framework semantics.

Note: a custom **AuthorizationManager** is where real policy lives, so test it as a security decision function. Do not convert a complex custom voter into a lambda returning **true** for unspecified cases, and do not expect the new filter to infer resource ownership automatically.

## 9. Common Upgrade Errors and Diagnostics

| Symptom | Cause to Check | Verification Method |
| --- | --- | --- |
| USER reaches admin URL after migration | Overly broad matcher, wrong rule order, wrong SecurityFilterChain, or endpoint outside chain | Positive/negative HTTP permission tests, print filter chain, check securityMatcher |
| New 403 appears during view rendering | FORWARD dispatch blocked by rules | Test DispatcherType.FORWARD and view paths |
| Error page missing or 403 masks original error | ERROR dispatch or **/error** blocked by rules | Check error dispatch and original status/logs |
| Test returns 403 on POST, assumed authorization works | CSRF blocked before reaching AuthorizationFilter | Test with a valid CSRF token or inspect AccessDenied source |
| 401 confused with 403 | Unauthenticated request; HTTP Basic requires challenge | Test anonymous and authenticated separately |
| Custom voter no longer takes effect | New model uses AuthorizationManager and does not invoke legacy voters as before | Move policy into a manager and test specific cases |
| New filter present but URL unprotected | No matching SecurityFilterChain or custom filter bypass | Inspect chain configuration and real requests |
| Assuming filter running twice is a bug | AuthorizationFilter can run across multiple dispatches | Distinguish REQUEST, FORWARD, ERROR, ASYNC and corresponding rules |
| Unable to enforce owner/tenant permissions | Role rules do not express per-object permissions | Add resource-level policy in service/AuthorizationManager |
| Both legacy and new filters appear | Multiple security chains, overlapping configs, or custom registration | Log filters per request/chain; avoid ad-hoc manual additions |

### 9.1. How to observe the filter chain

Enable targeted DEBUG logging in dev/test environments:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Or in tests, autowire **FilterChainProxy** as in Section 7.2 to inspect filters. Class lists aid diagnosis; a class appearing in the list **does not prove it handles a specific request** if the app has multiple chains. When needed, inspect each SecurityFilterChain and request matcher before drawing conclusions.

Never log tokens, session cookies, passwords, or sensitive payloads when diagnosing authorization.

### 9.2. Performance impact

**AuthorizationFilter** can defer Authentication lookup until the manager truly needs it, helping **permitAll** paths avoid unnecessary identity retrieval. Real-world gains depend on configuration and load; **you cannot claim every request becomes faster** just by swapping filters. Rules checking DB/ACLs can still incur high cost and require profiling.

The number of authorization checks may also increase due to multiple dispatches. If the app has frequent forward/error dispatches, measure request counts, latency, and policy evaluation counts. Never solve performance issues by broadening permissions or disabling authorization. For custom managers, permission queries can be optimized, but decision caches must key by user, tenant, resource, action, and policy/ACL version whenever those factors affect the outcome.

## 10. Relationship to Method Security and Object-Level Protection

**FilterSecurityInterceptor / AuthorizationFilter** checks **HTTP requests**. **@EnableMethodSecurity** and **@PreAuthorize** (when invoked via a Spring proxy) check **method invocations**. Each layer has its own scope:

~~~text
HTTP SecurityFilterChain:
  /api/reports/** -> authenticated() / REPORT_READ
             |
             v
Controller -> @PreAuthorize / policy service
             |
             v
Repository -> report by ID + tenant + effective permission
~~~

A user with **REPORT_READ** is still not automatically allowed to read documents belonging to another tenant. If **GET /api/reports/202** accepts `reportId` from the client, verify tenant/owner/ACL at the policy layer or trusted data query. Avoid IDOR/BOLA vulnerabilities caused by assuming migrating to AuthorizationFilter solved all authorization concerns.

Conversely, securing services with **@PreAuthorize** does not fully replace HTTP security: CSRF, sessions, authentication, dispatcher types, and route matching still require separate configuration and testing. If an annotated method is called via **this.method()** on the same bean under Spring proxying, advice may be bypassed; test actual call paths as well.

## 11. Acceptance Checklist Before Removing Legacy Paths

- **Configuration**: every migrated SecurityFilterChain uses **authorizeHttpRequests**; old **authorizeRequests**, custom AccessDecisionManagers, voters, and legacy XML have been searched and evaluated.
- **Request paths**: proved which SecurityFilterChain matches public, admin, API, actuator, docs, and error/view paths; no sensitive endpoints fall outside the chains.
- **Matching**: requestMatchers order, HTTP methods, path prefixes, URL encoding, trailing slashes, servlet paths, and proxy rewriting match policy.
- **Permissions**: complete 200/401/403 cases per authentication state; users lacking roles are blocked, authorized users succeed.
- **Dispatch**: FORWARD/ERROR/ASYNC handled per approved policy; both view rendering and error paths tested if applicable.
- **Customizations**: every legacy policy has an equivalent **AuthorizationManager** and counter-example tests; no lingering reliance on old voter side effects.
- **Actual filters**: verified running chains contain AuthorizationFilter under the new DSL; did not mix up classes from other chains and misdiagnose.
- **Service layer**: resource owner/tenant/ACL checks remain in place for workflows requiring object-level authorization.
- **Operations**: logs, metrics, performance, and permission caches do not mask denials; verified write transactions to prevent side effects before authorization.
- **Versions**: ran migration tests on **actual dependency versions**; cross-checked docs for the exact major/minor version in use rather than snippets from another version.

## 12. Conclusion

**FilterSecurityInterceptor** is the request authorization mechanism based on **SecurityMetadataSource + AccessDecisionManager/voters**. **AuthorizationFilter** is the **AuthorizationManager**-based mechanism typically created when migrating to **authorizeHttpRequests**, supporting deferred Authentication lookup when rules do not need it.

During migration, what matters most is preserving or clarifying **access policies**, while re-verifying matching, dispatchers, custom managers, and every caller type. A successful migration means legitimate callers retain access, unauthorized callers stay denied, and per-resource permissions remain enforced at the proper layer.

### Official Documentation

- Spring Security 6.5 — Authorize HTTP Requests, flow, and migration: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Servlet Architecture/FilterChainProxy: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Servlet Authorization Migration: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html
- Spring Security 6.5 — Multiple SecurityFilterChains, securityMatcher/requestMatchers: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
