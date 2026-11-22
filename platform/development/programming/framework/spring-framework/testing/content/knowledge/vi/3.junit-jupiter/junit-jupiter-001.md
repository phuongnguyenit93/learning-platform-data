# JUnit Platform, Jupiter và công cụ thực thi kiểm thử

Trong một dự án Java, viết các phương thức kiểm thử chỉ là một phần của quy trình. Cần có thành phần tìm ra test nào cần chạy, gọi đúng framework để thực thi chúng, ghi nhận kết quả và chuyển kết quả đó cho IDE hoặc hệ thống build. Hệ sinh thái JUnit tách các trách nhiệm này thành **JUnit Platform**, **JUnit Jupiter** và các công cụ thực thi tích hợp với Platform.

Khi kiểm thử ứng dụng Spring, sự phân chia này giúp ta hiểu vì sao một lớp có `@Test` nhưng không được chạy, vì sao IDE chạy được còn Gradle không tìm thấy test, hoặc vì sao `@Autowired` trong test chỉ hoạt động khi Spring Extension được đăng ký. Nắm được kiến trúc cũng giúp chọn đúng dependency và cấu hình cho từng môi trường.

## 1. Ba thành phần chính của hệ sinh thái JUnit

JUnit Platform, Jupiter và các công cụ chạy test có liên quan nhưng không phải là một thành phần duy nhất.

| Thành phần | Vai trò | Ví dụ API hoặc thành phần |
|---|---|---|
| JUnit Platform | Nền tảng discovery và execution; cung cấp cơ chế để công cụ tìm và chạy test thông qua các TestEngine | `Launcher`, `TestEngine`, `TestPlan`, `TestExecutionListener` |
| JUnit Jupiter | Mô hình lập trình test hiện đại: annotation, assertion, extension và quy tắc vòng đời | `@Test`, `@BeforeEach`, `@ParameterizedTest`, `@ExtendWith` |
| Jupiter Engine | Bộ máy triển khai `TestEngine` để Platform khám phá và thực thi test viết theo Jupiter | `junit-jupiter-engine` |
| Công cụ thực thi | Tích hợp với Platform để người dùng chạy test, chọn phạm vi và xem báo cáo | Gradle, Maven Surefire, IDE, Console Launcher |

Có thể hình dung luồng phụ thuộc như sau:

```text
Test code dùng JUnit Jupiter API
             |
             v
       Jupiter Engine  ---------+
             ^                  |
             |                  v
       JUnit Platform <---- Launcher API
             ^                  ^
             |                  |
      IDE / Gradle / Maven / Console Launcher
```

Sơ đồ nhấn mạnh rằng công cụ thực thi yêu cầu Platform chạy test, còn Platform giao việc khám phá và thực thi cho engine phù hợp. Jupiter API là cách lập trình test; Jupiter Engine là thành phần thực sự diễn giải mô hình đó trong Platform.

### 1.1. JUnit Platform

JUnit Platform là lớp nền cho các framework kiểm thử chạy trên JVM. Platform không quy định rằng mọi test phải dùng annotation `@Test` của Jupiter. Thay vào đó, nó cung cấp một hợp đồng chung để các framework đăng ký engine và để công cụ bên ngoài khám phá, chạy và nhận kết quả.

Các thành phần quan trọng gồm:

- **TestEngine:** SPI (Service Provider Interface) mà một framework hoặc engine triển khai. Engine chịu trách nhiệm nhận yêu cầu discovery, tìm test thuộc mô hình của mình và thực thi chúng.
- **Launcher:** API mà IDE, build tool hoặc chương trình tùy chỉnh dùng để gửi yêu cầu khám phá và chạy test.
- **LauncherDiscoveryRequest:** mô tả yêu cầu cần thực hiện, bao gồm selector và filter.
- **TestPlan:** biểu diễn kế hoạch test đã được khám phá, gồm các node và quan hệ cha-con.
- **TestIdentifier:** định danh một node trong test plan, có thể là container hoặc test leaf.
- **TestExecutionListener:** nhận các sự kiện trong quá trình chạy, chẳng hạn bắt đầu, thành công, thất bại, bị bỏ qua hoặc kết thúc.

Platform cũng có các thành phần để hỗ trợ engine được phát hiện qua cơ chế service loading. Nhờ đó, công cụ thực thi có thể làm việc với nhiều engine trong cùng một lần chạy mà không cần hiểu chi tiết annotation riêng của từng framework.

### 1.2. JUnit Jupiter

