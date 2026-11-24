# Roles, Permissions, and Token Scopes: Distinguishing Role, Permission, and Scope

In Spring Security, the three terms **role**, **permission**, and **scope** frequently appear together in access control, yet they answer different questions. What business operations can someone with the ADMIN role perform? Does an action require `orders:write` or just `orders:read`? Does an access token granted the `orders.read` scope allow the application to call every order API?

If you collapse all three concepts into a single "role" field, the design easily grants overly broad privileges. If you check a token's scope while ignoring per-order ownership, a valid user can still view someone else's order. If you write `hasRole("ADMIN")` with a JWT carrying only a `scope` claim, Spring Security may return 403 due to lacking the `ROLE_ADMIN` authority. This lesson explains the **boundaries between identity, role, operation permission, token scope, and permissions on specific resources**, and shows how they become `GrantedAuthority` instances and are evaluated.

The lab uses **Java 17+, Spring Boot 3.3.6, Spring Security 6.x, Spring MVC, and MockMvc**. The runnable portion uses **HTTP Basic + in-memory accounts** to illustrate roles and permissions clearly. The OAuth2/JWT section is a **separate deployment model** specifying dependencies and Identity Provider requirements, without using fake JWTs or skipping signature verification.

## 1. Questions Each Concept Answers

| Concept | Core question | Example | Who typically defines/grants it? |
| --- | --- | --- | --- |
| **Role** | Which responsibility group does the subject hold in the system? | USER, SUPPORT, ACCOUNTANT, ADMIN. | Identity management system, administrative group, or business domain. |
| **Permission** | Which specific action is the subject allowed to perform? | orders:read, orders:write, refunds:approve. | Application/domain, authorization policies, permission administration. |
| **Scope (token scope)** | What kinds of access does an issued OAuth2 credential allow the client to request at the resource server? | orders.read, orders.write, profile. | Authorization Server per client registration, grant, consent, and policy. |
| **Object-level authorization** | On **which object** may the subject perform the action? | Alice views only Alice's orders; support sees only customers in assigned tenants. | Service/domain, data permission system, tenant/ownership rules. |

A useful way to view them:

- **Role** is a coarse-grained group of responsibilities.
- **Permission** is a clearly named action on a resource type.
- **Scope** bounds the **capabilities expressed in an access token or access grant**. A token scope does not automatically prove a user owns a record, nor does it let an API bypass internal policies.
- **Resource relationship** (owner, tenant, department, order status, monetary threshold) determines whether an abstract permission may be exercised **on a concrete object**.

These groups **can be mapped to one another under trusted policies**, yet they are not three synonyms. Permission names are conventions chosen by the project; Spring Security does not inherently understand the business meaning of the string `orders:read`.

## 2. Distinguish Authentication and Authorization First

**Authentication:** verifying identity evidence via a trusted mechanism. For example, HTTP Basic checks a username/password pair; an OAuth2 Resource Server checks an access token via a decoder/introspection and applicable conditions.

**Authorization:** after obtaining a valid `Authentication`, deciding which methods/paths may be called and which resources may be acted upon.

~~~text
HTTP request
    |
    v
Verify credentials via appropriate mechanism
    |
    v
Authentication(principal, authorities, ...)
    |
    +--> Needs role?       ROLE_ADMIN?
    |
    +--> Needs permission? orders:read?
    |
    +--> Needs scope?      SCOPE_orders.read?
    |
    +--> Needs object access? ownerId / tenantId / state?
    |
    v
Allowed --> Controller/Service processes
Denied  --> 401 or 403/404 depending on context, no data leaked
~~~

Note that the diagram is **conceptual**. In an application, role/permission/scope checks may live at the URL layer, Service/method layer, or a custom `AuthorizationManager`; they do not all have to exist on every request. Object-level checks belong wherever authoritative data is available.

Never trust an `X-Role: ADMIN` header, a `userId=alice` query parameter, or a freshly Base64-decoded JWT payload as proof of identity or permissions. The authentication mechanism must verify credentials before mapping them to authorities.

## 3. Role — Responsibility Group, Not a Specific Action

Roles typically describe **groups of responsibilities**:

| Role | Assumed business meaning | Expected permissions when granted by the system |
| --- | --- | --- |
| USER | Customer/employee using basic features. | Read their own valid orders. |
| ORDER_EDITOR | Someone permitted to edit orders within assigned scope. | Read and create/update permitted orders. |
| SUPPORT | Limited customer support. | View support info per tenant and purpose. |
| FINANCE | Finance staff. | View transactions, propose or approve within limits. |
| ADMIN | Administrator of a system scope. | A specifically defined set of administrative operations. |

**A role name does not automatically carry permissions in Spring Security.** For example, `ROLE_ADMIN` does not inherently include `orders:read`, `refunds:approve`, or `ROLE_USER`. The system must explicitly grant those authorities, configure a role hierarchy, or define an explicit policy if ADMIN is meant to subsume other groups' permissions.

A role like ADMIN should also **be scoped**: an ADMIN of tenant A might not administer tenant B; a system-wide "SUPER_ADMIN" is highly sensitive and must be restricted.

### 3.1. ROLE_ in Spring Security

Spring Security represents granted permissions with **`GrantedAuthority`**, typically a string in `SimpleGrantedAuthority`. Under the default prefix setup:

~~~java
// Expression fragments used in SecurityFilterChain or @PreAuthorize:
hasRole("ADMIN")                  // checks authority "ROLE_ADMIN"
hasAuthority("ROLE_ADMIN")        // checks exact string "ROLE_ADMIN"
hasAuthority("ADMIN")             // checks exact string "ADMIN", different from the two lines above
~~~

