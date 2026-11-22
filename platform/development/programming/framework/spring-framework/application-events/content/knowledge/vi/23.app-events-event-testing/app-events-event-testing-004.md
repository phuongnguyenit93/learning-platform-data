# @RecordApplicationEvents: kiểm thử Spring Application Events

`@RecordApplicationEvents` là annotation của **Spring Framework TestContext**, dùng để ghi lại những application events được publish trong `ApplicationContext` trong vòng đời **một test method**. Sau đó, test đọc các event đã ghi nhận bằng API `ApplicationEvents` để khẳng định một tác vụ thật sự đã phát event nào, số lần bao nhiêu và payload có nội dung gì.

Ví dụ use case: khi gọi `OrderService.placeOrder("PO-42")`, service phải publish đúng một `OrderPlaced` có mã đơn `PO-42`. Thay vì tạo một mock `ApplicationEventPublisher` và chỉ xác minh `publishEvent(...)` được gọi, một integration test có thể để **Spring Context thực** phát event, rồi dùng `@RecordApplicationEvents` thu thập kết quả.

**Lưu ý tên package:** Đây **không phải annotation riêng của Spring Boot**. Nó có từ Spring Framework **5.3.3**, thuộc `org.springframework.test.context.event.RecordApplicationEvents` trong artifact `spring-test`. Spring Boot có thể sử dụng annotation này vì `@SpringBootTest` tích hợp Spring TestContext, nhưng một test Spring thuần với `@SpringJUnitConfig` cũng dùng được.

## 1. @RecordApplicationEvents giải quyết bài toán gì?

Khi testing event-driven code, ta muốn phân biệt ba câu hỏi:

1. **Publisher đã phát event đúng chưa?** Kiểm tra `ApplicationEvents.stream(OrderPlaced.class)`.
2. **Listener có thực hiện đúng side effect chưa?** Kiểm tra riêng trạng thái do listener tạo ra, ví dụ repository, một fake notification gateway, hoặc một spy.
3. **Transaction của nghiệp vụ có commit thành công chưa?** Kiểm tra outcome transaction/database; **đếm event đã publish không chứng minh đã commit**.

`@RecordApplicationEvents` giải quyết trực tiếp **câu hỏi thứ nhất**. Nó không phải message broker, không tự tạo event, không đảm bảo listener hoàn tất và không thay thế assertion cho database hoặc service ngoài.

```text
Test method (Spring TestContext)
    |
    +-- @RecordApplicationEvents
    |        |
    |        +-- ApplicationEventsTestExecutionListener chuẩn bị recorder
    |        +-- ApplicationEvents sẵn có trong vòng đời test method
    |
    +-- gọi OrderService.placeOrder(...)
                |
                +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                            |
                            +-- event multicaster gọi các listener phù hợp
                            |
                            +-- recorder giữ event đã publish
    |
    +-- events.stream(OrderPlaced.class)
    |        +-- kiểm tra count, payload, order ID, sequence...
    |
    +-- hết test method -> recorder của method đó kết thúc
```

Không cần tạo một `ApplicationEvents` bean production. Spring TestContext cung cấp **test-scoped resolvable dependency** khi annotation và `ApplicationEventsTestExecutionListener` hoạt động.

## 2. Các thành phần liên quan

| Thành phần | Package / vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Đặt trên **test class** hoặc làm meta-annotation; không dùng như annotation cho một test method đơn lẻ |
| `ApplicationEvents` | `org.springframework.test.context.event` | Truy cập các event đã ghi nhận trong vòng đời test hiện tại |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Kích hoạt việc ghi nhận; được Spring TestContext đăng ký **mặc định** |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Kết hợp SpringExtension và Spring test context config cho JUnit 5 |
| `@SpringBootTest` | `org.springframework.boot.test.context` | Có thể thay `@SpringJUnitConfig` khi cần Boot application context |
| `ApplicationEventPublisher` | `org.springframework.context` | API production để publish event |
| `@EventListener` | `org.springframework.context.event` | Định nghĩa phương thức xử lý event, độc lập với recorder của test |

`@RecordApplicationEvents` chỉ hoạt động khi test được chạy trong **Spring TestContext framework**, ví dụ thông qua `SpringExtension` với JUnit Jupiter. Dùng một test JUnit thuần không tải Spring context rồi chỉ thêm annotation này sẽ không tạo ra recorder tự động.

