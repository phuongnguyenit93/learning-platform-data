# Propagating Identity, Trace IDs, and Tenants via Reactor Context

In a Spring WebFlux application combined with Spring Data R2DBC, a request can pass through multiple asynchronous layers: WebFilters, controllers, services, repositories, WebClient, and result-handling callbacks. These layers may execute on different threads while still needing to share request-scoped metadata such as the authenticated user, current tenant, correlation ID, or trace context.

Reactor Context provides a subscription-scoped data region to carry this information throughout a reactive pipeline. It solves context propagation in the reactive model, where you cannot rely by default on `ThreadLocal` as in imperative applications. Spring Security WebFlux also uses Reactor Context to store `SecurityContext`; Spring Data R2DBC can read the auditor from the reactive security context; and applications can add tenant IDs or correlation IDs for lower layers to consume.

Reactor Context is solely a mechanism for passing data within a pipeline. It does not authenticate users, automatically secure tenant queries, automatically attach trace headers, or configure database sessions. Each piece of metadata still needs a trusted source, validation rules, and clear usage points.

## 1. Why Do Reactive Applications Need Reactor Context?

In synchronous applications, a request usually runs on a single thread for most of its lifecycle. Some frameworks use `ThreadLocal` to store the security principal, MDC logging values, or transaction metadata. When moving to WebFlux, a request may resume on a different thread after I/O completes. A single thread may also serve many different requests sequentially.

For example:

```text
Request A: Thread-1 -> Thread-4 -> Thread-2
Request B: Thread-2 -> Thread-3 -> Thread-1
```

If a tenant ID or user ID is stored in a `ThreadLocal` and read from an arbitrary callback, the code might miss the value or accidentally read a leftover value from another task if cleanup is imprecise.

Reactor Context is attached to the subscription rather than a thread:

```text
Request A subscription
  Context: user=1008, tenant=acme, correlation=abc...
       |
       +--> WebFilter
       +--> Controller
       +--> Service
       +--> Repository

Request B subscription
  Context: user=2042, tenant=globex, correlation=xyz...
       |
       +--> WebFilter
       +--> Controller
       +--> Service
       +--> Repository
```

Two requests maintain separate contexts even when their callbacks execute on the same thread at different moments.

### 1.1. Types of Data Commonly Propagated via Context

- **Identity:** user ID, principal, or authenticated actor.
- **Tenant:** verified and authorized tenant ID.
- **Correlation ID:** identifier used to correlate logs across layers within the same request.
- **Trace context:** trace ID, span ID, and sampling information managed by the tracing system.
- **Request metadata:** locale, channel, or other small immutable subscription-scoped attributes.

Do not place entire requests, large entities, connections, mutable maps, or unnecessary sensitive data into the Context. Context is meant for small, stable, well-scoped metadata.

## 2. Reactor Context and Core APIs

Reactor Context is an immutable key-value structure attached to a subscriber. When adding or modifying a value, Reactor produces a new Context; upstream operators see the Context provided by the downstream subscriber.

Commonly used APIs:

| API | Purpose |
|---|---|
| `contextWrite(...)` | Writes or transforms the Context for the upstream portion of a publisher |
| `deferContextual(...)` | Reads `ContextView` when subscription occurs |
| `ContextView` | Reads context values without mutating them |
| `Context.of(...)` | Creates an initial Context with key-value pairs |
| `contextRead()` | Reads the current Context in certain advanced operators |

### 2.1. Writing Values with contextWrite

```java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just("tenant=" + context.get("tenantId")))
    .contextWrite(context -> context.put("tenantId", "acme"));
```

Upon subscription, `deferContextual` reads the `tenantId` provided by `contextWrite`. Context is written lower in the pipeline yet takes effect for operators upstream of that position.

You can use the simple overload:

```java
Mono<String> pipeline = Mono.just("loaded")
        .contextWrite(Context.of("correlationId", "req-123"));
```

In application code, use clearly named keys and constants instead of scattered string literals.

### 2.2. Reading with deferContextual

