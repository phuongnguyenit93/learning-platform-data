# Khi mock collaborator ngoài module

## 1. Vấn đề: module đang kiểm thử phụ thuộc vào một bean ở module khác

Trong Spring Modulith, mỗi application module có một phạm vi trách nhiệm tương đối độc lập. Tuy nhiên, vẫn có những quan hệ đồng bộ hợp lệ: module `orders` cần hỏi module `customers` rằng một khách hàng có đủ điều kiện đặt hàng hay không; module `inventory` cần tra cứu thông tin sản phẩm từ API công khai của `catalog`.

Khi kiểm thử riêng `orders` bằng `@ApplicationModuleTest`, Spring Modulith **mặc định chỉ bootstrap module `orders`**. Bean thực thi giao diện của module `customers` có thể không được nạp. Nếu `OrderService` có constructor nhận một `CustomerEligibility` bên ngoài, application context của bài test có thể không khởi động vì thiếu bean.

Đây là thời điểm cân nhắc **mock collaborator ngoài module**: thay dependency không thuộc module đang kiểm thử bằng một đối tượng Mockito có hành vi do test điều khiển, để giữ logic của module được kiểm thử là **code thật**.

**Mock đúng ranh giới không có nghĩa mock cả ứng dụng.** Khi test `orders`, ta muốn:

- `OrderService`, domain logic và repository thuộc `orders` thực thi thật nếu mục tiêu là module integration test.
- `CustomerEligibility` — API của module `customers` — được mô phỏng ở phía bên kia ranh giới.
- Đầu ra của `orders` (trạng thái database, exception, event `OrderPlaced`) được xác minh bằng assertion thực tế.
- Các luật phụ thuộc giữa module vẫn được kiểm chứng riêng bằng `ApplicationModules.verify()`.

Bài thuộc chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Học phần hướng đến kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, thực hành `@ApplicationModuleTest`, kiểm thử event/database/tích hợp và thiết lập quality gate CI để phát hiện phụ thuộc sai, lỗi tích hợp và hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện **collaborator ngoài module** và phân biệt nó với dependency nội bộ, cổng hạ tầng hoặc listener sự kiện.
2. Giải thích vì sao `STANDALONE` có thể báo thiếu bean và khi nào `@MockitoBean` là lựa chọn phù hợp.
3. Chọn đúng giữa `STANDALONE`, `DIRECT_DEPENDENCIES` và `ALL_DEPENDENCIES`.
4. Viết `@ApplicationModuleTest` mock duy nhất dependency ngoài module, giữ service/repository/event publisher thật.
5. Phân biệt `@MockitoBean`, `@Mock`, `@MockitoSpyBean` và các annotation `@MockBean`/`@SpyBean` cũ.
6. Tránh mock che mất lỗi kiến trúc, lỗi transaction, event publication và hợp đồng giữa các module.
7. Kết hợp module test, architecture test và integration test trong quality gate CI.

## 2. Collaborator ngoài module là gì?

Một **collaborator** là đối tượng mà đối tượng đang kiểm thử gọi tới để hoàn thành hành vi. “Ngoài module” nghĩa là implementation hoặc bean được sở hữu bởi một application module khác, không thuộc phạm vi bootstrap của module test.

Giả sử cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── customers
│   ├── api
│   │   ├── CustomerEligibility.java
│   │   └── package-info.java
│   └── internal
│       └── CustomerEligibilityService.java
└── orders
    ├── OrderService.java
    ├── package-info.java
    ├── events
    │   └── OrderPlaced.java
    └── internal
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

Quan hệ phụ thuộc mong muốn:

~~~mermaid
flowchart LR
    OT["orders.OrderService"] -->|"gọi public API"| CA["customers.api.CustomerEligibility"]
    CI["customers.internal.CustomerEligibilityService"] -->|"implements"| CA
    OT --> OR["orders.internal.OrderRepository"]
    OT --> EP["Spring ApplicationEventPublisher"]
    T["orders module test"] --> OT
    T -.->|"@MockitoBean thay bean ngoài scope"| CA
~~~

`orders` biết **interface công khai** `CustomerEligibility`, không biết `CustomerEligibilityService` nội bộ của `customers`. Trong bài test riêng `orders`, interface ấy vẫn có trong classpath để biên dịch, nhưng implementation thực bị loại khỏi application context.

| Dependency của `OrderService` | Thuộc phạm vi nào? | Test module `orders` nên làm gì? |
| --- | --- | --- |
| `OrderRepository` | Nội bộ `orders`. | **Giữ thật** nếu muốn kiểm thử persistence/transaction. |
| `OrderEntity` và domain logic | Nội bộ `orders`. | **Giữ thật** để assertion phản ánh nghiệp vụ. |
| `CustomerEligibility` | API của `customers`. | **Mock** khi cần cô lập ranh giới đồng bộ. |
| `ApplicationEventPublisher` | Hạ tầng event Spring. | Thường **giữ thật**, dùng `PublishedEvents` để quan sát. |
| Kafka/Rabbit/HTTP client do một outbound adapter sở hữu | Hạ tầng hoặc module tích hợp. | Mock port khi kiểm thử logic; dùng fake server/broker thật ở test tích hợp. |

Một class nằm ở package khác **chưa đủ** để kết luận nó là module khác; Spring Modulith xác định application module theo cấu hình phát hiện module. Tốt nhất kiểm chứng mô hình thực tế với `ApplicationModules` và đặt test trong package của module định kiểm thử.

## 3. @ApplicationModuleTest bootstrap những module nào?

`@ApplicationModuleTest` là Spring Modulith module integration test. Nó dùng Spring Boot test context nhưng hạn chế component/entity scanning vào phạm vi module đã xác định; JUnit test thường nằm trong package root của module hoặc package con.

Các chế độ bootstrap:

| Bootstrap mode | Phạm vi | Khi nào dùng? |
| --- | --- | --- |
| `STANDALONE` (**mặc định**) | Chỉ module chứa test. | Kiểm thử một module độc lập, mock collaborator ngoài module. |
| `DIRECT_DEPENDENCIES` | Module hiện tại và các module mà nó phụ thuộc **trực tiếp**. | Cần kiểm thử kết nối thật với các module trực tiếp. |
| `ALL_DEPENDENCIES` | Module hiện tại và toàn bộ cây phụ thuộc của nó. | Kiểm thử sâu hơn các module upstream, chi phí bootstrap lớn hơn. |

~~~java
@ApplicationModuleTest
class OrderModuleTests {
    // Tương đương lựa chọn mode STANDALONE mặc định.
}

@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithCustomerModuleTests {
    // Nạp orders và các module phụ thuộc trực tiếp.
}
~~~

