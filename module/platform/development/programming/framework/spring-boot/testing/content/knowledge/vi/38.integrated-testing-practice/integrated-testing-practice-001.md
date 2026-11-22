# Xây bộ kiểm thử cho một tính năng từ service đến HTTP và database

> **Module:** Spring Boot – testing  
> **Nhóm:** Thực hành tích hợp  
> **Đề bài:** Xây bộ kiểm thử cho một tính năng từ service đến HTTP và database  
> **Mục tiêu:** Thiết kế và thực hành một bộ test theo lát cắt dọc (*vertical slice*) cho chức năng tạo/tra cứu đơn hàng: unit test quy tắc nghiệp vụ, MVC slice test validation và HTTP mapping, JPA slice test với PostgreSQL thực, full-context MockMvc test ghi/đọc dữ liệu và test HTTP TCP thật qua random port. Ví dụ dùng **Java 17, Spring Boot 3.5.0, JUnit Jupiter, Mockito, Spring Data JPA, Bean Validation, Flyway và Testcontainers**.

## 1. Bài toán: kiểm thử một hành trình hoàn chỉnh, không chỉ từng class

Chúng ta sẽ triển khai một API đơn giản nhưng có đủ tình huống thực tế: **tạo đơn hàng** và **tra cứu đơn hàng theo ID**.

```text
HTTP client
   |
   | POST /api/orders hoặc GET /api/orders/{id}
   v
Spring MVC / JSON / Bean Validation
   |
   v
OrderController
   |
   v
OrderService [nghiệp vụ, transaction, xử lý trùng]
   |
   v
OrderRepository [Spring Data JPA]
   |
   v
Hibernate / JDBC / HikariCP
   |
   v
PostgreSQL [Flyway migration, unique constraint]
```

Bộ kiểm thử tốt không chỉ hỏi “controller trả 201?” mà cần phát hiện:

- Controller nhận và deserialize JSON đúng hay không.
- DTO có reject request thiếu dữ liệu, số lượng ≤ 0 hoặc quá giới hạn.
- Service bảo vệ business invariants kể cả khi được gọi ngoài HTTP.
- Service phát hiện mã yêu cầu trùng và trả exception domain đúng.
- Spring ExceptionHandler ánh xạ domain exception thành HTTP 404/409, không trả 500 vô cớ.
- Repository có ghi, truy vấn và enforce unique constraint trên **PostgreSQL thật**.
- Full request qua Spring MVC có gọi service/repository thật, commit dữ liệu và GET thấy bản ghi vừa tạo.
- MockMvc test có đủ tính tích hợp đến database nhưng **không** mở TCP server.
- Một test `RANDOM_PORT` dùng HTTP client thật để chứng minh embedded server nhận request qua socket.
- Cleanup không phụ thuộc test order hoặc dọn sạch dữ liệu test khác.

**Hai sai lầm trái ngược:** Chỉ unit test Mockito rồi gọi là end-to-end; hoặc chỉ chạy `@SpringBootTest` cho mọi edge case khiến suite chậm, khó biết hỏng ở đâu. Bài này phối hợp nhiều tầng, mỗi tầng có trách nhiệm riêng.

## 2. API contract và acceptance criteria

### 2.1. POST tạo đơn hàng

```http
POST /api/orders
Content-Type: application/json

{
  "requestId": "client-2026-001",
  "sku": "BOOK-01",
  "quantity": 2
}
```

Yêu cầu:

- `requestId` là chuỗi không rỗng/toàn khoảng trắng, dài tối đa 64 ký tự.
- `sku` là chuỗi không rỗng/toàn khoảng trắng, dài tối đa 32 ký tự.
- `quantity` là số nguyên từ 1 tới 20; không được thiếu/null.
- Một `requestId` chỉ được phép tạo **một** đơn. Chính sách của lab: gọi lại cùng `requestId` sẽ là **409 Conflict**, không phải automatic idempotent replay. Nếu dự án muốn semantics idempotency-key thật, phải bổ sung kiểm tra payload và replay response, không được tự gọi sample này là idempotent.
- Khi tạo hợp lệ, trả **201 Created** và header `Location: /api/orders/{id}`.
- Body trả ID do database sinh và thông tin nghiệp vụ.

Ví dụ response minh họa, ID thực tế do database sinh:

```http
HTTP/1.1 201 Created
Location: /api/orders/1
Content-Type: application/json

{
  "id": 1,
  "requestId": "client-2026-001",
  "sku": "BOOK-01",
  "quantity": 2,
  "status": "CREATED"
}
```

Không hard-code kỳ vọng ID `1` trong integration tests: sequence/identity có thể tăng vì tests khác, rollback cũng không bảo đảm sequence reset.

### 2.2. GET đọc đơn hàng

```http
GET /api/orders/1
```

- Tìm thấy: **200 OK** với JSON đầy đủ.
- Không có ID: **404 Not Found**, body dạng `ProblemDetail` có `status` và `detail`.

### 2.3. Đầu vào không hợp lệ và mã trùng

- POST thiếu SKU, `requestId` blank, `quantity=0` hoặc `quantity=21`: **400 Bad Request**, không gọi service trong MVC slice và không tạo row trong integration.
- POST cùng `requestId` khi row đã tồn tại: **409 Conflict**, chỉ một row cho requestId đó.
- Hai requests chạy đồng thời cùng `requestId`: kiểm tra `existsByRequestId` trước insert **không đủ ngăn race**; database unique constraint là tầng quyết định. Service phải chuyển **đúng** unique-constraint violation thành domain conflict. Các ràng buộc khác không được lạm dụng ánh xạ thành 409.

### 2.4. Ma trận acceptance tests

| ID | Tình huống | Service | HTTP | DB |
| --- | --- | --- | --- | --- |
| AC-01 | Tạo hợp lệ | Tạo entity trạng thái CREATED | 201, Location, body | 1 row, ID sinh |
| AC-02 | Tra cứu đã tạo | Trả view | 200 JSON | GET đúng row |
| AC-03 | Request trùng | Ném OrderConflictException | 409 | Không có row thứ hai |
| AC-04 | Payload không hợp lệ | Bảo vệ invariant nếu gọi trực tiếp | 400 | Không insert |
| AC-05 | ID không tồn tại | Ném OrderNotFoundException | 404 | Không phát sinh row |
| AC-06 | Race insert trùng | DB constraint nhận diện | 409 khi đúng unique key | Unique constraint |
| AC-07 | Sau POST, GET đọc được | Transaction commit | 201 → 200 | Dữ liệu còn sau HTTP request |
| AC-08 | HTTP TCP thật | Bean wiring + server | Real TCP response | Postgres real |

Đây là **hợp đồng cụ thể**, không phải lời hứa về toàn bộ tính năng order management production. Lab chưa có payment, inventory, authentication, event broker, pagination hay distributed idempotency.

## 3. Chọn đúng tầng test

### 3.1. Năm loại test dùng trong bài

| Tầng | Annotation/cơ chế | Thành phần thật | Thành phần thay thế | Phát hiện lỗi |
| --- | --- | --- | --- | --- |
| Unit Service | JUnit + `MockitoExtension` | OrderService | Mock OrderRepository | Business rule, nhánh exception |
| MVC Slice | `@WebMvcTest`, `@MockitoBean` | Controller, MVC, Jackson, validation/advice | Mock OrderService | Route, DTO, HTTP code/body |
| JPA Slice | `@DataJpaTest` + PostgreSQL Testcontainers | Repository, Hibernate, PostgreSQL, Flyway | Không cần service | SQL mapping, unique constraint |
| Full Context MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Controller → Service → JPA → PostgreSQL | Không mock nghiệp vụ | Chuỗi tích hợp, commit/persistence |
| HTTP TCP | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Embedded HTTP server + toàn bộ stack | Không mock nghiệp vụ | Port/network serialization và real HTTP |

**Phân biệt quan trọng:** `@WebMvcTest` và `@AutoConfigureMockMvc` **không** mở server TCP, dù đều mô phỏng request HTTP qua servlet stack. `RANDOM_PORT` mới khởi động embedded server trên port động. Ở full-context MockMvc test ta cố ý **không** gắn `@Transactional` trên test method để kiểm tra row đã commit thực sự sau service call.

### 3.2. Vì sao không dùng 100% `@SpringBootTest`?

