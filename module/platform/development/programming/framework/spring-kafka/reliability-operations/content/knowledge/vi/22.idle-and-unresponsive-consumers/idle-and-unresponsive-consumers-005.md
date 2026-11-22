# Phát hiện partition không có message

Trong hệ thống **Spring Kafka Reliability Operations**, một partition **không có message** trong một khoảng thời gian có thể là trạng thái bình thường, nhưng cũng có thể là dấu hiệu producer ngừng phát sự kiện, phân phối key bị lệch, consumer không nhận dữ liệu, partition bị pause hoặc một luồng nghiệp vụ đang bị gián đoạn. Phát hiện đúng tình trạng này giúp đội vận hành phân biệt **topic thực sự không có lưu lượng** với **consumer không hoạt động** và **record bị tồn đọng chưa xử lý**.

Spring Kafka cung cấp các sự kiện idle ở **cấp listener container** và **cấp từng partition**. Đối với bài toán tìm một partition cụ thể không nhận record, điểm quan trọng là cấu hình `idlePartitionEventInterval` và quan sát `ListenerContainerPartitionIdleEvent` cùng sự kiện trở lại hoạt động `ListenerContainerPartitionNoLongerIdleEvent` trong những phiên bản hỗ trợ.

Tuy nhiên, **idle không có nghĩa bị lỗi**. Một partition có thể hoàn toàn không được producer ghi tới vì cách chọn key, lịch hoạt động hoặc do traffic thấp. Ngược lại, một consumer có thể liên tục poll thành công nhưng không nhận được record mới; việc đó khác hẳn consumer thread bị treo. Phải đặt kết quả phát hiện idle trong ngữ cảnh **partition assignment, tốc độ publish, offset, consumer lag, yêu cầu SLA và trạng thái pause** trước khi cảnh báo hay tự khắc phục.

## 1. Partition không có message nghĩa là gì?

Kafka topic được chia thành nhiều partition, mỗi partition là một log có offset riêng. Kafka producer quyết định partition đích thông qua key và partitioner, còn Kafka consumer group phân phối các partition cho consumer members.

Ví dụ topic `orders.events` có bốn partition:

~~~text
orders.events
  partition 0: offset 100, 101, 102, 103, ...
  partition 1: offset  40,  41,  42, ...
  partition 2: offset  77,  78,  79, ...
  partition 3: offset  19,  20, ...
~~~

Giả sử trong 10 phút gần đây partition 0 và 1 liên tục có record, còn partition 2 và 3 không nhận record mới. Có ít nhất ba khả năng:

1. **Không có record mới được publish vào partition:** đây là idle thực sự của log ở đầu vào; có thể bình thường.
2. **Broker có record nhưng consumer không fetch được:** consumer có thể bị pause, mất quyền đọc, không có assignment hoặc gặp lỗi.
3. **Consumer nhận record nhưng nghiệp vụ không tiến:** listener bị retry ở một offset, downstream chậm hoặc offset chưa commit; tình huống này không nhất thiết tạo idle event.

Vì vậy, cần tách các khái niệm:

| Hiện tượng | Quan sát trực tiếp | Không được suy luận |
|---|---|---|
| Partition không có record mới | End offset của partition không tăng trong khoảng quan sát | Consumer bị treo hoặc broker hỏng. |
| Partition không được consumer nhận record | Thời gian từ record cuối consumer nhận vượt ngưỡng | Producer chắc chắn ngừng publish. |
| Listener container idle | Container không nhận record nào trong khoảng cấu hình | Tất cả partition trong topic đều không có traffic. |
| Một partition idle | Không nhận record từ partition đó đủ lâu theo cơ chế quan sát | Mọi partition khác đều idle. |
| Consumer không phản hồi | Khoảng poll dài bất thường, consumer thread có thể bị chặn | Topic không có message. |
| Consumer lag tăng | End offset đi trước committed offset | Producer đã dừng hoặc một partition không có record. |

**Bài toán “phát hiện partition không có message” nên có hai lớp:** phát hiện **consumer không thấy message ở partition được giao** và, nếu cần, xác minh **Kafka log của partition có đang được ghi thêm hay không**.

## 2. Vì sao cần quan sát ở cấp partition?

Một listener container có thể sở hữu nhiều partition. Khi một partition có traffic liên tục, container nhìn tổng thể có vẻ đang hoạt động tốt mặc dù những partition khác không nhận được message.

Ví dụ:

~~~text
Consumer A được assigned:
  orders.events-0: 200 record/phút
  orders.events-1:   0 record/phút
  orders.events-2: 150 record/phút

Container A:
  vẫn liên tục nhận record từ P0 và P2
  -> event idle của toàn container có thể không xuất hiện

Partition P1:
  không có record trong 15 phút
  -> cần phát hiện idle ở cấp riêng P1
~~~

Nếu chỉ cấu hình `idleEventInterval` cho container, đội vận hành có thể bỏ sót một partition im lặng khi container vẫn nhận record từ partition khác. Vì thế phải sử dụng **per-partition idle signal** khi SLA hoặc chính sách nghiệp vụ được áp dụng riêng theo partition.

Đặc biệt hữu ích với:

- Topic có nhiều partition nhưng lưu lượng phân bố không đều.
- Topic dùng key theo customer/order, có khả năng một nhóm key ngừng gửi event.
- Topic có producer được kỳ vọng phát heartbeat hoặc dữ liệu định kỳ.
- Luồng đối soát, IoT, stream sự kiện theo ca hoặc kênh dữ liệu.
- Tình huống nghi ngờ một partition bị pause hoặc consumer mất assignment.
- Giám sát hiệu quả của thay đổi partitioner/key distribution.

Không nên coi **mỗi partition phải có record mỗi phút** là giả định chung cho mọi topic. Với topic có nhiều partition và traffic thấp, sự im lặng của một vài partition có thể hoàn toàn bình thường.

## 3. Spring Kafka: idleEventInterval và idlePartitionEventInterval

Spring Kafka cung cấp các thuộc tính lifecycle trong `ContainerProperties`. Hai cấu hình dễ nhầm:

| Thuộc tính | Phạm vi quan sát | Event liên quan |
|---|---|---|
| `idleEventInterval` | **Toàn listener container** không nhận record theo thời gian cấu hình | `ListenerContainerIdleEvent` và `ListenerContainerNoLongerIdleEvent`. |
| `idlePartitionEventInterval` | **Từng topic-partition được consumer container theo dõi** không nhận record theo thời gian cấu hình | `ListenerContainerPartitionIdleEvent` và `ListenerContainerPartitionNoLongerIdleEvent`. |
| `monitorInterval` / `noPollThreshold` | Giám sát **vòng poll bị treo hoặc không phản hồi** | `NonResponsiveConsumerEvent`, không phải partition idle event. |

Tên và khả năng phát các event này phụ thuộc phiên bản Spring Kafka. Đối với `idlePartitionEventInterval`, phải xác minh rằng phiên bản đang sử dụng có hỗ trợ cả interval và event theo partition.

### Ví dụ cấu hình qua listener container factory

~~~java
@Configuration
public class KafkaIdleMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // Cảnh báo khi toàn consumer container không nhận record.
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        // Theo dõi riêng mỗi partition được giao.
        factory.getContainerProperties()
                .setIdlePartitionEventInterval(30_000L);

        return factory;
    }
}
~~~

Các import thường dùng gồm `ConcurrentKafkaListenerContainerFactory`, `ConsumerFactory` và `Configuration`. `OrderEvent` là DTO do ứng dụng tự định nghĩa.

Trong ví dụ:

- `idleEventInterval=60000` biểu diễn thời gian theo dõi idle toàn container là 60 giây.
- `idlePartitionEventInterval=30000` biểu diễn ngưỡng theo dõi idle partition là 30 giây.
- `concurrency=3` tạo tối đa ba consumer con tương ứng với khả năng phân công partition của group.
- Mỗi consumer con chỉ trực tiếp quan sát các partition được giao cho nó, không phải mọi partition trong cluster.

**Các ngưỡng trên chỉ để minh họa.** Ngưỡng thực tế phải dựa vào tần suất message được kỳ vọng và khoảng trễ có thể chấp nhận của nghiệp vụ.

Listener sử dụng factory này:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersListenerFactory")
public void onOrderEvent(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Khi listener vẫn nhận record trên một partition nhưng không nhận record trên partition khác, sự kiện idle của partition vắng traffic có thể xuất hiện trong khi container chưa được xem là idle toàn phần.

## 4. ListenerContainerPartitionIdleEvent: ý nghĩa và thời điểm phát

`ListenerContainerPartitionIdleEvent` được Spring Kafka phát khi **một topic-partition do container theo dõi không nhận record trong một khoảng đủ dài** theo `idlePartitionEventInterval`.

Ví dụ:

~~~text
Thời gian:
  10:00:00  orders.events-2 nhận record cuối
  10:00:30  Không nhận record mới từ P2
  10:00:30+ Spring Kafka có thể phát PartitionIdleEvent(P2)
  10:01:00+ Nếu vẫn idle, có thể phát event tiếp theo theo lịch kiểm tra

Trong khi đó:
  orders.events-0 vẫn có record đều
  orders.events-1 vẫn có record đều
~~~

Sự kiện được phát dựa trên **sự vắng mặt của record mà listener container quan sát**, không phải Kafka broker xác nhận producer không ghi vào partition. Thời gian phát thực tế có thể lệch ngưỡng bởi chu kỳ poll, scheduling và cách framework kiểm tra idle.

Event có thể được phát **lặp lại** trong lúc partition tiếp tục idle. Không xây dựng hệ thống cảnh báo coi mỗi event lặp là một incident mới.

### Sự kiện có chứa thông tin gì?

Các event idle theo partition trong Spring Kafka thường cung cấp thông tin về topic-partition, thời gian idle, listener/container và ngữ cảnh consumer theo API của phiên bản. Khi viết event handler, hãy kiểm tra method signatures thực tế trước khi lấy các trường này.

Ví dụ ý tưởng ghi nhận một partition cụ thể:

~~~java
@Component
public class PartitionIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn(
                "Kafka partition idle: partition={}, idleTimeMs={}",
                event.getTopicPartition(),
                event.getIdleTime());
    }
}
~~~

Ví dụ dựa trên những accessor thường có của Spring Kafka partition-idle events; xác minh method tương ứng với bản Spring Kafka của dự án. `getIdleTime()` là khoảng thời gian idle mà event báo cáo, **không phải số record bị mất**.

### Phân biệt thời điểm poll và thời điểm business event

Record có thể chứa Kafka timestamp do producer cấp hoặc broker ghi. Khi phát hiện idle, Spring Kafka quan sát thời gian không **nhận** record, không kiểm tra rằng `event.createdAt` của nghiệp vụ đã cũ bao lâu.

Nếu producer phát một record backlog với timestamp tuần trước, container vẫn vừa nhận record đó ở thời điểm hiện tại. Do đó, khi kiểm tra dữ liệu “không có message mới”, cần chọn rõ:

- **Không nhận record mới theo processing/receive time**.
- **Không có event nghiệp vụ mới theo event time**.
- **Không có bản ghi Kafka mới được append vào partition**.

Ba chỉ số này giải quyết ba câu hỏi khác nhau.

## 5. ListenerContainerPartitionNoLongerIdleEvent: partition hoạt động trở lại

Khi một partition trước đó idle nhưng sau đó container bắt đầu nhận record từ partition đó, Spring Kafka có thể phát `ListenerContainerPartitionNoLongerIdleEvent` trong những phiên bản hỗ trợ.

Event này hữu ích để khép lại trạng thái idle:

~~~text
P2:
  10:00  nhận record cuối
  10:01  idle event: đánh dấu P2 IDLE
  10:02  vẫn không có record
  10:03  record mới đến
         -> partition no-longer-idle event
         -> đánh dấu P2 ACTIVE theo quan sát receive
~~~

Observer minh họa:

~~~java
@Component
public class PartitionActivityObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionActivityObserver.class);

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn("Partition became idle: {}",
                event.getTopicPartition());
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        log.info("Partition received records again: {}",
                event.getTopicPartition());
    }
}
~~~

Một event trở lại hoạt động chỉ chứng minh **container nhận được record**. Record có thể sau đó deserialize lỗi, listener xử lý thất bại, bị retry hoặc chuyển DLT. Vì thế cần thêm chỉ số **business success/commit offset** nếu muốn đóng incident nghiệp vụ hoàn toàn.

