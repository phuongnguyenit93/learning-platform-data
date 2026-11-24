# Phân biệt chỉ số kết nối, luồng tương tác, payload và nghiệp vụ

RSocket hỗ trợ kết nối lâu dài, multiplex nhiều interaction và trao đổi dữ liệu hai chiều. Khi một dashboard chỉ hiển thị tổng số request hoặc tỷ lệ lỗi, người vận hành khó biết vấn đề nằm ở kết nối, một stream cụ thể, payload quá lớn hay logic nghiệp vụ phía sau.

Để quan sát đúng hệ thống RSocket, cần tách chỉ số thành bốn lớp:

1. **Connection:** trạng thái và vòng đời TCP/WebSocket/RSocket session.
2. **Interaction và stream:** từng request-response, fire-and-forget, request-stream hoặc request-channel.
3. **Payload:** kích thước, codec, MIME type và lỗi chuyển đổi dữ liệu.
4. **Business:** kết quả và độ trễ của thao tác nghiệp vụ như tạo đơn, cập nhật thiết bị hoặc xử lý sự kiện.

Bốn lớp liên kết với nhau nhưng trả lời các câu hỏi khác nhau. Connection mở thành công không có nghĩa request được xử lý thành công; request trả response nhanh không có nghĩa nghiệp vụ đã commit; payload nhỏ không bảo đảm dữ liệu hợp lệ. Quan sát cần kết hợp metrics, logs và traces để đi từ triệu chứng đến nguyên nhân.

## 1. Vì sao phải tách bốn lớp?

Giả sử dashboard báo tỷ lệ request thành công giảm. Có thể có nhiều nguyên nhân:

- Connection bị đóng liên tục do proxy timeout hoặc mạng không ổn định.
- SETUP thành công nhưng route handler bị chậm.
- Một request-stream giữ quá nhiều phần tử trong buffer.
- Payload JSON lớn làm decode tốn CPU.
- Service nghiệp vụ chờ database hoặc downstream API.
- Handler trả response thành công nhưng transaction nghiệp vụ bị rollback sau đó.

Nếu chỉ có một metric tổng như requests_total, các trường hợp này dễ bị trộn lẫn. Mỗi lớp cần metric riêng và một số chiều phân loại có giới hạn.

| Lớp | Câu hỏi chính | Ví dụ chỉ số |
|---|---|---|
| Connection | Có bao nhiêu phiên đang mở? Có thường xuyên disconnect không? | Active connections, setup failures, connection duration |
| Interaction/stream | Route nào chậm hoặc lỗi? Stream nào bị hủy? | Interaction rate, duration, active streams, cancellation |
| Payload | Dữ liệu có quá lớn hoặc decode lỗi không? | Data bytes, metadata bytes, encode/decode failures |
| Business | Người dùng có hoàn tất được công việc không? | Orders accepted, commands rejected, processing lag |

## 2. Kiến trúc quan sát bốn lớp

~~~mermaid
flowchart TD
    A[Browser / Service Peer] --> B[Transport: TCP / WebSocket]
    B --> C[RSocket Connection / SETUP]
    C --> D[Interaction: RR / FNF / Stream / Channel]
    D --> E[Payload: Data + Metadata + Codec]
    E --> F[Business Handler / Domain Service]
    F --> G[Database / Broker / Downstream]
    B -.-> M1[Connection metrics]
    D -.-> M2[Interaction and stream metrics]
    E -.-> M3[Payload metrics]
    F -.-> M4[Business metrics]
    M1 --> O[Micrometer / OpenTelemetry]
    M2 --> O
    M3 --> O
    M4 --> O
    O --> P[Prometheus / OTLP / Dashboard]
~~~

Điểm đặt instrumentation nên nằm sát nơi có thể xác định ý nghĩa của dữ liệu:

- Transport/connection layer biết connection mở, đóng và lỗi transport.
- RSocket interaction layer biết loại interaction, route và vòng đời stream.
- Codec hoặc payload boundary biết số byte thực tế và lỗi encode/decode.
- Domain service biết một đơn hàng được chấp nhận, từ chối hay commit.

