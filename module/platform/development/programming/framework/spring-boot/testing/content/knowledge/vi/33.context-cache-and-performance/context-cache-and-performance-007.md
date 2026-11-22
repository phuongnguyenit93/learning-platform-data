# Thay full-context test bằng slice hoặc unit test khi đủ bằng chứng

## 1. Bài toán: test nhanh hơn nhưng không được mất bằng chứng

Một dự án Spring Boot có hàng trăm lớp gắn `@SpringBootTest`. Mỗi lớp chỉ kiểm tra một hàm tính tiền, một JSON field hoặc một repository query, nhưng vẫn yêu cầu ApplicationContext đầy đủ: component scan, auto-configuration, JPA, DataSource, security, web infrastructure, scheduler, HTTP clients và có thể cả Testcontainers. Khi test suite lớn, điều này tạo chi phí khởi động và bảo trì không cần thiết.

Một phản xạ thường gặp là **thay mọi `@SpringBootTest` bằng unit tests** và gọi đó là tối ưu thành công. Nhưng việc đó có thể xóa những bằng chứng quan trọng: annotation mapping đúng, `@Valid` thực thi, security filter từ chối anonymous, repository query tương thích dialect, transaction wiring đúng, configuration properties được bind, hoặc HTTP requests thực sự tới đúng handler.

**Nguyên tắc trung tâm:** chỉ thay full-context test bằng unit hoặc slice khi **những hành vi mà test cũ cần chứng minh vẫn được chứng minh đủ** ở ranh giới mới hoặc ở một nhóm integration tests còn giữ lại. Thay annotation không phải đích đến; **giữ đúng hợp đồng và giảm setup thừa** mới là mục tiêu.

Bài học này nằm trong chủ đề **Context cache và hiệu năng**. Nó kết nối các yếu tố: Spring TestContext cache, mức độ lớn của context, chi phí setup, số cache keys, sự cô lập test, và bản đồ bằng chứng theo từng tầng.

### Sau bài này, bạn có thể

1. Phân biệt unit test, Spring slice test, full-context MockMvc integration test và real HTTP integration test.
2. Chọn test boundary theo **câu hỏi cần chứng minh**, không theo thói quen annotation.
3. Đánh giá khi nào Mockito phù hợp và khi nào mock đã xóa đúng behavior cần kiểm chứng.
4. Hiểu `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` và các Spring Boot test slices.
5. Giữ lại một **cross-layer seam test** khi tách một full integration test lớn thành unit/slice tests.
6. Nhận ra chi phí cache key khác nhau do mock overrides, profiles, inline properties và slices.
7. Hiểu vì sao `@SpringBootTest` không tự mở real HTTP server, còn `RANDOM_PORT` thì có.
8. Tổ chức tests độc lập, nhanh và đáng tin mà không ép mọi integration test về `@DirtiesContext`.
9. Thử mẫu Java 17+, Spring Boot 3.5.16 với **15 JUnit Jupiter methods** trải trên bốn cấp độ.
10. Xây một bộ tiêu chí “đủ bằng chứng” để review PR refactor tests.

**Phạm vi phiên bản:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter, Mockito, AssertJ, Spring MVC, Spring Data JPA, H2. Spring Boot 4.x thay đổi một số module, starter và test package; các imports ở đây được chọn cho **Boot 3.5.16**, không trộn với hướng dẫn Boot 4.x.

## 2. Trước khi chọn công cụ, viết lại câu hỏi test

Thay vì hỏi “dùng @SpringBootTest hay @WebMvcTest?”, hãy hỏi: **Điều gì sẽ xảy ra nếu một developer cố ý làm hỏng behavior này? Test nào phải đỏ?**

Ví dụ cùng một tính năng tạo sản phẩm:

| Behavior/hợp đồng | Khi cố tình tạo regression | Lớp test cần phát hiện |
|---|---|---|
| Giá phải lớn hơn 0 ở service | Service chấp nhận giá 0 | Unit service test |
| Tên được trim trước khi lưu | Bỏ `trim()` | Unit service test |
| Route POST /products nhận JSON | Đổi route sang /items | MVC slice hoặc full MockMvc |
| Request thiếu name bị 400 | Xóa `@NotBlank`/`@Valid` | MVC slice hoặc full MockMvc |
| JSON response có id/name/price | Đổi DTO serialization | MVC slice hoặc full MockMvc |
| JPA mapping lưu cột price đúng | Đổi entity mapping/query | JPA slice hoặc real-DB integration |
| Controller→service→repository thực sự nối đúng | Thay nhầm dependency/wiring | Một full-context integration test |
| Anonymous không tạo sản phẩm khi cần login | Bỏ authorization rule | Security-enabled MockMvc/HTTP test |
| HTTP thật qua port hoạt động | Web server/network config lỗi | `RANDOM_PORT` + HTTP client |
| DB transaction/retry/outbox hoạt động | Đổi transaction/rollback behavior | Integration test với resources thật |

**“Đủ bằng chứng” không có nghĩa nhiều assertions giống nhau ở nhiều tầng.** Nó nghĩa là mỗi yêu cầu có một hoặc vài tests **thực sự chạy qua ranh giới gây rủi ro**, bao gồm negative cases và một ít kiểm thử nối tầng.

### 2.1. Một câu hỏi kiểm tra trước khi mock

“Nếu collaborator này bị thay bằng Mockito mock, phần behavior mà tôi muốn phát hiện lỗi có còn thực thi không?”

- Muốn kiểm tra **service ra quyết định gọi repository với giá đã chuẩn hóa**: mock repository có thể phù hợp.
- Muốn kiểm tra **SQL query tìm đúng rows**: mock repository là không đủ.
- Muốn kiểm tra **JSON ↔ DTO và status mapping**: mock service, giữ Spring MVC thật là hợp lý.
- Muốn kiểm tra **service bean được inject vào controller khi application start**: mock service trong MVC slice không chứng minh đủ.
- Muốn kiểm tra **security filter chain và CSRF**: không loại filters hoặc permitAll chỉ để test xanh.
- Muốn kiểm tra **HTTP TCP socket, servlet container và reverse-proxy assumptions**: MockMvc không đủ, cần real HTTP path.
- Muốn kiểm tra **Kafka publish/consume thật**: mock KafkaTemplate không đủ; cần broker integration.

Mock đúng ở tầng **không thuộc câu hỏi cần chứng minh**. Mock sai ở tầng **chứa chính behavior mục tiêu**.

## 3. Các mức độ test và phạm vi quan sát

```text
               Real environment / cross-system
            [RANDOM_PORT + DB/IdP/broker etc.]
                       /\
                      /  \
              Full Spring Boot integration
             [@SpringBootTest + MockMvc]
                    /        \
              MVC slice     JPA slice
              [@WebMvcTest] [@DataJpaTest]
                   \          /
                    \        /
                    Pure unit tests
                      [JUnit/Mockito]
```

Sơ đồ là khung phân loại, **không phải** thứ bậc “càng lên cao càng tốt”. Mỗi tầng phát hiện một nhóm lỗi khác nhau.

| Tiêu chí | Pure unit | `@WebMvcTest` | `@DataJpaTest` | Full `@SpringBootTest` + MockMvc | Full `RANDOM_PORT` |
|---|---|---|---|---|---|
| Spring context | Không | MVC slice | JPA slice | Full app | Full app + server |
| Bean/component wiring toàn app | Không | Không | Không | Có | Có |
| Domain branching | Có | Thường mock service | Có thể qua repository behavior | Có | Có |
| JSON route/validation | Không | Có | Không | Có | Có |
| JPA entity mapping/query | Không | Thường không | Có | Có nếu dùng real repo | Có nếu dùng real repo |
| Real HTTP socket | Không | Không | Không | Không | Có |
| External DB dialect đúng production | Không | Không | Chỉ nếu dùng đúng database | Chỉ nếu dùng đúng database | Chỉ nếu dùng đúng database |
| Spring Security filters | Không | Theo slice context/config | Không thuộc mục tiêu | Theo full context/config | Theo server config |
| Startup/setup cost | Rất thấp | Thường thấp hơn full | Thường thấp hơn full | Thường cao hơn | Thường cao nhất |
| Cache reuse | Không cần | Theo key của slice | Theo key của slice | Theo full-context key | Theo web-server key |