- Unit test service không cần database hay Spring context; phản hồi nhanh và chẩn đoán business branch chính xác.
- MVC slice không nên phụ thuộc Docker chỉ để kiểm tra request validation hay status mapping.
- JPA slice kiểm tra DB mapping/constraint mà không phải boot web server.
- Full integration bắt cross-layer wiring bugs mà các mock-based tests không thấy.
- Test TCP thật chỉ cần một vài happy/error paths để phát hiện khác biệt startup/port/codec, không lặp toàn bộ unit assertions.

Khi một integration test fail, kết quả các test tầng dưới giúp khoanh vùng: service business, HTTP mapping, JPA migration hay Spring wiring.

## 4. Project runnable-design

### 4.1. Cấu trúc thư mục

```text
orders-testing-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orders/
    │   │   ├── OrdersApplication.java
    │   │   ├── OrderStatus.java
    │   │   ├── PurchaseOrder.java
    │   │   ├── OrderRepository.java
    │   │   ├── CreateOrderRequest.java
    │   │   ├── OrderView.java
    │   │   ├── OrderConflictException.java
    │   │   ├── OrderNotFoundException.java
    │   │   ├── OrderService.java
    │   │   ├── OrderController.java
    │   │   └── OrderExceptionHandler.java
    │   └── resources/
    │       ├── application.properties
    │       └── db/migration/V1__create_purchase_orders.sql
    └── test/
        └── java/com/example/orders/
            ├── PostgresTestConfig.java
            ├── OrderServiceTest.java
            ├── OrderControllerMvcTest.java
            ├── OrderRepositoryPostgresTest.java
            ├── OrderFlowMockMvcIT.java
            └── OrderHttpSocketIT.java
```

**Package:** `com.example.orders`. Tên public top-level class/record/enum trùng tên file. Không cần Docker cho hai test classes unit/MVC slice; ba classes còn lại cần Docker-compatible daemon. Tất cả tests dùng JUnit Jupiter.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-testing-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-database-postgresql</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <includes>
                        <include>**/*Test.java</include>
                        <include>**/*IT.java</include>
                    </includes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:**

- `starter-web`: MVC controller, embedded Tomcat, Jackson JSON và MockMvc web dependencies trong tests.
- `starter-validation`: Jakarta Bean Validation, `@Valid`, `@NotBlank`, `@NotNull`, `@Min`/`@Max`.
- `starter-data-jpa`: Hibernate, Spring Data repositories và transaction manager.
- `postgresql`: JDBC driver (runtime).
- `flyway-core` + `flyway-database-postgresql`: database migration support cho PostgreSQL trên Flyway 11 do Boot 3.5 BOM quản lý. Thiếu module PostgreSQL có thể gây “Unsupported Database”.
- `starter-test`: JUnit Jupiter, AssertJ, Mockito, MockMvc.
- `spring-boot-testcontainers`: `@ServiceConnection`/Boot Testcontainers integration.
- `org.testcontainers:postgresql`: real PostgreSQL container. **Không cần `org.testcontainers:junit-jupiter`** khi container được khai là Spring-managed `@Bean`, không dùng JUnit `@Container` extension.
- `maven-surefire-plugin` được cấu hình include cả `*IT.java` trong goal `test`. Mặc định nhiều cấu hình Surefire không tự nhận tên `*IT`, vì vậy đừng bỏ phần includes rồi tuyên bố full suite đã chạy.

Các dependency versions đến từ Spring Boot 3.5.0 BOM; nếu nâng patch, kiểm tra managed versions trước khi override từng thư viện.

### 4.3. `application.properties`

```properties
# src/main/resources/application.properties

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.flyway.locations=classpath:db/migration

# Không ghi thông tin datasource/secrets production vào sample.
# Integration test lấy JDBC credentials từ Testcontainers @ServiceConnection.
```

`ddl-auto=validate` nghĩa là Hibernate **không tự tạo** bảng trong test; Flyway migration là nguồn schema. Nếu migration thiếu hoặc entity/schema lệch, Spring context sẽ fail sớm — đó là tín hiệu có ích.

Chạy app production độc lập cần cung cấp datasource URL/credentials riêng qua environment/secret manager. Bài tập này chủ yếu chạy test suite, không có PostgreSQL production được hard-code.

### 4.4. Flyway migration

```sql
-- src/main/resources/db/migration/V1__create_purchase_orders.sql

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    sku VARCHAR(32) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    CONSTRAINT ck_purchase_orders_quantity
        CHECK (quantity BETWEEN 1 AND 20),
    CONSTRAINT uk_purchase_orders_request_id
        UNIQUE (request_id)
);
```

Migration có tên `V1__create_purchase_orders.sql` với **hai dấu gạch dưới** giữa version và description; Flyway chạy khi context kết nối PostgreSQL. Unique key ở DB bảo vệ cả khi hai HTTP requests cùng thấy `existsByRequestId=false`. Không thay unique constraint bằng assert trong một test.

Sử dụng PostgreSQL 16. H2 có thể khác dialect/constraint behavior, nên bài cố ý dùng PostgreSQL Testcontainers cho repository/full integration.

## 5. Code production: từ domain đến HTTP

### 5.1. `OrdersApplication.java`

```java
// src/main/java/com/example/orders/OrdersApplication.java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 5.2. `OrderStatus.java`

```java
// src/main/java/com/example/orders/OrderStatus.java
package com.example.orders;

