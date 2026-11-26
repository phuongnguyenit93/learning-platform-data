# Không có quan sát

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Tuy nhiên, khi publisher chỉ phát event rồi tiếp tục chạy, listener xử lý ở thread khác và các module có thể nằm trên nhiều service, hệ thống rất dễ mất dấu luồng xử lý. **Không có quan sát** là anti-pattern trong đó ứng dụng không cung cấp đủ log, metric, trace và trạng thái vận hành để biết event đã được phát, nhận, xử lý, retry hay thất bại ở đâu.

Một hệ thống không có quan sát có thể vẫn chạy bình thường trong điều kiện tải thấp. Khi sự cố xảy ra, đội vận hành không biết event nào bị kẹt, listener nào gây lỗi, consumer nào đang tụt lại hoặc side effect đã được commit chưa. Việc điều tra phải dựa vào phỏng đoán, restart hoặc replay thử, làm tăng nguy cơ mất dữ liệu và xử lý trùng.

## 1. Nhận diện anti-pattern

Một luồng event có thể gồm nhiều bước: publisher commit transaction, publication được ghi nhận, listener nội bộ xử lý, event được gửi qua broker, consumer cập nhật read model và một dịch vụ khác thực hiện side effect. Nếu mỗi bước không phát ra tín hiệu có thể liên kết, không ai có thể trả lời câu hỏi “event này đang ở đâu?”.

Các dấu hiệu thường gặp:

- Publisher không ghi log hoặc metric khi công bố event.
- Listener chỉ ghi một dòng log chung như “received event” mà không có event ID hay correlation ID.
- Exception bị catch rồi bỏ qua, khiến hệ thống báo thành công dù nghiệp vụ chưa hoàn tất.
- Không đo thời gian xử lý, tỷ lệ thất bại hoặc số event tồn đọng.
- Không có trace nối publisher với listener bất đồng bộ.
- Không theo dõi publication incomplete, consumer lag, retry topic hoặc DLT.
- Dashboard chỉ hiển thị CPU, memory và HTTP request, không phản ánh event pipeline.
- Alert chỉ dựa vào process UP, dù consumer đã ngừng xử lý.
- Khi có sự cố, không thể xác định event đã commit side effect hay chưa.

Ví dụ, API xác nhận đơn hàng trả HTTP 200 nhưng listener Inventory không cập nhật reservation. Nếu không có trace, metric hoặc trạng thái publication, đội vận hành không thể biết event chưa được phát, listener chưa được gọi, listener đã lỗi hay projection đã cập nhật ở database khác.

## 2. Vì sao event-driven cần observability?

Event-driven architecture tách thời điểm phát và thời điểm xử lý. Publisher thường không chờ mọi consumer hoàn tất. Vì vậy, trạng thái HTTP của request ban đầu không phản ánh toàn bộ kết quả nghiệp vụ.

Không có observability gây ra các vấn đề:

| Vấn đề | Hệ quả |
| --- | --- |
| Không có event identity | Không tìm được cùng một event qua nhiều module, retry và broker. |
| Không có log có cấu trúc | Khó lọc và nối các bước xử lý. |
| Không có metrics | Không biết lỗi tăng, throughput giảm hay backlog đang lớn dần. |
| Không có distributed trace | Không xác định được bước nào gây latency hoặc lỗi. |
| Không có publication state | Không biết listener nội bộ đã hoàn tất hay còn incomplete. |
| Không có broker metrics | Không phát hiện consumer lag, rebalance hoặc DLT tăng. |
| Không có alert | Sự cố chỉ được phát hiện khi người dùng báo lỗi. |
| Không có runbook | Mỗi ca trực tự suy luận và có thể chọn recovery nguy hiểm. |

Observability không chỉ phục vụ debug. Nó giúp đặt SLO, phát hiện suy giảm trước khi vượt SLA, kiểm tra hiệu quả retry, đánh giá capacity và chứng minh rằng event được xử lý theo invariant nghiệp vụ.

## 3. Phân biệt logs, metrics và traces

Ba loại tín hiệu trả lời ba nhóm câu hỏi khác nhau:

| Tín hiệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Logs | Điều gì đã xảy ra với một event cụ thể? | Event evt-123 bị listener Inventory từ chối vì dependency timeout. |
| Metrics | Hệ thống đang hoạt động ở mức nào và xu hướng ra sao? | Tỷ lệ listener failure tăng lên 8%; oldest incomplete publication là 12 phút. |
| Traces | Một luồng xử lý đi qua những thành phần nào và mất thời gian ở đâu? | Request xác nhận đơn hàng → publisher → listener → database projection. |

Audit record có thể bổ sung bằng chứng về hành động nghiệp vụ hoặc thao tác vận hành. Audit và observability có mục tiêu khác nhau: audit cần tính toàn vẹn và lưu giữ theo chính sách; log kỹ thuật có thể được sampling hoặc expire theo retention.

Không nên chỉ chọn một loại tín hiệu. Log đơn lẻ không cho biết xu hướng; metric không giải thích nguyên nhân của một event cụ thể; trace có thể không được giữ cho mọi request nếu sampling được bật.

## 4. Thiết kế event metadata để truy vết

Event nên có định danh ổn định và metadata tối thiểu để nối các bước xử lý. Một envelope có thể gồm:

| Field | Mục đích |
| --- | --- |
| eventId | Định danh duy nhất của một event; giữ nguyên khi retry hoặc replay cùng event. |
| eventType | Loại event theo hợp đồng. |
| schemaVersion | Phiên bản payload để chọn parser/upcaster phù hợp. |
| occurredAt | Thời điểm nghiệp vụ xảy ra theo UTC. |
| correlationId | Nối các event và thao tác thuộc cùng một luồng nghiệp vụ. |
| causationId | Chỉ ra event hoặc command trực tiếp tạo ra event hiện tại. |
| aggregateId | Định danh aggregate liên quan, nếu phù hợp với hợp đồng. |
| aggregateVersion | Hỗ trợ kiểm tra thứ tự và phát hiện event cũ. |

Không phải event nào cũng cần tất cả field. Chọn metadata theo mục tiêu truy vết và hợp đồng của hệ thống. eventId không nên thay đổi khi cùng một event được giao lại; nếu tạo event nghiệp vụ mới sau một bước xử lý, event mới cần ID riêng và có thể giữ causationId của event trước.

Ví dụ envelope:

~~~java
public record EventEnvelope<T>(
    UUID eventId,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String correlationId,
    UUID causationId,
    T payload
) {}
~~~

Đây là mô hình minh họa. Có thể dùng metadata header của broker hoặc một envelope trong payload, miễn là producer và consumer thống nhất hợp đồng. Không đưa access token, session cookie, password hoặc toàn bộ security context vào event metadata.

## 5. Tạo structured logs ở publisher

Publisher cần phát ra tín hiệu cho biết event nào được tạo và gắn với giao dịch nghiệp vụ nào. Log nên có field riêng để hệ thống log search lọc được, thay vì ghép mọi thông tin vào một chuỗi tự do.

Ví dụ:

~~~java
@Service
@RequiredArgsConstructor
class OrderService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId, String correlationId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();

        UUID eventId = UUID.randomUUID();
        OrderConfirmed event =
            new OrderConfirmed(eventId, orderId, correlationId);

        events.publishEvent(event);

        log.info(
            "Application event published eventId={} eventType={} "
                + "aggregateId={} correlationId={}",
            eventId,
            "OrderConfirmed",
            orderId,
            correlationId
        );
    }
}
~~~

Log trên ghi nhận publisher đã gọi publishEvent trong transaction. Với transactional listener, đây chưa phải bằng chứng listener đã xử lý thành công. Nên phân biệt rõ published với handled hoặc completed để tránh tạo tín hiệu thành công sai.

Nếu transaction rollback sau log, dòng log publisher vẫn tồn tại dù publication record và dữ liệu nghiệp vụ có thể rollback. Vì vậy, log cần ghi rõ phase hoặc outcome, còn trạng thái commit nên được quan sát qua transaction completion hoặc publication registry phù hợp.

## 6. Quan sát listener và không nuốt exception

Listener cần log kết quả xử lý và giữ exception semantics để framework hoặc registry biết xử lý thất bại. Ví dụ:

~~~java
@Component
@RequiredArgsConstructor
class InventoryListener {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryListener.class);

    private final InventoryService inventory;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        try {
            inventory.reserve(event.orderId());
            log.info(
                "Application event handled eventId={} "
                    + "eventType={} listener={} outcome=success",
                event.eventId(),
                "OrderConfirmed",
                "inventory-order-listener"
            );
        } catch (RuntimeException exception) {
            log.error(
                "Application event handling failed eventId={} "
                    + "eventType={} listener={} exceptionType={}",
                event.eventId(),
                "OrderConfirmed",
                "inventory-order-listener",
                exception.getClass().getSimpleName(),
                exception
            );
            throw exception;
        }
    }
}
~~~

Ví dụ giả định event có eventId() và orderId(). Khi lỗi, handler ghi log rồi ném lại exception để transaction của listener thất bại theo cấu hình. Không catch exception chỉ để log rồi return bình thường; hành vi đó có thể khiến publication bị xem là completed dù side effect chưa được thực hiện.

Không ghi toàn bộ payload hoặc thông tin cá nhân nhạy cảm vào log. Ghi event ID, loại event, listener, exception category và correlation ID thường đủ để tra cứu record có kiểm soát.

## 7. Đo metrics cho event pipeline

Metrics cho biết hệ thống đang khỏe hay suy giảm theo thời gian. Một bộ metric cơ bản có thể gồm:

| Metric | Ý nghĩa |
| --- | --- |
| application.events.published | Số event được publisher công bố. |
| application.events.handled | Số lần listener hoàn tất xử lý. |
| application.events.failed | Số lần listener thất bại. |
| application.event.listener.duration | Thời gian xử lý listener. |
| application.event.publication.incomplete | Số publication chưa hoàn tất. |
| application.event.publication.oldest.age | Tuổi publication incomplete lâu nhất. |
| messaging.consumer.lag | Khoảng cách tiến độ consumer với dữ liệu mới nhất. |
| messaging.retry.records | Số record đang nằm ở retry route hoặc số lần retry. |
| messaging.dlt.records | Số record được đưa vào dead-letter topic. |

Tên metric thực tế phụ thuộc naming convention và instrumentation đang dùng. Cần thống nhất đơn vị, loại metric và ý nghĩa đếm: một event có thể được giao nhiều lần, vì vậy handled có thể đếm invocation thành công chứ không nhất thiết là số event duy nhất.

Ví dụ dùng Micrometer để đo thời gian listener:

~~~java
@Component
class TimedInventoryListener {

    private final MeterRegistry meterRegistry;
    private final InventoryService inventory;

    TimedInventoryListener(
            MeterRegistry meterRegistry,
            InventoryService inventory) {
        this.meterRegistry = meterRegistry;
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            inventory.reserve(event.orderId());
        } catch (RuntimeException exception) {
            outcome = "failure";
            throw exception;
        } finally {
            sample.stop(
                Timer.builder("application.event.listener.duration")
                    .tag("listener", "inventory-order")
                    .tag("event_type", "order-confirmed")
                    .tag("outcome", outcome)
                    .register(meterRegistry)
            );
        }
    }
}
~~~

Trong ví dụ, các tag là giá trị có số lượng hữu hạn. Đừng dùng eventId, orderId, customerId hoặc correlationId làm metric tag; mỗi giá trị mới có thể tạo một time series riêng và làm tăng cardinality rất lớn. Những ID này phù hợp với log hoặc trace attribute có kiểm soát.

## 8. Tránh metric cardinality cao

Một anti-pattern phổ biến là gắn mọi business key vào metric:

~~~java
// Không nên: orderId có thể có hàng triệu giá trị khác nhau.
Counter.builder("application.event.failed")
    .tag("order_id", orderId)
    .register(meterRegistry)
    .increment();
~~~

Metric backend phải lưu một time series cho mỗi tổ hợp tag. Cardinality cao làm tăng RAM, storage, chi phí truy vấn và có thể khiến monitoring mất ổn định đúng lúc sự cố xảy ra.

Nên dùng các tag có tập giá trị hữu hạn:

- event_type: loại event đã chuẩn hóa.
- listener: tên logic ổn định của handler.
- outcome: success, failure hoặc skipped.
- failure_category: transient, contract, business hoặc unknown.
- destination: main, retry hoặc dlt.
- environment: môi trường triển khai.

Nếu cần phân tích theo tenant hoặc aggregate, dùng log/tracing có giới hạn truy cập hoặc một hệ thống analytics được thiết kế cho high-cardinality data. Không biến metric thành kho lưu event identity.

