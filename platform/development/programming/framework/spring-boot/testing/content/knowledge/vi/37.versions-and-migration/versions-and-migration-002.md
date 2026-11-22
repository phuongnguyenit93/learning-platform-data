# JUnit 4, SpringRunner và chuyển sang JUnit Jupiter trong Spring Boot

## 1. Vì sao cần chuyển từ JUnit 4 sang Jupiter?

Trong nhiều dự án Spring Boot tồn tại đồng thời ba thế hệ test:

- Test cũ có `org.junit.Test`, `@Before`, `@Rule`, `@RunWith(SpringRunner.class)`.
- Test mới có `org.junit.jupiter.api.Test`, `@BeforeEach`, `@ExtendWith`, `@ParameterizedTest`.
- CI dùng **JUnit Platform** để khám phá và thực thi cả hai tập, có thể thông qua **Vintage engine** trong giai đoạn chuyển đổi.

Việc chỉ thay import `org.junit.Test` thành `org.junit.jupiter.api.Test` là **không đủ**. Runner/Rule của JUnit 4 không tự hoạt động dưới Jupiter, thứ tự lifecycle có thể khác, Gradle có thể bỏ sót tests nếu thiếu engine, và Spring context dependency injection cần đúng extension. Một pipeline báo xanh nhưng lặng lẽ không khám phá được 100 tests cũ nguy hiểm hơn một migration thất bại rõ ràng.

Bài này dành cho **Java 17+, Spring Boot 3.5, Spring Framework 6.2 và JUnit Jupiter 5.x**, với lựa chọn giữ tạm JUnit 4.13.2/Vintage trong quá trình chuyển đổi. Những ví dụ Gradle có version pin nhằm tái lập quy trình học, không khẳng định đó là các bản mới nhất.

### Sau bài học, bạn có thể

1. Phân biệt JUnit Platform, Jupiter API/engine, Vintage engine và JUnit 4 runner.
2. Hiểu `SpringRunner` và `SpringExtension` cùng tích hợp Spring TestContext nhưng dùng hai extension models khác nhau.
3. Chuyển `@RunWith(SpringRunner.class)` sang Jupiter đúng cách, biết khi nào `@SpringBootTest` đã bao gồm `SpringExtension`.
4. Chuyển lifecycle `@Before/@After/@BeforeClass/@AfterClass` sang các annotations Jupiter.
5. Thay `@Test(expected=...)`, `ExpectedException` và timeout bằng `assertThrows`, `@Timeout` hoặc `assertTimeout`.
6. Thay `TemporaryFolder`, `TestName`, `@Category`, `@Ignore` và JUnit 4 Rules bằng Jupiter API/extensions.
7. Chuyển JUnit 4 `Parameterized` runner thành `@ParameterizedTest`, `@CsvSource` hoặc `@MethodSource`.
8. Dùng `@MockitoBean` trong Spring Boot 3.5 và `MockitoExtension` cho Mockito unit tests.
9. Dùng Gradle `useJUnitPlatform()`, Vintage có kiểm soát và JUnit test reports để tránh mất test coverage.
10. Bảo toàn Spring TestContext cache, transaction rollback, test slices và semantics của functional assertions.
11. Thiết kế lộ trình migration theo từng class mà không ép đổi mọi test cùng một commit.
12. Nhận diện lỗi import, test discovery, extension order, constructor injection và preemptive timeouts.

## 2. Kiến trúc JUnit: Platform khác Jupiter và Vintage

~~~text
Gradle Test task
      |
      +-- JUnit Platform Launcher
                 |
                 +-- Jupiter TestEngine
                 |     +-- org.junit.jupiter.api.Test
                 |     +-- @BeforeEach, @ParameterizedTest
                 |     +-- @ExtendWith extensions
                 |
                 +-- Vintage TestEngine (temporary)
                       +-- org.junit.Test (JUnit 4)
                       +-- @RunWith(SpringRunner.class)
                       +-- @Rule / @ClassRule
~~~

- **JUnit Platform** là tầng launcher/discovery và test execution API. Gradle `useJUnitPlatform()` dùng nền này.
- **JUnit Jupiter** bao gồm programming model/API cùng test engine cho tests hiện đại.
- **JUnit Vintage** là test engine giúp những JUnit 3/4 tests cũ có thể được chạy trên Platform.
- **JUnit 4** là bộ APIs cũ như `org.junit.Test` và `Runner`; engine Jupiter **không** thực thi những methods chỉ có `org.junit.Test`.
- **SpringRunner** là JUnit 4 runner tích hợp Spring TestContext.
- **SpringExtension** là JUnit Jupiter extension tích hợp cùng Spring TestContext, không phải một JUnit 4 runner đổi tên.

### 2.1 Cùng classpath nhưng không cùng ngữ nghĩa

Hai import sau là **hai annotation types khác nhau**:

~~~java
import org.junit.Test;              // JUnit 4
import org.junit.jupiter.api.Test;  // JUnit Jupiter
~~~

Không import cả hai trong cùng một Java source file bằng simple name `Test`. Java không cho hai single-type imports có cùng simple name; ngay cả khi dùng fully qualified annotation để né conflict, trộn Jupiter và JUnit 4 annotations/methods trong một class là anti-pattern khó dự đoán lifecycle.

### 2.2 Chạy JUnit 4 dưới Platform không có nghĩa đã chuyển sang Jupiter

Nếu Gradle dùng `useJUnitPlatform()` và cài Vintage engine, class `@RunWith(SpringRunner.class)` vẫn chạy **bằng JUnit 4 runner**, chỉ được JUnit Platform tổ chức/discover. Các `@Rule` và `@Before` cũ vẫn giữ semantics JUnit 4.

Muốn **thật sự** chuyển class sang Jupiter, phải đổi imports, lifecycle, assertions và rule/runner mechanisms tương ứng; sau đó mới loại Vintage khi không còn test JUnit 4.

## 3. Bản đồ annotation: JUnit 4 → Jupiter

| JUnit 4 | Jupiter | Lưu ý |
| --- | --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` | Khác package/engine |
| `@Before` | `@BeforeEach` | Chạy trước mỗi test |
| `@After` | `@AfterEach` | Chạy sau mỗi test |
| `@BeforeClass` | `@BeforeAll` | Mặc định static |
| `@AfterClass` | `@AfterAll` | Mặc định static |
| `@Ignore("reason")` | `@Disabled("reason")` | Hoặc conditional annotations |
| `@Category(Fast.class)` | `@Tag("fast")` | Tags là chuỗi, không Class |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` | Spring Boot test annotations thường đã đăng ký sẵn extension |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` | Cho Mockito pure unit |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` | Thêm data sources |
| `@Test(expected=...)` | `assertThrows(...)` | Bọc đoạn code dự kiến ném |
| `@Test(timeout=...)` | `@Timeout` / `assertTimeout` | Thread/transaction semantics cần xem |
| `@Rule TemporaryFolder` | `@TempDir` | Parameter/field injection |
| `@Rule ExpectedException` | `assertThrows` / `assertThrowsExactly` | Kiểm exception/message tùy nhu cầu |
| `@Rule TestName` | `TestInfo` injection | Cho tên method/display name |
| `@Rule / @ClassRule` | Jupiter extensions / `@RegisterExtension` | Không có chuyển đổi 1–1 cho mọi rule |
| `@RunWith(Suite.class)` | JUnit Platform suite / Gradle tags | Cần suite module nếu dùng `@Suite` |
| `Assert.assertEquals(message,expected,actual)` | `Assertions.assertEquals(expected,actual,message)` | Message chuyển cuối tham số |
| `Assume.assumeTrue(...)` | `Assumptions.assumeTrue(...)` | Cần kiểm message order/exception semantics |

