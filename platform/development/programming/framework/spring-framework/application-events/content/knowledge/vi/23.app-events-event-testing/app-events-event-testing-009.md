# Kiểm thử payload và thuộc tính trong Spring Framework Application Events

## 1. Mục tiêu học tập

Trong ứng dụng Spring, việc một listener được gọi **không đủ** để kết luận một event đúng. Chẳng hạn `OrderPlaced` đã được publish một lần nhưng mang sai `orderId`, sai `correlationId`, thời điểm xảy ra không đúng hoặc danh sách sản phẩm bị thay đổi sau lúc publish. Một bài kiểm thử tốt cần xem xét **nội dung payload, thuộc tính/metadata và hợp đồng phân phối** của event.

Sau bài này, bạn có thể:

1. Phân biệt kiểm thử **event được phát** với kiểm thử **listener xử lý**.
2. Xác minh đúng **loại event, số lần phát, giá trị component, metadata, timestamp và quan hệ định danh**.
3. Sử dụng `@RecordApplicationEvents` và `ApplicationEvents.stream(Class<T>)` trong Spring TestContext với JUnit 5.
4. Test payload POJO/record được công bố bằng `publishEvent(Object)` và event truyền thống kế thừa `ApplicationEvent`.
5. Kiểm tra **snapshot bất biến**, validation, giá trị null, enum, collection và tình huống cùng eventId được phát lặp.
6. Tránh test chập chờn khi listener bất đồng bộ hoặc khi event bị ràng buộc với transaction.
7. Biết khi nào cần kiểm thử ở lớp domain, ở hạ tầng Spring hay ở consumer thực hiện tác dụng phụ.

Chủ đề thuộc nhóm **Kiểm thử event** trong Spring Framework Application Events. Tập trung vào **payload và thuộc tính** chứ không chỉ vào việc kiểm tra callback có chạy.

## 2. Payload và thuộc tính cần kiểm thử là gì?

**Payload** là dữ liệu mà event chuyển tới người tiêu thụ, ví dụ bản ghi:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId,
        String causationId,
        Instant occurredAt,
        int schemaVersion,
        List<OrderLine> lines
) {}
```

Đây là phác thảo kiểu dữ liệu; constructor validation và defensive copy xuất hiện trong ví dụ đầy đủ ở mục 6.

**Thuộc tính** có thể thuộc ba tầng:

| Tầng | Ví dụ | Phép kiểm thử phù hợp |
| --- | --- | --- |
| Dữ liệu nghiệp vụ | `orderId`, `sku`, `quantity`, `unitPrice` | Giá trị khớp đầu vào và quy tắc nghiệp vụ |
| Metadata trong payload | `eventId`, `correlationId`, `causationId`, `occurredAt`, `schemaVersion` | Định danh chính xác, giữ correlation, thời gian cố định trong fixture, version hợp lệ |
| Thuộc tính framework | Kiểu event, `ApplicationEvent.getSource()`, `getTimestamp()`, `PayloadApplicationEvent.getPayload()` | Spring phân phối đúng kiểu và wrapper có hợp đồng phù hợp |

**Không nhầm** `occurredAt` của domain event với `ApplicationEvent.getTimestamp()`. Trường `occurredAt` do ứng dụng tạo để mô tả **thời điểm nghiệp vụ**, còn timestamp của `ApplicationEvent` được framework gán khi instance event được khởi tạo. Chúng có thể không giống nhau và không nên bị so sánh bằng một con số hard-code.

### Cần xác minh những câu hỏi nào?

- **Loại:** đã phát `OrderPlaced` chứ không phải `OrderCancelled`?
- **Số lượng:** đúng một event hay nhiều event? Có publish lặp ngoài ý muốn?
- **Định danh:** `eventId` đúng occurrence, `orderId` đúng aggregate?
- **Nhân quả:** `correlationId` giữ đúng workflow, `causationId` trỏ event cha nếu có?
- **Thời điểm:** `occurredAt` có đến từ nghiệp vụ hay bị tạo lại trong listener?
- **Nội dung:** chi tiết số lượng, giá tiền, enum trạng thái, tập phần tử đúng chưa?
- **Tính bất biến:** caller sửa list sau publish có làm payload đã phát thay đổi?
- **Validation:** dữ liệu sai có bị từ chối trước khi event được công bố?
- **Hợp đồng framework:** listener nhận đúng POJO record? Với subclass `ApplicationEvent`, source có phải object mong muốn?

## 3. Phân biệt ba mức kiểm thử

| Mức | Đối tượng test | Bằng chứng thu được | Không tự chứng minh |
| --- | --- | --- | --- |
| Unit test record/constructor | Bất biến, validation, defensive copy | Payload tự thân hợp lệ | Spring thực sự publish event |
| TestContext integration test | Service gọi `ApplicationEventPublisher`; `ApplicationEvents` ghi nhận | Spring đã phát đúng loại và đúng dữ liệu | External API, database hoặc async job chắc chắn thành công |
| Consumer/flow integration test | Listener thật, transaction, queue, side effect | Handler thực hiện tác dụng phụ theo hợp đồng | Exactly-once end-to-end hoặc delivery bền vững nếu chưa có thiết kế riêng |

Một phản ví dụ test quá yếu:

```java
@Test
void weakTest() {
    OrderPlaced event = buildFixture();
    listener.onOrderPlaced(event);
    // Test này chỉ chứng minh phương thức Java được gọi trực tiếp,
    // không chứng minh service đã publish đúng event qua Spring.
}
```

Đoạn trên là **mã mô phỏng**, cần fixture/listener cụ thể để chạy. Muốn kiểm tra hệ thống publish event, phải gọi **hành vi của service phát event** và quan sát event từ application context, thay vì tự dựng rồi gọi thẳng callback.

## 4. Công cụ Spring TestContext: @RecordApplicationEvents

Spring Framework từ phiên bản 5.3.3 có tính năng ghi nhận các application events trong quá trình test:

- `@SpringJUnitConfig`: annotation kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`, cho phép chạy JUnit Jupiter cùng Spring TestContext.
- `@RecordApplicationEvents`: bật ghi nhận event cho mỗi test method.
- `ApplicationEvents`: API đọc những event đã được ghi nhận, có `stream()`, `stream(Class<T>)` và `clear()`.
- `ApplicationEventsTestExecutionListener`: thành phần TestContext hỗ trợ ghi nhận; được đăng ký mặc định khi dùng cấu hình listener chuẩn.

