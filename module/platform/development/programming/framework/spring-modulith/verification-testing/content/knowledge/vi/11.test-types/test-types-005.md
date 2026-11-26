# End-to-end test qua entry point ứng dụng

> **Chương:** Test types  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Gửi yêu cầu qua entry point công khai của ứng dụng Spring Modulith, quan sát kết quả ở đầu ra công khai, rồi kết hợp với kiểm chứng ranh giới module và quality gate CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích end-to-end (E2E) test **qua entry point ứng dụng** và phân biệt nó với unit test, slice test, `@ApplicationModuleTest` và integration test giữa module.
2. Khởi động ứng dụng bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và gọi HTTP thật bằng `TestRestTemplate`.
3. Xây dựng một luồng kiểm thử `orders → event → fulfillment`, đi từ HTTP request, qua transaction và database, đến HTTP response của module nhận.
4. Viết assertion cho hành vi **eventual consistency** khi listener chạy bất đồng bộ và chỉ nhận sự kiện sau commit.
5. Dùng Testcontainers để kiểm tra với database gần môi trường triển khai, giữ fixture độc lập và tránh các test chờ cố định bằng `Thread.sleep`.
6. Xác định những điều E2E test **không tự chứng minh**: mọi tình huống nghiệp vụ, độ bền event qua restart, hiệu năng và ranh giới phụ thuộc module.
7. Đưa E2E test, kiểm tra kiến trúc bằng `ApplicationModules.verify()` và các test ở cấp thấp hơn vào quality gate CI phù hợp.

**Định nghĩa trong phạm vi bài:** “E2E qua entry point ứng dụng” nghĩa là test gửi yêu cầu qua một cửa vào công khai (ở đây là REST API) rồi quan sát kết quả qua một cửa ra công khai. Test đi xuyên qua các tầng cần thiết của ứng dụng thay vì gọi thẳng service hoặc repository trong test. Với ứng dụng có giao diện web, một bài browser E2E còn có thể kiểm tra UI; ở đây ta tập trung vào **application/API E2E**, chưa bao gồm trình duyệt và hệ thống bên ngoài không được kết nối.

## 2. Vì sao Spring Modulith cần E2E test?

Spring Modulith giúp tổ chức ứng dụng Spring Boot thành những **application module** có ranh giới và quan hệ phụ thuộc rõ ràng. Các module có thể có unit test và module test xanh nhưng đường đi của một request thực vẫn sai, ví dụ:

- HTTP adapter không validate hoặc chuyển đổi JSON đúng.
- Service được inject sai hoặc thiếu transaction.
- Database migration, constraint hoặc mapping làm luồng lưu thất bại.
- Module phát event đúng nhưng listener của module khác không có trong context.
- Listener chạy bất đồng bộ; client quan sát quá sớm nên nhận trạng thái chưa hoàn tất.
- Endpoint đọc kết quả trả cấu trúc hoặc status HTTP khác hợp đồng đã công bố.

Xét ứng dụng bán hàng:

~~~mermaid
flowchart LR
    C["HTTP client<br/>POST /api/orders"] --> W["orders<br/>OrderController"]
    W --> S["orders<br/>OrderManagement"]
    S --> D[("Orders DB")]
    S --> E["OrderPlaced<br/>event"]
    E --> F["fulfillment<br/>event listener"]
    F --> T[("Fulfillment DB")]
    C --> Q["GET /api/fulfillments/{id}"]
    Q --> T
~~~

Ở góc độ E2E, **đầu vào** là request tạo đơn; **đầu ra mong đợi** là response `201 Created` chứa `orderId`, rồi sau khi event được xử lý, endpoint fulfillment trả trạng thái `READY` của đúng đơn đó.

### Mỗi loại kiểm thử bảo vệ một lớp khác nhau

| Loại test | Cửa vào thường dùng | Điều được chứng minh | Điều còn thiếu |
| --- | --- | --- | --- |
| Unit test | Phương thức Java | Quy tắc, nhánh và bất biến miền nghiệp vụ | Spring wiring, HTTP, database, event |
| Slice test | `MockMvc` hoặc repository trong Spring slice | Web/JPA adapter và cấu hình liên quan | Toàn đường đi nhiều module |
| `@ApplicationModuleTest` | API/bean của module | Bean wiring, use case, persistence, publication trong phạm vi bootstrap | Entry point HTTP thật và các module ngoài phạm vi |
| Integration test liên module | API bean hoặc event của một module | Sự phối hợp producer/consumer và hạ tầng chọn lọc | Chưa chắc đi qua HTTP boundary |
| **Application/API E2E** | **HTTP trên cổng thật** | Routing, deserialization, validation, service, transaction, database, event, response | Chưa chắc bao gồm UI/browser, dịch vụ ngoài hay mọi lỗi production |
| Architecture verification | Mô hình `ApplicationModules` | Các quan hệ phụ thuộc và ranh giới module hợp lệ | Không xác nhận HTTP hay luồng nghiệp vụ chạy đúng |

