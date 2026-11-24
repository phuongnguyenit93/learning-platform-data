# Phân biệt cấu hình dùng chung với khả năng riêng của từng binder

Spring Cloud Stream cung cấp một mô hình lập trình thống nhất cho ứng dụng xử lý sự kiện. Ta khai báo Supplier, Function hoặc Consumer, nối các đầu vào và đầu ra với destination bằng binding, rồi chọn binder để kết nối với Kafka, RabbitMQ, Pulsar hoặc hệ thống truyền tin khác. Nhờ vậy, phần lớn logic nghiệp vụ không cần phụ thuộc trực tiếp vào API của broker.

Tuy nhiên, mô hình thống nhất không có nghĩa mọi broker có cùng tính năng hoặc cùng cách cấu hình. Một số thuộc tính mô tả ý định chung của ứng dụng, chẳng hạn destination, consumer group và content type. Những thuộc tính khác điều khiển hành vi đặc thù, chẳng hạn offset của Kafka, routing key của RabbitMQ hoặc subscription type của Pulsar. Thiết kế kiến trúc tốt cần nhận diện ranh giới này để giữ phần cấu hình có thể tái sử dụng, đồng thời khai thác đúng khả năng của broker.

## 1. Ba lớp cấu hình trong Spring Cloud Stream

Có thể chia cấu hình thành ba lớp:

1. **Cấu hình hàm và binding:** chọn hàm cần kích hoạt, xác định đầu vào/đầu ra, destination, group và định dạng message. Đây là lớp ứng dụng nhìn thấy.
2. **Cấu hình chung của binding:** điều chỉnh những hành vi mà Spring Cloud Stream định nghĩa ở mức trừu tượng, ví dụ số lần thử lại, khoảng chờ, partition key hoặc nhóm consumer mặc định.
3. **Cấu hình riêng của binder:** điều khiển tính năng của broker cụ thể, ví dụ Kafka offset và DLQ, RabbitMQ exchange và queue, hoặc Pulsar subscription và redelivery.

Sơ đồ dưới đây thể hiện ranh giới trách nhiệm:

~~~text
Logic nghiệp vụ
 Supplier / Function / Consumer
             |
             v
Cấu hình Spring Cloud Stream
 function definition, binding, destination, group
             |
             v
Thuộc tính chung của binding
 retry, backoff, partition key, content type
             |
             v
Binder được chọn
 Kafka binder | Rabbit binder | Pulsar binder
             |
             v
Broker và tài nguyên vật lý
 topic/partition | exchange/queue | topic/subscription
~~~

Lớp trên mô tả điều ứng dụng muốn làm. Binder chuyển yêu cầu đó thành thao tác tương ứng của broker. Khi cần một tính năng không có trong hợp đồng chung, cấu hình phải đi qua lớp riêng của binder hoặc thông qua API chuyên biệt.

## 2. Cấu hình dùng chung ở cấp ứng dụng

Các thuộc tính trong nhóm spring.cloud.function và spring.cloud.stream.bindings là điểm bắt đầu tốt cho một ứng dụng có khả năng thay đổi broker.

Ví dụ, một Function xử lý sự kiện đơn hàng:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConfiguration {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(
                event.orderId(),
                event.customerId(),
                "ACCEPTED");
    }
}

record OrderCreated(String orderId, String customerId) {}

record OrderAccepted(String orderId, String customerId, String status) {}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-acceptance
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Các thuộc tính trên diễn tả những khái niệm chung:

- **definition:** bean hàm mà ứng dụng muốn kích hoạt.
- **destination:** tên logic của luồng đầu vào hoặc đầu ra.
- **group:** nhóm consumer có chung mục tiêu xử lý và tiến độ nhận.
- **content-type:** định dạng payload mà message converter sử dụng.

Tên binding được tạo từ tên hàm và hướng dữ liệu. Với Function một đầu vào và một đầu ra, hậu tố thường là in-0 và out-0. Khi cấu hình, phải dùng đúng tên binding được tạo ra; destination là tên luồng, không phải tên binding.

Các thuộc tính chung không tự quyết định cách broker lưu dữ liệu. Ví dụ, destination orders.created có thể trở thành topic Kafka, exchange RabbitMQ hoặc topic Pulsar. Group order-acceptance có thể trở thành consumer group, queue gắn với exchange hoặc subscription. Cần hiểu ánh xạ của binder trước khi suy luận về độ bền, thứ tự và cách phân phối.

