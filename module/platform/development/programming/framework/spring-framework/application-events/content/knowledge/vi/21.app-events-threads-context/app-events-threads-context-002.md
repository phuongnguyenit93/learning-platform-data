# MDC và correlation ID trong Spring Framework Application Events

## 1. MDC và correlation ID trong nhóm Thread và context

Khi ứng dụng Spring xử lý một HTTP request hoặc một command nghiệp vụ, nó có thể phát `OrderPlaced`, `PaymentConfirmed` hoặc nhiều application events khác. Để điều tra sự cố, ta cần nhận ra những log nào thuộc **cùng một chuỗi xử lý**. Một **correlation ID** như `REQ-42` giúp nối log của controller, service, publisher và listener.

Tuy nhiên, listener Spring có thể chạy **cùng thread** hoặc **khác thread** với publisher. Nếu đặt correlation ID vào MDC trên request thread, rồi dispatch event qua executor, MDC của worker **không mặc nhiên có ID đó**. Nếu quên cleanup, worker thread được tái sử dụng còn có thể giữ ID của tác vụ trước, khiến log liên kết sai request.

Ví dụ log đúng:

```text
10:15:30 INFO  cid=REQ-42 [http-worker] Order placed ORD-42
10:15:30 INFO  cid=REQ-42 [event-worker-1] Notification queued
10:15:30 INFO  cid=REQ-42 [event-worker-2] Audit finished
```

Thời gian và thread name ở đây chỉ minh họa.

**Mục tiêu học tập**: hiểu MDC/ThreadLocal; phân biệt correlation ID với trace ID và event ID; cách propagate và restore MDC qua `TaskDecorator`; đặt correlation ID vào event payload; xử lý `@EventListener`, `@Async`, transactional listener và WebFlux đúng cách; kiểm thử thread reuse, exception, retry và bảo vệ dữ liệu.

MDC là ngữ cảnh hỗ trợ **logging/observability**. Nó **không phải** transaction context, security context, message broker hoặc nguồn dữ liệu nghiệp vụ bền vững.

## 2. MDC (Mapped Diagnostic Context) là gì?

`org.slf4j.MDC` là API để đặt những cặp key/value dạng chuỗi vào diagnostic context hiện hành. Logging backend như Logback có thể chèn các giá trị ấy vào log pattern. Ví dụ MDC key `correlationId` được hiển thị bằng `%X{correlationId}`.

| SLF4J API | Tác dụng | Cẩn trọng |
| --- | --- | --- |
| `MDC.put("correlationId", value)` | Đặt value ở thread hiện tại | Có thể ghi đè giá trị trước đó |
| `MDC.get("correlationId")` | Đọc value | Trả về `null` nếu thiếu |
| `MDC.remove("correlationId")` | Xóa riêng khóa | Không khôi phục giá trị bị ghi đè trước đó |
| `MDC.clear()` | Xóa toàn map MDC thread hiện tại | Không dùng tùy tiện trong nested scope |
| `MDC.getCopyOfContextMap()` | Chụp bản sao map hiện tại | Có thể trả `null` |
| `MDC.setContextMap(map)` | Thay context map bằng bản sao | Phải restore trạng thái cũ sau task |
| `MDC.putCloseable(key, value)` | Đặt value rồi xóa key khi close | Close xóa key chứ không tự khôi phục previous value |

MDC của những backend thông dụng có **tính thread-bound**: request thread và executor worker có thể có map riêng. Thread pool tái sử dụng worker, nên thiếu cleanup sẽ tạo context leak. Không dựa vào `InheritableThreadLocal` để truyền MDC trong pool đã tồn tại từ trước.

**Backend quan trọng:** thêm `slf4j-api` chỉ cung cấp facade. Để MDC hiện trong log cần runtime backend có hỗ trợ, ví dụ Logback, và cấu hình pattern/JSON logging đúng. Một provider không hỗ trợ MDC hoặc không hiển thị trường này có thể khiến `MDC.put(...)` không tạo ra kết quả log như mong muốn.

