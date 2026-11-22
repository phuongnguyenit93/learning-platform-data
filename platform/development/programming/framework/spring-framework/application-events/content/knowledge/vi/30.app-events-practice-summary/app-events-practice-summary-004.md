# Sắp xếp nhiều listener trong Spring Framework Application Events

## 1. Mục tiêu và bối cảnh

Một sự kiện nghiệp vụ có thể được nhiều phần của ứng dụng Spring cùng quan tâm. Khi `OrderPlaced` được phát, hệ thống có thể ghi audit, cập nhật projection, đo metrics và chuẩn bị notification. Những listener này đều hợp lệ, nhưng việc **thứ tự nào được gọi trước** cần được hiểu đúng, nhất là khi một bước có lỗi, một listener có `@Async` hoặc ứng dụng sử dụng custom executor.

Ví dụ lệnh publish:

```java
applicationEventPublisher.publishEvent(new OrderPlaced("O-100"));
```

Đây là một dòng minh họa; kiểu `OrderPlaced` và publisher cần do ứng dụng định nghĩa. Trên Spring Framework 6.2, ta có các phương án sắp xếp:

- Đặt `@Order` trên từng phương thức `@EventListener`.
- Dùng `Ordered.getOrder()` trên đối tượng triển khai `ApplicationListener<E>`.
- Để listener không khai báo thứ tự nhận mức ưu tiên mặc định thấp.

**Quy tắc:** Spring ưu tiên **số order nhỏ hơn**. Với multicaster mặc định đồng bộ, listener có order 10 chạy trước order 20. Nhưng không được hiểu `@Order` là giao dịch, hàng đợi bền vững, cơ chế retry hay sự bảo đảm listener hoàn thành trước khi một task bất đồng bộ khác bắt đầu.

Bài này là một thực hành tổng kết về Spring Application Events: giải thích cơ chế dispatch, code Java 17 chạy được, test JUnit 5 trên Spring context, các tình huống async/transaction/error và tiêu chí khi nào không nên xếp chuỗi công việc bằng events.

## 2. Thứ tự thuộc phạm vi một lần phát event

Khi `ApplicationEventPublisher.publishEvent(event)` được gọi, `ApplicationEventMulticaster` trong context thực hiện việc tìm các listener nhận loại event đó và phân phối event.

Với `SimpleApplicationEventMulticaster` mặc định:

```text
OrderService
  |
  +-- publishEvent(OrderPlaced)
         |
         v
     tìm các listeners cho OrderPlaced
         |
         v
     sắp xếp theo order
         |
         +-- Audit @Order(10)
         +-- Projection Ordered=20
         +-- Metrics @Order(30)
         +-- Observer không @Order
         |
         v
     publishEvent returns
```

Hầu hết listener được gọi **ngay trên thread của publisher**, trong cùng call stack. Khi tất cả là synchronous và không có lỗi, `Audit` chạy xong rồi đến `Projection`, `Metrics` và `Observer`. Một listener mất 2 giây có thể làm `publishEvent` mất ít nhất 2 giây.

### 2.1. Chỉ so sánh thứ tự giữa những listener phù hợp với event

Hai listener này không tạo một thứ tự toàn cục:

```java
@EventListener
@Order(10)
public void onOrderPlaced(OrderPlaced event) { /* ... */ }

@EventListener
@Order(20)
public void onPaymentCaptured(PaymentCaptured event) { /* ... */ }
```

Đây là snippet minh họa trong một bean Spring, với hai event classes cần khai báo. Khi publish `OrderPlaced`, listener `onPaymentCaptured` không được gọi chỉ vì nó có order 20. Spring lọc theo event type/generic type và điều kiện trước khi dispatch.

### 2.2. Không suy ra thứ tự giữa hai publisher threads

Hai threads có thể cùng publish:

```text
Thread A: OrderPlaced(O-100)
Thread B: OrderPlaced(O-101)
```

Trên thread A, callbacks O-100 được ưu tiên theo thứ tự. Trên thread B, callbacks O-101 cũng vậy. Nhưng hai chuỗi có thể **đan xen** ở cấp ứng dụng; Spring không dùng `@Order` để khóa toàn bộ việc publish giữa các threads.

Nếu cả hai events phải thay đổi cùng aggregate, điều quan trọng là transaction isolation/version và business invariant, không phải chỉ order numbers.

## 3. @Order trên @EventListener

Cách phổ biến và dễ đọc nhất:

```java
@Component
public class OrderEventHandlers {

    @EventListener
    @Order(10)
    public void audit(OrderPlaced event) {
        // Ghi nhận fact.
    }

    @EventListener
    @Order(20)
    public void updateProjection(OrderPlaced event) {
        // Cập nhật projection.
    }

    @EventListener
    @Order(30)
    public void collectMetrics(OrderPlaced event) {
        // Metrics.
    }
}
```

Đoạn trên là **snippet**, không phải class chạy độc lập: cần `@Component`, `@EventListener`, `@Order` và `OrderPlaced`.

