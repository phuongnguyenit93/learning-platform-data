# Quản lý thực thể bằng Redis Repository và chỉ mục phụ

Spring Data Redis không chỉ hỗ trợ truy cập Redis bằng các lệnh thấp như `GET`, `SET`, `HSET` hay `SADD`. Với **Redis Repository**, ứng dụng Java có thể quản lý thực thể theo mô hình quen thuộc của Spring Data: khai báo entity, định nghĩa interface repository kế thừa `CrudRepository`, sau đó sử dụng các method `save`, `findById`, `findAll` và `deleteById`. Khi cần tìm entity bằng thuộc tính thay vì ID, **chỉ mục phụ (secondary index)** giúp Redis Repository tìm ra những ID phù hợp mà không phải tự duyệt toàn bộ tập key.

Bài thực hành này xây dựng một ứng dụng nhỏ quản lý **khách hàng**. Mỗi khách hàng có ID, họ tên, email đã chuẩn hóa, trạng thái, thành phố và TTL tùy chọn. Chúng ta sẽ tạo entity bằng `@RedisHash` và `@Id`, đánh chỉ mục một số thuộc tính bằng `@Indexed`, định nghĩa repository có derived query, hiện thực service CRUD và kiểm thử bằng Redis thật.

Quan trọng: Redis Repository là một cách ánh xạ entity lên cấu trúc dữ liệu Redis, **không phải hệ quản trị quan hệ**. Chỉ mục phụ của Spring Data Redis phục vụ những truy vấn được hỗ trợ dựa trên thuộc tính đã đánh index; chúng không tự cung cấp unique constraint, JOIN, truy vấn SQL tùy ý, full-text search hoặc giao dịch ACID cho một quy trình thay đổi nhiều key.

## 1. Mục tiêu thực hành

Sau bài này, người học có thể:

1. Cấu hình một ứng dụng Spring Boot sử dụng Spring Data Redis Repositories.
2. Ánh xạ đối tượng Java thành Redis Hash với `@RedisHash` và `@Id`.
3. Khai báo secondary index bằng `@Indexed` cho các trường cần tìm kiếm.
4. Tạo interface `CrudRepository<Customer, String>` và derived query theo các trường đã được đánh chỉ mục.
5. Thực hiện tạo, đọc, cập nhật và xóa entity mà không tự viết `HSET`/`SADD` trong service.
6. Quan sát cách secondary index gắn giá trị thuộc tính với ID của entity.
7. Thử nghiệm cập nhật thuộc tính được đánh index và phân biệt dữ liệu thực thể với dữ liệu chỉ mục.
8. Sử dụng `@TimeToLive` có chủ đích, hiểu tác động của expiration đến index cleanup.
9. Nhận diện giới hạn về uniqueness, consistency, truy vấn và vận hành.
10. Viết integration test với Redis thực qua Testcontainers.

### Bối cảnh ứng dụng

Giả sử API cần những chức năng:

| Nghiệp vụ | Ví dụ | Cách truy cập |
| --- | --- | --- |
| Thêm khách hàng | Tạo khách hàng ở Hà Nội | `repository.save(customer)` |
| Lấy theo ID | Xem khách hàng `c-42` | `repository.findById(id)` |
| Tìm theo trạng thái | Danh sách `ACTIVE` | `findByStatus("ACTIVE")` |
| Tìm theo thành phố | Danh sách `HANOI` | `findByCity("HANOI")` |
| Kết hợp hai điều kiện | Khách hàng `ACTIVE` tại `HANOI` | `findByStatusAndCity(...)` |
| Tìm theo email chuẩn hóa | Tìm những bản ghi có email tương ứng | `findByEmailNormalized(...)` |
| Sửa thành phố | `HANOI` thành `DANANG` | Đọc entity, thay đổi trường, `save` |
| Xóa khách hàng | Xóa `c-42` | `deleteById(id)` |

Các giá trị trạng thái, thành phố và email là thuộc tính phục vụ truy vấn. ID là khóa chính để truy cập một entity trực tiếp.

## 2. Redis Repository lưu dữ liệu như thế nào?

Với một entity được khai báo `@RedisHash("customers")`, Spring Data Redis ánh xạ dữ liệu entity thành **Redis Hash**, thường có key theo keyspace và ID:

~~~text
customers:<customerId>
   |
   +-- id               = <customerId>
   +-- fullName         = ...
   +-- emailNormalized  = ...
   +-- status           = ACTIVE
   +-- city             = HANOI
   +-- ttlSeconds       = ...
~~~

Để truy vấn theo `status` hoặc `city`, Spring Data Redis có thể duy trì những **Set chứa ID** theo giá trị thuộc tính đã đánh index:

~~~text
                         Redis database

Entity Hash:

customers:c-001 ──────> {status: ACTIVE, city: HANOI,  ...}
customers:c-002 ──────> {status: ACTIVE, city: DANANG, ...}
customers:c-003 ──────> {status: LOCKED, city: HANOI, ...}

Secondary index (mô hình khái niệm):

customers:status:ACTIVE  ──> {c-001, c-002}
customers:status:LOCKED  ──> {c-003}

customers:city:HANOI    ──> {c-001, c-003}
customers:city:DANANG   ──> {c-002}
~~~

Các tên key index trong sơ đồ nhằm giải thích cơ chế; **không nên coi chúng là API lưu trữ ổn định để code business trực tiếp sửa bằng lệnh `SADD`/`SREM`**. Spring Data Redis còn duy trì metadata cần thiết để theo dõi index của entity; chi tiết key thực tế phụ thuộc cách mapping và phiên bản.

Ví dụ truy vấn theo một thuộc tính:

~~~text
findByStatus("ACTIVE")
        |
        v
Tra chỉ mục trạng thái ACTIVE
        |
        v
Lấy tập ID {c-001, c-002}
        |
        v
Đọc Hash tương ứng
        |
        v
Trả List<Customer>
~~~

Với hai điều kiện được hỗ trợ, hệ thống có thể kết hợp những tập ID ứng với các index để tìm entity phù hợp. Ví dụ tập `ACTIVE` giao với tập `HANOI` cho `c-001`.

### Vì sao cần đánh index?

Nếu chỉ có Hash `customers:c-001`, Redis không tự biết “những khách hàng nào có `status=ACTIVE`”. Truy cập theo ID rất nhanh vì key đã biết. Nhưng tìm theo một field tùy ý cần một cấu trúc ánh xạ bổ sung hoặc phải quét dữ liệu.

Annotation `@Indexed` cho phép Spring Data Redis duy trì một secondary index cho field được chỉ định, giúp các derived query phù hợp không phải do service tự `SCAN` mọi entity rồi deserialize từng bản ghi.

**Đổi lại**, mỗi thao tác save/delete có thể phát sinh việc cập nhật index, sử dụng thêm bộ nhớ và thêm lệnh Redis. Vì vậy chỉ đánh index các trường thực sự phục vụ truy vấn.

## 3. Chuẩn bị ứng dụng Spring Boot và Redis

Ví dụ dùng Java 21, Spring Boot 3.x, Spring Data Redis và Gradle Groovy DSL. Redis cần được khởi động trong môi trường thử nghiệm riêng; có thể dùng Redis cài cục bộ, Docker hoặc một Redis development server.

### 3.1. Dependencies

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<SPRING_BOOT_VERSION>'
    id 'io.spring.dependency-management' version '<DEPENDENCY_MANAGEMENT_VERSION>'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các placeholder phiên bản trong đoạn `plugins` cần thay bằng những phiên bản Spring Boot/dependency-management tương thích theo dự án đang sử dụng. Nếu dự án đã có Spring Boot plugin và BOM, chỉ cần bổ sung những dependency còn thiếu; không sao chép thêm một bộ plugin thứ hai.

`spring-boot-starter-data-redis` đưa Spring Data Redis và Redis client cần thiết vào ứng dụng; trong các cấu hình Spring Boot thường gặp, Lettuce là lựa chọn client mặc định. `spring-boot-starter-web` chỉ cần nếu làm thêm REST API; phần repository/service có thể chạy không cần web server.

### 3.2. Khởi động Redis development

Một lệnh Docker minh họa:

~~~bash
docker run --name redis-repository-lab \
  -p 127.0.0.1:6379:6379 \
  -d redis:7.2-alpine
~~~

Lệnh gắn port Redis vào loopback của máy chạy Docker để tránh chủ ý công bố một Redis thử nghiệm không có xác thực ra mạng ngoài. Không dùng cấu hình lab này cho production. Trong môi trường chia sẻ hoặc máy đã có dịch vụ trên port 6379, chọn port khác và cập nhật application configuration tương ứng.

