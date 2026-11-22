# TaskDecorator cho logging context trong Spring Framework Application Events

## 1. Vấn đề cần giải quyết

Một request HTTP xử lý đơn hàng thường gắn các thông tin như `traceId`, `requestId` hoặc `correlationId` vào **Mapped Diagnostic Context (MDC)** để mỗi dòng log có thể liên kết với cùng một yêu cầu. Khi service phát `OrderPlaced` bằng `ApplicationEventPublisher.publishEvent(...)`, một `@EventListener` chạy đồng bộ trên cùng thread thường đọc được MDC.

Nhưng listener bất đồng bộ sử dụng `@Async` hoặc executor được cấu hình cho `ApplicationEventMulticaster` lại chạy trên một **worker thread khác**. MDC thường được lưu theo `ThreadLocal`, nên bản đồ ngữ cảnh của publisher **không tự động truyền** sang worker. Một listener có thể xử lý đúng dữ liệu nghiệp vụ nhưng log lại mất `traceId`.

```text
Request thread "http-1"
    MDC.traceId = trace-A
        |
        | publishEvent(OrderPlaced)
        v
Spring Event Multicaster
        |
        | gọi @Async("eventExecutor") trên listener
        v
ThreadPoolTaskExecutor
        |
        | submit task
        v
Worker thread "events-1"
    MDC.traceId = ?         <-- không tự copy
        |
        v
log.info("Order event processed")
```

Nếu một worker còn giữ MDC từ task trước vì code thiếu dọn dẹp, log của `OrderPlaced("ORD-B")` có thể thậm chí bị gắn nhầm `trace-A`. Điều này nguy hiểm với hệ thống nhiều người dùng/tenant, vì log không chỉ khó điều tra mà còn có thể gây hiểu nhầm về nguồn của dữ liệu.

**`TaskDecorator` là điểm mở rộng của Spring để bọc task được thực thi bởi executor.** Ta sử dụng nó để chụp MDC lúc gửi task, cài vào worker lúc xử lý, rồi **khôi phục context cũ trong `finally`**.

Mục tiêu của bài: hiểu vòng đời MDC giữa publisher và listener, viết decorator an toàn, cấu hình đúng `ThreadPoolTaskExecutor`, kiểm chứng bằng chương trình Java 17 chạy được, và phân biệt logging context với transaction/security/tracing.

## 2. Các thuật ngữ và ranh giới

| Khái niệm | Vai trò | Cần nhớ |
| --- | --- | --- |
| `SLF4J MDC` | Map khóa–giá trị phục vụ log của thread đang chạy | Không phải kho dữ liệu nghiệp vụ |
| `ThreadLocal` | Nơi dữ liệu gắn với từng thread | Worker trong pool thường không có MDC của thread submit |
| `TaskDecorator` | Bọc `Runnable` trước khi executor thực thi | Capture, install, restore execution context |
| `ThreadPoolTaskExecutor` | Pool Spring quản lý | Hỗ trợ `setTaskDecorator(...)` |
| `@Async` | Chuyển method call qua Spring async infrastructure | Cần `@EnableAsync` và đường gọi qua proxy |
| `@EventListener` | Đăng ký callback nhận event theo kiểu | Có thể đồng bộ hoặc được gửi sang executor |
| `ApplicationEventPublisher` | Phát event trong context | Không tự lưu event bền vững |

Chú ý: `TaskDecorator` **không nằm trên lớp event**, không thay đổi payload và không tự “đăng ký” listener. Nó được gắn **vào executor**. Nếu ứng dụng có nhiều executor, phải chọn chính xác nơi muốn truyền MDC.

### Hợp đồng của TaskDecorator

Interface `org.springframework.core.task.TaskDecorator` có phương thức:

```java
Runnable decorate(Runnable runnable);
```

Đây là chữ ký API rút gọn. Spring gọi decorator khi chuẩn bị thực thi task và dùng `Runnable` được trả về làm wrapper. Theo Javadoc, đối tượng đầu vào **có thể là callback đã được hạ tầng bọc**, không nhất thiết chính là `Runnable` ban đầu mà ứng dụng gửi.

Decorator phù hợp để tạo phạm vi execution context quanh `runnable.run()`. Nó không phải vị trí duy nhất để xử lý mọi exception của tác vụ, đặc biệt khi tác vụ được bọc trong `FutureTask`.

## 3. Nguyên lý capture – install – run – restore

Một task thường trải qua hai thời điểm tách biệt:

- **Submission time:** thread của publisher gọi `publishEvent(...)`; hạ tầng `@Async` nộp task cho executor.
- **Execution time:** worker lấy task từ queue và thực hiện phần thân listener.

