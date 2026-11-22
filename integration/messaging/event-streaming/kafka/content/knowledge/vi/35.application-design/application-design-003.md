# Tránh topic dùng chung trở thành hợp đồng phụ thuộc chặt

Trong Kafka, một topic có thể được nhiều producer ghi và nhiều consumer đọc. Khả năng chia sẻ này rất hữu ích để phân phối sự kiện giữa các dịch vụ. Tuy nhiên, nếu nhiều nhóm ứng dụng cùng ghi các loại dữ liệu không liên quan vào một topic tổng quát như **events** hoặc **system-events**, topic dễ trở thành một hợp đồng ngầm mà mọi bên phải hiểu giống nhau.

Khi hợp đồng đó thay đổi, một producer có thể vô tình làm hỏng nhiều consumer. Các nhóm cũng bị ràng buộc bởi cùng quy tắc phân vùng, retention, compaction, quyền truy cập và nhịp phát hành schema. Đây là dạng phụ thuộc chặt ở cấp dữ liệu và vận hành.

Mục tiêu thiết kế không phải là tạo một topic cho mọi record. Mục tiêu là chọn ranh giới topic theo quyền sở hữu nghiệp vụ và đặc tính vận hành, công bố schema có quản lý, đồng thời để mỗi consumer có thể tiến hóa độc lập trong giới hạn hợp đồng đã thống nhất.

## 1. Topic dùng chung trở thành vấn đề khi nào?

Một topic được nhiều consumer đọc không tự động là thiết kế xấu. Đây là cách Kafka hỗ trợ fan-out: nhiều consumer group có thể đọc cùng một luồng với tiến độ độc lập. Vấn đề thường xuất hiện khi topic trở thành nơi tập hợp tùy tiện dữ liệu từ nhiều miền nghiệp vụ hoặc nhiều hệ thống không có cùng nhu cầu.

Ví dụ, một topic tên **events** nhận tất cả loại record sau:

- **OrderPlaced** từ Order Service.
- **PaymentCaptured** từ Payment Service.
- **CustomerAddressChanged** từ Customer Service.
- **InventoryAdjusted** từ Inventory Service.
- **EmailDeliveryFailed** từ Notification Service.

Mỗi record có thể mang schema, key, độ nhạy dữ liệu và chu kỳ lưu trữ khác nhau. Consumer phải đọc topic rồi tự phân loại theo trường **eventType**. Khi thêm loại event mới, các consumer có thể cần cập nhật parser, bộ lọc và logic xử lý. Khi một producer đổi schema hoặc cách phân vùng, tác động có thể lan đến những ứng dụng không liên quan.

Topic tổng quát thường gây ra các dạng phụ thuộc sau:

1. **Phụ thuộc schema:** consumer phải biết tất cả biến thể payload hoặc tự xử lý các trường hợp không nhận diện.
2. **Phụ thuộc tên và ngữ nghĩa:** đổi eventType, tên trường hoặc ý nghĩa trường có thể làm consumer hiện có hiểu sai dữ liệu.
3. **Phụ thuộc phân vùng:** các event không liên quan bị ép dùng chung key strategy và số partition dù có yêu cầu ordering hoặc throughput khác nhau.
4. **Phụ thuộc retention:** các event có thời gian lưu khác nhau phải dùng chung chính sách retention của topic.
5. **Phụ thuộc bảo mật:** quyền đọc ở cấp topic có thể cho phép một consumer nhìn thấy các loại record khác mà nó không cần.
6. **Phụ thuộc vận hành:** một loại event có lưu lượng tăng đột biến có thể ảnh hưởng tài nguyên và độ trễ của các consumer cùng đọc topic.

Một topic chung chỉ nên được chọn khi các record thực sự thuộc cùng một luồng dữ liệu có ý nghĩa, có quy tắc phân vùng và chính sách lưu trữ tương thích, cùng một ranh giới quản trị phù hợp.

## 2. Phân biệt chia sẻ luồng với trộn nhiều hợp đồng

Kafka cho phép nhiều consumer group độc lập đọc một topic. Ví dụ, cùng topic **orders.events** có thể được đọc bởi:

- Group **fulfillment** để chuẩn bị giao hàng.
- Group **notification** để gửi thông báo.
- Group **analytics** để tổng hợp số liệu.

Mỗi group quản lý offset riêng. Việc group **fulfillment** đã đọc record không làm record biến mất hoặc khiến group **analytics** mất cơ hội đọc. Đây là chia sẻ luồng đúng mục đích: một hợp đồng event có chủ sở hữu rõ ràng được nhiều consumer sử dụng.

