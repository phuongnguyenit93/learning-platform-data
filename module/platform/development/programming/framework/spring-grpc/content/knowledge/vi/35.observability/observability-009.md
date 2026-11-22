# Log request ID và method name

Khi một request đi qua nhiều service, log riêng lẻ thường không đủ để hiểu toàn bộ luồng xử lý. Một service có thể ghi “đã nhận request”, service khác ghi “dependency timeout”, nhưng nếu thiếu khóa liên kết và tên method thống nhất thì khó tìm đúng các dòng log thuộc cùng một operation. Với gRPC, request ID có thể được truyền qua metadata, còn method name có thể lấy trực tiếp từ Protobuf method descriptor. Kết hợp hai trường này giúp log có thể tìm kiếm và đối chiếu xuyên suốt client/server.

**Log request ID và method name** là cách ghi correlation identifier và tên RPC vào log có cấu trúc tại các ranh giới client/server, đồng thời truyền request ID qua các hop gRPC. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là định nghĩa vòng đời request ID, validate metadata đầu vào, lấy full method name từ descriptor, duy trì MDC/context đúng thread và tránh lộ dữ liệu nhạy cảm trong log.

## 1. Request ID dùng để liên kết log

Request ID là một định danh tương quan cho một request hoặc logical operation. Khi request đi từ gateway tới service A, rồi A gọi B và C, các log có thể cùng mang một request ID để người vận hành tìm toàn bộ đường đi.

Ví dụ:

~~~text
request_id=01JQ8F7M2K grpc_method=orders.OrderService/CreateOrder event=started
request_id=01JQ8F7M2K grpc_method=inventory.Inventory/Reserve event=started
request_id=01JQ8F7M2K grpc_method=inventory.Inventory/Reserve event=completed status=OK
request_id=01JQ8F7M2K grpc_method=orders.OrderService/CreateOrder event=completed status=OK
~~~

Request ID không nhất thiết là một UUID. Nó có thể là ULID, UUID hoặc một chuỗi ngẫu nhiên có entropy đủ lớn. Quan trọng là:

- Không chứa thông tin cá nhân hoặc dữ liệu nghiệp vụ.
- Không dự đoán được nếu định danh có thể xuất hiện trong môi trường bên ngoài.
- Có giới hạn độ dài và bộ ký tự.
- Ổn định trong phạm vi logical operation cần liên kết.
- Không được dùng làm metric label vì mỗi request thường tạo một giá trị mới.

Request ID giúp tìm log; nó không tự tạo distributed trace và không thay thế trace context.

## 2. Phân biệt request ID với trace ID và span ID

Ba định danh này có mục đích khác nhau:

| Trường | Phạm vi | Mục đích |
| --- | --- | --- |
| request_id | Một request/logical operation theo quy ước ứng dụng | Tìm các log liên quan trong nhiều service. |
| trace_id | Một distributed trace | Liên kết các span của một lần trace. |
| span_id | Một span trong trace | Xác định một đoạn công việc cụ thể. |

Một request ID có thể được giữ nguyên qua nhiều RPC fan-out và retry thuộc cùng operation. Trace ID cũng thường được giữ trong cùng trace, nhưng span ID thay đổi theo từng span. Sampling có thể khiến trace không được ghi đầy đủ, trong khi request ID vẫn hữu ích trong log.

Không gán request ID vào trường trace ID hoặc ngược lại. Khi có OpenTelemetry, log nên có cả request_id, trace_id và span_id nếu các giá trị tương ứng tồn tại. Request ID là correlation field của ứng dụng; trace/span ID tuân theo W3C Trace Context và OpenTelemetry.

## 3. Xác định phạm vi và vòng đời request ID

Trước khi triển khai interceptor, cần thống nhất request ID đại diện cho điều gì:

- Nếu request đi vào từ HTTP gateway rồi gọi nhiều service gRPC, gateway có thể tạo request ID tại ingress và truyền xuyên suốt operation.
- Nếu một client gọi một RPC độc lập, client có thể tạo request ID khi bắt đầu logical call.
- Nếu một operation gọi song song nhiều service, các child RPC có thể dùng chung request ID để liên kết log fan-out.
- Nếu gRPC retry một logical call, các attempt nên giữ cùng request ID; attempt number là thuộc tính riêng trong trace/telemetry.
- Nếu một message/event được xử lý độc lập sau khi operation ban đầu kết thúc, event có thể cần correlation ID riêng hoặc parent operation ID theo quy ước nghiệp vụ.

