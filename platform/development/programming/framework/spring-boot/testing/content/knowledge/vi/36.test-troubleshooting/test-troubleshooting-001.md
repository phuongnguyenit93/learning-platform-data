# Test không được phát hiện do engine, classpath, tên hoặc bộ lọc

## 1. Hiện tượng: BUILD SUCCESSFUL nhưng không có bài kiểm thử nào chạy

Trong module **Spring Boot - testing**, nhóm **Chẩn đoán lỗi kiểm thử**, một lỗi nguy hiểm là dự án có source test, IDE nhìn thấy phương thức `@Test`, nhưng lệnh chạy CI không thực thi ca nào. Build có thể hoàn tất mà không thực sự kiểm thử hành vi; hoặc chỉ một nhóm tests chạy, còn nhóm khác bị bỏ qua âm thầm.

Những ví dụ thường gặp:

- Có `import org.junit.jupiter.api.Test`, source compile được, nhưng runtime không có **JUnit Jupiter TestEngine**.
- Gradle dùng `testImplementation 'spring-boot-starter-test'` nhưng quên `useJUnitPlatform()`.
- File ở `src/integrationTest/java` nhưng dự án chỉ cấu hình mặc định `test` source set.
- Một lớp JUnit 4 dùng `org.junit.Test` trong khi test task chỉ bật Jupiter engine, **không có JUnit Vintage**.
- Maven Surefire không chọn `InvoiceSpec.java` theo bộ mẫu tên mặc định.
- Test đã được discovery nhưng `@Disabled` hoặc condition vô hiệu hóa trước khi thực thi.
- Gradle `--tests`, `includeTags`, `excludeTags` hoặc file/class include/exclude patterns lọc hết tests.
- Task `:moduleA:test` đang chạy, trong khi test ở `moduleB`.
- Gradle hiện `UP-TO-DATE` hoặc `FROM-CACHE`: task không chạy lại ở lượt hiện tại, không phải bằng chứng “không có test”.
- IDE sử dụng runner/JDK/classpath khác với Gradle hoặc Maven nên hai nơi nhìn thấy bộ tests khác nhau.

**Mục tiêu:** tìm đúng chặng nơi bài kiểm thử biến mất: source → compilation → test runtime classpath → launcher/engine → discovery → filtering → execution → report. Không chữa lỗi bằng cách thêm `@SpringBootTest` vào mọi lớp hoặc tắt filter một cách mù quáng.

Bài dùng **Java 17, Spring Boot 3.3.0, Gradle 8.x, JUnit Jupiter 5, JUnit Platform** cho ví dụ runnable; có thêm hướng dẫn **Maven Surefire** và JUnit 4 Vintage. Phần thực hành gồm positive tests (test thật được chạy) và negative diagnostics (các cấu hình sai được trình bày riêng, **không đặt trong nguồn runnable**). Chúng ta phân biệt **kết quả dự kiến** với các kết quả Gradle/JUnit đã thực thi thực tế.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **test có trong source**, **compile được**, **được discover**, **được select**, **được execute** và **pass**.
2. Biết API `@Test` và runtime **TestEngine** thuộc hai tầng khác nhau.
3. Giải thích ba phần `JUnit Platform`, `JUnit Jupiter` và `JUnit Vintage`.
4. Hiểu vai trò JUnit Platform Launcher và test runner Gradle/Maven/IDE.
5. Dùng đúng `org.junit.jupiter.api.Test` cho JUnit Jupiter.
6. Biết tại sao `org.junit.Test` thuộc JUnit 4 cần Vintage nếu chạy qua Platform.
7. Cấu hình `useJUnitPlatform()` và `junit-platform-launcher` trong Gradle.
8. Đọc `testRuntimeClasspath`, `testCompileClasspath` và dependency tree để tìm engine thiếu/lệch version.
9. Kiểm tra compile outputs ở `build/classes/java/test` và Gradle `test` source set.
10. Phân biệt quy tắc tên test của **Maven Surefire** với JUnit Platform/Gradle.
11. Biết JUnit Jupiter test class/method không cần `public`, nhưng không được `private`.
12. Viết `@Test` không `static`, không trả value; biết trường hợp ngoại lệ `@TestFactory` trả dynamic tests.
13. Dùng `@ParameterizedTest`, `@CsvSource` và hiểu một method tạo nhiều invocations.
14. Dùng `@Nested` đúng: inner class không static và được chú thích `@Nested`.
15. Biết `@Disabled`/conditions là **skip sau khi chọn/discover**, không phải engine mất.
16. Phân biệt include/exclude tags và Gradle `--tests` filter, biết cách cô lập từng tầng.
17. Hiểu test task `UP-TO-DATE`, `NO-SOURCE`, `SKIPPED`, `FROM-CACHE`, `FAILED`.
18. Dùng `--info`, `--rerun-tasks`, `--tests` và XML/HTML reports để điều tra.
19. Chẩn đoán Maven Surefire `-Dtest`, naming includes, skip flags và plugin versions.
20. Kiểm tra custom `integrationTest` task, source set, classpath và dependencies.
21. Không coi `@SpringBootTest` làm cho test được discover nếu thiếu test engine.
22. Nhận diện classpath conflict, `NoClassDefFoundError` và engine discovery failures.
23. Biết khi nào chạy JUnit Platform ConsoleLauncher để tách runner khỏi build plugin (tùy dependencies).
24. Dựng một “sentinel test” nhỏ để chứng minh runner chạy được rồi khoanh vùng lỗi của các tests khác.
25. Tạo CI guard tránh một thay đổi làm số tests chạy về zero.
26. Viết báo cáo chẩn đoán có commands, version, task, engines, filters, discovered/executed/skipped counts.

## 3. Pipeline từ mã nguồn đến kết quả thực thi

```text
src/test/java/*.java
        |
        v
compileTestJava
        |
        +-- Có class file tại build/classes/java/test?
        |        |
        |        +-- Không -> wrong source set/path or compile failure
        |
        v
Gradle Test task / Maven Surefire / IDE runner
        |
        +-- Runtime classpath
        |       junit-jupiter-api?
        |       junit-jupiter-engine?
        |       junit-platform-launcher?
        |       junit-vintage-engine? (nếu JUnit 4)
        |
        v
JUnit Platform Launcher
        |
        v
TestEngine discovery
        |
        +-- junit-jupiter -> @Test, @Nested,
        |                     @ParameterizedTest, @TestFactory...
        +-- junit-vintage -> JUnit 3/4
        +-- other engines -> test framework tương ứng
        |
        v
Filters and selectors
        |
        +-- class, method, package patterns
        +-- Gradle --tests
        +-- tags include/exclude
        +-- engine include/exclude
        |
        v
Execution
        |
        +-- PASS
        +-- FAIL
        +-- SKIPPED / DISABLED
        |
        v
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

“Test không được phát hiện” chỉ chính xác khi thất bại ở **discovery**. Nếu `@Disabled` bị skip hoặc Gradle chỉ chọn `@Tag("fast")`, tests **có thể đã được discover** nhưng không được execute. Nếu `compileTestJava` fail, chưa tới bước discovery.

### 3.1. Bốn câu hỏi đầu tiên

1. **Đúng dự án, module, task và source set chưa?** Ví dụ `:orders:test` không mặc nhiên chạy `:billing:test`.
2. **Test class đã được biên dịch chưa?** Xem outputs của `compileTestJava`.
3. **Có TestEngine phù hợp trên runtime classpath chưa?** Không chỉ API compile.
4. **Selectors/filters/conditions có cho test chạy không?** Xóa từng filter để thử, không trộn nhiều biến.

### 3.2. Trạng thái Gradle không phải trạng thái JUnit

| Hiển thị Gradle | Ý nghĩa chính | Việc cần làm |
| --- | --- | --- |
| `:test NO-SOURCE` | Task không có nguồn đầu vào test phù hợp | Kiểm tra source set/đường dẫn |
| `:test UP-TO-DATE` | Inputs/outputs không đổi, Gradle không chạy lại task | Nếu cần thực chạy lại, dùng `--rerun-tasks` |
| `:test FROM-CACHE` | Kết quả task được restore từ build cache | Kiểm tra report/đổi invocation nếu cần fresh execution |
| `:test SKIPPED` | Task bị skip vì task condition/skip setting | Kiểm tra `onlyIf`, `-x test`, skip flags |
| `:test FAILED` | Task thất bại, có thể do assertion, process hoặc test detection | Đọc logs/reports, không tự gán “test failure” |
| `BUILD SUCCESSFUL` | Build tasks hoàn tất theo Gradle rules | **Không chứng minh** số test thực thi lớn hơn zero |

Một `@Disabled` JUnit test có thể được ghi là skipped trong JUnit report dù Gradle task `test` không hiển thị `SKIPPED`. Hai tầng trạng thái hoàn toàn khác nhau.

## 4. JUnit 5 là một kiến trúc nhiều module

**JUnit 5** thường được mô tả bằng ba thành phần:

- **JUnit Platform:** nền tảng discovery/execution và Launcher API/SPI, giúp build tools/IDE gọi các engines.
- **JUnit Jupiter:** API lập trình (`@Test`, `@Nested`, `@ParameterizedTest`) **và** implementation engine `junit-jupiter-engine`.
- **JUnit Vintage:** engine để chạy tests theo JUnit 3/4 trên JUnit Platform, dùng khi migrate dự án cũ.

```text
JUnit Jupiter API jar
       |
       +-- compile: import @Test, Assertions...
       |
