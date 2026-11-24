# Never Treat Hiding UI Buttons as Authorization

> **Topic:** Spring Security — fundamentals / Application Design. This lesson explains why hiding buttons, disabling forms, or blocking navigation in the frontend is **purely user experience (UX)**, never a security boundary. Permissions must be enforced **on the server, for the exact operation and resource**, whether requests come from a browser, script, mobile app, or HTTP client. Examples use **Java 17+**, **Spring Boot 3.5.0**, Spring Security 6.x (Servlet), Maven, and MockMvc.

## 1. Nature of the problem: clients control the UI, not permissions

Suppose a report management app has an "Approve" button. The UI hides the button when the account lacks `ROLE_MANAGER`:

~~~javascript
// Frontend illustration; this itself does NOT grant or revoke permissions.
const me = await fetch("/api/me", {
  credentials: "same-origin"
}).then(response => response.json());

document.querySelector("#approveButton").hidden =
    !me.authorities.includes("ROLE_MANAGER");
~~~

Ordinary users may not see the button. Yet they can still:

- Open DevTools and remove the element's `hidden` or `disabled` attribute.
- Call `fetch` directly in the console; write a Python/JavaScript script; use Postman, curl, or another browser.
- Change the URL, HTTP method, resource ID, or JSON body fields the UI does not expose.
- Use an older frontend version, mobile app, or call the API directly.
- Modify the `/api/me` response inside the client to reveal the button (though doing so does **not** alter server permissions).

A hand-crafted request:

~~~http
POST /api/reports/51/approve HTTP/1.1
Host: example.test
Cookie: session=REDACTED
Content-Type: application/json
X-Role: MANAGER

{}
~~~

**There is no button in an HTTP request for the server to rely on.** If the API only verifies that the caller is logged in and then approves the report, hiding the button in the frontend does not stop unauthorized actions.

`X-Role: MANAGER` in this example is **self-asserted client data** and must never be used to grant permissions. For cookie-session apps, state-changing requests also need CSRF protection per design; CSRF **does not replace** role/owner checks. The `Cookie` header here is merely a redacted placeholder, not proof of a real session.

**Principle:** the frontend may **reflect** permissions; only the backend and policy/data layers may **enforce** permissions.

## 2. Distinguishing UI visibility, authentication, and authorization

| Question | Component that handles it | What it does **not** guarantee |
|---|---|---|
| Should the "Approve" button be shown? | Frontend using capability/permission info from the server | Cannot block hand-crafted requests |
| Who is the caller? | Authentication, verified session/Basic/Bearer token | Does not say which objects they may act on |
| Does the caller have the role/scope for the feature? | Spring Security HTTP/method authorization | Does not guarantee record tenant/owner permission |
| Are they permitted on **resource ID 51**? | Service/policy/ACL/repository with principal + resource + action | Cannot be inferred merely from knowing the ID or seeing a button |
| Is data modified safely? | Transactions, tenant/owner-scoped queries, side-effect checks | Must never be skipped just because the frontend disabled a button |

**Authentication** establishes a trusted `Authentication` in `SecurityContext`. **Authorization** answers "may this principal perform action A on resource R right now?". When clients send `role`, `ownerId`, `tenantId`, or `isAdmin` in bodies or headers, those are **untrusted inputs** and must never automatically become authorization attributes.

A coarse check example:

~~~java
// Wrong: "logged in" does not mean authorized to approve.
.requestMatchers("/api/reports/**").authenticated()
~~~

If any logged-in user can call `POST /api/reports/51/approve`, hiding the button in the UI does not change server behavior.

A better rule at the **HTTP layer** is:

~~~java
.requestMatchers(HttpMethod.POST, "/api/reports/{id}/approve")
    .hasRole("MANAGER")
~~~

This is still only a first step. In a multi-tenant SaaS, `ROLE_MANAGER` in tenant **west** does not automatically grant approval rights for reports in tenant **east**. The service must verify data boundaries.

## 3. Design policies from business rules, not button state

Consider a sample system with:

| Resource | ID | Tenant | Owner | Initial status |
|---|---|---|---|---|
| Order | 101 | east | alice | OPEN |
| Order | 202 | east | bob | OPEN |
| Order | 303 | west | mallory | OPEN |
| Report | 51 | east | — | PENDING |
| Report | 61 | west | — | PENDING |

Principals:

| Principal | Server-assigned role | Server-verified tenant |
|---|---|---|
| alice | USER | east |
| bob | USER | east |
| manager | MANAGER | east |
| mallory | MANAGER | west |
| anonymous | none | none |

**Example policy:**

1. **READ order:** only the **owner in the same tenant** may view.
2. **CANCEL order:** only the **owner in the same tenant** may cancel.
3. **READ report:** only a **MANAGER of the right tenant** may view.
4. **APPROVE report:** only a **MANAGER of the right tenant** may approve.
5. **Non-existent or wrong tenant/owner:** return `404` per the demo's choice to hide resource existence.
6. **Logged in without functional role:** `403`; **anonymous** calling protected APIs: `401` under HTTP Basic in the demo.

