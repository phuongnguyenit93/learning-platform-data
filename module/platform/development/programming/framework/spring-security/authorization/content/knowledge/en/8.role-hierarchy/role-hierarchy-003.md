# Modeling ADMIN Implies MANAGER, USER Without Duplicating Authorities in Spring Security

> **Topic:** Spring Security — Role hierarchy. This lesson builds the **ADMIN implies MANAGER, MANAGER implies USER** model, explains transitive inheritance relationships, shows how to configure `RoleHierarchy` to avoid storing/granting duplicate roles per account, and demonstrates verification with Java 17+, Spring Boot, HTTP authorization, and method security.

## 1. The problem: higher roles should be able to use lower roles' features

Suppose a task management application has three roles:

| Business role | Characteristic functions |
| --- | --- |
| `USER` | View personal profile, read permitted tasks |
| `MANAGER` | Perform USER functions and approve tasks within management scope |
| `ADMIN` | Perform MANAGER and USER functions and manage system configuration |

Without a role hierarchy, you typically have to pick one of two approaches:

1. **Duplicating roles when assigning accounts:** admin is stored with `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER`; manager is stored with `ROLE_MANAGER`, `ROLE_USER`. This easily creates redundant data and makes synchronized revocation hard when the structure changes.
2. **Repeating OR clauses in every policy:** USER endpoints check `hasAnyRole("USER", "MANAGER", "ADMIN")`; MANAGER endpoints check `hasAnyRole("MANAGER", "ADMIN")`. Whenever a new role is added or permissions change, many places must be updated.

**Role hierarchy** solves this by storing only the **directly granted role** on the user while declaring **implication relationships evaluated during authorization**:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER

Declaration:
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

The `>` sign means **“implies the role/authority below”**. Because the relationship is transitive:

- A user with only `ROLE_ADMIN` is also recognized as having `ROLE_MANAGER` and `ROLE_USER` when authorization components **apply the hierarchy**.
- A user with only `ROLE_MANAGER` is recognized as having `ROLE_USER`, **not** `ROLE_ADMIN`.
- A user with only `ROLE_USER` is **not** elevated to MANAGER or ADMIN.

**This is one-way inheritance**, not three equivalent roles.

## 2. Distinguishing direct roles from effective roles

In Spring Security, `Authentication#getAuthorities()` holds the `GrantedAuthority` instances **directly granted** to the user during authentication. Typically `SimpleGrantedAuthority("ROLE_ADMIN")` holds the exact string `ROLE_ADMIN`.

`RoleHierarchy` is the component that can derive additional **effective authorities** during authorization checks:

`effectiveAuthorities = getReachableGrantedAuthorities(directAuthorities)`.

With `ROLE_ADMIN > ROLE_MANAGER` and `ROLE_MANAGER > ROLE_USER`:

| Principal | Directly assigned authority | Effective authorities when using hierarchy |
| --- | --- | --- |
| Alice | `ROLE_ADMIN` | `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER` |
| Bob | `ROLE_MANAGER` | `ROLE_MANAGER`, `ROLE_USER` |
| Carol | `ROLE_USER` | `ROLE_USER` |
| Dave | `report:read` | `report:read` (no role present in the hierarchy) |

This table shows **evaluation semantics**, not that the framework writes `ROLE_MANAGER` and `ROLE_USER` into Alice's database record, session, or token.

### What does avoiding data duplication mean?

For example, in a relational database, the user-role table only needs:

| user_id | role_code |
| --- | --- |
| alice | ADMIN |
| bob | MANAGER |
| carol | USER |

There is no need to store two extra rows for MANAGER/USER on Alice or a USER row on Bob **just to achieve inheritance**. The application maps `ADMIN` to `ROLE_ADMIN` when loading identity; `RoleHierarchy` infers the implied authorities at compatibly configured authorization checkpoints.

**Note:** if the system genuinely wants Alice to belong to **two independent organizational groups**, assigning multiple direct roles can be completely valid. “No duplication” here refers to roles added **solely for inheritance**, not forbidding multiple independent roles on one user.

### Role hierarchy does not alter roles inside tokens

- Alice's `Authentication#getAuthorities()` can still contain only `ROLE_ADMIN`.
- `RoleHierarchy#getReachableGrantedAuthorities(...)` can additionally return `ROLE_MANAGER` and `ROLE_USER`.
- A JWT issued by an IdP retains its original claims; role hierarchy does not rewrite the JWT.
- A separate service not supplied with the same hierarchy may evaluate permissions differently; verify consistency across all enforcement points.

## 3. Role hierarchy is a directed graph

Each line `A > B` is an edge from the **higher** role to the **implied** role. Evaluation must consider the **transitive path** (*transitive closure*).

