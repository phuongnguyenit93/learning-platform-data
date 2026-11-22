# Payload lớn và áp lực bộ nhớ trong Spring Application Events

Một application event thường chỉ cần mô tả **điều gì đã xảy ra**: ID của aggregate, loại sự kiện, phiên bản và các dữ liệu tối thiểu để listener tiếp tục công việc. Nếu ta đưa toàn bộ file, ảnh, JSON lớn, cây object/JPA entity hay danh sách hàng chục nghìn phần tử vào event, chi phí không dừng ở kích thước object tại lúc `publishEvent(...)`. Khi listener xử lý chậm hoặc bất đồng bộ, object có thể bị **giữ tham chiếu trong hàng đợi**, tăng live heap, tăng áp lực garbage collection (GC), gây latency và cuối cùng có thể dẫn tới `OutOfMemoryError`.

Đây là vấn đề về **lifetime và số lượng object đang sống**, không chỉ về “Java object nặng bao nhiêu byte”. Spring Framework Application Events là cơ chế truyền thông tin trong một application context, **không phải message queue bền vững có backpressure tự động**. Bài học giải thích cơ chế giữ payload, ước lượng áp lực bộ nhớ, các lựa chọn thiết kế an toàn, cấu hình executor giới hạn queue và cách kiểm thử Java 17+ với Spring Test.

## 1. Payload lớn là gì và khi nào nguy hiểm?

Payload là phần thông tin mang theo event. Từ Spring Framework 4.2, có thể publish một đối tượng Java thông thường, chẳng hạn `record ReportCreated(...)`. Spring bọc đối tượng không phải `ApplicationEvent` vào `PayloadApplicationEvent` để dispatch. Việc bọc này **không mặc nhiên serialize hoặc deep-copy toàn bộ object graph**.

Ví dụ một event dễ gây áp lực bộ nhớ:

~~~java
record ReportGenerated(
    String reportId,
    byte[] pdfBytes,
    String customerId
) {}
~~~

Khi file PDF có kích thước vài MiB và mỗi request tạo một `byte[]` riêng, event giữ tham chiếu đến mảng này. `record` làm các field reference trở thành final nhưng **không biến nội dung `byte[]` thành immutable**; thread khác vẫn có thể thay đổi phần tử.

Trong thực tế, payload lớn còn có thể nằm ở:

- `String` chứa XML/JSON cỡ lớn;
- `List<OrderLine>` với hàng trăm nghìn phần tử;
- entity JPA mang theo toàn bộ quan hệ hoặc proxy lazy-loading;
- `Map<String,Object>` chứa bản sao dữ liệu từ request;
- `byte[]`, `ByteBuffer`, image, tài liệu, tệp nén;
- object bất kỳ mà `toString()` hoặc JSON serialization tạo thêm một bản sao rất lớn.

“Lớn” phụ thuộc **tần suất event, số listeners, thời gian chờ, heap size và hành vi copy**. Một event 8 MiB thỉnh thoảng xuất hiện có thể ổn trong công việc đồng bộ; nhưng 200 event 4 MiB đang chờ pool là một tình huống đáng lo, dù từng object riêng lẻ không có gì bất thường.

## 2. Vì sao event có thể giữ bộ nhớ lâu hơn dự kiến?

Xem đồ thị tham chiếu khái niệm:

~~~text
ApplicationEventPublisher.publishEvent(reportGenerated)
                   |
                   v
      PayloadApplicationEvent / event object
                   |
                   +----> ReportGenerated
                                 |
                                 +----> byte[] pdfBytes (4 MiB)

Nếu listener đồng bộ:
  publisher thread -> listener dùng payload -> stack kết thúc
  (nếu không còn reference khác, payload có thể được GC)

Nếu listener @Async:
  publisher thread -> submit Runnable vào executor queue
                          |
                          +----> task/lambda/proxy giữ event
                                       |
                                       +----> byte[] (4 MiB)
  Task chưa chạy vẫn giữ một đường strong reference tới dữ liệu.
~~~

**GC chỉ thu hồi object khi không còn đường tham chiếu sống phù hợp đến object đó.** `publishEvent` trả về không có nghĩa object đã trở nên có thể thu hồi: executor queue, listener, một `CompletableFuture`, cache, retry buffer hoặc cấu trúc ứng dụng khác vẫn có thể giữ nó.

Cần phân biệt:

1. **Allocation:** tạo object hoặc bản sao mới làm tăng lượng bộ nhớ được cấp phát.
2. **Retention:** một object còn reachable, nên chưa thu hồi được.
3. **GC pressure:** hệ thống phải theo dõi/thu hồi nhiều object; nếu live set quá lớn, khoảng trống heap giảm.
4. **Memory leak thực sự:** giữ tham chiếu lâu ngoài nhu cầu; không phải mọi đỉnh heap nhất thời đều là leak.
5. **Thêm bản sao do serialization:** `byte[]` -> Base64/JSON/string có thể tạo nhiều intermediate buffers; tác động khác với một reference đơn thuần.

Một listener có thể giữ cùng object bằng tham chiếu (không copy) và vẫn gây **retained memory** đáng kể. Ngược lại, nếu nhiều events tham chiếu cùng một immutable object, không được lấy kích thước payload nhân số events mà coi là bộ nhớ mới tương ứng.

## 3. Ước lượng áp lực bộ nhớ bằng live outstanding events

Với các payload **khác nhau, không dùng chung**, một ước lượng rất thô là:

~~~text
retained_payload_bytes ≈ distinct_outstanding_events × bytes_reachable_per_event

Ví dụ:
  mỗi event chứa byte[] ~ 4 MiB
  khoảng 200 event khác nhau chưa xử lý
  riêng dữ liệu payload đã xấp xỉ 800 MiB
~~~

Đây **không phải tổng heap đã đo** và không phải mức trần chính xác: còn event wrappers, executor tasks, queue nodes, object graph, String/collection overhead, duplicated JSON buffers và các reference khác. `byte[]` 4 MiB ở đây là ví dụ để hiểu cấp độ rủi ro, không phải kích thước có thể đọc từ record một cách tự động.

Khi đo hiệu năng, một mô hình khác hữu ích là quan hệ thông lượng–thời gian chờ:

~~~text
outstanding ≈ arrival_rate × average_time_in_system

Ví dụ (trạng thái gần ổn định):
  50 events/giây × trung bình 4 giây mỗi event chờ/xử lý
  -> khoảng 200 events outstanding
~~~

Đây là suy luận gần đúng từ Little's Law và chỉ đúng dưới những giả định phù hợp như hệ thống gần ổn định. Khi arrival rate vượt khả năng xử lý trong thời gian dài, queue có thể **tiếp tục phình ra**, nên không được dùng công thức trạng thái ổn định để bảo đảm một mức trần.

### Tại sao “thêm threads” chưa chắc giải quyết được?

Nếu bottleneck nằm ở DB, broker, API bên ngoài hay disk, tăng số worker có thể làm nhiều tác vụ cùng giữ payload và tăng số connection/request đang chờ. Heap tệ hơn, downstream còn bị quá tải. Ngược lại, giảm queue capacity nhưng không có chính sách từ chối/backpressure phù hợp có thể làm lộ lỗi tải cao ngay trên caller.

Cần xác định **độ lớn payload × số bản còn sống × thời gian sống**, chứ không chỉ đếm số request hay nhìn một snapshot `usedHeap`.

## 4. Listener đồng bộ, @Async và custom multicaster giữ payload khác nhau

| Cơ chế | Hành vi chính | Rủi ro bộ nhớ cần chú ý |
| --- | --- | --- |
| `@EventListener` đồng bộ mặc định | Thực thi trên publisher thread; `publishEvent` có thể bị chặn | Payload sống trong call stack lâu nếu listener chậm; throughput caller giảm |
| `@Async @EventListener` | Async proxy submit invocation đến executor riêng | Pending Runnable/task có thể giữ reference tới payload lớn |
| `SimpleApplicationEventMulticaster.setTaskExecutor(...)` | Multicaster schedule listeners hỗ trợ async execution | Số tasks có thể tăng theo số listeners; cách xử lý task rejection tùy phiên bản/cấu hình |
| `@TransactionalEventListener` | Listener gắn với transaction phase; thường đăng ký synchronization trước khi xử lý | Event có thể được giữ tới commit/rollback completion |
| Broker/outbox | Phần message được lưu ngoài event bus in-memory | Có chi phí serialization/persistence; payload lớn vẫn phải quản lý riêng |

