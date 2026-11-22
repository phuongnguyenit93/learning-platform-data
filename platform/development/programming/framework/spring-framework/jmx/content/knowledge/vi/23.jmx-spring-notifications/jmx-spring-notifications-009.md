# Đồng bộ, bất đồng bộ và thread khi xử lý JMX Notification Listener trong Spring Framework

## 1. Mục tiêu bài học

JMX Notification cho phép một MBean phát sự kiện quản trị như worker thay đổi trạng thái, hàng đợi vượt ngưỡng hoặc một tác vụ bảo trì hoàn tất. Một `NotificationListener` nhận thông báo thông qua phương thức `handleNotification(Notification, Object)`. Trong Spring Framework, ứng dụng có thể khai báo listener và đăng ký với MBean bằng `MBeanExporter` hoặc sử dụng `NotificationListenerBean`.

Khi thiết kế listener, câu hỏi quan trọng không chỉ là **nhận được thông báo chưa**, mà còn là:

- Callback được chạy trên thread nào?
- Việc gửi thông báo có chờ listener xử lý xong không?
- Listener chậm có làm tắc nghẽn code phát notification không?
- Nhiều listeners có chạy tuần tự hay song song?
- Exception trong listener tác động đến nguồn phát và listeners khác như thế nào?
- Khi listener xử lý bất đồng bộ, làm sao kiểm soát thứ tự, queue, backpressure và shutdown?
- Khi JMX client ở xa, callback đi qua những threads và mạng nào?

Sau bài học, bạn sẽ phân biệt ngữ nghĩa đồng bộ/bất đồng bộ của **notification dispatch** và **business processing**, cấu hình listener an toàn cho ứng dụng Spring, đồng thời kiểm thử thread, thứ tự, lỗi và vòng đời.

## 2. Notification là gì?

JMX Notification là đối tượng kế thừa `javax.management.Notification`, có các thông tin thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `type` | Loại sự kiện, ví dụ `training.worker.paused` |
| `source` | Đối tượng phát |
| `sequenceNumber` | Số thứ tự do nguồn phát gán |
| `timeStamp` | Thời điểm notification được tạo |
| `message` | Mô tả để người vận hành đọc |
| `userData` | Dữ liệu bổ sung nếu cần |

Một MBean có thể phát notification bằng cách dùng `NotificationBroadcasterSupport` hoặc triển khai các giao diện JMX tương ứng.

Người nhận dùng:

```java
public interface NotificationListener {
    void handleNotification(Notification notification, Object handback);
}
```

Giá trị `handback` do bên đăng ký listener cung cấp; nó không phải payload sự kiện do emitter tự động tạo.

Sơ đồ cơ bản:

```text
Management event
      |
      v
MBean / NotificationEmitter
      |
      | sendNotification(...)
      v
JMX notification dispatch
      |
      +-- listener A
      +-- listener B
      +-- listener C
```

Không được xem notification như hàng đợi tin nhắn bền vững có retry, acknowledgement và lưu trữ mặc định. JMX notifications chủ yếu hỗ trợ thông báo quản trị, không thay thế messaging system khi cần bảo đảm delivery.

## 3. Đồng bộ và bất đồng bộ có hai tầng khác nhau

Cần tách:

1. **Tầng JMX dispatch:** notification được chuyển từ broadcaster đến `NotificationListener` như thế nào.
2. **Tầng xử lý nghiệp vụ trong listener:** callback xử lý ngay hay chỉ enqueue công việc cho executor khác.

Ví dụ:

```text
Thread phát sự kiện
    |
    v
sendNotification()
    |
    +-- Đồng bộ: gọi listener.handleNotification() trực tiếp
    |
    +-- Bất đồng bộ: đẩy callback sang Executor
                          |
                          v
                    Worker thread
```

Ngay cả khi JMX dispatch đồng bộ, listener vẫn có thể tự đưa công việc vào queue rồi trả về nhanh. Ngược lại, có executor dispatch bất đồng bộ nhưng bên trong listener lại chạy tác vụ dài, khiến thread pool của broadcaster bị nghẽn.