Ví dụ mẫu:

```java
@SpringJUnitConfig(TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    OrderService service;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        events.clear(); // Chỉ xét event kể từ thời điểm này.
        service.placeOrder();

        assertEquals(1,
                events.stream(OrderPlaced.class).count());
    }
}
```

Đây là **trích đoạn minh họa** vì cần `TestConfig`, `OrderService` và `OrderPlaced` tương ứng. Ví dụ chạy được ở mục 6 cung cấp đầy đủ cấu hình và class.

### Vì sao cần ApplicationEvents.stream(Class<T>)?

`events.stream()` trả về stream các `ApplicationEvent` theo lớp framework, có thể bao gồm các sự kiện startup/context hoặc các loại khác trong test. Còn `events.stream(OrderPlaced.class)` lọc **event hoặc payload có đúng kiểu quan tâm**, giúp bạn kiểm tra các record/POJO được phát qua `publishEvent(Object)`.

Ví dụ:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("ORD-42", placed.get(0).orderId());
```

Một bài test payload phải **lấy event thực tế đã được record** để assert giá trị, thay vì chỉ gọi `count()`. Đếm đúng một nhưng event chứa sai `orderId` hoặc tiền vẫn là lỗi.

### Không dùng sai phạm vi lifecycle

Theo Spring TestContext, `ApplicationEvents` gắn với vòng đời **test method hiện tại**. Với JUnit Jupiter, cách đơn giản là nhận `ApplicationEvents` qua tham số `@Test` hoặc `@BeforeEach`/`@AfterEach`. Có thể inject field trong test; **không inject ApplicationEvents vào constructor của test class hoặc vào singleton service trong application context để giữ vĩnh viễn**.

`events.clear()` là thao tác hữu ích trước phần hành vi cần test khi test có setup event; nó xóa những event đã record **trong instance của test hiện tại**, không xóa sự kiện trên message broker và không can thiệp dữ liệu nghiệp vụ.

## 5. Lập ma trận test trước khi viết code

Với event `OrderPlaced`, ma trận tối thiểu:

| Trường hợp | Hành động | Kỳ vọng |
| --- | --- | --- |
| Publish hợp lệ | Gọi `OrderService.place(...)` | Có đúng một `OrderPlaced` |
| Metadata | Publish với ID và timestamp xác định | Các field khớp chính xác |
| Giá trị lồng nhau | Có một dòng `SKU-7`, số lượng 2, giá 75.00 | List chứa đúng line, tổng nếu tính là 150.00 |
| Snapshot | Sửa list nguồn sau khi phát | Payload đã record không thay đổi |
| Chống mutation | Gọi `event.lines().clear()` | Bị từ chối bằng `UnsupportedOperationException` |
| Loại event | Publish `OrderCancelled` | `stream(OrderPlaced.class)` trống |
| Validation | Gửi `orderId` rỗng | Constructor ném lỗi, không publish `OrderPlaced` |
| Duplicate occurrence | Publish hai lần cùng `eventId` | Có hai lần phát; Spring không tự dedupe |
| Framework source | Publish `OrderFlaggedEvent extends ApplicationEvent` | `getSource()` là object được chọn khi tạo event |
| Timestamp framework | Kiểm tra `getTimestamp()` | Giá trị hợp lệ tại thời điểm tạo, không hard-code epoch mili-giây |

Ở các nhóm event khác, ma trận có thể bổ sung status enum, aggregate version, multi-tenant ID, currency, schema version, collection rỗng/null, causation của event dẫn xuất, và các bất biến đặc thù.

## 6. Ví dụ hoàn chỉnh Java 17, Spring Framework 6.2 và JUnit 5

Dự án này sử dụng **Spring Framework thuần**, không cần Spring Boot, web server hoặc database.

Ứng dụng mẫu có:

1. Record `OrderLine` và `OrderPlaced`, có validation và `List.copyOf`.
2. Record `OrderCancelled` để test phân biệt loại event.
3. Class `OrderFlaggedEvent` kế thừa `ApplicationEvent` để kiểm tra `getSource()` và `getTimestamp()`.
4. `OrderService` phát event thông qua `ApplicationEventPublisher`.
5. `RecordingListener` nhận `OrderPlaced` qua `@EventListener` để xác nhận Spring đã chuyển record payload đến listener.
6. Bộ JUnit 5 sử dụng `@SpringJUnitConfig` + `@RecordApplicationEvents`, kiểm tra **năm tình huống**.

Ví dụ chọn `occurredAt` cố định, chỉ dùng một context cấu hình qua `@Bean` và dùng multicaster **đồng bộ mặc định**. Điều này giúp kết quả có tính xác định mà không cần `sleep`.

### 6.1. Cấu trúc thư mục

```text
spring-event-payload-test/
├── pom.xml
└── src/
    ├── main/java/example/OrderEventModule.java
    └── test/java/example/OrderPayloadEventsTest.java
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-event-payload-test</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.3</version>
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
        </plugins>
    </build>