Nếu MDC thay đổi **sau submission nhưng trước execution**, listener vẫn cần thấy snapshot **lúc submission**. Ví dụ publisher gửi A dưới `trace-A`, đổi MDC sang `trace-B` để gửi B, rồi xóa MDC; task A có thể lúc đó mới bắt đầu chạy. A vẫn phải thấy `trace-A`.

Sơ đồ an toàn:

```text
Publisher thread                       Worker thread
--------------------------------      -------------------------
MDC = {traceId: trace-A}
        |
        | executor nhận task
        v
decorate(delegate)
captured = copy(MDC)
        |
        +-----------------------------> Runnable.run()
                                          previous = copy(MDC)
                                          install(captured)
                                          try {
                                              delegate.run()
                                          } finally {
                                              restore(previous)
                                          }
```

Có **bốn quy tắc** quan trọng:

1. Capture từ thread **gửi task**, không phải worker: worker chưa có thông tin publisher.
2. Phải copy MDC thành **snapshot**, không giữ dữ liệu mutable để publisher thay đổi bên ngoài.
3. Nếu caller **không có MDC**, worker phải dùng context rỗng khi xử lý task ấy, thay vì giữ context cũ.
4. Phải khôi phục context worker ở `finally`, kể cả khi listener ném exception.

## 4. Tự viết MDC TaskDecorator

Một implementation gọn và đúng:

```java
package example;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        // Thực thi khi task được gửi từ publisher.
        Map<String, String> captured =
                MDC.getCopyOfContextMap();

        return () -> {
            // Thực thi trên worker khi task bắt đầu.
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
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

Đây là class có thể dùng trong dự án Spring, nhưng để kiểm chứng phải cung cấp executor, một logging backend có hỗ trợ MDC và một task thực sự qua pool. Ví dụ hoàn chỉnh nằm ở mục 6.

### 4.1. Chụp bản sao

`MDC.getCopyOfContextMap()` trả về một `Map<String,String>` là **bản sao context map hiện có**, hoặc `null` khi không có map. Không được gọi phương thức này **chỉ bên trong lambda worker** rồi kỳ vọng đọc được MDC publisher: lúc đó thread đã khác.

### 4.2. Cài context hoặc clear

Nếu captured khác `null`, `MDC.setContextMap(captured)` thay thế MDC hiện có trên worker. Nếu captured là `null`, phải gọi `MDC.clear()`. Nhánh null đặc biệt quan trọng trong thread pool tái sử dụng worker để tránh log của một request không có traceId bị gắn nhầm ID từ request trước.

### 4.3. Khôi phục previous

Không nên chỉ clear vô điều kiện sau khi chạy. Worker có thể nằm trong một wrapper khác đã cài context hợp lệ, hoặc executor có thể thực thi inline trong một chính sách nhất định. Mẫu **save → replace → restore** cho phép decorator phối hợp tốt hơn với context bên ngoài.

### 4.4. Dùng finally

Nếu `delegate.run()` thất bại, `finally` vẫn chạy và khôi phục MDC. Một listener bất đồng bộ không được phép để lại `traceId` trong thread được đưa trở lại pool.

**Bản phản ví dụ:**

```java
return () -> {
    MDC.setContextMap(captured);
    delegate.run();
    // Sai: không restore khi chạy xong hoặc ném lỗi.
};
```

Đoạn này cố tình sai và **không dùng trong production**. Nó vừa không bảo vệ worker khi task lỗi, vừa có thể làm mất/bẩn ngữ cảnh cũ.

## 5. Cấu hình decorator vào đúng executor

Trong một class `@Configuration`:

```java
@Bean("eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("events-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    return executor;
}
```

Sau đó listener:

```java
@Async("eventExecutor")
@EventListener
public void onOrder(OrderPlaced event) {
    log.info("Handle orderId={}", event.orderId());
}
```

Cần bật `@EnableAsync`. Listener phải là Spring bean có thể được proxy; ví dụ phương thức `public` nằm trong class không `final` và được gọi qua Spring event infrastructure, không phải qua `this.onOrder(...)` tự gọi nội bộ.

Khi `@Async("eventExecutor")` có tên executor, Spring tra cứu bean executor tương ứng theo bean name/qualifier. Nếu sử dụng `@Async` không chỉ định tên, nó đi qua cơ chế chọn executor mặc định; **không tự biết** rằng ứng dụng muốn dùng pool vừa được gắn decorator.

Với Spring bean `ThreadPoolTaskExecutor`, context quản lý việc khởi tạo và shutdown của executor. Không nên tạo `new ThreadPoolTaskExecutor()` cho mỗi event hoặc gửi task trên một executor ngoài hệ thống rồi mong decorator trên bean khác vẫn có tác dụng.

## 6. Ví dụ Java 17 + Maven: ba sự kiện qua cùng một worker

Ví dụ sau chứng minh **snapshot MDC theo từng task** và **không rò rỉ context** khi worker thread được tái sử dụng. Không cần web server hay database.

Ba event:

- `ORD-A` được publish dưới `traceId=trace-A`.
- `ORD-B` được publish dưới `traceId=trace-B`.
- `ORD-C` được publish khi publisher **không có traceId**.

Executor có `corePoolSize=1`, `maxPoolSize=1` nên cả ba task chạy trên cùng một worker. Listener được đánh dấu `@Async("eventExecutor")` và `@EventListener`. Kết quả được ghi vào `ConcurrentHashMap`; `CountDownLatch` đợi đủ cả ba callback trước khi kiểm tra.

### Cấu trúc thư mục

```text
mdc-event-context/
├── pom.xml
└── src/main/
    ├── java/example/MdcEventDemo.java
    └── resources/logback.xml