```java
Mono<OrderView> findOrder(Long orderId) {
    return Mono.deferContextual(context -> {
        String tenantId = context.get("tenantId");
        return orderRepository.findByTenantIdAndId(tenantId, orderId)
                .map(OrderView::fromEntity);
    });
}
```

`deferContextual` defers reading the Context until subscription time. Do not read Context when assembling the publisher because the subscription context may not exist yet.

If a key might be absent, use `hasKey` or `getOrEmpty` and handle missing values explicitly:

```java
return Mono.deferContextual(context -> {
    if (!context.hasKey(TENANT_ID)) {
        return Mono.error(new MissingTenantContextException());
    }

    String tenantId = context.get(TENANT_ID);
    return orderRepository.findByTenantIdAndId(tenantId, orderId);
});
```

For tenant-scoped data, a missing tenant should usually fail explicitly. Never silently fall back to a default tenant because it can lead to accessing data in the wrong scope.

### 2.3. ContextView Is Read-Only

`ContextView` exposes read access to keys and values. It does not offer mutation methods. To add values, use `contextWrite` at the appropriate point.

### 2.4. Context Is Subscription-Scoped

Context values apply only to the subscription they are attached to. Two subscriptions to the same publisher can have different Contexts:

```java
Mono<String> currentTenant = Mono.deferContextual(ctx ->
        Mono.just(ctx.get(TENANT_ID)));

Mono<String> acme = currentTenant
        .contextWrite(ctx -> ctx.put(TENANT_ID, "acme"));

Mono<String> globex = currentTenant
        .contextWrite(ctx -> ctx.put(TENANT_ID, "globex"));
```

Never store a request's Context in a singleton field or static variable to share across requests. Context belongs to a subscription, not shared bean state.

## 3. Understanding the Direction of contextWrite

A common source of confusion is that `contextWrite` takes effect in the opposite direction of top-down code reading. It writes Context for operators upstream—those appearing before `contextWrite` in the publisher chain.

Example:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.get("key")))
        .contextWrite(ctx -> ctx.put("key", "value"));
```

`deferContextual` is upstream of `contextWrite`, so it reads `value`.

Conversely:

```java
Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("key", "missing")))
        .contextWrite(ctx -> ctx.put("key", "value"))
        .flatMap(value -> Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("key", "missing"))));
```

The `flatMap` operator downstream of `contextWrite` does not automatically see the value `contextWrite` supplied to the upstream operators before it. Context flows from subscriber to upstream according to operator position.

When analyzing a complex pipeline, identify which publisher is upstream, which operators read Context, and where `contextWrite` sits. Breaking pipelines into small methods makes context boundaries clearer.

## 4. Defining Consistent Context Keys and Data Types

Avoid scattering arbitrary strings like `"tenant"`, `"user"`, or `"trace"` across layers. Define keys centrally:

```java
public final class RequestContextKeys {

    public static final String CORRELATION_ID = "app.correlationId";
    public static final String TENANT_ID = "app.tenantId";
    public static final String ACTOR_ID = "app.actorId";

    private RequestContextKeys() {
    }
}
```

You can create a record to group validated metadata:

```java
public record RequestMetadata(
        String correlationId,
        String tenantId,
        Long actorId
) {
}
```

Then store a single immutable object:

```java
return chain.filter(exchange)
        .contextWrite(context -> context.put(REQUEST_METADATA, metadata));
```

A grouped metadata object avoids fragmented keys, though you should not dump everything into one global context object. Include only fields genuinely needed by downstream reactive layers.

### 4.1. Choosing Key Types

Reactor Context allows any object as a key. You can use namespaced `String` constants or dedicated key objects. Using dedicated key objects prevents collisions with other libraries; `String` keys are convenient for observability and integration. What matters is keeping keys stable and centrally managed.

### 4.2. Never Store Mutable Objects

An immutable Context does not make values inside it immutable. Storing a `HashMap` or mutable object allows multiple operators to reference and mutate it concurrently. Prefer records, immutable value objects, boxed primitives, or Strings.

## 5. Propagating Correlation ID via WebFilter

A correlation ID links logs for a single request across WebFilters, controllers, services, and repositories. It can be accepted from a trusted header or generated at the HTTP boundary.

### 5.1. Generating or Validating Correlation IDs

Example `WebFilter`:

```java
@Component
public class CorrelationIdWebFilter implements WebFilter {

