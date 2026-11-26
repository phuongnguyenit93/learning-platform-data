# Integration test giữa nhiều module

> **Chương:** Test types  
> **Phạm vi đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING` — kiểm chứng ranh giới kiến trúc Spring Modulith, quan hệ phụ thuộc, hành vi sự kiện, database và quality gate CI.  
> **Trọng tâm bài học:** Kiểm tra **một luồng nghiệp vụ đi qua ít nhất hai application module** bằng các bean thực, transaction và event; phân biệt rõ bằng chứng của integration test với kiểm chứng cấu trúc bằng `ApplicationModules.verify()`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định khi nào một hành vi cần **integration test liên module**, thay vì chỉ unit test, slice test hoặc `@ApplicationModuleTest` cho một module.
2. Thiết kế test đi qua API công khai của module phát sự kiện và API của module nhận sự kiện.
3. Kiểm chứng luồng **ghi dữ liệu → commit transaction → giao sự kiện → xử lý ở module nhận → quan sát kết quả**.
4. Viết test có điều kiện chờ hữu hạn cho listener bất đồng bộ, không dựa vào `Thread.sleep(...)`.
5. Chọn phạm vi context giữa `@ApplicationModuleTest` và `@SpringBootTest` theo hướng phụ thuộc module.
6. Cô lập dữ liệu test, nhận diện sự khác biệt giữa H2 và database production, và đưa các test phù hợp vào quality gate CI.
7. Giải thích vì sao integration test xanh vẫn chưa thay thế được `ApplicationModules.verify()`.

**Bối cảnh:** Spring Modulith chia ứng dụng Spring Boot thành các application module với API và phụ thuộc có hướng. Một module có thể hoạt động đúng khi kiểm thử riêng nhưng thất bại khi giao tiếp với module khác do sự kiện bị xử lý sai, transaction chưa commit, listener không được đăng ký, payload không tương thích hoặc cấu hình persistence không phù hợp.

## 2. Khi nào cần integration test giữa nhiều module?

Xét một ứng dụng bán hàng có hai module:

- `orders`: nhận yêu cầu tạo đơn, lưu đơn và phát sự kiện `OrderPlaced`.
- `fulfillment`: nhận `OrderPlaced` và tạo một công việc chuẩn bị hàng.

Luồng cần chứng minh:

~~~mermaid
sequenceDiagram
    participant Test as Integration test
    participant Orders as orders API
    participant DB as Database
    participant Event as Spring event infrastructure
    participant Fulfillment as fulfillment listener
    participant Query as fulfillment API

    Test->>Orders: placeOrder(customerId, amount)
    Orders->>DB: INSERT order
    Orders->>Event: publish OrderPlaced
    Orders-->>Test: orderId
    Note over Orders,Event: Transaction của orders commit
    Event-->>Fulfillment: giao event sau commit
    Fulfillment->>DB: INSERT fulfillment_task
    Test->>Query: hasTask(orderId)
    Query->>DB: SELECT task
    Query-->>Test: true
~~~

Một **unit test** của `OrderService` có thể xác nhận phương thức gọi event publisher. Một **module test** của `orders` với `PublishedEvents` có thể xác nhận event được phát với payload đúng. Nhưng cả hai chưa chứng minh bean listener của `fulfillment` có mặt trong Spring context, có nhận event sau commit, có lưu dữ liệu và cho phép đọc lại kết quả.

Integration test liên module cần quan sát **đầu ra cuối luồng**, ví dụ việc xuất hiện của `fulfillment_task` tương ứng với `orderId` được trả về từ API `orders`.

### Phân biệt các lớp kiểm thử

| Loại test | Câu hỏi được trả lời | Phạm vi Spring |
| --- | --- | --- |
| Unit test thuần Java | Quy tắc và quyết định nghiệp vụ có đúng? | Không cần context |
| Slice test | HTTP/JPA/JSON adapter tuân thủ hợp đồng kỹ thuật? | Context cho một slice |
| `@ApplicationModuleTest` | Các bean trong module và dependency được chọn có phối hợp đúng? | Một module và các dependency theo mode |
| Integration test liên module | Hành vi đi xuyên nhiều module có tạo ra kết quả thực sự đúng? | Các module liên quan, transaction, event, hạ tầng test |
| `ApplicationModules.verify()` | Quan hệ phụ thuộc và các ranh giới API module có hợp lệ? | Kiểm tra mô hình kiến trúc |
| End-to-end test | Luồng từ đầu vào hệ thống đến kết quả cuối cùng hoạt động theo hợp đồng? | Có thể bao gồm HTTP server, broker và dịch vụ ngoài |

Integration test liên module **không bắt buộc** mở HTTP server hoặc dùng tất cả dịch vụ production. Hãy chọn cách nhỏ nhất nhưng đủ trung thực để chứng minh luồng đang kiểm tra.

## 3. Thiết kế ranh giới module cho ví dụ

Giả sử package ứng dụng gốc là `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/                                # module orders
│   ├── OrderManagement.java              # API công khai
│   ├── OrderPlaced.java                  # event công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/                           # module fulfillment
    ├── FulfillmentQueries.java           # API công khai
    └── internal/
        ├── OrderFulfillmentListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTaskEntity.java
            └── FulfillmentTaskRepository.java
