# Bảo đảm test fail khi verification không xảy ra

## 1. Một test “xanh” phải chứng minh được điều gì?

Trong JUnit Jupiter, một phương thức `@Test` **không bắt buộc có assertion**. Nếu method chạy đến cuối mà không ném lỗi, JUnit có thể báo **passed** dù test chưa kiểm chứng bất cứ hợp đồng nghiệp vụ nào. Vấn đề này đặc biệt nguy hiểm ở Spring Modulith: context khởi động được, bean chạy được hoặc event được lọc ra **không có nghĩa** yêu cầu đã được kiểm chứng.

Ví dụ **test xanh giả**:

```java
@Test
void orderShouldPublishEvent(PublishedEvents events) {
    orders.place(id, "SKU-READY", 2);
    events.ofType(OrderPlaced.class)
          .matching(OrderPlaced::orderId, id);
    // Không có assertion: lọc event chỉ trả về một đối tượng Iterable.
}
```

Nếu production code bỏ hoàn toàn `publishEvent(...)`, đoạn test vẫn có thể passed. Cũng tương tự nếu ta viết `given(stock.available(...)).willReturn(true)` nhưng không có `then(stock).should()...`; **stubbing không phải verification**.

**Yêu cầu của một testcase đáng tin:** Khi hậu điều kiện mà tên test tuyên bố **không xảy ra**, testcase phải **thất bại quan sát được bởi JUnit runner và CI**. Có thể đạt điều đó bằng assertion, Mockito verification, một terminal operation của `Scenario` hoặc phép kiểm tra tương đương **thực sự được thực thi**.

Bài này thuộc chương **JUnit integration** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**: kiểm chứng ranh giới với `ApplicationModules`, thực hành `@ApplicationModuleTest`, event, cơ sở dữ liệu và integration, kết hợp quality gate trong CI. Trọng tâm không phải toàn bộ JUnit API mà là **đường đi từ stimulus đến failure signal** khi verification bị bỏ quên.

### Bản đồ các “khoảng trống verification”

| Mẫu code | Vì sao có thể xanh giả? | Cách làm test fail đúng lúc |
| --- | --- | --- |
| Method `@Test` chỉ gọi service | Không có hậu điều kiện nào được kiểm tra | Assert result/state hoặc tương tác cần thiết |
| `given(mock...).willReturn(...)` | Stub quyết định phản hồi; không chứng minh mock đã được gọi | `then(mock).should().method(...)` hoặc assert outcome |
| `events.ofType(...).matching(...)` | Mới lọc event, chưa kiểm tra có event | `assertThat(...).hasSize(1)` / `singleElement()` |
| `scenario.publish(...).forEventOfType(...)` | Chưa gọi **terminal operation** để thực thi scenario | `toArrive()` hoặc `toArriveAndVerify(...)` |
| `optional.ifPresent(value -> assert...)` | Khi rỗng, callback không chạy và không fail | `assertThat(optional).isPresent()` hoặc `hasValueSatisfying(...)` |
| `future.thenAccept(value -> assert...)` không đợi | Callback có thể chưa chạy khi JUnit kết thúc | Chờ future hoàn tất và để exception truyền về test |
| `latch.await(timeout, unit)` không assert kết quả | `await` trả `false` khi timeout, không tự ném AssertionError | `assertThat(awaited).isTrue()` |
| `@Tag("architecture")` trên method trống | Tag chỉ phân loại, không xác minh cấu trúc | Gọi `ApplicationModules.verify()` trong test được CI chọn |

**Phân biệt hai loại sai lầm:** *Verification chưa từng chạy* khác với *verification đã chạy nhưng chỉ kiểm tra điều kiện yếu*. Cả hai đều có thể tạo “passed” không đáng tin; cách sửa lần lượt là **buộc có điểm thực thi** và **đặt assertion đúng hợp đồng**.

## 2. JUnit fail-closed: mọi nhánh kiểm chứng phải có kết quả

### `assertThrows` so với `try/catch` bỏ qua lỗi

Nếu hợp đồng là “input sai phải ném `IllegalArgumentException`”, đoạn sau **không đủ**:

```java
@Test
void rejectsInvalidOrder_BAD() {
    try {
        orders.place(id, "SKU-READY", 0);
    } catch (IllegalArgumentException ignored) {
        // Nếu method KHÔNG ném gì, test vẫn chạy đến cuối và passed.
    }
}
```

Đổi thành một assertion có thể thất bại:

```java
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> orders.place(id, "SKU-READY", 0));
assertThat(error).hasMessage("INVALID_ORDER");
```

Nếu service không ném exception, `assertThrowsExactly` **fail**. Nếu service ném sai type hoặc sai message, test cũng fail. Với hợp đồng chấp nhận subtype, dùng `assertThrows` thay vì `assertThrowsExactly`; chọn theo nghiệp vụ.

### Callback tùy chọn không phải assertion về sự tồn tại

```java
// SAI: Optional.empty() sẽ không chạy callback và không fail.
store.findById(id).ifPresent(record ->
        assertThat(record.quantity()).isEqualTo(2));

// ĐÚNG: kiểm chứng cả việc record có tồn tại.
assertThat(store.findById(id))
        .as("Order %s phải được lưu", id)
        .hasValueSatisfying(record ->
                assertThat(record.quantity()).isEqualTo(2));
```