JUnit Jupiter Engine jar
       |
       +-- runtime: discovers + executes Jupiter tests
       |
JUnit Platform Launcher
       |
       +-- runner asks engines to discover/run tests
```

### 4.1. Vì sao compile thành công nhưng không chạy?

Source có:

```java
import org.junit.jupiter.api.Test;

class ExampleTest {
    @Test
    void works() {
        org.junit.jupiter.api.Assertions.assertTrue(true);
    }
}
```

Nếu build chỉ có `junit-jupiter-api` mà thiếu `junit-jupiter-engine` tại runtime, compiler vẫn nhận diện annotation và compile. Tuy nhiên Platform không có Jupiter engine để discover/execute test. Lỗi biểu hiện cụ thể tùy launcher/runner và Gradle version: có thể thông báo thiếu engine, “Cannot create Launcher without at least one TestEngine” hoặc no tests discovered. **Không đoán chính xác một thông báo lỗi duy nhất** cho mọi môi trường.

### 4.2. Engine ID

Thông dụng:

| Engine ID | Artifact | Phát hiện |
| --- | --- | --- |
| `junit-jupiter` | `org.junit.jupiter:junit-jupiter-engine` | JUnit Jupiter |
| `junit-vintage` | `org.junit.vintage:junit-vintage-engine` | JUnit 3/4 |
| `junit-platform-suite` | `org.junit.platform:junit-platform-suite-engine` | Declarative JUnit suites |

Tên engine ID không nhất thiết giống hoàn toàn Maven artifact name. Nếu build filter chỉ `includeEngines 'junit-vintage'`, các Jupiter test methods có thể không được chọn ngay cả khi Jupiter engine có trên classpath.

### 4.3. TestEngine là SPI, không phải chỉ một annotation

Một engine được JUnit Platform nạp từ runtime classpath theo ServiceLoader/engine discovery. Khi runtime thiếu artifact engine, hoặc engine bị engine-filter loại, Platform không thể thực thi các tests thuộc programming model đó. Mockito, SpringExtension và `@SpringBootTest` không tự tạo một TestEngine thay thế.

## 5. Java test annotations: import sai là một nguồn lỗi lớn

Có các annotation `@Test` tên giống nhau nhưng thuộc frameworks khác:

| Import | Framework | Runner/Engine phù hợp |
| --- | --- | --- |
| `org.junit.jupiter.api.Test` | JUnit Jupiter | Jupiter engine |
| `org.junit.Test` | JUnit 4 | JUnit 4 runner hoặc Vintage engine trên Platform |
| `org.testng.annotations.Test` | TestNG | TestNG runner/provider/engine tương ứng |
| `org.junit.jupiter.params.ParameterizedTest` | Jupiter | Jupiter engine + params API |

Code gắn annotation từ một framework không tự chạy bởi engine của framework khác.

### 5.1. JUnit 4 import nhầm trong bài Jupiter

```java
// JUnit 4 annotation -- không phải Jupiter:
import org.junit.Test;

public class LegacyPaymentTest {
    @Test
    public void checksLegacyCondition() {
        org.junit.Assert.assertEquals(4, 2 + 2);
    }
}
```

Đây là **snippet minh họa lỗi phối hợp engine**, không thuộc project runnable. Nó compile được nếu có JUnit 4 API; khi Gradle dùng `useJUnitPlatform()` và chỉ Jupiter engine, test JUnit 4 không được thực thi. Muốn giữ legacy tests, thêm **JUnit Vintage engine + JUnit 4** vào runtime/test classpath; hoặc migrate annotation/assertions sang Jupiter.

### 5.2. JUnit 4 và Jupiter có rules visibility khác

JUnit 4 thường yêu cầu test class/method `public` và test method `public void` không parameters (trừ runner đặc biệt). Với JUnit Jupiter, test class và test method **không cần public**, nhưng không được `private`; `@Test` method phải là instance (không static) và trả `void`. Không chữa một Jupiter test “không được nhận” bằng cách ép tất cả method thành public khi nguyên nhân thật là thiếu engine.

### 5.3. @BeforeEach không tạo test

`@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll` là lifecycle methods. Một class chỉ có `@BeforeEach` mà **không có test method/factory/template nào** không tự thành một suite có executable test cases. Tương tự, `@DisplayName` hoặc `@Tag` không làm một method thành test nếu thiếu test annotation.

## 6. Cấu hình Gradle tối thiểu, đúng cho Spring Boot 3.3

Trong project sử dụng Java 17 và Spring Boot 3.3, một cấu hình cơ bản:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Ba điểm cần kiểm tra:

1. `spring-boot-starter-test` đem JUnit Jupiter API/engine và Spring testing utilities theo dependency management của Boot. Không chỉ có `spring-boot-starter` rồi kỳ vọng `@Test` chạy.
2. `useJUnitPlatform()` yêu cầu Gradle Test task dùng JUnit Platform. Nếu quên, Gradle 8.x có thể dùng JUnit 4 style runner/detection và bỏ qua Jupiter tests.
3. `junit-platform-launcher` ở `testRuntimeOnly` đảm bảo launcher version nằm trên **test runtime classpath**, thay vì dựa vào nội bộ Gradle đã cung cấp ngầm. Gradle 9 càng nghiêm ngặt hơn về dependencies, nhưng bài cố định Boot 3.3/Gradle 8.x.

Dự án runnable ở chương 13 sẽ mở rộng build file này bằng tag filter có thể bật qua `-PincludeTestTag=...`.

### 6.1. Không tự ghép các versions JUnit tùy ý

Ví dụ nguy hiểm:

```groovy
testImplementation 'org.junit.jupiter:junit-jupiter-api:5.10.2'
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.8.2'
```

Đây là **anti-pattern minh họa**: API/engine lệch major/minor có thể gây discovery/runtime errors do incompatible platform versions. Với Boot starter test, để BOM quản lý versions khi không có lý do mạnh để override. Dùng `dependencyInsight` để xác minh version cuối được resolve.

### 6.2. Test runtime khác compile classpath

Một dependency `testCompileOnly` có thể giúp Java compile nhưng không đưa jar vào runtime. Một dependency ở `testRuntimeOnly` giúp runner runtime nhưng không cung cấp types khi compile. Vì vậy phải kiểm tra đúng configuration khi chẩn đoán.

Nếu JUnit API có trong testCompileClasspath nhưng Jupiter engine không có trong **testRuntimeClasspath**, có thể là nguồn gốc chính.

## 7. Cách kiểm tra Gradle dependency tree

Trong module chứa test:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-vintage-engine --configuration testRuntimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
```

**Cách đọc:**

- `junit-jupiter-engine` có mặt → Jupiter engine artifact được resolve; vẫn cần kiểm tra filters/launcher/classpath thực của task.
- `junit-platform-launcher` có mặt → launcher dependency được resolve.
- `junit-vintage-engine` vắng mặt → JUnit 4 tests sẽ không được chạy trên Platform theo Vintage, trừ khi một runner khác chuyên biệt được cấu hình.
- `spring-boot-starter-test` có mặt nhưng runtime bị `exclude` engine/transitive modules → phải kiểm tra exclusions/resolution.
- Version conflict → xem dependency graph và BOM; không đoán từ source imports.

**Không hứa rằng thấy jar trong dependency report đã chứng minh engine được load thành công**: một custom Test task có thể dùng classpath khác `sourceSets.test.runtimeClasspath`. Kiểm tra chính task đang chạy.

### 7.1. Một anti-pattern với dependency exclusions

```groovy
testImplementation(
        'org.springframework.boot:spring-boot-starter-test') {
    exclude group: 'org.junit.jupiter',
            module: 'junit-jupiter-engine'
}
```

Đây là snippet **cố ý sai**; không đưa vào runnable build. Khi remove engine, Java có thể vẫn compile, nhưng Jupiter test discovery sẽ không hoạt động như mong muốn.

