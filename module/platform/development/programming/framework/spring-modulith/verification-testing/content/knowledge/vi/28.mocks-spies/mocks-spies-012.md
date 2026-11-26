# Không dùng mock để che lỗi bootstrap

## 1. Một context khởi động được sau khi thêm mock chưa chắc là context đúng

Giả sử `@ApplicationModuleTest` không khởi động:

~~~text
UnsatisfiedDependencyException: Error creating bean 'orderService'
  NoSuchBeanDefinitionException:
    No qualifying bean of type '...catalog.api.StockAvailability'
~~~

Developer thêm:

~~~java
@MockitoBean StockAvailability stock;
~~~

và test xanh. Có **hai cách diễn giải rất khác nhau**:

- **Cô lập đúng:** `orders` đang chạy ở `STANDALONE`, còn `StockAvailability` là **public API** của module `catalog` được cố ý loại khỏi test context. Mock giúp kiểm tra module `orders` độc lập; phải có một bài test khác kiểm chứng `catalog` thật và wiring tích hợp.
- **Che lỗi thật:** bean đáng lẽ phải xuất hiện trong context đang kiểm chứng, nhưng implementation không được scan, điều kiện `@ConditionalOnProperty` sai, qualifier sai, configuration thiếu hoặc dependency bị hỏng. `@MockitoBean` tự tạo một bean và làm mất tín hiệu đó.

Khác biệt nằm ở **mục tiêu bootstrap của bài test**, không nằm ở chỗ annotation Mockito có làm ApplicationContext start được hay không.

Bài thuộc chương **Mock và spy** trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**: kiểm chứng ranh giới kiến trúc bằng `ApplicationModules` và quy tắc phụ thuộc module; thực hành `@ApplicationModuleTest`, kiểm thử sự kiện, cơ sở dữ liệu và tích hợp, kết hợp quality gate CI nhằm ngăn phụ thuộc sai/hồi quy. Trọng tâm trực tiếp ở đây là **không dùng mock để che lỗi bootstrap** — không ôn lại cách Mockito stubbing cơ bản.

**Quy tắc quyết định:** Chỉ thêm mock khi bạn có thể hoàn thành câu sau một cách chính xác:

> “Trong test này, bean **X** thuộc boundary **Y** được cố ý không bootstrap; tôi thay **đúng public contract của X** để kiểm chứng hành vi **Z**, còn một test khác sẽ kiểm chứng bean thực của X tồn tại và kết nối được.”

Nếu không thể xác định Y, Z và test đối chứng, hãy **giữ lỗi bootstrap hiển thị** và chẩn đoán nguyên nhân trước khi mock.

### Cấp độ bằng chứng cần phân biệt

| Test xanh | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| `@ApplicationModuleTest(STANDALONE)` + mock public API ngoài module | Hành vi nội bộ của module với đầu vào do mock cung cấp | Bean implementation ngoài module tồn tại/wire đúng trong runtime |
| `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` **không mock** public API đang kiểm tra | Bean trực tiếp phụ thuộc được nạp và wiring tương ứng hoạt động | Toàn bộ application, broker hoặc provider ngoài đều đúng |
| `@SpringBootTest` **không mock** collaborator cần kiểm chứng | Full Spring context bootstrap và autowiring được kiểm chứng ở test profile | Mọi điều kiện production profile/hạ tầng ngoài đều được kiểm chứng |
| `ApplicationModules.verify()` | Phụ thuộc và public module boundaries hợp lệ theo Modulith | Bean runtime tồn tại, database/transaction/event chạy đúng |

Điều đầu tiên phải biết là **bạn đang yêu cầu context nào bootstrap**.

## 2. Phân loại lỗi: thiếu bean có chủ ý khác lỗi cấu hình thực

Spring Modulith cung cấp ba chế độ bootstrap cho module test:

| Mode | Modules được nạp | Thiếu bean nào có thể là điều kiện hợp lệ? |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Chỉ module đang test | Public collaborator của **module khác**, nếu module kia cố ý bị loại khỏi context |
| `DIRECT_DEPENDENCIES` | Module hiện tại và các module nó phụ thuộc **trực tiếp** | Bean thuộc module ngoài phạm vi vừa nạp |
| `ALL_DEPENDENCIES` | Module hiện tại cùng cây phụ thuộc bắc cầu | Bean nằm ngoài cây phụ thuộc được nạp |

Các mode tác động đến **bootstrap scope**; chúng không sửa code dependency graph. Nếu `orders` gọi class nội bộ của `catalog`, dùng một mock cho class ấy không biến dependency thành hợp lệ.

### Cây quyết định chẩn đoán

~~~mermaid
flowchart TD
    F["ApplicationContext bootstrap thất bại"] --> R["Đọc deepest root cause"]
    R --> Q{"Thực sự là NoSuchBeanDefinitionException?"}
    Q -->|"Không"| O["Xử lý lỗi thật: DB, config, qualifier, migration, bean creation..."]
    Q -->|"Có"| M{"Bean thuộc module nào?"}
    M -->|"Module ngoài, bị STANDALONE loại"| P{"Là public contract hợp lệ?"}
    P -->|"Có"| A["Mock boundary trong isolated module test"]
    P -->|"Không"| V["Sửa module boundary; verify architecture"]
    M -->|"Module đang test / hạ tầng bắt buộc"| B["Sửa bean/config/scan; KHÔNG mock để chữa"]
    A --> I["Bổ sung test wiring không mock"]
    B --> I
~~~