~~~text
Edges:
    ADMIN  --> MANAGER
    MANAGER --> USER

Path:
    ADMIN  --> USER  (via MANAGER)

No reverse direction exists:
    USER   -X-> MANAGER
    MANAGER -X-> ADMIN
~~~

The check problem:

`hasEffectiveRole(subject, requiredRole) = requiredRole ∈ reachable(directRoles(subject))`.

For example, Alice has `ROLE_ADMIN`:

- `hasRole("ADMIN")`: ALLOW.
- `hasRole("MANAGER")`: ALLOW via inheritance.
- `hasRole("USER")`: ALLOW via transitive inheritance.

Bob has `ROLE_MANAGER`:

- `hasRole("ADMIN")`: DENY.
- `hasRole("MANAGER")`: ALLOW.
- `hasRole("USER")`: ALLOW.

### Relationships must not form cycles

The definition:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
ROLE_USER > ROLE_ADMIN
~~~

is a **modeling error**: a lower role loops back and implies a higher role, destroying the hierarchy. `RoleHierarchyImpl` detects cycles while building relationships and can throw an exception; do not design inheritance loops or rely on the library to “guess” business intent.

### Can one role imply multiple roles?

Yes. For instance, a `ROLE_DIRECTOR` role can imply both `ROLE_MANAGER` and `ROLE_AUDITOR` if business policy defines it that way. However, a role hierarchy must not turn into “every role has every permission” or merge unrelated responsibilities. *Separation of duties* may require independent checks.

## 4. Configuring `RoleHierarchyImpl.fromHierarchy`

Spring Security provides the interface:

`org.springframework.security.access.hierarchicalroles.RoleHierarchy`

and the implementation:

`org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl`.

Direct declaration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class HierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\n"
          + "ROLE_MANAGER > ROLE_USER"
        );
    }
}
~~~

This is a **configuration class running inside a Spring ApplicationContext**, not a standalone program with `main`. Each line `ROLE_X > ROLE_Y` describes **one implication relationship**. There is no need to declare `ROLE_ADMIN > ROLE_USER` explicitly because transitive inference handles it.

**Why use `fromHierarchy`?** In Spring Security 6.5, this is the static factory creating a hierarchy from text lines. `setHierarchy(...)` is the legacy configuration method and is deprecated in newer APIs; using the factory in new code makes intent clearer.

### Declaring with the builder

Since Spring Security 6.3, you can use the builder with the default `ROLE_` prefix:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("USER")
        .build();
}
~~~

This is an **alternative** to the `roleHierarchy()` bean above: register **only one** bean as the hierarchy source rather than copying both `@Bean` blocks into the same project. The builder automatically prepends `ROLE_` according to the configured prefix when building relationships; with `fromHierarchy`, you explicitly write full authority names.

### Avoiding missing or doubled prefixes

- `hasRole("USER")` normally requires the authority `ROLE_USER` under default conventions.
- `User.withUsername(...).roles("ADMIN")` creates `ROLE_ADMIN`.
- `User.withUsername(...).authorities("ROLE_ADMIN")` creates the literal authority `ROLE_ADMIN`.
- If using a custom prefix such as `APP_` via `GrantedAuthorityDefaults`, you must **synchronize** user authority mapping, the hierarchy builder, and each consumer; a prefix bean does not rewrite an existing `ROLE_ADMIN` string into `APP_ADMIN`.
- Never use `roles("ROLE_ADMIN")`; the `roles(...)` builder expects unprefixed role names and prepends `ROLE_` automatically.

## 5. Pure Java 17: demonstrating transitivity without duplicating authorities

This program **has no Spring dependencies**; it uses a graph and breadth-first traversal to simulate reachable authorities. It clearly shows why there is no need to store `ROLE_USER` on Alice.

