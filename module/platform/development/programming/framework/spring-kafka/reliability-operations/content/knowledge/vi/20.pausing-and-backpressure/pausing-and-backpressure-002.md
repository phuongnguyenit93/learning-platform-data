# Resume listener container

Trong Spring Kafka, khi downstream quá tải, database chạm giới hạn kết nối, worker queue gần đầy hoặc cần bảo trì một thành phần phụ thuộc, ứng dụng có thể **pause listener container** để tạm ngừng nhận thêm record vào đường xử lý nghiệp vụ. Nhưng pause chỉ là một nửa của quy trình backpressure: khi hệ thống đã phục hồi, ứng dụng phải **resume listener container** đúng thời điểm để tiếp tục tiêu thụ Kafka mà không làm mất record hoặc tạo một đợt tải đột ngột.

API chính là `MessageListenerContainer.resume()`. Phương thức này yêu cầu Spring Kafka **hủy trạng thái pause do container quản lý** và cho consumer tiếp tục lấy record từ những partition được phép tiêu thụ. Tùy vòng đời và thời điểm polling, resume có thể không có hiệu lực tức thì ở dòng lệnh gọi: container áp dụng thay đổi trên consumer thread trong chu kỳ poll phù hợp.

Resume **không giống** `start()`, không tương đương `seek()`, và không tự commit offset. Nó điều khiển việc tiêu thụ record sau một khoảng pause mà vẫn giữ consumer tham gia group nếu container đang chạy và poll định kỳ.

## 1. Bối cảnh: pause và resume giải quyết vấn đề gì?

Một consumer Kafka thường xử lý nhanh hơn hoặc chậm hơn downstream tùy thời điểm. Nếu lưu lượng đầu vào tăng nhưng downstream chỉ xử lý được một phần, tiếp tục nhận record liên tục có thể gây:

- Queue trong ứng dụng phình to, sử dụng nhiều heap.
- Thread pool bị bão hòa và phát sinh rejection.
- Database hết connection hoặc transaction kéo dài.
- HTTP downstream bị throttling hoặc timeout.
- Consumer mất khả năng xử lý poll kịp thời và tăng nguy cơ rebalance.
- Retry storm khi nhiều record cùng thất bại do một dependency đang yếu.

Backpressure chủ động cho phép giảm lượng công việc mới đưa vào ứng dụng:

~~~text
Kafka topic
    |
    v
Spring Kafka listener container
    |
    +---- Trạng thái RUNNING, không pause
    |         |
    |         v
    |      @KafkaListener
    |         |
    |         v
    |    Database / HTTP / worker queue
    |
    +---- Khi downstream quá tải
    |         |
    |         v
    |       pause()
    |         |
    |   Container tiếp tục poll để giữ group
    |   nhưng không chuyển thêm record mới tới listener
    |
    +---- Khi downstream đủ khỏe
              |
              v
           resume()
              |
              v
        Tiếp tục delivery và xử lý
~~~

Pause/resume là cơ chế **điều chỉnh tốc độ tiêu thụ**, không phải công cụ sửa dữ liệu lỗi. Nếu một record luôn ném exception do payload sai, resume không làm record tự hợp lệ; cần error handler, DLT hoặc quy trình recovery.

## 2. Các API quan trọng

Spring Kafka cung cấp khả năng pause/resume qua listener container, ví dụ `KafkaMessageListenerContainer` và `ConcurrentMessageListenerContainer`. Với `@KafkaListener`, ứng dụng thường lấy container từ `KafkaListenerEndpointRegistry`.

| API | Ý nghĩa | Lưu ý |
|---|---|---|
| `container.pause()` | Yêu cầu tạm ngừng tiêu thụ record của container | Không nhất thiết có hiệu lực ngay trên consumer thread |
| `container.resume()` | Yêu cầu hủy pause để tiêu thụ tiếp | Áp dụng theo chu kỳ poll/lifecycle |
| `container.isPauseRequested()` | Có yêu cầu pause của ứng dụng/container hay không | Phản ánh ý định, không phải bằng chứng mọi partition đã pause |
| `container.isConsumerPaused()` | Consumer đã thực sự ở trạng thái pause do container quản lý hay chưa | Với concurrent container, phải hiểu trạng thái của các consumer con |
| `container.isRunning()` | Container đang chạy hay không | Resume không thay thế việc start một container đã stop |
| `container.pausePartition(tp)` | Yêu cầu pause một partition cụ thể | Chỉ áp dụng ở phiên bản hỗ trợ partition-level pause |
| `container.resumePartition(tp)` | Cho partition đã pause tiếp tục | Không đồng nghĩa resume mọi partition |

Các phương thức partition-level và khả năng truy vấn trạng thái theo partition phụ thuộc phiên bản Spring Kafka; hãy kiểm tra API tương ứng với dependency của dự án.

### 2.1. Pause requested và consumer paused khác nhau

Giả sử một thread điều hành gọi `container.pause()` lúc listener vừa nhận một batch record:

~~~text
Thời điểm T0: container.pause()
              isPauseRequested() = true

Thời điểm T1: listener còn xử lý các record từ poll trước

Thời điểm T2: consumer thread tới điểm áp dụng pause
              isConsumerPaused() = true

Thời điểm T3: operator gọi container.resume()
              isPauseRequested() = false

Thời điểm T4: consumer thread áp dụng resume
              isConsumerPaused() = false
~~~

Đây là trình tự minh họa, không phải cam kết thời gian cụ thể. Không kết luận rằng `resume()` thất bại chỉ vì `isConsumerPaused()` vẫn true ngay trong dòng kế tiếp. Hãy đợi vòng poll phù hợp hoặc lắng nghe event resume.

### 2.2. Resume không commit offset

