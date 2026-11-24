# How WebSecurityExpressionRoot Differs from the Method Security Context

> **Topic:** Spring Security – authorization · **Group:** Expressions and policies. This lesson focuses on Spring Security **Servlet**: HTTP request-level expressions are evaluated in the web context, whereas `@PreAuthorize`/`@PostAuthorize` expressions are evaluated in the method invocation context. Java examples use Java 17+ and common APIs from Spring Security 6.x/7.x.

## 1. Why does the same expression behave differently?

Spring Security uses Spring Expression Language (SpEL) for certain authorization rules. An expression like `hasAuthority('report:read')` can appear in both web and method security because both places have `Authentication` information. However, the **expression root object** and **what is being authorized** differ:

- **Web security:** the question is "May this HTTP request pass through the filter chain into the application?". The expression has information about `HttpServletRequest`; `WebSecurityExpressionRoot` exposes `request` and `hasIpAddress(...)`.
- **Method security:** the question is "Is this method invocation, with these arguments and/or this result, permitted?". The expression is built from `MethodInvocation`, exposing parameter variables like `#p0`, and `returnObject`/`filterObject` at the appropriate stage.

For example: Bob holds authority `report:read`, while report ID 1 belongs to Alice. The URL rule lets anyone with `report:read` call `GET /api/reports/1`; the service rule denies Bob from viewing a report he does not own. **Passing the web layer does not mean passing the method layer.** These are two independent checks serving two different kinds of data.

## 2. What are the expression root and EvaluationContext?

When Spring Security evaluates SpEL, the framework creates an **EvaluationContext** containing the root, variables, functions, bean resolver, and metadata tied to the interception point. In an expression:

- `hasAuthority('report:read')`: invokes a method on the root; you do not need to write `#root.hasAuthority(...)`.
- `authentication.name`: accesses the `Authentication` provided by the security context.
- `#p0`: retrieves the first parameter of the **method invocation** when using method security.
- `request.method`: accesses the HTTP method through the `request` property of the **web root** in a web SpEL context.
- `@reportAccess.canRead(authentication, #p0)`: calls a Spring bean named `reportAccess`, passing user data and the method parameter.

Do not equate the **root** with `Authentication`: `Authentication` represents the identity/authorities used in the decision, whereas the root bundles security operations together with context data for the interception point.

Architecturally, the base class `SecurityExpressionRoot` provides operations such as `hasRole`, `hasAuthority`, `isAuthenticated`, `permitAll`, and `denyAll`. Spring Security extends that semantics for web and method contexts, without creating the same set of variables everywhere.

~~~text
                          Authentication
                                |
                    Common security checks
                  (SecurityExpressionRoot)
                         /             \
      HTTP Servlet request               Method invocation
               |                                  |
  WebSecurityExpressionRoot          MethodSecurityExpressionRoot
  - request                          - parameters #p0/#p1, #name
  - hasIpAddress(...)                 - returnObject (post)
  - authentication, hasRole...        - filterObject (filter)
               |                                  |
 Web expression evaluation             Method expression evaluation
 (WebExpressionAuthorizationManager)  (@PreAuthorize/@PostAuthorize/...)
~~~

This is a conceptual diagram, not a requirement for application authors to instantiate root classes manually. In modern Spring Security versions, the framework uses handlers/authorization managers to build the evaluation context. Internal APIs and root constructors may change across versions; configure via DSL, annotations, or appropriate SPIs.

## 3. WebSecurityExpressionRoot: HTTP Servlet context

`WebSecurityExpressionRoot` lives in package `org.springframework.security.web.access.expression`. In web SpEL, it provides:

| Member | Meaning | Example |
| --- | --- | --- |
| `authentication`, `principal` | Current authentication/user object | `authentication.name == 'alice'` |
| `hasAuthority(...)`, `hasRole(...)` | Check authority/role | `hasAuthority('report:read')` |
| `request` | The `HttpServletRequest` being protected | `request.method == 'GET'` |
| `hasIpAddress(...)` | Check request IP/CIDR | `hasIpAddress('192.0.2.0/24')` |
| `permitAll`, `denyAll` | Allow/deny independent of specific resources | `permitAll` |

`request` is the servlet request currently processed by the filter chain; it is not an implicit parameter of service methods. `hasIpAddress` evaluates the request address according to the framework implementation; behind a reverse proxy/load balancer, you must configure trusted IP sources rather than blindly trusting client-supplied headers. Never rely on IP alone as proof of identity.