Create **`RoleGraphDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.HashSet;

public class RoleGraphDemo {

    private static final Map<String, List<String>> INCLUDES = Map.of(
        "ROLE_ADMIN", List.of("ROLE_MANAGER"),
        "ROLE_MANAGER", List.of("ROLE_USER")
    );

    static List<String> reachable(String directRole) {
        Queue<String> queue = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        queue.add(directRole);

        while (!queue.isEmpty()) {
            String role = queue.remove();
            if (visited.add(role)) {
                queue.addAll(INCLUDES.getOrDefault(role, List.of()));
            }
        }

        List<String> sorted = new ArrayList<>(visited);
        sorted.sort(String::compareTo);
        return sorted;
    }

    static boolean hasRole(String directRole, String requiredRole) {
        return reachable(directRole).contains(requiredRole);
    }

    public static void main(String[] args) {
        System.out.println("ADMIN reachable = "
            + reachable("ROLE_ADMIN"));
        System.out.println("MANAGER reachable = "
            + reachable("ROLE_MANAGER"));
        System.out.println("USER reachable = "
            + reachable("ROLE_USER"));
        System.out.println("ADMIN has USER = "
            + hasRole("ROLE_ADMIN", "ROLE_USER"));
        System.out.println("MANAGER has ADMIN = "
            + hasRole("ROLE_MANAGER", "ROLE_ADMIN"));
        System.out.println("USER has MANAGER = "
            + hasRole("ROLE_USER", "ROLE_MANAGER"));
    }
}
~~~

Run with **JDK 17+** inside the directory containing the file:

~~~bash
javac RoleGraphDemo.java
java RoleGraphDemo
~~~

**Deterministic stdout from the code:**

~~~text
ADMIN reachable = [ROLE_ADMIN, ROLE_MANAGER, ROLE_USER]
MANAGER reachable = [ROLE_MANAGER, ROLE_USER]
USER reachable = [ROLE_USER]
ADMIN has USER = true
MANAGER has ADMIN = false
USER has MANAGER = false
~~~

Explanation:

- Alice's input can be just `ROLE_ADMIN`. The program traverses ADMIN → MANAGER → USER and returns the **effective** list.
- Bob has `ROLE_MANAGER`, so the result only includes MANAGER/USER; there is no reverse inheritance up to ADMIN.
- Carol has `ROLE_USER` and is not automatically promoted to MANAGER.
- `HashSet` prevents visiting the same node repeatedly; the list is sorted before printing so output order is fixed.

This is only a role graph simulation and does not replace `RoleHierarchyImpl`, `Authentication`, or Spring Security's real decision-making mechanisms. Its purpose is to make the math of the relationship clear.

## 6. Where does Spring Security use the hierarchy?

Creating a `RoleHierarchy` bean **does not mean** every custom authorization check across the entire application automatically uses it. Distinguish at least these places:

| Check location | Can it use hierarchy? | How to ensure it |
| --- | --- | --- |
| `authorizeHttpRequests(...).hasRole(...)` | Yes, in Spring Security configurations that integrate `RoleHierarchy` | Register the hierarchy bean and verify with version-appropriate HTTP integration tests |
| `authorizeHttpRequests(...).hasAuthority(...)` | Yes, when the manager is configured with hierarchy | Check the contract / test the exact manager |
| `@PreAuthorize("hasRole(...)")` | Yes | Enable `@EnableMethodSecurity` and set `RoleHierarchy` on `DefaultMethodSecurityExpressionHandler` |
| `@PreAuthorize("hasAuthority(...)")` | Yes, when the expression handler uses hierarchy | Configure the method expression handler and test |
| `@Secured(...)` | Yes, in supported versions | Enable `securedEnabled`, verify manager/hierarchy |
| `@RolesAllowed(...)` | Yes, in supported versions | Enable `jsr250Enabled`, verify the corresponding manager |
| `AuthorityAuthorizationManager.hasRole(...)` created via static factory | Not guaranteed by default to receive the context hierarchy bean | If assembling a manager manually, call `setRoleHierarchy(...)` and test |
| Custom `AuthorizationManager` or policy bean | **Cannot be assumed** | Inject `RoleHierarchy` and use it per contract, or intentionally evaluate direct roles |
| `Authentication#getAuthorities()` | Does not expand list automatically | Use `getReachableGrantedAuthorities(...)` to inspect effective authorities |
| JWT converter / user repository | Does not alter source data | Manage mappings/tokens separately |

Per Spring Security 6.5 documentation, **HTTP request authorization** supports role hierarchy, whereas **pre/post method security** requires wiring the hierarchy into `MethodSecurityExpressionHandler` for the expression usage in this lesson.

### Why state the scope explicitly?

Suppose an HTTP rule lets Alice (ADMIN) access a USER endpoint, yet the controller calls a service protected by a custom manager that only reads `authentication.getAuthorities()` for the literal `ROLE_USER` without applying the hierarchy. In that case HTTP may ALLOW while the service still DENYs.

The right diagnosis is not “hierarchy is broken”, but that two **different enforcement checkpoints** are not using the same model. An application with multiple filter chains, method interceptors, or custom managers must verify each layer.

## 7. Complete Spring Boot Java 17+ configuration: HTTP and method security sharing the hierarchy

This demo uses **one SecurityFilterChain**, **four accounts**, and one hierarchy. Endpoints use GET only to focus on role inheritance; no data-mutating operations are performed.

### 7.1. Create the project

