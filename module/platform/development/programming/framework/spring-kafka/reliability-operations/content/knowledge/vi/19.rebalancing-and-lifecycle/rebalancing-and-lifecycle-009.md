# Graceful shutdown

Trong một ứng dụng Spring Kafka chạy production, **graceful shutdown** là quá trình dừng consumer, listener container và các tài nguyên liên quan **có điều phối**, thay vì cắt tiến trình ngay lập tức. Mục tiêu là ngừng nhận thêm công việc, xử lý hoặc kết thúc an toàn những record đang thực hiện, ghi nhận offset theo đúng cơ chế acknowledgement/transaction, rồi đóng Kafka consumer và producer trước khi tiến trình thoát.

Graceful shutdown đặc biệt quan trọng khi Kubernetes rolling update, deploy phiên bản mới, scale down, restart instance để thay đổi cấu hình hoặc hệ điều hành gửi **SIGTERM**. Nếu chỉ kết thúc process bằng SIGKILL, các record đang xử lý có thể bị thực thi lại khi partition được phân công sang consumer khác. Với thao tác như gửi email, tạo hóa đơn hoặc cập nhật database, việc đó có thể gây side effect trùng lặp.

Một shutdown đúng không đồng nghĩa với lời hứa rằng **không bao giờ có duplicate**. Kafka consumer thông thường có delivery semantics at-least-once; một instance vẫn có thể crash, hết thời gian shutdown hoặc mất quyền sở hữu partition ngay trước lúc commit. Thiết kế production cần cả hai lớp: **dừng có trật tự khi có cơ hội** và **xử lý idempotent khi không có cơ hội dừng an toàn**.

Bài học đặt graceful shutdown trong chương **Rebalance và lifecycle** của Spring Kafka, làm rõ các thành phần tham gia, cách Spring lifecycle dừng container, tác động lên offset và transaction, shutdown trong Kubernetes, cùng các chiến lược drain in-flight processing và giám sát vận hành.

## 1. Shutdown đột ngột và graceful shutdown khác nhau thế nào?

Giả sử một consumer thuộc group inventory-service đang đọc topic orders.events, partition 2, và xử lý record tại offset 100.

**Shutdown đột ngột:**

~~~text
Consumer A poll offset 100
        |
        v
Gọi Inventory API / cập nhật database
        |
        v
SIGKILL / process crash
        |
        v
Không có cơ hội chạy lifecycle shutdown
        |
        v
Consumer B nhận partition
        |
        v
Đọc lại từ committed offset trước đó
        |
        v
Record 100 có thể được xử lý lần nữa
~~~

**Graceful shutdown:**

~~~text
Consumer A nhận SIGTERM
        |
        v
Spring bắt đầu lifecycle stop
        |
        v
Kafka listener container được yêu cầu dừng
        |
        v
Ngừng vòng poll mới và hoàn tất đơn vị xử lý
được chính sách stop cho phép
        |
        v
Commit offset / hoàn tất hoặc abort Kafka transaction
theo outcome thực tế
        |
        v
Close Kafka consumer và producer resources
        |
        v
Partition được chuyển giao cho group member khác
        |
        v
Process thoát
~~~

Graceful shutdown giúp giảm những record phải phát lại, nhưng **không thể sửa** nghiệp vụ đã thực hiện side effect trước khi offset commit thất bại. Đó là trách nhiệm của idempotency và consistency design.

## 2. Shutdown bao gồm những thành phần nào?

Một ứng dụng Spring Kafka thường có nhiều vòng đời cùng tồn tại:

| Thành phần | Vai trò khi shutdown | Điều cần chú ý |
|---|---|---|
| Spring ApplicationContext | Điều phối lifecycle và đóng beans | Spring Boot phải nhận tín hiệu dừng có trật tự |
| KafkaListenerEndpointRegistry | Quản lý các @KafkaListener containers | Có thể dừng container theo ID hoặc toàn bộ registry |
| KafkaMessageListenerContainer | Poll record và gọi listener | Dừng poll, xử lý record đang có và commit theo policy |
| ConcurrentMessageListenerContainer | Quản lý nhiều consumer con | Phải chờ các consumer threads kết thúc phù hợp |
| KafkaConsumer | Thành viên consumer group, sở hữu partitions | Wakeup/close, xử lý rebalance và offset |
| KafkaTemplate/ProducerFactory | Gửi Kafka output hoặc DLT | Pending sends và transaction phải có outcome rõ |
| KafkaTransactionManager | Quản lý Kafka transaction | Commit/abort theo listener/container semantics |
| Database/HTTP clients | Side effect ngoài Kafka | Timeout, idempotency và thứ tự đóng resources |
| Kubernetes/Process manager | Gửi SIGTERM rồi có thể SIGKILL | Grace period phải đủ dài cho shutdown path |

Chỉ nhìn KafkaConsumer.close() là chưa đủ. Ví dụ consumer đã ngừng poll nhưng một task bất đồng bộ vẫn đang cập nhật database; process exit khi task chưa hoàn thành có thể khiến record phải được xử lý lại sau restart.

## 3. Spring Kafka listener container là một SmartLifecycle

Các listener containers của Spring Kafka tham gia Spring **SmartLifecycle**. Điều này cho phép Spring ApplicationContext khởi động và dừng chúng theo lifecycle phase, thay vì dựa vào một vòng lặp thủ công trong @PreDestroy.

Trong Spring Boot, khi ứng dụng nhận tín hiệu kết thúc như SIGTERM, context shutdown thông thường sẽ yêu cầu các SmartLifecycle beans dừng, đợi callback theo timeout của từng phase rồi mới hủy các beans và đóng tài nguyên.

### 3.1. Lifecycle phase ảnh hưởng thứ tự dừng

Spring lifecycle có nguyên tắc tổng quát:

- Khi startup, các component với phase thấp hơn thường bắt đầu trước.
- Khi shutdown, các component có phase cao hơn thường được dừng trước.
- Dependencies giữa beans có thể ảnh hưởng thứ tự thực tế.

Spring Kafka listener containers thường sử dụng phase rất cao để chúng được khởi động sau nhiều dependency và được yêu cầu dừng sớm khi shutdown. Điều này hữu ích: consumer nên ngừng nhận việc **trước khi** database pool, producer factory hoặc service dependency bị đóng.

Không nên tùy tiện chỉnh phase bằng một số lớn/nhỏ nếu chưa hiểu toàn bộ graph dependencies. Xác định phase thực tế của container và các SmartLifecycle resources khác trong version đang sử dụng.

