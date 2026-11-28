# Che thông tin event và payload nhạy cảm

## 1. Vì sao payload event cần được bảo vệ?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, các application module có thể giao tiếp bằng application event. Ví dụ, module ordering phát sự kiện `OrderPlaced`, module payment tiếp tục xử lý thanh toán và module notification gửi thông báo. Event giúp các module giảm phụ thuộc trực tiếp, nhưng payload của event có thể đi qua nhiều thành phần hơn một lời gọi method thông thường.

Một event có thể được nhiều listener đọc, được xử lý bất đồng bộ, được ghi nhận trong publication registry, được externalize sang broker hoặc được đưa vào log và trace nếu developer ghi toàn bộ object để debug. Nếu payload chứa tên, email, địa chỉ, thông tin tài khoản, access token hoặc dữ liệu thanh toán, mỗi bản sao có thể mở rộng phạm vi truy cập và thời gian lưu trữ.

Rủi ro không chỉ nằm ở việc một listener có quyền đọc event. Dữ liệu có thể bị sao chép sang:

- Log ứng dụng, log agent và hệ thống tìm kiếm.
- Span attributes, span events, baggage và tracing backend.
- Exception message, dead-letter record và retry metadata.
- Cơ sở dữ liệu lưu publication state hoặc event payload.
- Message broker, queue, backup và bản export phục vụ phân tích.
- Dashboard, alert notification, ticket và ảnh chụp màn hình hỗ trợ.

**Che dữ liệu nhạy cảm phải bắt đầu từ lúc thiết kế payload và instrumentation.** Redaction tại collector hoặc log backend chỉ là lớp phòng vệ bổ sung; nếu dữ liệu thô đã được ghi ra nguồn thì bản sao đó có thể đã rời khỏi vùng kiểm soát.

Bài học thuộc chương **Bảo mật** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot, bao gồm module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện dữ liệu nhạy cảm trong event payload và telemetry.
2. Thiết kế event DTO chỉ chứa dữ liệu tối thiểu cần cho listener.
3. Tránh ghi payload, token và exception chứa dữ liệu cá nhân vào logs/traces.
4. Dùng allowlist, masking, tokenization hoặc mã hóa đúng vị trí.
5. Kiểm soát dữ liệu đi qua MDC, trace attributes, baggage và metric tags.
6. Đánh giá rủi ro khi event được persist hoặc externalize.
7. Thiết lập quyền truy cập, retention và quy trình xử lý dữ liệu.
8. Viết test phát hiện rò rỉ dữ liệu qua log, span, metric, database và broker.

## 2. Phân loại dữ liệu trước khi tạo event

Trước khi định nghĩa event, hãy xác định payload chứa loại dữ liệu nào và listener nào thực sự cần chúng.

| Nhóm dữ liệu | Ví dụ | Cách xử lý mặc định |
| --- | --- | --- |
| Bí mật xác thực | Password, access token, refresh token, API key, private key, session cookie. | Không đưa vào event hoặc telemetry. Truyền credential qua secret manager hoặc cơ chế xác thực riêng. |
| Dữ liệu cá nhân | Họ tên, email, số điện thoại, địa chỉ, ngày sinh, mã định danh. | Chỉ dùng khi có mục đích nghiệp vụ rõ; ưu tiên reference/token và hạn chế người nhận. |
| Dữ liệu thanh toán | PAN, CVV, tài khoản ngân hàng, payment credential. | Không phát dữ liệu thẻ nhạy cảm; dùng token từ payment provider và tuân thủ chính sách thanh toán. |
| Dữ liệu nghiệp vụ nhạy cảm | Giá trị đơn hàng, hạn mức, hợp đồng, thông tin nội bộ. | Phân loại theo mức độ nhạy cảm, giới hạn listener và thời gian lưu. |
| Dữ liệu kỹ thuật | Trace ID, span ID, module identifier, event type. | Thường phù hợp cho correlation nếu không chứa định danh người dùng; vẫn cần kiểm soát access và retention. |

Không phải mọi mã định danh đều vô hại. Customer ID, order ID hoặc IP address có thể liên kết tới một cá nhân khi kết hợp với dữ liệu khác. Hash một email hoặc số điện thoại cũng không tự động biến dữ liệu thành vô danh, nhất là khi miền giá trị có thể đoán được.

### 2.1. Áp dụng nguyên tắc data minimization

Với mỗi field, đặt câu hỏi:

- Listener nào cần field này?
- Listener cần giá trị đầy đủ hay chỉ cần biết có/không, loại hoặc trạng thái?
- Có thể dùng opaque reference thay cho dữ liệu gốc không?
- Field có cần tồn tại sau khi listener hoàn tất không?
- Field có bị log, serialize, retry hoặc gửi sang broker không?
- Ai có quyền đọc bản lưu và trong bao lâu?

Ví dụ, listener notification có thể chỉ cần `orderReference` và `notificationType`. Nó thường không cần password, access token, số thẻ hay toàn bộ địa chỉ thanh toán. Nếu cần email để gửi thông báo, hãy lấy dữ liệu qua một service có kiểm tra quyền truy cập tại thời điểm xử lý, hoặc dùng một delivery destination đã được quản lý riêng theo chính sách.

### 2.2. Event payload là một bản sao dữ liệu

Một khi dữ liệu được đặt vào event, nó có thể sống lâu hơn request đã tạo ra nó. Listener async có thể xử lý sau vài giây hoặc vài giờ; retry có thể giữ publication chưa hoàn tất; broker có thể giữ message theo retention policy. Vì vậy, không coi event là object tạm thời chỉ vì nó được publish trong cùng JVM.