## 3. Giá trị mặc định và cấu hình theo từng binding

Spring Cloud Stream cho phép đặt mặc định cho các binding rồi ghi đè ở một binding cụ thể. Cách này hữu ích khi nhiều luồng có cùng chính sách nhưng một luồng cần cấu hình riêng.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      default:
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-max-interval: 10000
          back-off-multiplier: 2.0
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-service
        auditPayment-in-0:
          destination: payments.requested
          group: payment-service
          consumer:
            max-attempts: 5
            back-off-initial-interval: 2000
~~~

Giả sử ứng dụng có hai binding đầu vào acceptOrder-in-0 và auditPayment-in-0. Cả hai dùng chính sách retry mặc định ba lần, còn auditPayment-in-0 ghi đè số lần thử và khoảng chờ ban đầu. Cú pháp và thuộc tính cụ thể cần được đối chiếu với phiên bản Spring Cloud Stream mà dự án đang dùng.

Đặt mặc định giúp cấu hình nhất quán, nhưng không nên áp dụng một chính sách retry cho mọi loại lỗi. Lỗi tạm thời như timeout có thể thử lại; lỗi dữ liệu sai định dạng hoặc vi phạm quy tắc nghiệp vụ thường cần cách ly sớm. Cần xem thêm khả năng retry, dead-letter và xác nhận của binder để biết chính sách chung được thực thi ra sao.

## 4. Những gì thuộc về Kafka binder

Kafka lưu message thành record trong topic được chia thành partition. Consumer group giữ offset riêng để theo dõi tiến độ; các consumer trong cùng group chia nhau partition. Những khái niệm này không có bản tương đương hoàn toàn trong mọi broker.

Ví dụ cấu hình chung cho binding và một số thuộc tính riêng của Kafka:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders.created
          group: inventory-service
      kafka:
        binder:
          brokers: localhost:9092
        bindings:
          inventory-in-0:
            consumer:
              start-offset: earliest
              enable-dlq: true
              dlq-name: orders.created.inventory.dlq
~~~

Trong cấu hình này:

- Binding inventory-in-0, destination và group thuộc lớp Spring Cloud Stream.
- brokers xác định cụm Kafka mà binder kết nối.
- start-offset điều khiển vị trí bắt đầu đọc trong những trường hợp áp dụng.
- enable-dlq và dlq-name là khả năng riêng của Kafka binder.

Kafka binder còn có thể cấu hình hành vi commit offset, acknowledgement mode, xử lý transaction, chọn partition và thuộc tính client Kafka. Các lựa chọn này ảnh hưởng trực tiếp đến giao nhận và thứ tự. Ví dụ, commit offset trước khi side effect hoàn tất có thể khiến ứng dụng không xử lý lại record sau sự cố; commit sau khi hoàn tất có thể dẫn đến xử lý lặp nếu tiến trình dừng trước lúc commit. Consumer vì thế vẫn cần idempotency.

Kafka có thể dùng key để đưa các record liên quan vào cùng partition. Với sự kiện đơn hàng, key có thể là orderId để giữ thứ tự trong phạm vi partition đó. Nếu cần cấu hình cách chọn key, có thể dùng thuộc tính chung về partitioning hoặc biểu thức message key riêng của Kafka binder, tùy mục đích và phiên bản. Không nên vừa cấu hình hai cơ chế chọn partition khác nhau vừa kỳ vọng chúng có cùng kết quả.

DLQ của Kafka binder thường liên quan đến consumer group và partition gốc. Cần kiểm tra số partition, quyền tạo topic, tên DLQ, cách giữ metadata và cách phát lại. Bật một thuộc tính DLQ không thay thế quy trình vận hành: đội phát triển vẫn cần theo dõi topic lỗi, xác định nguyên nhân và quyết định có thể phát lại hay phải sửa dữ liệu.

## 5. Những gì thuộc về RabbitMQ binder

RabbitMQ thường định tuyến message qua exchange đến một hoặc nhiều queue. Consumer group của Spring Cloud Stream được ánh xạ vào queue của nhóm; nhiều instance trong cùng group cạnh tranh đọc queue đó. Exchange type và routing key quyết định queue nào nhận được message.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        billing-in-0:
          destination: orders.events
          group: billing-service
      rabbit:
        bindings:
          billing-in-0:
            consumer:
              acknowledge-mode: AUTO
              prefetch: 20
              auto-bind-dlq: true
              dead-letter-queue-name: orders.events.billing.dlq
