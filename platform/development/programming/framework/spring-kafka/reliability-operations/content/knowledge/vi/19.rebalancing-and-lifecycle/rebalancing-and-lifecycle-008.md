# Rebalance do session timeout

## 1. Rebalance do session timeout là gì?

Trong Kafka, các consumer thuộc cùng một **consumer group** chia nhau các partition của những topic đã đăng ký. Kafka broker giữ vai trò group coordinator và theo dõi các thành viên thông qua cơ chế heartbeat. Nếu coordinator không nhận được heartbeat hợp lệ từ một consumer trong khoảng thời gian cho phép, member đó có thể bị coi là không còn hoạt động và bị loại khỏi group. Các partition trước đó do consumer này sở hữu cần được phân phối lại: đó là **rebalance do session timeout**.

Với Spring Kafka, điều này có thể xảy ra ngay cả khi phương thức `@KafkaListener` không ném exception. JVM có thể bị pause lâu, mạng kết nối broker mất ổn định, CPU không cấp đủ thời gian chạy hoặc coordinator không phản hồi kịp. Sau khi session hết hạn, Kafka phải phục hồi khả năng xử lý bằng cách chuyển partition sang consumer khác.

Ví dụ topic `orders` có 4 partition:

~~~text
Trước sự cố:
  Consumer A -> orders-0, orders-1
  Consumer B -> orders-2, orders-3

Consumer A không heartbeat đủ lâu:
  Coordinator loại A khỏi group
  Kafka thực hiện rebalance

Sau sự cố:
  Consumer B -> orders-0, orders-1, orders-2, orders-3
~~~

Một rebalance có thể dẫn đến consumer lag tăng, xử lý tạm gián đoạn, offset commit thất bại hoặc record được giao lại. Không có nghĩa record biến mất khỏi Kafka; vấn đề là **quyền sở hữu partition và tiến độ xử lý** đã thay đổi.

## 2. Consumer group và group coordinator

### 2.1. Consumer group

`group.id` xác định nhóm consumer có chung tiến độ tiêu thụ. Mỗi partition được phân công cho tối đa một consumer member trong cùng group tại một thời điểm theo assignment hợp lệ. Nhiều group khác nhau có thể đọc cùng một topic độc lập.

~~~text
Topic payments: P0 P1 P2 P3 P4 P5

Group payment-service:
  pod-a/consumer-0 -> P0, P1
  pod-b/consumer-0 -> P2, P3
  pod-c/consumer-0 -> P4, P5
~~~

Khi một consumer rời group hoặc không còn được coi là sống, coordinator cần phân phối lại những partition bị bỏ trống.

### 2.2. Coordinator theo dõi membership

Group coordinator là broker chịu trách nhiệm quản lý trạng thái group. Nó phối hợp các yêu cầu join, heartbeat và việc cập nhật assignment tùy group protocol. Coordinator không thể biết trực tiếp nghiệp vụ database trong `@KafkaListener` đã hoàn tất hay chưa; nó chỉ đánh giá các tín hiệu group protocol.

Đừng đồng nhất liveness với tiến độ nghiệp vụ. Một consumer có thể gửi heartbeat bình thường nhưng listener xử lý rất chậm. Ngược lại, consumer xử lý logic nhanh nhưng mất đường truyền tới coordinator vẫn có thể bị timeout.

### 2.3. Heartbeat

Heartbeat là tín hiệu định kỳ của consumer gửi đến coordinator để duy trì tư cách thành viên. Trong giao thức consumer group **classic**, các cấu hình thường gặp gồm:

- `session.timeout.ms`: giới hạn thời gian coordinator có thể chờ heartbeat trước khi coi member không còn hoạt động.
- `heartbeat.interval.ms`: chu kỳ consumer cố gắng gửi heartbeat.
- `group.id`: group mà member tham gia.

Ví dụ:

~~~properties
group.id=payment-service
session.timeout.ms=30000
heartbeat.interval.ms=10000
~~~

Khoảng timeout cho phép một số lần heartbeat chậm hoặc thất bại tạm thời. Một heartbeat thất bại đơn lẻ không tự động đồng nghĩa với việc coordinator lập tức loại member.

Với **consumer group protocol mới** (khi client và cluster hỗ trợ `group.protocol=consumer`), cấu hình session và heartbeat có thể do broker quyết định qua các thông số tương ứng, ví dụ `group.consumer.session.timeout.ms` và `group.consumer.heartbeat.interval.ms`. Vì vậy cần xác định protocol hiệu lực trước khi chỉnh timeout.

## 3. Session timeout khác max.poll.interval.ms

Đây là phân biệt quan trọng nhất khi điều tra một consumer mất partition.