### 3.1. Modern web configuration: prefer AuthorizationManager

For Servlet apps, use `SecurityFilterChain` and `authorizeHttpRequests`:

~~~java
// Snippet inside a @Configuration class of a Spring Boot application.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/*")
                        .hasAuthority("report:read")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Key imports: `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.http.HttpMethod`, `org.springframework.security.config.Customizer`, and `org.springframework.context.annotation.Bean`.

**A very common misconception:** `.hasAuthority("report:read")` in this DSL uses a strongly typed `AuthorizationManager`; it **does not necessarily parse a SpEL string and does not necessarily instantiate `WebSecurityExpressionRoot`**. The existence of the web root class does not mean every web configuration passes through an expression root.

When you actually need **web SpEL**, you can use `WebExpressionAuthorizationManager`:

~~~java
// Snippet added to authorizeHttpRequests(...), placed before anyRequest().
.requestMatchers("/internal/**")
    .access(new WebExpressionAuthorizationManager(
        "hasAuthority('internal:read') and hasIpAddress('192.0.2.0/24')"))
~~~

Import: `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager`. This is an **HTTP request** configuration example, not a service annotation. The IP block is a documentation-only address range; replace it with your real network policy if applied. Spring Security recommends strongly typed `AuthorizationManager` implementations whenever rules can be expressed via the API, and using the expression manager when migrating or expressing SpEL rules.

Modern flow:

~~~text
HTTP request
 -> SecurityFilterChain / AuthorizationFilter
 -> requestMatchers select the rule
 -> AuthorizationManager<RequestAuthorizationContext>
    -> hasAuthority(...) via direct manager, OR
    -> WebExpressionAuthorizationManager evaluates web SpEL
 -> allow or deny before reaching the controller
~~~

Do not use `@EnableMethodSecurity` as a replacement for `SecurityFilterChain`. And do not configure `WebSecurityExpressionRoot` by instantiating an object manually and passing it into `@PreAuthorize`; that is not an official integration path.

## 4. Method security: the MethodInvocation context

Method security applies when calls pass through a Spring AOP proxy (or configured interception mechanism), regardless of whether the method is invoked from a controller, scheduled job, message listener, or another bean. Enable it with `@EnableMethodSecurity`.

The standard handler is typically `DefaultMethodSecurityExpressionHandler`; it builds a context from `MethodInvocation` and a root containing common operations along with method-bound details. Variables apply by stage:

| Expression in method security | When does it make sense? | Example |
| --- | --- | --- |
| `authentication`, `principal` | When `Authentication` is present in the security context | `authentication.name` |
| `hasAuthority(...)`, `hasRole(...)` | Common permission expressions | `hasAuthority('report:read')` |
| `#p0`, `#a0` | First parameter of the intercepted method | `#p0 > 0` |
| `#reportId` | Named parameter if parameter name discovery is available | `#reportId == 1` |
| `returnObject` | Result after the method runs, e.g., `@PostAuthorize` | `returnObject.owner() == authentication.name` |
| `filterObject` | Current element in `@PreFilter` or `@PostFilter` | `filterObject.owner() == authentication.name` |
| `this` | Target object being protected in the method context | Expression may reference the service |
| `@bean.method(...)` | Invokes a policy bean for business checks | `@reportAccess.canRead(authentication, #p0)` |

**Stage distinction:** inside `@PreAuthorize`, the intercepted call's `returnObject` does not exist yet; `@PostAuthorize` can inspect the result, but the method body has already executed. `filterObject` only makes sense while the framework is filtering collection elements. Do not put `returnObject` inside `@PreAuthorize` expecting Spring to "predict" the result in advance.

Example:

~~~java
// Snippet inside a @Service.
@PreAuthorize("hasAuthority('report:read') and "
        + "@reportAccess.canRead(authentication, #p0)")
public Report findReport(long id) {
    return store.find(id).orElseThrow();
}

@PostAuthorize("returnObject.owner() == authentication.name")
public Report findReportAndCheckAfter(long id) {
    return store.find(id).orElseThrow();
}

@PostFilter("filterObject.owner() == authentication.name")
public List<Report> listVisibleReports() {
    return new ArrayList<>(store.findAll());
}
~~~