### 3.2. Shutdown được quản lý thay vì System.exit ngay

Không dùng một shutdown hook tự gọi Runtime.halt() hoặc cưỡng bức System.exit trước khi Spring context kịp stop. Nếu ứng dụng phải cung cấp endpoint quản trị để dừng một listener, dùng registry/container lifecycle APIs và để Spring đảm nhận resource cleanup.

## 4. Cấu hình thời gian chờ shutdown của Spring Boot

Spring Boot hỗ trợ cấu hình timeout cho các lifecycle phases:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Thuộc tính này cho Spring một khoảng thời gian tối đa **cho từng shutdown phase** khi đợi SmartLifecycle beans dừng. Nó không bảo đảm toàn bộ ứng dụng sẽ dừng chính xác sau 45 giây, vì còn các phase khác, bean destruction và thời gian bên ngoài Spring.

Với container Kafka, một số phiên bản còn có các tham số shutdown timeout riêng ở container/container properties. Các tham số này cần được xác nhận bằng API/Javadoc đúng Spring Kafka version.

Hãy phân biệt:

- **Spring lifecycle phase timeout:** thời gian framework đợi callback dừng của các SmartLifecycle beans trong phase.
- **Kafka container stop/shutdown timeout:** thời gian container có thể chờ thread/consumer kết thúc theo cấu hình.
- **Kubernetes terminationGracePeriodSeconds:** tổng ngân sách Kubernetes dành cho container trước khi có thể cưỡng bức kết thúc.
- **HTTP/database timeout:** giới hạn thời gian các dependency calls có thể giữ listener.
- **Kafka max.poll.interval.ms:** giới hạn consumer tiến độ poll theo group protocol.

Các timeout này cùng tham gia một kế hoạch shutdown, không có một thuộc tính nào tự bao phủ toàn bộ.

## 5. stopImmediate: dừng sau record hiện tại hay cả poll?

Một Kafka poll thường trả về nhiều records. Khi nhận yêu cầu stop, Spring Kafka có thể xử lý những records đã được fetch trước đó hoặc dừng sớm hơn tùy cấu hình.

**Mặc định trong nhiều phiên bản Spring Kafka**, container hoàn tất các records còn lại từ poll trước khi dừng. Có thể cấu hình **stopImmediate** để container dừng sau khi xử lý record hiện tại, thay vì tiếp tục toàn bộ các record đã nhận từ poll.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setStopImmediate(true);
    return factory;
}
~~~

Khác biệt khái niệm:

~~~text
poll() trả về [R1, R2, R3, R4]
                |
                v
             Xử lý R1
                |
             SIGTERM
                |
       +--------+---------+
       |                  |
 stopImmediate=false  stopImmediate=true
       |                  |
       v                  v
 Xử lý R2,R3,R4       Dừng sau record
 trong poll hiện tại   đang được xử lý
       |                  |
       v                  v
 Container stop        Các record chưa
                      xử lý có thể được
                      đọc lại sau resume
~~~

Chọn cấu hình theo mục tiêu:

- Nếu record rất nhanh, xử lý hết poll hiện tại có thể giảm lượng replay.
- Nếu record xử lý lâu hoặc poll batch lớn, stopImmediate giúp shutdown nhanh hơn.
- Các record chưa xử lý phải còn khả năng được tiêu thụ lại; không được commit offset vượt quá phần thực sự đã xử lý thành công.

Tên setter và chi tiết xử lý có thể khác theo phiên bản; kiểm tra Spring Kafka thực tế, đặc biệt khi dùng batch listener hoặc acknowledgement thủ công.

## 6. max.poll.records ảnh hưởng ngân sách shutdown

Giả sử:

- max.poll.records = 500.
- Một record cần trung bình 300 ms để xử lý tuần tự.
- Consumer vừa poll đủ 500 records.
- stopImmediate = false.

Chỉ riêng xử lý 500 records có thể cần khoảng:

~~~text
500 × 0.3 giây = 150 giây
~~~

Nếu Kubernetes chỉ cho 30 giây để terminate, container có nguy cơ bị SIGKILL giữa chừng. Dù throughput bình thường có vẻ ổn, shutdown path không phù hợp.

Một cấu hình minh họa:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
~~~

Giảm max.poll.records có thể hạn chế số records đang được xử lý sau một poll, nhưng không tự giảm latency của từng record. Trong các hệ thống dùng batch listener, kích thước batch ảnh hưởng trực tiếp tới phạm vi commit/rollback.

Nếu record xử lý chậm, cần giải quyết timeout của dependency, batching, concurrency, backpressure và lựa chọn stopImmediate cùng nhau.

## 7. AckMode quyết định offset nào được commit

Graceful shutdown chỉ an toàn khi offset phản ánh **công việc thực sự đã hoàn thành**. Spring Kafka hỗ trợ nhiều AckMode.

| AckMode | Cơ chế khái quát | Điểm cần chú ý khi shutdown |
|---|---|---|
| RECORD | Commit sau mỗi record được xử lý thành công theo cơ chế container | Record hiện tại thất bại có thể được redeliver |
| BATCH | Commit sau khi các record trong poll được xử lý theo policy | Poll đang dang dở có thể khiến replay nhiều record |
| TIME / COUNT / COUNT_TIME | Commit theo ngưỡng thời gian/số lượng sau xử lý | Có records đã xử lý nhưng chưa commit khi dừng đột ngột |
| MANUAL | Listener gọi acknowledge; container xử lý pending ack theo semantics của mode | Phải ack đúng sau khi nghiệp vụ hoàn tất |
| MANUAL_IMMEDIATE | Có thể commit ngay khi acknowledge đúng ngữ cảnh | Không được ack trước side effect hoàn tất |

**Điểm mấu chốt:** offset commit là thông tin consumer group dùng để bắt đầu đọc lần sau, **không phải một phép khử trùng side effect**. Nếu database đã commit nhưng Kafka offset chưa commit, record có thể replay.

### 7.1. Ví dụ manual acknowledgement

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );
    return factory;
}

@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    containerFactory = "ordersFactory"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.apply(record.value());   // Hoàn tất nghiệp vụ trước
    acknowledgment.acknowledge();         // Rồi mới acknowledge
}
~~~

Nếu apply() ném exception, acknowledgement không được gọi và error handler thực hiện retry/recovery. Nếu apply() hoàn thành nhưng ack/commit thất bại đúng lúc shutdown, record có thể được đọc lại. Handler vì vậy cần idempotent.