Trong cấu hình mặc định, Spring dùng `SimpleApplicationEventMulticaster` và xử lý listeners đồng bộ. `@Async` là một cơ chế riêng: method proxy gửi task tới executor. Nếu custom multicaster cũng dùng executor, cần hiểu **hai tầng scheduling** và exception/queue semantics thay vì mặc định coi chúng tương đương.

**Cảnh báo quan trọng:** không dựa vào một hành vi từ chối task duy nhất cho mọi multicaster/phiên bản. Một số implementation/phiên bản có thể xử lý `RejectedExecutionException` bằng cách chạy tại caller thread, trong khi `@Async` proxy với `ThreadPoolTaskExecutor` có thể ném `TaskRejectedException`. Kiểm thử **chính cấu hình đang dùng**, đặc biệt khi transaction nằm trên publisher thread.

## 5. Thiết kế event nhỏ: metadata thay vì binary data

Thay vì:

~~~java
// Anti-pattern: event mang toàn bộ file.
public record ReportReady(
    String reportId,
    byte[] pdfBytes,
    String recipientEmail
) {}
~~~

Ưu tiên event có định danh, version và một tham chiếu tới dữ liệu bền vững:

~~~java
public record ReportReady(
    String eventId,
    String reportId,
    String objectKey,
    long contentLength,
    String checksumSha256
) {}
~~~

Đây là hai **phương án dữ liệu độc lập**, mỗi record cần được đặt trong file Java cùng tên nếu tạo `public` top-level type. `objectKey` ở ví dụ thứ hai nên trỏ tới storage có durability, expiration policy và access control phù hợp (object store, blob store, database). Không biến nó thành một presigned URL chứa token sống dài trong event hoặc log.

Luồng xử lý tốt hơn:

~~~text
Application service
  -> tạo file / stream vào object storage bền vững
  -> nhận objectKey, size, checksum
  -> publish ReportReady(eventId, reportId, objectKey, ...)
          |
          +-- Listener đọc metadata nhỏ
                 |
                 +-- cần bytes thì mở stream từ storage theo chunk
                 +-- xử lý/chuyển tiếp
                 +-- đóng stream và giải phóng tài nguyên
~~~

Đây không phải một luật “mọi payload phải cực nhỏ”. Nếu listener xử lý trực tiếp một DTO vài KB, không có lý do buộc tạo remote storage round trip. Nguyên tắc là **payload chỉ mang phần dữ liệu cần thiết theo hợp đồng event**, còn binary data lớn nên dùng nơi lưu trữ thích hợp hoặc streaming.

### Không đặt entity JPA đang managed trong async event

~~~java
// Dễ gây vấn đề: giữ nguyên cả entity graph.
publisher.publishEvent(new OrderImported(orderEntity));
~~~

`OrderImported` là loại ví dụ do ứng dụng định nghĩa. Nếu entity chứa collections/lazy proxies, listener chạy sau khi transaction/session kết thúc có thể gặp `LazyInitializationException`. Một entity mutable còn có thể thay đổi sau publish, khiến listener đọc không đúng snapshot.

Chọn một DTO immutable với ID và các giá trị tối thiểu. Nếu cần dữ liệu chính xác tại lúc event xảy ra, có thể lưu **snapshot DTO đã chọn trường** hoặc một version trong storage; nếu chỉ có ID và listener reload tại lúc chạy, nó có thể thấy **trạng thái mới hơn** do aggregate thay đổi lần nữa. Cần xác định rõ semantics giữa “current state” và “state at event time”.

## 6. Immutable payload: đừng nhầm record với deep immutability

Ví dụ:

~~~java
public record BinaryEvent(String id, byte[] bytes) {}
~~~

`bytes` là final reference nhưng mảng vẫn mutable. Test/production có thể gặp race:

~~~java
byte[] original = {1, 2, 3};
BinaryEvent event = new BinaryEvent("E-1", original);
original[0] = 9;
// event.bytes()[0] đã trở thành 9 dù event record không đổi field.
~~~

Nếu payload thực sự cần snapshot bất biến, có thể defensive copy, nhưng copy dữ liệu lớn tốn bộ nhớ và CPU. Một ví dụ Java 17 độc lập minh họa:

File `DefensiveCopyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DefensiveCopyDemo {
    public record Snapshot(byte[] bytes) {
        public Snapshot {
            Objects.requireNonNull(bytes, "bytes");
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Snapshot snapshot = new Snapshot(input);
        input[0] = 9;

        byte[] someoneElse = snapshot.bytes();
        someoneElse[1] = 8;

        System.out.println(Arrays.toString(snapshot.bytes()));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout chính xác:

~~~text
[1, 2, 3]
~~~

Ở đây constructor copy dữ liệu một lần, accessor lại copy khi đọc. Đây là thiết kế an toàn cho **ví dụ mảng nhỏ**, nhưng với file hàng trăm MiB sẽ rất đắt. Khi không thể bảo đảm immutable với chi phí hợp lý, dùng **reference đến object bất biến trong storage**, hoặc API stream/transfer ownership có hợp đồng rõ, thay vì truyền mảng dùng chung rồi hy vọng không ai sửa.

## 7. Bounded executor: ngăn backlog giữ payload vô hạn

Một `ThreadPoolTaskExecutor` có thể cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity` và chính sách từ chối task. **Queue phải có giới hạn phù hợp với mức tải và payload**, không chỉ với số lượng request lý thuyết.

~~~java
@Configuration
@EnableAsync
class EventExecutorConfig {

    @Bean("largePayloadExecutor")
    ThreadPoolTaskExecutor largePayloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("large-event-");
        return pool;
    }
}
~~~

Đây là **trích đoạn cấu hình Spring**; cần import `@Configuration`, `@EnableAsync`, `@Bean` và `ThreadPoolTaskExecutor`. Khi listener được đánh dấu `@Async("largePayloadExecutor")`, method invocation sẽ đi qua pool này.

Với `ThreadPoolExecutor` nền tảng khi queue có capacity dương, behavior điển hình là: khởi tạo tới core workers, rồi enqueue; khi queue đầy mới tạo thêm threads tới max; khi cả threads và queue đầy, áp dụng rejection policy. Do vậy, **`maxPoolSize=20` nhưng queue rất lớn không đồng nghĩa hệ thống sẽ nhanh chóng chạy 20 workers**.

### Từ chối task không đồng nghĩa backpressure hoàn chỉnh

Khi executor không nhận thêm work, cần có **hợp đồng xử lý**:

- Task quan trọng nhưng không được mất: đừng chỉ dựa trên in-memory async events; lưu durable work/outbox rồi giao lại có kiểm soát.
- Task có thể bỏ: ghi nhận chỉ số dropped và nêu rõ policy; không dùng silent drop cho nghiệp vụ bắt buộc.
- Caller có thể tự điều tiết: rate limit, bounded semaphore, bounded ingestion queue, hoặc trả lỗi có thể retry với backoff.
- `CallerRunsPolicy`: có thể làm publisher tự chạy work để hãm tốc độ, nhưng **thay đổi thread, latency, transaction/security context semantics**. Phải test thật, không dùng tùy tiện.

Trong Spring, `TaskRejectedException` là một failure mode cần quan sát. Với `@Async` proxy, việc submit bị từ chối có thể khiến `publishEvent` ném exception ngay ở thời điểm scheduling, dù exception phát sinh **trong body của async listener** thì thường không lan ngược publisher. Hai trường hợp rất khác nhau.

## 8. Integration test Java 17+: xác minh cùng reference và queue giới hạn

Ví dụ này dùng Spring Framework, JUnit 5 và một `ThreadPoolTaskExecutor` **1 worker + 1 pending slot**. Ta tạo ba event payload riêng (mỗi event có mảng 1 MiB):

1. Event đầu vào worker và được chặn bởi `CountDownLatch`, chứng minh listener nhận **cùng mảng** mà publisher truyền vào.
2. Event thứ hai được xếp queue (queue size bằng 1).
3. Event thứ ba bị từ chối vì cả worker và queue đều đầy; test xác nhận `TaskRejectedException`.
4. Cuối test, release worker; cả event đầu và event thứ hai hoàn tất. Không có thao tác ép GC hoặc so sánh `Runtime.freeMemory()` vốn dễ flaky.