**Quan trọng:** behavior của `NotificationBroadcasterSupport` phụ thuộc constructor và `Executor` được cung cấp. Mặc định nếu không thiết lập executor riêng, notification được gửi theo kiểu đồng bộ với thread gọi `sendNotification`. Khi cung cấp executor, broadcaster chuyển nhiệm vụ thông báo theo cơ chế executor đó. Hành vi thứ tự/đồng thời phụ thuộc executor, không phải JMX tự bảo đảm tuần tự cho mọi cấu hình.

## 4. Đồng bộ: listener chạy trên thread phát notification

Ví dụ đơn giản:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationListener;
import java.util.concurrent.atomic.AtomicLong;

public class WorkerEmitter extends NotificationBroadcasterSupport {
    private final AtomicLong sequence = new AtomicLong();

    public void pause() {
        Notification notification = new Notification(
            "training.worker.paused",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker paused"
        );
        sendNotification(notification);
    }

    public static void main(String[] args) {
        WorkerEmitter emitter = new WorkerEmitter();

        NotificationListener listener = (n, handback) -> {
            System.out.println(
                "Listener thread: " +
                Thread.currentThread().getName());
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        emitter.addNotificationListener(listener, null, null);

        long started = System.nanoTime();
        emitter.pause();
        long durationMs =
            (System.nanoTime() - started) / 1_000_000L;

        System.out.println("Duration ms: " + durationMs);
    }
}
```

Trong cấu hình synchronous dispatch, `pause()` phải chờ callback hoàn thành, nên thời gian chạy sẽ bao gồm phần sleep của listener.

### 4.1. Ưu điểm

- Logic đơn giản, dễ quan sát thread.
- Không cần thiết lập executor và queue riêng.
- Listener hoàn thành trước khi `sendNotification` trả về, nếu không có exception/hành vi đặc biệt.
- Hữu ích khi callback rất ngắn, chỉ cập nhật bộ đếm hoặc ghi log nhẹ.

### 4.2. Nhược điểm

- Listener chậm làm tăng latency cho method phát notification.
- Nếu code gửi notification đang giữ lock, listener chạy lâu có thể tăng contention hoặc tạo deadlock.
- Listener gọi network, database hoặc blocking I/O có thể làm tắc thread quan trọng.
- Các listener có thể ảnh hưởng latency của nhau nếu broadcaster dispatch tuần tự.

**Khuyến nghị:** callback đồng bộ nên ngắn, không chặn lâu và không phụ thuộc vào hệ thống bên ngoài thiếu timeout.

## 5. Bất đồng bộ bằng Executor của NotificationBroadcasterSupport

JDK cung cấp constructor nhận `Executor`. Ví dụ:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationListener;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

public final class AsyncWorkerEmitter
        extends NotificationBroadcasterSupport
        implements AutoCloseable {

    private final ExecutorService executor;
    private final AtomicLong sequence = new AtomicLong();

    public AsyncWorkerEmitter(ExecutorService executor) {
        super(executor);
        this.executor = executor;
    }

    public void signal(String message) {
        Notification notification = new Notification(
            "training.worker.signal",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message);
        sendNotification(notification);
    }

    @Override
    public void close() {
        executor.shutdown();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
            Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "jmx-notify-worker");
                t.setDaemon(true);
                return t;
            });

        try (AsyncWorkerEmitter emitter =
                 new AsyncWorkerEmitter(executor)) {
            emitter.addNotificationListener(
                (n, h) -> System.out.println(
                    "Thread = " +
                    Thread.currentThread().getName() +
                    ", message=" + n.getMessage()),
                null, null);

            emitter.signal("ready");
            Thread.sleep(300);
        }
    }
}
```

Khi executor nhận task, `sendNotification` có thể trả về trước callback. Một `ExecutorService` vẫn cần lifecycle và shutdown phù hợp, đặc biệt nếu Spring quản lý broadcaster như bean. Trong ví dụ demo, sleep chỉ để minh họa quan sát; test thực nên dùng `CountDownLatch` thay vì phụ thuộc thời gian ngủ.

### 5.1. Một thread hay nhiều threads?

- Single-thread executor: thường giữ thứ tự thực hiện các task theo thứ tự được submit, giảm cạnh tranh giữa callbacks.
- Fixed-thread pool: có thể xử lý song song, tăng throughput nhưng kết thúc callback không nhất thiết theo sequence.
- Bounded thread pool/queue: giúp kiểm soát tài nguyên khi số notification tăng.
- Unbounded queue: dễ tăng memory nếu producer nhanh hơn consumer.

Chọn executor theo tính chất callback và số lượng notification, không mặc định dùng pool lớn để “nhanh hơn”.

## 6. Spring quản lý listener bằng NotificationListenerBean

Spring Framework hỗ trợ `org.springframework.jmx.export.notification.NotificationListenerBean`, cho phép kết hợp listener, filter, handback và mapping MBean được giám sát. Một ví dụ cấu hình dùng `MBeanExporter`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import java.util.Map;

@Configuration
public class JmxNotificationConfig {

