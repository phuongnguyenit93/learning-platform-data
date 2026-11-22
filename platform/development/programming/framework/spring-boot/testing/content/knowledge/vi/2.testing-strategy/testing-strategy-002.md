# Phân bổ unit test, slice test và integration test theo kiến trúc Spring Boot

## 1. Mục tiêu và nguyên tắc

Bài này trả lời câu hỏi: trong một hệ thống Spring Boot, **hành vi nào nên kiểm bằng unit test, hành vi nào cần slice test, và đường đi nào bắt buộc có integration test?** Việc phân bổ dựa trên *ranh giới kiến trúc, loại lỗi có thể xảy ra và chi phí phản hồi*, thay vì ấn định một tỉ lệ cứng cho mọi dự án.

Sau khi học, bạn có thể:
- Nhìn vào sơ đồ tầng hoặc hexagonal/clean architecture để đặt test tại đúng ranh giới.
- Chọn JUnit 5 + Mockito (unit), `@WebMvcTest`/`@DataJpaTest` (slice), `@SpringBootTest` (integration) và biết mỗi loại **không** chứng minh được điều gì.
- Thiết kế bộ test cho một chức năng từ HTTP tới database mà không lặp cùng một phép kiểm ở mọi tầng.
- Lập chính sách chạy test trên CI theo mức rủi ro thay vì theo số lượng annotation.

Ví dụ phía dưới dùng **Java 17, Maven, Spring Boot 3.5.7, JUnit Jupiter, Mockito**. Spring Boot 4 có thay đổi module/package của một số annotation kiểm thử; khi dùng Boot 4, tra tài liệu đúng phiên bản để cập nhật dependency/import. **Chiến lược phân bổ theo ranh giới không thay đổi.**

## 2. Đọc kiến trúc trước khi chọn loại test

Ứng dụng MVC đơn giản:

```text
HTTP + JSON
    |
    v
CustomerController (web adapter: route, body, status)
    |
    v
CustomerService (application/use case: quy tắc nghiệp vụ)
    |
    v
CustomerRepository (outbound port / Spring Data adapter)
    |
    v
JPA + SQL database
```

Trong hexagonal/clean architecture, `CustomerService` nên phụ thuộc vào *interface port* và không phụ thuộc trực tiếp HTTP/JPA. Trong kiến trúc phân tầng truyền thống, có thể dùng Spring Data repository làm phụ thuộc của service; nguyên tắc kiểm thử vẫn là chọn **ranh giới nhỏ nhất đủ phát hiện lỗi cần quan sát**.

| Loại | Khởi động gì? | Tập trung chứng minh | Không chứng minh |
| --- | --- | --- | --- |
| **Unit** | Đối tượng Java, JUnit/Mockito; không cần Spring context | Quy tắc, nhánh, trạng thái, tương tác với port giả | Mapping MVC, dependency injection, SQL, serialization |
| **Slice** | Một phần Spring `ApplicationContext` và một nhóm auto-configuration | Hợp đồng của *một adapter/tầng*: HTTP, JSON, validation, JPA query, mapping | Toàn bộ chuỗi request → service thật → DB thật |
| **Integration** | Nhiều tầng cùng nhau; thường `@SpringBootTest` và hạ tầng thực hoặc tương đương | Bean wiring, transaction, cấu hình, hành trình xuyên tầng, protocol/SQL thực | Mọi tổ hợp quy tắc nghiệp vụ nếu chỉ kiểm một số luồng |

Lưu ý thuật ngữ: `@DataJpaTest` vẫn tích hợp JPA với một database, nhưng trong phân loại **theo phạm vi Spring Boot** nó là *persistence slice*. “Integration” trong bài này chỉ phép thử nối nhiều tầng hoặc hạ tầng có ý nghĩa thực tế. Phân loại này giúp tránh tranh cãi tên gọi khi thiết kế test.

## 3. Bản đồ phân bổ theo trách nhiệm kiến trúc