    private static final String HEADER = "X-Correlation-Id";
    private static final String CONTEXT_KEY = "app.correlationId";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String supplied = exchange.getRequest()
                .getHeaders()
                .getFirst(HEADER);

        String correlationId = isSafe(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders()
                .set(HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(CONTEXT_KEY, correlationId));
    }

    private boolean isSafe(String value) {
        return value != null
                && value.length() <= 100
                && value.matches("[A-Za-z0-9._-]+");
    }
}
```

This filter:

1. Reads the `X-Correlation-Id` header if present.
2. Validates its length and allowed character set.
3. Generates a UUID if the header is missing or invalid.
4. Returns the ID in the response header.
5. Writes the ID into the Reactor Context for the downstream pipeline.

If requests arrive from a trusted proxy or gateway, you can accept the gateway-issued correlation ID after verifying the source. Do not blindly trust arbitrary headers from the Internet if the system uses that ID to link events or access sensitive logs.

### 5.2. Reading the Correlation ID in a Service

```java
public Mono<OrderView> getOrder(Long id) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get(CORRELATION_ID);
        log.debug("Loading order id={}, correlationId={}", id, correlationId);

        return orderRepository.findById(id)
                .map(OrderView::fromEntity);
    });
}
```

If the service may be called outside HTTP—such as from a scheduler or message consumer—the key might be absent. Use `getOrEmpty`/`hasKey` or require callers to populate metadata per the service contract. Never assume every subscription originates from a `WebFilter`.

### 5.3. Do Not Use Correlation IDs Instead of Trace IDs

A correlation ID is an application-managed identifier for correlating logs or requests. A trace ID belongs to distributed tracing, carrying spans, parent-child relationships, and sampling metadata. A single request may have its own correlation ID while multiple services participate in a single trace.

If using Micrometer Tracing or OpenTelemetry instrumentation, let the tracing system manage trace/span contexts and propagate standard trace headers. You can record a correlation ID alongside for business diagnostics, but never fabricate a `traceId` and overwrite the trace context managed by the tracing framework.

## 6. User Identity and Spring Security WebFlux

Spring Security WebFlux stores `SecurityContext` in the Reactor Context. Applications should read identity via `ReactiveSecurityContextHolder` rather than the `ThreadLocal`-based `SecurityContextHolder`.

### 6.1. Reading Authentication in a Service

```java
public Mono<CustomerProfile> currentProfile() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .filter(AppPrincipal.class::isInstance)
            .cast(AppPrincipal.class)
            .flatMap(principal -> customerRepository
                    .findById(principal.userId())
                    .map(CustomerProfile::fromEntity));
}
```

Example assuming the application defines a custom principal:

```java
public record AppPrincipal(
        Long userId,
        String username,
        String tenantId
) {
}
```

The actual principal could be `UserDetails`, a JWT principal, or a custom type. Convert safely from the type produced by your security configuration rather than casting blindly.

### 6.2. Distinguishing Authenticated vs. Anonymous Users

Some `Authentication` objects representing anonymous users may still return `isAuthenticated() == true`. If an endpoint requires a real user, exclude `AnonymousAuthenticationToken` or check the principal according to security policy. Do not rely solely on `isAuthenticated()`.

### 6.3. Do Not Copy the Security Context Arbitrarily

Spring Security already manages `SecurityContext` via Reactor Context. Usually, reading it via `ReactiveSecurityContextHolder` is sufficient. If you want to place an actor ID into a separate request metadata object, do so only after authentication and copy only the minimal required value.

Never take a `userId` key from a request header and treat it as an authenticated identity. Headers or bodies can be forged by clients. Identity must come from authentication verified by Spring Security.

## 7. Propagating Tenant Identity Safely

In multi-tenant applications, the tenant ID defines the data scope a request is permitted to access. Passing the tenant via Context helps lower layers access the same tenant, but Context is not an authorization mechanism. The tenant value must come from an authenticated identity or verified routing mechanism and be authorized before querying.

### 7.1. Extracting Tenant from an Authenticated Principal

```java
public Mono<OrderView> findOrder(Long orderId) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .flatMap(principal -> orderQueryService.findForTenant(
                    principal.tenantId(), orderId));
}
```

This passes the tenant explicitly via method parameters. In smaller codebases, explicit parameters can be clearer and easier to audit than putting every value in Context.

### 7.2. Writing Tenant into Context When Many Layers Need It

If multiple downstream services need the same tenant and passing it through many signatures is noisy, write the tenant into Context after retrieving it from the principal:

```java
public Mono<OrderView> findOrder(Long orderId) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .flatMap(principal -> orderQueryService.find(orderId)
                    .contextWrite(context -> context.put(
                            TENANT_ID, principal.tenantId())));
}
```

`contextWrite` on the inner publisher provides the tenant to upstream operators inside `orderQueryService.find(...)`. The query service method can read it:

```java
public Mono<OrderView> find(Long orderId) {
    return Mono.deferContextual(context -> {
        String tenantId = context.get(TENANT_ID);
        return orderRepository.findByTenantIdAndId(tenantId, orderId)
                .map(OrderView::fromEntity);
    });
}
```

Ensure no call path enters `find` without a tenant. If the service is invoked from multiple entry points, either require an explicit tenant parameter or validate the Context and fail when missing.

### 7.3. Never Trust Tenant Headers Without Verification

A client might send `X-Tenant-Id: other-company`. If the system reads this header and queries data without verifying membership/permissions, it creates a cross-tenant authorization vulnerability.

If a header selects one tenant among those a user is permitted to access, you must:

1. Authenticate the user.
2. Read the requested tenant.
3. Verify the user has access to that tenant.
4. Only after verification succeeds, write the tenant into Context or pass it to queries.

If a user belongs to a single fixed tenant, taking the tenant from the authenticated principal or verified claim is simpler.

### 7.4. Tenant Must Appear in Query Predicates

Reactor Context does not automatically append `WHERE tenant_id = ...`. Repositories/queries must still constrain by tenant:

```java
Flux<OrderEntity> findByTenantIdAndStatus(
        String tenantId, String status);
