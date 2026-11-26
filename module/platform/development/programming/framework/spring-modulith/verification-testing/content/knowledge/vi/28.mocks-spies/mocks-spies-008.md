# Mock repository làm mất bằng chứng persistence

## 1. Test xanh khi `save()` đã được gọi, nhưng database vẫn có thể trống

Hãy xem một assertion rất phổ biến:

~~~java
verify(orderRepository).save(any(OrderEntity.class));
~~~

Nếu `orderRepository` là **Mockito mock**, assertion chỉ chứng minh `OrderService` đã gọi một method tên `save` trên mock với argument phù hợp. Nó **không chứng minh**:

- JPA provider đã được gọi.
- Hibernate đã sinh một câu `INSERT` hợp lệ.
- Bảng, column, quan hệ và converter được ánh xạ đúng.
- Giá trị được ghi xuống database, không chỉ nằm trong persistence context.
- Unique constraint hoặc foreign key của database hoạt động.
- Transaction đã commit, thay vì rollback khi kết thúc test.
- Một truy vấn mới có thể đọc lại đúng dữ liệu.
- Sự kiện được phát sau nghiệp vụ có tương ứng với dữ liệu bền vững.

Những điều này chỉ có thể được kiểm chứng bằng **repository implementation và persistence infrastructure thật** ở một tầng test thích hợp.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu là rèn kỹ năng kiểm chứng ranh giới kiến trúc ứng dụng Spring Modulith bằng `ApplicationModules` và các quy tắc phụ thuộc giữa module; thực hành `@ApplicationModuleTest`, sự kiện, cơ sở dữ liệu và kiểm thử tích hợp, kết hợp quality gate trong CI để ngăn phụ thuộc sai và hồi quy. Bài thuộc chương **Mock và spy**, với chủ đề cụ thể **“Mock repository làm mất bằng chứng persistence”**.

**Thông điệp trọng tâm:** Mock repository **không sai trong mọi hoàn cảnh**. Nó có thể rất hợp lý ở **unit test** chỉ kiểm tra orchestration. Nó trở thành vấn đề khi bài test tuyên bố đã kiểm chứng **persistence, transaction, JPA mapping hoặc database constraints**, trong khi đường đi tới database đã bị thay bằng mock.

### Sau bài học, bạn có thể

1. Phân biệt bằng chứng về **lời gọi `save`**, **trạng thái managed entity**, **flush**, **commit** và **dữ liệu đọc lại**.
2. Chọn khi nào `@Mock OrderRepository` là đủ, và khi nào phải giữ `OrderRepository` thật.
3. Viết `@ApplicationModuleTest(STANDALONE)` cho module `orders`, chỉ mock API của module ngoài.
4. Dùng `@DataJpaTest` để kiểm tra JPA mapping, constraint và query với database thử nghiệm.
5. Viết test commit/rollback qua Spring-managed service, tránh cái bẫy `@Transactional` trên chính test.
6. Phân biệt `save()`, `saveAndFlush()`, `EntityManager.flush()`, `clear()` và transaction completion.
7. Kiểm chứng sự kiện bằng `PublishedEvents` mà không suy ra listener đã completed.
8. Bảo vệ module boundary bằng `ApplicationModules.verify()` và phối hợp các tầng test trong CI.

## 2. “Đã lưu” là một chuỗi trạng thái, không phải một Boolean

Câu “order đã được lưu” cần được làm rõ:

| Tầng bằng chứng | Câu hỏi cần trả lời | Phương pháp phù hợp |
| --- | --- | --- |
| **Invocation** | Code có gọi `save(entity)` không? | Mockito `verify(repository).save(...)`. |
| **State trong persistence context** | Entity đã managed hoặc được Hibernate theo dõi chưa? | JPA test với `EntityManager`, kiểm tra trạng thái trong transaction. |
| **Flush** | Các thay đổi đã được đồng bộ với database qua SQL chưa? | `saveAndFlush`, `EntityManager.flush()`, SQL/constraint assertions. |
| **Commit** | Transaction chứa thay đổi đã hoàn tất thành công chưa? | Service Spring-managed, transaction thật, test không giữ outer rollback transaction. |
| **Read-back** | Một truy vấn khác có đọc được row/field đúng không? | Real repository hoặc JDBC với transaction/persistence context độc lập. |
| **Durability/failure recovery** | Sau restart, concurrency và lỗi kết nối, dữ liệu có đáp ứng hợp đồng không? | Integration/system test với database phù hợp và kịch bản failure. |

Một lời gọi `save` không tương đương `flush`; `flush` không tương đương `commit`; và `commit` ở database test in-memory cũng chưa chứng minh đầy đủ mọi đặc tính của database production.

~~~mermaid
flowchart TD
    A["OrderService.place(...)"] --> B["OrderRepository.save(entity)"]
    B --> C["JPA Persistence Context"]
    C --> D["Flush SQL"]
    D --> E{"Transaction outcome"}
    E -->|"COMMIT"| F[("Database row committed")]
    E -->|"ROLLBACK"| G["Change not committed"]
    F --> H["Independent read verifies state"]
    M["Mockito mock repository"] -. "Stops here" .-> B
~~~

Sơ đồ khái quát một transaction JPA thông thường. Tùy ID generation, cascade và provider, SQL có thể được thực thi ở các thời điểm khác nhau. Không dựa vào một thời điểm SQL cố định nếu chưa đặc tả cách sinh ID và flush mode.

## 3. Ranh giới kiểm thử xác định repository nào được mock

Một dependency có thể đóng vai trò khác nhau tùy **phạm vi test**:

| Tầng kiểm thử | System under test | Repository của chính module |
| --- | --- | --- |
| **Unit test service** | Một object `OrderService`, không Spring. | **Có thể mock** để điều khiển/quan sát orchestration; không khẳng định database. |
| **Unit test domain policy** | `OrderPolicy` thuần Java. | Thường không cần repository. |
| **JPA slice** | Entity mapping, repository queries, database constraints. | **Giữ thật** bằng `@DataJpaTest`. |
| **Spring Modulith module test** | Hành vi module `orders`, transaction, database và event. | **Giữ thật** nếu mục tiêu có persistence. |
| **Tích hợp nhiều module** | `orders` phối hợp `customers`/module khác. | Giữ thật những repository liên quan đến hợp đồng cần kiểm tra. |
| **Application/system test** | Toàn ứng dụng qua API/broker. | Dùng persistence infrastructure thật hoặc test environment đại diện. |

**Ranh giới cần mock ở module test thường là public API của module khác hoặc một I/O port ngoài hệ thống**, không phải repository thuộc chính module đang bảo vệ.

Trong ví dụ sau, module `orders` dùng `customers.api.CustomerEligibility` để xác minh khách hàng. `CustomerEligibility` có thể được mock khi test riêng `orders`; `orders.internal.OrderRepository` phải thật để test có thể kiểm chứng dữ liệu.

## 4. Ví dụ xuyên suốt: module orders và customers

Giả sử Spring Boot application root package là `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── customers
│   ├── api
│   │   ├── CustomerEligibility.java
│   │   └── package-info.java
│   └── internal
│       ├── CustomerEligibilityService.java
│       └── CustomerRepository.java
└── orders
    ├── OrderService.java
    ├── OrderRejectedException.java
    ├── package-info.java
    ├── events
    │   ├── OrderPlaced.java
    │   └── package-info.java
    └── internal
        ├── OrderEntity.java
        ├── OrderStatus.java
        └── OrderRepository.java
~~~

Yêu cầu nghiệp vụ:

1. Khách hàng phải được xác minh bởi public API `customers.api.CustomerEligibility`.
2. `orders` chỉ chấp nhận amount dương và `clientReference` không rỗng.
3. Mỗi `clientReference` phải **duy nhất** theo hợp đồng của ví dụ.
4. Khi đủ điều kiện, lưu `OrderEntity` với `OrderStatus.ACCEPTED`.
5. Phát `OrderPlaced` chứa `orderId`, `customerId`, amount và `eventId`.
6. Nếu lỗi phát sinh trước commit, transaction của module `orders` phải rollback.

~~~mermaid
flowchart LR
    T["@ApplicationModuleTest orders"] --> S["orders.OrderService (THẬT)"]
    S --> C["customers.api.CustomerEligibility (MOCK)"]
    S --> R["orders.internal.OrderRepository (THẬT)"]
    S --> P["ApplicationEventPublisher (THẬT)"]
    R --> DB[("Test database")]
    P --> EV["PublishedEvents"]
    R2["customers.internal.CustomerRepository"] -. "Không nạp ở STANDALONE" .-> C
~~~

Mục tiêu của sơ đồ là **không cần khởi động implementation của `customers` nhưng vẫn kiểm tra persistence của `orders` thật**.

### 4.1. Public API và named interface của customers

File `customers/api/CustomerEligibility.java`:

~~~java
package com.example.shop.customers.api;

import java.util.UUID;

public interface CustomerEligibility {
    boolean canPlaceOrder(UUID customerId);
}
~~~

File `customers/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.customers.api;
~~~

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "customers :: api"
)
package com.example.shop.orders;
~~~