| Giá trị order | Cách hiểu | Ghi chú |
| --- | --- | --- |
| `@Order(-10)` | Trước 0, 10, 20 | Số âm hợp lệ |
| `@Order(0)` | Trước 10 | Không có nghĩa chạy lúc startup |
| `@Order(10)` | Trước 20 | Ưu tiên cao hơn |
| `@Order(20)` | Sau 10 | Ưu tiên thấp hơn |
| Không khai báo `@Order` | Mặc định thấp, thường tương ứng `Ordered.LOWEST_PRECEDENCE` | Không dựa vào thứ tự giữa các listener cùng default |
| `@Order(Ordered.HIGHEST_PRECEDENCE)` | Mức rất cao | Tránh lạm dụng vì dễ gây tranh chấp priority |

**Cùng order không có thứ tự ổn định theo hợp đồng.** Nếu hai methods đều `@Order(10)`, không nên mặc định phương thức ở dòng đầu file sẽ chạy trước phương thức ở dòng sau. Khi quan hệ trước/sau có ý nghĩa, dùng giá trị khác và viết test.

### 3.1. Đặt số có khoảng trống

Một convention:

```text
10  audit
20  read-model projection
30  metrics
40  optional notification
```

Để chèn một bước giữa audit và projection, có thể chọn 15. Đây là quy ước của ứng dụng, không phải enum hoặc phase có sẵn trong Spring.

### 3.2. Đặt annotation ở đâu?

Với phương thức `@EventListener`, đặt `@Order` **trực tiếp trên chính phương thức** là cách minh bạch nhất:

```java
@EventListener
@Order(20)
public void handle(OrderPlaced event) {
    // ...
}
```

`@Order` trên class hoặc bean factory method cũng có tác dụng ở những ngữ cảnh ordering khác như collection injection; không nên mặc định nó mô tả chính xác order của mọi method `@EventListener` bên trong class. Thực hành này cần ưu tiên method-level annotation và integration test.

Quan trọng: `@Order` **không quyết định thứ tự khởi tạo bean**. Dependency graph, constructor injection và `@DependsOn` là chuyện riêng. Đặt `@Order(10)` không đảm bảo một bean được tạo trước bean có `@Order(20)`.

## 4. Ordered cho interface ApplicationListener

Khi tự triển khai `ApplicationListener<E>`, có thể cung cấp order bằng interface `org.springframework.core.Ordered`:

```java
public class ProjectionListener
        implements ApplicationListener<OrderPlaced>, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        // Xử lý event.
    }
}
```

Đoạn trên minh họa một class, chưa có imports và code nghiệp vụ. Với Spring Framework 6.2, khi triển khai `ApplicationListener<E>` thì `E` là subtype phù hợp của `ApplicationEvent`; ví dụ Maven hoàn chỉnh phía dưới dùng `OrderPlaced extends ApplicationEvent`.

So với `@Order`, `Ordered.getOrder()` cho phép giá trị cấu hình ở instance:

```java
private final int configuredOrder;

@Override
public int getOrder() {
    return configuredOrder;
}
```

Tuy vậy, không nên thay đổi giá trị `getOrder()` liên tục sau khi context đã hoạt động rồi kỳ vọng danh sách listener được sắp xếp lại tức thời. Multicaster có thể cache thông tin listener phù hợp. Hãy coi order là **cấu hình ổn định trong đời sống của application context**.

### 4.1. PriorityOrdered

Spring còn có `PriorityOrdered`, chuyên biểu diễn một nhóm ưu tiên đặc biệt so với các đối tượng Ordered thông thường. Với nhiều domain listeners, không cần dùng nó. Khi trộn `PriorityOrdered`, `Ordered` và các annotation order, nên kiểm thử đúng Spring version vì nhóm ưu tiên và quy tắc comparator có thể làm kết quả khác giả định “chỉ so số”.

Thông thường, các `@EventListener @Order(10/20/30)` đủ rõ để review. Không cần biến mọi business callback thành thành phần có ưu tiên hạ tầng cao nhất.

## 5. Ví dụ chạy được: bốn listeners, hai cách khai báo thứ tự

Ví dụ dùng:
- Java 17+ và Maven.
- Spring Framework `spring-context:6.2.12`.
- JUnit Jupiter + `spring-test` cho integration tests.
- Một recorder ghi callback order trong bộ nhớ.

Bốn listeners cho cùng `OrderPlaced`:
1. `AuditListener`: `@EventListener @Order(10)`.
2. `ProjectionListener`: implements `ApplicationListener<OrderPlaced>, Ordered`, order 20.
3. `MetricsListener`: `@EventListener @Order(30)`.
4. `ObserverListener`: `@EventListener` không có `@Order`, ưu tiên mặc định.

### 5.1. Cấu trúc

