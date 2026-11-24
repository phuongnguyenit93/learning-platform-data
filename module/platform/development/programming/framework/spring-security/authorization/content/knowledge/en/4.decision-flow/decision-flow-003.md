# AuthorizationManager and the Protected Object in Spring Security

In Spring Security, **authorization** is a decision about **whether the caller is permitted to perform the current operation on the object being protected**. The `AuthorizationManager<T>` interface is the general contract for making that decision. The type `T` is crucial: the framework does not merely supply the user's identity, it also supplies the **object/context of the operation being controlled** (*secure object*).

For example: the same employee may hold the `ORDER_READ` authority, yet only be allowed to view orders in an assigned store. When checked at the HTTP layer, the protected object may be the web request; at the service layer, the protected object may be a method invocation and its arguments. **The actual order in the database does not appear automatically inside that object**: the application must load and inspect it if the rule depends on owner, tenant, state, or limits.

This lesson explains the `AuthorizationManager` contract, decision flow, protected object types, HTTP/method security hooks, how to build policies, and testing decisions. Framework examples focus on **Spring Security 6.x on the Servlet stack**, with specific notes for APIs 6.4–6.5. The standalone Java example runs on **JDK 17+**.

## 1. What role does `AuthorizationManager<T>` play?

`AuthorizationManager<T>` is the interface for an access-decision component. It takes two primary inputs:

1. **`Supplier<Authentication>`**: a way to retrieve the caller's `Authentication` when truly needed. `Authentication` holds the principal, authorities, and authentication status; the supplier defers the cost of retrieving it.
2. **`T secureObject`**: the object/context being controlled. This can be an HTTP request, `RequestAuthorizationContext`, `MethodInvocation`, or the result context of a method invocation.

Picture the decision as:

~~~text
AuthorizationManager<T>
  input : Supplier<Authentication> + T secureObject
  output: AuthorizationResult / AuthorizationDecision
          granted = true  -> allow proceeding at corresponding checkpoint
          granted = false -> deny at corresponding checkpoint
          null             -> no decision made (abstain; must handle safely)
~~~

The relationship is not a rigid "role → endpoint" mapping. A manager can inspect authorities, path, HTTP method, method parameters, return values, or looked-up business data. **The same caller** can be allowed for resource A and denied for resource B.

In modern Spring Security, `AuthorizationManager` replaces the traditional `AccessDecisionManager` and `AccessDecisionVoter` model for new integrations. Applications typically use built-in managers or write custom managers when a policy cannot be fully expressed with `authenticated()`, `hasRole()`, or `hasAuthority()`.

### APIs to distinguish by version

In **Spring Security 6.5**, the relevant methods are:

~~~java
// Abbreviated signatures for learning the API (not the full interface definition).
AuthorizationResult authorize(Supplier<Authentication> authentication, T object);
AuthorizationDecision check(Supplier<Authentication> authentication, T object);
void verify(Supplier<Authentication> authentication, T object);
~~~

- `authorize(...)` was added in **6.4**, returning `AuthorizationResult` (which may be `null` if the manager abstains). When **calling a manager from application code** in 6.4+, prefer `authorize`.
- `check(...)` is the long-standing decision method returning `AuthorizationDecision`; it is **marked deprecated in 6.5** to encourage callers to use `authorize`. In the 6.5 API, `check` remains the abstract method of the functional interface, so **the lambda `(authentication, object) -> new AuthorizationDecision(...)` is still a valid way to declare a manager**. Spring Security 6.3 applications do not yet have the new `authorize` method.
- `verify(...)` serves cases where you want to enforce a decision via an exception: on a **deny** decision, it throws `AccessDeniedException`; do not equate `verify` with a `boolean`-returning function.
- `AuthorizationDecision(boolean granted)` is an implementation of `AuthorizationResult`. Check `isGranted()` when you need to know ALLOW vs. DENY.

If you write a policy for a specific Spring Security 6.5 application, you can use a `check`-compatible class/lambda and call `authorize` at call sites. Do not copy an `authorize` snippet from newer docs into an older Spring Security project without checking the API version.

