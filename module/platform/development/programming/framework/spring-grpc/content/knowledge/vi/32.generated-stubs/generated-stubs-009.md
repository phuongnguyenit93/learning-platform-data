# Stub cho từng service

## 1. Mục tiêu

Một server gRPC thường cung cấp nhiều service, chẳng hạn Catalog, Inventory, Pricing và Order. Mỗi service có contract Protobuf, service descriptor và các RPC method riêng. Ở phía client, gRPC Java sinh một nhóm stub riêng cho từng service. Ứng dụng tạo stub từ channel phù hợp rồi dùng stub đó để gọi các method thuộc service tương ứng.

**Stub cho từng service** là cách tổ chức client theo đúng ranh giới service trong Protobuf: mỗi generated service có stub type riêng, còn các stub có thể dùng chung một ManagedChannel nếu chúng cùng gọi một target và có chung cấu hình kết nối/bảo mật.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa Protobuf service, generated stub và full method path.
- Tạo stub riêng cho nhiều service từ cùng một channel.
- Chọn blocking, asynchronous hoặc future stub theo nhu cầu của từng service.
- Inject nhiều stub có kiểu khác nhau vào một Spring application service.
- Dùng qualifier và gateway để tránh nhầm lẫn khi cấu hình nhiều client.
- Quyết định khi nào các service dùng chung channel và khi nào cần channel riêng.
- Áp dụng interceptor, credentials, deadline và lifecycle đúng phạm vi.
- Kiểm thử việc gọi đúng service khi nhiều stub cùng dùng một target.

## 2. Mỗi Protobuf service sinh một bộ stub riêng

Giả sử backend cung cấp hai service:

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

gRPC Java plugin sinh class ProductCatalogGrpc và InventoryServiceGrpc, mỗi class có các factory method tạo stub tương ứng:

```java
ProductCatalogGrpc.ProductCatalogBlockingStub catalogStub =
        ProductCatalogGrpc.newBlockingStub(channel);

InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub =
        InventoryServiceGrpc.newBlockingStub(channel);
```

ProductCatalogGrpc chỉ chứa API gọi các method của ProductCatalog; InventoryServiceGrpc chứa API của InventoryService. Mỗi stub có kiểu Java riêng và method riêng. Không thể gọi getStock() qua catalogStub vì method đó thuộc service khác.

Stub được gắn với service descriptor và channel. Khi gọi method, generated code tạo RPC call dùng full method path của service tương ứng, ví dụ:

```text
/catalog.v1.ProductCatalog/GetProduct
/inventory.v1.InventoryService/GetStock
```

Package Protobuf, service name và method name quyết định full method path. java_package quyết định package Java của generated class, không quyết định route trên wire.

## 3. Nhiều service có thể dùng chung một channel

Nếu hai service được phục vụ bởi cùng một gRPC endpoint và dùng cùng transport/security configuration, client thường chỉ cần một ManagedChannel:

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

Hai stub khác kiểu nhưng dùng cùng channel. gRPC định tuyến từng call dựa trên full method path, vì vậy channel không cần một kết nối riêng cho mỗi service. Nhiều RPC có thể multiplex trên cùng HTTP/2 connection.

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

Việc dùng chung channel không làm các service nhập thành một service. Mỗi stub vẫn có method descriptor, request/response type, full method path và generated API riêng.

Không tạo một channel cho mỗi generated stub theo thói quen. Channel quản lý target, name resolution, load balancing, transport và kết nối; stub mô tả service API cần gọi qua channel đó.

## 4. Khi nào cần channel riêng?

Chỉ dùng chung channel khi các service thực sự có chung đích kết nối và chính sách transport. Tạo channel riêng khi có ranh giới cần cô lập:

| Điều kiện | Cách tổ chức |
|---|---|
| Catalog và Inventory cùng host/port, cùng TLS identity | Có thể dùng chung channel |
| Pricing nằm ở cluster/endpoint khác | Channel riêng cho Pricing |
| Một service dùng mTLS client certificate khác | Channel riêng với TLS identity tương ứng |
| Cần trust store hoặc authority khác | Channel riêng |
| Cần cô lập load balancing, retry policy hoặc lifecycle | Cân nhắc channel riêng |
| Nhiều service chỉ khác RPC method nhưng cùng endpoint | Dùng chung channel, tạo stub riêng |

