# Connection Routing Based on Reactor Context

## 1. The Multi-Database Problem

A Spring Data R2DBC application may need to access multiple databases. Common scenarios include:

- Each tenant has its own database.
- Data is partitioned by region or customer.
- The application needs to switch between read databases and write databases.
- Data groups are stored in independent databases.
- Environments or customers have different connection configurations.

If all repositories use a single `ConnectionFactory`, operations go to the same target. When the database must be selected per tenant or request context, the application needs a connection routing layer.

In imperative programming, a common legacy pattern was storing the route key in a `ThreadLocal`. That approach does not fit reactive pipelines because a single request can hop across multiple threads. With Spring Data R2DBC, the route key should be propagated through **Reactor Context** and read at connection acquisition time.

The idea is to create a routing `ConnectionFactory` backed by multiple target `ConnectionFactory` beans. When a repository needs a connection, the routing factory reads the route key from Reactor Context and selects the corresponding factory.

## 2. What Is Reactor Context?

Reactor Context is a data store attached to a reactive subscription. It allows passing metadata throughout a pipeline without depending on which thread executes callbacks.

For example, the application can put a tenant key into context:

```java
Mono<Customer> result = customerRepository.findById(customerId)
        .contextWrite(context -> context.put("tenant-route", "tenant-a"));
```

`contextWrite` creates a context containing the key `tenant-route` for the upstream portion of the pipeline. When an upstream publisher needs to acquire a connection, the routing factory can read this value.

Key characteristics:

- Context belongs to a subscription, not to a fixed thread.
- Reactor Context is immutable; operators create a new context rather than mutating the old context object.
- `contextWrite` affects operators upstream of where it is placed.
- Standard Reactor operators preserve context across thread switches.
- A new subscription created via `subscribe()` does not automatically share the context of another subscription.

Because the route key must be present before the connection is acquired, set the context at the outer boundary of the publisher or request pipeline, before R2DBC operations start.

## 3. Why Not Use ThreadLocal for Routing?

A thread in a reactive application can serve multiple requests at different times. A single request can also start on one thread and continue on another due to schedulers or drivers.

The following example is unsafe in reactive code:

```java
TenantContextHolder.setCurrentTenant("tenant-a");
return customerRepository.findAll();
```

If `TenantContextHolder` uses `ThreadLocal`, reading the route key may happen on a different thread from the one that set the value. Conversely, a reused thread may still retain the previous request's value if not cleaned up properly.

Reactor Context solves this by attaching the route key to the subscription:

```java
return customerRepository.findAll()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY,
                "tenant-a"));
```

When the pipeline switches threads, the context still travels with the subscription. There is no need to manually copy the tenant key via `ThreadLocal`.

## 4. Routing ConnectionFactory

R2DBC defines `ConnectionFactory` as the connection-creation abstraction. Spring Framework provides `AbstractRoutingConnectionFactory` to choose one of several target `ConnectionFactory` beans based on a lookup key.

This class lives in package:

```java
org.springframework.r2dbc.connection.lookup.AbstractRoutingConnectionFactory
```

The application extends that class and implements `determineCurrentLookupKey()`. With R2DBC, the method returns `Mono<Object>` because resolving the route key may need to consult the reactive context.

High-level routing flow:

```mermaid
flowchart TD
    A[Repository / DatabaseClient] --> B[Routing ConnectionFactory]
    B --> C[Read route key from Reactor Context]
    C --> D{Route key}
    D -->|tenant-a| E[ConnectionFactory A]
    D -->|tenant-b| F[ConnectionFactory B]
    D -->|Invalid| G[Routing error]
    E --> H[Database A]
    F --> I[Database B]
```

The routing factory does not need to know which SQL is running. It only decides which connection is used when the caller requests a connection.

## 5. Declaring a Shared Route Key

Centralize the key name in one class to avoid typos across multiple places:

```java
public final class TenantRouteContext {

    public static final String ROUTE_KEY = "tenant-route";

    private TenantRouteContext() {
    }
}
```

The route key can be a String, an enum, or an internal identifier type. The example uses String for readability; in larger systems, an enum can help prevent invalid values.

Do not put passwords, connection URLs, or sensitive information into Reactor Context. The context should only carry an authenticated route identifier; the routing factory maps that identifier to pre-configured `ConnectionFactory` beans.