**Important:** `null` means "abstain/no decision", **not an explicit DENY**. How a checkpoint handles `null` depends on the caller and how managers are composed. For sensitive operations, return **`new AuthorizationDecision(false)`** when information is missing or the allow condition is not met; do not rely on `null` hoping it will block access.

## 2. Is `T secureObject` the business record being protected?

**Not necessarily.** The name *secure object* simply denotes **the unit that the interceptor/filter is guarding at that moment**. The type `T` tells you what information the manager can see.

| Checkpoint | Typical manager type | Object/context passed | What can be checked? |
| --- | --- | --- | --- |
| Servlet request at `AuthorizationFilter` | `AuthorizationManager<HttpServletRequest>` | `HttpServletRequest` | URL, HTTP method, request info, and `Authentication`. |
| `.access(...)` rule in `authorizeHttpRequests` | `AuthorizationManager<RequestAuthorizationContext>` | `RequestAuthorizationContext` | `getRequest()` and path variables from the matcher via `getVariables()`. |
| Before method invocation | `AuthorizationManager<MethodInvocation>` | AOP Alliance `MethodInvocation` | Method, target object, arguments; can check before the method runs. |
| After method invocation | `AuthorizationManager<MethodInvocationResult>` | Method invocation **and returned result** | Can decide whether the caller is allowed to receive the result. |
| Application-organized policy | Application-chosen type `T` | DTO, command, or domain context | Information supplied by the application for business-level decisions. |

**Key distinction:** `RequestAuthorizationContext` is not `Order`; `MethodInvocation` is not `Customer`. A route `GET /api/orders/42` only supplies the **ID "42"**; it does not prove who owns order 42 or its current state. Any manager needing that data must load or be given **trusted server-side data**.

Concrete example:

~~~text
HTTP GET /api/orders/42
  secure object at filter: HttpServletRequest
  secure object at DSL .access: RequestAuthorizationContext
     request: GET /api/orders/42
     variables: {orderId: "42"} (if extracted by matcher)
  domain resource in DB:
     Order(id=42, tenantId="shop-a", ownerId="alice", status="PAID")
~~~

`getVariables()` only holds meaningful values when the request matcher provides extracted variables. Do not assume every URL pattern produces the same map. Also do not use `orderId` as proof of access: you must verify the caller against the **actual record**.

At the method security layer, `MethodInvocation` may contain an ID, a DTO object, or an amount parameter. If you need to check conditions on the state of a record being modified, the service must fetch the appropriate live data; the method call only provides the arguments passed in.

## 3. Decision flow at the HTTP Servlet layer

With `authorizeHttpRequests`, Spring Security uses `AuthorizationFilter` to guard requests. Overview flow:

~~~mermaid
flowchart TD
  A[HTTP request] --> B[Security filter chain]
  B --> C[Authentication established if needed]
  C --> D[AuthorizationFilter]
  D --> E[Supplier Authentication + HttpServletRequest]
  E --> F[AuthorizationManager routing by RequestMatcher]
  F --> G[Manager of matching rule]
  G --> H{AuthorizationResult}
  H -->|ALLOW| I[Continue FilterChain to controller]
  H -->|DENY| J[AccessDeniedException]
  J --> K[ExceptionTranslationFilter and appropriate response]
~~~

Step-by-step essence:

1. `AuthorizationFilter` creates a `Supplier<Authentication>` that retrieves the current identity from `SecurityContextHolder` when needed.
2. The request-layer manager inspects the path pattern, HTTP method, and declared rules. With `authorizeHttpRequests`, the **first matching matcher** determines the rule applied.
3. A rule can use built-in managers (`permitAll`, `denyAll`, `authenticated`, `hasAuthority`) or a custom manager passed via `.access(...)`.
4. If denied, Spring throws an access-control exception; `ExceptionTranslationFilter` coordinates with `AuthenticationEntryPoint` / `AccessDeniedHandler` to handle it. REST APIs typically return 401 for unauthenticated callers needing login and 403 for authenticated callers lacking permission; form login may redirect.
5. If allowed, the request **continues through the filter chain**. This **does not automatically prove** the controller/service will be permitted to operate on individual records; other policies at the method/service layer can still deny it.

