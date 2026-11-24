# AuthorizationManager for Custom Access Rules

In **Spring Security for Servlet**, authentication answers the question "who sent this request?"; **HTTP authorization** answers a different question: "is that identity allowed to access the resource at this URL and HTTP method?". Common rules such as `authenticated()`, `hasRole("ADMIN")`, or `hasAuthority("project:read")` are very useful, yet sometimes insufficient: a user may only view **their own** projects, an admin may only manage projects **within their own tenant**, or a request is accepted only if a trusted business condition holds.

`AuthorizationManager<T>` is Spring Security's abstraction for bringing those decisions into the authorization check flow. At the HTTP Servlet layer, the common context type is `RequestAuthorizationContext`; it provides the request along with path variables extracted from a compatible `RequestMatcher`. You can pass an `AuthorizationManager<RequestAuthorizationContext>` to `authorizeHttpRequests(...).requestMatchers(...).access(customManager)` to enforce custom rules while keeping authorization inside the Security Filter Chain.

Lesson objectives:

- Understand how `AuthorizationFilter`, `RequestMatcher`, `AuthorizationManager`, and `Authentication` work together.
- Know when to use built-in rules and when to write a custom manager.
- Write an HTTP rule for **project owner + tenant + tenant admin**, using server-side data rather than trusting client claims.
- Use `RequestAuthorizationContext.getVariables()` safely; **deny when variables are missing or invalid**, never guess.
- Distinguish 401, 403, and 404 outcomes, matcher order, multiple SecurityFilterChains, and CSRF.
- Design tests with Spring Security Test/MockMvc and a standalone Java 17 program with deterministic stdout.
- Recognize the limits of HTTP-only checks: service/method security, TOCTOU scenarios, mutable data, and non-HTTP execution paths.

Example scope: **Java 17+, Spring Boot 3.x, Spring Security 6.x with Servlet/MVC**. Newer Spring Security 6.x releases have shifted the API from `check(...)` toward `authorize(...)` and deprecated `check`; this article uses `check(...)` for broad comparison across many 6.x versions while explaining how to check signatures per version. Spring snippets require full dependencies; only the plain Java program in section 12 runs directly on JDK 17 without external libraries.

## 1. How Does Authentication Differ from Authorization?

A GET request for a project resource can pass through these steps:

~~~text
GET /api/projects/101
Authorization: Basic <credentials>
           |
           v
FilterChainProxy selects the first matching SecurityFilterChain
           |
           v
Authentication filter (e.g., BasicAuthenticationFilter)
           |-- AuthenticationManager + AuthenticationProvider
           |-- verifies password
           |-- authenticated Authentication with authorities
           |
           v
AuthorizationFilter
           |-- RequestMatcher: GET /api/projects/{projectId}
           |-- AuthorizationManager<RequestAuthorizationContext>
           |       |
           |       +-- principal verified by provider?
           |       +-- projectId from matcher?
           |       +-- project belongs to allowed tenant?
           |       +-- user owns project OR is admin in tenant?
           |       |
           |       +-- ALLOW -> request reaches controller
           |       +-- DENY  -> AccessDeniedException
           |
           v
ExceptionTranslationFilter / exception handling
           |-- missing authentication -> authentication entry point (typically 401)
           |-- authenticated but lacking permission -> typically 403
~~~

The diagram shows logical relationships, not an immutable guarantee of filter ordering when the framework is customized. When reaching `AuthorizationFilter`, Spring Security can supply a `Supplier<Authentication>` to retrieve authentication **lazily when needed**, instead of always forcing it upfront.

### Distinct Components

| Component | Role in the Decision |
| --- | --- |
| `Authentication` | Verified identity, authorities, state; result from provider |
| `HttpServletRequest` | Method/path/headers and request data that may carry client input |
| `RequestMatcher` | Defines which requests belong to the rule, and can extract URI template variables |
| `RequestAuthorizationContext` | Wraps the request and matcher variables for the HTTP authorization manager |
| `AuthorizationManager<T>` | Decides access based on `Authentication` and the protected target's context |
| `AuthorizationDecision` / `AuthorizationResult` | Grant/deny result depending on API version |
| `AuthorizationFilter` | Invokes the corresponding manager, allowing or blocking the request |
| `ExceptionTranslationFilter` | Translates security exceptions into 401/302/403 per entry point and access denied handler |
| `SecurityFilterChain` | Scope of security filters applied to a request, chosen via security matcher |

**Important:** having `ROLE_ADMIN` or being logged in does not automatically grant access to all resources. Authorization must still examine the **relationship between principal, resource, and tenant** per product policy.

## 2. From authorizeHttpRequests to AuthorizationManager

Simple rules:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("reports:read")
    .anyRequest().authenticated());
~~~

The `authorizeHttpRequests` DSL relies on `AuthorizationManager` for decisions. When a custom rule is needed:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/projects/{projectId}")
        .access(projectReadAuthorizationManager)
    .anyRequest().denyAll());
~~~

This is a **configuration fragment**, assuming `HttpMethod` and a `projectReadAuthorizationManager` bean already exist; section 6 has the complete version using an explicit MVC matcher to illustrate extracting the `projectId` variable.

### Why access(manager) Instead of permitAll?

`permitAll()` skips authority checks at that rule. If an application puts `permitAll()` on a project endpoint just so the controller can check permissions itself, every request can enter deep into code before proper verification, and it is easy to miss a branch. `access(manager)` lets us enforce permission checks **before the controller** at the selected URL.

However, HTTP checks **do not completely replace** service-layer authorization in applications with multiple service entry points (scheduled jobs, messaging, GraphQL, gRPC, or other APIs). Place business authorization close enough to data to prevent bypasses.

### Use Built-In Rules When Possible

Do not write a manager merely to check `authentication.get().isAuthenticated()` or a fixed role if the DSL already offers `authenticated()`/`hasRole(...)`. Custom managers add design, testing, operational cost, and potential data lookups. Use one when decisions genuinely depend on multiple factors or reusable policies.

## 3. The AuthorizationManager<RequestAuthorizationContext> Contract

