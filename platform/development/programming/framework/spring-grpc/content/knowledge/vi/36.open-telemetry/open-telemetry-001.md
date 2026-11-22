# Trace span cho mỗi RPC

**Chương:** OpenTelemetry  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào việc tạo trace span cho mỗi RPC, liên kết span client với span server, truyền trace context qua metadata và quan sát thời gian xử lý xuyên suốt các service.

## 1. Vì sao cần span cho mỗi RPC?

Một request nghiệp vụ thường đi qua nhiều thành phần. Ví dụ client gọi Order service; Order service kiểm tra tồn kho qua Inventory service rồi ghi dữ liệu. Chỉ đo tổng thời gian ở client không cho biết chậm ở đoạn nào.

Distributed tracing mô tả một request dưới dạng **trace** gồm nhiều **span**:

- Trace là toàn bộ hành trình của một request qua một hoặc nhiều service.
- Span biểu diễn một thao tác có thời gian bắt đầu/kết thúc, tên, thuộc tính, trạng thái và quan hệ cha/con.
- Span cha biểu diễn thao tác gọi; span con biểu diễn công việc được gọi bên trong.

Với gRPC, thường cần một client span cho outbound RPC và một server span cho inbound RPC. Nếu server gọi downstream gRPC khác, lời gọi đó tạo client span con dưới server span hiện tại.

~~~mermaid
flowchart TD
    A["Trace: CreateOrder"] --> B["Client span: orders.v1.OrderService/CreateOrder"]
    B --> C["Server span: orders.v1.OrderService/CreateOrder"]
    C --> D["Child span: validate order"]
    C --> E["Client span: inventory.v1.InventoryService/Reserve"]
    E --> F["Server span: inventory.v1.InventoryService/Reserve"]
    C --> G["Child span: persist order"]
~~~

Nhìn trace tree, người vận hành có thể xác định thời gian nằm ở RPC boundary, validation, database hoặc downstream service. Một span chỉ hữu ích khi nó có quan hệ đúng với trace và được kết thúc đúng lúc.

## 2. Trace span được tạo ở đâu trong gRPC?

Không cần tự viết một span thủ công trong mọi service method. Cách phổ biến là dùng OpenTelemetry gRPC instrumentation:

- **Client interceptor** tạo client span quanh outbound RPC, inject trace context vào metadata request.
- **Server interceptor** extract trace context từ metadata, tạo server span làm con của client span.
- Instrumentation kết thúc span khi RPC hoàn tất, thất bại hoặc bị hủy; nó cũng ghi nhận status theo khả năng của phiên bản instrumentation.

Với streaming RPC, span thường bao phủ toàn bộ vòng đời call, từ lúc bắt đầu tới terminal event (onCompleted, onError hoặc cancellation). Không tạo một server span mới cho mỗi message nếu mục tiêu là theo dõi một RPC; message-level work có thể được ghi bằng event hoặc child span riêng khi thực sự cần.

## 3. Thêm OpenTelemetry gRPC instrumentation

Với gRPC Java 1.6 API, instrumentation có thể được dùng qua artifact **opentelemetry-grpc-1.6** và lớp **GrpcTelemetry**. Quản lý version cùng OpenTelemetry BOM của ứng dụng để API và runtime tương thích.

Ví dụ tạo interceptor từ một instance OpenTelemetry đã được cấu hình SDK/exporter:

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
    public ServerInterceptor openTelemetryServerInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newServerInterceptor();
    }

    @Bean
    public ClientInterceptor openTelemetryClientInterceptor(
            OpenTelemetry openTelemetry) {
        return GrpcTelemetry.create(openTelemetry)
                .newClientInterceptor();
    }
}
~~~

Hai bean trên tạo interceptor; chúng chỉ được sử dụng khi được đăng ký vào interceptor chain. Với gRPC Java server builder trực tiếp:

~~~java
NettyServerBuilder.forPort(port)
        .intercept(openTelemetryServerInterceptor)
        .addService(orderGrpcService)
        .build();
~~~

Với client channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(openTelemetryClientInterceptor)
        .build();
~~~

Trong Spring gRPC, server thường được tạo bởi starter/auto-configuration. Hãy đăng ký server interceptor qua extension point hoặc global interceptor registration mà starter của phiên bản dự án hỗ trợ; việc khai báo một bean đơn thuần không bảo đảm interceptor tự được gắn vào server. Tương tự, client interceptor phải được gắn vào channel hoặc cơ chế channel customization được ứng dụng sử dụng.