Đừng tạo channel riêng chỉ vì tên service khác nhau. Ngược lại, đừng ép các service khác security boundary vào cùng channel chỉ để giảm số bean.

Channel thường được chia sẻ theo target và connection policy, không nhất thiết theo tên domain hoặc tên generated class. Quyết định phải dựa vào endpoint, TLS, identity, load balancing và lifecycle.

## 5. Tạo Spring bean cho từng service stub

Với một channel dùng chung, cấu hình có thể tạo nhiều bean stub có kiểu khác nhau:

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

Spring phân biệt hai stub bằng kiểu bean. @Qualifier trên channel làm rõ channel nào được dùng nếu ứng dụng có nhiều ManagedChannel bean.

Khi có nhiều bean cùng kiểu stub, đặt tên bean và dùng qualifier khi inject. Không dựa vào thứ tự khai báo bean hoặc giả định Spring sẽ luôn chọn đúng một bean trong số nhiều candidate.

Một số Spring gRPC starter có client factory, channel builder hoặc auto-configuration riêng. Khi dự án dùng các cơ chế đó, hãy đăng ký generated stub theo API của starter và để starter quản lý channel lifecycle. Đoạn cấu hình trên minh họa mô hình bean cơ bản; không tạo thêm channel cạnh channel mà starter đã sở hữu.

## 6. Inject nhiều stub vào application service

Một use case có thể cần gọi nhiều service:

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

Application service dùng đúng stub theo service mà nó cần gọi. Mỗi request Protobuf được tạo riêng; mỗi stub dẫn xuất có deadline riêng. Base stub được inject vẫn bất biến và có thể dùng chung giữa nhiều lần gọi.

Ví dụ trên gọi tuần tự vì kết quả Product và Stock được ghép ở cuối. Nếu hai call độc lập và latency quan trọng, có thể thực hiện bất đồng bộ bằng async/future stub rồi kết hợp kết quả. Khi làm vậy, phải có deadline tổng cho use case, giới hạn concurrency và xử lý lỗi/cancellation nhất quán.

## 7. Một service có thể có nhiều loại stub

Mỗi generated service thường cung cấp các factory method cho blocking, async và future stub. Chúng cùng đại diện cho một service API nhưng khác execution model:

```java
var blockingCatalog =
        ProductCatalogGrpc.newBlockingStub(channel);

var asyncCatalog =
        ProductCatalogGrpc.newStub(channel);

var futureCatalog =
        ProductCatalogGrpc.newFutureStub(channel);
```

Chọn theo cardinality và cách xử lý:

| RPC cardinality | Blocking stub | Async stub | Future stub |
|---|---|---|---|
| Unary | Trả response trực tiếp | StreamObserver nhận response | ListenableFuture<Response> |
| Server streaming | Trả Iterator<Response> | StreamObserver<Response> | Không hỗ trợ |
| Client streaming | Không có API blocking streaming tương đương trong generated blocking stub | Trả request StreamObserver | Không hỗ trợ |
| Bidirectional streaming | Không hỗ trợ kiểu blocking hai chiều | Request/response observer | Không hỗ trợ |

Không cần tạo channel mới khi tạo một loại stub khác. Blocking, async và future stub có thể cùng dùng một channel nếu target và transport policy giống nhau.

Một service client có thể cung cấp cả blocking và async gateway, nhưng nên chọn API phù hợp với execution model của application. Không inject cả ba loại stub vào mọi bean nếu use case chỉ dùng một loại.

## 8. Tách gateway theo service boundary

Khi application service có quá nhiều generated type hoặc xử lý status lặp lại, tạo gateway riêng cho từng dependency:

```java
public interface CatalogClient {
    ProductDetails getProduct(String productId);
}

public interface InventoryClient {
    int getAvailableQuantity(String productId, String warehouseId);
}
```

Gateway Catalog:

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

Gateway Inventory có thể thực hiện mapping tương tự. Application service khi đó inject CatalogClient và InventoryClient, không cần biết Protobuf package, generated stub hoặc gRPC status cụ thể.

Gateway theo service boundary hữu ích khi:

- Nhiều use case cùng gọi một dependency.
- Cần mapping status thống nhất.
- Cần tách generated API khỏi domain/application model.
- Muốn mock dependency trong unit test.
- Contract của một service có thể thay đổi độc lập.