These snippets assume `Report`, `store`, and `reportAccess` exist in a Spring service; they are **not standalone runnable Java files**. `@PostAuthorize` and `@PostFilter` are post-checks and therefore do not prevent method side effects. For write/delete operations, prefer pre-checks alongside data-layer/transaction-level protection.

Names like `#reportId` depend on parameter name discovery (such as compiling with `-parameters` or supported annotations). This lesson uses `#p0` to avoid depending on Java parameter names. Authorization expressions can call Spring beans using `@beanName.method(...)`.

### 4.1. What does not "carry over" from the web root

Inside `@PreAuthorize` on a service, the following expressions **do not have the default meaning they have in web SpEL**:

~~~text
hasIpAddress('192.0.2.0/24')   // method specific to web root
request.method == 'POST'        // request is not an automatic variable of method root
request.requestURI              // HttpServletRequest is not automatically passed to method
~~~

Conversely, the web root does not automatically have `ReportService.findReport(id)`'s `#p0`, nor the service's `returnObject` or `filterObject`. Request path data may be supplied separately by an HTTP authorization manager/matcher, but that is not the same as the Java arguments of a method invoked later.

If a service policy needs an additional attribute, pass explicitly normalized data via method parameters or a policy bean (and validate data trustworthiness). Do not force services to depend on `HttpServletRequest` just to reuse URL expressions; background jobs will have no request.

## 5. Complete example: both web and method protecting reports

The following example exposes `GET /api/reports/{id}`. The **web layer** only checks the `report:read` authority; the **method layer** also requires the caller to own the report. Those are two distinct decisions.

In a Spring Boot Servlet project configured with Java 17+ and dependencies `spring-boot-starter-web` and `spring-boot-starter-security`, save the following as `src/main/java/demo/security/AuthorizationExampleApplication.java`. This is a **complete single-file Java example** (one `public` class and package-private types), requiring no database. The demo uses `{noop}` plaintext passwords **solely for learning**, never for production.

~~~java
package demo.security;