Không đánh dấu toàn bộ consumer group HEALTHY chỉ vì một partition no-longer-idle: các partition khác có thể vẫn idle hoặc consumer khác vẫn lỗi.

## 6. Khi nào không có event dù partition không có message?

Không nên coi "không thấy idle event" là bằng chứng topic đang có dữ liệu. Có thể xảy ra các trường hợp:

1. Chưa cấu hình `idlePartitionEventInterval` hoặc phiên bản Spring Kafka không hỗ trợ.
2. Listener không sử dụng container factory mà bạn vừa cấu hình.
3. Partition chưa được assign cho consumer này.
4. Consumer/container đã stopped hoặc không poll; event idle thông thường không còn được phát như khi container đang hoạt động.
5. Consumer bị pause; hành vi phát event và thông tin paused cần kiểm tra theo phiên bản.
6. Consumer đang liên tục đọc lại một poison pill ở cùng offset: có record được giao lại, nhưng nghiệp vụ không tiến.
7. Một consumer khác đã nhận partition sau rebalance.
8. Application event observer không đăng ký đúng Spring context hoặc event multicaster gặp lỗi.
9. Ngưỡng idle quá dài so với thời gian quan sát.
10. Record liên tục đến rất thưa nhưng đều đặn trước khi đạt ngưỡng.

Nếu partition không được gán cho consumer nào trong group, các event idle do listener hiện tại phát ra **không phải công cụ giám sát toàn cluster**. Khi cần kiểm tra cả những partition không có owner, cần nguồn quan sát độc lập ở cấp Kafka topic/group.

## 7. Idle không đồng nghĩa NonResponsiveConsumerEvent

Phân biệt này là điểm quan trọng nhất trong vận hành:

**Idle:** consumer **vẫn poll**, nhưng không nhận record. Có thể hoàn toàn khỏe mạnh nếu producer không gửi dữ liệu.

**Non-responsive:** consumer thread **không quay lại poll đúng nhịp**, có thể do listener chặn, blocking retry, deadlock hoặc I/O quá dài. Topic có thể vẫn chứa nhiều record và lag tăng.

~~~mermaid
flowchart TD
    A[Thấy partition không có record ở listener] --> B{Consumer còn poll đúng nhịp?}
    B -->|Không| C[Điều tra NonResponsiveConsumerEvent]
    C --> D[Listener timeout, retry, deadlock, GC, max.poll.interval.ms]
    B -->|Có| E{Partition còn được assigned và không pause?}
    E -->|Không| F[Điều tra assignment, rebalance, pause/resume]
    E -->|Có| G{Log end offset còn tăng?}
    G -->|Không| H[Producer không publish vào partition hoặc traffic thấp]
    G -->|Có| I[Điều tra fetch, quyền truy cập, lag và committed offset]
~~~

Spring Kafka có `NonResponsiveConsumerEvent` và những cấu hình như `monitorInterval`, `noPollThreshold` để quan sát việc consumer không poll theo kỳ vọng. Chúng không thay thế per-partition idle events.

Ví dụ:

| Kịch bản | Idle partition | Non-responsive consumer | Lag |
|---|---|---|---|
| Producer không gửi record, consumer poll bình thường | Có thể có | Không | Thường không tăng thêm. |
| Listener bị treo tại API, broker có record mới | Có thể không có event mới | Có thể có | Có thể tăng. |
| Consumer pause partition nhưng vẫn poll | Phụ thuộc cơ chế event/phiên bản | Không nhất thiết | Có thể tăng nếu producer tiếp tục publish. |
| Một partition không có traffic, hai partition khác vẫn nhận đều | Có thể có per-partition idle event | Không | Partition idle có thể lag bằng 0. |
| Retry một record lỗi nhiều lần | Không nhất thiết idle vì có redelivery | Có thể xảy ra nếu retry chặn poll quá lâu | Offset có thể đứng yên. |

Một alert chỉ nói "Kafka idle" mà không phân biệt hai loại sẽ khiến đội vận hành xử lý sai hướng.

## 8. Idle container và idle partition là hai phạm vi

`ListenerContainerIdleEvent` cho biết **container** không nhận được record trong khoảng `idleEventInterval`. Với consumer quản lý nhiều partition, bất kỳ record được nhận từ một partition nào cũng có thể khiến container không còn idle như trường hợp không có dữ liệu tổng thể.

`ListenerContainerPartitionIdleEvent` cho phép theo dõi một topic-partition độc lập.

Ví dụ:

~~~text
orders.events
  P0: 1.000 record/phút
  P1:     0 record/phút
  P2:    30 record/phút

Child consumer C0:
  assigned P0, P1, P2

Container-wide idle?
  Không, vì vẫn nhận record ở P0/P2.

Partition-idle?
  Có thể phát cho P1 khi vượt threshold.
~~~

Khi topic có traffic rất thấp và nhiều partition, nên tránh cấu hình per-partition threshold quá ngắn. Một partition không được chọn bởi key hashing trong 10 phút có thể hoàn toàn bình thường.

## 9. Partition assignment thay đổi thì tracking idle ra sao?

Trong consumer group, partition có thể được chuyển cho member khác do startup, scale, rebalance, timeout hoặc rolling deployment.

~~~text
T1: Consumer A assigned P1, không nhận record 5 phút.
T2: Group rebalance, P1 chuyển sang Consumer B.
T3: Consumer B bắt đầu poll P1.

A:
  không còn quyền quan sát/đọc P1.

B:
  quan sát P1 theo vòng đời mới của B.
~~~

Vì thế, không tạo alert "Consumer A thiếu message ở P1" kéo dài mãi sau khi P1 đã chuyển ownership. Một hệ thống monitoring tốt nên gắn trạng thái với **topic-partition + consumer group + current assignment** và cập nhật ownership khi rebalance.

### Tích hợp với lifecycle callbacks

- `onPartitionsAssigned`: đánh dấu những partition mà consumer mới chịu trách nhiệm; có thể khởi tạo state tracking cho owner mới.
- `onPartitionsRevoked`: ngừng coi consumer hiện tại là owner của các partition được revoke.
- `onPartitionsLost`: consumer đã mất ownership; không cố commit/truy xuất như owner hợp lệ.
- `ConsumerStoppedEvent`: consumer đã dừng; đóng hoặc vô hiệu hóa trạng thái theo vòng đời container.
- `ListenerContainerPartitionIdleEvent`: partition hiện đang được theo dõi chưa có record theo ngưỡng idle.