JUnit Jupiter là mô hình viết test thế hệ mới của JUnit. Nó cung cấp:

- Annotation xác định test và các callback vòng đời.
- Assertion và assumption để kiểm tra điều kiện.
- Test tham số, test lặp, test lồng nhau và dynamic test.
- Extension API để tích hợp dependency injection, quản lý tài nguyên hoặc hành vi bổ sung.
- Cơ chế hiển thị tên, gắn tag, vô hiệu hóa test và cấu hình vòng đời instance.

Các annotation như `@Test`, `@BeforeEach` và `@ParameterizedTest` thuộc package `org.junit.jupiter.api` hoặc các package con của Jupiter. Chúng mô tả test theo mô hình Jupiter; Platform không tự diễn giải những annotation này nếu không có Jupiter Engine.

### 1.3. Jupiter Engine và các engine khác

Jupiter Engine là triển khai `TestEngine` dành cho test Jupiter. Khi Platform nhận yêu cầu chạy test, engine này tìm các lớp và phương thức theo quy tắc Jupiter rồi thực thi chúng.

Platform không giới hạn ở một engine. Ví dụ:

- **Jupiter Engine** chạy test dùng JUnit Jupiter.
- **Vintage Engine** cho phép Platform chạy các test JUnit 3 và JUnit 4 cũ trong giai đoạn chuyển đổi.
- Các framework khác có thể cung cấp engine riêng để tích hợp với Platform.

Nếu dự án còn test JUnit 4, việc thêm Jupiter API không tự động khiến các test cũ chạy bằng Jupiter. Dự án cần engine tương ứng (chẳng hạn Vintage) và cấu hình tương thích. Với dự án mới, nên thống nhất dùng Jupiter để tránh phải duy trì nhiều mô hình test nếu không có nhu cầu chuyển đổi.

## 2. Quá trình khám phá và thực thi test

Khi chạy test từ IDE hoặc build tool, thường có hai giai đoạn lớn: **discovery** và **execution**.

### 2.1. Discovery — tìm test cần chạy

Đầu tiên, công cụ thực thi tạo một yêu cầu khám phá. Yêu cầu có thể chỉ định:

- Package cần quét.
- Một lớp hoặc một phương thức cụ thể.
- Một classpath root.
- Engine được phép hoặc bị loại trừ.
- Tag cần bao gồm hoặc loại trừ.
- Các filter khác do công cụ hỗ trợ.

Các selector cho biết phạm vi hoặc đối tượng mà công cụ muốn tìm; filter thu hẹp những gì được chọn. Platform chuyển yêu cầu này đến các engine phù hợp. Mỗi engine khám phá test của mình và trả về cây descriptor mô tả cấu trúc test.

Với Jupiter, engine đọc annotation và cấu trúc lớp để nhận biết test method, lifecycle method, nested class, parameterized test và các thành phần liên quan. Kết quả được hợp nhất thành `TestPlan` để công cụ có thể hiển thị cây test trước hoặc trong khi chạy.

### 2.2. Execution — thực thi test

Sau discovery, Launcher yêu cầu các engine thực thi test đã tìm thấy. Trong quá trình chạy, Platform phát sự kiện đến listener. Công cụ thực thi dùng những sự kiện này để cập nhật trạng thái trong IDE, ghi báo cáo XML, thống kê thời gian và đánh dấu test thất bại.

Luồng tổng quát:

1. Người dùng chọn chạy test trong IDE hoặc build tool.
2. Công cụ tạo `LauncherDiscoveryRequest` với selector và filter phù hợp.
3. Platform tìm các `TestEngine` khả dụng và yêu cầu từng engine khám phá test.
4. Các engine trả về mô tả test; Platform tạo `TestPlan`.
5. Launcher yêu cầu engine thực thi các node đã chọn.
6. Engine chạy từng container/test, áp dụng lifecycle và extension theo framework.
7. Platform phát sự kiện thực thi; công cụ thu thập kết quả và tạo báo cáo.

Một test có thể không được chạy dù source code đã biên dịch thành công. Ví dụ, engine tương ứng chưa có trên runtime classpath, filter loại test đó, tên lớp không khớp quy tắc discovery của công cụ, hoặc test được đánh dấu disabled. Vì vậy, cần phân biệt lỗi biên dịch, lỗi discovery và lỗi trong lúc execution.

## 3. Mô hình test của JUnit Jupiter

Jupiter hỗ trợ nhiều loại test và callback. Những annotation dưới đây là nhóm thường dùng khi xây dựng bộ kiểm thử cho ứng dụng Spring.

