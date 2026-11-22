# Async listener chạy trên thread khác

## 1. Triệu chứng: publish thành công nhưng listener chạy ở thread không mong đợi

Trong Spring Framework Application Events, developer thường bắt đầu bằng một `@EventListener` đồng bộ:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    process(event);
}
~~~

Ở cấu hình multicaster mặc định, listener này thường chạy **trên chính thread gọi `ApplicationEventPublisher.publishEvent(...)`**. Nếu publisher là request thread của Spring MVC, listener cũng có thể nhìn thấy các thread-bound context đang hợp lệ tại thời điểm đó.

Khi bổ sung `@Async` và bật `@EnableAsync`, hành vi thay đổi:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    process(event);
}
~~~

Spring gửi lời gọi method qua cơ chế async proxy đến `TaskExecutor`. Thread xử lý thật có thể là `event-worker-1`, **không phải** `http-nio-8080-exec-3` đang publish event.

Ví dụ log:

~~~text
2026-11-11T07:00:01Z publisher [http-nio-8080-exec-3] eventId=evt-101
2026-11-11T07:00:01Z listener  [event-worker-1]       eventId=evt-101
~~~

Tên thread chỉ là ví dụ minh họa; mỗi servlet container và executor có cách đặt tên riêng. Một event có thể giữ nguyên ID khi truyền qua hai thread, trong khi các dữ liệu gắn với thread như MDC, request context hoặc transaction context **không tự đi theo**.

Các triệu chứng thường gặp:

- `RequestContextHolder.currentRequestAttributes()` ném `IllegalStateException`: không có request context được bind trên worker.
- `SecurityContextHolder.getContext().getAuthentication()` không có giá trị mong đợi nếu không có cơ chế propagation phù hợp.
- Log trong listener thiếu `traceId`/`correlationId` dù log trong controller có.
- `TransactionSynchronizationManager.isActualTransactionActive()` trả về `false` trong listener async dù publisher đang ở trong `@Transactional`.
- Một exception ở listener không quay về controller hoặc service đã gọi `publishEvent`.
- Service in “đã publish” trước khi listener in “bắt đầu xử lý”.
- Listener đôi khi chạy trên một thread khác mỗi lần do executor pool; thứ tự hoàn thành có thể thay đổi.

**Câu hỏi chẩn đoán đầu tiên** phải là: *lời gọi listener có thật sự được đưa sang một executor không, và thread nào đang chạy code nghiệp vụ?* Không nên suy luận chỉ từ việc thấy `@Async` trong source.

## 2. Phân biệt ba cách dispatch event

| Cách xử lý | Thread chạy handler | Publisher có đợi handler hoàn tất? | Lưu ý |
| --- | --- | --- | --- |
| `@EventListener` bình thường, multicaster mặc định | Thường chính thread publish | Có, đối với listener đồng bộ | Exception handler có thể lan về publisher |
| `@Async @EventListener` và `@EnableAsync` hoạt động | Thread thuộc executor của async proxy | Không đợi tác vụ xử lý xong | Lỗi của method `void` được xử lý theo async exception policy |
| Custom `SimpleApplicationEventMulticaster` gắn `TaskExecutor` | Executor do multicaster chọn, nếu listener hỗ trợ async execution | Không nhất thiết | Chính sách dispatch, context và exception là trách nhiệm cấu hình |

### Hai tầng async không phải một thứ

**Cách A — `@Async` trên method listener:**

~~~text
ApplicationEventPublisher
    -> multicaster mặc định gọi adapter của @EventListener
        -> bean async proxy lên lịch method vào TaskExecutor
            -> worker thread thực thi thân listener
~~~

**Cách B — TaskExecutor ngay tại multicaster:**

~~~text
ApplicationEventPublisher
    -> SimpleApplicationEventMulticaster
        -> TaskExecutor chuyển việc invoke listener sang worker
            -> method listener thực thi
~~~