Với cooperative rebalance, các partition không đổi owner có thể được giữ lại. Không xóa tất cả trạng thái partition trên mỗi callback assigned/revoked; chỉ cập nhật đúng tập partition liên quan.

## 10. Phân biệt producer không publish và consumer không fetch

Nếu nhận per-partition idle event, bước xác minh quan trọng là **so sánh log end offset theo thời gian**, không phải xem một snapshot duy nhất.

Giả sử với P1:

~~~text
T1: end offset = 500
T2: end offset = 500
T3: end offset = 500

=> Không quan sát thấy log được append thêm trong khoảng đó.

T1: end offset = 500
T2: end offset = 530
T3: end offset = 560

=> Broker có thêm record; nếu consumer không nhận thì cần điều tra fetch/assignment/pause.
~~~

Cách đọc:

| End offset | Committed offset | Diễn giải |
|---|---|---|
| Không tăng | Bằng end offset hoặc gần đó | Có thể thực sự không có dữ liệu mới, consumer đã bắt kịp. |
| Tăng | Không tăng | Backlog tăng; có thể consumer chậm, pause hoặc lỗi. |
| Tăng | Cùng tăng | Dữ liệu và consumer đều tiến; nếu idle event xuất hiện, kiểm tra identity/time window/owner. |
| Không tăng | Commit vẫn còn xa end offset | Có backlog cũ chưa xử lý, không được coi partition khỏe chỉ vì producer im lặng. |

**Committed offset** là vị trí sẽ đọc tiếp của group, không phải timestamp record cuối đã xử lý. **End offset** phản ánh vị trí cuối log theo cách API/isolation level tương ứng; với Kafka transaction còn tồn tại khác biệt giữa log end và last stable offset. Khi tính lag, phải thống nhất loại offset và nguồn dữ liệu.

### Lấy end offsets từ đâu?

Có thể dùng công cụ quản trị Kafka hoặc `AdminClient.listOffsets` từ một **monitoring component độc lập**, theo API của Kafka client đang dùng. Không nên tạo `KafkaConsumer` mới dùng chung `group.id` chỉ để quan sát, vì nó có thể tham gia group và gây rebalance nếu subscribe.

Không nên gọi liên tục `endOffsets(...)` từ `@EventListener` được phát đồng bộ trên consumer thread: đó là một thao tác có thể cần I/O, làm chậm vòng poll. Thu thập broker offsets theo chu kỳ riêng, rồi tương quan với idle events.

Ví dụ phương án kiến trúc:

~~~mermaid
flowchart LR
    P[Producer] --> K[Kafka topic partitions]
    K --> C[Spring Kafka consumers]
    C --> I[Partition idle events]
    K --> A[AdminClient offset sampler]
    I --> M[Monitoring state]
    A --> M
    M --> R{SLA traffic/lag breached?}
    R -->|Không| N[Normal / expected quiet]
    R -->|Có| O[Alert có ngữ cảnh]
~~~

Nếu muốn giám sát log của **mọi partition**, kể cả partition chưa được assign, observer offset từ Kafka broker chính là lớp bổ sung cần thiết.

## 11. Key distribution: partition yên lặng có thể là bình thường

Kafka producer thường chọn partition dựa trên key/partitioner. Khi record có cùng key, chúng thường được gửi vào cùng partition để giữ thứ tự theo key. Điều này dẫn đến phân bố có thể rất không đều.

Ví dụ business topic dùng key theo `customerId`:

~~~text
Customer A có 100.000 events -> P0
Customer B có 1 event      -> P2
Customer C không có event  -> không tạo traffic
P1 có thể không nhận record trong nhiều phút
~~~

Nếu user traffic tập trung ở một số key, những partition khác có thể idle dù hệ thống khỏe. Việc tăng partition count không bảo đảm record được chia đều theo tải.

### Khi nào idle là bất thường?

- Topic được thiết kế có **producer heartbeat định kỳ cho mỗi partition**.
- Producer có contract xuất dữ liệu theo shard/partition cố định.
- Mỗi partition phục vụ một tập nguồn dữ liệu và SLA yêu cầu nguồn nào cũng phải có cập nhật.
- Partition từng nhận dữ liệu ổn định với tần suất cao nhưng đột ngột không nhận trong thời gian dài.
- Sau deploy producer, nhiều partition đồng loạt idle còn một partition tăng đột biến: nghi ngờ thay đổi key/partitioner.
- Khi end offset không tăng ở partition bắt buộc phải có dữ liệu, dù nguồn upstream xác nhận đã tạo event.

### Khi nào không nên cảnh báo?

- Topic chỉ có traffic giờ hành chính.
- Traffic thưa, số partition lớn.
- Một số key không phát sinh business event trong thời gian bình thường.
- Topic dùng cơ chế key distribution tự nhiên có hot partitions và cold partitions.
- Hệ thống được bảo trì có chủ đích, có maintenance window được ghi nhận.

Cảnh báo theo **business expectation** thường đáng tin cậy hơn cảnh báo “mỗi partition idle quá 60 giây”.

## 12. Chọn ngưỡng idle phù hợp

Ngưỡng `idlePartitionEventInterval` phải dựa trên thời gian giữa hai record được kỳ vọng **tại mỗi partition**, không chỉ dựa trên tổng tốc độ của topic.

Một cách suy nghĩ:

~~~text
Expected records / partition / minute
  = topic_records_per_minute
    × expected_share_of_that_partition

Idle threshold
  > expected inter-arrival time
    + biến động lưu lượng
    + biên cho network/scheduling
~~~

Công thức chỉ là khung tư duy. Nếu traffic không đều hoặc mang tính burst, dùng phân bố thực nghiệm theo partition (p95/p99 inter-arrival time) thay vì chia đều số record cho số partition.

Ví dụ so sánh:

| Workload | Nhịp dữ liệu bình thường | Gợi ý thiết kế cảnh báo |
|---|---|---|
| CDC/event ingestion liên tục | Record đều mỗi vài giây tại mỗi shard | Ngưỡng theo expected shard throughput, kiểm tra end offset. |
| Giao dịch theo giờ | Có khoảng lặng tự nhiên ban đêm | Schedule-aware alerting; tránh cảnh báo trong quiet hours. |
| Heartbeat theo partition | Mỗi partition có heartbeat định kỳ | Ngưỡng lớn hơn chu kỳ heartbeat và jitter. |
| Topic nhiều partition nhưng traffic rất thấp | Có partition không nhận record hàng giờ | Không cảnh báo từng partition trừ khi có business SLA riêng. |
| Batch ingestion hằng ngày | Chỉ có dữ liệu trong cửa sổ batch | Theo dõi thời điểm batch hoàn tất và freshness, không dùng ngưỡng vài giây. |

Nên thiết lập **hai ngưỡng**: thời điểm phát hiện kỹ thuật và thời điểm cảnh báo nghiệp vụ. Ví dụ hệ thống có thể phát idle event sau 30 giây để ghi nhận, nhưng chỉ alert nếu partition quan trọng không nhận record quá SLA 10 phút và end offset không tăng.

## 13. Idle event lặp: cách tránh alert storm

Trong lúc partition tiếp tục idle, Spring Kafka có thể phát nhiều idle events theo interval. Nếu mỗi event làm gửi một email/notification, một topic có hàng trăm partition sẽ gây bão cảnh báo.

Thiết kế nên dùng state machine:

~~~mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> ACTIVE: Có record / baseline đủ
    UNKNOWN --> IDLE: Vượt idle threshold
    ACTIVE --> IDLE: PartitionIdleEvent
    IDLE --> IDLE: Idle event lặp
    IDLE --> ACTIVE: PartitionNoLongerIdleEvent
    ACTIVE --> UNKNOWN: Mất assignment / stop
    IDLE --> UNKNOWN: Mất assignment / stop
~~~

Mỗi chuyển trạng thái chỉ phát cảnh báo/thông báo khi cần; các idle events lặp có thể dùng cập nhật `lastObservedIdleAt` hoặc idle duration.

### Khóa trạng thái theo partition

Nếu theo dõi nhiều consumer groups, một khóa đơn giản là:

~~~text
Cluster + Environment + ConsumerGroup + Topic + Partition
~~~

Nếu cần phân biệt ownership/rebalance, bổ sung listener ID hoặc owner generation vào metadata riêng. Không dùng mỗi partition number vì partition 0 tồn tại trên nhiều topic, group hoặc cluster khác nhau.

### Ví dụ state tracker trong ứng dụng

~~~java
public record PartitionKey(String topic, int partition) { }

@Component
public class PartitionIdleState {

    private final Set<PartitionKey> idle =
            ConcurrentHashMap.newKeySet();

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        TopicPartition tp = event.getTopicPartition();
        PartitionKey key = new PartitionKey(tp.topic(), tp.partition());

        if (idle.add(key)) {
            log.warn("Partition entered idle state: {}", key);
        }
    }

    @EventListener
    public void onActive(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition tp = event.getTopicPartition();
        PartitionKey key = new PartitionKey(tp.topic(), tp.partition());

        if (idle.remove(key)) {
            log.info("Partition resumed receiving records: {}", key);
        }
    }
}
~~~

Đây là ví dụ tối giản để minh họa chống cảnh báo trùng. Trong production cần phân biệt cluster/group/listener khi cùng application context có nhiều nguồn event, xóa state khi revoke/stop, và giữ state bền vững hoặc tổng hợp tập trung nếu restart làm mất bộ nhớ.

Không dùng map trong-memory như **nguồn sự thật toàn cluster**; nhiều pod có bản sao state khác nhau và consumer assignments có thể thay đổi qua rebalance.

## 14. Metrics hữu ích khi điều tra partition idle

| Metric hoặc dữ liệu | Phạm vi | Dùng để kết luận điều gì? |
|---|---|---|
| Last received timestamp | Topic-partition tại consumer | Lần gần nhất container nhận record từ partition. |
| Idle duration | Topic-partition tại consumer | Thời gian không nhận record theo event. |
| Kafka log end offset | Topic-partition ở broker | Vị trí log hiện tại, có append thêm trong khoảng đo không. |
| Committed offset | Consumer group + topic-partition | Group đang ở vị trí nào. |
| Consumer lag | Group + topic-partition | Số khoảng offset còn cách end/LSO theo phép đo tương ứng. |
| Records consumed rate | Kafka consumer hoặc client metrics | Tốc độ nhận record ở consumer; cần xem granularity. |
| Partition assignment | Consumer group | Consumer nào hiện sở hữu partition. |
| Paused partitions | Container/consumer | Partition có bị chủ động ngừng fetch không. |
| Rebalance count/duration | Consumer group | Ownership thay đổi có làm gián đoạn dữ liệu không. |
| Nonresponsive poll signals | Consumer/container | Có thread poll đang bị treo/chặn không. |
| Producer send rate/error | Producer/topic | Producer có thực sự publish thành công đến Kafka không. |

Khi đặt metrics labels, dùng topic, partition, group, environment theo bộ giá trị có giới hạn; cân nhắc cardinality với số topic/partition lớn. Tránh dùng `eventId`, customer ID, order ID làm metric label.

### Last received time và last produced time

Một ứng dụng có thể lưu `lastReceivedAt` trong listener theo record timestamp nhận từ hệ thống. Nhưng Kafka record timestamp có thể là thời điểm producer tạo event từ trước; nếu lấy timestamp đó làm “last received”, idle duration bị sai.

Nên phân biệt:

- `lastReceivedAt`: thời điểm **consumer** nhận record.
- `record.timestamp()`: Kafka timestamp gắn với record.
- `event.createdAt`: thời điểm nghiệp vụ phát sinh.
- `lastBrokerAppendObservationAt`: thời điểm monitoring xác nhận log end offset thay đổi.

Nếu mục tiêu freshness của nghiệp vụ, có thể cần kết hợp nhiều loại thời gian.

## 15. Consumer pause: lý do đặc biệt

Spring Kafka cho phép pause listener/container hoặc partition trong những trường hợp nhất định. Pause giúp consumer tiếp tục giữ membership/poll nhưng tạm không nhận records từ những partition được pause.

Ví dụ ứng dụng dùng pause để thực hiện backpressure khi database quá tải. Trong lúc pause:

- Producer vẫn có thể append record vào partition.
- End offset của broker có thể tiếp tục tăng.
- Consumer không nhận record mới từ partition trong thời gian pause.
- Lag có thể tăng.
- Idle signal của listener có thể xuất hiện hoặc hành vi tùy theo cách Spring Kafka xét trạng thái pause và phiên bản.

Đừng phát cảnh báo "producer stopped" nếu nguyên nhân thực tế là **consumer đã pause có chủ đích**.

### Cách xử lý

1. Xác định container/partition có đang paused hoặc pauseRequested không.
2. Đọc nguyên nhân pause: backpressure, retry, maintenance hay operator action.
3. Kiểm tra thời điểm pause và policy resume.
4. Quan sát broker end offset và lag.
5. Resume khi downstream đã sẵn sàng; không bỏ qua record.
6. Xác minh listener nhận record trở lại và offset tiến đúng policy.

Không gọi `KafkaConsumer.resume(...)` từ background thread không được container quản lý. Dùng API container tương ứng, với lifecycle/poll coordination được Spring Kafka hỗ trợ.

## 16. Retry record có thể che giấu một partition không tiến

Nếu listener đọc record offset 500 rồi liên tục thất bại, error handler có thể giao lại cùng record nhiều lần. Trong trường hợp đó:

- Consumer **có record được giao lại**.
- Partition có thể **không bị xem là idle** theo cách quan sát nhận record.
- Committed offset có thể đứng yên ở 500 hoặc trước đó.
- Producer có thể tiếp tục ghi record mới, làm lag tăng.
- Listener có thể đang xử lý cùng một poison pill mà không tiến qua offset.

Do đó, để tìm partition “không có tiến triển” cần thêm một detector dựa trên **committed offset không thay đổi trong khi end offset tăng** hoặc **processing success không tiến**, chứ không chỉ idle event.

Ví dụ:

~~~text
P1:
  End offset       1.000 -> 1.200 -> 1.500
  Committed offset   500 ->   500 ->   500
  Listener retries offset 500 nhiều lần

=> P1 không idle theo nghĩa không nhận record,
   nhưng xử lý thực tế bị kẹt.
~~~

Khi điều tra, phân loại exception là transient hay permanent, kiểm tra `DefaultErrorHandler`, DLT recovery và backoff. Không bỏ qua offset 500 bằng seek/commit thủ công nếu chưa có chính sách recovery.

## 17. Tạo tín hiệu heartbeat có thực sự cần thiết?

Với topic mà mọi partition **bắt buộc** phải có tín hiệu định kỳ, doanh nghiệp có thể phát heartbeat. Nhưng Kafka không tự bảo đảm heartbeat sẽ đến mọi partition khi producer gửi record không key hoặc dùng key hashing thông thường.

Nếu muốn per-partition heartbeat, producer phải có cơ chế điều hướng record đến đúng partition hoặc một dịch vụ quan sát sử dụng dữ liệu broker để đánh giá. Cần cân nhắc:

- Heartbeat làm tăng throughput, chi phí lưu trữ và consumer processing.
- Heartbeat có thể thay đổi thứ tự/offset của topic.
- Consumer phải nhận biết heartbeat và không áp dụng nhầm business logic.
- Heartbeat không được dùng để che giấu việc event nghiệp vụ thực sự bị mất.
- Producer heartbeat còn sống không chứng minh luồng business data đã thành công.
- Nếu thêm partition mới, phải cập nhật định tuyến heartbeat phù hợp.

Trong nhiều hệ thống, **theo dõi end offset và business freshness** là lựa chọn rõ ràng hơn so với tạo heartbeat record cho mọi partition.

### Khi một partition đại diện một nguồn dữ liệu

Nếu partition được ánh xạ theo shard/source mà mỗi shard có SLA riêng, có thể giám sát theo partition tương đối chính xác. Nếu partition chỉ là kết quả hashing ngẫu nhiên theo key, SLA nên đặt theo **nguồn nghiệp vụ** hoặc aggregate, không mặc nhiên theo partition number.

## 18. Kiểm thử per-partition idle bằng Spring Kafka Test

Nên kiểm tra cả việc phát hiện idle và việc kết thúc trạng thái idle khi record trở lại, trong môi trường tích hợp có Kafka broker test phù hợp.

Một kịch bản với topic `orders.events` có hai partition:

1. Tạo topic hai partition trong môi trường test và consumer group test riêng.
2. Cấu hình `idlePartitionEventInterval` đủ ngắn cho test nhưng có biên scheduling.
3. Khởi động listener container và đợi partition assignment ổn định.
4. Publish record vào partition 0 nhưng **không publish vào partition 1**.
5. Đợi `ListenerContainerPartitionIdleEvent` tương ứng partition 1.
6. Kiểm tra listener container vẫn đang hoạt động và có thể xử lý partition 0.
7. Publish record vào partition 1.
8. Kiểm tra `ListenerContainerPartitionNoLongerIdleEvent` hoặc trạng thái nhận record trở lại theo phiên bản hỗ trợ.
9. Đối chiếu committed offset và record processing success.
10. Dừng container, bảo đảm test observer không giữ queue/thread nền làm treo shutdown.

Ví dụ producer chỉ rõ partition:

~~~java
kafkaTemplate.send(
        new ProducerRecord<>("orders.events", 0, "order-A", payloadA));

// Giữ partition 1 không có record trong cửa sổ test.

kafkaTemplate.send(
        new ProducerRecord<>("orders.events", 1, "order-B", payloadB));
~~~

`payloadA` và `payloadB` là dữ liệu test có serializer phù hợp. Test phải chờ assignment trước khi đo idle để tránh nhầm thời gian startup với thời gian không có record.

### Event recorder cho test

~~~java
@Component
public class PartitionIdleEventRecorder {

    private final BlockingQueue<TopicPartition> idleEvents =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        idleEvents.offer(event.getTopicPartition());
    }

    public TopicPartition awaitIdle(long timeout, TimeUnit unit)
            throws InterruptedException {
        return idleEvents.poll(timeout, unit);
    }
}
~~~

Đây là ví dụ ý tưởng ở môi trường test. Các import từ `java.util.concurrent` và Kafka `TopicPartition` cần được khai báo, và event API phải đối chiếu theo version. Với test, dùng một điều kiện chờ có timeout hữu hạn thay vì `Thread.sleep` không giới hạn hoặc assertion dựa trên thời điểm tuyệt đối.

