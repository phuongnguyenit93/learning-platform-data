# Vintage engine cho giai đoạn chạy song song bộ test cũ

Khi chuyển một dự án Spring Boot từ bộ kiểm thử **JUnit 4** sang **JUnit Jupiter (JUnit 5)**, không nhất thiết phải sửa toàn bộ hàng trăm test trước khi nâng cấp build. **JUnit Vintage TestEngine** giúp **chạy các test JUnit 4 hiện có trên JUnit Platform**, đồng thời các test mới dùng **JUnit Jupiter TestEngine**. Hai engine tồn tại cùng một test runtime, để nhóm phát triển chuyển đổi **từng lớp, từng module** mà không đánh mất lớp bảo vệ regression của bộ test cũ.

Cụm từ **“chạy song song”** ở đây cần phân biệt hai nghĩa:
1. **Cùng tồn tại trong một lần chạy suite (coexistence):** JUnit 4 và Jupiter cùng được JUnit Platform discovery/execution. **Đây là mục đích chính của Vintage**.
2. **Chạy đồng thời trên nhiều threads (parallel execution):** JUnit Platform/Jupiter/Vintage có tùy chọn riêng; bật concurrency là quyết định bổ sung có rủi ro về fixture, transaction, context cache và các JUnit 4 Rules/Runner cũ. **Thêm Vintage không tự biến test cũ thành thread-safe**.

Bài này thuộc nhóm **Phiên bản và chuyển đổi** của **Spring Boot - testing**, tập trung chủ đề **“Vintage engine cho giai đoạn chạy song song bộ test cũ”**. Nội dung gồm cơ chế JUnit Platform, dependency trong Spring Boot 3.5, Maven Surefire/Gradle, SpringRunner so với SpringExtension, compatibility của runners/rules/parameterized/categories, ma trận migration, lỗi làm mất test âm thầm, chiến lược CI nhiều pha và ví dụ Maven **Java 17 + Spring Boot 3.5.0 + JUnit 4.13.2 + Jupiter + Vintage** với **17 lượt thực thi test**. Ví dụ không dùng database, Docker, web server hoặc API bên ngoài.

> **Nguyên tắc chuyển đổi:** Vintage là **cầu nối tạm thời**, không phải lý do để viết thêm mã mới theo JUnit 4. Từ lúc đã chạy được hai engine, viết test mới bằng Jupiter; đo số test cũ còn lại; chuyển các test cũ theo nhóm nhỏ; cuối cùng bỏ JUnit 4/Vintage khi không còn legacy tests.

## 1. Kiến trúc: JUnit Platform, Jupiter và Vintage không đồng nghĩa

JUnit 5 có ba nhóm thành phần thường thấy:

| Thành phần | Artifact/khái niệm | Vai trò |
|---|---|---|
| **JUnit Platform** | Launcher, discovery selectors, filters, TestEngine SPI | Điểm vào chung để IDE, Maven, Gradle phát hiện và thực thi tests |
| **JUnit Jupiter API** | `org.junit.jupiter.api.Test`, `BeforeEach`, `Assertions`, extensions | Viết test theo mô hình JUnit 5 |
| **JUnit Jupiter Engine** | `org.junit.jupiter:junit-jupiter-engine` | Thực thi test được viết bằng Jupiter API |
| **JUnit 4 API** | `junit:junit:4.13.2`, `org.junit.Test`, `RunWith`, `Rule` | Source annotations/runners của test cũ |
| **JUnit Vintage Engine** | `org.junit.vintage:junit-vintage-engine` | Cho JUnit Platform khám phá/chạy test JUnit 4 (và những kiểu legacy được hỗ trợ) |
| **Spring TestContext** | `spring-test`, `SpringRunner`, `SpringExtension` | Tích hợp Spring-managed `ApplicationContext` và dependency injection vào từng testing model |
| **Maven Surefire** | `maven-surefire-plugin` | Launcher chạy test trong vòng đời Maven `test` |

```text
mvn test / IDE / Gradle
             |
             v
      JUnit Platform Launcher
             |
             +----------------------+----------------------+
             |                                             |
             v                                             v
   junit-jupiter-engine                          junit-vintage-engine
             |                                             |
             v                                             v
   org.junit.jupiter.api.Test                    org.junit.Test (JUnit 4)
   @BeforeEach / @ParameterizedTest              @Before / @Rule / @RunWith
             |                                             |
             +--------------- Spring ----------------------+
                             |
                Jupiter: SpringExtension
                JUnit 4: SpringRunner
                             |
                             v
              @SpringBootTest ApplicationContext
```

**Lưu ý về imports:** `org.junit.Test` và `org.junit.jupiter.api.Test` là **hai annotation khác nhau**. Vintage **không** chuyển bytecode hay source JUnit 4 thành Jupiter; nó thực thi mô hình JUnit 4 thông qua engine tương thích. Khi kiểm thử đi qua `@RunWith(Parameterized.class)` hoặc một `@Rule` cũ, đó vẫn là semantics JUnit 4, không được Jupiter “nâng cấp” tự động.

### 1.1. Vì sao hai engine không xung đột tên Test?

Bởi vì package khác nhau:
- JUnit 4: `import org.junit.Test;`
- Jupiter: `import org.junit.jupiter.api.Test;`

Hai test classes riêng có thể import annotation đúng loại. Trong giai đoạn migration, tránh đặt cả hai kiểu annotation `@Test` trong **cùng một class** để lách việc chuyển đổi: engine discovery có thể tạo thông báo khó hiểu, chạy trùng hoặc bỏ sót phương thức. Dùng cấu trúc rõ ràng: **class JUnit 4 nguyên vẹn** → convert sang **class Jupiter nguyên vẹn**.

### 1.2. Vintage có tự chạy khi thêm dependency JUnit 4?

**Không nhất thiết.** `junit:junit` cung cấp API/classes của JUnit 4; để JUnit Platform thực thi chúng như test cũ, cần `junit-vintage-engine` trong test runtime. Ngược lại, chỉ có Vintage mà thiếu API/runtime JUnit 4 phù hợp cũng không đủ để compile các source dùng `org.junit.Test`. Vintage thông thường kéo JUnit 4 transitively, nhưng POM ví dụ khai **cả dependency JUnit 4 trực tiếp** để rõ ràng source contract.

Spring Boot 3.5 `spring-boot-starter-test` cung cấp Jupiter, Spring Test, AssertJ, Mockito... **không tự bật Vintage theo mặc định**; muốn chạy JUnit 4 phải bổ sung engine. Đây là khác biệt đáng chú ý nếu đọc hướng dẫn cũ của các bản Spring Boot trước kia, khi starter-test từng kéo Vintage hoặc người dùng được hướng dẫn exclude Vintage sau migration. Hãy kiểm dependency graph thực tế, không đoán dựa trên README từ phiên bản khác.

## 2. Dependency Maven trong Spring Boot 3.5

### 2.1. Tại sao nên dùng Boot BOM để đồng bộ JUnit Platform?

