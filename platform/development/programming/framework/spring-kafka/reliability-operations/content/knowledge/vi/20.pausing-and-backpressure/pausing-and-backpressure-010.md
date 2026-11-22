# Không gọi stop trên consumer thread

Trong Spring Kafka, một listener container quản lý vòng đời của KafkaConsumer: tạo consumer, gọi poll, giao record cho listener, xử lý lỗi, commit offset và đóng consumer khi cần. Khi hệ thống cần giảm tải hoặc ngừng tiêu thụ, ứng dụng có thể yêu cầu **pause** hoặc **stop** listener container. Hai thao tác không giống nhau; đặc biệt, **không gọi trực tiếp container.stop() trên chính consumer thread** đang thực thi listener hoặc callback của container.

Lời khuyên này là một quy tắc an toàn về **thread và lifecycle**, không phải quy tắc cú pháp Java. Consumer thread là nơi container cần tiếp tục chạy để hoàn tất các bước xử lý hiện tại và thoát khỏi vòng poll. Nếu thread đó tự thực hiện thao tác dừng có thể chờ chính nó hoặc gây xung đột với trình tự shutdown, ứng dụng có nguy cơ bị kẹt, dừng không hoàn chỉnh hoặc để lại tình trạng offset/transaction khó xác định.

Trong module Spring Kafka Reliability Operations, thiết kế đúng thường là: **phân biệt backpressure tạm thời với shutdown thực sự**, dùng container.pause()/resume() cho nhu cầu điều tiết tạm thời; nếu phải stop, **chuyển yêu cầu stop sang một executor/lifecycle coordinator chạy trên thread khác**, sau đó quan sát kết quả dừng và xử lý việc khởi động lại có kiểm soát.

## 1. Consumer thread làm gì?

KafkaConsumer không được thiết kế để truy cập đồng thời tùy ý từ nhiều thread. Spring Kafka đặt consumer trong một listener container và sử dụng thread phụ trách vòng poll.

~~~text
Spring Kafka listener container
          |
          v
    Consumer thread
          |
          +-- consumer.poll()
          |
          +-- invoke @KafkaListener
          |
          +-- invoke CommonErrorHandler (khi lỗi)
          |
          +-- handle acknowledgement / offset commit
          |
          +-- rebalance callbacks
          |
          +-- poll tiếp hoặc thoát khi container stopping
~~~

Với **record listener** đồng bộ, method được đánh dấu @KafkaListener thường được gọi trên consumer thread. Với batch listener đồng bộ, callback nhận một batch cũng thường nằm trong poll/lifecycle thread. Nhiều Spring Kafka lifecycle events và rebalance callbacks cũng được phát trên thread này.

Điều đó có nghĩa là code sau nhìn có vẻ bình thường nhưng đang cố điều khiển chính container từ bên trong thread mà container cần dùng để kết thúc vòng đời:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void onOrder(OrderEvent event) {
    if (maintenanceRequired(event)) {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        container.stop(); // KHÔNG gọi trực tiếp trên consumer thread.
    }
}
~~~

Vấn đề không nằm ở việc lấy container qua KafkaListenerEndpointRegistry, mà ở **thread thực hiện stop()** và thời điểm listener container vẫn đang trong callback xử lý record.

## 2. Vì sao gọi stop() trực tiếp có rủi ro?

Stop là một yêu cầu thay đổi lifecycle. Tùy phiên bản Spring Kafka và loại container, việc dừng có thể bao gồm đánh dấu trạng thái, hoàn tất các record đang xử lý, xử lý pending commits, đóng KafkaConsumer, giải phóng thread và phát events.

Một trình tự gây rủi ro:

~~~text
Consumer thread C
      |
      v
Kafka poll nhận record
      |
      v
@KafkaListener.onOrder()
      |
      v
container.stop() ngay trên C
      |
      +-- lifecycle cần consumer loop kết thúc
      |
      +-- consumer loop chưa thể kết thúc
      |   vì C vẫn đang chạy stop() / listener callback
      |
      v
Nguy cơ chờ vòng, timeout, shutdown không đúng trình tự
~~~

Không nên khẳng định mọi phiên bản và mọi overload stop() chắc chắn deadlock; implementation có thể có các cơ chế tránh tự chờ. Nhưng **dựa vào chi tiết implementation để gọi stop trên consumer thread là thiết kế mong manh**. Hành vi có thể thay đổi theo container type, concurrency, callback và phiên bản Spring Kafka.

Ngoài việc chặn thread, stop sai thời điểm còn làm phức tạp câu hỏi: listener đã hoàn tất side effect chưa, pending offset đã được commit chưa và transaction Kafka hiện tại có được commit hay abort không.

Đó là lý do nên coi consumer thread là nơi **phát tín hiệu cần dừng**, không phải nơi tự thực hiện toàn bộ quy trình stop.

## 3. Những nơi dễ vô tình gọi stop trên consumer thread

Các vị trí cần đặc biệt chú ý:

| Vị trí gọi | Vì sao có thể chạy trên consumer thread? | Cách tiếp cận |
|---|---|---|
| **@KafkaListener** | Container gọi listener trong vòng poll | Chỉ requestStop và giao việc cho executor riêng |
| **CommonErrorHandler** | Handler tham gia đường xử lý lỗi của container | Dùng cơ chế container stopping được framework hỗ trợ hoặc offload stop |
| **ConsumerAwareRebalanceListener** | Callback revoke/assign chạy trong quá trình poll/rebalance | Không stop trực tiếp; để callback kết thúc nhanh |
| **ListenerContainerIdleEvent listener** | Spring event có thể được publish đồng bộ từ consumer thread | Không stop trực tiếp trong handler; chuyển thread |
| **ConsumerPausedEvent/ConsumerResumedEvent listener** | Event có thể đến từ lifecycle thread | Không thực hiện stop đồng bộ trong callback |
| **Interceptor/callback gắn vào container** | Có thể chạy trong thread consumer | Tránh lifecycle operation có thể chờ callback hiện tại |