import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.expression.WebExpressionAuthorizationManager;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationExampleApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/reports/*")
                            .hasAuthority("report:read")
                        .requestMatchers("/internal/**")
                            .access(new WebExpressionAuthorizationManager(
                                    "hasAuthority('internal:read') and "
                                    + "hasIpAddress('192.0.2.0/24')"))
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}demo")
                        .authorities("report:read").build(),
                User.withUsername("bob").password("{noop}demo")
                        .authorities("report:read").build(),
                User.withUsername("visitor").password("{noop}demo")
                        .authorities("profile:read").build());
    }
}

record Report(long id, String owner, String title) {
}

@Component
class ReportStore {
    private final Map<Long, Report> data = Map.of(
            1L, new Report(1L, "alice", "Report A"),
            2L, new Report(2L, "bob", "Report B"));

    Optional<Report> find(long id) {
        return Optional.ofNullable(data.get(id));
    }
}

@Component("reportAccess")
class ReportAccess {
    private final ReportStore store;

    ReportAccess(ReportStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        return authentication != null
                && store.find(id)
                        .map(r -> r.owner().equals(authentication.getName()))
                        .orElse(false);
    }
}

@Service
class ReportService {
    private final ReportStore store;

    ReportService(ReportStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('report:read') and "
            + "@reportAccess.canRead(authentication, #p0)")
    public Report findReport(long id) {
        return store.find(id).orElseThrow(
                () -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Report not found"));
    }
}

@RestController
@RequestMapping("/api/reports")
class ReportController {
    private final ReportService service;

    ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Report findReport(@PathVariable long id) {
        return service.findReport(id);
    }
}
~~~

If the Boot application uses a standard Gradle setup, the required dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **dependencies block for a project that already applies the Spring Boot plugin and dependency management**, not a standalone `build.gradle` file. Start it using your project's runner (e.g., `./gradlew bootRun` with the Gradle wrapper on Unix; on Windows use `gradlew.bat bootRun`).

Send requests (once the app is running at `localhost:8080`):

~~~bash
curl -i -u alice:demo http://localhost:8080/api/reports/1
curl -i -u bob:demo http://localhost:8080/api/reports/1
curl -i -u bob:demo http://localhost:8080/api/reports/2
curl -i -u visitor:demo http://localhost:8080/api/reports/1
curl -i http://localhost:8080/api/reports/1
~~~

| Caller and URL | Web authorization | Method authorization | Expected HTTP result |
| --- | --- | --- | --- |
| Alice → `/api/reports/1` | PASS: has `report:read` | PASS: owner Alice | 200 and JSON for report ID 1 |
| Bob → `/api/reports/1` | PASS: has `report:read` | DENY: owner Alice | 403 |
| Bob → `/api/reports/2` | PASS: has `report:read` | PASS: owner Bob | 200 and JSON for report ID 2 |
| Visitor → `/api/reports/1` | DENY: missing `report:read` | Not invoked | 403 |
| Unauthenticated → `/api/reports/1` | Not authenticated | Not invoked | 401 with standard HTTP Basic |

Look closely at one key detail: Bob receives 403 on Alice's report **even though the URL rule allowed him through**. Therefore, if tests only verify HTTP matchers and skip the service, they do not prove data access authorization. Conversely, if a job invokes `ReportService.findReport(...)` through a Spring bean, the web filter does not run, yet `@PreAuthorize` can still run when method security is enabled with an appropriate security context.

In this example, non-existent reports are also denied by `ReportAccess.canRead` before the method body runs. That is a policy choice of the demo, **not a Spring Security requirement to return 403 instead of 404**. In real systems, design not-found vs. unauthorized handling consistently to prevent information leakage and match your API contract.

## 6. Standalone Java 17 illustration to verify decision order

The snippet below **does not emulate Spring Security or SpEL**; it simply models the combined semantics of the two check layers and compiles directly with JDK 17. Save as `ContextDecisionDemo.java`:

~~~java
public class ContextDecisionDemo {
    record HttpContext(String path, boolean hasReadAuthority) {}
    record MethodContext(long reportId, String user, String owner) {}

    static boolean webAllows(HttpContext request) {
        return request.path().startsWith("/api/reports/")
                && request.hasReadAuthority();
    }

    static boolean methodAllows(MethodContext call) {
        return call.user().equals(call.owner());
    }

    public static void main(String[] args) {
        boolean web = webAllows(
                new HttpContext("/api/reports/1", true));
        boolean method = methodAllows(
                new MethodContext(1L, "bob", "alice"));

        System.out.println("web=" + web);
        System.out.println("method=" + method);
        System.out.println("final=" + (web && method));
    }
}
~~~

~~~bash
javac --release 17 ContextDecisionDemo.java
java ContextDecisionDemo
~~~

Exact stdout:

~~~text
web=true
method=false
final=false
~~~

That is the difference between **permission to enter an HTTP route** and **permission to execute business logic on a specific resource**. The Spring Boot example in Section 5 implements this principle using a filter chain and AOP method security.

## 7. Testing both layers properly

With `spring-security-test` and `spring-boot-starter-test`, an integration test example (save as `src/test/java/demo/security/AuthorizationFlowTest.java`) is:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFlowTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void sameAuthorityAndOwnerPassesBothLayers() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:read")
    void webPassesButMethodDeniesOtherOwner() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "visitor", authorities = "profile:read")
    void webDeniesMissingAuthority() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithAnonymousUser
    void unauthenticatedRequestRequiresLogin() throws Exception {
        mvc.perform(get("/api/reports/1"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

This is an integration test using the Spring context and MockMvc, not a unit test invoking `new ReportService(...)` directly. With Spring AOP, **internal calls via `this.securedMethod()` generally bypass the proxy**, so annotations may not be applied; test through the actual Spring bean and production call path.

A useful QA matrix should also cover: a user who has URL access but not record access; another URL reaching the same service; calls from jobs/listeners outside HTTP; revoked permissions; async threads not propagating the security context; 401/403/404 responses per configuration; and protecting write operations before side effects.

## 8. Common misconceptions and how to fix them

### Misconception 1: "Both have `hasRole`, so the root is the same everywhere"

False. `hasRole` and `hasAuthority` belong to common operations, whereas the web root carries `request` and the method root carries the invocation. `hasRole('ADMIN')` checks authority `ROLE_ADMIN` under default configuration; `hasAuthority('ADMIN')` matches the exact string `ADMIN`. You need to know this in both places, and it does not mean the roots are identical.

### Misconception 2: "Method security automatically has `request`"

False in the default context. Especially when a service runs from a queue or scheduled task, there is no servlet request. Pass required policy data via service parameters or an explicitly managed policy bean; avoid relying on a thread-local HTTP request as a mandatory business dependency.

### Misconception 3: "Protecting the URL makes the service always safe"

Insufficient. The same service may be called from multiple endpoints or outside HTTP. Add `@PreAuthorize`/policies at the business boundary for resource-level permissions, especially multi-tenancy/ownership. Conversely, method security does not replace endpoint protection, CORS/CSRF, authentication, filter chains, and Servlet URL rules.

### Misconception 4: "`@PostAuthorize` runs before the service mutates data"

False. `@PostAuthorize` inspects the result after the invocation; if the method body sends email, triggers external transactions, or updates records, those side effects may already have happened. For updates/deletes, evaluate permissions before execution and enforce atomicity and conditions at the data layer.

### Misconception 5: "Copy the web SpEL string verbatim into `@PreAuthorize`"

There is no generic conversion like that. `request.method` and `hasIpAddress(...)` belong to web; `#p0`, `returnObject`, and `filterObject` belong to method. Rewrite policies using the data the target layer actually has. You can reuse **business policy beans** designed with explicit parameters, rather than blindly reusing every SpEL string.

### Misconception 6: "All `authorizeHttpRequests` rules use `WebSecurityExpressionRoot`"

False. `.hasRole(...)`, `.hasAuthority(...)`, and `.authenticated()` in the DSL are typically enforced by concrete `AuthorizationManager` implementations. Only when you opt into expression APIs (such as `WebExpressionAuthorizationManager`) does a web SpEL evaluation context exist. The modern direction is strongly typed managers for most web rules.

### Misconception 7: "HTTP 403 is guaranteed everywhere when a method denies access"

At the service layer, authorization failures raise an exception/denial outcome depending on the API. HTTP 401/403/404 depend on authentication, the filter chain, exception translation, and application handlers. Background invocations have no HTTP status code. Test HTTP status at the HTTP layer and exceptions at the service layer separately.

### Misconception 8: "`WebSecurityExpressionRoot` also applies to WebFlux"

This lesson covers **Servlet** with `HttpServletRequest`. Spring Security WebFlux uses a reactive pipeline and request context (`ServerWebExchange`), along with its own security APIs. Do not extrapolate Servlet's `WebSecurityExpressionRoot` directly to reactive authorization or equate `@EnableMethodSecurity` with `@EnableReactiveMethodSecurity`.

## 9. Policy design checklist

1. **Are you protecting a request or a method?** If it is a URL, use `SecurityFilterChain`/`AuthorizationManager`. If it is permission to act on data, use method security and/or policies in services/repositories.
2. **Where does the expression get its data?** `request`/IP on the web side; `#p0` and return object properties on the method side. Shared authentication checks do not erase context differences.
3. **Can the method be called from elsewhere?** Protect at the service boundary whenever business rules must always be enforced, even outside HTTP.
4. **Does the policy depend on owner/tenant/ACL?** Place checks where trustworthy data lives; for large queries, push permission predicates into the data layer rather than relying only on UI or URLs.
5. **Does the operation have side effects?** Check before writing; never expect post-checks to roll back automatically.
6. **Have you tested the combined flow?** Include cases where web passes but method denies, as well as cases where web denies before the method. Verify proxies, authentication, and HTTP status codes.

**Self-check:**

- `hasAuthority('report:read')` works in both web and method: why? → Because both have `Authentication` information and shared security operations.
- Is `hasIpAddress('192.0.2.0/24')` guaranteed to work in `@PreAuthorize`? → No; that operation belongs to the web root, and the method root does not provide it by default.
- Why does Bob pass `/api/reports/1` at the web layer yet still get 403? → Web only checks the HTTP route authority, while method also checks ownership of ID 1.
- If a job calls the service bean without going through the filter chain, which authorization can still apply? → Method authorization on calls going through the Spring proxy, given a valid security context.

## Official Documentation

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `AuthorizationManager`, migrating from SpEL expressions.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, method annotations, expressions, and method interception.
- [WebSecurityExpressionRoot API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/expression/WebSecurityExpressionRoot.html): `request` and `hasIpAddress`.
- [DefaultHttpSecurityExpressionHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/expression/DefaultHttpSecurityExpressionHandler.html): creating a web evaluation context from `RequestAuthorizationContext`.
- [DefaultMethodSecurityExpressionHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html): creating a method evaluation context from `MethodInvocation`.
