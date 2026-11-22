# Restart container sau lỗi

## 1. Mục tiêu của restart container

Trong Spring Kafka, một **listener container** quản lý KafkaConsumer, poll loop, consumer group membership, partition assignment, offset commit và lời gọi tới phương thức @KafkaListener. Khi consumer gặp lỗi, có những trường hợp container tiếp tục chạy và tự phục hồi, nhưng cũng có trường hợp nó phải dừng.

**Restart container sau lỗi** là thao tác khởi động lại lifecycle của listener container đã dừng hoặc không còn hoạt động phù hợp, sau khi xác định và xử lý nguyên nhân. Restart không đồng nghĩa với retry record; nếu lỗi chỉ nằm trong một record nghiệp vụ, **DefaultErrorHandler**, BackOff hoặc DLT thường là hướng xử lý chính xác hơn.

~~~text
KafkaListenerContainer
         |
         v
   KafkaConsumer.poll()
         |
    +----+--------------------+
    |                         |
Record nhận được           Lỗi tầng poll / lifecycle
    |                         |
    v                         v
@KafkaListener             Phân loại lỗi
    |                         |
 +--+---------+         +-----+-----------------+
 |            |         |                       |
OK         Exception   Có thể retry         Không thể tiếp tục
 |            |         |                       |
 v            v         v                       v
Commit     Error       Kafka client /       Container STOPPED
theo       handler     container retry             |
policy       |                                   v
          Retry /                            Khắc phục nguyên nhân
          Recover                                 |
             |                                    v
             v                              Restart có kiểm soát
      Container tiếp tục                          |
                                                  v
                                           Join consumer group
                                                  |
                                                  v
                                           Nhận assignment mới
~~~

Một chính sách vận hành tốt phải trả lời được: lỗi nào thực sự khiến container dừng, ai được phép restart, khi nào restart, có giới hạn số lần hay không và làm sao xác minh consumer đã xử lý dữ liệu trở lại.

## 2. Phân biệt KafkaConsumer và các loại container

| Thành phần | Trách nhiệm |
|---|---|
| KafkaConsumer | Client Kafka thực hiện subscribe, poll, commit và tham gia group |
| KafkaMessageListenerContainer | Quản lý một consumer cùng consumer thread |
| ConcurrentMessageListenerContainer | Parent container quản lý nhiều child containers |
| ConcurrentKafkaListenerContainerFactory | Tạo container từ endpoint @KafkaListener |
| KafkaListenerEndpointRegistry | Tìm và điều khiển các container đăng ký theo listener ID |
| DefaultErrorHandler | Retry, seek/redeliver hoặc recover lỗi record theo cấu hình |
| KafkaTransactionManager | Quản lý transaction Kafka trong những luồng hỗ trợ |
| Spring application events | Thông báo trạng thái/lifecycle của consumer và container |

Ví dụ listener có concurrency bằng ba:

~~~text
ConcurrentMessageListenerContainer (parent)
         |
         +-- Child #0 --> KafkaConsumer #0
         +-- Child #1 --> KafkaConsumer #1
         +-- Child #2 --> KafkaConsumer #2
~~~

Một child container có thể gặp lỗi và dừng trong khi các child khác vẫn hoạt động. **ConsumerStoppedEvent của một child không tự chứng minh parent đã dừng hoàn toàn.** Điều này quan trọng nếu ứng dụng dự định tự restart toàn endpoint từ event.

## 3. Lifecycle cơ bản

~~~text
CREATED
   |
   | context startup / start()
   v
STARTING
   |
   | create consumer, subscribe, join group
   v
RUNNING
   |
   +--------------------------+
   |                          |
   | stop bình thường         | lỗi nghiêm trọng
   v                          v
STOPPING                   STOPPING / ERROR
   |                          |
   +-------------+------------+
                 |
                 v
              STOPPED
                 |
                 | start() khi đã an toàn
                 v
              STARTING
                 |
                 v
              RUNNING
~~~

Sơ đồ mô tả lifecycle theo khái niệm, không phải tên enum đầy đủ trong Spring Kafka. API **isRunning()** cho biết trạng thái lifecycle của container nhưng chưa đủ để kết luận consumer khỏe.

Một container có thể **isRunning=true** mà vẫn:

- Chưa được assign partition vì group đang rebalance.
- Đang pause.
- Mất kết nối broker và chờ reconnect.
- Bị chậm do downstream hoặc consumer lag cao.
- Đang retry một lỗi qua error handler.