Một @EventListener không đương nhiên chạy trên thread riêng. Với ApplicationEventMulticaster đồng bộ, event handler thường chạy trên thread của bên phát event. Vì thế, **đưa stop() vào @EventListener chưa tự giải quyết được vấn đề**.

Nếu ứng dụng cấu hình event multicaster bất đồng bộ, cần phân biệt thread dispatch thực tế; không được dựa vào việc "event listener thường async" mà bỏ qua quy tắc an toàn. Một coordinator/executor do ứng dụng quản lý giúp hành vi nhất quán hơn.

## 4. Stop và pause có mục đích khác nhau

Đây là quyết định đầu tiên khi gặp backpressure.

| Khía cạnh | container.pause() | container.stop() |
|---|---|---|
| Consumer group membership | Thường được giữ trong khi container vẫn poll | Consumer đóng/rời group, có thể gây rebalance |
| Tiếp tục poll | Container có thể tiếp tục poll để duy trì group | Không poll sau khi đã dừng |
| Record mới đến listener | Tạm ngừng giao khi pause có hiệu lực | Ngừng khi container dừng theo lifecycle |
| Khôi phục | container.resume() | container.start() sau khi đã stop |
| Mục tiêu | Điều tiết tải hoặc chờ dependency phục hồi | Shutdown, maintenance, thay đổi cấu hình/lifecycle |
| Ảnh hưởng partition ownership | Không tự nhường partition chỉ vì pause | Có thể chuyển ownership sang consumer khác |
| Chi phí | Thường nhẹ hơn, không bắt buộc rebalance | Có startup/shutdown và group coordination |

Nếu database connection pool bị quá tải trong vài giây, pause thường phù hợp hơn stop. Nếu service phải hoàn toàn ngừng nhận message để shutdown, thay đổi cấu hình hoặc bảo trì dài, stop có thể hợp lý.

**Pause không bảo đảm listener đã dừng ngay tức khắc.** Yêu cầu pause được container thực thi theo poll boundary hoặc cấu hình pauseImmediate; cần quan sát trạng thái thực sự thay vì xem việc gọi pause() là bằng chứng mọi processing đã ngừng.

## 5. Cách pause/resume cho backpressure

Spring Kafka cung cấp API điều khiển container:

~~~java
@Service
public class KafkaBackpressureControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaBackpressureControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");
        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

Các method **pause()** và **resume()** là API điều khiển container được thiết kế để yêu cầu thay đổi trạng thái; chúng khác với gọi trực tiếp KafkaConsumer.pause()/resume() trên thread tùy ý. Container thực hiện việc pause/resume consumer vào thời điểm phù hợp.

Để kiểm tra:

- **isPauseRequested()** phản ánh container đang nhận yêu cầu pause.
- **isContainerPaused()** phản ánh trạng thái đã pause theo semantics container.
- Các events pause/resume có thể hỗ trợ quan sát chuyển trạng thái.

Không đồng nhất **pause requested** với **pause effective**. Trong khoảng giữa hai thời điểm, listener có thể còn xử lý records đã poll.

### Pause một partition thay vì cả container

Khi một partition có dependency nóng hoặc cần kiểm soát theo key, Spring Kafka có API pause/resume ở cấp partition:

~~~java
TopicPartition partition = new TopicPartition("orders", 2);

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isRunning()) {
    container.pausePartition(partition);
}

// Khi điều kiện phục hồi đã đạt:
if (container != null && container.isRunning()) {
    container.resumePartition(partition);
}
~~~

API này chỉ phù hợp khi partition thuộc assignment mà container có thể điều khiển; với concurrent container, cần hiểu cách Spring Kafka điều phối child consumers. Không giả định partition luôn nằm trên cùng child consumer sau một rebalance.

## 6. pauseImmediate và stopImmediate

Hai tùy chọn dễ bị nhầm nhưng có ý nghĩa khác nhau:

- **pauseImmediate**: ảnh hưởng thời điểm container ngừng giao records sau yêu cầu pause, khi phiên bản hỗ trợ.
- **stopImmediate**: ảnh hưởng thời điểm listener container ngừng xử lý records của lần poll hiện tại khi đã nhận yêu cầu stop, khi phiên bản hỗ trợ.

Ví dụ cấu hình:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
factory.getContainerProperties().setStopImmediate(true);
~~~

Trong các phiên bản Spring Kafka hỗ trợ các thuộc tính này, cấu hình immediate có thể khiến container dừng sau record hiện tại thay vì tiếp tục xử lý toàn bộ records lấy từ poll. Nhưng **immediate không đồng nghĩa interrupt business code giữa chừng**, cũng không bảo đảm không còn records đã giao cho một async worker.

Nếu container giữ các records chưa giao lại trong bộ nhớ khi pause, cần tính tới memory pressure và vòng đời container. Khi stop/restart, records chưa được xử lý phải được đọc lại theo committed offsets và semantics của container.

**Bật stopImmediate không làm an toàn việc gọi stop() trực tiếp trên consumer thread.** Vấn đề gốc là thread thực hiện lifecycle operation; cờ immediate chỉ ảnh hưởng cách container ngừng giao records.

## 7. Mẫu an toàn: tách yêu cầu stop khỏi consumer thread

Một thiết kế đơn giản là tạo **KafkaStopCoordinator**. Consumer thread chỉ gọi requestStop(); coordinator đưa công việc thực sự vào executor được quản lý riêng.

~~~text
Consumer thread
      |
      v
@KafkaListener
      |
      +-- xử lý record
      |
      +-- phát hiện cần dừng
      |
      v
stopCoordinator.requestStop("orders-listener")
      |
      v
Queue của lifecycle executor
      |
      v
Lifecycle thread (khác consumer thread)
      |
      +-- tìm container
      +-- container.stop()
      +-- ghi nhận kết quả/alert
~~~

Ưu điểm:

1. Consumer thread không tự thực hiện shutdown đồng bộ.
2. Có nơi tập trung kiểm soát restart, backoff, de-duplication và logging.
3. Lifecycle executor có thể được giới hạn số thread và queue.
4. Có thể phân biệt stop theo chủ đích với stop do lỗi.
5. Dễ kiểm thử thread ownership và trạng thái cuối.

Coordinator phải xử lý được cả **request trùng**, **executor hết khả năng nhận task** và **container đã dừng trước khi task chạy**.

## 8. Tạo lifecycle executor riêng

Ví dụ Spring configuration:

~~~java
@Configuration
public class KafkaLifecycleExecutorConfiguration {

    @Bean("kafkaLifecycleExecutor")
    public ThreadPoolTaskExecutor kafkaLifecycleExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("kafka-lifecycle-");
        executor.initialize();
        return executor;
    }
}
~~~

Thông số 2/4/64 chỉ minh họa; một hệ thống nhỏ có thể dùng ít worker hơn. Điều quan trọng là **executor riêng cho lifecycle**, không dùng chính consumer executor đang cần dừng, và không dùng một queue không giới hạn có nguy cơ tích tụ lệnh stop/start.

Nếu lifecycle executor bị bão hòa, một requestStop có thể bị từ chối. Với lệnh vận hành quan trọng, cần logging và alert hoặc đường điều khiển khác; không được âm thầm coi stop đã thành công khi task chưa được nhận.

Không tạo Thread thủ công cho mỗi record lỗi. Mỗi yêu cầu stop cần được gộp và điều phối theo container ID.

## 9. Ví dụ KafkaStopCoordinator

~~~java
@Service
public class KafkaStopCoordinator {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaStopCoordinator.class);

    private final KafkaListenerEndpointRegistry registry;
    private final TaskExecutor lifecycleExecutor;
    private final Set<String> pending = ConcurrentHashMap.newKeySet();

    public KafkaStopCoordinator(
            KafkaListenerEndpointRegistry registry,
            @Qualifier("kafkaLifecycleExecutor") TaskExecutor lifecycleExecutor) {
        this.registry = registry;
        this.lifecycleExecutor = lifecycleExecutor;
    }

    public void requestStop(String listenerId) {
        if (!pending.add(listenerId)) {
            return; // Đã có yêu cầu stop đang được xử lý.
        }

        try {
            lifecycleExecutor.execute(() -> {
                try {
                    MessageListenerContainer container =
                            registry.getListenerContainer(listenerId);

                    if (container == null) {
                        log.warn("Listener container not found: {}", listenerId);
                        return;
                    }

                    if (container.isRunning()) {
                        log.info("Stopping listener container {}", listenerId);
                        container.stop();
                    }
                }
                catch (RuntimeException ex) {
                    log.error("Unable to stop listener {}", listenerId, ex);
                    // Phát cảnh báo hoặc đưa vào cơ chế recovery được quản lý.
                }
                finally {
                    pending.remove(listenerId);
                }
            });
        }
        catch (TaskRejectedException ex) {
            pending.remove(listenerId);
            log.error("Lifecycle executor rejected stop for {}", listenerId, ex);
            // Không coi request này là stop thành công.
        }
    }
}
~~~

Mẫu này sử dụng các API Spring Kafka và Spring Task phổ biến. Cần khai báo imports, beans và logging phù hợp với ứng dụng.

Trong ví dụ, pending ngăn việc enqueue hàng chục lệnh stop cho cùng listener trong lúc lệnh trước chưa hoàn tất. Tuy nhiên, khi task chạy xong, **đã gọi stop() không đồng nghĩa mọi child consumer đã dừng** nếu implementation lifecycle bất đồng bộ. Nếu cần trạng thái cuối chắc chắn, hãy theo dõi container events hoặc sử dụng callback completion của API stop được hỗ trợ.

Khi production cần start/stop liên tiếp, coordinator nên có **state machine** thay vì chỉ dùng pending flag, để tránh một yêu cầu start mới chạy trong lúc stop cũ chưa hoàn tất.

## 10. Listener chỉ gửi yêu cầu stop sau khi xử lý xong

Một ví dụ listener có điều kiện bảo trì:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;
    private final KafkaStopCoordinator stopCoordinator;
    private final MaintenanceGate maintenanceGate;

    @KafkaListener(
            id = "orders-listener",
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderEvent event) {
        orderService.process(event);

        if (maintenanceGate.shouldStopAfterCurrentRecord()) {
            stopCoordinator.requestStop("orders-listener");
        }
    }
}
~~~

Trong ví dụ, requestStop chỉ xuất hiện **sau khi xử lý nghiệp vụ của record thành công**. Điều này giảm nguy cơ method trả về bình thường khi record còn chưa được xử lý.

Tuy nhiên, offset commit có thể diễn ra **sau khi listener trả về**, tùy AckMode và transaction mode. Không vì gọi requestStop sau process() mà kết luận offset đã được broker commit. Hãy coi record có thể được giao lại nếu container dừng/crash trước commit và bảo vệ side effect bằng idempotency.

Nếu điều kiện dừng xảy ra **trước** khi record được xử lý, không được đơn giản requestStop rồi return như một thành công. Khi đó cần pause trước khi nhận thêm record, hoặc để record thất bại theo error-handling/acknowledgment policy phù hợp.

## 11. Sai lầm: stop rồi return với record chưa xử lý

Ví dụ nguy hiểm:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    if (downstreamUnavailable()) {
        stopCoordinator.requestStop("orders-listener");
        return; // Có thể bị coi là xử lý thành công.
    }

    process(event);
}
~~~

Với record listener có AckMode.RECORD, method kết thúc bình thường có thể khiến container xem record là đã xử lý và commit offset theo chính sách. Nếu process(event) chưa chạy, record có nguy cơ bị bỏ qua về mặt nghiệp vụ.

Các cách tiếp cận phù hợp hơn:

- Đặt cơ chế điều tiết tải **trước khi giao thêm records** bằng container.pause().
- Nếu đã nhận record nhưng dependency lỗi, ném một exception retryable để error handler quản lý retry/recovery.
- Nếu dùng manual acknowledgment, chỉ acknowledge sau khi business work thật sự thành công.
- Nếu cần stop để bảo trì, phát yêu cầu stop mà vẫn để lỗi nghiệp vụ được xử lý theo đường error/rollback đúng.

Stop không phải một phương án thay thế cho việc xác định record đã được xử lý thành công hay chưa.

## 12. ListenerContainerIdleEvent và dừng an toàn

Một trường hợp thực tế: ứng dụng muốn dừng một consumer sau khi không có message trong khoảng thời gian nhất định. Spring Kafka có **ListenerContainerIdleEvent** khi được cấu hình idle event interval.

Event này có thể được publish đồng bộ trên consumer thread. Vì vậy không nên:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    container.stop(); // Không an toàn nếu event handler chạy trên consumer thread.
}
~~~

Thay vào đó:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    if (event.getListenerId().startsWith("orders-listener")) {
        stopCoordinator.requestStop("orders-listener");
    }
}
~~~

Mẫu dùng startsWith chỉ để minh họa việc lọc event; **không dùng prefix không đủ phân biệt** nếu ứng dụng có các listener IDs tương tự nhau. Với concurrent container, child container IDs có thể chứa hậu tố; thiết kế cần ánh xạ chính xác child/parent theo các ID thực tế.

Idle event không tự động nghĩa là service cần dừng. Một topic không có record trong vài phút có thể là tình trạng bình thường. Nên kết hợp điều kiện nghiệp vụ, maintenance state hoặc lịch vận hành trước khi yêu cầu stop.

## 13. Đăng ký stop bằng callback sau khi dừng

Một số API Spring Kafka container hỗ trợ **stop(Runnable callback)** để gọi callback sau khi thao tác dừng hoàn tất theo lifecycle.

~~~java
lifecycleExecutor.execute(() -> {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()) {
        container.stop(() ->
                log.info("Listener orders-listener has stopped"));
    }
});
~~~

Cần kiểm tra overload và semantics callback của phiên bản Spring Kafka đang sử dụng. Callback nên thực hiện công việc ngắn như ghi log, cập nhật trạng thái hoặc phát tín hiệu; nếu phải thao tác phức tạp, tiếp tục điều phối qua lifecycle coordinator.

Đừng gọi callback rồi ngay lập tức start lại container mà không kiểm tra stop thực sự hoàn tất. Một race giữa stop và start có thể làm kết quả lifecycle khó đoán, nhất là với concurrent containers.

## 14. ConcurrentMessageListenerContainer: stop parent hay child?

Một listener có concurrency lớn hơn 1 thường được thực thi bằng một parent ConcurrentMessageListenerContainer và nhiều child KafkaMessageListenerContainer.

~~~text
Parent: orders-listener (concurrency=3)
    |
    +-- child 0 -> consumer A -> P0, P1
    |
    +-- child 1 -> consumer B -> P2, P3
    |
    +-- child 2 -> consumer C -> P4, P5
~~~

Nếu lấy container từ KafkaListenerEndpointRegistry với ID được @KafkaListener khai báo, ứng dụng thường thao tác trên parent container. Stop parent sẽ điều phối stop các child consumers của listener đó. Nếu lấy source container trực tiếp từ một lifecycle event, có thể đó là child container; cần xác định mục tiêu thực sự.

Vì vậy:

1. Định nghĩa rõ yêu cầu là stop **toàn listener** hay stop **một child consumer**.
2. Dùng một listener ID ổn định cho logic điều khiển ở cấp listener.
3. Không duy trì một KafkaConsumer object dùng chung cho mọi child.
4. Không tự map partition cố định với child index, vì assignment có thể thay đổi khi rebalance.
5. Log parent/child ID và nhóm partitions bị ảnh hưởng khi vận hành.

Với yêu cầu giảm tải một partition, **pausePartition** thường có phạm vi ảnh hưởng phù hợp hơn stop cả parent container.

## 15. Stop gây rebalance, pause thường không

Khi container dừng hẳn, consumer không còn tham gia poll và có thể rời group. Các partitions trước đó thuộc consumer này sẽ được giao lại cho members khác nếu group còn active.

~~~text
Trước:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

A stop:
  Consumer A rời group
  Group rebalance

Sau:
  Consumer B -> P0, P1, P2, P3
~~~

Nếu ứng dụng chỉ muốn chờ database phục hồi trong thời gian ngắn, stop có thể gây rebalance không cần thiết, chuyển tải sang instance khác và tăng rủi ro xử lý lặp.

Với pause:

~~~text
Consumer A -> P0, P1 (vẫn giữ ownership)
Consumer A pause
Consumer A vẫn poll để duy trì membership
Consumer A resume khi dependency khỏe
~~~

Pause chỉ là điều tiết việc giao records cho listener, không phải nhường partitions. Vì thế pause thích hợp hơn khi cần chặn tạm thời vì backpressure.

Lưu ý: pause không bảo đảm consumer giữ group membership mãi mãi nếu bản thân ứng dụng không poll đúng hạn vì lý do khác. Phải quản lý listener time, worker saturation và max.poll.interval.ms.

## 16. Dừng container không phải thao tác tức thời

Một lệnh stop có thể cần chờ record đang xử lý và các công việc container đang hoàn tất. Với stopImmediate=false, container ở một số phiên bản có thể hoàn tất những records đã nhận từ poll trước khi dừng. Với stopImmediate=true, nó có thể dừng giao thêm sau record hiện tại.

~~~text
consumer.poll() trả record offsets 100..109
        |
        v
Listener đang xử lý offset 100
        |
        +-- nhận requestStop()
        |
        v
Container dừng theo StopImmediate/implementation policy
        |
        +-- có thể xử lý thêm records đã poll
        +-- hoặc dừng sau record hiện tại
        |
        v
