# Nhiều listener độc lập cho một event

## 1. Mẫu triển khai: một sự việc, nhiều phản ứng

Trong Spring Framework Application Events, một application service có thể công bố **một domain event** khi nghiệp vụ xảy ra, rồi nhiều listener đăng ký xử lý những trách nhiệm riêng:

~~~text
PlaceOrder use case
    |
    +-- publishEvent(OrderPlaced #101)     [MỘT lần publish]
                  |
                  +--> AuditListener        [ghi audit]
                  |
                  +--> LoyaltyListener      [tính điểm thưởng]
                  |
                  +--> NotificationListener [tạo yêu cầu thông báo]
~~~

Đây là mẫu **fan-out / publish–subscribe nội bộ**. Bên phát chỉ nói “đơn hàng đã được đặt”; nó không cần gọi trực tiếp từng listener. Mỗi listener tập trung vào một việc phụ trợ, được thêm hoặc thay đổi mà không buộc application service biết danh sách đầy đủ các bước hậu xử lý.

Một event có ba listener **không phải ba lần publish**: chỉ có một lời gọi `ApplicationEventPublisher.publishEvent(...)`, sau đó Spring tìm và gọi các listener phù hợp.

Bài này giải thích cách tổ chức các listener **độc lập về trách nhiệm**, cách đăng ký bằng `@EventListener`, kiểm thử fan-out bằng `ApplicationContext` thật và những giới hạn quan trọng: lỗi listener đồng bộ, thứ tự thực thi, `@Async`, transaction, idempotency và độ bền của event.

### “Độc lập” có nghĩa gì?

Nên hiểu **độc lập ở tầng thiết kế nghiệp vụ**:

- `AuditListener` không cần gọi `LoyaltyListener`, và ngược lại.
- Mỗi handler phụ thuộc vào service/repository của **chính trách nhiệm** đó.
- Không handler nào đọc hoặc sửa một object event mutable để điều khiển handler khác.
- Publisher không chứa danh sách `@audit(); loyalty(); notify();`, mà chỉ công bố **fact**.
- Có thể thêm một listener mới mà không sửa contract của publisher, miễn payload đã đủ thông tin phù hợp.

**Nhưng độc lập về trách nhiệm không có nghĩa độc lập về hạ tầng hoặc cách ly lỗi.** Với Spring multicaster đồng bộ mặc định, listener vẫn chạy nối tiếp trên một thread; một exception có thể làm những listener sau không được gọi. Vì vậy phải phân biệt *decoupling* với *failure isolation* và *durable delivery*.

## 2. Spring thực hiện fan-out như thế nào?

Khi ứng dụng gọi:

~~~java
publisher.publishEvent(new OrderPlaced(101L));
~~~

Spring sẽ dùng cơ chế `ApplicationEventMulticaster` để tìm các listener phù hợp với kiểu event. Với các method của bean được đánh dấu `@EventListener`, Spring đăng ký adapter listener dựa trên chữ ký method.

Ví dụ ba bean khác nhau cùng nhận `OrderPlaced`:

~~~java
@Component
class AuditListener {
    @EventListener
    public void on(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}

@Component
class LoyaltyListener {
    @EventListener
    public void on(OrderPlaced event) {
        loyaltyService.awardPoints(event.orderId());
    }
}

@Component
class NotificationListener {
    @EventListener
    public void on(OrderPlaced event) {
        notificationService.enqueue(event.orderId());
    }
}
~~~

Đây là **mã minh họa**: để biên dịch cần các bean service, kiểu `OrderPlaced` và import phù hợp. Phần 5 có một dự án chạy độc lập, đăng ký bean bằng `@Bean` thay vì `@Component`, giúp phân biệt rõ từng thành phần.

Trong cấu hình mặc định của Spring Framework:

1. `SimpleApplicationEventMulticaster` là multicaster thông dụng.
2. Các listener hỗ trợ event và không được cấu hình async được gọi **đồng bộ**, thường ngay trong thread gọi `publishEvent(...)`.
3. Mỗi listener nhận event phù hợp theo type; không cần kế thừa `ApplicationEvent` nếu công bố object thông thường qua `publishEvent(Object)`.
4. Listener có thể được gọi qua `@EventListener` hoặc `ApplicationListener`; hãy tránh vô tình đăng ký cùng logic hai lần.
5. Lời gọi publisher trả về bình thường **không phải bảo đảm transaction nghiệp vụ đã commit** nếu publisher được gọi bên trong transaction chưa hoàn tất.
6. Application event mặc định là **in-process dispatch**, không phải broker bền vững hay cơ chế exactly-once.

### Phân biệt publish, dispatch, execution và completion

| Mốc | Điều gì đã xảy ra? | Chưa chắc đã xảy ra |
| --- | --- | --- |
| `publishEvent(...)` được gọi | Publisher đưa event vào cơ chế dispatch | DB đã commit, mọi side effect thành công |
| Listener adapter được chọn | Spring xác định listener phù hợp với kiểu event | Thân method đã chạy |
| Listener được gọi | Handler bắt đầu thực thi | Handler hoàn thành thành công |
| Handler trả về | Handler đồng bộ hoàn tất lời gọi | I/O đã bền vững sau commit của transaction khác |
| Async task được submit | Executor nhận việc theo cấu hình | Worker đã xử lý xong |
| Transaction commit | Dữ liệu trong transaction đó được commit | Email/broker message hậu commit đã được giao |

Tách những mốc này là cơ sở để viết test và metrics không gây hiểu nhầm.

## 3. Tách trách nhiệm để listener thật sự độc lập

Một cách tổ chức file/bean:

~~~text
orders/
  OrderApplicationService
  OrderPlaced             (event contract)

audit/
  OrderAuditListener
  AuditRepository

loyalty/
  OrderLoyaltyListener
  LoyaltyLedger

notifications/
  OrderNotificationListener
  NotificationGateway
~~~

Điểm tốt của thiết kế:

- **Single responsibility:** audit không cần biết điểm thưởng; loyalty không gửi email.
- **Open/closed:** bổ sung search index listener thường không phải sửa publisher.
- **Testability:** mỗi handler có thể unit test riêng bằng event và dependency giả, bên cạnh integration test cho Spring fan-out.
- **Khả năng thay đổi:** có thể chuyển notification sang queue/broker sau này mà không bắt publisher gọi gateway trực tiếp.
- **Giảm coupling theo thời gian:** publisher không phải giữ danh sách các phần phụ trợ tăng dần.

Điểm cần giữ kỷ luật:

- Nếu `NotificationListener` gọi trực tiếp `AuditListener` để “chờ audit xong”, hai listener không còn độc lập.
- Nếu một listener sửa event mutable để listener khác đọc, thứ tự và race trở thành dependency ẩn.
- Nếu một listener phải chạy trước một listener khác để nghiệp vụ đúng, đây có thể là **workflow có thứ tự** chứ không còn là những subscriber độc lập.
- Nếu chính thao tác audit là yêu cầu pháp lý phải commit atomically với đơn hàng, đừng tự ý đẩy nó ra một callback best-effort chỉ vì tiện.

### Event nên là fact tối thiểu, immutable

Ví dụ:

~~~java
public record OrderPlaced(
    java.util.UUID eventId,
    long orderId,
    java.time.Instant occurredAt
) {}
~~~

Đây là mã định nghĩa kiểu độc lập có thể đặt trong file riêng, cần package/import phù hợp. Event nên mang dữ liệu **đã xảy ra**, với `eventId` để hỗ trợ deduplication khi tích hợp bền vững. Tránh truyền cả JPA entity, `HttpServletRequest`, access token hoặc mutable object graph. Mỗi listener có thể truy vấn những dữ liệu cần thiết qua repository/service của chính nó theo quyền được cấp.

Tùy nhu cầu, còn có thể thêm `aggregateId`, `causationId`, `correlationId` hoặc schema version; không nhất thiết mọi bài toán cần tất cả metadata. Không dùng `eventId` làm metric tag có cardinality cao; ưu tiên log/trace có retention phù hợp.

## 4. Chọn event và listener tương ứng với nghiệp vụ

Một workflow đặt hàng gồm vài loại thông tin:

~~~text
Command: PlaceOrder
    |
    v
Order application/domain service
    |
    +-- kiểm tra điều kiện bắt buộc
    +-- ghi order theo transaction
    |
    +-- publish OrderPlaced (theo boundary phù hợp)
              |
              +-- create audit projection
              +-- update loyalty projection
              +-- request notification
~~~

Tránh hai dạng thiết kế sai:

**Một publisher biết quá nhiều:**

~~~java
// Anti-pattern minh họa.
public void placeOrder(PlaceOrder command) {
    orderRepository.save(...);
    auditService.record(...);
    loyaltyService.award(...);
    notificationService.enqueue(...);
}
~~~

Không phải lúc nào đoạn này cũng sai: nếu nghiệp vụ yêu cầu các thao tác có thứ tự, đồng bộ và rollback cùng nhau, orchestration trực tiếp có thể **đúng hơn** event-driven fan-out. Nó chỉ trở thành vấn đề khi publisher bị kéo theo ngày càng nhiều công việc phụ trợ **độc lập, không bắt buộc**.

**Một listener ôm tất cả trách nhiệm:**

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    auditService.record(event.orderId());
    loyaltyService.award(event.orderId());
    notificationService.enqueue(event.orderId());
}
~~~

Nếu audit lỗi, loyalty/notification chưa được gọi; trách nhiệm và chính sách lỗi bị trộn vào một method. Khi có yêu cầu tách biệt hợp lý, dùng ba listener riêng. Tuy nhiên, nếu ba việc thực sự phải thành công cùng nhau hoặc theo thứ tự chặt chẽ, nên giữ một workflow rõ ràng, không tách chỉ vì “nhiều listener nghe có vẻ đẹp”.

## 5. Ví dụ Java 17+ chạy được: một event, ba listener riêng

Ví dụ sử dụng **Spring Framework 6.2.19**, Java 17+, JUnit Jupiter 5.12.2 và Gradle. Không cần Spring Boot hoặc database.

Ba store ở đây là **bản mô phỏng in-memory**, mỗi store thuộc một trách nhiệm: audit, loyalty, notification. Listener không gọi nhau. Chương trình phát đúng một `OrderPlaced`, sau đó đọc trạng thái riêng của ba store để kiểm chứng.

### Cấu trúc dự án

~~~text
fanout-listeners-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/FanOutDemo.java
    └── test/java/demo/FanOutDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'fanout-listeners-demo'
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
    mainClass = 'demo.FanOutDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/FanOutDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public final class FanOutDemo {

    private FanOutDemo() {}

    // Với production nên bổ sung eventId/occurredAt nếu cần.
    // Demo này không dùng database, chỉ chứng minh fan-out.
    public record OrderPlaced(long orderId) {}
    public record StockRecounted(long productId) {}

    // Mỗi store mô phỏng một nơi lưu/nhận việc riêng.
    public static final class AuditTrail {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void record(OrderPlaced e) {
            items.add("audit:" + e.orderId());
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class LoyaltyLedger {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void award(OrderPlaced e) {
            items.add("points:" + e.orderId() + ":+10");
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class NotificationQueue {
        private final List<String> items =
            new CopyOnWriteArrayList<>();

        public void enqueue(OrderPlaced e) {
            items.add("notify:" + e.orderId());
        }

        public List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static final class PlaceOrder {
        private final ApplicationEventPublisher publisher;

        public PlaceOrder(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(long orderId) {
            // Trong demo, giả định nghiệp vụ đặt hàng đã thành công.
            // Ứng dụng thật phải xác định transaction/commit boundary.
            publisher.publishEvent(new OrderPlaced(orderId));
        }
    }

    public static final class AuditListener {
        private final AuditTrail store;

        public AuditListener(AuditTrail store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.record(event);
        }
    }

    public static final class LoyaltyListener {
        private final LoyaltyLedger store;

        public LoyaltyListener(LoyaltyLedger store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.award(event);
        }
    }

    public static final class NotificationListener {
        private final NotificationQueue store;

        public NotificationListener(NotificationQueue store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            store.enqueue(event);
        }
    }

    // Đăng ký tường minh đúng ba bean listener.
    // KHÔNG bật @ComponentScan để tránh đăng ký trùng.
    @Configuration
    public static class FanOutConfig {

        @Bean
        AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        LoyaltyLedger loyaltyLedger() {
            return new LoyaltyLedger();
        }

        @Bean
        NotificationQueue notificationQueue() {
            return new NotificationQueue();
        }

        @Bean
        PlaceOrder placeOrder(
                ApplicationEventPublisher publisher) {
            return new PlaceOrder(publisher);
        }

        @Bean
        AuditListener auditListener(AuditTrail store) {
            return new AuditListener(store);
        }

        @Bean
        LoyaltyListener loyaltyListener(LoyaltyLedger store) {
            return new LoyaltyListener(store);
        }

        @Bean
        NotificationListener notificationListener(
                NotificationQueue store) {
            return new NotificationListener(store);
        }
    }

    // Nhóm bean riêng cho ví dụ lỗi trong unit/integration test.
    public static final class FailureLog {
        private final List<String> calls =
            new CopyOnWriteArrayList<>();

        public void add(String value) {
            calls.add(value);
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    public static final class FailingListener {
        private final FailureLog log;

        public FailingListener(FailureLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-10)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("first-throws");
            throw new IllegalStateException("listener failed");
        }
    }

    public static final class LaterListener {
        private final FailureLog log;

        public LaterListener(FailureLog log) {
            this.log = log;
        }

        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("later");
        }
    }

    @Configuration
    public static class FailureConfig {

        @Bean
        FailureLog failureLog() {
            return new FailureLog();
        }

        @Bean
        FailingListener failingListener(FailureLog log) {
            return new FailingListener(log);
        }

        @Bean
        LaterListener laterListener(FailureLog log) {
            return new LaterListener(log);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutConfig.class)) {

            ctx.getBean(PlaceOrder.class).place(101L);

            // Không dựa vào thứ tự listener:
            // chỉ đọc các projection sau khi publish sync hoàn tất.
            System.out.println("published=1");
            System.out.println(
                "audit=" +
                ctx.getBean(AuditTrail.class).snapshot());
            System.out.println(
                "loyalty=" +
                ctx.getBean(LoyaltyLedger.class).snapshot());
            System.out.println(
                "notification=" +
                ctx.getBean(NotificationQueue.class).snapshot());
        }
    }
}
~~~

### Chạy và kiểm tra

~~~bash
gradle run --quiet
# Linux/macOS nếu có wrapper: ./gradlew run --quiet
# Windows nếu có wrapper: gradlew.bat run --quiet
~~~

Các dòng do chính chương trình in ra:

~~~text
published=1
audit=[audit:101]
loyalty=[points:101:+10]
notification=[notify:101]
~~~

Cần đọc output đúng nghĩa:

1. `PlaceOrder.place(101L)` chỉ gọi `publishEvent(...)` **một lần**.
2. Spring tìm ba `@EventListener` nhận `OrderPlaced` trong `FanOutConfig`.
3. Mỗi listener cập nhật **store riêng** và không gọi listener khác.
4. Với `SimpleApplicationEventMulticaster` đồng bộ mặc định, khi `place(...)` trả về thì ba listener đã hoàn tất phần xử lý mô phỏng.
5. Chương trình in snapshot các store theo thứ tự cố định do **`main` sắp xếp các lệnh println**, không phải do Spring bảo đảm thứ tự listener.
6. `CopyOnWriteArrayList` giúp collector có thể đọc an toàn trong demo; đây không phải persistence và không thay thế database, message queue hay transaction.

**Vì sao không gắn `@Order` cho ba listener chính?** Vì nghiệp vụ mô phỏng không yêu cầu audit, loyalty và notification phải chạy theo thứ tự. Thêm `@Order` chỉ để test dễ pass có thể che dependency thiết kế. Mục 6 dùng `@Order` trong một bài test **riêng**, khi cần chứng minh rõ đường truyền exception của multicaster đồng bộ.

## 6. Kiểm thử bằng JUnit 5 với Spring ApplicationContext thật

Tạo tệp `src/test/java/demo/FanOutDemoTest.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FanOutDemoTest {

    @Test
    void oneEventReachesAllThreeIndependentListeners() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            ctx.getBean(FanOutDemo.PlaceOrder.class).place(101L);

            assertEquals(
                List.of("audit:101"),
                ctx.getBean(FanOutDemo.AuditTrail.class).snapshot());

            assertEquals(
                List.of("points:101:+10"),
                ctx.getBean(FanOutDemo.LoyaltyLedger.class).snapshot());

            assertEquals(
                List.of("notify:101"),
                ctx.getBean(
                    FanOutDemo.NotificationQueue.class).snapshot());
        }
    }

    @Test
    void twoPublicationsReachEachListenerOncePerEvent() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            var publisher = ctx.getBean(FanOutDemo.PlaceOrder.class);
            publisher.place(101L);
            publisher.place(102L);

            assertEquals(
                List.of("audit:101", "audit:102"),
                ctx.getBean(FanOutDemo.AuditTrail.class).snapshot());

            assertEquals(
                List.of("points:101:+10", "points:102:+10"),
                ctx.getBean(FanOutDemo.LoyaltyLedger.class).snapshot());

            assertEquals(
                List.of("notify:101", "notify:102"),
                ctx.getBean(
                    FanOutDemo.NotificationQueue.class).snapshot());
        }
    }

    @Test
    void anotherEventTypeDoesNotTriggerOrderListeners() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FanOutConfig.class)) {

            ctx.publishEvent(new FanOutDemo.StockRecounted(99L));

            assertTrue(
                ctx.getBean(FanOutDemo.AuditTrail.class)
                    .snapshot().isEmpty());
            assertTrue(
                ctx.getBean(FanOutDemo.LoyaltyLedger.class)
                    .snapshot().isEmpty());
            assertTrue(
                ctx.getBean(FanOutDemo.NotificationQueue.class)
                    .snapshot().isEmpty());
        }
    }

    @Test
    void oneFailingSyncListenerCanStopLaterListener() {
        try (var ctx = new AnnotationConfigApplicationContext(
                FanOutDemo.FailureConfig.class)) {

            assertThrows(
                IllegalStateException.class,
                () -> ctx.publishEvent(
                    new FanOutDemo.OrderPlaced(103L))
            );

            // @Order(-10) listener ném lỗi trước @Order(10).
            // Default multicaster chưa có ErrorHandler.
            assertEquals(
                List.of("first-throws"),
                ctx.getBean(FanOutDemo.FailureLog.class).snapshot()
            );
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
# Linux/macOS nếu có wrapper: ./gradlew test
# Windows nếu có wrapper: gradlew.bat test
~~~

Kỳ vọng **bốn bài test pass** nếu chạy với dependency và cấu hình trong ví dụ:

- **Test 1:** một lần publish được ba listener nhận, mỗi nơi ghi một kết quả.
- **Test 2:** hai lần publish làm từng listener nhận hai event. Không cộng kết quả của ba listener để gọi đó là “sáu event đã phát”.
- **Test 3:** listener lọc theo event type. Event `StockRecounted` không khớp `OrderPlaced`, nên ba store của đơn hàng trống.
- **Test 4:** `FailingListener` có `@Order(-10)` được gọi trước `LaterListener` có `@Order(10)`. Listener đầu ném `IllegalStateException`; multicaster đồng bộ mặc định không có `ErrorHandler`, nên exception lan về publisher và listener phía sau **không chạy**.

**Điểm then chốt:** fan-out thành công không chứng minh *mức độ chịu lỗi*. Test thứ tư cố tình cho thấy ba listener tách bean vẫn có thể bị ảnh hưởng bởi một exception ở đường dispatch đồng bộ. Khi thay đổi cấu hình multicaster hoặc `@Async`, phải điều chỉnh các assertion cho đúng contract mới.

Không dùng mock `ApplicationEventPublisher` rồi kết luận fan-out đã hoạt động: mock chỉ chứng minh phương thức publish được gọi, không nhất thiết tạo ra listener dispatch. Các test trên dùng Spring `ApplicationContext` thật để kiểm tra đăng ký và routing.

## 7. Xử lý khi một listener bị lỗi

Với default `SimpleApplicationEventMulticaster` đồng bộ, **một listener ném unchecked exception có thể dừng lượt dispatch và truyền lỗi về thread publisher**.

~~~text
publishEvent(OrderPlaced)
    |
    +--> AuditListener: OK
    |
    +--> LoyaltyListener: throws
    |
    +--> NotificationListener: có thể không được gọi
    |
    +--> publisher nhận exception
~~~

Thứ tự ở sơ đồ chỉ **minh họa**; không có `@Order` thì không lấy vị trí đó làm một contract. Trong transaction `@Transactional`, exception đồng bộ lan ra khỏi service có thể dẫn đến rollback theo quy tắc transaction; side effect không nằm trong transaction (email, HTTP API) **không tự được hoàn tác**.

### Hướng xử lý tùy độ quan trọng

| Trường hợp | Hướng thiết kế |
| --- | --- |
| Một listener kiểm tra invariant bắt buộc để cho phép transaction commit | Cân nhắc xử lý trực tiếp trong use case/domain hoặc cùng transaction, không coi là hậu xử lý độc lập |
| Listener audit phải commit atomically với order | Ghi cùng transaction hoặc dùng thiết kế domain/outbox phù hợp với yêu cầu |
| Notification chỉ là best-effort | Có thể tách async + monitoring, có chính sách mất việc rõ ràng |
| Notification không được mất khi order commit | Transactional outbox + worker có retry/idempotency |
| Một handler lỗi không nên chặn handler khác nhưng vẫn cần phát hiện lỗi | Chọn cơ chế error handling phù hợp, log/metric/alert và retry |
| Có dependency “A xong thì B mới chạy” | Dùng orchestration/workflow rõ, không dựng dependency bằng order ngẫu nhiên |

Có thể cấu hình `ErrorHandler` cho `SimpleApplicationEventMulticaster` để xử lý exception và cho các listener khác tiếp tục, nhưng **log và suppress không biến tác vụ lỗi thành thành công**:

~~~java
// Mẫu cấu hình minh họa; không thuộc project ở mục 5.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster() {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(
        TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER
    );
    return multicaster;
}
~~~

Đoạn này cần import `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `TaskUtils`, `@Bean` và cấu hình Spring thích hợp. Khi suppress, caller có thể không nhận exception nhưng failure vẫn phải được giám sát và phục hồi theo hợp đồng nghiệp vụ. Nếu downstream có side effect quan trọng, không dùng suppress như cách “giải quyết” lỗi.

## 8. @Order không tạo sự độc lập hay trình tự nghiệp vụ bền vững

`@Order` được Spring hỗ trợ để ưu tiên **invocation** listener. Giá trị nhỏ hơn có ưu tiên cao hơn:

~~~java
@EventListener
@Order(-10)
void first(OrderPlaced e) { ... }

@EventListener
@Order(10)
void second(OrderPlaced e) { ... }
~~~

Nếu cùng event, đồng bộ và multicaster sử dụng thứ tự này, `first` được gọi trước `second`. Nhưng:

- Cùng một mức `@Order` thì không nên dựa vào thứ tự ổn định.
- `Order` không nói một listener sẽ **commit** thành công trước listener khác.
- Với `@Async` hoặc executor, độ ưu tiên dispatch **không bảo đảm thứ tự hoàn thành**.
- Một listener có thể phát event lồng nhau, tạo thứ tự thực thi khác việc “xử lý xong tất cả event A rồi mới tới event B”.
- Parent/child Spring contexts có multicaster riêng; một giá trị `@Order` không áp dụng thứ tự toàn cục xuyên mọi context.

Nếu B thực sự cần kết quả A, cân nhắc một orchestrator gọi A rồi B với contract và transaction rõ, hoặc một workflow phát event **tiếp theo** sau khi A xác nhận hoàn tất. Đừng dựa vào “nó thường chạy trước ở môi trường dev”.

## 9. Một listener chạy @Async có còn độc lập hơn không?

`@Async @EventListener` (khi có `@EnableAsync` và `TaskExecutor` thích hợp) đưa thân listener sang worker thread:

~~~java
// Minh họa cần bean và executor cấu hình đầy đủ.
@Async("notificationExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.enqueue(event.orderId());
}
~~~

Điều thay đổi:

- Publisher thường **không chờ handler xử lý hoàn tất**.
- Một exception xảy ra trong worker **không tự truyền về** caller của `publishEvent`. Với method `void`, cần `AsyncUncaughtExceptionHandler` hoặc monitoring riêng.
- Thread-bound context như request attributes, security, MDC/trace hay imperative transaction **không tự được truyền đầy đủ**.
- Việc publish có thể trả về trước khi worker thực thi, nên có race với transaction commit và database visibility.
- Một pool local không phải durable queue; process crash/restart có thể làm mất task pending.

Vì vậy `@Async` có thể **giảm ảnh hưởng độ trễ** giữa các listener, nhưng không tự tạo failure isolation hoàn toàn, exactly-once hay durability. Executor có thể hết capacity và reject task; tác vụ có thể lỗi; thread pool có thể bị nghẽn.

Nếu một callback phải chờ order commit rồi mới xử lý, dùng transaction-bound listener hoặc outbox thay vì `@Async @EventListener` trực tiếp.

## 10. Mỗi listener nên chọn transaction boundary đúng

Một service có thể publish event khi còn trong transaction `T1`:

~~~text
BEGIN T1
    INSERT orders(...)
    publishEvent(OrderPlaced)
    ...
COMMIT / ROLLBACK T1
~~~

Ba `@EventListener` thông thường chạy đồng bộ ngay khi publish, **trước khi biết T1 chắc chắn commit**. Khi một listener gửi email hoặc gọi dịch vụ ngoài ngay tại thời điểm này, T1 vẫn có thể rollback sau đó.

Nếu yêu cầu phản ứng **chỉ sau commit**:

~~~java
// Đoạn minh họa cần Spring-managed bean và transaction thực.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    notificationService.enqueue(event.orderId());
}
~~~

Điểm cần nhớ:

1. `@TransactionalEventListener` mặc định gắn phase `AFTER_COMMIT`, có thể khai báo tường minh cho dễ hiểu.
2. Nếu không có transaction phù hợp, mặc định `fallbackExecution=false`, callback **không chạy**.
3. Khi transaction rollback, listener `AFTER_COMMIT` không chạy. Cần phân biệt `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
4. Một exception trong callback hậu commit **không thể đảo ngược commit T1**. Theo Spring imperative tiêu chuẩn, exception từ `afterCompletion` thường được ghi log, không truyền ngược cho caller.
5. Listener muốn ghi DB sau commit nên mở transaction mới phù hợp (ví dụ một service riêng `@Transactional(propagation=REQUIRES_NEW)` khi đúng use case), không mặc định tái dùng transaction T1 đang cleanup.
6. Reactive transaction dùng Reactor Context; nếu cần, dùng `TransactionalEventPublisher` đúng cơ chế reactive.
7. Bắt đầu xử lý sau commit **không có nghĩa không thể mất**. Process có thể chết giữa commit và callback/enqueue.

**Đa listener và transaction không nhất thiết cùng một đơn vị atomic:** nếu audit yêu cầu cùng T1 nhưng notification chỉ sau T1, hai listener này có **hợp đồng nhất quán khác nhau**. Hãy thiết kế/kiểm thử theo từng công việc, không coi mọi listener “bắt một event” đều phải có cùng phase.

## 11. Nếu event quan trọng, cần outbox và idempotency

Spring application event nội bộ không phải durable message queue. Một use case commit order rồi dùng after-commit listener để enqueue trong RAM vẫn có khoảng trống:

~~~text
BEGIN T1
  insert order
COMMIT T1
    |
    +--- process crash ngay trước khi listener enqueue
             -> order đã có
             -> công việc phụ trợ có thể mất
~~~

Với tác vụ **không được bỏ sót**, dùng một cơ chế như **transactional outbox**:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(event_id, event_type, aggregate_id, payload)
COMMIT T1

Outbox worker:
  claim pending rows
  publish to broker / invoke consumer
  retry with backoff on transient failure
  record success/ACK
  DLQ/alert for poison messages
~~~

Đây là mô hình kiến trúc, không phải SQL production copy-paste. Hai lần ghi domain + outbox phải cùng transaction, trong khi worker gửi ra bên ngoài có thể thất bại hoặc retry.

Khi một event có ba consumers, mỗi consumer có thể cần **trạng thái xử lý riêng**, ví dụ unique key `(consumer_name, event_id)`. Việc audit đã xử lý không chứng minh loyalty cũng đã xử lý; cũng không nên mark event toàn cục DONE nếu ba công việc bắt buộc chưa hoàn tất theo contract.

### Idempotency theo từng listener

~~~text
OrderPlaced eventId=E1
    |
    +--> AuditConsumer       processed E1: yes
    +--> LoyaltyConsumer     processed E1: yes
    +--> NotificationConsumer processed E1: no -> retry
~~~

Khi delivery lại E1, Audit/Loyalty có thể bỏ qua vì đã xử lý E1; Notification xử lý riêng. Đây là **at-least-once + idempotency**, không phải bảo đảm exactly-once trên mọi hệ thống.

**Không dựa vào `eventId` mới tạo trong mỗi retry** nếu đó vẫn là cùng một business event. Cần giữ identity ổn định xuyên retry. Khi gửi email hoặc gọi API ngoài, deduplication phải xét hợp đồng của đích; timeout có thể xảy ra sau khi đích đã thực hiện thành công.

## 12. Quan sát vận hành khi một event có nhiều listener

Không nên chỉ theo dõi “publisher gọi thành công” rồi suy rằng ba handler đều thành công. Nên có số liệu cho từng giai đoạn:

| Metric logic | Ý nghĩa |
| --- | --- |
| `event.publish.attempts` | Số lần ứng dụng thử publish |
| `event.listener.invocations` | Số lần từng listener thật sự được gọi |
| `event.listener.results{listener,outcome}` | Số lần listener hoàn thành thành công/thất bại |
| `event.listener.duration` | Thời lượng từng handler |
| `event.retry.total` | Lần retry độc lập cho từng consumer |
| `event.pending.count` | Công việc đang chờ/outbox backlog |
| `event.pending.oldest.age` | Độ trễ của công việc chưa xử lý |

Các tên trên là **đề xuất instrument bằng Micrometer**, không phải mặc định Spring tự tạo mọi metric đó.

Ví dụ một event tới ba listener:

~~~text
publish attempts = 1
audit invocations = 1
loyalty invocations = 1
notification invocations = 1
~~~

Không cộng thành “3 events đã phát”. Nếu notification lỗi, metric xử lý có thể là `notification error=1` dù `publish attempts=1`. Các listener async có thể hoàn tất về sau, vì thế dùng correlation/event ID trong structured logs và traces để liên kết các bước.

**Tránh high-cardinality metric tags:** `eventId`, `orderId`, `correlationId`, `userId` không nên thành label thay đổi theo mỗi event; dùng chúng trong logging/tracing có quyền phù hợp. Tag `listener=order_audit`, `event_type=order_placed` và `outcome=success/error` là ví dụ giá trị hữu hạn.

## 13. Khi nào nên và không nên dùng mẫu này?

### Nên dùng

- Một business fact có nhiều phản ứng hậu kỳ độc lập: audit, cache invalidation, metrics, notification.
- Phần lớn listener có thể được thêm/bỏ mà không đổi mục tiêu chính của use case.
- Có hợp đồng rõ ràng về khi nào event được công bố, dữ liệu trong payload và cách xử lý lỗi.
- Nếu cần độ bền, có bridge/outbox phù hợp thay vì nhầm local application events với broker.

### Cân nhắc mô hình khác

- Các bước A → B → C **bắt buộc theo thứ tự** hoặc cần kết quả của nhau.
- Tất cả bước phải commit atomically như một transaction.
- Use case cần trả về kết quả từ các handler để quyết định HTTP response.
- Cần workflow phân tán có retry, compensation hoặc saga state, vượt khả năng local event dispatcher.
- Mỗi listener phải có quyền truy cập rất khác nhau: có thể nên tách integration event hợp đồng riêng, không broadcast DTO chứa dữ liệu nhạy cảm.

Đừng chọn event-driven fan-out chỉ để tránh vài lời gọi method trực tiếp. Chọn nó khi việc **giảm phụ thuộc và quản lý side effects độc lập** thực sự có giá trị.

## 14. Các lỗi phổ biến và cách sửa

**Lỗi 1 — “Ba listener tức ba event.”** Một publication có thể kích hoạt ba handler. Phân biệt publication count với invocation count.

**Lỗi 2 — Listener gọi lẫn nhau.** Nếu handler B cần kết quả A, dùng một orchestrator/workflow rõ thay vì ẩn dependency giữa các event subscribers.

**Lỗi 3 — Cho rằng listener không lỗi lẫn nhau.** Multicaster sync mặc định có thể dừng khi listener ném exception; test policy của `ErrorHandler`, `@Async` và transaction.

**Lỗi 4 — Dựa vào thứ tự đăng ký bean.** Không dùng vị trí `@Bean`, scan order hoặc tên class để yêu cầu invocation order. Nếu cần, dùng `@Order` nhưng không suy ra completion order của async.

**Lỗi 5 — Phát event quá sớm.** `@Async @EventListener` có thể đọc DB trước commit, hoặc gửi email cho transaction sau đó rollback. Cân nhắc `AFTER_COMMIT` hoặc outbox.

**Lỗi 6 — Dùng `AFTER_COMMIT` như durable queue.** Nó chỉ giải quyết thời điểm callback, không giải quyết crash window. Tác vụ bắt buộc cần kênh bền vững.

**Lỗi 7 — Dùng entity/request chứa secret trong payload.** Event nên immutable và tối thiểu; không cho nhiều listener đọc raw credential hoặc `HttpServletRequest`.

**Lỗi 8 — Mọi listener chia sẻ một mutable object làm state.** Sẽ phát sinh race, order dependency và khó kiểm thử. Truyền event immutable và để mỗi consumer sở hữu projection của mình.

**Lỗi 9 — Không quản lý duplicate/retry.** Với broker/outbox, một event có thể được gửi lại; từng consumer phải idempotent theo event ID và use case.

**Lỗi 10 — Test bằng cách gọi ba method thủ công.** Nó không chứng minh annotation registration/type routing. Dùng Spring `ApplicationContext` thật cho integration test fan-out.

**Lỗi 11 — Không phân biệt listener sync và async.** `publishEvent` trả về có thể chỉ có nghĩa task đã được submit. Kiểm tra completion bằng signal/Future, tránh `Thread.sleep()`.

**Lỗi 12 — Đăng ký cùng một listener hai lần.** Khi kết hợp `@Bean` và `@ComponentScan` không chủ ý hoặc thêm cả `ApplicationListener` adapter riêng, có thể xử lý event lặp. Xác định một cơ chế registration cho từng handler và kiểm tra invocation count.

## 15. Checklist triển khai và kiểm thử

- [ ] Event là fact nghiệp vụ rõ ràng, payload tối thiểu, immutable.
- [ ] Một publisher gọi `publishEvent` tại đúng business/transaction boundary.
- [ ] Mỗi listener có một trách nhiệm rõ, không gọi listener khác để tạo dependency ẩn.
- [ ] Chọn sync/async/transaction-bound cho từng công việc dựa trên semantics chứ không theo thói quen.
- [ ] Có chính sách lỗi: propagate, suppress + alert, retry hoặc outbox tùy use case.
- [ ] Không coi `@Order` là guarantee về commit/completion.
- [ ] Nếu cần after-commit, test có transaction thật; ngoài transaction mặc định không chạy.
- [ ] Nếu cần durable delivery, outbox/broker có ACK, retry và idempotency theo consumer.
- [ ] Có integration test publish **một event** và assert từng listener đã xử lý đúng một lần.
- [ ] Có test event type không liên quan không kích hoạt handler.
- [ ] Có test listener ném lỗi theo cấu hình multicaster thực tế.
- [ ] Với async, dùng latch/queue có timeout thay vì sleep.
- [ ] Metrics đếm publication riêng với invocation/completion từng listener.
- [ ] Tránh secret, PII không cần thiết và identifier cardinatility cao trong payload/log tags.
- [ ] Quan sát behavior của nested events và parent/child contexts nếu topology có sử dụng.

### Ghi nhớ

~~~text
Một lần publishEvent(OrderPlaced)
             |
             +--> AuditListener
             +--> LoyaltyListener
             +--> NotificationListener

Ba handler độc lập về trách nhiệm
KHÔNG đồng nghĩa ba publication.

Default multicaster: đồng bộ trên thread caller.
Lỗi một listener có thể chặn các listener sau.

@Order      : ưu tiên gọi, không bảo đảm async completion.
@Async      : chuyển thread, không bảo đảm delivery bền vững.
AFTER_COMMIT: chỉ xử lý khi commit, không cứu crash window.
Outbox      : khi cần khôi phục và retry đáng tin cậy.

Độc lập thực sự = ranh giới trách nhiệm rõ
                 + hợp đồng nhất quán, lỗi, retry rõ.
~~~

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events, asynchronous và ordering](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