In many Spring Security 6.x versions, an HTTP manager implementation takes the shape:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Core part of a class implementing AuthorizationManager<RequestAuthorizationContext>
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        RequestAuthorizationContext context) {

    // Decision must be computed from the verified identity
    // and actual server-side resource/attributes.
    boolean granted = false;
    return new AuthorizationDecision(granted);
}
~~~

This is a **fragment** to explain the signature, not a standalone compilable file. The full class is written in section 6.5. On newer Spring Security 6.x releases, `AuthorizationManager.authorize(...)` returns `AuthorizationResult` and `check(...)` may be deprecated. When upgrading libraries, consult the exact version's Javadoc, adjust the override method, and test; do not assume all 6.x releases share identical signatures.

### Why Use Supplier<Authentication>?

`Supplier<Authentication>` lets the framework defer looking up `Authentication` when a rule does not need it. For some built-in rules, this avoids unnecessary `SecurityContext` access. Inside a custom manager, call `authentication.get()` when identity/authorities are needed, and treat the result according to the `SecurityContext` contract.

**Never** use `request.getParameter("role")` or a client-supplied `X-User-Role` header as an authentication result. Permission info must come from a server-verified provider/identity. If the app relies on identity headers injected by a trusted reverse proxy, trusting those headers still requires a proper authentication mechanism for that architecture, not blindly reading client headers.

### Do Not Treat isAuthenticated() Alone as Enough

In Spring Security, `AnonymousAuthenticationToken` can have `isAuthenticated() == true` per token semantics. When coding custom rules, you must **distinguish anonymous from real authenticated users**, or use `AuthenticatedAuthorizationManager.authenticated()` / built-in managers where appropriate.

Example for a custom rule:

~~~java
if (auth == null ||
        !auth.isAuthenticated() ||
        auth instanceof AnonymousAuthenticationToken) {
    return new AuthorizationDecision(false);
}
~~~

This is a fragment inside a method that already holds `auth`. For other authentication types (remember-me, fully authenticated, MFA), decide the required identity assurance level. A sensitive permission may require **fully authenticated** rather than merely a remembered principal.

### Allow, Deny, and Abstain

An `AuthorizationDecision(true)` represents grant; `AuthorizationDecision(false)` is deny. Some interfaces/managers may return `null` per their contract to represent abstaining, especially when composing multiple managers. In a custom rule protecting an endpoint, the safe choice is **explicit deny** when missing authentication, path variables, records, or policy data, rather than returning `null` hoping another manager will block it.

**Fail closed** is the principle: if authorization data is insufficient or untrusted, do not grant access. On system failures you may return an error rather than turning every failure into "not found", and never `catch (Exception) { return allow; }`.

## 4. RequestAuthorizationContext and Path Variables

A typical endpoint:

~~~text
GET /api/projects/101
GET /api/projects/102
GET /api/projects/201
~~~

The rule is declared with a URL template:

~~~java
"/api/projects/{projectId}"
~~~

When the `RequestMatcher` supports variable extraction, `RequestAuthorizationContext.getVariables()` can return a map such as:

~~~text
{projectId=101}
~~~

This is an **illustrative result** for `/api/projects/101`, not data from a client HTTP header. The value `101` is still **untrusted input**: parse/validate it, then use it as a key to look up the record in server-side data. Never let clients self-assert "this project belongs to me".

### Why Is an Explicit Matcher Needed?

In Spring Security Servlet with Spring MVC, `MvcRequestMatcher` can use `HandlerMappingIntrospector` to match paths the MVC way, including URI template variables. Some setups use `AntPathRequestMatcher`, `PathPatternRequestMatcher`, or custom matchers; **not every matcher returns variables under the expected names**. Never write code depending on `context.getVariables().get("projectId")` while pairing it with a matcher that extracts no variables.

Example in a Spring MVC configuration:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(handlerMappingIntrospector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        mvc.pattern(HttpMethod.GET, "/api/projects/{projectId}"))
        .access(projectReadAuthorizationManager)
    .anyRequest().denyAll());
~~~

`handlerMappingIntrospector` is the `HandlerMappingIntrospector` bean created by Spring MVC, used in the appropriate web application context. Spring Security 6.5+ also introduces newer matcher APIs; check your application's exact version and servlet mapping. If `DispatcherServlet` uses a custom servlet path, configure the matcher accordingly so routes do not mismatch.

### Do Not Parse Numbers Carelessly

The `projectId` input may be absent, empty, malformed, negative, too large for `long`, or unusually encoded. Safe procedure:

1. Check that the variable exists under the exact name.
2. Validate format with a reasonable length bound.
3. Parse inside `try/catch(NumberFormatException)`.
4. Verify the resource exists and belongs to the tenant using server data.
5. Deny if any fact is missing; never fall back to a default ID.

**Do not** fall back to parsing an ID from another query parameter if the matched route is supposed to have no ID. Ambiguous fallbacks create alternate paths into resources that bypass reviewed policies.

## 5. Sample Problem: Owner + Tenant + Tenant Admin

We build a project-read rule:

- Alice belongs to tenant `north` and owns project 101.
- Bob belongs to tenant `north` and owns project 102.
- Carol belongs to tenant `south` and owns project 201.
- Admin belongs to tenant `north` and has `ROLE_ADMIN`.
- Regular users may view only **their own** projects within their tenant.
- Admins may view any project **within their own tenant**, never across tenants.
- Non-existent projects and incomplete policy data **must not be permitted**.
- User/tenant/role come from server authentication or trusted stores, **never** from `X-Tenant`/`role` in the request.

### Decision Table

| User | User's Tenant | Resource | Resource Tenant / Owner | Expectation |
| --- | --- | --- | --- | --- |
| alice | north | 101 | north / alice | **Allow** |
| alice | north | 102 | north / bob | **Deny** |
| bob | north | 102 | north / bob | **Allow** |
| admin (ROLE_ADMIN) | north | 101 | north / alice | **Allow** |
| admin (ROLE_ADMIN) | north | 201 | south / carol | **Deny** |
| carol | south | 201 | south / carol | **Allow** |
| alice | north | 999 | Does not exist | **Deny** |
| Anonymous | unknown | 101 | north / alice | **Deny** |

