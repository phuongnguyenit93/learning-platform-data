# ConsumerPausedEvent và ConsumerResumedEvent

Trong Spring Kafka, **ConsumerPausedEvent** và **ConsumerResumedEvent** là hai **application events** phản ánh việc một Kafka consumer do listener container quản lý **đã thực sự được pause hoặc resume**. Chúng đặc biệt hữu ích khi ứng dụng dùng pause/resume để thực hiện **backpressure**, hạn chế tải lên database, đợi một dependency phục hồi hoặc kiểm soát lưu lượng xử lý trong quá trình vận hành.

Điểm quan trọng nhất là phân biệt **yêu cầu thay đổi trạng thái** với **trạng thái đã có hiệu lực**. Khi một thread gọi **container.pause()**, Spring Kafka ghi nhận yêu cầu và áp dụng nó tại thời điểm phù hợp trong vòng poll của consumer. Vì vậy, việc method pause() trả về **không có nghĩa ngay lúc đó mọi partition đã được pause**. ConsumerPausedEvent giúp quan sát thời điểm consumer thực sự được pause; ConsumerResumedEvent đóng vai trò tương ứng khi resume.

Hai events này cung cấp khả năng quan sát lifecycle tốt hơn, nhưng **không tự xử lý offset, không dừng consumer group, không bảo đảm các business tasks đã hoàn tất và không thay thế error handler**. Sử dụng đúng cần kết hợp hiểu biết về KafkaConsumer poll loop, concurrent listener containers, pause theo partition, thread safety và trạng thái processing thực tế.

## 1. Vì sao cần quan sát pause/resume?

Giả sử service inventory-service tiêu thụ topic inventory.commands và cập nhật database. Khi database connection pool bị quá tải, tiếp tục nhận và xử lý thêm Kafka records có thể làm latency tăng, thread chờ kết nối nhiều hơn và cuối cùng gây lỗi hàng loạt.

Ứng dụng có thể yêu cầu pause:

~~~text
inventory.commands
        |
        v
Spring Kafka listener
        |
        v
Database connection pool
        |
        +-- tải bình thường --> xử lý tiếp
        |
        +-- vượt ngưỡng --> container.pause()
                                  |
                                  v
                             Pause requested
                                  |
                                  v
                        Consumer thực sự paused
                                  |
                                  v
                         ConsumerPausedEvent
~~~

Sau khi database ổn định:

~~~text
Backpressure controller
       |
       v
container.resume()
       |
       v
Resume requested
       |
       v
Consumer thực sự resumed
       |
       v
ConsumerResumedEvent
       |
       v
Tiếp tục giao records cho listener
~~~

Nếu chỉ log "pause called" và "resume called", người vận hành không biết request đã có hiệu lực chưa, có child consumer nào chưa đổi trạng thái hay không, hoặc một thread khác đã đảo lại yêu cầu. Application events bổ sung góc nhìn **observed state** từ container.

## 2. KafkaConsumer.pause() thực sự làm gì?

Ở tầng Kafka client, **KafkaConsumer.pause(Collection<TopicPartition>)** tạm dừng việc fetch/trả về records mới cho các partitions được chỉ định theo cơ chế KafkaConsumer. **resume(Collection<TopicPartition>)** tiếp tục tiêu thụ các partitions đó.

Pause **không phải** thao tác rời consumer group, không xóa assignment và không tự commit offsets.

~~~text
Consumer A sở hữu:
  orders/P0
  orders/P1

Pause orders/P1:
  ownership P0 -> vẫn thuộc A
  ownership P1 -> vẫn thuộc A

Polling:
  A vẫn poll để duy trì consumer group membership
  P0 có thể tiếp tục nhận records
  P1 tạm thời không giao records mới
~~~

Trong Spring Kafka, thông thường nên điều khiển bằng **listener container.pause()/resume()** thay vì lấy KafkaConsumer rồi gọi pause/resume trực tiếp từ một thread bên ngoài. KafkaConsumer không thread-safe cho mọi lời gọi; container là nơi phối hợp yêu cầu với consumer thread.

Pause giúp điều tiết nhịp độ nhận công việc mới. Nó **không tự hủy một database query đang chạy**, không hoàn tác HTTP request đã gửi và không loại bỏ records đã được listener nhận trước khi pause có hiệu lực.

## 3. Hai event phản ánh điều gì?

| Event | Điều kiện quan sát | Ý nghĩa vận hành |
|---|---|---|
| **ConsumerPausedEvent** | Container đã pause consumer theo yêu cầu/chính sách tương ứng | Consumer đã chuyển sang trạng thái paused đối với các partition được thông báo |
| **ConsumerResumedEvent** | Container đã resume consumer | Consumer đã tiếp tục tiêu thụ các partition được thông báo |

Các events có thông tin về partitions liên quan, cho phép ứng dụng phân biệt consumer nào hoặc tập partition nào bị ảnh hưởng.

Không nhầm các events này với:

- **ConsumerStoppedEvent**: consumer đã đóng/dừng lifecycle.
- **ConsumerStartingEvent/ConsumerStartedEvent**: consumer bắt đầu lifecycle.
- **ListenerContainerIdleEvent**: container không nhận record theo tiêu chí idle.
- **onPartitionsRevoked**: consumer nhường quyền sở hữu partition do rebalance.
- **onPartitionsLost**: consumer đã mất ownership.
- **BackOff/DefaultErrorHandler**: chính sách retry hoặc xử lý lỗi record.

Một consumer paused vẫn có thể đang chạy poll loop và giữ assignment. Vì vậy, **ConsumerPausedEvent không phải ConsumerStoppedEvent**.

## 4. Từ pause requested đến ConsumerPausedEvent

Spring Kafka quản lý thay đổi pause trong consumer thread để tránh gọi KafkaConsumer từ thread tùy ý. Một luồng điển hình:

~~~text
Thread giám sát / REST admin / scheduler
          |
          v
container.pause()
          |
          +-- ghi nhận pause requested
          |
          v
Consumer thread hoàn tất đoạn xử lý phù hợp
          |
          v
Vòng poll áp dụng consumer.pause(partitions)
          |
          v
Consumer ở trạng thái paused
          |
          v
Spring Kafka publish ConsumerPausedEvent
~~~

Khoảng thời gian giữa **pause requested** và **paused event** phụ thuộc vào trạng thái container:

