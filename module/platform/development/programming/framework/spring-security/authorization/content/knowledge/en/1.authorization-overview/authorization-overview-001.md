# Authorization: Who Can Do What on Which Resource?

In an application, **authorization** answers a business question: **which subject is allowed to perform which action on which specific resource, under which conditions?** This is the starting point for designing a Spring Security policy, before choosing annotations or writing HTTP configuration.

After this lesson, you will be able to separate authentication from authorization, express an access rule using business data, distinguish URL-level checks from per-resource checks, and build test scenarios for allow/deny decisions.

## 1. Four Components of an Authorization Decision

A decision can be thought of as:

~~~text
canAccess(subject, action, resource, context) -> ALLOW or DENY
~~~

| Component | Question | Example in an Order System |
| --- | --- | --- |
| **Subject** | Who is making the request? | User `alice`, logged in, belongs to store `shop-a`, has authority `ORDER_READ_OWN`. |
| **Action** | What does that person want to do? | View order, cancel order, refund, export report; not necessarily just GET/POST/PUT/DELETE. |
| **Resource** | Which object does the action target? | Order #42, owner `alice`, belongs to `shop-a`. |
| **Context** | Which conditions must hold? | Same store/tenant, order status still allows cancellation, policy is active. |

For example, the statement "an authenticated user can access `/api/orders/42`" only answers part of the question. To **view order 42**, the system still needs to know whether the caller has permission to read orders, whether the order belongs to a store they are allowed to access, and their relationship to that order. To **cancel order 42**, it also needs to check whether the status allows cancellation.

A useful rule of thumb: **successful login does not imply permission on all data**; nor does a resource identifier in the URL prove ownership.

## 2. How Does Authentication Differ from Authorization?

- **Authentication:** verifies identity and establishes caller information. For example: a valid token indicates the request comes from account `alice`.
- **Authorization:** relies on the known identity together with a policy to decide whether a specific action is permitted. For example: `alice` can only view her own orders in the right store.
- **UI visibility:** hiding the "Cancel" button for unauthorized users makes the experience clearer, but **cannot replace server-side checks**. APIs can be called directly without going through the UI.

Access outcomes typically have two branches. If unauthenticated and the endpoint requires login, a REST API usually returns **401 Unauthorized**; if authenticated but lacking permission, it usually returns **403 Forbidden**. Form-based login mechanisms, entry points, and custom handlers may redirect or return different responses. Therefore, do not treat HTTP status codes as the policy itself; HTTP codes only represent how a denial is handled.

## 3. Turning Business Statements into Testable Policies

Suppose we have a multi-store (**multi-tenant**) order management system. We choose an example policy:

1. Every operation on an order requires being **authenticated** and in the **same tenant** as the order.
2. Authority `ORDER_READ_OWN` allows reading **orders owned by the caller themselves**. Authority `ORDER_READ_ALL` allows reading orders within the caller's tenant.
3. Authority `ORDER_CANCEL_OWN` allows canceling one's own orders; `ORDER_CANCEL_ALL` allows canceling orders within the tenant. **Both still require the order status to allow cancellation**.
4. If any mandatory condition is not met, **deny**. Having no matching rule must also deny according to the *deny by default* principle.

Illustrative decision table:

| Caller / Operation | Requested Order | Decision | Reason |
| --- | --- | --- | --- |
| Alice has `ORDER_READ_OWN` and wants to read | Alice's order in `shop-a` | ALLOW | Right authority, right owner, and right tenant. |
| Alice has `ORDER_READ_OWN` and wants to read | Bob's order in `shop-a` | DENY | Not the owner, does not have permission to read all orders. |
| Support staff has `ORDER_READ_ALL` and wants to read | Alice's order in `shop-a` | ALLOW | Has read permission within the tenant. |
| Support staff only has `ORDER_READ_ALL` and wants to cancel | Alice's order in `shop-a` | DENY | Read permission does not equate to cancel permission. |
| Support staff has `ORDER_READ_ALL` and wants to read | Order in `shop-b` | DENY | Different tenant, even though they have permission to read all orders in their own tenant. |
| Alice has `ORDER_CANCEL_OWN` and wants to cancel | Alice's already-processed order | DENY | Right owner, but the status does not allow it. |

Notice the difference between **general permissions** and **object-level conditions**. `ORDER_READ_ALL` does not mean "every order in every tenant". A broad permission can still be constrained by organization, data scope, status, or legal/regulatory rules. Tenant and identity must be obtained from a trusted authentication context or verified server-side data—never accept an arbitrary ID sent by the client and treat it as proof of permission.

## 4. Roles, Authorities, Ownership, and Policy Models

**RBAC (Role-Based Access Control)** assigns permissions through roles, such as `CUSTOMER`, `SUPPORT`, `ADMIN`. It is well suited for answering "which user group can access which features?", but a role alone does not know who owns an order.

**ABAC (Attribute-Based Access Control)** makes decisions based on attributes of the subject, resource, and context, such as `actor.tenantId == order.tenantId` or `order.cancellable == true`. It works well for dynamic rules based on status, organization, and time.

