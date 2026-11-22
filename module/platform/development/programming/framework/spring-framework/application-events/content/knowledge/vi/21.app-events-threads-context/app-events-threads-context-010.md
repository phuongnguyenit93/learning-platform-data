# Kiểm tra thread name khi chẩn đoán Spring Application Events

## 1. Vì sao thread name quan trọng?

Khi ứng dụng dùng Spring Application Events, cùng một lời gọi `publishEvent(...)` có thể dẫn đến listener chạy **ngay trong luồng publisher** hoặc được giao cho một executor và chạy **ở luồng khác**. Nếu chỉ nhìn kết quả nghiệp vụ mà không biết listener đã chạy ở đâu, kỹ sư dễ chẩn đoán sai các vấn đề:

- Vì sao request HTTP chậm dù service chỉ gọi `publishEvent(...)`?
- Vì sao listener được đánh dấu `@Async` nhưng log vẫn nằm trên thread của request?
- Vì sao `MDC`, `SecurityContext`, transaction hoặc một giá trị `ThreadLocal` biến mất khi sang listener?
- Vì sao event được publish thành công nhưng listener xử lý lỗi ở thời điểm khác?
- Vì sao nhiều listener dường như chạy "song song" nhưng thực tế cùng một worker, gây nghẽn hàng đợi?

**Thread name** (tên thread), lấy qua `Thread.currentThread().getName()`, là một tín hiệu chẩn đoán rất hữu ích. Nó giúp xác định *đường thực thi có khả năng xảy ra*, đặc biệt khi đặt prefix riêng cho executor. Tuy nhiên **tên thread chỉ là một nhãn có thể thay đổi**: không tự chứng minh listener có transaction, không bảo đảm một event đã hoàn tất, không xác định duy nhất thread, và không đủ để kết luận có dữ liệu context được truyền đúng.

Bài này tập trung vào cách xem và diễn giải tên thread khi phát/xử lý **Spring Application Events**, cách cấu hình tên rõ ràng và cách kết hợp log/metrics để xác minh giả thuyết.

## 2. Mô hình mặc định: publisher và listener đồng bộ

Theo cơ chế mặc định của Spring, `ApplicationEventPublisher` chuyển event cho multicaster (thường là `SimpleApplicationEventMulticaster`). Nếu không cấu hình task executor cho multicaster và listener không tự dùng `@Async`, callback được gọi **đồng bộ trên thread của publisher**.

```text
HTTP thread: http-nio-8080-exec-3
    |
    v
OrderService.placeOrder()
    |
    v
publisher.publishEvent(new OrderPlaced(...))
    |
    v
@EventListener onOrderPlaced(...)  <--- cùng HTTP thread
    |
    v
callback hoàn tất
    |
    v
publishEvent(...) trả về
    |
    v
HTTP response
```

Ví dụ một request đang được xử lý bởi thread có tên `http-nio-8080-exec-3`:

```text
2026-11-11 12:00:00.000 [http-nio-8080-exec-3] INFO  OrderService - Publishing order=ORD-9
2026-11-11 12:00:00.003 [http-nio-8080-exec-3] INFO  OrderListener - Handling order=ORD-9
2026-11-11 12:00:00.040 [http-nio-8080-exec-3] INFO  OrderService - Publish returned
```

Đây là **log minh họa**, không phải output của chương trình ở mục 4. Cùng tên thread và thứ tự thực hiện gợi ý listener đồng bộ; cần kết hợp cấu hình executor và bằng chứng runtime trước khi kết luận. Khi listener làm việc chậm, thời gian đó có thể nằm trong độ trễ trả response.

**Không suy diễn sai:** Nếu thấy tên thread `main` khi khởi động ứng dụng, đó chỉ cho thấy code đang chạy trên thread khởi động tại thời điểm ghi log. Trong ứng dụng web, publisher thường là thread xử lý request, nhưng cũng có thể là scheduler, worker, thread nhắn tin hoặc một thread tự tạo.

## 3. Khi nào tên thread sẽ thay đổi?

Có một số cách độc lập để listener được gọi khác thread publisher:

### 3.1. @Async trên chính listener

Với `@EnableAsync` và executor phù hợp:

```java
@Async("eventExecutor")
@EventListener
public void on(OrderPlaced event) {
    System.out.println(Thread.currentThread().getName());
}
```

Đây là **mảnh code minh họa**. Listener sẽ được thực thi theo cơ chế `@Async` thông qua Spring proxy; lời gọi được gửi tới bean executor tên `eventExecutor`. Không phải mọi lời gọi đều chuyển thread trong mọi cấu hình có thể có: executor đồng bộ, chính sách `CallerRunsPolicy` khi quá tải, cấu hình proxy sai hoặc self-invocation có thể làm hành vi khác kỳ vọng.

### 3.2. Executor của ApplicationEventMulticaster

Một cách khác là cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` để multicaster có thể nộp callback của các listener **hỗ trợ chạy bất đồng bộ** qua executor. Cách này khác việc đặt `@Async` trên một method.

Kể từ Spring Framework 6.1, một số listener không hỗ trợ async execution ở cấp multicaster, đặc biệt các listener đồng bộ gắn transaction như `@TransactionalEventListener` cần được gọi trong ngữ cảnh xuất phát để đăng ký transaction synchronization. Do đó, không giả định "đặt executor cho multicaster = mọi listener đều chạy trên pool".

### 3.3. Listener tự chuyển công việc sang executor khác

Một listener có thể chạy đồng bộ nhưng gọi `CompletableFuture.runAsync(...)`, `TaskExecutor.execute(...)` hoặc gửi việc vào broker. Log đầu listener sẽ giữ tên publisher, trong khi log của công việc con mang tên khác.

**Cần xác định chính xác đoạn code nào đang được đo.** Chỉ ghi thread name ở điểm bắt đầu listener không cho biết thread của các việc được submit ở bên trong.

## 4. API Java dùng để kiểm tra thread

Java 17 hỗ trợ:

```java
Thread current = Thread.currentThread();

String name = current.getName();
long id = current.getId();
boolean daemon = current.isDaemon();

System.out.printf(
        "thread=%s id=%d daemon=%s%n",
        name, id, daemon);
```

Đây là **mảnh code Java độc lập về API**, có thể đặt trong một phương thức đang thực thi. Lưu ý:

- `getName()` lấy nhãn thread hiện tại. Tên mặc định tùy container/framework và có thể được đổi bằng `setName(...)`.
- `getId()` có thể dùng với JDK 17 để đối chiếu trong tiến trình; **không** dùng làm request ID hay event ID. Java mới hơn có thêm API định danh thread và thay đổi khuyến nghị sử dụng.
- `isDaemon()` cho biết thread được đánh dấu daemon, không chứng minh task sẽ được hoàn tất trước shutdown.
- Tên thread có thể trùng hoặc bị tái sử dụng; pool thường tái sử dụng cùng một thread cho nhiều event khác nhau.

Trong production, nên đưa **thread name + event ID/correlation ID + tên listener + trạng thái/latency** vào log. Thread name giúp tìm đoạn thực thi, còn event ID mới cho phép nối những log của cùng một event qua các thread khác nhau.

## 5. Ví dụ Java 17+ chạy được: so sánh listener đồng bộ và @Async

Ví dụ dùng Spring Boot 3.3.13, Java 17+, không mở web server, tạo riêng một executor với prefix `evt-worker-`. Chúng ta phát hai **kiểu event khác nhau** để thấy chính xác đường đồng bộ và bất đồng bộ, tránh phụ thuộc thứ tự dispatch giữa nhiều listener cùng loại.

### Cấu trúc thư mục

```text
event-thread-demo/
├── pom.xml
└── src/main/java/example/events/EventThreadDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>event-thread-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### EventThreadDemo.java

