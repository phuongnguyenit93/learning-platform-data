# Tách test structural nhanh khỏi integration test chậm

## 1. Tách theo loại bằng chứng, không chỉ theo số giây chạy

Một thay đổi rất nhỏ trong ứng dụng Spring Modulith, chẳng hạn `orders` import một class thuộc `inventory.internal`, có thể vi phạm ranh giới module mà **không cần khởi động database, application context hoặc broker** để phát hiện. Nếu đưa phép kiểm tra ấy vào `@SpringBootTest`, mỗi lần sửa kiến trúc lại phải chờ context bootstrap, migrations và có thể cả Testcontainers — chi phí không liên quan đến loại lỗi cần bắt.

Ở chiều ngược lại, một test chạy `ApplicationModules.verify()` xanh **không chứng minh** rằng `OrderRepository` được Spring Data JPA tạo, bean `StockAvailability` thật wire đúng, transaction commit hoặc `OrderSubmitted` đã đi qua Spring event publisher.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu là kiểm chứng ranh giới kiến trúc qua `ApplicationModules` và quy tắc phụ thuộc module, thực hành `@ApplicationModuleTest` cho event, database và tích hợp, kết hợp quality gate CI để ngăn phụ thuộc sai/hồi quy. Bài thuộc chương **Performance tests** và trực tiếp giải quyết câu hỏi **“Tách test structural nhanh khỏi integration test chậm”**.

**Quy tắc:** Chọn tầng test **rẻ nhất có thể đưa ra đúng bằng chứng**, nhưng không dùng test rẻ để suy ra một điều chỉ integration test thật mới chứng minh được.

| Trục phân loại | Structural test | Integration test |
| --- | --- | --- |
| **Câu hỏi chính** | Các module có tuân thủ dependency graph và API boundaries không? | Spring có bootstrap đúng bean và thực hiện đúng transaction/DB/event không? |
| **Ví dụ** | `ApplicationModules.of(ShopApplication.class).verify()`. | `@ApplicationModuleTest`, JPA repository thật, `PublishedEvents`. |
| **Có Spring ApplicationContext?** | **Không cần** với ví dụ structural bên dưới. | **Có**, bootstrap phạm vi module hoặc ứng dụng. |
| **Có DB/broker?** | Không, nếu chỉ xác minh module structure. | Tùy contract; DB thật cho persistence, broker cho externalization. |
| **Loại lỗi chính** | Module cycles, import internals, `allowedDependencies` sai. | Missing beans, SQL/migration, rollback, wiring, listener/transport. |
| **Chi phí phổ biến** | Không có Spring context/DB startup; thường thấp. | Context scan/bean creation, migrations, containers và I/O. |
| **Kết luận không được suy ra** | Context chắc chắn khởi động, DB commit, listener hoàn tất. | Có thể chứng minh architecture hợp lệ chỉ nhờ happy-path pass. |

“Nhanh” và “chậm” là **đặc tính đo được của suite**, không phải cam kết tốc độ cố định của framework. `ApplicationModules.verify()` vẫn phải phân tích classpath/bytecode và có thể kích hoạt quy tắc jMolecules/ArchUnit bổ sung tùy classpath. Ngược lại, một `@ApplicationModuleTest` nhỏ dùng context cache có thể chạy khá nhanh ở lượt warm. Nhưng việc **không cần Spring context** vẫn là ranh giới quan trọng để dành structural checks cho feedback sớm.

### Sơ đồ hai đường kiểm chứng

~~~mermaid
flowchart TD
    C["Thay đổi Java / module dependency"] --> S["Structural gate: JUnit + ApplicationModules.verify"]
    S -->|"PASS"| I["Integration gate: @ApplicationModuleTest"]
    S -->|"FAIL"| F["Sửa import / cycle / allowedDependencies"]
    I -->|"PASS"| E["Full wiring / DB / event / external integration tùy rủi ro"]
    I -->|"FAIL"| D["Sửa Spring bean / transaction / database / listener"]
~~~

Một cách vận hành phù hợp là **fail fast**: kiến trúc sai thì không cần trả chi phí hạ tầng tích hợp để biết PR chưa đủ điều kiện. Khi structural xanh, integration mới tiếp tục đưa ra bằng chứng runtime. Hai gate có thể chạy song song khi thời gian tổng quan trọng hơn tiết kiệm tài nguyên; nếu muốn thực sự tiết kiệm chi phí CI, đặt dependency để integration chỉ chạy sau fast gate.

## 2. Structural test bằng ApplicationModules.verify(): không cần Spring context

