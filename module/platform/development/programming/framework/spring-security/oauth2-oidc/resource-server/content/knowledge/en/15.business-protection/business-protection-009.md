# Proxies, Internal Calls, and Cases Where Annotations Are Not Applied

## 1. Why Can a Method with `@PreAuthorize` Still Execute?

In Spring Boot, an **OAuth 2.0 Resource Server** endpoint may already validate Bearer access tokens yet still need to protect business actions such as reading, modifying, or approving an order. Spring Security supports **method security** via annotations like `@PreAuthorize` and `@PostAuthorize`.

Example of a developer's intent:

~~~java
@Service
public class OrderApprovalService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Approval action requiring special permission.
    }
}
~~~

If a controller invokes this method **through a Spring bean wrapped by a proxy**, Spring Security gets the opportunity to intercept the call, check `SCOPE_orders.approve`, and deny access when permissions are insufficient.

However, the following situation often surprises developers:

~~~java
@Service
public class OrderApprovalService {

    public void approveFromWorkflow(long orderId) {
        // Internal call on the current object itself.
        this.approve(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Writes "APPROVED" status to the database.
    }
}
~~~

When an external component calls `approveFromWorkflow(...)` through the proxy, the outer method **is not protected by its own annotation**; inside it, calling `this.approve(...)` typically runs directly on the target object **without going back out through the proxy**. As a result, `@PreAuthorize` on `approve(...)` may **not execute** under Spring's default AOP proxy mode.

This is the core theme of this lesson: **an annotation in source code does not guarantee every path reaching the method will be checked**. You must understand where Spring AOP proxies sit, which calls pass through them, and how to design business boundaries so no unintended bypass paths exist.

This lesson focuses on **Spring Security Servlet Resource Servers** (Spring MVC, Bearer JWT/opaque tokens) and Spring's **proxy-based** method security. Several limitations also apply generally to Spring AOP features like `@Transactional` or `@Async`, though the focus here is **business protection**.

## 2. Two Protection Layers: HTTP Requests and Business Methods

### 2.1. Resource Server Protection in the HTTP Filter Chain

With a JWT access token:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
~~~

conceptual flow:

~~~mermaid
flowchart TD
    A["HTTP Request + Bearer token"] --> B["Spring SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["JwtDecoder / JWT validators"]
    D --> E{"Valid token?"}
    E -->|"No"| F["401"]
    E -->|"Yes"| G["JwtAuthenticationToken + SecurityContext"]
    G --> H["AuthorizationFilter"]
    H --> I{"HTTP policy allows?"}
    I -->|"No"| J["403 or challenge"]
    I -->|"Yes"| K["Spring MVC Controller"]
    K --> L["Service method via Spring AOP proxy"]
    L --> M["@PreAuthorize / method authorization"]
    M --> N["Business logic executes if valid"]
~~~

The diagram depicts key milestones, not a fixed filter list. When using opaque tokens, authentication may pass through `OpaqueTokenIntrospector` instead of `JwtDecoder`; the proxy behavior at the service layer remains identical.

### 2.2. URL Security Does Not Replace Method Security

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

This protects **HTTP requests** to the specified path. Yet the service method may also be invoked from:

- Another controller with a broader URL rule.
- A GraphQL resolver or another API endpoint.
- A message listener/consumer.
- A scheduled job.
- An application event handler.
- Another internal service.
- A new API version that accidentally omits the rule.

Thus, placing `@PreAuthorize` at the **service boundary** provides valuable defense in depth. However, if the service is called **without passing through the proxy**, the annotation may not run even though it is present in source code.

### 2.3. Method Security Does Not Replace Token Validation

When a controller is invoked after Bearer authentication, Spring Security holds an `Authentication` in `SecurityContext`. In a JWT Resource Server, this is usually a `JwtAuthenticationToken` containing a `Jwt` principal and authorities derived from scopes.

Method security consumes those already-verified authorities, such as `SCOPE_orders.read`. It must not:

- Manually Base64URL-decode a JWT and trust raw claims.
- Accept roles from unverified request headers.
- Skip issuer/audience/expiry validation.
- Treat `sub` as permission to access all records without checking tenant/ownership.

**`SecurityFilterChain` verifies credentials and gates requests; method security adds policy enforcement at the method boundary.** Both must be configured properly.

## 3. How Does a Spring AOP Proxy Work?

### 3.1. The Proxy Sits Between Caller and Target Bean

When method security is enabled, Spring can wrap a Spring-managed bean containing protected methods in an **AOP proxy**. Callers receive a reference to the proxy rather than invoking the target directly on every call.

~~~text
Controller / Other Bean
        |
        v
Spring AOP proxy
        |
        +--> Method security interceptor
        |         |
        |         +--> evaluates @PreAuthorize
        |
        v
Target service object
        |
        v
Business method body
~~~

If the policy denies access, the interceptor throws `AccessDeniedException` (or an appropriate subtype) before the business method runs.

### 3.2. External Calls Through the Proxy

Example:

~~~java
@RestController
public class OrdersController {

    private final OrderQueryService orders;

    public OrdersController(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    public OrderDto get(@PathVariable long id) {
        // orders is a Spring-injected service reference.
        return orders.load(id);
    }
}
~~~

Service:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto load(long id) {
        return repository.findOrderDto(id);
    }
}
~~~

When the controller is managed by Spring, `orders` is typically a reference to the AOP-proxied bean when method security applies. Calling `orders.load(id)` passes through the security interceptor before entering the method body.

### 3.3. Internal Calls Do Not Exit to the Proxy

Now add to the same service:

~~~java
@Service
public class OrderQueryService {

    public OrderDto loadWithoutGuard(long id) {
        // Call within the same instance; does not route back through the Spring proxy.
        return this.load(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto load(long id) {
        return repository.findOrderDto(id);
    }
}
~~~

If a controller happens to call `loadWithoutGuard(...)`, method security on `load(...)` can be bypassed via **self-invocation**.

Illustration:

~~~mermaid
flowchart TD
    A["Controller"] --> B["Spring AOP proxy of OrderQueryService"]
    B --> C["Target.loadWithoutGuard()"]
    C --> D["this.load() directly on target"]
    D --> E["Does not re-enter the proxy"]
    E --> F["@PreAuthorize guard on load() is not invoked"]
~~~

The takeaway is not "method security is always useless," but rather: **only join points passing through the proxy receive advice in proxy-based Spring AOP**. Once execution is inside the target object, `this` refers to the target itself, and calls on `this` do not automatically route back through the proxy.

## 4. Enabling Method Security Properly

### 4.1. Dependencies

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Method security requires appropriate Spring Security configuration. In modern Spring Boot applications, the standard declaration is:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

**Merely adding `@PreAuthorize` to a service without enabling method security does not guarantee the annotation will be enforced.**

### 4.2. Which Annotations Does `@EnableMethodSecurity` Support?

In modern Spring Security:

- `@PreAuthorize`: checks **before** invoking the method.
- `@PostAuthorize`: checks **after** the method runs, with access to the return value.
- `@PreFilter` / `@PostFilter`: filters collections/arrays/maps according to supported mechanisms; consider performance and business semantics.
- `@Secured`: typically must be enabled explicitly via `securedEnabled = true`.
- JSR-250 annotations like `@RolesAllowed`: typically must be enabled explicitly via `jsr250Enabled = true`.

Example:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
@Configuration
public class MethodSecurityConfig {
}
~~~

`prePostEnabled` is typically enabled by default in `@EnableMethodSecurity`. There is no need to enable every annotation family if your application does not use them.

### 4.3. Method Security and OAuth2 Resource Server Are Still Separate Configurations

Filter chain example:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

`oauth2ResourceServer(...jwt(...))` configures JWT Bearer authentication; `@EnableMethodSecurity` configures method interceptors. Enabling one **does not automatically replace** the other's responsibilities.

Illustrative `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Issuer and audience must match the Authorization Server and API contract. In particular, never use an OIDC ID Token in place of an access token simply because both are verifiable JWTs.

## 5. The Most Important Case: Self-Invocation

### 5.1. Example of an Authorization Bug in an Approval Workflow

Suppose an API has two methods:

~~~java
@Service
public class ApprovalService {

    public void submitOrder(long orderId) {
        // Other business step.
        this.approveOrder(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approveOrder(long orderId) {
        orderRepository.markApproved(orderId);
    }
}
~~~

A developer might expect **every call to `approveOrder`** to be gated by `SCOPE_orders.approve`. Yet when `submitOrder` calls it via `this`, the interceptor on `approveOrder` may not run.

If an HTTP endpoint allows scope `orders.submit` to invoke `submitOrder`, callers can inadvertently perform the `approve` action holding only `submit` rights. This is **privilege escalation via an internal call path**, not a JWT signature or `JwtGrantedAuthoritiesConverter` bug.

### 5.2. Why the Annotated Method Does Not Check Itself

Annotations are metadata. In proxy mode, Spring Security attaches interceptors **to calls passing through the proxy**, rather than injecting an `if` statement at the start of every Java method body in standard bytecode.

Distinguish:

~~~text
callerBean.approvalService.approveOrder(42)
    -> proxy
    -> @PreAuthorize
    -> target.approveOrder(42)
~~~

versus:

~~~text
target.submitOrder(42)
    -> this.approveOrder(42)
    -> target.approveOrder(42)
    -> bypasses the proxy
~~~

Even when the object comes from Spring's `BeanFactory` and a proxy genuinely exists, **self-invocation within the same target object is still not intercepted by the proxy** under the default AOP proxy model.

### 5.3. Writing `this` Is Not the Only Cause

All of the following internal call forms behave identically when executed on the same target:

~~~java
approveOrder(orderId);
this.approveOrder(orderId);
privateHelperThatCallsApprove(orderId);
~~~

What matters is whether the path to the protected method **passes through the AOP proxy**, not whether the `this` keyword is written explicitly.

A helper within the same class invoking the annotated method still risks a bypass. Calling a `@PreAuthorize` method from another method on the same bean is **not an external proxy call**.

## 6. Preferred Fix: Extract Policy-Guarded Methods into a Separate Bean

Instead of trying to force `this` back through the proxy, move actions with distinct policies into **a separate Spring-managed service** and inject that service into the caller.

### 6.1. Protected Approval Bean

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProtectedOrderApprovalService {

    private final OrderRepository orders;

    public ProtectedOrderApprovalService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        orders.markApproved(orderId);
    }
}
~~~

`OrderRepository` is an illustrative business interface implemented by the application.

### 6.2. Orchestration Bean Calling Through the Injected Reference

~~~java
package com.example.orders.service;

import org.springframework.stereotype.Service;

@Service
public class OrderWorkflowService {

    private final ProtectedOrderApprovalService approval;

    public OrderWorkflowService(
            ProtectedOrderApprovalService approval) {
        this.approval = approval;
    }

    public void submitAndApprove(long orderId) {
        // Submit step if permitted by the workflow's policy.
        approval.approve(orderId);
    }
}
~~~

When Spring injects `ProtectedOrderApprovalService`, the injected reference passes through the corresponding method-security proxy. Because the bean was split, `approval.approve(...)` from `OrderWorkflowService` is a **cross-bean call** that `@PreAuthorize` can intercept.

### 6.3. Splitting Beans Is Not Enough If Workflows Still Have Backdoors

If the workflow does not check submit permissions, or the repository exposes public methods to other callers, the system may still have another bypass path. Design so that:

- Every public application-service entry point enforces an appropriate policy.
- Sensitive actions have one protected boundary with no alternative "shortcut."
- Controllers do not call repositories directly to mutate sensitive state.
- Internal processes needing system privileges use dedicated policies/identities, **never bypassing** through unguarded methods.
- Tests cover all real call paths, not just direct calls to an annotated method.

Specifically, a **legitimate internal call** and an **accidental internal bypass** are not the same: an application may have trusted system jobs, but that trust must be expressed through an explicit authorization design, not by relying on annotations failing to fire.

## 7. Transactions and Method Security: `@Transactional` Also Uses Proxies

A method may both be security-protected and manage a transaction:

~~~java
@Service
public class ProtectedOrderApprovalService {

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Database update.
    }
}
~~~

In proxy mode, Spring's `@Transactional` also depends on calls passing through the proxy. Thus, self-invoking:

~~~java
this.approve(orderId);
~~~

can skip not only method security, but transaction advice as well.

This creates a double failure: **the authorization path is bypassed** and **the transaction boundary does not behave as expected**.

Do not rely on a fixed interceptor order between method security and transaction advice across all versions and configurations. When logic requires rollback/commit and pre-side-effect authorization, design explicit service and transaction boundaries and verify them with tests.

### 7.1. Why Is `@PostAuthorize` Dangerous on Write Methods?

`@PostAuthorize` evaluates authorization **after the method invocation** has executed, typically when policy inspects `returnObject`. Example:

~~~java
@PostAuthorize(
    "returnObject == null or returnObject.ownerId == authentication.name"
)
public OrderDto findOrder(long orderId) {
    return repository.findDtoById(orderId);
}
~~~

On a method with side effects:

~~~java
@PostAuthorize("hasAuthority('SCOPE_orders.approve')")
public void approve(long orderId) {
    repository.markApproved(orderId);
}
~~~

post-method authorization runs **after the data mutation has already occurred**. Never choose `@PostAuthorize` as the primary guard for writes on the assumption that rollbacks will automatically undo everything if denied; actual rollback depends on transaction boundaries and interceptor ordering.

Prefer `@PreAuthorize` for permissions required **before executing the operation**, combined with object-level permission checks at the right point inside the transaction. `@PostAuthorize` fits safe queries needing to compare permissions against returned results, while still weighing data-access and side-effect risks inside the method.

## 8. Cases Where Annotations Do Not Run Because the Object Is Not Spring-Managed

### 8.1. Instantiating with `new`

Wrong example:

~~~java
OrderApprovalService approval =
    new OrderApprovalService(repository);

approval.approve(orderId);
~~~

An object created with `new` **is not automatically proxied by Spring**. Even if the class carries `@Service` or the method carries `@PreAuthorize`, that manually created instance receives no Spring-managed interceptors.

Never treat an annotation on a class as a built-in Java runtime check attached to every instance.

### 8.2. Fix: Dependency Injection

~~~java
@RestController
public class ApprovalController {

    private final ProtectedOrderApprovalService approval;

    public ApprovalController(
            ProtectedOrderApprovalService approval) {
        this.approval = approval;
    }

    @PostMapping("/api/orders/{id}/approve")
    public void approve(@PathVariable long id) {
        approval.approve(id);
    }
}
~~~

Spring instantiates and injects the bean; security advice applies when the controller calls the method through the proxy.

### 8.3. Objects Created by Other Frameworks

If another library, custom scheduler, object mapper, or manual factory creates an object outside Spring's `BeanFactory`, that object does not automatically receive a Spring AOP proxy. Having `@Service` in the class source code is not enough.

Verify:

- Is the object truly a Spring-managed bean?
- Is the reference held by the caller a **proxy** or a raw target instance?
- Through which reference is the method invoked?
- Is the object's lifecycle managed by Spring?

Never "fix" this by hand-crafting a fake proxy or stuffing JWT validators into every method. Design consistent bean boundaries instead.

## 9. Methods That Are Hard or Impossible to Proxy in Spring AOP

### 9.1. `private` Methods

Spring AOP proxies cannot intercept calls to private methods in the standard way. Because private methods are neither exposed on proxy interfaces nor overridable by class-based proxies, annotations like the following do not create a reliable authorization boundary:

~~~java
@Service
public class OrderService {

    public void run(long orderId) {
        approveInternal(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    private void approveInternal(long orderId) {
        // Do not use annotations on private methods as primary protection.
    }
}
~~~

The proper fix is placing the policy on a **proxiable method called through a bean proxy** or extracting the action into a separate service.

### 9.2. `final` Methods and Class-Based Proxies

Spring AOP can use subclass-based class proxies (commonly referred to as CGLIB). A `final` method cannot be overridden in a subclass; therefore, a class-based proxy **cannot intercept that final method via overriding**.

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public final void approve(long orderId) {
        // A class-based proxy cannot override a final method.
    }
}
~~~

If the entire class is `final`, a subclass proxy cannot extend it under this mechanism.

**Important nuance:** do not oversimplify this into "no final method can ever be protected under any proxy mechanism." With a **JDK interface-based proxy**, calls are intercepted on the proxy interface method before delegating to the target, so final-method rules on the target differ from class-based subclass proxies. Still, the most predictable design uses public, non-final service methods on Spring-managed beans unless a specific proxy strategy is intentionally verified.

### 9.3. `static` Methods

Static methods are not invoked through bean instance proxies in the standard Spring AOP model. Never place `@PreAuthorize` on a static method and assume runtime protection.

### 9.4. Non-Public Methods

With **JDK interface proxies**, the interface exposes public interface methods. With class-based proxies, handling of package-private or protected methods varies by Spring version, visibility, and proxy mechanics. Thus, never generalize that all non-public methods are either always protected or always skipped.

For a predictable method-security contract, prefer:

- Public methods.
- Spring-managed beans.
- An explicit proxy strategy.
- Calls from another bean via an injected reference.
- Tests exercising the real security path.

### 9.5. Summary Table of Cases

| Case | Does Proxy-Based Method Security Apply? | What to Do |
|---|---|---|
| Public method on Spring bean, called by another bean via proxy | Typically yes | Enable `@EnableMethodSecurity` and use the right annotation |
| Public method called via `this.method()` inside the same target | Typically **no** | Split beans or design external proxy calls |
| Annotated private method | No reliable proxy interception | Move guard to a public boundary |
| Annotated static method | No instance proxy interception | Never use static methods as method-security boundaries |
| Final method under subclass/class-based proxy | Cannot override/intercept via that mechanism | Remove `final` or change architecture |
| Final target method with JDK interface proxy | Can be intercepted via the interface proxy | Verify proxy type and injection |
| Instance created with `new` | No Spring proxy | Use dependency injection / Spring bean |
| Called in constructor / target initialization | Do not expect method advice to run | Move business logic to an initialized bean |
| Object outside Spring container | No automatic proxy | Bring into Spring lifecycle or use another explicit boundary |
| Method security not enabled | No | Configure `@EnableMethodSecurity` |
| Annotation family not enabled | Not necessarily | Enable `securedEnabled`/`jsr250Enabled` when used |
| Call passes through proxy but lacks permission | Yes, and gets denied | Inspect policy / Authentication |

## 10. JDK Dynamic Proxies and Class-Based Proxies

### 10.1. JDK Interface Proxies

If a service implements an interface, Spring AOP can use a JDK dynamic proxy:

~~~java
public interface OrderApprovalOperations {
    void approve(long orderId);
}

@Service
public class OrderApprovalService implements OrderApprovalOperations {

    @Override
    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // ...
    }
}
~~~

Callers should depend on the interface:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderApprovalOperations approval;

    public OrderWorkflowService(OrderApprovalOperations approval) {
        this.approval = approval;
    }

    public void perform(long id) {
        approval.approve(id);
    }
}
~~~

JDK proxies expose interface methods, not methods declared solely on the concrete class. Injecting by concrete implementation type when the bean is actually a JDK proxy implementing only the interface can cause type or injection errors.

### 10.2. Class-Based Proxies

Class-based proxies can expose proxiable methods on the concrete class according to the proxy strategy. However, they still do not fix `this.method()` self-invocation, final methods, or private methods.

Spring Boot may configure `proxy-target-class` differently depending on version and auto-configuration; do not rely on general assumptions without checking your actual application.

### 10.3. Annotations on Interfaces vs. Implementations?

Spring Security method security supports placing annotations across methods, interfaces, and classes, resolving metadata across the type hierarchy according to its rules. When interfaces and implementations have overlapping annotations, or multiple interfaces carry differing policies, behavior can become surprising or cause configuration errors.

For maintainability:

- Choose one clear convention for where policies are declared.
- Avoid conflicting annotations across multiple interfaces.
- Do not assume switching proxy strategies preserves every metadata-resolution case identically.
- Test invocations through interface references and concrete beans just as the real application uses them.

**What never changes:** whether using JDK or class-based proxies, self-invocation on the target still bypasses the proxy.

## 11. Kotlin and Default `final`

In Kotlin, classes and methods are `final` by default unless marked `open` or opened via a compiler plugin.

Conceptual example:

~~~kotlin
@Service
class OrderApprovalService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    fun approve(orderId: Long) {
        // ...
    }
}
~~~

If a class-based proxy needs to subclass while the class or method remains final, interceptors may fail to apply properly. With Spring Boot Kotlin, the **`kotlin-spring`/`all-open` plugin** is typically used to open Spring-annotated classes and methods as configured.

Still, the plugin **does not solve self-invocation**: even when a method is proxiable, internal calls on `this` still bypass the proxy under default Spring AOP proxying.

In both Kotlin and Java, separating business services by responsibility and calling across beans is usually far clearer than relying on tricks to obtain the current proxy.

## 12. Constructors and `@PostConstruct`: When the Bean Is Not Ready Yet

### 12.1. Calls Inside Constructors

Example:

~~~java
@Service
public class OrderService {

    public OrderService() {
        initializeProtectedData();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.admin')")
    public void initializeProtectedData() {
        // Never rely on method security inside a constructor.
    }
}
~~~

A constructor initializes the **target object** before Spring completes the proxy lifecycle. Never rely on `@PreAuthorize` to guard calls triggered from a constructor.

### 12.2. `@PostConstruct` or Lifecycle Callbacks

Example:

~~~java
@PostConstruct
void init() {
    refreshPrivilegedState();
}
~~~

If a lifecycle callback calls an annotated method on the same bean during initialization, that is still an **internal call** and may run before the proxy/method-security boundary is ready. Never use method security to "authenticate" an application startup task that has no request principal.

If privileged bootstrapping genuinely exists, define a separate trusted startup workflow with explicit system permissions, without leaving any path from user endpoints to those tasks.

### 12.3. Scheduled Jobs and Application Events

A scheduled job or event listener can call a protected service method in two ways:

- Through a bean proxy: the method-security interceptor runs, so you must examine that thread's **`SecurityContext`**.
- Within the same target bean or without a principal: self-invocation or missing authentication can cause either a bypass or a denial.

Never reason "the job runs on the server so it automatically gets admin rights." If a batch job needs special privileges, design explicit system identities/authorizations and task boundaries isolated from untrusted requests.

## 13. Async Execution and `SecurityContext`

Spring Security Servlet typically stores `SecurityContext` on the thread handling the request. A service method annotated with `@Async` or a task submitted to another executor may find **authentication is not automatically propagated to the new thread**.

Example:

~~~java
@Service
public class OrderExportService {

    @Async
    @PreAuthorize("hasAuthority('SCOPE_orders.export')")
    public void export(long orderId) {
        // ...
    }
}
~~~

Here there are **two independent concerns**:

1. Whether `@Async` and `@PreAuthorize` are both invoked **through the proxy**.
2. Whether the caller's `SecurityContext` is **propagated** to wherever the method-security check actually runs.

Advice ordering, proxy layers, and which thread evaluates the check depend on configuration and versions. Never assume adding both annotations automatically preserves `Authentication` on worker threads.

Spring Security provides **security context propagation** utilities such as `DelegatingSecurityContextExecutor` and `DelegatingSecurityContextAsyncTaskExecutor`, which must be configured to fit your threat model—especially when tasks run after the HTTP request ends.

**Never use a shared global/static `SecurityContext` across all tasks.** If a task needs a durable identity, pass a purpose-built identity DTO/authorization decision, or run under a managed system principal. Never grant a task higher privileges just because request authentication is gone.

## 14. Cases Where Annotations Exist but Security Is Not Enabled

### 14.1. Missing `@EnableMethodSecurity`

Adding:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) {
    return repository.findDtoById(id);
}
~~~

does not ensure the annotation works if the application has not enabled method security or an equivalent configuration.

Confirm the configuration is picked up by component scanning/imports and that Spring actually registers method interceptors.

### 14.2. Using `@Secured` Without Enabling It

~~~java
@Secured("ROLE_ORDER_ADMIN")
public void deleteOrder(long id) {
    // ...
}
~~~

`@EnableMethodSecurity` has a `securedEnabled` attribute; in standard configurations it **does not enable `@Secured` automatically** unless explicitly set.

Likewise, JSR-250's `@RolesAllowed` requires `jsr250Enabled` to be enabled if using that annotation family.

### 14.3. Annotation on a Helper That Is Not a Spring Bean

An application-instantiated helper class:

~~~java
public class OrderPolicyHelper {

    @PreAuthorize("hasAuthority('SCOPE_orders.admin')")
    public void doAdminWork() {
        // ...
    }
}
~~~

is not AOP-intercepted merely because it carries an annotation. To protect it with Spring method security, place the method on a Spring-managed bean and call through the proxy, or use an authorization service/programmatic check suitable for non-Spring code.

### 14.4. Missing Expected Authority

If the proxy and annotation run and the policy denies access, that is **not a skipped annotation**. For instance, if a JWT has `scope: "orders.read"` while the rule requires `SCOPE_orders.write`, the proper outcome is typically **403**.

Distinguish clearly:

- **Annotation not intercepted:** the method runs despite lacking permissions.
- **Annotation ran and denied:** caller lacks authority; an exception/403 signals active protection.
- **Invalid JWT:** authentication filter returns 401 before controller/service.
- **Annotation runs on thread without context:** may deny or error; fix context propagation.

## 15. Accessing the JWT Principal in Method Security

### 15.1. Authorities After JWT Conversion

JWT:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Typically the Resource Server creates authority `SCOPE_orders.read`. `@PreAuthorize` uses:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) { ... }
~~~

If the application customizes `JwtAuthenticationConverter`, authority names may differ. Align policies with the converter; never relax a rule to `permitAll` when authorities are missing just to make requests succeed.

### 15.2. Using Identity/Tenant to Check Data Permissions

A request arrives:

~~~http
GET /api/orders/42
Authorization: Bearer <ACCESS_TOKEN>
~~~

and the token carries `tenant_id = tenant-42`. Scope `orders.read` does not prove order 42 belongs to that tenant or that the user has rights on that order.

Method security can consult a policy bean:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderPolicy.canRead(authentication, #orderId)"
)
public OrderDto loadOrder(long orderId) {
    return repository.findOrderDto(orderId);
}
~~~

Policy:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("orderPolicy")
public class OrderPolicy {

    private final OrderAccessRepository access;

    public OrderPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(Authentication auth, long orderId) {
        if (auth == null
                || !(auth.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        String subject = jwt.getSubject();
        Object tenantClaim = jwt.getClaim("tenant_id");

        if (subject == null || subject.isBlank()
                || !(tenantClaim instanceof String tenant)
                || tenant.isBlank()) {
            return false;
        }

        return access.canReadOrder(subject, tenant, orderId);
    }
}
~~~

`OrderAccessRepository` is an illustrative business component. It must check live permissions/owner/tenant against trusted data, not merely match a client-sent order ID.

**A method-level policy protecting data reads must be called through the proxy.** If another method in the same service calls `this.loadOrder(...)`, both the scope check and `orderPolicy.canRead(...)` inside the annotation can be bypassed.

### 15.3. Parameter Names in SpEL

The expression `#orderId` requires Spring Security to resolve method parameter names. In Java, depending on build setup, this may require the `-parameters` compiler option or a framework-supported parameter-naming annotation.

If the parameter name fails to resolve, the expression may receive null and deny or throw, producing hard-to-trace errors. Test method security against **real Spring beans**, not just compilation checks.

### 15.4. With Client Credentials Tokens

`sub` in an access token is not always a human user. With client credentials, `sub` may represent the client/service per profile. If a policy must identify a *real human user*, distinguish token types/grants and claims per contract.

Never turn a machine principal into the owner of a human user's order, or trust `email`/`preferred_username` as a secure identity key.

## 16. Ways to Resolve Self-Invocation: Priorities and Trade-Offs

### 16.1. Approach 1 — Split Beans (Recommended)

~~~text
Controller
  |
  v
OrderWorkflowService proxy/bean
  |
  v
ProtectedOrderApprovalService proxy
  |
  v
@PreAuthorize -> approve()
~~~

Advantages:

- Clear business responsibilities.
- Easy to test.
- Independent of specific proxy mechanics.
- Easy to align transaction and authorization boundaries.
- Reduces the risk of accidentally calling an unguarded helper.

Drawback: introduces a few extra classes/beans, requiring thoughtful domain boundaries.

### 16.2. Approach 2 — Move the Guard to the Public Entry Point

If a workflow must **always** be allowed or denied as a whole, you can protect the outer method:

~~~java
@Service
public class ApprovalWorkflowService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void submitAndApprove(long orderId) {
        prepare(orderId);
        approveInternal(orderId);
    }

    private void approveInternal(long orderId) {
        // Do not treat this private method as a separate boundary.
    }
}
~~~

This is valid **only if every entry point into the public workflow requires the exact same permission** and no other public method can reach `approveInternal` unguarded.

Advantage: simplicity. Risk: later adding another public entry point and forgetting to apply the permission. Therefore, tests and code reviews must trace all paths to sensitive side effects.

### 16.3. Approach 3 — Self-Injection or Calling Proxy via Context

Some projects use self-injection through an interface proxy or `AopContext.currentProxy()`. While these can route internal calls back through the proxy if configured properly, they typically:

- Increase coupling to AOP infrastructure.
- Risk circular dependencies or bean initialization issues.
- Make code harder to read and test.
- Can break if expose-proxy or proxy strategy settings change.
- Mask an unclear domain design.

Do not use this as your default fix for self-invocation. **Splitting beans or moving policies to clear entry points** is generally much easier to maintain.

### 16.4. Approach 4 — AspectJ Weaving

Spring AOP proxies are the default model. **AspectJ weaving** can technically intercept join points like self-invocation that proxies miss, provided the application is fully integrated and configured for it.

However, merely adding `@EnableMethodSecurity` does not enable weaving. You need the right dependencies, weaving setup, and compatibility with the method-security interceptors your application uses.

Due to operational and testing complexity, consider AspectJ only with a strong architectural justification. Never present it as a zero-configuration "annotation fix."

## 17. Testing to Prove Annotations Actually Execute

### 17.1. Do Not Unit Test with `new Service()` When Testing AOP

Example:

~~~java
OrderApprovalService service =
    new OrderApprovalService(repository);

service.approve(42);
~~~

This is a **unit test of the method body**, not a test of the Spring proxy. Seeing `@PreAuthorize` have no effect here does not mean Spring Security is broken; the object bypassed the Spring context.

Similarly, a Mockito mock replacing the entire service will not execute the real method's method security.

### 17.2. Testing Through a Spring-Managed Bean

Integration test example:

~~~java
package com.example.orders.security;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class OrderApprovalSecurityTest {

    @Autowired
    ProtectedOrderApprovalService approval;

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void deniesWhenApproveScopeMissing() {
        assertThatThrownBy(() -> approval.approve(42))
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

This is a conceptual test example: the project needs `spring-security-test` and appropriate test beans/repositories so the Spring context boots. When the policy works, the call must be denied **before the data-writing method runs**.

Test helper dependency:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 17.3. Testing Self-Invocation Paths

Test **actual public entry points**, not solely direct calls to the annotated method.

Initial anti-pattern example:

~~~java
public void submitAndApprove(long id) {
    this.approve(id);
}

@PreAuthorize("hasAuthority('SCOPE_orders.approve')")
public void approve(long id) {
    repository.markApproved(id);
}
~~~

If a test only calls `approval.approve(...)` through the proxy, it sees protection working. Yet the real endpoint calls `submitAndApprove(...)`, which can bypass it.

Therefore, tests must invoke `submitAndApprove(...)` in a context missing `SCOPE_orders.approve` and verify **no approval side effects occur**. If the database updates, an internal path is bypassing protection.

In the split-bean architecture, the equivalent test must show that the call into the injected `ProtectedOrderApprovalService` is denied.

### 17.4. Test Matrix

| Scenario | What to Verify |
|---|---|
| `@EnableMethodSecurity` not enabled | Catch missing configuration before reaching production |
| Calling annotated method via Spring bean proxy | Missing authority is denied |
| Calling same method via `this.method()` | Do not rely on annotation on inner method; test detects bypass |
| Object created with `new` | Do not treat annotation as a runtime guard |
| Private annotated method | Do not use as a security boundary |
| Final method under class-based proxy | Verify interceptability; avoid this pattern |
| JDK proxy and interface injection | Caller genuinely invokes via the interface proxy |
| Annotation present, auth lacks scope | Deny; typically 403 over HTTP |
| Bearer token with bad signature/issuer/audience | 401 before method invocation |
| Valid JWT, wrong tenant/owner | Deny per policy |
| Method called from scheduled/async thread | Right Authentication context or fail closed |
| `@PostAuthorize` on side-effecting method | Do not use as primary write guard |
| Another controller or message listener calls service | Still routes through protected boundary |

### 17.5. `@WithMockUser` Does Not Test the JWT Decoder

`@WithMockUser` creates a mock Authentication with authorities for method-security tests. It **does not** verify JWT signatures, issuers, audiences, Bearer headers, or `JwtAuthenticationConverter`.

To test the full Resource Server, add integration tests sending **real test JWTs** through the security filter chain with an appropriate issuer, test signing keys, or JWKS. Distinguish:

- **Invalid token** → authentication failure, typically 401.
- **Valid token with insufficient scope** → method/HTTP authorization failure, typically 403.
- **Annotation bypass** → method body runs despite missing authority; a security bug.

## 18. Diagnosing When Annotations Appear Not to Apply

### 18.1. First Question: Did the Request Pass Through a Spring Proxy?

A practical diagnostic sequence:

1. Is `@EnableMethodSecurity` enabled in a loaded Spring configuration?
2. Is the annotation family enabled (e.g., `@Secured`, JSR-250)?
3. Is the service a **Spring-managed bean**?
4. Did the caller obtain the bean via DI or instantiate it with `new`?
5. Was the method invoked from another bean via the proxy, or via `this.method()`?
6. Is the method `private`, `static`, `final`, or is the class `final`?
7. Is the proxy interface-based or class-based?
8. Was the method called while a constructor or `@PostConstruct` was running?
9. For async/scheduled tasks, does `SecurityContext` exist with the right principal?
10. Did the test genuinely exercise the guarded call path and check side effects?

Never "fix" the problem by escalating token scopes or removing `@PreAuthorize`.

### 18.2. Inspecting AOP Proxies in Development

Temporary diagnostic snippet:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(orderApprovalService);
boolean jdk = AopUtils.isJdkDynamicProxy(orderApprovalService);
boolean cglib = AopUtils.isCglibProxy(orderApprovalService);
~~~

These helpers only tell you whether **the current reference** is an AOP proxy and which kind; they do not by themselves prove a specific method was intercepted by the method-security advisor. Combine them with missing-authority tests and side-effect assertions.

Avoid dumping proxy internals or sensitive principals/claims into production logs unnecessarily.

### 18.3. Enabling Logs Locally / in Dev

`application.yml` can enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.aop: DEBUG
~~~

Log verbosity and contents depend on framework versions. Adjust logging deeper in test environments if needed, but never leave verbose logging enabled long-term in production without assessing the risk of leaking tokens, headers, claims, or request metadata.

### 18.4. Distinguishing "Blocked" from "Never Ran"

Suppose an endpoint returns 403 and the controller is never entered. The HTTP `AuthorizationFilter` may have rejected the request before the service; that **does not confirm method security ran**.

To prove the service guard works, test calling the service through its **Spring-managed proxy** in a context that has an `Authentication` lacking the authority, and confirm the method body did not execute. Also test any internal routes that production code can invoke.

### 18.5. A 200 Response Does Not Prove the Guard Executed

An authorized request returns 200 in both situations:

- Method security ran and allowed access.
- Method security was bypassed and business logic ran anyway.

Therefore, the most critical tests are **negative tests**: missing scopes, wrong tenants, and unauthorized callers must still be denied without producing side effects.

## 19. Putting It Together: Protecting Order Reads Without Self-Invocation Bypass

### 19.1. Unsafe Design

~~~java
@Service
public class OrderFacade {

    public OrderDto getOrder(long orderId) {
        // Even if caller is only authenticated, the policy below can be bypassed.
        return this.readProtected(orderId);
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto readProtected(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

If `getOrder` lacks an equivalent policy, requests from an endpoint requiring only `authenticated()` can reach `readProtected` without passing through advice.

### 19.2. Split-Bean Design with an Explicit Business Boundary

~~~java
@Service
public class ProtectedOrderQueryService {

    private final OrderRepository repository;

    public ProtectedOrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto load(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

Facade:

~~~java
@Service
public class OrderFacade {

    private final ProtectedOrderQueryService query;

    public OrderFacade(ProtectedOrderQueryService query) {
        this.query = query;
    }

    public OrderDto getOrder(long orderId) {
        return query.load(orderId);
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrderFacade facade;

    public OrdersController(OrderFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/{id}")
    public OrderDto get(@PathVariable long id) {
        return facade.getOrder(id);
    }
}
~~~

In a real system, each class needs its respective imports (`Service`, `PreAuthorize`, `RestController`, `RequestMapping`, `GetMapping`, `PathVariable`); `OrderDto` and `OrderRepository` must be defined by the application.

Call path:

~~~text
HTTP Controller
    |
    v
OrderFacade bean
    |
    v
ProtectedOrderQueryService proxy
    |
    +-- @PreAuthorize:
    |      SCOPE_orders.read
    |      AND orderPolicy.canRead(...)
    |
    v
Target load(orderId)
    |
    v
Repository
~~~

Regardless of what other permissions a controller has, the query service returns no data when scope is missing or the order policy denies, **provided the call genuinely traverses the proxy** and no backdoor accesses the sensitive repository directly.

### 19.3. Note on Data Leakage and TOCTOU

Even with `@PreAuthorize`, a policy checking owner/tenant followed by the service loading the record in another transaction can exhibit **time-of-check/time-of-use** if ownership changes concurrently. For sensitive operations, constrain queries by tenant/owner within the same transaction and re-verify conditions at the right moment in the database/service.

Method security is an **authorization boundary**, not a substitute for data policies, isolation, and transaction correctness.

## 20. Misconceptions to Avoid

### "Having the annotation on a method means every call is checked"

False in proxy mode. Calls must pass through the AOP proxy or be handled by another fully configured interception mechanism.

### "Because the service is Spring-injected, self-invocation is intercepted too"

False. The bean has a proxy, yet `this.method()` runs on the target directly without exiting to the proxy.

### "`@PreAuthorize` on a private method protects private logic"

No. Private methods are not reliable pointcuts for Spring AOP proxies.

### "Using class-based proxies solves self-invocation"

No. CGLIB/class-based proxies share the self-invocation limitation under the standard Spring AOP proxy model.

### "Kotlin final methods are always intercepted anyway"

Never assume that. Class-based proxies require subclassing/overriding; check your `all-open`/`kotlin-spring` setup and test in practice.

### "Method security runs automatically on objects created with `new`"

No. Instances outside Spring's `BeanFactory` do not automatically receive proxies.

### "`@PostAuthorize` protects all write operations before side effects"

No. It decides after method invocation, so it is not the primary guard for actions that must be blocked before changing state.

### "Method security can replace issuer/audience validation"

No. JWTs must be verified before trusting claims or authorities.

### "Having the scope means owning every order"

No. Tenant, ownership/ACL, and business entitlements must still be checked.

### "Testing the method directly with `new` tests security"

No. Test through the Spring-managed proxy with negative cases.

### "If the HTTP rule returns 403, method security definitely works"

No. The HTTP filter may have denied the call before the service was reached; test method guards separately.

## 21. Key Takeaways

- `@EnableMethodSecurity` activates method-security infrastructure; annotations in source code **do not run automatically** if configuration does not enable them.
- In **Spring AOP proxy mode**, calls are guarded when flowing **from caller through proxy to target method**. `this.method()` on the same target bean **does not re-enter the proxy**.
- Watch out for: self-invocation, `new`-instantiated objects, private/static methods, final methods under class-based proxies, constructors, lifecycle callbacks, async threads, mixed proxy types, and unenabled annotation families.
- **Preferred solution** for business actions with distinct policies: **extract protected methods into another Spring bean** and invoke via an injected reference, or guard a single public entry point covering the whole workflow.
- `@PreAuthorize` fits checking permissions **before side effects**; `@PostAuthorize` has post-invocation semantics and should not be used casually for writes.
- HTTP security and method security complement each other. Bearer tokens must pass issuer, audience, signature, time, and token-profile checks; method security consumes trusted Authentication/authorities and must still check tenant/ownership.
- Only testing **real production paths** and **negative cases** catches bypassed annotations; testing only authorized callers or testing with `new` is insufficient.
- Never work around bypasses by widening scopes, dropping validation, or letting services trust client-declared inputs.

### References

- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Framework Reference — Spring AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Security Reference — Servlet Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security API — EnableMethodSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Security API — PreAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Framework API — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
