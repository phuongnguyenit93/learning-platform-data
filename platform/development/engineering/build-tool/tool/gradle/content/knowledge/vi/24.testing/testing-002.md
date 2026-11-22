# Cấu hình JUnit Platform và các test engine trong Gradle

## 1. Mục tiêu của bài học

Khi chuyển một dự án Java từ JUnit 4 sang JUnit Jupiter, lỗi thường không nằm ở method `@Test` mà ở **cách Gradle chọn test framework và các engine có mặt trên test runtime classpath**. Một project có thể biên dịch mọi class trong `src/test/java` thành công nhưng task `test` không chạy một test nào, vì thiếu engine, dùng nhầm `useJUnit()` thay `useJUnitPlatform()`, hoặc lọc mất toàn bộ tests.

JUnit Platform không đồng nghĩa JUnit Jupiter. Trong hệ sinh thái JUnit 5:

- **JUnit Platform** là nền tảng khám phá và khởi chạy các test engines.
- **JUnit Jupiter** cung cấp programming model, annotations, assertions, extensions và `junit-jupiter-engine` để chạy các bài test viết theo Jupiter API.
- **JUnit Vintage** là engine tương thích để chạy phần lớn JUnit 3/4 tests trên cùng JUnit Platform trong giai đoạn migration.
- Các engine khác cũng có thể tích hợp với Platform; không phải mọi test chạy trên Platform đều dùng `org.junit.jupiter.api.Test`.

Sau bài này, bạn sẽ biết:

1. Phân biệt Platform, Launcher, engine API, Jupiter API và Vintage engine.
2. Cấu hình `useJUnitPlatform()` trong Gradle `Test` và các dependencies ở đúng scope.
3. Align JUnit artifact versions bằng JUnit BOM; tránh trộn tùy tiện Jupiter 5.x với Platform 1.x không phù hợp.
4. Viết và chạy ví dụ **Java 17 + Gradle Kotlin DSL + JUnit Jupiter**, có tests độc lập và parameterized tests.
5. Thêm JUnit 4 legacy tests rồi chạy chúng qua Vintage **cùng một Gradle `test` task**.
6. Lọc theo engine, tag, class hoặc method; hiểu lúc nào tests bị loại.
7. Chẩn đoán `Cannot create Launcher without at least one TestEngine`, `No tests found`, `No tests discovered` và test runtime classpath thiếu engine.
8. Tổ chức nhiều test suites, CI reports và quy trình migration an toàn.

**Nguyên tắc:** `useJUnitPlatform()` chỉ **bật cơ chế Platform** cho task Test; một hoặc nhiều **TestEngine implementations phải có mặt trên runtime classpath**, và test APIs cần hiện diện khi biên dịch test sources.

## 2. Kiến trúc: Gradle Test task, Platform, engine và test API

```text
Gradle Java plugin
    |
    +-- src/test/java -> compileTestJava
    |       |
    |       +-- testCompileClasspath
    |              junit-jupiter-api
    |              junit-jupiter-params
    |              (junit:junit cho legacy JUnit 4)
    |
    +-- task test  [useJUnitPlatform()]
            |
            +-- testRuntimeClasspath
            |       junit-platform-launcher
            |       junit-platform-engine APIs
            |       junit-jupiter-engine       [TestEngine ID: junit-jupiter]
            |       junit-vintage-engine       [TestEngine ID: junit-vintage, tùy chọn]
            |       test classes + main classes + dependencies
            |
            +-- forked Test JVM
                    |
                    +-- JUnit Platform Launcher
                    |      discover / select / execute
                    |
                    +-- TestEngines qua ServiceLoader
                           |
                           +-- Jupiter -> @Test, @ParameterizedTest, ...
                           |
                           +-- Vintage -> org.junit.Test JUnit 4/3
                           |
                           +-- Engine bên thứ ba nếu được khai báo
```

**Đọc đúng sơ đồ:** Gradle `Test` task chọn framework adapter `useJUnitPlatform()`, rồi JUnit Platform phát hiện các `TestEngine` từ runtime classpath. Gradle không tự biến một JAR có annotation `@Test` thành test engine. Compiler và test process sử dụng **hai classpaths có vai trò khác nhau**.

### 2.1. Các artifact cần phân biệt

| Artifact / API | Dùng ở đâu? | Chức năng |
| --- | --- | --- |
| `org.junit.jupiter:junit-jupiter-api` | `testImplementation` | `@Test`, `@BeforeEach`, `Assertions`, extension API |
| `org.junit.jupiter:junit-jupiter-params` | `testImplementation` | `@ParameterizedTest`, `@CsvSource`, sources của parameterized tests |
| `org.junit.jupiter:junit-jupiter-engine` | `testRuntimeOnly` | Implementation `TestEngine` chạy Jupiter tests |
| `org.junit.jupiter:junit-jupiter` | `testImplementation` | Aggregator kéo Jupiter API/params/engine để cấu hình ngắn |
| `org.junit.platform:junit-platform-launcher` | `testRuntimeOnly` | Launcher API/implementation dùng để discover/execute tests |
| `org.junit.platform:junit-platform-engine` | Thường transitive | `TestEngine` SPI và discovery model; **không phải một engine thực thi đủ dùng** |
| `org.junit.vintage:junit-vintage-engine` | `testRuntimeOnly` | Engine chạy JUnit 3/4 test classes |
| `junit:junit:4.13.2` | `testImplementation` hoặc `testCompileOnly` theo migration | JUnit 4 annotations/assertions/runner APIs |
| `org.junit:junit-bom` | `platform(...)` | Đồng bộ versions của Jupiter, Platform và Vintage artifacts |

**Không viết nhầm:** `org.junit.platform:junit-platform-engine` cung cấp **interface** để viết engine. Có interface mà không có `junit-jupiter-engine`/`junit-vintage-engine` hoặc engine khác thì Platform vẫn không có implementation để thực thi tests.

### 2.2. Engine ID không phải dependency coordinates

- Jupiter engine ID: `junit-jupiter`.
- Vintage engine ID: `junit-vintage`.
- Maven dependency Jupiter engine: `org.junit.jupiter:junit-jupiter-engine`.
- Maven dependency Vintage engine: `org.junit.vintage:junit-vintage-engine`.

Trong `includeEngines("junit-jupiter")` phải dùng **engine ID**, không dùng `"junit-jupiter-engine"` và cũng không dùng `"org.junit.jupiter:junit-jupiter-engine"`.

### 2.3. Không phải cái gì có chữ “JUnit” cũng là cùng một phiên bản

Với **JUnit 5.14.1** làm ví dụ đã publish: Jupiter/Vintage artifacts dùng phiên bản **5.14.1**, còn JUnit Platform artifacts tương ứng được BOM ràng buộc ở phiên bản **1.14.1**. Không buộc tất cả group IDs về literal `5.14.1` — Platform có version line riêng. Dùng `org.junit:junit-bom:5.14.1` để Gradle chọn đúng tương quan versions thay vì đoán thủ công.

Version trong bài là **một baseline đã xác minh tồn tại**, không phải tuyên bố đó là release mới nhất trên mọi thời điểm. Khi nâng version, chọn BOM/plugin/Gradle Wrapper tương thích và kiểm chứng trên CI.

## 3. Cấu hình tối thiểu JUnit Jupiter với Gradle

### 3.1. Kotlin DSL `build.gradle.kts`

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.14.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Cách ngắn này dùng **`junit-jupiter` aggregator**: module đó transitively mang Jupiter API, parameterized support và engine. Gradle docs cùng JUnit docs khuyến nghị thêm launcher rõ trên test runtime classpath để không phụ thuộc phiên bản launcher mà IDE/build tool cung cấp ngầm.

Khi viết Java tests, chỉ `src/test/java` cần các test APIs. Không khai báo JUnit như `implementation`/`api` của application nếu code production không sử dụng nó.