Với module detection mặc định theo package con trực tiếp, `orders` chỉ nên import `customers.api`. Không inject `customers.internal.CustomerRepository` vào `orders` để thuận tiện cho test; đó là vi phạm ranh giới và không được hợp thức hóa bằng Mockito.

## 5. Entity và repository có những bất biến persistence thật

File `orders/internal/OrderStatus.java`:

~~~java
package com.example.shop.orders.internal;

public enum OrderStatus {
    ACCEPTED,
    CANCELLED
}
~~~

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "shop_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_shop_orders_client_reference",
        columnNames = "client_reference"))
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(name = "client_reference",
            nullable = false, length = 64)
    private String clientReference;

    @Column(name = "total", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal total;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    protected OrderEntity() {} // Constructor dành cho JPA.

    public OrderEntity(UUID id,
                       UUID customerId,
                       String clientReference,
                       BigDecimal total) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.clientReference = Objects.requireNonNull(clientReference);
        this.total = Objects.requireNonNull(total);
        this.status = OrderStatus.ACCEPTED;
    }

    public UUID getId() { return id; }
    public UUID getCustomerId() { return customerId; }
    public String getClientReference() { return clientReference; }
    public BigDecimal getTotal() { return total; }
    public OrderStatus getStatus() { return status; }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity> findByClientReference(
            String clientReference);
}
~~~

Trong mẫu này, có nhiều thứ chỉ database/JPA thực mới giúp kiểm tra được:

- `@Table(name = "shop_orders")` và tên các column.
- `@Enumerated(EnumType.STRING)` có ghi `ACCEPTED` đúng cách không.
- `BigDecimal` với `precision=19, scale=2` có giữ giá trị như mong đợi không.
- `nullable=false` có được thực thi trong schema đang chạy không.
- Unique constraint `uk_shop_orders_client_reference` có thực sự tồn tại không.
- `findByClientReference(...)` có tạo truy vấn chính xác không.

**Mock `OrderRepository` không thực thi bất kỳ kiểm tra nào trong danh sách này.**

> Giới hạn của mã mẫu: trong production cần khai báo migration Flyway/Liquibase, quy tắc tiền tệ, index, tenancy, concurrency, timezone, audit và versioning tương ứng. Annotation `@UniqueConstraint` chỉ phát sinh DDL tự động nếu schema generation được bật; nếu production dùng migration, test phải chạy migration ấy để chứng minh constraint thật tồn tại.

## 6. Service dùng transaction và phát event thật

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        Instant occurredAt
) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `orders/OrderRejectedException.java`:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public class OrderRejectedException extends RuntimeException {
    public OrderRejectedException(UUID customerId) {
        super("Customer not eligible: " + customerId);
    }
}
~~~

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final CustomerEligibility customers;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(CustomerEligibility customers,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.customers = customers;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public UUID place(UUID orderId,
                      UUID customerId,
                      String clientReference,
                      BigDecimal total) {
        createOrderAndPublish(
                orderId, customerId, clientReference, total);
        return orderId;
    }

    @Transactional
    public void placeAndFail(UUID orderId,
                             UUID customerId,
                             String clientReference,
                             BigDecimal total) {
        createOrderAndPublish(
                orderId, customerId, clientReference, total);

        // Chỉ dành cho minh họa rollback trong test.
        throw new IllegalStateException("Simulated failure");
    }

    private void createOrderAndPublish(UUID orderId,
                                       UUID customerId,
                                       String clientReference,
                                       BigDecimal total) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(clientReference, "clientReference");
        Objects.requireNonNull(total, "total");

        if (clientReference.isBlank() ||
                clientReference.length() > 64 ||
                total.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid order input");
        }

        if (!customers.canPlaceOrder(customerId)) {
            throw new OrderRejectedException(customerId);
        }

        orders.save(new OrderEntity(
                orderId, customerId, clientReference, total));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, customerId,
                total, Instant.now()));
    }
}
~~~

`OrderService` là **system under test**. `CustomerEligibility` là collaborator ngoài module. `OrderRepository` và publisher là hạ tầng thật của module `orders`.

Lưu ý:

1. Hai public methods được gọi **qua Spring bean/proxy** trong module test. Helper private `createOrderAndPublish` thực thi bên trong transaction đã mở. Không gọi tự tham chiếu một method `@Transactional` khác trên `this` rồi kỳ vọng một proxy transaction mới.
2. `orders.save(...)` có thể chưa flush SQL ngay; khi method `place` trả về thành công qua proxy, transaction thường đã commit.
3. Một unchecked exception trong `placeAndFail` khiến transaction nguồn rollback theo cấu hình mặc định của Spring.
4. `publisher.publishEvent` xảy ra **trong** transaction nguồn; thấy event được phát chưa có nghĩa một listener sau commit đã xử lý.
5. `placeAndFail` là ví dụ sư phạm. Trong production hãy test kịch bản lỗi thực hoặc fixture, không tạo API public cố ý ném exception.

## 7. Anti-pattern: module test mock repository rồi tuyên bố đã kiểm tra lưu dữ liệu

Đây là test **chống-pattern**:

~~~java
@ApplicationModuleTest
class MisleadingOrderPersistenceTests {

    @Autowired OrderService service;

    @MockitoBean CustomerEligibility customers;

    // Sai mục tiêu: thay chính repository cần kiểm chứng.
    @MockitoBean OrderRepository repository;

    @Test
    void storesOrder() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(customers.canPlaceOrder(customerId))
                .thenReturn(true);

        service.place(
                orderId, customerId,
                "client-ref-001", new BigDecimal("100000.00"));

        verify(repository).save(any(OrderEntity.class));
    }
}
~~~

Test có thể xanh ngay cả khi:

- Table `shop_orders` không tồn tại.
- Mapping `client_reference` sai.
- Unique constraint đã bị xóa khỏi migration.
- Entity dùng sai column type.
- Transaction không commit.
- Database không có row nào với `orderId` đó.

`@MockitoBean OrderRepository` thay bean repository bằng Mockito mock trong Spring Test context. Khi `OrderService` gọi `save`, mock ghi nhận invocation, **không chạy JPA implementation**. Bài test chỉ đo orchestration, nhưng tên `storesOrder` đưa ra kết luận quá rộng.

### 7.1. Verify save không chứng minh tham số thật đúng nếu dùng any()

~~~java
verify(repository).save(any(OrderEntity.class));
~~~

Câu này cũng không khẳng định `OrderEntity` có đúng `customerId`, `clientReference`, `total` hay `status`.

Để test riêng orchestration, có thể dùng `ArgumentCaptor<OrderEntity>` và assert các trường; nhưng dù payload đúng, **vẫn không có bằng chứng persistence**. Một database test khác vẫn là bắt buộc nếu tính bền vững dữ liệu là hợp đồng.

### 7.2. Nút thắt: test dừng trước JPA

~~~mermaid
flowchart LR
    S["OrderService thật"] --> M["OrderRepository Mockito mock"]
    M --> V["verify(save) PASS"]
    D[("Real database")] -. "Không có lời gọi" .-> M
    C["JPA mapping/constraints"] -. "Không được chạy" .-> M
~~~

Thêm nhiều `verifyNoMoreInteractions`, `InOrder` hay `times(1)` **không mở lại đường đi từ mock tới database**.

## 8. Trường hợp đúng để mock repository: unit test orchestration

