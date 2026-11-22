# Trailers và thông tin kết quả

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **HTTP/2 trailers** và vai trò của chúng trong việc kết thúc một gRPC RPC.
- Phân biệt **response message**, **initial response headers**, **trailers**, **HTTP status** và **gRPC status**.
- Đọc các trường **grpc-status**, **grpc-message**, **grpc-status-details-bin** và custom trailing metadata.
- Trả status/trailers từ server bằng grpc-java; đọc trailers ở client blocking và async.
- Chọn thông tin kết quả phù hợp cho lỗi nghiệp vụ, chẩn đoán, retry và quan sát vận hành trong Spring gRPC.
- Kiểm thử việc truyền trailers và xử lý trường hợp RPC kết thúc mà client không nhận được trailers.

## 1. Trailers là gì?

Trong gRPC qua HTTP/2, **trailers** là phần metadata được gửi ở cuối một RPC. Server dùng chúng để thông báo **kết quả cuối cùng** của lời gọi, đặc biệt là mã **gRPC status**. Trailers được truyền bằng HTTP/2 **HEADERS frame** kết thúc stream, thường có cờ **END_STREAM**.

Một RPC thường có ba loại dữ liệu ở phía phản hồi:

| Thành phần | Thời điểm | Mục đích |
| --- | --- | --- |
| **Initial response headers** | Đầu phản hồi, trước response message | Metadata ban đầu như phiên bản API hoặc thông tin phục vụ client |
| **Response message(s)** | Trong phần DATA của HTTP/2 stream | Dữ liệu nghiệp vụ được định nghĩa trong Protocol Buffers |
| **Trailers** | Cuối RPC | Gửi **grpc-status**, mô tả lỗi và metadata kết thúc |

Ví dụ unary thành công:

~~~text
Server -> Client
  HEADERS
    :status: 200
    content-type: application/grpc
  DATA
    [serialized GetOrderResponse]
  HEADERS (trailers, END_STREAM)
    grpc-status: 0
~~~

Ví dụ lỗi không tìm thấy tài nguyên:

~~~text
Server -> Client
  HEADERS (trailers-only, END_STREAM)
    :status: 200
    content-type: application/grpc
    grpc-status: 5
    grpc-message: Order%20not%20found
~~~

Trường hợp thứ hai là **trailers-only response**: lỗi xảy ra trước khi server gửi initial headers hoặc response message, nên một block HEADERS cuối cùng mang cả thông tin HTTP/gRPC cần thiết.

**Điểm cần nhớ:** HTTP status **200** không có nghĩa RPC thành công. Kết quả RPC được xác định bằng **grpc-status**. Client gRPC đọc trailers và chuyển mã status thành kết quả hoặc exception tương ứng.

## 2. Các trường chuẩn trong trailers

| Trường | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| **grpc-status** | Mã kết thúc RPC; **0** là OK | Dùng mã số này để xác định thành công/lỗi |
| **grpc-message** | Mô tả ngắn về lỗi nếu có | Chỉ phục vụ chẩn đoán; không parse chuỗi để điều khiển nghiệp vụ |
| **grpc-status-details-bin** | Chi tiết lỗi mở rộng được tuần tự hóa dưới dạng binary | Dùng khi client/server thống nhất rich error model |

Các mã status thường gặp:

- **INVALID_ARGUMENT**: request không hợp lệ.
- **NOT_FOUND**: tài nguyên nghiệp vụ không tồn tại.
- **UNAUTHENTICATED** / **PERMISSION_DENIED**: thiếu xác thực hoặc không đủ quyền.
- **FAILED_PRECONDITION**: trạng thái hiện tại chưa cho phép thao tác.
- **RESOURCE_EXHAUSTED**: vượt quota hoặc giới hạn tài nguyên.
- **UNAVAILABLE**: backend/transport tạm không sẵn sàng.
- **DEADLINE_EXCEEDED**: caller không nhận được kết quả trước deadline.
- **CANCELLED**: RPC bị hủy.

Trong grpc-java, nên trả status bằng **io.grpc.Status**, không tự thêm một custom header tên **grpc-status**. Runtime sẽ chuyển status thành trường giao thức thích hợp.

**grpc-message** có quy tắc mã hóa riêng trên wire. Không đưa stack trace, SQL, token, thông tin khách hàng hoặc chi tiết nội bộ vào mô tả lỗi trả cho client.

## 3. Custom trailing metadata: khi nào cần?

Ứng dụng có thể thêm một số metadata riêng vào trailers, ví dụ:

- **x-error-id**: mã tham chiếu để tìm log nội bộ.
- **x-service-version**: phiên bản server nếu cần chẩn đoán.
- **x-result-source**: nguồn xử lý kết quả, khi thông tin này được phép công bố.

Không đưa dữ liệu nghiệp vụ chính vào trailers. Nếu client cần **order_id**, trạng thái đơn, danh sách lỗi validation có cấu trúc hoặc cursor tiếp theo, hãy khai báo chúng trong **response message**. Trailers phù hợp với metadata kết thúc của cả RPC.

Tên custom key nên viết chữ thường, không dùng tiền tố reserved **grpc-**. Giữ trailers nhỏ, tránh gửi payload lớn, token hoặc dữ liệu cá nhân. Proxy/gateway có thể áp giới hạn metadata và chính sách chuyển tiếp riêng.

## 4. Trả trailers từ server bằng grpc-java

### 4.1. Gắn trailers khi trả lỗi

Trong grpc-java, **Status.asRuntimeException(Metadata)** cho phép gắn metadata đi kèm status. Ví dụ Spring service trả lỗi không tìm thấy đơn hàng và một mã tham chiếu:

~~~java
import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class OrderEndpoint
        extends OrderServiceGrpc.OrderServiceImplBase {

    private static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {

        String id = request.getOrderId().trim();

        if (id.isEmpty()) {
            observer.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("order_id không được rỗng")
                            .asRuntimeException());
            return;
        }

        if (!"order-42".equals(id)) {
            Metadata trailers = new Metadata();
            trailers.put(ERROR_ID, "ord-lookup-404");

            observer.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy đơn hàng")
                            .asRuntimeException(trailers));
            return;
        }

        observer.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(id)
                        .setState("PENDING")
                        .build());
        observer.onCompleted();
    }
}
~~~

Khi gọi **onError(...)**, runtime kết thúc RPC với status và trailers đính kèm. Với thành công, **onNext(...)** gửi response message rồi **onCompleted()** kết thúc RPC với status **OK**.

Response observer không cung cấp một API chung để thêm trailers tùy ý ở mọi thời điểm. Nếu cần thêm metadata cho cả đường thành công lẫn lỗi, có thể dùng **ServerInterceptor** để trang trí **ServerCall**.

### 4.2. Thêm trailers tập trung bằng ServerInterceptor

**ServerCall.close(Status, Metadata)** là điểm runtime đóng RPC. Interceptor có thể bọc lời gọi này và thêm một metadata key:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResultTrailerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> decorated =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(SERVICE_VERSION, "orders-v1");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(decorated, requestHeaders);
    }
}
~~~

Interceptor trên thêm metadata vào **mọi kết quả kết thúc** mà nó quan sát được, kể cả OK hoặc lỗi. Nếu chỉ muốn thêm khi lỗi, kiểm tra **status.isOk()** trước khi thêm. Đừng sửa hoặc ghi đè **grpc-status**; runtime chịu trách nhiệm trường chuẩn này.

Có thể đăng ký interceptor bằng **ServerInterceptors.intercept(endpoint, interceptor)** khi dùng grpc-java ServerBuilder. Nếu Spring gRPC starter đang tự quản lý server/service, hãy dùng cơ chế đăng ký interceptor do phiên bản starter cung cấp, tránh khởi tạo server thứ hai trên cùng cổng.

**Initial headers khác trailers:** dùng **ServerCall.sendHeaders(...)** để gửi metadata ban đầu. Không gọi sendHeaders với ý định thay thế thông tin kết thúc RPC.

## 5. Đọc trailers ở client

### 5.1. Blocking stub: lấy trailers khi có lỗi

Với blocking stub, khi RPC thất bại, client thường nhận **StatusRuntimeException**. Exception có thể chứa trailers:

~~~java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

private static final Metadata.Key<String> ERROR_ID =
        Metadata.Key.of(
                "x-error-id",
                Metadata.ASCII_STRING_MARSHALLER);

try {
    GetOrderResponse response = stub.getOrder(request);
    // Xử lý response thành công.
} catch (StatusRuntimeException error) {
    Status.Code code = error.getStatus().getCode();
    Metadata trailers = error.getTrailers();

    if (trailers != null) {
        String errorId = trailers.get(ERROR_ID);
        // Dùng errorId để tra cứu log, không coi nó là bằng chứng xác thực.
    }

    // Phân nhánh theo code, không parse description text.
}
~~~

**getTrailers() có thể trả null**, ví dụ lỗi transport xảy ra trước khi client nhận được phản hồi cuối từ server. Vì vậy, không giả định mọi exception đều có custom trailing metadata.