Tương tự, `stream.filter(...).findFirst()`, `anyMatch(...)` hoặc `Map.get(...)` chỉ **tính toán giá trị**. Chúng không fail nếu kết quả không được đem đi assert. Một phép `if (condition) assert...` mà không có nhánh `else` cũng dễ bỏ trống đường thất bại.

### `assertAll` và `assertDoesNotThrow` không tự sinh kỳ vọng

`assertAll("...", executables)` thực thi những assertion đã viết và gom lỗi; nó không phát hiện điều kiện nghiệp vụ mà bạn **chưa viết**. `assertDoesNotThrow(() -> orders.place(...))` chỉ chứng minh không có exception, **không** chứng minh record/event được tạo.

Khi kiểm chứng nhiều kết quả từ một stimulus:

```java
OrderReceipt receipt = orders.place(id, "SKU-READY", 2); // Act một lần.

assertAll("Hậu điều kiện nhận đơn",
    () -> assertThat(receipt.orderId()).isEqualTo(id),
    () -> assertThat(store.findById(id)).isPresent(),
    () -> assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, id)).hasSize(1)
);
```

Đoạn này là **trích đoạn bên trong testcase có `orders`, `store`, `events`, `id`**. Từng nhánh có phép assert có thể fail; không đặt stimulus có side effect ở bên trong từng lambda.

### `assumeTrue` và `@Disabled` không phải tín hiệu thất bại

`Assumptions.assumeTrue(...)` có thể **abort** testcase khi tiền điều kiện môi trường không đạt; kết quả không giống một assertion failure. `@Disabled` bỏ qua test. Không dùng chúng để che việc một verification bắt buộc bị thiếu. Nếu kiến trúc yêu cầu gate phải chạy, CI cần kiểm tra **số testcase được thực thi** và coi “0 architecture tests” là lỗi cấu hình.

## 3. Ứng dụng mẫu tối giản để nhận biết false-green

Ví dụ dùng **Java 17+, Spring Boot 3.4/3.5, Spring Framework 6.2, Spring Modulith 1.4, JUnit Jupiter 5**, với BOM tương thích. `@MockitoBean` thuộc Spring Framework 6.2. Ví dụ chính dùng store in-memory để tập trung vào verification; không tự tuyên bố kiểm chứng SQL transaction hay broker.

```text
src/main/java/com/example/shop/
  ShopApplication.java
  inventory/StockAvailability.java
  inventory/StockAvailabilityService.java
  order/OrderReceipt.java
  order/OrderRecord.java
  order/OrderPlaced.java
  order/OrderStore.java
  order/OrderService.java
src/test/java/com/example/shop/
  order/OrderVerificationTests.java
  ModuleArchitectureTests.java
```

Các Maven dependencies chính (bổ sung vào dự án đã có Spring Boot/Modulith dependency management):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

`src/main/java/com/example/shop/ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`src/main/java/com/example/shop/inventory/StockAvailability.java`:

```java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean available(String sku, int quantity);
}
```

`src/main/java/com/example/shop/inventory/StockAvailabilityService.java`:

```java
package com.example.shop.inventory;

import org.springframework.stereotype.Service;

@Service
public class StockAvailabilityService implements StockAvailability {
    @Override
    public boolean available(String sku, int quantity) {
        return "SKU-READY".equals(sku) && quantity <= 3;
    }
}
```

`src/main/java/com/example/shop/order/OrderReceipt.java`:

```java
package com.example.shop.order;

import java.util.UUID;

public record OrderReceipt(UUID orderId, String sku, int quantity) {}
```

`src/main/java/com/example/shop/order/OrderRecord.java`:

```java
package com.example.shop.order;

import java.util.UUID;

public record OrderRecord(UUID orderId, String sku, int quantity) {}
```

`src/main/java/com/example/shop/order/OrderPlaced.java`:

```java
package com.example.shop.order;

import java.util.UUID;

public record OrderPlaced(UUID orderId, String sku, int quantity) {}
```

`src/main/java/com/example/shop/order/OrderStore.java`:

```java
package com.example.shop.order;

import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {
    private final ConcurrentMap<UUID, OrderRecord> records =
            new ConcurrentHashMap<>();

    public void save(OrderRecord record) {
        if (records.putIfAbsent(record.orderId(), record) != null) {
            throw new IllegalStateException("DUPLICATE_ORDER");
        }
    }

    public Optional<OrderRecord> findById(UUID id) {
        return Optional.ofNullable(records.get(id));
    }

    public void deleteById(UUID id) {
        records.remove(id);
    }
}
```

`src/main/java/com/example/shop/order/OrderService.java`:

```java
package com.example.shop.order;

import java.util.UUID;
import com.example.shop.inventory.StockAvailability;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final StockAvailability stock;
    private final OrderStore store;
    private final ApplicationEventPublisher publisher;

    public OrderService(StockAvailability stock,
                        OrderStore store,
                        ApplicationEventPublisher publisher) {
        this.stock = stock;
        this.store = store;
        this.publisher = publisher;
    }

    public OrderReceipt place(UUID id, String sku, int quantity) {
        if (id == null || sku == null || sku.isBlank()
                || quantity < 1 || quantity > 3) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        if (!stock.available(sku, quantity)) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        store.save(new OrderRecord(id, sku, quantity));
        publisher.publishEvent(new OrderPlaced(id, sku, quantity));
        return new OrderReceipt(id, sku, quantity);
    }
}
```

Trong mô hình này, `order` phụ thuộc API **công khai** `StockAvailability` của module `inventory`. Ở `@ApplicationModuleTest` mặc định `STANDALONE`, implementation inventory sẽ được thay bằng `@MockitoBean`. Store là singleton in-memory nên cần cleanup theo ID của testcase. Nếu bỏ câu lệnh `publisher.publishEvent(...)`, chương tiếp theo sẽ cho thấy cách **bắt buộc test đỏ** thay vì xanh giả.

## 4. `@ApplicationModuleTest`: verification phải có assertion thực thi

File `src/test/java/com/example/shop/order/OrderVerificationTests.java`:

```java
package com.example.shop.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