| Annotation | Ý nghĩa |
|---|---|
| `@Test` | Đánh dấu một test thông thường |
| `@ParameterizedTest` | Chạy cùng một test với nhiều bộ tham số |
| `@RepeatedTest` | Chạy một test nhiều lần theo số lần chỉ định |
| `@TestFactory` | Tạo dynamic test hoặc dynamic container tại thời điểm chạy |
| `@TestTemplate` | Tạo các lần thực thi theo một provider và extension tương ứng |
| `@BeforeEach` / `@AfterEach` | Chạy trước/sau mỗi test method tương ứng |
| `@BeforeAll` / `@AfterAll` | Chạy một lần trước/sau tất cả test trong container |
| `@Nested` | Tổ chức nhóm test lồng nhau bên trong một lớp test |
| `@DisplayName` | Đặt tên hiển thị dễ đọc cho test hoặc container |
| `@Tag` | Gắn nhãn để chọn hoặc loại trừ một nhóm test |
| `@Disabled` | Vô hiệu hóa test hoặc container |
| `@ExtendWith` | Đăng ký một hoặc nhiều extension |
| `@TestInstance` | Chọn vòng đời instance của lớp test |
| `@TempDir` | Cung cấp thư mục tạm cho test |
| `@Timeout` | Đặt giới hạn thời gian cho một test hoặc container |

### 3.1. Cấu trúc một test class

Ví dụ cơ bản:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PriceCalculatorTest {

    private PriceCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new PriceCalculator();
    }

    @Test
    @DisplayName("applies the discount to the original price")
    void appliesDiscount() {
        var result = calculator.discount(100, 10);

        assertEquals(90, result);
    }

    @AfterEach
    void tearDown() {
        calculator = null;
    }
}
```

Các test class và test method của Jupiter có thể dùng mức truy cập package-private. Test method thông thường không phải `static`, trả về `void` và không nhận tham số tùy ý. Tham số chỉ được phép khi được cung cấp bởi parameterized test, test template hoặc một `ParameterResolver` phù hợp. Test class không được là `private` hay `abstract`.

### 3.2. Vòng đời mặc định

Mặc định, Jupiter dùng vòng đời instance `PER_METHOD`: mỗi test method có một instance mới của test class. Điều này hạn chế trạng thái mutable được chia sẻ giữa các test.

Thứ tự tổng quát cho một test method:

```text
Tạo test instance
      |
      v
@BeforeEach (theo thứ tự kế thừa phù hợp)
      |
      v
Test method
      |
      v
@AfterEach
      |
      v
