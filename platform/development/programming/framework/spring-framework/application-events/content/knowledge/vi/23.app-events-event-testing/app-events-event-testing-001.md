# Kiểm thử publisher phát đúng event trong Spring Framework

## 1. Mục tiêu của bài kiểm thử

Trong Spring Framework, `ApplicationEventPublisher` giúp một thành phần công bố sự kiện mà không cần gọi trực tiếp tất cả consumer:

```java
publisher.publishEvent(new OrderPlaced(orderId, quantity));
```

Điều quan trọng khi kiểm thử không chỉ là xác minh dòng code `publishEvent(...)` từng chạy. Một bài test chất lượng cần trả lời **publisher có công bố đúng sự kiện theo hợp đồng nghiệp vụ hay không**:

1. **Đúng loại event:** `OrderPlaced`, không phải `OrderCancelled` hoặc một loại quá chung chung.
2. **Đúng payload:** `orderId`, số lượng, version, `eventId` và những giá trị có ý nghĩa đã được ánh xạ chính xác.
3. **Đúng số lần phát:** đúng một lần cho một hành động thành công; không vô tình phát trùng.
4. **Đúng điều kiện:** dữ liệu không hợp lệ hoặc thao tác thất bại trước điểm phát thì không công bố sự kiện thành công.
5. **Đúng mốc thời gian/ngữ cảnh:** cần biết event được phát ngay khi thực hiện command hay chỉ khi commit thành công.
6. **Đúng ranh giới kiểm thử:** mock publisher chỉ xác minh **lời gọi Java**; Spring Test ghi nhận event để kiểm chứng **sự kiện thực tế được công bố trong `ApplicationContext`**.

Bài này thuộc nhóm **Kiểm thử event** của chủ đề **Spring Framework Application Events**. Ví dụ chính dùng Java 17+, Spring Framework 6.2.12, JUnit Jupiter và Mockito, không cần Spring Boot, HTTP server hoặc database.

## 2. `publishEvent(...)` thực sự xác nhận điều gì?

`ApplicationEventPublisher` có API với hai overload quan trọng:

```java
void publishEvent(ApplicationEvent event);
void publishEvent(Object event);
```

Đây là **chữ ký API minh họa**, nằm trong `org.springframework.context.ApplicationEventPublisher`. Event có thể là một class kế thừa `ApplicationEvent` hoặc một object/record Java thông thường.

Ví dụ:

```java
public record OrderPlaced(String orderId, int quantity) {}

publisher.publishEvent(new OrderPlaced("O-101", 3));
```

Với một record không kế thừa `ApplicationEvent`, overload `publishEvent(Object)` được sử dụng. Khi Spring dispatch sự kiện kiểu object, hạ tầng có thể bọc nó trong `PayloadApplicationEvent`, nhưng consumer `@EventListener` khai báo tham số `OrderPlaced` vẫn có thể nhận **payload `OrderPlaced`**, và `ApplicationEvents.stream(OrderPlaced.class)` của Spring Test có thể lọc chính các payload đó.

Cần hiểu giới hạn:

- `publishEvent(...)` là **`void`**. Nó không trả kết quả hoặc số lượng listener thành công.
- Với multicaster mặc định đồng bộ, listener thường được xử lý trên thread publisher.
- Khi cấu hình multicaster bất đồng bộ, `@Async`, hoặc listener theo pha transaction, `publishEvent()` có thể trả về **trước khi hậu xử lý hoàn thành**.
- Test xác minh publisher đã gọi đúng event **không chứng minh** email, DB write hoặc HTTP request trong listener đã thành công.
- Nếu listener đồng bộ có exception và không có error handler nuốt lỗi, exception có thể lan ngược về publisher. Do đó cần tách rõ test publisher, test listener và test toàn luồng.

**Hợp đồng cần kiểm thử** nên được viết thành một câu: "Khi submit đơn hợp lệ với ID và số lượng xác định, publisher phát **chính xác một** `OrderPlaced` có dữ liệu đúng; khi dữ liệu không hợp lệ, không phát `OrderPlaced`."

## 3. Hai cấp độ kiểm thử bổ sung cho nhau