import java.util.UUID;
import com.example.shop.inventory.StockAvailability;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Tag("module")
@DisplayName("Order: mỗi verification đều có đường thất bại")
@ApplicationModuleTest
class OrderVerificationTests {

    @Autowired OrderService orders;
    @Autowired OrderStore store;
    @MockitoBean StockAvailability stock;

    @Test
    @Tag("event")
    void orderMustPersistAndPublishExactlyOneMatchingEvent(
            PublishedEvents events) {
        // GIVEN
        UUID id = UUID.randomUUID();
        String sku = "SKU-READY";
        int quantity = 2;
        given(stock.available(sku, quantity)).willReturn(true);

        try {
            // WHEN: gọi use case thật đúng một lần.
            OrderReceipt receipt = orders.place(id, sku, quantity);

            // THEN: mỗi kỳ vọng bị phá phải tạo assertion/verification failure.
            var matchingEvents = events.ofType(OrderPlaced.class)
                    .matching(OrderPlaced::orderId, id);

            assertAll("Đơn hợp lệ cần đủ bốn hậu điều kiện",
                () -> assertThat(receipt)
                        .isEqualTo(new OrderReceipt(id, sku, quantity)),
                () -> assertThat(store.findById(id))
                        .contains(new OrderRecord(id, sku, quantity)),
                () -> then(stock).should()
                        .available(sku, quantity),
                () -> assertThat(matchingEvents)
                        .as("Phải publish đúng một OrderPlaced cho %s", id)
                        .singleElement()
                        .satisfies(event -> assertAll("Payload event",
                            () -> assertThat(event.sku()).isEqualTo(sku),
                            () -> assertThat(event.quantity())
                                    .isEqualTo(quantity)))
            );
        } finally {
            store.deleteById(id);
        }
    }

    @Test
    void invalidQuantityMustFailBeforeAnySideEffect(
            PublishedEvents events) {
        UUID id = UUID.randomUUID();

        try {
            // assertThrowsExactly đảm bảo test fail nếu exception KHÔNG xảy ra.
            var failure = assertThrowsExactly(
                    IllegalArgumentException.class,
                    () -> orders.place(id, "SKU-READY", 0));

            assertAll("Validation chặn trước boundary",
                () -> assertThat(failure)
                        .hasMessage("INVALID_ORDER"),
                () -> then(stock).shouldHaveNoInteractions(),
                () -> assertThat(store.findById(id)).isEmpty(),
                () -> assertThat(events.ofType(OrderPlaced.class)
                        .matching(OrderPlaced::orderId, id)).isEmpty()
            );
        } finally {
            store.deleteById(id);
        }
    }

    @Test
    void unavailableStockMustNotPublishOrPersist(
            PublishedEvents events) {
        UUID id = UUID.randomUUID();
        given(stock.available("SKU-OUT", 1)).willReturn(false);

        try {
            var failure = assertThrowsExactly(
                    IllegalStateException.class,
                    () -> orders.place(id, "SKU-OUT", 1));

            assertAll("Kho từ chối đơn",
                () -> assertThat(failure).hasMessage("OUT_OF_STOCK"),
                () -> then(stock).should().available("SKU-OUT", 1),
                () -> assertThat(store.findById(id)).isEmpty(),
                () -> assertThat(events.ofType(OrderPlaced.class)
                        .matching(OrderPlaced::orderId, id)).isEmpty()
            );
        } finally {
            store.deleteById(id);
        }
    }
}
```

### Thử hủy verification để xem testcase có đỏ không

Trong một nhánh thử nghiệm **có kiểm soát** (không commit mutation production), thay:

```java
publisher.publishEvent(new OrderPlaced(id, sku, quantity));
```

bằng:

```java
// Tạm bỏ publishEvent để kiểm chứng sức mạnh testcase.
// publisher.publishEvent(new OrderPlaced(id, sku, quantity));
```

Bài `orderMustPersistAndPublishExactlyOneMatchingEvent` phải fail ở assertion `singleElement()` vì **không có event** đúng `orderId`. Nếu testcase vẫn xanh, hãy kiểm tra rằng bạn có vô tình chỉ viết `events.ofType(...).matching(...)` mà không assert, đọc event cũ với ID cố định, hoặc test đã không được runner chọn.

Tương tự, thay quantity của event thành `quantity + 1` phải làm assertion payload fail, dù event vẫn cùng type và `orderId`. Vì vậy chỉ `isNotEmpty()` hoặc chỉ `hasSize(1)` **chưa đủ** nếu hợp đồng bao gồm nội dung payload.

### Không nhầm failure của verification với failure của setup

Nếu mock tồn kho trả `false`, `orders.place(...)` ném `OUT_OF_STOCK` **trước khi** verification chạy. Test đỏ, nhưng lý do là **setup không phù hợp kịch bản thành công**, chứ không chứng minh assertion event đã phát hiện thiếu publication. Khi thử mutation, giữ fixture nhất quán để có thể quy lỗi đúng vào hậu điều kiện cần bảo vệ.

## 5. `PublishedEvents`: lọc dữ liệu không phải kiểm chứng

Tài liệu Spring Modulith 1.4 minh họa việc inject `PublishedEvents` vào method `@ApplicationModuleTest` để quan sát các Spring application events của testcase. API `ofType(...).matching(...)` trả một tập sự kiện có type/predicate phù hợp; **nó không có nghĩa “phải tồn tại ít nhất một event”**.

### Bốn cách viết và mức độ bảo vệ

| Code sau khi `orders.place(...)` | Nếu không có event | Nếu có event sai SKU |
| --- | --- | --- |
| `events.ofType(OrderPlaced.class);` | **Có thể passed** (không assert) | **Có thể passed** |
| `events.ofType(...).matching(OrderPlaced::orderId, id);` | **Có thể passed** (chỉ lọc) | **Có thể passed** |
| `assertThat(events.ofType(...).matching(...)).hasSize(1);` | **Fail** | Chưa chắc fail nếu sai SKU |
| `assertThat(...).singleElement().satisfies(e -> assertThat(e.sku()).isEqualTo(sku));` | **Fail** | **Fail** |

Nếu mục tiêu là kiểm tra sự kiện chỉ được phát một lần, dùng `hasSize(1)`/`singleElement()` thay vì `isNotEmpty()`. Nếu mục tiêu là payload, kiểm tra từng field có ý nghĩa. Mỗi assertion nên diễn đạt **hợp đồng cụ thể**, không chỉ tăng số dòng test.

### Cẩn thận với lambda không bao giờ chạy

```java
// SAI: iterable rỗng thì forEach không chạy callback, test vẫn passed.
events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, id)
        .forEach(event ->
                assertThat(event.quantity()).isEqualTo(2));

