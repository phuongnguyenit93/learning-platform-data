# Xác định consumer bên ngoài

Event externalization đưa application event từ một ứng dụng Spring Modulith ra một hệ thống khác, thường thông qua message broker. Để định tuyến đúng, cần xác định rõ **hệ thống nào cần nhận sự kiện, nó đăng ký nhận qua đích giao tiếp nào và nó sẽ xử lý hợp đồng dữ liệu ra sao**.

Spring Modulith giúp đánh dấu event cần externalize và gắn event với một target identifier. Target này là thông tin định tuyến để integration adapter chuyển sự kiện ra bên ngoài. Nó không phải danh sách consumer đang hoạt động và cũng không tự khám phá các ứng dụng đã subscribe. Consumer thực tế được xác định qua cấu hình topic, exchange, queue, subscription, consumer group và quyền truy cập của hạ tầng messaging.

## 1. Phân biệt consumer, destination và subscription

Ba khái niệm thường bị gộp làm một nhưng có vai trò khác nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| External consumer | Ứng dụng hoặc hệ thống nào sử dụng dữ liệu? | billing-service, analytics-service |
| Destination | Sự kiện được gửi đến đâu? | Kafka topic orders.order-paid, AMQP exchange orders.events |
| Subscription | Consumer nhận thông điệp bằng cấu hình nào? | Kafka consumer group billing-service; queue billing.order-paid được bind vào exchange |
| Event contract | Consumer phải hiểu payload theo cấu trúc nào? | OrderPaid với eventId, orderId, occurredAt, total |

Một destination có thể phục vụ nhiều consumer. Ví dụ, billing-service và analytics-service đều cần biết một đơn hàng đã thanh toán. Producer có thể phát một event vào destination chung; mỗi consumer đăng ký subscription độc lập để nhận bản sao theo cơ chế của broker.

Tên consumer không nhất thiết là tên destination. Nếu đặt topic theo từng consumer ngay từ đầu, producer sẽ phải biết danh sách ứng dụng nhận sự kiện và thường phải thay đổi khi có consumer mới. Destination theo event hoặc nhóm hợp đồng nghiệp vụ thường giữ producer ít phụ thuộc hơn. Chỉ tạo destination riêng cho một consumer khi có lý do rõ ràng như dữ liệu khác nhau, quyền truy cập khác nhau, yêu cầu lưu giữ khác nhau hoặc chính sách vận hành riêng.

## 2. Xác định ai thực sự cần nhận event

Trước khi cấu hình externalization, hãy bắt đầu từ nhu cầu nghiệp vụ. Một event chỉ nên được gửi ra ngoài khi có hệ thống khác cần phản ứng với sự kiện đó hoặc cần dùng dữ liệu đó cho một mục đích được xác định.

Có thể lập danh sách consumer theo các câu hỏi sau:

- **Tên ứng dụng:** hệ thống nào sẽ nhận và xử lý event?
- **Chủ sở hữu:** nhóm nào chịu trách nhiệm vận hành consumer và xử lý lỗi?
- **Mục đích:** consumer dùng event để cập nhật dữ liệu, kích hoạt quy trình hay phân tích?
- **Phạm vi dữ liệu:** consumer cần toàn bộ payload hay chỉ một phần thông tin?
- **Độ trễ:** xử lý trong vài giây, vài phút hay theo lô?
- **Mức độ quan trọng:** nếu consumer ngừng hoạt động, nghiệp vụ nào bị ảnh hưởng?
- **Bảo mật:** consumer có được phép nhận các trường dữ liệu đó không?
- **Khả năng phát lại:** consumer có thể xử lý lại cùng một event mà không tạo tác dụng phụ trùng lặp không?

Ví dụ với OrderPaid, có thể có hai consumer độc lập:

| Consumer | Mục đích | Dữ liệu cần | Cách nhận |
|---|---|---|---|
| billing-service | Ghi nhận giao dịch thanh toán | Mã đơn, số tiền, thời điểm, mã giao dịch | Subscription riêng |
| analytics-service | Cập nhật số liệu doanh thu | Mã đơn, số tiền, thời điểm, loại tiền | Subscription riêng |

