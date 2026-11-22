# Lọc theo lớp, phương thức, tag và bộ kiểm thử trong Gradle

## 1. Vì sao cần lọc test?

Trong một dự án Java, khi sửa một lỗi nhỏ, chạy hàng nghìn unit tests, integration tests và end-to-end tests mỗi lần có thể rất tốn thời gian. Gradle hỗ trợ nhiều tầng lựa chọn:

- **Lớp kiểm thử**: chỉ chạy một class như `example.CalculatorTest`.
- **Phương thức kiểm thử**: chỉ chạy `example.CalculatorTest.addsNumbers`.
- **Mẫu tên**: chọn các lớp/phương thức có tên khớp wildcard `*`.
- **JUnit Platform tag**: chọn các tests có nhãn `fast`, `slow`, `smoke` hoặc `integration`, không phụ thuộc vào tên class.
- **Bộ kiểm thử (test suite)**: chạy đúng một `Test` task, ví dụ `test` cho unit tests và `integrationTest` cho integration tests, với source set/dependencies/classpath riêng.

Các tầng này **không thay thế nhau**. `--tests` không hiểu JUnit tags; `includeTags` không tự tạo integration test task; và gọi `test` không tự chạy mọi test suite đã được định nghĩa trong cả build.

**Mục tiêu:** hiểu cơ chế lọc test của Gradle và JUnit Platform, thực hành lệnh CLI, cấu hình lọc trong `build.gradle` (Groovy DSL), biết cách chọn một suite cụ thể, xử lý trường hợp không khớp test, và xây quy trình CI có test coverage rõ ràng.

Ví dụ dùng **Gradle Groovy DSL**, Java 17+ và JUnit Jupiter 5.11.4. Mọi mã Java trong lab được viết đủ để compile/run. Các ví dụ mở rộng được đánh dấu **thay thế** hoặc **bổ sung**; đừng gộp các cấu hình lọc có mục đích mâu thuẫn vào cùng một build.

## 2. Bốn tầng lựa chọn test: hiểu đúng trước khi chạy lệnh

```text
Project :app hoặc root project
|
+-- Gradle task :test                   [bộ unit tests]
|      |
|      +-- TestFilter / --tests         [tên lớp, tên phương thức]
|      |      |
|      |      +-- JUnit Platform        [includeTags/excludeTags]
|      |                |
|      |                +-- tests được khám phá và thực thi
|      |
|      +-- Test reports
|
+-- Gradle task :integrationTest       [bộ integration tests]
       |
       +-- TestFilter / --tests         [áp dụng cho task này]
       +-- JUnit Platform tags         [cấu hình riêng được]
       +-- Test reports của task này
```

| Bạn muốn | Công cụ chính | Ví dụ |
| --- | --- | --- |
| Chỉ một class | `--tests` của Gradle `Test` task | `./gradlew test --tests example.CalculatorTest` |
| Chỉ một method | `--tests` với class.method | `./gradlew test --tests example.CalculatorTest.addsNumbers` |
| Nhiều tên cùng quy tắc | `--tests '*Pattern'` hoặc `filter { includeTestsMatching ... }` | `--tests '*Test'` |
| Theo nhãn ý nghĩa | JUnit Jupiter `@Tag` và JUnit Platform `includeTags`/`excludeTags` | `-PtestTags=fast` nếu build script hỗ trợ |
| Một bộ tests riêng | Chọn **task** của suite | `./gradlew integrationTest` |
| Nhiều bộ tests | Gọi nhiều tasks hoặc lifecycle đã nối | `./gradlew test integrationTest` |
| Xem test được chọn, không thực thi | `--test-dry-run` | `./gradlew test --test-dry-run --tests '*Test'` |

**Hai thuật ngữ giống nhau nhưng khác:** `TestFilter` là API lọc **test cases trong một `Test` task**; `JvmTestSuite` là mô hình **một tập tests có nguồn, dependencies và targets riêng**. Một suite thường tạo một task `Test` mặc định, nhưng một suite có thể có thêm targets, mỗi target lại có task và filter riêng.

## 3. Dự án mẫu: 5 tests, 2 classes, 4 nhóm tag

### 3.1. Cấu trúc thư mục

Tạo project Java mới với Gradle Wrapper tương thích và các file sau:

```text
gradle-test-filter-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/Calculator.java
    └── test/java/example/
        ├── CalculatorTest.java
        └── TextTest.java
```

File `gradlew` và thư mục `gradle/wrapper` phải được tạo bằng Gradle Wrapper của project, ví dụ qua `gradle wrapper` hoặc `gradle init` từ Gradle tương thích. Chỉ chép các file Java/Groovy mà không có Wrapper thì lệnh `./gradlew` không tự hoạt động.

### 3.2. File settings.gradle

```groovy
rootProject.name = 'gradle-test-filter-lab'
```

### 3.3. File build.gradle

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Jupiter API ở test compile classpath.
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'

    // JUnit Platform chạy tests tại runtime.
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Mặc định chạy tất cả tags. Có thể thêm -PtestTags=fast
// hoặc -PtestTags=slow để chỉ lấy nhóm tương ứng.
def requestedTags = providers.gradleProperty('testTags').orNull

