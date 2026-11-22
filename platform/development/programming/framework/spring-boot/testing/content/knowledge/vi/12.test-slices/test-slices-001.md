# Test slice giới hạn những bean và auto-configuration nào trong Spring Boot?

Trong Spring Boot, **test slice** là một `ApplicationContext` được cấu hình để kiểm tra một **tầng kỹ thuật cụ thể** của ứng dụng: Spring MVC, WebFlux, JPA, JDBC, JSON serialization, REST client hoặc GraphQL. Dùng slice không đơn thuần là “khởi động ít bean hơn”. Mỗi annotation `@...Test` còn quyết định **những component nào được quét**, **nhóm auto-configuration nào được nhập** và **test helper nào được cung cấp**.

Ví dụ, `@WebMvcTest(OrderController.class)` có thể có controller, JSON converters, validation và `MockMvc`, nhưng **không tự nạp `@Service` và JPA repository thông thường**. Ngược lại, `@DataJpaTest` cấu hình entity/repository/JPA/datasource và transaction, nhưng **không tự nạp MVC controller và business service**. Do đó **slice test xanh chỉ chứng minh hành vi trong slice đã thử**, không chứng minh toàn bộ ứng dụng kết nối các tầng chính xác.

Các ví dụ trong bài dùng **Java 17+, Spring Boot 3.4.5, JUnit Jupiter và Gradle**. Các tên class auto-configuration và thành phần test có thể thay đổi theo phiên bản Spring Boot, vì vậy chỉ dùng bảng dưới đây cho nguyên lý và xem danh sách exact imports ở phần tham khảo khi cần kiểm chứng dự án thực.

## 1. Hai bộ lọc quyết định phạm vi của slice

Một Spring Boot slice kết hợp hai cơ chế:

1. **Component scan được thu hẹp bằng type-exclude filters.** Một web slice cho phép controller, advice, filter/converter và một số thành phần web được chỉ định, nhưng loại những `@Component` ứng dụng không thuộc phạm vi. JPA slice tập trung entity/repository. Điều này ảnh hưởng những **bean do component scan tạo**.
2. **Tập auto-configuration giới hạn theo mục đích.** MVC slice nhập MVC, HTTP converters, `MockMvc` và các cấu hình điều kiện liên quan; JPA slice nhập datasource, JPA provider, repositories, transaction, database test; JSON slice tập trung mapper/tester.

Ngoài hai cơ chế đó, `@Import`, `@TestConfiguration`, `@MockitoBean`, properties, profile và bean definitions khai báo tường minh **có thể bổ sung bean**. Vì vậy, không được nói “`@WebMvcTest` tuyệt đối không thể có service”: chính xác là **nó không tự quét business service thông thường**, nhưng test có thể chủ động import/mock service.

```text
                      ApplicationContext trong test
                               |
           +-------------------+-------------------+
           |                                       |
    Component scan filter                  Auto-configuration imports
           |                                       |
    MVC / JPA / JSON types                  Web / JPA / JDBC / JSON...
           |                                       |
           +-------------------+-------------------+
                               |
                      Test-specific additions
              @MockitoBean / @Import / properties
                               |
                       Assertions trong slice
```

**Auto-configuration là điều kiện, không phải cam kết tồn tại bean.** Một class có tên trong danh sách import vẫn phải thỏa `@ConditionalOnClass`, `@ConditionalOnBean`, property/profile hoặc các điều kiện khác. Ví dụ thiếu JDBC driver thì không thể suy ra một datasource hoạt động chỉ vì `DataSourceAutoConfiguration` xuất hiện.

## 2. Bảng tổng quan: những bean và auto-config tiêu biểu

Bảng dưới đây mô tả **Spring Boot 3.4.x**. Auto-config được liệt kê là các lớp **tiêu biểu**, không phải toàn bộ danh sách import.