Consumer đóng, partition bàn giao
~~~

Do đó, khi API quản trị phản hồi "stop requested", không nên hiển thị "stopped" nếu chưa có tín hiệu xác nhận trạng thái cuối.

Đặt trạng thái rõ ràng:

~~~text
RUNNING -> STOP_REQUESTED -> STOPPING -> STOPPED
                           |
                           +-- STOP_FAILED / RETRY_NEEDED
~~~

Thứ tự chuyển trạng thái cụ thể do coordinator và container lifecycle quyết định. Nếu ứng dụng còn có START_REQUESTED, phải xử lý cả việc request start trong khi STOPPING.

## 17. Offset commit và stop

Kafka commit offset biểu thị vị trí **tiếp theo** consumer group sẽ đọc. Với record ở offset 40, nếu xử lý thành công thì group thường commit offset 41.

~~~text
P0:
  offset 39 -> DONE
  offset 40 -> DONE
  offset 41 -> IN_FLIGHT
  offset 42 -> QUEUED

Offset an toàn nếu chỉ 39,40 hoàn tất:
  41
~~~

Nếu stop xảy ra trong khi offset 41 chưa hoàn thành, ứng dụng không được commit offset 43 chỉ vì records đã được fetch hoặc enqueue. Làm vậy có thể bỏ qua record chưa được xử lý.

Với listener đồng bộ, container và AckMode thường quản lý tiến độ rõ hơn. Với xử lý bất đồng bộ, phải bảo vệ các khoảng trống offset:

- Chỉ acknowledge record đã thực sự hoàn thành.
- Chỉ commit đến **last contiguous completed offset** của partition.
- Không coi task đã đưa vào queue là đã xử lý.
- Khi stop, có kế hoạch drain task có deadline hoặc để những records chưa commit được replay.
- Bảo vệ side effects bằng event ID/idempotency khi record được xử lý lại.

Stop coordinator không tự biết record nào đã thành công. Nó không thể thay thế offset management và nghiệp vụ.

## 18. Manual acknowledgment khi requestStop

Với AckMode.MANUAL hoặc MANUAL_IMMEDIATE, listener có thể nhận Acknowledgment và acknowledge sau khi xử lý:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        containerFactory = "manualAckFactory")
public void handle(
        OrderEvent event,
        Acknowledgment ack) {

    orderService.process(event);
    ack.acknowledge();

    if (maintenanceGate.shouldStopAfterCurrentRecord()) {
        stopCoordinator.requestStop("orders-listener");
    }
}
~~~

Ví dụ chỉ đúng nếu manualAckFactory đã cấu hình AckMode tương ứng. **acknowledge() không phải lời hứa rằng commit đã hoàn tất tại broker trong mọi mode và mọi thread**. Với MANUAL, commit có thể diễn ra sau đó; với MANUAL_IMMEDIATE, semantics khác và phụ thuộc thread thực hiện acknowledgment.

Ngay cả khi đã ack, process crash trước khi commit hoàn tất vẫn có thể làm record được giao lại. Thiết kế consumer phải chịu được at-least-once delivery và idempotency.

Đừng gọi ack cho record chưa xử lý chỉ vì sắp stop container.

## 19. Transactional listener: stop phải tôn trọng transaction boundary

Với Kafka consume-process-produce transaction, listener container mở Kafka transaction và đưa consumed offsets vào transaction cùng với output records.

~~~text
Kafka container BEGIN transaction T1
       |
       +-- consume orders.input/P1@50
       +-- produce orders.output
       |
       +-- listener hoàn tất
       |
       +-- sendOffsetsToTransaction(P1 -> 51)
       |
       v
COMMIT T1
~~~

Nếu listener ném exception, transaction có thể abort. Nếu stop/race/shutdown xảy ra trước khi commit hoàn tất, input record có thể được giao lại theo committed offset.

Không tự gọi consumer.commitSync() trong listener hoặc shutdown callback để "đánh dấu xong" khi đang dùng Kafka transaction. Offset cần được container/transaction manager phối hợp cùng output.

Ngoài ra, Kafka transaction **không rollback database hoặc HTTP side effect**. Nếu listener cập nhật DB rồi stop/crash trước Kafka commit, record có thể được xử lý lại. Dùng idempotency key, unique constraint hoặc outbox nếu cần đảm bảo nghiệp vụ.

Đối với transactional listener, nên để transaction boundary hoàn tất hoặc abort theo đường container hỗ trợ, thay vì tự đóng consumer trong callback nghiệp vụ.

## 20. Stop từ error handler: cần phân biệt loại lỗi

Một CommonErrorHandler có thể được gọi khi listener ném exception. Vì handler nằm trong processing path của container, đây không phải nơi an toàn để tự gọi container.stop() một cách tùy tiện.

Ví dụ anti-pattern:

~~~java
public void handleOne(
        Exception exception,
        ConsumerRecord<?, ?> record,
        Consumer<?, ?> consumer,
        MessageListenerContainer container) {

    container.stop(); // Không stop đồng bộ trên consumer thread.
}
~~~

Một số phiên bản Spring Kafka cung cấp error handler có sẵn cho mục đích dừng container khi gặp lỗi nghiêm trọng, ví dụ các API thuộc nhóm container-stopping error handlers. Khi đây là requirement rõ ràng, ưu tiên cơ chế Spring Kafka được thiết kế cho trường hợp đó và đọc semantics của phiên bản đang dùng.

Không nhầm:

- Lỗi nghiệp vụ tạm thời: retry/backoff rồi recovery.
- Lỗi dữ liệu không thể phục hồi: DLT hoặc non-retryable handling.
- Dependency quá tải: pause/backpressure hoặc circuit breaker.
- Lỗi hạ tầng nghiêm trọng cần dừng: stop container qua đường lifecycle an toàn.

Đặc biệt, việc error handler nuốt exception và return có thể khiến container coi record đã được xử lý theo một số cấu hình. Nếu record chưa recovery thành công, phải giữ đúng exception/ack/offset semantics để tránh mất dữ liệu.