```java
package example.events;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class EventThreadDemo {

    public record SyncRequested(String id) {
    }

    public record AsyncRequested(String id) {
    }

    public static class EventHandlers {
        private final CountDownLatch asyncDone;

        public EventHandlers(CountDownLatch asyncDone) {
            this.asyncDone = asyncDone;
        }

        @EventListener
        public void onSync(SyncRequested event) {
            System.out.printf("SYNC id=%s thread=%s%n",
                    event.id(), Thread.currentThread().getName());
        }

        @Async("eventExecutor")
        @EventListener
        public void onAsync(AsyncRequested event) {
            try {
                System.out.printf("ASYNC id=%s thread=%s%n",
                        event.id(), Thread.currentThread().getName());
            } finally {
                // Chỉ dùng để đồng bộ output của demo.
                asyncDone.countDown();
            }
        }
    }

    @Bean
    CountDownLatch asyncDone() {
        return new CountDownLatch(1);
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("evt-worker-");
        return executor;
    }

    @Bean
    EventHandlers eventHandlers(CountDownLatch asyncDone) {
        return new EventHandlers(asyncDone);
    }

    @Bean
    CommandLineRunner scenario(
            ApplicationEventPublisher publisher,
            CountDownLatch asyncDone) {
        return args -> {
            System.out.println(
                    "PUBLISHER thread=" + Thread.currentThread().getName());

            publisher.publishEvent(new SyncRequested("S1"));
            publisher.publishEvent(new AsyncRequested("A1"));

            if (!asyncDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async event listener timed out");
            }

            System.out.println("RUNNER after async");
        };
    }

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EventThreadDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            // Runner đã kết thúc; Spring quản lý vòng đời executor.
        }
    }
}
```

### Lệnh chạy

Đứng trong thư mục chứa `pom.xml`, dùng Java 17+ và Maven:

```bash
mvn -q package
java -jar target/event-thread-demo-1.0.0.jar
```

Trên JVM khởi chạy bằng lệnh `java -jar` thông thường, các dòng **do ứng dụng tự in** xuất hiện theo thứ tự sau, ngoài log riêng của Spring:

```text
PUBLISHER thread=main
SYNC id=S1 thread=main
ASYNC id=A1 thread=evt-worker-1
RUNNER after async
```

**Phân tích từng dòng:**

1. `CommandLineRunner` được chạy trong giai đoạn startup trên thread gọi `SpringApplication.run(...)` (với lệnh trên thường có tên `main`).
2. `SyncRequested` được dispatch tới listener không có `@Async`, nên tên thread giữ nguyên là `main`.
3. `AsyncRequested` được dispatch tới method có `@Async("eventExecutor")`; method thực sự chạy trên worker do `ThreadPoolTaskExecutor` quản lý, với prefix cấu hình `evt-worker-`. Trong tình huống một worker đầu tiên, tên là `evt-worker-1`.
4. `CountDownLatch` bảo đảm runner chỉ in `RUNNER after async` **sau khi** listener async đã in dòng của nó. Không sử dụng `Thread.sleep(...)` để may rủi thứ tự.
5. `@EnableAsync` và việc gọi qua Spring-managed event listener/proxy là điều kiện để `@Async` có hiệu lực. Nếu tự `new EventHandlers(...)` rồi gọi trực tiếp, không có Spring proxy cho `@Async`.

**Những điều ví dụ không chứng minh:** không có giao dịch DB, không có propagation của MDC/security context, không có message broker, không bảo đảm event bền vững. Tên thread chỉ xác nhận nơi một đoạn code đã chạy trong lượt thực thi này.

**Giới hạn tái lập:** số thứ tự phía sau prefix phụ thuộc các task/worker đã được tạo. Demo chỉ tạo một event async trong pool riêng, nên tên `evt-worker-1` là dự kiến. Trong hệ thống thật có nhiều worker và task song song, không hardcode suffix để làm logic hay assertion lâu dài.

## 6. Đặt tên executor để log dễ đọc

Khi nhiều executor cùng tồn tại, tên như `pool-8-thread-12` không nói rõ task thuộc nghiệp vụ nào. Đặt prefix phân biệt theo **mục đích công việc**, ví dụ:

| Luồng | Prefix gợi ý | Hành vi có thể quan sát |
| --- | --- | --- |
| Listener gửi thông báo | `event-notify-` | Tác vụ xử lý thông báo sau event |
| Listener cập nhật projection | `event-projection-` | Xử lý cập nhật dữ liệu đọc |
| Job đồng bộ dữ liệu | `sync-job-` | Chạy batch/scheduler |
| HTTP server Tomcat | `http-nio-...` (tên do container đặt) | Request được xử lý trên worker của server |
| Async task chung | `application-task-` | Cần xem bean nào thực sự sử dụng |