| Slice | Bean và công cụ thường có | Auto-configuration tiêu biểu | Mặc định không kiểm chứng |
| --- | --- | --- | --- |
| **`@WebMvcTest`** | `@Controller`, `@ControllerAdvice`, web converters/filters, MVC infrastructure, `MockMvc` | `WebMvcAutoConfiguration`, `MockMvcAutoConfiguration`, `HttpMessageConvertersAutoConfiguration`, validation, security nếu có | Service nghiệp vụ, repository, transaction và database |
| **`@WebFluxTest`** | Reactive controller, WebFlux codecs, `WebTestClient` | `WebFluxAutoConfiguration`, `WebTestClientAutoConfiguration`, codec/validation | Business service/repository, real server/remote systems |
| **`@DataJpaTest`** | `@Entity`, JPA repository, `EntityManager`, datasource, transaction, `TestEntityManager` khi phù hợp | `HibernateJpaAutoConfiguration`, `JpaRepositoriesAutoConfiguration`, `DataSourceAutoConfiguration`, `TestDatabaseAutoConfiguration`, transaction config | Controller, business `@Service`, HTTP |
| **`@JdbcTest`** | `DataSource`, `JdbcTemplate`/`JdbcClient` theo classpath, transaction | `JdbcTemplateAutoConfiguration`, JDBC datasource/transaction/test database | JPA entity/repository, service, MVC |
| **`@DataJdbcTest`** | Spring Data JDBC aggregate/repository và JDBC infra | `JdbcRepositoriesAutoConfiguration`, nhóm JDBC/test database | Hibernate JPA repository, MVC/service thông thường |
| **`@JsonTest`** | JSON mapper và `JacksonTester`/tester cho thư viện hiện có | `JsonTestersAutoConfiguration` và mapper configuration phù hợp | Controller, HTTP route, service, repository |
| **`@RestClientTest`** | Outbound REST client được chọn, serializers, `MockRestServiceServer` | `RestClientAutoConfiguration`, `RestTemplateAutoConfiguration`, `MockRestServiceServerAutoConfiguration` | HTTP server, service/repository khác, đối tác thật |
| **`@GraphQlTest`** | GraphQL controllers/handlers và tester | `GraphQlAutoConfiguration`, `GraphQlTesterAutoConfiguration` | Toàn bộ hệ thống ngoài GraphQL boundary |
| **`@DataMongoTest`** | Mongo mapping/client/repository theo dependencies | Mongo auto-configuration, Mongo Data/repositories auto-config | Business service/MVC; không tự bảo đảm Mongo server chạy |

Các slice khác: `@DataR2dbcTest`, `@DataRedisTest`, `@DataCassandraTest`, `@JooqTest`, `@DataNeo4jTest` và những lớp tương đương. Chúng **không giống nhau về transaction, repository và hạ tầng**. Đặc biệt không lấy kỳ vọng H2/SQL của JPA áp cho MongoDB, Redis hoặc R2DBC.

**Nguồn chính xác:** bảng import auto-configuration đầy đủ cho Spring Boot 3.4 ở:

https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html

Khi cần biết một class như `FlywayAutoConfiguration` hay `SecurityAutoConfiguration` có nằm trong danh sách, tra đúng hàng của annotation tương ứng **và** xác minh điều kiện classpath/property, thay vì suy đoán từ tên slice.

## 3. `@WebMvcTest`: controller và Spring MVC, không tự load service

`@WebMvcTest(OrderController.class)` sẽ chọn controller đích và nạp những thành phần web được bộ lọc cho phép, thường gồm `@ControllerAdvice`, `Converter`, `GenericConverter`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer`, `WebMvcRegistrations`, `HandlerMethodArgumentResolver` và JSON components thích hợp.

Nó cũng cấu hình Spring MVC, converters/JSON, validation khi có dependency, error handling và `MockMvc`. **Không tự nạp** business `@Service`, Spring Data repository, datasource/JPA, hoặc các bean `@ConfigurationProperties` thông thường chỉ vì chúng tồn tại trong app.

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {
    @Autowired MockMvc mockMvc;

    @MockitoBean OrderQuoteService service;
}
```

Đây là trích đoạn; phần 8 có class runnable. `OrderController` cần `OrderQuoteService`, nhưng slice mặc định không scan service. `@MockitoBean` cung cấp **mock bean trong test context** để controller khởi tạo và có thể được stub. Nếu thiếu nó, ứng dụng có thể báo `NoSuchBeanDefinitionException` cho dependency; đó thường là **đúng bản chất của slice**, không phải lỗi Spring quét thiếu ngẫu nhiên.

