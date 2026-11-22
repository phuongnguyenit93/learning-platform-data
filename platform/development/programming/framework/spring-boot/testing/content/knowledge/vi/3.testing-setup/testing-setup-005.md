# JUnit Platform, Jupiter và Vintage trong quá trình phát hiện test

## 1. Vì sao cần phân biệt ba thành phần?

Trong một dự án Spring Boot, việc viết một phương thức có tên bắt đầu bằng test hoặc gắn một annotation Test chưa bảo đảm phương thức ấy được chạy. Trình chạy kiểm thử phải **phát hiện** được phương thức, hiểu nó thuộc hệ sinh thái JUnit nào và tìm được bộ máy có khả năng thực thi nó.

Ở thế hệ JUnit 5 thường được dùng cùng Spring Boot 3.3.x, cần phân biệt:

| Thành phần | Vai trò chính | Bản thân có định nghĩa annotation kiểm thử không? | Chịu trách nhiệm với test nào? |
|---|---|---|---|
| **JUnit Platform** | Nền tảng để công cụ build/IDE khám phá, lọc, lập kế hoạch, chạy và nhận kết quả từ các test engine | Không; cung cấp API launcher, engine, selector, listener | Điều phối nhiều engine |
| **JUnit Jupiter** | Mô hình lập trình và engine cho test kiểu JUnit 5 | Có: org.junit.jupiter.api.Test, BeforeEach, ParameterizedTest, Nested… | Test viết bằng API Jupiter |
| **JUnit Vintage** | Engine tương thích để chạy lại JUnit 3/4 trên JUnit Platform | Không tạo phong cách test mới; sử dụng API JUnit 3/4 hiện có | Test JUnit 3 (TestCase) và JUnit 4 (org.junit.Test, runner…) |

Điểm cần nhớ: **JUnit Platform không tự hiểu mọi annotation Test.** Nó tìm các triển khai giao diện TestEngine rồi ủy quyền quá trình phát hiện và thực thi. Jupiter và Vintage là hai engine khác nhau. Một dự án có thư viện JUnit 4 trên classpath nhưng thiếu Vintage engine sẽ không tự động biến test JUnit 4 thành test Jupiter.

Trong JUnit 5, các engine thường có ID:
- **junit-jupiter:** Jupiter engine.
- **junit-vintage:** Vintage engine.

Tên “JUnit 5” thường được dùng để nói về cả hệ sinh thái Platform + Jupiter và khả năng tương thích Vintage. Bài này mô tả kiến trúc JUnit 5 phù hợp với ví dụ Spring Boot 3.3.x/Java 17; không giả định mọi phiên bản Spring Boot hay JUnit về sau có cùng danh sách dependency mặc định.

## 2. Từ lệnh test đến danh sách test được phát hiện

Luồng tiêu biểu:

~~~text
IDE / Gradle Test task / Maven Surefire
                 |
                 | tạo yêu cầu khám phá và cấu hình launcher
                 v
         JUnit Platform Launcher
                 |
                 | selectors: class, package, method, classpath roots...
                 | filters: engine, tag, package, class name...
                 v
          Các TestEngine khả dụng
            /              \
           v                v
  Jupiter TestEngine   Vintage TestEngine
  @Jupiter Test        JUnit 3/4 Test
           \                /
            v              v
      Cây TestDescriptor / TestPlan
                 |
                 | execute(request)
                 v
      TestExecutionListener / báo cáo
~~~

Có hai giai đoạn khác nhau:

**Discovery (khám phá):** Launcher nhận LauncherDiscoveryRequest, tìm các TestEngine đã đăng ký và nhờ từng engine nhận diện những test phù hợp với selector/filter. Kết quả có cấu trúc cây: engine → container (thường là class/nested class) → test. Có thể gọi launcher.discover(request) để xem kế hoạch **mà chưa chạy thân phương thức test**.

**Execution (thực thi):** Launcher giao việc chạy cho các engine theo request; engine xử lý vòng đời, assertion, exception và báo kết quả qua listener. Các báo cáo Gradle/Maven/IDE được tạo từ sự kiện chạy test, không đơn giản từ số file Java có tên Test.

