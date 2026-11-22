# Assert event bằng stream trong kiểm thử Spring Application Events

## 1. Mục tiêu: kiểm chứng sự kiện thực sự được publish

Trong Spring Framework, một service thường không trả về trực tiếp các domain event mà nó phát:

```java
public void placeOrder(String orderId) {
    // Thực hiện thao tác nghiệp vụ hợp lệ.
    publisher.publishEvent(new OrderPlaced(orderId, 2500));
}
```

Đoạn trên là ví dụ phương thức minh họa: giả định `publisher` là `ApplicationEventPublisher`, `OrderPlaced` là kiểu event do ứng dụng định nghĩa, và phần kiểm tra nghiệp vụ đã được thực hiện. Muốn kiểm thử hành vi, việc chỉ assert return value là chưa đủ. Ta cần biết:

- Đã publish **đúng kiểu event** hay chưa?
- Publish bao nhiêu lần, có phát trùng không?
- Payload có đúng định danh và giá trị nghiệp vụ không?
- Với input không hợp lệ, có **không phát** event thành công hay không?
- Nếu nhiều event cùng loại được phát, có thể lọc, biến đổi và so sánh danh sách kỳ vọng thế nào?

Spring TestContext Framework cung cấp `org.springframework.test.context.event.ApplicationEvents` để ghi nhận những application events trong phạm vi **một test method**. API này cho phép đọc các event như `java.util.stream.Stream`, rất tiện cho assertion bằng JUnit 5 hoặc AssertJ.

Ví dụ ý tưởng:

```java
long count = events.stream(OrderPlaced.class).count();
assertEquals(1, count);
```

Điều cần phân biệt ngay từ đầu: **đây là khả năng của Spring TestContext (module `spring-test`), không phải cú pháp riêng chỉ có ở Spring Boot**. Một project Spring Framework thuần có thể dùng `@RecordApplicationEvents` + `@SpringJUnitConfig`; Spring Boot project thường dùng `@SpringBootTest` cùng annotation ghi nhận này.

## 2. API cần biết: ApplicationEvents và @RecordApplicationEvents

Bộ công cụ kiểm thử chính gồm:

| Thành phần | Package | Công dụng |
| --- | --- | --- |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Yêu cầu Spring TestContext ghi nhận application events trong từng test |
| `ApplicationEvents` | `org.springframework.test.context.event` | Cung cấp các event đã được ghi nhận cho test đang chạy |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Tích hợp ghi nhận với test lifecycle; được đăng ký mặc định trong cấu hình TestContext chuẩn |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Ghép SpringExtension và ContextConfiguration cho JUnit Jupiter |
| `ApplicationEventPublisher` | `org.springframework.context` | Đối tượng application service dùng để publish |
| `Stream<T>` | `java.util.stream` | Lọc, đếm, biến đổi, tìm event để assert |

Các thao tác cốt lõi của `ApplicationEvents` trong Spring Framework 6.2:

```java
Stream<ApplicationEvent> all = events.stream();

Stream<OrderPlaced> placed = events.stream(OrderPlaced.class);

events.clear();
```

Đoạn trên chỉ minh họa API, giả định `events` được cung cấp trong test và `OrderPlaced` do ứng dụng khai báo. `ApplicationEvents.stream(Class<T>)` có thể stream cả **ApplicationEvent subclass** lẫn **payload của event** có kiểu chỉ định. Điểm này quan trọng vì `ApplicationEventPublisher.publishEvent(Object)` hỗ trợ POJO/Java record không kế thừa `ApplicationEvent`.

`ApplicationEvents.clear()` xóa **những event đã ghi trong recorder của test**, không thu hồi sự kiện đã gửi tới listener, không đảo ngược side effect, không rollback transaction và không xóa domain data.

### 2.1. Vì sao phải có @RecordApplicationEvents?

Đăng ký listener business theo `@EventListener` không tự tạo recorder kiểm thử. Cần kích hoạt rõ:

```java
@SpringJUnitConfig(MyConfig.class)
@RecordApplicationEvents
class OrderServiceTest {
    // Test methods...
}
```

Nếu quên `@RecordApplicationEvents`, test không được bảo đảm có `ApplicationEvents` để inject theo quy trình chuẩn. Đừng cố khởi tạo `new ApplicationEvents()`: đây là interface do TestContext cung cấp, không phải object lưu event mà ứng dụng tự tạo.

### 2.2. Inject ApplicationEvents như thế nào?

Cách được Spring hướng dẫn khi dùng JUnit Jupiter là inject vào **method parameter**:

```java
@Test
void publishesEvent(ApplicationEvents events) {
    // events dùng trong đúng test method này.
}
```

Khi test đã có `@SpringJUnitConfig` hoặc `@SpringBootTest` và `@RecordApplicationEvents`, SpringExtension có thể cung cấp argument này.

Cũng có thể inject vào field:

```java
@Autowired
ApplicationEvents events;
```

Nhưng **không constructor-inject ApplicationEvents vào test class**. Nó được đăng ký như một resolvable dependency trong scope của vòng đời test method, không phải một singleton application bean dùng mọi nơi.

### 2.3. TestExecutionListener có cần đăng ký thủ công?

Với cấu hình Spring TestContext thông thường, `ApplicationEventsTestExecutionListener` được đăng ký mặc định. Chỉ cần xem lại nếu project đã tự cấu hình `@TestExecutionListeners` và thay thế danh sách listener mặc định.

Nếu thay danh sách và loại bỏ listener quản lý application events, `@RecordApplicationEvents` có thể không hoạt động theo kỳ vọng. Không thêm listener trùng một cách tùy tiện; kiểm tra cách hợp nhất cấu hình hiện có.