Nếu event phải mang snapshot để bảo đảm semantics tại thời điểm phát, chỉ đưa vào những facts cần thiết. Khi snapshot có field nhạy cảm, cần xác định rõ nơi lưu, mã hóa, quyền đọc và thời điểm xóa. Không thay snapshot bằng lookup hiện tại nếu điều đó làm sai ý nghĩa nghiệp vụ của event.

## 3. Thiết kế event an toàn

### 3.1. Ưu tiên event DTO tối thiểu

Ví dụ event chỉ mang reference và dữ liệu nghiệp vụ cần thiết:

~~~java
public record OrderPlaced(
    UUID eventId,
    String orderReference,
    Instant occurredAt,
    String salesChannel
) {}
~~~

`orderReference` cần là mã opaque không tiết lộ thông tin cá nhân và không thể suy ra trực tiếp từ email/số điện thoại. `salesChannel` phải thuộc tập giá trị giới hạn. Nếu listener cần thêm thông tin, nó dùng `orderReference` để gọi application service có kiểm soát quyền.

Ví dụ publisher:

~~~java
public class OrderApplicationService {

    private final ApplicationEventPublisher events;

    public OrderApplicationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(Order order) {
        // Persist order và hoàn tất các bước nghiệp vụ cần thiết.
        events.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.publicReference(),
            Instant.now(),
            order.salesChannel().name()
        ));
    }
}
~~~

Ví dụ chỉ minh họa cấu trúc; thời gian nên được cung cấp qua `Clock` để dễ kiểm thử. Không đưa entity JPA đầy đủ vào event vì entity có thể chứa quan hệ, lazy fields, credential hoặc dữ liệu không dành cho consumer.

### 3.2. Không publish entity hoặc request object nguyên trạng

Tránh các kiểu payload:

~~~java
// Không nên: entity có thể chứa nhiều field nhạy cảm và quan hệ.
events.publishEvent(orderEntity);

// Không nên: request có thể mang token, địa chỉ và thông tin thanh toán.
events.publishEvent(new OrderCreatedEvent(httpRequest));
~~~

Tạo event DTO tường minh giúp reviewer thấy chính xác dữ liệu nào rời module. Nếu cần serialize, schema của DTO trở thành một phần contract cần được review.

### 3.3. Tránh đưa secret vào event rồi trông chờ @JsonIgnore

`@JsonIgnore` có thể ảnh hưởng Jackson serialization trong một số cấu hình, nhưng không bảo vệ mọi đường đi. Java record `toString()`, logger, serializer khác, reflection, debugger hoặc custom mapper vẫn có thể làm lộ field. Annotation không thay thế việc loại bỏ dữ liệu khỏi payload.

Nếu một secret không cần cho consumer, không đưa nó vào event. Nếu nghiệp vụ bắt buộc truyền một credential, hãy xem đó là một luồng secret riêng với encryption, access control, expiry và audit; không coi event bus là secret manager.

## 4. Bảo vệ listener và ranh giới module

Spring Modulith giúp tổ chức application module và event listener theo ranh giới rõ ràng. Tuy nhiên, ranh giới module không tự động là ranh giới bảo mật. Mọi listener nhận event cần được xem như một consumer có quyền đọc payload.

### 4.1. Kiểm tra nhu cầu dữ liệu của từng listener

Ví dụ:

| Listener | Dữ liệu tối thiểu | Không nên nhận |
| --- | --- | --- |
| Inventory listener | Order reference, item references, quantities cần giữ chỗ. | Customer password, payment token, full profile. |
| Notification listener | Order reference, notification type hoặc destination reference. | Payment credential, toàn bộ entity order. |
| Reporting listener | Event type, timestamp, dimension đã được phê duyệt. | Raw email, address hoặc payload không cần thiết. |
| Payment listener | Order reference, amount/currency nếu cần, payment intent reference. | Password, session cookie, CVV. |

### 4.2. Ví dụ listener dùng application service

~~~java
@Component
class OrderNotificationListener {

    private final OrderQueryService orders;
    private final NotificationSender sender;

    OrderNotificationListener(
            OrderQueryService orders,
            NotificationSender sender) {
        this.orders = orders;
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        var notification = orders.createNotificationFor(
            event.orderReference()
        );
        sender.send(notification);
    }
}
~~~

Trong ví dụ, listener không cần nhận trực tiếp email hoặc địa chỉ từ event. `OrderQueryService` chịu trách nhiệm kiểm tra quyền và trả về projection tối thiểu. Nếu listener chạy bất đồng bộ, cần xác định quyền được đánh giá ở thời điểm publish hay thời điểm consume; đây là quyết định nghiệp vụ và bảo mật cần ghi tài liệu.

### 4.3. Không coi mọi module trong cùng ứng dụng đều đáng tin như nhau

Một module có thể bị lỗi hoặc bị khai thác. Giới hạn dữ liệu theo nguyên tắc least privilege:

- Chỉ expose event cần thiết cho consumer.
- Không dùng event chung chứa toàn bộ customer/order profile cho mọi module.
- Tách event theo mục đích và quyền dữ liệu.
- Giữ application service/API module làm điểm kiểm tra quyền truy cập.
- Review listener mới như một thay đổi về data access.

Module graph giúp nhận diện dependency, nhưng không thay thế access-control review. Khi một module mới subscribe event, hãy kiểm tra xem dữ liệu trong event có vượt quá nhu cầu của module đó không.

## 5. Không ghi event payload vào log

Log thường là nơi rò rỉ dữ liệu nhanh nhất vì developer có thể thêm một dòng debug trong lúc xử lý sự cố.

