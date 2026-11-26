# Application module test cho một module hoàn chỉnh

> **Chương:** Test types  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Dùng `@ApplicationModuleTest` để kiểm thử phần Spring của một application module, từ API qua service, repository và event publication, đồng thời xác định rõ ranh giới của bài kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **unit test**, **slice test**, **application module test**, **kiểm chứng kiến trúc** và **kiểm thử tích hợp toàn ứng dụng**.
2. Tổ chức package của một application module để Spring Modulith nhận diện đúng module khi chạy `@ApplicationModuleTest`.
3. Viết bài test khởi tạo các bean thực của một module, gọi API của module, lưu và đọc dữ liệu qua JPA.
4. Kiểm tra sự kiện được module phát ra bằng `PublishedEvents`; biết khi nào phải kiểm thử riêng việc listener nhận và xử lý sự kiện sau commit.
5. Chọn đúng `BootstrapMode.STANDALONE`, `DIRECT_DEPENDENCIES` hoặc `ALL_DEPENDENCIES` và xử lý dependency ngoài phạm vi module.
6. Kết hợp `ApplicationModules.verify()`, module test và quality gate CI để phát hiện sai phạm cấu trúc cùng hồi quy hành vi.

Trong Spring Modulith, application module là đơn vị tổ chức chức năng trong một ứng dụng Spring Boot. Ta muốn mỗi module có API rõ ràng, phụ thuộc theo chiều hợp lệ và đủ độc lập để kiểm thử. **`@ApplicationModuleTest` là công cụ kiểm tra sự phối hợp của các Spring bean thuộc một module** mà không phải mặc định tải toàn bộ ứng dụng.

Bài học dùng một module đặt hàng minh họa. Các tên package, quy tắc nghiệp vụ và dữ liệu là ví dụ độc lập, không đại diện cho một hệ thống production cụ thể.

## 2. “Một module hoàn chỉnh” nghĩa là gì khi kiểm thử?

Giả sử ứng dụng có ba module nghiệp vụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders/                          # module orders
│   ├── OrderManagement.java         # API công khai
│   ├── OrderView.java               # kiểu dữ liệu công khai
│   ├── OrderPlaced.java             # sự kiện công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderJpaEntity.java
│           └── OrderJpaRepository.java
├── inventory/                       # module khác
└── notification/                    # module khác
~~~

Trong cách bố trí mặc định của Spring Modulith, các package trực tiếp dưới package ứng dụng chính thường là application module. Các kiểu ở root package `com.acme.shop.orders` thuộc API module mặc định; những thành phần ở `orders.internal` là phần triển khai nội bộ. Việc một class là `public` trong Java **không tự biến nó thành API được phép dùng từ module khác**.

~~~mermaid
flowchart LR
    T["OrderModuleTest<br/>@ApplicationModuleTest"] --> API["orders API<br/>OrderManagement"]
    subgraph O["Module orders"]
        API --> S["OrderApplicationService"]
        S --> R["OrderJpaRepository"]
        R --> DB[("Database test")]
        S --> E["OrderPlaced event"]
    end
    INV["Module inventory"] -. "không mặc định khởi tạo" .-> O
    N["Module notification"] -. "không mặc định khởi tạo" .-> O
~~~

Ở đây, “hoàn chỉnh” nghĩa là **các thành phần cần thiết để thực hiện một hành vi của module đang được kiểm thử cùng nhau**: bean wiring, lời gọi service, transaction, persistence và việc publish event. Nó không có nghĩa mọi module còn lại hoặc mọi dịch vụ production phải chạy trong test.

Một module test cần đặt ra câu hỏi quan sát được, ví dụ:

- Lời gọi `OrderManagement.placeOrder(...)` có lưu đơn và trả ID đúng không?
- Dữ liệu lưu có đọc được trở lại qua API của chính module không?
- Đầu vào không hợp lệ có bị từ chối đúng không?
- Khi đặt hàng thành công, module có phát ra `OrderPlaced` chứa ID vừa lưu không?

Những câu hỏi đó yêu cầu phần thực thi bên trong module phối hợp được với nhau. Do vậy unit test một class hoặc mock toàn bộ repository sẽ chưa đủ.

## 3. @ApplicationModuleTest và các chế độ bootstrap

