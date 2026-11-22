# Bật log để theo dõi multicaster trong Spring Application Events

## 1. Mục tiêu chẩn đoán

Một lỗi phổ biến của Spring Application Events là service đã gọi `ApplicationEventPublisher.publishEvent(...)` nhưng không thấy listener chạy, hoặc listener chạy chậm/đúng lúc transaction rollback mà log không cho biết nguyên nhân. Khi ấy, cần quan sát **đường đi từ publisher → ApplicationEventMulticaster → listener** thay vì chỉ nhìn một dòng log ở service.

Trong một `ApplicationContext` thông thường, Spring dùng `ApplicationEventMulticaster`; implementation mặc định thường là `SimpleApplicationEventMulticaster`. Nó tìm các listener phù hợp với kiểu event, rồi chuyển event cho chúng. Mặc định listener được gọi **đồng bộ trên thread của publisher**, trừ khi ứng dụng bật `@Async` cho listener hoặc thay đổi executor/cơ chế dispatch.

Từ góc độ vận hành, một lần publish có thể cần trả lời:

1. Code có **thực sự** gọi `publishEvent(...)` không?
2. Kiểu event runtime là gì, và nó có phù hợp chữ ký listener không?
3. Context có đăng ký listener không? Có nhiều context hoặc listener trùng không?
4. Multicaster có nhận event và chọn listener dự kiến không?
5. Handler có bắt đầu xử lý, kết thúc thành công hay ném exception không?
6. Handler chạy trên thread nào, đồng bộ hay bất đồng bộ?
7. Nếu listener gắn transaction, callback có chờ commit/rollback nên chưa chạy không?
8. Có event bị bỏ qua do điều kiện `@EventListener(condition=...)` hoặc lỗi generic không?
9. Một event có gây side effect nhiều lần vì retry hoặc đăng ký trùng không?

**Bật log là bước đầu, không phải lời giải duy nhất.** Spring không hứa rằng chỉ tăng một logging level sẽ có log chi tiết cho từng event và từng listener ở mọi phiên bản. Khi cần chứng cứ chính xác, bổ sung structured logs tại publisher/listener hoặc instrumentation tại multicaster.

## 2. Sơ đồ luồng Spring event và nơi nên ghi log

```text
Controller / Service / Scheduler
    |
    | (1) log PUBLISH eventId, type, thread
    v
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationContext
    |
    v
ApplicationEventMulticaster
    | (2) chọn listener theo type / ResolvableType
    | (3) phân phối đến listener phù hợp
    |
    +----> ApplicationListener<E>
    |         | (4) START, SUCCESS, FAILURE
    |
    +----> @EventListener method adapter
    |         | (5) điều kiện, proxy, method
    |
    +----> @Async / executor (nếu có)
    |         | (6) queue, thread, errors
    |
    +----> @TransactionalEventListener adapter
              | (7) đăng ký transaction synchronization
              | (8) callback tại phase tương ứng
```

Khi publisher và listener đồng bộ, thời gian thực thi listener nằm trong lời gọi `publishEvent(...)`. Nếu một listener ném unchecked exception và không có `ErrorHandler` đặc biệt, exception có thể lan ngược tới publisher. Ngược lại, với async execution, publisher có thể trở về trước khi listener hoàn thành; lỗi cần được quan sát trên worker.

**Điểm cần phân biệt:** Có thể multicaster **đã gọi adapter** cho một method `@EventListener` nhưng điều kiện SpEL của method trả `false`, nên body listener **không chạy**. Vì vậy log "multicaster invoked adapter" không luôn tương đương log "business handler processed event". Thêm log ở chính body handler để phân biệt.

## 3. Bật TRACE/DEBUG qua cấu hình Spring Boot

Trong ứng dụng Spring Boot dùng logging mặc định, có thể bắt đầu bằng file `src/main/resources/application.properties`:

```properties
# Chẩn đoán tạm thời các class quản lý Spring context events.
logging.level.org.springframework.context.event=TRACE

# Khi cần mở rộng quá trình refresh/registration context:
logging.level.org.springframework.context.support=DEBUG

# Mã ứng dụng tự ghi thông tin event.
logging.level.com.example.order.events=DEBUG

# Pattern có thời gian, thread, level, tên logger.
logging.pattern.console=%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n
```

Tên package `com.example.order.events` **chỉ là ví dụ**, phải thay bằng package thật của ứng dụng. Spring Boot cũng hỗ trợ cấu hình tương đương qua YAML:

```yaml
logging:
  level:
    org.springframework.context.event: TRACE
    org.springframework.context.support: DEBUG
    com.example.order.events: DEBUG
  pattern:
    console: "%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n"
```

Chỉ cần chọn **một** trong hai cấu hình tương ứng, không nhất thiết khai báo cả hai cùng lúc.

### Điều có thể và không thể mong đợi