```

### Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>mdc-event-context</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.MdcEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### Tệp src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>trace=%X{traceId:-none} thread=%thread %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.events" level="INFO" additivity="false">
        <appender-ref ref="STDOUT"/>
    </logger>

    <root level="ERROR">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%X{traceId:-none}` là pattern của Logback để in MDC key `traceId`, và in `none` khi không có. `%thread` giúp kiểm tra logger chạy trên thread nào. Logback ở đây là backend SLF4J thực sự hỗ trợ MDC; nếu thay bằng backend không hỗ trợ MDC, kết quả sẽ khác.

### Tệp src/main/java/example/MdcEventDemo.java

```java
package example;

import java.util.HashSet;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class MdcEventDemo {

    public record OrderPlaced(String orderId) {}

    public static final class MdcTaskDecorator implements TaskDecorator {
        @Override
        public Runnable decorate(Runnable task) {
            Map<String, String> captured =
                    MDC.getCopyOfContextMap();

            return () -> {
                Map<String, String> previous =
                        MDC.getCopyOfContextMap();
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

    public static final class Evidence {
        private final CountDownLatch done =
                new CountDownLatch(3);
        private final Map<String, String> traces =
                new ConcurrentHashMap<>();
        private final Map<String, String> threads =
                new ConcurrentHashMap<>();

        public void record(String orderId, String traceId,
                           String workerThread) {
            traces.put(orderId,
                    traceId == null ? "<none>" : traceId);
            threads.put(orderId, workerThread);
            done.countDown();
        }

        public void awaitAll() throws InterruptedException {
            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async listeners timed out");
            }
        }

        public String traceOf(String orderId) {
            return traces.get(orderId);
        }

        public boolean sameWorkerForAll() {
            return threads.size() == 3
                    && new HashSet<>(threads.values()).size() == 1;
        }
    }

    // Class này không final để Spring có thể tạo proxy @Async.
    public static class OrderListener {
        private static final Logger log =
                LoggerFactory.getLogger("demo.events");
        private final Evidence evidence;

        public OrderListener(Evidence evidence) {
            this.evidence = evidence;
        }

        @Async("eventExecutor")
        @EventListener
        public void handle(OrderPlaced event) {
            String trace = MDC.get("traceId");
            log.info("order={}", event.orderId());
            evidence.record(
                    event.orderId(),
                    trace,
                    Thread.currentThread().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListener orderListener(Evidence evidence) {
            return new OrderListener(evidence);
        }

        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.setTaskDecorator(new MdcTaskDecorator());
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Evidence evidence = context.getBean(Evidence.class);

            try {
                MDC.put("traceId", "trace-A");
                context.publishEvent(new OrderPlaced("ORD-A"));

                MDC.put("traceId", "trace-B");
                context.publishEvent(new OrderPlaced("ORD-B"));

                MDC.clear();
                context.publishEvent(new OrderPlaced("ORD-C"));
            } finally {
                // Cleanup cả publisher thread khi kết thúc.
                MDC.clear();
            }

            evidence.awaitAll();

            System.out.println(
                    "A trace=" + evidence.traceOf("ORD-A"));
            System.out.println(
                    "B trace=" + evidence.traceOf("ORD-B"));
            System.out.println(
                    "C trace=" + evidence.traceOf("ORD-C"));
            System.out.println(
                    "Worker reused=" + evidence.sameWorkerForAll());
            System.out.println(
                    "Publisher MDC cleared="
                            + (MDC.get("traceId") == null));
        }
    }
}
```