| Tiêu chí | Session timeout | Max poll interval |
|---|---|---|
| Câu hỏi | Coordinator còn nhận được heartbeat/liveness không? | Ứng dụng có tiếp tục gọi `poll()` kịp không? |
| Cấu hình classic | `session.timeout.ms` | `max.poll.interval.ms` |
| Nguyên nhân thường gặp | Mạng lỗi, JVM pause, process chết, coordinator unavailable | Listener xử lý chậm, batch quá lớn, blocking operation |
| Tác động | Member hết session và bị loại khỏi group | Consumer có thể rời group hoặc ngừng heartbeat tùy membership/protocol |
| Hướng điều tra | Heartbeat, coordinator, network, GC, CPU | Processing time, poll cycle, batch, downstream |

### 3.1. Listener lâu không luôn gây session timeout

Trong Kafka client hiện đại dùng classic group protocol, heartbeat thường được xử lý bởi một background thread sau khi consumer tham gia group. Vì vậy listener bị chặn không nhất thiết khiến heartbeat ngừng ngay.

Tuy nhiên, nếu poll loop không tiến trong thời gian vượt `max.poll.interval.ms`, consumer vi phạm hợp đồng tiến độ poll. Với dynamic membership, client có thể chủ động rời group. Trường hợp này vẫn gây rebalance nhưng **không phải session timeout thuần túy**.

### 3.2. Static membership có khác biệt

Nếu consumer có `group.instance.id` (static membership), khi vượt `max.poll.interval.ms`, client có thể ngừng gửi heartbeat mà không nhả assignment ngay. Coordinator thường đợi session timeout trước khi reassignment partition. Do đó một chuỗi sự cố có thể là:

~~~text
Listener bị block lâu
       |
       v
Vượt max.poll.interval.ms
       |
       v
Static member ngừng heartbeat
       |
       v
Session timeout
       |
       v
Coordinator reassignment partition
~~~

Cách xử lý chi tiết phụ thuộc Kafka version và group protocol. Điều quan trọng là đừng đọc dòng log session timeout cuối cùng rồi bỏ qua nguyên nhân poll interval xảy ra trước đó.

### 3.3. Ví dụ hai timeline

Giả sử cấu hình:

~~~text
session.timeout.ms    = 30000   (30 giây)
heartbeat.interval.ms = 10000   (10 giây)
max.poll.interval.ms  = 300000  (5 phút)
~~~

**Tình huống A:** Consumer mất kết nối coordinator 35 giây dù listener vẫn xử lý nhanh. Session timeout có thể xảy ra.

**Tình huống B:** Một batch listener mất 7 phút mới trả về, trong khi network và JVM bình thường. Trước hết phải điều tra việc vượt `max.poll.interval.ms`; không kết luận đó là lỗi heartbeat chỉ vì group đã rebalance.

## 4. Timeline của một session timeout

Giả sử coordinator đã nhận heartbeat cuối của consumer A và ngưỡng session là 30 giây.

~~~text
T+00s  A gửi heartbeat thành công; B vẫn hoạt động
T+03s  A mất kết nối đến coordinator
T+10s  Heartbeat tiếp theo của A không đến
T+20s  Coordinator vẫn không nhận heartbeat hợp lệ từ A
T+30s  Session của A có thể hết hạn
       Coordinator loại A khỏi group
       Kafka thay đổi assignment
T+35s  B tiếp nhận các partition trước đó thuộc A
T+40s  A phục hồi mạng và nhận ra membership cũ không còn hợp lệ
       A cần join/reconcile group trở lại
~~~

Các mốc là minh họa. Thực tế phụ thuộc heartbeat cuối cùng, broker tải cao, coordinator availability, protocol và thời gian các member hoàn thành rebalance.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant K as Group coordinator
    participant B as Consumer B
    A->>K: Heartbeat thành công
    B->>K: Heartbeat thành công
    Note over A,K: Mạng A bị gián đoạn
    A-xK: Heartbeat thất bại
    B->>K: Heartbeat bình thường
    Note over K: Session của A hết hạn
    K->>K: Loại A khỏi membership
    K-->>B: Group assignment thay đổi
    B->>B: Nhận thêm partition
    Note over A: Kết nối phục hồi
    A->>K: Tiếp tục với trạng thái cũ
    K-->>A: Generation hoặc membership đã thay đổi
    A->>K: Join/reconcile lại group
~~~

Kafka chỉ reassignment khi coordinator xác định membership thay đổi. Không phải cứ network đứt rất ngắn là partition được chuyển ngay.

## 5. Các nguyên nhân thực tế

### 5.1. Mạng gián đoạn