## 3. Correlation ID, request ID, trace ID, span ID, event ID

| ID | Diễn đạt điều gì? | Ví dụ |
| --- | --- | --- |
| **Correlation ID** | Nhiều bước cùng một luồng nghiệp vụ hoặc request | `REQ-42` cho request và các event con |
| **Request ID** | Một HTTP request hoặc inbound message cụ thể | Một lần gọi API |
| **Trace ID** | Các span thuộc cùng distributed trace | Được tracing system quản lý |
| **Span ID** | Một thao tác/đoạn công việc của trace | Một đoạn xử lý trong service |
| **Event ID** | Một lần xảy ra event logic | `EVT-200` dùng dedupe/retry |
| **Aggregate ID** | Một object nghiệp vụ | `ORD-42` có thể tạo nhiều event |

Correlation ID và trace ID **có thể liên hệ** với nhau, nhưng không phải luôn giống. Nơi đã triển khai OpenTelemetry hoặc Micrometer Tracing nên tận dụng trace/span IDs do hệ thống đó cung cấp, và chỉ tạo correlation ID riêng khi hợp đồng nghiệp vụ/quan sát yêu cầu.

Một correlation ID có thể xuất hiện trong nhiều domain events. **Không dùng correlation ID làm idempotency key cho tất cả events**, vì nhiều sự kiện hợp lệ cùng quy trình có thể bị loại nhầm. Event ID dùng để xác định **một event**; aggregate ID dùng để xác định **đối tượng domain**.

ID log không phải access token. Không suy ra quyền truy cập từ việc người gọi cung cấp đúng một correlation ID.

## 4. Spring Application Events và thread execution

### 4.1. Mặc định listener đồng bộ

`SimpleApplicationEventMulticaster` mặc định gọi listener trong **thread publisher**:

```text
http-worker  MDC(cid=REQ-42)
  |
  +--> applicationEventPublisher.publishEvent(OrderPlaced)
          |
          +--> @EventListener A (cùng http-worker)
          +--> @EventListener B (cùng http-worker)
  |
  +--> publisher tiếp tục
```

Các listener đồng bộ thường nhìn thấy MDC của publisher. Nhưng nếu listener A thay đổi MDC mà không restore, listener B và publisher sẽ thấy context sai. Đừng giả định một listener được phép sửa MDC toàn cục mà không chịu trách nhiệm cleanup.

### 4.2. Multicaster với TaskExecutor

Khi cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, các listener cho phép async có thể chạy ở một worker thread khác:

```text
http-worker  MDC(cid=REQ-42)
  |
  +--> publishEvent(OrderPlaced)
           |
           +--> queue Runnable
                   |
                   v
              event-worker-1
              MDC không tự có REQ-42
```

Spring không mặc định copy MDC từ thread publish sang worker. Trên Spring 6.1, `ApplicationListener.supportsAsyncExecution()` cho biết listener có phù hợp với async multicaster không. Transaction-synchronized listener là trường hợp cần ngữ cảnh gốc khi đăng ký synchronization, nên không nên xem việc set executor là cách chuyển toàn bộ transactional event listener sang background thread.

### 4.3. Async multicaster khác `@Async`

`@Async @EventListener` có thể thực thi bằng Spring async proxy, với executor do `@EnableAsync`, `AsyncConfigurer` hoặc cấu hình liên quan lựa chọn. Executor này **không nhất thiết là** executor của multicaster.

Tương tự, `CompletableFuture.supplyAsync(...)` với common pool, scheduler riêng và một message broker không tự thừa kế MDC. Muốn propagate phải cấu hình đúng **executor thực sự nhận task**, hoặc chuyển correlation ID trong dữ liệu rồi tạo logging scope ở consumer.

## 5. Correlation ID phải sống trong event payload khi cần