| Phương pháp | Kiểm tra được | Không tự chứng minh |
| --- | --- | --- |
| **Unit test** mock `ApplicationEventPublisher` bằng Mockito | Service đã gọi publisher đúng loại event, payload, số lần và điều kiện | Spring event infrastructure, component scan, listener registration, transaction phase |
| **Integration test** với `@RecordApplicationEvents` và `ApplicationEvents` | Event thực sự đã được công bố trong `ApplicationContext` Spring trong phạm vi test method | Tác vụ listener async hoàn thành, side effect ngoài hệ thống thành công, event bền vững sau crash |
| **Listener/flow integration test** | Handler được gọi và trạng thái cuối được tạo theo contract cụ thể | Mọi lỗi hạ tầng production, đặc biệt broker/DB ngoài test |
| **End-to-end test** | Toàn bộ quy trình từ API đến DB/broker/consumer | Không thay thế test unit nhỏ, nhanh, xác định nguyên nhân lỗi |

**Không chọn một trong hai theo kiểu loại trừ:** unit test bắt được lỗi ánh xạ dữ liệu tại service rất nhanh; integration test đảm bảo đường publish Spring hoạt động như mong đợi.

Một nhầm lẫn phổ biến là viết:

```java
verify(publisher).publishEvent(any());
```

Nếu không kiểm soát overload, event type và payload, kiểm thử chỉ chứng minh **một lời gọi mơ hồ** đã xảy ra. Ví dụ service phát `OrderCancelled` thay vì `OrderPlaced` có thể vẫn qua test quá lỏng. Cần dùng `ArgumentCaptor` hoặc so khớp đối tượng/value object cụ thể.

## 4. Ví dụ đầy đủ Java 17+: unit test và integration test cho cùng publisher

Dự án này cố ý nhỏ để chạy được trên một máy có JDK 17+ và Gradle 8+.

Nó gồm một service:

- `submit("O-41", 3)` phát `OrderPlaced("O-41", 3)` và trả ID.
- ID rỗng hoặc quantity không dương làm phương thức ném `IllegalArgumentException` **trước khi** gọi publisher.
- Không có repository/database: bài tập chỉ đo lường chính xác hành vi publish, tránh trộn với DB rollback khi chưa cần.

Hai test class sẽ xác minh **năm test cases**:

- 2 unit tests bằng Mockito;
- 3 integration tests bằng Spring Test `@RecordApplicationEvents`.

### 4.1. Cấu trúc thư mục

```text
publisher-event-tests/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/OrderWorkflow.java
    └── test/java/demo/
        ├── OrderPublisherUnitTest.java
        └── OrderEventsIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'publisher-event-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testImplementation 'org.mockito:mockito-core:5.15.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Phiên bản:** Các tọa độ dependency này minh họa một bộ Spring Framework 6.2.x và Java 17 tương thích. Trong dự án thật, nên dùng dependency management/BOM để nhất quán phiên bản Spring/JUnit. `spring-test` ở `testImplementation` vì chỉ dùng trong test; Mockito cũng không xuất hiện trong source production.

Đây là dự án Java, không có plugin Spring Boot. `gradle test` sẽ tạo classpath main và test, chạy JUnit Jupiter bằng JUnit Platform.

### 4.2. `src/main/java/demo/OrderWorkflow.java`

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class OrderWorkflow {

    private OrderWorkflow() {
    }

    // Event là immutable value object.
    public record OrderPlaced(String orderId, int quantity) {}

    // Event khác để kiểm tra không phát nhầm loại.
    public record OrderCancelled(String orderId) {}

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public String submit(String orderId, int quantity) {
            if (orderId == null || orderId.isBlank()
                    || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            publisher.publishEvent(
                    new OrderPlaced(orderId, quantity));
            return orderId;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }
}
```

Giải thích:

- `OrderPlaced` là Java record. Record được so sánh bằng **giá trị** (`equals`) của các component, rất thuận tiện cho assertions.
- Service nhận `ApplicationEventPublisher` qua constructor, nên **có thể test unit bằng mock** mà không dựng Spring context.
- `submit(...)` validate **trước khi publish**. Test invalid input phải chứng minh không có event thành công được phát.
- `OrderCancelled` chỉ làm đối chứng loại event; service này **không** bao giờ công bố `OrderCancelled`.
- `@Configuration` cung cấp bean service cho integration test. Không có `@ComponentScan` nên không phụ thuộc cấu trúc package ngoài ba file trong dự án.
- Publisher được Spring context cung cấp dưới dạng dependency; không phải tự tạo bean publisher.