**Đừng dùng bảng như một lời hứa về tốc độ tuyệt đối.** Một full context đã được cache hit có thể rất rẻ ở lượt test kế tiếp; ngược lại một slice cấu hình quá nhiều bean/customizers có thể không còn nhẹ. Đo thực tế mới biết lợi ích.

## 4. Vì sao full-context tests tốn thời gian?

Một `@SpringBootTest` dùng SpringApplication tạo ApplicationContext theo cấu hình mục tiêu. Nếu full app có JPA, datasource, scheduling, HTTP client wiring, observability, security hoặc optional integrations, phần startup có thể đáng kể.

Nhưng Spring TestContext framework có **static ApplicationContext cache trong JVM**:

1. Tạo configuration cache key từ application classes, context loader, profiles, property sources, context customizers và các metadata khác.
2. Nếu key đã được load và chưa bị evict/dirty, **reuse chính ApplicationContext instance cũ**.
3. Nếu key mới, tạo/refresh context.
4. Nếu nhiều unique contexts vượt default cache capacity **32**, Spring Framework sử dụng LRU eviction.
5. Nếu test dùng `@DirtiesContext`, context có thể bị đóng và reload cho lần sau.

**Suy ra:** một full-context test class không nhất thiết tốn lại toàn bộ startup nếu nhiều classes có cùng cache key. Tối ưu test suite bằng việc chuyển mọi full-context test thành nhiều slice contexts khác nhau **không bảo đảm** tổng startup time giảm.

### 4.1. Những yếu tố khiến “cùng full-context” thành nhiều cache keys

- Khác `@ActiveProfiles`.
- Khác `@SpringBootTest(properties=...)`.
- Khác `@TestPropertySource`.
- Khác test configuration classes/imports.
- Khác `@MockitoBean`/`@MockBean` target, qualifier hoặc field fallback name.
- Khác `@DynamicPropertySource` method/context customizer.
- Khác servlet/reactive environment hoặc test slice annotations.
- Khác parent context/hierarchy.
- Một context bị `@DirtiesContext` hoặc LRU evict.
- Test được chạy trong các **forked JVMs khác nhau** (static cache không cross-process).

**Phải phân biệt chi phí startup context với chi phí mỗi test method.** JUnit methods, fixtures, DB cleanup, transactional rollback, Mockito stubbing, Testcontainers operations và HTTP requests vẫn tốn thời gian dù context hit.

### 4.2. Mô hình chi phí gần đúng

Nếu gọi:

- `S(K)`: thời gian khởi tạo context cache key K.
- `N(K)`: số lần startup thực vì miss/dirty/eviction.
- `E(i)`: thời gian thực thi method i cùng fixtures.
- `F`: chi phí fork, database/container setup, build overhead.

Thì tổng thời gian gần đúng:

```text
Total ≈ Σ_keys [N(K) × S(K)] + Σ_methods E(i) + F
```

Đây là **mô hình tư duy**, không phải công thức timing chính thức của Spring. Không cộng trừ số liệu máy khác và không hứa một ngưỡng 10x cố định.

**Một chuyển đổi test có ích khi** nó làm giảm S(K), N(K) hoặc E(i) mà **không giảm khả năng phát hiện lỗi cần thiết**. Cần đo cả latency và mutation/regression coverage.

## 5. Quy tắc chọn: unit, slice hay giữ full-context?

### 5.1. Chọn pure unit test khi

Behavior cần kiểm tra là logic Java thuần:

- input validation nghiệp vụ không cần Spring MVC;
- chuẩn hóa text/số tiền;
- tính toán tax/discount/fee;
- lựa chọn branch, fallback hoặc retry decision không phụ thuộc framework;
- tạo command/value object;
- quy tắc business trước khi gọi persistence port.

Ưu tiên **constructor injection** để tự tạo object và fake/mock dependencies. Trong pure unit test **không cần** `@SpringBootTest`, `@ExtendWith(SpringExtension.class)`, ApplicationContext hoặc `@Autowired`.

Dùng Mockito khi phải mô phỏng một dependency; dùng fake/real immutable objects khi dễ hơn. Unit test phải kiểm tra **kết quả logic**, không chỉ `verify(mock)` cho một call không liên quan. Trường hợp quan trọng: nếu test verify chính việc stubbing, nó có thể xanh mà không chạy production behavior.

### 5.2. Chọn @WebMvcTest khi

Câu hỏi về **web layer**:

- URL route và HTTP method;
- JSON request/response binding;
- `@Valid`/Bean Validation;
- HTTP status, response headers, error mapping;
- controller exception resolution;
- Spring MVC converters/argument resolvers;
- request filters/security nếu thật sự được nạp trong slice.

`@WebMvcTest(ProductController.class)` nạp MVC infrastructure và giới hạn component scanning theo một số loại web components. Regular `@Service`, `@Repository` và nhiều regular `@ConfigurationProperties` beans không được scan mặc định. Vì vậy thường dùng `@MockitoBean` để cung cấp fake collaborator.

**Giới hạn:** khi mock ProductService, test **không** chứng minh ProductService chạy đúng, service bean được tạo, JPA query đúng hoặc database commit. Nếu web slice không nạp custom SecurityFilterChain, đừng gọi đó là production security test.

### 5.3. Chọn @DataJpaTest khi

Câu hỏi về **entity mapping, repository method hoặc JPA query**:

- entity được lưu/đọc với ID;
- derived queries đúng với mapping;
- JPA converter, cascade/relationship behavior;
- custom JPQL/SQL trong phạm vi datasource được cung cấp.

`@DataJpaTest` nạp phần data JPA cần thiết, không mặc định scan mọi service/controller; thông thường chọn **embedded test database** nếu trên classpath có H2/HSQL/Derby phù hợp. Mặc định data JPA tests có transaction rollback sau mỗi test. Cần nhớ H2 **không tương đương** PostgreSQL/MySQL/Oracle về dialect, collation, JSONB, constraints, locking, sequences hoặc query planner. Nếu contract phụ thuộc production database, dùng `@AutoConfigureTestDatabase(replace = NONE)` và một datasource test như Testcontainers DB tương ứng.

### 5.4. Giữ @SpringBootTest khi

Câu hỏi về **cách các tầng thực nối với nhau**:

- controller→service→repository qua real bean injection;
- Boot auto-configuration, properties, security policies;
- @Transactional proxies và bean lifecycle;
- multiple modules hoặc conditional beans;
- filter/interceptor/configuration integration;
- một regression từng xảy ra vì wiring và chỉ thấy ở startup/full path.

`@SpringBootTest + @AutoConfigureMockMvc` có thể là lựa chọn đủ khi bạn cần Spring container + MVC flow nhưng **không cần real socket**. Nó không mở HTTP server mặc định. Nếu mục tiêu là network/port/server filters/protocol boundaries, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và HTTP client thật.

## 6. Một quy trình quyết định có căn cứ

```text
Bắt đầu từ test full-context đang chạy
                   |
                   v
Nó cần chứng minh điều gì?
                   |
       +-----------+-------------+
       |           |             |
    Java logic    MVC contract   JPA/query
       |           |             |
     Unit       @WebMvcTest   @DataJpaTest
       |           |             |
       +-----------+-------------+
                   |
                   v
Có assertion nào còn cần cross-layer wiring?
              /           \
            Có             Không
            |               |
    Giữ full-context      Xem thêm security/
    seam test nhỏ         config/network risks
            |               |
            +-------+-------+
                    |
                    v
    So positive + negative evidence
                    |
                    v
     Chạy cả suite, đo tốc độ, QA
```