Một thông báo `UnsatisfiedDependencyException` ở đầu stack trace chỉ nói Spring **không thể tạo một bean**. Nó có thể do `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, lỗi tạo bean bên dưới, datasource không kết nối, thiếu configuration property hoặc migration thất bại. Nếu chỉ thấy chữ “dependency” rồi thêm `@MockitoBean`, bạn có thể đang chữa sai bệnh.

### Các lớp nguyên nhân cần giữ riêng

| Dấu hiệu | Nguồn lỗi có khả năng | Có nên thêm mock? |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho `catalog.api.StockAvailability` ở module `orders` chạy `STANDALONE` | Module `catalog` không được bootstrap **đúng thiết kế** | Có thể mock **public boundary** để cô lập |
| `NoSuchBeanDefinitionException` cho `orders.internal.OrderRepository` | Repository/entity scan, starter JPA hoặc configuration sai | **Không** nếu test cần JPA thật |
| `NoUniqueBeanDefinitionException` | Nhiều candidates, thiếu qualifier/`@Primary` | Sửa bean selection; mock có thể che ambiguity |
| `BeanCreationException` bên dưới có lỗi DB | Datasource/schema/migration/SQL không hợp lệ | Sửa test infrastructure; mock repository không kiểm chứng DB |
| `ConfigurationPropertiesBindException` hoặc validation fail | Property thiếu/sai kiểu/sai profile | Sửa profile/fixture/config, không giả tạo config bean |
| `NoSuchBeanDefinitionException` cho gateway ở full-context wiring test | Auto-configuration, component scan hoặc `@Conditional` sai | **Không**; cần nhìn thấy lỗi bean thật bị thiếu |
| Test dùng `@MockitoBean` cho chính SUT | Service thật không chạy | Không phù hợp để tuyên bố module behavior/wiring đã được kiểm chứng |

**Lưu ý:** Một lỗi runtime thực có thể chỉ xuất hiện với một `@Profile` hoặc property cụ thể. Một `@SpringBootTest` chạy test profile không tự chứng minh production profile sẽ bootstrap giống hệt. Test wiring cần cấu hình/profile đại diện cho contract đang bảo vệ.

## 3. Ví dụ xuyên suốt: orders phụ thuộc catalog qua public API

Ta dùng một Spring Boot app có root package `com.example.shop`, hai application modules `orders` và `catalog`:

~~~text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── api
│   │   ├── StockAvailability.java
│   │   └── package-info.java
│   └── internal
│       ├── DatabaseStockAvailability.java
│       ├── StockEntity.java
│       └── StockRepository.java
└── orders
    ├── OrderService.java
    ├── OutOfStockException.java
    ├── package-info.java
    ├── events
    │   ├── OrderPlaced.java
    │   └── package-info.java
    └── internal
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

### Contract có chủ đích giữa modules

File `catalog/api/StockAvailability.java`:

~~~java
package com.example.shop.catalog.api;

import java.util.UUID;

public interface StockAvailability {
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

Module `orders` chỉ được dùng public API `catalog :: api`; nó không được gọi `catalog.internal.StockRepository`. Trong `STANDALONE`, bean triển khai `StockAvailability` ở `catalog` **bị bỏ ra khỏi component scan theo scope test**. Đó là một dependency thiếu có thể hợp lệ.

### Producer nội bộ cần giữ thật

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "shop_orders")
public class OrderEntity {
    @Id private UUID id;
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

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.util.UUID;

public record OrderPlaced(
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

import com.example.shop.catalog.api.StockAvailability;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final StockAvailability stock;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(StockAvailability stock,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.stock = stock;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId, UUID skuId, int quantity) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(skuId, "skuId");
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }
        if (!stock.isAvailable(skuId, quantity)) {
            throw new OutOfStockException();
        }
        orders.save(new OrderEntity(orderId, skuId, quantity));
        publisher.publishEvent(
                new OrderPlaced(orderId, skuId, quantity));
    }
}
~~~

**Giới hạn nghiệp vụ:** `isAvailable` chỉ là một truy vấn tồn kho, **không đặt giữ hàng atomic** khi nhiều đơn cùng mua. Ví dụ dùng nó để kiểm tra bootstrap và bean boundaries; quy tắc reservation/concurrency cần contract và integration tests riêng trong hệ thống production.

### Bean thực của module catalog

File `catalog/internal/StockEntity.java`:

~~~java
package com.example.shop.catalog.internal;

import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "catalog_stock")
public class StockEntity {
    @Id private UUID id;
    @Column(nullable = false)
    private int available;

    protected StockEntity() {}
    public UUID getId() { return id; }
    public int getAvailable() { return available; }
}
~~~

File `catalog/internal/StockRepository.java`:

~~~java
package com.example.shop.catalog.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StockRepository
        extends JpaRepository<StockEntity, UUID> {}
~~~

File `catalog/internal/DatabaseStockAvailability.java`:

~~~java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.api.StockAvailability;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class DatabaseStockAvailability
        implements StockAvailability {

    private final StockRepository stocks;

    public DatabaseStockAvailability(StockRepository stocks) {
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

Ba lớp của `catalog.internal` **không được import trực tiếp vào service thuộc `orders`**. Chúng sẽ được nạp khi chạy test catalog, `DIRECT_DEPENDENCIES` của orders, hoặc full context. Nếu `DatabaseStockAvailability` bị xóa `@Service`, đặt sai package hoặc thiếu JPA infrastructure, test wiring **không mock** phải phát hiện điều đó.

## 4. Test STANDALONE: khi mock là ranh giới cô lập hợp lệ

Test class đặt trong package `com.example.shop.orders` để Spring Modulith xác định module chủ sở hữu. Trong `STANDALONE`, Spring nạp `OrderService` và repository của `orders`, **không nạp** `DatabaseStockAvailability` thuộc module `catalog`.

Mục tiêu của test **không phải** chứng minh catalog bootstrap; mục tiêu là: khi public `StockAvailability` trả **đủ hàng/thiếu hàng**, module `orders` có lưu order và phát event đúng hay không.

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.api.StockAvailability;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrdersIsolatedModuleTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    // Đúng: dependency public thuộc catalog cố ý không bootstrap.
    @MockitoBean StockAvailability stock;

    @Test
    void enoughStockPersistsOrderAndPublishesEvent(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        when(stock.isAvailable(skuId, 2)).thenReturn(true);

        orders.place(orderId, skuId, 2);

        verify(stock).isAvailable(skuId, 2);
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(row -> {
                    assertThat(row.getSkuId()).isEqualTo(skuId);
                    assertThat(row.getQuantity()).isEqualTo(2);
                });
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event ->
                        assertThat(event.quantity()).isEqualTo(2));
    }

    @Test
    void missingStockCreatesNoOrderOrEvent(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        when(stock.isAvailable(skuId, 2)).thenReturn(false);

        assertThatThrownBy(() ->
                orders.place(orderId, skuId, 2))
                .isInstanceOf(OutOfStockException.class);

        verify(stock).isAvailable(skuId, 2);
        assertThat(repository.existsById(orderId)).isFalse();
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .isEmpty();
    }
}
~~~

**Phạm vi bằng chứng chính xác:**

- Bean `OrderService`, JPA `OrderRepository` và Spring `ApplicationEventPublisher` đều chạy **thật** trong module.
- Bean public `StockAvailability` từ module ngoài được **cố ý tạo bằng Mockito**; test kiểm tra outcome nội bộ cho hai câu trả lời đã biết.
- `PublishedEvents` chỉ xác nhận event đã được phát; nó không tự chứng minh listener ở module khác đã hoàn tất.
- Test **không chứng minh** có một bean `DatabaseStockAvailability` hợp lệ trong app đầy đủ hoặc có row stock thật trong `catalog`.

Lưu ý cấu hình: cần Spring Modulith test starter, Spring Data JPA, transaction manager và schema test cho bảng `shop_orders`. Không gắn outer `@Transactional` vào class test nếu cần chứng minh service đã hoàn tất commit khi truy vấn read-back; Spring Test transaction mặc định rollback làm thay đổi thời điểm và ý nghĩa assertion.

### Điều không nên đưa vào test này

~~~java
// Anti-pattern: mock repo nội bộ của module orders.
@MockitoBean OrderRepository repository;

// Anti-pattern: mock chính system under test.
@MockitoBean OrderService orders;

// Anti-pattern: mock publisher trong bài muốn PublishedEvents thật.
@MockitoBean ApplicationEventPublisher publisher;
~~~

Ba khai báo trên là **phản ví dụ**. Chúng có thể khiến context khởi động bằng cách thay đúng những thành phần mà test muốn xác minh: service wiring, JPA persistence hoặc event publication. Đừng kết luận “module đã được kiểm chứng” chỉ vì `verify(mock)` xanh.

### Không phải mọi dependency ngoài module đều phải mock

Nếu `orders` có nhiều dependency từ `catalog`, `customers`, `pricing` chỉ để dựng một case, hãy đánh giá kiến trúc:

- Dependency thật sự đồng bộ và cần decision ngay? Mock đúng public port ở isolated test và bảo đảm contract của producer được test riêng.
- Chỉ cần thông báo một thay đổi sau khi commit? Có thể dùng domain event thay vì thêm một dependency đồng bộ.
- Nhiều public ports từ nhiều modules khiến bootstrap test phức tạp? Đây có thể là dấu hiệu coupling cao, không phải lời mời thêm vô hạn mocks.

## 5. Test wiring không mock: đối chứng bắt buộc của bài STANDALONE

Một isolated test ở mục 4 **có thể tiếp tục xanh ngay cả khi implementation catalog bị xóa `@Service`**. Điều đó không khiến isolated test sai — nó chỉ có phạm vi bằng chứng hẹp. Lỗ hổng xuất hiện nếu pipeline **chỉ chạy isolated test** và tuyên bố toàn ứng dụng đã wire đúng.

Tạo một bài test khác **không có `@MockitoBean StockAvailability`**.

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.api.StockAvailability;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersCatalogWiringTests {

    @Autowired ApplicationContext context;
    @Autowired OrderService orders;
    @Autowired StockAvailability stock;

    @Test
    void realCatalogImplementationIsPresentAndNotMocked() {
        assertThat(orders).isNotNull();
        assertThat(context.getBeansOfType(
                StockAvailability.class)).hasSize(1);
        assertThat(mockingDetails(stock).isMock()).isFalse();
    }
}
~~~

Ở đây:

1. `DIRECT_DEPENDENCIES` nạp `orders` và module trực tiếp được khai báo phụ thuộc là `catalog`.
2. Trong ví dụ, `DatabaseStockAvailability` được annotate `@Service`, nên nó là bean thật.
3. Nếu annotation `@Service` biến mất hoặc condition của bean không thỏa, việc inject `StockAvailability` sẽ thất bại; **test cần fail**, không nên “sửa” bằng mock.
4. Nếu bean có Spring AOP proxy bình thường, `mockingDetails(stock).isMock()` thông thường vẫn trả `false`; khi dự án có test-specific spy/override, cần kiểm tra policy context riêng.

**Điều kiện test:** `catalog` có JPA repository và datasource tương ứng. Nếu context fail vì migration thiếu bảng `catalog_stock`, đó là lỗi infrastructure của bài wiring; **không thêm `@MockitoBean StockRepository` để làm giả một runtime catalog đang chạy tốt**.

### Bao giờ dùng ALL_DEPENDENCIES hoặc @SpringBootTest?

| Mục đích | Test phù hợp | Có mock StockAvailability không? |
| --- | --- | --- |
| Chỉ kiểm tra hành vi module `orders` dưới inputs đã kiểm soát | `@ApplicationModuleTest` mặc định | **Có**, nếu public API thuộc module ngoài bị loại |
| Kiểm tra wiring `orders` ↔ `catalog` thật | `@ApplicationModuleTest(mode = DIRECT_DEPENDENCIES)` | **Không** |
| Cần các dependencies bắc cầu của `catalog` | `ALL_DEPENDENCIES` | Không mock bean thuộc đường tích hợp đang xác minh |
| Kiểm tra toàn bộ Spring runtime bean graph trong test profile | `@SpringBootTest` smoke, có cấu hình hạ tầng thích hợp | Không mock những bean cấu thành điều kiện runtime cần kiểm chứng |

Một smoke test full application:

~~~java
package com.example.shop;

import com.example.shop.catalog.api.StockAvailability;
import com.example.shop.orders.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ShopRealWiringSmokeTests {

    @Autowired OrderService orders;
    @Autowired StockAvailability stock;

    @Test
    void bootsWithRealDomainBeans() {
        assertThat(orders).isNotNull();
        assertThat(stock).isNotNull();
    }
}
~~~

Nếu `StockAvailability` không còn implementation khi chạy với profile của bài smoke test, context không khởi động. Đây là **tín hiệu mong muốn**, không phải test cần được cứu bằng `@MockitoBean`.

**Caveat:** Full `@SpringBootTest` cũng chỉ kiểm chứng **test context/configuration đang chạy**. Không suy rằng credentials production, DNS, TLS hoặc broker bên ngoài đều hợp lệ chỉ vì local test profile boot được. Muốn bao phủ những điều ấy, cần kiểm thử môi trường/integration tương ứng.

### Một đối chứng về behavior, không chỉ bean presence

Bean tồn tại không chứng minh implementation đáp ứng mọi hợp đồng. Ở phía module `catalog`, viết một `@ApplicationModuleTest` với `StockRepository` **thật**: tạo fixture có `available=3`, assert `isAvailable(skuId,2)` là `true` và `isAvailable(skuId,4)` là `false`. Đó là contract test của producer. Giữ fixture **trong package test của catalog**, không để test production module `orders` import `catalog.internal.StockRepository`.

## 6. @MockitoBean REPLACE_OR_CREATE: cơ chế dễ che thiếu bean nhất

Spring Framework 6.2+ dùng chiến lược **`REPLACE_OR_CREATE`** mặc định với `@MockitoBean`. Nghĩa là khi không tìm thấy bean target phù hợp, Spring Test có thể **tạo một bean mock mới**. Đây là tính năng cần thiết cho `STANDALONE`, nhưng cũng là lý do một full-context test có thể xanh khi implementation thực vắng mặt.

### Full-context mock khiến kiểm tra wiring trở nên vô nghĩa

~~~java
// ANTI-PATTERN nếu tên/mục tiêu test là "real app bootstrap".
@SpringBootTest
class MisleadingApplicationBootstrapTests {

    @MockitoBean StockAvailability stock;
    @Autowired OrderService orders;

    @Test
    void boots() {
        assertThat(orders).isNotNull();
    }
}
~~~

Nếu bean `DatabaseStockAvailability` bị xóa hoặc bị một condition loại khỏi runtime, mock có thể được **tạo thay**. Bài test vẫn pass, nhưng không còn chứng minh adapter/catalog implementation tồn tại.

Đây là **anti-pattern theo mục tiêu**. Trong một full-context test mà mục tiêu là cố ý cô lập external provider có I/O tốn kém, mock một outbound gateway có thể hợp lý; nhưng test đó phải nói rõ “behavior with gateway mocked” và **không thay thế smoke test của real wiring**.

### enforceOverride = true là một công cụ chẩn đoán, không phải công thức cho mọi module test

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class ExistingStockBeanOverrideTests {

    // Với full context, yêu cầu bean target thực sự đã tồn tại
    // để thay, thay vì tự tạo mock mới.
    @MockitoBean(enforceOverride = true)
    StockAvailability stock;

    @Test
    void usesExplicitlyOverriddenBean() {
        // Khi context khởi động, đã tồn tại target bean để override.
    }
}
~~~

`enforceOverride = true` chuyển strategy sang **`REPLACE`**: nếu không có bean phù hợp để thay, context **fail** thay vì tạo một mock mới. Nó hữu ích khi một test **cố ý dùng mock cho bean mà runtime context phải có** (chẳng hạn HTTP gateway đang được thay bằng mock trong contract test). Tuy vậy:

- Nó chỉ kiểm tra bean definition target tồn tại, **không chứng minh implementation target đã thực sự khởi tạo/chạy đúng**; bean được thay trước khi đi qua các post-processors bình thường.
- Bean mock thay vào là object trần; nếu bean gốc được AOP proxy cho `@Transactional`, `@Cacheable`, `@Retryable`, mock **không mang semantics AOP thực** của bean đó.
- Nếu mục tiêu là **real wiring**, cách mạnh nhất vẫn là **không override** bean đang kiểm chứng.
- Trong **`STANDALONE`**, `StockAvailability` ngoài module **không có bean để replace**. Dùng `enforceOverride=true` ở đó sẽ fail đúng cơ chế, nhưng **không phải bằng chứng kiến trúc hỏng**. Ở isolated test, default `REPLACE_OR_CREATE` mới đúng.

### @MockitoSpyBean không phải cách cứu bean không tồn tại

`@MockitoSpyBean` dùng chiến lược `WRAP`, yêu cầu **đúng một bean** đã tồn tại để wrap. Nếu bootstrap fail do không có bean, đổi `@MockitoBean` thành spy **không khôi phục được implementation**. Kể cả khi spy được tạo, real method vẫn có thể chạy, tạo SQL/I/O ngoài ý muốn.

### Bean name, qualifier và context cache cũng là một phần chẩn đoán

Khi một type có nhiều beans, Spring dùng `@Qualifier`, tên field hoặc tên bean để tìm target override. Ví dụ:

~~~java
@MockitoBean(name = "primaryStockAvailability",
             enforceOverride = true)
StockAvailability stock;
~~~

Chỉ dùng snippet này nếu production context thật sự có bean tên `primaryStockAvailability`; ví dụ ở mục 3 **không** khai báo tên ấy. Nếu chọn nhầm tên và không enforce, test có thể tạo mock mới trong khi bean thực khác vẫn tồn tại — khiến ngữ nghĩa wiring và context cache khó hiểu.

Hãy xác nhận **tên bean/type/qualifier cụ thể** trước khi override và dùng cùng field/qualifier conventions trong các test classes để tránh Spring tạo không cần thiết những cached contexts khác nhau.

## 7. Không mock hạ tầng để làm lỗi bootstrap “biến mất”

Khi thiếu một dependency, giải pháp nhanh thường là tiếp tục mock bean tiếp theo cho đến khi context xanh. Với module test có JPA và events, điều này có thể **loại bỏ toàn bộ đường thực thi cần xác minh**.

### Repository, transaction và entity scanning

Giả sử sau khi thêm mock `StockAvailability`, test lại fail:

~~~text
NoSuchBeanDefinitionException:
  No qualifying bean of type '...orders.internal.OrderRepository'
~~~

**Không nên:**

~~~java
@MockitoBean OrderRepository orders;
~~~

Nếu mục tiêu là kiểm tra `orders.place()` **ghi database**, mock repository biến phép kiểm tra thành `verify(orders).save(...)` — chỉ còn lời gọi Java. Nguyên nhân thật có thể là:

- Chưa có `spring-boot-starter-data-jpa`/starter test phù hợp.
- Test module không scan được `orders.internal.OrderEntity` hoặc repository.
- Datasource/driver/schema thiếu; JPA auto-configuration không được kích hoạt như dự kiến.
- Bean repository được định nghĩa ở package/scan location không thuộc bootstrap scope.
- Profile hoặc test configuration thay đổi `@EnableJpaRepositories`/`@EntityScan` không chủ đích.

**Cách sửa:** bảo đảm Spring Data JPA/repository và test datasource được cấu hình phù hợp, rồi assert **read-back state** qua repository thật. Nếu test thuần business-rule thật sự không cần JPA, chuyển nó về unit test không Spring thay vì tuyên bố đó là persistence module test.

### Event publisher và listener

Một anti-pattern khác:

~~~java
@MockitoBean ApplicationEventPublisher publisher;
~~~

Nếu bài test muốn dùng `PublishedEvents`, mock publisher làm mất đường phát event thật và giảm phạm vi bằng chứng. Nếu listener của **module khác** vắng mặt trong `STANDALONE`, đó có thể là điều kiện **đúng**: producer test không cần listener để phát event. Nếu muốn xác nhận listener `@ApplicationModuleListener` chạy sau commit, hãy viết test receiver/integration nạp listener thật; **không tạo listener mock để tuyên bố đã kiểm chứng delivery**.

Nhớ tách:

| Mốc | Cần kiểm chứng bằng |
| --- | --- |
| `OrderService` đã yêu cầu publish | Mockito publisher mock chỉ phù hợp ở unit test thuần |
| Spring publisher thật đã phát event | `@ApplicationModuleTest` + `PublishedEvents` |
| Transaction nguồn đã commit | JPA transaction thật và database read-back |
| Listener `AFTER_COMMIT` chạy | Listener thật, commit/rollback positive-negative controls |
| Event Publication Registry completed | Registry store/target và integration test riêng |
| Broker/HTTP provider thực nhận | Adapter/transport integration test |

**Mock không nên tạo ra cảm giác “các tầng phía sau đã hoạt động”** chỉ vì `publishEvent` hoặc `save` được gọi.

### AOP/proxy và những annotation mất hiệu lực khi thay bean bằng mock

Bean `OrderService` có `@Transactional`. Nếu dùng:

~~~java
@MockitoBean OrderService orders;
~~~

thì bản thân `OrderService` thật bị thay bởi Mockito mock, không còn thực hiện code business; mock được thay trực tiếp, **không được Spring AOP wrap như bean gốc**. Một test inject service mock rồi `verify(orders).place(...)` không chứng minh transaction, persistence hoặc event. Tương tự, thay `@Cacheable`/`@Retryable` service bằng mock khiến bạn không kiểm chứng cache/retry advice thật.

**Phải đặc biệt cảnh giác** với cơ chế `REPLACE_OR_CREATE`: ngoài việc che bean missing, nó còn có thể **thay đổi chính semantics runtime** cần kiểm tra. Những bài test đó có giá trị như unit/orchestration tests nếu đặt tên đúng và không suy kết luận vượt phạm vi.

### ConfigurationProperties và ConditionalOnProperty

Ví dụ một biến thể production của `DatabaseStockAvailability` được bật có điều kiện:

~~~java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.api.StockAvailability;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import java.util.UUID;

// Chỉ minh họa biến thể cấu hình, không gắn đồng thời
// với @Service unconditional của ví dụ mục 3.
@Service
@ConditionalOnProperty(
        prefix = "catalog.stock",
        name = "enabled",
        havingValue = "true")
class ConditionalDatabaseStockAvailability
        implements StockAvailability {

    private final StockRepository stocks;

    ConditionalDatabaseStockAvailability(StockRepository stocks) {
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

Nếu `DIRECT_DEPENDENCIES` test không cấu hình `catalog.stock.enabled=true`, bean có thể vắng mặt **đúng theo condition**. Giải pháp là:

1. Xác định intended profile/property cho wiring test.
2. Nếu contract yêu cầu bean trong cấu hình này, cấp property test phù hợp và cho **implementation thật** khởi tạo.
3. Nếu contract yêu cầu bean vắng mặt khi feature tắt, test rằng context/consumer behavior thay đổi **có chủ đích** (fallback, disabled feature hoặc startup fail có kiểm soát).
4. Không thêm `@MockitoBean StockAvailability` vào chính wiring test chỉ để nó khởi động.

Tương tự, nếu `@ConfigurationProperties` không bind được URL/credentials/timeout hoặc validation fail, hãy dùng **cấu hình test hợp lệ** và assertion phù hợp; mock configuration bean có thể che những validation/runtime wiring errors đó.

**Lưu ý:** Không nên kiểm tra provider credentials thật trong mọi unit/module test. Ta có thể dùng fake HTTP server và test properties cho adapter, nhưng vẫn cần một smoke/contract test **có real adapter bean** để chắc chắn Spring configuration được bind, tạo bean và kết nối tới fake transport đúng.

## 8. Chẩn đoán bootstrap bằng chứng cứ, thay vì thêm mocks theo stack trace

Khi một module test bootstrap fail, dùng quy trình sau và **giữ nguyên test không mock** trong lúc chẩn đoán:

### Bước 1 — Đọc deepest cause, không chỉ dòng đầu

Các exception cần tách:

~~~text
UnsatisfiedDependencyException
  └─ NoSuchBeanDefinitionException

UnsatisfiedDependencyException
  └─ BeanCreationException
       └─ PSQLException / SQLSyntaxErrorException

UnsatisfiedDependencyException
  └─ NoUniqueBeanDefinitionException

BeanCreationException
  └─ BindException / ConfigurationPropertiesBindException
~~~

Không có một mock nào là câu trả lời chung cho cả bốn nhánh. Với DB fail, kiểm tra datasource/schema/migration; với nhiều beans, xem `@Qualifier`/`@Primary`; với properties fail, xem profile và binding/validation; với NoSuchBean, hỏi **scope module** trước khi chọn mock.

### Bước 2 — Xác nhận test có nằm đúng module không

`@ApplicationModuleTest` xác định module qua package của test class. Nếu test lớp đặt ở `com.example.shop.orders` hoặc một subpackage của nó, mục tiêu là `orders`. Nếu chuyển lớp sang package `com.example.shop.integration` mà không xem xét module discovery, bootstrap có thể thay đổi hoặc fail. Đừng dùng `@MockitoBean` để “sửa” việc chọn sai module test.

### Bước 3 — Xem các modules được nạp thực sự

Theo Spring Modulith, tăng mức logging cho package `org.springframework.modulith` lên `DEBUG` giúp thấy chi tiết cách module test giới hạn component/entity scan. Ví dụ trong cấu hình test:

~~~properties
logging.level.org.springframework.modulith=DEBUG
~~~

Quan sát xem module `catalog` có được bootstrap hay không. Với `STANDALONE`, việc catalog không có trong context là **expected**; với `DIRECT_DEPENDENCIES`, thiếu catalog trong graph phụ thuộc trực tiếp cần được điều tra thêm.

### Bước 4 — Kiểm tra condition report và bean candidates

Trong Spring Boot, condition evaluation report giúp phân biệt:

- Auto-configuration nào khớp/không khớp.
- `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean` hoặc `@ConditionalOnProperty` nào đã loại bean.
- Một bean definition bị override hay chưa từng được đăng ký.

Có thể bật Spring Boot debug report trong môi trường chẩn đoán (tùy cách chạy test) hoặc dùng `ConditionEvaluationReport` trong một test setup phù hợp. **Không lấy việc bean được inject sau `@MockitoBean` làm bằng chứng condition của bean thật đã được thỏa.**

### Bước 5 — Kiểm tra biến thể theo profile và bean name

Ví dụ, bean thực có:

~~~java
@Profile("production")
@Component
class ProductionStockAvailability
        implements StockAvailability {
    // ...
}
~~~

Nếu test chạy `test` profile, `ProductionStockAvailability` có thể không tồn tại vì profile filter; điều này **không tự chứng minh production có hoặc không có lỗi**. Hãy chọn profile/fixture thích hợp cho gate đang kiểm tra. Nếu một type có nhiều candidates, cần xác định qualifier/name thay vì mock một candidate ngẫu nhiên.

### Bước 6 — Sau khi sửa, thêm một test âm tính bảo vệ chính nguyên nhân

Nếu lỗi là “`StockAvailability` biến mất trong real wiring”, hãy giữ một test **không mock** như mục 5. Nếu lỗi là migration thiếu `catalog_stock`, giữ JPA/integration test chạy schema thật. Nếu lỗi là `allowedDependencies` sai, giữ `ApplicationModules.verify()`.

Đừng chỉ sửa configuration để context xanh một lần; biến **lỗi từng xảy ra** thành một quality gate có tên và assertion chính xác, giúp CI phát hiện khi hồi quy.

### Bước 7 — Không mở rộng module test vô tội vạ để chữa missing bean

Từ `STANDALONE` đổi sang `ALL_DEPENDENCIES` có thể khiến test bootstrap được vì nhiều bean mới xuất hiện. Nhưng scope lớn hơn có thể:

- Khiến một bài test business đơn giản phụ thuộc database của nhiều modules khác.
- Che coupling cao hoặc dependency trái intent.
- Tăng thời gian khởi động context, khiến suite chậm.
- Làm khó phân biệt lỗi nội bộ `orders` với lỗi tích hợp.

Nên giữ **hai test riêng có mục tiêu rõ**: isolated behavior ở `STANDALONE` và real wiring ở `DIRECT_DEPENDENCIES`/full context. Chỉ dùng `ALL_DEPENDENCIES` khi test cần toàn cây phụ thuộc thật sự.

## 9. Quality gate CI: chứng minh cả isolation lẫn wiring thật

Một pipeline chỉ có `@ApplicationModuleTest` với nhiều `@MockitoBean` không đủ để bảo vệ **khả năng khởi động ứng dụng thật**. Ngược lại, chỉ có full-context smoke test cũng không đủ để chứng minh ranh giới `orders` và hành vi DB/event đúng cho các trường hợp nghiệp vụ.

### Ma trận kiểm chứng theo mục tiêu

| Gate | Cách chạy | Mock được chấp nhận | Lỗi bắt được |
| --- | --- | --- | --- |
| **Module architecture** | `ApplicationModules.verify()` | Không áp dụng | Dependency cycle, import package nội bộ, sai `allowedDependencies` |
| **orders isolated behavior** | `@ApplicationModuleTest(STANDALONE)` + JPA thật + `PublishedEvents` | `@MockitoBean StockAvailability` tại public API catalog | Sai điều kiện đặt hàng, persistence/event của orders |
| **catalog implementation contract** | `@ApplicationModuleTest` trong package catalog | Chỉ outbound dependency ngoài scope nếu cần | `DatabaseStockAvailability` đọc dữ liệu tồn kho sai; repository/JPA lỗi |
| **orders ↔ catalog wiring** | `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` | **Không mock StockAvailability** | Bean implementation thiếu, auto-scan/condition sai, dependency trực tiếp không wire |
| **full application smoke** | `@SpringBootTest` với profile/hạ tầng đại diện | Không mock những beans đang kiểm tra | Lỗi autowiring/bean graph ở cấu hình full |
| **schema/transaction** | JPA/Testcontainers/migration integration | Không mock repository/transaction manager | Bảng/schema sai, SQL/constraint/commit/rollback lỗi |
| **event receiver** | Listener/module integration, transaction commit | Có thể mock external I/O port | Listener thiếu hoặc phase `AFTER_COMMIT` sai |
| **outbound adapter contract** | HTTP fake server hoặc provider sandbox | Fake server **ngoài Spring port** | Request/response/transport mapping sai |

### Architecture gate cụ thể

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiến trúc đúng **không có nghĩa** bean `DatabaseStockAvailability` chắc chắn được Spring tạo. `verify()` kiểm tra cấu trúc dependency và public APIs theo Modulith, **không bootstrap Spring ApplicationContext**. Đó là lý do gate architecture và gate wiring cần chạy độc lập.

### Thử nghiệm hồi quy có đối chứng

Để đánh giá chất lượng của bộ test, hãy tưởng tượng các mutation và xác định **test nào phải đỏ**:

| Mutation | STANDALONE với mock catalog | DIRECT_DEPENDENCIES/full không mock | Gate cần đỏ |
| --- | --- | --- | --- |
| Xóa `@Service` của `DatabaseStockAvailability` | **Có thể vẫn xanh** | Fail khi thiếu `StockAvailability` | Wiring |
| Đặt `catalog.stock.enabled=false` khi real bean bắt buộc | **Có thể vẫn xanh** | Fail nếu bean không được đăng ký | Wiring/profile |
| Sai `@Entity`/`OrderRepository` của orders | Fail nếu JPA thực được giữ | Thường fail | Module persistence/JPA |
| `OrderService` bỏ `publisher.publishEvent` | Fail vì `PublishedEvents` thiếu event | Có thể fail nếu có assertion event | Producer event |
| `orders` import `catalog.internal.StockRepository` | Có thể vẫn bootstrap nếu mock bù thiếu bean | Có thể bootstrap tùy context | **Architecture** |
| Lỗi wiring do hai `StockAvailability` beans không có qualifier | Test mock có thể thay đổi candidate set và che lỗi | Fail `NoUniqueBeanDefinitionException` | Wiring/qualifier |
| Thiếu listener `notifications` nhưng `OrderPlaced` vẫn phát | Isolated producer có thể vẫn xanh | Full smoke có thể vẫn xanh nếu listener không bắt buộc | Receiver integration |
| Migration `catalog_stock` không tồn tại | STANDALONE có thể không cần catalog | DIRECT_DEPENDENCIES chạy DB có thể fail | Catalog/JPA/wiring |

Một test suite bảo vệ tốt không cần mọi test đỏ với mọi mutation. Nó cần **ít nhất một gate phù hợp** làm đỏ mỗi loại hồi quy có ý nghĩa. Việc biết trước “gate nào phải đỏ” là dấu hiệu phạm vi mocks và test architecture được thiết kế có chủ đích.

### Khi nào nên chạy trong CI?

- **Pull request:** architecture + isolated module tests + các wiring tests đủ nhanh. Đây là các gate rất nên giữ bắt buộc.
- **Integration stage:** migration/DB production-like, real module dependency graph, listener phase/registry và adapter tests.
- **Pre-release/deployment:** smoke test theo profile/env đại diện, external service contract, secret/config readiness, không tái sử dụng mock để tuyên bố các kết nối thật đã hoạt động.

Không có nghĩa mọi test đều phải kết nối provider production. **Mục tiêu quan trọng là không thay bean thật bằng Mockito tại chính ranh giới bạn đang muốn kiểm chứng.**

### Kiểm tra các lỗi do test configuration tự gây ra

Đôi khi bộ test có `@Import(TestConfiguration.class)`, `@Primary`, `@TestBean` hoặc `@MockitoBean` được thừa kế từ base class/annotation dùng chung. Khi một wiring gate xanh bất thường, xem cả **cấu hình test được kế thừa** và context hierarchy:

1. Có base class chung nào auto-mock `StockAvailability` không?
2. Có test profile/conditional config đang thay implementation thật bằng fake không?
3. Bean nào thực sự được inject vào SUT (type, name và qualifier)?
4. Context đó có bị giới hạn bởi `STANDALONE` hay đã nạp `DIRECT_DEPENDENCIES`?
5. Có một *test-only* bean trùng type được `@Primary` chọn thay vì production implementation không?

Trong bài real wiring, nên tránh kế thừa một base class “mock tất cả external dependencies” vì nó vô hiệu hóa chính phép kiểm chứng cần có.

## 10. Bài tập: năm lỗi bootstrap, một quyết định đúng cho mỗi trường hợp

Giả sử nhóm phát triển Spring Modulith với modules `orders`, `catalog`, `payments` và `notifications`. Một pull request làm `OrdersIntegrationTests` không start được; developer định thêm một danh sách `@MockitoBean` đến khi context xanh.

### Tình huống A — Isolated orders thiếu public stock API

~~~text
@ApplicationModuleTest // STANDALONE
NoSuchBeanDefinitionException: catalog.api.StockAvailability
~~~

**Câu hỏi:** Có nên mock không? Sau khi test xanh, còn thiếu gate nào?

**Đáp án:** Có thể dùng `@MockitoBean StockAvailability` vì đó là public API của module ngoài **cố ý không được bootstrap**. Giữ `OrderService`, `OrderRepository` và publisher thật; assert DB/event outcome. Đồng thời phải có test catalog riêng, `DIRECT_DEPENDENCIES` hoặc full smoke **không mock stock** để bắt lỗi implementation/wiring runtime.

### Tình huống B — Orders thiếu repository của chính mình

~~~text
@ApplicationModuleTest
NoSuchBeanDefinitionException: orders.internal.OrderRepository
~~~

**Câu hỏi:** Thêm `@MockitoBean OrderRepository` có phải giải pháp không?

**Đáp án:** Không, nếu mục tiêu là persistence của module orders. Chẩn đoán JPA starter/repository scan/entity scan/datasource/transaction configuration. Nếu mục tiêu chỉ là business rule và không cần DB, chuyển thành unit test rõ ràng; không giả một module persistence test đã chạy qua JPA.

### Tình huống C — Full-context smoke thiếu payment gateway

~~~text
@SpringBootTest
NoSuchBeanDefinitionException: payments.api.PaymentGateway
~~~

Developer đề nghị:

~~~java
@MockitoBean PaymentGateway gateway;
~~~

**Câu hỏi:** Test “application boots with real payment integration” còn ý nghĩa không?

**Đáp án:** Không. Mặc định `REPLACE_OR_CREATE` có thể tạo gateway mock và che việc bean thật không được đăng ký. Phải xác nhận profile, `@ConditionalOnProperty`, component scan, `@ConfigurationProperties` và factory bean; sửa cấu hình. Một **test behavior riêng** có thể mock external provider để tránh gọi mạng, nhưng không được thay real-wiring smoke.

### Tình huống D — orders gọi repository nội bộ catalog

~~~java
// Trong OrderService thuộc orders: sai ranh giới.
import com.example.shop.catalog.internal.StockRepository;
~~~

**Câu hỏi:** Nếu thêm `@MockitoBean StockRepository` làm `STANDALONE` start, bài test đã hợp lệ chưa?

**Đáp án:** Chưa. Dependency vi phạm public/named interface. Đổi thành `catalog.api.StockAvailability`, chạy `ApplicationModules.of(ShopApplication.class).verify()`. Một test Mockito xanh không làm kiến trúc đúng.

### Tình huống E — Mock publisher để sửa lỗi listener

~~~text
OrderPlaced xuất hiện trong PublishedEvents của orders
nhưng notifications listener không có trong STANDALONE context
~~~

**Câu hỏi:** Có nên tạo mock `NotificationListener` hoặc mock `ApplicationEventPublisher`?

**Đáp án:** Không cần để test producer. `STANDALONE` chủ ý không nạp module notifications; `PublishedEvents` đã quan sát publisher thật. Nếu cần chứng minh receiver chạy, viết test của `notifications` hoặc integration test với listener thật, transaction commit, `Scenario`/Awaitility và side effect phù hợp. Không dùng publisher mock để thay một kiểm chứng delivery.

### Checklist quyết định trước khi thêm @MockitoBean

- [ ] Đã đọc **deepest cause**, không chỉ `UnsatisfiedDependencyException` ở đầu log.
- [ ] Đã xác định `@ApplicationModuleTest` đang dùng `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`.
- [ ] Test class đặt trong đúng package module, không làm thay module discovery ngoài ý muốn.
- [ ] Bean thiếu nằm trong **module ngoài bị loại có chủ đích**, không phải repository/service/hạ tầng của module đang test.
- [ ] Target mock là **public API hoặc I/O boundary** được phép dùng, không phải class internal của module khác.
- [ ] Đã viết rõ: “mock X để kiểm tra behavior Y”; không đặt tên test là “real bootstrap/wiring” khi X là mock.
- [ ] Không dùng `@MockitoBean` để thay chính SUT, JPA repository, transaction manager hoặc event publisher nếu chúng thuộc bằng chứng cần kiểm tra.
- [ ] Hiểu `REPLACE_OR_CREATE` có thể tạo bean không tồn tại; `enforceOverride=true` chỉ phù hợp khi bean target **phải có mặt** trong context đó.
- [ ] Không dùng `enforceOverride=true` cho public collaborator vắng mặt đúng thiết kế ở `STANDALONE`.
- [ ] Với nhiều candidates, đã kiểm tra bean name/`@Qualifier` và profile/conditional config.
- [ ] Biết `@MockitoSpyBean` cần bean thật và có thể chạy side effect.
- [ ] Nếu lỗi là DB/schema/property binding/auto-config, sửa **hạ tầng thực** thay vì mock.
- [ ] Có test `DIRECT_DEPENDENCIES` hoặc `@SpringBootTest` **không mock** đường wiring đang bảo vệ.
- [ ] Có contract test của module cung cấp public API, không chỉ câu trả lời do consumer mock tạo.
- [ ] `ApplicationModules.verify()` được chạy trong CI để bắt import sai boundary và cycle.
- [ ] Có DB read-back và `PublishedEvents` khi cần bằng chứng persistence và event thật.
- [ ] Test listener `AFTER_COMMIT`/registry/broker được đặt ở tầng tích hợp thích hợp, không suy từ producer test.
- [ ] Không mở rộng bootstrap mode hoặc thêm mocks hàng loạt chỉ để context xanh.
- [ ] CI có ít nhất một gate phải **thất bại khi implementation thực của collaborator biến mất**.

**Kết luận:** Lỗi bootstrap là một **tín hiệu kiểm thử** cần được diễn giải trước khi sửa. Trong `@ApplicationModuleTest(STANDALONE)`, thiếu public collaborator của module khác có thể là điều kiện cô lập đúng, nên một `@MockitoBean` có chủ đích là hợp lý. Nhưng `@MockitoBean` mặc định **có thể tạo bean mới khi bean thực vắng mặt**, nên dễ che lỗi wiring/configuration nếu dùng trong test lẽ ra phải bootstrap implementation thật. Giữ hai phép kiểm chứng song song: **isolated behavior có mock đúng boundary** và **real wiring không mock**; bổ sung `ApplicationModules.verify()`, JPA/event/receiver tests theo bằng chứng cần bảo vệ. Một context chỉ đáng tin khi nó khởi động **đúng những beans mà test cam kết kiểm tra**, chứ không chỉ vì log báo “Started”.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): bootstrap modes, cô lập module và public collaborator mocks.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): `REPLACE_OR_CREATE`, `enforceOverride`, qualifier, context cache và AOP.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()`, public/named interfaces, `allowedDependencies`.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): conditional configuration và condition evaluation report.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test profiles và integration context.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context lifecycle, test configuration và bean overrides.

> Ghi chú tương thích: Ví dụ dùng Spring Framework 6.2+ cho `@MockitoBean`, Spring Modulith với `@ApplicationModuleTest`, Spring Boot/JPA/JUnit 5. Với Spring Boot cũ hơn, các annotation mock và package imports có thể khác. Ví dụ giả định có test datasource, migrations/schema và transaction manager đúng; chúng **chưa được compile hoặc chạy Gradle** theo STEP_4. Vòng Content QA chuyên môn thuộc bước sau, không nằm trong nhiệm vụ biên soạn này.