Prefix không phải cơ chế cách ly: hai executor khác nhau vẫn có thể được cấu hình cùng tên hoặc một task có thể đổi thread. Phải đi kèm **bean name**, thread dump và metrics nếu cần chẩn đoán sâu.

Cấu hình cơ bản:

```java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("event-notify-");
    return executor;
}
```

Đây là **một đoạn cấu hình riêng**, không phải file độc lập. Các số 4/8/100 chỉ để minh họa; trong production phải đo tải, memory, downstream capacity và tỷ lệ rejection để chọn. Đừng thay đổi executor/pool của một module khác chỉ vì muốn tên log đẹp hơn.

**Cẩn thận với tên bean:** `@Async("notificationExecutor")` yêu cầu Spring phân giải đúng executor/qualifier tương ứng. Nếu annotation trỏ sai tên, có thể xảy ra lỗi executor resolution hoặc dùng cấu hình fallback khác tùy setup; khi chẩn đoán, xem cả cấu hình của Spring và log thực thi.

## 7. In thread name có cấu trúc trong log

Mặc dù `System.out.println(...)` hữu ích để học, trong production nên sử dụng logger. Với SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(OrderEventListener.class);

@EventListener
public void on(OrderPlaced event) {
    log.info("Handling eventId={} orderId={} thread={}",
            event.eventId(),
            event.orderId(),
            Thread.currentThread().getName());
}
```

Đây là **đoạn minh họa**, cần định nghĩa `OrderEventListener`, `OrderPlaced` và các method trên event trong một ứng dụng Spring sẵn có. Nếu logging pattern đã chứa thread name, không cần lặp thread ở message trừ khi phục vụ mục tiêu điều tra riêng.

Trong Spring Boot dùng Logback, có thể đặt pattern trong `application.properties`:

```properties
logging.pattern.console=%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n
```

Đây là **cấu hình minh họa**, không cần thêm vào demo mục 5. `%thread` hoặc `%t` trong Logback lấy tên thread tại thời điểm log được tạo. Mẫu log:

```text
12:00:01.050 [http-nio-8080-exec-3] INFO  OrderService - Publishing order=ORD-9
12:00:01.053 [event-notify-2] INFO  NotificationListener - Sending order=ORD-9
```

Log không chứng minh request HTTP đã hoàn tất trước khi listener chạy; chỉ cho thấy chúng đang phát sinh trên những thread có nhãn khác nhau. Nếu log được xử lý asynchronous bởi logging backend, **thứ tự xuất hiện khi xem log tập trung** còn có thể bị thay đổi. Ưu tiên timestamp, event ID và trace/span ID.

### Dùng cả correlation ID và event ID

Tối thiểu nên ghi:

- `eventId`: định danh bản ghi sự kiện.
- `eventType`: kiểu nghiệp vụ, ví dụ `OrderPlaced`.
- `listener`: tên handler.
- `threadName`: nơi handler đang chạy.
- `traceId`/`correlationId`: liên kết các bước trong một request/flow.
- `status`, `durationMs`, `attempt`: biết handler thực sự thành công hay lỗi.

Nếu chỉ dựa vào thread name, hai request/aggregate khác nhau lần lượt chạy trên cùng worker sẽ bị nối nhầm thành cùng một hành động.

## 8. ThreadLocal, MDC và các context không tự đi theo thread

Một trong các nguyên nhân phổ biến nhất khiến listener async "mất dữ liệu" là hiểu nhầm quan hệ giữa thread và context.

| Context | Bản chất | Khi chuyển thread |
| --- | --- | --- |
| Java `ThreadLocal` | Giá trị gắn với thread hiện tại | Không mặc định xuất hiện ở worker khác |
| SLF4J `MDC` | Logging diagnostic context thường lưu theo thread | Không tự động được copy đúng trong mọi executor |
| Spring Security `SecurityContextHolder` | Mặc định dùng chiến lược gắn context với thread | Không nên tự giả định có principal trên async worker |
| Spring transaction | Với transaction imperative, trạng thái thường gắn với thread | Không tự kéo transaction gốc sang async worker |
| Request context | Một số thông tin servlet gắn với request thread | Không nên dùng sau request hoặc không có propagation |
| Reactor Context | Context theo subscriber, không đồng nhất với ThreadLocal | Cần cơ chế quan sát/propagation phù hợp cho reactive flow |

Ví dụ publisher ghi vào MDC:

```java
MDC.put("traceId", "t-123");
publisher.publishEvent(new OrderPlaced(...));
```

Đây là **đoạn minh họa**. Listener đồng bộ trên cùng thread thường đọc được MDC tại thời điểm đó; listener chạy trên pool riêng có thể **không thấy** `traceId` nếu không dùng context propagation. Lỗi không nằm ở việc event "không chứa tên thread", mà ở chỗ MDC không phải payload của event và không tự được mang giữa các thread.

**Tuyệt đối không copy bừa transaction ThreadLocal** để giả lập transaction xuyên thread. Một transaction imperative của Spring, entity manager/connection hoặc request-scoped resource không được coi là an toàn để dùng từ một worker khác. Với nghiệp vụ cần transaction riêng, hãy mở transaction mới đúng cách trong service của listener.

## 9. Propagate logging context có kiểm soát bằng TaskDecorator

Khi có nhu cầu giữ MDC qua một `ThreadPoolTaskExecutor`, có thể gắn `TaskDecorator` để chụp logging context lúc submit và khôi phục ở thread thực thi.

Ví dụ với SLF4J MDC, đặt **trong phương thức cấu hình executor** (đây là đoạn bổ sung, không phải project độc lập):

```java
executor.setTaskDecorator(task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }

            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
});
```

Giả định đã import `java.util.Map` và `org.slf4j.MDC` và có dependency logging phù hợp. Chụp context khi submit, áp lên worker trước khi thực thi, rồi **khôi phục trạng thái trước đó trong finally** để tránh rò thông tin giữa các task dùng chung pool. Việc copy đúng MDC trong một executor không tự truyền được cả `SecurityContext`, request scope hay transaction.

Trong Spring Framework 6.1+, có `ContextPropagatingTaskDecorator` hỗ trợ tích hợp với Micrometer Context Propagation khi đã cấu hình dependency/accessor phù hợp; có thể dùng thay đoạn chép MDC thủ công trong kiến trúc observability được hỗ trợ. Cần kiểm thử phần context thực tế được truyền, vì không phải mọi loại context tùy chỉnh đều được propagate tự động.

**Cảnh báo bảo mật:** Nếu một task được trì hoãn lâu, context chứa dữ liệu nhạy cảm có thể không còn hợp lệ khi task thực sự chạy. Ưu tiên gửi các giá trị nghiệp vụ tối thiểu (như userId đã kiểm soát) trong payload và xác thực lại khi cần thay vì sao chép nguyên request/security context.

## 10. Phân biệt @Async và executor của multicaster

Đây là hai cách khác nhau để chuyển việc sang thread khác; đôi khi ứng dụng dùng cả hai và gây khó hiểu.

### A. @Async trên method listener

```java
@Async("eventExecutor")
@EventListener
public void handle(MyEvent event) {
    // Method này do async proxy nộp cho eventExecutor.
}
```

Điều kiện: annotation processing của `@EnableAsync` hoạt động, bean được Spring quản lý, không bypass proxy, tên executor đúng. Listener mặc định được multicaster **gọi ở publisher thread**, nhưng async proxy chuyển method thực thi sang worker.

### B. Executor của multicaster

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

Đây là **cấu hình minh họa**, cần import các class Spring và dùng trong ứng dụng có bean `eventExecutor`. Khi multicaster có executor, các listener **hỗ trợ asynchronous execution** có thể được gọi trên worker. Một số listener như transaction-synchronized listener không được tùy tiện chuyển sang thread khác bởi multicaster. Mỗi chiến lược có vị trí nộp task khác nhau; chọn một cách rõ ràng là tốt nhất nếu không cần thiết kế phức tạp.

### C. Vì sao thấy thread name của publisher dù tưởng là async?

- Listener không có `@Async` và multicaster chưa cấu hình executor.
- `@EnableAsync` thiếu hoặc bean không được Spring quản lý.
- Lời gọi method `@Async` bị self-invocation (gọi bằng `this.method()`), đi vòng qua proxy.
- Dùng executor đồng bộ, ví dụ `SyncTaskExecutor`.
- Pool dùng `CallerRunsPolicy` khi bão hòa: task có thể được chạy bởi thread đang submit để tạo backpressure.
- Log được ghi ở **trước lúc submit** chứ không phải bên trong callback thực thi.
- Code tạo một task khác bên trong listener và log của cả hai phần bị trộn.

Chỉ thấy một tên giống nhau **chưa đủ** để kết luận cấu hình `@Async` chắc chắn không hoạt động. Hãy thêm log ở cả điểm publish, điểm bắt đầu callback và điểm hoàn tất công việc thực tế, rồi kiểm tra executor/cấu hình runtime.

## 11. Sơ đồ kiểm tra khi listener "không chạy đúng thread"

```text
1. Log thread của publisher ngay trước publishEvent()
                      |
                      v