Ở mức API, một TestEngine có trách nhiệm nhận EngineDiscoveryRequest để tạo cây TestDescriptor, sau đó thực thi các nút thông qua ExecutionRequest. Trong ứng dụng thông thường, ta không cần tự viết engine; Gradle/Maven/IDE và JUnit Platform đã xử lý lớp điều phối.

**Phân biệt ba lớp lọc:**

1. **Nguồn test:** Công cụ build biên dịch và cung cấp classpath/test classes từ source set hoặc thư mục test. File không được biên dịch, bị exclude hoặc không nằm trên test runtime classpath thì Platform không thể chạy.
2. **Discovery selectors:** Chỉ ra nơi cần tìm, chẳng hạn một class, package, method hoặc các classpath root. Selector chưa khẳng định nơi đó thực sự chứa test.
3. **Discovery filters:** Thu hẹp kết quả theo engine ID, tag, class/package, tên… Những bộ lọc riêng của Gradle (ví dụ --tests) hoặc Maven cũng có thể tiếp tục giới hạn tập chạy.

Sau đó **engine** quyết định liệu class/method có thuộc dạng test nó hỗ trợ không. Có mặt trên classpath không có nghĩa là được phát hiện.

## 3. Jupiter phát hiện những gì?

Jupiter nhận diện annotation trong namespace **org.junit.jupiter** như Test, RepeatedTest, ParameterizedTest, TestFactory, TestTemplate; đồng thời xử lý cấu trúc Nested và các extension của Jupiter.

