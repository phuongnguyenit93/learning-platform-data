# Verify lời gọi khi đó là một phần hợp đồng

## 1. Verify không chỉ để chứng minh “một method đã chạy”

Khi kiểm thử với Mockito, `verify(mock).method(...)` xác nhận rằng một đối tượng giả lập đã nhận lời gọi phù hợp. Kỹ thuật này hữu ích, nhưng cũng dễ bị lạm dụng: một bài test có thể chứa hàng chục lệnh `verify` cho mọi method nội bộ, rồi thất bại khi developer refactor mà hành vi nghiệp vụ vẫn đúng.

Trong ứng dụng Spring Modulith, cần đặt một câu hỏi trước khi verify:

> **Lời gọi này có phải nghĩa vụ của module đối với một collaborator hoặc hệ thống khác, hay chỉ là một bước triển khai bên trong module?**

**Lời gọi là một phần hợp đồng** nếu việc gọi đúng người nhận, đúng tham số, đúng điều kiện, đúng giới hạn số lần hoặc đúng thứ tự là yêu cầu mà module đã cam kết với đối tác. Ví dụ:

- Module `orders` **phải** hỏi API đánh giá rủi ro của module `compliance` với đúng `orderId`, `customerId`, `amount` và `tenantId` trước khi chấp nhận đơn hàng.
- Nếu dữ liệu đơn hàng sai, module **không được** gọi dịch vụ tính phí đánh giá rủi ro.
- Một workflow gửi nội dung marketing **phải** xác minh sự đồng ý trước khi đưa thông điệp vào hàng đợi.
- Module nhận sự kiện gọi gateway gửi thông báo với **đúng idempotency key** nhằm hỗ trợ xử lý lặp an toàn.

**Lời gọi chỉ là chi tiết triển khai** nếu một method có thể được đổi tên, tách/gộp hoặc thay bằng thuật toán khác mà không thay đổi kết quả/hợp đồng đã công bố. Ví dụ `OrderTotalCalculator.applyDiscount()` được gọi hai lần hay gộp thành một biểu thức không phải điều nên verify trong module integration test, nếu mục tiêu là kiểm tra **giá cuối cùng**.

Bài thuộc chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Học phần chú trọng kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm thử `@ApplicationModuleTest`, sự kiện, database và tích hợp, đồng thời thiết lập quality gate CI để ngăn phụ thuộc sai và hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận ra khi nào `verify` diễn đạt **hợp đồng tương tác** thay vì phụ thuộc implementation detail.
2. Kiểm tra đúng **target, tham số, điều kiện không gọi, số lần và thứ tự** bằng Mockito.
3. Dùng `@MockitoBean` tại API của module ngoài trong `@ApplicationModuleTest(STANDALONE)` mà vẫn chạy database và event publisher thật.
4. Kết hợp interaction assertions với state/exception/`PublishedEvents` assertions.
5. Dùng `ArgumentCaptor`, `argThat`, `eq`, `never`, `times`, `InOrder` và các mức verify khác đúng ngữ nghĩa.
6. Giải thích giới hạn của `verify(timeout(...))` với event listener bất đồng bộ, retry và idempotency.
7. Chọn contract test, integration test và `ApplicationModules.verify()` để kiểm chứng phần mà mock không bao phủ.

## 2. Phân biệt interaction contract và implementation detail

| Tình huống | Có nên `verify`? | Lý do |
| --- | --- | --- |
| Gọi `RiskAssessment.assess(request)` với đúng `tenantId` và `orderId`. | **Có**. | Tham số vượt module boundary là một phần hợp đồng bảo mật/nghiệp vụ. |
| Không gọi `RiskAssessment` khi `amount` không hợp lệ. | **Có**. | Bảo vệ một **negative interaction contract** và chi phí ngoài module. |
| Không gọi gateway gửi email khi không có quyền đồng ý. | **Có**. | Không phát sinh side effect trái quy định. |
| `OrderPricingPolicy.calculate()` được gọi đúng hai lần. | Thường **không**. | Số bước tính toán nội bộ không phải đầu ra nghiệp vụ. |
| `OrderRepository.save()` được gọi trong một test muốn chứng minh order đã commit. | Chưa đủ. | `verify(save)` không chứng minh JPA transaction/database; phải query dữ liệu thật. |
| `ApplicationEventPublisher.publishEvent()` được gọi trong unit test thuần. | Có thể. | Unit test chỉ chứng minh lời gọi, không chứng minh listener hoặc commit. |
| `OrderPlaced` đã phát trong `@ApplicationModuleTest`. | Ưu tiên `PublishedEvents`. | Kiểm chứng event payload qua Spring publisher thật, không mock publisher. |
| External HTTP client được gọi với header/idempotency key đúng. | Có trong unit test adapter; **cần thêm wire test**. | Mock kiểm tra invocation Java, không chứng minh bytes/protocol thực. |

Một bài test tốt không nhất thiết có nhiều `verify`. Nó chọn **những tương tác có giá trị hợp đồng**, còn kết quả nghiệp vụ được kiểm tra trực tiếp.

### 2.1. Hợp đồng phải nói rõ “bao nhiêu lần” trước khi assert times(1)

Ví dụ API đánh giá rủi ro bị tính phí mỗi lượt gọi. Nhóm nghiệp vụ có thể yêu cầu:

> Trong một lần xử lý lệnh tạo đơn hợp lệ, không bật retry tự động, `orders` chỉ thực hiện **một lần đánh giá** và sử dụng đúng định danh yêu cầu.

Khi đó `verify(risk, times(1)).assess(request)` kiểm tra một ràng buộc có thật. Nhưng nếu API cho phép retry timeout có kiểm soát, “đúng một lần” có thể là yêu cầu **sai**: một lần xử lý lệnh hợp lệ có thể tạo nhiều network attempts. Phải định nghĩa rõ bạn đang đếm **method invocation, attempt, logical command hay business side effect**.

## 3. Ví dụ kiến trúc: orders gọi public API của compliance

Giả sử `ShopApplication` nằm ở `com.example.shop`; các package con trực tiếp được phát hiện là application module:

~~~text
com.example.shop
├── ShopApplication.java
├── compliance
│   ├── api
│   │   ├── RiskAssessment.java
│   │   ├── RiskRequest.java
│   │   ├── RiskDecision.java
│   │   ├── RiskUnavailableException.java
│   │   └── package-info.java
│   └── internal
│       ├── RiskAssessmentService.java
│       └── RiskRuleRepository.java
└── orders
    ├── OrderService.java
    ├── OrderDeniedException.java
    ├── package-info.java
    ├── internal
    │   ├── OrderEntity.java
    │   └── OrderRepository.java
    └── events
        ├── OrderPlaced.java
        └── package-info.java
~~~

Hợp đồng giữa hai module trong ví dụ:

1. Module `orders` gọi đúng **public API** `compliance.api.RiskAssessment`, không truy cập repository nội bộ của `compliance`.
2. Chỉ gọi API khi `orderId`, `customerId`, `total` và `tenantId` đã qua validation.
3. Thông điệp gửi sang `compliance` phải mang đúng định danh lệnh, tổng tiền và tenant.
4. Nếu kết quả `APPROVED`, module lưu đơn hàng và phát `OrderPlaced`.
5. Nếu `DENIED` hoặc API ném lỗi kỹ thuật, module không tạo đơn đã chấp nhận.

