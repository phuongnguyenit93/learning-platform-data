# Quan hệ với hỗ trợ JUnit 4 và TestNG trong mã cũ

Spring TestContext Framework được thiết kế để quản lý phần tích hợp kiểm thử của Spring độc lập với một test framework cụ thể. Nó cung cấp cơ chế tạo và tái sử dụng `ApplicationContext`, chuẩn bị test instance, quản lý các sự kiện vòng đời và chạy những hành vi kiểm thử được đăng ký qua `TestExecutionListener`.

JUnit Jupiter là một cách tích hợp hiện đại thông qua `SpringExtension`. Trong các hệ thống cũ, cùng nền tảng TestContext đó cũng có thể được sử dụng với JUnit 4 và TestNG. Điểm cần phân biệt là phần cốt lõi của Spring TestContext được chia sẻ, còn cách một test framework gọi vào phần cốt lõi được triển khai bằng adapter riêng.

Hiểu ranh giới này giúp duy trì các bộ kiểm thử cũ, kết hợp nhiều test framework trong giai đoạn chuyển đổi và lập kế hoạch chuyển sang JUnit Jupiter mà không phải viết lại toàn bộ cấu hình Spring.

## 1. TestContext Framework và các test framework

Một ứng dụng Spring có thể có các bài kiểm thử được viết bằng nhiều test framework qua những giai đoạn phát triển khác nhau. Ví dụ, một module cũ dùng JUnit 4, một bộ kiểm thử tích hợp dùng TestNG, còn code mới dùng JUnit Jupiter.

Spring TestContext Framework cung cấp các thành phần chung:

- **TestContextManager:** điều phối vòng đời kiểm thử và giao tiếp với các listener.
- **TestContext:** giữ thông tin về test class, test method, test instance và application context.
- **TestExecutionListener:** thực hiện các hành vi trước/sau test class hoặc test method, chẳng hạn dependency injection, quản lý transaction và xử lý annotation kiểm thử.
- **Context cache:** tái sử dụng application context khi các bài kiểm thử có cấu hình tương đương.

Mỗi test framework cần một cách tích hợp vòng đời phù hợp:

| Test framework | Cách tích hợp Spring phổ biến |
|---|---|
| JUnit Jupiter | `SpringExtension`, thường qua `@ExtendWith` hoặc annotation tổng hợp |
| JUnit 4 | `SpringRunner` hoặc các rule `SpringClassRule` và `SpringMethodRule` |
| TestNG | Các lớp nền `AbstractTestNGSpringContextTests` và `AbstractTransactionalTestNGSpringContextTests` |

Sơ đồ khái quát:

```text
                  Spring TestContext Framework
              TestContextManager / TestContext / Listeners
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
       JUnit Jupiter        JUnit 4           TestNG
       SpringExtension      SpringRunner      AbstractTestNG...
             |                |                |
             v                v                v
        JUnit Platform    JUnit 4 runner     TestNG lifecycle
```

Các adapter đưa sự kiện của framework tương ứng vào TestContext Framework. Chúng không làm cho JUnit 4, JUnit Jupiter và TestNG trở thành cùng một framework; mỗi framework vẫn có annotation, quy tắc thực thi và cách cấu hình riêng.

## 2. Hỗ trợ JUnit 4 bằng SpringRunner

Trong JUnit 4, Spring cung cấp `SpringRunner`, tên khác của `SpringJUnit4ClassRunner`. Runner này kết nối vòng đời JUnit 4 với Spring TestContext Framework.

Một test class có thể khai báo:

```java
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;

@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

Trong ví dụ này:

1. `@RunWith(SpringRunner.class)` yêu cầu JUnit 4 sử dụng SpringRunner để chạy test class.
2. `@ContextConfiguration` chỉ định nguồn cấu hình để tạo Spring test context.
3. Spring chuẩn bị test instance và inject `GreetingService`.
4. JUnit 4 chạy phương thức có `@Test`.
5. Spring TestContext Framework phối hợp các listener và callback cần thiết quanh quá trình thực thi.

Các annotation như `@Autowired`, `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@DirtiesContext`, `@Transactional`, `@Rollback`, `@Commit` và `@Sql` có thể tiếp tục được sử dụng theo hỗ trợ của Spring TestContext Framework. Cấu hình cụ thể vẫn phải đáp ứng điều kiện của từng annotation và listener tương ứng.

### SpringRunner và giới hạn một runner

JUnit 4 sử dụng một runner cho một test class thông qua `@RunWith`. Nếu class đã cần runner khác, không thể khai báo thêm một `@RunWith` độc lập cho SpringRunner.

Ví dụ, một test class đang dùng runner của một thư viện khác sẽ gặp xung đột nếu cố gắng thêm `@RunWith(SpringRunner.class)`. Trong trường hợp này, Spring cung cấp hai rule để tích hợp TestContext mà vẫn giữ runner hiện có:

- `SpringClassRule` xử lý các sự kiện ở phạm vi class.
- `SpringMethodRule` xử lý các sự kiện ở phạm vi method và chuẩn bị test instance.

## 3. Dùng SpringClassRule và SpringMethodRule khi cần runner khác

Nếu JUnit 4 test class phải dùng một runner khác, có thể đăng ký Spring rules:

```java
import org.junit.ClassRule;
import org.junit.Rule;
import org.junit.Test;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.rules.SpringClassRule;
import org.springframework.test.context.junit4.rules.SpringMethodRule;

@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyRunnerTest {

    @ClassRule
    public static final SpringClassRule springClassRule =
            new SpringClassRule();

    @Rule
    public final SpringMethodRule springMethodRule =
            new SpringMethodRule();

    @Test
    public void runsWithSpringTestContext() {
        // Test sử dụng cấu hình và tính năng của Spring TestContext.
    }
}
```

Trong ví dụ này, test class không khai báo `@RunWith(SpringRunner.class)`. Các rule cung cấp điểm tích hợp Spring trong vòng đời JUnit 4. Runner khác vẫn có thể điều khiển test class theo yêu cầu của thư viện đang dùng.

Cần đăng ký cả hai rule để bao phủ các sự kiện cấp class và cấp method. Chỉ thêm một rule không tương đương với tích hợp đầy đủ của SpringRunner.

Rules là API của JUnit 4. Không thể chuyển nguyên `@ClassRule` và `@Rule` sang một test class JUnit Jupiter rồi kỳ vọng chúng được xử lý như cũ. Khi chuyển sang Jupiter, cần thay thế bằng extension hoặc cơ chế tương ứng của Jupiter.

## 4. Các annotation Spring vẫn dùng được trong test JUnit 4

Một ưu điểm của TestContext Framework là nhiều annotation mô tả cấu hình và ý định kiểm thử không gắn riêng với JUnit Jupiter. Khi dùng adapter JUnit 4 phù hợp, test cũ có thể tiếp tục sử dụng những tính năng Spring quen thuộc.

Ví dụ kiểm thử service với profile và transaction:

```java
@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyPersistenceConfig.class)
@ActiveProfiles("test")
@Transactional
public class LegacyOrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    public void findsSavedOrder() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertEquals(
                "ORDER-42",
                orderRepository.findById("ORDER-42")
                        .orElseThrow()
                        .getId()
        );
    }
}
```

Với test-managed transaction được cấu hình đúng, Spring có thể bắt đầu transaction trước test và rollback theo mặc định sau test. `@Commit` hoặc `@Rollback(false)` có thể thay đổi hành vi rollback khi thực sự cần. Cần có transaction manager và cấu hình persistence phù hợp; chỉ đặt `@Transactional` không tự tạo database hoặc schema cho test.

Điều quan trọng là JUnit 4 runner cung cấp vòng đời để Spring TestContext áp dụng các tính năng đó. Quy tắc về transaction, context cache và listener vẫn thuộc Spring TestContext Framework.

## 5. Hỗ trợ TestNG bằng lớp nền Spring

TestNG có vòng đời riêng với các annotation như `@BeforeClass`, `@BeforeMethod`, `@AfterMethod`, `@AfterClass`, `@Test` và các tính năng như group, DataProvider. Spring cung cấp tích hợp TestNG thông qua các lớp nền trong package `org.springframework.test.context.testng`.

Lớp thường dùng là `AbstractTestNGSpringContextTests`. Test class kế thừa lớp này để kết nối các mốc vòng đời TestNG với Spring TestContext Framework.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.testng.AbstractTestNGSpringContextTests;
import org.testng.annotations.Test;

import static org.testng.Assert.assertEquals;

@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyTestNgGreetingTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals(greetingService.greet("Lan"), "Hello, Lan");
    }
}
```