tasks.named('test', Test) {
    useJUnitPlatform {
        if (requestedTags != null && !requestedTags.isBlank()) {
            includeTags requestedTags
        }
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Vì sao cấu hình như vậy?**

1. Plugin `java` tạo source set `test` và task `test` kiểu `Test`.
2. `testImplementation` đưa `@Test`, `@Tag` và Assertions vào compile classpath.
3. `testRuntimeOnly` đưa Jupiter engine và Platform launcher vào runtime; đặc biệt với Gradle 9, không dựa vào thư viện test nội bộ của Gradle bị lộ classpath như các bản cũ.
4. JUnit BOM `5.11.4` quản lý Jupiter modules `5.11.4` và JUnit Platform `1.11.4`.
5. `useJUnitPlatform` bật JUnit Platform cho Gradle. Nếu có `-PtestTags=...`, `includeTags` mới được thêm; nếu không thì **không có tag restriction**, nên cả tests có tag lẫn tests không tag đều được chạy.
6. `providers.gradleProperty('testTags')` đọc **Gradle project property**. Nó **không phải** một option `--tests` của Gradle. Việc dùng Provider API giúp không hardcode tên tag vào build.
7. `testLogging.events` giúp quan sát số trường hợp được chọn trong console; nó không thay đổi bộ tests được thực thi.

Đây là **một file build.gradle hoàn chỉnh**, không cần thêm task `test` thủ công. Nếu bạn có build script khác, hãy ghép các phần có chủ đích để tránh lặp `useJUnitPlatform` hay khai báo version lệch.

### 3.4. File src/main/java/example/Calculator.java

```java
package example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static int subtract(int a, int b) {
        return a - b;
    }

    public static int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException(
                    "divisor must not be zero");
        }
        return a / b;
    }
}
```

Class này không dùng thư viện bên ngoài, không in stdout. Nó có ba method production để các tests xác minh hành vi, gồm lỗi chia cho 0 có message xác định.

### 3.5. File src/test/java/example/CalculatorTest.java

```java
package example;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    @Test
    @Tag("fast")
    void addsNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    @Tag("slow")
    void subtractsNumbers() {
        assertEquals(3, Calculator.subtract(7, 4));
    }

    @Test
    @Tag("smoke")
    void rejectsZeroDivisor() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> Calculator.divide(10, 0));
        assertEquals("divisor must not be zero",
                error.getMessage());
    }

    @Test
    void worksWithoutATag() {
        assertEquals(0, Calculator.subtract(2, 2));
    }
}
```

Trong class này có **4 test methods**:

| Method | JUnit tag | Kết quả |
| --- | --- | --- |
| `addsNumbers` | `fast` | PASS (3 + 4 = 7). |
| `subtractsNumbers` | `slow` | PASS (7 - 4 = 3). |
| `rejectsZeroDivisor` | `smoke` | PASS (kiểm tra exception và message). |
| `worksWithoutATag` | Không có tag | PASS (2 - 2 = 0). |

Không có method nào sử dụng `System.out.println`, vì vậy đừng dự đoán có các dòng in số `7` hay `3` từ mã test. Console log được Gradle/JUnit tạo theo cấu hình `testLogging`.

### 3.6. File src/test/java/example/TextTest.java

```java
package example;

import java.util.Locale;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("fast")
class TextTest {

    @Test
    void uppercasesText() {
        assertEquals("HELLO",
                "hello".toUpperCase(Locale.ROOT));
    }
}
```

`@Tag("fast")` nằm trên **class**, nên JUnit Jupiter áp dụng tag đó cho các test methods trong class. Với `TextTest` hiện tại có **1 test fast**. Nếu bạn thêm các test methods không gắn tag vào class này, chúng vẫn nhận `fast` từ class-level tag.

### 3.7. Chạy baseline và kiểm tra số lượng

Linux/macOS:

```bash
./gradlew clean test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test --console=plain
```

Khi các file được đặt đúng và Maven Central truy cập được, Gradle sẽ biên dịch source rồi JUnit Platform chạy **5 tests PASS**. Vì `testLogging` bật sự kiện `passed`, phần log test có thể tương tự:

```text
CalculatorTest > addsNumbers() PASSED
CalculatorTest > subtractsNumbers() PASSED
CalculatorTest > rejectsZeroDivisor() PASSED
CalculatorTest > worksWithoutATag() PASSED
TextTest > uppercasesText() PASSED

BUILD SUCCESSFUL
```

Đây là **trích đoạn minh họa**, không phải toàn bộ stdout có thể so sánh từng byte. Thứ tự test, task output, daemon, thời gian và trạng thái `UP-TO-DATE` phụ thuộc môi trường. Kết quả đúng từ mã là **4 tests trong CalculatorTest, 1 test trong TextTest**.

Reports mặc định:

- HTML: `build/reports/tests/test/index.html`.
- XML: `build/test-results/test/`.

Một test có trạng thái `PASSED` không có nghĩa một test khác không được chọn cũng đã được kiểm tra. Khi lọc để phát triển nhanh, vẫn cần CI có bước chạy bộ test đầy đủ.

## 4. Lọc theo lớp với --tests

### 4.1. Chọn đúng một class bằng fully qualified name

```bash
./gradlew test --tests example.CalculatorTest --console=plain
```

Kỳ vọng **4 tests** trong `CalculatorTest` được chọn; `TextTest.uppercasesText` **không** được chọn.

Nếu muốn `TextTest`:

```bash
./gradlew test --tests example.TextTest --console=plain
```

Kỳ vọng **1 test**.

Cấu trúc `--tests` thường chấp nhận:

- Fully qualified class name: `example.CalculatorTest`.
- Simple class name bắt đầu bằng chữ hoa: `CalculatorTest` (Gradle hỗ trợ cách hiểu simple class name từ Gradle 4.7).
- Mẫu wildcard `*` như `*Test`, `example.*Test`.

Ví dụ với simple class name:

```bash
./gradlew test --tests CalculatorTest --console=plain
```

Câu lệnh này chỉ định tên class không cần package. Nếu nhiều package có class cùng simple name, nó có thể chọn **nhiều classes** phù hợp; khi cần tính xác định trong CI, nên dùng **fully qualified name**.

### 4.2. Chọn nhiều class theo tên

```bash
./gradlew test --tests '*Test' --console=plain
```

Trong lab, cả `CalculatorTest` và `TextTest` đều kết thúc bằng `Test`, nên cả **5 tests** phù hợp.

Chú ý:

- `*` là wildcard kiểu matching text của Gradle, **không phải Java regex**.
- Wildcard `*` không hiểu đặc biệt dấu chấm phân cách Java package. `--tests 'example.*'` có thể khớp tests bên dưới package đó; dùng tên cụ thể nếu không muốn lấy cả nested packages.
- Bọc patterns bằng **dấu nháy** trong Bash/Zsh/PowerShell để shell không tự mở rộng `*` thành file path.
- `--tests` chọn **tests trong task được chỉ định**, không tạo task mới hoặc tải JUnit engine.

### 4.3. Lọc tên lớp không phải chọn mọi project

Với một multi-project build:

```bash
./gradlew :core:test --tests example.CalculatorTest
```

Lệnh trên chỉ áp dụng khi project `:core` thật sự tồn tại. Nó chạy task `:core:test`, không phải tự động chạy `:app:test` dù app có class cùng tên. Nếu bạn chạy task tên `test` ở phạm vi bao gồm nhiều subprojects, cần quan sát những task paths được chọn để không suy đoán filter đã giới hạn đúng module.

## 5. Lọc theo phương thức và multiple patterns

### 5.1. Một phương thức chính xác

```bash
./gradlew test \
  --tests example.CalculatorTest.addsNumbers \
  --console=plain
```

Kỳ vọng **1 test** `addsNumbers`, không chạy ba methods khác của `CalculatorTest`.

Có thể dùng simple class + method:

```bash
./gradlew test --tests CalculatorTest.rejectsZeroDivisor
```

Kỳ vọng **1 test** `rejectsZeroDivisor`.

**Không** dùng `--tests addsNumbers` và mặc định rằng Gradle sẽ tìm tất cả methods mang tên này. Mẫu bắt đầu bằng chữ thường thường được hiểu như fully qualified name. Để tìm method theo suffix trong nhiều classes, dùng wildcard:

```bash
./gradlew test --tests '*Test.addsNumbers'
```

Với mã lab, mẫu này chọn `CalculatorTest.addsNumbers`. Khi nhiều test classes có method cùng tên, mẫu sẽ chọn nhiều tests — đọc reports để xác minh.

### 5.2. Wildcard trong method names

```bash
./gradlew test --tests 'example.CalculatorTest.*Numbers'
```

Với lab, mẫu này chọn:

- `addsNumbers`.
- `subtractsNumbers`.

Hai methods còn lại không kết thúc bằng `Numbers`. Wildcard không phải regex: `.*`, `^...$` hay character groups không mang ngữ nghĩa regex như Java `Pattern`.

### 5.3. Nhiều --tests: lấy nhiều patterns

```bash
./gradlew test \
  --tests example.CalculatorTest.addsNumbers \
  --tests example.TextTest.uppercasesText \
  --console=plain
```

Kỳ vọng **2 tests** — mỗi pattern bổ sung một tập matches. Không đọc hai flags như phép AND “một test phải có hai tên”; chúng là nhiều inclusion patterns. Nhưng **các filters khác đã được khai báo trong build** vẫn có tác động; đặc biệt nếu `-PtestTags=slow` thì hai test ở trên không có tag `slow` và có thể không được chạy.

Trên Windows PowerShell, dùng một dòng khi thuận tiện:

```powershell
.\gradlew.bat test --tests example.CalculatorTest.addsNumbers --tests example.TextTest.uppercasesText --console=plain
```

### 5.4. Filter mặc định có thể làm test fail khi pattern không khớp

Thử cố ý nhập sai:

```bash
./gradlew test --tests example.CalculatorTest.noSuchMethod
```

Gradle thường báo lỗi dạng `No tests found for given includes` vì `TestFilter.failOnNoMatchingTests` mặc định là **true** khi có include filter và không tìm thấy test phù hợp. Đây là tín hiệu hữu ích, đặc biệt trong CI, để phát hiện typo thay vì “pass vì không chạy gì”.

Không sửa bằng cách tắt fail mặc định ngay. Trước tiên kiểm tra package, class/method name, `@Test`, JUnit runner, source sets và các filters khác.

## 6. Lọc cố định trong build.gradle bằng TestFilter

`--tests` hợp cho việc **chạy tạm thời từ CLI**; `filter { ... }` hợp khi muốn một **task luôn chạy một tập con** theo naming convention.

Ví dụ **thay thế** phần `tasks.named('test', Test)` ở lab (không thêm song song nếu không muốn filters tích lũy):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    filter {
        includeTestsMatching 'example.CalculatorTest.*'
        excludeTestsMatching 'example.CalculatorTest.subtractsNumbers'
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Với dữ liệu lab, `test` được cấu hình chỉ chạy **3 methods** của `CalculatorTest`, trừ `subtractsNumbers`, và không chạy `TextTest`.

**Phân biệt hai nhóm API:**

| API | Ý nghĩa |
| --- | --- |
| `filter.includeTestsMatching 'pattern'` | Thêm một inclusion pattern theo tên test. |
| `filter.excludeTestsMatching 'pattern'` | Loại tên test khớp pattern, kể cả nếu inclusion khác match. |
| `filter.includeTest 'example.CalculatorTest', 'addsNumbers'` | Thêm chính xác class + method theo hai tham số. |
| `filter.excludeTest 'example.CalculatorTest', 'subtractsNumbers'` | Loại chính xác method. |
| `filter.failOnNoMatchingTests = true` | Giữ fail khi filter được dùng mà không có tests phù hợp. |

Cú pháp alternative cho một test:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    filter {
        includeTest 'example.CalculatorTest', 'addsNumbers'
    }
}
```

Dòng `includeTest` không phải `includeTags`. Đây vẫn là **name-based test selection của Gradle**.

### 6.1. Khi CLI và build.gradle đều có filter

Theo tài liệu Gradle, khi dùng `--tests`, những inclusions khai báo sẵn trong build script **vẫn được tôn trọng**. Đừng coi CLI có quyền vượt mọi rules trước đó. Trong thực tế, một test có thể không chạy vì các exclusions ở filter, JUnit tag conditions, source-set include/exclude hoặc test engine.

Cách điều tra tốt nhất là xem toàn bộ filters tại task `test`, chạy `--test-dry-run` để xem danh sách cuối và dùng fully qualified method để loại nhập nhằng.

### 6.2. failOnNoMatchingTests: khi nào được phép nới?

Trong một task test có filter:

```groovy
tasks.named('test', Test) {
    filter {
        includeTestsMatching '*OptionalTest'
        failOnNoMatchingTests = false
    }
}
```

Nếu không có method/class phù hợp, filter có thể không khiến task fail vì **không match**. Đây là **biến thể đặc biệt** cho task optional, không phải mặc định nên dùng cho unit tests bắt buộc. CI cần bảo vệ độ phủ test không nên bật false hàng loạt; một build “xanh” nhưng thực thi 0 tests là false positive nguy hiểm.

## 7. Lọc theo @Tag trong JUnit Jupiter

**`@Tag` thuộc JUnit Jupiter/JUnit Platform, không thuộc API `TestFilter` của Gradle.** Bạn có thể đặt tag trên class hoặc method:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("smoke")
class ExampleTest {
    @Test
    void criticalPath() {
        // Test chạy khi chọn tag smoke.
    }

    @Test
    @Tag("fast")
    void anotherPath() {
        // Test này có cả tag smoke (từ class) và fast.
    }
}
```

Đây là **đoạn minh họa**, class không chứa assertion vì mục đích chỉ cho thấy inherited class tags; không thay thế các JUnit tests có assertion trong lab.

Quy tắc:

- Class-level `@Tag("fast")` được kế thừa tới test methods trong class.
- Method-level `@Tag("slow")` gắn tag riêng cho method; class-level tag khác vẫn có tác dụng nếu class đã gắn.
- Nhiều tags có thể cùng tồn tại trên một test; `includeTags` thường chọn nếu thỏa tag expression.
- Tag **không tự tạo test suite**, không thay đổi classpath và không làm test chạy nếu JUnit engine không tìm thấy test.
- Nên đặt tên đơn giản, ổn định như `fast`, `slow`, `smoke`, `integration`. Không dùng khoảng trắng, dấu phẩy, dấu ngoặc hoặc các ký tự reserved của JUnit tag syntax.

### 7.1. Dùng Gradle property để lọc tag mà không sửa build

Với **build.gradle gốc ở mục 3**, các lệnh dưới đây **chạy được ngay**:

```bash
./gradlew test -PtestTags=fast --console=plain
./gradlew test -PtestTags=slow --console=plain
./gradlew test -PtestTags=smoke --console=plain
```

Kết quả dự kiến:

| Lệnh | Test methods được chọn | Số lượng |
| --- | --- | ---: |
| `./gradlew test` | Cả 5 tests | 5 |
| `-PtestTags=fast` | `CalculatorTest.addsNumbers`, `TextTest.uppercasesText` | 2 |
| `-PtestTags=slow` | `CalculatorTest.subtractsNumbers` | 1 |
| `-PtestTags=smoke` | `CalculatorTest.rejectsZeroDivisor` | 1 |
| `-PtestTags=unknown` | Không có test gắn tag `unknown` | 0 |

**Lưu ý với hàng cuối:** một JUnit Platform tag filter không match có thể dẫn đến test task có 0 tests mà không nhất thiết sinh đúng lỗi `No tests found for given includes` của Gradle TestFilter. Vì vậy CI cần đo **số tests thực thi** qua XML/report và policy, không chỉ dựa vào exit code khi lọc theo tag.

Dòng `-PtestTags=fast` **không phải flag Gradle mặc định cho tags**: nó chỉ hoạt động vì build script lab đọc property đó và gọi `includeTags requestedTags`.

### 7.2. Lọc JUnit tag cố định bằng useJUnitPlatform

Nếu toàn bộ task `test` phải chỉ chạy `fast` theo một policy cố định, **thay phần cấu hình test của lab** bằng:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'fast'
        excludeTags 'slow'
    }
}
```

Với tags trong lab, kết quả là 2 tests fast, vì không có test vừa mang fast vừa mang slow. Nếu một test có cả fast và slow, `excludeTags 'slow'` loại test đó. `includeTags` và `excludeTags` là **framework filter**, không phải Gradle method-name filters.

Có thể dùng cùng một cấu hình cho nhiều Test tasks:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform {
        includeTags 'smoke'
    }
}
```