Đoạn thứ hai cần import `org.springframework.modulith.test.ApplicationModuleTest`. **Không** thay mọi test bằng `ALL_DEPENDENCIES` chỉ để hết lỗi thiếu bean: test chậm hơn, phụ thuộc thêm database, client và side effect ngoài module, đồng thời làm lỗi boundary khó khoanh vùng.

### 3.1. Vì sao context thiếu bean?

Khi `OrderService` có constructor:

~~~java
OrderService(OrderRepository orders,
             CustomerEligibility customers,
             ApplicationEventPublisher events) {
    // ...
}
~~~

test `STANDALONE` khởi tạo `OrderService` thật nhưng không có `CustomerEligibilityService` của module `customers`, nên Spring không tìm thấy candidate cho dependency `CustomerEligibility`.

Đây **không mặc nhiên là lỗi thiết kế**. Đó có thể là kết quả bình thường của việc chủ động chỉ tải một module. Nếu interface `CustomerEligibility` là public API hợp lệ, hãy tạo một mock ở context test. Nhưng nếu `OrderService` trực tiếp inject `customers.internal.CustomerRepository`, mock repository đó **không sửa được vi phạm phụ thuộc**.

### 3.2. Chiến lược lựa chọn

~~~mermaid
flowchart TD
    A["Module test không có bean collaborator"] --> B{"Có phụ thuộc module hợp lệ?"}
    B -->|"Không"| C["Sửa boundary: public API hoặc event"]
    B -->|"Có"| D{"Mục tiêu test có cần logic thực module ngoài?"}
    D -->|"Không"| E["STANDALONE + @MockitoBean public collaborator"]
    D -->|"Có"| F["DIRECT_DEPENDENCIES hoặc integration test"]
    E --> G["Assert nghiệp vụ thật + verify tương tác"]
    F --> H["Assert hợp đồng/tác động thật của cả hai module"]
    G --> I["ApplicationModules.verify + test bổ sung"]
    H --> I
~~~

Không có câu trả lời “luôn mock” hoặc “không bao giờ mock”. Lựa chọn đúng phụ thuộc **mục tiêu test** và **hợp đồng giữa các module**.

## 4. Dựng ví dụ có boundary hợp lệ

### 4.1. API công khai của module customers

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

Implementation thật ở `customers/internal/CustomerEligibilityService.java` có thể dùng repository của module `customers`, ví dụ:

~~~java
package com.example.shop.customers.internal;

import com.example.shop.customers.api.CustomerEligibility;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
class CustomerEligibilityService implements CustomerEligibility {

    private final CustomerRepository customers;

    CustomerEligibilityService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Override
    public boolean canPlaceOrder(UUID customerId) {
        return customers.isActive(customerId);
    }
}
~~~

`CustomerRepository` là repository nội bộ cần triển khai. Điều quan trọng là module `orders` **chỉ import `CustomerEligibility`**, không import implementation hoặc repository này.

### 4.2. Cho phép phụ thuộc đúng named interface

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "customers :: api")
package com.example.shop.orders;
~~~

Quy tắc này cho phép `orders` phụ thuộc vào named interface `api` của `customers`. Nó **không** cho phép tham chiếu tùy tiện vào các package `customers.internal`.

Nếu một module có nhiều dependency hợp lệ, cấu hình `allowedDependencies` phải liệt kê đúng các dependency; không thay `"customers :: api"` bằng `"customers"` để cho qua mọi kiểu public nếu hợp đồng chỉ cần một named interface.

### 4.3. Entity, repository và event của module orders

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

    protected OrderEntity() {} // Cho JPA.

    public OrderEntity(UUID id, UUID customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
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
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {}
~~~

Đây là mô hình tối giản. Ứng dụng thật cần thêm validation, unique constraint, trạng thái order, idempotency và quản lý schema phù hợp. Không đưa `OrderEntity` hoặc repository nội bộ vào payload công khai chỉ để listener dễ lấy dữ liệu.

### 4.4. Code thật của module đang kiểm thử

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

import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final CustomerEligibility customers;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders,
                        CustomerEligibility customers,
                        ApplicationEventPublisher events) {
        this.orders = orders;
        this.customers = customers;
        this.events = events;
    }

    @Transactional
    public void place(UUID orderId, UUID customerId) {
        if (!customers.canPlaceOrder(customerId)) {
            throw new IllegalStateException("Customer not eligible");
        }

        orders.save(new OrderEntity(orderId, customerId));
        events.publishEvent(
                new OrderPlaced(orderId, customerId, Instant.now()));
    }
}
~~~

Đây là một **synchronous collaborator**: `orders` cần câu trả lời `boolean` của `customers` trước khi thực hiện use case. Nó là một trường hợp hợp lý để mock trong module test khi mục tiêu là hành vi của `orders`.

Nếu nghiệp vụ thay đổi để `orders` không còn cần hỏi đồng bộ, cân nhắc event-driven integration hoặc một local projection. Mock chỉ là kỹ thuật kiểm thử, **không phải giải pháp cho coupling nghiệp vụ không cần thiết**.

## 5. Mock collaborator ngoài module bằng @MockitoBean

Trong hệ Spring Boot sử dụng Spring Framework có `@MockitoBean` (Spring Framework 6.2+, như Spring Boot 3.4+), khai báo:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
CustomerEligibility customers;
~~~

Spring Test đưa mock vào `ApplicationContext` của test. Với bootstrap `STANDALONE`, bean thật từ `customers` không xuất hiện; chiến lược mặc định `REPLACE_OR_CREATE` của `@MockitoBean` sẽ **tạo một bean mock mới** cho interface đó. Sau đó Spring inject mock vào `OrderService` thật.

### 5.1. Module test đầy đủ: khách hàng hợp lệ

Đặt lớp test trong `com.example.shop.orders`, dưới application root `com.example.shop` có `ShopApplication`:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
class OrderPlacementModuleTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    // Bên ngoài module orders: không tải implementation customers thật.
    @MockitoBean CustomerEligibility customers;

    @Test
    void acceptedCustomerCreatesOrderAndPublishesEvent(
            PublishedEvents publishedEvents) {

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(customers.canPlaceOrder(customerId)).thenReturn(true);

        orders.place(orderId, customerId);

        // Điều khiển collaborator và xác nhận lời gọi qua boundary.
        verify(customers).canPlaceOrder(customerId);

        // Logic nghiệp vụ + persistence của orders vẫn chạy THẬT.
        assertThat(repository.existsById(orderId)).isTrue();

        // Event publisher không bị mock nên kiểm tra được event thật.
        assertThat(publishedEvents.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event ->
                        assertThat(event.customerId())
                                .isEqualTo(customerId));
    }
}
~~~

**Điểm quan trọng:** `@MockitoBean` chỉ áp dụng cho `CustomerEligibility`. Nó không thay `OrderService`, `OrderRepository` hoặc `ApplicationEventPublisher`.