Ngược lại, **isRunning=false** không chỉ rõ là operator chủ động dừng, application shutdown hay container dừng vì lỗi.

## 4. Phân loại lỗi trước khi restart

| Nhóm lỗi | Dấu hiệu điển hình | Hướng xử lý chính |
|---|---|---|
| Business exception | Listener xử lý record thất bại | DefaultErrorHandler, retry/DLT |
| Poison record | Cùng một record thất bại lặp | Non-retryable classification hoặc DLT |
| Deserialization failure | Không chuyển được key/value bytes | ErrorHandlingDeserializer và error handler |
| Network tạm thời | Broker disconnect, reconnect | Kafka client retry/reconnect; quan sát trước khi restart |
| Authentication failure | Sai SASL credential hoặc TLS config | Sửa secret/cấu hình, cân nhắc auth retry interval |
| Authorization failure | Thiếu READ topic/group | Sửa ACL; restart chỉ sau khi quyền hợp lệ |
| Poll thread chết | ConsumerStoppedEvent có lý do lỗi | Điều tra cause, đánh giá container restart |
| Không start được | ConsumerFailedToStartEvent | Kiểm tra executor, tài nguyên và cấu hình |
| Producer fenced | ProducerFencedException ở transactional listener | Kiểm tra transactional ID, producer lifecycle |
| Không có offset | auto.offset.reset=none, group chưa có offset | Quyết định offset khởi đầu hợp lệ |
| Normal shutdown | Operator/context stop container | Không tự restart |
| Container vẫn running nhưng paused | Consumer bị pause có chủ đích | Resume khi điều kiện đủ |

**Restart là lựa chọn ở tầng lifecycle**, không phải hành động xử lý mặc định cho mọi exception.

## 5. Trước tiên hãy xử lý lỗi record bằng error handler

Với record listener, một cấu hình phổ biến là:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Ví dụ sử dụng FixedBackOff với khoảng cách 1 giây, ba lần retry sau lần xử lý đầu tiên. Khi hết retry, recoverer xử lý record theo policy.

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Nếu fulfillmentService gặp timeout tạm thời, handler có thể retry mà container vẫn chạy. Nếu dữ liệu vi phạm schema một cách cố định, có thể recover sang DLT.

### 5.1. Vì sao restart không chữa poison record?

~~~text
Consumer đọc P0 offset 101
          |
          v
Record bị lỗi validation
          |
          v
Container bị restart
          |
          v
Consumer quay lại offset 101 nếu chưa commit
          |
          v
Record lỗi lặp lại
~~~

Nếu nguyên nhân là dữ liệu, restart thường chỉ chuyển lỗi sang lần poll mới. Thay vì tạo restart loop, cần phân loại lỗi và có recovery path an toàn.

### 5.2. Dừng container theo error handler

Một số phiên bản Spring Kafka cung cấp **CommonContainerStoppingErrorHandler** để dừng listener container khi lỗi xảy ra. Đây là chính sách fail-fast, không phải cơ chế tự động sửa lỗi.

Nếu sử dụng stopping error handler, phải định nghĩa rõ khi nào cho phép restart, ai điều khiển restart và làm gì với record chưa commit. Không nên dừng rồi khởi động lập tức vô điều kiện, vì lỗi sẽ lặp.

## 6. Authentication và authorization: restart không phải bước đầu tiên

Kafka có thể từ chối client do credential không hợp lệ hoặc principal không có quyền trên topic/group. Ví dụ:

~~~text
Principal: User:order-consumer

Topic orders.created:
  READ required

Group order-fulfillment:
  READ required
~~~

Nếu thiếu READ trên group, việc restart cứ vài giây không tạo thêm quyền. Cần cập nhật ACL trước.

### 6.1. authExceptionRetryInterval

Spring Kafka có API **setAuthExceptionRetryInterval(Duration)** trên ContainerProperties ở các phiên bản hỗ trợ. Nó cho phép chờ và retry sau một số AuthenticationException hoặc AuthorizationException thay vì dừng ngay theo behavior mặc định tương ứng.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

    return factory;
}
~~~

Cần xem API/version đang triển khai để biết phạm vi exception được retry và điều kiện dừng.

Khi ACL được sửa trong broker cho đúng principal, consumer có thể phục hồi qua retry/reconnect mà không cần restart JVM, tùy tình trạng thực tế.

### 6.2. Secret rotation

Nếu secret được đặt trong environment variable lúc process khởi động, stop/start riêng Spring listener container **không tự làm environment variable thay đổi**.

Sau khi rotate credential, cần xem:

1. Nguồn secret đã cập nhật chưa?
2. Ứng dụng có cơ chế reload secret hay không?
3. ConsumerFactory có dùng credential mới không?
4. Restart listener container có tạo KafkaConsumer với cấu hình mới không?
5. Có cần restart cả pod/JVM không?

Không kết luận rằng restart container đã thành công chỉ vì API start trả về bình thường.

## 7. Quan sát container dừng qua application events

Spring Kafka phát những events liên quan lifecycle. Một số event hữu ích:

| Event | Vai trò |
|---|---|
| ConsumerStartingEvent | Consumer bắt đầu giai đoạn khởi động |
| ConsumerStartedEvent | Consumer đã khởi động |
| ConsumerStoppingEvent | Consumer đang dừng |
| ConsumerStoppedEvent | Consumer đã dừng, có thông tin reason ở version hỗ trợ |
| ConsumerFailedToStartEvent | Consumer không khởi động được đúng hạn trong điều kiện tương ứng |
| ConsumerPartitionAssignedEvent | Consumer nhận partition |
| ConsumerPartitionRevokedEvent | Partition bị thu hồi |
| ConsumerPartitionLostEvent | Consumer mất ownership partition |
| NonResponsiveConsumerEvent | Poll không đáp ứng trong khoảng giám sát của container |

Các event này phụ thuộc lifecycle của framework; process bị kill đột ngột có thể không kịp phát event dừng.

Observer:

~~~java
@Component
public class KafkaConsumerLifecycleObserver {

    @EventListener
    public void stopped(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped; reason={}, source={}",
            event.getReason(),
            event.getSource()
        );
    }

    @EventListener
    public void assigned(ConsumerPartitionAssignedEvent event) {
        log.info("Kafka partitions assigned: {}", event.getPartitions());
    }
}
~~~

Tên enum reason cụ thể khác nhau giữa các phiên bản. Hãy log giá trị thực tế thay vì hardcode một tập nguyên nhân nếu API version chưa được xác nhận.

### 7.1. Event observer không phải restart controller

Một observer chỉ nên ghi metrics/log và phát tín hiệu vận hành. **Đừng gọi start() ngay trong ConsumerStoppedEvent handler** mà không kiểm tra trạng thái parent, lý do stop, shutdown và backoff.

Event có thể đến từ consumer thread hoặc trong quá trình stop chưa hoàn tất. Nếu multicaster chạy bất đồng bộ, callback có thể ở thread khác. Lifecycle control cần được điều phối riêng.

## 8. ConsumerFailedToStartEvent

Lỗi không start được có thể liên quan tới:

- Task executor không có thread khả dụng.
- CPU hoặc memory bị bão hòa.
- Số concurrent consumer vượt năng lực pod.
- Custom container factory cấu hình không phù hợp.
- Context đang startup/shutdown.
- Bean dependency hoặc security configuration không hợp lệ.

Khi xuất hiện **ConsumerFailedToStartEvent**, không nên restart ngay hàng chục lần; nếu lỗi là thread exhaustion, các lần khởi động lại chỉ làm thiếu tài nguyên trầm trọng hơn.

Cần xem logs của container và thread executor, sizing concurrency, JVM heap, GC, thread pool và broker connection state.

## 9. Lấy container bằng KafkaListenerEndpointRegistry

Đặt ID rõ ràng trên listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Dùng registry để truy xuất:

~~~java
@Service
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }

    public void startIfStopped(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener: " + listenerId
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }
}
~~~

**Listener ID khác group ID**. Registry tra container theo @KafkaListener(id=...), không phải group.id Kafka.

Ngoài ra, container được tạo trực tiếp như Spring bean hoặc theo custom logic có thể không được đăng ký trong registry theo cùng cách. Với các container đó, phải dùng reference/bean lifecycle phù hợp.

## 10. Restart sau khi root cause đã được khắc phục

Quy trình thao tác an toàn:

1. Ghi nhận listener ID, container state và stop reason.
2. Xác định exception gốc.
3. Phân biệt intentional stop, application shutdown và lỗi bất thường.
4. Sửa ACL, secret, serializer, broker, topic hoặc dependency tương ứng.
5. Xác nhận health của thành phần phụ thuộc.
6. Nếu container đã stopped, gọi start theo API lifecycle.
7. Nếu container vẫn running nhưng cần restart, stop rồi chờ completion trước khi start.
8. Theo dõi consumer group rebalance, assignment và lag.
9. Xác nhận record processing thực sự tiếp tục.