~~~mermaid
flowchart LR
    T["@ApplicationModuleTest orders"] --> O["orders.OrderService THẬT"]
    O -->|"assess(request)"| C["compliance.api.RiskAssessment MOCK"]
    O --> R["orders.internal.OrderRepository THẬT"]
    O --> P["ApplicationEventPublisher THẬT"]
    R --> DB[("Test database")]
    P --> E["PublishedEvents"]
    S["compliance.internal.RiskAssessmentService"] -.->|"Không nạp ở STANDALONE"| C
~~~

Trong `STANDALONE`, việc thay public collaborator `RiskAssessment` bằng mock là hợp lý; service, repository và event infrastructure của `orders` phải chạy thật để kiểm chứng kết quả.

### 3.1. Định nghĩa contract công khai

File `compliance/api/RiskDecision.java`:

~~~java
package com.example.shop.compliance.api;

public enum RiskDecision {
    APPROVED,
    DENIED
}
~~~

File `compliance/api/RiskRequest.java`:

~~~java
package com.example.shop.compliance.api;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

public record RiskRequest(
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        String tenantId,
        UUID idempotencyKey
) {
    public RiskRequest {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(total);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(idempotencyKey);
    }
}
~~~

File `compliance/api/RiskAssessment.java`:

~~~java
package com.example.shop.compliance.api;

public interface RiskAssessment {
    RiskDecision assess(RiskRequest request);
}
~~~

File `compliance/api/RiskUnavailableException.java`:

~~~java
package com.example.shop.compliance.api;

public class RiskUnavailableException extends RuntimeException {
    public RiskUnavailableException(String message) {
        super(message);
    }
}
~~~