Trong ứng dụng thực tế, ID và thông tin event thường xuất phát từ aggregate hoặc kết quả persistence. Event nên là immutable DTO/snapshot, tránh truyền nguyên entity mutable hoặc object gắn request.

### 4.3. Unit test — `src/test/java/demo/OrderPublisherUnitTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class OrderPublisherUnitTest {

    @Test
    void publishesOneCorrectOrderPlacedEvent() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);

        OrderWorkflow.OrderService service =
                new OrderWorkflow.OrderService(publisher);

        String result = service.submit("O-41", 3);

        ArgumentCaptor<OrderWorkflow.OrderPlaced> captor =
                ArgumentCaptor.forClass(
                        OrderWorkflow.OrderPlaced.class);

        verify(publisher, times(1))
                .publishEvent(captor.capture());

        OrderWorkflow.OrderPlaced event =
                captor.getValue();

        assertEquals("O-41", result);
        assertEquals(
                new OrderWorkflow.OrderPlaced("O-41", 3),
                event);
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidInputDoesNotCallPublisher() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);

        OrderWorkflow.OrderService service =
                new OrderWorkflow.OrderService(publisher);

        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.submit("O-42", 0));

        assertEquals("invalid order", ex.getMessage());
        verifyNoInteractions(publisher);
    }
}
```

**Tại sao đây là unit test mạnh hơn `verify(publisher).publishEvent(any())`?**

- `ArgumentCaptor<OrderPlaced>` buộc Java nhận đúng loại event khi test quan sát lời gọi.
- `assertEquals(new OrderPlaced("O-41", 3), event)` xác minh cả **type** và **giá trị của từng field**, nhờ `record.equals`.
- `times(1)` xác minh **không phát trùng cùng lời gọi đó**.
- `verifyNoMoreInteractions(publisher)` xác minh không có lời gọi publisher bổ sung nào ngoài lời gọi đã được verify.
- Test invalid dùng `verifyNoInteractions(...)` để chứng minh **không hề gọi publisher**.
- Service được tạo bằng `new`, không có Spring container: test tập trung thuần vào **logic publisher invocation**.

**Lưu ý về overload:** `OrderPlaced` là record không kế thừa `ApplicationEvent`, nên đoạn `publishEvent(captor.capture())` kiểm tra overload `publishEvent(Object)` của API. Nếu thay bằng subclass `ApplicationEvent`, Mockito verification cần phù hợp overload và kiểu truyền thực tế; tránh so khớp nhầm sang overload không được gọi.

## 5. Integration test bằng `@RecordApplicationEvents`

Spring TestContext Framework cung cấp:

- `@RecordApplicationEvents` (package `org.springframework.test.context.event`): yêu cầu ghi nhận application events được publish trong phạm vi một test.
- `ApplicationEvents`: API truy xuất sự kiện đã ghi nhận như một `Stream`.
- `ApplicationEventsTestExecutionListener`: thiết lập/bảo trì recorder trong TestContext; **được đăng ký mặc định** nếu bạn không thay toàn bộ danh sách TestExecutionListener.
- `@SpringJUnitConfig`: kết hợp SpringExtension và cấu hình context cho JUnit Jupiter.

Ví dụ:

```java
events.stream(OrderWorkflow.OrderPlaced.class).toList();
```

Dòng này lấy các **event hoặc payload** có kiểu `OrderPlaced`. Với `publisher.publishEvent(new OrderPlaced(...))`, Spring có thể bọc object bằng `PayloadApplicationEvent` cho dispatch, nhưng `ApplicationEvents.stream(OrderPlaced.class)` vẫn là API phù hợp để test event payload theo type.

### 5.1. `src/test/java/demo/OrderEventsIntegrationTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(OrderWorkflow.Config.class)
@RecordApplicationEvents
class OrderEventsIntegrationTest {