Ví dụ tối thiểu:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SumJupiterTest {
    @Test
    void sumsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
~~~

Ở đây import là **org.junit.jupiter.api.Test**, class và method có thể package-private; Jupiter engine nhận ra test theo annotation, không cần phương thức tên testSomething.

Một vài chi tiết quan trọng khi đọc cây discovery:

- **@Nested** tạo quan hệ container lồng nhau để tổ chức các test con; với Jupiter, nested test class thường là inner class không static.
- **@ParameterizedTest** được nhận diện như một test template; từng invocation được xử lý khi thực thi. Đừng mặc định mỗi annotation tương đương một test case cuối cùng.
- **@TestFactory** mô tả factory tạo dynamic tests; những test động có thể được đăng ký **trong lúc execution**, nên số lượng test trong TestPlan khi discover có thể khác số test đã hoàn thành.
- **@Disabled** không đồng nghĩa “không discover”: test có thể vẫn nằm trong kế hoạch nhưng được thông báo là skipped khi thực thi.
- Jupiter hỗ trợ lifecycle callback, extension, điều kiện enable/disable, thứ tự test; các cơ chế đó không biến một class JUnit 4 thành Jupiter test.

Trong Spring Boot, spring-boot-starter-test thường cung cấp Jupiter cùng Mockito, AssertJ, Spring Test, MockMvc support (khi có web stack) và các thành phần phục vụ kiểm thử. Có dependency **Jupiter API** để biên dịch annotation chưa đủ nếu **Jupiter engine** không có trên runtime classpath.

## 4. Vintage phát hiện những gì?

Vintage engine mang khả năng thực thi test theo quy ước cũ vào JUnit Platform:

- **JUnit 4:** phương thức có org.junit.Test; runner thông qua @RunWith, JUnit 4 Rules, Before/After và các tính năng tương thích.
- **JUnit 3:** class kế thừa junit.framework.TestCase và phương thức test* theo quy ước của JUnit 3.

Ví dụ JUnit 4:

~~~java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class SumLegacyTest {
    @Test
    public void sumsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
~~~

Dù chữ Test trông giống ví dụ trước, đây là **org.junit.Test**, không phải org.junit.jupiter.api.Test. JUnit 4 thường yêu cầu class test và phương thức kiểm thử public khi sử dụng runner mặc định. JUnit 4 và Jupiter có bộ annotation/assertion/lifecycle khác nhau:

| Ý định | JUnit 4 | Jupiter |
|---|---|---|
| Đánh dấu test | org.junit.Test | org.junit.jupiter.api.Test |
| Trước mỗi test | @Before | @BeforeEach |
| Sau mỗi test | @After | @AfterEach |
| Trước tất cả test | @BeforeClass, phương thức static | @BeforeAll, thường static (trừ cấu hình lifecycle phù hợp) |
| Phụ thuộc mở rộng Spring Test truyền thống | @RunWith(SpringRunner.class) | @ExtendWith(SpringExtension.class), hoặc annotation Spring Boot đã meta-annotate tương ứng |
| Kiểm tra exception | @Test(expected = ...) hoặc ExpectedException | assertThrows(...) |
| Phân nhóm | @Category | @Tag |

**Vintage không phải thành phần bắt buộc của dự án mới.** Nó hữu ích trong giai đoạn chuyển JUnit 3/4 sang Jupiter. Khi không còn legacy test, bỏ engine Vintage và dependency JUnit 4 giúp giảm độ phức tạp của classpath. Nhưng bỏ Vintage **trước** khi chuyển hết test có thể khiến một phần bài kiểm thử không được thực thi, tạo cảm giác build xanh sai lệch.

JUnit Platform còn hỗ trợ các TestEngine khác. Hai engine trong bài là ví dụ phổ biến, không phải danh sách đầy đủ. JUnit Platform Suite có engine riêng khi dùng suite API; không nên nhầm một suite engine với Jupiter/Vintage.

## 5. Ví dụ chạy được: Spring Boot + Gradle + hai engine

Tạo một dự án Java 17+, Gradle 8.x, Spring Boot 3.3.5. Cấu trúc tệp:

~~~text
build.gradle
settings.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/PriceCalculator.java
src/test/java/demo/testing/PriceCalculatorJupiterTest.java
src/test/java/demo/testing/PriceCalculatorLegacyTest.java
src/test/java/demo/testing/DiscoveryProbe.java
~~~

Ví dụ cố ý giữ một test JUnit 4 để minh họa Vintage; dự án mới chỉ sử dụng Jupiter có thể bỏ các dependency legacy.

**settings.gradle**

~~~groovy
rootProject.name = 'junit-engine-discovery-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    // Jupiter và các tiện ích test được quản lý qua Spring Boot.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Hai dependency này chỉ cần khi còn test JUnit 4.
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'

    // Probe bên dưới gọi trực tiếp Launcher API khi biên dịch.
    testImplementation 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}

// Task độc lập để xem discovery mà không chạy test methods.
tasks.register('discoverTests', JavaExec) {
    dependsOn tasks.named('testClasses')
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.testing.DiscoveryProbe'
}
~~~

**Vì sao các khai báo này cần thiết?**

- Gradle test task với **useJUnitPlatform()** giao quá trình chạy test cho JUnit Platform. Nếu bỏ nó trong cấu hình Gradle sử dụng cơ chế JUnit 4 mặc định, Jupiter test có thể không được chạy.
- spring-boot-starter-test cung cấp các thư viện kiểm thử mà Spring Boot quản lý phiên bản, trong đó có Jupiter. Spring Boot BOM quản lý phiên bản của JUnit Platform/Jupiter/Vintage khi dùng dependency management như trên.
- junit:junit:4.13.2 cho phép compile test kiểu JUnit 4.
- junit-vintage-engine ở **testRuntimeOnly** giúp Platform tìm được engine chạy test JUnit 4.
- junit-platform-launcher ở **testImplementation** vì DiscoveryProbe trực tiếp import Launcher API trong source test. Nếu chỉ chạy qua Gradle và không tự viết probe thì thường chỉ cần launcher trên test runtime classpath.
- Tập hợp các engine thực sự chạy phụ thuộc vào test runtime classpath và các bộ lọc; **useJUnitPlatform() không tự cài Vintage**.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/PriceCalculator.java**

~~~java
package demo.testing;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static long totalWithFee(long price, long fee) {
        if (price < 0 || fee < 0) {
            throw new IllegalArgumentException("Price and fee must be non-negative");
        }
        return Math.addExact(price, fee);
    }
}
~~~

Đây là đối tượng kiểm thử thuần Java trong dự án Spring Boot, giúp ta quan sát rõ cơ chế phát hiện test mà không cần khởi động ApplicationContext. Kiểm thử Spring context như @SpringBootTest cũng được phát hiện bởi engine tương ứng; SpringExtension xử lý phần tích hợp Spring trong quá trình thực thi.

