# AuthorityAuthorizationManager and AuthenticatedAuthorizationManager in Spring Security

## 1. The Problem: Granted Permissions and Authentication State Are Two Different Things

An application has the following APIs:

- `GET /api/reports`: only users with the `report:read` authority.
- `GET /api/admin`: only users with the `ADMIN` role.
- `GET /api/me`: anyone authenticated can view.
- `GET /api/sensitive`: requires **full** authentication, rejecting remember-me sessions.
- `GET /api/export`: requires both the `report:export` authority and full authentication.

These requirements are addressed by two policy groups with distinct meanings:

- **`AuthorityAuthorizationManager<T>`**: checks the `GrantedAuthority` entries inside `Authentication`, such as `report:read` or `ROLE_ADMIN`.
- **`AuthenticatedAuthorizationManager<T>`**: classifies the state of `Authentication`, such as anonymous, authenticated, remember-me, or fully authenticated.

Both implement the **`AuthorizationManager<T>`** interface in Spring Security. Using these built-in classes is often enough for role/authority and login-state requirements, whereas a policy depending on owner, tenant, record attributes, or business data may require an additional custom `AuthorizationManager`.

**Learning goals:** understand the authorization decision flow, distinguish roles from authorities and remember-me from fully authenticated, use the right factory methods, compose managers, integrate into `SecurityFilterChain`, write tests covering both allow and deny, and recognize the boundaries that neither manager checks.

This article uses **Spring Security 6.5.x** APIs, Java 17, and Spring Boot 3.5.x for the complete runnable example. Spring Security 7.x adds further factory utilities; do not assume every API appearing in a newer release exists in 6.5.

## 2. Foundation: What Data Does AuthorizationManager<T> Receive?

In a servlet application, the typical flow is:

```text
HTTP request
  → SecurityFilterChain
  → Authentication filter: extract/build Authentication
  → AuthorizationFilter
      → select the first rule matching the request
      → AuthorizationManager<RequestAuthorizationContext>
          → Supplier<Authentication>
          → RequestAuthorizationContext
          → AuthorizationResult: granted / denied
      → allow request to proceed or deny
  → Controller → Service
```

Spring Security does not force every application to build a new manager; when you write `.hasRole("ADMIN")` or `.authenticated()` in the `authorizeHttpRequests` DSL, the framework creates/wires the required authorization components. When you want to supply a manager explicitly, use `.access(AuthorizationManager)`.

The interface has a generic parameter `T` denoting **the object being authorized**. For a standard servlet request, `T` is `RequestAuthorizationContext`; for method authorization, `T` can be `MethodInvocation`. The two managers studied here **primarily inspect Authentication**, so they can be reused across different `T` types, though that does not mean they automatically inspect URLs, ownership, or method parameters.

In Spring Security 6.5, the preferred method when invoking directly is:

```java
AuthorizationResult result = manager.authorize(authenticationSupplier, object);
boolean allowed = result != null && result.isGranted();
```

This is an **API illustration snippet**; the manager, supplier, and object must share compatible types in a real program. `AuthorizationResult` has the `isGranted()` method. `AuthorizationManager#authorize(...)` was introduced in Spring Security 6.4; `check(...)` is deprecated in the 6.5 line. For managers that can abstain, the result may be `null`. These two built-in managers normally return an explicit allow/deny decision for a valid `Authentication`.

`Supplier<Authentication>` lets the framework **defer retrieving Authentication** until needed; do not call `supplier.get()` just to check a `permitAll` request. When writing a custom manager, never assume the target object already exposes the business attributes you want if type `T` does not provide them.

## 3. AuthorityAuthorizationManager: Checking GrantedAuthority

### 3.1. What Is GrantedAuthority?

An `Authentication` holds a collection of `GrantedAuthority` objects. Each authority typically has a string name, for example:

```text
User: alice
Authorities:
  ROLE_ADMIN
  report:read
  report:export
```

`GrantedAuthority#getAuthority()` is the value matched against. For example, `SimpleGrantedAuthority("report:read")` carries the exact string `report:read`. `AuthorityAuthorizationManager` does not query a permissions database or search JWT groups on its own; it inspects the **authorities already populated into Authentication** by an authentication provider, converter, or security setup.