### 3.2. Groovy DSL `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.14.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Chọn một DSL** theo build hiện có; không đặt song song `build.gradle` và `build.gradle.kts` trong cùng một project để cấu hình trùng.

### 3.3. Ý nghĩa của `useJUnitPlatform()`

`tasks.named<Test>("test") { useJUnitPlatform() }` bảo Gradle dùng JUnit Platform adapter thay vì cơ chế `useJUnit()` dành cho JUnit 3/4 hoặc `useTestNG()`. Nó:

- Chỉ ảnh hưởng **task `test` cụ thể** được cấu hình.
- Cho phép khám phá các Jupiter/Vintage/third-party engines có sẵn trên **test runtime classpath**.
- Cho phép lọc theo tags và engine IDs.
- **Không tự thêm dependencies**, không tự download Jupiter/Vintage engine.
- **Không tự tạo test classes**, không thay đổi source set path và không bảo đảm test nào có thể được khám phá.

Nếu có một `integrationTest` task khác, hãy cấu hình Platform riêng cho task đó hoặc dùng `tasks.withType<Test>().configureEach { useJUnitPlatform() }` khi muốn **mọi Test task** của build dùng Platform. Cẩn thận với plugin khác có test framework riêng.

## 4. Các scope Gradle dễ bị nhầm

| Configuration | Nội dung điển hình | Vai trò |
| --- | --- | --- |
| `testImplementation` | JUnit Jupiter API/aggregator, assertion libs, JUnit 4 API | Dùng để compile test source; được đưa vào runtime graph theo Java plugin |
| `testRuntimeOnly` | Jupiter Engine, Vintage Engine, Platform Launcher | Chỉ cần lúc chạy test |
| `testCompileOnly` | Một API chỉ cần compile (ví dụ JUnit 4 test API trong một setup legacy có runtime khác đảm bảo) | Không tự bảo đảm API tồn tại ở runtime |
| `testRuntimeClasspath` | `testImplementation` + `testRuntimeOnly` + test/main outputs... | **Resolvable classpath** thực tế của Gradle Test worker |
| `testCompileClasspath` | Inputs để `compileTestJava` biên dịch | Có API không đồng nghĩa có engine |
| `implementation` | Main program dependencies | Không nên thêm test-only libs vào main app |

**Quan trọng:** `testImplementation` chứa JUnit Jupiter aggregator có thể đưa engine vào runtime transitively, nhưng với setup API riêng lẻ `testImplementation("org.junit.jupiter:junit-jupiter-api")`, bạn phải chủ động khai báo `testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine")`. Đây là nguyên nhân “test compile được nhưng không chạy” rất phổ biến.

Thêm `junit-platform-launcher` mà **không** thêm bất cứ engine implementation nào cũng không đủ. Ngược lại thêm `junit-jupiter-engine` nhưng quên `useJUnitPlatform()` sẽ khiến Gradle không chạy Jupiter theo engine đó như bạn mong đợi.

## 5. Dùng JUnit BOM để không trộn versions

Một cấu hình minh bạch theo từng artifact:

```kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.14.1"))
    testImplementation("org.junit.jupiter:junit-jupiter-api")
    testImplementation("org.junit.jupiter:junit-jupiter-params")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

Lợi ích:

- Gradle BOM cung cấp version constraints cho `org.junit.jupiter`, `org.junit.platform` và `org.junit.vintage`.
- Không cần viết `junit-platform-launcher:1.14.1` thủ công rồi vô tình lệch khi nâng Jupiter.
- Dễ thấy engine là **runtime dependency**, còn `api` và `params` là **compile dependencies**.
- Khi thêm Vintage, có thể khai báo không version nếu BOM có constraint cho nó.
- Giảm lỗi `NoSuchMethodError`/`NoClassDefFoundError` do các modules JUnit lệch major/minor.

JUnit Jupiter aggregator cũng có thể kéo BOM transitively theo metadata của publisher. Trong bài thực hành, dùng **BOM tường minh** để người học nhìn thấy rõ version alignment, nhất là khi quản lý cả Jupiter + Vintage.

**Không nhầm JUnit BOM với Gradle version catalog:** version catalog quản lý aliases/requested versions; BOM tham gia dependency graph để căn chỉnh artifact versions. Cả hai có thể cùng tồn tại.

### 5.1. Nếu phải dùng version catalog

Trong `gradle/libs.versions.toml`, ví dụ:

```toml
[versions]
junit = "5.14.1"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api" }
junit-jupiter-params = { module = "org.junit.jupiter:junit-jupiter-params" }
junit-jupiter-engine = { module = "org.junit.jupiter:junit-jupiter-engine" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher" }
```

Sau đó trong `build.gradle.kts`:

```kotlin
dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter.api)
    testImplementation(libs.junit.jupiter.params)
    testRuntimeOnly(libs.junit.jupiter.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
}
```

Mẫu này là **một phương án thay thế** cho block dependencies trước, không dán cả hai. Chú ý các aliases trong TOML được chuyển thành subgroup accessors; nếu dự án đang dùng aliases xung đột, chọn tên rõ hơn. Catalog không tự áp dụng engine hay `useJUnitPlatform()`; việc đó vẫn nằm ở test task.

## 6. Thực hành độc lập: Java 17, JUnit Jupiter và các engine

Đây là demo **chạy được khi có Gradle Wrapper, JDK 17 và Maven Central**. Không cần code của ứng dụng thật, không cần database hay dịch vụ bên ngoài. Các file phải được đặt đúng đường dẫn.

### 6.1. Cấu trúc dự án

```text
junit-engines-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/example/math/Calculator.java
    └── test/java/example/math/CalculatorTest.java
```

Nếu project mới chưa có Wrapper, tạo bằng một Gradle được cài tạm để chạy `gradle wrapper`, rồi commit đủ bốn file Wrapper. Từ sau đó luôn dùng `./gradlew` trên Unix hoặc `.\gradlew.bat` trên Windows. Maven Central dùng để tải JUnit lần đầu hoặc khi chưa có artifact trong cache.

`settings.gradle.kts`:

```kotlin
rootProject.name = "junit-engines-lab"
```

### 6.2. Toàn bộ `build.gradle.kts` của demo

```kotlin
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // BOM đồng bộ Jupiter (5.14.1) và Platform (1.14.1).
    testImplementation(platform("org.junit:junit-bom:5.14.1"))

    // API dùng khi biên dịch tests.
    testImplementation("org.junit.jupiter:junit-jupiter-api")
    testImplementation("org.junit.jupiter:junit-jupiter-params")

    // Engine thật và launcher dùng lúc chạy test.
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()

    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}
