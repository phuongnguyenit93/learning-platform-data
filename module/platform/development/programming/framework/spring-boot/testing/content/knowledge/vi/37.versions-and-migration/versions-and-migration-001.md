# Đối chiếu Spring Boot, Spring Framework, JUnit, Mockito và Testcontainers

Trong nhóm **Phiên bản và chuyển đổi** của module **Spring Boot - testing**, một hệ thống có thể build xanh ở phiên bản cũ nhưng fail hàng loạt unit, MVC hoặc database integration tests sau khi nâng Spring Boot. Không phải luôn do business code: nguyên nhân có thể là **Spring Framework không đúng dòng**, **JUnit API/engine/launcher xung đột**, **Mockito mock bean annotation bị thay hoặc loại bỏ**, hay **Testcontainers module/package và Docker runtime không tương thích**.

Bài này giúp người học trả lời: dự án Spring Boot 2.7, 3.3, 3.5 hay 4.1 đang dùng stack kiểm thử nào; vai trò của dependency management/BOM; chọn unit, slice và integration tests đúng lớp; đọc dependency tree; và nâng cấp theo từng bước có khả năng rollback. Mẫu chính được xây trên **Java 17, Spring Boot 3.5.x, Spring Framework 6.2, JUnit Jupiter 5, Mockito 5, Testcontainers 1.x**. Phần migration đối chiếu **Spring Boot 4.1.x + Spring Framework 7 + JUnit 6 + Testcontainers 2.x**.

Tài liệu gồm mã nguồn đầy đủ cho domain, service, controller, Mockito tests, `@WebMvcTest` cùng `@MockitoBean`, một PostgreSQL integration test dùng `@ServiceConnection`, Gradle dependencies, và chương trình Java SE chạy `javac/java` với stdout được nêu chính xác. Các lệnh Gradle/JUnit/Docker được đưa ra để **người học tự chạy**, không phải khẳng định bộ tests đã được thực thi trong khi soạn bài.

**Quy tắc trung tâm:** không ghép ngẫu nhiên những thư viện “mới nhất” của năm dự án. **Chọn Spring Boot release/BOM đã được tổ chức phê duyệt**, đối chiếu Java/Gradle/Framework baseline, để BOM quản lý JUnit/Mockito/Testcontainers, rồi dùng dependency graph và regression tests để xác minh.

## 1. Mỗi thư viện đảm nhiệm việc gì?

```text
                  Spring Boot application
               + auto-configuration / starters
               + spring-boot-dependencies BOM
               + Spring Boot test slices
                           |
            +--------------+-------------+
            |                            |
            v                            v
      Spring Framework             Version alignment
      ApplicationContext           Gradle/Maven BOM
      WebMVC / TestContext                |
      SpringExtension                     |
      @MockitoBean                        |
            |                            |
            +-------------+--------------+
                          |
                          v
                   JUnit Platform
                discovery / execution
                          |
                          v
                     JUnit Jupiter
                 @Test / @BeforeEach
                          |
              +-----------+-------------+
              |                         |
              v                         v
           Mockito                 Testcontainers
      fake collaborator            real PostgreSQL,
      verify interactions          Kafka, Redis, etc.
              |                         |
              +-------------+-----------+
                            |
                   assertions / contracts
```

**Spring Framework**: IoC, MVC/WebFlux, `MockMvc`, Spring TestContext, `SpringExtension` và framework-level bean override. **Spring Boot**: auto-config, starters, `@SpringBootTest`, `@WebMvcTest`, managed dependencies, `@ServiceConnection` integration. **JUnit**: platform/engine, lifecycle, assertions, extensions. **Mockito**: mocks, spies, stubs và verification. **Testcontainers**: khởi động dependency thật trong Docker-compatible runtime. Testcontainers không thay Mockito; Mockito không chứng minh database dialect.

Một lỗi `NoSuchMethodError` thường khác với một assertion sai. Một lỗi Docker khác với một thiếu Spring bean. Trước khi thay code, **định vị lớp lỗi**.

## 2. Bảng tương thích theo các dòng phiên bản

| Boot line | Spring Framework line | Java baseline | JUnit | Mockito | Testcontainers | Chuyển đổi đáng chú ý |
| --- | --- | --- | --- | --- | --- | --- |
| Boot 2.7.x | Framework 5.3.x | Java 8+ | JUnit Jupiter 5 / legacy JUnit4 | Version theo BOM của patch | 1.x | Hệ Java EE `javax.*`, Boot test APIs cũ |
| Boot 3.2/3.3.x | Framework 6.1.x | Java 17+ | Jupiter 5 + Platform 1.x | Mockito 5 trên các patch hiện đại | 1.x | Jakarta `jakarta.*`; Boot 3.1+ có @ServiceConnection |
| Boot 3.4/3.5.x | Framework 6.2.x | Java 17+ | Jupiter 5 + Platform 1.x | Mockito 5 | 1.x | @MockitoBean từ Framework 6.2, @MockBean deprecated |
| Boot 4.0/4.1.x | Framework 7.0.x | Java 17+ | JUnit 6 / Platform 6 | Mockito 5 | 2.x | Modular starters, relocated packages, Boot @MockBean removed |

**Đây là ma trận dòng (major/minor), không phải BOM version lock chi tiết cho mọi release.** Ví dụ từ tài liệu chính thức: Boot 3.5.16 yêu cầu Java17 và Framework 6.2.19+; dependency coordinates của nó quản lý JUnit Jupiter 5.12.x, Mockito 5.x và Testcontainers 1.21.x. Boot 4.1.2 yêu cầu Java17, Framework 7.0.10+ và Gradle 8.14+ hoặc 9.x; BOM 4.1 quản lý JUnit6 và Testcontainers2. Những con số patch có thể thay khi nâng bản release; cần kiểm tra trang version coordinates **của đúng phiên bản đang chạy** thay vì sao chép từ bảng.

Spring Framework 5.3 thuộc thế hệ Java EE 8/`javax.*`; 6.x theo Jakarta EE9/10; 7.x có nền Jakarta EE11. Việc đổi namespace/Servlet/JPA/Validation APIs có thể ảnh hưởng source và tests độc lập với nâng JUnit.

## 3. JUnit 5 không chỉ là @Test, JUnit 6 không chỉ đổi số

JUnit hiện đại gồm:

- **JUnit Platform**: launcher và `TestEngine` infrastructure mà Gradle/Maven/IDE dùng.
- **JUnit Jupiter**: programming model `org.junit.jupiter.api.Test`, assertions, test lifecycle, parameterized tests, extension APIs.
- **JUnit Vintage**: chạy JUnit 3/4 tests khi chưa chuyển đổi; dùng như một cầu nối có kế hoạch, không phải hướng đi mặc định lâu dài.

Với JUnit 5, thường có `junit-jupiter-api:5.x`, `junit-jupiter-engine:5.x`, `junit-platform-launcher:1.x`. Với JUnit 6, các JUnit modules Jupiter/Platform/Vintage cùng ở dòng **6.x** và yêu cầu Java 17+ tại runtime. Java imports của Jupiter như `org.junit.jupiter.api.Test` và `Assertions.assertEquals` vẫn quen thuộc. Điều nguy hiểm là **override riêng API lên 6.x nhưng để engine 5.x hoặc Platform 1.x** ngoài hệ dependency management.

Bật Jupiter discovery trong Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

JUnit engine/launcher phải xuất hiện ở test runtime classpath. `spring-boot-starter-test` của Boot3.5 kéo JUnit/Jupiter infrastructure theo dependency BOM; có thể thêm `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` không ghi version để giữ Gradle launcher đồng bộ. Đối với Maven, cần Surefire/Failsafe hỗ trợ JUnit Platform và engine tương thích.

**Chuyển JUnit4 → Jupiter:**

| JUnit 4 | Jupiter |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before`, `@After` | `@BeforeEach`, `@AfterEach` |
| `@BeforeClass`, `@AfterClass` | `@BeforeAll`, `@AfterAll` |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` hoặc Boot integration annotation |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` |
| `@Ignore` | `@Disabled` |
| `ExpectedException` rule | `assertThrows(ExactException.class,...)` |
| `@Category` | `@Tag` |

**Không chuyển cơ học** những rule/runner extensions có behavior đặc biệt. Kiểm tra số lượng discovered tests trước/sau migration: một build xanh khi thực tế đã bỏ qua nửa số tests là một regression của CI.

## 4. BOM và dependency graph quan trọng hơn hardcode versions

Spring Boot quản lý các phiên bản transitive libraries qua `spring-boot-dependencies` BOM. Trong Maven có thể dùng `spring-boot-starter-parent` hoặc import BOM qua `dependencyManagement`; Gradle dùng Boot Gradle plugin với dependency-management phù hợp.

Một anti-pattern (không được dùng làm build):

```groovy
// Anti-pattern: versions bị trộn không đồng bộ
testImplementation 'org.junit.jupiter:junit-jupiter-api:6.0.0'
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.12.2'
testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
testImplementation 'org.mockito:mockito-core:4.11.0'
testImplementation 'org.testcontainers:postgresql:2.0.5'
```

Vấn đề: Jupiter6/5/Platform1 có thể binary incompatible; Mockito4 khác behavior mock maker/Java support; Testcontainers2 đã đổi tên `postgresql` artifact sang `testcontainers-postgresql`. Trộn chỉ vì “chọn mới nhất” có thể gây `ClassNotFoundException`, `NoSuchMethodError` hoặc test discovery failure.

**Cách thực hành:** khai báo dependencies do BOM quản lý **không có version**, in `testRuntimeClasspath`, xác nhận phiên bản thực được resolve. Chỉ override BOM nếu có lý do được review (ví dụ security fix khẩn cấp), có kiểm tra compatibility và rollback.

## 5. Spring Framework test API khác Spring Boot test slices

| Hợp đồng | Test phù hợp | Bảo đảm | Không bảo đảm |
| --- | --- | --- | --- |
| Pure Java logic | Jupiter, không Spring | Expected output/exceptions | MVC/DB |
| Service gọi collaborator | Mockito unit test | Stubbing/interaction | Bean proxies/context |
| Controller mapping | Boot `@WebMvcTest` + MockMvc | HTTP status/JSON/binding | Remote TCP, real DB |
| Repository SQL | `@DataJdbcTest`/`@DataJpaTest` | SQL behavior theo DB test | Entire full app |
| Auto-configuration | `ApplicationContextRunner` | Condition/bean presence | External service |
| Full application graph | `@SpringBootTest` | Integration of beans | Mọi production outage |
| PostgreSQL thật | Testcontainers | JDBC/dialect/constraints | Production network/HA |

Spring Framework TestContext tạo và cache `ApplicationContext` cho các classes có merged config tương thích. Spring Boot test slices giới hạn beans/auto-config để nhanh và đúng phạm vi. **Một MVC slice không auto-load tất cả @Service beans**, nên cần `@MockitoBean` để cung cấp service mock hoặc `@Import` một config/service thật.

Spring context cache không reset JVM static state hay Docker volumes. Nếu test mutate singleton cache/state rồi context được dùng lại, tests khác có thể bị ảnh hưởng. `@DirtiesContext` chỉ làm framework loại context khỏi cache theo lifecycle, không thay mọi công cụ isolation.

## 6. Phân biệt Mockito @Mock, @InjectMocks, @MockitoBean và @MockBean

| Cách dùng | Thư viện | Cần Spring? | Thực hiện |
| --- | --- | --- | --- |
| `@Mock` | Mockito | Không | Tạo mock object |
| `@InjectMocks` | Mockito | Không | Mockito tìm cách inject vào object dưới test |
| `@Spy` | Mockito | Không | Wrap real object bằng spy |
| `@ExtendWith(MockitoExtension.class)` | Mockito/Jupiter | Không | Khởi tạo mocks và lifecycle |
| `@MockitoBean` | Spring Framework 6.2/7 | Có | Override hoặc tạo bean mock trong test context |
| `@MockitoSpyBean` | Spring Framework 6.2/7 | Có | Wrap Spring bean bằng Mockito spy |
| `@MockBean`/`@SpyBean` | Spring Boot đời cũ | Có | Boot bean override, deprecated ở 3.4 và removed ở 4 |

Imports:

```java
// Mockito unit test
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

// Spring Framework bean override
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