Kiểm tra Redis:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

Khi kết nối thành công, phản hồi thông thường là `PONG`.

### 3.3. `application.yml`

~~~yaml
spring:
  application:
    name: redis-repository-lab
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Ví dụ là Redis standalone development. Với Redis có ACL/TLS, Sentinel hoặc Cluster, cần cấu hình phù hợp. **Repository không tự lo xác thực, bảo mật mạng hay khám phá topology**; nó sử dụng `RedisConnectionFactory` được ứng dụng cấu hình.

### 3.4. Bật Redis repositories

~~~java
package com.example.redis.repositorylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackages = "com.example.redis.repositorylab.repository"
)
public class RedisRepositoryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            RedisRepositoryLabApplication.class, args
        );
    }
}
~~~

`@EnableRedisRepositories` xác định package có repository interface cần Spring Data Redis tạo implementation. Khi dự án dựa hoàn toàn vào Spring Boot auto-configuration, có thể không cần annotation này; minh họa dùng nó để làm rõ loại repository đang bật và phạm vi scan.

Nếu ứng dụng đồng thời có JPA, MongoDB hoặc nhiều Spring Data store, cần thiết kế repository scanning rõ ràng để không tạo sự nhầm lẫn về repository thuộc store nào.

## 4. Khai báo entity `Customer`

Tạo file `src/main/java/com/example/redis/repositorylab/model/Customer.java`:

~~~java
package com.example.redis.repositorylab.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String fullName;

    @Indexed
    private String emailNormalized;

    @Indexed
    private String status;

    @Indexed
    private String city;

    @TimeToLive
    private Long ttlSeconds;

    protected Customer() {
        // Constructor phục vụ object mapping.
    }

    public Customer(
            String id,
            String fullName,
            String emailNormalized,
            String status,
            String city,
            Long ttlSeconds) {
        this.id = id;
        this.fullName = fullName;
        this.emailNormalized = emailNormalized;
        this.status = status;
        this.city = city;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmailNormalized() {
        return emailNormalized;
    }

    public void setEmailNormalized(String emailNormalized) {
        this.emailNormalized = emailNormalized;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

### Ý nghĩa annotation

| Annotation | Chức năng | Lưu ý |
| --- | --- | --- |
| `@RedisHash("customers")` | Chỉ định entity được ánh xạ lên Redis Hash thuộc keyspace `customers` | Không đồng nghĩa tạo bảng SQL |
| `@Id` | Đánh dấu thuộc tính định danh | Repository dùng ID cho `findById`/`deleteById` |
| `@Indexed` | Yêu cầu secondary index cho field | Tốn thêm bộ nhớ và thao tác cập nhật index |
| `@TimeToLive` | Sử dụng giá trị property để quản lý TTL của entity | Đơn vị mặc định của property số là giây; cần chính sách rõ |

Một entity có thể không cần TTL: khi không muốn entity tự hết hạn, hãy bỏ `@TimeToLive` hoặc thiết kế thời gian sống theo yêu cầu cụ thể. Trong bài này, `ttlSeconds` được đưa vào để thực hành hành vi expiration và các hệ quả đối với index.

**Không đặt `@Indexed` lên mọi field.** Các thuộc tính như `fullName` có thể không cần index nếu ứng dụng chỉ hiển thị theo ID và không truy vấn trực tiếp bằng tên. Ngay cả khi đánh index, Redis Repository không tự biến trường String thành công cụ tìm kiếm gần đúng, prefix matching hoặc full-text search.

### Vì sao chuẩn hóa dữ liệu trước khi lưu?

Giả sử các lần lưu cho cùng một trạng thái:

~~~text
ACTIVE
active
Active
 ACTIVE
~~~

Nếu ứng dụng coi chúng là một trạng thái nhưng lưu thành những chuỗi khác nhau, chúng có thể tạo nhiều giá trị index khác nhau. Tương tự, `Hanoi` và `HANOI` không đương nhiên cùng một điều kiện tìm kiếm.

Nên chuẩn hóa trạng thái, thành phố và email tại service hoặc một layer chuyên trách, trước khi gọi `save`. Cần chọn quy tắc chuẩn hóa đáp ứng nghiệp vụ; không tùy tiện chuyển đổi email quốc tế hóa hay tên riêng trong hệ thống có yêu cầu đa ngôn ngữ mà chưa xác định quy tắc.

## 5. Khai báo interface `CustomerRepository`

Tạo file `src/main/java/com/example/redis/repositorylab/repository/CustomerRepository.java`:

~~~java
package com.example.redis.repositorylab.repository;

import java.util.List;

import org.springframework.data.repository.CrudRepository;
import com.example.redis.repositorylab.model.Customer;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByStatus(String status);

    List<Customer> findByCity(String city);

    List<Customer> findByEmailNormalized(
        String emailNormalized
    );

    List<Customer> findByStatusAndCity(
        String status, String city
    );
}
~~~

Spring Data tạo implementation cho repository interface lúc chạy ứng dụng. Những method được kế thừa từ `CrudRepository`:

~~~java
repository.save(customer);
repository.findById(customerId);
repository.existsById(customerId);
repository.findAll();
repository.count();
repository.deleteById(customerId);
repository.delete(customer);
~~~

Những method tự khai báo `findByStatus`, `findByCity` và `findByEmailNormalized` yêu cầu Spring Data hiểu tên field và có secondary index phù hợp. `findByStatusAndCity` minh họa tìm theo hai thuộc tính đã được đánh index; với những biểu thức query phức tạp hơn, cần xác minh tập operator/điều kiện mà phiên bản Spring Data Redis của dự án hỗ trợ thay vì mặc định mọi cú pháp derived query của JPA đều được hỗ trợ.

### Chỉ mục phụ không có unique constraint

`@Indexed` trên `emailNormalized` chỉ giúp tìm các ID theo email, **không bảo đảm email là duy nhất**:

~~~text
customers:emailNormalized:alice@example.com
  └── có thể chứa ID c-101 và c-205
~~~

Vì thế repository dùng `List<Customer> findByEmailNormalized(...)` thay vì giả định luôn có đúng một bản ghi. Nếu nghiệp vụ yêu cầu email duy nhất, cần một cơ chế cấp phát/ràng buộc uniqueness nguyên tử được thiết kế riêng, chẳng hạn một bảng có unique constraint hoặc thao tác điều kiện phù hợp tại nơi quản lý nguồn sự thật. Việc service tự `findByEmailNormalized` rồi `save` **không nguyên tử** và có race khi nhiều instance cùng tạo khách hàng.

## 6. Thực hành CRUD qua service

Định nghĩa một service quản lý việc chuẩn hóa dữ liệu, tạo ID, gọi repository và kiểm tra đầu vào. Không gọi trực tiếp `SADD` hoặc `SREM` để sửa chỉ mục từ code nghiệp vụ; **Spring Data Redis repository phải là bên quản lý index tương ứng với entity**.

Tạo file `src/main/java/com/example/redis/repositorylab/service/CustomerService.java`:

~~~java
package com.example.redis.repositorylab.service;

import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.repository.CustomerRepository;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(
            String fullName,
            String email,
            String city) {
        String id = UUID.randomUUID().toString();

        Customer customer = new Customer(
            id,
            requireText(fullName, "fullName"),
            normalizeEmail(email),
            "ACTIVE",
            normalizeToken(city, "city"),
            3600L
        );

        return repository.save(customer);
    }

    public Customer getRequired(String id) {
        Objects.requireNonNull(id, "id");
        return repository.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException(
                    "Customer not found: " + id
                )
            );
    }

    public List<Customer> findActive() {
        return repository.findByStatus("ACTIVE");
    }

    public List<Customer> findByCity(String city) {
        return repository.findByCity(
            normalizeToken(city, "city")
        );
    }

    public List<Customer> findActiveByCity(String city) {
        return repository.findByStatusAndCity(
            "ACTIVE", normalizeToken(city, "city")
        );
    }

    public List<Customer> findByEmail(String email) {
        return repository.findByEmailNormalized(
            normalizeEmail(email)
        );
    }

    public Customer changeCity(String id, String newCity) {
        Customer customer = getRequired(id);
        customer.setCity(normalizeToken(newCity, "city"));
        return repository.save(customer);
    }

    public Customer changeStatus(String id, String newStatus) {
        Customer customer = getRequired(id);
        String status = normalizeToken(newStatus, "status");
        if (!status.equals("ACTIVE")
                && !status.equals("LOCKED")
                && !status.equals("INACTIVE")) {
            throw new IllegalArgumentException(
                "Unsupported customer status"
            );
        }
        customer.setStatus(status);
        return repository.save(customer);
    }

    public void delete(String id) {
        Objects.requireNonNull(id, "id");
        repository.deleteById(id);
    }

    private static String requireText(
            String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " must not be blank"
            );
        }
        String trimmed = value.trim();
        if (trimmed.length() > 200) {
            throw new IllegalArgumentException(
                field + " is too long"
            );
        }
        return trimmed;
    }

    private static String normalizeToken(
            String value, String field) {
        String token = requireText(value, field)
            .toUpperCase(Locale.ROOT);
        if (!token.matches("[A-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                "Invalid " + field
            );
        }
        return token;
    }

    private static String normalizeEmail(String value) {
        String email = requireText(value, "email")
            .toLowerCase(Locale.ROOT);
        if (email.length() > 254
                || !email.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email"
            );
        }
        return email;
    }
}
~~~