Không nên ack ở đầu listener để “tránh replay” khi shutdown; cách này tạo khả năng mất record nghiệp vụ nếu process chết sau ack.

## 8. Dừng listener container qua KafkaListenerEndpointRegistry

Spring Kafka cho phép truy cập listener container theo ID để quản lý runtime:

~~~java
@Component
public class KafkaConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaConsumerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

Điểm lưu ý:

- ID phải khớp thuộc tính id trên @KafkaListener hoặc listener container đăng ký tương ứng.
- stop() yêu cầu container dừng theo lifecycle; thời gian và cách chờ hoàn tất phụ thuộc API/implementation.
- start() chỉ nên được gọi khi ứng dụng còn hoạt động và dependency đã sẵn sàng.
- Không gọi stop() bên trong listener rồi tự chờ cùng thread theo cách gây deadlock.
- Khi Spring ApplicationContext shutdown, thường **không cần** tự gọi registry.stop() từ @PreDestroy; Spring lifecycle đã điều phối stop của container.

Nếu cần chờ callback dừng thay vì suy đoán stop() đã hoàn tất ngay, hãy dùng API stop(Runnable) được version hỗ trợ và kết hợp timeout ở phía caller phù hợp.

### 8.1. Không nhầm pause với stop

Spring Kafka cũng hỗ trợ pause/resume:

- **pause:** tạm ngừng fetch/delivery theo semantics của container nhưng consumer có thể tiếp tục poll để giữ membership.
- **stop:** kết thúc consumer container lifecycle, đóng consumer, nhường partition theo group protocol.

Pause phù hợp để backpressure hoặc chờ dependency ngắn mà không muốn rời group; stop phù hợp khi instance thật sự kết thúc. **Pause không phải shutdown hoàn chỉnh**, vì connection và consumer membership có thể vẫn tồn tại.

## 9. Graceful shutdown và rebalance

Khi một consumer rời consumer group, partitions của nó cần được giao cho các member còn hoạt động. Đó là một phần của quá trình **rebalance** hoặc điều chỉnh assignment theo consumer group protocol.

Trong trường hợp dynamic membership thường gặp:

1. Container nhận yêu cầu stop.
2. Consumer kết thúc các thao tác đang xử lý theo stop policy.
3. Consumer close rời group theo hành vi client.
4. Group coordinator cập nhật membership.
5. Các partitions được giao lại cho các consumers còn lại.

Thời điểm và số lượng partitions bị thu hồi phụ thuộc assignor, group protocol, static membership, trạng thái coordinator và các members khác.

### 9.1. Eager và cooperative rebalance

- **Eager rebalance:** có thể revoke nhiều hoặc toàn bộ partitions của các members trước khi phân công lại.
- **Cooperative rebalance:** hỗ trợ thu hồi tăng dần, giảm mức độ gián đoạn khi topology phù hợp.

Cooperative assignment giảm churn trong nhiều trường hợp nhưng **không thay thế shutdown safety**. Một record đang xử lý vẫn có thể replay nếu offset chưa commit hoặc owner mất quyền.

### 9.2. Static membership

Consumer dùng group.instance.id có thể được coordinator xem là static member theo Kafka protocol. Trong một số kịch bản rolling restart, static membership giúp giảm rebalance không cần thiết, nhưng việc đóng/dừng và mất kết nối có semantics khác dynamic membership.

Không thể mặc định rằng stop một static member sẽ giải phóng partitions ngay như dynamic member trong mọi client/phiên bản. Khi sử dụng static membership, xem xét session.timeout.ms, max.poll.interval.ms và chính sách restart của orchestration để tránh giữ assignment lâu hơn mong muốn.

## 10. ConsumerRebalanceListener và trạng thái partition

Spring Kafka có hook cho quá trình assign/revoke/lost partitions. Với Spring Kafka, **ConsumerAwareRebalanceListener** cho phép phản ứng tại một số giai đoạn như:

- onPartitionsAssigned.
- onPartitionsRevokedBeforeCommit.
- onPartitionsRevokedAfterCommit.
- onPartitionsLost.

Trong shutdown/rebalance, các hook này có thể giúp quan sát partition ownership hoặc cập nhật state theo assignment.

Ví dụ khái niệm:

~~~java
public class OrdersRebalanceListener
        implements ConsumerAwareRebalanceListener {

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.info("Assigned partitions: {}", partitions);
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.info("Revoking partitions: {}", partitions);
    }

    @Override
    public void onPartitionsLost(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        log.warn("Lost partitions: {}", partitions);
    }
}
~~~

Đây là một mẫu minh họa: method signatures, callbacks thực sự và cách đăng ký listener cần được kiểm tra theo Spring Kafka version. Khi container nhận **onPartitionsLost**, consumer có thể đã mất quyền đối với partitions; không được cố commit offset như thể vẫn sở hữu chúng.

Không đưa database calls kéo dài vào callback rebalance. Callback hoạt động trong context consumer và có thể làm chậm rebalance hoặc poll. Chỉ ghi nhận state/metrics cần thiết và điều phối công việc dài qua cơ chế an toàn khác.

## 11. Xử lý tác vụ đồng bộ và bất đồng bộ khác nhau

### 11.1. Listener đồng bộ

Listener đồng bộ chỉ trả về sau khi xử lý nghiệp vụ hoàn tất:

~~~java
@KafkaListener(topics = "orders.events")
public void onMessage(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong mô hình này, container thường biết listener đã hoàn thành khi method return. Graceful shutdown có thể chờ current record hoặc poll batch theo stop policy, rồi xử lý ack/offset.

Tuy nhiên, nếu orderService.process() gọi HTTP client không có timeout và treo vô hạn, container khó dừng trong grace period. **Mọi dependency blocking phải có timeout hữu hạn**.

### 11.2. Listener khởi chạy tác vụ bất đồng bộ

Ví dụ dễ gây mất an toàn:

~~~java
@KafkaListener(topics = "orders.events")
public void onMessage(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Method trả về ngay dù nghiệp vụ còn đang chạy.
}
~~~

Nếu container cho rằng listener đã thành công và commit offset khi method return, process có thể bị dừng trước khi task hoàn tất. Record đã được ghi nhận tiến độ nhưng side effect chưa xong.

Muốn xử lý async cần một protocol rõ ràng:

- Không acknowledge trước khi task hoàn tất thành công.
- Quản lý số lượng in-flight tasks và shutdown drain của executor.
- Bảo đảm partition ordering nếu domain cần.
- Phân loại lỗi async và chuyển lại error handling theo API Spring Kafka version hỗ trợ.
- Cân nhắc listener async return type được Spring Kafka hỗ trợ trong phiên bản đang chạy, thay vì tự fire-and-forget.
- Đặt shutdown timeout cho worker pool và tránh ack sau khi container đã mất partition.

Một thread pool có thể đã drain xong trong khi Kafka offset chưa commit; vẫn cần idempotency vì crash có thể xảy ra giữa hai bước đó.

## 12. Thiết kế in-flight work tracker

Với pipeline cần xử lý ngoài consumer thread, có thể dùng một tracker quản lý các tác vụ đang chạy.

Khái niệm:

~~~text
Listener nhận record
       |
       v
In-flight counter +1
       |
       v
Start asynchronous processing
       |
       +-- Success -> ghi nhận trạng thái, ack theo API
       |
       +-- Failure -> retry/recovery theo policy
       |
       v
In-flight counter -1

Shutdown:
       |
       v
Ngừng nhận task mới
       |
       v
Chờ counter về 0 trong grace budget
       |
       v
Hoàn tất offset/producer/transaction, đóng container
~~~

Không dùng counter bằng 0 làm bằng chứng duy nhất rằng work đã được commit bền vững. Counter có thể về 0 trước khi Kafka producer acknowledgement hoặc offset commit hoàn tất.

Nên kết hợp:

- In-flight count theo component.
- Queue depth của executor.
- Futures/completion signals.
- Pending Kafka producer sends.
- Pending acknowledgements và offset commit.
- Shutdown deadline chung.

Nếu thời hạn drain hết, ứng dụng cần có hành vi rõ: dừng nhận việc, ghi log/metric cảnh báo và cho phép record chưa commit được replay; không cố ack để process thoát đúng giờ.

## 13. Thứ tự dừng consumer và producer

Một shutdown an toàn cần tránh đóng producer quá sớm khi listener vẫn đang gửi Kafka output hoặc DLT.

Thứ tự mong muốn ở mức khái niệm:

~~~text
1. Ngừng tiếp nhận thêm công việc nếu có ingress khác.
2. Yêu cầu Kafka listener containers stop/pause có chủ đích.
3. Chờ phần xử lý được phép hoàn thành.
4. Xác nhận producer sends hoặc kết thúc transaction
   cần thiết cho phần xử lý đã hoàn tất.
5. Xử lý offset commit/rollback theo listener semantics.
6. Close Kafka consumers, producers và các resources.
7. Kết thúc Spring ApplicationContext.
~~~

Trong Spring Boot, đừng tự sắp xếp hoàn toàn bằng một chuỗi @PreDestroy của nhiều beans rồi giả định thứ tự luôn như trên. SmartLifecycle phases và bean dependencies quyết định thứ tự dừng; có thể dùng lifecycle component phù hợp khi ứng dụng có executor/custom queues cần drain.

### 13.1. Producer flush không phải commit Kafka transaction

Với producer non-transactional, flush giúp chờ các producer records pending được gửi theo producer API. Nhưng:

- Flush không biến database update và Kafka publish thành một transaction.
- Flush không thay thế việc kiểm tra send future đã thành công hay thất bại.
- Flush không có nghĩa consumer offset đã commit.
- Với transactional producer, flush không thay cho commitTransaction().

Nếu đang dùng KafkaTemplate transactional trong listener container, để transaction manager/container hoàn tất commit hoặc abort theo outcome. Không gọi commitTransaction trực tiếp trên producer mà framework đang quản lý.

## 14. Graceful shutdown với Kafka transaction

Với transactional listener, container có thể gom Kafka output và consumed offsets vào một transaction. Khi shutdown xảy ra giữa transaction:

**Transaction hoàn tất và commit thành công:**

- Output transactional trở nên visible cho read_committed consumers.
- Offset input được ghi nhận cùng transaction.
- Record không cần được replay do riêng transaction đó.

**Transaction chưa thể commit hoặc bị abort:**

- Output transactional của transaction abort bị ẩn với read_committed consumers.
- Consumed offset trong transaction không được commit.
- Input có thể được xử lý lại khi group phân công partition.

~~~text
Input record 300
       |
       v
Kafka transaction begin
       |
       v
Listener gửi output
       |
       +-- Graceful stop đủ thời gian
       |       |
       |       v
       |   Commit output + input offset
       |
       +-- Process bị cưỡng bức dừng / TX abort
               |
               v
           Output bị ẩn nếu abort
           Input offset không commit
           Record có thể replay
~~~

Trong transactional path, Spring Kafka thường dùng **DefaultAfterRollbackProcessor** để quản lý retry/recovery sau rollback. Không giả định DefaultErrorHandler của non-transactional listener sẽ điều khiển toàn bộ transaction rollback.

### 14.1. Transaction timeout vẫn áp dụng

transaction.timeout.ms giới hạn thời gian transaction producer còn mở. Graceful shutdown deadline không tự kéo dài Kafka transaction timeout.

Nếu listener cần 90 giây để hoàn tất mà transaction.timeout.ms chỉ cho phép 60 giây, broker có thể abort transaction trước khi Kubernetes grace period hết. Vì vậy, cần giữ transaction scope ngắn và đánh giá transaction.timeout.ms, max.poll.interval.ms, shutdown deadline **độc lập**.

### 14.2. Producer fencing khi rolling restart

Nếu instance mới dùng lại transactional.id trong khi instance cũ chưa dừng, producer cũ có thể bị **fence**. Fencing bảo vệ Kafka transaction khỏi zombie producer, nhưng không rollback HTTP/database side effect ngoài Kafka.

Khi rolling update:

- Kiểm soát transactional ID prefix/instance identity.
- Không cho hai instance độc lập vô tình dùng cùng transactional.id.
- Chấp nhận trường hợp instance cũ bị fence hoặc transaction abort và record replay.
- Dùng idempotency ở business boundary.

Không cố retry vô hạn một producer đã bị fence.

## 15. Vì sao idempotency vẫn bắt buộc?

Giả sử listener:

1. Ghi database thành công.
2. Chuẩn bị commit Kafka offset.
3. Instance nhận SIGKILL vì hết grace period.
4. Consumer mới đọc lại record.

Database đã có thay đổi, nhưng Kafka group có thể chưa ghi nhận offset. Nếu handler không idempotent, thay đổi được áp dụng hai lần.

Một mô hình thường dùng là **processed_events/inbox**:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (event_id, consumer_name)
);
~~~