Giả sử package root của ứng dụng là `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── api
│   │   ├── StockAvailability.java
│   │   └── package-info.java
│   └── internal
│       └── StockRepository.java
└── orders
    ├── OrderService.java
    ├── package-info.java
    ├── events
    │   ├── OrderSubmitted.java
    │   └── package-info.java
    └── internal
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

Module `inventory` công bố một API mà `orders` được phép sử dụng:

~~~java
// com/example/shop/inventory/api/StockAvailability.java
package com.example.shop.inventory.api;

import java.util.UUID;

public interface StockAvailability {
    boolean isAvailable(UUID skuId, int quantity);
}
~~~

~~~java
// com/example/shop/inventory/api/package-info.java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.inventory.api;
~~~

Module `orders` giới hạn dependencies:

~~~java
// com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory :: api")
package com.example.shop.orders;
~~~

Kiểm tra cấu trúc **không cần** `@SpringBootTest`, `@Autowired`, `@ApplicationModuleTest`, datasource hay `@MockitoBean`:

~~~java
// src/test/java/com/example/shop/ModuleStructureTests.java
package com.example.shop;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

@Tag("structural")
class ModuleStructureTests {

    @Test
    void moduleDependenciesFollowPublishedBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là JUnit 5 test thông thường: `ApplicationModules` đọc mô hình các application modules và xác minh quy tắc cấu trúc mà **không bootstrap Spring `ApplicationContext`**. `verify()` sẽ ném exception khi có vi phạm. Các nhóm quy tắc chính gồm:

- Không có vòng phụ thuộc giữa các application modules.
- Không truy cập các type thuộc **internal packages** của module khác khi không được công bố qua API/named interface (có ngoại lệ theo mô hình open modules).
- Tuân thủ `@ApplicationModule(allowedDependencies = ...)` nếu được khai báo.
- Có thể có các quy tắc bổ sung khi tích hợp jMolecules/ArchUnit trên classpath.

### 2.1. Structural mutation phải làm test đỏ

Giả sử developer thay `StockAvailability` bằng repository nội bộ:

~~~java
// SAI: class thuộc orders import implementation detail inventory.
import com.example.shop.inventory.internal.StockRepository;
~~~

Từ góc nhìn JPA, code vẫn có thể compile; từ góc nhìn Spring Modulith, đây là **đường dependency sai kiến trúc**. `ModuleStructureTests` phải thất bại vì truy cập type không được công bố và/hoặc trái `allowedDependencies`.

Tương tự, nếu `orders` được phép gọi `inventory :: api` nhưng lại import `billing.api.PaymentGateway` mà không có dependency được cho phép, structural gate cần bắt lỗi, kể cả khi một `@SpringBootTest` đầy đủ có đủ các beans để context khởi động.

**Bằng chứng quan trọng:** Test phát hiện *thao tác vi phạm cấu trúc*, không cần gửi HTTP request, không cần rollback transaction và không cần nhìn vào DB state.

### 2.2. Lỗi structural không phải lỗi bootstrap

Đừng “sửa” một structural violation bằng:

~~~java
@MockitoBean StockRepository inventoryRepository;
~~~

Mock chỉ thay bean trong Spring context; dependency từ code `orders` sang `inventory.internal.StockRepository` vẫn tồn tại. Cách sửa là **đi qua `inventory.api.StockAvailability`**, công bố named interface hợp lệ nếu thật sự cần, hoặc thay thiết kế module.

Một hiểu nhầm khác: thêm `@ApplicationModuleTest` lên `ModuleStructureTests` làm nó “mạnh hơn”. Nó chỉ thêm chi phí bootstrap và chuyển mục tiêu của structural check thành hỗn hợp khó chẩn đoán; **không có lý do kỹ thuật để mở context chỉ để gọi `verify()`**.

### 2.3. Vì sao không gộp với unit tests khác?

Có thể để structural và unit tests chạy trong cùng Gradle `test` task vì cả hai đều không cần nạp Spring context; nhưng giữ **class riêng** và `@Tag("structural")` để:

1. Biết một thay đổi làm gãy architecture hay một business rule.
2. Có thể chạy riêng structural checks khi cần phản hồi tức thời.
3. Theo dõi tổng thời gian structural gate độc lập với unit suite.
4. Đảm bảo cấu hình Gradle/CI **không bỏ sót** structural tests.

## 3. Integration test: kiểm tra runtime behavior mà structural test không thấy

Để phân biệt rõ, ta dùng **cùng hệ thống orders/inventory** nhưng viết một test có mục tiêu khác: khi tồn kho đáp ứng, Spring-managed `OrderService` có lưu `OrderEntity` và phát `OrderSubmitted` đúng không?

Đây là nơi **cần** `@ApplicationModuleTest`, JPA và transaction.

### 3.1. Mã use case tối thiểu

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

    protected OrderEntity() {} // Dành cho JPA.

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

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.inventory.api.StockAvailability;
import com.example.shop.orders.events.OrderSubmitted;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class OrderService {

    private final StockAvailability stock;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(StockAvailability stock,
                        OrderRepository orders,
                        ApplicationEventPublisher events) {
        this.stock = stock;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId, UUID skuId, int quantity) {
        if (orderId == null || skuId == null || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        if (!stock.isAvailable(skuId, quantity)) {
            throw new IllegalStateException("Out of stock");
        }

        orders.save(new OrderEntity(orderId, skuId, quantity));
        events.publishEvent(
                new OrderSubmitted(orderId, skuId, quantity));
    }
}
~~~

**Giới hạn thiết kế:** `StockAvailability.isAvailable` không phải phép giữ hàng atomic; ví dụ chỉ kiểm chứng hành vi module. Một inventory contract thực cần xử lý concurrent reservations nếu nghiệp vụ yêu cầu.

### 3.2. @ApplicationModuleTest(STANDALONE) với DB/event thật

Lớp test đặt trong `com.example.shop.orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.inventory.api.StockAvailability;
import com.example.shop.orders.events.OrderSubmitted;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@Tag("integration")
@ApplicationModuleTest
class OrdersModuleIntegrationTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    // Mock public API thuộc inventory, ngoài scope STANDALONE.
    @MockitoBean StockAvailability stock;

    @Test
    void acceptsOrderAndPublishesEvent(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        when(stock.isAvailable(skuId, 2)).thenReturn(true);

        service.place(orderId, skuId, 2);

        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order -> {
                    assertThat(order.getSkuId()).isEqualTo(skuId);
                    assertThat(order.getQuantity()).isEqualTo(2);
                });

        assertThat(events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::orderId, orderId))
                .singleElement()
                .satisfies(event ->
                        assertThat(event.quantity()).isEqualTo(2));
    }

    @Test
    void rejectsOrderWithoutPersistenceOrEvent(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        when(stock.isAvailable(skuId, 2)).thenReturn(false);

        assertThatThrownBy(() ->
                service.place(orderId, skuId, 2))
                .isInstanceOf(IllegalStateException.class);

        assertThat(repository.existsById(orderId)).isFalse();
        assertThat(events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::orderId, orderId))
                .isEmpty();
    }
}
~~~

Hai test này cần Spring Data JPA starter, transaction manager, test datasource/schema `shop_orders` và Spring Modulith test starter. Với Spring Framework 6.2+, `@MockitoBean` là annotation thay/tạo bean; version Boot cũ có thể dùng `@MockBean` ở package khác. Ở `STANDALONE`, mocking public collaborator ngoài module là **cô lập có chủ đích**, không phải mock nội bộ của `orders`.

**Đừng gắn `@Transactional` lên test class** nếu muốn lời gọi `service.place` tự mở/commit transaction rồi đọc lại row. Một outer test transaction có thể giữ row chưa commit và tự rollback cuối test.

### 3.3. Những bằng chứng mà test này bổ sung

| Structural xanh | Module integration xanh |
| --- | --- |
| `orders` chỉ phụ thuộc `inventory :: api`. | `OrderService` được Spring instantiate/inject thành công. |
| Không có illegal import/cycle theo mô hình module. | JPA repository thật được tạo và có thể ghi/đọc order. |
| API dependency graph hợp lệ. | Transaction/service behavior của nhánh thành công/thất bại chạy thật. |
| **Không nói gì** về event publication. | `PublishedEvents` quan sát đúng event producer đã phát. |

`PublishedEvents` **không tự chứng minh** listener của module khác hoàn tất hay broker nhận message. Test JPA cũng không tự chứng minh provider inventory thật có bean khi bị thay bằng mock. Đó là những integration contracts riêng.

## 4. Đối chứng integration thật: DIRECT_DEPENDENCIES và producer contract

