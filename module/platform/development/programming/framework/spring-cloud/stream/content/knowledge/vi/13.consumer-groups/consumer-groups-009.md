# Thực nghiệm phân phối thông điệp giữa nhiều nhóm

Trong Spring Cloud Stream, một destination có thể phục vụ nhiều nhóm tiêu thụ. Mỗi nhóm có mục đích riêng, chẳng hạn cập nhật tồn kho, gửi thông báo và tổng hợp doanh thu. Cách đặt consumer group quyết định thông điệp được chia cho nhiều instance cùng làm một công việc hay được chuyển tới nhiều nhóm để mỗi nhóm thực hiện một công việc độc lập.

Bài thực hành này dùng cùng một luồng `orders.placed` để kiểm chứng hai hành vi:

- **Nhiều group khác nhau:** mỗi group nhận toàn bộ luồng sự kiện để thực hiện một nhiệm vụ riêng.
- **Nhiều instance cùng group:** các instance chia sẻ công việc; một message được giao cho một consumer trong group theo cơ chế của broker.

Cần phân biệt group với instance. Tên group biểu diễn một luồng tiêu thụ logic; instance là một tiến trình đang tham gia group đó. Thay đổi tên group có thể làm thay đổi hành vi phân phối và vị trí đọc, vì vậy group cần được đặt tên có chủ đích.

## 1. Mô hình phân phối cần quan sát

Giả sử service đơn hàng phát các event tới destination `orders.placed`. Ba nhóm downstream có trách nhiệm khác nhau:

- `inventory-v1`: cập nhật tồn kho.
- `notifications-v1`: gửi thông báo cho khách hàng.
- `sales-analytics-v1`: cập nhật số liệu bán hàng.

~~~text
                         orders.placed
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
        Group inventory   Group notifications  Group analytics
             |                 |                 |
        +----+----+       +----+----+        +----+----+
        |         |       |         |        |         |
      App A     App B    App A     App B     App A     App B
      (same     (same    (same     (same     (same     (same
       group)    group)   group)    group)    group)    group)
~~~

Mỗi group là một luồng tiêu thụ độc lập. Khi một event được publish tới destination, mỗi group có cơ hội nhận event đó. Bên trong từng group, broker phân phối công việc cho các consumer member của group.

| Cách cấu hình | Kết quả mong đợi |
|---|---|
| Ba binding có cùng destination, ba group khác nhau | Mỗi group nhận các event của destination |
| Hai instance cùng destination và cùng group | Hai instance chia sẻ công việc của group |
| Hai instance cùng destination nhưng group khác nhau | Mỗi instance/group nhận luồng riêng; có thể xử lý cùng một event |
| Mỗi instance dùng group ẩn danh riêng | Các instance thường hoạt động như những nhóm độc lập, không chia sẻ cùng một tiến trình tiêu thụ bền vững |

Điều này không có nghĩa broker luôn giao message đúng một lần end-to-end. Khi consumer xử lý xong nhưng chưa xác nhận hoặc commit offset, message có thể được giao lại. Vì vậy, consumer vẫn cần xử lý idempotent dựa trên event ID hoặc khóa nghiệp vụ.

## 2. Chuẩn bị event và các consumer

Dùng một event đơn giản để mọi nhóm cùng nhận:

~~~java
import java.math.BigDecimal;

public record OrderPlaced(
    String eventId,
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}
~~~

Tạo ba bean `Consumer<OrderPlaced>`. Mỗi bean chỉ đại diện cho một nhiệm vụ:

~~~java
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderGroupConsumers {

    private static final Logger log =
        LoggerFactory.getLogger(OrderGroupConsumers.class);

    @Bean
    Consumer<OrderPlaced> inventoryProjection() {
        return event -> log.info(
            "INVENTORY eventId={} orderId={}",
            event.eventId(),
            event.orderId()
        );
    }

    @Bean
    Consumer<OrderPlaced> notificationSender() {
        return event -> log.info(
            "NOTIFICATION eventId={} customerId={}",
            event.eventId(),
            event.customerId()
        );
    }

    @Bean
    Consumer<OrderPlaced> salesAnalytics() {
        return event -> log.info(
            "ANALYTICS eventId={} total={} currency={}",
            event.eventId(),
            event.total(),
            event.currency()
        );
    }
}
~~~