## 6. Implementing TenantRoutingConnectionFactory

A simple implementation reading the key from Reactor Context:

```java
import org.springframework.r2dbc.connection.lookup.AbstractRoutingConnectionFactory;
import reactor.core.publisher.Mono;

public final class TenantRoutingConnectionFactory
        extends AbstractRoutingConnectionFactory {

    @Override
    protected Mono<Object> determineCurrentLookupKey() {
        return Mono.deferContextual(contextView ->
                Mono.justOrEmpty(
                        contextView.getOrEmpty(TenantRouteContext.ROUTE_KEY)));
    }
}
```

`Mono.deferContextual` defers reading the context until the publisher is subscribed. `getOrEmpty` returns the value if the key is present, or `Optional.empty()` if absent.

When the key exists, `AbstractRoutingConnectionFactory` uses it to look up the corresponding factory in the target map. When the key is absent or does not match, behavior depends on the default target and fallback configuration.

In multi-tenant systems, it is usually best to fail closed if the route key is missing or invalid. If every request defaults to tenant A's database, a request missing context could accidentally read or write tenant A's data.

## 7. Configuring Multiple Target ConnectionFactory Beans

Suppose the application has two PostgreSQL databases, one for `tenant-a` and one for `tenant-b`. First, configure two independent `ConnectionFactory` beans. You can create them with the R2DBC driver or use the application's own configuration.

Example routing factory declaration, assuming two connection factory beans are configured:

```java
@Configuration
public class MultiDatabaseConfiguration {

    @Bean("tenantAConnectionFactory")
    ConnectionFactory tenantAConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:secret@localhost:5432/tenant_a");
    }

    @Bean("tenantBConnectionFactory")
    ConnectionFactory tenantBConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:secret@localhost:5432/tenant_b");
    }

    @Bean("routingConnectionFactory")
    @Primary
    ConnectionFactory routingConnectionFactory(
            @Qualifier("tenantAConnectionFactory") ConnectionFactory tenantA,
            @Qualifier("tenantBConnectionFactory") ConnectionFactory tenantB) {

        TenantRoutingConnectionFactory routing =
                new TenantRoutingConnectionFactory();

        Map<Object, ConnectionFactory> targets = new HashMap<>();
        targets.put("tenant-a", tenantA);
        targets.put("tenant-b", tenantB);

        routing.setTargetConnectionFactories(targets);
        routing.setLenientFallback(false);
        return routing;
    }
}
```

The example uses illustrative URLs to show connection structure; do not put real credentials in source code. In real projects, obtain credentials from environment variables or secret management. You can configure `ConnectionFactory` via builders/options to avoid manual URL assembly.

Points to note:

- Each tenant has a target factory.
- `setTargetConnectionFactories` registers the map from route key to factory.
- `setLenientFallback(false)` requires unmatched keys to be rejected rather than silently falling back to a default factory.
- The example omits a default target so even a missing route key does not automatically route to a specific tenant.
- `@Primary` marks the routing factory as the default connection factory for beans needing a `ConnectionFactory`.

Bean names, qualifiers, and auto-configuration must be adapted to your project structure. If the application has multiple `ConnectionFactory` beans, explicitly configure repositories/templates and the transaction manager to use the routing factory.

### 7.1. Configuring Lenient Fallback

`AbstractRoutingConnectionFactory` can use a default target and fallback mode. With multi-tenant data, understand the cases clearly:

| Route key | Default target | Lenient fallback | Expected behavior |
| --- | --- | --- | --- |
| Valid key in map | Present/absent | Any | Selects the corresponding factory |
| Key not in map | Present | `true` | May use default target |
| Key not in map | Present | `false` | Rejects unmatched key; default mainly applies to null key |
| Key missing | Absent | `false` | No matching factory; emits error |

With tenant routing, do not configure the default target to be a real tenant's database. If you want a shared database for non-tenant requests, represent that route with an explicit key and only grant that key to valid callers.

## 8. Attaching the Route Key to Reactor Context

The routing factory only reads the context; an outer component must set the route key before the repository acquires a connection.

Example in an application service or controller:

```java
public Flux<Customer> findCustomersForTenant(String tenantId) {
    return customerRepository.findAll()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

When subscribing to the publisher, the context containing the tenant ID flows upstream to the routing factory.

In real applications, do not accept an arbitrary `tenantId` from request body/query parameters and use it directly for routing. The route key must be derived from authenticated information, such as a tenant claim in the principal or the result of a trusted tenant resolver.

### 8.1. Setting Context in a WebFlux WebFilter

If all operations in an HTTP request need the same route, context can be set in a WebFlux filter after identifying and authorizing the tenant:

```java
@Component
public class TenantRoutingWebFilter implements WebFilter {

    private final TenantResolver tenantResolver;

    public TenantRoutingWebFilter(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return tenantResolver.resolveAuthenticatedTenant(exchange)
                .flatMap(tenantId -> chain.filter(exchange)
                        .contextWrite(context -> context.put(
                                TenantRouteContext.ROUTE_KEY,
                                tenantId)));
    }
}
```

`TenantResolver` in the example represents logic verifying the tenant against the principal or application policy. The filter only sets the route key after the resolver returns a valid tenant.

`contextWrite` is placed on the publisher of `chain.filter(...)`, so the context is visible to upstream operations in the request, including controllers, services, transaction interceptors, and repositories when they participate in the same pipeline.

### 8.2. Getting the Tenant from Reactive Security Context

If the application uses Spring Security WebFlux, the tenant can be obtained from the authenticated principal:

```java
Mono<String> tenantId = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getPrincipal)
        .cast(TenantAwarePrincipal.class)
        .map(TenantAwarePrincipal::getTenantId);