Trong ví dụ:

1. TestNG nhận diện phương thức có annotation `org.testng.annotations.Test`.
2. Lớp nền Spring tích hợp TestNG với TestContext Framework.
3. Spring tạo hoặc lấy context theo cấu hình và chuẩn bị test instance.
4. Dependency được inject trước khi test method sử dụng.
5. Các sự kiện trước/sau test được chuyển tới Spring TestContext để listener thực hiện công việc tương ứng.

Khác với JUnit 4, test class không khai báo `@RunWith`. Khác với JUnit Jupiter, nó cũng không đăng ký `@ExtendWith(SpringExtension.class)`. Cơ chế tích hợp ở đây là lớp nền TestNG của Spring.

### Không nhầm annotation TestNG với annotation JUnit

Hai framework có thể dùng tên annotation giống nhau, nhưng chúng thuộc package khác nhau và được test runner xử lý theo cách khác:

| Mục đích | JUnit 4 | TestNG |
|---|---|---|
| Test method | `org.junit.Test` | `org.testng.annotations.Test` |
| Trước mỗi method | `org.junit.Before` | `org.testng.annotations.BeforeMethod` |
| Sau mỗi method | `org.junit.After` | `org.testng.annotations.AfterMethod` |
| Trước class | `org.junit.BeforeClass` | `org.testng.annotations.BeforeClass` |
| Sau class | `org.junit.AfterClass` | `org.testng.annotations.AfterClass` |

Dùng nhầm import có thể khiến test không được runner mong muốn phát hiện hoặc các callback không chạy như dự định. Hãy kiểm tra package của annotation khi bảo trì test cũ, nhất là khi IDE tự động thêm import.

## 6. TestNG với hỗ trợ transaction

Spring cung cấp `AbstractTransactionalTestNGSpringContextTests` cho các bài kiểm thử TestNG cần hỗ trợ transaction. Lớp này kế thừa tích hợp Spring TestContext của TestNG và bổ sung tiện ích cho kiểm thử persistence/JDBC.

Ví dụ:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.testng.AbstractTransactionalTestNGSpringContextTests;
import org.springframework.transaction.annotation.Transactional;
import org.testng.annotations.Test;

import static org.testng.Assert.assertEquals;