Lớp trên chỉ dùng một quy tắc email tối giản nhằm minh họa normalization trong bài. **Không dùng `contains("@")` làm bộ kiểm tra email đầy đủ hoặc bảo đảm email duy nhất trong sản phẩm thật.** Với ứng dụng có yêu cầu email quốc tế hóa, alias hoặc phân biệt chữ hoa ở phần local-part, phải xác định quy tắc chuẩn hóa theo hợp đồng nghiệp vụ và hệ thống danh tính.

Mỗi lần tạo customer được gán một UUID trước khi gọi repository. Việc gán ID rõ ràng giúp thuận tiện trong các test và minh họa đường key; không có nghĩa Spring Data Redis không hỗ trợ một số cơ chế sinh ID khác.

### Điều gì xảy ra khi cập nhật một trường có index?

Giả sử customer `c-001` ban đầu:

~~~text
id: c-001
status: ACTIVE
city: HANOI
~~~

Service thực hiện:

~~~java
Customer changed =
    customerService.changeCity("c-001", "DANANG");
~~~

Về mặt logic, repository cần duy trì:

~~~text
Trước:
  index city:HANOI  -> chứa c-001
  index city:DANANG -> không chứa c-001

Sau:
  index city:HANOI  -> không còn c-001
  index city:DANANG -> chứa c-001
~~~

Spring Data Redis duy trì metadata/index phục vụ thao tác cập nhật này. Không nên tự ghi `HSET customers:c-001 city DANANG` rồi kỳ vọng index được tự cập nhật như lúc `repository.save`: **bỏ qua repository mapping có thể làm dữ liệu Hash và secondary index bất nhất**.

## 7. Tạo REST API để thực hành

Nếu ứng dụng có `spring-boot-starter-web`, có thể tạo một REST controller nhỏ để gọi service. HTTP layer chỉ nhận input, gọi nghiệp vụ và chuyển entity thành DTO response; không tự thao tác các Redis index.

Tạo `src/main/java/com/example/redis/repositorylab/api/CustomerController.java`:

~~~java
package com.example.redis.repositorylab.api;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.service.CustomerService;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    public record CreateCustomerRequest(
        @NotBlank String fullName,
        @NotBlank String email,
        @NotBlank String city
    ) {
    }

    public record UpdateCityRequest(
        @NotBlank String city
    ) {
    }

    public record CustomerResponse(
        String id,
        String fullName,
        String status,
        String city
    ) {
        static CustomerResponse from(Customer customer) {
            return new CustomerResponse(
                customer.getId(),
                customer.getFullName(),
                customer.getStatus(),
                customer.getCity()
            );
        }
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        Customer created = service.create(
            request.fullName(),
            request.email(),
            request.city()
        );

        return ResponseEntity
            .created(URI.create("/api/customers/" + created.getId()))
            .body(CustomerResponse.from(created));
    }

    @GetMapping("/{id}")
    public CustomerResponse get(@PathVariable String id) {
        return CustomerResponse.from(service.getRequired(id));
    }

    @GetMapping("/active")
    public List<CustomerResponse> activeInCity(
            @RequestParam String city) {
        return service.findActiveByCity(city)
            .stream()
            .map(CustomerResponse::from)
            .toList();
    }

    @PatchMapping("/{id}/city")
    public CustomerResponse changeCity(
            @PathVariable String id,
            @Valid @RequestBody UpdateCityRequest request) {
        return CustomerResponse.from(
            service.changeCity(id, request.city())
        );
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller trả DTO không chứa email hay TTL để minh họa nguyên tắc **không tự động trả toàn bộ Redis entity** cho client. Trong hệ thống thật, các trường nào được phép trả còn phụ thuộc yêu cầu nghiệp vụ và authorization; DTO trong bài chỉ là ví dụ.

Để API có mã HTTP phù hợp khi không tìm thấy ID, có thể thêm `@RestControllerAdvice` ánh xạ `NoSuchElementException` thành 404 và `IllegalArgumentException` thành 400. Không nên để lỗi Redis connection hoặc dữ liệu sai schema mặc định bị biến thành 404, vì đó là các tình huống khác với “khách hàng không tồn tại”.

### Thử bằng HTTP

Khởi động ứng dụng, sau đó gửi request tạo:

~~~bash
curl -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "Nguyen An",
    "email": "AN@example.com",
    "city": "hanoi"
  }'
~~~

Phản hồi minh họa:

~~~json
{
  "id": "c8c77cc9-7a66-4b88-8e9c-4790cb50efc1",
  "fullName": "Nguyen An",
  "status": "ACTIVE",
  "city": "HANOI"
}
~~~

ID thực tế được sinh bằng UUID nên không giống nhau giữa các lần chạy. Dùng ID trả về để thử:

~~~bash
curl http://localhost:8080/api/customers/c8c77cc9-7a66-4b88-8e9c-4790cb50efc1

curl "http://localhost:8080/api/customers/active?city=HANOI"

curl -X PATCH \
  http://localhost:8080/api/customers/c8c77cc9-7a66-4b88-8e9c-4790cb50efc1/city \
  -H "Content-Type: application/json" \
  -d '{"city":"danang"}'

curl "http://localhost:8080/api/customers/active?city=DANANG"
~~~

Sau khi cập nhật thành phố, truy vấn `active?city=HANOI` không còn trả khách hàng đó, còn truy vấn `active?city=DANANG` sẽ trả khách hàng nếu index đã được repository cập nhật thành công.

Các lệnh HTTP chỉ dành cho ứng dụng thử nghiệm không yêu cầu xác thực. Trong production, endpoint quản lý khách hàng cần authentication, authorization, giới hạn request và bảo vệ dữ liệu cá nhân. Không đưa email thật hay token người dùng vào log/bài thử.

## 8. Quan sát dữ liệu bằng Redis CLI

Thay vì đoán các key Redis được tạo, hãy bắt đầu từ ID entity mà API trả về:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 TYPE customers:<customer-id>
redis-cli -h 127.0.0.1 -p 6379 HGETALL customers:<customer-id>
redis-cli -h 127.0.0.1 -p 6379 TTL customers:<customer-id>
~~~

Thay `<customer-id>` bằng ID thực tế. Với mapping `@RedisHash("customers")`, key entity thông thường thuộc keyspace này và sử dụng Redis Hash để chứa fields đã ánh xạ.

Để khám phá các key liên quan:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  --scan --pattern 'customers:*'
~~~

`--scan` dùng cơ chế `SCAN`. Trên một dataset lớn, kết quả có thể cần nhiều lượt cursor; nó không đại diện cho một snapshot bất biến trong khi keyspace đang thay đổi.

Các bước quan sát index:

1. Tạo hai khách hàng có `status=ACTIVE` và `city=HANOI`.
2. Dùng `--scan --pattern 'customers:*'` để quan sát key mà repository đã tạo.
3. Xác định các key có kiểu Redis Set bằng `TYPE <key>`.
4. Với key index thích hợp trong môi trường thử nghiệm, dùng `SMEMBERS <key>` để quan sát ID.
5. Cập nhật thành phố của một khách hàng qua service.
6. Quan sát thay đổi trong kết quả `findByCity(...)`; nếu cần, so sánh metadata/index tương ứng.

**Không nên phụ thuộc vào tên key nội bộ của secondary index trong mã ứng dụng**, vì đó là chi tiết triển khai của Spring Data Redis. Hãy dùng repository API cho CRUD/query; CLI dành cho việc quan sát và chẩn đoán.

