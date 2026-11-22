# Test client interceptor

Client interceptor là lớp xử lý nằm trên client call pipeline của grpc-java. Nó có thể thêm metadata như request ID, bearer token hoặc tracing headers; chuẩn hóa header; ghi nhận method và thời gian gọi; hoặc bọc callback để quan sát kết quả. Khi kiểm thử, cần xác minh interceptor được áp dụng vào đúng call, gửi đúng metadata, giữ nguyên method và CallOptions, không làm rò dữ liệu giữa các request và không thay đổi status ngoài contract.

Trong Spring gRPC, client interceptor thường được gắn vào ManagedChannel hoặc channel bean dùng chung để tạo generated stub. Một bài test chỉ gọi interceptor trực tiếp chưa chứng minh Spring đã đăng ký interceptor vào channel thực tế. Vì vậy nên kết hợp unit test cho logic interceptor, in-process test để xác minh metadata tới server, và Spring context/TCP/TLS test cho wiring cùng transport.

## 1. Client interceptor nằm ở đâu?

Khi generated stub gọi RPC, grpc-java tạo ClientCall từ channel. Client interceptor có thể bọc call đó trước khi request được gửi:

```text
Generated stub
    |
    | method(request)
    v
ClientInterceptor.interceptCall(...)
    |
    | wrap ClientCall
    v
ClientCall.start(responseListener, headers)
    |
    | add/validate metadata
    v
ManagedChannel and transport
    |
    v
gRPC server
```

ClientInterceptor có một method chính là interceptCall(method, callOptions, next). Nó nhận MethodDescriptor, CallOptions và Channel kế tiếp; trả về ClientCall có thể được bọc để can thiệp vào start, request, sendMessage, halfClose hoặc cancel.

Thông thường, metadata được bổ sung trong ClientCall.start vì đây là thời điểm interceptor nhận headers mà caller chuẩn bị gửi. Không sửa payload Protobuf trong interceptor nếu việc đó thuộc contract hoặc business logic; giữ interceptor tập trung vào cross-cutting concerns.

## 2. Vòng đời interceptCall và ClientCall

Một implementation điển hình tạo call tiếp theo rồi bọc bằng ForwardingClientCall:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.function.Supplier;

final class RequestIdClientInterceptor implements ClientInterceptor {
    static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    private final Supplier<String> requestIdSupplier;

    RequestIdClientInterceptor(Supplier<String> requestIdSupplier) {
        this.requestIdSupplier = requestIdSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                if (headers.get(REQUEST_ID) == null) {
                    headers.put(REQUEST_ID, requestIdSupplier.get());
                }
                super.start(responseListener, headers);
            }
        };
    }
}
```

Supplier tạo request ID ở mỗi call thay vì tạo một ID duy nhất trong constructor. Nếu caller đã gửi request ID, ví dụ giữ nguyên ID đó để liên kết trace xuyên nhiều service. Nếu policy yêu cầu server luôn tin ID do gateway tạo, cần xác minh nguồn header trước khi giữ lại; không tin giá trị tùy ý từ client bên ngoài.

Implementation phải gọi super.start đúng một lần. Không giữ Metadata hoặc Listener của một call vào field dùng chung. Một interceptor bean có thể phục vụ nhiều RPC đồng thời.

## 3. Metadata key và quy tắc truyền header

Metadata key phải dùng tên hợp lệ và marshaller phù hợp:

| Loại dữ liệu | Key/marshaller | Lưu ý |
| --- | --- | --- |
| Request ID | ASCII string | Không chứa dữ liệu nhạy cảm |
| Authorization | ASCII string | Không ghi token vào log |
| Trace context | Theo chuẩn tracing đang dùng | Duy trì định dạng nhất quán |
| Binary metadata | Key kết thúc bằng -bin và binary marshaller | Không dùng ASCII marshaller cho bytes |

Tên metadata key thường được viết chữ thường. Với một key đã được định nghĩa, dùng cùng Metadata.Key ở client và server để tránh sai khác về tên hoặc marshaller.

Quyết định khi header đã tồn tại cần rõ ràng:

- Preserve: giữ request ID caller truyền nếu caller thuộc trust boundary phù hợp.
- Replace: xóa giá trị cũ rồi đặt ID do interceptor/gateway tạo.
- Reject: từ chối call nếu header vi phạm format hoặc policy.

Đừng vô tình append thêm giá trị cho một header được thiết kế chỉ có một giá trị. Nếu thay thế, dùng headers.removeAll(KEY) rồi headers.put(KEY, value). Nếu giữ nguyên, kiểm tra headers.get(KEY) trước khi put.

## 4. Giữ nguyên method descriptor và CallOptions

Interceptor không nên làm thay đổi method hoặc các option caller đã cấu hình. Luôn gọi next.newCall(method, callOptions) với đúng hai đối số nhận được, trừ khi có policy được thiết kế rõ ràng để bổ sung option.

CallOptions có thể chứa deadline, executor, compressor, credentials hoặc các option của client call. Ví dụ stub cấu hình deadline:

```java
GreeterGrpc.GreeterBlockingStub boundedStub =
    stub.withDeadlineAfter(250, TimeUnit.MILLISECONDS);