| Thành phần / rủi ro | Test mặc định nên có | Khi nào nâng lên integration |
| --- | --- | --- |
| Domain: tính giá, giới hạn, chuyển trạng thái, invariant | Unit, không Spring; dữ liệu biên và case sai | Quy tắc phụ thuộc isolation, transaction hoặc nhiều service thật |
| Application service/use case | Unit, mock/fake **port đầu ra**, assert kết quả và side effect cốt lõi | `@Transactional`, retry, event, transaction boundary hoặc chuỗi bean có nguy cơ cấu hình sai |
| REST controller, request/response, status, exception handler | `@WebMvcTest(Controller.class)` + `MockMvc`, mock service | Security filter thực, route đa tầng, serialization + database, full HTTP stack |
| Repository/JPA mapping, JPQL, constraint, query | `@DataJpaTest`, chạy entity/repository với DB | SQL/dialect/lock/migration đặc thù production; dùng cùng DB engine qua Testcontainers |
| HTTP client/adapter kết nối hệ khác | Unit cho chuyển đổi dữ liệu; slice/client test với stub HTTP | TLS/auth/network timeout, protocol và contract với hệ thật/staging |
| Security, transaction, caching, message broker, scheduling | Slice có mục tiêu nếu hỗ trợ; thêm integration tập trung | Khi behavior phụ thuộc toàn context, AOP/proxy, ACL, broker hoặc đồng bộ bất đồng bộ |
| Luồng nghiệp vụ quan trọng, không thể mất dữ liệu | Unit cho mọi nhánh + vài slice tại adapter + integration “happy path” và failure trọng yếu | Cross-service contract/E2E smoke cho ranh giới triển khai |

**Quy tắc chọn:** lỗi thuần thuật toán → unit; lỗi chuyển đổi/hợp đồng một adapter → slice; lỗi chỉ xuất hiện khi **hai phần thật tương tác** → integration. Một hành vi có thể cần hơn một test nếu chúng bảo vệ **những rủi ro khác nhau**.

Không coi mock xác nhận lời gọi repository là bằng chứng dữ liệu được lưu. Không coi `@WebMvcTest` là bằng chứng service hoạt động. Không coi `@SpringBootTest` là tự động kiểm được tất cả các nhánh ngoại lệ.

## 4. Phân bổ theo luồng chức năng: đăng ký khách hàng

Giả sử API `POST /customers` nhận email, service chuẩn hóa về chữ thường, kiểm tra trùng và lưu database.

| Kịch bản | Test chính | Lý do |
| --- | --- | --- |
| Email chứa khoảng trắng/chữ hoa phải chuẩn hóa | **Unit service** | Quy tắc thuần dữ liệu và logic service |
| Email rỗng/sai dạng bị từ chối | **Unit service** | Rất nhiều dữ liệu biên, chạy nhanh |
| Email trùng không gọi `save` | **Unit service** | Quyết định ứng dụng; mock port kiểm tương tác |
| JSON request được bind, HTTP trả 201, `Location` và response đúng | **Web slice** | Hợp đồng HTTP/Jackson/`MockMvc` |
| Lỗi nghiệp vụ được map sang 400/409 | **Web slice** | Exception handler thuộc web adapter |
| `findByEmail`, unique constraint, mapping JPA | **JPA slice** | Hợp đồng persistence + database |
| Request thật qua controller → service thật → repository thật lưu được bản ghi | **Integration** | Chứng minh wiring và transaction xuyên tầng |
| DB production dùng Postgres, query đặc thù hoặc migration | **Integration với Postgres Testcontainers** | H2 không chứng minh hành vi dialect/DDL production |
| Phân quyền cho endpoint / JWT filter | **Security-focused integration** khi có cấu hình thực | Quyết định nằm tại security chain và cấu hình |

Tỉ lệ khởi đầu minh họa cho **100 tình huống kiểm thử**: khoảng 65 unit, 25 slice, 10 integration. Đây là *tham số lập kế hoạch, không phải KPI*: domain nhiều thuật toán có thể cần 85% unit; hệ CRUD hoặc tích hợp nặng có thể cần nhiều slice/integration hơn. Đếm **rủi ro được bảo vệ**, không ép số test cho vừa phần trăm.

## 5. Ví dụ Maven chạy được: một đường đi, bốn mức bảo vệ

### 5.1. Cấu trúc dự án