Trong một unit test **không khởi động Spring**, repository là port của class `OrderService`. Mock cho phép điều khiển phản hồi và kiểm tra dữ liệu được truyền đi nhanh chóng.

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.orders.internal.OrderStatus;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock CustomerEligibility customers;
    @Mock OrderRepository repository;
    @Mock ApplicationEventPublisher publisher;

    @Test
    void preparesExpectedEntityForRepository() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        String reference = "reference-123";
        var amount = new BigDecimal("100000.00");

        when(customers.canPlaceOrder(customerId))
                .thenReturn(true);

        var service = new OrderService(
                customers, repository, publisher);

        service.place(orderId, customerId, reference, amount);

        var captor = ArgumentCaptor.forClass(OrderEntity.class);
        verify(repository).save(captor.capture());

        var submitted = captor.getValue();
        assertThat(submitted.getId()).isEqualTo(orderId);
        assertThat(submitted.getCustomerId())
                .isEqualTo(customerId);
        assertThat(submitted.getClientReference())
                .isEqualTo(reference);
        assertThat(submitted.getTotal())
                .isEqualByComparingTo(amount);
        assertThat(submitted.getStatus())
                .isEqualTo(OrderStatus.ACCEPTED);

        verify(publisher).publishEvent(
                org.mockito.ArgumentMatchers.any(OrderPlaced.class));
    }
}
~~~

**Kết luận hợp lệ từ unit test này:** service tạo entity với dữ liệu đúng, yêu cầu repository lưu nó và yêu cầu publisher phát sự kiện. **Không hợp lệ:** “row đã được lưu/commit trong database” hoặc “listener `AFTER_COMMIT` đã chạy”.

`@Transactional` của service **không mở transaction** trong unit test vì service được tạo bằng `new`, không qua Spring proxy. Test dùng Mockito `@Mock`, không dùng Spring Test bean override.

### 8.1. Test negative path trong unit test

~~~java
@Test
void rejectedCustomerDoesNotRequestPersistence() {
    UUID customerId = UUID.randomUUID();
    when(customers.canPlaceOrder(customerId))
            .thenReturn(false);

    var service = new OrderService(
            customers, repository, publisher);

    assertThatThrownBy(() ->
            service.place(
                    UUID.randomUUID(),
                    customerId,
                    "reference-456",
                    new BigDecimal("100000.00")))
            .isInstanceOf(OrderRejectedException.class);

    verifyNoInteractions(repository, publisher);
}
~~~

Đoạn này nằm trong `OrderServiceUnitTests`, cần static imports `assertThatThrownBy` và `verifyNoInteractions`. Nó bảo vệ hợp đồng **không yêu cầu lưu/phát** khi khách bị từ chối. Nhưng vẫn chỉ là bằng chứng về method invocations trên mocks.

## 9. Module test đúng: giữ JPA repository thật, mock API ngoài module

Trong `@ApplicationModuleTest`, bootstrap mode mặc định là `STANDALONE`: chỉ nạp module chứa test. Implementation của `CustomerEligibility` ở `customers` có thể không được nạp; dùng `@MockitoBean` để cung cấp public collaborator giả. **Không khai báo `@MockitoBean OrderRepository`**.

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.orders.internal.OrderStatus;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderModulePersistenceTests {

    @Autowired OrderService service;

    // Bean của Spring Data JPA thật.
    @Autowired OrderRepository repository;

    // Chỉ thay public collaborator ngoài module orders.
    @MockitoBean CustomerEligibility customers;

    @Test
    void acceptedOrderIsStoredAndEventIsPublished(
            PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        String reference = "ref-" + UUID.randomUUID();
        var amount = new BigDecimal("100000.00");

        when(customers.canPlaceOrder(customerId))
                .thenReturn(true);

        service.place(orderId, customerId, reference, amount);

        verify(customers).canPlaceOrder(customerId);

        // Truy vấn repository thật, không verify save trên mock.
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order -> {
                    assertThat(order.getCustomerId())
                            .isEqualTo(customerId);
                    assertThat(order.getClientReference())
                            .isEqualTo(reference);
                    assertThat(order.getTotal())
                            .isEqualByComparingTo(amount);
                    assertThat(order.getStatus())
                            .isEqualTo(OrderStatus.ACCEPTED);
                });

        assertThat(repository.findByClientReference(reference))
                .isPresent();

        // Publisher thật; sự kiện được quan sát trong module test.
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId())
                            .isEqualTo(customerId);
                    assertThat(event.total())
                            .isEqualByComparingTo(amount);
                });
    }
}
~~~

Test sử dụng Spring Test context, `OrderService` thật, Spring Data JPA repository thật và `ApplicationEventPublisher` thật. Nó kiểm chứng **dữ liệu đọc lại** cộng với một `OrderPlaced` có payload đúng, thay vì chỉ kiểm tra lời gọi `save`.

Điều kiện chạy: module test starter, Spring Data JPA, datasource, transaction manager và schema `shop_orders` phải được cấu hình. Với Spring Framework 6.2+ (ví dụ Spring Boot 3.4+), `@MockitoBean` là annotation tương ứng; Boot cũ có thể cần `@MockBean` theo phiên bản.

### 9.1. Tại sao không mock event publisher?

Nếu module test muốn kiểm tra event thực, đừng thay `ApplicationEventPublisher` bằng Mockito mock. `PublishedEvents` quan sát việc Spring phát event, còn `verify(mockPublisher).publishEvent(...)` chỉ chứng minh lời gọi Java.

**Nhưng `PublishedEvents` cũng có giới hạn:** nó không tự chứng minh transaction đã commit, listener module ngoài đã chạy, hay Event Publication Registry đã hoàn tất một publication. Bài test producer và listener/registry integration test bảo vệ những tầng khác nhau.

## 10. Phân biệt kết quả đọc trong cùng transaction và đọc sau commit

JPA có **first-level cache/persistence context**. Nếu một test đang ở cùng transaction và `EntityManager`, `findById(id)` có thể trả entity **đang managed** mà không cần truy vấn database mới. Một assertion như:

~~~java
repository.save(entity);
assertThat(repository.findById(id)).isPresent();
~~~

chưa chắc chứng minh SQL đã flush, càng chưa chắc chứng minh transaction đã commit.

Để tăng sức mạnh bằng chứng, có thể:

1. `flush()` những thay đổi để database thực thi SQL/constraints.
2. `clear()` persistence context trước khi query lại, tránh trả entity từ first-level cache.
3. Kết thúc transaction thành công rồi đọc từ **transaction khác** nếu muốn chứng minh commit.
4. Khi cần khẳng định SQL/schema thực, kiểm tra bằng JDBC hoặc database test chuyên biệt, không chỉ dùng object state.

### 10.1. @DataJpaTest: ép flush, clear rồi đọc lại

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class OrderRepositoryJpaTests {

    @Autowired OrderRepository repository;
    @PersistenceContext EntityManager entityManager;

    @Test
    void writesSqlAndReloadsMappedEntity() {
        UUID id = UUID.randomUUID();
        String reference = "ref-" + UUID.randomUUID();

        repository.save(new OrderEntity(
                id, UUID.randomUUID(), reference,
                new BigDecimal("12345.60")));

        entityManager.flush();
        entityManager.clear();

        var reloaded = repository.findById(id).orElseThrow();
        assertThat(reloaded.getClientReference())
                .isEqualTo(reference);
        assertThat(reloaded.getTotal())
                .isEqualByComparingTo("12345.60");
        assertThat(reloaded.getStatus())
                .isEqualTo(OrderStatus.ACCEPTED);
    }
}
~~~

`flush` buộc Hibernate đồng bộ SQL tới DB trong transaction hiện tại; `clear` buộc JPA tải lại thay vì trả entity managed cũ.

**Quan trọng:** `@DataJpaTest` mặc định transactional và **rollback sau mỗi test**. Test này chứng minh SQL/mapping/read-back **trong transaction**, không chứng minh row còn tồn tại sau khi test kết thúc.

### 10.2. @DataJpaTest không kiểm tra toàn bộ module

JPA slice test chủ yếu kiểm tra entity, repository, query và persistence configuration. Nó **không thay thế** `@ApplicationModuleTest` cần chạy `OrderService`, transaction business và Spring events. Hai loại test bổ sung cho nhau.

## 11. save(), saveAndFlush() và commit: bảng sự thật