Ngược lại, nếu một topic **events** trộn dữ liệu đơn hàng, thanh toán, khách hàng và thông báo, mỗi consumer phải hiểu một tập hợp hợp đồng khác nhau. Consumer group giúp tách tiến độ đọc, nhưng không tách schema, quyền truy cập, retention hoặc quy tắc phân vùng của topic.

| Thiết kế | Đặc điểm | Rủi ro phụ thuộc |
|---|---|---|
| Một topic theo miền hoặc họ event có liên quan | Nhiều consumer dùng chung một hợp đồng có chủ sở hữu | Thường kiểm soát được nếu schema và chính sách rõ |
| Một topic tổng hợp mọi event của hệ thống | Nhiều hợp đồng không liên quan cùng tồn tại | Cao: schema, key, retention, bảo mật và lưu lượng bị trộn |
| Một topic riêng cho từng consumer | Mỗi ứng dụng có bản sao dữ liệu riêng | Có thể giảm phụ thuộc đọc nhưng tăng số luồng sao chép và công việc đồng bộ |
| Topic nguồn và topic dẫn xuất | Event nguồn có chủ sở hữu; luồng dẫn xuất phục vụ nhu cầu riêng | Ranh giới rõ, cần quản lý pipeline và schema của output |

Không nên tạo topic riêng cho từng consumer một cách máy móc. Nếu nhiều consumer cần cùng một sự kiện nghiệp vụ, hãy để chúng đọc cùng topic nguồn bằng các group riêng. Chỉ tạo topic dẫn xuất khi có nhu cầu biến đổi, lọc, tổng hợp, che dữ liệu hoặc áp dụng chính sách lưu trữ khác.

## 3. Chọn ranh giới topic theo miền nghiệp vụ

Một cách bắt đầu thực tế là xác định **dịch vụ hoặc miền nghiệp vụ sở hữu sự kiện**. Topic nên thể hiện nguồn dữ liệu và chủ đề đủ rõ để producer, consumer và người vận hành hiểu được mục đích.

Ví dụ:

~~~text
orders.events
payments.events
customers.events
inventory.events
notifications.delivery-events
~~~

Các tên này không phải quy tắc bắt buộc của Kafka. Chúng là quy ước đặt tên minh họa, giúp thể hiện chủ sở hữu và miền dữ liệu.

Trong một miền, có thể nhóm nhiều event có cùng đặc tính vào một topic nếu chúng chia sẻ được:

- Cùng chủ sở hữu và quy tắc công bố.
- Cùng nhu cầu ordering, thường theo cùng loại entity key.
- Cùng yêu cầu retention hoặc compaction.
- Cùng ranh giới bảo mật và nhóm consumer được phép đọc.
- Cùng mức lưu lượng và yêu cầu vận hành có thể dự đoán.

Ví dụ, **orders.events** có thể chứa **OrderPlaced**, **OrderCancelled** và **OrderShipped** nếu các sự kiện đều thuộc vòng đời đơn hàng, được key theo orderId, có cùng chính sách lưu trữ và được quản lý bởi Order domain.

Tuy nhiên, nếu **orders.events** phải giữ lịch sử đầy đủ còn **orders.current-state** chỉ cần trạng thái mới nhất theo key và bật compaction, hai luồng nên có topic riêng. Chính sách lưu trữ khác nhau là lý do rõ ràng để tách.

### Khi nào nên tách topic?

| Dấu hiệu | Quyết định nên cân nhắc |
|---|---|
| Event thuộc miền nghiệp vụ khác và có chủ sở hữu khác | Tách topic theo miền |
| Cần key hoặc ordering khác nhau | Tách topic để chọn partition strategy phù hợp |
| Retention hoặc cleanup policy khác nhau | Tách topic |
| Có mức độ nhạy cảm hoặc quyền đọc khác nhau | Tách topic theo ranh giới bảo mật |
| Lưu lượng một loại event vượt trội và ảnh hưởng các loại khác | Tách topic hoặc thiết kế phân vùng riêng |
| Các event có schema và vòng đời tương thích, cùng chủ sở hữu | Có thể giữ chung topic với envelope và schema rõ ràng |

Số lượng topic không phải mục tiêu tối ưu độc lập. Mỗi topic và partition đều có chi phí metadata, file, tài nguyên broker và vận hành. Hãy tách khi ranh giới hợp đồng hoặc chính sách cần tách thực sự khác nhau.

## 4. Xây dựng hợp đồng event rõ ràng

Một topic trở nên dễ sử dụng khi producer công bố hợp đồng có thể kiểm tra và consumer biết cách diễn giải record. Hợp đồng nên xác định tối thiểu:

- **Tên event:** mô tả sự thật đã xảy ra, ví dụ **OrderPlaced**.
- **Chủ sở hữu:** nhóm hoặc dịch vụ chịu trách nhiệm về ý nghĩa và chất lượng dữ liệu.
- **Schema:** kiểu dữ liệu, trường bắt buộc, trường tùy chọn và quy tắc tương thích.
- **Key:** entity hoặc aggregate dùng để phân vùng và duy trì thứ tự cần thiết.
- **Timestamp:** phân biệt thời điểm nghiệp vụ xảy ra với timestamp Kafka gán cho record.
- **Event ID:** định danh ổn định để consumer nhận biết cùng một event khi retry hoặc phát lại.
- **Quy tắc tiến hóa:** cách bổ sung, ngừng dùng hoặc thay đổi trường mà không phá consumer hiện tại.

Ví dụ một envelope event đơn hàng:

~~~json
{
  "eventId": "evt-91b2",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "occurredAt": "2026-11-20T09:30:00Z",
  "producer": "order-service",
  "aggregateId": "order-1042",
  "data": {
    "customerId": "customer-88",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

Producer có thể dùng **order-1042** làm Kafka key. Consumer dựa vào eventType và schema đã công bố để diễn giải value. Các trường eventId, schemaVersion và occurredAt phục vụ các mục đích khác nhau: định danh, tương thích schema và thời gian nghiệp vụ.

Không nên coi envelope là lý do để đưa mọi event của mọi miền vào một topic. Envelope chuẩn hóa cách mô tả record, nhưng không giải quyết khác biệt về retention, bảo mật, ordering và chủ sở hữu giữa các miền.

### Tiến hóa schema có kiểm soát

Producer và consumer thường được triển khai ở các thời điểm khác nhau. Vì vậy, schema phải có quy tắc tương thích rõ ràng. Một số nguyên tắc phổ biến:

- Ưu tiên thêm trường tùy chọn có giá trị mặc định phù hợp thay vì đổi ý nghĩa trường đang dùng.
- Không đổi kiểu dữ liệu của trường hiện có nếu consumer cũ chưa thể xử lý.
- Không tái sử dụng tên trường cũ cho một ý nghĩa mới.
- Kiểm tra compatibility bằng Schema Registry hoặc quy trình kiểm tra schema tương đương trước khi phát hành.
- Ghi rõ trường nào đã deprecated, khoảng thời gian hỗ trợ và thời điểm có thể xóa.

Nếu thay đổi không tương thích, có thể cần một phiên bản hợp đồng mới hoặc một topic mới, cùng kế hoạch chuyển consumer. Không nên thêm hậu tố version vào topic cho mọi lần bổ sung trường nhỏ; version topic chỉ hữu ích khi ranh giới tương thích hoặc khả năng triển khai thực sự yêu cầu tách.

## 5. Key và partition là một phần của hợp đồng

Topic không chỉ xác định nơi lưu record. Số partition và cách chọn key ảnh hưởng đến thứ tự, khả năng song song và tải broker.

Ví dụ, nếu các sự kiện vòng đời của cùng một đơn hàng cần được xử lý theo thứ tự, producer nên dùng orderId làm key:

~~~text
key = order-1042

OrderPlaced
PaymentAuthorized
OrderShipped
~~~

Với partitioner mặc định, cùng key thường được định tuyến đến cùng partition trong cùng điều kiện phân vùng. Kafka bảo đảm thứ tự trong một partition, không bảo đảm thứ tự toàn cục giữa mọi partition.

Nếu một topic trộn event đơn hàng, thanh toán và telemetry nhưng lại dùng chung một quy tắc key, một số partition có thể nóng hoặc consumer phải xử lý nhiều loại record không liên quan. Khi mỗi miền cần ordering, partition count hoặc phân phối tải khác nhau, tách topic thường đơn giản hơn.

Cũng cần chú ý rằng tăng số partition có thể làm thay đổi kết quả ánh xạ key của partitioner mặc định cho các record mới. Nếu ứng dụng dựa vào thứ tự lâu dài theo entity, phải đánh giá tác động của thay đổi partition count và quy trình chuyển đổi trước khi thực hiện.

## 6. Topic dùng chung còn chia sẻ retention và bảo mật

Retention và cleanup policy được cấu hình ở cấp topic. Nếu topic chứa event có yêu cầu lưu 7 ngày và event khác cần lưu 1 năm, một chính sách duy nhất khó đáp ứng cả hai mục tiêu.

Tương tự, một topic compacted giữ trạng thái mới nhất theo key. Nếu nhiều loại event cùng dùng một key trong topic compacted, record mới nhất của key có thể khiến các record cũ hơn bị loại trong quá trình compaction, kể cả khi chúng là loại event khác. Chỉ nên dùng compaction khi mô hình key-value thực sự biểu diễn trạng thái mong muốn; nếu cần lịch sử event, chọn cleanup policy phù hợp.

Bảo mật cũng là ranh giới quan trọng. Kafka ACL thường được áp dụng theo resource như topic và consumer group. Khi một ứng dụng có quyền đọc topic chung, nó có thể đọc mọi record trong topic; lọc theo eventType ở phía consumer không phải cơ chế kiểm soát truy cập dữ liệu. Nếu các miền có quyền đọc khác nhau, hãy tách topic và cấp ACL theo nhu cầu tối thiểu.

Vì vậy, trước khi gộp hai họ event vào cùng topic, hãy hỏi:

- Có cùng thời gian retention và cleanup policy không?
- Có thể dùng cùng key strategy và ordering không?
- Cùng nhóm ứng dụng có quyền đọc toàn bộ dữ liệu không?
- Lưu lượng có thể chia sẻ mà không gây ảnh hưởng lẫn nhau không?
- Có một chủ sở hữu chịu trách nhiệm cho hợp đồng và thay đổi schema không?

Nếu câu trả lời khác nhau đáng kể, hãy tách topic hoặc tạo luồng dẫn xuất có chính sách riêng.

## 7. Ví dụ triển khai với Spring Kafka

Giả sử Order Service là chủ sở hữu của **orders.events**. Nó phát event sau khi ghi nhận đơn hàng thành công. Fulfillment Service và Analytics Service đọc cùng topic bằng hai consumer group riêng:

Kiểu dữ liệu minh họa cho event có thể là một Java record:

~~~java
public record OrderEvent(
    String orderId,
    String eventType,
    String status
) {}
~~~

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderEvent event) {
        kafkaTemplate.send(
            "orders.events",
            event.orderId(),
            event
        );
    }
}
~~~