// Deprecated Boot 3.x API: không dùng khi nâng lên Boot 4
import org.springframework.boot.test.mock.mockito.MockBean;
```

Đây chỉ là **import reference**, không phải Java class. `@Mock InvoiceService` trong một MVC test không khiến Spring controller nhận bean đó; `@MockitoBean InvoiceService` được Spring TestContext xử lý để tạo/override bean.

Một số semantics `@MockitoBean` không giống Boot `@MockBean` 100%: Spring Framework dùng `REPLACE_OR_CREATE` theo mặc định; `enforceOverride=true` yêu cầu bean phải tồn tại; chọn theo qualifier/name và field name fallback; non-singleton bean override có thể thành singleton mock. **Đừng dùng enforceOverride=true một cách máy móc** trong MVC slice khi service thật vốn không nằm trong slice: lúc ấy cần *tạo* mock bean.

Nếu mock thay một bean AOP/proxied, test mock không chứng minh `@Transactional`/`@Cacheable`/`@Retryable` của bean gốc chạy. Những behavior đó cần integration tests trên real bean.

## 7. Project Java 17 đầy đủ để đối chiếu

```text
compatibility-lab/
├── build.gradle
└── src/
    ├── main/java/example/compat/
    │   ├── CompatApplication.java
    │   ├── PricePolicy.java
    │   ├── TaxGateway.java
    │   ├── ZeroTaxGateway.java
    │   ├── InvoiceService.java
    │   ├── InvoiceController.java
    │   ├── InvoiceErrorAdvice.java
    │   └── CompatDemo.java
    └── test/java/example/compat/
        ├── PricePolicyTest.java
        ├── InvoiceServiceTest.java
        ├── InvoiceControllerTest.java
        └── PostgreSqlContainerTest.java
```

Bộ example có **14 JUnit test methods**: 5 pure Java tests, 4 Mockito service tests, 3 MockMvc tests và 2 PostgreSQL Testcontainers integration tests. Java SE demo chạy độc lập; integration suite cần Docker-compatible runtime.

**Lựa chọn ranh giới:** PricePolicy có logic tính subtotal/validation và không biết Spring. InvoiceService nhận TaxGateway qua constructor để Mockito mock đúng collaborator. Spring MVC controller nhận InvoiceService (mock trong test slice). PostgreSQL integration test không dùng H2, nó query PostgreSQL thật để kiểm tra JDBC + service connection.

## 8. build.gradle — stack Boot 3.5.x theo BOM

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vai trò dependency:**

- `spring-boot-starter-web` cho MVC application và testing slice ecosystem.
- `spring-boot-starter-jdbc` cho DataSource và `JdbcTemplate`.
- `spring-boot-starter-test` chứa Boot testing infrastructure, JUnit Jupiter, Mockito/Jupiter, AssertJ theo BOM.
- `spring-boot-testcontainers` cung cấp `@ServiceConnection` Boot integration.
- `org.testcontainers:junit-jupiter` đưa `@Testcontainers`/`@Container` của Testcontainers 1.x.
- `org.testcontainers:postgresql` cung cấp PostgreSQLContainer của Testcontainers 1.x.
- `org.postgresql:postgresql` là JDBC driver; đây là thư viện **khác** Testcontainers module.
- `junit-platform-launcher` ở runtime giúp runner/IDE khớp JUnit engine theo BOM.

Tất cả libraries ở block dependencies **không ghi version riêng**; Boot BOM chọn versions đồng bộ. Build plugin version là cấu hình tooling riêng, không phải JUnit dependency.

**Runtime note:** Vì project có JDBC starter, khi chạy full application ngoài test, Spring cần cấu hình datasource thực. Trong Testcontainers integration test, `@ServiceConnection` cấp details từ PostgreSQL container. Unit và MVC slice tests **không** cần Docker/database. File `build.gradle` không tự tạo Gradle wrapper; tạo wrapper phù hợp Spring Boot system requirements trước khi dùng `./gradlew`.

## 9. Maven: parent hoặc BOM thay vì version từng dependency

Một **đoạn POM minh họa**, không phải file pom.xml độc lập:

```xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.5.16</version>
  <relativePath/>
</parent>

<properties>
  <java.version>17</java.version>
</properties>

<dependencies>
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
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Project đầy đủ còn cần Maven coordinates, Web/JDBC dependencies và plugin settings. Nếu không dùng Spring Boot parent, import `spring-boot-dependencies` BOM trong `dependencyManagement` và cấu hình Maven Surefire/Failsafe để chạy JUnit Platform. BOM quản lý libraries, **không tự bảo đảm Maven test plugin đủ mới**.

## 10. PricePolicy.java: pure Java domain

Tạo `src/main/java/example/compat/PricePolicy.java`:

```java
package example.compat;

public final class PricePolicy {

    public int subtotalCents(
            int unitCents, int quantity) {

        if (unitCents < 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                    "unitCents must be >= 0 and quantity > 0");
        }

        return Math.multiplyExact(unitCents, quantity);
    }
}
```

Business contract: đơn giá không âm, số lượng dương, kết quả đúng tích số cent. `Math.multiplyExact` ném `ArithmeticException` nếu tràn `int`. Trong ứng dụng tiền thật cần thêm currency/rounding/bounds; đây là bài học về testing compatibility, không phải một pricing engine production.

Class Java thuần nên unit tests không phụ thuộc Spring context hay Docker. Việc giữ unit tests này khi nâng Boot giúp phân biệt bug business với lỗi framework/testing infrastructure.

## 11. TaxGateway.java và ZeroTaxGateway.java

Tạo `src/main/java/example/compat/TaxGateway.java`:

```java
package example.compat;

public interface TaxGateway {
    int taxCents(int subtotalCents);
}
```

Tạo `src/main/java/example/compat/ZeroTaxGateway.java`:

```java
package example.compat;

import org.springframework.stereotype.Component;

@Component
public final class ZeroTaxGateway implements TaxGateway {

    @Override
    public int taxCents(int subtotalCents) {
        return 0;
    }
}
```

`ZeroTaxGateway` chỉ là **demo bean** giúp full Spring context có collaborator không gọi hệ thống ngoài. Nó không đại diện chính sách thuế thực. Trong Mockito unit test sẽ không dùng bean này: ta mock interface TaxGateway để kiểm tra service thật.

**Ranh giới mock:** thay external port/collaborator, không mock chính service đang cần kiểm chứng. Việc mock SUT cho test kết quả thường chỉ kiểm tra “Mockito trả đúng dữ liệu mình đã stub”, không kiểm tra nghiệp vụ.

