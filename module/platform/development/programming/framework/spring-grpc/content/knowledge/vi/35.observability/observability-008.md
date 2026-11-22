# Trace context qua gRPC metadata

Một request thường đi qua nhiều service trước khi trả kết quả cho caller. Log của từng service có thể cho biết lỗi xảy ra ở đâu, nhưng nếu không liên kết được các log và span theo cùng một trace, việc lần theo đường đi của request sẽ khó khăn. gRPC truyền thông tin qua HTTP/2 metadata; đây là nơi phù hợp để chuyển trace context giữa các process và tiếp tục một distributed trace.

**Trace context qua gRPC metadata** là cách truyền định danh trace, span cha và các thuộc tính propagation giữa gRPC client/server bằng metadata của mỗi RPC. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là W3C Trace Context, OpenTelemetry propagator, client/server interceptor, context propagation qua tác vụ bất đồng bộ và giới hạn bảo mật của baggage.

## 1. Trace context giải quyết vấn đề gì?

Một distributed trace biểu diễn đường đi của một operation qua nhiều process. Mỗi trace có một trace_id chung; mỗi span có span_id riêng và có thể tham chiếu span cha. Khi service A gọi service B qua gRPC, B cần nhận được context của operation để tạo span con thuộc cùng trace.

Ví dụ:

~~~text
HTTP request
  └── API service span
        ├── database span
        └── gRPC client span: Inventory.GetStock
              └── gRPC server span: Inventory.GetStock
                    └── downstream gRPC client span
~~~

Nếu context bị mất tại ranh giới gRPC, service B có thể tạo một trace mới. Trace UI khi đó hiển thị hai trace rời rạc dù chúng thuộc cùng một request nghiệp vụ.

Trace context thường mang:

- Trace ID: định danh trace xuyên suốt các service.
- Parent/span context: thông tin span đã tạo ra outbound call.
- Trace flags: ví dụ cờ sampled theo W3C Trace Context.
- Trace state: thông tin vendor-specific được chuẩn hóa theo W3C.
- Baggage: các thuộc tính key/value được truyền theo request nếu ứng dụng cho phép.

Trace context phục vụ observability. Nó không phải danh tính người dùng, credential hoặc bằng chứng authorization.

## 2. gRPC metadata là kênh truyền context

gRPC metadata là tập key/value gắn với một RPC. Client thường gửi metadata cùng request headers; server có thể đọc metadata trong ServerInterceptor hoặc service context. Metadata cũng có thể được gửi dưới dạng response headers/trailers, nhưng trace context đi từ caller tới callee thường được inject vào request metadata ban đầu.

Một số quy tắc quan trọng:

- Metadata key phải dùng chữ thường; key chuẩn trace context là traceparent, tracestate và baggage.
- Giá trị text dùng Metadata.ASCII_STRING_MARSHALLER.
- Key kết thúc bằng -bin dùng binary marshaller cho dữ liệu nhị phân.
- Không tự tạo key trùng lặp cho cùng một trace field; propagator phải thay giá trị cũ theo contract.
- Không ghi đè các HTTP/2 pseudo-header hoặc metadata dành riêng cho transport.
- Metadata có giới hạn kích thước ở client, server và proxy; baggage lớn có thể làm request bị từ chối.

Ví dụ minh họa metadata của một call:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
baggage: tenant-tier=gold,region=apac
~~~

Ứng dụng không nên tự ghép chuỗi traceparent hoặc tự parse trace ID. Dùng OpenTelemetry propagator để xử lý định dạng, validation và sampling flags đúng chuẩn.

## 3. W3C Trace Context và Baggage

W3C Trace Context định nghĩa cách biểu diễn trace context qua các trường traceparent và tracestate.

- traceparent chứa version, trace ID, parent ID và trace flags.
- tracestate mang trạng thái bổ sung theo định dạng vendor-neutral, với quy tắc kích thước và số member.
- baggage là chuẩn riêng để truyền các thuộc tính key/value theo operation; nó không thay thế traceparent.

OpenTelemetry thường cấu hình W3CTraceContextPropagator và W3CBaggagePropagator, có thể ghép bằng composite propagator. Khi nhận context hợp lệ, SDK tạo span tiếp nối trace; khi header thiếu hoặc không hợp lệ, SDK có thể tạo root context mới theo cấu hình instrumentation.