Domain/application event có thể dùng một immutable record:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    String correlationId
) {}
```

`OrderPlaced` không chứa `MDC`, `ThreadLocal` hay Servlet request. Nếu event được xử lý bất đồng bộ, replay sau restart hoặc gửi qua broker, correlation ID vẫn là một phần của thông điệp.

Phân biệt hai vai trò:

1. **Payload** chứa metadata/identity cần dùng lâu dài hoặc qua ranh giới thread/process: `eventId`, `orderId`, `correlationId`.
2. **MDC** làm giàu log tại nơi code đang chạy. Có thể dựng lại MDC từ `event.correlationId()`.

Đưa nguyên `MDC.getCopyOfContextMap()` vào payload thường là sai: map có thể có khóa nội bộ, dữ liệu nhạy cảm, chi tiết logging backend hoặc giá trị chỉ hợp lệ trong thread hiện tại. Chỉ truyền các trường được thiết kế thành hợp đồng sự kiện.

Nếu một đơn hàng phát hai domain events khác nhau, chúng có thể chia sẻ correlation ID nhưng mỗi event phải có event ID riêng. Khi retry **chính cùng event**, giữ event ID và correlation ID ổn định để consumer nhận diện duplicate và hỗ trợ log truy vết.

## 6. Tạo và cleanup MDC ở request boundary

Một hệ thống có thể tiếp nhận ID từ header `X-Correlation-ID` hoặc message envelope. Nhưng giá trị do client đưa vào là **untrusted input**:
- Giới hạn độ dài, ví dụ tối đa 128 ký tự.
- Giới hạn ký tự chữ/số và một số dấu đơn giản như `-` hoặc `_`.
- Từ chối ký tự xuống dòng/điều khiển để tránh log forging.
- Nếu thiếu hoặc không hợp lệ, tạo UUID mới hoặc xử lý theo hợp đồng API.
- Không dùng password, token, email khách hàng hay PII làm correlation ID.

Một scope trong service hoặc filter imperative:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("correlationId", validatedCorrelationId);
    orderService.placeOrder(command, validatedCorrelationId);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là **đoạn tích hợp**, cần `java.util.Map`, `org.slf4j.MDC`, `orderService` và ID đã validate. Với servlet filter, đặt scope quanh `chain.doFilter(...)` để mọi nhánh, kể cả exception, đều cleanup.

Capture/restore giúp giữ MDC của caller nếu logic đang lồng trong một scope khác. Chỉ `MDC.remove("correlationId")` phù hợp khi code biết chắc chính nó là chủ sở hữu của khóa đó và không cần khôi phục giá trị cũ.

## 7. MDC TaskDecorator: snapshot, install, restore

`ThreadPoolTaskExecutor` có `setTaskDecorator(TaskDecorator)`. Một decorator an toàn cho MDC phải:
1. Chụp bản sao MDC tại **thread submit task**, không phải khi worker đã bắt đầu chạy.
2. Trong worker, nhớ map MDC `previous`.
3. Set map `captured`, hoặc clear nếu producer không có context.
4. Thực thi task.
5. Trong `finally`, **restore previous** để tránh leak và bảo vệ nested scopes.

Mẫu class:

```java
public final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
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
    }
}
```

Đây là **class minh họa** cần `org.slf4j.MDC`, `java.util.Map` và `org.springframework.core.task.TaskDecorator`. Chương trình độc lập ở mục 8 có đầy đủ import và cấu hình Spring.

Điều quan trọng: nếu task A chụp `REQ-A` rồi main thread xóa MDC ngay sau publish, worker vẫn có bản sao `REQ-A`. Ngược lại, nếu task B được submit khi không có MDC, decorator phải clear context trước khi chạy B để không đọc nhầm `REQ-A`.

**Giới hạn:** decorator này chỉ truyền MDC. Nó không copy `EntityManager`, transaction, SecurityContext, Reactor Context hay tracing context nếu chúng không được capture bằng cơ chế phù hợp. Thread pool reuse không đồng nghĩa transaction reuse.

## 8. Ví dụ Java 17+ chạy được với Spring 6.1, SLF4J và Logback

Chương trình sử dụng:
- Spring Context 6.1.21 và `SimpleApplicationEventMulticaster`.
- `ThreadPoolTaskExecutor` pool size = 1 để dễ quan sát thread reuse.
- `MdcTaskDecorator` chụp và restore MDC.
- Hai `OrderPlaced` events mang `REQ-A` và `REQ-B`.
- `CountDownLatch` chờ listener hoàn tất thay vì `Thread.sleep`.

Chương trình không dùng Spring Boot, web server hoặc DB. Nó chứng minh propagation của **logging context**, không chứng minh transaction hoặc delivery bền vững.

Cấu trúc:

```text
mdc-spring-events/
├── build.gradle
└── src/main/java/demo/MdcEventsDemo.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.slf4j:slf4j-api:2.0.13'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.6'
}

