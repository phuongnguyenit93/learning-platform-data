# Producer adapter

Producer adapter là thành phần ở ranh giới giữa application event của ứng dụng Spring Modulith và message broker. Nó nhận sự kiện cần externalize, chuyển sự kiện thành thông điệp theo hợp đồng tích hợp, xác định destination, gửi thông điệp bằng client của broker và xử lý kết quả gửi.

Adapter giúp module nghiệp vụ chỉ công bố sự kiện đã xảy ra. Module không cần biết Kafka topic, RabbitMQ exchange, credential, serializer hay cách retry của broker. Những chi tiết đó thuộc lớp tích hợp và cấu hình triển khai.

Trong Spring Modulith, annotation `@Externalized` đánh dấu event cần được đưa ra ngoài và cung cấp target identifier. Target là khóa định tuyến để integration tìm cách gửi event. Nó không tự đại diện cho một Kafka topic, RabbitMQ queue hoặc consumer cụ thể trong mọi cấu hình. Cách ánh xạ target sang destination phụ thuộc integration và adapter mà ứng dụng sử dụng.

## 1. Vai trò và ranh giới của producer adapter

Producer adapter chịu trách nhiệm chuyển đổi giữa hai mô hình:

- **Application event:** biểu diễn sự kiện nghiệp vụ trong ứng dụng, có kiểu dữ liệu và ngữ nghĩa do producer sở hữu.
- **Broker message:** thông điệp trên wire format, có payload, headers, destination và metadata theo quy ước tích hợp.

Một adapter tốt giữ các trách nhiệm này ở ranh giới rõ ràng:

| Trách nhiệm | Việc adapter cần thực hiện |
|---|---|
| Nhận diện event | Xác định loại event và target identifier |
| Định tuyến | Ánh xạ target sang topic, exchange hoặc destination |
| Mapping | Chuyển event thành payload công bố ra ngoài |
| Serialization | Chuyển payload thành wire format đã thống nhất |
| Metadata | Gắn event ID, event type, schema version, correlation ID |
| Gửi message | Gọi broker client với destination và headers phù hợp |
| Xác nhận | Xác định khi nào broker đã xác nhận việc gửi theo cấu hình |
| Lỗi và phục hồi | Phân loại lỗi, để publication còn khả năng retry khi gửi thất bại |
| Quan sát | Ghi log, metric và trace ở ranh giới gửi |

Adapter không nên chứa quy tắc nghiệp vụ như tính lại tổng tiền, tự quyết định trạng thái đơn hàng hoặc thay đổi dữ liệu miền. Nếu cần biến đổi có ý nghĩa nghiệp vụ, hãy thực hiện ở module sở hữu dữ liệu trước khi phát event hoặc trong một bước mapping có hợp đồng được quản lý rõ.

## 2. Luồng từ application event đến broker

Một luồng externalization thường có các bước sau:

~~~mermaid
flowchart TD
    A["Module nghiệp vụ cập nhật dữ liệu"] --> B["Phát application event"]
    B --> C["Publication được ghi nhận"]
    C --> D["Externalization listener / producer adapter"]
    D --> E["Map target và tạo message"]
    E --> F["Serialize payload và headers"]
    F --> G["Broker client gửi message"]
    G --> H{"Broker xác nhận?"}
    H -->|Có| I["Adapter hoàn tất xử lý publication"]
    H -->|Không| J["Giữ publication chưa hoàn tất"]
    J --> K["Retry hoặc xử lý lỗi"]
    K --> G
~~~

Giao dịch nghiệp vụ và việc gửi message ra broker có thể nằm ở hai ranh giới tài nguyên khác nhau. Việc producer commit dữ liệu không đồng nghĩa broker đã nhận message; broker xác nhận cũng không đồng nghĩa consumer đã xử lý xong nghiệp vụ.

Event Publication Registry của Spring Modulith giúp theo dõi publication mà framework quản lý. Với externalization được cấu hình phù hợp, registry hỗ trợ phát hiện và phục hồi publication chưa hoàn tất. Adapter cần kết thúc xử lý đúng thời điểm theo mức xác nhận mà integration quy định để registry không ghi nhận hoàn tất quá sớm.

## 3. Đánh dấu event cần externalize

Event nên mô tả một sự kiện nghiệp vụ đã xảy ra và mang dữ liệu cần thiết cho consumer. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders.order-paid")
public record OrderPaid(
    UUID eventId,
    String orderNumber,
    BigDecimal total,
    String currency,
    Instant occurredAt
) {}
~~~