// ĐÚNG: bảo đảm phải có đúng một phần tử rồi mới assert payload.
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, id))
        .singleElement()
        .satisfies(event ->
                assertThat(event.quantity()).isEqualTo(2));
```

**Nguyên tắc chung:** `Iterable.forEach(...)`, `Stream.allMatch(...)` hoặc `Optional.ifPresent(...)` có thể thành công *vacuously* khi không có phần tử. Hãy assert **cardinality/presence** trước khi assert phần tử.

### `AssertablePublishedEvents` là lựa chọn thay thế

Khi dự án dùng AssertJ, Spring Modulith có thể inject `AssertablePublishedEvents` để dùng API assertion chuyên biệt:

```java
@Test
void emitsOrderEvent(AssertablePublishedEvents events) {
    UUID id = UUID.randomUUID();
    given(stock.available("SKU-READY", 1)).willReturn(true);
    try {
        orders.place(id, "SKU-READY", 1);
        assertThat(events)
                .contains(OrderPlaced.class)
                .matching(OrderPlaced::orderId, id);
    } finally {
        store.deleteById(id);
    }
}
```

Đây là một **method minh họa đặt trong `OrderVerificationTests`** với field `orders`/`stock`/`store` và static imports tương ứng; thêm import `org.springframework.modulith.test.AssertablePublishedEvents` khi sử dụng. Đối với hợp đồng cần **chính xác một event và payload đầy đủ**, cú pháp lọc `PublishedEvents` rồi `singleElement().satisfies(...)` ở phần 4 diễn đạt rõ hơn.

**Giới hạn:** Cả `PublishedEvents` và `AssertablePublishedEvents` chỉ kiểm tra **publication**. Chúng không xác nhận consumer ở module khác đã commit xử lý. Để kết luận “notification hoàn tất”, phải dùng một điểm quan sát consumer thật ở phần tiếp theo.

## 6. `Scenario`: thiếu terminal operation đồng nghĩa test chưa chạy

Trong **Spring Modulith 1.4**, `Scenario` dùng fluent DSL: bắt đầu từ `publish(...)` hoặc `stimulate(...)`, mô tả event/state mong đợi, cuối cùng **gọi phương thức kết thúc** để thực thi scenario và chờ verification.

### So sánh một lỗi rất khó nhận biết

```java
// SAI: mới tạo DSL, chưa thực thi scenario.
@Test
void shouldHandleOrder_BAD(Scenario scenario) {
    scenario.publish(new OrderPlaced(id, "SKU-READY", 1))
            .andWaitAtMost(Duration.ofSeconds(3))
            .forEventOfType(NotificationRecorded.class)
            .matching(event -> event.orderId().equals(id));
    // Bỏ qua kết quả fluent; không có toArrive/toArriveAndVerify.
}
```

Theo Javadoc 1.4, các builder có `@CheckReturnValue`, có thể được IDE/static analysis cảnh báo khi bỏ qua, nhưng **đừng mặc định annotation này tự làm JUnit fail lúc runtime**. Đoạn trên có thể kết thúc “passed” mà stimulus chưa thực hiện.

**Phiên bản đúng**:

```java
scenario.publish(new OrderPlaced(id, "SKU-READY", 1))
        .andWaitAtMost(Duration.ofSeconds(3))
        .forEventOfType(NotificationRecorded.class)
        .matching(event -> event.orderId().equals(id))
        .toArriveAndVerify(event ->
                assertThat(event.orderId()).isEqualTo(id));
