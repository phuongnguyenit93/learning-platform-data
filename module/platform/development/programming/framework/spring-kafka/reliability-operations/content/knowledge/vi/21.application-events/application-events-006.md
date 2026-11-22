# ConsumerStoppingEvent

Trong Spring Kafka, một consumer không chỉ có trạng thái **đang chạy** hoặc **đã dừng**. Listener container còn trải qua nhiều bước trong vòng đời: khởi tạo consumer thread, tham gia consumer group, poll record, xử lý record, nhận yêu cầu dừng và cuối cùng đóng `KafkaConsumer`. Spring Kafka phát các **application events** để ứng dụng có thể quan sát những chuyển tiếp quan trọng này.

**`ConsumerStoppingEvent`** là event được phát bởi consumer thread **ngay trước khi consumer ngừng hoạt động và được đóng**. Đây là thời điểm thích hợp để ghi nhận việc consumer chuẩn bị kết thúc và dọn dẹp một số tài nguyên gắn với chính thread tiêu thụ. Event này đặc biệt hữu ích khi ứng dụng dùng `ThreadLocal`, thread-bound context hoặc tài nguyên do consumer thread sở hữu.

Tuy nhiên, `ConsumerStoppingEvent` **không phải** lời hứa rằng mọi side effect đã hoàn tất, offset đã commit thành công, hoặc consumer group không còn rebalance. Nó cũng không phải hook để tự gọi `consumer.close()` lần thứ hai. Muốn vận hành tin cậy, phải phân biệt rõ event này với `ConsumerStoppedEvent`, `ContainerStoppedEvent` và các callback khi partition bị revoke.

## 1. Vị trí trong vòng đời của Kafka listener container

Một luồng xử lý đơn giản có thể mô tả như sau:

```text
Spring application khởi động
          |
          v
Kafka listener container start
          |
          v
Consumer thread khởi tạo
          |
          v
ConsumerStartingEvent / ConsumerStartedEvent
          |
          v
poll() -> @KafkaListener -> commit/retry/recovery
          |
          v
Nhận yêu cầu stop hoặc đi vào nhánh kết thúc consumer
          |
          v
ConsumerStoppingEvent
          |
          v
Đóng KafkaConsumer, kết thúc consumer thread
          |
          v
ConsumerStoppedEvent
          |
          v
ContainerStoppedEvent (khi container kết thúc)
```

Sơ đồ thể hiện **quan hệ chức năng**, không phải bảo đảm về mọi chi tiết thứ tự callback trong mọi phiên bản và mọi loại container. Ví dụ `ConcurrentMessageListenerContainer` chứa các child containers; mỗi child có consumer thread và lifecycle riêng. Một lần dừng container cha có thể dẫn tới nhiều `ConsumerStoppingEvent` và `ConsumerStoppedEvent`.

Điểm quan trọng là `ConsumerStoppingEvent` xảy ra **trước khi consumer đóng hoàn toàn**. Nếu chỉ lắng nghe `ConsumerStoppedEvent`, tài nguyên của consumer đã ở trạng thái khác. Nếu chỉ lắng nghe `ContainerStoppedEvent`, ứng dụng chỉ thấy trạng thái ở mức container sau khi các consumer liên quan hoàn tất.

## 2. Event nào cần dùng cho nhiệm vụ nào?

| Event hoặc callback | Thời điểm/ngữ cảnh | Mục đích phù hợp |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread bắt đầu khởi tạo | Quan sát thời điểm tạo consumer và khởi động |
| `ConsumerStartedEvent` | Consumer bắt đầu hoạt động/poll | Ghi dấu đã khởi động, khởi tạo quan sát per-thread nếu phù hợp |
| `ConsumerStoppingEvent` | Consumer thread chuẩn bị kết thúc, trước khi đóng consumer | Dọn thread-bound resources, ghi lifecycle log/metric |
| `ConsumerStoppedEvent` | Consumer đã dừng | Ghi nhận kết quả dừng và lý do dừng nếu event/version hỗ trợ |
| `ContainerStoppedEvent` | Listener container đã dừng | Quan sát trạng thái tổng thể của container |
| `ListenerContainerIdleEvent` | Container không nhận record trong khoảng idle được cấu hình | Phát hiện luồng tạm rảnh, không có nghĩa consumer đang stop |
| `ConsumerAwareRebalanceListener` | Partition revoke/assign trong rebalance | Quản lý trạng thái theo partition và ownership |