Consumer có thể không liên hệ được coordinator do DNS, routing, firewall, NAT, packet loss hoặc broker connection errors. Kết nối TCP tồn tại không bảo đảm heartbeat request được trả lời đúng thời hạn.

Kiểm tra network RTT, DNS errors, connection resets, broker discovery và các log đánh dấu coordinator unknown.

### 5.2. JVM pause dài

Một đợt stop-the-world GC làm các Java threads tạm dừng, bao gồm thread heartbeat. Nếu pause quá dài, coordinator có thể hết session trước khi JVM hoạt động lại.

Đo pause duration, heap occupancy, allocation rate và thời điểm GC. Một pause ấn tượng trong log có thể quan trọng hơn CPU usage trung bình.

### 5.3. CPU throttling hoặc starvation

Trong Kubernetes, giới hạn CPU quá thấp hoặc node quá tải có thể làm JVM không có thời gian chạy heartbeat đúng hạn. Nhiều consumer threads, GC và ứng dụng web cùng cạnh tranh CPU có thể khiến vấn đề rõ hơn.

Theo dõi container CPU throttling, host load, thread count, OOM/restart và JVM execution pause.

### 5.4. Group coordinator không khả dụng

Coordinator broker có thể restart, chuyển ownership, chịu tải cao hoặc tạm mất kết nối. Consumer sẽ tìm lại coordinator nhưng nếu gián đoạn kéo dài, group membership có thể bị ảnh hưởng.

Đối chiếu broker logs với client logs. Nếu nhiều consumer group cùng mất heartbeat vào cùng thời điểm, nên nghi ngờ hạ tầng chung trước khi chỉnh từng listener.

### 5.5. Process crash hoặc bị kill đột ngột

Nếu process bị kill hoặc VM mất điện, heartbeat ngừng. Coordinator phát hiện member chết theo session timeout. Trái lại, khi consumer shutdown sạch và gửi leave group, rebalance có thể xảy ra trước ngưỡng session timeout.

Vì vậy rebalance ngay lúc rollout chưa chắc do timeout; cần xác định có orderly leave hay abrupt loss.

### 5.6. Consumer API bị dùng không đúng

KafkaConsumer không thread-safe. Nếu ứng dụng tự dùng consumer instance trong thread khác, gọi `poll()`, `seek()` hoặc `commitSync()` không đúng owner, trạng thái consumer có thể khó dự đoán. Với `@KafkaListener`, nên để container quản lý consumer và poll loop.

## 6. Spring Kafka listener container tham gia thế nào?

Spring Kafka chịu trách nhiệm tạo consumer, poll record, dispatch vào listener, xử lý error handler, commit offset và điều phối lifecycle. Kafka group coordinator vẫn là nơi quyết định session timeout.

Quy trình thông thường:

1. Listener container tạo KafkaConsumer từ ConsumerFactory.
2. Consumer subscribe topic, join group và nhận partition assignment.
3. Container poll record rồi gọi listener.
4. Khi listener hoàn tất, container tiến offset theo acknowledgment mode.
5. Khi rebalance xảy ra, container nhận revoke/assign/lost callbacks tùy group protocol và trạng thái client.
6. Khi dừng sạch, container đóng consumer và giải phóng resource.

Một session timeout có thể xảy ra ngay khi listener container chưa kịp xử lý callback. Nếu JVM đang đóng băng, callback không thể chạy trước khi broker loại member.

### 6.1. Phân biệt revoked và lost

- **Revoked**: partition bị thu hồi theo quy trình rebalance; có thể có cơ hội lưu trạng thái hợp lệ trước khi chuyển ownership.
- **Lost**: consumer đã mất quyền sở hữu partition; không nên cố commit offset như thể member vẫn hợp lệ.
- **Assigned**: consumer nhận assignment mới và có thể chuẩn bị state để xử lý.

Các callback không phải bảo đảm “trước khi broker chuyển partition luôn chạy cleanup”. Với crash hoặc freeze, callback cũ có thể xuất hiện muộn hoặc không xuất hiện.

### 6.2. Eager so với cooperative rebalance

Eager rebalance có thể yêu cầu nhiều member revoke toàn bộ assignment trước khi chia lại. Cooperative rebalance cố gắng chuyển partition dần và giảm phạm vi thu hồi.

Cooperative **không chữa được session timeout**. Nếu một member thật sự mất liveness, các partition của nó vẫn cần có owner mới. Cooperative chỉ điều chỉnh cách chuyển assignment.

### 6.3. Pause vẫn có thể duy trì poll

Spring Kafka hỗ trợ pause listener container để tạm ngừng nhận record mới mà vẫn poll theo cơ chế của container nhằm giữ group membership. Cách này phù hợp hơn việc để listener ngủ dài không có kiểm soát.