</project>
```

### 6.3. Tệp src/main/java/example/OrderEventModule.java

```java
package example;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class OrderEventModule {

    private OrderEventModule() {}

    public record OrderLine(
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be negative");
            }
        }
    }

    // Payload POJO/record, không extends ApplicationEvent.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String correlationId,
            String causationId,
            Instant occurredAt,
            int schemaVersion,
            List<OrderLine> lines) {

        public OrderPlaced {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(correlationId, "correlationId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank()
                    || orderId.isBlank()
                    || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "required ID is blank");
            }
            if (schemaVersion < 1) {
                throw new IllegalArgumentException(
                        "schemaVersion must be positive");
            }

            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "order must have at least one line");
            }
        }
    }

    public record OrderCancelled(
            String eventId,
            String orderId,
            String reason) {}

    // Kiểu sự kiện Spring cổ điển để test getSource/timestamp.
    public static final class OrderFlaggedEvent
            extends ApplicationEvent {
        private final String orderId;

        public OrderFlaggedEvent(Object source, String orderId) {
            super(source);
            this.orderId =
                    Objects.requireNonNull(orderId, "orderId");
        }

        public String orderId() {
            return orderId;
        }
    }

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(
                String eventId,
                String orderId,
                String correlationId,
                String causationId,
                Instant occurredAt,
                int schemaVersion,
                List<OrderLine> lines) {

            // Validate và tạo snapshot trước khi publish.
            OrderPlaced event = new OrderPlaced(
                    eventId, orderId, correlationId,
                    causationId, occurredAt, schemaVersion, lines);
            publisher.publishEvent(event);
        }

        public void cancel(String eventId,
                           String orderId,
                           String reason) {
            publisher.publishEvent(
                    new OrderCancelled(eventId, orderId, reason));
        }

        public void flag(String orderId) {
            // Chủ động chọn service làm source object.
            publisher.publishEvent(
                    new OrderFlaggedEvent(this, orderId));
        }
    }

    public static class RecordingListener {
        private final CopyOnWriteArrayList<OrderPlaced> received =
                new CopyOnWriteArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
        }

        public List<OrderPlaced> received() {
            return List.copyOf(received);
        }

        public void clear() {
            received.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public RecordingListener recordingListener() {
            return new RecordingListener();
        }
    }
}
```

**Giải thích phần chính:**

- `OrderPlaced` và `OrderLine` là record Java 17. Compact constructor kiểm tra ID, số lượng, giá và chụp snapshot `List.copyOf(lines)`.
- `OrderService.place(...)` tạo event **trước** rồi mới publish. Nếu constructor báo lỗi, việc publish không diễn ra.
- Spring hỗ trợ `publishEvent(Object)`. Khi nhận record không kế thừa `ApplicationEvent`, hạ tầng có thể bọc record thành `PayloadApplicationEvent<OrderPlaced>`; listener `@EventListener` vẫn nhận **trực tiếp OrderPlaced**.
- `OrderFlaggedEvent` dùng `super(source)` để kiểm tra API của một `ApplicationEvent` truyền thống. Đây là cơ chế khác với metadata `correlationId` nằm trong record.
- `RecordingListener` là bean thật để xác minh đường phân phối tới listener. Vì test chạy đồng bộ mặc định, nó ghi nhận event trước khi `place(...)` trả về. `CopyOnWriteArrayList` chỉ giúp recorder an toàn nếu sau này cần đọc từ thread khác; chưa có cơ chế chờ cho async.
- Tất cả bean được khai báo qua `@Bean` trong `Config`, không phụ thuộc component scan hay một Spring Boot application ngoài dự án.

### 6.4. Tệp src/test/java/example/OrderPayloadEventsTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.OrderEventModule.OrderCancelled;
import example.OrderEventModule.OrderFlaggedEvent;
import example.OrderEventModule.OrderLine;
import example.OrderEventModule.OrderPlaced;

@SpringJUnitConfig(OrderEventModule.Config.class)
@RecordApplicationEvents
class OrderPayloadEventsTest {

    private static final Instant OCCURRED_AT =
            Instant.parse("2026-11-01T08:00:00Z");

    @Autowired
    OrderEventModule.OrderService service;

    @Autowired
    OrderEventModule.RecordingListener recorder;

    @BeforeEach
    void resetRecorder() {
        // Bean là singleton và TestContext có thể cache context.
        recorder.clear();
    }

    private static OrderLine sampleLine() {
        return new OrderLine(
                "SKU-7", 2, new BigDecimal("75.00"));
    }

    // Test 1: cả kiểu, payload, thuộc tính và snapshot.
    @Test
    void recordsExactPayloadAndProperties(ApplicationEvents events) {
        events.clear();

        List<OrderLine> draft =
                new ArrayList<>(List.of(sampleLine()));

        service.place(
                "evt-100", "ORD-42", "flow-7", null,
                OCCURRED_AT, 1, draft);

        List<OrderPlaced> published =
                events.stream(OrderPlaced.class).toList();
        assertEquals(1, published.size());

        OrderPlaced actual = published.get(0);
        assertAll(
                () -> assertEquals("evt-100", actual.eventId()),
                () -> assertEquals("ORD-42", actual.orderId()),
                () -> assertEquals("flow-7", actual.correlationId()),
                () -> assertNull(actual.causationId()),
                () -> assertEquals(OCCURRED_AT, actual.occurredAt()),
                () -> assertEquals(1, actual.schemaVersion()),
                () -> assertEquals(
                        List.of(sampleLine()), actual.lines())
        );

        // Sửa input sau publish không sửa snapshot đã phát.
        draft.clear();
        assertEquals(1, actual.lines().size());

        // Bên nhận không thể sửa cấu trúc list trong record.
        assertThrows(UnsupportedOperationException.class,
                () -> actual.lines().clear());

        // Chứng minh Spring đưa đúng payload tới listener.
        assertEquals(1, recorder.received().size());
        assertSame(actual, recorder.received().get(0));
    }

    // Test 2: loại khác không bị nhầm thành OrderPlaced.
    @Test
    void filtersByEventType(ApplicationEvents events) {
        events.clear();

        service.cancel("evt-cancel", "ORD-42", "requested");

        assertEquals(0,
                events.stream(OrderPlaced.class).count());

        List<OrderCancelled> cancelled =
                events.stream(OrderCancelled.class).toList();
        assertEquals(1, cancelled.size());
        assertEquals("ORD-42", cancelled.get(0).orderId());
        assertEquals("requested", cancelled.get(0).reason());
        assertTrue(recorder.received().isEmpty());
    }

    // Test 3: validation lỗi phải ngăn publish.
    @Test
    void rejectsInvalidPayloadBeforePublishing(
            ApplicationEvents events) {
        events.clear();

        assertThrows(IllegalArgumentException.class, () ->
                service.place(
                        "evt-bad", "  ", "flow-7", null,
                        OCCURRED_AT, 1, List.of(sampleLine())));

        assertEquals(0,
                events.stream(OrderPlaced.class).count());
        assertTrue(recorder.received().isEmpty());
    }

    // Test 4: Spring event bus không tự dedupe eventId.
    @Test
    void duplicateEventIdsAreNotAutomaticallyDeduplicated(
            ApplicationEvents events) {
        events.clear();

        for (int i = 0; i < 2; i++) {
            service.place(
                    "evt-same", "ORD-42", "flow-7", null,
                    OCCURRED_AT, 1, List.of(sampleLine()));
        }

        List<OrderPlaced> published =
                events.stream(OrderPlaced.class).toList();

        assertEquals(2, published.size());
        assertEquals(
                List.of("evt-same", "evt-same"),
                published.stream().map(OrderPlaced::eventId).toList());
        assertEquals(2, recorder.received().size());
    }

    // Test 5: thuộc tính lớp ApplicationEvent truyền thống.
    @Test
    void legacyEventContainsExpectedSourceAndTimestamp(
            ApplicationEvents events) {
        events.clear();

        service.flag("ORD-42");

        List<OrderFlaggedEvent> flags =
                events.stream(OrderFlaggedEvent.class).toList();
        assertEquals(1, flags.size());

        OrderFlaggedEvent event = flags.get(0);
        assertSame(service, event.getSource());
        assertEquals("ORD-42", event.orderId());
        assertTrue(event.getTimestamp() > 0L);
    }
}
```