@ContextConfiguration(classes = LegacyPersistenceConfig.class)
@Transactional
public class LegacyOrderTest
        extends AbstractTransactionalTestNGSpringContextTests {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    public void findsSavedOrder() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertEquals(
                orderRepository.findById("ORDER-42")
                        .orElseThrow()
                        .getId(),
                "ORDER-42"
        );
    }
}
```

Lớp nền transactional cung cấp hỗ trợ transaction dành cho test theo cơ chế Spring TestContext. Hành vi thực tế còn phụ thuộc vào transaction manager và cấu hình ứng dụng. Với test-managed transaction thông thường, dữ liệu thay đổi được rollback sau test trừ khi có cấu hình yêu cầu commit.

Lớp transactional này cũng cung cấp một số tiện ích JDBC như `jdbcTemplate` và phương thức thực thi SQL script, hữu ích trong các bài kiểm thử persistence. Khi dùng repository JPA, có thể inject repository như ví dụ; khi cần thao tác SQL trực tiếp, các tiện ích JDBC có thể giúp chuẩn bị và kiểm tra dữ liệu.

Không nên mặc định mọi test TestNG đều cần lớp transactional. Nếu test chỉ kiểm tra logic service hoặc controller, `AbstractTestNGSpringContextTests` thường là đủ. Chỉ chọn lớp transactional khi mục tiêu và cấu hình của test thực sự cần transaction.

## 7. Vòng đời khác nhau nhưng cùng dùng TestContext

JUnit 4 và TestNG có các điểm mở rộng vòng đời khác nhau. Adapter của Spring kết nối các điểm đó với những sự kiện chung của TestContext Framework.

| Nhu cầu | JUnit 4 | TestNG |
|---|---|---|
| Chuẩn bị test instance | SpringRunner hoặc Spring rules | Lớp nền Spring TestNG |
| Trước test method | Runner/rule phối hợp với TestContext | Callback TestNG của lớp nền |
| Sau test method | Runner/rule phối hợp với TestContext | Callback TestNG của lớp nền |
| Trước/sau test class | Runner hoặc SpringClassRule | Callback cấp class của lớp nền |
| Dependency injection | TestContext listener | TestContext listener |
| Transaction test-managed | Spring transaction listener | Spring transaction listener |
| Cấu hình context | Annotation Spring TestContext | Annotation Spring TestContext |

Sự khác biệt về thứ tự lifecycle có thể ảnh hưởng đến test nếu nó dựa vào trạng thái được tạo trong `@Before`, `@BeforeMethod`, `@After` hoặc `@AfterMethod`. Khi chuyển framework, không nên chỉ đổi import rồi giả định mọi callback sẽ chạy đúng thứ tự cũ.

Ví dụ, TestNG cho phép cấu hình nhiều nhóm và thứ tự phụ thuộc giữa các method. JUnit 4 có các quy tắc thực thi riêng, còn JUnit Jupiter có lifecycle và cơ chế extension riêng. TestContext Framework có thể giữ nguyên phần lớn cấu hình Spring, nhưng không thể tự chuyển đổi semantics của các annotation thuộc framework cũ.

## 8. Những tính năng Spring có thể được giữ lại trong mã cũ

Khi duy trì JUnit 4 hoặc TestNG, phần lớn cấu hình TestContext có thể được giữ lại nếu adapter tương ứng vẫn được sử dụng và các điều kiện cấu hình được đáp ứng.

| Tính năng | Vai trò trong test |
|---|---|
| `@ContextConfiguration` | Chỉ định cấu hình hoặc nguồn tạo context |
| `@ActiveProfiles` | Chọn profile dùng trong kiểm thử |
| `@TestPropertySource` | Bổ sung property source dành cho test |
| `@Autowired` | Inject bean vào test instance |
| `@DirtiesContext` | Đánh dấu context cần loại khỏi cache |
| `@Transactional` | Kích hoạt test-managed transaction khi cấu hình hỗ trợ |
| `@Rollback`, `@Commit` | Điều chỉnh hành vi kết thúc transaction |
| `@Sql` | Chạy SQL script theo vòng đời kiểm thử |
| `@TestExecutionListeners` | Tùy chỉnh tập listener tham gia test |

Những annotation trên thuộc hệ sinh thái Spring TestContext. Cách chúng được kích hoạt phụ thuộc vào việc test framework đã được tích hợp đúng và annotation được đặt ở phạm vi phù hợp hay chưa.

Nếu một bài test cũ bị lỗi sau khi đổi runner hoặc lớp nền, hãy kiểm tra cả adapter và cấu hình. Việc giữ nguyên `@Transactional` không bảo đảm transaction listener sẽ hoạt động nếu vòng đời Spring TestContext không được kích hoạt.

## 9. Duy trì JUnit 4, TestNG và Jupiter trong cùng repository

Trong một codebase lâu năm, việc chuyển đổi có thể diễn ra theo từng module hoặc nhóm test. Không nhất thiết phải di chuyển tất cả bài kiểm thử trong cùng một lần.

Có thể tổ chức theo nguyên tắc:

- Test JUnit 4 tiếp tục dùng `SpringRunner` hoặc Spring rules.
- TestNG tiếp tục kế thừa lớp nền Spring TestNG.
- Test JUnit Jupiter dùng `SpringExtension` hoặc annotation Spring Boot/JUnit Jupiter tương ứng.
- Mỗi test được thực thi bằng runner hoặc engine phù hợp với framework mà nó sử dụng.

Điều này đòi hỏi cấu hình build nhận diện đúng từng framework. Ví dụ, JUnit 4 có thể chạy trực tiếp qua runner tương ứng hoặc chạy trên JUnit Platform thông qua JUnit Vintage Engine nếu dự án cấu hình engine đó. TestNG thường được thực thi bằng TestNG provider/framework riêng; JUnit Vintage Engine không phải adapter để chạy TestNG.

Với Gradle, một dự án có thể cần các test task hoặc source set riêng tùy cách tổ chức. Một task dùng `useJUnitPlatform()` chạy các engine được đăng ký trên JUnit Platform, chẳng hạn Jupiter và Vintage. Một task dùng `useTestNG()` chạy TestNG. Không nên cấu hình cùng một task như thể hai cơ chế này là một engine duy nhất.

Ví dụ định hướng:

```groovy
dependencies {
    testImplementation "org.springframework:spring-test"

    // JUnit Jupiter
    testImplementation "org.junit.jupiter:junit-jupiter"

    // Chỉ khi còn test JUnit 4 chạy qua JUnit Platform
    testImplementation "junit:junit"
    testRuntimeOnly "org.junit.vintage:junit-vintage-engine"

    // Chỉ khi còn test TestNG
    testImplementation "org.testng:testng"
}