File `compliance/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.compliance.api;
~~~

**Tại sao truyền `RiskRequest` thay vì năm tham số rời?** Một record bất biến có thể nêu rõ hợp đồng và dễ dùng `equals`/captor. `tenantId` là thông tin phân vùng dữ liệu cần giữ đúng. `idempotencyKey` được chọn là `orderId` trong ví dụ để ổn định cho cùng một đơn hàng; nó **không tự làm provider idempotent**, mà chỉ cung cấp khóa để implementation bên kia thực hiện chính sách nếu có.

### 3.2. Cấu hình phụ thuộc module

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "compliance :: api"
)
package com.example.shop.orders;
~~~

`orders` được phép import API được công bố qua named interface `compliance :: api`, **không được** import `compliance.internal.RiskRuleRepository`. Mock không thể biến một dependency trái luật thành hợp lệ; phần này được bảo vệ bằng `ApplicationModules.verify()`.

## 4. Module orders có logic và persistence thật

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

    @Column(precision = 19, scale = 2, nullable = false)
    private BigDecimal total;

    private String tenantId;

    protected OrderEntity() {}

    public OrderEntity(UUID id, UUID customerId,
                       BigDecimal total, String tenantId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.total = Objects.requireNonNull(total);
        this.tenantId = Objects.requireNonNull(tenantId);
    }

    public UUID getCustomerId() { return customerId; }
    public BigDecimal getTotal() { return total; }
    public String getTenantId() { return tenantId; }
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
        BigDecimal total,
        Instant occurredAt
) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `orders/OrderDeniedException.java`:

~~~java
package com.example.shop.orders;

public class OrderDeniedException extends RuntimeException {
    public OrderDeniedException() {
        super("Risk assessment denied order");
    }
}
~~~

### 4.1. OrderService chỉ giao tiếp qua public API

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.compliance.api.RiskAssessment;
import com.example.shop.compliance.api.RiskDecision;
import com.example.shop.compliance.api.RiskRequest;
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

    private final RiskAssessment risk;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(RiskAssessment risk,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.risk = risk;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId, UUID customerId,
                      BigDecimal total, String tenantId) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(total, "total");
        Objects.requireNonNull(tenantId, "tenantId");

        if (total.signum() <= 0 || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid order input");
        }

        var request = new RiskRequest(
                orderId, customerId, total, tenantId, orderId);

        var decision = Objects.requireNonNull(
                risk.assess(request),
                "Risk decision must not be null");

        if (decision == RiskDecision.DENIED) {
            throw new OrderDeniedException();
        }

        orders.save(new OrderEntity(
                orderId, customerId, total, tenantId));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, customerId,
                total, Instant.now()));
    }
}
~~~

Ví dụ đặt **validation trước lời gọi risk**, rồi mới lưu và phát event. `OrderService` không biết `RiskAssessmentService` thật dùng database hay API ngoài. Đây là cơ sở để verify **đúng request** và **không gọi khi invalid**.

**Giới hạn nghiệp vụ:** mô hình rút gọn này không triển khai idempotency hoàn chỉnh cho `place()`, không xử lý race giữa hai lệnh cùng `orderId` và không mô phỏng một cổng thanh toán có side effect tài chính. Trong production cần quyết định transaction boundary, locking/unique constraint và chính sách retry theo hợp đồng thực.

## 5. @ApplicationModuleTest: mock collaborator ngoài module, giữ lõi thật

Với `@ApplicationModuleTest`, `STANDALONE` là bootstrap mode mặc định: chỉ nạp module chứa test. Vì bean thực thi `RiskAssessment` thuộc module `compliance`, implementation thường không được tải. Spring Framework 6.2+ cung cấp `@MockitoBean` để tạo/thay bean trong `ApplicationContext`.

~~~java
package com.example.shop.orders;

import com.example.shop.compliance.api.RiskAssessment;
import com.example.shop.compliance.api.RiskDecision;
import com.example.shop.compliance.api.RiskRequest;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
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
class OrderRiskContractTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    // Chỉ mock public API của module compliance.
    @MockitoBean RiskAssessment risk;

    @Test
    void sendsExactRiskRequestBeforeAcceptingOrder(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        var amount = new BigDecimal("129900.00");
        String tenantId = "tenant-a";

        var expected = new RiskRequest(
                orderId, customerId, amount, tenantId, orderId);

        when(risk.assess(expected))
                .thenReturn(RiskDecision.APPROVED);

        service.place(orderId, customerId, amount, tenantId);

        // Hợp đồng BÊN NGOÀI: đúng type, đúng định danh, đúng nội dung.
        verify(risk).assess(expected);

        // Hành vi BÊN TRONG: repository và publisher chạy thật.
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(saved -> {
                    assertThat(saved.getCustomerId())
                            .isEqualTo(customerId);
                    assertThat(saved.getTotal())
                            .isEqualByComparingTo(amount);
                    assertThat(saved.getTenantId())
                            .isEqualTo(tenantId);
                });

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId()).isEqualTo(customerId);
                    assertThat(event.total())
                            .isEqualByComparingTo(amount);
                });
    }
}
~~~

**Giá trị của test:** nếu service truyền nhầm `tenantId`, `orderId`, amount hoặc idempotency key, `verify(risk).assess(expected)` bắt sai lệch ở module boundary. Nếu service hỏi đúng risk nhưng không lưu hoặc phát event sai, assertions về database và `PublishedEvents` bắt lỗi đó.

Điều kiện chạy: dự án có Spring Boot, Spring Modulith test starter, JPA, datasource, schema và transaction manager phù hợp. Test đặt trong package `orders`; không tự thêm `@Transactional` ở cấp test nếu cần quan sát transaction service commit thật.

### 5.1. Verify có mặc định times(1) không?

Có. Với Mockito:

~~~java
verify(risk).assess(expected);
~~~

tương đương:

~~~java
verify(risk, times(1)).assess(expected);
~~~

đối với **lời gọi khớp method/arguments**. Tuy nhiên nó **không cấm tất cả lời gọi khác** trên mock. Ví dụ gọi `assess(otherRequest)` ngoài một lần `assess(expected)` có thể không bị assertion trên phát hiện trừ khi bạn kiểm tra toàn bộ interactions hoặc chính sách riêng.

Nếu hợp đồng thực sự là “chỉ một assessment cho toàn command”, có thể kiểm tra tổng số invocation theo method:

~~~java
verify(risk, times(1)).assess(any(RiskRequest.class));
verify(risk).assess(expected);
~~~

Kết hợp này xác nhận **chỉ có một lời gọi assess với bất kỳ `RiskRequest`** và lời gọi ấy có đúng dữ liệu. Cách đếm mạnh hơn chỉ nên dùng nếu giới hạn số lần là một phần contract, không phải vì muốn mọi test chặt nhất có thể.

## 6. Khi không được phép gọi: never() và verifyNoInteractions()

Một negative interaction có thể quan trọng hơn việc gọi thành công. Nếu đơn hàng có tổng tiền `0`, service phải dừng **trước khi** tương tác với module compliance.

Thêm test vào `OrderRiskContractTests`:

~~~java
@Test
void invalidAmountNeverCallsRiskAssessment(PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    assertThatThrownBy(() -> service.place(
                orderId, customerId,
                BigDecimal.ZERO, "tenant-a"))
            .isInstanceOf(IllegalArgumentException.class);

    // Không có bất kỳ tương tác nào với mock.
    verifyNoInteractions(risk);

    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Đoạn này dùng thêm static imports:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
~~~

So sánh các API:

| Lệnh | Khẳng định chính xác |
| --- | --- |
| `verify(risk, never()).assess(request)` | Không có lời gọi `assess` với **request khớp**. Có thể có lời gọi `assess(other)`. |
| `verify(risk, never()).assess(any(RiskRequest.class))` | Không có lời gọi `assess` với request không null phù hợp matcher. |
| `verifyNoInteractions(risk)` | Không có **bất kỳ tương tác** nào trên mock tính đến lúc kiểm tra. |
| `verifyNoMoreInteractions(risk)` | Không còn tương tác nào **chưa được verify**; không đồng nghĩa “không có lời gọi”. |

**Lưu ý về `any(RiskRequest.class)`:** matcher theo kiểu thường không khớp `null`. Nếu muốn cấm mọi lần gọi `assess`, bao gồm `null`, cần điều chỉnh matcher hoặc dùng `verifyNoInteractions` khi hợp đồng cấm tất cả tương tác.

### 6.1. Không verify negative ngay trước khi tác vụ async kết thúc

Nếu một callback có thể được enqueue sau vài mili giây, `verifyNoInteractions(mock)` kiểm tra **chỉ tại thời điểm hiện tại**. Nó không bảo đảm một lời gọi sẽ không xảy ra sau đó. Với async, phải chờ lifecycle/tín hiệu kết thúc phù hợp rồi mới kiểm tra, hoặc viết test transaction/broker ở tầng đúng.

## 7. Business rejection và technical failure: tương tác có xảy ra nhưng không được lưu

Hai nhánh này **đều phải gọi** public API compliance (với request hợp lệ), nhưng không được tạo order:

~~~java
@Test
void deniedRiskIsCheckedButDoesNotCreateOrder(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    var total = new BigDecimal("129900.00");
    var request = new RiskRequest(
            orderId, customerId, total, "tenant-a", orderId);

    when(risk.assess(request)).thenReturn(RiskDecision.DENIED);

    assertThatThrownBy(() -> service.place(
                orderId, customerId, total, "tenant-a"))
            .isInstanceOf(OrderDeniedException.class);

    verify(risk).assess(request);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}

@Test
void riskTechnicalFailureIsNotMistakenForApproval(
        PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    var total = new BigDecimal("129900.00");
    var request = new RiskRequest(
            orderId, customerId, total, "tenant-a", orderId);

    when(risk.assess(request))
            .thenThrow(new RiskUnavailableException(
                    "Risk provider unavailable"));

    assertThatThrownBy(() -> service.place(
                orderId, customerId, total, "tenant-a"))
            .isInstanceOf(RiskUnavailableException.class);

    verify(risk).assess(request);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Các đoạn này thuộc lớp test mục 5, cần các static import `when`, `verify`, `assertThatThrownBy` cùng import `RiskUnavailableException`.

**Điểm học thuật:** `verify` có thể đúng **ngay cả khi nghiệp vụ bị từ chối** — vì hợp đồng chỉ yêu cầu lời gọi đánh giá rủi ro xảy ra. Sau đó phải assert **không có side effect**. Ngược lại, `verify(risk).assess(request)` một mình không chứng minh kết quả được chấp nhận hay bị từ chối.

## 8. ArgumentCaptor: kiểm tra payload mà module thực sự gửi

Khi `RiskRequest` có nhiều field, record `equals` giúp so sánh expected request trực tiếp. Nhưng đôi khi request được tạo động (correlation ID, timestamp, metadata) hoặc test cần giải thích chính xác field nào sai.

`ArgumentCaptor` thu lại argument **của lời gọi thực tế** để assertion:

~~~java
@Test
void capturesActualBoundaryRequest(PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    BigDecimal amount = new BigDecimal("129900.00");
    String tenantId = "tenant-a";

    when(risk.assess(any(RiskRequest.class)))
            .thenReturn(RiskDecision.APPROVED);

    service.place(orderId, customerId, amount, tenantId);

    ArgumentCaptor<RiskRequest> captor =
            ArgumentCaptor.forClass(RiskRequest.class);
    verify(risk).assess(captor.capture());

    RiskRequest sent = captor.getValue();
    assertThat(sent.orderId()).isEqualTo(orderId);
    assertThat(sent.customerId()).isEqualTo(customerId);
    assertThat(sent.total()).isEqualByComparingTo(amount);
    assertThat(sent.tenantId()).isEqualTo(tenantId);
    assertThat(sent.idempotencyKey()).isEqualTo(orderId);

    assertThat(repository.existsById(orderId)).isTrue();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .hasSize(1);
}
~~~

Thêm:

~~~java
import org.mockito.ArgumentCaptor;
import static org.mockito.ArgumentMatchers.any;
~~~

Ở đây stub bằng `any` được bù bằng **assertion captor thật chặt chẽ**. Nếu chỉ stub `any`, gọi service rồi assert thành công, test có thể bỏ sót việc truyền sai `customerId` hoặc `tenantId`.

### 8.1. Không dùng captor thay cho mọi matcher

Nếu contract đơn giản:

~~~java
verify(risk).assess(new RiskRequest(
        orderId, customerId, amount, tenantId, orderId));
~~~

đã đủ rõ, không cần captor. Dùng captor khi cần:

- Kiểm tra nhiều field với thông báo lỗi chi tiết.
- Kiểm tra `eventId`/correlation ID phát sinh động.
- Thu nhiều request để kiểm tra danh sách hoặc thứ tự logic.
- Khẳng định payload không chứa dữ liệu nhạy cảm.

`ArgumentCaptor` phù hợp nhất ở **verification**. Không nên lạm dụng để tạo stubbing phức tạp khi `eq` hoặc `argThat` đủ diễn đạt.

### 8.2. Kiểm tra nhiều invocation

~~~java
ArgumentCaptor<RiskRequest> requests =
        ArgumentCaptor.forClass(RiskRequest.class);

verify(risk, times(2)).assess(requests.capture());

assertThat(requests.getAllValues())
        .extracting(RiskRequest::orderId)
        .containsExactly(firstOrderId, secondOrderId);
~~~

Đây là đoạn minh họa dành cho **test có chủ đích thực hiện hai lần assessment** và các biến đã được thiết lập. Không tự áp dụng `times(2)` chỉ vì muốn test capture, nhất là khi chính contract yêu cầu một lần.

## 9. ArgumentMatchers và những bug bị che bởi any()

Một lỗi phổ biến:

~~~java
when(risk.assess(any(RiskRequest.class)))
        .thenReturn(RiskDecision.APPROVED);

service.place(orderId, customerId, amount, tenantId);

assertThat(repository.existsById(orderId)).isTrue();
~~~

Test có thể pass dù service gửi nhầm `tenantId` sang một tenant khác. Vì mock trả `APPROVED` cho **mọi RiskRequest**, nó không bảo vệ phần quan trọng nhất của hợp đồng.

Lựa chọn:

~~~java
verify(risk).assess(argThat(req ->
        req.orderId().equals(orderId)
        && req.customerId().equals(customerId)
        && req.total().compareTo(amount) == 0
        && req.tenantId().equals(tenantId)
        && req.idempotencyKey().equals(orderId)));
~~~

Nếu mọi field đều là một phần hợp đồng, `verify` trực tiếp bằng record expected có thể đơn giản hơn. Nếu một field không liên quan hoặc sinh động, `argThat` giúp tập trung vào những bất biến cụ thể.

### 9.1. eq() khi method có nhiều tham số

Ví dụ một gateway có method:

~~~java
void send(UUID orderId, String tenantId, String payload);
~~~

Mockito:

~~~java
verify(gateway).send(
        eq(orderId),
        eq(tenantId),
        argThat(payload -> payload.contains("\"schemaVersion\":1")));
~~~

Nếu dùng matcher cho một tham số, các tham số còn lại trong cùng lời gọi cũng nên được biểu diễn bằng matcher phù hợp (`eq`, `any`, `argThat`...), không trộn matcher với literal một cách sai quy tắc Mockito.

**Lưu ý:** ví dụ chuỗi JSON dùng để minh họa. Muốn kiểm chứng wire contract nghiêm túc, hãy deserialize JSON và so cấu trúc/schema, không dựa vào `contains` vì spacing, escaping và serialization có thể thay đổi.

## 10. Mockito verification modes: chọn độ chặt theo hợp đồng

| API Mockito | Kiểm tra | Chỉ nên dùng khi |
| --- | --- | --- |
| `verify(mock)` | Đúng một lần cho method/argument match. | Contract cần một invocation cụ thể. |
| `times(n)` | Chính xác `n` invocation match. | Số lần được đặc tả rõ, không có retries ẩn. |
| `never()` | Không có invocation match. | Không được gọi trên nhánh invalid/denied. |
| `atLeastOnce()` / `atLeast(n)` | Số invocation tối thiểu. | Có thể lặp do retry, chỉ yêu cầu đạt ngưỡng. |
| `atMostOnce()` / `atMost(n)` | Không quá số invocation quy định. | Giới hạn phí/tác động gọi ngoài. |
| `only()` | Một lời gọi đúng và không có tương tác khác với mock. | Hợp đồng thực sự cấm mọi tương tác khác. |
| `verifyNoInteractions(mock)` | Mock chưa từng nhận invocation tính đến thời điểm kiểm tra. | Nhánh phải không chạm dependency. |
| `verifyNoMoreInteractions(mock)` | Không còn invocation chưa verify. | Mọi interaction trên mock đều là phạm vi hợp đồng cần kiểm soát. |
| `InOrder` | Thứ tự những lời gọi được chọn. | Thứ tự là nghĩa vụ đã được mô tả, không chỉ là cách viết code. |

### 10.1. verifyNoMoreInteractions không phải “càng chặt càng tốt”

~~~java
verify(risk).assess(expected);
verifyNoMoreInteractions(risk);
~~~

Đoạn này có thể hợp lý khi contract quy định chỉ assessment đó được phép xảy ra. Nhưng dùng `verifyNoMoreInteractions(...)` trong **mọi test** khiến test dễ gãy khi collaborator bổ sung một lời gọi hợp lệ như `isHealthy()` mà không làm thay đổi nghiệp vụ.

Theo tài liệu Mockito, verify mọi interaction là một dạng test quá đặc tả. Ưu tiên khẳng định **những điều thực sự bị cấm** bằng `never()`, hoặc kiểm soát số lần theo API cụ thể.

### 10.2. atLeastOnce có thể che tác động trùng

~~~java
verify(gateway, atLeastOnce()).send(orderId);
~~~

Nó pass nếu gửi một, hai hoặc mười lần. Nếu gateway gửi email hoặc charge, số lần có thể là yêu cầu nghiệp vụ. Cần tách:

- **Invocation count** của callback trong test.
- **Delivery attempts** do retry.
- **Business side effect** đã thực hiện bao nhiêu lần.

Một test chỉ kiểm tra `atLeastOnce` **không chứng minh tác động nghiệp vụ đúng một lần**.

## 11. InOrder: verify thứ tự khi thứ tự là luật kinh doanh

Không nên verify “gọi A trước B” chỉ vì source code đang viết như vậy. Nhưng có tình huống thứ tự là một phần hợp đồng, ví dụ **chỉ được enqueue thông điệp marketing sau khi xác minh sự đồng ý**.

Một unit test độc lập, không cần Spring context:

~~~java
interface ConsentGateway {
    void requireConsent(UUID customerId);
}

interface MarketingGateway {
    void enqueueOffer(UUID customerId);
}

final class CampaignWorkflow {

    private final ConsentGateway consent;
    private final MarketingGateway marketing;

    CampaignWorkflow(ConsentGateway consent,
                     MarketingGateway marketing) {
        this.consent = consent;
        this.marketing = marketing;
    }

    void sendOffer(UUID customerId) {
        consent.requireConsent(customerId);
        marketing.enqueueOffer(customerId);
    }
}
~~~

Test:

~~~java
@Test
void verifiesConsentBeforeSending() {
    ConsentGateway consent = mock(ConsentGateway.class);
    MarketingGateway marketing = mock(MarketingGateway.class);
    UUID customerId = UUID.randomUUID();

    var workflow = new CampaignWorkflow(consent, marketing);
    workflow.sendOffer(customerId);

    InOrder sequence = inOrder(consent, marketing);
    sequence.verify(consent).requireConsent(customerId);
    sequence.verify(marketing).enqueueOffer(customerId);
}
~~~

Các snippets là minh họa đặt trong test source cùng với imports `org.mockito.InOrder`, `org.junit.jupiter.api.Test`, `java.util.UUID` và static `Mockito.mock`/`Mockito.inOrder`.

**Vì sao InOrder có giá trị ở đây?** Việc chuyển lời gọi marketing lên trước kiểm tra consent sẽ vi phạm quy tắc bảo mật/nghiệp vụ. Thứ tự là contract.

### 11.1. Không InOrder mọi bước nội bộ

Không nên kiểm tra trình tự:

~~~java
order.verify(calculator).round(...);
order.verify(calculator).applyDiscount(...);
order.verify(formatter).formatTotal(...);
~~~

nếu đó chỉ là cách tính toán nội bộ. Hãy assert giá cuối cùng và các ràng buộc nghiệp vụ. Ngược lại, nếu protocol bắt buộc `beginTransaction → send → acknowledge` theo hợp đồng adapter, InOrder có thể phù hợp **ở test của adapter**.

### 11.2. InOrder không chứng minh transaction commit hay thứ tự xuyên broker

Ngay cả khi Mockito xác nhận `consent` được gọi trước `marketing` trong cùng thread, điều đó không chứng minh:

- Dữ liệu consent được commit trước message.
- Broker nhận record theo thứ tự đó.
- Consumer khác xử lý đúng thứ tự.
- Một instance khác không đồng thời gửi message trùng.

Đây là phạm vi cần integration/transaction/broker test và kiến trúc xử lý phân tán, không phải chỉ Mockito.

## 12. Kiểm thử lỗi: đúng tương tác đã xảy ra nhưng không được phép tiếp tục

Một trường hợp cần verify theo contract: nếu `RiskAssessment` báo `DENIED`, module `orders` phải dừng sau đánh giá, không lưu, không phát event. Test ở mục 7 đã bảo vệ cả hai phần.

Nếu một service có hai **external ports**, ví dụ `RiskAssessment` và `OrderSubmissionGateway`, thì khi risk bị từ chối:

~~~java
verify(risk).assess(expected);
verify(submissionGateway, never()).submit(any());
~~~

Đây là đoạn **minh họa** trong một test có khai báo `submissionGateway` và service thật; nó hợp lý nếu `submit` là side effect bị cấm khi rejected. Không thêm một gateway giả vào production chỉ để có thứ mà test verify.

### 12.1. Void method dùng doThrow khi stub thất bại

Giả sử một port bên ngoài:

~~~java
public interface AuditGateway {
    void recordAttempt(UUID orderId);
}
~~~

Để mô phỏng lỗi:

~~~java
doThrow(new IllegalStateException("Audit unavailable"))
        .when(auditGateway)
        .recordAttempt(orderId);
~~~

Với method trả giá trị:

~~~java
when(risk.assess(expected))
        .thenThrow(new RiskUnavailableException("Provider timeout"));
~~~

**Cú pháp khác nhau do `void` không thể truyền vào `when(...)`**, không phải vì Spring Modulith.

### 12.2. Nếu đã gọi external side effect trước rollback

Một mock `AuditGateway` ném exception trong `@Transactional` service có thể khiến database rollback. Nhưng nếu gateway thật đã gửi HTTP/email **trước** exception, transaction DB nguồn không thể tự thu hồi side effect ấy.

Vì vậy interaction verification phải đi kèm một **mô hình giao tác hợp lý**: after-commit listener, transactional event publication, outbox/dispatcher hoặc compensation khi nghiệp vụ cần. Không coi `verify(gateway, times(1))` là bằng chứng hệ thống phân tán đã đồng bộ thành công.

## 13. Kiểm tra event bằng PublishedEvents, không thay event bus bằng mock

Trong module `orders`, `ApplicationEventPublisher.publishEvent(new OrderPlaced(...))` là cơ chế thông báo đã xảy ra sự kiện. Khi dùng `@ApplicationModuleTest`, `PublishedEvents` cho phép truy vấn những event được phát bởi use case:

~~~java
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, orderId))
        .singleElement()
        .satisfies(event ->
                assertThat(event.total())
                        .isEqualByComparingTo(amount));
~~~

Nếu lại khai báo:

~~~java
@MockitoBean ApplicationEventPublisher publisher;
~~~

thì lời gọi event có thể chỉ đi vào Mockito mock thay vì Spring event infrastructure, khiến test không còn kiểm chứng đúng phát event. `verify(publisher).publishEvent(...)` có chỗ đứng trong **unit test thuần**, nhưng không thay `PublishedEvents` của module integration test.

### 13.1. “Event đã phát” không đồng nghĩa “listener đã xử lý”

Với `@ApplicationModuleListener`, listener thuộc module nhận có thể chạy **sau commit**, bất đồng bộ và trong transaction mới. `PublishedEvents` của test nguồn chứng minh việc phát event, **không chứng minh** listener ở module khác đã được bootstrap, thực thi, completed hay tạo side effect.

Test listener thật nên được đặt trong module nhận hoặc integration test có các module cần thiết. Nó phải kiểm tra transaction và trạng thái bền vững, không chỉ `verify(mockListener).on(event)`.

## 14. Async verification: timeout() là tín hiệu lời gọi, không phải kết thúc nghiệp vụ

Mockito hỗ trợ xác minh tương tác bất đồng bộ:

~~~java
verify(notificationGateway, timeout(2_000))
        .sendConfirmation(orderId);
~~~

`timeout(2_000)` sẽ thử kiểm tra lặp trong giới hạn thời gian và **trả về ngay khi điều kiện thỏa**. Nếu muốn hai lời gọi:

~~~java
verify(notificationGateway, timeout(2_000).times(2))
        .sendConfirmation(orderId);
~~~

Nhưng cần hiểu rõ:

- Nó xác nhận method **đã được gọi**, chưa chứng minh gateway ngoài nhận/xử lý.
- `times(1)` có thể pass khi lời gọi đầu tiên xuất hiện, rồi lời gọi thứ hai xảy ra **sau khi assertion hoàn tất**.
- Nếu chỉ verify `never()` ngay sau khi trigger async, callback có thể vẫn đến sau đó.
- Test phụ thuộc timing có thể flaky nếu executor/CI bận hoặc broker/network không ổn định.

### 14.1. Awaitility hoặc Scenario cho trạng thái thực

Khi kiểm tra listener `@ApplicationModuleListener`, ưu tiên chờ theo **điều kiện nghiệp vụ**:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(deliveryRepository
                        .existsByOrderId(orderId))
                        .isTrue());
~~~

Đây là đoạn assertion của một integration test đã có `deliveryRepository` cùng import `await`, `Duration` và AssertJ; không phải test class hoàn chỉnh.

Spring Modulith cũng cung cấp `Scenario` để diễn đạt việc phát sự kiện và chờ state change khi phù hợp. Một assertion cuối cùng về database/registry **mạnh hơn** một interaction-only assertion nếu mục tiêu là biết listener đã xử lý xong.

### 14.2. Mockito after(...) không phải lời giải mặc định

Mockito có `after(milliseconds)` để đánh giá điều kiện sau một khoảng thời gian, khác `timeout` có thể kết thúc sớm. Nhưng đây vẫn là công cụ **kiểm tra interaction theo thời gian**, không bảo đảm không có lời gọi ở bất kỳ thời điểm nào trong tương lai.

Thay vì kéo dài các `sleep` và `after` tùy ý, hãy dùng trạng thái hoàn tất có thể quan sát được, transaction commit, listener completion/registry hoặc synchronization mechanism phù hợp trong test.

## 15. Retry, idempotency và giới hạn của times(1)

Giả sử listener gửi email:

1. Listener gọi `EmailGateway.sendConfirmation(orderId, eventId)`.
2. Provider gửi thành công nhưng ứng dụng mất kết nối trước khi ghi nhận completion.
3. Event Publication Registry vẫn có publication chưa hoàn tất.
4. Recovery resubmit event, listener gọi gateway lần nữa.

Một test `verify(gateway, times(1)).sendConfirmation(...)` cho **lần callback đầu tiên** không chứng minh hệ thống sẽ chỉ gửi đúng một lần trong đời thực.

Phân biệt bốn đại lượng:

| Đại lượng | Ví dụ | Cách quan sát |
| --- | --- | --- |
| **Method invocation** | `gateway.send(...)` được gọi mấy lần trên mock. | Mockito `verify(..., times(n))`. |
| **Publication attempt** | Listener đã thử giao event mấy lần. | Registry lifecycle, log, metrics, integration instrumentation. |
| **Broker/network delivery** | Provider đã nhận record/request bao nhiêu lần. | Broker/HTTP integration logs và protocol ack. |
| **Business effect** | Khách nhận mấy email, tạo mấy reservation hoặc charge. | DB state/provider idempotency/reconciliation. |

Khi cần bảo đảm **business effect một lần**, dùng khóa idempotency, constraint, transaction hoặc cơ chế của provider, rồi test **side effect cuối cùng** bằng DB/integration assertions.

### 15.1. Tại sao eventId khác publicationId?

Một `OrderPlaced` có thể được giao cho nhiều listener target. Event ID nghiệp vụ ổn định khi retry; publication ID là định danh lần giao đến target của registry. Không dùng publication ID một cách thiếu suy xét làm khóa business idempotency xuyên các consumer.

### 15.2. Test fail-once khác test exactly-once

Một test có thể stub:

~~~java
when(risk.assess(expected))
        .thenThrow(new RiskUnavailableException("Timeout"))
        .thenReturn(RiskDecision.APPROVED);
~~~

Nhưng chuỗi stubbing này **không tự tạo retry**. Nếu service không có retry, lời gọi đầu tiên ném lỗi và kết thúc; phải chủ động gọi lại hoặc bật policy Spring Retry/Resilience4j thật qua proxy.

Ngay cả khi test thấy hai invocation, cần đối chiếu thứ gì được retry và liệu side effect trước lỗi đã commit hay chưa. Không thêm `times(1)` tùy tiện vào một workflow có retry hợp lệ.

## 16. Unit test với @Mock và module test với @MockitoBean

Trong **unit test thuần**, mock collaborator và khởi tạo service bằng constructor:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock RiskAssessment risk;
    @Mock OrderRepository repository;
    @Mock ApplicationEventPublisher publisher;

    @Test
    void sendsOneRequestWithCorrectIdentity() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        var total = new BigDecimal("129900.00");
        var request = new RiskRequest(
                orderId, customerId, total, "tenant-a", orderId);

        when(risk.assess(request))
                .thenReturn(RiskDecision.APPROVED);

        var service = new OrderService(
                risk, repository, publisher);
        service.place(orderId, customerId, total, "tenant-a");

        verify(risk).assess(request);
        verify(repository).save(any(OrderEntity.class));
        verify(publisher).publishEvent(any(OrderPlaced.class));
    }
}
~~~

Đoạn này đặt trong package `com.example.shop.orders`; cần imports `JUnit`, `MockitoExtension`, các lớp mẫu, Mockito và AssertJ phù hợp. `OrderEntity` ở `orders.internal` là public trong ví dụ. Vì `OrderService` được tạo bằng `new`, `@Transactional` **không có Spring AOP proxy**, repository và publisher đều là mock.

**Giới hạn:** nó chỉ xác nhận đúng method calls, không xác nhận DB commit, event listener hoặc Event Publication Registry. Vì vậy khi mục tiêu là kiểm chứng module `orders`, bài test `@ApplicationModuleTest` ở mục 5 có giá trị bổ sung thiết yếu.

### 16.1. Nếu test thực sự không cần verify interaction thì không nhất thiết mock

Một class domain thuần như `DiscountPolicy` có thể kiểm thử bằng `new DiscountPolicy()` và assert số tiền. Việc tạo spy để `verify(policy).calculate()` chỉ khiến test lệ thuộc chi tiết thực thi.

## 17. @MockitoSpyBean: theo dõi real bean, không thay thế contract test

`@MockitoBean` của Spring Framework dùng chiến lược **REPLACE_OR_CREATE** trong test `ApplicationContext`. Với `STANDALONE`, một bean thuộc module ngoài không được nạp thì mock có thể được tạo mới.

`@MockitoSpyBean` dùng chiến lược **WRAP** và cần có đúng một bean thật. Nếu muốn spy một listener hoặc service thật của module nhận, phải bootstrap đúng module có bean ấy. Trong `STANDALONE` của `orders`, spy `RiskAssessment` thuộc `compliance` có thể không dùng được vì không có implementation để wrap.

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealComplianceTests {

    @MockitoSpyBean RiskAssessment risk;

    // Chỉ hợp lệ nếu một bean RiskAssessment thật tồn tại
    // trong context; cần dữ liệu compliance và fixture phù hợp.
}
~~~

Khi spy có Spring AOP proxy, `verify` trên proxy thường vẫn hoạt động, nhưng **stubbing** cần cẩn trọng với cache/retry/transaction advice. Nếu method thật có side effect, `when(spy.method()).thenReturn(...)` có thể gọi method thật ngay lúc setup; ưu tiên `doReturn(...).when(spy).method()` khi thực sự cần stub, và xem tài liệu `AopTestUtils.getUltimateTargetObject(...)` khi advice can thiệp.

**Spy có đúng method invocation vẫn không chứng minh public API tuân thủ contract dữ liệu**, và việc spy toàn bộ method nội bộ thường làm test trở nên giòn.

### 17.1. enforceOverride=true: chỉ dùng khi bắt buộc bean phải tồn tại

~~~java
@MockitoBean(enforceOverride = true)
RiskAssessment risk;
~~~

Tùy chọn này yêu cầu một bean phù hợp **đã có trong context**. Nó thường không phù hợp với `STANDALONE` của `orders` khi implementation `compliance` bị loại khỏi bootstrap. Dùng `@MockitoBean` mặc định trong trường hợp tạo public collaborator giả, và có integration test khác không override để chứng minh wiring thật.

### 17.2. Spring Boot cũ

Các dự án Spring Boot trước 3.4 có thể dùng `@MockBean` và `@SpyBean` trong package Boot test. Từ Spring Boot 3.4, các annotation này bị deprecated để hướng tới `@MockitoBean`/`@MockitoSpyBean` của Spring Framework 6.2+. Không thay import máy móc nếu dependency chưa hỗ trợ.

## 18. Verify qua proxy hoặc nhiều bean: kiểm tra đúng đối tượng

Khi có nhiều implementation `RiskAssessment`, mock theo type có thể mơ hồ. Spring Test hỗ trợ chọn bằng `@Qualifier` hoặc `name`:

~~~java
@MockitoBean(name = "retailRiskAssessment")
RiskAssessment risk;
~~~

Nhưng test còn phải bảo đảm `OrderService` thật sự inject bean tên `retailRiskAssessment`. Nếu module bị giới hạn scan hoặc có fallback bean khác, test có thể verify **một mock không hề được SUT sử dụng**.

Một số tín hiệu debug:

- `Wanted but not invoked`: service không gọi mock mong đợi, gọi bean khác, nhánh code không chạy hoặc input không khớp.
- `TooManyActualInvocations`: cùng method/argument match được gọi nhiều hơn dự kiến; xem có retry, duplicate event hoặc logic gọi hai lần không.
- `ArgumentsAreDifferent`: method có chạy nhưng payload không đúng contract.
- Spring context không start: có thể annotation/qualifier chưa đúng hoặc ranh giới module test chưa được xác định đúng.

Không sửa mọi lỗi verify bằng `atLeastOnce()` hoặc `any()`. Hãy xác nhận **hợp đồng thực** và luồng xử lý trước khi nới điều kiện.

## 19. Provider contract và integration test: phần Mockito không chứng minh

Trong test `orders`, câu lệnh:

~~~java
when(risk.assess(expected)).thenReturn(RiskDecision.APPROVED);
~~~

chỉ mô phỏng tình huống “`compliance` trả `APPROVED`”. Nó **không chứng minh** implementation thật của `compliance` trả đúng kết quả với những dữ liệu đó, không chứng minh mapping tenant đúng, hoặc provider có thực sự chấp nhận idempotency key.

Cần thêm:

1. **Provider module test** trong `compliance`: implementation thật đưa ra `APPROVED`, `DENIED` và lỗi kỹ thuật đúng contract.
2. **Wiring integration test** với `DIRECT_DEPENDENCIES`: không override public `RiskAssessment`, khởi động cả `orders` và `compliance`.
3. **Adapter test** nếu `compliance` gọi HTTP/DB ngoài: kiểm tra request/headers/timeout và mapping lỗi với fake server hoặc Testcontainers.
4. **Security test**: không gửi nhầm tenant, không lộ dữ liệu nhạy cảm qua log hoặc message.

### 19.1. Skeleton integration test thật

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersAndComplianceIntegrationTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;
    @Autowired ComplianceFixture complianceFixture;

    @Test
    void approvedRiskFromRealProviderCreatesOrder() {
        UUID customerId = complianceFixture.createApprovedCustomer();
        UUID orderId = UUID.randomUUID();

        orders.place(orderId, customerId,
                new BigDecimal("129900.00"), "tenant-a");

        assertThat(repository.existsById(orderId)).isTrue();
    }
}
~~~

`ComplianceFixture` là **test fixture giả định**, không phải lớp do Spring Modulith tự cung cấp. Cần tự định nghĩa dữ liệu/bean phù hợp; mục tiêu của test này là **không mock `RiskAssessment`** để kiểm tra wiring và implementation thực.

### 19.2. Không thay contract test bằng số lời gọi

Nếu API `RiskAssessment` chuyển từ `BigDecimal` sang đơn vị tiền nhỏ nhất, hoặc thay ý nghĩa tenant, một unit test vẫn có thể verify đúng những argument mà chính test vừa stub. Cần kiểm thử tương thích hợp đồng **ở hai phía**. Mock phản ánh giả định của consumer; contract/provider integration test chứng minh giả định đó có thật.

## 20. Chất lượng test: tránh oververification

### 20.1. Bad example: verify mọi implementation step

~~~java
verify(validator).checkId(orderId);
verify(validator).checkAmount(amount);
verify(calculator).normalize(amount);
verify(factory).newOrder(...);
verify(repository).save(...);
verify(eventFactory).build(...);
verify(publisher).publishEvent(...);
~~~

Đây là một loạt lời gọi **có thể chỉ thuộc cách triển khai**. Refactor gộp validator, thay object factory hoặc tối ưu tính toán sẽ làm test fail dù kết quả vẫn đúng.

### 20.2. Better example: một contract interaction + kết quả quan sát được

~~~java
verify(risk).assess(expected);
assertThat(repository.findById(orderId)).isPresent();
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, orderId))
        .hasSize(1);
~~~

Nó chỉ verify **đường vượt boundary**, còn dữ liệu DB và event được assert bằng hạ tầng thật.

### 20.3. Khi nào verifyNoMoreInteractions có giá trị?

Nếu contract của một **gateway tính phí** quy định một command chỉ được gửi **một loại request duy nhất**, `verifyNoMoreInteractions(gateway)` sau các verify có thể bảo vệ chính sách đó. Nhưng nếu gateway có thêm phương thức hợp lệ như health check hoặc tracing metadata, assertion này dễ chặt quá mức. Hãy viết comment nêu **vì sao mọi tương tác bổ sung là vi phạm**.

### 20.4. Mutations giúp đánh giá sức bảo vệ

Thử giả định các thay đổi lỗi:

| Mutation trong production | Test nào bắt? |
| --- | --- |
| Truyền nhầm `tenantId` | `verify(risk).assess(expected)` hoặc `ArgumentCaptor`. |
| Gọi `assess` hai lần | `verify(times(1))` nếu giới hạn số lần là hợp đồng. |
| Gọi compliance cả khi amount bằng zero | `verifyNoInteractions(risk)` ở nhánh invalid. |
| `RiskDecision.DENIED` vẫn lưu order | Assertion DB/event nhánh denied. |
| Không phát `OrderPlaced` sau approved | `PublishedEvents` assertion. |
| `OrderEntity` lưu nhầm customer | Query database và assert field. |
| Import `compliance.internal.RiskRuleRepository` | `ApplicationModules.verify()`. |
| Implementation compliance thật trả sai quyết định | Provider contract/integration test, **không** được đảm bảo bởi mock. |

Một test chỉ nhiều dòng `verify` không chắc bảo vệ tốt hơn một test có vài assertions nhưng nhắm đúng contract.

## 21. CI quality gate: kết hợp bốn loại bằng chứng

| Gate | Mục tiêu | Công cụ/assertion |
| --- | --- | --- |
| **Architecture** | Giữ module `orders` chỉ dùng `compliance :: api`. | `ApplicationModules.verify()`. |
| **Contract interaction** | Đúng request/tenant/idempotency, không gọi trên input lỗi. | `@ApplicationModuleTest`, `@MockitoBean`, `verify`, `never`/captor. |
| **Business state** | Approved lưu order; denied/unavailable không lưu. | Repository thật, exception assertions. |
| **Event publication** | Approved phát đúng `OrderPlaced`. | `PublishedEvents`, không mock publisher. |
| **Provider contract** | `compliance` thật hiểu request và trả response đúng. | Module test của provider. |
| **Wiring** | Hai module tương tác thật. | `DIRECT_DEPENDENCIES`/integration test không override API. |
| **Transaction** | Rollback/commit đúng, listener after-commit không chạy sớm. | TransactionTemplate, database và listener test. |
| **Async/retry** | Publication lỗi được phục hồi không nhân business effect. | `Scenario`/Awaitility, Registry, idempotency marker. |
| **External protocol** | HTTP/broker wire contract đúng. | Fake server/Testcontainers, schema/headers assertions. |

### 21.1. Architecture test độc lập với Mockito

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

`verify()` phát hiện vi phạm dependency/named interface và một số ràng buộc cấu trúc của Spring Modulith. Nó **không kiểm tra runtime số lần gọi `risk.assess`**, nên phải chạy song song với interaction test.

### 21.2. Test isolation và các giới hạn

- `@MockitoBean` có cơ chế reset giữa test methods, nhưng reset mock **không dọn database**.
- Đặt dữ liệu theo UUID riêng; dọn publication/broker fixture nếu có các test event tích hợp.
- Khi test chạy song song, tránh chia sẻ mock hoặc context chưa được quản lý thread-safe.
- Đừng dùng `Thread.sleep` cố định để chờ event async; ưu tiên điều kiện chờ có timeout.
- Không bọc test cần after-commit bằng transaction test mặc định rollback.
- Không kết luận “exactly once toàn hệ thống” từ một Mockito verify trong một process.

## 22. Bài tập tình huống

Một ứng dụng Spring Modulith có:

- `checkout`: nhận lệnh xác nhận đơn và phát `CheckoutCompleted`.
- `payments`: public API `PaymentAuthorization.authorize(AuthorizationRequest)`.
- `marketing`: subscriber ngoài module cần nhận event sau commit.

Contract `payments` quy định request có `checkoutId`, `customerId`, `amount`, `currency`, `idempotencyKey`. Một lần checkout hợp lệ thực hiện một lệnh authorize theo **logical command**, còn provider có thể retry network với cùng idempotency key.

### Câu hỏi

1. Trong `@ApplicationModuleTest(STANDALONE)` của `checkout`, nên mock đối tượng nào?
2. Khi tổng tiền `0`, dùng `verifyNoInteractions` hay `verify(...)` kiểu nào để diễn đạt “không được gọi payment”?
3. Khi được phê duyệt, nên verify những field nào của `AuthorizationRequest`?
4. Vì sao `verify(payments).authorize(request)` chưa chứng minh dữ liệu checkout đã được commit?
5. Nếu payment bị `DECLINED`, nên assert gì ngoài `verify`?
6. Vì sao `verify(..., times(1))` không bảo đảm payment provider chỉ charge một lần qua timeout/retry?
7. Khi nào `InOrder` có giá trị trong quy trình thanh toán?
8. `verifyNoMoreInteractions(payments)` trong mọi test có rủi ro gì?
9. `PublishedEvents` thấy `CheckoutCompleted` có chứng minh `marketing` listener đã hoàn tất không?
10. Nếu `checkout` import `payments.internal.PaymentRepository` rồi mock repository đó, test nào phát hiện vi phạm kiến trúc?

### Đáp án tham khảo

1. Mock **public API** `payments.api.PaymentAuthorization` nếu test chỉ bảo vệ `checkout`; không mock service/repository/publisher của module hiện tại khi muốn kiểm tra DB và event.
2. `verifyNoInteractions(payments)` diễn đạt cấm mọi lời gọi; hoặc `verify(payments, never()).authorize(...)` nếu chỉ cấm hành động đó và tham số/matcher đã chọn bao phủ hợp đồng.
3. Đúng checkout/customer, tiền và currency, tenant nếu có, **idempotency key ổn định**; dùng record expected hoặc `ArgumentCaptor`.
4. Mockito chỉ biết một method invocation; phải query repository thật/kiểm tra transaction.
5. Không lưu trạng thái completed, không phát `CheckoutCompleted`, trả kết quả/exception nghiệp vụ đúng.
6. Một mock trong test chỉ ghi số invocation đã xảy ra tại thời điểm test; network retry, mất ack và provider side effects cần idempotency/reconciliation riêng.
7. Khi contract quy định bước kiểm tra điều kiện/consent phải xảy ra **trước** thao tác không thể đảo ngược; không dùng chỉ để bảo vệ thứ tự method nội bộ.
8. Dễ over-specify: thêm tương tác hợp lệ làm test vỡ dù hợp đồng chính vẫn đúng.
9. Không. Nó quan sát event phát; cần test listener after-commit/async, trạng thái side effect và registry nếu cần.
10. `ApplicationModules.of(...).verify()` kiểm tra module boundary; Mockito không hợp thức hóa import trái luật.

## 23. Checklist trước khi viết verify(...)

- [ ] Đã viết bằng lời **điều khoản hợp đồng** mà lệnh `verify` đang bảo vệ.
- [ ] Biết collaborator thuộc public API module khác hay I/O boundary, không phải chi tiết triển khai.
- [ ] Đã phân biệt method invocation, logical command, retry attempt và business effect.
- [ ] Nếu verify đúng một lần, **số lần** là yêu cầu được mô tả rõ; không có retry hợp lệ bị cấm nhầm.
- [ ] Verify đúng **target bean**, type/qualifier, arguments và tenant/ID quan trọng.
- [ ] Dùng record equality, `ArgumentCaptor` hoặc `argThat` theo mức phức tạp; không dùng `any()` quá rộng.
- [ ] Test nhánh invalid/denied có `never` hoặc `verifyNoInteractions` nếu thật sự cấm gọi.
- [ ] Không dùng `verifyNoMoreInteractions` chỉ vì muốn test “chặt”; có lý do hợp đồng cụ thể.
- [ ] Chỉ dùng `InOrder` khi thứ tự là nghĩa vụ nghiệp vụ hoặc protocol.
- [ ] Kết hợp interaction với assertion **state, exception, event**, không dừng ở số lần gọi.
- [ ] Giữ `OrderService`, repository và publisher thật trong module test cần kiểm chứng DB và `PublishedEvents`.
- [ ] `@MockitoBean` dùng trong Spring context ở phiên bản hỗ trợ; `@Mock` dùng cho unit test thuần.
- [ ] `@MockitoSpyBean` chỉ khi có real bean và có lý do quan sát hành vi thật.
- [ ] Không dùng `enforceOverride=true` khi `STANDALONE` cần tạo mock của bean ngoài module bị loại.
- [ ] Với async, không coi `timeout(times(1))` là bằng chứng không có lời gọi tiếp theo.
- [ ] Với retry/broker, có idempotency marker hoặc provider key và integration test kiểm tra side effect.
- [ ] Provider module có contract tests không dựa vào mock giả định từ consumer.
- [ ] Có integration/wiring test không override public API cần kiểm chứng.
- [ ] Chạy `ApplicationModules.verify()` để bảo vệ named interface và `allowedDependencies`.
- [ ] CI bao phủ interaction contracts, DB/event state, transaction/async và kiến trúc.

**Kết luận:** Trong Spring Modulith, `verify` có giá trị khi nó chứng minh **một nghĩa vụ tương tác ở module boundary hoặc I/O boundary**: đúng người nhận, đúng dữ liệu, không gọi khi bị cấm, hoặc số lần/thứ tự theo hợp đồng. Đừng verify mọi bước triển khai nội bộ. Hãy mock public collaborator bên ngoài module bằng `@MockitoBean`, giữ business logic, database và publisher thật trong `@ApplicationModuleTest`, rồi kết hợp `PublishedEvents`, contract/integration tests và `ApplicationModules.verify()` để bảo vệ cả hành vi lẫn kiến trúc.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes và `@MockitoBean` cho dependency module khác.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `PublishedEvents`, transactional listeners và `Scenario`.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, AOP, qualifier và spy.
- [Mockito — Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `verify`, `times`, `never`, `InOrder`, `timeout` và `verifyNoMoreInteractions`.

> Ghi chú áp dụng: ví dụ giả định Spring Framework 6.2+, Spring Modulith và Spring Data JPA có cấu hình thích hợp. Các entity, datasource, test fixtures, bean implementations và hạ tầng broker ngoài ví dụ cần được hoàn thiện theo dự án. Bài thuộc bước biên soạn STEP_4, chưa trải qua Content QA chuyên môn hoặc chạy kiểm thử Gradle.