Consumer phục vụ giao hàng:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class FulfillmentConsumer {
    @KafkaListener(
        topics = "orders.events",
        groupId = "fulfillment"
    )
    public void onOrderEvent(OrderEvent event) {
        // Cập nhật quy trình chuẩn bị đơn hàng.
    }
}
~~~

Consumer phân tích:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAnalyticsConsumer {
    @KafkaListener(
        topics = "orders.events",
        groupId = "order-analytics"
    )
    public void onOrderEvent(OrderEvent event) {
        // Cập nhật số liệu phân tích đơn hàng.
    }
}
~~~

Hai group đọc độc lập cùng một topic. Nếu hai consumer thuộc cùng một group, Kafka phân phối partition giữa chúng để chia tải; chúng không nhận hai bản sao độc lập của mọi record.

Ví dụ trên giả định OrderEvent là hợp đồng đã được thống nhất. Trong ứng dụng thực tế, nên cấu hình serializer/deserializer tương ứng, quản lý schema, xử lý lỗi và cân nhắc transactional outbox để tránh tình huống cơ sở dữ liệu đã commit đơn hàng nhưng việc publish event thất bại.

Nếu Analytics cần dữ liệu đã làm giàu hoặc tổng hợp với retention riêng, có thể tạo topic dẫn xuất như **orders.analytics-view**. Pipeline tạo topic đó trở thành thành phần sở hữu schema output; Analytics không cần yêu cầu Order Service thay đổi event nguồn chỉ để phục vụ một truy vấn riêng.

## 8. Quy trình thiết kế topic trước khi triển khai

Có thể dùng quy trình sau trong một nhóm phát triển:

1. **Xác định producer sở hữu event.** Ghi rõ dịch vụ nào được quyền định nghĩa ý nghĩa và phát hành schema.
2. **Nhóm event theo vòng đời và chính sách chung.** Chỉ đặt chung topic khi key, ordering, retention, bảo mật và tải tương thích.
3. **Định nghĩa key và partition.** Xác định entity cần giữ thứ tự, mức song song và nguy cơ hot partition.
4. **Công bố schema và quy tắc tương thích.** Consumer phải biết cách xử lý trường mới, event chưa biết và schema version.
5. **Chọn retention và cleanup policy.** Phân biệt topic lưu lịch sử event với topic lưu trạng thái compacted.
6. **Cấp quyền theo topic.** Producer chỉ có quyền ghi vào topic thuộc phạm vi của nó; consumer chỉ đọc topic cần thiết.
7. **Kiểm thử consumer độc lập.** Thử thêm event mới, thêm consumer group, thay đổi schema tương thích và mô phỏng consumer chậm.
8. **Quản lý thay đổi có lộ trình.** Thông báo deprecation, theo dõi consumer còn dùng hợp đồng cũ và chỉ xóa phiên bản sau khi các bên đã chuyển đổi.