```

Nếu không có `NotificationRecorded` đúng ID trong timeout, terminal `toArriveAndVerify(...)` **fail** vì điều kiện chờ không đạt; nếu có event nhưng payload sai, callback assertion **fail**. Có thể dùng `toArrive()` nếu hợp đồng **chỉ đòi event phù hợp xuất hiện**, nhưng `toArriveAndVerify(...)` rõ ràng hơn khi cần kiểm tra dữ liệu.

### Ví dụ consumer thật, tối giản nhưng đầy đủ

Thêm module `notification` vào ứng dụng mẫu, với event kết quả:

`src/main/java/com/example/shop/notification/NotificationRecorded.java`:

```java
package com.example.shop.notification;

import java.util.UUID;

public record NotificationRecorded(UUID orderId, String channel) {}
```

`src/main/java/com/example/shop/notification/NotificationJournal.java`:

```java
package com.example.shop.notification;

import java.util.UUID;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class NotificationJournal {
    private final Set<UUID> handled = ConcurrentHashMap.newKeySet();

    public void record(UUID id) { handled.add(id); }
    public boolean contains(UUID id) { return handled.contains(id); }
    public void remove(UUID id) { handled.remove(id); }
}
```

`src/main/java/com/example/shop/notification/NotificationListener.java`:

```java
package com.example.shop.notification;

import com.example.shop.order.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class NotificationListener {
    private final NotificationJournal journal;
    private final ApplicationEventPublisher publisher;

    public NotificationListener(NotificationJournal journal,
                                ApplicationEventPublisher publisher) {
        this.journal = journal;
        this.publisher = publisher;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        journal.record(event.orderId());
        publisher.publishEvent(
                new NotificationRecorded(event.orderId(), "EMAIL"));
    }
}
```

Listener này ghi **journal in-memory** và phát event xác nhận ghi nhận xử lý; nó **không gửi email thật**. Vì sử dụng `@TransactionalEventListener(AFTER_COMMIT)`, test cần transaction manager để kích hoạt listener. Với dự án có Spring Boot dependency management, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>test</scope>
</dependency>
```

Trong test scope, embedded H2 cùng JDBC starter cho phép Spring Boot auto-configure datasource và transaction manager nếu không bị cấu hình khác ghi đè. Vì journal là in-memory, ví dụ **không cần bảng SQL**. Không áp dụng hạ tầng demo này như cấu hình production.

Test `Scenario` thuộc package `order` chủ động nạp consumer:

```java
package com.example.shop.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.mockito.BDDMockito.given;

import java.time.Duration;
import java.util.UUID;
import com.example.shop.inventory.StockAvailability;
import com.example.shop.notification.NotificationJournal;
import com.example.shop.notification.NotificationRecorded;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Tag("integration")
@ApplicationModuleTest(extraIncludes = "notification")
class OrderScenarioVerificationTests {
    @Autowired OrderService orders;
    @Autowired OrderStore store;
    @Autowired NotificationJournal journal;
    @MockitoBean StockAvailability stock;

    @Test
    void notificationMustFinishForThisOrder(Scenario scenario) {
        UUID id = UUID.randomUUID();
        given(stock.available("SKU-READY", 1)).willReturn(true);

        scenario.stimulate(
                    () -> orders.place(id, "SKU-READY", 1))
                .andCleanup(() -> {
                    store.deleteById(id);
                    journal.remove(id);
                })
                .andWaitAtMost(Duration.ofSeconds(3))
                .forEventOfType(NotificationRecorded.class)
                .matching(event -> event.orderId().equals(id))
                // TERMINAL: bắt buộc thực thi/chờ/verify.
                .toArriveAndVerify((event, receipt) -> assertAll(
                    "Consumer đã ghi nhận chính đơn này",
                    () -> assertThat(receipt.orderId()).isEqualTo(id),
                    () -> assertThat(event.channel()).isEqualTo("EMAIL"),
                    () -> assertThat(journal.contains(id)).isTrue()
                ));
    }
}
```

Pha `stimulate(...)` dùng **use case thật** (validation + inventory mock + event), không chỉ phát một event giả. `Scenario` thực thi stimulus trong transaction để listener `AFTER_COMMIT` có thể chạy. `extraIncludes = "notification"` cần thiết vì consumer phụ thuộc **ngược** vào `order`; các mode nạp dependency xuôi của `order` không tự thêm consumer.

**Khi listener hoàn toàn không chạy**, timeout của `Scenario` khiến test fail, thay vì một test có callback không bao giờ được gọi nhưng vẫn xanh. **Khi journal sai hoặc channel sai**, callback assertion khiến test fail. Khi cần bảo vệ nhiều side effect bền vững, cleanup phải xử lý chính những side effect đã commit, không dựa vào rollback của một test transaction bên ngoài.

### Verification bằng state: buộc predicate phải thực sự đúng

Khi không có event kết quả nhưng có thể quan sát state:

```java
scenario.publish(new OrderPlaced(id, "SKU-READY", 1))
        .andWaitAtMost(Duration.ofSeconds(3))
        .forStateChange(
                () -> journal.contains(id),
                Boolean.TRUE::equals)
        .andVerify(isRecorded ->
                assertThat(isRecorded).isTrue());
```

Đây là **trích đoạn trong lớp có listener, transaction manager và `journal`**, không phải testcase hoàn chỉnh. Chú ý `Boolean.FALSE` là object **non-null**; nếu chọn overload không có predicate và chỉ dựa vào “non-null value”, điều kiện có thể hoàn thành ngay lúc state vẫn là `false`. Hãy diễn đạt rõ **giá trị thật sự cần đạt**. `andVerify(...)` là terminal operation của state-result; không chỉ dừng tại `forStateChange(...)`.