## 3. Hai stream khác nhau: stream() và stream(Class<T>)

### 3.1. stream(Class<T>) — đường thông dụng nhất

```java
events.stream(OrderPlaced.class)
```

Kiểu phần tử của stream là `OrderPlaced`. Nếu `OrderPlaced` là Java record và publisher gọi `publishEvent(new OrderPlaced(...))`, Spring vẫn ghi nhận được **payload** tương ứng để typed stream trả ra.

Vì có kiểu, có thể gọi accessor trực tiếp:

```java
boolean found = events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100"));
```

Không cần ép kiểu `ApplicationEvent` hay kiểm tra `instanceof` thủ công.

### 3.2. stream() — stream của application event wrappers

```java
Stream<ApplicationEvent> eventsOnContext = events.stream();
```

Ở đây kiểu phần tử là `ApplicationEvent`. Khi bạn publish một POJO, Spring có thể gói nó trong `PayloadApplicationEvent<?>` để phân phối qua hạ tầng `ApplicationEvent`. Vì vậy, đoạn kiểm tra sau có thể cho kết quả sai dù POJO đã được phát:

```java
// Phản ví dụ: stream() chứa ApplicationEvent,
// không nhất thiết chứa trực tiếp POJO record.
boolean found = events.stream()
        .anyMatch(e -> e instanceof OrderPlaced);
```

Nó còn có vấn đề kiểu Java: nếu `OrderPlaced` không kế thừa `ApplicationEvent`, biểu thức `instanceof OrderPlaced` trên biến có kiểu `ApplicationEvent` có thể **không biên dịch** khi hai kiểu không tương thích theo luật kiểm tra kiểu của Java. Hãy dùng `events.stream(OrderPlaced.class)` thay vì cách này.

Khi cần xử lý hỗn hợp nhiều loại event, có thể dùng `stream()` và kiểm tra `PayloadApplicationEvent<?>` cùng `getPayload()`, nhưng nên làm vậy chỉ nếu bài kiểm thử thật sự cần quan sát **toàn bộ dòng event**. Với một domain event type cụ thể, typed stream đơn giản và chính xác hơn.

### 3.3. Lưu ý lifecycle events và framework events

ApplicationContext có thể phát các event khác như `ContextRefreshedEvent`, `ContextClosedEvent`; Spring TestContext cũng có các test lifecycle events. Khi kiểm tra tổng số qua `events.stream().count()`, bạn có thể vô tình đếm cả sự kiện không thuộc hành vi đang test.

**Tránh:**

```java
assertEquals(1, events.stream().count());
```

khi mục tiêu là chứng minh service publish đúng một `OrderPlaced`.

**Ưu tiên:**

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

Chỉ so sánh tổng của mọi event nếu bạn đã xác định rõ phạm vi và loại event framework có thể xuất hiện trong test đó.

## 4. Các thao tác Stream API thường dùng để assert

| Thao tác | Mẫu | Khi nên dùng |
| --- | --- | --- |
| `count()` | `stream(OrderPlaced.class).count()` | Đếm số event cụ thể |
| `anyMatch(...)` | Tìm event có `orderId` xác định | Khẳng định tồn tại ít nhất một fact |
| `noneMatch(...)` | Không có event sai quy tắc | Khẳng định điều **không** được phát |
| `allMatch(...)` | Mọi event thỏa predicate | Kiểm tra các bất biến chung |
| `filter(...)` | Lọc theo tenant/order/status | Thu hẹp tập event trước assertion |
| `map(...)` | Chuyển event thành ID/amount | So sánh payload gọn hơn |
| `findFirst()` | Lấy event đầu tiên theo encounter order | Khi kỳ vọng có event phù hợp và thứ tự được xác định |
| `toList()` | Materialize danh sách event/payload | So sánh danh sách, số lần lặp, thứ tự |
| `distinct()` | Loại trùng giá trị | Hữu ích cho phân tích, **không** dùng để che duplicate |
| `groupingBy(...)` | Nhóm theo tenant/loại | Khi cần thống kê nhiều occurrence |

Ví dụ để đếm đúng một lần:

```java
assertEquals(1L, events.stream(OrderPlaced.class).count());
```

Để kiểm tra payload cụ thể:

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100")
                && e.amountMinor() == 2500));
```

Để kiểm tra không có event “đặt đơn thành công” khi bị từ chối:

```java
assertEquals(0L, events.stream(OrderPlaced.class).count());
assertTrue(events.stream(OrderRejected.class)
        .anyMatch(e -> e.reason().equals("INVALID_AMOUNT")));
```

Để kiểm tra tất cả event đều có dữ liệu hợp lệ:

```java
assertTrue(events.stream(OrderPlaced.class)
        .allMatch(e -> e.amountMinor() > 0));
```

**Bẫy:** `allMatch` trên stream **rỗng trả true** (vacuous truth). Nếu mục tiêu là “có ít nhất một event, và tất cả event đều hợp lệ”, cần assert count > 0 hoặc danh sách không rỗng trước.

### 4.1. Đếm đúng trước rồi mới kiểm tra nội dung

Một assertion chỉ có `anyMatch` có thể pass dù service publish **hai hoặc ba event trùng**. Khi nghiệp vụ yêu cầu exactly one *occurrence trong lần gọi test*, kết hợp:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("O-100", placed.get(0).orderId());
assertEquals(2500, placed.get(0).amountMinor());
```

Điều này kiểm tra đồng thời **số lượng và payload**, dễ đọc hơn một chuỗi predicate phức tạp.

