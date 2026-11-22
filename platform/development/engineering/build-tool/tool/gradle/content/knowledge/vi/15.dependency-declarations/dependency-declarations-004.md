# testImplementation, testRuntimeOnly và dependency cho bộ kiểm thử trong Gradle

## 1. Bối cảnh: test cần dependency riêng với mã sản phẩm

Dự án Java thường có **mã ứng dụng** trong `src/main/java` và **mã kiểm thử** trong `src/test/java`. Phần main được biên dịch và chạy trong môi trường sản phẩm; phần test cần thêm framework kiểm thử, thư viện assertion, mocking và các công cụ chỉ phục vụ kiểm thử. Chúng không nhất thiết cần xuất hiện trên production runtime classpath.

Đặt sai scope có thể tạo ra các vấn đề:

- Khai báo JUnit/Mockito/AssertJ ở `implementation` khiến thư viện chỉ dành cho test có mặt trong classpath production không cần thiết.
- Đặt JUnit API ở `testRuntimeOnly` khiến `compileTestJava` không nhận ra `org.junit.jupiter.api.Test`.
- Chỉ thêm JUnit annotation API mà thiếu **test engine** hoặc **launcher** dẫn đến lỗi khi thực thi test.
- Dùng `testImplementation` cho runtime driver/plugin không cần lúc compile làm classpath biên dịch lớn hơn cần thiết.
- Xem `implementation` thay vì `testRuntimeClasspath` và kết luận nhầm về thư viện thực sự được JVM test sử dụng.
- Dùng `useJUnitPlatform()` rồi cho rằng Gradle tự tải các thành phần runtime của JUnit.

**Mục tiêu học tập:** đọc được sự khác nhau giữa `testImplementation`, `testRuntimeOnly` và `testCompileOnly`; hiểu test compile/runtime classpaths; cấu hình một project **JUnit Jupiter/Java 17+ chạy được**; phân loại đúng test API và runtime engine/launcher; biết dùng `dependencies`/`dependencyInsight` để tìm lỗi.

Ví dụ dùng **Gradle Groovy DSL** trong `build.gradle`, không phải Kotlin DSL (`build.gradle.kts`). Dùng Wrapper của project; nếu chạy Gradle 9.x, JVM chạy Gradle phải là Java 17+.

## 2. Khi compile và khi chạy test, Java cần gì?

Để Gradle thực thi một test Java, có hai giai đoạn:

```text
src/main/java           src/test/java
     |                        |
 compileJava           compileTestJava
     |                        |
 main classes           test classes
     |                        |
     +-----------+------------+
                 |
         Gradle Test task
          (test JVM riêng)
                 |
       XML và HTML test report
```

**Compile test** sử dụng `testCompileClasspath`. Compiler phải thấy:

1. Các lớp của project cần kiểm tra, ví dụ `Calculator` ở `src/main/java`.
2. Annotation `@Test`, `Assertions.assertEquals`, Mockito API hoặc các lớp do test source **import trực tiếp**.
3. Các compile dependencies khác của test.

**Chạy test** sử dụng `testRuntimeClasspath` và compiled main/test classes. Test JVM cần những thành phần phát hiện và chạy test như JUnit Jupiter Engine, JUnit Platform Launcher, các runtime dependencies của ứng dụng và driver/plugin được load động.

Bởi vậy hai classpath **có phần chung** nhưng không đồng nhất. Việc compiler đã compile được `CalculatorTest` **không** bảo đảm Gradle đã có đủ thư viện để chạy test.

## 3. Các configuration do Java plugin cung cấp

Khi áp dụng `plugins { id 'java' }` hoặc `java-library`, Gradle tạo các configuration theo source set `main` và `test`.

