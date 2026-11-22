# Kiểm thử cùng nghiệp vụ qua @SpringBootTest với RANDOM_PORT

Khi một controller trả `201 Created` trong test gọi trực tiếp Java method hoặc `MockMvc`, ta mới chứng minh **một phần** đường đi của request. Để xác nhận **nghiệp vụ thực sự vận hành khi ứng dụng mở cổng HTTP**, Spring Boot cung cấp `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`. Annotation này khởi tạo một `ApplicationContext` gần với ứng dụng thật, chạy embedded web server ở **cổng TCP được chọn động**, cho phép test thực hiện một request HTTP qua serialization, servlet filters, mapping, validation, controller, service, JDBC và sau đó nhận response HTTP thực.

Bài thuộc nhóm **Thực hành tích hợp** của **Spring Boot - testing**, tập trung đề bài **“Kiểm thử cùng nghiệp vụ qua @SpringBootTest với RANDOM_PORT”**. Ta dùng **một nghiệp vụ tạo đơn hàng** để so sánh kiểm thử pure Java của bảng giá với test service trực tiếp và test qua HTTP thật. Bộ project **Java 17 + Spring Boot 3.5.0 + Spring MVC + Bean Validation + JDBC/H2 + JUnit Jupiter** có thể dựng từ các file dưới đây, không cần Docker hay dịch vụ bên ngoài. API có cả thành công lẫn lỗi `400/404/409/422`; test đọc database sau response để xác nhận server transaction đã commit và cleanup bằng test-owned request keys.

**Điểm phân biệt phải nhớ:**
- `RANDOM_PORT` là **real web server**, không phải mock request dispatcher.
- `TestRestTemplate` gửi **real HTTP**; nó không mặc định ném exception cho response `4xx/5xx`, nên phải assert `status code`/body.
- Client test và server chạy trên **hai thread/transaction boundary khác nhau**; `@Transactional` trên test không tự rollback writes do HTTP endpoint đã commit.
- `@LocalServerPort` chỉ chứa actual port **sau khi web server khởi động**, không phải một fixed port tự chọn.
- Chạy trong một JVM với embedded server **chưa phải** E2E qua ingress, TLS, API gateway, load balancer hay môi trường production.

## 1. Chọn mức kiểm thử theo bằng chứng cần thu được

| Mức | Cách chạy | Kiểm được | Không kiểm được |
|---|---|---|---|
| Pure unit | `new PricingPolicy()` + JUnit | Bảng giá, ràng buộc tham số, exception của domain | Spring wiring, HTTP, JSON, JDBC |
| Service integration | `@SpringBootTest` + gọi `OrderService` trực tiếp | Bean wiring, `@Transactional`, repository, H2 data | HTTP contract, serialization, web filters, network socket |
| Controller/mock | `@WebMvcTest` + `MockMvc` | Mapping, validation, exception advice, serialized response theo MVC mock | Embedded TCP server, servlet container/network behavior; service/repo thường mock |
| Full Spring + MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Service/repository thật + MVC stack trong JVM | Real client/server TCP exchange, container-level error page |
| Full Spring + real HTTP | **`@SpringBootTest(RANDOM_PORT)`** + `TestRestTemplate` | TCP listener, HTTP status/headers, JSON, validation, controller → service → JDBC commit | Ingress/proxy/TLS/network ACL/cloud resources nếu không cấu hình |
| Deployment/E2E | Ứng dụng deployed + real client | Cổng/routes/proxy/TLS/auth và dependencies đã deploy | Có thể khó ổn định và cô lập dữ liệu hơn |

### 1.1. Bốn giá trị `webEnvironment`

Spring Boot 3.5 có:

- `MOCK` (**mặc định**): tạo mock servlet/web context khi Spring MVC có trên classpath, không mở TCP listener. Kết hợp `@AutoConfigureMockMvc` để thực thi HTTP-like requests bên trong MVC stack.
- `RANDOM_PORT`: khởi tạo embedded server thật và bind một **port động** (hiệu quả tương đương yêu cầu `server.port=0` đối với web server chính).
- `DEFINED_PORT`: chạy server thật trên `server.port` đã cấu hình, hoặc port mặc định 8080; dễ collision trên CI nên chỉ dùng khi cần kiểm một cổng đã định.
- `NONE`: khởi động Spring application context nhưng không dựng web environment.

**Không nhầm cổng ngẫu nhiên với “mỗi @Test có một server mới”:** TestContext có thể cache và chia sẻ ApplicationContext giữa nhiều test methods/classes cùng cấu hình. Cổng có thể **giữ nguyên trong các methods dùng chung context**, và thay đổi khi context bị recreate hoặc JVM khác chạy. Không assert rằng hai methods phải nhận hai cổng khác nhau.

### 1.2. Mô hình thực thi của test ở bài này

```text
JUnit Jupiter, test JVM
  |
  +-- @SpringBootTest(webEnvironment=RANDOM_PORT)
  |        |
  |        v
  |   SpringApplication -> ApplicationContext
  |        |
  |        +--> Embedded Tomcat binds ephemeral TCP port
  |        +--> DispatcherServlet, Jackson, Validator
  |        +--> OrderController, OrderService, PricingPolicy
  |        +--> JdbcTemplate -> isolated H2
  |
  +-- @Autowired TestRestTemplate
  |        |
  |        +-- POST /api/orders (real TCP -> server thread)
  |        |        |
  |        |        +-- HTTP 201 + Location + JSON receipt
  |        |
  |        +-- GET /api/orders/{id}
  |                 |
  |                 +-- HTTP 200 / 404
  |
  +-- @Autowired JdbcTemplate (test thread)
           |
           +-- verify server-committed row
           +-- delete rows by OWN request_key in @AfterEach
```

Với API này, một test có thể kiểm **cùng invariant tính tiền** từ `PricingPolicy` thuần Java tới HTTP response và row database. Điều này bổ sung bằng chứng ở từng ranh giới, không có nghĩa phải viết cùng một assertion trùng lặp vô ích ở mọi test.

## 2. Điều gì thực sự được test qua RANDOM_PORT?

Một request `POST` đi qua:

1. `TestRestTemplate` serialize `CreateOrderRequest` thành JSON và gửi HTTP tới `http://localhost:<random-port>`.
2. Servlet container nhận request qua socket, chuyển cho `DispatcherServlet`.
3. Spring MVC tìm `@PostMapping("/api/orders")`, dùng Jackson đọc JSON, dùng Jakarta Bean Validation vì parameter `@Valid`.
4. `OrderController` gọi **bean `OrderService` thật** (không thay bằng Mockito).
5. `OrderService` gọi `PricingPolicy` và `OrderStore`, tạo transaction qua Spring AOP `@Transactional`.
6. `JdbcTemplate` ghi row vào H2, transaction server commit sau service method thành công.
7. Controller trả `ResponseEntity.created(location).body(receipt)`; Jackson tạo JSON.
8. Client nhận **HTTP status, Location header và JSON body** để assert.
9. Test đọc H2 row qua `JdbcTemplate` và xóa theo `request_key` riêng.

Lỗi ở bất cứ lớp nào có thể làm test fail: thiếu `@RestController`, `@Valid` không được kích hoạt, JSON field mismatch, DI thiếu bean, constraint DB sai, exception advice sai HTTP status hoặc server không bind port.

### 2.1. Tại sao TestRestTemplate tiện hơn RestTemplate thuần trong test?