Không tạo request ID mới tại mỗi service hop. Làm như vậy khiến log không thể tìm xuyên chuỗi. Cũng không dùng chung một request ID toàn cục cho mọi request; nó phải được tạo theo từng logical operation.

Ở ranh giới tin cậy bên ngoài, request ID do caller gửi là dữ liệu không đáng tin cậy. Gateway có thể luôn sinh ID nội bộ mới và lưu external correlation value đã validate ở một trường riêng nếu thật sự cần. Với traffic nội bộ, có thể giữ request ID hợp lệ đã được tạo tại ingress.

## 4. Truyền request ID bằng gRPC metadata

gRPC metadata là kênh key/value đi kèm một RPC. Có thể dùng key ứng dụng như x-request-id:

~~~text
x-request-id: 01JQ8F7M2K
~~~

Metadata key phải viết chữ thường. Không dùng prefix grpc- cho custom key vì đây là vùng tên dành cho gRPC. Với request ID dạng text, dùng Metadata.ASCII_STRING_MARSHALLER. Không dùng binary marshaller cho ID dạng chuỗi.

Không forward toàn bộ inbound metadata sang downstream một cách mù quáng. Chỉ truyền các key đã được cho phép, bao gồm request ID và các propagation fields cần thiết. Authorization metadata, cookie hoặc thông tin riêng tư phải tuân theo chính sách bảo mật riêng.

Nếu metadata không có request ID hoặc giá trị không hợp lệ, service ở trust boundary nên tạo ID mới. Không ghi raw giá trị sai định dạng vào log; chuỗi do caller cung cấp có thể chứa ký tự điều khiển hoặc nội dung cố tình gây log injection.

## 5. Validate request ID trước khi ghi log

Một quy tắc đơn giản là cho phép chữ cái ASCII, chữ số, dấu chấm, gạch dưới và gạch ngang, với độ dài tối đa 128 ký tự. Quy tắc cụ thể phải thống nhất giữa gateway và các service:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class RequestIds {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,128}");

    private RequestIds() {}

    public static boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }

    public static String validOrNew(String candidate) {
        return isValid(candidate)
                ? candidate
                : UUID.randomUUID().toString();
    }
}
~~~

Validation không biến request ID thành credential. Caller vẫn có thể tự chọn một giá trị hợp lệ; do đó không dùng request ID để xác thực, phân quyền hoặc truy cập dữ liệu. Nếu cần chống giả mạo correlation ID từ bên ngoài, gateway phải xác lập ID nội bộ và chỉ tin header từ các upstream đã được xác thực.

## 6. Lấy method name từ Protobuf descriptor

Không cần tự parse URL hoặc lấy tên method từ payload. gRPC cung cấp tên đầy đủ của method qua MethodDescriptor:

~~~java
String fullMethod =
        call.getMethodDescriptor().getFullMethodName();
~~~

Ví dụ full method name:

~~~text
inventory.Inventory/GetStock
orders.OrderService/CreateOrder
~~~

Tên đầy đủ gồm package/service và method, giúp phân biệt các service có method trùng tên. Ở client, lấy cùng thông tin từ đối số MethodDescriptor của ClientInterceptor.

Nên log trường grpc_method với full method name. Nếu cần phân nhóm, có thể tách service và method thành hai field có cấu trúc, nhưng không nên chỉ log method ngắn như Get vì nhiều service có thể cùng tên.

## 7. Structured logging và MDC

Log nên là bản ghi có các field ổn định thay vì một câu text phải phân tích lại:

~~~json
{
  "event": "grpc.server.completed",
  "request_id": "01JQ8F7M2K",
  "grpc_method": "inventory.Inventory/GetStock",
  "grpc_status": "OK",
  "duration_ms": 18
}
~~~

Các field hữu ích:

- event: rpc.started, rpc.completed, rpc.cancelled hoặc một event nghiệp vụ rõ nghĩa.
- request_id: correlation ID đã validate.
- grpc_method: full Protobuf method name.
- grpc_status: terminal status code khi call kết thúc.
- duration_ms: thời lượng ở đúng ranh giới đo.
- trace_id/span_id: nếu OpenTelemetry context có mặt.
- service.name và deployment/environment: do logging/telemetry resource cung cấp.

SLF4J MDC cho phép gắn request_id vào log của thread hiện tại. JSON encoder có thể đưa MDC fields thành các thuộc tính riêng. MDC là thread-local; nó không tự động đi theo task sang executor khác. Mỗi lần attach phải restore giá trị cũ trong finally để không làm request sau trên cùng thread nhận nhầm ID.

## 8. Context holder dùng chung cho gRPC

Có thể giữ request ID trong io.grpc.Context để các interceptor và handler downstream đọc được:

~~~java
import io.grpc.Context;
import io.grpc.Metadata;
import org.slf4j.MDC;

import java.util.UUID;
import java.util.function.Supplier;

public final class GrpcRequestContext {

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");

    public static final Metadata.Key<String> REQUEST_ID_HEADER =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    private GrpcRequestContext() {}

    public static String resolve(String incoming) {
        return RequestIds.validOrNew(incoming);
    }

    public static <T> T call(
            Context grpcContext,
            String requestId,
            Supplier<T> action) {

        Context previous = grpcContext.attach();
        String previousMdc = MDC.get("request_id");
        try {
            MDC.put("request_id", requestId);
            return action.get();
        } finally {
            if (previousMdc == null) {
                MDC.remove("request_id");
            } else {
                MDC.put("request_id", previousMdc);
            }
            grpcContext.detach(previous);
        }
    }

    public static void run(
            Context grpcContext,
            String requestId,
            Runnable action) {
        call(grpcContext, requestId, () -> {
            action.run();
            return null;
        });
    }
}
~~~

Helper attach gRPC Context và MDC cho đúng đoạn code thực thi, rồi restore cả hai. Không giữ MDC bằng cách chỉ gọi put mà quên remove/restore. Nếu thread pool tái sử dụng thread, lỗi này có thể làm request ID rò từ request trước sang request sau.

## 9. ServerInterceptor log request ID và method

ServerInterceptor là ranh giới phù hợp để:

1. Đọc x-request-id từ inbound metadata.
2. Validate hoặc tạo ID mới.
3. Lấy full method name từ descriptor.
4. Đưa request ID vào gRPC Context.
5. Ghi log bắt đầu và terminal event.
6. Attach context/MDC khi listener callbacks chạy.

~~~java
import io.grpc.Context;
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class RequestLoggingServerInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestLoggingServerInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = GrpcRequestContext.resolve(
                headers.get(GrpcRequestContext.REQUEST_ID_HEADER));
        String method =
                call.getMethodDescriptor().getFullMethodName();
        Context requestContext =
                Context.current().withValue(
                        GrpcRequestContext.REQUEST_ID,
                        requestId);
        long startedNanos = System.nanoTime();
        AtomicBoolean terminalLogged = new AtomicBoolean();

        Consumer<Status> logTerminal = status -> {
            if (terminalLogged.compareAndSet(false, true)) {
                long durationMs =
                        (System.nanoTime() - startedNanos) / 1_000_000;
                GrpcRequestContext.run(requestContext, requestId, () ->
                        log.info(
                                "grpc.server.completed request_id={} grpc_method={} grpc_status={} duration_ms={}",
                                requestId, method,
                                status.getCode().name(), durationMs));
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(
                            Status status,
                            Metadata trailers) {
                        logTerminal.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> delegate;
        try {
            delegate = GrpcRequestContext.call(
                    requestContext,
                    requestId,
                    () -> {
                        log.info(
                                "grpc.server.started request_id={} grpc_method={}",
                                requestId, method);
                        return next.startCall(monitoredCall, headers);
                    });
        } catch (RuntimeException failure) {
            logTerminal.accept(Status.fromThrowable(failure));
            throw failure;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(delegate) {
            @Override
            public void onMessage(ReqT message) {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> super.onMessage(message));
            }

            @Override
            public void onHalfClose() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onHalfClose);
            }

            @Override
            public void onReady() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onReady);
            }

            @Override
            public void onCancel() {
                logTerminal.accept(Status.CANCELLED);
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onCancel);
            }

            @Override
            public void onComplete() {
                GrpcRequestContext.run(
                        requestContext, requestId,
                        super::onComplete);
            }
        };
    }
}
~~~

