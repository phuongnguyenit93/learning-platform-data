# Ánh xạ destination, group và subscription

Spring Cloud Stream cung cấp một lớp trừu tượng để ứng dụng khai báo nơi gửi và nơi nhận message. Với Pulsar binder, ba khái niệm cần phân biệt là **destination**, **consumer group** và **subscription**:

- **Destination** xác định Pulsar topic mà binding đọc hoặc ghi.
- **Group** xác định danh tính logic của một nhóm consumer trong Spring Cloud Stream.
- **Subscription** là cursor và quy tắc phân phối message mà Pulsar duy trì cho consumer trên một topic.

Pulsar binder kết nối group của input binding với danh tính subscription của consumer. Các instance cùng chạy một ứng dụng và cùng group sẽ tham gia cùng subscription; những group khác nhau trên cùng destination có backlog và tiến độ xác nhận độc lập. Pulsar subscription type quyết định các consumer trong cùng subscription chia message như thế nào.

Nếu nhầm ba lớp này, ứng dụng có thể đọc trùng dữ liệu, bỏ lỡ fan-out, không scale được vì subscription đang ở chế độ Exclusive, hoặc tạo subscription mới mỗi lần triển khai. Bài học này giải thích cách ánh xạ chúng, cấu hình theo binding và kiểm chứng hành vi trên broker.

## 1. Nhìn tổng thể: binding nối ứng dụng với Pulsar

Một binding là kết nối giữa function của ứng dụng và destination của middleware. Function không cần biết cách Pulsar quản lý broker, topic hay subscription; binder đảm nhiệm phần kết nối.

~~~text
Spring Cloud Stream application
+-----------------------------------------------+
| Function: processOrder                       |
|                                               |
| processOrder-in-0  <--- input binding         |
| processOrder-out-0 ---> output binding        |
+-------------------------|---------------------+
                          |
                          | Pulsar binder
                          v
                 Apache Pulsar cluster
                 +---------------------+
                 | Topic: orders       |
                 |                     |
                 | Subscription:      |
                 | order-projection    |
                 |                     |
                 | Consumer instances  |
                 +---------------------+
~~~

Ba lớp cấu hình có ý nghĩa khác nhau:

| Thành phần | Cấu hình Spring Cloud Stream | Đối tượng Pulsar |
|---|---|---|
| Destination | `bindings.<binding>.destination` | Topic |
| Group | `bindings.<input-binding>.group` | Danh tính subscription của consumer |
| Subscription type | Pulsar extended consumer properties | Exclusive, Shared, Failover hoặc Key_Shared |
| Subscription mode | Pulsar extended consumer properties | Durable hoặc NonDurable |
| Partition count | Pulsar binder producer/consumer properties | Số partition của topic |

Một topic có thể có nhiều subscription. Mỗi subscription có một tên và một kiểu phân phối riêng. Một subscription có thể có nhiều consumer tùy subscription type.

## 2. Destination ánh xạ tới Pulsar topic

Trong Spring Cloud Stream, destination là tên đích của binding. Với Pulsar, destination được dùng làm tên topic mà producer publish hoặc consumer subscribe.

Tên topic đầy đủ của Pulsar có cấu trúc:

~~~text
{persistent|non-persistent}://tenant/namespace/topic
~~~

Ví dụ:

~~~text
persistent://acme/orders/orders-created
persistent://acme/orders/orders-approved
non-persistent://acme/telemetry/device-heartbeat
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `persistent` | Message được lưu bền vững trong storage của Pulsar |
| `non-persistent` | Message chỉ tồn tại trong bộ nhớ khi đang được chuyển tới consumer |
| `tenant` | Ranh giới quản trị và đa thuê bao |
| `namespace` | Nhóm topic cùng chính sách quản trị, retention và cấu hình |
| `topic` | Tên luồng message cụ thể |

Với dữ liệu nghiệp vụ cần khả năng phục hồi sau broker restart hoặc consumer disconnect, thường dùng persistent topic. Non-persistent topic chỉ phù hợp khi ứng dụng chấp nhận mất message đang truyền khi broker hoặc subscriber gặp sự cố.

Nên dùng tên topic đầy đủ trong cấu hình production để tránh phụ thuộc vào tenant/namespace mặc định của client. Tên topic cũng là contract giữa producer và consumer: hai binding muốn trao đổi cùng một luồng dữ liệu phải trỏ tới cùng destination.

## 3. Binding name không phải destination

Spring Cloud Stream tạo tên binding mặc định từ tên function bean:

- Supplier có output binding: `<function>-out-0`.
- Function có input và output: `<function>-in-0` và `<function>-out-0`.
- Consumer chỉ có input binding: `<function>-in-0`.