**src/test/java/demo/testing/PriceCalculatorJupiterTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorJupiterTest {

    @Test
    void addsFee() {
        assertEquals(125L, PriceCalculator.totalWithFee(100L, 25L));
    }

    @Test
    void rejectsNegativeFee() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalWithFee(100L, -1L)
        );
    }
}
~~~

Class và method không khai báo public nhưng Jupiter vẫn discover được hai phương thức Test.

**src/test/java/demo/testing/PriceCalculatorLegacyTest.java**

~~~java
package demo.testing;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class PriceCalculatorLegacyTest {

    @Test
    public void addsFee() {
        assertEquals(125L, PriceCalculator.totalWithFee(100L, 25L));
    }
}
~~~

Đây là một JUnit 4 test. Vintage phải có mặt để Launcher chạy nó cùng hai test Jupiter khi dùng JUnit Platform.

**src/test/java/demo/testing/DiscoveryProbe.java**

~~~java
package demo.testing;

import org.junit.platform.engine.discovery.DiscoverySelectors;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

public final class DiscoveryProbe {
    private DiscoveryProbe() {
    }

    public static void main(String[] args) {
        LauncherDiscoveryRequest request =
            LauncherDiscoveryRequestBuilder.request()
                .selectors(
                    DiscoverySelectors.selectClass(
                        PriceCalculatorJupiterTest.class
                    ),
                    DiscoverySelectors.selectClass(
                        PriceCalculatorLegacyTest.class
                    )
                )
                .build();

        Launcher launcher = LauncherFactory.create();
        TestPlan plan = launcher.discover(request);

        plan.getRoots().stream()
            .map(TestIdentifier::getUniqueId)
            .sorted()
            .forEach(System.out::println);

        System.out.println(
            "Discovered test nodes: "
                + plan.countTestIdentifiers(TestIdentifier::isTest)
        );
    }
}
~~~

LauncherFactory tìm những TestEngine có trên runtime classpath. Request chọn **chính xác hai class** nên ví dụ không phụ thuộc vào việc quét package rộng hơn. plan.getRoots() cho biết các engine có test được phát hiện; countTestIdentifiers(TestIdentifier::isTest) đếm các nút test của kế hoạch. Probe gọi **discover**, không gọi execute, nên thân các phương thức test không chạy.

Chạy bằng Gradle Wrapper của dự án (nếu tạo thủ công từ các tệp trên, cần có Gradle/Gradle Wrapper được cài hoặc tạo trước):

~~~bash
./gradlew discoverTests
./gradlew test
~~~

Trên Windows PowerShell với Gradle Wrapper:

~~~powershell
.\gradlew.bat discoverTests
.\gradlew.bat test
~~~

Phần output do **DiscoveryProbe** in ra (các dòng khác của Gradle có thể xuất hiện):

~~~text
[engine:junit-jupiter]
[engine:junit-vintage]
Discovered test nodes: 3
~~~

Khi chạy Gradle test task, cả ba test đều pass. Để xem báo cáo HTML, mở **build/reports/tests/test/index.html**. Console của Gradle có thêm trạng thái task và thông báo BUILD SUCCESSFUL khi build thành công, nhưng chi tiết hiển thị phụ thuộc Gradle/logging.

Có thể chạy có chọn lọc:

~~~bash
./gradlew test --tests demo.testing.PriceCalculatorJupiterTest
./gradlew test --tests demo.testing.PriceCalculatorLegacyTest
~~~

Khi chạy hai lệnh liên tiếp, Gradle có thể dùng cache/up-to-date hoặc thực thi lại tùy tập filter và đầu vào task; điều cần kiểm tra là test được chọn có xuất hiện trong báo cáo. Nếu bỏ Vintage engine, lệnh chọn riêng test JUnit 4 có thể báo không tìm thấy test khớp bộ lọc. Việc source JUnit 4 vẫn biên dịch thành công **không chứng minh nó đã chạy**.

## 6. Dùng selector và filter đúng cách

Bài demo đã dùng **selectClass** để đảm bảo chỉ tìm hai class. Trong dự án có nhiều test, ta có thể dùng selector khác:

~~~java
// Ví dụ API đặt trong code đã có LauncherDiscoveryRequestBuilder.
LauncherDiscoveryRequest request =
    LauncherDiscoveryRequestBuilder.request()
        .selectors(
            DiscoverySelectors.selectPackage("demo.testing")
        )
        .build();