public enum OrderStatus {
    CREATED
}
```

Chỉ một trạng thái cho lab; production có thể có `PAID`, `CANCELLED`, state transitions và outbox events với những test riêng.

### 5.3. `PurchaseOrder.java`

```java
// src/main/java/com/example/orders/PurchaseOrder.java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "purchase_orders",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_purchase_orders_request_id",
                columnNames = "request_id"))
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, length = 64)
    private String requestId;

    @Column(nullable = false, length = 32)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private OrderStatus status;

    protected PurchaseOrder() {
        // Required by JPA.
    }

    public PurchaseOrder(
            String requestId, String sku, int quantity) {
        this.requestId = requestId;
        this.sku = sku;
        this.quantity = quantity;
        this.status = OrderStatus.CREATED;
    }

    public Long getId() {
        return id;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`@GeneratedValue(IDENTITY)` dựa PostgreSQL identity column; ID được DB sinh. `@Enumerated(STRING)` lưu literal `CREATED` chứ không lưu ordinal integer dễ vỡ khi đổi enum order. Entity có protected no-arg constructor cho JPA.

### 5.4. `OrderRepository.java`

```java
// src/main/java/com/example/orders/OrderRepository.java
package com.example.orders;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    boolean existsByRequestId(String requestId);

    Optional<PurchaseOrder> findByRequestId(
            String requestId);

    long countByRequestId(String requestId);
}
```

Spring Data JPA suy ra queries từ method names. `findById`, `saveAndFlush`, `delete`, `flush` đã có sẵn qua `JpaRepository`. `countByRequestId` giúp assert **đúng row test này**, không lấy count toàn bảng khi các test khác có thể chạy.

### 5.5. `CreateOrderRequest.java`

```java
// src/main/java/com/example/orders/CreateOrderRequest.java
package com.example.orders;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank @Size(max = 64) String requestId,
        @NotBlank @Size(max = 32) String sku,
        @NotNull @Min(1) @Max(20) Integer quantity) {
}
```

Sử dụng `Integer` thay vì primitive `int` để phát hiện `null`/field bị thiếu bằng `@NotNull`. Controller phải khai `@Valid @RequestBody` để Bean Validation có tác dụng ở HTTP boundary. Validation annotations **không tự kích hoạt** khi một unit test trực tiếp `new CreateOrderRequest(...)` nếu không chạy validator; service cũng kiểm tra invariants.

### 5.6. `OrderView.java`

```java
// src/main/java/com/example/orders/OrderView.java
package com.example.orders;

public record OrderView(
        Long id,
        String requestId,
        String sku,
        int quantity,
        OrderStatus status) {

    public static OrderView from(PurchaseOrder order) {
        return new OrderView(
                order.getId(),
                order.getRequestId(),
                order.getSku(),
                order.getQuantity(),
                order.getStatus());
    }
}
```

Record này là response contract ổn định; không serialize JPA entity trực tiếp để tránh vấn đề lazy loading, leaking internal fields và coupling JSON với DB mapping.

### 5.7. `OrderConflictException.java`

```java
// src/main/java/com/example/orders/OrderConflictException.java
package com.example.orders;

public class OrderConflictException
        extends RuntimeException {

    public OrderConflictException(String requestId) {
        super("requestId already exists: " + requestId);
    }

    public OrderConflictException(
            String requestId, Throwable cause) {
        super("requestId already exists: " + requestId,
                cause);
    }
}
```

### 5.8. `OrderNotFoundException.java`

```java
// src/main/java/com/example/orders/OrderNotFoundException.java
package com.example.orders;

public class OrderNotFoundException
        extends RuntimeException {

    public OrderNotFoundException(long id) {
        super("Order " + id + " not found");
    }
}
```

### 5.9. `OrderService.java`

```java
// src/main/java/com/example/orders/OrderService.java
package com.example.orders;

import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class OrderService {

    private static final String REQUEST_ID_CONSTRAINT =
            "uk_purchase_orders_request_id";

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderView create(
            String requestId, String sku, int quantity) {

        // Defense-in-depth: service can be called outside HTTP.
        if (!StringUtils.hasText(requestId)
                || requestId.length() > 64
                || !StringUtils.hasText(sku)
                || sku.length() > 32
                || quantity < 1 || quantity > 20) {
            throw new IllegalArgumentException(
                    "invalid order input");
        }

        if (repository.existsByRequestId(requestId)) {
            throw new OrderConflictException(requestId);
        }

        try {
            PurchaseOrder saved = repository.saveAndFlush(
                    new PurchaseOrder(requestId, sku, quantity));
            return OrderView.from(saved);
        }
        catch (DataIntegrityViolationException ex) {
            // Handle only the known unique constraint.
            if (isRequestIdUniquenessViolation(ex)) {
                throw new OrderConflictException(requestId, ex);
            }
            throw ex;
        }
    }

    @Transactional(readOnly = true)
    public OrderView get(long id) {
        return repository.findById(id)
                .map(OrderView::from)
                .orElseThrow(
                        () -> new OrderNotFoundException(id));
    }

    private static boolean isRequestIdUniquenessViolation(
            Throwable error) {
        Throwable current = error;

        while (current != null) {
            if (current instanceof ConstraintViolationException
                    constraint
                    && REQUEST_ID_CONSTRAINT.equalsIgnoreCase(
                            constraint.getConstraintName())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
```

**Tại sao service kiểm tra cả `existsBy...` lẫn DB constraint?**

- `existsByRequestId` trả lỗi domain sớm cho trường hợp trùng bình thường.
- Hai transactions cùng kiểm tra `exists=false` có thể cùng insert; unique constraint ở PostgreSQL mới quyết định.
- `saveAndFlush` buộc Hibernate phát SQL để unique violation xuất hiện ngay trong method, không chờ commit bên ngoài service.
- Khi exception hierarchy chứa Hibernate `ConstraintViolationException` đúng tên `uk_purchase_orders_request_id`, service chuyển thành `OrderConflictException` → HTTP 409.
- Những constraint errors khác được rethrow, **không biến tất cả `DataIntegrityViolationException` thành 409**.

**Giới hạn có chủ đích:** Không phải mọi database/vendor/JDBC driver đều report constraint name ổn định. Nếu Hibernate không có constraint name, service sẽ rethrow DB exception thay vì đoán. Với production nên bổ sung PostgreSQL SQLSTATE + exact constraint metadata handling được kiểm thử với driver/version và centralized error policy. Không parse thông điệp SQL lỗi bằng cách phụ thuộc text tiếng Anh không ổn định. Vì đây là một lab sử dụng PostgreSQL 16 và Flyway constraint name cố định, ta có thể kiểm tra cả unique violation repository và mapping exception service.

**Giao dịch:** `@Transactional` của service bao toàn bộ tạo order. Nếu unique insert fail, runtime exception làm transaction rollback. Test full flow không nên gắn `@Transactional` ngoài method rồi tưởng đã kiểm tra commit thật.

### 5.10. `OrderController.java`

```java
// src/main/java/com/example/orders/OrderController.java
package com.example.orders;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderView view = service.create(
                request.requestId(),
                request.sku(),
                request.quantity());

        return ResponseEntity
                .created(URI.create("/api/orders/" + view.id()))
                .body(view);
    }

    @GetMapping("/{id}")
    public OrderView get(@PathVariable long id) {
        return service.get(id);
    }
}
```

`@Valid` đảm bảo payload invalid bị Spring MVC trả 400 trước khi gọi service. Header `Location` dùng ID từ persisted `OrderView`. Từ unit service mock (nơi ID có thể null) **không** suy ra 201 response: controller slice phải cấp một mock response ID cụ thể; full integration đảm bảo DB sinh ID không null.

### 5.11. `OrderExceptionHandler.java`

```java
// src/main/java/com/example/orders/OrderExceptionHandler.java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderExceptionHandler {

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ProblemDetail> conflict(
            OrderConflictException ex) {
        return problem(
                HttpStatus.CONFLICT,
                "Order request conflict",
                ex.getMessage());
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            OrderNotFoundException ex) {
        return problem(
                HttpStatus.NOT_FOUND,
                "Order not found",
                ex.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> badRequest(
            IllegalArgumentException ex) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "Invalid order request",
                ex.getMessage());
    }

    private static ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail) {
        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);
        return ResponseEntity.status(status).body(body);
    }
}
```

`ProblemDetail` của Spring Framework 6 dùng HTTP status/detail/title cho lỗi domain. Tests assert **status và thông tin ổn định**, không phụ thuộc toàn bộ error JSON của Spring Boot cho malformed JSON/validation; format các default errors có thể thay theo config.

## 6. Cấu hình Testcontainers cho các integration tests

### 6.1. `PostgresTestConfig.java`

```java
// src/test/java/com/example/orders/PostgresTestConfig.java
package com.example.orders;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

- Container là **Spring-managed bean** (`@Bean`), không phải static `@Container` của JUnit extension.
- `@ServiceConnection` để Boot nhận host/port/username/password động, không hard-code `localhost:5432`.
- Container bean khởi động **trước** các dependent beans (Flyway/DataSource/JPA) và stop **sau** khi các beans đó được destroy.
- ApplicationContext cache có thể giữ cả container lẫn JDBC pool giữa classes tương thích; chúng sống đồng bộ.
- `@Import(PostgresTestConfig.class)` trong test classes nào cần Postgres; unit/MVC slice không import nó.
- Mỗi cấu hình context riêng có thể khởi động PostgreSQL container riêng. Vì `@DataJpaTest`, full MockMvc và `RANDOM_PORT` có context keys khác, nên project thường tạo **ba context/container lifetimes khác nhau**; đó là trade-off có chủ đích để tách test scopes.
- Không dùng reusable Testcontainers hoặc Docker global cleanup trong bài; nếu environment bị kill, cần CI resource management riêng.

### 6.2. `@DataJpaTest` và database replacement

`@DataJpaTest` auto-configure JPA repository/entity, transaction và Flyway (khi dependency có sẵn), nhưng có thể tự thay datasource bằng database embedded nếu có H2/HSQL/Derby trong classpath. Với PostgreSQL Testcontainers, khai rõ:

```java
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
```

Dù project không khai H2, flag này thể hiện **ý định kiểm tra đúng PostgreSQL**, tránh test xanh giả sau khi một dependency H2 được thêm về sau.

### 6.3. Flyway vs `ddl-auto=validate`

Trình tự mong muốn:

```text
Spring creates PostgreSQLContainer bean
      ↓
Boot obtains JdbcConnectionDetails
      ↓
DataSource/Hikari ready
      ↓
Flyway applies V1 migration
      ↓
Hibernate validates entity/table mapping
      ↓
Repository/Service/Controller tests run
```

Nếu migration sai, test nên fail startup, không fallback sang H2 hay `ddl-auto=create-drop` để “cho xanh”. Test schema cần giống production migrations trong phạm vi chức năng.

## 7. Unit test Service bằng Mockito — 5 tests, không Spring context

### 7.1. `OrderServiceTest.java`

```java
// src/test/java/com/example/orders/OrderServiceTest.java
package com.example.orders;

import java.sql.SQLException;
import java.util.Optional;

import org.hibernate.exception.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @Test
    void createsOrderWithCorrectBusinessFields() {
        when(repository.saveAndFlush(
                any(PurchaseOrder.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        OrderView view =
                service.create("req-unit-1", "BOOK-01", 2);

        assertThat(view.requestId())
                .isEqualTo("req-unit-1");
        assertThat(view.sku())
                .isEqualTo("BOOK-01");
        assertThat(view.quantity()).isEqualTo(2);
        assertThat(view.status())
                .isEqualTo(OrderStatus.CREATED);

        ArgumentCaptor<PurchaseOrder> captured =
                ArgumentCaptor.forClass(PurchaseOrder.class);

        verify(repository).existsByRequestId("req-unit-1");
        verify(repository).saveAndFlush(captured.capture());

        assertThat(captured.getValue().getRequestId())
                .isEqualTo("req-unit-1");
        assertThat(captured.getValue().getStatus())
                .isEqualTo(OrderStatus.CREATED);
        // Entity chưa có ID vì repository ở đây là mock.
    }

    @Test
    void rejectsKnownDuplicateBeforeInsert() {
        when(repository.existsByRequestId("req-dup"))
                .thenReturn(true);

        assertThatThrownBy(
                () -> service.create("req-dup", "BOOK-01", 1))
                .isInstanceOf(OrderConflictException.class)
                .hasMessageContaining("req-dup");

        verify(repository, never())
                .saveAndFlush(any(PurchaseOrder.class));
    }

    @Test
    void translatesNamedUniqueConstraintRaceToConflict() {
        ConstraintViolationException hibernateCause =
                new ConstraintViolationException(
                        "duplicate request id",
                        new SQLException("duplicate", "23505"),
                        "uk_purchase_orders_request_id");

        when(repository.saveAndFlush(
                any(PurchaseOrder.class)))
                .thenThrow(new DataIntegrityViolationException(
                        "unique constraint", hibernateCause));

        assertThatThrownBy(() ->
                service.create("req-race", "BOOK-01", 1))
                .isInstanceOf(OrderConflictException.class)
                .hasCauseInstanceOf(
                        DataIntegrityViolationException.class);
    }

    @Test
    void rejectsInvalidInputBeforeRepositoryCall() {
        assertThatThrownBy(
                () -> service.create("req-x", "BOOK-01", 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid order input");

        verifyNoInteractions(repository);
    }

    @Test
    void missingIdBecomesDomainNotFound() {
        when(repository.findById(404L))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(404L))
                .isInstanceOf(OrderNotFoundException.class)
                .hasMessage("Order 404 not found");

        verify(repository).findById(404L);
    }
}
```

**5 phương thức `@Test`.** Unit mock repository trả entity chưa có JPA-generated ID, nên test service **không** khẳng định `id == 1` hay ID non-null. Bản ghi được persist và ID do database cấp sẽ được kiểm tra ở JPA/full integration tests.

**Lưu ý Mockito strict stubbing:** Không stub mọi method “cho sẵn”. Chỉ stub những lời gọi thực tế cần thiết; các method `existsBy...` trả boolean false mặc định trên mock khi không được stub, nên hai happy/race tests không cần `when(...).thenReturn(false)`.

**Vì sao unit test race?** Nó chứng minh nhánh chuyển đúng **named unique constraint** thành domain conflict. Nhưng repository đã bị mock, nên nó **không chứng minh PostgreSQL thật** enforce unique key — `OrderRepositoryPostgresTest` ở phần 9 sẽ kiểm tra điều đó.

### 7.2. Những điều unit test không chứng minh

- Không chạy Hibernate, SQL, Flyway hay PostgreSQL.
- Không chứng minh `@Transactional` tạo/commit một DB transaction, vì `MockitoExtension` không khởi động Spring AOP proxy.
- Không chứng minh JSON/request validation; `@Valid` thuộc Spring MVC và validation framework.
- Không chứng minh 201/404/409 HTTP mapping; đó là trách nhiệm controller/advice.
- Không chứng minh constraintName thực tế do PostgreSQL/Hibernate report khi có race. Khi nâng driver, hãy bổ sung race integration test nếu đó là mục tiêu quan trọng.

## 8. MVC slice test — 5 tests, không Docker

### 8.1. `OrderControllerMvcTest.java`

```java
// src/test/java/com/example/orders/OrderControllerMvcTest.java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(OrderExceptionHandler.class)
class OrderControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderService service;

    @Test
    void postValidJsonReturns201AndLocation()
            throws Exception {
        when(service.create("req-mvc-1", "BOOK-01", 2))
                .thenReturn(new OrderView(
                        77L, "req-mvc-1",
                        "BOOK-01", 2, OrderStatus.CREATED));

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "requestId": "req-mvc-1",
                              "sku": "BOOK-01",
                              "quantity": 2
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/orders/77"))
                .andExpect(jsonPath("$.id").value(77))
                .andExpect(jsonPath("$.sku").value("BOOK-01"))
                .andExpect(jsonPath("$.status")
                        .value("CREATED"));

        verify(service).create("req-mvc-1", "BOOK-01", 2);
    }

    @Test
    void invalidJsonFieldsReturn400WithoutServiceCall()
            throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "requestId": " ",
                              "sku": "",
                              "quantity": 0
                            }
                            """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void duplicateDomainExceptionMapsTo409()
            throws Exception {
        when(service.create("req-mvc-2", "BOOK-01", 1))
                .thenThrow(new OrderConflictException(
                        "req-mvc-2"));

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "requestId": "req-mvc-2",
                              "sku": "BOOK-01",
                              "quantity": 1
                            }
                            """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.detail").value(
                        "requestId already exists: req-mvc-2"));
    }

    @Test
    void getExistingReturns200Json() throws Exception {
        when(service.get(77L))
                .thenReturn(new OrderView(
                        77L, "req-mvc-3",
                        "BOOK-01", 3, OrderStatus.CREATED));

        mvc.perform(get("/api/orders/{id}", 77L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(77))
                .andExpect(jsonPath("$.quantity").value(3))
                .andExpect(jsonPath("$.status")
                        .value("CREATED"));

        verify(service).get(77L);
    }

    @Test
    void getMissingMapsTo404ProblemDetail()
            throws Exception {
        when(service.get(444L))
                .thenThrow(new OrderNotFoundException(444L));

        mvc.perform(get("/api/orders/{id}", 444L))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail")
                        .value("Order 444 not found"));
    }
}
```

**5 phương thức `@Test`.** `@WebMvcTest` auto-configures Spring MVC, Jackson, Bean Validation và MockMvc. `@MockitoBean` là annotation Spring Framework 6.2 để thay dependency bean trong test ApplicationContext; **không** nhầm với Mockito field `@Mock` (field mock không tự được Controller autowire). `@Import(OrderExceptionHandler.class)` đưa advice vào test context một cách tường minh.

Các tests trên không tạo PostgreSQL container và không phát SQL. Chúng bảo vệ HTTP contract và isolation với controller logic; service behavior là mocked. Nếu controller gọi sai parameters, `verify(service)` có thể bắt được lỗi chuyển dữ liệu.

**Vì sao không chỉ assert status?** Trường hợp 201 còn cần `Location`, response JSON ID/SKU/status và verify controller chuyển đúng parameters sang service. Trường hợp 400 cần verify service chưa bị gọi.

## 9. JPA slice test với PostgreSQL thật — 2 tests

### 9.1. `OrderRepositoryPostgresTest.java`

```java
// src/test/java/com/example/orders/OrderRepositoryPostgresTest.java
package com.example.orders;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresTestConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderRepositoryPostgresTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesAndReadsRowWithGeneratedIdentity() {
        String requestId =
                "repo-" + UUID.randomUUID();

        PurchaseOrder saved = repository.saveAndFlush(
                new PurchaseOrder(requestId, "BOOK-01", 2));

        assertThat(saved.getId()).isNotNull();
        assertThat(repository.findByRequestId(requestId))
                .isPresent()
                .get()
                .extracting(PurchaseOrder::getQuantity)
                .isEqualTo(2);
    }

    @Test
    void postgresUniqueConstraintRejectsSameRequestId() {
        String requestId =
                "dup-" + UUID.randomUUID();

        repository.saveAndFlush(
                new PurchaseOrder(requestId, "BOOK-01", 1));

        assertThatThrownBy(() ->
                repository.saveAndFlush(
                        new PurchaseOrder(
                                requestId, "BOOK-02", 2)))
                .isInstanceOf(
                        DataIntegrityViolationException.class);
        // Sau PostgreSQL constraint error, đừng query thêm
        // trong cùng transaction đang bị đánh dấu aborted.
    }
}
```

**2 phương thức `@Test`.** Test này chạy Hibernate/real PostgreSQL, không load controller/service. `@DataJpaTest` thường tạo transaction và rollback sau mỗi method. Bởi vậy fixture ở method đầu không phụ thuộc method thứ hai; PostgreSQL identity sequence **không** phải lúc nào rollback cũng quay về 1.

**Cảnh báo khi test constraint trên PostgreSQL:** Khi SQL violation xảy ra trong transaction, PostgreSQL đánh dấu transaction lỗi tới lúc rollback. Đừng thực hiện truy vấn tiếp trên cùng transaction rồi kết luận repository API hỏng; để Spring test-managed transaction rollback khi method kết thúc.

Nếu chỉ có H2, unique constraints có thể vẫn pass nhưng không chứng minh PostgreSQL driver/dialect/DDL đã khớp. `@AutoConfigureTestDatabase(replace=NONE)` là yêu cầu rõ ràng.

## 10. Full-context MockMvc + PostgreSQL — 4 tests

### 10.1. Vì sao class này không `@Transactional`?

`@SpringBootTest + @AutoConfigureMockMvc` tải **controller, service, JPA, Flyway và PostgreSQL**. Dù MockMvc không mở socket, nó đi qua Spring MVC filters, request mapping, validation và controller. Service tự mở/commit transaction.

Không đặt `@Transactional` trên test method vì muốn khẳng định sau POST, GET và repository query **ở transaction mới** nhìn thấy row đã commit. Một test-managed transaction có thể che vấn đề commit hoặc tự rollback dữ liệu sau method.

Để không làm bẩn database, mỗi test dùng `requestId` ngẫu nhiên rồi `@AfterEach` chỉ xóa rows **thuộc mình**.

### 10.2. `OrderFlowMockMvcIT.java`

```java
// src/test/java/com/example/orders/OrderFlowMockMvcIT.java
package com.example.orders;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(PostgresTestConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderFlowMockMvcIT {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderRepository repository;

    @Autowired
    ObjectMapper mapper;

    private final Set<String> ownedIds = new HashSet<>();

    private String newRequestId() {
        String id = "it-" + UUID.randomUUID();
        ownedIds.add(id);
        return id;
    }

    private static String json(
            String requestId, String sku, int quantity) {
        return """
            {"requestId":"%s","sku":"%s","quantity":%d}
            """.formatted(requestId, sku, quantity);
    }

    @AfterEach
    void deleteOnlyRowsCreatedByThisTest() {
        for (String requestId : ownedIds) {
            repository.findByRequestId(requestId)
                    .ifPresent(repository::delete);
        }
        repository.flush();
    }

    @Test
    void postThenGetReadsCommittedRow()
            throws Exception {
        String requestId = newRequestId();

        MvcResult created = mvc.perform(
                        post("/api/orders")
                                .contentType(
                                        MediaType.APPLICATION_JSON)
                                .content(
                                        json(requestId, "BOOK-01", 2)))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.requestId")
                        .value(requestId))
                .andExpect(jsonPath("$.status")
                        .value("CREATED"))
                .andReturn();

        long id = mapper.readTree(
                created.getResponse().getContentAsString())
                .get("id").asLong();

        assertThat(id).isPositive();

        mvc.perform(get("/api/orders/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku")
                        .value("BOOK-01"))
                .andExpect(jsonPath("$.quantity")
                        .value(2));

        assertThat(repository.countByRequestId(requestId))
                .isEqualTo(1);
    }

    @Test
    void duplicatePostReturns409AndOnlyOneRow()
            throws Exception {
        String requestId = newRequestId();
        String payload = json(requestId, "BOOK-01", 1);

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isCreated());

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409));

        assertThat(repository.countByRequestId(requestId))
                .isEqualTo(1);
    }

    @Test
    void invalidPostDoesNotInsert()
            throws Exception {
        String requestId = newRequestId();

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(requestId, " ", 0)))
                .andExpect(status().isBadRequest());

        assertThat(repository.countByRequestId(requestId))
                .isZero();
    }

    @Test
    void missingGetReturns404()
            throws Exception {
        mvc.perform(get(
                        "/api/orders/{id}", Long.MAX_VALUE))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }
}
```

**4 phương thức `@Test`** kiểm tra đường đi thật trong ứng dụng. Chúng không mock repository hoặc service. Test `postThenGetReadsCommittedRow` có ba bằng chứng bổ sung nhau: HTTP 201, HTTP GET 200, và repository thấy **một** row của requestId. Test `duplicatePostReturns409AndOnlyOneRow` không chỉ xem status 409 mà còn assert database không tăng thành hai rows.

**Về cleanup:** `@AfterEach` chạy sau mỗi method, chỉ gọi `findByRequestId`/`delete` cho các IDs test sở hữu. Không dùng `TRUNCATE TABLE purchase_orders` global. Mỗi test object JUnit mặc định `PER_METHOD` có `ownedIds` riêng. Class chưa bật concurrent methods; nếu bật song song/forks, database namespace/transaction và context lifecycle cần được thiết kế lại.

**Không nhầm:** MockMvc vẫn là **mock servlet environment**; không có HTTP server lắng nghe thật. Muốn kiểm thử TCP/embedded server, xem phần 11.

## 11. Random-port real HTTP + PostgreSQL — 2 tests

### 11.1. Tại sao thêm một tầng HTTP thật?

`MockMvc` rất mạnh ở Spring MVC boundary nhưng bỏ qua real socket/embedded server startup. `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động Tomcat/embedded server trên port ngẫu nhiên; `TestRestTemplate` gửi request HTTP qua client/server threads thật.

