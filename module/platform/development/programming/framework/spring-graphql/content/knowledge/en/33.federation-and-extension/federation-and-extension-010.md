# Spring GraphQL in a multi-service architecture

Spring for GraphQL can be used to build a GraphQL API in a monolithic application, a GraphQL endpoint at the BFF/API gateway layer, or multiple GraphQL subgraphs in a microservices architecture. The framework provides the GraphQL infrastructure for each service; it does not split a system into microservices itself, does not route requests between services on its own, and does not create distributed transactions.

When introducing GraphQL into a multi-service system, you must decide which service owns which data and fields, which endpoint clients hit, how services coordinate to return a single response, how identity is propagated across network boundaries, and how to handle slow or failing dependencies. Apollo Federation is a common way to unify multiple GraphQL subgraphs into a supergraph. Another option is building a GraphQL BFF or API composition service using GraphQlClient/HTTP clients to call existing backends.

This lesson focuses on choosing an architecture, implementing service boundaries with Spring GraphQL, avoiding per-field network calls, securing cross-service requests, handling errors, and operating the system.

## 1. GraphQL and microservices solve two different problems

Microservices partition a system along business boundaries and data ownership. Each service can be deployed, scaled, and released independently. GraphQL provides a field-level data query contract, allowing clients to choose the response structure they need.

The two concepts complement each other:

- Microservices decide who owns capabilities and data.
- The GraphQL schema describes which data clients can request.
- Resolvers connect schema fields to use cases or data sources.
- A gateway/BFF/Federation router coordinates requests across multiple services when one response requires multiple domains.

GraphQL does not replace service boundaries. If a GraphQL resolver reads directly from another service's database, the system has created cross-service data coupling even though the endpoint is GraphQL. Call the API published by the data-owning service, or use federation so the gateway routes to the right subgraph.

## 2. Ways to organize GraphQL in a multi-service system

There are three common patterns:

| Architecture style | How it works | Best suited when |
| --- | --- | --- |
| Single GraphQL gateway/BFF | One GraphQL server calls REST, gRPC, or GraphQL APIs of backends | Multiple backends already exist and you want an API tailored to each client's needs |
| Apollo Federation | Multiple GraphQL subgraphs publish their own schemas; a router composes a supergraph and builds query plans | Multiple domain teams own GraphQL schemas/fields and need to develop independently |
| Per-service GraphQL, client picks endpoint | Clients call multiple GraphQL APIs directly | Few services, internal clients can manage multiple APIs, and a single unified graph is unnecessary |

A common architecture is for clients to know only one endpoint at the gateway/router. The gateway may be a custom-built BFF or a Federation router. Each Spring GraphQL service continues to own its schema, resolvers, authorization, and domain data.

There is no requirement that every microservice expose GraphQL. Some services may expose only REST, gRPC, or message-based APIs. A GraphQL gateway can call those APIs and transform the data into a GraphQL response.

## 3. BFF/API composition architecture

In the BFF model, Spring GraphQL runs at the client-facing API layer. Resolvers call application services, which coordinate backends via appropriate clients:

~~~mermaid
flowchart TD
    C[Web or Mobile Client] --> G[Spring GraphQL BFF]
    G --> A[Application Service]
    A --> P[Product Service]
    A --> O[Order Service]
    A --> U[User Service]
    P --> PD[(Product DB)]
    O --> OD[(Order DB)]
    U --> UD[(User DB)]
    G --> R[GraphQL Response]
    R --> C
~~~

The BFF owns a schema designed for the client experience, such as ProductCard, OrderSummary, or AccountDashboard. It does not need to expose each backend's internal schema verbatim.

Example GraphQL query:

~~~graphql
query Dashboard {
    dashboard {
        displayName
        recentOrders {
            id
            status
        }
        recommendedProducts {
            id
            name
        }
    }
}
~~~

The BFF can coordinate User Service, Order Service, and Product Service to return one response. The benefit is that clients do not need to know about multiple backends and the schema can be optimized per screen. In return, the BFF must manage downstream calls, timeouts, partial failures, DTO mapping, and service contracts.

If every resolver calls a separate service, the BFF can become an unruly network orchestration layer. Place orchestration in application services, batch independent requests when appropriate, and use batch APIs for sets of IDs.