Hai cách có thể cùng tồn tại trong ứng dụng, thậm chí dẫn đến hai lớp scheduling nếu cấu hình không có chủ ý. Khi debug, phải xác định **executor nào** nhận task. Không nên “sửa” tình trạng listener chậm bằng cách gắn thêm executor ngẫu nhiên ở cả hai nơi.

Trong Spring 6.2, `SimpleApplicationEventMulticaster` mặc định gọi listener đồng bộ. Khi cấu hình executor ở multicaster, một số listener **không hỗ trợ async execution** vẫn được chạy trong thread publish; ví dụ transaction-synchronized listener có cơ chế riêng. Vì thế “đã cấu hình multicaster async” không chứng minh *mọi* listener chuyển thread.

## 3. Điều kiện để @Async thực sự hoạt động

`@Async` là annotation được Spring xử lý thông qua hạ tầng async, thường bằng AOP proxy. Kiểm tra các điều kiện sau:

1. **Có `@EnableAsync`** trong context phù hợp (hoặc hạ tầng tương đương đã được bật), chứ không chỉ import annotation.
2. Listener là **bean do Spring quản lý**, không phải object được tạo bằng `new` rồi gọi trực tiếp.
3. Method handler đủ điều kiện được proxy intercept: tránh `private`, `final` hoặc target class `final` trong cấu hình proxy dựa trên subclass; xác định rõ hạn chế của interface/class-based proxy.
4. Có **`TaskExecutor` hợp lệ**. Với `@Async("eventExecutor")`, qualifier phải trỏ đến đúng executor bean.
5. Lời gọi đến handler đi **qua proxy**, không phải self-invocation nội bộ như `this.onOrderPlaced(event)`.
6. Không nhầm với việc publisher gọi một listener đồng bộ rồi listener tự tạo task trong method; đó là kiến trúc khác và cần đo ở điểm tạo task.

Nếu một đoạn code gắn `@Async` nhưng vẫn chạy trong request thread, kiểm tra registration/proxy/configuration trước khi đổ lỗi cho Spring event routing.

### @Order và thứ tự xử lý

`@Order` quyết định mức ưu tiên **gọi hoặc lên lịch** giữa những listener tương ứng, không buộc listener async ưu tiên cao phải **hoàn thành** trước listener ưu tiên thấp. Khi dùng thread pool, thứ tự hoàn thành còn chịu ảnh hưởng của độ dài tác vụ, queue và scheduler.

~~~text
@Order(-10) async A: được schedule
@Order(10)  sync B : xử lý xong
async A             : có thể xong muộn hơn B
~~~

Vì thế, nếu B **cần dữ liệu mà A đã commit**, hãy xây orchestration/transaction rõ ràng thay vì dựa vào `@Order`.

## 4. Chương trình Java 17+ chứng minh bằng thread và event payload

Demo hoàn chỉnh dùng **Spring Framework 6.2.19**, **Java 17+** và `ThreadPoolTaskExecutor`. Không cần Spring Boot, web server hay database.

Thiết kế:

- `main` đóng vai thread publish;
- `SyncOrderListener` dùng `@EventListener` bình thường, chạy trên thread publish;
- `AsyncOrderListener` dùng `@Async("eventExecutor")`, chạy trên thread có tiền tố `event-worker-`;
- cả hai ghi `Observation` vào một `BlockingQueue`;
- `main` lấy **hai observation** bằng `poll(timeout)`, phân loại theo tên listener và in kết quả theo thứ tự cố định, không phụ thuộc thread nào hoàn thành trước;
- event chứa `correlationId` để chứng minh **payload vẫn được chuyển đầy đủ** dù thread-local context không tự đi theo.

### Cấu trúc thư mục