| Configuration | Vai trò | Thường tham gia classpath nào? |
| --- | --- | --- |
| `implementation` | Dependency được mã sản phẩm dùng khi compile và chạy. | `compileClasspath`, `runtimeClasspath` và các test classpaths thừa hưởng dependency main. |
| `runtimeOnly` | Dependency của mã sản phẩm chỉ cần runtime. | `runtimeClasspath`, đồng thời có thể được test runtime kế thừa. |
| **`testImplementation`** | Dependency để **compile và chạy test**. | **`testCompileClasspath`**, **`testRuntimeClasspath`**. |
| **`testRuntimeOnly`** | Dependency chỉ cần **khi chạy test**, không cần để compile. | **`testRuntimeClasspath`**, không tự thêm vào test compile classpath. |
| `testCompileOnly` | API chỉ cần để compile test, không cần được thêm vào runtime. | `testCompileClasspath`. |
| `testAnnotationProcessor` | Annotation processor dành cho source test. | Processor path của `compileTestJava`. |

`testImplementation` và `testRuntimeOnly` là **declarable configurations** (nơi khai báo). Để xem phiên bản/JAR **được giải quyết thực tế**, dùng `testCompileClasspath` và `testRuntimeClasspath` (resolvable configurations). Không dùng một report chỉ trên `testImplementation` như bằng chứng toàn bộ runtime classpath.

### 3.1. Đường đi của dependency

```text
implementation ───────────┐
                           ├── testImplementation ───> testCompileClasspath
testCompileOnly ──────────┘

testImplementation ────────┐
testRuntimeOnly ───────────┼── testRuntimeClasspath
runtimeOnly ───────────────┘

main + test compiled classes + testRuntimeClasspath
                      |
                    Test task
```

Sơ đồ mô tả ý nghĩa kế thừa, không mô phỏng mọi lớp nội bộ của Gradle. `testImplementation` thường mở rộng `implementation`; `testRuntimeOnly` thường mở rộng `runtimeOnly`. Điều này cho phép test gọi được code của ứng dụng và các dependency cần thiết.

**Hướng kế thừa không đảo ngược:** JUnit được khai báo ở `testImplementation` **không tự xuất hiện** trên main `compileClasspath` hay `runtimeClasspath`, và không tự được publish cho người tiêu thụ thư viện. Test scopes giúp giữ production dependency graph gọn.

### 3.2. Chọn scope theo cách code sử dụng

Hãy đặt câu hỏi: **Mã Java test có import trực tiếp API nào từ dependency không?**

- Có: ưu tiên **`testImplementation`** (hoặc `testCompileOnly` trong trường hợp đặc biệt khi runtime có nguồn khác cung cấp).
- Không, dependency chỉ được framework/JVM load khi chạy: thường là **`testRuntimeOnly`**.
- Mã production thật sự cần dependency: dùng `implementation` hoặc `runtimeOnly` theo compile/runtime của production.
- Thư viện chỉ dùng bởi annotation processor của test: `testAnnotationProcessor`.
- Chỉ biết tên dependency nhưng chưa hiểu cơ chế: tra tài liệu của framework trước khi chọn.

**Ví dụ đối chiếu:**

```groovy
dependencies {
    // Đúng khi test import JUnit API:
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
```

Phản ví dụ khi **chỉ test source** dùng JUnit:

```groovy
dependencies {
    // Không nên đưa test framework vào production mặc định:
    implementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
}
```

Hai đoạn trên là **lựa chọn thay thế**, không dán cả hai vào một script.

## 4. JUnit Jupiter cần API, engine và launcher

JUnit 5 gồm **JUnit Platform**, **JUnit Jupiter** và một hệ engine mở rộng. Khi sử dụng `useJUnitPlatform()`, bản thân Gradle không tự cấp đầy đủ mọi library của JUnit.