## 4. Apollo Federation architecture

Federation organizes one unified graph from multiple GraphQL subgraphs. Each subgraph owns part of the schema and implements the fields within its domain. The router receives client requests, builds query plans, and calls subgraphs according to field dependencies.

~~~mermaid
flowchart TD
    C[GraphQL Client] --> R[Federation Router]
    R --> S[Supergraph Query Plan]
    S --> P[Catalog Subgraph]
    S --> O[Order Subgraph]
    S --> U[Customer Subgraph]
    P --> PD[(Catalog DB)]
    O --> OD[(Order DB)]
    U --> UD[(Customer DB)]
    P --> R
    O --> R
    U --> R
    R --> C
~~~

Spring for GraphQL provides integration with federation-jvm. A subgraph can use FederationSchemaFactory to build a federation schema, declare entities with @key, and restore entities via @EntityMapping. The router uses _service to fetch the SDL and _entities to resolve entity representations when a query plan spans multiple subgraphs.

For example:

- The Catalog subgraph owns Book with id, title, and price.
- The Review subgraph extends Book with rating and reviews.
- The Order subgraph owns Order and references Book by product ID.
- The router can fetch Book from Catalog and then call Review to supply rating.

Federation enables domain teams to manage their own schemas. It does not automatically guarantee sound service boundaries; ownership, entity keys, authorization, and cross-subgraph dependencies still need to be designed.

## 5. Role of Spring GraphQL in each service

A Spring GraphQL subgraph typically consists of these layers:

| Layer | Responsibility |
| --- | --- |
| SDL | Publishes types, fields, inputs, and entity keys owned by the service |
| Controller/resolver | Maps GraphQL fields to use cases |
| Application service | Executes business rules and orchestration within the service's scope |
| Repository/client | Accesses databases or dependencies the service is allowed to call |
| Security | Authenticates callers and checks permissions on each operation/field |
| GraphQlSource/FederationSchemaFactory | Builds the GraphQL schema, including the subgraph protocol when using Federation |
| Observation/logging | Tracks latency, errors, and dependencies |

A service should retain ownership of its own data. Other services should not query that service's database directly just to save an HTTP call. Use APIs or event contracts published by the owner; if read-heavy data from multiple domains is needed, consider a purposefully built read model/materialized view.

## 6. Designing service boundaries and schema ownership

The schema should reflect domain capabilities rather than necessarily mirroring database table structures. For example, Order Service owns Order, payment status, and order history. Catalog Service owns Product, list prices, and product descriptions.

When a field belongs to another domain, there are two choices:

1. A gateway/BFF calls the field-owning domain's API and merges the response.
2. In Federation, the subgraph owning the entity can be extended by another subgraph via key.

Avoid having multiple services write to the same data source or claim ownership of the same field without clear rules. In Federation, use ownership directives matching your federation version and composition rules. Outside Federation, explicitly document which service is the source of truth.

Do not design one subgraph per table. Group fields by capability and business language so changing a single use case does not require coordinating too many services.

## 7. Calling other GraphQL services with GraphQlClient

Spring for GraphQL provides GraphQlClient with a unified workflow across HTTP, WebSocket, and RSocket. A BFF can use HttpGraphQlClient to call backend GraphQL APIs.

Example creating a client via WebClient:

~~~java
@Configuration
public class DownstreamGraphQlConfig {

    @Bean
    HttpGraphQlClient catalogGraphQlClient(
            WebClient.Builder webClientBuilder) {

        WebClient webClient = webClientBuilder
            .baseUrl("http://catalog-service/graphql")
            .build();

        return HttpGraphQlClient.builder(webClient).build();
    }
}
~~~

Service calling an operation:

~~~java
@Service
public class CatalogClient {

    private final HttpGraphQlClient graphQlClient;

    public CatalogClient(HttpGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }

    public Mono<ProductView> findProduct(String id) {
        return graphQlClient.document("""
                query ProductById($id: ID!) {
                    product(id: $id) {
                        id
                        name
                        price
                    }
                }
                """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(ProductView.class);
    }
}
~~~

This is a WebFlux/reactive example. If the application uses Spring MVC and blocking I/O, you can choose HttpSyncGraphQlClient backed by RestClient. Do not call block() arbitrarily on the WebFlux event loop.

GraphQlClient helps a BFF call GraphQL backends with strongly typed operations and variables. It is not a Federation router and does not build query plans across multiple subgraphs.

## 8. Calling independent services in parallel

If a dashboard needs data from three independent services, you can call them in parallel instead of sequentially:

~~~java
public Mono<Dashboard> loadDashboard(String customerId) {
    Mono<CustomerView> customer =
        customerClient.findCustomer(customerId);
    Mono<List<OrderView>> orders =
        orderClient.findRecentOrders(customerId);
    Mono<List<ProductView>> recommendations =
        catalogClient.findRecommendations(customerId);

    return Mono.zip(customer, orders, recommendations)
        .map(tuple -> new Dashboard(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()));
}
~~~

Only run calls in parallel when they do not depend on each other's results and downstream systems can handle that concurrency. If one call depends on an ID returned by an earlier call, preserve ordering or design an appropriate batch/aggregate endpoint.

Mono.zip requires all sources to emit a value by default. If a dependency may return no data, define an explicit fallback or result type for that case; do not turn errors into empty objects that clients cannot distinguish from real data.

## 9. Avoiding chatty calls and N+1 over the network

N+1 does not happen only with SQL. A resolver making an HTTP call per parent object can create a network N+1:

~~~java
@SchemaMapping(typeName = "Order", field = "customer")
public Mono<CustomerView> customer(Order order) {
    return customerClient.findCustomer(order.customerId());
}
~~~

If a query returns 100 Orders, the resolver can issue 100 HTTP requests to Customer Service. DataLoader in GraphQL does not automatically turn a single-item HTTP client into a batch API; the batch loader must actually collect keys and call downstream in bulk.

Solutions:

- Expose a batch endpoint in the data-owning service, such as customersByIds(ids).
- Use DataLoader or @BatchMapping to collect customer IDs across multiple Orders.
- Cache immutable or rarely changing data under a policy with an explicit TTL.
- Avoid resolvers calling services sequentially across multiple layers.
- Fetch fields only when selected by the client and permitted by authorization.

Example batch loader:

~~~java
@Component
public class CustomerBatchLoader {

    public CustomerBatchLoader(
            BatchLoaderRegistry registry,
            CustomerClient customerClient) {

        registry.forTypePair(String.class, CustomerView.class)
            .registerMappedBatchLoader((ids, environment) ->
                customerClient.findCustomers(ids));
    }
}
~~~

CustomerClient.findCustomers(ids) must call an actual batch API and return a Map from ID to CustomerView. If this method still loops over each ID and calls findCustomer(), the N+1 problem has merely shifted from the resolver into the service client.

## 10. DataLoader and request boundaries

DataLoader typically caches and batches loads within the scope of a single GraphQL execution. It is useful when multiple resolvers need the same key or multiple parents share an association type.

When using DataLoader with downstream services:

- Batch keys must have clear, stable types.
- The batch function must return accurate results for each key.
- If using a mapped batch loader, Map keys must match the requested IDs.
- Do not share DataLoader caches across requests or users if data depends on permissions.
- Pass tenant/security scope to downstream queries rather than trusting client-supplied IDs.
- Cap batch sizes to avoid creating oversized requests.

DataLoader does not replace a distributed cache. A loader's cache typically serves one execution; if cross-request caching is needed, design TTL, invalidation, and isolation separately.

## 11. Propagating authentication and request context

In a multi-service architecture, the gateway or BFF needs to pass appropriate identity to downstream services. Depending on security requirements, you can use OAuth2 token relay, service-to-service credentials, or a token exchange model.

Do not forward all headers blindly. Only forward allowlisted headers, and do not trust client-sent X-User-Id or X-Tenant-Id headers unless the gateway has verified and regenerated them.

On the Spring GraphQL server side, WebGraphQlInterceptor can read details from the HTTP request and put required values into GraphQLContext:

~~~java
@Component
public class RequestContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
            request.getHeaders().getFirst("X-Correlation-Id");

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context -> {
                if (correlationId != null) {
                    context.put("correlationId", correlationId);
                }
            }).build());

        return chain.next(request);
    }
}
~~~