### 6.5. Chạy kiểm thử

Trong thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
```

Bộ test có **5 phương thức `@Test`**. Trong điều kiện các dependency được tải đầy đủ và kiểm thử thành công, Maven Surefire báo kết quả tương đương:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **những trường kết quả cần kiểm tra**, không phải khẳng định nguyên văn toàn bộ stdout: định dạng log, thứ tự dòng, thông báo dependency/plugin và thời gian chạy có thể thay đổi. Với `mvn -q test`, output có thể được giảm bớt; hãy xem exit code hoặc file báo cáo `target/surefire-reports/example.OrderPayloadEventsTest.txt`.

**Quan trọng:** mã là bộ test thật, không phải demo có `main()`. Lệnh đúng là `mvn test`, không phải `mvn exec:java`. Kết quả đáng tin là **tất cả assertion đều PASS**, không phải một thông điệp console do ví dụ tự in.

### 6.6. Phân tích từng test

**Test 1 — recordsExactPayloadAndProperties**

- Gọi service thật, không gọi listener trực tiếp.
- Lấy `OrderPlaced` từ `events.stream(OrderPlaced.class)` để xác minh đây chính là event Spring đã ghi nhận.
- Kiểm tra đầy đủ `eventId`, `orderId`, `correlationId`, `causationId`, `occurredAt`, `schemaVersion` và `lines`.
- Kiểm tra `List.copyOf` tạo snapshot độc lập với `draft` mutable.
- Kiểm tra List của payload không bị sửa cấu trúc từ bên nhận.
- Kiểm tra `RecordingListener` nhận đúng cùng instance payload trong đường dispatch đồng bộ của demo.

**Test 2 — filtersByEventType**

- Một `OrderCancelled` được phát không được tính là `OrderPlaced`.
- Test xác minh thêm `reason`, vì một event có đúng loại mà sai lý do vẫn không đạt.
- Không so tổng event bất kỳ bằng `events.stream().count()` vì test context có thể có event khác.

**Test 3 — rejectsInvalidPayloadBeforePublishing**

- `orderId` chỉ có dấu cách là không hợp lệ.
- Constructor `OrderPlaced` ném `IllegalArgumentException` trước `publisher.publishEvent`.
- Vì vậy không có `OrderPlaced` nào được ghi nhận; kiểm tra cả bộ recorder.

**Test 4 — duplicateEventIdsAreNotAutomaticallyDeduplicated**

- Hai lần publish cùng `eventId` tạo ra hai lần event được ghi nhận.
- Đây là **hành vi framework**, không phải lỗi test.
- Nếu nghiệp vụ không được phép tạo cùng tác dụng phụ hai lần, consumer phải có idempotency key và xử lý trùng riêng.

**Test 5 — legacyEventContainsExpectedSourceAndTimestamp**

- Class `OrderFlaggedEvent` kế thừa `ApplicationEvent`; constructor gán source bằng `this` của `OrderService`.
- Assert `getSource()` bằng **identity** (`assertSame`), không đoán source từ tên lớp hoặc event payload.
- `getTimestamp()` do instance event tạo ra, nên không hard-code epoch cụ thể; test chỉ chứng minh timestamp được khởi tạo. Nếu nghiệp vụ cần timestamp xác định, tự lưu `occurredAt` trong payload và truyền `Clock`/`Instant` kiểm soát trong test.

## 7. Tại sao phải phân biệt event POJO và ApplicationEvent?

Spring hỗ trợ hai kiểu phổ biến.

### 7.1. Record hoặc POJO làm payload

```java
public record OrderPlaced(String orderId) {}