Test dùng JPA repository thật; vì vậy cần test datasource, transaction manager, schema và các Spring Boot/Spring Modulith test dependencies phù hợp. `@ApplicationModuleTest` giới hạn module scanning, **không tự loại bỏ nhu cầu cấu hình database**.

### 5.2. Test đường từ chối và đường lỗi

Cùng lớp test có thể bổ sung:

~~~java
@Test
void rejectedCustomerDoesNotCreateOrderOrPublishEvent(
        PublishedEvents publishedEvents) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.canPlaceOrder(customerId)).thenReturn(false);

    assertThatThrownBy(() -> orders.place(orderId, customerId))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Customer not eligible");

    verify(customers).canPlaceOrder(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(publishedEvents.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}

@Test
void collaboratorFailureDoesNotSaveOrder(
        PublishedEvents publishedEvents) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();

    when(customers.canPlaceOrder(customerId))
            .thenThrow(new IllegalStateException(
                    "Customer service unavailable"));

    assertThatThrownBy(() -> orders.place(orderId, customerId))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Customer service unavailable");

    verify(customers).canPlaceOrder(customerId);
    assertThat(repository.existsById(orderId)).isFalse();
    assertThat(publishedEvents.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Các đoạn này thuộc **cùng lớp `OrderPlacementModuleTests`** và cần thêm:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Trong hai trường hợp, exception xảy ra **trước** lệnh `publishEvent` nên bộ quan sát không thấy `OrderPlaced`. Nếu exception xảy ra **sau** lời gọi publisher nhưng trước commit, `PublishedEvents` có thể vẫn thấy event; để kiểm tra side effect sau commit phải dùng transactional listener và kiểm thử transaction riêng.

### 5.3. Vì sao dùng Mockito.verify lẫn assertion nghiệp vụ?

`verify(customers).canPlaceOrder(customerId)` chứng minh module đã **hỏi collaborator đúng khách hàng**, nhưng không chứng minh kết quả cuối cùng đúng. Trái lại, chỉ kiểm tra `repository.existsById(orderId)` chưa phát hiện một thay đổi khiến service bỏ qua chính sách eligibility nếu test vô tình chuẩn bị dữ liệu không chặt.

Kết hợp hai loại assertion:

| Loại | Khẳng định gì? |
| --- | --- |
| **Interaction assertion** | Service gọi API ngoài module với đúng tham số/số lần cần thiết. |
| **State assertion** | Dữ liệu của module đang kiểm thử thay đổi hoặc giữ nguyên đúng nghiệp vụ. |
| **Event assertion** | Module phát đúng sự kiện/payload qua Spring publisher thật. |

Không lạm dụng `verifyNoMoreInteractions(...)` cho mọi test: nó có thể khiến test vỡ khi thêm một lời gọi hợp lệ không liên quan đến hợp đồng. Dùng nó chỉ khi “không được có lời gọi bổ sung” là **quy tắc nghiệp vụ rõ ràng**.

## 6. MockBean cũ, MockitoBean mới và compatibility

Các tài liệu Spring Modulith hiện hành dùng `@MockitoBean`, nhưng dự án cũ có thể đang dùng annotation của Spring Boot:

~~~java
// Cú pháp trong các dự án Spring Boot cũ:
import org.springframework.boot.test.mock.mockito.MockBean;

@MockBean CustomerEligibility customers;
~~~

`@MockBean` và `@SpyBean` thuộc package `org.springframework.boot.test.mock.mockito` đã bị **deprecated từ Spring Boot 3.4** để chuyển sang `@MockitoBean` và `@MockitoSpyBean` của Spring Framework; API cũ được đánh dấu cho việc loại bỏ trong phiên bản lớn kế tiếp.

| Bài toán | Annotation/đối tượng khuyến nghị | Nơi sử dụng |
| --- | --- | --- |
| Mock một bean trong Spring context. | `@MockitoBean` | `@ApplicationModuleTest`, `@SpringBootTest`, slice test hỗ trợ. |
| Spy một bean thật trong Spring context. | `@MockitoSpyBean` | Context có **đúng một bean thật** để wrap. |
| Mock trong unit test **không khởi tạo Spring context**. | Mockito `@Mock` hoặc `mock(...)` | JUnit + `MockitoExtension`. |
| Spy một object thông thường ngoài Spring. | Mockito `@Spy` hoặc `spy(...)` | Unit test, chỉ dùng real logic khi có chủ đích. |
| Dự án trên Boot cũ chưa có Framework `@MockitoBean`. | `@MockBean`/ `@SpyBean` tương ứng phiên bản. | Chưa thể thay import mà không nâng dependency. |

Không thay annotation chỉ bằng cách đổi tên nếu chưa xác nhận **Spring Framework/Spring Boot version**. Ví dụ `@MockitoBean` nằm trong:

~~~java
org.springframework.test.context.bean.override.mockito.MockitoBean
~~~

chứ không phải package cũ của Spring Boot.

### 6.1. `@MockitoBean` không hoàn toàn giống `@Mock`

~~~java
@Mock
CustomerEligibility customers;
~~~

Chỉ tạo mock dưới sự quản lý của Mockito (ví dụ qua `MockitoExtension`). Nó **không tự đăng ký bean** vào Spring `ApplicationContext`. Nếu `OrderService` là bean thật do `@ApplicationModuleTest` tạo, constructor của service có thể vẫn thiếu bean `CustomerEligibility`.

Trong unit test không có Spring, `@Mock` hoàn toàn phù hợp; trong module integration test cần **bean override** như `@MockitoBean`.

## 7. Bẫy enforceOverride=true khi bean nằm ngoài module

`@MockitoBean` mặc định có chiến lược **replace-or-create**. Nếu target bean có mặt, nó được thay bằng mock; nếu không có, mock mới được tạo.

~~~java
@MockitoBean
CustomerEligibility customers;
~~~

Đây là lựa chọn hợp lý trong `STANDALONE`, vì bean của module `customers` thực sự không được bootstrap.

Ngược lại:

~~~java
@MockitoBean(enforceOverride = true)
CustomerEligibility customers;
~~~

đòi hỏi một bean tương ứng **đã tồn tại trong context** để thay thế. Trong `STANDALONE`, thường không có bean thật của `customers`, nên test có thể **không khởi động**. Thuộc tính này hữu ích khi bạn muốn bảo đảm mình đang thay một bean vốn được nạp, ví dụ trong `DIRECT_DEPENDENCIES` hoặc `@SpringBootTest` có bean thật; nó **không phải một cách làm mock “chặt hơn” có thể áp dụng tùy tiện** cho tất cả module tests.

### 7.1. Replace-or-create cũng có nguy cơ che cấu hình production

Nếu một interface không còn implementation production, `@MockitoBean` vẫn có thể tạo mock cho test chạy xanh. Vì vậy một module test mock dependency **không chứng minh** toàn ứng dụng có đủ bean thật khi triển khai.

Cần một **integration smoke test** với `DIRECT_DEPENDENCIES` hoặc `@SpringBootTest` không override API ấy, kiểm chứng Spring có thể wiring implementation thật. Đây là bổ sung cần thiết, không phải lý do từ bỏ mock ở test cô lập.

### 7.2. Nhiều bean cùng interface

Giả sử module `customers` có hai implementation `CustomerEligibility` cho hai kênh bán hàng. Khi context chứa cả hai bean, override chỉ theo kiểu có thể **mơ hồ**. Dùng `@Qualifier` hoặc tên bean:

~~~java
@MockitoBean(name = "onlineCustomerEligibility")
CustomerEligibility customers;
~~~

Trong trường hợp một bean bị loại bởi `STANDALONE`, đặt đúng tên chỉ giúp tạo mock có identity phù hợp; vẫn cần đảm bảo tên đó tương ứng với injection point ở `OrderService`. Nếu đã có hai bean production, nên xem hợp đồng bean name/qualifier là một phần cấu hình kiểm thử và có test wiring thật.

**Lưu ý hiệu năng:** tên field và qualifier của `@MockitoBean` có thể tham gia quyết định cache key của Spring test context. Dùng cách đặt tên nhất quán giữa các test tương tự để tránh tạo nhiều context không cần thiết.

## 8. Khi nào spy, và vì sao spy ngoài module thường không phù hợp với STANDALONE?

**Mock** là một đối tượng giả lập: lời gọi không có implementation thật trừ khi test stub rõ. **Spy** bao quanh một đối tượng thật và thường **gọi method thật** nếu chưa bị stub.

`@MockitoSpyBean` của Spring Framework yêu cầu **có đúng một bean thật** để wrap. Nó **không tạo bean mới** khi target vắng mặt.

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
CustomerEligibility customers;
~~~

Trong `@ApplicationModuleTest` mặc định `STANDALONE`, `CustomerEligibilityService` của `customers` bị loại khỏi bootstrap, nên spy này **không dùng để thay thế collaborator còn thiếu**. Muốn spy một bean thật của module ngoài, test phải bootstrap module ấy, ví dụ `DIRECT_DEPENDENCIES`, và đảm bảo chỉ có một bean tương ứng:

~~~java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithRealCustomersTests {

    @Autowired OrderService orders;

    // Chỉ hợp lệ khi module customers có một bean
    // CustomerEligibility thật được khởi tạo trong context.
    @MockitoSpyBean CustomerEligibility customers;

    @Test
    void usesRealCustomerPolicy() {
        // Chuẩn bị dữ liệu customers và orders thật...
        // Gọi service, kiểm tra hành vi và verify collaborator nếu cần.
    }
}
~~~

**Đây là đoạn minh họa**, cần có fixture `CustomerRepository`, datasource và import. Nếu mục tiêu chỉ là điều khiển kết quả eligibility để kiểm thử `orders`, `@MockitoBean` trong `STANDALONE` đơn giản và ổn định hơn.

### 8.1. Cẩn thận khi stub spy

Mockito:

~~~java
when(spy.someMethod()).thenReturn(value);
~~~

có thể **gọi method thật ngay lúc cấu hình stubbing**, gây database write, HTTP call hoặc exception ngoài ý muốn. Với spy, thường dùng:

~~~java
doReturn(value).when(spy).someMethod();
doThrow(new IllegalStateException("Simulated")).when(spy).someMethod();
~~~

Đây là cú pháp minh họa với một spy và method phù hợp, không phải code đầy đủ. Trong Spring, AOP proxy của `@Transactional`, `@Cacheable` hoặc `@Retryable` có thể ảnh hưởng stubbing. Với `@MockitoSpyBean`, để stub chính xác khi có proxy advice, tài liệu Spring khuyến nghị có thể unwrap spy bằng `AopTestUtils.getUltimateTargetObject(...)`.

**Spy vẫn chạy code thật**, nên nếu muốn loại side effect của module `customers`, không nên dùng spy thay mock chỉ để có `verify(...)`.

## 9. Unit test với @Mock khác module integration test

Khi mục tiêu chỉ là kiểm tra nhánh điều kiện trong `OrderService`, unit test không cần tạo Spring context:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.api.CustomerEligibility;
import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock OrderRepository repository;
    @Mock CustomerEligibility customers;
    @Mock ApplicationEventPublisher events;

    @InjectMocks OrderService orders;

    @Test
    void eligibleCustomerCausesSaveAndPublish() {
        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(customers.canPlaceOrder(customerId)).thenReturn(true);

        orders.place(orderId, customerId);

        verify(customers).canPlaceOrder(customerId);
        verify(repository).save(any());
        verify(events).publishEvent(any(OrderPlaced.class));
    }
}
~~~

Test này nhanh, nhưng:

- `@Transactional` **không được kích hoạt** vì không gọi qua Spring proxy.
- `OrderRepository` là mock, không chứng minh dữ liệu thật đã commit.
- `ApplicationEventPublisher` là mock, không thể dùng `PublishedEvents` theo ngữ nghĩa Spring Modulith.
- Không có module scan, không kiểm chứng cấu hình dependency hoặc listener.

Vì vậy unit test dùng `@Mock` và module test dùng `@MockitoBean` **bổ sung cho nhau**. Khi test cần transaction/event/database thật, chọn module integration test với bean nội bộ thật, chỉ mock collaborator ngoài module.

## 10. Đừng mock ApplicationEventPublisher trong bài test sự kiện

Vì event làm giảm coupling giữa các module, một số use case chỉ cần phát domain event:

~~~java
@Transactional
public void place(UUID id) {
    repository.save(new OrderEntity(id));
    events.publishEvent(new OrderPlaced(id));
}
~~~

Nếu test dùng:

~~~java
@MockitoBean
ApplicationEventPublisher events;
~~~

thì lời gọi `publishEvent` đi vào Mockito mock thay vì bộ phân phối thật của Spring. Test có thể `verify(events).publishEvent(...)` nhưng **không còn kiểm chứng cơ chế event thật** và thường không thể dùng `PublishedEvents` đúng mục đích.

Trong `@ApplicationModuleTest`, ưu tiên:

~~~java
@Test
void publishesExpectedEvent(PublishedEvents events) {
    service.performBusinessAction();

    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, expectedId))
            .hasSize(1);
}
~~~