Với `RANDOM_PORT`, Spring Boot 3.5 auto-configure `TestRestTemplate` dùng root URI trỏ vào server vừa khởi động. Vì vậy:

```java
@Autowired TestRestTemplate client;

ResponseEntity<String> response =
        client.getForEntity("/api/orders/missing", String.class);
```

không cần tự ghép port cho phần lớn requests. Đây là snippet giả định class test có `@SpringBootTest(RANDOM_PORT)`; code đầy đủ ở phần 6.

**Khác RestTemplate thông thường:** `TestRestTemplate` được thiết kế cho kiểm thử và **không throw mặc định với `4xx/5xx`**. Nếu bạn gọi API thiếu dữ liệu, nhận `ResponseEntity` rồi assert `isBadRequest()`/`isNotFound()` thay vì chỉ chờ catch `HttpClientErrorException`. Điều này làm negative tests dễ viết, nhưng cũng có nghĩa một test chỉ gọi API mà không assert response có thể **xanh sai**.

### 2.2. @LocalServerPort dùng khi nào?

`@LocalServerPort` (Boot 3.5: `org.springframework.boot.test.web.server.LocalServerPort`) inject actual listening port:

```java
@LocalServerPort
private int port;
```

Dùng khi bạn cần:
- Gửi request bằng client không được Boot cấu hình root URI, ví dụ JDK `HttpClient`.
- Xây callback URL cho một fake client và inject vào test code.
- Kiểm tuyệt đối request đi đến listener chính mà không trỏ nhầm một external host.
- Debug mismatch base path/proxy của test environment.

**Không** dùng giá trị field này trong static initializer hoặc quá sớm khi Spring context chưa chạy. Tránh đặt server port là `8080` trong test; RANDOM_PORT giảm collision khi nhiều Maven forks/CI jobs trên cùng host.

### 2.3. TestRestTemplate, WebTestClient và RestClient khác nhau

- `TestRestTemplate` là tiện ích của **Spring Boot test** phù hợp Spring MVC, không cần thêm WebFlux; được auto-configure trong `RANDOM_PORT`.
- `WebTestClient` có API fluent cho response assertions và cũng có thể gắn vào real server, nhưng setup Boot 3.5 cần `spring-webflux` trên classpath để tiện ích này khả dụng theo docs. Chỉ thêm WebFlux vào test nếu có lý do; không vô tình đổi application type.
- `RestClient` (Spring Framework) là synchronous production HTTP client, có thể xây base URL bằng port của server. Nó không tự thay thế các tiện ích assertions của test.
- `MockMvc` là mock request dispatcher; dùng cùng `@SpringBootTest` để test MVC nội bộ, **không tự biến thành real TCP request** chỉ vì context dùng RANDOM_PORT.
- `TestRestTemplate.withBasicAuth(...)` có thể dùng cho secured endpoints, nhưng mẫu không bật Spring Security để giữ trọng tâm vào một business contract. Trong hệ thực, cần test quyền truy cập thay vì disable filters cho nhanh.

## 3. Contract nghiệp vụ duy nhất dùng xuyên suốt bài

Ví dụ là API **đặt đơn hàng cho hai mã sản phẩm**:

| Mã `sku` | Đơn giá VND | Quy tắc |
|---|---:|---|
| `BOOK` | 120.000 | Số lượng từ 1 đến 10 |
| `PEN` | 20.000 | Số lượng từ 1 đến 10 |
| Mã khác | Không hỗ trợ | HTTP **422** |

Request JSON:

```json
{
  "requestKey": "run-001",
  "sku": "BOOK",
  "quantity": 2
}
```

Thành công: `POST /api/orders` → `201 Created` + `Location: /api/orders/<id>` + body chứa `id`, `requestKey`, `sku`, `quantity`, `totalPriceVnd = 240000`. `GET /api/orders/{id}` → `200 OK` + body giống record đã lưu. Bảng có constraint **UNIQUE(request_key)** để client gửi lại cùng request key sẽ nhận **409 Conflict**. Đây là **chính sách demo duplicate rejection**, không phải idempotent replay theo chuẩn; nếu API thực muốn idempotency, có thể trả lại response cũ cho cùng key và cần lưu request fingerprint/outcome.

Trường hợp lỗi:

| Case | Status kỳ vọng | Mã JSON lỗi |
|---|---:|---|
| `requestKey` rỗng/blank | 400 | `INVALID_INPUT` |
| `sku` null/blank | 400 | `INVALID_INPUT` |
| `quantity = 0` hoặc `11` | 400 | `INVALID_INPUT` |
| JSON hỏng hoặc body rỗng | 400 | `MALFORMED_JSON` |
| `sku = "UNKNOWN"` | 422 | `UNKNOWN_SKU` |
| `GET` ID không tồn tại | 404 | `ORDER_NOT_FOUND` |
| Cùng `requestKey` được dùng lần nữa | 409 | `DUPLICATE_REQUEST` |

**Giới hạn dữ liệu test:** Không gọi database ngoài. Mỗi test tạo request key có UUID, sau đó xóa rows theo key trong `@AfterEach`. Mỗi lần khởi tạo Spring context sử dụng H2 in-memory và table chỉ phục vụ test.

### 3.1. Vì sao không có output ID cố định?

Mỗi đơn có `UUID.randomUUID()` nên giá trị `id` không thể dự đoán trước. Test assert **không blank**, Location có path chứa ID vừa trả và GET đúng cùng ID. Không hardcode một UUID rồi assert response == một chuỗi tĩnh; đó là một trong các nguyên nhân khiến suite dễ trùng fixture khi chạy nhiều lần.

### 3.2. Kiểm nghiệp vụ và HTTP contract riêng nhưng liên kết

- **PricingPolicy unit test:** `BOOK x 2 = 240000`, quantity invalid thì throw, SKU lạ thì throw.
- **OrderService direct call:** cùng policy, store vào H2, transaction hoạt động trong test thread.
- **Real HTTP POST:** cùng service code path nhưng đi qua JSON, validation, routing và server thread. So sánh total/invariants với direct service.
- **Real HTTP GET:** xác minh response đọc từ row đã lưu chứ không chỉ echo request trong controller.
- **JDBC readback:** xác nhận HTTP write đã commit và có thể đọc từ một connection khác sau response.

Đối chiếu “cùng nghiệp vụ” nên là **cùng invariants và các nhánh lỗi có giá trị**, không copy test y nguyên qua nhiều tầng để tạo số lượng test ảo.

## 4. Dự án runnable Java 17 + Spring Boot 3.5

Cây thư mục:

```text
random-port-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/orders/
    │       ├── OrdersApplication.java
    │       ├── PricingPolicy.java
    │       ├── UnknownSkuException.java
    │       ├── OrderNotFoundException.java
    │       ├── CreateOrderRequest.java
    │       ├── OrderReceipt.java
    │       ├── ApiError.java
    │       ├── OrderStore.java
    │       ├── OrderService.java
    │       ├── OrderController.java
    │       └── OrderExceptionAdvice.java
    └── test/
        ├── java/com/example/orders/
        │   ├── PricingPolicyTest.java
        │   └── OrderApiRandomPortTest.java
        └── resources/
            ├── application-test.properties
            └── schema.sql
```