```

You can then put the value into context or have `determineCurrentLookupKey()` read directly from `ReactiveSecurityContextHolder`. Either approach must ensure the tenant is authenticated and the route key is validated against the allowed set of factories.

Do not use imperative ThreadLocal-based `SecurityContextHolder` in a reactive flow unless corresponding context propagation is configured. With WebFlux, use `ReactiveSecurityContextHolder`.

## 9. Ordering Context Placement and Transaction Boundaries

A crucial point is that the routing key must be present when the transaction manager acquires the connection.

Example using `@Transactional`:

```java
public Mono<Order> placeOrderForTenant(String tenantId, Order order) {
    return orderService.placeOrder(order)
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

Suppose `orderService.placeOrder` is a method where a Spring proxy applies `@Transactional`. `contextWrite` on the outer publisher propagates the route key to the transaction interceptor when the publisher is subscribed. The transaction manager then asks the routing factory for a connection, and the factory can read the right key.

Do not set the route key after the connection has been acquired. Once the pipeline has started a transaction and the transaction manager has bound a connection, changing context downstream cannot switch the connection already used by the transaction.

### 9.1. Using TransactionalOperator

With programmatic transactions, place context outside the transaction-wrapped publisher:

```java
Mono<Order> work = transactionalOperator.transactional(
        orderRepository.save(order));

return work.contextWrite(context -> context.put(
        TenantRouteContext.ROUTE_KEY,
        tenantId));
```

The subscriber context is provided from `contextWrite` at the end of the chain and is visible to the transaction operator and the routing factory upstream.

Ensure all database operations inside the transaction use the same route key. A normal R2DBC transaction holds one selected connection; changing the route key mid-transaction does not switch the transaction to another database.

### 9.2. Common Mistakes When Setting Context

Do not invoke a repository or start a transaction first and then resolve the tenant in a separate subscription:

```java
// Avoid: route context does not belong to the returned publisher
customerRepository.findAll().subscribe();
return Mono.just("done");
```

An independent subscription does not share lifecycle/context with the caller's publisher. It also detaches query errors and results from the request.

Chain all work in one publisher and place context at the outermost boundary:

```java
return customerRepository.findAll()
        .collectList()
        .flatMap(this::processCustomers)
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY,
                tenantId));
```

## 10. Combining Routing Factory with R2dbcTransactionManager

The transaction manager must use the same routing `ConnectionFactory` that repositories use:

```java
@Bean("routingTransactionManager")
ReactiveTransactionManager routingTransactionManager(
        @Qualifier("routingConnectionFactory") ConnectionFactory routingFactory) {
    return new R2dbcTransactionManager(routingFactory);
}
```

Repositories, `R2dbcEntityTemplate`, `DatabaseClient`, and the transaction manager must all use the same routing factory if they need to participate in the same transaction.

When a transaction begins:

1. Spring invokes `R2dbcTransactionManager`.
2. The transaction manager requests a connection from the routing factory.
3. The routing factory reads the route key from Reactor Context.
4. The routing factory selects the target connection factory.
5. The connection is acquired and bound to the transaction context.
6. Subsequent repository operations in the transaction use the bound connection.
7. The transaction commits/rolls back and the connection is returned to the appropriate factory/pool.

This means the route key must be set before step 2. Otherwise, the lookup key may be empty and routing fails or uses the configured default.

### 10.1. Same Routing Factory for DatabaseClient

If creating `DatabaseClient` manually, use the routing factory:

```java
@Bean
DatabaseClient databaseClient(
        @Qualifier("routingConnectionFactory") ConnectionFactory routingFactory) {
    return DatabaseClient.create(routingFactory);
}
```

If `DatabaseClient` uses a separate target factory, its SQL statements may not participate in transactions managed by the routing transaction manager.

### 10.2. Transaction Manager Name

If there are multiple transaction managers, specify the name explicitly in the annotation:

```java
@Transactional(transactionManager = "routingTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order);
}
```

Do not rely on default selection if the application has multiple managers and multiple databases. Specifying the manager explicitly avoids opening transactions on the wrong resource.

## 11. Tenant Routing in Repositories

Repositories do not need to know about a specific tenant:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {
}
```

Services can also focus on business logic:

```java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Flux<Customer> findAll() {
        return customerRepository.findAll();
    }
}
```

Routing happens at the connection factory. The same repository can access tenant A's or tenant B's database depending on the route key in the subscription.

This is the benefit of connection-level routing: domain repositories do not have to accept a tenant ID in every method signature just to pick the database. However, services still need to enforce tenant authorization and should not rely on the route key as the sole mechanism protecting data.

## 12. Routing Based on Multiple Metadata Sources

The route key can be determined from:

- A tenant claim in an authenticated JWT/principal.
- Hostname/subdomain after checking against a registered domain list.
- A request attribute populated by an authentication filter.
- Job metadata recorded when a message is received from a queue.
- Context of a background task with a clearly identified tenant.

Do not take a route key from an arbitrary header without verification. For example, if a request sends `X-Tenant: tenant-b`, the application must check that the user has permission to access tenant B before putting that key into context.

Nor should the route key contain a caller-supplied connection string. Map an authenticated ID to a factory in a pre-configured allowlist.

## 13. Background Jobs and Message Consumers

Not every pipeline starts from an HTTP request. A message consumer must also set the route key before calling repositories:

```java
public Mono<Void> handle(TenantMessage message) {
    String tenantId = tenantResolver.resolve(message);

    return orderService.process(message)
            .then()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    tenantId));
}
```

In practice, `tenantResolver.resolve` must authenticate the message source and verify the tenant is valid. If a message is retried, the route key must still be resolved from trusted metadata.

For scheduled jobs running across multiple tenants, you can create one pipeline per tenant:

```java
Flux<Void> jobs = Flux.fromIterable(tenantIds)
        .concatMap(tenantId -> processTenant(tenantId)
                .contextWrite(context -> context.put(
                        TenantRouteContext.ROUTE_KEY,
                        tenantId)));