## 9. Distributed tracing cho event bất đồng bộ

Trace giúp nối một request hoặc nghiệp vụ qua publisher, listener và broker. Trong hệ thống bất đồng bộ, trace context cần được truyền qua ranh giới thread hoặc message.

Luồng minh họa:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Order module]
    B --> C[Publish OrderConfirmed]
    C --> D[Inventory listener]
    C --> E[Notification listener]
    D --> F[Inventory database]
    E --> G[Notification provider]
~~~

Trace nên thể hiện:

- Span của request/publisher.
- Span hoặc consumer processing span của từng listener.
- Message/event identity và destination.
- Thời gian chờ giữa publish và consume nếu instrumentation hỗ trợ.
- Span của database hoặc dependency ngoài.
- Exception và outcome của từng bước.

Không phải listener nào cũng nằm trong cùng một trace nếu message được xử lý sau một khoảng thời gian dài hoặc qua broker. Có thể tạo span mới và liên kết với trace context được truyền trong message. Cách triển khai phụ thuộc Micrometer Tracing, OpenTelemetry và instrumentation của broker.

## 10. Context propagation qua thread và broker

@ApplicationModuleListener hỗ trợ xử lý bất đồng bộ. Thread xử lý listener có thể khác thread nhận HTTP request. Không nên giả định ThreadLocal, MDC hoặc SecurityContext tự động có mặt ở listener.

Các nguyên tắc:

- Dùng context propagation được hỗ trợ bởi executor/tracing integration để chuyển trace context qua thread.
- Với broker, truyền trace context qua header theo chuẩn instrumentation đang dùng.
- Giữ correlationId nghiệp vụ riêng nếu cần nối nhiều event thuộc cùng một quy trình.
- Xóa hoặc kết thúc context sau xử lý để tránh rò context sang task khác.
- Kiểm tra trace thực tế trong integration test, không chỉ kiểm tra code có gọi logger.

Correlation ID và trace ID có mục đích khác nhau. Trace ID định danh một trace kỹ thuật; correlation ID có thể nối nhiều trace qua nhiều bước nghiệp vụ hoặc thời gian dài. Không dùng correlation ID làm credential hoặc bằng chứng authorization.

## 11. Quan sát Event Publication Registry

Spring Modulith Event Publication Registry cung cấp trạng thái publication đến transactional listener. Đây là nguồn tín hiệu quan trọng cho các listener nội bộ:

- Số publication incomplete.
- Tuổi publication chưa hoàn tất lâu nhất.
- Số publication được hoàn tất theo thời gian.
- Listener có tỷ lệ lỗi hoặc thời gian xử lý bất thường.
- Số lần recovery/resubmit nếu ứng dụng có ghi nhận.

Registry giúp xác định publication nào còn pending hoặc incomplete theo cơ chế của thư viện. Nó không tự động là distributed trace, không thay thế log handler và không phản ánh consumer offset của Kafka.

Khi quan sát registry:

1. Dùng API được hỗ trợ bởi phiên bản Spring Modulith đang chạy.
2. Theo dõi count và age thay vì chỉ đếm incomplete.
3. Phân nhóm theo listener/event type nếu nguồn dữ liệu hỗ trợ.
4. Không query toàn bộ publication history ở mỗi lần scrape.
5. Không sửa trực tiếp bảng nội bộ hoặc xóa incomplete record để làm dashboard sạch.

Một publication incomplete mới phát sinh trong vài giây có thể bình thường. Publication tồn tại lâu hơn SLA hoặc tăng liên tục mới cần cảnh báo theo policy.

## 12. Quan sát Kafka, retry và DLT

Với Kafka, cần nhìn được tiến độ consumer và đường đi khi lỗi:

| Khu vực | Tín hiệu cần theo dõi |
| --- | --- |
| Producer | Send rate, send error, acknowledgement latency và serialization failure. |
| Topic | Incoming rate, bytes, partition distribution và retention. |
| Consumer group | Member count, partition assignment, rebalance và commit progress. |
| Lag | Lag theo partition và tuổi record lâu nhất. |
| Retry topic | Backlog, retry attempt và thời gian chờ. |
| DLT | Record count, event type, exception category và tuổi record. |
| Security | Authentication failure, authorization denied và ACL changes. |