Bản đồ này là điểm xuất phát, **không phải** công cụ chuyển mã tự động không cần QA. Với custom Runners/Rules, phải xem chúng làm gì: setup resource, retry, instrumentation, rule chaining hay assertion interception.

## 4. SpringRunner thực hiện gì?

JUnit 4:

~~~java
@RunWith(SpringRunner.class)
@SpringBootTest
public class LegacySpringTest {
    @Autowired SomeService service;

    @Before
    public void setup() { /* ... */ }

    @Test
    public void shouldWork() { /* ... */ }
}
~~~

Đây là **snippet**; `SomeService` và imports chưa được định nghĩa. `SpringRunner` (biệt danh của `SpringJUnit4ClassRunner`) liên kết vòng đời JUnit 4 với Spring TestContext Manager. Spring TestContext cung cấp:

- Tải và cache ApplicationContext theo merged context configuration.
- Dependency injection vào test instance.
- `TestExecutionListener` callbacks.
- Transactional tests và rollback logic khi cấu hình đúng.
- `@ActiveProfiles`, `@TestPropertySource`, `@DirtiesContext`, `@ContextConfiguration`.

**Đổi Runner không có nghĩa bỏ Spring TestContext.** Dưới Jupiter, `SpringExtension` cung cấp những tích hợp tương ứng qua Jupiter extension model.

### 4.1 JUnit 4 chỉ có một @RunWith trong một class

Một class JUnit 4 không thể đồng thời gắn `@RunWith(SpringRunner.class)` và `@RunWith(Parameterized.class)` như hai runners độc lập. Người dùng từng phải viết custom runner, chọn một runner hoặc tách test.

Jupiter dùng extension model và parameterized tests, cho phép tổ hợp `@ExtendWith` với `@ParameterizedTest`, nhưng vẫn phải kiểm tương tác lifecycle/parameter resolution khi nhiều extensions.

## 5. Spring Boot 3.5: thường không cần viết @ExtendWith(SpringExtension.class)

Theo **Spring Boot 3.5 Testing Spring Boot Applications**, `@SpringBootTest` và các test slice annotations như `@WebMvcTest`, `@DataJpaTest` đã meta-annotated để đăng ký `SpringExtension`. Vì vậy:

~~~java
@SpringBootTest
class ModernSpringBootTest {
    @Autowired SomeService service;

    @Test
    void shouldWork() { /* ... */ }
}
~~~

là **đủ tích hợp Spring** nếu dùng đúng Jupiter `@Test`. Viết thêm:

~~~java
@ExtendWith(SpringExtension.class)
@SpringBootTest
class RedundantRegistrationExample { /* ... */ }
~~~

thường không cần thiết, mặc dù Jupiter có xử lý đăng ký duplicate extensions. Hai snippets này là minh họa, chưa phải source files runnable vì `SomeService` thiếu.

### 5.1 Khi nào cần @ExtendWith(SpringExtension.class)?

Khi bạn không sử dụng Spring Boot test composed annotations, ví dụ **plain Spring Framework**:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class PlainSpringContextTest {
    // Dependency injection + Spring TestContext
}
~~~

Hoặc dùng composed annotation `@SpringJUnitConfig(TestConfig.class)` thay cho cả `@ExtendWith` và `@ContextConfiguration`. Bài có một file Spring-only test runnable ở phần ví dụ.

### 5.2 @SpringBootTest vẫn có nhiều web environments

| Boot test mode | Hành vi |
| --- | --- |
| `MOCK` mặc định | Web context giả lập, không chạy embedded server |
| `RANDOM_PORT` | Chạy embedded server trên random port |
| `DEFINED_PORT` | Chạy server theo configured/default port |
| `NONE` | Chạy non-web ApplicationContext |

Đổi JUnit runner sang Jupiter **không** nên âm thầm đổi `webEnvironment`. Nếu migration chuyển từ MockMvc test sang `RANDOM_PORT`, bạn đã thay cả mô hình integration chứ không chỉ framework test, làm QA khó xác định nguyên nhân regressions.

## 6. Dự án thực hành: cùng nghiệp vụ, hai thế hệ test

Mini-project Gradle Java 17+/Spring Boot 3.5 bao gồm:

- `DiscountService` làm phép tính tiền sau giảm giá; Java 17 đủ để chạy.
- `PriceController` HTTP endpoint để thấy test slice.
- `LegacyDiscountServiceTest` dùng JUnit 4 + SpringRunner.
- `DiscountServiceJupiterTest` dùng JUnit Jupiter + `@SpringBootTest` không khai báo SpringExtension lặp lại.
- `DiscountParameterizedTest` dùng `@ParameterizedTest`/`@CsvSource`/`@ValueSource`.
- `DiscountTempDirTest` dùng `@TempDir` thay TemporaryFolder.
- `DiscountMvcJupiterTest` dùng `@WebMvcTest`/`@MockitoBean`.
- `SpringExtensionOnlyTest` dùng plain `@ExtendWith(SpringExtension.class)`/`@ContextConfiguration`.
- `MockitoJupiterTest` minh họa MockitoExtension không cần Spring context.

Cấu trúc:

~~~text
junit-migration-demo/
  settings.gradle
  build.gradle
  src/main/java/example/migration/
    MigrationDemoApplication.java
    DiscountService.java
    PriceController.java
  src/test/java/example/migration/
    LegacyDiscountServiceTest.java
    DiscountServiceJupiterTest.java
    DiscountParameterizedTest.java
    DiscountTempDirTest.java
    DiscountMvcJupiterTest.java
    SpringExtensionOnlyTest.java
    MockitoJupiterTest.java
  src/test/resources/
    junit-platform.properties
~~~

Với cấu hình **giai đoạn chuyển đổi** có Vintage, cả JUnit 4 và Jupiter tests sẽ chạy. Khi xóa class JUnit 4, xóa dependencies Vintage và JUnit 4 để đạt **Jupiter-only**.

## 7. settings.gradle và build.gradle giai đoạn chuyển đổi

`settings.gradle`:

~~~groovy
rootProject.name = 'junit-migration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // CHỈ trong giai đoạn vẫn còn tests JUnit 4:
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }

    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

- `spring-boot-starter-test` đưa JUnit Jupiter, Mockito, AssertJ và test infrastructure vào classpath.
- `junit:junit:4.13.2` cần để compile `org.junit.Test`/`@RunWith` legacy.
- `junit-vintage-engine` làm JUnit Platform discover/run JUnit 4 classes.
- `junit-platform-launcher` giúp Gradle sử dụng launcher phù hợp với engine dependencies.
- `useJUnitPlatform()` là bước quan trọng; không có nó, Jupiter discovery có thể không hoạt động theo cách dự kiến.
- Các dependencies JUnit4/Vintage ở trên **có chủ đích là tạm thời**, không cần với project đã Jupiter-only.

### 7.1 Nếu không có Vintage

Khi giữ `org.junit.Test` nhưng bật `useJUnitPlatform()` và chỉ có Jupiter engine, Gradle có thể không khám phá class legacy. Kết quả “BUILD SUCCESSFUL” **không chứng minh test JUnit 4 đã chạy**.

Phải đối chiếu số lượng test cases trong JUnit XML/Gradle reports, không dựa vào màu xanh của một task.

### 7.2 JUnit Vintage phải tương thích với Platform/Jupiter versions