```text
pom.xml
src/main/java/com/example/testing/
  TestingApplication.java
  Customer.java
  CustomerRepository.java
  CustomerService.java
  CustomerController.java
  ApiErrorHandler.java
src/test/java/com/example/testing/
  CustomerServiceTest.java
  CustomerControllerTest.java
  CustomerRepositoryTest.java
  CustomerFlowIntegrationTest.java
```

`pom.xml`: ví dụ pin Spring Boot 3.5.7 để import bên dưới nhất quán; khi dùng dự án thật, đồng bộ phiên bản với BOM của dự án.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>testing-strategy</artifactId>
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
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

`TestingApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

`Customer.java`:

```java
package com.example.testing;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {} // JPA cần constructor không tham số

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

`CustomerRepository.java`:

```java
package com.example.testing;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    boolean existsByEmail(String email);
    Optional<Customer> findByEmail(String email);
}
```

`CustomerService.java` chứa use case. Kiểm tra email dưới đây cố ý đơn giản cho bài học; production cần chính sách validation, chuẩn hóa và xử lý uniqueness phù hợp.

```java
package com.example.testing;

import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public RegistrationReceipt register(String rawEmail) {
        String email = rawEmail == null
                ? ""
                : rawEmail.trim().toLowerCase(Locale.ROOT);

        if (!email.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        if (repository.existsByEmail(email)) {
            throw new IllegalStateException("Email đã tồn tại");
        }

        Customer saved = repository.save(new Customer(email));
        return new RegistrationReceipt(saved.getId(), saved.getEmail());
    }

    public record RegistrationReceipt(Long id, String email) {}
}
```

`CustomerController.java` chỉ lo HTTP; mọi quy tắc đăng ký nằm ở service.

```java
package com.example.testing;

import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/customers")
public class CustomerController {
    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerService.RegistrationReceipt> create(
            @RequestBody CreateRequest request) {
        var result = service.register(request.email());
        return ResponseEntity
                .created(URI.create("/customers/" + result.id()))
                .body(result);
    }

    public record CreateRequest(String email) {}
}
```

`ApiErrorHandler.java` quyết định mã HTTP cho lỗi nghiệp vụ.

```java
package com.example.testing;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> duplicated(IllegalStateException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", ex.getMessage()));
    }
}
```

### 5.2. Unit test: quy tắc service, không khởi động Spring

`src/test/java/com/example/testing/CustomerServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock CustomerRepository repository;

    @Test
    void normalizesEmailBeforeSaving() {
        var service = new CustomerService(repository);
        when(repository.save(any(Customer.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        var result = service.register("  A@Example.COM  ");

        assertEquals("a@example.com", result.email());
        verify(repository).existsByEmail("a@example.com");
        verify(repository).save(
                org.mockito.ArgumentMatchers.argThat(c ->
                        "a@example.com".equals(c.getEmail())));
    }

    @Test
    void refusesDuplicateWithoutSaving() {
        var service = new CustomerService(repository);
        when(repository.existsByEmail("a@example.com")).thenReturn(true);

        assertThrows(IllegalStateException.class,
                () -> service.register("a@example.com"));

        verify(repository, never()).save(any(Customer.class));
    }

    @Test
    void invalidEmailDoesNotTouchPersistence() {
        var service = new CustomerService(repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.register("   "));

        verifyNoInteractions(repository);
    }
}
```

Ở đây Mockito tạo repository giả, nên kiểm được rẽ nhánh và lời gọi. **Không thể** từ bài unit này kết luận Hibernate lưu dữ liệu, constraint chạy hoặc `@Transactional` có hiệu lực. Test `normalizesEmailBeforeSaving` để mock trả về entity chưa có ID là chủ ý: test chỉ khẳng định chuẩn hóa, không giả lập khả năng sinh ID của database.

### 5.3. Web slice test: HTTP contract và MVC