| Thao tác | Có thể làm gì? | Không mặc nhiên chứng minh |
| --- | --- | --- |
| `repository.save(entity)` | Đưa entity vào trạng thái được quản lý/thực hiện persist hoặc merge theo Spring Data. | SQL đã gửi, constraint đã kiểm tra, commit. |
| `repository.saveAndFlush(entity)` | Save rồi yêu cầu flush persistence context. | Transaction đã commit, dữ liệu sẽ sống sau rollback. |
| `entityManager.flush()` | Đồng bộ pending changes thành SQL trong transaction. | Commit thành công hoặc side effect ngoài DB đã hoàn tất. |
| `entityManager.clear()` | Loại managed entities khỏi persistence context. | Commit; nó chỉ giúp lần đọc sau không dựa vào cache cấp một. |
| `TransactionTemplate.execute(...)` trả thành công | Transaction do template quản lý đã kết thúc theo propagation/cấu hình. | Mọi external side effect chắc chắn thành công. |
| Lời gọi method `@Transactional` qua proxy trả thành công | Với transaction do method mở, commit thường hoàn tất trước khi trả về. | Mọi listener async hoặc broker đã completed. |
| `verify(mockRepo).save(...)` | Một invocation phù hợp đã xảy ra. | **Bất kỳ** đặc tính JPA/database kể trên. |

### 11.1. Khi nào constraint lỗi xuất hiện?

Với unique constraint, lỗi có thể xuất hiện **khi flush hoặc commit**, không nhất thiết tại `save`. Bởi vậy đoạn này chưa đủ:

~~~java
repository.save(first);
repository.save(second);
// Không có assert hoặc flush: chưa biết constraint được kiểm tra.
~~~

Hãy dùng repository thật, schema thật, ép flush khi cần và assert exception hoặc outcome **trong transaction phù hợp**. Tránh lấy `save` không ném lỗi làm bằng chứng DB đã chấp nhận dữ liệu.

## 12. Unique constraint: mock repository dễ bỏ lọt hồi quy

Giả sử hợp đồng yêu cầu không có hai order có cùng `clientReference`. Lỗi trong production migration vô tình xóa unique index. Một test Mockito:

~~~java
verify(repository, times(2)).save(any(OrderEntity.class));
~~~

không thể phát hiện chuyện đó. Mock **không có index** để thực thi và cũng không phản hồi như database.

### 12.1. JPA test phát hiện duplicate khi flush

~~~java
@Test
void databaseRejectsDuplicateClientReference() {
    String reference = "dup-" + UUID.randomUUID();

    repository.saveAndFlush(new OrderEntity(
            UUID.randomUUID(), UUID.randomUUID(),
            reference, new BigDecimal("100.00")));

    assertThatThrownBy(() ->
            repository.saveAndFlush(new OrderEntity(
                    UUID.randomUUID(), UUID.randomUUID(),
                    reference, new BigDecimal("200.00"))))
            .isInstanceOf(
                    org.springframework.dao.DataIntegrityViolationException.class);
}
~~~

Đây là method bổ sung trong `OrderRepositoryJpaTests`, cần static import `assertThatThrownBy`. Spring Data thường chuyển exception ràng buộc DB thành `DataIntegrityViolationException`; loại exception cụ thể có thể phụ thuộc JPA provider, dialect và vị trí lỗi (flush/commit). Nếu test chạy với database khác production, hãy hiệu chỉnh assertion theo contract thực và verify schema/migration, thay vì bắt một implementation detail của vendor.

**Không tiếp tục truy vấn với cùng `EntityManager` sau constraint violation** trong test này; JPA transaction có thể đã bị đánh dấu rollback-only. Để test logic recovery, dùng transaction riêng và boundary rõ ràng.

### 12.2. Rủi ro của check-then-insert

Một service có thể kiểm tra:

~~~java
if (repository.findByClientReference(reference).isPresent()) {
    throw new DuplicateOrderReferenceException();
}
repository.save(entity);
~~~

Nhưng dưới concurrency, hai transaction đều có thể đọc “chưa tồn tại” trước khi cùng insert. Vì vậy database unique constraint/transaction isolation vẫn quan trọng; mock repository có thể được stub để trả empty cho cả hai và không phát hiện race.

Nếu cần chính sách trả lỗi nghiệp vụ rõ ràng, đặt chuyển đổi exception ở transaction boundary thích hợp và kiểm tra bằng integration test trên database tương ứng. **Đừng dựa vào mock `findBy...` để chứng minh không trùng dữ liệu trong hệ thống nhiều request đồng thời.**

## 13. Rollback: verify(save) vẫn có thể PASS dù row không được commit

Trong `OrderService.placeAndFail`, thứ tự là:

~~~text
transaction BEGIN
  orders.save(new OrderEntity(...))
  publisher.publishEvent(new OrderPlaced(...))
  throw IllegalStateException
transaction ROLLBACK
~~~

Ở unit test:

~~~java
var service = new OrderService(customers, repository, publisher);
service.placeAndFail(orderId, customerId, reference, amount);
~~~

vì `repository` là mock và không có Spring transaction proxy, `verify(repository).save(...)` vẫn pass, nhưng test **không có khái niệm database rollback**.

### 13.1. Module test kiểm tra rollback của database thật

Thêm method vào `OrderModulePersistenceTests`:

~~~java
@Test
void failureAfterSaveRollsBackOrder(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    String reference = "rollback-" + UUID.randomUUID();

    when(customers.canPlaceOrder(customerId))
            .thenReturn(true);

    assertThatThrownBy(() ->
            service.placeAndFail(
                    orderId, customerId, reference,
                    new BigDecimal("100000.00")))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Simulated failure");

    // Lời gọi save đã diễn ra, nhưng transaction rollback.
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(repository.findByClientReference(reference))
            .isEmpty();

    // PublishedEvents có thể đã quan sát OrderPlaced,
    // vì publishEvent được gọi TRƯỚC exception.
    // Đừng assert events rỗng chỉ vì transaction rollback.
}
~~~

Thêm import `assertThatThrownBy`. Trong test này, tham số `events` không được dùng trực tiếp; có thể bỏ nếu không cần quan sát sự kiện. Đây là phép kiểm tra **rollback thật** khi `OrderService` được Spring quản lý, có transaction manager, repository thật và **không có outer transaction của test**.

### 13.2. Rollback không xóa sự thật “publisher đã được gọi”

Một `PublishedEvents` trong module test có thể ghi nhận event phát **trước khi transaction rollback**. Ngược lại, `@TransactionalEventListener(AFTER_COMMIT)` không chạy nếu transaction nguồn rollback. Test cần phân biệt:

1. **Publisher invocation:** có gọi `publishEvent` không?
2. **DB outcome:** commit hay rollback?
3. **Listener phase:** `AFTER_COMMIT` có thực thi?
4. **Business side effect:** module nhận có ghi/email/charge không?

Đừng dùng một `verify(save)` hay một `PublishedEvents` assertion để suy ra cả bốn.

## 14. @Transactional trên test: bẫy “đã lưu” nhưng chưa commit

Giả sử bạn viết:

~~~java
@ApplicationModuleTest
@Transactional
class TransactionalOrderTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @Test
    void orderExistsWithinOpenTestTransaction() {
        service.place(orderId, customerId, reference, amount);
        assertThat(repository.existsById(orderId)).isTrue();
    }
}
~~~

Đây là **snippet minh họa** (cần field/fixture đầy đủ), không phải test commit hợp lệ. Spring Test thường mở transaction bao ngoài test và **rollback khi test kết thúc**. `OrderService.place` có thể tham gia cùng transaction; lúc `existsById` chạy, row/managed entity có thể nhìn thấy nhưng **chưa commit**.

### 14.1. Test muốn chứng minh commit cần gì?

- Không để `@Transactional` test bao ngoài vô thức.
- Gọi public `@Transactional` method qua **Spring-managed proxy**.
- Để transaction service **hoàn tất trước khi truy vấn xác nhận**.
- Khi cần tách bạch, đọc từ transaction mới hoặc connection độc lập.
- Có test đối chứng rollback dùng cùng datasource/schema.

Trong `OrderModulePersistenceTests` ở mục 9, ta cố ý **không thêm `@Transactional` lên class hoặc method test**. Sau khi `service.place` trả thành công, transaction do service mở thường đã commit; repository query phía sau là một lời gọi mới.

