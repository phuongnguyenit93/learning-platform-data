# Reset mock giữa các scenario

## 1. “Giữa các scenario” là ranh giới nào?

Với một bài kiểm thử Spring Modulith, có ít nhất ba đối tượng rất dễ bị gọi chung là “trạng thái test”:

1. **Mockito mock state:** những lời gọi đã ghi nhận (*invocations*), các câu `when(...).thenReturn(...)` (*stubbings*), và bộ đếm/chuỗi trả lời.
2. **Spring test context state:** bean/mock được inject, ApplicationContext được cache, các listener, transaction manager và executor đang hoạt động.
3. **Business state:** hàng dữ liệu trong database, sự kiện đã phát, publication trong Event Publication Registry, cache/queue và side effect ngoài hệ thống.

**Reset Mockito chỉ tác động lên đối tượng thứ nhất.** Nó không xóa những row JPA, không thu hồi event đã publish, không hủy HTTP request đã gửi và không nhất thiết dừng một listener bất đồng bộ.

Trong chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu là kiểm chứng ranh giới module qua `ApplicationModules`, `@ApplicationModuleTest`, database, event và quality gate CI. Vì vậy câu hỏi “reset mock giữa các scenario” không chỉ là chọn API Mockito: cần xác định **scenario nào**, **khi nào nó thực sự kết thúc**, và **loại state nào phải được cô lập**.

### Hai nghĩa của “scenario” cần tách bạch

**A. Hai phương thức JUnit độc lập**:

~~~java
@Test void acceptsOrder() { /* scenario A */ }
@Test void rejectsOrder() { /* scenario B */ }
~~~

Với `@MockitoBean` do Spring Test quản lý và reset mode mặc định `AFTER`, mock thường được reset **sau mỗi phương thức test**. Spring có thể **tái sử dụng cùng ApplicationContext** cho cả hai; reset mock không có nghĩa Spring tạo context mới.

**B. Hai lần stimulate/quan sát trong *cùng* một phương thức**:

~~~java
@Test
void twoStepsInsideOneTest() {
    // Stimulus A; verify kết quả A.
    // Stimulus B; verify kết quả B.
}
~~~

Reset tự động ở ranh giới **test method** không tự diễn ra giữa hai bước A/B. Ngay cả khi dùng `Scenario` của Spring Modulith để mô tả luồng event, mỗi lệnh stimulate/wait **không mặc nhiên** là một ranh giới reset Mockito.

**Câu hỏi quyết định trước khi gọi `reset(...)`:** Bạn cần “bỏ những invocations đã verify trong bước A để đếm riêng bước B”, hay cần “thay đổi cấu hình trả lời của mock”? Hai nhu cầu đó có đáp án khác nhau.

## 2. Phân biệt reset(), clearInvocations() và reset mode của @MockitoBean

| Cơ chế | Xóa invocations? | Xóa stubbings? | Ranh giới/ý nghĩa |
| --- | --- | --- | --- |
| `Mockito.clearInvocations(mock)` | **Có.** | **Không.** | Làm rỗng lịch sử lời gọi tại một checkpoint, giữ các `when(...)`. |
| `Mockito.reset(mock)` | **Có.** | **Có.** | Đưa mock về default behavior; phải stub lại trước khi dùng. |
| `@MockitoBean(reset = MockReset.AFTER)` | **Có, sau test method.** | **Có.** | Spring Test reset mock đã đăng ký sau mỗi test method; đây là mặc định thông dụng của annotation. |
| `@MockitoBean(reset = MockReset.BEFORE)` | **Có, trước test method.** | **Có.** | Chọn khi cần dọn mock trước mỗi phương thức thay vì sau. |
| `@MockitoBean(reset = MockReset.NONE)` | **Không tự động.** | **Không tự động.** | Chỉ dùng nếu có chiến lược quản lý state/isolation thật sự rõ ràng. |
| `@Mock` với `MockitoExtension` | Mockito/JUnit quản lý theo lifecycle test tương ứng. | Theo lifecycle test. | Unit test thuần: thường không cần gọi reset giữa các phương thức. |

Trong Spring Framework 6.2+, `@MockitoBean` và `@MockitoSpyBean` có thuộc tính `reset` dùng `org.springframework.test.context.bean.override.mockito.MockReset`. Với Spring Boot cũ hơn, `@MockBean`/`@SpyBean` có API reset tương ứng nhưng **khác package/phiên bản**; không trộn các imports.

### 2.1. Đoạn JUnit chứng minh khác biệt bằng hành vi

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class ClearVersusResetTests {

    interface StockPort {
        boolean available(String sku);
    }

    @Test
    void clearKeepsStubsButResetDropsThem() {
        StockPort stock = mock(StockPort.class);
        when(stock.available("SKU-1")).thenReturn(true);

        assertThat(stock.available("SKU-1")).isTrue();
        verify(stock).available("SKU-1");

        clearInvocations(stock);
        verifyNoInteractions(stock);

        // Stub vẫn còn; đây là lần gọi ĐẦU sau checkpoint.
        assertThat(stock.available("SKU-1")).isTrue();
        verify(stock).available("SKU-1");

        reset(stock);
        verifyNoInteractions(stock);

        // Boolean primitive chưa stub -> Mockito trả false.
        assertThat(stock.available("SKU-1")).isFalse();
    }
}
~~~

Trong phương thức này, `reset(stock)` là **đối tượng minh họa** để thấy sự khác nhau. Nó không phải lời khuyên gọi reset thường xuyên. Trường hợp thực tế hay gặp hơn là `clearInvocations` tại **checkpoint giữa hai pha**, hoặc tách hai pha thành **hai test độc lập**.