Annotation `@ApplicationModuleTest` thuộc `org.springframework.modulith.test`. Nó sử dụng cơ chế kiểm thử Spring Boot nhưng giới hạn phạm vi bean theo application module gắn với package của test, kết hợp với chế độ bootstrap đã chọn.

### 3.1. Ba chế độ thường dùng

| Bootstrap mode | Phạm vi bean ứng dụng được xét | Khi phù hợp | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| `STANDALONE` (mặc định) | Module của test | Kiểm tra module tự vận hành với các dependency được cung cấp/được thay thế cần thiết | Bean của module khác không mặc nhiên sẵn có |
| `DIRECT_DEPENDENCIES` | Module của test cùng những module mà nó phụ thuộc trực tiếp | Kiểm tra phối hợp với dependency trực tiếp | Không tự động đưa các module phụ thuộc ngược vào test |
| `ALL_DEPENDENCIES` | Module của test cùng chuỗi dependency bắc cầu | Luồng cần nhiều module ở phía dependency | Context lớn và nhiều yếu tố ảnh hưởng hơn |

Cú pháp:

~~~java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest
class StandaloneOrdersTest {
    // STANDALONE là mode mặc định
}

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithDirectDependenciesTest {
    // Nạp module orders và dependency trực tiếp của nó
}

@ApplicationModuleTest(mode = BootstrapMode.ALL_DEPENDENCIES)
class OrdersWithTransitiveDependenciesTest {
    // Nạp module orders cùng các dependency bắc cầu
}
~~~

Đây là **ba cách cấu hình độc lập** để minh họa, không phải ba lớp test bắt buộc phải tạo cho cùng một hành vi.

**Phụ thuộc có hướng:** Nếu `notification` cần đọc kiểu sự kiện `orders.OrderPlaced`, thông thường `notification` phụ thuộc `orders`. Khi kiểm thử `orders` với `DIRECT_DEPENDENCIES`, không vì vậy mà Spring tự nạp `notification`. Muốn xác nhận listener của `notification`, hãy kiểm thử module consumer với dependencies phù hợp hoặc chạy integration test bao trùm cả hai.

### 3.2. Vị trí test quyết định module được nhận diện

Đặt test dưới package ứng với module, chẳng hạn:

~~~text
src/test/java/com/acme/shop/orders/OrdersModuleIntegrationTest.java
~~~

Không đặt mọi module test vào chung package `com.acme.shop` mà mong framework tự đoán module cần kiểm tra từ tên class. Việc định vị module của test dựa trên cấu trúc package và mô hình module ứng dụng; cấu hình bootstrap sẽ vô nghĩa nếu framework không nhận diện đúng module.

### 3.3. Dependency cần có

