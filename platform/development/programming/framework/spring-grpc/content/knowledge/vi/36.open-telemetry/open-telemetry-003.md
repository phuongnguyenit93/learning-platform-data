# Client span và server span

**Chương:** OpenTelemetry  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào hai span đại diện cho một lời gọi gRPC: client span ở phía gọi và server span ở phía nhận. Hiểu đúng vai trò, quan hệ cha/con và vòng đời của hai span giúp đọc distributed trace và tìm điểm gây chậm hoặc lỗi.

## 1. Một RPC có hai góc nhìn

Một lời gọi gRPC đi qua hai tiến trình. Client biết lúc bắt đầu gọi, lúc gửi request và lúc nhận kết quả. Server biết lúc nhận call, thời gian chạy handler và lúc kết thúc response. Hai góc nhìn bổ sung cho nhau:

- **Client span** ghi nhận thời gian phía caller thực hiện RPC, thường có span kind `CLIENT`.
- **Server span** ghi nhận thời gian phía receiver xử lý RPC, thường có span kind `SERVER`.

Client span bao gồm chi phí quan sát được từ phía client như gửi call, chờ response và nhận terminal status. Server span bao gồm thời gian call ở phía server, có thể gồm chờ application executor, handler, downstream operation và gửi response theo cách instrumentation đo được.

Không nên trừ thời lượng server span khỏi client span rồi mặc định phần còn lại chính xác là network latency. Hai span có thể chịu ảnh hưởng của clock skew, scheduling, buffering và các khoảng thời gian instrumentation khác nhau. Hãy dùng chúng để xác định vùng chậm và đối chiếu với metrics/network telemetry.

## 2. Quan hệ cha/con giữa client và server span

Khi client đang có một span hiện hành, gRPC client instrumentation tạo client span làm con của span đó. Propagator inject SpanContext của client span vào request metadata. Ở server, instrumentation extract metadata và tạo server span có cùng trace ID, với remote parent là client span.

~~~mermaid
flowchart TD
    A["Parent span: checkout workflow"] --> B["CLIENT: OrderService/CreateOrder"]
    B --> C["SERVER: OrderService/CreateOrder"]
    C --> D["Child span: validate order"]
    C --> E["CLIENT: InventoryService/Reserve"]
    E --> F["SERVER: InventoryService/Reserve"]
~~~

Trong trace tree:

- Client span và server span thuộc cùng trace.
- Server span liên kết với client span qua parent span ID được truyền trong trace context.
- Server span trở thành parent của các span nghiệp vụ bên trong handler.
- Nếu server gọi một gRPC service khác, downstream client span là con của span hiện hành ở server.

Nếu không có trace context trong metadata hoặc server không extract được context, server span có thể trở thành root của một trace mới. Hai span có cùng tên method nhưng trace ID khác nhau không tạo thành một distributed trace.

## 3. Span kind thể hiện góc nhìn nào?

OpenTelemetry định nghĩa span kind để mô tả vai trò của thao tác:

| Span kind | Ý nghĩa trong gRPC | Ví dụ |
| --- | --- | --- |
| `CLIENT` | Tiến trình hiện tại gọi một RPC ở tiến trình khác | Order service gọi Inventory service |
| `SERVER` | Tiến trình hiện tại nhận và xử lý một RPC | Inventory service nhận Reserve |
| `INTERNAL` | Công việc nội bộ trong một tiến trình | Validate request, tính giá |
| `PRODUCER` / `CONSUMER` | Tạo/nhận message trong hệ thống messaging | Publish/consume event qua broker |

Không tạo span kind `SERVER` ở client hoặc `CLIENT` ở server chỉ vì tên method. Kind phải phản ánh chiều giao tiếp từ góc nhìn của tiến trình tạo span.

## 4. Tạo client và server span bằng gRPC instrumentation

Với gRPC Java, OpenTelemetry cung cấp instrumentation có thể tạo hai loại span và propagate context thông qua interceptor:

~~~java
import io.grpc.ClientInterceptor;
import io.grpc.ServerInterceptor;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;

public final class GrpcTracingInterceptors {

    private final GrpcTelemetry grpcTelemetry;

    public GrpcTracingInterceptors(OpenTelemetry openTelemetry) {
        this.grpcTelemetry = GrpcTelemetry.create(openTelemetry);
    }

    public ClientInterceptor clientInterceptor() {
        return grpcTelemetry.newClientInterceptor();
    }

    public ServerInterceptor serverInterceptor() {
        return grpcTelemetry.newServerInterceptor();
    }
}
~~~

Client interceptor cần được gắn vào channel:

~~~java
ManagedChannel channel = NettyChannelBuilder
        .forAddress(host, port)
        .intercept(grpcTracingInterceptors.clientInterceptor())
        .build();
