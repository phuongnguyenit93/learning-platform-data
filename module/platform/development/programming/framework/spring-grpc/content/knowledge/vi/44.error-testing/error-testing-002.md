# Test NOT_FOUND và resource thiếu

Một gRPC API thường nhận định danh để đọc hoặc thay đổi một resource. Khi định danh đúng định dạng nhưng resource không tồn tại trong phạm vi caller được phép truy cập, server nên trả status **NOT_FOUND**. Bài này dùng GetOrder trong Spring gRPC để minh họa cách ánh xạ resource thiếu thành status chuẩn và kiểm thử bằng generated blocking stub.

NOT_FOUND có nghĩa resource được yêu cầu không tồn tại hoặc không được công bố trong phạm vi truy vấn. Nó khác với INVALID_ARGUMENT, dùng khi request sai về cấu trúc hoặc giá trị; và khác với PERMISSION_DENIED, dùng khi resource có tồn tại nhưng caller không có quyền truy cập, tùy chính sách bảo mật có thể cố ý che giấu sự tồn tại bằng cách trả NOT_FOUND.

## 1. Xác định hợp đồng resource

Giả sử service cung cấp RPC đọc đơn hàng:

~~~proto
syntax = "proto3";

package acme.orders.v1;

option java_multiple_files = true;
option java_package = "com.acme.orders.v1";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string customer_id = 2;
  int64 total_minor = 3;
  string currency = 4;
}
~~~

Request có order_id để định vị resource. Có hai trường hợp khác nhau:

- ID rỗng hoặc sai cú pháp: request không hợp lệ, trả INVALID_ARGUMENT.
- ID hợp lệ nhưng không có đơn hàng tương ứng trong phạm vi truy vấn: trả NOT_FOUND.

Không nên trả NOT_FOUND cho mọi lỗi repository. Database mất kết nối là UNAVAILABLE hoặc status phù hợp với lỗi hạ tầng; timeout downstream là DEADLINE_EXCEEDED. Nếu gộp mọi lỗi thành NOT_FOUND, client sẽ hiểu nhầm rằng resource không tồn tại và có thể bỏ qua sự cố vận hành.

## 2. Ánh xạ Optional.empty thành NOT_FOUND

Repository nên biểu diễn trường hợp không có resource bằng Optional.empty() thay vì trả null hoặc ném một exception chung:

~~~java
public interface OrderRepository {
    Optional<OrderRecord> findById(String orderId);
}
~~~

Service implementation validate định danh trước, sau đó tra cứu và chuyển kết quả thiếu thành status:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository repository;

    public OrderGrpcService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        String orderId = request.getOrderId();
        if (orderId == null || orderId.isBlank()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("order_id must not be blank")
                    .asRuntimeException());
            return;
        }

        Optional<OrderRecord> result = repository.findById(orderId);
        if (result.isEmpty()) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("order not found")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(toResponse(result.get()));
        responseObserver.onCompleted();
    }

    private GetOrderResponse toResponse(OrderRecord order) {
        return GetOrderResponse.newBuilder()
            .setOrderId(order.id())
            .setCustomerId(order.customerId())
            .setTotalMinor(order.totalMinor())
            .setCurrency(order.currency())
            .build();
    }
}
~~~

OrderRecord là kiểu dữ liệu nội bộ của ví dụ. Trong ứng dụng Spring, OrderGrpcService thường được đăng ký bằng cơ chế service registration của starter và nhận OrderRepository qua constructor injection. Không để implementation phụ thuộc trực tiếp vào HTTP controller hoặc exception mapping của REST.

Với unary RPC, sau onError phải return và không gọi onNext/onCompleted. Nếu dùng exception mapping/interceptor tập trung, cần bảo đảm exception resource missing được ánh xạ ổn định thành NOT_FOUND, không rơi về UNKNOWN.

## 3. Chọn đúng status khi resource không truy cập được

| Tình huống | Status phù hợp | Ý nghĩa |
| --- | --- | --- |
| ID rỗng hoặc sai cú pháp | INVALID_ARGUMENT | Caller phải sửa request |
| ID hợp lệ nhưng resource không tồn tại | NOT_FOUND | Resource không có trong phạm vi truy vấn |
| Resource tồn tại nhưng caller không có quyền | PERMISSION_DENIED | Caller không được phép thực hiện thao tác |
| Cần đăng nhập hoặc credential không hợp lệ | UNAUTHENTICATED | Danh tính caller chưa được xác thực |
| Resource đang ở trạng thái không cho phép thao tác | FAILED_PRECONDITION | Cần thay đổi trạng thái trước |
| Database hoặc downstream không khả dụng | UNAVAILABLE | Lỗi hạ tầng có thể tạm thời |