Use Spring Initializr or a Maven project with Spring Boot **3.5.x**, Java **17+**, and:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` and `spring-security-test` for test scope.

If using the Maven wrapper from Initializr, you can run `./mvnw spring-boot:run`. No database is needed. This project must not be used directly in production because it contains sample accounts and passwords.

### 7.2. Main class and security configuration

Create **`src/main/java/com/example/hierarchy/HierarchyApplication.java`**:

~~~java
package com.example.hierarchy;

import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class HierarchyApplication {

    public static void main(String[] args) {
        SpringApplication.run(HierarchyApplication.class, args);
    }

    // Declare the ADMIN > MANAGER > USER relationship once.
    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\n"
          + "ROLE_MANAGER > ROLE_USER"
        );
    }

    // Method-security SpEL must use the same hierarchy.
    // static @Bean so it registers before method security configuration.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/manager/**").hasRole("MANAGER")
                .requestMatchers("/api/user/**").hasRole("USER")
                .requestMatchers(
                    "/api/method/**", "/api/whoami", "/api/reachable"
                ).authenticated()
                .anyRequest().denyAll()
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
        // Do not duplicate MANAGER and USER onto Alice.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();

        // Do not duplicate USER onto Bob.
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("MANAGER")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("USER")
            .build();

        // Permission not in the role graph:
        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .authorities("report:read")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    @RestController
    static class Api {
        private final TeamService service;
        private final RoleHierarchy hierarchy;

        Api(TeamService service, RoleHierarchy hierarchy) {
            this.service = service;
            this.hierarchy = hierarchy;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/admin/settings")
        String admin() {
            return "admin settings";
        }

        @GetMapping("/api/manager/review")
        String manager() {
            return "manager review";
        }

        @GetMapping("/api/user/dashboard")
        String user() {
            return "user dashboard";
        }

        @GetMapping("/api/method/admin")
        String methodAdmin() {
            return service.admin();
        }

        @GetMapping("/api/method/manager")
        String methodManager() {
            return service.manager();
        }

        @GetMapping("/api/method/user")
        String methodUser() {
            return service.user();
        }

        // Display only directly granted authorities without duplication.
        @GetMapping("/api/whoami")
        String whoami(Authentication authentication) {
            String direct = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + direct;
        }

        // Display the effective set inferred by the hierarchy.
        @GetMapping("/api/reachable")
        String reachable(Authentication authentication) {
            String derived = hierarchy
                .getReachableGrantedAuthorities(
                    authentication.getAuthorities()
                )
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
            return authentication.getName() + ":" + derived;
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "must not be reached";
        }
    }

    @Service
    static class TeamService {

        @PreAuthorize("hasRole('ADMIN')")
        public String admin() {
            return "method admin";
        }

        @PreAuthorize("hasRole('MANAGER')")
        public String manager() {
            return "method manager";
        }

        @PreAuthorize("hasRole('USER')")
        public String user() {
            return "method user";
        }
    }
}
~~~

### 7.3. Inspecting three essential parts

**First — assign only the direct role:** Alice is built with `roles("ADMIN")`, so her `Authentication#getAuthorities()` list contains **`ROLE_ADMIN`**, not three duplicated authority entries. Bob holds only `ROLE_MANAGER` and Carol holds only `ROLE_USER`.

**Second — a single hierarchy bean as source of truth:** `roleHierarchy()` uses just two edges, and Spring Security infers ADMIN → USER transitively. You do not need to add `ROLE_ADMIN > ROLE_USER`.

**Third — two distinct enforcement points:**

- HTTP `authorizeHttpRequests(...).hasRole("MANAGER")` checks the role during request authorization, using the hierarchy via integrated configuration.
- Method `@PreAuthorize("hasRole('MANAGER')")` uses `DefaultMethodSecurityExpressionHandler` configured with `setRoleHierarchy(roleHierarchy)`.
- HTTP rules for `/api/method/**` only require `authenticated()`, proving that 403 role denials come from **method security**.

### 7.4. Why invoke the service from the controller instead of internally?

Method security relies on Spring AOP proxies in standard setups. In the example, `Api` receives the Spring bean `TeamService` and calls public methods annotated with `@PreAuthorize`. If another method inside the same service class calls `this.manager()` (self-invocation), the internal call can **bypass the proxy**, skipping the interceptor. Do not rely on self-invocation when verifying whether hierarchy or `@PreAuthorize` is working.

### 7.5. ROLE_ADMIN does not mean holding every permission

`RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_USER")` only defines implication over **the two lower roles**. It does not automatically grant `docs:read`, `report:write`, or access to every document.

A reporting feature requiring `hasAuthority("report:read")` needs that authority explicitly granted or implied by an **explicitly declared** hierarchy edge. The model never assumes `ADMIN` equals “allowed to do anything”.

## 8. Manual testing: comparing direct vs. inherited authorities

