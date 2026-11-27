# Per-Service Stubs

## 1. Objectives

A gRPC server often exposes multiple services, such as Catalog, Inventory, Pricing, and Order. Each service has its own Protobuf contract, service descriptor, and RPC methods. On the client side, gRPC Java generates a separate set of stubs for each service. The application creates stubs from the appropriate channel and uses each stub to call methods belonging to that service.

**Per-service stubs** is the pattern of organizing clients along Protobuf service boundaries: each generated service has its own stub types, while those stubs can share a single ManagedChannel if they target the same endpoint and share connection/security configuration.

After this lesson, you can:

- Explain the relationship between a Protobuf service, generated stubs, and full method paths.
- Create separate stubs for multiple services from the same channel.
- Choose blocking, asynchronous, or future stubs based on each service's needs.
- Inject multiple stubs of different types into a Spring application service.
- Use qualifiers and gateways to avoid ambiguity when configuring multiple clients.
- Decide when services share a channel and when they need separate channels.
- Apply interceptors, credentials, deadlines, and lifecycles at the right scope.
- Test that the right service is invoked when multiple stubs share a target.

## 2. Each Protobuf Service Generates Its Own Stub Set

Suppose the backend provides two services:

```proto
// catalog.proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service ProductCatalog {
  rpc GetProduct(GetProductRequest) returns (Product);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string name = 2;
}
```

```proto
// inventory.proto
syntax = "proto3";

package inventory.v1;
option java_package = "dev.example.inventory.v1";
option java_multiple_files = true;

service InventoryService {
  rpc GetStock(GetStockRequest) returns (Stock);
}

message GetStockRequest {
  string product_id = 1;
  string warehouse_id = 2;
}

message Stock {
  string product_id = 1;
  int32 available_quantity = 2;
}
```

The gRPC Java plugin generates ProductCatalogGrpc and InventoryServiceGrpc, each with factory methods to create the corresponding stubs:

```java
ProductCatalogGrpc.ProductCatalogBlockingStub catalogStub =
        ProductCatalogGrpc.newBlockingStub(channel);

InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub =
        InventoryServiceGrpc.newBlockingStub(channel);
```

ProductCatalogGrpc only contains APIs to invoke ProductCatalog methods; InventoryServiceGrpc contains InventoryService APIs. Each stub has its own Java type and methods. You cannot call getStock() via catalogStub because that method belongs to another service.

A stub is bound to a service descriptor and a channel. When invoking a method, the generated code creates an RPC call using the corresponding service's full method path, for example:

```text
/catalog.v1.ProductCatalog/GetProduct
/inventory.v1.InventoryService/GetStock
```

The Protobuf package, service name, and method name determine the full method path. java_package determines the Java package of the generated classes, not the wire route.

## 3. Multiple Services Can Share One Channel

If two services are served by the same gRPC endpoint and use the same transport/security configuration, the client usually needs only one ManagedChannel:

```java
ManagedChannel backendChannel = ManagedChannelBuilder
        .forAddress("backend.internal", 9090)
        .useTransportSecurity()
        .build();

var catalogStub =
        ProductCatalogGrpc.newBlockingStub(backendChannel);
var inventoryStub =
        InventoryServiceGrpc.newBlockingStub(backendChannel);
```

The two stubs have different types yet share the same channel. gRPC routes each call based on its full method path, so the channel does not need a separate connection per service. Multiple RPCs can multiplex over the same HTTP/2 connection.

```mermaid
flowchart TD
    A[Spring application] --> B[ManagedChannel: backend.internal]
    B --> C[ProductCatalog blocking stub]
    B --> D[InventoryService blocking stub]
    B --> E[Pricing async stub]
    C --> F[/catalog.v1.ProductCatalog/GetProduct]
    D --> G[/inventory.v1.InventoryService/GetStock]
    E --> H[/pricing.v1.PricingService/Calculate]
```

Sharing a channel does not merge the services into one service. Each stub still retains its own method descriptors, request/response types, full method paths, and generated API.

Do not create a separate channel for every generated stub out of habit. The channel manages target, name resolution, load balancing, transport, and connections; the stub describes the service API to invoke over that channel.

## 4. When Is a Separate Channel Needed?

Only share a channel when services genuinely share a destination and transport policy. Create a separate channel when an isolation boundary is required:

| Condition | Organization Approach |
|---|---|
| Catalog and Inventory share host/port and TLS identity | Can share a channel |
| Pricing resides on a different cluster/endpoint | Separate channel for Pricing |
| One service uses a different mTLS client certificate | Separate channel with corresponding TLS identity |
| Different trust store or authority required | Separate channel |
| Need to isolate load balancing, retry policy, or lifecycle | Consider a separate channel |
| Multiple services differ only in RPC methods on the same endpoint | Share channel, create separate stubs |

