# Lỗi status trong unary call

## 1. Status là kết quả kết thúc của một RPC

Một **unary RPC** gửi một request và nhận một response khi thành công. Ở tầng gRPC, mỗi lời gọi kết thúc bằng một **status**:

- `OK`: server hoàn tất thành công; client nhận đúng một response protobuf.
- Status khác `OK`: lời gọi kết thúc bằng lỗi; client không nhận response nghiệp vụ thành công.

Status gồm mã chuẩn, mô tả tùy chọn và có thể kèm metadata trong phần trailers. Trong gRPC Java, các kiểu thường gặp là `io.grpc.Status`, `StatusRuntimeException` và `StatusException`.

Status không phải field `error` trong response. Nếu server gọi `responseObserver.onError(...)`, client nhận lỗi RPC; server không nên gửi thêm response giả rồi kết thúc `OK`. Cách phân biệt này giúp client xử lý lỗi nhất quán dù server được viết bằng Java, Go, Python hay ngôn ngữ khác.

## 2. Chọn status code theo ý nghĩa lỗi

gRPC định nghĩa các mã status dùng chung. Chọn đúng mã quan trọng hơn việc viết description dài, vì client nên phân nhánh theo **code**.

| Status code | Khi dùng | Ví dụ trong unary RPC |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Dữ liệu request sai, độc lập với trạng thái hiện tại của hệ thống. | `product_id` rỗng hoặc số lượng âm. |
| `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại. | Không có sản phẩm với ID đã gửi. |
| `ALREADY_EXISTS` | Tạo tài nguyên bị trùng hoặc xung đột định danh. | Mã đơn hàng đã được sử dụng. |
| `UNAUTHENTICATED` | Caller chưa được xác thực hoặc credentials không hợp lệ. | Token thiếu, hết hạn hoặc không hợp lệ. |
| `PERMISSION_DENIED` | Caller đã xác thực nhưng không có quyền thực hiện thao tác. | Người dùng không được xem đơn hàng của tenant khác. |
| `FAILED_PRECONDITION` | Hệ thống chưa ở trạng thái cho phép thao tác. | Không thể hủy đơn đã giao. |
| `ABORTED` | Thao tác bị hủy do xung đột transaction hoặc concurrency. | Optimistic lock conflict khi cập nhật. |
| `OUT_OF_RANGE` | Giá trị nằm ngoài miền hợp lệ của thao tác. | Trang hoặc offset vượt phạm vi hỗ trợ. |
| `RESOURCE_EXHAUSTED` | Hết quota hoặc tài nguyên được cấp. | Vượt giới hạn request hoặc dung lượng. |
| `UNAVAILABLE` | Service hoặc dependency tạm thời không sẵn sàng. | Service đang khởi động hoặc mất kết nối dependency. |
| `DEADLINE_EXCEEDED` | Deadline của lời gọi đã hết. | Client không nhận kết quả trong thời hạn. |
| `CANCELLED` | Lời gọi bị caller hoặc context cha hủy. | Người dùng hủy thao tác đang chờ. |
| `UNIMPLEMENTED` | Method hoặc tính năng chưa được triển khai. | Client gọi RPC mà server chưa hỗ trợ. |
| `INTERNAL` | Lỗi nội bộ không mong đợi ở server. | Lỗi xử lý không được dự kiến. |
| `DATA_LOSS` | Dữ liệu bị mất hoặc hỏng nghiêm trọng. | Phát hiện bản ghi không thể đọc do corruption. |
| `UNKNOWN` | Không thể phân loại lỗi cụ thể. | Lớp trung gian không giữ được status gốc. |

Ba nhóm dễ nhầm:

- `INVALID_ARGUMENT`: request sai dù tài nguyên đang ở trạng thái nào.
- `FAILED_PRECONDITION`: request có thể hợp lệ, nhưng trạng thái hiện tại không cho phép thực hiện.
- `ABORTED`: xung đột khiến thao tác cần được điều phối hoặc chạy lại ở cấp cao hơn.

Ví dụ: `quantity = -1` là `INVALID_ARGUMENT`; hủy đơn đã giao là `FAILED_PRECONDITION`; cập nhật thất bại do optimistic lock conflict có thể là `ABORTED`.

Không dùng `INTERNAL` cho mọi lỗi nghiệp vụ. Cũng không trả `OK` cùng response chứa chuỗi `"error"` nếu hợp đồng đã quy định lỗi bằng gRPC status.

## 3. Ánh xạ lỗi nghiệp vụ thành status ở server Spring gRPC

Server nên chuyển lỗi ở ranh giới RPC: lỗi nghiệp vụ đã biết thành status phù hợp, còn lỗi ngoài dự kiến thành `INTERNAL`.

Ví dụ hợp đồng unary:

```proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.catalog.grpc";
option java_multiple_files = true;