Một lựa chọn khác là OpenTelemetry Java agent với auto-instrumentation cho gRPC. Khi agent đã tạo span client/server, không đồng thời thêm interceptor thủ công cho cùng RPC nếu chưa xác minh cơ chế tránh duplicate spans. Hãy chọn một cơ chế instrumentation cho mỗi boundary.

## 4. Cấu hình SDK, exporter và propagator

Interceptor cần một OpenTelemetry instance được cấu hình. Trong môi trường production, ứng dụng thường dùng OpenTelemetry SDK cùng exporter OTLP để gửi span tới collector:

~~~java
OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(sdkTracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();
~~~

sdkTracerProvider ở đây là provider đã cấu hình resource, sampler và span processor/exporter. Không nên tạo một SDK độc lập trong từng service bean; hãy quản lý một instance dùng chung trong application lifecycle.

Các thành phần chính:

- **Resource:** định danh service, ví dụ service.name=orders, môi trường và phiên bản triển khai.
- **Sampler:** quyết định trace nào được ghi lại.
- **Span processor/exporter:** xử lý span kết thúc và gửi dữ liệu tới collector/backend.
- **Propagator:** inject/extract trace context qua ranh giới process; W3C Trace Context thường dùng traceparent và tracestate.

SDK/exporter có thể được cấu hình qua Spring Boot starter, Java agent hoặc code. Điều quan trọng là gRPC interceptor và các span nghiệp vụ dùng cùng OpenTelemetry provider/context.

## 5. Trace context đi qua metadata như thế nào?

Span client hiện tại có một SpanContext chứa trace ID, span ID và sampling flags. Client propagator inject context vào metadata của outbound RPC. Server interceptor extract metadata đó để tạo server span có cùng trace ID và có parent tương ứng.

Luồng tổng quát:

1. Client bắt đầu client span.
2. Propagator ghi W3C trace context vào metadata, thường là header traceparent và tùy trường hợp tracestate.
3. Server interceptor đọc metadata và tạo server span liên kết với client span.
4. Nếu server gọi downstream, client interceptor tạo span con và inject context tiếp.
5. Mọi service trong cùng hành trình có thể được ghép thành một trace.

Không tự tạo trace ID mới tại mỗi service. Nếu metadata không được propagate, backend tracing sẽ hiển thị các trace rời rạc dù các RPC thuộc cùng một request.

Không tin metadata trace context như dữ liệu xác thực. Trace ID chỉ dùng liên kết telemetry; nó không chứng minh danh tính caller và không được dùng thay authorization.

## 6. Đặt tên span và thêm thuộc tính hữu ích

RPC instrumentation thường tự tạo tên span và thuộc tính theo semantic conventions của phiên bản thư viện. Các thuộc tính hữu ích có thể gồm:

- Hệ thống RPC là gRPC.
- Tên service và method, ví dụ orders.v1.OrderService/CreateOrder.
- RPC status code hoặc trạng thái kết thúc.
- Network peer/server address ở mức được phép thu thập.
- Resource attributes như service name, service version và deployment environment.

Ưu tiên thuộc tính do instrumentation chuẩn tạo ra. Tên semantic convention có thể thay đổi giữa các phiên bản; tránh tự ghi đè cùng một ý nghĩa bằng nhiều key khác nhau.

Thuộc tính tùy chỉnh nên có cardinality thấp và giúp trả lời câu hỏi vận hành:

~~~java
span.setAttribute("app.operation", "reserve_inventory");
span.setAttribute("app.region", regionCode);
~~~

Không thêm order ID, email, account ID, token hoặc giá trị request tùy ý làm span name/attribute. Những giá trị có cardinality cao làm tăng chi phí lưu trữ và có thể lộ dữ liệu cá nhân.

## 7. Tạo child span cho một bước nghiệp vụ

Instrumentation đã tạo RPC span. Nếu cần biết riêng thời gian validation hoặc gọi repository, tạo child span bên trong handler/use case, không tạo một RPC span thứ hai cùng cấp.

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.stereotype.Service;

@Service
public class ReserveInventoryUseCase {

    private final Tracer tracer;
    private final InventoryRepository repository;

    public ReserveInventoryUseCase(
            Tracer tracer,
            InventoryRepository repository) {
        this.tracer = tracer;
        this.repository = repository;
    }

    public Reservation reserve(String sku, int quantity) {
        Span span = tracer.spanBuilder("inventory.validate_and_reserve")
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("app.operation", "reserve_inventory");
            validate(sku, quantity);
            return repository.reserve(sku, quantity);
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }
}
~~~

Child span tự động kế thừa parent từ OpenTelemetry Context hiện tại khi RPC instrumentation đã attach server span. makeCurrent làm span mới trở thành current span trong scope; finally bảo đảm span được kết thúc kể cả khi nghiệp vụ ném lỗi.

Không ghi exception message chứa dữ liệu nhạy cảm vào attribute. recordException có thể ghi exception type/message/stack tùy SDK; hãy cấu hình chính sách redaction hoặc chỉ record exception đã được kiểm soát. Nếu instrumentation RPC đã ghi status lỗi, child span chỉ nên mô tả bước nghiệp vụ của nó, tránh tạo bản sao span RPC.

## 8. Truyền context khi chuyển sang executor khác

OpenTelemetry Context thường được attach trong lúc server interceptor gọi handler. Khi ứng dụng submit công việc sang executor tùy chỉnh, không giả định thread mới tự có context của RPC.

Capture context tại thời điểm submit và wrap task:

~~~java
import io.opentelemetry.context.Context;

Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span span = Span.current();
    span.addEvent("blocking-work-started");
    processBlockingOperation();
}));
~~~