Blocking stub trả về response message, không cung cấp trực tiếp trailers của một RPC thành công. Nếu cần đọc trailers trên cả đường thành công và lỗi, dùng **ClientInterceptor**.

### 5.2. ClientInterceptor: nhận status và trailers tại onClose

Ở tầng grpc-java thấp hơn, **ClientCall.Listener.onClose(Status, Metadata)** được gọi khi RPC kết thúc. Đây là nơi quan sát status và trailers cho cả thành công lẫn thất bại:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class ResultTrailerClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, options);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata requestHeaders) {

                Listener<RespT> wrapped =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {

                                String version =
                                        trailers.get(SERVICE_VERSION);

                                // Gửi status/version tới telemetry an toàn.
                                super.onClose(status, trailers);
                            }
                        };

                super.start(wrapped, requestHeaders);
            }
        };
    }
}
~~~

Trong ứng dụng thật, hãy đưa dữ liệu cần thiết vào telemetry hoặc context gắn với đúng RPC; không lưu metadata vào biến singleton dùng chung giữa nhiều call. Nếu client dùng Spring, có thể gắn interceptor vào Channel wrapper hoặc stub theo cơ chế cấu hình hiện có. Interceptor không tạo connection mới.

## 6. Rich error details với google.rpc.Status

Với lỗi cần nhiều chi tiết máy đọc được, gRPC có thể sử dụng **rich error model**. Chi tiết được đóng gói trong **google.rpc.Status** và truyền trong metadata binary **grpc-status-details-bin**.

Ví dụ khái niệm cho lỗi validation:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;
import io.grpc.stub.StreamObserver;

BadRequest detail = BadRequest.newBuilder()
        .addFieldViolations(
                BadRequest.FieldViolation.newBuilder()
                        .setField("order_id")
                        .setDescription("Giá trị không được rỗng"))
        .build();

Status richStatus = Status.newBuilder()
        .setCode(io.grpc.Status.Code.INVALID_ARGUMENT.value())
        .setMessage("Request không hợp lệ")
        .addDetails(Any.pack(detail))
        .build();

observer.onError(StatusProto.toStatusRuntimeException(richStatus));
~~~

Client có thể trích xuất chi tiết bằng **StatusProto.fromThrowable(error)** nếu thư viện tương ứng được thêm vào và hai phía thống nhất schema error details. Ví dụ trên cần các dependency tương thích cho **grpc-protobuf**, **protobuf-java** và **proto-google-common-protos**.

Rich error details hữu ích khi client cần hiển thị hoặc xử lý lỗi theo field mà không phân tích chuỗi. Tuy nhiên:

- Chỉ gửi những chi tiết client được phép biết.
- Không đưa stack trace, câu SQL, đường dẫn nội bộ hoặc token vào **Any**.
- Không gửi một danh sách error details quá lớn.
- Client phải chịu được loại detail chưa biết hoặc phiên bản detail mới.
- Mã **Status.Code** cơ bản vẫn là căn cứ phân loại chính; detail bổ sung ý nghĩa cho lỗi.

Không nhầm **google.rpc.Status** với protobuf response của method. Khi RPC thất bại, rich status là mô tả lỗi ở tầng RPC, không phải response thành công của business method.

## 7. Trailers trong streaming RPC

Với server-streaming, client có thể nhận nhiều response message trước khi RPC kết thúc:

~~~text
Một HTTP/2 stream:
  initial HEADERS
  DATA: OrderUpdate #1
  DATA: OrderUpdate #2
  DATA: OrderUpdate #3
  trailing HEADERS: grpc-status=0
  END_STREAM
~~~

Chỉ có **một bộ trailers cuối RPC**, không phải một bộ trailers cho mỗi message. Nếu một event cần chứa **sequence**, **event_id**, cursor hoặc trạng thái cập nhật, hãy khai báo chúng trong protobuf message.

Với client-streaming và bidirectional streaming, client có thể **half-close** chiều gửi bằng **onCompleted()** trong khi vẫn chờ response. Trailers chỉ có khi toàn bộ RPC kết thúc. Khi caller hủy hoặc connection mất, client có thể không nhận được trailers từ server.

Vì vậy, client không được dùng trailers làm kênh cập nhật tiến độ liên tục. Hãy dùng response message cho dữ liệu streaming, trailers cho metadata kết thúc.

## 8. Status và trailers không phải cam kết retry

