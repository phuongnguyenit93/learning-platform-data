# Correlation ID trong log

Một luồng nghiệp vụ thường đi qua nhiều module, listener bất đồng bộ và đôi khi cả message broker hoặc service bên ngoài. Khi một bước thất bại, log của từng thành phần có thể nằm ở nhiều thread, nhiều process và nhiều hệ thống. Nếu không có một định danh chung, người vận hành phải tìm theo timestamp hoặc nội dung message, rất dễ bỏ sót một bước hoặc ghép nhầm hai luồng chạy đồng thời.

Correlation ID là định danh được giữ xuyên suốt một luồng công việc để liên kết các log và event có liên quan. Trong ứng dụng Spring Modulith, correlation ID giúp theo dõi event từ module phát tới các listener nhận; khi event được chuyển qua broker, ID này tiếp tục được truyền trong metadata hoặc message header. Nó bổ sung cho trace ID, event ID và các định danh nghiệp vụ, mỗi loại có mục đích riêng.

Bài này trình bày cách tạo, xác thực, truyền và ghi correlation ID; cách kết hợp với MDC, structured logging và distributed tracing; cùng các quy tắc cần giữ khi xử lý bất đồng bộ, retry và kiểm thử.

## 1. Correlation ID giải quyết vấn đề gì?

Giả sử một yêu cầu đặt hàng đi qua các bước:

1. API nhận yêu cầu và tạo đơn hàng.
2. Module Order publish OrderPlaced.
3. Listener của Inventory giữ hàng.
4. Listener của Payment yêu cầu thanh toán.
5. Một integration adapter gửi message tới broker.
6. Consumer Shipping tạo vận đơn.

Mỗi bước có thể chạy ở thread hoặc process khác nhau. Một lỗi tại Shipping cần được liên kết ngược về yêu cầu đặt hàng ban đầu và các bước đã xảy ra trước đó.

Correlation ID cung cấp một khóa chung cho toàn bộ luồng:

~~~text
HTTP request
  correlationId = corr-8f31
       |
       v
Order module
  OrderPlaced
  correlationId = corr-8f31
       |
       +----> Inventory listener
       |        correlationId = corr-8f31
       |
       +----> Payment listener
       |        correlationId = corr-8f31
       |
       +----> AMQP message
                correlationId = corr-8f31
                       |
                       v
                 Shipping consumer
                   correlationId = corr-8f31
~~~

Khi tìm log theo corr-8f31, người vận hành có thể nhìn thấy các bước thuộc cùng một quy trình dù chúng xảy ra ở nhiều thành phần. Correlation ID hỗ trợ điều tra và đối chiếu; nó không tự bảo đảm event được giao thành công, không thay thế transaction và không ngăn xử lý trùng.

## 2. Phân biệt correlation ID với các định danh khác

Không nên dùng một ID duy nhất cho mọi mục đích. Các định danh sau có phạm vi và vòng đời khác nhau:

| Định danh | Phạm vi | Dùng để |
|---|---|---|
| correlationId | Một yêu cầu hoặc luồng nghiệp vụ | Liên kết log/event thuộc cùng luồng |
| traceId | Một distributed trace | Gom các span được tracing system ghi nhận |
| spanId | Một operation/span trong trace | Xác định một bước cụ thể trong trace |
| eventId | Một event cụ thể | Nhận diện event và deduplicate |
| causationId | Event/command gây ra event hiện tại | Truy ngược quan hệ nguyên nhân |
| sagaId | Một quy trình saga kéo dài | Tìm trạng thái và các bước của saga |
| aggregateId | Một đối tượng nghiệp vụ | Nhóm các thay đổi của cùng aggregate |
| requestId | Một lần gọi HTTP hoặc RPC | Định danh request tại một boundary |

Ví dụ, một đơn hàng có thể có:

- correlationId chung cho luồng checkout.
- sagaId cho quy trình fulfillment.
- aggregateId là orderId.
- eventId riêng cho OrderPlaced và PaymentAuthorized.
- causationId của PaymentAuthorized trỏ về command hoặc event đã kích hoạt thao tác thanh toán.
- traceId có thể bao phủ một đoạn xử lý phân tán; một tác vụ nền chạy lâu có thể bắt đầu trace mới nhưng vẫn giữ correlationId nghiệp vụ.