Quyết định giữa NOT_FOUND và PERMISSION_DENIED có thể phụ thuộc chính sách chống dò quét resource. Ví dụ API đa tenant có thể trả NOT_FOUND cho cả resource không tồn tại lẫn resource thuộc tenant khác, nhằm tránh tiết lộ tenant khác có dữ liệu. Nếu áp dụng cách này, phải thực hiện kiểm tra tenant ở tầng truy vấn và giữ hành vi nhất quán cho mọi endpoint.

## 4. Kiểm thử bằng in-process gRPC server

In-process transport chạy server và client trong cùng JVM, phù hợp để kiểm tra logic service, status mapping và repository interaction mà không cần mở TCP port.

Ví dụ JUnit 5 dùng repository fake:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OrderGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        OrderRepository repository = orderId -> {
            repositoryCalls.incrementAndGet();
            return Optional.empty();
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new OrderGrpcService(repository))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = OrderServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void validButMissingOrderReturnsNotFound() {
        GetOrderRequest request = GetOrderRequest.newBuilder()
            .setOrderId("order-404")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(request));

        assertEquals(
            Status.Code.NOT_FOUND,
            error.getStatus().getCode());
        assertEquals(
            "order not found",
            error.getStatus().getDescription());
        assertEquals(1, repositoryCalls.get());
    }

    @Test
    void blankOrderIdReturnsInvalidArgumentWithoutLookup() {
        GetOrderRequest request = GetOrderRequest.newBuilder()
            .setOrderId(" ")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

Test dùng directExecutor() vì handler trong ví dụ thực hiện validation và lookup đồng bộ, không block chờ tác vụ khác. Nếu repository fake có delay, latch hoặc I/O, hãy dùng executor riêng để tránh chặn luồng test. Artifact grpc-inprocess phải tương thích phiên bản với các artifact gRPC Java còn lại.

## 5. Kiểm tra cả trường hợp resource tồn tại

Một test chỉ xác minh NOT_FOUND có thể bỏ sót lỗi khiến service luôn trả lỗi. Cần có test thành công để chứng minh mapping chỉ áp dụng khi repository thực sự không có resource:

~~~java
OrderRecord record = new OrderRecord(
    "order-42", "customer-7", 12500, "USD");

OrderRepository foundRepository =
    orderId -> Optional.of(record);

OrderGrpcService service = new OrderGrpcService(foundRepository);
~~~

Trong test fixture riêng, đăng ký service này và gọi GetOrder với order-42; assert response có đúng order_id, customer_id, amount và currency. Kết quả thành công phải gọi repository đúng một lần và không tạo NOT_FOUND.

Nên kiểm tra thêm các trường hợp:

- Resource bị soft-delete có được xem là không tồn tại theo hợp đồng hay không.
- ID đúng nhưng thuộc tenant khác được trả NOT_FOUND hay PERMISSION_DENIED theo policy.
- Repository trả Optional.empty() chỉ khi truy vấn hoàn tất thành công nhưng không có hàng.
- Lỗi database được truyền thành status hạ tầng phù hợp, không bị đổi thành NOT_FOUND.

## 6. Test không gọi nhầm repository và không tạo side effect

Với RPC đọc, assertion quan trọng là repository được gọi đúng một lần cho ID hợp lệ và không được gọi khi ID sai định dạng. Với RPC cập nhật/xóa, resource không tồn tại phải bị phát hiện trước side effect:

1. Đọc hoặc kiểm tra sự tồn tại trong transaction phù hợp.
2. Nếu không có resource, trả NOT_FOUND.
3. Không phát event, không ghi audit thành công và không gọi downstream như thể thao tác đã hoàn tất.
4. Nếu có race giữa bước đọc và ghi, xử lý bằng transaction/constraint và ánh xạ kết quả nhất quán.

Không dựa vào một lần existsById tách rời rồi mới update nếu thao tác có thể thay đổi giữa hai query. Với update/delete, ưu tiên một câu lệnh có điều kiện hoặc transaction để xác định chính xác số hàng bị tác động.

## 7. Resource thiếu trong hệ thống đa tenant

Trong hệ thống nhiều tenant, truy vấn phải ràng buộc tenant từ danh tính đã xác thực:

~~~java
Optional<OrderRecord> findByIdAndTenantId(
    String orderId,
    String authenticatedTenantId);
~~~

authenticatedTenantId phải được lấy từ principal/credential đã xác minh, không tin tenant ID do caller tự gửi trong request hoặc metadata. Nếu query theo cả order ID và tenant ID trả empty, service có thể trả NOT_FOUND để không tiết lộ resource thuộc tenant khác.

Không đưa tenant ID, customer ID nhạy cảm hoặc thông tin resource khác vào status description nếu caller không được phép biết. Ghi log nội bộ bằng request ID và mã lỗi đã chuẩn hóa; hạn chế log định danh đầy đủ theo chính sách dữ liệu.

## 8. Rich error details khi cần thông tin resource

Status NOT_FOUND cùng description ngắn thường đủ cho API đơn giản. Nếu client cần biết loại resource bị thiếu, có thể dùng rich error model từ google.rpc.Status và detail google.rpc.ResourceInfo:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.ResourceInfo;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;

ResourceInfo resourceInfo = ResourceInfo.newBuilder()
    .setResourceType("acme.orders.v1.Order")
    .setResourceName("orders/order-404")
    .setOwner("")
    .setDescription("The requested order was not found")
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(com.google.rpc.Code.NOT_FOUND_VALUE)
    .setMessage("order not found")
    .addDetails(Any.pack(resourceInfo))
    .build();

responseObserver.onError(StatusProto.toStatusRuntimeException(richStatus));
~~~

Đoạn code cần các protobuf common types tương thích, gồm google.rpc.ResourceInfo và Any. Chỉ đưa resource name nếu caller được phép nhìn thấy nó; trong API đa tenant, detail có thể làm lộ sự tồn tại của resource. Client đọc detail bằng StatusProto.fromThrowable(error) và unpack đúng type URL.

Không phải mọi proxy hoặc client đều giữ trailers rich error details. Nếu detail là bắt buộc, kiểm thử qua toàn bộ đường đi production và vẫn giữ status code/message cơ bản đủ rõ khi detail bị mất.

## 9. Không retry NOT_FOUND

NOT_FOUND thường là kết quả ổn định của truy vấn tại thời điểm thực hiện. Retry ngay cùng request thường không giúp ích và có thể tạo tải không cần thiết. Không đưa NOT_FOUND vào danh sách retryable status code trừ khi API có semantics đặc biệt được tài liệu hóa, chẳng hạn resource được tạo bất đồng bộ và caller chủ động polling theo backoff.

Nếu resource có thể xuất hiện sau đó, thiết kế operation/polling rõ ràng: trả trạng thái pending hoặc một resource operation riêng thay vì biến NOT_FOUND thành lỗi retry chung. Với request tạo resource, dùng idempotency key để caller có thể truy vấn kết quả sau timeout mà không tạo trùng.

## 10. Kiểm thử qua Spring application context

In-process test xác minh service logic và status mapping, nhưng không chứng minh starter đã đăng ký đúng service hoặc interceptor. Bổ sung Spring integration test để:

- Khởi động application context với repository fake hoặc test database.
- Gọi GetOrder qua channel tới server do starter quản lý.
- Xác minh service name và method path được đăng ký đúng.
- Kiểm tra interceptor không đổi NOT_FOUND thành status khác.
- Kiểm tra metadata/trailers và rich error details nếu API sử dụng.
- Xác minh TLS/proxy nếu đó là một phần của deployment.

Tên property chọn cổng và cách lấy channel phụ thuộc starter/version. Dùng đúng extension point của dự án; không giả định mọi Spring gRPC starter có cùng cấu hình.

## 11. Ma trận kiểm thử đề xuất

| Kịch bản | Status/kết quả | Repository |
| --- | --- | --- |
| ID rỗng | INVALID_ARGUMENT | Không gọi |
| ID hợp lệ nhưng không tồn tại | NOT_FOUND | Gọi đúng một lần |
| ID hợp lệ và resource tồn tại | Thành công | Gọi đúng một lần |
| Resource thuộc tenant khác | Theo policy, thường NOT_FOUND để tránh enumeration | Query có tenant scope |
| Database không khả dụng | UNAVAILABLE hoặc mapping hạ tầng phù hợp | Lỗi được phân biệt với empty result |
| Resource soft-deleted | Theo hợp đồng API | Truy vấn áp dụng quy tắc xóa mềm |

Kiểm tra status code trước, sau đó mới kiểm tra description hoặc rich details. Không chỉ assert chuỗi thông báo vì message có thể được điều chỉnh mà semantics status phải ổn định.

## 12. Ghi nhớ và tự kiểm tra

**Test NOT_FOUND và resource thiếu** cần chứng minh ID hợp lệ nhưng resource không tồn tại được ánh xạ thành NOT_FOUND, trong khi ID sai định dạng vẫn là INVALID_ARGUMENT. Dùng repository Optional, generated blocking stub và in-process server để kiểm tra status, description, số lần lookup và đường đi thành công. Với multi-tenant, truy vấn phải giới hạn theo danh tính đã xác thực và tránh tiết lộ resource ngoài phạm vi caller.

Tự kiểm tra:

1. Vì sao resource ID hợp lệ nhưng không có kết quả khác với request sai định dạng?
2. Khi nào dùng NOT_FOUND thay vì PERMISSION_DENIED?
3. Vì sao lỗi database không được ánh xạ thành NOT_FOUND?
4. Test cần xác minh gì ngoài status code để chứng minh mapping đúng?
5. Vì sao tenant scope phải lấy từ danh tính đã xác thực?
6. Khi nào rich error detail ResourceInfo có thể làm lộ dữ liệu?

Kiểm thử NOT_FOUND đúng giúp client phân biệt resource thiếu với lỗi request và lỗi hạ tầng, đồng thời bảo vệ dữ liệu và giữ hành vi API nhất quán.