    @Autowired
    OrderWorkflow.OrderService service;

    @Test
    void successfulSubmitPublishesExactEvent(
            ApplicationEvents events) {

        String id = service.submit("O-41", 3);

        List<OrderWorkflow.OrderPlaced> published =
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .toList();

        assertEquals("O-41", id);
        assertEquals(1, published.size());
        assertEquals(
                new OrderWorkflow.OrderPlaced("O-41", 3),
                published.get(0));

        // Không phát nhầm loại event nghiệp vụ khác.
        assertEquals(0,
                events.stream(OrderWorkflow.OrderCancelled.class)
                        .count());
    }

    @Test
    void invalidSubmitPublishesNoSuccessEvent(
            ApplicationEvents events) {

        assertThrows(
                IllegalArgumentException.class,
                () -> service.submit("O-42", 0));

        assertEquals(0,
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .count());
    }

    @Test
    void twoValidSubmitsPublishTwoCorrectPayloads(
            ApplicationEvents events) {

        service.submit("O-1", 1);
        service.submit("O-2", 2);

        List<OrderWorkflow.OrderPlaced> expected = List.of(
                new OrderWorkflow.OrderPlaced("O-1", 1),
                new OrderWorkflow.OrderPlaced("O-2", 2));

        List<OrderWorkflow.OrderPlaced> actual =
                events.stream(OrderWorkflow.OrderPlaced.class)
                        .toList();

        assertEquals(2, actual.size());
        assertIterableEquals(expected, actual);
    }
}
```

**Giải thích từng test:**

- `successfulSubmitPublishesExactEvent`: service là Spring bean thật và publisher là implementation trong context. `ApplicationEvents` xác minh event đã được công bố. Kiểm tra đúng loại, đúng `orderId`, đúng số lượng, đúng số lần và không có `OrderCancelled`.
- `invalidSubmitPublishesNoSuccessEvent`: kiểm tra đường lỗi. Đúng hành vi không phải luôn "có event", mà là **không công bố event thành công khi validate thất bại**.
- `twoValidSubmitsPublishTwoCorrectPayloads`: kiểm tra hai hành động độc lập và hai payload tương ứng. Với publisher và multicaster đồng bộ mặc định trong ví dụ, thứ tự hai event được ghi nhận theo thứ tự gọi `submit` trong test thread.

`ApplicationEvents events` được SpringExtension cung cấp qua **tham số của test method**. Cách này được tài liệu Spring khuyến nghị vì recorder có phạm vi **theo từng test method**. Không nên inject `ApplicationEvents` vào constructor của test class; nó không được sử dụng ngoài lifecycle của method test.

Nếu muốn dùng field:

```java
@Autowired
ApplicationEvents events;
```

Đây là đoạn minh họa thay thế method parameter. Tài liệu Spring cho phép cách này nhưng vẫn yêu cầu truy cập khi test method đang hoạt động. Không giữ `ApplicationEvents` trong singleton application bean hoặc trong static field để dùng qua nhiều test.

### 5.2. Chạy cả năm test cases

Tại thư mục dự án có `build.gradle`, chạy:

```bash
gradle clean test
```

Nếu dùng Gradle Wrapper, chạy `./gradlew clean test` trên Linux/macOS hoặc `gradlew.bat clean test` trên Windows. Dự án mẫu chưa kèm wrapper.

**Kết quả mong đợi:** Gradle/JUnit Jupiter chạy **5 test methods**, không có assertion thất bại và tác vụ `test` thành công. Dòng báo thành công của Gradle có thể là `BUILD SUCCESSFUL`, nhưng thời gian, task up-to-date, thứ tự các test và định dạng console phụ thuộc môi trường; **không có một stdout cố định cần sao chép để test được coi là thành công**.

Có thể xem HTML report ở:

```text
build/reports/tests/test/index.html
```

Report này do Gradle tạo, không phải file mà ví dụ yêu cầu bạn soạn tay. Nếu một test không tìm được context hoặc không ghi event, hãy kiểm tra annotation/package, resource và danh sách `TestExecutionListener` trước khi kết luận publisher sai.

## 6. Các khía cạnh cần xác minh trong một event contract

Ví dụ mã kiểm thử bên trên chưa có timestamp hoặc event ID. Ở dự án thực tế, payload thường giàu thông tin hơn:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        long aggregateVersion,
        String customerId,
        int quantity,
        Instant occurredAt) {}
```