In Spring Security, **`hasRole("ADMIN")` is typically shorthand for checking `ROLE_ADMIN`**. The role prefix can be reconfigured; this lesson uses the default `ROLE_`. Do not write `hasRole("ROLE_ADMIN")` when the API expects an unprefixed role name; choose `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` according to your intent.

In `UserDetailsBuilder`, **`roles("ADMIN")` typically adds `ROLE_ADMIN`**. **`authorities("ROLE_ADMIN", "orders:read")` grants the authority list exactly as listed**. If combining `roles()` and `authorities()`, understand the builder may replace the previously set authorities; in the complete example below we call **`authorities(...)` once** to avoid confusion.

### 3.2. Role-Based Access Control (RBAC)

RBAC organizes authorization through relationships:

~~~text
User / Service Account
    |
    v
Assigned Roles
    |
    v
Role -> Permissions (application policy)
    |
    v
Allowed actions on a resource type
    |
    v
Additional condition checks on the specific resource
~~~

RBAC helps manage users by responsibility and simplifies granting permissions. Yet for multi-tenant, ownership, or limit-based business rules, roles alone are insufficient. A SUPPORT role does not imply permission to read every customer's profile.

**Role hierarchy** only works when intentionally configured. For example, `ADMIN > STAFF > USER` can be used in a system, but it is not a Spring Security default. Test permissions derived from a hierarchy and ensure lower roles never inherit unintended privileges.

## 4. Permission — Functional Operation Permission

Permissions describe **permitted action types**, making them easier to control than overly broad roles. A naming convention might look like:

~~~text
orders:read
orders:write
orders:cancel
refunds:request
refunds:approve
users:invite
users:disable
reports:export
~~~

These are **application-designed names**, not a list defined by Spring Security. We use colons in permissions to distinguish them from dots in OAuth scopes in the example. No special mechanism is triggered merely because a string contains a colon.

A good permission needs a clear **action and resource-type target**:

- `orders:read`: read order info within granted scope.
- `orders:write`: create/update orders if business rules allow.
- `refunds:approve`: approve refunds within job scope.
- `reports:export`: export reports; may require additional checks on data volume or role.

### 4.1. Permission vs. Role

Suppose Alice is a USER and Bob is an ORDER_EDITOR. If both have `ROLE_USER`, checking only `hasRole("USER")` cannot separate readers from writers. You can grant:

| Principal | Authenticated authorities | Consequence |
| --- | --- | --- |
| alice | ROLE_USER, orders:read | Can read valid resource types; no write permission yet. |
| bob | ROLE_USER, orders:read, orders:write | Can read, and can invoke write operations when data conditions hold. |
| viewer | ROLE_USER | Has role USER but has not been granted orders:read. |
| admin | ROLE_ADMIN, orders:read, orders:write, refunds:approve | Can perform listed operations, while still subject to object/tenant policies. |

**`ROLE_USER` does not automatically imply `orders:read`**. If policy intends USER to have read access, the system also grants `orders:read` when building `Authentication`, or defines an explicit role → permission mapping.

### 4.2. hasAuthority and hasPermission Differ

**`hasAuthority("orders:write")`** checks whether `Authentication` contains a `GrantedAuthority` with that exact string. If present, it passes the authority check. It **does not query the orders table** and **does not check amounts/limits**.

**`hasPermission(...)`** in method-security expressions is a hook for a **`PermissionEvaluator`** or a customized mechanism to check object-level permissions. It **does not automatically know** owners, tenants, or business rules without an appropriate implementation.

Illustrative example:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
public OrderView readOrder(long id) {
    // Checks coarse permission only; still needs owner/tenant check.
    throw new UnsupportedOperationException("illustration only");
}
~~~

This is a **non-standalone code fragment**, as order lookup and owner checks are omitted. In the runnable example below, we place the owner check inside the Service and return data only when both the permission and object-level rules are satisfied.

### 4.3. Limitations of Purely String-Based Permissions

If thousands of dynamic permissions are baked straight into a JWT or session, revoking permissions mid-lifetime can lag. Sensitive privileges like refunds need current state, tenant, limits, dual approval, timing, and auditing. Do not model all dynamic rules solely as a long-lived list of strings.

## 5. Scope — Access Scope of an OAuth2 Token

**Scope is an OAuth 2.0 concept.** It describes the access scope granted to a client within an access grant/access token. The Authorization Server decides scopes based on client registration, grant type, consent, and policy; the Resource Server uses verified token information to bound operations.

Suppose a client is granted:

~~~text
orders.read
orders.write
profile
~~~

These scopes are **illustrative names**. Real scope names depend on the API contract and Authorization Server. A token carrying `orders.read` means it can satisfy **a scope-based access condition** of the API, not bypass all business authorization.

### 5.1. Is a Scope a User Role?

**No.** An access token can represent:

- A user via the authorization code flow or another delegated authorization flow.
- A service/client via **client credentials** with no end user at all.
- A caller delegated a restricted set of scopes.

For instance, a data-sync service may hold scope `reports.read` without holding a human user's `USER` role; conversely, an employee with `ADMIN` role in system A does not automatically receive an access token carrying scopes for system B.

A resource server must distinguish **user identity**, **client identity**, **token audience**, and **scope**. Avoid deriving an order's `ownerId` from `client_id` when the token does not represent a user. If the operation requires a human user, verify the delegation flow and true principal.

### 5.2. Scope Alone Does Not Express Full Data Permissions

Suppose Alice's access token is valid, has scope `orders.read`, and was issued for `orders-api`. Alice requests `GET /api/orders/102`, but order 102 belongs to Bob.