Do not create separate channels just because service names differ. Conversely, do not force services across different security boundaries onto the same channel merely to reduce bean counts.

Channels are generally shared by target and connection policy, not necessarily by domain name or generated class name. Base the decision on endpoint, TLS, identity, load balancing, and lifecycle.

## 5. Creating Spring Beans for Each Service Stub

With a shared channel, configuration can declare multiple stub beans of different types:

```java
@Configuration
public class BackendGrpcClientConfiguration {

    @Bean(name = "backendChannel", destroyMethod = "shutdown")
    ManagedChannel backendChannel() {
        return ManagedChannelBuilder
                .forAddress("backend.internal", 9090)
                .useTransportSecurity()
                .build();
    }

    @Bean
    ProductCatalogGrpc.ProductCatalogBlockingStub productCatalogStub(
            @Qualifier("backendChannel") ManagedChannel channel) {
        return ProductCatalogGrpc.newBlockingStub(channel);
    }

    @Bean
    InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub(
            @Qualifier("backendChannel") ManagedChannel channel) {
        return InventoryServiceGrpc.newBlockingStub(channel);
    }
}
```

Spring distinguishes the two stubs by bean type. @Qualifier on the channel parameter clarifies which channel is used when the application defines multiple ManagedChannel beans.

When there are multiple beans of the same stub type, name the beans and use qualifiers when injecting. Do not rely on bean declaration order or assume Spring will always pick the intended one among multiple candidates.

Some Spring gRPC starters provide their own client factory, channel builder, or auto-configuration. When a project uses those mechanisms, register generated stubs via the starter's API and let the starter manage the channel lifecycle. The configuration above illustrates the basic bean pattern; do not create an extra channel alongside one already owned by the starter.

## 6. Injecting Multiple Stubs into an Application Service

A use case may need to call multiple services:

```java
@Service
public class ProductAvailabilityService {

    private final ProductCatalogGrpc.ProductCatalogBlockingStub catalogStub;
    private final InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub;

    public ProductAvailabilityService(
            ProductCatalogGrpc.ProductCatalogBlockingStub catalogStub,
            InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub) {
        this.catalogStub = catalogStub;
        this.inventoryStub = inventoryStub;
    }

    public ProductAvailability getAvailability(
            String productId,
            String warehouseId) {

        var productRequest = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();
        var stockRequest = GetStockRequest.newBuilder()
                .setProductId(productId)
                .setWarehouseId(warehouseId)
                .build();

        Product product = catalogStub
                .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
                .getProduct(productRequest);

        Stock stock = inventoryStub
                .withDeadlineAfter(350, TimeUnit.MILLISECONDS)
                .getStock(stockRequest);

        return new ProductAvailability(
                product.getProductId(),
                product.getName(),
                stock.getAvailableQuantity());
    }
}
```

The application service uses the appropriate stub for each service it calls. Each Protobuf request is constructed separately; each derived stub carries its own deadline. The injected base stubs remain immutable and can be shared across calls.

The example above calls sequentially because the Product and Stock results are combined at the end. If the two calls are independent and latency matters, they can be executed asynchronously with async/future stubs and combined afterward. When doing so, enforce an overall deadline for the use case, bound concurrency, and handle errors/cancellation consistently.

## 7. One Service Can Have Multiple Stub Types

Each generated service typically provides factory methods for blocking, async, and future stubs. They represent the same service API with different execution models:

```java
var blockingCatalog =
        ProductCatalogGrpc.newBlockingStub(channel);

var asyncCatalog =
        ProductCatalogGrpc.newStub(channel);

var futureCatalog =
        ProductCatalogGrpc.newFutureStub(channel);
```

Choose based on cardinality and handling style:

| RPC cardinality | Blocking stub | Async stub | Future stub |
|---|---|---|---|
| Unary | Returns response directly | StreamObserver receives response | ListenableFuture<Response> |
| Server streaming | Returns Iterator<Response> | StreamObserver<Response> | Not supported |
| Client streaming | No equivalent blocking streaming API in generated blocking stub | Returns request StreamObserver | Not supported |
| Bidirectional streaming | Bidirectional blocking not supported | Request/response observers | Not supported |

There is no need to create a new channel when creating a different stub type. Blocking, async, and future stubs can share one channel if the target and transport policy are the same.

A service client can expose both blocking and async gateways, though you should pick the API that matches the application's execution model. Do not inject all three stub types into every bean if the use case only uses one.

## 8. Separating Gateways Along Service Boundaries

