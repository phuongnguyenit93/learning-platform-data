# Subscribe topic theo regular expression

Trong Kafka, một consumer có thể đăng ký đọc một topic cụ thể hoặc một tập topic có tên phù hợp với biểu thức chính quy (regular expression). Spring Kafka hỗ trợ cách đăng ký này qua thuộc tính `topicPattern` của `@KafkaListener`. Cách làm phù hợp khi một service cần đọc nhiều topic có chung quy ước đặt tên, hoặc cần tự nhận biết những topic mới được tạo sau khi ứng dụng đã chạy.

Ví dụ, một consumer có thể đăng ký mẫu `^orders\..+$` để nhận các topic như `orders.created`, `orders.updated` và `orders.cancelled`. Khi topic mới `orders.refunded` được tạo và metadata được cập nhật, consumer đang subscribe theo pattern có thể phát hiện topic mới, tham gia rebalance và nhận các partition tương ứng.

Pattern chỉ quyết định consumer đăng ký những topic nào. Nó không định tuyến record ở phía producer, không lọc record theo payload và không tự tạo topic. Producer vẫn gửi vào một tên topic cụ thể; Kafka broker lưu record vào partition; consumer group nhận partition của các topic khớp pattern theo cơ chế phân phối bình thường.

Bài học thuộc chương **Consumer** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Subscribe topic bằng regular expression là gì?

Có ba cách phổ biến để consumer xác định nguồn topic:

- Đăng ký một hoặc nhiều topic theo tên cụ thể.
- Đăng ký bằng một regular expression để khớp nhiều tên topic.
- Gán trực tiếp các partition cụ thể bằng topic-partition assignment.

Với Spring Kafka, `@KafkaListener` cung cấp các thuộc tính tương ứng:

| Thuộc tính | Mục đích |
| --- | --- |
| `topics` | Đăng ký một hoặc nhiều topic có tên cụ thể. |
| `topicPattern` | Đăng ký các topic có tên khớp regular expression. |
| `topicPartitions` | Chỉ định topic và partition cụ thể mà listener nhận. |

Trong một listener endpoint, chọn phương thức đăng ký phù hợp với yêu cầu. Không kết hợp `topics`, `topicPattern` và `topicPartitions` như thể chúng là các bộ lọc bổ sung cho nhau.

Ví dụ đăng ký theo tên cố định:

~~~java
@KafkaListener(
    topics = {"orders.created", "orders.updated"},
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Ví dụ đăng ký theo pattern:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Trong ví dụ thứ hai, listener đăng ký mọi topic có tên phù hợp với pattern. Khi danh sách topic thay đổi, Kafka consumer có thể cập nhật subscription theo metadata và thực hiện rebalance.

## 2. Cú pháp regular expression thường dùng

`topicPattern` nhận một chuỗi regular expression theo cú pháp Java Pattern. Pattern được dùng để so khớp tên topic, vì vậy cần viết sao cho chỉ khớp namespace mà service thực sự sở hữu.

Một số thành phần regex hữu ích:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `^` | Bắt đầu chuỗi | `^orders` |
| `$` | Kết thúc chuỗi | `v1$` |
| `.` | Một ký tự bất kỳ | `a.b` |
| `\.` | Dấu chấm literal | `orders\.created` |
| `.*` | Không hoặc nhiều ký tự | `orders\..*` |
| `.+` | Một hoặc nhiều ký tự | `orders\..+` |
| `[0-9]+` | Một hoặc nhiều chữ số | `v[0-9]+` |
| `(a|b)` | Một trong các nhánh | `(created|updated)` |

Dùng `^` và `$` để thể hiện rõ phạm vi toàn tên topic cần khớp. Tránh pattern quá rộng như `.*` nếu service không thực sự cần subscribe mọi topic trong cluster.

### 2.1. Escape dấu chấm trong Java string

Trong regex, dấu chấm `.` là ký tự đại diện. Nếu tên topic chứa dấu chấm thật, phải escape nó thành `\\.` trong regex.

Khi viết regex trong Java string, dấu gạch chéo ngược phải được escape thêm một lần. Vì vậy, annotation dùng:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-projection"
)
~~~