~~~text
async-event-thread-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/AsyncEventThreadDemo.java
    └── test/java/demo/AsyncEventThreadDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'async-event-thread-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AsyncEventThreadDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/AsyncEventThreadDemo.java

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncEventThreadDemo {

    // Snapshot nghiệp vụ: không giữ tham chiếu Thread, HttpServletRequest
    // hoặc transaction/session object trong event.
    public record OrderPlaced(long orderId, String correlationId) {}

    public record Observation(
        String listener,
        String threadName,
        String correlationId
    ) {}

    @Bean
    BlockingQueue<Observation> observations() {
        return new LinkedBlockingQueue<>();
    }

    @Bean(name = "eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("event-worker-");
        return executor;
    }

    @Bean
    SyncOrderListener syncOrderListener(
            BlockingQueue<Observation> observations) {
        return new SyncOrderListener(observations);
    }

    @Bean
    AsyncOrderListener asyncOrderListener(
            BlockingQueue<Observation> observations) {
        return new AsyncOrderListener(observations);
    }

    public static class SyncOrderListener {
        private final BlockingQueue<Observation> queue;

        public SyncOrderListener(BlockingQueue<Observation> queue) {
            this.queue = queue;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            queue.add(new Observation(
                "sync",
                Thread.currentThread().getName(),
                event.correlationId()
            ));
        }
    }

    // Không final: @Async dùng proxy, method phải được intercept.
    public static class AsyncOrderListener {
        private final BlockingQueue<Observation> queue;

        public AsyncOrderListener(BlockingQueue<Observation> queue) {
            this.queue = queue;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            queue.add(new Observation(
                "async",
                Thread.currentThread().getName(),
                event.correlationId()
            ));
        }
    }

    // Helper nhận đủ hai observation và không giả định thứ tự arrival.
    public static Map<String, Observation> collectTwo(
            BlockingQueue<Observation> queue)
            throws InterruptedException {
        Observation first = queue.poll(10, TimeUnit.SECONDS);
        Observation second = queue.poll(10, TimeUnit.SECONDS);

        if (first == null || second == null) {
            throw new IllegalStateException(
                "Expected both sync and async listener observations"
            );
        }

        Map<String, Observation> results = new HashMap<>();
        results.put(first.listener(), first);
        results.put(second.listener(), second);

        if (results.size() != 2 ||
            !results.containsKey("sync") ||
            !results.containsKey("async")) {
            throw new IllegalStateException(
                "Missing or duplicated listener observation"
            );
        }
        return results;
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncEventThreadDemo.class)) {

            String publisherThread = Thread.currentThread().getName();

            @SuppressWarnings("unchecked")
            BlockingQueue<Observation> queue =
                (BlockingQueue<Observation>) context.getBean(
                    "observations");

            context.publishEvent(new OrderPlaced(101L, "REQ-101"));

            Map<String, Observation> result = collectTwo(queue);
            Observation sync = result.get("sync");
            Observation async = result.get("async");

            System.out.println(
                "sync same thread="
                    + publisherThread.equals(sync.threadName()));
            System.out.println(
                "async on event executor="
                    + async.threadName().startsWith("event-worker-"));
            System.out.println(
                "async different thread="
                    + !publisherThread.equals(async.threadName()));
            System.out.println(
                "correlation preserved="
                    + (Objects.equals(sync.correlationId(), "REQ-101")
                    && Objects.equals(async.correlationId(), "REQ-101"))
            );
        }
    }
}
~~~

### Chạy chương trình

Dùng JDK 17+ với Gradle hoặc Gradle Wrapper tương thích:

~~~bash
gradle run --quiet
# Nếu có wrapper: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Các dòng do `main` chủ động in ra:

~~~text
sync same thread=true
async on event executor=true
async different thread=true
correlation preserved=true
~~~

Giải thích từng dòng:

1. **`sync same thread=true`**: listener bình thường chạy trên chính thread gọi `publishEvent` với multicaster mặc định.
2. **`async on event executor=true`**: method `@Async("eventExecutor")` thực thi trên một thread do `ThreadPoolTaskExecutor` đặt tiền tố `event-worker-`.
3. **`async different thread=true`**: thread xử lý async khác thread publish.
4. **`correlation preserved=true`**: payload của event giữ nguyên `correlationId` khi được chuyển tới cả hai listener.