Đây là snippet đặt trong test với fixture/bean tương ứng. Nếu dependency cần thiết là một **module nhận event**, `orders` thường **không inject bean listener bên ngoài**: nó chỉ phát `OrderPlaced`. Do đó **không cần mock listener của module nhận** để kiểm thử module phát. Test luồng listener thật nằm ở `@ApplicationModuleTest` của module nhận hoặc integration test có hai module/registry.

### 10.1. Khi module trực tiếp gọi service khác thay vì publish event

Một synchronous port như `CustomerEligibility` có thể cần kết quả ngay để quyết định nghiệp vụ. Nếu producer chỉ cần **thông báo** việc đã xảy ra và không cần phản hồi, tham chiếu trực tiếp tới `EmailNotificationService` ở module khác có thể là coupling không cần thiết.

Khi số lượng `@MockitoBean` ngoài module ngày càng tăng, hãy xem lại:

- Các module có gọi trực tiếp service của nhau chỉ để làm side effect không?
- Có thể thay bằng domain event và `@ApplicationModuleListener` không?
- Một module đang gánh nhiều trách nhiệm và cần chia lại boundary không?
- API công khai của module khác có quá rộng không?

Spring Modulith cũng khuyến nghị xem xét việc phát domain event khi một module phụ thuộc quá nhiều bean thuộc module khác.

