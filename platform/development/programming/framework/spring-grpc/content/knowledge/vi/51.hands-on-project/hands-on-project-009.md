# Thêm deadline và retry có kiểm soát

Trong dự án này, bạn sẽ xây dựng một client Spring gọi RPC unary `GetOrder` tới dịch vụ Spring gRPC. Client đặt deadline cho từng lần gọi và cấu hình retry có giới hạn khi server trả trạng thái `UNAVAILABLE`. Bạn sẽ kiểm thử lỗi tạm thời được khôi phục, lỗi không nên retry và dependency xử lý quá thời gian cho phép.

Mục tiêu là bảo vệ thời gian phản hồi và tài nguyên khi dịch vụ phụ thuộc gặp sự cố. Retry chỉ hữu ích khi thao tác có thể gọi lại an toàn và vẫn còn ngân sách thời gian. Chính sách retry thiếu giới hạn có thể làm tăng tải đúng lúc hệ thống đang quá tải.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Định nghĩa unary RPC bằng Protocol Buffers và triển khai server bằng Spring gRPC.
- Tạo `ManagedChannel` do Spring quản lý vòng đời và sinh blocking stub.
- Đặt deadline cho từng RPC bằng `withDeadlineAfter`.
- Cấu hình retry policy theo service và method, với số lần thử, backoff và status được phép retry.
- Phân biệt một lời gọi logic ở client với nhiều attempt được server nhận.
- Kiểm thử `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `NOT_FOUND` và hành vi cancellation.
- Giải thích khi nào cần idempotency key thay vì retry trực tiếp.

## 2. Bài toán và phạm vi

Một ứng dụng quản lý đơn hàng cần lấy thông tin đơn từ `OrderService`. Trong lúc triển khai hoặc khi dependency tạm thời mất kết nối, server có thể trả `UNAVAILABLE`. Client cần thử lại một số lần với khoảng nghỉ tăng dần. Mỗi request cũng phải có deadline để không chờ vô hạn.

RPC `GetOrder` chỉ đọc dữ liệu nên có thể retry an toàn nếu service giữ đúng semantics đọc. Chính sách mẫu cho phép tối đa ba attempt, bao gồm lần gọi đầu tiên, và chỉ retry status `UNAVAILABLE`.

| Thành phần | Quyết định |
|---|---|
| RPC | Unary `orders.v1.OrderService/GetOrder` |
| Deadline mỗi lời gọi | 2 giây |
| Số attempt tối đa | 3, tính cả attempt đầu |
| Backoff ban đầu | 200 ms |
| Backoff tối đa | 1 giây |
| Hệ số tăng backoff | 2 |
| Status được retry | Chỉ `UNAVAILABLE` |
| Status không retry trong chính sách này | `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `DEADLINE_EXCEEDED` |

Deadline là ngân sách tổng của RPC, bao gồm thời gian xử lý và thời gian chờ giữa các attempt. Retry dừng khi hết ngân sách, dù vẫn còn attempt theo cấu hình.

## 3. Cấu trúc dự án

Tổ chức mã theo cấu trúc module hiện có. Một cách bố trí tham khảo:

```text
src/main/proto/
  order_service.proto

src/main/java/com/example/orders/
  server/OrderGrpcService.java
  server/OrderRepository.java
  client/GrpcClientConfiguration.java
  client/OrderClient.java

src/test/java/com/example/orders/
  OrderClientRetryIntegrationTest.java
```

Dùng phiên bản Spring gRPC và plugin sinh mã protobuf đã được dự án quản lý. Bài thực hành tập trung vào API gRPC Java; cấu hình plugin protobuf và dependency cần khớp với phiên bản Spring gRPC đang dùng.

## 4. Khai báo hợp đồng protobuf

Tạo file `src/main/proto/order_service.proto`:

```protobuf
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.grpc";
option java_outer_classname = "OrderServiceProto";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string status = 2;
  int64 total_amount = 3;
  string currency = 4;
}
```