```text
listener-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/OrderingEventsDemo.java
    └── test/java/demo/OrderingEventsDemoTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>listener-order-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.12</version>
            <scope>test</scope>
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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OrderingEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/java/demo/OrderingEventsDemo.java

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

public final class OrderingEventsDemo {

    public static final class OrderPlaced extends ApplicationEvent {
        private final String orderId;

        public OrderPlaced(String orderId) {
            super("order-service");
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            if (orderId.isBlank()) {
                throw new IllegalArgumentException("blank order ID");
            }
        }

        public String orderId() {
            return orderId;
        }
    }

    // Chỉ dùng trong demo đồng bộ, một thread.
    public static final class CallRecorder {
        private final List<String> calls = new ArrayList<>();

        public void add(String text) {
            calls.add(text);
        }

        public void clear() {
            calls.clear();
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    public static final class AuditListener {
        private final CallRecorder recorder;

        public AuditListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        @Order(10)
        public void on(OrderPlaced event) {
            recorder.add("AUDIT:" + event.orderId());
        }
    }

    public static final class ProjectionListener
            implements ApplicationListener<OrderPlaced>, Ordered {

        private final CallRecorder recorder;

        public ProjectionListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            recorder.add("PROJECTION:" + event.orderId());
        }
    }

    public static final class MetricsListener {
        private final CallRecorder recorder;

        public MetricsListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        @Order(30)
        public void on(OrderPlaced event) {
            recorder.add("METRICS:" + event.orderId());
        }
    }

    public static final class ObserverListener {
        private final CallRecorder recorder;

        public ObserverListener(CallRecorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        public void on(OrderPlaced event) {
            recorder.add("OBSERVER:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        CallRecorder callRecorder() {
            return new CallRecorder();
        }

        @Bean
        AuditListener auditListener(CallRecorder recorder) {
            return new AuditListener(recorder);
        }

        @Bean
        ProjectionListener projectionListener(CallRecorder recorder) {
            return new ProjectionListener(recorder);
        }

        @Bean
        MetricsListener metricsListener(CallRecorder recorder) {
            return new MetricsListener(recorder);
        }

        @Bean
        ObserverListener observerListener(CallRecorder recorder) {
            return new ObserverListener(recorder);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(new OrderPlaced("O-100"));

            List<String> actual =
                    context.getBean(CallRecorder.class).snapshot();

            List<String> expected = List.of(
                    "AUDIT:O-100",
                    "PROJECTION:O-100",
                    "METRICS:O-100",
                    "OBSERVER:O-100");

            System.out.println(
                    "CALL_ORDER=" + String.join(" > ", actual));
            System.out.println("ORDER_OK=" + actual.equals(expected));
        }
    }
}
```

### 5.4. Lệnh chạy và kết quả

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Hai dòng chương trình chủ động in, bỏ qua log của Maven/framework:

```text
CALL_ORDER=AUDIT:O-100 > PROJECTION:O-100 > METRICS:O-100 > OBSERVER:O-100
ORDER_OK=true
```

#### Vì sao kết quả đúng?

1. `AnnotationConfigApplicationContext` khởi tạo các bean do `Config` khai báo.
2. `AuditListener`, `MetricsListener` và `ObserverListener` có `@EventListener`; Spring đăng ký chúng qua hạ tầng xử lý listener methods.
3. `ProjectionListener` là một `ApplicationListener<OrderPlaced>` thực sự và cung cấp `Ordered.getOrder() = 20`.
4. `OrderPlaced` kế thừa `ApplicationEvent`; trong bài này constructor nhận order ID và đặt source là chuỗi cố định `"order-service"`.
5. Multicaster tìm tất cả listener phù hợp, sắp xếp theo order: 10, 20, 30, default.
6. Mặc định không cấu hình async executor, các callbacks chạy đồng bộ trên publisher thread.
7. Recorder chỉ append nhãn; sau khi `publishEvent` trả về đã có đủ bốn nhãn.
8. Danh sách đúng thứ tự nên `ORDER_OK=true`. Ví dụ không chứa DB, broker hoặc network nên không chứng minh durability.

Vì recorder chỉ dùng `ArrayList`, không được đem nguyên class này vào test đa thread. Khi có nhiều publisher threads, dùng thread-safe recorder cùng cơ chế lọc theo event ID và chờ hoàn thành.

## 6. Viết JUnit integration tests cho thứ tự listener

Test đúng thứ tự phải chạy trong **Spring ApplicationContext thật**, để Spring tự đăng ký `@EventListener` và `ApplicationListener`. Chỉ `new` bốn listener rồi gọi thủ công không kiểm tra được multicaster ordering.

### 6.1. src/test/java/demo/OrderingEventsDemoTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import demo.OrderingEventsDemo.CallRecorder;
import demo.OrderingEventsDemo.OrderPlaced;