Core Boolean rule:

~~~text
ALLOW = authenticatedRealUser
        AND projectExists
        AND trustedUserTenant == projectTenant
        AND (trustedUsername == projectOwner OR has ROLE_ADMIN)
~~~

The `AND/OR` operators express logical conditions. **Wrapping the tenant check outside the admin branch** is vital: writing `(sameTenant AND owner) OR admin` by mistake lets admins read across every tenant — a classic flaw when combining multiple conditions.

### Why Choose GET /api/projects/{projectId}?

It is a request needing access control before the controller with a clear URI variable. POST/PUT/DELETE methods may need different policies; **never infer write or delete permissions from GET permission**. In the example, only GET matches the custom rule; other requests hit `denyAll()`.

## 6. Spring Boot 3 + Security 6 Implementation

This is a **structurally complete illustrative demo app**, using HTTP Basic authentication for easy testing and immutable in-memory project data to stay focused on `AuthorizationManager`. It is not meant as a production user or project storage design. All files belong to package `com.example.authz`.

### 6.1. Maven Dependencies

In a Spring Boot 3.x project with a compatible parent/BOM and build plugin, `pom.xml` needs:

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

These dependencies inherit versions from the Spring Boot BOM. Do not manually mix mismatched Spring Security versions. Java 17 or newer must be the active toolchain. `MvcRequestMatcher`, `AuthorizationManager.check(...)`, and the test imports below are written for the Spring Security 6.x family; check for changes/deprecations in your actual minor version.

### 6.2. Startup Class

Create `src/main/java/com/example/authz/AuthorizationDemoApplication.java`:

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

### 6.3. Trusted Data/Policy Service

Create `src/main/java/com/example/authz/ProjectAccessService.java`:

~~~java
package com.example.authz;

import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;

public final class ProjectAccessService {

    public record Project(long id, String tenant, String owner) {}

    // IMMUTABLE data for demo; in practice loaded from a tenant-partitioned DB.
    private final Map<Long, Project> projects = Map.of(
        101L, new Project(101L, "north", "alice"),
        102L, new Project(102L, "north", "bob"),
        201L, new Project(201L, "south", "carol")
    );

    // In production, tenant comes from the verified principal
    // and a trusted identity/tenancy store, never from an arbitrary header.
    private final Map<String, String> userTenants = Map.of(
        "alice", "north",
        "bob", "north",
        "carol", "south",
        "admin", "north"
    );

    public Project find(long id) {
        return projects.get(id);
    }

    public boolean mayRead(Authentication authentication, long id) {
        if (authentication == null ||
                !authentication.isAuthenticated() ||
                authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        Project project = projects.get(id);
        if (project == null) {
            return false; // Deny non-existent resources.
        }

        String trustedTenant = userTenants.get(authentication.getName());
        if (trustedTenant == null ||
                !trustedTenant.equals(project.tenant())) {
            return false; // Even admins cannot cross tenants.
        }

        boolean isOwner = project.owner().equals(authentication.getName());
        boolean isAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return isOwner || isAdmin;
    }
}
~~~

Why place logic in a service instead of writing everything inside the manager? Because the same business policy may need standalone testing, reuse across other call sites, and easy replacement of the data source with a database. Still, **service-layer permissions must also be enforced on every code path needing protection**, not merely sit as an uncalled helper.

Note: `userTenants` in the example is a server-side map illustrating the relationship. In production, the tenant normally resides in the verified principal, a membership store, or an identity system; handle overlapping usernames across tenants using immutable identifiers/multi-tenant IDs rather than using `getName()` as a primary key if it is not globally unique.

### 6.4. Custom HTTP Rule: ProjectReadAuthorizationManager

Create `src/main/java/com/example/authz/ProjectReadAuthorizationManager.java`:

~~~java
package com.example.authz;

import java.util.Map;
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ProjectReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ProjectAccessService projects;

    public ProjectReadAuthorizationManager(ProjectAccessService projects) {
        this.projects = projects;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        // Matcher did not provide URI variable -> fail closed.
        Map<String, String> variables = context.getVariables();
        String rawId = variables == null ? null :
                variables.get("projectId");

        // Accept only positive decimal integers with bounded length.
        if (rawId == null ||
                !rawId.matches("[1-9][0-9]{0,17}")) {
            return new AuthorizationDecision(false);
        }

        final long id;
        try {
            id = Long.parseLong(rawId);
        } catch (NumberFormatException exception) {
            return new AuthorizationDecision(false);
        }

        Authentication user = authentication.get();
        boolean allow = projects.mayRead(user, id);
        return new AuthorizationDecision(allow);
    }
}
~~~

Key points to understand:

1. `RequestAuthorizationContext.getVariables()` depends on the matcher. If `projectId` is missing, deny; **never** allow all.
2. The pattern `[1-9][0-9]{0,17}` only illustrates positive numeric IDs without leading zeros up to 18 digits. For UUIDs, adjust parser/validation. Never use regex as your sole authorization mechanism.
3. `authentication.get()` fetches `Authentication` from the Spring Security context; the manager does not invoke login or `PasswordEncoder` itself.
4. `ProjectAccessService.mayRead(...)` inspects **server-side** records and tenants.
5. `AuthorizationDecision(false)` causes `AuthorizationFilter` to block before the controller runs. It does not call `response.sendError(403)` directly from the manager; exception translation and entry points decide the HTTP response.
6. The manager is an object shared concurrently across requests. Never store "currentUser/currentProject" in singleton fields, avoiding cross-thread data leaks.
7. If the database fails, enforce **fail closed**. Never catch all exceptions and return `true`. For data store failures you may return an appropriate service error via error handling, yet **never** grant access by default.

This class uses the `check(...)` API style common in Spring Security 6.x. If your newer library version provides `authorize(Supplier<? extends Authentication>, T)` and flags deprecation, update to the Javadoc-supported signature and re-run tests without changing the underlying condition semantics.

### 6.5. SecurityFilterChain and HTTP Matchers