```

Or in SQL:

```sql
SELECT id, order_code, status
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
```

Never use `findById(id)` for tenant-scoped data when ID alone does not establish access rights. Use `findByTenantIdAndId(tenantId, id)` to enforce scoping directly in the database.

## 8. Integrating Tenants with PostgreSQL Row-Level Security

Some systems use Row-Level Security (RLS) so the database enforces per-tenant policies. In PostgreSQL, the application can store the tenant in a transaction-local setting, and the policy reads that setting.

Illustrative policy:

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON orders
USING (tenant_id = current_setting('app.tenant_id', true));
```

Within a transaction, the tenant can be set via:

```sql
SELECT set_config('app.tenant_id', :tenantId, true);
```

The third argument `true` scopes the setting to the local transaction in PostgreSQL. This is critical when connections are reused through a pool.

### 8.1. Setting the Parameter in the Same Transaction

Example showing consumption of the `SELECT set_config` result row:

```java
@Transactional(readOnly = true)
public Flux<OrderEntity> findOrdersForTenant(String tenantId) {
    return databaseClient.sql(
                    "SELECT set_config('app.tenant_id', :tenantId, true)")
            .bind("tenantId", tenantId)
            .map((row, metadata) -> row.get(0, String.class))
            .one()
            .thenMany(orderRepository.findAll());
}
```

In a real application, the tenant should come from an authenticated context rather than an arbitrary controller parameter. You can read the tenant from Reactor Context inside the method and run the corresponding transaction.

### 8.2. Preventing Session State Leakage Across Connection Pools

Never set the tenant via session-scoped `SET app.tenant_id = ...` and return the connection to the pool without resetting it. The next connection lease could serve a request for a different tenant and inherit the stale session setting.