Nếu analytics-service bị dừng, billing-service vẫn cần tiếp tục nhận event. Hai consumer không nên dùng chung một hàng đợi theo kiểu competing consumers nếu mỗi hệ thống đều cần nhận mọi event. Với Kafka, hai consumer cần group ID khác nhau để mỗi group nhận luồng bản ghi độc lập. Với RabbitMQ, mỗi consumer cần queue riêng được bind vào exchange/routing key phù hợp.

Danh sách consumer nên được ghi nhận trong tài liệu hợp đồng tích hợp hoặc catalog do đội sở hữu nền tảng quản lý. Thông tin này cần có owner, môi trường, destination, subscription, quyền truy cập và quy trình liên hệ khi có thay đổi. Annotation ở producer không thay thế catalog đó.

## 3. Đặt target identifier cho event trong Spring Modulith

Spring Modulith sử dụng annotation **@Externalized** để đánh dấu event cần được đưa ra ngoài. Giá trị của annotation là target identifier mà externalization integration dùng để định tuyến. Cách target được ánh xạ thành topic, exchange hoặc destination cụ thể phụ thuộc transport adapter và cấu hình của ứng dụng.

Ví dụ, event thanh toán đơn hàng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders.order-paid")
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    BigDecimal total,
    String currency,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

orders.order-paid là target identifier được chọn theo hợp đồng nghiệp vụ. Nó mô tả loại thông điệp cần đưa ra ngoài, không gắn chặt với tên một consumer cụ thể. Nếu sau này có thêm hệ thống phân tích, đối soát hoặc thông báo cần nhận event, các hệ thống đó có thể đăng ký subscription phù hợp mà producer không phải thêm một lệnh gửi riêng cho từng ứng dụng.

Publisher vẫn phát application event trong luồng nghiệp vụ:

~~~java
@Component
class OrderPaymentService {

    private final ApplicationEventPublisher events;

    OrderPaymentService(ApplicationEventPublisher events) {
        this.events = events;
    }

    void confirmPayment(Order order, Payment payment) {
        // Cập nhật trạng thái đơn và ghi nhận thanh toán
        // trong giao dịch nghiệp vụ hiện tại.

        events.publishEvent(new OrderPaid(
            UUID.randomUUID(),
            order.getId(),
            payment.amount(),
            payment.currency(),
            Instant.now(),
            1
        ));
    }
}
~~~

Event được đánh dấu @Externalized sẽ được Spring Modulith nhận diện cho luồng externalization khi ứng dụng đã cấu hình integration phù hợp. Producer không cần gọi trực tiếp API của từng consumer. Việc phát event và việc chuyển event tới broker là hai bước có thể được theo dõi và phục hồi theo cơ chế publication mà ứng dụng cấu hình.

Không nên đưa tên máy chủ, thông tin đăng nhập, địa chỉ kết nối hoặc tên instance đang chạy vào target identifier. Những giá trị đó thuộc cấu hình môi trường và broker. Target nên ổn định qua các môi trường; cấu hình triển khai sẽ ánh xạ target tới tài nguyên messaging tương ứng.

## 4. Ánh xạ target sang cơ chế nhận của broker

Target identifier là điểm nối giữa event trong ứng dụng và destination bên ngoài. Khi chọn transport, cần làm rõ cách một target được ánh xạ sang tài nguyên messaging.

### Kafka

Với Kafka, target có thể được ánh xạ tới một topic như orders.order-paid. Mỗi ứng dụng nhận độc lập nên có consumer group riêng:

~~~text
Target identifier: orders.order-paid
Kafka topic:       orders.order-paid

Consumer:
  billing-service
  group.id = billing-service

Consumer:
  analytics-service
  group.id = analytics-service
~~~

Các instance của cùng một ứng dụng thường dùng chung group ID để chia nhau xử lý partition. Những ứng dụng độc lập cần nhận đầy đủ luồng sự kiện nên dùng group ID khác nhau. Nếu hai ứng dụng dùng chung group ID, Kafka phân phối bản ghi giữa các instance trong group; mỗi ứng dụng có thể chỉ nhận một phần bản ghi thay vì cùng nhận toàn bộ.