Lệnh `poll(10, TimeUnit.SECONDS)` ở đây chỉ dùng trong **console demo/test** để thu kết quả. Không nên bắt một HTTP request thread thực tế chờ vô thời hạn để giả lập công việc async đã hoàn tất; cần hợp đồng response/job riêng.

Một điều kiện quan trọng: chương trình in kết quả theo **loại observation**, không in trực tiếp từ các listener. Vì vậy thứ tự bốn dòng là xác định dù scheduler gọi listener nào trước. Code cũng kiểm tra không có observation lặp hoặc thiếu.

## 5. Kiểm thử bằng JUnit: không dùng Thread.sleep()

Tạo tệp `src/test/java/demo/AsyncEventThreadDemoTest.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.BlockingQueue;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncEventThreadDemoTest {

    @Test
    void asyncListenerUsesDifferentThreadAndKeepsEventData()
            throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncEventThreadDemo.class)) {

            String publisherThread = Thread.currentThread().getName();

            @SuppressWarnings("unchecked")
            BlockingQueue<AsyncEventThreadDemo.Observation> queue =
                (BlockingQueue<AsyncEventThreadDemo.Observation>)
                    context.getBean("observations");

            context.publishEvent(
                new AsyncEventThreadDemo.OrderPlaced(101L, "C-101"));

            Map<String, AsyncEventThreadDemo.Observation> values =
                AsyncEventThreadDemo.collectTwo(queue);

            var sync = values.get("sync");
            var async = values.get("async");

            assertEquals(publisherThread, sync.threadName());
            assertFalse(publisherThread.equals(async.threadName()));
            assertTrue(async.threadName().startsWith("event-worker-"));
            assertEquals("C-101", sync.correlationId());
            assertEquals("C-101", async.correlationId());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
# Hoặc: ./gradlew test
# Windows: gradlew.bat test
~~~

Khi cấu hình executor hoạt động đúng, **một bài test JUnit pass**. Test có timeout ở bước thu observation để không chờ vĩnh viễn khi async listener không chạy. Nó không dựa vào một khoảng ngủ cố định, không giả định observation `sync` nhất thiết vào queue trước `async`.

**Test thất bại là tín hiệu chẩn đoán**. Chẳng hạn, nếu bỏ `@EnableAsync` trong cấu hình này, method được đánh dấu `@Async` có thể bị gọi đồng bộ, làm `async different thread` thành `false`. Nếu tên `eventExecutor` sai hoặc task bị từ chối, test có thể thiếu observation async và ném lỗi sau thời hạn đợi.

Không nên chuyển kết quả test thành một khẳng định “tất cả event listener luôn chạy trên thread khác”: chính ví dụ có **một listener sync** và **một listener async** cùng nhận một loại event.

## 6. Lỗi trong async listener đi về đâu?

Với listener đồng bộ và multicaster mặc định, một `RuntimeException` có thể lan ngược lên publisher:

~~~text
publishEvent()
    -> sync listener throws
    -> caller của publishEvent nhận exception
~~~

Với `@Async @EventListener`:

~~~text
publishEvent()
    -> async proxy submit task
    -> publisher có thể return bình thường
                           |
                           v
                   worker listener throws
                           |
                           +-- không tự rethrow cho publisher
~~~

Spring documentation nhấn mạnh exception của asynchronous event listener **không được propagate về caller**. Với `@Async` method trả `void`, exception có thể đi tới `AsyncUncaughtExceptionHandler`. Nếu phương thức async có cơ chế trả kết quả kiểu Future/CompletableFuture trong trường hợp API hỗ trợ, lỗi thường được quan sát qua kết quả bất đồng bộ thay vì qua caller ban đầu; lưu ý method `@EventListener` gắn `@Async` không nên dựa vào return value để tự publish event kế tiếp.

Đoạn minh họa ứng dụng (không chạy độc lập):

~~~java
@Configuration
@EnableAsync
class AsyncErrorConfiguration implements AsyncConfigurer {

    private static final Logger log =
        LoggerFactory.getLogger(AsyncErrorConfiguration.class);

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {

        return (ex, method, params) -> {
            log.error(
                "Async listener failed: method={}",
                method.getName(),
                ex
            );
            // Có thể tăng metric, báo alert hoặc enqueue retry.
        };
    }
}
~~~

Cần dependency SLF4J cùng các import `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `Logger` và `LoggerFactory` thích hợp. Đây là **mẫu cấu hình một phần**, không phải class chạy độc lập. Cơ chế ghi log chỉ giúp quan sát lỗi; **nó không tự retry hoặc bảo đảm task đã hoàn tất**.