publisher.publishEvent(new OrderPlaced("ORD-42"));
```

Đây là snippet tích hợp. Spring bọc object không kế thừa `ApplicationEvent` thành `PayloadApplicationEvent<T>` khi phân phối. `@EventListener` có thể nhận trực tiếp `OrderPlaced`. Trong Spring TestContext, `ApplicationEvents.stream(OrderPlaced.class)` có thể trả về chính các **payload** đã phát.

Đừng assert rằng record có `getSource()` hay `getTimestamp()` — record `OrderPlaced` đơn giản không kế thừa `ApplicationEvent`. Nếu muốn hai thông tin đó là một phần hợp đồng nghiệp vụ, hãy khai báo component như `sourceSystem`/`occurredAt` riêng trong record.

### 7.2. Subclass ApplicationEvent

```java
public final class PaymentCapturedEvent extends ApplicationEvent {
    private final String paymentId;

    public PaymentCapturedEvent(Object source, String paymentId) {
        super(source);
        this.paymentId = paymentId;
    }

    public String paymentId() {
        return paymentId;
    }
}
```

Đây là class minh họa cần import `ApplicationEvent`; chương trình đầy đủ dùng `OrderFlaggedEvent` tương tự. Ở cách này, `getSource()` và `getTimestamp()` là API của `ApplicationEvent`.

**Cảnh báo:** `getSource()` chỉ chứa object được truyền cho constructor, không có nghĩa tự động là `causationId`, caller service đang chạy, người dùng hiện tại, hay nơi lưu dữ liệu nghiệp vụ. Đừng suy luận sai ý nghĩa của thuộc tính framework.

## 8. Kiểm thử thuộc tính thời gian đúng cách

Thời điểm là thuộc tính thường gây flaky test.

### Phản ví dụ

```java
assertEquals(
        Instant.now(),
        event.occurredAt());
```

Hai lần gọi đồng hồ không thể chắc chắn trả cùng nanosecond. Điều này **không đúng** nếu `occurredAt` được tạo trước khi callback chạy hoặc được lấy từ transaction khác.

### Cách 1 — fixture với Instant cố định

Trong ví dụ đầy đủ:

```java
private static final Instant OCCURRED_AT =
        Instant.parse("2026-11-01T08:00:00Z");
```

Service nhận giá trị này rồi đưa vào event. Test dùng `assertEquals(OCCURRED_AT, actual.occurredAt())`, nên kết quả xác định.

### Cách 2 — inject Clock khi service tự tạo timestamp

Nếu domain service phải tự lấy thời điểm, inject `java.time.Clock`:

```java
public class EventFactory {
    private final Clock clock;

    public EventFactory(Clock clock) {
        this.clock = clock;
    }

    public Instant timestamp() {
        return Instant.now(clock);
    }
}
```

Đây là snippet minh họa. Trong test có thể cung cấp `Clock.fixed(Instant.parse("2026-11-01T08:00:00Z"), ZoneOffset.UTC)` để kiểm tra giá trị đúng 100%, thay vì so sánh hai `Instant.now()`.

### Cách 3 — timestamp của ApplicationEvent

Với `ApplicationEvent.getTimestamp()`, test có thể xác nhận nó dương hoặc nằm trong một khoảng thời gian hợp lý nếu môi trường có ràng buộc rõ. Nhưng không nên so khớp chính xác timestamp tạo tự động với đồng hồ khác được gọi sau đó. Ví dụ mục 6 dùng phép kiểm tra đơn giản `getTimestamp() > 0L`.

Nếu cần ghi lại thời gian nghiệp vụ **lâu dài và có thể replay**, dùng `occurredAt` nằm trong payload; timestamp framework không thay thế thiết kế schema nghiệp vụ.

## 9. Kiểm thử collection và dữ liệu lồng nhau

Record có field final nhưng có thể chứa `List` hoặc object mutable. Muốn test payload bất biến phải kiểm tra cả hai hướng:

1. **Caller thay đổi input:** event giữ snapshot trước đó.
2. **Consumer cố thay đổi accessor:** event không cho phép sửa trực tiếp.

`List.copyOf(...)` bảo vệ cấu trúc list, nhưng **không deep-copy phần tử mutable**. Nếu component `OrderLine` giữ entity có setter hoặc array, list immutable vẫn chứa object có thể đổi.

Với nested data, cần bổ sung test:

```java
assertEquals("SKU-7", actual.lines().get(0).sku());
assertEquals(2, actual.lines().get(0).quantity());
assertEquals(
        new BigDecimal("75.00"),
        actual.lines().get(0).unitPrice());