Offset đã commit của consumer group xác định vị trí đọc có thể phục hồi. `resume()` chỉ làm consumer tiếp tục có thể poll/deliver record, không phải thao tác `commitSync()` hay `acknowledge()`.

Nếu offset đã commit trước khi pause, sau resume consumer tiếp tục từ vị trí phù hợp theo trạng thái consumer. Nếu còn record chưa xử lý từ poll trước, container có thể tiếp tục xử lý chúng trước khi nhận thêm record mới, tùy cấu hình pause và listener.

## 3. Lấy listener container bằng KafkaListenerEndpointRegistry

Đối với ứng dụng dùng annotation `@KafkaListener`, cách phổ biến là đặt `id` ổn định trên listener rồi tra container bằng registry.

Ví dụ listener:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-processing")
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Lấy container và resume:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return false;
        }

        container.resume();
        return true;
    }
}
~~~

Trong ví dụ, `true` chỉ có nghĩa **đã gửi yêu cầu resume tới container đang chạy**, không chứng minh consumer đã thực sự resume hoặc một record mới đã được xử lý. Nếu cần xác nhận, theo dõi `isConsumerPaused()` và lifecycle events.

### 3.1. Vì sao cần id?

Registry cần một định danh để tìm đúng listener. Với nhiều `@KafkaListener`, tên method Java có thể trùng nhau giữa các bean hoặc không phản ánh container ID thực tế. Đặt `id` rõ ràng giúp vận hành tránh resume nhầm consumer.

Hãy khai báo `groupId` riêng để làm rõ consumer group. Trong Spring Kafka, ID của listener và group ID có thể ảnh hưởng lẫn nhau theo annotation semantics và phiên bản; chỉ định rõ giúp tránh đổi group ID ngoài ý muốn.

### 3.2. Registry không thấy container

`getListenerContainer("ordersListener")` có thể trả về null nếu:

- ID không khớp tên container đã đăng ký.
- `@KafkaListener` không được quét hoặc bean không được tạo.
- Container được tạo trực tiếp chứ không phải qua registry tương ứng.
- Người điều hành đang gọi ứng dụng instance khác.
- Cấu hình ứng dụng điều kiện hóa listener theo profile.

Không tự động gọi `start()` cho một ID bất kỳ chỉ vì registry trả về null. Hãy xác nhận listener đã được đăng ký và đúng lifecycle.

## 4. Resume khác start, stop và restart

Đây là điểm thường gây lỗi trong runbook.

| Thao tác | Consumer vẫn thuộc group? | Mục đích |
|---|---|---|
| `pause()` | Thông thường có, vì container vẫn poll | Ngừng delivery tạm thời, tránh thêm tải |
| `resume()` | Tiếp tục tiêu thụ trong container đang chạy | Kết thúc pause |
| `stop()` | Consumer dừng; group có thể rebalance | Kết thúc vòng đời container |
| `start()` | Tạo/khởi động consumer theo lifecycle | Khởi động lại container đã stop/chưa start |
| `seek()` | Thay đổi vị trí đọc của partition | Replay/điều chỉnh vị trí đọc có kiểm soát |

Nếu container đang `stop()`, gọi `resume()` không phải cách đúng để khởi động lại. Cần `start()` theo lifecycle và điều kiện vận hành phù hợp.

Nếu container đang chạy nhưng pause, `start()` không phải lệnh đối xứng với `pause()`. Hãy dùng `resume()`; không chủ động stop/start chỉ để tạo lại consumer nếu không cần.

### 4.1. Tại sao pause giữ consumer group ổn định?

Khi container pause, Spring Kafka vẫn tiếp tục gọi `poll()` theo cách quản lý của nó để consumer duy trì tương tác group/heartbeats. Điều này giúp hạn chế rebalance chỉ vì tạm ngừng delivery record.

Tuy vậy, pause không bảo đảm miễn nhiễm mọi rebalance. Consumer còn có thể mất group membership vì:

- Container stop hoặc process crash.
- Network/broker bất ổn.
- Listener xử lý một record quá lâu trước khi quay lại poll.
- Không đáp ứng `max.poll.interval.ms` trong các điều kiện cụ thể.
- Group thay đổi do scale-out hoặc rolling deploy.

Nói cách khác, pause giúp kiểm soát lượng công việc mới, nhưng không cứu được một listener đã block vô hạn trước khi container có cơ hội poll.

## 5. Khi nào resume có hiệu lực?

Spring Kafka không khuyến khích ứng dụng gọi trực tiếp `KafkaConsumer.resume(...)` từ một thread quản trị bất kỳ. KafkaConsumer không thread-safe cho các hoạt động tùy ý; container là thành phần sở hữu consumer và biết thời điểm an toàn để pause/resume.

Khi ứng dụng gọi `container.resume()`:

1. Yêu cầu pause do container quản lý được hủy.
2. Consumer thread áp dụng thay đổi trên những partition được phép resume trong chu kỳ poll thích hợp.
3. Container có thể nhận/deliver record tiếp theo.
4. Event resume có thể được publish khi trạng thái thực tế thay đổi.

Không nên viết loop busy-wait trên thread request:

~~~java
container.resume();
while (container.isConsumerPaused()) {
    // Sai: quay CPU liên tục, không có timeout.
}
~~~

Thay vào đó, response quản trị có thể trả `202 Accepted` với ý nghĩa “đã yêu cầu”, sau đó dùng state/event hoặc một health check để theo dõi chuyển trạng thái.

### 5.1. Poll timeout ảnh hưởng độ trễ điều khiển