| Thành phần | Module tiêu biểu | Scope hợp lý |
| --- | --- | --- |
| **Jupiter API** | `org.junit.jupiter:junit-jupiter-api` | `testImplementation`: test import `@Test`, `Assertions`. |
| **Jupiter Engine** | `org.junit.jupiter:junit-jupiter-engine` | `testRuntimeOnly`: JUnit Platform dùng khi tìm/chạy Jupiter tests. |
| **Platform Launcher** | `org.junit.platform:junit-platform-launcher` | `testRuntimeOnly`: Gradle dùng để tương tác với JUnit Platform. |
| **Jupiter aggregate** | `org.junit.jupiter:junit-jupiter` | `testImplementation` khi muốn convenience dependency gồm API/engine. |
| **Vintage Engine** | `org.junit.vintage:junit-vintage-engine` | `testRuntimeOnly` nếu muốn JUnit Platform chạy JUnit 3/4 tests. |
| **JUnit BOM** | `org.junit:junit-bom` | Version constraints cho JUnit modules, không phải engine riêng. |

**JUnit Platform Launcher và Jupiter Engine khác nhau:** launcher là lớp điều phối chạy test; engine hiểu cách khám phá/thực thi Jupiter tests. Khi chỉ có Jupiter API, test source có thể compile nhưng không có nghĩa JVM đã có engine.

Đặc biệt với **Gradle 9.x**, không nên dựa vào một số thư viện nội bộ mà Gradle phiên bản cũ vô tình đưa vào test runtime classpath. Tài liệu Gradle khuyến nghị khai báo **`junit-platform-launcher` tường minh**.

### 4.1. Cấu hình A: tách API / engine / launcher

```groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'

    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

JUnit BOM `5.11.4` căn chỉnh các phiên bản Jupiter `5.11.4` và JUnit Platform `1.11.4`. Nhờ BOM đang tham gia test dependency graph, các module theo sau có thể **không ghi version**; nếu bỏ BOM, phải khai báo các version tương thích bằng cách khác. Bài thực hành sẽ sử dụng cách A.

### 4.2. Cấu hình B: một Jupiter aggregate dependency

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Aggregate `junit-jupiter` có các transitive dependency dành cho Jupiter API/engine. Cách B gọn hơn, nhưng kém trực quan khi đang học sự khác nhau giữa compile API và runtime engine. Chọn **một** trong A hoặc B. Những version ở đây là bản đã phát hành dùng cho bài lab, **không được hiểu là phiên bản mới nhất** của JUnit.

## 5. Bài lab hoàn chỉnh với Java 17+ và Gradle Groovy DSL

### 5.1. Cấu trúc

Trong một thư mục mới, dùng Gradle Wrapper phù hợp. Chuẩn bị:

```text
test-dependency-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/example/Calculator.java
    └── test/java/example/CalculatorTest.java
```

`gradlew` và `gradle/wrapper` được tạo bằng task `gradle wrapper` khi máy đã có Gradle hoặc từ một project đã khởi tạo sẵn; bài không giả định Wrapper tự xuất hiện. Maven Central cần truy cập lần đầu nếu cache thiếu dependency.

### 5.2. settings.gradle

```groovy
rootProject.name = 'test-dependency-lab'
```

### 5.3. build.gradle

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Test compile: JUnit annotations, assertions và BOM constraints.
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'

    // Test runtime: engine và launcher.
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
```

**Giải thích:** plugin `java` tạo source sets `main`/`test` cùng `compileJava`, `compileTestJava`, `test` và `check`. `testImplementation` đặt JUnit API cho compiler test; `testRuntimeOnly` đặt engine và launcher để Gradle chạy test. `useJUnitPlatform` chọn runner; `testLogging` chỉ bật hiển thị kết quả trong console.

### 5.4. src/main/java/example/Calculator.java

```java
package example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException(
                    "denominator must not be zero");
        }
        return numerator / denominator;
    }
}
```

Production source chỉ sử dụng API Java, **không import JUnit**. Việc thêm JUnit ở test scopes không thay đổi tính đúng đắn của `compileJava`.