## 11. Khi nào không mock: cần kiểm chứng hợp đồng thật giữa hai module

Mock chỉ trả lời “`orders` xử lý thế nào **nếu** `CustomerEligibility` trả lời đúng dữ liệu đã stub?”. Nó **không xác minh** service thật của `customers` có thực sự trả kết quả đó, tương thích schema hoặc được Spring wiring đúng.

Hãy dùng `DIRECT_DEPENDENCIES` hoặc một integration test riêng khi mục tiêu là:

1. Xác nhận bean thật của `customers` được nạp và inject thành công.
2. Kiểm tra query và luật eligibility trên dữ liệu thật.
3. Kiểm tra transaction/isolation giữa hai module có chia sẻ database/transaction hay không.
4. Phát hiện thay đổi semantics của public API `CustomerEligibility`.
5. Chạy các callback/event listener thực sự của module nhận.

Ví dụ skeleton:

~~~java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersAndCustomersIntegrationTests {

    @Autowired OrderService orders;
    @Autowired CustomerRepositoryFixture customersFixture;
    @Autowired OrderRepository ordersRepository;

    @Test
    void realCustomerPolicyAllowsAnActiveCustomer() {
        UUID customerId = customersFixture.createActiveCustomer();
        UUID orderId = UUID.randomUUID();

        orders.place(orderId, customerId);

        assertThat(ordersRepository.existsById(orderId)).isTrue();
    }
}
~~~

Đây là **mẫu kịch bản**, không phải lớp copy-paste chạy ngay: `CustomerRepositoryFixture` là test fixture cần định nghĩa và expose đúng cách, schema/data source phải tương ứng. Trọng tâm là **không override `CustomerEligibility`**, vì muốn thực thi chính implementation của module `customers`.

Nếu `customers` phụ thuộc hạ tầng ngoài như HTTP profile provider, có thể mock **một port hạ tầng ở sâu bên trong module `customers`** hoặc dùng WireMock/Testcontainers để kiểm tra adapter; không nhất thiết phải mock chính public API đang cần kiểm chứng.

### 11.1. Khác nhau giữa kiểm thử hợp đồng và kiểm thử implementation

Một interface `CustomerEligibility` có contract:

> Trả về `false` cho khách hàng bị khóa và `true` cho khách hàng đang hoạt động.

Test `orders` với mock chỉ xác minh phản ứng khi nhận `true/false`. Test `customers` phải chứng minh implementation thật tuân thủ contract ấy bằng dữ liệu thích hợp. Integration test giữa hai module phải chứng minh wiring và dữ liệu qua boundary tương thích.

Đừng để test mock định nghĩa **hợp đồng tưởng tượng** mà implementation thật không thỏa mãn. Nếu phương thức thực có thể ném exception cho khách hàng không tồn tại, phải thể hiện điều đó trong contract và trong test.

## 12. Mocks không thay thế kiểm chứng transaction và database

Hãy so sánh ba trường hợp:

| Kiểm thử | Phụ thuộc được mock | Bằng chứng có được |
| --- | --- | --- |
| Unit test `OrderService`. | Repository, publisher và `CustomerEligibility`. | Nhánh code, số lần gọi method. |
| `@ApplicationModuleTest(STANDALONE)`. | Chỉ `CustomerEligibility`. | Logic, database, transaction và event **trong `orders`** thật. |
| Integration test trực tiếp với `customers`. | Không mock public API `CustomerEligibility`. | Hợp đồng và Spring wiring giữa hai module. |

### 12.1. Lỗi transaction có thể bị mock che giấu

Giả sử `CustomerEligibility` thực thi database query và có yêu cầu isolation phức tạp. Khi bị mock, test của `orders` **không quan sát**:

- Lock hoặc transaction propagation của service thật.
- Exception từ datasource/transaction manager module `customers`.
- Lazy loading hoặc vấn đề schema ở module ngoài.
- Tác động cạnh tranh khi hai request chạy đồng thời.

Vì vậy một ứng dụng có module tests dùng mock pass 100% vẫn có thể lỗi khi toàn bộ app boot hoặc khi hai module tương tác thật. Đây là lý do cần các tầng test khác nhau.

### 12.2. Test không nên có transaction bao ngoài khi cần commit thật

Nếu test dùng `@Transactional` ở cấp class và để Spring Test rollback cuối test, `OrderService.place(...)` thường tham gia transaction test, khiến các listener `AFTER_COMMIT` **không chạy trong suốt test**.

Khi cần kiểm tra commit/event side effect:

- Dùng test không có `@Transactional` bao ngoài, để service tạo và commit transaction riêng.
- Hoặc điều khiển rõ bằng `TransactionTemplate` / `TestTransaction`.
- Với `@ApplicationModuleListener` async, chờ theo điều kiện qua `Scenario` hoặc Awaitility.

Mock collaborator không thay đổi ngữ nghĩa commit/rollback của transaction nguồn; **đừng diễn giải `verify(mock)` như bằng chứng database đã commit**.

## 13. Mock có thể làm test pass trong khi boundary đã bị vi phạm

Một anti-pattern:

~~~java
package com.example.shop.orders;

import com.example.shop.customers.internal.CustomerRepository;

@Service
class OrderService {
    OrderService(CustomerRepository customerRepository) {
        // ...
    }
}
~~~

Đây là truy cập **implementation nội bộ** của module `customers`. Việc viết:

~~~java
@MockitoBean
CustomerRepository customerRepository;
~~~

có thể làm Spring context của `orders` test khởi động, nhưng **không hợp thức hóa phụ thuộc sai**. Nó còn khuyến khích module nguồn hiểu persistence của module khác.

Cách xử lý đúng:

1. Đặt contract thật sự cần thiết ở một public API như `customers.api.CustomerEligibility`.
2. Thực thi contract trong module `customers`.
3. Chỉ import API công khai từ `orders`.
4. Mock API đó trong module test, không mock repository nội bộ bị dùng lén.
5. Chạy `ApplicationModules.verify()` như một quality gate bắt buộc.

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