Nếu chỉ có structural test và `OrdersModuleIntegrationTests` với `StockAvailability` mock, cả hai có thể xanh khi `inventory` **không còn một bean triển khai `StockAvailability` nào**. Structural gate không bootstrap Spring; isolated integration gate cố ý dùng mock để thay module ngoài. Đây không phải lỗi thiết kế các test riêng lẻ, mà là **khoảng trống bằng chứng của cả suite**.

Hãy bổ sung một **integration test có mục tiêu wiring**:

~~~java
package com.example.shop.orders;

import com.example.shop.inventory.api.StockAvailability;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;

@Tag("integration")
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersInventoryWiringTests {

    @Autowired OrderService service;
    @Autowired StockAvailability stock;

    @Test
    void realInventoryPortIsAvailable() {
        assertThat(service).isNotNull();
        assertThat(stock).isNotNull();
        assertThat(mockingDetails(stock).isMock()).isFalse();
    }
}
~~~

**Không thêm `@MockitoBean StockAvailability` vào bài wiring này.** `DIRECT_DEPENDENCIES` khởi động `orders` và `inventory` (module phụ thuộc trực tiếp). Nếu `inventory` được kỳ vọng có `StockAvailability` implementation mà thiếu vì component scan, `@Profile`, `@ConditionalOnProperty` hoặc configuration hỏng, context **phải thất bại**. `@MockitoBean` mặc định có thể tạo bean mới nếu không có target, làm mất chính tín hiệu bootstrap mà test cần bảo vệ.

Để test thực sự có bean, module `inventory` có thể triển khai port bằng Spring Data JPA:

~~~java
// inventory/internal/InventoryStock.java
package com.example.shop.inventory.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.UUID;

@Entity
@Table(name = "inventory_stock")
public class InventoryStock {
    @Id private UUID id;

    @Column(nullable = false)
    private int available;

    protected InventoryStock() {}

    public InventoryStock(UUID id, int available) {
        this.id = id;
        this.available = available;
    }

    public UUID getId() { return id; }
    public int getAvailable() { return available; }
}
~~~

~~~java
// inventory/internal/InventoryStockRepository.java
package com.example.shop.inventory.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryStockRepository
        extends JpaRepository<InventoryStock, UUID> {}
~~~

~~~java
// inventory/internal/JpaStockAvailability.java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.api.StockAvailability;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class JpaStockAvailability implements StockAvailability {

    private final InventoryStockRepository stocks;

    public JpaStockAvailability(
            InventoryStockRepository stocks) {
        this.stocks = stocks;
    }

    @Override
    public boolean isAvailable(UUID skuId, int quantity) {
        if (quantity <= 0) return false;
        return stocks.findById(skuId)
                .map(row -> row.getAvailable() >= quantity)
                .orElse(false);
    }
}
~~~

`OrdersInventoryWiringTests` khởi động các beans thật và phát hiện lỗi autowiring, nhưng mới kiểm tra **bean presence**. Để kiểm chứng behavior của producer, thêm bài test **bên trong module inventory**, nơi được phép truy cập repository nội bộ của chính nó:

~~~java
package com.example.shop.inventory;

import com.example.shop.inventory.api.StockAvailability;
import com.example.shop.inventory.internal.InventoryStock;
import com.example.shop.inventory.internal.InventoryStockRepository;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
@ApplicationModuleTest
class InventoryContractTests {

    @Autowired InventoryStockRepository stocks;
    @Autowired StockAvailability availability;

    @Test
    void stockQueryUsesPersistedQuantity() {
        UUID skuId = UUID.randomUUID();
        stocks.save(new InventoryStock(skuId, 3));

        assertThat(availability.isAvailable(skuId, 2)).isTrue();
        assertThat(availability.isAvailable(skuId, 4)).isFalse();
    }
}
~~~

Với `InventoryContractTests`, cần datasource/schema `inventory_stock` và transaction manager thật. Bài test không mở transaction ở test method; các lệnh repository tự dùng transaction thích hợp theo cấu hình Spring Data và giá trị được truy vấn thực. Nếu cần kiểm chứng concurrency/reservation, phải có tests khác vì `isAvailable` chỉ là phép đọc.

### 4.1. Ranh giới tốc độ và bằng chứng sau khi thêm đối chứng

| Gate | Nếu xóa `@Service` trên `JpaStockAvailability` | Nếu `OrderService` import `inventory.internal` |
| --- | --- | --- |
| `ModuleStructureTests` | Có thể vẫn xanh: cấu trúc package/dependency không đổi. | **Đỏ**, vi phạm public boundary/allowed dependency. |
| `OrdersModuleIntegrationTests` với mock | Có thể vẫn xanh: external port được mock chủ đích. | Không có nghĩa structural violation được hợp thức hóa. |
| `OrdersInventoryWiringTests` không mock | **Đỏ** do bean implementation thiếu. | Có thể còn bootstrap được nếu thiếu gate structural. |
| `InventoryContractTests` | **Đỏ** vì thiếu producer implementation. | Không nhất thiết thấy import sai ở consumer. |

Điều này giải thích **vì sao structural và integration phải tách mà đều có mặt**. Một loại không thay thế loại kia.

### 4.2. Khi nào dùng ALL_DEPENDENCIES hoặc full SpringBootTest?

Nếu `inventory` còn phụ thuộc module khác, `DIRECT_DEPENDENCIES` có thể không nạp module bắc cầu đó. Đặt mục tiêu rõ:

- `STANDALONE`: chỉ behavior `orders`, ngoài module có thể mock public API.
- `DIRECT_DEPENDENCIES`: cần wiring trực tiếp `orders` ↔ `inventory`.
- `ALL_DEPENDENCIES`: cần bootstrap cây phụ thuộc bắc cầu.
- `@SpringBootTest`: cần smoke toàn bộ bean graph/auto-configuration ở test profile.

**Mode rộng hơn không tự biến test thành tốt hơn**; nó chỉ tăng phạm vi context và đôi khi chi phí, trong khi assertion vẫn có thể quá yếu. Chọn mode theo câu hỏi cần trả lời, không đổi mode chỉ vì một bean thiếu mà chưa biết nguyên nhân.

## 5. Tách bằng JUnit 5 tags và Gradle Test tasks

Mục tiêu cấu hình là:

- **`./gradlew test`** chạy structural và unit tests nhanh, **không khởi động** các integration tests được gắn tag đúng.
- **`./gradlew integrationTest`** chỉ chạy integration tests được gắn `@Tag("integration")`.
- Có thể chạy riêng structural class/tag khi điều tra kiến trúc.
- Test code vẫn có thể nằm trong `src/test/java` để bắt đầu đơn giản; không cần chuyển file tùy tiện sang source set mới chỉ để phân loại.

### 5.1. Tag trên class theo mục tiêu