application {
    mainClass = 'demo.MdcEventsDemo'
}
```

`src/main/java/demo/MdcEventsDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.slf4j.MDC;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class MdcEventsDemo {

    public record OrderPlaced(String orderId, String correlationId) {}

    public static final class MdcTaskDecorator implements TaskDecorator {
        @Override
        public Runnable decorate(Runnable task) {
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
        }
    }

    public static final class Signal {
        private final CountDownLatch latch = new CountDownLatch(2);

        public void handled() {
            latch.countDown();
        }

        public void awaitBoth() throws InterruptedException {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Events not completed");
            }
        }
    }

    public static final class OrderListener {
        private final Signal signal;

        public OrderListener(Signal signal) {
            this.signal = signal;
        }

        @EventListener
        public void on(OrderPlaced event) {
            try {
                System.out.println(
                    "HANDLE order=" + event.orderId()
                    + " payloadCid=" + event.correlationId()
                    + " mdcCid=" + MDC.get("correlationId")
                );
            } finally {
                signal.handled();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Signal signal() {
            return new Signal();
        }

        @Bean
        public OrderListener orderListener(Signal signal) {
            return new OrderListener(signal);
        }

        @Bean
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-worker-");
            executor.setTaskDecorator(new MdcTaskDecorator());
            return executor;
        }

        @Bean(name = AbstractApplicationContext
                .APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {
            SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            MDC.clear();

            try {
                MDC.put("correlationId", "REQ-A");
                context.publishEvent(new OrderPlaced("ORD-1", "REQ-A"));
            } finally {
                MDC.remove("correlationId");
            }

            try {
                MDC.put("correlationId", "REQ-B");
                context.publishEvent(new OrderPlaced("ORD-2", "REQ-B"));
            } finally {
                MDC.remove("correlationId");
            }

            context.getBean(Signal.class).awaitBoth();
            System.out.println("MAIN mdcCid="
                    + MDC.get("correlationId"));
            MDC.clear();
        }
    }
}
```

Lệnh chạy với JDK 17+ và Gradle:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng**:

```text
HANDLE order=ORD-1 payloadCid=REQ-A mdcCid=REQ-A
HANDLE order=ORD-2 payloadCid=REQ-B mdcCid=REQ-B
MAIN mdcCid=null
```

Giải thích:

1. Spring tìm bean có tên `applicationEventMulticaster` và dùng nó thay multicaster mặc định.
2. Executor có một worker thread; các task listener cho hai event được xếp theo thứ tự publish.
3. Ở mỗi `publishEvent(...)`, decorator chụp MDC trên main thread trước khi `finally` xóa khóa.
4. Worker cài captured map, nên `MDC.get("correlationId")` trong listener khớp với `event.correlationId()`.
5. Khi một task kết thúc, decorator restore previous map của worker, tránh `REQ-A` rò rỉ sang `REQ-B`.
6. `Signal.awaitBoth()` đợi cả hai handler đi tới điểm đếm; main thread đã cleanup nên dòng cuối in `null`.
7. Với một listener, một worker và hai lần publish nối tiếp, các dòng `HANDLE` xuất hiện theo thứ tự đã nêu. Ứng dụng nhiều threads/listeners không có bảo đảm ordering tương tự.

Nếu môi trường bật framework logging bổ sung, màn hình có thể có thêm log ngoài ba dòng nghiệp vụ. Phần dự đoán chỉ khẳng định ba dòng này.

## 9. Cấu hình Logback để thấy correlation ID

Trong demo, `System.out` cho phép đối chiếu chính xác. Ứng dụng thật thường dùng `Logger` và MDC pattern hoặc structured logging. Ví dụ file **tùy chọn** `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] cid=%X{correlationId:-none} %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đoạn code ghi log tích hợp:

```java
private static final Logger log =
    LoggerFactory.getLogger(OrderListener.class);

// Bên trong listener:
log.info("Handled order {}", event.orderId());
```

Cần import `org.slf4j.Logger`, `LoggerFactory`. Pattern đọc MDC của **thread đang log**. Nếu payload có correlation ID nhưng MDC chưa được set, pattern sẽ in `cid=none`. Điều đó cho thấy lý do cần cả event data và logging scope.

Không log full object event khi event có PII. Trong JSON logging, chuẩn hóa một khóa `correlationId` và tránh nhầm với `traceId`. Đặc biệt không đẩy từng correlation ID thành label của metrics tổng hợp nếu không kiểm soát cardinality.

## 10. Dựng lại MDC từ event payload ở consumer

Một event được xử lý sau restart, từ broker hoặc trên executor không có decorator không thể kế thừa MDC của request ban đầu. Nếu payload mang correlation ID, tạo logging scope mới:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        MDC.put("correlationId", event.correlationId());
        // Ghi log hoặc xử lý nghiệp vụ.
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
```

Đây là **đoạn tích hợp** với `OrderPlaced` record, `MDC` và `Map` đã import. Nếu event đến từ bên ngoài, validate correlation ID trước khi đặt vào MDC. Nếu handler phát event con, thường giữ correlation ID để nối workflow, cấp event ID mới cho event mới và dùng causation ID khi cần biết event nào gây ra event con.

Có thể dùng cả decorator **và** scope từ payload: decorator phục vụ chuyển context nội bộ qua executor, payload phục vụ hợp đồng truy vết lâu dài. Nhưng phải quy định rõ nguồn dữ liệu ưu tiên nếu MDC nhận từ thread và correlation ID trong event không khớp; mismatch nên được log và điều tra thay vì âm thầm chuyển định danh.

## 11. MDC không phải transaction hoặc security context

Copy một `Map<String,String>` MDC không truyền theo:
- JDBC connection, JPA `EntityManager` hoặc Hibernate Session.
- `TransactionSynchronizationManager` / transaction status.
- `SecurityContext` hoặc quyền của user.
- Reactor Context và reactive transaction.
- Độ bền của event, retry và chính sách idempotency.

Vì vậy, listener async có thể **log đúng correlation ID** nhưng thực thi ngoài transaction của publisher. Nếu cần thao tác database, listener phải được thiết kế transaction riêng cho trường hợp đó.

### @TransactionalEventListener

`@TransactionalEventListener` hỗ trợ phase `BEFORE_COMMIT`, `AFTER_COMMIT` (mặc định), `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Với transaction imperative, listener phải đăng ký synchronization khi transaction đang hoạt động. Trong Spring 6.1, transactional listener không bị multicaster đưa sang executor bất chấp hỗ trợ async; không coi `setTaskExecutor(...)` là cách làm transactional event handling “tự động hậu commit và bất đồng bộ”.

Nếu handler tự gọi tác vụ `@Async` sau commit, MDC và transaction trên thread mới cần được thiết kế riêng. Lỗi sau commit không rollback được transaction gốc.