~~~

Theo mô hình module mặc định của Spring Modulith, package con trực tiếp dưới application root thường là application module. Các class nằm ở root package của module là API mặc định; package `internal` chứa implementation mà module khác không được tùy tiện tham chiếu.

~~~mermaid
flowchart LR
    A["orders<br/>OrderManagement"] --> E["OrderPlaced<br/>API event"]
    E --> L["fulfillment<br/>OrderFulfillmentListener"]
    L --> F["fulfillment<br/>FulfillmentTaskRepository"]
    L -. "sự kiện là phụ thuộc<br/>về kiểu từ fulfillment<br/>sang orders API" .-> A
~~~

Quan hệ phụ thuộc **theo mã nguồn** ở ví dụ là `fulfillment → orders`, vì listener của `fulfillment` tham chiếu kiểu `orders.OrderPlaced`. Luồng dữ liệu khi chạy bắt đầu từ `orders` và kết thúc ở `fulfillment`, nhưng việc phát event **không yêu cầu** `orders` import class nội bộ của `fulfillment`.

Đây là khác biệt quan trọng khi quyết định phạm vi test: nếu chỉ bootstrap `orders`, listener của `fulfillment` thường **không xuất hiện** trong context.

### Quy tắc API cần giữ

- Module `fulfillment` chỉ dùng kiểu sự kiện `orders.OrderPlaced` đã công bố.
- Test liên module gọi `OrderManagement` và `FulfillmentQueries` thay vì đọc trực tiếp repository nội bộ của hai module.
- Các JPA entity và repository không trở thành DTO công khai của module.
- Kiểm chứng những phụ thuộc không hợp lệ bằng `ApplicationModules.verify()` trong một bài kiểm thử riêng.

## 4. Mã ứng dụng mẫu: hai module kết nối bằng event

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data JPA, Spring Modulith tương thích và một database kiểm thử. Các ví dụ sau là những file nguồn **minh họa**, không phải mã đã ghi vào repository hiện tại.

### 4.1. Bootstrap ứng dụng

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

`@EnableAsync` bật hạ tầng cho các listener bất đồng bộ trong ví dụ. Khi dùng `@ApplicationModuleListener`, cần hiểu rõ semantics của phiên bản Spring Modulith đang sử dụng: annotation này hỗ trợ xử lý sự kiện theo transaction, thường với thực thi bất đồng bộ và transaction riêng. Hãy kiểm tra cấu hình executor, transaction manager và registry sự kiện của ứng dụng khi triển khai thật.

### 4.2. API của module orders

**`src/main/java/com/example/shop/orders/OrderManagement.java`**

~~~java
package com.example.shop.orders;

import java.math.BigDecimal;