Không dùng baggage để chuyển payload nghiệp vụ hoặc dữ liệu lớn. Baggage thường được truyền tiếp qua nhiều service, do đó một thuộc tính nhạy cảm có thể lan tới nhiều hệ thống log, proxy và telemetry backend.

## 4. Inject và extract là hai thao tác đối xứng

Propagation có hai bước:

1. **Inject ở client:** lấy OpenTelemetry Context.current() rồi ghi các trường propagation vào gRPC Metadata trước khi gửi call.
2. **Extract ở server:** đọc các trường propagation từ inbound Metadata để tạo context hiện tại cho span server và các lời gọi downstream.

~~~mermaid
sequenceDiagram
    participant A as gRPC Client
    participant M as HTTP/2 Metadata
    participant B as gRPC Server
    A->>A: Read current OTel context
    A->>M: Inject traceparent/tracestate/baggage
    M->>B: Send request metadata
    B->>B: Extract remote context
    B->>B: Create server span as child
    B->>B: Propagate context to downstream calls
~~~

Client interceptor chỉ inject; server interceptor chỉ extract. Đừng tạo một trace ID mới ở mỗi service nếu mục tiêu là nối các span trong cùng distributed trace.

## 5. Cấu hình OpenTelemetry propagator

Trong ứng dụng Java, OpenTelemetry API cung cấp TextMapPropagator để inject/extract context qua carrier bất kỳ. Với gRPC, carrier là io.grpc.Metadata.

Ví dụ khởi tạo propagator dùng W3C Trace Context và Baggage:

~~~java
import io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.TextMapPropagator;

TextMapPropagator propagator =
        TextMapPropagator.composite(
                W3CTraceContextPropagator.getInstance(),
                W3CBaggagePropagator.getInstance());
~~~

Trong ứng dụng Spring Boot, nên dùng một OpenTelemetry instance được quản lý tập trung bởi OpenTelemetry SDK/autoconfiguration hoặc starter tương ứng. Không tự tạo SDK riêng trong mỗi interceptor; nếu có nhiều SDK/tracer provider, trace có thể bị chia context và export sang các pipeline khác nhau.

## 6. Tạo TextMapGetter và TextMapSetter cho Metadata

OpenTelemetry propagator không phụ thuộc gRPC trực tiếp. Ta cung cấp adapter để đọc/ghi Metadata:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class GrpcMetadataTextMap {

    private GrpcMetadataTextMap() {}

    public static final TextMapSetter<Metadata> SETTER =
            new TextMapSetter<>() {
                @Override
                public void set(
                        Metadata carrier,
                        String key,
                        String value) {
                    if (carrier == null) {
                        return;
                    }
                    Metadata.Key<String> metadataKey =
                            Metadata.Key.of(
                                    key.toLowerCase(Locale.ROOT),
                                    Metadata.ASCII_STRING_MARSHALLER);
                    carrier.discardAll(metadataKey);
                    carrier.put(metadataKey, value);
                }
            };

    public static final TextMapGetter<Metadata> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Metadata carrier) {
                    if (carrier == null) {
                        return Collections.emptyList();
                    }
                    List<String> textKeys = new ArrayList<>();
                    for (String key : carrier.keys()) {
                        if (!key.endsWith("-bin")) {
                            textKeys.add(key);
                        }
                    }
                    return textKeys;
                }

                @Override
                public String get(Metadata carrier, String key) {
                    if (carrier == null || key == null) {
                        return null;
                    }
                    Metadata.Key<String> metadataKey =
                            Metadata.Key.of(
                                    key.toLowerCase(Locale.ROOT),
                                    Metadata.ASCII_STRING_MARSHALLER);
                    return carrier.get(metadataKey);
                }
            };
}
~~~

Setter xóa giá trị cũ của cùng key trước khi thêm giá trị mới để tránh nhiều bản traceparent hoặc tracestate trong một carrier. Getter trả về các key metadata hiện có; propagator chỉ đọc những key mà nó hỗ trợ.

Adapter này dành cho các propagation fields dạng ASCII. Không dùng ASCII marshaller cho key -bin; W3C trace context và baggage là text fields. Metadata key phải hợp lệ theo quy tắc gRPC; không cho phép dữ liệu tùy ý tạo key binary hoặc key dành riêng.

## 7. Inject trace context ở gRPC client

ClientInterceptor đọc OpenTelemetry context tại thời điểm call bắt đầu và inject vào metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