`verify()` kiểm chứng các quy tắc phụ thuộc và module API của Spring Modulith, còn Mockito chỉ thay hành vi của bean trong test. **Cả hai không thay thế nhau**.

### 13.1. Mock có thể che sự thiếu Bean thực

Ngay cả khi import đúng public API, nếu project chưa có implementation `CustomerEligibility` thật, `@MockitoBean` vẫn tạo bean để test pass. Thêm một smoke/integration test **không mock** public API, nạp các module cần thiết và kiểm tra wiring thực.

### 13.2. Mock có thể che việc gọi quá nhiều module ngoài

Nếu test `orders` phải khai báo:

~~~java
@MockitoBean CustomerEligibility customers;
@MockitoBean LoyaltyPointsService loyalty;
@MockitoBean EmailNotificationService email;
@MockitoBean ShippingScheduleService shipping;
@MockitoBean InvoiceIssuingService invoices;
~~~

có thể module đã bị **coupling quá mức** với nhiều collaborator ngoài. Các tên ngoài `CustomerEligibility` ở đây chỉ minh họa. Trước khi thêm mock thứ sáu, hãy xem luồng có thể chuyển một phần sang **domain event** hoặc xác định lại ranh giới module không.

## 14. Cách thiết kế mock ổn định và dễ bảo trì

### 14.1. Stub đủ cho hành vi cần kiểm chứng

Ưu tiên stub theo input cụ thể:

~~~java
when(customers.canPlaceOrder(customerId)).thenReturn(true);
~~~

Tránh dùng:

~~~java
when(customers.canPlaceOrder(any())).thenReturn(true);
~~~

nếu việc truyền **đúng customer ID** là điều kiện của hợp đồng. Stubbing quá rộng khiến bug truyền nhầm ID vẫn pass. Khi thật sự cần khớp một nhóm input, dùng `argThat`, `eq` hoặc `ArgumentCaptor` có chủ đích.

### 14.2. Mockito mặc định có giá trị trả về

Nếu không stub phương thức trả về `boolean`, Mockito thường trả `false`. Vì vậy test happy path có thể thất bại với `IllegalStateException` nếu quên:

~~~java
when(customers.canPlaceOrder(customerId)).thenReturn(true);
~~~

Đừng sửa bằng cách bỏ eligibility guard khỏi service; hãy hoàn chỉnh test setup đúng hành vi.

### 14.3. Reset giữa các test

`@MockitoBean` hỗ trợ reset mock và mặc định dùng `MockReset.AFTER`: các invocation/stubbing của mock được reset sau mỗi test method theo cơ chế Spring Test. Điều này giúp hạn chế tương tác còn sót giữa các test dùng chung application context.

Nhưng **mock reset không dọn database**. Fixture JPA, event publication, message từ broker, static flag và tác vụ async có thể vẫn còn. Dùng ID riêng cho test, dọn dữ liệu thích hợp và chờ tác vụ async hoàn tất khi cần. Tránh `Mockito.reset(...)` thủ công giữa một bài test nếu không có lý do rõ ràng, vì có thể xóa stub/interaction đang cần xác minh.

### 14.4. Dữ liệu và kiểm thử song song

Các context test có thể được cache. Nếu một test bắt đầu job async dùng mock rồi test kết thúc/reset, job chưa hoàn tất có thể gọi vào mock đã đổi trạng thái, gây flaky.

Không chạy song song các test chia sẻ cùng mock/fixture chưa được thiết kế thread-safe. Khi cần async listener, dùng `Scenario`/Awaitility và cô lập test data; không coi `verify(mock, timeout(...))` là bằng chứng transaction/broker đã hoàn tất nếu chưa kiểm tra dữ liệu cuối cùng.

### 14.5. Đừng stub method của chính SUT

Nếu mock `OrderService` trong test `OrderService`, test chỉ kiểm tra giá trị giả mà mình tự tạo:

~~~java
@MockitoBean
OrderService orders;
~~~

Không còn chạy logic cần bảo vệ. Chỉ mock boundary **ngoài** module; giữ bean đang kiểm thử và domain rules thật. Nếu cần override một thành phần nội bộ vì side effect khó cô lập, hãy đánh giá lại test type và thiết kế port để việc mock có lý do rõ ràng.

## 15. Kiểm thử event-driven boundary không cần mock listener ngoài

Một cách giảm coupling trong Spring Modulith là để module `orders` phát event khi đơn hàng đã được tạo:

~~~java
events.publishEvent(new OrderPlaced(
        orderId, customerId, Instant.now()));
~~~

Module `notifications` nhận:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    // Gửi thông báo sau commit.
}
~~~

Trong `@ApplicationModuleTest(STANDALONE)` của `orders`, listener ngoài module thường **không được bootstrap**, vì nó không phải dependency được inject vào `OrderService`. Do đó **không cần** một `@MockitoBean NotificationListener` chỉ để test producer.

Hãy kiểm tra event bằng:

~~~java
@Test
void publishesOrderPlaced(PublishedEvents events) {
    UUID id = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    when(customers.canPlaceOrder(customerId)).thenReturn(true);

    orders.place(id, customerId);

    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, id)).hasSize(1);
}
~~~

Đây là snippet của lớp module test mục 5.

Với listener thật, tạo test ở module `notifications` hoặc integration test có hai module và persistent Event Publication Registry. Test nguồn không chứng minh listener đã chạy, publication đã completed hay side effect email đã xảy ra.

### 15.1. Khi test @ApplicationModuleListener của module nhận

Listener `@ApplicationModuleListener` có ngữ nghĩa xử lý sau commit, async và transaction mới. Một test muốn kiểm chứng callback thật cần:

- Nạp listener module trong Spring context.
- Phát event trong transaction thực sự **commit**.
- Dùng `Scenario` hoặc Awaitility chờ kết quả thay vì `Thread.sleep` cố định.
- Xác minh DB side effect hoặc trạng thái publication sau xử lý.
- Kiểm tra retry/idempotency khi listener nhận lại event.

Mock listener bên ngoài **không thể** thay thế bài test này, vì Mockito chỉ phản hồi theo stub/verify.

## 16. Ma trận quyết định: mock gì, test ở đâu?