### Bảo mật và validation trong web slice

Khi có Spring Security trên classpath, các security filter và auto-config liên quan có thể tham gia `@WebMvcTest`; POST có thể trả 401/403 do authentication hoặc CSRF trước khi đến controller. Dùng `spring-security-test`, `@WithMockUser`, `csrf()` và cấu hình phù hợp khi mục tiêu là kiểm tra filter/security.

Nếu dùng `@AutoConfigureMockMvc(addFilters=false)` để cô lập controller khỏi filters, phải ghi rõ test **không chứng minh filter/security**. Với `@Valid @RequestBody` và Bean Validation provider trên classpath, `@WebMvcTest` có thể kiểm tra request binding/validation/HTTP 400, nhưng không chứng minh nghiệp vụ hay persistence thật.

## 4. `@DataJpaTest`: JPA repository, EntityManager, transaction

`@DataJpaTest` mặc định quét `@Entity` và Spring Data JPA repositories, nạp JPA/Hibernate, datasource, transaction và test-database infrastructure. Nó **không tự scan** controller, business service và các `@Component` tùy ý.

Các auto-config tiêu biểu của Boot 3.4 gồm:

- `DataSourceAutoConfiguration` và test database `TestDatabaseAutoConfiguration`.
- `HibernateJpaAutoConfiguration` và `JpaRepositoriesAutoConfiguration`.
- `TransactionAutoConfiguration`, datasource/transaction manager.
- JDBC helper, SQL initialization, `TestEntityManagerAutoConfiguration`.
- Flyway/Liquibase khi điều kiện classpath/config phù hợp.

**Mặc định JPA slice transactional và rollback cuối test method.** Điều này giúp từng repository test ít làm bẩn DB. Nhưng nó không chứng minh production service có `@Transactional` đúng, cũng không chứng minh dữ liệu đã commit sau request thật.

Nếu H2/HSQL/Derby có trên classpath, slice thường dùng database nhúng để kiểm thử. Muốn dùng datasource container hoặc DB thật đã cấu hình, cân nhắc `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` cùng cấu hình kết nối/test container hoàn chỉnh. Không suy ra setting này tự khởi động DB.

**Phạm vi bằng chứng:** repository có thể save/find và mapping đúng **trong JPA test context**. Đối với SQL vendor-specific, locking hoặc isolation, test trên DB production engine vẫn cần thiết.

## 5. `@JdbcTest` không phải `@DataJdbcTest` hay `@DataJpaTest`

`@JdbcTest` phục vụ thao tác `JdbcTemplate`, `JdbcClient`, datasource/transaction và SQL adapter; nó **không tự đăng ký Spring Data JDBC/JPA repositories**.

`@DataJdbcTest` bổ sung Spring Data JDBC repository/mapping trên nền JDBC; `@DataJpaTest` bổ sung Hibernate/JPA repositories và `EntityManager`. Cả ba có datasource/transaction-related auto-config nhưng **khác technology và kiểu bean được quét**.

Trích đoạn test JDBC (cần import JUnit/JDBC, có embedded driver):

```java
@JdbcTest
class BasicSqlTest {
    @Autowired JdbcTemplate jdbc;

    @Test
    void executesSql() {
        assertEquals(1,
                jdbc.queryForObject("SELECT 1", Integer.class));
    }
}
```

Phép kiểm trên chỉ chứng minh test datasource/JDBC chạy một câu SQL đơn giản, không chứng minh JPA repository hay nghiệp vụ đặt hàng.

## 6. JSON, outbound HTTP, reactive web và những slice khác

**`@JsonTest`** cấu hình JSON mapper và helper như `JacksonTester<T>` để so sánh serialization/deserialization. Nó **không** tạo controller route, servlet filter hay service/repository. JSON contract xanh khác với HTTP status xanh.

**`@RestClientTest(RemoteCatalogClient.class)`** tập trung vào client ứng dụng **gọi ra ngoài**, serializers/client builder và `MockRestServiceServer`. Nó thích hợp kiểm tra URL, method, header/body và cách client xử lý response giả lập. Nó không mở server thật và không khẳng định đối tác thực trả dữ liệu đúng.