public final class TraceContextClientInterceptor
        implements ClientInterceptor {

    private final TextMapPropagator propagator;

    public TraceContextClientInterceptor(
            TextMapPropagator propagator) {
        this.propagator = propagator;
    }

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
                propagator.inject(
                        Context.current(),
                        headers,
                        GrpcMetadataTextMap.SETTER);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Đọc Context.current() trong start() giúp lấy context đang hoạt động tại thời điểm stub thực sự gọi RPC. Nếu inject từ lúc tạo channel hoặc tạo stub, context có thể không thuộc request hiện tại.

Gắn interceptor vào channel qua ManagedChannelBuilder.intercept(...) hoặc extension point của Spring gRPC starter. Nếu OpenTelemetry gRPC instrumentation đã tự động inject metadata, không thêm interceptor thủ công thứ hai có cùng chức năng; duplicate propagation headers có thể gây hành vi khó đoán.

## 8. Extract trace context ở gRPC server

ServerInterceptor extract context từ metadata trước khi gọi service handler. Cần duy trì OTel context trong lúc handler được gọi và trong các callback của listener:

~~~java
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;

public final class TraceContextServerInterceptor
        implements ServerInterceptor {

    private final TextMapPropagator propagator;

    public TraceContextServerInterceptor(
            TextMapPropagator propagator) {
        this.propagator = propagator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        io.opentelemetry.context.Context extracted =
                propagator.extract(
                        io.opentelemetry.context.Context.current(),
                        headers,
                        GrpcMetadataTextMap.GETTER);

        ServerCall.Listener<ReqT> delegate;
        try (Scope ignored = extracted.makeCurrent()) {
            delegate = next.startCall(call, headers);
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(delegate) {
            @Override
            public void onMessage(ReqT message) {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onMessage(message);
                }
            }

            @Override
            public void onHalfClose() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onHalfClose();
                }
            }

            @Override
            public void onReady() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onReady();
                }
            }

            @Override
            public void onCancel() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onCancel();
                }
            }

            @Override
            public void onComplete() {
                try (Scope ignored = extracted.makeCurrent()) {
                    super.onComplete();
                }
            }
        };
    }
}
~~~

Ví dụ trên dùng OpenTelemetry Context và Scope; không nhầm chúng với io.grpc.Context, là một context system khác của gRPC Java. Interceptor này chỉ extract và attach parent context; bản thân propagator không tạo server span. Trong production, cần có OpenTelemetry gRPC instrumentation tạo server span từ extracted parent, hoặc tự tạo span bằng Tracer rồi attach context chứa span đó. Nếu service handler gọi downstream gRPC ngay trong callback, context đang attach sẽ được client interceptor đọc và inject tiếp.

Nếu tự tạo server span, thứ tự logic là: extract remote parent, tạo span với kind SERVER và parent là extracted context, tạo server context bằng extracted.with(serverSpan), attach server context trong handler/listener callbacks, rồi end span đúng một lần khi call complete/cancel. Dùng một atomic guard cho terminal callbacks để không end span hai lần. Không coi việc gọi propagator.extract là đã tạo server span.

Trong hệ thống production, ưu tiên OpenTelemetry gRPC instrumentation đã được kiểm chứng nếu nó tự tạo server/client spans và quản lý context callback. Code thủ công ở đây minh họa cơ chế metadata propagation; không cài song song với auto instrumentation nếu chưa xác định rõ thành phần nào chịu trách nhiệm tạo span và inject/extract.

## 9. Context propagation qua executor và tác vụ bất đồng bộ

Context chỉ có hiệu lực trong scope hiện tại. Nếu handler chuyển công việc sang executor, thread mới không tự động kế thừa OTel context:

~~~java
io.opentelemetry.context.Context captured =
        io.opentelemetry.context.Context.current();

executor.execute(captured.wrap(() -> {
    inventoryClient.getStock(request);
}));
~~~

captured.wrap(...) attach context đã chụp khi task chạy và khôi phục context trước đó sau khi task hoàn tất. Điều này giúp client interceptor inject đúng trace context cho downstream RPC.

Nếu dùng CompletableFuture, reactive pipeline hoặc scheduler của framework, dùng integration/context propagation chính thức của framework hoặc capture context tại thời điểm submit task. Không giữ một Context toàn cục trong singleton service; context phải gắn với từng request/call.

Đối với streaming RPC, callback onMessage, onHalfClose, onReady và cancellation có thể chạy trên thread khác nhau. Phải bảo đảm context được attach ở từng callback hoặc dùng instrumentation đã xử lý lifecycle này. Chỉ attach context quanh next.startCall không đủ để bảo đảm callback tương lai có context.