```

`concatMap` processes tenants sequentially. If tenants are independent and concurrent execution is desired, `flatMap` with a concurrency limit can be used. Each inner publisher has its own context so one tenant's route key does not overwrite another's.

## 14. Routing and Connection Pools

Each target `ConnectionFactory` can be a separate pool. The routing factory chooses the target factory; the target factory is responsible for issuing connections according to its configuration.

For example, if there are 100 tenants and each tenant has a pool with max 10 connections, the theoretical total limit can reach 1,000 connections if all pools are utilized. The database server might not handle that many connections.

Consider:

- Number of active tenants/databases.
- `maxSize`, `initialSize`, and acquire timeout of each pool.
- Maximum total connections allowed by the databases.
- Whether pools are initialized lazily or eagerly at application startup.
- Health checks and how pools are closed on application shutdown.
- Whether low-activity tenants should use a shared pool or a different database/schema model.

Do not create a new pool per request. Target `ConnectionFactory` beans should be managed as long-lived beans/resources per database or tenant group.

## 15. Multi-Database Routing Is Not a Distributed Transaction

The routing factory selects one target `ConnectionFactory` for a connection acquisition. It does not turn multiple databases into a single ACID transaction.

Suppose a request needs to:

1. Read a customer from tenant A's database.
2. Write an invoice to the billing database.

If the two operations use two different `ConnectionFactory` beans, the `R2dbcTransactionManager` bound to tenant A's routing factory cannot automatically roll back the operation in the billing database.

A normal R2DBC transaction keeps the connection chosen at the start. Changing the route key mid-transaction does not switch the bound connection. Do not design a transaction expecting to jump back and forth among multiple target factories just by changing Reactor Context.

If cross-database coordination is required, use separate transaction boundaries and appropriate distributed consistency mechanisms such as saga, outbox, idempotent retries, or compensating steps. Do not call two local transactions a single global transaction.

## 16. Ensuring Tenant Isolation

Routing to the right database is one layer of protection, not a replacement for full access control.

Principles to apply:

- Authenticate the user before determining the tenant.
- Verify the principal is authorized to access the corresponding tenant.
- Only allow route keys present in the configured target factory list.
- Missing or invalid route keys must fail explicitly.
- Do not use a specific tenant's database as the default target.
- Do not log connection URLs, passwords, or secrets.
- Test to verify context from request A does not leak to request B.
- In shared database models, still enforce tenant predicates/row-level security in queries/schemas.

A valid route key only determines where to connect. If one tenant can submit another tenant's route key, the application can still access the wrong database. The source of the route key must be authenticated data, not an arbitrary client string.

## 17. Missing or Invalid Route Keys

When `determineCurrentLookupKey()` returns `Mono.empty()`, the routing factory has no lookup key. If a default target exists, the factory may use the default depending on configuration. If there is no default and fallback is disallowed, connection acquisition fails.

For multi-tenant applications, adopt a fail-closed policy:

```java
routing.setLenientFallback(false);
```

And do not declare a default target if every request must have a tenant. When the route key is invalid, emit a clear error and translate it into an appropriate response at the web layer.

You can validate the key directly inside `determineCurrentLookupKey()` to emit a clear error:

```java
@Override
protected Mono<Object> determineCurrentLookupKey() {
    return Mono.deferContextual(contextView ->
            Mono.justOrEmpty(contextView.getOrEmpty(TenantRouteContext.ROUTE_KEY))
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("Tenant route is missing"))));
}
```

This example uses `switchIfEmpty` to signal an error when the key is missing. If `AbstractRoutingConnectionFactory` should apply default behavior itself, choose one consistent policy: either return empty and configure default/fallback, or emit an error directly. With strict multi-tenancy, failing explicitly usually surfaces misconfiguration faster.

## 18. Read/Write or Primary/Replica Routing

Reactor Context does not have to carry only a tenant key. It can also carry read/write intent:

```java
public final class DatabaseRouteContext {
    public static final String ROUTE_KEY = "database-route";

    private DatabaseRouteContext() {
    }
}
```

Routes can be `primary` and `replica`. However, note consistency implications:

- Writing to primary and immediately reading from replica may see stale data due to replication lag.
- Write transactions must always use primary.
- A transaction must not switch from primary to replica after a connection has been bound.
- Queries requiring read-after-write consistency must read from primary or use a session consistency mechanism.

The route can be determined from annotations or use-case metadata, but ensure the route key is set before the transaction begins and all operations in the transaction use the same route.

## 19. Testing Routing with Two Databases

A clear integration test should use two separate databases with the same schema and distinguishable data. For example:

- Database A has customer `tenant-a@example.com`.
- Database B has customer `tenant-b@example.com`.

When route A is set, the repository only sees data A; when route B is set, the repository only sees data B.

Test example with Reactor Context:

```java
@Test
void shouldRouteToTenantA() {
    StepVerifier.create(customerRepository.findAll()
            .collectList()
            .contextWrite(context -> context.put(
                    TenantRouteContext.ROUTE_KEY,
                    "tenant-a")))
            .assertNext(customers -> {
                assertTrue(customers.stream()
                        .anyMatch(c -> c.getEmail().equals("tenant-a@example.com")));
                assertFalse(customers.stream()
                        .anyMatch(c -> c.getEmail().equals("tenant-b@example.com")));
            })
            .verifyComplete();
}
```

Test tenant B similarly with route key `tenant-b`.

### 19.1. Testing Missing Route Key

If the system requires every request to carry a route key, verify that a query without context terminates with an error:

```java
StepVerifier.create(customerRepository.findAll().collectList())
        .expectError()
        .verify();