Ví dụ consumer dùng Spring Kafka ở phía ứng dụng nhận:

~~~java
@KafkaListener(
    topics = "orders.order-paid",
    groupId = "billing-service"
)
void on(OrderPaidPayload event) {
    billingService.recordPayment(event);
}
~~~

Đây là ví dụ ở phía consumer. Cách deserialize payload, cấu hình serializer, tên topic và cơ chế xác thực phải khớp với adapter externalization và cấu hình Kafka đang triển khai. Consumer có thể được viết bằng Spring, framework khác hoặc ngôn ngữ khác, miễn là tuân thủ event contract.

### RabbitMQ hoặc AMQP

Với AMQP, cần phân biệt exchange, routing key và queue:

- Exchange nhận thông điệp do producer gửi.
- Routing key giúp exchange định tuyến thông điệp.
- Queue giữ thông điệp cho một subscription.
- Consumer đọc thông điệp từ queue đó.

Một cách tổ chức fan-out là dùng exchange chung cho event của đơn hàng, routing key mô tả loại event và một queue riêng cho từng ứng dụng:

~~~text
Exchange: orders.events
Routing key: order.paid

Queue: billing.order-paid
  binding: orders.events + order.paid

Queue: analytics.order-paid
  binding: orders.events + order.paid
~~~

Khi một event được publish với routing key order.paid, cả hai queue đã bind phù hợp đều có thể nhận bản sao. Nhiều instance của billing-service đọc cùng queue sẽ chia nhau xử lý thông điệp của queue đó. analytics-service đọc queue riêng nên không tranh thông điệp với billing.

Tên exchange, routing key và queue trong ví dụ là quy ước thiết kế. Adapter cụ thể có thể yêu cầu cách khai báo hoặc ánh xạ target khác; hãy đối chiếu cấu hình của integration đang sử dụng thay vì giả định target luôn bằng tên exchange hoặc queue.

### Chọn mô hình phân phối

| Nhu cầu | Mô hình thường phù hợp |
|---|---|
| Nhiều ứng dụng độc lập đều phải nhận mọi event | Một destination chung với subscription độc lập cho mỗi ứng dụng |
| Nhiều instance của cùng ứng dụng chia tải | Cùng consumer group hoặc cùng queue |
| Consumer có quyền dữ liệu khác nhau | Destination, payload hoặc subscription được phân tách theo quyền |
| Consumer cần nhịp xử lý hoặc thời hạn lưu trữ khác nhau | Subscription hoặc tài nguyên messaging riêng |
| Consumer chỉ cần một tập event | Filter hoặc binding theo loại event/routing key, tùy broker |

Chọn mô hình theo ngữ nghĩa phân phối trước khi chọn tên tài nguyên. Nếu cần fan-out, hãy bảo đảm cấu hình broker thực sự tạo bản sao độc lập cho từng consumer.

## 5. Thiết kế event contract cho consumer

Một external consumer có thể được triển khai độc lập và thay đổi theo lịch phát hành riêng. Vì vậy, payload cần là hợp đồng ổn định, có thể đọc mà không phụ thuộc vào class nội bộ hoặc mô hình persistence của producer.

Một event contract nên có:

- **Event ID:** định danh duy nhất và ổn định khi phát lại.
- **Event type:** tên loại sự kiện có ý nghĩa nghiệp vụ.
- **Occurred at:** thời điểm sự kiện xảy ra theo chuẩn thời gian thống nhất.
- **Schema version:** phiên bản cấu trúc payload hoặc cơ chế versioning được tổ chức sử dụng.
- **Business identifiers:** các ID cần thiết để consumer liên kết dữ liệu.
- **Payload tối thiểu:** chỉ những trường consumer được phép và thực sự cần dùng.

Ví dụ OrderPaid chứa mã đơn, số tiền, loại tiền, thời điểm và event ID. Không nên gửi cả entity JPA, lazy relation, thông tin nội bộ của database hoặc toàn bộ hồ sơ khách hàng chỉ vì producer đang có sẵn các đối tượng đó.

