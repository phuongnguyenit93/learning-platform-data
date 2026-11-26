# Spy bean và nguy cơ chạy logic thật ngoài ý muốn

## 1. Spy không phải một mock “thông minh hơn”

Trong Mockito, **mock** và **spy** đều cho phép kiểm tra lời gọi bằng `verify(...)`, nhưng hành vi mặc định khác nhau:

- **Mock** thường không chạy implementation thật của method; nếu chưa stub, nó trả giá trị mặc định theo return type.
- **Spy** bao quanh một đối tượng thật và **thường gọi method thật** khi chưa được stub. Điều này áp dụng cả khi method ghi database, gửi HTTP, gửi email hoặc ném exception.

Trong Spring Framework, `@MockitoBean` dùng bean override kiểu **REPLACE_OR_CREATE**, còn `@MockitoSpyBean` dùng **WRAP**: Spring lấy instance thật của bean rồi tạo Mockito spy. Spy vì thế **không phải công cụ để loại bỏ side effect**. Đặc biệt, một kiểu stubbing rất quen thuộc:

~~~java
when(auditService.record(orderId)).thenReturn("STUBBED");
~~~

có thể gọi **`auditService.record(orderId)` thật ngay lúc thiết lập stub**. Nếu method đó ghi bảng audit, row có thể xuất hiện **trước khi gọi system under test (SUT)**. Nếu method gọi payment provider, HTTP request có thể đã được gửi ngay trong bước Given của test.

Ngược lại:

~~~java
doReturn("STUBBED").when(auditService).record(orderId);
~~~

trong tình huống spy thông thường sẽ tránh gọi real method tại **thời điểm cấu hình stubbing**. Nhưng thao tác ấy còn một rủi ro khác: nó làm cho method thật **không chạy khi SUT gọi sau này**, có thể khiến test bỏ sót một side effect đáng ra phải được kiểm chứng.

> **Nguyên tắc trung tâm:** Chỉ spy khi bạn **cố ý muốn chạy logic thật** và cần quan sát hoặc thay thế có kiểm soát một phần của nó. Nếu mục tiêu là cô lập hệ thống ngoài, hãy mock đúng **module/API/I/O boundary**; nếu mục tiêu là kiểm chứng nghiệp vụ của module, hãy giữ implementation thật và assert kết quả.

Bài thuộc chương **Mock và spy** trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, nơi chúng ta kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, thực hành `@ApplicationModuleTest`, kiểm thử event/database/integration và thiết kế quality gate CI chống phụ thuộc sai và hồi quy. Nội dung đặc biệt quan trọng vì một spy trong module test có thể khiến test **thực hiện công việc ngoài mong đợi** dù người viết nghĩ rằng đã “giả lập” mọi dependency.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích sự khác biệt giữa `@Mock`, `@Spy`, `@MockitoBean` và `@MockitoSpyBean`.
2. Xác định **khi nào logic thật chạy**: lúc tạo bean, cấu hình `when`, gọi SUT, callback bất đồng bộ hoặc AOP advice.
3. Nhận biết tác hại của `when(spy.method()).thenReturn(...)` đối với database, network, cache và transaction.
4. Dùng `doReturn`, `doThrow`, `doAnswer` có cân nhắc và hiểu giới hạn khi Spring AOP proxy bao quanh spy.
5. Chọn `@MockitoBean` cho public collaborator ngoài module, thay vì `@MockitoSpyBean` trên bean không được bootstrap trong `STANDALONE`.
6. Viết module test giữ repository/event publisher thật, quan sát side effect của spy và phân biệt nó với state assertions.
7. Kiểm thử lỗi, retry, async listener, idempotency và test isolation mà không đưa ra kết luận quá mức từ `verify(spy)`.
8. Kết hợp `ApplicationModules.verify()`, provider contract, integration và CI quality gates.

## 2. Mock, spy, bean override: so sánh theo hành vi thật

| Công cụ | Bean trong Spring context? | Method thật có chạy không? | Phù hợp với |
| --- | --- | --- | --- |
| `Mockito.mock(Foo.class)` hoặc `@Mock` | Không tự đăng ký Spring bean. | Không, trừ khi cấu hình `CALLS_REAL_METHODS` hoặc một Answer đặc biệt. | Unit test không khởi tạo Spring. |
| `Mockito.spy(realObject)` hoặc `@Spy` | Không tự thay bean trong context. | **Có** khi chưa stub. | Unit test cần quan sát object thật. |
| `@MockitoBean Foo foo` | Có; Spring Test thay hoặc tạo bean. | Thông thường không. | Module test cô lập public API/I/O boundary. |
| `@MockitoSpyBean Foo foo` | Có; Spring Test wrap **bean đã tồn tại**. | **Có**, mặc định. | Integration test muốn quan sát một bean thật. |
| `@MockBean` / `@SpyBean` của Spring Boot cũ | Có, theo cơ chế Boot test. | Tương ứng mock/spy. | Dự án chưa chuyển sang Framework annotations. |

**Không đồng nhất spy với fake.** Fake là một implementation đơn giản có hành vi thực thi riêng do test kiểm soát (ví dụ repository in-memory). Spy lại có **code production thật** bên trong, nên các side effect của production có thể xảy ra.

### 2.1. Lựa chọn theo mục tiêu kiểm thử

| Mục tiêu | Nên bắt đầu với | Vì sao? |
| --- | --- | --- |
| `orders` gọi public API `customers` và test chỉ cần giá trị true/false. | `@MockitoBean CustomerEligibility`. | Cô lập module ngoài, không chạy database của `customers`. |
| Test kiểm tra `OrderAuditService` **thật sự ghi database**. | Bean thật, không mock. | Query database là bằng chứng đáng tin hơn chỉ `verify(record)`. |
| Test cần quan sát một callback thật mà vẫn để method chạy. | `@MockitoSpyBean`, có điều kiện. | Verify lời gọi nhưng phải chấp nhận real behavior. |
| Test cần ngăn gửi email/thanh toán ra môi trường thật. | Fake/mock **gateway port** hoặc test server. | Spy lên gateway thật có thể gửi request ngoài ý muốn. |
| Test logic thuần `DiscountPolicy`. | Tạo object thật, assert output. | Không cần Spring/Mockito/spy. |
| Test giao tiếp HTTP, serialization và retry thực. | Integration test với mock HTTP server/Testcontainers. | Mockito spy không kiểm chứng wire contract. |

## 3. Bốn thời điểm spy có thể tạo side effect

~~~mermaid
flowchart TD
    A["Spring tạo bean thật"] --> B["Constructor / @PostConstruct / init"]
    B --> C["@MockitoSpyBean tạo spy (WRAP)"]
    C --> D["Test cấu hình stubbing"]
    D --> E["SUT gọi method"]
    E --> F["Listener / retry / async callback"]
    B -. "Có thể gọi DB/HTTP" .-> X["SIDE EFFECT"]
    D -. "when(spy.method()) gọi thật" .-> X
    E -. "Không stub => gọi thật" .-> X
    F -. "Có thể chạy sau assertion" .-> X
~~~

Điều cần nhớ:

1. **Khởi tạo bean:** constructor, `@PostConstruct`, `InitializingBean`, startup listener hoặc factory logic có thể chạy trước khi test method bắt đầu. Spy không chặn được việc bean thật cần được tạo.
2. **Thiết lập stub:** `when(spy.realMethod())` thường thực thi real method ngay khi đánh giá biểu thức.
3. **Lời gọi từ SUT:** nếu không stub method đó, spy thực thi code thật và các dependency của nó.
4. **Callback khác:** event listener, scheduled task, retry hoặc executor có thể tiếp tục gọi spy ngoài thời điểm mà test đang quan sát.