### Vòng đời theo từng test method

`ApplicationEvents` gắn với **vòng đời method test hiện tại**, không phải singleton để giữ một lịch sử event xuyên suốt cả test suite. Nếu test class có nhiều `@Test`, mỗi test có tập recorded events của lần chạy đó.

Có thể nhận `ApplicationEvents` bằng hai cách phổ biến:

**Cách khuyên dùng với JUnit 5:** làm tham số của `@Test`, `@BeforeEach` hoặc `@AfterEach`:

```java
@Test
void publishOrder(ApplicationEvents events) {
    // events thuộc về test method này.
}
```

**Cách dùng field:**

```java
@Autowired
ApplicationEvents events;
```

Hai đoạn trên là **mã khung**, cần nằm trong test class có `@RecordApplicationEvents` và context Spring phù hợp.

Không inject `ApplicationEvents` qua **constructor của test class**: tại thời điểm constructor chạy, test-method lifecycle chưa sẵn sàng. Tài liệu Spring TestContext nêu rõ chỉ dùng instance này trong vòng đời method. Không đưa `ApplicationEvents` vào singleton bean production để giữ nó làm dependency dài hạn.

## 3. API của ApplicationEvents

API cốt lõi có ba phương thức:

```java
Stream<ApplicationEvent> stream();
<T> Stream<T> stream(Class<T> type);
void clear();
```

Đây là **chữ ký rút gọn** của interface `ApplicationEvents`, không phải chương trình Java độc lập.

### 3.1. stream(Class<T>): lọc theo kiểu event/payload

```java
long count = events.stream(OrderPlaced.class).count();

List<OrderPlaced> orderEvents =
        events.stream(OrderPlaced.class).toList();
```

Nếu `OrderPlaced` là record/POJO được phát qua `publishEvent(new OrderPlaced(...))`, Spring có thể đóng gói nó trong `PayloadApplicationEvent`. `stream(OrderPlaced.class)` vẫn trả về **payload kiểu `OrderPlaced`**, cho phép khẳng định nội dung mà không cần cast wrapper.

Việc lọc theo type đặc biệt quan trọng vì context có thể publish nhiều sự kiện framework khác: refresh, lifecycle, test events hoặc event của những component khác. Đừng assert tổng `events.stream().count() == 1` chỉ vì service của bạn publish một event.

### 3.2. stream(): xem toàn bộ ApplicationEvent

```java
events.stream().forEach(event ->
        System.out.println(event.getClass().getSimpleName()));
```

Đoạn này trả về stream của các `ApplicationEvent` thực sự đã ghi nhận, có thể gồm `PayloadApplicationEvent<?>` khi publisher phát POJO. Dùng để khám phá, phân loại hoặc debug event; thông thường test nghiệp vụ nên ưu tiên `stream(MyDomainEvent.class)` để giảm nhiễu.

### 3.3. clear(): làm sạch những event đã ghi nhận trong **method hiện tại**

```java
events.clear();

service.placeOrder("PO-43");

assertEquals(1L, events.stream(OrderPlaced.class).count());
```

`clear()` xóa **danh sách event được recorder giữ**, không hoàn tác transaction, không xóa database, không gọi lại listener, không sửa trạng thái của publisher và không đợi event async hoàn thành. Vì vậy có thể dùng `clear()` để tạo ranh giới quan sát rõ ràng giữa hai hành động trong cùng một test.

## 4. Ví dụ Java 17+ hoàn chỉnh: Spring Test + JUnit 5 + @RecordApplicationEvents

Ví dụ dùng **Spring Framework 6.2.9**, không cần Spring Boot hay database. Chúng ta tạo một Spring-managed service phát record `OrderPlaced`, rồi kiểm tra lần phát thứ nhất, xóa recorder và kiểm tra lần phát thứ hai. Chỉ có **một test method**, nên stdout ổn định.

### 4.1. Cấu trúc dự án

```text
record-application-events-demo/
├── pom.xml
└── src/test/java/example/events/RecordApplicationEventsTest.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>record-application-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-test` chứa `@RecordApplicationEvents` và `ApplicationEvents`. `junit-jupiter` cung cấp JUnit 5 API và test engine; `maven-surefire-plugin` chạy test theo mẫu tên `*Test`. Không cần tạo một Spring Boot application để kiểm tra cơ chế ghi nhận event này.