### 14.2. TransactionTemplate giúp kiểm soát ranh giới rõ ràng

Một mẫu để kiểm tra persistence độc lập:

~~~java
@Autowired TransactionTemplate tx;
@Autowired OrderRepository repository;

@Test
void committedEntityIsVisibleFromSeparateRead() {
    UUID id = UUID.randomUUID();
    String reference = "tx-" + UUID.randomUUID();

    tx.executeWithoutResult(status ->
            repository.save(new OrderEntity(
                    id, UUID.randomUUID(), reference,
                    new BigDecimal("10.00"))));

    // Transaction ghi đã kết thúc thành công.
    Boolean present = tx.execute(status ->
            repository.existsById(id));

    assertThat(present).isTrue();
}
~~~

Đây là snippet của một Spring/JPA integration test có `TransactionTemplate` bean, không đặt trong một outer `@Transactional` test. Nếu thực sự có outer transaction, propagation `REQUIRED` mặc định của template sẽ **join** giao tác đó, không tạo một commit riêng. Cấu hình transaction manager/propagation rõ ràng là điều kiện để kết luận đúng.

### 14.3. TestTransaction và @Commit phải dùng có chủ đích

Trong Spring Test, `TestTransaction` cho phép điều khiển kết thúc transaction do test quản lý; `@Commit` hoặc `@Rollback(false)` thay đổi hành vi mặc định. Dùng chúng khi cần kiểm tra mốc commit cụ thể, nhưng phải dọn dữ liệu test và tránh làm các test khác phụ thuộc state còn lại.

`@DataJpaTest` thường rollback để cô lập test; điều đó **tốt cho JPA slice**, nhưng không nên nhầm một assertion trong transaction đó với bằng chứng durable commit.

## 15. Nhánh từ chối: không lưu, không phát event

Một bài test âm tính có thể viết hoàn toàn trong module context, chỉ mock public API ngoài module:

~~~java
@Test
void rejectedCustomerCreatesNoOrderAndNoEvent(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    String reference = "denied-" + UUID.randomUUID();

    when(customers.canPlaceOrder(customerId)).thenReturn(false);

    assertThatThrownBy(() ->
            service.place(orderId, customerId, reference,
                    new BigDecimal("100000.00")))
            .isInstanceOf(OrderRejectedException.class);

    verify(customers).canPlaceOrder(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(repository.findByClientReference(reference))
            .isEmpty();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Đây là method bổ sung vào `OrderModulePersistenceTests`, cần import `assertThatThrownBy`. Với service ví dụ, nhánh từ chối được kiểm tra **trước** `repository.save` và `publisher.publishEvent`, nên cả row và event phải vắng mặt. Điều đó **không** tạo thành quy tắc chung “transaction rollback thì `PublishedEvents` luôn rỗng”: nếu code đã phát event trước lỗi, bộ quan sát vẫn có thể thấy event.

### 15.1. Dữ liệu invalid không được chạm collaborator

~~~java
@Test
void invalidAmountDoesNotUseExternalModuleOrDb(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();

    assertThatThrownBy(() ->
            service.place(orderId, UUID.randomUUID(),
                    "ref-invalid", BigDecimal.ZERO))
            .isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(customers);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId)).isEmpty();
}
~~~

Thêm `verifyNoInteractions` và `assertThatThrownBy` static imports. Phép kiểm tra interaction bảo vệ không gọi module ngoài khi input sai, trong khi repository thật chứng minh hậu quả persistence tương ứng.

## 16. Mapping SQL và migration không được mock xác nhận thay

Annotation trên entity:

~~~java
@Column(name = "client_reference",
        nullable = false, length = 64)
private String clientReference;
~~~

không tự bảo đảm production schema có đúng column/index/constraint. Nếu dự án quản lý schema bằng Flyway hoặc Liquibase, annotations có thể lệch migration mà test mock vẫn xanh.

Ví dụ DDL PostgreSQL **minh họa** tương ứng với entity:

~~~sql
CREATE TABLE shop_orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    client_reference VARCHAR(64) NOT NULL,
    total NUMERIC(19, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    CONSTRAINT uk_shop_orders_client_reference
        UNIQUE (client_reference)
);
~~~

Đây là đoạn SQL giải thích contract, không phải migration đã được tạo trong workspace. Cần điều chỉnh theo database/tenant/migration thật. `@UniqueConstraint` chỉ ảnh hưởng DDL tự tạo khi schema generation được kích hoạt.

### 16.1. DDL generation có thể che migration lỗi

Test chạy với:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

có thể tạo schema từ entity annotations, nên vẫn pass dù migration production bị thiếu unique index. Với integration stage bảo vệ migrations, nên **chạy migrations thật** và cân nhắc:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

Cấu hình chỉ mang tính minh họa, phải phù hợp datasource và migration tool thực tế. `validate` không kiểm tra mọi constraint/index; test unique, nullability, precision và foreign key riêng nếu là yêu cầu quan trọng.

### 16.2. SQL log không chứng minh commit

Một dòng log `insert into shop_orders...` chứng minh SQL đã được tạo/gửi tại một thời điểm, không chứng minh transaction commit. Nếu Hibernate flush rồi rollback, SQL vẫn có thể xuất hiện. Test cần kiểm tra trạng thái **sau transaction boundary**; bật SQL log chỉ để phân tích khi cần.

## 17. Database thử nghiệm nên đại diện được cho production

`@DataJpaTest` với H2 hữu ích và nhanh, nhưng có khác biệt so với PostgreSQL/MySQL/Oracle:

| Khác biệt | Rủi ro |
| --- | --- |
| `UUID`, `JSONB`, native enum, array | Entity/query pass trong H2 nhưng fail trên production DB. |
| Collation/case sensitivity, unique constraints | Hai chuỗi được coi là trùng/khác khác nhau. |
| Numeric scale/rounding | Giá trị `BigDecimal` không được lưu như kỳ vọng. |
| Native SQL và dialect | Query sai cú pháp hoặc functions không tương thích. |
| Isolation, locks và deadlocks | Race condition chỉ xuất hiện với DB thực. |
| Triggers, generated columns, migrations | Schema tự tạo không có hành vi production. |

H2 có thể đủ cho smoke/JPA mapping cơ bản. Nếu test nhằm bảo vệ schema, native query, unique constraint, locking hoặc transaction semantics, nên có integration test với database gần production.

### 17.1. Ví dụ Testcontainers dành cho module test

Trong Spring Boot 3.1+ có hỗ trợ `@ServiceConnection`, có thể dùng:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@ApplicationModuleTest
class OrderPostgresModuleTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @MockitoBean CustomerEligibility customers;
    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @Test
    void persistsUsingRealPostgres() {
        // Stub public CustomerEligibility; gọi service.place(...).
        // Đọc lại bằng real repository/JDBC sau transaction commit.
        // Assert schema và constraint của PostgreSQL thực.
    }
}
~~~

Đây là **test skeleton**, không phải class tự chạy nếu chưa bổ sung imports, fixtures, module Testcontainers, datasource và schema/migrations. Chọn image version phù hợp production. Với Boot cũ không có `@ServiceConnection`, dùng `@DynamicPropertySource` hoặc cấu hình datasource tương thích.

**Không cần Testcontainers trong mọi unit test.** Domain rules thuần vẫn nên chạy nhanh; chọn database thật khi đặc tính vendor ảnh hưởng hợp đồng.

## 18. Read-back bằng JDBC tránh phụ thuộc JPA first-level cache

Nếu một test đọc `repository.findById` trong **cùng persistence context**, JPA có thể trả entity managed, chưa cần query DB. Một phép đối chứng sau khi transaction ghi đã commit là `JdbcTemplate`:

~~~java
@Autowired JdbcTemplate jdbc;

@Test
void committedOrderIsVisibleInSqlQuery() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    String reference = "jdbc-" + UUID.randomUUID();

    when(customers.canPlaceOrder(customerId)).thenReturn(true);
    service.place(orderId, customerId, reference,
            new BigDecimal("100.00"));

    Integer rows = jdbc.queryForObject(
            "SELECT COUNT(*) FROM shop_orders WHERE id = ?",
            Integer.class,
            orderId);

    assertThat(rows).isEqualTo(1);
}
~~~