Nếu container đã dừng:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container == null) {
    throw new IllegalStateException("Listener is not registered");
}

if (!container.isRunning()) {
    container.start();
}
~~~

Không nên thêm logic reset offset vào restart mặc định. Restart với committed offsets hiện tại và reset offset là hai thao tác vận hành khác nhau, có ảnh hưởng dữ liệu khác nhau.

## 11. Stop-complete trước start

Một lỗi phổ biến là:

~~~java
container.stop();
container.start();
~~~

Hai lời gọi liên tiếp không đảm bảo consumer threads đã dừng hoàn tất nếu stop đang hoạt động bất đồng bộ. Container còn đang stopping có thể không nhận start theo cách mong muốn.

Spring Lifecycle hỗ trợ **stop(Runnable)** để nhận callback sau khi stop hoàn tất.

Ví dụ cho Spring Framework 6 / Java 17 với TaskScheduler:

~~~java
@Service
public class KafkaRestartService {

    private final KafkaListenerEndpointRegistry registry;
    private final TaskScheduler scheduler;

    public KafkaRestartService(
            KafkaListenerEndpointRegistry registry,
            TaskScheduler scheduler) {

        this.registry = registry;
        this.scheduler = scheduler;
    }

    public void restart(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener: " + listenerId
            );
        }

        Runnable scheduleStart = () ->
            scheduler.schedule(
                () -> {
                    if (!container.isRunning()) {
                        container.start();
                    }
                },
                Instant.now().plusSeconds(5)
            );

        if (container.isRunning()) {
            container.stop(scheduleStart);
        }
        else {
            scheduleStart.run();
        }
    }
}
~~~

Điều kiện của ví dụ:

- TaskScheduler là Spring-managed bean đã được khởi tạo.
- API schedule nhận Instant trong Spring Framework 6; phiên bản cũ có thể nhận Date.
- Code cần imports tương ứng.
- Caller phải có quyền vận hành.
- Không chạy restart khi application context đang shutdown.
- Trong production, cần tránh nhiều request restart đồng thời.

Callback stop chỉ **schedule** thao tác start; bản thân start được thực hiện trên scheduler thread, không chạy trực tiếp khi consumer thread đang kết thúc.

### 11.1. Chống concurrent restart

Nếu hai operator requests hoặc hai event callbacks cùng yêu cầu restart, có thể xảy ra cuộc đua giữa stop và start. Dùng trạng thái riêng cho listener ID:

~~~text
restartRequested
        |
        v
Check restartInProgress?
   /                \
 YES                 NO
  |                   |
  v                   v
ignore/log        mark in progress
                      |
                      v
              stop until complete
                      |
                      v
                  schedule start
                      |
                      v
                  clear state
~~~

Có thể triển khai bằng ConcurrentHashMap và AtomicBoolean, kèm state machine cho **STOPPING**, **WAITING_TO_RESTART**, **STARTING** và **RUNNING**. Khi start thất bại, phải giải phóng guard hoặc chuyển sang trạng thái retry chứ không giữ restartInProgress mãi mãi.

## 12. Tránh auto-restart trực tiếp trong ConsumerStoppedEvent

Đoạn code sau không an toàn như một chính sách tổng quát:

~~~java
@EventListener
public void stopped(ConsumerStoppedEvent event) {
    registry.getListenerContainer("orders-listener").start();
}
~~~

Vấn đề:

- Có thể nhận event khi container stop bình thường.
- Event có thể được phát từ child container trong parent concurrent container.
- Consumer thread hoặc parent còn đang stopping.
- Application context có thể đang shutdown.
- Root cause vẫn còn, dẫn tới restart loop.
- Không có backoff hay restart budget.
- Không xác nhận assignment hoặc processing sau khi start.

Nếu cần auto-restart, event listener chỉ nên ghi nhận nguyên nhân và gửi yêu cầu tới **restart coordinator** chạy trên executor/scheduler riêng.

### 12.1. Một child stopped không đồng nghĩa toàn endpoint stopped

~~~text
ConcurrentMessageListenerContainer
   |
   +-- child #0 RUNNING
   +-- child #1 STOPPED (error)
   +-- child #2 RUNNING
~~~

Parent có thể vẫn báo isRunning=true. Gọi parent.start() không nhất thiết khôi phục child lỗi theo ý muốn.

Cần quyết định policy:

- Chấp nhận giảm capacity tạm thời và alert.
- Dừng toàn endpoint rồi restart sau khi stop-complete.
- Thực hiện recovery riêng theo API/version được hỗ trợ.
- Để orchestrator restart pod trong trường hợp không thể phục hồi một child an toàn.