### 5.5. src/test/java/example/CalculatorTest.java

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void rejectsDivisionByZero() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> Calculator.divide(4, 0));
        assertEquals("denominator must not be zero", error.getMessage());
    }
}
```

Hai methods `@Test` có thể là package-private trong JUnit Jupiter. `Assertions` và `Test` đều thuộc Jupiter API; vì chúng được import trong test source nên phải được cung cấp ở **test compile classpath**.

### 5.6. Chạy thật

Linux/macOS:

```bash
./gradlew clean test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test --console=plain
```

Với các file và dependencies đúng, dự án có **2 tests PASS**. Vì `testLogging` có events `passed`, bạn sẽ thấy đoạn đại ý (thứ tự/dạng header có thể khác theo Gradle):

```text
CalculatorTest > addsTwoNumbers() PASSED
CalculatorTest > rejectsDivisionByZero() PASSED

BUILD SUCCESSFUL
```

Đây là **trích đoạn minh họa**, không phải toàn bộ stdout. Các dòng khởi động daemon, trạng thái task, thời gian và thứ tự test không cố định; mã Java không tự in thông báo. Cơ sở để xác định kết quả:

- `Calculator.add(2, 3)` trả `5`.
- `Calculator.divide(4, 0)` ném `IllegalArgumentException` có message chính xác `denominator must not be zero`.
- JUnit Jupiter chạy hai phương thức có annotation `@Test`.

Báo cáo kiểm thử chuẩn thường nằm ở `build/reports/tests/test/index.html` (HTML) và `build/test-results/test/` (XML). Trong CI, đẩy những artifacts này lên hệ thống build khi cần kiểm tra thất bại.

### 5.7. Chạy một test

```bash
./gradlew test --tests example.CalculatorTest.addsTwoNumbers --console=plain
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.CalculatorTest.addsTwoNumbers --console=plain
```

Cờ `--tests` chỉ lọc test cases, **không** thêm/bớt dependency. Nếu Gradle báo task `UP-TO-DATE`, chỉnh source test hoặc dùng `--rerun-tasks` trong lần chẩn đoán; không nhất thiết thêm cờ này vào CI thường xuyên.

## 6. Kiểm chứng dependency graph của test

Các dòng `dependencies { ... }` là yêu cầu ban đầu. Để biết module/version thực sự được chọn, dùng reports.

### 6.1. Test compile classpath

```bash
./gradlew -q dependencies --configuration testCompileClasspath
```

Tìm `org.junit.jupiter:junit-jupiter-api` và `org.junit:junit-bom` (với constraint tham gia chọn phiên bản). Mã test cần thấy API. Jupiter Engine và Platform Launcher trong lab được khai báo ở `testRuntimeOnly`, nên không có lý do để xuất hiện **chỉ bởi các khai báo đó** trên compile classpath; nếu report thực tế cho thấy chúng qua transitive dependencies thì phải truy nguồn đúng đường.

### 6.2. Test runtime classpath

```bash
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Tìm đủ `junit-jupiter-api`, `junit-jupiter-engine` và `junit-platform-launcher`. API còn ở runtime vì test code cần nó khi chạy; engine/launcher được thêm từ runtime-only. Với BOM `5.11.4`, phiên bản launcher được chọn là thuộc JUnit Platform dòng `1.11.4`.

Truy nguyên version hoặc đường đưa module vào graph:

```bash
./gradlew -q dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-jupiter-engine

./gradlew -q dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-platform-launcher
```

`dependencyInsight` hữu ích khi nhiều module cùng yêu cầu version khác nhau, khi có BOM/constraint hoặc đang điều tra runtime mismatch. Đọc cả requested và selected; ký hiệu `(c)` trong dependency tree là **constraint**, không phải bản JAR được tải riêng bởi chính dòng đó.

### 6.3. So với production runtime

```bash
./gradlew -q dependencies --configuration runtimeClasspath
```