Quan trọng: test method có `@Transactional` **không tự rollback** những DB writes do server thread thực hiện. Trong project, ta không khai test transaction và cleanup rows theo requestId.

### 11.2. `OrderHttpSocketIT.java`

```java
// src/test/java/com/example/orders/OrderHttpSocketIT.java
package com.example.orders;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(PostgresTestConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderHttpSocketIT {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository repository;

    private final Set<String> ownedIds = new HashSet<>();

    private String ownedRequestId() {
        String id = "http-" + UUID.randomUUID();
        ownedIds.add(id);
        return id;
    }

    @AfterEach
    void cleanupOnlyOwnRows() {
        for (String id : ownedIds) {
            repository.findByRequestId(id)
                    .ifPresent(repository::delete);
        }
        repository.flush();
    }

    @Test
    void realTcpPostThenGetPersistsOrder() {
        String requestId = ownedRequestId();

        ResponseEntity<OrderView> created =
                http.postForEntity(
                        "/api/orders",
                        new CreateOrderRequest(
                                requestId, "BOOK-HTTP", 3),
                        OrderView.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        assertThat(created.getHeaders().getLocation())
                .isNotNull();

        OrderView body = Objects.requireNonNull(
                created.getBody());

        assertThat(body.id()).isNotNull();
        assertThat(body.requestId())
                .isEqualTo(requestId);
        assertThat(body.status())
                .isEqualTo(OrderStatus.CREATED);

        ResponseEntity<OrderView> fetched =
                http.getForEntity(
                        "/api/orders/{id}",
                        OrderView.class,
                        body.id());

        assertThat(fetched.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(
                Objects.requireNonNull(fetched.getBody())
                        .requestId())
                .isEqualTo(requestId);

        assertThat(repository.countByRequestId(requestId))
                .isEqualTo(1);
    }

    @Test
    void invalidRealHttpPostYields400WithoutRow() {
        String requestId = ownedRequestId();

        ResponseEntity<String> invalid =
                http.postForEntity(
                        "/api/orders",
                        new CreateOrderRequest(
                                requestId, "", 0),
                        String.class);

        assertThat(invalid.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(repository.countByRequestId(requestId))
                .isZero();
    }
}
```