### 7.2. Khi nào cần JUnit Vintage?

Nếu source test hiện tại chứa JUnit 4 imports, với Boot 3.3 và `useJUnitPlatform`:

```groovy
testImplementation 'junit:junit:4.13.2'
testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
```

Đây là **phần bổ sung tùy chọn**, không cần cho runnable project thuần Jupiter. JUnit Vintage có thể bị bỏ sau khi migrate hết JUnit 4. Kiểm tra BOM resolve phiên bản Vintage tương thích Jupiter/Platform.

### 7.3. TestNG không tự trở thành Jupiter

Nếu lớp dùng `org.testng.annotations.Test`, Jupiter engine không nhận. Bạn cần chọn **TestNG runner** hoặc phù hợp với plugin/engine TestNG ở phiên bản đang dùng. Không chỉ thêm JUnit Jupiter engine rồi mong nó chạy được mọi annotation tên `Test`.

## 8. Gradle source sets và output class files

Gradle Java plugin có source set mặc định:

```text
src/main/java
src/main/resources
src/test/java
src/test/resources
```

`compileTestJava` biên dịch Java ở `src/test/java`, thông thường outputs ở `build/classes/java/test`. `test` task mặc định chạy những test classes từ `test` source set, trên runtime classpath của source set.

Nếu file nằm ở:

```text
src/integrationTest/java/example/InvoiceIT.java
```

mà chưa cấu hình `integrationTest` source set/task, `./gradlew test` mặc định **không compile/execute** file đó.

### 8.1. Cách chẩn đoán trong 60 giây

```bash
./gradlew compileTestJava --info
./gradlew test --info
./gradlew tasks --all
```

Sau compile, kiểm tra thực tế class file. Ví dụ Linux/macOS:

```bash
find build/classes/java/test -type f -name '*Test*.class'
```

Windows PowerShell:

```powershell
Get-ChildItem build\classes\java\test -Recurse -Filter '*Test*.class'
```

**Lưu ý:** đây là lệnh tìm *tên class file* để chẩn đoán, không phải định nghĩa duy nhất về JUnit Platform discovery. Một Jupiter test class tên `BillingChecks` vẫn có thể được engine nhận nếu class được đưa vào selection/classpath hợp lệ.

### 8.2. Package và thư mục

Một file:

```java
package example.discovery;
```

nên đặt ở `src/test/java/example/discovery/InvoiceCalculatorTest.java` để dễ quản lý, mặc dù `javac` kiểm soát package dựa vào declaration. Nếu đặt package/class sai, có thể compile errors, test filter FQN không khớp hoặc IDE không hiểu source root.

### 8.3. Multi-module build

Trong Gradle multi-project:

```bash
./gradlew :orders:test
./gradlew :billing:test
./gradlew test
```

Lệnh thứ ba có thể chạy test tasks ở nhiều subprojects tùy task selector/configuration; đừng chỉ đọc output của `:orders:test` rồi kết luận tests trong `billing` không được phát hiện. Luôn ghi rõ **Gradle path của task** và module chứa file.

### 8.4. Custom Test task cần khai báo inputs

Nếu bạn tự định nghĩa `integrationTest` task, phải cung cấp `testClassesDirs` và `classpath` của integration source set và `useJUnitPlatform()`. Ví dụ skeleton (cần source set đã được tạo trong build script):

```groovy
tasks.register('integrationTest', Test) {
    description = 'Runs integration test source set'
    testClassesDirs =
            sourceSets.integrationTest.output.classesDirs
    classpath =
            sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
```

Snippet này **không thể copy nguyên vào minimal runnable build** nếu chưa tạo `sourceSets.integrationTest`. Nếu `testClassesDirs` trống, task không có compiled tests để discover dù runtime engine đúng.

## 9. Tên lớp: Gradle và Maven không hoàn toàn giống nhau

### 9.1. Gradle chạy JUnit Platform

Với `useJUnitPlatform()`, Jupiter engine discover tests dựa trên test class structure, annotations, selectors, classpath và Gradle include/exclude patterns. **Không áp bộ mẫu tên mặc định của Maven Surefire như một quy tắc bắt buộc cho mọi Jupiter test chạy trên Gradle.**

Tuy vậy dùng conventions `*Test`/`*Tests` cho test class là lựa chọn tốt để IDE, build tools, CI patterns và teammate dễ tìm. Một custom Gradle include/exclude pattern vẫn có thể lọc lớp đúng Jupiter annotation nếu tên không khớp.

### 9.2. Maven Surefire mặc định lọc theo tên

Maven Surefire (nếu không có includes tùy chỉnh) thường chọn các class theo:

- `**/Test*.java`
- `**/*Test.java`
- `**/*Tests.java`
- `**/*TestCase.java`

Ví dụ `InvoiceTest.java` và `TestInvoice.java` được chọn; `InvoiceSpec.java` có thể bị bỏ qua nếu không cấu hình include. Đừng áp nhầm tên theo plugin Failsafe `*IT` rồi chạy `mvn test` và nghĩ Surefire phải nhận nó.

Maven Surefire cũng có hành vi exclude nested classes theo default patterns của plugin, cần hiểu khi dùng JUnit Jupiter `@Nested`. Xem phiên bản và rules thật của plugin.

### 9.3. Đừng “sửa” tên file mà không tìm engine/filter

Một class `InvoiceCalculatorTest.java` đặt đúng tên vẫn có thể không chạy vì quên `useJUnitPlatform()`, JUnit 4 import, classpath thiếu engine hoặc `@Tag` bị filter. Tên file chỉ là **một tầng selection**, không thay thế việc kiểm tra engine.

## 10. Bộ lọc: nơi tests dễ biến mất nhất

Có nhiều tầng filter khác nhau:

| Tầng | Ví dụ | Triệu chứng |
| --- | --- | --- |
| Gradle class include/exclude | `include '**/*FastTest.class'` | Các class khác không được đưa vào discovery |
| Gradle test filter | `--tests example.discovery.InvoiceCalculatorTest` | Chỉ chọn class/method match |
| JUnit tag filter | `includeTags 'fast'` | Test không có tag hoặc tag khác bị loại |
| JUnit engine filter | `includeEngines 'junit-vintage'` | Jupiter tests không chạy |
| JUnit conditions | `@Disabled`, `@EnabledOnOs` | Test được discover nhưng skipped |
| Maven Surefire file includes | `**/*Test.java` | `InvoiceSpec.java` bị bỏ qua |
| Maven Surefire CLI | `-Dtest=InvoiceTest` | Chỉ chạy selected pattern |
| Custom suite select/exclude | `@SelectPackages`, `@ExcludeTags` | Suite cố ý chỉ chạy một tập |
| Build task skip | `-x test`, `-DskipTests` | Không execute task, không phải engine missing |

### 10.1. Gradle --tests

```bash
./gradlew test --tests example.discovery.InvoiceCalculatorTest
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
./gradlew test --tests '*TaggedChecksTest*'
```

**Quan trọng:** Class/method selector phải khớp test actually discovered. Nếu tên sai, Gradle thường báo kiểu “No tests found for given includes” khi filter yêu cầu một test không tồn tại. Điều đó không chứng minh toàn suite không có tests; chỉ chứng minh **selection hiện tại không khớp**.

### 10.2. Tag filters

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'fast'
        excludeTags 'slow'
    }
}
```

Đoạn này là **cấu hình cố định minh họa**, không phải build chính của lab. Một method chỉ có `@Tag("slow")` hoặc không có `fast` sẽ không chạy. Khi có include tag và exclude tag mâu thuẫn, exclusion thắng đối với các tests thuộc tập exclude.

### 10.3. Engine filters

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-vintage'
    }
}
```

Đoạn này chủ ý chỉ chọn Vintage: nếu project chỉ có Jupiter tests, selector sẽ lọc hết. Đừng dùng engine filter khi không có yêu cầu phân tách frameworks; mặc định JUnit Platform dùng các engines có mặt trên runtime classpath.

### 10.4. Maven flags và biến môi trường

`mvn -Dtest=SomeTest test` khác `mvn test`. Tương tự một CI job có `-Dgroups`, `-DexcludedGroups`, `-DskipTests`, custom profiles hoặc Surefire includes. Một “green build” có thể do task bị skip theo CI flags. Luôn xem **effective task/plugin configuration** và command thật đã chạy.

## 11. Disabled, aborted, failed, undiscovered: bốn trạng thái khác nhau

### 11.1. Test không discover