service ProductQueryService {
  rpc GetProduct (GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
```

Ví dụ triển khai bằng Spring gRPC:

```java
package com.example.catalog.server;

import com.example.catalog.grpc.GetProductRequest;
import com.example.catalog.grpc.GetProductResponse;
import com.example.catalog.grpc.ProductQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.grpc.server.service.GrpcService;

import java.util.Optional;

@GrpcService
public class ProductQueryGrpcService
        extends ProductQueryServiceGrpc.ProductQueryServiceImplBase {

    private static final Logger log =
            LoggerFactory.getLogger(ProductQueryGrpcService.class);

    private final ProductCatalog catalog;

    public ProductQueryGrpcService(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {

        String productId = request.getProductId().trim();

        if (productId.isEmpty()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id không được để trống")
                    .asRuntimeException());
            return;
        }

        try {
            Optional<Product> found = catalog.findById(productId);

            if (found.isEmpty()) {
                observer.onError(Status.NOT_FOUND
                        .withDescription("Không tìm thấy sản phẩm")
                        .asRuntimeException());
                return;
            }

            Product product = found.get();
            observer.onNext(GetProductResponse.newBuilder()
                    .setProductId(product.id())
                    .setName(product.name())
                    .build());
            observer.onCompleted();

        } catch (SecurityException denied) {
            observer.onError(Status.PERMISSION_DENIED
                    .withDescription("Không có quyền xem sản phẩm")
                    .asRuntimeException());

        } catch (RuntimeException unexpected) {
            // Log exception đầy đủ ở server; không gửi stack trace cho client.
            log.error("Unexpected error in ProductQueryService/GetProduct",
                    unexpected);
            observer.onError(Status.INTERNAL
                    .withDescription("Không thể xử lý yêu cầu")
                    .asRuntimeException());
        }
    }
}
```

`ProductCatalog` và `Product` là các kiểu ứng dụng minh họa. Vòng đời terminal của observer:

- Thành công: gọi `onNext(response)` đúng một lần, sau đó `onCompleted()`.
- Thất bại: gọi `onError(status.asRuntimeException())` và kết thúc nhánh xử lý.
- Sau `onError`, không gọi `onNext` hoặc `onCompleted`.
- Không gọi nhiều terminal signal cho cùng một RPC.

`Status.INVALID_ARGUMENT`, `Status.NOT_FOUND` và các giá trị tương tự là status chuẩn. `withDescription(...)` thêm thông tin chẩn đoán ngắn gọn; description không phải mã máy đọc và không nên chứa SQL, stack trace, token, thông tin cá nhân hoặc chi tiết nội bộ.

### Không biến mọi exception thành cùng một status

Nếu tầng nghiệp vụ ném exception có ý nghĩa rõ ràng, adapter gRPC nên ánh xạ chúng theo hợp đồng:

| Exception ở application | Status gợi ý |
| --- | --- |
| `ProductNotFoundException` | `NOT_FOUND` |
| `InvalidProductQueryException` | `INVALID_ARGUMENT` |
| `ProductAccessDeniedException` | `PERMISSION_DENIED` |
| `ProductStateConflictException` | `FAILED_PRECONDITION` hoặc `ABORTED`, tùy nguyên nhân |
| Lỗi ngoài dự kiến | `INTERNAL` |

Có thể đặt logic ánh xạ trong helper hoặc component dùng chung nếu nhiều handler có cùng quy tắc. Interceptor phù hợp cho logging, metrics, tracing và xử lý xuyên suốt; không nên dùng interceptor để đoán ý nghĩa của mọi exception nghiệp vụ nếu thiếu ngữ cảnh của method.

## 4. Nhận và xử lý status ở blocking client

Khi unary RPC không kết thúc với `OK`, blocking stub ném `StatusRuntimeException`. Client nên đọc `getStatus().getCode()` để chuyển thành lỗi ứng dụng:

```java
package com.example.catalog.client;

import com.example.catalog.grpc.GetProductRequest;
import com.example.catalog.grpc.GetProductResponse;
import com.example.catalog.grpc.ProductQueryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryClient {

    private final ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub;

    public ProductQueryClient(
            ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public GetProductResponse getProduct(String productId) {
        try {
            return stub.getProduct(GetProductRequest.newBuilder()
                    .setProductId(productId)
                    .build());

        } catch (StatusRuntimeException failure) {
            Status.Code code = failure.getStatus().getCode();

            switch (code) {
                case NOT_FOUND ->
                        throw new ProductNotFoundException(productId, failure);
                case INVALID_ARGUMENT ->
                        throw new IllegalArgumentException(
                                "Thông tin sản phẩm không hợp lệ", failure);
                case UNAUTHENTICATED ->
                        throw new RemoteAuthenticationException(failure);
                case PERMISSION_DENIED ->
                        throw new ProductAccessDeniedException(failure);
                case FAILED_PRECONDITION, ABORTED ->
                        throw new ProductStateConflictException(failure);
                case DEADLINE_EXCEEDED ->
                        throw new RemoteCallTimeoutException(failure);
                case UNAVAILABLE, RESOURCE_EXHAUSTED ->
                        throw new RemoteServiceUnavailableException(failure);
                default ->
                        throw new RemoteGrpcException(
                                "Lời gọi ProductQueryService thất bại", failure);
            }
        }
    }
}
```

Các exception `ProductNotFoundException`, `RemoteAuthenticationException` và những kiểu tương tự là exception ứng dụng do dự án định nghĩa. Ví dụ minh họa **phân loại status**, không thực hiện retry. Chính sách retry cần được quyết định riêng theo method và tính idempotent.

Không phân nhánh bằng `failure.getStatus().getDescription()`: description có thể thay đổi theo phiên bản hoặc ngôn ngữ. Cũng không bắt `Exception` rồi trả response mặc định, vì sẽ che mất lỗi transport và làm caller tưởng thao tác thành công.

### Future stub và async stub

Cùng một status được biểu diễn khác nhau tùy kiểu stub:

| Kiểu client | Đường lỗi |
| --- | --- |
| Blocking stub | Ném `StatusRuntimeException` trực tiếp. |
| Future stub | Future thất bại; gọi `get()` có thể nhận `ExecutionException`, status nằm trong cause. |
| Async stub | Gọi `StreamObserver.onError(Throwable)`. |

Với future hoặc wrapper exception, dùng `Status.fromThrowable(cause)` để tìm status gRPC:

```java
Status status = Status.fromThrowable(failure);
Status.Code code = status.getCode();

if (code == Status.Code.NOT_FOUND) {
    // Chuyển thành kết quả hoặc exception ứng dụng phù hợp.
}
```

Nếu không tìm thấy status gRPC trong cause, `Status.fromThrowable(...)` trả status `UNKNOWN`. Không giả định mọi exception đều đến từ server; lỗi có thể phát sinh trong client, callback hoặc code chuyển đổi dữ liệu.

## 5. Description, trailers và thông tin lỗi có cấu trúc

Status code trả lời câu hỏi **loại lỗi là gì**. Description giúp chẩn đoán, còn trailers có thể mang metadata bổ sung khi RPC kết thúc. Ví dụ server thêm mã lỗi ổn định cho một lỗi nghiệp vụ:

```java
private static final Metadata.Key<String> ERROR_ID =
        Metadata.Key.of(
                "x-error-id",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_ID, "PRODUCT_STATE_LOCKED");

observer.onError(Status.FAILED_PRECONDITION
        .withDescription("Sản phẩm hiện không thể cập nhật")
        .asRuntimeException(trailers));
```

Client có thể đọc trailers từ `StatusRuntimeException`:

```java
Metadata trailers = failure.getTrailers();

if (trailers != null) {
    String errorId = trailers.get(ERROR_ID);
    // Dùng errorId để đối chiếu log hoặc tài liệu lỗi.
}
```

Metadata key phải tuân theo quy tắc tên header gRPC/HTTP/2; dùng chữ thường và chỉ đưa dữ liệu nhỏ, không nhạy cảm. Không gửi access token, stack trace, SQL hoặc payload lớn trong trailers. `x-error-id` là mã chẩn đoán do hệ thống định nghĩa, không thay thế status code.

Với hệ thống cần lỗi giàu cấu trúc và đa ngôn ngữ, có thể dùng mô hình `google.rpc.Status` cùng các error detail chuẩn như `BadRequest`, `PreconditionFailure`, `ResourceInfo` hoặc `RetryInfo`. Client chỉ nên dựa vào detail mà nó hiểu; status code chuẩn vẫn là tín hiệu tương thích tối thiểu. Cần thống nhất schema detail và dependency protobuf giữa các service trước khi áp dụng.

## 6. Ranh giới giữa gRPC status và lỗi HTTP/application

Không ánh xạ status gRPC sang HTTP bằng cách so khớp số hoặc tên một cách máy móc. Gateway hoặc REST adapter cần chuyển lỗi theo hợp đồng API bên ngoài. Ví dụ `NOT_FOUND` có thể thành HTTP 404, `INVALID_ARGUMENT` có thể thành 400, nhưng `UNAVAILABLE` thường là lỗi dịch vụ tạm thời; lựa chọn HTTP cụ thể còn phụ thuộc API gateway và ngữ nghĩa ứng dụng.

Trong nội bộ ứng dụng, giữ ba lớp rõ ràng:

1. **gRPC status:** kết quả giao tiếp giữa client và server.
2. **Application exception/result:** cách tầng nghiệp vụ biểu diễn lỗi đã được phân loại.
3. **HTTP/UI/message response:** cách trình bày lỗi cho người gọi bên ngoài.

Không để application service phụ thuộc trực tiếp vào `StatusRuntimeException` nếu nó không phải tầng tích hợp. Client adapter nên chuyển status sang exception/result của ứng dụng; controller hoặc message handler quyết định cách trình bày tiếp theo.

## 7. Kiểm thử status cho unary RPC

Kiểm thử cần xác minh cả status code lẫn hành vi terminal của observer. Với gRPC Java, có thể dùng `InProcessServerBuilder` và `InProcessChannelBuilder` để kiểm tra mà không mở cổng TCP.

Ví dụ kiểm thử client nhận `NOT_FOUND`:

```java
@Test
void returnsNotFoundForMissingProduct() throws Exception {
    String name = InProcessServerBuilder.generateName();

    Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new ProductQueryGrpcService(testCatalog))
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

    try {
        ProductQueryServiceGrpc.ProductQueryServiceBlockingStub stub =
                ProductQueryServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getProduct(GetProductRequest.newBuilder()
                        .setProductId("missing")
                        .build()));

        assertEquals(Status.Code.NOT_FOUND,
                error.getStatus().getCode());
    } finally {
        channel.shutdownNow();
        server.shutdownNow();
    }
}
```

`testCatalog` là fixture kiểm thử được cấu hình để không có sản phẩm với ID `missing`. Ví dụ cần JUnit Jupiter và dependency `grpc-inprocess` tương thích với phiên bản gRPC Java của dự án.

Ma trận kiểm thử tối thiểu:

| Tình huống | Status mong đợi |
| --- | --- |
| Request có ID rỗng | `INVALID_ARGUMENT` |
| Sản phẩm không tồn tại | `NOT_FOUND` |
| Caller không có quyền | `PERMISSION_DENIED` |
| Caller chưa xác thực | `UNAUTHENTICATED` |
| Sản phẩm ở trạng thái không thể cập nhật | `FAILED_PRECONDITION` |
| Lỗi ngoài dự kiến | `INTERNAL` với description an toàn |
| Thành công | Một response và terminal status `OK` |

Ngoài test client, nên kiểm tra handler không gửi `onNext` trước `onError`, không gọi hai terminal signal và không để exception nội bộ lọt vào description. Với lỗi có trailers, xác minh client đọc được error ID nhưng không có dữ liệu nhạy cảm.

In-process test xác minh semantics của gRPC và mapping status; nó không kiểm tra TLS, TCP/HTTP/2, load balancing hoặc cấu hình bảo mật thực tế. Những phần đó cần integration test chạy transport thật.

## 8. Quan sát status trong môi trường vận hành

Status code là tín hiệu hữu ích để theo dõi độ tin cậy. Nên ghi nhận:

- Số RPC theo service, method và status code.
- Tỷ lệ lỗi theo client/server và theo phiên bản triển khai.
- Latency p50/p95/p99 cho từng method và status.
- Số lỗi `INTERNAL`, `UNAVAILABLE`, `RESOURCE_EXHAUSTED` tăng đột biến.
- Correlation ID hoặc trace ID để nối log giữa client và server.

Không dùng description tự do hoặc request ID làm metric label vì cardinality cao. Không log toàn bộ request/response hoặc credentials. Với `INTERNAL`, log stack trace ở server cùng trace ID; client chỉ nhận thông tin an toàn và mã lỗi có thể đối chiếu.

Interceptor phù hợp để đo latency, đếm status, gắn trace context và ghi log thống nhất. Logic chọn status nghiệp vụ vẫn nên nằm tại handler hoặc một bộ chuyển đổi exception có hiểu biết về ngữ cảnh method.

## 9. Lỗi thường gặp

1. **Dùng `INTERNAL` cho mọi lỗi.** Client không phân biệt được request sai, không tìm thấy tài nguyên hay lỗi hệ thống. Ánh xạ domain error sang status phù hợp.
2. **Trả `OK` cùng response chứa chuỗi báo lỗi.** Làm mất ngữ nghĩa terminal status và buộc mọi client tự phân tích payload.
3. **Phân nhánh bằng description.** Description không phải mã ổn định. Dùng `Status.Code`.
4. **Gửi stack trace hoặc SQL qua description.** Có thể làm lộ cấu trúc nội bộ và dữ liệu nhạy cảm. Log chi tiết ở server, trả thông điệp an toàn.
5. **Nhầm `FAILED_PRECONDITION` với `INVALID_ARGUMENT`.** Một bên là trạng thái hiện tại không cho phép thao tác; bên kia là request sai.
6. **Gọi `onError` rồi tiếp tục gửi response.** Mỗi RPC chỉ có một terminal outcome. Kết thúc nhánh xử lý ngay sau `onError`.
7. **Bắt lỗi quá rộng ở client rồi trả response mặc định.** Che khuất lỗi kết nối và làm sai kết quả nghiệp vụ. Chuyển status thành exception/result rõ ràng.
8. **Đưa logic nghiệp vụ vào interceptor chung.** Interceptor thiếu ngữ cảnh có thể ánh xạ sai lỗi. Giữ mapping ở handler hoặc adapter phù hợp.

## 10. Bài thực hành

Mở rộng `ProductQueryService` với method unary `UpdateProductName`. Thiết kế status cho các trường hợp: request thiếu ID, sản phẩm không tồn tại, caller không có quyền, sản phẩm đang bị khóa và lỗi lưu trữ không mong đợi.

Viết unit/integration test chứng minh:

- Mỗi lỗi nghiệp vụ trả đúng status code.
- Client chuyển status sang application exception tương ứng.
- Status description không chứa stack trace hoặc dữ liệu nhạy cảm.
- Lỗi có error ID trong trailers có thể được đối chiếu với log.
- Thành công chỉ gửi một response và kết thúc bình thường.

**Tự kiểm tra:** Với unary RPC, thành công là **một response cùng status `OK`**; thất bại là **một status khác `OK`**, có thể kèm description và trailers. Chọn code theo ngữ nghĩa lỗi, ánh xạ lỗi nghiệp vụ ở server, đọc code ở client và giữ thông tin chẩn đoán an toàn để các service Spring gRPC xử lý lỗi nhất quán.