Container thường áp dụng pause/resume quanh các điểm poll. Vì vậy, độ trễ chuyển trạng thái có thể phụ thuộc poll timeout, xử lý các record hiện tại và lịch chạy của consumer thread. Không đặt SLO “resume phải xong ngay lập tức” nếu chưa đo behavior thực tế.

### 5.2. Không nhầm polling với delivery

Trong trạng thái paused, container vẫn poll để duy trì consumer group nhưng không giao thêm record mới tới listener từ các partition paused theo cơ chế thông thường. Sau resume, poll có thể trả record và listener mới bắt đầu xử lý tiếp.

Nếu topic chưa có record hoặc lag bằng 0, consumer đã resume thành công nhưng listener có thể không nhận message mới ngay. Đừng coi “không có log listener” là bằng chứng resume lỗi.

## 6. pauseImmediate và record đã lấy từ poll trước

Mặc định, yêu cầu pause của listener container thường được áp dụng sau khi container xử lý xong các record từ lần poll hiện tại. Vì vậy, ngay sau `pause()`, listener có thể vẫn nhận thêm một số record **đã được poll trước đó**.

Spring Kafka có thuộc tính `ContainerProperties.pauseImmediate` từ các phiên bản hỗ trợ. Khi bật, container có thể pause sau khi xử lý record hiện tại, thay vì chờ hết tất cả record từ poll trước; những record còn lại được giữ trong memory để tiếp tục delivery sau resume.

Ví dụ cấu hình:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setPauseImmediate(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

Trong listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-processing",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

### 6.1. Diễn tiến minh họa

Giả sử poll trả năm records: offsets 100, 101, 102, 103, 104.

**Không bật pauseImmediate:**

~~~text
Poll: [100, 101, 102, 103, 104]
Process 100
pause() requested
Process 101, 102, 103, 104
Container applies pause before subsequent poll
~~~

**Bật pauseImmediate:**

~~~text
Poll: [100, 101, 102, 103, 104]
Process 100
pause() requested
Container pauses after current record
Retains [101, 102, 103, 104] in memory
resume() requested later
Container delivers retained records
~~~

Đây là sơ đồ nguyên lý cho record listener; số lượng record thực tế và cách container giao batch phụ thuộc phiên bản và listener type.

### 6.2. Resume không có nghĩa poll mới hoàn toàn

Khi `pauseImmediate` giữ records trong memory, sau resume container có thể giao **các record đã poll nhưng chưa xử lý** trước khi tiến tới batch mới. Đây không phải duplicate chỉ vì offset nhìn thấy không tăng so với thời điểm pause; các record đó đơn giản chưa được listener xử lý.

Nếu ứng dụng crash khi đang pause, records chưa được commit có thể được giao lại sau restart. Vì vậy, thiết kế side effects vẫn phải chịu được at-least-once/redelivery.

## 7. Resume khi dùng concurrency lớn hơn 1

Với `ConcurrentMessageListenerContainer`, một bean listener có thể chạy nhiều consumer con theo `concurrency`. Mỗi consumer con thường xử lý một tập partition được broker assign.

~~~text
@KafkaListener(id="ordersListener")
                |
                v
ConcurrentMessageListenerContainer
       |           |           |
       v           v           v
   consumer-0   consumer-1   consumer-2
   partitions   partitions   partitions
     [0,3]        [1,4]        [2,5]
~~~

Khi gọi `pause()` hoặc `resume()` trên **concurrent container cha**, Spring Kafka quản lý yêu cầu trên các consumer con theo thiết kế container. Không cần tự lấy KafkaConsumer từ từng listener thread để resume.

### 7.1. Ý nghĩa isConsumerPaused

Ở concurrent container, trạng thái aggregate `isConsumerPaused()` cần được hiểu trong bối cảnh nhiều consumer con: một số child có thể đã áp dụng pause/resume, một số vẫn đang hoàn tất record hoặc poll hiện tại.

Vì vậy:

- `isPauseRequested()` cho biết yêu cầu ở cấp container.
- `isConsumerPaused()` phản ánh trạng thái thực tế theo implementation của container.
- Event theo consumer/partition giúp xác minh quá trình chuyển trạng thái.
- Không giả định tất cả child threads thay đổi chính xác cùng một mili giây.

### 7.2. Multi-instance

Mỗi process/pod có một `KafkaListenerEndpointRegistry` riêng. Nếu hệ thống chạy bốn pods cùng group, gọi `resume()` trong pod A **không** ra lệnh cho consumer trên pods B, C, D.

Một admin API gọi vào một instance chỉ điều khiển consumer instance đó, trừ khi ứng dụng tự thiết kế cơ chế điều phối phân tán. Đối với lệnh pause/resume toàn deployment:

1. Có một control plane hoặc cấu hình chung xác định policy.
2. Mỗi pod tự reconcile trạng thái desired với container local.
3. Hệ thống ghi nhận pod nào đã áp dụng yêu cầu.
4. Operator chỉ tuyên bố toàn bộ deployment resumed khi các instance mục tiêu đã xác nhận.

Không nhầm thao tác local container với thao tác trên broker hay consumer group toàn cluster.

## 8. Resume chỉ một partition

Đôi khi một partition có lượng record lớn hoặc dữ liệu không phù hợp trong khi các partition khác vẫn xử lý tốt. Spring Kafka có API pause/resume ở cấp partition trong các phiên bản hỗ trợ:

~~~java
TopicPartition partition =
        new TopicPartition("orders.events", 2);

MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.resumePartition(partition);
}
~~~

API `resumePartition` chỉ hủy yêu cầu pause cho partition tương ứng; nó không nhất thiết hủy trạng thái pause toàn container nếu container vẫn đang được pause ở cấp container hoặc vì một nguyên nhân quản lý khác.

### 8.1. Khi nào dùng partition-level?