Không dựa vào một child event để start parent vô điều kiện.

## 13. Backoff, jitter và restart budget

Restart nhanh liên tục có thể gây:

- Connection/SASL/TLS handshake storm.
- Rebalance liên tục.
- Consumer lag tăng.
- Broker group coordinator chịu tải thêm.
- Log noise che khuất lỗi gốc.
- Nhiều pod cùng restart gây thundering herd.

Policy đơn giản:

~~~text
Attempt 1: 5 seconds
Attempt 2: 10 seconds
Attempt 3: 20 seconds
Attempt 4: 40 seconds
Attempt 5: 60 seconds (cap)
~~~

Có thể bổ sung jitter nhỏ để những instance không chạy cùng nhịp.

~~~text
delay(attempt) =
   min(maxDelay, baseDelay * 2^(attempt - 1))
   + randomJitter
~~~

Giới hạn số attempts trong một khoảng thời gian hoặc mở circuit sau một số failure liên tiếp. Khi vượt budget, alert và yêu cầu operator can thiệp.

Không auto-restart vô hạn các lỗi không thể tự phục hồi như ACL sai, password sai, topic không tồn tại theo cấu hình không cho phép, serialization config sai hoặc transactional ID collision.

## 14. Không restart trong application shutdown

Khi Spring context đang đóng, container sẽ được stop theo lifecycle. Event **ConsumerStoppedEvent** là bình thường trong quá trình này.

Nếu auto-restart listener từ event đó, pod có thể không tắt đúng hạn hoặc scheduler vẫn cố tạo consumer mới khi các dependency đã bị destroy.

Một restart coordinator nên có cờ trạng thái shutdown được đặt từ **ContextClosedEvent**, hoặc kiểm tra trạng thái application lifecycle trước khi chạy scheduled restart.

Ví dụ ý tưởng:

~~~java
private volatile boolean shuttingDown;

@EventListener
public void contextClosed(ContextClosedEvent event) {
    shuttingDown = true;
}

public void restartIfAllowed(MessageListenerContainer container) {
    if (shuttingDown) {
        return;
    }

    // Áp dụng reason, backoff, budget và stop-complete.
}
~~~

Đây chỉ là một phần bảo vệ; production còn cần cancel scheduled tasks và release scheduler khi context đóng.

## 15. Restart listener và restart pod là hai cấp khác nhau

| Phục hồi | Ảnh hưởng |
|---|---|
| Spring container stop/start | Tạo lại consumer lifecycle trong cùng JVM |
| Application process restart | Khởi tạo lại toàn bộ Spring context, beans và client factories |
| Kubernetes pod restart | Thay process/container, có thể nhận env vars hoặc mounted secrets mới tùy triển khai |
| Pause/resume | Tạm dừng tiêu thụ trong khi thường vẫn giữ group membership |
| Retry record | Giữ listener container hoạt động và xử lý lỗi dữ liệu cụ thể |

Restart pod có thể giải quyết tình huống config/secret chỉ được nạp lúc JVM start. Nhưng cũng gây cold start, warm-up và rebalance lớn hơn so với restart riêng listener.

### 15.1. Liveness và readiness

Không nên để liveness fail chỉ vì Kafka tạm mất kết nối nếu điều đó tạo pod restart storm. Có thể biểu diễn tình trạng broker hoặc consumer degraded bằng readiness/health detail phù hợp.

Với service chỉ chạy Kafka consumers, Kubernetes readiness không thay thế Kafka group assignment. Dù pod ready hay không, membership vẫn do consumer poll/heartbeat và group coordinator quản lý.

## 16. Rebalance sau restart

Khi một consumer rời group, partition của nó có thể được giao lại. Khi container start, consumer mới join group và Kafka có thể rebalance lần nữa.

~~~text
Before:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

Stop A:
  Consumer B may receive P0, P1, P2, P3

Start A:
  Group rebalances
  Consumer A -> P0, P1
  Consumer B -> P2, P3
~~~

Đây chỉ là sơ đồ minh họa; assignment thực tế phụ thuộc assignor và membership. Với cooperative rebalance, partition có thể được di chuyển theo từng bước.

**Restart liên tục có thể gây rebalance liên tục**, làm throughput giảm dù nhiều consumer vẫn sống. Vì vậy, sau restart cần đo:

- Rebalance count/duration.
- Partition assignment events.
- Consumer lag per partition.
- Throughput và processing latency.
- Số attempts restart.