Nhờ vậy child span được tạo trong worker vẫn có quan hệ với RPC span cha. Cần capture context thuộc đúng RPC; không lưu context vào field singleton rồi dùng cho request khác.

gRPC io.grpc.Context và OpenTelemetry io.opentelemetry.context.Context là hai loại context khác nhau. Một số instrumentation tích hợp propagation cho callback gRPC, nhưng khi chuyển qua executor do ứng dụng tự quản lý, hãy bảo đảm cả dữ liệu cần thiết của gRPC (deadline/cancellation/principal theo thiết kế) và OpenTelemetry context được truyền đúng cách. Không nhầm việc propagate trace context với việc propagate security identity.

## 9. Status, exception và vòng đời span

Span RPC cần kết thúc khi RPC kết thúc:

- Unary thành công: kết thúc sau khi response hoàn tất.
- Unary lỗi: kết thúc cùng status lỗi.
- Client/server/bidirectional streaming: span bao phủ toàn call và kết thúc khi stream hoàn tất, lỗi hoặc bị hủy.
- Deadline/cancellation: ghi nhận kết quả tương ứng, không để span mở vô hạn.

Instrumentation gRPC thường xử lý status và exception ở interceptor. Nếu tự instrument, phải bảo đảm mọi nhánh terminal đều kết thúc span đúng một lần. Không chỉ kết thúc span ngay sau khi method server trả về đối với streaming RPC; method có thể trả observer sớm trong khi stream còn hoạt động.

Các gRPC status như INVALID_ARGUMENT, NOT_FOUND, PERMISSION_DENIED, UNAVAILABLE và DEADLINE_EXCEEDED giúp phân loại lỗi ở span. Không nhất thiết coi mọi status nghiệp vụ là lỗi lập trình; áp dụng quy ước error status nhất quán với instrumentation và cách backend hiển thị lỗi.

## 10. Sampling và chi phí tracing

Không phải lúc nào cũng cần lưu toàn bộ trace. Sampling quyết định trace nào được ghi:

- **Always-on:** phù hợp môi trường dev/test hoặc lưu lượng thấp; chi phí tăng nhanh khi traffic lớn.
- **Probability/parent-based sampling:** giữ trace theo tỷ lệ và tôn trọng quyết định sampling từ parent.
- **Tail sampling tại collector:** có thể giữ trace chậm/lỗi sau khi collector quan sát đủ trace, nhưng cần hạ tầng và buffer phù hợp.

Với microservice, parent-based propagation giúp các service trong cùng trace tuân theo quyết định sampling nhất quán. Nếu mỗi service tự random sampling độc lập, trace có thể thiếu span ở giữa.

Đo overhead và cân nhắc sampling theo lưu lượng, độ nhạy dữ liệu, retention và yêu cầu điều tra. Sampling không thay thế metrics; metrics vẫn cần biểu diễn latency/error rate của toàn bộ traffic.

## 11. Bảo mật và quyền riêng tư

Trace có thể đi qua nhiều service và được lưu ở backend tập trung. Trước khi thêm dữ liệu vào span:

- Không ghi access token, authorization metadata, password hoặc secret.
- Tránh ghi raw protobuf request/response.
- Không đưa PII, nội dung message hoặc identifier có cardinality cao vào span name.
- Giới hạn baggage; baggage được propagate qua service và có thể làm tăng kích thước metadata.
- Chỉ export tới collector/backend được kiểm soát; dùng TLS và xác thực exporter khi triển khai qua mạng.
- Đặt retention và quyền truy cập telemetry phù hợp với dữ liệu vận hành.