- Logger category `org.springframework.context.event` giúp bật log của những class Spring thực sự ghi ở level tương ứng, ví dụ adapter/multicaster/event-listener infrastructure.
- **Không có bảo đảm** rằng `SimpleApplicationEventMulticaster` luôn in một dòng `dispatch event X to listener Y` với mỗi lần publish. Nội dung, mức độ log và thông tin của các class nội bộ phụ thuộc phiên bản.
- `org.springframework.context.support=DEBUG` có thể rất nhiều log về lifecycle, bean/context initialization; không phải chỉ dành cho multicaster.
- Nếu ứng dụng dùng Logback nhưng cấu hình phân cấp logger hoặc filter khác, một category ở TRACE có thể vẫn không xuất hiện ở console/appender cần xem.
- Nếu listener xử lý trong executor khác, cần xem log của worker và thread pool, không chỉ log request thread.
- Trong Spring MVC/Tomcat, nhiều event có thể phát gần nhau; phải dùng eventId/aggregateId/traceId để nối log, không chỉ đối chiếu timestamp.

**Khuyến nghị:** Bắt đầu bằng các category chính xác và khoảng thời gian ngắn, chỉ tăng độ rộng khi cần. Không bật `TRACE` cho toàn bộ `org.springframework` lâu dài ở môi trường tải lớn; log có thể gây quá tải I/O và vô tình lộ dữ liệu.

### Ghi đè tạm trong runtime/deployment

Có thể dùng tham số Spring Boot:

```bash
java -jar app.jar --logging.level.org.springframework.context.event=TRACE
```

Hoặc biến môi trường:

```bash
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_CONTEXT_EVENT=TRACE java -jar app.jar
```

Cú pháp trên dành cho shell POSIX; với PowerShell, cách đặt environment variable khác. Trường hợp container/Kubernetes cần truyền biến vào manifest hoặc runtime deployment tương ứng. Đối với level chỉ định **một class riêng**, Spring Boot có một số giới hạn khi biến đổi tên biến môi trường (relaxed binding có thể làm mất chữ hoa), nên ưu tiên cấu hình file hoặc system property rõ ràng nếu category case-sensitive. 

Nếu ứng dụng đã tích hợp Actuator loggers endpoint và có cấp quyền thích hợp, có thể thay đổi log level mà không cần restart. **Không mở endpoint thay đổi logger công khai**; quản lý authentication, authorization, audit và thời hạn bật TRACE. Với ứng dụng không có Actuator, việc đổi cấu hình thường đòi hỏi restart/redeploy theo cơ chế quản lý cấu hình.

## 4. Log hữu ích nhất là gì?

Để theo dõi một sự kiện từ đầu đến cuối, nên ghi các mốc:

| Vị trí | Trường tối thiểu | Kết luận có thể rút ra |
| --- | --- | --- |
| Trước `publishEvent` | `eventType`, `eventId`, `aggregateId`, `thread` | Producer bắt đầu publish |
| Sau `publishEvent` | `eventId`, duration, outcome | Lời gọi publisher đã trở về hoặc ném lỗi |
| Khi multicaster chọn/invoke listener | `eventId`, listener identity, thread | Hạ tầng đang phân phối event cho một listener |
| Đầu body listener | `eventId`, listener, START, thread | Code handler thực sự đã bắt đầu |
| Cuối body listener | `eventId`, SUCCESS, duration | Phần code được theo dõi đã kết thúc bình thường |
| Trong catch/exception handler | `eventId`, FAILED, error class | Handler thất bại; cần xem retry/recovery |
| Trong async executor | pool, active count, queue, rejects | Có task bị chờ, nghẽn, hoặc từ chối |
| Trong transaction-bound listener | phase, tx state, commit outcome | Callback có phụ thuộc mốc transaction |

Không log nguyên payload chứa password, access token, cookie hoặc dữ liệu nhạy cảm. Ưu tiên event metadata và một số field nghiệp vụ đã được phép log; với thông tin nhạy cảm, có thể hash/mask theo chính sách.

### Mẫu log tốt

```text
PUBLISH eventId=e-81 type=OrderPlaced orderId=ORD-81
LISTENER_START eventId=e-81 listener=ProjectionUpdater
LISTENER_SUCCESS eventId=e-81 listener=ProjectionUpdater durationMs=14
PUBLISH_RETURN eventId=e-81 durationMs=16
```

Đây là **mẫu minh họa** chứ không phải output tự động của Spring. Có `eventId` để nối các đoạn, `durationMs` để xác định handler chậm và `listener` để tránh lẫn khi một event có nhiều subscriber.

Nếu listener là async, dòng `PUBLISH_RETURN` có thể xuất hiện **trước** `LISTENER_START` hoặc `LISTENER_SUCCESS`. Nếu có listener đồng bộ và listener async cùng loại event, log hai nhánh có thể xen kẽ.

## 5. Ví dụ chạy được Java 17+: nhìn thấy multicast đến @EventListener