`src/test/java/com/example/testing/CustomerControllerTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CustomerController.class)
class CustomerControllerTest {
    @Autowired MockMvc mvc;
    @MockitoBean CustomerService service;

    @Test
    void createsHttpResponse() throws Exception {
        when(service.register("a@example.com")).thenReturn(
                new CustomerService.RegistrationReceipt(42L, "a@example.com"));

        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"a@example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/customers/42"))
                .andExpect(jsonPath("$.email").value("a@example.com"));
    }

    @Test
    void convertsBusinessErrorToConflict() throws Exception {
        when(service.register("a@example.com"))
                .thenThrow(new IllegalStateException("Email đã tồn tại"));

        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"a@example.com\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("Email đã tồn tại"));
    }
}
```

`@WebMvcTest` nạp cấu hình MVC, controller, advice và `MockMvc`, thay service bằng `@MockitoBean`. Nó bắt lỗi route, HTTP status, binding, JSON, handler; **không** chạy use case thật hoặc database. Với Spring Security trên classpath, slice thường có filter chain; nên dùng Spring Security test support và test xác thực/phân quyền có chủ đích, không tùy tiện tắt filter để có test xanh.

### 5.4. JPA slice test: repository và mapping thật

`src/test/java/com/example/testing/CustomerRepositoryTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired CustomerRepository repository;

    @Test
    void storesAndFindsByEmail() {
        Customer saved = repository.saveAndFlush(
                new Customer("db@example.com"));

        assertNotNull(saved.getId());
        Customer loaded = repository.findByEmail("db@example.com")
                .orElseThrow();
        assertEquals("db@example.com", loaded.getEmail());
    }
}
```

`@DataJpaTest` chỉ tạo persistence slice (entity, Spring Data JPA, transaction, database), mặc định rollback sau test. Vì dependency H2 hiện diện, ví dụ dùng H2 nhúng. Chọn loại test này để kiểm query và mapping; nếu production dùng PostgreSQL với JSONB, collation, lock hoặc migration đặc thù, **thay H2 bằng PostgreSQL Testcontainers** cho phép thử cần độ trung thực cao. Chú ý rollback sau test không thay thế hoàn toàn việc dọn dữ liệu cho test đa luồng/HTTP server thật.

### 5.5. Integration test: một luồng xuyên tầng, bean thật

`src/test/java/com/example/testing/CustomerFlowIntegrationTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerFlowIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired CustomerRepository repository;

    @Test
    @Transactional
    void postCreatesCustomerThroughRealServiceAndRepository() throws Exception {
        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"FLOW@Example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.email").value("flow@example.com"));

        assertTrue(repository.findByEmail("flow@example.com").isPresent());
    }
}
```

Đây là **full Spring context + MockMvc**, không khởi động HTTP server thật. Nó chứng minh controller, service, JPA và auto-configuration nối được với nhau. `@Transactional` ở test này cho phép rollback với mô hình MockMvc cùng luồng; nếu chuyển thành `@SpringBootTest(webEnvironment = RANDOM_PORT)` và gọi qua HTTP client, request của server chạy transaction riêng, **transaction tại test không rollback thao tác của server**. Khi đó phải cô lập dữ liệu bằng schema/container riêng, cleanup rõ ràng hoặc identifier duy nhất.

### 5.6. Chạy và hiểu kết quả

Đặt mọi file đúng đường dẫn ở trên, có JDK 17+ và Maven:

```bash
mvn -q -Dtest=CustomerServiceTest test
mvn -q -Dtest=CustomerControllerTest test
mvn -q -Dtest=CustomerRepositoryTest test
mvn -q -Dtest=CustomerFlowIntegrationTest test
mvn -q test
```

Bốn lệnh đầu lần lượt chạy một lớp test; lệnh cuối chạy toàn bộ 4 lớp vì tên kết thúc bằng `Test`. Điều kiện thành công là Maven trả exit code 0 và các assertion đều qua; thông tin log/summary phụ thuộc môi trường nên không giả định một stdout cố định. Code nguồn *phải* được biên dịch với dependencies Maven; lệnh `javac` đơn lẻ không có classpath Spring/JUnit sẽ không biên dịch được, vì vậy `mvn test` là lệnh tái lập đúng cho ví dụ.