Transaction-local settings paired with transaction boundaries reduce state-leakage risk. Still, test both rollback and commit paths and verify the driver/pool returns connections in a clean state. RLS is a defense-in-depth layer; application-level authorization and policy checks against spoofed tenant contexts are still required.

## 9. Propagating Correlation ID and Tenant to WebClient

When a Service calls a downstream HTTP service, the correlation ID can be passed via headers to link logs across services. Context can be read directly within the pipeline:

```java
public Mono<ProductInfo> loadProduct(String productCode) {
    return Mono.deferContextual(context ->
            webClient.get()
                    .uri("/products/{code}", productCode)
                    .header("X-Correlation-Id",
                            context.getOrDefault(CORRELATION_ID, "unknown"))
                    .retrieve()
                    .bodyToMono(ProductInfo.class));
}
```

Do not send tenant or user IDs to external services unless required by contract and security policy. When needed, send a signed claim/token or use proper service-to-service identity mechanisms. Never treat a correlation ID header as authentication proof.

### 9.1. Using Filters with WebClient

If multiple requests share header-injection logic, you can write an `ExchangeFilterFunction` or configure observation/tracing instrumentation. However, the filter must read Context at subscription time and never store a previous request's metadata in a singleton field.

### 9.2. Distributed Tracing

With Micrometer Tracing/OpenTelemetry, instrumentation usually propagates trace context across `WebClient` and supported transports automatically. Use the tracing bridge and observation instrumentation matching your Spring Boot version. Avoid manually setting `traceparent` to a correlation ID string, because `traceparent` has its own format and semantics.

## 10. Logging and MDC

Many logging frameworks use `ThreadLocal`-based MDC. Reactor Context does not automatically sync all values into MDC across every version and configuration.

### 10.1. Reading Context to Log in the Pipeline

You can use `deferContextual` or `doOnEach` to extract metadata at signal time:

```java
return Mono.deferContextual(context -> {
    String correlationId = context.getOrDefault(CORRELATION_ID, "-");
    log.info("Processing order, correlationId={}", correlationId);
    return orderRepository.findById(orderId);
});
```

This is explicit and does not depend on MDC. If you want the correlation ID to appear automatically in every log line, configure context propagation/MDC bridging.

### 10.2. Micrometer Context Propagation

The Spring ecosystem can integrate Micrometer Context Propagation to capture and restore specific `ThreadLocal` values across reactive and imperative boundaries. With Reactor, automatic context propagation can be enabled via the appropriate hook in your library version, such as `Hooks.enableAutomaticContextPropagation()`.

Enable this only after understanding its impact and configuring the corresponding `ThreadLocalAccessor`. Do not assume every MDC key or logging library propagates automatically merely from adding a dependency. Check Spring Boot/Micrometer documentation for your project version.

### 10.3. Avoid Manual MDC Management Without Cleanup

If you set MDC manually inside callbacks, you must clear or restore values along every termination path: complete, error, and cancel. Threads are pooled and reused; without cleanup, logs for subsequent requests may carry the previous request's correlation ID.

For new applications, prefer properly configured Micrometer Tracing/Context Propagation or explicit metadata logging from Context over scattered manual `ThreadLocal` bridges.

## 11. Reactor Context and R2DBC Auditing

Spring Data auditing in R2DBC uses `ReactiveAuditorAware<T>` to obtain the current actor. If the application uses Spring Security WebFlux, the provider can read the principal from `ReactiveSecurityContextHolder`, which is backed by Reactor Context.

Example:

```java
@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .cast(AppPrincipal.class)
            .map(AppPrincipal::userId);
}
```