### Permission verification matrix

| Principal | GET order 101 | POST cancel order 101 | GET report 51 | POST approve report 51 |
|---|---|---|---|---|
| anonymous | 401 | 401* | 401 | 401* |
| alice (owner) | 200 | 200* | 403 | 403* |
| bob (not owner) | 404 | 404* | 403 | 403* |
| manager (east) | 404 | 404* | 200 | 200* |
| mallory (MANAGER, west) | 404 | 404* | 404 | 404* |

Note `*`: when testing `POST` authorization in an environment with CSRF protection, you must **send a valid CSRF token**. If the token is absent, `CsrfFilter` may return `403` before authorization rules are evaluated. The MockMvc test suite below intentionally uses `with(csrf())` to avoid false conclusions.

Notably:

- Alice sees the "Cancel order 101" button because she owns the order, while Bob is forbidden from canceling even if he un-hides the button.
- The west manager may **see the Approve button** due to having the MANAGER role, yet **cannot approve east tenant report 51**. Button visibility only reflects broad permissions and does not necessarily know full resource policies.
- The server must resolve role, tenant, owner, and action before modifying records. Never trust JavaScript to have decided correctly.

## 4. Application trust boundary wall

~~~mermaid
flowchart LR
    U["Frontend: hide/show button<br/>UX, untrusted"] -->|"HTTP request"| S["Spring Security FilterChain<br/>Authentication + route authz"]
    X["curl / Postman / script<br/>no UI needed"] -->|"HTTP request"| S
    S -->|"reaches service"| P["Policy/service: tenant,<br/>owner, resource, action"]
    P -->|"allow"| D["Resource query/mutation"]
    P -->|"deny"| E["401 / 403 / 404<br/>no side effects"]
    D --> F["HTTP response"]
~~~

In a Spring Security application:

- `SecurityFilterChain` verifies identity, route, method, and security requirements such as CSRF. For example, `POST /api/reports/{id}/approve` requires `ROLE_MANAGER`.
- `Authentication` is supplied by a trusted authentication mechanism (e.g., `UserDetailsService`, OAuth2 Resource Server, session login), never by self-reported frontend JSON.
- **Service/policy** binds the identity to the object and action. For example, `manager` in tenant east cannot approve documents belonging to west.
- Repository/database layers can apply predicates on `owner_id`, `tenant_id`, ACLs, or Row-Level Security to reduce bypass risk across multiple access paths.
- The frontend can use server-provided permission metadata to improve UX. That data **does not replace** checks at request execution time.

In systems where permissions change over time, "the button appeared at 10:00" does not prove permission still holds at 10:05. The server must check at **operation time**, avoiding *time-of-check to time-of-use* (TOCTOU) issues when owner/tenant/membership changes.

## 5. Complete example with Spring Boot and Spring Security

This demo builds a simple API using HTTP Basic to make switching roles easy to reproduce. `ActionsService` holds owner and tenant policies with an in-memory store for tests. This is a **Maven-runnable** learning app; the code in section 6 is illustrative frontend code, not required to run the backend.

**Environment:** Java 17+, Maven 3.9+, Spring Boot **3.5.0** (Spring Security 6.x). Project layout:

~~~text
ui-is-not-authorization-demo/
├── pom.xml
├── src/main/java/com/example/uiauth/
│   ├── UiAuthApplication.java
│   ├── SecurityConfig.java
│   ├── ActionsService.java
│   └── ActionsController.java
└── src/test/java/com/example/uiauth/
    └── UiAuthorizationTest.java
~~~

Credentials `alice:pw`, `bob:pw`, `manager:pw`, `mallory:pw` are strictly for localhost. The sample primarily verifies **server-side permissions**, not a production persistence architecture.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ui-is-not-authorization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
~~~

### 5.2. UiAuthApplication.java

~~~java
package com.example.uiauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UiAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(UiAuthApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.uiauth;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/{id}/cancel")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports/{id}")
                    .hasRole("MANAGER")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports/{id}/approve")
                    .hasRole("MANAGER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Intentionally keep default CSRF protection: Basic credentials can be
        // automatically attached by browsers on state-changing requests.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            user("alice", "USER"),
            user("bob", "USER"),
            user("manager", "MANAGER"),
            user("mallory", "MANAGER")
        );
    }

    private static org.springframework.security.core.userdetails.UserDetails
            user(String username, String role) {
        return User.withUsername(username)
            .password("{noop}pw")
            .roles(role)
            .build();
    }
}
~~~

**Explanation:**