HelloReply reply = boundedStub.sayHello(request);
```

Client interceptor nhận CallOptions chứa deadline đã cấu hình. Test cần xác minh interceptor không vô tình tạo call mới bằng CallOptions.DEFAULT hoặc bỏ qua deadline. Nếu interceptor thêm custom CallOptions.Key, giữ nguyên các option hiện có.

MethodDescriptor cung cấp full method name và kiểu request/response. Có thể dùng nó để gắn policy theo method, nhưng tránh hardcode một method duy nhất nếu interceptor được dùng chung cho nhiều service.

## 5. Unit test interceptor bằng channel giả

Có thể kiểm tra logic interceptCall độc lập bằng Channel giả ghi nhận method, CallOptions và metadata truyền tới ClientCall. Test channel không cần server:

```java
final class CapturingChannel extends Channel {
    private MethodDescriptor<?, ?> observedMethod;
    private CallOptions observedOptions;
    private Metadata observedHeaders;

    @Override
    public String authority() {
        return "test-authority";
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> newCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions) {
        observedMethod = method;
        observedOptions = callOptions;

        return new ClientCall<>() {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {
                observedHeaders = headers;
            }

            @Override public void request(int numMessages) {}
            @Override public void cancel(String message, Throwable cause) {}
            @Override public void halfClose() {}
            @Override public void sendMessage(ReqT message) {}
        };
    }
}
```

Dùng CapturingChannel làm next channel của interceptor, tạo call với method và CallOptions test, gọi start với Metadata, rồi assert:

- Full method name được chuyển tiếp nguyên vẹn.
- CallOptions/deadline được giữ nguyên.
- Request ID được thêm khi header chưa có.
- Header caller cung cấp được preserve hoặc replace đúng policy.
- Supplier được gọi đúng số lần cho mỗi call.

Đây là unit test cho logic bọc call. Nó không xác minh metadata đã đi qua transport hoặc được server nhận; cần in-process test ở phần tiếp theo.

## 6. In-process test xác minh metadata tới server

Để kiểm tra end-to-end trong JVM, tạo server interceptor ghi nhận header, rồi gọi service bằng generated stub gắn client interceptor:

```java
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> receivedRequestId = new AtomicReference<>();

ServerInterceptor captureHeader = new ServerInterceptor() {
    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        receivedRequestId.set(headers.get(
            RequestIdClientInterceptor.REQUEST_ID));
        return next.startCall(call, headers);
    }
};

ServerServiceDefinition observedService =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        captureHeader);

String serverName = InProcessServerBuilder.generateName();
Server server = InProcessServerBuilder.forName(serverName)
    .addService(observedService)
    .build()
    .start();
ManagedChannel channel = InProcessChannelBuilder
    .forName(serverName)
    .build();

Channel intercepted = ClientInterceptors.intercept(
    channel,
    new RequestIdClientInterceptor(() -> "req-test-42"));
GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(intercepted);

HelloReply reply = stub.sayHello(
    HelloRequest.newBuilder().setName("An").build());

