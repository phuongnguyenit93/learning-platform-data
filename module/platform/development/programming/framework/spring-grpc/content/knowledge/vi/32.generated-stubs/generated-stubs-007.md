# Tạo stub từ channel

## 1. Mục tiêu

Trong gRPC Java, file Protobuf định nghĩa service và RPC method; code generation tạo ra các lớp service cùng những loại client stub để gọi chúng. Khi ứng dụng đã có một Channel, client tạo stub từ channel đó để gọi method được sinh. Trong Spring gRPC, channel thường được quản lý như một dependency dùng chung, còn stub được inject vào gateway hoặc service cần gọi RPC.

**Tạo stub từ channel** là bước kết nối generated service API với một đích gRPC cụ thể. Channel cung cấp khả năng gửi RPC qua transport; stub cung cấp kiểu gọi và method tương ứng với service trong file proto.

Sau bài học, bạn có thể:

- Tạo blocking, asynchronous và future stub từ cùng một channel.
- Chọn loại stub theo cardinality của RPC và cách xử lý kết quả.
- Phân biệt trách nhiệm của Channel, ManagedChannel, stub và từng RPC call.
- Tái sử dụng channel/stub an toàn trong ứng dụng đa luồng.
- Tạo stub dẫn xuất với deadline, credentials hoặc call options riêng.
- Bọc channel bằng client interceptor trước khi tạo stub.
- Quản lý channel lifecycle trong Spring và tránh đóng channel sau mỗi request.

## 2. Từ generated service đến stub

Giả sử Protobuf định nghĩa service:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc WatchInventory(WatchInventoryRequest)
      returns (stream InventoryUpdate);
  rpc UploadImages(stream ImageChunk) returns (UploadSummary);
  rpc SyncCatalog(stream CatalogEvent) returns (stream SyncResult);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string name = 2;
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated Product products = 1;
}

message WatchInventoryRequest {
  string warehouse_id = 1;
}

message InventoryUpdate {
  string product_id = 1;
  int32 available_quantity = 2;
}

message ImageChunk {
  bytes content = 1;
}

message UploadSummary {
  int32 stored_images = 1;
}

message CatalogEvent {
  string event_id = 1;
}

message SyncResult {
  string event_id = 1;
  bool accepted = 2;
}
```

gRPC Java plugin sinh lớp CatalogServiceGrpc. Lớp này cung cấp các factory method tạo stub:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub =
        CatalogServiceGrpc.newBlockingStub(channel);

CatalogServiceGrpc.CatalogServiceStub asyncStub =
        CatalogServiceGrpc.newStub(channel);

CatalogServiceGrpc.CatalogServiceFutureStub futureStub =
        CatalogServiceGrpc.newFutureStub(channel);
```

Các tên cụ thể được sinh từ service name. newBlockingStub, newStub và newFutureStub nhận một io.grpc.Channel; vì vậy có thể truyền ManagedChannel hoặc channel wrapper do interceptor tạo ra.

Stub không tự định nghĩa endpoint. Nó dùng channel được truyền vào để gửi method có full path tương ứng, ví dụ /catalog.v1.CatalogService/GetProduct.

## 3. Phân biệt Channel, ManagedChannel và Stub

| Thành phần | Trách nhiệm | Vòng đời |
|---|---|---|
| Channel | Abstraction để gửi RPC tới service | Do transport hoặc wrapper cung cấp |
| ManagedChannel | Channel có khả năng quản lý kết nối, name resolution, load balancing và shutdown | Thường sống cùng application hoặc dependency |
| Generated stub | Gắn service descriptor và kiểu gọi vào channel | Có thể tái sử dụng và tạo bản dẫn xuất |
| RPC call | Một lần gọi method cụ thể với request và call options | Kết thúc khi response/error hoàn tất |

Channel quyết định target, transport và các chính sách kết nối. Stub quyết định service/method và kiểu gọi. Deadline, credentials hoặc compression có thể được đặt ở stub dẫn xuất hoặc call options tương ứng.