Kết thúc instance
```

`@BeforeAll` và `@AfterAll` chạy một lần cho container. Với vòng đời `PER_METHOD`, các method này thông thường phải là `static`. Nếu khai báo `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, chúng có thể là instance method:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedFixtureTest {

    private ExpensiveFixture fixture;

    @BeforeAll
    void createFixtureOnce() {
        fixture = ExpensiveFixture.open();
    }

    @AfterAll
    void closeFixtureOnce() {
        fixture.close();
    }
}
```

`PER_CLASS` hữu ích khi fixture khởi tạo tốn kém hoặc cần chia sẻ giữa các method. Tuy nhiên, các test có thể ảnh hưởng lẫn nhau nếu cùng thay đổi trạng thái. Chỉ dùng khi việc chia sẻ đó được kiểm soát và việc dọn dẹp được thực hiện rõ ràng.

### 3.3. Parameterized test

Parameterized test cho phép mô tả một quy tắc và nhiều dữ liệu đại diện. Nguồn tham số có thể đến từ `@ValueSource`, `@NullSource`, `@EmptySource`, `@CsvSource`, `@MethodSource` hoặc các nguồn tùy chỉnh.

```java
@ParameterizedTest
@ValueSource(strings = {"", "   "})
void rejectsBlankEmail(String email) {
    assertThrows(IllegalArgumentException.class,
            () -> registrationService.register(email, "valid-password-123"));
}
```

Các annotation nguồn tham số thường dùng nằm trong package `org.junit.jupiter.params` và `org.junit.jupiter.params.provider`. Khi chỉ thêm `junit-jupiter-api` mà thiếu module tham số, các annotation như `@ParameterizedTest` sẽ không có trên classpath. Dependency tổng hợp `junit-jupiter` thường giúp đưa cả phần API, parameterized test và engine vào cấu hình test.

### 3.4. Nested test và display name

`@Nested` giúp nhóm các trường hợp theo trạng thái hoặc ngữ cảnh. Ví dụ, một lớp `OrderServiceTest` có thể chứa nhóm `WhenOrderIsPending` và `WhenOrderIsShipped`, mỗi nhóm có fixture và test riêng. Các nested class không được khai báo `static` theo mô hình Jupiter.

`@DisplayName` giúp báo cáo dễ hiểu hơn tên method kỹ thuật. Tuy vậy, nên giữ tên method có ý nghĩa vì tên đó hữu ích khi tìm kiếm, lọc và đọc log.

### 3.5. Tags và assumptions

`@Tag` gắn nhãn cho test, chẳng hạn `unit`, `integration`, `database` hoặc `slow`. Công cụ thực thi có thể chọn hoặc loại trừ test theo tag. Một test có thể mang nhiều tag.

Assumption khác assertion. Assertion thất bại có nghĩa hành vi được kiểm tra không đáp ứng mong đợi. Assumption không được thỏa mãn có thể khiến test bị bỏ qua vì điều kiện môi trường hoặc tiền đề của kịch bản không phù hợp. Không nên dùng assumption để che giấu một lỗi nghiệp vụ cần được phát hiện.

## 4. Extension API và tích hợp Spring TestContext

Một điểm quan trọng của Jupiter là extension model. Extension bổ sung hành vi vào vòng đời test mà không cần kế thừa một base class duy nhất.

Extension có thể tham gia vào các điểm mở rộng như:

- Tạo và xử lý test instance.
- Thực thi callback trước/sau container hoặc test method.
- Cung cấp tham số cho test method.
- Xử lý exception.
- Can thiệp vào điều kiện thực thi hoặc đăng ký thêm hành vi test.

Có thể đăng ký extension bằng `@ExtendWith`, qua cấu hình đăng ký tự động hoặc bằng API đăng ký phù hợp. Jupiter cung cấp một số extension tích hợp, ví dụ `@TempDir` và `@Timeout` được hỗ trợ bởi cơ chế mở rộng của framework.

### 4.1. SpringExtension là cầu nối giữa Jupiter và Spring

Spring Framework cung cấp `SpringExtension` trong Spring TestContext Framework. Extension này tích hợp vòng đời Jupiter với `TestContextManager`, nhờ đó test có thể sử dụng ApplicationContext, dependency injection, quản lý transaction và các tính năng kiểm thử Spring khác.

Có hai cách khai báo phổ biến:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class AccountServiceTest {
    // test fields và test methods
}
```