**ReBAC (Relationship-Based Access Control)** relies on relationships between the subject and the resource, such as "creator", "shared with", or "project member". Checking `actor.id == order.ownerId` is a simple ownership relationship.

These models **can be combined**. For example: a user needs the `ORDER_CANCEL_OWN` (**permission**), to be the right owner (**relationship**), in the same tenant with an unprocessed order (**attributes**). A good rule is typically a logical **AND** of mandatory conditions, combined with **OR** across explicitly allowed paths, avoiding accidental grants due to a missing check.

In Spring Security, `Authentication` contains `GrantedAuthority` instances. An authority is usually a string indicating a permission or role assigned by the system. With the default configuration, `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority, whereas `hasAuthority("ORDER_READ_ALL")` matches that exact string. Do not confuse the role name in code with the actual authority value inside `Authentication`.

**Authorities do not automatically replace object queries.** For instance, storing tens of thousands of order IDs as individual authorities per user is usually not an appropriate way to protect individual orders. Checking tenant, ownership, and status in the business layer using current data is usually much clearer.

## 5. Where Should Checks Live in a Spring Security Application?

There are three complementary layers of responsibility:

| Check Layer | What Does It Know? | Primary Responsibility |
| --- | --- | --- |
| **HTTP/request** | Path, HTTP method, and authentication info | Block public/internal endpoints, require login or coarse-grained permissions. |
| **Method/service** | Business operation, method arguments, current user | Block unauthorized business calls, even when a service has multiple entry points. |
| **Domain/resource** | Actual object in the database: owner, tenant, status | Decide on **individual records or sets of records**; protect against accessing the wrong object. |

Example **Spring Boot 3 / Spring Security 6 with Java 17+** configuration for the HTTP layer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

This is a **configuration snippet to place in a Spring Boot project with the Spring Security dependency**, not a standalone file compiled directly with `javac`. Specific rules come first, with `anyRequest().denyAll()` as the final fallback. With `authorizeHttpRequests`, Spring Security evaluates request matchers in order and uses the **first matching rule**. `permitAll` should only apply to truly public endpoints.

Key point: `.requestMatchers("/api/orders/**").authenticated()` **only guarantees that the user is logged in**; it does not ensure they own the order or belong to the right tenant. After loading the order from the database, the service still has to apply business policy to decide `READ` or `CANCEL`. Avoid inferring permission from the ID in the URL or from the user being able to reach the controller.

The `@EnableMethodSecurity` annotation enables mechanisms such as `@PreAuthorize` on methods in Spring-managed beans. For example, `@PreAuthorize("hasAuthority('ORDER_READ_ALL')")` only checks the authority; if the method returns a list of orders, the method itself still needs to restrict the query by tenant. For a specific object, you can delegate to a policy bean that checks the resource ID and `Authentication`, or check explicitly in the service after loading the object. Note that method security is based on Spring AOP proxies: internal calls from one method to another on the same instance may bypass the interceptor.

On the servlet stack, `AuthorizationFilter` and `AuthorizationManager` help enforce HTTP-level permissions; `ExceptionTranslationFilter` participates in converting security exceptions into appropriate responses. In business design, we focus first on **the conditions to allow or deny**, and only then choose which Spring Security hook/location to use for enforcement.

## 6. Standalone Java 17 Example: Decision on an Order

The following program intentionally **does not use Spring** to highlight the core policy. `Principal` represents verified caller information; `Order` is the resource data. In real integration, these values must come from the authentication system and server-side data, not self-assigned from client requests.

Save the program as **AuthorizationDecisionDemo.java**:

~~~java
import java.util.Set;

public class AuthorizationDecisionDemo {
    enum Action { READ, CANCEL }

    record Principal(String userId, String tenantId,
                     Set<String> authorities, boolean authenticated) {}

    record Order(String ownerId, String tenantId, boolean cancellable) {}

    static boolean allowed(Principal actor, Action action, Order order) {
        if (actor == null || !actor.authenticated()
                || !actor.tenantId().equals(order.tenantId())) {
            return false;
        }
        return switch (action) {
            case READ -> actor.authorities().contains("ORDER_READ_ALL")
                    || (actor.authorities().contains("ORDER_READ_OWN")
                        && actor.userId().equals(order.ownerId()));
            case CANCEL -> order.cancellable()
                    && (actor.authorities().contains("ORDER_CANCEL_ALL")
                        || (actor.authorities().contains("ORDER_CANCEL_OWN")
                            && actor.userId().equals(order.ownerId())));
        };
    }

    public static void main(String[] args) {
        Principal alice = new Principal("alice", "shop-a",
                Set.of("ORDER_READ_OWN", "ORDER_CANCEL_OWN"), true);
        Principal support = new Principal("sue", "shop-a",
                Set.of("ORDER_READ_ALL"), true);
        Principal anonymous = new Principal("guest", "shop-a",
                Set.of("ORDER_READ_ALL"), false);
        Order ownNew = new Order("alice", "shop-a", true);
        Order ownProcessed = new Order("alice", "shop-a", false);
        Order otherTenant = new Order("bob", "shop-b", true);

        System.out.println("Alice reads own order: "
                + allowed(alice, Action.READ, ownNew));
        System.out.println("Alice cancels processed order: "
                + allowed(alice, Action.CANCEL, ownProcessed));
        System.out.println("Support reads same-tenant order: "
                + allowed(support, Action.READ, ownNew));
        System.out.println("Support cancels without permission: "
                + allowed(support, Action.CANCEL, ownNew));
        System.out.println("Cross-tenant read: "
                + allowed(support, Action.READ, otherTenant));
        System.out.println("Unauthenticated read: "
                + allowed(anonymous, Action.READ, ownNew));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

Expected output:

~~~text
Alice reads own order: true
Alice cancels processed order: false
Support reads same-tenant order: true
Support cancels without permission: false
Cross-tenant read: false
Unauthenticated read: false
~~~

Read the first two conditions of `allowed` carefully: if unauthenticated or in a different tenant, **DENY before evaluating each action**. The `READ` branch allows two specific paths: having permission to read all in the tenant, or having permission to read one's own *and* actually being the order owner. The `CANCEL` branch adds a status condition. This rule models a sample policy; real systems may also require account lock status, branch-level permissions, time limits, refund rules, etc.

## 7. Designing Tests Around Decisions, Not Just Endpoints

When writing security requirements, create a table with **subject + authority + action + resource + context + expected outcome**. At minimum, test:

| Scenario | Expectation |
| --- | --- |
| Unauthenticated call to a protected API | Denied; standard REST API returns 401. |
| Authenticated but missing authority | DENY; standard REST API returns 403. |
| Has `READ_OWN`, views own order | ALLOW if other conditions are valid. |
| Has `READ_OWN`, changes ID to someone else's order | DENY, even when the endpoint is identical. |
| Has `READ_ALL`, accesses an order from another tenant | DENY. |
| Has cancel permission, but order is no longer cancellable | DENY. |
| Has right permission, same tenant, valid status | ALLOW. |
| Calls the same service from another controller or internal flow | Business policy is still enforced. |

In Spring Boot, you can combine HTTP tests using MockMvc with policy/service tests using real order data or fixtures. Do not only test 200 responses for authorized users; **negative cases** (especially changing the ID, changing the tenant, changing the status) are what uncover most object-access bugs.

A common critical vulnerability is **IDOR/BOLA**: an API allows a user to swap an ID in the path to read or modify someone else's resource. For example, `GET /api/orders/42` and `GET /api/orders/43` both pass `authenticated()`, yet only one order belongs to the caller. Permissions must be checked on **the actual loaded object**; for listing APIs, the query must be scoped from the outset so out-of-scope data is never returned.

## 8. Common Mindset Pitfalls and How to Avoid Them

1. **"Being logged in is enough."** Authentication only identifies the caller; always bind actions to the corresponding object and conditions.
2. **"Having the ADMIN role bypasses all limits."** Only create exceptions when explicitly allowed by business requirements; tenant, status, and other regulatory limits may still be mandatory.
3. **"Hiding the button in the UI is enough."** Always check on the server, regardless of whether requests come from a browser, mobile app, script, or another entry point.
4. **"URL checks are enough."** HTTP rules do not capture owner, tenant, or record status; combine them with service/domain policies.
5. **"The client sends tenantId/ownerId so we can trust it."** Use verified identity/tenant and check relationships against server data. Never equate input data with granted permission.
6. **"If no deny rule matches, allow it."** Prefer **deny by default** and *least privilege*; write broad rules very carefully.
7. **"One check in the controller protects everywhere."** Reuse policies in the business layer when the same operation has multiple entry points. Watch out for proxy limitations when relying on method security.
8. **"Testing the happy path is enough."** Test missing permissions, different owner, different tenant, boundary statuses, and runtime permission changes. Consider auditing deny decisions without logging tokens or sensitive data.

## 9. How to Turn a New Requirement into a Policy

When given the statement "staff can edit orders", clarify step by step:

1. **Who:** all staff, only staff belonging to that store, or only the person assigned to the order?
2. **What:** are editing the shipping address, changing the price, canceling, and refunding separate permissions?
3. **Which resource:** all orders in the tenant, team orders, or only assigned orders?
4. **When:** only before shipping, under a value limit, requiring additional approval?
5. **Decision and verification:** write out the ALLOW conditions and DENY cases explicitly, enforce them in the service, and create tests for every branch.

For example, replace the vague sentence with: "Staff with `ORDER_EDIT_ADDRESS` may change the address of an order in their own tenant, only when the order has not yet been handed over for shipping." The testable rule is:

~~~text
ALLOW when:
  authenticated
  AND hasAuthority(ORDER_EDIT_ADDRESS)
  AND actor.tenantId == order.tenantId
  AND order.shippingStatus == NOT_HANDED_OVER
DENY in all other cases
~~~

**Key takeaway:** Authorization is not just "what role does the user have". The complete answer is **who + action + specific resource + context + rules consistently enforced on the server**. Spring Security provides the mechanisms to enforce it; the ALLOW/DENY policy itself must first be clearly defined from the business requirements.

### References

- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