Tuy nhiên, pause không chữa JVM stop-the-world, broker mất kết nối hoặc network partition: heartbeat vẫn phải thật sự đến coordinator.

## 7. Cấu hình Spring Boot với classic protocol

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: payment-service
      enable-auto-commit: false
      max-poll-records: 200
      properties:
        group.protocol: classic
        session.timeout.ms: 30000
        heartbeat.interval.ms: 10000
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Các thuộc tính có chức năng riêng:

| Property | Ý nghĩa |
|---|---|
| `group-id` | Định danh consumer group |
| `enable-auto-commit=false` | Để container quản lý commit offset theo listener processing |
| `session.timeout.ms` | Thời gian dung sai mất heartbeat ở classic protocol |
| `heartbeat.interval.ms` | Chu kỳ gửi heartbeat mục tiêu |
| `max.poll.interval.ms` | Giới hạn giữa các lần poll |
| `max-poll-records` | Số record tối đa trả về trong một poll |
| `concurrency` | Số consumer trong listener container mỗi instance |
| `ack-mode=record` | Commit theo record đã xử lý thành công |

Đây là **giá trị minh họa**, không phải cấu hình khuyến nghị cố định. Kafka broker có thể giới hạn khoảng `session.timeout.ms` mà client được phép yêu cầu. Session timeout ngoài giới hạn sẽ khiến consumer join group không thành công.

### 7.1. Heartbeat interval nên thấp hơn session timeout đáng kể

Nếu heartbeat interval gần bằng session timeout, chỉ cần một heartbeat chậm là consumer có nguy cơ bị coi là chết. Một điểm bắt đầu thông thường là khoảng một phần ba session timeout:

~~~text
heartbeat.interval.ms = 10000
session.timeout.ms    = 30000
~~~

Tỷ lệ thực tế phụ thuộc network jitter, broker response latency và yêu cầu failover. Không nên tăng heartbeat rate vô tội vạ nếu broker đang chịu group coordination tải cao.

### 7.2. Session timeout quá nhỏ

- Phát hiện member chết nhanh hơn.
- Nhưng dễ bị false failure khi network jitter hoặc GC pause.
- Có thể gây rebalance thường xuyên, giảm throughput và tăng lag.

### 7.3. Session timeout quá lớn

- Chịu được gián đoạn heartbeat dài hơn.
- Nhưng khi process chết thật, coordinator phát hiện chậm.
- Partition của member chết có thể bị chờ lâu hơn trước khi được reassigned, làm tăng recovery time.

Đặt timeout là bài toán cân bằng **failure detection speed** và **tolerance for transient failures**.

## 8. Với consumer group protocol mới

Khi client và broker hỗ trợ `group.protocol=consumer`, heartbeat và session parameters có thể do broker quản lý, khác mô hình classic.

Ví dụ client:

~~~properties
group.protocol=consumer
~~~

Các broker properties liên quan có thể gồm:

~~~text
group.consumer.heartbeat.interval.ms
group.consumer.session.timeout.ms
~~~

Không nên sao chép `heartbeat.interval.ms` hoặc `session.timeout.ms` của classic consumer và giả định chúng vẫn điều khiển timeout khi consumer protocol đang được sử dụng. Tùy Kafka client version, một số property classic có thể bị từ chối hoặc không có hiệu lực trong protocol mới.

Quy trình cấu hình:

1. Xác định `group.protocol` thực tế.
2. Xác nhận Kafka client và broker versions.
3. Xác định timeout được điều khiển ở client hay broker.
4. Đặt giá trị được hỗ trợ.
5. Quan sát thời gian phát hiện failure qua fault injection và metrics.
6. Không suy đoán chỉ từ tên property.

`max.poll.interval.ms` vẫn phục vụ kiểm soát tiến độ poll, nhưng tương tác với static membership/protocol cần đối chiếu phiên bản đang chạy.

## 9. Khi chạy nhiều replica và concurrency

Giả sử một topic có 6 partition, dịch vụ chạy 3 pod, mỗi pod có concurrency 2:

~~~text
Topic payments: 6 partitions

Pod A: A-0, A-1
Pod B: B-0, B-1
Pod C: C-0, C-1

Total consumer members = 3 × 2 = 6
~~~

Nếu Pod B bị pause nặng, cả B-0 và B-1 có thể cùng mất heartbeat. Group có thể chuyển các partition trước đó thuộc hai member này cho bốn member còn lại.

Tăng concurrency **không tự chữa session timeout**. Thậm chí quá nhiều consumers có thể gia tăng thread, socket và tài nguyên, khiến CPU/memory pressure cao hơn.