Trong ứng dụng thực tế, thay log bằng các thao tác nghiệp vụ tương ứng. Không để một consumer thực hiện tất cả nhiệm vụ nếu các nhiệm vụ có vòng đời triển khai, yêu cầu mở rộng hoặc chính sách lỗi khác nhau. Tách consumer giúp mỗi nhóm có thể được mở rộng và vận hành độc lập.

Với ba bean trên, Spring Cloud Function nhận diện ba function theo tên bean. Spring Cloud Stream tạo input binding:

| Bean | Input binding |
|---|---|
| `inventoryProjection` | `inventoryProjection-in-0` |
| `notificationSender` | `notificationSender-in-0` |
| `salesAnalytics` | `salesAnalytics-in-0` |

## 3. Cấu hình ba group cùng đọc một destination

Ví dụ dưới đây dùng Kafka binder. Ba binding cùng trỏ tới topic `orders.placed`, nhưng mỗi binding có group riêng:

~~~yaml
spring:
  application:
    name: order-group-lab

  cloud:
    function:
      definition: "inventoryProjection;notificationSender;salesAnalytics"

    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.placed
          group: inventory-v1
          content-type: application/json

        notificationSender-in-0:
          destination: orders.placed
          group: notifications-v1
          content-type: application/json

        salesAnalytics-in-0:
          destination: orders.placed
          group: sales-analytics-v1
          content-type: application/json

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
        bindings:
          inventoryProjection-in-0:
            consumer:
              startOffset: earliest
          notificationSender-in-0:
            consumer:
              startOffset: earliest
          salesAnalytics-in-0:
            consumer:
              startOffset: earliest
~~~

Giải thích:

- `spring.cloud.function.definition` kích hoạt ba consumer độc lập. Dấu chấm phẩy phân tách các function.
- Cả ba input binding cùng có destination `orders.placed`.
- Mỗi binding có group riêng, do đó mỗi nhóm có tiến trình tiêu thụ riêng.
- `startOffset: earliest` yêu cầu Kafka binder bắt đầu từ offset sớm nhất khi group chưa có offset được commit. Nếu group đã có offset, consumer tiếp tục theo offset đã lưu; thuộc tính này không đặt lại offset hiện có.
- `KAFKA_BROKERS` cho phép thay địa chỉ broker theo môi trường.

Tên group nên ổn định giữa các lần deploy nếu muốn tiếp tục tiến trình tiêu thụ. Ví dụ, `inventory-v1` thể hiện nhóm xử lý tồn kho. Không tạo group mới cho mỗi lần khởi động nếu không chủ đích replay toàn bộ dữ liệu.

## 4. Khởi tạo Kafka và chạy thử fan-out giữa các group

Tạo topic với bốn partition để các bước mở rộng sau có thể quan sát việc phân phối trong group:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic orders.placed --partitions 4 --replication-factor 1
~~~

Với Kafka trên Windows, script có thể nằm trong `bin\windows` và dùng đuôi `.bat`, tùy bản phân phối.

Khởi động ứng dụng Spring Boot:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Mở terminal khác và gửi một số event vào topic:

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders.placed
~~~

Nhập từng JSON trên một dòng:

~~~json
{"eventId":"evt-001","orderId":"ord-1001","customerId":"cus-01","total":125000,"currency":"VND"}
{"eventId":"evt-002","orderId":"ord-1002","customerId":"cus-02","total":85000,"currency":"VND"}
{"eventId":"evt-003","orderId":"ord-1003","customerId":"cus-03","total":210000,"currency":"VND"}
~~~

Quan sát log ứng dụng. Với mỗi event ID, cần thấy một dòng `INVENTORY`, một dòng `NOTIFICATION` và một dòng `ANALYTICS`. Ví dụ:

~~~text
INVENTORY eventId=evt-001 orderId=ord-1001
NOTIFICATION eventId=evt-001 customerId=cus-01
ANALYTICS eventId=evt-001 total=125000 currency=VND
~~~