Structural:

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("structural")
class ModuleStructureTests {
    @Test
    void dependenciesFollowArchitectureRules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là **snippet rút gọn**, cần imports `ApplicationModules` và class `ShopApplication` như mục 2. Nó không dùng Spring Test annotation.

Integration:

~~~java
import org.junit.jupiter.api.Tag;
import org.springframework.modulith.test.ApplicationModuleTest;

@Tag("integration")
@ApplicationModuleTest
class OrdersModuleIntegrationTests {
    // Các @Test methods đều thuộc nhóm integration.
}
~~~

Test có thể dùng class-level `@Tag("integration")` để tránh gắn trên từng method. **Đừng gắn `@Tag("structural")` cho một class sử dụng `@ApplicationModuleTest`** rồi kỳ vọng nó nhanh như pure architecture test: tag chỉ chọn test, không thay đổi bootstrap behavior.

### 5.2. Cấu hình Gradle Groovy DSL có thể áp dụng

Ví dụ trong `build.gradle` (phần cấu hình task; giả định project đã dùng plugin Java/Spring Boot và JUnit Platform):

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        // Unit + structural; tránh integration trong fast task.
        excludeTags 'integration'
    }
}

tasks.register('integrationTest', Test) {
    description = 'Run Spring/DB/module integration tests.'
    group = 'verification'

    // Dùng test sources đã được compile trong source set test.
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }

    shouldRunAfter tasks.named('test')
}
~~~

Khi chạy:

~~~bash
./gradlew test
./gradlew integrationTest
./gradlew test integrationTest
~~~

thì `test` loại `@Tag("integration")`, còn `integrationTest` chỉ lấy tag ấy. `shouldRunAfter` **chỉ đưa ra thứ tự khi cả hai tasks đều được yêu cầu chạy**; nó **không** tạo dependency `integrationTest` vào `test`.

**Lưu ý quan trọng:** Việc định nghĩa `integrationTest` như trên **không tự khiến Gradle `check` chạy integrationTest**. Nếu muốn `check` bao gồm cả integration:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
~~~

Nhưng khi cần CI có **fast gate** riêng và **slow gate** riêng, có thể **không** nối `check` vào `integrationTest`; thay vào đó pipeline gọi task tích hợp rõ ràng tại stage khác. Hãy chọn **một chính sách**, ghi vào README/build conventions và branch protection. Không để `integrationTest` tồn tại nhưng không job nào chạy.

### 5.3. Tag nhầm có thể khiến suite chậm vẫn chạy trong fast task

Điều kiện phân tách chỉ hoạt động nếu mọi Spring/DB integration test đều được **tag đúng**. Nếu một class viết:

~~~java
@ApplicationModuleTest
class AnotherOrdersIntegrationTests {
    // Quên @Tag("integration"): Gradle test vẫn chạy!
}
~~~

thì class ấy sẽ chạy trong `test`, vì bộ lọc `excludeTags 'integration'` chỉ loại tests **có tag**. Hãy kiểm tra test reports và bổ sung convention/architecture rule cho test code nếu cần, thay vì tin rằng tên lớp `*IntegrationTests` tự động được JUnit phân loại.

Ngược lại, nếu class **không có tag `integration` nhưng chỉ được mong chạy ở `integrationTest`**, nó sẽ bị bỏ qua ở task đó; trong cấu hình trên, nó có thể chạy ở `test` và làm chậm fast gate.

### 5.4. Lựa chọn source set riêng

Khi số integration tests tăng, có thể tách `src/integrationTest/java` và source set riêng để kiểm soát dependencies, resources, Testcontainers và parallelism. Đây là **biện pháp tổ chức**, không bắt buộc ngay từ đầu. Với một số ít bài kiểm tra, tags + hai Test tasks thường đủ để tách thời gian chạy. Nếu chọn source set riêng, phải cấu hình compile/runtime classpaths và tasks đúng; không nên chỉ tạo folder mà kỳ vọng Gradle tự discover mọi test trong đó.

## 6. CI pipeline: fast feedback trước, integration evidence sau

Một pipeline nên thể hiện được **hai câu hỏi riêng**:

1. *Có vi phạm cấu trúc module hoặc unit rule không?* → trả lời nhanh.
2. *Các module có bootstrap, truy vấn DB, commit transaction và phát event thật không?* → trả lời ở integration stage, có thể dùng Testcontainers.

Ví dụ job phụ thuộc trong GitHub Actions (**mẫu minh họa**, cần điều chỉnh JDK, caching, database services và branch protection theo project):

~~~yaml
name: modulith-verification

on:
  pull_request:
  push:
    branches: [main]

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Unit and structural checks
        run: ./gradlew test --no-daemon

  integration:
    needs: fast
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Module and database integration checks
        run: ./gradlew integrationTest --no-daemon
~~~

`integration` chạy **sau khi `fast` thành công**. Nếu `ModuleStructureTests` phát hiện illegal import, integration không cần khởi động container trong workflow này. Trường hợp tổ chức muốn giảm wall-clock latency, có thể chạy hai jobs song song nhưng chấp nhận lãng phí compute khi structural gate đỏ.

### 6.1. Branch protection không chỉ kiểm tra job fast

Nếu PR chỉ bắt buộc job `fast` xanh để merge, còn integration luôn “optional”, hồi quy DB/bean/event vẫn có thể được merge. Cần chính sách rõ:

| Tình huống | Phương án phù hợp |
| --- | --- |
| Integration có thể hoàn tất trong SLA PR | Bắt buộc cả `fast` và `integration` xanh trước merge. |
| Integration rất nặng | Chạy một tập **module integration trọng yếu** ở PR, full suite ở merge queue/nightly; có cơ chế chặn/revert khi fail. |
| Thay đổi code thuần nhưng architecture dễ bị phá | Structural luôn bắt buộc trên mọi PR. |
| Thay đổi migration, transaction, event consumer | Bổ sung integration gate phù hợp theo phạm vi; không chỉ dựa vào structural. |

Không đặt ra một ngưỡng giây tùy tiện rồi loại integration khỏi CI. Đo chi phí thực, rủi ro hồi quy và mức độ tin cậy của từng gate trước khi quyết định cadence.

### 6.2. Tránh báo cáo xanh giả vì task chưa discover test

Một `integrationTest` task có thể kết thúc **thành công nhưng chạy 0 tests** nếu thiếu tag, classpath sai hoặc engine chưa được cấu hình. Đó là lỗi nguy hiểm hơn một suite chậm:

- Kiểm tra XML/JUnit reports hoặc Gradle test summary để thấy tên/tổng số tests được thực thi.
- Xem `@Tag("integration")` có nằm ở class-level đúng hay không.
- Đảm bảo task dùng cùng compiled test classes/classpath, hoặc source set riêng được cấu hình đúng.
- Giữ ít nhất một integration smoke test bắt buộc được discover trong stage tích hợp.
- Khi nâng JUnit/Gradle plugin, rà lại cấu hình filters và task wiring.