@SpringJUnitConfig(OrderingEventsDemo.Config.class)
class OrderingEventsDemoTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    CallRecorder recorder;

    @BeforeEach
    void clearRecorder() {
        recorder.clear();
    }

    @Test
    void usesOrderTenTwentyThirtyThenDefault() {
        publisher.publishEvent(new OrderPlaced("O-200"));

        assertEquals(List.of(
                "AUDIT:O-200",
                "PROJECTION:O-200",
                "METRICS:O-200",
                "OBSERVER:O-200"),
                recorder.snapshot());
    }

    @Test
    void repeatsOrderingForTwoSequentialPublishes() {
        publisher.publishEvent(new OrderPlaced("O-201"));
        publisher.publishEvent(new OrderPlaced("O-202"));

        assertEquals(List.of(
                "AUDIT:O-201",
                "PROJECTION:O-201",
                "METRICS:O-201",
                "OBSERVER:O-201",
                "AUDIT:O-202",
                "PROJECTION:O-202",
                "METRICS:O-202",
                "OBSERVER:O-202"),
                recorder.snapshot());
    }

    @Test
    void ignoresUnrelatedEventType() {
        publisher.publishEvent("not-an-OrderPlaced");
        assertEquals(List.of(), recorder.snapshot());
    }
}
```

Chạy:

```bash
mvn test
```

Khi dependencies được tải và dùng JDK 17+, cả **3 test methods** phải thành công. Surefire sẽ báo các con số tương đương:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Những dòng log khác có thể xuất hiện tùy Maven/environment. Chương trình chính có thể chạy sau đó bằng `mvn -q compile exec:java`.

### 6.2. Vì sao không chỉ dùng @RecordApplicationEvents?

`@RecordApplicationEvents` và `ApplicationEvents.stream(...)` là công cụ tốt để assert **event đã được publish**. Trong bài này ta muốn xác minh **thứ tự callback**, nên recorder được đặt ngay trong các listeners cho biết thứ tự thực thi thực tế.

Ba tests có mục tiêu khác nhau:
- Test thứ nhất kiểm tra 4 callbacks của một event.
- Test thứ hai kiểm tra tính chất dispatch đồng bộ khi publish tuần tự hai occurrences.
- Test thứ ba bảo đảm các listeners theo kiểu `OrderPlaced` không được gọi cho một payload `String`.

### 6.3. Vì sao phải clear trước mỗi test?

Recorder là Spring singleton bean trong test context. JUnit có thể tái sử dụng application context qua nhiều test methods. Nếu không clear, nhãn từ test trước có thể còn lại, tạo kết quả phụ thuộc thứ tự thực thi test. `@BeforeEach` đặt lại recorder trước mỗi test.

Nếu dùng recorder trong application thực, không nên để một singleton lưu vô hạn event history trong `ArrayList`; đó chỉ là test probe.

### 6.4. Kiểm tra thứ tự khác kiểm tra side effects

Các assertions trên **chỉ chứng minh thứ tự listener đã chạy** trong cấu hình đồng bộ. Chúng không chứng minh:
- DB đã commit.
- Email đã được gửi.
- Kafka đã ACK.
- Transaction nào đã rollback.
- Retry/redelivery không xảy ra.
- Các remote services nhận theo đúng thứ tự.

Các mục đó cần test ở boundary tương ứng.

## 7. @Async làm thứ tự hoàn tất trở nên không xác định

Giả sử:

```java
@Async("eventExecutor")
@EventListener
@Order(10)
public void sendEmail(OrderPlaced event) {
    emailClient.send(event);
}

@Async("eventExecutor")
@EventListener
@Order(20)
public void refreshCache(OrderPlaced event) {
    cacheClient.update(event);
}
```

Đây là snippet, cần `@EnableAsync`, executor bean, client methods và cấu hình Spring thích hợp; không thuộc Maven demo.

Ở publisher thread, listener proxy có thứ tự ưu tiên: `sendEmail` trước `refreshCache`. Nhưng mỗi proxy có thể **chỉ submit task**. Nếu email chậm và cache nhanh, cache có thể hoàn tất trước email:

```text
Publisher            Worker-1                Worker-2
--------             --------                --------
@Order(10) submit --> sendEmail starts
@Order(20) submit -------------------------> refreshCache starts
publish returns      sendEmail still busy     refreshCache finishes
                     sendEmail finishes
```

**Phân biệt:**
- Listener selection order: listener nào phù hợp.
- Invocation/submission order: callback/proxy nào được gọi trước.
- Start order: task nào bắt đầu trước trên executor.
- Completion order: task nào hoàn tất trước.
- Business effect order: remote side effect nào thực sự được commit/ACK trước.

`@Order` chỉ giúp tầng ordering của event dispatch. Nó không đặt semaphore cho hai executor tasks hay mở một transaction chung.

### 7.1. Custom multicaster task executor

Spring cho phép thay default multicaster bằng bean tên `applicationEventMulticaster`:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") Executor executor) {
    var result = new SimpleApplicationEventMulticaster();
    result.setTaskExecutor(executor);
    return result;
}
```

Đây là snippet cấu hình, cần imports Spring và executor bean. Với task executor, multicaster thường submit các listener hỗ trợ asynchronous execution. Một số listeners, chẳng hạn transaction-synchronized listeners, khai báo không hỗ trợ async dispatch qua `ApplicationListener.supportsAsyncExecution()` nên có thể vẫn chạy trên publisher thread.

Vì thế **không được suy ra** từ việc “đã bật executor” rằng tất cả listeners sẽ ở một thread pool duy nhất, hoặc thứ tự của chúng hoàn tất đúng order numbers.

### 7.2. Vì sao single-thread executor cũng không đủ để kết luận luôn FIFO?

Single-thread executor có thể hữu ích nếu cấu hình queue có FIFO và mọi task liên quan thật sự đi qua cùng queue. Nhưng vẫn có:
- Listener chạy đồng bộ vì không hỗ trợ async.
- `@Async` proxy bên trong listener submit tới executor khác.
- Rejection policy như `CallerRunsPolicy` có thể chạy task trên caller.
- Nested event publication tạo một dispatch mới.
- Nhiều application instances có những queues riêng.
- Retry hoặc broker có thứ tự giao lại khác.

Đừng biến “một thread” thành bảo đảm global ordering khi kiến trúc có nhiều đường thực thi.