Dùng dependency management của Spring Boot BOM thay vì trộn bất kỳ major JUnit versions. Khi nâng Spring Boot lên major mới, xem release notes và JUnit Platform compatibility; JUnit 6 có cấu trúc/versions khác JUnit 5. Bài này cố ý target **Boot 3.5/Jupiter 5.x**, không lấy API của Boot 4/JUnit 6 làm ví dụ thay thế.

### 7.3 Gradle wrapper

Tạo/commit Gradle wrapper tương thích với Java 17/Spring Boot 3.5, rồi dùng:

~~~bash
./gradlew clean test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

**Chưa có build/test thực tế chạy trong bài này.** Commands là hướng dẫn tái lập; số tests/expected outcomes dưới đây dựa trên code examples chứ không phải log đã thu.

## 8. MigrationDemoApplication.java

`src/main/java/example/migration/MigrationDemoApplication.java`:

~~~java
package example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MigrationDemoApplication.class, args);
    }
}
~~~

Root package `example.migration` sẽ scan `DiscountService` và `PriceController` cùng package. Không cần database, Docker hoặc external services.

## 9. DiscountService.java

`src/main/java/example/migration/DiscountService.java`:

~~~java
package example.migration;

import org.springframework.stereotype.Service;

@Service
public class DiscountService {

    public int afterDiscount(int priceCents, int percent) {
        if (priceCents < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "price must be non-negative; "
                    + "percent must be within 0..100");
        }

        long result = (long) priceCents * (100 - percent) / 100;
        return Math.toIntExact(result);
    }
}
~~~

Dùng `long` cho phép nhân để không overflow `int` trước khi chia. Với price 10.000 cents và discount 15%, kết quả là **8.500 cents**. Ví dụ dùng integer cents; production pricing có thể cần `BigDecimal`, scale/rounding policy và currency semantics rõ ràng.

## 10. PriceController.java

`src/main/java/example/migration/PriceController.java`:

~~~java
package example.migration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/prices")
public class PriceController {

    private final DiscountService discountService;

    public PriceController(DiscountService discountService) {
        this.discountService = discountService;
    }

    @GetMapping("/after-discount")
    public int afterDiscount(
            @RequestParam int cents,
            @RequestParam int percent) {

        return discountService.afterDiscount(cents, percent);
    }
}
~~~

Endpoint cho test MVC dùng `GET /api/prices/after-discount?cents=10000&percent=15`. Việc return integer dưới `@RestController` qua Spring MVC/Jackson thường tạo body JSON number `8500`. Controller chỉ phục vụ việc so JUnit migration trong một slice; đây không phải API tiền tệ production.

## 11. LegacyDiscountServiceTest.java — JUnit 4 + SpringRunner

`src/test/java/example/migration/LegacyDiscountServiceTest.java`:

~~~java
package example.migration;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@RunWith(SpringRunner.class)
@SpringBootTest(
    classes = MigrationDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
public class LegacyDiscountServiceTest {

    @Autowired
    private DiscountService discountService;

    @Before
    public void verifyWiring() {
        assertNotNull(discountService);
    }

    @Test
    public void calculatesDiscount() {
        assertEquals(8500, discountService.afterDiscount(10000, 15));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsInvalidPercentage() {
        discountService.afterDiscount(10000, 150);
    }
}
~~~

Đây là class JUnit **4**, dùng `public` class/methods theo quy ước JUnit 4. `@Before` chạy trước mỗi method, `@Test(expected=...)` coi test PASS khi exception type phù hợp được ném trong method.

**Bài học:** class này vẫn có thể được chạy trong Gradle `useJUnitPlatform()` nếu **JUnit Vintage engine** có mặt. Vintage không biến annotations sang Jupiter; SpringRunner vẫn quản lý TestContext theo JUnit 4 lifecycle.

### 11.1 Rủi ro với expected exception JUnit 4

`@Test(expected=IllegalArgumentException.class)` coi exception phù hợp ở **bất cứ dòng nào trong method** là success, không chỉ dòng bạn muốn kiểm. Nếu setup trong method vô tình ném đúng exception, test có thể false positive. Với Jupiter `assertThrows`, bọc chính xác operation mong đợi sẽ rõ hơn.

## 12. DiscountServiceJupiterTest.java — phiên bản mới

`src/test/java/example/migration/DiscountServiceJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = MigrationDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DiscountServiceJupiterTest {

    @Autowired
    DiscountService discountService;

    @BeforeEach
    void verifyWiring() {
        assertNotNull(discountService);
    }

    @Test
    @DisplayName("Giảm 15% từ 10.000 cents còn 8.500 cents")
    void calculatesDiscount() {
        assertEquals(
                8500, discountService.afterDiscount(10000, 15));
    }

    @Test
    void rejectsInvalidPercentage() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class,
                        () -> discountService.afterDiscount(10000, 150));

        assertTrue(error.getMessage().contains("0..100"));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> discountService.afterDiscount(-1, 10));
    }
}
~~~

Điểm quan trọng:

- Import `org.junit.jupiter.api.Test`, không phải `org.junit.Test`.
- Jupiter class và methods không buộc phải `public`, nhưng không được `private`.
- `@BeforeEach` thay `@Before`.
- `assertThrows` khoanh chính xác lambda operation phải ném exception và cho phép inspect message.
- `@DisplayName` tạo tên báo cáo dễ đọc; không đổi tên Java method.
- **Không cần ghi `@ExtendWith(SpringExtension.class)`**: Spring Boot 3.5 `@SpringBootTest` đã meta-annotated nó.

### 12.1 Parity với legacy class

Hai tests quan trọng của legacy có bản Jupiter tương đương; Jupiter sample thêm test negative price để minh họa migration không làm giảm coverage. Trong migration thật, giữ semantics asserts nguyên trước, tối ưu/refactor sau, tránh việc test “khác” làm khó so regression.

## 13. Parameterized tests thay JUnit 4 Parameterized runner

JUnit 4 truyền thống:

~~~java
@RunWith(Parameterized.class)
public class LegacyPriceCases {
    // @Parameters returns data; fields/constructor receive arguments
}
~~~

Snippet này chưa độc lập runnable. Với Jupiter, một method có nhiều invocations, không cần runner của cả class.

`src/test/java/example/migration/DiscountParameterizedTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
class DiscountParameterizedTest {

    private final DiscountService discountService =
            new DiscountService();

    @ParameterizedTest(name =
            "price={0}, discount={1}% -> result={2}")
    @CsvSource({
        "10000, 15, 8500",
        "5000, 25, 3750",
        "1000, 0, 1000",
        "1000, 100, 0"
    })
    void calculatesCases(
            int price, int percent, int expected) {

        assertEquals(
                expected, discountService.afterDiscount(price, percent));
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 101})
    void rejectsInvalidPercent(int invalidPercent) {
        assertThrows(IllegalArgumentException.class,
                () -> discountService.afterDiscount(10000, invalidPercent));
    }
}
~~~

Bài demo gồm **hai @ParameterizedTest methods**, lần lượt chạy **4** và **2** invocations, tổng 6 parameterized cases. Đây là JUnit Jupiter test thuần, không dựng Spring context vì business logic không cần dependency injection.

### 13.1 Những data sources hữu ích khác

- `@ValueSource` cho primitive, String, Class...
- `@NullSource`/`@EmptySource`/`@NullAndEmptySource` cho null và dữ liệu rỗng.
- `@EnumSource` cho enum values.
- `@MethodSource` cho streams/collections/`Arguments` phức tạp.
- `@CsvFileSource` cho datasets có định dạng CSV.
- `@ArgumentsSource`/`ArgumentsProvider` cho custom generators.

Với `@MethodSource`, factory thường static theo lifecycle mặc định `PER_METHOD`. Nếu `@TestInstance(PER_CLASS)`, có thể dùng non-static factory. Không ép dùng file CSV cho dữ liệu đơn giản 2–4 rows.

### 13.2 Không nhầm method count với invocation count

JUnit report có thể hiển thị một Java method nhưng nhiều test invocations. Khi so test counts JUnit 4 ↔ Jupiter, đếm **test cases thực thi** (kể cả parameterized invocations), không chỉ số lượng annotations.

## 14. @Rule TemporaryFolder → @TempDir

JUnit 4:

~~~java
@Rule
public TemporaryFolder folder = new TemporaryFolder();
~~~

Jupiter không chạy JUnit 4 Rule này một cách mặc định. Dùng built-in `@TempDir`:

`src/test/java/example/migration/DiscountTempDirTest.java`:

~~~java
package example.migration;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTempDirTest {

    @Test
    void writesTemporaryReport(@TempDir Path tempDirectory)
            throws Exception {

        Path report = tempDirectory.resolve("discount.txt");
        Files.writeString(
                report, "discount=8500", StandardCharsets.UTF_8);

        assertEquals(
                "discount=8500",
                Files.readString(report, StandardCharsets.UTF_8));
    }
}
~~~

`@TempDir` hỗ trợ parameter/field injection; Jupiter quản lý lifecycle và cleanup phù hợp. Không tự tạo file dưới `src/test/resources` hoặc system temp folder chung khi test cần isolation. Test method dùng thư mục riêng; không hardcode absolute OS path.

### 14.1 Quy tắc migration các Rule khác

| JUnit 4 Rule | Cách Jupiter thường dùng |
| --- | --- |
| `TemporaryFolder` | `@TempDir` |
| `ExpectedException` | `assertThrows` / `assertThrowsExactly` |
| `TestName` | `TestInfo` parameter resolver |
| `Timeout` | `@Timeout` hoặc `assertTimeout` |
| `ExternalResource` | BeforeEach/AfterEach/BeforeAll/AfterAll callbacks, AutoCloseable store |
| `Verifier` | Assertion trong test hoặc AfterEachCallback |
| `RuleChain` | Thứ tự Jupiter extensions, explicit composition |
| Custom `@ClassRule` | Class-level extension/`@RegisterExtension` có lifecycle rõ |

Không luôn có chuyển đổi 1–1. Hãy xem Rule cũ đang bảo vệ tài nguyên gì và tại mốc nào. Một custom Rule chặn exception/retry/transaction cần được viết lại có chủ đích, không chỉ đổi tên annotation.

## 15. Mockito: Runner JUnit 4 và Extension Jupiter

JUnit 4 từng dùng:

~~~java
@RunWith(MockitoJUnitRunner.class)
public class LegacyMockTest {
    @Mock Repository repo;
}
~~~

Đây là snippet. Jupiter dùng `MockitoExtension` (thường có trong `spring-boot-starter-test`) khi test **không cần Spring context**:

`src/test/java/example/migration/MockitoJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class MockitoJupiterTest {

    @Mock
    Runnable auditCallback;

    @Test
    void verifiesMockInvocation() {
        auditCallback.run();
        verify(auditCallback, times(1)).run();
    }
}
~~~

Ví dụ dùng `Runnable` làm dependency nhỏ để minh họa lifecycle Mockito, không cần app context. Trong production, mock repository/client gateway thực, kiểm interaction có ý nghĩa và tránh overmocking.

### 15.1 @Mock khác @MockitoBean

- `@Mock` do MockitoExtension hoặc Mockito init quản lý trên **test instance**.
- `@MockitoBean` từ Spring TestContext bean override mechanism, thay thế/thêm **bean trong ApplicationContext**.
- Dùng `@MockitoBean` khi controller/service integration slice cần bean Spring được mock; không thêm `MockitoExtension` vào mọi `@SpringBootTest` theo thói quen.
- Với Spring Boot 3.5/Spring Framework 6.2, `@MockBean` và `@SpyBean` của Spring Boot đã bị **deprecated từ 3.4** để nhường chỗ cho `@MockitoBean` và `@MockitoSpyBean`. Khi đổi, kiểm import và reset semantics.

Không dùng `@Mock` field rồi mong `@Autowired` controller trong Spring context tự nhận object mock đó. Hai scopes khác nhau.

## 16. @WebMvcTest + @MockitoBean minh họa migration test slice

`src/test/java/example/migration/DiscountMvcJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PriceController.class)
class DiscountMvcJupiterTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    DiscountService discountService;

    @Test
    void endpointReturnsDiscountedPrice() throws Exception {
        when(discountService.afterDiscount(10000, 15))
                .thenReturn(8500);

        mockMvc.perform(get("/api/prices/after-discount")
                        .param("cents", "10000")
                        .param("percent", "15"))
                .andExpect(status().isOk())
                .andExpect(content().string("8500"));
    }
}
~~~