**2 phương thức `@Test`.** `TestRestTemplate` được auto-configured khi `@SpringBootTest(RANDOM_PORT)` và `spring-web` có mặt, dùng relative URLs theo server port thực. Không hard-code `8080`. `@DirtiesContext(AFTER_CLASS)` để Spring close cả web server, DataSource và PostgreSQL container bean theo lifecycle có chủ đích.

**Không nhầm test server port với database port:** Spring Testcontainers `@ServiceConnection` cung cấp mapped PostgreSQL connection; embedded HTTP server port do Spring Boot random hóa. Cả hai là tài nguyên khác nhau.

## 12. Tổng số test và lệnh thực thi

### 12.1. Bảng số lượng chính xác

| Test class | `@Test` methods | Docker? | Tầng |
| --- | ---: | --- | --- |
| `OrderServiceTest` | 5 | Không | Service unit / Mockito |
| `OrderControllerMvcTest` | 5 | Không | Spring MVC slice |
| `OrderRepositoryPostgresTest` | 2 | Có | JPA + PostgreSQL |
| `OrderFlowMockMvcIT` | 4 | Có | Full context + MockMvc + PostgreSQL |
| `OrderHttpSocketIT` | 2 | Có | Real HTTP + PostgreSQL |
| **Tổng** | **18** | Full suite cần Docker | Một vertical slice, nhiều boundary |