~~~

Binding destination và group mô tả luồng logic. Các thuộc tính dưới spring.cloud.stream.rabbit.bindings điều khiển cách Rabbit binder tạo queue, xác nhận message và cấu hình dead-letter. Ví dụ prefetch giới hạn số message chưa được xác nhận mà broker có thể giao cho consumer; giá trị phù hợp phụ thuộc vào thời gian xử lý, dung lượng message và khả năng của ứng dụng.

Một số khả năng riêng khác của Rabbit binder gồm:

- Chọn exchange type như direct, topic, fanout hoặc headers.
- Định tuyến bằng routing key hoặc biểu thức routing key.
- Cấu hình queue bền vững, exclusive, TTL và dead-letter exchange.
- Chọn acknowledgement mode, prefetch và concurrency.
- Xử lý message bị từ chối, requeue hoặc phát lại thông tin lỗi vào DLQ.

Ví dụ producer có thể cần routing key theo loại sự kiện hoặc loại khách hàng. Đây là ý niệm gắn với cơ chế định tuyến của RabbitMQ; không nên đưa routing key vào cấu hình chung của ứng dụng nếu luồng đó có thể chạy trên broker không hỗ trợ cùng ngữ nghĩa.

RabbitMQ queue và exchange có vòng đời riêng. Khi đổi tên destination hoặc group, binder có thể tạo tài nguyên mới trong khi queue cũ vẫn còn. Trước khi xóa hoặc đổi tài nguyên, cần kiểm tra binding, queue, message đang tồn đọng và chính sách lưu giữ để tránh mất công việc chưa xử lý.

## 6. Những gì thuộc về Pulsar binder

Pulsar tổ chức message theo topic và consumer đọc thông qua subscription. Subscription lưu cursor và quyết định cách một hoặc nhiều consumer phối hợp. Các kiểu subscription phổ biến gồm:

- **Exclusive:** một consumer hoạt động trên subscription.
- **Failover:** một consumer chính xử lý; consumer dự phòng tiếp quản khi cần.
- **Shared:** nhiều consumer cùng chia sẻ message.
- **Key_Shared:** message được phân phối theo khóa để giữ các message cùng khóa trên cùng consumer theo cơ chế của Pulsar.

Những lựa chọn này ảnh hưởng đến khả năng song song, thứ tự và failover. Chúng không thể được thay thế chỉ bằng một giá trị group chung. Trong Spring Cloud Stream, group thường cung cấp tên nhóm/subscription logic, còn loại subscription là thuộc tính riêng của Pulsar binder.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        shipment-in-0:
          destination: persistent://public/default/orders.created
          group: shipment-service
      pulsar:
        bindings:
          shipment-in-0:
            consumer:
              subscription-type: Shared
~~~

Đây là cách minh họa ranh giới giữa binding chung và subscription type riêng. Tên thuộc tính, kiểu giá trị và namespace cấu hình Pulsar có thể thay đổi theo phiên bản binder. Trước khi sử dụng, kiểm tra tài liệu đúng phiên bản để xác nhận cú pháp, mặc định và khả năng hỗ trợ.

Pulsar binder còn có thể cung cấp tùy chọn schema, batching, nén, timeout xác nhận, negative acknowledgement và dead-letter policy. Các thuộc tính đó tác động đến cách message được mã hóa, gửi, xác nhận hoặc giao lại. Khi dùng schema của Pulsar, cần thống nhất schema type và chính sách tương thích giữa producer và consumer.

## 7. So sánh ranh giới cấu hình