Hãy đặt tên event theo sự kiện nghiệp vụ đã xảy ra, chẳng hạn OrderPaid, OrderCancelled hoặc ShipmentDispatched. Tránh tên phụ thuộc vào chi tiết kỹ thuật như OrderRowUpdated hay PaymentTableChanged. Tên event và ý nghĩa của nó cần ổn định để consumer hiểu được ngay cả khi producer thay đổi cấu trúc module hoặc database.

Khi mở rộng schema, ưu tiên thay đổi tương thích ngược: thêm trường có thể bỏ qua, giữ nguyên ý nghĩa trường hiện có và không đổi kiểu dữ liệu tùy tiện. Nếu cần thay đổi phá vỡ tương thích, hãy công bố phiên bản hoặc loại event mới, lập thời gian chuyển đổi và xác định consumer nào đã sẵn sàng. Có thể dùng schema registry hoặc tài liệu contract để kiểm soát tương thích giữa producer và consumer.

Không dùng schema version như một cách che giấu thay đổi ý nghĩa. Nếu trường total trước đây là số tiền trước thuế nhưng nay chuyển thành số tiền sau thuế, consumer cũ có thể tiếp tục đọc được dữ liệu nhưng xử lý sai nghiệp vụ. Mọi thay đổi ngữ nghĩa cần được công bố rõ ràng.

## 6. Xử lý nhiều consumer và thay đổi danh sách consumer

Khi có consumer mới, quy trình thông thường là:

1. Xác định mục đích nghiệp vụ và owner của consumer.
2. Xác nhận event contract hiện tại đã chứa dữ liệu cần thiết và được phép chia sẻ.
3. Chọn destination và mô hình subscription phù hợp.
4. Cấp quyền đọc destination, cấu hình consumer group hoặc queue, cùng chính sách retry và dead-letter ở phía broker.
5. Triển khai consumer ở môi trường thử nghiệm và kiểm tra với payload thực tế.
6. Theo dõi lag, lỗi xử lý, tỷ lệ thành công và khả năng phát lại trước khi đưa vào vận hành.

Nếu consumer cần dữ liệu nhạy cảm hoặc cấu trúc khác với event công khai hiện có, hãy cân nhắc tạo một event contract hoặc projection riêng. Không thêm dữ liệu nhạy cảm vào payload dùng chung chỉ để phục vụ một consumer mới.

Khi ngừng một consumer, cần xác định thời điểm dừng subscription, xử lý thông điệp còn tồn, lưu trữ dữ liệu cần đối soát và thu hồi quyền truy cập. Việc xóa consumer khỏi tài liệu không tự động xóa queue, consumer group hoặc credential trong broker. Những tài nguyên đó phải được quản lý trong quy trình hạ tầng tương ứng.

Nếu consumer đổi tên hoặc được tách thành nhiều ứng dụng, hãy giữ ổn định destination nếu hợp đồng event không đổi. Điều chỉnh subscription và quyền truy cập ở phía hạ tầng. Cách này giúp tránh buộc producer phát hành lại chỉ vì topology consumer thay đổi.

## 7. Giao event đáng tin cậy và giới hạn bảo đảm

Event Publication Registry của Spring Modulith theo dõi publication tới listener mà framework quản lý. Với externalization được cấu hình đúng, publication liên quan tới việc chuyển event ra ngoài có thể được lưu bền vững và xem xét resubmit khi chưa hoàn tất. Điều này giúp ứng dụng phục hồi khi việc gửi ra broker gặp lỗi hoặc tiến trình dừng giữa chừng.

Cần phân biệt các mốc xác nhận:

1. Giao dịch nghiệp vụ của producer commit.
2. Spring Modulith ghi nhận publication cần externalize.
3. Integration gửi thông điệp tới broker và nhận kết quả theo cơ chế xác nhận của adapter.
4. Broker lưu hoặc định tuyến thông điệp theo cấu hình.
5. External consumer nhận thông điệp.
6. Consumer xử lý nghiệp vụ và xác nhận thông điệp theo cơ chế của broker.