**`@WebFluxTest`** tập trung reactive controller, WebFlux codecs/configurers và `WebTestClient`, không tự nạp service/repository tùy ý. Nếu ứng dụng MVC, dùng `@WebMvcTest` cho MVC; đừng nhầm `WebTestClient` có mặt với việc app chắc chắn dùng reactive stack.

**`@GraphQlTest`** kiểm tra GraphQL handlers/mapping/tester, không tự bao phủ business service hoặc persistence. **`@DataMongoTest`** kiểm tra Mongo mapping/repositories nếu có client và server test thích hợp; không mặc định có một MongoDB nhúng theo cách H2 thường làm cho JDBC.

## 7. So sánh `@SpringBootTest` với slice

`@SpringBootTest` tạo Spring Boot `ApplicationContext` theo cấu hình ứng dụng, cho phép quét controller/service/repository và áp dụng các auto-configuration đủ điều kiện theo classpath/profile. Nó **không có nghĩa mọi possible auto-configuration đều sinh bean**; condition vẫn quyết định.

| Tiêu chí | Test slice | `@SpringBootTest` |
| --- | --- | --- |
| Phạm vi | Một tầng được lọc | Nhiều tầng ứng dụng |
| Component scan | Type-exclude filters theo slice | Scan app thông thường |
| Auto-config | Chỉ nhóm liên quan slice | Những auto-config của app thỏa điều kiện |
| Dependency khác tầng | Mock/`@Import` khi cần | Thường có nếu app wiring đầy đủ |
| Context | Thường nhỏ, có thể nhanh | Thường lớn hơn; tùy context cache |
| HTTP server thật | Không tự mở server | Chỉ khi chọn `RANDOM_PORT`/`DEFINED_PORT` |
| Kết luận | Chỉ lớp được thử, test double đã cấu hình | Có thể kiểm tra nhiều tầng nếu assertion đủ |

**`@SpringBootTest @AutoConfigureMockMvc` không phải MVC slice.** Nó cung cấp `MockMvc` cho full context. `@WebMvcTest` cũng có `MockMvc`, nhưng service/repository vẫn bị loại mặc định. Sự có mặt của cùng một test helper **không xác định** phạm vi context.

Không chồng hai annotation slice như `@WebMvcTest` và `@DataJpaTest` lên cùng một test class. Khi cần controller → service → repository, dùng `@SpringBootTest` và kiểm tra đúng contract tích hợp.

## 8. Dự án chạy được: một nghiệp vụ, bốn mức bằng chứng

Dự án Spring Boot 3.4.5 dùng Java 17+, Gradle, JUnit Jupiter, Spring MVC, Spring Data JPA, H2, Jackson và Bean Validation. Nghiệp vụ: `POST /api/orders` nhận `customer` và `subtotal`; nếu hợp lệ, service cộng phí 20, lưu đơn và trả JSON có `id` và `total`.

Cấu trúc:

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/slices/SlicesApplication.java
src/main/java/com/example/slices/OrderRecord.java
src/main/java/com/example/slices/OrderRepository.java
src/main/java/com/example/slices/OrderReceipt.java
src/main/java/com/example/slices/OrderQuoteService.java
src/main/java/com/example/slices/OrderController.java
src/test/java/com/example/slices/OrderMvcSliceTest.java
src/test/java/com/example/slices/OrderJpaSliceTest.java
src/test/java/com/example/slices/OrderJsonSliceTest.java
src/test/java/com/example/slices/OrderFullContextTest.java
```

### 8.1. Gradle và cấu hình database test

**`settings.gradle`**

```groovy
rootProject.name = 'spring-slice-scope'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
```

H2 có sẵn ở runtime/test classpath; `generate-unique-name` giảm nguy cơ các context test cùng dùng tên DB in-memory; JPA tạo schema ở context có Hibernate. Cấu hình `ddl-auto=create-drop` chỉ để học, **không dùng nguyên trạng cho production**.

### 8.2. Application, entity và repository

**`src/main/java/com/example/slices/SlicesApplication.java`**

```java
package com.example.slices;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SlicesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlicesApplication.class, args);
    }
}
```

**`src/main/java/com/example/slices/OrderRecord.java`**

```java
package com.example.slices;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class OrderRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String customer;
    private int total;

    protected OrderRecord() {
    }

    public OrderRecord(String customer, int total) {
        this.customer = customer;
        this.total = total;
    }

    public Long getId() { return id; }
    public String getCustomer() { return customer; }
    public int getTotal() { return total; }
}
```

**`src/main/java/com/example/slices/OrderRepository.java`**

```java
package com.example.slices;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderRecord, Long> {
}
```

Đây là JPA repository thật: Spring Data tạo bean khi JPA repository auto-config tham gia context (JPA slice hoặc full context), nhưng không phải MVC/JSON slice.

**`src/main/java/com/example/slices/OrderReceipt.java`**

```java
package com.example.slices;