Resolvers can read the context:

~~~java
@QueryMapping
public Dashboard dashboard(
        @ContextValue("correlationId") String correlationId,
        Principal principal) {
    return dashboardService.load(principal, correlationId);
}
~~~

GraphQLContext only shares data within an execution; it does not automatically propagate context over HTTP. Outbound GraphQlClient/WebClient instances need separate header/token configuration, ideally through a centralized interceptor or filter. Use the Spring Security context and OAuth2 client support to obtain credentials per policy rather than concatenating tokens into query strings.

## 12. Authorization at gateway and subgraph

The gateway can authenticate users before accepting queries, yet each subgraph must still protect the data it owns. Never assume requests coming from the gateway are always valid or that every field is readable.

A typical model can include:

1. The gateway authenticates the end user's access token.
2. The gateway forwards the verified token or a token exchanged for the subgraph's audience.
3. The subgraph validates the token and builds its SecurityContext.
4. Resolvers/services check permissions by resource, tenant, and action.
5. Batch loaders enforce the same authorization scope as single-item resolvers.

With shared service credentials, you need a trusted mechanism to carry signed user identity or authorization context. Do not trust unprotected identity headers.

Field-level authorization should live close to domain logic or method security. Hiding a field at the gateway is insufficient if the subgraph can still be called directly or accessed via another query plan.

## 13. GraphQL errors and partial data across services

A GraphQL response can contain both data and errors. If Product Service succeeds while Recommendation Service fails, the BFF can return the usable product data along with a GraphQL error on the recommendations field, depending on schema nullability and error mapping.

Avoid turning every downstream error into an empty list or null without semantics. Clients need to know which fields lacked real data, which failed, and whether retrying makes sense.

Example categorization:

| Downstream error | Appropriate handling |
| --- | --- |
| Resource does not exist | Return NOT_FOUND or null per contract |
| Permission denied | Return FORBIDDEN/UNAUTHORIZED per policy |
| Timeout on an optional field | Can return partial data and an error with a stable code |
| Mandatory dependency unavailable | Can fail the operation or return an error on the required field |
| Invalid downstream request sent by BFF | Log internal error without blaming the end client |

GraphQL null propagation can bubble nulls up to parent objects if fields are declared non-null. Schema design should account for independent dependencies failing. Do not mark a field depending on another service non-null simply because data is usually present if the system needs partial responses when a dependency is disrupted.

When using GraphQlClient, you can use execute() to inspect both the response and errors instead of only calling retrieve on a path when handling partial data. Transport errors (timeouts, connection refused) differ from GraphQL errors returned by downstream services.

## 14. Timeouts, retries, and circuit breakers

Every network call needs a finite timeout. If a BFF waits on multiple services sequentially, total latency can equal the sum of each dependency's latency. Parallel calls reduce latency for independent work, yet an overall request deadline is still required.

Principles:

- Set connect timeouts and response timeouts on HTTP clients.
- Maintain a deadline budget at the operation/BFF level.
- Use circuit breakers to stop calling persistently failing dependencies.
- Use bulkheads or concurrency limits so one slow service does not exhaust all resources.
- Use bounded retries with jitter, and only when the operation is safe to repeat.
- Never automatically retry non-idempotent mutations.
- Avoid retrying at every layer simultaneously, as that can amplify load.

For read queries, retries may be appropriate for transient failures while time budget remains. For mutations, use idempotency keys or command IDs if business semantics allow safe retries.

Fallbacks must be meaningful to the business. Stale caches or default data should only be used when the contract allows it; never return stale data as fresh without indicating freshness.

## 15. Cross-service mutations and consistency

GraphQL mutations only guarantee sequential execution of top-level mutation fields within an operation per GraphQL rules. They do not create an ACID transaction spanning multiple microservices.

For example, creating an order might require:

1. Order Service creates an order in PENDING state.
2. Inventory Service reserves stock.
3. Payment Service processes payment.
4. Order Service transitions status to CONFIRMED or FAILED.

Do not open a database transaction in the BFF expecting it to roll back Inventory and Payment databases. Each service has its own local transaction.

Common patterns:

- **Saga:** orchestrates steps and compensating actions when a step fails.
- **Transactional outbox:** writes domain changes and events in the same local transaction, then publishes events.
- **Idempotency:** uses command IDs/idempotency keys to handle retries and duplicate messages.
- **Process manager:** tracks long-running business workflows across multiple services.

A GraphQL mutation should invoke a single meaningful business use case, such as placeOrder, rather than having the gateway perform a sequence of database writes across multiple domains itself.

## 16. Subscriptions and streaming in a multi-service system

Spring for GraphQL supports HTTP, WebSocket, Server-Sent Events, and RSocket depending on transport and configuration. Subscriptions typically need an event source such as a message broker or reactive publisher.

One service can emit domain events via Kafka/RabbitMQ while the GraphQL API subscribes to the event stream and turns it into GraphQL responses. When running multiple instances, account for consumer groups, event fan-out, replay, backpressure, connection lifecycles, and per-subscriber permissions.

Do not use an internal WebSocket subscription in place of a message broker for durable service-to-service communication. GraphQL subscriptions serve client streams; broker/event contracts are usually better suited for service-to-service event delivery.

## 17. Propagating traces and correlation across services

A GraphQL request can pass through a router, BFF, and multiple subgraphs. If each service logs independently without propagating trace context, pinpointing where latency originates becomes difficult.

Recommended practices:

- Use Micrometer Observation/Tracing or compatible OpenTelemetry instrumentation.
- Propagate trace context through HTTP client and server instrumentation.
- Log operation names, service names, and correlation IDs.
- Measure latency, error rates, and timeouts for each downstream dependency.
- Track spans for GraphQL requests, DataFetchers, DataLoaders, and outbound HTTP calls.
- Do not put tokens, PII, raw query variables, or entire queries into metric labels.

A good trace can show a BFF operation waiting 30 ms on Catalog, 180 ms on Order, and 20 ms on Customer, immediately identifying Order Service as the dominant latency dependency. Metrics show trends, traces show individual requests, and logs provide diagnostic context.

## 18. Protecting GraphQL endpoints from overly expensive queries

A client can request deeply nested fields or alias the same field many times. When resolvers call other services, wide queries can trigger massive fan-out.

Measures to consider:

- Depth limits and query complexity/cost limits.
- Maximum page sizes for connections/lists.
- Limits on alias counts or operation counts per policy.
- Per-user/client request rate limits.
- Concurrency and batch size limits.
- Persisted queries/allowlists for trusted clients where appropriate.
- Field-level authorization and downstream timeouts.

DataLoader reduces repeated calls per key, yet it does not eliminate the cost of a query with thousands of nodes or expensive fields. Measure both batch key counts, total downstream requests, and response sizes.

## 19. Managing schemas and independent deployments

In a multi-service system, the schema is the contract between services and clients/gateways. Schema changes should be backward-compatible:

- Adding nullable fields is generally safer than altering existing fields.
- Do not change the type or semantics of fields currently used by clients.
- Deprecate fields before removing them.
- Entity key changes must be coordinated with the router and affected subgraphs.
- Run composition checks before deploying new schemas.
- Maintain backward compatibility while gateway and subgraph deployments are out of sync.

With Federation, CI pipelines should collect subgraph SDLs and run composition checks before releasing. If composition fails, do not publish a subgraph schema that breaks the supergraph.

Deploy using expand-and-contract: add new fields/keys or endpoints, update consumers/gateway, observe traffic, and only then remove old contracts. Never assume all services deploy simultaneously.

## 20. Testing a multi-service system

Test across multiple boundaries:

| Test type | Goal |
| --- | --- |
| Application service unit test | Business rules and data mapping |
| GraphQlTester | SDL, resolvers, error mapping, nullability, and authorization |
| GraphQlClient contract test | Downstream operation/variables and response contracts |
| Subgraph entity test | _service, _entities, @EntityMapping, and representations |
| Federation composition test | Subgraph SDLs compose into a valid supergraph |
| Integration test | Gateway/BFF calling multiple services over real networking or testcontainers |
| Failure test | Timeouts, unavailable services, partial data, retries, and circuit breakers |
| Security test | Token relay, tenant isolation, and direct subgraph access |

