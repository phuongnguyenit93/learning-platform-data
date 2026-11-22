# Listener chậm làm nghẽn publisher trong Spring Application Events

## 1. Hiện tượng và mục tiêu

Trong Spring Framework Application Events, một `ApplicationEventPublisher` có thể gửi sự kiện cho nhiều listener trong cùng `ApplicationContext`. Cách này giúp giảm phụ thuộc trực tiếp giữa các module, nhưng rất dễ gặp vấn đề hiệu năng nếu **một listener làm công việc chậm hoặc chặn thread**.

Ví dụ:

- Use case `placeOrder()` lưu đơn hàng rồi gọi `publisher.publishEvent(new OrderPlaced(...))`.
- `@EventListener` thứ nhất chỉ ghi audit trong vài mili giây.
- `@EventListener` thứ hai gọi API đối tác hoặc gửi email và phải chờ nhiều giây.
- HTTP request, message consumer hoặc service đang publish **chưa thể tiếp tục** cho tới khi các listener đồng bộ hoàn tất.

Điều đáng chú ý: Spring Framework mặc định xử lý application events **đồng bộ trên thread phát event**. Do đó, `publishEvent()` không luôn là lời gọi “fire-and-forget”. Trong cấu hình mặc định, chính listener chậm có thể kéo dài thời gian phản hồi hoặc chiếm worker của publisher.

Bài học giúp bạn:

1. Hiểu vì sao `SimpleApplicationEventMulticaster` mặc định khiến `publishEvent()` chờ.
2. Nhận diện listener chậm, sự khác biệt giữa xử lý **đồng bộ**, **`@Async`** và multicaster có executor.
3. Tách tác vụ chậm mà không nhầm async với bảo đảm giao hàng bền vững.
4. Cấu hình `ThreadPoolTaskExecutor`, queue capacity, rejection và backpressure đúng đắn.
5. Hiểu tác động lên transaction, error propagation, context và thứ tự listener.
6. Chạy chương trình Java 17+ có `CountDownLatch` chứng minh publisher bị chặn trước khi listener hoàn tất, rồi đối chiếu với listener `@Async`.
7. Thiết kế metrics, test và checklist xử lý nghẽn trong production.

## 2. Cơ chế mặc định: listener xử lý trên publisher thread

Spring cung cấp `org.springframework.context.ApplicationEventPublisher`. Bean có thể inject giao diện này và phát event:

~~~java
// Minh họa bên trong một Spring-managed service.
publisher.publishEvent(new OrderPlaced(orderId));
~~~

Một method listener tương ứng:

~~~java
// Minh họa trong một Spring bean.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    paymentGateway.notifyPartner(event.orderId()); // Có thể block.
}
~~~

Khi không cấu hình executor cho multicaster và không bật `@Async` trên listener, `SimpleApplicationEventMulticaster` mặc định gọi callback trên **thread đang publish**. Sơ đồ:

~~~text
HTTP request thread / consumer thread
   |
   +-- service.placeOrder()
         |
         +-- thay đổi dữ liệu nghiệp vụ
         +-- publisher.publishEvent(OrderPlaced)
               |
               +-- Listener A: ghi log           [nhanh]
               +-- Listener B: gọi API đối tác   [chờ I/O]
               +-- Listener C: cập nhật cache   [nhanh]
         |
         +-- publishEvent trả về sau các listener đồng bộ
         +-- service tiếp tục / return response
~~~

Trong một dispatch đồng bộ với một thread, listener tiếp theo còn có thể phải đợi listener trước kết thúc. Thứ tự gọi listener mặc định phụ thuộc vào cấu hình và các annotation như `@Order`; nhưng **thay đổi thứ tự không loại bỏ tổng thời gian chờ** nếu vẫn có listener chậm.

Theo tài liệu Spring Framework 6.2, listener mặc định nhận event đồng bộ và `publishEvent()` có thể phải đợi tất cả listener hoàn tất. Lưu ý đây là **hành vi của cấu hình mặc định**, không phải cam kết mọi `ApplicationEventPublisher` luôn đồng bộ: chính API `publishEvent` mô tả thao tác handoff sang multicaster và implementation có thể dùng chiến lược khác.

### 2.1. Vì sao một listener chậm ảnh hưởng nhiều nơi?

Nếu publisher là HTTP request thread, thời gian handler giữ thread tăng, kéo dài response latency và có thể giảm số request mà server xử lý đồng thời.

Nếu publisher nằm trong một `@Transactional` service, thời gian xử lý listener đồng bộ có thể làm transaction mở lâu hơn, giữ connection, lock và tài nguyên liên quan; từ đó tăng nguy cơ contention và timeout.

Nếu publisher là message consumer với concurrency giới hạn, listener chậm có thể giữ consumer thread, làm backlog của topic/queue tăng.

Nếu một event được phát trong startup/shutdown lifecycle, callback chậm còn có thể trì hoãn ứng dụng chuyển sang giai đoạn tiếp theo. Cần tránh I/O chặn dài trong các listener lifecycle nhạy cảm.