## 10. Spring gRPC và OpenTelemetry: chọn một cơ chế propagation

Trong ứng dụng Spring, thường có hai cách:

1. **Automatic instrumentation:** OpenTelemetry Java agent hoặc gRPC instrumentation library tạo spans và inject/extract context tự động.
2. **Manual interceptor:** ứng dụng tự đăng ký client/server interceptor và dùng TextMapPropagator.

Automatic instrumentation thường là lựa chọn đầu tiên vì đã xử lý call lifecycle, context và semantic conventions theo phiên bản thư viện. Manual interceptor phù hợp khi runtime chưa có instrumentation tương ứng hoặc ứng dụng cần tích hợp đặc thù.

Không bật cả hai cơ chế mà không kiểm tra. Có thể tạo span trùng, inject metadata trùng hoặc tạo quan hệ parent-child sai. Hãy xác minh:

- Có đúng một thành phần tạo client/server span cho mỗi RPC boundary.
- Outbound call mang trace context của span hiện tại.
- Inbound call extract context trước khi server span được tạo hoặc gắn đúng parent.
- Callback streaming và task async vẫn thấy context.
- Trace được export về đúng collector/backend.

Với Spring Boot, cấu hình OpenTelemetry SDK/agent theo lifecycle ứng dụng. Không tạo SDK hoặc TracerProvider mới bên trong interceptor.

## 11. Baggage: hữu ích nhưng cần kiểm soát

Baggage truyền key/value xuyên qua service graph. Ví dụ tenant-tier=gold hoặc region=apac có thể giúp áp dụng sampling/diagnostic policy, nhưng baggage cũng có thể bị forward tới nhiều downstream service.

Quy tắc vận hành:

- Chỉ cho phép một allowlist key có mục đích rõ ràng.
- Không đưa access token, session cookie, email, số điện thoại, dữ liệu cá nhân hoặc payload nghiệp vụ vào baggage.
- Giới hạn số key, độ dài value và tổng kích thước.
- Không dùng baggage làm nguồn xác thực/authorization; client có thể tự gửi metadata.
- Không biến baggage value thành metric label nếu cardinality không được kiểm soát.
- Xem xét bỏ baggage ở ranh giới trust domain hoặc khi gọi external service.

Trace context cũng không đáng tin cậy để quyết định quyền truy cập. Caller có thể tự tạo traceparent; nó chỉ định danh trace/span, không chứng minh request đến từ một principal hợp lệ.

## 12. Metadata limits, validation và lỗi propagation

Metadata đi qua client, server, proxy và load balancer; mỗi thành phần có thể áp dụng giới hạn tổng kích thước. Baggage quá lớn hoặc metadata dư thừa có thể khiến request bị từ chối trước khi tới handler.

Một số nguyên tắc:

- Chỉ truyền các field propagation chuẩn mà hệ thống cần.
- Không copy toàn bộ inbound metadata sang downstream một cách mù quáng.
- Dùng propagator để validate traceparent/tracestate thay vì tự parse.
- Giữ trace context ở dạng ASCII metadata; binary application metadata dùng key -bin riêng.
- Không ghi raw metadata vào log vì có thể chứa token hoặc thông tin nhạy cảm.
- Nếu trace context thiếu hoặc sai định dạng, xử lý theo propagator (thường tạo context mới) và không làm hỏng RPC nghiệp vụ chỉ vì tracing header không hợp lệ.

Nếu cần truyền custom correlation ID ngoài W3C trace context, định nghĩa metadata key riêng, giới hạn định dạng/độ dài và xác định rõ trust boundary. Không dùng custom ID thay cho trace/span IDs của OpenTelemetry.

## 13. Quan sát propagation thành công

Có thể xác minh trace propagation bằng một request xuyên qua hai service:

1. Client A tạo một root/server span cho request đầu vào.
2. A gọi gRPC service B; client span là child của context hiện tại.
3. Client interceptor inject traceparent vào metadata.
4. Server interceptor B extract context; server span của B nối vào trace của A.
5. B gọi downstream C; client interceptor tiếp tục inject context từ span hiện tại.
6. Trace backend hiển thị các span trong cùng một trace ID với parent-child relationship hợp lý.