Không tạo node test được engine chọn: thiếu engine, sai source set, private/static signature không hợp lệ, class bị filter, engine không match annotation. Với lỗi signature, engine có thể discover class rồi báo **discovery/validation failure**, không phải âm thầm bỏ test. Đọc logs thay vì áp một nhãn chung.

### 11.2. Discovered nhưng skipped

`@Disabled` và một số conditional annotations tạo skipped result; vẫn có thể xuất hiện trong JUnit XML/IDE test tree. Không dùng “skipped=0” để khẳng định mọi source test được compile/discover; nó chỉ áp cho tập test được runner ghi nhận.

### 11.3. Executed rồi aborted

JUnit assumptions như `Assumptions.assumeTrue(false)` dẫn đến **aborted**; một số runners hiển thị “skipped” hoặc trạng thái tương đương trong report. Aborted nghĩa là test đã bắt đầu, gặp condition runtime, không giống method không được engine discover.

### 11.4. Executed rồi failed

Assertion `assertEquals` sai, lỗi startup Spring ApplicationContext hoặc `NoClassDefFoundError` trong test execution là **failure/error**, không phải zero tests. Điều tra stack trace và số executed tests, đừng đổi TestEngine khi discovery đã thành công.

## 12. Quy tắc class/method của JUnit Jupiter

Class Jupiter thông thường có thể package-private:

```java
package example.discovery;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ArithmeticTest {
    @Test
    void additionWorks() {
        assertEquals(4, 2 + 2);
    }
}
```

**Không bắt buộc public**. Một số lỗi cần phát hiện:

```java
// WRONG: Jupiter @Test method should not be private.
private @Test void inaccessible() {}

// WRONG: @Test method is not static.
@Test static void notAnInstanceTest() {}

// WRONG: @Test method does not return a value.
@Test int returnsValue() { return 42; }
```

Đây là **anti-pattern snippets**, không thuộc runnable project. Java source syntax của `private @Test` cho method modifier/annotation vẫn có thể được compiler chấp nhận nhưng JUnit Jupiter validation sẽ bác; cần đặt annotations/method declarations đúng convention.

### 12.1. Constructor và visibility

Jupiter test classes không được abstract, không private, và constructor phải tương thích với Jupiter parameter resolution. Nhiều constructors tùy ý, private constructor không phù hợp hoặc constructor parameter không có ParameterResolver có thể làm engine/test instantiation fail.

### 12.2. @Nested phải là non-static inner class

```java
class OuterTest {

    @Nested
    class InnerCases {

        @Test
        void childTest() {}
    }
}
```

Đây là snippet đúng (thiếu imports trong đoạn minh họa). Một static nested class không được gắn `@Nested` theo contract JUnit Jupiter cho nested tests. Nếu chỉ tạo nested Java class mà không có `@Nested`, không mặc định rằng mọi runner sẽ treat nó như nested Jupiter container.

### 12.3. @ParameterizedTest và invocations

Một `@ParameterizedTest` method có thể tạo ba, mười hoặc một trăm invocations. Trong report, runner có thể hiển thị mỗi invocation như một child test node. Vì vậy “số phương thức @Test trong source” **không bằng** “số test cases executed”. Nên ghi rõ discovered/executed invocations khi cần coverage budget.

### 12.4. @TestFactory dynamic tests

`@TestFactory` được engine discover làm **factory/container**; dynamic test nodes được tạo khi factory chạy. Nếu factory trả một empty stream, không có dynamic child tests được thực thi dù factory method đã chạy. Nếu factory throw, đó là execution error. Đừng coi dynamic tests không có trong static IDE tree ban đầu là “engine không nhận factory”.

## 13. Dự án runnable Java 17 + Spring Boot 3.3 + JUnit Jupiter

### 13.1. Cấu trúc thư mục

```text
test-discovery-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/discovery/
    │   ├── DiscoveryApplication.java
    │   └── InvoiceCalculator.java
    └── test/java/example/discovery/
        ├── InvoiceCalculatorTest.java
        ├── TaggedChecksTest.java
        └── WiringSmokeTest.java
```

Không có module khác, database hay Docker. Mục tiêu là **tách lỗi discovery/filter khỏi lỗi external environment**. Nếu chưa có Gradle wrapper, tạo wrapper từ Gradle tương thích (ví dụ Gradle 8.7); `./gradlew` không tự sinh khi chỉ copy build.gradle.

### 13.2. settings.gradle

```groovy
rootProject.name = 'test-discovery-lab'
```