Đây là đoạn định nghĩa **minh họa** riêng, không thay thế record `OrderPlaced` trong dự án chạy được ở mục 4. Cần import `java.time.Instant`.

Đừng chỉ dùng:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

Tất nhiên kiểm tra số lượng là hữu ích, nhưng nếu publisher phát đúng một event với **sai customer hoặc quantity**, test vẫn qua. Hãy kiểm tra toàn bộ trường quan trọng:

```java
OrderPlaced event = events.stream(OrderPlaced.class)
        .findFirst()
        .orElseThrow();

assertEquals("O-41", event.orderId());
assertEquals("C-9", event.customerId());
assertEquals(3, event.quantity());
assertEquals(7L, event.aggregateVersion());
```

Đoạn code trên là **minh họa**, giả định `OrderPlaced` là record mở rộng và event đã được ghi nhận. Với `eventId` sinh ngẫu nhiên/UUID và `occurredAt` từ clock, dùng `Clock` được inject hoặc kiểm tra tính hợp lệ thay vì so sánh timestamp với `Instant.now()` tại một thời điểm khác.

Cấu trúc test nên phản ánh contract:

| Điều kiện | Kiểm tra |
| --- | --- |
| Submit hợp lệ | Đúng một `OrderPlaced` |
| Submit không hợp lệ | Không có `OrderPlaced` thành công |
| Xử lý hai submit khác nhau | Hai event có ID/payload riêng |
| Hành động bị từ chối | Không phát event thành công; event failure chỉ khi contract yêu cầu |
| Thay đổi trạng thái từ A sang B | Event chứa old/new state, version đúng |
| Event chứa collection | Payload là snapshot bất biến; không bị đổi khi entity nguồn tiếp tục mutate |
| Có publish trùng cùng ID | Assert `times(1)` hoặc thiết kế idempotency và test duplicate semantics |
| Có event cùng type từ nơi khác | Lọc theo `orderId`/eventId, không lấy bất kỳ event cùng type để kết luận |

Tách **điều kiện đầu vào**, **event type**, **payload** và **số lần phát** thành assertions rõ ràng sẽ cho thông báo lỗi hữu ích hơn một assertion mơ hồ.

## 7. Chỉ ghi nhận event được publish, không tự chứng minh listener đã xử lý xong

Cần phân biệt ba mốc:

```text
Publisher tạo Event
    |
    +-- publishEvent(Event)
          |
          +-- ApplicationEvents recorder: event đã được công bố
          |
          +-- Listener đồng bộ: xử lý ngay theo multicaster mặc định
          |
          +-- Listener @Async: có thể mới được submit vào executor
          |
          +-- @TransactionalEventListener(AFTER_COMMIT):
                 có thể chỉ mới đăng ký chờ commit
```

Vì vậy:

```java
assertEquals(1, events.stream(OrderPlaced.class).count());
```

**Không tương đương** với:

```text
email đã gửi thành công
payment đã capture
audit row đã commit
listener đã hoàn tất
```

Trong Spring Test, `@RecordApplicationEvents` dành cho việc ghi **những sự kiện được publish trong context**. Muốn test listener, hãy làm test riêng với state/spy/DB hoặc một observer xác định đã chạy.

Đối với async listener, dùng `CountDownLatch`, `CompletableFuture`, Awaitility hay tín hiệu trạng thái có timeout. Không dùng `Thread.sleep(100)` rồi hy vọng worker chạy xong. Nếu service cần bảo đảm giao hàng qua process restart, Spring Application Events trong bộ nhớ không thay thế event store, outbox hoặc message broker.

### Khi có `@Async`

ApplicationEvents recorder có phạm vi test thread và các luồng phù hợp với test context; **không nên mặc định nó ghi được mọi event phát từ thread pool bất kỳ**, đặc biệt khi thread pool đã được tạo từ trước và không mang context TestContext tương ứng. Cách chắc chắn là test trực tiếp publisher bằng mock ở unit test, và test đường consumer async bằng một cơ chế observer/latch do test quản lý.