Tạo một stub không có nghĩa là tạo một TCP connection mới cho mỗi stub. Nhiều stub có thể dùng chung một channel và nhiều RPC có thể multiplex trên cùng HTTP/2 connection. Channel thường là đối tượng tốn chi phí hơn; không tạo/đóng channel cho từng request nghiệp vụ.

## 4. Tạo ManagedChannel

Trong một ứng dụng Java thuần, có thể tạo channel bằng builder:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .build();
```

Khi phát triển local, server plaintext có thể dùng:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .usePlaintext()
        .build();
```

Chỉ chọn usePlaintext() khi môi trường thực sự không dùng TLS và được cấu hình có chủ đích. Với production, cấu hình TLS/trust và xác thực service theo chính sách của hệ thống.

ManagedChannelBuilder trả về channel quản lý kết nối. Việc tạo channel thường lazy: gọi build() tạo đối tượng và cấu hình channel; kết nối thực tế được thiết lập khi có nhu cầu RPC hoặc channel cần kết nối. Không dùng việc tạo stub thành công để kết luận server đang reachable.

## 5. Tạo blocking stub

Blocking stub phù hợp với unary RPC hoặc server-streaming RPC khi caller chấp nhận chờ kết quả trên thread hiện tại.

```java
CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel);

GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("product-42")
        .build();

Product product = stub.getProduct(request);
```

Với unary RPC, method trả về response sau khi call hoàn tất hoặc ném StatusRuntimeException nếu call thất bại.

Với server streaming, blocking stub thường trả về Iterator để caller đọc từng response:

```java
Iterator<InventoryUpdate> updates =
        stub.watchInventory(
                WatchInventoryRequest.newBuilder()
                        .setWarehouseId("warehouse-1")
                        .build());

while (updates.hasNext()) {
    InventoryUpdate update = updates.next();
    process(update);
}
```

Không gọi blocking stub trên event-loop thread hoặc thread cần phục vụ nhiều request đồng thời nếu thời gian chờ có thể làm nghẽn hệ thống. Với Spring MVC, cần cân nhắc thread pool và giới hạn concurrency; với reactive pipeline, dùng API bất đồng bộ hoặc tích hợp reactive phù hợp.

## 6. Tạo asynchronous stub

Asynchronous stub được tạo bằng newStub(channel). Nó dùng StreamObserver để nhận response và lỗi, đồng thời hỗ trợ các kiểu RPC streaming:

```java
CatalogServiceGrpc.CatalogServiceStub stub =
        CatalogServiceGrpc.newStub(channel);

stub.getProduct(
        GetProductRequest.newBuilder()
                .setProductId("product-42")
                .build(),
        new StreamObserver<>() {
            @Override
            public void onNext(Product product) {
                process(product);
            }

            @Override
            public void onError(Throwable error) {
                handleGrpcError(error);
            }

            @Override
            public void onCompleted() {
                finish();
            }
        });
```

Với unary RPC, observer nhận một response rồi onCompleted(), hoặc nhận onError(). Với server-streaming, onNext() có thể được gọi nhiều lần trước onCompleted().

Với client-streaming hoặc bidirectional streaming, method trả về một StreamObserver để client gửi request message:

```java
StreamObserver<UploadSummary> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary summary) {
                recordUpload(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleGrpcError(error);
            }

            @Override
            public void onCompleted() {
                finishUpload();
            }
        };

StreamObserver<ImageChunk> requestObserver =
        stub.uploadImages(responseObserver);

requestObserver.onNext(
        ImageChunk.newBuilder().setContent(firstChunk).build());
requestObserver.onNext(
        ImageChunk.newBuilder().setContent(secondChunk).build());
requestObserver.onCompleted();
```

Sau onCompleted() hoặc onError(), client không gửi thêm message trên observer đó. Với streaming lớn, cần thiết kế flow control, giới hạn buffer, cancellation và backpressure; không gom toàn bộ stream vào memory chỉ vì API observer cho phép gọi onNext() liên tiếp.