Publication được đánh dấu hoàn tất ở phía producer không chứng minh rằng consumer đã hoàn tất nghiệp vụ. Nó chỉ phản ánh mức hoàn tất mà listener externalization và transport adapter có thể xác nhận. Muốn theo dõi đến bước xử lý cuối cùng, consumer cần có log, metric, trạng thái xử lý hoặc acknowledgment phù hợp ở phía mình.

Hệ thống messaging có thể giao trùng trong một số tình huống retry hoặc phục hồi. Consumer nên thiết kế idempotency dựa trên event ID hoặc khóa nghiệp vụ. Nếu cùng một event được nhận lại, consumer cần nhận diện và tránh tạo thanh toán, hóa đơn hoặc side effect trùng lặp.

Ví dụ, consumer ghi nhận event ID đã xử lý cùng giao dịch với thay đổi dữ liệu của nó:

~~~text
BEGIN TRANSACTION

Nếu eventId đã có trong processed_events:
    kết thúc xử lý như một lần giao trùng
Ngược lại:
    áp dụng thay đổi nghiệp vụ
    lưu eventId vào processed_events

COMMIT
ACK message
~~~

Dấu mốc xử lý và thay đổi nghiệp vụ phải có ranh giới nhất quán. Nếu consumer gọi dịch vụ bên ngoài, cần idempotency key ở dịch vụ đích hoặc quy trình đối soát riêng. Không đánh dấu message thành công trước khi bảo đảm công việc cần thiết đã hoàn tất theo chính sách của consumer.

## 8. Bảo mật và quản trị quyền truy cập

Xác định consumer cũng là xác định ai được quyền đọc dữ liệu. Mỗi ứng dụng nên có identity riêng trong broker, được cấp quyền tối thiểu trên destination cần dùng. Không dùng chung credential giữa nhiều consumer vì sẽ khó thu hồi quyền, truy vết và phân tích sự cố.

Trước khi externalize một event, hãy phân loại dữ liệu:

- Trường nào là dữ liệu nghiệp vụ cần thiết?
- Trường nào chứa thông tin cá nhân hoặc bí mật?
- Consumer nào có căn cứ nghiệp vụ để nhận từng trường?
- Dữ liệu được lưu trong broker và hệ thống nhận trong bao lâu?
- Log có vô tình ghi toàn bộ payload hay không?

Có thể tạo event projection chỉ chứa trường đã được phê duyệt thay vì gửi nguyên đối tượng nội bộ. Với dữ liệu nhạy cảm, cân nhắc mã hóa, phân quyền theo destination, chính sách retention và audit truy cập. Không đưa token, mật khẩu, credential, thông tin xác thực hoặc dữ liệu thanh toán nhạy cảm vào event.

## 9. Quan sát hoạt động theo từng consumer

Một destination có thể có nhiều consumer với tốc độ và mức độ ổn định khác nhau. Vì thế, dashboard và cảnh báo nên phân biệt được destination với từng subscription hoặc consumer group.

Các chỉ số cần theo dõi gồm:

- Số event được externalize và tỷ lệ gửi thành công.
- Số publication chưa hoàn tất và tuổi publication lâu nhất ở phía producer.
- Kafka consumer lag hoặc độ dài queue ở phía broker.
- Tỷ lệ xử lý thành công, retry và dead-letter ở từng consumer.
- Thời gian từ lúc event xảy ra đến khi consumer hoàn tất nghiệp vụ.
- Số event bị từ chối do schema không tương thích hoặc dữ liệu không hợp lệ.

Log nên có event ID, event type, target identifier, destination, consumer/group hoặc queue, correlation ID và thời điểm xử lý. Producer và consumer cần truyền correlation ID xuyên suốt để điều tra một giao dịch từ lúc phát event tới lúc consumer xử lý xong.

Cảnh báo nên gắn với tác động nghiệp vụ. Consumer thanh toán bị lag có thể cần ngưỡng cảnh báo chặt hơn consumer phân tích dữ liệu chạy theo lô. Khi một consumer lỗi liên tục, cần xác định lỗi nằm ở producer, broker, cấu hình subscription hay logic xử lý phía consumer trước khi replay hàng loạt.