Nếu topic có nhiều partition, test nên xác minh **đúng partition** được báo idle chứ không chỉ kiểm tra có bất kỳ idle event nào. Kafka Test/EmbeddedKafka có thể có chi tiết setup khác giữa các phiên bản Spring Boot/Spring Kafka.

## 19. Fault injection: kiểm thử phân biệt các loại không có dữ liệu

| Thử nghiệm | Cách tạo điều kiện | Tín hiệu mong đợi |
|---|---|---|
| Producer im lặng | Không gửi record đến partition đã assigned | Có thể phát partition idle event; broker end offset không tăng. |
| Chỉ một partition im lặng | Gửi đều vào P0, không gửi P1 | Container vẫn active; P1 idle riêng. |
| Container toàn bộ idle | Không gửi đến bất kỳ assigned partition nào | Có thể có container idle và partition idle events. |
| Listener bị chặn | Chặn có kiểm soát trong listener test | Poll không responsive; cần giám sát riêng, không chỉ idle. |
| Pause partition | Pause P1 theo container API | Consumer vẫn poll, P1 không nhận record; xem pause status. |
| Poison pill retry | Listener liên tục ném exception ở một offset | Offset không tiến và lag có thể tăng, dù vẫn có redelivery. |
| Rebalance | Thêm consumer member trong group | Ownership thay đổi; state idle phải cập nhật theo assignment. |
| Consumer stopped | Stop container theo lifecycle | Không coi thiếu idle events là topic có data. |

Không tạo fault injection trên consumer group hoặc Kafka cluster production đang xử lý dữ liệu thật, vì có thể gây rebalance, duplicate delivery và backlog.

## 20. Vận hành khi có nhiều replica

Một service chạy nhiều pod, mỗi pod có listener concurrency riêng. Mỗi child container theo dõi chỉ các partition hiện được assign, vì vậy event idle có thể phát từ những pod khác nhau sau rebalance.

Ví dụ:

~~~text
Replica A: P0, P1
Replica B: P2, P3

T1: P1 idle -> Replica A phát event.
T2: Rebalance, P1 chuyển sang Replica B.
T3: Nếu P1 tiếp tục idle, Replica B sẽ là nơi quan sát mới.
~~~

Hệ thống cảnh báo tập trung cần gộp các event theo **topic + partition + group** và theo dõi owner hiện tại để tránh mở hai incident do partition chuyển pod. Nên đặt metadata như assignment generation/observed-at khi có thể.

Nếu cùng một topic được đọc bởi hai consumer groups khác nhau, một partition có thể idle ở group A nhưng không idle ở group B do pause, offset/reset hoặc xử lý khác nhau. **Đừng gộp sự kiện idle của hai group thành một sự cố duy nhất** nếu chúng phục vụ mục đích riêng.

## 21. Thiết kế cảnh báo có ngữ cảnh

Một cảnh báo hữu ích nên trả lời:

- Topic, partition, consumer group nào bị ảnh hưởng?
- Phát hiện từ per-partition idle event hay broker offset sampler?
- Partition đó có được assign không? Owner hiện tại là ai?
- Consumer còn poll hay đã non-responsive?
- Partition có bị pause có chủ đích không?
- Broker end offset có tăng trong cửa sổ tương ứng không?
- Committed offset/lag ra sao?
- Lưu lượng vào partition này có được kỳ vọng theo SLA không?
- Có deployment, broker outage, producer change hoặc thời gian bảo trì liên quan không?

Ví dụ phân loại mức độ:

| Trạng thái | Bằng chứng | Hành động |
|---|---|---|
| Expected quiet | Không có traffic theo business schedule, end offset không tăng | Ghi nhận, không page. |
| Suspicious producer silence | Partition bắt buộc có dữ liệu nhưng end offset không tăng | Cảnh báo nguồn phát hoặc upstream. |
| Consumer delivery issue | End offset tăng nhưng consumer không nhận dù assigned | Điều tra pause, auth, fetch, polling và group. |
| Processing stalled | End offset tăng, committed offset đứng yên, retry lặp | Điều tra listener/error handler/DLT. |
| Consumer non-responsive | Poll interval bất thường, thread bị chặn | Điều tra timeout, GC, deadlock, max.poll interval. |
| Recovery | Partition nhận record lại và xử lý/offset tiến | Đóng incident sau stability window. |

Không dùng một ngưỡng idle chung cho mọi partition nếu phân phối lưu lượng khác nhau quá lớn.

## 22. Runbook: Partition idle nhưng các partition khác hoạt động tốt

1. Ghi nhận topic, partition, group, listener ID, thời gian idle và ứng dụng phát event.
2. Kiểm tra partition có nằm trong assignment hiện tại của consumer không.
3. Kiểm tra trạng thái pause của partition/container.
4. So sánh broker end offset ở hai thời điểm, tránh chỉ xem snapshot.
5. Đối chiếu producer metrics và cách chọn key/partition.
6. Kiểm tra lịch hoạt động, business SLA và khả năng traffic thấp tự nhiên.
7. Nếu producer dự kiến có event nhưng end offset không tăng, điều tra upstream/producer.
8. Nếu end offset tăng, điều tra consumer fetch, auth, assignment, retry và lag.
9. Khi dữ liệu trở lại, xác nhận partition no-longer-idle và processing/commit thực sự tiến.

Không reset offset hoặc đổi partitioner ngay lập tức khi chưa biết nguyên nhân.

## 23. Runbook: Cả topic im lặng đột ngột

1. Xác định tất cả partition đều không tăng end offset hay chỉ listener group không nhận record.
2. Kiểm tra producer deployments, rate, send failures, credentials, ACL và broker health.
3. Đối chiếu thời điểm ngừng traffic với lịch maintenance hoặc upstream outage.
4. Kiểm tra consumer group có member và partition assignment đầy đủ không.
5. Kiểm tra container idle events, poll health, consumer lag và paused state.
6. Nếu Kafka log không tăng, tập trung vào producer/upstream thay vì restart consumer liên tục.
7. Nếu log tăng mà consumer không nhận, tập trung vào consumer/network/security.
8. Khi khắc phục, đo backlog catch-up và event freshness, không chỉ đợi một idle event biến mất.