## 17. Offset commit và record redelivery

Kafka group lưu offset tiếp theo cần đọc cho từng partition. Nếu listener đã xử lý một record nhưng offset chưa commit lúc container dừng, record có thể được giao lại sau restart.

Ví dụ:

~~~text
Committed offset: 100

Consumer A:
  offset 100 -> business side effect OK
  offset 101 -> business side effect OK
  offset 102 -> lỗi
  crash trước commit

Consumer sau restart:
  đọc lại từ offset 100
~~~

Đây là đặc điểm của at-least-once delivery. Restart không bảo đảm exactly-once cho database/HTTP side effect.

### 17.1. Idempotency

Với nghiệp vụ Order Fulfillment, mỗi event nên có event ID ổn định. Một bảng processed_event có thể dùng unique constraint:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng DB transaction, ghi dấu vết event và thay đổi nghiệp vụ. Khi event được giao lại, unique constraint giúp phát hiện duplicate và tránh side effect lần hai.

Chỉ kiểm tra **existsById** rồi mới insert là chưa đủ vì race condition. DB unique constraint và transaction thực tế mới là lớp bảo vệ quan trọng.

### 17.2. Graceful shutdown

Stop có kiểm soát tạo cơ hội để container hoàn tất xử lý và commit theo AckMode. Tuy nhiên, nếu listener đang block hoặc pod bị kill trước thời hạn, vẫn có thể có record cần redelivery.

Cần cân đối stop timeout, processing p95/p99, retry duration, transaction timeout và Kubernetes termination grace period.

## 18. Transactional listener và ProducerFencedException

Trong consume-transform-produce, listener có thể ghi output Kafka qua KafkaTemplate và đưa input offsets vào cùng transaction. Nếu transaction abort, output chưa commit không được consumer read_committed nhìn thấy, offset input không commit trong transaction đó.

Khi container restart, input record có thể được giao lại. Đây là hành vi phù hợp với Kafka transaction semantics.

Tuy nhiên, khi producer bị **fenced** do transactional ID trùng:

- Producer cũ không thể tiếp tục transaction bình thường.
- Cần tìm instance nào tạo cùng transactional ID.
- Kiểm tra transaction ID prefix của các pod.
- Để Kafka transaction manager/producer factory quản lý lifecycle.
- Không retry vô hạn cùng producer bị fence.

Nếu lỗi nằm trong record khi transactional listener xử lý, Spring Kafka có thể dùng **AfterRollbackProcessor** để retry hoặc recover sau transaction rollback. Không cần restart toàn container cho mọi transaction abort.

## 19. Pause/resume khác stop/start

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pause();
}
~~~

Khi điều kiện phục hồi:

~~~java
if (container != null) {
    container.resume();
}
~~~

| Thao tác | Tác động thông thường |
|---|---|
| pause | Tạm ngừng nhận/xử lý record theo container API, vẫn duy trì group membership nếu poll phù hợp |
| resume | Tiếp tục tiêu thụ |
| stop | Dừng consumer/container, có thể rời group |
| start | Khởi tạo lại consumer và join group |
| Pod restart | Khởi động lại toàn process/JVM |

Nếu downstream bảo trì ngắn, pause/resume có thể tránh nhiều rebalance hơn stop/start. Nhưng pause không khôi phục một poll thread đã chết.

Không để container pause quá lâu mà thiếu monitoring; consumer lag sẽ tăng và event freshness có thể vi phạm SLO.

## 20. autoStartup và startup có kiểm soát

Spring Kafka cho phép listener không tự start khi context khởi động:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    autoStartup = "false"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Sau khi dependencies sẵn sàng:

~~~java
registry.getListenerContainer("orders-listener").start();
~~~

**autoStartup=false không phải cơ chế tự restart sau lỗi.** Nó chỉ quyết định lúc khởi động ứng dụng có tự start listener hay không.

Cách này hữu ích khi cần warm-up state, kiểm tra access policy hoặc đợi external dependency trước khi cho Kafka consumer nhận record.

## 21. Lỗi không có committed offset

Nếu consumer group chưa có committed offset và **auto.offset.reset=none**, Kafka client có thể không xác định được vị trí bắt đầu hợp lệ.

Khi đó không nên restart mãi. Phải chọn một chính sách offset:

- **earliest** nếu cần xử lý backlog từ đầu.
- **latest** nếu nghiệp vụ cho phép chỉ đọc dữ liệu mới.
- Offset được operator quyết định theo một quy trình replay.
- Khởi tạo consumer group sau khi có checkpoint phù hợp.