~~~

Server interceptor cần được gắn vào server chain. Trong Spring gRPC, server thường do starter quản lý; đăng ký interceptor bằng extension point/global interceptor registration mà phiên bản starter cung cấp. Khai báo một bean interceptor không tự động chứng minh nó đã được áp dụng cho server và mọi channel.

Nếu ứng dụng đã dùng OpenTelemetry Java agent có gRPC auto-instrumentation, agent có thể đã tạo client/server spans. Tránh gắn thêm interceptor thủ công cho cùng boundary nếu chưa kiểm tra duplicate spans. Chọn một cơ chế instrumentation cho mỗi RPC boundary.

## 5. Thuộc tính của client span và server span

Instrumentation gRPC có thể ghi tên method, service, peer/server và status. Bộ attribute cụ thể phụ thuộc phiên bản instrumentation và phiên bản semantic conventions đang bật. Một số phiên bản dùng nhóm `rpc.system`, `rpc.service`, `rpc.method`; phiên bản semantic conventions mới hơn có thể dùng tên thuộc tính đã được chuẩn hóa khác.

Các thông tin hữu ích khi phân tích:

- RPC system là gRPC.
- Service và method, ví dụ `orders.v1.OrderService/CreateOrder`.
- Span kind là `CLIENT` hay `SERVER`.
- Status code hoặc trạng thái kết thúc của RPC.
- Địa chỉ server/peer nếu chính sách telemetry cho phép.
- Resource attributes như `service.name`, `service.version` và deployment environment.

Không tự ghi một bộ key khác tên cho cùng một thông tin nếu instrumentation đã có semantic convention tương ứng. Khi nâng version, kiểm tra thay đổi semantic conventions để dashboard và query không bị đứt.

Không đặt order ID, customer ID, email, token hoặc raw request làm span name/attribute. Các giá trị có cardinality cao làm tăng chi phí backend và có thể chứa dữ liệu nhạy cảm. Nếu cần liên kết với log nghiệp vụ, dùng correlation identifier đã được phê duyệt và có chính sách bảo vệ dữ liệu.

## 6. Vòng đời client span

Với unary RPC, client span thường bắt đầu khi client instrumentation bắt đầu call và kết thúc khi nhận kết quả terminal từ gRPC:

1. Client instrumentation tạo span kind `CLIENT`.
2. Propagator inject context vào request metadata.
3. Stub gửi request.
4. Client chờ response hoặc lỗi.
5. Khi call hoàn tất, bị hủy hoặc thất bại, instrumentation ghi kết quả và kết thúc span.

Với async stub, method Java có thể trả về ngay sau khi khởi tạo call; điều đó không có nghĩa client span kết thúc. Span phải bao phủ call đến khi callback terminal xảy ra.

Với client-streaming hoặc bidirectional streaming, span thường bao phủ toàn bộ RPC stream. Việc gửi xong message cuối ở một chiều chưa chắc call đã kết thúc; client span chỉ kết thúc khi RPC có terminal result theo semantics của gRPC.

## 7. Vòng đời server span

Server span bắt đầu khi server instrumentation nhận call và có thể extract remote parent context từ metadata. Span bao phủ thời gian xử lý call theo vòng đời server:

- Gọi service method và xử lý request.
- Nhận thêm message với client-streaming/bidirectional streaming.
- Gửi response message với server-streaming/bidirectional streaming.
- Xử lý exception, cancellation hoặc deadline.
- Kết thúc call bằng completion hoặc status lỗi.

Với unary RPC, handler thường gửi một response rồi gọi `onCompleted()`. Với streaming RPC, method service có thể trả inbound observer ngay khi stream bắt đầu; server span không được kết thúc chỉ vì method Java đã trả observer.

Instrumentation server nên kết thúc span khi call terminal. Nếu tự viết instrumentation, cần bọc các callback và xử lý đúng `onComplete`, `onCancel`, lỗi và race giữa các nhánh terminal. Ưu tiên interceptor instrumentation đã được kiểm thử thay vì tự quản lý lifecycle nếu không có yêu cầu đặc biệt.

## 8. Downstream RPC tạo span lồng nhau

Giả sử Order service nhận `CreateOrder`, sau đó gọi Inventory service:

1. Client của Order tạo span `CLIENT` cho CreateOrder.
2. Order server tạo span `SERVER` cho CreateOrder.
3. Khi Order gọi Inventory, client instrumentation tạo span `CLIENT` cho Reserve dưới server span Order.
4. Inventory server extract metadata và tạo span `SERVER` cho Reserve.

Nhờ quan hệ này, trace thể hiện cả thời gian Order xử lý lẫn thời gian chờ Inventory. Nếu Order gọi thêm database, auto-instrumentation JDBC có thể tạo span database con; nếu không, có thể thêm child span nội bộ có chọn lọc.