JUnit Platform, Jupiter và Vintage có nhiều artifacts dùng chung các interfaces. Một tổ hợp lệch phiên bản, chẳng hạn Jupiter/Platform của Boot 3.5 nhưng Vintage tự pin từ nhánh JUnit khác, có thể dẫn tới `NoSuchMethodError`, `ClassNotFoundException`, discovery failures hoặc IDE khác CLI. Để giảm rủi ro:
- Dùng `spring-boot-starter-parent`/BOM phù hợp.
- Không tự trộn nhiều phiên bản `junit-platform-*`, `junit-jupiter-*` và `junit-vintage-*`.
- Chỉ đặt version rõ cho **`junit:junit:4.13.2`**; để Boot quản lý version của Vintage và launcher.
- Dùng Maven Surefire được Boot parent quản lý (hoặc một version tương thích với JUnit Platform).
- Kiểm `mvn dependency:tree` khi nghi có test framework transitive cũ.

### 2.2. POM chính thức của ví dụ runnable

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>junit-vintage-bridge</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <!-- Jupiter, Spring TestContext, AssertJ, Mockito -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- JUnit 4 API cho source tests cũ -->
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
            <scope>test</scope>
            <exclusions>
                <exclusion>
                    <groupId>org.hamcrest</groupId>
                    <artifactId>hamcrest-core</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- Cầu nối JUnit 4 -> JUnit Platform -->
        <dependency>
            <groupId>org.junit.vintage</groupId>
            <artifactId>junit-vintage-engine</artifactId>
            <scope>test</scope>
            <exclusions>
                <exclusion>
                    <groupId>org.hamcrest</groupId>
                    <artifactId>hamcrest-core</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- Cho test kiểm tra cả hai engines bằng Launcher API -->
        <dependency>
            <groupId>org.junit.platform</groupId>
            <artifactId>junit-platform-launcher</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao exclude `hamcrest-core`?** Spring Boot `starter-test` mang Hamcrest hiện đại, còn đường JUnit 4/Vintage có thể mang `hamcrest-core` cũ transitively. Spring Boot 3.5 docs gợi ý exclude `hamcrest-core` ở Vintage để tránh trùng/lệch Hamcrest. POM ở đây còn exclude tại dependency JUnit 4 trực tiếp, nên không kéo lại qua đường đó. Nếu project thực dùng matcher của phiên bản Hamcrest khác, xem toàn bộ resolved graph trước khi can thiệp.

`junit-platform-launcher` không phải một test framework riêng; nó có mặt vì ví dụ có `EngineDiscoveryTest` dùng `LauncherFactory` để assert **có cả hai engine trong runtime**. Nếu dự án không dùng Launcher API trực tiếp, có thể không cần khai dependency này riêng khi Surefire/IDE tự cung cấp launcher phù hợp; nhưng khai rõ giúp tooling có phiên bản được BOM quản lý.

**Đừng pin** `junit-vintage-engine` ở một version khác Boot BOM chỉ vì blog cũ đưa `5.4.2`; nếu bắt buộc override JUnit version, dùng hướng dẫn chính thức của Spring Boot để cập nhật **đồng bộ Platform/Jupiter/Vintage**.

## 3. Maven Surefire phát hiện và thực thi tests như thế nào?

Surefire chọn các class theo tên file mặc định, chẳng hạn:
- `**/Test*.java`
- `**/*Test.java`
- `**/*Tests.java`
- `**/*TestCase.java`

Sau đó JUnit Platform/engines xác định test methods bên trong. Project runnable đặt tên cả JUnit 4 và Jupiter classes kết thúc bằng **`Test`** để không bị bỏ qua do naming conventions.

### 3.1. Test count phải bao gồm cả Vintage và Jupiter

Nếu vô tình bỏ Vintage, các source `LegacyPlainTest`/`LegacySpringTest` có thể vẫn **biên dịch** nhờ `junit:junit`, nhưng **JUnit Platform không còn engine phù hợp để chạy chúng**. Khi suite vẫn có nhiều Jupiter tests, tổng build có thể PASS dù **regression tests cũ đã biến mất khỏi kết quả**.

Vì vậy CI nên kiểm:
1. dependency `org.junit.vintage:junit-vintage-engine` hiện diện ở test runtime trong giai đoạn chuyển tiếp;
2. `EngineDiscoveryTest` xác nhận JUnit Platform thấy engine IDs `junit-vintage` và `junit-jupiter`;
3. báo cáo Surefire chứa expected legacy classes;
4. tổng test count/engine count không giảm bất thường;
5. mỗi lần loại một JUnit4 class phải đi kèm phiên bản Jupiter thay thế tương ứng, không chỉ xóa file.

Một `BUILD SUCCESS` không phải bằng chứng mọi test đã được discovery. Nếu log báo `Tests run: 0` cho một module từng có tests, **phải điều tra và fail CI**, không coi đó là thành công.

### 3.2. Chạy cả hai, hoặc chọn engine để chẩn đoán

Với Maven Surefire hỗ trợ filter theo JUnit engine IDs:

```bash
# Chạy cả JUnit 4 qua Vintage và Jupiter.
mvn test

# Chỉ các JUnit 4/Vintage tests.
mvn test -Dsurefire.includeJUnit5Engines=junit-vintage

# Chỉ các JUnit Jupiter tests.
mvn test -Dsurefire.includeJUnit5Engines=junit-jupiter
```

`surefire.includeJUnit5Engines` là user property của Surefire, không phải annotation/Java system property tự diễn giải bởi test class. Trong project có custom Surefire configuration/provider, verify effect bằng reports. **Không đặt một filter chỉ Jupiter trong CI tổng** rồi kỳ vọng các tests cũ vẫn được chạy.

Chọn class cụ thể:

```bash
mvn -Dtest=LegacyPlainTest test
mvn -Dtest=LegacySpringTest test
mvn -Dtest=ModernSpringTest test
```

Bài mẫu có test cụ thể ở phần 6. Với multi-module Maven, `-Dtest=...` và `failIfNoSpecifiedTests` có thể khác hành vi từng module; đừng dùng `-Dtest` để kết luận toàn reactor test count nếu nhiều modules không có class tên đó.

### 3.3. Surefire khác Failsafe

- `maven-surefire-plugin` thường chạy unit-style tests trong Maven phase `test`, theo patterns `*Test`.
- `maven-failsafe-plugin` thường chạy integration-style tests trong `integration-test`/`verify`, theo patterns `*IT`/`ITCase`.
- Cả hai có thể dùng JUnit Platform/Vintage khi cấu hình đúng, nhưng **`mvn test` không tự thay `mvn verify` cho Failsafe integration suite**.
- Nếu project có legacy `*IT`, cần kiểm reports của **cả Surefire lẫn Failsafe**, không chỉ các test classes trong `src/test/java`.
- Không nhầm “migrated Jupiter test” với “tự động được discover dù đặt sai tên file”. Các conventions/filter build vẫn có hiệu lực.

### 3.4. Gradle tương đương

Trong project Gradle đã có Spring Boot/BOM dependency management phù hợp, ý tưởng cấu hình:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **snippet Gradle**, không phải build thứ hai trong project Maven của phần 6. Với Gradle, `useJUnitPlatform()` là điểm quan trọng; nếu chỉ có JUnit 4 runner cũ, phải chuyển test task sang JUnit Platform để chọn Jupiter và Vintage engines. Kiểm Boot BOM/plugin setup để versions align; không để Gradle lấy Vintage mới nhất khác Jupiter/Platform của dự án.