Sau khi build, plugin protobuf sinh `OrderServiceGrpc`, `GetOrderRequest` và `GetOrderResponse`. Full service name trong service config là `orders.v1.OrderService`; tên method là `GetOrder`. Hai giá trị này phải khớp chính xác với package và service trong file proto.

## 5. Triển khai server Spring gRPC

Server chuyển lỗi dependency thành gRPC status. Lỗi tạm thời được ánh xạ thành `UNAVAILABLE`; đơn hàng không tồn tại được ánh xạ thành `NOT_FOUND`. Không chuyển mọi exception thành `UNAVAILABLE`, vì client sẽ retry cả lỗi lập trình hoặc lỗi dữ liệu.

Ví dụ dưới đây giả định `OrderRepository` ném `TemporaryDependencyException` khi dependency tạm thời không sẵn sàng và `OrderNotFoundException` khi không tìm thấy đơn hàng:

```java
@GrpcService
public class OrderGrpcService extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository orderRepository;

    public OrderGrpcService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            Order order = orderRepository.findById(request.getOrderId());

            GetOrderResponse response = GetOrderResponse.newBuilder()
                    .setOrderId(order.id())
                    .setStatus(order.status())
                    .setTotalAmount(order.totalAmount())
                    .setCurrency(order.currency())
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (OrderNotFoundException ex) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy đơn hàng")
                            .asRuntimeException());
        } catch (TemporaryDependencyException ex) {
            responseObserver.onError(
                    Status.UNAVAILABLE
                            .withDescription("Dependency tạm thời không khả dụng")
                            .withCause(ex)
                            .asRuntimeException());
        } catch (Exception ex) {
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Không thể xử lý yêu cầu")
                            .withCause(ex)
                            .asRuntimeException());
        }
    }
}
```

`@GrpcService` đăng ký implementation với Spring gRPC. Các kiểu `Order`, `OrderRepository` và exception là thành phần ứng dụng cần triển khai. Không gửi stack trace hoặc thông tin nội bộ của dependency trong status description; ghi exception gốc ở server với correlation ID để điều tra.

Với xử lý đồng bộ, deadline/cancellation của RPC không tự bảo đảm một lệnh JDBC hoặc HTTP đang chặn sẽ dừng ngay. Hãy truyền timeout còn lại xuống dependency và dùng API có hỗ trợ timeout/cancellation. Nếu xử lý bất đồng bộ, kiểm tra context/cancellation trước khi tiếp tục công việc và giải phóng tài nguyên khi client hủy.

## 6. Cấu hình retry policy cho client

gRPC Java nhận retry policy qua service config. Trong Spring, có thể tạo channel thành bean để Spring quản lý vòng đời và inject stub vào client service. Ví dụ sau dùng địa chỉ local và plaintext cho môi trường phát triển:

```java
@Configuration
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        Map<String, Object> retryPolicy = Map.of(
                "maxAttempts", 3.0,
                "initialBackoff", "0.2s",
                "maxBackoff", "1s",
                "backoffMultiplier", 2.0,
                "retryableStatusCodes", List.of("UNAVAILABLE")
        );

        Map<String, Object> methodConfig = Map.of(
                "name", List.of(Map.of(
                        "service", "orders.v1.OrderService",
                        "method", "GetOrder"
                )),
                "retryPolicy", retryPolicy
        );

        Map<String, Object> serviceConfig = Map.of(
                "methodConfig", List.of(methodConfig)
        );

        return ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .enableRetry()
                .defaultServiceConfig(serviceConfig)
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderServiceBlockingStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
```

Các import chính gồm `ManagedChannel`, `ManagedChannelBuilder`, `OrderServiceGrpc`, `Configuration`, `Bean`, `List` và `Map`. `usePlaintext()` chỉ dành cho môi trường local/test. Trong production, cấu hình TLS hoặc mTLS theo hạ tầng chứng thư của hệ thống.