### 13.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion =
                JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform {
        if (project.hasProperty('includeTestTag')) {
            includeTags(
                    project.property('includeTestTag').toString())
        }
        if (project.hasProperty('excludeTestTag')) {
            excludeTags(
                    project.property('excludeTestTag').toString())
        }
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Ý nghĩa:**

- Mặc định không truyền `-PincludeTestTag`/`-PexcludeTestTag`: mọi tagged/untagged tests có cơ hội được chọn.
- `-PincludeTestTag=fast`: chỉ tests có tag `fast` được chọn; các tests không tag **bị loại khỏi selection**, không phải bị JUnit `@Disabled`.
- `-PexcludeTestTag=slow`: loại tests có tag `slow`.
- `--tests` là một **filter khác**, có thể kết hợp với tag filter theo kiểu giao nhau: chỉ những tests thỏa **cả hai** mới chạy.
- `testLogging` hiển thị event types; không bắt buộc khi chạy test, nhưng giúp chẩn đoán nhanh.
- `testRuntimeOnly junit-platform-launcher` phù hợp với JUnit Platform runtime; Boot BOM quản lý versions.

## 14. DiscoveryApplication.java và InvoiceCalculator.java

**src/main/java/example/discovery/DiscoveryApplication.java**

```java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DiscoveryApplication.class,
                args);
    }
}
```

**src/main/java/example/discovery/InvoiceCalculator.java**

```java
package example.discovery;

import org.springframework.stereotype.Service;

@Service
public class InvoiceCalculator {

    public int total(int subtotal, int tax) {
        return Math.addExact(subtotal, tax);
    }

    public boolean isPositive(int amount) {
        return amount > 0;
    }
}
```

`InvoiceCalculator` được đánh dấu `@Service` để Spring Boot wiring test xác nhận bean thực sự được tạo. Trong unit tests, chúng ta dùng `new InvoiceCalculator()` để không cần startup Spring context. `Math.addExact` ném `ArithmeticException` khi overflow, tạo một negative test case có kết quả deterministic.

## 15. InvoiceCalculatorTest.java: plain test, parameterized, nested, dynamic

**src/test/java/example/discovery/InvoiceCalculatorTest.java**

```java
package example.discovery;

import java.util.stream.Stream;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.DynamicTest.dynamicTest;

class InvoiceCalculatorTest {

    private final InvoiceCalculator calculator =
            new InvoiceCalculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(17, calculator.total(12, 5));
    }

    @ParameterizedTest(
            name = "addition {index}: {0} + {1} = {2}")
    @CsvSource({
            "1, 2, 3",
            "4, 5, 9",
            "-1, 1, 0"
    })
    void parameterizedAddition(
            int a,
            int b,
            int expected) {
        assertEquals(expected, calculator.total(a, b));
    }

    @Nested
    class BoundaryCases {

        @Test
        void zeroIsNotPositive() {
            assertFalse(calculator.isPositive(0));
        }

        @Test
        void negativeIsNotPositive() {
            assertFalse(calculator.isPositive(-1));
        }
    }

    @TestFactory
    Stream<DynamicTest> createsDynamicTests() {
        return Stream.of(
                dynamicTest(
                        "zero plus zero",
                        () -> assertEquals(
                                0, calculator.total(0, 0))),
                dynamicTest(
                        "overflow is rejected",
                        () -> assertThrows(
                                ArithmeticException.class,
                                () -> calculator.total(
                                        Integer.MAX_VALUE, 1)))
        );
    }
}
```

### 15.1. Chính xác bài này có bao nhiêu phương thức và case?

- `addsTwoNumbers`: 1 invocation.
- `parameterizedAddition`: 3 invocations từ `@CsvSource`.
- `BoundaryCases.zeroIsNotPositive`: 1 invocation.
- `BoundaryCases.negativeIsNotPositive`: 1 invocation.
- `createsDynamicTests`: factory tạo 2 dynamic test cases.

**Tổng logic: 8 executable test cases** từ class này khi không lọc/disable. Không đếm `@TestFactory` như một test case thứ chín chỉ vì nó là một method; nó sinh các dynamic child tests. Cách runner trình bày containers/factory trong report có thể khác, nhưng các tám assertions/test executions ở đây là mục tiêu.

### 15.2. Vì sao class package-private chạy được?

JUnit Jupiter cho phép test class và methods package-private, miễn không private. Đây là một positive example chống thói quen suy luận “không public nên JUnit không phát hiện”.

### 15.3. Vì sao nested class không static?

`@Nested` dùng non-static inner class để kế thừa context của outer instance và lifecycle. Đây là cú pháp JUnit Jupiter hợp lệ cho Java 17.

### 15.4. Vì sao @TestFactory không trả null?

`@TestFactory` phải trả một kiểu dynamic node hợp lệ, ví dụ `Stream<DynamicTest>`, `Collection<DynamicTest>` hoặc `Iterable`. Nếu return type/value không đúng contract, test engine có thể báo validation/processing errors. Source lab dùng `Stream.of(...)` hai dynamic tests có tên rõ.

## 16. TaggedChecksTest.java: lọc và skipped

**src/test/java/example/discovery/TaggedChecksTest.java**

```java
package example.discovery;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TaggedChecksTest {

    @Test
    @Tag("fast")
    void taggedFast() {
        assertEquals(4, 2 + 2);
    }

    @Test
    @Tag("slow")
    void taggedSlow() {
        assertEquals(8, 4 + 4);
    }

    @Test
    @Disabled("Demonstrates discovered-but-skipped")
    void knownDisabled() {
        throw new AssertionError(
                "This body must never execute");
    }
}
```

**Ba test methods** được JUnit Jupiter nhận theo annotation. Nếu chạy mặc định, `taggedFast` và `taggedSlow` có thể execute/pass; `knownDisabled` được **skipped** chứ không thực thi. Khi lọc `includeTestTag=fast`, chỉ `taggedFast` được chọn; hai tests còn lại **không phải** “discovered rồi skipped vì @Disabled” trong kết quả filtered selection nếu đã bị tag filter loại.

### 16.1. Tag inherit từ class

Nếu đặt `@Tag("fast")` ở class, các methods bên trong có tag fast theo Jupiter tag semantics. Trong lab, tags đặt ở **method-level** có chủ đích để kiểm chứng mỗi đường filter.

### 16.2. Không trộn JUnit 4 @Ignore với Jupiter @Disabled

JUnit 4 dùng `org.junit.Ignore`; Jupiter dùng `org.junit.jupiter.api.Disabled`. Import sai test-framework annotation có thể khiến condition không được áp dụng như mong đợi. Đọc đúng engine/imports.

## 17. WiringSmokeTest.java: xác minh Spring context

**src/test/java/example/discovery/WiringSmokeTest.java**

```java
package example.discovery;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class WiringSmokeTest {

    @Autowired
    InvoiceCalculator calculator;

    @Test
    void springBootInjectsCalculator() {
        assertNotNull(calculator);
        assertEquals(
                22,
                calculator.total(20, 2));
    }
}
```

**Một test** chạy với SpringExtension tích hợp qua `@SpringBootTest`. Nếu Jupiter engine không có, SpringExtension không có cơ hội khởi tạo Spring context vì test class chưa được engine thực thi.

Điều này giúp phân biệt lỗi:

- **Discovery missing:** không có test method `springBootInjectsCalculator` được selected/executed.
- **Context bootstrap failure:** test method được chọn nhưng Spring context khởi tạo thất bại, ví dụ bean không tồn tại. Đó là **test execution/error**, không phải “JUnit không phát hiện test”.

### 17.1. Bao nhiêu test cases trong toàn lab?

| Class | Executable test cases khi không lọc | Disabled |
| --- | ---: | ---: |
| `InvoiceCalculatorTest` | 8 | 0 |
| `TaggedChecksTest` | 2 | 1 |
| `WiringSmokeTest` | 1 | 0 |
| **Tổng mục tiêu** | **11** | **1** |

JUnit/Gradle có thể hiển thị các containers/factory nodes khác nhau, nhưng **11 executable cases + 1 disabled case** là số mục tiêu cho một lần chạy unfiltered trên source mẫu. Không lấy thông số này làm **executed report** trước khi chạy lệnh thật.

## 18. Chạy bài thực hành và đọc reports

Yêu cầu:

- JDK 17.
- Gradle 8.7 hoặc wrapper tương thích Spring Boot 3.3.
- Các files ở đúng package paths.
- Maven Central/cache có các artifacts.

Linux/macOS:

```bash
./gradlew clean test
./gradlew test --tests example.discovery.InvoiceCalculatorTest
./gradlew test --tests example.discovery.WiringSmokeTest
./gradlew test --tests 'example.discovery.TaggedChecksTest.taggedFast'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests example.discovery.InvoiceCalculatorTest
.\gradlew.bat test --tests example.discovery.WiringSmokeTest
```

Chạy riêng một tag:

```bash
./gradlew test -PincludeTestTag=fast
```

Chạy mọi tests trừ slow:

```bash
./gradlew test -PexcludeTestTag=slow
```

Chạy một method rõ selector:

```bash
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
```

Nếu chưa chắc class/method được discover, **đầu tiên chạy unfiltered**, sau đó mới thêm `--tests`/tag. Đừng tự áp cả engine/tag/name filters một lúc rồi phải đoán tầng nào đã loại test.

### 18.1. Đọc XML và HTML reports

Gradle test plugin thường tạo:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

Xem số `tests`, `failures`, `errors`, `skipped` trong XML của **lần chạy tương ứng**. Khi chạy filtered task hoặc task FROM-CACHE, cần biết report đang thuộc invocation nào. Từng JUnit dynamic/parameterized case có thể là một test node được report riêng.

### 18.2. UP-TO-DATE không phải “không có test”

Nếu task vừa chạy trước đó và inputs/outputs chưa đổi, Gradle có thể hiển thị `:test UP-TO-DATE`. Khi **cần fresh execution để chẩn đoán**, dùng:

```bash
./gradlew test --rerun-tasks --info
```

Có thể dùng `clean test` trong **project sandbox**; ở repository lớn, clean tất cả modules làm chậm hơn và xóa build outputs không cần thiết. Không chạy `--rerun-tasks` vô hạn trong CI chỉ để che caching hay flaky tests.

### 18.3. Không dùng --dry-run để chứng minh tests execute

`./gradlew test --dry-run` chỉ lập task execution plan, **không thực thi test methods**. Nó hữu ích kiểm tra đúng task nhưng không chứng minh Jupiter engine phát hiện test nào.

## 19. Negative experiment 1: quên useJUnitPlatform

Trong một branch thử nghiệm riêng, bỏ:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Trong Gradle 8.x, `Test` task có thể dùng JUnit 4 runner theo legacy defaults nên Jupiter test classes không được discover/execute. Kết quả lỗi/zero count tùy Gradle, dependencies và build config. **Đừng kết luận test source sai** khi chỉ cần bật đúng framework runner.

**Sửa:** khôi phục `useJUnitPlatform()` trên **đúng test task**. Nếu có task `integrationTest` độc lập, thêm cho chính task đó, không chỉ `test`.

### 19.1. Vì sao một plugin tự bật JUnit Platform có thể thay đổi biểu hiện?

Một số Gradle testing suites/plugins có auto-configuration; nếu test task dùng conventions khác, `useJUnitPlatform` có thể đã được bật. Do đó không áp “mọi Gradle version đều thiếu Platform nếu không có dòng này” như một định luật. Chẩn đoán trên **effective test task configuration** của project đang chạy.

## 20. Negative experiment 2: runtime thiếu engine

Trong một branch cố ý sai, chỉ giữ JUnit Jupiter API, thiếu runtime engine:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter-api'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Không chạy đồng thời với starter-test đang kéo engine, nếu không engine vẫn có trên runtime. Source `@Test` compile được; runner có Platform Launcher nhưng không có `junit-jupiter-engine`. Tùy Gradle/Platform version, sẽ có lỗi khi launch hoặc no tests discovered.

**Sửa:** dùng `spring-boot-starter-test` đầy đủ, hoặc thêm một dependency runtime engine tương thích:

```groovy
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
```

Đây là **đoạn sửa minh họa**; runnable build dùng starter-test. Khi thêm engine trực tiếp, để Boot BOM quản lý version trừ khi có compatibility review.

### 20.1. Engine có trong dependency graph nhưng không được dùng

Nếu engine tồn tại trên project-level runtime graph mà custom task `classpath` bị ghi đè, JUnit Platform trong task vẫn không nạp được engine. Kiểm tra task `classpath` và `testClassesDirs`, không chỉ `dependencies --configuration testRuntimeClasspath`.

## 21. Negative experiment 3: import nhầm JUnit 4

Trong source JUnit Jupiter, thay:

```java
import org.junit.jupiter.api.Test;
```

bằng:

```java
import org.junit.Test;
```

Chỉ khi có JUnit 4 artifact thì Java mới compile. Trên `useJUnitPlatform` với chỉ Jupiter engine, `org.junit.Test` không được Jupiter engine xử lý; thêm Vintage để giữ legacy tests hoặc migrate đúng annotation.

**Không đổi annotation chỉ để compile** nếu chưa xác định runner. Trong Spring Boot 3.3, JUnit Jupiter + SpringExtension là đường mặc định phù hợp với test code mới.

### 21.1. JUnit 4 @RunWith và JUnit Jupiter @ExtendWith

`@RunWith(SpringRunner.class)` thuộc JUnit 4; Jupiter dùng `@ExtendWith(SpringExtension.class)`, và `@SpringBootTest` đã tích hợp SpringExtension. Một lớp có `@RunWith` nhưng không có Vintage/runner JUnit 4 có thể không chạy; đừng đổ lỗi cho `@Autowired`.

## 22. Negative experiment 4: tag/engine filter sai

Thử:

```bash
./gradlew test -PincludeTestTag=fast
./gradlew test -PincludeTestTag=slow
./gradlew test -PexcludeTestTag=slow
```

Dựa vào nguồn lab:

- Include fast: chỉ `TaggedChecksTest.taggedFast` được selected.
- Include slow: chỉ `taggedSlow` được selected.
- Exclude slow: các tests khác có thể được selected, gồm Jupiter cases không tag; `knownDisabled` vẫn skipped nếu được selected.
- Include fast đồng thời `--tests example.discovery.WiringSmokeTest`: bộ lọc giao nhau không có method thỏa, nên có thể nhận no-matching-tests outcome tùy Gradle.

**Cách chẩn đoán:** chạy unfiltered; thêm từng filter một; đọc lệnh từ CI, không chỉ build.gradle trong source (CLI còn có thể thêm `-P` và `--tests`).

### 22.1. Tag expression không phải class name

`@Tag("fast")` không có nghĩa class tên `FastTest`; một class tên `FastTest` không tự có tag fast. Filters theo tag và filters theo class name là hai cơ chế độc lập.

### 22.2. Không tắt fail-on-no-matching cho qua

Một số configuration cho phép thay đổi `filter.failOnNoMatchingTests`. Trong test suite bắt buộc, **một filter không match phải được coi là tín hiệu cần sửa**. Tắt validation để build xanh có thể làm CI bỏ cả module tests mà không ai biết.

## 23. Maven Surefire: bộ quy tắc tên và provider

Nếu dùng Maven thay cho Gradle, Surefire thường chạy trong lifecycle `test` (unit tests). Một POM tối thiểu tương đương cho Java 17/Boot 3.3 có thể là:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>test-discovery-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Đây là **Maven alternative**, đặt thành `pom.xml` và dùng cùng Java source files nếu chuyển build system; không đặt nó đồng thời như một yêu cầu bắt buộc với Gradle. Maven plugin 3.2.5 hỗ trợ JUnit Platform qua provider phù hợp. Nếu dự án thực dùng Surefire version khác, xem effective POM và log provider của version đó.

### 23.1. Lệnh Maven chẩn đoán

```bash
mvn test
mvn -Dtest=InvoiceCalculatorTest test
mvn -Dtest=WiringSmokeTest test
mvn -X test
mvn dependency:tree
mvn help:effective-pom
```

Reports thường ở:

```text
target/surefire-reports/
```

Maven Surefire filter `-Dtest=...` chỉ chọn tests theo pattern. Nếu truyền tên class sai, mặc định Surefire có thể fail khi không có specified tests; tham số cụ thể khác nhau theo version. Không kết luận “project không có tests” trước khi chạy `mvn test` không filter và xem source naming.

### 23.2. Maven tên *IT thường dành cho Failsafe

Maven Surefire mặc định thường chọn `*Test`/`*Tests`/`Test*`/`*TestCase`. Nhiều dự án dùng Maven Failsafe với `*IT`/`*ITCase` ở integration-test/verify lifecycle. Nếu file là `CheckoutIT.java` và chỉ chạy `mvn test`, nó có thể không được Surefire nhận. Cần cấu hình includes hoặc Failsafe plugin phù hợp.

**Không trộn Gradle `--tests` với Maven `-Dtest`**: mỗi công cụ có cú pháp riêng.

### 23.3. Maven skip flags

- `-DskipTests` thường bỏ qua chạy tests nhưng vẫn compile tests.
- `-Dmaven.test.skip=true` có thể bỏ cả test compilation và execution (tùy plugin lifecycle).
- CI profile/plugin config có thể exclude modules/classes.

Khi log `Tests are skipped` xuất hiện, lỗi không nằm ở JUnit engine discovery; trước hết kiểm tra flags/plugin execution.

## 24. JUnit 4 và Vintage: chiến lược migrate an toàn

Nếu dự án có hàng trăm JUnit 4 tests, chưa thể chuyển một lượt, có thể:

1. Giữ `junit:junit` test API.
2. Thêm `junit-vintage-engine` runtime.
3. Bật `useJUnitPlatform()`.
4. Test cả legacy và Jupiter trên cùng Platform, trừ khi có engine filter.
5. Dùng dependency/report để xác minh số legacy test cases đã thực chạy.
6. Migrate dần `@RunWith`/`@Rule`, imports và lifecycle sang Jupiter/Extension.
7. Bỏ Vintage khi đã chắc không còn legacy tests.

### 24.1. Không tự coi Vintage và Jupiter tương đương

JUnit 4 rules, categories và runners không tự chuyển thành Jupiter extensions/tags. Khi migrate, cần kiểm tra semantics của assertions, expected exceptions, timeouts, temporary folders và SpringRunner. Một test “được discover” sau migrate vẫn có thể có khác biệt lifecycle.

### 24.2. Engine filters để chạy riêng legacy

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-vintage'
    }
}
```

Snippet này hữu ích khi muốn chạy riêng legacy tests và runtime có Vintage engine, nhưng **không được** giữ nguyên trên task dành cho toàn suite nếu muốn Jupiter tests chạy cùng.

## 25. Spring Boot test và TestContext không sửa lỗi discovery

`@SpringBootTest` yêu cầu runtime có SpringExtension và Spring Boot test support. Nó giúp bootstrap ApplicationContext khi **JUnit Jupiter đã discover và execute test method**. Nhưng nó không có nghĩa:

- Tự đăng ký Jupiter TestEngine khi engine runtime bị loại.
- Tự đưa file ở wrong source set vào Gradle `test` classpath.
- Tự bỏ Gradle `--tests` filter.
- Tự chuyển JUnit 4 `org.junit.Test` sang Jupiter.
- Tự thay Maven Surefire file naming includes.
- Tự buộc method `@Disabled` chạy.

### 25.1. Phân biệt context load error với undiscovered test

Nếu log có:

```text
Failed to load ApplicationContext
```

thì thường Jupiter/SpringExtension đã bước vào quá trình thực thi và thử bootstrap context. Đây là **test failure** (hoặc test context load failure threshold), không phải “test không được nhận”. Đọc stack trace thiếu bean, config, datasource, profile, component scanning trước khi đổi test engine.

### 25.2. Không thêm @SpringBootTest cho unit tests thuần túy

JUnit Jupiter plain test không cần Spring context. Thêm `@SpringBootTest` cho mọi test có thể làm suite chậm và tăng cache fragmentation, không giải quyết thiếu engine. Dùng pure JUnit tests cho business logic; chỉ dùng Boot context khi cần DI/config/HTTP/persistence integration.

## 26. Diagnosing custom test tasks và source sets

Một số projects có `integrationTest`, `functionalTest` hoặc `acceptanceTest` tasks với source sets khác `test`. Phân biệt:

```text
src/test/java              -> task test
src/integrationTest/java   -> task integrationTest (nếu đã tạo)
src/functionalTest/java    -> task functionalTest (nếu đã tạo)
```

Một custom Gradle task phải có:

- Test source directory được compile.
- Source set dependencies và runtime classpath.
- `testClassesDirs` trỏ compiled classes.
- `classpath` gồm application outputs + test runtime dependencies/engine.
- `useJUnitPlatform()` nếu chạy Jupiter.
- Task được wire vào CI/check lifecycle nếu muốn tự động chạy.
- Filters/tag selectors không loại hết tests.

### 26.1. Đừng nhìn nhầm task

Một dự án có `./gradlew test` thành công nhưng chỉ test unit, trong khi integration tests nằm ở `integrationTest` task và CI chưa gọi. Đây là **workflow coverage gap**, không phải JUnit discovery bug. Thêm correct task invocation/`check.dependsOn integrationTest` khi phù hợp, có review runtime cost.

### 26.2. IDE với custom source set

IDE cần đánh dấu `src/integrationTest/java` là test source root hoặc đồng bộ Gradle model. Nếu IDE run từng test nhưng CLI task không có classpath, khả năng là IDE chạy bằng runner riêng hoặc custom source set chưa wire vào Gradle task. Ưu tiên CI-authoritative Gradle command làm nguồn kiểm chứng.

## 27. Đọc một lỗi discovery theo thứ tự ngắn nhất

### Bước 1 — Đảm bảo đúng task

Chạy:

```bash
./gradlew tasks --all
./gradlew :test --info
```

Với multi-module, thay `:test` bằng task path thực, ví dụ `:orders:test`. Nếu task `NO-SOURCE`, kiểm tra `src/test/java` và compiled outputs.

### Bước 2 — Chạy một sentinel Jupiter test

Thêm một file nhỏ, đúng thư mục, với `org.junit.jupiter.api.Test` và `assertTrue(true)`. Không thêm Spring context. Nếu nó cũng không chạy, tập trung vào Gradle Test/JUnit Platform/runtime engine/classpath trước khi phân tích service code.

### Bước 3 — Kiểm tra runtime engine

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
```