Spring Security also provides authorization outcome events (`AuthorizationDeniedEvent`, `AuthorizationGrantedEvent`); whether granted events are actually recorded/published depends on `AuthorizationEventPublisher` and configuration, so do not assume every ALLOW result generates a log event.

Note that `AuthorizationFilter` is placed near the end of the security filter chain by default and can evaluate dispatches such as `REQUEST`, `FORWARD`, and `ERROR`. Matcher configuration must account for the application's actual flows. If you add custom filters after `AuthorizationFilter`, do not assume they are blocked in the same way.

## 4. Pairing a RequestMatcher with the right manager

Short configuration example in Spring Boot 3 + Spring Security 6:

~~~java
@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/admin/**").hasAuthority("ADMIN_PANEL")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

The snippet above is **configuration to place inside a Spring project**, requiring Spring Framework/Spring Security imports and an appropriate authentication mechanism. It is not standalone Java compilable with `javac` without libraries.

Each branch leads to a distinct authorization mechanism: `permitAll` does not need to read `Authentication`, `hasAuthority` checks authorities in `Authentication`, `authenticated` requires an authenticated user, and `denyAll` denies by default. `/api/orders/**` only requires login; **it does not yet check whose order it is**.

At the HTTP layer, `RequestMatcherDelegatingAuthorizationManager` is the standard implementation of `AuthorizationManager<HttpServletRequest>`: it selects a delegate based on `RequestMatcher`. When using the `.access(...)` configuration API, the application-supplied manager typically receives **`RequestAuthorizationContext`**. That is why two different generic types appear in the same HTTP flow without any design contradiction.

### Custom manager reading an ID from the path

A minimal example allowing order viewing only when the business policy verifies permission on **that exact order**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
class OrderSecurityConfig {

    @Bean
    SecurityFilterChain orderChain(HttpSecurity http,
                                   OrderReadPolicy policy) throws Exception {
        AuthorizationManager<RequestAuthorizationContext> canReadOrder =
                (authentication, context) -> {
                    String orderId = context.getVariables().get("orderId");
                    if (orderId == null || orderId.isBlank()) {
                        return new AuthorizationDecision(false);
                    }
                    // policy must verify identity, permissions, tenant/owner,
                    // and server-side Order data; do not trust the ID alone.
                    Authentication actor = authentication.get();
                    return new AuthorizationDecision(
                            policy.canRead(actor, orderId));
                };

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
                .access(canReadOrder)
            .anyRequest().denyAll()
        );
        return http.build();
    }

    interface OrderReadPolicy {
        boolean canRead(Authentication authentication, String orderId);
    }
}
~~~

This is a **Spring configuration snippet to place into a project with the corresponding dependencies**, not a standalone plain-JDK Java file. `OrderReadPolicy` only declares the contract; **the application must provide the real implementation** that retrieves user/tenant from a trusted security context, looks up the Order by ID, checks permissions and owner/tenant, and returns `false` if any condition is missing. The example uses the `check` API via a lambda compatible with Spring Security 6.x; in 6.5 it is a functional interface with abstract `check` and default `authorize`.

Detail to read carefully: `context.getVariables().get("orderId")` is a **routing parameter**, not a business object. `.access(canReadOrder)` invokes the manager for matching requests; if the matcher cannot extract `orderId`, the example denies. The `actor` value returned by the supplier may represent an unauthenticated/anonymous caller; the policy must check properly and **not merely trust `isAuthenticated()`**, because anonymous representations in Spring Security can use an `Authentication` with the authenticated flag set.

Querying the database inside a request manager can cost extra queries; when the controller/service subsequently loads the same order, it easily causes **duplicate queries** and a data-change window. For sensitive state-modifying operations, keep invariant checks close to the update in the service, using appropriate transactions and concurrency controls. The request manager example illustrates how *secure object* works, not a requirement that every ownership check live in a filter.

## 5. Decision flow at the method layer

At the service layer, the protected object is usually **`MethodInvocation`**, rather than an HTTP request. Spring Security uses AOP proxies and interceptors such as:

- `AuthorizationManagerBeforeMethodInterceptor` paired with `PreAuthorizeAuthorizationManager` to check **before** the method runs.
- `AuthorizationManagerAfterMethodInterceptor` paired with `PostAuthorizeAuthorizationManager` to check **after** the method returns a result.
- `@EnableMethodSecurity` enables mechanisms such as `@PreAuthorize` and `@PostAuthorize`; Spring Boot Starter Security **does not enable method security automatically**.

Illustrative snippet in a Spring-managed service:

~~~java
@Service
class OrderService {
    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderDto loadOrder(String orderId) {
        // Load the real Order and apply tenant/owner policy.
        // Only convert to OrderDto after passing all conditions.
        return serviceLogicForAuthorizedOrder(orderId);
    }
}
~~~

`OrderDto` and `serviceLogicForAuthorizedOrder` are hypothetical application components; the snippet above **does not run standalone**. When the proxy intercepts a call to `loadOrder("42")`, `MethodInvocation` can expose the method name and argument `"42"`. `PreAuthorizeAuthorizationManager` evaluates the expression against `Authentication` and the invocation context; checking `ORDER_READ` **does not automatically check the owner of Order 42**. Logic inside the method or a policy bean must handle that part.

Example protecting returned data after the method returns:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public OrderDto findOrder(String id) {
    return repositoryAndMapper.loadOrderDto(id);
}
~~~

`@PostAuthorize` can inspect the **returned object** to refuse disclosing the result if the owner does not match. Executing the method first and checking afterward can suit **side-effect-free queries**; never use post-checks as a "safety brake" for operations that already transferred money, sent emails, or wrote data. For writes/updates, check **before the action** and guard conditions inside the transaction.

`MethodInvocationResult` includes both the method invocation and the returned value, giving the post-check manager more information than the pre-check manager. Note that `@PostAuthorize` only applies to results and calls passing through the appropriate interceptor; it does not replace query/resource-level access control.

**Proxy limitation:** a call from one method to another on the **same instance** can bypass the AOP proxy and fail to trigger method security as expected. If a business operation must uphold an invariant, enforce it in a shared service/policy layer and test non-controller entry points as well.

## 6. "Being protected" has two different layers

A common mistake is equating **the object Spring intercepts** with **the final business data**.

| Question | At the filter layer | At the service layer |
| --- | --- | --- |
| What is the framework protecting? | A request matching a matcher. | A method invocation / method result. |
| Is the resource ID available? | Possibly in the path/query. | Possibly in the parameters. |
| Are owner, tenant, and record state known? | Usually **not**, without extra lookup. | **Only when** the service/policy has loaded that data. |
| What decision suffices to pass this layer? | Satisfying HTTP conditions. | Satisfying method call conditions and business data rules. |
| Is it completely safe after passing this layer? | No; the service still needs to scope data. | Update logic and concurrency invariants must also be ensured. |

**BOLA/IDOR** example: both `GET /api/orders/42` and `GET /api/orders/43` pass `authenticated()`. However, Order 42 belongs to Alice and Order 43 belongs to Bob. If Alice changes the ID in the URL, a request-level manager checking only "logged in" still lets it through, while the service must deny Order 43 unless Alice holds valid permission to view it.

Conversely, to block an internal backoffice API, an HTTP rule requiring an authority can already serve as a useful layer of defense. **Where enforcement lives depends on what information the decision needs.** Do not force every rule into a URL expression, and do not skip request authorization just because the service has a policy.

For multi-tenant data, list queries should filter by tenant/authorization directly at the data layer when appropriate. Fetching all records and filtering afterward can leak metadata, total counts, pagination, or incur unnecessary processing costs. For update methods, consider the latest data, transactions, and optimistic/pessimistic concurrency control.

## 7. Why is the `Authentication` input a `Supplier`?

`Supplier<Authentication>` lets a manager **read the identity only when the rule needs it**. For example, `permitAll` allows a public endpoint without loading authentication from the session. This avoids unnecessary work and keeps rules cleanly structured.

~~~text
GET /api/catalog          -> permitAll -> ALLOW, no need to read Authentication
GET /api/orders/42        -> hasAuthority / custom policy
                           -> needs Authentication to evaluate permissions
GET /api/internal/secret  -> denyAll -> DENY, no need to read Authentication
~~~

In a custom manager, if an initial check determines the request is invalid, it can return DENY before calling `authentication.get()`. Never store a `Supplier` beyond the request lifecycle or assume it represents an immutable principal across asynchronous threads.

In Spring Security Servlet apps, `Authentication` typically comes from `SecurityContextHolder`. `Authentication` is **not** `AuthorizationResult`: it describes identity/status and authorities; the manager uses that information together with the secure object to make a decision. **Successful login does not mean access to every object**.

## 8. Standalone Java 17 example: permission depends on caller and object

The following program uses **`Supplier<Actor>`** and a **`ProtectedAction`** object to model the exact two-input shape of a policy. It **does not use Spring libraries** and does not try to emulate every Spring Security API, but lets you observe decisions and supplier laziness.

Example policy:

- Public documents may be read without looking up identity.
- Private documents require being authenticated, in the same tenant, and having `DOC_READ`.
- The document owner may read; someone with `DOC_READ_ALL` may read other documents **within the same tenant**.
- Any operation other than `READ` is denied under this illustrative policy.

Save with exact filename **ProtectedObjectDecisionDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class ProtectedObjectDecisionDemo {
    enum Operation { READ, EDIT }

    record Actor(String userId, String tenantId,
                 Set<String> permissions, boolean authenticated) {}

    record Document(String tenantId, String ownerId, boolean publiclyReadable) {}

    record ProtectedAction(Operation operation, Document document) {}

    record Decision(boolean granted) {}

    static Decision decide(Supplier<Actor> currentActor,
                           ProtectedAction secured) {
        Document document = secured.document();
        if (secured.operation() == Operation.READ && document.publiclyReadable()) {
            return new Decision(true);
        }
        Actor actor = currentActor.get();
        if (actor == null || !actor.authenticated()) {
            return new Decision(false);
        }
        if (secured.operation() != Operation.READ
                || !actor.tenantId().equals(document.tenantId())
                || !actor.permissions().contains("DOC_READ")) {
            return new Decision(false);
        }
        boolean owner = actor.userId().equals(document.ownerId());
        boolean allInTenant = actor.permissions().contains("DOC_READ_ALL");
        return new Decision(owner || allInTenant);
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "shop-a", Set.of("DOC_READ"), true);
        Actor manager = new Actor("mary", "shop-a",
                Set.of("DOC_READ", "DOC_READ_ALL"), true);
        Actor noPermission = new Actor("alice", "shop-a", Set.of(), true);
        Actor anonymous = new Actor("guest", "shop-a",
                Set.of("DOC_READ", "DOC_READ_ALL"), false);
        Document publicDoc = new Document("shop-a", "alice", true);
        Document ownDoc = new Document("shop-a", "alice", false);
        Document otherDoc = new Document("shop-a", "bob", false);
        Document foreignDoc = new Document("shop-b", "bob", false);

        AtomicInteger lookups = new AtomicInteger();
        Supplier<Actor> suppliedAlice = () -> {
            lookups.incrementAndGet();
            return alice;
        };

        System.out.println("Public read: " + decide(suppliedAlice,
                new ProtectedAction(Operation.READ, publicDoc)).granted());
        System.out.println("Authentication lookups for public: " + lookups.get());
        System.out.println("Owner read: " + decide(() -> alice,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Different owner: " + decide(() -> alice,
                new ProtectedAction(Operation.READ, otherDoc)).granted());
        System.out.println("Manager same tenant: " + decide(() -> manager,
                new ProtectedAction(Operation.READ, otherDoc)).granted());
        System.out.println("Manager other tenant: " + decide(() -> manager,
                new ProtectedAction(Operation.READ, foreignDoc)).granted());
        System.out.println("Missing permission: " + decide(() -> noPermission,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Anonymous: " + decide(() -> anonymous,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Unsupported edit: " + decide(() -> manager,
                new ProtectedAction(Operation.EDIT, ownDoc)).granted());
    }
}
~~~

Compile and run commands on JDK 17 or higher:

~~~bash
javac ProtectedObjectDecisionDemo.java
java ProtectedObjectDecisionDemo
~~~

Expected output:

~~~text
Public read: true
Authentication lookups for public: 0
Owner read: true
Different owner: false
Manager same tenant: true
Manager other tenant: false
Missing permission: false
Anonymous: false
Unsupported edit: false
~~~

**Explanation:** `ProtectedAction` holds both the **operation** and the **Document**, so the policy has enough data to decide. Even though the manager has `DOC_READ_ALL`, a document in a different tenant is still denied. For the public document, the ALLOW branch runs **before** `currentActor.get()`, so the supplier counter stays at 0. Changing `Operation.READ` to `EDIT` causes the policy to return DENY because no allow path is defined for that operation.

In a real application, `Document.publiclyReadable()`, owner, tenant, and security attributes must come from verified server-side data; callers must never send `publiclyReadable=true` to unlock access. `Actor` must represent verified authentication data, not arbitrary client-supplied claims.

## 9. When to use a built-in manager vs. a custom manager?

Use a built-in manager when the policy is simple and stable:

| Goal | Commonly used mechanism | Boundary |
| --- | --- | --- |
| Truly public resource | `permitAll` | Does not need to retrieve Authentication. |
| Default block | `denyAll` | No allowed access path. |
| User must be logged in | `authenticated` | Does not yet decide on individual resources. |
| Exact authority required | `hasAuthority("ORDER_READ")` | Does not know the owner/tenant of individual orders. |
| Convention-based role required | `hasRole("ADMIN")` | By default checks the `ROLE_ADMIN` authority. |
| Select rule by URL and HTTP method | `authorizeHttpRequests` + `requestMatchers` | First matching rule applies. |
| Decision by request/method + dynamic data | `.access(customManager)` or policy service | Must proactively fetch trusted data and determine the result. |

Spring Security also provides specialized managers such as `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager`, `RequestMatcherDelegatingAuthorizationManager`, `PreAuthorizeAuthorizationManager`, and `PostAuthorizeAuthorizationManager`. These components **serve different object/context types**, so do not force `AuthorizationManager<MethodInvocation>` into a slot expecting `AuthorizationManager<RequestAuthorizationContext>`.

In large systems, managers can be composed with AND/OR or backed by a dedicated policy engine. When doing so, explicitly define how **ALLOW, DENY, and abstain** outcomes are handled; an allowed role branch must not accidentally bypass tenant/owner or state checks. For complex business rules, a policy function with clear inputs and unit tests is often easier to audit than a long expression string.

## 10. Avoiding confusion about the "protected object"

1. **Assuming `T` is always an entity.** In practice it is usually a request/method invocation. → Identify the exact type `T` at each checkpoint and only read data that the object actually contains.
2. **Confusing path ID with ownership.** `/orders/42` only carries an ID. → Look up the real owner/tenant from the server and compare against the trusted caller.
3. **Having only `authenticated()` and believing every record is protected.** → Add data-level enforcement in the service/domain layer.
4. **Using `AuthorizationManager<MethodInvocation>` for HTTP `.access`.** → Use `AuthorizationManager<RequestAuthorizationContext>` in the HTTP DSL; method security has its own context types.
5. **Calling `authentication.get()` in every branch.** → `permitAll`/`denyAll` rules may not need to read Authentication; optimize conditionally without breaking correctness.
6. **Returning `null` when data is missing expecting fail-closed behavior.** → Return an explicit DENY in risky cases or when mandatory conditions are absent.
7. **Relying on `@PostAuthorize` to block actions with side effects.** → Check before writing and use transaction/concurrency guards when needed.
8. **Trusting client-sent data as the protected resource.** → Use server-side records/current state and verified claims/authorities.
9. **Placing policy only in one controller.** → Other service call paths, jobs, and message consumers must uphold the same invariants.
10. **Mixing API versions inconsistently.** → Verify `check`/`authorize` against the Spring Security version in use; do not assume every newer snippet compiles on 6.3.
11. **Ignoring request dispatches and matcher order.** → Test FORWARD/ERROR when relevant and ensure specific rules precede broad rules.
12. **Testing only the ALLOW path.** → Test DENY for missing authority, changed ID, changed tenant, status, and authentication state.

## 11. Test matrix for managers and protected objects

Manager tests are most valuable when holding authentication constant while **varying the protected object**:

| Input | Object/context | Expected result |
| --- | --- | --- |
| Unauthenticated caller | Request to private API | DENY; REST typically returns 401 if auth is needed. |
| Caller with `ORDER_READ` | Request to view valid order in same tenant/owner | ALLOW if full policy is satisfied. |
| Same caller, same authority | Request to view someone else's out-of-scope order | DENY. |
| Same caller, same authority | Request with nonexistent order ID | DENY or 404 per API convention, without leaking data. |
| Caller in tenant A | Request with order ID belonging to tenant B | Consistent DENY/404, no cross-tenant leak. |
| Caller with valid role but missing permission | Request to action requiring permission | DENY. |
| Public object | `permitAll` | ALLOW without needing to retrieve Authentication. |
| No valid matcher | `anyRequest().denyAll()` | DENY. |
| Method with valid arguments | `MethodInvocation` satisfying policy | Allow call to proceed. |
| Same method with different ID | `MethodInvocation` with out-of-scope ID | Denied before sensitive processing. |
| Method returning undisclosed record | Post-check context `MethodInvocationResult` | Refuse returning data per appropriate policy. |
| Two concurrent write requests | Same resource, state changing | Only valid update succeeds via transaction/locking conditions. |

With Spring Security Test, you can use `MockMvc` to test request-level authorization, `@WithMockUser` or test `SecurityContext` specifying exact authorities and roles, and add service/policy tests for each owner/tenant/status combination. When testing a custom manager, verify the exact variables extracted by `RequestMatcher` and verify that the supplied `Authentication` has authorities matching the real source.

If you only test that `GET /api/orders/42` returns 200 for Alice, you have not proven object-level authorization. The crucial test is **the same Alice calling `/api/orders/43`**, belonging to someone else, which must be blocked.

## 12. Process for designing an `AuthorizationManager` for a new feature

When given a requirement such as "Employees may export customer reports", proceed step by step:

1. **Define the operation and resource:** which report is exported, which organization, which data filters.
2. **Identify the caller and required authority:** e.g., `CUSTOMER_REPORT_EXPORT`, not inferred from simply being logged in.
3. **Determine data conditions:** tenant/branch, allowed customer scope, account status, data limits.
4. **Choose checkpoints and type `T`:** HTTP request needs to guard endpoint access; service needs to guard actual execution/data scoping; both can be used.
5. **Choose built-in vs. custom manager:** use `hasAuthority` for simple checks; use a policy service or checkpoint-appropriate `AuthorizationManager<T>` for complex ones.
6. **Define explicit DENY:** missing context, invalid ID, wrong tenant, or unauthenticated state must never create an implicit ALLOW path.
7. **Control updates and output data:** do not use post-checks to justify side effects; filter data at query time and guard write operations.
8. **Write tests for both inputs:** hold principal constant and vary the object; hold object constant and vary principal/authority; add unauthenticated and concurrency cases.
9. **Observe and operate:** record necessary audits for sensitive decisions without exposing tokens or personal data; monitor whether 403s stem from mapper/permission issues or object policy.

**Key takeaway:** `AuthorizationManager<T>` answers the access question by combining **who is asking** (`Supplier<Authentication>`) with **what is being protected** (`T`). In HTTP, `T` is typically the request/request context; in method security, `T` is typically the invocation or invocation result. That is the entry point for making a decision, but **the business record and its control conditions must be verified separately when needed**. An ALLOW decision at one layer does not remove the responsibility to protect data at subsequent layers.

### References

- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — RequestAuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html)