Trong **lab chưa có production dependencies**, main `runtimeClasspath` không chứa các JUnit libraries chỉ khai báo ở test scopes. Nếu report production của một project lớn vẫn có JUnit, nguyên nhân có thể là một library production khác kéo nó vào; dùng `dependencyInsight` trước khi kết luận scope bị rò rỉ.

**Cần nhớ:** `testImplementation` và `testRuntimeOnly` là nơi **khai báo**, còn `testCompileClasspath` và `testRuntimeClasspath` là nơi nên **resolve để chẩn đoán**. Khi lỗi ở project `:app`, dùng `:app:dependencies`, không đọc nhầm report root.

## 7. Vì sao engine/launcher thường là testRuntimeOnly?

Đặt câu hỏi **ai gọi các class đó?**

- Test source của bạn import `org.junit.jupiter.api.Test`, `Assertions` → compiler cần Jupiter API → `testImplementation`.
- JUnit Platform phát hiện engine khi JVM chạy test → engine không cần làm API mà test source import → `testRuntimeOnly`.
- Gradle gọi Platform Launcher để điều khiển việc thực thi → launcher không cần cho compile test source → `testRuntimeOnly`.

Một biến thể không dùng BOM, với version explicit:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}
```

Đây là **đoạn thay thế** cho `dependencies` trong lab, không thêm trùng. Nếu bạn đưa engine hoặc launcher vào `testImplementation`, test vẫn có thể chạy do testImplementation góp vào runtime, nhưng classpath compile test chứa runtime infrastructure không cần thiết. Mục tiêu tách scope là diễn tả đúng dependency role, không phải chỉ làm build chạy được bằng mọi giá.

### 7.1. Một driver chỉ được load động khi test chạy

Thư viện driver H2 có thể dùng qua `DriverManager` của Java:

```groovy
dependencies {
    // Ví dụ mở rộng, không cần cho CalculatorTest.
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}
```

Test có thể chỉ import `java.sql.DriverManager`, rồi mở kết nối `jdbc:h2:mem:demo`. Implementation của JDBC driver được đăng ký bằng SPI trên runtime classpath; compiler không cần biết class H2 cụ thể.

**Nếu test source import trực tiếp `org.h2.Driver`** thì trường hợp đổi: compiler cần dependency đó → dùng `testImplementation`. Không chọn scope chỉ dựa vào nhãn “driver”; chọn theo cách code thực sự tham chiếu nó.

### 7.2. Mockito, AssertJ và test helpers

Nếu test viết:

```java
import static org.mockito.Mockito.mock;
import static org.assertj.core.api.Assertions.assertThat;
```

Mockito/AssertJ cung cấp API mà compiler thấy trong **test source**, nên thường thuộc `testImplementation`. Đoạn này chỉ minh họa việc chọn scope; muốn chạy cần thêm đúng Mockito/AssertJ modules và test body thực tế, không chèn hai imports này vào `CalculatorTest` của lab khi chưa khai báo dependencies.

Với frameworks có plugin/engine runtime riêng, hãy dùng đúng tài liệu của framework để tách compile API và runtime implementation.

## 8. Các bộ kiểm thử khác: JUnit 4, Vintage và TestNG

Những mẫu sau là **các lựa chọn thay thế**, không được ghép tự động với lab JUnit Jupiter.

### 8.1. JUnit 4 thuần

```groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
}

tasks.named('test', Test) {
    useJUnit()
}
```

JUnit 4 dùng `org.junit.Test`, không phải `org.junit.jupiter.api.Test`. Khi chạy JUnit 4 theo cơ chế truyền thống, không cần Jupiter engine hoặc Platform launcher chỉ vì test dùng annotation JUnit 4.

### 8.2. Chạy test JUnit 4 bằng JUnit Platform/Vintage

```groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`junit-vintage-engine` chỉ cần runtime; nó nhận diện JUnit 3/4 tests. Test source kiểu cũ vẫn cần `junit:junit` để compile imports của JUnit 4.