public interface OrderManagement {
    long placeOrder(String customerId, BigDecimal amount);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

public record OrderPlaced(long orderId, String customerId) {}
~~~

`OrderPlaced` là một **integration event nội bộ của ứng dụng Modulith**: module consumer được phép phụ thuộc vào kiểu sự kiện thuộc API `orders`. Payload chỉ mang dữ liệu cần thiết cho bên nhận; không đưa JPA entity hay cấu trúc persistence riêng tư ra ngoài.

### 4.3. JPA của orders

**`src/main/java/com/example/shop/orders/internal/persistence/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String customerId;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal amount;

    protected OrderEntity() {}

    public OrderEntity(String customerId, BigDecimal amount) {
        this.customerId = customerId;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
~~~

Các kiểu này là `public` để thuận lợi cho framework và class trong package nội bộ của cùng module sử dụng, nhưng **không phải API được phép tham chiếu từ module khác**.

### 4.4. Application service phát event trong transaction

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderManagement;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.internal.persistence.OrderEntity;
import com.example.shop.orders.internal.persistence.OrderRepository;

@Service
class OrderApplicationService implements OrderManagement {

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
    public long placeOrder(String customerId, BigDecimal amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        var saved = orders.saveAndFlush(
                new OrderEntity(customerId, amount));

        long id = saved.getId();
        events.publishEvent(new OrderPlaced(id, customerId));
        return id;
    }
}
~~~

`@Transactional` mở transaction khi phương thức được gọi qua Spring proxy. `saveAndFlush(...)` bảo đảm entity đã được đồng bộ với database trong transaction hiện tại, nhưng **flush không đồng nghĩa commit**. Transaction chỉ được coi là commit thành công khi lời gọi kết thúc và transaction manager hoàn tất commit.

Event được publish trong transaction. Với listener chạy sau commit, listener chỉ nên bắt đầu hành vi nghiệp vụ tiếp theo khi transaction tạo đơn đã commit; điều này giúp tránh module consumer xử lý dữ liệu từ một giao dịch cuối cùng bị rollback.

### 4.5. API của module fulfillment

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

public interface FulfillmentQueries {
    boolean hasTask(long orderId);
}
~~~

Test sẽ quan sát kết quả qua **API của consumer** này; nó không cần import `FulfillmentTaskRepository`.

### 4.6. Persistence của fulfillment

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTaskEntity.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "fulfillment_tasks")
public class FulfillmentTaskEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private Long orderId;

    protected FulfillmentTaskEntity() {}

    public FulfillmentTaskEntity(long orderId) {
        this.orderId = orderId;
    }

    public Long getOrderId() {
        return orderId;
    }
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTaskRepository.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface FulfillmentTaskRepository
        extends JpaRepository<FulfillmentTaskEntity, Long> {

    boolean existsByOrderId(long orderId);
}
~~~

Trường `orderId` có unique constraint nhằm chống tạo nhiều task cho một đơn ở cấp database. Trong production, vẫn phải thiết kế xử lý **event trùng lặp và cạnh tranh đồng thời**: thao tác kiểm tra rồi tạo bản ghi không tự nó bảo đảm idempotency khi hai listener xử lý đồng thời.

### 4.7. Listener và query service của fulfillment

**`src/main/java/com/example/shop/fulfillment/internal/OrderFulfillmentListener.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskEntity;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Component
class OrderFulfillmentListener {

    private final FulfillmentTaskRepository tasks;

    OrderFulfillmentListener(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!tasks.existsByOrderId(event.orderId())) {
            tasks.save(new FulfillmentTaskEntity(event.orderId()));
        }
    }
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/FulfillmentQueryService.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository tasks;

    FulfillmentQueryService(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Override
    @Transactional(readOnly = true)
    public boolean hasTask(long orderId) {
        return tasks.existsByOrderId(orderId);
    }
}
~~~

**Điểm tích hợp cốt lõi:** `orders` chỉ publish `OrderPlaced`, còn `fulfillment` tự đăng ký listener và quản lý dữ liệu riêng. Với `@ApplicationModuleListener`, ứng dụng có thể xử lý sự kiện bất đồng bộ sau commit trong transaction riêng, tùy phiên bản/cấu hình. Vì vậy integration test **không nên giả định task đã tồn tại ngay tại thời điểm `placeOrder(...)` trả về**.

Lưu ý về tính tin cậy: `@ApplicationModuleListener` giúp khai báo hành vi nhận event; mức độ lưu trữ, replay và retry của event publication còn phụ thuộc vào event publication registry và adapter bền vững đã cấu hình. Không nên coi việc publish thành công là bằng chứng rằng sự kiện sẽ được giao bền vững qua mọi lần restart.

## 5. Viết integration test cho luồng orders → fulfillment

### 5.1. Cấu hình phụ thuộc kiểm thử

Trong dự án dùng Gradle Kotlin DSL cùng bộ quản lý phiên bản Spring Boot/Spring Modulith tương thích, dependency minh họa là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testRuntimeOnly("com.h2database:h2")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` thường bao gồm JUnit Jupiter, AssertJ và Awaitility trong các phiên bản Spring Boot phổ biến. Nếu cấu hình dự án loại trừ Awaitility, thêm dependency tương ứng. Không khai báo phiên bản thư viện tùy tiện nếu BOM của dự án đã quản lý.

Ví dụ dùng H2 trong bộ nhớ để làm rõ cơ chế; khi cần kiểm tra SQL dialect hoặc migration production, xem mục 7 về Testcontainers.

### 5.2. Test khởi tạo đủ hai module

Đặt test ở package ứng dụng gốc để kiểm tra luồng tích hợp toàn context. Ví dụ dưới đây **không** khởi động HTTP server, vì mục tiêu là sự phối hợp của Spring beans, event infrastructure và database.

**`src/test/java/com/example/shop/OrdersFulfillmentIntegrationTest.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import com.example.shop.orders.OrderManagement;
import com.example.shop.fulfillment.FulfillmentQueries;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:cross_module_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrdersFulfillmentIntegrationTest {

    @Autowired
    OrderManagement orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void creates_fulfillment_task_after_order_is_committed() {
        String customerId = "CUS-" + UUID.randomUUID();

        long orderId = orders.placeOrder(
                customerId, new BigDecimal("125.00"));

        assertThat(orderId).isPositive();

        await()
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertThat(fulfillment.hasTask(orderId)).isTrue());
    }

