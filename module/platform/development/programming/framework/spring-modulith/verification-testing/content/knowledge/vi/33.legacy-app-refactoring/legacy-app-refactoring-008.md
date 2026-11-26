# Tách test fixture khỏi implementation package

> **Chương:** Refactoring an existing app  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Vấn đề:** Khi refactor ứng dụng Spring legacy thành các application modules, test fixture thường nằm chung `*.internal` với entity/repository/service. Test cross-module tái sử dụng fixture ấy sẽ vô tình tạo một **đường phụ thuộc vào implementation**, khiến việc đổi persistence hoặc siết API module làm hàng loạt test hỏng.  
> **Kết quả mong đợi:** Tổ chức lại fixture theo **mục tiêu kiểm chứng**: fixture hợp đồng dùng public module API; fixture white-box chỉ phục vụ unit test cùng module; fixture database/clock/gateway chuyên biệt nằm trong **test source** với lifecycle và quyền truy cập rõ. Kết hợp `@ApplicationModuleTest`, `PublishedEvents`, integration database và architecture gate để xác nhận thay đổi không làm suy yếu bằng chứng.

## 1. Nhận diện coupling ẩn trong test fixture của ứng dụng legacy

Giả sử source code có module `orders` và `invoicing`. Bài test tạo order bằng helper cũ:

~~~text
src/
├── main/java/com/example/shop/
│   ├── orders/
│   │   ├── OrderCommands.java
│   │   ├── OrderPlaced.java
│   │   └── internal/
│   │       ├── OrderApplicationService.java
│   │       ├── OrderEntity.java
│   │       └── OrderRepository.java
│   └── invoicing/
│       ├── InvoiceQueries.java
│       └── internal/OrderPlacedListener.java
└── test/java/com/example/shop/
    ├── orders/internal/
    │   └── LegacyOrderFixture.java
    └── invoicing/InvoiceFlowIT.java
~~~

Helper cũ dùng implementation trực tiếp:

~~~java
// src/test/java/com/example/shop/orders/internal/LegacyOrderFixture.java
package com.example.shop.orders.internal;

import java.util.UUID;

final class LegacyOrderFixture {

    private final OrderRepository repository;

    LegacyOrderFixture(OrderRepository repository) {
        this.repository = repository;
    }

    UUID insertedOrder(String customerCode) {
        UUID id = UUID.randomUUID();
        repository.save(new OrderEntity(id, customerCode));
        return id;
    }
}
~~~

Vấn đề **không** phải tất cả test trong `orders.internal` đều sai. Một unit test của repository, entity mapping hoặc domain implementation **có lý do** truy cập package-private class. Lỗi xuất hiện khi integration/contract tests của module khác dùng helper đó làm cách **chuẩn** để dựng dữ liệu:

- `invoicing` test phụ thuộc vào `orders.internal.OrderRepository` hoặc một fixture wrapper của repository.
- Dữ liệu được insert trực tiếp, **bỏ qua** validation, domain event và transaction boundary của `OrderCommands.place(...)`.
- Khi refactor JPA entity sang aggregate khác, fixture hỏng dù public contract của orders không đổi.
- Test có thể xanh khi `OrderPlaced` không bao giờ được publish, vì helper đã “tạo order” không đi qua application service.
- Nếu fixture bị đưa vào `src/main/java` chỉ để module khác import, **test convenience** trở thành public production surface.
- Nếu helper giữ entity/ID mutable trong static fields, tests chạy parallel dễ chia sẻ sai trạng thái.

### Chẩn đoán từ một lần thay implementation

~~~text
Đổi OrderEntity / OrderRepository
        |
        +--> Public OrderCommands vẫn giữ nguyên
        |
        +--> LegacyOrderFixture compile fail
        +--> InvoicingFlowIT compile fail
        +--> Event/transaction test không được thực thi
~~~

Đây là **hồi quy do test implementation coupling**, không tự chứng minh sản phẩm hỏng. Ngược lại, nếu sau khi bỏ fixture nội bộ mà một integration test **không còn thấy event**, đó có thể là bằng chứng thực rằng scenario trước đây chưa đi qua public workflow.

### Bảng nhận diện mức phụ thuộc

| Dấu hiệu trong fixture | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Import `orders.internal.OrderEntity` | White-box coupling | Chỉ giữ cho unit test sở hữu module |
| Inject `OrderRepository` để seed integration | Bỏ qua public command/event | Dùng `OrderCommands` cho normal business state |
| Constructor trả entity JPA mutable | Lộ persistence model | Trả business ID/immutable test handle |
| Gắn `@Component` lên helper trong `src/main` | Rò fixture vào production runtime | Chuyển sang `src/test/java`, plain Java |
| Cùng static UUID/code giữa tests | Cross-test collision | Per-test UUID/correlation |
| Helper tự `deleteAll()` sau test | Race với async listener/retry | Fixture isolation và cleanup theo ownership |
| Có outer `@Transactional` ở test | Có thể ngăn `AFTER_COMMIT` | Tách test commit thật khỏi test rollback |
| Fixture mock event publisher khi integration | Che event dispatch | Dùng real Spring events khi test cross-module |

**Tiêu chí:** Nếu bài test muốn chứng minh *người dùng module khác có thể sử dụng API orders*, fixture đó **không nên cần biết** `OrderEntity`, `OrderRepository` hoặc package `orders.internal`.

## 2. Chọn nơi đặt fixture theo loại bằng chứng cần thu

Một đích tổ chức phù hợp với monolith dùng Spring Modulith:

~~~text
src/
├── main/java/com/example/shop/
│   ├── ShopApplication.java
│   ├── orders/
│   │   ├── OrderCommands.java
│   │   ├── OrderQueries.java
│   │   ├── OrderPlaced.java
│   │   └── internal/...                 # Chỉ production implementation
│   └── invoicing/
│       ├── InvoiceQueries.java
│       └── internal/...
└── test/java/
    ├── com/example/shoptest/fixtures/
    │   ├── AcceptedOrderFixture.java  # Plain Java, public API only
    │   └── AcceptedOrderFixtureTest.java
    └── com/example/shop/
        ├── orders/
        │   └── OrderModuleContractTest.java
        ├── orders/internal/
        │   └── OrderEntityMappingTest.java
        │       # White-box unit/slice, có chủ sở hữu
        └── InvoiceFlowIT.java          # Cross-module test
~~~