### 4.3. src/test/java/example/events/RecordApplicationEventsTest.java

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(RecordApplicationEventsTest.TestConfig.class)
@RecordApplicationEvents
class RecordApplicationEventsTest {

    record OrderPlaced(String orderId, String customerId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void placeOrder(String orderId) {
            publisher.publishEvent(new OrderPlaced(orderId, "C-7"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Autowired
    OrderService service;

    @Test
    void recordsDomainEventsAndCanClearThem(ApplicationEvents events) {
        // Không có OrderPlaced nào được ghi trước thao tác.
        assertEquals(0L, events.stream(OrderPlaced.class).count());

        service.placeOrder("PO-42");

        List<OrderPlaced> first = events.stream(OrderPlaced.class).toList();
        assertEquals(1, first.size());
        assertEquals("PO-42", first.get(0).orderId());
        assertEquals("C-7", first.get(0).customerId());
        System.out.println("recorded: " + first.get(0).orderId());

        // Chỉ xóa các event recorder đang giữ.
        events.clear();

        long afterClear = events.stream(OrderPlaced.class).count();
        assertEquals(0L, afterClear);
        System.out.println("after clear: " + afterClear);

        service.placeOrder("PO-43");

        List<OrderPlaced> second = events.stream(OrderPlaced.class).toList();
        assertEquals(1, second.size());
        assertEquals("PO-43", second.get(0).orderId());
        System.out.println("recorded: " + second.get(0).orderId());
    }
}
```

Từ thư mục chứa `pom.xml`, cần **JDK 17+** và **Maven**:

```bash
mvn -q test
```

Các dòng do chính test in ra theo thứ tự sau, không tính log của Maven/JUnit/Spring:

```text
recorded: PO-42
after clear: 0
recorded: PO-43
```

Test phải kết thúc thành công (Maven exit code 0); nếu assertion sai, Maven Surefire báo test failed.

**Tại sao ví dụ hoạt động?**

1. `@SpringJUnitConfig` tạo Spring test context và đăng ký `SpringExtension` cho JUnit 5. `TestConfig` cung cấp `OrderService` là Spring bean.
2. `@RecordApplicationEvents` kích hoạt recorder thông qua `ApplicationEventsTestExecutionListener`. Listener này thường đã có trong danh sách default `TestExecutionListeners`.
3. `service.placeOrder("PO-42")` gọi `ApplicationEventPublisher.publishEvent(...)` thực tế; Spring ghi nhận payload `OrderPlaced`.
4. Test method nhận `ApplicationEvents` qua parameter injection. `events.stream(OrderPlaced.class)` lọc đúng domain event, kiểm tra số lượng và các field.
5. `events.clear()` làm rỗng bộ nhớ recorder trong method hiện tại. Publish tiếp `PO-43` chỉ tạo một event mới trong danh sách đang được test xem.
6. Test **không có business listener**. Đây là chủ ý để chứng minh `@RecordApplicationEvents` quan sát **publication**, không yêu cầu đã có listener xử lý event nghiệp vụ.

Nếu một số event lifecycle của Spring tồn tại trong test context, chúng **không làm sai** các assertion vì test chỉ lọc `OrderPlaced.class`.

## 5. Dùng với @SpringBootTest

Trong ứng dụng Spring Boot, annotation vẫn là từ `spring-test` nhưng có thể kết hợp `@SpringBootTest`, ví dụ:

```java
@SpringBootTest
@RecordApplicationEvents
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void publishesCheckoutCompleted(ApplicationEvents events) {
        checkoutService.checkout("CHK-42");

        assertEquals(1L,
                events.stream(CheckoutCompleted.class).count());
    }
}
```

Đây là **đoạn minh họa tích hợp**, không độc lập: ứng dụng phải có `CheckoutService`, `CheckoutCompleted`, @SpringBootTest và các import cần thiết. Spring Boot test dependencies thường được cung cấp bằng `spring-boot-starter-test`. Không cần tự khai báo một bean `ApplicationEvents` trong cấu hình production.

Có thể thêm các assertion cho nội dung payload:

```java
List<CheckoutCompleted> captured =
        events.stream(CheckoutCompleted.class).toList();

assertEquals("CHK-42", captured.get(0).checkoutId());
```

Không nên chỉ đếm events nếu phần quan trọng của hợp đồng là mã định danh, version, timestamp hoặc trạng thái nghiệp vụ. Tuy nhiên, tránh assert những giá trị không ổn định như `Instant.now()` chính xác từng nano-giây; hãy inject một `Clock` kiểm soát được vào service hoặc kiểm tra một khoảng thời gian hợp lý.

### So với mock ApplicationEventPublisher

| Cách test | Kiểm tra tốt nhất | Không chứng minh |
| --- | --- | --- |
| Mockito `verify(publisher).publishEvent(...)` | Service có gọi đúng API publish không | Spring context thực đã phát event hay chưa |
| `@RecordApplicationEvents` + `ApplicationEvents` | Spring context ghi nhận event đúng type/payload/số lần | Listener đã xử lý xong, transaction đã commit |
| Spy/mock listener hoặc kiểm tra side effect | Một listener cụ thể đã thực thi công việc | Toàn bộ event khác cũng được xử lý |
| Database/outbox integration test | Thay đổi bền vững và commit/rollback | Consumer ngoài JVM đã nhận message |

Chọn test phù hợp với **hợp đồng thật** cần bảo vệ. Nếu chỉ test domain model thuần Java, không cần bật Spring context; nếu muốn kiểm tra Spring event publication thực tế, `@RecordApplicationEvents` là lựa chọn đúng.

## 6. Chú ý @Transactional trong test: đã ghi nhận event không có nghĩa đã commit

Đây là một trong những bẫy lớn nhất khi dùng `@RecordApplicationEvents`.

Giả sử service publish `OrderPlaced` bên trong một transaction và có listener:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    notificationService.notifyCustomer(event.orderId());
}
```

Đoạn này **chỉ là minh họa tích hợp**. `@TransactionalEventListener` gắn execution của listener với **pha commit thành công**, không phải thời điểm chỉ gọi `publishEvent(...)`.

Trong Spring TestContext, một test method có `@Transactional` thường được **tự động rollback** sau khi test kết thúc. Vì vậy có thể xảy ra:

```text
@Transactional test bắt đầu transaction T1
       |
       +-- service.placeOrder(...)
       |      +-- publishEvent(OrderPlaced)
       |             +-- @RecordApplicationEvents ghi nhận event
       |             +-- @TransactionalEventListener(AFTER_COMMIT) đăng ký callback
       |
       +-- events.stream(OrderPlaced.class).count() == 1
       |
       +-- test kết thúc
              +-- T1 bị ROLLBACK theo mặc định
              +-- AFTER_COMMIT KHÔNG CHẠY
```

Do đó, việc thấy `ApplicationEvents` có event **không chứng minh** side effect after-commit đã chạy. Nếu muốn test listener `AFTER_COMMIT`, hãy đảm bảo transaction thật sự commit trước khi assert side effect.

Các hướng phù hợp:

1. Dùng một test **không có test-managed `@Transactional`** bao ngoài, gọi service transactional qua Spring proxy để service tự commit khi trả về, rồi kiểm tra side effect.
2. Trong một test transaction có chủ đích, dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` để kết thúc bằng commit trước khi assert side effect. Đây là công cụ của `spring-test` và chỉ hoạt động khi có test-managed transaction hợp lệ.
3. Sử dụng `@Commit` hoặc `@Rollback(false)` nếu muốn transaction test commit sau test method, **nhưng không assert after-commit side effect ngay bên trong method trước khi framework commit**; cần lifecycle hook hoặc thiết kế test phù hợp.
4. Nếu dữ liệu test đã được commit, quản lý **cleanup/isolation** rõ ràng, không để dữ liệu làm ô nhiễm các test tiếp theo.

Không nên gọi `flush()` hoặc `saveAndFlush()` rồi coi đó là commit: flush có thể đưa SQL vào database nhưng transaction vẫn có thể rollback. `events.clear()` cũng hoàn toàn không ảnh hưởng commit.

### @RecordApplicationEvents có ghi cả event của transaction rollback không?

Có thể ghi nhận một event **đã publish trong transaction**, dù transaction đó sau đó rollback. Recorder quan sát **publication** của Spring event, không lọc chỉ những event thuộc transaction đã commit. Nếu yêu cầu “chỉ ghi nhận sau commit”, thiết kế event hoặc listener theo transaction phase rồi kiểm tra kết quả tương ứng, không suy luận từ recorder.

Với listener `AFTER_ROLLBACK`/`AFTER_COMPLETION`, phải phân biệt event được publish và callback được gọi sau transaction. Một test có `@Transactional` và auto-rollback có thể khiến một số callback rollback chạy **sau khi các assertion trong test body đã hoàn tất**. Kiểm thử giai đoạn này ở điểm đồng bộ chính xác thay vì dùng delay ngẫu nhiên.

## 7. @RecordApplicationEvents có quan sát được event bất đồng bộ không?

Theo hợp đồng Spring TestContext, recorder gắn với **vòng đời test method** và cơ chế test execution. Tài liệu Javadoc mô tả việc ghi nhận các event được publish từ test thread **hoặc các thread con** trong phạm vi hỗ trợ. Tuy nhiên không thể coi annotation này là bộ thu toàn cục cho **mọi thread từ executor pool hoặc mọi process**.

Ví dụ:

```java
@Async("eventExecutor")
public void publishLater(String orderId) {
    applicationEventPublisher.publishEvent(new OrderPlaced(orderId));
}
```

Đây là **đoạn minh họa tích hợp**, không độc lập: cần `@EnableAsync`, bean `eventExecutor` và các lớp liên quan. `publishLater(...)` có thể chạy sau khi test body đã kiểm tra recorder, hoặc trên executor thread không có cùng test-scoped recording context. Kết quả `events.stream(...)` lúc đó có thể chưa có event hoặc không phản ánh toàn bộ luồng async.

Để kiểm thử async đáng tin cậy:

- **Đợi completion thật:** `CompletableFuture`, latch hoặc test executor được điều khiển; không dùng `Thread.sleep(...)` rồi hy vọng event đã phát.
- **Kiểm tra context boundary:** có phải event được publish trong cùng Spring context và trong vòng đời method hiện tại không? Executor thread có nhận context phù hợp không?
- **Tách assertion:** nếu mục tiêu là listener async đã thực hiện side effect, kiểm tra side effect/spy hoặc trạng thái bền vững sau completion, thay vì chỉ dựa vào event recorder.
- **Với broker ngoài JVM:** dùng contract/integration test của broker và consumer riêng; `@RecordApplicationEvents` không tự nhận Kafka/RabbitMQ messages.
- **Không gắn thử nghiệm với thứ tự luồng không được bảo đảm:** recorder không phải một scheduler/delivery-order specification.

Nếu test yêu cầu mỗi event async phải được bắt một cách tất định, có thể kiểm soát executor trong test, chuyển một luồng cần đo sang synchronous hoặc thiết kế điểm đồng bộ/hook phù hợp. Không “sửa” test flaky bằng sleep lâu hơn.

## 8. Kết hợp với @EventListener: ghi nhận publication khác với kiểm tra xử lý

Giả sử có listener:

```java
@Component
class OrderAccountingListener {

    private final AccountingService accounting;

    OrderAccountingListener(AccountingService accounting) {
        this.accounting = accounting;
    }

    @EventListener
    void on(OrderPlaced event) {
        accounting.recordRevenue(event.orderId());
    }
}
```

Đây là **đoạn minh họa**, giả định `OrderPlaced` và `AccountingService` tồn tại.

Một integration test chuẩn có thể:

1. Gọi service phát `OrderPlaced`.
2. Assert `events.stream(OrderPlaced.class)` có đúng event và payload.
3. Assert `accounting` (spy/mock) được gọi hoặc database được cập nhật như hợp đồng.
4. Nếu async, đợi completion rõ ràng trước khi assert bước 3.
5. Nếu transaction-bound, assert ở thời điểm transaction thực sự hoàn tất.

Nếu chỉ kiểm tra `events.stream(...)`, test vẫn pass ngay cả khi `OrderAccountingListener` không được đăng ký, đang bỏ qua event theo điều kiện, hoặc thất bại ở một thread khác. **Kiểm tra publication và kiểm tra consumption nên là hai assertion độc lập**.

### Số lượng event và trùng lặp

`ApplicationEvents.stream(OrderPlaced.class).count()` đếm số lần event phù hợp được recorder lưu. Nếu cùng một hành động phát hai event cùng type, count có thể là 2. Nhưng số lần publisher gọi **không luôn** bằng số tác vụ nghiệp vụ có kết quả cuối cùng: một listener có thể retry, publish event thứ cấp, hoặc application context hierarchy có thể chuyển event tới parent contexts.

Để bắt bug phát trùng:

- Kiểm tra `eventId` và các business identifiers ổn định khi hợp đồng yêu cầu uniqueness.
- Không chỉ assert `count() > 0` nếu hợp đồng yêu cầu đúng **một** event.
- Nếu cần kiểm tra thứ tự các event trong một luồng đồng bộ, thu thập stream theo thứ tự ghi nhận và so sánh; không áp dụng kỳ vọng thứ tự hoàn tất cho listener async.
- Dùng `events.clear()` trước hành động cần đo khi muốn loại sự kiện cùng type từ `@BeforeEach` hoặc bước setup, nhưng đừng xóa bằng cách che giấu một hành vi publish không mong muốn trong setup.

## 9. @TestExecutionListeners tùy chỉnh có thể làm recorder không hoạt động

`ApplicationEventsTestExecutionListener` là một trong các Spring `TestExecutionListener` **được đăng ký theo mặc định**. Khi test dùng `@TestExecutionListeners` để thay thế danh sách mặc định mà không merge, listener ghi nhận có thể bị bỏ mất.

Ví dụ *minh họa cấu hình cần cẩn trọng*:

```java
@TestExecutionListeners(
        listeners = CustomTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

Đoạn code này cần `CustomTestExecutionListener` và import annotation. `MERGE_WITH_DEFAULTS` giúp giữ các listener framework mặc định, trong đó có recorder, đồng thời bổ sung listener tùy chỉnh. Nếu bạn chủ động thay toàn bộ danh sách, phải đăng ký `ApplicationEventsTestExecutionListener` phù hợp theo yêu cầu của framework.

Khi annotation tồn tại nhưng `ApplicationEvents` không inject được, kiểm tra:

- Test có chạy qua SpringExtension/TestContext framework chưa?
- `@RecordApplicationEvents` có đặt trên class hoặc meta-annotation phù hợp không?
- Có `@TestExecutionListeners` tùy chỉnh đã loại defaults không?
- Có đang inject `ApplicationEvents` vào constructor hoặc singleton ngoài lifecycle test method không?
- Có đang kiểm tra event từ context khác, process khác hoặc thread async ngoài phạm vi recorder không?

Không giải quyết vấn đề bằng cách tạo một `ApplicationEvents` bean production tùy tiện; nó không thay thế `ApplicationEventsTestExecutionListener`.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “`@RecordApplicationEvents` chỉ dùng cho Spring Boot” | Thuộc **Spring Framework TestContext**; Spring Boot là một trong các môi trường sử dụng |
| “Annotation tự tạo listener nghiệp vụ” | Nó ghi lại publication; không thay listener của ứng dụng |
| “`stream(OrderPlaced.class)` đếm mọi Spring lifecycle event” | Chỉ lọc event hoặc payload tương ứng kiểu `OrderPlaced` |
| “`stream()` trả về trực tiếp mọi POJO đã publish” | API không tham số trả về `Stream<ApplicationEvent>`, POJO thường nằm trong `PayloadApplicationEvent` |
| “`clear()` rollback database” | Chỉ xóa event recorder đang giữ |
| “Test có event -> listener AFTER_COMMIT đã chạy” | Không; transaction test thường rollback mặc định |
| “Test có event -> external message đã được gửi” | Không; broker/outbox cần assertion riêng |
| “Mọi thread đều được record” | Không bảo đảm với executor pool hoặc process khác |
| “Dùng `@RecordApplicationEvents` thay được Mockito hoàn toàn” | Nó chỉ đo publication thực; mock/spy có nhiệm vụ khác |
| “Không có event trong stream là chắc chắn service không publish” | Cần kiểm tra lifecycle recorder, context, thread, loại event và test setup |
| “Cứ có `@RecordApplicationEvents` mà không dùng SpringExtension cũng chạy” | Cần Spring TestContext hỗ trợ |
| “Có thể inject `ApplicationEvents` qua constructor test class” | Không nên; dependency scoped theo từng test method |

## 11. Chiến lược kiểm thử thực tế

Một bộ test bền vững cho hệ thống dùng Spring events có thể chia lớp:

**Unit test domain / service:** Kiểm tra điều kiện phát event và payload bằng fake/mocked publisher hoặc domain event collector; không cần Spring context khi không kiểm tra event multicasting.

**Spring integration test với `@RecordApplicationEvents`:** Kiểm tra event được publish từ Spring-managed service/repository; type, số lượng, nội dung và những event không được phép phát. Không suy luận commit từ publication.

**Listener integration test:** Xác nhận đăng ký `@EventListener`, filter `condition`, `@Order` khi liên quan, side effects và error propagation. Nếu listener async, đợi completion; nếu transaction-bound, commit/rollback đúng như use case.

**Transaction/outbox test:** Ghi dữ liệu và event outbox trong cùng transaction, thực hiện rollback giả lập, đọc từ kết nối mới và kiểm tra dữ liệu bền vững. Khi cần delivery thật, bổ sung test broker/consumer, idempotency và retry riêng.

Đối với test Spring Boot có thể tốn thời gian khởi tạo context, hãy dùng `@SpringJUnitConfig` với cấu hình tối thiểu cho những test chỉ cần event bus; dùng `@SpringBootTest` khi muốn cả auto-configuration hoặc wiring production thực.

### Một checklist trước khi chấp nhận test

1. Test có `@RecordApplicationEvents` đúng class và SpringExtension/TestContext hoạt động?
2. Có assert **event type + payload + số lượng**, không chỉ “có ít nhất một” khi hợp đồng yêu cầu chính xác?
3. Có tránh nhầm các lifecycle events của framework với domain event?
4. Có xử lý `ApplicationEvents` trong đúng test-method lifecycle?
5. Nếu có transaction, có phân biệt publication với commit và listener phase?
6. Nếu có async, có điểm đồng bộ rõ ràng thay vì sleep?
7. Nếu cần listener side effect, có assertion độc lập với event recorder?
8. Nếu có custom `@TestExecutionListeners`, đã giữ recorder listener?
9. Có tránh rò rỉ dữ liệu giữa các test và giữa các Spring contexts?
10. Có dùng event ID/nguồn dữ liệu để phát hiện duplicate khi nghiệp vụ yêu cầu?

## 12. Câu hỏi tự đánh giá

**1. `@RecordApplicationEvents` thuộc thư viện nào?**  
Thuộc `spring-test` của Spring Framework, package `org.springframework.test.context.event`. Có thể dùng trong Spring Boot nhưng không phải API chỉ dành cho Boot.

**2. Muốn đếm `OrderPlaced` đã được publish trong test, dùng API nào?**  
`events.stream(OrderPlaced.class).count()`; nó lọc cả event type và payload phù hợp.

**3. Vì sao không nên assert `events.stream().count() == 1`?**  
Vì stream không có tham số chứa mọi `ApplicationEvent` được recorder thu thập, có thể gồm sự kiện framework và các event khác không thuộc nghiệp vụ.

**4. `events.clear()` xóa điều gì?**  
Xóa lịch sử event **được ghi nhận trong recorder hiện tại**; không xóa dữ liệu hoặc hoàn tác side effects.

**5. Một `@Transactional` test có event ghi nhận và listener `AFTER_COMMIT`. Tại sao listener không chạy?**  
Vì Spring test transaction mặc định rollback khi test kết thúc; event được publish vẫn được recorder ghi nhận, nhưng không có commit thành công.

**6. Có thể inject `ApplicationEvents` vào constructor test class không?**  
Không phù hợp; dependency có scope vòng đời test method. Dùng tham số của `@Test`/lifecycle method hoặc `@Autowired` field.

**7. Tại sao test async không nên dựa riêng vào `@RecordApplicationEvents`?**  
Recorder có phạm vi test lifecycle và context/thread nhất định; event async có thể xuất hiện muộn hoặc ngoài context đó. Cần điểm đồng bộ và assertion riêng cho side effect.

**8. `@RecordApplicationEvents` có tự lưu event vào Kafka hoặc outbox không?**  
Không. Đây là công cụ **kiểm thử in-memory Spring application event publication**, không phải hạ tầng giao nhận production.

## 13. Tài liệu chính thức

- [Spring Framework Reference — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework Reference — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework Javadoc — `RecordApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html)
- [Spring Framework Javadoc — `ApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework Reference — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide — Spring integration sử dụng JUnit Jupiter](https://junit.org/junit5/docs/current/user-guide/)