Nhưng cách này áp dụng cho **tất cả `Test` tasks**, kể cả `integrationTest`, nếu build có chúng. Chỉ dùng khi thực sự muốn quy tắc chung; trong build nhiều suites, cấu hình từng task sẽ dễ hiểu hơn.

### 7.3. Tag expressions: AND, OR, NOT

JUnit Platform hỗ trợ tag expressions, ví dụ:

- `fast`: có tag `fast`.
- `fast | smoke`: có `fast` **hoặc** `smoke`.
- `fast & !slow`: có `fast` **và không có** `slow`.
- `(fast | smoke) & !flaky`: thuộc fast hoặc smoke, nhưng không thuộc flaky.

Ví dụ **thay thế một filter tag**:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags '(fast | smoke) & !flaky'
    }
}
```

Với lab, không có tag `flaky`, nên expression này chọn **3 tests**: hai fast và một smoke. Dấu `|`, `&`, `!` là toán tử của **JUnit Platform tag expressions**, không phải Java regex hay shell pipeline. Trong CLI khi truyền qua property, luôn đặt expression có khoảng trắng/ký tự đặc biệt vào dấu nháy:

```bash
./gradlew test '-PtestTags=(fast | smoke) & !flaky'
```

Lệnh chỉ có ý nghĩa với phần Gradle property handling trong lab. Đừng viết `--tests '@fast'` để thay thế: `--tests` không nhận cú pháp JUnit tags.

### 7.4. Phân biệt tags với @Disabled

`@Tag("slow")` không đánh dấu test là disabled; nó chỉ phân loại. Một test `@Disabled` sẽ **không chạy** ngay cả khi filter tên/tag chọn nó. Nếu muốn tạm thời bỏ một test lỗi, cần lý do và thời hạn xử lý; không trộn việc bỏ qua test với chia nhóm fast/slow.

Một `@Tag("flaky")` có thể giúp CI tạo nhóm chẩn đoán riêng, nhưng không nên tự động loại bỏ mọi flaky tests khỏi pipeline mặc định mà không có chính sách, vì điều đó che lỗi sản phẩm.

## 8. Kết hợp class, method và tag: phép giao thực tế

Khi chỉ dùng một bộ test `test` với hai loại lọc:

1. Gradle `TestFilter` xem **tên lớp/phương thức**.
2. JUnit Platform xem **tags/engines** trong tập tests có thể khám phá.

Những test **thỏa điều kiện lựa chọn cuối cùng** mới được thực thi. Ví dụ với build lab gốc:

| Câu lệnh | Bộ test cuối cùng | Vì sao |
| --- | --- | --- |
| `./gradlew test --tests example.CalculatorTest` | 4 methods trong CalculatorTest | Chọn một class, không có tag restriction. |
| `./gradlew test --tests example.CalculatorTest -PtestTags=fast` | Chỉ `addsNumbers` | Class chọn 4 methods, tag fast còn 1. |
| `./gradlew test --tests example.TextTest -PtestTags=fast` | Chỉ `uppercasesText` | TextTest có class tag fast. |
| `./gradlew test --tests example.CalculatorTest.subtractsNumbers -PtestTags=fast` | Không có test | Method tag slow, không phải fast. |
| `./gradlew test --tests '*Test' -PtestTags=smoke` | Chỉ `rejectsZeroDivisor` | Name pattern gồm cả classes, tag smoke còn 1. |
| `./gradlew test -PtestTags='fast | smoke'` | 3 tests | Hai fast và một smoke; trong lab tag expression hợp lệ. |

Một số tình huống filter quá hẹp có thể trả lỗi `No tests found for given includes`; một số trường hợp JUnit tag không match có thể cho 0 test. **Đừng phụ thuộc vào việc “lệnh đã hoàn thành thành công” để chứng minh có test được thực thi.** Đọc XML/HTML reports và số test cases.

**Cảnh báo về thứ tự:** test selection không phải cơ chế sắp xếp thứ tự chạy. `--tests A --tests B` không cam kết A chạy trước B; JUnit có chiến lược sắp xếp riêng và Gradle có thể chạy forks song song. Nếu test phụ thuộc thứ tự, cần sửa thiết kế test để độc lập hoặc dùng cơ chế order của framework có chủ đích.

## 9. Dry run: xem test được chọn mà không thực thi

Gradle có hai loại dry-run rất dễ nhầm.

### 9.1. --dry-run: mô phỏng task graph

```bash
./gradlew test --dry-run --console=plain
```

Cờ `--dry-run` (hay `-m`) **không chạy task actions**; nó cho biết những tasks nào có trong graph. Bạn có thể thấy `compileTestJava`, `testClasses`, `test` dưới dạng các task được liệt kê hoặc `SKIPPED`. Nó **không chạy JUnit để khám phá chính xác danh sách test methods**.

### 9.2. --test-dry-run: mô phỏng thực thi test cases

```bash
./gradlew test --test-dry-run \
  --tests example.CalculatorTest \
  --console=plain