### Ví dụ về sự khác nhau giữa Hash và Set

Redis Hash:

~~~text
HGETALL customers:c-001
    id         -> c-001
    fullName   -> Nguyen An
    status     -> ACTIVE
    city       -> HANOI
~~~

Redis Set dành cho secondary index, về mặt khái niệm:

~~~text
SMEMBERS [key index của status ACTIVE]
    c-001
    c-002
~~~

Hash là nơi chứa dữ liệu entity; Set index là cấu trúc hỗ trợ tìm ID. Chỉ mục **không phải một bản sao đầy đủ của đối tượng**, nên một truy vấn index vẫn cần đọc entity tương ứng để materialize `Customer`.

Nếu một key index chứa ID của một entity đã hết hạn mà chưa được cleanup, repository có thể cần xử lý kết quả ID đó không còn Hash. Đây là lý do quản lý TTL và events có ảnh hưởng tới tính chính xác cũng như chi phí duy trì index.

## 9. Vòng đời secondary index khi save, update và delete

Khi một repository lưu entity lần đầu, nó cần lưu Hash và duy trì những chỉ mục được khai báo. Khi entity bị cập nhật, các liên kết index cũ phải được điều chỉnh; khi entity bị xóa, các liên kết cũ cũng cần được loại bỏ.

| Thao tác repository | Hash entity | Secondary index |
| --- | --- | --- |
| `save` mới | Tạo key/entity | Thêm ID vào các index của giá trị field đã đánh dấu |
| `save` sau khi đổi city | Cập nhật dữ liệu | Cập nhật liên kết ID từ giá trị city cũ sang mới |
| `save` sau khi đổi status | Cập nhật dữ liệu | Điều chỉnh Set ứng với status cũ/mới |
| `deleteById` | Xóa dữ liệu entity | Repository xử lý index/metadata liên quan |
| Entity hết TTL | Redis tự xóa key entity | Cần cơ chế xử lý expiration/cleanup phù hợp |
| Ghi `HSET` trực tiếp | Hash đổi mà không đi qua repository | **Không bảo đảm index được cập nhật đúng** |

### Save không phải một thay đổi đơn lệnh

Việc ghi Hash và cập nhật nhiều Set index có thể cần **nhiều lệnh Redis**. Không nên giả định cả chuỗi save được bảo vệ như một transaction ACID của relational database chỉ vì dùng một method `repository.save(...)`.

Với hai instance cùng sửa cùng entity:

~~~text
T0  App A đọc customer c-001: city=HANOI
T1  App B đọc customer c-001: city=HANOI
T2  App A đổi city=DANANG và save
T3  App B đổi status=LOCKED rồi save bản entity cũ
~~~

Nếu không có cơ chế điều phối/versioning phù hợp, App B có thể ghi đè thành phố cũ trở lại hoặc tạo tình huống race trong các index tương ứng. Redis Repository **không tự biến mọi đoạn “đọc → sửa object → save” thành optimistic locking an toàn xuyên nhiều worker**.

Nếu yêu cầu nghiệp vụ là cập nhật đồng thời một thực thể quan trọng, cần đánh giá cách tổ chức update nguyên tử, compare-and-set/Lua, nguồn dữ liệu có optimistic locking hoặc transaction ở hệ thống phù hợp. Với dữ liệu cache có thể tái tạo, chấp nhận một số giới hạn nhất quán đôi khi hợp lý hơn.

### Vì sao không cập nhật index bằng tay?

Một anti-pattern:

~~~java
// Hash thay đổi, nhưng metadata/Set index của repository
// không được đồng bộ theo hợp đồng Spring Data Redis.
stringRedisTemplate.opsForHash()
    .put("customers:c-001", "city", "DANANG");
~~~

Sau lệnh này, `repository.findByCity("HANOI")` vẫn có thể dựa vào index cũ, trong khi Hash đã nói rằng city là `DANANG`. Ứng dụng có thể thấy kết quả lạ, thiếu hoặc dư ID.

Nếu bắt buộc tương tác trực tiếp với Redis key do repository quản lý, hãy coi đó là **thao tác can thiệp cấu trúc nội bộ** và có kế hoạch cập nhật/rebuild index rõ ràng; tốt hơn là để một đường ghi chính duy trì dữ liệu và chỉ mục.

## 10. TTL của entity và nguy cơ chỉ mục còn tham chiếu key đã hết hạn

Thuộc tính `@TimeToLive` cho phép Repository đặt thời gian sống của entity. Trong ví dụ, `ttlSeconds=3600L` biểu diễn thời gian sống 3.600 giây tại thời điểm lưu.

~~~java
Customer customer = new Customer(
    "c-100",
    "Le Minh",
    "le.minh@example.com",
    "ACTIVE",
    "HANOI",
    3600L
);

repository.save(customer);
~~~

Redis sẽ quản lý expiration cho key entity. Tuy nhiên, **một index Set là cấu trúc riêng**, và hành động Redis tự làm một Hash hết hạn không mặc định xóa mọi ID tương ứng trong các Set mà ứng dụng duy trì.

Spring Data Redis có cơ chế theo dõi key expiration để hỗ trợ việc cleanup index và phát sự kiện repository; cơ chế đó liên quan đến **Redis keyspace notifications** và cách repository được cấu hình.

### 10.1. Keyspace notifications là gì?

Redis có thể phát sự kiện khi key hết hạn. Ví dụ Redis configuration dùng các flag phù hợp:

~~~text
notify-keyspace-events Ex
~~~

Các flag ví dụ trên bật notification kiểu **keyevent** cho **expired events**, tùy yêu cầu triển khai. Ứng dụng Spring Data Redis có thể dùng listener của repository để phản ứng với sự kiện key hết hạn.

Điểm vận hành quan trọng:

- Redis keyspace notifications có thể bị **tắt mặc định** và phải cấu hình phù hợp.
- Một số Redis managed service hạn chế `CONFIG SET`; cần cấu hình qua cơ chế của provider.
- Keyspace notification hoạt động theo Pub/Sub, **không phải event log bền vững**.
- Nếu ứng dụng ngừng nhận thông báo trong lúc key hết hạn, sự kiện có thể bị mất.
- Nếu entity/metadata chưa được quản lý theo repository hoặc listener không hoạt động, index cleanup có thể thiếu.

Vì vậy không được chỉ nhìn TTL của Hash rồi khẳng định index chắc chắn không còn mọi tham chiếu tới entity sau expiry trong mọi tình huống.

### 10.2. Cấu hình repository lắng nghe expiration

Một ví dụ cấu hình tùy chọn:

~~~java
package com.example.redis.repositorylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackages = "com.example.redis.repositorylab.repository",
    enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            RedisRepositoryLabApplication.class, args
        );
    }
}
~~~

Đây là **biến thể thay thế** annotation ở phần chuẩn bị ứng dụng, không phải một class `RedisRepositoryLabApplication` thứ hai cần tạo song song. Trong cấu hình thực tế, cần bảo đảm các Redis keyspace notifications thích hợp đã được bật trên server và listener có quyền subscribe.

Một số tùy chọn cấu hình repository có thể cố thiết lập notification qua Redis `CONFIG SET`; cách này không phải lúc nào cũng được phép trên Redis managed service. Nếu hạ tầng tự quản lý `notify-keyspace-events`, nên kiểm tra lựa chọn khởi tạo listener và quyền cấu hình trong phiên bản Spring Data Redis hiện dùng.

### 10.3. Shadow copy khi entity có TTL

Spring Data Redis Repository có những tùy chọn liên quan đến việc giữ một **bản sao phục vụ expiration event** trong thời gian nhất định sau khi key chính hết hạn. Điều này hữu ích nếu ứng dụng cần sự kiện hết hạn có nội dung entity, nhưng có thể làm tăng lượng key và bộ nhớ tiêu thụ.

Một ứng dụng chỉ cần biết một ID đã hết hạn và không cần nội dung entity đầy đủ có thể cân nhắc cấu hình tắt cơ chế shadow copy theo API của phiên bản Spring Data Redis đang sử dụng. Nhưng việc thay đổi tùy chọn đó **không tự giải quyết sự kiện Pub/Sub bị mất** khi listener offline.

Với workload có rất nhiều entity TTL ngắn, hãy đo số key bổ sung, bộ nhớ và số sự kiện khi chuyển trạng thái expiration. Nếu không cần entity hết hạn mà chỉ cần cache, có khi sử dụng `RedisTemplate` với TTL đơn giản sẽ ít phức tạp hơn repository có secondary indexes.