`@WebMvcTest` đăng ký SpringExtension qua composed annotation. `@MockitoBean` tạo mock `DiscountService` trong MVC slice để controller constructor injection hoạt động. `MockMvc` gửi mock request trong JVM và kiểm status/body; **không mở real HTTP server**.

Với controller có Spring Security filter chain, cần xác định có yêu cầu mock users/CSRF hay không; bài này không thêm Spring Security. Nếu một test JUnit4 cũ dùng `@RunWith(SpringRunner.class)` + `@WebMvcTest`, migration chính là đổi imports/lifecycle/test method, không cần thêm một `@ExtendWith` dư.

### 16.1 Tách test migration khỏi cấu trúc context

Đổi từ `@SpringBootTest` sang `@WebMvcTest` **có thể làm test nhanh hơn** nhưng cũng thay coverage (DB/services/filters). Khi mục tiêu là “chuyển JUnit 4 sang Jupiter”, trước tiên giữ nguyên test slice/config, sau đó tối ưu layer trong PR riêng.

## 17. Plain Spring Framework: SpringExtension rõ ràng

`src/test/java/example/migration/SpringExtensionOnlyTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SpringExtensionOnlyTest.DiscountConfig.class)
class SpringExtensionOnlyTest {

    @Autowired
    DiscountService discountService;

    @Test
    void plainSpringContextWiresService() {
        assertEquals(
                3750, discountService.afterDiscount(5000, 25));
    }

    @Configuration(proxyBeanMethods = false)
    static class DiscountConfig {
        @Bean
        DiscountService discountService() {
            return new DiscountService();
        }
    }
}
~~~

File này **không dùng @SpringBootTest**. `@ExtendWith(SpringExtension.class)` thực sự cần vì `@ContextConfiguration` đơn lẻ không đăng ký Jupiter extension. Có thể rút gọn thành:

~~~java
@SpringJUnitConfig(
    classes = SpringExtensionOnlyTest.DiscountConfig.class)
class AlternativeSpringTest {
    // SpringExtension + ContextConfiguration được compose.
}
~~~

Snippet thứ hai minh họa, không thêm thành file trong mini-project. `@SpringJUnitConfig` là Spring Framework composed annotation; hữu ích cho plain Spring contexts khi không cần toàn bộ Boot autoconfiguration.

## 18. @Before, @After, @BeforeClass, @AfterClass

JUnit 4:

~~~java
@Before public void beforeEachTest() { }
@After public void afterEachTest() { }
@BeforeClass public static void beforeSuiteClass() { }
@AfterClass public static void afterSuiteClass() { }
~~~

Jupiter:

~~~java
@BeforeEach void beforeEachTest() { }
@AfterEach void afterEachTest() { }
@BeforeAll static void beforeAllTestsInClass() { }
@AfterAll static void afterAllTestsInClass() { }
~~~

Hai fragments này là mapping annotation, không phải standalone Java source vì thiếu containing class/imports.

### 18.1 Static lifecycle

- Jupiter `@BeforeAll` và `@AfterAll` mặc định phải static trong top-level class với default test-instance lifecycle `PER_METHOD`.
- Có thể dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` để cho phép non-static `@BeforeAll/@AfterAll`.
- JUnit 4 `@BeforeClass`/`@AfterClass` thường public static; Jupiter methods có thể package-private.
- `@Nested` test classes và test instance lifecycle có rules riêng; đừng chuyển cơ học static/non-static khi test có state.