## 21. Rebalance callback không phải nơi stop trực tiếp

Các callback onPartitionsRevoked/onPartitionsAssigned thường chạy trong quá trình poll và rebalance, nên cũng cần giữ ngắn.

~~~text
Consumer poll thread
      |
      v
onPartitionsRevoked(P1, P2)
      |
      +-- flush/checkpoint có giới hạn
      +-- release state của P1, P2
      |
      v
Trả quyền điều khiển cho Kafka rebalance
~~~

Nếu gọi stop trực tiếp ở đây, ứng dụng vừa đang bàn giao partitions vừa tự khởi động lifecycle stop, có thể tạo reentrancy và trì hoãn group coordination. Không dùng revoke callback làm nơi tắt toàn bộ listener do thấy assignment đổi.

Nếu chính sách nghiệp vụ thực sự yêu cầu dừng sau một biến cố rebalance, callback có thể ghi nhận tín hiệu rồi gửi yêu cầu qua lifecycle coordinator **sau khi rời consumer thread**. Nhưng phải cân nhắc rằng rebalance bình thường xảy ra khi deploy/scale và không có nghĩa consumer cần shutdown.

Khi partition đã lost, không cố commit offset như owner cũ chỉ để phục vụ shutdown.

## 22. Backpressure nên được điều khiển bằng tín hiệu nào?

Stop cả container thường là biện pháp khá mạnh. Với backpressure, nên thiết kế các ngưỡng rõ ràng:

| Tín hiệu | Phản ứng phù hợp |
|---|---|
| Worker queue vượt high watermark | Request pause |
| Worker queue xuống dưới low watermark | Request resume |
| Database pool gần cạn tạm thời | Pause, điều tiết concurrency/throughput |
| Downstream trả HTTP 429/503 ngắn hạn | Backoff, pause hoặc error handler tùy ordering |
| DLT publish thất bại và không thể recovery | Alert, đánh giá stop có kiểm soát |
| Cần bảo trì listener lâu dài | Stop qua lifecycle executor |
| Cần thay đổi subscriptions/configuration | Stop và restart theo deployment policy |

Không pause/resume liên tục mỗi khi queue dao động quanh một ngưỡng. Dùng **hysteresis**:

~~~text
Worker queue capacity = 1000

Queue >= 800 -> PAUSE
Queue <= 300 -> RESUME

300 < Queue < 800 -> giữ trạng thái hiện tại
~~~

Ngưỡng chỉ minh họa. Cần đặt theo throughput, latency, memory và khả năng xử lý tải của dependency.

Pause không làm xử lý nhanh hơn; nó giảm tốc độ đưa thêm work vào hệ thống. Nếu consumer có backlog lớn, Kafka lag sẽ tăng trong lúc pause và giảm dần khi resume.

## 23. Thực thi một controller pause có hysteresis

Một controller đơn giản có thể chạy từ scheduler hoặc thread giám sát, thay vì mỗi record tự quyết định stop:

~~~java
@Component
public class QueueBackpressureMonitor {

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMetrics queueMetrics;
    private boolean pauseRequested;

    @Scheduled(fixedDelay = 1_000L)
    public synchronized void check() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int depth = queueMetrics.pendingJobs();

        if (!pauseRequested && depth >= 800) {
            container.pause();
            pauseRequested = true;
        }
        else if (pauseRequested && depth <= 300) {
            container.resume();
            pauseRequested = false;
        }
    }
}
~~~

Ví dụ yêu cầu bật scheduling và có bean WorkQueueMetrics. Nếu nhiều code paths cũng có thể pause/resume cùng container, boolean cục bộ sẽ không đủ. Production cần **một nguồn trạng thái điều khiển chung**, phân biệt lý do pause (backpressure, maintenance, circuit breaker) để tránh một subsystem resume trong khi subsystem khác vẫn muốn pause.

Với hệ thống nhiều replicas, queue depth mỗi instance có thể khác nhau. Một monitor cục bộ chỉ điều tiết container tại instance của mình; không cần pause toàn cluster nếu chỉ một pod quá tải.

## 24. Rủi ro khi lifecycle executor bão hòa

Việc offload stop sang thread khác là cần thiết, nhưng chưa đủ nếu executor không được vận hành đúng.

Các tình huống:

- **Queue đầy**: requestStop bị từ chối và container tiếp tục chạy.
- **Một task stop kẹt**: thread lifecycle không còn khả năng xử lý các lệnh mới.
- **Nhiều request trùng**: hàng nghìn stop tasks cùng target một container.
- **App shutdown**: lifecycle executor có thể bị hủy trước khi xử lý hết yêu cầu.
- **Stop/start chạy song song**: container chuyển trạng thái không theo thứ tự mà operator mong muốn.

Các biện pháp:

1. Giữ executor riêng và có giới hạn.
2. Gộp request theo listener/container ID.
3. Ghi log khi task bị reject, có alert với lệnh quan trọng.
4. Theo dõi executor queue depth, task duration và rejected count.
5. Dùng coordinator có state machine nếu có cả stop và start.
6. Không thực hiện thao tác lifecycle vô hạn; dùng timeout/watchdog ở lớp điều phối.
7. Kiểm tra app shutdown ordering để lifecycle executor còn hoạt động trong giai đoạn stop cần thiết.

Không dùng CallerRunsPolicy để xử lý rejection của lifecycle executor nếu nó khiến **consumer thread tự chạy lại task stop**. Điều đó đưa nguyên nhân ban đầu quay trở lại.

## 25. Restart sau stop: không chỉ gọi resume()

Khi container chỉ bị pause, resume() có thể tiếp tục hoạt động trên assignment hiện tại. Nhưng sau khi stop, consumer đã dừng và có thể rời group.

~~~text
RUNNING
   |
   +-- pause() --> PAUSED
   |                 |
   |                 +-- resume() --> RUNNING
   |
   +-- stop()  --> STOPPING --> STOPPED
                                      |
                                      +-- start() --> RUNNING