### 8.3. TestNG

```groovy
dependencies {
    testImplementation 'org.testng:testng:7.10.2'
}

tasks.named('test', Test) {
    useTestNG()
}
```

Với TestNG, dùng `useTestNG()` thay vì mặc định dùng `useJUnitPlatform()`. Tùy framework, các adapters bổ sung có thể cần ở test runtime. Hãy phân biệt **test runner** của Gradle với **dependency modules** của framework.

## 9. Nhiều source sets và bộ integration tests

### 9.1. Không mặc định test suite mới dùng classpath của test cũ

Java plugin tạo source set `test` chuẩn. Một source set khác như `integrationTest` có thể tạo ra các configuration như `integrationTestImplementation`, `integrationTestRuntimeOnly` khi được định nghĩa. JVM Test Suite plugin cũng cho phép mô tả các suite riêng.

Với một task `Test` tự tạo, phải cung cấp đúng **testClassesDirs** và **classpath** của suite. Gradle 9 đã bỏ một convention cũ khiến `tasks.register('otherTest', Test)` mặc nhiên dùng classes/classpath của source set `test`; khi nâng Gradle, viết task mới mà quên cấu hình có thể dẫn tới không chạy test như mong đợi.

Bộ integration test có thể cần driver thật, container libraries hoặc endpoint, trong khi unit test dùng mocks. Tách dependencies theo suite để tránh kéo mọi integration tool vào runtime của unit tests.

### 9.2. Test fixtures chia sẻ cho nhiều module

Nếu nhóm có thư viện test helpers dùng chung, plugin `java-test-fixtures` tạo source set fixtures và các configuration test-fixture scopes:

```groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}
```

Trong project khác có `:shared` dùng plugin đó, có thể tiêu thụ fixtures:

```groovy
dependencies {
    testImplementation testFixtures(project(':shared'))
}
```

Đây là **ví dụ multi-project**, không phải build script chạy độc lập trong lab Calculator. Không đưa fixture dependencies vào `implementation` của sản phẩm chỉ vì tests cần helper.

## 10. BOM, version catalog và tính tái lập

BOM giúp căn chỉnh version giữa các module trong cùng một hệ sinh thái. Ví dụ:

```groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

JUnit Jupiter `5.11.4` tương ứng JUnit Platform `1.11.4`, không phải hai library cùng số `5.11.4`. BOM không tự làm runtime có engine/launcher; nó chỉ cung cấp constraints **cho modules đã được yêu cầu**.

Các dự án lớn có thể dùng `gradle/libs.versions.toml` (version catalog) để quản lý tọa độ; điều đó không thay thế việc xác minh selected versions trong resolved graphs. Tránh dùng `+` như `5.+` nếu build cần reproducibility. Nếu dùng dependency locking, kiểm tra lockfiles phù hợp trước/sau khi thay đổi và tránh tự chạy `--write-locks` khi chỉ cần xem báo cáo, vì cờ này có thể thay đổi file.

Khi dùng CI, pin Gradle Wrapper, dùng JDK phù hợp và kiểm tra các test frameworks sau nâng cấp. Một engine mới với launcher quá cũ có thể phát sinh lỗi runtime dù compiler hoàn toàn chấp nhận API.

## 11. Lỗi thường gặp: chọn đúng classpath trước khi sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách chẩn đoán/sửa |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` khi compile test | API JUnit không nằm trên test compile classpath. | `testImplementation` Jupiter API, kiểm tra BOM/version và `testCompileClasspath`. |
| Test compile pass nhưng test runtime fail | Có API nhưng thiếu engine/launcher/driver. | Xem `testRuntimeClasspath`, thông báo lỗi và phiên bản đã chọn. |
| Không có `TestEngine` thích hợp | Chưa có Jupiter Engine trong test runtime. | Dùng `testRuntimeOnly` cho engine hoặc aggregate Jupiter. |
| Gradle báo lỗi launcher/Platform khi chạy test | Thiếu hoặc không tương thích Launcher. | Khai báo `junit-platform-launcher` tại `testRuntimeOnly`, dùng BOM/versions đúng. |
| Test dùng Jupiter annotations nhưng không được phát hiện | Chưa `useJUnitPlatform()`, sai source path hoặc filter. | Kiểm tra Test task, source set, annotations và `--tests`. |
| Test cần JUnit 4 nhưng runner là Platform | Chưa có Vintage Engine. | Dùng `useJUnit()` cho JUnit 4 thuần hoặc thêm Vintage Engine. |
| Test import Mockito nhưng khai báo `testRuntimeOnly` | Compiler không có Mockito API. | Đổi sang `testImplementation`. |
| Main runtime có JUnit không cần thiết | JUnit bị đưa vào `implementation` hoặc kéo bắc cầu. | Đọc `runtimeClasspath` và truy nguồn, sửa scope theo nhu cầu. |
| Test chạy trong IDE nhưng fail qua Wrapper | IDE có classpath khác hoặc cache cũ. | Dùng `./gradlew clean test` làm chuẩn và xem resolved classpaths. |
| Unit tests pass nhưng integration tests thiếu library | Suite khác có dependencies riêng. | Cấu hình `integrationTestImplementation`/`integrationTestRuntimeOnly` tương ứng. |
| Chạy test ở root trong multi-project nhưng lỗi ở subproject | Report sai project. | Chạy `:module:test` và `:module:dependencies`. |
| Test không chạy lại | Task `UP-TO-DATE` hoặc filter không khớp. | Kiểm tra task outcome; thử `--rerun-tasks` chỉ khi điều tra. |

### 11.1. Quy trình tìm lỗi cụ thể

1. Xác định lỗi ở `compileTestJava` hay `test`; ghi module/project path.
2. Với compile error, kiểm tra imports và `testCompileClasspath`.
3. Với runtime error, kiểm tra `testRuntimeClasspath`, engine/launcher và các driver.
4. Dùng `dependencyInsight` trên dependency nghi vấn để xem selected version và constraint.
5. Thay **một** khai báo/scope/version có lý do, rồi chạy lại `./gradlew clean test`.
6. Đọc production `runtimeClasspath` nếu bạn vừa di chuyển một test dependency khỏi `implementation`, đảm bảo test library không xuất hiện ở môi trường chính ngoài chủ đích.

## 12. Bài tập và đáp án tự kiểm tra

**Bài 1 — Phân loại:** chọn `testImplementation` hay `testRuntimeOnly` cho (a) Jupiter `@Test`, (b) Jupiter Engine, (c) Platform Launcher, (d) AssertJ `assertThat`, (e) H2 JDBC driver dùng qua `DriverManager` mà không import H2. Đáp án tương ứng: (a) implementation test, (b) runtime-only, (c) runtime-only, (d) implementation test, (e) runtime-only.

**Bài 2 — Thiếu API:** trong bản sao lab, xóa `testImplementation 'org.junit.jupiter:junit-jupiter-api'` rồi chạy `./gradlew compileTestJava`. Vì sao compiler báo thiếu package Jupiter? Khôi phục file trước khi thử tiếp.

**Bài 3 — Thiếu engine:** trong mẫu A, bỏ Jupiter Engine rồi chạy test và quan sát error. Nếu một project khác có engine qua transitive Jupiter aggregate, dùng `dependencyInsight` để xác minh, đừng đoán từ một dòng script. Khôi phục trước khi thử phần sau.

**Bài 4 — Launcher:** xóa launcher runtime trong bản sao lab, chạy bằng Gradle 9 và đọc `testRuntimeClasspath`. Vì sao `useJUnitPlatform()` không tự thay thế dependency launcher?