```

**Giải thích:**

- `java` là Gradle core plugin, tạo source sets, configurations `testImplementation`/`testRuntimeOnly` và task `test`.
- `java.toolchain=17` chọn JDK compiler/default test launcher theo Java plugin. Nó không buộc Gradle Daemon cũng phải chạy trên JDK 17.
- `testImplementation(platform(...))` thêm JUnit BOM; version cho các JUnit artifacts có thể bỏ ở dependency declarations.
- `junit-jupiter-api` có `org.junit.jupiter.api.Test`; `junit-jupiter-params` có `ParameterizedTest`/`CsvSource`.
- `junit-jupiter-engine` là **runtime engine** thật. `junit-platform-launcher` đưa Launcher đúng version vào runtime graph.
- `useJUnitPlatform()` bảo task test chạy discovery/execution qua Platform.
- `testLogging` hiển thị PASSED/FAILED/SKIPPED và standard output test; output cụ thể phụ thuộc Gradle console version.

### 6.3. Source production: `Calculator.java`

File `src/main/java/example/math/Calculator.java`:

```java
package example.math;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
```

`Math.addExact` là Java API có từ Java 8; ở đây chỉ dùng làm phép cộng có kiểm tra integer overflow, không phụ thuộc JUnit hay frameworks bên ngoài.

### 6.4. Source Jupiter: `CalculatorTest.java`

File `src/test/java/example/math/CalculatorTest.java`:

```java
package example.math;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    @Tag("fast")
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
        System.out.println("JUPITER_ENGINE_OK");
    }

    @ParameterizedTest
    @Tag("fast")
    @CsvSource({
        "1, 2, 3",
        "4, 5, 9"
    })
    void addsParameterized(int a, int b, int expected) {
        assertEquals(expected, Calculator.add(a, b));
    }

    @Test
    @Tag("slow")
    void stillRunsByDefault() {
        assertEquals(0, Calculator.add(-1, 1));
        System.out.println("SLOW_TEST_OK");
    }
}
```

**Vì sao có cả `@Test` và `@ParameterizedTest`?** Jupiter engine nhận hai test styles. `ParameterizedTest` với hai hàng `CsvSource` tạo **hai lần thực thi** trong reports. `@Tag("fast")`/`@Tag("slow")` dùng để minh họa filtering, **không tự làm Gradle bỏ qua test** khi chưa cấu hình include/exclude tags.

Test class có package-private visibility, các methods không cần `public` — điều Jupiter cho phép. Điều này **khác JUnit 4 truyền thống** vốn thường yêu cầu public test class/method với runner mặc định.

### 6.5. Lệnh chạy và kết quả

Linux/macOS:

```bash
./gradlew --version
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean test
```

Khi build và JUnit resolution thành công, task `test` chạy **bốn test invocations** (1 `addsTwoNumbers` + 2 lần `addsParameterized` + 1 `stillRunsByDefault`), không có test failure.

Vì đã bật `showStandardStreams = true`, phần output của tests gồm hai dòng chương trình in, thường nằm dưới các nhãn `STANDARD_OUT` của Gradle:

```text
JUPITER_ENGINE_OK
SLOW_TEST_OK
```

**Không khẳng định chỉ có đúng hai dòng trong toàn bộ console:** Gradle in tasks, report, trạng thái build; thứ tự hai dòng test có thể tùy test runner scheduling. Nếu test pass, kết quả tổng thể là `BUILD SUCCESSFUL`; JUnit engines được xử lý từ runtime classpath của task.

### 6.6. Kiểm tra báo cáo

```text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-example.math.CalculatorTest.xml
    └── binary/...
```

Tên và cách chia XML có thể khác chút theo Gradle version; `build/reports/tests/test/index.html` và `build/test-results/test` là các **đường mặc định phổ biến** của task Java `test`. Mở HTML report để xem từng method/parameterized invocation, timing, failures và stdout nếu có.

Báo cáo XML hữu ích cho CI/test visualization. **Một report HTML hiện hữu không chứng minh tests mới đã chạy trong lượt build vừa rồi**; xem timestamp và task outcome, dùng `clean test` hoặc `--rerun-tasks test` khi chẩn đoán.

## 7. Phân biệt Jupiter engine và Vintage engine trong migration

Khi một codebase còn JUnit 4 tests, thay `useJUnit()` bằng `useJUnitPlatform()` mà **không thêm Vintage engine** khiến phần lớn JUnit 4 tests không được phát hiện bởi Jupiter engine. Bởi vì:

- `org.junit.Test` (JUnit 4) và `org.junit.jupiter.api.Test` (Jupiter) là **hai annotation khác nhau**.
- Jupiter engine xử lý Jupiter tests, không tự nhận JUnit 4 test methods.
- Vintage là engine riêng nhận JUnit 3/4 test conventions khi các APIs tương ứng có trên classpath.

### 7.1. Thêm Vintage vào demo

Giữ nguyên `build.gradle.kts` ở phần 6, chỉ thêm **hai dependencies** vào block `dependencies`:

```kotlin
// Dành cho JUnit 4 test source.
testImplementation("junit:junit:4.13.2")

// Engine để Platform khám phá/chạy test JUnit 4.
testRuntimeOnly("org.junit.vintage:junit-vintage-engine")
```

BOM `org.junit:junit-bom:5.14.1` đã có trong demo sẽ cung cấp version cho `junit-vintage-engine`. Version `4.13.2` của artifact `junit:junit` **không** nằm trong các JUnit 5 artifact constraints đó nên phải ghi rõ.

**Trong một project sử dụng Gradle mà chỉ cần compile JUnit 4 API**, đôi khi người ta dùng `testCompileOnly("junit:junit:4.13.2")` và dựa vào Vintage engine kéo JUnit 4 ở runtime. Nhưng với người học và migration đơn giản, dùng `testImplementation` rõ ràng hơn để cả compile/runtime có API ổn định.

### 7.2. Thêm class `LegacyCalculatorTest.java`

Tạo file `src/test/java/example/math/LegacyCalculatorTest.java`:

```java
package example.math;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class LegacyCalculatorTest {

    @Test
    public void legacyAddition() {
        assertEquals(7, Calculator.add(3, 4));
        System.out.println("VINTAGE_ENGINE_OK");
    }
}
```

Đây là test **JUnit 4 thực sự**: import `org.junit.Test`, `org.junit.Assert`, class và method `public` theo conventions của JUnit 4 runner. Không dùng `org.junit.jupiter.api.Test` trong file này.

Chạy:

```bash
./gradlew clean test
```

Khi cả Jupiter và Vintage engines có mặt trên `testRuntimeClasspath`, Gradle Platform có thể chạy **5 test invocations**: 4 từ `CalculatorTest` và 1 từ `LegacyCalculatorTest`. Vì bật standard streams, sẽ thấy thêm:

```text
VINTAGE_ENGINE_OK
```

Không phụ thuộc vào thứ tự in so với Jupiter tests. Hai engines chạy **trong cùng Gradle Test task**, nhưng không có nghĩa Gradle tự di chuyển JUnit 4 annotations sang Jupiter.

### 7.3. Cần biết giới hạn Vintage

Vintage phục vụ **migration** và khả năng chạy test cũ, không phải một lời hứa mọi JUnit 4 extension/runner tương thích hoàn hảo với mọi ecosystem versions. Đặc biệt các custom runners, `@RunWith`, Rules, Categories, Spring/Mockito extensions, JUnit 4.12+ API behavior có thể cần kiểm thử riêng.

Nếu dự án muốn ngừng JUnit 4:

1. Đếm số lượng JUnit 4 classes còn lại.
2. Migrates `org.junit.Test` sang `org.junit.jupiter.api.Test`, cập nhật lifecycle annotations và assertions.
3. Thay JUnit 4 Rules/Runner bằng Jupiter extensions khi phù hợp.
4. Loại các Java/JUnit 4 dependencies không còn dùng.
5. Gỡ Vintage engine khỏi testRuntimeOnly.
6. Chạy toàn bộ suite và kiểm tra số tests không giảm bất ngờ.

Đừng gỡ Vintage chỉ vì `BUILD SUCCESSFUL`: nếu test task không còn phát hiện JUnit 4 classes, build có thể báo success nhưng coverage giảm.

## 8. Lọc theo test engine

Khi **hai engines đều tồn tại**, có thể chọn Jupiter-only trong một task:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        includeEngines("junit-jupiter")
    }
}
```