public record OrderReceipt(Long id, int total) {
}
```

Record chỉ là kiểu dữ liệu Java, không phải Spring bean. `@JsonTest` serialize record không cần phải đưa record vào component scan.

### 8.3. Service và controller

**`src/main/java/com/example/slices/OrderQuoteService.java`**

```java
package com.example.slices;

import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {
    private final OrderRepository repository;

    public OrderQuoteService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderReceipt create(String customer, int subtotal) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException(
                    "customer must not be blank");
        }
        if (subtotal <= 0) {
            throw new IllegalArgumentException(
                    "subtotal must be positive");
        }

        int total = Math.addExact(subtotal, 20);
        OrderRecord saved =
                repository.save(new OrderRecord(customer, total));
        return new OrderReceipt(saved.getId(), saved.getTotal());
    }
}
```

**`src/main/java/com/example/slices/OrderController.java`**

```java
package com.example.slices;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderQuoteService service;

    public OrderController(OrderQuoteService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderReceipt create(@Valid @RequestBody CreateOrderRequest req) {
        return service.create(req.customer(), req.subtotal());
    }

    public record CreateOrderRequest(
            @NotBlank String customer,
            @Positive int subtotal) {
    }
}
```

MVC nhận JSON, Bean Validation áp dụng cho request body, controller gọi service. Khi dùng slice, các phần này không nhất thiết cùng tồn tại.

## 9. `@WebMvcTest` runnable: controller thật, service mock

**`src/test/java/com/example/slices/OrderMvcSliceTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderMvcSliceTest {
    @Autowired MockMvc mockMvc;
    @Autowired ApplicationContext context;

    @MockitoBean OrderQuoteService service;

    @Test
    void mapsValidRequestAndUsesMock() throws Exception {
        when(service.create("Lan", 100))
                .thenReturn(new OrderReceipt(9L, 120));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":"Lan","subtotal":100}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.total").value(120));

        verify(service).create("Lan", 100);
        assertTrue(mockingDetails(service).isMock());
        assertEquals(0,
                context.getBeanNamesForType(OrderRepository.class).length);
    }

    @Test
    void rejectsInvalidRequestBeforeService() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":" ","subtotal":0}
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

Kết quả mong đợi: HTTP 201, JSON và lời gọi mock đúng; request sai bị 400 trước khi gọi service. Nhưng mock **không save dữ liệu**: test này không có repository bean (`getBeanNamesForType(...).length == 0`). `@MockitoBean` có từ Spring Framework 6.2/Boot 3.4; với Boot 3.3 cũ thường dùng `@MockBean` tương ứng phiên bản.

## 10. `@DataJpaTest` runnable: entity/repository thật

**`src/test/java/com/example/slices/OrderJpaSliceTest.java`**

```java
package com.example.slices;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
class OrderJpaSliceTest {
    @Autowired OrderRepository repository;
    @Autowired ApplicationContext context;

    @PersistenceContext EntityManager entityManager;

    @Test
    void savesAndReloadsThroughJpa() {
        OrderRecord saved =
                repository.saveAndFlush(new OrderRecord("Lan", 120));
        assertNotNull(saved.getId());

        entityManager.clear();
        OrderRecord reloaded =
                repository.findById(saved.getId()).orElseThrow();

        assertEquals("Lan", reloaded.getCustomer());
        assertEquals(120, reloaded.getTotal());
        assertEquals(0,
                context.getBeanNamesForType(OrderQuoteService.class).length);
    }
}
```