Trace context không phải kênh truyền dữ liệu nghiệp vụ. Chỉ propagate trace ID, span ID, sampling state và baggage tối thiểu đã được phê duyệt.

## 12. Kiểm thử trace span cho RPC

Nên kiểm thử ít nhất bốn thuộc tính:

1. Client/server RPC tạo span tương ứng.
2. Client span và server span có cùng trace ID và quan hệ parent-child.
3. Downstream RPC tạo span con dưới server span hiện tại.
4. Lỗi/cancellation vẫn kết thúc span và ghi trạng thái phù hợp.

OpenTelemetry SDK cung cấp InMemorySpanExporter trong test artifact để kiểm tra span mà không cần collector bên ngoài. Mẫu setup:

~~~java
InMemorySpanExporter exporter = InMemorySpanExporter.create();
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(SimpleSpanProcessor.create(exporter))
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(tracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();

ServerInterceptor serverTracing =
        GrpcTelemetry.create(openTelemetry).newServerInterceptor();
ClientInterceptor clientTracing =
        GrpcTelemetry.create(openTelemetry).newClientInterceptor();
~~~

Gắn server interceptor vào in-process server builder và client interceptor vào in-process channel, gọi generated stub, sau đó lấy exporter.getFinishedSpanItems() để kiểm tra:

| Ca | Assertion |
| --- | --- |
| Unary thành công | Có client span và server span cho method |
| Context propagation | Hai span có cùng trace ID; server span có parent là client span |
| Downstream RPC | Có client span con dưới server span |
| RPC trả status lỗi | Span kết thúc và thể hiện kết quả lỗi theo instrumentation |
| Streaming hoàn tất | Span chỉ kết thúc khi stream terminal event xảy ra |
| Cancellation/deadline | Span được kết thúc, không bị treo |
| Async worker | Child span trong worker vẫn thuộc trace của RPC |

Test cần đóng channel/server và tracerProvider sau khi chạy để giải phóng tài nguyên. Với streaming test, dùng latch/future có timeout để đợi terminal event và span export; không dùng Thread.sleep làm đồng bộ.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ tạo span ở server, không có client propagation | Trace bị đứt ở ranh giới RPC | Gắn cả client và server instrumentation |
| Mỗi service tự tạo trace ID mới | Không ghép được distributed trace | Dùng W3C propagator và truyền context |
| Bật Java agent và interceptor thủ công cùng lúc | Duplicate RPC spans | Chọn một cơ chế instrumentation cho boundary |
| Tạo span RPC thủ công thêm vào span tự động | Trace tree dư span, khó đọc | Chỉ tạo child span cho bước nghiệp vụ |
| Không kết thúc span của streaming call | Span mở lâu hoặc rò rỉ | Kết thúc ở terminal event |
| Chuyển executor không truyền context | Child span thành root hoặc mất parent | Wrap task bằng OpenTelemetry Context |
| Ghi raw request/token vào attribute | Lộ dữ liệu và tăng cardinality | Redact và chỉ ghi thuộc tính tối thiểu |
| Dùng span thay metrics | Không có thống kê tổng thể ổn định | Kết hợp trace, metrics và logs |

## 14. Tự luyện tập

1. Một client gọi Order service rồi Order gọi Inventory service. Hãy mô tả client/server span và quan hệ cha/con mong đợi.
2. Vì sao chỉ cài server interceptor không đủ để nối trace từ client bên ngoài?
3. Một handler submit JDBC task sang executor riêng. Cần làm gì để child span trong worker giữ đúng parent?
4. Với bidirectional streaming, vì sao span không nên kết thúc ngay khi method trả về inbound observer?
5. Làm thế nào tránh duplicate spans khi ứng dụng đã chạy OpenTelemetry Java agent?
6. Những dữ liệu nào không nên đưa vào span attribute hoặc baggage?

**Ghi nhớ:** Tạo client và server span cho mỗi RPC bằng OpenTelemetry gRPC instrumentation, truyền W3C trace context qua metadata và tạo child span cho các bước nghiệp vụ cần phân tích. Span phải bao phủ đúng vòng đời unary/streaming call, được kết thúc khi success/error/cancellation, giữ parent khi chuyển executor và không chứa secret hoặc PII. Kết hợp trace với metrics/logs để quan sát toàn hệ thống.