Thay đổi offset ảnh hưởng dữ liệu nghiệp vụ, khác hẳn thao tác restart container. Không chọn latest chỉ để làm mất lỗi nếu backlog cũ vẫn cần được xử lý.

## 22. Monitoring và alert

| Metric / tín hiệu | Mục tiêu |
|---|---|
| Container isRunning | Xác định trạng thái lifecycle |
| ConsumerStoppedEvent reason | Tìm nguyên nhân container dừng |
| ConsumerFailedToStartEvent | Phát hiện startup failure |
| Restart attempt count | Phát hiện restart loop |
| Time since last successful poll | Phát hiện consumer không có tiến độ |
| Partition assignment | Xác nhận join group sau start |
| Rebalance rate/duration | Đo tác động của restart |
| Consumer lag per partition | Đo backlog sau restart |
| Listener processing duration | Tìm batch/record processing chậm |
| Commit failures | Đánh giá offset progression |
| Authentication/authorization errors | Phân biệt lỗi credential và ACL |
| Producer fencing | Phát hiện transactional ID collision |
| DLT publish failures | Phát hiện recovery chưa thành công |
| Pod restarts/OOM/GC | Tìm nguyên nhân resource |

Một log lifecycle hữu ích:

~~~text
timestamp=2026-11-15T10:21:34Z
service=order-fulfillment
listenerId=orders-listener
groupId=order-fulfillment
event=consumer_stopped
reason=ERROR
restartAttempt=2
scheduledDelaySeconds=10
action=restart_pending
~~~

Không log JAAS password, token, private key hoặc raw payload. Theo dõi container stopped cùng lag và partition assignment sẽ giúp tránh alert sai khi topic không có dữ liệu.

### 22.1. Xác minh hồi phục

Sau khi gọi start(), cần xác minh:

1. Container chuyển running.
2. Consumer được tạo và group membership ổn định.
3. Partition assignment xuất hiện.
4. Listener xử lý được event hợp lệ.
5. Commit offset tiến theo policy.
6. Consumer lag giảm nếu topic có backlog.
7. Không còn lỗi authentication, fencing hoặc restart loop.
8. DLT/retry tiếp tục hoạt động.

**start() trả về mà không ném exception không chứng minh mọi điều trên đã thành công.**

## 23. Integration tests cho restart

Có thể dùng Embedded Kafka hoặc Testcontainers để thử lifecycle với broker thực.

### 23.1. Test stop/start

1. Khởi động listener có ID cố định.
2. Lấy container qua KafkaListenerEndpointRegistry.
3. Dừng container và đợi stop callback.
4. Xác nhận trạng thái stopped.
5. Gọi start qua scheduler/management thread.
6. Đợi partition assignment.
7. Publish một record mới và xác nhận listener xử lý.

### 23.2. Test rebalance

1. Khởi động hai consumer cùng group.
2. Ghi nhận assignment ban đầu.
3. Stop một consumer.
4. Chờ consumer còn lại nhận partition.
5. Start lại consumer đã dừng.
6. Xác nhận assignment mới và không có consumer nào sở hữu trùng partition trong cùng group ở một trạng thái assignment hợp lệ.
7. Kiểm tra lag và xử lý.

### 23.3. Test crash trước commit

1. Gửi event có ID ổn định.
2. Làm consumer tạo DB side effect nhưng crash trước Kafka offset commit.
3. Khởi động lại consumer.
4. Quan sát record có thể được giao lại.
5. Xác nhận DB unique constraint/idempotency ngăn side effect trùng.

### 23.4. Test lỗi không thể tự phục hồi

1. Cấu hình ACL hoặc credential sai trong môi trường test.
2. Xác nhận restart coordinator không lặp vô hạn.
3. Sửa quyền hoặc secret.
4. Chỉ restart khi điều kiện đủ.
5. Xác nhận group và record processing phục hồi.

### 23.5. Test shutdown

Khi context đóng, event stopped không được kích hoạt restart mới. Scheduler phải hủy hoặc bỏ qua scheduled tasks còn chờ và process hoàn tất graceful shutdown.

## 24. Ví dụ thực tế: Order Fulfillment sau lỗi ACL

Giả sử Order Fulfillment chạy hai consumer con với group **order-fulfillment** và đọc topic **orders.created**. Một thay đổi ACL khiến principal ứng dụng mất quyền READ trên group.

Triệu chứng:

~~~text
GroupAuthorizationException
Consumer stopped or auth retry scheduled
Listener no longer processes records
Consumer lag increases
~~~