When an application service accumulates too many generated types or repetitive status handling, create a dedicated gateway for each dependency:

```java
public interface CatalogClient {
    ProductDetails getProduct(String productId);
}

public interface InventoryClient {
    int getAvailableQuantity(String productId, String warehouseId);
}
```

Catalog gateway:

```java
@Component
public class GrpcCatalogClient implements CatalogClient {

    private final ProductCatalogGrpc.ProductCatalogBlockingStub stub;

    public GrpcCatalogClient(
            ProductCatalogGrpc.ProductCatalogBlockingStub stub) {
        this.stub = stub;
    }

    @Override
    public ProductDetails getProduct(String productId) {
        var request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();

        try {
            Product product = stub
                    .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
                    .getProduct(request);
            return new ProductDetails(
                    product.getProductId(),
                    product.getName());
        } catch (StatusRuntimeException ex) {
            throw CatalogCallException.from(ex);
        }
    }
}
```

An Inventory gateway can perform similar mapping. The application service then injects CatalogClient and InventoryClient without needing to know about Protobuf packages, generated stubs, or specific gRPC statuses.

Per-service-boundary gateways are helpful when:

- Multiple use cases call the same dependency.
- Consistent status mapping is needed.
- Generated APIs should be decoupled from domain/application models.
- Dependencies need to be mocked in unit tests.
- A service's contract may evolve independently.

For small applications, injecting stubs directly may suffice. Create a gateway when it clarifies boundaries or eliminates duplicated logic; avoid adding extra classes merely to forward a call with no processing.

## 9. Deadlines and Call Options per Service

Services have different latency budgets. Catalog may need to respond quickly, while a Pricing calculation may need more time. Keep base stubs shared and apply deadlines per call:

```java
Product product = catalogStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getProduct(productRequest);

PriceQuote quote = pricingStub
        .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
        .calculatePrice(priceRequest);
```

Deadlines must fit within the inbound request's remaining budget. If an application service has a 1-second total budget and has already spent 300 ms on Catalog, it cannot grant Pricing 900 ms and still expect the use case to finish within 1 second.

Other call options can also vary by service or call:

- withWaitForReady() if the call can wait for channel readiness within the deadline.
- withCallCredentials(...) if the service requires specific credentials.
- withCompression(...) if the payload benefits and the server supports it.
- withDeadlineAfter(...) according to the latency budget.

Because stubs are immutable, each configuration produces a derived stub without altering the shared base stub.

## 10. Shared Interceptors vs. Service-Specific Interceptors

If all services on the same endpoint share a tracing/metrics policy, wrap the channel once and create stubs from the channel wrapper:

```java
Channel observedChannel = ClientInterceptors.intercept(
        channel,
        tracingInterceptor,
        metricsInterceptor);

var catalogStub =
        ProductCatalogGrpc.newBlockingStub(observedChannel);
var inventoryStub =
        InventoryServiceGrpc.newBlockingStub(observedChannel);
```

If Catalog and Inventory need different interceptors, you can create separate channel wrappers over the same underlying channel:

```java
Channel catalogChannel = ClientInterceptors.intercept(
        sharedChannel, catalogMetricsInterceptor);

Channel inventoryChannel = ClientInterceptors.intercept(
        sharedChannel, inventoryMetricsInterceptor);

var catalogStub =
        ProductCatalogGrpc.newBlockingStub(catalogChannel);
var inventoryStub =
        InventoryServiceGrpc.newBlockingStub(inventoryChannel);
```

Both wrappers still share the underlying transport; they do not own two independent connections. Only create separate wrappers when different policies are needed. Avoid registering the same interceptor on both the channel builder and a wrapper, which would cause an RPC to record spans or metrics twice.

An interceptor can inspect the full method name to apply policies per service/method. Do not use mutable instance fields to store request IDs, tenants, or tokens because interceptors are typically shared across concurrent calls.

## 11. Credentials and Security Boundaries

Services on the same endpoint can share a TLS channel if they share the same server identity and trust policy. However, call credentials or authorization can still differ per service:

- Catalog may only allow reading product information.
- Inventory may require permission to view stock per warehouse.
- Pricing may require a distinct service identity or scope.

Do not equate sharing a channel with sharing permissions. Authentication establishes the principal; authorization must check whether that principal is allowed to call the full method path and access the specific resource.

If two services require different client certificates, trust stores, or authorities, create separate channels to maintain the proper security boundary. Do not try to alter the TLS identity of an already-created channel per RPC via arbitrary metadata.

## 12. Lifecycle Management When Multiple Stubs Share a Channel

When multiple stubs use the same ManagedChannel, the channel is shut down only once by its owning component:

```java
channel.shutdown();
if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
```