~~~

Đoạn trên là **minh họa API**, không phải một tệp Java độc lập; cần các import tương ứng và classpath đã cấu hình. Nó yêu cầu tìm test trong package, còn engine sẽ xác định các class nào là test. Không phải mọi class trong package đều thành test.

Một số selector thường gặp:

| Selector | Ý định |
|---|---|
| selectClass(MyTest.class) | Chỉ định một class ứng viên |
| selectMethod("demo.testing.MyTest#caseName()") | Chỉ định phương thức kiểm thử |
| selectPackage("demo.testing") | Khám phá theo package |
| selectClasspathRoots(Set<Path>) | Khám phá các classpath root xác định |

Có thể giới hạn engine ở tầng Launcher bằng **EngineFilter.includeEngines("junit-jupiter")** trong LauncherDiscoveryRequestBuilder.filters(...). Phạm vi ID ở đây chính là tên engine, không phải tên artifact Maven.

Với Gradle, có thể đặt engine filter trong test task:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-jupiter'
    }
}
~~~

**Đây là cấu hình thay thế**, không áp dụng đồng thời với cấu hình chạy cả hai engine ở ví dụ trên. Khi dùng chỉ Jupiter, test JUnit 4 không được chạy dù vintage-engine vẫn có trong dependencies. Để chạy cả hai, dùng useJUnitPlatform() không lọc hoặc chỉ định cả junit-jupiter và junit-vintage.

Các bộ lọc về **tag** và **class/package** hoạt động ở giai đoạn lựa chọn test; @Disabled của Jupiter thường gây trạng thái skipped khi chạy chứ không phải xóa luôn test khỏi quá trình khám phá. Đừng đánh đồng “được discover”, “được chọn để execute”, “đã execute”, “pass” và “skipped”.

## 7. TestPlan, TestIdentifier và cách đếm test

Một TestPlan biểu diễn các nút:
- **Engine root:** chẳng hạn unique ID [engine:junit-jupiter] hoặc [engine:junit-vintage].
- **Container:** class hoặc nhóm test, bao gồm nested class và những cấp trung gian do engine tạo.
- **Test node:** đơn vị test được biểu diễn trong kế hoạch.

Mỗi TestIdentifier có unique ID, display name và các thuộc tính như isTest()/isContainer(). Unique ID giúp engine định danh phần tử trong cây; display name phục vụ trình bày và có thể thay đổi. Không nên dựa vào text của display name làm khóa bền vững.

Một class chứa hai phương thức Jupiter @Test và một class chứa một phương thức JUnit 4 @Test trong ví dụ tạo ba test node lúc discover. Nhưng con số này **không phải công thức chung**: dynamic tests tạo bởi @TestFactory có thể xuất hiện khi execute, parameterized/repeated tests có nhiều invocation và engine có quyền cấu trúc descriptor theo mô hình riêng. Để đánh giá số test **đã chạy/thành công/thất bại/bị bỏ qua**, xem TestExecutionSummary, listener hoặc báo cáo test cuối cùng.

Có thể đăng ký SummaryGeneratingListener khi dùng Launcher API: listener được cung cấp cho launcher, sau đó gọi execute(request) và lấy summary. Bước đó thực thi test thật; không nên lẫn nó với lời gọi discover(request) phía trên.

## 8. Spring Boot Test và việc chọn engine

Spring Boot Test không thay thế JUnit Platform. Nó cung cấp cơ chế quản lý ApplicationContext, dependency injection, transaction, MockMvc/WebTestClient, test slices và SpringExtension tùy annotation.

Ví dụ với JUnit Jupiter:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextJupiterTest {

    @Test
    void contextLoads() {
        // Spring Boot khởi động ApplicationContext trước khi test chạy.
    }
}
~~~

Ở Spring Boot 3.3.x, SpringBootTest tích hợp SpringExtension cho Jupiter. **Jupiter engine** vẫn là thành phần phát hiện annotation org.junit.jupiter.api.Test; SpringExtension không phải TestEngine độc lập. Với test Spring viết theo JUnit 4, mẫu cũ thường sử dụng @RunWith(SpringRunner.class) và org.junit.Test; khi chạy trên Platform, **Vintage engine** xử lý test ấy. Vì vậy cùng một dự án Spring Boot có thể chứa cả Jupiter và Vintage trong giai đoạn chuyển đổi.