## 4. Spring TestContext: SpringRunner khác SpringExtension

### 4.1. JUnit 4 cần `@RunWith(SpringRunner.class)`

```java
@RunWith(SpringRunner.class)
@SpringBootTest
public class LegacyServiceTest {
    @Autowired
    private PricingService service;

    @Test // import org.junit.Test
    public void shouldWork() {
        assertEquals(6, service.lineTotal(2, 3));
    }
}
```

Đây là snippet, không phải file runnable độc lập. `SpringRunner` là JUnit 4 Runner cho phép Spring TestContext xử lý lifecycle, application context, injection và các test execution listeners. **Vintage chịu trách nhiệm chạy JUnit 4 Runner**, nhưng **không tự thêm SpringRunner** vào những class chỉ có `@SpringBootTest`. Tài liệu Spring Boot 3.5 nhắc rõ rằng test JUnit 4 cần `@RunWith(SpringRunner.class)` để tích hợp Spring.

Nếu bỏ `@RunWith`:
- Một test thuần JUnit 4 không dùng Spring vẫn chạy bằng Vintage.
- Một test có `@Autowired` nhưng thiếu SpringRunner có thể nhận `null`/không có Spring context. Test fail tại runtime, hoặc tệ hơn, test không kiểm điều bạn nghĩ mình đang kiểm.
- Không chữa bằng cách thêm `@ExtendWith(SpringExtension.class)` vào **class vẫn dùng `org.junit.Test`**; Jupiter extension không tự áp lên Vintage method.

### 4.2. Jupiter dùng SpringExtension (đã có qua @SpringBootTest)

```java
@SpringBootTest
class ModernServiceTest {
    @Autowired
    private PricingService service;

    @Test // import org.junit.jupiter.api.Test
    void shouldWork() {
        assertEquals(6, service.lineTotal(2, 3));
    }
}
```

Với Spring Boot 3.5, `@SpringBootTest` đã meta-annotated bằng `@ExtendWith(SpringExtension.class)`, nên **không cần** lặp lại extension. Nếu dùng Spring Framework test với `@ContextConfiguration` thuần và Jupiter, `@ExtendWith(SpringExtension.class)` hoặc `@SpringJUnitConfig` có thể cần thiết.

### 4.3. Không ép hai models vào một class

Không nên:

```java
@RunWith(SpringRunner.class)
@ExtendWith(SpringExtension.class)
class ConfusedTest {
    @org.junit.Test
    public void oldStyle() {
    }

    @org.junit.jupiter.api.Test
    void newStyle() {
    }
}
```

Đoạn trên chỉ là **anti-pattern minh họa**: engine filtering và các lifecycle callbacks có thể xử lý khác mong muốn. Mục tiêu migration không phải làm một class có đủ annotations, mà là **mỗi class có đúng một engine model**. Dùng Vintage cho JUnit 4 class hiện có; chuyển trọn class sang Jupiter với annotations/imports và extension tương ứng.

### 4.4. Context cache, rollback và test isolation

Dù JUnit 4 `SpringRunner` và Jupiter `SpringExtension` đều dùng Spring TestContext, đừng giả định mọi test classes luôn share cùng `ApplicationContext`. Cache key có thể thay đổi bởi `@SpringBootTest(classes/properties)`, `@ActiveProfiles`, `@DynamicPropertySource`, `@MockitoBean` hoặc test configuration khác.

- Reuse context có thể giảm startup, nhưng singleton mutable beans vẫn sống qua nhiều tests.
- `@Transactional` test có thể rollback mặc định nếu dùng test-managed transaction, nhưng HTTP server thread, `REQUIRES_NEW` hoặc async work không tự rollback cùng test.
- `@DirtiesContext` loại context khỏi cache; dùng bừa bãi làm suite chậm và không xóa data đã commit ở external DB.
- Chạy hai engines cùng suite **không có nghĩa JUnit 4 `@Before` được thực hiện trước Jupiter `@BeforeEach`**; mỗi class/method có lifecycle riêng.
- Tests cũ dùng static fixtures, JUnit4 `@ClassRule` hoặc external resources cần được audit trước khi bật parallel execution.

## 5. Ma trận migration JUnit 4 → Jupiter

| JUnit 4 cũ | Jupiter thay thế thường gặp | Lưu ý |
|---|---|---|
| `org.junit.Test` | `org.junit.jupiter.api.Test` | **Đổi import**, không chỉ đổi method name |
| `@Before` | `@BeforeEach` | Jupiter method có thể package-private, không bắt buộc public |
| `@After` | `@AfterEach` | Kiểm cleanup và exception semantics |
| `@BeforeClass` | `@BeforeAll` | Theo lifecycle PER_METHOD thông thường phải static |
| `@AfterClass` | `@AfterAll` | Xác nhận teardown của shared resources |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` hoặc `@SpringBootTest` meta-extension | Không giữ @RunWith trong Jupiter |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` | Có dependency Mockito Jupiter cần thiết |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` với `@CsvSource`/`@MethodSource` | Khác mô hình constructor injection/runner |
| `@Rule TemporaryFolder` | `@TempDir` | Kiểm per-test cleanup/filesystem ownership |
| `@Rule ExpectedException` | `assertThrows(...)` | Chỉ assert đúng exception type/message |
| `@Rule TestName` | `TestInfo` parameter injection | Không có same Rule callback tự động |
| `@Rule Timeout` hoặc `@Test(timeout=...)` | `@Timeout`/`assertTimeout` | Cẩn trọng preemptive execution và Spring transactions |
| `@Ignore` | `@Disabled` | Đừng tự động “unignore” hàng loạt |
| `@Category(MyCategory.class)` | `@Tag("my-category")` | Vintage expose category dưới FQN tag |
| `org.junit.Assert.assertEquals(expected, actual)` | `org.junit.jupiter.api.Assertions.assertEquals(expected, actual)` | Với message, Jupiter đưa message **cuối** thay vì đầu |
| `@Test(expected=IllegalArgumentException.class)` | `assertThrows(IllegalArgumentException.class, executable)` | Assert throwable chính xác trong code body |

**Không tự chuyển toàn bộ `@Rule` thành Jupiter chỉ bằng một import.** Rules và custom Runners là JUnit 4 extension model; Vintage tiếp tục chạy chúng theo JUnit 4, trong khi Jupiter có `@ExtendWith`/`@RegisterExtension`/`TestInfo`/`@TempDir` và extension contracts riêng. Có một số hỗ trợ migration hạn chế cho một số JUnit4 rules, nhưng đừng coi đó là bảo đảm mọi custom Rule đều hoạt động trong Jupiter.

### 5.1. JUnit 4 @Category khi chạy trên Vintage

JUnit Vintage 5.12 chuyển một `@Category(com.example.legacy.Fast.class)` thành **JUnit Platform tag** dùng tên class fully qualified, ví dụ `com.example.legacy.Fast`. Jupiter `@Tag("fast")` là một tag string khác. Nếu CI hiện đang dùng `-Dgroups=...`, cần mapping/tag policy có chủ đích, tránh vô tình bỏ test legacy vì filter chỉ nhận `fast` trong khi Vintage phát `com.example.legacy.Fast`.

Không dùng wildcard dựa trên class name category để “đoán” tag mới. Chạy riêng engine và kiểm reports/phân loại trước khi thay filter.

### 5.2. JUnit 4 Parameterized Runner không đổi ngay được

Legacy:
```java
@RunWith(Parameterized.class)
public class OldParameterizedTest {
    @Parameters public static Iterable<Object[]> data() {
        // ...
    }
    @Test public void verifiesCase() {
        // ...
    }
}
```

Đây là snippet để nhận diện, không phải runnable file. Dưới Vintage, JUnit 4 `Parameterized` vẫn là Runner được dùng. Khi chuyển sang Jupiter, nên dùng `@ParameterizedTest` cùng `@CsvSource` hoặc `@MethodSource`; không cố gắn đồng thời `@RunWith(Parameterized.class)` và `@RunWith(SpringRunner.class)`, vì Java/JUnit4 không hỗ trợ hai runners cùng lúc. Nếu cần Spring injection trong parameterized test, Jupiter với SpringExtension phù hợp hơn.

### 5.3. Kiểm cùng behavior, không chỉ cùng số test methods

Một `@RunWith(Parameterized.class)` có **một `@Test` method** nhưng nhận **ba parameter sets**, nên **thực thi ba invocations**. Khi chuyển sang một `@ParameterizedTest` với ba `@CsvSource` rows, phải kiểm cả ba cases vẫn chạy. Nếu một migration vô tình chỉ giữ một row, test method count không đổi nhưng test coverage giảm.

Tương tự JUnit4 custom Runners có thể sinh test instances động; chỉ so số tên class không đủ. Dùng report test invocations/test IDs và case matrix, nhất là với browser/DB/contract tests.

## 6. Project runnable Java 17 + Spring Boot 3.5: hai engine trong một Maven suite

### 6.1. Sơ đồ files

```text
junit-vintage-bridge/
├── pom.xml
└── src/
    ├── main/java/com/example/vintage/
    │   ├── VintageDemoApplication.java
    │   └── PricingService.java
    └── test/
        ├── java/com/example/vintage/
        │   ├── LegacyCategory.java
        │   ├── LegacyPlainTest.java
        │   ├── LegacySpringTest.java
        │   ├── LegacyParameterizedTest.java
        │   ├── ModernSpringTest.java
        │   └── EngineDiscoveryTest.java
        └── resources/
            └── junit-platform.properties