## 10. Các lỗi thường gặp khi xác định consumer

**Dùng tên consumer làm target mặc định.** Cách này khiến producer phải biết mọi ứng dụng nhận. Hãy chọn target theo event contract hoặc destination nghiệp vụ khi nhiều consumer cần cùng một event.

**Cho rằng @Externalized tự tìm consumer.** Annotation đánh dấu event và cung cấp target identifier cho externalization. Việc ứng dụng nào subscribe destination do broker và cấu hình phía consumer quyết định.

**Dùng chung một consumer group cho các ứng dụng độc lập.** Các ứng dụng có thể chia nhau bản ghi thay vì mỗi ứng dụng nhận đầy đủ luồng. Hãy dùng group ID riêng khi cần fan-out trên Kafka.

**Dùng chung một queue cho các consumer cần cùng nhận mọi event.** Các consumer đọc cùng queue sẽ cạnh tranh thông điệp. Hãy tạo queue riêng và bind phù hợp cho từng subscription độc lập trong mô hình AMQP fan-out.

**Đổi destination chỉ vì consumer đổi tên.** Consumer identity và event contract là hai khái niệm khác nhau. Giữ target ổn định khi hợp đồng không đổi và cập nhật subscription ở phía hạ tầng.

**Gửi payload chứa entity nội bộ hoặc dữ liệu thừa.** Điều này làm consumer phụ thuộc vào cấu trúc database và tăng rủi ro lộ dữ liệu. Hãy công bố DTO bất biến với trường tối thiểu.

**Coi producer publication hoàn tất là consumer đã xử lý xong.** Registry của producer không theo dõi toàn bộ nghiệp vụ ở ứng dụng nhận. Consumer cần cơ chế xác nhận, retry, idempotency và quan sát riêng.

**Không chuẩn bị cho event giao trùng hoặc schema thay đổi.** Retry và phát lại có thể tạo lần giao lặp; producer có thể phát hành phiên bản contract mới. Hãy thiết kế idempotency và chính sách tương thích ngay từ đầu.

## 11. Quy trình kiểm tra trước khi công bố consumer

Trước khi đưa một consumer mới vào sử dụng, hãy xác nhận các điểm sau:

| Hạng mục | Điều cần xác nhận |
|---|---|
| Consumer identity | Có tên ứng dụng, owner và môi trường rõ ràng |
| Nhu cầu nghiệp vụ | Có lý do cụ thể để nhận event |
| Event contract | Có event type, event ID, thời điểm, schema và ý nghĩa trường |
| Target | Đã chọn target identifier ổn định và hiểu cách adapter ánh xạ |
| Destination | Topic/exchange/queue tồn tại và có cấu hình phù hợp |
| Subscription | Consumer group hoặc queue bảo đảm đúng semantics phân phối |
| Security | Identity riêng và quyền tối thiểu |
| Reliability | Có retry, dead-letter, idempotency và quy trình replay phù hợp |
| Observability | Có metric, log, cảnh báo và correlation ID |
| Lifecycle | Có owner, quy trình nâng cấp, ngừng hoạt động và thu hồi quyền |

Nếu một consumer chưa có owner hoặc chưa xác định được cách xử lý event giao trùng, chưa nên coi tích hợp đã sẵn sàng vận hành.

## Kết luận

Trong Spring Modulith, @Externalized đánh dấu event cần được đưa ra ngoài và cung cấp target identifier cho integration. Để xác định consumer bên ngoài, cần kết hợp event contract với cấu hình destination và subscription ở broker. Consumer identity, target, topic, exchange, queue và consumer group có trách nhiệm khác nhau; hiểu đúng từng khái niệm giúp thiết kế fan-out, chia tải và phân quyền chính xác.

Khi consumer được xác định bằng nhu cầu nghiệp vụ, có owner, hợp đồng dữ liệu ổn định và cơ chế vận hành rõ ràng, producer có thể công bố event mà không phụ thuộc trực tiếp vào từng ứng dụng nhận. Các consumer mới có thể đăng ký độc lập, trong khi ranh giới module và khả năng phục hồi của luồng event vẫn được duy trì.