`com.example.shoptest.fixtures` là **test helper package nằm ngoài** application base package `com.example.shop`; cách đặt này cũng tránh việc bộ quét module nhìn thấy một direct subpackage `testing` trên test classpath và vô tình coi nó là application module. Fixture chỉ là plain Java thuộc `src/test/java`, không phải runtime component; không gắn `@Component` để được scan, hãy tạo bằng `new` trong test. Cần bảo đảm test source set/classpath chứa helper này khi biên dịch các test sử dụng nó.

### Phân loại fixture theo ranh giới

| Loại test | Nơi đặt helper | Được phép phụ thuộc | Không nên phụ thuộc |
| --- | --- | --- | --- |
| Unit test `OrderEntity` | `orders.internal` trong test sources | Domain implementation đang được test | Module khác |
| Repository slice `@DataJpaTest` | `orders.internal` hoặc test support riêng của module | Entity/repository/DB mappings của chính module | Consumer module behavior |
| Producer contract `@ApplicationModuleTest` | `orders` test + `shoptest.fixtures` helpers | `OrderCommands`, `OrderQueries`, `OrderPlaced` | `OrderRepository` để giả đường đi production |
| Cross-module `@SpringBootTest` | Root integration test + `shoptest.fixtures` | Public APIs/event, test-controlled ports | `orders.internal`, `invoicing.internal` |
| DB migration/legacy corrupt-state test | Test DB adapter riêng có phạm vi | SQL/test schema, container | Seed helper làm giả business flow |
| External API failure simulation | Test-specific gateway fake/wiring | Stable outbound port, structured failures | Mở implementation package cho mọi tests |
| Reusable fixtures giữa Gradle subprojects | Dedicated `testFixtures` source set/test-support artifact | Chỉ test APIs được cấp phép | Đóng gói vào production runtime |

**Đừng hiểu “tách fixture khỏi implementation package” là cấm mọi white-box test.** Mục tiêu là **đúng loại test ở đúng ranh giới**. Test repository vẫn có thể đặt trong `orders.internal` để kiểm tra ORM mapping; nhưng consumer integration không nên import helper nội bộ ấy.

### Phân biệt source set và package boundary

- `src/test/java` giữ fixture khỏi main artifact khi build convention đúng, nhưng **không tự ngăn** test khác import class package `internal`.
- Đặt helper ở `shoptest.fixtures` mà vẫn import `orders.internal` chỉ là **đổi tên package**, chưa tách dependency.
- Đưa fixture vào `src/main/java` để chia sẻ dễ hơn là rủi ro lớn: test helper có thể thành API/runtime dependency ngoài ý muốn.
- Với multi-project Gradle, `java-test-fixtures` tạo variant test fixture riêng; Maven có thể dùng test-jar/test-support module. Chỉ áp dụng khi thực sự cần cross-project sharing, kiểm tra dependency scope để production artifacts không kéo fixture vào runtime.
- Spring Modulith kiểm chứng **application modules ở production code**; chính sách test fixture phải có gate riêng nếu muốn chặn test-only phụ thuộc implementation.

## 3. Định nghĩa contract production mà fixture phải đi qua

Để fixture không phụ thuộc JPA, trước hết thiết lập đường **public** mà scenario nghiệp vụ thực sự sử dụng. Ví dụ này minh họa Java 17+, Spring Boot 3.x và Spring Modulith tương thích; các snippets tạo một model nhất quán nhưng vẫn cần dependencies/test DB và migration phù hợp.

**`src/main/java/com/example/shop/ShopApplication.java`**

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@EnableAsync` minh họa hạ tầng async được dùng bởi listener Spring Modulith trong ví dụ; dự án có thể cấu hình executor/async theo convention khác. Không cần đưa `AcceptedOrderFixture` vào component scan của ứng dụng.

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    UUID place(String customerCode);
}
~~~

**`src/main/java/com/example/shop/orders/OrderSnapshot.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderSnapshot(
        UUID orderId,
        String customerCode) {}
~~~

**`src/main/java/com/example/shop/orders/OrderQueries.java`**

~~~java
package com.example.shop.orders;

import java.util.Optional;
import java.util.UUID;