Ví dụ Gradle trong ứng dụng Spring Boot/Spring Modulith đã quản lý phiên bản thư viện:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testRuntimeOnly("com.h2database:h2")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Phải dùng BOM/plugin quản lý phiên bản Spring Boot và Spring Modulith tương thích trong dự án thực tế. `spring-modulith-starter-test` cung cấp các tiện ích test của Modulith; `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và hạ tầng test thông dụng. `H2` chỉ đóng vai trò database kiểm thử cho ví dụ, không phải yêu cầu bắt buộc của `@ApplicationModuleTest`.

Nếu dự án đã có dependency tương đương thì không khai báo trùng. Với ứng dụng dùng database khác, có thể lựa chọn Testcontainers để chạy cùng loại database production thay cho H2.

## 4. Xây dựng một application module để kiểm thử

Ta xây dựng luồng:

~~~mermaid
sequenceDiagram
    participant Test as Module test
    participant API as OrderManagement
    participant Service as OrderApplicationService
    participant Repo as OrderJpaRepository
    participant DB as Test database
    participant Events as ApplicationEventPublisher
    Test->>API: placeOrder(customerId, amount)
    API->>Service: giao dịch qua Spring proxy
    Service->>Repo: save(entity)
    Repo->>DB: INSERT
    DB-->>Repo: generated ID
    Repo-->>Service: saved entity
    Service->>Events: publishEvent(OrderPlaced)
    Service-->>Test: orderId
    Test->>API: findById(orderId)
    API->>Service: tra cứu
    Service->>Repo: findById(orderId)
    Repo->>DB: SELECT
    DB-->>Test: kết quả qua service
~~~

### 4.1. Ứng dụng Spring Boot và API module

**`src/main/java/com/acme/shop/ShopApplication.java`**

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

**`src/main/java/com/acme/shop/orders/OrderManagement.java`**

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;
import java.util.Optional;

public interface OrderManagement {

    long placeOrder(String customerId, BigDecimal amount);

    Optional<OrderView> findById(long id);
}
~~~

**`src/main/java/com/acme/shop/orders/OrderView.java`**

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;

public record OrderView(
        long id,
        String customerId,
        BigDecimal amount
) {}
~~~

**`src/main/java/com/acme/shop/orders/OrderPlaced.java`**

~~~java
package com.acme.shop.orders;

public record OrderPlaced(long orderId) {}
~~~

API chỉ chứa hành vi và kiểu cần chia sẻ. Nó không để lộ `JpaRepository` hay JPA entity cho client của module. Sự kiện `OrderPlaced` được đưa vào package API vì các module khác có thể cần subscribe sự kiện này trong hệ thống hoàn chỉnh.

### 4.2. Entity và repository nội bộ

**`src/main/java/com/acme/shop/orders/internal/persistence/OrderJpaEntity.java`**

~~~java
package com.acme.shop.orders.internal.persistence;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
public class OrderJpaEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String customerId;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal amount;

    protected OrderJpaEntity() {
        // JPA constructor
    }

    public OrderJpaEntity(String customerId, BigDecimal amount) {
        this.customerId = customerId;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

**`src/main/java/com/acme/shop/orders/internal/persistence/OrderJpaRepository.java`**

~~~java
package com.acme.shop.orders.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderJpaRepository
        extends JpaRepository<OrderJpaEntity, Long> {
}
~~~

Các kiểu trong `orders.internal.persistence` có thể để `public` khi phục vụ cơ chế reflection/proxy của framework. Chúng vẫn là thành phần **nội bộ của application module** theo package model mặc định của Spring Modulith.

### 4.3. Application service, transaction và event

**`src/main/java/com/acme/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.acme.shop.orders.internal;

import java.math.BigDecimal;
import java.util.Optional;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.shop.orders.OrderManagement;
import com.acme.shop.orders.OrderPlaced;
import com.acme.shop.orders.OrderView;
import com.acme.shop.orders.internal.persistence.OrderJpaEntity;
import com.acme.shop.orders.internal.persistence.OrderJpaRepository;

@Service
class OrderApplicationService implements OrderManagement {