Cần tính tổng consumer trong group qua mọi replica, không chỉ concurrency của một JVM.

### 9.1. Dấu hiệu lỗi ở một pod

Nếu chỉ các consumer trên một pod gặp session timeout, kiểm tra node network, pod CPU throttling, JVM GC và restart events.

Nếu nhiều pod thuộc nhiều group cùng timeout, xem broker coordinator, network hoặc dịch vụ hạ tầng chung.

### 9.2. Autoscaling và deployment

Pod mới join group có thể gây rebalance dù không có timeout. Pod shutdown sạch cũng có thể gây rebalance do leave group. Pod mất điện đột ngột thường được nhận diện muộn hơn qua session timeout.

Đối chiếu deployment history với coordinator logs để phân biệt những tình huống này.

## 10. Static membership và session timeout

`group.instance.id` cung cấp static membership, giúp một consumer có danh tính ổn định qua restart trong một số kiến trúc.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: payment-service
      properties:
        group.instance.id: payment-worker-slot-a
        session.timeout.ms: 45000
~~~

`group.instance.id` phải duy nhất giữa các static members đang hoạt động trong cùng group. Với listener container concurrency lớn hơn 1, Spring Kafka có thể tạo suffix định danh cho từng child consumer; cần hiểu hành vi của version đang dùng để không cấu hình một ID giống nhau cho nhiều members.

Static membership có thể giảm rebalance không cần thiết trong restart ngắn, nhưng nó **không vô hiệu session timeout**.

~~~text
Static member restart ngắn:
  Có thể giữ assignment ổn định hơn.

Static member mất liveness vượt session timeout:
  Coordinator vẫn có thể reassignment partition.
~~~

Nếu chọn session timeout rất dài cho static member, application recovery sau crash thực sự cũng chậm hơn. Cần căn cứ vào restart SLO và failover requirements.

## 11. Ảnh hưởng đến offset commit và dữ liệu

Rebalance không làm Kafka xóa record. Nhưng nó thay đổi quyền sở hữu partition và khả năng commit offset của consumer.

Ví dụ:

~~~text
Consumer A xử lý payments-0 offset 120
    |
    +-- Ghi DB đã commit
    |
    +-- A bị mất session trước offset commit
    |
    v
Consumer B nhận payments-0
    |
    v
B có thể đọc lại offset 120 từ committed offset trước đó
~~~

Khi A đã mất generation/assignment, một lần commit offset có thể thất bại với `CommitFailedException` hoặc exception liên quan rebalance. Nếu A còn chạy task nền, side effect của A và B có thể cạnh tranh dù Kafka chỉ assign partition cho một member hợp lệ.

### 11.1. Idempotency

Với at-least-once processing, redelivery là một khả năng bình thường. Các phương án bảo vệ side effect:

- Event ID ổn định.
- Inbox table có unique constraint.
- Cập nhật database idempotent.
- Ràng buộc business operation ID (ví dụ payment ID).
- Outbox nếu cần phát event sau khi DB commit.
- Lỗi không thể xử lý được chuyển sang recovery/DLT theo policy rõ ràng.

Kafka session timeout không bảo đảm listener method chỉ chạy một lần. Thậm chí khi Kafka EOS được cấu hình cho Kafka-to-Kafka, side effect ngoài Kafka vẫn cần cơ chế idempotency.

### 11.2. Đừng commit offset sau khi partition đã lost

Nếu member đã mất quyền sở hữu, không nên tự commit tiến độ như thể partition vẫn thuộc mình. Đặc biệt, callback `onPartitionsLost` không phải nơi an toàn để ép commit offset của partition đã mất.

Nếu consumer bị freeze, nó có thể không chạy callback trước khi broker chuyển partition. Vì vậy correctness phải dựa vào transaction/idempotency chứ không chỉ dựa vào revoke callback.

## 12. Quan sát rebalance trong Spring Kafka

Có thể đăng ký `ConsumerAwareRebalanceListener` để ghi nhận assignment:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

            @Override
            public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.info("Assigned: {}", partitions);
            }

            @Override
            public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.warn("Revoked: {}", partitions);
            }

            @Override
            public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.error("Lost: {}", partitions);
            }
        }
    );

    return factory;
}
~~~

Các import và callback contract cần phù hợp với Spring Kafka version của dự án.

### 12.1. Không block trong callback

Callback rebalance chạy trên đường vận hành consumer. Một thao tác database hoặc HTTP lâu trong callback có thể kéo dài rebalance, gây thêm group instability.

Nếu cần checkpoint state, hãy dùng logic có deadline rõ ràng và phân biệt revoke với lost. Không chờ vô hạn để “đảm bảo” một task nền hoàn tất.