Một số lỗi liên quan nhưng khác nhau:

- **Lỗi khi schedule task:** executor quá tải, đã shutdown hoặc cấu hình sai; việc submit có thể bị từ chối ngay từ đường gọi publisher hoặc async proxy, ví dụ `TaskRejectedException`.
- **Lỗi sau khi task được nhận:** callback chạy trong worker rồi ném exception; publisher có thể đã return, nên không dựa vào `try/catch` bên ngoài `publishEvent` để bắt lỗi này.
- **Exception bị bắt và bỏ qua bên trong listener:** phương thức không ném tiếp; monitoring có thể không thấy lỗi nếu handler không báo cáo.
- **Executor queue nghẽn:** listener không nhất thiết chạy ngay sau publish. “Có event” không đồng nghĩa “đã xử lý xong”.
- **Process crash trước khi worker chạy:** local async executor không phải durable queue; task có thể mất.

Nếu tác vụ quan trọng như gửi thông báo giao dịch, cập nhật hệ thống ngoài hoặc gọi thanh toán, cần thiết kế **retry, idempotency, outbox/message broker hoặc job bền vững** thay vì tin rằng `@Async` tự cung cấp độ tin cậy.

## 7. Thread khác: những context nào bị mất?

Thread không tự chia sẻ mọi trạng thái do request/publisher đang giữ. Từng loại context có luật riêng:

| Context/giá trị | Gắn ở đâu? | Điều cần nhớ trong worker async |
| --- | --- | --- |
| `RequestContextHolder` / `RequestAttributes` | Thread-bound trong Spring MVC/Servlet | Thường vắng mặt; không dùng raw `HttpServletRequest` sau khi request kết thúc |
| `SecurityContextHolder` | Thường dùng ThreadLocal theo chiến lược mặc định | Không tự có authentication của request; cần cơ chế security propagation hoặc xác thực độc lập |
| `LocaleContextHolder` | Thread-local locale context | Không tự chuyển locale/timezone |
| MDC/logging context | Thread-local theo logging implementation | Log worker có thể thiếu trace/correlation |
| Imperative transaction context | `TransactionSynchronizationManager` gắn resource với thread | Không tự tham gia transaction của publisher |
| Reactor Context | Context gắn với reactive subscriber | Không phải servlet ThreadLocal; cần giữ trong reactive chain và dùng propagation phù hợp |
| Event payload | Object được đưa tới listener | Giá trị trong payload vẫn có thể đọc nếu thiết kế immutable và an toàn |

Điều này giải thích lỗi điển hình:

~~~java
@Async("eventExecutor")
@EventListener
public void onPlaced(OrderPlaced event) {
    // Có thể ném lỗi vì worker không có request attributes.
    RequestAttributes attrs =
        RequestContextHolder.currentRequestAttributes();
}
~~~

Đây là đoạn minh họa; cần bean, import và config `@EnableAsync`. Thay bằng dữ liệu thực sự cần thiết trong payload:

~~~java
public record OrderPlaced(
    long orderId,
    String correlationId,
    String tenantId
) {}