Essential factory methods on `AuthorityAuthorizationManager`:

| Factory | Requirement | Example required authority |
|---|---|---|
| `hasAuthority("report:read")` | Has this exact authority | `report:read` |
| `hasAnyAuthority("read", "write")` | Has **at least one** of these authorities | `read` or `write` |
| `hasRole("ADMIN")` | With default factory, has role with `ROLE_` prefix added | `ROLE_ADMIN` |
| `hasAnyRole("ADMIN", "SUPPORT")` | Has at least one role with `ROLE_` added | `ROLE_ADMIN` or `ROLE_SUPPORT` |

Both `hasAnyAuthority` and `hasAnyRole` represent **OR**, not requiring all listed permissions. To express AND, use `AuthorizationManagers.allOf(...)` or a dedicated policy.

### 3.2. Are Role and Authority Really the Same?

A role is conventionally stored as an authority with a `ROLE_` prefix. Look at these static factories:

```java
AuthorityAuthorizationManager.hasRole("ADMIN");
AuthorityAuthorizationManager.hasAuthority("ROLE_ADMIN");
```

With default configuration, both can accept a user holding `ROLE_ADMIN`. However, the argument semantics differ:

- `hasRole("ADMIN")` automatically prepends `ROLE_` before matching.
- `hasAuthority("ROLE_ADMIN")` uses the exact string provided.
- `hasAuthority("ADMIN")` only accepts the exact authority `ADMIN`, without prepending `ROLE_`.
- `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")` is **misuse**, and this factory may throw `IllegalArgumentException` because the name already carries the prefix.

Distinguish other framework APIs that support custom role prefixes (such as `GrantedAuthorityDefaults` or specially configured factories) from direct calls to `AuthorityAuthorizationManager.hasRole(...)`, which is defined with the `ROLE_` prefix. If your project uses a custom prefix, check the exact manager being built; you can use `hasAuthority("MYROLE_ADMIN")` or an appropriate factory instead of assuming `ROLE_`.

### 3.3. Sample Decisions

Suppose `alice`'s Authentication has `ROLE_ADMIN` and `report:read`:

| Rule | Result | Reason |
|---|---|---|
| `hasRole("ADMIN")` | Allow | Has `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Allow | Exact match |
| `hasAuthority("ADMIN")` | Deny | Lacks `ADMIN` authority |
| `hasAuthority("report:read")` | Allow | Has `report:read` |
| `hasAnyAuthority("report:write", "report:read")` | Allow | Has one of the required authorities |
| `hasAnyRole("SUPPORT", "USER")` | Deny | Lacks `ROLE_SUPPORT` or `ROLE_USER`, unless role hierarchy is configured |

The rule checks **authorities present in Authentication**; it does not verify fetched data, record ownership, or tenant. A user with `report:read` in tenant A is not thereby automatically allowed to read a report belonging to tenant B.

### 3.4. Role of RoleHierarchy

In a system where `ROLE_ADMIN > ROLE_USER`, a manager can be configured to expand reachable authorities from the hierarchy. The API provides `setRoleHierarchy(...)`:

```java
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

RoleHierarchy hierarchy =
    RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_USER");

AuthorityAuthorizationManager<RequestAuthorizationContext> manager =
    AuthorityAuthorizationManager.hasRole("USER");
