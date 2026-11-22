# Vai trò của JUnit, Spring Test, Spring Boot Test, Mockito và Testcontainers

## 1. Bức tranh tổng thể: mỗi công cụ giải quyết một việc

Khi kiểm thử một ứng dụng Spring Boot, ta cần trả lời nhiều câu hỏi khác nhau: phép tính nghiệp vụ có đúng không, Spring có khởi tạo và nối các bean đúng không, HTTP request có được xử lý đúng không, và ứng dụng có làm việc chính xác với PostgreSQL hoặc dịch vụ phụ thuộc thật không? Không một thư viện nào tự mình trả lời được tất cả.

| Thành phần | Trách nhiệm cốt lõi | Dấu hiệu nhận biết | Điều **không** tự đảm bảo |
| --- | --- | --- | --- |
| **JUnit Jupiter (JUnit 5)** | Định nghĩa, chạy và xác nhận kết quả test Java | `@Test`, `@BeforeEach`, `assertEquals`, `assertThrows` | Không tự tạo Spring context, mock dependency hay database |
| **Mockito** | Tạo test double cho collaborator và kiểm tra tương tác khi cần | `@Mock`, `when(...).thenReturn(...)`, `verify(...)` | Không chứng minh JDBC, HTTP, cấu hình DI hoặc hệ thống ngoài hoạt động thật |
| **Spring Test (Spring Framework)** | Tích hợp JUnit với Spring TestContext, DI và các công cụ kiểm thử framework | `SpringExtension`, `@SpringJUnitConfig`, `MockMvc`, `@Transactional` | Không mặc nhiên khởi động toàn bộ cấu hình tự động của Spring Boot |
| **Spring Boot Test** | Đưa quy ước auto-configuration của Boot vào test; cung cấp test toàn ứng dụng và test từng lát | `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` | Không mặc nhiên biến dependency giả thành dịch vụ thật; `@SpringBootTest` cũng không có nghĩa là luôn mở HTTP port |
| **Testcontainers** | Cấp phát dịch vụ phụ thuộc thật trong container dùng cho test | `@Testcontainers`, `@Container`, `PostgreSQLContainer` | Không thay JUnit, assertion, Mockito hay Spring Test; thường cần runtime container như Docker |

Một bài test có thể dùng **JUnit + Mockito**, **JUnit + Spring Test**, **JUnit + Spring Boot Test**, hoặc **JUnit + Spring Boot Test + Testcontainers**. Đây là các vai trò có thể phối hợp, không phải năm lựa chọn loại trừ nhau.

Sơ đồ tư duy:

```text
JUnit Jupiter: định nghĩa test, gọi test, xác nhận đúng/sai
  ├─ Mockito: thay collaborator bằng mock khi cần cô lập logic
  └─ Spring Test: dựng và quản lý Spring TestContext, hỗ trợ DI/MockMvc
       └─ Spring Boot Test: thêm Boot auto-configuration, test slices,
            @SpringBootTest và các tiện ích Boot
                 └─ Testcontainers: cấp database/broker/service thật cho test
```

Sơ đồ biểu diễn **vai trò trong một chiến lược test**, không phải quan hệ kế thừa của mọi thư viện. Testcontainers có thể sử dụng riêng với JUnit mà không cần Spring.

## 2. JUnit Jupiter: khung thực thi và tiêu chí PASS/FAIL

JUnit 5 gồm JUnit Platform (nền tảng chạy test), Jupiter (API và engine viết/chạy test) và khả năng hỗ trợ engine khác. Khi nói “viết test JUnit 5”, ta thường dùng **JUnit Jupiter**.

- `@Test`: đánh dấu một phương thức kiểm thử; assertion sai hoặc exception không mong đợi làm test FAIL.
- `@BeforeEach` / `@AfterEach`: thiết lập, thu dọn quanh từng test; `@BeforeAll` / `@AfterAll` dùng cho vòng đời lớp.
- `assertEquals`, `assertTrue`, `assertThrows`, `assertAll`: phát biểu kết quả mong đợi.
- `@ParameterizedTest` với nguồn tham số: kiểm tra nhiều trường hợp theo cùng một quy tắc.
- `@Nested`, `@DisplayName`: tổ chức test dễ đọc.
- Extension API, chẳng hạn `MockitoExtension` hay `SpringExtension`: gắn các cơ chế bổ sung vào vòng đời JUnit.

