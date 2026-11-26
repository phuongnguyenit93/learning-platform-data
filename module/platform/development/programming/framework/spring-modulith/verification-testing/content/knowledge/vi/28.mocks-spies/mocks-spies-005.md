# Tránh verify thứ tự gọi không được đặc tả

## 1. Khi một bài test đúng cú pháp nhưng sai mục tiêu

Trong Mockito, `InOrder` cho phép xác nhận các lời gọi diễn ra theo một thứ tự nhất định. Ví dụ:

~~~java
InOrder inOrder = inOrder(pricing, customers);
inOrder.verify(pricing).quoteFor(skuId);
inOrder.verify(customers).canPlaceOrder(customerId);
~~~

Đoạn mã kiểm tra rằng lời gọi báo giá xảy ra trước lời gọi kiểm tra khách hàng. Nhưng hãy đặt câu hỏi: **nghiệp vụ có yêu cầu thứ tự đó không?** Nếu hai thao tác độc lập, và dù chạy theo thứ tự nào thì đơn hàng vẫn có giá đúng, khách hàng vẫn hợp lệ, dữ liệu vẫn được lưu và `OrderPlaced` vẫn được phát, bài test đã thêm một ràng buộc không có trong hợp đồng.

Hậu quả thường thấy:

- Một refactor vô hại — đổi chỗ hai lời gọi độc lập — làm test thất bại.
- Developer phải sửa test mặc dù không có lỗi nghiệp vụ.
- Test cản trở tối ưu hóa, thực thi song song hoặc cache.
- Số lượng lời gọi được kiểm tra nhiều nhưng dữ liệu cuối cùng và sự kiện lại ít được assert.
- CI có false alarm, gây tốn thời gian và làm giảm niềm tin vào những kiểm tra thực sự quan trọng.

**Nguyên tắc:** Chỉ verify thứ tự khi **thứ tự là một phần hợp đồng được mô tả rõ**: quy tắc nghiệp vụ, bảo mật, giao thức hoặc ràng buộc dữ liệu. Nếu hợp đồng chỉ yêu cầu các tác vụ được thực hiện và kết quả đúng, hãy kiểm tra **đúng lời gọi cần thiết + trạng thái cuối**, không ép buộc một thứ tự ngẫu nhiên của implementation.

Bài thuộc chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Học phần giúp kiểm chứng ranh giới kiến trúc Spring Modulith bằng `ApplicationModules`, các quy tắc phụ thuộc module, `@ApplicationModuleTest`, kiểm thử sự kiện/database/tích hợp và quality gate CI. Trong bối cảnh đó, thứ tự giữa hai **collaborator ngoài module** và thứ tự thực thi bên trong một module cần được phân biệt cẩn thận.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **thứ tự được đặc tả**, **thứ tự ngẫu nhiên của code** và **thứ tự không bảo đảm vì xử lý bất đồng bộ**.
2. Giải thích cách `Mockito.inOrder(...)` và `InOrder.verify(...)` hoạt động và giới hạn của chúng.
3. Viết `@ApplicationModuleTest(STANDALONE)` dùng `@MockitoBean` ở public boundary nhưng **không over-verify** thứ tự các lời gọi độc lập.
4. Kết hợp Mockito interaction checks với JPA state, `PublishedEvents` và kiểm thử lỗi nghiệp vụ.
5. Chỉ sử dụng `InOrder` cho các trường hợp như **kiểm tra quyền trước khi thực hiện side effect** hoặc thứ tự bước được quy định bởi protocol.
6. Hiểu **partial order** (một số bước phải trước bước khác) khác với ép **total order** (mọi bước phải nối tiếp).
7. Tránh dùng thứ tự invocation để khẳng định transaction commit, callback `AFTER_COMMIT`, thứ tự broker hoặc exactly-once side effect.
8. Bổ sung architecture test, provider contract test, integration test và quality gate CI phù hợp.

## 2. Ba loại thứ tự cần phân biệt

| Loại | Mô tả | Có nên verify bằng InOrder? |
| --- | --- | --- |
| **Thứ tự bắt buộc theo hợp đồng** | Bắt buộc kiểm tra quyền/consent trước khi gọi gateway có side effect; protocol yêu cầu `begin → send → ack`. | **Có thể**, tại đúng boundary; còn cần kiểm tra kết quả. |
| **Thứ tự triển khai không được đặc tả** | Kiểm tra khách hàng rồi lấy giá, hoặc lấy giá rồi kiểm tra khách hàng, khi hai thao tác độc lập. | **Không**. Verify arguments và assert outcome. |
| **Thứ tự chạy không có cam kết** | Hai `@ApplicationModuleListener` bất đồng bộ cùng nhận event, hoặc nhiều worker/retry trên broker. | **Không suy ra từ InOrder**; cần thiết kế sequencing/ordering nếu nghiệp vụ yêu cầu. |

Ví dụ cùng một kết quả:

~~~text
Phương án A:
  pricing.quoteFor(SKU)
  customers.canPlaceOrder(customer)
  orders.save(order)
  publishEvent(OrderPlaced)

Phương án B:
  customers.canPlaceOrder(customer)
  pricing.quoteFor(SKU)
  orders.save(order)
  publishEvent(OrderPlaced)

Hợp đồng (nếu hai lookup độc lập):
  - đúng SKU được báo giá
  - đúng customer được xác minh
  - chỉ lưu và phát event khi đủ điều kiện
  - số tiền cuối cùng chính xác
  - KHÔNG quy định hai lookup nào bắt đầu trước
~~~

Một test yêu cầu phương án A có thể thất bại với phương án B, dù cả hai đáp ứng toàn bộ hợp đồng đã nêu.

### 2.1. “Không có quy định” khác với “mọi thứ đều có thể xảy ra”

Không verify thứ tự giữa **hai lookup** không có nghĩa bỏ qua quy tắc **chỉ lưu order khi đã xác minh điều kiện**. Những quan hệ nhân quả thật sự vẫn quan trọng:

- Không chấp nhận kết quả `DENIED` rồi lưu order.
- Không phát `OrderPlaced` cho một transaction đã rollback khi kiểm tra side effect sau commit.
- Không charge trước khi biết khách có quyền thanh toán.

Hãy chọn assertion thể hiện chính xác quan hệ ấy. Nhiều khi **assert không có row/event sau lỗi** mạnh hơn việc verify một dãy method calls của các helper nội bộ.

## 3. Mockito InOrder thực sự đo điều gì?

Mockito cho phép:

~~~java
InOrder order = inOrder(mockA, mockB);

order.verify(mockA).firstAction();
order.verify(mockB).secondAction();
~~~

Nó kiểm tra **thứ tự những invocation Mockito ghi nhận trên các mock được truyền vào**, không kiểm tra toàn bộ tiến trình nghiệp vụ ở mọi thành phần. Các điểm dễ bỏ qua:

1. `order.verify(...)` chỉ quan sát **mock/spy** có trong `InOrder`, không tự quan sát database, transaction, broker hay một service thật không được spy.
2. Mockito hỗ trợ xác minh **một phần chuỗi invocation**: nếu không yêu cầu kiểm tra hết, các lời gọi khác có thể tồn tại.
3. `order.verifyNoMoreInteractions()` có semantics riêng về các tương tác chưa được kiểm chứng theo thứ tự; không phải bằng chứng “toàn hệ thống không còn công việc”.
4. Một lời gọi trên mock thành công không đồng nghĩa network request được broker/provider xử lý thành công.
5. Nếu một callback chạy ở thread khác, thứ tự quan sát bị ảnh hưởng scheduling; test có thể flaky dù nghiệp vụ không sai.

### 3.1. Ví dụ đơn giản về thứ tự