@Async("eventExecutor")
@EventListener
public void onPlaced(OrderPlaced event) {
    processOrder(
        event.orderId(),
        event.correlationId(),
        event.tenantId()
    );
}
~~~

Đoạn này cũng là minh họa cần method `processOrder` và bean tương ứng. **Giá trị `tenantId` trong event không tự thay thế việc xác thực/ủy quyền** khi worker truy cập tài nguyên nhạy cảm.

### Vì sao không bật InheritableThreadLocal cho mọi thứ?

`InheritableThreadLocal` có thể truyền giá trị khi **thread con mới được tạo**, nhưng thread pool tái sử dụng worker và có thể tạo thread đúng lúc đang xử lý request A. Context từ request A có thể bị giữ lại và lộ sang task của request B. Với request context, đây là sai lầm nguy hiểm.

Đừng bật `RequestContextHolder.setRequestAttributes(attributes, true)` hoặc cơ chế tương tự như lời giải tổng quát cho executor. Nếu thật sự cần propagation, phải cân nhắc lifetime của context, capture/restore chính xác và cleanup trên pooled threads.

## 8. Cách truyền logging/observation context có kiểm soát

Nếu mục tiêu chỉ là ghi log có `correlationId`, thường **đơn giản và an toàn hơn** khi đưa ID vào immutable event payload. Listener có thể ghi ID từ event vào structured log fields trong thời gian xử lý.

Khi cần chuyển **một số execution context đã được định nghĩa rõ**, Spring hỗ trợ `TaskDecorator`, chẳng hạn `ContextPropagatingTaskDecorator` phối hợp với Micrometer Context Propagation và accessor tương ứng:

~~~java
// Minh họa bổ sung vào cấu hình ThreadPoolTaskExecutor.
executor.setTaskDecorator(
    new ContextPropagatingTaskDecorator()
);
~~~

Cần Spring version hỗ trợ, dependency Micrometer Context Propagation và `ThreadLocalAccessor` tương ứng. **Không phải mọi context đều tự được copy** chỉ nhờ thêm decorator; cần kiểm tra những accessor đã đăng ký.

Các quy tắc:

- Chỉ propagate context **có lifetime phù hợp**, ví dụ tracing/logging metadata, không mặc định giữ raw servlet request/session trong background thread.
- Nếu tự viết decorator, snapshot context trước khi submit; restore/clear **trong `finally`**, tránh rò dữ liệu khi worker tái sử dụng.
- Không copy transaction thread-local để cố gắng dùng chung JDBC transaction giữa threads. Transaction imperative không được thiết kế để tham gia như vậy.
- Với security context, dùng cơ chế Spring Security phù hợp, ví dụ các executor wrapper bảo đảm clear context theo contract, thay vì tự sao chép token tùy tiện.
- Có overhead cho capture/restore; test throughput và latency nếu app dùng nhiều event.
- Việc tracing/observability context được truyền không đồng nghĩa listener chắc chắn chạy sau commit hoặc hoàn tất thành công.

Nếu ứng dụng sử dụng Spring WebFlux/Reactor, nên hiểu ngữ cảnh reactive theo **subscriber context**, không ép mọi thứ vào ThreadLocal theo cách servlet.

## 9. Thread khác và transaction: lỗi dễ bị bỏ qua

Giả sử:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    repository.save(toOrder(command));
    eventPublisher.publishEvent(new OrderPlaced(...));
}
~~~

Code là ví dụ không độc lập. Khi event được công bố **trước commit** và `@Async @EventListener` nhận nó, worker có thể chạy **trước khi transaction T1 commit**.

Hậu quả có thể xảy ra:

- Listener gọi repository qua transaction/connection riêng và **không đọc thấy bản ghi chưa commit**.
- T1 rollback, nhưng listener đã gọi API ngoài hoặc gửi email; side effect không tự quay lại.
- Listener đọc các dữ liệu thread-local của T1 và thấy không có transaction active.
- Exception từ listener async không tự làm T1 rollback.

