# Stub kết quả lỗi và kết quả thành công

## 1. Vì sao phải kiểm thử cả thành công lẫn thất bại?

Trong một ứng dụng Spring Modulith, module `orders` có thể hỏi module `customers` xem khách hàng có được phép đặt hàng không. Nếu nhận kết quả **được phép**, `orders` lưu đơn hàng và phát `OrderPlaced`. Nếu nhận kết quả **bị từ chối**, module không được tạo đơn. Nếu collaborator bị **lỗi kỹ thuật** — ví dụ service khách hàng hoặc database không sẵn sàng — module cũng không được âm thầm coi đó là một lần kiểm tra hợp lệ.

Khi viết test, ta thường cần điều khiển câu trả lời của collaborator. **Stubbing** là cấu hình cho test double trả một giá trị hoặc ném một exception khi được gọi với dữ liệu nhất định. Với Mockito, hai dạng quen thuộc nhất là:

~~~java
when(customers.check(customerId))
        .thenReturn(EligibilityDecision.APPROVED);

when(customers.check(customerId))
        .thenThrow(new CustomerEligibilityUnavailableException());
~~~

Nhưng hai dòng ấy chỉ là **test setup**, chưa phải kết quả kiểm thử. Điều quan trọng là xác minh module đang kiểm thử đã phản ứng đúng: dữ liệu nào được commit hoặc rollback, sự kiện nào được phát, ngoại lệ nào đi ra ngoài, và có lời gọi không mong muốn nào xảy ra không.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, chủ đề thuộc chương **Mock và spy**. Mục tiêu chung là rèn kỹ năng kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, kiểm thử `@ApplicationModuleTest`, sự kiện, database và tích hợp; đưa các phép kiểm tra này vào quality gate CI để ngăn phụ thuộc sai và hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **success result**, **business rejection** và **technical failure** trước khi stub.
2. Dùng `thenReturn`, `thenThrow`, `doThrow`, `doReturn`, `thenAnswer` và các API BDD theo đúng mục tiêu.
3. Viết module test `STANDALONE` có mock **public collaborator ngoài module** nhưng vẫn giữ service, JPA repository và event publisher thật.
4. Kiểm tra cả nhánh thành công, từ chối, exception, lỗi dữ liệu hợp đồng và lần gọi lại.
5. Phân biệt kết quả giả lập từ Mockito với transaction thực, callback sau commit và hành vi của provider thật.
6. Tránh lỗi stub nhầm tham số, mock không được inject, strict stubbing, spy gọi method thật và test xanh giả.
7. Kết hợp test unit, module, contract, integration và architecture test trong CI.

## 2. Ba loại kết quả không được đánh đồng

Một phương thức `CustomerEligibility.check(customerId)` có thể dẫn đến ba nhóm kết quả:

| Trường hợp | Ví dụ | Ngữ nghĩa | Kỳ vọng ở module `orders` |
| --- | --- | --- | --- |
| **Thành công** | Trả `APPROVED`. | Khách hàng hợp lệ để tiếp tục nghiệp vụ. | Lưu order, phát một `OrderPlaced`. |
| **Từ chối nghiệp vụ** | Trả `DENIED`. | Hệ thống đã kiểm tra thành công, nhưng quy tắc không cho đặt hàng. | Không lưu order, không phát `OrderPlaced`, trả lỗi nghiệp vụ phù hợp. |
| **Lỗi kỹ thuật** | Ném `CustomerEligibilityUnavailableException`. | Không thể xác định điều kiện hợp lệ vì phụ thuộc thất bại. | Không tạo order hoặc event xác nhận; để caller/chính sách retry xử lý đúng. |

**DENIED không phải tương đương với service unavailable.** Nếu module `orders` chuyển timeout thành `DENIED`, người dùng sẽ nhận lời từ chối nghiệp vụ sai. Nếu chuyển `DENIED` thành exception có thể retry, hệ thống có thể gọi lại vô ích một quyết định từ chối đã rõ ràng.

Một hệ thống khác có thể mô hình hóa lỗi kỹ thuật bằng một kiểu `Result.Failure` thay vì ném exception. Khi đó hãy stub **đúng contract thật**. Bài này chọn `enum` cho quyết định nghiệp vụ và unchecked exception cho lỗi kỹ thuật để minh họa rõ.

### 2.1. Hành vi quan sát được quan trọng hơn dòng stub

~~~mermaid
flowchart TD
    A["orders.place(orderId, customerId)"] --> B["customers.check(customerId)"]
    B --> C{"Stub result"}
    C -->|"APPROVED"| D["Save order"]
    D --> E["publishEvent(OrderPlaced)"]
    C -->|"DENIED"| F["OrderRejectedException"]
    F --> G["Không save, không publish"]
    C -->|"Throw technical exception"| H["Báo lỗi phụ thuộc"]
    H --> G
~~~

Sơ đồ giả định code xác minh khách hàng **trước khi lưu/phát**. Nếu thực tế lỗi xảy ra sau `publishEvent`, một test `PublishedEvents` vẫn có thể ghi nhận lời gọi phát dù transaction bị rollback; cần kiểm thử after-commit và persistence riêng.

## 3. Thiết kế ví dụ theo đúng module boundary

Giả sử application root là `com.example.shop`. Theo cách phát hiện module mặc định của Spring Modulith, các package con trực tiếp là application module:

~~~text
com.example.shop
├── ShopApplication.java
├── customers
│   ├── api
│   │   ├── EligibilityDecision.java
│   │   ├── CustomerEligibility.java
│   │   ├── CustomerEligibilityUnavailableException.java
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
        └── OrderRepository.java
~~~

**Ranh giới kiểm thử:** `orders` được chạy thật trong `@ApplicationModuleTest(STANDALONE)`, còn API `customers.api.CustomerEligibility` được thay bằng mock. Test không cần biết `customers.internal.CustomerRepository` hay database của module `customers` hoạt động như thế nào.

~~~mermaid
flowchart LR
    T["@ApplicationModuleTest(orders)"] --> O["orders.OrderService THẬT"]
    O --> C["customers.api.CustomerEligibility MOCK"]
    O --> R["orders.OrderRepository THẬT"]
    O --> P["ApplicationEventPublisher THẬT"]
    R --> DB[("Test database")]
    P --> EV["PublishedEvents"]
    X["customers.internal.CustomerEligibilityService"] -. "Không bootstrap ở STANDALONE" .-> C
~~~

### 3.1. Công bố API của module customers

File `customers/api/EligibilityDecision.java`:

~~~java
package com.example.shop.customers.api;

public enum EligibilityDecision {
    APPROVED,
    DENIED
}
~~~

File `customers/api/CustomerEligibility.java`:

~~~java
package com.example.shop.customers.api;

import java.util.UUID;

public interface CustomerEligibility {
    EligibilityDecision check(UUID customerId);
}
~~~

File `customers/api/CustomerEligibilityUnavailableException.java`:

~~~java
package com.example.shop.customers.api;