Hoặc Vintage-only:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        includeEngines("junit-vintage")
    }
}
```

Đây là **các phương án thay thế**, không dán cả hai `includeEngines` nếu bạn muốn chỉ một engine. Nếu bỏ `includeEngines` và `excludeEngines`, JUnit Platform mặc định dùng **mọi engines có trên test runtime classpath** phù hợp discovery selectors/filters.

**Lưu ý:** viết `includeEngines("junit-vintage")` không tự download Vintage. Nếu chưa khai báo `junit-vintage-engine`, filter không sinh ra một engine. Nếu đã khai báo engine nhưng không có JUnit 4 tests, task có thể khám phá 0 tests.

### 8.1. Lọc engine và test class là hai việc khác nhau

- `includeEngines("junit-jupiter")`: giới hạn **loại TestEngine** được sử dụng.
- `--tests example.math.CalculatorTest`: Gradle lọc **class/method test** theo test filter.
- `includeTags("fast")`: JUnit Platform/Jupiter lọc các **test descriptors có tag tương ứng**.
- `test.include("**/*Test.class")`: Gradle lọc **class files**, có thể loại classes theo pattern.
- `excludeEngines("junit-vintage")`: loại engine Vintage khỏi discovery/execution, không gỡ dependency khỏi classpath.

Không thay `includeEngines` bằng `--tests junit-jupiter`. Một engine không phải là tên test class.

### 8.2. Khi cần cho chạy cả Jupiter và Vintage trong migration

Trong `test` mặc định:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Không thêm engine filter; cả hai engines được chọn nếu có mặt và phù hợp. Dùng số test từ report làm baseline, kiểm tra JUnit 4 legacy tests vẫn được execute.

## 9. Lọc theo tag: `@Tag` và Gradle `includeTags`/`excludeTags`

JUnit Jupiter có `@Tag`:

```java
@Test
@Tag("fast")
void quicklyChecksSum() {
    assertEquals(3, Calculator.add(1, 2));
}
```

Đây là **đoạn minh họa trong một Jupiter test class** đã import Test, Tag và Assertions; không phải file Java độc lập.

Để chỉ chạy fast tests, thay `useJUnitPlatform()` của demo bằng:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        includeTags("fast")
    }
}
```

Trong demo phần 6, dự kiến chạy `addsTwoNumbers` và hai invocation của `addsParameterized`, **không chạy** `stillRunsByDefault` vì nó mang tag `slow`. Trường hợp sau khi thêm Vintage, test JUnit 4 thông thường không tự có `@Tag("fast")` nên cũng không được chọn bởi filter này.

Để loại slow nhưng chạy các untagged tests:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        excludeTags("slow")
    }
}
```

Khác biệt:

- `includeTags("fast")` chỉ chọn tests có tag `fast` theo cơ chế tag inheritance/filtering.
- `excludeTags("slow")` giữ tests không mang `slow`, kể cả tests không có tag (nếu không bị loại bởi filter khác).
- Không có filter, cả fast và slow đều được chạy.
- Class-level `@Tag` có thể được kế thừa trong Jupiter model; tag không phải Gradle task group.
- JUnit Platform còn hỗ trợ **tag expressions**, ví dụ `"fast & !integration"`, khi dùng đúng API/version.
- Engine khác có thể có cơ chế tag khác; không giả định annotation Jupiter `@Tag` có hiệu lực với mọi engine.

### 9.1. Lọc nhiều tags

Ví dụ một task chỉ cho phép smoke hoặc fast nhưng loại flaky:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        includeTags("fast | smoke")
        excludeTags("flaky")
    }
}
```

`fast | smoke` là một tag expression, **không phải tên của một tag duy nhất**. JUnit Platform diễn giải toán tử `|`/`&`/`!` theo tài liệu tag expressions.

Để chạy “mọi test trừ integration”, đặt `excludeTags("integration")` hoặc thiết kế riêng task integration suite. Không dùng thay đổi tên package/thư mục làm phương án phân nhóm duy nhất khi project có thể sử dụng tags rõ hơn.

### 9.2. Test class/method filter qua command line

Linux/macOS:

```bash
./gradlew test --tests example.math.CalculatorTest
./gradlew test --tests example.math.CalculatorTest.addsTwoNumbers
./gradlew test --tests '*CalculatorTest'
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.math.CalculatorTest
.\gradlew.bat test --tests example.math.CalculatorTest.addsTwoNumbers
.\gradlew.bat test --tests "*CalculatorTest"
```

`--tests` là bộ lọc của **Gradle Test task**, không cần sửa source file. Đối với parameterized/dynamic tests, Gradle/JUnit Platform có thể dùng display names hoặc descriptors nên lọc method cụ thể có thể phức tạp hơn một test method thông thường. Lúc đó lọc theo class hoặc `@Tag` thường ổn định hơn.

**Quan trọng:** filter `--tests` được kết hợp với các filters đã cấu hình trong build. Nếu build đã `includeTags("fast")` mà bạn chọn một method chỉ mang `slow`, kết quả có thể là **không test nào phù hợp**, không phải `--tests` vô hiệu lực.

## 10. Cấu hình JUnit Platform qua file `junit-platform.properties`

Một số hành vi của JUnit Platform/Jupiter không có DSL tương ứng trong `useJUnitPlatform()`. JUnit hỗ trợ file cấu hình:

```text
src/test/resources/junit-platform.properties
```

Ví dụ:

```properties
junit.jupiter.testinstance.lifecycle.default = per_method
junit.jupiter.execution.parallel.enabled = false
junit.jupiter.displayname.generator.default = org.junit.jupiter.api.DisplayNameGenerator$Standard
```

File được Java plugin đưa vào `testRuntimeClasspath` qua test resources; Platform tự tìm nó. Trong Java 17 demo, không cần tạo file này để chạy các tests mặc định; nó minh họa nơi giữ **framework configuration parameters**.

Có thể đặt các tham số tương ứng vào `Test.systemProperty(...)`:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    systemProperty(
        "junit.jupiter.execution.parallel.enabled", "false"
    )
}
```

**Ưu tiên một nơi làm nguồn chuẩn cho từng parameter**. Nếu thiết lập cùng key ở nhiều nơi (Gradle system property, `junit-platform.properties`, Launcher configuration), JUnit có precedence riêng; khi debug phải xem đường override thực tế, không chỉ mở một file.

### 10.1. Test lifecycle

`per_method` mặc định tạo một test class instance mới cho từng test invocation trong Jupiter. `per_class` dùng một instance cho nhiều methods trong một class, giúp dùng non-static `@BeforeAll` nhưng cũng tạo nguy cơ shared mutable state/race khi chạy parallel.

Nếu bật parallel execution:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
```

phải đảm bảo tests thread-safe, không dùng chung database/file/system properties không kiểm soát. **`junit.jupiter.execution.parallel.enabled` không đồng nghĩa `Test.maxParallelForks`**: một cái điều khiển **threads trong JUnit engine**, một cái điều khiển **số JVM worker processes của Gradle**.

### 10.2. Đừng sao chép `junit-platform.properties` nhiều bản

Nếu nhiều modules/libraries trên runtime classpath đều chứa `junit-platform.properties`, JUnit Platform có thể cảnh báo hoặc chọn một tài nguyên theo cơ chế classloader; điều này gây cấu hình khó đoán. Cần giữ một policy rõ trong test resources của từng suite, hoặc dùng test system properties được quản trị trong convention plugin.

## 11. Các test engines khác: Platform không chỉ có Jupiter và Vintage

JUnit Platform định nghĩa `TestEngine` SPI. Một engine implementation bên ngoài có thể discover và execute những framework/test descriptors khác miễn là tương thích với Platform API.

Ví dụ:

- **Spock 2.x** dùng JUnit Platform engine cho Spock specifications.
- Một custom/internal test engine có thể dùng `TestEngine` SPI do Gradle test task khám phá.
- JUnit Platform Suite Engine có thể chạy suite selectors/declarations khi các artifacts và engines cần thiết có mặt.

**Nguyên tắc chung:** engine phải nằm trên `testRuntimeClasspath`, tương thích với Platform/Launcher APIs, có descriptor đăng ký đúng, và framework cần đủ compile/runtime dependencies. Không tự suy rằng “JUnit Platform” chỉ đồng nghĩa với Jupiter.

Với JUnit Platform Suite, có thể khai báo `@Suite` và selectors thông qua `junit-platform-suite` modules; đây là một mô hình tổ chức suite **khác** với `@Tag` filters được viết trực tiếp ở Gradle task. Khi thêm suite engine, cần kiểm tra tránh chạy trùng tests vừa do suite vừa do trực tiếp engine discovery nếu configuration cho phép.