- Chỉ một partition cần giảm tải.
- Một tenant/business key tập trung vào một partition và cần cách ly tạm thời.
- Muốn khôi phục từng phần thay vì dồn tất cả backlog cùng lúc.
- Một partition được phép resume sau khi luồng dữ liệu của nó đã được sửa.

Tuy vậy, partition-level pause không thay thế retry/error handling cho poison pill. Nếu record sai định dạng, resume partition có thể lập tức tái tạo lỗi. Cần xử lý nguyên nhân trước.

### 8.2. Ownership và rebalance

Partition assignment có thể thay đổi do rebalance. Một partition đang thuộc consumer con A có thể chuyển sang consumer B. Trước khi điều khiển một partition, cần kiểm tra container có quản lý assignment phù hợp và API có áp dụng yêu cầu cho partition đó trong phiên bản đang chạy không.

Không dùng consumer group lag đơn thuần để suy ra partition đang thuộc process nào; assignment phải được lấy từ trạng thái group/container thực tế.

## 9. ConsumerPausedEvent và ConsumerResumedEvent

Spring Kafka có application events liên quan pause/resume, ví dụ `ConsumerPausedEvent` và `ConsumerResumedEvent`. Chúng hữu ích vì thể hiện **chuyển trạng thái thực tế** thay vì chỉ có lời gọi API gửi yêu cầu.

Ví dụ:

~~~java
@Component
public class KafkaPauseResumeEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeEvents.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: partitions={}",
                event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: partitions={}",
                event.getPartitions());
    }
}
~~~

Ví dụ dùng các event API có trong Spring Kafka, chi tiết package/field tùy phiên bản. Khi monitoring, nên kèm listener/container ID, service instance và timestamp để phân biệt nhiều consumer.

### 9.1. Không làm I/O nặng trong event callback

Application events có thể được phát đồng bộ tùy cấu hình `ApplicationEventMulticaster`. Nếu callback thực hiện HTTP request lâu hoặc block, nó có thể cản trở luồng xử lý của container.

Nên:

- Ghi log ngắn.
- Cập nhật local atomic state hoặc counters.
- Gửi metric qua instrumentation nhẹ.
- Nếu cần gọi hệ thống quản trị bên ngoài, đưa sự kiện sang pipeline bất đồng bộ có giới hạn và lỗi riêng.

Không gọi `resume()` liên tục ngay trong `ConsumerPausedEvent` chỉ vì thấy consumer paused, vì có thể tạo vòng lặp thay đổi trạng thái và phá mục tiêu backpressure.

## 10. Khi nào được phép resume?

Một quyết định resume tốt không chỉ dựa trên việc “đã qua 30 giây”. Cần kiểm tra resource gây pause đã thực sự đủ sức nhận thêm công việc.

Các tín hiệu hữu ích:

| Tín hiệu | Khi nào có thể resume? | Rủi ro nếu kiểm tra sai |
|---|---|---|
| Worker queue depth | Queue xuống dưới low-watermark | Queue có thể lại đầy ngay |
| Database connection utilization | Số kết nối rảnh ổn định | Resume tạo connection storm |
| HTTP downstream error rate | Lỗi/timeout trở về mức chấp nhận | Retry storm ngay sau resume |
| Circuit breaker | Chuyển sang trạng thái cho phép thử hoặc closed theo policy | Half-open bị quá tải |
| Recovery/DDL migration | Bước bảo trì hoàn tất | Consumer chạy trên schema chưa sẵn sàng |
| Disk/memory pressure | Memory giảm và không còn gần ngưỡng OOM | In-memory queue tiếp tục phình |
| Manual maintenance flag | Operator bỏ lệnh pause có chủ đích | Automation resume trái chỉ đạo |

Đừng resume chỉ dựa trên **lúc nào được pause**. Nếu nguyên nhân chưa được xử lý, resume thường chỉ tạo một đợt lỗi mới.

### 10.1. High watermark và low watermark

Để tránh container pause/resume liên tục khi queue depth dao động quanh một ngưỡng, dùng hysteresis:

~~~text
queue capacity = 1,000

>= 800 tasks pending: pause
<= 200 tasks pending: resume

201..799: giữ trạng thái hiện tại
~~~

Ví dụ:

~~~text
Pending: 100 -> 500 -> 850 : PAUSE
Pending: 850 -> 650 -> 250 : still PAUSED
Pending: 250 -> 190        : RESUME
Pending: 190 -> 420        : still RUNNING
~~~

Khoảng cách giữa hai ngưỡng giảm flapping. Chọn ngưỡng theo tốc độ xử lý, queue capacity, memory và độ trễ của downstream, không sao chép giá trị của ví dụ vào production.

## 11. Ví dụ BackpressureCoordinator tự resume khi khỏe lại

Một coordinator có thể định kỳ quan sát queue depth và trạng thái downstream, sau đó reconcile listener container theo policy.

~~~java
@Component
public class OrdersBackpressureCoordinator {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 200;

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMeter queueMeter;
    private final DownstreamHealth downstreamHealth;

    public OrdersBackpressureCoordinator(
            KafkaListenerEndpointRegistry registry,
            WorkQueueMeter queueMeter,
            DownstreamHealth downstreamHealth) {
        this.registry = registry;
        this.queueMeter = queueMeter;
        this.downstreamHealth = downstreamHealth;
    }

    @Scheduled(fixedDelay = 1_000)
    public void reconcile() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int pending = queueMeter.pending();
        boolean healthy = downstreamHealth.isReady();

        if (!healthy || pending >= HIGH_WATERMARK) {
            if (!container.isPauseRequested()) {
                container.pause();
            }
            return;
        }