### 5.1. Tránh log toàn bộ event hoặc entity

Không nên:

~~~java
log.info("Received event: {}", event);
log.debug("Order payload: {}", objectMapper.writeValueAsString(event));
log.error("Failed to process event " + event, exception);
~~~

Record Java tự sinh `toString()` có thể in tất cả component. JSON serialization cũng có thể đưa field nhạy cảm vào log. Exception message đôi khi chứa URL, query parameter, request body hoặc thông tin do upstream trả về.

Nên log một allowlist metadata:

~~~java
log.info(
    "Order event received: eventType={}, orderReference={}, module={}",
    "OrderPlaced",
    event.orderReference(),
    "notification"
);
~~~

Chỉ log `orderReference` nếu đây là reference opaque đã được phê duyệt cho log search. Nếu reference vẫn có thể liên kết tới một cá nhân, cần giới hạn quyền và retention hoặc dùng correlation key riêng.

### 5.2. Structured logging theo allowlist

Với structured logging, tạo object log riêng chỉ gồm field được phép:

~~~java
Map<String, Object> fields = Map.of(
    "event.name", "OrderPlaced",
    "module.name", "notification",
    "order.reference", event.orderReference()
);

log.atInfo()
    .addKeyValue("event.name", fields.get("event.name"))
    .addKeyValue("module.name", fields.get("module.name"))
    .addKeyValue("order.reference", fields.get("order.reference"))
    .log("Application event received");
~~~

Đây là ví dụ dùng structured logging API của SLF4J phiên bản hỗ trợ fluent logging. Nếu logger hoặc encoder không hỗ trợ, dùng DTO log-safe và encoder tương ứng. Không serialize event gốc rồi cố xóa một vài field sau đó.

### 5.3. Masking là lớp phòng vệ bổ sung

Nếu hệ thống bắt buộc nhận log record có thể chứa dữ liệu nhạy cảm, có thể bổ sung masking tại logging encoder, appender hoặc collector. Ví dụ:

- Mask email thành dạng rút gọn chỉ để hỗ trợ nhận diện.
- Chỉ giữ bốn chữ số cuối của một định danh nếu chính sách cho phép.
- Loại bỏ header `Authorization`, cookie và query parameter nhạy cảm.
- Thay payload bằng kích thước, content type hoặc checksum không thể đảo ngược theo threat model.

Masking bằng regex trên chuỗi log dễ bỏ sót JSON lồng nhau, encoding khác nhau, tên field mới hoặc dữ liệu đã escape. Ưu tiên structured logging với allowlist ở nguồn; kiểm thử masking trên nhiều dạng payload và lỗi.

### 5.4. Exception message cũng là dữ liệu đầu vào không tin cậy

Không log nguyên exception message nếu nó có thể chứa dữ liệu từ request hoặc upstream. Có thể ghi exception class, error code đã chuẩn hóa, module và trace ID; giữ stack trace theo chính sách truy cập. Khi cần chi tiết nhạy cảm để hỗ trợ, dùng kho sự cố có quyền hạn chế và thời gian lưu ngắn, không phát tán vào log chung.

## 6. Bảo vệ traces, span attributes và baggage

Tracing thường được chia sẻ rộng giữa developer, SRE và nhiều service. Một span attribute có thể được index và truy vấn lâu dài, nên không đưa payload nghiệp vụ vào span chỉ để tiện debug.

### 6.1. Chỉ thêm attributes có ích và được phê duyệt

Ví dụ attributes phù hợp:

- `module.identifier=payment`
- `module.invocation-type=BEAN`
- `event.type=OrderPlaced`
- `payment.outcome=DECLINED`
- `service.name=shop-service`

Các giá trị trên cần tuân theo taxonomy có giới hạn và không tiết lộ lý do nhạy cảm. Không gắn:

- Full event JSON hoặc request/response body.
- Access token, cookie, API key, password.
- Email, số điện thoại, địa chỉ hoặc payment credential.
- Query SQL chứa dữ liệu khách hàng.
- Exception message thô có thể chứa payload.

### 6.2. Ví dụ tạo span an toàn

~~~java
Span span = tracer.nextSpan().name("order.notification").start();
try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    span.tag("module.identifier", "notification");
    span.tag("event.type", "OrderPlaced");
    span.tag("notification.outcome", "accepted");

    notificationService.sendFor(event.orderReference());
} catch (RuntimeException exception) {
    span.error(exception);
    throw exception;
} finally {
    span.end();
}
~~~

Ví dụ sử dụng API của Micrometer Tracing. Hãy kiểm tra bridge và convention của phiên bản đang dùng; `span.error(exception)` có thể ghi exception message/stack tùy implementation. Nếu exception chứa dữ liệu nhạy cảm, cần xử lý ở nguồn hoặc cấu hình exception recording phù hợp, không chỉ dựa vào tag tự tạo.

### 6.3. Baggage có thể lan qua nhiều service

Baggage được thiết kế để truyền context qua ranh giới service. Vì vậy, một field nhạy cảm được đưa vào baggage có thể lan sang downstream service và instrumentation khác.

Chỉ cho phép các baggage key có mục đích rõ, giá trị không nhạy cảm và kích thước nhỏ. Không truyền email, token, customer profile hoặc payment data qua baggage. Nếu cần correlation, dùng trace ID hoặc một opaque correlation key có chính sách truy cập phù hợp.

### 6.4. Kiểm soát span events và exception recording

Span event cũng có thể chứa attributes và payload. Không gọi `recordException` một cách máy móc nếu exception message có thể chứa dữ liệu nhạy cảm. Đánh giá:

- Có cần lưu exception message không?
- Có thể ghi error code đã chuẩn hóa thay thế không?
- Stack trace có thể tiết lộ SQL, path hoặc input không?
- Ai có quyền đọc trace và retention bao lâu?

Sampling không phải biện pháp bảo mật. Trace bị sampling loại ở một lần chạy khác vẫn có thể được ghi ở lần tiếp theo; dữ liệu nhạy cảm phải được loại bỏ trước khi tạo/export span.

## 7. Không đưa dữ liệu nhạy cảm vào metric tags

Metrics thường được giữ lâu, được aggregate và được nhiều dashboard truy vấn. Metric labels có cardinality cao vừa tăng chi phí vừa làm lộ dữ liệu.

### 7.1. Tag an toàn có miền giá trị nhỏ

Ví dụ:

~~~java
Counter.builder("shop.module.event.processed")
    .description("Number of processed application events")
    .tag("module", "notification")
    .tag("event_type", "OrderPlaced")
    .tag("outcome", "success")
    .register(meterRegistry)
    .increment();
~~~

Các tag `module`, `event_type` và `outcome` cần lấy từ danh sách có kiểm soát. Không dùng giá trị do người dùng nhập trực tiếp nếu nó có thể tạo vô số series.

### 7.2. Không dùng các giá trị sau làm metric label

- `email`, `phone`, `customer_id`, `order_id`.
- `trace_id`, `span_id`, session ID.
- Access token, API key, cookie hoặc authorization header.
- Raw URL, query string hoặc exception message.
- Nội dung event, tên file tùy ý hoặc giá trị nhập tự do.

Một giá trị đã hash vẫn có thể tạo cardinality rất cao và có thể bị dò ngược nếu miền đầu vào nhỏ. Hash không biến customer ID thành label an toàn.

### 7.3. Giới hạn dimension cho event metrics

Spring Modulith event metrics thường dùng module và event type làm chiều quan sát. Nếu tùy biến tag cho per-event counter, chỉ thêm dimension có tập giá trị nhỏ như channel hoặc outcome đã chuẩn hóa. Không thêm `customerId`, `orderReference` hoặc payload field.

Metrics chỉ cần trả lời câu hỏi tổng hợp: event nào tăng, module nào phát nhiều, outcome nào lỗi. Để điều tra một event cụ thể, dùng trace/log với quyền kiểm soát thích hợp.

### 7.4. Kiểm tra cardinality trước khi phát hành

Đánh giá số tổ hợp tag tối đa. Ví dụ 8 module × 6 event type × 4 outcome = 192 series cho một metric. Thêm 100.000 customer ID có thể đẩy số tổ hợp lý thuyết lên hàng chục triệu. Đây là lý do không đưa ID duy nhất vào metric labels, ngay cả khi nó không phải PII trực tiếp.

## 8. Event publication persistence và externalization

Spring Modulith event flow có thể đi qua nhiều cơ chế lưu trữ và truyền tải. Hãy xem mỗi nơi là một data store hoặc data processor có trách nhiệm bảo vệ payload.

### 8.1. Event Publication Registry

Event Publication Registry theo dõi publication tới transactional listeners và trạng thái xử lý theo cấu hình. Khi dùng implementation có persistence, cần kiểm tra chính xác dữ liệu publication nào được lưu, serializer nào được sử dụng, thời gian giữ bản ghi và ai có quyền truy cập database.

Không giả định mọi cấu hình Spring Modulith đều lưu nguyên event payload theo cùng một cách. Hành vi phụ thuộc phiên bản, registry implementation và serializer. Hãy kiểm tra schema/database thực tế của dự án và xác định liệu serialized event có chứa field nhạy cảm hay không.

Nếu payload được lưu:

- Giới hạn quyền đọc database và bảng publication.
- Mã hóa storage/backup theo chính sách.
- Không ghi payload ra SQL logs hoặc debug logs.
- Xác định retention và quy trình cleanup publication đã hoàn tất.
- Xác định cách xử lý bản ghi lỗi, retry và dead-letter.

### 8.2. Event externalization và message broker

Nếu event được externalize sang Kafka, RabbitMQ hoặc broker khác, payload trở thành dữ liệu truyền qua ranh giới process. Cần:

- Chỉ externalize event được phép chia sẻ.
- Dùng schema/DTO có allowlist field.
- Bật TLS và xác thực producer/consumer.
- Áp dụng ACL theo topic/queue và consumer group.
- Mã hóa field nhạy cảm ở cấp payload nếu threat model yêu cầu.
- Kiểm soát retention, replay, dead-letter queue và backup.
- Không ghi raw message vào broker client logs.

Mã hóa đường truyền không ngăn consumer được cấp quyền đọc payload; ACL không ngăn một consumer hợp lệ ghi payload vào log. Cần kết hợp minimization, authorization và kiểm soát downstream.

### 8.3. Retry và dead-letter có thể kéo dài thời gian lưu

Một event lỗi có thể bị retry nhiều lần hoặc được chuyển vào dead-letter queue. Hãy tính cả các bản sao này trong data inventory. Khi sửa/xóa dữ liệu theo yêu cầu retention hoặc privacy, cần xác định cách xử lý message đã retry, dead-letter, backup và replay archive.

### 8.4. Event metrics không cần payload

Event publication metrics có thể theo dõi module và event type mà không cần lưu business payload. Không thêm raw event content vào metric tag hoặc custom metric description. Nếu cần đo outcome listener, phát counter với outcome đã chuẩn hóa và cardinality thấp.

## 9. Masking, pseudonymization và encryption