```

Cờ `--test-dry-run` của Gradle **để Test task khám phá những tests được chọn**, nhưng **không gọi code của các test methods**; nó vẫn có thể sinh test results/reports để bạn kiểm tra selection. Nó phù hợp để xác nhận filter mà không chạy integration workflow tốn tài nguyên.

Ví dụ kiểm chứng lựa chọn fast tags (trong lab):

```bash
./gradlew test --test-dry-run \
  '-PtestTags=fast' \
  --console=plain
```

Kỳ vọng các report/console liên quan cho thấy **hai test names**. Lưu ý kết quả được mô phỏng trong test-dry-run **không phải bằng chứng tests PASS ngoài đời thực**; đừng đưa report dry-run vào CI release gate như kết quả kiểm thử đã thực thi.

**Khi cần kiểm tra các filters và coverage thực tế:** dùng `--test-dry-run` cho preview, sau đó bỏ flag và chạy test thật.

### 9.3. --rerun-tasks và UP-TO-DATE

Một `Test` task có thể `UP-TO-DATE` nếu Gradle thấy inputs/outputs không đổi, nên không in lại events của test trong lần chạy tiếp theo. Nếu bạn cần tái hiện selection trong lúc debug:

```bash
./gradlew test --rerun-tasks \
  --tests example.CalculatorTest.addsNumbers \
  --console=plain