**“BUILD SUCCESSFUL” không đồng nghĩa “mọi test quan trọng đã được chạy”.** Tách task chỉ có giá trị khi test discovery và báo cáo được xác minh.

## 7. Đo đúng chi phí: cold start, warm context, execution và CI wall-clock

Tách structural khỏi integration là một quyết định về **chi phí phản hồi**. Nhưng không nên dùng cảm giác “test kia chậm” để quyết định xóa test quan trọng khỏi pipeline. Hãy đo cùng một mô hình:

| Chỉ số | Ý nghĩa | Cần ghi nhận |
| --- | --- | --- |
| **Structural execution time** | Thời gian test `ApplicationModules.verify()` phân tích các modules. | Chi phí structural logic, không thêm Spring bootstrap. |
| **Integration test execution time** | Thời gian `@ApplicationModuleTest` và assertions của test method. | Có thể gồm Spring context startup ở method/class đầu. |
| **ApplicationContext startup time** | Thời gian tạo beans, scan, data source, migration. | Cold context vs cached context. |
| **Container startup time** | DB/broker Testcontainers image/start/health check. | Cold Docker/image cache vs container reused trong test run. |
| **Gradle task duration** | Thời gian task `test` hoặc `integrationTest`, gồm worker startup và orchestration. | Build cache, test filtering và fork configuration. |
| **PR job wall-clock** | Từ lúc CI nhận job đến khi báo trạng thái. | Checkout, dependency download, compile, queued time, tests. |

Không dùng các chỉ số thay thế lẫn nhau. Ví dụ, `OrdersModuleIntegrationTests` có thể mất vài giây cho method nhưng container/database startup ở đầu test suite tốn nhiều hơn; gọi nó là “test method chậm” sẽ dẫn đến tối ưu sai chỗ.

### 7.1. Thu số liệu từ Gradle và JUnit reports

Có thể dùng các lệnh **để tham khảo trong workflow thực tế**:

~~~bash
# Fast suite: unit + structural.
./gradlew test

# Slow suite: module/DB/wiring integration.
./gradlew integrationTest

# Hồ sơ thời gian của một build có cả hai tasks.
./gradlew test integrationTest --profile
~~~

`--profile` tạo báo cáo hiệu năng Gradle ở build reports (đường dẫn cụ thể tùy Gradle version/build setup). JUnit XML/HTML test reports thường ghi thời gian của suites/test cases và số lượng tests; dùng chúng cùng task timing để phân biệt bootstrap với execution. **Không chạy những lệnh này trong bước soạn bài STEP_4**; chỉ mô tả cách người học đo khi tích hợp vào dự án.

### 7.2. So sánh cold và warm một cách công bằng

Thực hiện hai nhóm đo có giải thích:

1. **Cold run:** không dựa vào Spring context đã được tạo trong JVM test worker; ghi rõ Docker image/cache/dependency/Gradle daemon có được warm hay không.
2. **Warm run:** chạy lại cùng tập tests với môi trường tương tự và build/test task không bị skip do cache; ghi nhận Spring context caching **bên trong từng worker process**.
3. Lặp lại đủ lần nếu muốn nhận diện variance; không lấy một lượt may mắn làm baseline.
4. Phân biệt elapsed time của **test logic** với startup, DB migration và compilation.
5. So sánh cùng JDK, CPU, container, heap, parallelism và số lượng tests.

Nếu Gradle báo task `UP-TO-DATE` hoặc `FROM-CACHE`, lượt đó **không đo thực thi tests**. Chạy lại tests có chủ đích và đọc báo cáo JUnit tương ứng; khi dùng `--rerun-tasks`, chú ý rằng nó có thể làm chạy lại các task khác như compilation, ảnh hưởng wall-clock của build.

### 7.3. Dữ liệu minh họa để thảo luận ngân sách

Bảng sau là **số liệu giả định**, không phải benchmark của Spring Modulith hoặc kết quả chạy trên workspace:

| Nhóm | Thời gian giả định | Nội dung |
| --- | ---: | --- |
| Structural | 2 giây | Kiểm tra dependency graph 20 modules. |
| Unit | 9 giây | Các business rules thuần Java. |
| Module integration | 70 giây | Context/JPA/migrations và vài module tests. |
| External integration | 150 giây | Broker, network fake server, recovery scenarios. |

Nếu fast gate chỉ có structural + unit, developer có thể nhận phản hồi lỗi import nhanh hơn nhiều so với đợi toàn bộ integration. Nhưng CI vẫn phải **chạy slow gates ở một cadence phù hợp rủi ro** để phát hiện bean/migration/event failures.

### 7.4. Không biến timing thành một assertion JUnit dễ flaky

Đây là **anti-pattern** khi thời gian structural test dao động theo CPU, CI queue hoặc cache:

~~~java
// KHÔNG khuyến khích dùng như gate độ đúng kiến trúc.
assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> ApplicationModules
                .of(ShopApplication.class).verify());
~~~

Giới hạn 2 giây không phải một invariant kiến trúc; trên runner tải cao, test có thể fail dù dependency graph hoàn toàn hợp lệ. `assertTimeoutPreemptively` còn chạy executable trên thread khác, gây khác biệt context/thread-local với code khác nếu tái sử dụng bừa bãi.

Thay vì gắn hard timeout vào structural correctness, **theo dõi trend** task/test durations, cảnh báo khi vượt ngân sách được thống nhất, rồi điều tra nguyên nhân. Một timeout đủ rộng cho CI infrastructure/hang protection có thể hợp lý, nhưng đó là một **operational safeguard**, không phải “verify module đúng”.

## 8. Tối ưu integration suite mà không làm mất bằng chứng

Khi integration gate chậm, phải xác định **tầng chi phí** trước khi “tối ưu” bằng mock toàn bộ repository hay publisher.

### 8.1. Dùng bootstrap scope nhỏ nhất đáp ứng hợp đồng

| Test cần gì? | Chọn | Không nên làm |
| --- | --- | --- |
| Luật module boundary | `ApplicationModules.verify()` không Spring context. | Đưa vào `@SpringBootTest` chỉ để đọc dependency graph. |
| Use case `orders`, DB và event producer | `@ApplicationModuleTest(STANDALONE)` + mock API module ngoài. | `@SpringBootTest` nếu không cần cả app. |
| Wiring `orders` với `inventory` thật | `DIRECT_DEPENDENCIES`. | Mock `StockAvailability` trong chính test wiring. |
| Transitive integration | `ALL_DEPENDENCIES` nếu phải kiểm tra cả cây. | Nạp cả cây trong mọi module test chỉ để tránh thiếu bean. |
| Full application bootstrap, REST wiring | `@SpringBootTest` hoặc test web thích hợp. | Suy toàn app từ một `STANDALONE` test. |
| Repository mapping/constraint cụ thể | `@DataJpaTest` hoặc JPA integration có real database. | Mock repository rồi `verify(save)`. |