assertEquals("req-test-42", receivedRequestId.get());
```

Đây là phần thân minh họa của test; cần đóng channel và server trong try/finally hoặc @AfterEach, với shutdown timeout hữu hạn. Server interceptor quan sát metadata trước khi service handler chạy, vì vậy assertion chứng minh header đã được gửi qua gRPC call pipeline tới server.

Với test nhiều call đồng thời, không dùng một AtomicReference để khẳng định thứ tự request; dùng queue hoặc map keyed by request ID. Test phải xác minh mỗi call nhận đúng header riêng, không rò ID từ call trước.

## 7. Preserve, replace và validation test

Một interceptor request ID nên có test cho cả ba tình huống:

| Input headers | Policy | Kết quả mong đợi |
| --- | --- | --- |
| Không có request ID | Generate | Interceptor thêm ID mới |
| Có ID hợp lệ từ trusted caller | Preserve | Server nhận ID ban đầu |
| Có ID không hợp lệ | Reject hoặc replace | Hành vi theo policy, không mơ hồ |
| Hai call đồng thời | Generate per call | Mỗi call nhận ID độc lập |

Test preserve/replace nên kiểm tra số lượng giá trị của header, không chỉ giá trị đầu tiên. Nếu key được thiết kế single-valued, xóa giá trị cũ trước khi put giá trị mới.

Không dùng request ID làm credential. Request ID chỉ phục vụ correlation; authentication phải dựa trên token/certificate đã xác minh.

## 8. Deadline, error và cancellation

Client interceptor có thể ghi nhận method hoặc thời gian call, nhưng không nên nuốt lỗi. Khi delegate kết thúc bằng onClose với status lỗi, wrapper phải chuyển nguyên status/trailers tới listener caller.

Một interceptor quan sát kết quả có thể bọc ClientCall.Listener:

```java
import io.grpc.ForwardingClientCallListener;
import io.grpc.Status;