Không nên suy đoán metric nghiệp vụ từ trạng thái transport. Ví dụ client gửi fire-and-forget thành công không chứng minh server đã lưu lệnh.

## 3. Metrics, logs và traces bổ sung cho nhau

Ba tín hiệu quan sát có mục đích khác nhau:

| Tín hiệu | Dùng để trả lời | Đặc điểm |
|---|---|---|
| Metrics | Điều gì đang tăng, giảm hoặc vượt ngưỡng? | Tổng hợp, nhẹ, phù hợp dashboard và alert |
| Logs | Sự kiện cụ thể nào đã xảy ra? | Có ngữ cảnh chi tiết, cần lọc và bảo vệ dữ liệu |
| Traces | Một interaction đi qua những thành phần nào và chậm ở đâu? | Theo dõi đường đi xuyên service |

Ví dụ:

- Metric cho biết p95 của route orders.find tăng từ 80 ms lên 900 ms.
- Trace cho thấy phần lớn thời gian nằm ở database query.
- Log có correlation ID cho biết request thuộc deployment và partition nào.

Không ghi toàn bộ payload để thay thế metrics hoặc traces. Payload có thể chứa dữ liệu cá nhân, token hoặc thông tin nghiệp vụ nhạy cảm.

## 4. Lớp connection: quan sát vòng đời phiên

Connection metrics mô tả trạng thái transport và RSocket session. Nên theo dõi:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| rsocket.connections.active | Gauge | Số connection hiện đang mở |
| rsocket.connections.opened | Counter | Tổng connection được mở |
| rsocket.connections.closed | Counter | Tổng connection đã đóng |
| rsocket.setup.accepted | Counter | SETUP được chấp nhận |
| rsocket.setup.rejected | Counter | SETUP bị từ chối |
| rsocket.connection.duration | Timer | Thời gian sống của connection |
| rsocket.connection.errors | Counter | Lỗi transport/session |
| rsocket.connection.reconnects | Counter | Số lần client reconnect |
| rsocket.connection.keepalive.timeouts | Counter | Số lần timeout keepalive |

Các chiều phân loại hữu ích có thể gồm transport (tcp/websocket), kết quả (accepted/rejected), nguyên nhân đóng (normal/timeout/error) và service role. Dùng giá trị cố định, không dùng địa chỉ socket hoặc session ID làm tag metric.

### Active connection khác connection opened

- Active connections là số phiên hiện tại, nên dùng Gauge.
- Opened/closed là sự kiện tích lũy, nên dùng Counter.
- Connection duration là phân phối thời gian sống, nên dùng Timer.

Một server có 5.000 connection opened trong một giờ nhưng chỉ có 300 active connections tại thời điểm hiện tại. Không thể dùng tổng opened để suy ra tải đang hoạt động.

### Ví dụ đăng ký Gauge và Counter

~~~java
@Component
public class RSocketConnectionMetrics {

    private final AtomicInteger active = new AtomicInteger();
    private final Counter opened;
    private final Counter closed;

    public RSocketConnectionMetrics(MeterRegistry registry) {
        Gauge.builder(
                "rsocket.connections.active",
                active,
                AtomicInteger::get)
            .description("Active RSocket connections")
            .register(registry);

        this.opened = Counter.builder("rsocket.connections.opened")
            .description("Total opened RSocket connections")
            .register(registry);

        this.closed = Counter.builder("rsocket.connections.closed")
            .description("Total closed RSocket connections")
            .register(registry);
    }

    public void onOpen() {
        active.incrementAndGet();
        opened.increment();
    }

    public void onClose() {
        active.updateAndGet(value -> Math.max(0, value - 1));
        closed.increment();
    }
}
~~~

Đây là bộ đếm minh họa ở application boundary. Trong ứng dụng thực, gọi onOpen/onClose từ lifecycle callback của transport hoặc RSocket session và bảo đảm mỗi connection chỉ tăng/giảm đúng một lần, kể cả khi lỗi xảy ra trong lúc SETUP.

Nếu một process có nhiều instance, mỗi instance có Gauge riêng. Dashboard tổng hợp bằng phép sum theo các instance đang hoạt động; không cộng dồn Counter tuyệt đối giữa các lần restart mà nên dùng rate/increase.