Tên `*IT` đã được thêm vào Surefire includes, vì vậy `mvn test` của project này chạy **tất cả 18 phương thức** theo cấu hình đề xuất. Nếu dùng Maven Failsafe trong dự án production, hãy chuyển `*IT` sang integration-test/verify lifecycle thích hợp và tránh chạy trùng giữa Surefire/Failsafe.

### 12.2. Chạy từng tầng

```bash
java -version
mvn -version

# Chỉ unit service: không Docker
mvn -B -ntp -Dtest=OrderServiceTest test

# MVC slice: không Docker
mvn -B -ntp -Dtest=OrderControllerMvcTest test

# JPA PostgreSQL: cần Docker
docker version
docker info
mvn -B -ntp -Dtest=OrderRepositoryPostgresTest test

# HTTP + DB với MockMvc: cần Docker
mvn -B -ntp -Dtest=OrderFlowMockMvcIT test

# Real TCP HTTP + DB: cần Docker
mvn -B -ntp -Dtest=OrderHttpSocketIT test

# Tất cả 18 test methods:
mvn -B -ntp test
```

**Đây là lệnh để người học tự chạy**, không phải tuyên bố Maven đã được chạy khi tạo README. Output `BUILD SUCCESS`, số lượng contexts, Docker mapped ports và elapsed time phụ thuộc môi trường. Nếu Docker không available, ba lớp integration không được tính là PASS chỉ vì unit/MVC xanh.

### 12.3. Dự kiến log kết quả

Không hard-code số PostgreSQL port hay order IDs. Với full suite được thực thi thành công, mục tiêu logic là:

```text
OrderServiceTest:             5 tests
OrderControllerMvcTest:       5 tests
OrderRepositoryPostgresTest:  2 tests
OrderFlowMockMvcIT:           4 tests
OrderHttpSocketIT:            2 tests
--------------------------------------
Total:                      18 tests
```

Đây là **ma trận test count theo source**, không phải trích xuất báo cáo Surefire đã chạy. Kiểm tra báo cáo thực tại `target/surefire-reports` để kết luận chính xác tests run/skipped/errors/failures.

## 13. Điều gì sẽ fail nếu bỏ từng tầng?

### 13.1. Bỏ Service unit tests

Business logic có thể thay đổi từ `quantity >=1` thành `quantity>=0` mà không bị phát hiện sớm. Unit tests xác định rõ invariants và exception mapping khi repository báo duplicate.

### 13.2. Bỏ MVC slice

Controller có thể dùng sai `@RequestParam` thay vì `@RequestBody`, thiếu `@Valid`, mapping `/api/order` thiếu “s”, hoặc trả status `200` thay vì `201`. Repository tests không biết các lỗi HTTP contract này.

### 13.3. Bỏ JPA slice

Entity `@Column(name="request_id")` có thể bị đổi sai, migration bị lệch, hoặc unique constraint bị bỏ. Mockito service vẫn xanh vì repo giả lập, MVC slice cũng xanh vì service giả.

### 13.4. Bỏ full-context MockMvc

Service + repository thật có thể không được Spring inject đúng, transaction proxy không active, Flyway migration fail, hoặc HTTP call không đi qua những beans mà unit tests giả định. Full context bắt wiring và cross-layer behavior.

### 13.5. Bỏ real HTTP

MockMvc không chứng minh embedded server có thể khởi động, random port được bind, client/server HTTP headers được truyền qua socket. Một số serialization/filter/connector behaviors có thể khác trong environment HTTP thật.

**Tuy nhiên:** Không bắt buộc mỗi API phải có 2 real-HTTP tests. Ở hệ thống lớn, chọn contract-critical journeys làm smoke tests, giữ đa số business edge cases ở unit/slice để CI nhanh.

## 14. Transaction, rollback và dữ liệu test: phần dễ nhầm nhất

### 14.1. `@DataJpaTest` mặc định rollback

Repository test có transaction bao quanh mỗi method, nên rows tạo trong method thường rollback sau đó. Dù rollback, **PostgreSQL identity sequence không đảm bảo quay về giá trị ban đầu**. Không assert ID cố định.

### 14.2. `@SpringBootTest + @AutoConfigureMockMvc` không tự rollback

Một `@SpringBootTest` mặc định không thêm `@Transactional`. Service `@Transactional` tạo/commit transaction theo invocation. Đây là điều ta muốn khi assert POST sau đó GET đọc row. Nếu gắn `@Transactional` vào integration test, service có thể tham gia test-managed transaction và row rollback ở cuối; test có thể xanh khi logic commit thực tế chưa được chứng minh.

### 14.3. `RANDOM_PORT`: HTTP client và server khác thread

Với server thật, HTTP client test và application server chạy thread khác nhau, nên một `@Transactional` trên test method **không** rollback DB writes do server thread. Cleanup phải dùng IDs/namespace riêng, không phụ thuộc test rollback.

### 14.4. Tránh global cleanup

Anti-pattern:

```java
@AfterEach
void resetEverything() {
    repository.deleteAll();
}
```

Nếu hai test classes/forks dùng chung database, `deleteAll` xóa rows của test khác và tạo flaky failures. Dùng requestId UUID riêng, xóa đúng rows mình tạo. Nếu cần reset toàn schema, sở hữu **database/schema riêng cho worker** và không làm trên shared DB.

### 14.5. Đừng dùng `@DirtiesContext` để dọn rows

`@DirtiesContext` đánh dấu context dirty, làm Spring đóng/recreate beans, **không** tự xóa rows đã commit ở PostgreSQL shared. Trong sample, annotation đóng context/container ở cuối class; `@AfterEach` dọn test-owned records.

### 14.6. Exception trong transaction PostgreSQL

Khi unique violation xảy ra, transaction thường vào trạng thái aborted cho đến rollback. Đừng catch rồi tiếp tục query trong **cùng** transaction với `saveAndFlush` đã fail. Service ném `OrderConflictException` để transaction rollback. Test JPA constraint dừng sau assertion exception; Spring rollback kết thúc lifecycle.

## 15. Phân biệt validation, business rule và database constraint

### 15.1. Bean Validation là HTTP boundary

`@NotBlank`/`@NotNull`/`@Min`/`@Max` trên DTO được kích hoạt ở controller bằng `@Valid`. MVC test invalid input kiểm tra `400` và không gọi service.

### 15.2. Service invariants không chỉ dựa vào HTTP

Nếu có scheduler, message listener hoặc một service khác gọi `OrderService.create(...)`, những callers đó không nhất thiết đi qua MVC Bean Validation. Vì vậy service kiểm tra các invariants cốt lõi. Unit test invalid quantity chứng minh repository không bị gọi.

### 15.3. DB constraint là ranh giới cuối

Một API chỉ check `exists` rồi insert không atomic trước concurrent requests. PostgreSQL unique key đảm bảo không có hai rows cùng requestId ngay cả khi application races. JPA slice test chứng minh unique constraint real, unit service test chứng minh nhánh mapping known DB exception.

### 15.4. Không dùng message text để phân loại lỗi SQL