Snippet thuộc module test có datasource và `JdbcTemplate` phù hợp, không đặt trong outer transaction tự rollback. Binding `UUID` có thể cần thích ứng với driver/dialect. Truy vấn JDBC thực hiện SQL, không lấy entity từ JPA first-level cache.

**Quan trọng:** Nếu JDBC query ở **cùng transaction chưa commit**, nó vẫn có thể thấy dữ liệu pending. Sức mạnh bằng chứng phụ thuộc **thời điểm đọc và transaction isolation**, không phải chỉ thay `findById` bằng `SELECT`.

## 19. Query, converter và lazy loading cũng không xuất hiện trong mock

Một repository thật còn có thể gặp:

- Derived query `findByClientReference` sai property hoặc mapping.
- `@OneToMany`/`@ManyToOne` cascade/orphan removal không như mong đợi.
- `LazyInitializationException` khi truy cập association sau transaction.
- Projection/DTO không map đúng alias và kiểu dữ liệu.
- Native query sai dialect hoặc case sensitivity.
- Performance N+1, lock và isolation issue.

Nếu test chỉ viết:

~~~java
when(repository.findByClientReference(reference))
        .thenReturn(Optional.of(expectedOrder));
~~~

thì nó trả object do test cung cấp, không thực thi query derivation/SQL/converter.

### 19.1. JPA slice kiểm tra query thật

~~~java
@Test
void queriesPersistedOrderByClientReference() {
    String reference = "query-" + UUID.randomUUID();
    UUID id = UUID.randomUUID();

    repository.saveAndFlush(new OrderEntity(
            id, UUID.randomUUID(), reference,
            new BigDecimal("42.00")));
    entityManager.clear();

    assertThat(repository.findByClientReference(reference))
            .get()
            .extracting(OrderEntity::getId)
            .isEqualTo(id);
}
~~~

Đây là method của `OrderRepositoryJpaTests` mục 10. Repository và EntityManager là real beans; test sẽ chạy query thật, không trả trước giá trị `Optional` được stub.

## 20. @MockitoSpyBean trên repository cũng chưa phải lựa chọn tốt

`@MockitoBean OrderRepository` thay real repository bằng mock, nên không có persistence. Nhưng `@MockitoSpyBean OrderRepository` cũng thường **không cần thiết** khi mục tiêu là persistence.

~~~java
@ApplicationModuleTest
class OrdersWithSpyRepository {
    @MockitoSpyBean OrderRepository repository;
}
~~~

Spy wrap một bean thật; method chưa stub thường thực thi real JPA operations. Điều đó có thể gây side effect **ngay ở bước stubbing**:

~~~java
when(repository.findByClientReference(reference))
        .thenReturn(Optional.empty());
~~~

Trên spy, real query có thể chạy khi biểu thức `when(spy.method())` được đánh giá. `doReturn(...).when(spy).method(...)` tránh gọi real method lúc setup trong trường hợp spy thông thường, nhưng đồng thời **chặn chính truy vấn** mà bạn cần kiểm chứng. Spring Data repository còn được quản lý qua proxies/transaction advice, khiến stubbing spy phức tạp.

**Khuyến nghị:** Trong persistence test, dùng repository thật **không spy**, query row và constraint trực tiếp. Trong unit orchestration test, dùng `@Mock` theo đúng scope. Đừng chuyển qua spy chỉ để có `verify(repository.save)` cùng với Spring context.

## 21. Sự kiện và persistence là hai loại bằng chứng độc lập

`OrderService.place` làm hai việc: yêu cầu lưu order và phát `OrderPlaced`. Với unit test, mock repository/publisher chỉ xác nhận **hai lời gọi**. Với module test, cần:

1. Query repository/JDBC thật để biết dữ liệu đã lưu theo contract.
2. Dùng `PublishedEvents` để biết sự kiện đã được phát qua Spring infrastructure.
3. Test transaction commit/rollback riêng nếu sự kiện gắn với transaction nguồn.
4. Test listener `AFTER_COMMIT` riêng nếu side effect của module nhận là mục tiêu.

**Event được phát trong transaction trước rollback** vẫn có thể được `PublishedEvents` quan sát. Nó không chứng minh row đã commit. Ngược lại, row order commit không chứng minh listener khác đã xử lý hoặc Event Publication Registry đã hoàn tất publication theo target.

### 21.1. Test AFTER_COMMIT cần positive/negative control

Khi hợp đồng yêu cầu “chỉ xử lý order sau commit”, nên có:

- **Commit case:** gọi Spring-managed service, order có row committed; listener `AFTER_COMMIT` nhận event.
- **Rollback case:** phát event rồi ném exception; row không commit; listener `AFTER_COMMIT` không nhận.
- **Positive control:** bảo đảm listener có đăng ký và thực sự chạy ở case commit; nếu chỉ kiểm tra rollback âm tính, test vẫn có thể pass khi listener hoàn toàn vắng mặt.

Với `@ApplicationModuleListener` async, dùng `Scenario`/Awaitility và side-effect/registry assertions. `verify(mockRepository).save` không bao phủ bất kỳ một phần nào của listener completion.

## 22. Mock collaborator ngoài module, không mock repository nội bộ

Trong module test `orders`, dependency công khai:

~~~java
import com.example.shop.customers.api.CustomerEligibility;
~~~

được thay bằng:

~~~java
@MockitoBean CustomerEligibility customers;
~~~

Đây là lựa chọn phù hợp vì `@ApplicationModuleTest(STANDALONE)` không nạp implementation thật ở `customers`. Trong Spring Framework 6.2+, `@MockitoBean` mặc định dùng **REPLACE_OR_CREATE** nên có thể tạo bean mock cho collaborator vắng mặt. Đừng dùng `enforceOverride = true` nếu mục tiêu là tạo mock khi không có bean thật.

Khi muốn kiểm tra hai module tích hợp thật, chọn:

~~~java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealCustomersTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;
    @Autowired CustomerFixture customerFixture;

    @Test
    void eligibleCustomerFromRealModuleCreatesOrder() {
        UUID customerId =
                customerFixture.createEligibleCustomer();
        UUID orderId = UUID.randomUUID();

        service.place(orderId, customerId,
                "real-" + UUID.randomUUID(),
                new BigDecimal("100.00"));

        assertThat(orders.existsById(orderId)).isTrue();
    }
}
~~~

`CustomerFixture` là **test fixture giả định cần triển khai**, không phải API có sẵn của Spring Modulith. Trong integration test này không mock `CustomerEligibility`, vì cần kiểm tra bean thật/wiring/contract giữa hai module. Việc `OrderRepository` vẫn chạy thật tiếp tục bảo vệ persistence.

### 22.1. Mock repository của module khác không chữa dependency sai

Nếu `orders` inject thẳng `customers.internal.CustomerRepository`, rồi test khai báo `@MockitoBean CustomerRepository` để context khởi động, sự phụ thuộc trái luật vẫn tồn tại. Sửa kiến trúc bằng public/named interface `customers :: api`, sau đó chạy `ApplicationModules.verify()`.

## 23. ApplicationModules.verify() bảo vệ một loại lỗi khác

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

`ApplicationModules.verify()` kiểm tra module dependency graph, API không được công bố, vòng phụ thuộc và `allowedDependencies` theo Spring Modulith. Nó **không thực thi JPA SQL hoặc kiểm tra transaction commit**.

Hai dạng hồi quy cần được kiểm tra độc lập:

- **Kiến trúc đúng, persistence sai:** không import trái luật, nhưng migration thiếu unique index.
- **Persistence đúng, kiến trúc sai:** order lưu được, nhưng `orders` truy cập repository nội bộ của `customers`.

Không thể thay persistence test bằng architecture test, cũng không thể thay architecture test bằng một repository query thành công.

## 24. Concurrency và idempotency: mock save không phát hiện race

Giả sử client gửi hai lệnh gần đồng thời:

~~~text
Request A: orderId=1, clientReference=R
Request B: orderId=2, clientReference=R
~~~

Nếu `OrderRepository` là mock, hai invocation `save` có thể đều được ghi nhận mà không có database constraint từ chối bản ghi trùng. Ngay cả một implementation có `findByClientReference` rồi `save` vẫn có race:

~~~text
Transaction A: SELECT R -> absent
Transaction B: SELECT R -> absent
Transaction A: INSERT R -> commit
Transaction B: INSERT R -> unique violation
~~~

### 24.1. Nhiều tầng bảo vệ idempotency

Một use case production cần cân nhắc:

1. Dùng `clientReference` hoặc `idempotencyKey` ổn định theo logical request.
2. Có unique constraint ở database, không chỉ check-then-insert.
3. Xác định hành vi khi key đã tồn tại: trả cùng kết quả hay báo duplicate.
4. Khi exception xuất hiện tại flush/commit, chuyển đổi ở đúng transaction boundary.
5. Nếu phát event, có event ID/business key ổn định khi replay.
6. Consumer có idempotency marker riêng cho side effect ngoài module.

**`OrderService` của bài chưa triển khai idempotent retry hoàn chỉnh**; nó chỉ có unique constraint ở persistence để minh họa điểm mấu chốt. Không kết luận “retry an toàn” từ việc một `save` được gọi một lần trong test.

### 24.2. Kịch bản concurrency test với database thật

Một integration test có giá trị nên:

- Khởi tạo **hai transaction độc lập** và hai request có cùng `clientReference`.
- Đồng bộ các điểm bắt đầu nhằm tạo race có kiểm soát.
- Chờ cả hai transaction hoàn tất hoặc rollback.
- Query database sau đó: chỉ **một** row có `clientReference` ấy.
- Kiểm tra kết quả bên thua phù hợp contract (exception/response/retry).

Phải quản lý executor, datasource pool, timeout và cleanup để tránh flaky. Dùng database tương ứng production khi concurrency/isolation là nội dung cần bảo vệ. Mockito `times(2)` chỉ đếm invocation, không có SQL locks hay unique constraint.

## 25. Fake in-memory repository không phải kiểm thử JPA

Một fake đơn giản:

~~~java
class InMemoryOrderStore {

    private final Map<UUID, OrderEntity> values =
            new ConcurrentHashMap<>();

    void save(OrderEntity entity) {
        values.put(entity.getId(), entity);
    }

    OrderEntity get(UUID id) {
        return values.get(id);
    }
}
~~~

là công cụ tốt khi test domain/service nhanh thông qua một abstraction thích hợp. Nhưng fake không có JPA dirty checking, SQL transaction, migration, schema constraint, lock hoặc database dialect.

| Dependency | Unit test orchestration | Module persistence test | Integration/contract test |
| --- | --- | --- | --- |
| `customers.api.CustomerEligibility` | Mock/stub. | `@MockitoBean` khi chỉ test `orders`. | Implementation thật, dữ liệu khách hàng thật. |
| `orders.internal.OrderRepository` | Có thể `@Mock`/fake theo abstraction. | **Spring Data JPA repository thật.** | Repository thật + database/migrations phù hợp production. |
| `ApplicationEventPublisher` | Có thể mock để kiểm tra request phát. | **Publisher thật + `PublishedEvents`.** | Listener/registry/transport thật theo phạm vi. |
| Email/payment HTTP gateway | Mock public I/O port. | Mock/fake I/O khi chưa test adapter. | Fake server/provider sandbox và protocol assertions. |
| Domain validation/pricing | Ưu tiên real logic. | Real logic. | Real behavior và integration invariants. |

Một fake có state giúp test các quy tắc nghiệp vụ mà không cần DB, nhưng **không đổi tên fake thành “repository integration test”** khi chưa đi qua JPA.

## 26. Ma trận quality gate trong CI

| Gate | Mục tiêu | Phương tiện | Không được suy ra |
| --- | --- | --- | --- |
| **Unit orchestration** | Entity được chuẩn bị đúng; `save`/publish được yêu cầu đúng nhánh. | Mockito `@Mock`, captor/`verify`. | DB đã commit. |
| **JPA slice** | Mapping, query, numeric, constraint. | `@DataJpaTest`, repository thật, flush/clear. | Whole module/event flow đúng. |
| **Module happy path** | Order lưu và event được phát. | `@ApplicationModuleTest`, JPA thật, `PublishedEvents`. | Listener ngoài module completed. |
| **Module rejection** | Customer bị từ chối thì không lưu/phát. | Mock public customers API, DB/event assertions. | Provider thật tuân thủ contract. |
| **Rollback** | Runtime failure làm transaction không commit. | Spring-managed service + database thật. | Event chưa từng được phát. |
| **AFTER_COMMIT** | Listener chạy sau commit, không chạy sau rollback. | Test phase có positive/negative control. | External side effect exactly-once. |
| **Migration/schema** | Columns/indexes/constraints theo production. | Flyway/Liquibase thật, validate và integration assertions. | Mọi DB failure mode đã được bao phủ. |
| **DB dialect/concurrency** | Lock, unique, native query, isolation. | Testcontainers hoặc DB gần production. | Không có bất kỳ race nào ngoài kịch bản test. |
| **Provider contract** | `customers` trả kết quả đúng dữ liệu. | Module test phía `customers`. | `orders` tự động phối hợp đúng. |
| **Wiring** | `orders` và `customers` thật làm việc được. | `DIRECT_DEPENDENCIES`/integration test. | Broker/transport đã nhận. |
| **Architecture** | Không import internal, không cycle, đúng `allowedDependencies`. | `ApplicationModules.verify()`. | SQL/commit đúng. |
| **Retry/idempotency** | Không duplicate row/effect khi replay. | Unique constraint + concurrency/integration. | Exactly-once toàn hệ thống tuyệt đối. |

CI có thể tách **PR fast gate** (unit, architecture, JPA/module tests nhanh) với **persistence/integration gate** (migrations, Testcontainers, listener, broker, concurrency) để cân bằng thời gian và độ bao phủ. Những gate quan trọng với contract hoặc rủi ro production phải tự động chạy khi thay đổi liên quan, không chỉ dựa vào test mock repository xanh.

## 27. Anti-pattern: bảng đối chiếu

| Anti-pattern | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| Mock repository rồi đặt test tên `storesOrder`. | Chỉ có invocation. | Unit test đặt tên đúng hoặc module test real repository. |
| `verify(save(any()))` là assertion duy nhất. | Không bảo vệ fields, SQL và commit. | Captor cho unit; DB read-back cho persistence. |
| `thenReturn(entity)` rồi assert entity đó. | Test tự chứng minh dữ liệu đã stub. | Real save/flush/read query. |
| `findById` trong cùng transaction rồi nói đã commit. | First-level cache có thể trả entity chưa commit. | Clear, hoặc đọc sau transaction commit. |
| Coi `saveAndFlush` là commit. | Flush có thể bị rollback. | Kiểm tra transaction boundary riêng. |
| `@DataJpaTest` tự rollback nhưng tên test nói `persistsAfterCommit`. | Mục tiêu và setup mâu thuẫn. | Slice test cho mapping, integration test cho commit. |
| Test H2 pass nên khẳng định PostgreSQL constraint đúng. | DB dialect/schema khác. | Migration + DB production-like. |
| Check-then-insert không cần unique constraint. | Hai transaction cùng thấy chưa tồn tại. | DB unique key và concurrent test. |
| Spy repository để xác nhận JPA. | Real query có thể chạy trong stubbing/AOP phức tạp. | Repository thật không spy, assert state. |
| Mock publisher trong test cần `PublishedEvents`. | Đường Spring event bị thay. | Publisher thật. |
| Có event thì nói order commit. | Event có thể phát trước rollback. | Assert DB commit và listener phase. |
| Mock `customers.internal` để context khởi động. | Che dependency sai boundary. | Public API + `ApplicationModules.verify()`. |
| Gọi `Mockito.reset` để dọn DB. | Reset không xóa row/cache/broker. | Fixture/transaction cleanup thật. |

## 28. Debug khi test xanh nhưng production không có row

Thay vì thêm `verify`, hãy hỏi theo trình tự:

1. Repository có bị thay bằng `@Mock`, `@MockitoBean`, `@MockBean` hoặc test configuration không?
2. Service có được gọi qua Spring proxy hay bằng `new` khiến `@Transactional` không hoạt động?
3. Có datasource và transaction manager đúng không? Multi-datasource/tenant schema có làm truy vấn sai DB không?
4. Có outer test `@Transactional` tự rollback hay `@DataJpaTest` transaction không?
5. `save` đã flush/commit chưa? Exception có xuất hiện ở commit?
6. Entity mapping có khớp migration thực không? Enum, converter, UUID, precision, index?
7. Test có đọc trong cùng persistence context hoặc cùng transaction chưa commit không?
8. Database production có isolation/locking/collation khác H2 không?
9. Có unique/foreign-key exception bị service catch hoặc chuyển đổi không?
10. Listener async hoặc Registry có side effect/transaction riêng khiến trạng thái quan sát khác không?
11. Có dùng repository nội bộ sai module khiến dữ liệu nằm ở nơi không mong đợi không?

Một bài test tái hiện nhỏ với **repository thật, schema thật, flush/commit rõ và read-back sau commit** thường hữu ích hơn nhiều assertion chỉ đếm lời gọi mock.

## 29. Bài tập: checkout và payment intent

Một Spring Modulith app có:

- Module `checkout` tạo `CheckoutEntity` và phát `CheckoutRequested`.
- Module `payments` công bố public API `PaymentAuthorization`.
- `CheckoutRepository` extends `JpaRepository`.
- Cột `idempotency_key` phải unique; amount là `NUMERIC(19,2)`.
- Nếu payment bị từ chối hoặc provider lỗi, checkout không được commit.
- Sau commit, listener tạo payment intent.

Team hiện có:

~~~java
@ApplicationModuleTest
class CheckoutTests {

    @MockitoBean CheckoutRepository repository;
    @MockitoBean PaymentAuthorization authorization;
    @Autowired CheckoutService service;

    @Test
    void persistenceWorks() {
        when(authorization.isApproved(any())).thenReturn(true);
        service.checkout(/* test data */);
        verify(repository).save(any(CheckoutEntity.class));
    }
}
~~~

Đây là **snippet tình huống**, chưa đầy đủ các lớp/fixtures nên không phải test compile nguyên trạng.

### Câu hỏi

1. Test trên thật sự chứng minh điều gì? Tên `persistenceWorks` sai ở đâu?
2. Muốn kiểm tra JPA mapping và unique constraint, nên viết test nào?
3. `@DataJpaTest` + `saveAndFlush` còn thiếu bằng chứng gì?
4. Muốn chắc chắn row tồn tại sau commit, cần tổ chức transaction như thế nào?
5. Khi service gọi `save` rồi ném unchecked exception, mock và real DB có thể cho kết quả trái ngược ra sao?
6. Trong `@ApplicationModuleTest(STANDALONE)`, mock `PaymentAuthorization` hay `CheckoutRepository` khi mục tiêu là DB của checkout?
7. `PublishedEvents` thấy `CheckoutRequested` trước rollback có chứng minh listener `AFTER_COMMIT` chạy không?
8. Nếu H2 pass nhưng production PostgreSQL báo duplicate-key violation, nên thêm gì?
9. `@MockitoSpyBean CheckoutRepository` có tự làm bằng chứng persistence mạnh hơn không?
10. Nếu `checkout` import `payments.internal.PaymentRepository`, gate nào phát hiện?
11. Hai request có cùng idempotency key đến đồng thời; vì sao `findBy...` rồi `save` không đủ?
12. Pipeline CI cần phân biệt những tầng bằng chứng nào?

### Đáp án gợi ý

1. Chỉ chứng minh service gọi **mock repository.save** với một `CheckoutEntity`. Không có JPA/database commit.
2. JPA slice hoặc integration test có repository/schema thật, flush/query/constraint assertions; migration test nếu schema production quan trọng.
3. Flush chưa commit, và `@DataJpaTest` thường rollback cuối test.
4. Gọi Spring-managed transactional service không nằm trong outer test rollback transaction; chờ commit rồi đọc ở transaction/connection phù hợp.
5. Mockito vẫn ghi nhận invocation; real database rollback có thể không giữ row.
6. Mock **public API ngoài module** `PaymentAuthorization`, giữ `CheckoutRepository` thật.
7. Không. Phải test transaction và listener sau commit với positive control.
8. Integration test PostgreSQL/Testcontainers chạy migrations thật và kiểm tra unique/transaction behavior.
9. Không. Spy có thể gây side effect khi stubbing và vẫn không thay state assertions.
10. `ApplicationModules.of(...).verify()` bảo vệ named interface/`allowedDependencies`.
11. Cả hai transaction có thể cùng thấy key chưa tồn tại; DB unique constraint và xử lý duplicate/idempotency là bắt buộc theo contract.
12. Unit, architecture, JPA, module persistence/rollback, production-like DB/migrations, event listener/registry và wire integration.

## 30. Checklist trước khi mock repository

- [ ] Xác định rõ mục tiêu là **method invocation** hay **database state**.
- [ ] Test mock repository được đặt tên trung thực là unit/orchestration test.
- [ ] Biết `ArgumentCaptor` chỉ chứng minh entity được truyền vào mock đúng fields.
- [ ] Không dùng `@MockitoBean` thay repository nếu cần kiểm chứng JPA mapping/commit.
- [ ] `@ApplicationModuleTest` giữ service, repository, transaction manager và publisher thật khi mục tiêu có database/event.
- [ ] Mock public API của module ngoài, không mock internal repository của module khác để chữa wiring.
- [ ] Kiểm tra table/columns, enum, precision, null/unique/foreign-key constraints bằng DB thật.
- [ ] Phân biệt `save`, `flush`, `clear`, `commit` và `read-back`.
- [ ] Hiểu `@DataJpaTest` rollback mặc định, không lấy nó làm bằng chứng durable commit.
- [ ] Hiểu `@Transactional` trên test có thể bao ngoài transaction service.
- [ ] Khi cần commit, gọi service qua Spring proxy và đọc sau transaction hoàn tất.
- [ ] Có migration/schema test thật nếu production không sinh DDL từ annotations.
- [ ] Với native query/locking, test trên DB phù hợp production.
- [ ] Unique constraint ở DB chặn race, không chỉ kiểm tra tồn tại tại service.
- [ ] Happy path, rejection và rollback có assertions database riêng.
- [ ] `PublishedEvents` chỉ chứng minh event được phát, không tự chứng minh commit/listener completion.
- [ ] AFTER_COMMIT tests có cả commit positive và rollback negative control.
- [ ] Event Registry và consumer idempotency có integration tests nếu cần reliability.
- [ ] Không spy repository chỉ để verify lời gọi trong persistence test.
- [ ] Không dùng Mockito reset như cách dọn DB/cache/broker.
- [ ] Context/datasource/test fixture không làm test phụ thuộc trạng thái test trước.
- [ ] `ApplicationModules.verify()` là architecture gate độc lập.
- [ ] CI kết hợp unit, JPA, module, migration và integration tests theo rủi ro.

**Kết luận:** `verify(mockRepository).save(entity)` có giá trị khi kiểm tra **một lời gọi của unit**, nhưng không chứng minh JPA đã lưu, SQL hợp lệ, constraint được thực thi, transaction commit hoặc dữ liệu đọc lại được. Trong Spring Modulith, hãy giữ repository của module đang test **chạy thật** trong `@ApplicationModuleTest`; kiểm tra mapping/query/constraint bằng `@DataJpaTest`; chứng minh commit/rollback với transaction rõ và database đại diện production khi cần. Mock đúng API ngoài module, dùng `PublishedEvents` cho việc phát event, và giữ `ApplicationModules.verify()` làm quality gate độc lập. Mỗi bài test nên đưa ra **đúng bằng chứng** mà mục tiêu nghiệp vụ yêu cầu.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes, module dependency mocks và `PublishedEvents`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): public module API, named interface và dependency verification.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listener, publication registry và recovery.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): entity state, `persist`, `merge` và repository save.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): JPA slice tests và Spring Test context.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction proxy, propagation và rollback.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): test bean overrides.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): real database trong integration tests.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `verify`, `ArgumentCaptor`, `times` và mock semantics.

> Ghi chú tương thích: Các ví dụ giả định Java 17+, Spring Framework 6.2+, Spring Modulith, Spring Data JPA, JUnit 5 và datasource được cấu hình phù hợp. Điều chỉnh migrations, database drivers, Testcontainers và transaction settings theo phiên bản thực tế. Theo quy trình STEP_4, bài mới được biên soạn, chưa chạy Gradle hoặc vòng Content QA chuyên môn.