AtomicBoolean bảo đảm terminal log chỉ được ghi một lần nếu onCancel và close xảy ra gần nhau. Nếu onCancel đến trước, server log status CANCELLED vì đó là trạng thái server quan sát; client có thể thấy DEADLINE_EXCEEDED khi deadline hết. Đừng diễn giải server cancellation log thành nguyên nhân chắc chắn nếu không có thêm bằng chứng.

Ví dụ ghi log bằng placeholder để dễ đọc; trong production, cấu hình JSON encoder đưa MDC thành field riêng hoặc dùng structured key/value logging của logger. Không log request payload trong interceptor này.

## 10. ClientInterceptor truyền request ID xuống server

ClientInterceptor đọc ID từ gRPC Context nếu call là downstream của một request đang xử lý. Nếu không có, nó tạo ID mới cho logical call và đưa vào metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(RequestIdClientInterceptor.class);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                String requestId = GrpcRequestContext.resolve(
                        GrpcRequestContext.REQUEST_ID.get());
                String methodName = method.getFullMethodName();
                Context requestContext = Context.current().withValue(
                        GrpcRequestContext.REQUEST_ID,
                        requestId);
                long startedNanos = System.nanoTime();

                headers.discardAll(
                        GrpcRequestContext.REQUEST_ID_HEADER);
                headers.put(
                        GrpcRequestContext.REQUEST_ID_HEADER,
                        requestId);

                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> log.info(
                                "grpc.client.started request_id={} grpc_method={}",
                                requestId, methodName));

                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onHeaders(Metadata responseHeaders) {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> super.onHeaders(responseHeaders));
                            }

                            @Override
                            public void onMessage(RespT message) {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> super.onMessage(message));
                            }

                            @Override
                            public void onReady() {
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        super::onReady);
                            }

                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                long durationMs = TimeUnit.NANOSECONDS
                                        .toMillis(System.nanoTime()
                                                - startedNanos);
                                GrpcRequestContext.run(
                                        requestContext, requestId,
                                        () -> {
                                            log.info(
                                                    "grpc.client.completed request_id={} grpc_method={} grpc_status={} duration_ms={}",
                                                    requestId, methodName,
                                                    status.getCode().name(),
                                                    durationMs);
                                            super.onClose(status, trailers);
                                        });
                            }
                        };
                GrpcRequestContext.run(
                        requestContext, requestId,
                        () -> super.start(monitored, headers));
            }
        };
    }
}
~~~

Nếu request ID đã được đặt trong Context ở ingress, downstream call giữ cùng ID. Nếu không, interceptor tạo một ID cho call. Trong một operation có nhiều RPC độc lập, application nên tạo Context scope ở ranh giới operation để các call đó dùng chung ID thay vì để mỗi call tự sinh một ID khác.

Với retry nội bộ của gRPC, metadata của logical call thường được sử dụng cho các attempts của call đó; không tạo request ID mới ở mỗi attempt. Nếu cần nhận diện từng attempt, dùng attempt span/attribute hoặc field telemetry riêng, không thay request ID của operation.

## 11. Propagate context qua executor và streaming callback

gRPC Context và MDC không tự động được bảo đảm trong mọi executor tùy biến. Nếu handler chuyển công việc sang thread pool, capture context khi submit task:

~~~java
Context captured = Context.current();
executor.execute(captured.wrap(() -> {
    inventoryClient.getStock(request);
}));
~~~

Khi callback chạy trong context đã wrap, ClientInterceptor có thể đọc request ID và tiếp tục truyền xuống service kế tiếp. Nếu task cần MDC cho log, dùng helper GrpcRequestContext.run hoặc logging context propagation phù hợp.