`STANDALONE` thường giảm component/entity scan, nhưng nếu test vẫn dùng DB và nhiều auto-configurations, nó không trở thành pure unit test. Vì vậy **đừng mong structural tốc độ bằng cách chỉ chuyển `@SpringBootTest` thành `@ApplicationModuleTest`**; muốn structural thuần hãy bỏ Spring Test bootstrap hoàn toàn.

### 8.2. Tận dụng Spring Test context cache có kiểm soát

Spring Test cache `ApplicationContext` theo cấu hình context. Một suite có quá nhiều biến thể gần giống nhau có thể bootstrap lại nhiều context:

- Khác `@ActiveProfiles`, `@TestPropertySource` hoặc `@DynamicPropertySource`.
- Khác danh sách `@MockitoBean`, qualifier/name hoặc test configuration override.
- Dùng `@DirtiesContext` quá rộng, làm context bị loại khỏi cache.
- Chạy tests qua nhiều forked JVM; cache **không dùng chung giữa JVM workers**.

Một vài hướng cải thiện:

1. Nhóm các tests có cùng bootstrap mode và context configuration.
2. Dùng cấu hình test nhất quán, tránh tạo một profile/bean override chỉ cho mỗi method.
3. Chỉ dùng `@DirtiesContext` khi thực sự cần thay context state không thể khôi phục khác.
4. Không lạm dụng `@MockBean`/`@MockitoBean` với các tên/qualifiers thay đổi vô nghĩa.
5. Đừng đổi tất cả `@ApplicationModuleTest` thành một full context duy nhất chỉ để “cache một lần”; chi phí, độ coupling và ý nghĩa assertions cũng phải được tính.

**Không bỏ mất cô lập state:** Context cache **không dọn DB rows, cache nghiệp vụ hoặc broker offsets**. Dùng UUID/fixtures riêng, cleanup được kiểm soát và test transaction phù hợp. Có thể tối ưu bootstrap trong khi vẫn bảo vệ dữ liệu độc lập.

### 8.3. Testcontainers và migration: tái sử dụng có điều kiện

Testcontainers có thể chiếm phần lớn cold startup của integration stage. Một vài hướng:

- Chạy cùng database vendor/dialect mà production dùng khi kiểm tra native SQL, constraint, locking hoặc migration.
- Tránh tạo một container mới cho **mỗi method** khi có thể cô lập data theo cách khác.
- Dùng setup chung có lifecycle rõ; container reuse giữa suites/JVM phải cân nhắc isolation, CI environment và tính nhất quán dữ liệu.
- Migration nên chạy ở những tests có mục tiêu schema/compatibility; không dùng Hibernate auto DDL để thay bằng chứng migration production.
- Khi đã dùng shared container, dữ liệu của các tests phải được cô lập bằng transaction/cleanup/schema hoặc key riêng; không để việc tiết kiệm startup tạo flaky tests.

**Không** đổi Testcontainers sang `@MockitoBean OrderRepository` rồi nói suite nhanh hơn mà vẫn kiểm tra persistence. Bạn đã đổi **loại bằng chứng**, không đơn thuần cải thiện performance.

### 8.4. Parallelism không mặc nhiên giảm wall-clock

Tăng `maxParallelForks` hoặc JUnit parallel execution có thể:

- Giảm tổng thời gian khi tests CPU-bound và đủ tài nguyên.
- **Tăng** thời gian/độ flaky khi mọi test cạnh tranh cùng DB container, connection pool, file locks hoặc singleton mocks.
- Làm Spring context cache kém hiệu quả nếu nhiều JVM processes được tạo.
- Khiến thứ tự listener async/transaction observations bất ổn hơn.

Tăng parallelism theo số liệu, theo phạm vi state chia sẻ, không theo số CPU đơn thuần. Structural/ArchUnit scanning có thể chạy độc lập với integration containers; nhưng integration tests cùng database cần isolation và connection limits phù hợp.

### 8.5. Đừng dùng mock để che lỗi bootstrap

Một module integration test không start vì thiếu `StockAvailability` của module ngoài trong `STANDALONE`: mock public API là hợp lý. Nhưng nếu không start vì thiếu `OrderRepository`, sai datasource, `BeanCreationException` hoặc migration lỗi, thêm mocks sẽ làm mất bằng chứng cần kiểm tra.

Giữ **structural test** để xác minh dependency graph, **isolated module test** để xác minh use case, và **real wiring test** để kiểm chứng implementation bên ngoài module hiện diện. Đây là tối ưu có chủ đích, không phải bỏ từng thành phần thật cho đến khi test nhanh.

## 9. Kiểm chứng bằng mutation: gate nào phải phát hiện lỗi nào?

Một cách kiểm tra chất lượng việc tách suite là tạo bảng **mutations có chủ đích**: thay đổi một điều khoản kiến trúc hoặc runtime và dự đoán **gate nào bắt buộc đỏ**. Nếu mọi test đều chạy xanh sau một mutation quan trọng, đội ngũ đang có **false confidence**, bất kể thời gian CI nhanh hay chậm.

| Mutation/lỗi giả định | Structural gate | Module integration gate | Gate bổ sung bắt buộc |
| --- | --- | --- | --- |
| `orders` import `inventory.internal.InventoryStockRepository` | **Phải đỏ** vì truy cập internal package/trái allowed dependency. | Có thể vẫn xanh nếu không bootstrap code path ấy. | Architecture riêng là đủ cho rule này. |
| Tạo vòng `orders → billing → orders` | **Phải đỏ** theo module dependency cycle. | Có thể fail bootstrap nhưng không giải thích đúng kiến trúc. | Architecture riêng. |
| Xóa `@Service` trên `JpaStockAvailability` | Có thể xanh vì graph class dependencies vẫn hợp lệ. | `STANDALONE` mock stock có thể xanh. | **DIRECT_DEPENDENCIES**/real wiring phải đỏ. |
| `OrderRepository` thiếu bean vì scan/config sai | Có thể xanh. | **Phải đỏ** nếu không mock repository. | JPA/bootstrap gate. |
| Đổi `orders.save(...)` thành code không ghi DB | Có thể xanh. | **Phải đỏ** tại real DB read-back. | Module persistence. |
| Bỏ `events.publishEvent(...)` | Có thể xanh. | **Phải đỏ** tại `PublishedEvents`. | Producer event test. |
| Listener `AFTER_COMMIT` không được đăng ký | Có thể xanh. | Producer test vẫn có thể xanh. | **Receiver/transaction integration test** phải đỏ. |
| Migration xóa unique constraint | Có thể xanh. | Happy-path insert có thể xanh. | **DB/schema constraint test** phải đỏ. |
| Provider HTTP đổi JSON field | Có thể xanh. | Gateway mock có thể xanh. | **Adapter/provider contract test** phải đỏ. |
| Thêm `@DirtiesContext` vào nhiều integration classes | Structural correctness không đổi. | Assertions có thể xanh, nhưng chạy chậm. | **Duration/context-cache observability** phát hiện performance regression. |
| Quên `@Tag("integration")` trên lớp chậm | Architecture không liên quan. | Test có thể bị chạy nhầm trong fast task. | **Test discovery/tag audit** phải chỉ ra phân loại sai. |