Nếu custom task, kiểm tra classpath của task đó. Đảm bảo JUnit Platform/engine versions tương thích Boot BOM.

### Bước 4 — Bỏ filters tạm thời trong sandbox

Chạy `test` không `--tests`, không include/exclude tags/engines/classes. Chỉ khi unfiltered test chạy được mới thêm từng filter và kiểm tra intersections. Không commit việc bỏ filters nếu security/slow tests cần phân tầng; thay bằng config có chủ đích.

### Bước 5 — Kiểm tra annotation signature

`import org.junit.jupiter.api.Test`; non-private, non-static, void instance method; `@Nested` đúng; `@ParameterizedTest` có source; `@TestFactory` có return type hợp lệ.

### Bước 6 — Đọc test report thực

Xem JUnit XML tests/failed/skipped; nếu zero executed thì phải điều tra, không chỉ nhìn BUILD SUCCESSFUL. Nếu có skipped, tìm `@Disabled`/conditional logic. Nếu failed, đọc failure stack trace.

### Bước 7 — Đối chiếu Maven/IDE/CI

Maven Surefire naming/filter khác Gradle. IDE có thể có runner riêng. CI có thể set task skip, tags, TestEngine include/exclude, JDK/Gradle versions khác. Ghi exact command, branch, dependency lock/BOM và environment.