Lưu ý “một event trong test” không đồng nghĩa nền tảng bảo đảm **exactly-once delivery** qua broker hoặc qua tiến trình khác. Đây chỉ là assertion tại boundary test được kiểm soát.

### 4.2. So sánh thứ tự của nhiều event cùng loại

```java
List<String> ids = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .toList();

assertEquals(List.of("O-100", "O-101"), ids);
```

Cách này hợp lý khi thao tác publish chạy **đồng bộ, có thứ tự xác định**, và bạn muốn kiểm tra thứ tự ghi nhận trong recorder. Không suy từ nó rằng những listener bất đồng bộ hoặc remote consumers đã hoàn tất theo thứ tự đó.

## 5. Ví dụ dự án Java 17 chạy được: Spring Framework + JUnit 5

Ví dụ sau là một **integration-style test nhỏ** của `ApplicationEventPublisher`, không cần Spring Boot, HTTP server hoặc database. Nó dùng:

- Java 17 trở lên.
- Spring Framework `spring-context` và `spring-test` cùng phiên bản **6.2.12**.
- JUnit Jupiter **5.11.4**.
- Maven Surefire để chạy các phương thức `@Test`.
- Java records làm domain event payload.

### 5.1. Cấu trúc project

```text
spring-event-stream-test/
├── pom.xml
└── src/test/java/demo/EventStreamTest.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-stream-test</artifactId>
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
        </plugins>
    </build>
</project>
```

File `src/test/java/demo/EventStreamTest.java`:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(EventStreamTest.Config.class)
@RecordApplicationEvents
class EventStreamTest {

    record OrderPlaced(String orderId, int amountMinor) {}
    record OrderRejected(String orderId, String reason) {}

    static final class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void place(String orderId, int amountMinor) {
            Objects.requireNonNull(orderId, "orderId");

            if (amountMinor <= 0) {
                publisher.publishEvent(
                        new OrderRejected(orderId, "INVALID_AMOUNT"));
                return;
            }

            publisher.publishEvent(
                    new OrderPlaced(orderId, amountMinor));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Autowired
    OrderService service;

    @Test
    void recordsOneEventWithCorrectPayload(ApplicationEvents events) {
        events.clear();
        service.place("O-100", 2500);

        List<OrderPlaced> placed =
                events.stream(OrderPlaced.class).toList();

        assertEquals(1, placed.size());
        assertEquals("O-100", placed.get(0).orderId());
        assertEquals(2500, placed.get(0).amountMinor());
        assertEquals(0L, events.stream(OrderRejected.class).count());
    }

    @Test
    void filtersSeveralEventsByType(ApplicationEvents events) {
        events.clear();
        service.place("O-101", 1200);
        service.place("O-BAD", 0);
        service.place("O-102", 3400);

        assertEquals(2L, events.stream(OrderPlaced.class).count());
        assertEquals(1L, events.stream(OrderRejected.class).count());

        List<String> ids = events.stream(OrderPlaced.class)
                .map(OrderPlaced::orderId)
                .toList();
        assertEquals(List.of("O-101", "O-102"), ids);
    }

    @Test
    void rejectsInvalidAmountWithoutPlacedEvent(ApplicationEvents events) {
        events.clear();
        service.place("O-103", -1);

        assertEquals(0L, events.stream(OrderPlaced.class).count());
        assertTrue(events.stream(OrderRejected.class)
                .anyMatch(e -> e.orderId().equals("O-103")
                        && e.reason().equals("INVALID_AMOUNT")));
    }

    @Test
    void checksAllEventsAndExactMultiplicity(ApplicationEvents events) {
        events.clear();
        service.place("O-104", 500);
        service.place("O-104", 600);

        List<OrderPlaced> placed =
                events.stream(OrderPlaced.class).toList();

        assertEquals(2, placed.size());
        assertTrue(placed.stream().allMatch(e -> e.amountMinor() > 0));
        assertEquals(List.of(500, 600),
                placed.stream().map(OrderPlaced::amountMinor).toList());
    }

    @Test
    void clearResetsOnlyTheRecordedWindow(ApplicationEvents events) {
        events.clear();
        service.place("O-OLD", 100);
        assertEquals(1L, events.stream(OrderPlaced.class).count());

        events.clear();
        service.place("O-NEW", 200);

        List<String> ids = events.stream(OrderPlaced.class)
                .map(OrderPlaced::orderId).toList();
        assertEquals(List.of("O-NEW"), ids);
        assertFalse(ids.contains("O-OLD"));
    }