GraphQlTester tests GraphQL execution inside one service, not router query plans or full network behavior. Test at the gateway/router to confirm real queries decompose properly and subgraphs return accurate data.

Tests should cover scenarios where one subgraph fails while another succeeds, missing entities, batch results missing keys, denied authorization, and retried mutations.

## 21. Example end-to-end request flow

Suppose a client needs an orders page:

~~~graphql
query CustomerOrders($customerId: ID!) {
    customer(id: $customerId) {
        displayName
        orders(first: 10) {
            edges {
                node {
                    id
                    status
                    total
                    items {
                        product {
                            id
                            name
                        }
                    }
                }
            }
        }
    }
}
~~~

In a BFF architecture:

1. The GraphQL resolver calls the Customer application service.
2. The service fetches the customer from Customer Service.
3. Order Service returns a page of orders by customer ID.
4. Product Service supplies product data via a batch endpoint for all product IDs across order items.
5. The BFF assembles DTOs and GraphQL executes the selection set.

In a Federation architecture:

1. The router receives the query and builds a query plan.
2. The Customer subgraph resolves the customer.
3. The Order subgraph extends customer or resolves orders by entity key/field ownership.
4. The Product subgraph resolves Product entities from representations.
5. The router merges results and returns the response to the client.

Both models can produce the same response, yet orchestration responsibilities differ. Choose a model based on ownership, number of domain teams, router operability, and client needs—not merely because one model has more annotations.

## 22. Common pitfalls

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Multiple services accessing the same database | Data schema and deployment coupling | Each service owns its data; communicate via contracts |
| Resolver making separate HTTP calls per parent | Network N+1 and latency scaling with node count | Batch APIs and DataLoader/@BatchMapping |
| Thinking DataLoader batches HTTP automatically | Loader still fires one request per key | Batch functions must call downstream batch endpoints |
| BFF becoming a domain service | Business logic and ownership get mixed | Keep BFF at orchestration/presentation, domain in owning services |
| Treating Federation router as a Spring GraphQL server | Confusing composition with subgraph execution | Separate router/gateway from Spring GraphQL subgraphs |
| Authenticating only at the gateway | Subgraphs called directly remain unprotected | Enforce authentication and authorization in every service |
| Forwarding all client headers | Identity spoofing or credential leakage | Allowlist and build context from verified data |
| Using one transaction across multiple database services | No cross-service atomic rollback | Saga, outbox, and idempotency |
| Retrying every mutation | Duplicate orders or payments | Idempotency keys and per-operation retry policies |
| Hiding dependency failures with empty data | Clients cannot tell data is missing due to errors | Return GraphQL errors/partial data per contract |
| Leaving query complexity unbounded | Uncontrolled fan-out and downstream load | Depth/cost limits, page caps, rate limits |
| Not propagating traces | Unable to pinpoint which service causes latency | Instrument HTTP clients/servers and propagate trace context |
| Deploying subgraphs without composition checks | Supergraph may fail to build | Run schema composition in CI |

## 23. Principles for designing Spring GraphQL in multiple services

Place Spring for GraphQL at the API boundary that a service genuinely owns. If you need a client-tailored API, use a BFF/API composition layer calling backends with appropriate clients; if multiple domain teams share ownership of one graph, consider Apollo Federation with a router and Spring GraphQL subgraphs. Never let resolvers read another service's database directly.

Keep resolvers thin, place orchestration in application services, batch downstream calls, and avoid making one network call per parent object. Propagate identity through verified mechanisms, enforce permissions in each subgraph, and keep transactions within service boundaries. Use Saga/outbox/idempotency for write workflows spanning multiple domains.

Configure timeouts and concurrency limits for dependencies, distinguish GraphQL errors from transport errors, allow partial data when appropriate to the contract, and avoid retrying non-idempotent mutations. Trace across services, bound query complexity, validate composition, and evolve schemas backward-compatibly.

Spring GraphQL provides the foundation for each service to build a GraphQL endpoint and integrate Federation or GraphQlClient. The quality of a multi-service architecture still depends on domain ownership, contracts, security, resilience, and end-to-end operability.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — GraphQlClient](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Request Execution and Schema Creation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring GraphQL support](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Apollo Federation — Introduction](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/federation)