| Mục tiêu test | Scope | Mock/spy phù hợp | Assertion chính |
| --- | --- | --- | --- |
| Nhánh nghiệp vụ của một class đơn lẻ. | JUnit + Mockito, không Spring. | `@Mock` cho mọi dependency. | Method calls và kết quả của class. |
| Logic + JPA + event của module `orders`. | `@ApplicationModuleTest(STANDALONE)`. | `@MockitoBean` cho `customers.api.CustomerEligibility` bên ngoài. | DB state + `PublishedEvents`. |
| Kiểm tra hợp đồng customers thật. | Module test `customers`. | Có thể fake hạ tầng không liên quan. | Eligibility đúng theo dữ liệu thật. |
| Wiring orders → customers thật. | `DIRECT_DEPENDENCIES` hoặc `@SpringBootTest`. | Không mock public API đang kiểm chứng. | End-to-end qua hai module. |
| Giám sát real method nhưng vẫn giữ behavior. | Context có bean thật. | `@MockitoSpyBean` cẩn trọng. | Real side effect + verify. |
| Kiểm tra `OrderPlaced` được phát. | Module test `orders`. | Không mock `ApplicationEventPublisher`. | `PublishedEvents` lọc event ID. |
| Kiểm tra listener khác module sau commit. | Module receiver/integration. | Fake external gateway nếu cần. | Listener side effect + transaction. |
| Kiểm tra API ngoài qua HTTP. | Adapter/integration. | WireMock/fake HTTP server thay cho mock port khi phù hợp. | Request/response, retry/serialization. |
| Kiểm tra cấu trúc phụ thuộc. | Architecture test. | **Không cần Mockito**. | `ApplicationModules.verify()`. |

Đọc bảng từ **mục tiêu kiểm chứng** sang **công cụ**, thay vì bắt đầu bằng “thêm mock nào để context xanh?”.

## 17. Quality gate CI: hai ranh giới phải được bảo vệ

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, CI cần bảo vệ đồng thời:

1. **Boundary kiến trúc:** module chỉ dùng API được phép của module khác.
2. **Hợp đồng hành vi:** khi collaborator trả kết quả theo contract, module đang kiểm thử xử lý đúng, lưu đúng và phát event đúng.

Ma trận gợi ý:

| Quality gate | Kịch bản | Điều bị phát hiện |
| --- | --- | --- |
| Architecture test | `ApplicationModules.of(ShopApplication.class).verify()`. | Import `customers.internal`, cycle hoặc allowed dependency sai. |
| Module happy-path test | Eligibility mock trả `true`. | `orders` không lưu order hoặc không phát `OrderPlaced`. |
| Module rejection test | Eligibility mock trả `false`. | `orders` vẫn lưu/phát event dù bị từ chối. |
| Module failure test | Eligibility mock ném exception. | Service phát event hoặc để dữ liệu sai sau lỗi. |
| Contract test cho customers | Bean thật trả đúng true/false theo trạng thái customer. | Stub trong consumer test không khớp implementation thật. |
| Wiring test | Nạp `orders` cùng `customers` không override API. | Thiếu bean, qualifier sai, cấu hình môi trường lỗi. |
| Transaction test | Có lỗi/rollback; listener after-commit. | Test xanh nhờ mock nhưng transaction thực sai. |
| Event test | `PublishedEvents` quan sát `OrderPlaced`. | Mock publisher vô tình làm mất event hoặc payload sai. |
| Database integration | Dữ liệu thực được lưu/rollback đúng. | Mock repository che lỗi JPA/schema. |
| CI compatibility check | Dùng đúng `@MockitoBean` với Spring Framework version. | Import API không tồn tại hoặc đổi annotation sai. |

Các test nhanh (architecture, unit, module tests) nên chạy ở mỗi pull request. Integration test có database và module thật có thể thuộc stage riêng nhưng là quality gate đối với thay đổi contract, wiring hoặc transaction. Không dùng số lượng mock thấp làm mục tiêu tự thân; số lượng mock tăng là **tín hiệu để xem lại coupling**, không phải tự động có lỗi.

### 17.1. Nếu module test fail vì thiếu bean

Checklist debug theo thứ tự:

1. Xác định **test đang nằm trong module nào** (package test/class và cách Spring Modulith phát hiện module).
2. Xác định `@ApplicationModuleTest` đang ở mode nào.
3. Xác định dependency thật được inject qua constructor thuộc module nào.
4. Kiểm tra có phải public API hợp lệ hay đang import implementation nội bộ.
5. Nếu public collaborator ngoài module và test không cần logic thật, dùng `@MockitoBean` cho đúng type/qualifier.
6. Nếu cần logic thật, chuyển sang `DIRECT_DEPENDENCIES` hoặc integration test.
7. Chạy `ApplicationModules.verify()` để không chữa vi phạm boundary bằng mock.
8. Có ít nhất một test wiring toàn phần để tránh mock che thiếu bean production.

## 18. Các anti-pattern tiêu biểu

### 18.1. Mock mọi thứ để test chạy nhanh

~~~java
@MockitoBean OrderService orders;
@MockitoBean OrderRepository repository;
@MockitoBean ApplicationEventPublisher publisher;
@MockitoBean CustomerEligibility customers;
~~~

Đây hầu như chỉ còn kiểm tra Mockito stubbing, **không kiểm chứng module `orders` thực tế**. Với module integration test, hãy giữ các phần lõi cùng database/event hạ tầng phù hợp thật.

### 18.2. Mock bean nội bộ của module khác bị import sai

~~~java
@MockitoBean
CustomerRepository customerRepository; // customers.internal
~~~

Ngăn context fail nhưng che một phụ thuộc không được phép. Giải pháp là public API hoặc event, cộng với architecture test.

### 18.3. Dùng spy như mock cho bean không tồn tại

~~~java
@ApplicationModuleTest
class BadSpyTest {
    @MockitoSpyBean CustomerEligibility customers;
}
~~~

Trong `STANDALONE`, nếu không có `CustomerEligibility` bean thật ở context, spy không thể wrap và sẽ lỗi. `@MockitoBean` mặc định tạo mock; spy thì yêu cầu bean sẵn có.

### 18.4. Dùng @Mock trong module integration test và tưởng Spring sẽ inject

~~~java
@ApplicationModuleTest
class BadContextTest {
    @Mock CustomerEligibility customers;
}
~~~

`@Mock` tự nó không tạo Spring bean. `OrderService` được Spring tạo vẫn có thể báo thiếu collaborator.

### 18.5. Test verify tương tác mà không assert kết quả

~~~java
verify(customers).canPlaceOrder(customerId);
~~~

Service có thể gọi đúng method nhưng vẫn bỏ qua kết quả, không lưu order, hoặc phát event sai. Cần kiểm tra **state và event** cùng interaction.

### 18.6. Chuyển mọi test sang ALL_DEPENDENCIES

`ALL_DEPENDENCIES` thường làm scope tăng, dẫn đến test chậm, khó cô lập và nhiều resource không liên quan. Chỉ dùng khi muốn kiểm chứng toàn bộ cây dependency.

### 18.7. Stub spy bằng when khiến method thật chạy

Với spy có method gửi HTTP hoặc ghi DB, `when(spy.call()).thenReturn(...)` có thể thực thi call ngay khi stub. Dùng `doReturn(...).when(spy)...` khi muốn tránh lời gọi thật trong stubbing, đồng thời cân nhắc AOP proxy.