`saveAndFlush` thực hiện SQL trong transaction test; `entityManager.clear()` giúp chứng minh truy xuất trở lại qua repository thay vì chỉ đọc lại entity đang được quản lý trong persistence context. Sau test, transaction mặc định rollback. Business service **không** thuộc JPA slice; test này chứng minh repository/mapping nhưng không chứng minh controller hoặc nghiệp vụ cộng phí 20.

## 11. `@JsonTest` runnable: DTO JSON không có MVC

**`src/test/java/com/example/slices/OrderJsonSliceTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;

@JsonTest
class OrderJsonSliceTest {
    @Autowired JacksonTester<OrderReceipt> json;
    @Autowired ApplicationContext context;

    @Test
    void roundTripsReceiptWithoutHttpServer() throws Exception {
        OrderReceipt receipt = new OrderReceipt(9L, 120);
        assertThat(json.write(receipt)).isEqualToJson("""
                {"id":9,"total":120}
                """);
        assertThat(json.parseObject("""
                {"id":9,"total":120}
                """)).isEqualTo(receipt);

        assertEquals(0,
                context.getBeanNamesForType(OrderController.class).length);
    }
}
```

Test chứng minh serialization/deserialization và không có controller bean trong JSON slice. Nếu chỉ cần bảo vệ `@JsonProperty`, enum/date format, field naming, không cần khởi động cả MVC/service/database.

## 12. `@SpringBootTest`: nối controller, service và repository

**`src/test/java/com/example/slices/OrderFullContextTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderFullContextTest {
    @Autowired MockMvc mockMvc;
    @Autowired OrderRepository repository;

    @Test
    void webServiceAndJpaWorkTogether() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":"Lan","subtotal":100}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.total").value(120));

        assertEquals(1L, repository.count());
        OrderRecord saved = repository.findAll().get(0);
        assertEquals("Lan", saved.getCustomer());
        assertEquals(120, saved.getTotal());
    }
}
```

Khác MVC slice, ở đây service và repository đều là bean thật trong full context; test quan sát request → service → DB. `@Transactional` trên test giúp rollback sau method, nhưng **không chứng minh commit trên một HTTP server thật chạy khác transaction**. `MockMvc` không mở TCP port; với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, server/client có thể chạy trên thread và transaction khác, cần cleanup phù hợp.

### Bảng bằng chứng rút ra từ các test

| Lớp test | Controller | Service | Repository | Điều đã kiểm tra |
| --- | --- | --- | --- | --- |
| `OrderMvcSliceTest` | Thật | Mock | Không có | HTTP status/body/validation/delegation |
| `OrderJpaSliceTest` | Không có | Không có | Thật (H2) | Entity mapping/save/reload |
| `OrderJsonSliceTest` | Không có | Không có | Không có | JSON mapping của DTO |
| `OrderFullContextTest` | Thật | Thật | Thật (H2) | Nhiều tầng cùng hoạt động trong test context |

Không thay thế các kết luận này bằng một con số duy nhất như “test xanh nghĩa toàn bộ ứng dụng đúng”.

## 13. Chạy các test và diễn giải lỗi

Với Gradle Wrapper tương thích và JDK 17:

```bash
./gradlew clean test
./gradlew test --tests com.example.slices.OrderMvcSliceTest
./gradlew test --tests com.example.slices.OrderJpaSliceTest
./gradlew test --tests com.example.slices.OrderJsonSliceTest
./gradlew test --tests com.example.slices.OrderFullContextTest
```

Windows dùng `gradlew.bat` thay `./gradlew`. Các test được **thiết kế để PASS** nếu dựng đúng các file và dependencies trên; đây là kỳ vọng suy từ code, **không phải log Gradle đã được thực thi**.