## 7. Tạo future stub

Future stub được tạo bằng newFutureStub(channel) và phù hợp với unary RPC khi caller muốn nhận kết quả dưới dạng ListenableFuture:

```java
CatalogServiceGrpc.CatalogServiceFutureStub stub =
        CatalogServiceGrpc.newFutureStub(channel);

ListenableFuture<Product> result = stub.getProduct(
        GetProductRequest.newBuilder()
                .setProductId("product-42")
                .build());
```

Caller có thể kết hợp future với callback hoặc executor thay vì block ngay:

```java
Futures.addCallback(
        result,
        new FutureCallback<>() {
            @Override
            public void onSuccess(Product product) {
                process(product);
            }

            @Override
            public void onFailure(Throwable error) {
                handleGrpcError(error);
            }
        },
        callbackExecutor);
```

Future stub chỉ hỗ trợ unary RPC. Với server-streaming, client-streaming hoặc bidirectional streaming, dùng asynchronous stub. ListenableFuture thuộc Guava; module sử dụng future stub cần dependency phù hợp và nên xác định executor cho callback.

## 8. Chọn loại stub theo cardinality

| RPC cardinality | Blocking stub | Async stub | Future stub |
|---|---|---|---|
| Unary | Trả response trực tiếp | Một onNext, sau đó complete | ListenableFuture<Response> |
| Server streaming | Iterator<Response> | StreamObserver<Response> | Không hỗ trợ |
| Client streaming | Không hỗ trợ | Trả request StreamObserver | Không hỗ trợ |
| Bidirectional streaming | Không hỗ trợ | Request và response đều qua observer | Không hỗ trợ |

Hãy chọn stub dựa trên kiểu RPC và mô hình xử lý của caller, không dựa trên việc một loại stub có vẻ ngắn code hơn. Một service có thể dùng nhiều loại stub trên cùng channel cho các method khác nhau.

## 9. Stub là immutable và có thể tái sử dụng

Generated stub trong gRPC Java là immutable. Các phương thức cấu hình như withDeadlineAfter() tạo một stub mới có call options đã thay đổi; chúng không sửa stub gốc:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub baseStub =
        CatalogServiceGrpc.newBlockingStub(channel);

var fastCallStub = baseStub.withDeadlineAfter(
        300, TimeUnit.MILLISECONDS);

var normalCallStub = baseStub.withDeadlineAfter(
        2, TimeUnit.SECONDS);
```

Hai stub dẫn xuất dùng chung channel nhưng có deadline khác nhau. Có thể lưu base stub trong singleton gateway và tạo bản dẫn xuất cho mỗi nhóm call cần policy riêng.

Do stub immutable và channel thread-safe, có thể tái sử dụng chúng giữa nhiều thread. Không đặt mutable request-specific state vào field của gateway hoặc interceptor dùng chung. Mỗi RPC nên có request, observer và call options riêng.

## 10. Cấu hình call options cho stub

### Deadline

```java
var stubWithDeadline = baseStub.withDeadlineAfter(
        700, TimeUnit.MILLISECONDS);
```

Deadline giới hạn thời gian call được phép hoàn tất. Nên đặt deadline cho RPC phụ thuộc vào latency budget của luồng nghiệp vụ; không dựa vào timeout mặc định vô hạn.

### Wait for ready

```java
var waitForReadyStub = baseStub.withWaitForReady();
```

withWaitForReady() cho phép call chờ channel sẵn sàng theo deadline thay vì fail ngay khi channel tạm thời chưa ready. Nó không bảo đảm RPC thành công và không thay thế retry policy.

### Call credentials

```java
var authenticatedStub = baseStub.withCallCredentials(callCredentials);
```

Call credentials gắn thông tin xác thực cho RPC. Credential cần được cấp phát và refresh theo chính sách bảo mật; không hard-code token vào generated stub hoặc source code.

### Compression

```java
var compressedStub = baseStub.withCompression("gzip");
```

Chỉ bật compression khi client/server hỗ trợ và payload thực sự có lợi. Compression tiêu tốn CPU, có thể tăng latency với payload nhỏ hoặc dữ liệu vốn đã nén.

Các phương thức cấu hình trả về stub cùng kiểu cụ thể. Có thể nối nhiều cấu hình:

```java
var callStub = baseStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .withWaitForReady()
        .withCallCredentials(callCredentials);