## 28. Test reporting và chính sách chống “zero tests”

Một quality gate cơ bản:

1. Biết tổng số test cases **dự kiến** của module (sau filters đã được phê duyệt).
2. Từ JUnit XML của **lần chạy thực**, đọc discovered/executed/skipped/failed.
3. Nếu task quan trọng có **zero executable tests**, coi là lỗi cấu hình/coverage cần điều tra.
4. Nếu dùng tag filter chạy riêng suite fast, bảo đảm suite slow/integration được chạy ở task/CI job khác.
5. Nếu có @Disabled/@Conditional test cases, ghi số skipped và lý do.
6. Khi upgrade JUnit/Gradle/Surefire, so sánh count theo từng module/task.
7. Khi tăng Gradle parallel forks hoặc CI shards, cộng counts từ **từng shard** có nguồn dữ liệu rõ; không nhân đôi các tests bị rerun.
8. Với flaky retries, phân biệt unique test cases và số execution attempts.

### 28.1. Maven/Gradle không có guard giống nhau trên mọi version

Một số versions của Gradle không mặc định fail nếu task có test sources nhưng không discover cases; Gradle 9 có thay đổi chính sách `failOnNoDiscoveredTests`. Bài cố định **Gradle 8.x** nên không dựa vào một property mới của Gradle 9 để bảo đảm zero-tests failure. Xây dựng CI validation bằng test report/sentinel case và version-appropriate settings.

### 28.2. Không bật ignoreFailures để làm test task xanh

`ignoreFailures=true` có thể cho build tiếp tục dù tests fail; nó **không** là giải pháp discovery. Không dùng nó để che engine/config errors. Với Maven tương tự, đừng cấu hình `testFailureIgnore` toàn bộ chỉ vì CI đỏ.

## 29. Bảng đối chiếu triệu chứng → tầng lỗi

| Triệu chứng | Tầng nhiều khả năng | Bước đầu |
| --- | --- | --- |
| `:test NO-SOURCE` | Source set/input | Đúng src/test/java và task? |
| Không có compiled .class trong build/classes/java/test | Compilation/source root | Chạy compileTestJava |
| Source có @Test nhưng runtime không có Jupiter engine | Dependency/engine | dependencyInsight testRuntimeClasspath |
| “Cannot create Launcher without at least one TestEngine” | Runtime engine | Thêm engine tương thích |
| `NoClassDefFoundError` junit-platform/Jupiter class | Classpath conflict | BOM/version alignment |
| JUnit4 tests không chạy với useJUnitPlatform | Missing Vintage | junit-vintage-engine |
| @Test import từ org.testng | Wrong framework | Use TestNG runner or Jupiter import |
| @Test private/static/non-void | Invalid Jupiter method | Correct signature |
| @Nested inner tests không hiển thị | Nested declaration/discovery | @Nested non-static inner |
| Parameterized method 0 invocations | Source/setup failure | CsvSource/MethodSource validation |
| @TestFactory method không có children | Empty/invalid dynamic nodes | Check returned Stream |
| `@Disabled` test hiển thị skipped | Execution condition | Đúng annotation/reason |
| `includeTags fast` bỏ test không tag | Tag filter | Check tag policy |
| `--tests` “No tests found for given includes” | Class/method filter | Exact FQN, no filters |
| `includeEngines vintage` bỏ Jupiter | Engine filter | Remove/adjust includeEngines |
| Maven `InvoiceSpec.java` không chạy | Surefire name includes | Rename/configure includes |
| Maven `InvoiceIT` không chạy với mvn test | Failsafe/source/task split | Check plugin/lifecycle |
| Gradle :orders:test không chạy billing tests | Wrong module | Run correct task path |
| Custom integrationTest không có input | Task classpath/classes | testClassesDirs/classpath |
| `:test UP-TO-DATE` | Build caching | --rerun-tasks for fresh diagnosis |
| `:test FROM-CACHE` | Remote/local build cache | Inspect restored report |
| `BUILD SUCCESSFUL` nhưng zero tests | Missing guard/selection | Parse test results |
| `Failed to load ApplicationContext` | Execution/Spring wiring | Root cause stack trace |
| IDE xanh, CI zero | Runner/config divergence | Compare exact CLI, JDK, imports |
| Parallel shards khác counts | Filters/modules/shards | Per-shard XML and config |

## 30. Bài tập thực hành

### Bài 1 — Khởi tạo đúng baseline

Copy runnable project, chạy `./gradlew clean test`. Ghi **số thực tế** pass/failed/skipped trong XML. Không lấy con số expected của README thay test report.

### Bài 2 — Kiểm chứng class package-private

Giữ `InvoiceCalculatorTest` package-private. Không sửa thành public; chạy test. Đây là positive proof JUnit Jupiter có thể discover non-public class hợp lệ.

### Bài 3 — Xóa useJUnitPlatform trong sandbox

Trong branch thử nghiệm, bỏ `useJUnitPlatform()`, chạy `test`. Quan sát behavior, sau đó khôi phục và xác nhận test executed count trở lại.

### Bài 4 — Loại junit-jupiter-engine

Tạo build thử nghiệm không còn engine ở runtime. Dùng `dependencyInsight` để xác nhận, rồi chạy sentinel test. Khôi phục starter-test/engine sau bài.

### Bài 5 — JUnit 4 import

Viết một JUnit 4 test `org.junit.Test` trong một file riêng; chạy Platform chỉ với Jupiter và quan sát nó không được thực thi. Sau đó thêm Vintage, đo số tests chạy. Không lẫn legacy và Jupiter imports trong cùng demo source chính.

### Bài 6 — Sai Maven naming

Với Maven alternative, đổi một class thành `InvoiceSpec.java` rồi chạy `mvn test`. Kiểm tra Surefire includes; thay tên hoặc config includes. Giải thích vì sao Gradle Jupiter không nên bị áp quy tắc Maven một cách máy móc.

### Bài 7 — Chọn một method

```bash
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
```

Kiểm tra JUnit XML chỉ có method được chọn. Nếu source method đổi tên, filter cũ không match; sửa CLI selector.

### Bài 8 — Include fast, exclude slow