Các annotation như @MockBean (trong phạm vi phiên bản Spring Boot ở ví dụ), @Transactional hay @ActiveProfiles điều chỉnh cách test dùng Spring context, **không tự chọn JUnit Platform engine**. Điều quyết định engine vẫn là kiểu test API/runner, các dependency và cấu hình launcher/filter.

## 9. Maven Surefire và IDE: cùng mục tiêu, cách khởi chạy khác

Nếu dự án dùng Maven thay cho Gradle, Maven Surefire có hỗ trợ JUnit Platform (chọn provider phù hợp khi có JUnit Platform engine); với Spring Boot 3.3.x dùng Spring Boot parent/BOM, các phiên bản JUnit được quản lý theo bộ phù hợp. Mẫu dependencies cần Jupiter, và chỉ thêm JUnit 4/Vintage nếu còn legacy tests:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ dùng khi còn test JUnit 4. -->
    <dependency>
        <groupId>junit</groupId>
        <artifactId>junit</artifactId>
        <version>4.13.2</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.vintage</groupId>
        <artifactId>junit-vintage-engine</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Snippet này là **phần dependencies của một pom.xml**, không phải POM hoàn chỉnh. Cần parent/BOM của Spring Boot và Maven Surefire có khả năng chạy JUnit Platform. Maven còn có quy tắc tên class mặc định để tìm test, ví dụ Test*, *Test, *Tests và *TestCase; tên hoặc include/exclude sai có thể khiến test không được chọn. Gradle và Maven có cách cấu hình lọc khác nhau, dù cuối cùng đều có thể sử dụng JUnit Platform.

IDE như IntelliJ IDEA hay Eclipse có thể tạo LauncherDiscoveryRequest khác với công cụ build (ví dụ chọn một class hay method thay vì cả package). Do đó “chạy được khi bấm nút ở IDE” chưa chắc đồng nghĩa “chạy trong CI”. Luôn xác minh bằng đúng lệnh Gradle/Maven của pipeline.

## 10. Cách chẩn đoán trường hợp “không tìm thấy test”

| Triệu chứng | Khả năng cần kiểm tra | Hành động |
|---|---|---|
| Jupiter test bị bỏ qua khi dùng Gradle | test task chưa cấu hình useJUnitPlatform; thiếu Jupiter engine | Bật useJUnitPlatform, kiểm tra runtime dependency của Jupiter |
| Test JUnit 4 vẫn compile nhưng không chạy | Không có junit-vintage-engine hoặc bị lọc loại junit-vintage | Giữ Vintage trong giai đoạn chuyển đổi; kiểm tra engine ID/filter |
| Chạy --tests tên class cụ thể báo không khớp | Sai tên package/class, test bị loại bởi filter, hoặc engine không phát hiện class | Kiểm tra testClasses, classpath, import @Test và tên pattern |
| Test report có 0 tests nhưng build xanh | Source set không chứa class test phù hợp, matcher/engine lọc sạch | Kiểm tra cả danh sách test **thực sự đã chạy**, không chỉ exit code |
| Test JUnit 4 bị lỗi “No runnable methods” | Dùng nhầm import, phương thức/class không đáp ứng quy tắc JUnit 4, runner sai | Xem annotation namespace và yêu cầu public của JUnit 4 |
| Test lẽ ra có nhiều case nhưng discovery đếm ít | Parameterized/dynamic tests đăng ký invocation khi execution | Đối chiếu test report/số invocation sau chạy |
| Chạy trong IDE khác chạy trong CI | IDE chọn class cụ thể; CI dùng include/exclude, engine filter hoặc dependency khác | Chạy lại lệnh build của CI và so sánh classpath, bộ lọc |
| Lỗi không khởi động được test engine | Version Platform/Jupiter/Vintage lệch nhau hoặc trộn thủ công dependency không tương thích | Dùng BOM/management của Spring Boot, kiểm tra dependency graph |

Các lệnh hỗ trợ với Gradle:

~~~bash
./gradlew test --info
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests demo.testing.PriceCalculatorLegacyTest
~~~