- Listener đang xử lý một record dài hay không.
- Một poll đã lấy bao nhiêu records.
- Thuộc tính **pauseImmediate** có được bật không.
- Consumer đang trong rebalance hoặc xử lý error handler hay không.
- Container là single consumer hay concurrent container.
- Phiên bản Spring Kafka và các chi tiết lifecycle của nó.

Do đó, không dùng giá trị trả về của container.pause() như một hàng rào đồng bộ khẳng định mọi listener callbacks đã dừng. Đối với yêu cầu quan sát, **lắng nghe event và kiểm tra trạng thái container** là hai cách bổ trợ.

## 5. Từ resume requested đến ConsumerResumedEvent

Khi gọi container.resume(), container ghi nhận yêu cầu rồi thực hiện consumer.resume(...) tại thời điểm thích hợp trên consumer thread.

~~~text
Monitoring thấy dependency đã khỏe
          |
          v
container.resume()
          |
          v
Resume requested
          |
          v
Consumer thread áp dụng resume
          |
          v
Spring Kafka publish ConsumerResumedEvent
          |
          v
Consumer có thể tiếp tục nhận records
~~~

**ConsumerResumedEvent không có nghĩa record nghiệp vụ đầu tiên sau resume đã xử lý thành công**. Event phản ánh trạng thái tiếp tục tiêu thụ, còn kết quả xử lý phải đo bằng listener success rate, offset tiến triển, consumer lag và các metrics nghiệp vụ.

Trong một topic ít dữ liệu, sau ConsumerResumedEvent có thể chưa nhận được record mới nào. Đó không phải dấu hiệu resume thất bại nếu consumer đã ở trạng thái được phép consume.

Nếu ngay sau resume một controller khác lại yêu cầu pause, ứng dụng có thể quan sát các events liên tiếp. Cần ghi nhận **lý do pause** và kiểm soát quyền quyết định để tránh dao động.

## 6. Cấu hình Kafka listener có thể pause/resume

Một listener thông thường:

~~~java
@Component
public class InventoryCommandListener {

    private final InventoryService inventoryService;

    public InventoryCommandListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @KafkaListener(
            id = "inventory-listener",
            topics = "inventory.commands",
            groupId = "inventory-service")
    public void onCommand(InventoryCommand command) {
        inventoryService.apply(command);
    }
}
~~~

Để pause/resume, ứng dụng lấy listener container từ **KafkaListenerEndpointRegistry** bằng listener ID:

~~~java
@Service
public class InventoryConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public InventoryConsumerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestPause() {
        MessageListenerContainer container =
                registry.getListenerContainer("inventory-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void requestResume() {
        MessageListenerContainer container =
                registry.getListenerContainer("inventory-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

Các method này **gửi yêu cầu** tới container. Nếu registry không có listener ID, cần xem bean registration, autoStartup và cách container được tạo. Một listener container tạo thủ công ngoài registry có thể cần được quản lý bằng bean/reference riêng.

**Không tạo một KafkaConsumer mới chỉ để pause consumer đang chạy.** Consumer mới có identity, assignment và lifecycle khác.

## 7. Lắng nghe ConsumerPausedEvent với @EventListener

Spring application context có thể nhận events do Spring Kafka phát hành. Một observer đơn giản:

~~~java
@Component
public class KafkaPauseResumeObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeObserver.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused, partitions={}",
                event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed, partitions={}",
                event.getPartitions());
    }
}
~~~

Đoạn code minh họa pattern Spring application event. Cần imports thuộc gói listener events của Spring Kafka, @EventListener và logging tương ứng với dự án.

Event cung cấp ngữ cảnh của container phát sự kiện và các partitions liên quan. Để phân biệt nhiều listener containers, có thể xem **event source/container** theo API của phiên bản Spring Kafka đang dùng, kết hợp với listener ID và child container identity.

Nếu toàn ứng dụng chỉ có một listener, log partitions có thể đủ. Với hàng chục listeners và concurrent containers, cần bổ sung nguồn phát event để tránh nhầm lẫn.

## 8. Application events và thread thực thi

Trong Spring, **@EventListener không tự đồng nghĩa chạy bất đồng bộ**. Khi dùng ApplicationEventMulticaster đồng bộ mặc định, callback thường chạy trên **thread phát event**. Với Spring Kafka, nhiều consumer/container events được phát trên consumer thread.

~~~text
Consumer thread
     |
     +-- áp dụng consumer.pause()
     |
     +-- publish ConsumerPausedEvent
     |
     +-- gọi @EventListener đồng bộ
     |
     +-- quay lại poll/lifecycle loop
~~~

Do đó, event listener nên:

- Ghi log ngắn gọn.
- Cập nhật metric counter/gauge nhẹ.
- Lưu trạng thái quan sát vào cấu trúc thread-safe.
- Phát tín hiệu sang một coordinator khác nếu cần xử lý tốn thời gian.

Không nên:

- Gọi API bên ngoài có thể treo.
- Chạy database transaction dài.
- Chờ một CompletableFuture không có timeout.
- Gọi container.stop() đồng bộ ngay từ event callback trên consumer thread.
- Tự dùng KafkaConsumer lấy từ event để poll/commit từ thread khác.

Nếu cấu hình event multicaster chạy bất đồng bộ, không được giả định event handler vẫn chạy trên consumer thread. Phải kiểm soát thread safety và không sử dụng KafkaConsumer/reference nhạy cảm với thread trong callback async.

## 9. Vì sao không nên stop container từ event handler?

Một anti-pattern:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    MessageListenerContainer container = findContainer(event);
    container.stop();  // Tránh stop trực tiếp ở callback có thể trên consumer thread.
}
~~~

Trong ví dụ, findContainer là helper ứng dụng, không phải Spring Kafka API có sẵn.

Stop là thao tác lifecycle khác với pause. Nó có thể cần container hoàn tất poll loop, đóng consumer, commit pending offsets và bàn giao partitions. Nếu callback đang chạy trên consumer thread mà gọi stop đồng bộ, có nguy cơ làm shutdown reentrant, block consumer thread hoặc làm trạng thái lifecycle khó dự đoán.

Nếu hệ thống thực sự cần stop sau khi pause đã có hiệu lực, nên gửi yêu cầu tới một **lifecycle executor/coordinator riêng**, rồi để thread đó điều khiển stop. Không dùng event listener như nơi thực hiện trực tiếp những thao tác lifecycle có thể chờ chính container hiện tại.