2. Log thread tại dòng đầu tiên của listener
                      |
            +---------+----------+
            |                    |
      cùng tên                 khác tên
            |                    |
            v                    v
3a. Kiểm tra @Async,       3b. Xác định executor,
    multicaster config         prefix và task
    và proxy                   execution path
            |                    |
            +---------+----------+
                      |
                      v
4. Log eventId/traceId ở cả hai bên
                      |
                      v
5. Kiểm tra queue, active threads, rejection,
   exception và elapsed time
                      |
                      v
6. Xác nhận kết quả nghiệp vụ,
   MDC/transaction/security context nếu có
```

Các câu hỏi nên trả lời theo thứ tự:

**(1) Event này được publish từ thread nào?** Log trong controller/service trước và sau `publishEvent(...)`, không đoán từ tên method.

**(2) Listener nào thật sự được gọi?** Xác định bằng event type, listener class, method và một eventId. Nếu không có log callback, có thể do listener không được đăng ký, filter/condition không khớp, lỗi nộp task hoặc task đang xếp hàng; thread name đơn độc không chẩn đoán được.

**(3) Có executor nào thực sự nhận task?** Kiểm tra cấu hình `@Async("...")`, bean executor hoặc multicaster, tên thread prefix và rejection handler. Nếu task bị từ chối, callback có thể chưa chạy lần nào.

**(4) Callback mất context nào?** Phân biệt MDC (chỉ hỗ trợ log), security principal, transaction và request attributes. Chọn đúng cơ chế propagation, không gộp tất cả thành "thread context".

**(5) Callback đã thành công hay chỉ chạy đến dòng log đầu?** Log trạng thái kết thúc, exception, thời lượng, attempt và theo dõi idempotency. Nếu listener là `void @Async`, exception khi chạy thường không quay về caller; cấu hình `AsyncUncaughtExceptionHandler` hoặc xử lý lỗi trong listener.

## 12. Thread dump: khi log không giải thích được sự cố

Nếu listener nghi bị treo, deadlock hoặc hết worker, cần xem trạng thái thread và stack trace tại thời điểm sự cố. Một JVM chạy trên máy/container có JDK có thể dùng:

```bash
jcmd <PID> Thread.print
```

Hoặc với môi trường/JDK phù hợp:

```bash
jstack <PID>
```

Đây là **lệnh công cụ quản trị**, thay `<PID>` bằng process ID thật; thường cần cùng người dùng hệ điều hành hoặc quyền phù hợp. Không chạy bừa trên tiến trình không có quyền truy cập, và kiểm tra tác động vận hành khi lấy dump của hệ thống rất lớn.

Trong output, tìm:

- Tên thread khớp prefix đã cấu hình, ví dụ `evt-worker-1`.
- Trạng thái `RUNNABLE`, `WAITING`, `TIMED_WAITING` hoặc `BLOCKED` — phải diễn giải **cùng stack**, không kết luận chỉ từ tên state.
- Nhiều worker mắc ở cùng HTTP client/DB call, lock hoặc `CountDownLatch.await()`.
- Thread đang đợi queue trong executor: có thể bình thường khi pool rảnh, không tự chứng minh deadlock.
- Các dấu hiệu deadlock do khóa Java; phân biệt với downstream timeout hay connection pool exhaustion.

**Ví dụ minh họa:** Một task tên `event-notify-3` đang `TIMED_WAITING` trong HTTP client có thể chờ timeout; nếu nhiều task đều như vậy và queue tăng, cần điều tra downstream, timeout, retries và giới hạn concurrency chứ không chỉ tăng pool.

Với **virtual threads** (Java 21+), tên/cách hiển thị và thread dump có khác biệt; các công cụ/định dạng mới có thể phù hợp hơn. Trên Java 17 trong demo, chúng ta đang dùng platform threads từ `ThreadPoolTaskExecutor`.

## 13. Không nhầm thread name với transaction, tính đúng đắn và thứ tự

Các kết luận sai thường gặp:

| Kết luận vội | Vì sao sai | Bằng chứng cần thêm |
| --- | --- | --- |
| "Cùng thread tức là cùng transaction" | Transaction có thể chưa được mở/đã kết thúc, hoặc propagation khác | Trạng thái transaction và transaction boundary thực |
| "Khác thread nên dữ liệu sẽ chạy song song" | Pool có thể chỉ có 1 worker hoặc queue dài | Pool size, active count, queue, timestamps |
| "Tên có async nghĩa là không chặn publisher" | Executor có thể dùng `CallerRunsPolicy`, chính sách rejection khác, hoặc submit bị block | Thời lượng `publishEvent`, policy, stack |
| "Có log START tức là event xử lý thành công" | Task có thể ném lỗi sau START | END/FAILED logs, metrics, kết quả nghiệp vụ |
| "Thread khác là transaction tự đi theo" | Imperative transaction thường thread-bound | Cấu hình transaction mới ở worker |
| "Tên thread giống nhau nghĩa là cùng request" | Worker tái sử dụng và tên có thể không unique | eventId, traceId, requestId |
| "Hai log gần nhau nghĩa là có thứ tự nghiệp vụ" | Async scheduling/log ingestion có thể đảo thứ tự | Sequence/aggregate version, timestamp, contract |
| "Tên thread đặt đúng là đủ quan sát" | Không có thông tin lỗi/latency/retry | Tracing, queue/executor metrics, ID |

Nếu cần biết có imperative transaction ở thời điểm listener chạy, có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` **cho mục tiêu chẩn đoán**, nhưng kết quả đó chỉ phản ánh transaction gắn với thread tại thời điểm gọi; không chứng minh commit sau này sẽ thành công và không thể thay thế kiểm tra dữ liệu DB.