Không yêu cầu `src/main/resources/application.properties`. Chỉ test class kích hoạt profile `test`; H2 nằm trong **test dependencies**. Khi muốn chạy application theo production configuration, phải cung cấp DataSource/DB thật trong **một môi trường được phép**, không dùng lệnh khởi động demo để kết nối hệ thống thật.

### 4.1. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>random-port-order-demo</artifactId>
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
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot parent quản lý versions tương thích của Spring MVC, TestContext, Jackson, H2, Hibernate Validator, HikariCP và JUnit 5. `spring-boot-starter-validation` là dependency quan trọng: nếu thiếu Bean Validation provider, `@NotBlank`/`@Min` có thể không được thực thi như kỳ vọng. `spring-boot-starter-test` đưa vào `TestRestTemplate`/Jupiter/AssertJ. H2 `test` scope tránh đưa DB in-memory driver vào production artifact.

### 4.2. Boot application

File **`src/main/java/com/example/orders/OrdersApplication.java`**:

```java
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

Tất cả code và tests ở package `com.example.orders`, nên Spring Boot tìm `@SpringBootApplication` và component scan các controller/service/repository. Test dùng `RANDOM_PORT` sẽ khởi tạo real Tomcat mặc định của `spring-boot-starter-web`.

### 4.3. Chính sách giá thuần Java

File **`src/main/java/com/example/orders/PricingPolicy.java`**:

```java
package com.example.orders;

import org.springframework.stereotype.Component;

@Component
public class PricingPolicy {

    public long totalFor(String sku, int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException(
                    "Quantity must be 1..10");
        }
        if (sku == null) {
            throw new UnknownSkuException();
        }

        long unitPrice = switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new UnknownSkuException();
        };

        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

**Thống nhất source of truth:** controller và service không tự tính lại tiền; mọi đường tạo đơn gọi `PricingPolicy.totalFor(...)`. Unit tests có thể instantiate trực tiếp `new PricingPolicy()` để kiểm quy tắc không cần khởi động Spring. `Math.multiplyExact` an toàn với nguy cơ overflow nếu miền giá sau này mở rộng; test version này chỉ có giá nhỏ.

File **`src/main/java/com/example/orders/UnknownSkuException.java`**:

```java
package com.example.orders;

public class UnknownSkuException extends RuntimeException {
    public UnknownSkuException() {
        super("SKU is not supported");
    }
}
```

File **`src/main/java/com/example/orders/OrderNotFoundException.java`**:

```java
package com.example.orders;

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException() {
        super("Order not found");
    }
}
```

Không đưa giá trị SKU, requestKey hoặc ID nhạy cảm vào messages công khai. API advice sẽ trả mã lỗi ổn định và thông báo tổng quát.

### 4.4. Request/response records

File **`src/main/java/com/example/orders/CreateOrderRequest.java`**:

```java
package com.example.orders;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank @Size(max = 64) String requestKey,
        @NotBlank String sku,
        @Min(1) @Max(10) int quantity) {
}
```

File **`src/main/java/com/example/orders/OrderReceipt.java`**:

```java
package com.example.orders;

public record OrderReceipt(
        String id,
        String requestKey,
        String sku,
        int quantity,
        long totalPriceVnd) {
}
```

File **`src/main/java/com/example/orders/ApiError.java`**:

```java
package com.example.orders;

public record ApiError(
        String code,
        String message) {
}
```

Java 17 records có JSON serialization/deserialization hỗ trợ bởi Jackson trong Spring Boot 3.5. `CreateOrderRequest` mang Bean Validation annotations; khi controller nhận `@Valid @RequestBody`, requestKey/sku blank hoặc quantity ngoài 1..10 gây `MethodArgumentNotValidException` → response 400 theo advice.

**Đừng nhầm DTO validation và domain invariant:** nếu một service khác gọi `PricingPolicy` trực tiếp, `@Valid` trên controller sẽ không chạy. `PricingPolicy` vẫn kiểm quantity và SKU vì đó là quy tắc nghiệp vụ; test thuần Java kiểm riêng. Một API production còn nên giới hạn độ dài `sku`/request body size, normalize/canonicalize identifiers khi contract yêu cầu, và có authorization phù hợp.

### 4.5. JDBC repository

File **`src/main/java/com/example/orders/OrderStore.java`**:

```java
package com.example.orders;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OrderReceipt receipt) {
        jdbc.update("""
                INSERT INTO purchase_order
                    (order_id, request_key, sku,
                     quantity, total_price_vnd)
                VALUES (?, ?, ?, ?, ?)
                """,
                receipt.id(),
                receipt.requestKey(),
                receipt.sku(),
                receipt.quantity(),
                receipt.totalPriceVnd());
    }

    public Optional<OrderReceipt> findById(String id) {
        List<OrderReceipt> rows = jdbc.query("""
                SELECT order_id, request_key, sku,
                       quantity, total_price_vnd
                FROM purchase_order
                WHERE order_id = ?
                """,
                (rs, index) -> new OrderReceipt(
                        rs.getString("order_id"),
                        rs.getString("request_key"),
                        rs.getString("sku"),
                        rs.getInt("quantity"),
                        rs.getLong("total_price_vnd")),
                id);

        return rows.stream().findFirst();
    }
}
```

Repository dùng prepared parameters, không ghép raw request values vào SQL. `UNIQUE(request_key)` ở schema làm constraint cuối cùng chống gửi lại cùng một key; việc kiểm duplicate chỉ ở application memory sẽ có race khi hai requests đồng thời. Trong demo, Spring JDBC chuyển H2 unique constraint violation thành `DuplicateKeyException`, được advice ánh xạ thành HTTP 409.

### 4.6. Service dùng cùng một rule và transaction

File **`src/main/java/com/example/orders/OrderService.java`**:

```java
package com.example.orders;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderStore store;
    private final PricingPolicy pricing;

    public OrderService(
            OrderStore store,
            PricingPolicy pricing) {
        this.store = store;
        this.pricing = pricing;
    }

    @Transactional
    public OrderReceipt create(CreateOrderRequest request) {
        long total = pricing.totalFor(
                request.sku(), request.quantity());

        OrderReceipt receipt = new OrderReceipt(
                UUID.randomUUID().toString(),
                request.requestKey(),
                request.sku(),
                request.quantity(),
                total);

        store.insert(receipt);
        return receipt;
    }

    @Transactional(readOnly = true)
    public OrderReceipt find(String id) {
        return store.findById(id)
                .orElseThrow(OrderNotFoundException::new);
    }
}
```

Controller HTTP chỉ gọi service; một test gọi `OrderService.create(...)` trực tiếp vẫn thực thi cùng pricing/store code, nhưng không chứng minh JSON/HTTP và có transaction **trong test thread**. Ngược lại, POST qua TCP chạy service trong **server request thread**. Việc hai test dùng chung `OrderService` không làm chúng có chung transaction boundary.

### 4.7. REST controller thực

File **`src/main/java/com/example/orders/OrderController.java`**:

```java
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
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest input) {

        OrderReceipt saved = service.create(input);
        URI location = URI.create(
                "/api/orders/" + saved.id());

        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable String id) {
        return service.find(id);
    }
}
```

`ResponseEntity.created(...)` tạo HTTP `201` và `Location` header, Jackson tạo body JSON. `@Valid` kích hoạt Bean Validation cho request DTO. `GET` trả record hoặc ném `OrderNotFoundException` để advice xử lý 404.