    @Test
    void noCallMeansNoBusinessEvent(ApplicationEvents events) {
        events.clear();

        assertEquals(0L, events.stream(OrderPlaced.class).count());
        assertEquals(0L, events.stream(OrderRejected.class).count());
    }
}
```

Từ thư mục `spring-event-stream-test`, chạy:

```bash
mvn test
```

Khi môi trường có JDK 17+, Maven và tải được dependencies, toàn bộ **6 test methods** trong class `EventStreamTest` cần pass. Trong phần tổng kết của Maven Surefire sẽ có ý nghĩa tương đương:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là các dòng kết quả trọng yếu mong đợi; những dòng tải dependency, thông báo Maven/Surefire và vị trí log có thể khác tùy môi trường. Bản demo không in business stdout, bởi mục tiêu là **test assertions**.

### 5.2. Vì sao cấu hình này chạy được?

- `@SpringJUnitConfig(EventStreamTest.Config.class)` tích hợp JUnit Jupiter với Spring TestContext và nạp một configuration rất nhỏ.
- `@Bean OrderService` nhận `ApplicationEventPublisher` từ Spring context. Test field `@Autowired OrderService service` lấy bean thực.
- `@RecordApplicationEvents` kích hoạt recorder cho lifecycle của từng test method.
- Tham số `ApplicationEvents events` của mỗi `@Test` được SpringExtension cung cấp theo phạm vi test hiện hành.
- `events.clear()` đặt một mốc ghi nhận sạch **trước thao tác đang kiểm tra**. Nó không làm ảnh hưởng tới context bean, chỉ xóa các event đã ghi trước đó trong recorder.
- Khi gọi `service.place(...)`, service publish object Java record `OrderPlaced` hoặc `OrderRejected`. Spring event framework cho phép publish POJO và recorder typed stream trả về payload đúng kiểu.
- Từng test chỉ assert event của thao tác nó thực sự gọi; không phụ thuộc vào số `ContextRefreshedEvent` hoặc framework events của vòng đời test.

### 5.3. Tại sao không cần @EventListener trong ví dụ?

Bài này kiểm tra **producer có publish đúng event**, không kiểm tra consumer side effect. `ApplicationEvents` ghi nhận event được phát trong application context của test, vì vậy không bắt buộc phải khai báo business `@EventListener` để assertions có dữ liệu.

Nếu muốn kiểm tra listener có gửi email, cập nhật bảng hoặc gọi service ngoài hay không, đó là **một mục tiêu test khác**. Việc recorder thấy event chỉ chứng minh fact đã được phát tại boundary Spring context; nó không chứng minh một consumer đã xử lý thành công mọi side effect.

### 5.4. Lưu ý về tính nhất quán của ví dụ

Ví dụ `OrderService` cố tình đơn giản: không dùng repository, không lưu transaction, không kiểm tra chống duplicate. Test `checksAllEventsAndExactMultiplicity` chứng minh **hai lần gọi place tạo hai event**, không khẳng định đây là hành vi nghiệp vụ đúng của hệ thống bán hàng thật.

Trong production, chỉ phát `OrderPlaced` sau khi domain xác nhận trạng thái đủ điều kiện. Kiểm thử nên đi kèm các assertion về invariant và sự kiện **không được** phát khi thao tác bị từ chối.

## 6. Những assertion hữu ích trong dự án thực

### 6.1. Assert event tồn tại

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> "O-100".equals(e.orderId())));
```

Tốt khi một test chỉ cần chứng minh một fact cụ thể đã xuất hiện. Nhưng nếu hệ thống không được phát trùng, cần thêm kiểm tra số lượng.

### 6.2. Assert không tồn tại event bị cấm

```java
assertTrue(events.stream(OrderPlaced.class)
        .noneMatch(e -> "O-FAILED".equals(e.orderId())));
```

Cách này tránh sự phụ thuộc vào nội dung event khác cùng loại, đặc biệt khi một test cố tình thực hiện nhiều operations trong một workflow.

### 6.3. Assert tập event đúng chính xác

```java
List<String> actualIds = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .toList();

assertEquals(List.of("O-1", "O-2"), actualIds);
```

Phép kiểm tra trên có ý nghĩa khi thứ tự publish được thiết kế xác định. Nếu chỉ cần set bất kể thứ tự, có thể dùng `Set.copyOf(actualIds)` cùng assertion về **số lượng phần tử trước** để tránh việc loại trùng âm thầm. Không dùng `distinct()` rồi tự kết luận không có duplicate.

### 6.4. Assert giá trị money và tenant đúng

Với payload:

```java
public record PaymentCaptured(
        String tenantId,
        String paymentId,
        long amountMinor,
        String currency) {}
```

Có thể:

```java
List<PaymentCaptured> payments =
        events.stream(PaymentCaptured.class).toList();

assertEquals(1, payments.size());
assertEquals("tenant-blue", payments.get(0).tenantId());
assertEquals("P-3", payments.get(0).paymentId());
assertEquals(125000L, payments.get(0).amountMinor());
assertEquals("VND", payments.get(0).currency());
```

Các đoạn trên là **minh họa cho một test có `PaymentCaptured` riêng**, không phải thành phần của Maven project ở phần 5. Điều cần assert là giá trị có ý nghĩa với domain, không phải toàn bộ object runtime hoặc timestamp bất định.

### 6.5. Assert với AssertJ nếu dự án đã sử dụng

```java
import static org.assertj.core.api.Assertions.assertThat;

List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertThat(placed)
        .hasSize(2)
        .extracting(OrderPlaced::orderId)
        .containsExactly("O-1", "O-2");
```

Đây là snippet có thư viện **AssertJ** trên test classpath. Ví dụ Maven ở phần 5 chỉ dùng JUnit Jupiter, **không** đưa AssertJ vào dependency, nên snippet AssertJ không thuộc chương trình standalone ấy.

Với AssertJ, cũng có thể áp dụng `assertThat(events.stream(OrderPlaced.class))` tùy phiên bản API; nhưng materialize bằng `toList()` thường giúp message lỗi, kiểm tra nhiều thuộc tính và debugging dễ hiểu hơn.

### 6.6. Assert nested payload bằng predicate có kiểm soát

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-100")
                && e.amountMinor() > 0));
```

Predicate nên ngắn và không có side effect. Với nhiều thuộc tính, tách thành `List<Event>` rồi assert các field sẽ rõ hơn và dễ chẩn đoán khi test fail.

## 7. Lưu ý Stream là pipeline tiêu thụ một lần

Java `Stream` không phải collection có thể sử dụng nhiều lần. Sai lầm phổ biến:

```java
Stream<OrderPlaced> stream = events.stream(OrderPlaced.class);