Một consumer đang *idle* vẫn có thể poll và giữ membership. Một consumer bị *pause* vẫn có thể tiếp tục poll để duy trì group. Một consumer trải qua *rebalance* có thể mất một số partition nhưng tiếp tục sống và poll trên partition khác. Những sự kiện đó **không tương đương** việc consumer thread thực sự đang kết thúc.

Vì vậy, không dùng `ConsumerStoppingEvent` như giải pháp duy nhất để theo dõi partition revoke hoặc phát hiện ứng dụng thiếu record. Mỗi mốc lifecycle cần đúng công cụ quan sát.

## 3. Đăng ký listener bằng `@EventListener`

Spring phát `ConsumerStoppingEvent` qua application event infrastructure. Một Spring bean có thể nhận event bằng annotation `@EventListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log = LoggerFactory.getLogger(
            KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onConsumerStopping(ConsumerStoppingEvent event) {
        log.info(
                "Kafka consumer stopping: source={}, thread={}",
                event.getSource(),
                Thread.currentThread().getName());
    }
}
```

Code minh họa nhận event rồi ghi log ngắn. `getSource()` mô tả đối tượng phát event theo Spring application events; trong một topology nhiều container, nó không nhất thiết là tên `@KafkaListener` mà người vận hành nhìn thấy trong source code. Khi cần ánh xạ về listener ID/group ID, hãy xây cơ chế định danh container rõ ràng và kiểm tra giá trị được cung cấp bởi phiên bản đang dùng.

`@EventListener` hoạt động với Spring context có event multicaster phù hợp, không yêu cầu gọi thủ công từ listener. Nếu bean không nằm trong component scan hoặc event được phát ở application context khác, phương thức sẽ không được gọi.

### Dùng `ApplicationListener` khi cần kiểu tường minh

Một cách tương đương là triển khai interface:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStopObserver
        implements ApplicationListener<ConsumerStoppingEvent> {

    @Override
    public void onApplicationEvent(ConsumerStoppingEvent event) {
        // Ghi nhận event hoặc dọn tài nguyên gắn với consumer thread.
    }
}
```

Thông thường chỉ cần **một trong hai cách** cho cùng chức năng. Không nên đăng ký cả hai rồi thực hiện cleanup hai lần nếu logic không idempotent.

## 4. Lưu ý quan trọng nhất: event được phát từ consumer thread

Theo cơ chế mặc định của Spring application event multicaster, listener nhận event được gọi **đồng bộ trên thread phát event**. Với `ConsumerStoppingEvent`, thread phát event là consumer thread mà container đang chuẩn bị kết thúc.

Điều này có hai hệ quả quan trọng:

1. Có thể dọn những `ThreadLocal` đã được thiết lập trên **cùng consumer thread** vì callback đang chạy trên thread sở hữu dữ liệu đó.
2. Callback quá chậm hoặc bị chặn sẽ kéo dài quá trình dừng consumer. Nó có thể làm shutdown kéo dài, gây timeout hoặc làm khó việc kết thúc container.

Nếu ứng dụng cấu hình `ApplicationEventMulticaster` chạy với `TaskExecutor` bất đồng bộ, hoặc đánh dấu method nhận event bằng `@Async`, event listener có thể chạy trên **thread khác**. Khi đó, `ThreadLocal.remove()` chỉ dọn giá trị của thread event listener, **không dọn ThreadLocal của consumer thread**.

```text
Mặc định đồng bộ:

Consumer thread ---- publish ConsumerStoppingEvent
       |                       |
       |                       v
       +---- @EventListener chạy cùng thread
                               |
                               v
                      ThreadLocal.remove() đúng thread

Multicaster bất đồng bộ:

Consumer thread ---- publish event ---> Executor thread
                                           |
                                           v
                                  ThreadLocal.remove()
                                  chỉ trên executor thread
```

**Quy tắc:** nếu cleanup đòi hỏi thread affinity, hãy dùng event listener đồng bộ. Không truy cập trực tiếp `KafkaConsumer` được đính kèm trong event từ một async event handler vì `KafkaConsumer` không thread-safe.

## 5. Ví dụ dọn `ThreadLocal` khi consumer dừng

Một ứng dụng có thể tạo cache, formatter state hoặc một ngữ cảnh xử lý riêng cho mỗi consumer thread để tránh tạo lại đối tượng ở mỗi record. Nếu không giải phóng đúng lúc, tài nguyên có thể còn tham chiếu tới object lớn hoặc giữ connection sau khi consumer đã dừng.

Ví dụ một `ThreadLocal` chứa một đối tượng ứng dụng có tài nguyên cần đóng:

```java
import org.springframework.stereotype.Component;