Hoặc dùng annotation kết hợp của Spring:

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsServiceFromApplicationContext() {
        assertNotNull(accountService);
    }
}
```

`@SpringJUnitConfig` kết hợp khả năng đăng ký `SpringExtension` với cấu hình ApplicationContext. Khi test chạy, Spring extension phối hợp với TestContext Framework để chuẩn bị test instance và thực hiện các callback liên quan. Vì vậy, `@Autowired` trong test được Spring xử lý thay vì do Jupiter tự động hiểu.

### 4.2. Spring test annotations

Khi dùng SpringExtension, test có thể phối hợp với các annotation của Spring TestContext như:

- `@ContextConfiguration`: chỉ định nguồn cấu hình hoặc lớp cấu hình cho ApplicationContext.
- `@WebAppConfiguration`: yêu cầu cấu hình web application context trong những kịch bản phù hợp.
- `@TestPropertySource`: cung cấp property riêng cho test context.
- `@ActiveProfiles`: chọn profile hoạt động khi tạo context.
- `@DirtiesContext`: đánh dấu context cần được loại khỏi cache vì test đã làm thay đổi trạng thái dùng chung.
- `@Transactional`: chạy test trong transaction do Spring TestContext quản lý khi cấu hình hỗ trợ.
- `@Sql`: thực thi script SQL trong các giai đoạn được cấu hình.

Những annotation này thuộc Spring TestContext, không phải annotation gốc của JUnit Jupiter. Chúng hoạt động trong test Jupiter khi SpringExtension được đăng ký và các điều kiện cấu hình tương ứng được đáp ứng.

Với Spring Boot, `@SpringBootTest` thuộc Spring Boot Test và tạo ApplicationContext theo cấu hình ứng dụng Boot. Đây là lựa chọn ở phạm vi ứng dụng; nó không thay thế vai trò của Jupiter Engine hay JUnit Platform. Các test slice như `@WebMvcTest` và `@DataJpaTest` cũng là annotation của Spring Boot, thường được dùng để chỉ nạp một phần cấu hình phục vụ test.

### 4.3. Khi nào cần SpringExtension?

Không phải mọi test trong dự án Spring đều cần nạp Spring context.

- Nếu chỉ kiểm tra thuật toán hoặc quy tắc thuần Java, JUnit Jupiter cùng Mockito có thể đủ.
- Nếu cần kiểm tra bean wiring, `@Autowired`, profile, property, lifecycle hoặc transaction của Spring, hãy dùng SpringExtension.
- Nếu cần kiểm tra cấu hình web, persistence hoặc toàn bộ ứng dụng, chọn test slice hoặc `@SpringBootTest` theo phạm vi cần xác minh.

Việc nạp context có chi phí khởi tạo và có thể làm test phụ thuộc cấu hình môi trường. Chỉ bật Spring TestContext khi hành vi đang kiểm thử thực sự cần các khả năng đó.

## 5. Các công cụ thực thi JUnit Platform

JUnit Platform cung cấp Launcher API; các công cụ tích hợp API này để chạy test trong môi trường khác nhau. Cùng một test Jupiter có thể được chạy từ IDE, Gradle, Maven hoặc Console Launcher nếu classpath và cấu hình phù hợp.

### 5.1. IDE

Các IDE Java phổ biến có thể chạy test Jupiter trực tiếp từ editor hoặc test explorer. IDE thường:

- Phát hiện test class và method trong source set.
- Tạo yêu cầu chạy cho một method, một class, package hoặc toàn bộ test suite.
- Hiển thị cây test và trạng thái từng node.
- Cho phép debug, chạy lại test thất bại và xem stack trace.

IDE có thể dùng launcher tích hợp hoặc cấu hình runner riêng. Vì vậy, việc IDE chạy được test chưa chứng minh cấu hình Gradle/Maven đã đầy đủ. Khi CI không tìm thấy test, hãy kiểm tra cấu hình build độc lập với thiết lập của IDE.

### 5.2. Gradle

Gradle cần được cấu hình để dùng JUnit Platform. Với Groovy DSL, cấu hình thường có dạng:

```groovy
def junitVersion = providers.gradleProperty("junitVersion").get()