### 11.1. Xung đột ID hoặc API version

Nếu có hai engine implementations trùng `getId()` hoặc một engine được biên dịch với Platform API không tương thích, Launcher có thể fail khi khởi tạo/discover. Giải pháp là loại engine thừa, căn chỉnh BOM/framework dependencies, xem `testRuntimeClasspath` và release notes; không tắt fail-on-no-tests để che lỗi.

### 11.2. Nhận biết engine đã được tải

Khi cần chẩn đoán:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-vintage-engine --configuration testRuntimeClasspath
```

Trong demo ban đầu không có Vintage, report `dependencyInsight` cho Vintage có thể không có kết quả — **đó là điều đúng** cho Jupiter-only setup. Nếu engine được thêm rồi nhưng vẫn không chạy, kiểm tra filters, source classes, plugin và Test task classpath.

**Dependency report phản ánh module graph**, không trực tiếp chứng minh test engine đã khám phá test nào. Cần chạy test và xem report/XML/logs để kết luận.

## 12. Test discovery, execution và report là ba pha khác nhau

```text
src/test/java sources
      |
      v
compileTestJava   [compilation]
      |
      v
Test worker JVM started   [runtime]
      |
      v
Platform Launcher finds engines
      |
      v
Engines discover test descriptors
      |
      +-- 0 tests -> no discovered tests / filtering / NO-SOURCE
      |
      v
Engines execute selected test invocations
      |
      +-- PASSED / FAILED / ABORTED / SKIPPED
      |
      v
Gradle test results XML + HTML, CI reporting
```

Các tình huống khác nhau:

- `compileTestJava FAILED` vì import `org.junit.jupiter.api.Test` không tồn tại: **test compile classpath thiếu API**.
- `test` không khởi chạy được do thiếu Launcher hoặc engine: **test runtime classpath/framework configuration**.
- Gradle báo `NO-SOURCE`: có thể không có source/test classes tương ứng; **không chứng minh engine đã chạy đúng**.
- `test` chạy nhưng 0 discovered: filters, annotations, engine hoặc class layout có vấn đề.
- Test discovered và executed rồi fail assertion: **code/test behavior**, không phải engine absence.
- Task `UP-TO-DATE`: Gradle có thể không chạy test JVM ở invocation này vì inputs/outputs không thay đổi; dùng `--rerun-tasks` nếu cần quan sát thực thi.
- Tests thành công nhưng báo cáo CI không xuất hiện: có thể do đường XML/reporting, cấu hình CI, hoặc task test chưa được gọi.

## 13. `No tests found` và `No tests discovered`: chẩn đoán đúng

Khi gặp thông báo “No tests found for given includes”:

1. Xác nhận Gradle Test task đúng project/source set. `./gradlew projects`, `./gradlew :app:tasks --all`.
2. Kiểm tra source có trong `src/test/java` và `compileTestJava` chạy.
3. Xem import annotation: Jupiter `org.junit.jupiter.api.Test` hay JUnit 4 `org.junit.Test`?
4. Kiểm tra `useJUnitPlatform()` hoặc suite DSL.
5. Xem `testRuntimeClasspath` có `junit-jupiter-engine`/`junit-vintage-engine` tương ứng không.
6. Xem `--tests`, `includeTags`/`excludeTags`, `includeEngines`/`excludeEngines` có vô tình loại test không.
7. Chạy test với filter nhỏ nhất có ý nghĩa và xem HTML/XML reports.
8. Nếu project dùng custom `Test` task, kiểm tra `testClassesDirs`, `classpath` và source set liên quan.

**Phân biệt hai chế độ fail:**

- `Test.filter.failOnNoMatchingTests` điều khiển lỗi khi **test filtering** yêu cầu các tests không tìm thấy.
- `Test.failOnNoDiscoveredTests` (Property<Boolean> trên Gradle hiện hành, mặc định true khi có test sources) kiểm soát trường hợp **test sources có nhưng Platform không discover test nào**.

Ví dụ configuration:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    failOnNoDiscoveredTests.set(true)
    filter {
        isFailOnNoMatchingTests = true
    }
}
```

Đây là một đoạn **cấu hình cho Gradle có hỗ trợ `failOnNoDiscoveredTests`**; kiểm tra Wrapper nếu build cũ hơn. Không bật hai cờ với hy vọng chúng sẽ **tạo ra test** — chúng chỉ đảm bảo lỗi không bị im lặng.

**Không nên** sửa `No tests found` bằng cách đặt cả hai false trong CI. Làm vậy có thể khiến một test suite trống được báo success.

### 13.1. `scanForTestClasses` không chữa lỗi Platform

Theo tài liệu Gradle, khi dùng **JUnit Platform**, chỉ patterns `includes`/`excludes` được dùng cho lớp test; `scanForTestClasses` không có tác dụng như với JUnit 3/4 detection. Đừng liên tục bật/tắt `scanForTestClasses` để tìm Jupiter tests. Thay vào đó xác minh engine, annotations và các selectors/filters thực sự.

### 13.2. Class name không nhất thiết kết thúc bằng `Test`

JUnit Jupiter có thể discover test methods trong class package-private như `CalculatorTest`; mặc định không nên dựa hoàn toàn vào hậu tố `Test` khi phân tích engine. Tuy nhiên một build có **custom Gradle include patterns**, filters hoặc tools có thể chỉ chạy tên lớp theo convention. Hãy đọc source sets/`test` configuration thực tế.

## 14. Chẩn đoán lỗi Runtime classpath và engine

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Cannot create Launcher without at least one TestEngine` | Có launcher nhưng không có engine implementation tương thích | Thêm `junit-jupiter-engine`/`junit-vintage-engine` hoặc aggregator đúng |
| `TestEngine with ID 'junit-jupiter' failed to discover tests` | API/engine/launcher mismatch, classpath, lỗi initialization | Đồng bộ BOM và xem `--stacktrace`/cause gốc |
| `NoClassDefFoundError: ...junit/platform/...` | Thiếu hoặc lệch JUnit Platform module ở runtime | Xem `testRuntimeClasspath`/dependencyInsight, BOM |
| Jupiter `@Test` compile nhưng bị bỏ qua | Quên `useJUnitPlatform()` hoặc thiếu Jupiter engine | Chọn Platform và thêm engine runtime |
| JUnit 4 tests không chạy sau chuyển sang Platform | Chưa có Vintage engine, JUnit 4 API bị loại | Thêm `junit-vintage-engine` và JUnit4 API khi migration |
| `No tests found for given includes` | `--tests` filter pattern sai hoặc bị kết hợp tag/engine filters | Bỏ filters tạm, chạy class-level, kiểm tra tên/package |
| Tests báo `NO-SOURCE` | Không có compiled test classes trong source set | Kiểm tra `src/test/java`, `compileTestJava`, task |
| Test class có Jupiter annotation nhưng Gradle vẫn nhìn JUnit 4 | Task chưa chọn Platform adapter | Kiểm tra `useJUnitPlatform()` trên đúng Test task |
| Có `junit-platform-engine` mà không chạy test | Chỉ có SPI, chưa có implementation | Thêm `junit-jupiter-engine` hoặc engine khác |
| Một module kéo JUnit Platform 1.x khác phiên bản | Version alignment bị lệch vì dependency graph | Bật BOM đúng, dùng `dependencyInsight` và constraints |
| Test có chạy trong IDE nhưng Gradle CLI không chạy | IDE runner/classpath khác Gradle Test task | Chọn Gradle runner, đối chiếu `testRuntimeClasspath` |
| `failOnNoDiscoveredTests` phát hiện 0 tests | Engine/filters/configuration tạo suite trống | Xác minh tests thực có và các filters |
| Vintage chạy nhưng custom runner JUnit4 fail | Runner/Rules hoặc framework integration không tương thích | Giữ JUnit4 runner riêng trong migration, sửa extension |
| JUnit Jupiter @Tag filter không tác dụng như tưởng | Chỉ dùng `@Tag` cho Jupiter test; engine khác khác semantics | Xem engine/tag descriptors thực tế |
| `Test worker exited unexpectedly` | JVM args/heap/agent/native crash hoặc framework crash | `--info`/`--stacktrace`, test logs, worker JVM settings |
| Dùng `includeEngines("junit-vintage")` nhưng chỉ có Jupiter tests | Không có tests dành cho engine được chọn | Bỏ filter/đảm bảo Vintage tests và engine runtime |
| CI chạy 0 tests sau migration vẫn xanh | Fail-on-no-tests bị tắt hoặc custom tasks không chạy | Bật fail flags, kiểm số lượng tests, gate HTML/XML reports |

### 14.1. Quy trình lệnh ngắn khi test mất tích

```bash
./gradlew --version
./gradlew clean compileTestJava
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew test --rerun-tasks --info
./gradlew test --tests example.math.CalculatorTest --stacktrace
```

Trên Windows thay `./gradlew` bằng `.\gradlew.bat`. Một build multi-project cần thêm `:module:test` và `:module:dependencies` đúng đường dẫn. Không dùng root test report để kết luận tất cả subprojects đã chạy nếu chỉ gọi một task con.

Khi lỗi discovery xuất hiện, đọc **root cause** trong stack trace trước khi tăng memory hoặc sửa test naming. Nhiều lỗi do conflict dependencies/platform APIs chứ không phải assertions của test.

## 15. JVM Test Suite plugin so với `tasks.named<Test>("test")`

Gradle hiện đại có **JVM Test Suite** model để khai báo test suites rõ ràng:

```kotlin
plugins {
    java
}