manager.setRoleHierarchy(hierarchy);
```

This is a **configuration illustration snippet** and belongs inside an appropriate method/bean. A user with `ROLE_ADMIN` can be accepted by this manager when `ROLE_USER` is required thanks to the hierarchy. Managers created via the static factory default to `NullRoleHierarchy` unless `setRoleHierarchy` is called; **do not assume a RoleHierarchy bean is automatically injected into every manager you `new` up or create via static factories**. When using the DSL or other factories, configuration wiring may differ, so test the final policy.

Role hierarchy describes role relationships; it does not replace tenant boundaries or per-record authorization.

## 4. AuthenticatedAuthorizationManager: Authentication State

`AuthenticatedAuthorizationManager<T>` answers "does the current Authentication type meet the requirement?" via `AuthenticationTrustResolver`, defaulting to `AuthenticationTrustResolverImpl`.

Factory methods:

| Factory | Meaning |
|---|---|
| `authenticated()` | User is authenticated per trust resolver; **not anonymous** |
| `fullyAuthenticated()` | Fully authenticated, neither anonymous nor remember-me |
| `rememberMe()` | Authentication originated from remember-me |
| `anonymous()` | Authentication is marked anonymous |

**Note:** `authenticated()` normally **accepts remember-me**. `fullyAuthenticated()` normally **rejects remember-me**. Use `fullyAuthenticated()` for operations requiring stronger identity assurance, such as changing passwords or approving sensitive actions, though this **does not automatically verify MFA or application-specific assurance levels**.

Illustration table with typical tokens, without a custom `AuthenticationTrustResolver`:

| State | `anonymous()` | `authenticated()` | `fullyAuthenticated()` | `rememberMe()` |
|---|---:|---:|---:|---:|
| AnonymousAuthenticationToken | ✓ | ✗ | ✗ | ✗ |
| RememberMeAuthenticationToken | ✗ | ✓ | ✗ | ✓ |
| Authenticated UsernamePasswordAuthenticationToken | ✗ | ✓ | ✓ | ✗ |

`Authentication#isAuthenticated()` is a flag on the token; reading this flag alone is insufficient to distinguish anonymous, remember-me, and fully authenticated. For instance, `AnonymousAuthenticationToken` structurally reports `isAuthenticated() == true`, yet the trust resolver still identifies it as anonymous. Therefore, do not write policies like `authentication.isAuthenticated()` and assume it equals `AuthenticatedAuthorizationManager.authenticated()`.

### 4.1. "Logged In" Does Not Mean Authorized

User `bob` logs in with username/password but only has `ROLE_USER`:

- `AuthenticatedAuthorizationManager.authenticated()` → allow.
- `AuthenticatedAuthorizationManager.fullyAuthenticated()` → allow.
- `AuthorityAuthorizationManager.hasRole("ADMIN")` → deny.
- `AuthorityAuthorizationManager.hasAuthority("report:read")` → deny.

Conversely, a properly built Authentication carrying the required authority must still satisfy the **desired authentication state** if the policy requires it. For sensitive actions, combine both instead of checking only one side.

### 4.2. Limitations to Know

`AuthenticatedAuthorizationManager` does not automatically check:
- Whether the password was freshly re-entered or the user passed MFA.
- Whether JWT `acr`, `amr`, or `auth_time` satisfies a step-up policy.
- Whether the user has been locked in the business system while a token/session remains valid.
- Whether the user is allowed to edit a record belonging to another tenant.

These requirements need the authentication process and/or a custom `AuthorizationManager` backed by additional trusted data. You can swap `AuthenticationTrustResolver` via `setTrustResolver(...)`, but you should not distort the trust resolver merely to hide a business policy; instead, define an explicitly tested policy.

## 5. Direct Comparison: When to Choose Which Manager?

| Business requirement | Suitable manager | Example |
|---|---|---|
| Has permission to read reports | `AuthorityAuthorizationManager` | `hasAuthority("report:read")` |
| Is admin or support | `AuthorityAuthorizationManager` | `hasAnyRole("ADMIN", "SUPPORT")` |
| Being logged in is enough | `AuthenticatedAuthorizationManager` | `authenticated()` |
| Remember-me not accepted | `AuthenticatedAuthorizationManager` | `fullyAuthenticated()` |
| Remember-me sessions only | `AuthenticatedAuthorizationManager` | `rememberMe()` |
| Unauthenticated users only | `AuthenticatedAuthorizationManager` | `anonymous()` |
| Fully authenticated **and** has export permission | **Combine two managers** | `AuthorizationManagers.allOf(...)` |
| Permitted to read **a specific invoice** | Business manager needing extra object/context | Compare tenant and owner from trusted DB |

An easy design rule to remember: **"Who is logged in and at what assurance level?" → AuthenticatedAuthorizationManager. "Which permissions/roles were granted?" → AuthorityAuthorizationManager. "Is access allowed on this specific object?" → business policy.**

## 6. Combining Multiple AuthorizationManagers

Spring Security provides the `AuthorizationManagers` utility in package `org.springframework.security.authorization`.

**Require all conditions simultaneously (AND)**:

```java
AuthorizationManagers.allOf(
    AuthenticatedAuthorizationManager.fullyAuthenticated(),
    AuthorityAuthorizationManager.hasAuthority("report:export")
)
```

**Accept any one of the conditions (OR)**:

```java
AuthorizationManagers.anyOf(
    AuthorityAuthorizationManager.hasRole("ADMIN"),
    AuthorityAuthorizationManager.hasAuthority("support:read")
)
```

Both snippets above are **manager-constructing expressions**, placed where an `AuthorizationManager<T>` is expected so Java infers generic `T`. With AND, all conditions must pass; with OR, one valid condition suffices. Pay attention to evaluation order and custom managers returning `null` (abstain) when designing complex compositions; never treat `null` as allow. With these two built-in managers, outcomes are typically unambiguous.

You can use the concise DSL when manager reuse is unnecessary:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .requestMatchers("/api/me").authenticated()
    .anyRequest().denyAll()
);
```

This is a **configuration snippet inside a SecurityFilterChain method**, not a standalone program. The DSL creates/delegates managers automatically, keeping code concise. When you need to compose conditions, reuse policies, or configure specific hierarchies/trust resolvers, `.access(...)` with explicit managers is clearer.

## 7. Complete Example: Spring Boot 3.5.6, Java 17, HTTP Endpoints, and MockMvc

The project omits a database to focus on authorization logic. It uses Spring Boot 3.5.6 (managing Spring Security 6.5.x), Maven, Java 17, and `spring-security-test`. This example uses `@RestController` with GET endpoints only, so no extra CSRF exceptions for write operations are needed.

File layout:

```text
authz-manager-demo/
  pom.xml
  src/main/java/com/example/authz/AuthzManagerApplication.java
  src/main/java/com/example/authz/SecurityConfig.java
  src/main/java/com/example/authz/DemoController.java
  src/test/java/com/example/authz/SecurityConfigTest.java
```

### 7.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>authz-manager-demo</artifactId>
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

### 7.2. Application

**`src/main/java/com/example/authz/AuthzManagerApplication.java`**

```java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzManagerApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzManagerApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain Using Both Managers

**`src/main/java/com/example/authz/SecurityConfig.java`**