Với backpressure tạm thời, thường **không nên stop**. Pause giúp giữ consumer group membership và tránh rebalance không cần thiết.

## 10. Phân biệt isPauseRequested và isContainerPaused

Spring Kafka cung cấp các API để quan sát trạng thái pause ở mức container.

| Kiểm tra | Trả lời câu hỏi |
|---|---|
| **isPauseRequested()** | Ứng dụng/container đang có yêu cầu pause hay không? |
| **isContainerPaused()** | Container đã đạt trạng thái paused theo semantics container hay chưa? |
| **ConsumerPausedEvent** | Lần chuyển trạng thái consumer sang paused đã được phát sự kiện chưa? |
| **ConsumerResumedEvent** | Lần chuyển trạng thái consumer sang resumed đã được phát sự kiện chưa? |

Ví dụ:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

if (container != null) {
    log.info(
            "running={}, pauseRequested={}, containerPaused={}",
            container.isRunning(),
            container.isPauseRequested(),
            container.isContainerPaused());
}
~~~

Không nên hiểu các trạng thái trên là một snapshot có tính nguyên tử tuyệt đối với mọi callbacks trong hệ thống. Một thread có thể requestResume ngay khi thread khác đọc trạng thái pause. Cần xác định **desired state** và **observed state** riêng nếu có nhiều nguồn gửi lệnh điều khiển.

Với concurrent listener container, isContainerPaused có thể chỉ báo true khi các child consumers liên quan thực sự đã pause theo semantics của parent. Một event từ **một child** không nhất thiết chứng minh **toàn parent** đã paused.

## 11. ConsumerPausedEvent không bảo đảm hết in-flight work

Một listener có thể nhận record rồi gửi nghiệp vụ sang ExecutorService:

~~~java
@KafkaListener(topics = "inventory.commands")
public void onCommand(InventoryCommand command) {
    workerPool.execute(() -> inventoryService.apply(command));
}
~~~

Đây là ví dụ cần thận trọng vì listener trả về trước khi công việc thật sự hoàn tất. Khi consumer được pause, worker pool vẫn có thể còn tác vụ đang chạy:

~~~text
12:00:00  Listener nhận event A, B, C
12:00:01  A, B, C được enqueue vào worker pool
12:00:02  Controller yêu cầu pause
12:00:03  ConsumerPausedEvent được phát
12:00:04  Worker vẫn xử lý B và C
~~~

Như vậy **ConsumerPausedEvent chỉ cho biết consumer đã pause**, không cho biết số tasks đang xử lý bằng 0.

Nếu cần điểm quiesce thật sự để bảo trì database:

1. Yêu cầu pause để ngừng đưa thêm records vào worker pool.
2. Đợi trạng thái paused được quan sát.
3. Theo dõi in-flight work bằng bộ đếm/registry riêng.
4. Chỉ bắt đầu bảo trì khi in-flight work đã drain trong deadline.
5. Nếu task không thể hoàn tất, sử dụng cơ chế retry/ack/idempotency phù hợp.

Không dùng ConsumerPausedEvent thay thế việc đếm in-flight tasks hoặc xác nhận database transaction đã commit.

## 12. Pause/resume và Kafka consumer group

Điểm khác biệt quan trọng giữa pause và stop là **consumer vẫn thuộc group khi paused**. Container tiếp tục poll theo cơ chế thích hợp để duy trì consumer group membership và đáp ứng broker/coordinator.

~~~text
Trước:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

A paused:
  Consumer A vẫn sở hữu P0, P1
  Consumer B vẫn sở hữu P2, P3

A resumed:
  Consumer A tiếp tục xử lý P0, P1
~~~

Pause/resume thường không cần rebalance chỉ vì lệnh pause/resume. Ngược lại, stop consumer có thể khiến partitions được phân phối lại.

Nhưng pause **không miễn trừ** mọi quy tắc group membership. Nếu listener xử lý quá lâu hoặc poll thread bị block, consumer vẫn có thể vượt **max.poll.interval.ms**, mất assignment và gây rebalance. Một event paused không bảo đảm assignment sẽ tồn tại mãi.

Với rolling deployment, pause cũng không thay thế stop/shutdown. Nếu pod bị terminate, process vẫn phải dừng theo lifecycle phù hợp, và partition ownership sẽ được group điều phối lại.

## 13. Pause sau poll hay pause sau record hiện tại?

Một chi tiết quan trọng là yêu cầu pause có hiệu lực khi nào:

~~~text
Consumer.poll() đã lấy:
  offset 10
  offset 11
  offset 12
  offset 13

Listener đang xử lý offset 10
  |
  +-- thread khác gọi container.pause()
~~~

Theo cách hoạt động thông thường, container có thể tiếp tục xử lý những records còn lại từ poll hiện tại rồi mới pause. Một số phiên bản Spring Kafka hỗ trợ **pauseImmediate** để việc pause có hiệu lực sau record hiện tại thay vì chờ hoàn tất toàn bộ records của poll.

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

Khi bật pauseImmediate, ứng dụng cần hiểu container có thể giữ những records chưa được giao từ poll trước để xử lý sau khi resume theo semantics của phiên bản đang sử dụng.

Quan trọng: **pauseImmediate không ngắt giữa chừng method business listener** và không làm biến mất một task đã được gửi vào background executor. Nó thay đổi điểm container tạm dừng giao records, không phải cơ chế cancellation.

## 14. Pause theo partition và pause toàn container

Có hai phạm vi điều tiết tải:

### Pause toàn container

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

if (container != null) {
    container.pause();
}
~~~

Phù hợp khi dependency chung như database connection pool bị quá tải và tất cả partitions của listener cần giảm nhịp.

### Pause theo TopicPartition

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

TopicPartition hotPartition =
        new TopicPartition("inventory.commands", 3);

if (container != null && container.isRunning()) {
    container.pausePartition(hotPartition);
}
~~~

Phù hợp khi chỉ một partition có workload hoặc dependency đặc thù. Resume tương ứng:

~~~java
container.resumePartition(hotPartition);
~~~

Với pause theo partition, một số phiên bản Spring Kafka cung cấp các events riêng ở mức partition, chẳng hạn **ConsumerPartitionPausedEvent** và **ConsumerPartitionResumedEvent**. Không nên mặc định một ConsumerPausedEvent của pause toàn consumer luôn xuất hiện cho mọi lần gọi pausePartition(), hoặc dùng event toàn consumer để suy ra chính xác trạng thái của tất cả partitions.