### 18.8. Dùng mock của module nhận để chứng minh event đã xử lý

Mock listener có thể nhận `verify(mock)` nhưng không chứng minh `@ApplicationModuleListener` thực thi sau commit, không chứng minh Registry completion hoặc database side effect. Kiểm thử đường event thật ở receiver/integration test.

## 19. Bài tập tình huống

Một hệ thống Spring Modulith có các module:

- `checkout`: thực hiện thanh toán đơn hàng, có `CheckoutService`.
- `pricing`: cung cấp public API `PriceQuoteService.quote(cartId)`.
- `loyalty`: cung cấp `LoyaltyAwardService.awardPoints(orderId)`.
- `notifications`: lắng nghe `CheckoutCompleted` qua `@ApplicationModuleListener`.

`CheckoutService` hiện gọi đồng bộ cả `PriceQuoteService` và `LoyaltyAwardService`, sau đó lưu checkout và phát event.

### Câu hỏi

1. Nếu kiểm thử `checkout` bằng `@ApplicationModuleTest` mặc định, vì sao có thể thiếu hai bean ngoài module?
2. Khi mục tiêu là kiểm tra logic chấp nhận quote và lưu checkout, nên mock collaborator nào?
3. `LoyaltyAwardService` chỉ ghi điểm sau khi thanh toán đã thành công: có nhất thiết phải gọi đồng bộ từ `CheckoutService` không?
4. Nếu `PriceQuoteService` bị mock trả quote hợp lệ, test đó đã chứng minh implementation thật của `pricing` trả quote đúng chưa?
5. `@MockitoSpyBean PriceQuoteService` có hoạt động trong `STANDALONE` nếu không có bean thật không?
6. Vì sao không nên mock `ApplicationEventPublisher` khi mục tiêu là kiểm tra `CheckoutCompleted` bằng `PublishedEvents`?
7. Vì sao `ApplicationModules.verify()` phải là quality gate dù test Mockito đều pass?
8. Khi chuyển `LoyaltyAwardService` sang listener event, cần thêm kiểu test gì?

### Đáp án gợi ý

1. Vì `STANDALONE` chỉ khởi tạo module `checkout`, không tự tải các implementation bean của `pricing` và `loyalty`.
2. Mock **public API** `PriceQuoteService` bằng `@MockitoBean`; nếu synchronous loyalty là hợp đồng hiện hữu và cần cô lập, có thể mock `LoyaltyAwardService` tạm thời nhưng cần đánh giá coupling.
3. Không nhất thiết. Nếu awarding points là side effect sau commit và không cần phản hồi đồng bộ, có thể nhận `CheckoutCompleted` qua `@ApplicationModuleListener`.
4. Chưa. Cần test module `pricing` và integration/wiring test dùng bean thật.
5. Không. `@MockitoSpyBean` wrap bean hiện hữu, không tạo một bean vắng mặt.
6. Vì mock publisher không gửi sự kiện qua Spring infrastructure thật; `PublishedEvents` dùng để kiểm tra phát event.
7. Vì mock có thể che dependency sai vào implementation `pricing.internal` hoặc vòng phụ thuộc; architecture test kiểm tra boundary tĩnh.
8. Test listener ở module `loyalty`/integration có commit thật, async waiting, side effect DB, retry/idempotency và event publication completion.

## 20. Checklist trước khi dùng mock collaborator ngoài module

- [ ] Biết chính xác **module đang kiểm thử** và chế độ bootstrap của `@ApplicationModuleTest`.
- [ ] Collaborator được xác định thuộc **module khác**, không phải thành phần lõi đang kiểm thử.
- [ ] Module nguồn chỉ dùng public API/named interface của module ngoài; không import implementation/repository nội bộ.
- [ ] Chọn `STANDALONE` + `@MockitoBean` khi không cần thực thi logic thật của module ngoài.
- [ ] Chọn `DIRECT_DEPENDENCIES`/integration test nếu cần kiểm tra hợp đồng và bean wiring thật.
- [ ] Không dùng `@MockitoSpyBean` khi không có bean thật trong context.
- [ ] Đúng phiên bản: `@MockitoBean` của Spring Framework 6.2+; dự án cũ có thể cần `@MockBean`.
- [ ] Không đặt `enforceOverride = true` khi chính mục tiêu là tạo mock cho bean đã bị loại bởi `STANDALONE`.
- [ ] Có qualifier hoặc bean name rõ nếu nhiều candidate cùng interface.
- [ ] Stub chính xác input liên quan, không dùng `any()` quá rộng làm che bug tham số.
- [ ] Mock reset và test isolation được hiểu đúng; database/async fixture cần dọn riêng.
- [ ] Không mock SUT, domain logic, repository hoặc `ApplicationEventPublisher` khi test cần chạy chúng thật.
- [ ] Assert **kết quả nghiệp vụ**, **event** và tương tác API ngoài module khi thực sự cần.
- [ ] Module test không bao `@Transactional` ngoài ý muốn nếu kiểm tra `AFTER_COMMIT`.
- [ ] Có test implementation thật của collaborator và ít nhất một test wiring/integration không override public API.
- [ ] Nhiều mock ngoài module được xem là tín hiệu đánh giá coupling/event-driven design.
- [ ] `ApplicationModules.verify()`, `@ApplicationModuleTest` và integration test được đặt trong CI.

**Kết luận:** Hãy mock collaborator ngoài module **khi cần kiểm chứng hành vi của module hiện tại mà không khởi động implementation của module khác**. Trong `@ApplicationModuleTest(STANDALONE)`, `@MockitoBean` tạo đúng bean thay thế để service của module hiện tại chạy thật với một API ngoài module có kết quả do test kiểm soát. Nhưng mock không xác nhận hợp đồng thật, không sửa vi phạm module boundary và không thay integration test; kết hợp nó với `ApplicationModules.verify()`, kiểm thử database/event và test wiring thực để có chất lượng kiến trúc lẫn hành vi.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes và mocking efferent dependencies.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `PublishedEvents`, transactional listeners và `Scenario`.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): replace/create, spy, qualifiers và AOP caveats.
- [Spring Framework — MockitoBean API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): `enforceOverride`, reset và bean-override semantics.
- [Spring Boot 3.4 — MockBean API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): deprecation và chuyển sang Framework `@MockitoBean`.

> Ghi chú tương thích: mã minh họa dùng Spring Boot/Spring Framework có `@MockitoBean`, Spring Modulith và Spring Data JPA phù hợp. Các entity, fixture và database test config cần được triển khai thêm trong dự án cụ thể. Theo quy trình biên soạn STEP_4, bài chưa trải qua Content QA chuyên môn hoặc thực thi kiểm thử Gradle.