    @Bean
    public NotificationListener workerNotificationListener() {
        return (notification, handback) -> {
            System.out.println(
                "Received: " + notification.getType());
        };
    }

    @Bean
    public NotificationListenerBean workerListenerBean(
            NotificationListener workerNotificationListener)
            throws Exception {

        NotificationListenerBean bean =
            new NotificationListenerBean();
        bean.setNotificationListener(workerNotificationListener);
        bean.setMappedObjectNames(
            new ObjectName(
                "training.spring:type=Worker,name=Primary"));
        return bean;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerManagement worker,
            NotificationListenerBean workerListenerBean) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "training.spring:type=Worker,name=Primary", worker));
        exporter.setNotificationListeners(workerListenerBean);
        return exporter;
    }
}
```

`WorkerManagement` là một MBean-compatible class/bean cần được định nghĩa để phát notification, ví dụ kế thừa `NotificationBroadcasterSupport` hoặc dùng cơ chế Spring notification publisher. Đoạn cấu hình minh họa cách wiring listener; nếu ứng dụng đã có exporter tự động, phải tránh khai báo exporter thứ hai đăng ký cùng ObjectName.

**Lưu ý:** Spring không biến callback của listener thành bất đồng bộ chỉ vì listener được khai báo dưới dạng Spring bean. Thread thực thi phụ thuộc broadcaster, connector và cách listener tự xử lý công việc.

## 7. Spring NotificationPublisher và thread phát sự kiện

Spring JMX cung cấp cách phát notification qua `NotificationPublisher` khi bean triển khai `NotificationPublisherAware` trong cấu hình exporter phù hợp.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

import javax.management.Notification;
import java.util.concurrent.atomic.AtomicLong;

@ManagedResource(
    objectName = "training.spring:type=Worker,name=Primary")
public class WorkerManagement implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedOperation
    public void pause() {
        Notification n = new Notification(
            "training.worker.paused",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Paused via JMX");
        publisher.sendNotification(n);
    }
}
```

Để công bố notification metadata cho client, Spring hỗ trợ `@ManagedNotification` trong cấu hình annotation export thích hợp. Khi `pause()` được gọi qua JMX, thread gọi operation có thể là thread phục vụ connector. Nếu dispatch đến listener là đồng bộ và callback chậm, client có thể thấy `invoke("pause")` chậm hơn.

```text
Remote JMX request thread
        |
        v
WorkerManagement.pause()
        |
        v
publisher.sendNotification()
        |
        v
Listener đồng bộ chạy lâu
        |
        v
pause() mới trả về
        |
        v
Remote JMX client nhận kết quả
```

Do đó phải cẩn trọng khi notification được phát trong operations quản trị quan trọng.

## 8. Listener bất đồng bộ bằng cách enqueue công việc

Không nhất thiết phải cấu hình executor ở broadcaster. Một cách khác là listener nhận notification nhanh và đưa xử lý nặng vào queue:

```java
import javax.management.Notification;
import javax.management.NotificationListener;
import java.util.concurrent.Executor;

public final class EnqueueingListener implements NotificationListener {
    private final Executor executor;

    public EnqueueingListener(Executor executor) {
        this.executor = executor;
    }

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        String type = notification.getType();
        long sequence = notification.getSequenceNumber();

        executor.execute(() ->
            process(type, sequence));
    }

    private void process(String type, long sequence) {
        System.out.printf(
            "Processed %s sequence=%d%n",
            type, sequence);
    }
}
```