To allow access, **all** of these must hold simultaneously:

1. The token is verified, unexpired, and intended for the right resource server.
2. The token has a matching scope for the API, such as `orders.read`.
3. If the API requires internal permissions or role policies, the principal satisfies them via trusted mapping.
4. Alice is allowed to view **that exact order 102** per owner/tenant/policy; in this example the answer is **no**.

Holding a scope does not make the user an owner. Nor does a token with `orders.write` automatically allow reading every order if the API defines write separately. Read/write relationships must be explicitly defined; never assume write implies read.

### 5.3. Where Do Scopes Usually Appear?

In a JWT access token, the Authorization Server may issue claims:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

This JSON only **illustrates claims**, not a validly signed JWT. Real tokens also include fields like `exp`, `iat`, `nbf`, and a `header.payload.signature` structure per standard/design. Some providers use a **`scp`** claim as a list; the Resource Server must map according to the standard and actual config.

**A merely Base64-decoded JWT proves nothing about trust.** Signatures or introspection must be verified according to token format, issuer, expiration, and the application's audience/client/scope requirements. A scope in a token sent to an API with the wrong audience must not be accepted just because the scope string matches.

## 6. How Role, Permission, and Scope All Enter GrantedAuthority

In Spring Security, **`GrantedAuthority`** is the common contract used by the framework to check permissions at runtime. Strings from different origins can coexist in `Authentication#getAuthorities()` **if the authentication mechanism/converter produced them**.

| Source | Source value | Authority in example model | Check condition |
| --- | --- | --- | --- |
| UserDetails role | roles("ADMIN") | ROLE_ADMIN | hasRole("ADMIN") or hasAuthority("ROLE_ADMIN"). |
| UserDetails permission | authorities("orders:read") | orders:read | hasAuthority("orders:read"). |
| Verified JWT scope | scope = "orders.read" | SCOPE_orders.read by default converter | hasAuthority("SCOPE_orders.read"). |
| Verified JWT scope | scp = ["orders.write"] | SCOPE_orders.write when converter handles format | hasAuthority("SCOPE_orders.write"). |
| JWT custom roles | roles = ["ADMIN"] | **Does not automatically** become ROLE_ADMIN under default config | Needs converter if app decides to trust this claim. |
| User's ownership | ownerId = alice in DB | **Does not automatically** become a GrantedAuthority | Checked at object level in domain/Service. |

**`hasRole`**, **`hasAuthority`**, and **scope mapping** are distinct operations:

~~~java
// Expression fragments in config/annotations (not a standalone runnable Java file).
hasRole("ADMIN")                        // requires ROLE_ADMIN
hasAuthority("orders:read")             // requires exact orders:read
hasAuthority("SCOPE_orders.read")       // requires exact SCOPE_orders.read
~~~

Do not write `hasRole("orders.read")` to check an OAuth2 scope. Also do not write `hasAuthority("orders:read")` expecting the default Resource Server to strip the `SCOPE_` prefix automatically.

### 6.1. Why Do Prefixes Matter?

An application may receive three valid authorities:

~~~text
ROLE_ADMIN
orders:read
SCOPE_orders.read
~~~

They are **three distinct strings**. Spring Security infers no relationship among them unless you define an explicit mapping or policy. Prefixes distinguish **internal roles** from **token-derived scopes**, while reducing the risk of a scope named `ADMIN` being mistaken for an administrative role.

Changing the authority prefix to `ROLE_` for all scopes can grant higher privileges than intended. Change conversion only after reviewing issuer, audience, claim structure, token issuance, and target policy.

### 6.2. Spring Security Does Not Automatically Turn Custom JWT Roles into Internal Roles

If a JWT contains:

~~~json
{
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
~~~

A default JWT converter typically produces authorities from `scope`/`scp` such as **`SCOPE_orders.read`**, and does not automatically read `roles` to produce **`ROLE_ADMIN`**. If the Identity Provider guarantees a trusted `roles` claim and the application wants to use it, you must define a suitable converter and verify the role mapping with tests.

Important: **never read `roles` from an unverified JWT**. Granting `ROLE_ADMIN` to any token claiming `roles=ADMIN` is a critical vulnerability.

## 7. Multi-Layered Authorization Model

A solid policy typically has layers:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Authentication: Basic / session / verified access token"]
    B --> C["Endpoint policy: authenticated / role / permission / scope"]
    C --> D["Service policy: action, state, limits"]
    D --> E["Object policy: ownerId, tenantId, granted relationship"]
    E --> F["Action allowed"]
    C --> G["Denied"]
    D --> G
    E --> G
~~~

Order application example:

| Action | General condition | Specific resource condition |
| --- | --- | --- |
| View order | Permission orders:read or scope orders.read, per API and identity model. | Order belongs to user/tenant or caller holds valid delegated read rights. |
| Create order | Permission orders:write or matching scope. | Prices, products, customer state, and tenant valid; never trust client-submitted prices. |
| Edit order | Permission orders:write. | Order is in an editable state and caller holds granted relationship. |
| Refund | Permission refunds:approve; may require higher role or auth level. | Limits, segregation of duties, payment state, approval, audit. |
| User admin | Role ADMIN and permission users:manage (if policy requires). | Same tenant/admin scope; prevent self-escalation. |

**Multiple conditions combine with AND**, unless business logic intentionally designs OR: holding the right role **and** specific permission **and** object access when all are required. Whenever an expression uses OR, you must prove one branch does not bypass critical constraints.

In multi-tenant systems, **RBAC + ABAC/ReBAC** is often required: roles/permissions for general capability, resource attributes and relationships for data scope. Relying on a single role string in a token is not enough.

## 8. Runnable Example: Roles and Permissions in Spring Boot

This demo focuses on the **two concepts role/permission** using HTTP Basic, and then section 11 explains scope/JWT as a separate token mechanism. That way you can run tests without needing an IdP or fake-signed JWTs.

**Requirements:** JDK 17+, Maven 3.9+, port 8080. Spring Boot 3.3.6 is pinned for this lab; in real deployments choose a supported release line and keep patches up to date.

~~~text
role-permission-demo/
  pom.xml
  src/main/java/com/example/roleperm/
    RolePermissionApplication.java
    OrderView.java
    OrderService.java
    ApiController.java
    SecurityConfig.java
  src/test/java/com/example/roleperm/
    AuthorizationTests.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>role-permission-demo</artifactId>
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
~~~

### 8.2. RolePermissionApplication.java

~~~java
package com.example.roleperm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RolePermissionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolePermissionApplication.class, args);
    }
}
~~~