Nếu MVC slice báo thiếu service: kiểm tra mock/`@Import`. Nếu JPA slice thiếu datasource: kiểm tra H2/DB config. Nếu JSON slice thiếu `JacksonTester`: kiểm tra Jackson và `spring-boot-starter-test`. Nếu full context gặp 401/403 khi áp dụng cho dự án có security: kiểm tra auth/CSRF/filter; mẫu này không thêm security starter.

## 14. Cách mở rộng slice an toàn

**`@Import`** đưa thêm những bean/config cụ thể vào context. Dùng nó để bổ sung một converter, mapper hoặc test fake thật sự cần thiết; đừng import toàn bộ cấu hình ứng dụng làm slice rộng ra mà không nhận biết.

**`@EnableConfigurationProperties(MyProperties.class)`** có thể đưa một `@ConfigurationProperties` bean vào slice vì loại bean này không mặc định được scan như trong full context.

**`@MockitoBean`** (Framework 6.2) thêm/thay dependency mock trong test context; `@Mock` Mockito thuần trên field không tự đăng ký Spring bean. Với `@RestClientTest`, `@WebMvcTest` và service cần collaborator, đây là khác biệt quan trọng.

**`@ImportAutoConfiguration`** là cách thích hợp khi muốn nhập thêm **auto-configuration** vào slice. Không dùng `@Import` thông thường thay thế một cách tùy ý vì auto-config có cơ chế đăng ký/condition riêng. Nếu một slice phải nhập nhiều tầng auto-config, hãy cân nhắc chuyển sang `@SpringBootTest`.

**`excludeAutoConfiguration`**, khi annotation hỗ trợ, giúp loại auto-config không phù hợp; nhưng loại đi một cơ chế rồi test xanh **không chứng minh cơ chế bị loại hoạt động**. Chỉ dùng exclusion có chủ đích, không chỉ để làm biến mất lỗi context.

**Không chồng nhiều slice annotations** trong một test class; Boot không thiết kế `@WebMvcTest + @DataJpaTest` thành một context tổng hợp. Chọn một slice hoặc full context cho kịch bản cần nhiều tầng.

## 15. context cache, component scanning và hiệu năng

Spring TestContext cache `ApplicationContext` theo cấu hình hợp nhất; slice type, classes, active profile, properties, `@Import`, bean overrides/test customizers có thể làm cache key khác nhau. Vì vậy nhiều test nhỏ nhưng cấu hình rất khác vẫn có thể mất thời gian khởi động nhiều context. `@DirtiesContext` khiến Spring bỏ context khỏi cache khi cần, nhưng không nên dùng để che thiếu cleanup dữ liệu.

Một caveat quan trọng: nếu ứng dụng tùy biến `@ComponentScan` trực tiếp trên application class và vô tình bỏ type-exclude filters mà Boot cung cấp, những component đáng lẽ bị loại có thể lọt vào slice. Một `@Bean` explicit hoặc `@Import` rộng từ main configuration cũng có thể khiến slice có thêm bean ngoài dự tính. Vì vậy **đừng chỉ đọc annotation**, hãy hiểu primary configuration và bean graph thực sự.

Một test chỉ có `contextLoads()` cho biết context đã dựng, không tự bảo vệ output/contract. Test có giá trị nên assert HTTP response, JSON, repository state, interaction hoặc bean identity theo mục tiêu slice.

## 16. Bảng lỗi phổ biến

| Hiện tượng | Nguyên nhân điển hình | Cách giải quyết |
| --- | --- | --- |
| `@WebMvcTest` thiếu `@Service` | Service không được scan mặc định | Mock/fake hoặc dùng full context |
| `@DataJpaTest` thiếu business service | Data slice chỉ tập trung persistence | Test service bằng unit/`@SpringBootTest` |
| `@JsonTest` không có `MockMvc` | JSON mapper slice không phải MVC | Dùng `@WebMvcTest` |
| `@JdbcTest` thiếu JPA repository | JDBC không phải JPA | Chọn `@DataJpaTest` |
| MVC test trả 403 | Security/CSRF có hiệu lực | Cấu hình security test, không bỏ filter vô tội vạ |
| JPA test rollback mất dữ liệu | Hành vi mặc định | Không nhầm với service commit |
| JPA slice không kết nối PostgreSQL | Database replacement chọn embedded DB | Dùng real datasource + `Replace.NONE` |
| Service thật vẫn không được test | `@MockitoBean` thay logic thật | Thêm unit/full-context test riêng |
| Slice load bean không mong muốn | `@Import`, explicit config hoặc component scan tùy biến | Kiểm tra configuration và type-exclude filters |
| Context test chậm | Hibernate/DB/validation hoặc cache key phân mảnh | Chia test theo mục đích, giảm config variants |
| Kết hợp nhiều slice fail | Bootstrap/filters xung đột | Chọn một slice hoặc `@SpringBootTest` |
| `@SpringBootTest @AutoConfigureMockMvc` bị gọi là slice | Helper `MockMvc` không định nghĩa phạm vi | Kiểm tra annotation nạp context |