### 10.4. Không dựa vào `Thread.sleep` sát thời điểm TTL

Nếu muốn kiểm thử entity hết hạn sau một giây, test nên:

1. Lưu entity với `ttlSeconds=1L`.
2. Poll `repository.findById(id)` đến khi trả empty hoặc hết timeout test.
3. Đối với index cleanup, quan sát/kiểm tra riêng và cho phép cơ chế event xử lý bất đồng bộ.
4. Không giả định một notification sẽ xuất hiện đúng tại mili giây TTL bằng 0.

Redis xác định expiration theo cơ chế của server, còn listener/index cleanup có thêm độ trễ truyền sự kiện. Một phép thử chờ cố định một lần có thể dễ flaky.

## 11. Khác biệt giữa truy vấn qua ID và qua secondary index

Khi đã biết ID, repository có thể truy cập entity theo key tương ứng. Khi truy vấn theo status/city, repository cần dựa vào index để tìm ID rồi materialize các object. Hai đường truy cập có chi phí và giới hạn khác nhau.

| Đặc điểm | `findById` | `findByStatus` / `findByCity` |
| --- | --- | --- |
| Đầu vào | ID của entity | Giá trị của một trường được đánh index |
| Cách tìm | Trực tiếp qua key entity | Từ index đến ID rồi đọc entity |
| Cần `@Indexed`? | Không, chỉ cần `@Id` | Có đối với field tìm kiếm trong ví dụ |
| Kết quả | `Optional<Customer>` | Tập/List entity phù hợp |
| Chi phí | Phụ thuộc một entity/key và mạng | Phụ thuộc số ID khớp, số entity cần load và index |
| Rủi ro khi nhiều kết quả | Thấp hơn | Có thể lấy hàng nghìn/hàng triệu entity nếu không giới hạn |
| Tính duy nhất | ID xác định một key | Index không mặc định unique |

### Một index có selectivity thấp

Giả sử có một triệu khách hàng, trong đó 950.000 khách hàng có `status=ACTIVE`. Index theo status có thể rất lớn:

~~~text
status=ACTIVE   → 950.000 ID
status=LOCKED   →  40.000 ID
status=INACTIVE →  10.000 ID
~~~

Nếu API gọi `findByStatus("ACTIVE")` và trả tất cả entity cùng lúc, hệ thống có nguy cơ:

- Đọc và deserialize một lượng entity rất lớn.
- Tạo object Java và response JSON lớn, tăng heap/GC.
- Tốn băng thông mạng Redis–application và application–client.
- Gây latency cao, timeout hoặc áp lực lên những request khác.

**Có index không đồng nghĩa mọi truy vấn đều rẻ.** Nếu một thuộc tính chỉ có ba giá trị, tập ID mỗi giá trị có thể rất lớn. Cần đánh giá selectivity, giới hạn kết quả, phân trang thực tế, API response size và SLO.

### Index có cardinality cao

Email thường có cardinality cao: nhiều giá trị khác nhau, mỗi giá trị có rất ít entity. Index theo email có thể tăng số lượng key/Set index và metadata. Nó hữu ích nếu ứng dụng thật sự cần tìm bằng email, nhưng sẽ có memory overhead đáng kể nếu tạo index cho nhiều trường tương tự.

Không nên dùng `@Indexed` lên mọi thuộc tính chỉ vì “có thể một ngày sẽ cần tìm kiếm”. Hãy đánh index dựa trên truy vấn đã biết và đo chi phí khi lưu, cập nhật, xóa cũng như mức sử dụng bộ nhớ Redis.

## 12. Giới hạn truy vấn của Redis Repository

### 12.1. Redis Repository không phải JPQL hoặc SQL

Derived query theo trường được đánh index là một tính năng tiện lợi nhưng không tương đương:

~~~sql
SELECT *
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE LOWER(c.full_name) LIKE '%nguyen%'
ORDER BY c.created_at DESC
LIMIT 20 OFFSET 200;
~~~

Redis Repository không tự cung cấp JOIN tùy ý giữa các entity, full-text search trên String, query planner SQL hoặc sorting/phân trang server-side đầy đủ chỉ vì interface kế thừa Spring Data Repository.

Một số thao tác đơn giản như equality trên field đã được `@Indexed` có thể triển khai bằng secondary index. Với nhu cầu khác, cân nhắc:

- Dùng một secondary index được thiết kế riêng bằng Redis Sorted Set khi cần thứ tự/ranking, với logic đồng bộ dữ liệu rõ ràng.
- Sử dụng Redis Search/Query Engine nếu hạ tầng có module và yêu cầu tìm kiếm phù hợp, qua API/thư viện tương ứng, **không mặc định Redis Repository tự bật tìm kiếm toàn văn**.
- Sử dụng relational database hoặc search engine làm nguồn truy vấn khi cần join, nhiều predicate, sorting và pagination phức tạp.
- Duy trì một read model được thiết kế cho truy vấn thay vì ép repository chứa mọi loại truy vấn.

### 12.2. `findAll` không phải API phân trang

Với một tập khách hàng lớn, việc gọi:

~~~java
Iterable<Customer> all = repository.findAll();
~~~

rồi chuyển toàn bộ thành `List` trả qua HTTP là một lựa chọn có thể tốn nhiều memory. Với lượng dữ liệu nhỏ trong lab thì ổn, nhưng không nên dùng như một endpoint liệt kê production không có giới hạn.

Không tự giả định thêm `Pageable` vào method derived query sẽ cho hiệu quả phân trang theo chỉ mục tương đương SQL `LIMIT/OFFSET`. Khả năng sorting, paging và query operator phụ thuộc Redis Repository implementation/phiên bản, cần kiểm tra đúng hạ tầng và benchmark khi thiết kế API lớn.

### 12.3. Truy vấn nhiều trường chỉ tốt khi dữ liệu được chuẩn hóa

Giả sử một số entity lưu:

~~~text
status = ACTIVE
city   = HANOI
~~~

nhưng entity khác lưu:

~~~text
status = active
city   = Hanoi
~~~

`findByStatusAndCity("ACTIVE","HANOI")` có thể không tìm được nhóm thứ hai. Đây không phải lỗi Redis secondary index; đó là **mâu thuẫn giữa dữ liệu và quy tắc chuẩn hóa**. Vì vậy, service phải chuẩn hóa đầu vào cả khi save lẫn khi query, và có kế hoạch migration cho dữ liệu cũ.

## 13. Khi uniqueness, transaction và concurrency quan trọng hơn convenience

Redis Repository quản lý một entity ở dạng key/value và secondary indexes; nó **không tự bảo đảm một email chỉ được lưu cho duy nhất một customer**.

### 13.1. Race condition khi kiểm tra email

Một cách triển khai dễ nhầm:

~~~java
if (repository.findByEmailNormalized(email).isEmpty()) {
    repository.save(newCustomer);
}
~~~

Trong hai instance:

~~~text
App A: findByEmailNormalized("a@example.com") → empty
App B: findByEmailNormalized("a@example.com") → empty
App A: save(customer-A) → thành công
App B: save(customer-B) → thành công

Kết quả: cùng một email xuất hiện trong hai entity.
~~~

Đọc index rồi save là hai hành động riêng, không có uniqueness guarantee. Nếu cần uniqueness nghiêm ngặt, ưu tiên dùng ràng buộc unique tại nguồn dữ liệu phù hợp; nếu xây quy trình uniqueness bằng Redis, phải thiết kế một thao tác cấp phát/kiểm tra nguyên tử và xử lý việc tạo entity/index thất bại giữa chừng, TTL, failover và recovery. Một lệnh `SET NX` riêng cho email **chưa tự làm việc tạo nhiều key trở thành giao dịch toàn vẹn**.

### 13.2. Lỗi giữa chừng khi save

Giả sử repository đang cập nhật Hash, các index Set và metadata liên quan. Nếu Redis mất kết nối hoặc process bị ngắt giữa chuỗi lệnh, một phần thay đổi có thể đã thực hiện.

Điều cần làm:

1. Phân biệt lỗi kết nối/timeout với lỗi validation/query.
2. Không retry mù một workflow có side effect ngoài Redis.
3. Nếu Redis là dữ liệu nguồn chính, cần quy trình đối soát và repair consistency giữa entity/index.
4. Nếu Redis chỉ là read model/cache, có thể xây lại từ nguồn dữ liệu đáng tin cậy.
5. Giám sát index result chứa ID không còn Hash và các lỗi deserialize.

Một method `save` không hứa giao dịch phân tán giữa Redis, JDBC và HTTP service bên ngoài.