| Nhu cầu | Cấu hình chung | Phần phụ thuộc binder |
|---|---|---|
| Chọn hàm xử lý | function definition | Không cần nếu dùng mô hình hàm chuẩn |
| Nối hàm với luồng | binding và destination | Destination ánh xạ thành topic, exchange hoặc topic/subscription |
| Nhóm consumer | group | Consumer group Kafka, queue RabbitMQ hoặc subscription Pulsar |
| Định dạng payload | content type và message converter | Native encoding, schema registry hoặc schema type theo broker |
| Retry | max attempts và backoff của binding | Cơ chế redelivery, ack, offset hoặc negative acknowledgement |
| Dead-letter | Ý định cách ly message lỗi | Tên topic DLQ, dead-letter exchange/queue hoặc dead-letter topic |
| Chia tải | Consumer group và partitioning ở mức trừu tượng | Kafka partition assignment, RabbitMQ queue/prefetch, Pulsar subscription type |
| Thứ tự | Có thể xác định key và yêu cầu nghiệp vụ | Kafka partition, RabbitMQ routing/consumer, Pulsar subscription/key |
| Giao dịch | Một số abstraction và transaction manager | Phạm vi transaction và bảo đảm cụ thể của từng broker |

Bảng này mô tả ranh giới thiết kế, không khẳng định các tính năng có cùng mức bảo đảm. Ví dụ, một thuộc tính retry chung có thể yêu cầu binder thực hiện giao lại theo cách khác nhau. Một DLQ trên Kafka là topic; trong RabbitMQ thường là queue được định tuyến qua dead-letter exchange; trong Pulsar là topic đích theo dead-letter policy.

## 8. Cấu hình nhiều binder trong cùng ứng dụng

Một ứng dụng có thể kết nối nhiều hệ thống truyền tin. Ví dụ, sự kiện nghiệp vụ được phát lên Kafka để phân tích, trong khi lệnh gửi thông báo được đưa vào RabbitMQ để xử lý tác vụ. Mỗi binding có thể chọn binder cụ thể.

Ví dụ cấu hình khái niệm:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        analytics-kafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: localhost:9092
        notification-rabbit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: localhost
                port: 5672
      bindings:
        analytics-out-0:
          destination: order.analytics
          binder: analytics-kafka
        notification-out-0:
          destination: notification.commands
          binder: notification-rabbit
~~~

Tên binder ở đây là bí danh do ứng dụng đặt. Thuộc tính type chọn loại binder, còn environment chứa cấu hình dành cho binder đó. Cú pháp kết nối cụ thể phụ thuộc binder và phiên bản; có thể dùng cấu hình kết nối Spring Boot hoặc namespace riêng của binder theo tài liệu tương ứng.

Không nên đưa mọi thuộc tính broker vào một khối cấu hình toàn cục khi ứng dụng dùng nhiều binder. Nếu một thuộc tính chỉ có ý nghĩa với Kafka, đặt nó dưới namespace Kafka và gắn với binding Kafka. Làm tương tự với RabbitMQ và Pulsar. Cách tổ chức này giúp tránh việc một binding vô tình nhận thuộc tính không liên quan.

Khi dùng nhiều binder, cần cân nhắc việc truyền message giữa các broker. Một transaction cục bộ trên Kafka không tự bao trùm thao tác gửi sang RabbitMQ. Nếu ứng dụng đọc từ broker này rồi ghi sang broker khác, có thể cần outbox, inbox, idempotency hoặc một quy trình bù trừ để xử lý trường hợp một bước thành công còn bước kia thất bại.

## 9. Giữ cấu hình có thể chuyển đổi

Không phải mọi ứng dụng đều cần hỗ trợ nhiều broker. Tuy nhiên, ngay cả khi đã chọn một broker, việc phân biệt cấu hình chung và cấu hình riêng vẫn giúp mã nguồn rõ ràng, kiểm thử dễ hơn và tránh phụ thuộc ngầm.

Một số nguyên tắc tổ chức:

1. Đặt function definition, binding, destination, group và content type trong phần cấu hình chung của ứng dụng.
2. Đặt thuộc tính đặc thù dưới namespace của binder tương ứng và gần binding chịu ảnh hưởng.
3. Dùng profile theo môi trường để thay địa chỉ broker, thông tin xác thực, TLS và tên tài nguyên; không sao chép toàn bộ logic binding giữa các profile nếu không cần.
4. Tập trung các quyết định về partition, routing key, subscription type và DLQ vào tài liệu kiến trúc của luồng sự kiện.
5. Ghi rõ thuộc tính nào là bắt buộc, thuộc tính nào là mặc định và thuộc tính nào chỉ dùng cho một broker.
6. Kiểm thử cấu hình khởi động và hành vi thực tế với từng binder được hỗ trợ.