Hibernate `ConstraintViolationException.getConstraintName()` có thể cung cấp tên constraint, nhưng DB drivers/vendor không phải lúc nào cũng report tên. Nếu project chạy nhiều DB, xem root SQLSTATE và constraint-specific metadata theo driver. Không parse `SQLException.getMessage()` dựa vào chữ “duplicate key” vì localization/version thay đổi.

### 15.5. 409 không bằng idempotency

Trong lab, POST lần hai cùng requestId trả 409. Nếu yêu cầu thật là **idempotent retry** (POST với cùng key và cùng payload phải trả cùng kết quả), cần thêm:

- Lưu request hash/payload canonical.
- Khi key trùng, so sánh payload, quyết định replay result hay 409 khi khác nội dung.
- Database locking hoặc upsert/transaction policy cho request races.
- Test retry/concurrent clients và failure sau commit trước HTTP response.

Không suy rằng unique constraint đã triển khai đầy đủ idempotency.

## 16. Điều tra lỗi theo tầng

| Triệu chứng | Tầng nên kiểm tra đầu | Công cụ |
| --- | --- | --- |
| Unit service trả sai status | Business | Mockito, captured entity |
| MVC 400 khi JSON hợp lệ | Controller/DTO | MockMvc, Bean Validation logs |
| MVC status 200 thay vì 201 | Controller | MockMvc status/header |
| MVC 409 trả 500 | ExceptionHandler / mapping | MockMvc ProblemDetail |
| `@WebMvcTest` fail vì thiếu Service bean | Slice dependency | `@MockitoBean` |
| `@DataJpaTest` dùng H2 ngoài ý muốn | Test DB replacement | `@AutoConfigureTestDatabase` |
| Flyway “Unsupported Database” | Flyway PostgreSQL module | Maven dependency tree |
| Hibernate `Schema-validation: missing table` | Migration chưa chạy hoặc sai DB | Flyway history, connection details |
| JPA mapping lỗi cột `request_id` | Entity/schema drift | Repository PostgreSQL test |
| Duplicate rows được tạo | DB unique constraint thiếu | Flyway migration/constraint |
| Unit conflict PASS nhưng full flow 500 | Constraint name/translation khác thật | SQLSTATE, Hibernate cause chain |
| Test chỉ xanh khi chạy cùng class khác | Fixture/setup leak | Unique IDs, independent setup |
| Order ID khác 1 | Identity/sequence behavior bình thường | Assert ID non-null/positive |
| `RANDOM_PORT` refused connection | Server startup/port/runner | Spring logs, TestRestTemplate |
| HTTP client GET không thấy POST | Transaction commit/persistence | Full flow repo query |
| Test treo khi Docker thiếu | Container runtime/CI | Docker preflight; env failure |
| `Connection refused` sau class khác | Stopped container/context cache mismatch | Spring-managed container lifecycle |
| Maven chỉ chạy 10 tests | Surefire `*IT` chưa include | POM includes, surefire-reports |

### 16.1. Khi một test thất bại

1. Lưu **root cause stacktrace**, requestId của test và test class/method.
2. Xác minh test có thực sự chạy không (không SKIPPED).
3. Xác nhận Docker/container ready khi test cần PostgreSQL.
4. Xác nhận Spring profile/property, datasource mapped host/port từ `@ServiceConnection`.
5. Kiểm tra Flyway migration/schema validation.
6. Nếu HTTP 400, xem request contentType/JSON field names/Bean Validation trước khi debug repository.
7. Nếu 500 từ duplicate, kiểm tra SQL violation root cause/constraint name; không chuyển mọi DataIntegrityViolation thành 409.
8. Chạy lại test đơn lẻ rồi chạy cả suite; nếu fail chỉ khi chạy cùng, kiểm tra shared state/cleanup.
9. Không chữa flaky test bằng `Thread.sleep`/tăng timeout vô hạn.
10. Không bỏ test integration mandatory chỉ để build xanh.

## 17. CI/CD cho bộ test này

### 17.1. Phân nhóm nhanh/chậm

- **Fast checks (10 tests):** `OrderServiceTest` (5) + `OrderControllerMvcTest` (5); không Docker, có thể dùng làm pre-commit/fast feedback.
- **Database/integration (8 tests):** `OrderRepositoryPostgresTest` (2), `OrderFlowMockMvcIT` (4), `OrderHttpSocketIT` (2); cần Docker và PostgreSQL image.

Với một repo lớn, tách Maven Surefire/Failsafe hoặc CI jobs theo profile test groups để tối ưu thời gian; **không** coi group không chạy là PASS. Bài này dùng một Surefire configuration include mọi file để `mvn test` chạy toàn bộ.

### 17.2. GitHub Actions minh họa

```yaml
name: Orders Vertical Slice Tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker runtime
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run service, MVC, JPA and integration tests
        run: mvn -B -ntp test
      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: orders-surefire-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
```

Docker daemon phải truy cập được và có quyền start container. Đây là workflow minh họa, **không khẳng định đã chạy**. Không dùng production database URL/credentials trong test. Không cấp privileged Docker socket cho untrusted build nếu không có isolation policy.

### 17.3. Resource budget

Ba lớp có contexts khác nhau có thể start ba PostgreSQL containers nối tiếp. Ở CI có CPU/RAM yếu, container boot/migrations có thể tốn thời gian; đo performance thật trước khi tăng parallelism. Nếu gộp containers/suite-wide singleton để giảm runtime, đảm bảo Spring context cache lifecycle và data isolation, không để các classes cleanup database của nhau.

### 17.4. Chạy song song

Không bật parallel methods ở các full-context/DB tests trong sample. Khi bật cần:

- Mỗi test data row có requestId riêng.
- Không `deleteAll` hoặc `TRUNCATE` trên DB shared.
- Không stop Spring-managed container khi class khác vẫn dùng cached context.
- `@DirtiesContext` cần được cân nhắc khi classes concurrent.
- Database pool limits phù hợp fork count.
- JUnit `@ResourceLock` không khóa resource xuyên Surefire JVM forks/CI jobs; nếu dùng cùng DB phải có external namespace/schema/run isolation.

## 18. Mở rộng tình huống thực tế

### 18.1. Thêm GET list/search

Khi API mở rộng `GET /api/orders?sku=...`, test phân trang, sort ổn định, filter theo tenant, empty result và SQL performance. Đừng assert toàn bảng nếu có test data của nhóm khác.

### 18.2. Thêm update/cancel order

Thêm trạng thái chuyển `CREATED -> CANCELLED`, test illegal transitions và optimistic locking (`@Version`), HTTP 409 khi concurrent updates. Một unit test state machine là cần nhưng không thay PostgreSQL integration cho lock/transaction.

### 18.3. Thêm thanh toán hoặc phát event

Nếu service gửi Kafka/Rabbit messages hoặc gọi Payment API, hãy có test cho outbox/rollback/idempotency, dùng Testcontainers broker và HTTP stub riêng. Không gắn real payment sandbox vào unit tests.

### 18.4. Thêm security

Nếu có Spring Security, `@WebMvcTest` có thể load security filters; dùng `spring-security-test` và `@WithMockUser`/MockMvc request post processors, kiểm tra 401/403 và authorization boundary. Không tắt filters chỉ để 201 test xanh nếu security là một phần production contract.

### 18.5. Thêm HTTP contract docs

Dùng Spring REST Docs/OpenAPI contract tests để bảo vệ schema và headers. Tránh snapshot toàn bộ lỗi JSON nếu chứa timestamps/trace IDs không ổn định.

### 18.6. Thêm concurrency/idempotency real test

Tạo hai requests với cùng requestId thực sự **đồng thời** (barrier/latch), kiểm tra một 201 và một 409, database còn một row; chạy nhiều iterations có giới hạn, không phụ thuộc `Thread.sleep`. Khi test concurrency, dùng **hai transactions/threads độc lập**, không cùng test-managed transaction, và kiểm soát cleanup theo ID.

### 18.7. Thêm failure/recovery

Mô phỏng DB outage/network errors để đảm bảo ứng dụng trả lỗi có kiểm soát. Không chuyển mọi `DataIntegrityViolationException` hay `DataAccessException` thành 409; đó là phân loại sai. Với timeout/retry, quan sát committed side effects/duplicate risk.

## 19. Bài tập luyện tập