### 18.2 PER_METHOD vs PER_CLASS

Mặc định Jupiter tạo **test instance mới cho mỗi test method** (PER_METHOD), giúp giảm chia sẻ mutable fields. PER_CLASS dùng một test instance cho toàn class và có thể tạo state leakage nếu tests mutate fields. Đây không liên quan trực tiếp tới Spring **ApplicationContext** caching: dù test instance mới, Spring có thể reuse một context.

### 18.3 Không giả định thứ tự các test methods

Jupiter không cam kết một thứ tự business logic tùy ý giữa methods. Nếu test cần method A tạo data cho B, đó là dấu hiệu thiếu isolation. `@TestMethodOrder` dùng khi có mục tiêu lifecycle cụ thể, nhưng migration thông thường nên giữ tests độc lập.

## 19. Assertions: message argument và assertThrows

JUnit 4:

~~~java
assertEquals("bad total", expected, actual);
~~~

Jupiter:

~~~java
assertEquals(expected, actual, "bad total");
assertEquals(expected, actual, () -> "computed message lazily");
~~~

Đây là snippets, cần `expected`/`actual` và import tương ứng. **Failure message chuyển từ vị trí đầu sang cuối**, không được search/replace thiếu kiểm tra.

### 19.1 Exceptions

JUnit 4:

~~~java
@Test(expected = IllegalStateException.class)
public void invalidTransitionFails() {
    stateMachine.transition();
}
~~~

Jupiter:

~~~java
@Test
void invalidTransitionFails() {
    IllegalStateException thrown =
            assertThrows(IllegalStateException.class,
                    () -> stateMachine.transition());
    assertEquals("invalid state", thrown.getMessage());
}
~~~

Đây là **fragments** cần `stateMachine`, imports. Jupiter `assertThrows` chấp nhận exception type mong đợi **hoặc subclass**, còn `assertThrowsExactly` yêu cầu type đúng chính xác. Chọn theo business contract.

### 19.2 assertAll và grouping assertions

~~~java
assertAll(
    () -> assertEquals(8500, price),
    () -> assertTrue(statusReady)
);
~~~

Snippet minh họa: các assertions được đánh giá như nhóm, giúp báo nhiều failures của cùng một record thay vì dừng ở assertion đầu tiên. Không dùng nó để che exception từ setup bên ngoài hoặc làm tests phụ thuộc thứ tự.

### 19.3 assertIterableEquals, assertArrayEquals, assertInstanceOf

Jupiter có thêm assertions hữu ích nhưng **không bắt buộc rewrite mọi assertion thư viện khác**. AssertJ/Hamcrest vẫn dùng bình thường nếu tương thích; mục tiêu migration là engine/lifecycle đúng và giữ semantic coverage.

## 20. Timeout migration và giao dịch Spring

JUnit 4 `@Test(timeout=1000)` không map đơn giản một-một sang Jupiter trong mọi tình huống. Jupiter có:

~~~java
@Timeout(value = 1, unit = TimeUnit.SECONDS)
@Test
void shouldFinishQuickly() {
    operation();
}
~~~

Và:

~~~java
assertTimeout(
    Duration.ofSeconds(1),
    () -> operation()
);
~~~

Đây là snippets cần imports và `operation()`. Cách `assertTimeout` kiểm thời gian thường chạy code trong same thread; nó báo thất bại **sau khi** operation vượt giới hạn, không nhất thiết ngắt operation tại deadline.

### 20.1 Cẩn thận assertTimeoutPreemptively

`assertTimeoutPreemptively` chạy executable ở thread khác. Spring TestContext transaction state thường được bind với current thread qua ThreadLocal. Nếu test có `@Transactional`, code chạy trong thread khác **có thể không tham gia test-managed transaction** và dữ liệu không được rollback như bạn mong đợi.

Do đó:

- Với test `@Transactional`, ưu tiên `assertTimeout` hoặc thiết kế timeout mechanism không phá thread-bound context.
- Không đổi hàng loạt JUnit4 timeout sang `assertTimeoutPreemptively` mà chưa kiểm transaction boundary.
- Trong `@SpringBootTest(RANDOM_PORT)`, client HTTP và server đã ở threads/transactions khác nhau; test-managed rollback không bao trùm giao dịch server.
- Với async/reactive code, test đúng completion/cancellation semantics thay vì chỉ chờ sleep.

### 20.2 Timeout trên CI dễ flaky

Một hard-coded 10ms timeout cho `@SpringBootTest` có thể fail do context/JIT/GC/CI load dù functionality đúng. Giới hạn của **method body** khác giới hạn start application context. Nếu dùng performance criteria, đo nhiều runs và target controlled runner, không tạo unit assertions theo một con số laptop.

## 21. @Ignore, conditions và environment-dependent tests

JUnit 4:

~~~java
@Ignore("temporarily disabled")
@Test
public void legacyCase() { }
~~~

Jupiter:

~~~java
@Disabled("temporarily disabled")
@Test
void modernCase() { }
~~~

Hai snippets minh họa. `@Disabled` là skipped test với reason; nó không chứng minh test PASS. Điều kiện Jupiter:

- `@EnabledOnOs`/`@DisabledOnOs`.
- `@EnabledOnJre`/`@DisabledOnJre`.
- `@EnabledIfEnvironmentVariable`.
- `@EnabledIfSystemProperty`.
- Custom `ExecutionCondition` extension.

Nếu integration test cần Docker, **không** lặng lẽ disabled trong mandatory release gate. Route nó tới Docker-capable CI runner hoặc báo pipeline blocker rõ ràng.

## 22. @Category thành @Tag và Gradle selection

JUnit 4:

~~~java
@Category(SlowTests.class)
public class LegacySlowTest { }
~~~

Jupiter:

~~~java
@Tag("slow")
class ModernSlowTest { }
~~~

`@Category` dùng marker Java class/interface; Jupiter `@Tag` dùng string (không có spaces/comma theo JUnit rules). Với Gradle:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'slow'
    }
}
~~~

Đây là fragment dùng khi bạn thật sự muốn lọc tags. Nếu áp dụng `includeTags 'unit'` cho **toàn bộ test task** nhưng chỉ annotate một vài Jupiter tests, toàn bộ Spring Boot integration tests chưa tagged có thể bị loại **mà không phải code fail**.

Vì vậy rollout tagging phải kèm checklist thống kê discovered/executed/skipped tests và CI policy. Không thêm filter toàn cục rồi tuyên bố migration hoàn tất dựa vào test task PASS.

### 22.1 Vintage Categories trong migration

JUnit Platform Vintage có khả năng expose JUnit 4 categories theo tags. Tuy nhiên việc chọn tags có thể cần đúng tên/metadata tương ứng với category class, không nhất thiết bằng chuỗi Jupiter `"slow"`. Kiểm JUnit Vintage documentation và Gradle report của repo trước khi dùng một filter để chọn hai thế hệ tests.