Có thể dùng file cấu hình riêng theo profile, ví dụ application-kafka.yml và application-rabbit.yml. Chỉ bật profile phù hợp trong từng môi trường. Khi hai profile cần cùng một logic nghiệp vụ, giữ tên hàm và hợp đồng message ổn định; chỉ thay các thuộc tính ánh xạ và thuộc tính đặc thù.

## 10. Cách quyết định một thuộc tính nên đặt ở đâu

Khi gặp một thuộc tính mới, hãy trả lời lần lượt:

- Thuộc tính này mô tả yêu cầu nghiệp vụ hay một chi tiết của broker?
- Nó có ý nghĩa tương đương trên nhiều binder hay chỉ tồn tại ở một broker?
- Nếu thay binder, hành vi của ứng dụng có còn đúng hay phải thiết kế lại?
- Thuộc tính ảnh hưởng đến giao nhận, thứ tự, khả năng phục hồi hoặc chi phí vận hành ở mức nào?
- Có cần kiểm thử tích hợp với broker thật để xác nhận hành vi không?

Ví dụ, destination và group là khái niệm chung nên đặt ở binding. Routing key là chi tiết định tuyến của RabbitMQ nên đặt trong Rabbit binder. Offset reset là quyết định đọc của Kafka nên đặt trong Kafka binder. Subscription type là lựa chọn phối hợp consumer của Pulsar nên đặt trong Pulsar binder.

Không nên cố ép mọi tính năng đặc thù thành một abstraction chung nếu ngữ nghĩa khác nhau. Một lớp trừu tượng quá rộng có thể che giấu các khác biệt quan trọng và khiến cấu hình trở nên khó hiểu. Nếu nghiệp vụ thực sự phụ thuộc vào một tính năng như Kafka transaction hoặc Pulsar Key_Shared, hãy ghi nhận broker đó là một phần của quyết định kiến trúc và kiểm thử nó trực tiếp.

## 11. Kiểm thử và vận hành cấu hình binder

Kiểm thử cần bao phủ hai lớp. Test binder hữu ích để kiểm tra logic hàm, tên binding, payload và header mà không cần broker. Nó không chứng minh rằng cấu hình riêng của Kafka, RabbitMQ hoặc Pulsar được áp dụng đúng.

Với từng binder được triển khai, cần có kiểm thử tích hợp xác nhận:

- Ứng dụng kết nối đúng broker và có quyền truy cập destination.
- Topic, exchange, queue hoặc subscription được tạo/đăng ký theo mong muốn.
- Nhiều instance trong cùng group chia tải đúng; group khác vẫn nhận luồng độc lập.
- Partition key, routing key hoặc subscription type tạo ra thứ tự và mức song song mong muốn.
- Message được xác nhận đúng thời điểm; lỗi tạm thời được thử lại theo giới hạn.
- Message không xử lý được đi đến DLQ hoặc nơi cách ly đúng tên và có thể truy vết.
- Ứng dụng khởi động lại có thể tiếp tục từ offset, queue hoặc cursor theo chính sách đã chọn.

Khi triển khai, theo dõi consumer lag hoặc lượng message tồn đọng, tỷ lệ retry, số message ở DLQ, thời gian xử lý, lỗi kết nối và thay đổi phân công partition/consumer. Với RabbitMQ, theo dõi queue depth, unacked messages và trạng thái consumer. Với Pulsar, theo dõi backlog, subscription và redelivery. Tên chỉ số và công cụ quan sát sẽ khác nhau theo broker.

## 12. Kết luận thiết kế

Spring Cloud Stream chuẩn hóa cách khai báo hàm và binding để ứng dụng có thể tập trung vào xử lý sự kiện. Cấu hình chung nên thể hiện ý định ở cấp ứng dụng: hàm nào chạy, đọc hoặc ghi destination nào, group nào nhận và payload có định dạng gì. Những quyết định phụ thuộc broker cần được đặt ở namespace của binder: Kafka offset và partition, RabbitMQ exchange và queue, Pulsar subscription và redelivery.

Khi tách rõ hai lớp, nhóm phát triển biết phần nào có thể tái sử dụng và phần nào phải kiểm chứng theo broker. Điều đó giúp tránh kỳ vọng sai về retry, DLQ, thứ tự và giao nhận, đồng thời làm cho việc thay đổi cấu hình hoặc vận hành nhiều binder có chủ đích và dễ kiểm soát hơn.