### 13.3. Redis failover có thể làm dữ liệu/metadata chưa đồng bộ

Redis replication mặc định bất đồng bộ. Một primary có thể trả thành công cho thao tác ghi trước khi replica nhận đầy đủ các cập nhật. Nếu failover đúng ranh giới đó, primary mới có thể thiếu một số thay đổi cuối, bao gồm cả entity hoặc metadata chỉ mục.

Sentinel/Cluster giải quyết khả năng khôi phục endpoint và phục vụ dữ liệu ở mức nhất định, **không tự tạo cam kết zero-data-loss hoặc transaction cho Redis Repository**. Cần đánh giá chính sách persistence, replication và nguồn sự thật theo độ quan trọng nghiệp vụ.

### 13.4. Nên dùng Redis Repository cho loại dữ liệu nào?

Thường phù hợp khi:

- Entity tương đối nhỏ, truy cập chủ yếu theo ID.
- Có một số truy vấn equality đơn giản theo thuộc tính có index.
- Redis là read model/cache hoặc datastore phù hợp với rủi ro, durability và semantics đã phân tích.
- Không cần join, full-text, aggregation phức tạp.
- Số lượng entity và kết quả truy vấn nằm trong giới hạn RAM, network và SLA.

Cần cân nhắc kỹ hơn khi:

- Entity là nguồn dữ liệu nghiệp vụ quan trọng không được mất.
- Có nhiều writers cập nhật một entity cùng lúc.
- Unique constraint hoặc transaction chặt chẽ là yêu cầu bắt buộc.
- Truy vấn cần sorting/pagination phức tạp hoặc tìm kiếm gần đúng.
- Index chứa tập ID cực lớn và tần suất cập nhật cao.
- TTL ngắn với nhiều key hết hạn liên tục, đặc biệt khi expiration events có thể mất.

## 14. Integration test với Redis thật

Unit test chỉ mock `CustomerRepository` có thể kiểm tra logic service, nhưng **không chứng minh Spring Data Redis tạo và duy trì secondary index đúng**. Để kiểm tra mapping/index/TTL, cần một Redis server thật trong môi trường thử nghiệm độc lập.

Ví dụ sử dụng JUnit 5, Spring Boot và Testcontainers:

~~~java
package com.example.redis.repositorylab;

import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.repository.CustomerRepository;
import com.example.redis.repositorylab.service.CustomerService;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = RedisRepositoryLabApplication.class)
class CustomerRepositoryIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host", REDIS::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    CustomerService service;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void createAndReadByIdAndSecondaryIndexes() {
        Customer created = service.create(
            "Nguyen An", "AN@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            Customer loaded = repository.findById(id)
                .orElseThrow();

            assertThat(loaded.getFullName())
                .isEqualTo("Nguyen An");
            assertThat(loaded.getStatus())
                .isEqualTo("ACTIVE");
            assertThat(loaded.getCity())
                .isEqualTo("HANOI");
            assertThat(loaded.getEmailNormalized())
                .isEqualTo("an@example.com");

            assertThat(service.findActiveByCity("hanoi"))
                .extracting(Customer::getId)
                .contains(id);

            assertThat(service.findByEmail("AN@example.com"))
                .extracting(Customer::getId)
                .contains(id);
        } finally {
            repository.deleteById(id);
        }
    }

    @Test
    void updatingIndexedFieldChangesQueryResult() {
        Customer created = service.create(
            "Le Binh", "le.binh@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            assertThat(service.findByCity("hanoi"))
                .extracting(Customer::getId)
                .contains(id);

            service.changeCity(id, "danang");

            assertThat(service.findByCity("hanoi"))
                .extracting(Customer::getId)
                .doesNotContain(id);

            assertThat(service.findByCity("danang"))
                .extracting(Customer::getId)
                .contains(id);
        } finally {
            repository.deleteById(id);
        }
    }

    @Test
    void deletingEntityRemovesItsIndexMembership() {
        Customer created = service.create(
            "Do Ha", "do.ha@example.com", "hanoi"
        );
        String id = created.getId();

        repository.deleteById(id);

        assertThat(repository.findById(id)).isEmpty();
        assertThat(service.findByCity("hanoi"))
            .extracting(Customer::getId)
            .doesNotContain(id);
    }

    @Test
    void entityHasPositiveTimeToLive() {
        Customer created = service.create(
            "Tran Lan", "tran.lan@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            Long ttl = redis.getExpire(
                "customers:" + id, TimeUnit.SECONDS
            );

            assertThat(ttl)
                .isNotNull()
                .isGreaterThan(0L)
                .isLessThanOrEqualTo(3600L);
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

### Những điều integration test xác nhận

- `repository.save` tạo entity mà `findById` có thể đọc lại.
- Các giá trị được service chuẩn hóa trước khi index.
- `findByStatusAndCity` và `findByEmailNormalized` tìm được entity đã lưu.
- Sau khi thay city rồi save, truy vấn theo city cũ không còn chứa ID, còn truy vấn theo city mới có ID.
- `deleteById` làm entity không còn được tìm thấy và không nằm trong kết quả truy vấn index của ứng dụng.
- Property `@TimeToLive` dẫn tới TTL dương trên key entity.

Mỗi lần `create` tạo ID UUID khác, giúp giảm nguy cơ va chạm nếu chạy nhiều test cùng lúc. `finally` dọn đúng entity của test qua repository, tránh gọi `FLUSHALL` hoặc `FLUSHDB` trên Redis có thể dùng chung.

**Giới hạn của test này:** một Redis container đơn lẻ không kiểm chứng Sentinel failover, Cluster, keyspace notifications có thể bị bỏ lỡ khi listener offline hoặc trạng thái sau concurrent writes. Các yêu cầu đó cần bài kiểm thử riêng theo topology.

### Test không nên phụ thuộc vào một format key nội bộ của index

Một assertion tốt:

~~~java
assertThat(repository.findByCity("DANANG"))
    .extracting(Customer::getId)
    .contains(id);
~~~

Một assertion quá phụ thuộc implementation:

~~~java
// Không nên bắt buộc nội bộ index luôn có đúng key name này.
assertThat(redis.opsForSet()
    .members("customers:city:DANANG"))
    .contains(id);
~~~

Kiểm tra repository query theo contract sẽ ổn định hơn nếu phiên bản framework đổi cấu trúc index nội bộ. CLI và cấu trúc key vẫn hữu ích khi debug, nhưng không nhất thiết phải trở thành API ứng dụng.

## 15. Kiểm thử expire mà không đánh đồng với index cleanup

Để kiểm tra TTL thật, có thể lưu một entity có thời gian sống ngắn:

~~~java
Customer shortLived = new Customer(
    UUID.randomUUID().toString(),
    "Temporary Customer",
    "temporary@example.com",
    "ACTIVE",
    "HANOI",
    2L
);

Customer saved = repository.save(shortLived);
~~~

Sau đó dùng polling hữu hạn để chờ entity không còn tồn tại:

~~~java
import static org.awaitility.Awaitility.await;

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertThat(repository.findById(saved.getId()))
            .isEmpty()
    );
~~~

Ví dụ sử dụng Awaitility trong test; nếu dự án không có dependency, bổ sung thư viện kiểm thử tương ứng hoặc dùng cơ chế polling khác. Không suy luận thời điểm Redis hết hạn chính xác từ một `Thread.sleep(2000)`.

Kiểm tra **entity hết hạn** là một mục tiêu; kiểm tra **secondary index đã được cleanup sau expiration** là mục tiêu khác. Nếu listener keyspace notification chưa được cấu hình, mất kết nối hoặc ứng dụng bị tắt khi key hết hạn, một số liên kết index có thể còn tồn tại. Test cleanup phải khai báo rõ cấu hình server và listener cần thiết, thời hạn chờ có điều kiện, không mặc định mọi môi trường có cùng behavior.

## 16. Bài thực hành mở rộng: khóa trạng thái và đổi email

Để hiểu rõ hơn vòng đời index, hãy thêm hai nghiệp vụ:

**Bài A — Khóa một khách hàng.**

1. Tạo customer với `status=ACTIVE`, `city=HANOI`.
2. Kiểm tra customer có trong `findByStatus("ACTIVE")`.
3. Gọi `service.changeStatus(id, "LOCKED")`.
4. Kiểm tra ID biến mất khỏi kết quả `ACTIVE` và có trong `LOCKED`.
5. Xóa customer, kiểm tra cả hai tập query không còn ID.

**Bài B — Đổi email đã chuẩn hóa.**

