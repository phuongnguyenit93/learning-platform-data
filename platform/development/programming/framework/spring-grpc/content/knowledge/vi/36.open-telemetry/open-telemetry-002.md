# Propagator qua metadata

**Chương:** OpenTelemetry  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào cách OpenTelemetry propagator truyền trace context qua gRPC metadata, để các span ở nhiều service được nối vào cùng một distributed trace.

## 1. Vì sao phải propagate context?

Khi một client gọi Order service, rồi Order service gọi Inventory service, mỗi tiến trình có thể tạo span riêng. Nếu không truyền thông tin liên kết qua ranh giới RPC, backend tracing có thể hiển thị các span như những trace độc lập. Người vận hành sẽ khó biết chúng thuộc cùng một request.

OpenTelemetry Context mang thông tin telemetry hiện tại, thường gồm SpanContext của span đang hoạt động và có thể gồm baggage. Propagator chuyển phần context cần truyền thành các trường trên carrier của giao thức. Với gRPC, carrier đó là Metadata của RPC.

Hai thao tác cốt lõi:

- **Inject:** phía gọi ghi trace context từ OpenTelemetry Context vào metadata outbound.
- **Extract:** phía nhận đọc metadata inbound và dựng OpenTelemetry Context tương ứng.

Luồng này truyền ngữ cảnh liên kết trace; nó không gửi toàn bộ object Context qua mạng và không thay thế authentication, authorization hoặc gRPC Context.

~~~mermaid
sequenceDiagram
    participant A as Order client
    participant M as gRPC metadata
    participant B as Inventory server
    A->>A: Current span / SpanContext
    A->>M: Propagator inject(traceparent, tracestate)
    M->>B: HTTP/2 metadata
    B->>B: Propagator extract
    B->>B: Create server span with remote parent
    B-->>A: RPC response
~~~

Khi context được propagate đúng, span client và span server có cùng trace ID; server span có quan hệ parent với span phía client theo quy ước instrumentation.

## 2. W3C Trace Context gồm những gì?

W3C Trace Context là định dạng phổ biến để truyền danh tính trace qua các hệ thống. Hai header thường gặp:

| Header | Vai trò |
| --- | --- |
| traceparent | Mang version, trace ID, parent span ID và trace flags |
| tracestate | Mang thông tin vendor-specific được chuẩn hóa theo quy tắc W3C |

Ví dụ giá trị traceparent:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Giá trị này chứa trace ID, span ID của thao tác cha và sampling flag. Ứng dụng không nên tự parse hoặc tự ghép chuỗi này. W3C propagator chịu trách nhiệm kiểm tra định dạng, inject và extract theo chuẩn.

OpenTelemetry thường dùng W3C Trace Context propagator. Nếu cần truyền baggage, có thể bật W3C Baggage propagator; chỉ truyền các thuộc tính nhỏ, không nhạy cảm và có cardinality thấp.

## 3. gRPC Metadata là carrier

gRPC metadata là tập key/value đi cùng một RPC:

- Client gửi request metadata khi bắt đầu call.
- Server có thể gửi initial response headers.
- Server gửi trailers khi RPC kết thúc.

Trace context outbound được inject vào request metadata. Phía server extract từ metadata nhận được trước khi gọi application handler hoặc tạo server span theo instrumentation.

W3C header names như traceparent và tracestate phù hợp với metadata ASCII của gRPC. Tên metadata key phải viết thường. Các key nhị phân của gRPC dùng hậu tố -bin và binary marshaller; traceparent/tracestate là text nên không dùng -bin.

Không nhầm request metadata với response headers/trailers. Việc inject trace context ở client không có nghĩa server sẽ trả lại traceparent trong response; trace liên kết được duy trì nhờ server extract parent context và tạo span phù hợp.

## 4. Dùng OpenTelemetry gRPC instrumentation

Trong gRPC Java, cách ưu tiên là dùng OpenTelemetry gRPC instrumentation. Interceptor phía client thực hiện client span và inject context; interceptor phía server extract context và tạo server span.

Ví dụ tạo hai interceptor từ một OpenTelemetry instance dùng chung:

~~~java
import io.grpc.ClientInterceptor;
import io.grpc.ServerInterceptor;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcTracingConfiguration {

    @Bean
    public ClientInterceptor tracingClientInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newClientInterceptor();
    }

    @Bean
    public ServerInterceptor tracingServerInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newServerInterceptor();
    }
}
~~~