Nếu cần assert chuỗi event A → B phát ở worker, observer được đăng ký trong context có thể capture B một cách chủ động và báo latch. Đừng suy luận "đã publish A" nghĩa là B chắc chắn đã xuất hiện ngay khi assertion chạy.

## 8. Transaction: event được publish không có nghĩa transaction đã commit

Ví dụ:

```java
@Transactional
public void createOrder(OrderCommand command) {
    repository.save(toEntity(command));
    publisher.publishEvent(new OrderPlaced(command.id(), 2));
    // Một exception xuất hiện sau đây có thể làm transaction rollback.
}
```

Đây là đoạn minh họa; `repository`, `OrderCommand` và `toEntity(...)` thuộc code ứng dụng, không phải phần của dự án runnable.

Một `@RecordApplicationEvents` test có thể ghi nhận `OrderPlaced` **ngay khi publisher được gọi**, rồi transaction vẫn rollback. Do đó phải phân biệt:

- **Kiểm thử publisher:** xác minh service phát đúng event tại thời điểm gọi.
- **Kiểm thử transaction outcome:** xác minh DB commit hoặc rollback theo contract.
- **Kiểm thử listener hậu commit:** xác minh `@TransactionalEventListener(AFTER_COMMIT)` chỉ xử lý event khi transaction commit thành công.

Cấu trúc event listener minh họa:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Chỉ chạy sau commit thành công của transaction
    // đã đăng ký event, không phải ngay khi publishEvent().
}
```

Với `@TransactionalEventListener`, nếu không có transaction phù hợp khi event được phát, listener mặc định không chạy (`fallbackExecution=false`). Đừng dùng "không thấy listener chạy" làm bằng chứng rằng service không phát event; có thể event **đã được publish nhưng không có transaction để đăng ký callback**.

### Bẫy test có `@Transactional`

Spring Test thường rollback transaction của test method theo mặc định. Nếu test được annotate `@Transactional` và gọi service rồi kiểm tra listener `AFTER_COMMIT` ngay trước khi transaction kết thúc, callback **chưa chạy**. Đến cuối test, test transaction có thể rollback, nên listener không được gọi.

Khi cần kiểm thử commit thực, dùng `TestTransaction` để chủ động hoàn tất:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Lúc này kiểm tra DB hoặc listener hậu commit.
```

Đây là đoạn minh họa, yêu cầu test đang trong transaction do Spring Test quản lý và import `org.springframework.test.context.transaction.TestTransaction`. Không dùng nó trong ví dụ chính vì dự án chính cố tình không có database. Một lựa chọn khác là để test method **không** mở transaction mặc định, chỉ gọi service transactional; proxy service commit xong trước khi assertion về trạng thái DB.

Lưu ý quan trọng khi rollback một transaction: nếu event đã được publish **trước khi rollback**, assert `ApplicationEvents` vẫn có thể thấy nó. Test đúng cần chỉ rõ mình kiểm tra *publish* hay *commit-bound consumption*.

## 9. Phân biệt `ApplicationEvents` của Spring Test và các công cụ khác

Tên tương tự có thể gây nhầm:

- `ApplicationEventPublisher`: interface **production** dùng để công bố sự kiện.
- `ApplicationEvents` trong `org.springframework.test.context.event`: **Spring Test** API truy xuất các event được ghi trong test.
- `ApplicationListener<T>`: handler **production** theo event type.
- `@EventListener`: annotation handler theo method.
- `@TransactionalEventListener`: handler được gắn với transaction phase.
- `PayloadApplicationEvent<T>`: wrapper cho payload object event.
- `ApplicationEventMulticaster`: hạ tầng dispatch tới listeners.

`@RecordApplicationEvents` không tự tạo event và cũng không thay thế `ApplicationEventPublisher`. Nó chỉ giúp **quan sát những event được phát**, tránh viết một listener test thủ công trong các trường hợp đơn giản.