## 5. Lớp interaction: đo từng loại request

RSocket có bốn interaction model chính:

- **Request-response:** một request, tối đa một response.
- **Fire-and-forget:** một request, không có response payload.
- **Request-stream:** một request mở đầu, nhiều response.
- **Request-channel:** hai hướng đều có thể truyền stream.

Nên đo riêng theo interaction type và route ổn định:

| Metric | Ý nghĩa |
|---|---|
| rsocket.interactions | Số interaction được bắt đầu |
| rsocket.interaction.duration | Thời gian xử lý interaction |
| rsocket.interactions.errors | Số interaction kết thúc bằng lỗi |
| rsocket.streams.active | Số stream đang hoạt động |
| rsocket.streams.cancelled | Số stream bị hủy |
| rsocket.streams.completed | Số stream hoàn tất |
| rsocket.stream.items.in | Số payload phần tử nhận vào |
| rsocket.stream.items.out | Số payload phần tử phát ra |
| rsocket.flow_control.request_n.frames | Số REQUEST_N frame quan sát được |
| rsocket.flow_control.demand.items | Tổng demand units trong initial request và các REQUEST_N tiếp theo |

Initial demand được mang trong frame mở interaction như REQUEST_STREAM hoặc REQUEST_CHANNEL; REQUEST_N là frame cấp thêm demand sau đó. Nếu instrument ở protocol layer, hãy tách số frame khỏi tổng demand units để biết consumer gửi bao nhiêu lần cập nhật credit và yêu cầu bao nhiêu phần tử.

Không gộp số interaction với số payload. Một request-stream chỉ là một interaction nhưng có thể phát hàng triệu payload. Một request-channel có thể có hàng nghìn phần tử ở cả hai hướng.

### Đo thời gian cho request-response

~~~java
@Component
public class OrderHandlerMetrics {

    private final MeterRegistry registry;
    private final OrderService orderService;

    public OrderHandlerMetrics(
            MeterRegistry registry,
            OrderService orderService) {
        this.registry = registry;
        this.orderService = orderService;
    }

    public Mono<OrderView> find(FindOrderRequest request) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return orderService.find(request.orderId())
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "success";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancelled";
                        default -> "other";
                    };

                    Timer timer = Timer.builder("rsocket.interaction.duration")
                        .description("RSocket request-response duration")
                        .tag("route", "orders.find")
                        .tag("interaction", "request-response")
                        .tag("outcome", outcome)
                        .register(registry);

                    sample.stop(timer);
                });
        });
    }
}
~~~

Trong code sản phẩm, nên chọn một cách ghi Timer nhất quán. Ví dụ trên minh họa Timer.Sample để chỉ quyết định outcome khi interaction kết thúc; có thể viết gọn bằng một Timer được đăng ký trước và gọi sample.stop(timer). Không tạo thêm Counter chỉ để đếm cùng event đã được Timer ghi nhận vì Timer đã có count.

Với request-stream, đo ít nhất hai thời gian khác nhau:

- Time to first response: từ lúc mở stream đến payload đầu tiên.
- Stream lifetime: từ lúc mở đến complete, error hoặc cancel.

Một stream kéo dài 30 phút có thể hoàn toàn bình thường; nếu chỉ nhìn duration tổng, dashboard sẽ nhầm stream khỏe mạnh với request bị treo. Nên theo dõi cả thời gian tới payload đầu tiên, inter-arrival time và tiến độ phát dữ liệu. Timer ghi thời gian khi interaction kết thúc; LongTaskTimer phù hợp để quan sát thời lượng hiện tại của stream/connection vẫn đang chạy.

## 6. Theo dõi stream đang chạy và cancellation

Stream metrics giúp trả lời:

- Có bao nhiêu stream đang hoạt động?
- Stream nào không phát dữ liệu trong thời gian dài?
- Consumer hủy stream bao nhiêu lần?
- Một route có nhiều stream tồn tại lâu bất thường không?
- Khi client disconnect, publisher có được cancel và cleanup không?

Ví dụ Gauge cho active stream:

~~~java
@Component
public class StreamMetrics {