```

Đây là snippet chạy trong test mục 6 sau khi có biến `actual`. `BigDecimal.equals()` so sánh cả **scale**; `75.0` và `75.00` có thể bằng về giá trị toán học nhưng không `equals`. Nếu nghiệp vụ chỉ so giá trị tiền, cân nhắc chuẩn hóa scale hoặc dùng `compareTo(...) == 0`; đừng lặng lẽ đổi quy tắc equality trong test.

Với `Map.copyOf`/`Set.copyOf`, cần chú ý null và thứ tự không bảo đảm; với mảng, cần defensive copy cả constructor và accessor nếu muốn immutable. Test nên bám vào **hợp đồng dữ liệu công khai**, không assert thứ tự vòng lặp của một `HashMap`/`Set` khi không quy định.

## 10. Khi event có metadata phức tạp

Trong chuỗi event:

```text
OrderPlaced
  eventId       = evt-100
  correlationId = flow-7
  causationId   = null
          |
          v
InventoryReservationRequested
  eventId       = evt-101
  correlationId = flow-7
  causationId   = evt-100
```

Phép test event dẫn xuất nên assert:

```java
assertNotEquals(root.eventId(), derived.eventId());
assertEquals(root.correlationId(), derived.correlationId());
assertEquals(root.eventId(), derived.causationId());
```

Đây là snippet cho trường hợp có hai record `root` và `derived` phù hợp, không phải một phần chương trình chạy mục 6.

Ý nghĩa:

- `eventId` định danh một occurrence, không dùng chung giữa event mới khác nhau.
- `correlationId` nhóm các event cùng workflow, không nhất thiết là idempotency key.
- `causationId` cho biết event cha trực tiếp, không lấy từ `ApplicationEvent.getSource()`.
- `aggregateVersion` hoặc `schemaVersion` cần được kiểm tra theo chính sách version thực tế.
- `tenantId`/`sourceSystem` có thể quan trọng cho routing/kiểm toán; cần test nếu là phần hợp đồng.

Đừng chỉ assert `eventId != null`; một ID sai nhưng khác null vẫn có thể làm hệ thống không liên kết được event.

## 11. Test loại và số lượng event, tránh đếm sai

Có thể có nhiều event xuất hiện trong cùng một test context: `ContextRefreshedEvent`, `PayloadApplicationEvent`, event dẫn xuất từ listener, event quan sát riêng... Do vậy:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

thường là assertion đúng cho câu hỏi “Có chính xác một OrderPlaced không?”. Tránh:

```java
assertEquals(1, events.stream().count());
```

nếu bạn không thực sự có hợp đồng rằng toàn bộ Spring context chỉ phát một event. Test thứ hai có thể fail vì event hệ thống hợp lệ hoặc một loại event khác, chứ không phải vì chức năng đang test sai.

Cũng không nên test dựa vào vị trí `events.stream().findFirst()` của **tất cả** event. Lọc theo kiểu trước khi chọn event quan tâm.

### Kiểm tra không phát event khi validation thất bại

Một phép test tốt có cấu trúc:

```text
Arrange: dựng input không hợp lệ
Act: gọi hành vi của service
Assert: nhận đúng exception
Assert: stream(OrderPlaced.class) rỗng
Assert: listener không ghi tác dụng phụ
```

Nếu chỉ test constructor ném lỗi mà không xác minh **không có event nào publish**, vẫn còn khả năng service publish một event trước rồi mới validate ở bước khác.

### Không tự deduplicate

Spring ApplicationEventPublisher không có trách nhiệm tự bỏ event trùng theo `eventId`. Nếu cùng occurrence được publish hai lần, một listener đơn giản có thể chạy hai lần. Test duplicate có thể xác nhận điều đó, nhưng trong hệ thống nghiệp vụ cần chống trùng, hãy viết **thêm test cho consumer/idempotency**, ví dụ ràng buộc unique `(consumerName,eventId)` trong database.

## 12. Event listener bất đồng bộ cần chiến lược test khác

Nếu listener có:

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Xử lý trên worker thread khác.
}
```

đừng khẳng định listener đã hoàn thành ngay sau `service.place(...)`. `ApplicationEventPublisher.publishEvent(...)` không đợi các `@Async` listener chạy xong theo hợp đồng mặc định.

**Quan trọng về recorder:** `@RecordApplicationEvents` ghi nhận các event trong phạm vi test và có những ràng buộc thread/lifecycle của TestContext. Đối với các event phát từ worker pool, đặc biệt nếu pool thread đã được tạo sẵn hoặc không mang test context, không được mặc nhiên giả định mọi event được phát lại từ worker đều xuất hiện trong `ApplicationEvents` của test. Việc record event ban đầu và việc listener async xử lý xong là **hai câu hỏi khác nhau**.

Khi muốn assert kết quả listener async, có thể dùng listener test-specific với `CountDownLatch`, `BlockingQueue`, `CompletableFuture` hoặc một thread-safe recorder có timeout.

Mẫu kiểm tra hoàn tất:

```java
if (!latch.await(5, TimeUnit.SECONDS)) {
    fail("Async listener did not finish");
}
assertEquals("ORD-42", capturedOrderId.get());
```

Đây là snippet tích hợp; cần `CountDownLatch`, `AtomicReference`, executor được cấu hình và listener thật. Dùng timeout để test fail hữu ích khi job không hoàn thành; không dùng `Thread.sleep(100)` rồi đọc state vì dễ flaky.

### Test lỗi trong async listener

Với `@Async void`, exception trong listener không tự lan về thread publisher. Nếu test cần xác nhận lỗi, hãy kiểm tra error handler, trạng thái nghiệp vụ hoặc completion signal. Không xem `assertDoesNotThrow(service::place)` là bằng chứng listener async đã thành công.