Giá trị Java string `"^orders\\..+$"` được chuyển thành regex `^orders\..+$`. Nếu chỉ viết `"^orders..+$"`, dấu chấm không còn là dấu phân cách literal; pattern có thể khớp các tên topic ngoài dự kiến.

Khi regex được đặt trong YAML với chuỗi nháy đơn, dấu gạch chéo ngược được giữ nguyên:

~~~yaml
app:
  kafka:
    order-topic-pattern: '^orders\..+$'
~~~

Sau đó có thể tham chiếu bằng property placeholder:

~~~java
@KafkaListener(
    topicPattern = "${app.kafka.order-topic-pattern}",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Cần phân biệt cách escape trong Java string và trong file cấu hình. Khi đọc một pattern, hãy xác định nó đang ở trong Java source, YAML hay một lớp cấu hình khác để tránh escape thừa hoặc thiếu.

## 3. Cách Spring Kafka đăng ký listener theo pattern

Khi Spring tạo listener container từ phương thức có `@KafkaListener(topicPattern = ...)`, container sử dụng Kafka consumer subscription theo Pattern. Kafka client lấy metadata topic từ cluster và so khớp tên topic với pattern để xác định subscription.

Luồng hoạt động:

~~~mermaid
flowchart TD
    A[Spring khởi tạo @KafkaListener] --> B[Listener container]
    B --> C[Consumer subscribe Pattern]
    C --> D[Kafka lấy metadata topic]
    D --> E[So khớp tên topic với regex]
    E --> F[Consumer group nhận assignment]
    F --> G[Poll record từ các partition]
    G --> H[Listener xử lý record]
    D --> I[Metadata refresh]
    I --> E
~~~

Pattern được áp dụng ở phía Kafka consumer/client khi xác định topic subscription. Broker không nhận regex để tự định tuyến record; broker vẫn lưu và phục vụ record theo topic/partition cụ thể.

Vì subscription dựa trên metadata, topic phải tồn tại trong cluster để được phát hiện. Khi có topic mới phù hợp với pattern, consumer có thể nhận biết sau lần metadata refresh tiếp theo. Không nên giả định topic mới được thêm vào subscription ngay tức thì tại thời điểm tạo.

## 4. Ví dụ @KafkaListener với topicPattern

Giả sử hệ thống có nhiều topic về đơn hàng:

- `orders.created`
- `orders.updated`
- `orders.cancelled`
- `orders.refunded`

Các topic có cùng kiểu event `OrderEvent` và được xử lý bởi một projection service. Có thể dùng pattern:

~~~java
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private final OrderProjection orderProjection;

    @KafkaListener(
        topicPattern = "^orders\\..+$",
        groupId = "order-projection"
    )
    public void onOrderEvent(OrderEvent event) {
        orderProjection.apply(event);
    }
}
~~~

Listener đăng ký các topic khớp namespace `orders.`. Nếu một topic mới như `orders.refunded` xuất hiện, consumer có thể phát hiện và tham gia subscription sau khi metadata được làm mới.

Dùng một pattern cho nhiều topic chỉ phù hợp khi các topic có contract tương thích với listener. Nếu mỗi topic chứa một schema hoàn toàn khác, một phương thức nhận cùng kiểu payload có thể không giải mã được dữ liệu hoặc xử lý sai nghiệp vụ.

### 4.1. Quan sát topic nguồn trong listener