Với ứng dụng nhỏ, inject trực tiếp stub có thể đủ. Tạo gateway khi nó làm rõ ranh giới hoặc loại bỏ logic lặp; không tạo thêm lớp chỉ để chuyển tiếp một lời gọi không có xử lý.

## 9. Deadline và call options theo từng service

Các service có latency budget khác nhau. Catalog có thể cần trả thông tin nhanh, còn một phép tính Pricing có thể cần thời gian dài hơn. Giữ base stub dùng chung và áp dụng deadline cho từng call:

```java
Product product = catalogStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .getProduct(productRequest);

PriceQuote quote = pricingStub
        .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
        .calculatePrice(priceRequest);
```

Deadline phải nằm trong budget còn lại của request inbound. Nếu application service có tổng budget 1 giây và đã dùng 300 ms cho Catalog, không thể cấp cho Pricing 900 ms mà vẫn kỳ vọng use case hoàn tất trong 1 giây.

Các call options khác cũng có thể khác theo service hoặc call:

- withWaitForReady() nếu call có thể chờ channel sẵn sàng trong deadline.
- withCallCredentials(...) nếu service cần credential cụ thể.
- withCompression(...) nếu payload và server hỗ trợ.
- withDeadlineAfter(...) theo latency budget.

Stub immutable nên mỗi cấu hình tạo ra stub dẫn xuất; không làm thay đổi base stub được chia sẻ.

## 10. Interceptor chung và interceptor riêng cho service

Nếu mọi service cùng endpoint dùng chung tracing/metrics policy, bọc channel một lần rồi tạo các stub từ channel wrapper:

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

Nếu Catalog và Inventory cần interceptor khác nhau, có thể tạo channel wrapper riêng trên cùng channel gốc:

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

Hai wrapper vẫn dùng chung transport bên dưới; chúng không sở hữu hai kết nối độc lập. Chỉ tạo wrapper riêng khi cần policy khác nhau. Tránh đăng ký cùng interceptor ở cả channel builder và wrapper khiến một RPC bị ghi span hoặc metric hai lần.

Interceptor có thể kiểm tra full method name để áp dụng policy theo service/method. Không dùng mutable instance field để giữ request ID, tenant hoặc token vì interceptor thường được chia sẻ giữa các call đồng thời.

## 11. Credentials và security boundary

Các service cùng endpoint có thể dùng chung TLS channel nếu cùng server identity và trust policy. Tuy nhiên, call credentials hoặc authorization vẫn có thể khác theo service:

- Catalog chỉ cho phép đọc thông tin sản phẩm.
- Inventory có thể cần quyền xem tồn kho theo warehouse.
- Pricing có thể yêu cầu service identity hoặc scope riêng.

Không xem việc dùng chung channel là dùng chung quyền. Authentication xác định principal; authorization phải kiểm tra principal có quyền gọi full method path và truy cập resource cụ thể.

Nếu hai service yêu cầu client certificate, trust store hoặc authority khác nhau, tạo channel riêng để giữ đúng security boundary. Không cố thay TLS identity của một channel đã được tạo theo từng RPC bằng metadata tùy ý.

## 12. Quản lý lifecycle khi nhiều stub cùng dùng channel

Khi nhiều stub cùng sử dụng một ManagedChannel, channel chỉ được shutdown một lần bởi component sở hữu nó:

```java
channel.shutdown();
if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
```

Stub không sở hữu channel và không có trách nhiệm đóng transport. Nếu ProductCatalogClient và InventoryClient cùng nhận channel qua constructor, cả hai không được tự shutdown channel khi bean của chúng bị hủy.

Trong Spring:

- Channel bean được tạo tại configuration hoặc bởi starter.
- Stub bean phụ thuộc vào channel bean.
- Gateway/application service phụ thuộc vào stub hoặc client interface.
- Application context đóng channel theo lifecycle owner.

Nếu mỗi service có channel riêng, mỗi channel phải có owner và shutdown policy riêng. Đặt tên bean rõ ràng như catalogChannel, inventoryChannel và dùng @Qualifier để tránh inject nhầm.

## 13. Kiểm thử stub cho từng service

Kiểm thử nên xác minh mỗi stub gọi đúng service/method, ngay cả khi chúng dùng chung channel.

### Unit test application orchestration

Nếu application service inject gateway interface, mock từng dependency:

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