Đối với event cần gửi chắc chắn, `ApplicationEventPublisher` + MDC chưa đủ. Mẫu **transactional outbox** ghi intent gửi event vào DB trong cùng transaction, để worker retry và consumer dedupe theo event ID. Correlation ID giúp truy vết cả các lần retry; nó không biến event thành message bền vững.

## 12. Reactor/WebFlux và Micrometer context propagation

Trong Spring WebFlux, một `Mono`/`Flux` có thể chuyển thread nhiều lần trong cùng subscription. Reactive transaction nằm trong **Reactor Context**, không phải MDC ThreadLocal. Gọi `MDC.put(...)` trước khi tạo `Mono` không bảo đảm logging statement ở downstream operator thấy cùng map.

Reactor Context minh họa:

```java
Mono<String> operation = Mono.deferContextual(ctx -> {
    String cid = ctx.get("correlationId");
    return Mono.just("request=" + cid);
}).contextWrite(c ->
    c.put("correlationId", validatedCorrelationId)
);
```

Đây là **mã tích hợp** cần Reactor type, ID đã validate và subscription. Giá trị trong Reactor Context có thể đi theo reactive chain, nhưng để Logback `%X{correlationId}` thấy nó, cần bridge phù hợp giữa Reactor Context và MDC.

Spring Framework 6.1 có `ContextPropagatingTaskDecorator` dùng Micrometer Context Propagation cho logging/observation context khi task chuyển thread. Muốn dùng hiệu quả phải cấu hình đúng dependency, registry và accessor; không mặc định mọi MDC key hoặc reactive transaction tự được chuyển. Việc snapshot/restore có overhead, nhất là với nhiều tác vụ ngắn.

Nếu dự án đã dùng Micrometer Observation/Tracing và Reactor automatic context propagation, ưu tiên tích hợp observability chính thức thay vì tự cài global hooks có thể làm bẩn MDC giữa các signal. TaskDecorator thủ công ở mục 7 giải quyết executor thread, **không** tự giải quyết toàn bộ reactive chain.

## 13. Bảng chọn phương án theo tình huống

| Tình huống | MDC có theo tự động? | Giải pháp |
| --- | --- | --- |
| `@EventListener` đồng bộ | Có trong cùng thread, nếu scope đang tồn tại | Restore khi thay đổi MDC |
| Multicaster async | Không | `TaskDecorator` trên executor multicaster |
| `@Async @EventListener` | Không mặc định | Decorator trên executor `@Async` thực tế |
| `CompletableFuture` common pool | Không | Truyền executor có decorator hoặc context tường minh |
| Message broker | Không qua process boundary | Correlation ID trong header/payload, tái tạo MDC tại consumer |
| Transactional listener | Phụ thuộc thread/scope | Giữ ID trong payload, không suy ra transaction từ MDC |
| WebFlux/reactive | Không chỉ bằng ThreadLocal | Reactor Context + observability bridge |
| Event retry/replay | Không giữ MDC cũ | Event ID và correlation ID ổn định, tạo scope mới |

## 14. Các lỗi thường gặp

1. **Nhầm MDC là thuộc tính của Spring event:** MDC thuộc execution thread, không phải event.
2. **Thiếu cleanup ở request hoặc worker:** dẫn tới leak correlation ID sang request khác.
3. **Dùng `MDC.clear()` trong nested scope mà không restore:** làm mất MDC của caller.
4. **Chỉ ghi correlation ID vào MDC, không ghi vào event:** worker sau restart không biết ID gốc.
5. **Đưa cả MDC map vào payload:** vô tình lộ dữ liệu hoặc khóa backend-specific.
6. **Sử dụng correlation ID làm event ID:** dedupe sai khi một request phát nhiều event.
7. **Đặt decorator nhầm executor:** multicaster, `@Async`, scheduler và common pool có thể khác.
8. **Copy MDC và tưởng transaction tự chuyển:** transaction state không tự đi theo ThreadLocal strings.
9. **Coi trace ID luôn bằng correlation ID:** hai hệ thống định danh có lifecycle/hợp đồng riêng.
10. **Không validate ID từ HTTP header:** có nguy cơ log injection và ngập log.
11. **Dùng `Thread.sleep` chờ listener trong test:** không đáng tin và dễ flaky.
12. **Không giám sát exception async:** log đúng ID không chứng minh task thành công.
13. **Đặt MDC tùy tiện trong Reactor operator:** dễ mất hoặc rò rỉ khi đổi thread.
14. **Coi Spring event cộng MDC là durable queue:** process crash có thể làm mất tác vụ.
15. **Truyền authentication token trong correlation ID:** mất an toàn dữ liệu.