tasks.test {
    useJUnitPlatform()
}

// Có thể tạo task TestNG riêng và giới hạn class được chạy
tasks.register("testNgLegacy", Test) {
    useTestNG()
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
}
```

Đây là ví dụ minh họa cách tách cơ chế chạy; phiên bản dependency, plugin, source set và include/exclude pattern phải khớp với build thực tế. Nếu cùng một thư mục test chứa cả ba loại test, cần cấu hình lọc class hoặc tách source set để tránh một task cố chạy test bằng framework không phù hợp.

Trong Maven, cấu hình Surefire/Failsafe và provider tương ứng cũng cần được kiểm tra theo các framework thực sự có trong classpath. Không nên suy luận rằng chỉ thêm dependency là mọi test framework sẽ tự được phát hiện và thực thi theo đúng ý định.

## 10. Những điểm cần lưu ý khi chạy TestNG song song

TestNG hỗ trợ chạy song song theo method, class, instance hoặc suite tùy cấu hình. Spring TestContext Framework có cơ chế cache context dùng chung trong tiến trình test, vì vậy nhiều test có thể cùng truy cập một `ApplicationContext`.

Điều này không có nghĩa mọi trạng thái test đều tự cô lập. Cần chú ý:

- Bean singleton trong context có thể được nhiều test sử dụng đồng thời.
- Dữ liệu database dùng chung có thể xung đột nếu test tạo cùng mã định danh.
- Test-managed transaction gắn với thread thực thi; hành động chạy trên thread khác có thể không tham gia transaction của test.
- Fixture mutable đặt ở field có thể bị nhiều method chia sẻ tùy lifecycle và cấu hình TestNG.
- Các test phụ thuộc thứ tự hoặc dữ liệu do test trước tạo ra thường khó chạy ổn định song song.

Nếu bật parallel execution, hãy thiết kế dữ liệu riêng cho từng test, tránh thay đổi trạng thái singleton dùng chung và kiểm soát tài nguyên bên ngoài. Nếu test không an toàn khi chạy song song, cấu hình suite hoặc nhóm test phù hợp thay vì kỳ vọng SpringExtension/TestContext tự giải quyết mọi xung đột.

## 11. Lộ trình chuyển JUnit 4 sang JUnit Jupiter

Khi chuyển JUnit 4 sang Jupiter, có thể giữ lại phần lớn ý định kiểm thử và cấu hình Spring, rồi thay đổi lớp tích hợp vòng đời.

| JUnit 4 | JUnit Jupiter |
|---|---|
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` hoặc annotation tổng hợp |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` | `@BeforeEach` |
| `@After` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@Ignore` | `@Disabled` |
| `@Test(expected = ...)` | `assertThrows(...)` |
| `@Rule`, `@ClassRule` | Extension hoặc API Jupiter phù hợp |