~~~java
Gateway gateway = mock(Gateway.class);
Audit audit = mock(Audit.class);

gateway.prepare();
audit.recordPreparation();
gateway.submit();

InOrder order = inOrder(gateway, audit);
order.verify(gateway).prepare();
order.verify(audit).recordPreparation();
order.verify(gateway).submit();
~~~

Đây chỉ là ví dụ cú pháp; cần khai báo `Gateway` và `Audit` thích hợp trong unit test. **Không đưa `InOrder` vào test chỉ vì ba method hiện đang được viết theo ba dòng này.** Trước tiên hãy có một điều khoản hợp đồng giải thích tại sao audit phải nằm giữa prepare và submit.

## 4. Thiết kế ví dụ Spring Modulith theo ranh giới thực

Giả sử `ShopApplication` ở `com.example.shop`. Hai module cung cấp API được module `orders` sử dụng:

- `pricing` cung cấp `PriceQuoteService.quoteFor(skuId)`.
- `customers` cung cấp `CustomerEligibility.canPlaceOrder(customerId)`.
- `orders` dùng kết quả để lưu order và phát `OrderPlaced`.

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
│       └── PriceRepository.java
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
    ├── internal
    │   ├── OrderEntity.java
    │   └── OrderRepository.java
    └── events
        ├── OrderPlaced.java
        └── package-info.java
~~~

Mô hình dependency mong muốn:

~~~mermaid
flowchart LR
    O["orders.OrderService"] --> P["pricing.api.PriceQuoteService"]
    O --> C["customers.api.CustomerEligibility"]
    O --> R["orders.internal.OrderRepository"]
    O --> E["ApplicationEventPublisher"]
    T["@ApplicationModuleTest orders"] -.->|"@MockitoBean"| P
    T -.->|"@MockitoBean"| C
    T --> O
    R --> DB[("Database test")]
    E --> EV["PublishedEvents"]
~~~

Trong `STANDALONE`, module `orders` chạy thật; các bean implementation thuộc `pricing` và `customers` không được bootstrap, nên ta thay **public interface** của chúng bằng mock. Đây là lý do kiểm thử module giữ được sự cô lập mà không phải mock chính `OrderService`, database hoặc publisher.

### 4.1. Định nghĩa public API

File `pricing/api/PriceQuote.java`:

~~~java
package com.example.shop.pricing.api;

import java.math.BigDecimal;
import java.util.Objects;

public record PriceQuote(BigDecimal amount, String currency) {
    public PriceQuote {
        Objects.requireNonNull(amount);
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

`orders` chỉ import hai API công khai; không biết tên class implementation, repository hoặc schema của các module ngoài.

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "pricing :: api",
        "customers :: api"
    }
)
package com.example.shop.orders;
~~~

Các tên này là các application module được phát hiện theo package con trực tiếp trong ví dụ; ở một dự án có chiến lược phát hiện khác, cần đối chiếu mô hình module thực tế.

## 5. Business code: hai lookup độc lập, một quyết định cuối cùng

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

@Entity
public class OrderEntity {

    @Id
    private UUID id;
    private UUID customerId;
    private UUID skuId;

    @Column(precision = 19, scale = 2, nullable = false)
    private BigDecimal total;

    private String currency;

    protected OrderEntity() {}

    public OrderEntity(UUID id, UUID customerId,
                       UUID skuId, BigDecimal total,
                       String currency) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.skuId = Objects.requireNonNull(skuId);
        this.total = Objects.requireNonNull(total);
        this.currency = Objects.requireNonNull(currency);
    }

    public UUID getCustomerId() { return customerId; }
    public UUID getSkuId() { return skuId; }
    public BigDecimal getTotal() { return total; }
    public String getCurrency() { return currency; }
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
        UUID customerId,
        BigDecimal amount,
        String currency,
        Instant occurredAt
) {}
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

### 5.1. OrderService triển khai theo thứ tự A — báo giá rồi kiểm tra khách

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.pricing.api.PriceQuoteService;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final PriceQuoteService pricing;
    private final CustomerEligibility customers;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(PriceQuoteService pricing,
                        CustomerEligibility customers,
                        OrderRepository orders,
                        ApplicationEventPublisher events) {
        this.pricing = pricing;
        this.customers = customers;
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId, UUID skuId, UUID customerId) {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(skuId);
        Objects.requireNonNull(customerId);

        // Hai lookup có thể hoán đổi thứ tự theo contract ví dụ.
        var quote = pricing.quoteFor(skuId);
        boolean eligible = customers.canPlaceOrder(customerId);

        if (!eligible) {
            throw new OrderRejectedException();
        }
        if (quote == null || quote.amount().signum() <= 0) {
            throw new IllegalArgumentException("Invalid price quote");
        }

        orders.save(new OrderEntity(
                orderId, customerId, skuId,
                quote.amount(), quote.currency()));

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, customerId,
                quote.amount(), quote.currency(), Instant.now()));
    }
}
~~~

Ví dụ cố ý không quy định **pricing trước customers** hay ngược lại: hai collaborator độc lập, không tạo side effect tính phí trong mô hình này. Hợp đồng của use case chỉ yêu cầu một order hợp lệ khi cả giá và eligibility hợp lệ.

Nếu `PriceQuoteService` tính phí mỗi lần gọi, có hạn mức, trả giá biến động theo thời điểm hoặc chỉ được gọi sau consent, **thứ tự có thể trở thành một phần hợp đồng thật**. Khi ấy cần bổ sung quy tắc ấy trước khi viết verification. Không suy từ tên API rằng mọi thứ tự đều vô hại.

### 5.2. Phương án B — đổi chỗ hai lookup, nhưng giữ nguyên hành vi

Một refactor có thể thay phần đầu method bằng:

~~~java
boolean eligible = customers.canPlaceOrder(customerId);
var quote = pricing.quoteFor(skuId);

if (!eligible) {
    throw new OrderRejectedException();
}
if (quote == null || quote.amount().signum() <= 0) {
    throw new IllegalArgumentException("Invalid price quote");
}

// Phần save + publish còn lại giữ nguyên.
~~~

Đây là **đoạn thay thế**, không phải method thứ hai cùng tồn tại trong production. Nếu cả hai lookup trả kết quả hợp lệ, dữ liệu cuối cùng và event không thay đổi. Test kiểm tra đúng hợp đồng phải **pass với cả hai phương án**.

Với nhánh lỗi, lựa chọn thứ tự có thể làm khác số lần gọi collaborator hoặc exception nào xuất hiện trước. Điều này chỉ có thể coi là tương đương nếu contract **không cam kết thứ tự/lỗi ưu tiên** và không có side effect bị cấm. Những yếu tố đó cần được đánh giá trong thiết kế use case, không bỏ qua một cách tùy tiện.

## 6. Test không tốt: InOrder đóng băng một chi tiết triển khai

~~~java
@Test
void fragileOrderVerification() {
    UUID skuId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID orderId = UUID.randomUUID();

    when(pricing.quoteFor(skuId))
            .thenReturn(new PriceQuote(
                    new BigDecimal("100000.00"), "VND"));
    when(customers.canPlaceOrder(customerId))
            .thenReturn(true);

    service.place(orderId, skuId, customerId);

    InOrder sequence = inOrder(pricing, customers);
    sequence.verify(pricing).quoteFor(skuId);
    sequence.verify(customers).canPlaceOrder(customerId);
}
~~~

Trong một module test đã có các bean/fixture tương ứng, test này sẽ **pass với phương án A** và **fail với phương án B**, dù cả hai có thể đáp ứng hợp đồng đặt hàng. Nếu không có yêu cầu kiểm tra giá trước quyền đặt hàng, câu `sequence.verify(pricing)...` đang biến **implementation detail thành API của test**.