### Multicaster dùng executor

Nếu ứng dụng cấu hình `SimpleApplicationEventMulticaster#setTaskExecutor(...)`, nhiều listener có thể được gửi đi async. Kết quả test không còn bảo đảm hoàn tất đúng thứ tự publish theo cách đồng bộ. Khi kiểm tra nhiều event, assert theo **eventId/type và tập giá trị**, đừng ép thứ tự log nếu hợp đồng không đòi hỏi.

## 13. Kiểm thử @TransactionalEventListener

Một listener `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ xử lý khi transaction phát event được commit; với `fallbackExecution=false` (mặc định), event phát ngoài transaction thường không kích hoạt listener này.

Vấn đề thường gặp trong test:

```java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class OrderTransactionTests {
    // Một test @Transactional mặc định được rollback cuối test,
    // nên listener AFTER_COMMIT có thể không chạy.
}
```

Đây là trích đoạn mô tả cơ chế, không phải chương trình chạy độc lập.

Để test hậu commit chính xác, có thể:

- Gọi service thật với transaction và **commit thật** qua `TransactionTemplate` trong test tích hợp.
- Trong test-managed transaction, dùng `TestTransaction.flagForCommit()` rồi `TestTransaction.end()` ở thời điểm có chủ đích.
- Phân biệt assertion **event được publish trước commit** với assertion **listener AFTER_COMMIT đã hoàn thành sau commit**.
- Kiểm tra cả rollback: listener `AFTER_COMMIT` không thực hiện tác dụng phụ khi transaction rollback.

### Không nhầm ghi event với xử lý hậu commit

`ApplicationEvents` có thể ghi nhận event được công bố trong transaction, nhưng listener transaction-bound chỉ chạy theo phase. Test hai mục đích bằng hai assertion riêng:

```text
1. Was OrderPlaced published?            -> kiểm tra ApplicationEvents
2. Did after-commit handler run?         -> kiểm tra effect sau commit
```

Với callback hậu commit ghi database mới, cần xem xét `REQUIRES_NEW` và idempotency nếu nghiệp vụ yêu cầu. `AFTER_COMMIT` không tự cung cấp exactly-once, retry hay durability.

## 14. Mock publisher hay record event thật?

Có hai đường kiểm thử bổ sung nhau.

### 14.1. Unit test với mock ApplicationEventPublisher

Trong một unit test của service thuần, có thể mock `ApplicationEventPublisher` (Mockito hoặc hand-written fake) rồi dùng `ArgumentCaptor<OrderPlaced>` để kiểm tra object passed vào `publishEvent`.

Ưu điểm: nhanh, không cần Spring context, kiểm tra event được service tạo theo hợp đồng. Giới hạn: không chứng minh Spring đã đăng ký listener, filter đúng generic payload, hoặc đã phát event trong multicaster.

Ví dụ ý tưởng:

```java
verify(publisher).publishEvent(captor.capture());
OrderPlaced actual = captor.getValue();
// Assert thuộc tính trên actual.
```

Đây là snippet Mockito tích hợp, cần mock và captor được định nghĩa; **không thuộc bộ test Maven ở mục 6**. Nếu dùng overload `publishEvent(Object)` và `publishEvent(ApplicationEvent)`, cần chú ý kiểu argument khi verify, để không bắt nhầm overload.

### 14.2. Integration test dùng @RecordApplicationEvents

Test Spring thật để:

- Gọi service đã được Spring inject publisher.
- Spring nhận POJO/record và phân phối qua event infrastructure.
- Dùng `ApplicationEvents.stream(OrderPlaced.class)` lấy payload thực tế.
- Kiểm tra record và listener tương ứng nhận đúng kiểu.

Đây là hướng mà chương trình mục 6 thực hiện. Nó phù hợp cho kiểm thử **payload và thuộc tính** trong hạ tầng Spring, nhưng nếu có hệ thống bên ngoài, vẫn cần test consumer/integration riêng.

### 14.3. Test không nên biết quá nhiều implementation detail

Cần assert các thuộc tính thực sự thuộc hợp đồng nghiệp vụ: `orderId`, `eventId`, `correlationId`, giá trị chi tiết, điều kiện phát event. Đừng assert:

- Thứ tự callback giữa listener không có yêu cầu order cụ thể.
- Tên thread đúng từng ký tự nếu không phải yêu cầu.
- Con số timestamp tự tạo từ `System.currentTimeMillis()`.
- Toàn bộ `toString()` của record, khi chỉ vài field có ý nghĩa.
- Toàn bộ số lượng event hệ thống trong context, nếu chỉ kiểm tra một loại.

Test quá gắn chặt vào implementation dễ thất bại khi refactor vô hại.

## 15. Quy tắc về version, enum, tiền tệ và null

Một payload chất lượng thường có bất biến sâu hơn việc “field khác null”:

| Dữ liệu | Assertion nên có | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| `schemaVersion` | Dương và đúng version được gửi | Consumer parse sai schema |
| `aggregateVersion` | Khớp version sau thay đổi | Xử lý đảo thứ tự hoặc ghi đè read model |
| `status` enum | Bằng trạng thái nghiệp vụ mong đợi | Event báo sai sự thật |
| `BigDecimal` | Giá trị và scale/rounding policy rõ | Sai số tiền hoặc equality sai |
| `currency` | Đúng mã tiền tệ nếu nghiệp vụ dùng | Trộn các loại tiền |
| `causationId` | Null/ID cha đúng theo workflow | Mất quan hệ nhân quả |
| `List/Map` | Dữ liệu nested chính xác, không bị sửa | Race và snapshot sai |
| Nullable optional | Hợp đồng null rõ, dùng `assertNull` khi hợp lệ | NPE hoặc sai trạng thái |
| `eventId` | Duy nhất cho occurrence mới, ổn định khi retry | Khử trùng sai |
| Thời gian | Dùng `Clock.fixed` hoặc fixture `Instant` | Flaky test vì đồng hồ |

Ví dụ, `schemaVersion=1` của `OrderPlaced` trong chương trình là một giá trị hợp lệ. Nếu schema thay đổi, cần test backward/forward compatibility theo chiến lược cụ thể; `@RecordApplicationEvents` không tự kiểm tra format JSON gửi qua broker.

Không đưa secret hoặc dữ liệu nhạy cảm dư thừa vào payload chỉ để test dễ hơn. Một record tạo `toString()` chứa các component, có thể bị log nguyên giá trị khi debug.

## 16. Những lỗi kiểm thử thường gặp

1. **Chỉ assert số lần listener được gọi.** Có thể nhận đúng số lần nhưng sai `orderId`/`eventId`.
2. **Gọi thẳng method handler thay vì publish qua Spring** rồi tuyên bố hạ tầng event hoạt động.
3. **Không bật `@RecordApplicationEvents`** nhưng cố inject và dùng `ApplicationEvents`.
4. **Inject `ApplicationEvents` vào constructor của test hoặc singleton bean** thay vì trong test method/field.
5. **Dùng `events.stream().count()` để đếm một loại event.** Event context khác có thể làm test sai.
6. **Quên lọc theo lớp POJO record** và tưởng rằng chỉ subclass `ApplicationEvent` được record.
7. **Chỉ assert event khác null** mà không kiểm tra metadata và nested data.
8. **Không sao chép collection đầu vào** và bỏ qua việc caller thay đổi list sau publish.
9. **Cho rằng record immutable sâu** mặc dù chứa array/entity mutable.
10. **Assert `Instant.now()` bằng `Instant.now()`.** Timestamp gần nhau không nhất thiết bằng nhau.
11. **So sánh `BigDecimal` bằng `equals` mà không nghĩ đến scale.** Quy tắc equality phải theo nghiệp vụ.
12. **Không tách các test được cache chung ApplicationContext.** Listener singleton giữ dữ liệu từ lần test trước.
13. **Đoán thứ tự hoàn thành khi listener dùng `@Async`.** Dùng latch/future có timeout.
14. **Cho rằng `@RecordApplicationEvents` ghi được mọi event từ mọi worker thread** bất kể thread/context propagation; phải kiểm tra giới hạn và cơ chế instrumentation.
15. **Quên transaction test mặc định rollback.** Listener `AFTER_COMMIT` không chạy chỉ vì publisher đã phát event.
16. **Dùng `getSource()` như causationId nghiệp vụ.** Source object của Spring và quan hệ event cha là hai khái niệm khác nhau.
17. **Cho rằng Spring tự dedupe eventId.** Cùng event có thể được phát nhiều lần; idempotency thuộc thiết kế consumer.
18. **Dùng `Thread.sleep` cố định để test async.** Dễ flaky khi máy CI chậm.
19. **Chỉ mock publisher mà bỏ kiểm tra một đường Spring thật.** Unit test không thay thế integration test wiring.
20. **Coi có event là đã gửi email/commit DB thành công.** Publish không tự đảm bảo tác dụng phụ hoặc durability.

## 17. Checklist trước khi hoàn thành bộ test

- [ ] Đã xác định đúng **kiểu event** và nơi publish thật.
- [ ] Test dùng `@SpringJUnitConfig`/`@RecordApplicationEvents` hoặc recorder hợp lệ.
- [ ] Lấy payload từ `ApplicationEvents.stream(PayloadType.class)`.
- [ ] Assert số lượng, ID, metadata, thời gian và nested data cụ thể.
- [ ] Timestamp domain được điều khiển bằng fixture hoặc injectable Clock.
- [ ] Validation lỗi làm event **không được phát**.
- [ ] Event khác loại không bị tính nhầm.
- [ ] Payload snapshot không đổi sau khi caller sửa collection đầu vào.
- [ ] Có kiểm tra việc mutation từ accessor bị từ chối khi hợp đồng yêu cầu immutable.
- [ ] Nếu dùng `ApplicationEvent` subclass, kiểm tra source/timestamp đúng ý nghĩa.
- [ ] Không mặc định Spring tự bỏ event trùng.
- [ ] Recorder/listener dùng chung context được reset; test không phụ thuộc phương thức chạy trước.
- [ ] Nếu xử lý async, dùng cơ chế đợi có timeout và recorder an toàn luồng.
- [ ] Nếu xử lý hậu commit, test rõ commit/rollback và hiệu ứng sau commit.
- [ ] Các side effect bên ngoài có test riêng với retry và idempotency khi cần.
- [ ] Lệnh `mvn test` chạy đủ các test và CI báo không có failures/errors.

**Kết luận:** kiểm thử Spring Application Events nên xem event là **một hợp đồng dữ liệu**: đúng loại, đúng số lần, đúng payload và metadata, ổn định qua thời gian, đồng thời được Spring publish qua đường thực tế. `@RecordApplicationEvents` + `ApplicationEvents.stream(Class<T>)` giúp ghi nhận và assert event ngay trong Spring TestContext; JUnit 5 cung cấp các assertion; kiểm thử listener bất đồng bộ, transaction và tác dụng phụ cần thêm các cơ chế xác nhận riêng.

## Tài liệu chính thức

- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — ApplicationEvents API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — Spring JUnit Jupiter annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