1. Tạo customer có `emailNormalized=old@example.com`.
2. Thêm method service thay email sau khi validate.
3. Gọi `repository.save` sau khi thay property.
4. Kiểm tra `findByEmailNormalized("old@example.com")` không còn ID.
5. Kiểm tra `findByEmailNormalized("new@example.com")` chứa ID.
6. Tạo thêm một customer với email mới và quan sát index có thể chứa **hai ID**; đây không phải bug unique constraint của Redis, bởi `@Indexed` không bảo đảm uniqueness.

Với cập nhật nhiều field cùng lúc, hãy viết test cho kết quả query theo từng field và tổ hợp field để phát hiện dữ liệu/index không nhất quán.

### Bài C — Quan sát chi phí secondary index

Tạo một tập dữ liệu thử có quy mô vừa phải và đo:

- Số Redis keys trước và sau khi bật thêm một `@Indexed`.
- Lượng memory dùng cho Hash entity và những Set index liên quan.
- Latency `repository.save` khi entity có 1 index so với 3 index.
- Latency `findByStatus` khi 10, 1.000 hoặc 10.000 ID cùng trạng thái.
- Số entity phải deserialize để trả một kết quả query.
- Mức tải tăng khi nhiều entity đổi trạng thái liên tục.

Không dùng kết quả từ 10 entity để suy ra chi phí của hàng triệu entity; cũng không nên bật thêm index trên production trước khi có migration/backfill và đánh giá memory.

## 17. Những lỗi thường gặp khi sử dụng Redis Repository

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `findByStatus` không tìm thấy entity | Trường `status` thiếu `@Indexed`, giá trị chưa chuẩn hóa, hoặc dữ liệu được tạo trước khi index được triển khai | Kiểm tra annotation, trạng thái dữ liệu và kế hoạch reindex |
| `findById` được nhưng `findByCity` không được | Hash tồn tại nhưng secondary index thiếu hoặc sai | Xác định đường ghi có đi qua repository không; kiểm tra index metadata |
| Cập nhật field bằng `HSET` nhưng query trả kết quả cũ | Sửa Hash trực tiếp nên index không được repository cập nhật | Đưa các thay đổi qua repository hoặc cơ chế index maintenance thống nhất |
| Một email xuất hiện trong hai entity | `@Indexed` không có unique constraint | Thiết kế uniqueness ở nguồn dữ liệu/cấp phát nguyên tử |
| Query theo `hanoi` không tìm thấy `HANOI` | Sai quy ước chữ hoa/thường | Chuẩn hóa ở cả đường ghi và đường query |
| Entity mất sau một thời gian | `@TimeToLive` làm key hết hạn | Kiểm tra `ttlSeconds`, TTL Redis, chính sách entity expiration |
| Hash đã hết TTL nhưng index còn ID | Notification/cleanup bị mất hoặc chưa bật | Kiểm tra Redis keyspace notifications, listener, cơ chế repair |
| `save` trả thành công nhưng workflow khác thất bại | Ghi Redis không đồng nghĩa giao dịch với DB hoặc HTTP | Thiết kế idempotency/transaction/outbox tùy yêu cầu |
| Derived query phức tạp không được hỗ trợ | Redis Repository không có toàn bộ khả năng JPA | Dùng đúng field index và API query được hỗ trợ; chọn datastore khác khi phù hợp |
| Truy vấn `ACTIVE` quá chậm | Index có quá nhiều member, cần load quá nhiều entity | Giới hạn kết quả, tối ưu read model, xem xét cấu trúc truy vấn khác |
| Redis memory tăng sau khi bật index | Mỗi index có thêm Set/metadata, có thể kèm shadow copies với TTL | Đo memory, cardinality, chi phí write và TTL |
| Khi nâng version ứng dụng, kết quả query khác | Thay đổi mapping, schema hoặc cách normalize | Migration và kiểm thử tích hợp với dữ liệu đại diện |
| Repository bean không được tạo | Package scan sai hoặc repository auto-configuration không được bật phù hợp | Kiểm tra `@EnableRedisRepositories` và Spring Boot config |
| `WRONGTYPE` với key entity | Key đang bị dùng làm kiểu Redis khác | Kiểm tra namespace và writer, không trộn Redis String/Hash |
| Lỗi Redis connection hoặc timeout | Redis down, DNS/port/ACL/TLS, failover hoặc client quá tải | Chẩn đoán kết nối và topology, retry theo semantics, không coi là query không tìm thấy |
| API lộ trường không nên trả | Trả trực tiếp domain entity chứa email/metadata | Dùng response DTO theo chính sách phân quyền |
| Sau failover xuất hiện dữ liệu cũ | Replication bất đồng bộ hoặc đọc replica lag | Đánh giá durability, consistency và ranh giới nguồn dữ liệu |
| Nhiều ứng dụng ghi cùng keyspace theo quy tắc khác nhau | Hai writer không tuân cùng schema/index | Tách namespace/ownership, dùng một đường ghi thống nhất |

### Lỗi "không thấy repository" khác lỗi "không thấy customer"

Nếu Spring báo không thể inject `CustomerRepository`, đây là **lỗi wiring** lúc khởi tạo application context. Hãy xem package scanning, annotation và dependency.

Nếu `repository.findById(id)` trả `Optional.empty()`, đây có thể là **kết quả nghiệp vụ bình thường** do ID không tồn tại hoặc key đã hết hạn. Nếu method ném exception vì Redis không kết nối được, đó là **lỗi hạ tầng**, không được tự chuyển thành empty để trả HTTP 404.

Một hệ thống có logging/metrics tốt nên phân biệt ba trường hợp này ngay tại tầng service/API.

## 18. Tối ưu truy vấn và vận hành index

### 18.1. Theo dõi Redis và ứng dụng

Những chỉ số hữu ích:

| Nhóm | Chỉ số cần quan sát | Giải thích |
| --- | --- | --- |
| Redis memory | `used_memory`, key count, fragmentation | Index và metadata có làm tăng memory không? |
| Redis keyspace | Expired/evicted keys | Có nhiều entity bị xóa do TTL hoặc eviction không? |
| Query | Latency p50/p95/p99 theo derived query | Query theo field có tăng độ trễ theo cardinality không? |
| Save/delete | Throughput, error rate, latency | Chi phí index maintenance khi ghi |
| Index results | Số kết quả và số ID không load được entity | Dấu hiệu index tham chiếu Hash đã mất |
| App/JVM | Heap, GC, allocation, request concurrency | Deserialize danh sách lớn có gây quá tải không? |
| Listener | Trạng thái kết nối Pub/Sub key expiration | Cleanup/index events có bị gián đoạn không? |
| Failure | Redis timeout, reconnect, schema lỗi | Phân biệt lỗi hạ tầng và lỗi dữ liệu |

Ví dụ một số lệnh Redis CLI để quan sát trong môi trường được phép:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
redis-cli -h 127.0.0.1 -p 6379 INFO memory
redis-cli -h 127.0.0.1 -p 6379 INFO stats
redis-cli -h 127.0.0.1 -p 6379 INFO commandstats
redis-cli -h 127.0.0.1 -p 6379 SLOWLOG GET 10
~~~

Không chạy `KEYS customers:*` như một thao tác thống kê thường xuyên trên Redis production lớn. `SCAN` ít gây chặn hơn và phù hợp với công việc quản trị có kiểm soát, nhưng không tạo snapshot hoàn toàn nhất quán nếu dữ liệu thay đổi trong lúc scan.

### 18.2. Chỉ mục có chi phí ghi

Đặt `@Indexed` trên ba thuộc tính của entity có thể giúp query equality, nhưng save sẽ phải duy trì những Set tương ứng. Với lưu lượng cập nhật cao, việc thay đổi các giá trị index liên tục có thể làm tăng số Redis command, bộ nhớ và latency.

Hãy đánh giá theo workload thực:

~~~text
Workload A: 95% read by ID, 5% search by status
  -> Có cần index status không? Số query thực tế bao nhiêu?

Workload B: 50% cập nhật status, 50% findByStatus
  -> Chi phí maintenance có đáng so với lợi ích query?

Workload C: 90% findByEmailNormalized, rất ít cập nhật email
  -> Index email có thể hữu ích, nhưng nhớ yêu cầu uniqueness riêng.
~~~

Không có một công thức chỉ định “ba trường là vừa đủ”. Độ chọn lọc, cardinality, số entity, tỷ lệ đọc/ghi, TTL và SLO mới quyết định index nào đáng giữ.