Bước thực tế:

1. Trích ra **hành vi** mà test cũ bảo vệ. Ghi rõ endpoint/field/constraint/query/integration.
2. Phân loại theo layer đang chứa implementation gây rủi ro.
3. Dựng unit/slice tests mới và assertion cho cả valid/invalid cases.
4. Xác nhận service/controller/repository **thật** vẫn được gọi ít nhất một lần ở full integration seam nếu các tầng cần liên kết.
5. Giữ security/transaction/external integration tests nếu chúng bảo vệ các rủi ro thực.
6. Chạy test cũ và mới trong giai đoạn migration, so hành vi pass/fail và lỗi hồi quy.
7. Sau khi đủ evidence mới bỏ test cũ dư thừa.
8. Đo thời gian/counters, cache misses, số contexts, memory và sự ổn định CI.
9. Review false positives từ mocks, test data và test profiles.
10. Không giảm test scope chỉ vì một class khó khởi động; đôi khi lỗi startup chính là bug cần phát hiện.

**Không cần một full-context test cho mọi validation case.** Nhưng cũng không nên chỉ giữ toàn unit tests rồi mặc định toàn ứng dụng được cấu hình đúng.

## 7. Ví dụ runnable: Product API với 4 tầng bằng chứng

Ta tạo một mini Spring Boot application quản lý sản phẩm. Mục đích là minh họa cách chia một bộ test full-context nặng thành **4 suites có ranh giới rõ**, với một full integration suite nhỏ giữ lại.

Production flow:

```text
HTTP JSON
    |
    v
ProductController (@Valid, /products)
    |
    v
ProductService (normalize + domain validation)
    |
    v
ProductRepository (Spring Data JPA)
    |
    v
Product entity / H2 test DB
```

Trong ví dụ:

- Input DTO `CreateProductRequest(name, priceCents)`.
- Controller validate HTTP request bằng `@NotBlank` và `@Positive`.
- ProductService validate domain inputs độc lập, trim name, lưu qua repository.
- ProductRepository là một Spring Data JPA interface, có derived query.
- `ProductNotFoundException` được map thành HTTP 404.
- ProductView là record JSON response.
- H2 là DB test local; không có network/credentials thật.
- Có **15 JUnit methods**: 5 pure unit, 5 MVC slice, 3 JPA slice và 2 full-context seam.

**Cấu trúc này không có Spring Security dependency.** Với một ứng dụng có auth/CSRF, phải kiểm tra policy riêng ở security-enabled slice/full context; không hiểu kết quả 2xx của demo là policy cho production API.

### 7.1. File tree

```text
build.gradle
settings.gradle
src/
├── main/
│   ├── java/com/example/testlayers/
│   │   ├── TestLayersApplication.java
│   │   ├── Product.java
│   │   ├── ProductRepository.java
│   │   ├── ProductService.java
│   │   ├── ProductController.java
│   │   ├── CreateProductRequest.java
│   │   ├── ProductView.java
│   │   └── ProductNotFoundException.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/testlayers/
    ├── ProductServiceTest.java
    ├── ProductControllerWebMvcTest.java
    ├── ProductRepositoryDataJpaTest.java
    └── ProductFlowSpringBootTest.java
```

### 7.2. Gradle build

**File `build.gradle`**, Groovy DSL; cần Gradle/Java 17 toolchain và Gradle Wrapper phù hợp:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'test-layers-demo'
```

Spring Boot BOM quản lý versions của Spring Framework, JPA, Jackson, Hibernate Validator, H2 và JUnit. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và Mockito test dependencies cần thiết. Không cần đưa Spring Security vào project này; nếu thêm nó về sau, MVC/security expectations sẽ thay đổi.

### 7.3. Spring Boot application và H2 test schema

**File `src/main/java/com/example/testlayers/TestLayersApplication.java`:**

```java
package com.example.testlayers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestLayersApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestLayersApplication.class, args);
    }
}
```

**File `src/main/resources/application.properties`:**

```properties
# Local demo only; H2 is an embedded in-memory database.
spring.datasource.url=jdbc:h2:mem:layers;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

Dùng H2 là **quyết định giảm hạ tầng của demo**, không phải bằng chứng cho dialect production. Trong project thực, đặt config test ở `src/test/resources/application-test.properties` hoặc quản lý `@ActiveProfiles("test")` để không đẩy default demo DB vào production. Đối với sample này, application.properties chủ ý đặt H2 để cả 4 test classes chạy cục bộ. `spring.jpa.hibernate.ddl-auto=create-drop` tạo schema từ entity metadata lúc app context start và xóa khi đóng; với DB thực, dùng Flyway/Liquibase migrations thay vì ddl-auto demo.

## 8. Production code: JPA và domain services

### 8.1. Entity

**File `src/main/java/com/example/testlayers/Product.java`:**

```java
package com.example.testlayers;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private int priceCents;

    protected Product() {
        // For JPA
    }

    public Product(String name, int priceCents) {
        this.name = name;
        this.priceCents = priceCents;
    }

    // Explicit ID constructor is useful for unit test fixtures.
    public Product(Long id, String name, int priceCents) {
        this.id = id;
        this.name = name;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getPriceCents() {
        return priceCents;
    }
}
```

Lưu ý: constructor có ID chỉ dùng tạo fixture phía unit tests; repository sẽ dùng constructor không ID và JPA sinh primary key. Việc expose ID constructor có thể không phải design bạn muốn ở domain production; một project lớn có thể dùng package-private fixtures/test factory hoặc reflection test utilities. **Không gọi constructor có explicit ID để giả lập việc JPA đã persist** trong repository slice test.

### 8.2. Repository

**File `src/main/java/com/example/testlayers/ProductRepository.java`:**

```java
package com.example.testlayers;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findByName(String name);

    List<Product> findByPriceCentsGreaterThan(int threshold);
}
```

Spring Data JPA triển khai derived queries tại runtime. Unit test mock repository **không thực thi** những queries này. `@DataJpaTest` với H2 thật chạy JPA mapping và query generation.

### 8.3. DTOs

**File `src/main/java/com/example/testlayers/CreateProductRequest.java`:**

```java
package com.example.testlayers;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive int priceCents
) {}
```

**File `src/main/java/com/example/testlayers/ProductView.java`:**

```java
package com.example.testlayers;

public record ProductView(
        Long id,
        String name,
        int priceCents
) {}
```

Validation annotations trên request record được Spring MVC chạy khi controller dùng `@Valid @RequestBody` và có Jakarta Bean Validation provider. Với input JSON thiếu name hoặc priceCents=0, MVC test phải chứng minh HTTP 400 **mà không gọi service**.

### 8.4. Domain exception

**File `src/main/java/com/example/testlayers/ProductNotFoundException.java`:**

```java
package com.example.testlayers;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product " + id + " not found");
    }
}
```

`@ResponseStatus` giúp MVC map exception thành 404. Nó không phải cấu hình JPA, không cần full application để test thông qua MVC slice khi exception class được throw thực sự bởi mock service.

### 8.5. Service có domain behavior cần unit test

**File `src/main/java/com/example/testlayers/ProductService.java`:**

```java
package com.example.testlayers;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductView create(
            String name, int priceCents) {

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        if (priceCents <= 0) {
            throw new IllegalArgumentException(
                    "priceCents must be positive");
        }

        Product saved = repository.save(
                new Product(name.trim(), priceCents));
        return toView(saved);
    }

    public ProductView find(long id) {
        if (id <= 0) {
            throw new ProductNotFoundException(id);
        }

        Product found = repository.findById(id)
                .orElseThrow(() ->
                        new ProductNotFoundException(id));
        return toView(found);
    }

    private static ProductView toView(Product product) {
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPriceCents());
    }
}
```