### 7.3. Test async cần CountDownLatch

Một test bất đồng bộ không nên làm:

```java
publisher.publishEvent(event);
Thread.sleep(100); // Không ổn định khi CI chậm.
assertEquals(expected, recorder.snapshot());
```

Thay bằng công cụ đồng bộ có **timeout**, chẳng hạn `CountDownLatch`:

```java
CountDownLatch completed = new CountDownLatch(2);

// Hai callback async tương ứng gọi completed.countDown()
// sau khi hoàn tất thao tác cần kiểm thử.

publisher.publishEvent(event);
assertTrue(completed.await(5, TimeUnit.SECONDS));
```

Đây là **test snippet**, cần `CountDownLatch`, `TimeUnit`, JUnit, publisher, event và thiết lập callbacks có latch; nó **không** thuộc chương trình phần 5. Latch cho biết hai công việc đã đến một cột mốc, nhưng tự nó **không chứng minh** A hoàn thành trước B. Muốn assert ordering trong một quy trình bất đồng bộ, phải ghi start/finish events trên một thread-safe recorder, hoặc tổ chức dependency qua future chain/workflow.

### 7.4. Nếu B cần A thành công, đừng dựa vào @Order trong async

Nếu `ListenerB` chỉ có thể chạy sau khi `ListenerA` cập nhật DB/remote API thành công, nên xây một dependency rõ:

```text
OrderPlaced
    |
    v
ProjectionService updates projection successfully
    |
    +--> publishes OrderProjectionUpdated
                    |
                    v
               Notifier
```

Nếu bước này cần durability hoặc chạy qua service khác, dùng outbox/message broker và idempotent consumer; không chỉ một nested Spring event in-memory.

## 8. Exception có thể làm listener sau không chạy

Một ví dụ dễ hiểu:

```java
@EventListener
@Order(10)
public void first(OrderPlaced event) {
    throw new IllegalStateException("audit unavailable");
}

@EventListener
@Order(20)
public void second(OrderPlaced event) {
    // Không thể mặc định luôn được gọi.
}
```

Đây là snippet trong beans giả định. Với multicaster đồng bộ mặc định và **không có ErrorHandler suppress**, exception của listener thứ nhất có thể lan về `publishEvent` và dừng luồng dispatch. `@Order` sắp xếp ai được gọi trước, **không buộc tất cả listener chạy bất chấp lỗi**.

### 8.1. ErrorHandler ảnh hưởng đến chuỗi

```java
multicaster.setErrorHandler(error -> {
    logListenerFailure(error);
    // Return normally -> suppress at this boundary.
});
```

Đây là snippet minh họa; `multicaster` và `logListenerFailure` do ứng dụng định nghĩa. Nếu `ErrorHandler` xử lý rồi return, multicaster có thể đi tới listener sau, nhưng lỗi đầu tiên **không tự được sửa**.

Nếu listener A đã thực hiện một phần side effect trước khi lỗi, sự kiện được retry có thể nhân đôi kết quả. Nếu B phụ thuộc trạng thái A, cho B chạy tiếp sau khi suppress lỗi có thể tạo inconsistency. Vì vậy error policy phải phục vụ business contract, không chỉ mục tiêu “có đủ bốn dòng log”.

### 8.2. Async exception thường không về publisher

Với `@Async void`, lỗi có thể đi qua `AsyncUncaughtExceptionHandler`. Với custom multicaster executor, lỗi listener có thể được xử lý bởi `SimpleApplicationEventMulticaster.setErrorHandler(...)` hoặc executor boundary. Còn `Future` có thể giữ exception tới `get()/join()`.

**Không đánh đồng** một lời gọi `publishEvent` trả về bình thường với việc mọi listener thành công, đặc biệt khi async.

## 9. Transaction phase quan trọng hơn @Order