Điểm khác biệt của bài này nằm ở **cách thực hiện test**: client không inject `OrderManagement` để gọi trực tiếp; nó gọi HTTP giống một consumer của ứng dụng. Các assertion cũng dùng API quan sát, tránh đọc trực tiếp các repository nội bộ.

## 3. Thiết kế tình huống E2E có tiêu chí chấp nhận rõ ràng

Giả sử ứng dụng có hai module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderManagement.java                  # API module
│   ├── OrderPlaced.java                      # event công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── web/OrderController.java          # HTTP entry point
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java              # API đọc kết quả
    └── internal/
        ├── OrderFulfillmentListener.java
        ├── FulfillmentQueryService.java
        ├── web/FulfillmentController.java    # HTTP observation point
        └── persistence/
            ├── FulfillmentTaskEntity.java
            └── FulfillmentTaskRepository.java
~~~

Theo quy ước mặc định của Spring Modulith, `orders` và `fulfillment` là hai application module dưới package ứng dụng gốc. Các class ở package root mỗi module tạo thành API mặc định; lớp nằm trong `internal` là phần cài đặt nội bộ của module đó.

### Hợp đồng hành vi

**Luồng thành công:**

1. Client gửi `POST /api/orders` với `customerId` và `amount > 0`.
2. API trả `201` cùng `orderId` dương.
3. `orders` lưu đơn trong transaction rồi publish `OrderPlaced`.
4. `fulfillment` nhận sự kiện sau commit và tạo task.
5. Client gọi `GET /api/fulfillments/{orderId}`, cuối cùng nhận `200`, đúng `orderId` và `state = READY`.

**Luồng lỗi đầu vào:** `POST /api/orders` với `customerId` rỗng hoặc `amount` không dương trả `400 Bad Request`.

**Cách hiển thị khi xử lý bất đồng bộ:** Trong ví dụ, endpoint fulfillment trả `404` **trước khi task được tạo** và `200` **khi task xuất hiện**. Đây là hợp đồng minh họa; API thực có thể dùng `202 Accepted` và trạng thái `PENDING`. Test phải bám hợp đồng được chọn, không áp đặt một mã HTTP chung cho mọi ứng dụng.

~~~mermaid
sequenceDiagram
    participant Client as E2E HTTP client
    participant HTTP as Orders HTTP
    participant Service as Orders service
    participant DB as Test database
    participant Event as Event infrastructure
    participant Listener as Fulfillment listener
    participant Query as Fulfillment HTTP

    Client->>HTTP: POST /api/orders
    HTTP->>Service: placeOrder(...)
    Service->>DB: lưu đơn
    Service->>Event: publish OrderPlaced
    Note over Service,DB: Transaction commit thành công
    HTTP-->>Client: 201 {"orderId": ...}
    Event-->>Listener: nhận OrderPlaced sau commit
    Listener->>DB: tạo fulfillment task
    loop Poll có giới hạn
        Client->>Query: GET /api/fulfillments/{id}
        Query->>DB: kiểm tra task
        Query-->>Client: 404 trước khi READY / 200 khi READY
    end
~~~

Thứ tự các tín hiệu ở runtime có thể đan xen do scheduler và listener bất đồng bộ. Không viết test phụ thuộc vào việc listener nhất định hoàn tất trước response `201`.

## 4. Các dependency cần cho E2E HTTP + database

Ví dụ áp dụng cho **Spring Boot 3.x có `@ServiceConnection` (từ Boot 3.1+)**, Java 17+ và phiên bản Spring Modulith tương thích do BOM của dự án quản lý. Với Gradle Kotlin DSL, phần dependency minh họa:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.modulith:spring-modulith-starter-core")

    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Những dòng này cần được kết hợp với plugin/BOM của dự án để quản lý phiên bản; chúng không phải một `build.gradle.kts` đầy đủ. Testcontainers cần môi trường có container runtime phù hợp. `@ServiceConnection` tạo cấu hình kết nối datasource từ container, giúp test tránh ghi cứng username, password hoặc cổng PostgreSQL.

`spring-boot-starter-test` cung cấp hạ tầng JUnit, HTTP test client và AssertJ. Ví dụ bên dưới dùng Awaitility để chờ eventual consistency; nếu phiên bản starter đang dùng không cung cấp Awaitility trên test classpath, cần khai báo `testImplementation("org.awaitility:awaitility")` với phiên bản được quản lý phù hợp.

Trong production nên dùng Flyway/Liquibase cho schema. Để ví dụ tự chứa, E2E test bên dưới sử dụng `spring.jpa.hibernate.ddl-auto=create-drop` **chỉ trong test**; không đưa cấu hình này vào production.