Chạy `-PincludeTestTag=fast` rồi `-PexcludeTestTag=slow` riêng biệt; so đối tượng được chọn. Thử kết hợp với `--tests` trỏ WiringSmokeTest, giải thích bộ lọc giao nhau.

### Bài 9 — @Disabled

Bỏ `@Disabled` khỏi `knownDisabled` trong sandbox: test body cố ý throw và phải fail. Khôi phục disabled. Điều này phân biệt skipped với test silently missing.

### Bài 10 — @ParameterizedTest

Đổi `@CsvSource` từ 3 rows thành 4 rows có expected hợp lệ, quan sát executable invocations tăng dù chỉ một method definition.

### Bài 11 — @Nested

Bỏ `@Nested` khỏi `BoundaryCases`, chạy unfiltered suite và xem test tree/report. Khôi phục. Không tự cho rằng Java inner class mặc định thành Jupiter nested tests.

### Bài 12 — @TestFactory

Đổi `Stream.of(twoDynamicTests)` thành empty stream, xem factory có child test cases không; khôi phục để tránh zero dynamic coverage.

### Bài 13 — Wrong source set

Chuyển một test sang `src/integrationTest/java` mà chưa cấu hình source set. Chạy `compileTestJava`/`test`, xác nhận class không được đưa vào task test. Khôi phục hoặc tạo integrationTest task đúng.

### Bài 14 — Custom Test task

Tạo integrationTest source set riêng, khai báo `testClassesDirs`/`classpath`/`useJUnitPlatform()`, rồi chạy `./gradlew integrationTest`. Đảm bảo CI thật gọi task nếu muốn coverage.

### Bài 15 — Maven Surefire -Dtest

Chạy `mvn -Dtest=WiringSmokeTest test` trong Maven alternative, quan sát results. Thử tên không tồn tại rồi đọc fail message, không đổi engine mù quáng.

### Bài 16 — Gradle UP-TO-DATE

Chạy `./gradlew test` hai lần trên cùng checkout, quan sát task state. Dùng `--rerun-tasks` để buộc fresh execution khi chẩn đoán.

### Bài 17 — Engine include-only Vintage

Đặt `includeEngines 'junit-vintage'` trong sandbox có chỉ Jupiter tests; quan sát results. Bỏ filter để Jupiter chạy lại.

### Bài 18 — Spring context failure

Cố ý remove `@Service` khỏi InvoiceCalculator, chạy WiringSmokeTest, xem Spring bean injection fail **sau khi test được discover**. Khôi phục.

### Bài 19 — Multi-module

Trong một project multi-module, chạy `:orders:test` và `:billing:test` riêng, đọc counts mỗi module; không nhầm no tests của task này với tests ở module kia.

### Bài 20 — CI fail-on-zero

Thêm kiểm tra số JUnit XML test cases executed (theo policy) sau task. Trong sandbox, dùng tag filter không match để bảo đảm pipeline báo đỏ, không chỉ BUILD SUCCESSFUL.

## 31. Checklist QA trước khi merge

- [ ] File test nằm ở đúng source set/task được CI gọi.
- [ ] `compileTestJava` compile file và sinh .class tương ứng.
- [ ] Test runtime classpath có JUnit Platform Launcher và Jupiter engine phù hợp.
- [ ] Gradle Test task dùng JUnit Platform (hoặc testing suite cấu hình tương đương).
- [ ] Versions JUnit API/engine/platform không bị override lệch BOM.
- [ ] JUnit imports đúng programming model.
- [ ] JUnit4 legacy tests có Vintage engine hoặc runner phù hợp.
- [ ] Test method Jupiter không private/static/non-void.
- [ ] @Nested đúng non-static inner class.
- [ ] @ParameterizedTest có argument source hợp lệ.
- [ ] @TestFactory tạo dynamic nodes khi được gọi.
- [ ] Không nhầm @Disabled/conditions skipped với discovery missing.
- [ ] Gradle --tests selector được review và không lọc nhầm.
- [ ] IncludeTags/excludeTags/includeEngines khớp CI policy.
- [ ] Gradle include/exclude file patterns không bỏ quên test classes.
- [ ] Maven Surefire default patterns được hiểu rõ; custom includes khi cần.
- [ ] Maven Failsafe/integration task được gọi nếu có *IT.
- [ ] Không có -DskipTests, maven.test.skip, -x test ngoài ý muốn.
- [ ] Test task không chỉ UP-TO-DATE/FROM-CACHE khi cần fresh run.
- [ ] Không báo BUILD SUCCESSFUL = all tests passed nếu chưa xem test counts.
- [ ] Có sentinel test đơn giản để phân biệt engine vs Spring setup.
- [ ] Spring context failure được chẩn đoán theo stack trace đúng.
- [ ] Reports XML/HTML được thu thập từ đúng module/task/invocation.
- [ ] Phân biệt discovered, executed, skipped, failed và test containers.
- [ ] Coverage guard phát hiện zero tests theo suite policy.
- [ ] CI shards/forks có reporting không đếm trùng executions/retries.
- [ ] Đã chạy positive và negative diagnostics trong sandbox, không commit anti-patterns.
- [ ] Khi nâng Gradle/JUnit/Surefire, test count/filters được so sánh trước-sau.
- [ ] Kết quả executed được báo từ tool output thật, không suy đoán từ README.

## 32. Quy tắc quyết định

```text
JUnit test không xuất hiện?
       |
       +-- Đúng task/module?
       |      -> :module:test, integrationTest, IDE vs CI.
       |
       +-- Đúng source set?
       |      -> src/test/java; compileTestJava; .class files.
       |
       +-- Có Jupiter engine & launcher runtime?
       |      -> testRuntimeClasspath / dependencyInsight.
       |
       +-- Đúng runner?
       |      -> Gradle useJUnitPlatform().
       |         Maven Surefire supported provider.
       |
       +-- Đúng annotations?
       |      -> org.junit.jupiter.api.Test.
       |         JUnit4 needs Vintage if running on Platform.
       |
       +-- Đúng signature/nesting?
       |      -> non-private instance void @Test,
       |         @Nested non-static inner,
       |         @ParameterizedTest source.
       |
       +-- Bị lọc?
       |      -> --tests, tags, engine filters,
       |         includes/excludes, Maven naming.
       |
       +-- Đã discover nhưng skipped?
       |      -> @Disabled/conditional/assumptions.
       |
       +-- Task không chạy lại?
       |      -> UP-TO-DATE/FROM-CACHE;
       |         --rerun-tasks only when needed.
       |
       +-- Đã execute nhưng fail?
              -> Read JUnit XML/stack trace;
                 Spring ApplicationContext is another layer.
```

**Kết luận:** Test discovery là một chuỗi điều kiện liên tiếp: source đúng → compile đúng → runtime có đúng **TestEngine** → runner dùng JUnit Platform → class/method hợp lệ → filters cho phép → test thực sự được execute. Không thể chẩn đoán bằng một dòng “BUILD SUCCESSFUL”. Hãy dùng một sentinel Jupiter test, `testRuntimeClasspath`, `useJUnitPlatform()`, test task đúng, selector/filter theo từng tầng và XML reports. Quan trọng nhất, **JUnit Jupiter/Gradle và Maven Surefire có các cơ chế chọn test khác nhau**; nắm đúng công cụ mới tìm ra lỗi nhanh và không bỏ sót coverage ở CI.

## 33. Tài liệu tham khảo chính thức

- Gradle — Testing in Java & JVM Projects, JUnit 5, test filtering, test detection, engines: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Test task DSL, filters, classpath, testClassesDirs: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Gradle — Upgrading to 9.0, change to fail-on-no-discovered-tests: https://docs.gradle.org/current/userguide/upgrading_major_version_9.html
- Gradle — Dependency Insight: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- JUnit Jupiter 5.11 User Guide — Test classes, methods, nested and dynamic tests: https://docs.junit.org/5.11.4/user-guide/index.html
- JUnit 5 User Guide — Platform, engines, filtering, tags, legacy migration: https://docs.junit.org/5.11.4/user-guide/index.html
- JUnit Jupiter API — @Test: https://junit.org/junit5/docs/5.11.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Test.html
- JUnit Platform — Launcher API: https://junit.org/junit5/docs/5.11.4/api/org.junit.platform.launcher/org/junit/platform/launcher/Launcher.html
- Maven Surefire Plugin — Default inclusions/exclusions: https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion
- Maven Surefire Plugin — JUnit Platform: https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html
- Maven Surefire Plugin — Test mojo/flags: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Maven Failsafe Plugin — Integration test naming/lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testing features and annotations: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- JUnit Platform engine SPI and user guide: https://junit.org/junit5/docs/5.11.4/user-guide/index.html