Quy trình:

1. Đọc exception gốc và xác định group ID thực tế.
2. Kiểm tra principal và ACL READ trên topic/group.
3. Xem ConsumerStoppedEvent và trạng thái parent container.
4. Xác định có authExceptionRetryInterval hay không.
5. Sửa ACL qua quy trình quản trị Kafka.
6. Nếu consumer đang retry, quan sát khả năng phục hồi mà không restart.
7. Nếu container đã dừng, start lại có kiểm soát.
8. Đợi group rebalance và partition assignment.
9. Xác nhận lag giảm và commit offset tiến.
10. Kiểm tra duplicate detection vì record chưa commit có thể được giao lại.

Trong tình huống này, **ACL được sửa mới là nguyên nhân phục hồi**. Restart chỉ kích hoạt lại lifecycle của consumer đã dừng; nó không tạo quyền truy cập.

## 25. Runbook production

1. Xác định listener ID, topic, group ID, pod và concurrency.
2. Ghi nhận time/reason của stopped event và exception gốc.
3. Xem parent và child container states.
4. Phân biệt intentional stop/shutdown với lỗi bất thường.
5. Với record failure, ưu tiên error handler và DLT.
6. Với broker outage, kiểm tra Kafka client có tự reconnect hay không.
7. Với ACL/secret, sửa security configuration trước.
8. Với producer fencing, kiểm tra transactional ID namespace.
9. Với resource exhaustion, khôi phục executor/CPU/memory.
10. Nếu restart cần thiết, dùng registry hoặc managed container bean.
11. Điều phối stop-complete trước start.
12. Chặn concurrent requests, áp dụng backoff và restart budget.
13. Không auto-restart khi context shutdown.
14. Đợi consumer join group và nhận assignment.
15. Xem rebalance, consumer lag, commit, retry/DLT và throughput.
16. Kiểm tra idempotency của side effect có thể bị replay.
17. Ghi nguyên nhân, hành động sửa và bằng chứng phục hồi.

## 26. Những sai lầm thường gặp

**Mọi listener exception đều cần restart.** Sai; record lỗi thường được DefaultErrorHandler hoặc recovery policy xử lý.

**Container isRunning=true là đủ để nói healthy.** Sai; consumer có thể chưa nhận partition, bị pause hoặc vẫn retry hạ tầng.

**Một ConsumerStoppedEvent nghĩa là cả concurrent parent đã dừng.** Không chắc; event có thể đến từ một child.

**Gọi start() ngay trong stopped event là an toàn.** Có thể gây race với consumer thread và stop lifecycle.

**Stop rồi start liên tiếp luôn tương đương restart thành công.** Nên đợi stop-complete.

**Restart vô hạn sẽ sửa được lỗi ACL.** Không; quyền hoặc credential phải được sửa.

**Restart listener container sẽ reload mọi secret.** Không nếu secret được nạp vào environment tại JVM startup.

**Restart không tạo duplicate.** Sai; record đã xử lý nhưng chưa commit có thể được giao lại.

**Pause giống stop.** Không; pause thường giữ group membership.

**ProducerFencedException chỉ là network timeout.** Không; producer cũ không còn hợp lệ với transactional identity đó.

**Tăng concurrency sẽ chữa consumer không start.** Có thể làm tình trạng thread/resource exhaustion tệ hơn.

**Start() không ném exception là incident đã kết thúc.** Cần xác minh assignment, offset, throughput và lag.

## 27. Ghi nhớ

**Restart container sau lỗi** trong Spring Kafka là thao tác khôi phục listener lifecycle khi container đã dừng hoặc không còn có thể tiếp tục tiêu thụ an toàn. Nó khác với retry record. DefaultErrorHandler, DLT và AfterRollbackProcessor thường xử lý lỗi trong quá trình tiêu thụ mà không cần restart container.

Khi cần restart, hãy dùng KafkaListenerEndpointRegistry hoặc reference container được Spring quản lý, xác nhận root cause đã được khắc phục, điều phối stop-complete trước start và tránh thao tác trực tiếp trong consumer lifecycle event. Auto-restart cần backoff, jitter, restart budget và chặn khi application shutdown.

Restart có thể khiến consumer rời rồi tái gia nhập group, gây rebalance và replay những record chưa commit. Hãy kết hợp lifecycle monitoring, partition assignment, offset commit theo policy, idempotency của side effect và kiểm tra consumer lag để bảo đảm hệ thống thực sự phục hồi chứ không chỉ khởi động lại liên tục.
