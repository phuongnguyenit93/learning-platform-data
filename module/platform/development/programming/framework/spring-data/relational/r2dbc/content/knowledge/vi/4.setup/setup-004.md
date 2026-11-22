# Khởi tạo ứng dụng bằng cơ chế tự cấu hình của Spring Boot

Spring Boot giúp khởi tạo một ứng dụng Spring Data R2DBC với rất ít cấu hình thủ công. Khi các dependency phù hợp có mặt trên classpath và thông tin kết nối được khai báo, Spring Boot có thể tự tạo `ConnectionFactory`, cấu hình hạ tầng truy cập dữ liệu reactive, đăng ký repository và cung cấp các thành phần hỗ trợ transaction.

Điểm quan trọng là **auto-configuration dựa trên dependency, cấu hình và các bean hiện có trong ApplicationContext**. Spring Boot không tự đoán được database, tài khoản hay cấu trúc bảng của ứng dụng. Bạn vẫn cần thêm driver đúng loại, cung cấp thông tin kết nối và thiết kế schema.

## 1. Auto-configuration của Spring Boot là gì?

Auto-configuration là cơ chế Spring Boot tự cấu hình các thành phần phổ biến dựa trên những gì ứng dụng khai báo. Cơ chế này được kích hoạt bởi `@EnableAutoConfiguration`, vốn đã được bao gồm trong annotation tổng hợp `@SpringBootApplication`.

Ví dụ:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Khi ứng dụng khởi động, Spring Boot đọc cấu hình, kiểm tra classpath và các bean đã được đăng ký, sau đó áp dụng những auto-configuration phù hợp. Các cấu hình này thường sử dụng điều kiện như:

- Một class hoặc thư viện có mặt trên classpath.
- Một property được bật hoặc có giá trị.
- Một bean cần thiết đã tồn tại hoặc chưa tồn tại.
- Ứng dụng đang chạy trong một kiểu môi trường phù hợp.

Auto-configuration có tính linh hoạt. Nếu ứng dụng tự khai báo một bean mà auto-configuration chỉ tạo khi chưa có bean tương ứng, cấu hình mặc định sẽ nhường chỗ cho bean do ứng dụng cung cấp. Đây là cơ chế *back-off*.

Ví dụ, khi Spring Boot có thể tạo `ConnectionFactory` từ `spring.r2dbc.*`, bạn thường không cần tự viết cấu hình kết nối. Nếu có yêu cầu đặc biệt và tự khai báo một `ConnectionFactory` bean, cấu hình mặc định tạo connection factory sẽ lùi lại để dùng bean đó.

## 2. Chuẩn bị dependency cho Spring Data R2DBC

Một ứng dụng R2DBC cần ít nhất hai nhóm thành phần:

1. Spring Data R2DBC và phần tích hợp R2DBC của Spring Boot.
2. Driver R2DBC dành cho database cụ thể.

Ví dụ dưới đây dùng PostgreSQL và Gradle. Giả sử dự án đã áp dụng Spring Boot Gradle plugin và dependency management của Spring Boot:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    // Chỉ cần nếu ứng dụng cung cấp HTTP API bằng Spring WebFlux.
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

Nếu ứng dụng không có HTTP API, có thể bỏ `spring-boot-starter-webflux`. Nếu ứng dụng đang dùng Spring MVC, hãy giữ web stack phù hợp với kiến trúc hiện tại; việc dùng R2DBC không bắt buộc phải chuyển toàn bộ ứng dụng sang WebFlux.

Với Maven, các dependency tương ứng có dạng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Các ví dụ không ghi phiên bản riêng vì Spring Boot dependency management thường quản lý phiên bản tương thích. Với dự án không sử dụng dependency management của Spring Boot, cần tự chọn các phiên bản Spring Data, R2DBC SPI và driver tương thích với nhau.

### 2.1. Phân biệt driver JDBC và driver R2DBC

Driver JDBC và driver R2DBC là hai loại driver khác nhau. Ví dụ:

| Mục đích | PostgreSQL |
| --- | --- |
| JDBC | `org.postgresql:postgresql` |
| R2DBC | `org.postgresql:r2dbc-postgresql` |

Chỉ thêm PostgreSQL JDBC driver không đủ để Spring Data R2DBC tạo kết nối. Ứng dụng cần driver triển khai R2DBC SPI.