    @Test
    void rejects_invalid_amount_without_creating_order() {
        assertThatThrownBy(() -> orders.placeOrder(
                "CUS-INVALID", BigDecimal.ZERO))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("amount must be positive");
    }
}
~~~

**Giải thích bài test đầu tiên:**

1. `@SpringBootTest` nạp các module trong Spring Boot application context, bao gồm producer `orders` và consumer `fulfillment`.
2. `orders.placeOrder(...)` đi qua Spring proxy, lưu dữ liệu bằng JPA, publish event và hoàn tất transaction.
3. Event infrastructure giao event cho listener của `fulfillment` theo semantics đã cấu hình.
4. Listener tạo task trong database của test.
5. `FulfillmentQueries.hasTask(orderId)` đọc kết quả từ module consumer.
6. Awaitility lặp assertion cho tới khi thành công hoặc hết 10 giây. Nếu listener không chạy, mapping event sai hoặc ghi dữ liệu thất bại, test sẽ thất bại với thông tin assertion/timeout.

Thời hạn 10 giây **chỉ là ngưỡng minh họa**, cần được chọn theo độ ổn định và thời gian chạy thực tế của môi trường CI. Đừng tăng timeout vô hạn để che lỗi. Nếu test thường xuyên đạt ngưỡng này, hãy xem lại thread pool, transaction, database contention và log event.

**Vì sao không dùng `Thread.sleep(1000)`?** Một giây có thể quá ngắn trên CI đang tải và quá dài trên máy chạy nhanh. `await().untilAsserted(...)` quan sát điều kiện hoàn tất thực tế và thất bại có kiểm soát khi không đạt.

**Vì sao không gắn `@Transactional` lên lớp test?** Test có thể mở transaction bao quanh lời gọi `placeOrder`, sau đó rollback khi kết thúc. Khi ấy listener nhận sự kiện *sau commit* không có cơ hội chạy như luồng thật. Test trên không gắn `@Transactional` nên transaction do service quản lý có thể commit.

### 5.3. Cách đánh giá ca lỗi

Test thứ hai chỉ chứng minh rằng dữ liệu đầu vào không hợp lệ bị từ chối. Nó **chưa chứng minh đầy đủ** không có sự kiện nào được publish hoặc không có bản ghi trung gian phát sinh. Để kiểm tra rollback sau khi đã ghi dữ liệu, thiết kế một use case có lỗi **sau thao tác ghi**, rồi kiểm tra cả database producer và side effect của consumer theo đúng chính sách transaction. Không cố tình sửa production logic chỉ để test một tình huống không có trong hợp đồng.

Nếu cần assert **không có task** sau một giao dịch bị rollback trong khi xử lý bất đồng bộ, test phải có chiến lược quan sát hợp lý: kiểm tra trạng thái transaction/DB, đánh giá xem event có được phát/giao khi rollback, hoặc chờ hữu hạn một điều kiện âm được thiết kế có chủ đích. Chỉ assert `false` ngay lập tức không chứng minh rằng event sẽ không đến sau đó.

## 6. Khi nào dùng @ApplicationModuleTest thay vì @SpringBootTest?

`@ApplicationModuleTest` là lựa chọn tốt khi luồng thử nghiệm nằm trong **một module và các dependency cùng chiều** của nó.

~~~java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

// Đặt test trong package của module fulfillment:
// package com.example.shop.fulfillment;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class FulfillmentWithOrdersTest {
    // Module fulfillment và những module nó phụ thuộc trực tiếp
}
~~~