### Lệnh chạy

Trong thư mục có `pom.xml`, sử dụng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Các dòng log của logger `demo.events` trong cấu hình demo** (pool một worker):

```text
trace=trace-A thread=events-1 order=ORD-A
trace=trace-B thread=events-1 order=ORD-B
trace=none thread=events-1 order=ORD-C
```

**Các dòng `System.out` sau khi cả ba listener hoàn tất:**

```text
A trace=trace-A
B trace=trace-B
C trace=<none>
Worker reused=true
Publisher MDC cleared=true
```

Số sau tiền tố `events-` có thể khác nếu tạo thêm task/thread hoặc đổi cấu hình; điều quan trọng là cùng một worker và MDC của từng event là chính xác. Các log phụ của Maven, Logback hoặc framework (nếu có) không thuộc những dòng kết quả nghiệp vụ này.

### Giải thích kết quả

1. Khi `ORD-A` được publish, MDC trên luồng publisher là `trace-A`. Decorator capture bản sao tại thời điểm task A được nộp.
2. Publisher đổi MDC sang `trace-B` rồi nộp B. Dù worker chưa xử lý A, giá trị đã capture của A **không đổi**.
3. Trước C, publisher gọi `MDC.clear()`. Decorator capture `null` hoặc map rỗng và cài ngữ cảnh tương ứng để worker **không kế thừa trace-B**.
4. Do pool có một thread, ba task chạy trên cùng worker, chứng minh cleanup giữa các task có ý nghĩa thực tế.
5. `CountDownLatch` chờ cả ba callback trước khi main đọc `ConcurrentHashMap`. Không cần `Thread.sleep` tùy ý.
6. Các thao tác `record` chạy trước `countDown`; sau khi `awaitAll` thành công, chương trình có dữ liệu hoàn tất để in.
7. `try-with-resources` đóng Spring context sau khi các task kiểm thử đã hoàn thành.

Nếu executor không xử lý đủ ba task trong 10 giây, chương trình ném exception timeout thay vì báo kết quả thành công giả.

## 7. Nếu bỏ TaskDecorator thì sao?

Giữ nguyên listener `@Async` nhưng bỏ:

```java
executor.setTaskDecorator(new MdcTaskDecorator());
```

Với một worker mới không có cơ chế propagation khác, log thường không thấy MDC của publisher:

```text
trace=none thread=events-1 order=ORD-A
trace=none thread=events-1 order=ORD-B
trace=none thread=events-1 order=ORD-C
```

Đây là kết quả **minh họa khi không có cơ chế context propagation nào khác**. Nếu ứng dụng đã dùng Micrometer context propagation, executor instrumented hoặc decorator khác, phải kiểm tra cấu hình thật.

Ngược lại, khi `@EventListener` chạy đồng bộ trên chính thread publisher với multicaster mặc định, MDC có thể được đọc trực tiếp mà không cần decorator. Một test chỉ dùng listener đồng bộ **không chứng minh** propagation qua thread pool.

## 8. Gắn decorator ở đâu trong Application Events?

Có hai cách thường gặp để chuyển listener sang executor.

### 8.1. @Async trên phương thức listener

```java
@Async("eventExecutor")
@EventListener
public void onOrder(OrderPlaced event) {
    // Chạy qua executor được chọn bởi @Async.
}
```

MDC cần được propagate qua **executor của async method**. Nếu `eventExecutor` có decorator, task nhận context. Nếu `@Async("emailExecutor")` chọn bean khác không gắn decorator, cấu hình trên `eventExecutor` **không ảnh hưởng** bean kia.

Với nhiều pool, nên có factory hoặc convention cấu hình decorator nhất quán, hoặc cấu hình tường minh từng bean. Không nên tin rằng chỉ có một `TaskDecorator` bean trong context là mọi executor tự động sử dụng nó.

### 8.2. Executor của SimpleApplicationEventMulticaster

Ứng dụng có thể thiết lập:

```java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();

multicaster.setTaskExecutor(sharedTaskExecutor);
```

Đây là đoạn tích hợp cần `sharedTaskExecutor` và wiring multicaster phù hợp; không phải phần của chương trình mục 6. Trong trường hợp này, listener đủ điều kiện được multicast bất đồng bộ thông qua **executor của multicaster**. Nếu executor đó là `ThreadPoolTaskExecutor` có decorator, MDC được capture tại nơi multicaster nộp task.

