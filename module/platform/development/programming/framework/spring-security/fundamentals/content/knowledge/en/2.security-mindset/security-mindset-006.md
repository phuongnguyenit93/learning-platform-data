# Defense in Depth and the Limits of Any Single Control

In application security, a solid mechanism can still fail due to misconfiguration, implementation bugs, user behavior, unknown vulnerabilities, or because that mechanism itself addresses only **one specific category of risk**. HTTPS does not decide who may read an order; successful login does not guarantee a user sees only their own data; a CSRF token does not fix SQL injection; and a web application firewall (WAF) does not replace backend permission checks.

**Defense in depth** is the practice of designing multiple complementary controls across different boundaries. If one control is bypassed, another control has the opportunity to **block, limit blast radius, detect, or aid recovery**. The goal is to avoid letting a single mistake cause a full-scale incident while keeping potential damage as small as possible.

This lesson explains how to identify defense layers in a Spring Boot/Spring Security (Servlet) application, the limits of each control, how to weave them into a business flow, and how to test to avoid a false sense of security.

## 1. What Is Defense in Depth?

Imagine an e-commerce application with a `GET /api/orders/{id}` API. Users must log in to call the API. If the backend only checks `authenticated()` and loads the order by ID, a valid account can try someone else's ID and view unauthorized data.

An appropriate multi-layered design might include:

1. HTTPS connections to reduce data exposure in transit.
2. Identity authentication through a trusted mechanism, with proper session/token management.
3. An HTTP endpoint rule requiring the `order:read` permission.
4. A service-level check verifying the order belongs to the right tenant, owner, or authorized caller scope.
5. Database queries scoped by tenant/owner where appropriate.
6. Responses containing only fields permitted to be shown.
7. Logging, anomaly monitoring, and automated tests to detect drift.

With only layer 2, the system remains vulnerable to **Broken Object Level Authorization (BOLA/IDOR)**. If layer 4 has a bug, a tenant-scoped query in layer 5 can reduce impact; however, it does not guarantee ownership within the same tenant. Once data has leaked, auditing and monitoring cannot undo the disclosure, though they support detection and response.

**Key point:** each layer must have a clear purpose, sit at the right boundary, and be tested independently. Multiple layers repeating the same misconfiguration or trusting the same forged input can create **many checks yet a single real point of failure**.

### 1.1. Three Distinct Roles of Controls

| Role | Goal | Examples |
| --- | --- | --- |
| **Preventive** | Block invalid actions before impacting assets | Authentication, authorization, CSRF, validation, parameterized queries, least privilege |
| **Detective** | Recognize unusual events, failures, or abuse | Audit logs, alerts on bulk access denials, monitoring configuration changes |
| **Limiting/Recovery** | Shrink damage and recover after an incident | Tenant isolation, restricted service account rights, tested-restore backups, token revocation, incident response |

Detective controls cannot fully replace preventive controls. A highly detailed log still cannot stop an unauthorized read if the backend already returned the data to the attacker.

### 1.2. Defense in Depth Is Not Just Stacking More Tools

Putting WAF + API Gateway + Spring Security in front is still insufficient if all three only check "is there a token?" and all skip per-record permissions. You must explicitly define:

- **Assets**: user data, order state, payment details, secrets, availability.
- **Subjects**: users, services, jobs, unauthenticated clients.
- **Resources and actions**: specific orders, exports, refunds, role updates, data deletion.
- **Attack paths**: identity spoofing, privilege escalation, ID swapping, XSS, CSRF, injection, token leakage, misconfiguration.
- **Trust boundaries**: browser → backend; backend → database; backend → IdP; worker → queue; tenant A → tenant B.
- **Control layers**: what threat each layer blocks, with what evidence, and how it can fail.

A strong control placed in the wrong spot can still fail to prevent attacks. For example, a role check in a controller does not protect a background job calling the same service directly if the service lacks a matching permission boundary.

## 2. Architecture Example: Multiple Layers Around a Request

A Spring MVC application using cookie sessions might have this conceptual path:

```text
Browser / Mobile / Service client
    |
    |  TLS, cookie/token handling, client-side controls
    v
Reverse proxy / Load balancer / Gateway
    |  TLS termination, request limits, rate limiting, logging
    |  Not the sole source of truth for per-business-object permissions
    v
Spring SecurityFilterChain
    |  CSRF when applicable, Authentication, Request-level authorization
    |  Security headers and other protective mechanisms
    v
Controller + Request DTO
    |  Parse/validate input, size limits
    v
Service / Domain policy
    |  Right principal? right tenant? right owner?
    |  Has permission for action? business state permits it?
    v
Repository / Database / External dependency
    |  Parameterized queries, tenant scoping, least-privilege DB identity
    |  Transactions, constraints, idempotency if side effects occur
    v
Response projection / Audit / Monitoring
    |  Return only permitted data; log events in a controlled manner
```

The diagram shows **responsibilities**, not the exact execution order of every security filter. Some checks can occur in multiple places; some requests are blocked before reaching a controller. Each step must be tailored to the actual application.

### 2.1. Why Two Layers Checking Permissions Still Add Value

- **Request authorization** can block out-of-privilege URL groups early: `/api/admin/**` requires `ROLE_ADMIN`.
- **Method/service authorization** decides permissions by action and exact object: who owns `Order 100`, what state it is in, and which tenant the caller belongs to.
- **Data access scoping** prevents queries from returning another tenant's data in the first place.

The layers answer **different questions**: may the caller enter the feature group, may they perform this specific operation, and are they reading/writing the right dataset? Avoid mechanically repeating the same `hasRole("USER")` across all three layers while forgetting object ownership.

## 3. Limits of Common Security Controls

| Control | Helps Solve | Does Not Solve Alone | Additional Layers to Consider |
| --- | --- | --- | --- |
| **HTTPS/TLS** | Protects data in transit, authenticates server per TLS config | BOLA/IDOR, user with wrong privileges, in-app XSS | Object authorization, safe data handling |
| **Login / MFA** | Verifies user with appropriate assurance level | Logged-in user reading others' data, over-privileged accounts | Authorization, least privilege, session management |
| **JWT signature validation** | Verifies token integrity and issuer when checked properly | Wrong audience, overly broad scope, ownership, stolen still-valid token | Issuer/audience/expiration/scope checks, object authorization, short token lifetime |
| **`hasRole` / URL authorization** | Blocks endpoints for unauthorized roles | Accessing another object via the same endpoint, business state | Owner, tenant, action, and state checks in service |
| **CSRF protection** | Prevents forged requests under auto-attached credentials like cookies | XSS, SQL injection, missing authorization, intentional misuse by valid user | Authn/authz, output encoding, validation |
| **CORS** | Restricts cross-origin browser JavaScript response access | Authentication, authorization, CSRF in general, non-browser clients | Authentication, authorization, threat-model-appropriate CSRF |
| **`@Valid` / Bean Validation** | Enforces data types and declared constraints | SQL injection if concatenating strings, ownership checks, undeclared business rules | Prepared statements, domain validation, authorization |
| **Prepared statements** | Mitigates SQL injection from mixing SQL code and data | Privilege escalation, response leakage, wrong tenant queries | Least-privilege DB account, scoped queries, response minimization |
| **Security headers / CSP** | Reduces certain browser-side risks when configured properly | Does not guarantee all XSS disappears, does not fix IDOR | Output encoding, context-aware escaping, frontend review |
| **Rate limit** | Reduces request abuse and resource exhaustion | Single-request data leak, business logic bypass | Object permissions, resource/cost/execution controls |
| **WAF** | Blocks some known attack patterns before reaching the app | Authorization logic flaws, novel payloads, bugs over trusted paths | Code fixes, threat modeling, security tests |
| **Logging/monitoring** | Detection, investigation, alerting | Does not stop an already-wrongly-permitted action | Deny policies, enforcement at execution points, response handling |
| **Backup** | Recovers data after certain incidents | Preventing leaks, preventing permission tampering, guaranteeing untested recovery | Access control, encryption, tested restores, secure storage |

No row in this table is "useless." The point is that **every tool has a protection boundary**. When designing, explicitly ask "which threats remain after this layer?" instead of ticking a "security added" checkbox.

### 3.1. Do Not Confuse HTTPS with Access Control

Suppose Alice's connection to the server is encrypted with HTTPS, yet `GET /api/invoices/123` only requires login. Alice changes the ID to `124` and the server returns Bob's invoice. TLS protects **the transport of wrongly returned data**; it does not make the authorization decision right.

Therefore you must verify invoice permissions, apply owner/tenant-scoped queries, avoid returning unnecessary sensitive fields, and test with IDs belonging to other users.