Thứ tự các dòng log có thể khác nhau vì các group tiêu thụ độc lập. Điều cần xác nhận là mỗi event đã được xử lý trong cả ba group. Không yêu cầu các group xử lý cùng thời điểm hoặc theo cùng thứ tự hoàn thành.

Có thể lập bảng kết quả:

| Event ID | inventory-v1 | notifications-v1 | sales-analytics-v1 |
|---|---|---|---|
| evt-001 | Có | Có | Có |
| evt-002 | Có | Có | Có |
| evt-003 | Có | Có | Có |

Nếu một group không nhận được event, kiểm tra function có được kích hoạt, tên binding, destination, group, kết nối broker và offset hiện tại. Nếu group đã tồn tại từ lần chạy trước, nó có thể đang đọc từ offset đã commit thay vì đọc lại các record cũ.

## 5. Thử nghiệm hai instance cùng một group

Sau khi xác nhận fan-out, hãy chạy hai instance của cùng ứng dụng. Giữ nguyên các group trong YAML và khởi động ứng dụng hai lần ở hai terminal hoặc hai tiến trình riêng.

~~~text
Instance A                         Instance B
    |                                  |
    +---------- inventory-v1 ----------+
    |                                  |
    +-------- notifications-v1 --------+
    |                                  |
    +------- sales-analytics-v1 --------+
~~~

Với mỗi group, hai instance tham gia cùng một consumer group. Kafka phân phối các partition giữa các consumer member. Mỗi record của một partition được xử lý bởi một member trong group tại một thời điểm bình thường; group khác vẫn có tiến trình đọc độc lập.

Gửi thêm nhiều event, ví dụ từ `evt-004` đến `evt-020`. Quan sát log của hai tiến trình:

- Các event trong cùng group được chia giữa instance A và B theo partition assignment.
- Tổng số event ID khác nhau được xử lý trong một group phải khớp với số event đã gửi, sau khi tính đến lỗi và redelivery.
- Cùng một event ID vẫn xuất hiện trong từng group logic: inventory, notification và analytics.
- Không kỳ vọng chia đều tuyệt đối giữa hai instance. Phân phối phụ thuộc số partition, key, tải và thời điểm rebalance.

Nếu topic chỉ có một partition, chỉ một consumer trong group có thể được gán partition đó tại một thời điểm. Instance còn lại có thể không xử lý record nào trong group đó. Vì vậy, số consumer hoạt động song song trong một Kafka group bị giới hạn bởi số partition được gán.

Đây là điểm khác biệt quan trọng giữa hai cách mở rộng:

- Thêm instance cùng group giúp chia công việc của một nhiệm vụ, trong giới hạn partition.
- Tạo group mới tạo thêm một luồng tiêu thụ độc lập, khiến group mới cũng đọc các event của destination.

Không đổi group ID khi chỉ muốn thêm instance. Nếu mỗi instance vô tình dùng group khác nhau, chúng sẽ nhận bản sao của luồng và có thể thực hiện cùng side effect nhiều lần.

## 6. Quan sát consumer group và lag của Kafka

Dùng lệnh sau để xem trạng thái một group:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group inventory-v1
~~~

Kết quả thường có các thông tin:

| Trường | Ý nghĩa |
|---|---|
| TOPIC | Topic mà group đang đọc |
| PARTITION | Partition được mô tả |
| CURRENT-OFFSET | Offset group đã commit |
| LOG-END-OFFSET | Offset cuối hiện có trên partition |
| LAG | Số record group còn chậm so với cuối log |
| CONSUMER-ID | Consumer member đang nhận partition |
| HOST | Máy chạy consumer |
| CLIENT-ID | Định danh client Kafka |

Chạy lệnh tương tự cho `notifications-v1` và `sales-analytics-v1`. Mỗi group có offset và lag riêng. Một group xử lý nhanh không có nghĩa các group khác cũng theo kịp.

Nếu lag tăng liên tục:

1. Kiểm tra tốc độ producer và tốc độ xử lý của consumer.
2. Xác định partition nào có lag cao.
3. Kiểm tra consumer có gọi dịch vụ ngoài chậm hoặc bị block không.
4. Kiểm tra số partition và số instance đang hoạt động.
5. Kiểm tra rebalance lặp lại, lỗi xử lý hoặc retry kéo dài.
6. Chỉ tăng instance khi có đủ partition và downstream còn khả năng chịu tải.

Không đưa event ID hoặc order ID vào metric label có cardinality cao. Dùng log và trace để tra cứu chi tiết từng event; metric nên dùng các nhãn có số lượng giá trị giới hạn như group, topic, kết quả và loại lỗi.

## 7. Thử nghiệm tạo group mới và đọc lại dữ liệu

Tạo một group mới, ví dụ `inventory-rebuild-v1`, để mô phỏng một consumer mới cần dựng read model từ lịch sử event.

Với Kafka, group mới chưa có offset được commit. Khi cấu hình `startOffset: earliest`, consumer có thể đọc từ đầu phần dữ liệu còn retention trên topic. Nếu dữ liệu cũ đã hết retention hoặc bị xóa, group không thể replay phần dữ liệu đó từ Kafka.

Khi tạo group mới, hãy quan sát:

- Group mới có offset riêng.
- Group cũ tiếp tục vị trí đọc hiện tại.
- Group mới không làm group cũ chuyển sang offset khác.
- Nếu dùng cùng tên group với một ứng dụng đã chạy, consumer mới tham gia group hiện hữu và chia sẻ tiến trình đọc thay vì tạo một bản sao độc lập.

Replay có thể làm consumer chạy lại side effect. Trước khi dựng lại read model, cần xác định thao tác nào được phép chạy lại, dùng database/schema đích riêng hay có cơ chế xóa và dựng lại dữ liệu, và event handler có idempotent hay không.

## 8. So sánh semantics giữa Kafka, RabbitMQ và Pulsar

Khái niệm group có ý nghĩa chung trong Spring Cloud Stream, nhưng binder ánh xạ nó sang cấu trúc của broker.

| Broker | Một group thường được ánh xạ thành | Nhiều group khác nhau | Nhiều instance cùng group |
|---|---|---|---|
| Kafka | Consumer group ID | Mỗi group có offset riêng và đọc topic độc lập | Các consumer chia partition |
| RabbitMQ | Queue gắn với exchange/destination | Mỗi group có queue riêng nhận bản sao được route | Các consumer cạnh tranh trên cùng queue |
| Pulsar | Subscription name | Mỗi subscription độc lập đọc topic | Consumer cùng subscription chia message theo subscription type |

### Kafka

Kafka lưu event trong topic và phân vùng thành partition. Mỗi consumer group duy trì offset riêng cho từng topic-partition. Nhiều group cùng đọc một topic không chia sẻ offset; mỗi group có thể đọc toàn bộ các partition theo tiến trình riêng.

Trong một group, Kafka gán mỗi partition cho tối đa một consumer member tại một thời điểm. Khi member gia nhập hoặc rời nhóm, Kafka có thể rebalance và phân phối lại partition. Rebalance làm thay đổi assignment và có thể tạm dừng xử lý trong thời gian ngắn.

Thứ tự được bảo đảm trong phạm vi một partition. Nếu các event của cùng một đơn hàng cần giữ thứ tự, producer nên dùng order ID làm key để các event cùng key được đưa vào cùng partition. Không có thứ tự toàn cục giữa các partition.

### RabbitMQ

Rabbit binder ánh xạ destination tới exchange và group tới queue tiêu thụ. Các group khác nhau có queue riêng được bind vào exchange, vì vậy mỗi queue nhận bản sao message theo routing rule. Nhiều consumer trong cùng group cùng đọc một queue và cạnh tranh nhận message.

Queue là nơi lưu backlog của từng nhóm. Nếu consumer của nhóm notification chậm, queue của nhóm đó có thể tăng trong khi nhóm inventory vẫn xử lý bình thường. Đây là lý do mỗi group cần được quan sát riêng.

Khi không cấu hình group, binder có thể tạo queue ẩn danh/độc lập theo cấu hình. Với consumer cần tiến trình bền vững qua restart, nên khai báo group ổn định và kiểm tra tên queue, durability, binding cùng chính sách dead-letter trong RabbitMQ.