Nếu vừa cấu hình executor tại multicaster **vừa** gắn `@Async` ở listener, có thể phát sinh **hai lần chuyển luồng**. Mỗi tầng chuyển luồng cần được xét riêng về propagation. Không dùng cả hai chỉ để “đảm bảo chắc chắn là async”.

### 8.3. Listener phát tiếp event khác

Nếu một listener đang chạy trên worker có MDC đã được decorator cài và gọi `publisher.publishEvent(new ChildEvent(...))`, thì với multicaster đồng bộ, listener của event dẫn xuất có thể chạy trên **chính worker** đó và thấy MDC hiện tại.

Nếu listener của event con tiếp tục dùng `@Async("otherExecutor")`, lại xuất hiện ranh giới thread thứ hai. Để giữ traceId, decorator phải được cấu hình ở `otherExecutor` hoặc dùng một cơ chế context propagation tương đương.

## 9. ContextPropagatingTaskDecorator của Spring 6.1+

Spring Framework 6.1 giới thiệu `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, dùng **Micrometer Context Propagation** để capture và restore những ngữ cảnh có integration phù hợp. Nó có ích cho logging/tracing/observation khi ứng dụng dùng Micrometer và context registry.

Cấu hình minh họa:

```java
@Bean("observedExecutor")
public ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("observed-");
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    return executor;
}
```

Đoạn này cần import `ContextPropagatingTaskDecorator`, `ThreadPoolTaskExecutor` và `@Bean`, đồng thời có `micrometer-context-propagation` cùng các integration/accessor thích hợp trên classpath/configuration. Đây là ví dụ API, không phải chương trình chạy độc lập.

**Không được suy ra:** tạo `new ContextPropagatingTaskDecorator()` sẽ tự động copy **mọi khóa MDC tùy ý** trong mọi logging backend. Những kiểu ThreadLocal cần propagate phải có `ThreadLocalAccessor`/đăng ký phù hợp và tích hợp thực tế. Truyền context của Micrometer Observation không đồng nghĩa mọi logging context của thư viện tùy ý đều được bao phủ.

Cách lựa chọn:

| Nhu cầu | Giải pháp |
| --- | --- |
| Chỉ cần sao chép toàn bộ SLF4J MDC map qua một executor | `MdcTaskDecorator` đơn giản, dễ test |
| Cần phối hợp nhiều context quan sát trong hệ thống Micrometer | Đánh giá `ContextPropagatingTaskDecorator` và accessors |
| Phối hợp nhiều decorator | Kiểm tra thứ tự wrapper, phạm vi và cleanup |
| Khối lượng task cực nhỏ/rất lớn | Đo chi phí capture/restore và ưu tiên metadata tối thiểu |

Không tự xếp chồng hai decorator cùng quản lý MDC nếu chưa hiểu thứ tự cài và khôi phục của chúng.

## 10. MDC không phải transaction, SecurityContext hay HttpServletRequest

| Context | Ý nghĩa | MDC TaskDecorator có tự propagate không? |
| --- | --- | --- |
| SLF4J MDC | Metadata để làm phong phú log | **Có**, qua bản copy map |
| Spring transaction | Connection/resource binding và synchronization | **Không** |
| Spring SecurityContext | Authentication/authorization | **Không** |
| `RequestContextHolder` | Request attributes gắn thread | **Không** |
| Micrometer Observation | Ngữ cảnh metrics/tracing | Không tự động nếu chỉ copy MDC |
| Custom ThreadLocal của ứng dụng | State do dự án định nghĩa | Không, trừ khi có cơ chế riêng |
| Event payload | Snapshot dữ liệu nghiệp vụ | Không phải ThreadLocal |

**Không copy thủ công transaction context như MDC.** Một transaction gắn với connection/resource trên thread gốc có hợp đồng về commit/rollback; sao chép các reference ThreadLocal sang worker có thể phá hỏng ngữ nghĩa. Listener `@Async` cần transaction riêng nếu thực hiện thao tác database có giao dịch.

**Không dùng MDC để cấp quyền.** Log có `userId=alice` không phải bằng chứng rằng worker được phép truy cập dữ liệu của Alice. Nếu cần propagate authentication, sử dụng cơ chế được Spring Security cung cấp, với giới hạn và chính sách bảo mật phù hợp.

**Không giữ request object lâu.** Trong event payload hoặc task async dài, tránh giữ `HttpServletRequest`, persistence context, connection hoặc object mutable của luồng request. Truyền những ID nghiệp vụ cần thiết và metadata logging tối thiểu.

## 11. MDC và correlationId trong payload là hai lớp khác nhau

Một record event có thể định nghĩa:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId
) {}
```