## 3. Phân tích thời gian và khả năng thông qua

Giả sử một luồng publisher xử lý tuần tự:

~~~text
business work:  20 ms
listener A:      5 ms
listener B:    250 ms
listener C:     10 ms
-----------------------
thời gian xấp xỉ: 285 ms
~~~

Trong cấu hình đồng bộ và không có I/O chồng lấp, tổng thời gian một request gần bằng thời gian nghiệp vụ cộng thời gian của các listener. Chỉ một callback 250 ms đã chiếm phần lớn latency.

Nếu một publisher thread chỉ xử lý được một request tại một thời điểm, khả năng phục vụ tối đa của riêng thread đó xấp xỉ nghịch đảo thời gian xử lý một request; tuy nhiên **không được kết luận toàn hệ thống chỉ có một thread hay throughput cố định**, vì web server/consumer có nhiều threads, contention, kết nối DB và tải thực tế khác nhau.

Với N publisher threads, việc giữ mỗi thread thêm vài trăm mili giây vẫn có thể làm giảm concurrency hiệu dụng. Cần đánh giá bằng throughput, percentile latency (p95/p99), active threads và backlog, chứ không chỉ nhìn CPU trung bình.

### 3.1. Listener chậm không chỉ vì `Thread.sleep()`

Các nguyên nhân thực tế:

- HTTP client không có connect/read timeout hoặc timeout quá lớn.
- JDBC query chậm, lock wait, pool connections cạn.
- DNS resolution, SMTP, object storage hoặc API bên ngoài không ổn định.
- Listener thực hiện khối lượng CPU lớn trên publisher thread.
- Listener gọi `Future.get()`, `CountDownLatch.await()` hoặc lock đang bị giữ lâu.
- Listener mở nested transaction hoặc truy cập một service có contention.
- Event quá lớn và listener deserialize/serialize dữ liệu phức tạp.
- Listener phát event mới và tạo một chuỗi callback sâu hoặc nhiều nhánh (fan-out).

**`Thread.sleep()` chỉ nên xuất hiện trong demo mô phỏng**, không được dùng để “chữa” nghẽn. Trong bài này, ví dụ dùng latch để tạo điểm chờ có kiểm soát mà không phụ thuộc tốc độ của máy.

## 4. Các lựa chọn để tránh chặn publisher

Có nhiều hướng xử lý, không phải trường hợp nào cũng nên chuyển sang async.

| Cách làm | Hiệu ứng | Phù hợp khi | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| Tối ưu listener đồng bộ | Giảm thời gian trong `publishEvent()` | Callback bắt buộc nằm trong flow/transaction | Caller vẫn phải đợi |
| `@Async @EventListener` | Tác vụ listener chạy trên executor riêng | Một vài listener tốn I/O, không cần caller chờ hoàn tất | Queue, rejection, lỗi async, context khác thread |
| Multicaster có `TaskExecutor` | Có thể chuyển nhiều listeners sang worker | Thiết kế chung yêu cầu async dispatch | Ảnh hưởng toàn context, semantics transaction/order |
| Ghi job/outbox rồi xử lý sau | Giữ quyết định xử lý bền vững | Side effect quan trọng, cần retry sau crash | Phải có worker, trạng thái, idempotency |
| Thực hiện một service call trực tiếp | Duy trì hợp đồng đồng bộ rõ ràng | Kết quả listener quyết định response/rollback | Vẫn chịu latency nhưng minh bạch hơn |
| Batch/coalesce/deduplicate | Giảm lượng công việc trên mỗi event | Các cập nhật lặp/không cần từng thay đổi nhỏ | Cần thiết kế semantics và chống mất thay đổi |

**Nguyên tắc:** nếu tác vụ là điều kiện bắt buộc để use case thành công, chuyển nó sang `@Async` có thể làm sai hợp đồng nghiệp vụ. Phải quyết định trước **caller cần biết kết quả xử lý hay không**, sau đó mới chọn cơ chế.

## 5. `@Async @EventListener`: tách một listener chậm

Ví dụ:

~~~java
// Minh họa trong một Spring-managed bean.
@Async("notificationExecutor")
@EventListener
public void notifyPartner(OrderPlaced event) {
    partnerClient.notify(event.orderId());
}
~~~

Cấu hình cần `@EnableAsync` và một executor tên `notificationExecutor`. Với Spring AOP, `@Async` chuyển lời gọi method qua proxy/async interceptor để schedule task.

Khi cấu hình đúng:

1. Publisher vẫn gọi multicaster, multicaster vẫn xác định listener nào nhận event.
2. Invocation của listener async được schedule lên executor.
3. Publisher không đợi phần thân listener async hoàn thành, nhưng vẫn phải hoàn tất **thao tác submit** vào executor; thao tác này có thể thất bại hoặc chịu áp lực do overload.
4. Worker xử lý event sau, có thể khi HTTP request đã trả response hoặc transaction của publisher đã kết thúc.

### 5.1. Không đồng nhất `@Async` với không bao giờ block