### Apache Pulsar

Pulsar sử dụng subscription để quản lý tiến trình tiêu thụ topic. Trong Spring Cloud Stream Pulsar binder, group được dùng để xác định subscription theo quy tắc binder và phiên bản. Các subscription khác nhau nhận luồng event độc lập; nhiều consumer cùng subscription chia sẻ công việc theo subscription type.

Các subscription type thường gặp:

| Subscription type | Hành vi |
|---|---|
| Exclusive | Một consumer hoạt động trên subscription |
| Failover | Một consumer active; consumer khác làm standby |
| Shared | Nhiều consumer chia sẻ message; thứ tự toàn cục không được bảo đảm |
| Key_Shared | Nhiều consumer chia message theo key; cùng key được giữ trên một consumer theo semantics của Pulsar |

Nếu nghiệp vụ yêu cầu thứ tự theo order ID, hãy chọn subscription type và message key phù hợp, rồi kiểm thử với binder version đang dùng. Tên thuộc tính cấu hình subscription type nằm trong phần extended consumer properties của Pulsar binder; không dùng thuộc tính Kafka hoặc RabbitMQ thay thế.

## 9. Cách đọc kết quả khi thử trên từng broker

Một phép thử fan-out đúng cần xác nhận mỗi group nhận event độc lập. Một phép thử scale-out đúng cần xác nhận nhiều instance cùng group chia sẻ công việc.

| Quan sát | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Group/subscription mới | Offset group mới | Queue mới được tạo và bind | Subscription mới |
| Hai instance cùng group | Chia partition | Cạnh tranh trên cùng queue | Chia message theo subscription type |
| Theo dõi backlog | Consumer lag theo partition | Ready/unacknowledged trên queue | Backlog theo subscription |
| Thay đổi member | Rebalance | Consumer registration/cancel | Consumer attach/detach và phân phối lại |
| Replay | Offset reset hoặc group mới | Phụ thuộc queue durability và message còn tồn tại | Subscription cursor/position |

Không áp dụng lệnh quản trị của Kafka cho RabbitMQ hoặc Pulsar. Hãy quan sát bằng công cụ quản trị tương ứng: Kafka consumer group command, RabbitMQ Management UI/CLI và Pulsar Admin. Cấu hình và khả năng cụ thể phụ thuộc phiên bản broker và binder.

## 10. Xử lý lỗi, redelivery và tính idempotent

Phân phối một message tới group không đồng nghĩa với việc side effect chỉ xảy ra đúng một lần. Ví dụ consumer cập nhật database thành công nhưng bị dừng trước khi acknowledgment hoặc offset commit hoàn tất. Broker có thể giao lại message.

Consumer cần dùng event ID hoặc khóa nghiệp vụ để chống xử lý trùng. Với side effect trong cùng database, có thể lưu dấu event đã xử lý trong cùng transaction với thay đổi dữ liệu:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(200) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa có `consumer_name` để cùng một event có thể được xử lý độc lập bởi inventory, notification và analytics. Nếu dùng một bảng deduplication chung mà không phân biệt consumer, việc inventory đã xử lý có thể khiến notification bị bỏ qua ngoài ý muốn.

Luồng xử lý khái quát:

~~~text
Nhận event
   |
   v
Thử ghi (consumer_name, eventId)
   |
   +---- Đã tồn tại ----> Không lặp side effect
   |
   +---- Ghi mới -------> Thực hiện nghiệp vụ
                            |
                            v
                         Commit
~~~

Nếu side effect nằm ngoài database như gọi cổng thanh toán hoặc gửi email, cần idempotency key hoặc cơ chế đối soát của dịch vụ đích. Việc chỉ lưu event ID trong database không thể tự hoàn tác một request bên ngoài đã thành công.