public interface OrderQueries {
    Optional<OrderSnapshot> find(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

Implementation vẫn được giấu bên trong module:

**`src/main/java/com/example/shop/orders/internal/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
class OrderEntity {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String customerCode;

    protected OrderEntity() {}

    OrderEntity(UUID id, String customerCode) {
        this.id = id;
        this.customerCode = customerCode;
    }

    UUID id() {
        return id;
    }

    String customerCode() {
        return customerCode;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.Optional;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.OrderQueries;
import com.example.shop.orders.OrderSnapshot;

@Service
class OrderApplicationService
        implements OrderCommands, OrderQueries {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Override
    @Transactional
    public UUID place(String customerCode) {
        if (customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException(
                    "customerCode is required");
        }

        UUID id = UUID.randomUUID();
        orders.save(new OrderEntity(id, customerCode));

        events.publishEvent(new OrderPlaced(id));
        return id;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<OrderSnapshot> find(UUID id) {
        return orders.findById(id)
                .map(row -> new OrderSnapshot(
                        row.id(), row.customerCode()));
    }
}
~~~

**Đường business thật:** `OrderCommands.place` thực thi validation, persistence, publish event và transaction interceptor. Fixture tốt **không bypass** đường này bằng cách tạo `OrderEntity` và gọi repository trực tiếp.

### Vì sao ID được trả từ command?

`orders.place` tự phát sinh UUID và trả về ID, giúp fixture giữ **correlation ID thật** mà không cần biết entity lifecycle. Nếu API legacy phát sinh ID từ DB sequence hoặc ULID, giữ production behavior; fixture chỉ nhận về public ID, không đòi sửa API để chạm vào `@Id` của entity.

### Phân biệt public API và test API

**Không thêm method `OrderCommands.createTestOrderWithoutValidation(...)` vào production chỉ vì fixture muốn nhanh hơn.** Nếu fixture không thể thiết lập một trạng thái hợp lệ qua public command, cần hỏi trạng thái đó thuộc:

- **Business state hợp lệ:** Nên đi qua public command/use case có thật.
- **Trạng thái lỗi/migration bất thường:** Dùng test-specific DB seam trong bài migration/invariant test, không làm public API mơ hồ.
- **Giả lập external dependency:** Đổi adapter ở test context, không đổi domain entities trực tiếp.
- **Unit edge case của implementation:** Test trong internal package với quyền sở hữu rõ.

### Cách nhận diện fixture đã tách đúng

Một test từ `com.example.shoptest.fixtures` phải compile được chỉ với `com.example.shop.orders.OrderCommands` / `OrderQueries`, không import bất cứ `orders.internal.*` nào. Nếu thay JPA repository sang JDBC adapter mà test contract vẫn dùng API trên, fixture có thể tiếp tục hoạt động **không cần thay source test**.

## 4. Viết fixture reusable dưới test package bằng public module API

**`src/test/java/com/example/shoptest/fixtures/AcceptedOrderFixture.java`**

~~~java
package com.example.shoptest.fixtures;

import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

import com.example.shop.orders.OrderCommands;

public final class AcceptedOrderFixture {

    public record CreatedOrder(
            UUID orderId,
            String customerCode) {}

    private final OrderCommands commands;
    private final Supplier<String> customerCodes;

    public AcceptedOrderFixture(OrderCommands commands) {
        this(commands, () -> "TEST-CUS-" + UUID.randomUUID());
    }

    public AcceptedOrderFixture(
            OrderCommands commands,
            Supplier<String> customerCodes) {
        this.commands = Objects.requireNonNull(commands);
        this.customerCodes = Objects.requireNonNull(customerCodes);
    }

    public CreatedOrder create() {
        return createFor(customerCodes.get());
    }

    public CreatedOrder createFor(String customerCode) {
        if (customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException(
                    "A valid customer code is required");
        }

        UUID id = commands.place(customerCode);

        return new CreatedOrder(
                Objects.requireNonNull(
                        id,
                        "Public order command returned null ID"),
                customerCode);
    }
}
~~~

Fixture không hề import entity, repository hoặc consumer implementation. Nó tạo một **accepted order qua use case thật** và trả **immutable handle** gồm order ID và customer code. UUID làm customer code là data test-specific, giảm khả năng đụng nhau khi chạy song song.

### Vì sao không assert quá nhiều trong fixture?

Không nên để `create()` mặc định chờ invoice, email hoặc external workflow. Khi đó mọi test gọi fixture sẽ phải khởi động consumer và chờ async, tăng thời gian suite và làm mất phạm vi.

~~~java
// Không nên giấu việc chờ T2 trong factory tạo order:
CreatedOrder create() {
    UUID id = orders.place(...);
    await().until(() -> invoicing.invoiceExists(id)); // Sai scope.
    return ...;
}
~~~

**Separation of responsibilities:**

- `AcceptedOrderFixture.create`: thực thi public producer command và trả handle.
- Producer module test: kiểm tra event `OrderPlaced` được publish.
- Consumer integration test: dùng public API của `invoicing` để chờ outcome sau commit.
- Data migration test: có fixture SQL riêng nếu cần kiểm chứng schema state hiếm.

### Unit test fixture tự thân, không cần Spring context

**`src/test/java/com/example/shoptest/fixtures/AcceptedOrderFixtureTest.java`**

~~~java
package com.example.shoptest.fixtures;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.example.shop.orders.OrderCommands;

class AcceptedOrderFixtureTest {

    @Test
    void delegates_to_public_order_command() {
        OrderCommands commands = mock(OrderCommands.class);
        UUID id = UUID.randomUUID();

        when(commands.place("CUS-42")).thenReturn(id);

        var fixture = new AcceptedOrderFixture(
                commands, () -> "CUS-42");

        var created = fixture.create();

        assertThat(created.orderId()).isEqualTo(id);
        assertThat(created.customerCode()).isEqualTo("CUS-42");
        verify(commands).place("CUS-42");
        verifyNoMoreInteractions(commands);
    }

    @Test
    void rejects_invalid_fixture_input_before_command() {
        OrderCommands commands = mock(OrderCommands.class);
        var fixture = new AcceptedOrderFixture(
                commands, () -> "  ");

        assertThatThrownBy(fixture::create)
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(commands);
    }
}
~~~

**Đã chứng minh:** Fixture gọi đúng public command, dữ liệu được truyền qua đúng hợp đồng, không tự viết repository. **Chưa chứng minh:** Transaction đã commit hoặc event listener hoàn tất, vì các mocks chỉ là unit test của helper.

### Determinism và lifecycle

| Nguy cơ | Cách tránh |
| --- | --- |
| Test parallel dùng một customer code | Dùng UUID/unique test run key |
| Fixture static giữ `List<OrderEntity>` | Không giữ mutable global entity |
| Test giả fixed clock làm dữ liệu trùng | Truyền `Clock`/`Supplier` test-scoped khi logic thời gian cần thiết |
| Fixture cleanup tự xóa tất cả orders | Chỉ cleanup data thuộc test, sau khi async consumer đã quiescent |
| Helper tự tạo Spring context/DB container | Để test bootstrap sở hữu lifecycle; helper chỉ gọi API |
| Fixture tự `Thread.sleep` để “đợi email” | Test consumer dùng Awaitility với public business oracle |
| Test muốn order ở trạng thái invalid | Không bypass validation; test adapter/SQL chuyên biệt cho migration |

**Đây là refactor test architecture, không phải yêu cầu làm public JPA entity.** Production code tiếp tục giữ `internal` package; helper chỉ biết stable contract.

## 5. Chuyển producer module test sang fixture theo public contract

**Trước migration**, một test có thể seed `OrderEntity` thẳng qua `OrderRepository` rồi assert entity tồn tại. Điều đó không kiểm tra path `OrderCommands.place(...)` hoặc `OrderPlaced` event. Sau migration, test phải gọi **producer command thật** và chỉ dùng fixture để giảm lặp phần setup.

**`src/test/java/com/example/shop/orders/OrderModuleContractTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import com.example.shoptest.fixtures.AcceptedOrderFixture;

@ApplicationModuleTest
class OrderModuleContractTest {

    @Autowired
    OrderCommands commands;

    @Autowired
    OrderQueries queries;

    @Test
    void creates_order_through_public_api_and_publishes_event(
            PublishedEvents events) {

        var fixture = new AcceptedOrderFixture(
                commands, () -> "CUS-" + UUID.randomUUID());

        var created = fixture.create();

        var stored = queries.find(created.orderId())
                .orElseThrow();

        assertThat(stored.customerCode())
                .isEqualTo(created.customerCode());

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId())
                                .isEqualTo(created.orderId()));
    }

    @Test
    void invalid_input_does_not_publish_event(
            PublishedEvents events) {

        var fixture = new AcceptedOrderFixture(commands);

        assertThatThrownBy(() -> fixture.createFor(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class))
                .isEmpty();
    }
}
~~~

### Vì sao hai assertions khác nhau có giá trị?