Consumer lag khác 0 không nhất thiết là sự cố. Cần xem xu hướng tăng, tốc độ xử lý và SLA nghiệp vụ. DLT tăng đột ngột có thể chỉ ra schema incompatibility, lỗi dữ liệu hoặc dependency outage.

Với RabbitMQ hoặc broker khác, chọn metric tương ứng như ready/unacked messages, consumer count, redelivery và dead-letter queue depth. Không áp dụng tên metric Kafka cho broker khác.

## 13. Dashboard theo luồng nghiệp vụ

Dashboard hữu ích nên trả lời được cả câu hỏi kỹ thuật lẫn nghiệp vụ. Ví dụ dashboard cho luồng xác nhận đơn hàng:

| Nhóm | Nội dung |
| --- | --- |
| Volume | Orders confirmed, events published, events handled. |
| Reliability | Listener success/failure rate, incomplete publication, retry và DLT. |
| Latency | Thời gian từ publish đến listener hoàn tất; p50/p95/p99. |
| Backlog | Consumer lag, oldest event age và retry backlog. |
| Business outcome | Reservation thành công, không đủ hàng, order còn pending quá SLA. |
| Dependencies | Database latency, broker availability và API downstream. |

Đừng chỉ hiển thị tổng số event. Một event type có thể chiếm volume thấp nhưng ảnh hưởng nghiệp vụ rất lớn. Dashboard nên hỗ trợ filter theo service, event type, listener, environment và release version với tập giá trị được kiểm soát.

## 14. Alert theo SLO và hành vi

Alert cần kích hoạt khi có nguy cơ vi phạm SLO hoặc invariant nghiệp vụ, không chỉ khi một exception xuất hiện.

Ví dụ điều kiện cảnh báo:

- Tỷ lệ listener failure vượt ngưỡng trong một cửa sổ thời gian.
- Tuổi publication incomplete lâu nhất vượt SLA.
- Consumer lag tăng liên tục hoặc oldest record age vượt giới hạn.
- DLT có record mới thuộc event trọng yếu.
- Retry backlog tăng nhanh hơn khả năng drain.
- Tỷ lệ event đã publish nhưng chưa có business outcome tăng bất thường.
- Trace/metric cho thấy thời gian xử lý vượt SLO.

Ngưỡng phải dựa trên baseline và yêu cầu nghiệp vụ. Dùng cửa sổ thời gian, số mẫu tối thiểu và hysteresis để tránh alert chập chờn. Một alert tốt nêu service, event type/listener, phạm vi, mức ảnh hưởng, dashboard và runbook liên quan.

Không gửi alert cho mọi lần retry bình thường. Retry là một cơ chế phục hồi; chỉ cảnh báo khi retry rate, age hoặc backlog cho thấy hệ thống không còn phục hồi trong giới hạn cho phép.

## 15. Phân biệt health check và observability

Health check cho biết một thành phần có đủ điều kiện phục vụ tại thời điểm kiểm tra hay không. Observability giúp giải thích tại sao thành phần suy giảm và điều gì đã xảy ra trước đó.

Ví dụ:

- /actuator/health/readiness có thể báo UP vì process và dependency cần thiết đang sẵn sàng.
- Metric cho thấy listener failure rate đang tăng.
- Trace cho thấy dependency Inventory mất 4 giây mỗi lần gọi.
- Log theo eventId cho thấy event cụ thể đã retry hai lần.

Một health endpoint UP không chứng minh mọi event đã được xử lý. Ngược lại, một publication incomplete đơn lẻ không nhất thiết làm toàn bộ instance readiness DOWN. Cần kết hợp health, logs, metrics và traces để đánh giá đúng.

## 16. Bảo mật dữ liệu quan sát

Observability không được làm lộ dữ liệu nghiệp vụ hoặc bí mật:

- Không log access token, password, session cookie hoặc private key.
- Không ghi toàn bộ payload nếu có PII hoặc dữ liệu thanh toán.
- Mask hoặc loại bỏ field nhạy cảm trước khi log.
- Giới hạn quyền xem trace, log và health details.
- Đặt retention phù hợp cho log và trace.
- Không dùng event payload làm metric label.
- Kiểm soát ai được truy vấn event theo eventId/tenant.
- Audit các thao tác truy cập hoặc replay dữ liệu nhạy cảm.