        if (pending <= LOW_WATERMARK
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

`WorkQueueMeter` và `DownstreamHealth` là abstraction nghiệp vụ minh họa, không phải class có sẵn của Spring Kafka. Cần bật scheduling bằng `@EnableScheduling` (hoặc configuration tương đương) nếu dùng `@Scheduled`.

Coordinator này minh họa cơ chế tự động pause/resume theo queue và dependency health. Trong hệ thống thực tế cần xử lý **nhiều nguyên nhân pause** và **manual override** để không tự resume một listener mà operator đang cố tình giữ pause.

### 11.1. Nhiều nguyên nhân pause: đừng để một nguồn resume nhầm

Giả sử có ba lý do:

- `QUEUE_FULL`.
- `DOWNSTREAM_UNHEALTHY`.
- `MANUAL_MAINTENANCE`.

Nếu queue đã giảm, scheduler gọi `resume()` trong khi operator vẫn đang bảo trì database, listener sẽ nhận tải quá sớm. Container API không phải một hệ thống quản lý “pause reason” đầy đủ; ứng dụng cần lưu desired state riêng.

Một mô hình tốt:

~~~text
Desired state = PAUSED
if any pause reason is active

Desired state = RUNNING
only if all pause reasons are cleared

Reconciler:
  desired PAUSED  -> container.pause()
  desired RUNNING -> container.resume()
~~~

Có thể dùng một tập lý do pause đồng bộ trong application control plane và ghi log chuyển trạng thái. Tránh để health checker, operator API và queue monitor gọi `resume()` độc lập mà không biết nhau.

## 12. Manual resume qua API quản trị

Đôi khi đội vận hành muốn resume thủ công sau maintenance. Một service quản trị có thể cung cấp thao tác yêu cầu resume:

~~~java
@RestController
@RequestMapping("/internal/kafka/listeners")
public class KafkaListenerAdminController {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerAdminController(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @PostMapping("/orders/resume")
    public ResponseEntity<String> resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            return ResponseEntity.notFound().build();
        }
        if (!container.isRunning()) {
            return ResponseEntity.status(409)
                    .body("Container stopped; start is required");
        }

        container.resume();
        return ResponseEntity.accepted()
                .body("Resume requested");
    }
}
~~~

Ví dụ trên là skeleton, không bao gồm xác thực hoặc state coordinator. Trong production, endpoint phải:

- Yêu cầu authentication và authorization ở mức operator.
- Không phơi trực tiếp ra public internet.
- Ghi audit ai ra lệnh, khi nào, lý do gì.
- Xác nhận downstream thực sự sẵn sàng.
- Tương tác với central pause reason state thay vì bypass policy.
- Trả ý nghĩa “requested”, không tuyên bố đã áp dụng ở tất cả consumers.

Nếu listener đang được pause vì bảo trì có chủ đích, API resume nên xóa lý do bảo trì rồi để coordinator reconcile; không gọi `resume()` trực tiếp trái state mong muốn.

### 12.1. Manual resume trong hệ thống nhiều pods

HTTP request thường chỉ tới một pod qua load balancer. Vì vậy, kết quả `202 Accepted` từ một pod không chứng minh tất cả pods đã resume.

Để điều khiển toàn bộ group, có thể dùng một management job gửi yêu cầu đến mỗi instance hoặc một config/coordination store chung mà mỗi instance theo dõi. Cần xác nhận trạng thái từng instance trước khi hoàn tất thao tác trên dashboard.

## 13. Những điều pause/resume không xử lý thay bạn

### 13.1. In-flight records vẫn cần hoàn tất an toàn

Pause là chặn việc nhận thêm/deliver thêm record, không phải rollback hoặc cancel tự động tất cả công việc đang thực hiện. Record đang được listener xử lý có thể vẫn chạy khi pause được yêu cầu.

Nếu listener gọi database và commit trước khi pause, offset commit vẫn được container thực hiện theo ack mode và transaction policy. Nếu listener thất bại, error handler/retry phải xử lý lỗi riêng.

### 13.2. Queue async không tự an toàn

Một pattern nguy hiểm:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener trả về trước khi task hoàn tất.
}
~~~

Nếu container coi listener thành công và commit offset trước khi worker hoàn tất, process crash có thể làm mất tác động nghiệp vụ. Pause/resume không sửa được lỗi này.

Với asynchronous processing, cần:

- Ack/commit chỉ sau khi side effect bền vững hoặc recovery thành công.
- Worker queue có giới hạn capacity.
- Error propagation và retry/DLT cho worker failure.
- Concurrency và acknowledgement semantics phù hợp với phiên bản Spring Kafka.
- Cơ chế backpressure ngăn queue tiếp tục nhận khi đã gần đầy.

### 13.3. Resume không làm biến mất duplicate delivery

At-least-once consumer có thể xử lý lại record sau crash trước commit. Khi resume sau pause, record chưa commit cũng có thể tiếp tục được giao lại theo lifecycle. Business handler cần idempotency qua event id/inbox/unique constraint hoặc một cơ chế tương đương.

### 13.4. Resume không sửa seek position

Nếu operator đã điều chỉnh offset group hoặc container đã seek đến vị trí khác, `resume()` không đảo ngược thao tác seek. Đừng dùng resume như cách “quay về offset trước khi pause”; nó không có chức năng lưu một checkpoint riêng độc lập với Kafka offset.

## 14. Khi framework tự pause consumer

Không phải mọi pause đều bắt nguồn từ nút pause của operator. Spring Kafka còn có thể tạm dừng consumer do error handling, backoff hoặc chế độ acknowledgement đặc biệt.

Ví dụ, với `asyncAcks`, container có thể pause delivery khi còn những acknowledgements từ poll trước chưa hoàn tất. Khi các ack còn thiếu được xử lý đủ, container mới có thể tiếp tục an toàn theo semantics của chế độ này.