Ba kỹ thuật này giải quyết các mục tiêu khác nhau. Không dùng chúng thay thế cho data minimization.

| Kỹ thuật | Mục tiêu | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| Masking | Che một phần giá trị khi hiển thị. | Hiển thị email ở dạng rút gọn hoặc chỉ bốn số cuối. | Giá trị gốc vẫn có thể tồn tại ở nguồn; phần còn lại vẫn có thể nhận diện. |
| Pseudonymization/tokenization | Thay định danh trực tiếp bằng reference khác. | Customer reference ngẫu nhiên hoặc token do vault quản lý. | Có thể liên kết lại nếu có mapping; vẫn cần bảo vệ như dữ liệu có khả năng nhận diện. |
| Hash/HMAC | Tạo giá trị dẫn xuất để so khớp/correlation. | HMAC một identifier với secret key được quản lý riêng. | Hash thường có thể bị dò nếu input dễ đoán; HMAC vẫn là pseudonymous data và key phải được bảo vệ. |
| Encryption | Bảo vệ confidentiality khi lưu/truyền. | Mã hóa field payload trước khi persist. | Consumer có key vẫn đọc được; key management và authorization vẫn cần thiết. |

### 9.1. Masking ở nguồn

Nếu một field không cần cho consumer, loại bỏ field khỏi event. Nếu chỉ cần hiển thị một phần, tạo một projection đã mask trước khi log hoặc đưa vào giao diện hỗ trợ. Đừng dựa vào masking ở Grafana hoặc log UI vì dữ liệu gốc có thể vẫn được truy vấn qua API hoặc export.

Ví dụ hàm mask email chỉ nên được dùng khi policy cho phép hiển thị một phần:

~~~java
String masked = emailMasker.mask(customerEmail);
log.info("Notification destination selected: {}", masked);
~~~

Không tự viết regex mask đơn giản rồi coi đó là kiểm soát privacy hoàn chỉnh. Dùng thư viện/policy đã được review, test Unicode, email format, dữ liệu lỗi và trường hợp null.

### 9.2. Pseudonymization cho correlation

Nếu cần liên kết nhiều record của cùng một customer mà không lưu email trực tiếp, có thể dùng reference ngẫu nhiên hoặc HMAC có key:

~~~java
String correlationKey = hmacService.sign(customerId);
~~~

Giá trị này vẫn có thể liên kết các hoạt động của cùng người dùng và có thể là dữ liệu cá nhân giả danh theo chính sách áp dụng. Giới hạn nơi được dùng, thời gian lưu và quyền truy cập. Không dùng plain SHA-256 trên email/phone làm “ẩn danh”; attacker có thể thử từ điển các giá trị phổ biến.

### 9.3. Encryption cho payload thật sự cần thiết

Nếu event phải chứa dữ liệu nhạy cảm vì consumer cần snapshot chính xác, cân nhắc mã hóa field hoặc payload trước khi persist/transport:

- Dùng envelope encryption hoặc dịch vụ quản lý khóa phù hợp.
- Lưu key encryption material tách khỏi database/broker chứa ciphertext.
- Xác định consumer nào được phép decrypt.
- Hỗ trợ key rotation và version metadata.
- Không ghi plaintext trước hoặc sau bước encrypt vào log/trace.
- Có kế hoạch xử lý replay, backup và key revocation.

Mã hóa toàn bộ event bằng một key dùng chung cho mọi module có thể làm mất ý nghĩa least privilege. Nếu mọi consumer đều có cùng key, một module bị xâm nhập có thể giải mã mọi payload. Cần tách key/permission theo data domain và consumer khi threat model yêu cầu.

### 9.4. TLS và encryption at rest

TLS bảo vệ dữ liệu trên đường truyền giữa service, broker, collector và backend. Encryption at rest bảo vệ storage/backup khi bị truy cập vật lý hoặc ở tầng lưu trữ. Cả hai đều không ngăn người dùng hợp lệ truy vấn dữ liệu plaintext qua ứng dụng.

Vì vậy, vẫn phải giảm payload, giới hạn quyền đọc, quản lý key, audit truy cập và đặt retention. Không xem “đã bật TLS” là đủ để event payload an toàn.

## 10. Bảo vệ Actuator và observability backends

Telemetry có thể tiết lộ cấu trúc hệ thống, tên module, trạng thái dependency, lưu lượng nghiệp vụ và thông tin lỗi. Endpoint quản trị cần được bảo vệ như một bề mặt truy cập nội bộ.

### 10.1. Chỉ expose endpoint cần thiết

Ví dụ cấu hình giới hạn endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus,modulith"
  endpoint:
    health:
      show-details: when-authorized
~~~

Danh sách trên là ví dụ. Chỉ expose `/actuator/modulith` nếu đội vận hành thực sự cần xem module structure qua endpoint. Không expose công khai các endpoint có thể tiết lộ environment, configuration, heap hoặc thông tin nội bộ.

### 10.2. Phân quyền theo vai trò

Một cách triển khai phổ biến:

- Prometheus scrape account chỉ đọc endpoint metrics cần thiết.
- Người vận hành có quyền truy cập health và module information theo vai trò.
- Developer truy cập traces/logs theo service/team và môi trường được cấp.
- Người quản trị bảo mật quản lý credential, key và audit policy.
- Dashboard dùng service account có quyền đọc đúng datasource và folder.

Không dùng một tài khoản admin dùng chung cho ứng dụng, Prometheus, Grafana và tracing backend. Dùng service identity riêng, credential rotation và network policy.

### 10.3. Bảo vệ trace/log backend

