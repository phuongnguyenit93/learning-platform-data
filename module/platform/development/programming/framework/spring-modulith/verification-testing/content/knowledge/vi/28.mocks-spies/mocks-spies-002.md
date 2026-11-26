# Mock boundary hay mock implementation detail?

## 1. Câu hỏi cần trả lời trước khi dùng Mockito

Khi viết test cho một ứng dụng Spring Modulith, thấy `@Autowired` hoặc constructor có nhiều dependency, ta dễ có phản xạ: **mock tất cả để bài test chạy nhanh**. Nhưng cách đó có thể khiến test kiểm tra một phiên bản giả của chương trình thay vì hành vi cần bảo vệ. Ngược lại, không mock bất kỳ dependency nào cũng khiến một test nhỏ phải khởi động cả database, HTTP client, message broker và nhiều application module không liên quan.

Câu hỏi đúng hơn là:

> **Đối tượng nào nằm ở ranh giới của hành vi đang kiểm chứng, và đối tượng nào là một phần của chính hành vi đó?**

- **Mock boundary**: thay một collaborator ở *bên kia ranh giới kiểm thử* bằng test double, rồi kiểm chứng hệ thống đang test phản ứng đúng với kết quả/hợp đồng của collaborator.
- **Mock implementation detail**: thay chính những thành phần thực hiện quy tắc nghiệp vụ hoặc phối hợp nội bộ mà bài test có trách nhiệm bảo vệ. Cách này có thể che lỗi, khiến test phụ thuộc cấu trúc code và tạo kết quả xanh giả.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, ranh giới quan trọng là **application module**: kiểm chứng phụ thuộc qua `ApplicationModules`, dùng `@ApplicationModuleTest` để chạy module theo phạm vi, kiểm thử sự kiện và database bằng hạ tầng phù hợp, rồi kết hợp tất cả thành quality gate trong CI.

**Nguyên tắc trọng tâm:** Không có class nào “luôn phải mock” hoặc “tuyệt đối không được mock”. Tính phù hợp phụ thuộc **mục tiêu và kích thước của test**. Một repository có thể là boundary của **unit test** cho service, nhưng là thành phần cần chạy thật trong **module integration test** bảo vệ thao tác lưu dữ liệu.

### Sau bài này, bạn có thể

1. Phân biệt module boundary, I/O boundary, unit boundary và implementation detail.
2. Chọn dependency nào nên fake/mock trong `@ApplicationModuleTest(STANDALONE)`.
3. Giữ domain logic, transaction, repository và event publisher thật khi cần chứng minh kết quả module.
4. Viết test cùng ví dụ ở hai cách: **mock public API ngoài module** và **mock implementation nội bộ**, rồi giải thích khác biệt.
5. Áp dụng `@MockitoBean`, `@Mock`, `@MockitoSpyBean` theo đúng Spring context và phiên bản.
6. Nhận diện test dễ vỡ vì verify call chain, over-stubbing hoặc che vi phạm `allowedDependencies`.
7. Thiết kế test kiến trúc, contract, persistence và integration bổ sung cho test có mock.

## 2. Ranh giới nào đang được kiểm thử?

Có ít nhất bốn loại ranh giới, không nên gộp chúng:

| Ranh giới | Ví dụ | Khi nào mock? |
| --- | --- | --- |
| **Unit boundary** | `OrderService` nhận `OrderRepository` và `PricingPolicy`. | Trong unit test chỉ kiểm tra service orchestration, mock repository hoặc collaborator có thể hợp lý. |
| **Application module boundary** | `orders` gọi `pricing.api.PriceQuoteService`. | Trong `@ApplicationModuleTest(STANDALONE)` cho `orders`, thường mock API công khai của `pricing`. |
| **I/O / side-effect boundary** | HTTP client tới payment provider, SMTP sender, filesystem, broker adapter. | Mock/fake port khi test business logic; kiểm thử adapter thật bằng fake server, Testcontainers hoặc môi trường tích hợp. |
| **Deployment/integration boundary** | Ứng dụng gọi service khác qua HTTP/Kafka. | Test isolated dùng double, nhưng cần contract/wire integration test ở lớp kiểm thử khác. |

Không chỉ dựa vào số lượng class hoặc package:

- `orders.internal.OrderPricingPolicy` là một bean riêng, nhưng nó chứa **quy tắc tính giá** của `orders`. Khi test cả module `orders`, đây là logic cần chạy thật.
- `pricing.api.PriceQuoteService` là API của **module khác**. Khi test riêng `orders`, thay nó bằng mock giúp cô lập trách nhiệm của `orders`.
- `orders.internal.OrderRepository` cũng là một bean riêng. Nếu mục tiêu là chứng minh đơn hàng **thực sự được ghi vào database** trong module test, mock repository sẽ làm mất giá trị assertion đó.
- `orders.infrastructure.PaymentHttpClient` có thể ở **cùng module** nhưng đại diện một I/O boundary. Mock một port quanh HTTP client trong module test vẫn có thể hợp lý dù package không nằm ngoài module.

### 2.1. Cây quyết định ngắn

~~~mermaid
flowchart TD
    A["Xác định behavior muốn bảo vệ"] --> B{"Dependency có thực hiện chính behavior đó?"}
    B -->|"Có"| C["Giữ implementation thật; assert state/outcome"]
    B -->|"Không"| D{"Nó nằm sau module/I-O boundary?"}
    D -->|"Có"| E["Mock/fake ở boundary, xác định contract"]
    D -->|"Không"| F["Ưu tiên giữ thật; cân nhắc test scope"]
    E --> G["Viết contract/integration test riêng cho implementation bị thay"]
    C --> H["Architecture + behavior tests"]
    F --> H
    G --> H
~~~

Mock ở boundary giúp **kiểm soát input hoặc failure của dependency**. Giữ implementation detail thật giúp **đảm bảo những phép biến đổi nội bộ** vẫn đúng khi cấu trúc code thay đổi.

## 3. Ví dụ xuyên suốt: module orders phụ thuộc báo giá của pricing

Giả sử ứng dụng Spring Boot có root package `com.example.shop`. Theo cách phát hiện module mặc định của Spring Modulith, `orders` và `pricing` là hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── pricing
│   ├── api
│   │   ├── PriceQuote.java
│   │   ├── PriceQuoteService.java
│   │   └── package-info.java
│   └── internal
│       ├── PriceQuoteServiceImpl.java
│       └── PriceTableRepository.java
└── orders
    ├── OrderService.java
    ├── package-info.java
    ├── events
    │   ├── OrderPlaced.java
    │   └── package-info.java
    └── internal
        ├── OrderPricingPolicy.java
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

Nghiệp vụ:

1. `OrderService` hỏi `pricing` giá niêm yết của một SKU.
2. Trong module `orders`, `OrderPricingPolicy` áp dụng **giảm 10%** cho khách VIP, không giảm cho khách thường.
3. `orders` lưu order với giá cuối cùng.
4. Sau khi đã xác định được dữ liệu cần lưu, `orders` phát `OrderPlaced`.

~~~mermaid
flowchart LR
    T["orders module test"] --> S["orders.OrderService (THẬT)"]
    S --> P["pricing.api.PriceQuoteService (MOCK)"]
    S --> C["orders.internal.OrderPricingPolicy (THẬT)"]
    S --> R["orders.internal.OrderRepository (THẬT)"]
    S --> E["ApplicationEventPublisher (THẬT)"]
    R --> DB[("Test database")]
    E --> PE["PublishedEvents"]
~~~

**Boundary cần thay trong test module:** `PriceQuoteService`.  
**Hành vi cần chứng minh:** thuật toán giảm giá, persistence và `OrderPlaced` đều là code thật thuộc `orders`.

### 3.1. Tạo API công khai cho module pricing

File `pricing/api/PriceQuote.java`:

~~~java
package com.example.shop.pricing.api;

import java.math.BigDecimal;
import java.util.Objects;

public record PriceQuote(BigDecimal subtotal, String currency) {
    public PriceQuote {
        Objects.requireNonNull(subtotal);
        Objects.requireNonNull(currency);
    }
}
~~~

File `pricing/api/PriceQuoteService.java`:

~~~java
package com.example.shop.pricing.api;

import java.util.UUID;

public interface PriceQuoteService {
    PriceQuote quoteFor(UUID skuId);
}
~~~