Thiết kế observer cần phân biệt **event phản ánh consumer-level pause/resume** và **event phản ánh partition-level pause/resume** theo API của Spring Kafka version đang chạy.

## 15. Event chứa thông tin partition để làm gì?

ConsumerPausedEvent và ConsumerResumedEvent giúp xác định **tập TopicPartition liên quan tới chuyển trạng thái**. Một TopicPartition bao gồm:

~~~text
TopicPartition
  topic: inventory.commands
  partition: 3
~~~

Ví dụ log:

~~~text
timestamp=12:01:22.500
event=consumer_paused
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
reason=database_saturation
~~~

Các trường listener và reason trong log là metadata do ứng dụng bổ sung; event framework không nhất thiết tự biết **lý do nghiệp vụ** của pause. Nếu lý do là backpressure, maintenance hoặc circuit breaker, controller phải ghi nhận lý do đó ở nơi quản lý trạng thái.

Không đưa từng offset hoặc record ID vào metric label cho pause/resume. Event phản ánh partition lifecycle chứ không liên quan đến một offset cụ thể.

## 16. Concurrent listener container và nhiều events

Với một @KafkaListener cấu hình concurrency lớn hơn 1, Spring Kafka có thể tạo một parent ConcurrentMessageListenerContainer và nhiều child KafkaMessageListenerContainer.

~~~text
Parent: inventory-listener
  |
  +-- child 0 -> Consumer A -> P0, P1
  |
  +-- child 1 -> Consumer B -> P2, P3
  |
  +-- child 2 -> Consumer C -> P4, P5
~~~

Khi gọi **pause() trên parent**, pause được điều phối tới các child consumers. Mỗi child có vòng poll và thời điểm áp dụng riêng. Vì vậy, các ConsumerPausedEvent có thể xuất hiện ở những thời điểm khác nhau.

~~~text
12:00:00.000  parent.pause()
12:00:00.080  child 1 paused -> event
12:00:00.150  child 0 paused -> event
12:00:00.310  child 2 paused -> event
~~~

Sơ đồ chỉ minh họa; không có bảo đảm thứ tự child events cố định.

**Một child đã pause không có nghĩa toàn parent đã pause.** Khi cần báo cáo trạng thái của cả listener, hãy kết hợp events theo source/child và API trạng thái của parent như isContainerPaused() thay vì nhận event đầu tiên rồi đặt một cờ global.

Khi rebalance, partition assignment giữa các child có thể thay đổi. Đừng hardcode mapping P3 luôn thuộc child 1.

## 17. Không dùng event count làm nguồn sự thật duy nhất

Giả sử một dashboard tăng counter khi nhận ConsumerPausedEvent và giảm khi nhận ConsumerResumedEvent:

~~~text
pausedCount += 1 khi paused
pausedCount -= 1 khi resumed
~~~

Cách này có thể sai trong nhiều trường hợp:

- Container stop trước khi có resume event.
- Ứng dụng restart và mất event history trong bộ nhớ.
- Rebalance thay đổi partition assignment.
- Một child container paused nhiều lần trong những chu kỳ khác nhau.
- Event delivery listener nội bộ gặp exception hoặc quan sát mất sự kiện.
- Pause/resume theo partition có events khác với pause/resume toàn consumer.

Vì vậy:

- Dùng event counter để đo **tần suất chuyển trạng thái**.
- Dùng state gauge hoặc poll API container để đo **trạng thái hiện tại**.
- Khi service restart, xây lại trạng thái từ các containers đang chạy.
- Khi container stop, loại trạng thái stale của child đã đóng.

Đối với operational dashboard, nên có **desired paused**, **observed paused** và **consumer running** thay vì một boolean duy nhất.

## 18. Thiết kế backpressure bằng hysteresis

Nếu hệ thống pause khi worker queue đạt 800 và resume khi queue xuống 799, tải dao động nhỏ có thể gây pause/resume liên tục.

Thiết kế tốt hơn là dùng hai ngưỡng khác nhau:

~~~text
Worker queue capacity: 1000

Queue size >= 800:
    request PAUSE

Queue size <= 300:
    request RESUME

300 < Queue size < 800:
    giữ trạng thái hiện tại
~~~

Ví dụ trình tự:

~~~text
queue=820 -> pause requested
            |
            v
        ConsumerPausedEvent

queue=690 -> vẫn paused
queue=450 -> vẫn paused
queue=280 -> resume requested
            |
            v
        ConsumerResumedEvent
~~~

Hai ngưỡng tạo ra **hysteresis**, giảm số lần đổi trạng thái và giảm rung lắc điều khiển.

Các con số chỉ là ví dụ. High/low watermark phải dựa trên throughput, tốc độ xử lý của downstream, memory budget và thời gian recovery thực tế.

Consumer lag sẽ tăng trong lúc pause nếu producer tiếp tục ghi vào Kafka. Đó là một sự đánh đổi có chủ đích để bảo vệ downstream; cần alert riêng cho trường hợp paused quá lâu hoặc lag vượt SLO.

## 19. Ví dụ BackpressureController có quan sát sự kiện

Một controller có thể duy trì trạng thái yêu cầu từ queue:

~~~java
@Component
public class InventoryBackpressureController {

    private final InventoryConsumerControl consumerControl;
    private final QueueDepthProbe queueProbe;
    private final AtomicBoolean pauseRequested = new AtomicBoolean();

    public InventoryBackpressureController(
            InventoryConsumerControl consumerControl,
            QueueDepthProbe queueProbe) {
        this.consumerControl = consumerControl;
        this.queueProbe = queueProbe;
    }

    @Scheduled(fixedDelay = 1_000L)
    public void evaluate() {
        int queueDepth = queueProbe.pendingJobs();

        if (queueDepth >= 800
                && pauseRequested.compareAndSet(false, true)) {
            consumerControl.requestPause();
        }
        else if (queueDepth <= 300
                && pauseRequested.compareAndSet(true, false)) {
            consumerControl.requestResume();
        }
    }
}
~~~

Các class QueueDepthProbe và InventoryConsumerControl là thành phần ví dụ của ứng dụng. Cần bật scheduling và khai báo imports/beans phù hợp.

AtomicBoolean trên chỉ là trạng thái **controller đã yêu cầu**; nó **không chứng minh consumer đã paused/resumed**. Nếu container không tồn tại, đã stopped hoặc request không được áp dụng, cờ controller vẫn có thể lệch trạng thái thực.