With an entity:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        String orderCode,
        @CreatedBy @Column("created_by") Long createdBy,
        @LastModifiedBy @Column("last_modified_by") Long lastModifiedBy
) {
}
```

When auditing is enabled with `@EnableR2dbcAuditing`, callbacks can retrieve the auditor from the reactive context when saving entities. You do not need to manually read and assign the user ID on every entity when auditing is configured properly.

### 11.1. Background Tasks Without SecurityContext

Schedulers, message consumers, or batch jobs may run outside the HTTP security chain. `ReactiveSecurityContextHolder.getContext()` may then complete empty. Define an explicit policy:

- Allow a nullable auditor if schema and business rules permit.
- Assign a system actor explicitly within background task flows.
- Require an authenticated service actor if the job acts on behalf of another system.

Never default to a system user for every request missing a security context, as unauthenticated requests could be recorded as legitimate system actions.

## 12. Context Propagation Across Operators and Schedulers

Reactor Context is designed to propagate across standard Reactor operators. Switching schedulers with `publishOn` or `subscribeOn` does not drop the subscription's Context:

```java
Mono.deferContextual(context ->
        Mono.just(context.get(CORRELATION_ID)))
    .publishOn(Schedulers.parallel())
    .contextWrite(context -> context.put(CORRELATION_ID, "req-123"));
```

However, Context does not automatically follow execution mechanisms outside Reactor.

### 12.1. Nested Subscribe Breaks the Pipeline

Do not call `subscribe()` inside a Service:

```java
public Mono<Void> process(Long id) {
    repository.findById(id)
            .doOnNext(entity -> auditService.write(entity).subscribe())
            .then();
    return Mono.empty();
}
```

A nested subscription is detached from the pipeline controlled by the caller. Context, transactions, cancellation, and error handling may not propagate as expected.

Chain publishers with `flatMap` or `then` instead:

```java
public Mono<Void> process(Long id) {
    return repository.findById(id)
            .flatMap(auditService::write)
            .then();
}
```

### 12.2. Manual Threads or Executors

If code invokes `new Thread`, `ExecutorService.submit`, or library callbacks that do not integrate with Reactor, Context will not appear on that thread automatically. Use context-aware schedulers/adapters or pass metadata explicitly via parameters.

### 12.3. Imperative Callbacks

When calling imperative libraries that depend on `ThreadLocal`, bridge context intentionally. Micrometer Context Propagation provides abstractions to capture and restore context; exact setup depends on the library and version. Never rely on the current thread happening to match the previous thread.

## 13. Context in Message Consumers and Background Tasks

Not every subscription originates from HTTP. Kafka/RabbitMQ consumers, schedulers, and batch jobs may also need correlation IDs, tenants, or actors.

Example when processing a message carrying verified metadata:

```java
Mono<Void> handle(OrderCreatedMessage message) {
    return orderProcessor.process(message)
            .contextWrite(context -> context
                    .put(CORRELATION_ID, message.correlationId())
                    .put(TENANT_ID, message.tenantId())
                    .put(ACTOR_ID, SYSTEM_ACTOR_ID));
}
```

This snippet assumes the message comes from a trusted source and the consumer verifies tenant/actor per contract. Never trust a tenant ID solely because it appears in a message payload; message brokers also require authentication, authorization, and producer verification.

For scheduled jobs, generate a fresh correlation ID per run or use a stable execution ID. Write Context at the subscription entry point so all downstream publishers share the metadata.

## 14. Context and R2DBC Transactions

Spring manages reactive transactions via Reactor Context. `TransactionalOperator` or `@Transactional` attaches a transaction context to the managed publisher; downstream R2DBC operations join the transaction when using the proper transaction manager and the same pipeline.

This means Context can carry both application metadata and framework-managed transaction state. Never modify or overwrite Spring/Reactor internal keys. Use a dedicated namespace for application keys.

Example:

```java
@Transactional
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

When the caller attaches correlation or tenant context:

```java
return orderService.createOrder(order)
        .contextWrite(context -> context
                .put(CORRELATION_ID, correlationId)
                .put(TENANT_ID, tenantId));
```

Operations inside the transactional pipeline can read the metadata and share the same transaction context. However, tenant context does not automatically configure the database session or RLS; the application must still add query predicates or set transaction-local database settings as shown earlier.

### 14.1. Never Subscribe Manually Inside a Transaction

Creating a new subscription via `subscribe()` or calling `block()` can cause operations to run outside the original publisher's transaction context. Always return and compose publishers so the transaction manager controls the lifecycle.

### 14.2. Never Hold Transactions Across Non-Database Work