```

Call options áp dụng cho call được tạo từ stub dẫn xuất đó. Không thay đổi base stub dùng chung theo từng request.

## 11. Gắn client interceptor trước khi tạo stub

Interceptor xử lý concern xuyên suốt như tracing, metrics hoặc metadata. Có thể bọc channel bằng ClientInterceptors.intercept() rồi tạo stub từ channel đã bọc:

```java
Channel interceptedChannel = ClientInterceptors.intercept(
        channel,
        tracingInterceptor,
        metricsInterceptor);

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(interceptedChannel);
```

Interceptor được gọi trong quá trình tạo và thực hiện RPC; nó không thay thế generated stub. Stub vẫn xác định method và request/response type. Channel wrapper thêm hành vi chung cho các call đi qua nó.

Thứ tự interceptor có thể ảnh hưởng thứ tự xử lý metadata và call lifecycle. Hãy thống nhất thứ tự trong cấu hình, tránh đăng ký cùng interceptor ở cả channel builder và wrapper nếu điều đó khiến metrics/tracing bị ghi hai lần.

Nếu chỉ cần gắn metadata cho một nhóm call, có thể dùng interceptor riêng hoặc call credentials phù hợp. Không lưu request-specific metadata trong field mutable của interceptor singleton; tạo metadata/call state theo từng call.

## 12. Tổ chức channel và stub trong Spring

Trong Spring, channel nên là bean có vòng đời do application context quản lý. Gateway có thể nhận channel qua constructor và tạo stub một lần:

```java
@Configuration
public class CatalogClientConfiguration {

    @Bean(name = "catalogChannel", destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }
}
```

Gateway:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub baseStub;

    public CatalogGateway(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        this.baseStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    public Product getProduct(String productId) {
        var request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();

        return baseStub
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getProduct(request);
    }
}
```

Ví dụ minh họa channel TLS tới một dependency. Tên host, port, trust configuration và cách Spring gRPC starter quản lý channel phải phù hợp dự án. Một số starter có cơ chế auto-configuration/channel factory riêng; khi dùng starter đó, hãy tuân theo lifecycle và cấu hình được hỗ trợ, tránh tạo channel thứ hai tới cùng target mà không có lý do.

destroyMethod = "shutdown" yêu cầu Spring gọi shutdown khi bean bị hủy. Với ứng dụng cần graceful shutdown, có thể quản lý bước awaitTermination() và gọi shutdownNow() khi hết thời gian chờ. Không đóng channel trong method getProduct() hoặc sau từng request.

## 13. Một channel hay nhiều channel?

Tái sử dụng một channel cho nhiều stub khi chúng cùng target và cùng transport/security configuration:

- Nhiều service trên cùng server có thể dùng chung channel.
- Nhiều loại stub của cùng service có thể dùng chung channel.
- Client v1/v2 có thể dùng chung channel nếu target và TLS identity giống nhau.
- Các call có deadline hoặc credentials khác nhau có thể dùng stub dẫn xuất trên channel chung.

Tạo channel riêng khi có lý do rõ ràng:

- Target hoặc cluster khác nhau.
- TLS trust, client certificate hoặc identity khác nhau.
- Cần cô lập connection/load balancing hoặc quota.
- Có chính sách lifecycle riêng.

Không tạo một channel cho mỗi user hoặc mỗi RPC. Quá nhiều channel làm tăng socket, thread, connection management và chi phí name resolution.

## 14. Đóng channel đúng cách

Stub không có phương thức close() vì stub không sở hữu transport. ManagedChannel là đối tượng cần shutdown:

```java
channel.shutdown();

if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
```