`correlationId` trong payload là **dữ liệu nghiệp vụ/truy vết bền qua xử lý**. Trong khi đó `MDC.get("correlationId")` chỉ có ở thread đã được cài context. Nếu event được lưu outbox và được xử lý lại sau vài phút hoặc qua process khác, MDC của request ban đầu không còn.

Một listener có thể cài MDC từ payload:

```java
@EventListener
public void onOrder(OrderPlaced event) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable(
                         "correlationId",
                         event.correlationId())) {
        log.info("order={}", event.orderId());
    }
}
```

Đây là mẫu tích hợp. `MDC.putCloseable` xóa khóa được đặt khi scope kết thúc; nó **không mặc nhiên khôi phục giá trị cũ** của cùng khóa. Nếu cần giữ nested context, hãy tự save/restore giá trị trước đó hoặc map trước đó bằng `finally`.

Các ID thường khác nhau:

- `eventId` định danh **một occurrence của event**, cần ổn định qua retry cùng occurrence.
- `correlationId` nhóm những sự kiện thuộc **cùng workflow**.
- `traceId` từ distributed tracing mô tả một trace kỹ thuật, có thể ngắn hơn workflow.
- `causationId` (nếu có) mô tả event cha trực tiếp dẫn tới event mới.

Không nên dùng một MDC traceId tạm thời làm khóa idempotency duy nhất cho email, hóa đơn hoặc cập nhật thanh toán.

### Nếu publisher không có MDC thì decorator không tự biết dữ liệu payload

TaskDecorator chung nhận `Runnable`, không được bảo đảm biết kiểu event mà listener xử lý. Nó không có hợp đồng trích `correlationId` từ bất kỳ record nào. Nếu muốn log được ID khi publish từ một tác vụ scheduler/outbox không có MDC, cần cài context từ metadata trước khi submit hoặc bên trong listener theo scope rõ ràng.

## 12. Rò rỉ MDC và thread reuse

Thread pool tái sử dụng worker nhiều lần:

```text
Task A: set traceId=trace-A
Task A: kết thúc nhưng không clear
           |
           v
Task B trên cùng thread:
  publisher không có traceId
  log vẫn hiện trace-A  <-- sai
```

Một lỗi khác là:

```java
if (captured != null) {
    MDC.setContextMap(captured);
}
// Không clear trong trường hợp captured == null.
```

Đây là **phản ví dụ**. Nếu worker có MDC cũ hoặc có một wrapper bên ngoài, task mới có thể nhìn thấy dữ liệu không thuộc nó. Mẫu đúng phải **clear khi captured null** và **restore previous trong finally**.

Với log chứa `tenantId` hoặc `userId`, rò rỉ context có thể tạo dòng log sai người dùng/tenant, gây rủi ro khi vận hành và điều tra. Cần bảo đảm MDC chỉ chứa dữ liệu logging đã được giảm thiểu, không có mật khẩu, token hay PII không cần thiết.

### InheritableThreadLocal không phải lời giải cho thread pool

`InheritableThreadLocal` có ngữ nghĩa kế thừa khi **tạo thread**, không phải khi **nộp một task mới vào thread đã được tạo từ trước**. Một worker tồn tại lâu có thể mang state cũ hoặc không có state theo yêu cầu mới. Vì vậy dùng InheritableThreadLocal để truyền MDC theo từng event qua pool thường không đúng. Cơ chế capture/restore theo task là sự lựa chọn rõ ràng hơn.

## 13. TaskDecorator không phải cơ chế bắt lỗi duy nhất

Tài liệu Spring lưu ý decorator có thể nhận callback kiểu `FutureTask` thay vì runnable gốc. `FutureTask.run()` thường lưu exception vào `Future`, do đó `catch` ngoài lời gọi `delegate.run()` **không chắc** thấy exception nghiệp vụ.

Phản ví dụ:

```java
return () -> {
    try {
        delegate.run();
    } catch (RuntimeException ex) {
        log.error("All async errors are here", ex);
    }
};
```

Không dùng logic này làm phương thức duy nhất để bắt tất cả lỗi `@Async`.

Tách trách nhiệm:

- **TaskDecorator:** truyền và dọn context bằng `try/finally`, không nuốt exception.
- **`@Async void`:** theo dõi exception qua `AsyncUncaughtExceptionHandler` hoặc xử lý tại service.
- **Future/CompletableFuture:** xử lý kết quả hoặc exception qua API Future hoặc callback phù hợp.
- **Task rejection:** theo dõi lỗi gửi task khi executor đầy/đang đóng.
- **Event workflow:** có trạng thái nghiệp vụ, retry và idempotency riêng.