1. `authenticated()` requires a verified identity; `hasRole("MANAGER")` checks functional permission in the HTTP filter chain.
2. The rules open only specific GET/POST routes; other methods or undeclared endpoints fall into `anyRequest().denyAll()`.
3. `SessionCreationPolicy.STATELESS` means HTTP Basic does not rely on a session to remember credentials; clients send credentials on every request. This **does not eliminate** CSRF risk if a browser automatically attaches Basic credentials.
4. `DispatcherType.ERROR`/`FORWARD` are allowed for internal dispatches in this demo. Do not broaden this to `permitAll("/**")`.
5. `{noop}` is strictly for sample passwords. Production requires proper password hashing, TLS, and secret management.
6. Roles and tenants must come from trusted server sources. In this example, roles come from `InMemoryUserDetailsManager` and tenants are mapped in the service. Client-sent `X-Role` headers or `tenant` parameters **do not influence** this decision.
7. HTTP route permissions **do not replace object-level permissions**. Therefore the service must still check tenant and owner after requests pass the filter.

### 5.4. ActionsService.java

~~~java
package com.example.uiauth;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ActionsService {

    private static final Map<String, String> TENANTS = Map.of(
        "alice", "east",
        "bob", "east",
        "manager", "east",
        "mallory", "west"
    );

    private final Map<Long, Order> orders = new ConcurrentHashMap<>();
    private final Map<Long, Report> reports = new ConcurrentHashMap<>();

    public ActionsService() {
        resetFixture();
    }

    // Used to isolate tests; no HTTP endpoint calls this method.
    public void resetFixture() {
        orders.clear();
        reports.clear();
        orders.put(101L,
            new Order(101L, "east", "alice", "OPEN"));
        orders.put(202L,
            new Order(202L, "east", "bob", "OPEN"));
        orders.put(303L,
            new Order(303L, "west", "mallory", "OPEN"));
        reports.put(51L,
            new Report(51L, "east", "PENDING"));
        reports.put(61L,
            new Report(61L, "west", "PENDING"));
    }

    public UserView whoAmI(Authentication auth) {
        String tenant = trustedTenant(auth);
        List<String> authorities = auth.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .sorted(Comparator.naturalOrder())
            .toList();
        return new UserView(auth.getName(), tenant, authorities);
    }

    public OrderView readOrder(long id, Authentication auth) {
        return view(ownedOrder(id, auth));
    }

    public OrderView cancelOrder(long id, Authentication auth) {
        Order order = ownedOrder(id, auth);
        Order changed = new Order(
            order.id(), order.tenant(), order.owner(), "CANCELLED");
        orders.put(id, changed);
        return view(changed);
    }

    public ReportView readReport(long id, Authentication auth) {
        return view(manageableReport(id, auth));
    }

    public ReportView approveReport(long id, Authentication auth) {
        Report report = manageableReport(id, auth);
        Report changed = new Report(
            report.id(), report.tenant(), "APPROVED");
        reports.put(id, changed);
        return view(changed);
    }

    private Order ownedOrder(long id, Authentication auth) {
        String tenant = trustedTenant(auth);
        Order order = orders.get(id);

        if (order == null
                || !order.tenant().equals(tenant)
                || !order.owner().equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return order;
    }

    private Report manageableReport(long id, Authentication auth) {
        String tenant = trustedTenant(auth);
        Report report = reports.get(id);

        // Hide resources belonging to another tenant.
        if (report == null || !report.tenant().equals(tenant)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        // Defense in depth: also check in the service,
        // preventing bypass when called from a non-HTTP entry point.
        if (!hasRole(auth, "MANAGER")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return report;
    }

    private static String trustedTenant(Authentication auth) {
        if (auth == null
                || auth instanceof AnonymousAuthenticationToken
                || !auth.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        String tenant = TENANTS.get(auth.getName());
        if (tenant == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        return tenant;
    }

    private static boolean hasRole(Authentication auth, String role) {
        return auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_" + role));
    }

    private static OrderView view(Order order) {
        return new OrderView(order.id(), order.status());
    }

    private static ReportView view(Report report) {
        return new ReportView(report.id(), report.status());
    }

    private record Order(
        long id, String tenant, String owner, String status) {}

    private record Report(long id, String tenant, String status) {}

    public record OrderView(long id, String status) {}

    public record ReportView(long id, String status) {}

    public record UserView(
        String username, String tenant, List<String> authorities) {}
}
~~~

**Most important takeaway:** `cancelOrder` does not rely on `cancelButton.hidden`; it calls `ownedOrder` to take the **authenticated principal** and compare against the record's owner and tenant. `approveReport` does not trust a client-supplied `X-Role: MANAGER`; it starts from the Spring Security–supplied authentication and verifies that the report belongs to the right tenant. Both mutate state only after policy permits it.

Simple in-memory maps make the authorization branches clear in this lesson. This is **not** an example of real database transactions or atomic updates. Production requires trusted owner/tenant data, predicate-scoped queries, transactions, point-in-time permission checks, concurrency/TOCTOU handling, and business state checks on the order/report before transitioning state.

### 5.5. ActionsController.java

~~~java
package com.example.uiauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ActionsController {

    private final ActionsService actions;

    public ActionsController(ActionsService actions) {
        this.actions = actions;
    }

    @GetMapping("/api/me")
    public ActionsService.UserView me(Authentication auth) {
        return actions.whoAmI(auth);
    }

    @GetMapping("/api/orders/{id}")
    public ActionsService.OrderView order(
            @PathVariable long id, Authentication auth) {
        return actions.readOrder(id, auth);
    }

    @PostMapping("/api/orders/{id}/cancel")
    public ActionsService.OrderView cancel(
            @PathVariable long id, Authentication auth) {
        return actions.cancelOrder(id, auth);
    }

    @GetMapping("/api/reports/{id}")
    public ActionsService.ReportView report(
            @PathVariable long id, Authentication auth) {
        return actions.readReport(id, auth);
    }

    @PostMapping("/api/reports/{id}/approve")
    public ActionsService.ReportView approve(
            @PathVariable long id, Authentication auth) {
        return actions.approveReport(id, auth);
    }
}
~~~

The controller merely forwards `id` and the Spring Security–established `Authentication` to the service. It never accepts `owner`, `tenant`, or `role` from query strings or request bodies to grant permissions.

Important policies must not live **only** in a UI click callback or **only** in the controller: other code might call the service from a batch job, message handler, or new endpoint. In the demo, the service itself enforces owner/tenant permissions. Spring Method Security (`@EnableMethodSecurity`, `@PreAuthorize`) can add another defense layer, provided proxy invocation and resource-specific policies are verified.

## 6. Frontend should reflect permissions, not create them

With React/Vue/Angular or plain JavaScript, you can hide/disable an action if the user is unlikely to be allowed:

~~~javascript
// Illustrative UI snippet; requires a page with an #approveButton element.
async function refreshUiPermissions() {
  const response = await fetch("/api/me", {
    credentials: "same-origin"
  });

  if (!response.ok) {
    document.querySelector("#approveButton").hidden = true;
    return;
  }

  const me = await response.json();
  document.querySelector("#approveButton").hidden =
      !me.authorities.includes("ROLE_MANAGER");
}
~~~

**This is a UX improvement, not security enforcement:**

- If the user lacks the role, hide the button to avoid suggesting impossible actions.
- If the user has the MANAGER role yet the report belongs to another tenant, the button may still appear. The server must return 404/403 per policy.
- If permissions are revoked after the UI renders, the backend must reject the subsequent request even while the button remains visible.
- If the user edits the DOM or sends direct HTTP requests, the backend keeps enforcing the exact same policy.
- While waiting for permission data, avoid briefly flashing sensitive buttons that cause confusion; default to hidden and reveal once trusted data loads, yet **real safety still comes from the backend**.

An API returning **capabilities for a specific resource** can make the UI more accurate, for example:

~~~json
{
  "reportId": 51,
  "capabilities": {
    "canRead": true,
    "canApprove": false
  }
}
~~~

This is an illustrative response format, not included in the sample backend in section 5. Capabilities help the UI avoid showing wrong buttons, yet the backend must **recompute permissions when receiving the action**, never trusting the client sending back `canApprove:true` as authorization proof.

A flawed frontend pattern:

~~~javascript
// WRONG: client-side-only check.
if (currentUser.role === "MANAGER") {
  await fetch("/api/reports/51/approve", {method: "POST"});
}
// The backend API can still be called directly by other clients.
~~~

If the app uses cookie sessions/HTTP Basic, real POSTs must also send a CSRF token per design. This demo keeps CSRF enabled and tests via MockMvc; the `fetch` above merely illustrates insecure logic, **not a runnable approval request**.

## 7. Automated testing: bypassing buttons yet still blocked

Place file `src/test/java/com/example/uiauth/UiAuthorizationTest.java`. Tests go directly through MockMvc **without clicking UI buttons**. That is precisely what this lesson proves: the API must stay secure even when callers bypass the entire frontend.

~~~java
package com.example.uiauth;

import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UiAuthorizationTest {

    @Autowired MockMvc mvc;
    @Autowired ActionsService actions;

    @BeforeEach
    void reset() {
        actions.resetFixture();
    }

    static Stream<Arguments> authorizationCases() {
        return Stream.of(
            Arguments.of("anonymous me", null,
                "GET", "/api/me", 401),
            Arguments.of("alice me", "alice",
                "GET", "/api/me", 200),

            Arguments.of("alice reads own order", "alice",
                "GET", "/api/orders/101", 200),
            Arguments.of("bob cannot read Alice order", "bob",
                "GET", "/api/orders/101", 404),
            Arguments.of("manager cannot read Alice order", "manager",
                "GET", "/api/orders/101", 404),
            Arguments.of("west manager cannot read east order", "mallory",
                "GET", "/api/orders/101", 404),
            Arguments.of("unknown order", "alice",
                "GET", "/api/orders/999", 404),

            Arguments.of("Alice cancels own order", "alice",
                "POST", "/api/orders/101/cancel", 200),
            Arguments.of("Bob cannot cancel Alice order", "bob",
                "POST", "/api/orders/101/cancel", 404),
            Arguments.of("anonymous cannot cancel", null,
                "POST", "/api/orders/101/cancel", 401),
            Arguments.of("manager not owner cannot cancel", "manager",
                "POST", "/api/orders/101/cancel", 404),

            Arguments.of("east manager reads east report", "manager",
                "GET", "/api/reports/51", 200),
            Arguments.of("alice cannot read manager report", "alice",
                "GET", "/api/reports/51", 403),
            Arguments.of("west manager cannot read east report", "mallory",
                "GET", "/api/reports/51", 404),

            Arguments.of("east manager approves east report", "manager",
                "POST", "/api/reports/51/approve", 200),
            Arguments.of("alice cannot approve report", "alice",
                "POST", "/api/reports/51/approve", 403),
            Arguments.of("west manager cannot approve east report", "mallory",
                "POST", "/api/reports/51/approve", 404),
            Arguments.of("west manager approves west report", "mallory",
                "POST", "/api/reports/61/approve", 200),
            Arguments.of("anonymous cannot approve report", null,
                "POST", "/api/reports/51/approve", 401),
            Arguments.of("GET cannot approve report", "manager",
                "GET", "/api/reports/51/approve", 403)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("authorizationCases")
    void requestIsCheckedOnServer(
            String description, String username,
            String method, String path, int expectedStatus)
            throws Exception {
        MockHttpServletRequestBuilder request = switch (method) {
            case "GET" -> get(path);
            case "POST" -> post(path).with(csrf());
            default -> throw new IllegalArgumentException(method);
        };

        if (username != null) {
            request.with(httpBasic(username, "pw"));
        }
        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void forgedRoleHeaderCannotApproveReport() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("alice", "pw"))
                .with(csrf())
                .header("X-Role", "MANAGER")
                .param("role", "MANAGER")
                .param("tenant", "east"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void otherTenantManagerCannotApproveReport() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("mallory", "pw"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void unownedOrderCannotBeCancelled() throws Exception {
        mvc.perform(post("/api/orders/101/cancel")
                .with(httpBasic("bob", "pw"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/orders/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(jsonPath("$.status").value("OPEN"));
    }

    @Test
    void allowedOperationsReallyChangeState() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("manager", "pw"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("APPROVED"));

        mvc.perform(post("/api/orders/101/cancel")
                .with(httpBasic("alice", "pw"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("CANCELLED"));
    }

    @Test
    void csrfStillProtectsUnsafeMethods() throws Exception {
        mvc.perform(post("/api/reports/51/approve")
                .with(httpBasic("manager", "pw")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/51")
                .with(httpBasic("manager", "pw")))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
~~~

**What the tests prove:**

1. **20 HTTP cases** across caller + resource + action. Not a single test depends on `hidden`, `disabled`, or a React component.
2. Alice sending `X-Role: MANAGER`, `role=MANAGER`, and `tenant=east` still receives 403 on the approve route. Client-asserted values never escalate privileges.
3. Mallory genuinely has `ROLE_MANAGER`, yet belongs to tenant west and is denied on the east report (404). **A valid role is not enough to cross a data boundary**.
4. Bob cannot cancel Alice's order even though both belong to tenant east and have `ROLE_USER`. This is object-level authorization preventing IDOR/BOLA.
5. After rejected requests, the tests re-read report/order state to confirm **no side effects occurred**. Checking only 403/404 statuses could miss a service mutating data before throwing an error.
6. POST requests use `with(csrf())` to isolate authorization outcomes. A dedicated test omits CSRF to prove it remains protected.
7. Testing only one account or only happy paths often misses missing authorization checks. What matters is having **allowed/denied pairs** for the same action/resource.

In the demo, `resetFixture()` resets the maps before each test. Tests are expected to run sequentially; enabling parallel tests with a singleton fixture can cause interference. Real systems should use transaction rollbacks or isolated test data to ensure repeatability.

## 8. Running the program and comparing results

In the `ui-is-not-authorization-demo` directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

With available dependencies and matching code versions, `mvn test` is **expected** to succeed; this is an execution instruction, **not a claim that the command was run in this article**. Once started, the server defaults to `http://localhost:8080` if the port is free.

Call the GET endpoints to observe the policy:

~~~bash
curl -i -u alice:pw http://localhost:8080/api/me
curl -i -u alice:pw http://localhost:8080/api/orders/101
curl -i -u bob:pw http://localhost:8080/api/orders/101
curl -i -u manager:pw http://localhost:8080/api/reports/51
curl -i -u alice:pw http://localhost:8080/api/reports/51
curl -i -u mallory:pw http://localhost:8080/api/reports/51
~~~

Expected statuses in order: `200`, `200`, `404`, `200`, `403`, `404`.

Example `GET /api/me` response content for the manager account:

~~~json
{
  "username": "manager",
  "tenant": "east",
  "authorities": ["ROLE_MANAGER"]
}
~~~

Example successful report response:

~~~json
{"id":51,"status":"PENDING"}
~~~

**POST via curl must include a CSRF token when using this browser/Basic flow.** Because the demo keeps CSRF protection enabled, `curl -X POST -u manager:pw ...` without a CSRF token may return 403 **even for an authorized manager**. Do not use that to claim the backend policy rejected or allowed the action. Use `MockMvc` with `with(csrf())` in section 7 to test authorization cleanly in isolation. When building a real frontend, design CSRF endpoints/cookies/form tokens appropriate to the application's client rather than disabling CSRF just to make a demo POST run easily.

On PowerShell, use `curl.exe` if `curl` is aliased to `Invoke-WebRequest`. Exact JSON/error header details depend on framework configuration; primary tests check status codes and protected data.

## 9. Proper backend controls

### 9.1. At the route: define permissions per HTTP method

~~~java
// Illustrative fragment inside authorizeHttpRequests(...).
.requestMatchers(HttpMethod.POST, "/api/reports/{id}/approve")
    .hasRole("MANAGER")
.anyRequest().denyAll()
~~~

Separate reading reports (GET) from approving them (POST); avoid overly broad wildcard rules like `.requestMatchers("/api/reports/**").authenticated()` when some actions require stronger roles. Any new endpoint must be reviewed and given an explicit rule before `denyAll`, never relying on the frontend lacking a button yet.

### 9.2. In the service: check principal, tenant, and object relationship

~~~java
// Illustrative pseudocode — not a standalone runnable method.
if (!report.tenantId().equals(authenticatedTenantId)) {
    denyNotFound();
}
if (!hasPermission(authenticatedUser, "APPROVE", report)) {
    denyForbidden();
}
approve(report);
~~~

Never read `authenticatedTenantId` from an unverified client header; it must come from **verified and validated** session/JWT claims or a server-side mapping. When a product has shared permissions/ACLs, policies must also check owner, membership, action, and record state.

### 9.3. In the database: enforce permissions inside queries/mutations

For private resources:

~~~sql
SELECT id, status
FROM orders
WHERE id = :requestedId
  AND owner_user_id = :authenticatedUserId
  AND tenant_id = :authenticatedTenantId;
~~~

Updates that check permissions simultaneously:

~~~sql
UPDATE reports
SET status = 'APPROVED'
WHERE id = :requestedReportId
  AND tenant_id = :authenticatedTenantId
  AND status = 'PENDING';
~~~

This `UPDATE` statement **does not check the MANAGER role by itself**—the role must be verified at the service/policy layer or incorporated into a trusted authorization check prior to mutation. You should also verify affected row counts, handle transactions/idempotency/auditing, and enforce business state conditions. Avoid reading `id` → checking permissions at one moment → updating by `id` without protecting against concurrent permission changes.

### 9.4. Method Security as an additional defense layer

~~~java
// Requires @EnableMethodSecurity and a provided "reportPolicy" bean.
// Conceptual only; NOT part of the runnable Java sample in section 5.
@PreAuthorize("@reportPolicy.canApprove(authentication, #reportId)")
public void approve(Long reportId) {
    // Call service/repository with policy-constrained query/mutation.
}
~~~

`@PreAuthorize("hasRole('MANAGER')")` only protects functional permission and does not verify which tenant owns the report. Method security typically runs via a Spring AOP proxy, so calling `this.approve(...)` directly within the same bean may bypass the interceptor. Core policies should still enforce proper boundaries at the service/data layer.

## 10. Common client-tampering techniques and why they fail against a proper backend

### Removing hidden/disabled

A user sets `button.hidden = false` or removes `disabled`. This only modifies the browser DOM; it does not elevate server roles. When clicked, the HTTP request must be validated independently. The UI may display a helpful UX message on 403, without turning that failure into a fake success.

### Modifying URLs or IDs

Changing `/api/orders/101/cancel` to `/api/orders/202/cancel`. The server must compare the owner of **that exact order ID** against the authenticated principal, never assuming the client clicked a button for their own order.

### Sending role, user, or tenant in the request

~~~http
POST /api/reports/51/approve?role=MANAGER&tenant=east HTTP/1.1
X-Role: MANAGER
X-User: manager
~~~

These headers/query parameters must not be used to establish identity. In the demo, the caller remains the account verified by actual Basic credentials. When a reverse proxy/gateway forwards identity via headers, trust those headers only across a properly configured **trust boundary and inter-service authentication**; never allow Internet clients to supply those headers themselves.

### Altering permission API responses

A client can change `{"canApprove":false}` to `{"canApprove":true}` in memory or UI rendering; the server must never accept client-returned values to grant access. Button visibility is not a security token.

### Calling the API from another client

The API accepts HTTP independently of the page's JavaScript. You cannot expect every request to pass through `onClick`, frontend route guards, or confirmation modals. The backend must handle **intentionally malformed/crafted requests** according to policy.

### Stale UI or outdated caches

If a user used to be a manager and the UI still shows the button after their role is revoked, the backend must still reject requests at execution time. Frontend role/capability data is purely advisory for the UI; authorization decisions must use current, trusted data with appropriate cache/invalidation policies.

## 11. Distinguishing 401, 403, 404, and CSRF

| Status | Meaning in the example | Does it prove object permissions were checked? |
|---|---|---|
| `401` | Anonymous/invalid credentials on an HTTP Basic protected route | No; the request may have stopped at authentication |
| `403` | Authenticated principal missing role; or POST missing CSRF token | Not necessarily; must know which filter returned the error |
| `404` | ID does not exist or is hidden from this principal/tenant | May result from a scoped query/policy, yet requires no-leak/no-side-effect tests |
| `200` | Operation permitted and processed | Must verify the right data was affected, not just a success status |

For **CSRF**: inspect `X-CSRF-TOKEN` or the matching form parameter per app design and ensure `POST/PATCH/DELETE` requests are not blocked by CSRF when testing authorization. However, never use `csrf().disable()` by default on apps using browser credentials; instead use MockMvc `with(csrf())` for authorization test cases and test CSRF separately.

For **404 to hide resource existence**, return the same response for non-existent IDs and other users' IDs. If an API intentionally returns 403 when a caller is allowed to know a resource exists yet lacks edit permission, that can be reasonable too; what matters is a **consistent policy** that leaks no data via messages, bodies, headers, or caching.

## 12. Test plan sufficient to prevent "security by hiding buttons"

Do not test only React/Vue render/hidden state. Build a matrix across three axes:

| Resource | Action | Caller group | What to verify |
|---|---|---|---|
| Order 101 | READ | Alice owner | 200 + right data |
| Order 101 | READ | Bob with same role USER | 404 + order not leaked |
| Order 101 | CANCEL | Bob non-owner | 404 + status remains OPEN |
| Order 101 | CANCEL | Alice owner | 200 + status CANCELLED |
| Report 51 | READ | Alice USER | 403 |
| Report 51 | APPROVE | Alice USER, forged X-Role | 403 + PENDING |
| Report 51 | APPROVE | East tenant manager | 200 + APPROVED |
| Report 51 | APPROVE | West tenant manager | 404 + PENDING |
| Any protected API | READ/POST | Anonymous | 401 or matching entry point |
| Route outside allowlist | Any | Logged-in/manager | Denied by deny-all |
| Sensitive POST | No CSRF token | Authorized user | 403, no side effects |
| Revoked permissions | Old action still has button | Recently demoted user | Backend denies immediately |

Testing **the same resource across multiple principals** is vital; testing only with an authorized user will miss bypasses. For mutations, assert database state after rejected requests, not only HTTP status. For multi-tenant permissions, include at least one high-privilege user **from another tenant**.

An E2E UI test can verify a button is absent or disabled when a user lacks permission, yet that is a **UX test**. You must have backend integration tests **sending requests directly** to prove security.

### Two complementary testing layers

- **Frontend/UI tests:** element stays hidden; route guards work; reasonable 403/404 error messages; permissions refresh on reload. Must never serve as the sole proof of authorization.
- **Backend/HTTP tests:** call APIs directly with different credentials, right/wrong tenants, swapped IDs, forged headers, valid CSRF, and verify no side effects.
- **Repository/database integration:** verify owner/tenant predicates in queries and write/rollback behavior. Use Testcontainers/H2 matching real DB semantics; fake maps do not prove production transaction/row isolation.
- **Authorized pentest/security review:** inspect legacy routes, bulk endpoints, file URLs, exports, GraphQL resolvers, admin paths, and paths outside the main UI.

## 13. Common design mistakes

1. **"Hiding the button is enough because users won't know the URL."** Endpoints can still be called with HTTP clients; URLs/IDs can be guessed, read from Network logs, or discovered via other APIs.
2. **"The frontend already checked the role before calling."** The backend has no proof requests came from the frontend; roles must be checked server-side.
3. **Using only `.authenticated()` on sensitive endpoints.** Being logged in does not mean permission to APPROVE, DELETE, or SHARE.
4. **Checking roles without checking owner/tenant.** A west MANAGER must not automatically approve east reports.
5. **Trusting `isAdmin`, `role`, or `ownerId` in JSON/body.** Clients can alter those values; verify via server identity/policy.
6. **Returning raw entities directly.** Easily exposes owner/tenant/internal fields not meant to be read; use DTOs per contract.
7. **Forgetting GET/list/export/download and batch endpoints.** Permissions apply beyond write-action buttons; data can leak via read endpoints or files.
8. **Checking permissions after writing.** Returning 403 after mutating the DB is a critical bug; authorize before mutation inside proper transactions.
9. **Using an unmodeled global ADMIN role.** Multi-tenant systems must clearly distinguish tenant admins from platform-wide admins and audit privileged permissions.
10. **Disabling CSRF to make POST testing easier.** A 403 from CSRF differs from a 403 from a missing role; keep proper defenses and separate tests.
11. **Relying on hard-to-guess UUIDs/IDs as authorization.** Knowing an ID does not grant access; enforce object-level protection.
12. **Skipping policies when the backend runs from cron/jobs/message queues.** Controller route guards do not protect services invoked through other entry points.
13. **Testing UI rendering without testing APIs.** UIs can hide buttons while BOLA/BFLA (broken function-level authorization) still exists.
14. **Caching private responses solely by ID.** Risks serving another user's data when permissions/tenants change; scope caches by policy or re-authorize before returning.
15. **Trusting client capabilities for too long.** Users may be revoked after the UI loads; server decisions must use current valid state.
16. **Allowing overly broad path/method wildcards.** New endpoints may be unintentionally exposed; use explicit rules and a deny-all fallback when policy demands it.

## 14. Architectural improvements by maturity level

### Level 1 — Sufficient for a small application

- Spring Security authenticates requests and protects sensitive endpoints by method/role.
- Services take a trusted `Authentication` and verify resource owner and tenant.
- The frontend hides buttons based on role/capability info to avoid confusion, without making authorization decisions.
- MockMvc includes cases directly hitting APIs with unauthorized accounts.

### Level 2 — Multiple features and resources

- Centralize policies such as `canReadOrder`, `canCancelOrder`, and `canApproveReport` instead of copying scattered `if` statements into every controller.
- Separate authorization per **action**, avoiding treating `ROLE_MANAGER` as blanket permission for every operation.
- Add method security as needed, DTOs, auditing, and a test matrix; ensure policies cannot be bypassed via other service invocations.
- Scope data queries by owner/tenant right at the DB; bulk/read/write share the same boundaries.

### Level 3 — Multi-tenant, multi-data-source, multi-service

- Resolve identity, membership, tenant, and ACLs from trusted sources; validate tokens/claims and plan revocation/caching.
- Use a policy decision component or suitable ABAC/ReBAC model, audit privileged decisions, and enforce service-to-service checks.
- Enforce tenants in queries and transactional mutations; where DB RLS is supported, add defense-in-depth.
- Enforce permissions across background jobs, download URLs, exports, message consumers, and API gateways; never rely on UI or gateway alone.
- Measure coverage by policy branches, endpoints, and protected data, not solely by code coverage.

## 15. Self-check questions and exercises

1. If a user opens DevTools and removes `hidden` from the "Approve" button, where is the only place that can enforce rejecting the request?
2. What is the difference between `authenticated()`, `hasRole("MANAGER")`, and checking the tenant of report 51?
3. Why does Mallory—who holds a real `ROLE_MANAGER`—still receive 404 for report 51?
4. If the server trusts a client-sent `X-Role: MANAGER` header, how does a privilege escalation scenario unfold?
5. Why must we test "Bob cancels Alice's order" even when both have `ROLE_USER` and belong to the same tenant?
6. If the frontend showed `canApprove=true` at 10:00 yet the user's permission was revoked at 10:05, what information must the server base its decision on?
7. Why is a 403 status on POST insufficient to prove method authorization works when CSRF is enabled?
8. If a POST is rejected yet data changed anyway, what assertion must the test add?
9. How should authorization for `DELETE /api/reports/{id}`, file exports, and bulk updates be designed per action/resource?
10. When integrating a mobile app that has no HTML buttons, which conditions must the API protect?
11. How should the frontend present distinct UX responses for `401`, `403`, and `404` without leaking resource existence?
12. Why might a tenant policy enforced only in a controller fail to protect a job calling the repository directly?

**Conclusion:** Hiding or disabling buttons is sound UI design, **not authorization**. The security boundary lives on the backend: verify principal → check role/scope for the action → check object owner/tenant/ACL → only then read or mutate data. Tests must **bypass the UI, send HTTP requests directly, and verify data stays unchanged when rejected**.

## Official documentation for further reading

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Testing MockMvc and Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API Security Top 10 — Broken Function Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/)