Khi có Spring AOP (`@Transactional`, `@Cacheable`, `@Retryable`), còn phải phân biệt **proxy**, **spy target** và real method. Một số advice có thể chạy hoặc cache dữ liệu ngay cả khi Mockito đã chặn thực thi real method.

## 4. @ApplicationModuleTest quyết định bean nào tồn tại

Spring Modulith cho phép:

| Bootstrap mode | Phạm vi nạp | Hệ quả với spy |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Chỉ module chứa lớp test. | Spy được bean **trong module**; implementation ngoài module thường không tồn tại để spy. |
| `DIRECT_DEPENDENCIES` | Module hiện tại và những dependency trực tiếp. | Có thể spy bean thật của module phụ thuộc, đồng thời kích hoạt các dependency/side effect của nó. |
| `ALL_DEPENDENCIES` | Module hiện tại và toàn cây phụ thuộc. | Càng nhiều bean thật được tạo; chi phí và nguy cơ side effect tăng. |

Với `@MockitoBean`, Spring Test thường có thể **tạo** mock khi bean chưa có (chiến lược `REPLACE_OR_CREATE`). Với `@MockitoSpyBean`, Spring Test cần **đúng một bean hiện hữu** để wrap (`WRAP`). Spy không biến một interface trống thành implementation mới.

~~~java
@ApplicationModuleTest
class OrdersIsolatedTests {

    // Public API của module khác: có thể tạo bean giả.
    @MockitoBean CustomerEligibility customers;

    // Bean thật nằm trong orders: có thể wrap bằng spy.
    @MockitoSpyBean OrderAuditService audits;
}
~~~

Ngược lại, nếu cả `CustomerEligibility` implementation đều thuộc module `customers` bị loại khỏi `STANDALONE`:

~~~java
@ApplicationModuleTest
class IncorrectSpyOnMissingBean {

    @MockitoSpyBean CustomerEligibility customers;
    // Context có thể không khởi động: không có real bean để wrap.
}
~~~

**Không khắc phục bằng cách chuyển mọi test sang `ALL_DEPENDENCIES`.** Nếu test chỉ cần public collaborator trả một kết quả định sẵn, `@MockitoBean` là ranh giới hợp lý hơn và tránh khởi tạo một cây implementation có database, HTTP hoặc scheduled tasks.

## 5. Ví dụ xuyên suốt: orders, customers và audit nội bộ

Giả sử ứng dụng Spring Modulith có root package `com.example.shop`:

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
        ├── OrderRepository.java
        ├── OrderAuditEntry.java
        ├── OrderAuditRepository.java
        └── OrderAuditService.java
~~~

Use case `orders.place(orderId, customerId)`:

1. Hỏi public API của `customers` xem khách hàng có được đặt hàng không.
2. Nếu bị từ chối, ném lỗi nghiệp vụ.
3. Nếu được phép, lưu `OrderEntity`.
4. Ghi một audit entry trong database **qua `OrderAuditService` thuộc chính module `orders`**.
5. Phát `OrderPlaced` qua Spring `ApplicationEventPublisher`.

Hai collaborator cần đối xử khác nhau:

~~~mermaid
flowchart LR
    T["@ApplicationModuleTest(orders)"] --> S["OrderService (real)"]
    S --> C["CustomerEligibility (mock)"]
    S --> A["OrderAuditService (real hoặc spy)"]
    S --> R["OrderRepository (real)"]
    S --> E["ApplicationEventPublisher (real)"]
    A --> AR["OrderAuditRepository (real)"]
    R --> DB[("DB test")]
    AR --> DB
    E --> P["PublishedEvents"]
~~~

**`CustomerEligibility` là boundary được mock. `OrderAuditService` là logic nội bộ; nếu spy nó, bạn vẫn đang chạy code có thể ghi database.**

### 5.1. Công bố đúng API của customers

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

Implementation `CustomerEligibilityService` ở `customers.internal` là chi tiết của module ngoài. Module `orders` không được import repository nội bộ `customers.internal.CustomerRepository` để test có thêm thứ “dễ spy”.

## 6. Các entity và repository dùng để nhìn thấy side effect thật

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.Objects;
import java.util.UUID;

@Entity
public class OrderEntity {

    @Id
    private UUID id;
    private UUID customerId;

    protected OrderEntity() {}