**Không yêu cầu tất cả cột đều đỏ.** Mục tiêu của tách tầng là mỗi loại hồi quy có một **gate sở hữu rõ ràng**: kiến trúc → structural; wiring/DB/event → integration. Nhờ đó message lỗi nhanh và có ý nghĩa hơn so với một `@SpringBootTest` rất lớn thất bại vì lý do không rõ.

### 9.1. Hai anti-pattern làm structural “chậm giả”

**Anti-pattern A: mở context rồi mới verify architecture.**

~~~java
// Không cần @SpringBootTest cho structural-only rule.
@SpringBootTest
class OverBootstrappedArchitectureTests {
    @Test
    void architecture() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đoạn này có thể vẫn phát hiện dependency violation nhưng còn trả chi phí Spring bootstrap, autoconfiguration, DB connection hoặc migration. Thay bằng lớp JUnit thuần ở mục 2.

**Anti-pattern B: dùng integration happy path thay structural test.**

~~~java
@SpringBootTest
class MisleadingArchitectureTests {

    @Autowired OrderService orders;

    @Test
    void orderServiceExists() {
        assertThat(orders).isNotNull();
    }
}
~~~

Bean tồn tại không chứng minh `orders` không import `inventory.internal` hay không có module cycle. Đây là **wiring smoke test** với assertion còn yếu, không phải structural architecture test. Giữ nó nếu thật sự cần smoke, nhưng đừng đổi tên thành architecture verification.

### 9.2. Integration xanh giả do mock hoặc transaction context

Một test `@ApplicationModuleTest` có:

~~~java
@MockitoBean OrderRepository repository;
~~~

và chỉ `verify(repository).save(...)` sẽ không phát hiện migration/table/commit lỗi. Nếu đặt `@Transactional` lên cả test class, query trong transaction có thể nhìn thấy entity chưa commit; đó chưa phải bằng chứng transaction producer đã commit. Với event, `PublishedEvents` ghi nhận **publication tại producer**, không chứng minh listener ngoài module đã completed.

**Tốc độ chỉ là tối ưu sau khi định nghĩa đúng bằng chứng.** Không được giữ PR xanh nhanh bằng cách bỏ chính hạ tầng mà test hứa hẹn kiểm chứng.

### 9.3. Đừng gộp flaky integration vào structural task để “fix CI”

Nếu listener async cần chờ state, thêm `Awaitility` hoặc `Scenario` đúng boundary và kiểm soát transaction/executor. Nếu test phụ thuộc timing/broker/network, giải quyết failure mode ở integration layer. Chuyển tag của nó từ `integration` sang `structural` không giải quyết flaky và còn làm **fast gate chậm/không ổn định**.

Một structural gate đáng tin là nơi các lỗi compile/dependency được phản hồi sớm. Nếu nó cần Docker, credentials, network hoặc thread sleep để chạy, hãy xem lại **test bị phân loại sai**.

## 10. Bài tập, checklist và quyết định áp dụng

### 10.1. Case study: PR mất bốn phút chỉ để phát hiện import sai

Một dự án Spring Modulith có 14 modules. Bộ test hiện tại:

~~~text
ShopApplicationTests
  @SpringBootTest
  ApplicationModules.of(ShopApplication.class).verify()
  Assert OrderRepository exists
  Publish OrderSubmitted and verify listener

CheckoutTests
  @SpringBootTest
  @MockitoBean InventoryStockRepository
  verify(save(...))

BillingTests
  @SpringBootTest
  Testcontainers PostgreSQL
~~~

Đây là **tình huống giả định**, không phải tóm tắt repo đang làm việc. Một PR thêm `import inventory.internal.InventoryStockRepository` vào `orders` làm mất bốn phút mới thấy lỗi; developer đề nghị bỏ mọi integration tests khỏi PR để “tăng tốc”.

**Hãy đưa ra thiết kế thay thế** theo đúng loại bằng chứng:

1. Viết `ModuleStructureTests` JUnit thuần với `@Tag("structural")` và `ApplicationModules.verify()`.
2. Chuyển phép kiểm tra `OrderRepository` existence và event publication thành **module integration tests** có JPA/publisher thật, không để chung trong structural test.
3. Không dùng `@MockitoBean InventoryStockRepository` để kiểm tra persistence; nếu cần cô lập inventory, mock **public API `StockAvailability`**.
4. Bổ sung `DIRECT_DEPENDENCIES` hoặc wiring test không mock `StockAvailability` để bảo đảm implementation thật vẫn được đăng ký.
5. Gắn `@Tag("integration")` cho tests cần Spring/DB, dùng hai Gradle tasks như mục 5.
6. CI fast gate chạy `test`; slow gate chạy `integrationTest` và kiểm tra có tests thực thi.
7. Đo cold/warm startup, test reports và context cache trước khi giảm tần suất integration gate.
8. Giữ listener commit/retry và DB migration tests ở integration stage phù hợp, không giả rằng structural test bảo vệ được chúng.

### 10.2. Câu hỏi tự kiểm tra

**Câu 1.** `ApplicationModules.verify()` xanh, nhưng full Spring context thiếu bean `StockAvailability`. Vì sao không mâu thuẫn?

**Trả lời:** Structural check xác minh dependency graph/public API, không bootstrap Spring để tạo beans. `DIRECT_DEPENDENCIES` hoặc real-wiring smoke test mới có trách nhiệm chứng minh bean implementation được đăng ký.

**Câu 2.** Một test `@ApplicationModuleTest` chạy ở `STANDALONE` và dùng `@MockitoBean StockAvailability`. Nó là structural hay integration?

**Trả lời:** **Integration test**, vì Spring context, service, transaction/JPA/event đang chạy thật (nếu không bị mock). Dù module ngoài được mock, nó không thành structural test.

**Câu 3.** Nếu integration mất 90 giây chỉ vì Testcontainers cold start, có nên thay `OrderRepository` bằng mock?

**Trả lời:** Không nếu đang kiểm chứng persistence. Hãy đo startup riêng, cân nhắc container lifecycle, context cache, scope, fixtures; đừng bỏ database evidence.

**Câu 4.** Gradle `integrationTest` task được tạo nhưng CI chỉ gọi `./gradlew test`. Integration tests đã được chạy chưa?

**Trả lời:** Trong cấu hình mục 5, **chưa**: `test` loại tag `integration`, còn `integrationTest` chưa được yêu cầu. Phải thêm CI job/task dependency thích hợp.

**Câu 5.** `./gradlew integrationTest` báo `BUILD SUCCESSFUL` nhưng không có test cases trong JUnit report. Có thể merge không?

**Trả lời:** Không nên coi đó là green integration gate. Kiểm tra tag discovery, source set, test classpath, engine và cấu hình filters; gate đang thiếu bằng chứng.

**Câu 6.** Test trong `@SpringBootTest` chỉ assert `ApplicationModules.verify()`. Nó phát hiện vi phạm kiến trúc không?

**Trả lời:** Có thể phát hiện được, nhưng đã trả chi phí bootstrap **không cần thiết**. Chuyển sang JUnit structural thuần để nhận phản hồi nhanh và không phụ thuộc hạ tầng.

**Câu 7.** Đặt `@DirtiesContext` lên mọi module integration test giúp tăng độ tin cậy hay tốc độ?

**Trả lời:** Không phải mặc định. Nó có thể buộc context bootstrap nhiều lần, làm chậm suite; và không tự dọn database/broker. Dùng khi context state thực sự không thể phục hồi bằng fixture cleanup phù hợp.

**Câu 8.** Structural gate có phát hiện listener `AFTER_COMMIT` bị thiếu không?

**Trả lời:** Không nếu code vẫn tuân thủ module dependency graph. Cần receiver/transaction integration test thực với positive control và observable side effect.

### 10.3. Checklist trước khi đưa hai nhóm test vào CI

- [ ] Có một **pure JUnit** structural test gọi `ApplicationModules.of(ShopApplication.class).verify()`.
- [ ] Structural test **không** mang `@SpringBootTest`, `@ApplicationModuleTest` hoặc yêu cầu DB/network.
- [ ] Các quy tắc module cycle, public API và `allowedDependencies` đều có một gate chịu trách nhiệm.
- [ ] Integration tests dùng `@ApplicationModuleTest` đúng bootstrap scope, không tự động mở rộng thành full context.
- [ ] Test persistence giữ repository/transaction thật, có read-back sau boundary phù hợp.
- [ ] Test event producer dùng publisher thật/`PublishedEvents`; receiver có test hoàn tất riêng khi cần.
- [ ] `STANDALONE` có thể mock public API ngoài module; real wiring có test **không mock** cùng API.
- [ ] Structural và integration tests có **tags rõ**; không phụ thuộc tên class để JUnit tự phân loại.
- [ ] Gradle `test` loại tag `integration`, `integrationTest` chỉ chọn tag `integration`.
- [ ] CI thực sự gọi cả hai tasks theo chính sách; không để integration task không bao giờ được chạy.
- [ ] JUnit XML/report cho thấy **số test cases thực thi** ở mỗi nhóm, không chỉ một `BUILD SUCCESSFUL`.
- [ ] Fast gate được đặt trước slow gate nếu mục tiêu là fail fast/giảm compute.
- [ ] Đã đo riêng startup context, container, test method và Gradle job wall-clock.
- [ ] Cold/warm baselines được gắn với môi trường/cấu hình cụ thể, không so sánh tùy tiện.
- [ ] Không thêm hard timeout quá nhỏ vào structural test làm test flaky vì CPU/cache.
- [ ] Dùng context cache có chủ đích, hạn chế `@DirtiesContext`, giữ fixture isolation và DB cleanup đúng.
- [ ] Cân nhắc shared container/parallelism dựa trên số liệu, không đổi dependency thật thành mock để giảm thời gian.
- [ ] Có mutation matrix xác nhận ít nhất một gate đỏ khi illegal import, missing bean, DB mapping hoặc event regression xuất hiện.
- [ ] Các slow tests không tự động bị bỏ khỏi branch protection chỉ vì chạy lâu; cadence dựa trên rủi ro và SLA.

**Kết luận:** Tách test structural nhanh khỏi integration test chậm là **phân quyền bằng chứng cho hai tầng kiểm chứng**. `ApplicationModules.verify()` là phép kiểm tra cấu trúc module thuần JUnit, không cần khởi động Spring; nó phải cho phản hồi sớm về import trái ranh giới, vòng phụ thuộc và `allowedDependencies`. `@ApplicationModuleTest` và các integration stages chậm hơn có nhiệm vụ kiểm chứng bean, transaction, JPA, event và wiring thật. Dùng JUnit tags và Gradle tasks để chia thời gian chạy, đo cold/warm costs để tối ưu context/container, và bảo đảm CI **thực sự chạy** cả fast lẫn slow gates theo rủi ro. Test nhanh có giá trị khi không lược bỏ điều kiện runtime mà nó chưa từng có khả năng chứng minh.

### Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()`, module cycles, public API và allowed dependencies.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `STANDALONE`, `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES`, `PublishedEvents`.
- [Spring Framework — TestContext Framework, Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache key, lifecycle và `@DirtiesContext`.
- [Spring Framework — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean overrides, tác động tới TestContext.
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform tags, `Test` tasks và test reports.
- [JUnit 5 — Tagging and Filtering](https://junit.org/junit5/docs/current/user-guide/#writing-tests-tagging-and-filtering): `@Tag`, filtering và test discovery.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test contexts, JPA slices và full-context bootstrap.
- [Testcontainers — Java](https://java.testcontainers.org/): lifecycle và database containers cho integration tests.

> Ghi chú áp dụng: Ví dụ giả định Java 17+, JUnit 5, Spring Modulith, Spring Boot/Spring Data JPA và Spring Framework 6.2+ cho `@MockitoBean`; nếu dự án dùng phiên bản cũ, các annotation/import có thể khác. Snippets Gradle là **Groovy DSL**, YAML CI là minh họa, các packages/fixtures/schema phải được điều chỉnh theo dự án. **Không có số liệu benchmark thật** trong bài; mọi thời gian trong bảng đều là giả định để giải thích kỹ thuật. Theo STEP_4, đây là bản biên soạn tài liệu, chưa chạy Gradle/Python hoặc Content QA chuyên môn.