## 5. Xây dựng ứng dụng minh họa

### 5.1. Spring Boot entry point

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

`@EnableAsync` bật hạ tầng thực thi bất đồng bộ của ứng dụng. `@ApplicationModuleListener` trong ví dụ sử dụng cơ chế listener của Spring Modulith, thường xử lý event sau commit với transaction riêng và bất đồng bộ. Semantics chính xác, executor, logging và retry phải được xác nhận theo phiên bản cùng cấu hình thực tế.

### 5.2. API công khai của orders

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

public record OrderPlaced(long orderId) {}
~~~

Kiểu `OrderPlaced` thuộc public API của module `orders`, cho phép consumer module phụ thuộc vào payload sự kiện. `orders` không cần import entity hoặc service nội bộ của `fulfillment`.

### 5.3. Lưu dữ liệu bên trong orders

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
}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
~~~

### 5.4. Service thực hiện transaction và publish event

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

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository repository,
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
                new OrderEntity(customerId, amount));

        long id = saved.getId();
        events.publishEvent(new OrderPlaced(id));

        return id;
    }
}
~~~

Event được publish trong transaction của `placeOrder`. Transaction manager hoàn tất commit khi lời gọi service qua Spring proxy kết thúc thành công. Listener sau commit không nên thực thi side effect cho một transaction cuối cùng bị rollback.

### 5.5. HTTP entry point của orders

**`src/main/java/com/example/shop/orders/internal/web/OrderController.java`**

~~~java
package com.example.shop.orders.internal.web;

import java.math.BigDecimal;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.shop.orders.OrderManagement;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderManagement orders;

    OrderController(OrderManagement orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<CreatedOrderResponse> create(
            @Valid @RequestBody PlaceOrderRequest request) {

        long id = orders.placeOrder(
                request.customerId(),
                request.amount());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CreatedOrderResponse(id));
    }

    public record PlaceOrderRequest(
            @NotBlank String customerId,
            @NotNull @DecimalMin("0.01") BigDecimal amount
    ) {}

    public record CreatedOrderResponse(long orderId) {}
}
~~~

Spring MVC thực hiện route `POST /api/orders`, parse JSON, validate `@Valid` và serialize response. Test E2E sẽ đi qua các cơ chế này bằng HTTP thật. Với dữ liệu không hợp lệ, Bean Validation tạo phản hồi lỗi theo cấu hình Spring MVC; test dưới đây chỉ ràng buộc status `400`, chưa giả định định dạng lỗi chi tiết.

## 6. Xây dựng module fulfillment nhận event

### 6.1. API truy vấn từ bên ngoài module

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

public interface FulfillmentQueries {
    boolean hasTask(long orderId);
}
~~~

### 6.2. Entity và repository thuộc sở hữu fulfillment

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

Unique constraint theo `orderId` bảo vệ bất biến “không có hai task cho cùng đơn” ở database. Nhưng phép `existsByOrderId` rồi `save` vẫn có race condition khi xử lý đồng thời; production cần chính sách idempotency và xử lý duplicate phù hợp.

### 6.3. Listener của fulfillment

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

Module `fulfillment` **phụ thuộc vào API `orders.OrderPlaced`**, nhưng `orders` không import hoặc gọi trực tiếp `fulfillment.internal.OrderFulfillmentListener`. Quan hệ phụ thuộc theo mã nguồn là `fulfillment → orders`, trong khi luồng sự kiện runtime bắt đầu từ `orders` và được consumer `fulfillment` xử lý.

### 6.4. API đọc kết quả và HTTP observation point

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

**`src/main/java/com/example/shop/fulfillment/internal/web/FulfillmentController.java`**

~~~java
package com.example.shop.fulfillment.internal.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.shop.fulfillment.FulfillmentQueries;

@RestController
@RequestMapping("/api/fulfillments")
class FulfillmentController {

    private final FulfillmentQueries fulfillment;

    FulfillmentController(FulfillmentQueries fulfillment) {
        this.fulfillment = fulfillment;
    }

    @GetMapping("/{orderId}")
    ResponseEntity<FulfillmentResponse> get(
            @PathVariable("orderId") long orderId) {

        if (!fulfillment.hasTask(orderId)) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(
                new FulfillmentResponse(orderId, "READY"));
    }

    public record FulfillmentResponse(long orderId, String state) {}
}
~~~

Endpoint này là **cửa ra quan sát được** của E2E test. Với trường hợp thực tế đòi hỏi phân biệt đơn không tồn tại và đơn đang xử lý, có thể thiết kế trạng thái `PENDING`, `READY`, `FAILED` và contract HTTP tương ứng; ở đây `404` trước khi tạo task chỉ nhằm giữ ví dụ ngắn gọn.