Tương tự, URL kết nối cũng khác nhau. R2DBC dùng scheme do driver định nghĩa, ví dụ `r2dbc:postgresql://...`; JDBC dùng `jdbc:postgresql://...`.

## 3. Khai báo cấu hình kết nối

Spring Boot đọc các thuộc tính R2DBC từ prefix `spring.r2dbc`. Có thể khai báo trong `application.properties`:

```properties
spring.application.name=shop-service

spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=shop_app
spring.r2dbc.password=${DB_PASSWORD:local-secret}
```

Hoặc dùng YAML trong `application.yml`:

```yaml
spring:
  application:
    name: shop-service
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD:local-secret}
```

Trong ví dụ, database `shop` phải tồn tại và PostgreSQL phải đang chạy. `DB_PASSWORD` có thể được cung cấp qua biến môi trường. Giá trị mặc định `local-secret` chỉ nhằm giúp ví dụ chạy ở môi trường local; môi trường thật nên lấy thông tin bí mật từ hệ thống quản lý secret hoặc cấu hình triển khai.

### 3.1. Những thuộc tính cần biết

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.r2dbc.url` | URL R2DBC do driver hỗ trợ, xác định loại database và địa chỉ kết nối |
| `spring.r2dbc.username` | Tên người dùng kết nối database |
| `spring.r2dbc.password` | Mật khẩu kết nối database |
| `spring.r2dbc.name` | Tên database, nếu driver và kiểu cấu hình đang dùng hỗ trợ thuộc tính này |
| `spring.r2dbc.properties.*` | Các thuộc tính bổ sung được chuyển tới cấu hình connection factory theo hỗ trợ của driver |

Không phải driver nào cũng hỗ trợ mọi tùy chọn giống nhau. Khi cần cấu hình SSL, schema, application name hoặc các thuộc tính đặc thù khác, hãy kiểm tra tài liệu của driver tương ứng.

### 3.2. Không nhầm cấu hình R2DBC với cấu hình JDBC

Hai prefix sau phục vụ hai cơ chế kết nối khác nhau:

```properties
# R2DBC
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop

# JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
```

Spring Boot không tự chuyển `spring.datasource.*` thành `spring.r2dbc.*` hoặc ngược lại. Nếu ứng dụng chỉ dùng Spring Data R2DBC, hãy cấu hình `spring.r2dbc.*` và thêm driver R2DBC. Nếu ứng dụng có cả JDBC lẫn R2DBC, hai stack có thể cần cấu hình connection và pool riêng.

## 4. Những thành phần Spring Boot tự cấu hình

Khi dependency và cấu hình hợp lệ, auto-configuration có thể thiết lập các thành phần chính sau. Tên và điều kiện chi tiết có thể thay đổi theo phiên bản Spring Boot, vì vậy nên xem tài liệu đúng phiên bản đang dùng khi cần tùy chỉnh sâu.

### 4.1. `ConnectionFactory`

`ConnectionFactory` là điểm vào chính của R2DBC để tạo connection tới database. Spring Boot sử dụng URL và các thuộc tính `spring.r2dbc.*`, kết hợp driver tương ứng trên classpath, để tạo connection factory.

Ví dụ với URL:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
```

scheme `r2dbc:postgresql` cho biết cấu hình cần driver PostgreSQL R2DBC. Driver chịu trách nhiệm triển khai giao thức và tạo kết nối thực tế.

Nếu không có driver tương ứng, URL sai hoặc database không truy cập được, ứng dụng có thể thất bại khi tạo connection factory hoặc khi mở kết nối. Auto-configuration không thể bù cho driver bị thiếu hay database chưa chạy.

### 4.2. `DatabaseClient`

`DatabaseClient` là API cấp thấp của Spring Framework để thực thi SQL theo cách reactive. Nó sử dụng `ConnectionFactory` để làm việc với database và hỗ trợ bind tham số, đọc kết quả cũng như ánh xạ dữ liệu.