Ở đây callback chỉ tạo snapshot của những trường cần thiết và submit task. Điều này giảm thời gian callback đồng bộ, nhưng vẫn có vấn đề:

- Executor có thể từ chối task (`RejectedExecutionException`).
- Queue có thể đầy.
- Notification có thể bị xử lý sau khi resource đã thay đổi.
- Tác vụ có thể lỗi, cần logs và metrics riêng.
- Shutdown có thể làm mất các task còn trong queue.

Với payload mutable trong `userData`, không nên truyền tham chiếu dùng chung sang thread khác mà không có hợp đồng thread-safety. Có thể chuyển sang immutable DTO/snapshot.

## 9. Thứ tự notification và concurrency

JMX Notification có `sequenceNumber`, nhưng không thể suy ra mọi listener đều **xử lý xong theo sequence** trong mọi cấu hình.

Ví dụ:

```text
Notification #101 -> Thread A (work 2 seconds)
Notification #102 -> Thread B (work 100 ms)

Completion:
  #102 finishes before #101
```

Với executor đa luồng, chuyện này bình thường. Nếu operation cần đảm bảo ordering, cân nhắc:

1. Single-thread executor cho một nguồn/event stream.
2. Partition queue theo resource ID để từng resource được xử lý tuần tự.
3. Dùng sequence/idempotency để phát hiện out-of-order events.
4. Thiết kế state machine kiểm tra version trước khi áp dụng thay đổi.
5. Tránh sử dụng notification như giao thức cập nhật trạng thái bắt buộc nếu không có delivery guarantees.

Số sequence có thể được tạo bởi broadcaster/managed bean theo chính sách của ứng dụng. Không giả định sequence duy nhất toàn JVM hoặc toàn hệ thống phân tán.

### 9.1. Có nhiều listener

Một broadcaster có thể có nhiều listeners:

```text
Emitter
   +--> AuditListener
   +--> MetricsListener
   +--> AlertListener
```

Nếu một listener chậm, synchronous dispatch có thể làm chậm notification delivery tổng thể. Với executor chung, listener chiếm thread lâu vẫn có thể khiến các listener khác chờ queue. Muốn isolation, có thể dùng executor riêng hoặc listener nhẹ chỉ enqueue sang các hệ thống độc lập.

## 10. NotificationFilter và handback

Khi đăng ký listener:

```java
emitter.addNotificationListener(
    listener,
    notification -> notification.getType()
        .startsWith("training.worker."),
    "worker-tag");
```

- `NotificationFilter` quyết định notification nào được chuyển tới listener.
- `handback` là đối tượng được trả lại cho callback để giữ ngữ cảnh đăng ký.
- Filter có thể được thực thi trên đường dispatch, nên cũng cần ngắn và không chặn.

Không truyền secrets vào `handback` nếu logs, debugging hoặc client code không đáng tin có thể nhìn thấy nó. Remote JMX có thêm ràng buộc serialization và quyền truy cập; kiểm thử riêng nếu dùng handback phức tạp.

## 11. Exception trong listener

Một listener có thể ném `RuntimeException`:

```java
NotificationListener listener = (n, h) -> {
    throw new IllegalStateException("failed");
};
```

Với `NotificationBroadcasterSupport`, cách xử lý exception của listener thuộc cơ chế dispatcher/JMX implementation. Đừng mặc định exception sẽ phá hủy nguồn phát hoặc được remote client nhìn thấy như business exception của operation. Cần kiểm tra behavior cụ thể của broadcaster và executor.

Một listener robust nên chủ động cô lập lỗi:

```java
public void handleNotification(Notification n, Object handback) {
    try {
        processNotification(n);
    } catch (RuntimeException ex) {
        logger.error(
            "Failed handling JMX notification type={}",
            n.getType(),
            ex);
        metrics.recordListenerFailure(n.getType());
    }
}
```

Đây là code minh họa, `logger` và `metrics` cần được định nghĩa/inject trong ứng dụng.

### 11.1. Đừng nuốt lỗi hoàn toàn

Nếu lỗi chỉ bị bắt rồi bỏ qua, hệ thống mất khả năng quan sát. Cần log phù hợp, error counter, cảnh báo khi tỷ lệ lỗi cao và cơ chế retry có điều kiện nếu notification được xử lý thành tác vụ bên ngoài.