Tầng service chịu trách nhiệm một số business invariants kể cả khi không đi từ HTTP. Điều này tránh phụ thuộc hoàn toàn vào `@Valid` của controller: một batch job hoặc Kafka listener vẫn có thể gọi service.

Không có transaction đặc biệt trong service mẫu; repository CRUD methods tự quản lý transactions theo Spring Data JPA khi cần. Trong một ứng dụng thật, nếu một method phải thay đổi nhiều rows atomically, có thể cần `@Transactional` ở service và integration test riêng cho commit/rollback/proxy behavior.

### 8.6. REST Controller

**File `src/main/java/com/example/testlayers/ProductController.java`:**

```java
package com.example.testlayers;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductView create(
            @Valid @RequestBody CreateProductRequest request) {
        return service.create(
                request.name(), request.priceCents());
    }

    @GetMapping("/{id}")
    public ProductView get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Ở đây controller **không implement domain rule**. Nó xử lý HTTP path, JSON DTO, MVC validation, status/serialization và chuyển call cho service. Việc tách trách nhiệm giúp unit tests và MVC slice có phạm vi rõ ràng.

## 9. Tầng 1 — Unit test cho ProductService (5 methods)

**File `src/test/java/com/example/testlayers/ProductServiceTest.java`:**

```java
package com.example.testlayers;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    @InjectMocks
    ProductService service;

    @Test
    void createTrimsNameAndReturnsSavedProduct() {
        when(repository.save(any(Product.class)))
                .thenAnswer(invocation -> {
                    Product input = invocation.getArgument(0);
                    return new Product(
                            41L,
                            input.getName(),
                            input.getPriceCents());
                });

        ProductView actual =
                service.create("  Notebook  ", 1200);

        ArgumentCaptor<Product> captor =
                ArgumentCaptor.forClass(Product.class);
        verify(repository).save(captor.capture());

        assertThat(captor.getValue().getName())
                .isEqualTo("Notebook");
        assertThat(captor.getValue().getPriceCents())
                .isEqualTo(1200);

        assertThat(actual)
                .isEqualTo(new ProductView(
                        41L, "Notebook", 1200));
    }

    @Test
    void blankNameIsRejectedBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.create("   ", 100))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(repository);
    }

    @Test
    void zeroPriceIsRejectedBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.create("Pen", 0))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(repository);
    }

    @Test
    void findingExistingProductMapsDto() {
        when(repository.findById(9L))
                .thenReturn(Optional.of(
                        new Product(9L, "Pen", 250)));

        ProductView actual = service.find(9L);

        assertThat(actual)
                .isEqualTo(new ProductView(
                        9L, "Pen", 250));
        verify(repository).findById(9L);
    }

    @Test
    void missingProductRaisesDomainException() {
        when(repository.findById(404L))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.find(404L))
                .isInstanceOf(ProductNotFoundException.class);

        verify(repository).findById(404L);
    }
}
```

### 9.1. Test này có cần Spring không?

**Không.** `MockitoExtension` tạo mock repository, `@InjectMocks` tạo ProductService với constructor injection. Không có Spring ApplicationContext, không JPA, không H2 và không Spring TestContext cache lookup.

**Năm kết luận được chứng minh:**

- Name được trim **trước khi repository.save(...)**.
- Price được giữ đúng.
- Blank name không gây persistence call.
- Price 0 không gây persistence call.
- Existing/missing lookup dẫn tới DTO hoặc domain exception đúng.

Test **không** chứng minh Hibernate mapping, transaction, controller JSON, 404 HTTP status hay real dependency injection. Những bằng chứng đó thuộc các tầng tiếp theo.

### 9.2. Đừng viết một unit test rỗng

Một test kiểu:

```java
when(repository.findById(9L)).thenReturn(Optional.empty());
verify(repository).findById(9L);
```

là **phản ví dụ**: nó verify một call chưa hề được production service thực hiện, nên sẽ fail hoặc nếu verify nhầm một setup interaction thì không có giá trị. Hãy gọi `service.find(9L)` trước khi verify, assert exception/result và kiểm tra đúng behavior.

**Một test chỉ verify Mockito calls chưa đủ nếu kết quả/domain invariant mới là điều cần bảo vệ.**

## 10. Tầng 2 — @WebMvcTest cho controller (5 methods)

**File `src/test/java/com/example/testlayers/ProductControllerWebMvcTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;

    @Test
    void validCreateBindsJsonAndReturns201()
            throws Exception {
        when(service.create("Notebook", 1200))
                .thenReturn(new ProductView(
                        41L, "Notebook", 1200));

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"Notebook\",\"priceCents\":1200}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));

        verify(service).create("Notebook", 1200);
    }

    @Test
    void blankNameIsRejectedWith400()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  \",\"priceCents\":1200}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void zeroPriceIsRejectedByHttpValidation()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"Notebook\",\"priceCents\":0}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void validGetSerializesProductView()
            throws Exception {
        when(service.find(9L))
                .thenReturn(new ProductView(
                        9L, "Pen", 250));

        mvc.perform(get("/products/{id}", 9L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.name").value("Pen"))
                .andExpect(jsonPath("$.priceCents")
                        .value(250));

        verify(service).find(9L);
    }

    @Test
    void domainNotFoundExceptionMapsTo404()
            throws Exception {
        when(service.find(404L))
                .thenThrow(
                    new ProductNotFoundException(404L));

        mvc.perform(get("/products/{id}", 404L))
                .andExpect(status().isNotFound());
    }
}
```

### 10.1. Vì sao mock service ở MVC slice là hợp lý?

Vì ở nhóm này **câu hỏi là MVC contract**, không phải business logic. ProductService được thay bằng Mockito mock để:

- cấp output deterministic;
- tránh cần DataSource/JPA;
- buộc controller route, `@Valid`, request body conversion, status và response JSON hoạt động thật;
- kiểm tra `verifyNoInteractions(service)` ở negative validation cases, cho thấy invalid request bị chặn trước service.

Những test này **không chứng minh** service đã persist hoặc constructor injection của full app đúng. Một số tests full-context bên dưới sẽ cung cấp bằng chứng cross-layer.

### 10.2. @MockitoBean không giống @Mock

- `@Mock` từ Mockito tạo mock trong JUnit unit test, **không thay bean trong Spring context**.
- `@MockitoBean` (Spring Framework 6.2, dùng trong Boot 3.5) tạo/override một bean trong **test ApplicationContext**. Nó tham gia Spring TestContext context customizer/cache key.
- Legacy Spring Boot `@MockBean` đã deprecated từ Boot 3.4, hướng dùng `@MockitoBean` trong Boot 3.5.
- Các bean overrides có thể làm test slice/full context cache keys khác nhau. Không gắn một danh sách mocks khác nhau vào từng lớp chỉ vì tiện nếu chúng kiểm tra cùng một MVC config.

**Không dùng `@MockitoBean` nếu mục tiêu là kiểm tra bean thật đã được tạo/inject hoặc AOP advice của bean đó.**

### 10.3. Lưu ý với Spring Security

Demo không có Security starter. Trong ứng dụng thật có SecurityFilterChain, `@WebMvcTest` có thể auto-configure Spring Security, nhưng custom configuration có thể không được slice load như full app. Khi security là mục tiêu:

- import đúng security configuration hoặc dùng security-enabled full-context test;
- dùng `spring-security-test` với `@WithMockUser`/`user(...)`/`csrf()` khi phù hợp;
- test cả anonymous/forbidden/authorized;
- không đặt `@AutoConfigureMockMvc(addFilters=false)` để ép response 200;
- đừng lấy kết quả của MVC slice với fake security config làm bằng chứng production authorization đúng.

## 11. Tầng 3 — @DataJpaTest cho persistence (3 methods)

**File `src/test/java/com/example/testlayers/ProductRepositoryDataJpaTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ProductRepositoryDataJpaTest {

    @Autowired
    ProductRepository repository;

    @Test
    void entityIsPersistedAndFoundById() {
        Product saved = repository.saveAndFlush(
                new Product("Notebook", 1200));

        assertThat(saved.getId()).isNotNull();

        Product found = repository.findById(
                saved.getId()).orElseThrow();

        assertThat(found.getName())
                .isEqualTo("Notebook");
        assertThat(found.getPriceCents())
                .isEqualTo(1200);
    }

    @Test
    void derivedFindByNameQueryFindsRow() {
        repository.saveAndFlush(
                new Product("Pen", 250));

        Product found = repository.findByName("Pen")
                .orElseThrow();

        assertThat(found.getName()).isEqualTo("Pen");
        assertThat(found.getPriceCents())
                .isEqualTo(250);
    }

    @Test
    void greaterThanQueryFiltersRows() {
        repository.saveAndFlush(
                new Product("Pen", 250));
        repository.saveAndFlush(
                new Product("Notebook", 1200));

        assertThat(repository
                .findByPriceCentsGreaterThan(500))
                .extracting(Product::getName)
                .containsExactly("Notebook");
    }
}
```

### 11.1. Những gì @DataJpaTest thực sự chứng minh

- JPA entity có thể được persist/read trên **H2** test DB.
- Generated ID và basic column mapping hoạt động.
- Spring Data derived query `findByName` hoạt động.
- `findByPriceCentsGreaterThan` sinh và chạy query đúng trong môi trường đó.
- Spring/JPA transaction infrastructure cho slice được nạp đủ để test.

Spring Boot documentation nêu JPA slice mặc định có transaction và rollback sau mỗi method. Không cần `@DirtiesContext` sau từng test chỉ để tránh data từ method trước, miễn test transaction cleanup hoạt động và code không ghi qua một resource/thread khác.

### 11.2. H2 không chứng minh mọi hành vi PostgreSQL/MySQL

Nếu production query dùng JSONB, vendor-specific SQL, locking, collation, generated columns, migrations hoặc database-specific constraints, kết quả H2 slice **không đủ**. Khi cần evidence, dùng Testcontainers cho đúng engine/version và cấu hình datasource/test database replacement thích hợp.

Một repository có thể pass H2 nhưng fail PostgreSQL vì SQL dialect, tên reserved words, timezone hoặc transaction isolation. Không xóa real-DB integration test chỉ vì @DataJpaTest(H2) xanh.

### 11.3. Entity constructor chỉ để fixture

JPA slice dùng `new Product("...", price)` với ID null để database sinh ID. Constructor `new Product(9L, ...)` dành cho unit fixtures và **không được** dùng để tuyên bố một entity đã persist thành công.

## 12. Tầng 4 — giữ một full-context seam test nhỏ (2 methods)

**File `src/test/java/com/example/testlayers/ProductFlowSpringBootTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ProductFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @Test
    void postThenGetUsesRealControllerServiceAndJpa()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  Notebook  \",\"priceCents\":1200}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));

        Product stored = repository
                .findByName("Notebook")
                .orElseThrow();

        mvc.perform(get("/products/{id}", stored.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id")
                        .value(stored.getId()))
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));
    }

    @Test
    void invalidJsonIsRejectedBeforePersistence()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  \",\"priceCents\":0}"))
                .andExpect(status().isBadRequest());

        assertThat(repository.count()).isEqualTo(before);
    }
}
```

**Hai tests này giữ lại vì chúng cung cấp thứ mà unit/MVC/JPA slices riêng biệt không chứng minh:**

- Spring Boot tạo đủ controller, service và repository **thật**.
- HTTP request được dispatch qua MockMvc đến controller thật.
- Controller gọi ProductService thật, chuẩn hóa input.
- ProductService gọi ProductRepository thật, ghi/read H2 thật.
- Đường GET lấy lại persisted entity và serialize response.
- Input invalid bị MVC validation reject trước persistence.

Đây là một **cross-layer seam test**, không phải hàng chục full-context tests lặp cùng behavior với nhiều input variants.

### 12.1. Vì sao @Transactional có thể rollback ở đây?

Trong cấu hình mặc định `@SpringBootTest` (webEnvironment=MOCK) với `@AutoConfigureMockMvc`, request MockMvc được xử lý **trong cùng test thread** thay vì qua TCP/server thread riêng. Spring TestContext transaction được áp dụng trong test thread; các repository operations trong demo tham gia test transaction, và framework rollback khi kết thúc từng test.

**Cảnh báo quan trọng:** khi chuyển sang `@SpringBootTest(webEnvironment=RANDOM_PORT)` và gửi HTTP thật, client/test thread với server thread **không** tự chia sẻ cùng transaction. `@Transactional` trên test **không đảm bảo** rollback writes đã được server commit. Lúc đó cần cleanup DB riêng hoặc isolate dữ liệu/schema.

### 12.2. @SpringBootTest không mặc định là live HTTP

Mặc định `@SpringBootTest` dùng mock web environment khi Spring MVC có trên classpath, không tự mở embedded HTTP socket. Thêm `@AutoConfigureMockMvc` để inject MockMvc. Chỉ khi dùng `RANDOM_PORT`/`DEFINED_PORT` thì embedded server nghe cổng thật.

Điều này quan trọng khi review việc chuyển từ full-context sang slice: **nếu test cũ chỉ gọi MockMvc, chuyển sang @WebMvcTest có thể giữ MVC routing evidence**; nhưng vẫn cần một seam test để chứng minh wiring thật. Nếu test cũ dùng real HTTP/socket/TLS, chuyển sang MockMvc **mất một ranh giới khác nữa**.

## 13. Kiểm kê bằng chứng sau khi chia test

| Yêu cầu/behavior | Unit | MVC slice | JPA slice | Full seam |
|---|:---:|:---:|:---:|:---:|
| Blank name bị service reject | ✓ | — | — | Có thể, nhưng khác ranh giới |
| Price 0 bị service reject | ✓ | — | — | Có thể |
| Service trim name | ✓ | Service mock, không | — | ✓ (path thật) |
| POST /products → 201 | — | ✓ | — | ✓ |
| JSON response shape | — | ✓ | — | ✓ |
| @Valid request invalid → 400 | — | ✓ | — | ✓ |
| Domain exception → HTTP 404 | — | ✓ | — | Có thể bổ sung nếu cần |
| Generated JPA id/columns | — | — | ✓ | ✓ |
| Spring Data derived queries | — | — | ✓ | GET path tác động một phần |
| Controller→service bean injection | — | Service mock | — | ✓ |
| Service→repository real persistence | Repo mock | — | Chỉ repo | ✓ |
| Real TCP servlet server | — | — | — | — |
| Production DB dialect/migrations | — | — | Chỉ khi dùng đúng DB | H2 demo, không |
| Spring Security auth/CSRF | — | Không có dependency trong demo | — | Không có trong demo |
| External HTTP/Kafka/transactions across systems | — | — | — | — |

Dấu ✓ nghĩa là **được kiểm chứng trong ví dụ theo scope mô tả**, không có nghĩa tất cả edge cases được chứng minh. Dấu “—” nghĩa là chưa được kiểm chứng; nếu đó là acceptance criterion, phải thêm test phù hợp. Một test đơn lẻ có thể đóng góp vào nhiều yêu cầu nhưng không nên suy rộng quá phạm vi đã chạy.

### 13.1. Kết quả mong đợi sau migration

| Suite | Test methods | Context | Mục tiêu |
|---|---:|---|---|
| `ProductServiceTest` | 5 | Không có Spring | Domain behavior |
| `ProductControllerWebMvcTest` | 5 | MVC slice | HTTP binding/validation/status |
| `ProductRepositoryDataJpaTest` | 3 | JPA slice/H2 | ORM queries |
| `ProductFlowSpringBootTest` | 2 | Full context + MockMvc/H2 | Cross-layer wiring |
| **Tổng** | **15** | 3 loại Spring contexts + unit | Bằng chứng có phân lớp |

Đây là **kế hoạch kiểm thử dự kiến** dựa trên mã mẫu. Số executed/passed thực tế phải đọc từ Gradle/JUnit report sau khi chạy; bài soạn không giả định đã thực thi.

## 14. Chạy các test suites

**Linux/macOS** với Gradle Wrapper nếu project đã tạo wrapper:

```bash
./gradlew test --tests "com.example.testlayers.ProductServiceTest"
./gradlew test --tests "com.example.testlayers.ProductControllerWebMvcTest"
./gradlew test --tests "com.example.testlayers.ProductRepositoryDataJpaTest"
./gradlew test --tests "com.example.testlayers.ProductFlowSpringBootTest"