    public OrderEntity(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public UUID getCustomerId() { return customerId; }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

Audit entry dùng **`orderId` làm khóa chính** nhằm minh họa quan hệ một order ↔ một audit entry. Đây không phải mô hình audit lịch sử đầy đủ cho production; một hệ thống nhiều audit actions thường cần `auditId` riêng và constraint tương ứng.

File `orders/internal/OrderAuditEntry.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Entity
public class OrderAuditEntry {

    @Id
    private UUID orderId;
    private Instant recordedAt;

    protected OrderAuditEntry() {}

    public OrderAuditEntry(UUID orderId, Instant recordedAt) {
        this.orderId = Objects.requireNonNull(orderId);
        this.recordedAt = Objects.requireNonNull(recordedAt);
    }
}
~~~

File `orders/internal/OrderAuditRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface OrderAuditRepository
        extends JpaRepository<OrderAuditEntry, UUID> {}
~~~

### 6.1. Real bean có side effect ngay trong method

File `orders/internal/OrderAuditService.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.stereotype.Service;
import java.time.Instant;
import java.util.UUID;

@Service
public class OrderAuditService {

    private final OrderAuditRepository entries;

    public OrderAuditService(OrderAuditRepository entries) {
        this.entries = entries;
    }

    public String record(UUID orderId) {
        // Real side effect: JPA thật, không phải stub.
        entries.saveAndFlush(
                new OrderAuditEntry(orderId, Instant.now()));
        return "RECORDED";
    }
}
~~~

`saveAndFlush` trong Spring Data JPA làm thao tác ghi/flush theo transaction của repository hoặc transaction bên ngoài. Nếu method được gọi trước SUT trong một test không có transaction bao ngoài, row có thể được commit **ngay khi bạn mới cấu hình Mockito**.

Lớp này được thiết kế đơn giản để quan sát rủi ro. Trong code production, audit có thể được xử lý qua outbox/transactional event tùy yêu cầu bất biến, nhưng bài học tập trung vào **thời điểm thực thi thật của spy**.

### 6.2. Event và service nguồn

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
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

public class OrderRejectedException extends RuntimeException {
    public OrderRejectedException() {
        super("Customer is not eligible");
    }
}
~~~

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderAuditService;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final CustomerEligibility customers;
    private final OrderRepository orders;
    private final OrderAuditService audits;
    private final ApplicationEventPublisher events;

    public OrderService(CustomerEligibility customers,
                        OrderRepository orders,
                        OrderAuditService audits,
                        ApplicationEventPublisher events) {
        this.customers = customers;
        this.orders = orders;
        this.audits = audits;
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId, UUID customerId) {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);

        if (!customers.canPlaceOrder(customerId)) {
            throw new OrderRejectedException();
        }

        orders.save(new OrderEntity(orderId, customerId));
        audits.record(orderId);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId,
                customerId, Instant.now()));
    }
}
~~~

`OrderService` là **system under test**. Module test cần để nó chạy thật; `CustomerEligibility` được mock ở module boundary, còn `OrderAuditService` là một bean thật có thể chọn spy **chỉ khi cần quan sát**.

## 7. Spy an toàn về ý định: quan sát real behavior, không stub

Kịch bản đầu tiên cố ý dùng `@MockitoSpyBean` để verify invocation nhưng vẫn **cho phép method thật ghi audit**. Đây là trường hợp spy có ý nghĩa nếu lời gọi `record` là một yêu cầu cần quan sát.

File test `orders/OrderAuditSpyBehaviorTests.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderAuditRepository;
import com.example.shop.orders.internal.OrderAuditService;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderAuditSpyBehaviorTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;
    @Autowired OrderAuditRepository auditEntries;

    @MockitoBean CustomerEligibility customers;
    @MockitoSpyBean OrderAuditService audits;

    @Test
    void realAuditRunsWhenServiceCallsSpy(
            PublishedEvents publishedEvents) {

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        when(customers.canPlaceOrder(customerId))
                .thenReturn(true);

        service.place(orderId, customerId);

        // Interaction trên spy: SUT đã gọi audit.
        verify(audits).record(orderId);

        // State thật: real record() đã GHI DATABASE.
        assertThat(orders.existsById(orderId)).isTrue();
        assertThat(auditEntries.existsById(orderId)).isTrue();

        // Publisher thật: event xuất hiện ở tầng ứng dụng.
        assertThat(publishedEvents.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event ->
                        assertThat(event.customerId())
                                .isEqualTo(customerId));
    }
}
~~~

Ở đây `verify(audits).record(orderId)` **không phải thao tác làm phát sinh row**. Row được ghi vì `service.place` đã gọi real method qua spy. Assertion database mới xác nhận kết quả ghi.

Điều kiện chạy: cần Spring Data JPA, datasource và schema cho hai entities, transaction manager, starter test và module test dependency phù hợp. Không thêm `@Transactional` bao ngoài nếu muốn các lời gọi service commit riêng và kiểm tra state sau commit.

### 7.1. Có thật sự cần spy không?

Nếu mục tiêu chỉ là:

> “Order hợp lệ phải có một row audit được lưu trong database.”

thì có thể **không khai báo `@MockitoSpyBean`** mà vẫn assert `auditEntries.existsById(orderId)`. Test trở nên ít phụ thuộc method `record`: sau này team đổi sang method `append`, một event handler cùng module hoặc JPA auditing, miễn hợp đồng cuối giữ nguyên, state test vẫn đúng.

Spy hợp lý hơn khi **lời gọi vào bean cụ thể** là một phần hợp đồng cần kiểm chứng, không phải khi chỉ muốn nhìn thấy mọi bước triển khai.

## 8. Nguy hiểm: when(spy.method()) có thể ghi database trong bước Given

Xem một test **minh họa hành vi nguy hiểm**, không phải mẫu stubbing được khuyến nghị:

~~~java
@Test
void whenStubbingExecutesRealMethodDuringSetup() {
    UUID orderId = UUID.randomUUID();

    assertThat(auditEntries.existsById(orderId)).isFalse();

    // NGUY HIỂM: Java phải đánh giá audits.record(orderId)
    // trước khi Mockito nhận được lời gọi when(...).
    when(audits.record(orderId))
            .thenReturn("STUBBED");

    // Chưa gọi OrderService.place(...) mà row đã xuất hiện!
    assertThat(auditEntries.existsById(orderId)).isTrue();

    // Lời gọi sau này trả kết quả giả, không ghi thêm lần nữa.
    assertThat(audits.record(orderId)).isEqualTo("STUBBED");
}
~~~

Đoạn này đặt trong lớp test ở mục 7. Nó **chủ đích cho thấy một thao tác không nên làm trong test thông thường**. Vì `OrderAuditService.record` ghi database thật và không bị stub trước đó, lần gọi khi thiết lập `when` đã chạm repository.

Hậu quả ở hệ thống thực có thể nghiêm trọng hơn một row test:

- Một HTTP request gửi ra provider trong giai đoạn test setup.
- Email được gửi cho người thật nếu môi trường test cấu hình sai.
- Transaction hoặc lock được mở bất ngờ.
- Cache bị cập nhật trước khi SUT xử lý.
- Exception xuất hiện ở dòng `when(...)`, khiến developer tưởng lỗi do Mockito.
- Audit/event từ một test rò sang test khác nếu fixture không được cô lập.

### 8.1. Vì sao when() làm method thật chạy?

Trong Java, đối số của lời gọi được đánh giá trước khi method bên ngoài được gọi:

~~~java
when( spy.realMethod(argument) ).thenReturn(value);
~~~

Vì `spy.realMethod(argument)` là **biểu thức đối số**, Mockito spy có thể thực thi code thật để lấy giá trị truyền vào `when`. Mockito sau đó mới ghi nhận stubbing. Đây là khác biệt cốt lõi với mock thông thường, nơi lời gọi chưa stub không chạy implementation thật.

Một test có `@BeforeEach` hoặc setup dùng chung:

~~~java
@BeforeEach
void stubAudit() {
    when(audits.record(fixedOrderId)).thenReturn("OK");
}
~~~

có thể vô tình ghi row **trước mọi test method**, hoặc đụng unique constraint ở lần chạy tiếp. Tránh setup chung kiểu này đối với spy có side effect.

## 9. doReturn tránh real call lúc stubbing, nhưng cũng có cái giá

Với spy thông thường **không bị AOP advice can thiệp**, cách sau không gọi `record` thật lúc cấu hình:

~~~java
doReturn("STUBBED")
        .when(audits)
        .record(orderId);
~~~

Ví dụ kiểm chứng khác biệt:

~~~java
@Test
void doReturnDoesNotRecordAuditDuringSetup() {
    UUID orderId = UUID.randomUUID();

    assertThat(auditEntries.existsById(orderId)).isFalse();

    doReturn("STUBBED").when(audits).record(orderId);

    assertThat(auditEntries.existsById(orderId)).isFalse();
    assertThat(audits.record(orderId)).isEqualTo("STUBBED");

    // Real record() không chạy ở cả bước setup và lời gọi đã stub.
    assertThat(auditEntries.existsById(orderId)).isFalse();
}
~~~

Cần static import:

~~~java
import static org.mockito.Mockito.doReturn;
~~~

Đây không phải test “audit service đúng”. Nó chỉ chứng minh **cách stubbing làm mất side effect thật**. Nếu bạn viết test `OrderService` rồi dùng `doReturn` để chặn `audits.record`, test có thể thấy order và `OrderPlaced` nhưng **không có audit entry**. Nếu audit entry là bất biến nghiệp vụ, test đó đã trở nên quá dễ dãi.

### 9.1. Test có chủ đích mô phỏng lỗi audit

`doThrow` cũng có thể stub method trả giá trị trên spy mà không thực thi real method tại thời điểm cấu hình:

~~~java
@Test
void auditFailureRollsBackOrder(PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.canPlaceOrder(customerId))
            .thenReturn(true);

    doThrow(new IllegalStateException("Audit storage unavailable"))
            .when(audits).record(orderId);

    assertThatThrownBy(() ->
            service.place(orderId, customerId))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Audit storage unavailable");

