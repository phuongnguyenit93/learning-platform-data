# Keep Business Logic Out of Interceptors

Interceptors in Spring gRPC sit at the transport boundary: they observe an RPC before the request reaches the service or as the response/status goes out. This position suits cross-cutting concerns such as metadata, tracing, authentication, logging, metrics, and shared method-level policies. It is not the place to implement per-use-case business rules.

If an interceptor queries products, checks inventory, calculates fees, decides order status, or updates the database, the transport layer knows too much about the domain. Then a business change can force edits to a shared interceptor, unrelated RPCs are affected, and logic becomes hard to test in isolation. **Keep interceptors thin; place business decisions in the application/domain layer.**

## 1. Distinguishing cross-cutting concerns from business rules

A practical categorization:

| Concern | Example | Proper location |
| --- | --- | --- |
| Transport metadata | Read/attach correlation ID, trace context | Client/server interceptor |
| Observability | Record method, status, duration, trace attributes | Interceptor or instrumentation |
| Authentication | Verify bearer token, create principal | Security interceptor/filter or security layer |
| Coarse-grained method policy | Whether caller may invoke admin RPC group | Interceptor or method security |
| Resource authorization | Whether caller may read this exact product/order/tenant | Application service/domain policy |
| Input validation | Non-empty ID, valid format | Adapter/validator and application boundary |
| Business invariant | Do not sell discontinued products; no negative stock | Domain model/domain service |
| Use-case orchestration | Load aggregate, check permission, save changes, emit event | Application service |
| Persistence | Query and write database | Repository/infrastructure |

The boundary does not depend solely on the operation's name. Authentication determines who the caller is; resource-level authorization needs to know what the caller wants to do with which specific object. Interceptors usually know the method name and metadata, but should not have to load domain objects just to evaluate a use-case-specific rule.

## 2. Anti-pattern: interceptor querying and making business decisions

Example to avoid:

```java
public final class ProductPolicyInterceptor implements ServerInterceptor {
    private final ProductRepository products;

    public ProductPolicyInterceptor(ProductRepository products) {
        this.products = products;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String productId = headers.get(PRODUCT_ID);
        Product product = products.findById(productId).orElse(null);

        if (product == null || product.isDiscontinued()) {
            call.close(Status.FAILED_PRECONDITION, new Metadata());
            return new ServerCall.Listener<>() {};
        }
        return next.startCall(call, headers);
    }
}
```

This code causes several problems:

- The interceptor depends on the repository and Product domain structure.
- It assumes every RPC passing through the interceptor operates on the same product.
- product_id is pushed into metadata even though it belongs as business data in the protobuf request.
- Whether a product can be sold may differ across GetProduct, ReserveStock, and AdminUpdateProduct.
- A database lookup runs on the transport path; persistence latency, timeouts, and failures directly affect opening the RPC.
- The rule is hidden outside the application service, allowing another entry point to bypass it.

Specifically, interceptCall receives metadata and descriptor before receiving the request message. For unary or streaming calls, an interceptor cannot inspect the request body the way a handler does; moving business data into metadata just for an interceptor to read is a sign of a misplaced boundary.

## 3. What should an interceptor do?

A good server interceptor usually has one clear technical responsibility:

```java
public final class RequestContextInterceptor implements ServerInterceptor {
    static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_METADATA);
        if (requestId == null || requestId.isBlank()) {
            requestId = java.util.UUID.randomUUID().toString();
        }

        Context context = Context.current().withValue(REQUEST_ID, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

This interceptor reads metadata, generates a technical ID when missing, and attaches it to gRPC Context. It needs no knowledge of Product, Order, database tables, or pricing policies. The service can read the request ID for logging; the application service still receives business inputs per use case.

Other appropriate concerns:

- Authentication interceptor verifying credentials and placing the authenticated principal into Context.
- Metrics interceptor recording method, RPC type, status, and duration with bounded-cardinality tags.
- Tracing instrumentation injecting/extracting W3C trace context and managing span lifecycles.
- Exception boundary translating synchronous exceptions to gRPC statuses via a centralized mapper.

These concerns cut across many RPCs and can be described independently of any specific use case.

## 4. Resource authorization belongs at the application boundary

An interceptor can authenticate the caller or block a group of methods under a shared policy. But when the decision depends on the resource inside the request, the application service usually has the full context.

The endpoint simply translates the protobuf request into a use-case call:

```java
@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final GetProductUseCase getProduct;

    public CatalogGrpcEndpoint(GetProductUseCase getProduct) {
        this.getProduct = getProduct;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {
        ProductView result = getProduct.execute(
                request.getProductId(),
                CurrentPrincipal.require());
        observer.onNext(toResponse(result));
        observer.onCompleted();
    }
}
```

The use case receives the ID and principal, then enforces authorization and business logic:

```java
public final class GetProductUseCase {
    private final ProductRepository products;
    private final ProductAccessPolicy accessPolicy;

    public GetProductUseCase(
            ProductRepository products,
            ProductAccessPolicy accessPolicy) {
        this.products = products;
        this.accessPolicy = accessPolicy;
    }

    public ProductView execute(
            String productId,
            AuthenticatedPrincipal principal) {
        Product product = products.findById(productId)
                .orElseThrow(ProductNotFoundException::new);

        accessPolicy.checkCanRead(principal, product);
        return ProductView.from(product);
    }
}
```

CurrentPrincipal.require() is an illustrative adapter reading the principal from the current security context. In real projects, you can obtain the principal in the endpoint and pass it explicitly to the use case; that makes dependencies easier to see and test. The key point is that permission to read a Product is checked inside the use case/domain policy, where both the principal and the target object are present.

## 5. Do not move request body fields into metadata to bypass the application layer

Metadata is for short control information like authorization, trace context, transport-related deadlines, and correlation IDs. Use-case data must stay in the protobuf request:

```proto
message ReserveStockRequest {
  string product_id = 1;
  int32 quantity = 2;
  string warehouse_id = 3;
}
```

quantity, product_id, and warehouse_id are business inputs. Interceptors must not require clients to duplicate these fields in metadata. Doing so creates two potentially conflicting sources of truth and makes the contract confusing.

Validation can be split across layers:

- Adapters check simple structural conditions, such as required fields or formats.
- Application services validate inputs against the use case and access rights.
- Domain models protect invariants that must never be violated, whether the use case is invoked from gRPC, REST, a message consumer, or a batch job.

Do not place invariants solely inside an interceptor, because the domain may be called from multiple entry points.

## 6. Interceptors should not orchestrate transactions or workflows

Do not open transactions, call multiple repositories, emit domain events, or orchestrate sagas inside an interceptor. Those responsibilities belong to application services and require clear transaction boundaries.

If an interceptor updates an entity's last_accessed_at on every RPC, it turns an observational concern into a business side effect. That side effect can:

- Run even for health checks or rejected RPCs.
- Generate database writes on every call and increase load.
- Differ in semantics from the use case's read/write operations.
- Be difficult to roll back or coordinate with the handler's transaction.

If auditing a business action is genuinely required, the application service should emit an audit event after confirming the action is valid and determining its outcome. If only technical access logging is needed, the interceptor logs/records metrics without mutating domain state.

## 7. Keeping interceptors safe under concurrency

Interceptors are normally registered and shared across many RPCs. Therefore:

- Never store principal, product, request ID, or per-call state in mutable fields of a singleton.
- Create per-call state inside interceptCall when counting messages or ensuring single-close behavior.
- Use gRPC Context for call-scoped data; propagate context explicitly across executors when running asynchronously.
- Never perform blocking database/network I/O inside transport callbacks.
- Never retain references to requests/responses after a call finishes.
- Never let log/metric recording failures alter the RPC outcome.

These rules keep interceptors thin, predictable, and free of race conditions across concurrent requests.

## 8. Registration and layering in Spring gRPC

A clean layering structure:

```text
gRPC transport
  -> Interceptors
       metadata / tracing / authentication / metrics
  -> gRPC endpoint adapter
       protobuf <-> application input/output
  -> Application use case
       resource-level authorization / orchestration
  -> Domain
       invariants / business rules
  -> Repository and infrastructure
       database / remote systems