```

`--rerun-tasks` buộc chạy lại các tasks thay vì dùng trạng thái up-to-date, **không thay đổi filter**. Nó tốn thời gian hơn, không cần tự động thêm vào mọi build CI.

## 10. Bộ kiểm thử (test suite) khác lọc tên test ra sao?

Trong Gradle, **JUnit tests trong `src/test/java`** thường được chạy bởi task `test`. Nhưng integration tests có thể cần database, container, test fixture, thời gian và runtime dependencies khác. Khi đó nên tạo **bộ kiểm thử riêng**.

**Gradle JVM Test Suite plugin** có DSL `testing { suites { ... } }` mô hình hóa:

- **Test suite**: nhóm tests có nguồn, dependencies, framework.
- **Target**: một cách chạy suite. Mặc định một suite có một target dẫn tới một `Test` task.
- **Test task**: công việc thực thi trong Gradle, có thể được lọc bằng `--tests` hoặc `filter` và JUnit tags.

Với Java plugin, `jvm-test-suite` được áp dụng cùng Java plugin ở các bản Gradle hiện hành. Suite mặc định tên `test`, source set `test`, task `test`. Bạn có thể khai báo suite mới `integrationTest`; suite đó có source set riêng, configurations riêng và Test task tương ứng.

**Không nhầm:** thêm một class tên `IntegrationTest` vào `src/test/java` **không tự tạo** suite `integrationTest`. Nó vẫn thuộc bộ `test` cho tới khi bạn thiết kế source set/suite riêng.

### 10.1. Vì sao không chỉ dùng @Tag("integration")?

Đối với dự án nhỏ, `@Tag("integration")` trên các tests nằm trong `src/test/java` có thể đủ để chia nhóm thực thi. Nhưng chúng vẫn **dùng chung test source set, compile classpath và runtime classpath**.

Một suite `integrationTest` riêng phù hợp hơn nếu:

1. Cần database driver, container library, environment variables khác.
2. Có lịch chạy riêng (unit test ở mọi commit, integration tests sau merge).
3. Cần timeout, memory, JVM launcher, fork hoặc report riêng.
4. Không muốn unit test classpath kéo toàn bộ integration dependencies.
5. Muốn định nghĩa source roots như `src/integrationTest/java` và `src/integrationTest/resources`.

Lựa chọn giữa tag và suite phụ thuộc nhu cầu **tách môi trường/dependencies**, không chỉ số lượng tests.

## 11. Lab mở rộng: tạo suite integrationTest có task riêng

Đây là **phương án thay thế file build.gradle** của lab mục 3, kết hợp với thêm **một source file**. Giữ nguyên các file `Calculator.java`, `CalculatorTest.java`, `TextTest.java` đã tạo. Không để đồng thời hai build.gradle.

### 11.1. File build.gradle cho phiên bản có suites

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

testing {
    suites {
        test {
            // Suite mặc định cần chỉ định framework.
            useJUnitJupiter('5.11.4')
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter('5.11.4')

            dependencies {
                // Suite mới cần khai báo sử dụng mã production.
                implementation project()
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter tasks.named('test')
                        testLogging {
                            events 'passed', 'failed', 'skipped'
                        }
                    }
                }
            }
        }
    }
}

tasks.named('test', Test) {
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}

tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
```

**Giải thích quan trọng:**

1. `testing.suites.test` là suite mặc định của Java plugin; `useJUnitJupiter('5.11.4')` khai báo framework và Gradle tự thêm framework libraries phù hợp cho suite theo DSL. Đây là điểm khác với `tasks.named('test', Test) { useJUnitPlatform() }`, vốn chỉ chọn runner mà không tự thêm dependencies.
2. `integrationTest(JvmTestSuite)` tạo **suite mới**, source set `integrationTest` và Test task mặc định `integrationTest`. Source root convention là `src/integrationTest/java`, resources root là `src/integrationTest/resources`.
3. `dependencies { implementation project() }` **nằm trong block của suite**; nó cho integration tests truy cập output và dependencies của project production. Suite ngoài `test` không tự kế thừa main production outputs như built-in suite.
4. `shouldRunAfter tasks.named('test')` diễn đạt **thứ tự ưu tiên nếu hai tasks cùng trong graph**; không tự tạo dependency task `test`.
5. `check.dependsOn testing.suites.integrationTest` đưa bộ integration tests vào lifecycle `check`. Mặc định không nên suy luận rằng khai báo suite đã tự gắn nó vào `check`.
6. Khi chạy chỉ `./gradlew integrationTest`, Gradle có thể compile main/integration sources cần thiết, nhưng không nhất thiết phải chạy `test` trước chỉ vì có `shouldRunAfter`.
7. File này sử dụng suite DSL tự thêm framework dependencies; **không** lặp thủ công `testImplementation platform(...)` của lab gốc trừ khi có chủ đích quản lý thêm dependency versions.

### 11.2. File src/integrationTest/java/example/CalculatorIntegrationTest.java

Tạo folder/source mới:

```java
package example;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("integration")
class CalculatorIntegrationTest {

    @Test
    void addsThroughProductionCode() {
        assertEquals(12, Calculator.add(5, 7));
    }
}
```

Có **1 test trong suite integrationTest**. Nó import production class `Calculator`, chứng minh vì sao cần `implementation project()` của suite. JUnit tag `integration` giúp bạn có thể thêm lọc theo tag **bên trong** suite nếu muốn; nó không phải lý do task `integrationTest` tồn tại.

### 11.3. Chạy từng suite

```bash
./gradlew test --console=plain
./gradlew integrationTest --console=plain
./gradlew test integrationTest --console=plain
./gradlew check --console=plain
```

Trong phiên bản suite:

| Lệnh | Kết quả mong đợi |
| --- | --- |
| `test` | 5 unit tests, không tự chứa `CalculatorIntegrationTest`. |
| `integrationTest` | 1 integration test. |
| `test integrationTest` | Cả hai tasks được yêu cầu; tổng 6 test cases khi thực thi thật và không bị cache/skip. |
| `check` | Theo cấu hình, bao gồm unit + integration tests. |

Vì Gradle có incremental/up-to-date behavior, chạy lần lượt bốn lệnh trong cùng project **không đảm bảo cả bốn lần đều in lại events**. Nếu cần một lần kiểm chứng số test đã thực thi, chạy `./gradlew clean check` và đọc reports của cả hai tasks.

### 11.4. Lọc method chỉ trong suite integrationTest

```bash
./gradlew integrationTest \
  --tests example.CalculatorIntegrationTest.addsThroughProductionCode \
  --console=plain
```

Câu lệnh này chọn đúng một method **trong `integrationTest` task**, không chạy method cùng tên ở `test` nếu có. Khi có nhiều suite, hãy luôn viết task đích rõ ràng. Chạy:

```bash
./gradlew test \
  --tests example.CalculatorIntegrationTest.addsThroughProductionCode
```

sẽ **không tìm thấy class đó** trong `test` suite của lab vì source của nó nằm ở `src/integrationTest/java`. Đây là một lỗi chọn **nhầm task**, không phải lỗi JUnit `@Test`.

### 11.5. Lọc tag bên trong suite integrationTest

Trong phiên bản suite, nếu muốn chỉ chọn tag `integration` ở task đó, **bổ sung**:

```groovy
tasks.named('integrationTest', Test) {
    useJUnitPlatform {
        includeTags 'integration'
    }
}
```

Đoạn này áp dụng cho **integrationTest task**, không tự áp dụng lên unit `test`. `useJUnitJupiter()` ở suite đã cung cấp framework và dependencies; ở đây `useJUnitPlatform { includeTags ... }` chỉ tinh chỉnh framework selection tại task.

Nếu integration suite có hai classes (một gắn `integration`, một không tag), chỉ class có tag phù hợp sẽ được chọn sau khi bổ sung filter. Nhưng nếu mục tiêu là **chạy toàn bộ integration suite**, không cần tag filter: chọn task `integrationTest` đã đủ.

### 11.6. Task suites có báo cáo riêng

Sau `./gradlew clean check`, HTML và XML thông thường có:

```text
build/reports/tests/test/index.html
build/test-results/test/
build/reports/tests/integrationTest/index.html
build/test-results/integrationTest/
```

Bằng việc lưu hai reports trong CI, nhóm có thể thấy unit tests và integration tests độc lập. Không gộp kết quả từ hai bộ một cách làm mất dấu suite nào bị fail.

## 12. JVM Test Suite targets: cùng nguồn nhưng cách chạy khác