```

Tất cả tests deterministic; không cần DB, Docker, network hoặc fake secrets. `PricingService` không giữ mutable singleton state nên cả JUnit4 và Jupiter đều có thể kiểm cùng business behavior mà không phụ thuộc thứ tự. Mẫu sử dụng `webEnvironment=NONE` cho Spring integration tests để không khởi động HTTP server.

### 6.2. Boot application

File **`src/main/java/com/example/vintage/VintageDemoApplication.java`**:

```java
package com.example.vintage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VintageDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(VintageDemoApplication.class, args);
    }
}
```

### 6.3. PricingService: một behavior dùng để kiểm trên cả hai engines

File **`src/main/java/com/example/vintage/PricingService.java`**:

```java
package com.example.vintage;

import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public int lineTotal(int unitPrice, int quantity) {
        if (unitPrice < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must be non-negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

`Math.multiplyExact` ném `ArithmeticException` khi tích `int` overflow; đây là JDK Java 17 API thông thường. Test phân biệt input validation với overflow, nên không vô tình pass nhờ một exception type khác. Service không phụ thuộc DB/clock/network; `@Service` để Spring TestContext có bean dùng khi inject.

### 6.4. JUnit4 Category marker

File **`src/test/java/com/example/vintage/LegacyCategory.java`**:

```java
package com.example.vintage;

public interface LegacyCategory {
}
```

Interface chỉ làm marker cho `@Category` của JUnit4. Khi chạy Vintage, nó có thể xuất hiện dưới tag `com.example.vintage.LegacyCategory` trong metadata. Đây **không** là Jupiter `@Tag("legacy")`; nếu filter tags trong CI, phải dùng đúng tag.

### 6.5. JUnit4 thuần có @Rule/@Before/@After: 3 tests

File **`src/test/java/com/example/vintage/LegacyPlainTest.java`**:

```java
package com.example.vintage;

import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.experimental.categories.Category;
import org.junit.rules.TestName;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@Category(LegacyCategory.class)
public class LegacyPlainTest {

    @Rule
    public final TestName testName = new TestName();

    private PricingService service;

    @Before
    public void setUp() {
        service = new PricingService();
    }

    @After
    public void tearDown() {
        assertNotNull(service);
    }

    @Test
    public void computesLineTotal() {
        assertEquals(10, service.lineTotal(5, 2));
        assertEquals(
                "computesLineTotal", testName.getMethodName());
    }

    @Test
    public void zeroPriceIsAllowed() {
        assertEquals(0, service.lineTotal(0, 3));
    }

    @Test(expected = IllegalArgumentException.class)
    public void zeroQuantityIsRejected() {
        service.lineTotal(3, 0);
    }
}
```

**3 JUnit4 `@Test` methods.** Đây là Java class thuần: nó dùng `new PricingService()`, không dùng Spring context, nhưng là bằng chứng rằng Vintage giữ nguyên JUnit4 `@Before`, `@After`, `@Rule TestName` và `@Test(expected=...)` semantics. Nó không kiểm Spring dependency injection; dành cho `LegacySpringTest`.

Nếu chạy bằng chỉ `junit-jupiter` engine, cả ba methods **không được thực thi**. Nếu chạy chỉ `junit-vintage` engine, cả ba được discovery bởi JUnit4 annotation.

### 6.6. JUnit4 tích hợp SpringRunner: 3 tests

File **`src/test/java/com/example/vintage/LegacySpringTest.java`**:

```java
package com.example.vintage;

import org.junit.Test;
import org.junit.runner.RunWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@RunWith(SpringRunner.class)
@SpringBootTest(
        classes = VintageDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
public class LegacySpringTest {

    @Autowired
    private PricingService service;

    @Test
    public void springInjectsRealService() {
        assertNotNull(service);
    }

    @Test
    public void calculatesUsingSpringBean() {
        assertEquals(21, service.lineTotal(7, 3));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsNegativeUnitPrice() {
        service.lineTotal(-1, 2);
    }
}
```

**3 JUnit4 `@Test` methods.** `@RunWith(SpringRunner.class)` là phần quan trọng: SpringRunner khởi động TestContext/lifecycle và inject service, còn Vintage là bridge từ Platform tới JUnit4 Runner. Test class này cho phép nâng cấp Maven/Boot/JUnit Platform mà vẫn giữ mã legacy.

Với JUnit 4, public test class + public void `@Test` methods giúp tránh giới hạn visibility cổ điển; Jupiter cho phép package-private và non-public methods theo điều kiện. Không vội đổi modifiers/imports của legacy test trước khi đã xác lập baseline.

### 6.7. JUnit4 Parameterized Runner: 3 invocations

File **`src/test/java/com/example/vintage/LegacyParameterizedTest.java`**:

```java
package com.example.vintage;

import java.util.Arrays;
import java.util.Collection;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;
import org.junit.runners.Parameterized.Parameters;

import static org.junit.Assert.assertEquals;

@RunWith(Parameterized.class)
public class LegacyParameterizedTest {

    private final int unitPrice;
    private final int quantity;
    private final int expected;

    public LegacyParameterizedTest(
            int unitPrice, int quantity, int expected) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.expected = expected;
    }

    @Parameters(name = "{index}: {0} x {1} = {2}")
    public static Collection<Object[]> cases() {
        return Arrays.asList(new Object[][] {
                {2, 3, 6},
                {0, 4, 0},
                {7, 1, 7}
        });
    }

    @Test
    public void computesForEachCase() {
        PricingService service = new PricingService();
        assertEquals(
                expected,
                service.lineTotal(unitPrice, quantity));
    }
}
```

Class có **một `@Test` method** nhưng `@Parameters` cung cấp ba cases, nên Vintage/JUnit4 Parameterized Runner chạy **ba lượt**. Đây là bằng chứng quan trọng khi so sánh test counts trong migration. Jupiter `@ParameterizedTest` sẽ thay mô hình này, nhưng trong giai đoạn chuyển tiếp giữ nguyên runner.

### 6.8. Jupiter + Spring Boot: 4 @Test + 3 parameterized invocations

File **`src/test/java/com/example/vintage/ModernSpringTest.java`**:

```java
package com.example.vintage;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = VintageDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernSpringTest {

    @Autowired
    private PricingService service;

    @Test
    void springInjectsRealService() {
        assertNotNull(service);
    }

    @Test
    void calculatesUsingSpringBean() {
        assertEquals(21, service.lineTotal(7, 3));
    }

    @Test
    void rejectsZeroQuantityWithAssertThrows() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class,
                        () -> service.lineTotal(4, 0));

        assertEquals("quantity must be positive",
                error.getMessage());
    }

    @Test
    void reportsArithmeticOverflowSeparately() {
        assertThrows(ArithmeticException.class,
                () -> service.lineTotal(
                        Integer.MAX_VALUE, 2));
    }

    @ParameterizedTest(name = "{index}: {0} x {1} = {2}")
    @CsvSource({
            "2, 3, 6",
            "0, 4, 0",
            "7, 1, 7"
    })
    void calculatesCsvCases(
            int unitPrice, int quantity, int expected) {
        assertEquals(expected,
                service.lineTotal(unitPrice, quantity));
    }
}
```

Đây là **4 Jupiter `@Test` methods** + **1 `@ParameterizedTest` method chạy 3 lần** = **7 Jupiter test invocations**. Không có `@RunWith`. Với Spring Boot `@SpringBootTest`, Jupiter nhận SpringExtension qua meta-annotation.

Nhìn cặp `LegacySpringTest` và `ModernSpringTest`: chúng cố ý kiểm cùng một số behavior để chứng minh migration có thể chạy cùng suite, nhưng trong dự án thực bạn sẽ **chuyển test cũ rồi xóa bản legacy trùng**, tránh giữ duplicate lâu dài làm tăng chi phí build.

### 6.9. Kiểm engine IDs bằng JUnit Platform Launcher: 1 test

File **`src/test/java/com/example/vintage/EngineDiscoveryTest.java`**:

```java
package com.example.vintage;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.platform.engine.discovery.DiscoverySelectors
        .selectClass;

class EngineDiscoveryTest {

    @Test
    void jupiterAndVintageAreBothDiscoverable() {
        LauncherDiscoveryRequest request =
                LauncherDiscoveryRequestBuilder.request()
                        .selectors(
                                selectClass(LegacyPlainTest.class),
                                selectClass(ModernSpringTest.class))
                        .build();

        TestPlan plan = LauncherFactory.create()
                .discover(request);

        Set<String> ids = plan.getRoots().stream()
                .map(TestIdentifier::getUniqueId)
                .collect(Collectors.toSet());

        assertThat(ids).contains(
                "[engine:junit-jupiter]",
                "[engine:junit-vintage]");
    }
}
```

Test này dùng **Launcher discovery**, không gọi `execute(...)` lại các tests khác, nên không gây thực thi lặp vì test kiểm engine. Nó sẽ FAIL nếu không tìm được engine `junit-vintage` hay `junit-jupiter` trong runtime khi selectors tìm đúng class.

**Giới hạn của test:** cả hai engines **được discover** chưa chứng minh pipeline thực sự **execute tất cả** các legacy tests. Surefire có thể dùng engine filters, excludes hoặc khác tên class. Do đó vẫn cần Surefire reports + CI check tổng số tests/migration coverage. `EngineDiscoveryTest` là một canary dễ hiểu cho giai đoạn bridge; khi đã chuyển xong JUnit4 và cố ý xóa Vintage, **cập nhật/xóa canary theo lộ trình**, không giữ một assertion đòi engine đã loại.

### 6.10. JUnit Platform properties: không bật parallel một cách vô tình

File **`src/test/resources/junit-platform.properties`**:

```properties
# Hai engine cùng được discovery trong một JUnit Platform run.
# Không set global include/exclude engine filter ở đây.

junit.jupiter.execution.parallel.enabled=false
junit.vintage.execution.parallel.enabled=false
```

Mẫu tập trung **coexistence** giữa JUnit4 và Jupiter, không kiểm thread safety. Trên JUnit 5.12, Vintage có configuration parameters riêng cho parallel classes/methods; vì suite cũ có Rules/static fixtures, mặc định tốt nhất là **chưa bật parallel** cho tới khi audit.

### 6.11. Chạy bộ demo và kiểm số test

Trong thư mục chứa `pom.xml`, với **JDK 17+** và Maven:

```bash
mvn test
```

Kỳ vọng **17 lượt thực thi**:

| Class | Engine | Số methods | Số invocations |
|---|---|---:|---:|
| `LegacyPlainTest` | Vintage/JUnit4 | 3 | 3 |
| `LegacySpringTest` | Vintage/JUnit4 + SpringRunner | 3 | 3 |
| `LegacyParameterizedTest` | Vintage/JUnit4 Parameterized | 1 | 3 |
| `ModernSpringTest` | Jupiter + SpringExtension | 5 (4 @Test, 1 @ParameterizedTest) | 7 |
| `EngineDiscoveryTest` | Jupiter + Platform Launcher | 1 | 1 |
| **Tổng** | **2 engines** | **13** | **17** |

Số theo engine: **Vintage = 9 invocations**, **Jupiter = 8 invocations**. Không coi mọi invocation đều là một source method riêng vì parameterized runners tạo nhiều cases.

Có thể chạy:

```bash
# Với filters của Surefire hỗ trợ JUnit engine selection:
mvn test -Dsurefire.includeJUnit5Engines=junit-vintage
mvn test -Dsurefire.includeJUnit5Engines=junit-jupiter
```

Kỳ vọng filtered runs lần lượt có **9** và **8** invocations. Nếu một filter không được áp dụng như kỳ vọng do plugin version/custom provider, kiểm cấu hình chính thức Surefire và reports; đừng chỉ dựa vào lệnh đã gõ.

**Không bịa stdout:** Maven Surefire có thể hiện từng class, số tests, thời gian và Spring startup logs khác nhau theo phiên bản. Những số **17/9/8** là dự kiến từ mã sample, không phải bản sao output đã được chạy ở môi trường biên soạn.

Kiểm dependency tree và reports:

```bash
mvn dependency:tree
mvn test
```

Sau khi chạy, kiểm thư mục `target/surefire-reports` để xác minh có kết quả cho **cả năm test classes**. Trong CI, có thể dùng JUnit XML aggregator/quality gate để so baseline và cảnh báo nếu legacy classes bị mất. Khi dự án có Failsafe, còn phải kiểm `target/failsafe-reports` và chạy `mvn verify`.

## 7. Vintage và Jupiter chạy cạnh nhau: những thứ KHÔNG tự đồng nhất

### 7.1. `@Before` và `@BeforeEach` không chia sẻ lifecycle

Một JUnit4 test chỉ biết `@Before`/`@After` của JUnit4 Runner; Jupiter chỉ biết `@BeforeEach`/`@AfterEach` của Jupiter. Không tạo một superclass dùng Jupiter `@BeforeEach` rồi mong nó chắc chắn chạy khi JUnit4 Vintage test thực thi. Nếu cần chung fixture logic, tách thành helper Java thuần và gọi từ lifecycle của từng framework.

### 7.2. JUnit4 Rules tiếp tục hoạt động dưới Vintage

Vintage chạy JUnit4 Runner, vì thế `@Rule TestName`, `TemporaryFolder` hoặc custom JUnit4 Rules hợp lệ có thể tiếp tục hoạt động **theo semantics JUnit4**. Nó không biến rules thành Jupiter extensions. Khi chuyển class sang Jupiter, hãy map từng Rule sang `@TempDir`, `TestInfo`, `@RegisterExtension` hoặc extension riêng; đừng chỉ xóa `@Rule` cho code compile mà mất cleanup/logging/timeout behavior.

### 7.3. JUnit4 @RunWith chỉ có một runner tại một thời điểm

Một JUnit4 class không thể có hai `@RunWith` hợp lệ để cùng dùng `SpringRunner` và `Parameterized` theo cách thường. Nếu legacy suite dùng custom Runner, hãy:
- giữ runner nguyên trong giai đoạn Vintage nếu còn tương thích;
- đánh giá runner có gọi Spring TestContext hay không;
- chuyển sang Jupiter extension và parameterized model khi thích hợp;
- viết behavior regression trước khi đổi extension architecture.

Không sửa test bằng cách đặt `@RunWith(SpringRunner.class)` vào mọi class, vì điều đó có thể phá custom runner đang chịu trách nhiệm tạo test cases.

### 7.4. Spring Boot annotations không thay thế TestEngine

`@SpringBootTest` là test context bootstrapper/extension integration, không phải JUnit4 engine. Khi thiếu Vintage, test cũ không tự xuất hiện chỉ vì class còn `@SpringBootTest`. Khi thiếu `@RunWith(SpringRunner.class)`, Vintage có thể chạy JUnit4 methods nhưng không có Spring-managed injection. Hai lỗi **khác nhau**:
- thiếu engine → test không được chạy;
- thiếu runner → test chạy mà Spring context không hoạt động như mong đợi.

### 7.5. Jupiter @Test trên method public không phải JUnit4 test

Một method `public void foo()` với `org.junit.jupiter.api.Test` **không phải** JUnit4 test, dù đúng kiểu method public-void như JUnit4. Ngược lại, `org.junit.Test` trên method package-private có thể không tuân JUnit4 public visibility và dẫn tới initialization error. Khi auto-refactor imports, kiểm visibility và annotations đúng framework.

### 7.6. Assertion APIs và message order

JUnit4:
```java
org.junit.Assert.assertEquals(
        "total must match", 6, service.lineTotal(2, 3));
```

Jupiter:
```java
org.junit.jupiter.api.Assertions.assertEquals(
        6, service.lineTotal(2, 3), "total must match");
```

Cùng kết quả nhưng **vị trí message khác**. Compiler có thể giúp phát hiện nhiều lỗi, song một số overloads chấp nhận các kiểu khác nhau và test có thể compile nhưng báo thông điệp sai. Kiểm semantics, không chỉ thay imports bằng search-replace.

### 7.7. Exception và timeout semantics cần được rà lại

JUnit4 `@Test(expected=...)` kiểm exception xuất hiện trong toàn test method; Jupiter `assertThrows(...)` kiểm đúng **executable** bạn đưa vào. Đây là cơ hội làm assertion chặt hơn, ví dụ kiểm expected message/cause. Đối với timeout, `@Timeout`/`assertTimeoutPreemptively` có thread/lifecycle implications; với Spring test-managed `@Transactional`, preemptive timeout có thể đẩy business call sang thread không thuộc transaction và làm dữ liệu commit ngoài rollback. Không chuyển `@Test(timeout=...)` một cách cơ học khi test có DB transaction.

## 8. Chạy song song thật sự (parallel execution) là chủ đề riêng

### 8.1. Mặc định demo chạy tuần tự

Ở trên:
```properties
junit.jupiter.execution.parallel.enabled=false
junit.vintage.execution.parallel.enabled=false
```

Các test classes vẫn cùng suite nhưng không có chính sách “chạy 4 threads”. Vintage 5.12 hỗ trợ các keys riêng, ví dụ (chỉ tham khảo, **không đặt trong project runnable**):

```properties
junit.vintage.execution.parallel.enabled=true
junit.vintage.execution.parallel.classes=true
junit.vintage.execution.parallel.methods=false
junit.vintage.execution.parallel.pool-size=2
```

Bật các flags này chỉ sau khi kiểm legacy fixtures, static state, Spring context cache, port/filesystem và database. **JUnit Vintage có parallel settings riêng** với `junit.jupiter.execution.parallel.enabled`; không suy rằng bật Jupiter parallel sẽ luôn khiến Vintage methods cũng chạy đồng thời.

### 8.2. Rủi ro khi cả hai engine dùng chung resources

- Spring TestContext có **static context cache** trong cùng JVM. Legacy SpringRunner và Jupiter SpringExtension có thể dùng các context keys tương đương, nhưng mutable singleton state vẫn là shared.
- Một JUnit4 `@ClassRule` có thể mở server trên port cố định; Jupiter test khác dùng cùng port sẽ lỗi.
- Legacy tests dùng `static Map`/shared clock/system properties; concurrent execution có thể tạo race.
- Mockito mock/spy và `@MockitoBean` trong cached context có lifecycle/reset cần đánh giá, tránh verify/stub cạnh tranh.
- `@DirtiesContext` có thể đóng context khi test khác vẫn chạy; Spring Framework khuyến cáo tránh parallel với những tests như vậy.
- Test `@Transactional` chưa chắc rollback các side effects từ `RANDOM_PORT`, `REQUIRES_NEW` hoặc async worker.
- Không dùng `TRUNCATE` toàn DB khi nhiều tests cùng chạy; dùng unique run IDs và cleanup scoped.
- Test ordering `@FixMethodOrder` trong JUnit4 hoặc Jupiter `@TestMethodOrder` có thể che dependencies; bật parallel khiến việc dựa vào thứ tự hỏng.
- Kết quả “parallel flaky” không phải lý do xóa Vintage: nguồn lỗi là concurrency/data isolation và cần sửa fixture/đồng bộ hóa.

**Kế hoạch an toàn:** trước hết chạy hai engines **tuần tự** và lập baseline; sau đó chọn một số test classes đã chứng minh isolation để opt-in parallel với CI job có CPU/network budget phù hợp. Không bật flag toàn suite chỉ để giảm thời gian mà bỏ qua việc tái hiện lỗi.

## 9. Lộ trình migration theo giai đoạn

### Giai đoạn 0 — Lập baseline

1. Trên branch ổn định, ghi test count theo module/class và tỷ lệ PASS/FAIL.
2. Phân loại JUnit4 plain, JUnit4 SpringRunner, Parameterized, Category, custom Runner, Rules, JUnit3.
3. Kiểm CI thực sự đang chạy tests cũ (đừng chỉ đọc code).
4. Đảm bảo Java 17/Spring Boot 3.5/plugin versions tương thích với test dependencies.
5. Ghi rõ external fixtures, DB cleanup, flaky tests và engine filters.

**Exit criterion:** mọi class test cũ cần giữ đều có tên và số invocations trong report. Không vội đổi imports khi baseline chưa đáng tin.

### Giai đoạn 1 — Bật Vintage, giữ code legacy

1. Thêm JUnit4 dependency và `junit-vintage-engine` `test` scope.
2. Giữ `spring-boot-starter-test` để chạy Jupiter.
3. Kiểm Surefire/Gradle test task dùng JUnit Platform.
4. Chạy `mvn test`, kiểm reports cả Vintage và Jupiter.
5. Thêm canary engine discovery hoặc CI gate theo test counts.
6. Không bật parallel ngay.

**Exit criterion:** build PASS với cả hai engines, legacy tests không biến mất, reports xác nhận coverage giữ nguyên.

### Giai đoạn 2 — Viết test mới bằng Jupiter

- Mọi class mới import `org.junit.jupiter.api.Test`.
- Dùng `@ParameterizedTest`, `assertThrows`, `@TempDir`, Jupiter extensions.
- Với Spring Boot `@SpringBootTest`, không cần `@RunWith`.
- Khi cần Mockito Jupiter, dùng `MockitoExtension` hoặc Spring bean override đúng boundary.
- Không thêm test mới theo JUnit4 chỉ vì đã có Vintage.

**Exit criterion:** tỷ lệ test Jupiter tăng theo module, số JUnit4 không tăng.

### Giai đoạn 3 — Chuyển từng class cũ

Với mỗi legacy class:
1. Copy/ghi nhận hành vi hiện tại và expected test invocations (bao gồm parameter sets).
2. Chuyển imports `Test/Assertions/Before/After/Ignore/Category`.
3. Thay `@RunWith` bằng Jupiter extension model tương ứng; `@SpringBootTest` thường đã meta-extension.
4. Chuyển Rules và custom runners sang extensions/test fixtures.
5. Chạy riêng class mới; chạy cùng suite; đối chiếu data setup/cleanup/transactions.
6. **Xóa hoặc retire class JUnit4 cũ** chỉ khi hành vi đã được thay thế và CI coverage xác nhận.

**Exit criterion:** không còn JUnit4 annotation trong module đã migrate; Jupiter tests chạy bằng Jupiter engine và case count không sụt.

### Giai đoạn 4 — Bỏ Vintage khi không còn test cũ

- Tìm các imports `org.junit.*` cũ trong `src/test` (phân biệt các API platform/jupiter không phải JUnit4).
- Kiểm custom runners/rules/lib có phụ thuộc JUnit4 transitively.
- Chạy đầy đủ `mvn verify` nếu có Failsafe.
- Gỡ `junit-vintage-engine` và `junit:junit` khỏi dependencies.
- Cập nhật/xóa `EngineDiscoveryTest` đang đòi Vintage.
- Chỉ còn Jupiter engine (và engines khác nếu intentionally dùng) trong reports.
- Theo dõi test counts sau cleanup dependencies để không bỏ sót lớp cũ.
- Loại engine filters/tags legacy không còn dùng, cập nhật docs onboarding/CI.

**Exit criterion:** không còn regression tests chỉ thực thi bằng JUnit4; giảm số engines và dependencies là kết quả có chủ đích, không phải “vô tình build xanh”.

## 10. Lỗi thường gặp khi bật Vintage

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra/hành động |
|---|---|---|
| JUnit4 classes vẫn compile nhưng không chạy | Có `junit:junit`, thiếu Vintage engine | Kiểm test runtime dependency và Surefire reports |
| `Tests run: 0` dù có test source | Sai file names, engine thiếu, filter/exclude | Kiểm patterns, engine IDs, test selectors |
| `@Autowired` null trong JUnit4 test | Thiếu `@RunWith(SpringRunner.class)` | Dùng SpringRunner, không chỉ `@SpringBootTest` |
| Jupiter test có `@RunWith` mà không chạy lifecycle như mong đợi | Trộn annotations/JUnit frameworks | Chuyển cả class sang Jupiter đúng API |
| `NoSuchMethodError` của Platform/Launcher | Versions Platform/Jupiter/Vintage lệch | Để Boot BOM quản lý, xem dependency tree |
| Một Parameterized class chỉ còn 1 case | Migration làm mất input rows | So invocations/case data trước và sau |
| Jupiter `@BeforeEach` không chạy ở JUnit4 test | Lifecycle khác framework | Dùng JUnit4 `@Before` hoặc migrate class |
| `@Rule` không hoạt động sau khi đổi @Test | Rule không phải Jupiter extension | Chuyển Rule sang extension/fixture |
| JUnit4 @Category không khớp `@Tag("legacy")` filter | Vintage dùng FQN category tag | Điều chỉnh CI tag expression |
| Chỉ Vintage-run build nhưng Jupiter tests biến mất | Engine filter được đặt cố định | Chạy suite không filter, gate cả 2 engines |
| Test JUnit4 bị chạy hai lần | Plugin/provider khác hoặc suite selectors trùng | Kiểm Surefire configuration, runners và reports |
| Context startup bị lặp | Mỗi test class có profiles/mock overrides khác | Đọc cache key/log và chuẩn hóa hợp lý |
| H2/DB bị nhiễm state giữa engines | Shared database/context cache, thiếu cleanup | Unique test IDs, rollback/cleanup, không TRUNCATE toàn cục |
| Flaky sau khi bật parallel | Rules/static fixture không thread-safe | Tắt parallel, isolate resources và bật dần |
| Không thấy JUnit4 test trong IDE nhưng Maven thấy | IDE JUnit Platform config/version khác | Reload Maven dependencies, chọn đúng Platform runner |
| Có JUnit3 legacy tests nhưng runner không thấy | Compatibility khác theo Surefire version | Ưu tiên nâng lên JUnit4.12+ hoặc Jupiter và xác minh reports |
| `@Ignore` vẫn skip test cũ | JUnit4 behavior được giữ | Chỉ bỏ skip sau khi sửa lý do gốc |
| `@Test(timeout)` migration làm transaction residue | Timeout/preemptive thread semantics khác | Thiết kế timeout theo client/transaction boundary |
| Vintage bị xóa trước khi migration hoàn tất | Legacy test coverage biến mất | Engine canary, test inventory, rollback dependency removal |
| Có Vintage nhưng không có JUnit4 code | Bridge tồn tại quá lâu | Audit và gỡ dependency sau migration |

## 11. Đặt tiêu chí CI để không “xanh giả”

Có ít nhất ba quality gates có giá trị:

1. **Engine presence gate:** khi vẫn còn JUnit4 tests, JUnit Platform runtime phải thấy `junit-vintage`; đồng thời Jupiter phải hiện diện cho tests mới. Ví dụ có `EngineDiscoveryTest`.
2. **Execution count gate:** reports phải chứa legacy class names và expected number of invocations, không chỉ `dependency:tree`. Thêm ngưỡng theo module/engine, nhưng điều chỉnh có kiểm soát khi migration làm tăng/giảm tests.
3. **Behavior gate:** với một behavior quan trọng, bản Jupiter thay thế phải kiểm cùng invariants/negative cases. Hai tests chạy không bằng chứng chúng assert cùng nghiệp vụ.

### Không hardcode tổng count vĩnh viễn

Trong project sample, **17 invocations** là expected theo 5 classes ở phần 6. Trong production suite, số test thay đổi hợp lý khi thêm/cắt coverage; dùng **baseline review/gate có cập nhật rõ trong PR**, không coi mọi count change là failure tuyệt đối. Đặc biệt `@ParameterizedTest` hoặc JUnit4 Parameterized Runner tạo số cases khác method declarations.

Một report có thể chứa **skipped tests** do `@Ignore`/`@Disabled`; ghi rõ số executed, skipped, failures/errors. Nếu test mới được disabled để chuyển nhanh, total discovered vẫn có thể trông cao nhưng coverage thực giảm.

### Không bỏ qua test không có engine

Khi một module chứa **chỉ JUnit4 tests**, có thể thấy Surefire báo không có test thực thi nếu Vintage không được load/selection không phù hợp. Build plugin options về `failIfNoTests`/`failIfNoSpecifiedTests` tùy Surefire version; cần kiểm cấu hình hiện tại. CI nên coi “module quan trọng có zero executed tests” là lỗi, bất kể Maven task có exit code 0 hay không.

### Chạy Maven/Failsafe đúng phạm vi

`mvn test` dùng Surefire mặc định; nếu project có integration tests chạy bởi Failsafe, cần `mvn verify`. Nếu multi-module reactor có những modules không có JUnit4, cần phân biệt thiếu test hợp lệ với thiếu test do engine config. Không ép mọi module phải có Vintage: chỉ giữ bridge ở modules chưa migrate.

## 12. Checklist trước khi kết luận giai đoạn bridge thành công

- [ ] Dự án dùng Java 17+ và các phiên bản Spring Boot/JUnit/Surefire tương thích.
- [ ] Tôi hiểu JUnit Platform là launcher, Jupiter và Vintage là hai engines riêng.
- [ ] `spring-boot-starter-test` cung cấp Jupiter nhưng **Vintage được khai test runtime rõ ràng**.
- [ ] Có `junit:junit:4.13.2` cho test source JUnit4.
- [ ] JUnit Platform/Jupiter/Vintage artifacts được đồng bộ qua Spring Boot BOM.
- [ ] Đã xem dependency tree để tránh JUnit/Hamcrest conflicts.
- [ ] Surefire hoặc Gradle được cấu hình chạy JUnit Platform.
- [ ] Không có engine filter vô tình loại `junit-vintage` trong job tổng.
- [ ] File patterns/class names legacy được Surefire/Failsafe discover.
- [ ] JUnit4 `@Test` import `org.junit.Test`, Jupiter test import `org.junit.jupiter.api.Test`.
- [ ] Spring Boot JUnit4 classes dùng `@RunWith(SpringRunner.class)`.
- [ ] Jupiter Spring Boot classes dùng `@SpringBootTest`/SpringExtension, không giữ @RunWith.
- [ ] Legacy `@Rule`, `@ClassRule`, custom Runner vẫn được Vintage giữ semantics đến khi chuyển.
- [ ] JUnit4 Parameterized test cases được đếm theo **invocations**, không chỉ test methods.
- [ ] JUnit4 `@Category` tag mapping được tính khi dùng groups/tag filters.
- [ ] Có canary/CI gate chứng minh cả hai engines discoverable khi cần.
- [ ] Surefire reports cho thấy các legacy classes thật sự được thực thi.
- [ ] Không suy build xanh là mọi legacy tests đã chạy.
- [ ] Bật cả hai engines không đồng nghĩa bật parallel threads.
- [ ] Vintage/Jupiter parallel settings được đánh giá riêng; chưa bật concurrency trước khi audit isolation.
- [ ] Spring context cache, `@DirtiesContext`, mutable singleton, DB/Redis/Kafka/file fixtures được xử lý đúng.
- [ ] Test mới chỉ dùng Jupiter; có lộ trình giảm số legacy tests.
- [ ] Mỗi lần convert class đều có regression behavior và case-count comparison.
- [ ] Sau khi hết legacy, gỡ Vintage/JUnit4 dependencies và cập nhật engine canary/CI filters.
- [ ] Có kiểm `mvn verify` khi còn Failsafe integration tests.
- [ ] Không giữ dependency bridge vĩnh viễn chỉ vì “đang chạy được”.

**Kết luận:** **JUnit Vintage** là giải pháp thực tế để **duy trì JUnit4 regression tests trong lúc chuyển từng phần sang JUnit Jupiter** trên cùng JUnit Platform. Nó **không tự nâng cấp code, không tự thêm SpringRunner, không đồng bộ @Rule với Jupiter và không mặc định làm tests chạy đồng thời**. Chất lượng migration nằm ở **đúng dependencies/engine discovery, đúng test execution counts, đúng Spring test lifecycle, fixture isolation và kế hoạch loại bỏ bridge có kiểm soát**.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing và Vintage Engine](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html)
- [Spring Boot 3.5 — @SpringBootTest với JUnit4 SpringRunner và JUnit5](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit 5.12 — User Guide: Migrating from JUnit4, Vintage Engine, Categories, Parallel Execution](https://docs.junit.org/5.12.0/user-guide/)
- [JUnit 5.12 — JUnit Platform Launcher API](https://junit.org/junit5/docs/5.12.0/api/org.junit.platform.launcher/org/junit/platform/launcher/core/LauncherFactory.html)
- [Maven Surefire — JUnit Platform, Engine Filtering](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire — Configuring JUnit](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit.html)
- [Spring Framework 6.2 — Spring TestContext Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html)