Test tốt có cấu trúc **Arrange → Act → Assert**: chuẩn bị dữ liệu, thực hiện một hành động, rồi kiểm chứng hành vi quan sát được. Tên test nên mô tả điều kiện và kết quả, chẳng hạn `rejectsNegativeSubtotal`.

JUnit **không yêu cầu Spring**. Nếu đối tượng chỉ chứa logic Java thuần và có thể tự khởi tạo, chạy test trực tiếp sẽ nhanh hơn và ít phụ thuộc hơn.

## 3. Mockito: cô lập collaborator, không giả lập toàn bộ hệ thống

Giả sử `CheckoutService` cần một `DiscountPolicy`. Mục tiêu của unit test là kiểm tra quyết định tính tiền của `CheckoutService`, chưa cần kiểm tra cách `DiscountPolicy` lấy dữ liệu từ nơi khác. Mockito cung cấp một đối tượng thay thế, có thể định nghĩa đầu ra và quan sát lời gọi.

- `@Mock` hoặc `mock(...)`: tạo mock; hành vi chưa cấu hình nhận giá trị mặc định theo kiểu trả về.
- `when(mock.method(...)).thenReturn(...)`: cấu hình kết quả trả về; `doThrow(...).when(mock)...` hữu ích cho các trường hợp khác.
- `verify(mock).method(...)`: xác nhận một tương tác quan trọng; chỉ nên kiểm tra khi tương tác là một phần của hợp đồng hành vi.
- `@InjectMocks`: Mockito cố gắng tạo/tiêm mock vào đối tượng đang kiểm thử, **không** khởi tạo Spring ApplicationContext.
- `@ExtendWith(MockitoExtension.class)`: tích hợp mock và vòng đời test với JUnit Jupiter.

### Ví dụ Java 17 chạy độc lập: JUnit + Mockito

Dự án Gradle nhỏ này **không cần Spring Boot**. Tạo hai tệp:

`settings.gradle`:

```groovy
rootProject.name = 'checkout-unit-testing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.15.2'
}

test {
    useJUnitPlatform()
}
```

`src/test/java/CheckoutServiceTest.java`:

```java
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
class CheckoutServiceTest {
    interface DiscountPolicy {
        int discountFor(int subtotal);
    }

    static final class CheckoutService {
        private final DiscountPolicy policy;

        CheckoutService(DiscountPolicy policy) {
            this.policy = policy;
        }

        int total(int subtotal) {
            if (subtotal < 0) {
                throw new IllegalArgumentException("subtotal must be nonnegative");
            }
            return subtotal - policy.discountFor(subtotal);
        }
    }

    @Mock
    DiscountPolicy policy;

    @Test
    void calculatesTotalAfterDiscount() {
        when(policy.discountFor(100)).thenReturn(15);

        int actual = new CheckoutService(policy).total(100);

        assertEquals(85, actual);
        verify(policy).discountFor(100);
    }

    @Test
    void rejectsNegativeSubtotalWithoutConsultingPolicy() {
        CheckoutService checkout = new CheckoutService(policy);

        assertThrows(
                IllegalArgumentException.class,
                () -> checkout.total(-1)
        );
        verifyNoInteractions(policy);
    }
}
```

Trong thư mục dự án có Gradle được cài đặt, chạy:

```bash
gradle test
```

Hoặc nếu dự án có Gradle Wrapper thì chạy `./gradlew test` (Linux/macOS) hay `gradlew.bat test` (Windows). Có **2 test** được chạy: trường hợp đầu mong đợi tổng tiền là `85`; trường hợp sau mong đợi `IllegalArgumentException` và không có lời gọi tới policy. JUnit báo lỗi nếu một assertion thất bại. Không cần gán stdout cố định vì Gradle hiển thị log tùy phiên bản/cấu hình.

**Giới hạn của ví dụ:** mock chứng minh logic của `CheckoutService` theo hành vi policy đã giả định; nó không kiểm tra cách triển khai `DiscountPolicy` thật, DI trong Spring hay kết nối database. Không nên mock chính lớp đang kiểm thử rồi chỉ `verify` lời gọi của lớp đó: test sẽ không kiểm tra kết quả nghiệp vụ thật.

## 4. Spring Test: kiểm tra khi Spring Framework tham gia

`spring-test` đưa cơ chế kiểm thử của **Spring Framework** vào JUnit:

1. `SpringExtension` nối vòng đời JUnit Jupiter với Spring TestContext Framework. `@SpringJUnitConfig` là annotation tiện lợi kết hợp extension và cấu hình context.
2. TestContext khởi tạo/caching `ApplicationContext`, hỗ trợ tiêm `@Autowired`, cấu hình test, active profile, property source và test execution listeners.
3. `MockMvc` mô phỏng lời gọi vào tầng Spring MVC qua `DispatcherServlet` **mà không cần HTTP server thật**. Nó khác với Mockito: “Mock” trong MockMvc chỉ cơ chế chạy request MVC trong tiến trình test.
4. Hỗ trợ quản lý transaction trong test tích hợp Spring; với test chạy trong transaction do framework quản lý, rollback có thể diễn ra sau test theo cấu hình.

Ví dụ chỉ tải một Spring context nhỏ, không phải cả ứng dụng Boot:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ClockSpringTest.FixedClockConfig.class)
class ClockSpringTest {
    @Configuration
    static class FixedClockConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Test
    void injectsConfiguredBean() {
        assertEquals(2024, LocalDate.now(clock).getYear());
    }
}
```

Đặt tệp tại `src/test/java/ClockSpringTest.java` trong dự án đã có `spring-test`, `spring-context` và JUnit Jupiter (thường có qua `spring-boot-starter-test`). Test này kiểm tra Spring tạo và inject `Clock` bean từ cấu hình đã cho. Nó chưa chứng minh toàn bộ ứng dụng Boot khởi động.

**Lưu ý caching context:** Spring Test thường tái sử dụng context có cùng cấu hình giữa các test để giảm thời gian. Việc đổi profile, cấu hình hay dùng `@DirtiesContext` tràn lan làm tăng số lần khởi tạo context. Test không được phụ thuộc vào dữ liệu/biến mutable do test trước để lại.

## 5. Spring Boot Test: chọn đúng phạm vi context

Spring Boot xây dựng trên Spring Test và các quy ước Boot. Trong ứng dụng dùng Spring Boot 3.3.x, dependency kiểm thử thông dụng là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đoạn dependency này giả định dự án đã dùng Spring Boot plugin hoặc cơ chế quản lý phiên bản dependency của Boot. Starter test cung cấp JUnit Jupiter, Mockito, Spring Test, AssertJ và các thành phần test phổ biến. Không cần dựng Spring context trong mọi test chỉ vì starter đã có sẵn.

### 5.1. Test slice: tải đúng một “lát” cần kiểm tra

- `@WebMvcTest(MyController.class)`: tập trung vào Spring MVC (route, binding, validation, status, JSON, exception handler phù hợp); collaborator ngoài lát MVC thường cần mock hoặc cấu hình bổ sung.
- `@DataJpaTest`: kiểm tra JPA entity, repository, mapping và query với cấu hình Data JPA. Mặc định có cơ chế dùng embedded test database nếu khả dụng; với PostgreSQL thật cần cấu hình rõ để không tự thay bằng embedded DB.
- `@JdbcTest`: tập trung vào JDBC và các bean liên quan.
- `@JsonTest`: kiểm tra serialization/deserialization JSON.
- `@RestClientTest`: kiểm tra client HTTP và cấu hình liên quan trong phạm vi slice.

Ví dụ, giả sử ứng dụng đã có `GreetingController` phục vụ `GET /greetings/{name}`, controller gọi `GreetingService.greet(name)` và trả về nội dung string. Test trong Boot 3.3.x:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService greetingService;

    @Test
    void returnsGreetingFromHttpEndpoint() throws Exception {
        when(greetingService.greet("Lan")).thenReturn("Chào Lan");

        mvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Chào Lan"));
    }
}
```

Test này là **đoạn tích hợp vào ứng dụng có sẵn**, cần controller và service đúng hợp đồng đã mô tả. JUnit thực thi test; `@WebMvcTest` dựng MVC slice; `MockMvc` gửi request mô phỏng; `@MockBean` thay dependency `GreetingService` trong Spring context bằng Mockito mock. Nó kiểm tra mapping và HTTP response nhưng **không chứng minh logic của service thật** hoặc hệ thống đang nghe trên TCP port. Nếu ứng dụng bật Spring Security, filter/security configuration cũng ảnh hưởng kết quả; cần thiết lập user/authorization test tương ứng thay vì coi `401/403` là lỗi controller.

**Phân biệt phiên bản:** trong Spring Boot 3.3.x, `@MockBean` thuộc Boot là cách phổ biến thay bean bằng Mockito mock. Từ Spring Boot 3.4 / Spring Framework 6.2, hướng API mới là `@MockitoBean`; không sao chép annotation này vào dự án Boot 3.3 rồi mặc định nó tồn tại.