long count = stream.count();
boolean found = stream.anyMatch(e -> e.orderId().equals("O-1"));
// Sai: stream đã bị consumed. Có thể ném IllegalStateException.
```

Cách đúng thứ nhất: tạo **stream mới** cho mỗi terminal operation:

```java
long count = events.stream(OrderPlaced.class).count();
boolean found = events.stream(OrderPlaced.class)
        .anyMatch(e -> "O-1".equals(e.orderId()));
```

Cách đúng thứ hai: materialize thành **List** một lần:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
assertEquals("O-1", placed.get(0).orderId());
```

Khi dùng `Stream.toList()` từ Java 16+, danh sách trả về là unmodifiable. Không gọi `placed.add(...)` trên danh sách đó để mô phỏng sự kiện mới. Nếu cần một list mutable phục vụ thiết lập test khác, dùng `new ArrayList<>(...)` một cách có chủ ý.

### Stream có lazy evaluation

Các thao tác `filter/map` thường không chạy cho đến khi có terminal operation như `count`, `toList` hoặc `anyMatch`. Đừng đặt logic thay đổi dữ liệu hoặc side effect trong predicate, vì compiler và Stream không bảo đảm pipeline sẽ duyệt toàn bộ khi sử dụng short-circuit operations như `anyMatch`/`findFirst`.

Ví dụ tốt:

```java
List<String> ids = events.stream(OrderPlaced.class)
        .filter(e -> e.amountMinor() > 0)
        .map(OrderPlaced::orderId)
        .toList();
```

Không gọi `publishEvent` từ trong `filter` để “tạo thêm event cần kiểm thử”; việc thay đổi collection nguồn trong khi stream đang được tiêu thụ có thể cho kết quả khó kiểm soát.

## 8. Isolation: mỗi test cần một cửa sổ ghi nhận rõ

### 8.1. @RecordApplicationEvents có scope theo test method

Theo Spring TestContext, `ApplicationEvents` dùng cho **vòng đời của test method đang thực thi**, không phải lịch sử toàn bộ ứng dụng. Điều này giúp giảm rủi ro dữ liệu chồng giữa các test.

Dù vậy, các event từ test lifecycle hoặc một setup routine cũng có thể được ghi lại. Nếu mục tiêu là kiểm tra riêng một lệnh, cách dễ hiểu là `events.clear()` ngay trước action:

```java
events.clear();
service.place("O-100", 2500);
assertEquals(1, events.stream(OrderPlaced.class).count());
```

Khi dùng `@BeforeEach` để khởi tạo dữ liệu có publish domain event, hãy nhớ những event setup không thuộc action đang test. Có thể clear sau setup hoặc tổ chức fixture để không publish.

### 8.2. clear không reset ứng dụng

`events.clear()` chỉ xóa recorder. Nó **không**:
- Hoàn tác một transaction đã commit.
- Gỡ listener đã đăng ký trong context.
- Đặt lại state của singleton service/repository.
- Hủy các async task đang chạy.
- Xóa các message đã đưa vào queue hoặc broker.
- Làm mất audit records đã ghi ở database.

Nếu các test cần dữ liệu độc lập, hãy dùng transaction rollback khi phù hợp, dữ liệu test độc lập, repository cleanup hoặc Spring context isolation. Không lạm dụng `@DirtiesContext` chỉ để làm sạch recorder.

### 8.3. Không inject ApplicationEvents vào test constructor

`ApplicationEvents` là dependency có scope tương ứng lifecycle của test method. Vì vậy:

```java
// Không dùng trong test class constructor:
MyTest(ApplicationEvents events) {
    this.events = events;
}
```

Đoạn này là **phản ví dụ**, không thuộc phần code compile. Sử dụng injection vào `@Test` method hoặc field.

### 8.4. Custom TestExecutionListeners

Nếu project định nghĩa riêng `@TestExecutionListeners(listeners = {...})` và không merge defaults, recorder cần thiết có thể bị bỏ. Đọc quy tắc cấu hình TestExecutionListeners của Spring TestContext trước khi thay listener defaults, thay vì tự tạo một `ApplicationEvents` ở test code.

## 9. Khi nào count, anyMatch, allMatch cho kết quả sai ý nghĩa?

### 9.1. allMatch trên stream rỗng

```java
assertTrue(events.stream(OrderPlaced.class)
        .allMatch(e -> e.amountMinor() > 0));
```

Nếu không có event nào, assertion vẫn pass. Muốn test “có ít nhất một event và tất cả có amount dương”, viết:

```java
List<OrderPlaced> placed = events.stream(OrderPlaced.class).toList();
assertFalse(placed.isEmpty());
assertTrue(placed.stream().allMatch(e -> e.amountMinor() > 0));
```

### 9.2. anyMatch không phát hiện duplicate

```java
assertTrue(events.stream(OrderPlaced.class)
        .anyMatch(e -> e.orderId().equals("O-1")));
```

Nó pass dù có 10 event `OrderPlaced("O-1",...)`. Nếu cần đúng một occurrence:

```java
long matching = events.stream(OrderPlaced.class)
        .filter(e -> e.orderId().equals("O-1"))
        .count();
assertEquals(1L, matching);
```

### 9.3. Kiểm tra “không phát event” trên tổng stream

```java
assertEquals(0, events.stream().count());
```

Điều này dễ bị sai do event khác của Spring hoặc của fixture. Nếu kiểm tra “thao tác bị từ chối không phát success event”, dùng:

```java
assertEquals(0L, events.stream(OrderPlaced.class).count());
```

### 9.4. distinct() làm mất bằng chứng publish lặp

```java
long unique = events.stream(OrderPlaced.class)
        .map(OrderPlaced::orderId)
        .distinct()
        .count();
```