@Component
public class ConsumerThreadResources {

    private final ThreadLocal<ConsumerSession> current = new ThreadLocal<>();

    public ConsumerSession getOrCreate() {
        ConsumerSession session = current.get();
        if (session == null) {
            session = new ConsumerSession(); // class do ứng dụng định nghĩa
            current.set(session);
        }
        return session;
    }

    public void cleanupCurrentThread() {
        ConsumerSession session = current.get();
        current.remove();

        if (session != null) {
            session.close();
        }
    }
}
```

Giả định `ConsumerSession` là class của ứng dụng có method `close()` và được thiết kế riêng cho thread đang xử lý. Nó **không phải** chính `org.apache.kafka.clients.consumer.Consumer` hoặc một Kafka producer dùng chung. Listener nghiệp vụ có thể sử dụng cùng bean `ConsumerThreadResources`:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service")
public void onOrder(OrderEvent event) {
    ConsumerSession session = threadResources.getOrCreate();
    orderService.handleIdempotently(event, session);
}
```

Tại thời điểm consumer kết thúc, dọn state qua event listener:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerThreadCleanup {

    private static final Logger log = LoggerFactory.getLogger(
            ConsumerThreadCleanup.class);

    private final ConsumerThreadResources resources;

    public ConsumerThreadCleanup(ConsumerThreadResources resources) {
        this.resources = resources;
    }

    @EventListener
    public void onStopping(ConsumerStoppingEvent event) {
        try {
            resources.cleanupCurrentThread();
        }
        catch (RuntimeException ex) {
            log.warn("Could not clean consumer thread resource", ex);
        }
    }
}
```

Để ví dụ hoạt động đúng, `ConsumerThreadResources` phải là bean được chia sẻ giữa listener nghiệp vụ và cleanup listener; **application event dispatch phải đồng bộ**; `ConsumerSession.close()` phải xử lý được tình huống gọi lặp hoặc tài nguyên đã được đóng sớm. Nếu `close()` ném checked exception, cần xử lý hoặc khai báo cụ thể trong class tương ứng.

`ThreadLocal.remove()` thực hiện trước khi đóng tài nguyên để giảm nguy cơ state cũ còn được giữ nếu thao tác đóng thất bại. Nếu tài nguyên cần release theo thứ tự khác, hãy định nghĩa trình tự phù hợp và giám sát lỗi cleanup.

## 6. Tài nguyên nào phù hợp để dọn ở đây?

`ConsumerStoppingEvent` phù hợp nhất cho tài nguyên sống **theo vòng đời consumer thread**, không phải một thao tác nghiệp vụ cần quyết định commit hay rollback.

| Tài nguyên | Có nên xử lý ở event này? | Lý do |
|---|---|---|
| `ThreadLocal` context/cache | Có, nếu tạo trên consumer thread | Cần dọn trên đúng thread để tránh rò rỉ tham chiếu |
| Thread-bound formatter/session do ứng dụng tự quản lý | Có, nếu có `close()` phù hợp | Có cùng lifetime với consumer thread |
| Metric/gauge theo thread/container | Có thể ghi nhận trạng thái dừng | Hữu ích để tránh báo consumer sống khi đã kết thúc |
| KafkaConsumer do container quản lý | **Không tự đóng** | Container chịu trách nhiệm lifecycle của nó |
| Consumer offset chưa commit | **Không chọn event này làm nơi commit chính** | Không đủ bảo đảm transaction/assignment/ack state |
| Database transaction của một record | Không nên dồn đến khi consumer dừng | Cần hoàn tất trong ranh giới xử lý record hoặc unit of work |
| HTTP request đang chạy | Không nên chờ vô hạn trong callback | Cleanup chặn sẽ kéo dài shutdown |
| Shared connection pool của cả ứng dụng | Thường không | Nhiều consumer có thể dùng chung; đóng một lần khi một consumer dừng làm hỏng consumer khác |

Nếu một resource chỉ có tuổi đời **một record**, tốt hơn nên dùng `try/finally`, `try-with-resources` hoặc transaction boundary ngay trong business method. Đợi đến `ConsumerStoppingEvent` mới đóng resource per-record có thể khiến hàng nghìn resource tích lũy trong thời gian consumer chạy lâu.

## 7. Có thể dùng `event.getConsumer()` để làm gì?

`ConsumerStoppingEvent` cung cấp tham chiếu tới Kafka consumer đang kết thúc ở các phiên bản Spring Kafka hỗ trợ thuộc tính này. Đây là chi tiết hữu ích để quan sát hoặc áp dụng cleanup đặc thù, nhưng cần hết sức thận trọng.

```java
@EventListener
public void onConsumerStopping(ConsumerStoppingEvent event) {
    Consumer<?, ?> consumer = event.getConsumer();
    // Chỉ dùng nếu thực sự cần quan sát consumer trong cùng thread.
    // Không gọi consumer.close(), subscribe(), poll() hoặc commitSync().
}
```

**Không sử dụng tham chiếu này để điều khiển lại vòng đời consumer.** Container đang thực hiện shutdown và chịu trách nhiệm đóng consumer, xử lý commit/offset và giải phóng tài nguyên. Gọi `close()` chủ động, `poll()`, `seek()` hoặc thao tác commit từ callback có thể xung đột với lifecycle hoặc tạo ra trạng thái khó kiểm soát.

Không giữ `Consumer` trong static field, cache, queue hoặc gửi nó tới executor khác. Sau khi event kết thúc, consumer có thể đã được đóng; giữ lại tham chiếu không làm nó trở thành API an toàn để tái sử dụng.

Thông tin `assignment()` hoặc group metadata lấy ở thời điểm stopping cũng chỉ là **snapshot**. Partition có thể đã bị revoke hoặc đang trong quá trình thu hồi. Nếu cần quản lý chính xác ownership per partition, hãy dùng callback rebalance thay vì coi snapshot lúc stop là nguồn chân lý.

## 8. Phân biệt stopping consumer và stopping container

Một listener container có thể quản lý một consumer hoặc nhiều consumer. Với `ConcurrentKafkaListenerContainerFactory`, cấu hình `concurrency` thường tạo nhiều consumer child containers để xử lý các partition song song.

```text
ConcurrentMessageListenerContainer: ordersListener
             |
       +-----+-----+
       |     |     |
     Child A Child B Child C
       |     |     |
     Kafka   Kafka  Kafka
     consumer consumer consumer