## 12. InvoiceService.java — constructor injection rõ ràng

Tạo `src/main/java/example/compat/InvoiceService.java`:

```java
package example.compat;

import org.springframework.stereotype.Service;

@Service
public final class InvoiceService {

    private final PricePolicy pricePolicy;
    private final TaxGateway taxGateway;

    public InvoiceService(
            PricePolicy pricePolicy, TaxGateway taxGateway) {
        this.pricePolicy = pricePolicy;
        this.taxGateway = taxGateway;
    }

    public int totalCents(int unitCents, int quantity) {
        int subtotal =
                pricePolicy.subtotalCents(unitCents, quantity);

        int tax = taxGateway.taxCents(subtotal);

        return Math.addExact(subtotal, tax);
    }
}
```

Những assertion cần có: service gọi đúng subtotal, không gọi gateway khi input invalid, không nuốt gateway failure và không làm tràn tổng. Unit test tạo service bằng constructor với real PricePolicy + mock TaxGateway. Không cần Spring context.

Mockito5 hỗ trợ mock nhiều class final theo inline mock-maker khi cấu hình phù hợp. Tuy nhiên, **ưu tiên mock interface external port** để giảm phụ thuộc JVM instrumentation. Java agent/Byte Buddy warnings trên JDK mới cần xử lý theo Mockito/JDK documentation, không tắt tùy tiện security flags.

## 13. InvoiceController.java — HTTP boundary

Tạo `src/main/java/example/compat/InvoiceController.java`:

```java
package example.compat;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {

    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/invoices/total")
    public Map<String, Integer> total(
            @RequestParam int unitCents,
            @RequestParam int quantity) {

        return Map.of(
                "totalCents",
                service.totalCents(unitCents, quantity));
    }
}
```

Tạo `src/main/java/example/compat/InvoiceErrorAdvice.java`:

```java
package example.compat;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InvoiceErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidInvoice() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid invoice inputs"));
    }
}
```

GET `/invoices/total?unitCents=250&quantity=2` trả JSON `{"totalCents":500}` khi tax là 0. Invalid business input nhận HTTP 400 với error JSON; thiếu required param cũng nhận 400 từ Spring MVC binding. Unit test service **không chứng minh** controller mapping; MVC slice test dành cho contract này.

## 14. CompatApplication.java — một Spring Boot main class

Tạo `src/main/java/example/compat/CompatApplication.java`:

```java
package example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatApplication {

    @Bean
    PricePolicy pricePolicy() {
        return new PricePolicy();
    }

    public static void main(String[] args) {
        SpringApplication.run(
                CompatApplication.class, args);
    }
}
```

Package `example.compat` là gốc component scanning. Full context tìm `ZeroTaxGateway`, `InvoiceService`, `InvoiceController` và `InvoiceErrorAdvice`. MVC slice không tự quét @Service, vì thế sẽ mock service trong test. Không thêm nhiều @SpringBootApplication tùy tiện trong cùng root test khiến framework không biết chọn config nào.

## 15. PricePolicyTest.java: năm JUnit Jupiter unit tests

Tạo `src/test/java/example/compat/PricePolicyTest.java`:

```java
package example.compat;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PricePolicyTest {

    private final PricePolicy policy = new PricePolicy();

    @Test
    void multipliesUnitPriceAndQuantity() {
        assertEquals(750, policy.subtotalCents(250, 3));
    }

    @Test
    void zeroUnitPriceIsAllowed() {
        assertEquals(0, policy.subtotalCents(0, 1));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.subtotalCents(-1, 2));

        assertEquals(
                "unitCents must be >= 0 and quantity > 0",
                error.getMessage());
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.subtotalCents(100, 0));
    }

    @Test
    void rejectsIntegerOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> policy.subtotalCents(
                        Integer.MAX_VALUE, 2));
    }
}
```

**5 JUnit methods**, JDK/Jupiter only, không Spring/Docker. Test đúng kết quả, biên 0, validation và overflow. `org.junit.jupiter.api.Test` được dùng trong cả Jupiter5 và Jupiter6; khi migrate, các assertions là regression baseline.

## 16. InvoiceServiceTest.java: MockitoExtension với bốn test methods

Tạo `src/test/java/example/compat/InvoiceServiceTest.java`:

```java
package example.compat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    TaxGateway taxGateway;

    private InvoiceService service;

    @BeforeEach
    void setup() {
        service = new InvoiceService(
                new PricePolicy(), taxGateway);
    }

    @Test
    void calculatesTotalWithMockGateway() {
        when(taxGateway.taxCents(600)).thenReturn(60);

        assertEquals(660, service.totalCents(200, 3));
        verify(taxGateway).taxCents(600);
    }

    @Test
    void rejectsBadInputBeforeCallingGateway() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalCents(-1, 2));

        verifyNoInteractions(taxGateway);
    }

    @Test
    void doesNotHideGatewayFailure() {
        when(taxGateway.taxCents(500))
                .thenThrow(new IllegalStateException("offline"));

        assertThrows(
                IllegalStateException.class,
                () -> service.totalCents(250, 2));

        verify(taxGateway).taxCents(500);
    }

    @Test
    void detectsTaxAdditionOverflow() {
        when(taxGateway.taxCents(Integer.MAX_VALUE))
                .thenReturn(1);

        assertThrows(
                ArithmeticException.class,
                () -> service.totalCents(
                        Integer.MAX_VALUE, 1));

        verify(taxGateway).taxCents(Integer.MAX_VALUE);
    }
}
```

**4 JUnit methods**: real SUT, mocked external port. `@Mock` không tạo Spring bean; `MockitoExtension` khởi tạo mock cho Jupiter test và quản lý strict stubbing. Test có `verify`, không chỉ stub trả số. Nếu gặp `UnnecessaryStubbingException` sau migration, xem stub thừa hoặc input không khớp; không tắt strictness toàn suite để che bug.

`@InjectMocks` là một tính năng Mockito để thử inject mocks, **không phải Spring @Autowired**. Ở đây constructor injection thủ công minh bạch hơn.

## 17. InvoiceControllerTest.java: @MockitoBean trong MVC slice

Tạo `src/test/java/example/compat/InvoiceControllerTest.java` cho **Boot 3.5**:

```java
package example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    InvoiceService service;

    @Test
    void producesExpectedJson() throws Exception {
        when(service.totalCents(250, 2)).thenReturn(500);

        mvc.perform(get("/invoices/total")
                        .param("unitCents", "250")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void mapsValidationFailureTo400() throws Exception {
        when(service.totalCents(-1, 2))
                .thenThrow(new IllegalArgumentException(
                        "bad invoice"));

        mvc.perform(get("/invoices/total")
                        .param("unitCents", "-1")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid invoice inputs"));
    }

    @Test
    void missingQuantityFailsBeforeService() throws Exception {
        mvc.perform(get("/invoices/total")
                        .param("unitCents", "250"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

**3 JUnit methods** kiểm tra query binding, 200 + JSON, validation exception mapping qua `InvoiceErrorAdvice` và missing-param 400. `@WebMvcTest` là slice, không mở external network hoặc database. `@MockitoBean` đưa service mock vào Spring TestContext để controller autowire.

**Không dùng `@Mock` thay `@MockitoBean` trong MVC slice**: field Mockito thường không phải một bean trong ApplicationContext. Ngược lại, pure Mockito unit test nên dùng `@Mock`/MockitoExtension, không khởi động Spring context chỉ để tạo một collaborator mock.

**Boot 4 migration import:** Boot3.5 `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` → Boot4 `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`. `@MockitoBean` vẫn thuộc `org.springframework.test.context.bean.override.mockito`. Boot4 không còn Spring Boot `@MockBean` cũ.

## 18. PostgreSqlContainerTest.java: Testcontainers 1.x thực

Tạo `src/test/java/example/compat/PostgreSqlContainerTest.java` cho **Boot 3.5 / Testcontainers 1.x**:

```java
package example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class PostgreSqlContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("compatibility");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void selectsRealPostgresDatabaseName() {
        String database = jdbc.queryForObject(
                "select current_database()", String.class);

        assertEquals("compatibility", database);
    }

    @Test
    void executesPostgresUuidCast() {
        String uuid = jdbc.queryForObject(
                "select '00000000-0000-0000-0000-000000000001'::uuid::text",
                String.class);

        assertEquals(
                "00000000-0000-0000-0000-000000000001",
                uuid);
    }
}
```

**2 JUnit integration methods**, **cần Docker-compatible runtime**:

- `@Testcontainers` là JUnit Jupiter extension.
- `@Container` quản lý một static PostgreSQLContainer.
- `@ServiceConnection` cung cấp Spring Boot `JdbcConnectionDetails` để datasource tự nối vào container, không hardcode host, port hoặc password.
- `JdbcTemplate` gửi SQL tới **PostgreSQL thật**, thử `current_database()` và PostgreSQL UUID cast.
- `org.postgresql:postgresql` JDBC driver vẫn cần tại runtime. Testcontainers PostgreSQL module không phải JDBC driver.

**Không dùng H2 rồi nói đã test PostgreSQL dialect.** H2 có SQL/types/transactions khác; với migration DB cần PostgreSQL hoặc test environment tương đương. Khi Docker chưa sẵn, báo test blocked/failed hoặc skip một cách **tường minh** theo chính sách, không coi test chưa chạy là PASS.

Ở Boot4/Testcontainers2, PostgreSQLContainer đổi package và artifact; code trên nhắm Boot3.5 nên **không** kết hợp với imports TC2.

## 19. Java SE demo với javac/java và stdout chính xác

Tạo `src/main/java/example/compat/CompatDemo.java`:

```java
package example.compat;

public class CompatDemo {