- Executor có hàng đợi đầy sẽ **reject task** hoặc áp dụng policy dự phòng. Nếu policy là `CallerRunsPolicy`, một tác vụ bị từ chối có thể được chạy **ngay trên thread submit**, khiến publisher bị chặn trở lại.
- Scheduling có overhead, lock, context capture và tương tác với thread pool; thời gian gọi không luôn bằng 0.
- Nếu listener làm việc bất đồng bộ nhưng code khác gọi `Future.get()` để đợi trong publisher, nghẽn có thể quay trở lại.
- Nếu một listener đồng bộ khác vẫn chậm, `publishEvent()` vẫn chờ listener ấy; thêm `@Async` cho một callback không làm mọi callback khác async.

### 5.2. Exception và return value

Với listener đồng bộ mặc định, exception có thể lan ngược về `publishEvent()` (trừ khi error handler xử lý), làm use case/transaction lỗi.

Với `@Async @EventListener`, exception trong body không tự quay về publisher thread. Với method `void`, hãy cấu hình `AsyncUncaughtExceptionHandler`, logging, metrics và cơ chế retry phù hợp. Nếu muốn tác vụ có trạng thái hoàn thành để điều phối, sử dụng abstraction có acknowledgment phù hợp; đừng coi publisher `void` là một `Future` hoàn thành nghiệp vụ.

Một `@EventListener` đồng bộ được phép tạo event tiếp theo bằng **return value**. Listener `@Async` không hỗ trợ publish subsequent event bằng return value theo hợp đồng Spring; nếu cần tạo event mới từ worker, inject `ApplicationEventPublisher` và gọi `publishEvent` tường minh.

## 6. Ví dụ chạy được: chứng minh sync chặn, async không đợi listener

Dự án sử dụng **Java 17+**, Maven và **Spring Framework 6.2.12**; không cần Spring Boot, HTTP server hoặc database.

Hai event khác kiểu giúp độc lập:

- `SyncWork` có listener **đồng bộ** giữ ở `syncRelease`.
- `AsyncWork` có `@Async("eventExecutor")` listener giữ ở `asyncRelease`.

Main dùng một thread riêng để gọi `context.publishEvent(...)`; nhờ đó có thể kiểm tra thread publisher đã hoàn thành hay chưa. `CountDownLatch` cho phép quan sát điểm chờ, không cần đo thời gian bằng `System.currentTimeMillis` hay `Thread.sleep()`.

### 6.1. Cấu trúc

~~~text
slow-listener-demo/
├── pom.xml
└── src/main/java/demo/SlowListenerDemo.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>slow-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. `src/main/java/demo/SlowListenerDemo.java`

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SlowListenerDemo {

    // Java 17 records: event payload là POJO không cần extends ApplicationEvent.
    public record SyncWork(String id) {}
    public record AsyncWork(String id) {}

    public static final class Gates {
        final CountDownLatch syncEntered = new CountDownLatch(1);
        final CountDownLatch syncRelease = new CountDownLatch(1);
        final CountDownLatch asyncEntered = new CountDownLatch(1);
        final CountDownLatch asyncRelease = new CountDownLatch(1);
        final CountDownLatch asyncFinished = new CountDownLatch(1);
    }

    private static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Listener was interrupted", e);
        }
    }

    private static void awaitWithTimeout(
            CountDownLatch latch, String name) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out: " + name);
        }
    }

    public static final class SlowSyncListener {
        private final Gates gates;

        public SlowSyncListener(Gates gates) {
            this.gates = gates;
        }

        @EventListener
        public void onSync(SyncWork event) {
            gates.syncEntered.countDown();
            awaitRelease(gates.syncRelease);
        }
    }

    public static class SlowAsyncListener {
        private final Gates gates;

        public SlowAsyncListener(Gates gates) {
            this.gates = gates;
        }

        @Async("eventExecutor")
        @EventListener
        public void onAsync(AsyncWork event) {
            try {
                gates.asyncEntered.countDown();
                awaitRelease(gates.asyncRelease);
            } finally {
                gates.asyncFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean
        public SlowSyncListener slowSyncListener(Gates gates) {
            return new SlowSyncListener(gates);
        }

        @Bean
        public SlowAsyncListener slowAsyncListener(Gates gates) {
            return new SlowAsyncListener(gates);
        }

        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-worker-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService publisherThread =
                Executors.newSingleThreadExecutor();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Gates gates = context.getBean(Gates.class);

            try {
                Future<?> syncPublish = publisherThread.submit(
                    () -> context.publishEvent(new SyncWork("s1")));

                awaitWithTimeout(gates.syncEntered, "sync listener start");

                // Listener đã vào nhưng chưa có tín hiệu release.
                if (syncPublish.isDone()) {
                    throw new AssertionError(
                        "Synchronous publisher returned too early");
                }
                System.out.println("sync-publisher-blocked=true");

                gates.syncRelease.countDown();
                syncPublish.get(5, TimeUnit.SECONDS);
                System.out.println(
                    "sync-publisher-returned-after-release=true");

                Future<?> asyncPublish = publisherThread.submit(
                    () -> context.publishEvent(new AsyncWork("a1")));

                // Worker đang ở trong listener và chờ release.
                awaitWithTimeout(gates.asyncEntered, "async listener start");

                // Future publisher hoàn thành khi task đã được schedule,
                // KHÔNG cần listener async được release.
                asyncPublish.get(5, TimeUnit.SECONDS);
                System.out.println(
                    "async-publisher-returned-before-release=true");

                boolean finishedEarly =
                        gates.asyncFinished.getCount() == 0L;
                if (finishedEarly) {
                    throw new AssertionError(
                        "Async listener finished before release");
                }
                System.out.println(
                    "async-listener-finished-before-release=false");

                gates.asyncRelease.countDown();
                awaitWithTimeout(
                        gates.asyncFinished, "async listener finish");
                System.out.println(
                    "async-listener-finished-after-release=true");
            } finally {
                // Đảm bảo không treo worker nếu test assertion thất bại.
                gates.syncRelease.countDown();
                gates.asyncRelease.countDown();
            }
        } finally {
            publisherThread.shutdownNow();
        }
    }
}
~~~

Chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SlowListenerDemo
~~~

Năm dòng do **chính chương trình** in ra nếu các điều kiện được kiểm chứng:

~~~text
sync-publisher-blocked=true
sync-publisher-returned-after-release=true
async-publisher-returned-before-release=true
async-listener-finished-before-release=false
async-listener-finished-after-release=true
~~~

Maven/Spring có thể in log khác; output trên là năm dòng `System.out.println` của ví dụ. Không có timing assertion kiểu “phải chạy dưới 10 ms”. Các `await(..., 5, TimeUnit.SECONDS)` đóng vai trò **timeout để test không treo mãi**, không phải thước đo latency production.

### 6.4. Phân tích chính xác từng giai đoạn

**Đường đồng bộ:**

1. Main submit lời gọi `publishEvent(SyncWork)` sang `publisherThread`.
2. `SlowSyncListener` chạy **trực tiếp trên thread publish**, phát tín hiệu `syncEntered`, rồi đợi `syncRelease`.
3. Sau khi nhận `syncEntered`, main kiểm tra `syncPublish.isDone() == false`. Điều này chứng minh publisher **đang bị listener chặn**.
4. Main gọi `syncRelease.countDown()`; listener kết thúc; lời gọi `publishEvent` mới hoàn thành.
5. `Future.get(...)` trả về, main in `sync-publisher-returned-after-release=true`.

**Đường bất đồng bộ:**

1. Main submit `publishEvent(AsyncWork)` vào chính `publisherThread`.
2. `@Async` chuyển body của `SlowAsyncListener` sang `eventExecutor`.
3. Worker phát tín hiệu `asyncEntered` rồi đợi `asyncRelease`.
4. Main gọi `asyncPublish.get(...)` **khi worker vẫn đang bị giữ**, và lời gọi publisher vẫn hoàn tất: chứng minh publisher không cần chờ thân listener.
5. Trước release, `asyncFinished` chưa được count down; main in `async-listener-finished-before-release=false`.
6. Sau release, worker kết thúc và count down latch trong `finally`; main đợi rồi in `async-listener-finished-after-release=true`.

Hai loại event riêng biệt tránh việc một listener đồng bộ khác làm lẫn kết quả của `AsyncWork`. Executor được Spring quản lý và shutdown trong lifecycle context; `finally` mở các latch nếu có assertion thất bại.

**Giới hạn kiểm thử:** ví dụ dùng executor nhỏ và event có chủ đích để chứng minh semantics; không mô phỏng saturation hoặc benchmark throughput. Phần code đã được rà soát theo API Spring 6.2.12, nhưng output ở đây là dự kiến từ logic, không phải kết quả một lần chạy Maven đã được thực hiện.

## 7. Phương án khác: gắn executor cho `applicationEventMulticaster`

Có thể cấu hình bean có tên đặc biệt `applicationEventMulticaster` để multicaster dispatch các listener hỗ trợ async bằng `TaskExecutor`:

~~~java
// Snippet minh họa trong @Configuration, không phải file độc lập.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Ưu điểm: nhiều listeners thông thường có thể được schedule bất đồng bộ mà không thêm `@Async` từng method. Tuy nhiên, nó thay đổi **hành vi toàn ApplicationContext**: listener trước đây đồng bộ giờ có thể chạy thread khác, ordering và exception propagation thay đổi, và các thread-bound contexts không tự được truyền.

**Ngoại lệ rất quan trọng:** `ApplicationListener.supportsAsyncExecution() == false` buộc một listener chạy trên publisher thread dù multicaster có executor. Các transaction-synchronized listeners, ví dụ listener do `@TransactionalEventListener` tạo ra, cần đăng ký synchronization trên thread có transaction; không thể suy ra tất cả listeners đều được đưa vào pool.