~~~

Với container đã dừng, gọi resume() không thay thế cho start(). Khi start, KafkaConsumer mới có thể gia nhập group và nhận partition assignment mới. Chỉ sau khi start và assignment thành công mới nên xem consumer đã phục hồi.

Không start container ngay trong một event cho biết stop đang được yêu cầu. Hãy chờ completed stop hoặc lifecycle state ổn định. Nếu policy tự động restart, đặt backoff để tránh vòng stop–start–rebalance liên tục.

Trong hệ thống dùng KafkaListenerEndpointRegistry, có thể điều khiển start/stop theo **listener ID**, nhưng phải chọn đúng container quản lý bởi registry. Các container được tạo thủ công ngoài registry có thể cần quản lý bằng bean/reference riêng.

## 26. Graceful shutdown từ application lifecycle

Khi ứng dụng Spring Boot shutdown, framework có cơ chế lifecycle stop cho các managed beans/containers. Thông thường **không cần tự gọi stop() từ @KafkaListener khi nhận tín hiệu shutdown**.

Nếu có nhu cầu custom quiesce:

1. Ngừng nhận thêm request mới ở tầng ingress.
2. Pause Kafka listener nếu cần drain các tác vụ đang xử lý.
3. Chờ in-flight business work trong deadline.
4. Yêu cầu stop qua lifecycle manager/executor thích hợp.
5. Quan sát container thực sự stopped.
6. Hoàn tất cleanup ngoài Kafka và đóng resources.

Không giữ shutdown callback chờ vô hạn, vì Kubernetes termination grace period hoặc orchestrator timeout có thể hết. Process có thể bị kill mà không chạy cleanup; vì thế commit offset đúng và idempotency vẫn là cơ chế phòng vệ bắt buộc.

Một stop sạch không bảo đảm không có record bị giao lại. Nếu lần commit cuối chưa hoàn tất hoặc transaction abort, Kafka có thể replay records; đó là hành vi bình thường của at-least-once/transactional processing.

## 27. Quan sát lifecycle và ConsumerStoppedEvent

Spring Kafka có các application events liên quan consumer/container lifecycle. Có thể theo dõi **ConsumerStoppedEvent** để phân biệt stop bình thường với stop do lỗi.

~~~java
@EventListener
public void onConsumerStopped(ConsumerStoppedEvent event) {
    log.info(
            "Kafka consumer stopped: reason={}, source={}",
            event.getReason(),
            event.getSource());
}
~~~

Với concurrent container, các child consumers có thể phát events riêng. Cần đối chiếu listener/container ID để biết stop đã hoàn tất ở phạm vi nào; không chỉ thấy một ConsumerStoppedEvent rồi kết luận mọi child consumers đều stopped.

Log vận hành nên ghi:

~~~text
action=stop_requested
listenerId=orders-listener
requestSource=backpressure-controller
consumerThread=orders-listener-0-C-1
executionThread=kafka-lifecycle-1
stopReason=maintenance
transition=STOPPING
~~~

Đây là ví dụ log ứng dụng, không phải định dạng có sẵn của Spring Kafka. Nếu requestStop được gọi từ consumer thread, log cần giúp xác nhận thao tác stop thật sự diễn ra trên **thread khác**.

Khi dừng bất ngờ, phân biệt Reason.NORMAL với lỗi authentication, fencing, no offset hoặc lỗi lifecycle khác theo các reason được phiên bản Spring Kafka hỗ trợ. Không auto-restart mọi loại lỗi theo cùng một policy mà không phân tích nguyên nhân.

## 28. Monitoring cho pause/stop/backpressure

Các chỉ số hữu ích:

- Số listener containers RUNNING, PAUSED, STOPPING, STOPPED.
- Số pause/resume requests và thời gian pause thực tế.
- Số stop requests, stop completion và stop failures.
- Thời gian từ stop requested tới stopped.
- Lifecycle executor queue depth, rejection và task latency.
- Consumer lag theo topic/partition.
- Listener processing duration p95/p99 và số in-flight tasks.
- Số rebalance sau stop/start.
- Offset commit failures và transaction abort.
- Số lần start/stop liên tiếp trong một khoảng ngắn.

Metric nên phân biệt **desired state** và **observed state**. Ví dụ đã gửi pause request không có nghĩa container đã tạm ngừng hoàn toàn. Đã gửi stop request không có nghĩa thread đã đóng.

Không đưa offset, event ID hay full exception message làm metric labels có cardinality cao. Các chi tiết đó phù hợp với structured logs và traces.

## 29. Kiểm thử stop không chạy trên consumer thread

### Test 1: requestStop từ @KafkaListener

1. Khởi động Spring Kafka listener và gửi một record.
2. Cho listener xử lý thành công và gọi stopCoordinator.requestStop().
3. Ghi thread name ở listener và ngay trước container.stop() trong coordinator.
4. Xác nhận hai thread khác nhau.
5. Chờ container stopped bằng điều kiện có timeout.
6. Xác nhận không còn polling sau khi stop hoàn tất.

### Test 2: idle event

1. Cấu hình idle event interval đủ ngắn trong test.
2. Cho listener container không có record một khoảng thời gian.
3. Event handler chỉ gọi requestStop, không stop trực tiếp.
4. Xác nhận lifecycle executor nhận stop task.
5. Xác nhận container dừng mà consumer thread không tự chờ chính nó.

### Test 3: stop requested khi đang xử lý record

1. Listener nhận record và giữ một dependency call bằng cơ chế test.
2. Một thread khác requestStop.
3. Quan sát stop theo stopImmediate và AckMode của container.
4. Hoàn tất dependency call.
5. Xác nhận record được commit hoặc replay đúng theo semantics.
6. Xác nhận không có lost processing.

### Test 4: backpressure pause/resume