### 3.2. Do Not Confuse MFA with Post-Login Action Controls

MFA strengthens resistance against account takeover via a single compromised factor. Yet a legitimately logged-in user can still exploit an API missing permission checks; hijacked tokens/sessions also need separate defenses. Combine least privilege, anomaly detection, session/token policies, and object checks.

### 3.3. Do Not Confuse CORS with CSRF

CORS primarily governs when JavaScript on another website can read/access cross-origin responses under browser rules. It is not a server-side permission system. CSRF targets the browser's tendency to attach credentials automatically—such as session cookies—to requests the user did not intentionally initiate.

An HTML form on an external site can send a state-changing request under certain conditions even if that site's script cannot read the response. Thus a CORS config "blocking unknown origins" **does not replace** CSRF tokens for cookie-based apps with state-changing endpoints. For APIs that accept only bearer tokens explicitly added to headers by clients and use no auto-attached credentials, evaluate CSRF based on the actual auth model, not the "REST API" label.

### 3.4. Do Not Confuse Password Hashing with Session Protection

Proper password hashing (e.g., BCrypt/Argon2 via the chosen mechanism) reduces impact if the password database leaks; it does not encrypt sessions, protect hijacked cookies, enforce authorization, or stop an attacker using a valid password. Combine HTTPS, proper cookie flags, session lifecycle, MFA when needed, and monitoring.

## 4. Central Scenario: Order API

Consider the assets: order details, customer addresses, amounts, and order status. Subjects: Alice, Bob, customer support staff, and a background service. Actions: read, cancel, refund, and export.

### 4.1. Naive Design

```java
// Anti-pattern: authentication only, no object-level permission check.
@GetMapping("/api/orders/{id}")
public OrderDto getOrder(@PathVariable long id) {
    return orderService.findById(id);
}
```

Even though Spring Security configures `/api/orders/**` to require `authenticated()`, this code can still return another user's order data. Hard-to-guess IDs do not fix the underlying authorization flaw.

### 4.2. Purposeful Multi-Layered Design

| Layer | Condition to Check | If That Layer Is Missing |
| --- | --- | --- |
| Client/transport | HTTPS, no tokens in URLs, cookie/session hygiene | Data or sessions leak through other paths |
| SecurityFilterChain | Valid identity, `order:read` permission | Unauthenticated or wrong-permission callers reach API |
| Service policy | Right tenant, right owner, or explicitly delegated | Valid user can swap IDs to another person's order |
| Repository | Query scoped to allowed tenant/object, parameterized | An upper-layer filtering bug widens readable data |
| Response | DTO contains only role-appropriate fields | May accidentally leak internalNote, payment token, or excess data |
| Audit/monitoring | Log denied decisions and sensitive access | Difficult to spot ID enumeration or investigate incidents |

Checks should rely on **trusted data**. Never use `ownerId`/`tenantId` submitted by the client in the body as proof of permission. Tenant info in the principal must be verified, and order ownership data must come from the server's data store.

### 4.3. Canceling an Order Differs from Reading an Order

Even when Alice is the owner, she may read a delivered order yet no longer have permission to cancel it. So the policy requires both **action** and **resource state**:

```text
ALLOW cancel if:
  caller is authenticated
  AND has order:cancel permission
  AND caller and order are in the same tenant
  AND caller is the owner or explicitly authorized to cancel
  AND order is in a state that permits cancellation
  AND all relevant request protection layers accepted it
```

If any required condition fails, do not cancel. For a POST request from a browser using session cookies, CSRF protection is an additional layer to check. If data changes concurrently, state checks and updates must execute consistently via appropriate transactions/conditional updates.

## 5. Standalone Java 17: Passing One Layer Does Not Mean Allowed

The following example simulates **control gates** for reading/canceling an order. No Spring Boot or external libraries required. The goal is to show that a caller must pass distinct checks; having just one permission or a valid identity is insufficient.

Create **`DefenseInDepthDemo.java`**:

```java
import java.util.Objects;
import java.util.Set;

public class DefenseInDepthDemo {

    enum Action { READ, CANCEL }

    enum Decision {
        ALLOW,
        UNAUTHENTICATED,
        CSRF_REJECTED,
        MISSING_PERMISSION,
        WRONG_TENANT,
        WRONG_OWNER,
        INVALID_STATE,
        INVALID_INPUT
    }

    record Caller(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record Order(
        String id,
        String tenantId,
        String ownerId,
        boolean cancellable
    ) {}

    // This context is server-determined; do not trust flags sent by the client.
    record RequestContext(boolean csrfRequired, boolean csrfValid) {}

    static Decision decide(
        Caller caller,
        Action action,
        Order order,
        RequestContext context
    ) {
        if (caller == null || order == null || action == null
                || context == null || order.id() == null
                || order.id().isBlank()) {
            return Decision.INVALID_INPUT;
        }

        // Layer 1: authentication.
        if (!caller.authenticated()) {
            return Decision.UNAUTHENTICATED;
        }

        // Layer 2: request validity under the CSRF-required model.
        if (context.csrfRequired() && !context.csrfValid()) {
            return Decision.CSRF_REJECTED;
        }

        // Layer 3: permission for the action.
        String requiredPermission = switch (action) {
            case READ -> "order:read";
            case CANCEL -> "order:cancel";
        };

        if (caller.permissions() == null
                || !caller.permissions().contains(requiredPermission)) {
            return Decision.MISSING_PERMISSION;
        }

        // Layer 4: tenant isolation.
        if (!Objects.equals(caller.tenantId(), order.tenantId())
                || caller.tenantId() == null) {
            return Decision.WRONG_TENANT;
        }

        // Layer 5: permission on the specific object.
        if (!Objects.equals(caller.userId(), order.ownerId())
                || caller.userId() == null) {
            return Decision.WRONG_OWNER;
        }

        // Layer 6: business invariant.
        if (action == Action.CANCEL && !order.cancellable()) {
            return Decision.INVALID_STATE;
        }

        return Decision.ALLOW;
    }

    static void check(
        String label,
        Caller caller,
        Action action,
        Order order,
        RequestContext context
    ) {
        System.out.println(
            label + ": " + decide(caller, action, order, context)
        );
    }

    public static void main(String[] args) {
        Caller alice = new Caller(
            "alice", "shop-a", true,
            Set.of("order:read", "order:cancel")
        );
        Caller bob = new Caller(
            "bob", "shop-a", true,
            Set.of("order:read", "order:cancel")
        );
        Caller viewer = new Caller(
            "alice", "shop-a", true,
            Set.of("order:read")
        );
        Caller otherTenant = new Caller(
            "alice", "shop-b", true,
            Set.of("order:read", "order:cancel")
        );
        Caller guest = new Caller(
            "guest", "shop-a", false,
            Set.of("order:read")
        );

        Order draft = new Order("ORD-100", "shop-a", "alice", true);
        Order paid = new Order("ORD-100", "shop-a", "alice", false);

        RequestContext safeRead = new RequestContext(false, false);
        RequestContext validPost = new RequestContext(true, true);
        RequestContext invalidPost = new RequestContext(true, false);

        check("Alice reads", alice, Action.READ, draft, safeRead);
        check("Guest reads", guest, Action.READ, draft, safeRead);
        check("Alice cancel without CSRF", alice, Action.CANCEL,
            draft, invalidPost);
        check("Viewer cancels", viewer, Action.CANCEL, draft, validPost);
        check("Other tenant reads", otherTenant, Action.READ,
            draft, safeRead);
        check("Bob reads Alice order", bob, Action.READ,
            draft, safeRead);
        check("Alice cancels paid", alice, Action.CANCEL,
            paid, validPost);
        check("Alice cancels draft", alice, Action.CANCEL,
            draft, validPost);
    }
}
```

With JDK 17 or higher:

```bash
javac DefenseInDepthDemo.java
java DefenseInDepthDemo
```

**Exact expected stdout:**

```text
Alice reads: ALLOW
Guest reads: UNAUTHENTICATED
Alice cancel without CSRF: CSRF_REJECTED
Viewer cancels: MISSING_PERMISSION
Other tenant reads: WRONG_TENANT
Bob reads Alice order: WRONG_OWNER
Alice cancels paid: INVALID_STATE
Alice cancels draft: ALLOW
```

Explanation:

- Alice reads her own order: passes authentication, read permission, tenant, and owner; read requests do not require CSRF checks in the demo model.
- Guest has simulated permissions yet `authenticated=false`, so they are blocked right at the identity layer.
- Alice has cancel permission, yet the simulated POST lacks a valid CSRF token and is blocked at the request protection layer.
- Viewer is authenticated Alice with only `order:read`, lacking cancel permission.
- Caller in another tenant still cannot read despite having the permission; Bob in the same tenant but not the owner is also denied.
- Alice cannot cancel an order in a disallowed state. Only when every condition succeeds does it return ALLOW.

**Explicit simulation limits:** The `Caller`, `Order`, and `RequestContext` records are constructed manually. They **do not authenticate** passwords/tokens, do not actually verify CSRF tokens, do not query a database, have no transactions, and do not execute cancellations. In a real application, Spring Security authenticates identity and handles CSRF in their respective components; the service uses trusted data to verify permissions, then updates state consistently in the database. Never treat a client-sent `csrfValid` flag as valid proof.

An important detail: the example orders checks for readability; real systems may reorder them to avoid information leakage or reduce load. However, the final decision must satisfy **all mandatory conditions**, never treating the first passing condition as enough.

## 6. Defense in Depth with Spring Security

Spring Security focuses on authentication, authorization, protection against certain exploits, and application integration. It provides strong tools at the HTTP and method boundaries; checking **permissions on real data**, business correctness, and system-wide safety still require explicit design.

### 6.1. HTTP Layer: `SecurityFilterChain`

*Illustrative* configuration on a Spring Boot 3 / Spring Security 6 Servlet application:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("order:cancel")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

This is a snippet for a Spring project, **not a standalone program**: it needs imports for `@Configuration`, `@EnableMethodSecurity`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `HttpMethod`, `Customizer`, Spring Boot Web/Security dependencies, and an appropriate identity provider.

- `permitAll()` allows catalog GETs while still routing requests through the security filter chain; public access does not disable other protections.
- `hasAuthority("order:read")` and `hasAuthority("order:cancel")` block request groups lacking the required authority; a dedicated policy must still verify the exact object.
- `anyRequest().denyAll()` closes requests without an allow rule; new APIs require active updates.
- `httpBasic()` is only an easy-to-demonstrate authentication mechanism. Production requires HTTPS and an appropriate auth policy.
- `csrf()` retains CSRF protection, useful when credentials attach automatically; POSTs require valid CSRF tokens per the configured mechanism. Never disable CSRF globally just to make testing POST easier.

**Matcher order matters:** specific cases must precede catch-all cases. For example, never place `anyRequest().permitAll()` before admin matchers; an early matching rule makes later rules unreachable.

### 6.2. Service Layer: Method Security and Business Policies

`@EnableMethodSecurity` activates method security annotations such as `@PreAuthorize`. Partial service example:

```java
@PreAuthorize("hasAuthority('order:read')")
public OrderDto getOrder(long orderId, Authentication auth) {
    return orderPolicy.readOrderFor(auth, orderId);
}
```

This is a **non-standalone illustrative snippet**: `OrderDto` and `orderPolicy` are application components to define. `orderPolicy.readOrderFor` must fetch the real resource and check owner/tenant, rather than simply calling the repository by ID and returning all data.

If the service is also called from scheduled jobs or message consumers, establish an identity/permission model for those call paths; never create `ROLE_ADMIN` just to "make the job run." Method security operates via Spring proxy/AOP and requires crossing the proxied boundary; **self-invocation** within the same object may bypass the proxy. Critical business policies should be enforced at consistent boundaries with tests proving coverage.

### 6.3. Repository/Database Layer: Scoping Data and Reducing Privilege

Query concept example:

```sql
SELECT id, total_amount, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_user_id = :authenticatedUserId;
```

Variables are query parameters bound by the driver/ORM; never concatenate `orderId` or `tenantId` arbitrarily into SQL strings. `tenantId` and `authenticatedUserId` must come from verified context, never raw from the request body.

Depending on business rules, an `order:read:any` permission may use a different query while remaining scoped by tenant. The application's database account should hold only necessary permissions rather than system-wide admin rights. Row-level security can be added where platform and architecture fit, provided policies are verified for every connection/transaction; it is an extra layer, not a replacement for service authorization.

### 6.4. Response Layer: Data Minimization Principle

Even when a principal may view an order, they may not view all internal fields: secrets, payment gateway internals, fraud investigation notes, or internal comments. Role-tailored DTOs/projections protect better than serializing whole entities.