    private final AtomicInteger activeStreams = new AtomicInteger();

    public StreamMetrics(MeterRegistry registry) {
        Gauge.builder(
                "rsocket.streams.active",
                activeStreams,
                AtomicInteger::get)
            .register(registry);
    }

    public <T> Flux<T> track(Flux<T> source) {
        return Flux.defer(() -> {
            activeStreams.incrementAndGet();

            return source.doFinally(signal ->
                activeStreams.decrementAndGet());
        });
    }
}
~~~

Dùng Flux.defer để tăng gauge cho từng subscription thay vì lúc tạo publisher. doFinally được gọi khi complete, error hoặc cancel nên có thể giảm gauge trong mọi nhánh kết thúc.

Không dùng một Gauge cho số stream đã mở trong cả vòng đời process. Đó là Counter. Gauge phải phản ánh giá trị hiện tại.

## 7. Lớp payload: quan sát kích thước và codec

Payload metrics mô tả kích thước và khả năng chuyển đổi dữ liệu, không mô tả ý nghĩa nghiệp vụ.

Các chỉ số nên cân nhắc:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| rsocket.payload.data.size | DistributionSummary | Phân phối kích thước data theo byte |
| rsocket.payload.metadata.size | DistributionSummary | Phân phối kích thước metadata |
| rsocket.payload.encode.errors | Counter | Lỗi serialize |
| rsocket.payload.decode.errors | Counter | Lỗi deserialize |
| rsocket.payload.rejected | Counter | Payload bị từ chối do giới hạn |
| rsocket.payload.codec.duration | Timer | Thời gian encode/decode |
| rsocket.payload.content_type | Tag có giới hạn | MIME type đã chuẩn hóa |

Kích thước nên đo bằng byte thực tế sau encode nếu cần đánh giá network và allocator. Không dùng String.length() hoặc object.toString().length() làm kích thước wire payload vì chúng không phản ánh byte UTF-8, binary encoding hoặc framing overhead.

### Ví dụ DistributionSummary

~~~java
@Component
public class PayloadMetrics {

    private final DistributionSummary dataSize;
    private final DistributionSummary metadataSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.dataSize = DistributionSummary
            .builder("rsocket.payload.data.size")
            .baseUnit("bytes")
            .description("Encoded RSocket data payload size")
            .register(registry);

        this.metadataSize = DistributionSummary
            .builder("rsocket.payload.metadata.size")
            .baseUnit("bytes")
            .description("Encoded RSocket metadata size")
            .register(registry);
    }

    public void recordDataBytes(int bytes) {
        dataSize.record(bytes);
    }

    public void recordMetadataBytes(int bytes) {
        metadataSize.record(bytes);
    }
}
~~~

DistributionSummary phù hợp với giá trị số như kích thước payload. Timer phù hợp với thời gian. Cả hai đều cung cấp count, nên không cần counter trùng cho cùng phép đo.

### Không log nội dung payload theo mặc định

Để điều tra decode error, ghi MIME type, codec, route đã chuẩn hóa, kích thước byte và loại lỗi. Tránh ghi token, password, thông tin cá nhân hoặc toàn bộ payload. Nếu cần debug nội dung, dùng sampling có kiểm soát, redaction và thời hạn lưu ngắn.

## 8. Lớp business: đo kết quả mà người dùng thực sự quan tâm

Business metrics trả lời hệ thống có hoàn thành công việc hay không. Chúng được ghi ở domain/service boundary sau khi đã xác định kết quả nghiệp vụ.

Ví dụ:

| Metric | Ý nghĩa |
|---|---|
| orders.accepted | Số đơn được chấp nhận |
| orders.rejected | Số đơn bị từ chối |
| orders.processed.duration | Thời gian xử lý đơn |
| commands.executed | Số command đã thực thi |
| commands.failed | Số command thất bại |
| events.duplicates | Số event trùng bị loại |
| events.gaps | Số khoảng trống sequence được phát hiện |
| events.consumer.lag | Độ trễ xử lý so với producer |
| devices.online | Số thiết bị đang online theo trạng thái nghiệp vụ |

Ví dụ ghi kết quả đơn hàng:

~~~java
// Đoạn method nằm trong một bean đã inject MeterRegistry.
public Mono<OrderResult> createOrder(CreateOrderCommand command) {
    return orderService.create(command)
        .doOnNext(result -> {
            Counter.builder("orders.completed")
                .tag("outcome", result.accepted()
                    ? "accepted" : "rejected")
                .register(meterRegistry)
                .increment();
        });
}
~~~

Metric orders.completed chỉ tăng khi service phát kết quả. Nếu cần xác nhận đã commit database, hãy ghi metric ở sau ranh giới commit hoặc từ event/outbox đã commit. Không tăng metric accepted chỉ vì handler nhận được request.

Business metrics cần thống nhất định nghĩa. Ví dụ “đơn thành công” có thể là accepted, paid, fulfilled hoặc delivered; các trạng thái này không nên gộp thành một metric mơ hồ.

## 9. Không nhầm transport success với business success

Một request có thể đi qua các trạng thái:

~~~text
WebSocket connected
    -> RSocket SETUP accepted
        -> route authorized
            -> payload decoded
                -> handler invoked
                    -> domain validation passed
                        -> database committed
                            -> business result emitted
~~~

Mỗi bước có thể thành công hoặc thất bại độc lập.

| Quan sát | Chứng minh được | Không chứng minh được |
|---|---|---|
| WebSocket open | Transport handshake thành công | RSocket SETUP hoặc authentication thành công |
| SETUP accepted | RSocket session được thiết lập | User được phép gọi mọi route |
| Request frame received | Server nhận interaction | Payload decode hoặc business handler thành công |
| Response emitted | Responder phát response | Tác dụng phụ bên ngoài đã commit nếu response được phát quá sớm |
| FNF send completed | Client hoàn tất API gửi theo giao thức | Server đã xử lý bền vững |
| Business committed event | Domain transaction đã commit theo hợp đồng | Client chắc chắn đã nhận được response |

Khi thiết kế dashboard, hãy hiển thị các lớp này cạnh nhau để xác định ranh giới lỗi.

## 10. Metrics cơ bản với Micrometer

Spring Boot Actuator cung cấp hạ tầng Micrometer và auto-configuration cho các registry được thêm vào classpath. Các loại meter thường dùng:

| Meter | Khi dùng |
|---|---|
| Counter | Đếm sự kiện tích lũy như setup failure hoặc decode error |
| Gauge | Giá trị hiện tại như active connection, active stream, queue depth |
| Timer | Thời gian và số lần xảy ra của interaction |
| DistributionSummary | Phân phối giá trị không phải thời gian như payload bytes |
| LongTaskTimer | Theo dõi thời lượng hiện tại và số tác vụ/stream đang chạy lâu |

Không tăng Counter bằng một giá trị âm hoặc dùng Gauge cho tổng sự kiện tích lũy. Đối với latency, dùng Timer thay vì tự tính thời gian rồi ghi DistributionSummary.

### Ví dụ ghi lỗi theo loại cố định

~~~java
Counter.builder("rsocket.interactions.errors")
    .tag("route", "orders.find")
    .tag("interaction", "request-response")
    .tag("error.type", "decode")
    .register(meterRegistry)
    .increment();
~~~

Giá trị tag error.type nên thuộc một tập hữu hạn như transport, protocol, authentication, decode, timeout, business. Không dùng error message hoặc stack trace làm tag.

## 11. Observation và tracing cho một interaction

Micrometer Observation có thể tạo metrics và spans từ cùng một observation. Spring Boot cung cấp ObservationRegistry và Micrometer Tracing auto-configuration khi có dependency tracer phù hợp.

Ở application boundary, tạo observation với tên ổn định và các low-cardinality key như route template, interaction type và outcome. Với code reactive, observation phải sống từ lúc subscribe đến khi publisher complete/error/cancel. Không bọc một Mono bằng Observation.observe(() -> mono) theo cách đồng bộ rồi coi observation đã đo xong: supplier chỉ trả về publisher, trong khi công việc bất đồng bộ vẫn chưa chạy hoặc chưa hoàn tất. Dùng instrumentation hỗ trợ Reactor/context propagation hoặc gắn lifecycle start/stop theo subscription và terminal signal.