Khi một listener nhận dữ liệu từ nhiều topic, nên biết record đến từ topic nào. Có thể nhận `ConsumerRecord`:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-audit"
)
public void audit(ConsumerRecord<String, OrderEvent> record) {
    log.info(
        "Nhận event topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderAuditService.record(record.topic(), record.value());
}
~~~

Hoặc inject header nhận diện topic:

~~~java
@KafkaListener(
    topicPattern = "^orders\\..+$",
    groupId = "order-audit"
)
public void audit(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {

    orderAuditService.record(topic, event);
}
~~~

Thông tin topic, partition và offset giúp truy vết sự kiện. Khi listener nhận nhiều topic, nên đưa tên topic vào log, metric hoặc trace context để phân tích sự cố theo nguồn.

## 5. Topic mới khớp pattern được phát hiện thế nào?

Một lợi ích của pattern subscription là consumer không cần khai báo lại danh sách topic mỗi khi một topic mới cùng namespace được tạo.

Ví dụ:

1. Ứng dụng đang subscribe pattern `^orders\..+$`.
2. Cluster hiện có `orders.created` và `orders.updated`.
3. Một quy trình provisioning tạo topic `orders.refunded`.
4. Kafka consumer làm mới metadata và nhận biết tên topic mới phù hợp pattern.
5. Subscription của consumer group thay đổi; Kafka thực hiện rebalance để phân phối partition.
6. Consumer đọc record từ các partition mới được gán theo offset của group.

Việc phát hiện topic mới phụ thuộc metadata refresh và trạng thái consumer group. Thời gian thực tế còn phụ thuộc cấu hình Kafka client, broker và tình trạng kết nối; không nên viết logic nghiệp vụ dựa vào một khoảng chờ cố định.

Pattern subscription không phải cơ chế tạo topic. Topic mới cần được tạo bởi KafkaAdmin/NewTopic, AdminClient, pipeline hạ tầng hoặc cơ chế auto-create riêng của broker nếu được cho phép. Cấu hình auto-create là chính sách độc lập; không nên dựa vào nó để bảo đảm topic luôn có partition và replication đúng thiết kế.

## 6. Rebalance khi tập topic khớp pattern thay đổi

Consumer group cần phân phối partition của tập topic mà các thành viên subscribe. Khi một topic mới được phát hiện hoặc một topic bị xóa, tập partition của subscription có thể thay đổi và group thực hiện rebalance.

Trong thời gian rebalance:

- Partition có thể được thu hồi khỏi consumer hiện tại.
- Partition được phân phối lại cho các consumer đang hoạt động trong group.
- Consumer có thể tạm dừng việc xử lý record trong giai đoạn chuyển giao.
- Offset đã commit của từng topic-partition tiếp tục là mốc tiến độ của group.
- Record chưa được xử lý/commit có thể được đọc lại tùy thời điểm dừng và chính sách commit.

Rebalance là một phần bình thường của consumer group. Tuy nhiên, nếu topic liên tục được tạo/xóa hoặc pattern quá rộng khiến tập subscription thay đổi thường xuyên, hệ thống có thể gặp rebalance nhiều hơn và ảnh hưởng throughput.

Khi thiết kế, nên dùng namespace ổn định và quy trình provisioning topic có kiểm soát. Nếu hệ thống tạo topic hàng loạt, cần xem xét tác động tới metadata refresh và số lượng partition mới được thêm vào group.

## 7. Consumer group và offset khi subscribe nhiều topic

Pattern subscription không làm thay đổi nguyên tắc consumer group. Mỗi group có tiến độ offset riêng cho từng topic-partition.

Giả sử pattern khớp hai topic:

~~~text
Group: order-projection

orders.created
  Partition 0 -> committed offset 120
  Partition 1 -> committed offset 85

orders.updated
  Partition 0 -> committed offset 64
  Partition 1 -> committed offset 92
~~~

Các offset trên thuộc các topic-partition khác nhau. Offset 120 của `orders.created-0` không có quan hệ thứ tự với offset 64 của `orders.updated-0`.

Nếu có hai consumer group cùng subscribe một pattern, mỗi group có thể nhận toàn bộ record của các topic khớp pattern theo tiến độ riêng:

- `order-projection` đọc để cập nhật projection.
- `order-audit` đọc để ghi audit.

Hai group không chia sẻ committed offset. Trong mỗi group, các consumer chia nhau partition; giữa hai group, cả hai đều có thể đọc cùng dữ liệu.

### 7.1. auto-offset-reset với topic mới

Khi topic mới được phát hiện, group thường chưa có committed offset cho partition mới. Khi đó, `auto.offset.reset` quyết định vị trí bắt đầu nếu không có offset hợp lệ:

- `earliest`: bắt đầu từ record sớm nhất còn được giữ.
- `latest`: bắt đầu từ vị trí cuối tại thời điểm xác định offset ban đầu.

Nếu group đã có offset hợp lệ cho một topic-partition, consumer tiếp tục theo offset đã commit; auto-offset-reset không tự reset mọi topic mỗi lần ứng dụng khởi động.

Với pattern subscription, điều này đặc biệt quan trọng vì topic mới có thể xuất hiện khi service đang chạy. Hãy chọn earliest hoặc latest theo yêu cầu nghiệp vụ: có cần đọc dữ liệu đã được ghi trước khi topic được phát hiện hay chỉ cần nhận event mới từ thời điểm bắt đầu.

## 8. Chọn pattern an toàn và tránh subscribe quá rộng

Pattern càng rộng, tập topic được đăng ký càng lớn. Ví dụ `.*` có thể khớp gần như mọi tên topic mà consumer nhìn thấy. Điều này dễ dẫn đến đọc nhầm topic không thuộc service.

Các rủi ro thường gặp:

- Consumer nhận cả topic retry hoặc dead-letter ngoài dự kiến.
- Listener cố deserialize payload có schema khác.
- Group được gán thêm nhiều partition làm tăng tải và lag.
- Quyền ACL không đủ với một số topic khớp pattern.
- Topic mới do service khác tạo vô tình lọt vào subscription.

Nên thiết kế topic naming convention có namespace riêng:

| Namespace | Mục đích |
| --- | --- |
| `orders.*` | Event đơn hàng |
| `payments.*` | Event thanh toán |
| `inventory.*` | Event kho |
| `orders.retry.*` | Topic retry của luồng đơn hàng |
| `orders.dlt` | Dead-letter topic của đơn hàng |

Ví dụ nếu listener chỉ cần event nghiệp vụ chính, dùng pattern rõ hơn:

~~~java
@KafkaListener(
    topicPattern = "^orders\\.(created|updated|cancelled)$",
    groupId = "order-projection"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Pattern này không khớp các topic như `orders.retry.1` hoặc `orders.dlt`. Nếu service cần đọc cả retry/DLT, hãy đăng ký chúng một cách chủ đích và thiết kế listener/error handling phù hợp.

Không nên dùng pattern tổng quát chỉ vì muốn tránh cập nhật danh sách topic. Pattern cần thể hiện ranh giới dữ liệu mà service được phép và có trách nhiệm xử lý.

## 9. Regex subscription và Kafka ACL

Regex trong `topicPattern` là biểu thức so khớp tên topic ở phía consumer. Nó không tự cấp quyền đọc các topic được khớp.

Trong cluster có ACL, principal của consumer cần quyền phù hợp để mô tả/đọc các topic và tham gia consumer group. Nếu pattern khớp topic mà principal không có quyền, consumer có thể gặp lỗi authorization khi truy cập topic đó.

Cần phân biệt hai cơ chế:

- `topicPattern` là Java regular expression dùng để xác định topic subscription.
- Kafka ACL có resource pattern type như literal hoặc prefixed; prefixed ACL dựa trên tiền tố tên resource, không phải Java regex.

Ví dụ, ACL dạng prefixed cho namespace `orders.` có thể phù hợp khi cấp quyền cho một nhóm topic cùng prefix. Tuy nhiên, cấu hình ACL phải do quản trị Kafka thực hiện và cần giới hạn theo nguyên tắc quyền tối thiểu.

Không nên coi việc regex chỉ khớp một prefix là đủ để bảo vệ dữ liệu. Quyền thực tế được broker kiểm tra theo principal và ACL; cần xác minh quyền với tất cả topic mà consumer sẽ đọc.

## 10. Nhiều topic cần cùng schema hay nhiều schema?

Một listener nhận nhiều topic qua pattern thường đơn giản nhất khi tất cả topic có chung event contract.

Ví dụ, `orders.created`, `orders.updated` và `orders.cancelled` đều chứa một kiểu envelope chung:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    String eventType,
    Instant occurredAt,
    JsonNode payload
) {}
~~~

Consumer có thể giải mã tất cả topic thành OrderEvent rồi dựa vào eventType hoặc topic để điều phối logic.

Nếu các topic có payload hoàn toàn khác nhau, cần thiết kế type mapping hoặc deserialization rõ ràng. Một JsonDeserializer mặc định về một lớp không thể tự hiểu mọi schema chỉ vì topic name khớp regex.

Các lựa chọn thường gặp:

1. Dùng envelope chung với payload có cấu trúc thống nhất.
2. Dùng type header/schema registry để xác định kiểu event theo contract.
3. Nhận ConsumerRecord hoặc byte[] rồi dispatch theo topic và schema đã đăng ký.
4. Tách thành nhiều @KafkaListener với pattern hẹp và ConsumerFactory/deserializer phù hợp.

Không nên gộp mọi topic vào một listener nếu điều đó làm mất ranh giới schema hoặc khiến logic xử lý chứa nhiều nhánh khó kiểm soát.

## 11. Cấu hình pattern qua application.yml

Để thay pattern theo môi trường mà không sửa Java source, có thể đặt biểu thức trong application.yml:

~~~yaml
app:
  kafka:
    consumer:
      order-topic-pattern: '^orders\.(created|updated|cancelled)$'
      group-id: order-projection
~~~

Listener tham chiếu property:

~~~java
@Component
@RequiredArgsConstructor
public class OrderEventListener {

    private final OrderProjection orderProjection;

    @KafkaListener(
        topicPattern = "${app.kafka.consumer.order-topic-pattern}",
        groupId = "${app.kafka.consumer.group-id}"
    )
    public void onOrderEvent(
            OrderEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {

        orderProjection.apply(topic, event);
    }
}
~~~

Cách này tách cấu hình subscription khỏi logic xử lý. Có thể dùng profile hoặc environment variable để cung cấp pattern khác nhau cho local, test và production.

Pattern thường được resolve khi listener endpoint/container được cấu hình. Thay đổi file cấu hình sau khi container đã khởi động không đồng nghĩa subscription đang chạy tự đổi theo. Nếu cần đổi pattern lúc runtime, cần có cơ chế quản lý lifecycle của listener container để dừng, cấu hình lại và khởi động lại một cách có kiểm soát.

## 12. Kiểm thử topicPattern

Kiểm thử nên xác nhận cả topic được khớp và topic không được khớp. Có thể chia thành:

- Unit test regex bằng Java Pattern để kiểm tra quy tắc đặt tên.
- Integration test với broker để xác nhận listener nhận record từ topic khớp.
- Kiểm tra topic không khớp không được listener xử lý.
- Kiểm tra topic mới được tạo sau khi listener chạy có thể được phát hiện.
- Kiểm tra rebalance và offset khi subscription thay đổi.
- Kiểm tra authorization với các topic trong namespace.

Ví dụ unit test cho regex:

~~~java
@Test
void orderPatternShouldMatchOnlySupportedTopics() {
    Pattern pattern = Pattern.compile(
        "^orders\\.(created|updated|cancelled)$"
    );

    assertThat(pattern.matcher("orders.created").matches()).isTrue();
    assertThat(pattern.matcher("orders.updated").matches()).isTrue();
    assertThat(pattern.matcher("orders.cancelled").matches()).isTrue();

    assertThat(pattern.matcher("orders.dlt").matches()).isFalse();
    assertThat(pattern.matcher("payments.created").matches()).isFalse();
}
~~~

Unit test trên chỉ kiểm tra cú pháp và quy tắc regex. Nó không kiểm tra Kafka consumer subscribe hoặc nhận record.

Integration test có thể dùng Embedded Kafka hoặc Testcontainers. Tạo hai topic, một topic khớp pattern và một topic không khớp; gửi record vào cả hai; xác nhận listener chỉ nhận record từ topic khớp. Khi kiểm tra topic mới, hãy tạo topic sau khi listener đã chạy và chờ bằng điều kiện/timeout thay vì sleep cố định.

Với topic discovery, test cần đủ thời gian để consumer refresh metadata và group hoàn thành rebalance. Thời gian này phụ thuộc cấu hình và môi trường test; không nên coi một mốc thời gian ngắn cố định là bảo đảm của Kafka.

## 13. Theo dõi consumer pattern subscription khi vận hành

Khi một listener subscribe nhiều topic, theo dõi trạng thái chỉ theo group ID có thể chưa đủ. Nên quan sát thêm topic và partition:

- Danh sách topic hiện được subscription khớp.
- Partition assignment theo consumer.
- Consumer lag theo từng topic-partition.
- Số lần rebalance và thời gian rebalance.
- Record rate và processing latency theo topic.
- Lỗi deserialization, authorization và listener theo topic.
- Số topic mới được phát hiện và thay đổi subscription.

Trong log listener, nên ghi topic, partition, offset và event ID. Nếu nhiều topic dùng chung listener, các trường này giúp xác định nguồn dữ liệu và tránh nhầm offset giữa topic khác nhau.

Một pattern rộng có thể làm consumer group bất ngờ nhận thêm partition khi một team khác tạo topic mới. Vì vậy, namespace và quy trình tạo topic là một phần của hợp đồng vận hành giữa các service.

## 14. Các lỗi và nhầm lẫn thường gặp

| Triệu chứng hoặc nhầm lẫn | Nguyên nhân/cách hiểu chính xác |
| --- | --- |
| Listener không nhận topic mong muốn | Regex sai, topic chưa tồn tại, metadata chưa refresh hoặc group không được gán partition. |
| Listener nhận cả topic không mong muốn | Pattern quá rộng hoặc thiếu anchor/nhánh loại trừ. |
| Dùng `topics` và `topicPattern` cùng lúc | Đây là các chế độ subscription khác nhau; hãy chọn một chế độ phù hợp cho listener. |
| Topic mới không được nhận ngay | Consumer cần phát hiện qua metadata refresh và group có thể phải rebalance. |
| Regex tự tạo topic | Regex chỉ xác định subscription; topic creation thuộc KafkaAdmin/broker provisioning. |
| Regex lọc record theo value | Regex so khớp tên topic, không so khớp key, payload hay header. |
| Mọi consumer trong group đều nhận mọi record | Trong cùng group, consumer chia nhau partition; mỗi group độc lập có tiến độ riêng. |
| Offset của các topic có thể so sánh trực tiếp | Offset chỉ có ý nghĩa trong từng topic-partition. |
| Regex cấp quyền đọc topic | ACL do broker kiểm tra; regex subscription không cấp quyền. |
| Một listener nhận nhiều schema sẽ tự deserialize đúng | Cần contract, type mapping hoặc deserializer hỗ trợ các kiểu payload. |
| Pattern khớp topic DLT/retry ngoài ý muốn | Namespace rộng có thể bao gồm topic phụ trợ; cần giới hạn pattern. |

## 15. Checklist thiết kế topicPattern

Trước khi dùng regex subscription, hãy kiểm tra:

1. Các topic có chung quy ước tên và thuộc cùng ranh giới nghiệp vụ không?
2. Pattern có anchor và escape dấu chấm literal đúng không?
3. Pattern có vô tình khớp topic retry, DLT hoặc topic nội bộ không?
4. Tất cả topic khớp có schema tương thích với listener không?
5. Consumer group có đúng group ID và offset policy không?
6. Consumer principal có ACL phù hợp trên mọi topic cần đọc không?
7. Quy trình tạo topic mới có được quản lý và kiểm soát không?
8. Hệ thống có chấp nhận rebalance khi tập topic thay đổi không?
9. Có metric/log theo topic-partition để quan sát lag và lỗi không?
10. Integration test đã xác nhận topic khớp, topic không khớp và topic mới được phát hiện chưa?

Subscribe theo regular expression giúp một consumer quản lý tập topic có quy ước tên chung mà không phải cập nhật danh sách topic cố định mỗi lần có topic mới. Để dùng an toàn, pattern phải giới hạn đúng namespace, các topic phải có contract mà listener xử lý được, và hệ thống cần tính đến metadata refresh, rebalance, offset cùng ACL. Regex là công cụ chọn nguồn topic; consumer group và partition vẫn quyết định cách record được phân phối và xử lý.