Trong production, nên:

1. Xác định desired state từ nhiều nguồn pause.
2. Ghi nhận action request và thất bại khi container không khả dụng.
3. Quan sát event và container APIs để biết observed state.
4. Đối chiếu state theo chu kỳ, có retry request hữu hạn nếu cần.
5. Tránh resume khi một lý do pause khác vẫn còn hiệu lực.

## 20. Nhiều lý do pause cùng lúc

Một ứng dụng có thể có nhiều nguồn muốn pause consumer:

- Database saturation.
- Circuit breaker mở.
- Maintenance window.
- Worker queue quá sâu.
- Operator pause thủ công.

Giả sử:

~~~text
12:00  database quá tải -> PAUSE
12:01  maintenance bắt đầu -> vẫn PAUSE
12:02  database phục hồi -> KHÔNG RESUME
12:10  maintenance kết thúc -> RESUME
~~~

Nếu controller database gọi resume ngay khi database phục hồi, nó có thể vô tình bỏ qua pause do maintenance đang giữ.

Một mô hình đơn giản là quản lý **set các pause reasons**:

~~~text
pauseReasons = {
  DATABASE_OVERLOAD,
  MAINTENANCE
}

Consumer phải pause nếu set không rỗng.
Consumer chỉ resume khi set rỗng.
~~~

Events ConsumerPausedEvent/ConsumerResumedEvent dùng để biết consumer có thực hiện thay đổi hay không, nhưng **không phải nguồn quyết định chính sách** và không tự lưu mọi pause reasons. Quyền điều khiển nên tập trung vào một service/coordinator.

## 21. Event handler nên phát metrics như thế nào?

Một observer có thể cập nhật metrics nhẹ:

~~~java
@Component
public class KafkaPauseMetricsObserver {

    private final MeterRegistry registry;

    public KafkaPauseMetricsObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        registry.counter("kafka_consumer_pause_events_total")
                .increment();
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        registry.counter("kafka_consumer_resume_events_total")
                .increment();
    }
}
~~~

Đoạn code giả định ứng dụng sử dụng Micrometer, MeterRegistry được cấu hình. Nó chỉ đếm **số lần event được nhận** chứ không đếm số partition hiện đang pause.

Để biết trạng thái hiện tại, có thể định kỳ lấy isPauseRequested()/isContainerPaused() từ registry và cập nhật gauge theo listener ID. Với parent concurrent container, nếu cần gauge từng child, phải xác định chính xác child identity qua lifecycle APIs thay vì suy ra từ số lượng event.

Các metric liên quan:

| Metric | Mục đích |
|---|---|
| Pause requests | Đếm số lần controller yêu cầu pause |
| ConsumerPausedEvent count | Đếm các sự kiện pause đã được container phát |
| Resume requests | Đếm số lần yêu cầu resume |
| ConsumerResumedEvent count | Đếm các sự kiện resume đã được container phát |
| Pause request-to-effective latency | Thời gian giữa request và event tương ứng |
| Current paused state | Trạng thái quan sát thực tại |
| Pause duration | Khoảng thời gian consumer đã paused |
| Consumer lag | Backlog Kafka đang tích lũy |
| Listener processing latency | Tải xử lý record và dependency |
| Queue depth | Áp lực lên worker pool hoặc downstream |

Pause duration hữu ích hơn event count nếu muốn biết một consumer đã bị kẹt trong trạng thái paused bao lâu.

## 22. Đo request-to-effective latency

Khi requestPause được gọi, ứng dụng có thể ghi timestamp. Khi nhận ConsumerPausedEvent tương ứng, tính độ trễ từ request đến khi event được quan sát.

~~~text
requestPause at 10:00:00.000
ConsumerPausedEvent at 10:00:00.150

Observed transition latency: khoảng 150 ms
~~~

Tuy nhiên, có các rủi ro khi đo:

- Concurrent container có nhiều child events cho một parent request.
- Một request mới có thể thay thế request cũ trước khi event đến.
- Assignment thay đổi làm số partitions trong event không giống lúc request.
- Event handler chạy bất đồng bộ có thể làm timestamp callback muộn hơn thời điểm pause thực tế.
- Nếu container đã paused từ trước, requestPause lặp lại có thể không tạo event chuyển trạng thái mới.

Một tracking implementation đáng tin cậy cần **request ID hoặc transition generation** trong controller, trạng thái theo container/child và thời điểm monotonic phù hợp với đo thời lượng. Không dùng mỗi event timestamp để suy ra chính xác SLA nếu không kiểm soát asynchronous dispatch.

## 23. Pause không đồng nghĩa không còn consumer.poll()

Một hiểu lầm phổ biến: consumer paused nghĩa là thread dừng poll.

Không đúng. Với Spring Kafka listener container, pause thường được thiết kế để **tiếp tục poll** nhằm duy trì group membership, trong khi không giao records mới cho các partitions paused.

~~~text
Consumer PAUSED
    |
    +-- poll
    +-- heartbeat/group management tiếp tục
    +-- poll
    +-- xử lý rebalance nếu có
    +-- poll
    +-- đợi resume
~~~

Vì thế CPU/network vẫn có thể có hoạt động nền trong lúc pause, và consumer vẫn cần broker connectivity.

Nếu listener đang xử lý một batch cực dài hoặc event handler chặn poll thread quá lâu, consumer vẫn có thể gặp max.poll.interval.ms dù đã gửi pause request. Pause không chữa được vấn đề thread bị block.

Để xử lý công việc kéo dài, cần cân nhắc max.poll.records, timeout, asynchronous processing/acknowledgment đúng cách và partition ownership.

## 24. Pause và commit offset

Pause/resume là cơ chế **điều khiển tốc độ tiêu thụ**, không phải API commit offset.

~~~text
P0 records:
  offset 100 -> processed
  offset 101 -> processed
  offset 102 -> in-flight
  offset 103 -> fetched, chưa xử lý

Pause request
    |
    v
ConsumerPausedEvent

Chỉ vì paused không có nghĩa offset 104 an toàn để commit.
~~~

Nếu chỉ record 100 và 101 hoàn tất, committed offset an toàn thường là 102, theo chính sách xử lý và consumer group. Nếu application tự commit 104 vì đã pause, records 102/103 có thể bị bỏ qua sau restart.