Một **suite target** không phải suite mới. Nó có thể tái sử dụng nguồn và dependencies của suite, nhưng tạo một Test task khác để chạy lại tests với JVM, system properties hoặc filters khác nhau.

Ví dụ **mở rộng** cho phiên bản suite ở mục 11 — thêm một target `smokeTest` cho suite `test`:

```groovy
testing {
    suites {
        test {
            targets {
                register('smokeTest') {
                    testTask.configure {
                        useJUnitPlatform {
                            includeTags 'smoke'
                        }
                    }
                }
            }
        }
    }
}
```

Đây là **đoạn mở rộng** có thể thêm vào `build.gradle` phiên bản suite để học API targets; `smokeTest` **không** thêm source set mới. Test task target này chia sẻ nguồn/tests của suite `test`, nhưng chỉ chọn `@Tag("smoke")`. Với lab, `./gradlew smokeTest` dự kiến chạy **1 method** `rejectsZeroDivisor`.

**Chú ý về CI:** nếu lifecycle `check` đã chạy toàn bộ `test`, thêm một target smoke và đồng thời gắn vào `check` có thể khiến một số tests được chạy **lặp lại** trong hai tasks. Cần thiết kế mục đích (quick smoke gate vs full suite) và tránh tự động chạy trùng nếu không cần.

## 13. Source set thủ công và custom Test task: một lựa chọn khác

Có build không dùng JVM Test Suite DSL mà tự tạo `sourceSets.integrationTest`, các configurations và `tasks.register('integrationTest', Test)`. Cách đó vẫn hợp lệ khi bạn cần kiểm soát thấp hơn, nhưng **source set một mình không tự tạo Test task**.

Ví dụ sơ đồ tối giản:

```groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
```

**Đây là fragment khái niệm, không phải build.gradle hoàn chỉnh:** nó chưa khai báo JUnit API/engine/launcher vào configurations của `integrationTest`, chưa nối main implementation/runtime dependencies và lifecycle. Khi dùng thực tế, cần bổ sung những cấu hình đó hoặc chuyển sang JVM Test Suite DSL ở mục 11.

**Đặc biệt với Gradle 9:** đừng giả định mọi custom `Test` task tự được nối tới `test` source set như các convention cũ. Nếu tự tạo task, phải khai báo `testClassesDirs` và `classpath` rõ ràng. JVM Test Suite giảm nguy cơ quên những bước này.

## 14. Lọc theo tên khác với lọc theo framework

Gradle Test task có thể chạy nhiều framework, mỗi framework có cách nhóm tests riêng. Đừng dùng cú pháp JUnit Platform tags cho runner khác mà mong nó tự tương thích.

### 14.1. JUnit Jupiter và Platform

- `@Tag("fast")` / `@Tag("integration")` gắn ở class/method.
- `useJUnitPlatform { includeTags 'fast'; excludeTags 'slow' }` chọn nhóm.
- `includeEngines 'junit-jupiter'` hoặc `excludeEngines 'junit-vintage'` dùng **engine IDs**, không phải tag names.
- `--tests` vẫn dùng để lọc tên và không biết cấu trúc JUnit tags.