`unique == 1` không chứng minh đã publish đúng một lần. Đếm event thô **trước khi** distinct.

### 9.5. Dùng findFirst mà không kiểm tra empty

```java
OrderPlaced first = events.stream(OrderPlaced.class)
        .findFirst()
        .orElseThrow(() ->
                new AssertionError("Expected an OrderPlaced event"));
```

Với test có thể không nhận event, cách này báo lỗi assertion rõ ràng. Không gọi `.get()` trên `Optional.empty()` khi chưa biết có phần tử.

## 10. Assert thứ tự: phải xác định thứ tự của cái gì

Có ít nhất ba khái niệm khác nhau:

1. **Thứ tự publish:** service gọi `publishEvent(A)` rồi `publishEvent(B)`.
2. **Thứ tự recorder ghi nhận:** các event được recorder nhận trong test context.
3. **Thứ tự consumer hoàn thành:** listener xử lý xong A rồi B, có thể khác hẳn khi async.

Với mã synchronous trong ví dụ, `events.stream(OrderPlaced.class).map(...).toList()` là cách hợp lý để kiểm tra thứ tự **các occurrence cùng kiểu được ghi nhận**.

Nếu muốn xác minh một workflow phát các kiểu event khác nhau theo thứ tự, dùng các sự kiện đã ghi trên stream chung **kèm xử lý wrapper** hoặc một test recorder chuyên dụng ghi metadata/kiểu theo thiết kế. Đừng so sánh `List<Class<?>>` bằng cách gọi `events.stream().map(Object::getClass)` rồi kỳ vọng thấy `OrderPlaced.class`: với POJO, phần tử có thể là `PayloadApplicationEvent` wrapper.

Một phương án kiểm tra event payload trong `stream()` khi thật sự cần:

```java
List<Object> payloads = events.stream()
        .filter(e -> e instanceof PayloadApplicationEvent<?>)
        .map(e -> ((PayloadApplicationEvent<?>) e).getPayload())
        .toList();
```

Đây là **snippet minh họa**; cần import `org.springframework.context.PayloadApplicationEvent` và `List`. Nó không nằm trong file `EventStreamTest.java` của phần 5. Không dùng snippet nếu test chỉ quan tâm một kiểu, vì typed stream ngắn và mạnh hơn.

Quan trọng: kiểm tra thứ tự ghi nhận trong test không tạo guarantee về **ordering trên message broker**, transaction commit hoặc tác vụ hoàn thành ở executor.

## 11. Event đồng bộ và event bất đồng bộ: giới hạn của recorder

### 11.1. Khi publish đồng bộ

`SimpleApplicationEventMulticaster` mặc định chạy listener trên thread của publisher. Trong test ví dụ, việc gọi `service.place(...)` hoàn tất trước khi đọc `events.stream(...)`; vì thế assertion không cần chờ và kết quả ổn định.

Synchronous case là nơi `@RecordApplicationEvents` tiện dụng nhất.

### 11.2. Khi xử lý listener bất đồng bộ

Có hai tình huống cần phân biệt:

- **Publish đồng bộ, listener `@Async`:** event có thể đã được recorder ghi nhận trên thread publish, nhưng consumer xử lý side effect ở thread khác và chưa hoàn tất. Assert “event đã publish” vẫn khác assert “listener đã làm xong”.
- **Event được publish từ worker thread khác:** Spring TestContext sử dụng cơ chế quản lý sự kiện theo phạm vi test/thread. Không nên mặc định rằng `ApplicationEvents` sẽ ghi nhận chính xác mọi event publish từ thread ngoài test theo thời điểm/kỹ thuật đã chọn. Hãy kiểm thử hệ thống thực và dùng recorder/thread-safe test probe phù hợp.

Đừng áp dụng cách “publish → lập tức `count()` → assert” cho async pipeline mà không kiểm soát ranh giới ghi nhận. Nếu system under test thực sự publish sau một `CompletableFuture`, hàng đợi hoặc scheduler, cần một cơ chế chờ có thời hạn và một recorder quan sát đúng nơi event được phát.

### 11.3. Không dùng Thread.sleep thay điều kiện hoàn thành

Mẫu không ổn định:

```java
service.startAsync();
Thread.sleep(100);
assertEquals(1L, events.stream(OrderPlaced.class).count());
```

Thread scheduling, CI load và GC làm 100 ms không đáng tin. Thay vào đó:

- Dùng `CountDownLatch` hoặc `CompletableFuture` mà test kiểm soát và có timeout.
- Dùng Awaitility nếu project đã có dependency và recorder thật sự nhận được event xuyên thread.
- Với mục tiêu test **producer**, tách thao tác publish vào phần synchronous, test side effect async ở bài khác.
- Thiết kế listener recorder dùng `BlockingQueue` hoặc collection đồng bộ khi nhiều thread có thể gọi.

Ví dụ recorder đơn giản cho **một loại event**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;

public class EventProbe {
    private final BlockingQueue<OrderPlaced> received =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        received.add(event);
    }

    public OrderPlaced awaitOne() throws InterruptedException {
        return received.poll(3, TimeUnit.SECONDS);
    }
}
```

Đoạn này là **test helper minh họa**, giả định kiểu `OrderPlaced` đã khai báo và class được đăng ký làm Spring bean. Test có thể assert `assertNotNull(probe.awaitOne())` sau khi gọi thao tác async. Tuy nhiên, nó đo **việc EventProbe listener được gọi**, không chứng minh một listener nghiệp vụ khác đã hoàn tất. Nếu cần kiểm tra consumer side effect, đồng bộ hóa tại chính boundary thực thi side effect.

## 12. Transactional events: assert đúng thời điểm

`@TransactionalEventListener` thường thực thi theo transaction phase, chẳng hạn `AFTER_COMMIT`. Việc `ApplicationEvents` ghi lại một event đã publish **không** chứng minh callback sau commit đã chạy:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Logic diễn ra sau transaction commit thành công.
}
```