### 14.1. Gọi resume không vượt được mọi cơ chế nội bộ

Nếu framework còn lý do phải giữ consumer paused, yêu cầu `resume()` của ứng dụng có thể không làm listener nhận record ngay. Trước khi cưỡng ép xử lý:

1. Xác định ai đã yêu cầu pause.
2. Kiểm tra manual/app-level pause request.
3. Kiểm tra error handler/backoff hiện hành.
4. Kiểm tra outstanding manual acknowledgements, đặc biệt nếu dùng `asyncAcks`.
5. Kiểm tra partition pause riêng.
6. Xác nhận container vẫn running và consumer có assignment.

Không cố “chữa” consumer đứng chờ bằng cách gọi `resume()` liên tục trong vòng lặp. Nếu ack còn thiếu hoặc error handler chưa hoàn tất, cần giải quyết điều kiện gây chờ.

### 14.2. Partition paused và container paused

Nếu ứng dụng gọi `resume()` toàn container nhưng vẫn còn partition-level pause requests, những partition đó có thể tiếp tục paused. Ngược lại, gọi `resumePartition(tp)` không tự xóa pause request cấp container.

Khi điều tra, hãy kiểm tra cả hai cấp trạng thái và API khả dụng trong Spring Kafka version triển khai.

## 15. Consumer lag sau khi resume

Trong thời gian pause, producer vẫn có thể ghi dữ liệu mới vào topic. Consumer group không xử lý record mới nên lag thường tăng. Sau resume, consumer sẽ cần xử lý backlog:

~~~text
Time --------->
Input rate:   100 100 100 100 100 100
Consume rate: 100   0   0   0 150 150
State:        RUN PAUSE PAUSE RUN RUN RUN
Lag:            0 100 200 300 250 200 ...
~~~

Các con số chỉ minh họa. Nếu năng lực xử lý sau resume chỉ bằng đúng tốc độ producer tiếp tục ghi, backlog sẽ **không giảm**. Để bắt kịp, năng lực xử lý ròng phải lớn hơn tốc độ dữ liệu vào, hoặc hệ thống phải có thời gian/scale phù hợp.

### 15.1. Resume có thể tạo burst

Nếu nhiều consumers được resume đồng thời sau sự cố downstream, tất cả có thể bắt đầu tiêu thụ backlog và gây quá tải trở lại.

Biện pháp:

- Resume theo từng instance hoặc partition khi cần.
- Hạn chế concurrency/worker queue phù hợp.
- Dùng rate limiter hoặc adaptive backpressure ở application layer.
- Giữ high/low watermark để pause lại khi thật sự cần.
- Theo dõi database pool, downstream latency và error rate trong giai đoạn bắt kịp backlog.

Không giả định pause/resume tự giới hạn record rate. Nó là trạng thái bật/tắt delivery, không phải token-bucket rate limiter.

### 15.2. Resume khi lag cao không nhất thiết là sự cố

Lag cao ngay sau resume thường là hậu quả dự kiến của một khoảng pause. Điều cần theo dõi là:

- Lag có **giảm dần** không?
- Oldest record age có về dưới SLA không?
- Error/retry rate có thấp trở lại không?
- Downstream latency có ổn định không?
- Có xuất hiện vòng lặp pause/resume không?

Một dashboard chỉ hiển thị giá trị lag tại một thời điểm có thể gây hiểu nhầm. Nên có xu hướng lag và processing rate.

## 16. Metrics và logs cho pause/resume

| Metric hoặc trạng thái | Ý nghĩa |
|---|---|
| Pause requested | Ứng dụng đã yêu cầu pause hay chưa |
| Consumer paused | Trạng thái pause thực tế của container/consumer |
| Pause duration | Một đợt pause kéo dài bao lâu |
| Resume request count | Số lần yêu cầu resume |
| Resume applied/event count | Số lần resume thực tế được áp dụng |
| Consumer lag per partition | Backlog đang tăng hay giảm |
| Record processing rate | Khả năng xử lý sau resume |
| Oldest unprocessed record age | Độ trễ theo SLA |
| Worker queue depth | Áp lực trong ứng dụng |
| Downstream error/latency | Dependency đã thực sự phục hồi chưa |
| Rebalance count | Group có mất ổn định khi pause/restore không |

Không phải tất cả metric này có sẵn tự động với tên giống bảng. Có thể dùng Micrometer, Kafka client metrics, application events và instrumentation riêng.

### 16.1. Structured logging

Ví dụ một log chuyển trạng thái:

~~~text
event=kafka_listener_resume_requested
service=orders-worker
instance=pod-a
listenerId=ordersListener
groupId=order-processing
reasonCleared=QUEUE_FULL
queueDepth=170
downstreamHealthy=true
requestedPause=false
~~~

Và khi đã có event ứng dụng:

~~~text
event=kafka_consumer_resumed
instance=pod-a
listenerId=ordersListener
partitions=orders.events-0,orders.events-2
~~~

Đây là ví dụ format log, không phải Spring Kafka mặc định xuất đúng những field này. Không log payload, credentials hoặc Kafka record key nhạy cảm chỉ để chẩn đoán resume.

### 16.2. Cảnh báo hữu ích

- Container vẫn paused quá thời gian cho phép khi downstream đã khỏe.
- Resume requested nhưng không quan sát được resume applied sau khoảng chờ hợp lý.
- Queue depth vẫn cao dù consumer đã pause lâu.
- Lag tiếp tục tăng không giới hạn sau resume.
- Pause/resume flapping quá nhiều lần trong vài phút.
- Một instance không resume trong khi các instance khác đã chạy.
- Consumer container không running nhưng operator nghĩ nó chỉ paused.