Ví dụ lọc engine (chỉ khi runtime có nhiều engines):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-jupiter'
    }
}
```

Đoạn này là **phương án thay thế/tinh chỉnh cấu hình runner**, không cần cho lab vì chỉ có Jupiter engine. `includeEngines` chọn engine `junit-jupiter`, không có nghĩa chọn tag `jupiter`.

### 14.2. JUnit 4 Categories

Với JUnit 4 cổ điển, grouping dùng `@Category` và API Gradle:

```groovy
tasks.named('test', Test) {
    useJUnit {
        includeCategories 'com.example.FastTests'
        excludeCategories 'com.example.SlowTests'
    }
}
```

Đây là **ví dụ riêng cho JUnit 4 runner**, không dán vào lab JUnit Jupiter. Cần khai báo `junit:junit:4.13.2` và các category interfaces/classes thực tế trong project. JUnit 4 Categories **khác** JUnit Jupiter `@Tag`.

Nếu muốn chạy test JUnit 4 qua JUnit Platform, cần Vintage engine tương ứng; không suy luận Gradle tự nhận mọi @Category thành Jupiter tags có cùng tên.

### 14.3. TestNG Groups

Với TestNG, group được khai báo qua `@Test(groups = {"smoke"})`, và Gradle dùng:

```groovy
tasks.named('test', Test) {
    useTestNG {
        includeGroups 'smoke'
        excludeGroups 'slow'
    }
}
```

Đây là **mẫu độc lập** cho TestNG; cần dependency `org.testng:testng` với phiên bản hợp lệ và test source viết cho TestNG. `useTestNG` không dùng JUnit Jupiter `@Tag` hoặc `useJUnitPlatform`.

### 14.4. Parameterized, nested, dynamic tests

- Với `@ParameterizedTest`, một Java method có thể phát sinh nhiều invocations có display names khác nhau; `--tests` có thể cần wildcard thích hợp hoặc syntax invocation theo Gradle/JUnit version.
- Với `@Nested`, tên class thường có nested class identifier (`$` trong JVM binary name) và report hierarchy; tránh dự đoán chính xác bằng mắt, nên lấy tên thực tế từ reports khi lọc.
- Với `@DisplayName("Tên hiển thị")`, display name không nhất thiết trùng tên Java method dùng trong `--tests`; Gradle hỗ trợ một số dynamic display patterns tùy engine.
- Với `@TestFactory` và dynamic tests, method factory tạo cases lúc chạy; filtering chi tiết có những giới hạn theo engine và Gradle version. Khi cần chạy ổn định một subset, ưu tiên lọc class/factory method hoặc tag thích hợp.

Ví dụ syntax Gradle document có `--tests '*ParameterizedTest.*[2]'` để chọn invocation thứ hai của parameterized test theo tên được report; đây là **mẫu theo naming của test framework**, không phải chỉ số Java array hay regex chung cho mọi test framework.

## 15. Các bẫy khi tối ưu tốc độ test

### 15.1. Chỉ chạy test mới thay đổi không thay thế regression suite

Khi dev, `--tests example.CalculatorTest.addsNumbers` giúp lặp nhanh. Nhưng thay đổi production code có thể ảnh hưởng các tests khác, nhất là integration tests. CI release cần một điểm chạy **full suite** hoặc kế hoạch test selection có cơ chế xác minh đáng tin; không đánh giá toàn ứng dụng từ một method PASS.

### 15.2. include/exclude theo file class khác filter theo tên test

Gradle Test task có API `include '**/*Test.class'` / `exclude '**/Legacy*.class'` dựa vào **compiled test class file paths**; đây là legacy test inclusion/exclusion. Gradle docs khuyên dùng `TestFilter` cho chọn test names, vì nó làm việc cả ở mức method. Đừng nhầm:

```groovy
tasks.named('test', Test) {
    // Lọc file class được đưa vào test scan:
    include '**/CalculatorTest.class'
}
```

với:

```groovy
tasks.named('test', Test) {
    // Lọc test methods theo tên:
    filter {
        includeTestsMatching 'example.CalculatorTest.addsNumbers'
    }
}
```

**Hai đoạn là alternative configurations.** Với JUnit Platform, `scanForTestClasses` không điều khiển khám phá test theo cách JUnit 3/4 cũ; Gradle chỉ dùng include/exclude patterns của task và engine sẽ đảm nhận discovery. Dùng filter đúng mục đích và kiểm tra bằng test report.

### 15.3. @Disabled, -x test và --tests là ba hành vi khác nhau

| Cơ chế | Tác động |
| --- | --- |
| `@Disabled` | JUnit bỏ qua test class/method cụ thể khi framework khám phá. |
| `--tests ...` | Chọn một subset theo tên bên trong task `Test`. |
| `-x test` / `--exclude-task test` | Bỏ **cả Gradle task test** khỏi graph được thực thi. |
| `--test-dry-run` | Mô phỏng test execution để xem selection nhưng không chạy test methods. |
| `--fail-fast` | Dừng phần còn lại của một test task sớm sau failure; không phải test filter. |

Ví dụ:

```bash
./gradlew build -x test
```

Câu lệnh này không phải “chạy chỉ test nhanh”, mà là **bỏ task test** của graph đã chọn. Nếu build còn `integrationTest` task khác, `-x test` không tự tắt task ấy nếu graph vẫn yêu cầu nó.

### 15.4. Chọn pattern không phải kiểm soát thứ tự/parallelism

TestFilter chỉ chọn tên. `maxParallelForks`, `forkEvery`, JUnit execution mode, resource locks và test isolation kiểm soát những mặt khác của test execution. Dùng filter để kiểm soát độ phủ và chạy nhanh subset, không dùng để giải quyết race condition hoặc ép thứ tự.

## 16. Kiểm tra coverage và báo cáo sau khi lọc

Khi dùng một subset, test reports phải phản ánh **những tests đã được chọn**, không tự động đại diện cho toàn bộ tests source.

Một quy trình kiểm tra:

1. Chạy `./gradlew clean test --tests example.CalculatorTest.addsNumbers`.
2. Xem `build/reports/tests/test/index.html` hoặc XML dưới `build/test-results/test/`.
3. Kiểm tra đúng class/method được report và tổng số tests thực thi.
4. Chạy lại `./gradlew clean test` để kiểm tra 5 tests của lab.
5. Nếu có suite `integrationTest`, chạy `./gradlew integrationTest` và xem reports riêng.
6. Không coi `--test-dry-run` reports là bằng chứng test logic đã pass.
7. Trong CI, có thể dùng XML parser/CI test analytics để enforce minimum test count khi lọc bằng tag; chọn logic sao cho không vô tình cho phép 0 tests.

Với HTML reports, các tên hiển thị và hierarchy có thể khác nếu dùng `@DisplayName` hoặc dynamic tests. XML ở `build/test-results/<task-name>/` là đầu vào tốt cho công cụ CI, nhưng vẫn cần phân biệt source set/task tương ứng.

## 17. Troubleshooting: lọc rồi không thấy test nào chạy

| Triệu chứng | Nguyên nhân có thể | Việc kiểm tra |
| --- | --- | --- |
| `No tests found for given includes` | Typo package/class/method, filter name không match, hoặc đã exclude. | Dùng fully qualified name, xem `filter` trong task, `--test-dry-run`. |
| `--tests fast` không chạy tag fast | `--tests` là lọc tên, không phải JUnit tag filter. | Dùng `@Tag` và `useJUnitPlatform.includeTags`, hoặc project property lab. |
| `-PtestTags=fast` không có tác dụng trong project khác | Project khác không có Gradle script đọc `testTags`. | Cấu hình `useJUnitPlatform` đọc project property, không coi -P là built-in tag filter. |
| Test nằm trong `src/integrationTest/java` nhưng gọi `test` | Chọn nhầm suite/task. | Chạy `integrationTest` và kiểm tra source set của suite. |
| `--tests example.FooTest` vẫn chạy nhiều tests | Đó là **class selection**, chạy mọi methods phù hợp. | Thêm `.methodName` hoặc wildcard chính xác. |
| Chạy multiple `--tests` nhưng chỉ một test chạy | Kết hợp filters khác, JUnit tags, disabled tests hoặc không có method thứ hai. | Xem build script, reports và test dry-run. |
| Tag filter tạo 0 tests nhưng build không báo lỗi tương ứng | Framework filter khác TestFilter; không phải lúc nào cùng fail mode. | Enforce số tests trong CI; xem tag value, @Tag inheritance, JUnit runner. |
| `test SKIPPED/NO-SOURCE` | Test source không tồn tại, sai folder, source set không compile, hoặc task không có compiled classes. | Xem `src/test/java`, `compileTestJava`, testClassesDirs. |
| `test UP-TO-DATE` | Inputs/outputs không đổi nên Gradle không chạy lại. | Dùng `--rerun-tasks` khi cần chẩn đoán, không kết luận filter sai. |
| `package org.junit.jupiter.api does not exist` | Thiếu Jupiter API trên test compile classpath. | `testImplementation` và `testCompileClasspath`. |
| Test process không tìm thấy engine/launcher | Thiếu Jupiter engine hoặc Platform launcher ở test runtime. | `testRuntimeOnly`, `testRuntimeClasspath`. |
| Custom Test task không chạy tests ở Gradle 9+ | Chưa nối `testClassesDirs`, `classpath`. | Dùng JVM Test Suite hoặc cấu hình custom Test task đầy đủ. |
| `includeTags 'fast'` nhưng chạy slow | Test có cả fast và slow tags do class-level tag inheritance hoặc cấu hình task khác. | Kiểm tra tags ở class/method, `excludeTags 'slow'` nếu đúng policy. |
| `--tests '*SomeTest'` bị shell xử lý sai | Không quote pattern trong shell có expansion. | Dùng `'...*...'` hoặc quote tương ứng shell. |
| JUnit4 @Category và Jupiter @Tag bị trộn | Khác runner và cơ chế grouping. | Chọn JUnit Platform/Jupiter hoặc useJUnit/TestNG đúng framework. |
| Integration suite thiếu production class | Suite mới không tự nhận dependencies/main output. | `dependencies { implementation project() }` bên trong suite. |
| `check` chỉ chạy unit tests | Integration suite chưa được gắn vào lifecycle. | `tasks.named('check') { dependsOn testing.suites.integrationTest }`. |
| Báo cáo có 0 tests sau `--test-dry-run` | Filter/tags quá hẹp hoặc test không được khám phá. | Xác nhận task/source set/annotations/engine, bỏ từng filter để khoanh vùng. |

### 17.1. Quy trình 7 bước chẩn đoán

1. **Xác định chính xác task path**: `:app:test`, `:app:integrationTest` hay root `test`.
2. **Đảm bảo source được biên dịch**: `compileTestJava`, `compileIntegrationTestJava` nếu có suite; đọc status `NO-SOURCE`.
3. **Kiểm tra JUnit runner và dependencies**: `useJUnitPlatform()`, Jupiter API, engine, launcher hoặc `useJUnitJupiter()` suite DSL.
4. **Liệt kê mọi điều kiện lọc**: `--tests`, `filter { ... }`, `includeTags/excludeTags`, `includeEngines`, source class include/exclude và `@Disabled`.
5. **Chạy preview**: `--test-dry-run` trên task với pattern rõ, kiểm tra reports/console.
6. **Bỏ dần các filter** theo một giả thuyết để tìm điều kiện loại test; tránh sửa nhiều chỗ cùng lúc.
7. **Chạy thực và xem report**: test counts, skipped/failures, HTML/XML, test task outcome. Không kết thúc ở “BUILD SUCCESSFUL” nếu mục tiêu là bảo đảm đã chạy một bộ test tối thiểu.

## 18. Bài tập tự luyện

**Bài 1 — Class filter:** Từ lab mục 3, chạy `./gradlew test --tests example.CalculatorTest`. Có bao nhiêu tests? **Đáp án:** 4.

**Bài 2 — Method filter:** Chạy `./gradlew test --tests example.CalculatorTest.rejectsZeroDivisor`. Class/method nào được thực thi? **Đáp án:** chỉ `rejectsZeroDivisor`, một test.

**Bài 3 — Multiple filters:** Dùng hai `--tests` để chọn `CalculatorTest.addsNumbers` và `TextTest.uppercasesText`, sau đó xem report. **Kỳ vọng:** 2 tests được chọn.

**Bài 4 — Tag fast:** Chạy `./gradlew test -PtestTags=fast`. Vì sao `TextTest.uppercasesText` thuộc fast dù method không có `@Tag`? **Đáp án:** tag nằm ở class.

**Bài 5 — Tag slow:** Chạy `./gradlew test -PtestTags=slow` và đếm. **Đáp án:** 1 test `subtractsNumbers`.

**Bài 6 — Phép giao filters:** Chạy `./gradlew test --tests example.CalculatorTest -PtestTags=fast`. Vì sao chỉ 1 test? **Đáp án:** có 4 test trong class nhưng chỉ `addsNumbers` có tag fast.

**Bài 7 — Không match:** Thử `--tests example.CalculatorTest.noSuchMethod`. Giải thích `failOnNoMatchingTests` và tại sao giữ default true thường phù hợp CI. Sửa typo thay vì tắt guard.

**Bài 8 — Tag expression:** Đổi property sang `'-PtestTags=fast | smoke'`. Kỳ vọng bao nhiêu tests? **Đáp án:** 3 (2 fast + 1 smoke). Bổ sung `!slow` nếu cần chính sách loại nhóm slow.

**Bài 9 — Dry-run:** So sánh `--dry-run` với `--test-dry-run`. Cái nào chỉ liệt kê Gradle task graph, cái nào mô phỏng test case discovery?

**Bài 10 — Tạo suite:** Áp dụng phiên bản build.gradle mục 11, thêm `CalculatorIntegrationTest`. Vì sao `./gradlew integrationTest` chạy một test nhưng `./gradlew test` vẫn chỉ gồm 5 unit tests?

**Bài 11 — CI lifecycle:** Nếu muốn full suite chạy trong `check`, tại sao phải có `dependsOn testing.suites.integrationTest`? `shouldRunAfter` có tự thêm task vào graph không?

**Bài 12 — Custom target:** Thêm `smokeTest` target vào built-in test suite. Nó có tạo một SourceSet mới không? **Đáp án:** không, cùng sources/dependencies của suite với Test task khác.

**Bài 13 — Frameworks:** JUnit Jupiter `@Tag` tương ứng khái niệm nào trong TestNG và JUnit 4? Chúng có dùng cùng API Gradle không? **Đáp án:** TestNG groups, JUnit4 categories; runner options khác nhau.

**Bài 14 — Reports:** Thực thi 1 method bằng `--tests`, sau đó chạy đủ 5 unit tests. Vì sao test counts trong XML thay đổi nhưng số phương thức trong code không đổi?

### Tự kiểm tra nhanh

1. **`--tests` lọc theo tag không?** Không, lọc tên lớp/method.
2. **Pattern `*Test` là Java regex?** Không, wildcard của TestFilter.
3. **Tên `CalculatorTest` có cần package để được match không?** Không bắt buộc ở Gradle hiện đại, nhưng FQCN rõ ràng hơn.
4. **Hai `--tests` tương ứng hai patterns phải đồng thời match?** Không, chúng là các inclusions.
5. **Tag có đặt trên class được không?** Có; Jupiter methods nhận tag lớp.
6. **Không khai báo `includeTags` thì untagged tests có chạy không?** Có nếu không có filter khác loại chúng.
7. **`-PtestTags=fast` có phải CLI option built-in của Gradle?** Không, do lab định nghĩa project property.
8. **`includeTags` khác `includeTestsMatching` thế nào?** Framework tag so với Gradle name pattern.
9. **`--dry-run` có chạy JUnit discovery không?** Không, chỉ mô phỏng task actions.
10. **`--test-dry-run` có thật sự chạy assertion không?** Không.
11. **`integrationTest` là tag hay task?** Trong JVM Test Suite lab là task của suite riêng.
12. **JUnit test suite mới có tự thấy production output không?** Ngoài built-in suite, cần khai báo `implementation project()` theo convention.
13. **`check` có tự chạy mọi suite mới không?** Không, cần gắn dependency nếu muốn.
14. **Custom `Test` task có cần testClassesDirs và classpath không?** Có, nếu tự tạo không dựa trên suite DSL.
15. **CI có thể pass dù tag filter chọn 0 tests không?** Có thể; nên enforce test count.
16. **`@Disabled` có giống `@Tag("slow")` không?** Không.
17. **`--rerun-tasks` có thay filter không?** Không, chỉ yêu cầu tasks chạy lại.
18. **Vì sao lưu XML/HTML reports theo từng task?** Để kiểm tra số lượng và nhóm tests thật sự được chạy.

## 19. Tài liệu chính thức

- **Gradle — Testing in Java & JVM Projects:** filtering với `--tests`, `filter { }`, wildcard patterns, JUnit Platform tags, include/exclude test class patterns, `--test-dry-run`, logging/reports và troubleshooting: https://docs.gradle.org/current/userguide/java_testing.html
- **Gradle — TestFilter API:** `includeTestsMatching`, `excludeTestsMatching`, `includeTest`, `failOnNoMatchingTests`: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/TestFilter.html
- **Gradle — Test task DSL:** `useJUnitPlatform`, `testClassesDirs`, `classpath`, `testLogging`, test dry-run: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- **Gradle — JVM Test Suite Plugin:** `testing.suites`, default `test`, suite `integrationTest`, targets, project dependencies, lifecycle: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- **Gradle — Java Plugin:** test source set, tasks, dependency configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- **Gradle — Command-Line Interface:** `--tests`, `--test-dry-run`, `--dry-run`, `--rerun-tasks`, `-x test`: https://docs.gradle.org/current/userguide/command_line_interface.html
- **JUnit 5.11.4 User Guide:** `@Tag`, class-level inheritance, tag expressions, nested/parameterized tests: https://docs.junit.org/5.11.4/user-guide/
- **JUnit Platform Tags API:** rules đặt tên tag và Boolean expressions: https://docs.junit.org/5.11.4/api/org.junit.platform.commons/org/junit/platform/commons/util/StringUtils.html

**Kết luận:** Khi cần chọn **lớp/phương thức**, dùng Gradle `TestFilter` qua `--tests` hoặc `filter { ... }`. Khi cần nhóm test theo **ý nghĩa**, gắn JUnit `@Tag` rồi dùng `useJUnitPlatform { includeTags/excludeTags }`. Khi cần tách **nguồn, dependencies, môi trường và reports**, tạo **JVM Test Suite** riêng như `integrationTest` rồi chạy đúng task. Có thể kết hợp các tầng lọc, nhưng luôn xác nhận danh sách và số tests qua `--test-dry-run`/reports, và chạy full suite ở điểm kiểm soát CI phù hợp.