Yêu cầu stop container cha
       |
       +--> ConsumerStoppingEvent của A
       +--> ConsumerStoppingEvent của B
       +--> ConsumerStoppingEvent của C
       |
       +--> các ConsumerStoppedEvent
       |
       +--> ContainerStoppedEvent khi kết thúc tổng thể
```

Event của mỗi child có thể xuất hiện ở thời điểm khác nhau vì một child đang xử lý record lâu hơn hoặc gặp lỗi khi shutdown. Vì vậy, **một `ConsumerStoppingEvent` không có nghĩa toàn bộ listener container đã dừng**.

Khi tính metric số consumer đang hoạt động, cần dùng định danh child/container hoặc thread phù hợp để tránh trừ nhầm một lần stop cho cả group. `concurrency=3` cũng không bảo đảm luôn có đúng ba partition đang xử lý: số partition thực sự và assignment còn phụ thuộc topic và consumer group.

Nếu cần thực hiện một bước *duy nhất sau khi toàn bộ container dừng*, `ContainerStoppedEvent` hoặc callback điều phối ở mức container thường là lựa chọn đúng hơn. Dùng `ConsumerStoppingEvent` cho cleanup riêng của từng consumer thread.

## 9. Những nguyên nhân nào khiến event được phát?

`ConsumerStoppingEvent` gắn với **consumer thực sự kết thúc**, không giới hạn ở một thao tác stop do người vận hành bấm nút. Một consumer có thể kết thúc khi:

- Ứng dụng Spring context đang shutdown bình thường.
- Listener container được stop qua API quản trị hoặc `KafkaListenerEndpointRegistry`.
- Container dừng theo cấu hình/lifecycle hoặc vì một lỗi nghiêm trọng cần kết thúc consumer thread.
- Ứng dụng thay đổi lifecycle khiến container dừng rồi khởi động lại, tạo consumer thread mới.

Không suy luận nguyên nhân cụ thể chỉ từ việc nhận `ConsumerStoppingEvent`. Nếu muốn biết consumer dừng bình thường, do fencing, do lỗi hay do một điều kiện đặc biệt, cần kết hợp `ConsumerStoppedEvent`, các thuộc tính reason của phiên bản framework, exception log và sự kiện container tương ứng.

Ngược lại, những tình huống sau **không bắt buộc** phát `ConsumerStoppingEvent`:

- Consumer group rebalance nhưng consumer thread vẫn tiếp tục chạy.
- Container tạm pause do downstream quá tải rồi resume.
- Listener tạm idle vì topic chưa có record.
- Một lần retry record do `DefaultErrorHandler` mà consumer không kết thúc.

Nếu JVM bị kill cưỡng bức hoặc host mất điện, application event không có cơ hội chạy. Không xây hệ thống bắt buộc phải nhận event này để phát hiện lỗi hoặc giải phóng tài nguyên **ở một hệ thống khác**; dùng lease, timeout, heartbeat và idempotency theo kiến trúc phù hợp.

## 10. Rebalance revoke là một sự kiện khác

Một ứng dụng có thể cần dọn state khi partition `orders-2` chuyển sang consumer khác trong khi consumer thread cũ vẫn chạy và tiếp tục sở hữu `orders-0`.

```text
Consumer A đang sở hữu orders-0, orders-2
                 |
                 v
             Rebalance
                 |
                 +--> orders-2 bị revoke
                 |
                 +--> Consumer A vẫn chạy orders-0