Nên kết hợp pause reason, poll state và downstream health để alert có ích. Không page chỉ vì một consumer đang paused trong planned maintenance.

## 17. Runbook: gọi resume nhưng listener vẫn im lặng

1. Lấy đúng listener ID từ `KafkaListenerEndpointRegistry`.
2. Xác nhận `container != null` và `container.isRunning() == true`.
3. Kiểm tra `isPauseRequested()` có còn true không.
4. Kiểm tra `isConsumerPaused()` và ConsumerResumedEvent.
5. Kiểm tra có partition-level pause requests chưa được xóa không.
6. Kiểm tra framework đang giữ pause vì `asyncAcks`/error handler hay không.
7. Kiểm tra consumer group assignment và partition ownership.
8. Kiểm tra topic có record mới hoặc consumer lag còn lớn hơn 0 không.
9. Kiểm tra listener có đang block xử lý record từ poll trước không.
10. Kiểm tra logs/error/rebalance để tìm nguyên nhân khác.

Nếu container đã resume nhưng topic không có record mới, listener im lặng là bình thường. Nếu container stop, dùng lifecycle start theo quy trình thay vì spam resume.

## 18. Runbook: resume xong consumer lập tức pause lại

1. Xem pause reason state của coordinator.
2. Kiểm tra queue depth có vẫn vượt HIGH_WATERMARK không.
3. Kiểm tra downstream error rate/circuit breaker có còn đánh giá unhealthy không.
4. Kiểm tra operator/manual maintenance flag có còn hoạt động không.
5. Xác định có nhiều scheduler/controller cùng gọi pause/resume không.
6. Kiểm tra metrics timestamps để biết lần pause mới do ai phát sinh.
7. Nếu queue chưa có khả năng giảm, điều chỉnh worker throughput hoặc dependency chứ không chỉ tăng resume attempts.

Đây thường là dấu hiệu policy đúng đang ngăn tải quá mức, hoặc hai controller tranh quyền điều khiển. Tránh chỉnh threshold một cách mù quáng chỉ để metric pause về false.

## 19. Runbook: sau resume xuất hiện duplicate records

1. Xác định duplicate là cùng topic/partition/offset được giao lại hay hai event khác nhau có payload giống nhau.
2. Kiểm tra offset đã commit trước pause và sau resume.
3. Kiểm tra crash/rebalance trong thời gian pause.
4. Kiểm tra listener có ghi side effect trước khi offset commit không.
5. Kiểm tra manual ack và async worker có hoàn tất bền vững trước acknowledge không.
6. Kiểm tra error handler đã seek lại record chưa được xử lý hay chưa.
7. Xác nhận idempotency key và database uniqueness constraint.

Resume không tự tạo exactly-once end-to-end. Duplicate delivery có thể là kết quả hợp lệ của at-least-once semantics. Cần deduplication nghiệp vụ và cách ack/commit đúng.

## 20. Runbook: resume gây quá tải downstream trở lại

1. Quan sát thời điểm resume của từng instance.
2. Xác định tổng concurrency và rate xử lý tăng bao nhiêu.
3. Xem queue depth, DB connections, HTTP 429/503 và p95 latency.
4. Chọn staggered resume hoặc partition-level resume nếu phù hợp.
5. Giữ bounded queue và high/low watermark.
6. Cân nhắc rate limiter hoặc circuit breaker riêng.
7. Theo dõi lag giảm mà downstream vẫn trong ngưỡng an toàn.
8. Nếu dependency không đủ capacity, giải quyết giới hạn capacity hoặc điều chỉnh SLO/scale.

Không nên xem “resume xong lag giảm nhanh” là thành công nếu đồng thời database bị quá tải và error rate tăng.

## 21. Runbook: container đang stop, không phải pause

1. Kiểm tra `container.isRunning()`.
2. Xác nhận stop do operator, shutdown, lỗi fatal hay autoStartup false.
3. Kiểm tra bean lifecycle và consumer group membership.
4. Xem có shutdown đang diễn ra không để tránh start giữa quá trình dừng.
5. Sau khi xác định nguyên nhân và bảo đảm dependency sẵn sàng, dùng `start()` theo lifecycle hợp lệ.
6. Kiểm tra partition assignment và consumption sau start.
7. Nếu cần pause ngay khi container start, quản lý desired state để không tạo một đợt tải ngoài ý muốn.

Đừng dùng `resume()` thay cho start: hai API có nhiệm vụ khác nhau.

## 22. Kiểm thử pause/resume với Spring Kafka

Integration test cần kiểm tra **trạng thái container và delivery thực tế**, không chỉ verify mock đã gọi `resume()`.

### 22.1. Test pause rồi resume cơ bản

1. Khởi động broker test và một topic có dữ liệu.
2. Tạo listener container với ID ổn định.
3. Gửi một vài record và xác nhận listener đã xử lý.
4. Gọi `container.pause()`.
5. Chờ event pause hoặc trạng thái paused thực tế.
6. Gửi thêm record khi container paused.
7. Xác nhận không có delivery mới trong cửa sổ quan sát phù hợp.
8. Gọi `container.resume()`.
9. Chờ event resume hoặc trạng thái đã resume.
10. Xác nhận những record đã chờ cuối cùng được xử lý.

Khi test, cần dùng latch/await với timeout thay vì `Thread.sleep(...)` cố định làm test dễ flaky. Consumer có thể đang xử lý records từ poll trước khi pause có hiệu lực.

### 22.2. Test pauseImmediate