return new ForwardingClientCall
        .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
    @Override
    public void start(
            Listener<RespT> responseListener,
            Metadata headers) {
        super.start(new ForwardingClientCallListener
                .SimpleForwardingClientCallListener<RespT>(
                    responseListener) {
            @Override
            public void onClose(Status status, Metadata trailers) {
                // Record method, status and elapsed time.
                super.onClose(status, trailers);
            }
        }, headers);
    }
};
```

Test cần xác minh:

- Deadline từ stub vẫn có hiệu lực sau khi gắn interceptor.
- Status như DEADLINE_EXCEEDED, UNAVAILABLE hoặc UNAUTHENTICATED được chuyển tiếp nguyên vẹn.
- Trailers cần thiết không bị mất.
- Cancellation từ caller được delegate nhận.
- Interceptor không gửi thêm callback hoặc gọi terminal callback hai lần.

Không thực hiện blocking I/O trong start hoặc onClose. Interceptor chạy trên call path; công việc chậm có thể tăng latency hoặc làm cạn executor.

## 9. Thứ tự nhiều client interceptor

Một channel có thể gắn nhiều interceptor cho tracing, metrics, authentication và request metadata. Các wrapper được lồng nhau; thứ tự ảnh hưởng tới header nào được nhìn thấy hoặc ghi nhận ở mỗi lớp.

Ví dụ thứ tự logic:

1. Trace context: lấy hoặc tạo trace/span metadata.
2. Authentication: gắn credential do credential provider cấp.
3. Request ID: giữ hoặc tạo correlation ID.
4. Metrics/logging: ghi method và outcome, đã redaction dữ liệu nhạy cảm.
5. Transport channel: gửi call.

Không suy luận thứ tự thực tế chỉ từ thứ tự bean trong Spring context. API gắn interceptor và helper có thể định nghĩa thứ tự wrapper cụ thể; viết test dùng interceptor ghi event vào queue để xác minh request-side và response-side ordering.

Đặc biệt, logging interceptor không được ghi authorization token. Nếu một interceptor redaction chạy sau logger, secret có thể đã bị ghi trước khi được che.

## 10. Thread safety và vòng đời interceptor

Client interceptor thường được chia sẻ trên nhiều call và nhiều thread. Các quy tắc:

- Tránh mutable field chứa metadata, request ID hoặc listener của call.
- Dùng biến local trong interceptCall/start cho dữ liệu riêng từng call.
- Supplier/token provider phải thread-safe và có timeout rõ ràng.
- Không block trong interceptor để gọi identity service hoặc tracing backend.
- Không lưu Metadata object rồi tái sử dụng giữa nhiều call.
- Bảo đảm cancellation và deadline vẫn đi qua delegate.

Nếu interceptor phụ thuộc token refresh, dùng credential provider có cache/refresh concurrency được quản lý. Không để mọi RPC đồng thời cùng refresh token theo kiểu thundering herd.

Test concurrency có thể gọi nhiều RPC với request ID khác nhau rồi kiểm tra server nhận đủ ID đúng một lần. Dùng executor hữu hạn và deadline để test không treo khi interceptor lỗi.

## 11. Đăng ký interceptor trong Spring gRPC

Trong ứng dụng Spring, client channel thường được tạo qua bean/configuration hoặc starter-specific client factory. Cần xác minh interceptor được gắn vào channel thực sự dùng để tạo stub:

1. Khai báo interceptor bean hoặc cấu hình interceptor theo extension point của starter đang dùng.
2. Tạo ManagedChannel/client channel qua cấu hình Spring.
3. Gắn interceptor vào channel trước khi tạo generated stub, hoặc dùng cơ chế starter hỗ trợ.
4. Inject stub/client vào service bean.
5. Gọi RPC trong Spring context test và xác minh server nhận metadata.
6. Đóng channel khi context dừng nếu ứng dụng sở hữu lifecycle của channel.

Tên property và extension point phụ thuộc phiên bản Spring gRPC starter. Không giả định mọi bean implement ClientInterceptor tự động được gắn vào mọi channel. Test context phải xác minh channel/stub đang dùng thực sự đi qua interceptor.

In-process test chứng minh logic interceptor và metadata propagation trong JVM. TCP/TLS integration test cần thiết để xác minh header qua HTTP/2, proxy, ingress, service mesh, TLS/mTLS và certificate configuration.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Method propagation | Gọi nhiều generated method | MethodDescriptor được chuyển tiếp đúng |
| CallOptions | Stub có deadline | Deadline không bị mất |
| Metadata generate | Caller không gửi request ID | Server nhận ID do interceptor tạo |
| Metadata preserve | Caller gửi ID hợp lệ | Server nhận đúng ID theo policy |
| Metadata replace | Caller gửi ID không hợp lệ | Header cũ được xử lý đúng policy |
| Authentication | Token provider cấp credential | Header được gửi đúng, không log secret |
| Server capture | In-process server interceptor | Quan sát được metadata thực nhận |
| Error propagation | Server trả status lỗi | Caller nhận nguyên status/trailers |
| Cancellation | Caller cancel | Delegate nhận cancellation |
| Ordering | Nhiều interceptor | Request/response order đúng thiết kế |
| Concurrency | Nhiều call đồng thời | Không rò metadata giữa call |
| Spring wiring | Client channel bean | Stub thực tế đi qua interceptor |
| Transport | TCP/TLS | HTTP/2, proxy và certificate hoạt động |

**Bài tập:** OrderClient dùng generated OrderServiceStub. Mọi call phải có x-request-id; bearer token được lấy từ credential provider; deadline do từng use case đặt. Một số caller nội bộ đã có request ID từ gateway và cần giữ nguyên ID đó.

1. Viết RequestIdClientInterceptor chỉ tạo ID khi header chưa có.
2. Viết unit test với CapturingChannel để xác minh method, CallOptions và header.
3. Dựng in-process server với server interceptor ghi nhận request ID.
4. Kiểm tra generate, preserve, replace/reject và hai call đồng thời.
5. Xác minh deadline và status/trailers không bị interceptor làm mất.
6. Gắn authentication interceptor/credential provider và xác minh secret không xuất hiện trong log.
7. Kiểm tra thứ tự tracing, authentication, request ID và metrics interceptor.
8. Viết Spring context test xác minh channel/stub bean thực sự dùng interceptor.
9. Bổ sung TCP/TLS test cho HTTP/2, proxy và certificate nếu hệ thống dùng các thành phần đó.

**Câu hỏi tự kiểm tra:**

- ClientInterceptor nhận những tham số nào trong interceptCall?
- Vì sao metadata thường được sửa trong ClientCall.start?
- Làm thế nào giữ nguyên CallOptions và deadline?
- Khi nào nên preserve hoặc replace request ID?
- Vì sao không lưu Metadata trong field interceptor singleton?
- Làm thế nào chứng minh header thực sự tới server?
- Vì sao test status cần xác minh trailers và cancellation?
- Thứ tự client interceptor ảnh hưởng việc redaction ra sao?
- Vì sao Spring context test cần xác minh channel thực tế thay vì chỉ kiểm tra bean tồn tại?
- Những gì cần TCP/TLS integration test ngoài in-process test?

**Ghi nhớ:** Test client interceptor phải xác minh method và CallOptions được giữ nguyên, metadata được tạo/preserve/replace đúng policy và header thực sự tới server. Dùng CapturingChannel cho logic cô lập, in-process server để kiểm tra propagation, Spring context test cho channel wiring và TCP/TLS test cho transport thật. Giữ interceptor thread-safe, không log secret và không làm mất deadline, status hoặc cancellation.