Target identifier `orders.order-paid` mô tả loại thông điệp được công bố. Producer không cần khai báo từng consumer như billing-service hay analytics-service trong event. Các consumer đăng ký subscription của mình ở phía broker.

Publisher phát event cùng giao dịch nghiệp vụ:

~~~java
@Service
class PaymentService {

    private final ApplicationEventPublisher events;

    PaymentService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    void confirmPayment(Order order, Payment payment) {
        order.markPaid(payment);

        events.publishEvent(new OrderPaid(
            payment.eventId(),
            order.getOrderNumber(),
            payment.amount(),
            payment.currency(),
            payment.confirmedAt()
        ));
    }
}
~~~

Ví dụ minh họa ranh giới phát event. Cấu hình transaction phase, publication registry và externalization adapter phải được thiết lập theo integration đang dùng. Không nên giả định rằng chỉ thêm annotation là ứng dụng đã có broker connection, credential, serializer hoặc tài nguyên destination.

## 4. Ánh xạ target sang destination

Target identifier cần được ánh xạ một cách ổn định và có thể kiểm soát. Ví dụ:

| Target identifier | Destination ví dụ | Ghi chú |
|---|---|---|
| orders.order-paid | Kafka topic `orders.order-paid` | Các consumer độc lập dùng group riêng |
| orders.order-cancelled | Kafka topic `orders.order-cancelled` | Event khác có thể có retention riêng |
| orders.order-paid | AMQP exchange `orders.events`, routing key `order.paid` | Queue subscription được bind ở phía broker |

Đây là các quy ước minh họa, không phải ánh xạ tự động bắt buộc của mọi adapter. Một integration có thể dùng target làm tên topic; integration khác có thể dùng bảng cấu hình để ánh xạ target tới exchange và routing key.

Nên quản lý ánh xạ tập trung theo môi trường. Ví dụ, target nghiệp vụ vẫn giữ nguyên giữa development, staging và production, trong khi destination, broker endpoint và credential thay đổi theo cấu hình triển khai.

Một cấu hình ánh xạ cần xử lý rõ:

- Target không tồn tại hoặc chưa được cấu hình.
- Target trỏ tới destination sai môi trường.
- Destination chưa được tạo hoặc producer không có quyền publish.
- Một target cần định tuyến đến nhiều destination.
- Destination thay đổi tên trong quá trình migration.
- Các target có yêu cầu retention, partition hoặc quyền truy cập khác nhau.

Không nên âm thầm gửi một target không xác định vào destination mặc định. Điều đó có thể làm event đi sai nơi và khó phát hiện. Hãy fail fast khi cấu hình thiếu hoặc ghi nhận lỗi cấu hình theo cách có thể quan sát.

## 5. Tạo message envelope và headers

Payload chứa dữ liệu nghiệp vụ; headers chứa metadata phục vụ định tuyến, truy vết và xử lý. Có thể dùng envelope chung để consumer đọc các event theo một cấu trúc thống nhất.

Ví dụ JSON minh họa:

~~~json
{
  "eventId": "9ac78a4c-4b9f-4a9c-9b1f-73c2d4e2f5a1",
  "eventType": "orders.order-paid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:15:30Z",
  "correlationId": "checkout-7f21",
  "payload": {
    "orderNumber": "ORD-2026-00421",
    "total": "125000.50",
    "currency": "VND"
  }
}
~~~

Một số metadata có thể được đặt trong broker headers thay vì body. Producer và consumer phải thống nhất vị trí của chúng; không nên để cùng một trường có hai giá trị khác nhau ở header và payload.

| Metadata | Mục đích |
|---|---|
| eventId | Nhận diện event và hỗ trợ idempotency |
| eventType | Xác định loại sự kiện |
| schemaVersion | Chọn schema hoặc quy tắc giải mã |
| occurredAt | Thời điểm nghiệp vụ xảy ra |
| correlationId | Liên kết log và trace giữa các hệ thống |
| contentType | Cho biết định dạng payload |
| producer | Nhận diện ứng dụng phát event, nếu contract cần |

Không đưa credential, access token hoặc dữ liệu bí mật vào header. Headers thường được log, hiển thị trong công cụ quản trị broker hoặc sao chép qua nhiều hệ thống.

## 6. Mapping và serialization

Adapter cần chuyển event thành một payload công bố ổn định. Không nên serialize trực tiếp entity JPA hoặc object graph nội bộ. Hãy dùng DTO riêng và mapping tường minh để kiểm soát trường dữ liệu, kiểu số, thời gian, enum và schema version.

Ví dụ DTO:

~~~java
public record OrderPaidPayload(
    UUID eventId,
    String orderNumber,
    String total,
    String currency,
    Instant occurredAt
) {}
~~~

Mapping từ event sang payload:

~~~java
OrderPaidPayload toPayload(OrderPaid event) {
    return new OrderPaidPayload(
        event.eventId(),
        event.orderNumber(),
        event.total().toPlainString(),
        event.currency(),
        event.occurredAt()
    );
}
~~~

Trong ví dụ, total được chuyển thành chuỗi decimal để tránh consumer khác ngôn ngữ diễn giải JSON number bằng floating point thiếu chính xác. Nếu tổ chức chọn kiểu khác, cần công bố precision, scale và quy tắc parse trong contract.

Serializer phải thống nhất với consumer về:

- JSON, Avro, Protobuf hoặc wire format khác.
- Quy tắc ngày giờ và timezone.
- Decimal, số nguyên lớn và enum.
- Null, field bị bỏ qua và default.
- Tên field và chính sách tương thích schema.
- Kích thước tối đa và giới hạn độ sâu payload.

Spring Boot có thể quản lý ObjectMapper dùng chung, nhưng adapter phải thực sự sử dụng cấu hình đó. Một serializer được tạo riêng trong adapter hoặc test có thể không áp dụng cùng module Java Time, naming strategy hay cách xử lý null như cấu hình runtime.

## 7. Gửi message và xử lý acknowledgment

Producer adapter cần biết chính xác broker client xác nhận điều gì. Tùy công nghệ, kết quả có thể cho biết request đã được gửi, broker đã nhận, partition đã lưu bản ghi hoặc exchange đã định tuyến message. Cấu hình durability, replication, publisher confirm và delivery mode quyết định mức bảo đảm thực tế.

Không nên coi việc gọi hàm send hoặc đưa message vào buffer nội bộ của client là broker đã nhận message. Nếu client gửi bất đồng bộ, adapter cần đợi kết quả hoàn tất hoặc sử dụng cơ chế async mà integration và publication registry hỗ trợ. Chỉ trả về thành công sau khi đạt mốc xác nhận đã chọn.

Một port minh họa cho adapter tùy biến:

~~~java
public interface BrokerPublisher {
    PublishReceipt publish(OutboundMessage message);
}

public record OutboundMessage(
    String destination,
    String key,
    Map<String, String> headers,
    byte[] payload
) {}

public record PublishReceipt(
    String brokerMessageId,
    Instant acknowledgedAt
) {}
~~~

Đây là interface minh họa ở tầng ứng dụng, không phải API Spring Modulith. Adapter cụ thể có thể dùng KafkaTemplate, AmqpTemplate hoặc client tương ứng. Điều quan trọng là kết quả trả về phản ánh acknowledgment thật của broker theo cấu hình, và lỗi gửi được truyền về luồng publication để có thể phục hồi.

Với Kafka, hãy xác định producer acknowledgment, idempotence, retry, partition key và replication policy. Với RabbitMQ, hãy xác định publisher confirms, exchange durability, message persistence, routing và hành vi khi message không được route. Không dùng một khái niệm "send thành công" chung cho mọi broker mà bỏ qua khác biệt của chúng.

## 8. Khóa partition và thứ tự thông điệp

Nếu các event liên quan đến cùng một aggregate cần được xử lý theo thứ tự, producer phải chọn key phù hợp. Với Kafka, record key thường được dùng để chọn partition. Những event có cùng key thường được ghi vào cùng partition và giữ thứ tự trong partition đó.

Ví dụ, dùng order ID làm key:

~~~text
key = orderId
value = serialized OrderPaid payload
~~~

Không dùng event ID làm partition key nếu mục tiêu là gom các event của cùng một đơn hàng về một partition; mỗi event ID khác nhau có thể phân tán chúng.

Thứ tự không được bảo đảm toàn cục giữa nhiều partition. Nếu consumer xử lý song song hoặc retry, thứ tự hoàn tất nghiệp vụ cũng có thể khác thứ tự broker giao message. Khi thứ tự có ý nghĩa, cần xác định aggregate key, version hoặc sequence number và quy tắc phát hiện event đến muộn.

Với AMQP, thứ tự phụ thuộc queue, consumer concurrency, redelivery và cấu hình broker. Nhiều consumer đọc cùng queue có thể xử lý song song. Nếu cần thứ tự theo aggregate, cân nhắc queue hoặc partitioning theo khóa và giới hạn concurrency phù hợp.

## 9. Độ tin cậy: publication registry, retry và duplicate