- `queries.find(id)`: Order được nhìn thấy qua **public query**, không cần biết `OrderEntity` hay bảng dữ liệu. Khi service `place(...)` được gọi qua Spring proxy, không có outer transaction, đây thường là committed state.
- `events.ofType(OrderPlaced.class)`: Producer publish đúng event ID. Đây là **event contract**, không đồng nghĩa listener consumer đã chạy.
- `invalid_input_does_not_publish_event`: Bảo vệ việc fixture không tạo event cho input bị từ chối. Nhưng vì fixture tự validate rỗng, test hiện tại chứng minh **fixture fail-fast**, không nhất thiết chứng minh validation producer. Nếu mục tiêu kiểm tra *production rule*, nên viết thêm test gọi trực tiếp `commands.place(" ")` để xác minh service không publish. Đừng để helper tự kiểm tra input làm che bug validation trong production.

Ví dụ test bảo vệ **validation thật**:

~~~java
@Test
void production_command_rejects_blank_customer(
        PublishedEvents events) {

    assertThatThrownBy(() -> commands.place(" "))
            .isInstanceOf(IllegalArgumentException.class);

    assertThat(events.ofType(OrderPlaced.class))
            .isEmpty();
}
~~~

### `@ApplicationModuleTest` kiểm tra cái gì?

Spring Modulith module slice có thể bootstrap module `orders` và các dependency cần thiết theo cấu hình. **Không** dùng producer slice để khẳng định listener `invoicing` đã tạo invoice draft; nó có thể không nằm trong module test context. Nếu producer test xanh nhưng consumer integration đỏ, bằng chứng này giúp **khoanh vùng** sang event subscription, transaction T2, DB hoặc read path.

Trong test có outer `@Transactional` (do dự án tự thêm) thì `PublishedEvents` vẫn có thể thấy publication **trước commit**; listener `AFTER_COMMIT` chưa được phép chạy. Bài kiểm chứng consumer ở mục 6 không dùng outer test transaction.

### Không ép mọi contract test trả về entity nội bộ

Phản mẫu:

~~~java
// Phản mẫu trong module test dùng từ fixture:
OrderEntity order = fixture.insertedEntity();

assertThat(order.getPersistenceState()).isEqualTo(...);
~~~

Thay bằng public `OrderSnapshot`/`OrderQueries`. Nếu chính mapping của `OrderEntity` phải được test, dùng một `@DataJpaTest` sở hữu module bên dưới `orders.internal` như mục 7, không làm public DTO chứa persistence internals.

### Tối ưu chi phí test

`AcceptedOrderFixture` là plain Java helper, không tạo Spring context hay Testcontainers cho mỗi `create()`. Nó không chờ email/invoicing. Chỉ test cần producer module bootstrap mới dùng `@ApplicationModuleTest`; test chỉ cần kiểm tra fixture routing dùng Mockito ở mục 4.

## 6. Cross-module integration: fixture độc lập với implementation nhưng outcome vẫn đúng

Giả sử module `invoicing` duy trì một **draft read model** theo `OrderPlaced`. Draft không phải legal invoice đã phát hành; nghiệp vụ cho phép eventual consistency. Consumer chỉ import public `orders.OrderPlaced`.

**`src/main/java/com/example/shop/invoicing/InvoiceState.java`**

~~~java
package com.example.shop.invoicing;

public enum InvoiceState {
    NOT_FOUND,
    DRAFT_READY
}
~~~

**`src/main/java/com/example/shop/invoicing/InvoiceQueries.java`**

~~~java
package com.example.shop.invoicing;

import java.util.UUID;

public interface InvoiceQueries {
    InvoiceState stateOf(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/invoicing/internal/InvoiceDraftWriter.java`**

~~~java
package com.example.shop.invoicing.internal;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class InvoiceDraftWriter {

    private final JdbcTemplate jdbc;

    InvoiceDraftWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void createIfAbsent(UUID orderId) {
        jdbc.update("""
                INSERT INTO invoice_drafts(order_id, state)
                VALUES (?, 'DRAFT_READY')
                ON CONFLICT (order_id) DO NOTHING
                """, orderId);
    }
}
~~~

**`src/main/java/com/example/shop/invoicing/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.invoicing.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    private final InvoiceDraftWriter writer;

    OrderPlacedListener(InvoiceDraftWriter writer) {
        this.writer = writer;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        writer.createIfAbsent(event.orderId());
    }
}
~~~

**`src/main/java/com/example/shop/invoicing/internal/InvoiceQueryService.java`**

~~~java
package com.example.shop.invoicing.internal;

import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.invoicing.InvoiceQueries;
import com.example.shop.invoicing.InvoiceState;

@Service
class InvoiceQueryService implements InvoiceQueries {

    private final JdbcTemplate jdbc;

    InvoiceQueryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public InvoiceState stateOf(UUID id) {
        List<InvoiceState> results = jdbc.query(
                """
                SELECT state FROM invoice_drafts
                WHERE order_id = ?
                """,
                (rs, rowNum) -> InvoiceState.valueOf(
                        rs.getString("state")),
                id);

        return results.isEmpty()
                ? InvoiceState.NOT_FOUND
                : results.get(0);
    }
}
~~~

**Schema PostgreSQL minh họa** (đưa vào một migration phù hợp version của dự án; không tự ghi đè migration legacy):

~~~sql
CREATE TABLE customer_orders (
    id UUID PRIMARY KEY,
    customer_code VARCHAR(120) NOT NULL
);

CREATE TABLE invoice_drafts (
    order_id UUID PRIMARY KEY,
    state VARCHAR(30) NOT NULL
        CHECK (state IN ('DRAFT_READY'))
);
~~~

`ON CONFLICT` cần PostgreSQL hoặc cách upsert tương ứng theo DB. `@ApplicationModuleListener` ở Spring Modulith các version phù hợp thường chạy sau producer T1 commit, async và trong transaction mới; **kết thúc method body chưa chắc T2 commit xong**. `InvoiceQueries.stateOf` là outcome oracle công khai, tách test khỏi repository/entity nội bộ.

### Integration test không biết implementation của cả hai module

**`src/test/java/com/example/shop/InvoiceFlowIT.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import com.example.shop.invoicing.InvoiceQueries;
import com.example.shop.invoicing.InvoiceState;
import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderQueries;
import com.example.shoptest.fixtures.AcceptedOrderFixture;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.jpa.hibernate.ddl-auto=validate")
class InvoiceFlowIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderCommands commands;
    @Autowired OrderQueries orderQueries;
    @Autowired InvoiceQueries invoiceQueries;

    @Test
    void public_order_command_eventually_creates_draft() {
        var fixture = new AcceptedOrderFixture(commands);
        var created = fixture.create();

        // Contract producer: authoritative order committed.
        assertThat(orderQueries.find(created.orderId()))
                .isPresent();

        // Contract consumer: T2 eventually creates visible draft.
        await()
                .alias("invoice draft for " + created.orderId())
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(
                                invoiceQueries.stateOf(
                                        created.orderId()))
                                .isEqualTo(InvoiceState.DRAFT_READY));
    }
}
~~~

**Điểm kiến trúc:** Test không import `orders.internal.*` hay `invoicing.internal.*`. Nếu `OrderRepository` bị thay, hoặc consumer đổi từ JDBC sang JPA, test vẫn tập trung vào công khai **command → event → committed read model**.

### Những tiền điều kiện phải nêu rõ

- Java 17+, JUnit 5, Spring Boot 3.1+ cho `@ServiceConnection`, Spring Modulith/JPA/JDBC/Awaitility/Testcontainers phiên bản tương thích.
- PostgreSQL container cần Docker/container runtime; migration hoặc test schema phải tạo hai bảng như trên. `spring.jpa.hibernate.ddl-auto=validate` yêu cầu schema có sẵn, không tự tạo bảng.
- `InvoiceFlowIT` là integration test của **hai modules**, không tự dùng `@ApplicationModuleTest` mặc định của producer để nhận consumer.
- Không thêm `@Transactional` lên JUnit test method: transaction bao ngoài có thể khiến producer chưa commit, listener `AFTER_COMMIT` chưa chạy.
- Không giữ query snapshot ngoài Awaitility; mỗi poll phải gọi `invoiceQueries.stateOf(...)` mới.
- Spring TestContext cache và class-scoped Testcontainers lifecycle cần phối hợp: đừng reuse cached datasource trỏ tới một container đã stop.
- Không dùng `@AfterEach deleteAll()` lúc listener có thể vẫn đang retry; dùng UUID riêng và test-owned fixture lifecycle.
- `InvoiceState.DRAFT_READY` chỉ là read model draft, không hứa phát hành invoice pháp lý hoàn tất.

### So sánh cách seed cũ và mới

~~~text
CŨ:
InvoicingFlowIT
  -> LegacyOrderFixture
  -> OrderRepository.save(OrderEntity)       [private implementation]
  -> test directly calls InvoicingListener   [bypass event/transaction]

MỚI:
InvoiceFlowIT
  -> AcceptedOrderFixture
  -> OrderCommands.place                     [public API + real T1]
  -> publishes OrderPlaced
  -> @ApplicationModuleListener after commit [real event boundary]
  -> InvoiceQueries.stateOf                  [public committed view]
~~~

Sự thay đổi không chỉ làm code test “sạch” hơn: nó bổ sung **bằng chứng kiến trúc** mà cách seed trực tiếp trước đây đã bỏ qua.

## 7. Đừng biến mọi fixture thành black-box: giữ test nội bộ có mục đích

Đôi khi một scenario thực sự cần entity chưa hoàn chỉnh, row legacy với dữ liệu sai, optimistic locking conflict hoặc DB constraint. Một public command có validation đúng sẽ **không cho tạo** trạng thái bất thường đó. **Không thêm backdoor vào public production API** chỉ để test dễ viết.

### Phân tách rõ hai cấp fixture

**Cấp A — Contract fixture (`com.example.shoptest.fixtures`):**

- Tạo trạng thái **business hợp lệ** qua `OrderCommands.place`.
- Không biết JPA mappings, repository package hoặc SQL table names.
- Dùng trong module test producer và integration tests consumer.

**Cấp B — Implementation fixture (`orders.internal` trong test sources):**

- Chỉ hỗ trợ unit/slice/migration test của **orders**.
- Có thể tạo `OrderEntity`, trigger `@Version` conflict, query native SQL hoặc cố ý seed row legacy invalid.
- Không được import từ `invoicing` hay `shoptest.fixtures` shared helpers.

### Unit test mapping nội bộ là trường hợp hợp lệ

**`src/test/java/com/example/shop/orders/internal/OrderEntityMappingTest.java`**

~~~java
package com.example.shop.orders.internal;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class OrderEntityMappingTest {

    @Autowired OrderRepository repository;

    @Test
    void maps_customer_code_as_expected() {
        UUID id = UUID.randomUUID();

        repository.saveAndFlush(
                new OrderEntity(id, "CUS-INTERNAL"));

        assertThat(repository.findById(id))
                .isPresent()
                .get()
                .extracting(OrderEntity::customerCode)
                .isEqualTo("CUS-INTERNAL");
    }
}
~~~

Ở đây test **cố ý kiểm tra mapping**, nên import repository/entity là hợp lý. Đây không phải fixture chia sẻ để tạo dữ liệu cho test consumer. `@DataJpaTest` có thể dùng embedded database theo default auto-configuration; nếu rủi ro là PostgreSQL constraint/locking, thay bằng Testcontainers production-like database và cấu hình `@AutoConfigureTestDatabase(replace = NONE)` khi cần để không bị thay datasource ngoài ý muốn.

### Khi fixture có việc thiết lập trạng thái qua SQL

Đối với test database migration riêng:

~~~java
// src/test/java/com/example/shop/orders/internal/LegacyOrderRowSeed.java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;

final class LegacyOrderRowSeed {

    private final JdbcTemplate jdbc;

    LegacyOrderRowSeed(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    UUID insertLegacyRow(String historicalCode) {
        UUID id = UUID.randomUUID();

        jdbc.update(
                "INSERT INTO customer_orders(id, customer_code)"
                        + " VALUES (?, ?)",
                id,
                historicalCode);

        return id;
    }
}
~~~

**Không tái sử dụng `LegacyOrderRowSeed` từ `InvoiceFlowIT`**. Lý do tồn tại của nó là thử SQL schema/legacy migration của **orders**, không phải mô phỏng một order đã được chấp nhận và publish event. Với validation constraint, seeding row sai có thể bị DB từ chối; test cần chỉ rõ migration phase và schema state.

### Test doubles và thời gian

Khi integration cần clock cố định, không buộc `OrderEntity` có setter test-only:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FixedTimeConfig {

    @Bean
    @Primary
    Clock fixedTime() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

Đây là **khung @TestConfiguration**; phải có imports `Clock`, `Instant`, `ZoneOffset`, `Bean`, `Primary`, `TestConfiguration` và import config vào đúng test context. Nó chỉ có tác dụng nếu production service/adapter **thực sự inject `Clock`** thay vì gọi `Instant.now()` trực tiếp. Với provider error, dùng fake gateway qua port stable ở **test-owned configuration**. Đừng làm public entity hoặc expose setter nội bộ để tiện fake clock.

### Transaction/cleanup ownership

- Internal JPA test có thể rollback transaction mặc định theo `@DataJpaTest`.
- Cross-module event test cần **T1 commit thật** để kích hoạt `AFTER_COMMIT`; không dùng outer rollback test transaction như một cleanup trick.
- Dữ liệu ở module test và cross-module IT phải được cô lập theo `orderId`/schema và cleanup có chủ đích.
- Fixture không được tự đóng Spring-managed executor, stop container hoặc reset static registry từ `@AfterEach`.

**Bảo vệ đúng hai tầng:** Internal tests kiểm tra implementation đúng; contract/integration tests kiểm tra **module boundary và hành vi liên module**, không mang implementation dependency vào shared fixture.

## 8. Chuyển fixture legacy theo từng lớp, không di chuyển package một cách cơ học

Một cuộc refactor an toàn cần **thay luồng setup của test**, không chỉ đổi `package com.example.shop.orders.internal` thành `package com.example.shoptest.fixtures`. Nếu sau khi đổi package helper vẫn inject `OrderRepository`, dependency implementation vẫn tồn tại và thậm chí có thể khiến đội ngũ làm class nội bộ thành `public` chỉ để tránh compiler error.

### Trình tự migration có thể đảo ngược

~~~mermaid
flowchart TD
    A["Liệt kê các điểm dùng LegacyOrderFixture"] --> B["Phân loại mục đích từng test"]
    B --> C{"Test cần business scenario hợp lệ?"}
    C -- "Có" --> D["Tạo AcceptedOrderFixture từ public OrderCommands"]
    C -- "Không, internal mapping/migration" --> E["Giữ fixture module-private trong test source"]
    D --> F["Đổi test gọi public command + public query"]
    E --> G["Đổi tên fixture thể hiện mục đích hẹp"]
    F --> H["Producer event + cross-module outcome tests"]
    G --> H
    H --> I["ArchUnit chặn reusable fixture import internal"]
    I --> J["Xóa unused legacy helper và import sai"]
~~~

**Đừng bắt đầu bằng sửa visibility từ package-private thành public** cho `OrderEntity`, `OrderRepository` hoặc các constructors chỉ để test package `shoptest.fixtures` compile.

### Bản đồ chuyển đổi helper

| Legacy helper | Hành động | Điều kiện kiểm chứng |
| --- | --- | --- |
| `LegacyOrderFixture.insertOrder()` gọi repository | Thay bằng `AcceptedOrderFixture.create()` qua command | Event được phát, order đọc được qua public query |
| `LegacyOrderFixture.newOrderEntity()` dùng cho JPA unit | Giữ riêng dưới `orders.internal` test | Mapping tests chạy, không export sang consumer |
| `LegacyOrderFixture.withInvalidStatus()` | Chuyển thành `LegacyOrderRowSeed` cho migration/DB test | Không tạo backdoor public command |
| `LegacyOrderFixture.setClock(...)` | Inject `Clock` qua test-only configuration ở test cần thời gian | Production service thật sử dụng injected clock |
| `LegacyOrderFixture.mockGateway(...)` | Dùng test-specific fake port/config | Không làm global mock thay hạ tầng trong integration test khác |
| `LegacyOrderFixture.deleteAll()` | Bỏ auto destructive cleanup, cô lập theo ID | Không xóa dữ liệu khi listener còn retry |
| `LegacyOrderFixture.waitForEverything()` | Chuyển hoàn toàn vào assertion của test outcome | Helper tạo state không tự chờ consumer |

### Chuyển một test theo hướng “strangler” từng bước

**Trước:**

~~~java
// Phản mẫu thuộc test invoicing:
var raw = orderFixture.persistEntity("CUS-42");
invoiceListener.on(new OrderPlaced(raw.id()));
assertThat(invoiceRepository.findByOrderId(raw.id()))
        .isPresent();
~~~

Ở đây test gọi listener trực tiếp và query repository, nên **không chứng minh Spring event wiring/transaction hậu commit**.

**Sau:**

~~~java
var accepted = new AcceptedOrderFixture(commands)
        .createFor("CUS-" + UUID.randomUUID());

await()
        .atMost(Duration.ofSeconds(8))
        .untilAsserted(() ->
                assertThat(invoiceQueries.stateOf(
                        accepted.orderId()))
                        .isEqualTo(InvoiceState.DRAFT_READY));
~~~

Với test trong `InvoiceFlowIT` thực tế, command/queries được `@Autowired` như mục 6. Lưu ý phương thức `createFor(...)` là instance method, nên test nhận một helper mới mỗi method hoặc tạo từ dependency stable; không sử dụng singleton fixture có mutable lifecycle.

### Kiểm soát thay đổi test oracle

Khi bỏ repository seed trực tiếp, một test legacy có thể bắt đầu **thấy nhiều behavior thật hơn**:

- Validation từ `OrderCommands` có thể từ chối dữ liệu trước đây fixture tạo tùy ý.
- Transaction T1 giờ commit thật, nên constraint có thể xuất hiện ở commit.
- `OrderPlaced` giờ được publish, consumer có thể tạo thêm read model.
- Retry và duplicate delivery khiến cleanup cần correlation ID.

Nếu test đỏ sau refactor, đừng tự kết luận fixture mới sai. Phân loại: **state không hợp lệ theo business**, **implementation mapping test bị chuyển nhầm**, **event-handling defect**, **test transaction/context configuration**, hoặc **hạ tầng DB**. Chỉ sửa đúng tầng đã có bằng chứng.

### Chia sẻ fixture giữa modules hay subprojects

Trong một Spring Boot codebase đơn, `src/test/java/com/example/shoptest/fixtures` đủ cho các test cùng source set. Nếu `orders`, `invoicing` được tách thành các Gradle subprojects:

- Sử dụng Gradle `java-test-fixtures` hoặc một dedicated `test-support` artifact **test scope** khi cần.
- Export **public contract fixture** dựa trên DTO/API ổn định, không package-private JPA implementation.
- Kiểm tra build dependency graph để không có `testFixtures` được kéo vào production `implementation/runtimeOnly`.
- Không biến test fixture thành shared domain module mới chỉ vì nhiều test muốn gọi lại một helper.
- Maven test-jar/test-support tương ứng cũng phải kiểm soát scope; không giả định Maven/Gradle tự kiểm tra module ownership.

Đường lối quan trọng: **fixture là consumer của public API**, không phải “bạn thân” có quyền truy cập mọi package của production.

## 9. Kiểm chứng kiến trúc fixture bằng ArchUnit, kết hợp ApplicationModules.verify()

Chỉ gọi `ApplicationModules.verify()` là chưa đủ để chứng minh test fixture được tách. Spring Modulith architecture verification chủ yếu kiểm tra **application module structure trong production sources**; một fixture đặt trong `src/test/java` có thể tiếp tục import internal package mà production architecture gate vẫn xanh.

Cần **hai phép kiểm độc lập**.

### Gate A — Spring Modulith production boundaries

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void checks_production_module_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp kiểm tra vòng phụ thuộc, truy cập ngoài public module API và allowed dependencies theo metadata module được khai báo. Nó **không** chứng minh test sources không có imports tới `orders.internal`.

### Gate B — Test fixture package không phụ thuộc vào implementation modules

**`src/test/java/com/example/shop/ReusableFixtureArchitectureTest.java`**

~~~java
package com.example.shop;

import static com.tngtech.archunit.lang.syntax
        .ArchRuleDefinition.noClasses;

import org.junit.jupiter.api.Test;

import com.tngtech.archunit.core.importer.ClassFileImporter;

class ReusableFixtureArchitectureTest {

    @Test
    void shared_fixtures_do_not_reference_module_internal_packages() {
        var classes = new ClassFileImporter()
                .importPackages("com.example.shop", "com.example.shoptest");

        noClasses()
                .that()
                .resideInAPackage("com.example.shoptest.fixtures..")
                .should()
                .dependOnClassesThat()
                .resideInAnyPackage(
                        "com.example.shop.orders.internal..",
                        "com.example.shop.invoicing.internal..")
                .check(classes);
    }
}
~~~

ArchUnit được khai báo ở **test dependencies**. Import từ `com.example.shop` trong test runtime giúp rule phân tích cả classes của fixtures; nếu test runner/build profile không đưa test classes lên classpath, cần điều chỉnh import đến đúng test output. Đây là **quy tắc tĩnh**, không phát hiện reflection theo string, direct SQL tạo dữ liệu sai hoặc một fixture gọi public API nhưng mock event publisher ở integration.

### Vì sao không chặn toàn bộ tests import internal?

Một rule quá rộng:

~~~text
no test class may import *.internal.*
~~~

sẽ loại bỏ `OrderEntityMappingTest` có mục đích hợp lệ. Do đó rule trên chỉ kiểm tra **reusable shared fixture package**. Có thể mở rộng gate để bảo vệ `invoicing` integration tests không import `orders.internal`, nhưng scope rule phải phân biệt **unit tests sở hữu module** với **contract tests sử dụng module**.

### Ví dụ rule bổ sung cho cross-module test package

Nếu team đặt tất cả integration tests bên dưới `com.example.shop.it`, có thể thêm:

~~~java
noClasses()
        .that()
        .resideInAPackage("com.example.shop.it..")
        .should()
        .dependOnClassesThat()
        .resideInAnyPackage(
                "com.example.shop.orders.internal..",
                "com.example.shop.invoicing.internal..")
        .check(classes);
~~~

Chỉ dùng snippet này khi `com.example.shop.it` **thật sự tồn tại** và chứa các contract/integration tests; tránh tuyên bố một test package convention chưa thiết lập.

### Mutations để biết gate có sức chặn

| Đột biến trong nhánh thực hành | Gate phải đỏ | Vì sao |
| --- | --- | --- |
| Fixture `AcceptedOrderFixture` import `OrderRepository` | Fixture ArchUnit | Phụ thuộc implementation trở lại |
| Fixture trả `OrderEntity` ra ngoài | Fixture ArchUnit | Rò persistence model |
| Consumer `invoicing` import `orders.internal` | `ApplicationModules.verify()` hoặc rule bổ sung | Vi phạm ranh giới module production |
| Xóa `events.publishEvent` khỏi service | Producer `PublishedEvents` | Fixture vẫn tạo order nhưng business event thiếu |
| Bỏ `@ApplicationModuleListener` | Cross-module integration | Producer test có thể vẫn xanh |
| Consumer T2 rollback | Public outcome integration | Listener body return không đủ |
| Test `InvoiceFlowIT` chuyển seed về repository | Fixture test/CI review, thêm rule IT nếu áp dụng | Bỏ qua public flow |
| Trùng UUID/fixture static state giữa tests | Parallel/isolation tests | Rò dữ liệu test |

### CI quality gate theo tầng

~~~mermaid
flowchart LR
    PR["Pull request"] --> F["Fixture unit tests"]
    F --> M["ApplicationModules.verify()"]
    M --> A["Fixture ArchUnit"]
    A --> PUB["Producer @ApplicationModuleTest"]
    PUB --> S["Module-local JPA slice"]
    S --> IT["Cross-module PostgreSQL IT"]
    IT --> G{"Bằng chứng bắt buộc đạt?"}
    G -- "Có" --> OK["Merge/release policy"]
    G -- "Không" --> FIX["Sửa boundary hoặc behavior"]
~~~

**Kết luận về hai gate:** `ApplicationModules.verify()` xác nhận production API/dependencies; ArchUnit xác nhận test helpers shared **không lén nhập internal dependencies**; integration xác nhận module giao tiếp đúng khi đi qua public API. Không gate nào thay hoàn toàn gate khác.

## 10. Bài thực hành, checklist và tiêu chí hoàn tất refactor

### Các bài thực hành theo bằng chứng

**Bài A — Phân loại fixture legacy.** Cho danh sách helper: `insertOrderEntity()`, `acceptedOrder()`, `seedInvalidLegacyRow()`, `mockExternalInvoiceService()`, `waitUntilInvoiced()`. Quyết định helper nào thuộc public contract fixture, implementation test fixture, test configuration hoặc assertion của consumer. Giải thích vì sao không gom tất cả vào `BaseIntegrationTest`.

**Bài B — Tách một fixture đang chọc vào repository.** Chuyển từ `LegacyOrderFixture.insertedOrder` gọi `OrderRepository` sang `AcceptedOrderFixture.create()` gọi `OrderCommands.place`. Bảo đảm public record `CreatedOrder` không chứa JPA entity.

**Bài C — Fixture unit test.** Mock `OrderCommands`, assert fixture truyền đúng customerCode, trả đúng ID và không gọi command khi input invalid. Không bootstrap Spring chỉ để test một helper.

**Bài D — Producer module contract.** Chạy `OrderModuleContractTest` với `PublishedEvents`, assert event có `orderId` vừa tạo. Tạm bỏ `publishEvent`: test phải đỏ dù `OrderQueries.find` còn thấy order.

**Bài E — Consumer integration.** Trên PostgreSQL Testcontainers, tạo order qua fixture public, chờ `InvoiceState.DRAFT_READY` bằng Awaitility, không import repository nội bộ. Tạm bỏ listener: producer module test có thể xanh nhưng consumer test phải đỏ.

**Bài F — White-box mapping hợp lệ.** Viết `@DataJpaTest` trong `orders.internal` kiểm tra mapping/constraint của `OrderEntity`. Không xuất fixture đó sang `com.example.shoptest.fixtures`.

**Bài G — Legacy migration state.** Dùng `LegacyOrderRowSeed` trong test migration sở hữu module để seed row mà public command không cho phép. Nêu rõ SQL/schema test-only và không dùng helper này làm chuẩn tạo order cho consumer.

**Bài H — Fake thời gian và external API.** Inject `Clock` hoặc fake gateway bằng `@TestConfiguration` chỉ trong test cần nó. Kiểm tra production service thực sự nhận injected bean; không thêm setter `setNowForTest` vào JPA entity.

**Bài I — Architecture negative controls.** Cho `AcceptedOrderFixture` import `orders.internal.OrderEntity`: `ReusableFixtureArchitectureTest` phải đỏ. Khôi phục API. Tạo dependency từ production consumer tới `orders.internal`: `ApplicationModules.verify()` phải đỏ theo rules mặc định, trừ khi đã cố ý expose named interface phù hợp và được policy cho phép.

**Bài J — Cleanup/parallel.** Chạy integration tests song song với UUID riêng. Không để một test xóa bảng khi callback của test khác vẫn đang retry. Ghi nhận transaction T1/T2 và điều kiện completion trước cleanup.

### Câu hỏi tự đánh giá

1. Vì sao chuyển file fixture sang package `shoptest.fixtures` nhưng vẫn import `orders.internal` chưa thực sự tách dependency?
2. Khi nào fixture được phép truy cập JPA entity/repository nội bộ?
3. Vì sao test consumer seed order qua repository có thể bỏ sót `OrderPlaced`?
4. Vì sao không nên làm `OrderEntity` public chỉ để fixture compile?
5. `AcceptedOrderFixture` được phép chờ consumer async không? Khi nào?
6. `PublishedEvents` chứng minh gì và chưa chứng minh gì?
7. Cross-module test cần public oracle nào để xác nhận consumer T2 đã commit?
8. Vì sao `@Transactional` trên JUnit integration test có thể gây timeout?
9. Khi nào dùng `@DataJpaTest` thay vì `@ApplicationModuleTest`?
10. Vì sao giữ một helper SQL migration riêng không mâu thuẫn với public fixture?
11. Spring Modulith `ApplicationModules.verify()` có tự kiểm soát test-source imports không?
12. ArchUnit rule nào chỉ nhắm vào **shared fixtures** mà không cấm internal unit tests?
13. Tại sao fixture không tự stop Spring executor hoặc Testcontainers?
14. Đưa `testFixtures` artifact vào production runtime có vấn đề gì?
15. Nếu fixture đổi nhưng public test đỏ, cần điều tra producer validation/event, consumer wiring hay fixture sai trước?

### Checklist trước khi chấp nhận PR

- [ ] Đã liệt kê các fixture cũ và chủ sở hữu thực sự của chúng.
- [ ] Phân biệt fixture **business scenario hợp lệ** và fixture **white-box implementation**.
- [ ] Shared fixture nằm trong `src/test/java`/test-support scope, không vào runtime production.
- [ ] Shared fixture không import `orders.internal`/`invoicing.internal` hoặc các entity/repository nội bộ.
- [ ] Fixture dùng public `OrderCommands` và trả immutable `CreatedOrder`/business ID.
- [ ] Fixture không làm public constructor/entity hay thêm business backdoor chỉ cho test.
- [ ] Fixture không tự tạo Spring context, DataSource hoặc Testcontainers.
- [ ] Fixture không giấu Awaitility/Thread.sleep để chờ consumer ngoài scope.
- [ ] Customer/test identifiers unique theo test; không chia sẻ static mutable state.
- [ ] Test dữ liệu invalid/migration dùng seam nội bộ có phạm vi, không lan sang consumer.
- [ ] Producer module test `@ApplicationModuleTest` + `PublishedEvents` kiểm tra event ID/payload.
- [ ] Producer validation được kiểm tra **trực tiếp**, không chỉ qua validation của fixture.
- [ ] Cross-module integration chạy through real Spring event wiring và commit T1/T2.
- [ ] Consumer outcome được đọc qua public `InvoiceQueries`, không qua private repository.
- [ ] PostgreSQL/Testcontainers khi isolation/upsert/constraint là một phần mệnh đề.
- [ ] Không có outer test transaction vô tình ngăn `AFTER_COMMIT`.
- [ ] Không dùng cached snapshot/fixed sleep thay fresh Awaitility query.
- [ ] Test-owned fixture cleanup không đụng dữ liệu khi async worker còn chạy.
- [ ] Test clock/fake gateway được inject ở đúng test context, không rò giữa suites.
- [ ] `ApplicationModules.verify()` vẫn bảo vệ production module boundaries.
- [ ] ArchUnit kiểm tra shared fixture package không phụ thuộc implementation.
- [ ] Không cấm white-box test chính đáng trong `orders.internal`.
- [ ] CI giữ unit fixture, producer module, JPA slice và cross-module integration tests.
- [ ] Mutation tests chứng minh mỗi gate bắt đúng loại lỗi.
- [ ] Sau thay repository/JPA adapter, fixture contract không cần sửa chỉ vì đổi implementation.
- [ ] Báo cáo migration cho thấy giảm coupling thực tế, không chỉ đổi tên package.

**Ghi nhớ:** “Tách test fixture khỏi implementation package” nghĩa là thay **phụ thuộc của test** từ implementation details sang **public module contract**, không chỉ chuyển file sang thư mục mới. Shared fixture chỉ tạo business state qua `OrderCommands` và trả business handle; internal unit/slice tests vẫn có quyền sở hữu repository/entity khi mệnh đề thật sự cần. Kết hợp `@ApplicationModuleTest` + `PublishedEvents`, integration outcome qua `InvoiceQueries`, `ApplicationModules.verify()` và ArchUnit để đảm bảo việc refactor legacy app **giảm coupling mà không làm mất bằng chứng về event, transaction và boundary**.