Trích đoạn trên minh họa vị trí package và cấu hình, không thay thế bài test hoàn chỉnh ở mục 5. Trong ví dụ này, `fulfillment` phụ thuộc trực tiếp vào `orders` thông qua `OrderPlaced`, nên **test đặt trong package fulfillment** với `DIRECT_DEPENDENCIES` có thể là lựa chọn hợp lý để kiểm tra hai module cùng lúc, nếu cấu hình và các bean cần thiết thực sự thuộc phạm vi bootstrap.

### Ba bootstrap mode cần hiểu đúng

| Mode | Phạm vi mặc định theo chiều phụ thuộc | Tác động |
| --- | --- | --- |
| `STANDALONE` | Module đặt test | Nhanh, phù hợp test một module |
| `DIRECT_DEPENDENCIES` | Module đặt test và module nó phụ thuộc trực tiếp | Có thể kiểm tra tương tác với dependency trực tiếp |
| `ALL_DEPENDENCIES` | Module đặt test và chuỗi dependency bắc cầu | Context lớn hơn, dùng khi hợp đồng cần nhiều dependency |

**Điểm dễ nhầm:** `DIRECT_DEPENDENCIES` không nạp toàn bộ module *đang phụ thuộc vào* module của test. Nếu đặt test trong `orders` và chạy `STANDALONE` hoặc `DIRECT_DEPENDENCIES`, module `fulfillment` (consumer phụ thuộc `orders`) sẽ không được thêm chỉ vì có listener đối với `OrderPlaced`.

Dùng `@SpringBootTest` khi mục tiêu là đường đi liên module tương đối đầy đủ, hoặc khi việc xác định cây dependency riêng không phản ánh đúng phạm vi runtime cần kiểm chứng. Dùng module test khi muốn giữ context nhỏ nhưng vẫn bao gồm chính xác các module tham gia vào hành vi.

### So sánh sự kiện được publish và side effect được xử lý

| Assertion | Cần có trong test | Ý nghĩa |
| --- | --- | --- |
| `PublishedEvents.ofType(OrderPlaced.class)` trong module test publisher | Test Modulith được cấu hình hỗ trợ `PublishedEvents` | Producer đã publish event |
| `fulfillment.hasTask(orderId) == true` trong integration test | Producer, consumer, event dispatch, persistence và query bean | Sự kiện đã dẫn đến kết quả quan sát được ở consumer |
| Trạng thái publication registry là completed/retried | Registry + adapter persistence cụ thể | Cơ chế quản lý giao nhận sự kiện đã xử lý theo hợp đồng registry |
| Không có vi phạm module boundary | `ApplicationModules.verify()` | Cấu trúc phụ thuộc hợp lệ theo quy tắc kiến trúc |

Một assertion không tự suy ra các hàng khác.

## 7. Kiểm thử database và hạ tầng thật

H2 phù hợp với ví dụ gọn. Tuy nhiên, khi ứng dụng thật dùng PostgreSQL, MySQL hoặc một database khác, integration test cần kiểm tra các điểm mà H2 không đại diện được: loại dữ liệu, schema migration, unique constraint, transaction isolation, lock, native SQL và index.

### 7.1. Dùng Testcontainers với database tương thích production

Với Spring Boot hỗ trợ `@ServiceConnection`, có thể cấu hình PostgreSQL container trong test bằng đoạn minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrdersFulfillmentPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void integration_flow_uses_production_like_database() {
        // Gọi API orders và chờ side effect tại fulfillment,
        // tương tự bài test mục 5.
    }
}
~~~

Để chạy ví dụ này, thường cần `spring-boot-testcontainers`, `org.testcontainers:postgresql`, `org.testcontainers:junit-jupiter` và driver PostgreSQL. Phiên bản container và thư viện cần khớp với chính sách của dự án, đồng thời môi trường CI phải hỗ trợ container runtime. Đây là **khung cấu hình**, phần test thực tế vẫn cần khai báo/inject các API module và các assertion giống bài ở mục 5.

Khi đã dùng service connection, không nên giữ URL H2 cố định từ bài test trước, vì nó có thể ghi đè datasource dự kiến. Hãy để datasource của test trỏ đúng container đang chạy.

### 7.2. Migration và transaction

- Nếu production dùng Flyway/Liquibase, integration test nên thực thi migration tương đương thay vì chỉ tin `hibernate.ddl-auto=create-drop`.
- Với sự kiện xử lý sau commit, test nên quan sát **kết quả sau một lần commit thật**.
- Nếu có race condition, unique constraint là lớp bảo vệ, nhưng cần chính sách idempotency, retry và xử lý xung đột rõ ràng.
- Nếu module consumer lưu dữ liệu vào database khác hoặc gọi external service, thay test infrastructure để kiểm tra điểm tích hợp cụ thể; không được mặc định transactional rollback sẽ bao phủ cả dịch vụ ngoài.
- Test phải tự tạo dữ liệu của mình, tránh phụ thuộc seed data hoặc thứ tự test chạy.