1. Tạo worker queue có depth vượt high watermark.
2. Xác nhận controller request pause.
3. Xác nhận consumer group vẫn giữ assignment và container tiếp tục poll theo thiết kế.
4. Giảm queue depth dưới low watermark.
5. Xác nhận resume và processing tiếp tục.
6. Xác nhận không có pause/resume flapping.

### Test 5: concurrent child containers

1. Tạo listener với concurrency lớn hơn 1.
2. Request stop theo parent listener ID.
3. Xác nhận các child containers dừng theo lifecycle.
4. Kiểm tra không có task stop trùng cho từng child.
5. Khởi động lại và xác nhận group nhận assignment hợp lệ.

### Test 6: lifecycle executor rejection

1. Dùng executor có queue nhỏ trong test.
2. Tạo tình huống TaskRejectedException khi requestStop.
3. Xác nhận coordinator log/alert failure.
4. Xác nhận không coi container đã stopped khi task không được nhận.
5. Xác nhận không rơi lại vào chạy stop() trên consumer thread.

### Test 7: crash trước offset commit

1. Listener hoàn tất business side effect nhưng chưa commit offset.
2. Dừng process hoặc gây transaction abort có kiểm soát.
3. Khởi động consumer mới.
4. Xác nhận record có thể được giao lại.
5. Xác nhận idempotency ngăn side effect lặp không mong muốn.

Integration tests nên dùng Kafka test broker như Testcontainers Kafka hoặc EmbeddedKafka để quan sát group assignment, consumer stop, commit/replay và pause/resume thực tế. Không chỉ mock KafkaListenerEndpointRegistry rồi kết luận lifecycle của Kafka consumer đã đúng.

## 30. Các hiểu nhầm thường gặp

**Gọi container.stop() trong @KafkaListener là an toàn vì đều thuộc Spring.** Không đúng. Listener thường chạy trên consumer thread và stop có thể tương tác với shutdown của chính thread đó.

**Đưa stop() vào @EventListener luôn làm nó chạy trên thread khác.** Không đúng. Spring application events có thể được dispatch đồng bộ trên thread phát sự kiện.

**stopImmediate=true làm stop() trên consumer thread an toàn.** Không đúng. Nó chỉ thay đổi thời điểm ngừng xử lý records theo semantics container.

**container.pause() giống container.stop().** Không đúng. Pause thường giữ membership và poll; stop đóng consumer và có thể gây rebalance.

**Đã gọi pause() tức không còn listener nào đang chạy.** Không đúng. Pause cần có hiệu lực và records đã poll có thể còn đang xử lý.

**Đã requestStop tức container đã dừng.** Không đúng. Phải quan sát completion/state cuối.

**Chỉ cần ExecutorService là đủ, không cần xử lý request trùng.** Không đúng. Nhiều callbacks có thể tạo nhiều stop tasks và race với start.

**CallerRunsPolicy là fallback an toàn cho lifecycle executor.** Không đúng trong trường hợp caller là consumer thread; nó có thể chạy stop() ngay trên thread cần tránh.

**Stop trước khi xử lý record rồi return là bảo đảm record sẽ được đọc lại.** Không đúng. Return bình thường có thể làm container đánh dấu xử lý thành công theo AckMode.

**Stop luôn bảo đảm tất cả records đã poll đều hoàn tất.** Không đúng. Kết quả phụ thuộc stopImmediate, listener model, acknowledgment và in-flight tasks.

**Pause một partition đồng nghĩa nhường partition đó cho consumer khác.** Không đúng. Pause thường vẫn giữ ownership.

**Kafka transaction sẽ rollback luôn database khi stop.** Không đúng. Side effects ngoài Kafka cần transaction/idempotency riêng.

**Restart container sau stop chỉ cần gọi resume().** Không đúng. Resume áp dụng cho paused container; stopped container cần start theo lifecycle.

## 31. Quy trình áp dụng trong production

Khi ứng dụng Spring Kafka cần điều tiết tải hoặc dừng listener:

1. Xác định mục tiêu là **tạm ngừng tiêu thụ** hay **dừng lifecycle**.
2. Ưu tiên pause/resume cho backpressure ngắn hạn, giữ consumer group membership.
3. Dùng high/low watermark và một controller thống nhất để tránh pause/resume liên tục.
4. Nếu cần stop, không gọi trực tiếp từ @KafkaListener, error handler, rebalance callback hoặc synchronous event handler.
5. Tạo lifecycle executor riêng và coordinator nhận requestStop theo listener ID.
6. Giới hạn concurrent stop requests và xử lý TaskRejectedException.
7. Xác định stop parent hay child container khi concurrency lớn hơn 1.
8. Gọi stop từ lifecycle thread khác consumer thread, quan sát kết quả stopped.
9. Không acknowledge records chưa xử lý chỉ để việc stop nhanh hơn.
10. Với transactional listener, để container quyết định Kafka offset commit/abort trong transaction.
11. Với async processing, quản lý in-flight tasks, contiguous completed offsets và deadline drain.
12. Có idempotency cho record có thể được replay sau stop/restart.
13. Thiết kế restart policy có trạng thái và backoff, tránh vòng stop/start/rebalance.
14. Theo dõi pause duration, stop duration, lag, rebalance và commit failures.
15. Kiểm thử cả stop từ listener, idle event, executor rejection, crash và concurrent containers.

**Không gọi stop trên consumer thread** là nguyên tắc bảo vệ vòng đời Spring Kafka listener container. Consumer thread nên hoàn tất callback và trả quyền điều khiển về poll loop, còn lệnh stop được thực hiện bởi một lifecycle coordinator trên thread khác. Khi vấn đề chỉ là backpressure tạm thời, **pause/resume thường phù hợp hơn stop/start** vì không cần đóng consumer và gây rebalance. Dù chọn cách nào, vẫn phải bảo đảm offset/acknowledgment phản ánh records đã xử lý thật, tránh commit quá sớm và chuẩn bị cho khả năng record được giao lại khi dừng hoặc khởi động lại.