Nếu thử thủ công, chạy `mvn spring-boot:run` rồi gửi HTTP:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"email":"A@Example.com"}'
```

Với H2 trống, endpoint trả **201 Created**, header `Location: /customers/1` (ID có thể khác nếu đã có dữ liệu), body JSON chứa `id` và email `a@example.com`. Gửi lại cùng email sẽ trả **409 Conflict**. Ví dụ sử dụng H2 in-memory và không nhằm mô tả cơ chế lưu trữ lâu dài sau khi ứng dụng dừng.

## 6. Khi nào cần test sâu hơn các slice mẫu?

**Database:** H2 đủ cho CRUD cơ bản và mapping giản đơn, nhưng có thể khác PostgreSQL/MySQL về SQL dialect, collation, isolation, JSON/array, index và constraint. Với code phụ thuộc các yếu tố đó, chạy repository/integration tests trên database cùng loại và phiên bản gần production, có thể dùng Testcontainers + `@ServiceConnection` (Spring Boot phiên bản tương thích) hoặc `@DynamicPropertySource`; thêm dependency Testcontainers/JUnit và Docker khi triển khai. Test migration bằng Flyway/Liquibase trên schema sạch và kiểm rằng migration thật được chạy.

**Giao tiếp giữa service:** Unit mock HTTP client để kiểm quyết định retry/timeout; client-level test với stub HTTP để kiểm request/response, lỗi 4xx/5xx, header, serialization; contract test để kiểm hai phía hiểu đúng schema; số ít E2E smoke qua deployment thực để phát hiện routing, auth, DNS và compatibility. Không nên thay hàng trăm unit tests bằng một E2E test khó chẩn đoán.

**Event, queue, transaction:** Với Kafka/RabbitMQ/outbox, test unit logic chọn event; integration xác nhận serialization, publish/consume, idempotency, retry, dead-letter và việc commit/rollback. Mock broker không chứng minh delivery semantics hay hành vi concurrency.

**Security:** Web slice cho 401/403 và role policy tại endpoint; integration cho `SecurityFilterChain`, filter order, token converter, method security và endpoint critical. Cần phân biệt “không đăng nhập” (401) và “đã xác thực nhưng thiếu quyền” (403) theo cấu hình thật.

**AOP/proxy:** `@Transactional`, `@Cacheable`, retry annotation và method security hoạt động qua Spring proxy/interceptor; unit gọi trực tiếp đối tượng thường không kích hoạt các cơ chế đó. Dùng integration test nhắm đúng behavior khi rủi ro nằm ở proxy.

## 7. Giữ bộ test nhanh, ổn định và đáng tin

1. **Danh mục hành vi trước, annotation sau.** Liệt kê quy tắc, adapter contract và ranh giới hạ tầng cho mỗi feature. Gắn mỗi rủi ro với một nơi kiểm tra chính; chỉ lặp khi lớp thứ hai bảo vệ rủi ro khác.
2. **Mock tại ranh giới ngoài.** Mock repository/HTTP port trong unit service; trong web slice mock application service. Tránh mock chính đối tượng đang kiểm thử, mock JPA internals hoặc stubbing mọi lời gọi khiến test chỉ chép implementation.
3. **Ưu tiên assert kết quả có ý nghĩa.** Với unit, assert dữ liệu và side effect quan trọng; với MVC, assert status, body/header; với JPA, assert bản ghi/query/constraint; với integration, assert trạng thái cuối quan sát được. `verify(...)` chỉ hữu ích khi tương tác là một phần của contract.
4. **Dữ liệu độc lập.** Mỗi test tự dựng fixture; giữ clock/UUID/port có thể kiểm soát; dùng fake clock thay `Thread.sleep`; không phụ thuộc thứ tự chạy, timezone máy hoặc ID tự tăng cố định.
5. **Tối ưu context cache.** Cùng cấu hình Spring test có thể tái sử dụng `ApplicationContext`. Lạm dụng `@DirtiesContext`, thay profiles/properties/`@MockitoBean` vô tội vạ làm test chậm. Nhưng đừng hi sinh cô lập chỉ để có cache hit.
6. **Tổ chức theo tầng và tốc độ.** CI trên PR nên chạy unit + slice và những integration cốt lõi; các luồng tốn hạ tầng chạy thêm ở merge/nightly, hoặc trên PR nếu thay đổi chạm trực tiếp ranh giới đó. “Flaky” phải được điều tra, không mặc định tăng retry để che giấu.
7. **Không đánh đồng coverage với chất lượng.** Line coverage có thể cao dù bỏ sót trạng thái, lỗi transaction hoặc lỗi API contract. Đánh giá thêm branch/boundary, mutation testing cho domain phức tạp, mức độ bắt lỗi quan trọng và thời gian feedback.
8. **Phân tách trách nhiệm rõ ràng.** Ví dụ controller chịu trách nhiệm HTTP, service chịu trách nhiệm chuẩn hóa/trùng, repository chịu trách nhiệm lưu; nếu một lớp ôm cả ba, khó tạo unit và slice test hiệu quả. Việc khó test có thể chỉ ra ranh giới kiến trúc chưa tốt.

### Các lỗi phân bổ thường gặp và cách sửa

| Dấu hiệu | Hệ quả | Hành động |
| --- | --- | --- |
| Mọi lớp test dùng `@SpringBootTest` | Chậm, khó khoanh vùng lỗi, nhiều DB setup | Thay test logic bằng unit; controller/JPA bằng slice; giữ full-context cho wiring |
| Controller test mock `MockMvc` hoặc service mock chính nó | Không kiểm được HTTP thật của Spring hoặc quyết định thật | Dùng `MockMvc` được auto-configure; mock collaborator nằm ngoài boundary |
| Service unit test khẳng định “DB đã lưu” vì `verify(save)` | Dễ bỏ sót mapping, DDL, transaction | Bổ sung `@DataJpaTest` và một integration xuyên tầng |
| Chỉ có end-to-end happy path | Nhánh lỗi khó bao phủ; lỗi phát hiện muộn | Dồn ma trận input/edge case xuống unit; E2E cho một số journey sống còn |
| Chỉ dùng H2 cho SQL production phức tạp | Bỏ qua lỗi dialect/constraint/migration | Testcontainers với cùng DB engine cho vùng rủi ro |
| Tests tự phụ thuộc record tạo từ test khác | Chạy riêng/lặp dễ thất bại | Fixture riêng, transaction/cleanup/namespace test |
| Test qua RANDOM_PORT và kỳ vọng `@Transactional` tại test rollback server | Rò dữ liệu giữa lần chạy | Cô lập container/database hoặc cleanup |
| Chạy quá nhiều test y hệt ở 3 tầng | Tốn thời gian nhưng ít thêm bằng chứng | Phân biệt mục tiêu: rule / adapter contract / wiring |

## 8. Checklist áp dụng cho một module Spring Boot thực tế

Trước khi thêm test, trả lời theo thứ tự:

- **Bản đồ kiến trúc:** đầu vào (HTTP/event/job), use case, domain, port, adapter dữ liệu, hệ ngoài nằm ở đâu?
- **Rủi ro phải bắt:** nhánh nghiệp vụ, serialization/validation, SQL/dialect, transaction, security, retry/event, wiring?
- **Ranh giới nhỏ nhất:** không cần Spring → unit; cần đúng một adapter Spring → slice; cần nhiều bean/hạ tầng tương tác → integration.
- **Độ trung thực:** mock/fake đủ chưa, hay cần database/broker/server thật? Nếu dùng H2, có giả định production nào chưa được kiểm chứng?
- **Bằng chứng độc lập:** test assert output và trạng thái quan sát được, không buộc vào nội bộ vô ích; fixtures độc lập, test chạy lặp ổn định?
- **Ngân sách CI:** unit và slice phản hồi nhanh; critical integration kiểm lúc PR; thêm full-suite trước release/nếu rủi ro yêu cầu.

Một feature có chiến lược tốt thường có **nhiều unit test cho nhánh nghiệp vụ, vài slice test cho hợp đồng adapter, và ít integration test chọn lọc cho đường nối có giá trị cao**. Cấu trúc này tạo phản hồi nhanh, chỉ ra đúng tầng hỏng và vẫn bắt được lỗi cấu hình/SQL vốn không xuất hiện khi mock.

## 9. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Boot reference phiên bản hiện hành (kiểm tra thay đổi package khi chuyển sang Boot 4): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