Tên route cần là route template ổn định. Không đưa orderId vào low-cardinality key vì mỗi đơn hàng có thể tạo một time series mới.

Micrometer Observation phân biệt low-cardinality key values dùng cho metrics và high-cardinality key values phù hợp với trace/span. Dù trace có thể chứa ID cụ thể để điều tra, vẫn cần cân nhắc PII, quyền truy cập và retention trước khi ghi.

Nếu cần message ID hoặc connection ID để điều tra một lần cụ thể, có thể đưa vào trace/span hoặc structured log ở mức phù hợp, nhưng cần đánh giá quyền riêng tư và chi phí lưu trữ. Không đưa chúng thành metric tag.

### Trace propagation qua RSocket

Để trace xuyên qua các peer, cần truyền trace context và cấu hình phía nhận extract context. Dùng instrumentation tương thích với phiên bản Spring/RSocket đang triển khai hoặc một metadata convention rõ ràng cho W3C trace context.

Không giả định RSocket tự động mang trace context chỉ vì ứng dụng đã có HTTP tracing. Hãy kiểm thử trace xuyên qua WebSocket/TCP, request-response, stream và channel. Với stream dài, cân nhắc một span cho vòng đời stream và span riêng cho từng batch/operation thay vì tạo một trace khổng lồ chứa mọi payload.

## 12. Structured logs và correlation

Log nên ghi sự kiện có cấu trúc, chẳng hạn:

~~~json
{
  "event": "rsocket.interaction.completed",
  "service": "orders",
  "route": "orders.find",
  "interaction": "request-response",
  "outcome": "success",
  "duration_ms": 42,
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "stream_id": 7
}
~~~

Ví dụ chỉ minh họa schema log. Stream ID có thể hữu ích để điều tra frame trong phạm vi connection nhưng không phải khóa metric và không có ý nghĩa toàn cục. Nếu log connection ID hoặc principal, cần bảo vệ log access và tránh dữ liệu nhận diện không cần thiết.

Với Micrometer Tracing, Spring Boot có thể thêm traceId/spanId vào MDC để log liên quan cùng trace có thể được tìm kiếm. Không tự ghi access token, cookie, credential metadata hoặc payload nhạy cảm.

## 13. Cardinality: chọn tag có giới hạn

Một metric có thể tạo nhiều time series khi kết hợp tên meter và các tag. Nếu tag có quá nhiều giá trị, Prometheus và backend sẽ tốn bộ nhớ, CPU và chi phí lưu trữ.

**Tag phù hợp:**

- route template đã chuẩn hóa, ví dụ orders.find.
- interaction type: request-response, fire-and-forget, request-stream, request-channel.
- transport: tcp hoặc websocket.
- outcome: success, error, cancelled.
- error type: timeout, decode, auth, protocol.
- codec/MIME type từ allowlist.
- deployment/service role nếu tập giá trị được kiểm soát.

**Không nên dùng làm metric tag:**

- userId, tenantId, orderId, deviceId.
- connectionId, sessionId, Stream ID.
- messageId, traceId, correlationId.
- raw route chứa ID động.
- payload, exception message hoặc URL query string.

Nếu cần tìm một orderId cụ thể, dùng trace hoặc log đã được kiểm soát. Metrics dành cho xu hướng tổng hợp, không phải công cụ tra cứu từng người dùng.

## 14. Cấu hình Spring Boot Actuator và Prometheus

Thêm Actuator và registry Prometheus phù hợp với phiên bản Spring Boot của dự án. Ví dụ cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        rsocket.interaction.duration: true
~~~

Endpoint Prometheus thường được cung cấp tại /actuator/prometheus khi có registry tương ứng. Chỉ expose endpoint cần thiết và bảo vệ chúng bằng network policy hoặc Spring Security; không để metrics endpoint công khai nếu nó tiết lộ thông tin vận hành.

Spring Boot auto-configures MeterRegistry khi registry implementation có trên classpath. Các metric RSocket nghiệp vụ tùy chỉnh vẫn cần được ghi ở code của ứng dụng. Không mặc định rằng HTTP server metrics phản ánh đầy đủ interaction RSocket.