    public static void main(String[] args) {
        PricePolicy policy = new PricePolicy();

        System.out.println(
                "subtotal=" + policy.subtotalCents(250, 3));
        System.out.println(
                "zero=" + policy.subtotalCents(0, 1));

        try {
            policy.subtotalCents(-1, 2);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid=" + error.getMessage());
        }
    }
}
```

Từ project root với JDK 17+:

```bash
javac -d out src/main/java/example/compat/PricePolicy.java src/main/java/example/compat/CompatDemo.java
java -cp out example.compat.CompatDemo
```

Stdout **chính xác**:

```text
subtotal=750
zero=0
invalid=unitCents must be >= 0 and quantity > 0
```

Demo này chỉ chạy PricePolicy Java SE, không xác nhận Spring Context/JUnit/Mockito/Testcontainers integration. Để chứng minh stack tương thích phải chạy Gradle tests và DB container ở đúng CI runner.

## 20. Ma trận tests và các lệnh chạy

| Class | Methods | Phụ thuộc | Hợp đồng |
| --- | ---: | --- | --- |
| PricePolicyTest | 5 | Java/Jupiter | Validation, exact math, overflow |
| InvoiceServiceTest | 4 | Jupiter/Mockito | Interaction, propagating failures |
| InvoiceControllerTest | 3 | Spring Framework TestContext/Boot MVC slice | Bean override/HTTP JSON |
| PostgreSqlContainerTest | 2 | Spring full context/Testcontainers/Docker | JDBC real PostgreSQL |
| **Tổng** | **14** | | |

Chạy unit/MVC không cần Docker:

```bash
./gradlew test --tests example.compat.PricePolicyTest
./gradlew test --tests example.compat.InvoiceServiceTest
./gradlew test --tests example.compat.InvoiceControllerTest
```

Chạy database integration khi Docker sẵn:

```bash
./gradlew test --tests example.compat.PostgreSqlContainerTest
```

Chạy toàn bộ:

```bash
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.compat.PricePolicyTest"
.\gradlew.bat test --tests "example.compat.InvoiceServiceTest"
.\gradlew.bat test --tests "example.compat.InvoiceControllerTest"
.\gradlew.bat test --tests "example.compat.PostgreSqlContainerTest"
```

**14 là số @Test methods trong mã nguồn, không phải kết quả thực thi đã được thu thập.** Gradle console output, test reports và Docker startup time thay đổi theo môi trường. CI phải kiểm tra discovered/executed/skipped/failed counts riêng và xác nhận container test không bị bỏ qua.

## 21. Boot 4.1.x: thay đổi dependency/test starter

Spring Boot 4 chuyển sang các starters theo từng technology. Một **migration snippet Gradle**, không phải project Boot4 độc lập đã được thử nghiệm:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Đổi về bản chất:**

- Boot3 `spring-boot-starter-web` → Boot4 định hướng `spring-boot-starter-webmvc`.
- Boot4 có `spring-boot-starter-webmvc-test`, `spring-boot-starter-jdbc-test` và các technology test starters khác. `spring-boot-starter-test` vẫn có core test support nhưng không mặc nhiên thay mọi technology-specific support.
- Testcontainers2 artifacts đổi thành `testcontainers-junit-jupiter` và `testcontainers-postgresql`.
- JUnit6 và Spring Framework7 được Boot4 BOM quản lý.
- Boot4.1 Gradle yêu cầu **8.14+ hoặc 9.x** theo system requirements; Boot3.5 wrapper cũ có thể không còn hợp lệ.
- Một số Spring Boot annotation packages được di chuyển theo module mới.

Đây là delta cho MVC/JDBC project. Nếu app dùng Spring Security, GraphQL, JPA, Kafka, WebFlux, cần đọc bảng technology starters riêng; đừng giả định chỉ thay ba dòng Gradle là đủ migration production.

## 22. @WebMvcTest, MockMvc và Mockito trong Boot 4

Boot3.5 import:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

Boot4 import:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Spring Framework 6.2+/7 mock bean import **không đổi**:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Boot4 bỏ các Boot annotations `@MockBean`/`@SpyBean` theo package `org.springframework.boot.test.mock.mockito`. Thay bằng Spring `@MockitoBean`/`@MockitoSpyBean` và kiểm tra bean override behavior, qualifiers/scope.

**Đối với full `@SpringBootTest` trong Boot4**, nếu muốn dùng MockMvc, cần thêm `@AutoConfigureMockMvc` và module/test starter tương ứng, vì full context test không mặc nhiên cung cấp MockMvc support chỉ bằng `@SpringBootTest`. Đối với `TestRestTemplate`, Boot4 tổ chức lại test clients và auto-config annotations; phải kiểm tra package/import/dependency theo migration guide, không giả định full context tự cung cấp như một ví dụ cũ.

Một Boot4 test có `@WebMvcTest` không nhất thiết cần `@SpringBootTest`; đó là hai kiểu test khác nhau. Đừng thêm cả hai một cách máy móc khi sửa import.

## 23. Testcontainers 1.x sang 2.x: hai cặp thay đổi bắt buộc

| Vai trò | Testcontainers 1.x / Boot3.5 | Testcontainers 2.x / Boot4 |
| --- | --- | --- |
| Postgres dependency | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| JUnit extension dependency | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| Postgres class | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| JUnit `@Testcontainers` | `org.testcontainers.junit.jupiter.Testcontainers` | Vẫn package này |
| JUnit `@Container` | `org.testcontainers.junit.jupiter.Container` | Vẫn package này |
| Boot `@ServiceConnection` | `org.springframework.boot.testcontainers.service.connection.ServiceConnection` | Vẫn package này |

**Không dùng** `org.testcontainers:postgresql:2.0.x` rồi mong cùng artifact id với 1.x. **Không import** `org.testcontainers.postgresql.PostgreSQLContainer` khi dependency vẫn là Testcontainers1.21.x. Đảm bảo mọi module core/JUnit/Postgres thuộc một dòng đồng bộ, thông thường để Boot BOM quản lý.

Service Connection cung cấp **ConnectionDetails** phù hợp khi Boot nhận diện container; nó có thể ưu tiên hơn `spring.datasource.url` thông thường. `@ServiceConnection` không tự thay đổi behavior của Docker daemon và không thay `@Container`/lifecycle manager. Nếu dùng `GenericContainer` cho service đặc thù, kiểm tra image-name matching và có thể cần `@ServiceConnection(name = "...")` hoặc `@DynamicPropertySource`.

## 24. Boot 2.7 → 3: Java 17 và javax/jakarta

Nâng từ Boot2 sang Boot3 không chỉ sửa JUnit version:

- Java baseline chuyển từ 8+ lên 17+.
- Spring Framework5.3 → 6.x.
- Các Jakarta EE packages như `javax.servlet.*`, `javax.persistence.*`, `javax.validation.*` đổi sang `jakarta.servlet.*`, `jakarta.persistence.*`, `jakarta.validation.*` khi thuộc Jakarta counterparts.
- Không tự đổi **mọi** `javax.*`; một số API Java SE vẫn giữ nguyên tên.
- MVC/Servlet, Bean Validation, JPA, Security và embedded server versions có migration riêng.
- Các JUnit4 `@RunWith` tests có thể cần Jupiter `@ExtendWith` hoặc Vintage engine tạm thời.
- Nếu dùng Boot3.1+ có thể dùng `@ServiceConnection` thay dynamic datasource property wiring trong những Testcontainers use cases được hỗ trợ.

**Chiến lược giảm rủi ro:** nâng JDK/tooling và cleanup deprecations trước, migrate javax/Jakarta/API, chạy unit tests, rồi web/repository/full integration tests. Không trộn tất cả thay đổi cùng lúc mà không có baseline.

## 25. Boot 3.3 → 3.4/3.5: @MockBean deprecated

Spring Boot3.4 đánh dấu Boot `@MockBean`/`@SpyBean` **deprecated for removal**, chuyển sang Spring Framework6.2 `@MockitoBean`/`@MockitoSpyBean`.

Không phải đổi tên là xong. Kiểm tra:

- Bean có tồn tại trong context/slice không?
- Qualifier/field name có chọn đúng bean khi nhiều candidates?
- Mặc định REPLACE_OR_CREATE có phù hợp? Có cần enforceOverride?
- Mock/spy ảnh hưởng AOP proxy, transaction hoặc cache annotations ra sao?
- Context cache key có bị phân mảnh do mock configuration khác nhau?
- Mock state được reset giữa tests theo framework/version không?
- Spy stubbing có gọi real method gây side effect nếu dùng `when(spy.method())` không? Khi cần, dùng `doReturn(...).when(spy)...`.

**Tránh nhầm:** Mockito `@Mock` vẫn thuộc Mockito, không bị thay bằng `@MockitoBean` trong unit tests không có Spring.

## 26. @DynamicPropertySource khác @ServiceConnection

Hai giải pháp phục vụ những trường hợp khác nhau:

**@ServiceConnection**: Boot biết container type/image và tạo `JdbcConnectionDetails`, `RedisConnectionDetails` hoặc type phù hợp. PostgreSQLContainer trong demo hỗ trợ JDBC details, tránh hardcode mapped port/password.

**@DynamicPropertySource**: cho một arbitrary dynamic property của app, chẳng hạn URL service giả lập khi không có built-in ConnectionDetails factory:

```java
@DynamicPropertySource
static void addEndpoint(DynamicPropertyRegistry registry) {
    registry.add(
            "catalog.client.base-url",
            () -> "http://" + catalogContainer.getHost()
                    + ":" + catalogContainer.getMappedPort(8080));
}
```

Đây là **snippet**, cần các imports/Testcontainers setup và static container `catalogContainer` đã được khởi động; không phải một runnable file. `@DynamicPropertySource` chỉ đưa giá trị vào Spring Environment, không tự khởi động Docker hoặc sửa JVM system property toàn cục.

Không khai báo đồng thời `@ServiceConnection` và một `spring.datasource.url` test override rồi mặc định datasource dùng URL mình tưởng; kiểm tra thứ tự precedence và `ConnectionDetails` thực.

## 27. Dependency graph và diagnostics

**Gradle:**

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew test --tests example.compat.PricePolicyTest
```