Ví dụ:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumer {

    @Bean
    Consumer<OrderCreated> processOrder() {
        return order -> {
            // Xử lý nghiệp vụ của đơn hàng.
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        long total
    ) {}
}
~~~

Input binding mặc định là `processOrder-in-0`. Ta có thể ánh xạ binding đó tới một Pulsar topic:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
~~~

Ở đây:

- `processOrder` là tên function bean.
- `processOrder-in-0` là tên binding.
- `persistent://acme/orders/orders-created` là destination/topic thực tế.

Nếu không khai báo destination, Spring Cloud Stream dùng binding name làm tên destination. Cách mặc định hữu ích khi thử nghiệm, nhưng nên khai báo rõ destination cho ứng dụng production để đổi tên function không vô tình làm đổi topic.

Với nhiều function trong cùng ứng dụng, khai báo `spring.cloud.function.definition` để kích hoạt đúng các function cần chạy. Các binding name vẫn gắn với tên bean, còn destination được cấu hình độc lập.

## 4. Producer và consumer có thể dùng cùng destination

Một producer gửi message tới topic; một hoặc nhiều consumer binding có thể subscribe topic đó.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder

    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders-created

        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

Producer không cần khai báo group vì group chỉ áp dụng cho input binding. Consumer group không tạo một topic mới; nó tạo một subscription identity trên topic đã chọn.

Có thể có nhiều consumer binding trỏ tới cùng destination nhưng dùng group khác nhau. Khi đó mỗi subscription nhận một bản sao độc lập của message. Đây là cách xây dựng fan-out cho nhiều dịch vụ nghiệp vụ.

## 5. Consumer group trong Spring Cloud Stream

Consumer group đại diện cho một nhóm instance cùng thực hiện một nhiệm vụ tiêu thụ. Ví dụ, ba replica của dịch vụ tạo projection đơn hàng đều thuộc group `order-projection-v1`.

~~~text
Destination: orders-created

Group order-projection-v1
  +-- instance A
  +-- instance B
  +-- instance C

Group billing-v1
  +-- instance D
  +-- instance E
~~~

Với cùng một group, các instance phối hợp tiêu thụ message theo subscription type của Pulsar. Với group khác nhau, mỗi nhóm có tiến độ xác nhận riêng và nhận được bản sao của luồng message.

| Cấu hình | Kết quả |
|---|---|
| Cùng destination, cùng group | Cùng một nhóm tiêu thụ |
| Cùng destination, group khác nhau | Mỗi group có bản sao luồng message riêng |
| Cùng group, nhiều instance | Các instance tham gia cùng subscription |
| Group khác nhau, cùng tên instance | Vẫn là các subscription độc lập |

Ví dụ hai dịch vụ cần cùng nhận mọi đơn hàng:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

Dịch vụ thanh toán dùng cùng destination nhưng group riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: createInvoice

    stream:
      bindings:
        createInvoice-in-0:
          destination: persistent://acme/orders/orders-created
          group: billing-v1
~~~

Kết quả là cả projection và billing đều nhận được message. Nếu hai dịch vụ dùng cùng group, chúng sẽ chia nhau message và một dịch vụ có thể không nhận được event mà nó cần.

**Quy tắc vận hành:** đặt group theo tên nhiệm vụ logic, không đặt theo hostname, pod name hoặc ID của từng instance. Khi scale từ 2 lên 5 replica, giữ nguyên group để các replica cùng tham gia một subscription.

## 6. Group và subscription name liên hệ với nhau thế nào?

Pulsar không dùng thuật ngữ consumer group như Kafka. Pulsar dùng subscription name để định danh tiến độ tiêu thụ của một nhóm consumer trên topic.

Pulsar binder ánh xạ consumer group của Spring Cloud Stream sang subscription identity. Vì vậy, group cần ổn định qua các lần restart và rollout nếu ứng dụng muốn tiếp tục backlog/acknowledgement state hiện có.

Có thể đặt group như sau:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

Tên subscription tương ứng nên có ý nghĩa tương tự `order-projection-v1`. Nếu cần điều khiển trực tiếp tên subscription qua native Pulsar consumer properties, binder hỗ trợ cấu hình ở cấp extended binding:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                name: order-projection-v1
                type: Shared
                mode: Durable
~~~

Khi cấu hình cả `group` và `subscription.name`, hãy dùng cùng một giá trị để giữ một danh tính logical nhất quán. Tránh đặt hai tên khác nhau mà không hiểu rõ binder version và thứ tự ưu tiên cấu hình của ứng dụng.

Nếu bỏ group, Spring Cloud Stream xem consumer là anonymous. Một anonymous consumer không biểu diễn một danh tính nhóm bền vững mà nhiều instance có thể chủ động dùng chung. Với consumer production cần tiếp tục backlog sau restart, nên khai báo group rõ ràng.

## 7. Subscription là cursor và trạng thái xác nhận của Pulsar

Một subscription là trạng thái tiêu thụ được Pulsar lưu cho topic. Nó theo dõi những message đã được acknowledge và những message còn pending.

~~~text
Topic: persistent://acme/orders/orders-created
  message 1
  message 2
  message 3
  message 4
  message 5
       |
       +---- subscription: order-projection-v1
       |       acked: 1, 2, 3
       |       pending: 4, 5
       |
       +---- subscription: billing-v1
               acked: 1, 2
               pending: 3, 4, 5
~~~

Hai subscription có thể ở các vị trí khác nhau vì mỗi dịch vụ xử lý theo tốc độ riêng. Message đã acknowledge bởi một subscription không có nghĩa mọi subscription khác cũng đã acknowledge message đó.

Pulsar giữ message chưa được xác nhận để có thể gửi lại khi consumer lỗi hoặc disconnect. Message được xóa theo chính sách lưu trữ và trạng thái acknowledge của các subscription liên quan. Nếu namespace có retention policy, message đã acknowledge vẫn có thể được giữ lại theo chính sách đó.

Các thao tác vận hành như xóa subscription, skip backlog hoặc thay đổi initial position có thể làm thay đổi khả năng đọc lại dữ liệu. Không dùng chúng như thao tác dọn dẹp thông thường nếu chưa xác định tác động tới consumer.

## 8. Bốn subscription type của Pulsar

Subscription name xác định nhóm consumer; subscription type xác định cách broker phân phối message trong nhóm đó.

| Type | Consumer trong cùng subscription | Phân phối | Ordering |
|---|---|---|---|
| Exclusive | Chỉ một consumer được kết nối | Một consumer nhận toàn bộ message | Theo thứ tự topic; với topic phân vùng là theo từng partition |
| Failover | Nhiều consumer kết nối, một consumer active | Consumer standby tiếp quản khi active lỗi | Theo thứ tự trên từng partition |
| Shared | Nhiều consumer active | Broker phân phối message giữa các consumer | Không bảo đảm thứ tự |
| Key_Shared | Nhiều consumer active | Message cùng key được gửi tới cùng consumer | Bảo toàn thứ tự theo key |

### Exclusive

Exclusive là subscription type mặc định của Pulsar. Chỉ một consumer được gắn vào subscription. Nếu nhiều replica cùng dùng một subscription Exclusive, các consumer bổ sung sẽ bị từ chối.

Dùng Exclusive khi chỉ có một consumer hoặc khi ứng dụng chủ động muốn một consumer xử lý toàn bộ subscription. Không chọn Exclusive cho deployment có nhiều replica cần cùng xử lý song song.

### Failover

Failover cho phép nhiều consumer gắn vào cùng subscription, nhưng tại một thời điểm chỉ có consumer active nhận message trên một topic không phân vùng. Consumer còn lại đóng vai trò standby. Khi active consumer disconnect, một consumer standby được chọn để tiếp quản.

Với partitioned topic, mỗi partition có một consumer active. Vì vậy Failover có thể phân phối các partition cho nhiều consumer nhưng vẫn giữ một active consumer trên từng partition.

Dùng Failover khi cần standby và chuyển đổi dự phòng, hoặc muốn giữ ordering theo partition. Nó không giống Shared: các consumer standby không cùng xử lý message đồng thời trên một partition.

### Shared

Shared cho phép nhiều consumer cùng active và broker phân phối message giữa chúng. Đây là lựa chọn phù hợp cho competing consumers cần tăng throughput.

Shared không bảo đảm thứ tự message. Hai message cùng key có thể được giao cho hai consumer khác nhau và xử lý hoàn tất theo thứ tự khác nhau. Nếu nghiệp vụ cần thứ tự theo đơn hàng, tài khoản hoặc thiết bị, hãy cân nhắc Key_Shared hoặc thiết kế tuần tự hóa theo key.

### Key_Shared

Key_Shared cho phép nhiều consumer cùng active nhưng message có cùng key được phân phối tới cùng một consumer tại một thời điểm. Điều này hỗ trợ song song giữa các key mà vẫn giữ thứ tự theo từng key.

Producer phải cấu hình batching phù hợp. Nếu batching mặc định gom message của nhiều key vào cùng batch, broker có thể phân phối batch theo cách phá semantics của Key_Shared. Hãy tắt batching hoặc dùng key-based batching khi producer hỗ trợ.

Key_Shared yêu cầu message có key rõ ràng. Nếu message không có key, cách phân phối mặc định không thể bảo đảm cùng một thực thể nghiệp vụ luôn về cùng consumer.

## 9. Chọn subscription type theo nghiệp vụ

Một số tình huống thường gặp:

| Nhu cầu | Type phù hợp | Lý do |
|---|---|---|
| Một consumer duy nhất, không cần scale | Exclusive | Một consumer sở hữu subscription |
| Nhiều replica nhưng chỉ cần standby | Failover | Có consumer dự phòng |
| Nhiều replica cùng xử lý song song, chấp nhận reorder | Shared | Phân phối message cho nhiều consumer active |
| Nhiều replica, cần thứ tự theo key | Key_Shared | Cùng key đi tới một consumer |
| Hai dịch vụ đều cần nhận mọi event | Hai subscription name riêng | Mỗi dịch vụ có backlog riêng |

Đừng chọn Shared chỉ vì muốn tăng số replica. Nếu nghiệp vụ phụ thuộc vào thứ tự theo customer ID, account ID hoặc order ID, Shared có thể tạo race condition khi nhiều consumer xử lý cùng key đồng thời.

Cũng đừng chọn Failover để thay thế một subscription Shared đang chạy throughput cao. Failover ưu tiên một consumer active trên mỗi partition; các standby không tăng throughput xử lý của partition đó.

## 10. Cấu hình subscription type ở cấp binding

Spring Cloud Stream Pulsar binder hỗ trợ các Pulsar consumer properties ở cấp binder, cấp Spring Boot và cấp extended binding. Extended binding properties có phạm vi hẹp nhất và có độ ưu tiên cao nhất.

Ví dụ dùng Shared cho một input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

Đường dẫn cấu hình:

~~~text
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.mode
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.name
~~~

Các property native này được kế thừa từ Spring for Apache Pulsar consumer configuration. Cấu hình cấp binding giúp một function dùng Shared trong khi function khác trong cùng ứng dụng dùng Failover hoặc Key_Shared.

Nếu cấu hình ở cấp toàn ứng dụng bằng `spring.pulsar.consumer...` hoặc `spring.cloud.stream.pulsar.binder.consumer...`, nhiều consumer binding có thể cùng nhận một cấu hình. Dùng extended binding khi các function có yêu cầu khác nhau.

## 11. Subscription mode: Durable và NonDurable

Subscription type và subscription mode là hai trục cấu hình khác nhau.

- **Type** quyết định message được phân phối tới consumer nào.
- **Mode** quyết định cursor subscription có được lưu bền vững hay không.

Durable là subscription mode mặc định. Nó lưu cursor bền vững; khi consumer disconnect hoặc broker restart, trạng thái xác nhận và vị trí đọc được phục hồi. Consumer kết nối lại bằng cùng subscription name có thể tiếp tục từ vị trí đã xác nhận.

NonDurable subscription dùng cursor không bền vững. Nếu broker dừng, cursor không được phục hồi và consumer không thể tiếp tục từ vị trí cũ. Chỉ dùng cho luồng tạm thời có thể chấp nhận mất tiến độ đọc; với consumer nghiệp vụ cần giữ backlog qua restart, chọn Durable.

Spring for Apache Pulsar thường cấu hình subscription mode bằng `spring.pulsar.consumer.subscription.mode`; với binder, có thể đặt tại extended binding:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                mode: Durable
                type: Shared
                initial-position: Earliest
~~~

Trong production, hãy quyết định rõ initial position cho subscription mới. Một subscription đã tồn tại có cursor riêng; thay đổi initial position không phải là cách rewind cursor hiện tại.

## 12. Initial position: Earliest và Latest

Khi Pulsar tạo subscription mới, initial position xác định điểm bắt đầu đọc backlog.

| Initial position | Hành vi |
|---|---|
| Earliest | Bắt đầu từ message cũ nhất còn được giữ |
| Latest | Bắt đầu từ message mới được publish sau khi subscription được tạo |

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                initial-position: Earliest
~~~

Chọn Earliest khi consumer mới cần xử lý dữ liệu lịch sử. Chọn Latest khi chỉ muốn nhận message phát sinh từ thời điểm subscription mới được tạo.

Initial position chỉ có ý nghĩa khi subscription chưa có trạng thái tiêu thụ. Nếu subscription đã tồn tại, Pulsar tiếp tục dựa trên cursor và acknowledgement state hiện tại. Muốn replay cần dùng thao tác reset/seek có kiểm soát và đánh giá tác động lên output.

## 13. Destination và subscription không thay thế nhau

Một topic có thể phục vụ nhiều nhóm consumer. Mỗi nhóm tạo subscription riêng.

~~~text
persistent://acme/orders/orders-created
                 |
                 +---- order-projection-v1 (Shared)
                 |       +-- replica A
                 |       +-- replica B
                 |
                 +---- billing-v1 (Failover)
                 |       +-- active replica
                 |       +-- standby replica
                 |
                 +---- audit-v1 (Exclusive)
                         +-- audit consumer
~~~

Nếu đổi destination, consumer chuyển sang topic khác. Nếu đổi group, consumer dùng subscription identity khác trên cùng topic và có thể nhận lại backlog theo initial position của subscription mới.

Vì vậy:
- Đổi destination là đổi luồng dữ liệu.
- Đổi group là đổi danh tính logical consumer.
- Đổi subscription type là đổi cách phân phối message trong nhóm.
- Đổi subscription mode là đổi vòng đời trạng thái subscription.

Đừng đổi group chỉ để scale thêm pod. Hãy giữ group và thay subscription type phù hợp. Đổi group tạo một subscription khác và có thể khiến dữ liệu cũ được đọc lại.

## 14. Partitioned topic và subscription

Partitioned topic chia một logical topic thành nhiều partition nội bộ. Pulsar phân phối partition qua broker để tăng throughput.

~~~text
Topic: orders-created (8 partitions)
  partition-0  partition-1  partition-2  partition-3
  partition-4  partition-5  partition-6  partition-7

Subscription: order-projection-v1
  Shared consumers:
    replica A  <--- các message được broker dispatch
    replica B  <--- các message được broker dispatch
    replica C  <--- các message được broker dispatch
~~~

Partition count và subscription type giải quyết hai vấn đề khác nhau:

- Partition count xác định mức phân vùng của topic và khả năng xử lý song song phía broker.
- Subscription type xác định cách các consumer trong cùng subscription nhận message.

Với Failover, mỗi partition có một consumer active; standby có thể tiếp quản khi active consumer lỗi. Với Shared, nhiều consumer cùng nhận message từ subscription và không có ordering guarantee. Với Key_Shared, message cùng key được gửi tới cùng consumer theo semantics của loại subscription đó.

Không thể tăng throughput chỉ bằng cách thêm replica nếu topic chỉ có ít partition hoặc subscription type không cho phép consumer hoạt động song song. Cần xem cả partition count, routing key, subscription type và thời gian xử lý message.

## 15. Cấu hình partition count với Pulsar binder

Pulsar binder có topic provisioner. Khi topic chưa tồn tại, binder có thể tạo topic cơ bản không phân vùng. Để tạo partitioned topic, cần cấu hình partition count và quyền quản trị phù hợp.

Có hai phạm vi:

- Cấp binder: `spring.cloud.stream.pulsar.binder.partition-count` áp dụng cho các topic được binder tạo.
- Cấp binding: `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.partition-count` hoặc `consumer.partition-count` cho binding cụ thể.

Ví dụ đặt partition count cho output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder

    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders-created

      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 8
~~~

Topic provisioner dùng Pulsar administration API. Nếu cluster không chạy ở địa chỉ mặc định, cần cấu hình administration service URL:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
~~~

Trong production, cần cấp quyền admin phù hợp cho topic provisioning hoặc tạo topic trước bằng quy trình hạ tầng. Không cấp quyền quản trị rộng cho service chỉ để nó có thể publish/consume nếu tổ chức có quy trình quản lý topic tập trung.

Tăng partition count là thay đổi hạ tầng. Trước khi thực hiện, hãy đánh giá routing key, thứ tự theo key, throughput, consumer concurrency và tương thích của các client đang chạy.

## 16. Topic auto-creation và namespace

Pulsar có thể tự tạo topic khi client publish hoặc subscribe vào topic chưa tồn tại, nếu broker cho phép auto topic creation. Pulsar binder cũng cung cấp topic provisioner để tạo topic cần thiết.

Topic auto-created thường là topic không phân vùng. Partitioned topic cần được tạo với số partition mong muốn thông qua admin/provisioner.

Namespace là ranh giới quản trị quan trọng. Có thể áp dụng policy ở cấp namespace như retention, backlog quota, message TTL, replication hoặc quyền truy cập. Vì vậy nên chia namespace theo domain hoặc môi trường khi có yêu cầu vận hành khác nhau.

Ví dụ:

~~~text
tenant: acme
  namespace: orders-dev
    orders-created
    orders-approved
  namespace: orders-prod
    orders-created
    orders-approved
  namespace: billing-prod
    invoice-created
~~~

Không dùng cùng một destination cho dev và production nếu chúng dùng chung Pulsar cluster mà không có namespace phân tách. Cũng không dựa vào default tenant/namespace trong production khi có thể khai báo topic đầy đủ.

## 17. Một topic, nhiều group: fan-out và competing consumers

Pulsar cho phép kết hợp pub-sub và queue semantics.

**Fan-out:** mỗi dịch vụ dùng subscription name riêng.

~~~text
Topic orders-created
  |
  +--> order-projection-v1
  |
  +--> billing-v1
  |
  +--> audit-v1
~~~

Mỗi subscription có backlog và ack state độc lập. Billing có thể chậm hơn projection mà không làm projection phải chờ.

**Competing consumers:** nhiều replica dùng chung một subscription name.

~~~text
Topic orders-created
  |
  +--> order-projection-v1
         +--> replica A
         +--> replica B
         +--> replica C
~~~

Broker phân phối message trong subscription theo type đã chọn. Đây là mô hình scale một consumer application.

Không tạo một group riêng cho mỗi pod nếu các pod phải cùng xử lý một luồng nghiệp vụ. Nếu làm vậy, mỗi pod có thể nhận một bản sao của toàn bộ message thay vì chia tải.

## 18. Key_Shared, message key và ordering

Key_Shared hữu ích khi một đơn hàng phải được xử lý theo thứ tự trong khi các đơn hàng khác vẫn xử lý song song.

Ví dụ producer gửi:

~~~text
key=order-1001, event=OrderCreated
key=order-1002, event=OrderCreated
key=order-1001, event=OrderPaid
key=order-1003, event=OrderCreated
key=order-1001, event=OrderShipped
~~~

Với Key_Shared, các message có key `order-1001` được gửi tới cùng một consumer tại một thời điểm. Những key khác có thể được xử lý trên consumer khác.

Producer cần đặt key ổn định:

~~~java
pulsarTemplate.newMessage(orderEvent)
    .withMessageCustomizer(messageBuilder ->
        messageBuilder.key(orderEvent.orderId())
    )
    .send();
~~~

Khi dùng Key_Shared, producer phải tắt batching hoặc dùng key-based batching. Nếu không, batch có thể chứa nhiều key và broker không thể duy trì routing theo key như mong đợi.

Ordering guarantee chỉ có phạm vi được Pulsar đảm bảo theo key/partition. Nó không tự bảo đảm các side effect trong database của ứng dụng hoàn tất theo thứ tự nếu consumer xử lý bất đồng bộ hoặc dispatch công việc sang thread khác. Ứng dụng vẫn cần idempotency và kiểm soát thứ tự ở tầng nghiệp vụ.

## 19. Multi-topic subscription và nhiều destination

Pulsar hỗ trợ một consumer subscribe nhiều topic, bằng danh sách topic hoặc pattern. Spring Cloud Stream input binding cũng có thể nhận nhiều destination theo khả năng của binder.

Ví dụ một binding đọc hai topic:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrderEvents

    stream:
      bindings:
        processOrderEvents-in-0:
          destination: persistent://acme/orders/orders-created,persistent://acme/orders/orders-cancelled
          group: order-events-v1
~~~

Khi dùng nhiều topic, cần xác nhận binder version và cách nó chuyển danh sách destination sang Pulsar consumer. Nếu dùng pattern subscription, các topic được chọn bằng regex phải nằm trong cùng namespace.

Không có ordering guarantee giữa các topic khác nhau. Nếu cần xử lý theo thứ tự nghiệp vụ xuyên nhiều loại event, hãy đưa chúng về cùng topic hoặc thiết kế timestamp/sequence và state machine để sắp xếp ở ứng dụng.

## 20. Cấu hình subscription properties ở cấp ứng dụng và cấp binding

Pulsar binder sử dụng Spring for Apache Pulsar để tạo producer và consumer. Do đó, nhiều Pulsar properties của Spring Boot cũng có thể dùng trong binder.

Có ba phạm vi cấu hình:

| Phạm vi | Prefix | Phạm vi ảnh hưởng |
|---|---|---|
| Spring Boot Pulsar | `spring.pulsar.consumer...` | Consumer của toàn ứng dụng |
| Pulsar binder | `spring.cloud.stream.pulsar.binder.consumer...` | Consumer dùng binder trong ứng dụng |
| Extended binding | `spring.cloud.stream.pulsar.bindings.<binding>.consumer...` | Một input binding cụ thể |

Thứ tự ưu tiên của binder:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

Ví dụ một ứng dụng có hai consumer binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder;processPayment

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1

        processPayment-in-0:
          destination: persistent://acme/payments/payments-created
          group: payment-projection-v1

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable

          processPayment-in-0:
            consumer:
              subscription:
                type: Failover
                mode: Durable
~~~

Hai function dùng hai subscription type khác nhau dù cùng nằm trong một Spring Boot application. Nếu đặt subscription type ở cấp toàn ứng dụng, cả hai binding có thể nhận cùng cấu hình và không còn đáp ứng yêu cầu riêng.

## 21. Thay đổi group hoặc subscription type khi triển khai

Đổi group không giống đổi số replica.

- Giữ nguyên group: instance mới tham gia subscription hiện có và tiếp tục từ cursor.
- Đổi group: tạo danh tính subscription mới; subscription mới có initial position riêng.
- Đổi subscription type: thay đổi cách consumer trong subscription phân phối message.
- Đổi destination: chuyển sang topic khác.

Pulsar subscription chỉ có một type tại một thời điểm. Muốn đổi type, phải dừng tất cả consumer đang sử dụng subscription đó rồi khởi động lại với type mới. Không rollout dần các replica sang type khác trong khi replica cũ vẫn giữ kết nối cùng subscription.

Quy trình thay đổi type:

1. Xác định topic và subscription cần đổi.
2. Dừng toàn bộ consumer của subscription.
3. Xác nhận không còn consumer hoạt động.
4. Cấu hình type mới ở extended binding.
5. Khởi động consumer với cấu hình mới.
6. Kiểm tra subscription type và backlog trên broker.
7. Theo dõi redelivery, ordering và throughput sau khi chuyển đổi.

Nếu cần blue/green với hai nhóm chạy song song, dùng subscription name/group riêng và output được cô lập. Đừng đổi type giữa chừng khi hai nhóm vẫn cùng sử dụng một subscription.

## 22. Backlog, acknowledgement và vòng đời subscription

Consumer acknowledge message sau khi xử lý thành công. Pulsar lưu trạng thái ack theo subscription. Message chưa được ack tiếp tục nằm trong backlog và có thể được redeliver khi consumer lỗi, nack hoặc ack timeout.

Một số lưu ý:

- Cùng topic nhưng subscription khác nhau có backlog riêng.
- Một consumer chậm không làm cursor của subscription khác bị lùi.
- Subscription durable giữ trạng thái khi consumer disconnect.
- Xóa subscription có thể làm mất cursor/backlog state của nhóm đó.
- Retention policy của namespace có thể giữ message đã acknowledge.
- TTL hoặc backlog quota có thể ảnh hưởng dữ liệu chưa xử lý.

Khi một ứng dụng đổi group, subscription cũ có thể còn tồn tại và giữ backlog. Chỉ xóa subscription cũ sau khi đã xác nhận không còn consumer cần dữ liệu và đã có quyết định xử lý backlog.

## 23. Kiểm tra destination và subscription trên Pulsar

Khi ứng dụng không nhận được message, kiểm tra theo thứ tự:

1. Producer đang publish tới topic nào?
2. Input binding có destination trùng hoàn toàn topic đó không?
3. Tenant và namespace có đúng không?
4. Consumer group có đúng với subscription mong muốn không?
5. Subscription đã tồn tại chưa?
6. Subscription type có cho phép số replica đang chạy không?
7. Subscription mode có phải Durable khi cần giữ backlog không?
8. Initial position của subscription mới có phù hợp không?
9. Topic có partitioned không và partition count có đúng không?
10. Consumer có quyền subscribe namespace/topic không?

Pulsar Admin API và CLI có thể xem topic, subscription và stats. Ví dụ một topic có thể có nhiều subscription như `order-projection-v1`, `billing-v1` và `audit-v1`. Kiểm tra subscription giúp phát hiện trường hợp producer gửi đúng topic nhưng consumer đang subscribe nhầm group.

Không chỉ kiểm tra log Spring Boot. Cần kiểm tra trạng thái ở broker vì subscription là trạng thái được Pulsar quản lý.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không nhận message | Destination sai tenant/namespace/topic | Dùng topic URI đầy đủ và kiểm tra broker |
| Mỗi pod nhận bản sao toàn bộ message | Mỗi pod dùng group riêng | Dùng cùng group cho các replica |
| Consumer thứ hai không khởi động | Subscription đang Exclusive | Chuyển sang Shared, Key_Shared hoặc Failover theo yêu cầu |
| Không có fan-out cho dịch vụ thứ hai | Hai dịch vụ dùng cùng group | Đặt group riêng cho mỗi logical consumer |
| Message bị xử lý sai thứ tự | Dùng Shared trong khi cần ordering | Chọn Key_Shared hoặc Failover và thiết kế key |
| Key_Shared không giữ routing theo key | Producer batching không theo key | Tắt batching hoặc dùng key-based batching |
| Consumer mới bỏ qua backlog cũ | Subscription mới có initial position Latest | Chọn Earliest nếu cần đọc lịch sử |
| Restart làm xuất hiện subscription mới | Group không ổn định hoặc anonymous | Đặt group bền vững |
| Topic không có partition | Binder tạo topic cơ bản không phân vùng | Cấu hình partition-count và quyền provision |
| Đổi subscription type bị từ chối | Consumer cũ vẫn đang kết nối | Dừng toàn bộ consumer trước khi đổi |
| Backlog cũ vẫn còn sau rollout | Group cũ vẫn tồn tại | Kiểm tra subscription cũ và có kế hoạch cleanup |
| Hai input topic xử lý sai thứ tự | Không có ordering guarantee xuyên topic | Gộp luồng hoặc sắp xếp theo sequence/event time |

## 25. Kiểm thử mapping destination, group và subscription

Một integration test với Pulsar broker nên xác nhận cả tên topic và subscription, không chỉ xác nhận function được gọi.

### Kịch bản 1: producer và consumer cùng destination

1. Tạo output binding trỏ tới `persistent://acme/orders/orders-created`.
2. Tạo input binding trỏ tới cùng topic.
3. Gửi một OrderCreated.
4. Xác nhận consumer nhận payload.

### Kịch bản 2: hai group nhận cùng một message

1. Tạo consumer group `projection-v1`.
2. Tạo consumer group `billing-v1`.
3. Publish một message.
4. Xác nhận cả hai subscription đều nhận được message.
5. Acknowledge ở projection và kiểm tra billing vẫn có backlog cho đến khi nó xử lý.

### Kịch bản 3: nhiều replica cùng group

1. Chạy hai replica cùng destination và group.
2. Cấu hình Shared.
3. Publish nhiều message.
4. Xác nhận cả hai consumer cùng nhận message từ subscription.
5. Xác nhận tổng số message được xử lý và kiểm tra duplicate/idempotency.

### Kịch bản 4: ordering theo key

1. Chạy hai replica với Key_Shared.
2. Publish nhiều message cùng key và nhiều key khác nhau.
3. Cấu hình producer key-based batching hoặc tắt batching.
4. Xác nhận message cùng key được dispatch theo thứ tự.
5. Xác nhận các key khác vẫn có thể xử lý song song.

### Kịch bản 5: subscription mới và initial position

1. Publish một số message trước khi tạo subscription.
2. Tạo subscription với Earliest và xác nhận nhận backlog.
3. Tạo một subscription mới với Latest.
4. Xác nhận subscription Latest bắt đầu từ message mới sau khi được tạo.
5. Restart consumer với cùng group và xác nhận cursor hiện có được tiếp tục.

### Kịch bản 6: partitioned topic

1. Provision topic với số partition đã định.
2. Gửi message có key ổn định.
3. Chạy nhiều consumer trong Shared hoặc Key_Shared.
4. Kiểm tra partition routing, throughput và ordering theo key.
5. Thay số replica và xác nhận subscription vẫn giữ đúng identity.

## 26. Bài thực hành và tiêu chí hoàn thành

Xây dựng hệ thống xử lý đơn hàng với một topic và ba consumer application:

- Topic: `persistent://acme/orders/orders-created`.
- Projection group: `order-projection-v1`.
- Billing group: `billing-v1`.
- Audit group: `audit-v1`.

Thực hiện:

1. Tạo function `publishOrder` với output binding `publishOrder-out-0`.
2. Đặt destination đầy đủ cho output binding.
3. Tạo function `projectOrder` với input binding `projectOrder-in-0`.
4. Cấu hình group `order-projection-v1` và subscription type Shared.
5. Chạy hai replica của projection cùng group.
6. Tạo function `createInvoice` dùng group `billing-v1`.
7. Tạo function `auditOrder` dùng group `audit-v1`.
8. Publish một message và xác nhận cả ba group nhận được bản sao.
9. Publish nhiều message và xác nhận hai replica projection chia tải.
10. Thử chuyển projection sang Key_Shared và gửi message với order ID làm key.
11. Kiểm tra topic, subscription, backlog và acknowledgement trên Pulsar.
12. Restart một replica và xác nhận subscription tiếp tục từ cursor hiện tại.
13. Thử đổi group trong môi trường test và quan sát subscription mới.
14. Thử tạo partitioned topic và đo ảnh hưởng tới throughput.

Hoàn thành bài khi có thể giải thích destination khác binding name như thế nào; group ánh xạ thành danh tính subscription ra sao; cùng group và khác group tạo ra semantics nào; chọn đúng Exclusive, Failover, Shared hoặc Key_Shared; và cấu hình được topic, partition count, subscription mode, initial position trong Spring Cloud Stream Pulsar binder.

## 27. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — dependency, function binding, destination mapping, native encoding/decoding, extended binding properties và topic provisioner.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group và các thuộc tính input binding.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html) — Pulsar consumer subscription name, type, mode và initial position.
- [Apache Pulsar — Messaging Concepts](https://pulsar.apache.org/docs/concepts-messaging/) — topic URI, tenant, namespace, subscription, partitioned topic và routing.
- [Apache Pulsar 5.0 — Messaging Concepts](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/) — subscription mode Durable/NonDurable, cursor, topic và retention.
- [Apache Pulsar — Work with Consumer](https://pulsar.apache.org/docs/client-libraries/consumers/) — subscription types, consumer distribution, ordering và Key_Shared batching.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html) — subscription name, consumer configuration và acknowledgement.