Mỗi group có chính sách retry và DLQ riêng theo binder. Một group bị lỗi không nên khiến các group khác dừng xử lý nếu broker và cấu hình đã tách backlog độc lập. Tuy vậy, producer, broker và consumer vẫn có thể chia sẻ tài nguyên vật lý, nên sự cố quá tải broker có thể ảnh hưởng nhiều group.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng group khác nhau cho các replica của cùng một service | Mỗi replica nhận toàn bộ luồng và có thể lặp side effect | Dùng cùng group ID cho các replica của một nhiệm vụ |
| Dùng chung group cho hai nhiệm vụ nghiệp vụ khác nhau | Các nhiệm vụ cạnh tranh message; mỗi event chỉ đến một nhiệm vụ | Tạo group riêng cho từng nhiệm vụ cần nhận đầy đủ event |
| Đổi group ID khi deploy mà không có kế hoạch | Tạo tiến trình đọc mới, có thể replay hoặc bỏ qua dữ liệu theo offset policy | Giữ group ổn định hoặc lập kế hoạch migration/replay |
| Tăng instance nhưng không tăng partition Kafka | Consumer dư không có partition để xử lý | Đánh giá partition count và throughput |
| Cho rằng mỗi group xử lý đồng thời hoặc cùng thứ tự | Kết quả và thời điểm log khác nhau | Thiết kế theo semantics của từng broker |
| Cho rằng message chỉ được xử lý đúng một lần | Redelivery có thể lặp side effect | Idempotency và deduplication |
| Dùng group ẩn danh cho consumer cần lưu offset | Tiến trình tiêu thụ không được chia sẻ ổn định | Đặt group rõ ràng |
| Dùng metric label là event ID | Cardinality tăng rất lớn | Dùng log/trace cho định danh chi tiết |

## 12. Bài thực hành tổng hợp

Thực hiện lần lượt để quan sát cả fan-out và load balancing:

1. Tạo topic `orders.placed` với ít nhất bốn partition.
2. Chạy ứng dụng có ba consumer function và ba group khác nhau.
3. Gửi ít nhất năm event với event ID riêng biệt.
4. Xác nhận mỗi event ID xuất hiện trong log của cả ba nhóm.
5. Khởi động thêm một instance với cùng cấu hình và cùng group ID.
6. Gửi thêm từ mười đến hai mươi event; xác nhận hai instance chia tải trong từng group.
7. Dùng lệnh `kafka-consumer-groups --describe` để quan sát partition assignment và lag.
8. Tạo group mới với `startOffset: earliest`; quan sát group mới đọc lại phần dữ liệu còn retention.
9. Dừng một instance khi đang có tải; quan sát rebalance và quá trình consumer còn lại tiếp tục.
10. Mô phỏng consumer xử lý xong nhưng bị dừng trước commit; xác nhận idempotency ngăn side effect lặp.
11. Thực hiện lại fan-out trên RabbitMQ hoặc Pulsar và đối chiếu queue/subscription semantics.

### Tiêu chí hoàn thành

Người học hoàn thành khi có thể:

- Giải thích vì sao các group khác nhau đều nhận event của cùng destination.
- Giải thích vì sao các instance cùng group chia sẻ công việc.
- Cấu hình nhiều consumer function với destination chung và group riêng.
- Chạy hai instance với cùng group ID mà không tạo bản sao xử lý ngoài ý muốn.
- Quan sát offset, lag, queue backlog hoặc subscription backlog theo từng group.
- Giải thích giới hạn partition, rebalance và thứ tự message.
- Thiết kế idempotency phù hợp với redelivery và side effect.
- Nêu được khác biệt giữa Kafka consumer group, RabbitMQ queue group và Pulsar subscription.

## 13. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) — ý nghĩa group và cách Spring Cloud Stream ánh xạ consumer.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — tên input binding theo tên function.
- [Spring Cloud Stream — Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — cấu hình Kafka binder.
- [Apache Kafka — Consumer groups](https://kafka.apache.org/documentation/#intro_consumers) — group membership, partition assignment và offset.
- [Spring Cloud Stream — RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — destination, exchange, queue và group.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers) — competing consumers và acknowledgment.
- [Spring Cloud Stream — Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — cấu hình Pulsar binder.
- [Apache Pulsar — Messaging concepts](https://pulsar.apache.org/docs/concepts-messaging/) — subscription, consumer và message distribution.