```

In Spring gRPC, endpoints and servers are usually auto-configured by the framework. Register interceptors via the extension point of your exact version; never assume an arbitrary bean automatically becomes an interceptor. Keep dependencies unidirectional: interceptors do not depend on use cases/repositories; endpoints invoke application services; the domain does not depend on gRPC or generated protobuf classes.

If a shared method-level policy is needed, you can use the full method name inside an interceptor with a small configuration policy. That policy should not load entities or branch on specific product/order types. Whenever a decision requires domain data, move it into the application/domain layer.

## 9. Testing to catch misplaced business logic

A good test suite verifies both interceptors and use cases:

| Test | What to prove |
| --- | --- |
| Interceptor unit test | Technical metadata/context/status handled properly, no repository calls |
| Use-case unit test | Resource authorization and business invariants are enforced |
| Endpoint integration test | Protobuf request maps cleanly to inputs; use-case errors map to statuses |
| Alternate entry point test | Same use case enforces invariants when invoked outside gRPC |
| Concurrency test | Context/principal of two RPCs never mix |
| Failure test | Database/domain errors do not cause interceptors to hang or double-close calls |

For example, an interceptor test could inject a mock repository and verify it is never called; even better, design the interceptor without any repository dependency from the start. Use-case tests should cover callers from different tenants, discontinued products, and nonexistent resources.

## 10. Interceptor review checklist

- [ ] The interceptor has one technical cross-cutting responsibility describable in a single sentence.
- [ ] Does not query or update entities/repositories.
- [ ] Does not calculate prices, check stock, or decide business states.
- [ ] Does not require clients to pass use-case data in metadata.
- [ ] Authentication is separated from resource-level authorization.
- [ ] Business rules live in the application/domain layer and apply across all entry points.
- [ ] Interceptor does not store per-call mutable state in shared fields.
- [ ] No blocking I/O or workflow orchestration inside transport callbacks.
- [ ] Logging/metrics/tracing never alter the RPC outcome.
- [ ] Unit tests exist for the interceptor and use-case tests cover business logic.

**Self-check**

**Question 1.** Should an interceptor query ProductRepository to block discontinued products?

*Answer:* No. That is a domain and use-case rule. The application/domain service must check product state so every entry point enforces the same invariant.

**Question 2.** Can an interceptor verify a bearer token?

*Answer:* Yes. Credential verification is a cross-cutting concern at the RPC boundary. The interceptor then places the verified principal into Context; specific resource permissions are still checked in the application layer.

**Question 3.** Why shouldn't quantity and product_id be placed into metadata?

*Answer:* Those are business inputs belonging in the protobuf request. Metadata is for control information; putting the same data in two places creates conflicting sources of truth.

**Question 4.** Why shouldn't invariants be checked only inside an interceptor?

*Answer:* Use cases/domains can be invoked from REST, message consumers, batch jobs, or tests. Placing invariants in the domain/application protects every entry point.

**Question 5.** What must a singleton interceptor avoid when handling many concurrent RPCs?

*Answer:* Never store per-call state in shared mutable fields. Use local variables inside interceptCall, gRPC Context, and explicit context propagation across executors.

Good interceptors keep the transport boundary clean: handling metadata, security context, and RPC observability while letting the application/domain decide business behavior. By keeping interceptors free of repository access and use-case orchestration, Spring gRPC becomes easier to test, rules stay reusable, and domain changes have minimal impact on RPC infrastructure.