Chú ý: chế độ --info có thể in nhiều dòng; tìm thông tin về task, test class, filter và lỗi thực tế. Danh sách test runtime dependencies cho biết có cả junit-jupiter-engine và junit-vintage-engine hay không. Ở dự án nhiều module, chạy đúng task test của module cần kiểm tra, không giả định task gốc bao phủ mọi module.

Nếu một test không chạy, nên kiểm tra theo thứ tự: **(1) đã biên dịch vào test source set chưa → (2) task build có chọn phạm vi đó không → (3) JUnit Platform có được dùng không → (4) runtime có engine thích hợp không → (5) annotation/runner thuộc Jupiter hay JUnit 4 → (6) selectors/filters có loại test không → (7) test được discover nhưng bị disabled/skipped hay đã thực thi thất bại?** Cách này phân biệt lỗi discovery với lỗi assertion hoặc lỗi Spring ApplicationContext.

## 11. Chiến lược chuyển JUnit 4 sang Jupiter mà không mất test

1. **Đo đường cơ sở:** Ghi số lượng test thực sự chạy và báo cáo pass/fail/skipped trong CI trước khi sửa. Bảo đảm Vintage được bật nếu còn test JUnit 4.
2. **Cho hai engine chạy cùng lúc:** Bật useJUnitPlatform và giữ cả Jupiter lẫn Vintage trên test runtime classpath. Một test chỉ nên viết theo một hệ annotation/runner rõ ràng.
3. **Di chuyển có kiểm soát:** Đổi import org.junit.Test sang org.junit.jupiter.api.Test; đổi lifecycle annotation; chuyển @RunWith/Rule sang Jupiter extension/API tương ứng; thay expected exception bằng assertThrows khi phù hợp. Không chỉ đổi import rồi cho rằng ngữ nghĩa của Rule, parameterized runner và lifecycle tự động tương đương.
4. **So báo cáo trước và sau:** Bảo đảm phạm vi kiểm thử và assertion được giữ. Nếu số test giảm, xác định nguyên nhân bằng discovery/filter/report trước khi xóa dependency.
5. **Gỡ Vintage cuối cùng:** Sau khi xác nhận không còn JUnit 3/4 test cần chạy, bỏ junit-vintage-engine và các dependency JUnit 4 không còn sử dụng. Chạy test và xác minh lại kết quả trên CI.

Trong dự án mới không có bài kiểm thử cũ, chọn Jupiter làm mặc định. Vintage là **cầu nối tương thích**, không phải lựa chọn bắt buộc cho “JUnit Platform đầy đủ”.

## 12. Ghi nhớ để tự đánh giá

- JUnit Platform là **hạ tầng phát hiện/chạy test**; Jupiter và Vintage là **hai TestEngine**. Một annotation Test chỉ có ý nghĩa khi đúng engine nhận ra.
- **Jupiter** nhận org.junit.jupiter.api.Test và các API Jupiter; **Vintage** nhận JUnit 3/4. Spring Boot starter-test giúp thiết lập Jupiter, nhưng test JUnit 4 cần Vintage riêng nếu vẫn chạy qua Platform.
- **Selector** trả lời “tìm ở đâu”; **filter** trả lời “giữ lại cái gì”; **engine** trả lời “class/method này có phải test mà tôi hỗ trợ không”. Discovery tạo TestPlan; execution mới chạy phương thức và phát sinh pass/fail/skipped.
- Kiểm tra **test count và report thật** trên công cụ CI; một build xanh không đủ bảo đảm mọi bài test cũ đã được phát hiện sau khi đổi engine hoặc dependency.
- Nếu dùng @ParameterizedTest/@TestFactory, đừng coi số nút ở discovery là số invocation thực tế; dùng kết quả execution để kết luận độ bao phủ.

Bài tập tự kiểm tra: trong ví dụ, thử tạm loại junit-vintage-engine khỏi test runtime classpath, chạy discoverTests và test (sau khi đã ghi nhận baseline), rồi khôi phục dependency. Hãy giải thích vì sao JUnit 4 class vẫn biên dịch nhưng không còn xuất hiện trong TestPlan. Sau đó thử cấu hình includeEngines chỉ junit-jupiter và quan sát khác biệt giữa **có engine trên classpath** với **engine được phép tham gia discovery**.