Correlation ID thường tồn tại lâu hơn một trace đơn lẻ. Một luồng nghiệp vụ có thể gồm nhiều request, scheduled job hoặc message đến ở các thời điểm khác nhau. Trace ID không nên được dùng thay correlation ID nếu cần liên kết cả vòng đời nghiệp vụ dài.

Correlation ID cũng không phải idempotency key. Event ID hoặc một idempotency key riêng mới được dùng để ngăn side effect lặp.

## 3. Quy tắc vòng đời correlation ID

Trước khi triển khai, thống nhất các quy tắc:

- Tạo correlation ID tại boundary đầu tiên nếu request chưa có ID hợp lệ.
- Nếu request đến từ gateway hoặc service nội bộ đáng tin cậy, có thể tiếp nhận ID đã được xác thực theo quy ước chung.
- Giữ nguyên correlation ID khi event được chuyển sang module khác hoặc được retry.
- Khi một event tạo ra event mới trong cùng luồng nghiệp vụ, event mới giữ correlation ID và đặt causationId bằng ID của event/command gây ra nó.
- Một luồng nghiệp vụ độc lập bắt đầu từ scheduler hoặc batch job cần tạo correlation ID mới.
- Không tạo correlation ID mới mỗi lần listener retry hoặc broker redeliver cùng một event.

Một quy ước metadata có thể gồm:

~~~java
public record EventMetadata(
        UUID eventId,
        String correlationId,
        String causationId
) {}

public record OrderPlaced(
        EventMetadata metadata,
        UUID orderId,
        Instant occurredAt
) {}
~~~

eventId định danh event hiện tại; correlationId liên kết cả luồng; causationId ghi lại nguyên nhân trực tiếp. Nếu không có event/command cha, causationId có thể để trống theo schema đã thống nhất.

Hãy dùng cùng tên field và cách viết nhất quán giữa JSON payload, message headers và log. Ví dụ chọn correlationId trong Java/JSON và correlation-id trong AMQP/Kafka header.

## 4. Tạo correlation ID tại HTTP boundary

Với HTTP API, filter là vị trí phù hợp để xác định correlation ID trước khi controller và service ghi log. Có thể nhận header X-Correlation-ID từ gateway hoặc tạo UUID mới nếu header thiếu hay không hợp lệ.

Không nên chấp nhận chuỗi tùy ý từ request rồi đưa thẳng vào log. Hãy giới hạn độ dài và tập ký tự để tránh log injection, dữ liệu quá lớn hoặc các giá trị gây khó truy vấn.

Ví dụ dùng OncePerRequestFilter và SLF4J MDC:

~~~java
@Component
class CorrelationIdFilter extends OncePerRequestFilter {

    static final String HEADER = "X-Correlation-ID";
    static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        String correlationId = isValid(candidate)
                ? candidate
                : UUID.randomUUID().toString();

        String previous = MDC.get(ATTRIBUTE);
        MDC.put(ATTRIBUTE, correlationId);
        request.setAttribute(ATTRIBUTE, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            restoreMdc(ATTRIBUTE, previous);
        }
    }

    private boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }

    private void restoreMdc(String key, String previous) {
        if (previous == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, previous);
        }
    }
}
~~~

Ví dụ minh họa cơ chế. Trong ứng dụng thực tế, hãy đặt filter ở vị trí phù hợp trong filter chain để các log cần thiết đều có correlation ID. Nếu hệ thống chỉ tin header từ gateway, cần xác định gateway nào được phép gửi header và loại bỏ header do client bên ngoài tự đặt trước khi gateway gắn ID tin cậy.

Có thể trả correlation ID trong response header để client cung cấp khi báo lỗi. Không dùng ID này làm bằng chứng xác thực hoặc phân quyền; biết correlation ID không được phép mở quyền truy cập log hay dữ liệu nghiệp vụ.

Nếu request header sai định dạng, tạo ID mới và có thể ghi metric đếm số header bị từ chối. Tránh log nguyên văn giá trị không hợp lệ vì nó có thể chứa dữ liệu không an toàn.

## 5. Đưa correlation ID vào application event

MDC chỉ là ngữ cảnh ghi log ở thread hiện tại. Nó không phải hợp đồng dữ liệu và không tự động đi theo event khi listener chạy bất đồng bộ hoặc process khác nhận message.

Vì vậy, event cần mang correlation ID rõ ràng trong metadata hoặc envelope. Có thể đưa metadata vào command ở application boundary rồi chuyển tiếp khi publish:

~~~java
public record PlaceOrderCommand(
        UUID customerId,
        List<OrderLine> lines,
        String correlationId,
        String causationId
) {}