## 7. Async verification: exception ở thread khác không tự trở thành lỗi JUnit

Một test có thể kết thúc trước khi worker thread hoàn thành. Nếu assertion bị ném trong `CompletableFuture` nhưng testcase **không đợi/không quan sát future**, runner có thể không nhận được failure.

```java
// ANTI-PATTERN: không đưa vào CI như một verification hợp lệ.
@Test
void asynchronousAssertionMayNotReachJUnit() {
    CompletableFuture.runAsync(() ->
            assertThat(2 + 2).isEqualTo(5));
    // Không join/get; method có thể passed dù worker thất bại.
}
```

Phiên bản quan sát exception đúng cách:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class FutureVerificationTests {

    @Test
    void eventuallyComputesExpectedResult() throws Exception {
        CompletableFuture<Integer> operation =
                CompletableFuture.supplyAsync(() -> 2 + 2);

        // get(timeout) chờ completion và ném lỗi nếu worker thất bại
        // hoặc không hoàn thành đúng hạn.
        Integer result = operation.get(2, TimeUnit.SECONDS);

        assertThat(result).isEqualTo(4);
    }
}
```

Nếu producer dùng `@Async void` và ném exception, exception có thể được gửi tới `AsyncUncaughtExceptionHandler` hoặc log của executor **thay vì tới thread JUnit**. Đặt assertion trong production listener không phải một chiến lược đáng tin. Hãy chờ **event kết quả, state kết quả hoặc future có thể quan sát** trong test method; lỗi không được nuốt bằng `try/catch` rỗng.

### `CountDownLatch.await(...)` trả boolean — phải assert

```java
boolean completed = latch.await(2, TimeUnit.SECONDS);
assertThat(completed)
        .as("Listener phải hoàn thành trước deadline")
        .isTrue();
```

Nếu chỉ gọi `latch.await(2, TimeUnit.SECONDS);`, timeout trả `false` nhưng test **không bắt buộc fail**. Đồng thời, latch giảm xuống **không chứng minh dữ liệu nghiệp vụ đúng**; sau `await` vẫn cần assert event/state của correlation ID hiện tại. Với Spring Modulith event flow, `Scenario` thường diễn đạt điều kiện hoàn thành rõ ràng hơn latch thủ công.

### Thread, transaction và side effect đến muộn

Không bọc thao tác DB dựa vào Spring test-managed transaction trong `assertTimeoutPreemptively(...)`: JUnit chạy executable ở thread khác và có thể làm dữ liệu được ghi **ngoài transaction rollback** của test. Ưu tiên `@Timeout(threadMode = SAME_THREAD)` và deadline riêng của `Scenario`. Một scenario timeout cũng không tự **hủy** listener đang chạy; cleanup sau timeout phải tính tới dữ liệu commit muộn, dùng ID riêng và hạ tầng cô lập khi cần.

## 8. “Red control”: cố tình phá một hậu điều kiện để kiểm tra test

Một testcase đã từng passed **không chứng minh** nó biết phát hiện hậu điều kiện bị phá. Khi review test mới hoặc test từng báo false-green, có thể dùng **negative control/mutation thử nghiệm**:

| Thay đổi thử nghiệm trong code / fixture | Test nào phải đỏ? | Tín hiệu muốn nhìn thấy |
| --- | --- | --- |
| Bỏ `publisher.publishEvent(...)` | `orderMustPersistAndPublishExactlyOneMatchingEvent` | `singleElement()` fail vì event không đến |
| Publish `OrderPlaced` với quantity+1 | Test publication | Assert payload fail dù event type/ID đúng |
| Bỏ `store.save(...)` | Test order được chấp nhận | `Optional.contains(expected)` fail |
| Bỏ kiểm tra quantity trước lời gọi kho | Test quantity sai | Sai exception hoặc `shouldHaveNoInteractions()` fail |
| Cố ý đổi SKU khi hỏi inventory | Test boundary | Mock verification/khác biệt outcome fail |
| Bỏ listener `NotificationListener` hoặc không nạp module consumer | `notificationMustFinishForThisOrder` | `Scenario` terminal timeout/fail |
| Chỉ xây `Scenario` rồi bỏ `toArriveAndVerify(...)` | Kiểm tra sức mạnh test | Nếu JUnit vẫn xanh, đã phát hiện **lỗ hổng verification** cần sửa |
| Đổi `NotificationRecorded.channel` thành `"SMS"` | Test consumer | Assertion payload ở callback fail |

Đây là các **phép thử chẩn đoán**, không phải thay đổi nên để lại trong branch production. Sau khi xác nhận testcase báo **red đúng lý do**, hoàn nguyên mutation và chạy lại để bảo đảm **green**. Nếu muốn tự động hóa có kiểm soát, có thể cân nhắc mutation testing (ví dụ PIT) với cấu hình tương thích và test suite đủ nhanh; mutation score là một tín hiệu, không thay thế việc đánh giá hợp đồng nghiệp vụ.

### Ba bước xác minh đáng tin

1. **Green** với implementation đúng: test chạy và assertion hoàn tất, report có tên testcase.
2. **Red** khi xóa chính hành vi mà test tuyên bố bảo vệ: nhìn thấy lỗi từ **verification**, không chỉ lỗi khởi tạo context không liên quan.
3. **Green lại** sau hoàn nguyên: chứng minh kết quả có thể tái hiện và fixture sạch.

**Không nhầm “test đỏ” với “test đúng”**: một test có thể đỏ vì dependency cấu hình sai hoặc H2 không khởi động. Red-control chỉ có giá trị khi failure được định vị ở hậu điều kiện đang thử phá. Nên lưu bằng chứng trong pull request (mô tả mutation và assertion phát hiện), không cần commit mã production sai hoặc một testcase luôn fail.

### Verification chỉ xảy ra dưới điều kiện cũng cần negative control

Ví dụ code sai:

```java
if (store.findById(id).isPresent()) {
    assertThat(store.findById(id).orElseThrow().quantity())
            .isEqualTo(2);
}
// Nếu không có record, không có assertion nào được chạy.
```

Sửa:

```java
assertThat(store.findById(id))
        .as("Order %s phải tồn tại với quantity=2", id)
        .hasValueSatisfying(record ->
                assertThat(record.quantity()).isEqualTo(2));