Nếu callback không được đưa vào pool vì bị reject, `run()` không chạy. Decorator không biến event chưa chạy thành event hoàn tất.

## 14. Quá tải, shutdown và durability

`ThreadPoolTaskExecutor` có `corePoolSize`, `maxPoolSize` và `queueCapacity`. Khi tất cả worker và queue đều bận, executor có thể từ chối thêm task. Khi đó:

1. `@Async` không đồng nghĩa sự kiện chắc chắn được xử lý.
2. Task có thể chưa từng thực thi; không có log callback dù đã gọi `publishEvent`.
3. MDC snapshot đã capture không bảo đảm công việc được persist.
4. Dừng JVM cưỡng bức có thể làm mất task đang chờ trong RAM.
5. Nếu phải xử lý chắc chắn, nên có outbox, broker hoặc job store cùng retry/idempotency.

MDC cũng làm tăng dữ liệu nhớ giữ trong queue theo mỗi task. Không đặt payload lớn hoặc secrets vào MDC; chỉ giữ những ID ngắn, cần thiết và phù hợp chính sách log.

Chọn `queueCapacity` lớn không phải là bảo đảm delivery. Với executor nhỏ và queue lớn, thời gian chờ có thể tăng; lúc worker chạy, MDC vẫn là snapshot tại thời điểm nộp task, điều đúng về ngữ nghĩa tracing nhưng cần lưu ý độ trễ.

## 15. @TransactionalEventListener và MDC

Một listener hậu commit có thể khai báo:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    log.info("After commit: {}", event.orderId());
}
```

Đây là ví dụ tích hợp: cần `@EnableAsync`, executor và transaction manager thực tế. `@TransactionalEventListener` mặc định ràng buộc với pha `AFTER_COMMIT`; nếu phát event ngoài transaction khi `fallbackExecution=false`, callback thường không chạy.

Cần hiểu từng ranh giới:

- Callback hậu commit được đăng ký theo transaction nguồn.
- Khi Spring gửi phương thức `@Async` vào executor, decorator capture MDC của **thread đang nộp task lúc đó**.
- Nếu MDC đã bị xóa trước thời điểm này, decorator không thể tự hồi sinh một traceId không còn trên thread.
- Transaction gốc **không** được copy sang worker cùng MDC; nếu listener ghi dữ liệu mới, tạo transaction thích hợp.
- Event hậu commit vẫn có thể bị mất do crash giữa business commit và công việc follow-up. Nếu không được phép mất, transactional outbox là giải pháp ở tầng dữ liệu, không phải TaskDecorator.

Điều này giải thích vì sao event payload nên mang `eventId`/`correlationId` ổn định, để có thể tái thiết lập logging context trong tác vụ chậm hoặc replay.

## 16. Kiểm thử đúng

### Unit test cho save/restore

Có thể kiểm tra logic wrapper trên cùng một thread:

```java
MdcTaskDecorator decorator = new MdcTaskDecorator();

MDC.put("traceId", "publisher-A");
Runnable wrapped = decorator.decorate(() -> {
    if (!"publisher-A".equals(MDC.get("traceId"))) {
        throw new AssertionError("MDC was not installed");
    }
});

MDC.put("traceId", "worker-old");
wrapped.run();