## 7. E2E test qua HTTP trên cổng ngẫu nhiên

### 7.1. Vì sao dùng RANDOM_PORT và TestRestTemplate?

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` tạo Spring context cho ứng dụng và khởi động HTTP server trên cổng ngẫu nhiên. `TestRestTemplate` gửi request qua network loopback tới server đó, vì vậy test kiểm tra cả HTTP request mapping, Jackson, validation, Spring Security nếu được cấu hình, bean wiring, transaction và phản hồi.

Điểm khác biệt với `MockMvc`: `MockMvc` xử lý request qua môi trường Spring MVC mô phỏng, có thể không chạy HTTP server thật. Nó rất hữu ích cho web slice và integration test của MVC nhưng chưa chứng minh giao tiếp trên cổng mạng. Tình huống E2E bài này chọn **server thật**, nên dùng `RANDOM_PORT`.

### 7.2. Testcontainers PostgreSQL

Đặt test tại `src/test/java/com/example/shop/ShopHttpE2ETest.java`.

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@TestPropertySource(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class ShopHttpE2ETest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    TestRestTemplate http;

    @Test
    void post_order_eventually_creates_fulfillment_task() {
        var body = Map.of(
                "customerId", "CUS-" + UUID.randomUUID(),
                "amount", new BigDecimal("125.00"));

        var created = http.postForEntity(
                "/api/orders", body, JsonNode.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        JsonNode createdJson =
                Objects.requireNonNull(created.getBody());

        assertThat(createdJson.has("orderId")).isTrue();
        long orderId = createdJson.path("orderId").asLong();
        assertThat(orderId).isPositive();

        await()
                .atMost(Duration.ofSeconds(15))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() -> {
                    var result = http.getForEntity(
                            "/api/fulfillments/{id}",
                            JsonNode.class,
                            orderId);

                    assertThat(result.getStatusCode())
                            .isEqualTo(HttpStatus.OK);

                    JsonNode resultJson =
                            Objects.requireNonNull(result.getBody());

                    assertThat(resultJson.path("orderId").asLong())
                            .isEqualTo(orderId);
                    assertThat(resultJson.path("state").asText())
                            .isEqualTo("READY");
                });
    }

    @Test
    void rejects_invalid_http_request() {
        var response = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "", "amount", BigDecimal.ZERO),
                JsonNode.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }
}
~~~

### 7.3. Tại sao đây là E2E qua entry point?

- **Cửa vào thật:** test gửi `POST` HTTP tới ứng dụng đã khởi động trên một cổng.
- **Lớp web thật:** controller được Spring MVC gọi; Jackson parse JSON và Jakarta Validation thực hiện các ràng buộc.
- **Dịch vụ thật:** bean `OrderApplicationService` được inject và thực thi qua proxy transaction.
- **Database thật trong môi trường test:** PostgreSQL container nhận `INSERT`, `SELECT`; JPA entity và mapping được sử dụng.
- **Giao tiếp module thật:** `OrderPlaced` được Spring giao tới listener của `fulfillment` khi cấu hình và transaction phù hợp.
- **Cửa ra thật:** test dùng `GET /api/fulfillments/{id}` để quan sát dữ liệu đã ghi và khớp `orderId`.

Phần quan trọng nhất của assertion là kiểm tra **cùng một ID từ đầu vào đến kết quả cuối luồng**. Nếu chỉ assert một response `200` bất kỳ, test có thể xanh nhờ dữ liệu còn lại từ test khác và bỏ sót lỗi định tuyến sự kiện.

### 7.4. Vì sao không inject repository vào test?

Trực tiếp gọi `OrderRepository` hoặc `FulfillmentTaskRepository` để chuẩn bị, kích hoạt hay kiểm tra chính luồng đang thử sẽ đi vòng qua HTTP/contract của module. Trong bài này, test chỉ inject `TestRestTemplate`; các đường đi tạo và đọc dữ liệu đều qua API.

Trong suite thực tế, có thể cần fixture hoặc API quản trị riêng để seed/reset dữ liệu, nhưng phải mô tả rõ đâu là **bước thiết lập test** và đâu là **hành vi E2E đang được chứng minh**. Không dùng repository nội bộ làm assertion chính nếu mục tiêu là hợp đồng HTTP từ bên ngoài.

## 8. Đồng bộ, transaction và eventual consistency

### 8.1. Event được publish không có nghĩa consumer đã hoàn tất

Ở luồng trên, service publish event trong transaction. `@ApplicationModuleListener` hỗ trợ listener theo kiểu giao dịch và bất đồng bộ; test có thể nhận `201` trước khi listener ghi xong `fulfillment_tasks`. Vì thế:

~~~java
// Không đáng tin nếu listener xử lý bất đồng bộ:
var response = http.getForEntity(
        "/api/fulfillments/{id}", JsonNode.class, orderId);
// assert status 200 ngay lập tức có thể thất bại theo timing.
~~~

Thay vào đó, điều kiện phải phản ánh **trạng thái cuối cùng cần đạt**:

~~~java
await()
        .atMost(Duration.ofSeconds(15))
        .untilAsserted(() -> {
            var response = http.getForEntity(
                    "/api/fulfillments/{id}", JsonNode.class, orderId);
            assertThat(response.getStatusCode())
                    .isEqualTo(HttpStatus.OK);
        });
~~~

`untilAsserted` lặp assertion đến khi thành công hoặc quá hạn. Nó không bắt test đợi đủ 15 giây nếu task được tạo nhanh. Ngưỡng thời gian cần đo và điều chỉnh theo môi trường CI; timeout quá dài che lỗi, timeout quá ngắn gây test không ổn định.

### 8.2. Tránh @Transactional trên lớp E2E test

Trong ví dụ test dùng HTTP client, transaction của lời gọi server được quản lý trong request/service của server. Gắn `@Transactional` lên phương thức client test **không tự bao transaction phía server**, vì request được xử lý trên thread khác. Đừng kỳ vọng annotation này tự rollback mọi thay đổi của E2E test.

Nếu dùng test trực tiếp gọi bean thay vì HTTP, `@Transactional` của test có thể tạo transaction bao ngoài, bị rollback sau test và khiến listener `AFTER_COMMIT` không chạy. Vì vậy cần phân biệt rất rõ transaction phía client test và transaction của luồng server.

### 8.3. Kịch bản thất bại và quan sát trạng thái âm

Một test dạng “vừa gửi request lỗi, gọi ngay endpoint, thấy `404`” **chưa đủ chứng minh không có tác động bất đồng bộ**. Để kiểm tra không tạo side effect khi rollback, cần một tình huống thật sự rollback sau khi bắt đầu thao tác ghi, có cách quan sát event/transaction phù hợp và cửa sổ kiểm thử xác định.

Tình huống `rejects_invalid_http_request()` ở mục 7 chỉ xác nhận lỗi validation được chuyển thành `400`. Nó **không** khẳng định toàn bộ side effect đã được kiểm chứng; muốn có đảm bảo đó phải bổ sung test riêng có dữ liệu/điều kiện quan sát phù hợp.

## 9. Thiết kế E2E test ít nhiễu và có thể tái lập

### 9.1. Dữ liệu test phải có danh tính rõ

Dùng `UUID.randomUUID()` làm phần nhận diện khách trong request, lưu lại `orderId` nhận từ response, rồi chỉ assert task gắn với `orderId` đó. Không dựa vào “ID đầu tiên luôn là 1” hoặc “database luôn rỗng” khi test chạy.

Nếu chạy test song song hoặc tái sử dụng container, cần tách schema, test data hoặc namespace cho từng bài. Đừng dùng `DELETE FROM` tràn lan trên dữ liệu của một nhóm test khác.

### 9.2. Không phụ thuộc thời gian cố định

- Dùng `await().untilAsserted(...)` hoặc cơ chế chờ sự kiện có timeout rõ ràng.
- Đặt `pollInterval` vừa đủ; polling liên tục mỗi mili giây có thể gây tải và che race condition.
- Nếu business logic phụ thuộc thời gian, inject `Clock` để điều khiển trong unit/module test; E2E có thể dùng dữ liệu thời gian cố định hoặc fake clock trong môi trường test theo hợp đồng.
- Khi timeout xảy ra, cần giữ log của listener, transaction và database để điều tra, không chỉ tăng timeout.

### 9.3. Phân biệt response code và business state

Ở hệ thống thực, việc tạo đơn thành công có thể là `201`, còn fulfillment hoàn tất sau đó. **`201` không đồng nghĩa rằng mọi quy trình downstream đã hoàn thành**. API có thể trả `202 Accepted` cho một quy trình dài và cung cấp endpoint trạng thái riêng.

Test phải kiểm tra contract đúng với nghiệp vụ: created, accepted, pending, ready, failed hoặc canceled. Không ép mọi quy trình bất đồng bộ phải trả kết quả đồng bộ.

### 9.4. Xử lý authentication và authorization

Ví dụ trên giả định API không yêu cầu authentication để tập trung vào cấu trúc test. Với ứng dụng có Spring Security, E2E test nên đi qua cơ chế xác thực thật của môi trường test: HTTP Basic, JWT hợp lệ do test identity provider cấp, cookie/session hoặc phương thức được hệ thống hỗ trợ.

Bỏ qua security filter trong E2E test có thể làm mất bằng chứng rằng request thật được chấp nhận/từ chối đúng quyền. Các trường hợp thiếu token và không đủ quyền cần test theo hợp đồng bảo mật; token hoặc credential dành cho test phải được quản lý riêng.

## 10. Môi trường nào làm bài E2E có giá trị?

Độ trung thực của E2E phụ thuộc vào **hạ tầng được chạy thật** và **hạ tầng bị thay thế**. Test này dùng HTTP server thật, Spring context thật, PostgreSQL thật trong container và Spring event infrastructure trong cùng JVM.

| Thành phần | Trong ví dụ | Hệ quả |
| --- | --- | --- |
| HTTP server | Embedded server trên `RANDOM_PORT` | Kiểm tra request/response qua network stack |
| Bean wiring | Spring Boot context | Lỗi bean, profile và configuration liên quan có thể lộ ra |
| Database | PostgreSQL Testcontainers | SQL dialect và constraint gần PostgreSQL production |
| Sự kiện | Spring Modulith in-process | Kiểm tra giao tiếp trong JVM; chưa kiểm chứng broker ngoài |
| Browser/UI | Không có | Chưa chứng minh render hoặc thao tác người dùng trên web |
| Dịch vụ email/thanh toán bên ngoài | Không có | Chưa chứng minh side effect trên dịch vụ của nhà cung cấp |
| Migration production | Ví dụ dùng Hibernate DDL | Chưa chứng minh Flyway/Liquibase migration của hệ thống thật |

Nếu production dùng Flyway/Liquibase, **nên bật migration trong E2E test** rồi bỏ `ddl-auto=create-drop` của ví dụ. Khi schema lệch, các test phụ thuộc mapping JPA có thể xanh dưới DDL tự tạo nhưng production vẫn lỗi do migration sai.

### Khi có dịch vụ ngoài

Khi luồng cần gọi payment gateway, email provider hoặc một broker, có ba cách:

1. Chạy dịch vụ tương đương trong Testcontainers khi có image/hạ tầng phù hợp.
2. Dùng một fake service/server kiểm soát được (ví dụ mock HTTP server) và khẳng định request gửi ra qua giao thức thật; khi đó đây là **application E2E có biên mô phỏng**.
3. Chạy một bộ nhỏ smoke/E2E trên môi trường staging với dịch vụ thử nghiệm thật và dữ liệu riêng.

Không nên tuyên bố “E2E toàn bộ hệ thống” nếu các dịch vụ quan trọng đã bị mock. Test qua HTTP vẫn hữu ích nhưng phạm vi cần được nêu rõ để người đọc hiểu bằng chứng.

## 11. Các ca E2E nên bổ sung

Một luồng thành công là điểm bắt đầu. Bộ test cần tập trung vào những rủi ro có giá trị cao:

| Kịch bản | Request/điều kiện | Assertion |
| --- | --- | --- |
| Happy path | Tạo đơn hợp lệ | `201`, `orderId` hợp lệ, eventual `READY` cho cùng ID |
| Sai validation | Thiếu `customerId`, amount không dương | `400` và lỗi hợp đồng |
| Chưa có kết quả | GET fulfillment trước khi task có mặt | Status chưa hoàn tất theo API contract |
| Không tồn tại | GET với ID không hợp lệ | `404` hoặc error contract tương ứng |
| Duplicate event | Consumer nhận cùng event nhiều lần | Chỉ một task cuối cùng, không có tác động phụ trùng |
| Rollback | Thất bại sau khi bắt đầu ghi đơn | Không có đơn commit và không có fulfillment sai |
| Database constraint | Giá trị/quan hệ không hợp lệ | Lỗi được xử lý nhất quán, không rò SQL exception |
| Quyền truy cập | Token không hợp lệ/không đủ quyền | `401`/`403` theo security contract |
| Sự cố downstream | Consumer hoặc broker không sẵn sàng | Retry, trạng thái lỗi và quan sát vận hành đúng thiết kế |

### Retry và idempotency

Một listener nhận cùng `OrderPlaced` hai lần có thể thử tạo task hai lần. Unique constraint giúp ngăn duplicate ở database, nhưng cách kiểm tra `existsByOrderId` rồi `save` vẫn có race condition nếu hai listener xử lý đồng thời. Hệ thống đáng tin cậy thường cần thao tác idempotent ở database và cơ chế xử lý trùng hợp lệ.

Với event publication registry của Spring Modulith, khả năng lưu sự kiện chưa xử lý, retry hoặc resubmission phụ thuộc adapter persistence và cấu hình cụ thể. Một E2E test chạy trong cùng JVM **chưa chứng minh** sự kiện sống sót qua restart. Nếu độ bền event là yêu cầu, cần test riêng quy trình lỗi, lưu publication, khởi động lại và xử lý tiếp.

## 12. E2E xanh vẫn cần kiểm chứng kiến trúc

Giả sử `fulfillment` truy cập trực tiếp entity nội bộ:

~~~java
// Import sai ranh giới application module:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

Vì class Java có thể `public` nên mã có thể biên dịch và E2E test vẫn xanh. Nhưng theo mô hình package của Spring Modulith, `orders.internal` không phải API công khai của `orders`.

Bài kiểm tra kiến trúc riêng:

**`src/test/java/com/example/shop/ArchitectureVerificationTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTest {

    @Test
    void modules_respect_dependency_rules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra mô hình kiến trúc, quan hệ phụ thuộc và các ranh giới module mà Spring Modulith xác minh được. Khi muốn giới hạn chiều phụ thuộc, ứng dụng có thể khai báo `@ApplicationModule(allowedDependencies = ...)` hoặc named interfaces theo thiết kế.

**Phân biệt bằng chứng:**

- E2E test trả lời: *Một request thực có đạt kết quả công khai mong đợi không?*
- Architecture verification trả lời: *Các module có tuân thủ phụ thuộc và API được phép không?*

Một bộ test có cả hai mới giúp ngăn việc chữa lỗi bằng cách phá ranh giới kiến trúc mà vẫn giữ happy path chạy được.

## 13. Quality gate CI cho Spring Modulith

Không nên bắt mọi thay đổi nhỏ chỉ dựa vào một E2E test lớn. Một quality gate hợp lý kết hợp test nhanh để phát hiện lỗi gần nguồn và test tích hợp để phát hiện lỗi ghép nối:

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit tests"]
    U --> S["Slice tests"]
    S --> A["ApplicationModules.verify()"]
    A --> M["Application module tests"]
    M --> E["HTTP E2E tests"]
    E --> G{"Tất cả gate<br/>bắt buộc đạt?"}
    G -- "Có" --> Merge["Cho phép merge"]
    G -- "Không" --> Fix["Sửa lỗi / chạy lại"]
~~~

| Lớp quality gate | Lỗi điển hình bị bắt | Chi phí chạy |
| --- | --- | --- |
| Unit test | Công thức, điều kiện, edge case | Thấp |
| Slice test | HTTP mapping, validation, JPA query | Thấp đến vừa |
| Architecture verification | Phụ thuộc sai hướng, vượt internal API | Thường thấp |
| `@ApplicationModuleTest` | Wiring và use case trong module | Vừa |
| Cross-module integration | Listener, database, transaction sau commit | Vừa đến cao |
| HTTP E2E qua entry point | Hợp đồng request/response và luồng ứng dụng | Cao hơn, cần server và có thể cần container |

**Trong CI cần thực hiện:**

- Có container runtime tương thích nếu chạy Testcontainers, và phiên bản PostgreSQL được kiểm soát.
- Bảo đảm JUnit test được phát hiện bởi Gradle/Maven; nếu tách test suite, đánh dấu job E2E quan trọng là bắt buộc trước merge.
- Tránh dùng cổng HTTP cố định; `RANDOM_PORT` giúp giảm xung đột khi chạy song song.
- Lưu log server, listener và database khi bài test timeout; hiển thị rõ ID giao dịch/đơn trong log nếu có cơ chế correlation ID.
- Dọn dữ liệu test hoặc cách ly schema/container để job có thể chạy lại mà không bị dữ liệu cũ ảnh hưởng.
- Quản lý timeout và tài nguyên container dựa trên số liệu CI thực tế, không tăng ngưỡng vô hạn.
- Không để lỗi E2E “flaky” trở thành lý do mặc định để tắt quality gate; điều tra dependency vào thời gian, network, fixture và shared state.

Nếu E2E suite lớn và chậm, có thể giữ **một số luồng nghiệp vụ thiết yếu** làm điều kiện merge, rồi chạy phần còn lại theo lịch. Quyết định chia job phải theo rủi ro nghiệp vụ; các kiểm tra kiến trúc và unit/module test cốt lõi vẫn nên có ở mỗi pull request.

## 14. Chẩn đoán khi E2E thất bại

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| `POST` trả `404` | Sai mapping hoặc context path | Kiểm tra controller và URL thật |
| `POST` trả `400` với dữ liệu hợp lệ | JSON field, validation, content type sai | Kiểm tra payload và lỗi binding |
| `POST` trả `401`/`403` | Security filter hoạt động | Dùng credential/role test đúng |
| Spring context không lên | Thiếu bean, cấu hình module hoặc database | Đọc root cause của exception khi khởi động |
| `201` nhưng không bao giờ có `READY` | Listener không được đăng ký, transaction không commit hoặc event thất bại | Kiểm tra bean listener, executor, transaction và log |
| `READY` xuất hiện không ổn định | Poll quá sớm, timeout ngắn, tài nguyên CI thiếu | Quan sát điều kiện, chỉnh polling có cơ sở |
| H2 xanh, PostgreSQL lỗi | Schema, dialect, constraint khác | Test với database giống production |
| Response từ đơn khác | Fixture trùng hoặc state dùng chung | Ràng buộc assertion bằng đúng `orderId` |
| Test xanh nhưng `verify()` đỏ | Có phụ thuộc trái quy tắc module | Sửa API/import, giữ architecture gate |
| Test kẹt khi đóng context | Executor, pool hoặc container cleanup không hoàn tất | Kiểm tra lifecycle bean và thread dump |

Lỗi timeout không tự nói nguyên nhân là “event không chạy”: có thể event đã nhận nhưng transaction listener rollback, dữ liệu không commit, API đọc sai ID hoặc kết nối database bị lỗi. Cần log đủ chi tiết để xác định đoạn nào trong chuỗi thực thi thất bại.

## 15. Bài thực hành

### Bài A — Tạo E2E test đầu tiên

Dựng hai module `orders` và `fulfillment` như ví dụ, sau đó tạo `ShopHttpE2ETest`:

1. Khởi động Spring Boot trên `RANDOM_PORT`.
2. Gửi `POST /api/orders` với `customerId` riêng và `amount` dương.
3. Kiểm tra `201` cùng `orderId`.
4. Poll `GET /api/fulfillments/{orderId}` đến khi thấy `READY`.
5. Xác minh `orderId` khớp giữa hai HTTP response.

**Điều kiện đạt:** Nếu bỏ annotation listener hoặc sửa mapping event sai, E2E test thất bại trong thời hạn đã đặt.

### Bài B — Validation và error contract

Thêm các test với request thiếu `customerId`, amount bằng 0, JSON thiếu field hoặc sai kiểu dữ liệu. Xác minh status và body lỗi theo API contract. Giải thích sự khác nhau giữa lỗi bị từ chối ở Spring MVC và lỗi domain được ném từ service.

### Bài C — Eventual consistency

Thử thay `await().untilAsserted(...)` bằng một assertion `GET` ngay sau `POST`. Quan sát tại sao test có thể thành công trên máy này nhưng thất bại ở môi trường khác. Khôi phục cách chờ có điều kiện và ghi nhận thời gian thực tế để chọn timeout hợp lý.

### Bài D — Database migration

Thay Hibernate `ddl-auto=create-drop` bằng cơ chế migration của dự án. Chạy E2E với PostgreSQL Testcontainers và viết thêm tình huống kiểm tra unique constraint. Giải thích vì sao chạy trên H2 có thể bỏ sót một số khác biệt SQL/schema.

### Bài E — Kiểm chứng kiến trúc

Chạy bài test `ApplicationModules.of(ShopApplication.class).verify()`. Cố ý tạo một import từ `fulfillment` vào `orders.internal.persistence` ở nhánh thực hành để quan sát thất bại kiến trúc, rồi khôi phục bằng API `orders`. So sánh lỗi này với lỗi HTTP E2E.

### Câu hỏi tự kiểm tra

- Vì sao test gọi trực tiếp `OrderManagement.placeOrder(...)` chưa phải E2E **qua HTTP entry point**?
- Vì sao test `POST` trả `201` chưa chứng minh `fulfillment` đã xử lý event?
- Nếu test chạy với fake payment gateway, có thể khẳng định thanh toán ngoài production đã thành công không?
- Tại sao không nên dùng `@Transactional` của test client để giả định rollback dữ liệu được ghi từ HTTP server?
- Nếu E2E xanh nhưng `ApplicationModules.verify()` thất bại, quality gate có nên cho merge không?

## 16. Ghi nhớ

**End-to-end test qua entry point ứng dụng** cần đi từ request công khai tới kết quả công khai, qua các thành phần thật nằm trong phạm vi cần xác minh. Với Spring Modulith, bài test có giá trị là gửi HTTP tạo đơn, cho `orders` commit và phát `OrderPlaced`, rồi chờ `fulfillment` tạo task và quan sát trạng thái qua HTTP. Khi xử lý bất đồng bộ, test phải chờ một điều kiện đạt được trong thời hạn hữu hạn, đồng thời giữ dữ liệu độc lập và môi trường có thể tái lập.

Đừng đồng nhất E2E test với kiểm chứng kiến trúc. `@SpringBootTest(RANDOM_PORT)` kiểm tra hành vi đường đi HTTP đã chọn; `@ApplicationModuleTest` kiểm tra các hành vi có phạm vi module; `ApplicationModules.verify()` kiểm tra quy tắc phụ thuộc. Kết hợp chúng với unit, slice, database và event reliability tests trong **quality gate CI** để ngăn cả lỗi hồi quy lẫn việc phá vỡ ranh giới module.