### 11.2. Retry và idempotency

JMX notification không có ack/retry bền vững mặc định. Khi xử lý lỗi, nếu cần retry, phải tự quản lý idempotency và đảm bảo không gây side effect lặp. Với dữ liệu quan trọng, thay JMX notification bằng message broker/event log có khả năng lưu trữ và retry.

## 12. Backpressure và giới hạn queue

Khi producer phát nhanh hơn listener xử lý:

```text
Notification producer: 1000 events/s
Listener processing:   100 events/s
Backlog growth:        900 events/s
```

Một queue không giới hạn có thể gây memory pressure. Ví dụ tạo executor có giới hạn:

```java
import java.util.concurrent.*;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
    2, 2,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(200),
    r -> {
        Thread t = new Thread(r, "jmx-listener-worker");
        t.setDaemon(true);
        return t;
    },
    new ThreadPoolExecutor.AbortPolicy());
```

`AbortPolicy` ném `RejectedExecutionException` khi không nhận thêm task. Listener cần xác định policy khi overload: báo lỗi, drop có metrics, chuyển sang hàng đợi bền vững hoặc block producer có kiểm soát. Không dùng `CallerRunsPolicy` mà không hiểu rằng nó có thể làm callback chạy trên thread phát notification, khiến một thiết kế tưởng như async trở lại đồng bộ khi queue đầy.

### 12.1. Đặt giới hạn đo được

Theo dõi:

- Số notification phát/nhận.
- Queue depth.
- Active executor threads.
- Processing latency P50/P95/P99.
- Số rejected tasks.
- Số lỗi listener.
- Thời gian shutdown còn work pending.

Không gắn payload nhạy cảm vào metric labels.

## 13. Deadlock và lock contention

Một rủi ro khó chẩn đoán:

```text
Thread A holds lock L
   |
   +-- sendNotification()
         |
         +-- synchronous listener
               |
               +-- tries to acquire lock M

Thread B holds lock M
   |
   +-- waits for lock L
```

Vòng đợi này tạo deadlock. Thậm chí khi không deadlock, listener chậm bên trong `synchronized` block có thể làm tăng độ trễ.

Các biện pháp:

1. Không phát notification khi đang giữ lock dài nếu có thể tránh.
2. Dùng immutable snapshot cho event payload.
3. Giữ callback ngắn.
4. Không gọi lại chính MBean từ listener theo một đường có nguy cơ reentrancy mà chưa phân tích lock.
5. Dùng thread dump (`jcmd <pid> Thread.print`) khi nghi deadlock.
6. Dùng executor độc lập nếu dispatch sync không phù hợp; vẫn cần xác định ordering và queue policy.

## 14. Remote JMX listener có đặc thù khác

Với remote connector, listener ở phía client không được gọi trên thread business của server theo cách trực tiếp như local broadcaster. JMX connector có cơ chế chuyển notification qua giao thức, queue/fetch/dispatch và các threads riêng tùy implementation.

```text
Server JVM
  MBean emits notification
       |
  MBeanServer / connector
       |
     network
       |
Client JVM
  connector notification dispatcher
       |
  NotificationListener.handleNotification()
```

Vì vậy không được giả định:

- Callback luôn chạy trên thread đã gọi `addNotificationListener`.
- Callback remote chạy cùng thread với operation server.
- Remote notification có exactly-once delivery.
- Mất kết nối sẽ tự gửi lại mọi notification đã phát.
- Thread name hoặc số thread cố định giữa các phiên bản JDK.

Một client chậm cũng có thể gây backlog/gián đoạn nhận notification theo cấu hình connector. Nếu cần xử lý quan trọng, hãy query lại trạng thái authoritative qua MBean attributes/operations sau reconnect.

## 15. Lifecycle: đăng ký và hủy đăng ký listener

Khi dùng JMX trực tiếp:

```java
emitter.addNotificationListener(listener, filter, handback);
try {
    // Handle notifications.
} finally {
    emitter.removeNotificationListener(listener);
}
```

Với `MBeanServerConnection`, có thể dùng:

```java
connection.addNotificationListener(
    objectName, listener, filter, handback);

try {
    // Work.
} finally {
    connection.removeNotificationListener(
        objectName, listener);
}
```