The main class sits in the root package `com.example.roleperm`, so Spring Boot discovers Controller, Service, and Configuration beans in this package.

### 8.3. OrderView.java

~~~java
package com.example.roleperm;

public record OrderView(long id, String owner, String status) {
}
~~~

Java records are built into Java 17. This is a DTO for demo data, not a JPA entity. In real applications, avoid returning raw entities that contain secrets or fields the caller is not permitted to read.

### 8.4. OrderService.java

~~~java
package com.example.roleperm;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final Map<Long, OrderView> orders = Map.of(
        101L, new OrderView(101L, "alice", "CREATED"),
        102L, new OrderView(102L, "bob", "PAID")
    );

    @PreAuthorize("hasAuthority('orders:read')")
    public OrderView read(long id, Authentication authentication) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }

        boolean isAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        if (!isAdmin && !order.owner().equals(authentication.getName())) {
            throw new AccessDeniedException("Order access denied");
        }
        return order;
    }

    @PreAuthorize("hasAuthority('orders:write')")
    public String create(Authentication authentication) {
        // Demo only proves call permission, does not write to database.
        return "created:" + authentication.getName();
    }

    @PreAuthorize("hasAuthority('refunds:approve')")
    public String approveRefund() {
        // Demo only proves call permission, does not process refund.
        return "refund-approved";
    }
}
~~~

**Why check twice?**

- **`@PreAuthorize`** checks the coarse permission before executing the Service method: `orders:read`, `orders:write`, or `refunds:approve`.
- `read(...)` also checks **owner**: Alice holding `orders:read` still cannot view Bob's order. ADMIN in the demo is allowed to view both orders, though that is an **illustrative business choice**; if tenant boundaries exist, even ADMIN must be restricted to managed tenants.
- If the order does not exist, the Service returns 404. If lacking permission to read someone else's order, the Service throws `AccessDeniedException`, resulting in an access denial per Spring Security configuration.
- `create` and `approveRefund` only return strings to test permissions; they perform no real write or refund side effects.

Protecting at the Service layer ensures the same business rule holds when called from multiple Controllers. For tasks running outside HTTP (jobs, message consumers), establish an explicit principal/service identity or appropriate policy; never rely on an absent `Authentication` to skip permissions.

**`@PreAuthorize` only works when method security is enabled** and calls pass through a supported Spring bean proxy. Self-invocation inside the same class can bypass the proxy; test through real call paths.

### 8.5. ApiController.java

~~~java
package com.example.roleperm;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    private final OrderService orders;

    public ApiController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/orders/{id}")
    public OrderView readOrder(
            @PathVariable long id, Authentication authentication) {
        return orders.read(id, authentication);
    }

    @PostMapping("/orders")
    public String createOrder(Authentication authentication) {
        return orders.create(authentication);
    }

    @PostMapping("/refunds")
    public String approveRefund() {
        return orders.approveRefund();
    }
}
~~~

The Controller does not read roles from client-sent headers. It passes the `Authentication` verified by Spring Security to the Service, where permissions and object-level access are enforced.

### 8.6. SecurityConfig.java

~~~java
package com.example.roleperm;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-bob"))
            .authorities("ROLE_USER", "orders:read", "orders:write")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-viewer"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .authorities(
                "ROLE_ADMIN",
                "orders:read",
                "orders:write",
                "refunds:approve"
            )
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, viewer, admin
        );
    }
}
~~~

**Points to verify:**

1. **`@EnableMethodSecurity`** activates annotations like `@PreAuthorize` on `OrderService`. Without this annotation, the URL only requires `authenticated()` and users could bypass Service permission rules.
2. **`GET /api/public`** is intentionally public; other HTTP methods on that path are not automatically allowed.
3. **`GET /api/admin`** requires `ROLE_ADMIN` at the URL layer. In the example, ADMIN does not need `ROLE_USER` assigned.
4. **Remaining `/api/**`** routes require `authenticated()` before the Controller runs; fine-grained permissions sit on the Service.
5. **`anyRequest().denyAll()`** prevents new undefined routes from becoming open unintentionally.
6. Principals are granted **exact authority strings**: `ROLE_USER`/`ROLE_ADMIN` and `orders:read`/`orders:write`/`refunds:approve`. There is no automatic mapping.
7. HTTP Basic uses demo credentials in memory; passwords are stored as BCrypt hashes in `UserDetails`. Test only on localhost; never use demo accounts outside the lesson.
8. **CSRF protects POST under default configuration.** Tests use `csrf()` when checking permissions in isolation, because a POST lacking a CSRF token can return 403 before `@PreAuthorize` ever runs. Do not disable CSRF just to make POST commands run.
9. When a role hierarchy or DB/IdP permission model is needed, explicitly declare the mapping and test it. Never assume ADMIN has every permission.