    // OrderService có @Transactional, exception xảy ra trước
    // publishEvent nên không ghi order hay phát event.
    assertThat(orders.existsById(orderId)).isFalse();
    assertThat(auditEntries.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Đoạn này đặt trong lớp mục 7 và cần:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doThrow;
~~~

Nó có ích để tiêm lỗi khi cần kiểm tra rollback, **nhưng** nếu audit service là thành phần nội bộ quan trọng, một bài test database khác phải chạy implementation audit thật. Một lựa chọn thiết kế tốt hơn cho failure injection có thể là tách **persistence port** của audit service rồi mock port ấy; giữ domain/application service thật để kiểm tra phản ứng.

### 9.2. doNothing chỉ dành cho void method

Với một spy có method `void notify(UUID)`:

~~~java
doNothing().when(notificationSpy).notify(orderId);
~~~

giúp không chạy real method khi SUT gọi nó. Nhưng nếu method gửi email, việc chặn này **không tự tạo bằng chứng email sẽ được gửi**. Thường an toàn hơn là mock một `EmailGateway` port với `@MockitoBean` và kiểm thử adapter gửi email riêng.

## 10. Nguy cơ từ lúc tạo bean: @PostConstruct và constructor

Không phải mọi side effect xuất hiện vì `when(spy...)`. Để spy bean, Spring phải có **bean thật**. Ví dụ:

~~~java
@Service
class ExternalCatalogWarmup {

    private final CatalogHttpClient client;

    ExternalCatalogWarmup(CatalogHttpClient client) {
        this.client = client;
    }

    @PostConstruct
    void initialize() {
        client.preloadCatalog(); // I/O thật khi khởi tạo bean.
    }

    String status() {
        return "READY";
    }
}
~~~

Nếu bạn khai báo:

~~~java
@MockitoSpyBean ExternalCatalogWarmup warmup;
~~~

thì việc khởi tạo bean thật có thể đã gọi `preloadCatalog()` **trước khi test có cơ hội stub `warmup.status()`**. Câu:

~~~java
doReturn("TEST").when(warmup).status();
~~~

không thể quay ngược việc network call đã xảy ra lúc init.

### 10.1. Cách cô lập startup I/O

- Không thực hiện I/O không cần thiết trong constructor hoặc `@PostConstruct` nếu có thể thiết kế lifecycle rõ hơn.
- Tách I/O qua một **port/gateway** và dùng `@MockitoBean` cho gateway đó trong test, trước khi context tạo bean phụ thuộc.
- Dùng `@Profile` hoặc test configuration có chủ đích để tránh chạy startup job không thuộc mục tiêu test.
- Nếu muốn kiểm tra đúng startup behavior, dùng fake server/Testcontainers và assert request/side effect thật; không dựa vào spy để chặn.
- Đừng mở `DIRECT_DEPENDENCIES`/`ALL_DEPENDENCIES` chỉ để spy một bean ngoài module rồi phát hiện toàn bộ các initializer của dependency cũng chạy.

**Lưu ý:** Mock một bean dependency qua Spring Test có thể chặn các lời gọi vào dependency đó nếu quá trình wiring sử dụng mock. Nhưng nếu network I/O xảy ra **ngay trong constructor hoặc static initializer của bean cần spy**, không có stubbing của spy sau bootstrap nào chặn được nó.

## 11. @MockitoSpyBean và Spring AOP proxy: bẫy thứ hai

Spring thường áp dụng proxy cho bean có `@Transactional`, `@Cacheable`, `@Retryable` hoặc method security. Với `@MockitoSpyBean`, Spring Framework dùng `WRAP`: tạo spy trên target rồi **AOP proxy vẫn có thể bao quanh spy**.

~~~text
Test inject một bean:

  Spring AOP proxy
        │
        ▼
    Mockito spy
        │
        ▼
    Real target logic

@MockitoBean thay bean:

  Bare Mockito mock (không tự có các AOP advice gốc)
~~~

**Verification** bằng `verify(spyBean).method(...)` thường hoạt động qua proxy theo cơ chế Spring Test, nhưng **stubbing** qua proxy có thêm nguy cơ:

- `when(proxy.method())` có thể chạy cả AOP advice và real method.
- `doReturn(...).when(proxy).method()` tránh thực thi **real method** theo Mockito, nhưng một advice như `@Cacheable` vẫn có thể intercept lời gọi dùng để cấu hình stub.
- Khi advice cache một giá trị “rỗng” từ lần ghi nhận stubbing, lời gọi sau đó có thể nhận giá trị cache ngoài ý muốn thay vì stub.
- `@Retryable` hoặc transaction advice có thể thay đổi thời điểm/đếm invocation mà test quan sát.

### 11.1. Ví dụ cache proxy và cách unwrap

Giả sử bean thật:

~~~java
@Service
public class ExchangeRateService {

    private final RateProvider provider;

    public ExchangeRateService(RateProvider provider) {
        this.provider = provider;
    }

    @Cacheable("exchangeRates")
    public BigDecimal rateFor(String currency) {
        return provider.fetchRate(currency);
    }
}
~~~

Đây là ví dụ hạ tầng độc lập, cần định nghĩa `RateProvider`, bật Spring Cache và cấu hình cache manager. Trong test có `@MockitoSpyBean ExchangeRateService rates`, Spring có thể inject **AOP proxy** chứ không phải trực tiếp Mockito target.

Theo hướng dẫn Spring Framework, khi cần stub một spy chịu proxy advice, có thể lấy target:

~~~java
import org.springframework.test.util.AopTestUtils;

import static org.mockito.Mockito.doReturn;

ExchangeRateService spyTarget =
        AopTestUtils.getUltimateTargetObject(rates);

doReturn(new BigDecimal("25000"))
        .when(spyTarget)
        .rateFor("VND");
~~~

Việc unwrap giúp tránh **lời gọi cấu hình stubbing đi qua AOP proxy**. Khi production/test gọi `rates.rateFor("VND")` qua proxy, caching advice vẫn tham gia như thông thường. Bạn vẫn phải reset/clear cache đúng cách, bảo đảm có một target được spy hợp lệ và kiểm thử riêng semantics của cache.

**Không nên áp dụng unwrap như một câu thần chú cho mọi test.** Nếu mục tiêu là kiểm tra behavior của `@Cacheable`, việc stub target có thể che chính logic cần kiểm chứng. Nếu mục tiêu là tránh gọi remote rate provider, ưu tiên mock `RateProvider` port thay vì spy cả `ExchangeRateService`.

### 11.2. AOP còn khiến transaction assertion dễ hiểu sai

Trong một test dùng `@MockitoSpyBean` trên transactional service, lời gọi qua Spring proxy có thể đi qua advice, còn việc tự lấy target rồi gọi trực tiếp có thể **bỏ qua một số advice**. Đừng dùng:

~~~java
spyTarget.placeOrder(...);
~~~

để chứng minh transaction propagation. Hãy gọi **Spring-managed proxy của service** rồi assert database/commit/rollback. Chỉ unwrap khi cần cấu hình Mockito target trong tình huống đã hiểu tác động proxy.

## 12. Spy vào bean ngoài module: context có thể không khởi động

Một sai lầm phổ biến trong `@ApplicationModuleTest(STANDALONE)`:

~~~java
@MockitoSpyBean CustomerEligibility customers;
~~~

Nếu `CustomerEligibilityService` thật chỉ thuộc module `customers`, nó không có trong Spring test context của `orders`. `@MockitoSpyBean` không thể tạo implementation từ một interface; Spring có thể báo lỗi **không tìm thấy bean cần wrap**.

Khi chỉ cần điều khiển kết quả:

~~~java
@MockitoBean CustomerEligibility customers;

when(customers.canPlaceOrder(customerId))
        .thenReturn(true);
~~~

Khi mục tiêu thực sự là kiểm tra public API và implementation `customers`:

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealCustomersTests {

    @Autowired OrderService orders;
    @MockitoSpyBean CustomerEligibility customers;

    // Chỉ hợp lệ nếu có đúng một bean thật phù hợp.
    // Test cần fixture customers và các dependency thực.
}
~~~

Nhưng trước khi spy bean thật trong integration test, hãy hỏi: **Có cần spy không, hay chỉ cần gọi API thật và assert kết quả DB?** Việc nạp module `customers` thật có thể khởi tạo thêm JPA, cache, HTTP adapter và listeners.

### 12.1. Nhiều bean cùng interface

Nếu có nhiều implementation `CustomerEligibility`, một `@MockitoSpyBean` theo type có thể mơ hồ. Dùng tên/qualifier đúng:

~~~java
@MockitoSpyBean(name = "retailCustomerEligibility")
CustomerEligibility customers;
~~~

Tên phải ứng với bean **thực sự tồn tại** trong context; spy không tạo mới khi tên không tìm thấy. Kiểm tra cả injection point của SUT xem nó có dùng đúng bean đó không. Một `verify(spy)` trên bean khác với bean mà SUT inject sẽ gây `Wanted but not invoked`.

### 12.2. Bean scopes và FactoryBean

Khả năng override `prototype`, scoped proxy hoặc các bean được tạo qua `FactoryBean` có các quy tắc và khác biệt theo phiên bản Spring Framework. Không mặc định rằng có thể spy mọi scope như singleton bình thường:

- Đối chiếu reference/Javadoc **đúng version** của dự án.
- Xác nhận bean target được chọn đúng và không vô tình thay đổi lifecycle/scope trong test.
- Với `FactoryBean`, cần hiểu mình spy **object do factory tạo** hay bản thân factory.
- Tránh dựa vào trạng thái của spy singleton để suy luận đúng về production bean có request/session scope.

## 13. Mockito @Spy thuần khác @MockitoSpyBean trong Spring context

Unit test không có Spring có thể làm:

~~~java
@ExtendWith(MockitoExtension.class)
class AuditUnitTests {

    @Mock OrderAuditRepository repository;
    private OrderAuditService audits;

    @BeforeEach
    void prepareSpy() {
        // @Mock đã được MockitoExtension khởi tạo trước @BeforeEach.
        audits = spy(new OrderAuditService(repository));
    }

    @Test
    void recordsUsingRealMethod() {
        UUID orderId = UUID.randomUUID();

        audits.record(orderId);

        verify(repository).saveAndFlush(any(OrderAuditEntry.class));
    }
}
~~~

Đoạn test cần import `org.junit.jupiter.api.BeforeEach` và static `Mockito.spy`, `Mockito.verify`, `Mockito.any`. Khởi tạo spy trong `@BeforeEach` **sau khi `MockitoExtension` đã khởi tạo `@Mock repository`**; không truyền một field mock chưa được khởi tạo vào constructor trong field initializer. Vì repository là mock, đây là **unit test**, không chứng minh JPA row commit. `@Spy` hoặc `Mockito.spy(...)` áp dụng cho object trong unit test; chúng **không tự override bean** mà Spring inject vào một `OrderService` thuộc `@ApplicationModuleTest`.

Ngược lại:

~~~java
@ApplicationModuleTest
class OrderAuditIntegrationTests {
    @MockitoSpyBean OrderAuditService audits;
}
~~~

đặt spy vào Spring test context. Các bean khác được Spring inject phù hợp với cơ chế bean override. Đây là khác biệt cốt lõi giữa test thuần Mockito và module integration test.

### 13.1. Mockito.spy(real) và tham chiếu đối tượng

Với `Mockito.spy(existingObject)`, không nên tự giả định spy và object gốc là **cùng tham chiếu** hoặc mọi state change bên ngoài đều tự phản ánh theo một cách đơn giản. Mockito có cơ chế tạo spy từ object hiện có; hãy xác định rõ bạn đang gọi/verify **spy** hay object gốc. Trong Spring, dùng `@MockitoSpyBean` đúng context giúp tránh tình huống bạn verify một spy tự tạo nhưng SUT vẫn gọi bean không được spy.

## 14. Spy trong event listener: đừng biến kiểm thử thành side effect giả

Giả sử module `notifications` có listener:

~~~java
@Component
class OrderNotificationListener {

    private final EmailGateway gateway;

    OrderNotificationListener(EmailGateway gateway) {
        this.gateway = gateway;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        gateway.sendConfirmation(
                event.orderId(), event.eventId());
    }
}
~~~

Nếu test tạo spy trên **listener thật** và gọi trực tiếp:

~~~java
listener.on(event);
verify(listener).on(event);
~~~

thì real listener code đã chạy và có thể gửi email. Đồng thời test đó **không chứng minh** Spring event infrastructure đã kích hoạt callback sau commit hoặc Event Publication Registry đã hoàn tất.

### 14.1. Test listener đúng phạm vi

Thay vì spy gateway gửi email thật:

~~~java
@ApplicationModuleTest
class NotificationModuleTests {

    @MockitoBean EmailGateway email;

    // Dùng Scenario/transaction thật để trigger và chờ listener.
    // Sau đó verify email nhận đúng orderId/eventId,
    // và assert registry/state theo mục tiêu bài test.
}
~~~

`EmailGateway` cần là port được expose/inject hợp lệ trong test context; listener và event infrastructure nên chạy thật nếu mục tiêu là kiểm tra luồng event. Đây là **skeleton**, chưa có fixtures và cấu hình transaction.

Với `@ApplicationModuleListener`, callback thường chạy **sau commit**, bất đồng bộ và trong transaction mới. Test phải chờ kết quả theo điều kiện bằng `Scenario` hoặc Awaitility; không chạy trực tiếp `listener.on(event)` rồi kết luận annotation/transaction đã được kiểm chứng.

### 14.2. PublishedEvents không chứng minh listener completed

`PublishedEvents` ghi nhận ứng dụng **phát** event trong phạm vi test, không xác minh đầy đủ:

- Source transaction đã commit.
- Async listener đã chạy xong.
- Email provider đã nhận message.
- Registry đã đánh dấu publication completed.
- Consumer idempotent khi event được phát lại.

Một `verify(spyListener).on(event)` cũng chỉ cho biết invocation xảy ra trên spy. Cần test side effect và transaction riêng ở receiver module/integration.

## 15. Spy + transaction: rollback vẫn có thể bỏ sót side effect ngoài DB

Trong `OrderService.place` ví dụ, `OrderAuditService.record` ghi database **trong transaction nguồn** khi được gọi từ service. Nếu một unchecked exception xảy ra trước commit và transaction rollback, DB records có thể bị rollback. Tuy vậy:

- Một real method bị gọi **trong stubbing** ở ngoài transaction service có thể đã commit row trước.
- Một HTTP/email/payment call thực hiện trong real method **không được DB rollback thu hồi**.
- Một event đã gọi `publishEvent` trước khi ném exception có thể vẫn được `PublishedEvents` quan sát, dù `@TransactionalEventListener(AFTER_COMMIT)` không chạy.
- Một listener async có thể chạy sau thời điểm test method trả về nếu test chưa chờ đúng cách.

### 15.1. Không để @Transactional bao toàn bộ test một cách vô thức

Nếu test có:

~~~java
@ApplicationModuleTest
@Transactional
class OrderTests {
    // ...
}
~~~

Spring Test thường tạo một transaction bao quanh test và rollback cuối test. Khi `OrderService` join transaction test, listener after-commit có thể **không chạy trong suốt test**. Điều này có thể che việc một spy real method đã ghi vào persistence context, đồng thời làm kết quả phụ thuộc transaction isolation.

Khi mục tiêu là commit/after-commit:

- Không thêm `@Transactional` bao ngoài nếu không cần.
- Hoặc dùng `TransactionTemplate` / `TestTransaction` để kiểm soát commit rõ ràng.
- Assert database qua transaction phù hợp.
- Chờ callback async theo điều kiện.

### 15.2. Đừng dùng spy để “chứng minh không có transaction”

Nếu `@MockitoSpyBean` wrap bean có `@Transactional`, việc `verify(spy).method()` không cho biết transaction đang active, isolation đúng hay commit đã diễn ra. Muốn kiểm tra transaction, cần assertion về state/rollback hoặc một integration test có transaction manager thật.

## 16. Khi nào dùng doThrow, doAnswer và doCallRealMethod?

### 16.1. doThrow

~~~java
doThrow(new IllegalStateException("Simulated"))
        .when(audits).record(orderId);
~~~

Tác dụng: lần gọi `record(orderId)` sau khi stub sẽ ném exception do test chọn **thay vì chạy real method** (với điều kiện không có proxy advice gây khác biệt). Hữu ích để tiêm failure có chủ đích; không chứng minh database thật sẽ ném cùng exception.

### 16.2. doAnswer

~~~java
doAnswer(invocation -> {
    UUID actual = invocation.getArgument(0);
    if (!actual.equals(orderId)) {
        throw new IllegalArgumentException(
                "Unexpected order ID");
    }
    return "SIMULATED";
}).when(audits).record(any(UUID.class));
~~~

`doAnswer` giúp mô phỏng logic phụ thuộc argument; nhưng biến spy thành một fake phức tạp với trạng thái nội bộ có thể khó hiểu hơn việc tạo một test double rõ ràng cho public port.

### 16.3. doCallRealMethod

Nếu đã stub một method nhưng muốn chạy real implementation cho invocation cụ thể, Mockito có:

~~~java
doCallRealMethod().when(audits).record(orderId);
~~~

Điều này **không an toàn** nếu bạn chưa chấp nhận side effect của real `record`. Với spy, real method đã là hành vi mặc định khi chưa stub; không cần `doCallRealMethod` chỉ để “cho chắc”.

### 16.4. Tránh reset giữa chừng để “làm sạch” side effect

`Mockito.reset(audits)` chỉ xóa stubbings/interactions của Mockito; nó **không xóa row database, đảo ngược email đã gửi hoặc dọn cache**. Với `@MockitoSpyBean`, reset ở cuối test theo framework cũng không sửa được tác động business. Phải thiết kế isolation và teardown đúng hạ tầng.

## 17. Test isolation: một spy có thể gây nhiễu giữa nhiều test

Spring Test cache `ApplicationContext` để tăng tốc. `@MockitoSpyBean` có cơ chế reset giữa các test methods theo cấu hình nhưng **state ngoài Mockito** có thể còn:

- Database row được ghi trong bước setup trước transaction test.
- Cache entry do `@Cacheable` advice tạo.
- Static counters hoặc state trong singleton bean thật.
- Message nằm trong broker hoặc task đang chờ executor.
- HTTP call đã gửi tới fake/external server.
- Connection lock hoặc scheduled job đã kích hoạt khi bean khởi tạo.

### 17.1. Dùng dữ liệu riêng, không dựa vào thứ tự test

Trong ví dụ audit, dùng `UUID.randomUUID()` cho từng test và assert row theo ID riêng. Với những test cần tái sử dụng ID hoặc schema:

- Dùng transaction/DB cleanup có chủ đích.
- Dùng `@Sql`/fixtures hoặc xóa row tại teardown theo chiến lược dự án.
- Không trông chờ Mockito reset sẽ dọn DB.
- Nếu dùng cache, clear/evict theo test lifecycle; nếu dùng broker, isolate topic/consumer offsets.
- Nếu có async callback, đợi hoàn tất trước khi test kết thúc/reset spy.

### 17.2. Test chạy song song

Hai test dùng chung một spy singleton có thể cùng cấu hình stub hoặc reset, làm thay đổi cách real bean xử lý callback từ test khác. Không chạy song song nếu context/mock và fixture không được thiết kế thread-safe và isolated. Khi thật sự cần parallelism, tách context hoặc áp dụng cơ chế đồng bộ/dữ liệu độc lập phù hợp.

### 17.3. Nên dùng integration boundary giả thay spy với side effect cao

Nếu bean thực thi HTTP/network, dùng `@MockitoBean` ở **port** hoặc WireMock/MockWebServer để ngăn kết nối môi trường thật. Với Kafka/AMQP, dùng broker test container và ràng buộc topic test. Spy trực tiếp trên producer/gateway thật có nguy cơ gửi message tới hạ tầng không dự kiến nếu test config sai.

## 18. Chẩn đoán các lỗi hay gặp với spy

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Database row xuất hiện **trước khi gọi SUT**. | `when(spy.record(...))` đã thực thi real method. | Dùng `doReturn` nếu thật sự cần stub; tốt hơn xem lại mục tiêu test. |
| HTTP/email được gửi khi chạy `@BeforeEach`. | Stubbing trên spy gọi method thật, hoặc bean init có side effect. | Fake gateway trước bootstrap; bỏ I/O khỏi init nếu có thể. |
| `@MockitoSpyBean` làm context fail “bean không tồn tại”. | `STANDALONE` không nạp implementation module ngoài. | `@MockitoBean` cho boundary, hoặc mở rộng bootstrap khi cần bean thật. |
| Context fail vì nhiều candidate. | Spy theo type mơ hồ. | Đúng `@Qualifier` hoặc `name`; kiểm tra injection point. |
| `doReturn` đã stub nhưng caller thấy `null`/giá trị cache khác. | AOP proxy `@Cacheable` can thiệp khi stubbing. | Lấy Mockito spy target với `AopTestUtils.getUltimateTargetObject`; clear cache đúng cách. |
| `verify(spy)` pass nhưng database không có row. | Method bị stub chặn, transaction rollback hoặc kiểm tra sai DB. | Giữ real method khi test DB; assert state/commit. |
| Spy báo nhiều invocation hơn dự kiến. | Retry, callback async, initializers hoặc test chưa isolated. | Xác định contract count và đo đúng lifecycle; không nới `times` tùy tiện. |
| Test pass khi local nhưng flaky trên CI. | Scheduling/cache/context reuse/DB state không cô lập. | Awaitility/Scenario, unique IDs, cleanup, điều khiển concurrency. |
| Mockito verify trên spy tự tạo báo “wanted but not invoked”. | SUT gọi Spring bean gốc thay vì object `Mockito.spy(...)` tự tạo. | Dùng đúng `@MockitoSpyBean` để wrap bean trong Spring context. |
| Unit test pass nhưng production @Transactional lỗi. | Dựng bean bằng `new`/spy ngoài proxy, không chạy Spring AOP. | Integration test qua Spring-managed proxy và DB thật. |

Trong một số lỗi debug, **lệnh verify thành công chỉ cho biết đối tượng spy đã nhận lời gọi**. Nó không phải giấy chứng nhận về absence of side effects, commit, durable delivery hoặc idempotency.

## 19. Khi nào nên tránh spy hoàn toàn?

Cân nhắc **không spy** khi:

1. Dependency là **public collaborator ngoài module** và test chỉ cần stub response.
2. Bean thực thi payment charge, gửi email hoặc gọi external API mà test không định kiểm tra thực.
3. Test chỉ cần khẳng định output/DB state, không cần bảo vệ lời gọi method cụ thể.
4. Bean có `@PostConstruct` hoặc scheduled logic phụ thuộc I/O thật khó cô lập.
5. AOP proxy/caching khiến stubbing dễ sai và có thể che hành vi cần bảo vệ.
6. Bean có mutable state dùng chung, async tasks hoặc lifecycle/scopes khó kiểm soát.
7. Test muốn kiểm chứng transaction commit, listener completion, broker delivery hoặc external contract — những thứ `verify(spy)` không chứng minh.

**Spy không phải biểu tượng của integration test “thật hơn”.** Một test dùng real `OrderAuditService` **không spy** rồi query row thật thường mạnh hơn test spy chỉ verify `record(...)`.

## 20. Bảo vệ ranh giới kiến trúc bằng ApplicationModules

Mockito có thể khiến Spring context khởi động dù module `orders` truy cập implementation nội bộ của `customers`. Một `@MockitoSpyBean CustomerRepository` hoặc `@MockitoBean CustomerRepository` **không làm dependency sai thành hợp lệ**.

Architecture test:

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

`verify()` kiểm tra các quy tắc về module dependencies, public/named interfaces, cycle và `allowedDependencies` của Spring Modulith. Nó **không tự phát hiện mọi side effect của spy** hay tính đúng của schema/database/event. Vì vậy cần architecture gate **song song** với module behavior tests.

### 20.1. Efferent dependencies và module coupling

Nếu module `orders` phụ thuộc quá nhiều service ngoài module và mỗi test phải spy nhiều implementation thật, đó là dấu hiệu cần xem lại module coupling. Có thể:

- Dùng public API hẹp theo named interface.
- Mock collaborator ngoài module ở mức contract khi test riêng `orders`.
- Chuyển các side effects sau commit sang domain events và listeners thuộc module nhận khi nghiệp vụ cho phép.
- Tạo integration test riêng để bảo vệ hợp đồng giữa các modules thật.

Không giải quyết coupling bằng cách spy mọi bean và test cùng lúc cả ứng dụng.

## 21. Test contract và integration: phần spy không chứng minh

Trong `@ApplicationModuleTest(STANDALONE)`, dùng:

~~~java
@MockitoBean CustomerEligibility customers;
when(customers.canPlaceOrder(customerId)).thenReturn(true);
~~~

để test `orders` là hợp lý. Nhưng nó không chứng minh implementation thật của `customers` trả `true` đúng contract. Tương tự, spy một service dùng HTTP thật không chứng minh serialization, timeout hoặc authentication.

Cần các tầng:

| Loại test | Chạy thật | Giả lập/cô lập | Điều cần assert |
| --- | --- | --- | --- |
| **Unit audit** | `OrderAuditService` method thật. | `@Mock OrderAuditRepository`. | Method gọi repository đúng; chưa chứng minh JPA. |
| **Module orders** | OrderService, audit service, JPA, publisher. | `@MockitoBean CustomerEligibility` ngoài module. | Row order/audit và `PublishedEvents`. |
| **Spy behavior demo** | `OrderAuditService` thật qua spy. | Có hoặc không stub từng method. | Phân biệt DB side effect trước/sau SUT. |
| **Provider module test** | `CustomerEligibilityService` thật. | External gateway nếu cần. | Active/blocked customer đúng contract. |
| **Direct dependencies test** | orders + customers thật. | Không mock API cần kiểm chứng. | Wiring, logic và JPA liên module. |
| **HTTP adapter test** | HTTP client/serialization thật. | WireMock/MockWebServer. | Request, status, headers, retry. |
| **Event listener test** | Listener + transaction/event registry. | Fake email/gateway port. | AFTER_COMMIT, persistence, recovery/idempotency. |
| **Architecture test** | Mô hình module tĩnh. | Không Mockito. | `ApplicationModules.verify()`. |

### 21.1. Integration test với implementation customers thật

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersAndCustomersIntegrationTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;
    @Autowired CustomerFixture customerFixture;

    @Test
    void realEligibleCustomerCanPlaceOrder() {
        UUID customerId = customerFixture.createEligibleCustomer();
        UUID orderId = UUID.randomUUID();

        orders.place(orderId, customerId);

        assertThat(repository.existsById(orderId)).isTrue();
    }
}
~~~

`CustomerFixture` là **test fixture giả định cần triển khai**; snippet chưa hoàn chỉnh như một dự án có thể chạy độc lập. Điểm cần nhớ là **không dùng `@MockitoBean CustomerEligibility` trong test này**, vì mục tiêu đang là kiểm chứng bean thật và hợp đồng module.

## 22. Quality gate CI cho spy và side effect

| Quality gate | Kịch bản | Lỗi có thể phát hiện |
| --- | --- | --- |
| **Architecture** | `ApplicationModules.of(...).verify()`. | Truy cập API nội bộ/cycle/`allowedDependencies` sai. |
| **Unit tests** | Method business thuần không spy; audit method với mock repository. | Logic, argument, nhánh exception. |
| **Module behavior** | `@ApplicationModuleTest` giữ audit/DB/event thật. | Không lưu audit, lưu sai order, event sai. |
| **Spy setup hazard test** | So `when(spy.method())` với `doReturn` trong môi trường cô lập. | Method chạy thật khi cấu hình stub. |
| **Bean lifecycle test** | Bootstrap bean có init logic. | HTTP/DB work bất ngờ trong constructor/`@PostConstruct`. |
| **AOP test** | Spy bean có `@Cacheable`/`@Transactional`. | Proxy stubbing sai/cached empty value/advice bị bỏ qua. |
| **Negative/failure test** | Audit persistence lỗi giữa transaction. | Order không rollback, event phát sai thời điểm. |
| **Provider contract** | `customers` thật theo active/blocked state. | Mock response không khớp implementation. |
| **Async listener** | Event after commit, completion state. | Side effect chạy trễ, registry incomplete, callback lỗi. |
| **External protocol** | Fake HTTP/broker test thay vì spy gateway thật. | Truyền sai headers/payload, timeout/retry. |
| **Test isolation** | Chạy test lặp lại, xáo thứ tự, song song có kiểm soát. | Database/cache/async leakage giữa các tests. |

Khi xây CI:

- Chạy unit, architecture và module integration tests trên mỗi pull request nếu chi phí phù hợp.
- Chạy integration tests có database/broker thật hoặc Testcontainers tại stage chuyên biệt cho thay đổi liên quan.
- Không cho test dùng spy trực tiếp kết nối endpoint production; ràng buộc environment/test profile.
- Với lỗi async khó tái hiện, chờ trạng thái bằng `Scenario`/Awaitility thay vì `Thread.sleep` cố định.
- Bất kỳ test nào cố ý dùng `when(spy.sideEffectMethod())` để minh họa nguy hiểm phải chạy trên fixture cô lập; **không tái sử dụng đối tượng có quyền ghi hệ thống ngoài**.

## 23. Các anti-pattern đặc trưng

### 23.1. Spy gateway thật để “khỏi phải mock”

~~~java
@MockitoSpyBean PaymentGateway gateway;
~~~

Nếu SUT gọi `gateway.capture(...)` khi chưa stub, **payment call thật có thể diễn ra**. Dùng mock/fake payment port và kiểm thử adapter với sandbox/provider hợp lệ.

### 23.2. Stubbing with when trên real side-effect method

~~~java
when(audits.record(orderId)).thenReturn("OK");
~~~

Có thể ghi DB trước SUT. Dùng `doReturn` nếu thật sự muốn chặn call, nhưng cân nhắc xem việc chặn có khiến test mất giá trị không.

### 23.3. Tin rằng doReturn ngăn mọi side effect

~~~java
doReturn("OK").when(cacheProxySpy).value();
~~~

Mockito tránh gọi real spy method khi cấu hình, nhưng **proxy advice có thể vẫn tham gia**; với `@Cacheable` cần cân nhắc unwrap target và clear cache.

### 23.4. Spy bean vắng mặt trong STANDALONE

~~~java
@MockitoSpyBean CustomerEligibility customers;
~~~

Nếu module `customers` không được nạp, không có bean để wrap; dùng `@MockitoBean` ở public boundary.

### 23.5. Spy business helper rồi verify mọi method nội bộ

~~~java
verify(policy).calculateDiscount(...);
verify(policy).roundPrice(...);
~~~

Gắn test vào implementation detail. Nếu mục tiêu là số tiền cuối, assert total trên DTO/entity.

### 23.6. Cho spy chạy HTTP thật trong @BeforeEach

Một stubbing `when(spy.fetchRemote())` có thể gọi remote ngay tại setup. Chuyển sang fake port hoặc fake server và tránh init I/O ngoài ý muốn.

### 23.7. Verify spy rồi kết luận database commit

~~~java
verify(audits).record(orderId);
~~~

Chỉ chứng minh một invocation; transaction có thể rollback hoặc method bị stub không ghi gì. Assert database state/commit riêng.

### 23.8. Dùng Mockito.reset để sửa state contamination

Reset xóa Mockito invocations/stubs chứ không thu hồi DB row, email, broker message hay cache entry. Cần cleanup/isolation thật.

### 23.9. Dùng spy để chứng minh event listener sau commit

Gọi trực tiếp listener và verify method không chứng minh `AFTER_COMMIT`, registry lifecycle hoặc retries. Dùng module/integration test qua Spring event infrastructure.

### 23.10. Chạy test song song với spy singleton không cô lập

Một test reset/stub spy khi test khác đang dùng có thể gây kết quả không ổn định. Quản lý context, mock reset và async lifecycle có chủ đích.

## 24. Bài tập thực hành

Một ứng dụng Spring Modulith có:

- Module `checkout` gọi public API `payments.api.PaymentAuthorization`.
- Module `checkout` có `CheckoutAuditService.record(checkoutId)` ghi database.
- Khi giao dịch thành công, `checkout` phát `CheckoutCompleted`.
- Module `notifications` có listener `@ApplicationModuleListener` gửi email qua `EmailGateway`.

Bạn thấy trong một test:

~~~java
@ApplicationModuleTest
class CheckoutTests {