Trong **cùng database transaction**:

- Insert event ID theo unique constraint.
- Nếu đã tồn tại, bỏ qua side effect lặp.
- Nếu insert thành công, cập nhật nghiệp vụ.
- Commit database.
- Sau đó cho Kafka container commit offset theo AckMode.

Nếu Kafka commit thất bại, record replay và inbox giúp tránh side effect lặp. Nếu database transaction thất bại, cả dấu processed và side effect rollback.

Không tin rằng chỉ có graceful shutdown là đủ để đảm bảo exactly-once business behavior. Sự cố nguồn điện, node crash, OOMKill hoặc network partition có thể xảy ra bất cứ lúc nào.

## 16. Error handler, retry và DLT khi container dừng

Một record có thể đang trong chuỗi retry của DefaultErrorHandler khi shutdown xảy ra.

Ví dụ:

~~~text
Record X xử lý lỗi
      |
      v
Retry 1 sau 1 giây
      |
      v
Retry 2 sau 2 giây
      |
      v
SIGTERM
      |
      v
Container được yêu cầu stop
      |
      v
Retry/backoff còn chưa kết thúc
~~~

Tùy Spring Kafka version, BackOffHandler và container state, container có thể xử lý stop trong thời gian chờ hoặc ngừng chuỗi retry để consumer rời group. Nếu record chưa recover và offset chưa commit, record có thể được đọc lại khi start.

Để shutdown ổn định:

- Retry blocking cần số lần và thời gian hữu hạn.
- HTTP/database requests cần timeout riêng.
- Không đặt retry vô hạn trên consumer thread mà không có chiến lược stop.
- Record permanent nên được chuyển DLT/recovery đúng policy.
- Nếu DLT publish chưa được xác nhận, không cố commit offset chỉ vì shutdown deadline sắp hết.
- Theo dõi recovery publish failure và in-flight retry duration.

### 16.1. Non-blocking retry topic

Nếu hệ thống dùng @RetryableTopic, record lỗi có thể đã được publish sang retry topic và offset nguồn được commit theo policy. Lúc này một consumer khác của retry topic có thể tiếp tục xử lý sau khi instance gốc dừng.

Graceful shutdown cần tính tới **toàn bộ retry-topic containers**, không chỉ container của topic gốc. Dashboard nên theo dõi pending records ở các retry topics và DLT.

Một lần publish sang retry topic đã thành công nhưng offset nguồn chưa commit cũng có thể tạo duplicate khi redelivery. Idempotency và event ID ổn định giúp hệ thống chịu được cửa sổ lỗi này.

## 17. Kubernetes: SIGTERM và terminationGracePeriodSeconds

Kubernetes thường yêu cầu container kết thúc bằng tín hiệu terminate, sau đó có thể cưỡng bức dừng nếu quá **terminationGracePeriodSeconds**.

Một cấu hình minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-consumer
  template:
    metadata:
      labels:
        app: inventory-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: example/inventory-consumer:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
~~~

Giá trị 90 giây là ví dụ, không phải một khuyến nghị cố định cho mọi workload. Cần đo thực tế thời gian stop của listener, executor, producer và Spring context, rồi thêm khoảng dự phòng.

### 17.1. Thời gian grace không chỉ dành cho listener

Ngân sách Kubernetes bao gồm các hoạt động lifecycle như preStop hook, chờ process phản ứng SIGTERM, Spring context shutdown và resource cleanup. Nếu preStop hook chiếm phần lớn thời gian, Spring Kafka có thể còn rất ít thời gian để xử lý record đang chạy.

Vì vậy:

~~~text
T_k8s_grace
  > T_preStop
    + T_listener_drain
    + T_commit_or_abort
    + T_resource_close
    + T_safety_margin
~~~

Đây là công thức lập ngân sách, không phải một bảo đảm thời gian thực thi cứng. Các giai đoạn có thể chồng lấn hoặc bị ảnh hưởng bởi scheduling, GC, broker timeout và thread pool.

### 17.2. preStop không tự dừng Kafka consumer

Một hook kiểu:

~~~yaml
lifecycle:
  preStop:
    exec:
      command:
        - /bin/sh
        - -c
        - sleep 5
~~~

chỉ làm chậm quá trình terminate; nó **không** tự khiến @KafkaListener ngừng poll ngay. Nó có thể hữu ích cho HTTP traffic draining trong một số kiến trúc, nhưng không phải giải pháp shutdown Kafka consumer.

Để dừng Kafka có kiểm soát, hãy để process nhận SIGTERM và Spring lifecycle stop container, hoặc thiết kế endpoint/drain protocol chuyên dụng khi thật sự cần.

### 17.3. Readiness probe không điều khiển Kafka group

Khi Pod không ready, Kubernetes Service thường ngừng chọn Pod làm đích nhận **HTTP traffic** mới. Nhưng Kafka broker và consumer group không dựa trên Kubernetes readiness để quyết định consumer nào được phân công partition.

Vì vậy, đặt readiness=false **không tự pause/stop Kafka consumers**. Nếu một service vừa có REST API vừa có @KafkaListener, hai luồng ingress phải được điều phối riêng.

## 18. Shutdown JVM phải nhận được SIGTERM

Một ứng dụng Java chạy trong container cần bảo đảm SIGTERM đến được JVM process. Nếu entrypoint shell nuốt tín hiệu hoặc tiến trình Java không chạy dưới cơ chế forwarding phù hợp, Spring ApplicationContext có thể không nhận được tín hiệu để đóng.

Dockerfile/entrypoint minh họa:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dạng exec ENTRYPOINT thường giúp Java process nhận tín hiệu trực tiếp. Nếu phải dùng shell script, cân nhắc exec java ... để thay shell bằng JVM.

Không kỳ vọng @PreDestroy chạy khi process bị SIGKILL, OOMKill hoặc host mất điện. Shutdown callback chỉ là best effort khi runtime còn cơ hội hoàn tất.

## 19. Rolling deployment và concurrency

Khi một Pod dừng, partitions của nó được các Pods còn lại đảm nhiệm. Nếu scale down từ 6 instances xuống 3, các consumer còn lại phải chịu thêm partitions và backlog.

Các điểm cần theo dõi:

- Số partitions, số active consumers và concurrency của listener containers.
- Rebalance frequency và duration.
- Consumer lag theo partition, không chỉ group tổng.
- Thời gian listener stop và assignment mới.
- Oldest record age, throughput và latency sau scale down.
- Dependency throughput: nhiều partitions chuyển sang ít consumers có thể làm tăng tải trên mỗi instance.

Không phải cứ tăng concurrency sẽ giảm thời gian shutdown; nếu mỗi container thread có công việc in-flight lớn, phải drain nhiều công việc song song và tài nguyên downstream có thể quá tải.

Với rolling update, nên tránh dừng quá nhiều instances cùng lúc. Dùng deployment strategy, PodDisruptionBudget khi phù hợp và tính capacity của các replicas còn lại.

## 20. Phân biệt shutdown với pause/resume cho backpressure

Một số đội vận hành muốn dừng consumer khi downstream outage để tránh retry storm.

**Pause container** phù hợp nếu:

- Ứng dụng còn chạy và muốn giữ group membership theo cơ chế phù hợp.
- Dependency dự kiến phục hồi trong thời gian ngắn.
- Muốn resume mà không tạo lại toàn bộ container.
- Có monitor/cảnh báo nếu pause quá lâu.

**Stop container** phù hợp nếu:

- Instance sắp kết thúc.
- Cần giải phóng Kafka consumer resources.
- Cần chuyển partition cho instances khác.
- Có deployment hoặc maintenance yêu cầu dừng thật.

**Shutdown ApplicationContext** phù hợp khi:

- Toàn bộ service đang terminate.
- Cần đóng đồng bộ listener, producer, executors và database.

Không dùng pause như cách làm Pod thoát: pause có thể tiếp tục giữ consumer connection, và process vẫn chạy.

## 21. Khi stop không kịp: điều gì sẽ xảy ra?

Graceful shutdown có **deadline**. Khi deadline hết, orchestrator có thể cưỡng bức process kết thúc.

Các trạng thái có thể xảy ra:

| Trạng thái lúc bị dừng | Hệ quả có thể xảy ra |
|---|---|
| Record chưa được xử lý | Consumer mới đọc từ offset chưa commit |
| Record xử lý xong nhưng offset chưa commit | Record có thể replay, cần idempotency |
| Kafka producer send chưa xác nhận | Output có thể đã được ghi hoặc chưa; kết quả bất định |
| Kafka transaction chưa commit | Coordinator có thể abort; read_committed downstream không thấy output abort |
| Database đã commit, Kafka offset chưa commit | Side effect có thể lặp khi replay |
| DLT publish chưa xác nhận | Không thể coi recovery an toàn; record có thể cần redelivery |
| Asynchronous task còn chạy | Task có thể bị ngắt; không có bảo đảm hoàn thành |

Không có một flag stopImmediate hay shutdownTimeout nào xóa được mọi ranh giới lỗi này. Hãy ưu tiên **không commit công việc chưa hoàn thành**, ghi nhận outcome rõ và để các lần chạy sau xử lý idempotent.

## 22. Tính shutdown budget từ SLO

Một cách tính minh họa:

- Listener processing p99: 3 giây/record.
- max.poll.records: 40.
- stopImmediate: false.
- Producer commit/flush: tối đa 8 giây.
- Consumer close và Spring cleanup: 7 giây.
- Dự phòng GC/network/scheduling: 15 giây.

Nếu xử lý poll tuần tự, thời gian worst-case theo giả định có thể là:

~~~text
T_listener = 40 × 3s = 120s
T_commit  = 8s
T_close   = 7s
T_margin  = 15s

T_grace_budget ≈ 150s
~~~

Nếu Kubernetes terminationGracePeriodSeconds là 30 giây, không thể kỳ vọng poll lớn này drain hoàn toàn theo stop policy hiện tại.

Có thể điều chỉnh bằng:

1. Bật stopImmediate nếu semantics và Spring Kafka version cho phép.
2. Giảm max.poll.records hoặc giảm thời gian xử lý mỗi record.
3. Đặt dependency timeout.
4. Tách công việc dài khỏi listener sang durable workflow.
5. Nâng grace period khi thực sự cần và có bằng chứng latency.
6. Dùng idempotency để chấp nhận replay của records còn lại.

Không đặt grace period quá lớn chỉ để tránh replay: instance bị treo có thể giữ tài nguyên và làm rollout rất chậm.

## 23. Graceful shutdown và batch listener

Với batch listener, method nhận một danh sách ConsumerRecords thay vì một record.

~~~java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "batchFactory"
)
public void consumeBatch(List<OrderEvent> events) {
    batchService.apply(events);
}
~~~

Nếu batch có 500 records và batchService.apply mất 60 giây, shutdown phải chờ theo behavior container. Nếu process chết giữa batch, offset commit có thể chưa diễn ra và nhiều records bị redeliver.

Các nguyên tắc:

- Giữ batch size và thời gian xử lý dưới ngân sách vận hành.
- Xác định commit/ack semantics khi một record trong batch lỗi.
- Dùng idempotency theo từng event hoặc theo batch ID phù hợp.
- Không coi partial DB commit của batch là Kafka offset commit nguyên tử.
- Nếu batch rất lớn, cân nhắc chunking và checkpoint phù hợp hoặc chuyển sang record listener.

stopImmediate với batch listener không nhất thiết có thể dừng giữa method đang xử lý một batch; Java method vẫn phải kết thúc hoặc tự hỗ trợ cancellation hợp lệ.

## 24. Các thao tác external không nên bị interrupt tùy tiện

Khi shutdown, thread có thể bị interrupt hoặc dependency close. Nhưng tự ý hủy một tác vụ quan trọng ngay sau khi đã gửi request đi có thể làm trạng thái kết quả **không rõ**.

Ví dụ Payment API:

~~~text
Consumer gửi charge request
       |
       v
Payment API thực hiện thành công
       |
       v
Listener chưa nhận response
       |
       v
SIGTERM -> task bị hủy
       |
       v
Consumer mới retry charge
~~~

Không giải quyết bằng “đợi vô hạn cho Payment API phản hồi”. Hãy:

- Đặt idempotency key cho charge.
- Có API tra cứu payment status khi response timeout.
- Lưu business state và recovery intent bền vững.
- Dùng outbox/saga nếu workflow vượt phạm vi Kafka.
- Giới hạn thời gian shutdown nhưng chấp nhận replay an toàn.

Graceful shutdown có ý nghĩa khi nghiệp vụ được thiết kế để có thể dừng/tiếp tục trong ranh giới commit rõ ràng.