# All tests in the project:
./gradlew test
```

**Windows PowerShell**:

```powershell
.\gradlew.bat test --tests "com.example.testlayers.ProductServiceTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductControllerWebMvcTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductRepositoryDataJpaTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductFlowSpringBootTest"
.\gradlew.bat test
```

Nếu dự án dùng Maven, cần pom.xml với Spring Boot 3.5 parent/BOM, starters tương ứng, H2 và JUnit Platform/Surefire tương thích; rồi chọn test bằng Maven Wrapper, ví dụ `./mvnw -Dtest=ProductControllerWebMvcTest test`. Đây là lệnh minh họa cho **Maven project đã có wrapper**, không yêu cầu vừa Gradle vừa Maven.

Khi chạy:

- Kiểm tra Java 17+ được dùng bởi test worker.
- Bảo đảm H2 trên test runtime classpath.
- Đọc reports trong `build/test-results/test` và `build/reports/tests/test` (đường dẫn Gradle thông thường).
- Xác nhận expected **15 executed**, không chỉ `BUILD SUCCESSFUL` do cache/UP-TO-DATE.
- Không giới hạn test suite chỉ chạy `ProductServiceTest` rồi tuyên bố đã kiểm tra MVC/JPA/full path.

## 15. Khi nào không được thay full-context test?

### 15.1. Security contract

Một web slice với mock service có thể cho 200 nhưng không nạp đúng production `SecurityFilterChain`, hoặc test vô hiệu hóa filters để tránh 403. Điều đó không kiểm tra authorization, JWT decoder, CSRF, CORS/filter behavior, role mappings. Giữ **security-enabled tests** với custom security config đúng hoặc full context; thêm real HTTP integration khi yêu cầu.

**Không dùng `@AutoConfigureMockMvc(addFilters=false)` làm mẹo làm test xanh** nếu full test ban đầu kiểm chứng request authentication/authorization.

### 15.2. Transaction proxy/propagation và persistence consistency

Unit test gọi `new Service(repositoryMock)` **không chạy Spring AOP proxy**. Nếu bug nằm ở `@Transactional`, `@Cacheable`, `@Retryable`, Spring Security method advice hoặc aspect ordering, pure unit test không thể bắt được. JPA slice có thể chứng minh repo behavior nhưng không chứng minh service transaction boundary. Cần giữ integration test với service bean được Spring quản lý và DB phù hợp.

### 15.3. Auto-configuration và configuration properties

Một unit test kiểm tra class constructor không chứng minh Spring Boot bind `@ConfigurationProperties`, validation constraints hoặc condition `@ConditionalOnProperty`. Khi test custom starter, `ApplicationContextRunner` là một lựa chọn nhẹ và phù hợp, nhưng nếu bug nằm trong full SpringApplication ConfigData/profile loading, cần test whole app.

### 15.4. External systems và protocol behavior

Mock `RestClient` hoặc KafkaTemplate không chứng minh HTTP/TLS, serialization qua real transport hoặc Kafka producer ACK. Nếu test cũ có Testcontainers/PostgreSQL/Kafka và phát hiện lỗi khi tương tác thực, không bỏ hoàn toàn mà thay bằng fake cho tất cả suites. Giữ số integration tests đủ cho protocol boundaries và failure modes quan trọng.

### 15.5. Real HTTP / Servlet container

MockMvc chạy in-process. Khi cần kiểm tra server port, compression, TLS, HTTP filters thật, request/response trên socket hoặc reverse-proxy integration, dùng `RANDOM_PORT` + client HTTP (hoặc higher environment). MVC slice không bao phủ transport layer.

### 15.6. Cross-layer bug từng xảy ra

Nếu đã từng phát hiện lỗi do bean không được scan, repository method được inject sai type, DTO khác schema, HTTP exception mapping không tương thích service, xóa toàn bộ full-context test sẽ làm mất regression guard. Một seam test đúng hợp đồng thường rẻ hơn việc debug production incident.

## 16. Cache reuse có thể khiến kết quả tối ưu trái trực giác

### 16.1. Không phải số lượng test classes quyết định startup count

Giả sử 30 full-context classes dùng **một** cache key: sau startup đầu tiên, đa số tests được cache hit. Thay chúng bằng 30 classes `@WebMvcTest` có 30 combinations `@MockitoBean` khác nhau có thể tạo nhiều cache keys, mỗi key phải start một MVC context.

Dù MVC context nhẹ hơn full context, số lần startup tăng có thể khiến suite **không nhanh hơn**. Vì vậy nên:

- Giữ @WebMvcTest classes có config thật sự tương đương để cache hit.
- Tránh unique inline properties/ActiveProfiles không cần thiết.
- Dùng mock bean names/qualifiers nhất quán khi chúng tương đương.
- Không đặt `@DirtiesContext` trên mọi class.
- Không tăng cache max size bừa bãi chỉ vì suite chậm.
- Đo thời gian theo cả *context cold starts* lẫn *method execution*.

### 16.2. Không ép cache sharing nếu behavior khác

Nếu service chạy hai modes khác nhau bằng properties, dùng hai contexts là đúng. Nếu JPA test cần real PostgreSQL trong khi controller slice chỉ cần fake service, không phải mọi test nên dùng một full context.

**Correctness và isolation quan trọng hơn cache hit rate.** Việc ép nhiều tests về cùng config có thể tạo shared mutable singleton state hoặc che behavior khác nhau.

### 16.3. Static cache không qua các JVM forks

Spring TestContext cache sống trong một JVM test worker. Gradle `maxParallelForks`, `forkEvery` và Maven Surefire fork settings có thể khiến classes ở nhiều processes không share cache. Không nhầm Gradle build cache với Spring ApplicationContext cache.

## 17. Chứng minh hiệu năng bằng cách đo đúng

### 17.1. Chuẩn bị baseline

Trước refactor, ghi nhận trên cùng CI runner/config:

- Tổng wall-clock test time, cold/warm runs.
- Số JUnit executed/passed/failed/skipped.
- Số context startup thực.
- Spring context cache hits/misses và current size.
- Số unique test configuration keys nếu có instrumentation phù hợp.
- Gradle/Maven forks/parallel settings.
- External setup time: H2/JPA, Testcontainers image pull, migrations, server startup.
- Memory peak, CPU load và flaky failures.

Spring Framework TestContext hỗ trợ log statistics ở category `org.springframework.test.context.cache` ở DEBUG level.

**Ví dụ với Gradle test worker JVM:**

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'logging.level.org.springframework.test.context.cache',
            'DEBUG'
}
```