    @MockitoSpyBean PaymentAuthorization payments;
    @MockitoSpyBean CheckoutAuditService audits;

    @BeforeEach
    void setup() {
        when(audits.record(fixedCheckoutId))
                .thenReturn("RECORDED");
    }
}
~~~

### Câu hỏi

1. Vì sao `@MockitoSpyBean PaymentAuthorization` có thể khiến `STANDALONE` context fail?
2. Trong test chỉ kiểm tra logic `checkout`, thay annotation nào cho API `payments`?
3. `when(audits.record(fixedCheckoutId))` có thể tạo side effect gì trước khi test gọi `CheckoutService`?
4. `doReturn(...).when(audits).record(id)` tránh nguy cơ nào, và có thể **che mất** điều gì?
5. Nếu `CheckoutAuditService` có `@PostConstruct` gọi REST API, `doReturn` trong test method có ngăn được REST call đã xảy ra lúc init không?
6. Nếu audit service dùng `@Cacheable` qua proxy, cần lưu ý điều gì khi stub spy?
7. Nếu `verify(audits).record(id)` pass nhưng DB không có audit row, đâu là các nguyên nhân có thể?
8. Nếu test muốn xác nhận `CheckoutCompleted` được phát, nên mock `ApplicationEventPublisher` hay dùng `PublishedEvents`?
9. Nếu muốn xác nhận notification listener đã chạy sau commit và email được gửi, có thể chỉ `verify(spyListener).on(event)` không?
10. Nếu module `checkout` import `payments.internal.PaymentRepository`, Mockito spy có hợp thức hóa phụ thuộc không?

### Đáp án tham khảo

1. `@MockitoSpyBean` cần **một bean thật**; `STANDALONE` không nạp implementation `payments`.
2. `@MockitoBean PaymentAuthorization` để stub approved/declined/error tại **public module boundary**.
3. Real `record` có thể ghi DB, mở transaction hoặc ném exception ngay lúc cấu hình `when`; fixture dùng chung dễ bị nhiễu.
4. `doReturn` thường ngăn real method chạy lúc setup trên spy thông thường, nhưng cũng **ngăn real audit logic chạy khi lời gọi đã stub xảy ra**, nên không chứng minh audit persistence.
5. **Không**. Bean thật được khởi tạo trước khi test method stub spy; phải cô lập dependency hoặc thay đổi lifecycle thiết kế.
6. `doReturn` qua AOP proxy có thể bị advice/cache can thiệp; cân nhắc `AopTestUtils.getUltimateTargetObject`, clear cache và test proxy semantics riêng.
7. Method có thể bị stub, transaction rollback, kiểm tra sai datasource hoặc callback chưa hoàn tất; cần assert DB qua transaction phù hợp.
8. Giữ publisher thật, dùng `PublishedEvents` lọc theo checkout ID và payload.
9. **Không**. Phải trigger event trong transaction commit, chờ listener async, kiểm tra side effect và publication state nếu mục tiêu yêu cầu.
10. Không. Phải sửa dependency về public/named interface và chạy `ApplicationModules.verify()`.

## 25. Checklist trước khi khai báo @MockitoSpyBean

- [ ] Đã xác định rõ **vì sao cần spy**, không chỉ vì muốn `verify` mà không viết mock.
- [ ] Biết đối tượng là **bean thật trong ApplicationContext**, không phải public collaborator bị loại ở `STANDALONE`.
- [ ] Đã kiểm tra số lượng candidate/qualifier/name để chọn đúng bean SUT thực sự dùng.
- [ ] Đã phân biệt `@Spy` của Mockito với `@MockitoSpyBean` của Spring Test.
- [ ] Đã hiểu mọi **real method không stub** có thể chạy và tạo side effect.
- [ ] Đã kiểm tra constructor, `@PostConstruct` và init callbacks trước khi spy.
- [ ] Không dùng `when(spy.sideEffectMethod())` nếu nó có thể ghi DB, gọi HTTP hoặc ném exception.
- [ ] Nếu dùng `doReturn`/`doThrow`, hiểu nó có thể **che chính logic nghiệp vụ** cần kiểm chứng.
- [ ] Nếu bean có `@Cacheable`/`@Transactional`/`@Retryable`, đã xem lại cách Spring AOP bao quanh spy.
- [ ] Nếu stub qua proxy có vấn đề, cân nhắc unwrap Mockito target có kiểm soát; không gọi target trực tiếp để suy luận transaction.
- [ ] Đã đánh giá bean scope, FactoryBean và hạn chế theo đúng version của Spring.
- [ ] Nếu chỉ muốn cô lập network/payment/email, mock một **I/O port** hoặc dùng fake server thay vì spy gateway thật.
- [ ] Trong module test, giữ service, JPA repository và publisher thật khi cần kiểm chứng state/event.
- [ ] `PublishedEvents` chỉ dùng để quan sát event phát, không thay listener completion/integration test.
- [ ] Với callback async, dùng `Scenario`/Awaitility và deadline rõ; không chỉ `verify(timeout())`.
- [ ] Với transaction rollback, assert DB state; không suy commit từ `verify(spy)`.
- [ ] Không dùng reset spy như phương án dọn database/cache/broker state.
- [ ] Test data, mock reset, context reuse và parallel execution được cô lập.
- [ ] API module ngoài có provider contract test thật, không chỉ stub trong module consumer.
- [ ] Có integration test không override public collaborator nếu mục tiêu là kiểm chứng wiring thật.
- [ ] `ApplicationModules.verify()` bảo vệ named interface và `allowedDependencies`.
- [ ] CI bao phủ module state, startup side effect, AOP, async, security và integration.

**Kết luận:** `@MockitoSpyBean` cho phép quan sát **bean thật** trong Spring Test context, nhưng đi kèm trách nhiệm chấp nhận **real behavior**. Nguy cơ không chỉ nằm ở lúc SUT gọi: constructor/`@PostConstruct`, `when(spy.method())`, AOP proxy và async callbacks đều có thể tạo side effect ngoài ý muốn. Trong Spring Modulith, hãy mock public collaborator ngoài module bằng `@MockitoBean` khi cần cô lập; giữ logic nội bộ thật và assert database/`PublishedEvents` khi cần chứng minh hành vi; chỉ spy khi có lý do hợp đồng rõ. Kết hợp với `ApplicationModules.verify()`, transaction tests và integration/CI gates để test vừa an toàn vừa phát hiện hồi quy thực.

### Tài liệu tham khảo

- [Spring Framework — `@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): WRAP vs REPLACE_OR_CREATE, `doReturn` và AOP proxy/caching caveats.
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): bean override strategies và Spring AOP lifecycle.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes và mock efferent dependencies.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): public module APIs, named interfaces và dependency rules.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listener, registry và test behavior.
- [Mockito — Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html): spies, `when`, `doReturn`, `doThrow`, `verify`.

> Ghi chú tương thích: bài minh họa với Spring Framework 6.2+, Spring Modulith, Mockito, JUnit 5 và Spring Data JPA. Chi tiết override non-singleton, scoped proxies hoặc FactoryBean cần đối chiếu đúng phiên bản framework đang dùng. Các entity, schema, Spring Cache/AOP configuration, database fixtures và external gateways cần bổ sung theo dự án. Theo quy trình STEP_4, chưa chạy Gradle hoặc vòng Content QA chuyên môn.