Ví dụ minh họa một truy vấn:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public class CustomerQueries {

    private final DatabaseClient databaseClient;

    public CustomerQueries(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<String> findNames() {
        return databaseClient.sql("SELECT name FROM customers")
                .map((row, metadata) -> row.get("name", String.class))
                .all();
    }
}
```

Trong ứng dụng Spring, có thể inject `DatabaseClient` nếu auto-configuration đã tạo bean tương ứng. Ví dụ này cho thấy ứng dụng không phải tự mở và đóng connection cho từng truy vấn theo cách thủ công.

### 4.3. `R2dbcEntityTemplate` và mapping infrastructure

Spring Data R2DBC cung cấp `R2dbcEntityTemplate` để thao tác với entity và aggregate theo cách tiếp cận Spring Data Relational. Hạ tầng mapping sử dụng metadata của entity, converter và mapping context để chuyển đổi giữa hàng dữ liệu và đối tượng Java.

Template hữu ích khi cần thao tác linh hoạt mà repository abstraction chưa diễn đạt thuận tiện. Với các thao tác CRUD phổ biến, repository thường là điểm bắt đầu dễ dùng hơn.

### 4.4. Reactive repository

Spring Data R2DBC hỗ trợ repository reactive thông qua các interface như `ReactiveCrudRepository`. Spring Boot có thể kích hoạt cấu hình repository dựa trên classpath và các package được dùng làm vùng quét.

Trong ứng dụng thông thường, đặt repository trong package hiện tại hoặc package con của class có `@SpringBootApplication` để cơ chế quét mặc định tìm thấy chúng. Không cần thêm `@EnableR2dbcRepositories` trong trường hợp mặc định.

Chỉ dùng `@EnableR2dbcRepositories` khi cần tùy chỉnh phạm vi quét hoặc cấu hình repository riêng. Nếu tự cấu hình, hãy xác định package rõ ràng và tránh đăng ký trùng repository.

### 4.5. Reactive transaction manager

Khi có `ConnectionFactory` và các điều kiện cần thiết, Spring Boot có thể cấu hình `R2dbcTransactionManager` để quản lý transaction reactive. Ứng dụng có thể dùng `@Transactional` trên phương thức trả về publisher hoặc dùng `TransactionalOperator` để thể hiện ranh giới transaction trong pipeline.

Transaction reactive truyền ngữ cảnh qua Reactor Context. Vì vậy, cần giữ các thao tác thuộc transaction trong cùng pipeline reactive và tránh chuyển sang `.block()` giữa chừng.

## 5. Tạo ứng dụng R2DBC tối thiểu

Phần này ghép các thành phần lại thành một ứng dụng Spring Boot đơn giản.

### 5.1. Cấu trúc package

Có thể tổ chức source code như sau:

```text
src/main/java/com/example/shop/
    ShopApplication.java
    customer/
        Customer.java
        CustomerRepository.java
        CustomerService.java
        CustomerController.java

src/main/resources/
    application.yml
    schema.sql
```

Class `ShopApplication` nằm ở package gốc `com.example.shop`. Các package `customer` là package con nên được component scan và repository scan mặc định tìm thấy.

### 5.2. Main application class

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Không cần tự gọi `ConnectionFactories.get(...)`, tự tạo `DatabaseClient` hoặc tự đăng ký từng repository trong cấu hình cơ bản. Spring Boot sẽ thiết lập hạ tầng từ dependency và property đã khai báo.

### 5.3. Entity

```java
package com.example.shop.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

`@Table` chỉ định tên bảng và `@Id` đánh dấu khóa chính. Tên thuộc tính còn lại được ánh xạ theo quy ước của Spring Data Relational hoặc có thể tùy chỉnh bằng annotation mapping tương ứng.

### 5.4. Repository

```java
package com.example.shop.customer;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByNameContaining(String fragment);
}
```

Spring Data tạo implementation cho repository lúc khởi tạo ApplicationContext. Bạn chỉ khai báo interface và các query method theo quy ước; không phải tự viết class implementation cho CRUD cơ bản.

### 5.5. Service

```java
package com.example.shop.customer;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Flux<Customer> searchByName(String fragment) {
        return repository.findByNameContaining(fragment);
    }

    public Mono<Customer> findByEmail(String email) {
        return repository.findByEmail(email);
    }

    public Mono<Customer> create(String name, String email) {
        Customer customer = new Customer(null, name, email);
        return repository.save(customer);
    }
}
```

Service giữ nguyên kiểu trả về reactive. `save()` trả về `Mono<Customer>`; đối tượng được phát ra khi thao tác lưu hoàn tất. Không gọi `.block()` trong service để lấy kết quả đồng bộ.

### 5.6. Controller WebFlux

Nếu dự án đã thêm `spring-boot-starter-webflux`, controller có thể trả trực tiếp publisher:

```java
package com.example.shop.customer;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Customer> search(@RequestParam String name) {
        return service.searchByName(name);
    }

    @GetMapping("/email/{email}")
    public Mono<Customer> findByEmail(@PathVariable String email) {
        return service.findByEmail(email);
    }

    @PostMapping
    public Mono<Customer> create(@RequestBody CreateCustomerRequest request) {
        return service.create(request.name(), request.email());
    }

    public record CreateCustomerRequest(String name, String email) {
    }
}
```

Controller minh họa việc Spring WebFlux có thể subscribe publisher và ghi kết quả vào HTTP response. Với API thực tế, cần bổ sung validation, xử lý lỗi và thiết kế response phù hợp.

## 6. Tự động khởi tạo schema bằng SQL script

Auto-configuration tạo hạ tầng kết nối và truy cập dữ liệu; nó không tự biết cần tạo những bảng nghiệp vụ nào. Trong môi trường phát triển hoặc ví dụ nhỏ, Spring Boot có thể chạy script `schema.sql` và `data.sql` khi khởi động.

Tạo file `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE
);
```

Có thể thêm dữ liệu mẫu trong `src/main/resources/data.sql`:

```sql
INSERT INTO customers (name, email)
VALUES ('An Nguyen', 'an@example.com');
```

Để yêu cầu Spring Boot chạy script với database không thuộc nhóm embedded, cấu hình:

```properties
spring.sql.init.mode=always
```

Chế độ mặc định và thứ tự chạy script phụ thuộc phiên bản Spring Boot cũng như loại database. Khi dùng script khởi tạo, hãy đọc tài liệu SQL initialization của đúng phiên bản dự án.

Không nên dùng script khởi tạo đơn giản như cơ chế migration lâu dài cho production nếu schema cần tiến hóa qua nhiều phiên bản. Với hệ thống thật, hãy chọn một chiến lược quản lý schema có version, kiểm soát thứ tự migration và quy trình rollback phù hợp. Công cụ migration có thể dùng kết nối JDBC riêng ngay cả khi ứng dụng truy cập dữ liệu nghiệp vụ bằng R2DBC; cần cấu hình và kiểm soát hai kết nối đó rõ ràng.

## 7. Pool connection và cấu hình nâng cao

Trong môi trường có tải thực tế, ứng dụng thường dùng connection pool để tái sử dụng kết nối. Spring Boot có thể cấu hình pooled connection factory khi thư viện pool R2DBC phù hợp có mặt trên classpath và pooling được bật theo cấu hình của phiên bản đang dùng.

Ví dụ các thuộc tính pool thường gặp:

```properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-idle-time=30m
```

Hãy xác nhận các thuộc tính có trong phiên bản Spring Boot của dự án và bảo đảm dependency `r2dbc-pool` được cung cấp nếu starter hiện tại không kéo nó vào. Không sao chép cấu hình pool giữa các phiên bản mà chưa kiểm tra metadata hoặc tài liệu cấu hình.

`max-size` cần được lựa chọn dựa trên năng lực database, số instance ứng dụng và số connection dành cho các dịch vụ khác. Tăng pool quá lớn có thể làm database quá tải; pool lớn không tự làm truy vấn nhanh hơn.

Khi cần tinh chỉnh cách tạo connection factory, Spring Boot cung cấp các điểm mở rộng phù hợp với phiên bản, hoặc ứng dụng có thể tự khai báo `ConnectionFactory` bean. Trước khi thay thế cấu hình mặc định, hãy xác định chính xác tùy chọn nào chưa đáp ứng yêu cầu để tránh phải tự quản lý nhiều thành phần không cần thiết.

## 8. Những điều không nên làm khi dùng auto-configuration

### 8.1. Không tự tạo lại các bean mặc định khi chưa cần

Trong ứng dụng cơ bản, không cần tự khai báo đồng thời `ConnectionFactory`, `DatabaseClient`, template và repository factory. Việc tạo bean trùng có thể khiến auto-configuration lùi lại hoặc làm ApplicationContext có nhiều ứng viên gây xung đột.

Hãy bắt đầu bằng dependency và property chuẩn. Chỉ thêm cấu hình thủ công khi có yêu cầu đặc biệt như nhiều database, tùy chọn driver riêng hoặc phạm vi repository tách biệt.

### 8.2. Không đặt class chính ở package quá sâu hoặc không liên quan

`@SpringBootApplication` mặc định dùng package của class chính làm gốc cho component scan và các package được suy ra cho một số cấu hình Spring Data. Nếu class chính nằm trong một package con hẹp, các service hoặc repository ở package ngang hàng có thể không được tìm thấy.

Ví dụ cấu trúc dễ quét:

```text
com.example.shop
    ShopApplication.java
    customer
        CustomerService.java
        CustomerRepository.java
    order
        OrderService.java
```

Nếu không thể tổ chức package như vậy, hãy cấu hình rõ phạm vi component scan hoặc repository scan bằng annotation tương ứng.

### 8.3. Không dùng nhầm driver hoặc URL

Các trường hợp sau thường gây lỗi khởi tạo:

- Chỉ thêm JDBC driver nhưng khai báo `spring.r2dbc.url`.
- Dùng URL `jdbc:postgresql://...` trong thuộc tính `spring.r2dbc.url`.
- Scheme trong URL không có driver R2DBC tương ứng trên classpath.
- Phiên bản driver không tương thích với R2DBC SPI hoặc Spring Boot đang dùng.

Hãy đối chiếu artifact driver và scheme URL theo tài liệu của nhà cung cấp driver.

### 8.4. Không gọi `.block()` trong luồng xử lý reactive

Repository reactive trả về `Mono` hoặc `Flux`. Gọi `.block()` trong event-loop thread có thể chặn luồng xử lý request và làm giảm khả năng chịu tải của WebFlux.

Hãy kết hợp publisher bằng `map`, `flatMap`, `zip` và các toán tử Reactor phù hợp. Nếu buộc phải tích hợp API blocking, cô lập phần blocking trên scheduler phù hợp và giới hạn concurrency.

### 8.5. Không mặc định R2DBC và JDBC dùng chung transaction

Nếu ứng dụng có cả `DataSource` JDBC và `ConnectionFactory` R2DBC, Spring Boot có thể thiết lập các hạ tầng riêng cho từng loại. Transaction manager của JDBC không tự động quản lý connection R2DBC và ngược lại.

Hãy xác định rõ stack nào sở hữu mỗi thao tác dữ liệu. Nếu nghiệp vụ cần cập nhật qua cả hai stack, cần thiết kế tính nhất quán và xử lý lỗi riêng; không giả định một `@Transactional` đơn lẻ tạo transaction phân tán.

## 9. Kiểm tra ứng dụng đã được tự cấu hình đúng chưa

Sau khi thêm dependency và property, hãy khởi động ứng dụng và xác nhận các thành phần hoạt động.

### 9.1. Kiểm tra điều kiện auto-configuration

Có thể chạy ứng dụng với tùy chọn `--debug` để Spring Boot in báo cáo điều kiện auto-configuration:

```bash
./gradlew bootRun --args='--debug'
```

Báo cáo cho biết cấu hình nào được áp dụng, cấu hình nào không được áp dụng và điều kiện nào chưa thỏa mãn. Trên Windows PowerShell, có thể truyền cùng tham số qua lệnh Gradle tương ứng trong môi trường của dự án.

Nếu cần xem sâu hơn, có thể bật log DEBUG cho package auto-configuration của Spring Boot. Hãy giới hạn log ở môi trường phát triển vì log chi tiết có thể rất dài.

### 9.2. Kiểm tra các bean được tạo

Trong quá trình debug, có thể kiểm tra ApplicationContext để xác nhận các bean cần thiết, chẳng hạn:

- `ConnectionFactory` đã được tạo.
- `DatabaseClient` có thể được inject.
- Repository interface đã có implementation proxy.
- Transaction manager phù hợp đã được đăng ký nếu ứng dụng cần transaction.

Không cần thêm endpoint debug vào production chỉ để kiểm tra các bean này. Có thể dùng debugger, test context hoặc báo cáo điều kiện auto-configuration.

### 9.3. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không có bean `ConnectionFactory` | Thiếu driver R2DBC, URL không hợp lệ hoặc auto-configuration không được kích hoạt | Kiểm tra dependency, `spring.r2dbc.url` và condition report |
| Không kết nối được database | Database chưa chạy, sai host/port, tên database hoặc thông tin xác thực | Kiểm tra trạng thái database, network và credentials |
| Không tìm thấy repository bean | Repository nằm ngoài vùng scan hoặc repository auto-configuration không thỏa điều kiện | Kiểm tra package của class chính, dependency và repository scan |
| Không tìm thấy bảng | Schema chưa được tạo hoặc script initialization chưa chạy | Kiểm tra `schema.sql`, `spring.sql.init.mode` và schema database |
| Lỗi kiểu dữ liệu hoặc mapping | Kiểu cột không tương thích hoặc entity mapping chưa đúng | Đối chiếu kiểu SQL, thuộc tính entity và hỗ trợ của driver |
| Pool cạn hoặc chờ connection lâu | Pool quá nhỏ, connection không được giải phóng đúng cách hoặc database quá tải | Theo dõi pool metrics, thời gian truy vấn và giới hạn concurrency |

## 10. Kiểm thử ứng dụng sử dụng R2DBC

Spring Boot cung cấp các tiện ích kiểm thử cho Spring Data R2DBC. `@DataR2dbcTest` phù hợp với kiểm thử lát cắt tập trung vào mapping và repository; `@SpringBootTest` phù hợp khi cần kiểm tra toàn bộ cấu hình ứng dụng và các thành phần tích hợp.

Ví dụ một repository test ở mức khái niệm:

```java
@DataR2dbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindCustomerByEmail() {
        // Chuẩn bị dữ liệu trong database kiểm thử,
        // gọi repository và xác nhận publisher phát ra kết quả.
    }
}
```

Test thực tế cần có database R2DBC phù hợp, schema và dữ liệu kiểm thử. Không phải database nhúng nào cũng có driver R2DBC tương đương. Với database production như PostgreSQL, có thể dùng Testcontainers nếu dự án đã thiết lập môi trường Docker và driver tương thích.

Khi kiểm thử publisher, dùng các công cụ như `StepVerifier` để xác nhận giá trị, thứ tự phát dữ liệu, completion và lỗi mà không phải gọi `.block()` trong code ứng dụng.

## 11. Quy trình khởi tạo một dự án mới

Có thể thực hiện theo trình tự sau:

1. Chọn phiên bản Spring Boot phù hợp với JDK và các thư viện của dự án.
2. Thêm `spring-boot-starter-data-r2dbc`.
3. Thêm driver R2DBC đúng với database, ví dụ PostgreSQL R2DBC.
4. Nếu cần HTTP API reactive, thêm Spring WebFlux; nếu không, chỉ thêm web stack khi có nhu cầu.
5. Đặt class `@SpringBootApplication` tại package gốc của ứng dụng.
6. Khai báo `spring.r2dbc.url`, username và password trong cấu hình phù hợp với môi trường.
7. Tạo entity và repository trong package được quét.
8. Tạo schema bằng script khởi tạo hoặc công cụ migration.
9. Khởi động ứng dụng, xem condition report nếu auto-configuration chưa hoạt động như mong đợi.
10. Kiểm thử repository, transaction và kết nối với database thực tế.

## 12. Luồng hoạt động tổng quát

```mermaid
flowchart TD
    A[Thêm Spring Data R2DBC starter] --> B[Thêm driver R2DBC]
    B --> C[Khai báo spring.r2dbc.*]
    C --> D[SpringApplication khởi động]
    D --> E[@EnableAutoConfiguration kiểm tra điều kiện]
    E --> F[Tạo ConnectionFactory]
    F --> G[Cấu hình DatabaseClient và mapping infrastructure]
    G --> H[Quét và tạo repository]
    H --> I[Ứng dụng sử dụng Mono / Flux]
    I --> J[Driver thực thi I/O với database]
```

Sơ đồ thể hiện thứ tự khái quát. Các auto-configuration cụ thể có thể được đánh giá theo nhiều điều kiện và thứ tự nội bộ khác nhau tùy phiên bản Spring Boot.

## 13. Kết luận

Để khởi tạo Spring Data R2DBC bằng cơ chế tự cấu hình của Spring Boot, hãy thêm starter R2DBC, thêm driver đúng loại, khai báo `spring.r2dbc.*` và đặt class ứng dụng ở package gốc hợp lý. Spring Boot sẽ tự cấu hình connection factory cùng hạ tầng Spring Data cần thiết khi các điều kiện tương ứng được thỏa mãn.

Bạn chỉ cần viết cấu hình thủ công khi có yêu cầu đặc biệt như nhiều database, driver option riêng hoặc phạm vi repository tùy chỉnh. Khi gặp lỗi khởi động, hãy kiểm tra dependency, URL, package scan và condition report trước khi thay thế toàn bộ auto-configuration. Cách làm này giữ ứng dụng gọn, dễ bảo trì và vẫn cho phép mở rộng cấu hình khi nhu cầu thực tế xuất hiện.