## 23. @Rule, @ClassRule và custom extension migration

JUnit 4 Rules cho phép wrap method/class statement:

~~~text
Rule.enter
  @Before
    @Test
  @After
Rule.exit
~~~

Jupiter extensions có nhiều interfaces tùy lifecycle:

| Nhu cầu Rule cũ | Jupiter extension API phù hợp |
| --- | --- |
| Setup trước cả class | `BeforeAllCallback` |
| Cleanup cuối class | `AfterAllCallback` |
| Setup trước từng method | `BeforeEachCallback` |
| Cleanup sau từng method | `AfterEachCallback` |
| Trước/sau chính test body | `BeforeTestExecutionCallback`, `AfterTestExecutionCallback` |
| Intercept invocation | `InvocationInterceptor` |
| Resolve constructor/test parameters | `ParameterResolver` |
| Customize exception handling | `TestExecutionExceptionHandler` |
| Conditional skip | `ExecutionCondition` |
| Resource lifecycle per scope | `ExtensionContext.Store` / `CloseableResource` |
| Field-based extension registration | `@RegisterExtension` |

Đừng ép một custom `Rule` chứa retry logic, thread switching hoặc JUnit4 `Statement` wrapper thành chỉ một `BeforeEachCallback` mà chưa xem behavior. Một rule có thể kiểm exceptions/cleanup trong `finally`; extension mới phải bảo đảm cleanup cả khi assertion/fixture fail.

### 23.1 JUnit 4 Rule compatibility support chỉ là bước đệm

Một số JUnit Jupiter migration support có giới hạn tương thích JUnit4 Rule; phạm vi/versions thay đổi. Với code mới, ưu tiên Jupiter native APIs/extensions. Không dùng thư viện “rule adapter” như một lý do giữ JUnit 4 lâu dài khi đã có `@TempDir` hoặc `assertThrows` đơn giản hơn.

## 24. @RunWith(Suite.class) và test discovery

JUnit 4 `@RunWith(Suite.class)` + `@Suite.SuiteClasses` gom classes thành suite. Jupiter/JUnit Platform có module `junit-platform-suite` với `@Suite`, `@SelectClasses`, `@SelectPackages`, `@IncludeTags` nếu thực sự cần suite classes.

Ví dụ conceptual:

~~~java
@Suite
@SelectClasses({
    DiscountServiceJupiterTest.class,
    DiscountTempDirTest.class
})
class MigrationSmokeSuite {
}
~~~

Đây là snippet; cần imports từ `org.junit.platform.suite.api` và dependency `org.junit.platform:junit-platform-suite`. **Không thêm Suite class vào mini-project** khi Gradle test task đã khám phá tất cả test classes. Với nhiều CI nhóm, Gradle tags/test filters thường rõ hơn test suite wrapper.

### 24.1 Test suites có thể dẫn đến double execution

Nếu JUnit Platform khám phá cả original test classes lẫn suite class chọn lại chúng, bạn có thể vô tình chạy cùng test nhiều lần. Cấu hình test discovery/selectors phù hợp trước khi thêm suites vào CI.

## 25. @TestInstance(PER_CLASS) và constructor injection

Jupiter có thể inject parameters vào test constructor/method qua `ParameterResolver`, trong đó `SpringExtension` hỗ trợ dependency injection của Spring TestContext.

Ví dụ minh họa (không thêm vào demo):

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest
class ConstructorInjectionTest {

    final DiscountService service;

    @Autowired
    ConstructorInjectionTest(DiscountService service) {
        this.service = service;
    }

    @BeforeAll
    void warmup() {
        service.afterDiscount(10000, 10);
    }
}
~~~

Có thể dùng `@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)` hoặc khai báo `@Autowired` phù hợp. Spring Framework docs quy định test constructor auto-wiring không mặc định `ALL` nếu không cấu hình, nên không loại `@Autowired` một cách tự động.

### 25.1 Tác động của PER_CLASS

- Non-static `@BeforeAll` được phép.
- Test instance sống lâu hơn nên mutable fields có thể rò state giữa methods.
- Nếu có `@DirtiesContext` hoặc thay ApplicationContext trong khi giữ constructor-injected beans, cần xem bean references bị stale.
- Không buộc mọi test dùng PER_CLASS chỉ để chuyển `@BeforeClass`.

## 26. @Nested và Spring context inheritance

Jupiter `@Nested` giúp nhóm các tình huống có setup riêng:

~~~java
@Nested
class WhenDiscountIsZero {
    @Test
    void returnsOriginalPrice() { /* ... */ }
}
~~~

Snippet cần enclosing test class/imports. Với Spring TestContext, `@NestedTestConfiguration` kiểm cách nested test kế thừa Spring test configuration của enclosing class (INHERIT/OVERRIDE semantics). Không mặc định giả định mọi nested class tự load context riêng hoặc tự cô lập data.

Nếu chuyển JUnit4 inner-class runner/custom suite sang `@Nested`, đánh giá:

1. Nested test instance/lifecycle.
2. Spring TestContext configuration inheritance.
3. Extension registration/inheritance.
4. Fixture and transaction scope.
5. Mockito bean override changes.
6. Cache key và `@DirtiesContext` behavior.

Đối với đơn vị migration nhỏ, có thể giữ flat classes trước, chuyển sang `@Nested` sau khi functional parity đã được xác nhận.

## 27. Spring transaction rollback khi đổi test engine

`@Transactional` trên Spring integration test có thể được Spring TestContext quản lý và rollback sau mỗi method, với điều kiện transaction manager/test setup đúng.

~~~java
@SpringBootTest
@Transactional
class RepositoryTest {
    @Test
    void insertsAndRollsBack() {
        // Chạy repository trong test-managed transaction.
    }
}
~~~

Snippet này thiếu repository, là mô hình chứ không phải runnable file. `SpringExtension` tích hợp transaction TestExecutionListener như SpringRunner, nhưng **test-managed transaction gắn với thread**.

- Không dùng `assertTimeoutPreemptively` trong một test transactional mà không xét ThreadLocal transaction.
- Với `@SpringBootTest(RANDOM_PORT)`, HTTP server xử lý request trong thread/transaction khác; test thread rollback không rollback server writes.
- Với async jobs/schedulers, transaction contexts không tự băng qua threads.
- Với database integration tests, kiểm trạng thái DB trước/sau thật, không suy chỉ từ engine migration.

Migration JUnit 4 → Jupiter không phải giấy phép đổi transaction semantics bằng một annotation mà không kiểm tra.

## 28. Spring context cache và Mockito bean overrides

Spring TestContext cache được key theo metadata: config classes/locations, active profiles, properties, customizers, bean overrides. Chuyển từ `SpringRunner` sang `SpringExtension` **không tự đòi rebuild context mỗi test method**, nhưng nếu bạn đồng thời đổi:

- `@SpringBootTest` thành `@WebMvcTest`.
- `@ActiveProfiles("test")` thành profile khác.
- `@MockBean` thành mock khác type/name.
- `@TestPropertySource` thêm properties.
- `@DirtiesContext` class/method modes.
- `@MockitoBean` fields khác nhau giữa tests.

thì số contexts/cache misses có thể đổi và làm suite chậm. Bật `org.springframework.test.context.cache=DEBUG` khi cần so before/after. Giữ config tương thích và test isolation an toàn.

### 28.1 Test instance lifecycle không đồng nghĩa context cache

Jupiter mặc định tạo test instance mới mỗi method, nhưng Spring có thể reuse **ApplicationContext**. Đừng tăng `@TestInstance(PER_CLASS)` chỉ để “cache Spring context”: đó là hai caches/lifecycles khác nhau.