Một test JUnit 4:

```java
@RunWith(SpringRunner.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

Có thể chuyển thành Jupiter:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = LegacyTestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

Hoặc dùng `@SpringJUnitConfig(LegacyTestConfig.class)` để kết hợp đăng ký SpringExtension và cấu hình context. Nếu dự án đang dùng `@SpringBootTest` hoặc test slice, annotation Spring Boot tương ứng đã cung cấp tích hợp Jupiter.

Khi chuyển, cần xem lại các điểm sau:

1. Thay import annotation JUnit 4 bằng import Jupiter đúng package.
2. Chuyển các phương thức lifecycle và kiểm tra thứ tự setup/cleanup.
3. Chuyển rules sang extension hoặc API Jupiter tương ứng.
4. Chuyển `@Test(expected)` sang `assertThrows` để kiểm tra ngoại lệ rõ ràng.
5. Xem lại parameterized test, timeout và cách test được phân nhóm.
6. Giữ lại các annotation Spring TestContext khi ý nghĩa của chúng vẫn phù hợp.
7. Cập nhật cấu hình build để chạy Jupiter; giữ Vintage tạm thời nếu còn test JUnit 4.

Không phải mọi JUnit 4 Rule đều có bản thay thế trực tiếp bằng một annotation Jupiter. Hãy xác định hành vi mà rule đang cung cấp, sau đó chọn extension, `@TempDir`, `@RegisterExtension` hoặc cơ chế phù hợp.

## 12. Lộ trình chuyển TestNG sang JUnit Jupiter

Chuyển TestNG sang Jupiter thường cần xem kỹ hơn vì TestNG có các tính năng tổ chức suite, group, data provider và phụ thuộc method riêng.

| TestNG | Cách thể hiện thường gặp trong Jupiter |
|---|---|
| `@Test` | `@Test` |
| `@BeforeMethod` | `@BeforeEach` |
| `@AfterMethod` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@DataProvider` | `@ParameterizedTest` kết hợp `@MethodSource`, `@CsvSource` hoặc nguồn khác |
| TestNG groups | `@Tag` |
| `dependsOnMethods` | Thiết kế lại test độc lập hoặc tách workflow thành test rõ mục tiêu |
| TestNG listeners | Jupiter extensions hoặc cơ chế TestContext tương ứng |

Ví dụ một TestNG test:

```java
@ContextConfiguration(classes = LegacyTestConfig.class)
public class LegacyGreetingTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    public void returnsGreeting() {
        assertEquals(greetingService.greet("Lan"), "Hello, Lan");
    }
}
```

Sau khi chuyển sang Jupiter, có thể bỏ lớp nền TestNG và dùng SpringExtension:

```java
@SpringJUnitConfig(LegacyTestConfig.class)
class GreetingTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
```

TestContext annotations như `@ContextConfiguration`, `@ActiveProfiles` và `@Transactional` có thể được giữ nếu mục tiêu kiểm thử không thay đổi. Phần phải chuyển đổi là cách TestNG cung cấp vòng đời và cách test được tổ chức/chạy.

Đặc biệt, TestNG `dependsOnMethods` có thể che giấu sự phụ thuộc giữa các test. Khi chuyển sang Jupiter, nên xem lại liệu các method có thể trở thành test độc lập với fixture riêng hay nên chuyển chuỗi hành động thành một workflow được kiểm tra trong một test case.