Nếu cần kiểm tra security principal, sử dụng API Spring Security tương ứng và đảm bảo propagation phù hợp; tuyệt đối không log access token hoặc secret.

## 14. Kiểm thử tên thread và hành vi sync/async

### Unit test/integration test

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Listener thường và multicaster mặc định | Callback chạy trên cùng thread đang publish (trong cùng lượt gọi đồng bộ) |
| `@Async("eventExecutor")` và có `@EnableAsync` | Callback được nộp cho executor được chỉ định |
| Executor có prefix riêng | Tên thread callback bắt đầu bằng prefix phù hợp |
| Nhiều task async | Không assert thứ tự hoàn thành nếu không có cơ chế đồng bộ |
| Task bị từ chối | Log/metric rejection, không suy luận rằng listener đã chạy |
| Bật `CallerRunsPolicy` lúc pool bão hòa | Caller có thể thực thi task; phát hiện với thread name và latency |
| MDC propagation có TaskDecorator | Giá trị có mặt trong task và được dọn/restored sau đó |
| Async listener ném exception | Lỗi được quan sát ở đúng đường async, không giả định publisher nhận lỗi |
| Gắn transaction quanh publisher | Không mặc định worker async thừa hưởng transaction |

Với test bất đồng bộ, nên dùng `CountDownLatch`, `Awaitility` hoặc một cách chờ có **timeout**. Tránh `Thread.sleep(100)` rồi đoán chắc task đã chạy; máy CI chậm dễ gây flaky test.