### 5.2. `@SpringBootTest`: phạm vi rộng hơn

`@SpringBootTest` tìm cấu hình Boot và nạp application context gần với ứng dụng thực. Nó phù hợp khi kiểm tra wiring nhiều layer, auto-configuration, xử lý sự kiện, tích hợp hoặc một luồng đi xuyên nhiều bean.

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // PASS nếu context tạo thành công, không phải chứng minh nghiệp vụ.
    }
}
```

Mặc định `@SpringBootTest` dùng web environment kiểu `MOCK` nếu phù hợp, **không khởi động HTTP server trên cổng thật**. Muốn test mạng HTTP thực, dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và một HTTP client; chỉ chọn khi cần chứng minh hành vi qua socket/network. Bài `contextLoads` là smoke test cấu hình, chưa đủ làm bằng chứng nghiệp vụ.

Có thể kết hợp `@SpringBootTest` với `@AutoConfigureMockMvc` để test MVC trong context rộng hơn mà không mở HTTP port. Đổi lại, context lớn thường khởi động chậm và dễ chịu tác động của database, message broker hoặc cấu hình ngoài.

## 6. Testcontainers: kiểm thử với hạ tầng có hành vi thật

Mockito mock thích hợp để cô lập tương tác. Nhưng query SQL, transaction semantics, constraint, collation, migration, hành vi message broker hay khác biệt dialect đôi khi cần một **dịch vụ thật**. Testcontainers khởi chạy container tạm cho PostgreSQL, MySQL, Redis, Kafka và nhiều hệ thống khác thông qua runtime container (phổ biến là Docker).

Ví dụ một test kết nối PostgreSQL thật trong ứng dụng Spring Boot 3.3.x có `spring-boot-starter-jdbc` và driver PostgreSQL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Các dependency trên giả định Boot BOM đã quản lý phiên bản. Trong `src/test/java/.../DatabaseConnectionIT.java` của ứng dụng Boot đã có `@SpringBootApplication`:

```java
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
class DatabaseConnectionIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToRealPostgres() {
        Integer value = jdbcTemplate.queryForObject(
                "select 1", Integer.class
        );