Streaming listener có nhiều callback như onMessage, onHalfClose, onReady, onCancel và onComplete. Mỗi callback có thể chạy trên thread khác; chỉ attach MDC quanh startCall không đủ. Server interceptor ở trên bọc các callback để request ID sẵn sàng trong log của service khi callback được gọi.

Không dùng static mutable variable để giữ request ID hiện tại. Nhiều RPC có thể chạy đồng thời trên cùng process; static field sẽ làm request này ghi nhầm ID của request khác.

## 12. Spring gRPC: đăng ký interceptor theo lifecycle

Trong ứng dụng Spring, có thể khai báo interceptor như bean, sau đó đăng ký qua extension point mà starter đang dùng cung cấp:

~~~java
@Configuration
class GrpcRequestLoggingConfiguration {

    @Bean
    RequestLoggingServerInterceptor requestLoggingServerInterceptor() {
        return new RequestLoggingServerInterceptor();
    }

    @Bean
    RequestIdClientInterceptor requestIdClientInterceptor() {
        return new RequestIdClientInterceptor();
    }
}
~~~

Đoạn trên chỉ tạo bean. Cần xác minh starter/version có tự phát hiện bean interceptor hay yêu cầu cấu hình server/channel builder riêng. Đăng ký đúng vào server/channel do starter quản lý; không tạo thêm server hoặc ManagedChannel song song chỉ để thêm log.

Nếu dùng OpenTelemetry agent hoặc gRPC instrumentation library, giữ request ID propagation độc lập với trace context propagation. Có thể dùng chung interceptor chain, nhưng không tự ghi đè traceparent hoặc tự tạo trace ID trong request ID interceptor.

## 13. Log lifecycle, không log mọi message ở mức INFO

Với unary RPC, thường chỉ cần log một event bắt đầu và một event kết thúc:

- started: request ID, method, caller/service nếu có trường an toàn.
- completed: request ID, method, status, duration.
- failed: request ID, method, status và error category phù hợp.

Với streaming RPC, log lúc stream bắt đầu và kết thúc. Không ghi một dòng INFO cho từng message; stream nhiều message có thể tạo lượng log lớn, làm tăng chi phí và che khuất lỗi quan trọng. Message count, byte count và active stream nên được đo bằng metrics riêng.

Không log raw request/response payload trong interceptor tổng quát. Payload có thể chứa token, dữ liệu cá nhân, bí mật nghiệp vụ hoặc thông tin thanh toán. Nếu cần debug payload, dùng logging có sampling, redaction theo schema và quyền truy cập giới hạn.

## 14. Kết hợp request ID với trace context

Request ID giúp tìm log; trace context giúp dựng quan hệ span và thời gian giữa các service. Log tốt có thể chứa:

~~~json
{
  "request_id": "01JQ8F7M2K",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "grpc_method": "inventory.Inventory/GetStock",
  "grpc_status": "OK"
}
~~~

Không phải mọi log đều có trace ID: request có thể đến trước khi tracing được khởi tạo, trace có thể bị sampling hoặc một job nền có correlation ID nhưng không có active span. Khi trace context tồn tại, lấy trace_id/span_id từ OpenTelemetry Context hiện tại thay vì tự parse header trong từng service.

Request ID cũng không nên làm metric label. Metrics dùng service/method/status với cardinality hữu hạn; request ID thuộc log và trace. Dùng log search theo request_id rồi mở trace liên quan để xem timeline.

## 15. Bảo mật và trust boundary

Request ID do caller gửi có thể được giả mạo hoặc cố ý tạo nội dung gây hại. Các nguyên tắc:

- Validate độ dài và bộ ký tự trước khi đưa vào MDC/log.
- Không cho phép newline, tab, ký tự điều khiển hoặc JSON fragment tùy ý.
- Không chứa email, username, access token, account number hoặc dữ liệu cá nhân.
- Tại public ingress, cân nhắc tạo request ID nội bộ mới thay vì tin header bên ngoài.
- Nếu cần lưu external request ID, ghi ở field riêng sau khi validate và giới hạn độ dài.
- Không dùng request ID làm authorization input, idempotency key hoặc secret.
- Không forward metadata tùy ý qua trust boundary.