```

Do not write a test that only checks the query returns empty, because that could mask the routing factory accidentally picking a default database.

### 19.2. Testing No Context Leak Between Requests

Run two publishers with two different contexts:

```java
Mono<List<Customer>> tenantA = customerRepository.findAll()
        .collectList()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY, "tenant-a"));

Mono<List<Customer>> tenantB = customerRepository.findAll()
        .collectList()
        .contextWrite(context -> context.put(
                TenantRouteContext.ROUTE_KEY, "tenant-b"));

StepVerifier.create(Mono.zip(tenantA, tenantB))
        .assertNext(tuple -> {
            assertTrue(tuple.getT1().stream()
                    .allMatch(c -> c.getEmail().endsWith("tenant-a@example.com")
                            || c.getEmail().equals("tenant-a@example.com")));
            assertTrue(tuple.getT2().stream()
                    .allMatch(c -> c.getEmail().equals("tenant-b@example.com")));
        })
        .verifyComplete();
```

In real tests, use clean predicates for fixture data. The goal is to confirm two concurrent subscriptions still use their respective routes without sharing a mutable ThreadLocal variable.

### 19.3. Testing Transactions with Routing

Verify that:

- The route key is set before the transaction manager acquires the connection.
- All operations in the same transaction use the same target database.
- A failure in a later step rolls back changes in the selected target database.
- Changing context across requests does not alter the connection of a running transaction.
- Connections are returned to the pool after commit, rollback, and cancellation.

## 20. Common Mistakes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Always accesses the same database | Route key missing from Reactor Context or default target in use | Set context before acquiring connection and check fallback |
| Route key always empty | Using ThreadLocal or reading context at the wrong time | Use `Mono.deferContextual` in `determineCurrentLookupKey()` |
| `No ConnectionFactory found for lookup key` | Key not present in target map | Check tenant resolver and key/factory map |
| Tenant A reads tenant B's data | Wrong default target or route key taken from unverified input | Fail closed, authorize tenant, and test isolation |
| `@Transactional` uses wrong database | Transaction manager configured with a target factory instead of routing factory | Use the same routing factory for repositories and manager |
| Changing tenant mid-transaction does not switch DB | Connection already bound when transaction began | Do not change route mid-transaction; start a separate transaction if needed |
| Some queries hit another DB | Repository/DatabaseClient uses a separate factory | Configure all persistence components with the same routing factory |
| Context lost in background jobs | Creating detached subscription or not attaching context per message | Use `contextWrite` on each job's publisher |
| Pool connection exhaustion | Pool per tenant too large or long-running transactions | Limit pools, shorten transactions, and monitor acquire timeouts |
| Tests pass but production routes wrongly | Testing only one database or relying on default route | Test multiple databases with distinct data and missing-key cases |

## 21. Design Workflow for Reactor Context-Based Routing

When building multi-database routing, follow this sequence:

1. Identify routing criteria, such as tenant ID, region, or read/write role.
2. Validate the source supplying the route key before putting it into context.
3. Create one `ConnectionFactory` per target database or resource group.
4. Extend `AbstractRoutingConnectionFactory` and read the route key with `Mono.deferContextual`.
5. Register target factories with explicit map keys.
6. Choose default/fallback policy; for multi-tenant systems, prefer fail closed when keys are missing or invalid.
7. Set the route key via `contextWrite` outside the publisher before transactions or repositories acquire connections.
8. Use the routing factory for repositories, `DatabaseClient`, templates, and `R2dbcTransactionManager` that must participate in the same transaction.
9. Keep the route key stable throughout a transaction; do not expect changing context to switch a bound connection.
10. Cap pools and concurrency appropriately for the number of databases/tenants.
11. Test two independent routes, missing route, invalid route, transaction rollback, and context isolation.

Reactor Context-based routing allows the same reactive repository to use multiple databases according to subscription context. `AbstractRoutingConnectionFactory` selects the target when a connection is acquired, while `Mono.deferContextual` reads the route key without thread affinity. Setting context before the transaction boundary, using the same routing factory in repositories and the transaction manager, validating the route key, and failing closed when invalid prevents accidental cross-tenant data access.