Context can stay alive throughout the whole pipeline, but transactions should not span HTTP calls, waiting on messages, or heavy CPU processing. Holding connections open reduces throughput for other requests.

## 15. Security and Privacy When Using Context

Context is subscription-internal metadata, but it does not automatically make values inside it safe. Follow these principles:

- Only write user/tenant after authentication and authorization.
- Never treat arbitrary headers as trusted actor IDs or tenant IDs.
- Never store tokens, passwords, session secrets, or raw credentials in Context.
- Never log the entire Context; it may contain internal state or sensitive data.
- Never share mutable objects across requests.
- Never store tenant context in static fields or singleton state.
- Enforce tenant checks in queries or database policies, not merely by checking whether Context has a value.
- Use correlation IDs for tracing logs, never as authentication tokens.

If a method requires a tenant and Context lacks one, fail closed with an explicit error. Never fall back to a default tenant or omit the tenant predicate.

## 16. Testing Reactor Context

Context is part of reactive pipeline behavior, so tests should subscribe with an appropriate Context and verify that upstream/downstream operators read the expected values.

### 16.1. Testing contextWrite and deferContextual

```java
@Test
void readsTenantFromContext() {
    Mono<String> tenant = Mono.deferContextual(context ->
            Mono.just(context.get(TENANT_ID)));

    StepVerifier.create(tenant.contextWrite(context ->
                    context.put(TENANT_ID, "acme")))
            .expectNext("acme")
            .verifyComplete();
}
```

### 16.2. Testing Two Subscriptions Without Tenant Leakage

```java
Mono<String> tenant = Mono.deferContextual(context ->
        Mono.just(context.get(TENANT_ID)));

StepVerifier.create(tenant.contextWrite(ctx -> ctx.put(TENANT_ID, "acme")))
        .expectNext("acme")
        .verifyComplete();

StepVerifier.create(tenant.contextWrite(ctx -> ctx.put(TENANT_ID, "globex")))
        .expectNext("globex")
        .verifyComplete();
```

This test confirms each subscription maintains its own context. For tenant-scoped services, verify the repository receives the correct tenant for each simulated request.

### 16.3. Testing Missing Tenant

```java
StepVerifier.create(orderQueryService.find(10L))
        .expectError(MissingTenantContextException.class)
        .verify();
```

This is a critical test to ensure the system never silently queries without a tenant predicate.

### 16.4. Testing Spring Security Context

You can create a mock `SecurityContext` and attach it to a pipeline using `ReactiveSecurityContextHolder.withSecurityContext(...)`. Verify that auditors or services read the right principal, and also test anonymous/empty context cases.

```java
StepVerifier.create(ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication)))
        .expectNext("alice")
        .verifyComplete();
```

### 16.5. Testing WebFilter

Use `WebTestClient` to verify:

- Requests without a correlation header receive a new ID.
- Requests with a valid header preserve the ID per policy.
- Invalid headers are replaced with a new ID.
- Responses return the correlation header.
- Downstream services read the same ID from Reactor Context.

### 16.6. Testing Context Across WebClient and Transactions

For downstream HTTP calls, verify correlation headers are sent properly and tracing instrumentation generates trace headers as configured. For R2DBC, integration tests must verify that tenant predicates or RLS settings actually apply on the same transaction/connection, not just that Context contains the key.

## 17. Common Mistakes

### Using ThreadLocal to Store Request Metadata

Threads can switch inside a reactive pipeline. Use Reactor Context or a properly configured context propagation mechanism.

### Reading Context Before Subscription

Context belongs to a subscription. Use `deferContextual` to read at subscription time.

### Placing contextWrite in the Wrong Position

`contextWrite` supplies Context to upstream operators. Check pipeline direction and split methods if needed.

### Thinking contextWrite Passes Data Downstream

Context is provided by the subscriber and read upstream. Do not treat it like an imperative variable assignment visible to all subsequent lines.

### Using Context Instead of Authorization

Having a tenant ID in Context does not prove the user has access to that tenant. Authenticate and authorize before writing it.