Có thể dùng `ApplicationEvents.clear()` để xóa những event đã ghi trong **test method hiện tại** nếu muốn bắt đầu một vùng quan sát mới. Tuy nhiên, đừng gọi `clear()` bừa bãi làm che lỗi có thêm event ngoài mong đợi trước đó. Trong ví dụ, mỗi test method được quản lý recorder riêng nên không cần `clear()`.

### Điều gì xảy ra khi dùng `@TestExecutionListeners` tùy biến?

`ApplicationEventsTestExecutionListener` thuộc bộ listener mặc định của Spring Test. Nếu test class đặt:

```java
@TestExecutionListeners(
        listeners = CustomListener.class,
        mergeMode = TestExecutionListeners.MergeMode
                .MERGE_WITH_DEFAULTS)
```

Đây là **đoạn minh họa**; `CustomListener` là lớp test utility do dự án định nghĩa, chưa có trong ví dụ runnable. Sử dụng `MERGE_WITH_DEFAULTS` giúp giữ các listeners mặc định, trong đó có listener hỗ trợ ghi Application Events. Nếu bạn **thay thế toàn bộ** danh sách mặc định và quên thêm `ApplicationEventsTestExecutionListener`, `@RecordApplicationEvents` có thể không hoạt động như mong đợi.

Không cần tự khai báo `ApplicationEventsTestExecutionListener` khi bạn dùng TestContext mặc định như ví dụ.

## 10. Những lỗi thường gặp khi viết test publisher

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ viết `verify(publisher).publishEvent(any())` | Không kiểm tra event type và payload; có thể khớp sai overload | Dùng typed `ArgumentCaptor` hoặc so khớp value object |
| Chỉ assert `count() == 1` | Event có thể sai field quan trọng | Kiểm tra `orderId`, quantity, version, eventId |
| Chỉ assert event có xuất hiện ít nhất một lần | Không bắt được publish trùng | Assert exact count và no-more-interactions nếu unit test |
| Đoán event type là `ApplicationEvent` subclass | Object payload thường được Spring bọc bằng `PayloadApplicationEvent` | Dùng `events.stream(MyPayload.class)` để lọc payload |
| Assert event xuất hiện trước khi kích hoạt action | Test setup/previous event bị tính vào kết quả | Lọc đúng event type/id; chú ý scope recorder từng method |
| Dùng mock publisher rồi tuyên bố Spring đã dispatch | Mockito chỉ thấy lời gọi method trên mock | Thêm integration test với `@RecordApplicationEvents` |
| Đọc `ApplicationEvents` từ constructor test | Recorder là method-scoped, chưa sẵn sàng ở constructor | Inject vào `@Test` method hoặc field `@Autowired` |
| Mất recorder khi tùy biến TestExecutionListeners | Đã bỏ các listeners mặc định | Dùng `MERGE_WITH_DEFAULTS` hoặc khai báo đúng listener |
| Test transaction rollback nhưng chờ `AFTER_COMMIT` | Callback chỉ xảy ra sau commit thành công | Chủ động commit/kết thúc transaction test theo contract |
| Event publish trước rollback vẫn có trong recorder | Recorder đo publish, không đo commit | Tách assertion publish khỏi assertion hậu commit |
| Test async dùng `Thread.sleep` | Kết quả flake theo scheduler | Dùng latch/future/await với timeout |
| Listener xử lý event cùng type nhiều lần | Có chain/republication hoặc nhiều publisher cùng type | Lọc eventId, kiểm tra đường publish và số lần |

## 11. Thiết kế test ổn định trong ứng dụng lớn

### 11.1. Tạo event từ dữ liệu xác định