### 12.2. Không phụ thuộc hoàn toàn vào callback

JVM bị kill hoặc freeze có thể không chạy callback ở thời điểm mong muốn. Consumer mới vẫn có thể nhận partition sau session expiration. Side effect bên ngoài Kafka cần được bảo vệ độc lập bằng idempotency.

## 13. Chẩn đoán session timeout từ log

Khi thấy rebalance, nên thu thập cùng lúc:

1. `group.id`, consumer client ID và pod/JVM.
2. Topic-partition assignment trước và sau sự kiện.
3. Timestamp heartbeat cuối thành công và những lần heartbeat thất bại.
4. Bằng chứng member removed/session expired từ coordinator.
5. Bằng chứng `max.poll.interval.ms` violation.
6. Network errors hoặc coordinator discovery failures.
7. GC stop-the-world pauses.
8. CPU throttling, node pressure, pod restart/OOM.
9. Kafka broker restart/coordinator migration.
10. Offset commit failures và listener redelivery.

Một số mẫu log có thể gặp, tùy Kafka version:

~~~text
Heartbeat request failed
Marking coordinator unknown
Attempt to heartbeat failed since group is rebalancing
Max poll interval exceeded
Commit cannot be completed because the group has rebalanced
Partitions revoked / partitions assigned
~~~

Không phải các thông điệp này luôn xuất hiện nguyên văn. Chúng là gợi ý điều tra, không phải điều kiện đủ kết luận session timeout. Nên xem đầy đủ log coordinator và client quanh cùng mốc thời gian.

### 13.1. Dấu hiệu session timeout thực sự

- Heartbeat thất bại liên tiếp trong một khoảng tương ứng session threshold.
- Coordinator báo loại member mất liveness.
- JVM freeze hoặc network outage xảy ra trước rebalance.
- Không thấy listener/poll interval là nguyên nhân chính.

### 13.2. Dấu hiệu poll interval

- Processing time của listener/batch vượt max poll interval.
- Client log báo poll interval exceeded.
- Giảm batch size hoặc tối ưu listener làm sự cố biến mất.
- Heartbeat có thể vẫn bình thường trước thời điểm poll deadline bị vi phạm.

Với static membership, hai chuỗi này có thể nối tiếp nhau: poll interval violation rồi heartbeat dừng và session expiration.

## 14. Kafka CLI để quan sát group

Có thể quan sát consumer group từ môi trường có quyền truy cập cluster:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group payment-service
~~~

Thông tin có thể gồm committed offset, log end offset, lag, assignment và member metadata tùy phiên bản Kafka và trạng thái group. Khi group đang rebalance, kết quả có thể thay đổi liên tục; nên đối chiếu nhiều lần với log.

Để xem partition count:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic payments
~~~

Trong cluster có SASL/SSL, client CLI phải dùng cấu hình xác thực phù hợp. Đây là ví dụ thao tác vận hành để người học hiểu công cụ; không phải lệnh cần chạy khi soạn bài.

## 15. Monitoring và cảnh báo

| Nhóm metric | Mục đích |
|---|---|
| Heartbeat response time và failures | Xác định liveness của coordinator |
| Heartbeat rate | Phát hiện heartbeat bất thường |
| Rebalance count và duration | Đo group churn |
| Assigned-partitions count | Theo dõi số partition thuộc từng member |
| Poll latency / poll interval | Phát hiện consumer không poll kịp |
| Listener processing p95/p99 | Liên hệ độ trễ nghiệp vụ với poll |
| GC pause duration | Tìm stop-the-world pause |
| Container CPU throttling | Tìm starvation |
| Broker coordinator request errors | Xác định lỗi từ broker |
| Consumer lag theo partition | Đo gián đoạn và recovery |
| Offset commit failures | Dấu hiệu mất quyền hoặc group generation |
| Duplicate business event count | Đánh giá idempotency sau rebalance |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và hệ thống giám sát. Không phải mọi metric đều bật sẵn; cần cấu hình instrumentation tương ứng.

Không nên alert chỉ vì có một rebalance trong rolling deployment. Tín hiệu đáng chú ý hơn là **rebalance liên tục ngoài maintenance**, lag vượt SLO, heartbeat errors kéo dài hoặc commit failures tăng.

## 16. Điều chỉnh session timeout an toàn

### 16.1. Khi nào có thể tăng?

Tăng timeout có thể hợp lý nếu mạng có jitter ngắn hoặc GC pauses hiếm nhưng vượt ngưỡng hiện tại, và các nguyên nhân khắc phục được đã được xử lý.

Ví dụ minh họa:

~~~text
Trước:
  session timeout   = 10000 ms
  heartbeat interval = 3000 ms