## 29. JUnit Platform configuration và concurrency

Tạo `src/test/resources/junit-platform.properties`:

~~~properties
# Baseline migration: keep test execution deterministic.
junit.jupiter.execution.parallel.enabled=false
~~~

Khi migration còn custom Rules/Spring transactions và shared fixtures, bắt đầu với Jupiter parallel disabled để phát hiện khác biệt framework/lifecycle trước. Không tuyên bố Vintage engine parallelism bị cấu hình này kiểm soát hoàn toàn; Vintage có parameters riêng theo version.

Nếu cần parallel về sau:

- Xác định database/fixture independence.
- Giới hạn Gradle forks và Spring context count.
- Không chia sẻ static mutable state không reset.
- Kiểm `@ResourceLock`/`@Execution` và thread-bound transaction semantics.
- Đo CPU/RAM/CI flakiness thay vì bật parallel vô điều kiện.

## 30. Chạy test theo từng giai đoạn và xác nhận discovery

Với Gradle wrapper từ root project:

~~~bash
./gradlew clean test
./gradlew test --tests '*LegacyDiscountServiceTest'
./gradlew test --tests '*DiscountServiceJupiterTest'
./gradlew test --tests '*DiscountParameterizedTest'
~~~

Test task được cấu hình `useJUnitPlatform()`. Khi Vintage còn tồn tại, legacy test được discover bởi Vintage, Jupiter tests bởi Jupiter engine.

### 30.1 Những kết quả dự kiến từ sample

| Test class | Engine | Java test methods | Executed cases |
| --- | --- | ---: | ---: |
| LegacyDiscountServiceTest | Vintage/JUnit 4 | 2 | 2 |
| DiscountServiceJupiterTest | Jupiter | 3 | 3 |
| DiscountParameterizedTest | Jupiter | 2 parameterized methods | 6 |
| DiscountTempDirTest | Jupiter | 1 | 1 |
| DiscountMvcJupiterTest | Jupiter | 1 | 1 |
| SpringExtensionOnlyTest | Jupiter | 1 | 1 |
| MockitoJupiterTest | Jupiter | 1 | 1 |
| **Tổng** | — | **11 methods** | **15 cases** |

Số **15 cases** là theo số methods/invocations trong source demo. Đây là **kết quả mong đợi**, không phải actual Gradle output. Nếu report cho ít hơn, kiểm engine/tag/test discovery; nếu khác do thêm tests, cập nhật baseline.

### 30.2 JUnit XML / HTML reports

Gradle Test task thường ghi:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

Trong CI, lưu artifacts kể cả khi test FAIL để biết:

- Bao nhiêu tests đã discovered, executed, skipped, failed.
- Class legacy có thật chạy không.
- Parameterized methods có đủ invocations.
- Jupiter/Vintage test count có parity với baseline.
- Có class bị excluded do tags/Gradle filters không.

Đừng nhìn đơn độc dòng `BUILD SUCCESSFUL`; migration có thể vô tình loại toàn bộ JUnit 4 tests mà vẫn hoàn tất task.

## 31. Maven Surefire/Failsafe và IDE caveats

Nếu dự án dùng Maven thay Gradle, cần Surefire/Failsafe versions hỗ trợ JUnit Platform và test engines phù hợp. `spring-boot-starter-test` không tự bảo đảm rằng một plugin Maven cũ chạy đúng Jupiter.

Chạy cả Maven CI và IDE test run configurations; một IDE có thể dùng JUnit Jupiter runner khác CI, và chỉ vì test xanh trong IntelliJ không có nghĩa Gradle/Maven CI đã discover được legacy tests.

Nếu repo có test naming convention khác nhau (`*Test`, `*Tests`, `*IT`), kiểm Gradle/Maven includes. `InventoryIT` có thể không được Maven Surefire phát hiện nếu integration naming dành cho Failsafe; đừng đổ cho Jupiter engine khi root cause là test file patterns.

## 32. Legacy support tạm thời và mốc gỡ Vintage

Một chiến lược chuyển đổi an toàn:

~~~text
Phase 0: Inventory
  +-- Count JUnit 4 + Jupiter tests, rules, runners, CI engines
  +-- Record executed test count and test outcomes

Phase 1: Platform
  +-- Run JUnit Platform with Jupiter + Vintage
  +-- Verify BOTH test generations execute

Phase 2: Incremental migration
  +-- Convert test classes one-by-one
  +-- Keep assertions, fixtures, transactions equivalent
  +-- Replace custom Rules/runners carefully

Phase 3: Jupiter-only
  +-- No org.junit.Test / @RunWith / @Rule sources
  +-- Remove junit:junit and junit-vintage-engine dependencies
  +-- Run clean test, inspect reports

Phase 4: Cleanup
  +-- Refactor test slices, parameterization, extension reuse
  +-- Monitor context cache and CI performance
~~~

### 32.1 Không gỡ Vintage quá sớm

Nếu còn 200 JUnit4 tests, xóa Vintage trước khi chuyển hết có thể khiến Gradle không thực thi chúng. Không dùng `@Disabled`/test filter để làm counts trông hợp lý. Đặt CI gate tối thiểu về executed test count hoặc script kiểm engines/test source imports trong quá trình migration.

### 32.2 Khi đã chuyển hết

`build.gradle` chuyển về:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Không còn `junit:junit`, `junit-vintage-engine`. Xóa `LegacyDiscountServiceTest.java` hoặc chuyển hoàn toàn sang Jupiter, rồi chạy sạch Gradle. `@RunWith(SpringRunner.class)` không cần nữa trong Jupiter.

## 33. Những lỗi thường gặp

**1. Đổi import Test nhưng giữ @RunWith(SpringRunner.class).**  
JUnit4 runner không quản lý Jupiter @Test; phải chuyển lifecycle/extension hoặc giữ class JUnit4 + Vintage.

**2. useJUnitPlatform nhưng quên Vintage khi còn JUnit4.**  
Build có thể xanh do tests cũ không được khám phá.

**3. Chỉ kiểm BUILD SUCCESSFUL, không đối chiếu test count.**  
Mất coverage âm thầm.

**4. Thêm @ExtendWith(SpringExtension.class) vào mọi @SpringBootTest/@WebMvcTest.**  
Boot 3.5 đã đăng ký SpringExtension; phần này thường dư.

**5. Đổi SpringRunner sang MockitoExtension trong Spring integration test.**  
MockitoExtension không thay Spring TestContext dependency injection/transactions.

**6. Dùng @Mock và tưởng Spring bean tự bị override.**  
Trong Spring context cần `@MockitoBean` hoặc cơ chế config/test override thích hợp.

**7. Dùng @MockBean đã deprecated mà không biết lộ trình @MockitoBean.**  
Kiểm Framework6.2/Boot3.5 APIs/imports trước refactor.

**8. Đổi @Before thành @BeforeAll.**  
Sai lifecycle; @Before là per-test, phải thành @BeforeEach.

**9. Quên static cho @BeforeAll với PER_METHOD.**  
Jupiter báo validation lỗi nếu không có cấu hình PER_CLASS phù hợp.

**10. Đổi message parameter của assertEquals sai vị trí.**  
JUnit4 message trước; Jupiter message cuối.

**11. Thay @Test(expected) bằng assertThrows quanh toàn bộ setup không kiểm soát.**  
Có thể giữ false positive; bọc đúng operation.

**12. Dùng assertTimeoutPreemptively trong @Transactional test.**  
Khác thread có thể bypass Spring test transaction rollback.