### Một số truy vấn PromQL tham khảo

Tỷ lệ interaction lỗi trong 5 phút:

~~~promql
sum(rate(rsocket_interactions_errors_total[5m]))
/
sum(rate(rsocket_interactions_total[5m]))
~~~

Tổng số connection đang hoạt động trên các instance:

~~~promql
sum(rsocket_connections_active)
~~~

p95 latency của request-response theo route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(rsocket_interaction_duration_seconds_bucket{
      interaction="request-response"
    }[5m])
  )
)
~~~

Tên metric xuất Prometheus phụ thuộc naming convention và registry. Hãy kiểm tra tên thực tế tại endpoint trước khi dùng query trong alert.

## 15. Dashboard theo bốn lớp

Một dashboard vận hành nên có bốn nhóm panel.

| Nhóm | Panel nên có |
|---|---|
| Connection | Active connections, setup accepted/rejected, connection duration, disconnect/reconnect rate, keepalive timeout |
| Interaction | Rate theo route/type, p50/p95/p99 duration, error rate, active streams, cancellation, time to first item |
| Payload | Data/metadata bytes p50/p95/max, codec errors, decode duration, rejected oversized payload |
| Business | Orders accepted/rejected, command success, event processing lag, duplicate/gap count, SLA latency |

Thêm panel JVM và dependency để giải thích nguyên nhân: heap/direct memory, GC pause, CPU, thread/event-loop saturation, database pool, downstream latency và queue depth.

Không đặt quá nhiều panel ở cùng một mức chi tiết. Bắt đầu bằng overview, sau đó drill down theo route, interaction type và instance.

## 16. SLO và cảnh báo

Alert nên gắn với tác động tới người dùng hoặc nghiệp vụ, không chỉ với một con số kỹ thuật riêng lẻ.

Ví dụ:

| Tín hiệu | Điều kiện cảnh báo tham khảo | Tác động cần kiểm tra |
|---|---|---|
| Setup rejection | Tăng bất thường so với baseline | Auth/config/certificate hoặc client rollout |
| Connection churn | Open/close rate tăng mạnh | Proxy timeout, mạng hoặc reconnect loop |
| Interaction p95 | Vượt SLO liên tục | Handler hoặc dependency chậm |
| Stream cancellation | Tăng đột biến | Client rời đi, timeout hoặc server lỗi |
| Payload decode error | Tăng theo codec/version | Schema hoặc MIME type không tương thích |
| Active stream/queue | Tiến gần giới hạn | Slow consumer, leak hoặc producer quá nhanh |
| Business rejection | Tăng theo loại nghiệp vụ | Validation, policy hoặc dependency |
| Event lag/gap | Vượt ngưỡng SLA | Consumer không theo kịp hoặc mất dữ liệu |

Dùng multi-window alert hoặc burn-rate alert cho SLO quan trọng để tránh cảnh báo từ một spike ngắn. Tách alert theo mức độ ảnh hưởng: connection failures toàn hệ thống cần xử lý nhanh hơn một route thử nghiệm có ít người dùng.

## 17. Phân tích sự cố bằng cách đi từ ngoài vào trong

| Triệu chứng | Lớp cần xem trước | Hướng điều tra |
|---|---|---|
| Nhiều client không kết nối được | Connection | WebSocket upgrade, TCP, TLS, SETUP, proxy |
| Connection ổn định nhưng route chậm | Interaction | Handler duration, scheduler, downstream span |
| Chỉ payload lớn bị lỗi | Payload | Frame/payload limit, codec, direct memory |
| Response thành công nhưng đơn không hoàn tất | Business | Transaction, outbox, async worker và commit |
| Stream active tăng nhưng không có item mới | Interaction/stream | Source stalled, demand, cancellation, timeout |
| Một instance lỗi nhiều hơn instance khác | Tất cả lớp theo instance | Deployment, resource, network path, config drift |
| Business lag tăng nhưng network bình thường | Business | Consumer throughput, database, broker, queue |

Quy trình điều tra:

1. Xác định thời điểm và route bị ảnh hưởng.
2. Kiểm tra connection/setup có ổn định không.
3. Kiểm tra interaction latency và outcome.
4. Kiểm tra payload size, codec và lỗi decode.
5. Mở trace để xác định dependency chậm.
6. Kiểm tra business commit, queue lag và kết quả cuối.
7. Đối chiếu logs theo trace/correlation ID.

## 18. Những lỗi thiết kế observability thường gặp

- Chỉ đếm request mà không đo stream lifetime và payload count.
- Dùng Gauge cho tổng sự kiện thay vì Counter.
- Tạo Counter riêng trùng với count mà Timer đã cung cấp.
- Gắn userId, orderId, Stream ID hoặc traceId làm metric tag.
- Đo payload bằng số ký tự thay vì byte đã encode.
- Coi FNF send completion là business acknowledgement.
- Coi SETUP success là mọi route đều được phép.
- Đo thời gian stream dài nhưng không đo time to first response.
- Chỉ log exception message, không có route/interaction/outcome.
- Tạo trace quá dài cho stream chạy nhiều giờ.
- Expose Actuator/Prometheus endpoint mà không kiểm soát truy cập.
- Ghi token hoặc payload nhạy cảm vào log.

## 19. Kiểm thử instrumentation

Instrumentation cũng cần được kiểm thử để tránh metric sai hoặc bị rò rỉ cardinality.

Các trường hợp nên có:

1. Connection mở rồi đóng làm active gauge trở về giá trị ban đầu.
2. SETUP rejected tăng đúng counter.
3. Request-response success/error/cancel được ghi đúng outcome.
4. Request-stream complete/error/cancel đều giảm active stream gauge.
5. Một stream có nhiều payload tăng payload count nhưng chỉ tăng interaction count một lần.
6. Payload size ghi đúng byte sau encode.
7. Codec error không bị tính nhầm thành business rejection.
8. Business success chỉ ghi sau khi commit theo hợp đồng.
9. Route template được chuẩn hóa, không chứa ID động.
10. Trace context đi qua client/server và downstream.
11. Logs không chứa token, cookie hoặc payload nhạy cảm.
12. Prometheus endpoint chỉ expose và truy cập theo policy.

Có thể dùng SimpleMeterRegistry trong unit test để kiểm tra số lần tăng, gauge và Timer. Integration test với RSocket TCP/WebSocket thật giúp kiểm tra lifecycle callback, stream cancellation và context propagation.

## 20. Checklist triển khai

- Đã tách connection, interaction, payload và business metrics.
- Có Gauge cho active connections và active streams.
- Có Counter cho setup/error/reconnect/duplicate/gap.
- Có Timer cho interaction latency và business processing time.
- Có DistributionSummary cho payload bytes.
- Đã tách first-response latency và stream lifetime.
- Có route template và interaction type làm tag có giới hạn.
- Không dùng ID động hoặc PII làm metric tag.
- Có trace propagation và structured log correlation.
- Đã phân biệt transport success với business commit.
- Có dashboard theo bốn lớp và SLO alert.
- Actuator/Prometheus endpoint được bảo vệ.
- Có test cho success, error, cancel và cardinality.

## 21. Kết luận

Connection metrics cho biết phiên RSocket có ổn định hay không. Interaction metrics cho biết route và stream hoạt động thế nào. Payload metrics cho biết kích thước và khả năng encode/decode dữ liệu. Business metrics cho biết thao tác mà người dùng cần có thực sự hoàn tất hay không.

Kết hợp bốn lớp với logs và traces sẽ giúp xác định lỗi ở đúng ranh giới. Micrometer cung cấp Counter, Gauge, Timer và DistributionSummary; Spring Boot Actuator cung cấp hạ tầng xuất metrics, còn instrumentation tại handler và domain service cần được thiết kế theo semantics của ứng dụng.

Hãy dùng tag có cardinality thấp, giữ ID cụ thể trong trace/log có kiểm soát và định nghĩa rõ mỗi metric đo điều gì. Một hệ thống observability tốt không chỉ cho biết có lỗi, mà còn giúp trả lời lỗi bắt đầu ở connection, interaction, payload hay nghiệp vụ và ảnh hưởng đến người dùng ra sao.

Tài liệu tham khảo:
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot – Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)