## 25. Shutdown hook riêng: dùng khi nào?

Trong nhiều ứng dụng Spring Kafka thuần, lifecycle có sẵn đã đủ. Một shutdown hook tùy biến chỉ có ích khi cần điều phối tài nguyên ngoài Kafka, ví dụ:

- Dừng HTTP ingress trước khi consumer stop.
- Ngừng scheduler phát công việc mới.
- Chờ queue executor cạn.
- Ghi checkpoint riêng cho một long-running worker.
- Đóng external API connection sau khi consumer hoàn tất.

Nếu tự viết hook, tránh:

- Gọi System.exit trong @PreDestroy.
- Gọi listenerContainer.stop() từ chính listener rồi chặn chờ vô hạn.
- Đóng KafkaTemplate/ProducerFactory khi listener còn gửi output.
- Chỉ sleep một khoảng cố định rồi hy vọng đã drain.
- Nuốt exceptions và báo shutdown thành công khi còn pending work.
- Tạo một thread non-daemon treo, khiến JVM không thể thoát.

Một custom SmartLifecycle component có thể phối hợp drain khi cần, nhưng phải xác định dependencies/phase rõ ràng. Với Spring Boot và KafkaListenerEndpointRegistry, nên ưu tiên sử dụng API lifecycle đã được framework hỗ trợ.

## 26. Kiểm thử graceful shutdown

Không thể khẳng định shutdown an toàn chỉ bằng unit test cho một method listener. Cần kiểm thử integration có Kafka broker/test infrastructure và điều kiện dừng thực tế.

### 26.1. Stop khi không có record in-flight

Khởi động consumer, xác nhận group assignment rồi gửi tín hiệu stop. Kiểm tra container chuyển sang stopped, không còn consumer connections và startup lại không gây xử lý trùng bất thường.

### 26.2. Stop giữa một record đồng bộ

Cho listener xử lý record trong một khoảng thời gian biết trước. Gửi SIGTERM sau khi listener bắt đầu. Xác nhận:

- Stop policy đang áp dụng đúng.
- Nếu listener hoàn tất trong grace period, offset có thể commit theo AckMode.
- Nếu bị dừng trước commit, record có thể replay sau restart.
- Business side effect không bị lặp nhờ idempotency.

### 26.3. Stop giữa poll có nhiều records

Đặt max.poll.records nhỏ nhưng lớn hơn 1. Gửi nhiều records rồi shutdown ở giữa. So sánh stopImmediate=false/true theo version:

- Bao nhiêu records được xử lý trước stop?
- Committed offset cuối là bao nhiêu?
- Bao nhiêu records redeliver sau restart?
- Có record chưa xử lý nào bị bỏ qua không?

### 26.4. Stop khi producer send/DLT send chưa hoàn tất

Gây producer delay hoặc lỗi Kafka có kiểm soát. Kiểm tra logic không coi send tương lai chưa xác nhận là thành công và không commit offset của record chưa recover an toàn.

### 26.5. Stop với Kafka transaction mở

Gửi transactional output rồi shutdown trước commit. Xác nhận read_committed downstream không nhìn thấy output của aborted transaction và input record có thể redeliver.

### 26.6. Forced termination

Chạy cùng kịch bản nhưng dùng forced kill trong môi trường test. Đây là cách kiểm chứng idempotency thật sự: graceful path không chạy, nhưng pipeline vẫn phải phục hồi hợp lệ.

### 26.7. Rolling update nhiều replicas

Deploy thử với số replicas và concurrency như production. Xem rebalance duration, lag spike, shutdown time, số records replay và khả năng downstream bắt kịp backlog.

Không chạy kill/scale-down thử nghiệm phá hoại trên production cluster hoặc thay đổi topic quan trọng để kiểm thử; dùng môi trường và quyền được cấp riêng.

## 27. Quan sát và cảnh báo trong shutdown

Các tín hiệu nên thu thập:

| Tín hiệu | Ý nghĩa |
|---|---|
| Shutdown initiated/completed timestamps | Thời gian process nhận tín hiệu tới khi đóng xong |
| Listener container running/stopping state | Container còn hoạt động sau deadline không |
| In-flight listener count | Bao nhiêu record/task đang xử lý |
| Last processed offset và committed offset | Có khoảng cách giữa xử lý và commit không |
| Producer pending send count/failures | Có output chưa xác nhận khi shutdown không |
| Transaction commits/aborts | Transaction có hoàn tất hoặc rollback đúng không |
| Consumer group rebalance count/duration | Partition chuyển giao mất bao lâu |
| Partition lag và oldest record age | Group có phục hồi tiến độ sau rollout không |
| Duplicate/idempotency hits | Bao nhiêu record replay được hấp thụ an toàn |
| DLT recovery failure | Record lỗi có được lưu trước shutdown không |
| Kubernetes termination reason | SIGTERM bình thường, OOMKilled hay cưỡng bức |
| Grace-period exceeded count | Có instance thường xuyên không dừng kịp không |

Một log shutdown nên ghi:

- Application instance/pod ID.
- Consumer group, listener ID và số partitions đang sở hữu.
- Thời điểm bắt đầu và hoàn tất stop.
- Số record/tasks in-flight ban đầu và còn lại.
- Offset xử lý cuối cùng và offset commit gần nhất nếu có.
- Kết quả producer/transaction/recoverer đang chờ.
- Thời gian chờ và lý do timeout.

Không log toàn bộ payload/credential. Event ID/correlation ID đủ để truy dấu record đã xử lý một phần.

## 28. Runbook: Pod bị SIGKILL vì không dừng kịp

### Bước 1: Xác định loại termination

Xem Pod status, termination reason, exit code và application shutdown logs. Phân biệt SIGTERM có xử lý nhưng vượt deadline, JVM không nhận tín hiệu, OOMKill hoặc node disruption.

### Bước 2: Tìm thành phần làm chậm

- Listener có HTTP/database calls không timeout?
- max.poll.records và stopImmediate đang cấu hình thế nào?
- Batch listener có xử lý quá lâu không?
- Async executor còn tasks/queue không?
- Producer/DLT send hoặc Kafka transaction đang chờ broker?
- Spring lifecycle phase timeout đang là bao nhiêu?

### Bước 3: Kiểm tra dữ liệu

- Committed offset của group sau restart là gì?
- Có records bị redeliver không?
- Side effect database/HTTP có duplicate không?
- Có DLT hoặc retry topic backlog mới không?
- Transaction output có bị abort hoặc bị downstream read_uncommitted xử lý không?