public class CustomerEligibilityUnavailableException
        extends RuntimeException {

    public CustomerEligibilityUnavailableException(String message) {
        super(message);
    }
}
~~~

File `customers/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.customers.api;
~~~

Trong ví dụ, `DENIED` là kết quả bình thường của contract, còn `CustomerEligibilityUnavailableException` diễn đạt lỗi hệ thống không thể xác minh. Module `customers` chịu trách nhiệm triển khai interface trong package `internal`; module `orders` **không** truy cập repository hoặc implementation nội bộ ấy.

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "customers :: api"
)
package com.example.shop.orders;
~~~

Quy tắc `allowedDependencies` cho phép module `orders` import API công khai của `customers`, không cho phép import `customers.internal.*`. **Mockito không sửa được vi phạm ranh giới này**; cần architecture test `ApplicationModules.verify()` độc lập.

### 3.2. Repository và event của module orders

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

    protected OrderEntity() {} // JPA constructor.

    public OrderEntity(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public UUID getCustomerId() {
        return customerId;
    }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.UUID;

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

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

Những kiểu này cố ý tối giản để tập trung vào nhánh thành công/lỗi. Trong production cần xác định aggregate lifecycle, unique constraint, transaction/concurrency và event idempotency phù hợp. Repository là implementation thuộc **chính module `orders`**, nên sẽ giữ thật trong module integration test.

### 3.3. Service thật phân biệt approved, denied và unavailable

File `orders/OrderRejectedException.java`:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public class OrderRejectedException extends RuntimeException {

    public OrderRejectedException(UUID customerId) {
        super("Order rejected for customer " + customerId);
    }
}
~~~

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.customers.api.EligibilityDecision;
import com.example.shop.orders.events.OrderPlaced;
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
    private final ApplicationEventPublisher publisher;

    public OrderService(CustomerEligibility customers,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.customers = customers;
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId, UUID customerId) {
        var decision = Objects.requireNonNull(
                customers.check(customerId),
                "Customer eligibility response must not be null");

        if (decision == EligibilityDecision.DENIED) {
            throw new OrderRejectedException(customerId);
        }

        orders.save(new OrderEntity(orderId, customerId));
        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, customerId, Instant.now()));
    }
}
~~~

Hành vi service theo contract:

- `APPROVED`: lưu order và phát event.
- `DENIED`: ném `OrderRejectedException`, **chưa lưu/chưa phát**.
- Collaborator ném `CustomerEligibilityUnavailableException`: lỗi truyền qua service; do chưa lưu/chưa phát nên không tạo order.
- Collaborator trả `null` trái contract: `Objects.requireNonNull` báo lỗi cấu hình/dữ liệu, không mặc định coi là approved hoặc denied.

`@Transactional` có hiệu lực khi lời gọi đi qua Spring proxy. Nếu mock `OrderService` thay vì mock collaborator `customers`, các nhánh này **không còn được thực thi thật**.

## 4. Chọn đúng phạm vi test và annotation

Spring Modulith hỗ trợ `@ApplicationModuleTest` với các mode:

| BootstrapMode | Context được tải | Ảnh hưởng đến việc mock |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Module chứa lớp test. | Implementation ngoài module không nạp; `@MockitoBean` tạo mock public API cần thiết. |
| `DIRECT_DEPENDENCIES` | Module đang test và các module phụ thuộc trực tiếp. | Có thể dùng `CustomerEligibility` thật để kiểm tra kết nối giữa modules. |
| `ALL_DEPENDENCIES` | Module đang test và toàn bộ cây phụ thuộc. | Test rộng hơn; không nên dùng chỉ để né lỗi thiếu bean. |

Trong Spring Framework 6.2+ (ví dụ Spring Boot 3.4+):

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean CustomerEligibility customers;
~~~

`@MockitoBean` đăng ký một mock **trong Spring Test ApplicationContext**, dùng chiến lược `REPLACE_OR_CREATE` mặc định. Với `STANDALONE`, implementation `customers` không có trong context; Spring tạo một bean mock mới cho public interface để inject vào `OrderService` thật.

**Không dùng `@MockitoBean(enforceOverride = true)` cho trường hợp này**, vì tùy chọn ấy yêu cầu bean thật đã hiện diện để thay; khi module ngoài bị loại khỏi context, test có thể không khởi động.

### 4.1. @Mock khác @MockitoBean

~~~java
@Mock CustomerEligibility customers;       // Mockito unit test object.
@MockitoBean CustomerEligibility customers; // Spring context bean override.
~~~

`@Mock` trong test thuần dùng `MockitoExtension`/Mockito initialization; nó không tự đưa mock vào Spring context. `@MockitoBean` dành cho những bài test có Spring ApplicationContext như `@ApplicationModuleTest`.

Trong Spring Boot cũ chưa có `@MockitoBean`, dự án có thể dùng `@MockBean` của Spring Boot theo phiên bản phù hợp. `@MockBean`/`@SpyBean` của Boot bị deprecated từ 3.4 để chuyển sang Framework annotations; **đừng đổi import mà chưa kiểm tra dependency**.

## 5. Stubbing một kết quả thành công

Mẫu cơ bản:

~~~java
when(customers.check(customerId))
        .thenReturn(EligibilityDecision.APPROVED);
~~~

Nó có hai phần:

1. `when(customers.check(customerId))`: chỉ định lời gọi cần stub với **đúng customer ID**.
2. `thenReturn(APPROVED)`: cung cấp kết quả mà module `orders` sẽ nhận trong test.

Nếu `orders` vô tình gọi `check(otherId)`, stub cụ thể sẽ không khớp; với Mockito mock và enum, mặc định trả `null`, và code service sẽ báo vi phạm contract thay vì lặng lẽ tạo order.

### 5.1. Module integration test đầy đủ: nhánh approved

Đặt test trong `com.example.shop.orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.customers.api.EligibilityDecision;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderPlacementModuleTests {

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    // Chỉ thay public collaborator của module customers.
    @MockitoBean CustomerEligibility customers;

    @Test
    void approvedCustomerCreatesOrderAndOneEvent(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(customers.check(customerId))
                .thenReturn(EligibilityDecision.APPROVED);

        service.place(orderId, customerId);

        verify(customers, times(1)).check(customerId);
        assertThat(repository.findById(orderId))
                .get()
                .satisfies(order ->
                        assertThat(order.getCustomerId())
                                .isEqualTo(customerId));

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId()).isEqualTo(customerId);
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.occurredAt()).isNotNull();
                });
    }
}
~~~

**Bằng chứng nhận được:**

- **Interaction:** `orders` hỏi đúng `customerId` qua public API một lần.
- **Persistence:** `OrderRepository` thật nhìn thấy order được lưu bởi `OrderService` thật.
- **Publication:** Spring event publisher thật đã phát chính xác một `OrderPlaced` cho order đó.