Một assertion thích hợp:

```java
assertTrue(observedThreadName.startsWith("evt-worker-"));
```

Đây là **đoạn test minh họa**, giả định `observedThreadName` đã được thu thập an toàn qua cơ chế đồng bộ. Không cần assert chính xác suffix `-1` nếu hệ thống có thể tăng/giảm worker hoặc tạo task khác trước test.

### Test context propagation

Bài test nên thiết lập `MDC.put("traceId", "test-123")` trước lúc submit, xác nhận worker thấy giá trị khi có decorator, sau đó **xóa MDC phía publisher trong finally** và xác nhận một tác vụ độc lập không vô tình nhận giá trị cũ. Mục tiêu không phải chỉ "cho log đẹp", mà tránh rò dữ liệu giữa các request sử dụng chung pool.

## 15. Lỗi phổ biến khi chẩn đoán bằng thread name

**Lỗi 1 — Chỉ ghi tên thread trong publisher.** Điều đó không xác định thread thực thi listener. Ghi ở cả publish, listener START, listener END/FAILED.

**Lỗi 2 — Dùng thread name làm khóa định danh request.** Pool tái sử dụng và hai request có thể chạy nối tiếp trên cùng worker. Dùng eventId/correlationId thay thế.

**Lỗi 3 — Nhìn thấy thread khác rồi mặc định annotation @Async đúng.** Có thể task được chuyển bởi multicaster hoặc bởi `CompletableFuture` bên trong listener. Kiểm tra call path.