Stubs do not own the channel and are not responsible for closing the transport. If ProductCatalogClient and InventoryClient both receive the channel via constructor injection, neither may shut down the channel when its own bean is destroyed.

In Spring:

- Channel beans are created in configuration or by the starter.
- Stub beans depend on the channel bean.
- Gateways/application services depend on stubs or client interfaces.
- The application context closes the channel via its lifecycle owner.

If each service has its own channel, each channel must have its own owner and shutdown policy. Give beans clear names such as catalogChannel and inventoryChannel, and use @Qualifier to prevent injecting the wrong one.

## 13. Testing Per-Service Stubs

Tests should verify that each stub calls the right service/method, even when they share a channel.

### Unit Testing Application Orchestration

If the application service injects gateway interfaces, mock each dependency:

```java
when(catalogClient.getProduct("p-1"))
        .thenReturn(new ProductDetails("p-1", "Keyboard"));
when(inventoryClient.getAvailableQuantity("p-1", "wh-1"))
        .thenReturn(12);

ProductAvailability result =
        service.getAvailability("p-1", "wh-1");

assertEquals("Keyboard", result.productName());
assertEquals(12, result.availableQuantity());
```

This test verifies orchestration, not gRPC routing.

### Integration Testing on the Same Channel

Start a test server registering both ProductCatalog and InventoryService. Create both stubs from the same channel, call each method, and verify responses from the right service.

Tests should catch:

- Catalog stub accidentally calling Inventory methods/service.
- Incorrect full method paths or service registration.
- Both services sharing a channel fail under concurrent calls.
- Shared interceptors running the wrong number of times.
- Deadlines and statuses of each service affecting one another.
- Channel shutdown triggered prematurely by a gateway.

You can use a test server or a Spring application context on a random port. If the starter manages the server, retrieve the port through the starter's test mechanism rather than starting a competing server on the same port.

## 14. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Method not found on stub | Using a stub for a different service | Choose the generated stub for the right service |
| Stub calls the wrong endpoint | Injected the wrong channel or qualifier | Use clear channel bean names and qualifiers |
| Too many connections created | Creating a channel per service despite identical target | Share a channel when security/transport match |
| Two services needing different TLS identities share a channel | Picking channels solely by host/port | Split channels along security boundaries |
| Metrics duplicated | Interceptor attached at multiple layers | Standardize where channels are wrapped |
| One service's deadline affects another | Mutating shared configuration | Use derived stubs per call |
| Gateway closes a shared channel | Confusion over lifecycle ownership | Only the channel owner shuts down |
| Unit tests pass but routing fails | Only mocking gateways | Add integration tests against a real server |
| Application service depends too heavily on generated classes | Calling gRPC directly everywhere | Consider per-service gateways |
| Ambiguous bean injection | Multiple channels or stubs of the same type | Use bean names and Qualifier |

## 15. Hands-On Exercise

**Scenario:** A Spring application needs to call three services on the backend: ProductCatalog to read product names, InventoryService to fetch stock quantities, and PricingService to calculate prices. Catalog and Inventory share the same TLS identity; Pricing requires a different endpoint and client certificate.

Complete the following:

1. Create two channel beans: one shared channel for Catalog/Inventory and one separate channel for Pricing.
2. Create separate generated stubs for each service from the appropriate channel.
3. Use bean names and Qualifiers to inject the right channels/stubs.
4. Create ProductAvailabilityService calling Catalog and Inventory; create separate gateways if needed to isolate generated APIs.
5. Choose blocking/async/future stubs based on each RPC's cardinality and execution model.
6. Apply distinct deadlines per latency budget; never mutate base stubs.
7. Attach shared tracing/metrics interceptors for Catalog/Inventory and a separate policy for Pricing.
8. Test all three services, verifying full method paths, responses, and security identities.
9. Close the Spring context and verify each channel is shut down by its proper owner.

**Completion criteria:** each generated service has the right stub type; services sharing target/security policy can share a channel; Pricing is isolated on its own channel; the application service calls the right dependencies; lifecycle, deadlines, and interceptors do not leak across services.

## 16. Takeaways

Each Protobuf service generates its own set of stubs with distinct methods and full method paths. Create the right service stub from a Channel; multiple services can share one ManagedChannel when they share target, TLS identity, and transport policy. In Spring, register separate stub beans, use qualifiers when multiple channels exist, and inject them into application services or per-service-boundary gateways. Choose blocking, async, or future stubs based on cardinality; keep base stubs immutable and configure deadlines/credentials per call. Only split channels when target, security, or lifecycle requires isolation. The channel owner is responsible for shutdown; shared stubs and gateways must never close the transport themselves.