shutdown() ngừng nhận call mới và cho các call đang chạy cơ hội hoàn tất. shutdownNow() yêu cầu hủy call đang hoạt động. Thời gian chờ phải phù hợp với thời gian shutdown của ứng dụng.

Nếu gateway tạo stub từ channel do Spring quản lý, gateway không được tự shutdown channel. Chỉ component sở hữu channel lifecycle mới đóng nó. Điều này tránh một bean làm hỏng các gateway khác đang dùng cùng channel.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy CatalogServiceGrpc | Chưa chạy gRPC Java code generator | Cấu hình protoc-gen-grpc-java |
| RPC blocking làm nghẽn thread | Dùng blocking stub trên event loop hoặc pool nhỏ | Chuyển sang async hoặc điều chỉnh concurrency |
| Future stub không có method streaming | Future stub chỉ hỗ trợ unary | Dùng asynchronous stub |
| Mỗi request lại tạo socket/channel | Tạo và đóng ManagedChannel trong gateway method | Quản lý channel dùng chung theo target |
| Stub của request này ảnh hưởng request khác | Dùng mutable state chung thay vì stub dẫn xuất | Dùng immutable stub và call options riêng |
| Call chờ quá lâu | Không đặt deadline | Dùng withDeadlineAfter() theo latency budget |
| withWaitForReady() vẫn timeout | Deadline hết hạn hoặc server không sẵn sàng | Đặt deadline hợp lý và xử lý status |
| Metrics/tracing bị nhân đôi | Interceptor đăng ký nhiều lớp | Kiểm tra channel wrapper và cấu hình |
| Channel bị đóng khi gateway khác đang dùng | Gateway tự shutdown dependency dùng chung | Chỉ owner của channel quản lý shutdown |
| Spring shutdown làm mất call đang chạy | Chỉ gọi shutdownNow quá sớm | Dùng graceful shutdown với thời gian chờ |

## 16. Bài tập thực hành

**Tình huống:** Một Spring service gọi Catalog qua gRPC. Ứng dụng cần unary GetProduct, server-streaming WatchInventory và client-streaming UploadImages. Các call phải dùng TLS, tracing interceptor và deadline khác nhau.

Hãy thực hiện:

1. Tạo một ManagedChannel bean tới Catalog với transport/security configuration phù hợp.
2. Tạo blocking stub cho GetProduct và future stub nếu luồng nghiệp vụ cần ListenableFuture.
3. Tạo asynchronous stub cho WatchInventory và UploadImages.
4. Bọc channel bằng tracing/metrics interceptor trước khi tạo stub.
5. Tái sử dụng channel cho các stub cùng target; không tạo channel theo từng RPC.
6. Dùng stub dẫn xuất với deadline phù hợp cho từng call.
7. Kiểm thử một unary call thành công, một server stream nhiều message và một client stream kết thúc đúng observer lifecycle.
8. Kiểm thử deadline exceeded và channel shutdown khi Spring application context đóng.
9. Xác minh interceptor không ghi metadata hoặc metric trùng và không giữ state giữa các call.

**Tiêu chí hoàn thành:** mỗi loại RPC dùng stub phù hợp; các stub dùng channel được quản lý tập trung; call options độc lập; interceptor được áp dụng nhất quán; channel chỉ được shutdown bởi owner khi application dừng.

## 17. Ghi nhớ

Tạo stub bằng factory method của generated service, truyền vào một Channel hoặc ManagedChannel. Blocking stub phù hợp với unary/server-streaming theo kiểu chờ; asynchronous stub hỗ trợ cả bốn cardinality; future stub dành cho unary. Channel quản lý target và transport, còn stub là immutable client facade cho service API. Tái sử dụng channel và base stub; tạo stub dẫn xuất cho deadline, credentials hoặc call options riêng. Bọc channel bằng interceptor trước khi tạo stub nếu cần tracing/metrics chung. Trong Spring, để application context quản lý channel lifecycle và chỉ shutdown channel khi dependency owner dừng, không đóng channel sau từng RPC.