Đây là snippet tùy chọn. Thông số logging tùy test logging backend; trên một số cấu hình cần thiết lập logger theo Logback/Log4j2 test configuration để thấy Spring TestContext cache logs sớm. Không nhất thiết bật DEBUG cho toàn bộ CI vì verbose output có thể tăng noise và thời gian I/O.

### 17.2. Đo sau khi tách tests

Chạy lại **cùng scenarios** và environment:

1. Xem các assertions/negative cases đã được chuyển hoặc giữ.
2. Kiểm tra 15 tests của demo thực sự executed.
3. Đo context load times, runtime theo class và total suite time.
4. Nhìn cache hits/misses có thay đổi do slice configurations không.
5. So sánh memory và flakiness.
6. Nếu tốc độ cải thiện nhưng một yêu cầu không còn guard, **migration chưa thành công**.
7. Nếu không cải thiện, kiểm tra JPA/H2 startup, Gradle forks, unique cache keys hoặc @DirtiesContext.
8. Điều chỉnh mức test theo evidence, không theo một benchmark máy đơn lẻ.

### 17.3. Đừng đặt mục tiêu tỷ lệ unit/slice/full cố định

Test pyramid là một định hướng chi phí/boundary, không phải quy định “90% unit, 10% integration” đúng cho mọi dự án. Một API có heavy data consistency/security cần nhiều integration tests; một thư viện pure calculation có thể gần như toàn unit tests. Chỉ số có giá trị hơn là **số rủi ro quan trọng được bảo vệ và thời gian phản hồi của CI**.