Một custom trailer như **x-retry-after-ms** có thể được một ứng dụng tự định nghĩa, nhưng gRPC không tự động hiểu key tùy biến đó thành retry policy. Nếu dùng, phải có contract rõ ràng và xác thực giá trị. Thông thường, chọn **Status.Code** có ngữ nghĩa phù hợp và dùng service config/backoff policy được kiểm soát.

| Kết quả | Ý nghĩa | Retry? |
| --- | --- | --- |
| **OK** | RPC thành công | Không cần |
| **INVALID_ARGUMENT** | Caller gửi dữ liệu sai | Sửa request |
| **NOT_FOUND** | Không có tài nguyên | Thường không |
| **UNAUTHENTICATED** | Thiếu/sai xác thực | Làm mới credential nếu phù hợp |
| **PERMISSION_DENIED** | Không đủ quyền | Không retry mù |
| **RESOURCE_EXHAUSTED** | Quota/tài nguyên cạn | Giảm tải, theo policy |
| **UNAVAILABLE** | Tạm thời không thể phục vụ | Có thể retry với backoff nếu thao tác an toàn |
| **DEADLINE_EXCEEDED** | Caller không nhận kết quả kịp | Xem xét idempotency và trạng thái thực tế |

Đặc biệt với thao tác ghi, **DEADLINE_EXCEEDED** không chứng minh server chưa commit. Custom trailer **x-error-id** chỉ hỗ trợ tra cứu; nó không thể xác nhận một transaction đã rollback hay thành công.

## 9. Những trường hợp client không nhận được trailers

Trailers là kết quả cuối của một RPC đã đi đủ xa để server/transport gửi phần kết thúc. Chúng có thể vắng mặt nếu:

- DNS, TCP hoặc TLS thất bại trước khi RPC tới server.
- Proxy/connection bị đóng giữa chừng.
- Client hủy RPC trước khi server hoàn tất.
- Deadline hết trước khi nhận response cuối.
- Transport lỗi khi đang truyền trailers.

Trong các trường hợp này, runtime có thể cung cấp status do client/transport sinh ra, nhưng **custom trailers từ server không tồn tại hoặc không đến được client**. Code client phải chấp nhận **trailers null hoặc thiếu key**.

Không xây dựng luồng xử lý nghiệp vụ bắt buộc phải có **x-error-id** để tiếp tục. Trailers là kênh chẩn đoán hữu ích, không phải kho lưu trạng thái bền vững.

## 10. Kiểm thử trailers với grpc-inprocess