Thiết lập RBAC theo team, service và environment; giới hạn export/download; bật audit log cho truy vấn nhạy cảm; đặt retention theo phân loại dữ liệu. Nếu backend hỗ trợ field-level redaction hoặc tenant isolation, cấu hình như defense in depth và kiểm thử bằng tài khoản có quyền khác nhau.

### 10.4. Tránh đưa payload vào dashboard và alert

Dashboard/alert notification có thể được gửi qua email, chat hoặc incident platform. Chỉ đưa service, module, event type, outcome, trace link và mã tham chiếu đã được phê duyệt. Không chèn raw exception, request body, email hoặc payload vào alert annotation.

Một trace link cũng cần quyền truy cập tương ứng; người nhận alert không tự động có quyền đọc mọi span của trace đó.

## 11. Retention, deletion và audit

Payload nhạy cảm cần lifecycle rõ từ lúc publish đến lúc mọi bản sao được xóa hoặc hết hạn.

### 11.1. Lập data inventory

Ghi lại event type và các nơi dữ liệu có thể xuất hiện:

| Nơi lưu/truyền | Câu hỏi cần trả lời |
| --- | --- |
| Application memory | Event sống trong bao lâu và có thể dump heap không? |
| Event Publication Registry | Publication payload/metadata nào được persist? |
| Database backup | Bản sao lưu có cùng retention và access policy không? |
| Message broker | Topic/queue retention, replay và ACL thế nào? |
| Dead-letter/retry | Message lỗi được giữ bao lâu và ai được đọc? |
| Application logs | Có payload hoặc exception nhạy cảm không? |
| Trace backend | Attributes/events có dữ liệu nhận diện không? |
| Analytics/export | Có bản sao ở data lake, report hoặc file tải xuống không? |

### 11.2. Đặt retention theo mục đích

Không giữ mọi telemetry cùng một thời hạn. Metrics tổng hợp không chứa PII có thể có retention dài hơn; logs và traces chi tiết thường cần retention ngắn hơn; payload event persist phải theo yêu cầu nghiệp vụ và chính sách dữ liệu. Quy định thời gian cho cả primary store, replica, backup, dead-letter và export.

### 11.3. Xóa dữ liệu và quyền được yêu cầu

Nếu có yêu cầu xóa hoặc sửa dữ liệu cá nhân, cần xác định:

- Event nào chứa hoặc tham chiếu dữ liệu đó.
- Publication record, retry và dead-letter nào còn tồn tại.
- Broker replay/archive và backup có thể giữ bản sao không.
- Log/trace backend có hỗ trợ deletion hoặc retention policy phù hợp không.
- Có thể xóa mapping token/reference mà không phá audit nghiệp vụ không.

Không hứa xóa hoàn toàn ngay lập tức nếu backup immutable hoặc retention bắt buộc tồn tại. Ghi rõ quy trình, thời hạn và ngoại lệ pháp lý theo chính sách của tổ chức.

### 11.4. Audit truy cập

Ghi nhận ai đã truy cập payload nhạy cảm, khi nào, qua ứng dụng hoặc backend nào và mục đích hợp lệ. Audit log cũng phải được thiết kế không chứa chính secret/payload đang cần bảo vệ. Không ghi token hoặc dữ liệu đầy đủ vào audit record chỉ để chứng minh có truy cập.

## 12. Kiểm thử để phát hiện rò rỉ payload

Chính sách bảo mật cần được kiểm chứng bằng test. Một event có thể an toàn trong đường thành công nhưng bị lộ trong log exception, retry hoặc dead-letter.

### 12.1. Dùng synthetic sentinel values

Tạo dữ liệu giả có chuỗi dễ nhận diện, không dùng dữ liệu khách hàng thật:

~~~java
static final String SECRET_SENTINEL =
    "TEST_ONLY_SECRET_7f3c91";
static final String EMAIL_SENTINEL =
    "privacy-test@example.invalid";
~~~

Sau khi publish event và chạy listener, tìm các sentinel trong những bề mặt cần bảo vệ. Nếu sentinel xuất hiện trong log, span, metric tag hoặc payload không được phép, test phải fail.

### 12.2. Test log không chứa secret

Với Logback, có thể dùng `ListAppender` trong test để thu log event:

~~~java
ListAppender<ILoggingEvent> appender = new ListAppender<>();
appender.start();

Logger logger = (Logger) LoggerFactory.getLogger(OrderNotificationListener.class);
logger.addAppender(appender);

try {
    listener.on(safeOrderPlacedEvent);

    String output = appender.list.stream()
        .map(ILoggingEvent::getFormattedMessage)
        .collect(Collectors.joining("\n"));

    assertThat(output).doesNotContain(SECRET_SENTINEL);
    assertThat(output).doesNotContain(EMAIL_SENTINEL);
} finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

Đây là ví dụ cho Logback; nếu ứng dụng dùng logging implementation khác, dùng test appender tương ứng. Kiểm tra cả formatted message và structured arguments/MDC fields vì secret có thể nằm ngoài message text.

### 12.3. Test span không chứa payload nhạy cảm

Sau khi thu span bằng in-memory exporter, kiểm tra:

- Span attributes không có key hoặc value nhạy cảm.
- Span events không chứa exception message có sentinel.
- Baggage không chứa secret hoặc PII.
- Resource attributes không chứa user/customer identifier.

Ví dụ kiểm tra attribute values:

~~~java
SpanData span = exporter.getFinishedSpanItems().get(0);

String attributes = span.getAttributes().asMap().toString();
assertThat(attributes).doesNotContain(SECRET_SENTINEL);
assertThat(attributes).doesNotContain(EMAIL_SENTINEL);
~~~