Để ràng buộc xử lý sau khi commit, cân nhắc:

~~~java
@Async("eventExecutor")
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    // Callback đăng ký trong T1; khi commit thành công,
    // method được đưa sang executor để xử lý độc lập.
}
~~~

Đây là mẫu minh họa cần import/bean; không phải chương trình độc lập. Trong Spring imperative:

1. Event được publish khi T1 active.
2. Hạ tầng `@TransactionalEventListener` đăng ký callback synchronization; bản thân callback cần được kích hoạt bởi transaction manager ở phase phù hợp.
3. Khi T1 commit, async proxy đưa method handler vào executor.
4. **Thread executor không thừa hưởng transaction T1**. Nếu cần ghi DB tại worker, hãy thiết kế transaction riêng phù hợp, ví dụ một `@Transactional` trên service được gọi qua Spring proxy (thường mở transaction mới khi không có transaction ở worker).

Cũng cần nhớ: `@TransactionalEventListener` mặc định **bỏ qua event ngoài transaction** khi `fallbackExecution=false`. Với Spring reactive transaction, sử dụng `TransactionalEventPublisher`/Reactor Context theo đúng hợp đồng thay vì coi servlet ThreadLocal là nguồn transaction.

Nếu yêu cầu event **không được mất khi process crash giữa commit và xử lý**, `AFTER_COMMIT + @Async` vẫn là giải pháp trong bộ nhớ. Dùng transactional outbox hoặc cơ chế durable messaging với retry/idempotency khi yêu cầu tin cậy cao.

## 10. Chẩn đoán theo từng biểu hiện

### Trường hợp A: Đã thêm @Async nhưng vẫn thấy cùng thread

Hỏi:

1. Có `@EnableAsync` không? Nó nằm trong đúng `ApplicationContext` quản lý listener chứ?
2. Listener có phải Spring bean không?
3. Method có `private`/`final` hoặc bị gọi trực tiếp từ cùng object (self-invocation) không?
4. Có lỡ dùng `SyncTaskExecutor` hoặc executor tùy chỉnh thực thi inline không?
5. `@Async("executorName")` có tham chiếu đúng bean không?
6. Log đã đặt **bên trong method listener**, không phải chỉ quanh `publishEvent`?

Nếu tất cả listener đang dùng cùng thread và không có executor cấu hình, đó có thể là hành vi đồng bộ **đúng thiết kế**. Spring không tự bật `@Async` chỉ vì bạn đã đặt listener trong application context.

### Trường hợp B: Đã publish nhưng log handler xuất hiện trễ

Kiểm tra queue của executor, số active workers, task duration, saturation, rejection policy và việc process shutdown. Đừng chẩn đoán “event thất lạc” chỉ bằng thứ tự hai dòng log. Một listener async có thể đang chờ worker rảnh.

### Trường hợp C: Publisher không thấy exception nhưng task thất bại

Đối với `void @Async`, thêm `AsyncUncaughtExceptionHandler` hoặc chính sách try/catch + log/metric rõ ràng. Đo **publish attempts**, **listener invocations**, **listener success/error**, **latency** và số task pending bằng những metric có định nghĩa khác nhau. Không dùng `publishEvent` return làm bằng chứng handler success.

### Trường hợp D: Log handler mất correlationId/traceId

Dùng event payload hoặc context propagation có kiểm soát; phân biệt ID nghiệp vụ với trace context của hạ tầng. Không gắn ID có cardinality cao (`eventId`, `correlationId`) làm metric tag; chúng thích hợp cho logs/traces.

### Trường hợp E: Listener không thấy entity vừa save

Cần xem transaction T1 đã commit chưa. `@Async @EventListener` không đợi transaction commit. Kiểm tra mức isolation, cách listener lấy connection và truy vấn. Nếu nghiệp vụ cần after-commit, dùng transaction-bound event hoặc outbox, **không** cố sửa bằng `Thread.sleep(...)`.