`@TransactionalEventListener` cho phép callback gắn với phase giao dịch:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void updateReport(OrderPlaced event) {
    // Chạy sau commit thành công, nếu có transaction phù hợp.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(20)
public void notifyPartner(OrderPlaced event) {
    // Cùng AFTER_COMMIT phase, thứ tự callback có thể được ưu tiên.
}
```

Đây là snippet trong Spring bean có transaction manager, không thuộc Maven demo.

`@Order` có thể ưu tiên callbacks trong một phase, **không thay đổi chính phase**. Ví dụ:

```text
BEFORE_COMMIT @Order(100)
AFTER_COMMIT  @Order(1)
```

Không có nghĩa `AFTER_COMMIT @Order(1)` chạy trước `BEFORE_COMMIT @Order(100)`, vì lifecycle transaction quyết định trước/sau.

### 9.1. No transaction, no callback theo mặc định

Transactional listener thông thường không chạy khi event được publish ngoài transaction đang hoạt động, trừ khi đã dùng `fallbackExecution=true`. Một test về ordering phải tạo transaction boundary đúng thì mới có dữ liệu để so sánh.

### 9.2. AFTER_COMMIT không phải durable queue

Nếu process crash sau commit trước callback, `@TransactionalEventListener(AFTER_COMMIT)` không tự bảo đảm xử lý lại. Những side effects quan trọng nên đánh giá transactional outbox hoặc Event Publication Registry theo phiên bản/config thực tế.

### 9.3. Ghi database sau commit

Nếu listener sau commit cần ghi state như một transaction mới, sử dụng boundary dịch vụ phù hợp (ví dụ `REQUIRES_NEW` qua Spring proxy), không tự cho rằng `@Order` tạo transaction. Quy tắc về resource synchronization cần xem theo Spring transaction manager đang dùng.

## 10. Nested event làm log xen giữa callbacks

Listener A có thể publish một event mới trong lúc vẫn xử lý event cũ:

```java
@EventListener
@Order(10)
public void recordAudit(OrderPlaced event) {
    logger.info("A starts");
    publisher.publishEvent(new AuditRecorded(event.orderId()));
    logger.info("A ends");
}

@EventListener
@Order(20)
public void reportMetrics(OrderPlaced event) {
    logger.info("B starts");
}
```

Đây là snippet minh họa; cần publisher, logger và kiểu `AuditRecorded`. Trong synchronous dispatch:

```text
OrderPlaced:
  A starts
  AuditRecorded listeners execute
  A ends
  B starts
```

Do đó, log của các `AuditRecorded` listeners có thể xuất hiện giữa log A và B mà **không có vi phạm @Order**. Có một dispatch lồng vào dispatch khác.

Nguy hiểm hơn, nếu listener của `OrderPlaced` phát lại chính `OrderPlaced` không có điều kiện dừng, ứng dụng có thể đệ quy sâu, phát trùng và gây stack overflow.

Cần phân biệt:
- Thứ tự callbacks của một event occurrence.
- Thứ tự những event occurrences được publish.
- Thứ tự nested event.
- Thứ tự side effects/commit.

Nếu nested chain đã trở thành workflow nhiều bước phức tạp, dùng orchestration/state machine sẽ dễ review và khôi phục lỗi hơn.

## 11. Condition và nhiều listener methods trong một bean

Một phương thức có thể dùng điều kiện để chỉ xử lý một số events:

```java
@EventListener
@Order(10)
public void on(OrderPlaced event) {
    if (!event.orderId().startsWith("VIP-")) {
        return;
    }
    // Xử lý VIP order.
}
```

Đây là snippet. Nó vẫn được **gọi**, nhưng có thể kết thúc sớm và không tạo side effect. Với `@EventListener(condition="...")`, Spring có thể lọc trước khi gọi method theo SpEL.

Vì vậy, thấy ít log hơn dự kiến không nhất thiết là lỗi ordering. Cần kiểm tra type matching, condition, exceptions và việc listener có thực sự được đăng ký.

Khi nhiều `@EventListener` methods nằm trong cùng bean, không dựa vào thứ tự khai báo method trong Java file. Hãy đặt order trực tiếp trên các method có ràng buộc rõ ràng và viết integration test nếu thứ tự là yêu cầu thực sự.

### Listener trả về một event mới

Một `@EventListener` method có non-void return type có thể làm Spring publish return value như một event mới. Vì vậy:

```java
@EventListener
public AuditRecorded on(OrderPlaced event) {
    return new AuditRecorded(event.orderId());
}
```

Đây là snippet minh họa; cần class `AuditRecorded`. Nó không chỉ trả về một giá trị thông thường cho publisher. Việc tạo thêm event có thể sinh nested dispatch và làm log interleave; với async listener, Spring có hạn chế riêng về return-value event publication.

Nếu muốn rõ ràng, inject `ApplicationEventPublisher` và publish tường minh sau khi nghiệp vụ hoàn thành, kèm ràng buộc transaction/reliability phù hợp.

## 12. Không dùng order để thực hiện workflow nghiệp vụ bắt buộc

Giả sử hệ thống phải:

1. Dự trữ kho.
2. Capture tiền.
3. Xác nhận đơn.
4. Tạo yêu cầu giao hàng.

Nếu một bước thất bại thì các bước sau không được tiếp tục. Đây là một **workflow có dependency**, không phải bốn subscribers hoàn toàn độc lập. Việc viết:

```text
@Order(10) reserveStock
@Order(20) captureMoney
@Order(30) confirmOrder
@Order(40) shipOrder
```

là một thiết kế dễ sai, đặc biệt nếu publisher gọi listener trong transaction chưa commit, có IO ngoài DB, async hoặc cần compensation.

Phương án có trách nhiệm rõ ràng:

```text
OrderApplicationService / Saga Coordinator
    |
    +-- validate authorization and business state
    +-- reserve stock -> await outcome
    +-- capture payment -> await outcome / compensate if needed
    +-- transition domain state
    +-- persist state and event/outbox
    |
    +-- emit OrderConfirmed fact
             |
             +-- independent audit consumer
             +-- independent analytics consumer
             +-- independent notification consumer
```

Cơ chế event fan-out thích hợp với **các hành động độc lập phản ứng sau một fact**. Nếu B cần A đã làm thành công, cân nhắc gọi service theo thứ tự rõ ràng hoặc phát một fact khác **sau A thành công** với contract tương ứng.

### 12.1. @Order không tạo transaction

Tác vụ trong `@Order(10)` không tự commit trước `@Order(20)`, nhất là khi cả hai tham gia cùng transaction hoặc dùng repository/remote API khác nhau. `@Order` chỉ điều chỉnh invocation/scheduling của listeners.

### 12.2. @Order không tạo delivery guarantee

Một event xử lý trong JVM không tự được lưu bền vững. Nếu ứng dụng restart giữa chừng, không có replay tự động từ Spring core chỉ vì order numbers đã khai báo.

Nếu side effects phải bền vững, thiết kế outbox/broker/retry và idempotent consumers. Đừng dựa vào thứ tự log để xác nhận external delivery.

### 12.3. @Order không giải quyết duplicate

Nếu publisher phát lại cùng fact, mọi listener có thể nhận lại. Để tránh gửi hai email, tạo hai shipment hoặc ghi đè state, cần event ID/business idempotency key và unique constraints hoặc external idempotency theo boundary thực tế.

## 13. Bảng phân biệt các loại thứ tự

| Loại thứ tự | Ví dụ | @Order giải quyết? |
| --- | --- | --- |
| Bean initialization order | Constructor bean nào chạy trước | **Không**, phụ thuộc dependency graph |
| Listener selection | Event nào gọi listener nào | **Không**, dùng event type/condition |
| Listener invocation priority | Cùng event, callback nào được gọi trước | **Có**, đây là mục đích chính |
| Synchronous completion | Listener A xong rồi B chạy | Thường có nếu dispatch sync và không bị lỗi/nested dependency |
| Async completion | Task A hay B kết thúc trước | **Không** |
| Transaction phase | BEFORE_COMMIT vs AFTER_COMMIT | **Không**, dùng transaction synchronization phase |
| Database commit order | Hai transactions commit ra sao | **Không** |
| Global event order | Events từ nhiều threads/services | **Không** |
| Broker delivery order | Message thứ tự trên Kafka/RabbitMQ | **Không**, tùy partition/consumer configuration |
| Aggregate version | Event version 5 vs 6 | **Không**, cần version/sequence |
| External side effects | Email, payment, shipment hoàn thành lúc nào | **Không**, có contract riêng |

Một quy tắc an toàn: khi nói “đã sắp xếp đúng”, luôn ghi rõ **đang sắp xếp cái gì và ở ranh giới nào**.

## 14. Kiểm thử và vận hành: không nhầm log với ordering

Trong production, log có thể xen kẽ vì nhiều publishers/threads, nested events, async appenders hoặc tracing propagation. So sánh **timestamp của các dòng log** để chứng minh `@Order` có thể rất dễ sai.

Dùng recorder/test probe cho integration test như phần 6. Khi debug production, log có cấu trúc:

```text
event_type=OrderPlaced event_id=E-100 listener=audit order=10 outcome=START
event_type=OrderPlaced event_id=E-100 listener=audit order=10 outcome=SUCCESS
event_type=OrderPlaced event_id=E-100 listener=projection order=20 outcome=START
event_type=OrderPlaced event_id=E-100 listener=projection order=20 outcome=SUCCESS
```

Đây là log minh họa, **không phải output Spring tự tạo**. Event ID nên định danh occurrence thực sự, có thể dùng cùng correlation ID cho workflow. Không đưa raw event payload/PII/token vào log. Raw event ID/user ID cũng không nên làm metric tag high-cardinality.

### 14.1. Quy trình tìm lỗi khi order khác dự kiến

1. Kiểm tra chính xác event type được phát và listener nào match.
2. Kiểm tra `@EventListener` và `@Order` có nằm trên đúng method không.
3. Kiểm tra bean `ApplicationListener` có implement `Ordered` không, getOrder trả giá trị nào.
4. Kiểm tra nhiều listener có cùng order/default order.
5. Xác định có custom `applicationEventMulticaster`/executor không.
6. Kiểm tra `@Async` hoặc listener tự submit `CompletableFuture`.
7. Kiểm tra `@TransactionalEventListener` phase, transaction có tồn tại không.
8. Kiểm tra listener có ném exception hoặc ErrorHandler suppress hay không.
9. Kiểm tra nested events và lời gọi publish phát sinh trong listener khác.
10. Kiểm tra có nhiều publisher threads/contexts/replicas không.
11. Tái hiện bằng integration test với recorder đúng context.
12. Nếu liên quan kết quả cuối, assert side effects/commit thay vì chỉ callback order.

### 14.2. Test các nhánh lỗi

Ngoài test happy path, hãy kiểm chứng:

| Test | Cần xác minh |
| --- | --- |
| Listener order 10 ném exception sync | Publisher nhận lỗi đúng policy, callbacks sau có thể không chạy |
| Multicaster có ErrorHandler suppress | Metrics/alert ghi thất bại; không giả rằng A thành công |
| Two listeners same order | Không khẳng định thứ tự ổn định nếu contract không có |
| Condition lọc event | Listener được gọi hoặc bỏ qua theo đúng điều kiện |
| Async listener chậm | Không yêu cầu completion order bằng @Order |
| Nested publication | Recorder phân biệt event types/occurrences |
| Transaction rollback | AFTER_COMMIT callback không chạy nếu rollback |
| No active transaction | Transactional listener mặc định không được gọi |
| Two publisher threads | Mỗi dispatch có ordering riêng, không giả global serialization |
| Multiple application contexts | Scope đăng ký listener đúng, không phát trùng do hierarchy |

## 15. Những lỗi thường gặp

1. **Đọc @Order(30) là ưu tiên hơn @Order(10).** Spring ưu tiên số nhỏ.
2. **Đặt hai listeners cùng order rồi trông đợi source order.** Relative order không phải hợp đồng.
3. **Cho rằng annotation order sắp xếp bean initialization.** Không phải.
4. **Đặt @Order trên class rồi nghĩ mọi @EventListener methods được ưu tiên đúng.** Method-level rõ ràng hơn.
5. **Cho rằng mọi listener chạy async chỉ vì context có executor.** Một số không hỗ trợ async dispatch.
6. **Cho rằng @Async order 10 luôn hoàn thành trước order 20.** Worker scheduling không bảo đảm.
7. **Chạy test async với ArrayList recorder.** Không thread-safe.
8. **Dùng Thread.sleep để kiểm tra completion.** Test flake theo CI load.
9. **Chỉ nhìn log timestamp rồi kết luận ordering sai.** Có async, nested events và buffer.
10. **Quên transaction phase của @TransactionalEventListener.** AFTER_COMMIT khác invocation tại publish.
11. **Dùng @Order để chạy nghiệp vụ bắt buộc nhiều bước.** Thiếu rollback/compensation/retry.
12. **Quên listener đầu có thể ném exception.** Listener sau không nhất thiết được gọi.
13. **Suppress exception rồi báo success.** Task có thể thất bại một phần.
14. **Coi event publish là durable message.** Spring core không tự tạo outbox.
15. **Cho rằng @Order sắp xếp events khác type.** Chỉ có ý nghĩa với tập listener của một dispatch.
16. **Dựa vào thứ tự hoàn tất giữa các threads.** Không có global serializing.
17. **Listener A sửa object event mutable để listener B đọc.** Tạo coupling/race khó kiểm thử.
18. **Đặt mọi listener HIGHEST_PRECEDENCE.** Không còn sự phân biệt rõ.
19. **Không kiểm tra listener đăng ký hai lần.** Có thể có hai beans/contexts.
20. **Dùng idempotency theo correlation ID.** Một workflow có thể tạo nhiều facts.
21. **Cho rằng @Order điều khiển broker ordering.** Transport có hợp đồng riêng.
22. **Không test trên đúng Spring context.** Gọi thẳng callback bỏ qua multicast/sorting.
23. **Không clear recorder giữa tests.** Dữ liệu test trước gây flaky assertions.
24. **Thêm @EventListener return value mà không nghĩ Spring phát thêm event.** Nested dispatch có thể thay đổi quan sát.
25. **Xem callback được gọi là side effect đã commit.** Không có bảo đảm tương đương.

## 16. Checklist trước khi dùng @Order trên nhiều listeners

- [ ] Đã phân biệt listener selection, invocation và completion?
- [ ] Có biết Spring multicaster đang synchronous hay asynchronous không?
- [ ] Các listeners của cùng một event đã có priority rõ ràng khi cần?
- [ ] Số nhỏ hơn được hiểu là ưu tiên cao hơn?
- [ ] Không có tie order ở nơi bắt buộc thứ tự khác nhau?
- [ ] @Order đặt trực tiếp trên event listener method quan trọng?
- [ ] ApplicationListener implement Ordered.getOrder() đúng khi cần?
- [ ] Không dùng PriorityOrdered nếu chưa có lý do kỹ thuật và test?
- [ ] Không dùng @Order để cố ép thứ tự bean initialization?
- [ ] Listener B có độc lập với side effect của listener A không?
- [ ] Transaction phase đã được mô hình hóa đúng, không chỉ dùng số order?
- [ ] Async callbacks có completion/failure policy riêng?
- [ ] Exception sớm có thể ngăn callback sau không?
- [ ] Nested event có tạo recursion hoặc interleaving không?
- [ ] Test sử dụng real Spring context và CallRecorder?
- [ ] Async test dùng CountDownLatch/timeout/thread-safe recorder phù hợp?
- [ ] Không lấy log flush order làm chứng minh callback order?
- [ ] Khi cần side effect bền vững, đã có outbox/retry/idempotency?
- [ ] Có tài liệu convention order để đồng đội không vô tình phá đổi thứ tự?

**Tổng kết:** Trong Spring Framework Application Events, `@Order` và `Ordered` là công cụ sắp xếp **thứ tự gọi nhiều listener cho cùng một event**; số order nhỏ hơn được ưu tiên trước. Với `SimpleApplicationEventMulticaster` đồng bộ mặc định, điều đó cho phép kiểm thử danh sách callback một cách xác định. Nhưng khi có `@Async`, custom executor, phase giao dịch, lỗi và nested events, **thứ tự callback không còn đồng nghĩa với thứ tự hoàn tất hay tính nhất quán nghiệp vụ**. Dùng ordering cho những nhu cầu tổ chức listener thật sự; dùng workflow và cơ chế giao dịch/tin cậy riêng cho các dependency quan trọng.

## Tài liệu tham khảo

- [Spring Framework — Additional Capabilities of ApplicationContext, Ordering Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Ordered Interface](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html)
- [Spring Framework — @Order Annotation](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