1. Chạy riêng `OrderServiceTest` và giải thích vì sao không có PostgreSQL/Docker.
2. Cố tình bỏ check `quantity < 1` trong service, xem unit test nào phát hiện.
3. Cố tình bỏ `@Valid` trên controller, chạy MVC slice và quan sát invalid payload có thể đi đến service mock.
4. Đổi `ResponseEntity.created(...)` thành `ok(...)`, xem test status/header nào fail.
5. Bỏ `@MockitoBean` trong `OrderControllerMvcTest`, giải thích vì sao MVC slice thiếu collaborator.
6. Đổi tên JSON field `requestId` thành `request_id` mà không cấu hình Jackson, quan sát request binding/validation.
7. Bỏ unique constraint trong migration rồi chạy PostgreSQL repo test trên database mới. Không sửa schema của production/shared DB.
8. Thay `@AutoConfigureTestDatabase(replace=NONE)` bằng default và thêm H2 test dependency: xác nhận database nào thực sự được dùng.
9. Bỏ `spring.jpa.hibernate.ddl-auto=validate`, giải thích nguy cơ entity/schema drift.
10. Đặt `@Transactional` trên full MockMvc test rồi đánh giá liệu POST→GET có chứng minh commit ngoài test transaction hay không.
11. Tạo một requestId cố định trong hai test classes, chạy parallel và quan sát trùng fixture; sửa bằng UUID + scoped cleanup.
12. Chạy `OrderHttpSocketIT` với RANDOM_PORT, đối chiếu với MockMvc test: server nào thực sự lắng nghe TCP?
13. Thêm một `@ExceptionHandler` map tất cả database errors sang 409; chỉ ra vì sao outage sẽ bị báo sai.
14. Mở rộng API `GET /api/orders/{id}` với path ID không parse được; test 400 và không gọi repository.
15. Thêm test quantity=21 và quantity missing/null ở MVC slice; bảo đảm 400.
16. Cài một CI job chỉ chạy unit/MVC và job khác chạy 8 integration tests; báo rõ skipped/env failures.
17. Bổ sung contract verification cho `Location` theo ID trả về thay vì hard-code ID 1.
18. Thử Testcontainers DB image version khác trong branch, xem Flyway/Hibernate mapping test nào bắt regressions.

## 20. Câu hỏi tự kiểm tra

**1.** Unit test Mockito chứng minh Postgres unique constraint hoạt động không?  
**Không.** Vì repository là mock; cần JPA/PostgreSQL integration test.

**2.** `@WebMvcTest` có tạo real TCP server không?  
**Không.** MockMvc làm việc với mock servlet environment.

**3.** `@SpringBootTest + @AutoConfigureMockMvc` có thể gọi service và database thật không?  
**Có**, nếu không mock những beans đó và context có real DataSource.

**4.** `RANDOM_PORT` khác MOCK ở đâu?  
**RANDOM_PORT** khởi động embedded server nhận HTTP thật, **MOCK** không.

**5.** `@DataJpaTest` có mặc định rollback?  
**Có**, test-managed transaction thường rollback sau method.

**6.** `@Transactional` trên test method có rollback HTTP server thread không?  
**Không tự động**, server thread có transaction riêng.

**7.** Vì sao cần Flyway trong integration test?  
Để kiểm tra schema/migrations cùng ranh giới production, không để Hibernate tự tạo schema tùy ý.

**8.** Vì sao cần `@AutoConfigureTestDatabase(replace=NONE)`?  
Để tránh JPA slice dùng embedded DB thay Postgres Testcontainer ngoài ý muốn.

**9.** Check duplicate `existsByRequestId` có chống mọi race không?  
**Không**, cần unique constraint DB.

**10.** Vì sao dùng `saveAndFlush` thay `save` khi test unique violation?  
Để SQL/constraint được kiểm tra trước khi rời service method.

**11.** Nếu count toàn bảng lớn hơn 1 có chắc test thất bại không?  
Không. Data khác có thể tồn tại; assert theo test-owned requestId.

**12.** `@DirtiesContext` có tự xóa Postgres committed rows không?  
Không; context/container lifecycle khác data cleanup.

**13.** `@Mock` của Mockito có thay bean trong `@WebMvcTest` không?  
Không; dùng Spring `@MockitoBean`.

**14.** Khi lỗi Flyway “Unsupported Database PostgreSQL” cần xem gì?  
Dependency PostgreSQL-specific Flyway module/version.

**15.** Vì sao Surefire phải include `*IT.java` ở sample?  
Để `mvn test` không bỏ qua integration classes theo naming convention.

**16.** Bộ source này gồm bao nhiêu `@Test` methods?  
**18:** 5 unit service + 5 MVC + 2 JPA + 4 full MockMvc + 2 HTTP TCP.

## 21. Checklist review trước khi merge

- [ ] Bài toán/contract HTTP status, headers, JSON và DB invariants được ghi rõ.
- [ ] Unit service tests không kéo Spring/Docker không cần thiết.
- [ ] MVC slice dùng `@MockitoBean` đúng bean và `@Valid` cho DTO.
- [ ] 201 kiểm tra Location/ID/response body, không chỉ success status.
- [ ] 400 có assertion service chưa gọi hoặc DB chưa ghi.
- [ ] 404/409 dùng domain exceptions và HTTP advice test.
- [ ] JPA slice dùng **PostgreSQL thật**, không H2 implicit.
- [ ] Flyway migration được chạy trước Hibernate validate.
- [ ] Unique requestId nằm ở DB constraint, không chỉ check trước insert.
- [ ] Constraint violation chỉ được map 409 khi đúng requestId key.
- [ ] Full MockMvc không mock service/repository business.
- [ ] Full flow kiểm tra POST→GET và DB row còn sau service commit.
- [ ] Real HTTP test dùng RANDOM_PORT và TestRestTemplate, không fixed port.
- [ ] Test methods không phụ thuộc thứ tự, ID do database tạo không hard-code.
- [ ] Mọi row fixture có unique requestId và scoped cleanup.
- [ ] Không dùng global deleteAll/TRUNCATE trên database shared.
- [ ] Không dùng `@Transactional` test client để ngụy trang DB commit.
- [ ] Testcontainers managed bean lifetime khớp Spring context cache.
- [ ] Surefire include `*IT.java`, total test count chính xác.
- [ ] Docker environment fail được tách khỏi business test failures.
- [ ] CI không dùng production secrets, tránh container cleanup toàn host.
- [ ] Logs/test reports được dùng để chẩn đoán, không bịa `BUILD SUCCESS`.
- [ ] Tests đủ nhanh ở unit/slice và đủ thực ở integration boundary.

## 22. Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest`, `@AutoConfigureMockMvc`, `RANDOM_PORT` và TestRestTemplate.
- [Spring Boot 3.5 — Test Slice Auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): Flyway/JPA/MockMvc/ServiceConnection auto-configurations trong từng slice.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): Spring-managed container bean, `@ServiceConnection`, lifecycle và context cache.
- [Spring Boot 3.5 — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): Flyway migrations, database-specific modules, PostgreSQL.
- [Spring Framework 6.2 — @MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): Spring bean overrides cho slice/context tests.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed transaction và rollback boundaries.
- [Spring Framework 6.2 — MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): servlet request/response assertions.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): derived queries và JpaRepository.
- [Hibernate ORM 6.6 — ConstraintViolationException](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/exception/ConstraintViolationException.html): constraint name và SQL failure causes.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL real backend trong tests.
- [JUnit Jupiter 5.12 — User Guide](https://docs.junit.org/5.12.0/user-guide/): independent tests và lifecycle callbacks.
- [Maven Surefire — Inclusion/Exclusion](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html): naming conventions và `*IT` includes.
- [Spring Boot 3.5 — Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Flyway/PostgreSQL/JUnit/Mockito/Testcontainers versions qua BOM.

**Kết luận:** Một bộ kiểm thử đáng tin cho feature Spring Boot phải có cả *độ sâu* lẫn *độ thực*: Unit service cô lập quy tắc, MVC slice bảo vệ contract JSON/HTTP, JPA slice bắt mapping và constraint trên PostgreSQL, full-context MockMvc chứng minh tích hợp Spring→Service→DB, và một số tests RANDOM_PORT chứng minh HTTP TCP thật. Dữ liệu phải được cleanup theo owner, transaction boundaries phải được hiểu đúng và CI phải đếm đầy đủ 18 tests, không biến tests chưa chạy thành PASS.