ConsumerStoppingEvent KHÔNG phải hook thay thế revoke callback
```

Để dọn tài nguyên hoặc checkpoint **theo partition**, nên dùng `ConsumerAwareRebalanceListener` hoặc cơ chế callback assignment/revocation tương ứng:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStateStore.release(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStateStore.initialize(partitions);
    }
});
```

`partitionStateStore` là đối tượng ứng dụng tự định nghĩa. Cần đảm bảo callback không làm I/O chặn quá lâu; các API và thứ tự callback cần kiểm tra theo phiên bản Spring Kafka đang dùng. Cleanup theo partition phải tính đến nguy cơ redelivery nếu side effect đã hoàn tất nhưng offset chưa commit.

`ConsumerStoppingEvent` có thể dọn **phần thread state còn lại** khi toàn consumer kết thúc; nó không thay thế việc dọn một partition vừa bị revoke trong lúc consumer vẫn hoạt động.

## 11. Event và offset commit: điều gì không được suy luận?

Trong một listener Kafka, business method có thể ghi database thành công nhưng consumer mất assignment trước khi commit offset. Khi đó record chưa commit có thể được giao lại. `ConsumerStoppingEvent` không cung cấp một ranh giới transaction mới để làm tất cả side effect trở thành atomic.

Ví dụ:

```text
poll record offset 500
       |
       v
Database UPDATE thành công
       |
       v
Container bắt đầu stop / consumer mất assignment
       |
       v
ConsumerStoppingEvent được phát
       |
       v
Offset chưa được commit theo kỳ vọng
       |
       v
Consumer mới có thể đọc lại offset 500
```

Đừng đặt `consumer.commitSync()` vào event listener chỉ để “dọn offset còn lại”. Bạn cần biết offset nào đã xử lý thành công, transaction nào đã commit, partition có còn được sở hữu không và container có đang quản lý offset/transaction hay không. Một commit tùy ý trong shutdown callback có thể bỏ qua record chưa hoàn tất hoặc gây xung đột với commit của container.

Giải pháp là thiết kế acknowledgement đúng trong listener, dùng idempotency/inbox cho side effect ngoài Kafka và để Spring Kafka xử lý commit/recovery theo container configuration. Khi cần transactional consume-transform-produce Kafka→Kafka, hãy dùng Kafka transaction và offset commit cùng giao dịch thay vì cố hoàn tất bằng application event.

## 12. Không để cleanup làm treo quá trình shutdown

Shutdown là một giai đoạn nhạy cảm: consumer phải giải phóng kết nối và group membership, ứng dụng có thể đang nhận tín hiệu termination từ orchestration, và pod/service có deadline để kết thúc.

Trong `ConsumerStoppingEvent` listener, nên:

1. Ghi log ngắn, không flood log bằng dump toàn bộ assignment/payload.
2. Dọn `ThreadLocal` và tài nguyên thread-bound bằng thao tác ngắn, có timeout hoặc fallback nếu cần.
3. Bắt và ghi nhận lỗi cleanup để tránh che khuất nguyên nhân stop chính.
4. Tránh gọi API chặn dài, sleep, join thread hoặc chờ external service không có timeout.
5. Không gọi `container.stop()`/`start()` lại từ callback của consumer đang stop.
6. Không đóng shared pool, bean singleton hoặc global executor khi vẫn còn các consumer khác dùng nó.

Một `@EventListener` đồng bộ chạy trên consumer thread có thể giữ luồng đó cho đến khi callback trả về. Nếu cleanup HTTP call chờ 60 giây trong khi ứng dụng chỉ có 30 giây graceful shutdown, tiến trình có thể bị kill trước khi container đóng xong.

Nếu bắt buộc thực hiện công việc cleanup chậm và không cần thread affinity, hãy thiết kế nó thành **một tác vụ ở lifecycle tổng thể** (hoặc workflow bên ngoài) với deadline và cơ chế phục hồi riêng. Đừng vô tình biến per-consumer stopping callback thành một công việc doanh nghiệp quan trọng phải hoàn tất trước khi ứng dụng được phép dừng.

## 13. Tác động của custom `ApplicationEventMulticaster`

Spring có thể cấu hình `ApplicationEventMulticaster` dùng executor để dispatch events. Việc này có thể cải thiện tính độc lập giữa publisher và observer, nhưng thay đổi mạnh ý nghĩa của `ConsumerStoppingEvent` cho cleanup.

| Cách dispatch | `Thread.currentThread()` ở listener | Dọn `ThreadLocal` của consumer? | Truy cập live `KafkaConsumer`? |
|---|---|---|---|
| Mặc định đồng bộ | Consumer thread phát event | Có, nếu cùng ThreadLocal holder | Chỉ trong cùng thread và rất thận trọng |
| Multicaster dùng executor | Executor thread khác | Không, vì khác thread | Không an toàn; consumer có thể đang đóng |
| Method có `@Async` | Async executor thread | Không | Không nên dùng tham chiếu Consumer |

Do đó, khi một hệ thống tùy biến application event handling, phải kiểm tra **thread thật** trong một kiểm thử tích hợp. Nếu chỉ cần đếm số event stop hoặc gửi một telemetry record không dùng consumer/thread-local state, bất đồng bộ có thể phù hợp hơn, nhưng cần tính việc event không được bảo đảm hoàn tất trước khi JVM dừng.

Một lựa chọn thiết kế là tách hai observer: observer đồng bộ chỉ làm cleanup bắt buộc trên consumer thread; hệ thống metrics/logging nhận thông tin bất biến (container ID, thời gian, trạng thái) để xử lý riêng. Không chuyển nguyên `Consumer` object sang executor.

## 14. Quan sát event trong hệ thống nhiều consumer

Ở production, ứng dụng có thể có nhiều nhóm listener cho các topic, nhiều child consumers và nhiều replica. Nếu mỗi consumer đều gửi một event stopping, cần đặt metric/log sao cho phân biệt được ngữ cảnh.

Các thuộc tính hữu ích:

| Thuộc tính | Vai trò vận hành |
|---|---|
| Application/service name | Biết service nào đang dừng consumer |
| Instance/pod ID | Phân biệt các replica đang deploy hoặc restart |
| Listener/container ID | Phân biệt các luồng nghiệp vụ trong cùng JVM |
| Consumer group | Liên hệ với Kafka group membership và lag |
| Thread name | Gợi ý child consumer thread nào phát event |
| Event type và timestamp | Dựng lại chuỗi lifecycle stopping/stopped |
| Reason ở `ConsumerStoppedEvent` | Phân biệt kết thúc bình thường với một số nhánh lỗi, nếu version cung cấp |

Không nên dùng event ID, topic-partition-offset của từng record làm metric label của lifecycle event. Lifecycle events là sự kiện **của consumer**, không phải của từng message. Dùng metric với nhãn có cardinality giới hạn; định danh chi tiết có thể đưa vào log.

Ví dụ một chuỗi log mong muốn khi triển khai rolling deployment:

```text
2026-... listener=ordersListener child=0 event=ConsumerStoppingEvent
2026-... listener=ordersListener child=0 event=ConsumerStoppedEvent
2026-... listener=ordersListener event=ContainerStoppedEvent
2026-... instance=new-pod listener=ordersListener event=ConsumerStartedEvent
```