## 15. Kiểm thử đầy đủ

### Cùng thread

Tạo MDC `REQ-A`, publish event đồng bộ, assert listener đọc đúng. Cho handler thay đổi MDC rồi assert scope caller được restore. Test thêm nhánh exception.

### Executor dùng một worker nhiều lần

Publish `REQ-A` và `REQ-B`, xác minh mỗi listener đọc đúng ID của event tương ứng. Dùng `CountDownLatch` hoặc future để đợi hoàn tất; không dựa vào thời gian ngủ.

### Task không có MDC

Sau task `REQ-A`, gửi một task không có MDC qua cùng executor. Assert worker đọc `null` cho correlation ID; không bị rò rỉ context task trước.

### Exception trong task

Cho task ném exception rồi chạy task tiếp theo cùng worker. Assert MDC được restore trong `finally` và lỗi được chuyển tới cơ chế giám sát phù hợp.

### Executor khác

Tạo listener `@Async` với executor riêng. Xác minh decorator gắn vào multicaster executor không tự áp dụng cho pool này; thiết kế cấu hình propagation riêng.

### Broker/retry

Serialize ID theo message contract, consumer validate và tạo MDC scope. Retry cùng event giữ nguyên `eventId`; event mới trong cùng workflow dùng event ID mới nhưng có thể giữ correlation ID.

### Bảo mật

Thử correlation ID dài, chứa newline hoặc ký tự điều khiển. Xác nhận cơ chế validate bỏ hoặc thay ID; log không chứa token, email, PII trái chính sách.

## 16. Checklist triển khai

- [ ] Correlation ID được tạo/validate nhất quán ở request hoặc message boundary.
- [ ] Correlation ID không phải token xác thực, không chứa dữ liệu cá nhân.
- [ ] MDC được set theo scope, restore trong `finally`.
- [ ] Event cần xử lý muộn hoặc qua service có correlation ID tường minh.
- [ ] `eventId` và `correlationId` có mục đích khác nhau; giữ ổn định khi retry đúng event.
- [ ] `@EventListener` đồng bộ không làm bẩn MDC của caller/listener khác.
- [ ] Executor async thực tế đã có `TaskDecorator` nếu cần propagation.
- [ ] Decorator capture ở submit thread, restore trên worker.
- [ ] Test thread reuse, task thiếu MDC, exception và cleanup.
- [ ] Không nhầm MDC với transaction/security/reactive context.
- [ ] Với WebFlux, dùng Reactor Context và tracing integration đúng cách.
- [ ] Logging pattern hoặc JSON đã hiển thị correlation ID, không rò rỉ PII.
- [ ] Nếu event phải được giao bền vững, có outbox/queue và cơ chế retry/idempotency.

**Ghi nhớ:** correlation ID là dữ liệu giúp nối **các bước cùng một luồng xử lý**; MDC là cơ chế đặt dữ liệu ấy cho logger trên **thread hiện tại**. Spring Application Events có thể xử lý listener đồng bộ hoặc bất đồng bộ. Khi chuyển thread, hãy propagate và cleanup MDC một cách tường minh; đồng thời đặt correlation ID vào immutable event payload nếu cần truy vết lâu dài hoặc qua process khác.

## Tài liệu tham khảo

- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1.21 — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring 6.1 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html)
- [Logback MDC Manual](https://logback.qos.ch/manual/mdc.html)