dependencies {
    testImplementation(platform("org.junit:junit-bom:$junitVersion"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Ví dụ giả định dự án khai báo property `junitVersion` trong `gradle.properties` hoặc cung cấp qua cấu hình Gradle. Hãy chọn một phiên bản JUnit BOM tương thích với Java và các dependency của dự án. BOM giúp đồng bộ phiên bản các artifact JUnit Platform/Jupiter để tránh kết hợp các module không tương thích.

Vai trò của từng cấu hình:

- `junit-bom` quản lý phiên bản nhất quán cho các artifact JUnit.
- `junit-jupiter` là dependency tổng hợp thường dùng để đưa API, parameterized test và engine Jupiter vào cấu hình test.
- `junit-platform-launcher` cung cấp Launcher API cho công cụ thực thi; với Gradle hiện đại, khai báo runtime này giúp classpath launcher rõ ràng và tương thích với tích hợp chạy test.
- `useJUnitPlatform()` yêu cầu task `Test` dùng JUnit Platform thay cho cơ chế JUnit 4 mặc định cũ.

Chạy toàn bộ test:

```bash
./gradlew test
```

Chạy một test class:

```bash
./gradlew test --tests "com.example.account.AccountServiceTest"
```

Chạy một test method bằng bộ lọc của Gradle:

```bash
./gradlew test --tests "com.example.account.AccountServiceTest.rejectsDuplicateEmail"
```

Có thể lọc theo tag ở cấu hình task:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform {
        includeTags("unit")
        excludeTags("slow", "external")
    }
}
```

Khi cấu hình tag ở Gradle, hãy bảo đảm tag được gắn trong test và không có cấu hình khác loại trừ nhầm test cần chạy. Tên task cũng quan trọng: `test` thường chạy source set test chính, còn các source set hoặc task integration riêng có thể có cấu hình và classpath khác.

### 5.3. Maven Surefire và Failsafe

Trong Maven, Maven Surefire Plugin thường chạy unit test ở phase `test`. Với các phiên bản plugin hiện đại, Surefire tích hợp JUnit Platform để chạy Jupiter Engine. Cấu hình cần có dependency Jupiter và phiên bản Surefire tương thích với thế hệ JUnit được chọn.

Ví dụ cấu trúc dependency dùng JUnit BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`junit.version` cần được khai báo trong phần properties của dự án hoặc được quản lý bởi parent/BOM cấp cao hơn. Đồng thời cần dùng phiên bản Maven Surefire Plugin tương thích với JUnit Platform và Java mà dự án đang sử dụng. Không nên sao chép một phiên bản plugin cũ từ dự án khác mà chưa kiểm tra khả năng hỗ trợ.

Chạy test bằng Maven:

```bash
mvn test
```

Chỉ chạy một lớp test:

```bash
mvn -Dtest=AccountServiceTest test
```

Surefire phù hợp cho unit test chạy trong phase test. Với integration test cần chạy ở giai đoạn verify và có quy ước đặt tên riêng, Maven Failsafe Plugin thường được dùng để tách vòng đời integration test khỏi unit test. Việc tách task giúp pipeline có thể chạy nhanh unit test trước, sau đó mới chạy nhóm integration test cần database, container hoặc dịch vụ phụ trợ.

### 5.4. JUnit Platform Console Launcher

Console Launcher là công cụ dòng lệnh chạy test thông qua JUnit Platform. Nó hữu ích khi cần chạy test ngoài IDE hoặc build tool, thử nghiệm classpath, kiểm tra discovery độc lập hoặc tạo một bước chạy test đơn giản trong môi trường JVM.

Artifact `junit-platform-console-standalone` đóng gói Console Launcher cùng các thành phần cần thiết của Platform. Sau khi có file JAR tương ứng với phiên bản JUnit của dự án và classpath chứa test cùng dependency của ứng dụng, có thể quét classpath để tìm test Jupiter:

```bash
java -jar junit-platform-console-standalone.jar execute \
  --class-path "build/classes/java/test;build/classes/java/main" \
  --scan-class-path \
  --include-engine junit-jupiter
```

Đường dẫn classpath trong ví dụ cần được điều chỉnh theo hệ điều hành, build output và dependency thực tế. Trên Windows, dấu phân cách classpath là `;`; trên Linux/macOS là `:`. Nếu test phụ thuộc Spring, Mockito hoặc thư viện khác, các JAR tương ứng cũng phải có mặt trên classpath. Chỉ thêm thư mục class đã biên dịch mà thiếu dependency thì test có thể được tìm thấy nhưng thất bại khi khởi tạo.

Console Launcher hỗ trợ các selector và filter để giới hạn phạm vi chạy. Tùy phiên bản, cú pháp lệnh và tùy chọn có thể thay đổi; hãy dùng `--help` của đúng phiên bản Console Launcher được cài trong dự án để kiểm tra cú pháp hiện hành.

### 5.5. Launcher API cho công cụ tùy chỉnh

Trong trường hợp cần xây dựng một test runner, plugin hoặc công cụ báo cáo riêng, có thể dùng Launcher API trực tiếp. Ví dụ rút gọn:

```java
import static org.junit.platform.engine.discovery.DiscoverySelectors.selectPackage;
import static org.junit.platform.launcher.EngineFilter.includeEngines;

import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

LauncherDiscoveryRequest request = LauncherDiscoveryRequestBuilder.request()
        .selectors(selectPackage("com.example"))
        .filters(includeEngines("junit-jupiter"))
        .build();

Launcher launcher = LauncherFactory.create();
launcher.execute(request);
```

Ví dụ chỉ thể hiện cách tạo request, chọn package và giới hạn engine. Một công cụ thực tế thường đăng ký `TestExecutionListener` để nhận sự kiện, lưu kết quả, định dạng báo cáo và xử lý lỗi. Nếu chỉ cần chạy test thông thường, nên để Gradle, Maven hoặc IDE quản lý Launcher thay vì tự viết runner.

## 6. Lựa chọn phạm vi test bằng selector, filter và tag

Ba khái niệm này giúp kiểm soát tập test được chạy:

- **Selector** chỉ ra nơi hoặc đối tượng cần khám phá, ví dụ package, class, method hoặc classpath root.
- **Filter** loại bỏ các node không thỏa điều kiện, ví dụ engine hoặc tag.
- **Tag** là nhãn do người viết test gắn vào container/test để phân nhóm theo mục đích.

Ví dụ:

```java
@Tag("unit")
class PriceCalculatorTest {
    @Test
    void calculatesDiscount() {
        // ...
    }
}

@Tag("integration")
class AccountRepositoryTest {
    @Test
    void persistsAccount() {
        // ...
    }
}
```

Nhóm tag nên mô tả đặc điểm vận hành có ích cho pipeline, chẳng hạn `unit`, `integration`, `slow`, `database` hoặc `external`. Tránh tạo quá nhiều tag trùng nghĩa hoặc dùng tên tag không nhất quán giữa module.

Không nên dựa hoàn toàn vào tag để quyết định test có an toàn khi chạy song song hay không. Test được gắn `unit` vẫn có thể chia sẻ file hoặc trạng thái static; test `integration` có thể được cô lập tốt. Việc chọn test phải phù hợp với điều kiện môi trường và tài nguyên mà test sử dụng.

## 7. Thực thi song song và tính độc lập

JUnit Jupiter mặc định không bật thực thi song song. Có thể cấu hình parallel execution thông qua file `junit-platform.properties` đặt trên test classpath:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Khi bật chạy song song, nhiều test hoặc container có thể được thực thi đồng thời theo cấu hình. Điều này có thể rút ngắn thời gian chạy, nhưng chỉ an toàn khi test độc lập và tài nguyên được quản lý đúng.

Trước khi bật parallel execution, cần xem xét:

- Test có sửa cùng một bản ghi, file, thư mục hoặc dữ liệu dùng chung không?
- Database có schema hoặc transaction đủ cô lập giữa các test không?
- Test có dùng port cố định, server dùng chung hoặc tài nguyên singleton không?
- Các fixture mutable có bị chia sẻ giữa nhiều test instance không?
- Các extension và thư viện mock có an toàn khi nhiều test cùng sử dụng không?

Với Spring TestContext, ApplicationContext có thể được cache và dùng lại giữa các test có cấu hình tương thích. Test làm thay đổi trạng thái singleton trong context hoặc dữ liệu dùng chung cần được cô lập và dọn dẹp rõ ràng. `@DirtiesContext` có thể yêu cầu Spring loại context khỏi cache trong trường hợp test đã làm thay đổi trạng thái context; không nên dùng annotation này thay cho việc quản lý dữ liệu test đúng cách.

## 8. Báo cáo và sự kiện thực thi

Platform phát các sự kiện như bắt đầu test, test thành công, thất bại, bị bỏ qua và kết thúc container. Công cụ thực thi chuyển các sự kiện đó thành thông tin phù hợp với môi trường:

- IDE cập nhật trạng thái trong test explorer, hiển thị thời gian và stack trace.
- Gradle tạo báo cáo test và dữ liệu phục vụ build scan hoặc CI.
- Maven Surefire ghi báo cáo XML và báo cáo dạng văn bản.
- Console Launcher in kết quả ra terminal.
- Công cụ tùy chỉnh có thể dùng `TestExecutionListener` để ghi log, thu thập metrics hoặc xuất định dạng riêng.

Khi đọc báo cáo, cần phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| Successful | Test thực thi và tất cả assertion đều đạt |
| Failed | Test được thực thi nhưng có assertion hoặc exception làm thất bại |
| Aborted | Test bị hủy theo cơ chế như assumption hoặc điều kiện thực thi |
| Skipped | Test không được chạy theo quyết định của engine hoặc công cụ, ví dụ bị disabled hoặc bị filter loại bỏ |

Tên trạng thái cụ thể hiển thị có thể khác giữa IDE và build tool. Khi cần chẩn đoán, hãy xem cả số test được tìm thấy, số test được thực thi, số bị bỏ qua và nguyên nhân trong log; chỉ nhìn dòng “BUILD SUCCESSFUL” có thể bỏ qua việc không có test nào thực sự chạy.

## 9. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| IDE chạy được nhưng Gradle báo không có test | Task chưa gọi `useJUnitPlatform()`, engine thiếu hoặc test nằm ngoài source set | Kiểm tra cấu hình task, dependency runtime và đường dẫn `src/test` |
| Maven biên dịch test nhưng không thực thi Jupiter | Surefire quá cũ hoặc dependency engine không có trên test runtime | Kiểm tra phiên bản Surefire, JUnit BOM và dependency `junit-jupiter` |
| `@ParameterizedTest` không được nhận diện | Thiếu Jupiter Params hoặc đang dùng dependency chỉ có API cơ bản | Thêm `junit-jupiter` aggregate hoặc `junit-jupiter-params` tương thích |
| `@Autowired` trong test là `null` hoặc test không có Spring context | SpringExtension chưa đăng ký hoặc cấu hình context không đúng | Dùng `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`, hoặc `@SpringJUnitConfig` |
| Test JUnit 4 không chạy sau khi chuyển sang Platform | Chưa thêm Vintage Engine hoặc test vẫn phụ thuộc runner JUnit 4 | Kiểm tra engine và kế hoạch chuyển đổi sang Jupiter |
| Test không xuất hiện trong báo cáo | Selector, tag filter hoặc quy tắc include/exclude của công cụ loại test | Chạy một class cụ thể, xem log discovery và rà lại tag/filter |
| `NoSuchMethodError` hoặc lỗi tương thích runtime | Các artifact JUnit Platform/Jupiter lệch phiên bản | Dùng BOM và kiểm tra dependency tree để đồng bộ các module |
| Console Launcher tìm thấy test nhưng không khởi tạo được | Classpath thiếu dependency ứng dụng hoặc test runtime | Bổ sung các JAR cần thiết và kiểm tra phiên bản JDK |

Một quy trình chẩn đoán hữu ích là kiểm tra theo thứ tự: test source có biên dịch không, engine có trên runtime classpath không, công cụ có dùng Platform không, selector/filter có chọn test không, sau đó mới xem exception phát sinh trong quá trình thực thi.

## 10. Quy trình thiết lập và chạy test trong dự án Spring

Khi thêm JUnit Jupiter vào một module Spring, có thể thực hiện theo trình tự sau:

1. **Xác định build tool và phiên bản Java.** Kiểm tra Gradle hoặc Maven wrapper, JDK được dùng khi biên dịch và chạy test.
2. **Chọn phiên bản JUnit đồng bộ.** Dùng JUnit BOM hoặc dependency management sẵn có của dự án để tránh lệch phiên bản Platform, Jupiter API và engine.
3. **Thêm engine và API.** Dùng dependency `junit-jupiter` hoặc các artifact cần thiết riêng lẻ; bảo đảm engine có trên test runtime classpath.
4. **Bật JUnit Platform trong build.** Với Gradle, cấu hình `useJUnitPlatform()`; với Maven, dùng Surefire tương thích.
5. **Chạy một test nhỏ.** Xác minh công cụ tìm thấy và thực thi một test Jupiter cơ bản.
6. **Tích hợp Spring khi cần.** Đăng ký `SpringExtension` hoặc dùng `@SpringJUnitConfig`; cấu hình context và dependency cần thiết.
7. **Phân loại test.** Dùng tag hoặc source set/task riêng cho unit test và integration test.
8. **Đọc báo cáo của build tool.** Kiểm tra số test discovered, executed, skipped và failed để xác nhận pipeline đang chạy đúng tập test.

Một ví dụ test Spring Framework tối giản:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(classes = AccountTestConfiguration.class)
class AccountServiceContextTest {

    @Autowired
    private AccountService accountService;

    @Test
    void injectsServiceFromSpringContext() {
        assertNotNull(accountService);
    }
}
```

Ví dụ giả định `AccountTestConfiguration` khai báo bean `AccountService` cùng các dependency cần thiết. Test này xác minh việc tích hợp Jupiter với Spring TestContext và khả năng inject bean. Để kiểm tra nghiệp vụ, cần gọi hành vi của service với dữ liệu đã chuẩn bị rồi assertion kết quả cụ thể.

## 11. Nguyên tắc chọn công cụ phù hợp

Trong công việc hằng ngày, nên dùng IDE để phát triển và debug từng test; dùng Gradle hoặc Maven wrapper làm chuẩn thực thi trong local và CI vì đây là cấu hình được chia sẻ trong repository; dùng Console Launcher khi cần kiểm tra độc lập discovery/classpath; chỉ dùng Launcher API trực tiếp khi thật sự xây dựng công cụ tích hợp riêng.

Điều quan trọng là mọi môi trường phải chạy cùng một mô hình test và bộ dependency tương thích. Khi IDE và CI cho kết quả khác nhau, hãy đối chiếu runtime JDK, classpath, engine, selector, filter, system property và cấu hình Spring context. Sự khác biệt thường nằm ở môi trường thực thi hoặc discovery, chứ không phải annotation `@Test` tự thay đổi ý nghĩa giữa các công cụ.

Khi hiểu rõ ranh giới giữa Platform, Jupiter API, Jupiter Engine và công cụ chạy test, ta có thể lần theo toàn bộ vòng đời của một test: từ lúc được viết, được khám phá, được Spring chuẩn bị context, được thực thi cho đến khi kết quả xuất hiện trong báo cáo. Đây là nền tảng để thiết lập bộ kiểm thử Spring có thể chạy ổn định trong IDE, local build và CI.