## 18. Migration checklist từng bước cho một PR thực

Khi thấy một lớp full-context test có 30 methods:

1. **Đọc mục tiêu từng method.** Lập bảng behavior, assertion, dependency, risk.
2. **Tách những tests thuần logic** sang JUnit + Mockito/fakes, bỏ Spring annotations.
3. **Tách controller serialization/validation** sang @WebMvcTest với service mock.
4. **Tách repository mapping/query** sang @DataJpaTest; chọn DB engine dựa trên yêu cầu.
5. **Giữ ít nhất những full-context paths có giá trị cross-layer**; không giữ dư chỉ vì test cũ từng có.
6. **Bổ sung security/transaction/configuration tests** nếu test cũ đang chứng minh chúng.
7. **Chạy song song cũ/mới trong giai đoạn chuyển đổi** nếu có thể và kiểm chứng cả negative paths.
8. **Sửa fixtures**, không sửa production security/transaction config chỉ để slice pass.
9. **Kiểm tra test runner count** và việc các lớp mới đã được CI phát hiện.
10. **Đo timing**, context cache stats, forks, memory, flakiness.
11. **Xóa test cũ dư thừa** sau khi có bằng chứng parity; review code/diffs.
12. **Đặt tên test theo tầng và contract** để người sau không nhầm scope.

### 18.1. Bảng chuyển đổi mẫu

| Full-context test cũ | Cách chuyển | Bằng chứng cần giữ |
|---|---|---|
| Kiểm tra `if (price <= 0)` | ProductServiceTest | Exception và no repository call |
| Kiểm tra POST JSON và @Valid | ProductControllerWebMvcTest | 201/400/response JSON |
| Kiểm tra JPQL/derived finder | ProductRepositoryDataJpaTest | Row persist/query thật |
| Kiểm tra controller → service → JPA | ProductFlowSpringBootTest | Real beans và database write/read |
| Kiểm tra JWT/roles/CSRF | Giữ security-focused integration | Anonymous/USER/admin denied/allowed |
| Kiểm tra random port socket | Giữ RANDOM_PORT smoke | Real HTTP client/server boundary |
| Kiểm tra DB transaction across service | Giữ transaction integration | Commit/rollback/proxy behavior |

Không được xóa hàng cuối trong bảng chỉ vì một slice test khác xanh: chúng kiểm tra các boundary khác nhau.

## 19. Những sai lầm thường gặp khi giảm scope

| Anti-pattern | Vì sao tạo false confidence | Cách tốt hơn |
|---|---|---|
| Đổi mọi @SpringBootTest sang unit tests | Mất framework wiring | Giữ seam integration tests |
| Mock repository rồi assert SQL query đúng | Không chạy SQL | @DataJpaTest + DB thật |
| @WebMvcTest với service mock rồi bảo đã test service | Service không chạy | Unit service + full seam |
| @MockitoBean mọi beans chỉ để context start | Mất behavior real beans | Chỉ mock ngoài test boundary |
| Chọn @WebMvcTest để kiểm chứng @Transactional | Không có service proxy/DB path | Full service integration |
| Bỏ security filters để POST được 201 | Không test CSRF/auth | Giữ security-enabled tests |
| H2 test pass rồi khẳng định Postgres production tương thích | Dialect khác | PostgreSQL Testcontainers tests |
| @SpringBootTest(MOCK) được gọi là real HTTP E2E | Không mở socket | RANDOM_PORT HTTP client |
| @Transactional trên RANDOM_PORT test dùng như rollback server writes | Test/server threads khác | Explicit cleanup/isolated DB |
| Đặt @DirtiesContext trên mọi slice | Cache luôn bị evict | Reset state đúng resource |
| Mỗi test class một profile/inline property ngẫu nhiên | Nhiều cache keys | Chuẩn hóa configs tương đương |
| Rất nhiều micro-tests, không có negative cases | Không phát hiện forbidden behaviors | Positive và negative tests |
| Full-context test chỉ assert bean tồn tại | Khả năng phát hiện lỗi thấp | Test cross-layer behavior thực |
| Test runner skip integration classes nhưng CI xanh | Mất coverage | Assert executed counts |
| Dùng Mockito verify mà không gọi production method | Không chứng minh behavior | Call SUT, assert result/side effect |
| Mock authentication rồi nói JWT signature valid | Bỏ verification path | Real decoder/token integration |
| Bỏ migrations khỏi DB tests | Schema có thể khác production | Flyway/Liquibase migration test |
| Tối ưu theo benchmark local một lần | Kết luận không bền | CI baseline/repeatable measurements |

## 20. Các câu hỏi review về “đủ bằng chứng”

Khi reviewer gặp một PR đổi 25 full-context tests thành unit/slices, hãy hỏi:

**Câu 1. Test cũ từng phát hiện loại bug nào?** Nếu từng bắt bug wiring, migration không được xóa toàn bộ wiring test.

**Câu 2. Nếu xóa `@Valid`, test nào đỏ?** MVC slice/full MockMvc phải phát hiện invalid request không còn 400.

**Câu 3. Nếu xóa `trim()` trong ProductService, test nào đỏ?** Unit service test có assertion Input captured + ProductView outcome.

**Câu 4. Nếu sửa repository query thành sai field, test nào đỏ?** JPA slice chạy derived/query thật.

**Câu 5. Nếu bỏ @Service hoặc inject sai repository, test nào đỏ?** Full-context seam test cần khởi động/gọi real beans.

**Câu 6. Nếu mở endpoint admin cho anonymous, test nào đỏ?** Security-enabled integration test đúng policy.

**Câu 7. Nếu HTTP handler chỉ chạy trên MockMvc nhưng server port không mở, test nào đỏ?** RANDOM_PORT HTTP smoke.

**Câu 8. Nếu transaction rollback sai, test nào đỏ?** Transaction integration test, không chỉ mocked repository.

**Câu 9. Số contexts có giảm không?** Đọc cache logs và unique configs; 25 unit tests có thể không cần context, nhưng 25 @WebMvcTest với khác mocks vẫn tạo nhiều context keys.

**Câu 10. Tăng tốc bao nhiêu và điều kiện đo?** So cold/warm runs trên cùng CI worker và cùng tests executed, không cherry-pick.

## 21. Bài tập thực hành và đáp án

### Bài A. Một test tính giảm giá

Một method test `PriceService.discount(1200, 10)` thuần Java nhưng hiện tại dùng `@SpringBootTest` để autowire service. Nên chuyển?

**Có thể.** Nếu logic không phụ thuộc Spring advice/config và dependencies có thể fake, pure unit test là phù hợp. Nếu method được bảo vệ bởi `@Transactional`/`@Cacheable` mà đó là contract, cần test riêng cho advice ấy.

### Bài B. MVC validation

Test POST invalid price=0 đang dùng full-context, chỉ assert 400. Chuyển sang `@WebMvcTest` có đủ?