testing {
    suites {
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.14.1")
        }
    }
}
```

Đây là **một phương án cấu hình thay thế** cho demo thủ công, không dán chồng nếu sẽ gây trùng version/framework settings. `java` plugin cung cấp các DSL types liên quan trong build hiện đại. `useJUnitJupiter("5.14.1")` cấu hình Jupiter framework cho suite theo cơ chế Gradle, giảm một phần khai báo dependencies/test framework thủ công.

Phải phân biệt:

- Gradle **`JvmTestSuite`** quản lý **source set/task/dependencies của một suite** (ví dụ unit vs integration).
- JUnit Platform **TestEngine** chạy test descriptors trong task mà Gradle cung cấp.
- JUnit Platform **Suite Engine** chạy test suite annotations/selectors theo JUnit Platform.

Ba từ “suite”/“engine” ở ba lớp khác nhau; không dùng `@Suite` để mong tự tạo Gradle `integrationTest` task.

### 15.1. Tách unit và integration tests

Một hệ thống có thể dùng source `src/test/java` cho unit tests và `src/integrationTest/java` cho integration. Thay vì chỉ dựa vào tags:

- Tạo `integrationTest` JVM test suite thông qua `testing.suites.register<JvmTestSuite>("integrationTest")` theo Gradle docs.
- Chọn `useJUnitJupiter(...)` cho suite đó hoặc cấu hình `Test.useJUnitPlatform()` trên target tasks.
- Khai báo integration dependencies/runtime classpath riêng.
- Cho `check` phụ thuộc integration test task khi đó là policy.
- Không tự giả định mọi custom suite **tự chạy** khi gọi `./gradlew test`.
- Đặt output reports riêng để CI biết suites nào pass/fail.

Một mẫu cấu hình **phải đặt trong project có Java/JVM Test Suite support**:

```kotlin
testing {
    suites {
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.14.1")
            dependencies {
                implementation(project())
            }
            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named("test"))
                    }
                }
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
```

Đây là **mẫu kiến trúc cần tích hợp vào project thật**, không phải toàn bộ runnable build script. Khi cấu hình JVM Test Suite, cần xác minh API của Gradle Wrapper đang dùng, source set `src/integrationTest/java`, task và dependency graph. Custom suites có hành vi dependency inheritance riêng, không mặc định nhận toàn bộ `testImplementation` của unit tests.

### 15.2. Khi nào chỉ cần một `test` task?

Với thư viện nhỏ có tất cả tests dùng Jupiter và không có isolation requirements, cấu hình thủ công ở phần 6 là đủ:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Khi cần integration/migration/compatibility matrices, tạo thêm suites hoặc Test tasks riêng cho mục đích rõ ràng; tránh chỉ đặt `includeTags` nhiều lần trên một task rồi nghĩ chúng là nhiều suites độc lập.

## 16. Test lifecycle, extensions, parameterized và dynamic tests

### 16.1. Jupiter lifecycle annotations

Jupiter sử dụng:

```java
@BeforeEach
void prepare() {
    // Chuẩn bị fixture cho từng invocation.
}

@AfterEach
void cleanup() {
    // Dọn dẹp fixture sau từng invocation.
}
```

Đây là **mẫu method bên trong Jupiter test class**, cần import `org.junit.jupiter.api.BeforeEach`/`AfterEach`. Chúng không thuộc `org.junit.Before`/`After` của JUnit 4. `@BeforeAll`/`@AfterAll` có quy tắc static/non-static theo lifecycle `PER_METHOD` hoặc `PER_CLASS`, không nên thay vì cần dọn database một lần mà không xét concurrency.

### 16.2. Extensions Jupiter không phải engines

Một extension implements Jupiter `Extension` SPI, chẳng hạn `BeforeEachCallback` hoặc `ParameterResolver`, **chạy bên trong Jupiter engine**. Nó không phải JUnit Platform `TestEngine` độc lập. Đăng ký bằng `@ExtendWith` hoặc cơ chế auto-detection được cấu hình.

Ví dụ `@ExtendWith(SomeExtension.class)` chỉ hợp lệ nếu extension class đã tồn tại trên test classpath. Việc gắn extension không thể chữa thiếu `junit-jupiter-engine`.

### 16.3. Parameterized tests

`@ParameterizedTest` + `@CsvSource`, `@MethodSource` hay `@ValueSource` cần `junit-jupiter-params`. Trong demo đã có params ở `testImplementation`.

Nếu compile báo không tìm `org.junit.jupiter.params.ParameterizedTest`, thêm `junit-jupiter-params` vào compile classpath (hoặc dùng Jupiter aggregator). Nếu method xuất hiện thành nhiều invocations, CI report count có thể cao hơn số methods `@Test`. Không nhầm đó là chạy trùng engine.

### 16.4. Dynamic tests và factory

Jupiter `@TestFactory` có thể trả `DynamicTest` hoặc streams. Chúng được discover/execute theo model của Jupiter; display names và reporting có thể khác methods tĩnh. Khi lọc qua Gradle `--tests` ở mức method, cần kiểm tra Gradle/JUnit version vì dynamic descriptor matching không giống test method thông thường.

Đừng dùng một Jupiter test method làm “tạo tasks Gradle mới”: discovery/execution của tests xảy ra **trong Test worker**, sau configuration phase của Gradle.

## 17. Parallel execution, isolation và hiệu năng

Có **hai tầng song song** độc lập:

| Tầng | Điều khiển | Thực thi |
| --- | --- | --- |
| Gradle Test task forks | `maxParallelForks`, `forkEvery` | Nhiều JVM worker processes, mỗi worker có classloader/test runtime |
| JUnit Jupiter parallel execution | `junit.jupiter.execution.parallel.enabled` và mode settings | Nhiều test executions/threads **trong** JUnit Platform engine |

Một cấu hình Gradle Test task:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    maxParallelForks = 2
    maxHeapSize = "768m"
    systemProperty("app.env", "test")
}
```