Nếu chỉ một vài business listeners chậm, `@Async("namedExecutor")` thường cho phép thay đổi có phạm vi nhỏ và dễ kiểm thử hơn. Đừng bật async global để che tất cả vấn đề performance khi chưa đánh giá tác động đến correctness.

## 8. Thiết kế `ThreadPoolTaskExecutor` và backpressure

Chuyển chỗ làm việc chậm từ publisher thread sang pool khác giúp giảm thời gian giữ publisher thread **khi có đủ capacity**, nhưng tác vụ vẫn tiêu tốn CPU, network, DB và memory.

Ví dụ cấu hình minh họa:

~~~java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("notification-");

    // Executor sẽ từ chối task khi đã bão hòa thay vì nhận vô hạn.
    // Không chọn CallerRunsPolicy trừ khi cố ý muốn backpressure lên caller.
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
    return executor;
}
~~~

Đoạn trên là **snippet** trong Spring configuration, cần import `ThreadPoolTaskExecutor` và `java.util.concurrent.ThreadPoolExecutor`. Con số là ví dụ, **không phải cấu hình tối ưu cho mọi ứng dụng**.

### 8.1. Core pool, max pool và queue

- `corePoolSize`: số worker cốt lõi.
- `maxPoolSize`: trần worker có thể tăng lên khi policy của queue cho phép.
- `queueCapacity`: số task đợi được phép giữ; nên đặt **hữu hạn** khi cần kiểm soát memory/backpressure.
- `threadNamePrefix`: giúp debug và đo metrics.
- Rejection policy: quyết định điều gì xảy ra khi pool và queue không thể nhận thêm task.

Với `ThreadPoolTaskExecutor` và một hàng đợi có capacity dương, executor thường dùng core threads trước, sau đó xếp hàng; **chỉ khi queue đầy mới cần tăng thread vượt core** (tới max). Vì vậy, đặt queue quá lớn có thể khiến max pool hiếm khi được dùng, task chờ lâu trong khi CPU rảnh trên những thread chưa mở.

### 8.2. Rejection không phải lỗi có thể bỏ qua

Nếu queue đầy, việc submit có thể ném `TaskRejectedException` (hoặc được wrap/translate từ `RejectedExecutionException`). Một event “đã publish” nhưng callback async **không được schedule** là tình huống cần chính sách rõ ràng.

Các lựa chọn:

- **Fail fast:** publisher nhận lỗi submit và caller chọn retry/rollback/response phù hợp.
- **CallerRunsPolicy:** task được chạy trên thread submit khi executor bão hòa; gây **backpressure đồng bộ** — cố ý hay không, nó lại làm publisher chờ.
- **Bounded retry/durable queue:** nếu side effect quan trọng, ghi ý định xử lý vào storage/outbox và cho worker bền vững retry.
- **Drop/coalesce** chỉ với dữ liệu có thể mất theo hợp đồng (ví dụ một số metrics), có đo lường sự mất mát.
- **Giảm tốc producer** bằng rate limit hoặc concurrency limit thay vì chỉ tăng queue.

**Không dùng hàng đợi vô hạn như cách “sửa throughput”**: nó chỉ đổi latency thành memory và backlog cho đến khi cạn tài nguyên.

### 8.3. Ước lượng capacity

Giả sử listener mất trung bình 200 ms một task và có 4 worker liên tục bận. Trong điều kiện đơn giản không có overhead/contension, pool phục vụ khoảng `4 / 0,2 = 20 task/giây`. Nếu producer gửi 50 event/giây lâu dài, backlog tăng khoảng 30 task/giây. Một queue hữu hạn sớm muộn cũng đầy.

Con số này chỉ để giải thích cơ chế; capacity thực phụ thuộc phân bố thời gian xử lý, I/O concurrency, retry, fan-out, lock và hạ tầng. Đo p95/p99 thay vì chỉ dùng mean.

## 9. Transaction, consistency và độ bền

### 9.1. Listener đồng bộ chạy trong transaction của publisher

Ví dụ application service:

~~~java
// Minh họa trong Spring-managed bean.
@Transactional
public void submitOrder(long orderId) {
    repository.insertOrder(orderId);
    publisher.publishEvent(new OrderSubmitted(orderId));
}
~~~

Với multicaster mặc định đồng bộ, listener thông thường chạy ngay trong `publishEvent` và **có thể tham gia transaction thread-bound** của publisher. Nếu listener gọi API chậm, giao dịch có thể bị kéo dài. Nếu callback đồng bộ ném RuntimeException, exception có thể làm transaction rollback theo quy tắc hiện hành.

Đừng “sửa” bằng cách đưa một invariant nghiệp vụ quan trọng sang async rồi trả response thành công dù nghiệp vụ chưa hoàn tất.

### 9.2. Listener async không tự có transaction cũ

Với `@Async`, body chạy thread khác nên không tự tham gia transaction thread-bound của publisher. Khi worker bắt đầu, transaction chính có thể còn mở hoặc đã kết thúc. Worker đọc database từ connection khác có thể **chưa thấy dữ liệu chưa commit**.