Trong test đầy đủ, duyệt thêm `span.getEvents()` và resource attributes; không chỉ kiểm tra attribute map. Tránh serialize toàn bộ `SpanData` vào assertion message nếu test failure có thể làm lộ sentinel trong CI logs.

### 12.4. Test metric không có tag nhạy cảm

~~~java
for (Meter meter : meterRegistry.getMeters()) {
    for (Tag tag : meter.getId().getTags()) {
        assertThat(tag.getValue()).doesNotContain(SECRET_SENTINEL);
        assertThat(tag.getValue()).doesNotContain(EMAIL_SENTINEL);
    }
}
~~~

Có thể kiểm tra thêm tag key thuộc allowlist và cardinality của các meter nghiệp vụ không vượt ngưỡng dự kiến. Không cần quét tất cả meter nội bộ của framework bằng một allowlist cứng nếu chúng có convention riêng; tập trung vào meter do ứng dụng sở hữu.

### 12.5. Test serialized event và publication persistence

Kiểm tra serialization của event:

~~~java
String json = objectMapper.writeValueAsString(event);

assertThat(json).doesNotContain(SECRET_SENTINEL);
assertThat(json).doesNotContain(EMAIL_SENTINEL);
~~~

Nếu ứng dụng dùng persistent Event Publication Registry, viết integration test với đúng registry/serializer đang chạy để kiểm tra dữ liệu thực sự được lưu. Đừng chỉ test `ObjectMapper` mặc định nếu production dùng serializer khác.

### 12.6. Test broker và dead-letter

Với event externalized, dùng broker test container hoặc fake broker để kiểm tra message body, headers và dead-letter record. Xác nhận:

- Chỉ field được phép xuất hiện.
- Secret không bị đưa vào header hoặc message key.
- Log producer/consumer không ghi raw message.
- Retry/dead-letter không làm phát sinh bản sao plaintext ngoài policy.
- ACL và TLS được kiểm tra trong integration environment phù hợp.

### 12.7. Kiểm tra cả đường lỗi

Tạo test cho:

- Listener ném exception có message chứa sentinel.
- Retry publication nhiều lần.
- Serialization failure.
- Externalization/broker failure.
- Timeout khi gọi downstream service.
- Logging ở catch block và global exception handler.

Một test chỉ kiểm tra đường thành công chưa đủ. Rò rỉ thường xuất hiện khi log lỗi hoặc dump payload để chẩn đoán.

## 13. Quy trình xử lý khi phát hiện dữ liệu bị lộ

Nếu sentinel hoặc dữ liệu nhạy cảm xuất hiện ở telemetry, xử lý theo quy trình incident của tổ chức:

1. Xác định field, event type, service, module và thời gian bắt đầu.
2. Tìm mọi nơi đã nhận bản sao: logs, traces, metrics, registry database, broker, dead-letter, backup và export.
3. Ngăn phát sinh thêm bằng cách loại field khỏi payload/instrumentation hoặc tạm dừng đường export bị ảnh hưởng theo kế hoạch vận hành.
4. Hạn chế quyền truy cập tới bản ghi đã phát tán.
5. Đánh giá có cần rotate/revoke credential nếu secret thực sự bị lộ.
6. Xóa hoặc rút ngắn retention theo quy trình được phê duyệt và khả năng của từng backend.
7. Ghi audit và thông báo cho owner/privacy/security team theo chính sách.
8. Thêm regression test để ngăn lỗi tái diễn.

Không chỉ xóa log trên dashboard rồi coi sự cố đã kết thúc. Cần xác định replica, backup, archive, dead-letter và downstream export có còn bản sao không.

## 14. Những hiểu lầm cần tránh

**“Event chỉ chạy trong cùng JVM nên payload không nhạy cảm.”** Sai. Event có thể được log, persist, retry, externalize hoặc serialize bởi listener.

**“Module boundary là security boundary.”** Không. Spring Modulith giúp cấu trúc module; quyền đọc event phải được đánh giá theo listener và data domain.

**“Dùng `@JsonIgnore` là đủ.”** Không. Logger, `toString()`, serializer khác hoặc custom mapper vẫn có thể lộ field.

**“Masking ở collector giải quyết mọi rủi ro.”** Không. Dữ liệu thô có thể đã tồn tại ở application logs, exporter buffers hoặc đường truyền trước collector.

**“Hash customer ID thì có thể dùng làm metric label.”** Không. Hash vẫn có cardinality cao và có thể bị dò; metric labels không phải kho định danh.

**“Trace sampling giúp bảo vệ dữ liệu.”** Không. Sampling không bảo đảm trace có dữ liệu nhạy cảm sẽ luôn bị loại; phải loại dữ liệu trước khi tạo span.

**“TLS và encryption at rest là đủ.”** Không. Người dùng hợp lệ hoặc consumer có key vẫn có thể đọc plaintext; cần minimization, RBAC, audit và retention.

**“Event publication metric cho biết payload an toàn.”** Không. Metric publication chỉ đo hoạt động được instrument; nó không kiểm tra nội dung payload.

## 15. Checklist bảo mật trước khi phát hành