Quan sát:
  Một số pause ngắn 12-15s, rebalance lặp.

Sau khi đo và sửa tối ưu JVM/hạ tầng:
  session timeout   = 30000 ms
  heartbeat interval = 10000 ms
~~~

Nếu consumer group dùng protocol mới, timeout có thể phải đổi phía broker, không phải trong consumer properties.

### 16.2. Không dùng timeout để che lỗi nền

Không nên chỉ tăng session timeout khi:

- Listener vượt `max.poll.interval.ms`.
- JVM OOM hoặc restart liên tục.
- Broker coordinator không ổn định.
- Network thường xuyên đứt nhiều phút.
- CPU throttling nghiêm trọng.
- App tạo task background không có deadline và khiến shutdown không hoàn tất.

Timeout quá dài làm mất khả năng phát hiện member chết nhanh. Một cấu hình “không thấy rebalance nữa” chưa chắc tốt nếu partition bị treo quá lâu khi process thực sự đã chết.

### 16.3. Heartbeat interval và broker load

Heartbeat quá dày tăng số request group coordination. Heartbeat quá thưa giảm khả năng chịu jitter. Cần đo coordinator latency và group count, nhất là với nhiều consumer groups trên cùng broker cluster.

## 17. Điều chỉnh max.poll.interval và max.poll.records

Một batch xử lý lâu có thể vượt poll deadline dù heartbeat vẫn hoạt động.

Ví dụ một listener xử lý trung bình 500 ms/record, mỗi poll trả 500 record:

~~~text
500 record × 500 ms = 250 giây

max.poll.interval.ms = 300000  (5 phút)

Khoảng đệm cho retry, GC và network còn không nhiều.
~~~

Có thể giảm `max.poll.records` xuống 100, tối ưu database operations, dùng batch phù hợp hoặc tăng concurrency trong giới hạn số partition và downstream capacity.

Quy trình:

1. Đo p95/p99 duration theo record/batch.
2. Xác định số record tối đa thực tế trong một poll.
3. Tính thời gian xử lý xấu nhất gồm retry/backoff và downstream timeout.
4. Giảm `max.poll.records` nếu batch gây khoảng poll quá dài.
5. Chọn `max.poll.interval.ms` có headroom cho biến động.
6. Đo lại throughput và lag để tránh giảm batch quá mức.

`max.poll.records` giới hạn số record trả về trong một lần poll, không tạo thêm consumer. Nếu một record đơn lẻ có thể chạy lâu hơn poll interval, cần thay đổi listener hoặc chia workload.

## 18. Rebalance và xử lý bất đồng bộ

Một pattern nguy hiểm:

~~~java
@KafkaListener(topics = "payments")
public void onPayment(PaymentEvent event) {
    executor.execute(() -> database.apply(event));
}
~~~

Listener trả về ngay khi task được submit. Với ack mode dựa trên listener return, container có thể tiến offset trước khi database side effect hoàn tất. Nếu process crash, record có nguy cơ bị bỏ qua.

Ngược lại, nếu task chạy lâu sau khi partition bị reassigned vì session timeout, consumer cũ và consumer mới có thể cùng thực hiện side effect.

Một thiết kế an toàn hơn:

- Xử lý đồng bộ trong listener nếu nghiệp vụ có deadline ngắn.
- Hoặc ghi một work item bền vững vào database/queue trước khi listener trả về.
- Với acknowledgment bất đồng bộ, hiểu semantics của Spring Kafka version và không commit vượt quá record chưa hoàn tất.
- Theo dõi task theo topic-partition, hỗ trợ cancellation khi revoke/lost.
- Dùng inbox hoặc business idempotency key để ngăn tác động lặp.

Không có callback lifecycle nào thay thế được transaction boundary hoặc unique constraint của database.

## 19. Kiểm thử bằng fault injection

### 19.1. Mất kết nối coordinator

1. Tạo test topic và consumer group riêng.
2. Chạy ít nhất hai consumer members.
3. Ghi nhận assignment và committed offsets.
4. Trong môi trường thử nghiệm, chặn heartbeat/network của một member đủ lâu.
5. Quan sát coordinator loại member sau session timeout.
6. Xác nhận các partition được reassigned.
7. Khôi phục member và kiểm tra join/reconcile group.
8. Xác nhận event redelivery được xử lý idempotent.

### 19.2. JVM pause

1. Bật metrics và logs cho GC/heartbeat.
2. Tạo JVM pause có kiểm soát trong môi trường test.
3. Đối chiếu pause duration và session threshold.
4. Quan sát member removal và rebalance.
5. Giảm resource pressure rồi thử lại.

### 19.3. Max poll interval riêng biệt