Với Spring Kafka, container quản lý commit theo **AckMode** và error-handler/transaction configuration. Nếu dùng manual acknowledgment, chỉ acknowledge record thật sự thành công. Nếu dùng transactional listener, offset có thể được đưa vào Kafka transaction với output records, không được tự commit ngoài transaction trong event handler.

**ConsumerPausedEvent không phải tín hiệu "all offsets committed"**. Nếu nghiệp vụ yêu cầu một barrier quiesce trước maintenance, phải kiểm tra thêm in-flight completion và commit/transaction outcomes.

## 25. ConsumerResumedEvent và backlog sau khi resume

Khi dependency phục hồi, consumer được resume và có thể gặp một lượng lớn records tồn đọng:

~~~text
Kafka input rate khi paused: 200 records/giây
Pause duration: 60 giây

Backlog mới: khoảng 12.000 records

Resume:
  consumer cố gắng bắt kịp backlog
~~~

Ví dụ trên giả định input rate ổn định và không có nhóm consumer khác xử lý cùng partitions đó. Sau resume, tốc độ xử lý bùng lên có thể lại làm database quá tải, gây vòng **pause → resume → pause**.

Để giảm rủi ro:

- Dùng hysteresis đủ rộng.
- Điều chỉnh max.poll.records và concurrency phù hợp.
- Giới hạn số business tasks in-flight.
- Dùng rate limit hoặc semaphore tại dependency boundary.
- Theo dõi backlog age và processing lag, không chỉ queue depth.
- Cân nhắc gradual recovery thay vì cho toàn hệ thống nhận tải lớn ngay lập tức.

ConsumerResumedEvent cho biết hệ thống sẵn sàng nhận records trở lại, **không bảo đảm tốc độ xử lý đã ổn định**.

## 26. Quan hệ với retry và backoff

Spring Kafka error handlers có thể sử dụng các chiến lược backoff, pause/resume partitions hoặc containers trong những tình huống nhất định. Tuy nhiên, cần phân biệt:

1. **Manual container pause**: ứng dụng hoặc operator chủ động yêu cầu pause.
2. **Pause do framework/backoff**: container hoặc error handling thực hiện điều tiết theo policy.
3. **Partition pause**: chỉ một hoặc vài partitions tạm ngừng.
4. **Non-blocking retry topic**: record lỗi được forward qua topic retry; consumer retry có thể chờ thời điểm đến hạn.

Không nên gộp mọi ConsumerPausedEvent thành kết luận "database overload". Reason nghiệp vụ không nhất thiết được event mang theo; cùng một observed event có thể bắt nguồn từ cơ chế khác trong ứng dụng.

Nếu có nhiều hệ thống cùng điều khiển pause, cần xác định nguồn sở hữu pause state, tránh một scheduler resume trong khi error handler vẫn cần giữ backoff.

Với retry và DLT, **pause không tự thay đổi số attempts**, exception classifier hoặc recovery policy. Nó chỉ ảnh hưởng khi consumer tiếp tục nhận/giao records.

## 27. Rebalance trong khi consumer đang paused

Pause không làm partition được bảo vệ tuyệt đối trước rebalance.

~~~text
Consumer A sở hữu P0, P1
    |
    +-- A pause P1
    |
    +-- consumer B tham gia group
    |
    v
Rebalance
    |
    +-- P1 có thể chuyển sang B
    |
    v
Assignment thay đổi
~~~

Khi assignment thay đổi, listener container phải áp dụng trạng thái pause phù hợp với partitions mà nó hiện sở hữu. Các events đã phát trước đó mô tả trạng thái ở **thời điểm cũ** và không phải bằng chứng vĩnh viễn về ownership.

Với pause theo partition, ứng dụng cần cân nhắc chính sách khi partition chuyển consumer:

- Pause policy áp dụng theo **topic-partition** hay theo **consumer instance**?
- Một partition mới được assign có cần tiếp tục pause do lý do nghiệp vụ không?
- Nếu consumer cũ mất partition, observer có xóa observed paused state stale không?
- Ai quyết định resume sau rebalance?

Không lưu một cờ paused trên mỗi partition mà bỏ qua event revoke/assigned và trạng thái container thực tế; một cờ cũ có thể khiến dashboard báo sai.

## 28. Container stopped khác container paused

Khi container stopped, consumer đã đóng và không còn poll. Pause/resume chỉ có ý nghĩa khi container còn chạy theo lifecycle.

~~~text
RUNNING
   |
   +-- pause() --> PAUSE_REQUESTED --> PAUSED
   |                                      |
   |                                      +-- resume() --> RUNNING
   |
   +-- stop()  --> STOPPING --> STOPPED
                                      |
                                      +-- start() --> RUNNING
~~~

Trạng thái trong sơ đồ là mô hình vận hành, không phải toàn bộ enum states được Spring Kafka expose.

Nếu container đã stopped, không dùng resume() như cách thay thế start(). Khi start, KafkaConsumer mới có thể join group và nhận assignment mới, rồi pause policy sẽ cần được áp dụng theo cấu hình hiện hành.

Đừng yêu cầu stop trực tiếp từ ConsumerPausedEvent handler khi handler chạy trên consumer thread. Nếu muốn stop theo một transition, offload sang lifecycle coordinator như phần thread safety đã nêu.

## 29. Tránh event-driven feedback loop

Một kiểu lỗi thiết kế là để hai observers phản ứng đối nghịch:

~~~text
Observer A:
  thấy ConsumerPausedEvent
  -> gọi container.resume() ngay

Observer B:
  thấy ConsumerResumedEvent
  -> gọi container.pause() ngay

Kết quả:
  pause/resume loop liên tục
~~~

Events nên chủ yếu phục vụ **observation**, còn **chính sách điều khiển** nên nằm trong một controller với desired state và lý do rõ ràng.

Nếu thật sự cần phản hồi event để phát lệnh mới, phải có:

- Điều kiện thay đổi state rõ ràng.
- Debounce hoặc minimum dwell time.
- Kiểm tra transition generation hiện tại.
- Idempotent request handling.
- Giới hạn số transitions/phút.
- Alert khi phát hiện oscillation.

Trong production, vòng lặp pause/resume không chỉ tăng log/metric noise mà còn khiến throughput dao động, khó dự đoán latency và dễ che lấp sự cố downstream thật sự.

## 30. Một mẫu observer lưu observed state