Đây là đoạn phương thức **minh họa**, cần bean Spring, transaction manager và các import tương ứng.

Tình huống hay gặp:

1. Service bắt đầu transaction và publish `OrderPlaced`.
2. Recorder ghi nhận việc publish trong test.
3. Transaction **rollback** trước khi commit.
4. Callback `AFTER_COMMIT` không thực thi; tuy nhiên assertion “đã publish event” vẫn có thể pass.

Đặc biệt, test có `@Transactional` thường rollback khi kết thúc test, nên `@TransactionalEventListener(AFTER_COMMIT)` không nhất thiết chạy. Muốn kiểm thử việc callback chạy sau commit, hãy dùng transaction boundary tường minh, `TestTransaction` hoặc chiến lược commit có chủ đích, đồng thời xác minh side effect chứ không chỉ count event.

**Quy tắc:** `events.stream(OrderPlaced.class).count()` kiểm tra **đường publish vào ApplicationContext** trong scope test. Nó không kiểm tra database transaction đã commit, message broker đã nhận, hay callback `AFTER_COMMIT` đã hoàn thành.

Nếu event phải được phát bền vững qua tiến trình khác, kết hợp test outbox/retry/delivery phù hợp; không dùng stream recorder để tuyên bố exactly-once.

## 13. Khi nào nên dùng Mockito thay vì ApplicationEvents stream?

Hai kỹ thuật có mục tiêu hơi khác:

| Lựa chọn | Điều được kiểm tra | Phù hợp với |
| --- | --- | --- |
| Mock `ApplicationEventPublisher` bằng Mockito | Method `publishEvent(...)` được gọi với argument đúng | Unit test thuần, không cần Spring Context |
| `@RecordApplicationEvents` + `ApplicationEvents.stream(...)` | Event được publish qua application context thật trong Spring TestContext | Integration/slice test dùng context |
| Recorder business listener | Listener thực sự nhận event và có thể ghi lại payload | Test dispatch/listener behavior |
| Kiểm tra repository/outbox/broker | State/delivery bền vững | Transaction/integration/contract test |

Một unit test Mockito minh họa:

```java
ApplicationEventPublisher publisher =
        mock(ApplicationEventPublisher.class);

OrderService service = new OrderService(publisher);
service.place("O-100", 2500);

verify(publisher).publishEvent(
        new OrderPlaced("O-100", 2500));
```

Đây là **snippet minh họa**, cần Mockito test dependency/imports và cho phép truy cập constructor `OrderService`/record `OrderPlaced`. Nếu publisher có các overload hoặc phương thức gọi khác, hãy xác định đúng overload. `record` có value equality, vì vậy đối tượng event mới có field bằng nhau phù hợp với `verify` theo `equals()`.

Không cần khởi tạo Spring TestContext cho unit test chỉ nhằm chứng minh một đối tượng collaborator bị gọi. Ngược lại, khi muốn kiểm tra integration event routing, `ApplicationEvents` phản ánh đường publish qua Spring context tốt hơn việc chỉ mock interface.

### Bẫy khi test trước publication boundary

Mock chứng minh service **gọi publisher**, nhưng không chứng minh context thực sự dispatch event. Recorder trong test context chứng minh event xuất hiện trong hạ tầng publish, nhưng không chứng minh delivery bền vững. Chọn phương án theo mục tiêu, không mặc định một công cụ thay thế tất cả.

## 14. Test event có payload bất định như UUID hoặc Instant

Nhiều event mang `eventId` được tạo ngẫu nhiên và `occurredAt` từ clock hiện hành. Assert toàn bộ object bằng một giá trị cố định có thể gây test giòn.

Ví dụ domain payload:

```java
public record OrderPlaced(
        UUID eventId,
        String orderId,
        Instant occurredAt) {}
```

Mẫu assertion phù hợp:

```java
List<OrderPlaced> placed =
        events.stream(OrderPlaced.class).toList();

assertEquals(1, placed.size());
OrderPlaced event = placed.get(0);

assertEquals("O-100", event.orderId());
assertNotNull(event.eventId());
assertNotNull(event.occurredAt());
```

Đây là snippet độc lập về logic nhưng giả định test đã có `OrderPlaced` 3-field tương ứng, khác với record 2-field của ví dụ phần 5; cần imports JUnit, `UUID` và `Instant`.

Nếu cần assert mốc thời gian **chính xác**, hãy inject `Clock.fixed(...)` vào service để test có deterministic time. Không nên so sánh `Instant.now()` với một giá trị đoán trước rồi nới timeout tùy tiện.

Nếu event có `List` hoặc `Map` mutable trong payload, phải đảm bảo snapshot và defensive copy theo thiết kế; Stream assertion về payload có thể bị ảnh hưởng nếu producer sửa object sau khi publish.

## 15. Assertions âm tính là một phần không thể thiếu

Để test chất lượng nghiệp vụ, không chỉ hỏi “event nào được phát?”, mà còn hỏi **“event nào tuyệt đối không được phát ở nhánh này?”**

Ví dụ:

| Tình huống | Event phải có | Event không được có |
| --- | --- | --- |
| Đặt đơn hợp lệ | `OrderPlaced` | `OrderRejected` |
| Số tiền không hợp lệ | `OrderRejected` | `OrderPlaced` |
| Thanh toán pending | Có thể có `PaymentPending` theo domain | Không phát `PaymentCaptured` khi chưa thu |
| Giao dịch rollback | Có thể có internal event trước commit tùy thiết kế | Không tuyên bố durable integration event đã được giao |
| Người dùng không đủ quyền | Có thể log denied audit event theo policy | Không phát success fact nghiệp vụ |
| Duplicate command bị ngăn | Có thể phát kết quả idempotency riêng | Không phát thêm một business fact nếu không thật sự xảy ra |

Kết hợp positive và negative assertions giúp phát hiện logic như “vừa phát `OrderPlaced`, vừa phát `OrderRejected` cho cùng lệnh”. Chỉ assert một event có tồn tại có thể bỏ lọt lỗi này.

## 16. Các lỗi phổ biến

1. **Quên `@RecordApplicationEvents`** và nghĩ recorder mặc định có mặt trong mọi Spring test.
2. **Dùng nhầm `org.springframework.boot.context.event.*`** cho `ApplicationEvents`: API recorder thuộc `spring-test`, không phải Spring Boot startup event package.
3. **Dùng `events.stream()` rồi giả định phần tử là Java record payload**: nó trả `ApplicationEvent` wrappers; nên dùng `stream(MyEvent.class)`.
4. **Đếm tổng mọi event** để chứng minh domain event: lifecycle/test framework events có thể chen vào.
5. **Chỉ `anyMatch` mà quên số lượng**: duplicate event vẫn pass.
6. **Chỉ `allMatch` mà quên kiểm tra không rỗng**: stream rỗng làm assertion pass giả.
7. **Tiêu thụ lại cùng một `Stream`** sau `count()` rồi `anyMatch()`: ném exception hoặc sai cấu trúc test.
8. **Gọi `clear()` sau action nhưng trước assertion**: vô tình xóa bằng chứng cần kiểm tra.
9. **Tin rằng `clear()` rollback dữ liệu**: nó chỉ xóa recorder trong test scope.
10. **Constructor-inject ApplicationEvents**: dependency scoped theo test method, không thích hợp inject vào constructor test.
11. **Dùng `@TestExecutionListeners` tùy biến loại bỏ defaults**: recorder không được đăng ký đúng.
12. **Assert thứ tự hoàn tất async bằng thứ tự recorder**: đó là hai thứ tự khác nhau.
13. **Dùng `Thread.sleep(100)` để đợi event**: test flake khi CI chậm.
14. **Coi event recorder chứng minh listener side effect thành công**: recorder kiểm chứng publish, không kiểm chứng hậu quả.
15. **Coi event recorder chứng minh transaction commit**: publish có thể xảy ra trước rollback.
16. **Nhầm ghi event trong TestContext với broker delivery guarantee**: không có bảo đảm bền vững, retry hoặc exactly-once tự động.
17. **Lạm dụng `distinct()`** rồi bỏ qua lỗi phát trùng.
18. **So sánh UUID/timestamp runtime với literal cố định** mà không dùng fixed clock.
19. **Không kiểm tra nhánh unauthorized/invalid**: event success có thể bị phát sai.
20. **Dùng test state chung giữa các phương thức**: kết quả phụ thuộc thứ tự test hoặc các singleton có side effect.

## 17. Checklist trước khi kết luận test PASS

- [ ] Đã phân biệt **producer publish** với **consumer hoàn thành** chưa?
- [ ] Test có Spring TestContext và `@RecordApplicationEvents` hay chỉ là unit test thuần?
- [ ] `ApplicationEvents` được inject trong method/field, không phải constructor?
- [ ] Đang dùng `events.stream(MyEvent.class)` để lấy đúng payload type?
- [ ] Có đặt cửa sổ ghi nhận rõ ràng bằng `clear()` khi cần?
- [ ] Có assert **số lượng chính xác**, không chỉ `anyMatch`?
- [ ] Có assert các field có ý nghĩa nghiệp vụ và các invariant quan trọng?
- [ ] Nhánh invalid/unauthorized có test **không phát event success**?
- [ ] Có tránh dùng `allMatch` trên stream rỗng như bằng chứng tồn tại?
- [ ] Khi kiểm tra thứ tự, đã xác định đây là publish/recording order chứ không phải listener completion?
- [ ] Có dependency `spring-test`, JUnit Jupiter và TestExecutionListener đúng?
- [ ] Nếu async, đã dùng cơ chế chờ và recorder thread-safe phù hợp?
- [ ] Nếu transactional, đã tách publication assertion khỏi after-commit/durability assertion?
- [ ] Nếu payload chứa thời gian/UUID, test có deterministic input hoặc assertion phù hợp?
- [ ] Không để business events của setup/test khác làm nhiễu kết quả?
- [ ] Khi test thất bại, message assertion có đủ rõ để chỉ ra event sai loại, số lượng hay payload?

**Kết luận:** `ApplicationEvents.stream(Class<T>)` kết hợp `@RecordApplicationEvents` là cách trực tiếp, dễ đọc để assert các domain events đã được Spring application context publish trong phạm vi test method. Hãy lọc **đúng kiểu**, kiểm tra **đúng số lần**, rồi kiểm tra **payload và nhánh không được phát event**. Với event đồng bộ, cách này rất ổn định. Với async, transaction hoặc delivery qua broker, cần thêm cơ chế test phù hợp vì **event đã được ghi nhận không đồng nghĩa consumer đã hoàn tất hay dữ liệu đã commit**.

## Tài liệu tham khảo

- [Spring Framework — Application Events trong TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — ApplicationEvents Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12-SNAPSHOT/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Java 17 — java.util.stream.Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