| Trường | Ý nghĩa |
|---|---|
| `maxAttempts` | Tổng số attempt tối đa, bao gồm lần gọi đầu tiên |
| `initialBackoff` | Thời gian chờ trước lần retry đầu |
| `maxBackoff` | Giới hạn thời gian chờ giữa các attempt |
| `backoffMultiplier` | Hệ số nhân thời gian chờ sau mỗi lần thất bại |
| `retryableStatusCodes` | Chỉ status được liệt kê mới kích hoạt retry |
| `name` | Phạm vi service/method áp dụng policy |

Với cấu hình này, khoảng chờ dự kiến trước attempt thứ hai là 200 ms và trước attempt thứ ba là 400 ms, nếu chưa bị giới hạn bởi deadline hoặc cơ chế retry khác. Retry chỉ có thể tiếp tục khi RPC chưa đi qua điểm commit của gRPC, chẳng hạn server chưa gửi response headers. Khi server đã bắt đầu trả response, gRPC không thể tùy tiện phát lại RPC đó.

Không cấu hình retry cho mọi method bằng một policy rộng. Hãy khai báo đúng service và method cần retry, chọn status có ý nghĩa tạm thời và giới hạn số attempt. Nếu dự án có retry ở nhiều tầng như client, gateway và service trung gian, hãy tính tổng số lần gọi có thể phát sinh để tránh retry lồng nhau khuếch đại tải.

## 7. Đặt deadline ở từng lời gọi

Deadline nên được đặt theo yêu cầu nghiệp vụ. Có thể dùng stub đã cấu hình retry và tạo một stub có deadline riêng cho mỗi lần gọi:

```java
@Service
public class OrderClient {

    private final OrderServiceGrpc.OrderServiceBlockingStub baseStub;

    public OrderClient(
            OrderServiceGrpc.OrderServiceBlockingStub baseStub) {
        this.baseStub = baseStub;
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        try {
            return baseStub
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getOrder(request);
        } catch (StatusRuntimeException ex) {
            Status.Code code = ex.getStatus().getCode();
            if (code == Status.Code.DEADLINE_EXCEEDED) {
                throw new OrderLookupTimeoutException(orderId, ex);
            }
            if (code == Status.Code.NOT_FOUND) {
                throw new OrderNotFoundException(orderId, ex);
            }
            throw ex;
        }
    }
}
```

Stub là immutable; `withDeadlineAfter` trả về stub mới nên không làm thay đổi `baseStub` được inject. Mỗi lần gọi có deadline riêng hai giây. `OrderLookupTimeoutException` và `OrderNotFoundException` là exception ở tầng ứng dụng.

Deadline được tính từ lúc RPC bắt đầu và bao gồm thời gian xử lý, backoff cùng các attempt. Nếu ba attempt cần tổng cộng hơn hai giây, RPC sẽ kết thúc khi deadline hết hạn. Tăng `maxAttempts` không có ích nếu ngân sách thời gian không đủ; cần đo latency thực tế của dependency để chọn deadline và backoff.

## 8. Tạo kịch bản lỗi tạm thời có thể tái hiện

Để quan sát retry, tạo một repository giả cho môi trường tích hợp. Repository trả lỗi tạm thời ở hai lần đầu và trả đơn hàng ở lần thứ ba:

```java
public final class FlakyOrderRepository implements OrderRepository {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Order findById(String orderId) {
        int currentAttempt = attempts.incrementAndGet();
        if (currentAttempt <= 2) {
            throw new TemporaryDependencyException(
                    "Dependency is temporarily unavailable");
        }

        return new Order(orderId, "PAID", 125_000L, "VND");
    }

    public int attempts() {
        return attempts.get();
    }
}
```

Đăng ký implementation này trong test context thay cho repository thật. Server sẽ trả `UNAVAILABLE` cho hai request đầu và `OK` ở request thứ ba. Vì lỗi xảy ra trước khi server gửi response, gRPC có thể retry theo policy đã cấu hình.

Khi chạy thử, ghi nhận:

- Client gọi `getOrder()` một lần.
- Server nhận tối đa ba attempt.
- Hai attempt đầu kết thúc `UNAVAILABLE`.
- Attempt thứ ba trả response thành công.
- Client nhận một kết quả cuối cùng và không phải tự viết vòng lặp retry.

Đặt bộ đếm test có thể reset giữa các test để kết quả không phụ thuộc thứ tự thực thi. Không dùng repository giả có trạng thái dùng chung trong production.

## 9. Kiểm thử deadline, retry và status không được retry

Tạo integration test với server gRPC thực trong test context hoặc in-process server/client. Dùng deadline đủ rộng cho bài retry thành công để test không phụ thuộc máy chạy chậm:

```java
@Test
void retriesUnavailableAndReturnsSuccessfulResponse() {
    GetOrderResponse response = orderClient.getOrder("order-1001");

    assertEquals("order-1001", response.getOrderId());
    assertEquals("PAID", response.getStatus());
    assertEquals(3, flakyOrderRepository.attempts());
}
```

Bổ sung các kịch bản sau:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Dependency thành công ngay | Client nhận response; server xử lý một attempt |
| Hai lần `UNAVAILABLE`, sau đó thành công | Client nhận response; server xử lý ba attempt |
| Luôn trả `UNAVAILABLE` | Client nhận lỗi sau tối đa ba attempt hoặc sớm hơn nếu hết deadline |
| Trả `NOT_FOUND` | Client nhận `NOT_FOUND`; không retry |
| Dependency chậm hơn deadline | Client nhận `DEADLINE_EXCEEDED`; công việc phía server/dependency dừng khi có thể |
| Client hủy RPC | Server quan sát cancellation và giải phóng công việc liên quan |

Để kiểm thử deadline, tạo repository giả có độ trễ lớn hơn deadline của client. Không dùng `Thread.sleep()` dài trong test suite nếu có thể thay bằng latch hoặc fake dependency có thể điều khiển thời gian. Nếu buộc phải mô phỏng độ trễ, đặt giới hạn chờ và luôn giải phóng tài nguyên trong `finally`.

Ví dụ kiểm tra status timeout:

```java
@Test
void deadlineStopsSlowCall() {
    OrderClient clientWithShortDeadline = createClientWithDeadline(
            Duration.ofMillis(300));

    assertThrows(
            OrderLookupTimeoutException.class,
            () -> clientWithShortDeadline.getOrder("order-slow"));
}
```

Đây là khung kiểm thử: `createClientWithDeadline` cần được triển khai trong test fixture để inject stub có deadline 300 ms. Trong production, deadline nên đến từ ngân sách của request hoặc cấu hình nghiệp vụ, không hardcode cùng một giá trị cho mọi method.

## 10. Hiểu rõ idempotency trước khi retry thao tác ghi

`GetOrder` là thao tác đọc nên có thể gọi lại mà không tạo side effect. Nếu đổi bài toán thành `CreateOrder`, retry có thể tạo hai đơn hàng khi lần đầu server đã ghi dữ liệu nhưng response bị mất trên đường truyền.

Với thao tác ghi, thêm idempotency key vào hợp đồng:

```protobuf
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
```

Server cần lưu idempotency key cùng kết quả trong một transaction có ràng buộc duy nhất. Khi nhận lại cùng key, trả về kết quả đã lưu thay vì thực hiện side effect lần nữa. Cùng một key nhưng payload khác phải được phát hiện và từ chối theo quy tắc nghiệp vụ. Chỉ sau khi bảo đảm semantics này mới cân nhắc retry các lỗi tạm thời cho RPC ghi.