### 2.2. Những thứ không được reset

~~~text
Mockito.reset(inventoryMock)
    ├─ xóa stubs/invocations trên inventoryMock
    ├─ KHÔNG xóa shop_orders trong database
    ├─ KHÔNG xóa PublishedEvents đã quan sát
    ├─ KHÔNG hoàn tác publication / broker delivery
    └─ KHÔNG đồng bộ được các listener còn đang chạy
~~~

Nếu bài test chỉ xanh sau khi “reset mock rồi mong hệ thống trở lại ban đầu”, nó có thể đang bỏ sót DB fixture, async work, context cache hoặc idempotency state.

## 3. Case xuyên suốt: chỉ mock API tồn kho, giữ module orders thật

Giả sử Spring Boot application ở `com.example.shop`, với hai application modules `catalog` và `orders`:

~~~text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── api
│   │   ├── InventoryAvailability.java
│   │   └── package-info.java
│   └── internal
│       └── InventoryService.java
└── orders
    ├── OrderService.java
    ├── OutOfStockException.java
    ├── package-info.java
    ├── events
    │   ├── OrderSubmitted.java
    │   └── package-info.java
    └── internal
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

Module `orders` chỉ hỏi `catalog.api.InventoryAvailability` về số lượng hàng. Ta **mock duy nhất collaborator công khai ngoài module**; repository của `orders` và event publisher vẫn chạy thật để có bằng chứng persistence/event. Không import implementation hay repository nội bộ của `catalog` chỉ để test dễ stub hơn.

### 3.1. API của catalog và ràng buộc module

File `catalog/api/InventoryAvailability.java`:

~~~java
package com.example.shop.catalog.api;

import java.util.UUID;

public interface InventoryAvailability {
    boolean isAvailable(UUID skuId, int quantity);
}
~~~