Ứng dụng có thể duy trì một projection nhẹ về events để hiển thị cho dashboard. Nếu chỉ có một listener, có thể bắt đầu đơn giản:

~~~java
@Component
public class PauseStateProjection {

    private final AtomicBoolean observedPaused =
            new AtomicBoolean();

    @EventListener
    public void whenPaused(ConsumerPausedEvent event) {
        observedPaused.set(true);
    }

    @EventListener
    public void whenResumed(ConsumerResumedEvent event) {
        observedPaused.set(false);
    }

    public boolean observedPaused() {
        return observedPaused.get();
    }
}
~~~

**Mẫu trên chỉ minh họa ý tưởng và không đúng cho nhiều consumers nếu dùng nguyên trạng**. Khi có nhiều child containers, một child resumed có thể đặt cờ false dù child khác vẫn paused.

Đối với concurrent container, cần một map theo identity của child/source cùng partition set, hoặc tính trạng thái parent bằng container APIs. Khi container stop/restart, projection cần xóa hoặc làm mới state để tránh báo paused vĩnh viễn.

Nếu application events được dispatch async, cần cập nhật projection thread-safe và không mặc định callbacks đến đúng thứ tự thực thi trên mọi thread. Có thể dùng sequence/timestamp do controller cấp hoặc kiểm tra lại trạng thái container trước khi khẳng định state cuối.

## 31. Quan sát bằng logs, metrics và traces

Để vận hành, nên liên kết các sự kiện pause/resume với **lý do nghiệp vụ** do controller giữ:

~~~text
event=pause_requested
listener=inventory-listener
cause=database_pool_saturation
queueDepth=850
requestedAt=12:00:00.000

event=consumer_paused
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
observedAt=12:00:00.120

event=resume_requested
listener=inventory-listener
cause=database_pool_recovered
queueDepth=260
requestedAt=12:01:30.000

event=consumer_resumed
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
observedAt=12:01:30.090
~~~

Đây là structured logs ứng dụng minh họa, không phải output mặc định của framework.

Một dashboard hữu ích có thể hiển thị:

- Desired vs observed pause state.
- Thời gian chuyển trạng thái.
- Số lần pause/resume trong một giờ.
- Consumer lag và tuổi record lâu nhất.
- Queue depth, DB pool utilization và downstream error rate.
- Paused duration theo listener/child consumer.
- Rebalance count và partition assignment changes.
- Listener processing latency trước/sau resume.

Khi consumer lag tăng, cần biết nó tăng vì pause chủ động, listener chậm, dependency lỗi hay group rebalance; chỉ theo dõi lag một mình không trả lời được.

## 32. Các tình huống lỗi vận hành

### Đã gọi pause() nhưng không thấy ConsumerPausedEvent

Kiểm tra container có đang running không, listener ID đúng không, poll thread có bị block không, pause request đã có hiệu lực chưa và event listener có được đăng ký trong ApplicationContext không.

Với concurrent container, cần kiểm tra các child consumers. Nếu một child xử lý record rất lâu, parent có thể chưa đạt trạng thái paused dù một số child đã phát event.

### Đã gọi resume() nhưng vẫn thấy container paused

Kiểm tra còn pause reason khác không, partition-specific pause vẫn còn không, controller khác có request pause lại không và consumer có đang trong rebalance không.

Không dùng ConsumerResumedEvent của một child để kết luận toàn bộ parent resumed.

### Có ConsumerResumedEvent nhưng không có record mới

Topic có thể trống, lag bằng 0, partition assignment thay đổi, consumer group đang ở committed offset cuối hoặc listener khác trong cùng group sở hữu partition. Kiểm tra subscription/assignment và broker connectivity trước khi kết luận resume thất bại.

### Pause được quan sát nhưng database vẫn còn nhiều request

Có thể business tasks đã được enqueue trước pause, listener đang hoàn tất batch hoặc các service khác vẫn dùng database. ConsumerPausedEvent không phải quiesce barrier cho mọi in-flight work.

### Pause/resume events xuất hiện liên tục

Kiểm tra hysteresis, nhiều controllers tranh chấp pause state, queue depth dao động và source của các events. Cần một điểm điều phối desired state chung.

### Consumer paused nhưng vẫn rebalance

Kiểm tra max.poll.interval.ms, listener callback blocking, group churn, deployment và session timeout. Pause không miễn trừ consumer group lifecycle.

### Event metrics báo sai số consumer đang pause

Có thể metrics đếm transitions nhưng được hiểu là current state, hoặc thiếu xử lý child stop/restart/rebalance. Dùng gauge trạng thái container và state reconciliation.

## 33. Kiểm thử integration: pause thật và resume thật

Mock ConsumerPausedEvent giúp kiểm tra observer nhưng không chứng minh KafkaConsumer thực sự pause. Bài kiểm thử đầy đủ nên dùng broker Kafka test như **EmbeddedKafka** hoặc **Testcontainers Kafka**.

### Test 1: pause toàn container

1. Tạo topic inventory.commands có nhiều partitions.
2. Khởi động listener và chờ assignment.
3. Gọi container.pause().
4. Chờ ConsumerPausedEvent từ listener observer.
5. Xác nhận isPauseRequested() và isContainerPaused() theo semantics container.
6. Gửi thêm record và kiểm tra listener không giao thêm records mới sau khi pause có hiệu lực.
7. Xác nhận consumer không phải stop/restart chỉ vì pause.

### Test 2: resume

1. Bắt đầu từ container đã paused.
2. Gọi container.resume().
3. Chờ ConsumerResumedEvent.
4. Xác nhận trạng thái pause đã kết thúc.
5. Xác nhận records còn trong Kafka tiếp tục được giao cho listener.
6. Kiểm tra offset commit và xử lý thành công theo AckMode.

### Test 3: pauseImmediate

1. Cấu hình batch poll với nhiều records.
2. Cho listener nhận một record rồi requestPause từ thread khác.
3. Chạy test với pauseImmediate theo cấu hình.
4. Xác nhận hành vi dừng giao records sau boundary mong đợi.
5. Resume và xác nhận records chưa xử lý được giao tiếp, không mất dữ liệu.

### Test 4: concurrent container

1. Tạo listener concurrency lớn hơn 1 và topic nhiều partitions.
2. Request pause trên parent.
3. Thu thập events từ các child consumers.
4. Xác nhận không kết luận toàn parent paused trước khi trạng thái parent đáp ứng.
5. Resume parent và xác nhận các child tiếp tục nhận records.