Không retry mù quáng các status:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED` và `PERMISSION_DENIED` thường cần sửa request hoặc quyền truy cập.
- `RESOURCE_EXHAUSTED` có thể biểu thị quota hoặc quá tải; retry ngay có thể làm tình trạng nặng hơn.
- `DEADLINE_EXCEEDED` không chứng minh server chưa thực hiện side effect. Với thao tác ghi, kết quả có thể chưa rõ đối với client.
- `UNAVAILABLE` thường có tính tạm thời nhưng vẫn cần idempotency nếu method có side effect.

## 11. Quan sát và vận hành chính sách retry

Để biết policy đang hoạt động đúng, ghi nhận metrics và log ở cả client lẫn server:

| Tín hiệu | Phía đo | Ý nghĩa |
|---|---|---|
| Số lời gọi logic | Client | Số lần ứng dụng yêu cầu thực hiện RPC |
| Số attempt | Server hoặc instrumentation theo attempt | Số request thực tế server nhận |
| Tỷ lệ `UNAVAILABLE` | Client và server | Mức độ lỗi tạm thời |
| Tỷ lệ `DEADLINE_EXCEEDED` | Client | Ngân sách thời gian không đủ hoặc dependency quá chậm |
| Thời gian hoàn tất cuối cùng | Client | Trải nghiệm thực tế sau cả retry/backoff |
| Retry thành công | Client/server | Các lỗi tạm thời được phục hồi |

Một client interceptor có thể quan sát lời gọi logic ở tầng client; server interceptor thường nhìn thấy từng attempt được gửi đến server. Không mặc định hai bộ đếm này phải bằng nhau. Khi đối chiếu log, dùng trace/correlation ID ổn định cho lời gọi logic và thêm attempt number ở nơi có thể xác định attempt.

Không đưa order ID, customer ID hoặc idempotency key làm metric label vì cardinality sẽ tăng nhanh. Có thể ghi định danh cần thiết trong log đã kiểm soát quyền truy cập và chính sách lưu trữ.

Theo dõi cả latency sau retry. Một policy có thể làm tỷ lệ thành công tăng nhưng khiến p99 latency vượt SLO. Khi đó cần xem lại deadline, backoff, số attempt, timeout của dependency và tải của server thay vì chỉ tăng số lần thử.

## 12. Tiêu chí nghiệm thu

Hoàn thành dự án khi tất cả điều kiện sau được xác minh:

- [ ] Hợp đồng protobuf sinh được Java stub và service base class.
- [ ] Spring gRPC server phục vụ unary `GetOrder`.
- [ ] Client channel được quản lý vòng đời bởi Spring.
- [ ] Mỗi lời gọi `GetOrder` có deadline hữu hạn.
- [ ] Retry policy chỉ áp dụng cho đúng service/method và status `UNAVAILABLE`.
- [ ] `maxAttempts` được hiểu là tổng số lần thử, bao gồm lần đầu.
- [ ] Hai lỗi tạm thời rồi thành công trả kết quả trong giới hạn deadline.
- [ ] `NOT_FOUND` không bị retry.
- [ ] Hết deadline trả `DEADLINE_EXCEEDED` và server dừng công việc khi có thể.
- [ ] Log/metrics phân biệt lời gọi logic, attempt, status và latency cuối.
- [ ] Không retry thao tác ghi nếu chưa có idempotency phù hợp.

## 13. Bài tập mở rộng

1. Thay `FlakyOrderRepository` bằng dependency HTTP giả lập lỗi theo xác suất; đo tỷ lệ thành công và p95/p99 latency khi thay đổi `maxAttempts`.
2. Thêm cấu hình deadline riêng cho `GetOrder` và một RPC khác có thời gian xử lý dài hơn.
3. Thử `RESOURCE_EXHAUSTED` và quan sát vì sao policy mẫu không retry status này.
4. Thêm idempotency key cho `CreateOrder`, kiểm thử hai request đồng thời có cùng key.
5. Mô phỏng server restart giữa các attempt và xác minh client kết thúc trong deadline.
6. Bổ sung dashboard thể hiện số lời gọi logic, số attempt, retry success, `UNAVAILABLE` và `DEADLINE_EXCEEDED`.

Khi điều chỉnh policy, thay đổi từng tham số một và chạy lại cùng bộ test. Ghi rõ deadline, số attempt, backoff, status được retry và kết quả latency để có thể giải thích vì sao cấu hình mới cải thiện hoặc làm giảm độ tin cậy.