Event metadata nên chứa định danh kỹ thuật cần thiết, không chứa credential. Khi cần điều tra dữ liệu nhạy cảm, dùng ID để truy vấn nguồn dữ liệu có kiểm soát thay vì sao chép payload vào log.

## 17. Kiểm thử observability

Observability cần được kiểm thử như một phần của behavior vận hành. Một số tình huống:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Publisher phát event thành công | Có log/metric publish với event type và correlation ID. |
| Publisher transaction rollback | Không phát tín hiệu business completion sai. |
| Listener xử lý thành công | Có metric duration và outcome success. |
| Listener ném exception | Có log failure, metric failure và exception vẫn được propagate theo policy. |
| Listener chạy async | Trace/context được nối đúng hoặc có link phù hợp. |
| Publication incomplete | Metric count/age phản ánh trạng thái. |
| Consumer lag tăng | Dashboard/alert hiển thị theo group và partition. |
| Retry hoặc DLT | Có attempt/destination/outcome và metadata event. |
| Metric labels | Không có eventId/orderId/tenantId cardinality cao. |
| Payload nhạy cảm | Log/trace không chứa secret hoặc field bị cấm. |

Có thể dùng SimpleMeterRegistry để kiểm tra metric được đăng ký trong unit test. Integration test nên xác minh log/trace context qua listener async hoặc broker thực tế khi đó là yêu cầu quan trọng. Không nên assert chính xác toàn bộ chuỗi log nếu định dạng có thể thay đổi; ưu tiên field có ý nghĩa.

## 18. Runbook khi không có quan sát

Nếu phát hiện event pipeline không có đủ tín hiệu trong lúc incident:

1. Xác định event type, producer, listener/consumer và khoảng thời gian bị ảnh hưởng.
2. Thu thập business key, event ID nếu có, correlation ID, topic/partition/offset và release version.
3. Kiểm tra transaction publisher đã commit hay rollback.
4. Tra cứu Event Publication Registry bằng API được hỗ trợ nếu có.
5. Với broker, kiểm tra consumer group, lag, retry topic và DLT.
6. Đối chiếu database, inbox/outbox và side effect nghiệp vụ.
7. Không replay hoặc resubmit khi chưa biết side effect đã commit hay chưa.
8. Tạo log/metric tạm thời có phạm vi và thời hạn nếu cần để khoanh vùng.
9. Sau khi phục hồi, bổ sung instrumentation bền vững và test cho tín hiệu còn thiếu.

Nếu không có eventId hoặc correlation ID từ trước, dùng business key và timestamp để khoanh vùng nhưng ghi rõ độ tin cậy thấp. Tránh tạo một truy vấn log quá rộng hoặc export payload nhạy cảm để bù cho thiếu metadata.

## 19. Checklist tránh anti-pattern không có quan sát

- Mỗi event có identity ổn định và metadata truy vết phù hợp.
- Publisher phân biệt publish với transaction commit và listener completion.
- Listener ghi outcome và không nuốt exception ngoài chủ đích.
- Logs có cấu trúc, eventId, eventType, listener và correlation ID.
- Metrics bao phủ volume, failure, duration, backlog, retry và DLT.
- Metric tags có cardinality thấp; không dùng business ID làm label.
- Trace context được truyền qua async thread và broker theo instrumentation.
- Event Publication Registry được quan sát qua incomplete count và age.
- Kafka/RabbitMQ có dashboard cho consumer progress và queue backlog.
- Alert gắn với SLO và business impact.
- Health check không bị xem là bằng chứng toàn bộ event flow đã hoàn tất.
- Logs, traces và health details được bảo vệ khỏi dữ liệu nhạy cảm.
- Có test cho success, failure, rollback, async context và metric labels.
- Runbook có bước điều tra, recovery và xác minh side effect.

Không có observability khiến event-driven system trở thành một chuỗi xử lý mù: publisher không biết listener có hoàn tất, consumer không biết backlog đang tăng và người vận hành không thể xác định event đang dừng ở đâu. Khi kết hợp structured logs, metrics có cardinality thấp, distributed traces, publication state và broker signals, đội phát triển có thể lần theo từng event, phát hiện suy giảm theo SLO và phục hồi dựa trên bằng chứng thay vì phỏng đoán.