Các interceptor phải được đăng ký vào channel/server interceptor chain. Trong Spring gRPC, hãy dùng extension point của starter đang dùng để đăng ký global server interceptor; client interceptor phải được gắn vào ManagedChannel hoặc channel customizer tương ứng. Chỉ khai báo bean không tự động bảo đảm mọi channel và server đều sử dụng bean đó.

Với client channel được tạo trực tiếp:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(tracingClientInterceptor)
        .build();
~~~

Server builder trực tiếp có thể đăng ký server interceptor bằng API intercept của builder. Trong ứng dụng Spring, không tự tạo server thứ hai chỉ để thêm interceptor nếu starter đã quản lý server hiện tại.

Nếu ứng dụng đã dùng OpenTelemetry Java agent có gRPC auto-instrumentation, agent có thể tự tạo span và propagate context. Không thêm interceptor thủ công cho cùng boundary nếu chưa xác nhận tránh duplicate spans. Chọn một cơ chế instrumentation cho mỗi client/server boundary.

## 5. OpenTelemetry propagator hoạt động ra sao?

API chính là TextMapPropagator. Nó không phụ thuộc riêng gRPC; nó nhận một carrier cùng setter/getter do giao thức cung cấp:

- Setter ghi một key/value vào carrier khi inject.
- Getter đọc value từ carrier khi extract và liệt kê các key có thể đọc.

Với gRPC, carrier là đối tượng Metadata. Instrumentation gRPC đã cung cấp adapter phù hợp; vì vậy ứng dụng thông thường không cần tự viết setter/getter. Tự triển khai carrier chỉ hữu ích khi tích hợp một transport tùy biến hoặc cần hiểu rõ ranh giới inject/extract.

## 6. Ví dụ Metadata setter/getter

Ví dụ dưới đây minh họa carrier cho text metadata. Key được chuẩn hóa chữ thường và dùng ASCII marshaller:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import java.util.Locale;
import java.util.Set;

public final class GrpcMetadataCarrier {

    private GrpcMetadataCarrier() {}

    public static final TextMapSetter<Metadata> SETTER =
            (carrier, key, value) -> {
                if (carrier == null || key == null || value == null) {
                    return;
                }
                String normalizedKey = key.toLowerCase(Locale.ROOT);
                Metadata.Key<String> metadataKey =
                        Metadata.Key.of(
                                normalizedKey,
                                Metadata.ASCII_STRING_MARSHALLER);
                carrier.put(metadataKey, value);
            };

    public static final TextMapGetter<Metadata> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Metadata carrier) {
                    return carrier == null
                            ? Set.of()
                            : carrier.keys();
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

Đây là ví dụ minh họa cho W3C text headers. Trong code production cần bổ sung import Locale, kiểm tra key hợp lệ và bảo đảm không ghi đè metadata cùng tên ngoài ý muốn. Không dùng carrier này để đọc/ghi binary metadata; binary key cần marshaller riêng và hậu tố -bin.

Với Metadata mới tạo cho một outbound call, setter có thể ghi traceparent/tracestate vào carrier. Nếu tái sử dụng carrier đã có key, cần quy định rõ việc thay thế hay từ chối duplicate; không để nhiều traceparent mâu thuẫn trong cùng một RPC.

## 7. Inject ở client và extract ở server

Để hiểu cách propagator được gọi, ví dụ dưới đây minh họa hai thao tác ở ranh giới RPC. Đây là mô hình tích hợp thủ công; khi dùng GrpcTelemetry interceptor, không cần lặp lại cùng thao tác.

Inject context hiện tại vào request metadata:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

TextMapPropagator propagator =
        openTelemetry.getPropagators().getTextMapPropagator();

Metadata outboundHeaders = new Metadata();
propagator.inject(
        Context.current(),
        outboundHeaders,
        GrpcMetadataCarrier.SETTER);
~~~

Extract context từ metadata inbound:

~~~java
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;

Context extracted = propagator.extract(
        Context.current(),
        inboundHeaders,
        GrpcMetadataCarrier.GETTER);
~~~

Server interceptor cần làm context đã extract trở thành context hiện hành khi gRPC gọi handler/listener. Với gRPC Java, có thể dùng Contexts.interceptCall:

~~~java
return Contexts.interceptCall(
        extracted,
        call,
        headers,
        next);
~~~

Khi tự viết interceptor đầy đủ, cần bảo đảm extraction xảy ra đúng vị trí trong interceptor chain trước khi instrumentation tạo server span. Thứ tự interceptor phụ thuộc cách builder/starter đăng ký; tránh vừa tự extract vừa dùng server instrumentation tự extract nếu không có lý do rõ ràng.

## 8. Baggage có nên được truyền qua metadata?

Baggage là tập key/value gắn với OpenTelemetry Context và có thể được propagate giữa service. Nó hữu ích cho thông tin vận hành nhỏ, không nhạy cảm, ví dụ một phân loại tenant đã được ẩn danh hoặc rollout cohort đã được phê duyệt.

Không dùng baggage để truyền:

- Access token, session ID hoặc credential.
- Email, số điện thoại, account ID hoặc PII.
- Payload nghiệp vụ hoặc dữ liệu lớn.
- Dữ liệu cần bảo đảm tính toàn vẹn hay dùng cho authorization.

Baggage có thể đi qua nhiều service và xuất hiện trong telemetry backend. Nó làm tăng kích thước metadata và có thể tạo cardinality cao. Chỉ propagate các key đã được cho phép; giới hạn số lượng, độ dài và retention.

Nếu không cần baggage, chỉ bật W3C Trace Context propagator. Nếu cần baggage, cấu hình W3C Baggage propagator cùng trace context và kiểm thử rõ những key nào thực sự được gửi.

## 9. Async boundary và context propagation

Sau khi server extract trace context, OpenTelemetry instrumentation gắn context phù hợp trong lúc gọi handler. Khi ứng dụng chuyển công việc sang executor tùy chỉnh, context không phải lúc nào cũng tự đi theo thread mới.

Capture context tại thời điểm submit và wrap task:

~~~java
import io.opentelemetry.context.Context;

Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span child = tracer.spanBuilder("repository.load")
            .startSpan();
    try (Scope scope = child.makeCurrent()) {
        repository.loadData();
    } finally {
        child.end();
    }
}));
~~~