Test cần Spring Data JPA, test datasource/transaction manager, schema và dependency test tương ứng. Không gắn `@Transactional` bao ngoài nếu mục tiêu mở rộng là quan sát commit của transaction service hoặc listener `AFTER_COMMIT`.

### 5.2. Vì sao không dừng ở verify(mock)?

~~~java
verify(customers).check(customerId);
~~~

Assertion này **chưa đủ**: service có thể hỏi đúng khách hàng rồi không lưu order, lưu nhầm customer hoặc quên phát event. Đó là lý do test approved kết hợp **interaction**, **state** và **event** assertions.

Trong module test, không mock `OrderRepository` hay `ApplicationEventPublisher` nếu chính điều bạn cần chứng minh là DB persistence và Spring event publication.

## 6. Stub kết quả từ chối hợp lệ theo nghiệp vụ

Đây là kết quả bình thường của interface, không phải một lần gọi lỗi:

~~~java
when(customers.check(customerId))
        .thenReturn(EligibilityDecision.DENIED);
~~~

Vì service định nghĩa `DENIED` là một quyết định rõ ràng, test phải assert **không có đơn hàng và không có event**.

Trong cùng `OrderPlacementModuleTests`, thêm:

~~~java
@Test
void deniedCustomerDoesNotPersistOrPublish(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.check(customerId))
            .thenReturn(EligibilityDecision.DENIED);

    assertThatThrownBy(() -> service.place(orderId, customerId))
            .isInstanceOf(OrderRejectedException.class)
            .hasMessageContaining(customerId.toString());

    verify(customers).check(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Thêm import khi tích hợp vào lớp test:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Tránh gọi `thenThrow(...)` chỉ vì muốn test từ chối nếu contract thật trả về `DENIED`. Nếu test chỉ stub exception, nhánh `if (decision == DENIED)` của production sẽ **không được chạy**, và lỗi hồi quy của nhánh ấy không bị phát hiện.

### 6.1. Vì sao “không có event” đúng trong case này?

Trong `OrderService.place`, kiểm tra eligibility chạy **trước** `orders.save` và `publisher.publishEvent`. Vì vậy với `DENIED`, đường thực thi không tới lời gọi publish.

Đừng suy ra quy tắc chung “cứ transaction rollback thì PublishedEvents rỗng”. Khi code đã gọi `publishEvent` rồi mới rollback, bộ quan sát `PublishedEvents` có thể vẫn thấy lời gọi; việc callback `AFTER_COMMIT` có chạy hay không là câu hỏi khác.

## 7. Stub exception: lỗi kỹ thuật không phải từ chối nghiệp vụ

Mockito cho phép một mock ném exception:

~~~java
when(customers.check(customerId))
        .thenThrow(new CustomerEligibilityUnavailableException(
                "Customer service timed out"));
~~~

Test của module `orders` cần chứng minh lỗi không bị “nuốt” hoặc biến thành kết quả approved:

~~~java
@Test
void unavailableCustomerServiceDoesNotPersistOrPublish(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    var failure = new CustomerEligibilityUnavailableException(
            "Customer service timed out");

    when(customers.check(customerId)).thenThrow(failure);

    assertThatThrownBy(() -> service.place(orderId, customerId))
            .isSameAs(failure);

    verify(customers).check(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Đoạn test thuộc lớp mục 5, cần import:

~~~java
import com.example.shop.customers.api.CustomerEligibilityUnavailableException;
~~~

Vì exception phát sinh **trước khi ghi dữ liệu**, test chứng minh service không ghi/phát. Với một service ghi dữ liệu **trước** khi gọi collaborator rồi bị lỗi, test phải dùng transaction thật để kiểm tra rollback và xác nhận row không được commit.

### 7.1. thenThrow(instance) và thenThrow(Class)

Mockito có hai kiểu thông dụng:

~~~java
when(customers.check(customerId))
        .thenThrow(new CustomerEligibilityUnavailableException(
                "Unavailable"));

when(customers.check(customerId))
        .thenThrow(IllegalStateException.class);
~~~

Với **exception instance**, test kiểm soát message, cause và danh tính object; phù hợp cho test ánh xạ lỗi. Với **exception class**, Mockito tạo exception của class theo cơ chế hỗ trợ; phù hợp khi chỉ cần xác nhận type và class có constructor hợp lệ.

**Đừng test cứng nội dung stack trace**. Những thông tin ấy không phải contract nghiệp vụ và có thể thay đổi theo runtime/Mockito version.

### 7.2. Mockito không cho ném checked exception tùy tiện

Nếu method `CustomerEligibility.check(UUID)` **không khai báo** `throws IOException`, stubbing:

~~~java
when(customers.check(customerId))
        .thenThrow(new IOException("timeout"));
~~~

có thể bị Mockito từ chối bằng `MockitoException: Checked exception is invalid for this method!`. Đó là do Java checked-exception contract, không phải Spring Modulith.

Các hướng đúng:

- Dùng **unchecked exception** được public API định nghĩa cho lỗi kỹ thuật, như `CustomerEligibilityUnavailableException`.
- Nếu interface thực sự khai báo checked exception, test có thể stub checked exception hợp lệ.
- Không thay đổi signature production chỉ để phục vụ một test nhân tạo; chọn đúng failure mode của collaborator.

## 8. Khi nào dùng doThrow, doNothing và doAnswer?

`when(...).thenThrow(...)` phù hợp với method **có giá trị trả về**. Với method `void`, không thể viết `when(port.send(...))` vì biểu thức `void` không có giá trị để truyền vào `when`.

Giả sử một port ngoài module:

~~~java
public interface NotificationGateway {
    void sendOrderConfirmation(UUID orderId);
}
~~~

### 8.1. Void method thất bại

~~~java
doThrow(new IllegalStateException("SMTP unavailable"))
        .when(notificationGateway)
        .sendOrderConfirmation(orderId);
~~~

`doThrow` là lựa chọn đúng cho phương thức `void`. Test sau đó gọi class thực thi use case rồi assert exception hoặc chính sách recovery của use case, **không chỉ verify số lần gọi mock**.

### 8.2. Void method thành công

Mockito mock mặc định **không làm gì** khi method `void` được gọi. Nếu muốn diễn đạt rõ:

~~~java
doNothing().when(notificationGateway)
        .sendOrderConfirmation(orderId);
~~~

`doNothing` có giá trị khi muốn nhấn mạnh nhánh thành công hoặc thiết lập chuỗi hành vi. Nhưng thông thường nó **không cần thiết** cho mock method `void`; thêm stubbing không sử dụng còn có thể gây cảnh báo dưới strict stubbing.

### 8.3. doAnswer để kiểm soát phản hồi tùy tham số

~~~java
doAnswer(invocation -> {
    UUID actualOrderId = invocation.getArgument(0);
    if (!actualOrderId.equals(orderId)) {
        throw new IllegalArgumentException("Unexpected order ID");
    }
    return null; // Method void.
}).when(notificationGateway)
  .sendOrderConfirmation(any(UUID.class));
~~~

`doAnswer` hữu ích khi hành vi test double cần tính theo input, đếm attempt hoặc mô phỏng callback. Tuy nhiên đừng biến mock thành một **hệ thống giả quá phức tạp** với nhiều state, lock và timer; khi đó fake implementation có contract riêng thường dễ hiểu hơn.

### 8.4. Không dùng doThrow để che một real side effect đã xảy ra

Nếu service gọi `notificationGateway` **sau khi đơn hàng commit**, ném exception từ mock chỉ mô phỏng phần notification lỗi; nó không tự chứng minh email đã/không được gửi hay Event Publication Registry đã cập nhật đúng.

Để kiểm thử đường listener `@ApplicationModuleListener`, cần module/integration test có transaction commit, listener được nạp thật, và một gateway mock/fake ở **ranh giới I/O** của module nhận.

## 9. Success, business rejection và technical failure trong cùng test suite

Một test suite nên bao phủ ít nhất ma trận sau:

| Kịch bản | Stub `check(customerId)` | DB orders | `OrderPlaced` | Exception dự kiến |
| --- | --- | --- | --- | --- |
| Khách hợp lệ | `APPROVED` | Có một order. | Đúng một event. | Không. |
| Khách bị từ chối | `DENIED` | Không có order mới. | Không. | `OrderRejectedException`. |
| Service customers lỗi | `thenThrow(CustomerEligibilityUnavailableException)` | Không có order mới. | Không. | Technical exception. |
| Stub trả null trái contract | `thenReturn(null)` | Không. | Không. | `NullPointerException` theo guard. |
| Gọi sai customer ID | Stub đúng ID, service gọi nhầm ID. | Không được tạo order. | Không. | Contract guard/interaction assertion bắt lỗi. |
| Lỗi tạm thời rồi gọi lại | `thenThrow(...).thenReturn(APPROVED)` | Order chỉ có sau lần gọi thành công. | Một event phù hợp. | Lần đầu ném lỗi. |

**Ma trận phải khớp production contract.** Với hệ thống có typed `Result<Approved, Rejected, Unavailable>`, failure có thể là một giá trị thay vì exception. Không bắt mọi module dùng đúng enum/exception của ví dụ.

### 9.1. Test null để bắt vi phạm hợp đồng

~~~java
@Test
void nullEligibilityResponseFailsClosed(PublishedEvents events) {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.check(customerId)).thenReturn(null);

    assertThatThrownBy(() -> service.place(orderId, customerId))
            .isInstanceOf(NullPointerException.class)
            .hasMessageContaining("eligibility");

    verify(customers).check(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Một mock chưa được stub thường trả `null` cho enum/object return type. **Không dựa vào default answer như một kịch bản nghiệp vụ chính thức**; khi cần test vi phạm hợp đồng, stub `null` rõ ràng và assert đúng guard. Nếu hệ thống có business fallback rõ ràng, test phải phản ánh chính sách đó thay vì luôn ném `NullPointerException`.

## 10. Stub chuỗi kết quả: lỗi lần đầu, thành công lần sau

Mockito hỗ trợ **consecutive stubbing** khi một mock method được gọi nhiều lần với cùng arguments:

~~~java
when(customers.check(customerId))
        .thenThrow(new CustomerEligibilityUnavailableException(
                "Temporary outage"))
        .thenReturn(EligibilityDecision.APPROVED);
~~~

Lời gọi đầu tiên ném lỗi; lời gọi thứ hai trả `APPROVED`. Với `OrderService.place` hiện tại, **không có retry tự động trong service**. Bởi vậy test phải chủ động gọi service hai lần để mô phỏng caller retry sau lỗi:

~~~java
@Test
void explicitSecondAttemptSucceedsAfterTemporaryFailure(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.check(customerId))
            .thenThrow(new CustomerEligibilityUnavailableException(
                    "Temporary outage"))
            .thenReturn(EligibilityDecision.APPROVED);

    assertThatThrownBy(() -> service.place(orderId, customerId))
            .isInstanceOf(CustomerEligibilityUnavailableException.class);

    assertThat(repository.existsById(orderId)).isFalse();

    // Caller thử lại rõ ràng; đây KHÔNG phải retry tự động.
    service.place(orderId, customerId);

    verify(customers, times(2)).check(customerId);
    assertThat(repository.existsById(orderId)).isTrue();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .hasSize(1);
}
~~~

Đây là một kịch bản có chủ đích: lần đầu exception **trước khi lưu/phát**, lần hai mới ghi order. Trong thực tế, retry cùng một command cần idempotency/unique constraint; nếu lần đầu **đã commit** nhưng caller không nhận được phản hồi, retry toàn bộ use case có thể tạo event mới. Không suy ra an toàn của mọi retry chỉ từ bài test này.

### 10.1. Nếu service có @Retryable hoặc retry policy riêng

Giả sử production có `@Retryable` hoặc Resilience4j retry ở boundary. Khi đó lời gọi `service.place(...)` **một lần** có thể gọi collaborator nhiều lần trước khi trả kết quả.

Một test đúng phải:

1. Nạp **bean thật qua Spring proxy**, không dựng service bằng `new` nếu muốn kiểm tra AOP retry.
2. Cấu hình policy thử lại đúng trên boundary mà production sử dụng.
3. Stub chuỗi lỗi → thành công theo số attempt cho phép.
4. Assert kết quả DB/event **cuối cùng** và số lần gọi collaborator.
5. Có test vượt quá giới hạn retry, kiểm tra exception/fallback đúng.

Không thêm `@Retryable` vào service chỉ để làm test minh họa cho stubbing; retry phải là lựa chọn thiết kế có cân nhắc idempotency, transaction, delay, jitter và failure classification.

### 10.2. Quy tắc khi chuỗi stubbing kết thúc

Nếu cấu hình:

~~~java
when(customers.check(customerId))
        .thenReturn(EligibilityDecision.DENIED)
        .thenReturn(EligibilityDecision.APPROVED);
~~~

lời gọi một trả `DENIED`, lời gọi tiếp theo trả `APPROVED`; sau khi hết các hành vi đã khai báo, Mockito tiếp tục dùng hành vi cuối cùng cho các lời gọi kế tiếp, trừ khi test cấu hình lại. Đừng viết test phụ thuộc số lần ngẫu nhiên của một callback async hoặc một cache; hãy chủ động xác định số attempt cần kiểm chứng.

## 11. BDDMockito: cùng ý tưởng, cách diễn đạt Given–When–Then

Mockito có API dạng Behavior-Driven Development:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;

// Given: quyết định hợp lệ.
given(customers.check(customerId))
        .willReturn(EligibilityDecision.APPROVED);

// When: chạy nghiệp vụ thật.
service.place(orderId, customerId);

// Then: verify hợp đồng tương tác và kết quả DB/event.
then(customers).should().check(customerId);
~~~

Kết quả và ý nghĩa tương ứng với `when(...).thenReturn(...)` + `verify(...)`. **BDDMockito không tự làm test có độ bao phủ cao hơn**; chất lượng đến từ assertion và lựa chọn điều cần mock.

Để stub exception với method trả giá trị:

~~~java
given(customers.check(customerId))
        .willThrow(new CustomerEligibilityUnavailableException(
                "Customer service down"));
~~~

Với `void` method, sử dụng cú pháp BDD kiểu:

~~~java
willThrow(new IllegalStateException("SMTP down"))
        .given(notificationGateway)
        .sendOrderConfirmation(orderId);
~~~

**Lưu ý:** Trong `BDDMockito`, tên `willThrow` khi dùng với `given(...)` và `willThrow(...).given(mock).voidMethod()` có overload khác nhau. Chọn cú pháp phù hợp chữ ký method.

## 12. Stub theo tham số: một lỗi phổ biến khiến test xanh giả

So sánh hai cách:

~~~java
// Chặt chẽ: quyết định chỉ gắn với đúng customer.
when(customers.check(customerId))
        .thenReturn(EligibilityDecision.APPROVED);

// Rộng: bất kỳ UUID hợp lệ nào cũng được phép.
when(customers.check(any(UUID.class)))
        .thenReturn(EligibilityDecision.APPROVED);
~~~

Nếu `OrderService` bị bug và truyền sai `customerId`, cách thứ hai vẫn trả `APPROVED`; test có thể vô tình lưu đơn cho khách hàng sai. Vì vậy:

- Stub input cụ thể khi **định danh** là thành phần của hợp đồng.
- Dùng `eq(customerId)`, `argThat`, `ArgumentCaptor` khi cần mô tả điều kiện phức tạp.
- Nếu method có nhiều tham số và bạn dùng matcher cho một tham số, các tham số còn lại cũng phải là matcher phù hợp trong cùng lời gọi stub/verify.
- Không dùng `any()` chỉ để tránh làm rõ dữ liệu fixture.

### 12.1. Stub cho nhiều khách hàng với kết quả khác nhau

~~~java
UUID approvedId = UUID.randomUUID();
UUID deniedId = UUID.randomUUID();

when(customers.check(approvedId))
        .thenReturn(EligibilityDecision.APPROVED);
when(customers.check(deniedId))
        .thenReturn(EligibilityDecision.DENIED);
~~~

Khi cùng test thực hiện hai yêu cầu độc lập, có thể xác nhận order của khách approved được tạo, còn của khách denied bị từ chối. Nếu production gọi nhầm ID, tương tác hoặc default result sẽ giúp bắt lỗi.

### 12.2. thenAnswer khi đầu ra phụ thuộc input

~~~java
Set<UUID> approvedCustomers = Set.of(approvedId);

when(customers.check(any(UUID.class)))
        .thenAnswer(invocation -> {
            UUID customerId = invocation.getArgument(0);
            return approvedCustomers.contains(customerId)
                    ? EligibilityDecision.APPROVED
                    : EligibilityDecision.DENIED;
        });
~~~

`thenAnswer` hợp lý với nhiều input cần mô phỏng quy luật đơn giản. Tuy nhiên, nếu `Answer` có hàng chục nhánh, network timer và trạng thái khó kiểm soát, một **fake collaborator** có implement public interface và unit tests riêng có thể dễ bảo trì hơn. Đừng viết lại toàn bộ logic `customers` bằng một fake rồi coi nó đã chứng minh implementation thật.

## 13. Không stub kết quả lỗi bằng cách mock chi tiết triển khai

Giả sử thay vì mock `customers.api.CustomerEligibility`, test mock `customers.internal.CustomerRepository`:

~~~java
@MockitoBean
CustomerRepository customerRepository;
~~~

Đây là **sai ranh giới** nếu module `orders` đang import repository nội bộ từ `customers`: mock có thể giúp context khởi động nhưng vẫn vi phạm boundary. Cách thiết kế đúng là `orders` gọi API công khai, module `customers` tự xử lý repository của mình.

Tương tự, trong module test của `orders`, nếu mock `OrderService`, `OrderRepository` hoặc `ApplicationEventPublisher` rồi chỉ verify method, các test không còn chứng minh transaction, DB và event thực.

| Khi kiểm thử `orders` | Nên giả lập? | Lý do |
| --- | --- | --- |
| `customers.api.CustomerEligibility` | **Có**, nếu mục tiêu là cô lập `orders`. | Public collaborator thuộc module khác. |
| `orders.OrderService` | **Không**. | Đây là system under test. |
| `orders.internal.OrderRepository` | Không trong module integration test DB. | Cần JPA/persistence thật để kiểm chứng. |
| `ApplicationEventPublisher` | Không khi test `PublishedEvents`. | Cần luồng event thật. |
| External HTTP client phía `customers` | Có thể fake trong test của `customers`. | I/O boundary, cần adapter/contract tests riêng. |

### 13.1. Một mock success không chứng minh provider thật thành công

`when(customers.check(id)).thenReturn(APPROVED)` chỉ thiết lập tiền đề **giả định**. Nó không chứng minh implementation thật của `CustomerEligibilityService` trả `APPROVED` cho đúng dữ liệu, không chứng minh query database đúng hoặc credential ngoài hệ thống còn hợp lệ.

Vì vậy cần:

- Provider module tests cho `customers` với dữ liệu khách hàng active/blocked.
- Contract tests cho public API và cách mapping errors.
- Integration test nạp `orders` + `customers` thật khi cần xác nhận wiring.

Một mock failure cũng không chứng minh provider thật luôn ném đúng exception: test phải dựa trên **public contract có tài liệu và kiểm chứng**.

## 14. Mock hay spy khi muốn mô phỏng lỗi?

**Mock** không gọi implementation thật trừ khi được cấu hình để làm thế. **Spy** thường gọi method thật khi chưa stub.

Trong Spring Framework 6.2+:

~~~java
@MockitoBean
CustomerEligibility customers; // Tạo/thay bean bằng mock.

@MockitoSpyBean
SomeRealComponent component;    // Wrap một bean thật.
~~~

`@MockitoSpyBean` yêu cầu **có đúng một bean thật**. Trong `@ApplicationModuleTest(STANDALONE)` của `orders`, implementation `customers` không được nạp; `@MockitoSpyBean CustomerEligibility` vì vậy không dùng để chữa lỗi thiếu bean.

### 14.1. Bẫy stubbing spy bằng when(...)

~~~java
when(spy.expensiveOperation())
        .thenReturn(result);
~~~

Với spy, `expensiveOperation()` có thể chạy **ngay lúc setup**, tạo side effect HTTP/DB hoặc exception trước khi test bắt đầu phần `When`. Khi muốn stub spy mà **không gọi method thật lúc stubbing**, dùng:

~~~java
doReturn(result).when(spy).expensiveOperation();
doThrow(new IllegalStateException("Simulated"))
        .when(spy).expensiveOperation();
~~~

Những đoạn này là cú pháp minh họa, cần biến `spy`, `result` và method thực. Nếu bean spy có Spring AOP như `@Cacheable`, `@Transactional` hoặc `@Retryable`, việc stub qua proxy có thể khác việc stub trực tiếp trên spy target. Tài liệu Spring Framework hướng dẫn `AopTestUtils.getUltimateTargetObject(...)` cho những trường hợp cần bỏ proxy trước khi stub.

**Đừng chọn spy chỉ vì muốn mô phỏng exception.** Với collaborator ngoài module không có bean thật, `@MockitoBean` + `thenThrow` đơn giản và ít side effect hơn.

## 15. Strict stubbing, reset và test isolation

### 15.1. Stubbing không được sử dụng

Ví dụ:

~~~java
when(customers.check(approvedId))
        .thenReturn(EligibilityDecision.APPROVED);

// Nhưng test gọi service với một customerId khác.
service.place(orderId, otherCustomerId);
~~~

Tùy strictness của Mockito/Test runner, test có thể báo `PotentialStubbingProblem` hoặc `UnnecessaryStubbingException`; hoặc service nhận `null` vì input không khớp. Đừng sửa bằng cách thay mọi stub thành `lenient()`:

~~~java
lenient().when(customers.check(any(UUID.class)))
        .thenReturn(EligibilityDecision.APPROVED);
~~~

Cách này che bug truyền tham số sai và stubbing thừa. Chỉ dùng lenient khi có lý do **rõ ràng**, ví dụ setup dùng chung một số test không thực sự gọi collaborator; tốt hơn thường là **đưa stub vào đúng test cần nó**.

### 15.2. Mock reset không đồng nghĩa dọn database

`@MockitoBean` trong Spring Framework hỗ trợ reset mock giữa các test method; mặc định reset theo cơ chế `AFTER`. Nhưng:

- JPA records có thể vẫn tồn tại nếu test không rollback/dọn fixture.
- Event Publication Registry có thể còn publication từ test khác.
- Callback async có thể tiếp tục chạy sau khi mock reset.
- Test dùng chung Spring context có thể làm nhiều bài test tranh chấp cùng mock nếu chạy song song thiếu kiểm soát.

Dùng `UUID.randomUUID()` riêng, fixture database cô lập, chờ async theo điều kiện khi cần, và tránh phụ thuộc thứ tự thực thi test. Không gọi `Mockito.reset(mock)` giữa một test nếu bạn vẫn cần stubbing/interaction đã có.

### 15.3. Nhiều bean cùng interface

Nếu context có hai bean `CustomerEligibility`, mock theo type có thể mơ hồ. Dùng qualifier hoặc tên:

~~~java
@MockitoBean(name = "retailCustomerEligibility")
CustomerEligibility customers;
~~~

Cũng phải bảo đảm constructor injection của `OrderService` dùng bean name/qualifier tương ứng. Khi nhiều test cùng override một bean, đặt tên field nhất quán giúp Spring tái sử dụng test context cache thay vì tạo thêm context.

## 16. Transaction: stub failure không tự chứng minh rollback

Một test:

~~~java
when(customers.check(customerId))
        .thenThrow(new CustomerEligibilityUnavailableException(
                "Unavailable"));

assertThatThrownBy(() -> service.place(orderId, customerId))
        .isInstanceOf(CustomerEligibilityUnavailableException.class);
~~~

chỉ chứng minh exception đã đi ra ngoài. Muốn khẳng định dữ liệu **không commit**, phải có assertion với repository/datasource thật.

### 16.1. Trước khi ghi dữ liệu và sau khi ghi dữ liệu khác nhau

Trong service ví dụ, collaborator được gọi **trước** `orders.save` và `publishEvent`. Khi stub ném lỗi, service dừng trước side effect; kết quả DB/event rỗng là đương nhiên theo đường code.

Một service khác có thể:

~~~java
@Transactional
public void place(UUID orderId, UUID customerId) {
    orders.save(new OrderEntity(orderId, customerId));
    publisher.publishEvent(new OrderPlaced(
            UUID.randomUUID(), orderId, customerId, Instant.now()));
    customers.check(customerId); // Exception sau save + publish.
}
~~~

Khi mock `customers.check` ném unchecked exception, transaction nguồn có thể rollback nên row không còn bền vững. Tuy nhiên **lời gọi `publishEvent` đã xảy ra**; một bộ quan sát `PublishedEvents` có thể vẫn đếm event đó dù callback `AFTER_COMMIT` không chạy.

**Không áp dụng `assertThat(PublishedEvents).isEmpty()` cho nhánh lỗi muộn này.** Cần phân biệt ba kiểm tra:

1. Publisher có được gọi không?
2. Transaction nguồn có commit không?
3. Listener `AFTER_COMMIT` hoặc publication registry có hoàn tất/được lưu bền vững không?

### 16.2. @Transactional ở cấp test có thể làm sai thời điểm commit

Với `@ApplicationModuleTest`, nếu bạn thêm `@Transactional` lên test class, Spring Test có thể mở transaction bao ngoài và rollback khi kết thúc. Lúc đó các lần gọi service thường tham gia transaction test, callback after-commit không chạy giữa các assertion.

Khi test cần commit/rollback rõ ràng:

- Ưu tiên test **không có transaction bao ngoài**, gọi service qua Spring proxy.
- Hoặc điều khiển bằng `TransactionTemplate` hay `TestTransaction`.
- Với `@ApplicationModuleListener` async, dùng `Scenario` hoặc Awaitility và kiểm tra side effect thật.

Stubbing error đúng chưa đủ nếu test transaction setup vô tình không phản ánh production.

## 17. Khi lỗi xảy ra trong listener hoặc I/O adapter

Nếu `orders` chỉ phát `OrderPlaced`, module `notifications` có thể nhận qua:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    notificationGateway.sendOrderConfirmation(event.orderId());
}
~~~

Trong module test nguồn `orders`, **không cần mock listener của `notifications`** vì listener ngoài module thường không được nạp ở `STANDALONE`. Dùng `PublishedEvents` để kiểm chứng producer.

Nếu muốn test module nhận:

1. Đặt `@ApplicationModuleTest` tại `notifications` hoặc integration test nạp listener.
2. Giữ listener thật; mock/fake **`NotificationGateway` ở I/O boundary**.
3. Với success, stub void method (thường không cần `doNothing`) rồi kiểm tra completion/side effect của module.
4. Với failure, `doThrow(...)` để callback ném lỗi và publication chưa completed theo registry.
5. Phát event trong transaction **commit thật**; chờ callback async qua `Scenario`/Awaitility.
6. Với retry, chứng minh side effect không bị nhân đôi bằng idempotency key/marker bền vững.

**Một `verify(notificationGateway).sendOrderConfirmation(id)` không chứng minh email provider thật nhận request**, cũng không chứng minh Event Publication Registry đã đánh dấu completed. Cần integration/contract tests cho adapter và storage đúng mục tiêu.

## 18. Tách module test và contract/integration test

Mock là một cam kết giả định: “nếu `CustomerEligibility` trả `APPROVED` hoặc ném exception này, `OrderService` sẽ phản ứng đúng”. Nó **không chứng minh provider thật tuân thủ giả định**.

Ví dụ provider thật có thể:

- Trả `DENIED` cho customer bị khóa.
- Ném `CustomerEligibilityUnavailableException` khi database không sẵn sàng.
- Trả `null` do bug serialization hoặc mapping.
- Chậm, timeout hoặc trả kết quả không nhất quán khi update đồng thời.

Để tránh test của consumer tạo một contract tưởng tượng:

| Test | Bean chạy thật | Ý nghĩa |
| --- | --- | --- |
| `orders` module test với `@MockitoBean CustomerEligibility` | `OrderService`, JPA, publisher. | Phản ứng với approved/denied/error đã stub. |
| `customers` module test | `CustomerEligibilityService`, repository/provider của `customers`. | Implementation thật tuân thủ public contract. |
| `orders` + `customers` `DIRECT_DEPENDENCIES` | Public API và implementation thật của hai module. | Wiring và tương tác thực không bị mock che giấu. |
| Architecture test | Mô hình module dependency. | Không có import trái luật hoặc cycle. |
| External adapter integration | Client HTTP/DB/broker thật trong test harness. | Protocol, serialization, timeout/retry đúng. |

### 18.1. Wiring test không mock public API đang được kiểm chứng

~~~java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealCustomersTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;
    @Autowired CustomerFixture customersFixture;

    @Test
    void realActiveCustomerCanPlaceOrder() {
        UUID customerId = customersFixture.createActiveCustomer();
        UUID orderId = UUID.randomUUID();

        service.place(orderId, customerId);

        assertThat(orders.existsById(orderId)).isTrue();
    }
}
~~~

`CustomerFixture` ở đây là một **test fixture cần triển khai** và expose đúng trong test context, không phải class sẵn có của Spring Modulith. Khi test wiring, không khai báo `@MockitoBean CustomerEligibility`, vì điều đó lại thay bean thật mà bạn muốn kiểm chứng.

## 19. Kiểm chứng kiến trúc bằng ApplicationModules

Stubbing không cho phép truy cập implementation nội bộ của module khác. Mỗi module chỉ nên gọi API được công bố hợp lệ; trong ví dụ là `customers :: api`.

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

`verify()` kiểm tra quy tắc module dependencies, API không được công bố và chu trình module theo Spring Modulith. Nó không thực thi `CustomerEligibility.check`, không biết Mockito stub gì và không chứng minh transaction source đã commit.

**Cả test kiến trúc lẫn test hành vi đều cần trong CI**: một test mock success/error có thể pass dù module `orders` vô tình import `customers.internal.CustomerRepository`; `ApplicationModules.verify()` bảo vệ ranh giới ấy.

## 20. Ma trận quality gate CI

| Quality gate | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| **Architecture** | `ApplicationModules.of(...).verify()`. | Không phụ thuộc sai named interface/cycle. |
| **Unit logic** | Validation và nhánh approved/denied ở class đơn lẻ. | Logic đúng, không cần Spring context. |
| **Module happy path** | `@MockitoBean` trả `APPROVED`. | DB lưu đúng, đúng một `OrderPlaced`. |
| **Module business rejection** | `thenReturn(DENIED)`. | `OrderRejectedException`, không lưu/phát. |
| **Module technical failure** | `thenThrow(UnavailableException)`. | Exception kỹ thuật đúng, không lưu/phát nếu lỗi trước side effect. |
| **Contract violation** | `thenReturn(null)` hoặc input không khớp. | Không chấp nhận thành công giả; fail closed đúng. |
| **Explicit retry** | `thenThrow(...).thenReturn(APPROVED)`. | Lần hai thành công, không tạo event/order trùng. |
| **Provider module test** | `customers` thật trả quyết định từ DB. | Provider khớp với contract đã stub. |
| **Wiring integration** | Nạp `orders` + `customers` thật. | Bean resolution/transaction/semantics đúng. |
| **Listener/registry** | Listener sau commit lỗi rồi recovery. | Publication theo target đúng, idempotency. |
| **Adapter contract** | Database/HTTP/broker client xử lý lỗi thật. | Timeout, status mapping, serialization đúng. |

Những test nhanh (unit, architecture, module) có thể chạy trên mỗi pull request. Test database/adapter/broker nên chạy ở integration stage phù hợp và là gate bắt buộc đối với thay đổi contract hoặc transaction.

**CI không nên chỉ đếm số test có `thenReturn` và `thenThrow`.** Chất lượng đến từ sự phân biệt outcome, assertion dữ liệu cuối cùng, đường lỗi, hợp đồng provider và boundary dependency.

## 21. Các anti-pattern thường gặp

### 21.1. Dùng thenThrow cho mọi trường hợp không thành công

~~~java
when(customers.check(customerId))
        .thenThrow(new IllegalStateException("Rejected"));
~~~

Nếu public contract trả `DENIED`, đây là mock mô phỏng **sai nhánh nghiệp vụ**. Sửa thành `thenReturn(DENIED)` và assert `OrderRejectedException`.

### 21.2. Dùng thenReturn(false) cho lỗi hạ tầng

Với interface trả boolean, `false` thường là kết quả không đủ điều kiện; không dùng nó thay cho timeout nếu business không cho phép. Thiết kế typed result hoặc exception làm rõ **không biết được** khác với **đã xác định là không hợp lệ**.

### 21.3. Mock chính service đang kiểm thử

~~~java
@MockitoBean OrderService service;
~~~

Khi đó `service.place(...)` không chạy logic thật, test có thể chỉ tự xác nhận stubbing của `OrderService` mock.

### 21.4. Mock repository khi test tuyên bố kiểm tra database

~~~java
@MockitoBean OrderRepository repository;
~~~

`verify(repository).save(...)` không chứng minh JPA mapping, schema, transaction hay row đã commit. Dùng repo/datasource thật trong `@ApplicationModuleTest` nếu đó là mục tiêu.

### 21.5. Mock publisher rồi mong PublishedEvents thấy event

~~~java
@MockitoBean ApplicationEventPublisher publisher;
~~~

Điều này thay infrastructure event thật, khiến `PublishedEvents` không còn quan sát đúng luồng publish cần kiểm chứng.

### 21.6. Stub sai tham số rồi đổi thành any() cho test xanh

Bug có thể nằm ở production truyền nhầm ID. Kiểm tra fixture và interaction trước khi nới matcher.

### 21.7. Dùng Mockito spy như mock không có bean thật

`@MockitoSpyBean` cần một bean tồn tại; trong `STANDALONE`, collaborator module ngoài thường bị loại khỏi context.

### 21.8. Gọi khi(spy.realMethod()) và vô tình chạy I/O

Sử dụng `doReturn`/`doThrow` khi cần stub spy mà không muốn method thật chạy tại thời điểm cấu hình, hoặc đổi về mock của public port nếu mục tiêu chỉ là cô lập external dependency.

### 21.9. Assert exception nhưng không kiểm tra state/event

Một service có thể đã lưu dữ liệu/phát event trước khi lỗi. Chỉ `assertThatThrownBy` chưa chứng minh hành vi rollback, không trùng hoặc không side effect.

### 21.10. Coi chuỗi thenThrow-thenReturn là chứng minh retry tự động

Chuỗi stub chỉ thay kết quả giữa các invocation. Retry tự động phải được triển khai và kiểm chứng riêng; test gọi service hai lần là **manual retry**, không phải test Spring Retry.

## 22. Bài tập thực hành

Module `checkout` trong một Spring Modulith app gọi API công khai `payments.api.PaymentAuthorization.authorize(orderId, amount)` trước khi xác nhận giao dịch. API có các kết quả:

- `AuthorizationResult.APPROVED`: chấp nhận thanh toán.
- `AuthorizationResult.DECLINED`: nhà cung cấp đã phản hồi từ chối theo nghiệp vụ.
- `PaymentProviderUnavailableException`: không thể liên lạc provider, chưa biết thanh toán thành công hay chưa.

`CheckoutService` sẽ lưu `CheckoutEntity` và phát `CheckoutCompleted` **chỉ nếu được phê duyệt**.

### Câu hỏi

1. Với khách được phê duyệt, bạn stub gì và assert gì?
2. Với kết quả `DECLINED`, vì sao `thenReturn(DECLINED)` đúng hơn `thenThrow(...)` nếu API trả enum?
3. Nếu provider timeout, tại sao không chuyển `PaymentProviderUnavailableException` thành `DECLINED`?
4. Nếu `authorize` là method `void`, cú pháp Mockito nào dùng để mô phỏng lỗi?
5. Nếu muốn lần đầu timeout rồi lần hai trả `APPROVED`, nên stub thế nào? Kết quả ấy có chứng minh retry tự động chưa?
6. Vì sao không mock `CheckoutRepository` và `ApplicationEventPublisher` trong bài `@ApplicationModuleTest` kiểm tra DB/event?
7. Nếu module `checkout` import `payments.internal.PaymentRepository`, mock repository có làm dependency hợp lệ không?
8. Nếu `PaymentAuthorization` thật có thể trả `DECLINED` nhưng tất cả test consumer đều stub `APPROVED`, cần bổ sung test nào?

### Đáp án gợi ý

1. `when(paymentAuthorization.authorize(...)).thenReturn(APPROVED)`; assert checkout được lưu đúng và đúng một `CheckoutCompleted`, verify đúng order/amount.
2. `DECLINED` là kết quả **đã xử lý thành công nhưng bị từ chối nghiệp vụ**, không phải exception hạ tầng.
3. Timeout có thể là trạng thái **chưa xác định kết quả**, cần reconciliation/idempotency; gán `DECLINED` dễ làm sai nghiệp vụ và che lỗi.
4. `doThrow(exception).when(mock).voidMethod(...)`.
5. `when(...).thenThrow(...).thenReturn(APPROVED)`; cần code/test có invocation thứ hai thực sự, và phải kiểm soát khả năng provider đã charge ở lần trước.
6. Vì cần JPA và event publisher thật để kiểm chứng persistence, transaction và publication; mock chỉ chứng minh lời gọi method.
7. Không. Phải gọi public API/named interface của `payments` và chạy `ApplicationModules.verify()`.
8. Provider module/contract tests cho `payments` và integration test `checkout` + `payments` thật, bao phủ cả approved/declined/unavailable.

## 23. Checklist trước khi viết stub

- [ ] Đã phân biệt **success**, **business rejection** và **technical failure** trong contract.
- [ ] Biết module nào là system under test và collaborator thuộc public API module nào.
- [ ] Không mock implementation nội bộ hoặc repository của module khác để che vi phạm boundary.
- [ ] Dùng `@MockitoBean` cho bean trong Spring context; dùng `@Mock` cho unit test thuần theo phiên bản hỗ trợ.
- [ ] Không dùng `@MockitoSpyBean` nếu không có một bean thật để wrap.
- [ ] `thenReturn` dùng cho giá trị thành công và từ chối nghiệp vụ theo contract.
- [ ] `thenThrow` dùng cho exception hợp lệ mà collaborator có thể ném.
- [ ] `doThrow` dùng cho `void` method; tránh `when(voidCall)`.
- [ ] Checked exception trong stub phải tương thích chữ ký Java của method.
- [ ] Stub tham số đủ cụ thể để phát hiện service truyền nhầm ID.
- [ ] Có test happy path, rejection, technical exception và trường hợp dữ liệu contract không hợp lệ.
- [ ] Nếu dùng sequential stubbing, hiểu rõ số invocation và không nhầm với retry tự động.
- [ ] Assert kết quả database, event và exception, không dừng ở `verify(mock)`.
- [ ] Không mock repository/publisher nếu mục tiêu là JPA hoặc `PublishedEvents` thật.
- [ ] Nếu lỗi xảy ra sau lời gọi `publishEvent`, phân biệt việc phát với callback `AFTER_COMMIT`.
- [ ] Có test transaction commit/rollback rõ, không vô tình bao toàn bộ test bằng transaction rollback.
- [ ] Với listener async, chờ theo điều kiện và kiểm tra side effect/Registry riêng.
- [ ] Có provider module test và ít nhất một wiring/integration test không override public API đã mock.
- [ ] Chạy `ApplicationModules.verify()` để bảo vệ `allowedDependencies` và public named interfaces.
- [ ] Test isolation, reset mock, database fixture và CI quality gates được quản lý độc lập.

**Kết luận:** Stubbing giúp mô phỏng **đầu ra của một collaborator ở ranh giới kiểm thử**, nhưng không phải mục tiêu của bài test. Với Spring Modulith, hãy dùng `@MockitoBean` để điều khiển kết quả hợp lệ, từ chối và lỗi kỹ thuật từ public API của module khác; giữ service, repository và event publisher thật khi kiểm tra một module. Kết hợp assertion về **state, exception và publication**, rồi bổ sung contract/integration tests cùng `ApplicationModules.verify()`, mới đủ bảo vệ cả hành vi nghiệp vụ lẫn ranh giới kiến trúc.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes, mock efferent dependencies và `Scenario`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, publication registry và retry.
- [Spring Framework — MockitoBean and MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): replace-or-create, qualifiers, AOP proxy và stubbing spy.
- [Mockito API — Mockito](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): `when`, `thenReturn`, `thenThrow`, `doThrow`, `doAnswer`, consecutive stubbing và verification.

> Ghi chú: Mã minh họa giả định Spring Framework 6.2+, Spring Modulith, Spring Data JPA và môi trường test database tương thích. Đây là bài học được biên soạn theo STEP_4; chưa chạy Gradle hoặc vòng Content QA chuyên môn. Khi áp dụng, cần kiểm tra lại dependency, schema, transaction manager và policy retry thực tế của dự án.