### Test 5: partition-specific pause

1. Assign ít nhất hai partitions cho consumer/container.
2. Pause một TopicPartition.
3. Xác nhận partition đó không giao records mới sau khi pause có hiệu lực.
4. Xác nhận partition khác vẫn xử lý được.
5. Resume partition đó và xác nhận records tiếp tục.
6. Nếu phiên bản có partition pause/resume events, kiểm tra đúng loại event.

### Test 6: controller hysteresis

1. Điều khiển QueueDepthProbe giả để tăng queue tới high watermark.
2. Xác nhận controller phát một pause request.
3. Giảm queue nhưng vẫn trên low watermark; không resume.
4. Giảm qua low watermark; phát một resume request.
5. Xác nhận không có vòng pause/resume bất thường.

### Test 7: in-flight processing

1. Cho listener enqueue một task dài hạn.
2. Request pause và chờ ConsumerPausedEvent.
3. Xác nhận task vẫn có thể đang chạy.
4. Chờ task hoàn tất hoặc xử lý theo timeout policy.
5. Kiểm tra acknowledgment/offset không vượt records chưa hoàn thành.

### Test 8: rebalance khi paused

1. Pause container.
2. Thêm hoặc dừng một consumer khác trong cùng group.
3. Quan sát rebalance và partition assignment mới.
4. Xác minh pause policy áp dụng đúng theo ownership hiện tại.
5. Xác minh observed state không giữ partitions đã bị revoke như state hiện tại.

Nên dùng condition-based waits có timeout thay vì sleep cố định và suy luận rằng events đã được phát. Kết quả cần dựa trên container state cùng callback observation và records thực sự được giao.

## 34. Những hiểu nhầm thường gặp

**Gọi container.pause() là consumer đã pause ngay.** Không đúng. Đây là yêu cầu; consumer thread áp dụng ở thời điểm phù hợp và có event khi trạng thái có hiệu lực.

**ConsumerPausedEvent nghĩa là consumer đã dừng poll.** Không đúng. Container thường tiếp tục poll để giữ group membership.

**ConsumerPausedEvent nghĩa là mọi business tasks đã hoàn tất.** Không đúng. Các in-flight tasks hoặc records đã poll có thể vẫn đang xử lý.

**ConsumerResumedEvent chứng minh event nghiệp vụ tiếp theo đã thành công.** Không đúng. Nó chỉ đánh dấu consumer đã resume.

**Pause luôn gây rebalance.** Không đúng. Pause thường giữ partition ownership; stop có thể gây rebalance.

**@EventListener luôn chạy trên thread riêng.** Không đúng. Event listener có thể chạy đồng bộ trên consumer thread; không nên block lâu.

**Có thể gọi KafkaConsumer.pause() từ bất kỳ thread nào.** Không đúng. KafkaConsumer không thread-safe cho truy cập tùy ý; ưu tiên Spring listener container APIs.

**Một child ConsumerPausedEvent có nghĩa toàn concurrent container paused.** Không đúng. Các child có poll/lifecycle riêng; cần quan sát parent hoặc đủ các child.

**ConsumerPausedEvent tự cho biết vì sao pause.** Không nhất thiết. Lý do nghiệp vụ phải do controller lưu và gắn vào log/metrics.

**Một counter số paused events chính là số consumers hiện paused.** Không đúng. Counter đo transitions, không phải trạng thái hiện tại.

**Pause đã có hiệu lực nghĩa offset đã commit hết.** Không đúng. Pause không phải offset commit hoặc transaction completion barrier.

**Resume có thể dùng để khởi động container đã stop.** Không đúng. Container stopped cần start theo lifecycle.

**Tăng max.poll.interval.ms là đủ để giải quyết mọi backpressure.** Không đúng. Cần kiểm soát tốc độ nhận work, thời gian xử lý, queue, thread và downstream capacity.

**Chỉ cần một boolean paused cho mọi listener.** Không đủ khi có nhiều containers, nhiều child consumers và nhiều nguyên nhân pause.

## 35. Hướng dẫn triển khai trong production

Khi ứng dụng cần dùng ConsumerPausedEvent và ConsumerResumedEvent cho reliability operations:

1. Xác định mục tiêu pause: giảm tải, chờ dependency, maintenance hay throttling theo partition.
2. Dùng **container.pause()/resume()** thay vì gọi KafkaConsumer trực tiếp từ worker threads.
3. Phân biệt **desired pause state**, **pause requested** và **pause thực sự có hiệu lực**.
4. Đăng ký @EventListener cho ConsumerPausedEvent/ConsumerResumedEvent và giữ callbacks ngắn.
5. Không gọi container.stop() đồng bộ từ event callback có thể chạy trên consumer thread.
6. Khi có concurrent container, theo dõi source/child identity và trạng thái parent thay vì một boolean toàn cục.
7. Nếu cần pause từng partition, dùng pausePartition/resumePartition và các partition-specific events theo phiên bản hỗ trợ.
8. Dùng high/low watermark, hysteresis và một controller thống nhất các pause reasons.
9. Không coi pause event là bằng chứng in-flight business tasks đã drain hoặc offset đã committed.
10. Dùng AckMode, error handler, transaction và idempotency phù hợp với mô hình xử lý.
11. Giám sát queue depth, consumer lag, pause duration, transition latency và processing throughput.
12. Kiểm tra rebalance/assignment changes và tránh stale pause state sau consumer restart.
13. Thiết kế recovery khi resume không làm throughput bùng lên quá mức.
14. Kiểm thử pause/resume thật trên Kafka broker, concurrency, pauseImmediate, partition pause và in-flight processing.

**ConsumerPausedEvent** và **ConsumerResumedEvent** cung cấp điểm quan sát quan trọng giữa lệnh điều khiển và trạng thái consumer thực tế. Khi kết hợp đúng với pause/resume APIs, chúng giúp xác nhận backpressure đã có hiệu lực, đo thời gian tạm dừng và phát hiện trạng thái lệch giữa controller với container. Tuy nhiên, chúng chỉ phản ánh **consumer lifecycle**, không thay thế xử lý offset, business task completion hoặc transaction boundaries. Một thiết kế vững chắc cần vừa điều khiển tải có chủ đích, vừa quan sát events, vừa duy trì khả năng xử lý lại dữ liệu an toàn khi consumer được resume hoặc rebalance.