Avoid returning stack traces, SQL, environment info, or sensitive data in error messages. Logs need sufficient investigative evidence without recording passwords, bearer tokens, or full `Authorization` headers.

### 6.5. Other Layers Spring Security Does Not Automatically Cover

Spring Security does not automatically guarantee:

- Tenant-scoped, parameterized queries/ORM usage;
- Protection against business logic bugs, BOLA/IDOR, and race conditions;
- Full input validation and context-aware output encoding;
- Rate limiting, payload size caps, queues/backpressure;
- Secret management, infrastructure policies, and safe dependency versions;
- Accurate logging/auditing, monitoring, and incident response;
- Tested backup/restore and data recovery procedures.

Application security combines framework controls with domain design, infrastructure, development workflows, and operations.

## 7. Defense Layers at the Browser Edge

### 7.1. CSRF, SameSite, and Session Cookies

For web apps using session cookies, browsers can automatically attach cookies to requests to the server; attackers can exploit this behavior to trigger state-changing requests. CSRF protection lets the server verify that requests carry a valid token signal.

A multi-layered strategy can combine: CSRF tokens, appropriate `SameSite` cookie attributes, `Secure`/`HttpOnly` cookies as needed, restricting state-changing HTTP methods, Origin/Referer checks when appropriate, and backend authorization. **SameSite is only an additional layer**, not a blanket replacement for CSRF tokens in apps needing token-based protection.

`HttpOnly` restricts JavaScript from reading cookies; it does not stop the browser from attaching cookies to requests and does not eliminate the impact of XSS. `Secure` ensures cookies travel only over HTTPS per browser rules; it does not automatically ensure proper authorization.

### 7.2. XSS and Content Security Policy

Input validation, context-aware output encoding (HTML, attribute, JavaScript, URL), template escaping, and avoiding dangerous DOM APIs are layers that reduce XSS risk. Content Security Policy (CSP) can reduce the chance of unwanted script execution if properly designed, yet CSP is not a license to inject unescaped data into pages.

Never assume a `Content-Security-Policy` header alone solves all XSS or credential theft. When an app has XSS, code running in the valid origin can perform actions with the user's privileges in many contexts; CSRF tokens do not cure XSS either.

### 7.3. CORS and API Permissions

CORS controls which origins the browser allows to read responses under browser mechanics. It does not protect APIs from curl, backend clients, or unauthenticated/unauthorized calls. APIs still need token/session verification and proper subject/action/resource decisions. Never treat `allowedOrigins("*")` as an "anyone is authorized" policy, and never mistake CORS for authentication.

## 8. Damage-Limitation Thinking: Assuming One Layer Has Already Been Bypassed

Defense in depth also matters after an attack gets past one defense point.

### 8.1. A User's Token Leaks

- Bypassed layer: attacker can present a valid bearer token.
- Remaining layers: minimal scopes/authorities, reasonable token expiration, revocation policies where applicable, object/tenant checks, anomalous access alerts.
- Limitation: while the token remains valid, permissions actually inside that token can still be abused; detection, revocation, and response processes are required. MFA at login **does not automatically invalidate** an already stolen token.

### 8.2. An Endpoint Forgot the Owner Check

- Failed layer: `authenticated()` lets every valid account enter.
- Damage-limiting layers: service policy if enforced, tenant-scoped queries, minimal DTOs, auditing, BOLA tests.
- Limitation: tenant scoping does not stop Bob from reading Alice's data inside **the same tenant**; ownership or specific policy checks are still needed.

### 8.3. A Service Account Is Compromised

- Failed layer: attacker obtains service credentials.
- Remaining layers: least privilege, network isolation, restricted DB rights, tenant constraints, access quotas, and monitoring.
- Limitation: segmentation/rate limits shrink blast radius without preventing actions the service account itself was legitimately granted.

### 8.4. A Dependency or Control Fails

If the authorization service fails to respond, never fall back to `permitAll()`. For sensitive operations, **fail closed** means not executing the action without a trusted allow decision. HTTP 503 can reflect an unavailable dependency; permission denials can use 403. Failing closed does not mean every error must return 403.

Other layers can keep operating safely: a public catalog can continue serving while a separate refund authorization system is disrupted, as long as no bypass is opened for sensitive operations.

## 9. Designing Sufficiently Independent Layers

Multiple layers does not mean pasting the same rule everywhere. To increase real effectiveness:

1. **Diversify controls by risk.** E.g., token authentication, object permissions in service, tenant-scoped queries in database, and independent auditing.
2. **Reduce shared dependencies.** If every layer trusts client-sent `tenantId`, a single spoofed input defeats all of them. Use trusted data sources.
3. **Create no shortcuts.** "Internal" endpoints, admin APIs, jobs, async workers, and message consumers still require proper identity and permission models.
4. **Deny by default.** Routes lacking explicit allow policies should be denied within protected scopes.
5. **Constrain privilege scope.** Database accounts, service accounts, token scopes, and user permissions should carry only necessary rights.
6. **Prioritize root-cause fixes.** A WAF reduces short-term risk, yet a BOLA bug in the service must still be fixed; never use an extra layer as an excuse to delay remediation.
7. **Measure detection and recovery.** Define alert recipients, detection time, credential revocation procedures, backup/restore drills, and audit mechanisms.
8. **Keep usability reasonable.** Overly heavy or broken layers that push operators into dangerous workarounds signal the need for redesign, automation, and better testing.

A layer only adds value when it can genuinely deny, detect, or limit damage for a clearly stated scenario. Test impact by **assuming each layer fails one by one**, instead of only proving the normal path works.

## 10. Testing by Scenario and by Layer

| Test Case | Layer to Prove | Expected Result |
| --- | --- | --- |
| Anonymous calls `GET /api/orders/100` | Authentication + request authorization | Does not return order |
| User with `order:read` reads another user's order | Object authorization | Denied / existence hidden per policy |
| User with same role in another tenant | Tenant boundary | Cannot read or alter other tenant's data |
| User with read permission calls `POST /cancel` | Action permission | Denied |
| Owner with cancel permission on paid order | Domain state | Does not modify order if policy forbids canceling |
| Browser session-cookie POST missing valid CSRF token | Request exploit protection | Request blocked |
| Wrong-type or oversized JSON | Input validation | 4xx, business logic not invoked |
| Payload attempting SQL injection via ID param | Query parameterization | SQL semantics unaltered |
| Successful API read | Response projection | Leaks no out-of-scope sensitive fields |
| Policy service timeout | Fail closed | No side effects permitted, appropriate error |
| Leak of a low-privilege credential | Least privilege | No access beyond granted scope |
| Misconfigured security headers | Browser protections | Tests catch missing/wrong headers and trigger risk review |
| Newly configured route missing policy | Default deny | Endpoint not exposed automatically |

Checking 401/403 status codes alone is insufficient: for state-changing actions, prove no side effects occurred. For instance, a denied request must not write to the database, send messages, or call payment providers. Object authorization tests should include users with the same role but different owner, different tenant, and nonexistent resource IDs.

### 10.1. Request-Level Spring Security Testing

With `spring-security-test` and Spring MVC MockMvc, you can verify URL rules:

```java
// Illustrative snippet in a Spring Boot test, not standalone Java.
mvc.perform(get("/api/orders/100")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:read"))))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders/100/cancel")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:cancel"))))
    .andExpect(status().isForbidden()); // Missing valid CSRF token
```

This example assumes controllers/services/test fixtures allowing Alice to read/cancel the order, a `MockMvc` configured with Spring Security, and appropriate static imports. The POST illustrates CSRF protection when the filter is active; if the app uses bearer tokens with another mechanism or customized CSRF, test behavior against the actual configuration. HTTP 200 on the read request is only **one condition** and does not prove object authorization works against another user. Add ownership tests at the service or integration layer.

A CSRF-permitted POST test case can use `.with(csrf())`, yet still requires an authorized user and valid order state. Never "fix" a test by disabling `csrf` globally.

### 10.2. Testing Each Layer Independently

Write at least one "negative test" per critical layer. Use real requests with invalid tokens, mocked service policies returning deny, a database seeded with two tenants, response snapshots to catch leaked fields, configs missing security properties, or simulated dependency timeouts. When one layer is simulated to fail, verify other layers still deny or contain scope as designed.

Never attempt to simulate bypassing a layer in production. In tests, verify under controlled conditions using fixtures/mocks and isolated environments to uncover policy gaps.

## 11. Common Mindset Traps