**Thường có**, nếu MVC slice nạp đúng validator/converters và security config liên quan. Dùng negative test xác nhận controller/service mock **không được gọi**. Giữ một full seam test nếu cần wiring thật.

### Bài C. Repository SQL

Test query `findByPriceCentsGreaterThan` chuyển sang Mockito repository mock, stub trả danh sách đúng. Có đủ?

**Không.** Query thật không được chạy; dùng JPA slice/real DB test.

### Bài D. @WebMvcTest mất service bean

Slice không tìm được `ProductService`, class test fail startup. Có nên chuyển toàn bộ test về full-context?

**Không bắt buộc.** Nếu chỉ test MVC, dùng `@MockitoBean ProductService`. Nếu test muốn real service, dùng full-context test với service thật.

### Bài E. Một integration suite dài 3 phút

Xóa hết và thay 100 pure unit tests giúp suite còn 2 giây. Thành công chưa?

**Chưa có đủ bằng chứng.** Phải chứng minh những contracts đã được bảo vệ trước đó vẫn được kiểm thử, đặc biệt cross-layer, DB dialect, auth và external integration. Tốc độ không bù cho mất regression coverage.

### Bài F. @SpringBootTest không có RANDOM_PORT

Test inject MockMvc và gửi GET, vậy nó kiểm tra TCP socket không?

**Không.** MockMvc in-process. Cần RANDOM_PORT và client HTTP thật để test servlet server/network boundary.

### Bài G. @Transactional trên real HTTP test

Một test RANDOM_PORT POST tạo DB record; sau test dùng @Transactional thì record có tự rollback không?

**Không bảo đảm.** Test thread transaction không bao phủ server thread transaction. Dùng cleanup DB/isolated schema.

### Bài H. Cache key khác do @MockitoBean

Hai MVC slices cùng controller nhưng field mock names/qualifiers khác. Vì sao startup tăng?

**Bean override context customizers** có thể tham gia key, gây thêm cache entries. Chuẩn hóa mock target/field names khi thật sự tương đương.

### Bài I. Khi nào full context lại nhanh hơn slice?

Khi full context đã được warm/cache hit trong cùng JVM, trong khi nhiều unique slice contexts đều cold start, tổng thời gian có thể không cải thiện sau migration. **Cần đo** chứ không dựa hoàn toàn vào tên annotation.

### Bài J. Chuyển full context sang H2 JPA slice

Production dùng PostgreSQL JSONB query. H2 green có đủ không?

**Không.** H2 không chứng minh PostgreSQL dialect/JSONB. Giữ Postgres Testcontainers integration test cho query ấy.

### Bài K. Mock service, controller trả 201

Có chứng minh repository.save thực sự chạy không?

**Không.** MVC slice chỉ chứng minh controller dispatch/JSON/status và call đến mock. Full seam/DB tests mới chứng minh persistence thật.

### Bài L. Integration test bị skipped

Suite báo BUILD SUCCESSFUL nhưng chỉ 13/15 methods executed. Có thể chốt migration QA PASS không?

**Không.** Tìm vì sao 2 tests bị skip (filter, tag, context failure, @Disabled, test selection) trước khi tuyên bố bằng chứng đầy đủ.

## 22. Checklist hoàn tất migration

- [ ] Có danh sách behaviors mà full-context tests cũ đang bảo vệ.
- [ ] Mỗi behavior có owner test ở đúng tầng.
- [ ] Unit tests không khởi tạo Spring context khi không cần thiết.
- [ ] Unit tests gọi production method và assert outcome/side effect thực, không chỉ verify mock setup.
- [ ] MVC slice kiểm tra route, JSON, validation, errors, status.
- [ ] @MockitoBean dùng chỉ cho collaborator ngoài MVC boundary.
- [ ] JPA slice dùng DB/query thật, có ít nhất một negative/boundary case khi thích hợp.
- [ ] Production DB-specific behavior có real-dialect test khi cần.
- [ ] Có full-context seam test cho các bean wirings quan trọng.
- [ ] Nếu có security, tests vẫn chạy đúng filter/authorization chain.
- [ ] Nếu có CSRF, có valid/missing/invalid token scenarios theo policy.
- [ ] Nếu có AOP/transaction/caching advice, có test qua Spring proxy thật.
- [ ] Nếu có external API/broker, có contract/integration tests phù hợp.
- [ ] Nếu test real HTTP, dùng RANDOM_PORT và HTTP client thực.
- [ ] Không mặc định @Transactional test rollback writes của server thread trong RANDOM_PORT.
- [ ] Không thay production beans/security config chỉ để làm slice start.
- [ ] Test fixtures độc lập, database cleanup/rollback đúng scope.
- [ ] TestContext cache keys/profile/inline props/mock customizers được xem xét.
- [ ] Không áp @DirtiesContext đại trà; có reset state phù hợp.
- [ ] CI chạy cả unit, MVC slice, JPA slice, seam và security suites cần thiết.
- [ ] Có assertions positive/negative cho critical requirements.
- [ ] Không dùng H2 green làm bằng chứng mọi dialect production.
- [ ] Có thống kê executed/passed/failed/skipped thực, không chỉ build green.
- [ ] Đã đo startup/cache hits/misses/cold/warm wall time trên cùng môi trường.
- [ ] Refactor giảm chi phí mà không giảm khả năng phát hiện regression.
- [ ] Imports và versions Java 17 / Spring Boot 3.5 / Spring Framework 6 nhất quán.
- [ ] Tests không tiết lộ credentials, production data hoặc customer PII.
- [ ] Tên tests phản ánh layer: Unit, WebMvc, DataJpa, SpringBoot seam.
- [ ] PR ghi rõ tests được thay thế, được giữ và vì sao evidence đủ.

## 23. Kết luận

**Thay full-context test bằng slice hoặc unit test là một quyết định về phạm vi bằng chứng, không đơn thuần là quyết định về hiệu năng.**

- Dùng **unit test** cho domain behavior và branching không cần Spring.
- Dùng **MVC slice** cho route, JSON, validation và HTTP contract của controller, với mock service khi phù hợp.
- Dùng **JPA slice** cho entity mapping và query thực trên một test database phù hợp.
- Giữ **full-context seam tests** khi cần chứng minh các Spring beans thực nối đúng giữa controller/service/repository và các policies hoạt động cùng nhau.
- Giữ **real HTTP/security/transaction/external integration tests** khi các boundaries ấy thuộc acceptance criteria.
- Quan sát **Spring TestContext cache**: nhiều tests có cùng key có thể reuse một context, còn unique slice configs có thể làm số startups tăng.
- Đo execution time, memory và test failures **cùng với** coverage/negative evidence.

Ví dụ Java 17+/Spring Boot 3.5 gồm 15 JUnit methods ở bốn tầng. Chúng chứng minh việc giảm scope có thể có **hệ thống và kiểm chứng được**: service rules được test không cần Spring, MVC/JPA được test trong contexts hẹp, còn một seam suite nhỏ vẫn bảo vệ wiring xuyên tầng. Bài viết không tuyên bố đã biên dịch/thực thi ví dụ trên một máy cụ thể; hãy chạy build/test report trước khi dùng kết quả làm bằng chứng cho dự án của bạn.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, MockMvc, server modes, transaction rollback scope.
- [Spring Boot 3.5 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): các auto-configurations mặc định theo từng slice.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): custom MVC config, Spring Security integration trong slice tests.
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache key, maxSize, LRU, DEBUG stats.
- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): mock bean overrides, cache key qualifiers.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): transactional test rollback rules.
- [Spring Boot 3.5 — DataJpaTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): JPA slice auto-config, embedded DB, rollback.
- [Spring Boot 3.5 — WebMvcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html): MVC slice filters, MockMvc and controller scans.
- [Spring Boot 3.5 — MockBean deprecation API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): @MockBean deprecated in favor of @MockitoBean.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): derived query generation and parsing.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter methods/annotations and test execution.