Nếu event có `occurredAt`, hãy inject `Clock` để thay `Instant.now()` trực tiếp:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC);
```

Đây là mã minh họa, cần import `java.time.Clock`, `java.time.Instant`, `java.time.ZoneOffset`. Khi service dùng fixed clock, timestamp có thể được assert chính xác. Với UUID ngẫu nhiên, có thể inject `Supplier<UUID>`/factory để test dùng ID cố định, hoặc chỉ kiểm tra uniqueness và correlation theo contract.

### 11.2. Không chuyển event mutable vào test async

Nếu event chứa entity hoặc request object, việc test `@RecordApplicationEvents` đã thấy payload đúng lúc publish **không chứng minh** object ấy còn giữ nguyên khi listener async đọc. Với payload cần snapshot, test:

```text
create immutable event snapshot
publish event
mutate source entity
assert snapshot vẫn giữ giá trị ban đầu
```

Làm defensive copy cho nested collections và các phần tử mutable, không chỉ bọc bên ngoài bằng Java record. Điều này giúp event contract bền vững hơn khi thay multicaster hoặc thêm async listeners.

### 11.3. Parent/child contexts

Spring Application Events từ child context có thể propagate lên parent. Một recorder/listener ở parent có thể quan sát những event phát từ child, làm count bất ngờ tăng. Trong ứng dụng có nhiều context, test nên xác định **nguồn context** và chỉ lọc đúng event thuộc phạm vi cần xác minh.

Không dùng "có đúng một event trong toàn bộ application" làm assumption khi ứng dụng Boot/MVC có nhiều context, các library phát event startup, hoặc listener khác republish sự kiện. Hãy lọc **event type + ID nghiệp vụ/correlation**.

### 11.4. Mỗi test một phạm vi độc lập

Dù Spring Test thường cache `ApplicationContext` giữa test methods, recorder `ApplicationEvents` có phạm vi từng test method. Vì vậy đừng lưu giá trị `ApplicationEvents` trong singleton bean/static field; sử dụng method parameter cho đơn giản.

Với Mockito unit test, tạo một mock publisher mới trong từng test như ví dụ. Nếu dùng `@BeforeEach` và chia sẻ mock, `reset(...)` chỉ khi có lý do rõ; tránh cross-test contamination. Với event async, cleanup executor/future theo test framework để không còn task ảnh hưởng các test sau.

### 11.5. Chú ý điều gì không phải phạm vi unit test publisher

Một unit test mock publisher không xác minh:

- `@EventListener` được Spring đăng ký đúng type;
- listener `@Order` chạy theo thứ tự mong muốn;
- `@Async` proxy thực sự gọi executor;
- transaction commit/rollback thực sự xảy ra;
- DB insert/HTTP/email/broker hoàn tất;
- event được lưu/replay qua restart.

Các yêu cầu đó thuộc integration test hoặc end-to-end test. Giữ unit test nhỏ để chỉ một lý do làm test thất bại: service không phát event đúng hợp đồng.

## 12. Checklist áp dụng

Trước khi hoàn tất bài kiểm thử event publisher, tự kiểm tra:

- **Trigger:** đã thực sự gọi hành động nghiệp vụ cần phát event chưa?
- **Type:** đã xác minh đúng class/record event cụ thể chưa?
- **Count:** đã kiểm tra đúng số lần phát, không phát trùng chưa?
- **Payload:** đã kiểm tra mọi field quan trọng, không chỉ có event tồn tại chưa?
- **Negative path:** đầu vào không hợp lệ/thao tác thất bại trước publish có không phát sự kiện thành công không?
- **Overload:** Mockito đang verify đúng `publishEvent(Object)` hay `publishEvent(ApplicationEvent)`?
- **Spring integration:** đã có test với context thật hoặc `@RecordApplicationEvents` khi cần kiểm tra đường dispatch?
- **Async:** đã dùng cơ chế chờ xác định nếu test listener async chưa?
- **Transaction:** đã tách "đã publish" khỏi "đã commit" và hậu commit chưa?
- **Isolation:** test method có recorder/mock riêng và không bị context event khác làm nhiễu không?
- **Event contract:** payload immutable, không giữ object phụ thuộc request/thread/persistence context?

**Kết luận:** Để kiểm thử publisher phát đúng event, hãy dùng **typed `ArgumentCaptor` của Mockito** trong unit test để xác minh loại event, payload, số lần và đường lỗi; dùng **`@RecordApplicationEvents` + `ApplicationEvents.stream(EventType.class)`** trong Spring Test để xác minh event được công bố thực sự trong `ApplicationContext`. Tách rõ việc **publish** khỏi việc listener hoàn tất hoặc transaction commit; điều đó giúp test vừa chính xác vừa ít flaky.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — `ApplicationEvents` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito — ArgumentCaptor](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/ArgumentCaptor.html)