Nếu tác vụ chỉ nên bắt đầu sau commit, lựa chọn phù hợp là `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; với tác vụ cần offload sau commit, có thể kết hợp `@Async` theo thiết kế và kiểm tra đúng transaction semantics. Một callback async cần ghi DB thường phải mở transaction **riêng**, ví dụ service khác có `@Transactional` qua proxy.

`@TransactionalEventListener` mặc định bỏ qua event ngoài transaction nếu `fallbackExecution=false`. Nó cũng không tự giải quyết độ bền hoặc retry nếu JVM chết sau commit.

### 9.3. `AFTER_COMMIT` không phải reliable queue

Một callback sau commit trong JVM có thể không kịp chạy nếu process crash. Nếu business side effect bắt buộc phải thực hiện, dùng **transactional outbox**: ghi record outbox **trong cùng transaction với trạng thái nghiệp vụ**, commit nguyên tử, sau đó worker/relay gửi message và retry khi có lỗi.

~~~text
BEGIN TRANSACTION
    INSERT order state
    INSERT outbox event
COMMIT
    |
    +-- relay đọc outbox
          +-- gửi message, retry, observability
          +-- consumer idempotent
~~~

Outbox giúp lưu bền vững **ý định gửi**, không tự đảm bảo exactly-once end-to-end. Duplicate có thể xuất hiện khi relay gửi thành công nhưng chưa cập nhật trạng thái; consumer cần `eventId` và idempotency.

## 10. Error handling và isolation giữa listeners

Trong multicaster đồng bộ, exception từ listener có thể **dừng dispatch** và lan về publisher nếu không có error handler tùy chỉnh. Đây có thể là hành vi mong muốn nếu listener là một bước bắt buộc của use case; nhưng nếu listener chỉ ghi metrics, một lỗi metrics không nên nhất thiết làm rollback đơn hàng.

Spring `SimpleApplicationEventMulticaster` hỗ trợ `setErrorHandler(...)`. Cần cân nhắc không nuốt lỗi một cách mù quáng:

~~~java
// Minh họa: chỉ nên dùng cho side effect không quyết định use case.
multicaster.setErrorHandler(error ->
        logger.error("Application event listener failed", error));
~~~

Nếu chọn handler không ném lại, lỗi callback có thể không còn lan về publisher. Điều này **thay đổi chính sách lỗi**, không chỉ cải thiện hiệu năng. Đối với những side effect quan trọng, cần retry/queue hoặc orchestration tường minh và có trách nhiệm xử lý thất bại.

Với `@Async @EventListener` trả `void`, exception được xử lý theo cơ chế async của Spring, không tự lan về thread publisher. Thiết lập `AsyncUncaughtExceptionHandler`, log event ID, correlation ID và dashboard cho số task lỗi. Với global multicaster executor, error handler và `TaskExecutor` có vai trò khác nhau; kiểm thử chính xác ranh giới nơi lỗi được nhận.

## 11. ThreadLocal, MDC và security khi tách thread

Chuyển listener sang executor còn làm thay đổi context:

- `ThreadLocal` tùy chỉnh thường không tự sang worker.
- MDC/tracing/observation context có thể bị mất nếu không có propagation.
- `SecurityContextHolder` dạng ThreadLocal cần cơ chế security-aware executor khi thực sự phải mang principal.
- `TransactionSynchronizationManager` **không được copy nguyên transaction resource** sang worker.
- HTTP request có thể đã kết thúc khi worker xử lý; không truyền `HttpServletRequest` đang sống như payload.

Có thể đưa `traceId`, `orderId`, `tenantId` và dữ liệu cần thiết vào event payload một cách tường minh. Với logging/observation, Spring cung cấp `ContextPropagatingTaskDecorator` kết hợp Micrometer Context Propagation nếu accessor được cấu hình phù hợp.

**Chú ý bảo mật:** correlation/tenant ID trong event hoặc MDC không tự xác thực quyền truy cập. Listener phải kiểm tra authorization/tenant boundary đúng hệ thống.

## 12. `@Order` và fan-out không giải quyết nghẽn

Spring cho phép `@Order` để điều chỉnh ưu tiên gọi listener:

~~~java
// Minh họa trong Spring bean.
@Order(10)
@EventListener
public void first(OrderPlaced event) { /* ... */ }

@Order(20)
@EventListener
public void second(OrderPlaced event) { /* ... */ }
~~~

Khi cả hai đồng bộ, publisher vẫn phải đợi các callback; đổi thứ tự chỉ thay callback nào được gọi trước. Khi listener async, `@Order` **không bảo đảm thứ tự hoàn tất** task. Nếu bước B thật sự phụ thuộc kết quả bước A, dùng workflow/orchestrator hoặc pipeline có acknowledgment, không chỉ dựa vào thứ tự event subscribers.

Fan-out cũng cần kiểm soát. Một event kích hoạt mười callback đồng bộ có thể giữ publisher lâu hơn một callback, nhất là nếu mỗi listener đều gọi I/O bên ngoài. Không nên phát thêm nhiều event con tùy ý nếu không có điểm dừng, hop limit hoặc state machine; event storm có thể gây nghẽn dù mỗi callback riêng lẻ khá nhanh.

## 13. Khi nào nên giữ listener đồng bộ?

Async không phải đáp án mặc định. Có các tác vụ nên được giữ đồng bộ:

- Kiểm tra invariant bắt buộc trước khi use case trả về.
- Cập nhật trạng thái cùng transaction nếu kết quả phải atomic với nghiệp vụ.
- Xử lý rất nhanh, xác định, không cần external I/O và không làm tăng latency đáng kể.
- Công việc mà caller phải biết lỗi ngay để trả response hợp lệ.

Tuy nhiên, nếu đó thật sự là business logic quyết định thành công use case, một **service call tường minh** có thể rõ hợp đồng hơn một event listener ẩn. Event thường phù hợp khi downstream reaction có thể tách khỏi quyết định chính.

Ngược lại, email, analytics, cache refresh hoặc gọi một API bên ngoài có thể tách nếu nghiệp vụ cho phép; nhưng phải quyết định xử lý retry, idempotency và thất bại thực tế chứ không chỉ “đánh dấu async”.

## 14. Chẩn đoán nghẽn trong production

### 14.1. Dấu hiệu

- p95/p99 HTTP latency tăng đúng lúc lưu lượng event tăng.
- Request worker threads bị chiếm và xuất hiện nhiều stack frames trong `@EventListener`, HTTP client hoặc JDBC.
- Thread dump cho thấy publisher thread đang đợi I/O trong listener.
- Transaction duration, DB lock waits, connection utilization tăng.
- Consumer lag/backlog tăng, dù không thấy sự cố trực tiếp ở publisher.
- Với async, executor `activeCount` cao, `queueSize` tăng, rejected tasks và timeout tăng.

### 14.2. Thu thập bằng chứng

1. Xác định event type và mọi listener được đăng ký.
2. Đo **thời gian từ trước tới sau `publishEvent`** ở caller bằng timer/observation phù hợp.
3. Đo thời gian xử lý riêng của listener chậm; tách thời gian I/O, DB, CPU, queue và retry.
4. Lấy thread dump trong lúc chậm để thấy stack publisher và worker.
5. Kiểm tra multicaster có bean `applicationEventMulticaster` custom không và executor thực tế được dùng.
6. Kiểm tra `@Async` có hoạt động qua Spring proxy không; nếu method tự gọi `this.method()` trong cùng bean, async advice thường không được áp dụng.
7. Đối chiếu metrics executor: `activeCount`, `poolSize`, queue depth, rejection, task latency.
8. Phân loại: “publisher bị chặn” hay “publisher trả nhanh nhưng queue async đang tích tụ”.

Một lỗi quan sát thường gặp là chỉ đo callback body mà bỏ qua **thời gian task chờ trong queue**. Listener có thể chạy 30 ms nhưng bắt đầu sau 30 giây, nghĩa là end-to-end latency vẫn rất xấu.

Spring không tự sinh observation hoàn chỉnh cho mọi `@EventListener` invocation theo semantics bạn kỳ vọng; nếu cần metrics tin cậy, hãy đo rõ ranh giới **publish**, **queue wait**, **callback execution** và **business completion**.

### 14.3. Các metrics tối thiểu nên có

| Metric | Ý nghĩa |
| --- | --- |
| `publisher.duration` | Thời gian `publishEvent` giữ caller thread |
| `listener.execution.duration` | Thời gian chạy body listener |
| `listener.queue.delay` | Từ lúc submit đến lúc worker bắt đầu |
| `listener.errors` | Lỗi theo event type/listener |
| `executor.active`, `executor.queued` | Pool saturation |
| `executor.rejected` | Event/task không thể schedule |
| `outbox.backlog`, `outbox.oldest_age` | Khả năng hoàn thành hậu xử lý bền vững |
| `business.callback.completed` | Side effect nghiệp vụ đã đạt trạng thái mong muốn |

Tên metric là **gợi ý đặt tên ứng dụng**, không có nghĩa Spring tự cung cấp tất cả metric này sẵn. Tránh đưa nguyên `eventId` hay `userId` vào metric tag có cardinality cao; đưa vào logs/traces thay vì nhãn series.

## 15. Kiểm thử chính xác, không dựa vào `Thread.sleep()`

### 15.1. Chứng minh blocking behavior

Ví dụ ở trên không dùng assert latency nhỏ hơn một ngưỡng mili giây, vốn dễ sai trên CI chậm. Nó kiểm tra các điều kiện đồng bộ hóa:

- Listener sync **đã vào method** và **chưa được release**.
- Lời gọi publish sync **vẫn chưa kết thúc**.
- Khi release, publisher mới kết thúc.
- Với async, worker **đã vào method** và **chưa release**, nhưng Future của publisher đã hoàn thành.
- Sau release, async listener mới hoàn tất.

Nhờ vậy phép thử bám vào semantics của dispatcher chứ không phụ thuộc scheduler có nhanh hơn 5 ms hay không. Timeout 5 giây chỉ là ngưỡng phát hiện lỗi/deadlock trong môi trường demo, có thể điều chỉnh cho CI thực tế.

### 15.2. Test saturation riêng

Không dùng demo ở trên để suy ra hệ thống an toàn dưới tải lớn. Cần một test khác cho:

1. Worker count cố định, queue capacity nhỏ.
2. Submit nhiều event hơn capacity trong khi worker bị chặn có chủ đích.
3. Xác minh chính sách rejection/backpressure **đúng hợp đồng**.
4. Kiểm tra publisher được thông báo lỗi submit nếu policy yêu cầu.
5. Kiểm tra không mất event quan trọng nếu dùng outbox/durable messaging.
6. Kiểm tra trạng thái executor sau khi lỗi hoặc shutdown.

### 15.3. Test transaction và lỗi

- Nếu publisher ở trong `@Transactional`, kiểm tra listener sync nhìn thấy transaction còn hoạt động và callback chậm có kéo dài transaction không.
- Nếu dùng `@TransactionalEventListener(AFTER_COMMIT)`, kiểm thử cả commit/rollback; event có thể đã publish nhưng AFTER_COMMIT không chạy khi rollback.
- Nếu có `@Async`, test side effect chỉ quan sát được sau khi worker hoàn tất và exception không tự quay về publisher.
- Nếu publisher cần kết quả của callback để quyết định success, không thay callback đồng bộ bằng async mà bỏ qua phần kiểm chứng business outcome.

## 16. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi REST/SMTP chậm từ `@EventListener` mặc định | Giữ publisher thread và transaction lâu | Tối ưu I/O, timeout; cân nhắc async hoặc outbox |
| Chuyển mọi listener sang async để “fix” latency | Mất sequencing/transaction/error semantics | Tách đúng tác vụ có thể xử lý độc lập |
| Chỉ tăng queue mà không quản lý throughput | Backlog/memory tăng | Bounded queue, concurrency limit, đo arrival/service rate |
| Dùng `CallerRunsPolicy` nhưng kỳ vọng publish không bao giờ chờ | Worker bão hòa khiến caller tự chạy task | Dùng policy phù hợp, chấp nhận backpressure có chủ đích |
| Chọn executor quá ít worker cho I/O dài | Queue delay tăng | Đo duration/concurrency và giới hạn I/O hợp lý |
| Chọn executor quá nhiều worker | Bão hòa DB, network, memory | Đo tải và giới hạn tài nguyên downstream |
| Giả định async listener nhận transaction/MDC | Context mất, dữ liệu chưa commit | Event payload, context propagation có chọn lọc, transaction mới |
| Cho rằng `@Async` tự có retry | Task fail/mất khi JVM chết | Error handling, retry/durable queue/outbox |
| Dùng `@Order` để làm task async lần lượt hoàn tất | Race condition | Orchestrator/acknowledgment nếu cần thứ tự |
| Bỏ qua submit rejection | Business event bị mất reaction | Ràng buộc failure policy, monitoring và storage bền vững |
| Dùng `Thread.sleep()` để “chờ” listener trong test | Flaky test | Latch/Future với timeout |
| Nghĩ `publishEvent` trả về là mọi subscriber thành công | Async callback có thể chưa chạy | Assert business completion riêng |

## 17. Checklist triển khai

1. Có biết listener nào tốn thời gian và đang chạy trên thread nào không?
2. Có đo **publisher wait time**, queue delay và listener processing time riêng không?
3. Listener chậm thuộc invariant chính hay chỉ là side effect phụ?
4. Nếu chuyển async, application có `@EnableAsync` và executor đúng tên không?
5. Pool/queue có giới hạn và policy rejection rõ ràng không?
6. Nếu quá tải, publisher nhận lỗi, tự chạy task hay drop? Kết quả đó có đúng yêu cầu nghiệp vụ không?
7. Listener cần dữ liệu đã commit hay transaction mới không?
8. Có xử lý `AsyncUncaughtExceptionHandler`, retry, idempotency và crash recovery chưa?
9. Có truyền correlation ID/trace context phù hợp mà không copy transaction resource không?
10. Test có chứng minh callback sync block, callback async tách thread và saturation behavior không?

**Kết luận:** Listener chậm làm nghẽn publisher vì **multicaster mặc định của Spring gọi listeners đồng bộ ngay trên thread phát event**. Tối ưu callback là bước đầu; dùng `@Async` hoặc executor tùy chỉnh nếu công việc có thể xử lý sau, nhưng phải quản trị **queue, rejection, error handling, context và transaction**. Đối với công việc quan trọng cần tồn tại qua crash, hãy dùng outbox/durable queue thay vì trông chờ một executor in-memory.

## Tài liệu chính thức

- Spring Framework 6.2 — ApplicationContext events và `@Async`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — Scheduling and `@Async`: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — Transaction-bound events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — Observability và context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