Giao dịch cơ sở dữ liệu và broker thường không tham gia cùng một giao dịch phân tán. Có thể xảy ra các tình huống:

- Producer commit dữ liệu nhưng tiến trình dừng trước khi gửi message.
- Broker nhận message nhưng kết nối đứt trước khi producer nhận acknowledgment.
- Producer retry sau timeout trong khi broker đã nhận message trước đó.
- Adapter trả thành công quá sớm khi client mới chỉ buffer message.
- Broker từ chối message vì destination, quota hoặc quyền truy cập.

Event Publication Registry của Spring Modulith giúp lưu trạng thái publication và tìm những publication chưa hoàn tất để phục hồi. Với externalization, cần cấu hình storage bền vững phù hợp và bảo đảm listener/adapter chỉ hoàn tất publication sau khi đạt mốc gửi đã định nghĩa.

Một timeout không chứng minh broker chưa nhận message. Vì vậy, retry có thể tạo duplicate. Producer nên giữ event ID ổn định; consumer cần idempotency để xử lý cùng event nhiều lần mà không tạo side effect trùng.

Retry policy nên phân biệt:

| Lỗi | Hướng xử lý |
|---|---|
| Timeout hoặc lỗi kết nối tạm thời | Retry với backoff và jitter |
| Broker quá tải hoặc throttling | Giảm tốc độ gửi, retry theo chính sách |
| Credential hoặc quyền publish sai | Cảnh báo và sửa cấu hình trước khi retry |
| Destination không tồn tại | Xem là lỗi cấu hình, không retry vô hạn |
| Payload không serialize được | Cách ly event và xử lý lỗi contract |
| Message vượt giới hạn kích thước | Sửa payload hoặc dùng tham chiếu object storage |

Không nuốt exception rồi trả về bình thường. Nếu adapter báo thành công trong khi broker chưa nhận message, publication registry có thể đánh dấu hoàn tất và ứng dụng mất khả năng phục hồi phần việc đó.

## 10. Transaction boundary và thứ tự phát event

Event thường được phát trong giao dịch cập nhật nghiệp vụ. Cần bảo đảm event phản ánh trạng thái đã commit. Spring Modulith Event Publication Registry hỗ trợ theo dõi publication trong luồng giao dịch mà framework quản lý; lựa chọn transaction phase và persistence implementation cần phù hợp với kiến trúc ứng dụng.

Không nên tự gửi message từ giữa một giao dịch chưa commit rồi giả định database và broker sẽ cùng rollback. Nếu broker đã nhận message nhưng database rollback, consumer có thể quan sát một sự kiện chưa thực sự xảy ra.

Cũng không nên tự xây một hàng đợi trong bộ nhớ để gửi sau commit nếu cần phục hồi khi tiến trình dừng. Một tác vụ trong bộ nhớ có thể mất khi ứng dụng restart. Hãy dùng publication registry bền vững hoặc mô hình outbox đã được thiết kế và kiểm thử cho yêu cầu đó.

Nếu ứng dụng cần atomicity giữa cập nhật dữ liệu và việc ghi nhận công việc cần gửi, publication record phải được ghi trong ranh giới giao dịch phù hợp. Gửi broker sau đó là bước riêng có thể retry. Cơ chế này giảm nguy cơ mất dấu event nhưng không biến toàn bộ hành trình tới consumer thành một giao dịch nguyên tử.

## 11. Bảo mật và kiểm soát cấu hình producer

Producer adapter thường có quyền publish vào một hoặc nhiều destination. Hãy cấp quyền tối thiểu theo target và môi trường. Không dùng chung credential giữa producer và consumer nếu không cần thiết.

Các cấu hình cần quản lý ngoài mã nguồn:

- Broker bootstrap servers hoặc endpoint.
- Credential, certificate và truststore.
- Destination, routing key và partition policy.
- Timeout, retry, batch size và buffer limit.
- Serialization format và schema registry endpoint.
- TLS, authentication và authorization.
- Message size limit và compression.

Không ghi secret trong source code, event payload, broker header hoặc log. Không log toàn bộ payload nếu có dữ liệu cá nhân, thông tin thanh toán hoặc bí mật nghiệp vụ. Cấu hình sai destination có thể gửi dữ liệu sang môi trường hoặc consumer không được phép, vì vậy cần kiểm tra mapping khi ứng dụng khởi động.

## 12. Quan sát producer adapter

Producer cần có khả năng trả lời: event nào đang chờ gửi, target nào đang lỗi, broker đã xác nhận bao nhiêu message và publication nào đang bị retry?

Các metric hữu ích:

- Số publication externalization được tạo và hoàn tất.
- Số publication incomplete và tuổi publication lâu nhất.
- Tỷ lệ publish thành công/thất bại theo target.
- Thời gian từ lúc nhận event đến lúc broker acknowledgment.
- Số lần retry, timeout và lỗi serialization.
- Số message bị broker từ chối hoặc không được route.
- Kích thước payload và tỷ lệ nén nếu có.

Log có cấu trúc nên chứa event ID, event type, target, destination, broker message ID, correlation ID, attempt number và exception type. Không đưa toàn bộ payload hoặc secret vào log.

Trace nên tách span mapping/serialization và span publish để phân biệt lỗi ở adapter với độ trễ broker. Cảnh báo cần dựa trên tuổi publication incomplete, tỷ lệ lỗi và mức độ quan trọng của event, không chỉ dựa trên số exception.

## 13. Kiểm thử producer adapter

Kiểm thử cần bao phủ mapping, serialization, routing và hành vi khi broker lỗi. Có thể dùng fake publisher cho unit test của mapping, nhưng cần integration test với broker hoặc môi trường tương thích để kiểm tra acknowledgment và cấu hình thật.

Các tình huống nên kiểm tra:

- Event có target đúng được ánh xạ tới destination dự kiến.
- Event được map sang payload có trường và kiểu dữ liệu theo contract.
- Event ID, correlation ID và schema version được truyền đúng.
- Serializer dùng đúng cấu hình runtime.
- Producer nhận biết broker acknowledgment thành công.
- Broker timeout hoặc từ chối publish làm publication chưa hoàn tất.
- Retry không thay đổi event ID hoặc payload nghiệp vụ.
- Message có key đúng để giữ thứ tự theo aggregate nếu yêu cầu.
- Destination không tồn tại hoặc mapping thiếu tạo lỗi có thể quan sát.
- Payload quá lớn hoặc không hợp lệ được xử lý theo chính sách.
- Restart ứng dụng không làm mất publication chưa hoàn tất đã lưu bền vững.

Một kiểm thử quan trọng là mô phỏng tình huống broker đã nhận message nhưng producer mất acknowledgment. Khi retry, broker có thể nhận bản thứ hai. Test này chứng minh consumer cần idempotency và producer không thể hứa exactly-once end-to-end chỉ dựa trên một lần gửi.

## 14. Lỗi thiết kế thường gặp

**Để module nghiệp vụ gọi trực tiếp broker client.** Điều này làm module phụ thuộc transport, credential và routing. Hãy công bố application event và để adapter phụ trách giao tiếp bên ngoài.

**Coi target identifier luôn là tên topic hoặc queue.** Mapping phụ thuộc integration. Hãy quản lý ánh xạ tường minh và kiểm tra cấu hình lúc khởi động.

**Đánh dấu publication hoàn tất ngay sau khi gọi send bất đồng bộ.** Client có thể chưa nhận được acknowledgment. Hãy chờ kết quả hoặc dùng cơ chế async có trạng thái hoàn tất rõ.

**Nuốt exception trong adapter.** Registry có thể hiểu nhầm message đã được gửi. Hãy để lỗi truyền về luồng phục hồi.

**Retry vô hạn mọi loại lỗi.** Lỗi cấu hình và payload không hợp lệ không tự biến mất. Hãy phân loại lỗi, giới hạn retry và cách ly trường hợp không thể tự khắc phục.

**Dùng event ID làm key khi cần thứ tự theo aggregate.** Các event của cùng một đơn hàng có thể rơi vào partition khác nhau. Hãy chọn business aggregate ID làm key.

**Coi broker acknowledgment là consumer đã xử lý.** Producer chỉ biết mức xác nhận từ broker. Consumer cần cơ chế xác nhận và quan sát riêng.

**Serialize entity nội bộ.** Payload trở nên dễ thay đổi và có thể lộ dữ liệu không cần thiết. Hãy mapping sang DTO contract.

## Kết luận

Producer adapter chuyển application event thành broker message theo một hợp đồng tích hợp ổn định. Nó chịu trách nhiệm mapping target, tạo payload và metadata, serialize, gửi message, xử lý acknowledgment và để publication chưa hoàn tất có thể được phục hồi khi cần.

Khi adapter giữ ranh giới rõ, cấu hình destination được kiểm soát, acknowledgment phản ánh đúng mức bảo đảm của broker và event ID được giữ ổn định qua retry, ứng dụng Spring Modulith có thể externalize event đáng tin cậy mà module nghiệp vụ không phải phụ thuộc trực tiếp vào công nghệ messaging.