```java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin")
                    .access(AuthorityAuthorizationManager.hasRole("ADMIN"))

                .requestMatchers("/api/reports")
                    .access(AuthorityAuthorizationManager.hasAuthority("report:read"))

                .requestMatchers("/api/ops")
                    .access(AuthorityAuthorizationManager.hasAnyRole("ADMIN", "OPS"))

                .requestMatchers("/api/me")
                    .access(AuthenticatedAuthorizationManager.authenticated())

                .requestMatchers("/api/sensitive")
                    .access(AuthenticatedAuthorizationManager.fullyAuthenticated())

                .requestMatchers("/api/remembered")
                    .access(AuthenticatedAuthorizationManager.rememberMe())

                .requestMatchers("/api/guest")
                    .access(AuthenticatedAuthorizationManager.anonymous())

                .requestMatchers("/api/export")
                    .access(AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager.fullyAuthenticated(),
                        AuthorityAuthorizationManager.hasAuthority("report:export")
                    ))

                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Points to note in the configuration:
1. `.requestMatchers(...)` determines **which URLs** map to which policy.
2. `.access(...)` accepts an `AuthorizationManager<RequestAuthorizationContext>`; Java infers the generic type from the call site.
3. `AuthorityAuthorizationManager` checks authorities in Authentication.
4. `AuthenticatedAuthorizationManager` distinguishes anonymous, remember-me, and fully authenticated.
5. `AuthorizationManagers.allOf(...)` requires both conditions for `/api/export`.
6. `.anyRequest().denyAll()` covers all remaining paths following default-deny.
7. `.httpBasic(...)` provides an HTTP Basic authentication mechanism for the sample app. In a real deployment, you can replace it with session login, OAuth2 resource server/JWT, or whatever mechanism your organization uses. Authorization managers do not directly depend on how passwords/JWTs were verified.

Matcher order note: Spring applies **the first matching rule**. Putting a broad pattern like `/api/**` at the top can shadow more specific rules below. Endpoint `/api/guest` is intentionally anonymous-only to demonstrate the `anonymous()` API; public registration/documentation pages usually fit `permitAll()` better.

### 7.4. Illustrative Controller

**`src/main/java/com/example/authz/DemoController.java`**

```java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports";
    }

    @GetMapping("/api/ops")
    public String ops() {
        return "ops";
    }

    @GetMapping("/api/me")
    public String me() {
        return "me";
    }

    @GetMapping("/api/sensitive")
    public String sensitive() {
        return "sensitive";
    }

    @GetMapping("/api/remembered")
    public String remembered() {
        return "remembered";
    }

    @GetMapping("/api/guest")
    public String guest() {
        return "guest";
    }

    @GetMapping("/api/export")
    public String export() {
        return "export";
    }
}
```

The endpoints return fixed strings to test policies independently of document ownership and database schemas. This is a learning application with no real business APIs and no write operations allowed.

### 7.5. MockMvc Testing Allow/Deny, Anonymous, and Remember-Me

**`src/test/java/com/example/authz/SecurityConfigTest.java`**

```java
package com.example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    private static RememberMeAuthenticationToken remembered(String authority) {
        return new RememberMeAuthenticationToken(
            "demo-key",
            "saved-user",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminRoleGrantsAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "ADMIN")
    void rawAdminAuthorityDoesNotEqualRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void exactReportAuthorityGrantsRead() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void wrongReportAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsRoleSatisfiesAnyRole() throws Exception {
        mvc.perform(get("/api/ops"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void unrelatedRoleDoesNotSatisfyAnyRole() throws Exception {
        mvc.perform(get("/api/ops"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void authenticatedUserCanOpenMe() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousUserIsChallengedForMe() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void normalLoginIsFullyAuthenticated() throws Exception {
        mvc.perform(get("/api/sensitive"))
            .andExpect(status().isOk());
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        mvc.perform(get("/api/sensitive")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberMeIsStillAuthenticatedForMe() throws Exception {
        mvc.perform(get("/api/me")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isOk());
    }

    @Test
    void rememberMeCanOpenRememberMeOnlyEndpoint() throws Exception {
        mvc.perform(get("/api/remembered")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void normalLoginDoesNotCountAsRememberMe() throws Exception {
        mvc.perform(get("/api/remembered"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCanOpenGuestOnlyEndpoint() throws Exception {
        mvc.perform(get("/api/guest"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void authenticatedUserDoesNotCountAsAnonymous() throws Exception {
        mvc.perform(get("/api/guest"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:export")
    void fullyAuthenticatedExporterIsAllowed() throws Exception {
        mvc.perform(get("/api/export"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readPermissionDoesNotGrantExport() throws Exception {
        mvc.perform(get("/api/export"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberedExporterLacksFullAuthentication() throws Exception {
        mvc.perform(get("/api/export")
                .with(authentication(remembered("report:export"))))
            .andExpect(status().isForbidden());
    }
}
```

Explanation of the two test utilities:

- `@WithMockUser` populates the security context with a test Authentication. `roles = "ADMIN"` generates authority `ROLE_ADMIN`; `authorities = "ADMIN"` creates exact `ADMIN` without adding a prefix.
- `RememberMeAuthenticationToken` constructs a remember-me state for tests. The tests use the `authentication(...)` request post-processor to inject a mock Authentication; this **does not** assert that real remember-me cookies, passwords, or login flows are implemented.

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Expected by design:** 18 tests pass; allowed requests return HTTP 200, logged-in users lacking permissions return 403, and anonymous requests to authenticated endpoints return 401 via the HTTP Basic entry point. Exact Maven/Surefire log lines are not fixed, and this expected outcome must be verified by an actual run against locked dependencies. The lesson does not claim Maven has been executed.

You can run the application with:

```bash
mvn spring-boot:run
```

No real users/passwords are declared in the example. If you want to test HTTP Basic manually, configure users via an appropriate secure environment setup; **never use an auto-generated log account as an operational mechanism**. For authorization tests, `MockMvc + @WithMockUser` already provides controlled test identities.

### 7.6. Key Results Interpretation Table

| Endpoint | Simulated caller | Expected |
|---|---|---|
| `/api/admin` | `ROLE_ADMIN` | 200 |
| `/api/admin` | Authority `ADMIN` (without `ROLE_ADMIN`) | 403 |
| `/api/reports` | `report:read` | 200 |
| `/api/reports` | Only `report:write` | 403 |
| `/api/me` | Normal login | 200 |
| `/api/me` | Anonymous | 401 |
| `/api/me` | Remember-me | 200 |
| `/api/sensitive` | Remember-me | 403 |
| `/api/remembered` | Remember-me | 200 |
| `/api/remembered` | Full login | 403 |
| `/api/guest` | Anonymous | 200 |
| `/api/guest` | Full login | 403 |
| `/api/export` | Fully authenticated + `report:export` | 200 |
| `/api/export` | Only `report:read` | 403 |
| `/api/export` | Remember-me + `report:export` | 403 |

Distinguish **401** and **403** according to exception-handling configuration: when unauthenticated and blocked, HTTP Basic normally returns 401 to challenge for credentials; when authenticated yet lacking permission, it normally returns 403. With login forms, OAuth2 entry points, custom exception handlers, or API gateways, HTTP responses may vary. The manager returns the authorization decision; turning that decision into an HTTP response is the job of the filter chain and entry point.

## 8. Testing AuthorizationManager Directly Without a Web Server

You can unit test a manager independently without going through `SecurityFilterChain`. Below is an **additional test class that runs with the `pom.xml` above** if created as instructed.

**`src/test/java/com/example/authz/ManagerUnitTest.java`**

```java
package com.example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagerUnitTest {
    @Test
    void exactAuthorityVsRolePrefix() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
        );

        AuthorityAuthorizationManager<Object> role =
            AuthorityAuthorizationManager.hasRole("ADMIN");
        AuthorityAuthorizationManager<Object> rawAuthority =
            AuthorityAuthorizationManager.hasAuthority("ADMIN");

        assertTrue(role.authorize(() -> alice, new Object()).isGranted());
        assertFalse(rawAuthority.authorize(() -> alice, new Object()).isGranted());
    }

    @Test
    void configuredRoleHierarchyGrantsImpliedRole() {
        Authentication admin = UsernamePasswordAuthenticationToken.authenticated(
            "admin", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
        );

        AuthorityAuthorizationManager<Object> userRule =
            AuthorityAuthorizationManager.hasRole("USER");
        assertFalse(userRule.authorize(() -> admin, new Object()).isGranted());

        userRule.setRoleHierarchy(
            RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_USER")
        );
        assertTrue(userRule.authorize(() -> admin, new Object()).isGranted());
    }

    @Test
    void rememberMeIsAuthenticatedButNotFullyAuthenticated() {
        Authentication token = new RememberMeAuthenticationToken(
            "demo-key", "alice",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

        AuthenticatedAuthorizationManager<Object> authenticated =
            AuthenticatedAuthorizationManager.authenticated();
        AuthenticatedAuthorizationManager<Object> fully =
            AuthenticatedAuthorizationManager.fullyAuthenticated();
        AuthenticatedAuthorizationManager<Object> remembered =
            AuthenticatedAuthorizationManager.rememberMe();

        assertTrue(authenticated.authorize(() -> token, new Object()).isGranted());
        assertFalse(fully.authorize(() -> token, new Object()).isGranted());
        assertTrue(remembered.authorize(() -> token, new Object()).isGranted());
    }
}
```

With this file, `mvn test` is expected to run **21 tests** (18 HTTP tests + 3 unit tests), with no failures if the environment and dependencies match as described. The tests use `authorize(...)` per the 6.4+ API instead of the deprecated `check(...)`.

Direct unit tests are useful for verifying a single rule. However, they **do not** verify matcher order, authentication filters, remember-me cookies, or exception translation in a web application. Therefore, keep both unit tests and integration tests for sensitive paths.

## 9. Where Are These Two Managers Used Outside HTTP?

`AuthorityAuthorizationManager<T>` and `AuthenticatedAuthorizationManager<T>` are generic implementations of `AuthorizationManager<T>`. With `T = MethodInvocation`, they can participate in a custom advisor for method security; however, **`@PreAuthorize` uses its own Method Security expression manager mechanism** and does not mean every `@PreAuthorize` directly calls these two classes.

Example of a more common method security configuration snippet:

```java
@PreAuthorize("hasRole('ADMIN') or hasAuthority('report:read')")
public Report readReport(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

This is a **service snippet** requiring `@EnableMethodSecurity`, entity/repository, and imports; it is not a standalone file. For Method Security, understand the roles of `PreAuthorizeAuthorizationManager`/SpEL, AOP proxies, and referencing method arguments.

When a policy needs both the request context and a record ID, the two built-in managers are only small building blocks. You can implement:

```java
public final class TenantPolicy implements AuthorizationManager<RequestAuthorizationContext> {
    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        // Read user from authentication, tenant/id from context/request,
        // then check permissions against trusted business data.
        return new AuthorizationDecision(false);
    }
}
```

This is an **illustrative skeleton to complete**, not a deployable policy: you must add imports for `Authentication`, `Supplier`, `AuthorizationResult`, `AuthorizationDecision`, `RequestAuthorizationContext`, define the real policy, and return the proper decision. The `false` line merely represents **default fail-closed behavior** when no valid decision exists; it does not substitute for a real authorization function.

In a project that already has HTTP rules, you can attach the custom manager via `.requestMatchers("/tenant/**").access(tenantPolicy)`, while keeping other role and authentication policies intact. Without permission checks at the service/data boundary, another flow invoking the repository or a message consumer could bypass HTTP rules.

## 10. Critical Pitfalls and How to Fix Them

### 10.1. Equating authenticated with Allowed to Do Everything

`authenticated()` only requires an authenticated state; it knows nothing about `payment:approve`, tenant, owner, suspended accounts, or MFA level. For sensitive endpoints, add `hasAuthority(...)` or a business policy and test both authorized and unauthorized users.

### 10.2. Confusing Role Strings, Authorities, and JWT Scopes

A JWT converter may produce an authority like `SCOPE_reports.read`, while the policy expects `report:read`. The strings differ, so access is denied. Design and test the mapping from JWT claims, database roles, or LDAP groups to `GrantedAuthority`. `AuthorityAuthorizationManager` does not translate scope/role names automatically.

### 10.3. Passing "ROLE_ADMIN" to hasRole

With `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")`, the static factory automatically prepends `ROLE_` and may reject an already-prefixed argument. Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`.

### 10.4. Assuming @WithMockUser Simulates Remember-Me

`@WithMockUser` defaults to a fully authenticated user. To test `rememberMe()`, use `RememberMeAuthenticationToken`, real integration tests, or remember-me cookie flow tests; when testing an HTTP FilterChain, ensure the post-processor actually flows through Spring Security test integration.

### 10.5. Forgetting Custom RoleHierarchy When Instantiating Managers Directly

A standalone `AuthorityAuthorizationManager.hasRole("USER")` does not know by default that ADMIN implies USER. When constructing managers directly, call `setRoleHierarchy(...)` if that matches your organizational model. For global DSL/factory configurations, check your version's hierarchy-wiring mechanism.

### 10.6. Using anonymous-only as a Public Endpoint

`AuthenticatedAuthorizationManager.anonymous()` **differs from** `permitAll()`. An anonymous-only endpoint normally rejects logged-in users as well. For landing pages and public docs accessible to everyone, `permitAll()` is more appropriate.

### 10.7. Allowing Remember-Me on High-Risk Endpoints

Remember-me is designed for session continuity convenience, typically carrying a different assurance level than interactive full login. For sensitive exports, password changes, and payments, use `fullyAuthenticated()` and add step-up/MFA policies where needed. Never assume `fullyAuthenticated` automatically verifies MFA.

### 10.8. Relying on HTTP 401/403 While Ignoring Internal Paths

Managers grant or deny before the controller when placed in the filter chain; background jobs, direct service calls, or internal methods are not automatically blocked by HTTP rules. Add checks at the service or data layer for operations requiring security invariants.

### 10.9. Calling check() Out of Old Habit

In Spring Security 6.5, `AuthorizationManager#check(...)` is deprecated; the modern API is `authorize(...)` returning `AuthorizationResult`. When reading older code samples, always check your active version; do not force a newer API into an older project that lacks it.

### 10.10. Composing Managers with OR When Policy Requires AND

For example, someone holding `ROLE_SUPPORT` without `report:export` **must not** be allowed to export just because one branch passed. Carefully review choices between `AuthorizationManagers.anyOf` (OR) and `allOf` (AND); always write tests for "satisfies one condition while missing the other."

### 10.11. Trusting Authorities from Client-Sent Headers

The server must build `Authentication` from a trusted authentication mechanism. A self-asserted header `X-Role: ADMIN` is not a `GrantedAuthority` unless the application has a converter/filter that verifies its signature/origin and intended usage. If an insecure configuration copies headers into `Authentication` unverified, both managers will evaluate untrusted data.

### 10.12. RequestMatcher Order and Unexpected Paths

An `/api/**` rule placed before `/api/admin` can catch every request and prevent the admin rule from ever running. Verify path matchers, HTTP methods, servlet paths, dispatcher types, and `anyRequest().denyAll()` with MockMvc/HTTP tests.

## 11. Production Readiness Checklist

1. List endpoints requiring **specific authorities**, endpoints requiring only **login**, and endpoints requiring **full authentication**.
2. Standardize authority/role names, the `ROLE_` prefix, and mapping rules for claims or groups from your identity system.
3. For role/authority policies, use `AuthorityAuthorizationManager` or the corresponding DSL; verify role hierarchy if applicable.
4. For authentication state, use `AuthenticatedAuthorizationManager`; distinguish anonymous, remember-me, and fully authenticated—never assume `isAuthenticated` covers everything.
5. When multiple requirements must hold simultaneously, use `AuthorizationManagers.allOf`; only use `anyOf` when OR is genuinely the policy.
6. For owner/tenant/record-level access, verify trusted data using a custom manager, service policy, or permission-constrained query.
7. Put specific matchers before broad matchers, ending with an appropriate default-deny rule.
8. Write integration tests for allow/deny, role vs. authority, anonymous/remember-me/fully authenticated, and missing one condition under AND.
9. Inspect the dependency tree to confirm actual Spring Security/Boot versions; use `authorize(...)` on 6.4+ and note API changes in 7.x.
10. Never assume HTTP rules automatically protect background/service calls; verify remaining business boundaries.

## 12. Self-Check Questions

**Question 1.** `alice` has `ROLE_ADMIN`. Does `hasAuthority("ADMIN")` allow access?

**Explanation:** No, because `hasAuthority` performs an exact string match. `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` matches this string (with the default role prefix).

**Question 2.** Can a remember-me user pass `.authenticated()`? What about `.fullyAuthenticated()`?

**Explanation:** Normally they pass `authenticated()`, but fail `fullyAuthenticated()`, because the trust resolver distinguishes remember-me origin.

**Question 3.** Does `hasAnyAuthority("a", "b")` require both?

**Explanation:** No, that is OR. If both are required, compose two managers with `AuthorizationManagers.allOf(...)` or build an equivalent policy.

**Question 4.** Does a `hasRole("ADMIN")` manager know whether a user may edit someone else's document?

**Explanation:** It only knows the role in `Authentication`. Ownership/tenant rules on the document must be defined and enforced separately.

**Question 5.** Why does `@WithMockUser(authorities = "ADMIN")` not pass `hasRole("ADMIN")` in tests?

**Explanation:** The `authorities` attribute inserts the exact string `ADMIN`; it does not automatically prepend `ROLE_` as `roles = "ADMIN"` does. Thus the test demonstrates the difference between roles and authorities.

## 13. Official Documentation Sources

- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, `AuthorizationManager`, descriptions of `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager`, and composition.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, matchers, rules, request authorization, and MockMvc testing.
- [Spring Security 6.5 — AuthorityAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html): `hasRole`/`hasAuthority` factories and `setRoleHierarchy`.
- [Spring Security 6.5 — AuthenticatedAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html): `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous`, and trust resolver.
- [Spring Security 6.5 — AuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize(...)`, `verify(...)`, and deprecated `check(...)`.

**Takeaway:** The two managers solve two independent dimensions of security: **what permissions were granted** and **how the user is authenticated**. Use the right `hasAuthority`/`hasRole` or `authenticated`/`fullyAuthenticated` factories, compose with AND/OR as needed, and add business policies whenever access depends on specific resources.