## 17. Tự kiểm tra

**A.** `@WebMvcTest(OrderController.class)` không tạo `OrderQuoteService`. Đây có phải Spring lỗi? **Không**, cần mock/import collaborator hoặc chọn full context.

**B.** `@DataJpaTest` chạy với H2 và mặc định rollback. Có chứng minh transaction commit của server production không? **Không**; transaction và database trong test khác bối cảnh cần kiểm tra.

**C.** `@JsonTest` xác nhận DTO `{"total":120}` nhưng HTTP API trả 500. Hai kết quả mâu thuẫn không? **Không**; mapping JSON đúng không bảo đảm route/service/DB đúng.

**D.** `@WebMvcTest` và `@SpringBootTest @AutoConfigureMockMvc` đều có `MockMvc`. Có thể nói chúng nạp cùng bean graph không? **Không**.

**E.** Cần test REST client gửi đúng header/URL tới đối tác giả lập. Nên dùng `@RestClientTest` với `MockRestServiceServer`, không dùng MVC slice cho outbound client.

**F.** Test đã thêm `@Import` đưa business service thật vào MVC slice. Nó còn là slice không? **Vẫn là slice đã được mở rộng**, không đồng nghĩa full context. Hãy ghi nhận giới hạn và các dependency đã chủ động import.

**G.** Vì sao `@WebMvcTest` có thể chứa security filter nhưng không chứa service? Vì bộ lọc và auto-config của web slice có chủ đích cho phép web/security infrastructure, trong khi service nghiệp vụ bị loại từ component scan thông thường.

**H.** Khi cần kiểm tra controller → service → repository trong một flow, dùng `@SpringBootTest` với assertions tích hợp; đừng chồng hai slice annotation.

### Checklist review test slice

- Slice đang kiểm tra **tầng nào**, và có chọn đúng annotation công nghệ không?
- Bean nào do slice scan? Bean nào bị loại? Dependency thiếu đã được stub/mock có chủ đích chưa?
- Auto-config nào được import theo appendix của **đúng Boot version**? Điều kiện classpath/profile đã thỏa chưa?
- Test đã assert behavior đúng thay vì chỉ context load?
- Có phân biệt dữ liệu/trạng thái từ mock với service/repository thật?
- Data slice đang dùng H2 hay database engine thật? Transaction có rollback mặc định không?
- Khi cần security/HTTP/transaction end-to-end, đã có test ở đúng boundary chưa?
- `@Import`, `@TestConfiguration` hoặc component scan tùy biến có mở rộng slice bất ngờ không?
- context cache có bị phân mảnh bởi profiles/properties/mock configuration không?
- Có lý do rõ ràng trước khi chọn full context thay vì một slice hẹp không?

**Kết luận:** Test slice quyết định cả **loại component được nạp** lẫn **auto-configuration thích hợp**, nên nó mạnh để thử chính xác một tầng nhưng không chứng minh các tầng bị loại. `@WebMvcTest` cho MVC, `@DataJpaTest` cho JPA, `@JdbcTest` cho JDBC, `@JsonTest` cho JSON, `@RestClientTest` cho outbound HTTP và `@WebFluxTest` cho reactive web. Khi muốn bằng chứng về wiring nhiều tầng, dùng `@SpringBootTest` với assertion integration thích hợp.

## Tài liệu chính thức

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Test Slices và danh sách auto-config imports: https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext Bean Overriding: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