**Lỗi 4 — Nhìn thấy cùng thread rồi mặc định @Async sai.** Có thể executor đồng bộ hoặc `CallerRunsPolicy` khi quá tải; đo chính sách và tình trạng pool.

**Lỗi 5 — Không đặt tên executor.** Nhiều tên `pool-N-thread-M` khó truy ra chủ sở hữu. Đặt prefix theo mục đích với cấu hình bean rõ ràng.

**Lỗi 6 — Tin rằng MDC/transaction/security tự chuyển qua thread.** Các loại context có cơ chế khác nhau; chỉ propagate loại thật sự cần, không copy transaction ThreadLocal.

**Lỗi 7 — Không dọn MDC trong thread pool.** Dữ liệu của event trước có thể rò sang event sau; dùng `try/finally` hoặc giải pháp context propagation phù hợp.

**Lỗi 8 — Bỏ qua lỗi async vì publisher vẫn thành công.** Exception trong `void @Async` không tự lan về publisher. Ghi metric failure và xử lý rõ.

**Lỗi 9 — Chỉ dùng thread name để kết luận deadlock.** Cần stack trace, lock/resource state, pool/queue metrics và thời gian chờ.

**Lỗi 10 — Hardcode tên của container.** Prefix của Tomcat/Jetty hoặc các executor có thể đổi qua cấu hình/phiên bản. Dùng nhãn do chính ứng dụng kiểm soát và đo tại runtime.

## 16. Checklist vận hành

Khi điều tra một event bị chậm hoặc "chạy sai thread", hãy kiểm tra:

1. `eventType` và `eventId` đã được ghi ở publisher và listener chưa?
2. Đã ghi `Thread.currentThread().getName()` **ngay tại callback** chứ không chỉ trước khi submit chưa?
3. Ứng dụng đang dùng multicaster đồng bộ, `@Async`, multicaster executor hay nhiều tầng executor?
4. `@EnableAsync`, tên bean executor và proxy có đúng không?
5. Thread prefix có đủ phân biệt từng nhóm công việc không?
6. Callback có mất MDC, security principal, request context hay transaction do chuyển thread không?
7. Có dấu hiệu pool bão hòa, queue tăng, task rejection hay `CallerRunsPolicy` không?
8. Có đo thời lượng START→END, số lỗi, retry và tình trạng side effect không?
9. Nếu bị treo, đã xem thread dump/stack và trạng thái downstream chưa?
10. Test async có chờ có timeout và tránh assert tên thread không ổn định chưa?

**Ghi nhớ:** Thread name là **dấu vết về nơi code chạy**, không phải bằng chứng nghiệp vụ đã thành công. Với Spring Application Events, hãy ghi thread name ở publisher và listener, dùng prefix executor có ý nghĩa, nối log bằng eventId/traceId, đồng thời kiểm tra cách dispatch, context propagation, transaction, lỗi và tình trạng thread pool.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): listener đồng bộ mặc định và `@Async`, giới hạn exception/context.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `TaskDecorator` và `@Async`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): event observability và propagation của thread-bound context.
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): cấu hình executor, error handler.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): pattern và cấu hình logging khi chẩn đoán.