Create `src/main/java/com/example/authz/SecurityConfig.java`:

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-demo-only"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-demo-only"))
                .roles("USER").build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-demo-only"))
                .roles("USER").build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .roles("ADMIN").build()
        );
    }

    @Bean
    ProjectAccessService projectAccessService() {
        return new ProjectAccessService();
    }

    @Bean
    ProjectReadAuthorizationManager projectReadAuthorizationManager(
            ProjectAccessService projects) {
        return new ProjectReadAuthorizationManager(projects);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector,
            ProjectReadAuthorizationManager projectRead) throws Exception {

        // MVC matcher extracts the {projectId} variable for matching requests.
        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern(
                    HttpMethod.GET, "/api/projects/{projectId}"))
                    .access(projectRead)
                // Do not open any URLs outside the demonstration scope.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Read-only GET requires no CSRF token.
        // Do not disable CSRF globally: POST/PUT/DELETE still need their own policy.
        return http.build();
    }
}
~~~

In this example:

- HTTP Basic is used **purely for testing**, not as advice to use Basic auth with long-lived credentials for every SPA. Production needs HTTPS, login throttling, proper MFA/identity architecture, and never storing credentials insecurely on clients.
- Only `GET /api/projects/{projectId}` routes to the custom manager. `GET /api/projects` or `DELETE /api/projects/101` are not automatically permitted.
- `anyRequest().denyAll()` ensures undeclared paths are never accidentally permitted.
- Configuration preserves default CSRF. GET is not a state-changing operation; if a GET controller performs side effects, the HTTP design itself is flawed.
- `MvcRequestMatcher.Builder` uses MVC infrastructure; if a project lacks Spring MVC, use a Servlet-stack-compatible matcher and verify path variable support.
- In apps using `DispatcherServlet` under a custom servlet path, handle servlet path/lookup path explicitly rather than concatenating URL strings by guesswork.

**There is no `permitAll("/api/projects/**")`** in front of the custom rule. If a broader matcher sits earlier and matches the request, the detailed rule may never execute because rule selection prioritizes the first matching rule in the list.

### 6.6. Controller Does Not Grant Extra Permissions

Create `src/main/java/com/example/authz/ProjectController.java`:

~~~java
package com.example.authz;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProjectController {
    private final ProjectAccessService projects;

    public ProjectController(ProjectAccessService projects) {
        this.projects = projects;
    }

    @GetMapping("/api/projects/{projectId}")
    public Map<String, Object> getProject(@PathVariable long projectId) {
        ProjectAccessService.Project p = projects.find(projectId);
        if (p == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Project not found");
        }

        return Map.of(
            "id", p.id(),
            "tenant", p.tenant(),
            "owner", p.owner());
    }
}
~~~

If a GET request targets Alice's project 101, the manager allows it and the controller returns the record from memory. If Alice tries to read Bob's project 102, the manager denies **before the controller runs**. With immutable in-memory data, the service and controller see the same record.

**Critical limitation:** in a production database, a record can change owner/tenant **between** the manager check and the controller loading data. This is a time-of-check/time-of-use (TOCTOU) issue. Do not treat the code above as a complete consistency example for multi-user updates. For mutable data, enforce permissions inside the same data-reading query/transaction or via service authorization with appropriate transactions and isolation.

### 6.7. Running the Demo and Observing Results

In a Spring Boot project created with the right version, run:

~~~bash
./mvnw spring-boot:run
~~~

Use a local test machine; you can invoke curl HTTP Basic with a password prompt rather than recording passwords in shell history:

~~~bash
# curl prompts for password; use demo accounts only.
curl -i -u alice http://localhost:8080/api/projects/101
curl -i -u alice http://localhost:8080/api/projects/102
curl -i -u admin http://localhost:8080/api/projects/201
~~~

Expected results when entering the corresponding password:

- Alice -> project 101: HTTP **200**, JSON containing `id=101`, `tenant=north`, `owner=alice`.
- Alice -> project 102: HTTP **403** because same tenant yet not owner and no `ROLE_ADMIN`.
- Admin (north) -> project 201 (south): HTTP **403** despite `ROLE_ADMIN`, blocked by the tenant boundary.
- An unauthenticated request to project 101 typically receives **401** with an HTTP Basic challenge rather than assuming the user is Alice.
- Authenticated GET for non-existent project 999: the demo rule denies, typically 403; real products may choose 404 to hide existence, yet do not predict responses from the controller since the controller may never execute.

Note: in production, Basic credentials must always be sent over **HTTPS**, never plain HTTP. Localhost commands are strictly for a trusted demo environment.

## 7. Testing with MockMvc and Spring Security Test

An authorization test suite must not only unit-test `mayRead(...)`. It must ensure the rule is wired to the **right `SecurityFilterChain`, right method, right URL variable**, yielding accurate 200/403/401 responses. With `spring-security-test` you can send real HTTP Basic through `MockMvc`.

Create `src/test/java/com/example/authz/ProjectAuthorizationIntegrationTest.java`:

~~~java
package com.example.authz;

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
class ProjectAuthorizationIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void ownerCanReadOwnProject() throws Exception {
        mvc.perform(get("/api/projects/101")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void sameTenantButNotOwnerIsDenied() throws Exception {
        mvc.perform(get("/api/projects/102")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadWithinOwnTenantOnly() throws Exception {
        mvc.perform(get("/api/projects/102")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/projects/201")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void southTenantOwnerCanReadSouthProject() throws Exception {
        mvc.perform(get("/api/projects/201")
                .with(httpBasic("carol", "carol-demo-only")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/projects/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownProjectNeverGetsAllowed() throws Exception {
        mvc.perform(get("/api/projects/999")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void malformedIdNeverGetsAllowed() throws Exception {
        mvc.perform(get("/api/projects/not-a-number")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unmatchedUrlIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "alice-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Assertions assume the exact configuration, matcher version, and test classpath from section 6. Systems with custom entry points, API error handlers, or container mappings may return different status codes; verify the actual flow rather than treating fixed statuses as a universal contract.

**Note:** `malformedIdNeverGetsAllowed` depends on `MvcRequestMatcher` matching a string path segment and placing the variable into the context before MVC binds `@PathVariable long`. If the manager fails closed, it denies right before the controller. If the custom matcher does not match, `anyRequest().denyAll()` also denies; both block the request, while unit-testing the manager confirms which branch ran.

### More Important Test: Proving the Manager Actually Runs

A 403 status can come from `anyRequest().denyAll()` or from CSRF/another exception, **not proving** the custom rule received the `projectId` variable. To verify wiring tightly:

- Directly unit-test `ProjectReadAuthorizationManager.check(...)` with `RequestAuthorizationContext(request, Map.of("projectId","101"))` and a valid `Authentication`.
- In integration tests, the case where Alice **is allowed** to read 101 is crucial because if the matcher/manager failed to run, `denyAll()` would reject it.
- Test path variables 101, 102, 201, and other methods/routes.
- Verify an authenticated request lacking permission gets 403, and an unauthenticated request hits the authentication entry point.
- If using `@WithMockUser` for authorization tests, note that the annotation **does not test HTTP Basic/`PasswordEncoder`**. It fits policy tests needing a fake authenticated principal; to test the real flow, use `httpBasic`/`formLogin` credentials as shown.

### Unit Test for the Manager

A server-independent fragment can construct the context:

~~~java
// Fragment in a JUnit test already holding ProjectReadAuthorizationManager manager.
MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/projects/101");
RequestAuthorizationContext context =
        new RequestAuthorizationContext(
            request, java.util.Map.of("projectId", "101"));

Authentication user = new UsernamePasswordAuthenticationToken(
    "alice", "ignored", java.util.List.of(
        new SimpleGrantedAuthority("ROLE_USER")));

AuthorizationDecision decision = manager.check(() -> user, context);
assertTrue(decision != null && decision.isGranted());
~~~

Spring Test, Spring Security, and JUnit imports must be added; this is a fragment, not a complete test file. The 3-argument `UsernamePasswordAuthenticationToken` in the unit test represents a **simulated authenticated `Authentication`** for isolated rule testing, not a token built from a real production HTTP request. Never copy this trusted token creation into HTTP converters.

## 8. HTTP Rule Ordering: Specific First, Broad Later

A serious configuration mistake:

~~~java
// WRONG: general matcher can match before specific matcher.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/projects/{projectId}").access(projectRead)
    .anyRequest().denyAll());
~~~

When `/api/**` matches first, project requests may bypass the manager depending on first-match selection. Placing a narrow matcher later **cannot fix** an earlier broad `permitAll`.

How to structure it:

~~~java
// Specific rule first, deny fallback.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/projects/{projectId}")
        .access(projectRead)
    .anyRequest().denyAll());
~~~

The snippets above are fragments, not the selection order across all security matcher types. Spring Security also has an independent **`SecurityFilterChain` selection** layer:

~~~text
FilterChainProxy
  |-- chain #1 securityMatcher("/api/**")  -> API filters/rules
  |-- chain #2 securityMatcher("/**")      -> Web filters/rules
  |
  +-- Request is handled ONLY by the first matching SecurityFilterChain
~~~

If a request enters chain #1, `authorizeHttpRequests` rules in chain #2 **will not run**. Therefore manage both matcher levels separately:

1. **`securityMatcher`** / `@Order` selects the chain.
2. **`requestMatchers`** inside `authorizeHttpRequests` selects the rule within that chain.

Inspect the filter chain list and app-wide fallback policy. Do not mistake `securityMatcher("/api/**")` for automatically protecting non-API endpoints: if no chain matches, a request may go unprotected by Spring Security contrary to your assumption.

### HTTP Method and Dispatcher Type

- **GET** permission does not automatically allow **POST/PUT/PATCH/DELETE**.
- CSRF is a defense against cross-site requests in architectures needing CSRF; it **differs from authorization**. A POST with a valid CSRF token can still be denied by business permissions.
- Servlet requests can have dispatcher types like `REQUEST`, `FORWARD`, and `ERROR`. If the app gets 403 on error dispatches, inspect dispatcher configuration and policy rather than blindly enabling `permitAll` for all internal paths.
- A controller may be mapped to multiple URLs or aliases. Policies must cover **all routes** reaching protected operations.

## 9. 401, 403, and 404: Choosing Meaningful Responses

For the project GET policy:

| Scenario | Core Decision | Typical HTTP |
| --- | --- | --- |
| No credentials on protected endpoint | Unauthenticated | 401 HTTP Basic; form login may 302 redirect |
| Wrong Basic password | Authentication failed | 401 per entry point |
| Authenticated Alice reads Bob's project | Authorization deny | 403 |
| North admin reads South project | Authorization deny due to tenant | 403 |
| Non-existent project 999 | Demo rule denies before controller | 403 in example, does not automatically become 404 |
| Controller finds entity then rejects per another policy | Depends on enforcement point | 403/404 per app contract |
| Request violates CSRF before authorization | Blocked by CSRF filter | 403, does not prove custom manager ran |

Some products intentionally return 404 instead of 403 for out-of-scope resources to avoid leaking existence. Do not simply throw `ResponseStatusException(404)` inside a custom manager expecting `ExceptionTranslationFilter` to handle it identically to an authorization failure. Define an explicit contract and error translation point, and test existence-hiding across controllers/services and other API routes.

**A correct deny does not automatically mean good UX.** A manager may return false when a data service is temporarily failing; users see 403 and mistakenly think "no permission". In production, distinguish system errors from policy denials, while **never failing open** just to preserve availability.

### Role Prefixes and Authorities

In Spring Security, `hasRole("ADMIN")` normally checks the `ROLE_ADMIN` authority. In the example service, we match the `"ROLE_ADMIN"` string from `getAuthorities()`. If a project has a custom role prefix, custom user mapper, or OAuth scopes like `SCOPE_project.read`, you cannot assume fixed strings blindly. Establish identity from provider-verified `Authentication`, then apply server policies.

## 10. Trust Boundary: Never Take Permissions from Client Input

A classic mistake:

~~~java
// NEVER: Clients can forge headers and claim permissions.
boolean allow = "ADMIN".equals(
    context.getRequest().getHeader("X-Role"));
return new AuthorizationDecision(allow);
~~~

The problem is not `RequestAuthorizationContext`, but the data source. HTTP headers, query parameters, JSON bodies, path variables, and cookies can all be crafted by clients. They may **identify which resource is requested**, yet cannot be trusted to prove the user owns that resource or belongs to that tenant.

### Right: Use Server-Verified Information

A manager may read:

- `authentication.get().getName()` or an immutable principal ID verified by the provider.
- `authentication.get().getAuthorities()` from a trusted identity source.
- Confirmed tenant membership from the server-side principal/DB.
- Resource owner/ACL/organization loaded from the database.
- Time-based policies, account status, or server-known business conditions (when reliable and explicitly designed).

### Tenant Boundary Must Wrap Admin Permissions

Dangerous expression:

~~~text
(sameTenant AND isOwner) OR isAdmin
~~~

It lets any admin bypass the tenant check. In our example, the right rule is:

~~~text
sameTenant AND (isOwner OR isAdmin)
~~~

If a resource supports multiple owners, group memberships, or shared access, extend the permission clause using server-side data; never weaken the tenant boundary for the convenience of a UI screen.

### Protecting Against IDOR/BOLA

**Insecure Direct Object Reference** / **Broken Object Level Authorization** occurs when an API takes an object ID and returns data without verifying the object falls within the user's scope. Requiring only `authenticated()` on `GET /api/projects/{id}` is **not enough** for object-level authorization. `AuthorizationManager` can enforce checks before the controller, while services also need protection if called from elsewhere.

## 11. Performance, Database Access, and Consistency

### 11.1. Managers Should Be Small and Hold No Mutable Per-Request State

An `AuthorizationManager` bean is usually created once and shared across concurrent requests. Never declare:

~~~java
// AVOID: shared mutable fields holding per-request data.
private String currentUser;
private Long currentProjectId;
~~~

If a handler uses fields while multiple threads read/write concurrently, permission data can leak and produce wrong decisions. Use **local variables** inside `check(...)`, stateless services, and thread-safe repositories.

### 11.2. How Many Times Should the Resource Be Loaded?

In the example, the manager loads the record to authorize, and the controller loads it again to build the response. With an immutable map this is negligible; with a database it adds queries and opens a TOCTOU window. Design alternatives:

- Have the service method load the object constrained by tenant/owner in the same query, e.g., `WHERE id = ? AND tenant_id = ? AND owner_id = ?`, returning data only if found. Admin queries still constrain tenant.
- Check permissions inside an application service under appropriate transaction/isolation, not only at the filter layer.
- When the manager loads metadata, use a projection containing only fields needed for authorization, avoiding N+1 queries.
- Policy/resource metadata can be cached if permissions rarely change and cache invalidation is designed; never let caches serve dangerously stale permissions.
- With an external PDP (policy decision point), enforce timeouts/circuit breakers and **fail closed** when permissions cannot be determined.

**Never stash whole entities containing sensitive fields into request attributes** just for controller reuse if they could leak via logs/tracing/filters. If reuse is needed, use explicit object scoping and review transaction boundaries.

### 11.3. Data Consistency and Concurrent Permission Changes

Scenario:

1. Alice sends `GET /api/projects/101`; the manager sees Alice is the owner.
2. An admin changes the owner of 101 to Bob.
3. The controller loads 101 and returns data even though Alice is no longer the owner.

This is TOCTOU. For mutable records with strict security requirements, place the check and data access under the same consistency control, or use queries returning only records permitted at read time, policy versioning/optimistic locking, or proper transactions. Filter-level checking alone does not solve this.

### 11.4. Remote Authorization Latency

If every GET calls an external policy service, endpoint latency and availability depend on that service. Consider bounded caching, PII-safe tracing, timeouts, controlled retries, circuit breakers, and **deny** or service-unavailable fallbacks per contract. Never return allow "to avoid disrupting UX" when permissions cannot be verified.

## 12. Standalone Java 17: Modeling the Owner + Tenant Policy

Before working with Spring Security, we can self-verify the **business logic** with a JDK 17 program using only records and maps. It does **not** verify passwords, create a `SecurityContext`, read Servlet requests, or replace framework filters. It only models the Boolean policy.

Save `ProjectAccessPolicyDemo.java`:

~~~java
import java.util.Map;

public class ProjectAccessPolicyDemo {
    record User(String name, String tenant, boolean admin) {}
    record Project(long id, String tenant, String owner) {}

    static boolean canRead(User user, Project project) {
        if (user == null || project == null) {
            return false;
        }
        if (!user.tenant().equals(project.tenant())) {
            return false;
        }
        return user.admin() || user.name().equals(project.owner());
    }

    static String decision(User user, long projectId,
                           Map<Long, Project> projects) {
        return canRead(user, projects.get(projectId)) ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Map<Long, Project> projects = Map.of(
            101L, new Project(101L, "north", "alice"),
            102L, new Project(102L, "north", "bob"),
            201L, new Project(201L, "south", "carol")
        );

        User alice = new User("alice", "north", false);
        User admin = new User("admin", "north", true);
        User carol = new User("carol", "south", false);

        System.out.println("alice 101 -> " +
            decision(alice, 101L, projects));
        System.out.println("alice 102 -> " +
            decision(alice, 102L, projects));
        System.out.println("admin 102 -> " +
            decision(admin, 102L, projects));
        System.out.println("admin 201 -> " +
            decision(admin, 201L, projects));
        System.out.println("carol 201 -> " +
            decision(carol, 201L, projects));
        System.out.println("alice 999 -> " +
            decision(alice, 999L, projects));
    }
}
~~~

Run with **JDK 17+** from the directory containing the file:

~~~bash
javac ProjectAccessPolicyDemo.java
java ProjectAccessPolicyDemo
~~~

**Exact** stdout:

~~~text
alice 101 -> ALLOW
alice 102 -> DENY
admin 102 -> ALLOW
admin 201 -> DENY
carol 201 -> ALLOW
alice 999 -> DENY
~~~

What the program demonstrates:

- Alice cannot view project 102 despite being in the same tenant because she is not the owner.
- Admin can view project 102 in tenant north.
- Admin cannot cross into tenant south.
- Carol can view data she owns herself.
- Non-existent projects lead to deny.
- No line of code "grants permission" based on a client-asserted project ID.

**Limitation:** this program is only a pure-Java policy test; in a real system, `User` must come from a trusted identity provider, `Project` from server data, and HTTP rules must be bound to the right route/chain. Never construct `new User("admin",...,true)` from a JSON request and grant access.

## 13. HTTP AuthorizationManager vs. Method Security

HTTP authorization fits when:

- Rules depend on HTTP method/path.
- Blocking before the controller is needed.
- The URL template already identifies the resource and metadata suffices to check.
- Centralizing network access rules in `SecurityFilterChain`.

Method security fits when:

- Services are called from multiple paths, not only HTTP.
- Domain objects need checking after being loaded.
- Read/write policies depend on business arguments not fully expressed in the URL.
- All callers of a service must obey the same policy.

Spring Security can enable method security via `@EnableMethodSecurity` and annotations like `@PreAuthorize`. A conceptual fragment:

~~~java
// Conceptual example: requires projectPolicy bean, parameter names, and method security.
@PreAuthorize("@projectPolicy.mayRead(authentication, #projectId)")
public Project findForUser(long projectId) {
    // Service must ensure consistency with returned data.
    return repository.findById(projectId)
        .orElseThrow();
}
~~~

This is **not** a runnable class: `projectPolicy`, `repository`, imports, bean wiring, and method-security config must be provided by the project. `#projectId` requires parameter-name metadata or explicit parameter naming per framework mechanics. `@PreAuthorize` also relies on proxy interception; self-invocation does not necessarily pass through the proxy.

Both security layers **can complement each other**. Do not skip service checks just because an HTTP manager exists if services have other call paths; and do not leave the entire HTTP API at `permitAll()` just because method security exists.

### Comparison with AuthorizationManager<MethodInvocation>

`AuthorizationManager` is generic; `RequestAuthorizationContext` is specifically the context type **for HTTP requests**. Spring Security also provides authorization managers for method invocations and method return objects. You cannot arbitrarily pass an `AuthorizationManager<RequestAuthorizationContext>` where `AuthorizationManager<MethodInvocation>` is required without an appropriate adapter.

### Choosing a Single Unified Business Policy Source

A maintainable structure:

~~~text
ProjectPolicyService (business authorization)
       |
       +-- HTTP ProjectReadAuthorizationManager -> guards endpoint
       |
       +-- Method security adapter / service-level check
       |
       +-- Unit tests of the policy itself
~~~

In large systems, avoid duplicating the same tenant/owner expressions across multiple classes and letting them drift. Policies should have one trusted definition of data and rules, with adapters merely translating context and surfacing failures per protocol.

## 14. Composing Rules: allOf, anyOf, and Abstain

Spring Security provides built-in authorization managers for roles, authenticated status, and composing multiple conditions; exact APIs depend on version. Logical meaning:

~~~text
All conditions required:   allOf(A, B, C)
Only one condition needed: anyOf(A, B, C)
~~~

Do not confuse `allOf` with `anyOf` in multi-tenant contexts. For example:

~~~text
ALLOWED = sameTenant AND (owner OR tenantAdmin)
~~~

Must not turn into:

~~~text
ALLOWED = (sameTenant AND owner) OR globalAdmin
~~~

unless the product genuinely has a **global admin** role with clearly separated scope. If using `AuthorizationManagers.allOf(...)`/`anyOf(...)`, check generic types and behavior when a manager returns null/abstains in your specific version. In sensitive policies, return explicit decisions and test every combination to prevent null branches from granting unexpected access.

A rule can be written as a short lambda for simple conditions:

~~~java
// Fragment: suitable only if you truly do not need a service or large logic.
.access((authentication, context) -> {
    boolean allow = authentication.get().getAuthorities().stream()
        .anyMatch(a -> "project:read".equals(a.getAuthority()));
    return new AuthorizationDecision(allow);
})
~~~

This depends on the corresponding generic manager API inside `requestMatchers(...).access(...)`. It checks a global authority; it does **not** handle ownership/tenant like the main example. When rules grow complex, move logic into a dedicated class/service for testing instead of hundred-line lambdas.

## 15. Common Mistakes When Writing HTTP AuthorizationManagers

| Mistake | Why Dangerous or Wrong | How to Fix |
| --- | --- | --- |
| Manager constructs a new `Authentication` from request | Clients can spoof identity, bypassing providers | Use framework-provided `Supplier<Authentication>` |
| Trusting `role=ADMIN` or `X-Tenant` from client | Self-granted privileges via untrusted input | Use server-side principal and stores |
| Using `isAuthenticated()` while forgetting anonymous tokens | Can treat anonymous as authenticated object-wise | Use built-in rules or distinguish token types properly |
| Returning `true` when DB errors occur | Fail-open, leaks data | Fail closed / service unavailable per policy |
| Returning `null` when project not found | May cause unintended abstain semantics | Explicitly deny when data is missing |
| Matcher omits `projectId`, manager allows by default | Bypasses object-level check | Inspect `getVariables()`, deny if missing |
| Placing `permitAll("/api/**")` before custom access | Specific rule may never run | Narrow rules first, `denyAll()` fallback |
| Checking only `hasRole("ADMIN")`, skipping tenant | Admin crosses tenants unintentionally | Wrap permission branches inside tenant boundary |
| Assuming a GET rule protects PUT/DELETE | Write endpoints may be exposed | Declare per-method and dedicated scopes |
| Testing only 403 across all URLs | May merely be hitting `denyAll()` | Test at least one allow case and exact path variables |
| Calling `response.sendError(403)` inside manager | Mixes decision with HTTP response | Return `AuthorizationDecision`; let exception handling respond |
| Storing `currentUser`/`currentId` in singleton manager | Race condition across concurrent requests | Use local variables and stateless services |
| Manager query and controller query see changing data | TOCTOU and stale authorization | Enforce inside appropriate data access/transaction |
| Assuming `/api` has only one chain | Another chain may match first | Check `securityMatcher`, `@Order`, and filter list |
| Assuming 403 always means manager denied | May be CSRF, other access denied, or error dispatch | Test response source and rule wiring |
| Using Bearer JWT yet inferring role from request JSON | Identity/claims unverified | Resource server must verify token/signature/claims |
| Omitting public endpoints from declarations | App breaks under full `denyAll` | Declare public routes explicitly before fallback |
| Skipping method-level checks when service has many callers | HTTP gate can be bypassed | Defend in service / method security |

## 16. Practice Exercises

**Exercise 1.** Alice has `ROLE_USER` and owns project 101; Bob also has `ROLE_USER` but owns project 102. Why is `hasRole("USER")` insufficient for `GET /api/projects/{id}`?

**Answer:** `ROLE_USER` only says Alice/Bob share a general role; it does not identify which object belongs to whom. Object-level authorization using server-side resource ID/owner/tenant is needed.

**Exercise 2.** The manager receives `context.getVariables().get("projectId") == null`. Should it allow the request because the matcher "must have matched"?

**Answer:** No. There is not enough data to identify the resource; deny or fail closed on misconfiguration. Verify the matcher supports URI variable extraction and variable names match.

**Exercise 3.** A manager reads `request.getHeader("X-Role")` and allows if equal to `ADMIN`. What can an attacker do?

**Answer:** Send the `ADMIN` header themselves and bypass checks. Roles must come from trusted `Authentication`/identity stores, never client-modifiable headers.

**Exercise 4.** Admin belongs to tenant north, project 201 belongs to south. Is `(sameTenant AND owner) OR isAdmin` safe?

**Answer:** No if admins may only operate inside their tenant. It lets admins bypass `sameTenant`. The right rule for the example is `sameTenant AND (owner OR isAdmin)`.

**Exercise 5.** A user without credentials accesses GET project 101 and gets 401; authenticated Alice accesses Bob's project and gets 403. How do these differ?

**Answer:** The first lacks valid authentication and can trigger the entry point; the second has an identity yet authorization denies. HTTP Basic/form login/custom entry point configuration determines the specific status or redirect.

**Exercise 6.** A developer places `requestMatchers("/api/**").permitAll()` before `GET /api/projects/{projectId}.access(projectRead)`. What is the risk?

**Answer:** The broad matcher matches first and can allow requests without invoking the custom manager. Put specific rules first and deny fallback per design.

**Exercise 7.** A user has permission for `GET /api/projects/101`. Does that mean they can `DELETE` the same URL?

**Answer:** No. Permissions must constrain method and business logic. The example rule covers GET only; DELETE does not match and hits `denyAll`.

**Exercise 8.** A test `GET /api/projects/999` returns 403. Does that prove `ProjectReadAuthorizationManager` works properly?

**Answer:** Not enough; `denyAll()` can also return 403. Testing Alice reading 101 for 200 and unit-testing the manager directly with variables proves the wiring.

**Exercise 9.** After the manager checks the owner, another request changes the owner in the database before the controller reads it. What issue is this?

**Answer:** TOCTOU. Ensure authorization matches the actual data returned at read time, using constrained queries or transaction/service-level enforcement.

**Exercise 10.** A background job calls `ProjectService.read(101)` without going through Servlet filters. Does the HTTP `AuthorizationManager` run automatically?

**Answer:** No. If the policy must apply outside HTTP, enforce it via service/method security or appropriate adapters; the HTTP manager is only one gate in the architecture.

**Exercise 11.** In a newer Spring Security 6 release, the IDE marks `AuthorizationManager.check(...)` deprecated. Must every custom `AuthorizationManager` be deleted immediately?

**Answer:** No. Check the exact Javadoc/version, migrate to `authorize(...)`/`AuthorizationResult` per supported API, preserve grant/deny semantics, and run tests. Deprecation does not automatically make code insecure, though a migration plan is needed.

**Exercise 12.** A manager's DB policy service call fails, and a developer returns `new AuthorizationDecision(true)` so the endpoint stays up. Is that acceptable?

**Answer:** No. If permission cannot be verified, access must not be granted. Handle system errors through an appropriate failure policy, while failing closed.

## 17. Checklist for Real Projects

- [ ] Identify the **request matcher, HTTP method, URL, and `SecurityFilterChain`** to protect; do not read the wrong chain.
- [ ] Start from `authenticated/hasRole/hasAuthority`; add a custom manager only when policy genuinely needs it.
- [ ] Choose `AuthorizationManager<RequestAuthorizationContext>` for HTTP Servlet and the appropriate context type at other layers.
- [ ] Use a `RequestMatcher` supporting URI variables if the manager needs `getVariables()`; deny when variables are missing/invalid.
- [ ] Principal/authorities/tenant membership must come from verified authentication and trusted server data.
- [ ] Wrap tenant checks **outside** owner/admin if admins cannot cross tenants.
- [ ] Deny when the resource does not exist, the user is anonymous, IDs are invalid, or policy data is incomplete.
- [ ] Keep managers stateless and thread-safe; never store request data in singleton fields.
- [ ] Place specific rules before broad matchers; end with an appropriate `denyAll()` fallback.
- [ ] Test 200 allow, 403 authenticated deny, 401/302 unauthenticated, and invalid methods/paths.
- [ ] Test at least one HTTP allow case to prove rules are not silently shadowed by `denyAll`.
- [ ] Separate authorization from CSRF, login, URL route binding, and exception translation.
- [ ] For mutable data, enforce authorization close to data retrieval/mutation, handling TOCTOU and transactions.
- [ ] Protect services called outside HTTP with appropriate method/service-level checks.
- [ ] Verify `check/authorize` API and matcher behavior on the active Spring Security 6.x version.
- [ ] Observe authorization metrics/audits safely without logging passwords, bearer tokens, session IDs, or sensitive data.
- [ ] Grant only with sufficient proof; never fall back to allow when data or auth services fail.

**Conclusion:** `AuthorizationManager<RequestAuthorizationContext>` is how **custom HTTP authorization rules** plug into `authorizeHttpRequests(...).access(...)` in Spring Security Servlet. Its strength lies in combining verified identity, matcher-classified request/path info, and **server-trusted** resource data. Enforce clear tenant/owner boundaries, fail closed, verify matcher and filter chain ordering, and add service-level checks when data is mutable or called from non-HTTP paths.