Test này xác minh orchestration, không xác minh gRPC routing.

### Integration test trên cùng channel

Khởi động một test server đăng ký cả ProductCatalog và InventoryService. Tạo hai stub từ cùng channel, gọi từng method và xác minh response từ đúng service.

Test cần phát hiện:

- Stub Catalog không gọi nhầm method/service Inventory.
- Full method path và service registration đúng.
- Cả hai service dùng chung channel vẫn hoạt động đồng thời.
- Interceptor chung được chạy đúng số lần.
- Deadline và status của mỗi service được xử lý độc lập.
- Shutdown channel không bị một gateway thực hiện quá sớm.

Có thể dùng server test hoặc Spring application context với port ngẫu nhiên. Nếu starter quản lý server, lấy port từ cơ chế test của starter thay vì tạo một server cạnh tranh trên cùng port.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy method trên stub | Đang dùng stub của service khác | Chọn generated stub đúng service |
| Stub gọi sai endpoint | Inject nhầm channel hoặc qualifier | Đặt tên channel và qualifier rõ ràng |
| Tạo quá nhiều kết nối | Tạo channel cho mỗi service dù cùng target | Dùng chung channel khi security/transport giống nhau |
| Hai service cần TLS identity khác nhau nhưng dùng chung channel | Chọn channel chỉ theo host/port | Tách channel theo security boundary |
| Metrics bị nhân đôi | Interceptor gắn ở nhiều lớp | Chuẩn hóa vị trí bọc channel |
| Deadline service này ảnh hưởng service khác | Thay đổi shared configuration | Dùng stub dẫn xuất theo từng call |
| Gateway đóng channel dùng chung | Nhầm quyền sở hữu lifecycle | Chỉ channel owner shutdown |
| Unit test pass nhưng route sai | Chỉ mock gateway | Bổ sung integration test gọi server thật |
| Application service phụ thuộc quá nhiều generated class | Gọi gRPC trực tiếp ở nhiều nơi | Cân nhắc gateway riêng cho từng service |
| Bean injection mơ hồ | Nhiều channel hoặc stub cùng kiểu | Dùng bean name và Qualifier |

## 15. Bài tập thực hành

**Tình huống:** Một Spring application cần gọi ba service cùng backend endpoint: ProductCatalog để đọc tên sản phẩm, InventoryService để lấy số lượng và PricingService để tính giá. Catalog và Inventory dùng cùng TLS identity; Pricing yêu cầu một endpoint và client certificate khác.

Hãy thực hiện:

1. Tạo hai channel bean: một channel dùng chung cho Catalog/Inventory và một channel riêng cho Pricing.
2. Tạo generated stub riêng cho từng service từ channel phù hợp.
3. Dùng tên bean và Qualifier để inject đúng channel/stub.
4. Tạo ProductAvailabilityService gọi Catalog và Inventory; tạo gateway riêng nếu cần cô lập generated API.
5. Chọn blocking/async/future stub theo cardinality và execution model của từng RPC.
6. Áp dụng deadline riêng theo latency budget; không thay đổi base stub.
7. Gắn tracing/metrics interceptor chung cho Catalog/Inventory và policy riêng cho Pricing.
8. Kiểm thử cả ba service, xác minh full method path, response và security identity.
9. Đóng Spring context và xác minh mỗi channel được shutdown bởi đúng owner.

**Tiêu chí hoàn thành:** mỗi generated service có stub đúng kiểu; service cùng target/security policy có thể dùng chung channel; Pricing được cô lập bằng channel riêng; application service gọi đúng dependency; lifecycle, deadline và interceptor không rò giữa các service.

## 16. Ghi nhớ

Mỗi Protobuf service sinh bộ generated stub riêng với method và full method path riêng. Tạo stub đúng service từ Channel; nhiều service có thể dùng chung một ManagedChannel nếu cùng target, TLS identity và transport policy. Trong Spring, đăng ký bean stub riêng, dùng qualifier khi có nhiều channel và inject vào application service hoặc gateway theo service boundary. Chọn blocking, async hoặc future stub theo cardinality; giữ base stub immutable và đặt deadline/credentials theo call. Chỉ tách channel khi target, security hoặc lifecycle cần cô lập. Channel owner chịu trách nhiệm shutdown; các stub và gateway dùng chung không tự đóng transport.