### 8.7. Running the Demo and Testing with curl

In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

On Windows PowerShell use `curl.exe`; Linux/macOS normally use `curl`.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/orders/101
curl.exe -i -u alice:demo-alice http://localhost:8080/api/orders/101
curl.exe -i -u alice:demo-alice http://localhost:8080/api/orders/102
curl.exe -i -u viewer:demo-viewer http://localhost:8080/api/orders/101
curl.exe -i -u bob:demo-bob http://localhost:8080/api/orders/102
curl.exe -i -u bob:demo-bob http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Expected** results:

| Request | HTTP | Reason |
| --- | --- | --- |
| GET /api/public anonymous | 200 | Public via `permitAll()`. |
| GET /api/orders/101 anonymous | 401 | Valid identity required. |
| Alice reads order 101 | 200 | Has `orders:read` and is owner; JSON has `id=101`, `owner=alice`. |
| Alice reads order 102 | 403 | Has coarse permission yet does not own Bob's order. |
| Viewer reads order 101 | 403 | Has `ROLE_USER` yet lacks `orders:read`. |
| Bob reads order 102 | 200 | Has `orders:read` and is owner. |
| Bob visits /api/admin | 403 | `ROLE_USER` does not mean `ROLE_ADMIN`. |
| Admin visits /api/admin | 200 | Has `ROLE_ADMIN`. |

HTTP Basic uses Base64 and **does not protect credentials when transmitted over plain HTTP**. Commands using `http://localhost` and mock passwords are for learning only; over real networks use HTTPS. Never capture or place real passwords/tokens in command history or logs.

For `POST /api/orders` or `/api/refunds`, a `curl` command with valid Basic auth **but missing a CSRF token** may receive 403 from `CsrfFilter`. That does not necessarily indicate a missing permission. The test suite in the next section uses `csrf()` to test permissions separately from CSRF rejections.

## 9. Testing Permissions with MockMvc and Spring Security Test

Create **`src/test/java/com/example/roleperm/AuthorizationTests.java`**:

~~~java
package com.example.roleperm;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void protectedResourceNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/orders/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobsOrder() throws Exception {
        mvc.perform(get("/api/orders/102")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUserDoesNotAutomaticallyGrantReadPermission()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(httpBasic("viewer", "demo-viewer")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnOrder() throws Exception {
        mvc.perform(get("/api/orders/102")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void aliceCannotCreateOrderWithoutWritePermission()
            throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("alice", "demo-alice"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanCreateOrderWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("bob", "demo-bob"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:bob"));
    }

    @Test
    void bobCannotApproveRefund() throws Exception {
        mvc.perform(post("/api/refunds")
                .with(httpBasic("bob", "demo-bob"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanApproveRefund() throws Exception {
        mvc.perform(post("/api/refunds")
                .with(httpBasic("admin", "demo-admin"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("refund-approved"));
    }

    @Test
    void userRoleIsNotAdminRole() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanReadAdminPage() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Thirteen tests** verify public/authentication, roles, permissions, ownership, and POST requests blocked by CSRF. All are runnable tests in the declared project; no JWT or real IdP is required.

**Understand test limitations:** MockMvc with HTTP Basic executes authentication in application tests, yet does not prove TLS, proxies, production identity providers, caches, or ownership in a real DB are secure. In systems with write operations, denied tests must also verify the DB and message queues remain **unchanged**; the demo create/refund methods intentionally produce no side effects.

### 9.1. Permission Matrix Derived from the Demo

| Caller | ROLE_ADMIN? | orders:read? | orders:write? | refunds:approve? | Read others' orders? |
| --- | --- | --- | --- | --- | --- |
| alice | No | Yes | No | No | No. |
| bob | No | Yes | Yes | No | No. |
| viewer | No | No | No | No | No. |
| admin | Yes | Yes | Yes | Yes | Yes in the demo; real apps usually also restrict by tenant and purpose. |

This is the **specific permission matrix of the demo**, not a Spring Security default for every role. Adding a new role does not automatically endow it with old permissions.

## 10. Object-Level Access Control (BOLA/IDOR)

**BOLA (Broken Object Level Authorization)** or **IDOR** occurs when the server allows a subject to access an object they do not own, often via a path ID or query parameter. A user with `orders:read` for the order resource type is still not necessarily allowed to read **order 102**.

Example request:

~~~http
GET /api/orders/102 HTTP/1.1
Host: localhost:8080
Authorization: Basic <demo-credentials>

~~~

If Alice is authenticated and holds `orders:read` yet order 102 belongs to Bob, the Service must deny access. Extract the principal from the verified `SecurityContext`/`Authentication`; **never trust a `userId` sent by the client** to determine ownership.

In real database-backed systems, one way to prevent mis-access is querying by **`orderId + tenantId/ownerId` derived from the trusted identity**, or calling a policy engine/Service check before returning the object. Returning 403 or 404 depends on security policy, yet never return Bob's content and never trigger side effects.

**Dynamic conditions** can matter more than roles: a finance staffer may only approve refunds below a limit, during business hours, or must not be the order creator. Do not grant `refunds:approve` as an unrestricted permanent privilege when business rules require extra constraints.

### 10.1. When Do You Need PermissionEvaluator or a Custom AuthorizationManager?

For simple logic, `hasAuthority("orders:read")` plus an owner check in the Service is clear enough. If multiple modules share complex rules, create an authorization policy bean or `PermissionEvaluator`, then invoke it from `@PreAuthorize` or an appropriate `AuthorizationManager`.

Example **illustrative method-security snippet**:

~~~java
@PreAuthorize(
    "hasAuthority('orders:read') and @orderPolicy.canRead(authentication, #id)"
)
public OrderView read(long id) {
    // @orderPolicy must be an actual implemented Spring bean.
    return null;
}
~~~

The code above **is not a standalone Java file** and intentionally omits defining `orderPolicy`; it shows how to combine a coarse permission with an owner/tenant policy. In production, authorization decisions must rely on trusted data and handle missing or concurrently modified objects properly.

## 11. OAuth2/JWT: Mapping Scopes Dedicated to a Resource Server

This section is a **different architectural variant** from the HTTP Basic project in section 8. Do not paste Bearer configuration straight into that project and reuse the same Basic tests: `Authentication` and authority sources can differ, and Service policies must be redesigned for tokens.

### 11.1. Minimal Resource Server Configuration

With Spring Boot Servlet/MVC, add the **`spring-boot-starter-oauth2-resource-server`** dependency (instead of HTTP Basic configuration in a real Resource Server project). Maven dependency example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Declare the trusted issuer pointing to a **real deployed Identity Provider**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
~~~

The domain above is an example only, **not a live working IdP**. The Resource Server needs standard-compliant metadata and public keys. For JWTs, Spring Security verifies signatures and relevant claims per config; the application must also enforce the **audience issued for the API**, scopes, tenant/client constraints, expiry, and business policies. Never treat a sample `issuer-uri` as complete production configuration.

A dedicated `SecurityFilterChain` for a Resource Server may look like:

~~~java
// Bean snippet for a standalone Resource Server project,
// with dependency + trusted issuer-uri or JwtDecoder.
@Bean
SecurityFilterChain resourceServer(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

**You must import** `Bean`, `HttpSecurity`, `HttpMethod`, `SecurityFilterChain`, and `Customizer` from Spring; this is a config fragment, not a runnable project. If reusing the Controller/Service from section 8, realign policies and `Authentication`/permission mappings rather than simply copying the bean.

### 11.2. Mapping JWT Scopes to SCOPE_*

In Spring Security OAuth2 Resource Server, for a valid JWT access token carrying a **`scope`** claim (space-delimited string) or **`scp`** claim (formats supported by the converter), the default converter typically generates:

~~~text
Token claim: "scope": "orders.read orders.write"
          |
          v
GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

Thus **`hasAuthority("SCOPE_orders.read")`** checks the scope-derived authority. **`hasAuthority("orders:read")`** in section 8's Basic project checked a different internal permission; **they are not automatically equivalent**.

An endpoint receiving a token with scope `orders.read` while the Service still has:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
~~~

can return **403** despite passing the `SCOPE_orders.read` URL rule. Decide clearly: either the Service checks token scopes directly, or trusted scopes are converted into internal permissions via an explicit mapping policy. Never add two conflicting rules and then loosen them with `permitAll()`.

### 11.3. Customizing the Converter Requires Understanding What Is Replaced

If a provider issues a `permissions` claim instead of `scope`, Spring Security provides **`JwtGrantedAuthoritiesConverter`** and **`JwtAuthenticationConverter`**. Example config fragment:

~~~java
// Bean snippet for a Resource Server project, not merged into the Basic demo.
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("permissions");
    granted.setAuthorityPrefix("");

    JwtAuthenticationConverter result =
        new JwtAuthenticationConverter();

    result.setJwtGrantedAuthoritiesConverter(granted);
    return result;
}
~~~

Import both classes from **`org.springframework.security.oauth2.server.resource.authentication`** and `Bean` from Spring. To use this converter, wire it into the JWT DSL appropriately, for example:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
)
~~~

This DSL fragment is **exclusively for Resource Server configuration**. It is only safe when **issuer/audience/keys/claims** have been verified and permission values truly originate from a trusted source. Also, replacing the default converter like this can **drop `SCOPE_*` authorities** unless you deliberately combine them; to support both scopes and permissions, build a unified converter and test it.

Do not blindly map every `roles`/`permissions` claim across all tenants into high privileges. You may need to normalize namespaces, check authorized party/client, audience, issuer, and restrict which roles are accepted. **Granting `ROLE_ADMIN` based on an arbitrary claim is dangerous.**

### 11.4. Scopes in Access Tokens vs. ID Tokens

**Access tokens** are used to call Resource Servers under granted policies. OpenID Connect **ID tokens** give authentication info to the client in an OIDC flow, not credentials substituting for access tokens to call arbitrary APIs.

If the system uses **opaque tokens**, the Resource Server typically calls token introspection instead of decoding JWTs directly; scopes/authorities still need proper mapping and verification. Do not assume every token must be a JWT.

### 11.5. Checks That Cannot Be Skipped

- **Signature and algorithm**: accept only configured trusted keys/signatures/algorithms.
- **Issuer (`iss`)**: token was issued by an authorized source.
- **Timestamps (`exp`, `nbf`)** and clock skew: token is not expired and is within its valid window.
- **Audience (`aud`)**: token was issued for the receiving API. Never let a token for API A access API B automatically.
- **Scope/authority**: token holds permission to invoke that operation.
- **Subject and client**: distinguish delegated users from service-only clients; does the principal have a relationship to the resource?
- **Tenant and object policy**: check right inside Service/domain using current authoritative data.
- **Revocation/permission changes**: issued JWTs may retain old claims until expiry; design short TTLs, revocation/introspection, or dynamic policy checks for sensitive actions.

**A scoped token is an important constraint, not an all-access pass across the system.**

## 12. 401 and 403 Statuses When Role, Permission, or Scope Is Insufficient

| Situation | Typical HTTP | Reason |
| --- | --- | --- |
| No credentials sent to an API requiring authentication | **401** | No valid `Authentication` yet. |
| HTTP Basic sent with wrong password | **401** | Invalid authentication evidence. |
| Bearer token missing/expired/invalid signature | **401** | Token fails authentication; response/challenge depends on mechanism. |
| Logged-in user missing ROLE_ADMIN | **403** | Authenticated, yet denied due to missing role. |
| User has ROLE_USER yet lacks orders:read | **403** | Missing required permission. |
| Valid token yet missing scope orders.read | Usually **403**, possibly with Bearer `insufficient_scope` challenge | Token authenticated, yet lacks the authority the API requires. |
| Token has scope yet user does not own orderId | **403 or 404** per policy | Scope does not replace object-level authorization. |
| Cookie/session flow sends POST without CSRF token when CSRF applies | Usually **403** | Rejected by CSRF protection before permission logic runs. |

**Do not conclude solely from a 403 that a role is missing.** It could be a permission, scope, CSRF, tenant, or another policy. Use request IDs and controlled security logging to identify which rule rejected the request, without logging raw tokens or session cookies.

With a Bearer Resource Server, **`WWW-Authenticate: Bearer`** may carry standard error info; exact responses depend on configuration and should not leak sensitive policy internals. With form login, unauthenticated requests may receive a 302 redirect instead of 401; verify your `AuthenticationEntryPoint` and client behavior.

## 13. Common Permission Design Mistakes

### 13.1. Using an Overly Broad Role for Every Operation

Using **`hasRole("ADMIN")`** to permit refunds looks simple, yet it can grant refund privileges to technical administrators with no financial responsibility. Use the permission **`refunds:approve`** paired with limits/approvals, and govern which roles receive that permission.

### 13.2. Believing Write Permission Implies Read Permission

**`orders:write`** and **`orders:read`** are two independent strings. If write is meant to allow read, either grant both or implement and test an explicit policy/hierarchy. The same applies to scopes `orders.write` and `orders.read`.

### 13.3. Turning a Scope into ROLE_ADMIN

A scope named `admin` should not automatically become the `ROLE_ADMIN` authority just because the label matches. Scopes belong to token/client delegation, whereas administrative roles belong to trusted identity and policy. If a special mapping case exists, pin down issuer, audience, tenant, client, and allowed roles.

### 13.4. Checking Permissions Only in the Controller

If a Service is invoked from a batch job, message listener, or another Controller lacking checks, the same business operation can be bypassed. Enforce rules in the Service/domain or a shared policy engine where appropriate, while keeping URL policies to reject requests early.

### 13.5. Checking Scope on Endpoints While Dropping Object Checks

This is the root of IDOR/BOLA bugs: Alice has scope `orders.read` and accesses Bob's `orderId`. Add owner/tenant checks and cross-user/cross-tenant tests.

### 13.6. Skipping Audience or Claim Source Checks

A token issued for another service can carry identically named scopes. Deciding permissions from scope alone without verifying the token is meant for this resource server creates token-confusion vulnerabilities. Never trust custom `roles` claims when the issuer/tenant is not authorized to grant that role.

### 13.7. Granting Permissions from Client-Supplied Values

Roles, permissions, tenants, or owners must come from authenticated sources and backend policies. A request body `{"role":"ADMIN"}` or header `X-Role: ADMIN` is not proof. On user-update endpoints, prevent mass assignment that lets callers edit their own `role`/`permissions` fields.

### 13.8. Keeping Stale Permissions in Long-Lived JWTs

An employee whose `refunds:approve` permission was revoked may still hold a JWT valid for hours containing the old claim. Consider short TTLs, token revocation/introspection, dynamic permission checks on sensitive actions, and auditing.

### 13.9. Enabling Method Security Yet Calling Internal Methods Incorrectly

Spring method security typically relies on Spring AOP proxies. **Self-invocation** via `this.someSecuredMethod()` can bypass the proxy, and objects instantiated with `new` are not Spring-managed beans. Test through Controllers or container-injected Spring beans.

### 13.10. Returning 403 After Creating Side Effects

If a Service writes to the DB or emits a message before checking permission/owner, returning 403 is still unsafe. Place authorization before state mutations and use appropriate transactions/idempotency.

### 13.11. Caching Without Principal/Tenant Isolation

If user A's cached response is served to user B because the cache key uses only the URL, API role/scope checks fail to protect data. For sensitive responses, design cache policies keyed and isolated by principal/tenant.

### 13.12. Treating CORS as Authorization

CORS restricts browser JavaScript from reading cross-origin responses per policy; `curl` and backend clients are not subject to the same restriction. Never substitute `Access-Control-Allow-Origin` for authentication, roles, permissions, scopes, or CSRF.

## 14. How to Design Roles/Permissions/Scopes for a Project

### 14.1. Start with an Action Matrix

First list **resource + action + data scope + sensitivity**, rather than starting with a vague list of roles.

| Use case | Internal permission | API token scope if needed | Additional conditions |
| --- | --- | --- | --- |
| Read order | orders:read | orders.read | Owner or valid delegated read within the right tenant. |
| Create order | orders:write | orders.write | Server-verified prices, quotas, and account status. |
| Cancel order | orders:cancel | orders.cancel | Order not yet completed, valid owner, audited. |
| Approve refund | refunds:approve | refunds.approve | Limits, separation of duties, MFA per policy. |
| Export report | reports:export | reports.export | Tenant scope, record count, intended purpose. |

Next map roles to permissions per business rules. An operations ADMIN might hold `reports:export` without `refunds:approve`; a dedicated FINANCE role might hold `refunds:approve` up to a threshold.

### 14.2. Separate User Permissions and Service Permissions

When a service calls an API using **client credentials**, the principal is the client/service. It has no end-user `ownerId` by default. Design dedicated machine-to-machine APIs or explicit service-identity policies; when acting on behalf of a user, use an authorized delegation/token-exchange mechanism. Never accept a client-supplied `userId` as proof of permission to view resources.

### 14.3. Document Source and Trust Level

For every authority, document:

- **Exact name** and meaning.
- **Who may receive it** and who may revoke it.
- **Source**: DB, role store, verified IdP claim, or OAuth scope.
- **Refresh cycle**: per request, session, or JWT lifetime.
- **Boundaries**: tenant, resource owner, environment, service/client audience.
- **Enforcement points**: URL, Service/method, database query, policy engine.
- **Negative tests**: lower-privileged subject, cross-tenant, wrong-audience token, recently revoked permission.

### 14.4. Use Deny-by-Default and Least Privilege

The HTTP layer should define explicit rules for public, authenticated, role/scope/permission, and a **fallback `denyAll`** across protected areas. The Service layer rejects calls lacking permissions or trusted data. Avoid creating an "admin bypasses everything" exception unless the business strictly demands it and it passes review.

### 14.5. Check Changes Before Deploying

When adding a new scope, check its interaction with internal permissions. When adding a new role, check its assigned authorities. When migrating from HTTP Basic to Bearer, verify authority mappings and test the API against the same matrix. Never fix a 403 error by stripping away authorization conditions.

## 15. Self-Assessment Exercises

1. **Role:** A user has authority `ROLE_USER` but not `orders:read`. Do `hasRole("USER")` and `hasAuthority("orders:read")` return the same result? **Hint:** no; they are two different authorities.
2. **Permission:** Alice has `orders:read` yet requests Bob's order. Why is she still denied? **Hint:** coarse operation permission does not equal object ownership.
3. **Scope:** An access token has scope `orders.read` yet was issued for another API. Should it be accepted? **Hint:** no; check audience and token trust.
4. **Converter:** A JWT contains `roles=["ADMIN"]` yet `ROLE_ADMIN` is missing from `Authentication`. What is missing? **Hint:** verified and safe mapping for the custom JWT role claim.
5. **Prefix:** Does `hasAuthority("SCOPE_orders.read")` equal `hasAuthority("orders:read")`? **Hint:** no, unless intentionally mapped.
6. **Client credentials:** Does a service token with `reports.read` automatically carry a user identity to filter Alice's orders? **Hint:** no; a service-identity/delegation model is required.
7. **Role hierarchy:** Does `ROLE_ADMIN` automatically inherit `ROLE_USER`? **Hint:** no, unless both authorities are granted or a hierarchy is configured.
8. **CSRF:** Bob sends `POST /api/orders` with valid Basic auth yet no CSRF token and gets 403. Can we conclude Bob lacks `orders:write`? **Hint:** no; check the CSRF filter.
9. **Method security:** Why might `@PreAuthorize` on a method of an object created directly with `new` fail to guard calls? **Hint:** method security relies on Spring-managed proxies.
10. **Dynamic permissions:** A JWT holds `refunds:approve` yet the permission was revoked in the DB. Which mechanisms should be considered? **Hint:** TTL, revocation, introspection, or checking current data at runtime.
11. **Design:** Build a permission matrix for three roles `CUSTOMER`, `SUPPORT`, `FINANCE` and three permissions `orders:read`, `orders:cancel`, `refunds:approve`, including owner/tenant/approval constraints.
12. **Testing:** Add a test where `admin` has `ROLE_ADMIN` yet is denied a new operation whose permission has not been granted; prove that a role confers no automatic "superpower".

### Checklist to Remember

- **Role** = responsibility group; typically represented as `ROLE_*` by Spring Security convention.
- **Permission** = business operation permission; can be represented as an authority such as `orders:read`.
- **Scope** = access scope granted to an OAuth2 access token; default converters typically produce `SCOPE_*` authorities.
- **No automatic mapping** exists across the three authority kinds; configuration and tests define their relationships.
- **`hasRole("ADMIN")` differs from `hasAuthority("ADMIN")` and `hasAuthority("SCOPE_admin")`**.
- **Holding scope/permission still requires owner/tenant/resource-level policies**.
- **JWTs must have issuer, signature, expiration, and matching audience verified**; never trust self-decoded claims.
- **`@EnableMethodSecurity`** is required to use `@PreAuthorize` in the demo app.
- **CSRF, CORS, HTTPS, caching, and secret management** are complementary controls, not replacements for authorization.
- **Test denied cases and side effects**, not only 200 cases.

## References

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorities, roles, and authorization design.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `hasAuthority`, `hasRole`, and fallback rules.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and method-level policies.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `scope`/`scp`, `SCOPE_` authorities, and JWT conversion.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): auto-configuration and enabling method security.

## Conclusion

**Role** describes a responsibility group, **permission** describes a specific operation, and **scope** describes the access boundaries granted via an OAuth2 access token. In Spring Security, all three can be represented as `GrantedAuthority` instances through trusted sources and converters, yet **`ROLE_ADMIN`, `orders:read`, and `SCOPE_orders.read` are distinct conditions**. Good security design verifies credentials, keeps authority mappings intentional, enforces both action permissions and **specific object/tenant access**, and tests both authorized and denied cases before any side effects occur.