Nhờ vậy child span tạo trong worker có thể kế thừa span cha của RPC. Cần capture context thuộc đúng call; không lưu Context vào field mutable của singleton service.

gRPC Context và OpenTelemetry Context là hai loại context khác nhau. Nếu worker cần deadline, cancellation hoặc principal, ứng dụng còn phải truyền gRPC Context/SecurityContext theo cơ chế tương ứng. Việc wrap OpenTelemetry Context chỉ giải quyết propagation telemetry, không tự truyền quyền truy cập hay dừng JDBC.

## 10. Streaming RPC và vòng đời trace context

Với server streaming hoặc bidirectional streaming, context được extract một lần khi RPC bắt đầu. Server span thường bao phủ toàn bộ call, không chỉ method trả về observer. Các callback nhận message và gửi response thuộc cùng RPC context theo cơ chế instrumentation.

Khi chuyển từng message sang worker:

- Capture context của RPC hoặc message processing span trước khi submit.
- Không dùng context của message trước cho message sau nếu callback chạy đồng thời.
- Tạo child span cho một batch/message chỉ khi có giá trị chẩn đoán rõ.
- Kết thúc child span khi task hoàn tất, kể cả khi lỗi hoặc cancellation.
- Kết thúc RPC span khi stream có terminal event: hoàn tất, lỗi hoặc hủy.

Không tạo một root trace mới cho mỗi message nếu tất cả message thuộc cùng một RPC. Nếu hệ thống xử lý message sau khi RPC đã kết thúc, cần tạo một trace mới và liên kết bằng span link khi phù hợp, thay vì giữ một parent span đã kết thúc như thể call còn mở.

## 11. Propagation failure và trust boundary

Không phải metadata nào cũng hợp lệ. Propagator có thể không extract được context khi header thiếu, sai định dạng hoặc bị cắt. Trong trường hợp đó, server thường tiếp tục với context không có remote parent và tạo trace mới theo sampler; không nên làm RPC nghiệp vụ thất bại chỉ vì traceparent không hợp lệ.

Các nguyên tắc:

- Không tự parse traceparent bằng substring hoặc regex riêng.
- Không tin trace context như danh tính người dùng.
- Không cho phép metadata tracing tùy ý vượt giới hạn kích thước của gRPC.
- Không phản chiếu toàn bộ baggage hoặc metadata vào log.
- Chỉ propagate qua boundary đã được xác định; cân nhắc xóa baggage không tin cậy ở gateway công khai.
- Với cross-process boundary, dùng propagator chuẩn để xử lý version, flags và validation.