**13. Coi @SpringBootTest(RANDOM_PORT) rollback được HTTP server writes bằng test-thread @Transactional.**  
Server chạy thread/transaction khác; phải cleanup DB thật.

**14. Copy @Rule TemporaryFolder sang Jupiter.**  
Rule JUnit4 không tự chạy; dùng @TempDir.

**15. Cố kết hợp JUnit4 @RunWith(Suite/Parameterized/SpringRunner) trong một class.**  
Một runner JUnit4 không giải quyết nhiều nhu cầu; dùng Jupiter extensions/params.

**16. Chuyển @Category class thành @Tag với chuỗi sai và lọc mọi tests.**  
Tags phải được kiểm; CI có thể exclude classes bất ngờ.

**17. Bật JUnit parallel trước khi cleanup fixtures.**  
Tests dùng shared DB/static state có thể flake.

**18. Dùng @TestInstance(PER_CLASS) chỉ để cache ApplicationContext.**  
Khác lifecycle; có nguy cơ rò mutable fields.

**19. Đổi từ full-context sang test slice cùng lúc khi migration engine.**  
Không thể tách regression do test layer hay Jupiter.

**20. Dùng MockitoExtension cùng Spring Boot test để sửa bean injection sai.**  
Spring bean override và Mockito test-instance mock là hai scopes khác nhau.

**21. Quên testRuntimeOnly launcher/engine alignment trong Gradle.**  
Engine/version mismatch hoặc discovery failure.

**22. Maven plugin Surefire quá cũ.**  
IDE PASS nhưng Maven CI không chạy Jupiter đúng.

**23. Vintage engine để lại vô thời hạn.**  
Làm migration ownership mơ hồ và tiếp tục gánh custom Rules cũ.

**24. Trộn JUnit4/Jupiter @Test trong cùng source file.**  
Import ambiguity/lifecycle không rõ; mỗi class nên theo một programming model.

**25. Thay test assertion thật bằng mock để đạt cùng số lượng test.**  
Count bằng nhau không chứng minh behavior coverage như nhau.

## 34. Quy trình migration có thể áp dụng tại dự án thật

1. Tìm imports `org.junit.Test`, `org.junit.runner.RunWith`, `org.junit.Rule` và custom runners.
2. Ghi baseline test executions, skips, failures và build reports.
3. Cập nhật Gradle/Maven test launcher để hỗ trợ JUnit Platform.
4. Tạm cài Vintage để JUnit4 tests tiếp tục chạy trong giai đoạn hỗn hợp.
5. Chọn một class JUnit4 đơn giản để migrate trước.
6. Đổi sang `org.junit.jupiter.api.Test`, `@BeforeEach`/`@AfterEach`.
7. Nếu có `@SpringBootTest`/slice, tận dụng SpringExtension được meta-register; với plain Spring dùng `@ExtendWith` hoặc `@SpringJUnitConfig`.
8. Chuyển `@Test(expected)` và ExpectedException sang `assertThrows`.
9. Chuyển `TemporaryFolder` sang `@TempDir`, TestName sang TestInfo.
10. Chuyển parameterized runner sang `@ParameterizedTest` và correct sources.
11. Chuyển MockitoJUnitRunner/Rules sang MockitoExtension nếu pure unit; `@MockitoBean` nếu cần Spring bean override.
12. Kiểm constructor injection, test instance lifecycle, @Nested config và transaction boundaries.
13. Bảo toàn profiles, bean mocks, test slices và `@DirtiesContext` semantics.
14. Chạy class mới riêng và full suite với both engines, so expected coverage.
15. Xem JUnit XML/HTML reports để phát hiện tests bị omitted do engine/filter.
16. Migrate các classes có custom Rules/Suites sau khi đã hiểu lifecycle.
17. Chỉ gỡ Vintage/JUnit4 dependencies khi không còn legacy test sources.
18. Chạy clean CI pipeline, xác nhận executed test count/behavior và test isolation.
19. Refactor/nâng tốc độ tests trong bước riêng, sau functional parity.
20. Ghi migration guide cho team: imports, extension policies, MockitoBean và CI engine conventions.

### Checklist cuối

- [ ] Gradle/Maven dùng JUnit Platform khi chạy Jupiter.
- [ ] Legacy JUnit4 tests vẫn chạy qua Vintage trong chuyển tiếp.
- [ ] JUnit4/Jupiter @Test imports không bị trộn sai.
- [ ] @Before/@After đổi sang @BeforeEach/@AfterEach.
- [ ] @BeforeClass/@AfterClass đổi đúng @BeforeAll/@AfterAll.
- [ ] @SpringBootTest/@WebMvcTest giữ đúng SpringExtension, không lặp dư khi không cần.
- [ ] Plain Spring TestContext có @ExtendWith hoặc @SpringJUnitConfig.
- [ ] @Test(expected) được chuyển sang assertThrows đúng lambda.
- [ ] assertTimeoutPreemptively không phá transactional rollback.
- [ ] @Rule/TemporaryFolder/TestName/Category có migration tương ứng.
- [ ] Mockito pure unit và Spring @MockitoBean được phân biệt.
- [ ] Parameterized tests có đủ invocation count.
- [ ] Spring context/test slice/profiles/fixtures giữ nguyên behavior.
- [ ] JUnit XML/Gradle reports xác nhận tất cả tests thực thi.
- [ ] Không có accidental skips do tags/engines.
- [ ] Vintage chỉ được gỡ sau khi JUnit4 tests đã hết.
- [ ] CI chạy Java17+, Boot3.5 và dependencies tương thích.
- [ ] Test counts bằng nhau không được thay cho assertions/behavior coverage.

## 35. Kết luận

**Chuyển từ JUnit 4/SpringRunner sang JUnit Jupiter là chuyển cả programming model và extension model**, không chỉ sửa một import. Trên Spring Boot 3.5, `@SpringBootTest` và test slice annotations đã hỗ trợ Jupiter `SpringExtension`, giúp code tests mới gọn hơn. Jupiter thay JUnit4 runners/rules bằng extensions, data-driven tests, assertions và temp-dir injection.

Trong một repo lớn, **JUnit Vintage là cầu nối tạm thời**, cho phép Gradle `useJUnitPlatform()` chạy JUnit4 lẫn Jupiter. Nhưng build xanh chỉ có ý nghĩa khi bạn đối chiếu test discovery, số cases, fixtures và business assertions. Hãy migrate từng class, giữ Spring context và transaction semantics, chỉ bỏ Vintage sau khi tất cả JUnit4 tests thực sự được thay thế.

### Tài liệu tham khảo chính thức

- [JUnit 5 User Guide — Migrating from JUnit 4](https://docs.junit.org/5.12.0/user-guide/#migrating-from-junit4): JUnit4 annotations, rules, runners, Vintage.
- [JUnit 5 User Guide — Extensions](https://docs.junit.org/5.12.0/user-guide/#extensions): callbacks, parameter resolution và lifecycle.
- [JUnit 5 User Guide — Parameterized Tests](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parameterized-tests): data sources và invocations.
- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution): test isolation.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): Jupiter auto-registered SpringExtension, test environments.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html): starter-test/JUnit testing guidance.
- [Spring Framework 6.2 — Spring JUnit Jupiter Annotations](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-junit-jupiter.html): SpringJUnitConfig, TestConstructor.
- [Spring Framework 6.2 — TestContext Jupiter Integration](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/support-classes.html#testcontext-junit-jupiter-extension): SpringExtension and dependency injection.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): thread-bound test transactions.
- [Spring Framework 6.2 — MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): useJUnitPlatform, reports, filters.