### 8.1. settings.gradle và build.gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'large-event-payload-tests'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.2. src/test/java/example/events/LargePayloadPressureTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(LargePayloadPressureTest.Config.class)
class LargePayloadPressureTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Probe probe;

    @Autowired
    @Qualifier("boundedPool")
    ThreadPoolTaskExecutor pool;

    @AfterEach
    void cleanup() {
        // Không giữ worker vô thời hạn nếu một assertion thất bại.
        probe.release.countDown();
    }

    @Test
    void queueIsBoundedAndListenerGetsOriginalPayload() throws Exception {
        byte[] firstBytes = new byte[1024 * 1024];

        try {
            publisher.publishEvent(
                new LargeEvent("first", firstBytes));

            assertTrue(probe.firstStarted.await(5, TimeUnit.SECONDS));

            // Listener thấy cùng byte[] reference; Spring không
            // tự deep-copy toàn bộ payload trước khi dispatch.
            assertSame(firstBytes, probe.firstPayload.get());

            publisher.publishEvent(
                new LargeEvent("second", new byte[1024 * 1024]));

            assertEquals(
                1,
                pool.getThreadPoolExecutor().getQueue().size()
            );

            assertThrows(
                TaskRejectedException.class,
                () -> publisher.publishEvent(
                    new LargeEvent("third", new byte[1024 * 1024]))
            );
        } finally {
            probe.release.countDown();
        }

        assertEquals(
            "first",
            probe.completed.poll(5, TimeUnit.SECONDS)
        );
        assertEquals(
            "second",
            probe.completed.poll(5, TimeUnit.SECONDS)
        );
    }

    record LargeEvent(String id, byte[] bytes) {}

    static class Probe {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final AtomicReference<byte[]> firstPayload = new AtomicReference<>();
        final BlockingQueue<String> completed =
            new LinkedBlockingQueue<>();
    }

    static class Listener {
        private final Probe probe;

        Listener(Probe probe) {
            this.probe = probe;
        }

        @Async("boundedPool")
        @EventListener
        public void onLarge(LargeEvent event) {
            if ("first".equals(event.id())) {
                probe.firstPayload.set(event.bytes());
                probe.firstStarted.countDown();

                try {
                    if (!probe.release.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("gate timeout");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
            }

            probe.completed.offer(event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config {
        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        Listener listener(Probe probe) {
            return new Listener(probe);
        }

        @Bean("boundedPool")
        ThreadPoolTaskExecutor boundedPool() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(1);
            pool.setThreadNamePrefix("bounded-events-");
            return pool;
        }
    }
}
~~~

### 8.3. Chạy test và hiểu đúng kết luận

Với Gradle wrapper trong project:

~~~bash
./gradlew test --tests "example.events.LargePayloadPressureTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.LargePayloadPressureTest"
~~~

Test mong đợi **PASS** trong mô hình `@Async` proxy + `ThreadPoolTaskExecutor` trên. Nó chứng minh **behavior về reference và giới hạn queue**, không đo heap chính xác hoặc cam kết rằng toàn hệ thống chỉ dùng tối đa 2 MiB. Event thứ ba đã được cấp phát ở caller trước khi submit thất bại; những reference khác bên ngoài executor vẫn có thể tồn tại.

Tại sao ví dụ dùng `1 worker + 1 queue slot`? Khi worker đầu đang chờ gate, task thứ hai chắc chắn nằm trong queue; task thứ ba không còn capacity. Test không phụ thuộc vào tốc độ CPU hoặc sleep tùy ý. Khi gate được release, hai event được xử lý, và JUnit kiểm tra ID theo thứ tự trên single worker.

**Giới hạn của test:** nó kiểm tra một executor và một listener, không đánh giá serialization, số listeners khác, JPA entity graph, retry or buffer bên ngoài, cũng không trực tiếp đo GC. Production cần load test và đo đạc bổ sung. Nếu đổi sang custom multicaster executor, cần viết test riêng cho cách xử lý rejected tasks của multicaster đó.

## 9. Theo dõi heap, queue và latency bằng chỉ số thực

Để biết áp lực bộ nhớ từ application events, chỉ `used heap` là chưa đủ. Cần kết hợp:

| Chỉ số | Giá trị quan sát | Vì sao quan trọng |
| --- | --- | --- |
| `queue.size` và `queue.remainingCapacity` | Pending tasks | Queue lớn có thể giữ event payload lâu |
| `activeCount`, `poolSize` | Số workers bận/đang có | Cho biết saturation và hiệu quả concurrency |
| Rejected submissions | Số lần overload | Phát hiện khi backpressure/rejection policy kích hoạt |
| Event processing latency | Thời gian xử lý thực | Tìm bottleneck listener/downstream |
| Queue wait time | Chênh lệch submit -> bắt đầu | Đo khả năng payload bị retention trước xử lý |
| Heap used, live set sau GC | Số byte còn sống | Phát hiện payload references tồn đọng |
| GC pause/time/allocation rate | Tác động GC | Phân biệt allocation spike và retention kéo dài |
| Event count/size percentiles | P50/P95/P99 của payload size | Nhận diện outliers, không chỉ trung bình |

Với `ThreadPoolTaskExecutor`, Spring cung cấp `getActiveCount()`, `getPoolSize()` và truy cập `getThreadPoolExecutor().getQueue()` cho introspection. Trong Spring Boot, có thể dùng Micrometer/Actuator hoặc công cụ metrics nội bộ để ghi nhận các chỉ số tương ứng, tùy cấu hình. Tránh gắn `eventId` hoặc `aggregateId` làm **metric tags** vì cardinality cao.

Trong JVM Java 17+, có thể dùng **Java Flight Recorder (JFR)**, GC logs, heap histogram hoặc heap dump phù hợp với môi trường để xác định các loại object và nơi allocation/retention. Heap dump có thể chứa dữ liệu nhạy cảm (payload, secrets); phải phân quyền, lưu trữ an toàn và xóa theo retention policy. `System.gc()` hoặc ép GC trong unit test không phải cách đáng tin để chứng minh đã giải phóng bộ nhớ.

### Thử nghiệm tải đơn giản

1. Đo baseline với event chỉ chứa ID.
2. Đo cùng throughput nhưng event mang thêm 1 MiB payload riêng biệt.
3. Giữ nguyên số workers, queue capacity và thời gian xử lý downstream.
4. Thu thập queue depth, enqueue rejections, processing latency, heap after GC và allocation rate.
5. So sánh P95/P99 latency và live heap thay vì chỉ một snapshot.
6. Lặp lại với id-only event + storage reference; tính cả chi phí I/O để đánh giá trade-off.

Không nên kết luận “một object 1 MiB được tạo tức là heap sẽ tăng bền vững 1 MiB” vì dữ liệu có thể được thu hồi ngay, chia sẻ, nén khác nhau hoặc nằm ngoài heap. Điều cần đo là **retained live object graph** trong kịch bản tải thật.

## 10. Payload lớn, transaction và async consistency

Event có payload lớn thường xuất hiện khi nghiệp vụ xử lý tài liệu, nhập dữ liệu hoặc báo cáo. Nếu publish bên trong `@Transactional`, một listener đồng bộ chạy lâu có thể kéo dài transaction, giữ lock và connection hơn mức cần thiết.

~~~text
BEGIN DB TRANSACTION
  UPDATE reports SET state='READY'
  publish ReportReady(large byte[])
      -> listener đồng bộ nén/đẩy file: 3 giây
  COMMIT
~~~

Trong luồng này, transaction còn mở trong thời gian listener đồng bộ xử lý. Đổi listener thành `@Async` có thể rút ngắn thời gian block publisher nhưng **không tự đảm bảo listener đọc được dữ liệu committed**: worker có thể chạy trước commit và thấy trạng thái cũ.

Nếu listener cần dữ liệu đã commit:

- Dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` với ngữ nghĩa rõ; nếu xử lý sau commit nặng, chuyển công việc sang executor phù hợp *sau* mốc commit.
- Nếu ý định xử lý không được phép mất khi process chết, dùng **transactional outbox/event publication registry** hoặc durable queue có retry và idempotency.
- Trong record gửi qua outbox, lưu **metadata/reference** tới object storage, không nhét toàn bộ file lớn vào một message/outbox row trừ khi đã tính chi phí DB/broker và yêu cầu retention.
- Bảo đảm file/object được lưu bền vững trước khi phát event trỏ tới nó; phối hợp lifecycle của file với DB transaction bằng quy trình compensation/cleanup có chủ đích khi failure xảy ra.

Không giả định `@Async` tự truyền JDBC transaction, `SecurityContextHolder` hoặc MDC sang worker. Nếu listener phải tái tải entity bằng ID, hãy mở transaction/authorization phù hợp trong công việc riêng.

## 11. Quản lý dữ liệu lớn qua storage và streaming

Một thiết kế dùng object store và event ID chỉ hiệu quả khi các tình huống sau được giải quyết:

| Khía cạnh | Câu hỏi thiết kế |
| --- | --- |
| Durability | Object được upload hoàn tất trước khi event có thể được xử lý chưa? |
| Visibility | Consumer có thấy object theo consistency và quyền truy cập của storage không? |
| Authorization | Ai được đọc objectKey, và truy cập theo service identity nào? |
| Lifetime | Object phải tồn tại bao lâu để retry, audit, replay? |
| Integrity | Có checksum/version để phát hiện object bị đổi? |
| Retry | Consumer đọc lại sau lỗi một cách idempotent thế nào? |
| Cleanup | Nếu transaction rollback hoặc delivery bị hủy, object mồ côi được dọn ra sao? |
| Streaming | Consumer có đọc theo chunk, giới hạn concurrent streams và đóng tài nguyên không? |

Ví dụ contract:

~~~java
public record ImageProcessed(
    String eventId,
    String imageId,
    String objectKey,
    long sizeBytes,
    String sha256,
    int schemaVersion
) { }
~~~

Đây là Java record độc lập, không chứa tệp gốc. Consumer kiểm tra ID, access control, object metadata, kích thước và checksum trước khi tiêu thụ. **Không coi `objectKey` hay một URL bất kỳ là bằng chứng quyền truy cập.**

Khi cần xử lý file lớn, ưu tiên `InputStream`, channel hoặc API reactive streaming theo khả năng backend, sử dụng buffer có kích thước được kiểm soát. Nhưng đừng đặt một `InputStream` mở sẵn trong application event rồi cho listener async đọc sau khi HTTP request kết thúc: stream có thể đã đóng, không an toàn khi dùng song song và không có khả năng replay.

## 12. Những lỗi thiết kế thường gặp

**1. Publish nguyên `byte[]` nhiều MiB vào executor queue không giới hạn.** Mỗi pending task giữ dữ liệu cho tới khi xử lý; heap có thể tăng theo backlog. Dùng event metadata nhỏ, queue bounded và chính sách overload.

**2. Cho rằng Spring tự deep-copy event.** `PayloadApplicationEvent` thường giữ reference đến payload object, không phải cơ chế clone. Nếu producer sửa mảng hoặc list sau publish, async consumer có thể thấy dữ liệu bị đổi. Thiết kế immutable hoặc snapshot có chủ đích.

**3. Chỉ tăng `-Xmx` để chữa backlog.** Heap lớn hơn có thể hoãn OOM nhưng không giải quyết tốc độ arrival vượt processing; GC/live set có thể tiếp tục tăng. Tìm bottleneck, đo queue depth và backpressure.

**4. Dùng `maxPoolSize` rất lớn nhưng queue cũng vô hạn.** Executor có thể ưu tiên enqueue khi core workers đang bận. Tăng max không chắc giúp dùng workers như mong đợi. Hiểu queueing strategy và test.

**5. Dùng `DiscardPolicy` cho event nghiệp vụ quan trọng.** Task có thể bị bỏ âm thầm; không có retry/durable log tự động. Chọn outbox/broker nếu không thể mất.

**6. Dùng `CallerRunsPolicy` mà quên transaction.** Khi pool đầy, một “async listener” có thể chạy trên caller thread; latency và khả năng exception/context thay đổi. Dùng khi hiểu rõ contract và đã test.

**7. Giữ `List<Entity>` hoặc lazy proxies trong event.** Có thể giữ cả persistence graph, gặp lỗi lazy loading sau transaction hoặc không phản ánh snapshot. Chọn ID, version và DTO nhỏ.

**8. Tạo bản sao nhiều tầng mà không đo.** Serialize sang JSON, encode Base64, log full payload, sau đó copy vào HTTP body tạo nhiều allocations. Dùng streaming/chunking và không log dữ liệu nhạy cảm.

**9. Nhầm queue capacity với giới hạn tổng byte.** Queue 100 phần tử có thể giữ vài KB hoặc hàng GiB tùy payload. Nếu payload size biến thiên lớn, cần thêm size quotas/byte-budget semaphore, không chỉ task count.

**10. Đo `Runtime.freeMemory()` trước/sau một event rồi suy kết luận.** JVM có GC/JIT/allocator hoạt động không xác định theo từng bước test; dùng load profiling, JFR, heap dump có phân tích và metrics.

**11. Gắn file stream mở trực tiếp vào event.** Async listener có thể chạy khi stream đóng hoặc nhiều listeners cùng đọc hết stream. Gửi durable key rồi mở stream ở consumer theo ownership rõ.

**12. Nói “event accepted” nghĩa là đã lưu bền vững.** `ApplicationEventPublisher` không cung cấp durable delivery. Nếu task bị reject, process chết hoặc consumer fail, công việc quan trọng cần thiết kế retry/outbox độc lập.

## 13. Checklist trước khi vận hành

- [ ] Event chứa dữ liệu tối thiểu cần thiết và định danh/version rõ ràng.
- [ ] Đã biết P50/P95/P99 kích thước payload và tỷ lệ event/giây.
- [ ] Đã đánh giá object graph được giữ bởi event/lambda/proxy, không chỉ shallow size.
- [ ] Event dùng chung object immutable hoặc defensive copy với chi phí đã được đo.
- [ ] Async executor có queue capacity hữu hạn và overload policy rõ ràng.
- [ ] Rejection, queue wait time, active workers, heap/GC được giám sát.
- [ ] Không dựa vào việc tăng heap hoặc max threads như giải pháp duy nhất.
- [ ] Với data lớn, có storage reference, integrity, authorization, cleanup và retry.
- [ ] Không đưa JPA entity graph, HTTP request stream hoặc credentials vào event.
- [ ] Không dùng log serialization làm phình payload hoặc lộ dữ liệu nhạy cảm.
- [ ] Có test queue saturation/rejection và test async behavior thật.
- [ ] Có load test mô phỏng peak throughput và slow downstream.
- [ ] Với nghiệp vụ cần delivery chắc chắn, có outbox/durable queue và idempotency.
- [ ] Không suy việc listener chạy xong đồng nghĩa DB transaction nguồn đã commit.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao gọi `publishEvent` xong không đồng nghĩa payload lớn đã được GC?

Vì executor queue, listener, future hoặc một reference khác vẫn có thể giữ event và object graph. Spring không tự xóa mọi strong reference khi publisher trả về.

**Câu 2:** Một queue 200 phần tử có luôn dùng bộ nhớ cố định không?

Không. Memory retention phụ thuộc payload của từng task, số object khác biệt và sharing. Nếu mỗi task giữ một `byte[]` 4 MiB riêng thì chỉ riêng các mảng đã có thể xấp xỉ 800 MiB.

**Câu 3:** Record `record BigEvent(byte[] data) {}` có immutable sâu không?

Không. Record giữ field reference final nhưng nội dung mảng mutable. Defensive copy có thể tạo snapshot, song tốn thêm allocation/CPU; với data rất lớn nên cân nhắc storage reference.

**Câu 4:** `maxPoolSize` lớn nhưng queueCapacity lớn có giúp mọi worker chạy ngay không?

Không nhất thiết. Trong queueing strategy nền tảng, tasks thường vào queue sau khi core workers bận; max workers chỉ mở rộng khi queue đầy. Cần test dưới tải.

**Câu 5:** Bounded queue có đồng nghĩa “không thể OOM” không?

Không. Nó chỉ giới hạn số pending tasks của executor đó; data còn có thể ở caller, các executor khác, object graph, serialization buffers và các hệ thống liên quan. Cũng cần giới hạn bytes/throughput.

**Câu 6:** Vì sao không đẩy file PDF thẳng qua event và cho async listener xử lý?

Nó giữ binary data trong heap và queue lâu hơn; nếu process chết, payload in-memory mất. Khi phù hợp, lưu file bền vững và publish event nhỏ chứa storage key, version, checksum, rồi stream từ nơi lưu.

**Câu 7:** Khi nào dùng after-commit và outbox?

After-commit gắn xử lý với kết quả transaction; outbox/registry bền vững cần khi ý định gửi không được mất giữa commit và xử lý async/downstream. Cả hai không tự giải quyết bài toán kích thước payload; nên dùng event metadata nhỏ.

**Ghi nhớ:** tối ưu payload trong Spring Application Events nghĩa là kiểm soát **kích thước object graph × số event outstanding × thời gian retention**, cùng giới hạn queue và có chính sách quá tải rõ. Đối với binary data lớn, **truyền định danh/tham chiếu bền vững và xử lý theo luồng** thường dễ kiểm soát heap hơn là giữ toàn bộ dữ liệu trong event object.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Application Events và asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — PayloadApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Oracle JDK 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