        assertEquals(Integer.valueOf(1), value);
    }
}
```

Giải thích từng trách nhiệm:

1. **JUnit** chạy `connectsToRealPostgres` và so sánh kết quả.
2. **Testcontainers** quản lý lifecycle container PostgreSQL cho test; trường `static` cho phép tái dùng container trong phạm vi class.
3. **Spring Boot Test** dựng context ứng dụng và cấu hình `JdbcTemplate`.
4. **`@ServiceConnection`** (Boot 3.1+) cho Boot biết cách lấy thông tin kết nối từ PostgreSQL container; không cần hardcode port ngẫu nhiên. Cần `spring-boot-testcontainers`.
5. **PostgreSQL thật** xử lý câu SQL và trả `1`, nên test kiểm tra kết nối end-to-end từ Spring JDBC tới database trong container.

Đây là mẫu **tích hợp trong ứng dụng Boot đã cấu hình được**, không phải chương trình độc lập chỉ cần một tệp. Để chạy thành công cần runtime container hoạt động, khả năng tải image PostgreSQL, plugin/dependency management của Boot và không có cấu hình ứng dụng khác làm context thất bại. Có thể chạy bằng `./gradlew test --tests '*DatabaseConnectionIT'` nếu class thuộc task `test`; một số dự án có task `integrationTest` riêng và cần điều chỉnh.

Một cách nối container với cấu hình Spring không dựa trên `@ServiceConnection` là `@DynamicPropertySource` để cung cấp `spring.datasource.url`, `username` và `password` từ container. Dùng **một** cách quản lý kết nối rõ ràng, tránh khai báo nhiều giá trị cấu hình xung đột.

Với `@DataJpaTest` hoặc `@JdbcTest` cần PostgreSQL container, kiểm tra cấu hình tự thay DataSource trong slice; khi cần có thể dùng `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` để giữ DataSource từ Testcontainers. Testcontainers **không tự khởi chạy đầy đủ Spring context**, và không phải unit test sẽ luôn cần container.

## 7. Chọn công cụ theo câu hỏi cần chứng minh

| Câu hỏi kiểm thử | Phạm vi gợi ý | Công cụ thường cần | Vì sao |
| --- | --- | --- | --- |
| Quy tắc giá/điều kiện/biến đổi dữ liệu đúng không? | Unit test | JUnit; Mockito nếu có collaborator | Logic Java thuần, nhanh, cô lập |
| Một service gọi đúng cổng gửi mail khi xử lý yêu cầu? | Unit test tương tác | JUnit + Mockito | Kiểm tra hợp đồng gọi collaborator mà không gửi mail thật |
| Spring có tạo bean từ cấu hình cụ thể và inject đúng không? | Spring component test | JUnit + Spring Test | Cần một `ApplicationContext` nhỏ |
| URL, JSON, validation và HTTP status của controller đúng không? | MVC slice | JUnit + Spring Boot Test `@WebMvcTest` + MockMvc; Mockito cho service boundary | Cần MVC runtime nhưng không cần toàn bộ ứng dụng |
| Repository/migration/query chạy đúng trên PostgreSQL không? | Database integration | JUnit + Spring Boot Test slice hoặc full + Testcontainers | Cần database/dialect thật |
| Một luồng request đi qua nhiều layer và ghi DB đúng không? | Integration/system test | `@SpringBootTest` + Testcontainers; HTTP client/MockMvc tùy mục tiêu | Kiểm thử wiring và tương tác thật qua nhiều lớp |

Quy tắc chọn mức kiểm thử: bắt đầu ở **mức nhỏ nhất có thể quan sát hành vi cần chứng minh**; tăng phạm vi khi bản chất lỗi có thể nằm ở wiring, serialization, HTTP/security filter, SQL dialect hoặc tích hợp dịch vụ. Một test với nhiều thư viện hơn không đương nhiên chất lượng hơn.

### Ví dụ phân rã một yêu cầu

Yêu cầu: “Đặt hàng hợp lệ phải trừ số lượng tồn kho và trả `201 Created`; thiếu hàng phải trả lỗi hợp lệ”.

- **JUnit + Mockito:** kiểm tra service từ chối đặt hàng khi tồn kho không đủ; không cần DB.
- **`@WebMvcTest` + MockMvc:** kiểm tra endpoint trả đúng `201` hoặc response lỗi, mapping JSON/request validation; mock service để tập trung vào MVC.
- **`@DataJpaTest` + Testcontainers PostgreSQL:** kiểm tra query cập nhật tồn kho và constraint trên PostgreSQL thật.
- **`@SpringBootTest` + Testcontainers:** kiểm tra một luồng quan trọng đi qua controller → service → repository → DB. Nếu cần chứng minh HTTP server thật, dùng `RANDOM_PORT`; nếu chỉ cần MVC dispatch trong app context, cân nhắc MockMvc.

Các test này **bổ sung bằng chứng khác nhau**. Không cần lặp lại mọi trường hợp đầu vào ở cả bốn tầng.

## 8. Các điểm dễ nhầm và lỗi thường gặp

**1. Nhầm `@Mock` với `@MockBean`.** `@Mock` chỉ tạo đối tượng Mockito trong test; nó không tự thay Spring bean khi `@SpringBootTest` hoặc `@WebMvcTest` dựng context. Với Boot 3.3, `@MockBean` đăng ký/thay bean trong context. Ngược lại, đừng dùng Boot context chỉ để Mockito inject một POJO.

**2. Nhầm `MockMvc` với mock một service.** MockMvc thực thi Spring MVC pipeline không có HTTP server thật; service mock bởi Mockito trả kết quả đã lập trình. Vì vậy `@WebMvcTest` có thể kiểm tra mapping/validation nhưng không chứng minh service thật lưu dữ liệu.

**3. Dùng `@SpringBootTest` cho mọi test.** Context toàn ứng dụng tốn tài nguyên, làm chậm test và gây phụ thuộc vào môi trường. Unit test và slice test phù hợp thường nhanh hơn, rõ nguyên nhân FAIL hơn. Chỉ mở rộng context khi cần.

**4. Chỉ dùng database nhúng rồi suy diễn sang database production.** H2 hoặc database nhúng khác có thể khác PostgreSQL về cú pháp SQL, khóa, isolation, constraint và kiểu dữ liệu. Với logic phụ thuộc DB, dùng Testcontainers để kiểm tra hệ quản trị đúng mục tiêu.

**5. Giả định `@Transactional` luôn rollback mọi thay đổi.** Transaction test do Spring Test quản lý có thể rollback các thao tác nằm trong transaction của test thread. Khi `RANDOM_PORT` gửi HTTP tới server chạy ở thread/transaction khác, các commit phía server không tự được rollback chỉ vì test method có `@Transactional`. Cần dọn dữ liệu hoặc cô lập trạng thái phù hợp.

**6. Test không độc lập, dữ liệu dùng chung gây flaky.** Tránh phụ thuộc thứ tự chạy, dùng cùng bản ghi mà không cleanup, sleep theo thời gian cố định, cổng máy cố định, hoặc truy cập dịch vụ production. Tạo fixture rõ ràng; đặt tên/id test tách biệt, quản lý cleanup và chờ điều kiện khi có xử lý bất đồng bộ.

**7. Verify mọi lời gọi nội bộ.** `verify` quá chi tiết khiến refactor vô hại làm test fail dù kết quả người dùng không đổi. Ưu tiên assertion trên output và state. Dùng `verify` cho tương tác có ý nghĩa như “gửi đúng một thông báo” hoặc “không gọi cổng thanh toán khi dữ liệu sai”.

**8. Nhầm test chạy với test có ý nghĩa.** Test `contextLoads` chỉ xác nhận context khởi động. Một test có assertion yếu như `assertNotNull(service)` không thay thế được việc kiểm tra output, lỗi, side effect hoặc hợp đồng tương tác.

## 9. Cách tổ chức và vận hành bộ test

Trong dự án Boot, `src/test/java` chứa các lớp JUnit; `src/test/resources` chứa fixture và cấu hình dành riêng cho test. Dùng tên rõ như `OrderServiceTest`, `OrderControllerTest`, `OrderRepositoryIT` để người đọc hiểu mục đích. Hậu tố `IT` chỉ là quy ước: Gradle **không tự tạo task integration test riêng** vì tên lớp có hậu tố đó; phải cấu hình source set/task nếu muốn tách lịch chạy.

Một pipeline tham khảo:

1. Chạy unit test JUnit/Mockito thường xuyên để có phản hồi nhanh.
2. Chạy Spring MVC/JPA slice test cho hợp đồng framework.
3. Chạy integration test với PostgreSQL/Testcontainers cho đường đi liên quan database và dịch vụ thực.
4. Duy trì vài smoke/e2e test cho luồng quan trọng, tránh khiến toàn bộ test suite lệ thuộc vào nhiều service ở mọi commit.

Với ứng dụng dùng Gradle Wrapper, lệnh thông dụng:

```bash
./gradlew test
./gradlew test --tests '*CheckoutServiceTest'
./gradlew test --tests '*DatabaseConnectionIT'
```

Trên Windows dùng `gradlew.bat` thay `./gradlew`. Các lệnh chỉ chạy những lớp thuộc task `test`; task tích hợp riêng cần được định nghĩa trong build. Testcontainers yêu cầu runtime container khả dụng trong máy local/CI; cấu hình CI cần cấp quyền phù hợp và có thể cache image để giảm thời gian.

### Checklist khi thiết kế một test

- **Hành vi:** Test đang bảo vệ quy tắc nào? Assert điều gì người dùng hoặc hệ thống ngoài quan sát được?
- **Ranh giới:** Có thật sự cần Spring context, HTTP stack, transaction hoặc DB thật không?
- **Dependency:** Collaborator nên là đối tượng thật, Mockito mock hay Testcontainers service?
- **Tính độc lập:** Dữ liệu, thời gian, thứ tự chạy, cổng mạng, credentials và cleanup có ổn định không?
- **Tốc độ/độ tin cậy:** Test chậm có mua được bằng chứng mà test nhỏ không thể cung cấp không?
- **Khi FAIL:** Có thể nhận biết rõ lỗi ở logic Java, wiring, MVC/security, persistence hay hạ tầng không?

## 10. Kết luận định hướng

**JUnit** là người tổ chức và phán xử test; **Mockito** cô lập collaborator khi cần; **Spring Test** cung cấp cơ chế kiểm thử framework và context; **Spring Boot Test** quyết định Boot application context hoặc slice nào được kiểm tra; **Testcontainers** cung cấp hạ tầng thật tạm thời để quan sát hành vi tích hợp. Chọn chúng theo **câu hỏi cần chứng minh**, rồi xác nhận bằng assertion cụ thể. Cách phối hợp này cho một bộ test vừa nhanh ở tầng logic, vừa đủ đáng tin ở các ranh giới framework và hạ tầng.