Một bảng hợp đồng đơn giản có thể được lưu cùng tài liệu kỹ thuật của hệ thống:

| Topic | Chủ sở hữu producer | Key | Nhóm event | Chính sách |
|---|---|---|---|---|
| orders.events | Order Service | orderId | Vòng đời đơn hàng | Lưu lịch sử, nhiều consumer group |
| payments.events | Payment Service | paymentId | Vòng đời thanh toán | ACL và retention theo dữ liệu thanh toán |
| customers.state | Customer Service | customerId | Trạng thái mới nhất | Compaction |
| orders.analytics-view | Pipeline phân tích | orderId | Dữ liệu đã biến đổi | Retention phù hợp truy vấn phân tích |

Các tên và chính sách trong bảng là ví dụ minh họa; cần điều chỉnh theo yêu cầu lưu trữ, bảo mật và pháp lý của hệ thống thật.

## 9. Những ngộ nhận thường gặp

**“Càng ít topic càng dễ vận hành.”** Không nhất thiết. Một topic tổng hợp có thể giảm số lượng topic ban đầu nhưng tăng độ phức tạp của schema, quyền truy cập, partitioning và consumer.

**“Mỗi consumer phải có một topic riêng.”** Không đúng. Nhiều consumer group có thể đọc cùng một topic với offset riêng. Topic dẫn xuất chỉ cần khi có biến đổi hoặc chính sách khác biệt.

**“Consumer group tách biệt hoàn toàn các hợp đồng.”** Không đúng. Group tách tiến độ và phân phối partition, nhưng không tách schema, retention, ACL hoặc key strategy của topic.

**“Chỉ cần thêm eventType là có thể gộp mọi event.”** Không đủ. Trường eventType giúp phân loại payload, nhưng không giải quyết chính sách partition, retention, compaction, bảo mật và quyền sở hữu.

**“Schema Registry làm topic chung an toàn.”** Không tự động. Registry giúp quản lý schema và compatibility; nó không quyết định topic có ranh giới nghiệp vụ hợp lý hay consumer nào được đọc loại dữ liệu nào.

**“Đổi tên field nhỏ là không ảnh hưởng consumer.”** Không đúng. Consumer có thể phụ thuộc tên và ý nghĩa field. Thay đổi phải tuân thủ quy tắc tương thích đã thống nhất.

## 10. Tự kiểm tra cách hiểu

1. Nhiều consumer group đọc cùng orders.events có phải là coupling xấu không? — Không. Đây là fan-out bình thường khi topic có một hợp đồng rõ ràng.
2. Tại sao một topic events chứa mọi loại dữ liệu dễ gây phụ thuộc chặt? — Vì các producer và consumer phải chia sẻ schema, key strategy, retention, bảo mật và quy tắc vận hành.
3. Consumer group có tách ACL và retention của từng event type không? — Không. Các chính sách này gắn với topic hoặc resource tương ứng.
4. Khi nào nên tách topic? — Khi chủ sở hữu, ordering, key, retention, cleanup policy, bảo mật hoặc tải khác nhau đáng kể.
5. Có cần topic riêng cho từng consumer không? — Không. Hãy dùng consumer group riêng nếu chỉ cần tiến độ đọc độc lập.
6. Vì sao topic compacted cần key được thiết kế cẩn thận? — Compaction giữ trạng thái mới nhất theo key và có thể loại các record cũ hơn của cùng key.
7. Schema Registry giải quyết vấn đề nào? — Quản lý schema và kiểm tra compatibility; nó không thay thế quyết định ranh giới topic.
8. Ai chịu trách nhiệm hợp đồng event? — Producer hoặc miền nghiệp vụ sở hữu event phải công bố và quản lý ý nghĩa, schema cùng lộ trình thay đổi.

Một thiết kế Kafka bền vững cho phép nhiều consumer chia sẻ event mà không buộc các miền nghiệp vụ không liên quan cùng tiến hóa. Hãy bắt đầu từ chủ sở hữu và ý nghĩa của event, sau đó chọn ranh giới topic theo key, ordering, retention, bảo mật và lưu lượng. Topic là một phần của hợp đồng dữ liệu; giữ hợp đồng rõ ràng giúp producer và consumer thay đổi độc lập trong giới hạn đã thống nhất.