## 13. Những lỗi thường gặp khi bảo trì mã cũ

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JUnit 4 test không dùng được Spring bean | Thiếu `@RunWith(SpringRunner.class)` hoặc rules chưa đăng ký đầy đủ | Kiểm tra adapter JUnit 4 và cấu hình context |
| JUnit 4 class không thể thêm SpringRunner | Đã dùng runner khác | Dùng `SpringClassRule` và `SpringMethodRule` |
| TestNG không inject được dependency | Class không kế thừa lớp tích hợp Spring hoặc cấu hình context thiếu | Kiểm tra `AbstractTestNGSpringContextTests` và `@ContextConfiguration` |
| Test method không được phát hiện | Dùng annotation từ nhầm package | Kiểm tra import JUnit/TestNG và runner |
| JUnit 4 test biến mất sau khi chuyển sang JUnit Platform | Chưa có Vintage Engine hoặc task chưa cấu hình engine | Kiểm tra dependency và test task |
| TestNG test không chạy trong task JUnit Platform | Nhầm TestNG với một JUnit Platform engine mặc định | Cấu hình TestNG runner/task riêng |
| Transaction không rollback như mong đợi | Thiếu transaction manager, annotation hoặc listener phù hợp | Kiểm tra cấu hình transaction và test integration |
| Test chạy khác kết quả khi song song | Dùng chung trạng thái, dữ liệu hoặc tài nguyên | Cô lập fixture và kiểm soát concurrency |
| Test thất bại sau khi đổi framework | Thứ tự lifecycle hoặc semantics annotation khác nhau | Đối chiếu callback cũ và mới, viết lại setup/cleanup |

Khi debug, hãy phân loại lỗi theo tầng:

- **Tầng build/test runner:** test có được phát hiện và chạy bằng framework mong muốn không?
- **Tầng adapter:** SpringRunner, Spring rules hoặc TestNG base class có được kích hoạt không?
- **Tầng TestContext:** context có được tạo, cache và chuẩn bị test instance đúng không?
- **Tầng listener:** dependency injection, transaction hoặc SQL script có được xử lý không?
- **Tầng nghiệp vụ:** test method có nhận đúng dữ liệu và kiểm tra đúng hành vi không?

Phân loại theo tầng giúp tránh sửa logic service khi vấn đề thực ra là test runner không kích hoạt Spring.

## 14. Cách duy trì mã cũ trong giai đoạn chuyển đổi

Một repository có thể duy trì nhiều test framework trong một thời gian nếu ranh giới được tổ chức rõ ràng:

1. Ghi nhận framework mà từng test class sử dụng.
2. Giữ adapter tương ứng cho các class chưa chuyển đổi.
3. Cấu hình task/provider để mỗi loại test chạy bằng đúng framework.
4. Không trộn annotation JUnit 4, Jupiter và TestNG trong cùng một test class.
5. Chuyển đổi theo nhóm nhỏ, bắt đầu từ test độc lập và dễ xác định hành vi.
6. Sau mỗi đợt chuyển, chạy test bằng engine mới và xác nhận các listener/transaction/context hoạt động như trước.
7. Chỉ gỡ dependency runner cũ hoặc Vintage/TestNG khi không còn test cần chúng.

Không cần chuyển đổi chỉ để thay đổi cú pháp. Giá trị của việc chuyển đổi nằm ở khả năng thống nhất nền tảng kiểm thử, tận dụng extension API, parameterized tests và các tính năng Jupiter, đồng thời giảm gánh nặng duy trì nhiều runner. Nếu một bộ test cũ vẫn ổn định và có chi phí chuyển đổi lớn, có thể giữ nó trong adapter hiện tại trong khi code mới dùng Jupiter.

Spring TestContext Framework giúp việc chuyển đổi dễ kiểm soát hơn vì nhiều khái niệm cấu hình và hành vi kiểm thử được dùng chung. Khi hiểu rằng SpringRunner, Spring rules, TestNG base classes và SpringExtension là các cách tích hợp khác nhau vào cùng TestContext core, nhóm phát triển có thể bảo tồn các bài test cũ, chạy nhiều framework có chủ đích và chuyển dần sang JUnit Jupiter mà vẫn giữ được ý nghĩa của kiểm thử.