1. Cho listener xử lý batch lâu trong khi network bình thường.
2. Để thời gian xử lý vượt `max.poll.interval.ms`.
3. Quan sát log poll violation.
4. Nếu là dynamic member, xem client leave/rebalance.
5. Nếu static member, theo dõi giai đoạn ngừng heartbeat rồi session expiration.
6. Điều chỉnh poll size/processing duration và đo lại.

### 19.4. Crash sau DB commit nhưng trước offset commit

1. Gửi một event có event ID ổn định.
2. Cho consumer A commit thay đổi database.
3. Làm A mất membership trước offset commit.
4. Cho consumer B nhận partition.
5. Xác nhận event có thể được giao lại.
6. Xác nhận inbox/unique constraint ngăn side effect lặp.
7. Kiểm tra committed offset tiến đúng sau khi xử lý an toàn.

Đây là những thử nghiệm hạ tầng có kiểm soát; không chủ động gây network outage hoặc JVM freeze trên production để xác nhận một giả thuyết.

## 20. Các lỗi nhận định phổ biến

**Cho rằng mọi rebalance đều do session timeout:** deployment, join/leave, partition changes và poll interval violation cũng gây rebalance.

**Cho rằng listener chậm luôn làm heartbeat ngừng:** classic consumer hiện đại thường có background heartbeat; cần kiểm tra poll interval riêng.

**Tăng session.timeout.ms để sửa max.poll.interval:** hai giới hạn có chức năng khác nhau.

**Đặt heartbeat.interval.ms gần bằng session.timeout.ms:** tăng nguy cơ false failure khi một heartbeat bị chậm.

**Đặt timeout quá lớn:** kéo dài phát hiện consumer chết thật và recovery.

**Tin rằng static membership không bị timeout:** static member vẫn mất membership khi liveness quá hạn.

**Nhầm revoked và lost:** commit trên partition đã lost có thể không còn hợp lệ.

**Cho rằng cooperative rebalance loại bỏ session timeout:** cooperative chỉ thay đổi cách assignment chuyển owner.

**Bỏ qua commit failures:** record chưa commit có thể được redeliver.

**Dùng auto commit với listener dài và side effect khó lặp:** offset có thể không gắn chặt với trạng thái nghiệp vụ.

**Submit task nền rồi trả về:** container có thể coi record đã xử lý khi task chưa bền vững.

**Chỉnh cấu hình classic khi dùng group protocol mới:** các property client có thể không hiệu lực.

**Tăng concurrency vô hạn:** tiêu thụ nhiều CPU/threads nhưng không tăng song song vượt số partition.

## 21. Bảng xử lý tình huống vận hành

| Quan sát | Hướng điều tra |
|---|---|
| Rebalance ngay sau deploy hoặc scale | Join/leave group, rollout; chưa chắc timeout |
| Nhiều heartbeat failures | Network, coordinator, JVM pause |
| Chỉ một pod mất liveness | CPU throttling, GC, node/network riêng |
| Nhiều group cùng timeout | Broker hoặc hạ tầng chung |
| Listener duration tăng | `max.poll.interval.ms`, batch size, downstream |
| Static membership timeout sau task dài | Poll violation rồi ngừng heartbeat |
| CommitFailedException sau rebalance | Lost ownership, offset và redelivery |
| Lag tăng sau một member chết | Session detection time, reassignment |
| Fencing transactional producer | Transactional ID/epoch; không tự đồng nhất với session timeout |
| Timeout chỉ sau idle hoặc restart | Kiểm tra lifecycle, coordinator và version/config |
| Rebalance liên tục dù network bình thường | Poll interval, member churn, assignor, resource pressure |

## 22. Kết luận

**Rebalance do session timeout** xảy ra khi group coordinator không còn nhận đủ tín hiệu heartbeat/liveness của một consumer member trong khoảng cho phép. Coordinator loại member đó và group phải phân phối lại các partition đã mất owner. Mạng, broker coordinator, JVM pause, CPU starvation và process crash là những nguyên nhân thường gặp.

Trong Spring Kafka, cần phân biệt sự cố này với `max.poll.interval.ms`: một listener xử lý lâu thường tác động đến vòng poll trước, còn background heartbeat có thể vẫn hoạt động. Xác định đúng group protocol, theo dõi heartbeat và assignment, cấu hình timeout tại đúng phía client hoặc broker, và giữ offset commit gắn với kết quả xử lý nghiệp vụ.

Khi partition chuyển sang owner mới, redelivery và offset commit failure có thể xảy ra. Độ tin cậy đầu cuối không đến từ việc tăng timeout, mà từ **consumer lifecycle rõ ràng, observability, idempotency và transaction boundary phù hợp**.