1. **"Having Spring Security is enough."** The framework does not automatically decide permissions on all domain objects, data sanitization, queries, infrastructure, or financial logic.
2. **"Successful login means everything is allowed."** Authentication only verifies identity; authorization depends on subject, action, resource, and context.
3. **"HTTPS makes the API safe."** TLS protects transport; it does not fix broken policies or input handling.
4. **"CORS blocks external sites, so CSRF isn't needed."** CORS and CSRF address different threats.
5. **"Only admins see the button, so the API is protected."** Hiding UI elements does not replace server-side authorization.
6. **"Add a WAF so we don't have to fix the backend."** Edge layers help but are not the source of truth for per-object permissions.
7. **"Random IDs mean nobody can access others' IDs."** Even with hard-to-guess IDs, missing object authorization remains a vulnerability.
8. **"`@Valid` stops all input attacks."** DTO constraints do not replace prepared statements, output encoding, and business authorization.
9. **"We logged it, so attacks are prevented."** Logs serve detection and investigation; side effects that already occurred are not rolled back automatically.
10. **"Multiple layers reading the role from a request header is safer."** Unverified input can fool every layer simultaneously.
11. **"One security layer errored out, let's let requests through temporarily."** For access controls or sensitive conditions, handle errors safely; never default to ALLOW.
12. **"We have happy-path tests, that's enough."** You must test missing login, missing role, wrong owner, wrong tenant, invalid state, and zero side effects on denial.

## 12. Checklist for a New Feature

Before shipping a feature to production, answer all question groups:

**Assets and Risks**
- Which data, state, or capabilities hold value? What happens if read, altered, or disrupted?
- Which actors pose risks? Are there call paths outside REST controllers?
- Which trust boundaries are crossed (browser, gateway, queue, service, database)?

**Preventive Controls**
- Where is identity authenticated from? Do tokens/sessions enforce proper audience, scope, expiration, and lifecycle rules?
- Do requests have endpoint/method rules? Are undeclared routes denied by default?
- Does the service check the right resource, owner, tenant, and business state?
- Are data queries scoped, parameterized, and using a least-privilege account?
- Is input validated, and are sensitive fields stripped from responses?
- Are CSRF, cookies, CORS, browser headers, and rate limits chosen to match the threat model?

**Detection, Recovery, and Testing**
- Which denials/warnings require auditing, metrics, and alerts? Do logs avoid secrets?
- When a token or account leaks, are revocation and blast-radius limits in place?
- When a dependency fails or config is missing, does the system deny sensitive actions?
- Have wrong owner, wrong tenant, wrong permission, wrong state, invalid CSRF, and zero side effects been tested?
- Assuming any single layer fails, how do remaining layers still limit damage?

## 13. Self-Check

**Question 1.** An API uses HTTPS and requires login, yet Bob still reads Alice's order by changing the ID. Which protection layer is missing?

**Question 2.** A user with `ROLE_USER` calls `POST /api/orders/100/cancel` without having the `order:cancel` permission. Can the broad role be considered enough?

**Question 3.** A session-cookie app has strict CORS yet omits CSRF tokens on sensitive POSTs. Why does CORS not automatically stop CSRF?

**Question 4.** `@Valid` ensures `orderId` is non-null. Are prepared statements and ownership checks still needed?

**Question 5.** If the policy service times out, can the system allow sensitive actions to preserve availability?

**Question 6.** If the service's owner check has a bug, does the repository's tenant filter still have value? What does it protect against and what does it miss?

**Question 7.** When a valid token is stolen, which layers limit the damage, and does MFA automatically prevent all misuse of that token?

**Suggested Answers**

1. Object-level authorization (ownership/tenant); HTTPS and authentication do not solve that.
2. No. Permission for the specific action and related resource conditions are required.
3. Browsers can send credentials automatically; CORS does not check intent or authorization of state-changing requests.
4. Yes. Validation, query safety, and authorization address distinct risks.
5. No. Without sufficient proof of authorization, block the action and log/report the error appropriately.
6. It can block **cross-tenant** access, yet cannot stop wrong-owner reads **within the same tenant**; the policy still needs fixing.
7. Small scopes/permissions, TTL, token revocation where applicable, object authorization, and monitoring reduce impact. MFA at login does not automatically invalidate a stolen token.

### References

- [OWASP Developer Guide – Security Principles / Defense in Depth](https://owasp.github.io/www-project-developer-guide/release/foundations/security_principles/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [Spring Security – Servlet Authorization: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