### 6.1. Tác hại khi refactor

Giả sử team tối ưu hệ thống:

- Cho chạy kiểm tra khách hàng trước để từ chối sớm.
- Cache giá và loại bỏ một lời gọi.
- Gộp hai bước vào một application service có trả một kết quả.
- Chạy các lookup song song khi không có phụ thuộc dữ liệu.

Nếu chúng không thay đổi contract và kết quả, test InOrder đang ngăn những refactor hợp lệ. Nhiều test như vậy làm suite trở nên giòn (brittle) và khuyến khích sửa test thay vì đánh giá correctness thực.

### 6.2. Vì sao InOrder pass cũng không đủ?

Ngay cả khi thứ tự hiện tại đúng, InOrder **không khẳng định**:

- `OrderEntity` đã được ghi đúng giá.
- Transaction thực sự commit.
- `OrderPlaced` có đúng `orderId` và amount.
- Không có một call khác tới customer hoặc pricing với sai ID nếu test không kiểm tra.
- Module thật của `customers`/`pricing` tuân thủ contract đã stub.

Một bài test chỉ đếm/so thứ tự các mock có thể pass dù method `orders.save` bị xóa.

## 7. Test nên viết: verify hợp đồng hai API, assert state/event thật

Đặt lớp test trong package `com.example.shop.orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
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

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    // Public collaborators thuộc hai module ngoài orders.
    @MockitoBean PriceQuoteService pricing;
    @MockitoBean CustomerEligibility customers;

    @Test
    void persistsOrderAndPublishesEventWithValidInputs(
            PublishedEvents publishedEvents) {

        UUID orderId = UUID.randomUUID();
        UUID skuId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        var amount = new BigDecimal("100000.00");

        when(pricing.quoteFor(skuId))
                .thenReturn(new PriceQuote(amount, "VND"));
        when(customers.canPlaceOrder(customerId))
                .thenReturn(true);

        service.place(orderId, skuId, customerId);

        // Hợp đồng tham số: đúng SKU, đúng khách.
        verify(pricing).quoteFor(skuId);
        verify(customers).canPlaceOrder(customerId);

        // Không có InOrder: hợp đồng không quy định hai lookup nào trước.
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order -> {
                    assertThat(order.getSkuId()).isEqualTo(skuId);
                    assertThat(order.getCustomerId())
                            .isEqualTo(customerId);
                    assertThat(order.getTotal())
                            .isEqualByComparingTo(amount);
                    assertThat(order.getCurrency()).isEqualTo("VND");
                });

        assertThat(publishedEvents.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId()).isEqualTo(customerId);
                    assertThat(event.amount())
                            .isEqualByComparingTo(amount);
                    assertThat(event.currency()).isEqualTo("VND");
                });
    }
}
~~~

**Giá trị:** test pass với hai cách tổ chức lookup hợp lệ, nhưng vẫn phát hiện bug gọi sai `skuId`, `customerId`, lưu nhầm số tiền hoặc quên phát event.

Đoạn ví dụ giả định dự án đã có Spring Boot, Spring Modulith test dependency, JPA, test datasource, schema và transaction manager. `@MockitoBean` thuộc Spring Framework 6.2+; với Boot cũ cần lựa chọn annotation tương thích. Không gắn `@Transactional` ngoài ý muốn lên test nếu cần service commit riêng khi mở rộng sang listener `AFTER_COMMIT`.

### 7.1. Verify đúng input có khác verify đúng thứ tự không?

Có. Nếu `pricing.quoteFor(otherSkuId)` là bug, `verify(pricing).quoteFor(skuId)` không pass. Đây là **điều khoản dữ liệu** của contract.

Nếu `pricing.quoteFor(skuId)` diễn ra trước hay sau `customers.canPlaceOrder(customerId)` mà kết quả không thay đổi, thêm `InOrder` không tạo thêm độ tin cậy — chỉ tạo một ràng buộc không cần thiết.

### 7.2. Khi số lần gọi là một phần contract

Nếu cả hai API được định nghĩa **chỉ một lần trong mỗi lần thực thi command**, có thể:

~~~java
verify(pricing, times(1)).quoteFor(skuId);
verify(customers, times(1)).canPlaceOrder(customerId);
~~~

Nhưng `verify(mock).method(x)` vốn đã tương đương `times(1)` cho invocation match. Muốn bảo đảm không gọi thêm cùng method với ID khác, cần một assertion rộng hơn hoặc captor, ví dụ:

~~~java
verify(pricing, times(1)).quoteFor(any(UUID.class));
verify(pricing).quoteFor(skuId);
~~~

Không nên tự thêm ràng buộc “đúng một lần” nếu sau này retries/caching hoặc retry policy hợp lệ làm thay đổi số invocation. Bảo đảm “đúng một side effect” là câu hỏi khác với method invocation count.

## 8. Nhánh bị từ chối: điều gì cần kiểm chứng?

Khi `customers.canPlaceOrder` trả `false`, hợp đồng đặt hàng yêu cầu **không lưu và không phát sự kiện**. Nó không nhất thiết yêu cầu **không gọi pricing**, bởi hợp đồng ví dụ chưa quy định thứ tự hai lookup.

Trong cùng lớp `OrderModuleBehaviorTests`:

~~~java
@Test
void rejectedCustomerDoesNotCreateOrderOrEvent(
        PublishedEvents publishedEvents) {

    UUID orderId = UUID.randomUUID();
    UUID skuId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    // Không stub pricing: test này không yêu cầu pricing phải
    // được gọi hay phải chạy trước/sau kiểm tra khách hàng.
    when(customers.canPlaceOrder(customerId))
            .thenReturn(false);

    assertThatThrownBy(() ->
            service.place(orderId, skuId, customerId))
            .isInstanceOf(OrderRejectedException.class);

    verify(customers).canPlaceOrder(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(publishedEvents.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Thêm import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

**Không cần** `InOrder` giữa price và eligibility. Và cũng **không nên** thêm `verify(pricing, never()).quoteFor(...)` nếu chưa đặc tả rằng một khách bị từ chối **phải tránh mọi báo giá**. Với implementation A, lời gọi báo giá có thể xảy ra hợp lệ trước khi nhận kết quả `false`.

Nếu báo giá thực sự tốn phí, hoặc có yêu cầu quyền riêng tư “chỉ được hỏi giá sau khi xác minh khách”, hãy nâng điều kiện đó thành **hợp đồng công khai** rồi thay cả implementation lẫn test tương ứng. Không để assertion ngầm tự quyết định chính sách.

### 8.1. Khi không được gọi collaborator: never hoặc verifyNoInteractions

Một case khác: input `orderId` null cần bị từ chối **trước mọi I/O**. Khi đó negative interaction chính là yêu cầu:

~~~java
@Test
void nullOrderIdDoesNotCallExternalModules(
        PublishedEvents publishedEvents) {

    UUID skuId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    assertThatThrownBy(() ->
            service.place(null, skuId, customerId))
            .isInstanceOf(NullPointerException.class);

    verifyNoInteractions(pricing, customers);
    assertThat(publishedEvents.ofType(OrderPlaced.class)).isEmpty();
}
~~~

Test này giả định dữ liệu các test khác đã được cô lập và mock được reset phù hợp. `verifyNoInteractions` kiểm tra cả hai mock **tại thời điểm assertion**; không có nghĩa bảo đảm sẽ không bao giờ có một callback async về sau. Với phương thức đồng bộ của ví dụ, đây là phép kiểm chứng hợp đồng rõ ràng.

## 9. Khi nào InOrder là cần thiết: kiểm tra quyền trước side effect

Không nên cực đoan “không bao giờ dùng InOrder”. Giả sử hệ thống có một lệnh **thực hiện tác động không thể tự đảo ngược**: chuyển tiền, phát thông điệp marketing, mở khóa tài nguyên nhạy cảm hoặc gửi lệnh giao dịch cho đối tác. Hợp đồng yêu cầu **kiểm tra quyền trước khi kích hoạt side effect**.

Ví dụ hai port:

~~~java
interface AuthorizationPort {
    void requireAllowed(UUID actorId, UUID paymentId);
}

interface CapturePort {
    void capture(UUID paymentId, UUID idempotencyKey);
}

final class PaymentCaptureWorkflow {

    private final AuthorizationPort authorization;
    private final CapturePort captures;

    PaymentCaptureWorkflow(AuthorizationPort authorization,
                           CapturePort captures) {
        this.authorization = authorization;
        this.captures = captures;
    }

    void capture(UUID actorId, UUID paymentId) {
        authorization.requireAllowed(actorId, paymentId);
        captures.capture(paymentId, paymentId);
    }
}
~~~

Trong ví dụ này, **thứ tự là contract**: không được capture khi chưa kiểm tra quyền. Test unit:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import java.util.UUID;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;

class PaymentCaptureWorkflowTests {

    @Test
    void authorizesBeforeCapturing() {
        var authorization = mock(AuthorizationPort.class);
        var capture = mock(CapturePort.class);
        var workflow = new PaymentCaptureWorkflow(
                authorization, capture);

        UUID actorId = UUID.randomUUID();
        UUID paymentId = UUID.randomUUID();

        workflow.capture(actorId, paymentId);

        InOrder sequence = inOrder(authorization, capture);
        sequence.verify(authorization)
                .requireAllowed(actorId, paymentId);
        sequence.verify(capture)
                .capture(paymentId, paymentId);
    }
}
~~~

**Vì sao hợp lý?** Đổi `capture(...)` lên trước `requireAllowed(...)` làm vi phạm một điều khoản nghiệp vụ/bảo mật, dù code vẫn biên dịch. InOrder phát hiện chính xác lỗi ấy.

### 9.1. Kết hợp test lỗi quyền

Một test bổ sung nên yêu cầu khi authorization từ chối, gateway **không được gọi**:

~~~java
@Test
void deniedAuthorizationNeverCaptures() {
    var authorization = mock(AuthorizationPort.class);
    var capture = mock(CapturePort.class);
    var workflow = new PaymentCaptureWorkflow(
            authorization, capture);

    UUID actorId = UUID.randomUUID();
    UUID paymentId = UUID.randomUUID();

    doThrow(new SecurityException("Not allowed"))
            .when(authorization)
            .requireAllowed(actorId, paymentId);

    assertThatThrownBy(() ->
            workflow.capture(actorId, paymentId))
            .isInstanceOf(SecurityException.class);

    verify(authorization).requireAllowed(actorId, paymentId);
    verifyNoInteractions(capture);
}
~~~

Đây là snippet đặt trong cùng test class cùng imports AssertJ/Mockito. Test này **không cần InOrder**: xác minh authorization đã xảy ra, còn capture tuyệt đối không xảy ra là điều khoản mạnh hơn kiểm tra thứ tự trên nhánh lỗi.

**Giới hạn:** InOrder chỉ chứng minh thứ tự lời gọi hai Java ports trong process. Nó không chứng minh authorization server đã commit dữ liệu, hoặc payment provider chỉ charge đúng một lần. Các hiệu ứng đó cần contract/integration/idempotency tests.

## 10. Partial order khác total order

Một workflow có ba bước:

- A: kiểm tra quyền.
- B: kiểm tra giới hạn giao dịch.
- C: thực hiện giao dịch.

Hợp đồng có thể là **A và B phải xong trước C**, nhưng **A không bắt buộc trước B**. Đây là một **partial order**:

~~~mermaid
flowchart TD
    A["Authorization approved"] --> C["Capture"]
    B["Limit check passed"] --> C
~~~

Không nên viết:

~~~java
InOrder order = inOrder(authorization, limits, capture);
order.verify(authorization).check(...);
order.verify(limits).check(...);
order.verify(capture).capture(...);
~~~

nếu bản đặc tả không yêu cầu `authorization` phải trước `limits`. Test này ép **total order** A → B → C và có thể fail khi team đổi B → A → C dù C vẫn an toàn.

### 10.1. Một cách kiểm tra các quan hệ cần thiết

Với một unit workflow có mock `authorization`, `limits`, `capture` và fixture phù hợp, có thể xác minh riêng hai quan hệ:

~~~java
InOrder authBeforeCapture = inOrder(authorization, capture);
authBeforeCapture.verify(authorization).check(actorId);
authBeforeCapture.verify(capture).capture(paymentId);

InOrder limitBeforeCapture = inOrder(limits, capture);
limitBeforeCapture.verify(limits).check(paymentId);
limitBeforeCapture.verify(capture).capture(paymentId);
~~~

Hai kiểm tra độc lập chỉ áp đặt **A trước C** và **B trước C**, không vô tình áp đặt **A trước B**. Đây là snippet minh họa cho API có chữ ký như đã ghi; cần định nghĩa interfaces và các fixture trong test thực tế.

### 10.2. Dùng state machine khi thứ tự là thuộc tính nghiệp vụ

Khi nhiều bước có thể chạy song song, không nên phóng to một chuỗi `InOrder` đến mức mô phỏng toàn bộ scheduler. Một cách vững hơn là biểu diễn invariant trong domain state:

~~~text
PENDING
  ├── authorization = APPROVED
  ├── limits = PASSED
  └── chỉ khi cả hai đúng mới chuyển sang CAPTURE_REQUESTED
~~~

Test sau đó xác minh state transition và tác động bị cấm khi điều kiện thiếu. Điều này có giá trị lâu dài hơn việc đo chi tiết thứ tự lời gọi giữa nhiều thread.

## 11. Tại sao thứ tự giữa các @ApplicationModuleListener thường không được bảo đảm?

Trong Spring Modulith, `@ApplicationModuleListener` kết hợp hành vi transactional event listener với xử lý bất đồng bộ và transaction mới theo cấu hình/hạ tầng của framework. Một sự kiện `OrderPlaced` có thể được gửi tới nhiều listener:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    inventory.reserve(event.orderId());
}
~~~

và:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    notifications.scheduleEmail(event.orderId());
}
~~~

Nếu hai listener thuộc hai module khác nhau và cùng phản ứng sau commit, không nên mặc định rằng listener `inventory` **phải hoàn tất trước** listener `notifications`. Thread scheduling, transaction mở riêng, I/O latency và retry có thể làm thứ tự kết thúc thay đổi.

### 11.1. Anti-pattern: kiểm tra chuỗi listener bất đồng bộ

~~~java
InOrder order = inOrder(inventoryGateway, notificationGateway);
order.verify(inventoryGateway).reserve(orderId);
order.verify(notificationGateway).scheduleEmail(orderId);
~~~

Không nên dùng như một “quy tắc tự nhiên” chỉ vì producer phát `OrderPlaced` một lần. Nếu không có contract yêu cầu email phải đợi tồn kho, test này có thể flaky và áp đặt coupling không cần thiết giữa các module.

### 11.2. Test đúng khi hai listener độc lập

Kiểm tra mỗi **kết quả cuối cùng** riêng, với deadline rõ:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            assertThat(reservationRepository
                    .existsByOrderId(orderId)).isTrue();
            assertThat(notificationRepository
                    .existsByOrderId(orderId)).isTrue();
        });
~~~

Đây là snippet của integration test đã có repositories/transaction manager và Awaitility; không phải class tự chạy. Các assertions không quan tâm reservation hay notification record xuất hiện trước, chỉ quan tâm **cả hai được xử lý thành công**.

Spring Modulith cũng cung cấp `Scenario` để diễn đạt kích hoạt event và chờ state change ở module test. Với callback async, ưu tiên điều kiện trạng thái thay vì `Thread.sleep` và `InOrder` giữa các mock.

### 11.3. Nếu một listener thật sự phụ thuộc listener khác?

Nếu nghiệp vụ yêu cầu **chỉ gửi thông báo sau khi inventory giữ hàng thành công**, hãy biểu diễn dependency bằng sự kiện kế tiếp:

~~~mermaid
sequenceDiagram
    participant Orders
    participant Inventory
    participant Notifications
    Orders->>Inventory: OrderPlaced
    Inventory->>Inventory: Reserve stock + commit
    Inventory-->>Notifications: StockReserved
    Notifications->>Notifications: Schedule email
~~~

Khi đó `StockReserved` là **hợp đồng nghiệp vụ** của bước tiếp theo, chứ không chỉ là kỳ vọng timing giữa hai listener vốn được kích hoạt bởi cùng một event. Test nên kiểm tra `StockReserved` chỉ phát khi reservation thành công và notification chỉ phản ứng với `StockReserved` sau commit. Không dùng Mockito order thay cho thiết kế orchestration.

## 12. Thời điểm publish không đồng nghĩa thời điểm commit

Một service có thể phát event **trong transaction**:

~~~java
@Transactional
public void place(UUID id) {
    orders.save(new OrderEntity(/* ... */));
    events.publishEvent(new OrderPlaced(/* ... */));
}
~~~

Những mốc cần tách:

1. **`publishEvent` được gọi** trong thread của service.
2. Transaction nguồn **commit hoặc rollback**.
3. `@TransactionalEventListener(AFTER_COMMIT)` được kích hoạt nếu commit.
4. Listener bất đồng bộ xử lý trên executor/transaction riêng.
5. Event Publication Registry, nếu cấu hình persistence, ghi nhận completion theo target.

Một `InOrder` giữa `repository.save` mock và `publisher.publishEvent` mock **không chứng minh** commit thành công hoặc callback after-commit đã chạy.

### 12.1. PublishedEvents nhìn thấy gì?

`PublishedEvents` trong `@ApplicationModuleTest` quan sát những event được phát. Nó có thể thấy event được `publishEvent` trước khi transaction rollback. Vì vậy:

- Producer test: dùng `PublishedEvents` để kiểm tra type, payload và số lần phát.
- Transaction integration test: xác minh dữ liệu commit/rollback bằng DB thật.
- Listener test: kiểm tra callback after-commit và side effect bằng điều kiện chờ.
- Registry test: kiểm tra publication incomplete/completed theo target nếu cần reliability.

Không suy ra “đã phát event” đồng nghĩa “listener đã xử lý” hay “external broker đã nhận message”.

### 12.2. @Transactional trên test gây hiểu lầm về thứ tự

Nếu cả lớp `@ApplicationModuleTest` được bọc `@Transactional` và test mặc định rollback cuối cùng, `OrderService.place` có thể tham gia transaction ngoài. Khi đó `AFTER_COMMIT` listener không chạy giữa các assertions; một test kiểm tra “listener A trước listener B” có thể thất bại **không phải vì thứ tự**, mà vì chưa có commit.

Nếu cần kiểm tra callback sau commit, không bọc transaction test vô thức; có thể dùng `TransactionTemplate` hoặc `TestTransaction` để điều khiển commit, rồi chờ callback thật.

## 13. Timeout, after và sự nguy hiểm của xác minh theo đồng hồ

Mockito hỗ trợ:

~~~java
verify(gateway, timeout(2_000)).send(orderId);
~~~

`timeout(2_000)` chờ invocation khớp xuất hiện trong giới hạn và **có thể kết thúc sớm** ngay khi đủ điều kiện. Nó không có nghĩa sau hai giây sẽ không còn lời gọi mới.

Vì vậy:

- `verify(gateway, timeout(2_000).times(1)).send(orderId)` có thể pass khi lời gọi thứ nhất xuất hiện, rồi lời gọi thứ hai đến sau.
- `verify(gateway, never()).send(orderId)` kiểm tra ở thời điểm hiện tại, không bảo đảm không có future callback.
- `after(2_000)` có semantics chờ theo khoảng thời gian nhưng vẫn không bảo đảm tương lai vô hạn.
- `InOrder` giữa các mock bị gọi bởi các thread khác nhau có thể phản ánh lịch scheduling thay vì một thứ tự nghiệp vụ có cam kết.

### 13.1. Nếu thứ tự thời gian là SLA thực sự

Ví dụ yêu cầu **acknowledge trong vòng hai giây sau khi commit**, không nên chỉ viết `InOrder`. Hãy đo:

- Timestamp hoặc observation/span tại mốc commit/publish.
- Thời điểm side effect được hoàn tất.
- Các trạng thái database hoặc registry được lưu bền vững.
- Trường hợp timeout, retry hoặc stale publication.

Khi đó test SLA ở mức integration với thời gian kiểm soát hợp lý. Đừng biến thời gian wall-clock ngẫu nhiên trên CI thành ràng buộc giòn không liên quan đến contract.

## 14. Retry làm thay đổi số lần và thứ tự attempt

Một downstream timeout có thể kích hoạt retry. Phân biệt:

| Khái niệm | Ví dụ | Mockito có chứng minh đầy đủ không? |
| --- | --- | --- |
| **Invocation** | Mock gateway bị gọi lần 1, lần 2. | `verify(times(2))` đếm lời gọi trong test. |
| **Publication attempt** | Listener xử lý lại event chưa completed. | Cần Registry/observability và test recovery. |
| **Broker delivery** | Kafka nhận hai record cùng eventId. | Cần broker integration/consumer evidence. |
| **Business effect** | Khách thực nhận một email hoặc bị charge một lần. | Cần idempotency/DB/provider reconciliation. |

Nếu API hỗ trợ retry hợp lệ, test `times(1)` có thể tạo false failure. Ngược lại, `atLeastOnce()` có thể che duplicate ngoài ý muốn. Hãy verify số lần **khi đã đặc tả chính xác scope**: một phương thức trong một execution, một logical command, hay một lần gọi provider.

### 14.1. Ví dụ stubbing lỗi rồi thành công

~~~java
when(pricing.quoteFor(skuId))
        .thenThrow(new IllegalStateException("Temporary outage"))
        .thenReturn(new PriceQuote(
                new BigDecimal("100000.00"), "VND"));
~~~

Stubbing liên tiếp **không tự bật retry**. Nếu service hiện tại không có retry policy, lần gọi thứ nhất ném lỗi và kết thúc. Muốn lần hai xảy ra phải gọi lại service, hoặc test cơ chế Spring Retry/Resilience4j thực sự được cấu hình và proxy hóa.

Không dùng InOrder để “chứng minh retry đúng” nếu test chỉ sắp xếp các invocations mock mà không kiểm tra transaction/side effect sau khi phục hồi.

### 14.2. Đúng một event không đồng nghĩa đúng một business effect

Một `OrderPlaced` có thể được xử lý nhiều lần sau lỗi listener. Ngay cả khi producer chỉ gọi `publishEvent` một lần, Event Publication Registry vẫn có thể resubmit **publication theo target**. Consumer cần idempotency dựa vào `eventId`/business key và constraint hoặc cơ chế provider, không dựa vào thứ tự callback ở một test.

## 15. verifyNoMoreInteractions có phải phương án thay thế InOrder?

Không nên chữa over-verification bằng cách kiểm soát **mọi interaction**:

~~~java
verify(pricing).quoteFor(skuId);
verify(customers).canPlaceOrder(customerId);
verifyNoMoreInteractions(pricing, customers);
~~~

Phần cuối này assert không còn các invocation chưa verify trên hai mock. Nó có thể hợp lý khi contract thật sự **cấm mọi tương tác bổ sung** vì chi phí, bảo mật hoặc side effect. Nhưng nếu API có thêm một lời gọi hợp lệ để đọc metadata/cache, test sẽ fail dù kết quả vẫn đúng.

### 15.1. Chọn negative assertion đúng phạm vi

| Muốn bảo vệ | Assertion gợi ý |
| --- | --- |
| Không gọi pricing khi input ngay từ đầu không hợp lệ. | `verifyNoInteractions(pricing)`. |
| Không gửi lệnh charge nếu kiểm tra quyền thất bại. | `verifyNoInteractions(captureGateway)` hoặc `never().capture(...)`. |
| Một lần lấy quote đúng SKU trong một command không retry. | `verify(pricing).quoteFor(skuId)`; nếu cần, thêm `times(1)` toàn method. |
| Giá trị order đã được lưu và event đúng. | Assert database + `PublishedEvents`, **không phải** `verifyNoMoreInteractions`. |
| Tồn tại A trước C và B trước C. | Kiểm tra partial order hoặc state-machine invariant. |

Chỉ dùng mức kiểm tra chặt khi có **lý do được giải thích trong test name hoặc contract comment**.

## 16. BDD và tên test nên nói về hợp đồng, không kể lại code

So sánh hai test names:

~~~java
void callsPricingThenCustomersThenRepositoryThenPublisher()
~~~

và:

~~~java
void eligibleOrderUsesCorrectPriceAndPublishesOrderPlaced()
~~~

Tên thứ nhất khóa implementation detail; tên thứ hai bảo vệ kết quả nghiệp vụ. Khi thứ tự không được đặc tả, tên test không nên ám chỉ một thứ tự cố định.

### 16.1. Given–When–Then khi không quan trọng thứ tự

~~~java
// Given: các collaborator trả dữ liệu đúng hợp đồng.
given(pricing.quoteFor(skuId))
        .willReturn(new PriceQuote(amount, "VND"));
given(customers.canPlaceOrder(customerId))
        .willReturn(true);

// When: xử lý command thật.
service.place(orderId, skuId, customerId);

// Then: xác minh tham số và kết quả.
then(pricing).should().quoteFor(skuId);
then(customers).should().canPlaceOrder(customerId);
assertThat(repository.existsById(orderId)).isTrue();
~~~

`given` và `then` của `BDDMockito` giúp diễn đạt intent; chúng **không tự tăng độ đúng**. Với module test, vẫn cần `PublishedEvents` và assertions về giá trị row. Không thêm `InOrder` giữa hai `then(...)` nếu contract không yêu cầu.

## 17. Không dùng spy để đóng băng thứ tự implementation

`@MockitoSpyBean` wrap một **bean thật** và cho phép `verify` method invocation. Trong Spring Framework 6.2+, spy cần có đúng một bean hiện diện; khác với `@MockitoBean` mặc định có thể tạo mock cho collaborator vắng mặt.

Ví dụ anti-pattern:

~~~java
@MockitoSpyBean OrderTotalCalculator calculator;
@MockitoSpyBean OrderFormatter formatter;

// Sau khi chạy use case:
InOrder sequence = inOrder(calculator, formatter);
sequence.verify(calculator).calculate(...);
sequence.verify(formatter).format(...);
~~~

Nếu chính quy tắc nghiệp vụ chỉ yêu cầu tổng tiền và nội dung hiển thị đúng, verify trên spy của hai implementation details này thêm coupling với code nội bộ mà không tăng độ tin cậy. Hãy assert total, currency và output format.

### 17.1. Khi spy thực sự hữu ích?

Spy có thể phù hợp để quan sát một callback **đang được thực thi thật**, khi invocation là một phần hợp đồng và khó xác minh bằng state. Nhưng vẫn cần:

- Bean thật được bootstrap.
- Không stub method thật vô ý: `when(spy.method())` có thể gọi method thật **ngay khi setup**.
- Khi cần, dùng `doReturn(...).when(spy).method()` để tránh side effect lúc stubbing, và cân nhắc Spring AOP proxy.
- Không thay test outcome/transaction bằng interaction-only assertion.

Trong `@ApplicationModuleTest(STANDALONE)` của `orders`, `@MockitoSpyBean PriceQuoteService` thường không phù hợp nếu implementation thuộc module `pricing` không được nạp. Để test API thật, chuyển sang `DIRECT_DEPENDENCIES` hoặc integration test, không dùng spy như mock “mạnh hơn”.

## 18. MockitoBean và bootstrap modes quyết định ranh giới test

| Cấu hình | Context nạp | Cách kiểm tra |
| --- | --- | --- |
| `@ApplicationModuleTest` / `STANDALONE` | Chỉ module chứa test. | Mock public APIs ngoài module; giữ service/repository/publisher của module thật. |
| `DIRECT_DEPENDENCIES` | Module hiện tại và các dependency trực tiếp. | Dùng implementation thật khi mục tiêu là contract/wiring giữa hai module. |
| `ALL_DEPENDENCIES` | Module hiện tại và toàn cây phụ thuộc. | Kiểm tra sâu hơn nhưng context/test fixture lớn hơn. |
| JUnit + `MockitoExtension` | Không có Spring context. | Dùng `@Mock`/constructor; không chứng minh JPA/transaction/event dispatch. |

### 18.1. @MockitoBean mặc định replace-or-create

~~~java
@MockitoBean PriceQuoteService pricing;
~~~

Trong `STANDALONE`, Spring Test có thể tạo mock cho API ngoài module không được bootstrap. Nếu dùng:

~~~java
@MockitoBean(enforceOverride = true)
PriceQuoteService pricing;
~~~

thì test yêu cầu **bean phù hợp đã hiện diện để thay thế**. Khi implementation thật của `pricing` bị loại khỏi context, cấu hình này thường gây lỗi khởi động.

Đừng nhầm `@Mock` của Mockito với `@MockitoBean` của Spring Test: `@Mock` không tự tạo bean cho constructor injection vào một Spring-managed `OrderService`.

### 18.2. Tương thích phiên bản

`@MockitoBean`/`@MockitoSpyBean` nằm trong Spring Framework 6.2+ (ví dụ Spring Boot 3.4+). Trong Boot cũ có thể thấy `@MockBean`/`@SpyBean`; các annotation cũ được deprecated từ Boot 3.4 để chuyển sang Framework equivalents. Đối chiếu dependency đang dùng trước khi thay import, không chạy theo một ví dụ không khớp version.

## 19. Architecture test: mock không hợp thức hóa dependency sai

Một service `orders` import `pricing.internal.PriceRepository` là lỗi ranh giới nếu module `pricing` chỉ công bố `pricing :: api`. Mock repository ấy để `@ApplicationModuleTest` khởi động **không sửa được vi phạm**.

Phải kiểm chứng kiến trúc độc lập:

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

`verify()` phát hiện phụ thuộc vòng, truy cập API không công bố và vi phạm `allowedDependencies` theo các quy tắc Spring Modulith. Nó **không** chứng minh `pricing.quoteFor` và `customers.canPlaceOrder` đã được gọi, không chạy Kafka và không kiểm tra event payload.

### 19.1. Không cần đổi thứ tự để qua architecture test

Module dependency graph không phụ thuộc thứ tự mà methods được gọi trong một use case. Nếu `orders` hợp lệ phụ thuộc `pricing :: api` và `customers :: api`, việc hoán đổi hai lời gọi không tạo một cycle mới.

Chỉ khi các module thật bắt đầu **gọi ngược lại nhau** hoặc truy cập implementation nội bộ, mới cần đánh giá cấu trúc và API, chứ không phải xử lý bằng `InOrder`.

## 20. Khi nào cần contract/integration test với module thật?

Trong `@ApplicationModuleTest`, mock trả:

~~~java
when(pricing.quoteFor(skuId))
        .thenReturn(new PriceQuote(
                new BigDecimal("100000.00"), "VND"));
when(customers.canPlaceOrder(customerId))
        .thenReturn(true);
~~~

Đó là **giả định của test về contract của provider**, không chứng minh provider thật hoạt động đúng. Cần:

1. Test module `pricing` với dữ liệu giá thật để đảm bảo amount/currency và lỗi theo contract.
2. Test module `customers` để đảm bảo `canPlaceOrder` trả true/false đúng trạng thái.
3. `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` hoặc `@SpringBootTest` phù hợp để kiểm tra wiring/integration thật giữa các module.
4. Adapter tests cho HTTP/broker nếu implementation ngoài có I/O, bằng fake server/Testcontainers phù hợp.

Ví dụ skeleton:

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealDependenciesTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;
    @Autowired PricingFixture pricingFixture;
    @Autowired CustomerFixture customerFixture;

    @Test
    void acceptsOrderUsingRealPriceAndEligibility() {
        UUID skuId = pricingFixture.createPricedSku(
                new BigDecimal("100000.00"), "VND");
        UUID customerId = customerFixture.createEligibleCustomer();
        UUID orderId = UUID.randomUUID();

        service.place(orderId, skuId, customerId);

        assertThat(orders.existsById(orderId)).isTrue();
    }
}
~~~

`PricingFixture` và `CustomerFixture` là **test fixtures cần triển khai**, không phải bean sẵn có của Spring Modulith. Test integration này **không mock chính public APIs** cần kiểm chứng. Hành vi và wiring thật được xác nhận mà không cần áp đặt thứ tự hai lookup vốn không được đặc tả.

## 21. CI quality gate: chống lỗi thật, không chống refactor hợp lệ

| Quality gate | Mục tiêu | Assertion phù hợp |
| --- | --- | --- |
| **Architecture** | Không cycle/truy cập API nội bộ sai. | `ApplicationModules.of(...).verify()`. |
| **Unit business logic** | Validation và phép tính đúng. | State/output assertions; không spy để verify mọi helper. |
| **Orders module test** | Dữ liệu và event đúng, gọi public APIs đúng tham số. | `@MockitoBean` boundary, repository thật, `PublishedEvents`. |
| **Negative path** | Không lưu/phát khi customer bị từ chối. | Exception + DB/event assertions; không cần InOrder lookup. |
| **Prohibited side effect** | Không charge/gửi khi chưa được phép. | `verifyNoInteractions`/ `never` trên gateway. |
| **Required sequencing** | Kiểm tra quyền trước irreversible action. | `InOrder` giữa các **contract ports**. |
| **Provider contract** | API pricing/customers thật có semantics đã stub. | Module tests phía provider. |
| **Wiring integration** | Các module có thể phối hợp đúng với bean thật. | `DIRECT_DEPENDENCIES`/integration test. |
| **Async listener** | Side effect từng listener hoàn tất theo SLA. | `Scenario`/Awaitility và DB/registry state. |
| **Retry/idempotency** | Replay không nhân đôi business effect. | Database unique marker hoặc provider idempotency test. |
| **External protocol** | Kafka/HTTP payload/ordering contract nếu có. | Broker/fake server integration tests. |

### 21.1. Metamorphic test: hoán đổi thứ tự mà không thay đổi kết quả

Một cách đánh giá chất lượng test (ở mức thiết kế, không yêu cầu sửa production chỉ để test) là hỏi:

> “Nếu developer hoán đổi `pricing.quoteFor` và `customers.canPlaceOrder`, nhưng mọi kết quả hợp lệ giữ nguyên, test nào nên pass?”

Test state/event + verify arguments **nên pass**. Test dùng `InOrder` một cách vô cớ sẽ fail. Đây là cách tự đánh giá xem suite đang bảo vệ **business contract** hay đang đóng băng implementation.

Với tình huống có side effect, cần kiểm tra giả định độc lập trước. Không hoán đổi thật các thao tác khi contract yêu cầu order, quyền truy cập hoặc transaction propagation cụ thể.

### 21.2. Làm sao nhận diện over-specification trong code review?

Đặt các câu hỏi:

- Vì sao test yêu cầu A trước B? Điều đó được ghi ở đâu trong nghiệp vụ/API protocol?
- Nếu đổi A ↔ B, người dùng/hệ thống ngoài có quan sát sự khác biệt không?
- Test có assert DB state và event payload không, hay chỉ InOrder?
- Có retry/async làm thứ tự không được bảo đảm không?
- Có thể dùng state machine, `never()` hoặc outcome assertion thay vì thứ tự toàn chuỗi không?
- Liệu test đang spy helper nội bộ chỉ để theo dõi cách thực hiện?

Nếu không giải thích được một thứ tự bằng hợp đồng, **loại bỏ InOrder** và giữ những assertion có ý nghĩa.

## 22. Những anti-pattern thường gặp

### 22.1. InOrder hai lookup độc lập

~~~java
InOrder sequence = inOrder(pricing, customers);
sequence.verify(pricing).quoteFor(skuId);
sequence.verify(customers).canPlaceOrder(customerId);
~~~

Không có điều khoản “pricing phải trước customers”; test sẽ gãy khi refactor đổi thứ tự.

### 22.2. Verify một loạt helper nội bộ

~~~java
sequence.verify(normalizer).normalize(...);
sequence.verify(calculator).applyDiscount(...);
sequence.verify(formatter).format(...);
~~~

Đây có thể chỉ là chi tiết triển khai; ưu tiên assert số tiền, currency, format và kết quả cuối cùng.

### 22.3. Dùng InOrder để thay test transaction

~~~java
sequence.verify(repository).save(...);
sequence.verify(publisher).publishEvent(...);
~~~

Không chứng minh database commit hay listener after-commit. Dùng repository/transaction integration test và `PublishedEvents`/listener state.

### 22.4. Dùng InOrder giữa hai listener async

~~~java
sequence.verify(inventory).reserve(...);
sequence.verify(notifications).send(...);
~~~

Không có bảo đảm thứ tự theo scheduler; nếu nghiệp vụ thực cần phụ thuộc, đổi thiết kế thành event chain/explicit coordinator.

### 22.5. Dùng timeout(times(1)) rồi kết luận exactly once

Assertion có thể pass trước lời gọi duplicate đến muộn; business exactly-once cần idempotency và integration test.

### 22.6. Dùng verifyNoMoreInteractions mọi nơi

Chặn những tương tác được phép và làm test giòn; chỉ dùng khi mọi tương tác ngoài danh sách thực sự bị cấm.

### 22.7. Mock repository và publisher trong module integration test

Chỉ còn đo invocation thay vì chứng minh JPA state hoặc event thật. Với test module, giữ hai thành phần đó thật khi mục tiêu yêu cầu.

### 22.8. Mock implementation nội bộ của module khác

Mockito không chữa vi phạm `allowedDependencies`; thay bằng public API/named interface và architecture test.

### 22.9. Dùng @MockitoSpyBean khi bean thật không được bootstrap

Spy cần real bean để wrap; trong `STANDALONE`, implementation module ngoài thường không hiện diện. Dùng `@MockitoBean` cho public boundary hoặc mở rộng bootstrap nếu cần test implementation thật.

### 22.10. Quên đối chứng nhánh lỗi và điều kiện cấm gọi

Nếu quyền bị từ chối, nên assert **không thực hiện tác động không được phép**; test InOrder của happy path không bảo vệ nhánh này.

## 23. Bài tập tình huống

Hệ thống Spring Modulith có module `checkout` gọi:

- `pricing.api.QuoteProvider.quote(cartId)` để tính giá.
- `customers.api.CustomerEligibility.isEligible(customerId)` để đánh giá khách hàng.
- `payments.api.PaymentAuthorization.authorize(request)` để cho phép thanh toán.
- `payments.api.PaymentCapture.capture(request)` để thực hiện side effect với provider.
- Sau khi hoàn tất giao dịch, `checkout` phát `CheckoutCompleted` để `notifications` và `analytics` xử lý bất đồng bộ.

Hợp đồng được mô tả:

1. Pricing và eligibility độc lập, có thể thực hiện theo bất kỳ thứ tự nào.
2. Không capture nếu authorization bị từ chối.
3. Capture chỉ được bắt đầu **sau khi authorization thành công**.
4. `notifications` và `analytics` xử lý độc lập sau commit; không quy định cái nào xong trước.
5. Provider có thể retry network với cùng idempotency key; số attempts không mặc nhiên bằng một.

### Câu hỏi

1. Có nên viết `InOrder(pricing, eligibility)` không? Vì sao?
2. Với pricing/eligibility, nên verify những gì và assert những kết quả nào ở database/event?
3. Nếu `authorization` bị từ chối, `verify(capture, never()).capture(...)` hoặc `verifyNoInteractions(capture)` bảo vệ điều gì?
4. Nên dùng InOrder nào để bảo vệ điều khoản “authorize trước capture”?
5. Nếu có thêm bước fraud check độc lập với pricing, tất cả cùng phải xong trước capture, nên áp đặt total order hay partial order?
6. Có nên dùng InOrder giữa listener `notifications` và `analytics` không?
7. `verify(capture, times(1))` có bảo đảm provider chỉ charge đúng một lần khi mất ack không?
8. `PublishedEvents` thấy `CheckoutCompleted` có chứng minh hai listener đã completed không?
9. Khi đổi chỗ pricing và eligibility mà test InOrder fail, nên sửa production hay test?
10. Mockito tests đều pass nhưng `checkout` import `payments.internal.PaymentRepository`: phép kiểm tra nào bắt lỗi?

### Đáp án tham khảo

1. **Không**, vì contract xác nhận hai lookup độc lập, không quy định thứ tự.
2. Verify đúng `cartId`/`customerId`, assert tổng tiền cuối, trạng thái checkout, event payload; không verify method chain nội bộ.
3. Bảo đảm không thực hiện **side effect bị cấm** trên nhánh authorization failed; chọn matcher/port phù hợp phạm vi điều khoản.
4. `InOrder(authorization, capture)` để xác minh lời gọi authorize có trước capture; thêm negative test khi authorization từ chối.
5. **Partial order**: mỗi bước cần hoàn tất trước capture, nhưng không áp đặt thứ tự giữa các bước độc lập.
6. Không. Hai listener chạy sau commit và không có hợp đồng hoàn tất theo thứ tự; chờ side effects riêng.
7. Không. Invocation count trong test khác provider side effect; cần idempotency key, retry policy và integration/reconciliation.
8. Không. Nó chứng minh producer phát event; callback after-commit, Registry và side effect là các mốc khác.
9. Nếu hợp đồng không đổi, **sửa test over-specified** bằng outcome/contract assertions. Nếu thực tế có quy tắc cần thứ tự, làm rõ contract rồi mới thay code/test.
10. `ApplicationModules.of(...).verify()` bảo vệ module boundaries và `allowedDependencies`.

## 24. Checklist trước khi dùng InOrder

- [ ] Có điều khoản hợp đồng **nêu rõ A phải trước B** hoặc một dependency nhân quả tương đương.
- [ ] Đã xác định các bước độc lập **không có ràng buộc** và không đưa chúng vào total order vô cớ.
- [ ] Nếu chỉ cần đúng arguments, dùng `verify`/captor thay cho `InOrder`.
- [ ] Nếu cần bảo vệ kết quả, assert **database state, exception và event** thật thay vì chỉ method calls.
- [ ] Nếu cấm một side effect ở nhánh lỗi, dùng `never`/`verifyNoInteractions` theo đúng phạm vi.
- [ ] `verifyNoMoreInteractions` chỉ xuất hiện khi mọi interaction bổ sung thực sự bị cấm.
- [ ] Không dùng spy của business helper nội bộ chỉ để đóng băng thứ tự tính toán.
- [ ] Nếu sử dụng `@ApplicationModuleTest(STANDALONE)`, chỉ mock public API của module ngoài hoặc I/O boundary cần cô lập.
- [ ] `OrderService`, repository và `ApplicationEventPublisher` chạy thật nếu test cần bảo vệ transaction, DB và `PublishedEvents`.
- [ ] Test không vô tình bọc transaction ngoài làm listener `AFTER_COMMIT` không chạy.
- [ ] Với listener async, dùng `Scenario`/Awaitility và side-effect assertions, không giả định callback order.
- [ ] Nếu một listener phụ thuộc listener khác, hợp đồng được biểu diễn bằng event chain/coordinator hoặc state machine.
- [ ] Không coi `timeout(times(1))` hay `InOrder` là bằng chứng exactly-once business effect.
- [ ] Với retry, có idempotency và integration tests kiểm chứng duplicate/recovery.
- [ ] Provider module có contract tests riêng, vì mock chỉ giả định response.
- [ ] Có wiring/integration test không override public API khi kiểm tra hợp tác thật giữa module.
- [ ] Architecture gate `ApplicationModules.verify()` bảo vệ named interfaces/`allowedDependencies`.
- [ ] CI test names mô tả **nghiệp vụ mong muốn**, không kể lại thứ tự từng method call.
- [ ] Code review trả lời được: nếu hoán đổi hai bước độc lập, test có nên tiếp tục pass?

**Kết luận:** `Mockito.inOrder` không sai; **sai là dùng nó để biến thứ tự không được đặc tả thành điều kiện phải giữ mãi**. Trong Spring Modulith, hãy bảo vệ đúng hợp đồng tại module boundary: gọi đúng API với đúng dữ liệu, cấm side effect khi không đủ điều kiện, bảo đảm thứ tự **chỉ khi nghiệp vụ hoặc protocol thực sự đòi hỏi**. Phần còn lại nên được kiểm tra bằng trạng thái database, `PublishedEvents`, provider contract/integration tests và `ApplicationModules.verify()`. Cách này cho phép refactor hợp lệ mà vẫn phát hiện lỗi có ý nghĩa.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents`, bootstrap modes và mocking dependency ngoài module.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): module boundaries, named interfaces và dependency rules.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, spy và qualifier.
- [Mockito — Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `InOrder`, `verify`, `times`, `never`, `timeout` và `verifyNoMoreInteractions`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): listener phases và `AFTER_COMMIT`.

> Ghi chú áp dụng: ví dụ dùng Spring Framework 6.2+, Spring Modulith, JUnit 5, Mockito và Spring Data JPA theo phiên bản tương thích. Các fixtures, schema và hạ tầng test cần được thiết lập theo dự án. Đây là tài liệu được biên soạn ở STEP_4; chưa chạy Gradle hoặc vòng Content QA chuyên môn.