```

Khi cố tình bỏ `save(...)`, bản sửa chắc chắn **fail vì record rỗng**. Đây là trường hợp “**verification không xảy ra**” do một nhánh `if` bỏ qua, khác với lỗi do không gọi terminal `Scenario` nhưng cùng nguyên lý fail-closed.

## 9. CI cũng phải fail khi **không test nào được thực thi**

Ngay cả một testcase có assertion tốt vẫn vô dụng nếu pipeline **không phát hiện hoặc không chọn nó**. JUnit `@Tag` chỉ phân loại; Gradle/Maven filter và quy tắc tên lớp quyết định test nào được lên lịch. “BUILD SUCCESS” với **0 architecture tests** không phải bằng chứng kiến trúc đúng.

Ví dụ một architecture gate riêng:

`src/test/java/com/example/shop/ModuleArchitectureTests.java`:

```java
package com.example.shop;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

@Tag("architecture")
class ModuleArchitectureTests {
    @Test
    void moduleBoundariesRemainValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ApplicationModules.verify()` kiểm chứng ranh giới/module dependency do Spring Modulith mô hình hóa. **Tag không làm việc này thay bạn**; nếu bỏ dòng `verify()`, method vẫn có thể xanh. Nếu code dự án có quy tắc đặc thù không được mô hình mặc định bao phủ, cần khai báo `allowedDependencies` hoặc thêm rule ArchUnit/custom verification tương ứng.

### Tách nhóm chạy nhưng không bỏ lọt architecture gate

Trong một dự án Gradle Java với JUnit Platform đã được cấu hình, có thể tạo task chọn test kiến trúc:

```kotlin
import org.gradle.api.tasks.testing.Test

val architectureTest by tasks.registering(Test::class) {
    group = "verification"
    description = "Spring Modulith architecture verification"
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath

    useJUnitPlatform {
        includeTags("architecture")
    }
}

tasks.named("check") {
    dependsOn(architectureTest)
}
```

Đây là **đoạn cấu hình** cần tích hợp vào `build.gradle.kts` thật và plugin Java; không thay thế toàn bộ build. Một job khác chỉ chạy `module & !integration` sẽ **không tự chọn** architecture test. Hãy bảo đảm stage architecture được lên lịch và có assertion thật, đặc biệt khi tối ưu chạy test theo thay đổi source.

### Hai kiểm tra bắt buộc trong báo cáo CI

1. **Trạng thái:** Nếu `verify()` fail, runner phải trả exit code không thành công, job là **required check** và chặn merge.
2. **Số lượng:** Báo cáo thực thi phải cho thấy có ít nhất một architecture testcase đã chạy (không phải chỉ discovered/skipped). Nếu số chạy về **0**, pipeline phải đánh dấu **lỗi lựa chọn test** bằng một bước kiểm tra báo cáo/test counts riêng phù hợp với CI.

Đừng giả định một cấu hình `includeTags(...)` tự động làm Gradle/Maven fail khi filter chọn 0 testcase trong mọi phiên bản. Kiểm tra hành vi runner thực tế và có **guard độc lập** dựa trên test report khi architecture gate là yêu cầu bắt buộc.

### Ma trận chẩn đoán các trường hợp “đáng lẽ phải đỏ”

| Hiện tượng | Kiểm tra đầu tiên | Cách sửa đúng |
| --- | --- | --- |
| Test mất event mà vẫn xanh | Có `assertThat(...).hasSize(1)` hay chỉ lọc? | Thêm assertion có thể fail |
| `Scenario` không chạy listener nhưng test xanh | Chuỗi DSL có kết thúc `toArrive...()`/`andVerify(...)`? | Thêm terminal operation |
| Listener ném exception mà test vẫn xanh | Exception ở thread async có được truyền về không? | Chờ event/state/future và fail khi thiếu |
| Không có record nhưng callback assertion không chạy | Có `Optional.ifPresent` hoặc `if (present)` không? | Assert presence trước |
| Kho không được gọi mà test xanh | Chỉ stub hay đã `verify/then(...).should()`? | Verification theo boundary contract |
| Latch timeout mà test xanh | Có assert giá trị boolean của `await` không? | `assertTrue(completed)` + assert state |
| Mock repository xanh nhưng DB không lưu | Chỉ kiểm tra invocation, không đọc DB thật | Integration test repository/datasource riêng |
| Test `@Disabled`/assumption abort nhưng job xanh | Report có skipped/aborted không? | Không dùng skip cho required gate |
| Architecture job xanh với 0 tests | Test discovery/naming/tag filter? | Guard test count và gọi `verify()` |

**Ghi nhớ:** “Fail khi verification không xảy ra” có **hai cấp**: testcase phải thực thi các assertions hoặc terminal operations, và CI phải thực sự **chạy testcase đó**. Thiếu một trong hai, kết quả xanh không có giá trị bảo đảm.

## 10. Checklist review, bài tập và nguồn tham khảo

### Checklist trước khi merge

| Câu hỏi kiểm tra | Điều kiện đạt |
| --- | --- |
| Có một hậu điều kiện được phát biểu rõ? | Tên test và assertion bảo vệ cùng một hợp đồng |
| Nếu bỏ hành vi production thì test có đỏ? | Đã có negative control hoặc lập luận assertion cụ thể |
| Có assertion sau `PublishedEvents.ofType(...)`? | Kiểm tra cardinality/payload, không chỉ gọi filter |
| Có callback chỉ chạy khi dữ liệu tồn tại? | Assert presence/cardinality để callback không bị bỏ qua âm thầm |
| Với Mockito, có verify khi hợp đồng yêu cầu interaction? | Không nhầm stubbing và verification |
| Với `Scenario`, có terminal operation? | `toArrive...()`/`andVerify(...)` làm scenario thực thi |
| Event/state được lọc theo ID riêng? | Không nhận nhầm sự kiện của test khác |
| Eventual outcome có timeout và predicate đúng? | Không chỉ ngủ hoặc kiểm tra giá trị non-null |
| Async exception có về được thread JUnit? | Future được đợi hoặc Scenario đợi kết quả rõ ràng |
| Test negative có kiểm tra absence đúng? | Không còn record/event/tương tác cấm sau thao tác lỗi |
| Cleanup xảy ra cả khi assertion fail? | `finally`, rollback hoặc Scenario cleanup đúng phạm vi |
| Architecture test có verification thật? | Có `ApplicationModules.verify()` hoặc rule tương đương |
| CI có biết khi chọn 0 test? | Có kiểm tra test count, required checks không bị skip |

### Bài tập thực hành có trọng tâm

1. **Phát hiện test xanh giả:** Viết một `@Test` chỉ có `events.ofType(OrderPlaced.class).matching(...)`. Bỏ publication ở `OrderService`. Test xanh hay đỏ? Thêm `hasSize(1)` rồi giải thích thay đổi.
2. **Kiểm tra số event:** Sửa `OrderService` publish hai `OrderPlaced` cho cùng ID. So sánh `isNotEmpty()` với `singleElement()`, chọn assertion đúng hợp đồng “một lệnh — một event”.
3. **Kiểm tra payload:** Giữ type/ID đúng nhưng đổi quantity trong event. Viết callback `satisfies(...)` làm test fail vì field sai.
4. **Bỏ verification của Mockito:** Stub `stock.available(...)` nhưng cố ý loại bỏ lời gọi `stock.available(...)` khỏi use case, đồng thời thay bằng logic trả kết quả tĩnh. Xác định assertion/mock verification nào phát hiện dependency không được gọi.
5. **Optional vắng mặt:** So sánh `Optional.ifPresent(assertion)` với `hasValueSatisfying(...)` khi bỏ `store.save(...)`.
6. **Scenario thiếu terminal:** Tạo DSL `scenario.publish(...).forEventOfType(...).matching(...)` nhưng không gọi `toArrive()`. Sau đó thêm terminal và quan sát test fail khi listener không nạp.
7. **Future chưa đợi:** Viết `CompletableFuture.runAsync(...)` chứa assertion cố ý sai. So sánh kết quả khi bỏ qua future và khi `future.get(timeout)` truyền exception về JUnit.
8. **Nhánh từ chối:** Cho `OrderService` publish event rồi mới ném `INVALID_ORDER`. Test nào cần assert **không có event** để phát hiện lỗi này?
9. **Mutation red/green:** Với ít nhất hai hậu điều kiện (state và event), thực hiện red-control rồi hoàn nguyên mutation. Ghi rõ failure đến từ assertion nào.
10. **CI zero-test:** Thay đổi tag filter của architecture task để không có testcase được chạy. Thiết kế guard bằng JUnit XML/test-report count và required check, không chấp nhận build “thành công” vô nghĩa.

### Tài liệu tham khảo

- [JUnit Jupiter 5.14 — Assertions, assertThrows và assertAll](https://docs.junit.org/5.14.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html)
- [JUnit Jupiter User Guide — Writing Tests](https://docs.junit.org/5.14.4/writing-tests/index.html)
- [Mockito Javadoc — verify và BDDMockito](https://site.mockito.org/javadoc/current/org/mockito/Mockito.html)
- [Spring Modulith 1.4 — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/1.4/testing.html)
- [Spring Modulith 1.4 — Testing Published Events](https://docs.spring.io/spring-modulith/reference/1.4/events.html)
- [Spring Modulith 1.4 API — Scenario](https://docs.spring.io/spring-modulith/docs/1.4.0/api/org/springframework/modulith/test/Scenario.html)
- [Spring Modulith 1.4 API — Scenario.When.EventResult](https://docs.spring.io/spring-modulith/docs/1.4.0/api/org/springframework/modulith/test/Scenario.When.EventResult.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