    private final OrderJpaRepository repository;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderJpaRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Override
    @Transactional
    public long placeOrder(String customerId, BigDecimal amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        var saved = repository.save(
                new OrderJpaEntity(customerId, amount));

        long id = saved.getId();
        events.publishEvent(new OrderPlaced(id));
        return id;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<OrderView> findById(long id) {
        return repository.findById(id)
                .map(entity -> new OrderView(
                        entity.getId(),
                        entity.getCustomerId(),
                        entity.getAmount()));
    }
}
~~~

Điểm cần quan sát trong bài module test:

- Spring tạo bean `OrderApplicationService` và inject `OrderJpaRepository` cùng `ApplicationEventPublisher`.
- Spring quản lý transaction cho lời gọi phương thức qua bean proxy, trong khi JPA thực hiện lưu/truy vấn dữ liệu thật vào database test.
- ID chỉ có sau khi entity được lưu; `OrderPlaced` dùng ID đó làm payload.
- `findById` chuyển entity nội bộ thành `OrderView` thuộc API, không trả entity trực tiếp ra ngoài.

Vì service triển khai interface công khai của module, test có thể chỉ inject `OrderManagement`, qua đó kiểm tra hợp đồng module và để implementation tự được resolve bởi Spring.

> **Giới hạn của ví dụ:** Ở đây sự kiện được publish trong transaction nhưng chưa có listener. Phát ra sự kiện **không đồng nghĩa** với listener ở module khác đã chạy, đã commit hoặc đã gửi dữ liệu sang hệ thống ngoài. Những thuộc tính đó cần bài kiểm thử riêng.

## 5. Bài kiểm thử module hoàn chỉnh với @ApplicationModuleTest

Ví dụ cấu hình H2 trong ngữ cảnh test; ở dự án có Flyway/Liquibase hoặc schema migration thật, cần phối hợp chiến lược tạo schema và version database thay vì mặc định `ddl-auto=create-drop`.

**`src/test/java/com/acme/shop/orders/OrdersModuleIntegrationTest.java`**

~~~java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.TestPropertySource;

@ApplicationModuleTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:orders-test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrdersModuleIntegrationTest {

    @Autowired
    OrderManagement orders;

    @Test
    void persists_and_reads_an_order_through_module_api() {
        long id = orders.placeOrder(
                "CUS-007", new BigDecimal("120.00"));

        var order = orders.findById(id);

        assertThat(order).contains(new OrderView(
                id, "CUS-007", new BigDecimal("120.00")));
    }

    @Test
    void publishes_order_placed_event(PublishedEvents events) {
        long id = orders.placeOrder(
                "CUS-008", new BigDecimal("85.00"));

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void rejects_non_positive_amount() {
        assertThatThrownBy(() -> orders.placeOrder(
                "CUS-009", BigDecimal.ZERO))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("amount must be positive");
    }

    @Test
    void returns_empty_when_order_does_not_exist() {
        assertThat(orders.findById(-1L)).isEmpty();
    }
}
~~~

### 5.1. Mỗi test chứng minh điều gì?

| Test | Hành vi được chứng minh | Hành vi chưa được chứng minh |
| --- | --- | --- |
| `persists_and_reads_an_order_through_module_api` | API được Spring nối với implementation; JPA lưu/đọc dữ liệu và mapper trả `OrderView` đúng | Schema và SQL sẽ tương thích với mọi database production |
| `publishes_order_placed_event` | Lời gọi API làm Spring phát ra `OrderPlaced` chứa ID đúng trong lúc test | Listener ở module khác đã xử lý thành công hoặc xử lý sau commit |
| `rejects_non_positive_amount` | Service thực từ chối input vi phạm quy tắc | Toàn bộ chính sách xác thực từ REST API |
| `returns_empty_when_order_does_not_exist` | Đường đọc trả kết quả rỗng khi không có bản ghi tương ứng | HTTP status của controller, nếu ứng dụng có HTTP adapter |

Trong test thứ hai, Spring Modulith cung cấp đối tượng `PublishedEvents` cho phương thức test. `ofType(OrderPlaced.class)` lọc những sự kiện được phát trong phạm vi test, còn assertion xác nhận sự kiện chứa ID mong đợi.

### 5.2. Vì sao không mock repository trong bài này?

Nếu thay `OrderJpaRepository` bằng mock, test sẽ bỏ qua mapping JPA, database và wiring thật của repository. Khi mục tiêu là **kiểm tra một module cùng các thành phần nội bộ phối hợp**, ta giữ repository thật và cung cấp database test.

Ngược lại, với unit test riêng của `OrderApplicationService`, việc dùng mock repository và fake `ApplicationEventPublisher` có thể hợp lý vì bài test đó chỉ kiểm tra thuật toán/phối hợp trong class mà không cần Spring. Hai lớp kiểm thử bổ sung cho nhau.

### 5.3. Vì sao không cần @Transactional trên lớp test?

`OrderApplicationService.placeOrder(...)` tự mở transaction cho việc ghi dữ liệu. Bản thân test trong ví dụ **không có `@Transactional`**, để transaction của service có thể commit trước khi phương thức trả về. Đây là điều quan trọng nếu sau này muốn quan sát logic `@TransactionalEventListener(phase = AFTER_COMMIT)`.

Nếu đặt `@Transactional` trên test, service có thể tham gia transaction của test, và Spring Test thường rollback transaction đó sau test. Khi ấy listener yêu cầu **AFTER_COMMIT** sẽ không được gọi như trong một luồng commit thật. Đừng vô tình viết test sai pha transaction rồi kết luận rằng hệ thống không phát sự kiện.

Mặt khác, nếu test cần tự rollback dữ liệu, có thể dùng transaction ở test và lựa chọn chiến lược riêng cho các bài kiểm thử event hậu commit. Việc chia test theo loại transaction rõ ràng giúp tránh false positive/false negative.

### 5.4. Tính độc lập dữ liệu

Bài trên sử dụng ID do database sinh ra, tránh kỳ vọng ID cụ thể hoặc số lượng tổng cộng tất cả bản ghi. `PublishedEvents` chỉ được kiểm tra trong phạm vi mỗi bài test, không đếm sự kiện toàn ứng dụng.

Trong suite lớn, có thể cấp một database/schema riêng cho từng test class hoặc chạy Testcontainers có cơ chế reset dữ liệu. Không phụ thuộc thứ tự chạy test và không lấy kết quả của test trước làm điều kiện cho test sau.

## 6. Kiểm thử sự kiện: phát ra khác với xử lý thành công

Spring Modulith hỗ trợ cách ứng dụng giao tiếp qua event giữa các module. Ví dụ `orders` phát `OrderPlaced` và module `notification` đăng ký listener.

~~~mermaid
flowchart LR
    O["orders<br/>publish OrderPlaced"] --> B["Spring event infrastructure"]
    B --> N["notification<br/>@ApplicationModuleListener"]
    N --> X["email/SMS adapter"]
~~~

**Ba câu hỏi cần kiểm tra tách biệt:**

1. **Publisher:** `orders` có publish đúng kiểu sự kiện và payload khi xử lý nghiệp vụ thành công không? `PublishedEvents` trong module test publisher phù hợp.
2. **Consumer:** `notification` có nhận sự kiện và thực thi đúng logic của riêng nó không? Kiểm thử module consumer, kích hoạt event trong test, dùng fake outbound adapter hoặc hạ tầng test phù hợp.
3. **Giao nhận và transaction:** listener chạy sau commit, cơ chế retry, event publication registry hoặc broker hoạt động chính xác không? Cần module/integration test được cấu hình tương ứng, đặc biệt khi xử lý bất đồng bộ.

`PublishedEvents` là công cụ quan sát **sự kiện được phát**; không nên dùng nó làm bằng chứng rằng một listener bất đồng bộ đã hoàn tất. Nếu phải chờ phản ứng từ event một cách có chủ đích, Spring Modulith cung cấp tiện ích `Scenario` để mô tả stimulus và điều kiện hoàn thành/đợi event. Chi tiết API của `Scenario` phụ thuộc phiên bản; hãy chọn assertion và thời điểm đồng bộ phù hợp với loại listener bạn đang kiểm tra.

### 6.1. Trường hợp nhận sự kiện sau commit

Một listener có thể được khai báo:

~~~java
package com.acme.shop.notification.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.acme.shop.orders.OrderPlaced;

@Component
class OrderNotificationListener {

    private final NotificationSender sender;

    OrderNotificationListener(NotificationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendOrderConfirmation(event.orderId());
    }
}
~~~

Đây là đoạn minh họa cho module `notification`, không thuộc tập file tối thiểu của `orders`. `NotificationSender` là port của consumer, giả sử đã tồn tại trong cùng module. Annotation `@ApplicationModuleListener` là lựa chọn của Spring Modulith cho listener sự kiện theo cơ chế transactional/asynchronous phù hợp với cấu hình. Cách xử lý, retry và publication registry cụ thể còn phụ thuộc các thư viện, transaction manager và hạ tầng có trong ứng dụng.

Kiểm thử listener này phải có bean listener của **notification** và một cách quan sát `NotificationSender`; module test của **orders** ở `STANDALONE` không tự nạp listener từ module khác. Nếu handler bất đồng bộ, cần có điều kiện chờ có giới hạn thay vì `Thread.sleep(...)` cố định.

## 7. Xử lý dependency bên ngoài module

Một module thực tế có thể cần bean do module khác cung cấp, chẳng hạn `InventoryAvailability` hoặc `PaymentGateway`. Ở `STANDALONE`, nếu bean đó nằm ngoài module và không được tạo trong test context, Spring có thể báo lỗi dạng `NoSuchBeanDefinitionException`.

Có ba cách giải quyết tùy mục tiêu:

| Chiến lược | Mục đích | Lưu ý |
| --- | --- | --- |
| Giữ `STANDALONE` và cung cấp fake/mock cho port | Chỉ tập trung kiểm tra module hiện tại | Tránh mock nội bộ của chính module khi muốn xác minh wiring nội bộ |
| Chuyển `DIRECT_DEPENDENCIES` | Kiểm tra module cùng dependency trực tiếp | Chỉ dùng khi dependency thật là một phần của hành vi cần quan sát |
| Chuyển `ALL_DEPENDENCIES` | Cần cả chuỗi dependency bắc cầu | Test có thể chậm và khó phân biệt lỗi hơn |

Ví dụ nếu `OrderApplicationService` thêm dependency tới port `InventoryAvailability`, ta có thể dùng mock bean trong context test:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

// Trích đoạn minh họa: đặt field trong lớp test @ApplicationModuleTest.
@MockitoBean
InventoryAvailability inventory;
~~~

Annotation `@MockitoBean` thuộc Spring Framework 6.2+ (thường tương ứng Spring Boot 3.4+). Với các phiên bản Boot cũ hơn có thể dùng `@MockBean` theo API được cung cấp; không dùng đồng thời hai cách. Kiểu `InventoryAvailability` là port giả định phải được khai báo/cho phép truy cập đúng theo thiết kế module; trích đoạn trên chỉ minh họa việc cung cấp bean và **không thay thế yêu cầu kiểm chứng kiến trúc**.

Lỗi thường gặp là chuyển toàn bộ module test sang `ALL_DEPENDENCIES` ngay khi thấy thiếu bean. Việc cần làm trước là xác nhận dependency đang thiếu có **thực sự thuộc hợp đồng cần kiểm tra** hay không và module có được phép phụ thuộc vào nó theo mô hình kiến trúc hay không.

## 8. Kiểm chứng ranh giới kiến trúc vẫn là bước riêng

`@ApplicationModuleTest` khởi tạo một phạm vi Spring để kiểm tra hành vi. Nó không thay thế một bài kiểm tra cấu trúc module bằng `ApplicationModules`.

**`src/test/java/com/acme/shop/ArchitectureVerificationTest.java`**

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTest {

    @Test
    void modules_respect_dependency_rules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Phép `verify()` dựa trên mô hình application module và các quy tắc kiến trúc mà Spring Modulith xác minh, gồm phát hiện các quan hệ phụ thuộc không hợp lệ và vi phạm mô hình module. Trong kiến trúc có quy định `allowedDependencies` hoặc named interfaces, kiểm tra này càng quan trọng vì **code chạy được vẫn có thể phụ thuộc sai hướng**.

Ví dụ lỗi mà việc kiểm tra cấu trúc cần phát hiện:

~~~java
// Trong package com.acme.shop.notification.internal
// Truy cập implementation nội bộ của module orders:
import com.acme.shop.orders.internal.persistence.OrderJpaEntity;
~~~

Nếu module `notification` cần dữ liệu đơn hàng, nó nên làm việc qua API hợp lệ hoặc sự kiện do `orders` công bố, không import JPA entity nội bộ. Module test của `orders` vẫn có thể xanh dù module khác viết import sai, bởi test đang giới hạn phạm vi thành phần.

### Sự khác nhau về mặt bằng chứng

- **Architecture verification**: ứng dụng tuân thủ quy tắc phụ thuộc và phạm vi API đến đâu?
- **Module test**: các bean trong module phối hợp đúng theo tình huống đã kiểm thử không?
- **Slice test**: adapter web/JPA/JSON có tuân thủ hợp đồng công nghệ riêng không?
- **Unit test**: quy tắc nghiệp vụ thuần Java có đúng không?
- **Integration/E2E test**: luồng đi qua nhiều module và hạ tầng thật có đáp ứng hợp đồng đầu cuối không?

Mỗi loại kiểm thử trả lời một câu hỏi khác nhau. Một quality gate có độ tin cậy cao phải chọn đủ lớp kiểm tra cho rủi ro của ứng dụng.

## 9. Những rủi ro khi dùng database thật, H2 và transaction

### 9.1. H2 không tự chứng minh tương thích production

Ví dụ dùng H2 để minh họa toàn bộ đường đi qua Spring Data JPA với setup đơn giản. Tuy nhiên H2 khác PostgreSQL, MySQL hoặc Oracle về dialect, function, lock, constraint, kiểu dữ liệu và chi tiết transaction.

Nếu adapter phụ thuộc native query, JSON column, isolation hoặc lock, nên chạy thêm module/integration test với loại database giống production. Testcontainers là một lựa chọn thường gặp. Có thể dùng Spring Boot service connection hoặc cấu hình datasource theo phiên bản Boot thực tế, sau đó bảo đảm test kết nối tới container thay vì embedded H2.

### 9.2. Schema và dữ liệu test

- Nếu dùng Flyway/Liquibase, test cần có chiến lược migration giống môi trường triển khai và tránh xung đột với Hibernate DDL generation.
- Dùng dữ liệu gọn, có ý nghĩa, do từng test tự tạo.
- Với test kiểm tra constraint, `flush` có thể cần thiết để ép lỗi SQL xuất hiện tại thời điểm assertion.
- Không để test phụ thuộc vào bản ghi “seed” không được quản lý hoặc ID bắt đầu từ 1.
- Nếu cần xác nhận `AFTER_COMMIT`, phải bảo đảm giao dịch thật sự commit; test rollback mặc định có thể khiến assertion sai ngữ cảnh.

### 9.3. Khi nào nên dùng test infrastructure thật?

Chỉ dùng database/container/broker nếu mục tiêu yêu cầu kiểm chứng đặc tính của nó. Ví dụ quy tắc tính giá độc lập không cần database; JPA query có native SQL cần database tương thích; giao nhận event qua broker cần broker hoặc test infrastructure tương đương.

Đưa mọi kiểm thử lên `@SpringBootTest` với đầy đủ hạ tầng sẽ làm vòng phản hồi chậm mà chưa chắc tăng độ chính xác cho từng câu hỏi nhỏ. Với module integration test, hãy giữ phạm vi bean theo đúng dependency cần quan sát.

## 10. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| Không nhận diện được module của test | Test đặt sai package, mô hình module khác cấu trúc mặc định | Kiểm tra package ứng dụng, package test và cấu hình module |
| Thiếu bean của module khác | `STANDALONE` không nạp module dependency | Cung cấp mock/fake đúng biên hoặc chọn bootstrap mode phù hợp |
| Test chạy cả hệ thống và khởi tạo lâu | Chọn phạm vi bootstrap quá rộng | Giảm phạm vi về `STANDALONE` hoặc `DIRECT_DEPENDENCIES` nếu hợp đồng cho phép |
| Thiếu database hoặc lỗi schema | Không có datasource test, thiếu driver hoặc migration | Cấu hình H2/Testcontainers và schema rõ ràng |
| Event assertion xanh nhưng listener không chạy | `PublishedEvents` chỉ xác nhận publish | Viết test riêng cho consumer hoặc giao nhận sau commit |
| Listener `AFTER_COMMIT` không nhận event | Test đang rollback giao dịch | Kiểm tra ranh giới transaction và cho commit khi mục tiêu yêu cầu |
| Module test xanh nhưng import package nội bộ sai | Module test không thay thế structural verification | Chạy `ApplicationModules.verify()` trong CI |
| Test không ổn định khi chạy song song | Dữ liệu/port/database/shared state dùng chung | Cô lập fixture, ID, schema hoặc container theo hợp đồng |
| Test JPA H2 xanh nhưng production lỗi | Khác SQL dialect hoặc constraint | Chạy thêm kiểm thử database đúng loại production |

Không nên tự động xử lý mọi `NoSuchBeanDefinitionException` bằng cách import mọi configuration của ứng dụng. Hãy xác định bean thuộc module nào, vì sao nó cần có và module được phép phụ thuộc vào nó hay không.

## 11. Quality gate trong CI

Một pipeline tối thiểu cho ứng dụng Spring Modulith có thể gồm:

1. **Unit tests**: nhanh, tập trung quy tắc nghiệp vụ thuần Java.
2. **Slice tests**: kiểm tra HTTP adapter, JPA adapter và những tích hợp công nghệ theo lát cắt.
3. **Application module tests**: kiểm tra bean wiring, use case và dữ liệu/event trong phạm vi module.
4. **Architecture verification**: `ApplicationModules.verify()` để chặn phụ thuộc module không hợp lệ.
5. **Integration tests cần hạ tầng**: kiểm tra database production-compatible, after-commit listener, broker và những luồng nhiều module quan trọng.

Có thể chạy chung các test JUnit qua Gradle `test` hoặc Maven `test`, tùy cách tổ chức suite. Nếu tách thành nhiều task/job theo tốc độ và hạ tầng, phải đưa các job bắt buộc vào điều kiện merge. Đừng để architecture test hoặc event test bị bỏ sót khi đổi cách chia suite.

**Các tiêu chí hữu ích của quality gate:** mọi test bắt buộc xanh; thông báo thất bại chỉ ra module và hành vi bị phá; thời gian phản hồi phù hợp để chạy trên pull request; môi trường test có thể tái lập; không phụ thuộc dịch vụ cá nhân hoặc tài nguyên ngoài không kiểm soát.

Một module test đáng tin cậy có thể phát hiện lỗi hồi quy như: quên đăng ký `@Service`, wiring repository sai, transaction không hoạt động như dự kiến, mapper trả sai field, event thiếu payload hoặc method không còn lưu dữ liệu đúng. Nhưng nó không thay cho giám sát production, test tải và kiểm thử toàn bộ giao tiếp liên module.

## 12. Bài thực hành

### Bài A — Mở rộng hành vi của module

Thêm `cancelOrder(long id)` vào `OrderManagement` và định nghĩa sự kiện `OrderCancelled`. Viết module test cho các tình huống:

- Hủy một đơn tồn tại làm trạng thái thay đổi và đọc lại qua API thấy kết quả.
- Hủy đơn không tồn tại dẫn đến phản hồi/ngoại lệ theo hợp đồng đã đặt.
- Hủy thành công publish đúng một `OrderCancelled` với ID tương ứng.
- Đầu vào bất hợp lệ không tạo event và không tạo thay đổi persistent ngoài dự kiến.

### Bài B — Chọn chế độ bootstrap

Giả sử `orders` cần gọi `inventory` để giữ hàng. Hãy giải thích:

- Khi nào giữ `STANDALONE` và mock một port kiểm tra tồn kho?
- Khi nào dùng `DIRECT_DEPENDENCIES` để có module `inventory` thật?
- Nếu `inventory` lại phụ thuộc `catalog`, khi nào `ALL_DEPENDENCIES` thực sự cần thiết?
- Một listener `notification` nhận `OrderPlaced` có được tự động nạp khi test `orders` ở `DIRECT_DEPENDENCIES` không, và tại sao?

### Bài C — Chẩn đoán bài kiểm thử

Cho tình huống sau: bài module test ghi đơn thành công, `PublishedEvents` ghi nhận `OrderPlaced`, nhưng email xác nhận không được gửi trong production. Hãy chỉ ra những thông tin cần thu thập (module listener, transaction commit, cơ chế asynchronous/retry, cấu hình adapter email, publication registry nếu có) và đề xuất test consumer/integration phù hợp.

### Bài D — Kiểm tra kiến trúc

Viết `ArchitectureVerificationTest` gọi `ApplicationModules.of(ShopApplication.class).verify()`. Tạm thời tạo một import trái phép từ module `notification` tới class ở `orders.internal` trong nhánh thực hành, xác nhận kiến trúc test thất bại, rồi khôi phục bằng API hoặc event công khai phù hợp.

### Tiêu chí tự đánh giá

Bạn đạt yêu cầu khi có thể chứng minh bốn điều **riêng biệt**: (1) module service thực sự được Spring lắp ráp, (2) dữ liệu có thể ghi/đọc qua port của module, (3) sự kiện được publish đúng payload, (4) cấu trúc module tuân thủ ranh giới phụ thuộc. Sau đó giải thích được tại sao chưa thể suy ra listener liên module hay một integration production đã thành công chỉ từ kết quả module test.

## 13. Ghi nhớ

`@ApplicationModuleTest` giúp kiểm tra một application module Spring Modulith như một đơn vị vận hành: **API, bean wiring, transaction, persistence và event publication** trong một Spring context có phạm vi rõ ràng. Khởi đầu với `STANDALONE`, chỉ mở rộng dependency khi tình huống thực sự yêu cầu. Dùng `PublishedEvents` để kiểm tra việc publish và test consumer/after-commit riêng khi cần bảo đảm phản ứng bất đồng bộ.

Để đạt mục tiêu **kiểm chứng ranh giới kiến trúc và ngăn hồi quy trong CI**, hãy kết hợp module test với `ApplicationModules.verify()`, unit/slice test và những integration test hạ tầng cần thiết. Một bài module test xanh là bằng chứng mạnh cho **hành vi đã kiểm thử trong phạm vi module**, nhưng không tự chứng minh mọi phụ thuộc và tương tác liên module đều hợp lệ.