**Windows PowerShell:**

```powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
```

**Maven:**

```bash
./mvnw dependency:tree -Dscope=test
./mvnw test
```

**Tại sao nhìn testRuntimeClasspath?** API có thể compile nhưng runtime lại nạp phiên bản engine, spring-test, mockito-core hoặc Testcontainers khác. `NoSuchMethodError` thường chỉ xuất hiện khi JVM load class/method. In selected version và nguồn kéo dependency vào graph, không chỉ đọc version khai báo ở build.gradle.

Check đặc biệt:

1. Boot BOM có đang active không?
2. `spring-test` cùng Framework train với Spring Boot?
3. JUnit Jupiter API/Engine/Platform Launcher khớp JUnit5/6 line?
4. Mockito core, junit-jupiter extension và Byte Buddy hỗ trợ JDK?
5. Testcontainers module names 1.x vs 2.x hợp lệ?
6. PostgreSQL JDBC driver có mặt khi tạo DataSource?
7. Gradle/Maven runner có thực sự discover Jupiter tests?
8. CI có Docker container runtime sẵn cho DB tests?

## 28. CI matrix và phạm vi chứng minh

| Job | Cần Docker? | Bằng chứng |
| --- | --- | --- |
| Compile Java + test compile | Không | Imports/APIs/classpath compile |
| PricePolicyTest | Không | Java domain behavior |
| InvoiceServiceTest | Không | Mockito Jupiter interaction/exception |
| InvoiceControllerTest | Không | Spring MVC slice và @MockitoBean |
| PostgreSqlContainerTest | **Có** | Spring Boot @ServiceConnection + PostgreSQL real JDBC |
| Boot4 migration branch | Tùy suite | New starters/packages, JUnit6, Testcontainers2 |
| Supported JDK matrix | Tùy suite | Compatibility với JDK/Byte Buddy/Gradle versions |

Một CI có Docker unavailable **không được báo PostgreSQL integration PASS** nếu tests bị skip. Nếu DB contract là quality gate, provision runtime có quyền phù hợp và fail pipeline khi không chạy. Khi cần skip có chủ đích (developer laptop), phải hiển thị test skipped và có một CI job bắt buộc chạy container.

**Bảo mật CI:** Docker socket/daemon có quyền mạnh trên runner. Không mount daemon socket không được cách ly cho untrusted forks/PRs có production secrets. Pin images theo version/digest và kiểm tra vulnerability/license policy khi đưa lên production CI.

**Thời gian:** Unit/MVC tests nhanh hơn @SpringBootTest với DB. Không ép mọi test thành full context chỉ để “toàn diện”; hãy giữ test pyramid, chuyên biệt failure signals.

## 29. Lỗi thường gặp và cách chẩn đoán

**1. No tests found:** thiếu JUnit Jupiter engine/launcher, `useJUnitPlatform()` hoặc nhầm import JUnit4. Kiểm tra discovery output và testRuntimeClasspath.

**2. NoSuchMethodError từ JUnit Platform:** trộn JUnit6/5/Platform1 do override BOM hoặc transitive dependency. In dependencyInsight.

**3. Cannot find MockitoBean:** code import Spring Framework6.2 API nhưng thực tế đang Spring Framework6.1 (Boot3.3). Nâng Boot line hợp lệ hoặc giữ API test phù hợp.

**4. Boot4 không compile @MockBean:** annotation cũ đã removed. Dùng @MockitoBean của Spring TestContext, kiểm tra qualifier/scope.

**5. @Mock trong @WebMvcTest không tạo bean:** Mockito field không đăng ký vào Spring container. Dùng @MockitoBean.

**6. Mockito strict-stubbing failure:** stub không dùng; sửa test, đừng tắt toàn bộ strictness.

**7. Mockito final/mock maker warning:** xem Mockito5/Byte Buddy/JDK Java-agent policy; mock external interface khi có thể.

**8. Spring AOP behavior mất trong test mock:** @MockitoBean thay real service/proxy; không dùng kết quả slice mock để chứng minh transaction/retry.

**9. Testcontainers2 package postgresql missing:** phải đổi module `testcontainers-postgresql` và import `org.testcontainers.postgresql.PostgreSQLContainer`.

**10. Testcontainers2 junit-jupiter dependency unresolved:** artifact ID là `testcontainers-junit-jupiter`, không phải ID 1.x.

**11. Docker runtime not found:** lỗi môi trường container engine/permissions, không phải lỗi code JUnit.

**12. @ServiceConnection không cấp datasource:** thiếu `spring-boot-testcontainers` hoặc factory/type matching, container chưa được start hoặc competing config.

**13. Spring Boot4 WebMvcTest import fail:** package mới `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` + webmvc-test starter.

**14. Full Boot4 @SpringBootTest không có MockMvc:** thêm @AutoConfigureMockMvc và test module tương ứng.

**15. javax.servlet không tồn tại Boot3:** chuyển API liên quan sang Jakarta (không đổi mọi javax từ Java SE).

**16. Test H2 pass nhưng production Postgres fail:** dialect/types/constraints không tương đương; chạy Testcontainers thật.