### Bước 4: Khắc phục root cause

Đặt timeout dependency, giảm poll/batch, stopImmediate khi phù hợp, drain executor bằng completion signals, sửa producer timeout/backoff hoặc điều chỉnh grace period theo đo lường thực tế.

### Bước 5: Xác nhận rollout tiếp theo

Thử terminate lại trong môi trường đại diện. Xác nhận stop duration dưới grace period, lag phục hồi, group rebalance ổn định và không có side effect lặp không được kiểm soát.

## 29. Runbook: consumer lag tăng sau rolling deployment

Lag tăng nhẹ trong rebalance có thể là hiệu ứng bình thường, nhưng tăng kéo dài cần điều tra.

1. Kiểm tra có đủ active consumers sau rollout không.
2. Đối chiếu partitions assigned cho từng instance và concurrency.
3. Xem rebalance count/duration, assignor và group membership.
4. Xác nhận consumer mới thật sự chạy và listener/container factories khởi động đúng.
5. Xem oldest record age và throughput sau rollout.
6. Kiểm tra database/HTTP capacity vì partitions có thể dồn về ít instances.
7. Nếu static membership, kiểm tra các member cũ có còn giữ assignment qua session timeout không.
8. Kiểm tra replay/duplicates có gây thêm tải hoặc lock contention không.
9. Điều chỉnh rolling update strategy, grace period và readiness/health policies phù hợp.

Một dashboard chỉ có consumer group lag tổng thể có thể che khuất một partition bị kẹt do poison record hoặc một static member chưa giải phóng partition.

## 30. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ đặt terminationGracePeriodSeconds, không kiểm soát listener | Listener có thể vẫn đang poll/xử lý lâu | Dùng Spring lifecycle và stop policy phù hợp |
| Dựa vào readiness=false để ngừng Kafka consumption | Kafka group không đọc Kubernetes readiness | Dừng/pause listener bằng Kafka lifecycle |
| preStop chỉ sleep rất lâu | Hết grace budget trước lúc JVM nhận SIGTERM | Giữ preStop tối thiểu và đo end-to-end shutdown |
| Dùng shell entrypoint không forward SIGTERM | JVM không chạy shutdown hooks | Dùng exec ENTRYPOINT hoặc forward signals |
| Dùng stopImmediate mà không hiểu offset | Record trong poll chưa xử lý có thể replay | Bảo đảm AckMode/commit đúng phần đã xử lý |
| max.poll.records lớn, listener chậm, grace ngắn | Forced kill khi chưa drain hết poll | Giảm poll/batch, đặt timeout, nâng grace hợp lý |
| Ack trước khi ghi database/HTTP thành công | Silent business data loss khi shutdown | Ack sau xử lý bền vững |
| Fire-and-forget async task từ @KafkaListener | Container commit trước khi task hoàn tất | Async contract + in-flight drain + ack đúng |
| Đóng producer trước khi listener stop | Pending output/DLT có thể thất bại | Điều phối SmartLifecycle và dependencies |
| Gọi flush rồi tưởng transaction đã commit | EOS semantics sai | Commit/abort transaction theo manager |
| Tăng max.poll.interval.ms để xử lý shutdown treo | Che dependency không timeout | Sửa root cause và thiết kế retry/budget |
| Cố commit offset sau onPartitionsLost | Consumer có thể đã mất quyền partition | Không commit như owner cũ; chấp nhận redelivery |
| Cho rằng graceful shutdown loại bỏ duplicate | Forced kill và commit failure vẫn xảy ra | Consumer/business idempotency |
| Chỉ theo dõi lag ngay trước stop | Không thấy backlog ở retry topics và DLT | Giám sát toàn pipeline |
| Thử shutdown chỉ khi không có tải | Không phát hiện in-flight race | Test có load, rebalance, forced kill |

## 31. Checklist production

Trước khi vận hành listener trên Kubernetes hoặc hệ thống orchestration:

1. Spring Boot có nhận được SIGTERM và đóng ApplicationContext không?
2. Kafka listener containers có tham gia SmartLifecycle với shutdown phase hợp lý không?
3. stopImmediate đã được cân nhắc theo poll/batch size và latency chưa?
4. max.poll.records có phù hợp thời gian xử lý cuối cùng khi stop không?
5. Các HTTP/database calls trong listener có timeout hữu hạn không?
6. AckMode và manual acknowledgement có bảo đảm không commit trước xử lý thành công không?
7. Có custom async executor nào cần drain trước khi producer/database close không?
8. In-flight tasks có completion signals và shutdown deadline không?
9. Producer sends, DLT sends và Kafka transactions có outcome được xác nhận phù hợp không?
10. Grace period của orchestrator có lớn hơn thời gian lifecycle stop đo được cộng dự phòng không?
11. preStop hook có tiêu tốn quá nhiều thời gian grace không?
12. Readiness policy có được phân biệt với Kafka consumer group membership không?
13. Kafka transaction timeout, max.poll.interval.ms và shutdown timeout có được đánh giá riêng không?
14. Rolling update strategy có giữ đủ active consumers và downstream capacity không?
15. Nếu dùng static membership, có hiểu ảnh hưởng của session timeout đến reassignment không?
16. Side effect ngoài Kafka có idempotency key hoặc inbox/outbox không?
17. Có metrics cho stop duration, in-flight, commit, rebalance, lag và duplicate không?
18. Có test dừng giữa record, giữa poll, trong Kafka transaction và khi DLT send không?
19. Có test forced kill để chứng minh hệ thống vẫn phục hồi khi graceful path không chạy không?
20. Đội vận hành có runbook xử lý Pod không dừng kịp và lag tăng sau rollout không?

**Kết luận:** Graceful shutdown trong Spring Kafka là một quy trình lifecycle và rebalance, không chỉ là gọi close() hoặc sleep vài giây trước khi Pod thoát. Ứng dụng cần ngừng nhận việc tại container, xử lý phần in-flight theo stop policy, chỉ commit những offset có outcome an toàn, kết thúc hoặc abort Kafka transactions đúng ranh giới, rồi đóng resources trong ngân sách shutdown. Spring SmartLifecycle, stopImmediate, AckMode và Kubernetes terminationGracePeriodSeconds hỗ trợ điều phối, nhưng **idempotency và khả năng replay** vẫn là nền tảng bảo vệ dữ liệu khi shutdown không hoàn tất như dự kiến.