File `pricing/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.pricing.api;
~~~

Module `pricing` có thể triển khai API bằng service/repository trong `pricing.internal`. Module `orders` **chỉ cần hợp đồng** `PriceQuoteService` và `PriceQuote`, không cần truy cập bảng giá nội bộ.

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "pricing :: api"
)
package com.example.shop.orders;
~~~

Quy tắc `allowedDependencies` làm rõ việc `orders` chỉ được biết named interface `pricing :: api`. Đây là vấn đề **kiến trúc**, không thể giải quyết bằng Mockito.

## 4. Implementation detail chứa quy tắc nghiệp vụ: phải được kiểm thử thật

Trong `orders.internal`, tạo class tính giá:

~~~java
package com.example.shop.orders.internal;

import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Component
public class OrderPricingPolicy {

    private static final BigDecimal VIP_FACTOR =
            new BigDecimal("0.90");

    public BigDecimal totalFor(
            BigDecimal subtotal, boolean vipCustomer) {

        if (subtotal.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Subtotal must be positive");
        }

        BigDecimal amount = vipCustomer
                ? subtotal.multiply(VIP_FACTOR)
                : subtotal;

        return amount.setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`OrderPricingPolicy` là class độc lập và có thể dùng constructor injection. Nhưng về trách nhiệm, nó **thực thi quy tắc giá cuối cùng của module orders**. Nếu mock policy rồi stub trả `90000.00`, một lỗi đổi hệ số từ 10% sang 20% trong production **không bao giờ được thực thi trong bài test đó**.

### 4.1. Unit test thuần cho policy — không cần Mockito

~~~java
package com.example.shop.orders.internal;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OrderPricingPolicyTests {

    private final OrderPricingPolicy policy =
            new OrderPricingPolicy();

    @Test
    void appliesTenPercentDiscountToVip() {
        assertThat(policy.totalFor(
                    new BigDecimal("100000"), true))
                .isEqualByComparingTo("90000.00");
    }

    @Test
    void keepsFullPriceForNonVip() {
        assertThat(policy.totalFor(
                    new BigDecimal("100000"), false))
                .isEqualByComparingTo("100000.00");
    }

    @Test
    void rejectsNonPositiveSubtotal() {
        assertThatThrownBy(() -> policy.totalFor(
                    BigDecimal.ZERO, true))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Đây là unit test của **business rule**, không cần Spring context, database hay mock. Nó có sức chống hồi quy cao vì assertion gắn với **kết quả tiền** chứ không gắn với số lời gọi nội bộ.

### 4.2. Vì sao không verify các bước tính toán?

So sánh:

~~~java
verify(policy).totalFor(new BigDecimal("100000"), true);
~~~

và:

~~~java
assertThat(savedOrder.getTotal())
        .isEqualByComparingTo("90000.00");
~~~

Assertion thứ nhất chỉ chứng minh service **đã gọi method**. Nó không chứng minh method trả đúng số tiền hoặc kết quả được lưu. Assertion thứ hai kiểm tra **hành vi mà người dùng quan tâm**, ít phụ thuộc việc sau này team đổi tên/tách/gộp method nội bộ.

Mockito `verify(...)` hữu ích khi lời gọi **chính là một phần của hợp đồng bên ngoài** (ví dụ gọi public API báo giá đúng SKU), không phải khi chỉ muốn theo dõi mọi bước triển khai.

## 5. Entity, repository và event thuộc module orders

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
public class OrderEntity {

    @Id
    private UUID id;
    private UUID skuId;
    private UUID customerId;

    @Column(precision = 19, scale = 2, nullable = false)
    private BigDecimal total;

    private String currency;

    protected OrderEntity() {}

    public OrderEntity(UUID id,
                       UUID skuId,
                       UUID customerId,
                       BigDecimal total,
                       String currency) {
        this.id = id;
        this.skuId = skuId;
        this.customerId = customerId;
        this.total = total;
        this.currency = currency;
    }

    public BigDecimal getTotal() {
        return total;
    }
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

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        BigDecimal total,
        String currency,
        Instant occurredAt
) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Các kiểu trên là mô hình tối giản cho bài học. Trong production cần thêm constraints, validation, idempotency, chính sách cập nhật đơn hàng và migrations. Sử dụng `BigDecimal` cùng scale có mục đích để minh họa assertion chính xác cho nghiệp vụ tiền.

### 5.1. Service orchestration: chỉ hỏi public pricing API

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderPricingPolicy;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.pricing.api.PriceQuoteService;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final PriceQuoteService quotes;
    private final OrderPricingPolicy pricingPolicy;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(PriceQuoteService quotes,
                        OrderPricingPolicy pricingPolicy,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.quotes = quotes;
        this.pricingPolicy = pricingPolicy;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId,
                      UUID skuId,
                      UUID customerId,
                      boolean vipCustomer) {

        var quote = quotes.quoteFor(skuId);
        var total = pricingPolicy.totalFor(
                quote.subtotal(), vipCustomer);

        orders.save(new OrderEntity(
                orderId, skuId, customerId, total, quote.currency()));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, total,
                quote.currency(), Instant.now()));
    }
}
~~~

`OrderService` có bốn collaborator, nhưng chỉ `PriceQuoteService` là **đường gọi sang module `pricing`**. Trong một module test `STANDALONE`, thay public API ấy bằng `@MockitoBean` là lựa chọn dễ kiểm soát. Những dependency khác thuộc hành vi `orders` mà ta muốn xác nhận bằng database/event assertions.

## 6. Module test đúng: mock boundary, giữ implementation thật

`@ApplicationModuleTest` chỉ khởi tạo module chứa test khi dùng `STANDALONE` (mặc định). Vì `PriceQuoteService` có implementation ở module `pricing`, bean thật thường không được tải. Dùng `@MockitoBean` trong Spring Framework 6.2+ để tạo mock bean trong `ApplicationContext` của test:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.pricing.api.PriceQuote;
import com.example.shop.pricing.api.PriceQuoteService;
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
class OrderModuleBehaviorTests {

    @Autowired OrderService service;           // Bean thật.
    @Autowired OrderRepository repository;     // Repository thật.

    // Ranh giới module: API pricing được thay bằng mock.
    @MockitoBean PriceQuoteService quotes;

    @Test
    void vipOrderUsesRealDiscountAndPersistsResult(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(quotes.quoteFor(skuId))
                .thenReturn(new PriceQuote(
                        new BigDecimal("100000"), "VND"));

        service.place(orderId, skuId, customerId, true);

        // Verify đúng call vượt boundary.
        verify(quotes).quoteFor(skuId);

        // Chính business policy + JPA repository nội bộ chạy thật.
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order ->
                        assertThat(order.getTotal())
                                .isEqualByComparingTo("90000.00"));

        // Spring publisher thật: kiểm tra event được phát.
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event ->
                        assertThat(event.total())
                                .isEqualByComparingTo("90000.00"));
    }
}
~~~

**Giá trị của test:** nếu developer đổi `VIP_FACTOR` thành `0.80`, hoặc `OrderService` lưu subtotal thay vì total, assertion database/event sẽ thất bại. Mock `PriceQuoteService` không che lỗi đó, vì chúng thuộc **hành vi module orders** đang chạy thật.

Điều kiện thực thi: dự án có Spring Boot, Spring Modulith test starter, JPA, datasource/transaction manager và schema phù hợp. Test không gắn `@Transactional` bao ngoài nếu muốn service có transaction và commit riêng. Không đặt test ở package root chung khiến `@ApplicationModuleTest` xác định sai module.

### 6.1. Thử khách thường, input lỗi và failure từ boundary

Trong cùng test class, bổ sung:

~~~java
@Test
void regularOrderKeepsFullPrice(PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID skuId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(quotes.quoteFor(skuId))
            .thenReturn(new PriceQuote(
                    new BigDecimal("100000"), "VND"));

    service.place(orderId, skuId, customerId, false);

    assertThat(repository.findById(orderId))
            .get()
            .satisfies(order ->
                    assertThat(order.getTotal())
                            .isEqualByComparingTo("100000.00"));
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .hasSize(1);
}

@Test
void invalidQuoteDoesNotCreateOrderOrEvent(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID skuId = UUID.randomUUID();

    when(quotes.quoteFor(skuId))
            .thenReturn(new PriceQuote(BigDecimal.ZERO, "VND"));

    assertThatThrownBy(() -> service.place(
                orderId, skuId, UUID.randomUUID(), true))
            .isInstanceOf(IllegalArgumentException.class);

    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}

@Test
void quoteProviderFailureDoesNotCreateOrder(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID skuId = UUID.randomUUID();

    when(quotes.quoteFor(skuId))
            .thenThrow(new IllegalStateException(
                    "Pricing temporarily unavailable"));

    assertThatThrownBy(() -> service.place(
                orderId, skuId, UUID.randomUUID(), false))
            .isInstanceOf(IllegalStateException.class);

    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Các snippet thuộc cùng lớp `OrderModuleBehaviorTests` và cần thêm import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

**Vì sao được phép assert `PublishedEvents` rỗng ở đường lỗi này?** Trong mẫu `OrderService`, exception xảy ra **trước khi** lời gọi `publisher.publishEvent` diễn ra. Nếu code phát event rồi mới ném exception/rollback, `PublishedEvents` vẫn có thể quan sát event đã được phát; phải kiểm tra `AFTER_COMMIT` và database/registry riêng.

### 6.2. Interaction assertion chỉ nên tập trung vào contract ngoài

~~~java
verify(quotes).quoteFor(skuId);
~~~

Lời gọi trên thể hiện hợp đồng đồng bộ: `orders` phải lấy quote đúng SKU. Nhưng `verify(...)` **không thay thế** các assertions về số tiền, dữ liệu database và event.

Không cần verify từng lời gọi:

~~~java
verify(pricingPolicy).totalFor(...);
verify(repository).save(...);
verify(publisher).publishEvent(...);
~~~

trong bài test module có implementation thật, bởi các phép verify chi tiết đó dễ vỡ khi refactor và không chứng minh dữ liệu cuối cùng đúng. Chỉ dùng chúng khi **tương tác chính là điều cần bảo vệ**, ví dụ API bên ngoài không được gọi khi lệnh bị từ chối.

## 7. Bài test tưởng đúng: mock implementation detail và tự chứng minh điều đã stub

Hãy xem một phiên bản test chống-pattern:

~~~java
@ApplicationModuleTest
class FragileOrderTests {

    @Autowired OrderService service;

    @MockitoBean PriceQuoteService quotes;

    // Sai mục tiêu: business pricing policy của chính orders bị thay.
    @MockitoBean OrderPricingPolicy policy;

    @Test
    void vipOrderHasDiscount() {
        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();

        when(quotes.quoteFor(skuId))
                .thenReturn(new PriceQuote(
                        new BigDecimal("100000"), "VND"));
        when(policy.totalFor(
                new BigDecimal("100000"), true))
                .thenReturn(new BigDecimal("90000.00"));

        service.place(orderId, skuId, UUID.randomUUID(), true);

        verify(policy).totalFor(new BigDecimal("100000"), true);
    }
}
~~~

Test này có thể xanh ngay cả khi code thật `OrderPricingPolicy` đã đổi sai hệ số giảm giá. Nó chỉ xác nhận `OrderService` **gọi mock policy**, không xác nhận chính sách tính giá thật và không assert dữ liệu đã lưu.

### 7.1. Minh họa mutation bị bỏ lọt

Giả sử implementation thật đổi sai:

~~~java
private static final BigDecimal VIP_FACTOR =
        new BigDecimal("0.80"); // BUG: giảm 20%, thay vì 10%.
~~~

| Thiết kế test | Lỗi có bị phát hiện? | Vì sao? |
| --- | --- | --- |
| Stub `policy.totalFor(...)` trả `90000`, rồi chỉ verify method call. | **Không**. | Method thật của policy không chạy. |
| Chạy `OrderPricingPolicy` thật, assert DB total = `90000`. | **Có**. | Tiền được tính bằng code thật đã thay đổi. |
| Unit test thuần của policy, assert giảm 10%. | **Có**. | Trực tiếp kiểm chứng business invariant. |
| Mock `OrderRepository` rồi chỉ verify `save(any())`. | Chưa chắc. | Không bảo vệ schema/transaction và giá trị cuối cùng của row. |

**Mock implementation detail có thể làm coverage cao nhưng giá trị bảo vệ thấp.** Một lời gọi tới method mock vẫn tăng coverage của orchestration, nhưng không đi qua logic thật của collaborator.

### 7.2. Refactor vô hại cũng làm test dễ vỡ

Giả sử team nhập `OrderPricingPolicy` vào một service khác hoặc đổi cách tính mà vẫn cho ra **cùng total**. Test verify `policy.totalFor(...)` sẽ hỏng mặc dù hành vi người dùng đúng. Đây là dấu hiệu test đang bảo vệ **cách làm** thay vì **kết quả công khai**.

Nhận diện nhanh test quá chi tiết qua các dấu hiệu:

- Có nhiều `verify` cho từng method nội bộ nhưng ít assertion về kết quả.
- Cứ tách/gộp method là phải sửa một loạt test.
- Stub trả về đúng giá trị mà test sau đó assert, tạo thành “vòng tự chứng minh”.
- Mọi dependency của service đều bị mock, kể cả domain rules và publisher khi test muốn có event.

## 8. Nhưng repository không phải lúc nào cũng cần giữ thật

Cần tránh cực đoan: “không bao giờ mock repository” **không đúng**.

### 8.1. Unit test đơn vị OrderService

Nếu test chỉ kiểm tra việc orchestration gọi các port, không cần Spring context và database, có thể mock cả repository:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.internal.OrderPricingPolicy;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.pricing.api.PriceQuote;
import com.example.shop.pricing.api.PriceQuoteService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.math.BigDecimal;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock PriceQuoteService quotes;
    @Mock OrderRepository repository;
    @Mock ApplicationEventPublisher publisher;

    // Giữ policy thật dù unit test có mock repository.
    private final OrderPricingPolicy policy =
            new OrderPricingPolicy();

    @Test
    void sendsExpectedWorkToPorts() {
        UUID skuId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        when(quotes.quoteFor(skuId))
                .thenReturn(new PriceQuote(
                        new BigDecimal("100000"), "VND"));

        OrderService service = new OrderService(
                quotes, policy, repository, publisher);

        service.place(orderId, skuId, UUID.randomUUID(), true);

        verify(quotes).quoteFor(skuId);
        verify(repository).save(any());
        verify(publisher).publishEvent(any(Object.class));
    }
}
~~~

Đây là **unit test không có Spring**, nên `@Transactional` không được áp dụng qua Spring proxy; `repository` và `publisher` đều là mock. Kết quả của test chỉ phản ánh lời gọi giữa các object, **không chứng minh DB commit hoặc application event được phân phối**.

Muốn kiểm tra giá trị `OrderEntity` truyền vào repository trong unit test, có thể dùng `ArgumentCaptor<OrderEntity>`. Tuy nhiên, module integration test với repository thật và query trạng thái sau commit vẫn cần thiết khi muốn bảo vệ JPA mapping và dữ liệu bền vững.

### 8.2. Boundary là khái niệm tương đối theo test scope

| Cùng một dependency | Unit test service | Module integration test |
| --- | --- | --- |
| `PriceQuoteService` ngoài module | Mock để điều khiển input. | Mock ở public module boundary. |
| `OrderPricingPolicy` nội bộ | Thường giữ thật; cũng có thể kiểm thử riêng policy. | **Giữ thật** để bảo vệ quy tắc giảm giá của module. |
| `OrderRepository` nội bộ | Có thể mock nếu không kiểm tra persistence. | Giữ thật nếu kiểm tra JPA/transaction/data. |
| `ApplicationEventPublisher` | Có thể mock, verify lời gọi publish. | Giữ thật để dùng `PublishedEvents`/listener. |
| HTTP adapter triển khai trong `orders` | Mock port quanh I/O. | Fake server/adapter test riêng nếu cần hợp đồng HTTP thật. |

“Mock boundary hay implementation detail?” vì vậy không thể trả lời chỉ bằng `package-name.startsWith(...)`; hãy bắt đầu từ **assertion và hành vi phải bảo vệ**.

## 9. @ApplicationModuleTest: phạm vi bootstrap quyết định mock cần thiết

Spring Modulith có ba `BootstrapMode` chính:

| Mode | Context nạp | Ý nghĩa của mock |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Module chứa test. | `@MockitoBean` tạo replacement cho API của module ngoài bị loại khỏi scope. |
| `DIRECT_DEPENDENCIES` | Module chứa test và các dependency trực tiếp. | Có thể chạy `pricing` thật; đừng mock API nếu mục tiêu là wiring/contract. |
| `ALL_DEPENDENCIES` | Module chứa test cùng toàn cây dependency. | Test rộng hơn, rủi ro side effect và chi phí bootstrap cao hơn. |

Ví dụ:

~~~java
@ApplicationModuleTest
class IsolatedOrderModuleTests {
    @MockitoBean PriceQuoteService quotes;
}

@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealPricingTests {
    @Autowired PriceQuoteService quotes;
}
~~~

`@ApplicationModuleTest` mặc định **không nạp implementation của `pricing`**, nên mock giúp context của `orders` hoàn chỉnh. Tuy nhiên nếu test định kiểm tra `pricing` trả kết quả chính xác từ bảng giá, việc mock nó sẽ phá mục tiêu test — hãy nạp dependency thật.

### 9.1. Mock không biến một dependency trái luật thành hợp lệ

Giả sử `OrderService` sai cách:

~~~java
import com.example.shop.pricing.internal.PriceTableRepository;

@Service
class OrderService {
    private final PriceTableRepository prices;
}
~~~

`@MockitoBean PriceTableRepository prices` có thể khiến context chạy được, nhưng **không xóa vi phạm module boundary**. Cách sửa đúng là inject `pricing.api.PriceQuoteService`, để implementation của `pricing` quản lý repository của chính nó, và dùng `ApplicationModules.verify()` làm architecture gate.

## 10. @MockitoBean, @Mock, @MockitoSpyBean: ba công cụ khác nhau

### 10.1. @MockitoBean thay một Spring bean trong context

Trong Spring Framework 6.2+ (ví dụ Spring Boot 3.4+):

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
PriceQuoteService quotes;
~~~

`@MockitoBean` mặc định dùng chiến lược `REPLACE_OR_CREATE`: nếu có bean phù hợp, thay bằng mock; nếu không có, tạo bean mock. Điều này đặc biệt phù hợp với `@ApplicationModuleTest(STANDALONE)` khi implementation ngoài module **không nằm trong context**.

### 10.2. @Mock không tự tạo Spring bean

~~~java
import org.mockito.Mock;

@Mock
PriceQuoteService quotes;
~~~

`@Mock` thuộc Mockito; trong unit test với `MockitoExtension` nó tạo mock để class tự dựng bằng constructor hoặc `@InjectMocks`. Nó **không tự đăng ký một bean vào ApplicationContext** mà `@ApplicationModuleTest` đang khởi động. Nếu constructor của `OrderService` thiếu bean, `@Mock` một mình không giải quyết.

### 10.3. @MockitoSpyBean cần bean thật

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
OrderPricingPolicy pricingPolicy;
~~~

`@MockitoSpyBean` dùng chiến lược `WRAP`, yêu cầu có **đúng một bean thật** để wrap. Nó khác mock ở chỗ real method thường được gọi khi chưa stub. Spy policy trong `STANDALONE` có thể hoạt động vì policy thuộc chính module `orders`; tuy nhiên việc dùng spy để verify tất cả lời gọi nội bộ vẫn dễ khiến test phụ thuộc implementation.

Không dùng `@MockitoSpyBean PriceQuoteService` ở `STANDALONE` khi implementation ngoài module không được nạp — **không có đối tượng để wrap**.

### 10.4. Enforce override không áp dụng tùy tiện

~~~java
@MockitoBean(enforceOverride = true)
PriceQuoteService quotes;
~~~

Thuộc tính `enforceOverride = true` yêu cầu bean **đã hiện diện** trước khi mock thay thế. Trong `STANDALONE` không có bean thật của `pricing`, cấu hình này thường làm context fail. Nó phù hợp khi test chủ động yêu cầu một bean đang tồn tại phải được replace, không phải khi cần tạo collaborator giả bị loại khỏi scope.

### 10.5. Lưu ý phiên bản và annotation cũ

`@MockBean` và `@SpyBean` thuộc Spring Boot test đã bị deprecated từ Spring Boot 3.4 để chuyển sang Framework `@MockitoBean`/`@MockitoSpyBean`. Dự án dùng Boot cũ có thể chưa có annotation mới. Không đổi import máy móc trước khi xác nhận dependency.

### 10.6. Qualifier và nhiều bean

Nếu cùng một interface có nhiều bean, lựa chọn theo type có thể mơ hồ. Dùng bean name/qualifier rõ ràng:

~~~java
@MockitoBean(name = "retailPriceQuoteService")
PriceQuoteService retailQuotes;
~~~

Test cũng phải bảo đảm injection point của `OrderService` chọn đúng bean. Tên field của mock đôi khi tham gia cơ chế xác định context cache; giữ qualifier nhất quán để tránh tạo các Spring contexts không cần thiết.

## 11. Khi nào spy có giá trị, và khi nào nó phá test?

Spy là công cụ để quan sát **một real bean**, thường khi cần xác nhận một callback thực sự được gọi nhưng vẫn muốn giữ side effect/logic thật. Trong Spring context:

~~~java
@ApplicationModuleTest
class OrderPolicyObservationTests {

    @Autowired OrderService service;
    @MockitoBean PriceQuoteService quotes;
    @MockitoSpyBean OrderPricingPolicy policy;

    @Test
    void appliesPolicyAndPersistsRealTotal() {
        // Chuẩn bị quote, gọi service ...
        // Assert database total thật.
        // Có thể verify(policy).totalFor(...) nếu đây là hợp đồng cần quan sát.
    }
}
~~~

Đây là **khung test minh họa**; không tự chạy khi chưa có fixture, repository và import. `@MockitoSpyBean` bảo đảm policy thật được gọi, nhưng test tốt vẫn phải assert total từ database hoặc event.

### 11.1. Tránh khi(spy.call()) nếu method thật có side effect

Mockito spy thường gọi method thật trong:

~~~java
when(policy.totalFor(new BigDecimal("100000"), true))
        .thenReturn(new BigDecimal("90000.00"));
~~~

Cách stubbing này có thể gọi method thật **ngay lúc setup**, gây exception hoặc side effect nếu method truy cập database/HTTP. Khi cố ý stub spy mà không muốn method thật chạy lúc stubbing, dùng:

~~~java
doReturn(new BigDecimal("90000.00"))
        .when(policy)
        .totalFor(new BigDecimal("100000"), true);
~~~

Nhưng trong bài test **bảo vệ policy**, ngay cả `doReturn` cũng có thể làm test mất ý nghĩa vì real policy không thực hiện logic đó. Chỉ stub spy khi test nhằm kiểm tra **một hành vi khác**, và document rõ vì sao việc chặn real method là an toàn.

### 11.2. Spring AOP proxy cần thận trọng

`@MockitoBean` thay bean bằng bare mock, không giữ AOP advice của bean gốc như `@Transactional`, `@Cacheable` hoặc `@Retryable`. `@MockitoSpyBean` wrap real bean và proxy advice có thể vẫn hoạt động; cách stub qua proxy cần cân nhắc. Không dùng kết quả của một mock thay bean có `@Transactional` để chứng minh transaction propagation thực.

**Spy không đồng nghĩa an toàn hơn mock.** Spy có thể chạy HTTP call và ghi database thật. Nếu mục tiêu là ngăn side effect ngoài hệ thống trong module test, fake một port có thể phù hợp hơn.

## 12. Bảo vệ event publication: không mock publisher khi muốn quan sát event thật

Trong ví dụ `OrderService.place(...)`, `ApplicationEventPublisher` là một dependency nhưng cũng là **cơ chế Spring event thật** mà bài module test muốn kiểm chứng.

Trong unit test, có thể:

~~~java
@Mock ApplicationEventPublisher publisher;
verify(publisher).publishEvent(any(OrderPlaced.class));
~~~

Kết quả chỉ cho biết method publish được gọi. Với `@ApplicationModuleTest`, thay publisher bằng `@MockitoBean` thường khiến `PublishedEvents` không còn quan sát event qua infrastructure thật.

Thay vào đó:

~~~java
@Test
void publishesExactlyOneEvent(PublishedEvents events) {
    // setup quote mock, orderId riêng
    service.place(orderId, skuId, customerId, true);

    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .hasSize(1);
}
~~~

Đây là snippet thuộc lớp module test và cần fixture/stubbing trước lời gọi. Khi receiver ở module khác dùng `@ApplicationModuleListener`, `PublishedEvents` **không tự chứng minh listener đã được gọi hoặc hoàn tất**.

### 12.1. Receiver là một module khác: thường không cần mock trong producer test

Nếu `notifications` lắng nghe `OrderPlaced`:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    emailSender.sendConfirmation(event.orderId());
}
~~~

Module `orders` không inject `notifications.EmailListener` trực tiếp; nó chỉ phát `OrderPlaced`. Trong `@ApplicationModuleTest(STANDALONE)` của `orders`, listener ngoài module thường không được bootstrap — **không cần mock listener** chỉ để khởi động producer.

Khi muốn kiểm tra listener thật, dùng test thuộc `notifications` hoặc integration test có module nhận, transaction commit thật và có điều kiện chờ cho async. Có thể mock **external EmailSender port** của module `notifications` khi test riêng handler, nhưng phải có contract/integration test cho adapter gửi mail.

### 12.2. Rollback và PublishedEvents

Nếu transaction phát event rồi rollback **sau lệnh `publishEvent`**, `PublishedEvents` vẫn có thể thấy lời gọi phát, trong khi `AFTER_COMMIT` listener không chạy. Mock publisher/verify không phân biệt các trạng thái ấy. Test cần:

- Assertion về dữ liệu nguồn đã rollback.
- Test listener `AFTER_COMMIT` không chạy khi rollback và **chạy ở nhánh commit**.
- Nếu cần durability, integration test Event Publication Registry và storage thật.

## 13. Mock boundary không thay thế contract test của module bị mock

Giả sử `PriceQuoteService.quoteFor(skuId)` có contract:

> Với SKU còn bán, trả subtotal dương và currency hợp lệ. Với SKU bị khóa, ném `SkuUnavailableException`. Không được trả quote của SKU khác.

Trong `orders` module test, ta tự stub:

~~~java
when(quotes.quoteFor(skuId))
        .thenReturn(new PriceQuote(
                new BigDecimal("100000"), "VND"));
~~~

Điều này **không chứng minh** implementation thật của `pricing` trả đúng quote. Nếu implementation trả sai currency, null, hoặc query nhầm giá của sản phẩm, test `orders` vẫn xanh.

Chương trình cần ba lớp kiểm chứng khác nhau:

1. **Consumer-facing module test:** `orders` phản ứng đúng với các kết quả/lỗi mà `PriceQuoteService` contract cho phép.
2. **Provider module test:** `pricing` thực sự trả kết quả đúng khi có dữ liệu bảng giá, SKU khóa và currency tương ứng.
3. **Wiring/integration test:** `orders` dùng implementation thật của `pricing`, không mock chính API cần xác nhận.

### 13.1. Ví dụ integration test với dependency thật

~~~java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersPricingIntegrationTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;
    @Autowired PricingFixture pricingFixture;

    @Test
    void createsOrderUsingRealPriceQuote() {
        UUID skuId = pricingFixture.createSku(
                new BigDecimal("100000"), "VND");
        UUID orderId = UUID.randomUUID();

        service.place(
                orderId, skuId, UUID.randomUUID(), true);

        assertThat(orders.findById(orderId))
                .get()
                .satisfies(order ->
                        assertThat(order.getTotal())
                                .isEqualByComparingTo("90000.00"));
    }
}
~~~

`PricingFixture` là **fixture giả định** phải được cung cấp bằng test configuration phù hợp; snippet không phải một lớp tự chạy trong mọi dự án. Điểm quan trọng là test **không khai báo `@MockitoBean PriceQuoteService`**, vì cần kiểm tra API, implementation và Spring injection thật.

### 13.2. Contract test phát hiện stub quá lạc quan

Khi quote provider có thể:

- trả quote theo currency khác,
- ném exception nếu SKU hết bán,
- trả quote zero do dữ liệu sai,
- trả giá thay đổi theo thời điểm,
- chịu transaction/lock và concurrency,

module consumer test nên có các case phù hợp, nhưng vẫn cần provider test xác nhận implementation thực tuân thủ các kết quả được mô tả. Không để stub xây dựng một “API tưởng tượng” khác production.

## 14. Test doubles: mock, stub, fake, spy và test harness

| Loại | Bản chất | Trường hợp phù hợp |
| --- | --- | --- |
| **Stub** | Trả dữ liệu cố định hoặc cấu hình theo input. | Cho `PriceQuoteService` trả một quote nhất định. |
| **Mock** | Test double có thể kiểm tra các tương tác. | Verify `quoteFor(skuId)` được gọi với đúng SKU. |
| **Fake** | Implementation đơn giản chạy được, ví dụ repository in-memory. | Test nghiệp vụ nhanh mà không cần database thật, **không dùng để chứng minh JPA**. |
| **Spy** | Bao quanh implementation thật, có thể quan sát/stub một số lời gọi. | Theo dõi real callback khi cần, nhưng phải quản lý side effect. |
| **Test harness** | Cơ sở hạ tầng phục vụ test như embedded broker/Testcontainers/WireMock. | Kiểm tra HTTP/protocol/serialization/transaction gần thực tế. |

Mockito cung cấp API cho mock/stub/spy; còn `@MockitoBean` tích hợp việc thay bean vào Spring Test context.

**Đừng chọn công cụ vì quen tay.** Nếu chỉ cần trả về `PriceQuote` cố định, một fake hoặc stub cũng có thể đủ. Nếu cần xác nhận request HTTP serializer/header, mock ở public Java interface sẽ không kiểm chứng tầng wire; nên dùng fake HTTP server hoặc integration test adapter.

## 15. Dấu hiệu over-mocking và coupling quá mức

Một service `CheckoutService` phải inject mười public APIs của mười module khác không tự động sai, nhưng có thể là dấu hiệu module đang gánh quá nhiều trách nhiệm.

Ví dụ test có:

~~~java
@MockitoBean PriceQuoteService pricing;
@MockitoBean CustomerEligibility customers;
@MockitoBean LoyaltyService loyalty;
@MockitoBean EmailNotificationService email;
@MockitoBean ShippingScheduleService shipping;
@MockitoBean InvoiceIssuingService invoice;
~~~

Các kiểu ngoài `PriceQuoteService` ở đây **chỉ minh họa**. Thay vì mock thêm cho đến khi context xanh:

- Hỏi service cần kết quả **đồng bộ** từ module ngoài để quyết định nghiệp vụ hay chỉ muốn thông báo sau commit.
- Nếu chỉ cần side effect như email/loyalty points, cân nhắc phát domain event và `@ApplicationModuleListener`.
- Nếu một API trả quá nhiều dữ liệu, cân nhắc công bố named interface hẹp hơn.
- Nếu business policy bị phân tán qua nhiều module và phải stub từng bước mới test được, xem lại aggregate/application-module boundary.
- Giữ một số integration/contract tests có các module thật để tránh mock che mismatch.

Spring Modulith khuyến nghị rà soát các phụ thuộc ngoài module quá nhiều và xem liệu có thể giảm coupling qua domain events. **Mock nhiều là tín hiệu điều tra, không phải lỗi tự động.**

## 16. Quality gate: kiến trúc phải được kiểm tra độc lập với Mockito

Ngay cả một module test hoàn hảo với `@MockitoBean` cũng không phát hiện đầy đủ lỗi import `pricing.internal` hoặc phụ thuộc vòng. Cần architecture test:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra các quy tắc như không có phụ thuộc vòng ở mức module, không truy cập API nội bộ module khác và tuân thủ `allowedDependencies` khi được khai báo. Nó **không** chứng minh business policy 10% đúng, transaction commit thành công hoặc quote provider trả dữ liệu chính xác.

### 16.1. Test từng tầng theo mục tiêu

| Gate trong CI | Code thật được chạy | Mock/fake hợp lý | Phát hiện lỗi gì? |
| --- | --- | --- | --- |
| **Unit policy test** | `OrderPricingPolicy`. | Không cần. | Thuật toán tiền, rounding, validation. |
| **Unit orchestration test** | `OrderService`. | Quote service, repository, publisher tùy scope. | Nhánh code và đúng tương tác. |
| **Module test `orders`** | Service, policy, JPA, event publisher thật. | `PriceQuoteService` ngoài module. | Giá cuối, DB state, `PublishedEvents`, transaction module. |
| **Provider module test `pricing`** | Quote implementation + pricing repository. | API ngoài hệ thống nếu có. | Giá/trạng thái SKU/currency theo contract. |
| **Direct dependencies test** | `orders` + `pricing` thật. | Chỉ những I/O boundary không thuộc mục tiêu. | Wiring, semantic mismatch và persistence liên module. |
| **Architecture test** | Mô hình dependency tĩnh. | Không dùng Mockito. | Import sai internal, cycle, allowed dependencies. |
| **Event listener test** | Listener của module nhận, transaction. | External gateway theo phạm vi test. | AFTER_COMMIT, registry, idempotency, side effect. |
| **Broker/HTTP integration** | Adapter và giao thức thật. | Testcontainers/fake server. | Serialization, headers, routing, timeout. |

Đặt unit/architecture/module tests trong CI thường xuyên. Integration test dùng database/broker có thể nằm ở stage chuyên biệt nhưng vẫn phải là quality gate cho các thay đổi liên quan contract và persistence.

### 16.2. Không giả vờ rằng test mock đã kiểm thử adapter

Nếu `PriceQuoteService` thật gọi HTTP:

~~~text
orders → pricing.api.PriceQuoteService
       → pricing.internal.HttpPricingClient
       → external Pricing API
~~~

Test `orders` mock public `PriceQuoteService` là hợp lý. Nhưng không thể từ đó kết luận HTTP client gửi đúng Authorization header, parse tiền đúng đơn vị hay retry 503 hợp lý. Những thuộc tính ấy cần **adapter contract/integration test** của `pricing`.

## 17. Tác động của mocks đến transaction, async và trạng thái test

### 17.1. Mock không giữ transaction advice của bean bị thay

Khi Spring Framework `@MockitoBean` replace bean, mock mới không được wrap bởi Spring AOP proxy của original bean. Nếu original bean có `@Transactional` hoặc `@Retryable`, lời gọi vào mock không tự chứng minh những cơ chế đó hoạt động. Để kiểm chứng transaction/retry của collaborator thật, phải chạy bean thật hoặc có integration test riêng.

### 17.2. @Transactional trên test có thể che AFTER_COMMIT

Nếu lớp `@ApplicationModuleTest` được gắn `@Transactional`, Spring Test thường mở transaction bao ngoài và rollback sau mỗi test. `OrderService.place` có thể tham gia transaction đó, khiến listener `AFTER_COMMIT` không chạy khi test chưa commit thật.

Với test cần assert listener:

- Không gắn `@Transactional` bao ngoài một cách vô thức.
- Dùng `TransactionTemplate` hoặc `TestTransaction` khi muốn điều khiển commit/rollback.
- Dùng `Scenario` hoặc Awaitility để chờ async listener theo điều kiện.

Một `verify(mock)` pass ngay sau `service.place` không chứng minh listener sau commit đã chạy.

### 17.3. Reset mock không reset database hay event registry

`@MockitoBean` hỗ trợ reset giữa test methods theo cơ chế Spring Test; tuy nhiên:

- Database records trong datasource test có thể vẫn tồn tại nếu không rollback/dọn fixture.
- Event Publication Registry có thể còn publication từ test khác.
- Async callbacks có thể còn chạy khi test sau bắt đầu.
- Broker offset/message, fake HTTP server state, static cache không tự dọn theo Mockito reset.

Sử dụng ID riêng, fixture cô lập, dọn dữ liệu phù hợp, chờ async completion và quản lý test parallelism. Không lạm dụng `Mockito.reset` thủ công làm mất stubbing đang cần.

### 17.4. Stub chính xác dữ liệu quan trọng

Với boundary `PriceQuoteService`, nên stub:

~~~java
when(quotes.quoteFor(skuId))
        .thenReturn(new PriceQuote(
                new BigDecimal("100000"), "VND"));
~~~

Thay vì:

~~~java
when(quotes.quoteFor(any()))
        .thenReturn(new PriceQuote(
                new BigDecimal("100000"), "VND"));
~~~

nếu chọn **đúng SKU** là một phần của contract. Stub quá rộng khiến bug truyền nhầm SKU vẫn qua test. Kết hợp `verify(quotes).quoteFor(skuId)` khi muốn bảo vệ sự tương tác đó.

## 18. Các anti-pattern và cách sửa

| Anti-pattern | Vì sao nguy hiểm? | Cách cải thiện |
| --- | --- | --- |
| Mock `OrderPricingPolicy` khi đang test giảm giá. | Che lỗi chính sách tính tiền. | Chạy policy thật, assert số tiền cuối. |
| Mock JPA repository trong test tuyên bố kiểm tra persistence. | Không phát hiện schema/transaction/query sai. | Repository và datasource thật trong module/integration test. |
| Mock `ApplicationEventPublisher` rồi khẳng định `PublishedEvents` đúng. | Không chạy luồng event thật. | Giữ publisher thật trong module test. |
| Mock class `pricing.internal` để chữa context không bootstrap. | Che phụ thuộc sai module. | Public API + `ApplicationModules.verify()`. |
| Dùng `@Mock` và tưởng Spring inject. | Mock không là Spring bean. | `@MockitoBean` cho context integration. |
| Dùng `@MockitoSpyBean` khi bean vắng mặt. | Spy cần object thật để wrap. | `@MockitoBean` hoặc nạp dependency thật. |
| `@MockitoBean(enforceOverride=true)` trong `STANDALONE` khi bean ngoài module bị loại. | Bắt buộc bean tồn tại nên context fail. | Dùng replace-or-create mặc định. |
| Verify mọi method nội bộ, không assert kết quả. | Test gắn với implementation detail. | Bảo vệ state/event và contract-facing interaction. |
| Stub trả đúng điều test assert. | Tự chứng minh giả định của test. | Để real implementation tạo kết quả. |
| Mock public API trong **mọi** test, không test provider thật. | Mất kiểm chứng contract/wiring. | Provider module và direct-dependency integration tests. |
| Tăng bootstrap scope để “hết thiếu bean” mọi nơi. | Test nặng và khó cô lập. | Chọn scope theo mục tiêu test, mock public boundary có chủ đích. |

## 19. Bài tập phân loại: boundary hay implementation detail?

Giả sử module `checkout` có `CheckoutService` với các collaborator:

- `cart.internal.CartTotalCalculator`: tính tổng giỏ hàng **bên trong module checkout** (trong ví dụ giả sử `cart.internal` thuộc cùng application module được cấu hình).
- `payments.api.PaymentAuthorization`: public API của module `payments`, trả kết quả approve/decline.
- `checkout.internal.CheckoutRepository`: lưu checkout trong DB.
- `ApplicationEventPublisher`: phát `CheckoutCompleted`.
- `checkout.infrastructure.FraudHttpClient`: gọi dịch vụ fraud bên ngoài qua HTTP.
- `checkout.internal.OrderNumberFormatter`: format mã hiển thị theo quy tắc business.

**Câu hỏi:**

1. Khi viết `@ApplicationModuleTest(STANDALONE)` cho `checkout` để bảo vệ tính tiền và lưu database, nên mock collaborator nào?
2. Tại sao không mock `CartTotalCalculator` và `CheckoutRepository` trong bài test đó?
3. Vì sao `FraudHttpClient` tuy nằm cùng module vẫn có thể cần fake/mock qua port?
4. Nếu chỉ muốn unit test `CheckoutService` không Spring, mock repository có luôn là sai không?
5. Nếu `PaymentAuthorization` thật đổi semantics từ `approved=true` sang một enum mới, test mock hiện tại có tự phát hiện mismatch không?
6. Nếu `PaymentAuthorization` là type trong `payments.internal`, mock nó có giải quyết vi phạm boundary không?
7. Khi cần kiểm tra `CheckoutCompleted` thực sự phát, nên mock `ApplicationEventPublisher` không?
8. Điều gì xảy ra khi dùng `@MockitoSpyBean PaymentAuthorization` mà test `STANDALONE` không tải implementation module payments?

**Đáp án tham khảo:**

1. Mock **public API** `payments.api.PaymentAuthorization` khi chỉ kiểm thử `checkout`. Với HTTP fraud, nên trừu tượng hóa bằng port rõ ràng và fake/mock tại I/O boundary nếu cần cô lập network.
2. Chúng là logic/persistence **thuộc hành vi của module** cần chứng minh. Mock chúng sẽ che sai số và lỗi JPA/transaction.
3. Ranh giới I/O không phụ thuộc package: gọi HTTP thật làm test không ổn định và khó tiêm lỗi; giữ policy thật nhưng thay adapter/port mạng phù hợp.
4. Không. Trong **unit test**, repository là boundary của một đơn vị nhỏ và có thể mock; nhưng không suy ra database hoạt động đúng từ test đó.
5. Không. Stub chỉ thể hiện giả định của test, nên cần provider contract và wiring/integration tests.
6. Không. Vi phạm truy cập package nội bộ vẫn tồn tại; sửa thành public API hoặc event, chạy `ApplicationModules.verify()`.
7. Không trong module test dùng `PublishedEvents`; giữ publisher thật để quan sát event.
8. Spy không thể wrap bean vắng mặt và test context thất bại; dùng mock public boundary hoặc bootstrap implementation thật tùy mục tiêu.

## 20. Checklist trước khi thêm một mock

- [ ] Có câu mô tả **hành vi đang bảo vệ** và kết quả observable mong muốn.
- [ ] Đã xác định scope: unit, module integration, nhiều module, adapter hay end-to-end.
- [ ] Đã xác định dependency là **module boundary**, **I/O boundary** hay **implementation detail**.
- [ ] Nếu mock API ngoài module, nó thuộc public/named interface được `allowedDependencies` cho phép.
- [ ] Không dùng mock để hợp thức hóa import vào package nội bộ của module khác.
- [ ] Các quy tắc nghiệp vụ thuộc module đang test được chạy thật và kiểm tra bằng kết quả.
- [ ] Nếu cần chứng minh persistence/transaction, repository và datasource không bị mock.
- [ ] Nếu cần chứng minh event publish, không mock `ApplicationEventPublisher`.
- [ ] Có test âm tính/lỗi từ boundary, không chỉ happy path với stub lý tưởng.
- [ ] Stub dùng input chính xác khi tham số là một phần hợp đồng.
- [ ] Không dùng `verify` cho mọi lời gọi nội bộ nếu state/outcome đã đủ ý nghĩa.
- [ ] Dùng `@MockitoBean` cho Spring context có phiên bản hỗ trợ; `@Mock` cho unit test thuần.
- [ ] Không dùng `@MockitoSpyBean` khi bean thật không có trong context.
- [ ] Không đặt `enforceOverride=true` khi cần tạo mock cho dependency bị loại khỏi `STANDALONE`.
- [ ] Có test module cung cấp API bị mock và integration/wiring test với implementation thật.
- [ ] Có quality gate `ApplicationModules.verify()` độc lập với Mockito tests.
- [ ] Async, transaction, DB fixture và event publication được kiểm tra bằng công cụ phù hợp, không suy ra từ `verify(mock)`.
- [ ] CI bao phủ unit/domain rules, module behavior, contract/wiring và architecture.

**Kết luận:** Trong Spring Modulith, **mock boundary** là thay thế một collaborator ở bên ngoài phạm vi hành vi đang kiểm tra — thường là public API của module khác hoặc I/O port — để tập trung kiểm chứng module hiện tại. **Mock implementation detail** là thay những lớp thực thi chính behavior mà test cần bảo vệ; cách đó dễ làm test xanh giả và khó refactor. Hãy giữ business rules, database và event infrastructure thật ở đúng cấp module test, bổ sung contract tests cho những collaborator đã mock và luôn dùng `ApplicationModules.verify()` để ranh giới kiến trúc không bị Mockito che khuất.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes, xử lý efferent dependencies bằng mock có chủ đích.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): module APIs, dependency cycle và `allowedDependencies`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event listener, publication registry và transaction behavior.
- [Spring Framework — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): replace-or-create, enforce override, wrap, AOP và qualifier.

> Ghi chú: Các ví dụ được viết theo Spring Framework 6.2+ và Spring Modulith có `@ApplicationModuleTest`; dự án sử dụng Spring Boot cũ có thể cần annotation `@MockBean` tương ứng. Đây là tài liệu biên soạn tại STEP_4, chưa chạy Gradle hoặc vòng Content QA chuyên môn theo quy trình.