File `catalog/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.catalog.api;
~~~

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog :: api")
package com.example.shop.orders;
~~~

### 3.2. Repository thật, event và service transaction

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.UUID;

@Entity
@Table(name = "shop_orders")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "sku_id", nullable = false)
    private UUID skuId;

    @Column(nullable = false)
    private int quantity;

    protected OrderEntity() {}

    public OrderEntity(UUID id, UUID skuId, int quantity) {
        this.id = id;
        this.skuId = skuId;
        this.quantity = quantity;
    }

    public UUID getId() { return id; }
    public UUID getSkuId() { return skuId; }
    public int getQuantity() { return quantity; }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

File `orders/events/OrderSubmitted.java`:

~~~java
package com.example.shop.orders.events;

import java.util.UUID;

public record OrderSubmitted(
        UUID orderId, UUID skuId, int quantity) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `orders/OutOfStockException.java`:

~~~java
package com.example.shop.orders;

public class OutOfStockException extends RuntimeException {
    public OutOfStockException() {
        super("Not enough stock");
    }
}
~~~

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.api.InventoryAvailability;
import com.example.shop.orders.events.OrderSubmitted;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final InventoryAvailability inventory;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(InventoryAvailability inventory,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.inventory = inventory;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId, UUID skuId, int quantity) {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(skuId);
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }
        if (!inventory.isAvailable(skuId, quantity)) {
            throw new OutOfStockException();
        }

        orders.save(new OrderEntity(orderId, skuId, quantity));
        publisher.publishEvent(
                new OrderSubmitted(orderId, skuId, quantity));
    }
}
~~~

Ví dụ cố ý chỉ có một outbound dependency để tập trung vào **lifecycle của mock `InventoryAvailability`**. Nếu hệ thống thật còn reservation/stock decrement, cần một contract giữa module bảo đảm consistency dưới concurrency; Boolean availability trong ví dụ **chưa** chứng minh giữ hàng atomic.

## 4. Hai JUnit scenarios: @MockitoBean reset AFTER thực hiện đúng việc

Đặt test dưới package `com.example.shop.orders` để `@ApplicationModuleTest` chọn module `orders`. Trong mode `STANDALONE`, implementation `catalog.internal.InventoryService` không được bootstrap; Spring Test cung cấp `InventoryAvailability` mock.

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.api.InventoryAvailability;
import com.example.shop.orders.events.OrderSubmitted;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockReset;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderModuleMockLifecycleTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    // AFTER cũng là default; ghi rõ để dễ thảo luận lifecycle.
    @MockitoBean(reset = MockReset.AFTER)
    InventoryAvailability inventory;

    @Test
    void acceptsWhenInventoryIsAvailable(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();

        when(inventory.isAvailable(skuId, 2)).thenReturn(true);

        orders.place(orderId, skuId, 2);

        verify(inventory).isAvailable(skuId, 2);
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(row -> {
                    assertThat(row.getSkuId()).isEqualTo(skuId);
                    assertThat(row.getQuantity()).isEqualTo(2);
                });
        assertThat(events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::orderId, orderId))
                .hasSize(1);
    }

    @Test
    void rejectsWhenInventoryIsNotAvailable(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();

        // Không phụ thuộc stub true của test khác.
        when(inventory.isAvailable(skuId, 2)).thenReturn(false);

        assertThatThrownBy(() ->
                orders.place(orderId, skuId, 2))
                .isInstanceOf(OutOfStockException.class);

        verify(inventory).isAvailable(skuId, 2);
        assertThat(repository.existsById(orderId)).isFalse();
        assertThat(events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::orderId, orderId))
                .isEmpty();
    }
}
~~~

**Không cần `@BeforeEach void resetIt() { reset(inventory); }`.** Spring Test quản lý reset của bean đã override theo `MockReset.AFTER`; mỗi test tự khai báo stubbing của mình. Thứ tự hai methods không quan trọng, cả hai dùng UUID riêng nên không cần database rỗng toàn cục để đúng.

### Những việc cần quan sát chính xác

| Điều | Bằng chứng trong test |
| --- | --- |
| Mock sau test A không giữ stubbing true/invocation sang test B. | Reset mode do Spring Test quản lý; B chủ động stub false và verify đúng lời gọi của chính B. |
| Order thực được lưu khi đủ hàng. | Repository JPA thật `findById`. |
| Order không được lưu khi thiếu hàng. | Repository JPA thật `existsById` trả false. |
| Spring thực sự phát `OrderSubmitted`. | `PublishedEvents` với `orderId` riêng. |
| Listener module khác đã hoàn tất hoặc broker đã nhận. | **Chưa được chứng minh** bởi hai tests trên. |

Test này cần Spring Modulith test support, datasource, schema `shop_orders` và transaction manager. **Không gắn `@Transactional` lên cả test class** nếu cần kết luận `OrderService.place` đã mở/commit transaction thật trước khi query; một outer test transaction rollback mặc định sẽ thay đổi ý nghĩa bằng chứng.

### 4.1. Đừng tự xác minh reset bằng thứ tự JUnit cố định

Không viết “test B pass vì test A chạy trước” hoặc dùng `@TestMethodOrder` để chia sẻ stubbing. Một suite đúng phải chạy xanh khi:

- Chỉ chạy riêng phương thức B.
- Chạy cả lớp với thứ tự bất kỳ.
- Chạy lại phương thức A nhiều lần.

Nếu B cần A tạo dữ liệu, hãy tách thành một **workflow test** có setup/step rõ, không trá hình dependency giữa hai JUnit methods.

## 5. Nhiều bước trong cùng một method: clearInvocations() đúng lúc

Giả sử cần kiểm tra hai lần đặt hàng **trong cùng một use case test** để chứng minh mỗi stimulus hỏi inventory đúng một lần. Vì cả hai steps nằm trong một `@Test`, reset tự động `AFTER` chỉ chạy **sau khi method kết thúc**.

Nếu không clear, `verify(inventory).isAvailable(skuId, 1)` lần thứ hai sẽ thấy **hai invocations**, và Mockito báo `TooManyActualInvocations`. Khi cần một checkpoint chính thức, dùng `clearInvocations` — **giữ nguyên stub** để phần B tiếp tục dùng.

~~~java
// Thêm method này vào OrderModuleMockLifecycleTests.
@Test
void eachStimulusCallsInventoryOnceWithinOneTest(
        PublishedEvents events) {
    UUID skuId = UUID.randomUUID();
    UUID firstOrderId = UUID.randomUUID();
    UUID secondOrderId = UUID.randomUUID();

    when(inventory.isAvailable(skuId, 1)).thenReturn(true);

    // ===== Scenario A =====
    orders.place(firstOrderId, skuId, 1);
    verify(inventory).isAvailable(skuId, 1);
    assertThat(repository.existsById(firstOrderId)).isTrue();
    assertThat(events.ofType(OrderSubmitted.class)
            .matching(OrderSubmitted::orderId, firstOrderId))
            .hasSize(1);

    // Mốc kiểm chứng A đã hoàn tất; chỉ dọn invocation history.
    org.mockito.Mockito.clearInvocations(inventory);
    org.mockito.Mockito.verifyNoInteractions(inventory);

    // ===== Scenario B =====
    // Stub true từ A VẪN có hiệu lực.
    orders.place(secondOrderId, skuId, 1);
    verify(inventory).isAvailable(skuId, 1);
    assertThat(repository.existsById(secondOrderId)).isTrue();
    assertThat(events.ofType(OrderSubmitted.class)
            .matching(OrderSubmitted::orderId, secondOrderId))
            .hasSize(1);
}
~~~

Đây là phép kiểm chứng **riêng từng bước** của invocation contract, **không phải** hai test độc lập. Mock được clear một lần giữa A/B, nhưng **hai rows và hai events vẫn tồn tại**. Vì vậy mọi DB/event assertion lọc theo `orderId`, không viết `assertThat(repository.count()).isEqualTo(1)` hoặc `assertThat(events.ofType(OrderSubmitted.class)).hasSize(1)` ở cuối bước B.

### 5.1. Trường hợp *không cần* clearInvocations

Nếu mục tiêu thực sự là “hai lần gọi `orders.place` thì hỏi stock hai lần”, hãy assert **tổng hai invocations**:

~~~java
verify(inventory, org.mockito.Mockito.times(2))
        .isAvailable(skuId, 1);
~~~

Khi mục tiêu có thể diễn đạt bằng một assertion tổng, `clearInvocations` chỉ tăng độ phức tạp và có thể che số lần gọi thừa **trước checkpoint**. Chỉ xóa history khi **hợp đồng cần đối chiếu từng phase** và phase A đã được kiểm chứng đầy đủ.

### 5.2. Sequential stubbing không bị tua ngược bởi clearInvocations

~~~java
when(inventory.isAvailable(skuId, 1))
        .thenReturn(true, false);

orders.place(firstOrderId, skuId, 1);  // Nhận true.
clearInvocations(inventory);          // Xóa calls, KHÔNG rewind stub.

assertThatThrownBy(() ->
        orders.place(secondOrderId, skuId, 1))
        .isInstanceOf(OutOfStockException.class); // Nhận false.
~~~

Đây là **snippet độc lập** (cần `skuId`, IDs, imports và `@Test` như ví dụ trên), không thêm vào method đã stub `thenReturn(true)` mà không dọn setup. `clearInvocations` giữ cả *state của chuỗi câu trả lời*; khi cần hai quyết định tách biệt, có thể stub lại **có chủ đích** hoặc tách test thay vì trông đợi reset “tua lại” sequence.

## 6. Khi nào reset() giữa các bước làm test kết luận sai?

Một lỗi thường xảy ra là chọn `reset(mock)` khi thực ra chỉ muốn xóa invocation history:

~~~java
// Snippet minh họa bên trong OrderModuleMockLifecycleTests.
UUID skuId = UUID.randomUUID();
when(inventory.isAvailable(skuId, 1)).thenReturn(true);

orders.place(UUID.randomUUID(), skuId, 1);
verify(inventory).isAvailable(skuId, 1);

// Reset xóa CẢ stubs và calls.
org.mockito.Mockito.reset(inventory);

// Trong Mockito, boolean chưa stub mặc định false:
// service.place(...) sẽ ném OutOfStockException.
assertThatThrownBy(() ->
        orders.place(UUID.randomUUID(), skuId, 1))
        .isInstanceOf(OutOfStockException.class);
~~~

Đây là hệ quả của reset, **không phải bằng chứng** “scenario B có lỗi tồn kho”. Nếu bạn quên stub lại, test B có thể đi sai nhánh chỉ vì mock vừa bị xóa cấu hình. Với `clearInvocations(inventory)`, câu trả lời `true` được giữ; với `reset(inventory)`, phải viết lại:

~~~java
org.mockito.Mockito.reset(inventory);
when(inventory.isAvailable(skuId, 1)).thenReturn(true);
~~~

Tuy nhiên, nếu mọi bước đều cần reset rồi cấu hình lại như test độc lập, **nên tách chúng thành nhiều `@Test`**. Test ít code dọn dẹp hơn, dễ chạy độc lập hơn và tránh bỏ qua lỗi chỉ xuất hiện do thứ tự phase.

### 6.1. Chọn BEFORE, AFTER hay NONE?

`@MockitoBean` cho phép cấu hình:

~~~java
@MockitoBean(reset = MockReset.AFTER)
InventoryAvailability inventory;
~~~

Đây là lựa chọn mặc định thông dụng: test method tự tạo stubs, xác nhận interactions, rồi Spring Test reset mock sau khi test method kết thúc. Nếu cần reset **trước mỗi test method** do chính sách lifecycle của suite:

~~~java
@MockitoBean(reset = MockReset.BEFORE)
InventoryAvailability inventory;
~~~

Hai snippets thể hiện **hai cấu hình thay thế**, không khai báo cả hai cho cùng một bean trong một test class. `BEFORE` không reset giữa các `Scenario.stimulate(...)` bên trong method.

`MockReset.NONE` tắt auto-reset:

~~~java
@MockitoBean(reset = MockReset.NONE)
InventoryAvailability inventory;
~~~

Chỉ nên dùng `NONE` khi bạn có **lý do cụ thể và test isolation riêng**; nếu ApplicationContext được cache, stubs và invocation history có thể tồn tại qua nhiều methods, tạo false positives hoặc `TooManyActualInvocations` tùy test ordering. Đặc biệt nguy hiểm khi một test `verifyNoInteractions` vô tình kế thừa lời gọi từ test trước.

### 6.2. @BeforeEach là nơi đúng hơn @BeforeAll cho stubbing

Với auto reset `AFTER`, hãy stub điều kiện cần ở **trong từng test** hoặc `@BeforeEach`:

~~~java
@BeforeEach
void prepareInventory() {
    when(inventory.isAvailable(
            any(UUID.class), eq(1)))
            .thenReturn(true);
}
~~~

Đoạn này cần imports `BeforeEach`, `UUID`, `any`, `eq`, `when`. Chỉ nên dùng setup chung nếu **tất cả** tests thực sự cần stub ấy; các test “thiếu hàng” nên tự quyết định answer cho case cụ thể, không phụ thuộc một default ẩn. Nếu không cần setup chung, stubbing trong mỗi method như mục 4 dễ đọc hơn.

**Không đặt stubbing dùng cho nhiều tests một lần ở `@BeforeAll` rồi kỳ vọng nó còn nguyên**: reset sau test thứ nhất có thể xóa stub và làm test thứ hai chạy với default behavior. Kể cả khi dùng `@TestInstance(PER_CLASS)`, bean mock thuộc Spring context vẫn có lifecycle reset theo từng method, không theo thời gian sống của test instance.

### 6.3. Unit @Mock khác với @MockitoBean

`@ExtendWith(MockitoExtension.class)` cộng JUnit lifecycle mặc định `PER_METHOD` thường tạo bối cảnh mock mới cho từng method. Vì thế trong unit test thuần cũng **không cần** reset manual giữa các methods. Ngược lại, `@MockitoBean` là bean override trong **Spring Test ApplicationContext**, nơi context cache có thể giữ cùng bean instance được inject qua nhiều methods. Auto reset của framework giúp cô lập **Mockito state** mà không cần dựng lại toàn context.

### 6.4. Spy cũng reset lịch sử, không reset tác động thật

Nếu thay một service thật bằng:

~~~java
@MockitoSpyBean(reset = MockReset.AFTER)
AuditService auditService;
~~~

thì spy có thể đã thực hiện **real JPA write, HTTP call hoặc cache mutation**. Reset của Mockito không hoàn tác các side effects ấy. Không dùng spy chỉ để “giữ logic thật nhưng xóa được trạng thái” trong khi cần database isolation; state persistence phải được dọn/đặt lại theo contract riêng.

## 7. Scenario và listener bất đồng bộ: đừng reset khi công việc còn đang chạy

Spring Modulith có `Scenario` cho những luồng kiểm thử kích thích sự kiện rồi chờ một outcome. Tuy nhiên, **điểm kết thúc của một `Scenario` step không phải một lời gọi tự động tới Mockito.reset**. Đặc biệt với `@ApplicationModuleListener` hoặc `@Async`, một event có thể được phát trong transaction nguồn, rồi listener chạy trên thread khác **sau commit**.

~~~mermaid
sequenceDiagram
    participant Test
    participant Orders as OrderService
    participant Pub as Spring event publisher
    participant Worker as Async listener
    participant Mock as Mock outbound gateway
    Test->>Orders: Stimulus A
    Orders->>Pub: publish OrderSubmitted(A)
    Orders-->>Test: source transaction completes
    Pub-->>Worker: after-commit delivery (async)
    Note over Test,Worker: Listener có thể chưa hoàn tất
    Test-->>Mock: reset() quá sớm
    Worker->>Mock: send(A) sau reset
    Note over Mock,Test: Invocation rơi sang pha B hoặc bị kiểm tra sai
~~~

**Sai lầm:** Test A quan sát `PublishedEvents` có `OrderSubmitted(A)`, lập tức gọi `reset(notificationGateway)`, rồi bắt đầu B. `PublishedEvents` chứng minh producer đã phát event, **không chứng minh listener A đã xử lý xong**. Kết quả B có thể lẫn lời gọi trễ của A, hoặc stubbing của A bị xóa trước khi listener A dùng nó.

### 7.1. Checkpoint đúng là *sau khi outcome A được quan sát*

Trong một integration test nạp listener thật, nếu listener:

1. Nhận `OrderSubmitted(A)`.
2. Gọi `NotificationGateway.send(A)` (mock tại outbound boundary).
3. Ghi `NotificationReceipt(A)` trong transaction xử lý của nó.

thì có thể chờ **row receipt đã được commit** và verify gateway trước khi dọn invocation history:

~~~java
// Snippet cho một integration test đã nạp listener thật,
// notificationGateway là @MockitoBean, receipts là JPA thật.
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(receipts.existsByOrderId(firstOrderId))
                        .isTrue());

verify(notificationGateway).send(firstOrderId);

// Chỉ checkpoint khi callback A và side effect đã được xác nhận.
clearInvocations(notificationGateway);

// Bây giờ mới kích thích scenario B với ID riêng.
~~~

Snippet này cần Awaitility, repository/fixture và một listener có thứ tự thực thi tương ứng; nó **không phải một test class độc lập**. Đặc biệt, sự kiện nhận có thể được xử lý lại vì retry: nếu cần kiểm chứng “không duplicate”, hãy assert idempotency/business state bền vững và publication completion, không dựa hoàn toàn vào reset mock.

### 7.2. await verify(...) và await state là hai bằng chứng khác nhau

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                verify(notificationGateway)
                        .send(firstOrderId));
~~~

Đoạn này chỉ chờ **invocation xảy ra**. Nếu listener còn phải ghi database/commit hoặc đánh dấu publication completed **sau lời gọi gateway**, test không được kết luận nó đã hoàn tất. Ưu tiên chờ **điều kiện outcome bền vững** khi đó mới là mục tiêu nghiệp vụ.

### 7.3. Tại sao reset AFTER test method cũng có thể không cứu được async test lỗi?

Spring Test auto reset chạy theo lifecycle test method, không đợi vô hạn các callbacks async chưa hoàn tất. Nếu test kết thúc ngay khi chỉ vừa publish event, listener có thể tiếp tục dùng cùng mock **sau ranh giới teardown**, làm test kế tiếp bị nhiễu. Cách sửa là **đợi listener A kết thúc ở đúng observable boundary**, quản lý executor/registry và fixture, không đổi reset mode sang `NONE` hoặc thêm `Thread.sleep` cố định.

Nếu dùng `Scenario` API của Spring Modulith, hãy chọn phương thức chờ **event hoặc state** tương ứng với mục tiêu thực; chờ **event được phát** chưa chắc là chờ **listener xử lý xong**. Đối chiếu API `Scenario` với version Spring Modulith của dự án và không xem DSL stimulus là cơ chế isolation của Mockito.

## 8. Spring context cache, parallel tests và các trạng thái không phải Mockito

Một `@ApplicationModuleTest` có thể dùng **ApplicationContext được Spring Test cache** để chạy nhanh. Việc reset mock `AFTER` xử lý stubs/invocations theo methods, nhưng **không làm ApplicationContext mới, datasource mới hoặc thread pool mới**.

### 8.1. Nguồn state, cách xử lý và dấu hiệu lỗi

| State | `reset(mock)` có xóa không? | Cách cô lập đúng |
| --- | --- | --- |
| Stubbing `InventoryAvailability` | **Có.** | Auto-reset `AFTER` giữa JUnit methods; stub per test. |
| Invocation count mock | **Có.** | `clearInvocations` khi cần checkpoint trong cùng method. |
| Hàng `shop_orders` | **Không.** | UUID riêng, cleanup/migration fixtures, transaction isolation. |
| `PublishedEvents` đã quan sát trong method | **Không.** | Lọc theo event/business ID; hiểu lifecycle collector. |
| Publication incomplete trong registry | **Không.** | Registry store/transaction cleanup, test recovery đúng target. |
| Cache, static fields, singleton mutable state | **Không.** | Reset state thật, dùng isolated context khi cần. |
| Broker topic hoặc HTTP provider side effect | **Không.** | Test container/namespace/key riêng, provider sandbox và cleanup. |
| `@Async` callback chưa xong | **Không.** | Chờ completion/outcome và kiểm soát executor. |

`@DirtiesContext` có thể buộc Spring tạo context mới trong trường hợp cần tránh state khó khôi phục, nhưng **không nên dùng như giải pháp mặc định chỉ vì một mock có invocations cũ**: nó làm suite chậm và cũng không tự làm sạch database/broker bên ngoài context.

### 8.2. JUnit @Nested, @RepeatedTest và @ParameterizedTest

Với các test methods/invocations riêng, Spring Test lifecycle thường xử lý reset theo **từng lần thực thi test**. Tuy nhiên, `@Nested` có thể chia sẻ context; `@TestInstance(PER_CLASS)` giữ test instance; và `@RepeatedTest` không có nghĩa business state/database được dọn cho mỗi lần lặp. Vì vậy:

- Stub ở mỗi invocation hoặc `@BeforeEach`.
- Dùng ID dữ liệu riêng hoặc fixture cleanup có kiểm soát.
- Không dựa vào test order.
- Test kết quả theo ID của scenario, không theo `repository.count()` toàn DB.

### 8.3. Chạy song song trên cùng mocked Spring bean

Hai test methods/classes có thể chia sẻ **cùng cached context và mock bean**. Nếu chúng chạy song song, một test đang gọi/verify mock trong khi test kia reset hoặc stub nó, dẫn đến race và kết quả không xác định. Mockito cũng không bảo đảm an toàn khi một thread reset mock **đồng thời** thread khác đang sử dụng nó.

Các lựa chọn phù hợp:

1. Không chạy song song những integration tests chia sẻ mock/context mutable.
2. Tách test contexts hoặc profiles khi cần isolation mạnh; cân nhắc chi phí bootstrap.
3. Với các workflow nhiều pha, dùng một test có checkpoint rõ ràng và **chờ async hoàn tất**.
4. Nếu phải parallelize, thiết kế collaborators/fixtures theo scope riêng, không chỉnh stubs của một singleton mock chung.

Annotation `@Execution(SAME_THREAD)` tại **một** lớp có thể giúp điều khiển tests trong lớp đó, nhưng không đủ bảo đảm mọi lớp khác dùng cùng context sẽ không chạy đồng thời. Chính sách test parallelism cần thống nhất ở suite/CI.

### 8.4. Mock khác object được inject vào service

Nếu bạn tự tạo:

~~~java
InventoryAvailability local =
        org.mockito.Mockito.mock(InventoryAvailability.class);
org.mockito.Mockito.reset(local);
~~~

thì chỉ `local` bị reset. Nếu `OrderService` inject bean `@MockitoBean InventoryAvailability inventory` từ Spring context, `local` **không phải đối tượng mà service đang gọi**. Reset/verify nhầm một mock khác sẽ cho bằng chứng sai. Dùng đúng field được Spring Test inject vào SUT hoặc vào test, không tạo thêm mock cùng type không kết nối với SUT.

## 9. Chẩn đoán test nhiễu: phân biệt rò stubbing, rò invocation và rò business state

Một lỗi chỉ xuất hiện khi chạy **cả lớp**, nhưng biến mất khi chạy **một test**, chưa chắc do Mockito reset sai. Hãy xác định bằng chứng đang bị nhiễu ở lớp nào:

| Triệu chứng | Khả năng cần kiểm tra | Xác minh và sửa đúng tầng |
| --- | --- | --- |
| `TooManyActualInvocations` ở step B trong **cùng method**. | Invocation A còn trong mock. | Assert A trước; nếu cần kiểm tra riêng B thì `clearInvocations` sau checkpoint. |
| Step B bị từ chối dù A đã stub `true`. | Có `reset(mock)` giữa steps, mất stubbing. | Thay bằng `clearInvocations` hoặc stub B rõ ràng. |
| Test method B nhận stub từ method A. | Có `MockReset.NONE`, stubbing ngoài per-test setup hoặc reset listener không chạy. | Dùng `MockReset.AFTER`, stub trong từng method, kiểm tra test integration setup. |
| B fail chỉ khi chạy song song. | Một test khác stub/reset cùng cached mock. | Cô lập contexts/disable parallel cho tests chia sẻ mock. |
| Mock đã reset nhưng `repository.count()` vẫn lớn. | Database không được dọn. | Fixture/cleanup transaction, ID riêng; không gọi thêm `Mockito.reset`. |
| `PublishedEvents` vẫn có hai event sau `clearInvocations`. | Event collector không phải mock inventory. | Lọc `matching(OrderSubmitted::orderId, id)`; xác định scope của collector. |
| Invocation xuất hiện *sau* test A khi B đang chạy. | Async listener xử lý muộn. | Chờ outcome A hoàn tất; kiểm tra registry/retry, không reset đang chạy. |
| `verify` không thấy lời gọi, dù service đã chạy. | Verify nhầm mock tự tạo, qualifier/bean override khác, hoặc gọi ngoài module. | Kiểm tra object Spring inject; không tự tạo mock thay thế trong test. |
| `reset(spy)` xong DB vẫn có audit row. | Spy đã chạy real method. | Dọn dữ liệu thật; bỏ spy khi không cần quan sát invocations. |
| Sau `@DirtiesContext` test vẫn còn bản ghi trùng. | Database/container vẫn được tái sử dụng. | Cleanup DB theo schema/tenant; dựng lại context không xóa DB. |

### 9.1. Quy trình debug tối thiểu có thứ tự

1. **Khoanh vùng:** lỗi chỉ xảy ra trong một method nhiều bước, giữa hai JUnit methods, giữa hai lớp hay chỉ khi parallel?
2. **Kiểm tra kiểu mock:** `@Mock` của MockitoExtension, `@MockitoBean`/Boot `@MockBean`, hay spy? Mock có thật sự là bean đang được SUT dùng?
3. **Đọc reset mode:** mặc định `AFTER`, hay đã bị đổi thành `NONE`? Test dùng `@BeforeAll` hay setup static chia sẻ?
4. **Đếm lời gọi trước/sau checkpoint:** assertion A thực sự chạy trước `clearInvocations` chưa? Có callback A nào chưa hoàn tất không?
5. **Kiểm tra stubbing:** `reset` đã xóa cấu hình chưa? Sequential `thenReturn` đang ở phần tử nào?
6. **Xem state ngoài mock:** query DB bằng business ID; kiểm tra event/registry/queue/cache thay vì reset Mockito lặp lại.
7. **Kiểm tra isolation:** unique IDs, cleanup đúng schema, Spring context cache và parallel execution.
8. **Kiểm tra module boundary:** `ApplicationModules.verify()` nếu mock được tạo chỉ để bù cho việc gọi vào package nội bộ module khác.

### 9.2. Khi cần chứng minh reset tự động của chính test setup

Nếu một suite nghi ngờ auto reset không chạy, có thể tạo một **bài test chẩn đoán tạm thời** bằng mock do Spring quản lý:

~~~java
@Test
void diagnosticStartsWithNoInventoryInteractions() {
    // Chỉ dùng khi context startup/fixtures không gọi inventory.
    org.mockito.Mockito.verifyNoInteractions(inventory);
}
~~~

Test này chỉ có ý nghĩa khi nó **không phụ thuộc test nào đã chạy trước**, và context initialization không cố ý gọi inventory. Đừng giữ một test chỉ xanh khi phương thức khác chạy trước/không chạy trước. Một giải pháp ổn định hơn là xác lập đúng reset mode, per-test stubbing và đảm bảo async outcome hoàn tất.

## 10. Quality gate, bài tập và checklist cho reset theo scenario

### 10.1. Ma trận kiểm thử có trọng tâm

| Quality gate | Cần giữ chắc | Test phù hợp |
| --- | --- | --- |
| **Unit mock lifecycle** | `clearInvocations` giữ stubs; `reset` xóa cả hai. | JUnit + Mockito test ở mục 2. |
| **Per-method isolation** | Stubbing của method A không ảnh hưởng B. | `@ApplicationModuleTest` với `MockReset.AFTER`, stub riêng từng method. |
| **Within-method checkpoint** | Verify A rồi mới clear; B được đếm riêng. | Test hai stimuli ở mục 5. |
| **Correct negative path** | Mock `false` không làm lưu order/phát `OrderSubmitted`. | DB thật + `PublishedEvents`, lọc `orderId`. |
| **Async completion** | Không reset khi listener A còn xử lý. | `Scenario`/Awaitility với business side effect hoặc registry state. |
| **Context/parallel isolation** | Không có reset/stub race giữa tests chia sẻ context. | Test suite policy, cấu hình parallelism và context fixtures. |
| **Persistent state isolation** | Reset mock không bị dùng thay cleanup database/broker. | JPA/integration fixtures, state assertions theo ID. |
| **Architecture** | `orders` chỉ phụ thuộc `catalog :: api`. | `ApplicationModules.of(ShopApplication.class).verify()`. |

Architecture gate chạy độc lập:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test architecture xác minh các quy tắc module dependency, public/named interface và cycle theo Spring Modulith; nó **không reset Mockito** hoặc kiểm chứng transaction/event processing. Quality gates bổ sung cho nhau, không thay thế nhau.

### 10.2. Bài tập: sửa suite chỉ chạy xanh khi chạy riêng

Một team có class test sau:

~~~java
@ApplicationModuleTest
class FragileOrderTests {

    @MockitoBean(reset = MockReset.NONE)
    InventoryAvailability inventory;

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    @Test
    void firstScenario() {
        UUID skuId = UUID.randomUUID();
        when(inventory.isAvailable(skuId, 1))
                .thenReturn(true);
        orders.place(UUID.randomUUID(), skuId, 1);
        verify(inventory).isAvailable(skuId, 1);
    }

    @Test
    void secondScenario() {
        // Không stub cho SKU được dùng tại đây.
        orders.place(UUID.randomUUID(),
                UUID.randomUUID(), 1);
    }
}
~~~

Đoạn này là **tình huống cố ý có lỗi**, cần imports từ các phần trước. Câu hỏi:

1. Vì sao `MockReset.NONE` có thể làm invocation/stubbing từ một method ảnh hưởng method khác qua Spring cached context?
2. Vì sao `secondScenario` không thể mặc nhiên giả định tồn kho có sẵn?
3. Nếu thêm `reset(inventory)` ở đầu mọi method, test đã có bằng chứng database/event và async isolation chưa?
4. Muốn B dùng một stub `true` riêng, nên thay đổi test thế nào mà không phụ thuộc thứ tự A/B?
5. Nếu A và B là hai pha trong **cùng một test**, nên dùng `clearInvocations` ở điểm nào?
6. Nếu A phát event tới một `@ApplicationModuleListener` async và listener dùng mock gateway, khi nào được bắt đầu B?

**Đáp án và cách sửa:**

1. Với `NONE`, Spring Test không auto-reset; cached mock có thể giữ stubs/invocations. Chuyển về `@MockitoBean(reset = MockReset.AFTER)` mặc định, trừ khi có lý do và quản lý isolation đặc biệt.
2. Mockito trả default `false` cho boolean chưa stub; method B có thể ném `OutOfStockException`. Điều này phản ánh setup thiếu, không nhất thiết phản ánh business defect.
3. Chưa. Mockito reset chỉ xóa state của mock; rows, event collector, registry và async tasks là state khác.
4. B tạo `skuId` cụ thể, `when(inventory.isAvailable(skuId, 1)).thenReturn(true)`, rồi assert row/event theo `orderId` của B; hai tests tự chứa.
5. Verify đầy đủ behavior A, bảo đảm mọi async work cần thiết của A đã hoàn tất, **rồi** `clearInvocations` nếu mục tiêu là đếm riêng B và muốn giữ stub. Nếu mục tiêu đếm tổng, không clear mà verify `times(2)`.
6. Chỉ sau khi có bằng chứng phù hợp cho A — ví dụ một state bền vững đã commit hoặc outcome được `Scenario` chờ đúng cách. `PublishedEvents` thấy event producer chưa đủ chứng minh receiver hoàn tất.

### 10.3. Checklist trước khi merge

- [ ] Đã chỉ rõ “scenario” là **một JUnit method** hay **một pha trong cùng method**.
- [ ] `@MockitoBean` dùng reset mode phù hợp; ưu tiên `AFTER` mặc định.
- [ ] Không đặt stubbing dùng xuyên tests ở `@BeforeAll` rồi trông chờ nó tồn tại sau reset.
- [ ] Mỗi test tự quyết định input/stub và không phụ thuộc test order.
- [ ] Nếu chỉ muốn làm rỗng invocation history, dùng `clearInvocations`, không `reset`.
- [ ] Nếu `reset` được dùng có chủ đích, đã stub lại toàn bộ behavior cần thiết.
- [ ] Nếu dùng sequential `thenReturn`, hiểu `clearInvocations` không quay lại answer đầu.
- [ ] Nếu clear giữa pha A/B, đã verify A trước khi clear để không che lỗi của A.
- [ ] Mock được verify/reset chính là bean đang inject vào SUT, không phải mock local khác.
- [ ] `@ApplicationModuleTest` chỉ mock public collaborator ngoài module; repository và publisher thật khi cần bằng chứng DB/event.
- [ ] Assertions về event và row được lọc theo business ID, không nhầm reset mock với cleanup.
- [ ] Với listener async, test chờ **outcome A** trước khi clear/reset hoặc kết thúc test.
- [ ] Không dùng `Thread.sleep` cố định để chữa race; dùng `Scenario`/Awaitility với condition.
- [ ] Context cache và parallel test policy không cho các methods/classes reset cùng mock đồng thời.
- [ ] Không dùng `@DirtiesContext` như cách mặc định chỉ để dọn mock history.
- [ ] Nếu spy chạy real side effect, dữ liệu/caches được cô lập bằng cơ chế riêng.
- [ ] Có `ApplicationModules.verify()` và quality gates cho transaction/event khi tính đúng đắn cần chúng.

**Kết luận:** Để reset mock giữa các scenario, hãy **chọn đúng ranh giới**. Hai phương thức JUnit với `@MockitoBean` thường đã được Spring Test reset tự động theo `MockReset.AFTER`; không cần gọi `Mockito.reset` thủ công. Hai pha trong cùng một method chỉ nên dùng `clearInvocations` sau khi pha trước đã được xác minh đầy đủ, vì nó giữ stubbing; `reset` xóa cả stubbing và dễ tạo nhánh nghiệp vụ giả. Trong Spring Modulith, lifecycle của mock phải được đặt cạnh transaction, `PublishedEvents`, listener async, registry và state database: **không một API reset Mockito nào thay thế kiểm chứng và cô lập state thật**.

### Tài liệu tham khảo

- [Spring Framework — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, reset modes và Spring Test integration.
- [Spring Framework — TestContext Framework, context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): dùng lại ApplicationContext và yêu cầu isolation.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents`, `Scenario`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional/async module listeners và publication lifecycle.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): named interface và `ApplicationModules.verify()`.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `reset`, `clearInvocations`, stubbing và verification.
- [JUnit 5 — Test Instance Lifecycle](https://junit.org/junit5/docs/current/user-guide/#writing-tests-test-instance-lifecycle): `PER_METHOD` và `PER_CLASS`.

> Ghi chú tương thích: ví dụ giả định Spring Framework 6.2+, Spring Modulith test support, Spring Boot/JPA, Mockito và JUnit 5 với cấu hình schema/transaction phù hợp; phiên bản cũ có thể sử dụng Boot `@MockBean` và `MockReset` ở package khác. Những snippets trong một lớp cần imports và fixtures tương ứng. Đây là bước STEP_4 biên soạn kiến thức, **chưa chạy Gradle hoặc Content QA chuyên môn**.