**17. Tests riêng pass, full suite fail:** cached Spring singleton, static state, shared DB rows, container lifecycle, parallel test ordering.

**18. Build Boot4 fail trước khi compile:** Gradle wrapper/JDK không đáp ứng system requirements, không sửa Java assertions để chữa toolchain lỗi.

**19. Security tests compile nhưng annotation bị ignore:** Boot4 module-specific test starters cần đúng technology starter; verify runtime support.

**20. Maven dependency:tree đúng nhưng tests 0:** BOM không cấu hình Surefire test engine; kiểm tra plugin/runner.

## 30. Quy trình nâng cấp từng bước và rollback

**Giai đoạn A — Inventory:** chốt Boot/JDK/Gradle/Maven versions hiện tại, Spring Framework train, dependency overrides, Testcontainers/JUnit/Mockito/Byte Buddy, DB driver và Docker runtime. Lưu các class imports cũ để lập bản đồ migration.

**Giai đoạn B — Baseline:** chạy riêng pure JUnit, Mockito, Web MVC, SQL container và full tests. Ghi số tests discovered/executed/skipped/failed và các HTTP/SQL behaviors. Không chỉ nhìn một status GREEN.

**Giai đoạn C — Patch cleanup:** trên dòng cũ, nâng tới patch bảo mật được cho phép, xử lý deprecations như @MockBean, loại overrides không cần thiết. Khi từ Boot2, xử lý Java17/Jakarta trước.

**Giai đoạn D — Build tool/BOM:** nâng Gradle wrapper hoặc Maven plugin trước khi chuyển Boot4; thay Boot plugin/parent/BOM rồi resolve dependency tree. Không override năm thư viện test riêng lẻ.

**Giai đoạn E — Imports/starter migration:** sửa package @WebMvcTest, Starter WebMVC/JDBC test, @MockitoBean, Testcontainers2 artifacts/PostgreSQLContainer, Jakarta imports. Mỗi thay đổi có một test compile hoặc validation target.

**Giai đoạn F — Layered test:** pure Java → Mockito unit → MVC slices → Spring full context → Docker/PostgreSQL integration → full CI. Tìm failure tại layer đầu tiên có lỗi, không trộn nguyên nhân.

**Giai đoạn G — Observability/rollback:** xác minh 200/400 HTTP, SQL dialect, startup behavior, Docker image policy và JUnit test counts trước rollout. Duy trì branch/tag rollback cho code, database migrations theo chiến lược reversible/forward-compatible riêng.

## 31. Checklist QA khi đối chiếu stack testing

**Version:**

- Đã chọn một Boot release/BOM xác định và theo đúng Java/Gradle support matrix?
- Framework jars cùng một train với Boot, không override spring-test lẻ?
- JUnit Jupiter/Platform/TestEngine versions đồng bộ, Gradle useJUnitPlatform được bật?
- Mockito core/MockitoExtension và Byte Buddy tương thích JDK?
- Testcontainers modules/Core/JUnit extension trong cùng 1.x hoặc 2.x?
- Không dùng module IDs/import packages của Testcontainers1 khi đã nâng 2?

**Unit và MVC:**

- Pure Java JUnit tests có assertions đúng boundary và exceptions?
- Mockito unit tests mock external collaborator, real service được kiểm tra?
- @Mock khác @MockitoBean có được dùng đúng bối cảnh?
- Khi nâng 3.4/3.5 có thay @MockBean theo semantics Framework mới?
- Boot4 WebMvcTest import và test starter đúng?
- @SpringBootTest/MockMvc auto-configuration ở Boot4 đã được khai báo tường minh khi cần?
- Unit test không được gọi là Testcontainers integration test?

**DB và CI:**

- PostgreSQLContainer dùng image phù hợp, @Container lifecycle và @ServiceConnection hoạt động?
- DB integration test gửi truy vấn thực, không phải mock JdbcTemplate?
- JDBC driver có mặt, không lẫn với Testcontainers module?
- Docker-compatible runtime có trong CI và DB tests không bị skip âm thầm?
- File/test logs không lộ credentials, Docker daemon được bảo vệ?
- Có baseline 5+4+3+2 = 14 test methods và kiểm tra số được chạy sau migration?

**Migration:**

- javax/Jakarta/Servlet/Security APIs đã được xem xét khi lên Boot3?
- Technology-specific test starters/module packages đã được thay khi lên Boot4?
- Không bỏ qua context cache/parallel state leaks?
- Có dependencyInsight/dependency:tree làm bằng chứng versions thật?
- Có rollback plan và regression tests bảo vệ HTTP/SQL behavior?

**Kết luận:** một stack testing đúng là tập hợp **Spring Boot BOM + Spring Framework TestContext + JUnit engine + Mockito mocks + Testcontainers integration** hợp nhau. Spring Boot3.5 và 4.1 khác nhau về Framework, JUnit, Testcontainers artifacts và test starters; đừng chỉ tăng một con số version. Khi migration, kiểm tra dependency graph rồi chạy tests theo lớp, từ Java logic đến PostgreSQL thật. Một build thành công mới chỉ cho biết dự án có thể chạy tests; assertions và integration contract mới chứng minh behavior cần giữ.

## 32. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java17, Framework6.2, Gradle/Maven.
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java17, Framework7, Gradle8.14+/9.
- [Boot 3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): JUnit5/Mockito5/Testcontainers1 managed versions.
- [Boot 4.1 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): JUnit6/Mockito5/Testcontainers2.
- [Spring Boot 3.5 Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection/ConnectionDetails.
- [Spring Boot 4.1 Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): updated container packages/services.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, API imports, MockMvc/TestRestTemplate migration.
- [Spring Framework Version Matrix](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): Java and Jakarta support for 5.x/6.x/7.x.
- [Spring Framework @MockitoBean/@MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override semantics.
- [Boot 3.4 @MockBean Deprecation](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): migration to MockitoBean.
- [JUnit 6 Overview](https://docs.junit.org/6.0.0/overview.html): Platform/Jupiter/Vintage and Java17.
- [Mockito Documentation](https://site.mockito.org/): @Mock, MockitoExtension, strict stubbing.
- [Testcontainers Spring Boot Quickstart](https://github.com/testcontainers/testcontainers-java-spring-boot-quickstart): container-driven integration tests.