1. Cấu hình poll trả nhiều records.
2. Bật `pauseImmediate=true`.
3. Yêu cầu pause khi listener đang xử lý record đầu.
4. Xác nhận records còn lại từ poll cũ được giữ lại cho tới khi resume theo semantics hỗ trợ.
5. Resume và xác nhận records còn lại được delivery.
6. Kiểm tra offset/processing result, không mặc định bỏ record nào.

### 22.3. Test concurrency

1. Dùng topic có nhiều partition.
2. Cấu hình container concurrency lớn hơn 1.
3. Pause container cha.
4. Chờ các child consumers áp dụng pause.
5. Resume container cha.
6. Xác nhận các partition có assignment phù hợp tiếp tục xử lý.
7. Quan sát ConsumerResumedEvent trên từng consumer khi có.

### 22.4. Test backpressure coordinator

1. Giả lập queue depth tăng qua HIGH_WATERMARK.
2. Xác nhận coordinator yêu cầu pause.
3. Giảm depth xuống giữa high và low: container vẫn paused.
4. Giảm xuống dưới LOW_WATERMARK và xác nhận downstream healthy.
5. Xác nhận coordinator yêu cầu resume.
6. Kích hoạt MANUAL_MAINTENANCE và xác nhận queue hồi phục không tự resume trái policy.
7. Kiểm tra một dependency unhealthy vẫn giữ pause.

### 22.5. Test restart/rebalance

1. Pause consumer khi có record chưa commit.
2. Restart hoặc mô phỏng rebalance.
3. Xác nhận group assignment thay đổi theo Kafka.
4. Xác nhận application desired pause state được áp dụng lại nếu cần.
5. Sau resume, kiểm tra record chưa commit được xử lý và idempotency vẫn đúng.

## 23. Những sai lầm thường gặp

**Gọi start() thay cho resume().** Container vẫn running và đã pause thì dùng resume; start là lifecycle khác.

**Gọi KafkaConsumer.resume() ngoài consumer thread.** Bỏ qua container management và có thể vi phạm thread-safety.

**Cho rằng resume có hiệu lực ngay trong cùng dòng code.** Yêu cầu được áp dụng theo vòng poll, nên cần theo dõi applied state/event.

**Không xác định đúng listener ID.** Lệnh có thể không tìm được container hoặc điều khiển nhầm listener.

**Resume một pod rồi nghĩ toàn group đã resume.** Registry là local với process.

**Không có low-watermark.** Queue depth dao động quanh ngưỡng làm pause/resume flapping.

**Nhiều controller cùng gọi resume độc lập.** Một controller có thể bỏ qua manual maintenance hoặc downstream health.

**Resume khi pause do framework.** Outstanding acknowledgements hoặc backoff có thể vẫn giữ consumer paused.

**Tưởng pause dừng xử lý mọi in-flight records.** Listener có thể đang hoàn tất records từ poll trước.

**Không có idempotency.** Crash/rebalance vẫn có thể gây redelivery bất chấp pause/resume.

**Dùng resume để sửa poison pill.** Payload sai cần error handler/DLT, không phải thay đổi consumer pause.

**Dùng resume như lệnh commit offset.** Resume không xác nhận processing thành công.

**Không quan sát backlog sau resume.** Consumer hoạt động trở lại nhưng có thể không đủ capacity để giảm lag.

## 24. Checklist vận hành

### Trước khi resume

- [ ] Đã xác định nguyên nhân ban đầu của pause.
- [ ] Downstream, queue và database đang đủ khỏe.
- [ ] Không còn manual maintenance flag.
- [ ] Container đúng ID và đang running.
- [ ] Đã kiểm tra partition-level pause và framework-managed pause nếu có.
- [ ] Đã có kế hoạch giảm burst khi backlog lớn.

### Khi gửi yêu cầu

- [ ] Dùng `MessageListenerContainer.resume()` thay vì can thiệp trực tiếp KafkaConsumer.
- [ ] Ghi audit người/controller gửi yêu cầu.
- [ ] Không xem API return là xác nhận mọi child consumers đã resume.
- [ ] Có cơ chế quan sát `ConsumerResumedEvent` hoặc trạng thái thực tế.
- [ ] Với nhiều instances, đã phân phối desired state đến các instance cần thiết.

### Sau resume

- [ ] Consumer thực sự chuyển khỏi paused state.
- [ ] Record mới hoặc backlog được delivery nếu dữ liệu có sẵn.
- [ ] Lag và oldest record age có xu hướng giảm.
- [ ] Queue depth và downstream latency ổn định.
- [ ] Không có pause/resume flapping.
- [ ] Ack/commit và idempotency hoạt động đúng khi có redelivery.
- [ ] Nếu không thấy tiến độ, đã kiểm tra stop, assignment, backoff và lỗi listener.

## Kết luận

`resume()` là thao tác cho phép Spring Kafka listener container **tiếp tục tiêu thụ record sau một yêu cầu pause**. Nó không phải start, seek hay commit offset. Với `@KafkaListener`, ứng dụng thường lấy container theo `id` từ `KafkaListenerEndpointRegistry` rồi gọi `resume()`; trạng thái thực tế cần được xác nhận qua `isConsumerPaused()` và các application events thay vì giả định lời gọi có hiệu lực tức thì.

Trong hệ thống backpressure, chỉ resume khi các điều kiện gây pause đã được giải quyết, ưu tiên high/low watermarks và một coordinator thống nhất các lý do pause. Khi concurrency lớn hoặc chạy nhiều pods, cần quan sát từng consumer/instance và tránh burst sau resume. Pause/resume giúp giữ ổn định lượng công việc mới nhưng không tự bảo đảm processing, acknowledgement hoặc idempotency; vì vậy vẫn phải phối hợp error handling, DLT, offset commit đúng cách và monitoring consumer lag để quy trình phục hồi đáng tin cậy.