**Bài 5 — Hai classpaths:** so sánh `testCompileClasspath` và `testRuntimeClasspath`, tìm API, Engine, Launcher. Vì sao không nên dùng `testImplementation` làm report resolved duy nhất?

**Bài 6 — BOM:** từ JUnit BOM `5.11.4`, giải thích vì sao Platform Launcher có version `1.11.4` chứ không phải `5.11.4`, và đâu là nguồn quyết định version cuối.

**Bài 7 — Giới hạn phạm vi:** chuyển JUnit API sang `implementation` trong bản sao, so sánh main `runtimeClasspath` before/after. Vì sao cấu hình này không phù hợp nếu chỉ `src/test/java` cần API?

**Bài 8 — Một test:** chạy `./gradlew test --tests example.CalculatorTest.rejectsDivisionByZero`. Test nào được chọn? Tham số `--tests` có đổi dependency không?

**Bài 9 — Multi-project:** giả sử lỗi xảy ra ở `:service:test`. Cần chạy `:service:dependencies --configuration testRuntimeClasspath` thay vì báo cáo root không? Vì sao?

### Câu hỏi ngắn

1. **`testImplementation` có tham gia runtime test không?** Có, không chỉ compile.
2. **`testRuntimeOnly` có giúp compile annotation `@Test` không?** Không.
3. **JUnit Platform có chạy Jupiter tests mà không có engine nào không?** Không.
4. **`useJUnitPlatform()` có tự thêm JUnit libraries không?** Không.
5. **Nếu test source import Mockito API, scope thích hợp?** `testImplementation`.
6. **JUnit dependency trong test scopes có tự bị publish sang consumer của library?** Không theo cấu hình test mặc định.
7. **Nơi xem toàn bộ runtime dependencies của test?** `testRuntimeClasspath`.
8. **Nơi xem HTML và XML test reports?** `build/reports/tests/test/` và `build/test-results/test/`.
9. **Có cần nhét JUnit vào `implementation` để chạy test không?** Không.
10. **Nếu có suite integrationTest riêng, nó có thể cần runtime dependencies riêng không?** Có; cấu hình theo suite.

## 13. Tham khảo

- **Gradle — Testing in Java & JVM Projects:** Test task, JUnit Platform, Jupiter, Vintage, launcher và classpath: https://docs.gradle.org/current/userguide/java_testing.html
- **Gradle — The Java Library Plugin:** các configuration `testImplementation`, `testRuntimeOnly` và các resolved classpaths: https://docs.gradle.org/current/userguide/java_library_plugin.html
- **Gradle — Creating Dependency Configurations:** declarable/resolvable/consumable, source sets: https://docs.gradle.org/current/userguide/declaring_configurations.html
- **Gradle — Building Java & JVM Projects:** Java dependency scopes: https://docs.gradle.org/current/userguide/building_java_projects.html
- **Gradle — Platforms (BOM):** phiên bản được ràng buộc và căn chỉnh: https://docs.gradle.org/current/userguide/platforms.html
- **Gradle — Viewing Dependencies:** `dependencies`, `dependencyInsight`: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Upgrading to Gradle 9:** các thay đổi test classpath và Test task: https://docs.gradle.org/current/userguide/upgrading_major_version_9.html
- **JUnit 5 User Guide:** https://docs.junit.org/5.11.4/user-guide/
- **JUnit BOM 5.11.4 trên Maven Central:** https://central.sonatype.com/artifact/org.junit/junit-bom/5.11.4

**Kết luận:** `testImplementation` là nơi khai báo API mà mã test cần ở compile và runtime; `testRuntimeOnly` là nơi khai báo engine, launcher, driver và plugin chỉ dùng khi JVM thực thi test. Chọn scope theo cách thư viện được sử dụng, áp dụng JUnit BOM/versions nhất quán, kiểm tra `testCompileClasspath` và `testRuntimeClasspath` rồi chạy `./gradlew test` để xác thực.