Ví dụ này dùng **Spring Framework 6.2.13, Java 17+, Maven và Logback**. Không cần Spring Boot, cơ sở dữ liệu hoặc web server; mục tiêu là cô lập một `ApplicationContext` để quan sát cơ chế.

Ta xây:

- Event cụ thể `OrderAcceptedEvent extends ApplicationEvent`.
- Một bean có method `@EventListener`.
- Một `SimpleApplicationEventMulticaster` mở rộng để ghi log ở mức **invoke một listener adapter**.
- Logger cho publisher, multicaster và listener.
- Một integration test dùng JUnit để xác nhận Spring dispatch event thật.

**Lưu ý:** Thêm subclass multicaster là kỹ thuật instrumentation **cho ví dụ/điều tra có kiểm soát**, không phải yêu cầu bắt buộc của Spring. Ở production, nhiều ứng dụng chỉ cần logs tại publisher/listener và metrics/trace có sẵn, tránh thay hạ tầng dispatch nếu không cần.

### 5.1. Cấu trúc project

```text
multicaster-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/MulticasterDiagnostics.java
    │   └── resources/logback.xml
    └── test/
        └── java/example/events/MulticasterDiagnosticsTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>multicaster-diagnostics</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>

        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Bật TRACE cho hạ tầng event Spring trong demo. -->
    <logger name="org.springframework.context.event" level="TRACE"/>

    <!-- Log do các class ví dụ tự ghi. -->
    <logger name="example.events" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Mọi appender có thể bị ảnh hưởng bởi filtering/threshold khác trong dự án thực; ở đây chỉ dùng một ConsoleAppender. Pattern ghi `%thread` để thấy thread. Cấu hình `TRACE` không tự thêm log ở những vị trí Spring không ghi log.

### 5.4. src/main/java/example/events/MulticasterDiagnostics.java

```java
package example.events;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class MulticasterDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(MulticasterDiagnostics.class);

    public static final class OrderAcceptedEvent extends ApplicationEvent {
        private final String orderId;

        public OrderAcceptedEvent(Object source, String orderId) {
            super(source);
            this.orderId = Objects.requireNonNull(orderId);
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderHandler {
        private final AtomicInteger handled = new AtomicInteger();
        private static final Logger handlerLog =
                LoggerFactory.getLogger(OrderHandler.class);

        @EventListener
        public void on(OrderAcceptedEvent event) {
            handled.incrementAndGet();
            handlerLog.info("HANDLED id={}", event.getOrderId());
        }

        public int handledCount() {
            return handled.get();
        }
    }

    public static final class LoggingMulticaster
            extends SimpleApplicationEventMulticaster {

        private static final Logger multicasterLog =
                LoggerFactory.getLogger(LoggingMulticaster.class);

        @Override
        protected void invokeListener(
                ApplicationListener<?> listener,
                ApplicationEvent event) {

            if (!(event instanceof OrderAcceptedEvent accepted)) {
                super.invokeListener(listener, event);
                return;
            }

            multicasterLog.info(
                    "MULTICASTER invoke id={} listener={}",
                    accepted.getOrderId(),
                    listener.getClass().getSimpleName());

            try {
                super.invokeListener(listener, event);

                multicasterLog.info(
                        "MULTICASTER returned id={}",
                        accepted.getOrderId());
            } catch (RuntimeException ex) {
                multicasterLog.error(
                        "MULTICASTER failure id={} error={}",
                        accepted.getOrderId(),
                        ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        // Tên bean cố định mà ApplicationContext tìm để dùng
        // custom ApplicationEventMulticaster của chính context.
        @Bean("applicationEventMulticaster")
        SimpleApplicationEventMulticaster applicationEventMulticaster() {
            return new LoggingMulticaster();
        }

        @Bean
        OrderHandler orderHandler() {
            return new OrderHandler();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfig.class);
            context.refresh();

            log.info("PUBLISH id=ORD-7");
            context.publishEvent(
                    new OrderAcceptedEvent("demo", "ORD-7"));
            log.info("PUBLISH returned id=ORD-7");
        }
    }
}
```

### 5.5. Chạy chương trình

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.MulticasterDiagnostics
```

Đây là một lần chạy đồng bộ, chỉ phát một `OrderAcceptedEvent` từ code ví dụ. **Năm message do code demo tự tạo**, theo thứ tự logic:

```text
PUBLISH id=ORD-7
MULTICASTER invoke id=ORD-7 listener=ApplicationListenerMethodAdapter
HANDLED id=ORD-7
MULTICASTER returned id=ORD-7
PUBLISH returned id=ORD-7
```

Với `logback.xml`, mỗi message trên còn được đặt trong một dòng đầy đủ gồm **timestamp, thread, level và logger name**. `ApplicationListenerMethodAdapter` là tên lớp adapter thường dùng cho method `@EventListener` trong Spring 6.2; nếu Spring thay đổi implementation, trường `listener=...` có thể khác. Mã ví dụ không dựa vào chuỗi tên adapter để quyết định nghiệp vụ.

Các log **khác do TRACE hạ tầng Spring phát ra có thể xen giữa**; đừng so khớp output terminal nguyên văn với đúng năm dòng. Nội dung cần xác minh là quan hệ **PUBLISH → MULTICASTER invoke → HANDLED → MULTICASTER returned → PUBLISH returned** cho event `ORD-7`.

**Chú ý:** ví dụ dùng mặc định executor đồng bộ và không có `@Async`; phần log ở `invokeListener(...)` cho thấy adapter được Spring multicaster gọi trong lượt này. Nếu handler khai báo `@EventListener(condition=...)`, log `MULTICASTER returned` vẫn có thể xuất hiện dù method handler bị filter và không in `HANDLED`.

### 5.6. Ý nghĩa những mốc log

- `PUBLISH`: code ứng dụng đã đến ngay trước `context.publishEvent(...)`, chưa chứng minh listener được gọi.
- `MULTICASTER invoke`: Spring đã chọn một listener phù hợp để gọi ở tầng multicaster. Class hiển thị có thể là adapter/proxy thay vì bean business nguyên gốc.
- `HANDLED`: method business handler thật sự được thực thi và đi đến dòng log; không chứng minh mọi side effect bên ngoài hoàn tất nếu log đặt trước side effect.
- `MULTICASTER returned`: callback adapter trả về bình thường tại điểm instrumentation. Nếu adapter nộp công việc async, việc trả về này **không đồng nghĩa** task đã hoàn thành.
- `PUBLISH returned`: API publisher đã trả về bình thường; đối với dispatch đồng bộ ở đây, callback đã trả về trước đó.

Nếu muốn đo thời lượng, thêm `System.nanoTime()` trước `super.invokeListener(...)` và tính thời gian ở `finally`; **không** dùng đồng hồ wall-clock để đo chính xác duration do đồng hồ hệ thống có thể được điều chỉnh.

## 6. Integration test xác nhận wiring thay vì chỉ nhìn log

Trong quá trình chẩn đoán, log là bằng chứng vận hành, còn test xác nhận hành vi.

### 6.1. src/test/java/example/events/MulticasterDiagnosticsTest.java

```java
package example.events;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MulticasterDiagnosticsTest {

    @Test
    void matchingApplicationEventIsDeliveredOnce() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterDiagnostics.AppConfig.class)) {

            var handler = context.getBean(
                    MulticasterDiagnostics.OrderHandler.class);

            assertEquals(0, handler.handledCount());

            context.publishEvent(
                    new MulticasterDiagnostics.OrderAcceptedEvent(
                            this, "ORD-TEST"));

            assertEquals(1, handler.handledCount());
        }
    }

    @Test
    void unrelatedPayloadDoesNotInvokeOrderHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterDiagnostics.AppConfig.class)) {

            var handler = context.getBean(
                    MulticasterDiagnostics.OrderHandler.class);

            context.publishEvent("a plain string payload");

            assertEquals(0, handler.handledCount());
        }
    }
}
```

Chạy:

```bash
mvn test
```

Dự án định nghĩa **2 JUnit test methods**; khi chạy thành công, Maven Surefire báo số test chạy bằng 2, không có failure/error. Timestamp, tên thread và thời lượng log có thể khác theo máy, nên test **khẳng định số lần handler xử lý**, không kiểm tra log bằng snapshot timestamp.

Test thứ nhất chứng minh hạ tầng tìm đúng listener `@EventListener` và gọi method một lần. Test thứ hai phát một payload `String`, để Spring có thể bọc nó bằng `PayloadApplicationEvent<String>`; handler chỉ nhận `OrderAcceptedEvent` và không được kích hoạt.

Bộ test này không kiểm tra propagation, ordering giữa nhiều listener, retry hoặc transaction callbacks. Với ứng dụng có executor, cần đồng bộ test bằng latch/condition có timeout thay vì assert số lần ngay sau `publishEvent(...)`.

## 7. Khi chỉ bật TRACE mà không có log event nào

Đây là tình huống thường gặp, không nên kết luận logging bị hỏng ngay.

### Bước 1: xác minh level thực tế có hiệu lực

Nếu ứng dụng dùng SLF4J/Logback, một logger có thể bị chi phối bởi cấu hình:

- Logger name sai: ví dụ đang chạy Spring class khác với package bạn bật.
- Logger level trên class cụ thể hoặc parent khác ghi đè cấu hình.
- Appender threshold/filter bỏ bản ghi DEBUG/TRACE.
- Không có log statement ở đường code thực tế hoặc nội dung log chỉ ở level khác.
- Ứng dụng khởi chạy với cấu hình/profile khác bạn đang chỉnh.
- Có cấu hình logging bên ngoài ghi đè tài nguyên trong JAR.

**Thử tạo một log có chủ đích trong package ứng dụng**, hoặc trong ví dụ độc lập, xác minh dòng `PUBLISH` ở `INFO` xuất hiện. Nếu dòng đó không xuất hiện, phải sửa cấu hình logging/appender trước khi nghi multicast.

### Bước 2: bật category hẹp

Với Spring Boot:

```properties
logging.level.org.springframework.context.event.SimpleApplicationEventMulticaster=TRACE
logging.level.org.springframework.context.event.AbstractApplicationEventMulticaster=TRACE
```

Đây là cách bật level theo class chính xác, nhưng **không bảo đảm chính hai class này có log cho mỗi lần dispatch**. Sử dụng khi cần thu log nội bộ sẵn có; nếu mục tiêu là **bằng chứng mỗi event và mỗi listener**, dùng instrumentation/structured logging như mục 5.

### Bước 3: kiểm tra context thật đang phát event

Một ứng dụng nhiều context có thể có multicaster riêng cho từng context. Nếu bạn custom bean `applicationEventMulticaster` ở một child context nhưng event được publish ở context khác, log ở custom multicaster đó có thể không xuất hiện. Hãy xác định bean/context và nơi publisher được inject.

### Bước 4: kiểm tra kiểu event runtime

```java
Object event = ...; // Đối tượng thực sự định publish.
log.debug("eventType={}", event.getClass().getName());
publisher.publishEvent(event);
```

Đây là **mảnh code minh họa**, không phải file đầy đủ. Nếu event là record/POJO, Spring có thể bọc vào `PayloadApplicationEvent` nội bộ. Nếu listener dùng `ApplicationListener<ConcreteApplicationEvent>` nhưng producer chỉ gửi POJO khác kiểu, callback không được chọn dù logging hoạt động.

### Bước 5: phân biệt "listener được chọn" và "method body chạy"

- Với `@EventListener(condition="...")`, adapter có thể được gọi nhưng điều kiện false.
- Với generic events, metadata `ResolvableType` không đủ có thể khiến listener không match.
- Với `@TransactionalEventListener`, method có thể được đăng ký chờ `AFTER_COMMIT` thay vì chạy ngay.
- Với `@Async`, adapter hoặc proxy nộp task rồi trả về, trong khi method chạy muộn hơn trên worker.

Đừng giải quyết tất cả bằng cách tăng level logging; cần kiểm tra chính **cơ chế filtering/lifecycle**.

## 8. Chẩn đoán khi có @Async hoặc multicaster executor

Hai chiến lược async khác nhau:

**Chiến lược A — @Async trên method listener**

```java
@Async("eventExecutor")
@EventListener
public void on(OrderAcceptedEvent event) {
    // Method được async proxy nộp cho executor.
}
```

Điều kiện: `@EnableAsync`, executor bean tên `eventExecutor` và listener là bean do Spring quản lý. Nếu gọi method qua `this.on(...)` hoặc tạo bean bằng `new` bên ngoài Spring, annotation có thể bị bypass.

**Chiến lược B — executor ở multicaster**

```java
@Bean("applicationEventMulticaster")
SimpleApplicationEventMulticaster multicaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(executor);
    return m;
}
```

Đây là **đoạn cấu hình minh họa**, cần import `@Bean`, `@Qualifier`, `TaskExecutor` và class multicaster. Không thêm đoạn này **cùng lúc** với bean `applicationEventMulticaster` của ví dụ mục 5; cần chọn hoặc thay thế một bean duy nhất có tên chuẩn.

Khi đặt executor ở multicaster, các listener **hỗ trợ asynchronous execution** có thể được nộp sang worker. Một số listener, đặc biệt listener gắn transaction, cần được gọi tại publisher thread để đăng ký synchronization nên không được chuyển tùy tiện. Trong Spring Framework 6.1+, metadata `supportsAsyncExecution()` ảnh hưởng quyết định này.

### Bộ log nên thu khi nghi async

```text
PUBLISH eventId=e-17 thread=http-nio-8080-exec-7
SUBMIT eventId=e-17 executor=event-worker queueSize=12
HANDLER_START eventId=e-17 thread=event-worker-3
HANDLER_SUCCESS eventId=e-17 thread=event-worker-3 durationMs=44
```

Đây là **mẫu thông tin cần instrument**, không phải log Spring tự sinh. Nếu chỉ có SUBMIT mà không có HANDLER_START, điều tra queue, executor shutdown, rejection, task đang đợi hoặc thiếu context propagation.

Khi executor dùng `CallerRunsPolicy` trong tình huống quá tải, task có thể chạy trên chính thread đang submit, nên thread name không đổi dù cấu hình dùng executor. Việc "cùng thread" không đủ để kết luận `@Async` hỏng; cần xem trạng thái pool và chính sách rejection.

Với `void @Async` listener, exception thường không truyền về publisher; cấu hình `AsyncUncaughtExceptionHandler` hoặc bắt/ghi nhận lỗi trong handler. Không dùng một dòng "publish success" để thay cho business completion.

## 9. Chẩn đoán transaction-bound listeners

Event được publish **trong transaction đang hoạt động** có thể được nhận bởi `@TransactionalEventListener`. Ví dụ:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderAcceptedEvent event) {
    // Chạy sau khi transaction commit.
}
```

Đây là **method minh họa**, giả định đã import Spring transaction event và được khai báo trong một bean.

Các điểm cần log:

1. Thời điểm event được publish và transaction hiện tại có active không.
2. Phase listener đang sử dụng: `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hay `AFTER_COMPLETION`.
3. Transaction thực tế commit hay rollback.
4. Khi handler chạy, nó có mở transaction ghi DB mới nếu cần không.
5. Nếu không có transaction active, listener transaction **mặc định không được gọi**, trừ khi `fallbackExecution=true`.

Một lần event được multicaster "invoke" có thể chỉ làm adapter đăng ký synchronization; callback business chỉ thực thi sau commit. Đừng nhầm thời điểm `MULTICASTER returned` với `AFTER_COMMIT listener completed`.

Tại callback sau commit, transaction gốc đã commit; exception của hậu xử lý **không thể tự rollback** DB change đó. Nếu cần ghi DB sau commit, giao cho một service khác với transaction mới, ví dụ `@Transactional(propagation = Propagation.REQUIRES_NEW)` thông qua Spring proxy, hoặc dùng `TransactionTemplate` phù hợp.

**Nếu cần không mất event khi process chết sau commit**, không chỉ dựa vào `@TransactionalEventListener` hoặc log: sử dụng transactional outbox/durable queue và thiết kế retry/idempotency.

## 10. Theo dõi lỗi trong SimpleApplicationEventMulticaster

Mặc định, `SimpleApplicationEventMulticaster` gọi các listener đồng bộ; unchecked exception từ một listener có thể lan đến publisher và ngắt luồng dispatch tùy tình huống. Có thể cấu hình `ErrorHandler` để định nghĩa chính sách riêng:

```java
@Bean("applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setErrorHandler(error ->
            logger.error("Application listener failed", error));

    return multicaster;
}
```

Đây là **đoạn code minh họa**, giả định có biến `logger` của class cấu hình. Nếu dùng, nó **thay thế** bean multicaster ví dụ mục 5 thay vì khai báo trùng tên.

**Cực kỳ quan trọng:** ErrorHandler chỉ ghi log rồi trả về có thể làm exception **không tiếp tục lan tới publisher**, khác với chính sách mặc định. Điều này có thể khiến transaction nghiệp vụ gốc tiếp tục dù một side effect thất bại. Không đổi error policy chỉ để được nhiều log hơn mà chưa quyết định rõ semantics.

Khi cần vừa log vừa để lỗi lan lên, có thể dùng một ErrorHandler ném lại phù hợp; nhưng phải xác minh cách exception đi qua multicaster và transaction boundary. Cách ít xâm lấn hơn là log exception trong listener rồi `throw` lại theo hợp đồng, hoặc đo bằng instrumentation không thay đổi exception propagation.

Mô hình tiêu biểu:

```text
Publisher
    |
    v
Multicaster
    |
    +--> Listener A thành công
    |
    +--> Listener B ném lỗi
    |         |
    |         v
    |     ErrorHandler (nếu cấu hình)
    |         |
    |         +--> chỉ log/nuốt: publisher có thể không thấy lỗi
    |         +--> throw: publisher có thể thấy lỗi
    |
    +--> Listener C: có chạy hay không phụ thuộc
                       cách xử lý lỗi và dispatch
```

Vì vậy cần log **listener identity, eventId, exception class và chính sách lỗi**, không chỉ stack trace trôi nổi. Một lỗi ở listener B không nhất thiết có nghĩa mọi listener đã hoặc chưa chạy.

## 11. Theo dõi listener được đăng ký hay không

Không có callback không có nghĩa multicaster không tồn tại. Các nguyên nhân:

- Bean chưa được đăng ký hoặc nằm ngoài component scan.
- `@EventListener` nằm trong object tạo bằng `new` mà không là bean Spring.
- Dùng `ApplicationListener<WrongEvent>`, tên gần giống nhưng type không match.
- Event POJO/record được bọc thành `PayloadApplicationEvent`, còn listener chờ class wrapper hoặc class nghiệp vụ khác.
- Generic event không cung cấp `ResolvableType` chính xác.
- Event được phát **trước khi context sẵn sàng đăng ký bean listener**.
- Spring application có parent/child context và event được phát tại một context không như dự kiến.
- `@EventListener(condition=...)` trả false.
- Callback là `@TransactionalEventListener(AFTER_COMMIT)` và transaction chưa commit/đã rollback/không tồn tại.
- Async executor nhận task nhưng task chưa bắt đầu hoặc bị từ chối.

Không nên log toàn bộ bean graph ở production để tìm một listener. Hãy cô lập bằng một integration test nhỏ dùng cấu hình thực, publish event test và xác nhận handler có được gọi. Nếu log từ custom multicaster không xuất hiện, hãy kiểm tra bean chuẩn **`applicationEventMulticaster`** có được khai báo trong đúng context.

### Ứng dụng có nhiều ApplicationContext

Mỗi context có thể quản lý một multicaster riêng. Với hierarchy, event có thể được truyền lên parent, làm listener ở nhiều context nhìn thấy sự kiện. Một custom multicaster ở context A không tự động instrument mọi context B.

Đặt `contextId` hoặc định danh nguồn phù hợp vào log khi điều tra. Tránh dùng `ApplicationEvent.getSource()` như một bảo đảm rằng nó luôn chính là context; nhiều event nghiệp vụ có source tùy ứng dụng định nghĩa.

## 12. Khi TRACE quá ồn: structured logging và metrics

Bật log nội bộ có thể tạo hàng nghìn dòng trong startup hoặc luồng nghiệp vụ cao tần. Để vận hành lâu dài, nên phân biệt:

**Diagnostic logging tạm thời:**
- Chỉ bật trong một cửa sổ điều tra ngắn.
- Nhắm đúng package/class cần thiết.
- Giảm độ rộng sau khi đã tìm nguyên nhân.
- Có thời hạn giữ log và quyền truy cập phù hợp.

**Structured logging lâu dài:**
- Log một eventId và tên listener tại START/SUCCESS/FAILED.
- Log duration và error category, nhưng không log toàn payload nhạy cảm.
- Gắn traceId/correlationId để tìm qua các thread và hệ thống.
- Ghi idempotency/dedup state khi event có thể nhận lại.

**Metrics lâu dài:**
- `events.published`: số event đã được publish theo loại.
- `listener.started`: số lần handler bắt đầu.
- `listener.succeeded`: số lần handler kết thúc thành công.
- `listener.failed`: số lần xử lý lỗi.
- `listener.duration`: phân phối thời lượng.
- `executor.queue.size`, active/rejected: dấu hiệu bottleneck async.
- `outbox.pending`/lag: nếu có luồng vận chuyển bền vững.

Đây là **tên metric gợi ý cho ứng dụng**, không phải những tên metric Spring tự sinh sẵn. Với Micrometer, gắn tag **event type, listener name, result**, không gắn `eventId`/`orderId` làm tag vì cardinality quá lớn. ID chi tiết để ở log/tracing có kiểm soát.

### Trace giữa các thread

MDC thường gắn với thread và không tự chuyển qua executor. Nếu publisher log `traceId=t-1` nhưng listener async không có traceId, chưa chắc event bị mất; có thể chỉ **thiếu context propagation**. Dùng `TaskDecorator`/Micrometer Context Propagation nếu phù hợp hoặc truyền một correlation ID riêng trong event. Không copy bừa transaction `ThreadLocal` sang worker async.

## 13. Checklist gỡ lỗi từ log

| Triệu chứng | Giả thuyết cần kiểm tra | Bằng chứng hữu ích |
| --- | --- | --- |
| Không có PUBLISH | Producer không chạy, nhánh code không tới | Request/job tracing, breakpoint |
| Có PUBLISH nhưng không có multicaster log | Logger category không có statement, custom bean sai context hoặc chưa bật log | Cấu hình logger, bean name, contextId |
| Multicaster invoke nhưng không có HANDLED | `@EventListener condition` false, async task chưa chạy, transaction đang đợi | Body log, executor/tx phase |
| Có HANDLED nhưng không có SUCCESS | Exception, timeout, deadlock, thread bị chặn | FAILED log, thread dump, dependency metrics |
| Có RETURN trước HANDLED | Có thể listener async | Thread name, executor, queue |
| Có PUBLISH_RETURN nhưng xử lý nghiệp vụ thất bại | Async/recovery/ErrorHandler không lan lỗi | Handler status, business outcome |
| Có nhiều HANDLED cho một event | Nhiều listener/contexts, retry/duplicate publication | eventId, contextId, attempt, bean identity |
| Không thấy dữ liệu MDC ở HANDLED | Chuyển thread chưa propagate context | TaskDecorator, traceId trong event |
| Listener AFTER_COMMIT không chạy | Không có tx, rollback, phase sai | Tx outcome, fallbackExecution |
| TRACE tăng nhưng không thêm log dispatch | Class/phiên bản không ghi log ở mức đó | Explicit instrumentation và tests |
| Event đến handler sai | Type rộng/generic/wrapper không match như kỳ vọng | runtime class, ResolvableType, method signature |

### Một quy trình 7 bước

1. Xác định `eventType/eventId` mà producer thật sự phát.
2. Bật logger category **hẹp** của package ứng dụng và Spring event infrastructure.
3. Log tại publisher trước và sau `publishEvent(...)`, đo duration.
4. Log ở đầu/cuối body listener và exception, dùng cùng eventId.
5. Nếu vẫn không đủ, instrument multicaster ở đúng context, **không** thay đổi chính sách lỗi/trình tự một cách vô ý.
6. Kiểm tra thread/executor, điều kiện listener, transaction phase và generic type nếu log bất thường.
7. Thêm integration test hồi quy: publish object giống production và assert listener thật được gọi; khôi phục logging level sau điều tra.

## 14. Những lỗi phổ biến

**Lỗi 1 — Coi TRACE là công tắc in tất cả event.** Spring không bảo đảm có statement cho từng dispatch. Khi cần, thêm log có chủ đích hoặc instrumentation.

**Lỗi 2 — Bật TRACE toàn bộ Spring không giới hạn.** Log quá lớn, gây tải và lộ dữ liệu. Dùng category hẹp, thời hạn ngắn, quyền hạn thích hợp.

**Lỗi 3 — Chỉ log trong publisher.** `publishEvent(...)` được gọi không chứng minh handler đã xử lý; phải quan sát listener hoặc multicaster.

**Lỗi 4 — Chỉ log ở multicaster adapter.** `@EventListener(condition)` có thể bỏ qua method; async adapter có thể chỉ submit task. Thêm log tại body handler.

**Lỗi 5 — Dựa vào tên thread làm eventId.** Pool tái sử dụng thread, tên có thể trùng. Dùng định danh event/correlation riêng.

**Lỗi 6 — Gắn ErrorHandler nuốt exception chỉ để thêm log.** Thay đổi cơ chế lỗi và có thể khiến transaction commit ngoài ý muốn.

**Lỗi 7 — Dùng thời điểm multicast để kết luận AFTER_COMMIT chạy rồi.** Với transaction listener, callback nghiệp vụ được trì hoãn đến phase thích hợp.

**Lỗi 8 — Bỏ qua nhiều context.** Custom bean `applicationEventMulticaster` ở một context không theo dõi mọi context khác.

**Lỗi 9 — Không phân biệt payload wrapper.** POJO có thể được bọc thành `PayloadApplicationEvent`; log type đúng ở publisher và handler.

**Lỗi 10 — Nhìn log startup rồi kết luận event nghiệp vụ không phát.** Internal context events có thể xảy ra khác thời điểm; phải có eventId/type riêng.

**Lỗi 11 — Không quan sát lỗi executor.** Task async có thể bị reject trước khi body listener chạy; chỉ nhìn HANDLED là chưa đủ.

**Lỗi 12 — Chỉ test log string.** Log là công cụ quan sát, còn logic/wiring cần assertion thực tế qua unit/integration test.

## 15. Checklist vận hành trước khi kết thúc điều tra

1. Có log `PUBLISH` và `PUBLISH_RETURN` cho cùng eventId không?
2. Listener có log START/SUCCESS/FAILED ở **đầu và cuối body** không?
3. Logging level/category/appender đã được xác minh trên instance đang chạy chưa?
4. Đã xác nhận `applicationEventMulticaster` thuộc đúng context?
5. Có phân biệt listener adapter được invoke với method handler thật sự chạy không?
6. Tên thread, executor, queue, rejection và `@Async` có giải thích được thứ tự log không?
7. Nếu transaction listener, phase và commit/rollback đã được xác nhận chưa?
8. Có ghi đúng runtime type và generic metadata của event/handler không?
9. Có bảo vệ dữ liệu nhạy cảm, log retention và quyền bật TRACE không?
10. Có test hồi quy bằng Spring context sau khi sửa sự cố không?
11. Có ghi business outcome và số lần xử lý lại thay vì chỉ số lần publish không?
12. Đã hoàn nguyên log level tạm thời và tránh thay ErrorHandler khi không có chủ đích chưa?

**Kết luận:** Bật `TRACE` cho `org.springframework.context.event` là một bước quan sát ban đầu, **không phải bảo đảm Spring sẽ tự in mọi lần multicast**. Để chẩn đoán chính xác, kết hợp log ở publisher, multicaster và listener với eventId/traceId, thread/executor, exception và trạng thái transaction. Dùng instrumentation tạm thời khi cần và xác minh bằng integration test, rồi thu hẹp log để hệ thống vận hành ổn định.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventMulticaster` mặc định, registration, `@EventListener` và asynchronous listener.
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): `setTaskExecutor`, `setErrorHandler` và `invokeListener`.
- [Spring Framework 6.2 — AbstractApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html): đăng ký và chọn listener phù hợp.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): không tự tạo observation cho `@EventListener` và propagation của thread context.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): xử lý event gắn với transaction phase.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình log level/pattern và loggers.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): test dispatch và assertions.