Request ID không phải bí mật; tránh dùng nó làm capability token hoặc URL truy cập tài nguyên riêng tư.

## 16. Kiểm thử request ID và method name

Integration test nên xác minh metadata, context và log fields ở cả client/server:

1. Gửi request với x-request-id hợp lệ; xác minh server đọc đúng ID và log đúng full method name.
2. Gửi request không có ID; xác minh server tạo ID mới, hợp lệ và dùng thống nhất trong start/completed log.
3. Gửi ID quá dài hoặc chứa newline; xác minh giá trị bị thay bằng ID mới và raw input không xuất hiện trong log.
4. Gọi downstream gRPC từ server handler; xác minh client interceptor truyền cùng request ID.
5. Gọi hai downstream service trong cùng operation; xác minh chúng dùng cùng correlation ID.
6. Gọi hai request đồng thời; xác minh MDC của hai request không rò chéo.
7. Chuyển task qua executor; xác minh request ID còn trong log của worker khi context được wrap.
8. Gọi streaming RPC nhiều message; xác minh lifecycle log có một start và một terminal event, không tạo INFO log cho từng message.
9. Gọi hai service có method ngắn trùng tên; xác minh log dùng full method name để phân biệt.

Dùng in-process gRPC server/channel cho test interceptor và metadata. Dùng test logger appender hoặc JSON log encoder để kiểm tra field thực tế; chỉ kiểm tra MDC trong thread test chưa chứng minh JSON output có field request_id. Bổ sung TCP/TLS test khi cần xác minh metadata qua proxy hoặc trust boundary thật.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mỗi service log một request ID khác | Sinh ID mới ở mỗi hop. | Preserve ID hợp lệ qua metadata và Context. |
| Nhiều request có cùng ID | Dùng static/global ID hoặc tái sử dụng sai scope. | Tạo ID tại mỗi logical operation và attach theo request context. |
| Method log chỉ là tên ngắn | Chỉ lấy tên method không có service/package. | Dùng fullMethodName từ descriptor. |
| Request ID của request trước xuất hiện ở request sau | MDC không được restore trên thread pool. | Restore/remove trong finally ở mỗi scope. |
| Downstream log thiếu request ID | Context mất khi chuyển executor hoặc callback. | Capture/wrap gRPC Context và attach MDC. |
| Client retry có nhiều request ID | Sinh ID theo attempt thay vì logical call. | Tạo ID trước retry layer và giữ ổn định cho call. |
| Log bị chèn dòng hoặc cấu trúc sai | Tin raw request ID do caller gửi. | Validate allowlist, độ dài và ký tự. |
| Metrics backend quá nhiều series | Dùng request ID làm label. | Giữ request ID trong log/trace, không dùng làm metric tag. |
| Log lộ dữ liệu nhạy cảm | Ghi toàn bộ metadata hoặc payload. | Allowlist field và redaction theo policy. |

## 18. Bài tập thực hành

1. Tạo metadata key x-request-id và quy tắc validate ID có độ dài tối đa.
2. Viết ServerInterceptor đọc hoặc sinh request ID, lấy full method name và ghi start/completed log.
3. Đưa request ID vào io.grpc.Context và MDC; bảo đảm restore context trong finally.
4. Viết ClientInterceptor truyền request ID xuống downstream gRPC.
5. Gọi hai service nối tiếp và hai service song song; xác minh log liên kết cùng một logical request.
6. Chuyển downstream call qua executor bằng Context.wrap; xác minh request ID còn trong log.
7. Kiểm thử request ID sai định dạng, request đồng thời, retry và streaming lifecycle.
8. Cấu hình structured JSON logging để tìm kiếm theo request_id và grpc_method; đối chiếu với trace_id khi có tracing.

Sau bài này, bạn cần biết cách tạo/validate request ID, truyền nó qua gRPC metadata, lấy method name chính xác từ descriptor và giữ request context qua listener callback/executor. Khi log request_id cùng grpc_method, status, duration và trace context phù hợp, đội vận hành có thể tìm log xuyên service nhanh hơn mà vẫn kiểm soát được dữ liệu nhạy cảm và chi phí log.