Đây là ví dụ định dạng structured log do ứng dụng tự định nghĩa, không phải format mặc định của Spring Kafka. Thứ tự log giữa nhiều child containers khác nhau có thể đan xen do chạy ở các thread độc lập.

## 15. Những hiểu nhầm và lỗi triển khai phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy `ConsumerStoppingEvent` khi rebalance | Rebalance revoke partition nhưng consumer thread không stop | Lắng nghe `ConsumerAwareRebalanceListener` cho revoke/assign |
| `ThreadLocal` chưa được dọn | Event multicaster hoặc `@Async` chạy callback trên thread khác | Dùng listener đồng bộ trên consumer thread và chung holder ThreadLocal |
| Stop container rất chậm | Callback cleanup gọi HTTP/DB hoặc chờ lock dài | Rút ngắn cleanup, đặt timeout và không chặn shutdown |
| Một lần stop phát nhiều event | Container có `concurrency` lớn, mỗi child consumer phát event | Đếm theo consumer child, không theo toàn application |
| Thấy event nhưng offset vẫn redeliver sau restart | Event không đảm bảo commit offset | Thiết kế ack/transaction đúng và side effect idempotent |
| Log dừng bình thường bị báo như lỗi | Đồng nhất stopping với failure | Kết hợp `ConsumerStoppedEvent` reason, exception logs và deployment events |
| Event listener cleanup đóng shared pool | Nhầm resource thread-scoped với singleton application-wide | Quản lý shared pool ở Spring bean lifecycle, không ở consumer stop |
| Event listener gây lỗi khiến shutdown khó điều tra | Cleanup ném exception không được quản lý | Bắt/log lỗi cleanup, bảo đảm cleanup idempotent |
| Consumer reference bị dùng sau stop | Lưu `event.getConsumer()` cho async executor | Không giữ/điều khiển KafkaConsumer ngoài consumer thread |
| Không thấy event khi pod bị kill -9 | Không có graceful shutdown | Thiết kế recovery ngoài event, dùng timeout/lease và idempotency |

## 16. Kiểm thử `ConsumerStoppingEvent`

Để chứng minh listener cleanup hoạt động, có thể dùng môi trường kiểm thử Spring Boot với `@KafkaListener`, `KafkaListenerEndpointRegistry`, Kafka broker kiểm thử và một `CountDownLatch` ghi nhận event. Test không nên phụ thuộc chỉ vào `Thread.sleep()` vì shutdown và polling phụ thuộc scheduler.

Một event probe minh họa:

```java
@Component
public class ConsumerStoppingProbe {

    private final CountDownLatch stopping = new CountDownLatch(1);
    private final AtomicReference<String> stoppingThread =
            new AtomicReference<>();

    @EventListener
    public void record(ConsumerStoppingEvent event) {
        stoppingThread.set(Thread.currentThread().getName());
        stopping.countDown();
    }

    public boolean awaitStop(Duration timeout) throws InterruptedException {
        return stopping.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public String stoppingThread() {
        return stoppingThread.get();
    }
}
```

Trong integration test, lấy container theo listener ID rồi yêu cầu stop:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

assertNotNull(container);
container.stop();