## 24. Runbook: Partition idle event xuất hiện liên tục và alert storm

1. Xác minh `idlePartitionEventInterval` hiệu lực và số partition.
2. Kiểm tra event lặp trên cùng topic-partition có đang tạo incident mới mỗi lần không.
3. Áp dụng state transition `ACTIVE → IDLE → ACTIVE`, chỉ cảnh báo khi chuyển trạng thái hoặc vượt SLA.
4. Kiểm tra ngưỡng có thấp hơn nhịp record thực tế không.
5. Nhóm sự kiện theo cluster, group, topic, partition và thời điểm.
6. Bổ sung lịch business/maintenance và nhóm partition có SLA riêng.
7. Theo dõi độ trễ observer và log volume để tránh ảnh hưởng consumer thread.

## 25. Runbook: Partition bị pause nhưng vẫn có backlog

1. Xác định pause ở cấp container hay partition, ai yêu cầu pause và từ lúc nào.
2. Đọc log/backpressure state của downstream hoặc retry subsystem.
3. So sánh end offset với committed offset để đo backlog.
4. Xác định pause còn cần thiết không, downstream đã phục hồi chưa.
5. Resume bằng Spring Kafka container API trên thread/lifecycle phù hợp.
6. Theo dõi record consumption rate, listener errors và offset tiến.
7. Kiểm tra idle/no-longer-idle events theo version và không xem chúng là điều kiện duy nhất để resume.

Không cưỡng ép resume khi hệ thống downstream vẫn đang quá tải hoặc transaction chưa ổn định.

## 26. Runbook: Committed offset đứng yên dù không thấy idle event

1. Xác định topic-partition có record mới đến hay không.
2. Kiểm tra listener có đang nhận và retry cùng một offset nhiều lần không.
3. Kiểm tra exception type, `DefaultErrorHandler`, backoff và DLT publish result.
4. Kiểm tra listener có offload asynchronous work chưa hoàn tất khiến ack bị trì hoãn không.
5. Kiểm tra Kafka transaction abort/fencing nếu listener dùng transaction.
6. Quan sát consumer poll interval và `NonResponsiveConsumerEvent`.
7. Khắc phục lỗi nghiệp vụ/hạ tầng hoặc recovery có kiểm soát.
8. Không commit vượt record chưa xử lý nếu chưa có policy recovery hợp lệ.

## 27. Runbook: Partition không có idle event sau rebalance

1. Kiểm tra partition hiện được assigned cho consumer nào.
2. Xác nhận container mới có cấu hình `idlePartitionEventInterval` và listener factory đúng.
3. Kiểm tra thời gian kể từ assignment và interval có đủ để phát event chưa.
4. Xem consumer/container đã started hay đang stopped/paused.
5. Kiểm tra observer `@EventListener` nằm trong cùng application context.
6. Kiểm tra logs, application event multicaster và executor nếu observer chạy bất đồng bộ.
7. Không khởi tạo state idle từ dữ liệu của owner cũ mà không đối chiếu owner generation.
8. Khi cần toàn cluster visibility, bổ sung broker offset sampler độc lập.

## 28. Runbook: Producer thay đổi key khiến nhiều partition đột ngột idle

1. So sánh phân bố record theo partition trước và sau deployment producer.
2. Kiểm tra thay đổi key serializer, key nullable, partitioner và partition count.
3. Xác định có một số key quá nóng hoặc toàn bộ record chuyển vào một partition không.
4. Đối chiếu ordering requirement theo aggregate trước khi thay đổi key.
5. Kiểm tra consumer lag và throughput theo partition: hot partition có thể thành bottleneck.
6. Khôi phục partitioner/khóa nghiệp vụ theo contract hoặc thay đổi thiết kế có kiểm soát.
7. Không tự tạo record giả để che giấu idle metrics nếu dữ liệu thực tế vẫn lệch.
8. Theo dõi phân bố và idle rates trong vài chu kỳ traffic sau khi sửa.

## 29. Bảng kiểm soát phát hiện partition không có message

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Idle configuration | `idlePartitionEventInterval` đã bật trên đúng container factory chưa? | Effective container properties và event logs. |
| Event scope | Đang dùng partition idle hay container idle event? | Event type và topic-partition metadata. |
| Assignment | Partition có được assign cho consumer quan sát không? | Group assignment và rebalance logs. |
| Poll health | Consumer có tiếp tục poll đúng nhịp? | Poll metrics, `NonResponsiveConsumerEvent`. |
| Pause | Partition/container có đang pause có chủ đích không? | Container pause state và reason. |
| Broker input | End offset có tăng theo thời gian không? | AdminClient/broker offset samples. |
| Consumer progress | Committed offset và lag có tiến không? | Group offsets, error handler logs. |
| Producer skew | Key/partitioner có khiến partition cold? | Per-partition producer rates, key distribution. |
| SLA | Partition có thực sự phải nhận message trong khoảng này không? | Business schedule, heartbeat/freshness contract. |
| Retry/DLT | Poison pill hoặc retry có giữ offset không? | Attempts, DLT send result, exception class. |
| Lifecycle | Rebalance/stop có làm state monitoring lỗi thời không? | Assigned/revoked/lost và container events. |
| Alert quality | Event lặp có tạo alert storm không? | State transitions, deduplication và alert history. |
| Recovery | Record trở lại có được xử lý/commit thành công? | No-longer-idle event, processing rate, committed offset. |

**Kết luận:** Phát hiện partition không có message đòi hỏi quan sát **từng partition**, không chỉ trạng thái chung của listener container. Spring Kafka hỗ trợ `idlePartitionEventInterval` cùng các event `ListenerContainerPartitionIdleEvent` và `ListenerContainerPartitionNoLongerIdleEvent` để ghi nhận khi một partition do consumer quản lý ngừng và bắt đầu nhận record trở lại. Nhưng idle event chỉ phản ánh **không nhận record**, không tự chứng minh producer đã dừng hay nghiệp vụ thất bại. Để vận hành chính xác, cần kết hợp assignment, trạng thái pause, poll health, log end offset, committed offset, consumer lag và SLA lưu lượng. Khi phân biệt được **expected quiet**, **producer silence**, **consumer delivery issue** và **processing stall**, hệ thống mới cảnh báo đúng chỗ và phục hồi mà không bỏ qua hay xử lý trùng message.