Một file `src/test/resources/junit-platform.properties` có thể bật Jupiter parallel execution riêng:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
```

Nếu cả hai được bật, có thể tạo **nhiều worker JVM, mỗi JVM chạy nhiều test threads**, làm tăng tải CPU, RAM và khả năng race. Không bật đồng thời chỉ vì thấy tests chạy nhanh hơn trên laptop; nên kiểm tra test isolation, tài nguyên CI, database ports/files và locks.

### 17.1. Test worker JVM không phải Gradle Daemon JVM

Task `Test` chạy test trong JVM forked riêng. `maxHeapSize`/`jvmArgs` trên Test quản lý test worker, không điều chỉnh `org.gradle.jvmargs` của Gradle Daemon. Java toolchain chọn `javaLauncher` cho worker; JUnit engine chỉ là library trong process đó. Vì vậy thay JDK của Gradle Daemon không tự giải quyết engine version mismatch trong `testRuntimeClasspath`.

### 17.2. Không dùng `forkEvery=1` làm thuốc chữa

`forkEvery` có thể giúp cô lập leaks/static global state nhưng tốn startup time; nó không sửa classpath thiếu engine, không sửa Jupiter/Vintage version mismatch, cũng không bảo đảm test framework thread-safe. Ưu tiên sửa test fixtures và state management.

## 18. CI, báo cáo và xác nhận không mất tests

Với demo Jupiter-only, một pipeline cơ bản:

```bash
./gradlew --version
./gradlew --dependency-verification strict clean test
./gradlew test --rerun-tasks --info
```

Dòng `--dependency-verification strict` **chỉ phù hợp khi build đã có verification metadata được thiết lập đầy đủ**; demo mới chưa có `gradle/verification-metadata.xml` thì không cần áp dụng ngay. Với môi trường học tập, lệnh cốt lõi là:

```bash
./gradlew clean test
```

Trong CI của dự án thật:

1. Pin **Gradle Wrapper** và JDK/toolchains; tránh runner có môi trường Java ngầm định khác.
2. Resolve và kiểm tra JUnit dependencies với BOM, không tự mix phiên bản platform/engine.
3. Tạo test report XML/HTML để CI ingest; publish kết quả test dưới dạng artifact.
4. Bật failure khi **tests có source nhưng không được discover** để tránh green build giả.
5. Nếu migration Vintage → Jupiter, so **số test invocations** và coverage trước/sau.
6. Phân tách integration test suite khi có hạ tầng riêng, tránh chạy database/network trong unit suite.
7. Giới hạn parallel forks/threads theo quota CI, tránh tests flaky.
8. Không đặt secret vào test system properties/logs hoặc standard output.
9. Nâng Gradle/JUnit/IDE version qua PR có review; test lại discovery, engine behavior và classpath.
10. Nếu project có `junit-platform.properties`, commit và review nó như một phần behavior của tests.

### 18.1. Không dựa vào một dấu hiệu duy nhất

- `BUILD SUCCESSFUL` không nhất thiết chứng minh mọi tests đã chạy đúng nếu filters/suites bị cấu hình sai.
- `compileTestJava UP-TO-DATE` không có nghĩa `test` đã chạy.
- `test SKIPPED/NO-SOURCE` không phải “all passed”.
- Một class trong `src/test/java` không bảo đảm Jupiter/Vintage engine sẽ discover nó.
- `--tests` chạy một class thành công không chứng minh các classes còn lại được chạy.
- `testRuntimeClasspath` có engine không đồng nghĩa tests đã discover; cần reports.
- IDE hiển thị test pass không tự đảm bảo Gradle CLI/CI chạy cùng launcher/engines.

## 19. Quy trình debug từ đầu đến cuối

**Bước 1 — kiểm tra Gradle/JDK:**

```bash
./gradlew --version
./gradlew javaToolchains
```

Nếu JVM không khởi động được, giải quyết Gradle/Java compatibility trước; chưa đến bước JUnit discovery.

**Bước 2 — xác định đúng project/Task:**

```bash
./gradlew tasks --all
./gradlew test --dry-run
```

Với multi-project, dùng `./gradlew :module:tasks --all` và `./gradlew :module:test`. `--dry-run` chỉ xem task graph, **không thực thi JUnit**.

**Bước 3 — kiểm tra test sources:**

```bash
./gradlew clean compileTestJava
```

Nếu Java compile fail, kiểm tra annotations/imports, `testImplementation` và source set. Compiler success chỉ chứng minh API compile đủ.

**Bước 4 — kiểm tra runtime graph:**

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
```

Tìm đúng engine artifacts, BOM constraints, versions và runtime-only dependencies. Không dùng `implementation` thay cho `testRuntimeOnly` theo thói quen.

**Bước 5 — kiểm tra `useJUnitPlatform()` và filters.** Xem có plugin/convention logic ghi đè `useJUnit()` hoặc thêm `includeTags`/`includeEngines`? Có `--tests` trong CI command không? Một filter quá hẹp dễ loại toàn bộ suite.

**Bước 6 — chạy thật để xem discovery:**

```bash
./gradlew test --rerun-tasks --info --stacktrace
```

Đọc root cause, test worker logs, kết quả HTML/XML. Nếu launcher/engine lỗi, không sửa từng assertion.

**Bước 7 — test từng engine.** Nếu có cả Jupiter/Vintage, có thể tạm chọn `includeEngines("junit-jupiter")` hoặc `includeEngines("junit-vintage")` ở một branch test để khoanh vùng. Sau đó trả lại cấu hình chạy cả hai nếu migration còn cần.

**Bước 8 — xác nhận CI gate.** Chạy clean job, kiểm counts/coverage, fail-on-no-tests, artifacts reports và JDK. Dọn workaround sau khi xác minh nguyên nhân thay vì giữ `lenient`/`ignoreFailures` lâu dài.

## 20. Bảng các lỗi và anti-patterns

| Cấu hình/hành vi | Tại sao sai hoặc nguy hiểm? | Cách đúng |
| --- | --- | --- |
| Chỉ dùng `testImplementation("junit-jupiter-api")` | Có compile API nhưng **không có runtime engine** | Thêm `junit-jupiter-engine`/aggregator |
| Chỉ dùng `junit-platform-launcher` | Launcher không phải engine | Thêm ít nhất một `TestEngine` |
| Có Jupiter engine nhưng dùng `useJUnit()` | Gradle dùng adapter cũ dành JUnit 3/4 | Dùng `useJUnitPlatform()` |
| Nhập `includeEngines("junit-jupiter-engine")` | Sai ID, đó là artifact name | Dùng `"junit-jupiter"` |
| Đặt JUnit dependencies trong `implementation` | Đưa test-only libraries vào main runtime classpath | Dùng `testImplementation`/`testRuntimeOnly` |
| Trộn Jupiter 5.14.x và Platform 1.8.x | Có nguy cơ API linkage/NoSuchMethodError | Dùng đúng BOM/version alignment |
| Di chuyển JUnit 4 tests nhưng gỡ Vintage sớm | Legacy tests không được khám phá | Duy trì Vintage tới khi migration hoàn tất |
| Chỉ thấy `BUILD SUCCESSFUL` nên coi tất cả tests chạy | Filters/suites có thể chạy 0 test | Xem report counts và fail-on-no-tests |
| `includeTags("fast")` nhưng tất cả tests untagged | Filter loại mọi test | Tag tests hoặc dùng `excludeTags("slow")` phù hợp |
| Bật parallel Jupiter và Gradle forks không kiểm soát | Race/global state/CI quá tải | Thiết kế isolation và giới hạn concurrency |
| Thêm `junit-platform.properties` vào nhiều jars | Có thể xung đột cấu hình | Một nguồn config rõ và review |
| Cho Gradle `test` chạy Maven Surefire settings | Hai build systems có config độc lập | Cấu hình Gradle `Test.useJUnitPlatform`/classpath đúng |
| Chạy `--tests` với tên package sai | Không match class/method | Kiểm tên class và source set thực tế |
| Dùng `scanForTestClasses` để chữa Platform | Flag không hoạt động như JUnit 4 detector với Platform | Xem class includes/excludes, engine và annotations |
| Tắt fail-on-no-tests để CI xanh | Che suite trống | Sửa discovery và bật fail flags |
| Test report của lần chạy trước | Artifact cũ không chứng minh invocation hiện tại | `clean test` hoặc `--rerun-tasks test` |
| Đổi `Test.maxHeapSize` khi thiếu engine | Heap không sinh ra engine | Kiểm runtime classpath |
| Quên JUnit 4 API khi thêm Vintage | Legacy source không compile hoặc runtime thiếu API | Thêm `junit:junit:4.13.2` và Vintage |
| Custom suite không chạy khi `./gradlew test` | Suite có task riêng, không tự thuộc task `test` | Thêm task dependency/check lifecycle theo policy |
| IDE test runner dùng launcher khác | Kết quả IDE và CLI khác | Align IDE Gradle runner, BOM và classpath |
| Coi `@ExtendWith` là một engine | Jupiter extension không phải Platform engine | Đảm bảo Jupiter engine/runtime, rồi đăng ký extension |