Có thể dùng **InProcessServerBuilder** và **InProcessChannelBuilder** để kiểm tra việc trả status/trailers qua gRPC runtime mà không cần cổng mạng. Ví dụ JUnit 5 dưới đây kiểm tra lỗi **NOT_FOUND** có custom trailer:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Metadata;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class ResultTrailerTest {

    private static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void notFoundIncludesErrorReference() throws Exception {
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new OrderEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(channel);

            StatusRuntimeException error = org.junit.jupiter.api.Assertions
                    .assertThrows(
                            StatusRuntimeException.class,
                            () -> stub.getOrder(
                                    GetOrderRequest.newBuilder()
                                            .setOrderId("missing")
                                            .build()));

            assertEquals(Status.Code.NOT_FOUND,
                    error.getStatus().getCode());

            Metadata trailers = error.getTrailers();
            assertNotNull(trailers);
            assertEquals("ord-lookup-404", trailers.get(ERROR_ID));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Ví dụ giả định **OrderEndpoint** ở mục 4 được đăng ký và trả đúng **x-error-id** cho trường hợp không tìm thấy. Cần dependency **grpc-inprocess** tương thích với phiên bản grpc-java. Test này kiểm tra status/trailers qua runtime; nó không xác minh proxy, TLS hoặc việc một gateway ngoài thực tế có giữ custom trailers hay không.

Nên bổ sung test cho:

- RPC thành công và trailers được thêm qua server interceptor.
- Lỗi không có custom trailers; client không được giả định key luôn tồn tại.
- Client interceptor quan sát **onClose(status, trailers)** cho cả OK và lỗi.
- Trailers-only response.
- Rich error details có loại detail client biết và loại client chưa biết.
- Connection bị ngắt/cancellation trước khi trailers đến.

## 11. Vận hành và bảo mật

Trailers thường nhỏ, nhưng vẫn đi qua hạ tầng HTTP/2 và có thể bị giới hạn hoặc lọc bởi proxy. Khi thiết kế:

- **Giữ metadata ngắn**: error ID, version hoặc một vài trường chẩn đoán; không truyền JSON/payload lớn.
- **Không gửi bí mật**: token, cookie, thông tin cá nhân và chi tiết hạ tầng không nên xuất hiện trong trailers.
- **Redact log**: interceptor ghi status và error ID có thể hữu ích, nhưng không log mọi metadata một cách mặc định.
- **Không dùng trailer thay message**: dữ liệu nghiệp vụ cần lưu/hiển thị phải nằm trong protobuf response.
- **Theo dõi status theo method**: đo tỉ lệ OK, NOT_FOUND, UNAVAILABLE, DEADLINE_EXCEEDED và latency.
- **Kiểm thử proxy thực tế**: gateway/service mesh có thể áp giới hạn header hoặc policy chuyển tiếp khác nhau.

Một **x-error-id** tốt là mã tham chiếu ngẫu nhiên/không tiết lộ dữ liệu, liên kết với log server có kiểm soát truy cập. Nó giúp hỗ trợ vận hành mà không cần gửi stack trace cho caller.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Dùng **OrderService/GetOrder** và implementation Spring đã có. Với đơn không tồn tại, trả **NOT_FOUND** kèm trailer **x-error-id**.
2. Viết blocking client bắt **StatusRuntimeException**, đọc **getTrailers()** và xử lý trường hợp trailers hoặc key bị thiếu.
3. Thêm **ResultTrailerInterceptor** để gắn **x-service-version** vào mọi RPC kết thúc. Kiểm tra cả đường thành công và lỗi.
4. Viết **ClientInterceptor** quan sát **onClose(Status, Metadata)**; ghi nhận status và custom trailer mà không lưu metadata vào singleton mutable.
5. Tạo một rich error bằng **google.rpc.Status** và một **BadRequest.FieldViolation**. Kiểm tra client trích xuất được detail; thử với detail chưa biết.
6. Chuyển method sang server-streaming, gửi nhiều event rồi kết thúc. Xác nhận trailers chỉ xuất hiện một lần ở cuối RPC.
7. Chạy test in-process, sau đó kiểm tra qua proxy/TLS nếu hệ thống triển khai có gateway; xác minh custom trailers không bị mất và giới hạn header phù hợp.

### Câu hỏi tự kiểm tra

**1. Trailers khác initial response headers ở điểm nào?**  
Initial headers đến trước response message; trailers đến cuối RPC và mang **grpc-status** cùng metadata kết thúc.

**2. HTTP status 200 có đảm bảo RPC thành công không?**  
Không. Phải kiểm tra **grpc-status** trong trailers.

**3. Vì sao blocking stub không trả trailers cùng response thành công?**  
API blocking stub trả protobuf response; để quan sát trailers của cả đường thành công và lỗi, dùng **ClientInterceptor.onClose(...)**.

**4. Khi nào StatusRuntimeException.getTrailers() có thể null?**  
Khi lỗi xảy ra trước khi client nhận được trailers, ví dụ lỗi kết nối hoặc transport bị đóng giữa chừng.

**5. Có nên đưa order_id hoặc toàn bộ response vào trailers?**  
Không. Dữ liệu nghiệp vụ thuộc protobuf response message; trailers dành cho metadata kết thúc nhỏ gọn.

**6. Một server-streaming RPC có bao nhiêu bộ trailers?**  
Một bộ ở cuối RPC, không phải một bộ cho mỗi message.

**7. Rich error details được truyền bằng cách nào?**  
Có thể dùng **google.rpc.Status** và các error details được tuần tự hóa trong **grpc-status-details-bin**, với thư viện và contract tương thích giữa hai phía.

**8. Custom trailer x-retry-after-ms có tự kích hoạt retry không?**  
Không. Đây chỉ là metadata tùy biến; client cần logic/policy hiểu key đó và vẫn phải xét status, deadline và tính idempotent.

## Tổng kết

**Trailers** là phần metadata cuối cùng của một gRPC RPC, nơi runtime gửi **grpc-status** và có thể kèm mô tả hoặc custom trailing metadata. Chúng khác initial response headers và khác protobuf response message: message mang dữ liệu nghiệp vụ, còn trailers mô tả kết quả kết thúc và hỗ trợ chẩn đoán. Trong Spring gRPC, server có thể gắn trailers qua **Status.asRuntimeException(Metadata)** hoặc **ServerInterceptor/ServerCall.close(...)**; client đọc trailers lỗi từ **StatusRuntimeException** và quan sát mọi kết quả qua **ClientCall.Listener.onClose(...)**. Hãy giữ metadata ngắn, an toàn, tùy chọn khi transport lỗi, và kiểm thử cả thành công, lỗi lẫn streaming.