**Status 201 không có nghĩa dữ liệu đã commit trong mọi kiến trúc:** trong demo, service transaction hoàn tất trước khi controller return, nên JDBC readback kiểm chính xác. Nếu ứng dụng thật dùng outbox/async queue hoặc eventual consistency, contract có thể là `202 Accepted` và cần polling có timeout thay vì ép mọi request sync commit ngay.

### 4.8. Exception advice: HTTP errors có cấu trúc

File **`src/main/java/com/example/orders/OrderExceptionAdvice.java`**:

```java
package com.example.orders;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidInput() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT", "Invalid order input"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> malformedJson() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "MALFORMED_JSON", "Malformed JSON body"));
    }

    @ExceptionHandler(UnknownSkuException.class)
    public ResponseEntity<ApiError> unknownSku() {
        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(new ApiError(
                        "UNKNOWN_SKU", "Unknown SKU"));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> missingOrder() {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND", "Order not found"));
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<ApiError> duplicateRequest() {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "DUPLICATE_REQUEST", "Duplicate request key"));
    }
}
```

Không bắt mọi `DataIntegrityViolationException` rồi trả `409`: lỗi có thể do ràng buộc khác hoặc schema hỏng, không phải trùng request key. Ví dụ chỉ bắt `DuplicateKeyException` đủ để đại diện cho UNIQUE constraint. Real app có thể cần phân biệt tên constraint trong DB vendor một cách an toàn, nhưng không log PII/SQL chứa secrets.

Handler không lộ exception message raw. Với test HTTP negative, assert **status + error code** thay vì mong exception Java được ném qua TCP cho client.

### 4.9. H2 schema và profile riêng cho test

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE purchase_order (
    order_id VARCHAR(36) PRIMARY KEY,
    request_key VARCHAR(64) NOT NULL UNIQUE,
    sku VARCHAR(32) NOT NULL,
    quantity INT NOT NULL,
    total_price_vnd BIGINT NOT NULL
);

CREATE INDEX idx_purchase_order_sku
    ON purchase_order(sku);
```

File **`src/test/resources/application-test.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

# Chỉ dùng cho test; RANDOM_PORT tự chọn cổng web.
spring.main.banner-mode=off
```

**Không cố định `server.port`**. `@SpringBootTest(RANDOM_PORT)` dùng actual random listening port. `@ActiveProfiles("test")` chọn cấu hình H2 trong `src/test/resources`. CI cần chắc chắn không có `SPRING_DATASOURCE_URL`/system property lạ ghi đè đích này; nếu môi trường có secrets/production networks, phải cô lập runner và kiểm resolved targets trước khi chạy SQL init.

**H2 in-memory không thay thế mọi DB production:** PostgreSQL/MySQL dialect, locking, JSON, isolation, schema rules có thể khác. Khi cần chứng minh vendor-specific behavior, dùng Testcontainers với DB engine tương ứng và container disposable. Vẫn có thể giữ `RANDOM_PORT` để kiểm real HTTP ở đầu vào. Không dùng DB production/staging có dữ liệu thật chỉ để chạy thử.

## 5. JUnit unit tests cho nghiệp vụ thuần Java

File **`src/test/java/com/example/orders/PricingPolicyTest.java`**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PricingPolicyTest {

    private final PricingPolicy pricing =
            new PricingPolicy();

    @Test
    void bookTwoUnitsCost240000() {
        assertThat(pricing.totalFor("BOOK", 2))
                .isEqualTo(240_000L);
    }

    @Test
    void penThreeUnitsCost60000() {
        assertThat(pricing.totalFor("PEN", 3))
                .isEqualTo(60_000L);
    }

    @Test
    void maximumAllowedQuantityCanBePriced() {
        assertThat(pricing.totalFor("BOOK", 10))
                .isEqualTo(1_200_000L);
    }

    @Test
    void zeroQuantityIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("BOOK", 0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void quantityAboveLimitIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("BOOK", 11))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void unknownSkuIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("OTHER", 2))
                .isInstanceOf(UnknownSkuException.class);
    }
}
```

**6 JUnit tests** này không mở Spring context, không dùng DB/port/HTTP. Các invariants của `PricingPolicy` nên được kiểm nhanh ở đây; chúng là oracle cho test tích hợp kiểm cùng logic qua controller. Khi test HTTP sau thất bại, ta phân biệt được lỗi bảng giá thuần Java với lỗi wiring/serialization/JDBC.

## 6. JUnit RANDOM_PORT integration tests: nghiệp vụ qua TCP và H2 thật

File **`src/test/java/com/example/orders/OrderApiRandomPortTest.java`**:

```java
package com.example.orders;

import java.net.URI;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class OrderApiRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private OrderService service;

    @Autowired
    private PricingPolicy pricing;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Environment env;

    // JUnit Jupiter mặc định PER_METHOD:
    // mỗi test invocation sở hữu một Set riêng.
    private final Set<String> requestKeys = new HashSet<>();

    private String ownedKey() {
        String key = "run-" + UUID.randomUUID();
        requestKeys.add(key);
        return key;
    }

    private long countForKey(String key) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM purchase_order
                WHERE request_key = ?
                """,
                Long.class, key);
        return count;
    }

    private ResponseEntity<OrderReceipt> post(
            String key, String sku, int qty) {

        return http.postForEntity(
                "/api/orders",
                new CreateOrderRequest(key, sku, qty),
                OrderReceipt.class);
    }

    private ResponseEntity<ApiError> postError(
            String key, String sku, int qty) {

        return http.postForEntity(
                "/api/orders",
                new CreateOrderRequest(key, sku, qty),
                ApiError.class);
    }

    @AfterEach
    void cleanOnlyOwnedRows() {
        for (String key : requestKeys) {
            jdbc.update("""
                    DELETE FROM purchase_order
                    WHERE request_key = ?
                    """, key);
            assertThat(countForKey(key)).isZero();
        }
    }

    @Test
    void randomPortStartsARealHttpServer() {
        assertThat(port).isBetween(1, 65535);

        ResponseEntity<ApiError> response =
                http.getForEntity(
                        "/api/orders/not-present", ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(404);
        assertThat(response.getBody().code())
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void postCreatesOrderAndReturns201WithLocation() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "BOOK", 2);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(response.getBody()).isNotNull();

        OrderReceipt body = response.getBody();
        assertThat(body.id()).isNotBlank();
        assertThat(body.requestKey()).isEqualTo(key);
        assertThat(body.sku()).isEqualTo("BOOK");
        assertThat(body.quantity()).isEqualTo(2);
        assertThat(body.totalPriceVnd()).isEqualTo(240_000L);

        URI location = response.getHeaders().getLocation();
        assertThat(location).isNotNull();
        assertThat(location.getPath())
                .isEqualTo("/api/orders/" + body.id());
    }

    @Test
    void httpTotalMatchesPureBusinessPolicy() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "PEN", 3);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(response.getBody().totalPriceVnd())
                .isEqualTo(pricing.totalFor("PEN", 3))
                .isEqualTo(60_000L);
    }

    @Test
    void directServiceAndRealHttpShareBusinessInvariant() {
        String directKey = ownedKey();
        OrderReceipt direct = service.create(
                new CreateOrderRequest(directKey, "BOOK", 3));

        String httpKey = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(httpKey, "BOOK", 3);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);

        OrderReceipt overHttp = response.getBody();
        assertThat(direct.id()).isNotEqualTo(overHttp.id());
        assertThat(direct.requestKey())
                .isNotEqualTo(overHttp.requestKey());
        assertThat(overHttp.totalPriceVnd())
                .isEqualTo(direct.totalPriceVnd())
                .isEqualTo(pricing.totalFor("BOOK", 3));
        assertThat(countForKey(directKey)).isEqualTo(1L);
        assertThat(countForKey(httpKey)).isEqualTo(1L);
    }

    @Test
    void getReadsThePersistedOrderThroughHttp() {
        String key = ownedKey();
        OrderReceipt created = post(key, "BOOK", 1).getBody();

        ResponseEntity<OrderReceipt> fetched =
                http.getForEntity(
                        "/api/orders/" + created.id(),
                        OrderReceipt.class);

        assertThat(fetched.getStatusCode().value())
                .isEqualTo(200);
        assertThat(fetched.getBody()).isEqualTo(created);
    }

    @Test
    void serverCommittedRowIsVisibleToTestJdbcConnection() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "BOOK", 4);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(countForKey(key)).isEqualTo(1L);

        Long savedTotal = jdbc.queryForObject("""
                SELECT total_price_vnd
                FROM purchase_order WHERE request_key = ?
                """, Long.class, key);

        assertThat(savedTotal).isEqualTo(480_000L);
    }

    @Test
    void sameRequestKeyProducesConflictAndOneRow() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> first =
                post(key, "BOOK", 1);
        ResponseEntity<ApiError> second =
                postError(key, "BOOK", 1);

        assertThat(first.getStatusCode().value())
                .isEqualTo(201);
        assertThat(second.getStatusCode().value())
                .isEqualTo(409);
        assertThat(second.getBody().code())
                .isEqualTo("DUPLICATE_REQUEST");
        assertThat(countForKey(key)).isEqualTo(1L);
    }

    @Test
    void differentRequestKeysCanCreateSameProduct() {
        String firstKey = ownedKey();
        String secondKey = ownedKey();

        OrderReceipt a = post(firstKey, "PEN", 2).getBody();
        OrderReceipt b = post(secondKey, "PEN", 2).getBody();

        assertThat(a.id()).isNotEqualTo(b.id());
        assertThat(a.totalPriceVnd())
                .isEqualTo(b.totalPriceVnd());
        assertThat(countForKey(firstKey)).isEqualTo(1L);
        assertThat(countForKey(secondKey)).isEqualTo(1L);
    }

    @Test
    void blankRequestKeyReturns400() {
        ResponseEntity<ApiError> response =
                postError("  ", "BOOK", 1);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
    }

    @Test
    void missingSkuReturns400AndDoesNotInsert() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, null, 1);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void zeroQuantityReturns400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "BOOK", 0);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void quantityAboveLimitReturns400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "BOOK", 11);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void unsupportedSkuReturns422Not400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "UNKNOWN", 2);

        assertThat(response.getStatusCode().value())
                .isEqualTo(422);
        assertThat(response.getBody().code())
                .isEqualTo("UNKNOWN_SKU");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void unknownOrderIdReturns404() {
        ResponseEntity<ApiError> response =
                http.getForEntity(
                        "/api/orders/" + UUID.randomUUID(),
                        ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(404);
        assertThat(response.getBody().code())
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void malformedJsonReturnsStructured400() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request =
                new HttpEntity<>("{ invalid json", headers);

        ResponseEntity<ApiError> response = http.exchange(
                "/api/orders",
                HttpMethod.POST,
                request,
                ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("MALFORMED_JSON");
    }

    @Test
    void emptyBodyReturnsStructured400() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request =
                new HttpEntity<>("", headers);

        ResponseEntity<ApiError> response = http.exchange(
                "/api/orders",
                HttpMethod.POST,
                request,
                ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("MALFORMED_JSON");
    }

    @Test
    void absoluteUrlUsingInjectedPortReachesSameServer() {
        String key = ownedKey();
        OrderReceipt created =
                post(key, "PEN", 1).getBody();

        String absoluteUrl =
                "http://127.0.0.1:" + port
                        + "/api/orders/" + created.id();

        ResponseEntity<OrderReceipt> response =
                http.getForEntity(
                        absoluteUrl, OrderReceipt.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isEqualTo(created);
    }

    @Test
    void selectedProfileUsesTestOnlyDatabase() {
        assertThat(env.getActiveProfiles())
                .contains("test");

        String jdbcUrl =
                env.getProperty("spring.datasource.url");
        assertThat(jdbcUrl)
                .startsWith("jdbc:h2:mem:orders_test");
    }
}
```

**Lưu ý QA đối với ví dụ:**
- `@SpringBootTest(RANDOM_PORT)` đã tích hợp `SpringExtension` cho JUnit Jupiter; không cần thêm `@ExtendWith`.
- `@Autowired TestRestTemplate` root URI tự gắn với server; test absolute URL chứng minh `@LocalServerPort` có giá trị thực.
- Các negative tests **kiểm response status và JSON error.code**, không catch `HttpClientErrorException` vì `TestRestTemplate` cố ý không throw mặc định với 4xx/5xx.
- `@AfterEach` chỉ xóa các `request_key` mà test invocation hiện tại đã đăng ký; không chạy `TRUNCATE` hay `DELETE` toàn bảng.
- `OrderService.create` trực tiếp và `POST` qua HTTP dùng cùng pricing/store, nhưng chạy trong các **transaction/thread khác nhau**.
- `@TestInstance(PER_METHOD)` là mặc định của Jupiter, nên `Set<String> requestKeys` không bị chia giữa test methods; suite không bật parallel. Nếu bật concurrency, phải xem xét context/DB/cleanup resource ownership thực tế.
- Test `GET` sau `POST` xác nhận record được serialize/deserialized nhất quán và đọc từ DB đã lưu, chứ không chỉ so controller echo request.

## 7. Lệnh chạy và kết quả dự kiến

Yêu cầu JDK **17 trở lên**, Maven và dependencies có thể tải từ repository đã cấu hình. Chạy từ thư mục chứa `pom.xml`:

```bash
mvn --batch-mode --no-transfer-progress test
```

Chạy riêng từng class:

```bash
mvn -Dtest=PricingPolicyTest test
mvn -Dtest=OrderApiRandomPortTest test
```

Kiểm dependency versions:

```bash
mvn dependency:tree
```

**Dự kiến** `PricingPolicyTest` có **6 `@Test` methods**; `OrderApiRandomPortTest` có **18 `@Test` methods**, tổng **24 tests**, đều PASS với Spring Boot 3.5.0 + H2/Java 17 trên runner được cấu hình như mô tả. Đây là **dự kiến từ source**, không phải output Maven đã được chạy trong quá trình biên soạn tài liệu. Xem `target/surefire-reports` để kiểm class count, thất bại và elapsed time thực khi thực thi.

Không hardcode cổng vào stdout hay assertions: cổng do OS/embedded server chọn ở từng ApplicationContext startup, có thể khác giữa các lượt chạy. Không tự nói `server.port=8080` hay ngược lại assert `port != 8080`, vì một cổng động về lý thuyết có thể trùng bất kỳ giá trị đang rảnh.

### 7.1. Ví dụ về HTTP contract (minh họa, không phải captured output)

Giả sử server đã chạy và client gửi một key giả:

```http
POST /api/orders HTTP/1.1
Host: localhost:54231
Content-Type: application/json

{"requestKey":"example-key-123","sku":"BOOK","quantity":2}
```

Response có cấu trúc:

```http
HTTP/1.1 201 Created
Location: /api/orders/<generated-uuid>
Content-Type: application/json

{
  "id": "<generated-uuid>",
  "requestKey": "example-key-123",
  "sku": "BOOK",
  "quantity": 2,
  "totalPriceVnd": 240000
}
```

Dấu `<generated-uuid>` ở trên **chỉ là ký hiệu mô tả JSON/HTTP response động trong ví dụ**, không phải chuỗi literal mà code trả; tests không dùng placeholder ID và không so request với static output. Trong một run thực, port/UUID khác nhau và Content-Type có thể kèm charset/headers khác. Các giá trị cố định mà test assert là **status, URI path shape, request key, sku, quantity, total**.

Lỗi duplicate:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"DUPLICATE_REQUEST","message":"Duplicate request key"}
```

Đây là expected shape do `OrderExceptionAdvice` xác định; nó không có PII/exception stack trace. Nếu API thật sử dụng RFC 9457 Problem Details, thay `ApiError` bằng `ProblemDetail` và test fields contract tương ứng.

## 8. RANDOM_PORT và rollback: nguy cơ dữ liệu sót lại

Đây là nội dung đặc biệt quan trọng. Trong Spring TestContext, một phương thức test gắn `@Transactional` thường được test-managed transaction bao bọc và rollback sau test. Nhưng với `RANDOM_PORT`, **HTTP client và server chạy trên thread khác**; transaction context theo `ThreadLocal` không tự truyền qua request TCP. Vì vậy:
- Dữ liệu do test **gọi service trực tiếp** trong test transaction có thể rollback cùng test.
- Dữ liệu do HTTP request tạo **trong server request thread** có transaction riêng và có thể **commit thật**.
- `@Transactional` trên class test **không** biến toàn bộ POST/GET thành một transaction xuyên TCP.
- `@AfterEach` thực hiện dưới test-managed transaction nếu test có `@Transactional`; một lệnh cleanup JDBC ở đó có thể **cũng bị rollback**, để lại row HTTP đã commit.

### 8.1. Một anti-pattern thường gặp

```java
// Anti-pattern minh họa, KHÔNG thuộc runnable tests.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class MisleadingRollbackTest {

    @Autowired TestRestTemplate client;

    @Test
    void createsOrder() {
        client.postForEntity("/api/orders", request, String.class);
        // Sai nếu tin rằng server POST sẽ rollback cùng test!
    }
}
```

Biến `request` ở snippet này là giá trị giả định, không thuộc runnable project ở phần 6. Điều quan trọng là **test-managed transaction ở client test thread không rollback server-side transaction**. Ngay cả khi test method kết thúc PASS và @Transactional test rollback, HTTP writes vẫn có thể tồn tại.

### 8.2. Chiến lược demo dùng: cleanup theo request key ngoài transaction

`OrderApiRandomPortTest` **không đặt `@Transactional`**, để:
- Service được gọi qua HTTP commit/rollback theo cấu hình service thật.
- Test có thể đọc row đã commit bằng `JdbcTemplate` sau response.
- `@AfterEach` dùng một **new JDBC operation** để xóa row thuộc key riêng, không bị rollback cùng test transaction.
- Test khác không bị ảnh hưởng vì mỗi test method sở hữu unique request keys, và cleanup không xóa rows của test khác.
- Nếu HTTP trả lỗi validation trước insert, cleanup theo key vẫn an toàn (xóa 0 rows).

**Điều này không đảm bảo mọi side effect đã dọn.** Nếu service publish Kafka events, gửi email hoặc tạo file, phải cleanup/mocking/isolated sandbox phù hợp. Nếu test fail giữa async workflow, cần chờ async hoàn tất có timeout trước teardown. Không dùng `Thread.sleep` làm bằng chứng eventual consistency.

### 8.3. Khi muốn dùng @Transactional cùng RANDOM_PORT

Có thể cần test transaction trên một **direct-service scenario** riêng, không trộn với HTTP cleanup. Với HTTP test, sử dụng:
- Per-test schema/database hoặc container;
- Scoped fixture keys + cleanup;
- Bounded polling cho eventual consistency;
- Test-only reset endpoint có security chặt **chỉ trong isolated environment** nếu thật cần;
- Cleanup via TransactionTemplate không join một transaction đang rollback, khi rõ transaction semantics.

**Đừng bật `@DirtiesContext` sau mỗi HTTP test như bản vá**: context mới không xóa những rows đã commit trong DB ngoài, và startup rất tốn thời gian. Với H2 memory DB, đóng context có thể ảnh hưởng lifecycle DB nhưng không phải chiến lược data isolation có thể chuyển nguyên xi sang PostgreSQL production.

## 9. Chọn assertions cho HTTP end-to-end ở cấp ứng dụng

### 9.1. Thành công phải kiểm đủ status, body, headers và persisted state

Một kiểm thử tối thiểu nhưng đủ giá trị cho `POST`:

- Status đúng **201**, không chỉ “2xx”.
- Response `Location` present, path đúng `/api/orders/{id}`.
- JSON body có `requestKey`, `sku`, `quantity`, `totalPriceVnd` chính xác.
- `GET Location` trả đúng đơn vừa tạo.
- JDBC read từ một connection khác thấy row đã commit.
- Sau cleanup, `countByKey == 0`.

Nếu chỉ assert `postForObject(...) != null`, test có thể bỏ sót status 200 thay vì 201, location thiếu, quantity mismatch hoặc row không được persist.

### 9.2. Negative tests không gọi lại service trực tiếp để tạo giả lỗi

Nếu cần chứng minh JSON validation:
- Gửi **HTTP request** qua `TestRestTemplate`, không gọi `controller.create(...)` trực tiếp.
- Với blank/invalid payload, assert HTTP **400**, error.code `INVALID_INPUT`.
- Với JSON hỏng, assert HTTP **400**, code `MALFORMED_JSON`.
- Với domain SKU lạ, assert **422** (contract demo), không đánh đồng với validation 400.
- Với duplicate key, assert **409** và DB row count **1**, không chỉ count exception.
- Với unknown ID, assert **404** và code `ORDER_NOT_FOUND`.

Controller unit tests vẫn có giá trị nhanh, nhưng chúng không thay thế negative HTTP contract tests khi mục tiêu là kiểm routing, converters và exception resolver.

### 9.3. ResponseEntity và type safety

`TestRestTemplate.postForEntity(path, body, OrderReceipt.class)` dùng HTTP/message converters để deserialize JSON vào Java record. Nếu response đổi field name hoặc type, test có thể fail ở JSON binding hoặc assertion. Với collections/generic types, có thể dùng `exchange(...)` kèm `ParameterizedTypeReference<List<OrderReceipt>>` thay vì chỉ `List.class`.

Với error bodies, ví dụ dùng `ApiError.class` đúng theo contract. Nếu server trả lỗi không phải JSON (gateway, 404 HTML) thì Jackson deserialize sẽ fail; **đó là bằng chứng hữu ích** về contract khác dự kiến. Đừng dùng `String.class` cho mọi response chỉ để tránh xử lý type mismatch nếu API yêu cầu JSON schema.

## 10. Đọc lỗi trong CI đúng lớp

| Triệu chứng | Khả năng cao | Chẩn đoán |
|---|---|---|
| `Connection refused` khi gọi localhost | Server chưa start hoặc client dùng sai port | Kiểm annotation RANDOM_PORT, @LocalServerPort, context startup error |
| Port fixed 8080 bị chiếm | Dùng DEFINED_PORT hoặc config override | Bỏ fixed port, dùng RANDOM_PORT; kiểm system properties |
| `@Autowired TestRestTemplate` null | Không chạy Boot test context phù hợp | Có @SpringBootTest(RANDOM_PORT), đúng dependency, đúng package |
| `404` trên POST đã tạo controller | Sai mapping/base path/context path | Kiểm request URI, servlet path, controller scanning |
| `400` thay vì 201 | @Valid/JSON binding/input fields sai | Kiểm status + error.code; xem request DTO |
| `409` xuất hiện từ test khác | Reuse requestKey cố định, data còn sót | UUID keys, per-test cleanup, DB isolation |
| `422` dù SKU hợp lệ | Price policy không trùng contract | Unit test PricingPolicy + direct-service check |
| `500` do DuplicateKeyException không được handle | Advice chưa map hoặc exception type khác | Kiểm JDBC translator/constraint, không catch all |
| `200` nhưng không có row | Controller echo request, async persistence | Readback JDBC hoặc await eventual outcome có timeout |
| `@Transactional` test xanh nhưng DB row còn | Server thread transaction đã commit | Cleanup scoped ngoài test tx |
| Cùng tests lúc PASS lúc FAIL | Shared H2 DB, test order/parallel cleanup | Unique keys, no global TRUNCATE, test reports |
| Test JDBC thấy URL không đúng | Runner property override, @ServiceConnection | Kiểm resolved/actual DataSource trong sandbox |
| Test trả `401/403` khi app có Security | Authentication/CSRF đang active | Dùng test identity đúng, không disable security |
| Test WebTestClient không inject được | Thiếu spring-webflux/test setup | Dùng TestRestTemplate hoặc bổ sung config cần thiết |
| MockMvc pass nhưng HTTP test fail | Servlet container, routing, filter/socket khác | Giữ cả hai lớp khi cần, debug HTTP status/headers |
| Test management endpoint sai port | management server tách riêng | Dùng @LocalManagementPort/management test client đúng context |
| JSON error không parse thành ApiError | Proxy/HTML error hoặc advice không chạy | Kiểm raw response một cách sanitized |
| CI treo lâu | Real HTTP client timeout/retry hoặc DB wait | Bounded request timeouts, CI test budget, diagnostics |

### 10.1. Kiểm chính xác nguyên nhân thay vì tăng timeout bừa bãi

Một request timeout không phải luôn vì server “chậm”. Các khả năng: TCP port sai, DNS proxy env, Tomcat chưa start, database connection pool cạn, deadlock khi tests dùng transaction và server cùng một connection, hoặc async task chờ vô hạn. Dùng client timeouts có giới hạn, ghi timestamp/trace ID không nhạy cảm, phân biệt connect timeout với response timeout.

`RANDOM_PORT` giúp tránh collision, nhưng không thay thế **readiness/liveness của dependencies thật**. Trong CI không nên truy cập production services; nếu cần DB tương thích production, dùng container disposable, có startup timeout rõ ràng và cleanup.

## 11. Khi ứng dụng có Spring Security

Project sample **không** thêm `spring-boot-starter-security` để tập trung vào HTTP + business logic. Trong ứng dụng thật, request tới `POST /api/orders` có thể gặp:
- `401` nếu thiếu identity;
- `403` nếu role không đủ;
- `403` do thiếu CSRF token trên unsafe methods khi security policy áp dụng;
- Redirect `302` nếu form-login entry point;
- `429` nếu rate limiting/filter thực thi.

**Không được** sửa test bằng cách xóa `SecurityFilterChain` chỉ để GET/POST trả 201. Hãy test với account/token sandbox, authority/role đúng, và policy CSRF thực tế. `TestRestTemplate.withBasicAuth(...)` chỉ phù hợp nếu app sử dụng HTTP Basic; với OAuth2/JWT cần authorization header token **test-only**, bảo đảm không in token trong logs.

Khi cần assert authorization:
1. Anonymous request bị từ chối đúng code;
2. Role sai bị từ chối đúng code;
3. Role đúng đi qua full HTTP và tạo **đúng một** row;
4. Rejected request không có side effects;
5. Không lộ stacktrace/secret trong error body.

Security là một phần của real HTTP integration contract, không nhất thiết phải disable để đo nghiệp vụ.

## 12. MANAGEMENT_PORT, HTTPS, proxy và network boundary

### 12.1. Management server port riêng

Nếu `management.server.port` khác application `server.port`, Spring Boot 3.5 có thể khởi chạy management server với **một random port riêng** khi test dùng `RANDOM_PORT`. `@LocalServerPort` là port của ứng dụng chính, **không mặc định** là port management. Với test Actuator health/metrics ở management context riêng, phải lấy actual management port bằng cơ chế phù hợp (ví dụ `@LocalManagementPort`) và test security/network path riêng.

Không lấy một response `200` từ `/api/orders` rồi khẳng định `/actuator/health` ở management port cũng sẽ 200. Chúng có thể sử dụng port, servlet context và security config khác nhau.

### 12.2. HTTPS và reverse proxy

Test mẫu dùng HTTP loopback:
- Kiểm real Tomcat HTTP stack, **không** kiểm TLS certificates/truststore/mTLS.
- Không kiểm nginx/ingress rewrite `/api`, forwarded headers, sticky sessions hay load balancer.
- Không kiểm firewall, network policy hoặc DNS public.
- Không kiểm cookie Domain/SameSite/Secure trên public hostname nếu không cấu hình.

Khi hợp đồng deployment phụ thuộc proxy/TLS, bổ sung E2E test against **ephemeral deployed environment** với hostname/identity thích hợp. Tránh chạy destructive tests trên production data chỉ vì RANDOM_PORT chưa bao phủ edge infrastructure.

### 12.3. WebFlux vs Spring MVC

Nếu application là WebFlux-only, `RANDOM_PORT` vẫn khởi động web server thật, nhưng threading, body streaming và client stack khác. `WebTestClient` phù hợp WebFlux/reactive tests. Nếu cùng có MVC và WebFlux, Spring Boot mặc định ưu tiên MVC trừ khi `spring.main.web-application-type=reactive`. Không lấy snippet servlet `@AutoConfigureMockMvc` và giả định nó kiểm Netty/reactive semantics.

## 13. Test isolation và hiệu năng khi chạy bộ lớn

### 13.1. Context cache

Spring TestContext cache keyed theo merged test configuration, bao gồm `classes`, profiles, properties, context customizers (ví dụ `@MockitoBean`/`@DynamicPropertySource`), loader và những nguồn khác. Hai test classes với cùng cấu hình có thể dùng chung ApplicationContext + embedded server; port không được xem là test identity. Đổi profile/property hoặc bean override có thể tạo cache key khác và mở server mới.

Không đặt `@DirtiesContext` sau mọi test chỉ để “được port mới”. Nó gây restart context và có thể **không xóa DB rows ngoài context**. Cần cleanup data đúng scope, tách contexts chỉ khi bean graph/state thực sự phải khác.

### 13.2. Chạy song song không được xóa toàn DB

Nếu JUnit parallel execution bật, các tests có thể cùng dùng Spring context/H2:
- Mỗi test dùng `request_key` unique.
- Queries/cleanup theo request key; không `TRUNCATE purchase_order`.
- @AfterEach cleanup phải xảy ra sau khi server side effect đã hoàn tất.
- Không chia Mockito stubs/global static state tùy tiện.
- Nếu code có async writes, đợi completion và kiểm dữ liệu sau đó.
- Nếu DB có global inventory/quota shared, unique key riêng **chưa đủ** để ngăn races; cần transaction/isolation/locks và test concurrency riêng.

Demo không bật parallel để giữ mục tiêu rõ. Một lớp test có `@DirtiesContext` chạy đồng thời với lớp khác dùng shared context có thể đóng server khi request đang xử lý, gây flaky connection errors.

### 13.3. Vì sao không mock OrderService trong bài này?

Nếu dùng `@MockitoBean OrderService`, test chỉ chứng minh controller và client mock giao tiếp đúng; nó **không** chứng minh giá được tính theo `PricingPolicy`, JDBC repository gọi thật, unique constraint hoặc transaction commit. Mock hoàn toàn hợp lý ở `@WebMvcTest` slice khi muốn isolating controller mapping, nhưng **đi ngược mục tiêu “cùng nghiệp vụ xuyên tầng qua RANDOM_PORT”** của bài.

Ngoại lệ hợp lý: external gateway (payment, email, cloud) nên là fake/stub để test không có side effects thật; vẫn giữ service/repository nội bộ thật. Không dùng production credentials, database hoặc API endpoints trong integration test.

## 14. Test plan cho nghiệp vụ tương tự

| Ca kiểm thử | Cách làm | Bằng chứng cần có |
|---|---|---|
| Business pricing | Unit `PricingPolicy` | BOOK/PEN và quantity đúng, SKU lạ throw |
| Spring bean path | Service trực tiếp | Same total + JDBC row |
| Server startup | RANDOM_PORT + @LocalServerPort | Port thực >0, HTTP GET trả response từ handler |
| POST thành công | TestRestTemplate | 201 + Location + JSON fields |
| GET persistence | GET bằng ID trả sau POST | 200 + receipt đúng |
| Commit visibility | JDBC read sau HTTP POST | H2 row đã commit và total đúng |
| Duplicate key | Hai POST cùng requestKey | 201, 409 và chỉ một row |
| Unique requests | Hai keys khác nhau | Hai IDs khác, mỗi key một row |
| Body invalid | Blank/missing field, quantity sai | 400 + INVALID_INPUT, không insert |
| JSON syntax invalid | Raw HTTP request hỏng | 400 + MALFORMED_JSON |
| Domain invalid | SKU không hỗ trợ | 422 + UNKNOWN_SKU |
| ID không có | GET unknown UUID | 404 + ORDER_NOT_FOUND |
| Error disclosure | Negative response | Chỉ code/message safe; không stacktrace |
| Cleanup | @AfterEach theo ownedKey | Không còn row của test |
| Test profile | @ActiveProfiles("test") | H2 in-memory, không production |
| Security (khi có) | Token/role/CSRF | 401/403/2xx đúng policy |
| Management split port | Real port riêng | Actuator đúng path/status/security |
| Async business | HTTP 202 và poll | Await outcome, timeout, no cross-test residue |
| Production DB semantics | Disposable Testcontainers | Dialect/isolation/locking phù hợp |
| Proxy/TLS | Deployment-like E2E | Cấu hình edge đúng |

### Cách đặt tên test

Một test tên `createsOrder` còn mơ hồ; ưu tiên `postCreatesOrderAndReturns201WithLocation`, `sameRequestKeyProducesConflictAndOneRow`, `serverCommittedRowIsVisibleToTestJdbcConnection`. Tên cụ thể giúp người đọc hiểu **đường đi và bằng chứng**, không cần mở implementation.

**Không biến mọi case thành một server startup mới.** Một context chia sẻ theo TestContext cache + request keys độc lập giúp suite nhanh hơn trong khi vẫn giữ isolation.

## 15. Checklist trước khi chấp nhận test RANDOM_PORT trong CI

- [ ] Chọn `RANDOM_PORT` vì cần bằng chứng về real TCP/server, không chỉ gọi controller.
- [ ] POM có Spring Boot web/test/JUnit và dependencies dữ liệu cần thiết.
- [ ] Có `@LocalServerPort` nếu cần absolute URL; không hardcode port 8080.
- [ ] Dùng `@Autowired TestRestTemplate` hoặc real client được bind đúng actual port.
- [ ] Test kiểm HTTP status **chính xác**, không chỉ 2xx.
- [ ] Assert Location header, JSON response và error body contract.
- [ ] Các business rules được kiểm riêng ở unit level, rồi kiểm lại qua HTTP ở case đại diện.
- [ ] Không mock toàn bộ service/repository nội bộ nếu muốn chứng minh business integration.
- [ ] Bean Validation được cài đủ dependency; `@Valid` chạy trước service.
- [ ] Negative tests phân biệt 400 (input), 404 (missing), 409 (duplicate) và 422 (unsupported domain).
- [ ] Persistence được kiểm bằng real JDBC readback sau HTTP response.
- [ ] Tôi biết test thread không chia transaction với server thread, không mặc định HTTP writes được rollback.
- [ ] Cleanup theo test-owned key trong `@AfterEach`/finally, không global truncate.
- [ ] H2/config test chỉ trên test classpath và không bị production URL override.
- [ ] No secrets, PII, real customer data hoặc external production clients trong test suite.
- [ ] Nếu cần vendor DB semantics, dùng disposable Testcontainers thay cho DB production.
- [ ] `@SpringBootTest(RANDOM_PORT)` không được nhầm với `@AutoConfigureMockMvc`.
- [ ] Không cho rằng random port luôn khác giữa mọi test methods; context cache có thể reuse.
- [ ] Nếu security bật, test authentication, authorization, CSRF theo policy thật.
- [ ] Nếu có management port riêng, test actual management listener riêng.
- [ ] Không suy RANDOM_PORT kiểm được TLS, ingress, proxy hoặc public network paths.
- [ ] Test data và async operations được cleanup/await trước khi test kết thúc.
- [ ] Không bật parallel trên shared mutable DB/global state khi chưa đánh giá.
- [ ] Chạy `mvn test`, kiểm số test được discovery và `target/surefire-reports`.
- [ ] Khi một test FAIL, lưu status/headers/body đã sanitize cùng actual request URI/test key để chẩn đoán.

**Kết luận:** `@SpringBootTest(webEnvironment = RANDOM_PORT)` là công cụ phù hợp để kiểm **cùng một nghiệp vụ trong ứng dụng Spring Boot thật ở mức HTTP**, từ JSON input qua validation/controller/service/transaction/JDBC tới HTTP response và data đã lưu. Kết hợp **unit test cho invariant**, **real HTTP test cho contract** và **cleanup có ownership** để tránh biến suite thành các test phụ thuộc thứ tự. Hiểu rõ transaction boundary và phạm vi được chứng minh giúp tránh hai ngộ nhận phổ biến: **MockMvc không phải socket HTTP**, và **rollback của test thread không tự undo POST chạy trong server thread**.

### Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications: MOCK, RANDOM_PORT, TestRestTemplate và Transactions](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @SpringBootTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot 3.5 — @LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html)
- [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)
- [Spring Framework 6.2 — Integration Testing / Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
- [Spring Boot 3.5 — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [JUnit Jupiter 5.12 — User Guide](https://docs.junit.org/5.12.0/user-guide/)