@Service
@RequiredArgsConstructor
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        Order order = Order.place(
                command.customerId(),
                command.lines()
        );

        orders.save(order);

        EventMetadata metadata = new EventMetadata(
                UUID.randomUUID(),
                command.correlationId(),
                command.causationId()
        );

        events.publishEvent(new OrderPlaced(
                metadata,
                order.getId(),
                clock.instant()
        ));

        return order.getId();
    }
}
~~~

Trong ví dụ, correlation ID được truyền tường minh qua command. Với các entry point khác như scheduled job, consumer hoặc batch process, boundary tương ứng phải tạo hoặc lấy correlation ID rồi đưa vào application service.

Không nên để domain model phụ thuộc MDC hoặc đọc ThreadLocal trực tiếp. Domain/application event cần metadata rõ ràng để có thể serialize, lưu trữ, replay và kiểm thử độc lập với logging framework.

## 6. Gắn correlation ID vào MDC khi xử lý listener

MDC (Mapped Diagnostic Context) của SLF4J cho phép gắn các giá trị theo ngữ cảnh để logging framework tự thêm vào mỗi log record. Các appender có thể đưa correlationId vào JSON log hoặc pattern text.

Với listener bất đồng bộ, không giả định MDC từ thread publish sẽ tự có ở thread listener. Hãy thiết lập ngữ cảnh từ event metadata khi bắt đầu xử lý và khôi phục giá trị cũ trong finally:

~~~java
@Component
@RequiredArgsConstructor
class InventoryListener {

    private final InventoryService inventory;

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        String correlationId =
                event.metadata().correlationId();

        String previous = MDC.get("correlationId");
        if (correlationId == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }

        try {
            log.info(
                    "Processing OrderPlaced for orderId={}",
                    event.orderId()
            );

            inventory.reserveFor(event.orderId());
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
~~~

Có thể đóng gói việc set/restore MDC thành helper dùng chung trong module infrastructure. Helper phải luôn khôi phục context trước đó, kể cả khi listener ném exception. Không chỉ gọi MDC.put mà quên remove; thread pool tái sử dụng thread nên giá trị cũ có thể rò sang event tiếp theo.

MDC phục vụ logging. Nếu cần truyền correlation ID giữa các lớp, ưu tiên truyền metadata tường minh hoặc dùng context abstraction được quản lý; đừng coi MDC là nguồn dữ liệu nghiệp vụ duy nhất.

## 7. Truyền context qua executor và tác vụ bất đồng bộ

Thread pool thường tái sử dụng thread. Thread tạo task và thread chạy task có thể khác nhau; ThreadLocal/MDC không tự động được sao chép giữa chúng.

Nếu task chỉ cần MDC cho log, có thể dùng TaskDecorator để chụp context khi submit và khôi phục context của worker sau khi chạy:

~~~java
@Bean
TaskDecorator mdcTaskDecorator() {
    return task -> {
        Map<String, String> callerContext =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext =
                    MDC.getCopyOfContextMap();

            try {
                if (callerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callerContext);
                }

                task.run();
            } finally {
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    };
}
~~~

Gắn decorator vào executor thực sự được listener hoặc @Async sử dụng. Một TaskDecorator không có tác dụng nếu bean executor khác đang được chọn.

Đối với tracing và observation context, ưu tiên cơ chế context propagation của Micrometer/Spring được hỗ trợ bởi phiên bản ứng dụng. MDC decorator ở trên chỉ sao chép map logging; nó không thay thế việc truyền trace context, security context hoặc transaction context.

Với Reactor/WebFlux, tác vụ có thể chuyển thread trong quá trình reactive pipeline. Không dựa vào ThreadLocal MDC như context duy nhất; sử dụng Reactor Context và tích hợp context propagation/tracing phù hợp. Với bất kỳ mô hình bất đồng bộ nào, event hoặc message vẫn cần mang correlation ID bền vững để có thể khôi phục sau restart.

## 8. Phân biệt correlation ID và distributed tracing

Distributed tracing ghi lại đường đi của operation dưới dạng trace gồm nhiều span. Micrometer Tracing hoặc OpenTelemetry có thể tạo và truyền trace context qua HTTP, messaging và các client đã được instrument.

Correlation ID và trace ID bổ sung cho nhau:

- correlationId liên kết một luồng nghiệp vụ theo quy ước của ứng dụng.
- traceId liên kết các span trong một trace kỹ thuật.
- spanId xác định một operation cụ thể.
- causationId thể hiện quan hệ nguyên nhân ở mức event/command.

Một saga kéo dài nhiều giờ có thể đi qua nhiều trace riêng. Correlation ID nghiệp vụ vẫn giữ nguyên để tìm toàn bộ saga; tracing có thể bắt đầu trace mới cho mỗi lần xử lý và dùng span link nếu instrumentation hỗ trợ liên kết các trace có quan hệ.

Không tự tạo hoặc ghi đè traceId bằng correlationId. Không đặt traceId vào header traceparent theo cách thủ công nếu Micrometer/OpenTelemetry đã quản lý W3C Trace Context. Hãy để tracing instrumentation tạo span và inject/extract trace context.

Nếu cần tra cứu, log có thể chứa cả correlationId và traceId. Người vận hành dùng correlationId để tìm toàn bộ luồng nghiệp vụ, rồi dùng traceId để mở trace chi tiết của một đoạn xử lý.

## 9. Truyền correlation ID qua message broker

Khi event được externalize sang RabbitMQ, Kafka hoặc broker khác, correlation ID phải đi cùng message. Không dựa vào MDC của relay vì relay có thể chạy ở thread riêng hoặc process riêng.

### 9.1. RabbitMQ / Spring AMQP

Spring AMQP cung cấp message properties để mang correlation ID và message ID:

~~~java
rabbitTemplate.convertAndSend(
        "business.events",
        "order.placed",
        integrationEvent,
        message -> {
            MessageProperties properties =
                    message.getMessageProperties();

            properties.setMessageId(
                    integrationEvent.eventId().toString()
            );
            properties.setCorrelationId(
                    integrationEvent.correlationId()
            );
            properties.setHeader(
                    "causationId",
                    integrationEvent.causationId()
            );

            return message;
        }
);
~~~

Ở phía consumer, đọc correlation ID từ message metadata hoặc envelope, kiểm tra hai nguồn có nhất quán theo contract, rồi đưa ID vào MDC trong thời gian xử lý. Nếu payload và header mâu thuẫn, ghi nhận lỗi contract và áp dụng chính sách rõ ràng; không tùy tiện chọn một giá trị mà không có quy ước.

### 9.2. Kafka headers

Với Kafka, producer có thể đưa correlation ID vào record header:

~~~java
ProducerRecord<String, OrderPlacedIntegrationV1> record =
        new ProducerRecord<>(
                "order-events",
                event.orderId().toString(),
                event
        );

record.headers().add(
        "correlation-id",
        event.correlationId().getBytes(StandardCharsets.UTF_8)
);

record.headers().add(
        "event-id",
        event.eventId().toString().getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Consumer đọc header, xác minh định dạng và thiết lập log context. Nếu dùng Spring Kafka, có thể viết interceptor hoặc listener adapter để chuẩn hóa việc extract context thay vì lặp logic trong từng listener.

### 9.3. Header trace context

Correlation ID là metadata của ứng dụng. Trace context như traceparent và tracestate theo chuẩn W3C và thường được tracing instrumentation tự động inject/extract. Giữ hai nhóm header tách biệt và không dùng correlation-id để thay traceparent.

## 10. Giữ ID nhất quán khi retry, replay và compensation

Một số quy tắc cần giữ để log không bị chia thành nhiều luồng giả:

| Tình huống | correlationId | eventId | causationId |
|---|---|---|---|
| Retry cùng một event | Giữ nguyên | Giữ nguyên | Giữ nguyên |
| Broker redeliver message | Giữ nguyên | Giữ nguyên | Giữ nguyên |
| Event mới được tạo bởi event hiện tại | Giữ nguyên trong cùng workflow | Tạo mới | ID event/command gây ra |
| Saga phát compensation | Giữ nguyên saga correlation | ID mới cho compensation event/command | ID của bước thất bại hoặc yêu cầu bù |
| Scheduled job độc lập | Tạo mới | ID mới cho từng event | Có thể để trống hoặc dùng job execution ID |
| Replay lịch sử | Theo correlation gốc hoặc replay correlation riêng theo policy | Giữ event ID gốc nếu replay cùng event | Giữ quan hệ nguyên nhân gốc; ghi replayId riêng |

Replay cần quyết định rõ mục đích. Nếu replay chỉ là giao lại cùng event, giữ eventId và correlationId gốc để dedupe hoạt động đúng. Nếu tạo một lần chạy phục hồi độc lập, có thể thêm replayId hoặc recoveryRunId mới để phân biệt lần vận hành mà vẫn giữ originalCorrelationId để truy ngược luồng gốc. Không ghi đè eventId gốc.

Một event compensation là event mới vì nó mô tả một kết quả hoặc hành động mới. Nó dùng correlationId của saga và causationId trỏ về bước dẫn tới compensation.

## 11. Structured logging

Correlation ID hữu ích nhất khi log có cấu trúc và field nhất quán. Một log JSON có thể trông như sau:

~~~json
{
  "timestamp": "2026-11-25T14:10:15.123Z",
  "level": "INFO",
  "service": "inventory-service",
  "logger": "InventoryListener",
  "message": "Inventory reservation completed",
  "correlationId": "corr-8f31",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "eventId": "evt-102",
  "causationId": "evt-101",
  "sagaId": "saga-77",
  "aggregateId": "order-42"
}
~~~

Các field nên có quy ước tên thống nhất giữa service. Không ghi correlation ID chỉ trong message text như "Handling corr-8f31"; hãy ghi thành field riêng để log platform có thể filter và aggregate.

Ví dụ với Logback pattern text, có thể thêm MDC key:

~~~text
%date %-5level [%thread] correlationId=%X{correlationId} traceId=%X{traceId} %logger - %msg%n
~~~

Nếu dùng JSON encoder, cấu hình encoder để đưa MDC map vào JSON field. Không cần lặp correlation ID trong mọi message text nếu nó đã có field riêng.

## 12. Bảo mật và quyền riêng tư

Correlation ID thường không phải secret, nhưng vẫn là dữ liệu đầu vào có thể bị lạm dụng nếu chấp nhận tùy ý.

Các nguyên tắc:

- Giới hạn độ dài và tập ký tự.
- Không cho phép CR/LF hoặc ký tự điều khiển có thể giả mạo dòng log.
- Không dùng correlation ID để xác thực, phân quyền hoặc truy cập log.
- Không nhúng email, số điện thoại, token hoặc dữ liệu cá nhân vào ID.
- Không ghi toàn bộ header hoặc payload nhạy cảm khi debug.
- Xác định boundary nào được phép cung cấp ID tin cậy.
- Nếu cần public response header, không tiết lộ thông tin nội bộ qua định dạng ID.

Correlation ID do client tự gửi có thể được cố tình lặp lại để gây khó điều tra hoặc gom log của nhiều request không liên quan. Gateway có thể thay thế ID bên ngoài bằng ID do hệ thống tạo và giữ ID gốc trong một field riêng đã được sanitize nếu thực sự cần đối chiếu.

Không dùng correlation ID làm label của metric Prometheus hoặc metric time-series có cardinality cao. Dùng ID trong log/trace; metric chỉ nên dùng các label có tập giá trị giới hạn như service, eventType, outcome hoặc consumer.

## 13. Kiểm thử correlation context

Kiểm thử cần xác minh ID được tạo đúng, truyền đúng và được dọn sạch sau khi xử lý.

| Kịch bản | Điều cần xác minh |
|---|---|
| HTTP request không có header | Filter tạo ID mới và trả trong response header |
| HTTP request có ID hợp lệ | ID được giữ theo trust policy |
| Header chứa ký tự điều khiển hoặc quá dài | ID bị từ chối và tạo ID mới |
| Request kết thúc thành công hoặc exception | MDC được khôi phục/dọn sạch |
| Event được publish | Correlation ID có trong event metadata |
| Listener bất đồng bộ | Log listener có correlation ID của event |
| Hai task chạy trên cùng thread pool | Context task trước không rò sang task sau |
| AMQP/Kafka publish | Message header có correlation ID và event ID |
| Consumer nhận message | Header được extract và đưa vào log context |
| Retry/redelivery | correlationId và eventId giữ nguyên |
| Event con/compensation | correlationId giữ nguyên, eventId mới và causationId đúng |
| Scheduled job độc lập | Tạo correlation ID mới |
| Reactive pipeline | Context được truyền qua Reactor Context/tracing integration |

Test TaskDecorator nên kiểm tra cả hai chiều: task nhận đúng MDC snapshot và worker thread được trả về context cũ sau khi task kết thúc, kể cả khi task ném exception.

Với integration test broker, kiểm tra message header thực tế thay vì chỉ mock phương thức send. Với listener async, dùng Awaitility hoặc latch có timeout thay vì sleep cố định.

## 14. Chẩn đoán một luồng event bằng correlation ID

Khi một yêu cầu nghiệp vụ thất bại, quy trình điều tra có thể là:

1. Lấy correlation ID từ response header, log API gateway hoặc thông tin người dùng cung cấp.
2. Tìm toàn bộ log theo correlationId trong log platform.
3. Xác định eventId, sagaId và aggregateId liên quan.
4. Dùng traceId để mở distributed trace của đoạn xử lý có latency hoặc exception.
5. Tìm publication chưa hoàn tất, outbox record hoặc message DLQ bằng eventId.
6. Đối chiếu causationId để xác định event/command nào tạo ra bước lỗi.
7. Kiểm tra trạng thái nghiệp vụ trước khi retry hoặc replay.
8. Ghi nhận kết quả xử lý và correlation ID trong incident/ticket.

Correlation ID giúp liên kết log nhưng không bảo đảm mọi hệ thống đều ghi log. Nếu một adapter không truyền metadata hoặc một listener không thêm MDC, luồng log sẽ bị đứt. Vì vậy nên theo dõi metric tỷ lệ log/event có correlation ID và kiểm tra các boundary quan trọng.

Khi tìm theo correlation ID, cần tính tới thời gian retention của log và dữ liệu archive. Một saga kéo dài nhiều ngày có thể vượt retention của log nóng; hãy lưu audit/event metadata ở nguồn bền vững nếu nghiệp vụ yêu cầu truy vết dài hạn.

## 15. Lỗi thường gặp

**Dùng traceId làm correlationId cho mọi thứ.** Một workflow dài có thể qua nhiều trace. Giữ correlation ID nghiệp vụ ổn định và dùng trace ID cho từng distributed trace.

**Chỉ đặt ID trong MDC.** MDC không tự đi qua thread, broker hoặc process. Đưa correlation ID vào event/message metadata.

**Không dọn MDC.** Thread pool tái sử dụng thread có thể làm log của request sau mang ID của request trước. Luôn restore trong finally.

**Tạo ID mới khi retry.** Log bị chia thành nhiều luồng và dedupe/đối chiếu khó hơn. Retry cùng event phải giữ event ID và correlation ID.

**Dùng correlation ID làm event ID.** Một workflow có nhiều event; cần eventId riêng cho từng event.

**Không có causation ID.** Correlation ID cho biết các bước cùng luồng nhưng không cho biết bước nào gây ra bước nào. Dùng causationId để lưu quan hệ nguyên nhân trực tiếp.

**Tin mọi giá trị header từ bên ngoài.** Header không hợp lệ có thể làm log injection hoặc gây khó điều tra. Validate, giới hạn độ dài và xác định trust boundary.

**Đưa ID vào metric label.** Mỗi request tạo một giá trị mới làm cardinality tăng không kiểm soát. Dùng ID trong log/trace và label có tập giá trị giới hạn cho metric.

**Tạo một trace xuyên suốt quy trình kéo dài bằng cách tự ghi đè traceparent.** Hãy để tracing instrumentation quản lý trace context và dùng correlationId để liên kết nghiệp vụ.

## 16. Quy trình triển khai correlation ID

Khi thêm correlation ID vào một luồng Spring Modulith, có thể thực hiện theo thứ tự:

1. Chọn tên field/header thống nhất và quy tắc tạo ID.
2. Tạo hoặc xác thực ID tại HTTP, message hoặc scheduler boundary.
3. Đưa ID vào command/event metadata một cách tường minh.
4. Thiết lập MDC ở mỗi listener/consumer và khôi phục context trong finally.
5. Cấu hình executor/context propagation cho tác vụ bất đồng bộ.
6. Truyền ID trong AMQP/Kafka headers khi externalize event.
7. Bật structured logging với correlationId, eventId, causationId và traceId.
8. Giữ ID ổn định qua retry/redelivery; tạo eventId mới cho event mới.
9. Kiểm thử propagation, cleanup, duplicate và context leakage.
10. Tạo dashboard/truy vấn log và runbook điều tra theo correlationId.

Trong Spring Modulith, correlation ID là metadata của luồng nghiệp vụ đi cùng application event, còn MDC chỉ là cách đưa metadata đó vào log của thread hiện tại. Khi kết hợp ID ổn định, event metadata tường minh, context propagation đúng và structured logging, các module và consumer có thể được truy vết xuyên suốt mà không nhầm correlation với tracing, idempotency hoặc định danh aggregate.