if (!"worker-old".equals(MDC.get("traceId"))) {
    throw new AssertionError("MDC was not restored");
}
MDC.clear();
```

Đoạn này yêu cầu implementation `MdcTaskDecorator` và MDC provider như mục 6. Nó chứng minh save/restore, nhưng **không thay thế integration test qua Spring executor**.

### Integration test cần có chuyển luồng

| Tình huống | Kỳ vọng |
| --- | --- |
| Task A được nộp với `trace-A` | Worker A đọc `trace-A` |
| Publisher đổi sang `trace-B` khi A còn trong queue | A vẫn thấy `trace-A` |
| Task B được nộp với `trace-B` | Worker B đọc `trace-B` |
| Task C được nộp không có MDC | Worker C không thấy trace của B |
| Cùng thread pool xử lý nhiều task | Context không rò rỉ giữa task |
| Listener ném exception | `finally` vẫn khôi phục MDC |
| Executor không gắn decorator | Không được suy ra propagation thành công |
| Executor từ chối task | Có quan sát rejection và chính sách phù hợp |
| Hai tầng executor | Kiểm tra propagation tại cả hai lần chuyển luồng |
| Logger không in traceId nhưng MDC có giá trị | Kiểm tra cấu hình logging pattern thay vì chỉ sửa TaskDecorator |

**Không test bằng `Thread.sleep(50)` rồi assert.** Thời gian chạy phụ thuộc máy và queue, test dễ flaky. Dùng `CountDownLatch` hoặc future với timeout như ví dụ.

Test logging cũng nên ghi lại `MDC.get("traceId")` trên worker vào cấu trúc kiểm chứng an toàn luồng, không chỉ nhìn các chuỗi log — vì logger có thể bị filter hoặc pattern chưa được cấu hình.

## 17. Lỗi thường gặp

1. **Gắn TaskDecorator vào sai executor.** `@Async("mailExecutor")` không sử dụng decorator của bean `eventExecutor`.
2. **Quên `@EnableAsync`.** Listener có thể vẫn chạy đồng bộ, khiến phép thử sai khi kết luận propagation tốt.
3. **Capture MDC trên worker.** Quá muộn để có snapshot publisher.
4. **Không xử lý captured null.** Event mới không có MDC vẫn có thể thấy traceId cũ.
5. **Không restore previous.** Một wrapper bên ngoài có thể mất context ban đầu của worker.
6. **Không dùng finally.** Exception làm worker mang context sang task sau.
7. **Chỉ dùng InheritableThreadLocal.** Thread pool tái sử dụng thread, không kế thừa context theo từng task.
8. **Dùng MDC làm nguồn dữ liệu nghiệp vụ.** Logging context có thể mất khi qua process hoặc replay.
9. **Nghĩ copy MDC cũng copy transaction.** Đây là hai ngữ cảnh hoàn toàn khác nhau.
10. **Nghĩ copy MDC là kiểm soát quyền.** Authentication/authorization phải dựa vào cơ chế bảo mật phù hợp.
11. **Cấu hình executor của multicaster nhưng quên executor của @Async.** Có thể có hai lần chuyển luồng.
12. **Dựa vào decorator để bắt mọi exception.** `FutureTask` có thể giữ lỗi ở Future.
13. **Không có SLF4J backend hỗ trợ MDC.** Chỉ gọi MDC API không bảo đảm pattern log có giá trị.
14. **Nhét dữ liệu lớn hoặc nhạy cảm vào MDC.** Mỗi task có thể giữ snapshot trong queue.
15. **Để listener xử lý task cực nhỏ mà không đo overhead.** Capture và restore map có chi phí.
16. **Cho rằng ContextPropagatingTaskDecorator copy mọi MDC key mặc định.** Phải xác minh integration/accessors.
17. **Xem traceId trong log là bằng chứng xử lý thành công.** Task có thể lỗi, bị retry hoặc được log trước tác dụng phụ.
18. **Tin rằng executor trong RAM là hàng đợi bền vững.** TaskDecorator không cung cấp persistence hay exactly-once.

## 18. Checklist áp dụng vào ứng dụng

- [ ] Xác định rõ event listener chuyển thread bằng `@Async` hay multicaster executor.
- [ ] Cấu hình decorator trên **đúng executor** được dùng.
- [ ] Capture map MDC lúc submit task, không phải lúc worker chạy.
- [ ] Lưu previous context của worker và khôi phục trong `finally`.
- [ ] Captured null dẫn đến clear MDC cho task đó.
- [ ] Có logging backend hỗ trợ MDC và pattern in đúng key.
- [ ] `@EnableAsync` cùng proxy invocation hoạt động theo thiết kế.
- [ ] Test hai traceId khác nhau và một task không có MDC trên cùng worker.
- [ ] Dùng latch/future để đợi hoàn tất, không đoán thứ tự/timing.
- [ ] Với nhiều executor hoặc nhiều lần chuyển luồng, mỗi tầng đều có propagation cần thiết.
- [ ] Event payload chứa correlation ID nghiệp vụ để dùng khi replay/outbox.
- [ ] Không nhầm MDC với transaction, SecurityContext, request context và tracing state.
- [ ] Có chính sách exception, rejection, shutdown, retry và idempotency riêng.
- [ ] Không đưa secrets/PII không cần thiết vào MDC hoặc log.
- [ ] Đã đo overhead propagation khi task nhỏ và tần suất cao.

**Ghi nhớ:** `TaskDecorator` cho phép logging context “đi cùng công việc” qua ranh giới thread, bằng cách **capture ở publisher → install trên worker → run task → restore worker trong finally**. Cấu hình đúng pool và dọn sạch context mới là điều quyết định để log không bị thiếu hoặc rò rỉ traceId giữa các Spring Application Events.

## Tài liệu chính thức

- [Spring Framework — TaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html)
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html)