assertTrue(stoppingProbe.awaitStop(Duration.ofSeconds(10)));
```

Các assertion trên là cấu trúc minh họa; test cần bảo đảm listener đã start trước khi gọi stop, chạy với Spring context đúng, và chọn probe chỉ theo consumer/container đang kiểm thử. Với concurrency lớn, latch đếm một event là **chưa đủ** để xác nhận mọi child consumer đã dừng. Có thể đếm nhiều event theo số child consumer thực sự khởi tạo và kết hợp `ContainerStoppedEvent`.

Những kịch bản cần thử:

1. **Stop bình thường:** có `ConsumerStoppingEvent` và tài nguyên thread-bound được dọn.
2. **Stop container nhiều child:** mỗi child phát event theo lifecycle của nó; cleanup không đóng nhầm tài nguyên của child khác.
3. **Event multicaster async:** chứng minh cleanup ThreadLocal không còn cùng thread, để bảo vệ kiến trúc khỏi cấu hình sai.
4. **Rebalance không stop:** revoke partition không bị nhầm với `ConsumerStoppingEvent`.
5. **Pause/resume:** không tạo sự kiện stopping khi chỉ tạm dừng fetch record.
6. **Cleanup ném exception:** logic vẫn ghi log được nguyên nhân, không tự thực hiện commit/seek trái phép.
7. **Restart listener:** context thread cũ được giải phóng; consumer mới không thừa hưởng state cũ.
8. **Graceful shutdown:** tổng thời gian cleanup nằm trong shutdown budget thực tế.

Với tài nguyên thread-bound, hãy kiểm tra trạng thái sau cleanup thông qua instrumentation của holder hoặc việc resource thực sự đã đóng; chỉ nhận được event không đủ để chứng minh cleanup đã chạy đúng thread.

## 17. Runbook khi consumer liên tục stopping/restarting

Nếu thấy nhiều `ConsumerStoppingEvent` trong một khoảng ngắn, đừng chỉ đặt cảnh báo về event count. Cần tìm **vì sao consumer đang kết thúc**.

Quy trình gợi ý:

1. **Xác định phạm vi:** service, instance, listener/container ID, consumer group và các child đang phát event.
2. **Ghép chuỗi lifecycle:** tìm `ConsumerStartingEvent`, `ConsumerStartedEvent`, `ConsumerStoppingEvent`, `ConsumerStoppedEvent`, `ContainerStoppedEvent` và log startup/shutdown.
3. **Phân biệt deploy với lỗi:** kiểm tra rolling update, autoscaling, health check restart và cấu hình stop/start.
4. **Đọc reason/exception:** xem `ConsumerStoppedEvent` và log nguyên nhân thực tế, đặc biệt authentication, authorization, fencing hoặc lỗi runtime nếu có.
5. **Đối chiếu rebalance:** xem consumer group assignment, revoke/assign và poll interval để tránh nhầm stop với rebalance bình thường.
6. **Kiểm tra callback cleanup:** thời gian thực thi, exception, thread affinity và tài nguyên đã được giải phóng.
7. **Đánh giá dữ liệu:** xem committed offset, redelivery, consumer lag và downstream idempotency sau restart.
8. **Khắc phục:** sửa lỗi cấu hình/tài nguyên, không chữa triệu chứng bằng cách tắt lifecycle logging hoặc reset offsets tùy tiện.

Trong rolling deployment, một lượng `ConsumerStoppingEvent` tương ứng các consumer child của pod cũ là bình thường. Cảnh báo nên dựa vào **tần suất bất thường**, stop reason, lag và tỷ lệ restart, thay vì coi mọi event stopping là sự cố.

## 18. Nguyên tắc thiết kế production

Khi sử dụng `ConsumerStoppingEvent` trong Spring Kafka, hãy giữ các nguyên tắc:

1. Hiểu event này là tín hiệu **consumer thread sắp dừng**, không phải tín hiệu toàn bộ consumer group hay application đã dừng.
2. Dùng nó cho cleanup thread-scoped resources và quan sát lifecycle; không dồn business commit/transaction vào stopping callback.
3. Giữ event listener **đồng bộ** nếu cần thao tác trên `ThreadLocal` của consumer thread.
4. Không gọi `poll()`, `commitSync()`, `seek()` hoặc `close()` trên `KafkaConsumer` khi container đã quản lý lifecycle.
5. Với `concurrency > 1`, chấp nhận nhiều event stopping độc lập theo child consumer.
6. Dùng `ConsumerAwareRebalanceListener` cho partition revoke/assign; dùng `ContainerStoppedEvent` cho trạng thái toàn container.
7. Cleanup phải nhanh, idempotent, quan sát được lỗi và không đóng shared resources của consumer khác.
8. Không dựa vào event để bảo đảm shutdown khi JVM crash cưỡng bức hoặc pod bị kill không graceful.
9. Kết hợp event với committed offset, lag, stop reason và deployment timeline khi chẩn đoán.
10. Kiểm thử stop, restart, rebalance, pause/resume và multicaster đồng bộ/bất đồng bộ trước khi đặt cleanup production dựa trên event.

**Kết luận:** `ConsumerStoppingEvent` là một hook lifecycle có giá trị để Spring Kafka thông báo rằng **consumer thread đang chuẩn bị kết thúc**. Nó thích hợp cho cleanup nhanh và chính xác của tài nguyên gắn với thread cùng với log/metric vận hành. Bảo đảm an toàn đến từ việc sử dụng đúng thread, không can thiệp vào KafkaConsumer mà container đang đóng, và giữ riêng cơ chế xử lý record, commit offset, rebalance và khôi phục sau crash.