Các dấu hiệu lỗi:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Service B tạo trace ID mới | Metadata không được inject hoặc server không extract. | Kiểm tra traceparent tại client/server boundary. |
| Hai server spans cùng trace nhưng parent sai | Context bị attach sai thời điểm hoặc span được tạo trước extract. | Kiểm tra thứ tự interceptor và auto instrumentation. |
| Có hai server spans cho một RPC | Manual và automatic instrumentation cùng tạo span. | Kiểm tra agent, starter và interceptor registration. |
| Downstream span trở thành root | Context mất khi chuyển executor/thread. | Capture và wrap OTel Context cho task. |
| Baggage không tới downstream | Propagator chưa bật baggage hoặc policy đã lọc key. | Kiểm tra composite propagator và allowlist. |
| RPC bị từ chối do metadata lớn | Baggage/metadata vượt giới hạn proxy hoặc server. | Đo kích thước metadata và loại bỏ field thừa. |

## 14. Kiểm thử trace context qua gRPC metadata

Integration test nên kiểm tra cả nội dung metadata lẫn quan hệ trace:

1. Tạo một OTel context có trace/span hợp lệ, gọi client stub và xác minh outbound metadata có traceparent.
2. Gửi metadata traceparent vào server test; xác minh handler chạy với extracted trace ID.
3. Gọi downstream gRPC trong handler; xác minh context được inject tiếp.
4. Gọi handler qua executor; xác minh Context.wrap giữ trace context trên worker thread.
5. Kiểm thử server-streaming/bidirectional callbacks để xác minh context tồn tại ở onMessage và onHalfClose.
6. Gửi traceparent sai định dạng; xác minh propagator không làm hỏng business RPC và tracing tạo context phù hợp.
7. Gửi baggage ngoài allowlist hoặc vượt giới hạn; xác minh policy lọc/từ chối đúng cách.
8. Bật auto instrumentation cùng manual interceptor trong môi trường test; xác minh không tạo span trùng, sau đó chọn một cơ chế production.

Có thể dùng in-process gRPC server/channel cho test propagation logic. Bổ sung test qua TCP/TLS và proxy nếu cần xác minh metadata size limit hoặc hành vi của hạ tầng thực. Không chỉ kiểm tra rằng header tồn tại; phải kiểm tra trace ID và parent-child relationship ở backend hoặc test exporter.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mỗi service tạo trace riêng | Thiếu inject/extract hoặc sai metadata carrier. | Dùng W3C propagator ở client/server interceptor. |
| traceparent bị lặp trong metadata | Setter append mà không thay giá trị cũ. | discardAll cùng key trước khi put hoặc dùng instrumentation chuẩn. |
| Context mất trong async task | Thread/executor không tự kế thừa OTel Context. | Capture và wrap task hoặc dùng framework context propagation. |
| Streaming callback không có trace context | Chỉ attach context khi gọi startCall. | Attach context trong từng listener callback hoặc dùng auto instrumentation. |
| Có hai span cho một RPC | Agent và manual interceptor cùng instrument. | Chọn một cơ chế span creation/propagation. |
| Baggage gây metadata quá lớn | Truyền quá nhiều key/value hoặc payload. | Allowlist và giới hạn kích thước. |
| Dùng trace ID để authorization | Nhầm observability context với security identity. | Xác thực principal bằng cơ chế authentication riêng. |
| Log raw metadata làm lộ dữ liệu | Metadata có thể chứa credential hoặc PII. | Redact và chỉ log field đã được cho phép. |

## 16. Bài tập thực hành

1. Tạo W3C TextMapPropagator gồm Trace Context và Baggage.
2. Viết TextMapGetter/TextMapSetter adapter cho gRPC Metadata.
3. Viết ClientInterceptor inject trace context vào outbound RPC metadata.
4. Viết ServerInterceptor extract context và attach vào handler/listener callbacks.
5. Tạo hai Spring gRPC service gọi nối tiếp; xác minh các spans thuộc cùng trace ID.
6. Chuyển một downstream call qua executor; dùng Context.wrap để giữ parent context.
7. Thử baggage allowlist, giới hạn metadata size và trường hợp traceparent không hợp lệ.
8. Kiểm tra auto instrumentation và manual interceptor để bảo đảm không tạo duplicate spans.

Sau bài này, bạn cần biết cách inject/extract W3C trace context qua gRPC metadata, giữ OTel context qua listener callback và executor, cũng như giới hạn baggage theo trust/security policy. Khi propagation được cấu hình đúng, trace backend có thể nối client/server/downstream spans thành một distributed trace xuyên suốt hệ thống Spring gRPC.