## 21. Bài tập tự kiểm tra

1. **`useJUnitPlatform()` đã bật, nhưng chỉ có `junit-jupiter-api`: chạy được không?** Không đủ; test compile được nhưng thiếu Jupiter engine runtime. Thêm `junit-jupiter-engine` hoặc dùng Jupiter aggregator.
2. **`junit-platform-engine` có phải là engine Jupiter không?** Không. Đây là Platform SPI/API; Jupiter implementation là `junit-jupiter-engine`.
3. **Muốn giữ JUnit 4 tests khi chuyển sang Platform thì cần gì?** `junit:junit:4.13.2` cho API và `junit-vintage-engine` trên runtime classpath, cùng `useJUnitPlatform()`.
4. **Jupiter TestEngine ID là gì?** `junit-jupiter`, không phải tọa độ Maven của engine.
5. **Muốn chạy fast tests, chọn tag hay engine filter?** Dùng `includeTags("fast")` nếu fast là đặc tính của tests; engine filter giới hạn framework (Jupiter/Vintage).
6. **Dùng `includeTags("fast")` có chạy untagged tests không?** Thông thường không; kiểm tra tag expressions/inheritance/filter khác.
7. **Dùng `excludeTags("slow")` có giữ untagged tests không?** Có, nếu không bị filters khác loại.
8. **Chạy `--tests example.math.CalculatorTest` có giới hạn engine không?** Không trực tiếp; nó lọc class/method, còn engines có trên runtime classpath và Platform filter quyết định.
9. **Vì sao cần BOM khi dùng Jupiter + Vintage + Platform Launcher?** Để đồng bộ các artifact versions thuộc ba nhóm JUnit và giảm binary API mismatch.
10. **Có JUnit Jupiter 5.14.1 thì Platform artifact phải là 5.14.1?** Không. JUnit BOM 5.14.1 align Platform artifacts vào 1.14.1.
11. **`maxParallelForks=2` có nghĩa Jupiter chạy hai threads trong một JVM không?** Không. Đó là Gradle Test worker process forks; Jupiter parallel threads có settings riêng.
12. **Test task outcome `UP-TO-DATE` có chạy JUnit engine ở invocation hiện tại không?** Thường không, task được Gradle skip; dùng `--rerun-tasks` khi cần quan sát.
13. **`failOnNoDiscoveredTests` và `failOnNoMatchingTests` khác nhau?** Một kiểm 0 discovered tests khi có test sources, một kiểm filter không match; cả hai không tạo test.
14. **Dùng `@Suite` của JUnit có tự tạo `integrationTest` Gradle task không?** Không; JUnit Suite Engine khác Gradle JVM Test Suite DSL.
15. **Khi nào có thể gỡ Vintage khỏi build?** Khi đã chuyển hoặc loại bỏ mọi JUnit 3/4 tests cần chạy và CI xác minh counts/coverage không giảm bất ngờ.

## 22. Checklist trước khi merge

- [ ] Chọn Gradle Wrapper/JDK hợp lệ với Java 17+ target của dự án.
- [ ] Java/Java Library plugin tạo đúng source set `src/test/java` và Test tasks.
- [ ] `useJUnitPlatform()` có trên đúng task hoặc test suite tương ứng.
- [ ] `junit-jupiter-api`/`junit-jupiter-params` có khi compile tests; engine có lúc runtime.
- [ ] `junit-platform-launcher` được khai báo tường minh ở test runtime để căn chỉnh tốt với IDE/Gradle.
- [ ] BOM align Jupiter/Vintage 5.x và Platform 1.x đúng mapping.
- [ ] Nếu có JUnit 4 legacy tests, thêm Vintage runtime và JUnit4 API; đếm tests.
- [ ] Không nhầm engine IDs với Maven artifact IDs.
- [ ] Tag/engine/class filters phù hợp mục đích, không làm suite rỗng.
- [ ] Có báo cáo XML/HTML, CI thu nhận và fail khi test thất bại.
- [ ] Có cơ chế phát hiện 0 test khi test sources tồn tại.
- [ ] Parallel test workers/threads có giới hạn và fixtures thread-safe.
- [ ] Không lạm dụng `ignoreFailures` hay disable engine verification để CI xanh giả.
- [ ] Nếu dùng integration suite, task và dependencies của suite được cấu hình/kiểm tra riêng.
- [ ] Chạy Gradle CLI ngoài IDE để xác nhận discovery thực tế.
- [ ] Sau migration, so số test invocations và coverage trên CI trước/sau.
- [ ] Các JUnit version bumps đi cùng kiểm tra runtime classpath và test reports.

## 23. Ghi nhớ

- **JUnit Platform là hạ tầng**, **Jupiter và Vintage là các test engines**.
- **`useJUnitPlatform()` là lựa chọn Test framework của Gradle**, không phải dependency runtime và không tự thêm engine.
- **Jupiter API dùng khi compile**, **Jupiter Engine + Platform Launcher dùng lúc chạy**; dùng aggregator Jupiter nếu muốn khai báo gọn.
- **JUnit Vintage** cho phép tiếp tục chạy JUnit 3/4 tests trong giai đoạn migration.
- **JUnit BOM** giúp đồng bộ Jupiter/Vintage/Platform artifacts, tránh tự đoán version Platform.
- **Engine IDs `junit-jupiter`/`junit-vintage` khác artifact names**.
- **`--tests` lọc class/method**, **`includeTags`/`excludeTags` lọc tags**, **`includeEngines` lọc frameworks**.
- **Gradle Test forks JVM riêng**, report test có thể chứa nhiều invocations hơn số test methods khi dùng parameterized tests.
- **`No tests found` không tự có nghĩa là tests pass**. Kiểm tra source set, Test engine runtime, Platform configuration, filters, reports và fail-on-no-tests.
- **Gradle JVM Test Suite** và **JUnit Platform Suite Engine** là hai tầng khác nhau; không thay thế lẫn nhau.

## Tài liệu chính thức

- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform()`, Jupiter/Vintage, engine/tag filters, Test reports và detection behavior.
- [Gradle — Test Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): `failOnNoDiscoveredTests`, `Test` runtime, logging, filters và fork settings.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): `JvmTestSuite`, `useJUnitJupiter` và custom suites.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): runtime classpath/`dependencyInsight`.
- [JUnit 5.14.1 — Build Support](https://docs.junit.org/5.14.1/running-tests/build-support.html): BOM, Jupiter aggregator, Vintage, Platform launcher và Gradle setup.
- [JUnit 5.14.1 — User Guide](https://docs.junit.org/5.14.1/_exports/junit-user-guide-5.14.1.html): architecture, annotations, extensions, parameters, engines, discovery.
- [JUnit 5.14.1 — IDE Support](https://docs.junit.org/5.14.1/running-tests/ide-support.html): Launcher/Engine dependencies và IDE compatibility.
- [Maven Central — JUnit BOM 5.14.1](https://central.sonatype.com/artifact/org.junit/junit-bom/5.14.1): artifact/version constraints của Jupiter, Platform và Vintage.