Trace ID do caller gửi có thể được dùng làm parent context theo chính sách tracing, nhưng không phải bằng chứng request đáng tin cậy. Authorization phải dựa trên credential và principal được xác minh riêng.

## 12. Kiểm thử inject/extract

Test propagator nên xác nhận dữ liệu đi qua carrier và được extract đúng:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.grpc.Metadata;
import org.junit.jupiter.api.Test;

@Test
void injectsAndExtractsW3cTraceContext() {
    TextMapPropagator propagator =
            openTelemetry.getPropagators().getTextMapPropagator();
    Tracer tracer = openTelemetry.getTracer("propagation-test");

    Span parent = tracer.spanBuilder("client-call").startSpan();
    Context parentContext = Context.root().with(parent);
    Metadata headers = new Metadata();

    propagator.inject(
            parentContext,
            headers,
            GrpcMetadataCarrier.SETTER);

    assertNotNull(headers.get(
            Metadata.Key.of(
                    "traceparent",
                    Metadata.ASCII_STRING_MARSHALLER)));

    Context extracted = propagator.extract(
            Context.root(),
            headers,
            GrpcMetadataCarrier.GETTER);

    SpanContext remoteParent = Span.fromContext(extracted).getSpanContext();
    assertTrue(remoteParent.isValid());
    assertEquals(
            parent.getSpanContext().getTraceId(),
            remoteParent.getTraceId());

    parent.end();
}
~~~

Test trên kiểm tra propagator và carrier. Integration test cần dựng in-process gRPC server/channel có interceptor tracing ở hai đầu, gọi generated stub và xác nhận client/server spans có cùng trace ID, parent-child relationship đúng.

Ma trận kiểm thử nên có:

| Ca | Kỳ vọng |
| --- | --- |
| Metadata có traceparent hợp lệ | Server span nối vào trace từ client |
| Metadata thiếu traceparent | RPC vẫn chạy; server tạo trace mới theo cấu hình |
| Traceparent sai định dạng | Không làm hỏng RPC; không tạo parent context hợp lệ từ header sai |
| Tracestate hợp lệ | Được propagate theo quy tắc W3C |
| Baggage được bật | Chỉ key được phép được gửi và extract |
| Async worker | Child span giữ trace ID/parent đúng |
| Streaming | Span bao phủ tới terminal event |
| Client/server interceptor bị đăng ký trùng | Test phát hiện duplicate spans |

Đóng channel, server và tracer provider sau test. Với callback bất đồng bộ, dùng future/latch có timeout thay vì Thread.sleep.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tạo span nhưng không inject metadata | Trace đứt khi sang service khác | Dùng client propagator/interceptor |
| Server không extract metadata | Server span thành root trace mới | Đăng ký server instrumentation |
| Tự parse traceparent | Dễ sai chuẩn và bỏ sót validation | Dùng W3C propagator |
| Dùng binary marshaller cho traceparent | Metadata không tương thích | Dùng ASCII key/value |
| Dùng -bin cho tracestate | Sai loại metadata | Giữ text metadata key |
| Java agent và interceptor cùng instrument | Duplicate spans | Chọn một cơ chế cho boundary |
| Chuyển executor không wrap Context | Child span mất parent | Dùng Context.wrap/fixedContextExecutor |
| Đưa credential vào baggage | Rò rỉ secret qua nhiều service | Không propagate dữ liệu xác thực trong baggage |
| Dùng trace ID làm user identity | Lỗ hổng authorization | Xác thực độc lập bằng credential |

## 14. Tự luyện tập

1. Mô tả cách client inject traceparent vào gRPC request metadata và server extract để tạo server span.
2. Vì sao traceparent/tracestate dùng ASCII metadata thay vì key nhị phân hậu tố -bin?
3. Một RPC được chuyển sang worker executor. Cần làm gì để child span vẫn thuộc trace của RPC?
4. Phân biệt OpenTelemetry Context với gRPC Context khi truyền deadline và principal sang worker.
5. Vì sao baggage không nên chứa token, PII hoặc dữ liệu nghiệp vụ lớn?
6. Thiết kế integration test chứng minh client span và server span có cùng trace ID.

**Ghi nhớ:** Propagator chuyển trace context giữa các tiến trình bằng cách inject vào gRPC request metadata ở client và extract ở server. Ưu tiên OpenTelemetry gRPC instrumentation với W3C Trace Context; dùng carrier tùy biến chỉ khi cần. Truyền context qua executor, giữ đúng vòng đời streaming span, giới hạn baggage và tuyệt đối không dùng trace context thay authentication/authorization.