### Trường hợp F: Test đôi khi pass, đôi khi fail

Test đang đọc kết quả listener async **ngay sau publish**, hoặc dựa vào sleep/timing may rủi. Dùng `BlockingQueue.poll(timeout)`, `CountDownLatch`, `CompletableFuture` hoặc Awaitility để đợi tín hiệu cụ thể. Assert thread khác và dữ liệu event đúng, tránh assert thứ tự completion khi không có hợp đồng.

## 11. Ma trận phân biệt triệu chứng và hành động

| Quan sát | Nguyên nhân đáng kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Log cùng thread dù có `@Async` | Async proxy không hoạt động, executor đồng bộ | Kiểm tra `@EnableAsync`, bean/proxy, executor |
| Log thread `event-worker-*` | Async thực thi đúng | Đánh giá lifecycle, lỗi và context độc lập |
| `RequestContextHolder` trả `null` | Worker không có servlet request binding | Snapshot dữ liệu cần thiết vào payload |
| MDC thiếu `correlationId` | Không có propagation | Payload/structured logging hoặc decorator |
| `isActualTransactionActive() = false` | T1 gắn với publisher thread | Dùng transaction mới tại worker nếu cần |
| DB chưa thấy row mới | Listener chạy trước commit hoặc isolation khác | AFTER_COMMIT/outbox tùy yêu cầu |
| Exception không về publisher | Handler thất bại trong worker | AsyncUncaughtExceptionHandler, metric, retry |
| Handler không chạy sau publish | Sai type/annotation, executor rejected, backlog, transaction phase | Log event type, đăng ký bean, executor, phase |
| Log thứ tự A/B thay đổi | Scheduling và duration độc lập | Kiểm thử theo tín hiệu; không dựa vào `@Order` để chờ completion |
| Sau restart mất task | Executor local không durable | Queue/job/outbox bền vững |

## 12. Checklist trước khi đóng sự cố

- [ ] Xác nhận **event type, event ID/correlation ID, thread name** tại thời điểm publish và trong listener.
- [ ] Phân biệt `@EventListener` sync, `@Async @EventListener` và multicaster có `TaskExecutor` riêng.
- [ ] Kiểm tra `@EnableAsync`, proxy và executor qualifier.
- [ ] Không giả định `@Order` bảo đảm **thứ tự hoàn thành** của các task async.
- [ ] Biết listener trả lỗi bằng exception trực tiếp, Future hay async error handler nào.
- [ ] Kiểm tra các context cần thiết: request, security, locale, MDC và transaction.
- [ ] Truyền metadata cần thiết qua immutable event payload; không mang raw `HttpServletRequest`/JPA entity vào background task.
- [ ] Nếu propagate context bằng decorator, đảm bảo restore/clear đúng ở pooled thread.
- [ ] Kiểm thử timeout/rejection/error của executor, không chỉ happy path.
- [ ] Nếu cần xử lý **sau commit**, dùng đúng phase; nếu cần không mất task, dùng outbox/durable queue.
- [ ] Test async bằng latch/queue có timeout; tránh `Thread.sleep`.
- [ ] Đánh giá metric về queue depth, task rejection, listener latency, failure và backlog.

### Ghi nhớ

~~~text
publishEvent(...) trong thread A
    |
    +-- @EventListener đồng bộ
    |     -> thường chạy trong thread A
    |
    +-- @Async @EventListener
          -> proxy submit vào TaskExecutor
          -> chạy body listener trong thread B
          -> không tự có request/transaction/MDC context của A
          -> exception trong B không tự ném về A

Cách debug:
    Log thread + eventId + correlationId ở hai phía.
    Kiểm tra @EnableAsync + proxy + TaskExecutor.
    Dùng payload immutable cho metadata cần thiết.
    Tách after-commit/durability khỏi bài toán thread.
~~~

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Task Execution and Scheduling / @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — RequestContextHolder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)