**Cảnh báo phạm vi:** Việc dùng Testcontainers với database giống production tăng độ tin cậy cho persistence, nhưng không mặc nhiên mô phỏng đầy đủ mạng, phân quyền, tài nguyên và sự cố production.

## 8. Xác minh giao nhận event, retry và idempotency

Integration test happy path không đủ cho hệ thống có event bất đồng bộ và yêu cầu độ tin cậy cao. Cần phân biệt ba trách nhiệm:

1. **Event publication:** producer phát payload đúng sau hành vi nghiệp vụ.
2. **Event delivery/consumption:** consumer thực sự được đăng ký và nhận event, sau đó ghi side effect.
3. **Event reliability:** lỗi tạm thời, retry, duplicate delivery và restart được xử lý theo hợp đồng.

### 8.1. Kiểm tra payload và contract

Ví dụ `OrderPlaced(orderId, customerId)` có thể được consumer dùng để tạo task. Nếu producer đổi tên event, package API, kiểu trường hoặc nội dung payload mà không cập nhật consumer, test liên module phải phát hiện bằng hành vi quan sát được hoặc biên dịch thất bại ở thời điểm build.

Mọi DTO/event công khai nên có hợp đồng rõ: trường bắt buộc, versioning khi cần và chính sách chuyển đổi khi phát triển hệ thống.

### 8.2. Idempotency

Hạ tầng sự kiện thường có tình huống xử lý lại. Nếu listener tạo một bản ghi mới mỗi lần nhận cùng event, có thể có hai task cho một đơn.

Trong ví dụ, `FulfillmentTaskEntity.orderId` được ràng buộc unique và listener kiểm tra tồn tại trước khi lưu. Điều này **chưa đủ** để ngăn race condition khi hai listener chạy song song:

~~~text
Listener A: existsByOrderId(id) -> false
Listener B: existsByOrderId(id) -> false
Listener A: INSERT task
Listener B: INSERT task -> unique violation
~~~

Một triển khai production thường cần thao tác idempotent tại database (upsert hoặc xử lý lỗi duplicate đúng cách), định danh event, và cơ chế retry không gây side effect trùng lặp. Test bổ sung nên phát cùng event hai lần và xác nhận chỉ có **một** task cuối cùng, đồng thời kiểm tra cách xử lý khi có nhiều consumer đồng thời.

### 8.3. Failures và retry

Nếu `OrderFulfillmentListener` gặp lỗi database hoặc dịch vụ ngoài, cần xác định:

- Sự kiện có được ghi nhận trong publication registry bền vững không?
- Lỗi có được lưu lại đủ để retry/replay không?
- Có giới hạn retry, dead-letter strategy hoặc cảnh báo vận hành không?
- Việc xử lý lại có tạo side effect trùng không?
- Transaction của listener có rollback đúng khi thất bại không?

Spring Modulith cung cấp các cơ chế hỗ trợ quản lý event publication; **khả năng lưu bền và replay phụ thuộc adapter registry đã cấu hình**. Để xác minh retry/replay, cần chạy test với chính adapter bền vững và scenario lỗi phù hợp. Test in-memory chỉ quan sát event trong một JVM chưa chứng minh cơ chế sống sót qua restart.

## 9. Kiểm chứng kiến trúc giữa module

Kiểm thử tích hợp có thể chạy xanh dù source code chứa phụ thuộc trái quy tắc. Ví dụ developer cho `fulfillment` import trực tiếp:

~~~java
// Ví dụ phụ thuộc sai qua package nội bộ của module orders:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Khi compiler cho phép class `public`, import này vẫn có thể biên dịch. Nhưng theo mô hình module, `orders.internal.persistence` không thuộc public API của `orders`.

Bài kiểm tra kiến trúc riêng:

**`src/test/java/com/example/shop/ArchitectureVerificationTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTest {

    @Test
    void modules_obey_dependencies_and_api_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là bằng chứng độc lập cho ranh giới kiến trúc của ứng dụng Spring Modulith: phụ thuộc giữa module, khả năng truy cập API và các quy tắc được mô hình Modulith hỗ trợ. Trong một kiến trúc có giới hạn dependency cụ thể, có thể mô tả chúng bằng `@ApplicationModule(allowedDependencies = ...)` hoặc named interfaces theo quy định dự án.

**Hợp lệ:** `fulfillment` tham chiếu `orders.OrderPlaced` tại API công khai.  
**Không hợp lệ:** `fulfillment` phụ thuộc trực tiếp `orders.internal.persistence.OrderEntity`.

Integration test giúp xác minh **hành vi**; `verify()` giúp xác minh **cấu trúc**. Cần cả hai để ngăn lỗi hồi quy và phát hiện module boundary bị phá.

## 10. Các lỗi hay gặp trong multi-module integration test

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Test producer xanh nhưng không tạo task | Consumer module chưa được bootstrap, listener không có trong context | Xem package test, bootstrap mode, danh sách bean/listener |
| Test nhận event nhưng side effect chưa xuất hiện ngay | Listener bất đồng bộ | Dùng Awaitility với điều kiện quan sát được |
| Listener không chạy ở pha `AFTER_COMMIT` | Test bao transaction rollback; producer chưa commit | Bỏ `@Transactional` trên test khi cần kiểm tra sau commit; xem log transaction |
| Test thất bại ngẫu nhiên trên CI | Timing, thread pool, database contention, shared fixture | Cô lập dữ liệu và quan sát điều kiện, kiểm tra executor |
| Hai task cho cùng một đơn | Event duplicate hoặc race condition | Ràng buộc unique, idempotency và test replay |
| H2 chạy xanh nhưng PostgreSQL lỗi | SQL dialect/migration/constraint khác nhau | Dùng Testcontainers cùng loại database |
| Test đơn lẻ xanh nhưng `verify()` đỏ | Có dependency module sai | Sửa import và public API; không bỏ architecture gate |
| Test bị thiếu bean sau khi chuyển sang module test | Dependency nằm ngoài phạm vi bootstrap | Chọn mode theo dependency hoặc dùng `@SpringBootTest` |
| Test quá chậm và dễ vỡ | Khởi động hạ tầng không liên quan đến hợp đồng | Thu gọn module context hoặc tách test nhanh/chậm |
| Test xanh nhưng retry không hoạt động | Chỉ kiểm tra happy path, registry chưa cấu hình | Bổ sung integration test cho failure/replay với adapter thật |

**Đừng xử lý tất cả lỗi thiếu bean bằng cách chuyển sang `@SpringBootTest` ngay.** Hãy kiểm tra dependency có đúng thiết kế module không, rồi quyết định test cần bao nhiêu module và hạ tầng để chứng minh hành vi.

## 11. Thiết kế bộ test và quality gate CI

Một bộ kiểm thử Spring Modulith thường gồm nhiều lớp, với chi phí thực thi khác nhau:

| Lớp | Trọng tâm | Chu kỳ phù hợp |
| --- | --- | --- |
| Unit test | Logic domain | Mỗi lần build/PR |
| Slice test | Adapter web/JPA/JSON | Mỗi lần build/PR |
| `@ApplicationModuleTest` | Hành vi và wiring một module | Mỗi PR |
| Architecture verification | Ranh giới/chiều phụ thuộc | Mỗi PR, phải bắt buộc |
| Integration test liên module | Event sau commit, dữ liệu giữa các module | Mỗi PR cho luồng trọng yếu; suite lớn có thể chia job |
| Integration hạ tầng production-like | SQL dialect, broker, retry/replay | CI có container, trước merge/deploy theo mức rủi ro |

Điểm cốt lõi của quality gate không phải số lượng bài test mà là **ngăn đúng loại lỗi**:

- Lỗi tính toán và validation: unit test.
- Lỗi HTTP/JPA adapter: slice test.
- Lỗi module bean wiring và use case nội bộ: application module test.
- Lỗi giao tiếp event và side effect giữa module: integration test liên module.
- Lỗi dependency trái quy tắc: architecture verification.
- Lỗi transaction/dialect/broker ngoài môi trường giả: integration test với hạ tầng phù hợp.

### Ví dụ tổ chức pipeline

~~~mermaid
flowchart LR
    PR["Commit / Pull request"] --> U["Unit & slice tests"]
    U --> A["Architecture verification"]
    A --> M["Module tests"]
    M --> I["Cross-module integration tests"]
    I --> Q{"Tất cả gate<br/>bắt buộc xanh?"}
    Q -- "Có" --> OK["Cho phép merge"]
    Q -- "Không" --> FIX["Sửa và chạy lại"]
~~~

Trong Gradle/Maven, JUnit test có thể chạy bằng `test` và các task/suite được cấu hình riêng. Nếu tách integration test vào job khác, yêu cầu job đó phải thành công trước khi merge theo chính sách của dự án. Không nên để một suite quan trọng bị skip do thay đổi cách đặt tên, tagging hoặc filter test.

**Tính tái lập:** CI cần database test có thể tạo mới, cấu hình executor/timeout rõ ràng, logs đủ để chẩn đoán event và transaction, cũng như môi trường container nếu dùng Testcontainers. Tránh phụ thuộc vào một dịch vụ thủ công đang chạy trên máy cá nhân.

## 12. Bài thực hành

### Bài 1 — Tạo event giữa hai module

Tạo hai module `orders` và `fulfillment` như ví dụ. Hoàn thiện test kiểm tra:

1. Lưu một đơn có amount dương.
2. Đơn được commit.
3. Listener của `fulfillment` nhận `OrderPlaced`.
4. Task được tạo đúng với `orderId`.
5. Kết quả được xác nhận qua `FulfillmentQueries` trong thời hạn hữu hạn.

**Tiêu chí đạt:** Nếu bỏ `@ApplicationModuleListener` hoặc xóa code lưu task, test thất bại có ý nghĩa.

### Bài 2 — So sánh phạm vi bootstrap

Viết hai biến thể:

- Test ở package `orders` với `@ApplicationModuleTest` mặc định, chỉ quan sát việc publish event bằng tiện ích `PublishedEvents` khi được hỗ trợ.
- Test ở package `fulfillment` với `@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)` hoặc test gốc bằng `@SpringBootTest`, kiểm tra side effect cuối cùng.

Giải thích vì sao biến thể thứ nhất không tự chứng minh listener của `fulfillment` đã chạy.

### Bài 3 — Rollback và after-commit

Thiết kế một tình huống nghiệp vụ khiến transaction tạo đơn rollback **sau khi đã cố ghi dữ liệu**. Bổ sung test kiểm tra:

- Không có đơn bị commit.
- Không có task hợp lệ ở `fulfillment`.
- Listener sau commit không xử lý một event thuộc transaction thất bại.

Không dùng assertion trạng thái âm ngay sau phương thức thất bại làm bằng chứng duy nhất cho absence của sự kiện bất đồng bộ.

### Bài 4 — Event duplicate

Phát cùng `OrderPlaced` hai lần với cùng `orderId`. Kiểm tra kết quả chỉ có một task; sau đó thảo luận khả năng hai listener cùng nhận event đồng thời và cách database unique constraint cùng chiến lược xử lý xung đột bảo vệ tính idempotent.

### Bài 5 — Kiểm chứng kiến trúc

Chạy `ApplicationModules.of(ShopApplication.class).verify()`. Tạm tạo một import từ `fulfillment` vào `orders.internal.persistence.OrderEntity` để quan sát lỗi kiến trúc, rồi sửa thiết kế quay về dùng API `orders`.

### Câu hỏi tự đánh giá

- Vì sao `PublishedEvents` chứng minh producer đã publish nhưng chưa chứng minh consumer xử lý xong?
- Vì sao không nên đặt `@Transactional` lên test cần kiểm tra listener sau commit?
- `DIRECT_DEPENDENCIES` có nạp các module *phụ thuộc vào* module của test không?
- Lợi ích và giới hạn của H2, Testcontainers và mock ở mỗi lớp test là gì?
- Nếu integration test xanh nhưng `ApplicationModules.verify()` thất bại, có được merge không theo quality gate đã đề ra?

## 13. Ghi nhớ

**Integration test giữa nhiều module kiểm tra hành vi thực tế của một luồng nghiệp vụ vượt qua ranh giới module.** Với Spring Modulith, một ví dụ có giá trị là `orders` lưu dữ liệu, commit, phát `OrderPlaced`, `fulfillment` xử lý sự kiện và ghi một tác vụ có thể truy vấn qua API công khai. Khi listener bất đồng bộ, hãy chờ bằng điều kiện quan sát được và giới hạn thời gian; không giả định sự kiện được xử lý tức thì.

Hãy chọn `@ApplicationModuleTest` khi một module cùng dependency của nó đủ cho tình huống, và `@SpringBootTest` khi cần các module cùng vận hành trong context tích hợp lớn hơn. Luôn tách **kiểm chứng kiến trúc bằng `ApplicationModules.verify()`** khỏi **kiểm thử hành vi bằng JUnit/Spring Test**, rồi kết hợp cả hai cùng các test transaction, database và event cần thiết trong quality gate CI để ngăn phụ thuộc sai và hồi quy.