Cần xử lý các lỗi nếu MBean đã unregister hoặc kết nối đã đóng. Trong Spring, exporter và listener registration beans có lifecycle do ApplicationContext quản lý, nhưng không nên giả định mọi listener đăng ký thủ công sẽ được Spring tự dọn dẹp.

### 15.1. Executor shutdown

Nếu executor do Spring quản lý, có thể khai báo bean:

```java
@Bean(destroyMethod = "shutdown")
public ExecutorService jmxNotificationExecutor() {
    return Executors.newFixedThreadPool(2);
}
```

Khi context đóng, executor cần ngừng nhận task, chờ hoặc xử lý phần việc còn lại theo policy. `shutdown()` không chờ mọi task kết thúc ngay; `awaitTermination` có thể cần cho graceful shutdown. Nếu dùng daemon threads, JVM có thể kết thúc dù task còn lại, nên không dùng daemon như cơ chế bảo đảm hoàn tất công việc quan trọng.

## 16. Kiểm thử thread và tính bất đồng bộ

Dùng `CountDownLatch` thay vì `Thread.sleep` để tránh test không ổn định.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class NotificationThreadTest {

    @Test
    void synchronousCallbackRunsInCallingThread() {
        var emitter = new NotificationBroadcasterSupport();
        var listenerThread = new AtomicReference<Thread>();
        Thread caller = Thread.currentThread();

        emitter.addNotificationListener(
            (notification, handback) ->
                listenerThread.set(Thread.currentThread()),
            null, null);

        emitter.sendNotification(
            new Notification("test.sync", this, 1L));

        assertSame(caller, listenerThread.get());
    }

    @Test
    void asynchronousCallbackRunsOnExecutorThread()
            throws Exception {

        ExecutorService executor =
            Executors.newSingleThreadExecutor(
                r -> new Thread(r, "notification-executor"));

        try {
            var emitter =
                new NotificationBroadcasterSupport(executor);

            CountDownLatch handled = new CountDownLatch(1);
            AtomicReference<String> observed =
                new AtomicReference<>();

            emitter.addNotificationListener(
                (notification, handback) -> {
                    observed.set(
                        Thread.currentThread().getName());
                    handled.countDown();
                },
                null, null);

            emitter.sendNotification(
                new Notification("test.async", this, 2L));

            assertTrue(handled.await(2, TimeUnit.SECONDS));
            assertEquals("notification-executor", observed.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Lưu ý thời hạn `await` là budget cho test, không bảo đảm timing của một máy đang quá tải; CI cần điều chỉnh hợp lý. Với unit test, dùng executor controllable có thể giúp kiểm tra callback chưa chạy trước khi test chủ động drain task queue.

## 17. Kiểm thử ordering và backpressure

Một bài test ordering:

1. Tạo `NotificationBroadcasterSupport` với fixed pool nhiều threads.
2. Phát notification #1 và #2.
3. Cố tình cho callback #1 chờ latch, callback #2 xử lý nhanh.
4. Quan sát thứ tự completion có thể khác emission order.
5. Chuyển sang single-thread executor và so sánh.

Một bài test overload:

1. Tạo executor với queue size nhỏ.
2. Block workers bằng latch để làm đầy queue.
3. Phát thêm notifications.
4. Xác minh rejection policy được kích hoạt.
5. Xác minh metrics/logs ghi nhận overload.
6. Cleanup mọi thread/latch để test không treo.

Không thực hiện load-test notification trực tiếp trên production nếu không có kế hoạch và giới hạn cụ thể.

## 18. Chọn mô hình xử lý nào?

| Nhu cầu | Mô hình phù hợp | Lưu ý |
|---|---|---|
| Ghi một counter rất nhanh | Synchronous callback | Không block |
| Cập nhật UI/dashboard | Async dispatch hoặc enqueue | Chấp nhận eventual consistency |
| Gọi API ngoài | Bounded executor/queue | Timeout, retry có điều kiện |
| Cần giữ thứ tự theo resource | Single-thread/partitioned executor | Định nghĩa ordering key |
| Notification nhiều và bursty | Bounded queue + overload policy | Metrics và backpressure |
| Xử lý nghiệp vụ quan trọng | Message broker/event log | JMX không bảo đảm durable delivery |
| Remote monitoring | JMX client listener + resync | Có thể mất event khi disconnect |

Không có lựa chọn “async luôn tốt hơn sync”. Callback nhanh đồng bộ dễ kiểm soát và ít overhead, trong khi callback dài hoặc blocking nên được cô lập khỏi thread nguồn.

## 19. Checklist vận hành

- [ ] Biết ai tạo emitter và ai đăng ký listener.
- [ ] Xác định dispatch dùng synchronous hay Executor.
- [ ] Không làm network I/O dài trong callback đồng bộ.
- [ ] Có metrics cho callback latency và failure.
- [ ] Queue và thread pool có giới hạn nếu dùng async.
- [ ] Có overload policy, không chỉ tạo unbounded queue.
- [ ] Có chiến lược ordering/idempotency khi nhiều threads.
- [ ] Không giả định notification là hàng đợi bền vững.
- [ ] Đóng listener/executor đúng lifecycle.
- [ ] Không chuyển dữ liệu nhạy cảm qua notification payload.
- [ ] Có quy trình resync sau remote reconnect.
- [ ] Có tests cho thread, error, ordering, shutdown.

## 20. Bài tập thực hành

### Bài tập A — Quan sát synchronous listener

Viết broadcaster mặc định và một listener ngủ 300 ms trong lab. Đo thời gian `sendNotification`. Ghi nhận tên thread ở emitter và listener, giải thích vì sao method phát bị chậm.

### Bài tập B — Đổi sang executor

Tạo một single-thread executor rồi truyền vào `NotificationBroadcasterSupport`. Đo lại latency của `sendNotification` và completion time. Dùng `CountDownLatch` để test, không chỉ nhìn log.

### Bài tập C — Hai listeners, một callback chậm

Đăng ký metrics listener xử lý nhanh và audit listener gọi I/O mô phỏng chậm. So sánh synchronous dispatch với thread pool. Đề xuất cách tránh callback chậm ảnh hưởng phần còn lại.

### Bài tập D — Spring Listener Bean

Tạo `@ManagedResource` phát notification qua `NotificationPublisherAware`. Đăng ký listener bằng `NotificationListenerBean`, gọi operation `pause` và ghi thread name ở cả emitter và listener. Đổi sang listener enqueue công việc rồi so sánh.

### Bài tập E — Overload

Thiết lập bounded executor nhỏ, phát burst notifications và đo số rejected tasks. Thử policy drop có metrics hoặc queue bền vững trong lab; giải thích trade-off.

### Bài tập F — Remote reconnect

Tạo JMX client ở process khác, đăng ký listener, ngắt kết nối rồi kết nối lại. So sánh số notification nhận được với trạng thái hiện tại của MBean. Thêm bước resync bằng attribute đọc từ server.

## 21. Câu hỏi tự kiểm tra

1. Thread nào gọi listener trong synchronous dispatch?
2. Cung cấp executor cho broadcaster làm thay đổi điều gì?
3. Vì sao gọi database trong listener đồng bộ có thể làm chậm operation JMX?
4. `sequenceNumber` có tự đảm bảo completion order không?
5. `CallerRunsPolicy` ảnh hưởng thiết kế async thế nào?
6. Vì sao `NotificationListenerBean` không tự biến callback thành async?
7. Khi nào phải dùng durable messaging thay JMX notification?
8. Tại sao `Future.cancel` hoặc ngắt thread không bảo đảm xử lý đã bị hủy?
9. Cần làm gì khi listener executor bị quá tải?
10. Vì sao remote JMX listener có thread semantics khác listener local?

## 22. Tài liệu tham khảo

- Spring Framework Reference — Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationListenerBean.html
- Spring Framework API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Java SE 21 — NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 — NotificationListener: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 — ThreadPoolExecutor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html

**Ghi nhớ:** synchronous notification dispatch thường gọi listener trên đường thực thi của bên phát; cấu hình executor giúp chuyển callbacks sang worker threads, nhưng thêm chi phí queue, ordering và lifecycle. Trong Spring JMX, phải xác định rõ tầng nào dispatch và tầng nào xử lý nghiệp vụ, giữ callback ngắn, dùng bounded queues khi cần và không coi notification là hệ thống message delivery bền vững.