Không tạo một span tên `CreateOrder` thủ công trong handler nếu server instrumentation đã tạo server span cho chính RPC. Span tùy chỉnh nên đại diện cho bước nghiệp vụ riêng như `validate_order` hoặc `reserve_inventory`.

## 9. Ghi nhận status và exception

Client và server có thể quan sát cùng một kết quả RPC nhưng ở hai phía khác nhau. Ví dụ server trả `NOT_FOUND`; server span ghi nhận kết quả xử lý phía server, client span ghi nhận lỗi mà caller nhận được.

Một số status thường cần phân tích:

| gRPC status | Ý nghĩa thường gặp | Điều cần xem |
| --- | --- | --- |
| `OK` | RPC hoàn tất thành công | Latency và các child spans |
| `INVALID_ARGUMENT` | Request vi phạm hợp đồng | Boundary validation và client input |
| `NOT_FOUND` | Tài nguyên không tồn tại | Kết quả lookup và semantics API |
| `PERMISSION_DENIED` | Caller không được phép | Authorization policy |
| `UNAVAILABLE` | Service/dependency tạm thời không sẵn sàng | Network, server availability, retry |
| `DEADLINE_EXCEEDED` | Hết ngân sách thời gian | Queue, dependency latency, timeout propagation |
| `CANCELLED` | Caller hoặc runtime hủy call | User cancellation, shutdown hoặc deadline flow |

Instrumentation thường gắn status và error attributes theo phiên bản thư viện. Không tự đánh dấu mọi status khác `OK` là lỗi lập trình; status nghiệp vụ cần được phân loại nhất quán trong dashboard. Không ghi exception message chứa SQL, token hoặc PII vào span.

## 10. Retry và nhiều attempt

Một logical operation từ ứng dụng có thể dẫn đến nhiều lần thử RPC do retry policy hoặc application retry. Cần phân biệt:

- Logical operation: ý định nghiệp vụ của caller, ví dụ tạo đơn.
- RPC call/attempt: một lần thực hiện giao tiếp gRPC.

Tùy gRPC runtime và instrumentation, trace có thể biểu diễn một span cho call logic, các attempt riêng hoặc các span liên quan theo cách khác. Không mặc định mọi retry đều tạo đúng một client span độc lập; kiểm tra phiên bản instrumentation và trace thực tế.

Khi phân tích retry, quan sát số attempt, status từng lần thử, backoff và tổng thời gian logical operation. Một attempt `UNAVAILABLE` rồi attempt sau `OK` vẫn có thể khiến tổng latency cao dù server cuối cùng thành công.

Không thêm payload hay idempotency key nhạy cảm vào span. Nếu cần nhận biết nhóm retry, dùng thuộc tính kỹ thuật ít cardinality và không chứa định danh nghiệp vụ.

## 11. Async executor và parent context

Nếu server handler chuyển công việc sang executor riêng, OpenTelemetry Context cần được capture và truyền sang worker. Nếu không, child span tạo trong worker có thể thành root hoặc gắn sai parent:

~~~java
Context captured = Context.current();
workerExecutor.execute(captured.wrap(() -> {
    Span child = tracer.spanBuilder("order.load_inventory")
            .startSpan();
    try (Scope scope = child.makeCurrent()) {
        inventoryRepository.load();
    } catch (RuntimeException failure) {
        child.recordException(failure);
        child.setStatus(StatusCode.ERROR);
        throw failure;
    } finally {
        child.end();
    }
}));
~~~

Capture context ngay trong callback của RPC, trước khi submit task. Không lưu context vào field mutable của singleton Spring service. Nếu worker cần gRPC deadline/cancellation hoặc Spring SecurityContext, phải propagate các context đó bằng cơ chế tương ứng; OpenTelemetry Context chỉ mang telemetry context.

## 12. Sampling và trace completeness

Client span và server span cần cùng quyết định sampling để trace không bị đứt. Parent-based sampler thường giữ quyết định sampling từ context được propagate. Nếu mỗi tiến trình random sampling độc lập, một phía có thể giữ span trong khi phía kia bỏ span.

Trong môi trường có collector tail sampling, collector có thể quyết định giữ trace dựa trên toàn bộ trace đã nhận, ví dụ giữ trace chậm hoặc có lỗi. Cần tính đến buffer, timeout chờ trace hoàn chỉnh và khả năng thiếu span khi service không export được.

Sampling không thay metrics. Metrics vẫn cần thống kê latency, throughput và error rate trên toàn bộ traffic, kể cả request không được sample thành trace.

## 13. Kiểm thử client span và server span

Kiểm thử tracing nên xác nhận quan hệ chứ không chỉ đếm số span:

1. Có span kind `CLIENT` cho outbound RPC.
2. Có span kind `SERVER` cho inbound RPC.
3. Hai span có cùng trace ID khi propagation hoạt động.
4. Server span có parent span ID tương ứng với client span.
5. Downstream client span là con của server span hiện tại.
6. Span kết thúc sau terminal event đối với streaming RPC.
7. Lỗi/cancellation được ghi nhận và không để span mở vô hạn.

OpenTelemetry SDK có thể dùng `InMemorySpanExporter` trong test để thu thập span mà không cần collector. Cấu hình test cần dùng cùng OpenTelemetry instance cho interceptor client/server:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;

import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

InMemorySpanExporter exporter = InMemorySpanExporter.create();
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(SimpleSpanProcessor.create(exporter))
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setTracerProvider(tracerProvider)
        .setPropagators(ContextPropagators.create(
                W3CTraceContextPropagator.getInstance()))
        .build();

GrpcTelemetry grpcTelemetry = GrpcTelemetry.create(openTelemetry);
ClientInterceptor clientTracing =
        grpcTelemetry.newClientInterceptor();
ServerInterceptor serverTracing =
        grpcTelemetry.newServerInterceptor();
~~~

Gắn client interceptor vào in-process channel và server interceptor vào in-process server, gọi generated stub, rồi kiểm tra `exporter.getFinishedSpanItems()`. Dùng `SpanKind.CLIENT`, `SpanKind.SERVER`, trace ID và parent span ID để xác minh quan hệ.

Assertion minh họa sau khi unary RPC đã kết thúc:

~~~java
List<SpanData> spans = exporter.getFinishedSpanItems();
SpanData clientSpan = spans.stream()
        .filter(span -> span.getKind() == SpanKind.CLIENT)
        .findFirst()
        .orElseThrow();
SpanData serverSpan = spans.stream()
        .filter(span -> span.getKind() == SpanKind.SERVER)
        .findFirst()
        .orElseThrow();

assertEquals(
        clientSpan.getSpanContext().getTraceId(),
        serverSpan.getSpanContext().getTraceId());
assertEquals(
        clientSpan.getSpanContext().getSpanId(),
        serverSpan.getParentSpanContext().getSpanId());
~~~

Với streaming, giữ test mở cho đến khi stream kết thúc rồi mới assertion span đã được export. Dùng latch/future có timeout, không dùng `Thread.sleep()` để đoán thời điểm span kết thúc. Đóng channel, server và tracer provider sau test.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ có client span | Không biết server xử lý ở đâu | Đăng ký server instrumentation |
| Chỉ có server span | Trace có thể mất quan hệ với caller | Client inject context và server extract |
| Span kind đặt sai | Trace tree diễn giải sai chiều giao tiếp | Dùng CLIENT cho outbound, SERVER cho inbound |
| Server span kết thúc khi handler trả observer | Streaming duration bị cắt ngắn | Kết thúc tại terminal event |
| Tạo thêm RPC span thủ công | Duplicate span và trace tree khó đọc | Chỉ tạo child span cho bước nghiệp vụ |
| Chuyển executor không truyền context | Child span mất parent | Wrap task bằng OpenTelemetry Context |
| Java agent và interceptor cùng instrument | Duplicate client/server spans | Chọn một cơ chế tại mỗi boundary |
| So sánh duration như network latency tuyệt đối | Kết luận sai do clock/scheduling | Đối chiếu trace với metrics và timing khác |
| Ghi raw request hoặc identifier vào attributes | Lộ dữ liệu, cardinality cao | Redact và giới hạn attributes |

## 15. Tự luyện tập

1. Một client gọi Order service, rồi Order gọi Inventory. Hãy vẽ quan hệ cha/con của bốn span CLIENT/SERVER.
2. Vì sao client span và server span thường có cùng trace ID nhưng span ID khác nhau?
3. Một client-streaming handler trả inbound observer ngay lập tức. Server span nên kết thúc lúc nào?
4. Khi RPC trả `UNAVAILABLE` rồi retry thành công, cần quan sát những thông tin nào để hiểu tổng latency?
5. Làm thế nào kiểm thử server span có remote parent đúng là client span?
6. Khi chuyển công việc sang executor, cần truyền OpenTelemetry Context và các context ứng dụng nào khác?

**Ghi nhớ:** Client span mô tả RPC từ phía caller và thường có kind `CLIENT`; server span mô tả cùng call từ phía receiver và thường có kind `SERVER`. W3C trace context nối server span với client span qua metadata. Đọc cả parent-child relationship, status và lifecycle; với streaming, span phải bao phủ tới terminal event. Dùng instrumentation chuẩn, tránh duplicate spans và không đưa secret/PII vào telemetry.