### 8.1. Startup

In the root directory of the Maven project:

~~~bash
# macOS / Linux:
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt:
mvnw.cmd spring-boot:run
~~~

Once the application is running on default port 8080:

~~~bash
# Public:
curl -i http://localhost:8080/public/ping

# Check raw roles vs. effective roles:
curl -i -u alice:demo123 http://localhost:8080/api/whoami
curl -i -u alice:demo123 http://localhost:8080/api/reachable
curl -i -u bob:demo456 http://localhost:8080/api/whoami
curl -i -u bob:demo456 http://localhost:8080/api/reachable

# HTTP role checks:
curl -i -u alice:demo123 http://localhost:8080/api/user/dashboard
curl -i -u alice:demo123 http://localhost:8080/api/manager/review
curl -i -u alice:demo123 http://localhost:8080/api/admin/settings
curl -i -u bob:demo456 http://localhost:8080/api/admin/settings
curl -i -u carol:demo789 http://localhost:8080/api/manager/review

# Method security:
curl -i -u alice:demo123 http://localhost:8080/api/method/user
curl -i -u bob:demo456 http://localhost:8080/api/method/manager
curl -i -u bob:demo456 http://localhost:8080/api/method/admin
curl -i -u dave:demo000 http://localhost:8080/api/method/user
~~~

**Expected inspection endpoint bodies:**

| Request | Body |
| --- | --- |
| Alice `GET /api/whoami` | `alice:ROLE_ADMIN` |
| Alice `GET /api/reachable` | `alice:ROLE_ADMIN,ROLE_MANAGER,ROLE_USER` |
| Bob `GET /api/whoami` | `bob:ROLE_MANAGER` |
| Bob `GET /api/reachable` | `bob:ROLE_MANAGER,ROLE_USER` |
| Carol `GET /api/reachable` | `carol:ROLE_USER` |
| Dave `GET /api/reachable` | `dave:report:read` |

This is the crucial proof: **Alice is evaluated as MANAGER and USER even though Alice's direct authority remains only ROLE_ADMIN**. The `/api/reachable` response is computed by the demo app itself using `RoleHierarchy`; it is not a header automatically emitted by Spring Security.

### 8.2. HTTP authorization matrix

| User | `/api/admin/settings` | `/api/manager/review` | `/api/user/dashboard` |
| --- | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 |
| Alice — ADMIN | **200** | **200** | **200** |
| Bob — MANAGER | 403 | **200** | **200** |
| Carol — USER | 403 | 403 | **200** |
| Dave — only `report:read` | 403 | 403 | 403 |

This matrix reflects HTTP Basic in the sample app. Unauthenticated requests to protected routes typically return **401**; authenticated requests lacking permission return **403**. With form login, anonymous requests may receive a redirect (302) instead of 401.

### 8.3. Method security authorization matrix

| User | `/api/method/admin` | `/api/method/manager` | `/api/method/user` |
| --- | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 |
| Alice — ADMIN | **200** | **200** | **200** |
| Bob — MANAGER | 403 | **200** | **200** |
| Carol — USER | 403 | 403 | **200** |
| Dave — only `report:read` | 403 | 403 | 403 |

**Both matrices must agree.** If HTTP lets Alice into manager routes while the method returns 403, verify that the method expression handler uses `RoleHierarchy` and that requests invoke the Spring-managed service proxy.

### 8.4. Cases that must not be confused

- `ROLE_ADMIN > ROLE_MANAGER > ROLE_USER` does not mean `ROLE_USER > ROLE_ADMIN`.
- `authenticated()` is not equivalent to `hasRole("USER")`: Dave is authenticated so he can call `/api/whoami`, yet he cannot access `/api/user/dashboard`.
- `hasRole("USER")` with the default prefix is not the same as `hasAuthority("USER")`; it checks for `ROLE_USER` (which can be inherited when consumers use the hierarchy).
- `@PreAuthorize` only takes effect when method security is enabled and calls go through the appropriate interceptor mechanism.
- An HTTP-layer ALLOW does not waive domain policy; documents belonging to another tenant must still be blocked.

## 9. Automated verification with Spring Security Test + MockMvc

### 9.1. Test dependencies

In `pom.xml`, confirm these two test dependencies are present (do not duplicate them):

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

This is an XML fragment placed inside `<dependencies>` in the POM. The Spring Boot BOM/parent manages compatible versions.

### 9.2. Complete test suite for role ordering

Create **`src/test/java/com/example/hierarchy/HierarchyApplicationTests.java`**:

~~~java
package com.example.hierarchy;

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
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HierarchyApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // principal,password,path,expected HTTP status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/admin/settings,401",
        "anonymous,none,/api/manager/review,401",
        "anonymous,none,/api/user/dashboard,401",
        "anonymous,none,/api/method/user,401",

        "alice,demo123,/api/admin/settings,200",
        "alice,demo123,/api/manager/review,200",
        "alice,demo123,/api/user/dashboard,200",
        "alice,demo123,/api/method/admin,200",
        "alice,demo123,/api/method/manager,200",
        "alice,demo123,/api/method/user,200",

        "bob,demo456,/api/admin/settings,403",
        "bob,demo456,/api/manager/review,200",
        "bob,demo456,/api/user/dashboard,200",
        "bob,demo456,/api/method/admin,403",
        "bob,demo456,/api/method/manager,200",
        "bob,demo456,/api/method/user,200",

        "carol,demo789,/api/admin/settings,403",
        "carol,demo789,/api/manager/review,403",
        "carol,demo789,/api/user/dashboard,200",
        "carol,demo789,/api/method/admin,403",
        "carol,demo789,/api/method/manager,403",
        "carol,demo789,/api/method/user,200",

        "dave,demo000,/api/admin/settings,403",
        "dave,demo000,/api/manager/review,403",
        "dave,demo000,/api/user/dashboard,403",
        "dave,demo000,/api/method/admin,403",
        "dave,demo000,/api/method/manager,403",
        "dave,demo000,/api/method/user,403"
    })
    void roleMatrix(String principal, String password,
                    String path, int expectedStatus)
            throws Exception {
        MockHttpServletRequestBuilder request = get(path);

        if (!"anonymous".equals(principal)) {
            request.with(httpBasic(principal, password));
        }

        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void adminHasOnlyOneDirectAuthority() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_ADMIN"));
    }

    @Test
    void adminInheritsManagerAndUserTransitively() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "alice:ROLE_ADMIN,ROLE_MANAGER,ROLE_USER"
            ));
    }

    @Test
    void managerInheritsUserButNotAdmin() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "bob:ROLE_MANAGER,ROLE_USER"
            ));

        mvc.perform(get("/api/admin/settings")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void plainUserNeverGetsManagerRole() throws Exception {
        mvc.perform(get("/api/manager/review")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/user/dashboard")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());
    }

    @Test
    void unrelatedAuthorityDoesNotInheritAnyRole() throws Exception {
        mvc.perform(get("/api/reachable")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("dave:report:read"));

        mvc.perform(get("/api/method/user")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fallbackDeniesEvenAdmin() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/user/dashboard")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Why test this way?**

- Verifies **both directions**: Alice reaches manager/user routes (downward inheritance) while Bob cannot reach admin and Carol cannot reach manager (no upward inheritance).
- Verifies **direct vs. effective**: `/api/whoami` returns only `ROLE_ADMIN`, while `/api/reachable` returns all three roles. If code had duplicated roles onto Alice instead of using hierarchy, the direct authority test catches it.
- Verifies **both HTTP and method** simultaneously: never assume one layer working means the other works automatically.
- Verifies **unrelated authorities**: Dave holds only `report:read` and receives no roles from the hierarchy.
- Verifies **fallback deny**: endpoints without an allow rule remain closed, even to ADMIN.
- Verifies **wrong password**: separates authentication 401 from authorization 403.

`httpBasic(...)` actually sends Basic credentials on the MockMvc request, unlike `@WithMockUser` which builds a synthetic test identity. As a result, this test also exercises the demo `UserDetailsService` and `roles(...)` mapping. Testing role hierarchy separately with `@WithMockUser(roles = "ADMIN")` is also valid, though do not use it to claim your app's credential/mapper setup is correct.

### 9.3. Running the tests

~~~bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

Expected behavior: all test cases pass when using the exact dependencies and configuration shown. Logs, test duration, Maven/Surefire versions, and report names depend on the environment; rely on actual test execution output rather than fabricating output beforehand.

**Do not skip negative tests.** If a misconfiguration accidentally lets every user into `/api/manager/**`, Alice's 200 test still passes, but Carol's 403 test catches the flaw.

## 10. Using hierarchy only at HTTP or only at method — what happens?

### 10.1. If you only create a `RoleHierarchy` bean and enable HTTP rules

In Spring Security 6.5, documentation describes using a `RoleHierarchy` bean to support `authorizeHttpRequests`. However, if the application also uses `@PreAuthorize`, check `MethodSecurityExpressionHandler`. That is why section 7 intentionally registered **both**:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy(
        "ROLE_ADMIN > ROLE_MANAGER\n"
      + "ROLE_MANAGER > ROLE_USER"
    );
}

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy hierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(hierarchy);
    return handler;
}
~~~

Both methods above are **fragments** already present in the full application. Do not declare them a second time if your project already has them.

### 10.2. If you instantiate `AuthorityAuthorizationManager` manually

Example of a custom policy using the static factory:

~~~java
import org.springframework.security.authorization.AuthorityAuthorizationManager;

// Fragment: manager created manually by the application.
var manager = AuthorityAuthorizationManager
    .<Object>hasRole("USER");

// Ensure this manager uses the injected hierarchy.
manager.setRoleHierarchy(roleHierarchy);
~~~

This is a **fragment**, where `roleHierarchy` must be the `RoleHierarchy` bean used in the app. `AuthorityAuthorizationManager` provides `setRoleHierarchy(...)`; **a manually instantiated instance** must not be assumed to pick up the bean automatically just because it lives in the same ApplicationContext. When building your own custom `AuthorizationManager`, explicitly design its inputs and how effective authorities are expanded.

### 10.3. With `@Secured` and `@RolesAllowed`

Spring Security 6.5 can combine role hierarchies with other method authorization styles, provided the corresponding interceptors are enabled:

~~~java
// Annotation fragment replacing default @EnableMethodSecurity:
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

`@Secured("ROLE_USER")` uses literal role/authority strings; JSR-250's `@RolesAllowed("USER")` has its own prefix handling. Never assume from the annotation name alone that custom prefixes or managers behave identically to `@PreAuthorize("hasRole('USER')")`. Test each style, especially across version upgrades.

## 11. When business permissions exist: roles can imply other authorities

The ADMIN > MANAGER > USER model solves **role implication**. If the application has specific permissions such as `task:read` or `task:approve`, the graph can be extended so roles imply those authorities:

~~~java
RoleHierarchy hierarchy = RoleHierarchyImpl.fromHierarchy(
    "ROLE_ADMIN > ROLE_MANAGER\n"
  + "ROLE_MANAGER > ROLE_USER\n"
  + "ROLE_MANAGER > task:approve\n"
  + "ROLE_USER > task:read"
);
~~~

This is a **fragment**, suitable when policy states:

- USER is allowed `task:read`.
- MANAGER is allowed both `task:approve` and `task:read`.
- ADMIN inherits all of these permissions through MANAGER.

**Modeling note:** `RoleHierarchy` operates on authority strings and does not distinguish that `ROLE_MANAGER` is a “role” while `task:approve` is a “permission” if you declare that edge. Maintain clear naming conventions and change governance. In larger systems, mapping role → permission in the identity/authorization store or database may be easier to govern, while avoiding uncontrolled duplication during token issuance or synchronization.

A multi-tenant system should not treat a global `ROLE_MANAGER` as approval authority across **every tenant**. Scoped authorities, tenant-aware policies, or domain-level checks may be needed depending on requirements.

## 12. Do not confuse role inheritance with resource permissions

Role hierarchy answers: **which effective roles/authorities does the user have?** It does **not** automatically answer:

- Which tenant's documents a user may view.
- Whether a manager may approve a task they created themselves.
- Whether a record is in an editable state or locked.
- Whether a document is shared with a specific user.
- Whether a user is allowed to act on a project with a given ID.

For instance, both Alice (ADMIN) and Bob (MANAGER) may satisfy `hasRole("MANAGER")`, yet if task 42 belongs to another tenant, it must still **DENY** per resource policy. When writing services:

~~~java
// Illustrative fragment: combine role check with object-level policy.
@PreAuthorize("hasRole('MANAGER') and @taskPolicy.canApprove(authentication, #taskId)")
public void approveTask(Long taskId) {
    // Business logic: check state, transaction, audit.
}
~~~

This is a **fragment**, not standalone runnable code: it requires a `taskPolicy` bean and corresponding service implementation; copying the annotation without that bean will break the app. In production code, ensure SpEL parameter names are clear or use `@P` if compiler settings do not preserve parameter names.

**Preserve least privilege:** inheriting lower roles does not turn a higher role into a “bypass everything” pass when data policy or separation of duties dictates otherwise.

## 13. Common implementation mistakes and how to spot them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Granting Alice `ROLE_ADMIN`, `ROLE_MANAGER`, and `ROLE_USER` simultaneously just for inheritance | Redundant authority data, hard to update consistently | Store only the needed highest role; apply hierarchy during authorization |
| Writing `ROLE_ADMIN > ROLE_USER` while forgetting `ROLE_MANAGER > ROLE_USER` | Bob (MANAGER) never gets USER | Declare the actual edges and test transitivity |
| Writing reversed edge `ROLE_USER > ROLE_ADMIN` | USER can escalate privileges | Review direction of `>` |
| Creating loop ADMIN → MANAGER → USER → ADMIN | Invalid model, may fail at hierarchy creation | Keep the graph acyclic |
| Declaring hierarchy bean without configuring method expression handler | HTTP and method checks disagree | Register static handler bean with `setRoleHierarchy(...)` and test both layers |
| Instantiating `AuthorityAuthorizationManager` manually and forgetting `setRoleHierarchy` | Custom manager ignores role inheritance | Inject and wire the hierarchy |
| Calling `roles("ROLE_ADMIN")` | Builder rejects pre-prefixed role names | Use `roles("ADMIN")` or `authorities("ROLE_ADMIN")` |
| Using a custom prefix while hierarchy still uses `ROLE_` | Stored authorities fail to match policies | Align issuance and check prefixes |
| Assuming higher role grants access to every record | Tenant/ownership/IDOR vulnerabilities | Add domain authorization |
| Testing only that admin gets ALLOW | Misses privilege escalation by regular users | Test that manager/USER get DENY on higher rules |
| Assuming hierarchy mutates JWT/Authentication | Misleading debugging and unexpected data | Distinguish direct authorities from reachable authorities |
| Changing hierarchy without impact review | Permission scope widens unexpectedly | Review graph, run regression tests, and audit |

### Pre-production checklist

1. **Role diagram** confirmed by business owners? Every edge `A > B` is a **major authorization decision**.
2. **Edge order and direction** correct? No cycles or misunderstood special relationships?
3. **All enforcement points** (HTTP, method, custom managers) use the same hierarchy for your framework version?
4. **UserDetailsService/JWT converter** assigns direct authorities with exact names, prefixes, and no unnecessary duplication?
5. **Negative test suite** proves USER cannot become MANAGER and MANAGER cannot become ADMIN?
6. **Multi-tenant/owned resources** enforce object-instance authorization independently of roles?
7. **When revoking roles or updating hierarchy**, how are caches/sessions/tokens handled? Are stale permissions invalidated?
8. **403 monitoring and auditing** designed prior to rolling out permission changes?

## 14. Self-check questions

**Question 1.** What does the graph `ROLE_ADMIN > ROLE_MANAGER` and `ROLE_MANAGER > ROLE_USER` imply for ADMIN?  
**Answer:** ADMIN, MANAGER, and USER, via transitive implication.

**Question 2.** Do you also need to add `ROLE_ADMIN > ROLE_USER`?  
**Answer:** No. The ADMIN → USER edge is already inferred through MANAGER.

**Question 3.** Should you store three direct role rows for Alice (ADMIN) just so she can open the USER screen?  
**Answer:** No need. Assign `ROLE_ADMIN` only and apply hierarchy during authorization.

**Question 4.** Does Alice's `Authentication#getAuthorities()` automatically expand to three roles?  
**Answer:** Not by default. Hierarchy expands **effective authorities at check time** without necessarily modifying the directly granted list.

**Question 5.** Can MANAGER access an endpoint restricted solely to ADMIN?  
**Answer:** No, because there is no reverse inheritance.

**Question 6.** Alice (ADMIN) calls `@PreAuthorize("hasRole('USER')")` and gets 403 even though HTTP lets her through. What should you check?  
**Answer:** `@EnableMethodSecurity`, whether the method expression handler has `setRoleHierarchy(...)`, whether the call goes through a Spring bean/proxy, and whether the direct authority is literally `ROLE_ADMIN`.

**Question 7.** Dave has only `report:read`; does he automatically become USER?  
**Answer:** No, because that authority has no path to `ROLE_USER` in the graph.

**Question 8.** Can you declare `ROLE_USER > task:read`?  
**Answer:** Yes, if policy intends USER to imply `task:read` and consumers use the hierarchy. Keep naming and scope consistent.

**Question 9.** Does ADMIN implying MANAGER let an admin approve a task from another tenant?  
**Answer:** No. You need domain-level policies checking tenant, owner, state, and operation scope.

**Question 10.** Why must you test that Bob cannot access admin and Carol cannot access manager?  
**Answer:** Because one-way ALLOW tests do not prove the system is free from **reverse privilege escalation**.

**Remember:** Store **direct roles**, declare `ROLE_ADMIN > ROLE_MANAGER` and `ROLE_MANAGER > ROLE_USER`, and let `RoleHierarchy` derive **transitive** permissions at evaluation time. This avoids role duplication and repeated ORs in every rule, while still requiring proper configuration at **every authorization layer** and protection for **specific resource instances**.

## Official documentation

- Spring Security 6.5 — Authorization Architecture / Hierarchical Roles: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Method Security / Customizing Expression Handling: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — `RoleHierarchy` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchy.html
- Spring Security 6.5 — `RoleHierarchyImpl` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 6.5 — `AuthorityAuthorizationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 6.5 — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