### Trusting Tenant Headers or Message Payloads

Headers and messages can be spoofed without trust guarantees. Verify membership and permissions before using them.

### Calling Nested Subscribe

A new subscription can lose context, transactions, cancellation, and error propagation. Compose publishers using `flatMap`, `then`, or appropriate operators.

### Thinking publishOn Drops Reactor Context

Standard Reactor operators preserve subscription Context across scheduler switches. Issues usually arise when leaving Reactor or interacting with unbridged `ThreadLocal`s.

### Thinking MDC Automatically Receives All Context Values

MDC relies on `ThreadLocal`. You need Micrometer Context Propagation/tracing instrumentation or a bridge with explicit cleanup.

### Setting a Custom Trace ID Instead of Using the Tracing Framework

Correlation IDs and distributed trace IDs have different semantics. Let Micrometer Tracing/OpenTelemetry manage traces/spans and propagation.

### Assuming Context Automatically Adds Tenant Predicates or RLS

Context only supplies data to code. Queries must use the tenant ID or transactions must configure RLS settings properly.

### Letting Session Tenant State Leak Across the Pool

Never use session-level `SET` without resetting. Prefer transaction-local settings and test connection return to the pool.

## 18. Implementation Workflow

1. List metadata to propagate: actor, tenant, correlation ID, and trace context.
2. Identify the trusted source for each value.
3. Let Spring Security manage `SecurityContext` in Reactor Context; read via `ReactiveSecurityContextHolder`.
4. Generate correlation IDs at the HTTP boundary or trusted gateway and write with `contextWrite` in a `WebFilter`.
5. Verify tenant selection and access rights before placing the tenant in Context.
6. Define centralized keys or an immutable request metadata record.
7. Use `deferContextual` where metadata is read; handle missing keys explicitly.
8. Ensure all tenant-scoped queries include a tenant predicate or corresponding database policy.
9. Let Micrometer Tracing/OpenTelemetry propagate trace context and configure WebClient instrumentation.
10. Use Micrometer Context Propagation if bridging to `ThreadLocal`/MDC is needed.
11. Avoid nested subscriptions; keep operations in the same reactive pipeline and transaction when required.
12. Create dedicated contexts for message consumers/schedulers with appropriate actors and correlation IDs.
13. Test two concurrent subscriptions to confirm no tenant/user/correlation ID leakage.
14. Test missing context, anonymous users, unauthorized tenants, and cancellation.

## 19. Quick Checklist

- [ ] Use Reactor Context for subscription-scoped metadata, not `ThreadLocal` directly.
- [ ] Use `contextWrite` to add values and `deferContextual` to read upon subscription.
- [ ] Understand that `contextWrite` provides Context to upstream operators.
- [ ] Use consistent keys and small, immutable values.
- [ ] Read identity via `ReactiveSecurityContextHolder` in WebFlux.
- [ ] Never trust arbitrary user IDs or tenant IDs from headers/bodies.
- [ ] Verify tenant access permissions before writing tenant into Context.
- [ ] Tenant-scoped queries always include a tenant predicate or verified RLS policy.
- [ ] Do not confuse correlation IDs with trace IDs.
- [ ] Let tracing instrumentation manage trace/span propagation.
- [ ] Configure MDC/ThreadLocal bridges intentionally with proper cleanup.
- [ ] Never call `subscribe()` or `block()` inside a Service to spawn detached flows.
- [ ] Keep R2DBC transactions within the same reactive pipeline.
- [ ] Prevent tenant session settings from leaking across the connection pool.
- [ ] Message consumers and schedulers establish context from their own trusted sources.
- [ ] Include tests for context propagation, context isolation, missing keys, and tenant authorization.

Reactor Context is the foundation for propagating subscription-scoped metadata in WebFlux and Spring Data R2DBC. When identity comes from Spring Security, tenants are authorized before use, correlation IDs are generated at the request boundary, and trace contexts are managed by instrumentation, reactive layers can collaborate without depending on fixed threads. Context only supplies information to the pipeline; queries, transactions, authorization, and database policies must still fulfill their own responsibilities.