1. **Data inventory:** event type và field đã được phân loại theo sensitivity.
2. **Minimization:** mỗi listener chỉ nhận field thực sự cần.
3. **Event DTO:** không publish entity, HTTP request hoặc object có credential.
4. **Logging:** không log event/entity nguyên trạng; exception message được kiểm soát.
5. **Tracing:** span attributes, events và baggage không chứa secret/PII.
6. **Metrics:** labels chỉ dùng dimension có miền giá trị nhỏ; không chứa ID duy nhất.
7. **Persistence:** đã kiểm tra Event Publication Registry, serializer, database và backup.
8. **Externalization:** topic/queue ACL, TLS, schema, retry và dead-letter được bảo vệ.
9. **Masking/tokenization:** thực hiện ở nguồn theo policy; pseudonymous data vẫn được bảo vệ.
10. **Encryption:** key tách khỏi ciphertext, có rotation và quyền decrypt theo consumer.
11. **Actuator:** chỉ expose endpoint cần thiết và bảo vệ bằng network/authentication.
12. **Backend access:** RBAC, tenant isolation, audit và retention được cấu hình.
13. **Alert/dashboard:** không đưa payload hoặc exception nhạy cảm vào notification.
14. **Tests:** sentinel không xuất hiện trong log, span, metric, database hoặc broker ngoài allowlist.
15. **Failure paths:** retry, exception, dead-letter và serialization failure đã được kiểm tra.
16. **Incident response:** có owner và quy trình thu hồi/rotate/xóa khi phát hiện leak.

## 16. Bài tập thực hành

### Bài 1 — Thiết kế event an toàn

Cho một event `OrderPlaced` ban đầu chứa toàn bộ Customer entity, địa chỉ giao hàng, email, payment token và danh sách sản phẩm. Thiết kế lại DTO tối thiểu cho inventory, payment và notification. Giải thích field nào cần reference và field nào không được đưa vào event.

### Bài 2 — Phát hiện log leak

Tạo một test listener nhận event có sentinel email/token. Cố tình log event bằng `toString()`, chạy test với ListAppender và quan sát test fail. Sửa logger thành allowlist metadata rồi chạy lại.

### Bài 3 — Trace attributes và baggage

Tạo span cho module notification. Thử thêm email vào attribute và baggage trong test, sau đó viết assertion phát hiện sentinel. Thay bằng event type và opaque correlation reference đã được phê duyệt.

### Bài 4 — Metric cardinality

Tạo counter theo module/event type/outcome. Thử thêm customer ID làm tag và tính số series. Viết test kiểm tra tag keys/values thuộc allowlist.

### Bài 5 — Publication persistence

Trong test environment, bật Event Publication Registry có persistence theo cấu hình dự án. Publish event và kiểm tra dữ liệu được lưu/serialize. Xác nhận payload không chứa secret ngoài policy và quyền đọc database được giới hạn.

### Bài 6 — Externalized event

Externalize một event test tới broker. Kiểm tra message body, headers, TLS/ACL, retry và dead-letter. Xác nhận producer/consumer logs không ghi raw message.

### Bài 7 — Incident tabletop

Giả lập phát hiện access token trong log backend. Lập danh sách bản sao, cách ngăn phát sinh mới, cách revoke credential, xóa dữ liệu theo retention và regression test cần bổ sung.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không nên publish toàn bộ entity JPA làm application event?

**Đáp án:** Entity có thể chứa dữ liệu vượt nhu cầu listener, quan hệ lazy, credential và field nhạy cảm. DTO tường minh giúp giới hạn payload và review contract.

**Câu 2.** `@JsonIgnore` có bảo đảm field không xuất hiện trong log không?

**Đáp án:** Không. Annotation chỉ tác động một số serializer; `toString()`, logger và serializer khác vẫn có thể lộ field.

**Câu 3.** Vì sao không thêm email hoặc customer ID vào metric tags?

**Đáp án:** Chúng có thể nhận diện người dùng và tạo cardinality rất cao; metrics nên dùng dimension tổng hợp có miền giá trị nhỏ.

**Câu 4.** Baggage có rủi ro gì?

**Đáp án:** Baggage có thể được truyền qua nhiều service và instrumentation. Một giá trị nhạy cảm có thể lan rộng ngoài service ban đầu.

**Câu 5.** Collector redaction có thay thế data minimization ở nguồn không?

**Đáp án:** Không. Dữ liệu có thể đã được ghi hoặc truyền trước khi tới collector; redaction chỉ là lớp phòng vệ bổ sung.

**Câu 6.** Event Publication Registry có luôn lưu nguyên payload không?

**Đáp án:** Không thể giả định như vậy. Cần kiểm tra registry implementation, serializer, phiên bản và database schema thực tế.

**Câu 7.** Encryption có thay thế authorization không?

**Đáp án:** Không. Consumer có key vẫn giải mã được; cần giới hạn ai có key, ai được đọc và audit truy cập.

## 17. Tài liệu tham khảo

- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html): application events và Event Publication Registry.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry observations và event metrics.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose và bảo vệ management endpoints.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing, propagation và correlation.
- [OpenTelemetry — Security](https://opentelemetry.io/docs/security/): các cân nhắc bảo mật khi thu thập và truyền telemetry.
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/): spans, attributes, events và links.
- [OpenTelemetry — Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/): truyền baggage qua các service.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần tránh ghi log và bảo vệ log.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): nguyên tắc bảo vệ dữ liệu lưu trữ.

**Ghi nhớ:** bảo vệ event payload bằng cách chỉ phát dữ liệu listener thực sự cần, không log hoặc gắn payload vào span/metric, kiểm soát persistence và externalization, rồi bổ sung masking, encryption, RBAC, audit và retention. Với Spring Modulith, module graph và event listener giúp xác định ai có thể nhận event; chúng không tự cấp quyền hay tự loại bỏ dữ liệu nhạy cảm. Hãy kiểm thử bằng sentinel trên cả đường thành công lẫn đường lỗi để phát hiện rò rỉ trước khi phát hành.