### 18.3. Index mới không tự giải quyết dữ liệu đã lưu từ trước

Giả sử ứng dụng đã lưu 100.000 customer khi trường `city` chưa có `@Indexed`. Sau deploy, thêm annotation vào field không có nghĩa tất cả Hash cũ **ngay lập tức** có đầy đủ secondary index như thể chúng được lưu qua mapping mới.

Với dữ liệu cần truy vấn bằng index mới, cần có **kế hoạch backfill/reindex**:

1. Xác định tập entity được quản lý và nguồn dữ liệu đáng tin cậy.
2. Chuẩn hóa field theo schema mới.
3. Ở môi trường thử nghiệm, xây cơ chế ghi lại qua repository hoặc quy trình migration được thiết kế rõ.
4. Giới hạn batch/concurrency để tránh làm Redis quá tải.
5. Đo lượng memory index mới phát sinh và latency query.
6. Đối soát một tập sample: truy vấn theo ID và index trả kết quả tương ứng.
7. Có khả năng rollback hoặc chuyển namespace nếu quá trình migration gặp lỗi.

Không khẳng định một lệnh `save` chạy hàng loạt trên production là luôn an toàn: khi có concurrent updates, reindex và ghi nghiệp vụ có thể tranh chấp. Với dữ liệu quan trọng, cần kế hoạch downtime/versioning hoặc phối hợp ghi phù hợp.

### 18.4. Index cleanup và đối soát định kỳ

Nếu repository quản lý những entity TTL ngắn, keyspace notifications có thể mất khi Redis/application mất kết nối. Với hệ thống lớn, hãy chủ động thiết kế chính sách quan sát:

- Đếm số index member không còn entity tương ứng trên mẫu kiểm tra.
- Đo tỷ lệ entity expired và số event được listener nhận nếu có metric.
- Có quy trình rebuild index từ nguồn dữ liệu đáng tin cậy khi phát hiện lệch.
- Không sửa trực tiếp toàn bộ index bằng một script ad hoc không có giới hạn và kiểm soát.
- Với những key quan trọng, cân nhắc không dựa hoàn toàn vào expiration event không bền vững để duy trì correctness.

Nếu secondary index đóng vai trò tìm kiếm nghiệp vụ chính và không được phép có stale reference, cần đánh giá xem Redis Repository cùng keyspace Pub/Sub có đáp ứng yêu cầu nhất quán hay không. Một relational/search index có lifecycle giao dịch phù hợp có thể là lựa chọn tốt hơn.

## 19. Tách trách nhiệm giữa Repository, Template và nguồn dữ liệu chính

Trong một ứng dụng Spring Data Redis, `RedisRepository` và `RedisTemplate` đều có vai trò:

| Thành phần | Dùng phù hợp khi | Lưu ý |
| --- | --- | --- |
| `CrudRepository` với `@RedisHash` | CRUD entity theo ID, vài query secondary index | Mapping/metadata/index được Spring Data Redis quản lý |
| `StringRedisTemplate` | Lệnh trực tiếp trên String, counter, simple cache | Không tự cập nhật secondary index của Repository |
| `RedisTemplate<K,V>` | Các cấu trúc Redis như Hash/Set/List/ZSet, script, pipeline | Cần serializer, key convention và semantics rõ |
| Reactive Redis APIs | Luồng không blocking dùng `Mono`/`Flux` | Không mặc định tương đương repository đồng bộ |
| Database có transaction/unique constraint | Nguồn dữ liệu cần ràng buộc nghiệp vụ mạnh | Redis có thể giữ read model/cache |
| Search engine/Redis Query Engine phù hợp | Tìm kiếm full-text, sorting/filtering chuyên sâu | Không tự xuất hiện khi thêm `@Indexed` |

### Tránh sở hữu dữ liệu mập mờ

Một kiến trúc dễ lỗi:

~~~text
Service A → CustomerRepository.save(...)
Service B → StringRedisTemplate.opsForHash().put(...)
Batch C   → RESTORE key với payload cũ
             |
             v
   Cùng keyspace customers:*
             |
             v
     Hash và index bị lệch
~~~

Một kiến trúc dễ quản lý hơn:

~~~text
                    Business service
                          |
                          v
                CustomerRepository
                          |
              +-----------+-----------+
              |                       |
              v                       v
        Entity Hash               Index metadata
              |                       |
              +-----------+-----------+
                          |
                          v
                    Redis storage
~~~

Nếu có nhiều producer, chúng cần dùng cùng quy ước schema, namespace, serializer và index maintenance; nếu không, nên tách keyspace hoặc thiết kế một service chịu trách nhiệm ghi duy nhất.

## 20. Tóm lược lộ trình tự thực hành

Để chạy lại bài học theo thứ tự:

1. Tạo một Spring Boot project có `spring-boot-starter-data-redis` và Redis development chạy độc lập.
2. Khai báo `Customer` với `@RedisHash("customers")`, `@Id`, ba field `@Indexed` và `@TimeToLive`.
3. Định nghĩa `CustomerRepository extends CrudRepository<Customer, String>`.
4. Bật Redis repository scanning, cấu hình connection và khởi động ứng dụng.
5. Gọi `CustomerService.create(...)` để lưu entity.
6. Đọc entity bằng `findById`; tìm bằng `findByStatus`, `findByCity`, `findByStatusAndCity`.
7. Đổi city/status bằng cách sửa entity rồi `repository.save`; kiểm tra index query cũ/mới.
8. Xóa entity qua repository và xác nhận không tìm được bằng ID/index.
9. Quan sát Hash, Set index và TTL bằng Redis CLI trong môi trường test.
10. Chạy integration test với Redis riêng, key có UUID và cleanup.
11. Thử entity TTL ngắn, phân biệt Redis key expiration với index cleanup qua notifications.
12. Đánh giá chi phí khi tăng cardinality, số index, số entity và đồng thời ghi.

### Những kết quả cần nhận thấy

| Hành động | Kết quả cần quan sát |
| --- | --- |
| Lưu khách hàng mới | Entity có thể đọc bằng ID và các truy vấn index |
| Tìm `ACTIVE` tại `HANOI` | Trả các khách hàng cùng điều kiện, không phải mọi customer |
| Đổi `city` | Truy vấn city cũ không còn ID; city mới có ID |
| Đổi `status` | Truy vấn status cũ/mới thay đổi tương ứng |
| Xóa entity | `findById` empty và index query không chứa ID |
| TTL dương | Redis có thời gian hết hạn trên entity key |
| Entity hết hạn | `findById` cuối cùng empty; cleanup index phụ thuộc events/config |
| Hai khách hàng cùng email | `@Indexed` vẫn có thể trả hai entity; không phải unique index |
| Ghi Hash trực tiếp | Không có bảo đảm index được repository cập nhật |

## 21. Tổng kết

**Redis Repository giúp quản lý entity ở Redis theo mô hình Spring Data quen thuộc**, trong khi **secondary index** giúp tìm entity theo một số trường ngoài ID. Trong bài thực hành, các thành phần chính là:

- `@RedisHash` để ánh xạ entity lên Redis Hash.
- `@Id` để định danh và truy cập theo key.
- `@Indexed` để duy trì secondary index cho những thuộc tính cần query.
- `CrudRepository` để tạo, đọc, cập nhật và xóa entity.
- Derived query như `findByStatus`, `findByCity` và `findByStatusAndCity`.
- `@TimeToLive` để áp dụng expiration khi nghiệp vụ cần.
- Testcontainers để kiểm tra những hành vi Redis thật thay vì chỉ mock repository.

Cần nhớ **secondary index là cấu trúc dữ liệu bổ sung có chi phí duy trì**, không phải unique constraint hay công cụ tìm kiếm toàn năng. Thao tác ghi Hash trực tiếp có thể làm index không đồng bộ; TTL expiration cần quan tâm tới keyspace notifications; save/update có giới hạn về tính nguyên tử và concurrency; truy vấn có nhiều ID khớp vẫn có thể tiêu tốn đáng kể tài nguyên.

Khi sử dụng đúng phạm vi — entity nhỏ, truy cập chính theo ID, một số equality query đã biết, chuẩn hóa dữ liệu và ownership rõ ràng — Spring Data Redis Repository là một công cụ thuận tiện. Khi cần uniqueness nghiêm ngặt, transaction phức tạp, full-text search hoặc phân trang/sắp xếp quy mô lớn, hãy chọn thêm hoặc thay bằng một mô hình dữ liệu chuyên biệt phù hợp với yêu cầu nhất quán và hiệu năng của ứng dụng.
