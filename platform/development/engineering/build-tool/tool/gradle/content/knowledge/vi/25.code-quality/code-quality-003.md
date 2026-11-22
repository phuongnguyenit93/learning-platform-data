# Cấu hình PMD và SpotBugs theo plugin tương ứng trong Gradle

## 1. Vì sao nên dùng cả PMD và SpotBugs?

Đưa một dự án Java vào CI không chỉ là bảo đảm `compileJava` và `test` thành công. Có những lỗi vẫn biên dịch được và chưa được test bao phủ: nhánh xử lý ngoại lệ rỗng, đoạn debug để lại trong mã nguồn, null dereference, xử lý đồng thời không an toàn hoặc sử dụng API dễ gây lỗi.

**PMD** và **SpotBugs** là hai bộ phân tích tĩnh giúp phát hiện những vấn đề này ở **hai mức biểu diễn khác nhau**:

- **PMD** phân tích **mã nguồn Java** (và một số ngôn ngữ khác khi dùng PMD trực tiếp) theo các rule categories. Trong Gradle Java project, plugin `pmd` tạo các task đọc source files để kiểm tra quy tắc.
- **SpotBugs** phân tích **bytecode Java (.class)** kết hợp thông tin về dependencies. Trong Gradle, plugin `com.github.spotbugs` tạo task chạy sau compilation để kiểm tra những bug patterns có thể bị bỏ sót nếu chỉ xem cú pháp nguồn.

Cả hai có thể tham gia lifecycle task `check` của Gradle. Chúng **bổ sung, không thay thế** unit tests, integration tests, formatter, security scanning và code review. Chúng cũng có false positives, nên nhóm phát triển phải biết cách triage findings thay vì tự động xóa/suppress mọi cảnh báo.

Sau bài học, bạn sẽ:

1. Phân biệt đúng **plugin ID**, **toolVersion** và dữ liệu mà PMD/SpotBugs phân tích.
2. Viết được `build.gradle.kts` cho **Java 17 + PMD + SpotBugs**, có báo cáo HTML/XML và CI gate.
3. Tạo file PMD custom ruleset và SpotBugs exclude filter XML đúng định dạng.
4. Hiểu `pmdMain`/`pmdTest`, `spotbugsMain`/`spotbugsTest`, `check`, compilation dependencies và report paths.
5. Tùy chỉnh PMD rules, priority, toolchain; SpotBugs effort, confidence, filter, memory và external detectors.
6. Gây lỗi có chủ đích ở một sandbox để quan sát report và sửa root cause.
7. Chẩn đoán lỗi plugin resolution, thiếu bytecode/classpath, JDK mismatch, cấu hình reports và CI fail.
8. Áp dụng policy cho multi-project build mà không che mất lỗi mới.

**Điểm dễ nhầm:** `pmd` là **core Gradle plugin**, không cần số version độc lập trong `plugins { }`. SpotBugs dùng **external Gradle plugin** `com.github.spotbugs`, nên cần version đã được chấp thuận và plugin repository phù hợp.

## 2. So sánh hai công cụ trước khi cấu hình

| Khía cạnh | PMD | SpotBugs |
| --- | --- | --- |
| Dữ liệu chính | Java source files/AST, rule engine | Compiled class files/bytecode + classpath |
| Gradle plugin ID | `pmd` — **core plugin** | `com.github.spotbugs` — **third-party plugin** |
| Plugin version | Theo Gradle Wrapper | Pin qua `plugins { id(...) version "..." }`/version catalog |
| Tool version | `pmd.toolVersion` | `spotbugs.toolVersion`, **khác plugin version** |
| Task tự động (Java source sets) | `pmdMain`, `pmdTest` | `spotbugsMain`, `spotbugsTest` |
| Điểm đầu vào | `src/main/java`, `src/test/java` sau khi xét source sets | `build/classes/java/main`, `.../test` hoặc outputs do plugin/source set tạo |
| Khi cần compilation? | Có thể phân tích source; một số rules dùng type resolution/classpath | **Có**: phải có classes được compile |
| Quy tắc | PMD rule categories hoặc custom ruleset XML | Bug patterns/detectors và include/exclude filters |
| Mức lọc findings | `rulesMinimumPriority`, ruleset selection | `reportLevel` (confidence), `effort`, filter files |
| Plugin extension | `pmd { ... }` | `spotbugs { ... }` |
| Tùy chỉnh task | `tasks.withType<Pmd>()` | `tasks.withType<SpotBugsTask>()` |
| Tool-specific dependencies | `pmd`, `pmdAux` | `spotbugs`, `spotbugsPlugins` |
| Báo cáo | PMD XML/HTML/CSV/SARIF tùy Gradle | SpotBugs XML/HTML theo report container |
| Lifecycle | Plugin gắn các PMD tasks vào `check` | Plugin gắn SpotBugs tasks vào `check` khi bật `runOnCheck` |
| Điều không bảo đảm | Không suy ra mọi lỗi runtime/logic | Không phát hiện mọi lỗi logic, chưa chạy test |

**Không đánh đồng “độ nghiêm trọng” của hai tool:** PMD có **priority 1–5**, với **1 là mức ưu tiên cao nhất**. SpotBugs có **confidence/reportLevel** và bug rank/category riêng. Hai thang không tương đương từng con số; không viết một rule chung kiểu “priority >= 3” rồi áp dụng cả hai.

**Không đánh đồng phiên bản:** ví dụ `com.github.spotbugs` plugin `6.5.13` có thể điều khiển **SpotBugs analyzer** phiên bản `4.10.5`. Một con số là bản Gradle integration/plugin, con số kia là engine phân tích bytecode.

## 3. Lựa chọn phiên bản và yêu cầu môi trường

Bài thực hành chọn những phiên bản đã có bản phát hành/tài liệu chính thức:

- **SpotBugs Gradle plugin**: `com.github.spotbugs:6.5.13` (Gradle Plugin Portal, phát hành 12/10/2026).
- **SpotBugs analyzer**: `4.10.5`, có tài liệu SpotBugs và release tương ứng.
- **PMD analyzer**: `7.16.0`, phiên bản được chính tài liệu Gradle dùng làm ví dụ `toolVersion`; không nhất thiết là bản PMD mới nhất tại mọi thời điểm.
- **Java source/toolchain**: JDK 17.
- **Gradle Wrapper**: một Gradle release còn hỗ trợ môi trường JDK 17 và phiên bản SpotBugs plugin đã chọn; **kiểm tra compatibility matrix/release notes** thay vì đoán một version luôn đúng trong tương lai.

Ví dụ cần truy cập:

- **Gradle Plugin Portal** (hoặc plugin mirror phù hợp) để lấy `com.github.spotbugs`.
- **Maven Central** (hoặc dependency mirror đã cấu hình) để lấy PMD/SpotBugs analyzer artifacts và JUnit.
- JDK 17 installation hoặc Gradle toolchain resolver có thể cung cấp JDK phù hợp.

Dùng **Gradle Wrapper** đã commit. Nếu mới tạo một project hoàn toàn trống, dùng một Gradle cài tạm để chạy `gradle wrapper` rồi commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle-wrapper.properties`. Không tự chế tạo file `gradle-wrapper.jar` bằng tên giả.

**Chú ý:** Gradle core plugin `pmd` không cần gọi Plugin Portal. External plugin `com.github.spotbugs` thì cần Gradle plugin resolution; cấu hình `repositories { mavenCentral() }` cho project dependencies không tự thay thế `pluginManagement.repositories`.

## 4. Mô hình task và lifecycle

Khi áp dụng các plugins:

```kotlin
plugins {
    java
    pmd
    id("com.github.spotbugs") version "6.5.13"
}
```

Gradle có thể tạo hoặc gắn task theo source set:

```text
Gradle check
  |
  +-- test
  |
  +-- pmdMain -----------------> đọc source main
  +-- pmdTest -----------------> đọc source test
  |
  +-- spotbugsMain
  |      |
  |      +-- classes/compileJava -> đọc compiled .class main
  |
  +-- spotbugsTest
         |
         +-- testClasses/compileTestJava -> đọc compiled .class test
```

Đây là **sơ đồ khái niệm**, không phải output của `./gradlew tasks`. Task dependency graph có thể thay đổi theo plugin version, source sets và cách task được cấu hình. Dùng `./gradlew check --dry-run` để xem graph thực tế.

### 4.1. Các task cụ thể

| Task | Khi nào có | Ý nghĩa |
| --- | --- | --- |
| `compileJava` | Java plugin | Compile source `main` |
| `compileTestJava` | Java plugin | Compile source `test` |
| `pmdMain` | PMD + Java source set `main` | PMD kiểm tra Java sources của production |
| `pmdTest` | PMD + Java source set `test` | PMD kiểm tra Java test sources |
| `spotbugsMain` | SpotBugs + Java source set `main` | SpotBugs kiểm tra compiled classes của production |
| `spotbugsTest` | SpotBugs + Java source set `test` | SpotBugs kiểm tra compiled test classes |
| `check` | Java lifecycle | Tổng hợp test và code quality tasks theo plugins áp dụng |
| `build` | Base/Java lifecycle | Assemble và check; kéo theo code quality nếu `check` được nối đúng |

**Quan trọng:** `./gradlew test` **không** thay `./gradlew check`. Test task chạy unit tests nhưng thường không tự chạy PMD/SpotBugs. Muốn code quality là gate của CI, gọi `check` hoặc cấu hình rõ những tasks cần chạy.

Nếu dùng **`com.github.spotbugs-base`** thay plugin thông thường, base plugin không tự tạo `spotbugsMain`/`spotbugsTest` như bản full; phải tự đăng ký `SpotBugsTask`. Với Java project bình thường nên dùng `com.github.spotbugs`.

## 5. Demo hoàn chỉnh: Java 17 + PMD + SpotBugs + JUnit

Demo này **có thể dựng và chạy độc lập** sau khi có Wrapper, JDK phù hợp và repositories. Nó cố ý chọn một ruleset PMD nhỏ, để học cách kiểm tra và tạo lỗi có chủ đích mà không bị lẫn với nhiều quy tắc mới chưa được review.

### 5.1. Cây thư mục

```text
java-quality-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── config/
│   ├── pmd/
│   │   └── ruleset.xml
│   └── spotbugs/
│       └── exclude.xml
├── src/
│   ├── main/java/example/quality/Greeting.java
│   └── test/java/example/quality/GreetingTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Không cần tạo thư mục `build/` trước: Gradle tạo compilation outputs và reports khi task chạy. Các file `config/pmd` và `config/spotbugs` ở project directory, không đặt trong `src/main/resources` vì chúng là **cấu hình build-tool**, không phải resource ứng dụng cần đóng gói vào JAR.

### 5.2. `settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "java-quality-lab"
```

`pluginManagement` phải xuất hiện sớm ở settings. Đối với demo đơn giản, project `build.gradle.kts` vẫn khai báo `mavenCentral()` cho các tool/runtime dependencies. Khi tổ chức có mirror/`dependencyResolutionManagement` ở settings, áp dụng policy đã duyệt thay vì thêm duplicate repositories.

### 5.3. Toàn bộ `build.gradle.kts`

```kotlin
import com.github.spotbugs.snom.Confidence
import com.github.spotbugs.snom.Effort
import com.github.spotbugs.snom.SpotBugsTask
import org.gradle.api.plugins.quality.Pmd
import org.gradle.api.tasks.testing.Test

plugins {
    java
    pmd
    id("com.github.spotbugs") version "6.5.13"
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
    // Chỉ để test; không đưa Jupiter vào production classpath.
    testImplementation("org.junit.jupiter:junit-jupiter:5.14.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

// PMD core Gradle plugin -> phân tích Java source.
pmd {
    toolVersion = "7.16.0"
    isConsoleOutput = true
    isIgnoreFailures = false

    // Chỉ chạy custom ruleset của demo, tránh cộng thêm
    // một ruleset mặc định ngoài ý muốn.
    ruleSets = emptyList()
    ruleSetFiles = files("config/pmd/ruleset.xml")

    // PMD priorities: 1 cao nhất, 5 thấp nhất.
    // 5 cho phép báo cáo tất cả priorities.
    rulesMinimumPriority = 5
}

// SpotBugs external Gradle plugin -> phân tích bytecode.
spotbugs {
    toolVersion = "4.10.5"
    ignoreFailures = false
    effort = Effort.DEFAULT
    reportLevel = Confidence.DEFAULT

    // Filter file tồn tại nhưng ban đầu không loại finding nào.
    excludeFilter = file("config/spotbugs/exclude.xml")
    maxHeapSize = "1g"
}

// Báo cáo riêng cho các PMD tasks (main/test).
tasks.withType<Pmd>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

// SpotBugs HTML: đặt output theo tên task để tránh
// spotbugsMain và spotbugsTest ghi đè cùng một file.
tasks.withType<SpotBugsTask>().configureEach {
    reports.create("html") {
        required = true
        outputLocation = layout.buildDirectory.file(
            "reports/spotbugs/${name}.html"
        )
    }
}
```

**Giải thích cấu hình:**

- `java` tạo source sets và `check` lifecycle; `pmd` là **core plugin**; `com.github.spotbugs` là **external plugin**.
- Import `Pmd`, `SpotBugsTask`, `Effort`, `Confidence` để Kotlin DSL nhận đúng task/enum types.
- `pmd.toolVersion` đặt **PMD analyzer** độc lập với version Gradle.
- `spotbugs.toolVersion` đặt **SpotBugs analyzer** độc lập với `com.github.spotbugs` plugin version.
- `ruleSets=emptyList()` chặn PMD tự cộng built-in rulesets không chủ ý; `ruleSetFiles` chỉ tới custom XML.
- `rulesMinimumPriority=5` không có nghĩa “chỉ báo lỗi mức 5”; nó nhận mọi PMD priority đủ ngưỡng.
- `isIgnoreFailures=false`/`ignoreFailures=false` khiến code quality tasks **fail khi có violations đạt điều kiện tool/plugin**, thay vì chỉ phát report rồi báo CI xanh.
- `excludeFilter` là file XML của **SpotBugs**; không thể đưa PMD ruleset vào đó.
- `maxHeapSize` ở SpotBugs là bộ nhớ cho analyzer process, **không** thay Gradle Daemon heap.
- `tasks.withType<...>().configureEach` cấu hình mọi task phù hợp một cách lazy; giữ riêng output cho từng source set.
- `reports.create("html")` là API SpotBugs plugin (khác Gradle PMD reports API). Cấu trúc này dựa vào SpotBugs Gradle plugin 6.x và Gradle API hiện đại; kiểm tra plugin/Gradle compatibility khi nâng version.

### 5.4. PMD custom ruleset `config/pmd/ruleset.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Java Quality Lab"
    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0 https://pmd.github.io/schema/ruleset_2_0_0.xsd">

    <description>
        Hai quy tắc có chủ đích để học cách chạy PMD trong Gradle.
    </description>

    <rule ref="category/java/bestpractices.xml/SystemPrintln"/>
    <rule ref="category/java/errorprone.xml/EmptyCatchBlock"/>
</ruleset>
```

**Ý nghĩa:**

1. `SystemPrintln` phát hiện gọi `System.out.print/println` hoặc `System.err.print/println` trong Java source, nơi nhiều nhóm muốn thay bằng logger.
2. `EmptyCatchBlock` phát hiện một số `catch` body trống, có nguy cơ nuốt exception mà không có giải thích.
3. `ruleSets=emptyList()` trong Gradle khiến **chỉ các rules được chọn trong XML** chạy, thay vì vô tình bao gồm cả một category lớn.
4. Không yêu cầu tất cả PMD rules có chung một priority; mỗi rule có priority riêng trong bộ PMD.
5. Namespace `http://pmd.sourceforge.net/ruleset/2.0.0` và đường schema là format XML chính thức của PMD 7.x.

Đặt file đúng đường dẫn. Nếu XML thiếu `<rule>` hoặc dùng một rule tên không tồn tại, PMD có thể fail ở **giai đoạn đọc ruleset**, không phải trả về “0 findings”.

**Lưu ý học tập:** rule `SystemPrintln` sẽ quét cả `pmdMain` và `pmdTest` nếu áp dụng cùng ruleset cho hai task. Nếu nhóm muốn cho phép output trong test, hãy cấu hình policy theo source set hoặc dùng rulesets khác, đừng vô tình bỏ qua `pmdTest`.

### 5.5. SpotBugs filter `config/spotbugs/exclude.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
</FindBugsFilter>
```

Đây là **filter hợp lệ nhưng rỗng**, nên **không suppress finding nào**. Nó cho phép demo chạy với một filter file rõ ràng và sau này thêm ngoại lệ hẹp sau review. Tên root `FindBugsFilter` là tên được SpotBugs kế thừa từ FindBugs, **không phải gợi ý dùng plugin FindBugs cũ**.

Không đưa PMD ruleset `<ruleset>` vào vị trí này; SpotBugs dùng ngôn ngữ filter XML khác.

### 5.6. Java source `Greeting.java`

`src/main/java/example/quality/Greeting.java`:

```java
package example.quality;

import java.util.Objects;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String input) {
        String safeInput = Objects.requireNonNull(input, "input");
        return "Hello, " + safeInput.trim();
    }
}
```

Không dùng `System.out.println` trong production source, không có `catch` rỗng, và `requireNonNull` làm rõ contract của tham số `input`.

### 5.7. JUnit test source `GreetingTest.java`

`src/test/java/example/quality/GreetingTest.java`:

```java
package example.quality;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void greetsNameWithTrimmedSpaces() {
        assertEquals("Hello, Java 17", Greeting.greet(" Java 17 "));
    }

    @Test
    void rejectsNull() {
        assertThrows(NullPointerException.class, () -> Greeting.greet(null));
    }
}
```

Bài test không in `System.out` nên không vi phạm rule PMD `SystemPrintln` của demo. `assertThrows` kiểm chứng contract `Objects.requireNonNull`.

### 5.8. Chạy bằng Gradle Wrapper

Linux/macOS:

```bash
./gradlew --version
./gradlew tasks --all
./gradlew clean check
./gradlew pmdMain pmdTest spotbugsMain spotbugsTest
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat tasks --all
.\gradlew.bat clean check
.\gradlew.bat pmdMain pmdTest spotbugsMain spotbugsTest
```

**Kết quả kỳ vọng khi dependencies/toolchain được resolve và source như trên:** Java compilation thành công, JUnit 2 tests pass, `pmdMain`/`pmdTest` không phát hiện hai mẫu vi phạm đã chọn, SpotBugs có thể hoàn thành phân tích mà không có findings đạt ngưỡng; Gradle báo `BUILD SUCCESSFUL`. Đây là **kỳ vọng thiết kế**, không phải transcript stdout cố định. Phiên bản tool, Java/Gradle compatibility, XML rules và các checks thực tế mới quyết định kết quả.

Nếu SpotBugs analyzer thấy bug pattern khác trong code hoặc dependency/bytecode, `check` vẫn có thể fail — đó là chức năng của quality gate, không được coi lỗi plugin.

### 5.9. Báo cáo nằm ở đâu?

Sau khi chạy tasks, tìm dưới:

```text
build/
└── reports/
    ├── pmd/
    │   ├── main.html
    │   ├── main.xml
    │   ├── test.html
    │   └── test.xml
    ├── spotbugs/
    │   ├── spotbugsMain.html
    │   └── spotbugsTest.html
    └── tests/
        └── test/index.html
```

**Đường dẫn PMD** là convention phổ biến khi bật HTML/XML; có thể khác theo Gradle version hoặc nếu build đã override `reports.*.outputLocation`. **Đường dẫn SpotBugs HTML** là chính đường đã thiết lập tường minh trong `build.gradle.kts` thông qua `name`. SpotBugs XML report chỉ xuất hiện nếu đã được cấu hình/kích hoạt tương ứng, không được giả định là cùng cấu hình với PMD XML.

Đừng khẳng định có report chỉ vì task `UP-TO-DATE`; report có thể từ lần chạy trước. Dùng `clean check`/`--rerun-tasks` khi cần chứng minh lượt phân tích thật sự được thực thi.

## 6. Thực nghiệm PMD: phát hiện code xấu từ source

Trong **bản sao của project demo**, thêm một method vào `Greeting.java`:

```java
public static void debugLog(String input) {
    System.out.println(input);
}
```

Đây là **đoạn code cố ý vi phạm để quan sát PMD**, không dán nó vào baseline nếu muốn `check` mặc định pass. Rule PMD `category/java/bestpractices.xml/SystemPrintln` thường báo vị trí `System.out.println`. Chạy:

```bash
./gradlew pmdMain --rerun-tasks
```

Với `isIgnoreFailures=false`, task `pmdMain` dự kiến fail khi có violation. Báo cáo PMD XML/HTML nêu class/file và rule; chỉ dựa vào stdout có thể bỏ sót chi tiết. Thông báo Gradle có thể có dạng:

```text
Execution failed for task ':pmdMain'.
PMD found violations ...
```

Đây là **dạng lỗi minh họa**, không phải output đầy đủ của một phiên bản Gradle cụ thể. Khi sửa method để dùng logger phù hợp hoặc xóa debug line, chạy lại `pmdMain`. **Không đặt `ignoreFailures=true` chỉ để báo build xanh.**

### 6.1. Thực nghiệm EmptyCatchBlock

Một đoạn Java có chủ đích:

```java
public static int parseOrZero(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ignored) {
        // Không làm gì: dễ che giấu đầu vào sai.
    }
    return 0;
}
```

PMD rule `EmptyCatchBlock` có chính sách riêng về comment và tên exception variable; một `catch` rỗng **thực sự** như `catch (NumberFormatException ex) { }` dễ minh họa hơn khi muốn chắc chắn trigger. Đừng dùng `ignored` hoặc comment để “qua” rule mà chưa giải thích business behavior. Cách tốt hơn là xử lý exception tường minh hoặc propagate với ngữ nghĩa hợp lệ.

Nếu cố ý fail một test chỉ để xem quality gate, hãy làm trong sandbox/branch riêng, giữ bản baseline để khôi phục; không commit mã ví dụ vi phạm lên production.

## 7. Thực nghiệm SpotBugs: phân tích bytecode và nullness

SpotBugs chạy trên **compiled classes**. Bạn phải compile source trước hoặc để Gradle task dependencies đảm nhiệm compilation. Một ví dụ Java bị nghi ngờ null dereference:

```java
public static int unsafeLength() {
    String value = null;
    return value.length();
}
```

Đây là **đoạn code không an toàn để thử trong sandbox**, không có trong baseline. Compiler Java có thể vẫn biên dịch, nhưng bytecode của method chắc chắn dereference một null reference; SpotBugs thường cảnh báo thuộc nhóm `NP_*` (mã bug cụ thể phụ thuộc analyzer/ruleset).

Chạy:

```bash
./gradlew spotbugsMain --rerun-tasks
```

SpotBugs task sẽ compile/classes trước khi phân tích theo graph được tạo bởi plugin. Báo cáo HTML có thể chỉ rõ **bug pattern, confidence, location và stack/description**. Đừng suy từ một finding rằng ứng dụng chắc chắn lỗi trên mọi runtime path: static analyzers dùng heuristics và có false positives/false negatives. Nhưng **dereference null rõ ràng** là bug thực tế phải sửa, không suppress.

Cách sửa logic tương ứng:

```java
public static int safeLength(String value) {
    return java.util.Objects.requireNonNull(value, "value").length();
}
```

Nó buộc caller cung cấp giá trị hợp lệ. Với đầu vào được phép null, có thể dùng điều kiện `value == null ? 0 : value.length()`; lựa chọn nào đúng phụ thuộc contract thật của method.

### 7.1. Vì sao PMD và SpotBugs có thể báo khác nhau?

- PMD thấy Java source structure và patterns, có thể báo vấn đề ngay cả trước khi có `.class`.
- SpotBugs đọc bytecode, phân tích data flow, nullness, resource handling, concurrency và class relationships.
- Một lỗi `System.out.println` trong test có thể bị PMD báo, trong khi SpotBugs không nhất thiết xem nó là bug.
- Null dereference có thể được SpotBugs phát hiện từ bytecode, trong khi PMD ruleset chỉ có `SystemPrintln` và `EmptyCatchBlock` của demo không liên quan.
- Nếu code được generate/cross-compiled, nguồn và compiled bytecode không trùng 1:1, càng cần xác định source set và report location.

Không xóa một trong hai tool chỉ vì đôi lúc findings chồng nhau. Giữ rules có giá trị và tránh báo trùng không cần thiết bằng policy, không bằng cách tắt tất cả.

## 8. Cấu hình PMD sâu hơn

### 8.1. Built-in categories và custom ruleset

Để chạy hai categories thay vì custom XML, thay phần PMD của demo bằng:

```kotlin
pmd {
    toolVersion = "7.16.0"
    ruleSets = listOf(
        "category/java/errorprone.xml",
        "category/java/bestpractices.xml"
    )
    ruleSetFiles = files()
    rulesMinimumPriority = 5
}
```

Đây là **một phương án thay thế**, không đặt đồng thời với custom ruleset của demo nếu bạn muốn kết quả rõ ràng. Tham chiếu **cả category** có nghĩa sau khi nâng PMD, những rules mới thêm vào category có thể tự bật; đánh giá tác động trước khi áp dụng như CI gate.

Ngược lại, custom XML chỉ liệt kê từng rule giúp policy ổn định qua version upgrades, nhưng nhóm phải chủ động bổ sung rules mới có giá trị.

### 8.2. PMD priority hoạt động thế nào?

PMD dùng priority **1 cao nhất → 5 thấp nhất**. `rulesMinimumPriority=5` theo Gradle nghĩa là có thể báo cả priority 1–5. Giá trị **3** thường lọc lấy các rules priority 1–3, bỏ priorities 4–5; đây là cách giảm lượng cảnh báo ở giai đoạn khởi tạo, nhưng cũng bỏ qua một số phát hiện.

Không nhầm giá trị priority với **số lượng findings được phép**. Gradle PMD còn có `maxFailures` (đếm violations trước khi fail, mặc định 0) và `ignoreFailures` (không fail khi vi phạm). Nếu nhóm muốn chất lượng cao, ưu tiên xử lý triệt để/đặt baseline có kế hoạch, thay vì tăng maxFailures mãi.

Một task-level example:

```kotlin
tasks.withType<Pmd>().configureEach {
    maxFailures.set(0)
}
```

Đây là **đoạn bổ sung**, không thay thế nguyên block `pmd`. Nếu Gradle Wrapper cũ chưa hỗ trợ `maxFailures`, kiểm tra API trước khi copy.

### 8.3. PMD reports và format

Trong Gradle hiện đại:

```kotlin
tasks.withType<Pmd>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
        // Các format khác (CSV/SARIF/CodeClimate) tùy Gradle version.
    }
}
```

Khi CI cần machine-readable output, XML có tính tương thích rộng. **SARIF/CSV** chỉ có nếu Gradle version API/report container hỗ trợ; đừng copy `sarif.required` vào Wrapper cũ rồi nghĩ PMD lỗi. Reports không nhất thiết phải bật tất cả formats; chọn theo hệ thống phân tích CI thực.

Có thể đặt output cụ thể:

```kotlin
tasks.named<Pmd>("pmdMain") {
    reports {
        html.outputLocation.set(
            layout.buildDirectory.file("reports/pmd/custom-main.html")
        )
    }
}
```

Đây là **override riêng cho PMD task**, không liên quan `SpotBugsTask.reports.create("html")`. Đặt đường output khác nhau theo task/source set để không ghi đè nhau trong multi-project.

### 8.4. PMD Java toolchain riêng

Theo Gradle, PMD mặc định có thể chạy trên Java toolchain của project; nếu không có toolchain, dùng JVM chạy Gradle. Khi có yêu cầu đặc biệt, chạy PMD với JDK 17 độc lập:

```kotlin
tasks.withType<Pmd>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
```

Đây là **đoạn tùy chọn**, không cần thêm vào demo vì project đã `java.toolchain=17`. Nếu dùng PMD/JDK version không tương thích, lỗi analyzer startup có thể xuất hiện trước khi quét source. `javaLauncher` chọn JVM của PMD worker, không tự đổi Java compiler target của project.

### 8.5. Tối ưu threads

```kotlin
pmd {
    threads = 2
}
```

PMD `threads` là số luồng bên trong PMD analyzer, **khác Gradle `--parallel` và `org.gradle.workers.max`**. Với 8 subprojects đang chạy `pmdMain` cùng lúc, `threads=4` có thể tạo tải CPU lớn hơn dự kiến. Chọn theo CPU/quota CI, không mặc định tăng threads đến số core mỗi máy.

### 8.6. Phụ thuộc phục vụ type resolution

`pmdAux` configuration cho các thư viện bổ sung khi PMD cần resolve types. Không phải nơi khai báo application runtime dependencies:

```kotlin
dependencies {
    // Mẫu tình huống khi một thư viện types thực sự tồn tại.
    add("pmdAux", "com.example:analysis-types:1.0")
}
```

Địa chỉ ở đây chỉ là **tọa độ minh họa**, không thể chạy nếu repository không có artifact đó. Trong project thật, ưu tiên để PMD task có đúng source set classpath; chỉ thêm `pmdAux` khi giải thích được class nào PMD thiếu.

## 9. Cấu hình SpotBugs sâu hơn

### 9.1. Plugin version, toolVersion và rule/report settings

Trong SpotBugs Gradle plugin 6.x, `effort` và `reportLevel` dùng **enum**, không phải strings cũ:

```kotlin
import com.github.spotbugs.snom.Confidence
import com.github.spotbugs.snom.Effort

spotbugs {
    toolVersion = "4.10.5"
    effort = Effort.MAX
    reportLevel = Confidence.DEFAULT
    ignoreFailures = false
    maxHeapSize = "1g"
}
```

Đây là **một phiên bản cấu hình thay thế**, không dán hai block `spotbugs` trái nhau nếu không biết thứ tự override.

- `Effort.MAX`: yêu cầu analyzer thử mức phân tích cao hơn; có thể tốn tài nguyên hơn.
- `Confidence.DEFAULT`: giữ ngưỡng confidence mặc định, không tự đồng nghĩa với priority 5 của PMD.
- `reportLevel` điều khiển mức confidence warnings được báo; không phải “severity mới có CVE”.
- `ignoreFailures=false` để CI fail khi SpotBugs phát hiện vi phạm theo policy, không có nghĩa SpotBugs sẽ fail vì mọi warning ngoài filter.
- `maxHeapSize` cho SpotBugs analysis process, không phải JavaCompile/test heap.
- `toolVersion` là bản SpotBugs analyzer; không đặt `toolVersion="6.5.13"` vì đó là plugin version, không phải SpotBugs engine.

Khi chuyển từ plugin cũ (ví dụ v4/v5) lên v6, xem migration guide vì `effort`/`reportLevel` đã chuyển sang enum API. Các DSL cũ kiểu `effort="max"` hoặc `reportLevel="high"` có thể không hợp lệ.

### 9.2. Include/exclude filters trong SpotBugs

SpotBugs filter file dùng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
    <Match>
        <Class name="example.quality.GeneratedAdapter"/>
        <Bug pattern="UUF_UNUSED_FIELD"/>
    </Match>
</FindBugsFilter>
```

Đây là **ví dụ một ngoại lệ cụ thể**, không phải file baseline của demo. Nó chỉ lọc bug pattern `UUF_UNUSED_FIELD` trong class `example.quality.GeneratedAdapter`. Không đặt `<Class name="~.*"/>` để suppress mọi bug trong toàn repo, và không dùng `<Bug category="CORRECTNESS"/>` quá rộng chỉ để CI xanh.

Cấu hình:

```kotlin
spotbugs {
    excludeFilter = file("config/spotbugs/exclude.xml")
}
```

Cấu trúc `<Match>` có thể chứa `<Class>`, `<Method>`, `<Field>`, `<Bug>`, `<Confidence>`. Các yếu tố trong một Match thường kết hợp theo phép AND. Regex trong `<Class name="~...">` có quy tắc riêng của SpotBugs; nên kiểm tra bằng report thực tế sau khi thêm filter.

**Kỷ luật suppression:**

1. Xem finding cụ thể, file/line, bug pattern và false-positive justification.
2. Ưu tiên sửa code nếu lỗi thực.
3. Nếu false positive, thêm filter **hẹp nhất**, có comment/ticket/owner và review date theo policy.
4. Đảm bảo filter không vô tình che lớp hoặc bug khác.
5. Kiểm tra lại số findings trên toàn repo sau khi thêm filter.
6. Không xóa toàn bộ `exclude.xml` chỉ để chạy nhanh hơn rồi bỏ qua cảnh báo.

### 9.3. Baseline và annotations

SpotBugs plugin có `baselineFile` cho quản lý warnings tồn tại trước khi áp gate; cách nó vận hành phụ thuộc plugin version. Khi có nhiều findings legacy, nên chọn quy trình **chỉ ngăn bug mới** và giảm baseline dần thay vì cho phép `ignoreFailures=true` mãi.

Có thể dùng `@SuppressFBWarnings` khi thật sự cần suppress bug cụ thể ở method/class; annotation nằm trong module `com.github.spotbugs:spotbugs-annotations` và phải có mặt trên compile classpath theo scope thích hợp, thường `compileOnly`:

```kotlin
dependencies {
    compileOnly("com.github.spotbugs:spotbugs-annotations:4.10.5")
}
```

Đây là **đoạn mở rộng tùy chọn**, chưa được dùng trong Java source demo. Không chỉ thêm annotation dependency rồi nghĩ analyzer sẽ tự suppress mọi finding. Lạm dụng annotation ở class-level có thể giấu bug mới; ưu tiên nêu `justification` cho từng suppression.

### 9.4. External detectors: Find Security Bugs

SpotBugs có thể tải analyzer plugin ngoài, ví dụ **Find Security Bugs**, qua configuration riêng:

```kotlin
dependencies {
    spotbugsPlugins(
        "com.h3xstream.findsecbugs:findsecbugs-plugin:1.14.0"
    )
}
```

Version ví dụ đã có trong tài liệu SpotBugs, nhưng phải review compatibility, nguồn, license và security trước khi dùng production. Đây **không phải một Gradle plugin `id(...)` thứ hai**; nó là detector plugin được SpotBugs runtime load. Nó cũng **không tự thay thế security review hoặc taint analysis toàn diện**.

Có thể cấu hình `visitors`, `omitVisitors`, `chooseVisitors` để chọn detectors. Đây là lớp rule selection **của SpotBugs**, khác `pmd.ruleSets`. Chỉ dùng khi đã hiểu bug pattern cần điều chỉnh; không “tắt mọi visitors” để task kết thúc nhanh.

### 9.5. SpotBugs reports

Theo plugin 6.x:

```kotlin
tasks.named<SpotBugsTask>("spotbugsMain") {
    reports.create("html") {
        required = true
        outputLocation = layout.buildDirectory.file(
            "reports/spotbugs/main-analysis.html"
        )
    }
}
```

Đây là **mẫu đặt report riêng cho main**, không dán chồng lên `tasks.withType<SpotBugsTask>()` của demo nếu chúng tạo cùng report name trên cùng task. SpotBugs reports container khác PMD; nhiều báo cáo XML/HTML/EMACS/TEXT có thể phụ thuộc phiên bản plugin và report factories.

Dù đã bật HTML, CI có thể muốn XML phục vụ phân tích tự động. Hãy kiểm tra `spotbugsMain.reports` trên plugin version thật rồi bật XML output với location riêng theo docs. Không giả định Gradle `pmdMain` và `spotbugsMain` đều tạo cùng format/file path mặc định.

## 10. Phân tích main và test riêng

Có một sự khác biệt về chiến lược:

- **Production code** thường yêu cầu nghiêm: báo lỗi nullness, resource leak, visibility, concurrency; không nên ignore warnings mới.
- **Test code** có thể dùng static fixtures, `System.out`, test doubles hoặc reflection, nên một số rules PMD/SpotBugs ít giá trị hơn hoặc báo nhiều false positives.

Không vì vậy tắt toàn bộ `pmdTest`/`spotbugsTest` theo thói quen. Có thể cấu hình **policy riêng theo task**, ví dụ PMD Test chỉ kiểm errorprone:

```kotlin
tasks.named<Pmd>("pmdTest") {
    ruleSets = listOf("category/java/errorprone.xml")
    ruleSetFiles = files()
}
```

Đây là **mẫu thay thế riêng**, không thêm vào demo nếu muốn `pmdTest` sử dụng đúng custom XML chung. Sau khi tách policy, kiểm tra `pmdMain` và `pmdTest` thực sự đọc rules khác nhau.

Với SpotBugs, có thể tạo filter chỉ cho `spotbugsTest` (trong `tasks.named<SpotBugsTask>(...)`) để loại một bug pattern đã có lý do, hoặc điều chỉnh report level theo task. **Không** dùng file filter chung với wildcard giấu warnings của toàn project khi chỉ một test fixture gây false positive.

Khi có custom source set `integrationTest`, các plugins có thể tạo các task tương ứng như `pmdIntegrationTest`/`spotbugsIntegrationTest` khi source set được hỗ trợ và các plugins được áp dụng đúng. Tên tasks phụ thuộc thực tế; dùng `./gradlew tasks --all` để xác minh, đừng tự dự đoán tuyệt đối.

## 11. Multi-project build: áp policy thống nhất nhưng không lạm dụng `subprojects`

Trong monorepo có `:api`, `:service`, `:worker`, một cách cũ là:

```kotlin
subprojects {
    apply(plugin = "pmd")
    apply(plugin = "com.github.spotbugs")
}
```

Cách này có rủi ro cross-project configuration, eager configuration và khó kiểm soát module nào thực sự cần Java quality tools. Với Gradle hiện đại nên ưu tiên **convention plugin** (ví dụ `company.java-quality`) trong `build-logic`/`buildSrc`:

```text
root/
├── settings.gradle.kts
├── gradle/libs.versions.toml
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── company.java-quality.gradle.kts
├── api/build.gradle.kts
└── service/build.gradle.kts
```

Một convention plugin có thể:

- Áp `java-library`/`pmd`/`com.github.spotbugs` theo loại module.
- Đặt `pmd.toolVersion` và PMD custom ruleset.
- Đặt SpotBugs `toolVersion`, effort/confidence, excludes, report outputs.
- Kết nối quality tasks tới `check` theo policy.
- Tách test/main policy hợp lý.
- Thiết lập task avoidance với `configureEach` và không hardcode paths theo máy.

**Lưu ý:** precompiled convention plugin là **build riêng**. External plugin cần được đặt trên **build-logic plugin classpath** và applied theo ID, chứ không đơn giản copy `alias(libs.plugins.spotbugs)` vào precompiled plugin source. Không tự giả định main version catalog được thừa kế ở `buildSrc`/included build; phải import nếu cần.

### 11.1. Version catalog cho external plugin

Trong root `gradle/libs.versions.toml`:

```toml
[versions]
spotbugsGradlePlugin = "6.5.13"

[plugins]
spotbugs = { id = "com.github.spotbugs", version.ref = "spotbugsGradlePlugin" }
```

Project `build.gradle.kts`:

```kotlin
plugins {
    java
    pmd
    alias(libs.plugins.spotbugs)
}
```

Đây là **cấu hình thay thế** cho `id("com.github.spotbugs") version "6.5.13"`. Không giữ cả hai request trong một `plugins { }`. Catalog chỉ pin **Gradle plugin version**; `spotbugs.toolVersion` vẫn phải được cấu hình riêng nếu muốn pin analyzer.

### 11.2. Policy theo loại module

Không cần áp SpotBugs vào module Java source **không có .class outputs phù hợp**, module resources-only hoặc plugin không hỗ trợ; tương tự PMD phân tích Java source chứ không tự kiểm Kotlin code. Nếu project hỗn hợp Kotlin/Java, kiểm tra tools có thực sự phân tích được output mong muốn; PMD Java plugin không tương đương Detekt/Ktlint. SpotBugs phân tích Java bytecode, nhưng không phải chuyên gia phân tích mọi ngữ nghĩa Kotlin coroutines.

## 12. Reports là đầu ra quản trị, không phải mục tiêu duy nhất

Một hệ thống CI có thể yêu cầu **HTML cho developer**, **XML/SARIF cho CI** và **quality gate** để fail merge khi có violations vượt ngưỡng.

Tối thiểu:

1. Bật report có thể đọc được; mỗi task có path riêng.
2. Gọi `./gradlew check` trong CI job, không chỉ `test`.
3. Giữ `ignoreFailures=false` trong những tasks cần gate.
4. Publish reports lên CI khi fail; nếu không, người đọc chỉ thấy `BUILD FAILED` không biết cần sửa gì.
5. Giữ checksum/dependency verification cho PMD/SpotBugs tools/plugins vì chúng cũng là code tải và chạy trong build.
6. Khi update tools/rulesets, review sự thay đổi số findings để phân biệt “tool mới phát hiện bug cũ” với “code mới có bug”.
7. Không chỉ dựa vào tổng finding count; ưu tiên bug categories liên quan correctness/security và mức tin cậy.

**Khác biệt giữa report và fail condition:** có thể tạo report ngay cả khi task fail do violations; CI cần cấu hình upload reports **kể cả khi command `check` exit != 0**. Tùy CI platform, dùng step `always()`/`when: always` hoặc tương đương.

Nếu reports trống, kiểm tra source set có file hay không, task có thực thi không, filters có loại mọi finding không và Gradle có tìm được analyzer/runtime classes không. Empty report **không tự chứng minh** toàn codebase “không có bug”.

## 13. Trình tự CI đề xuất

```text
Checkout source
   |
Verify Gradle Wrapper / JDK 17
   |
Resolve plugin + analyzer artifacts từ approved repositories
   |
compileJava / compileTestJava
   |
+-------------------+--------------------+
|                   |                    |
JUnit Test         PMD                  SpotBugs
|                   |                    |
Test reports        Source findings      Bytecode findings
|                   |                    |
+-------------------+--------------------+
   |
Gradle check quality gate
   |
Archive XML/HTML reports dù PASS hay FAIL
   |
Publish/deploy chỉ nếu gate đạt policy
```

Lệnh cho Linux/macOS:

```bash
./gradlew --version
./gradlew clean check
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean check
```

Với demo, `check` kéo test, PMD, SpotBugs theo lifecycle links của plugins. Tên/outcome của tasks và report output thực tế có thể thay đổi khi plugin/configuration version khác nhau; kiểm tra bằng:

```bash
./gradlew check --dry-run
./gradlew tasks --all
```

**Không dùng `--dry-run` để xác nhận quality rules đã chạy**: nó chỉ mô phỏng task graph. Dùng `clean check` hoặc `--rerun-tasks pmdMain spotbugsMain` để thực sự kiểm tra.

### 13.1. CI chỉ cho tải artifact từ mirror

SpotBugs plugin resolution dùng `pluginManagement.repositories`; PMD và SpotBugs analyzer artifacts thường đến project dependency repos hoặc tool-specific configurations. Nếu tổ chức chỉ dùng internal repositories, mirror phải chứa:

- SpotBugs Gradle plugin marker + implementation dependencies.
- SpotBugs analyzer/PMD analyzer artifacts đúng version.
- Các runtime libraries/transitive dependencies của analyzers.
- JUnit dependencies nếu chạy demo tests.

Đừng giả định một `mavenCentral()` trong `build.gradle.kts` là đủ để plugin marker được tìm; plugin repositories và project repositories là hai loại cấu hình khác nhau.

### 13.2. CI có ít CPU và RAM

`pmd.threads=4` cộng với Gradle parallel tasks và SpotBugs `maxHeapSize="1g"` cho nhiều modules có thể làm runner vượt hạn mức. Tùy CI quota:

- Giảm PMD threads khi nhiều modules cùng phân tích.
- Giảm Gradle `--max-workers` nếu cần để tránh memory contention.
- Tách quality scan theo module hoặc job một cách có kiểm soát.
- Không tăng toàn bộ heaps vô hạn khi analyzer OutOfMemory; xem source sets/classpath và version tool.
- Cache Gradle artifacts theo chính sách nhưng không để cache phá verification/immutability.
- Nếu check chạy chậm, xem task inputs, incremental/caching behavior và execution log trước khi disable tools.

**Performance không nên được “cải thiện” bằng cách để quality gate chỉ chạy mỗi tuần nếu yêu cầu của repo là gate mọi PR.** Tối ưu scope đúng, triage false positives và cache có trách nhiệm.

## 14. Phân biệt lỗi plugin, lỗi tool runtime và finding thực sự

| Triệu chứng | Phân loại | Kiểm tra đầu tiên |
| --- | --- | --- |
| `Plugin com.github.spotbugs was not found` | Plugin resolution | `pluginManagement.repositories`, plugin ID/version, marker, credentials |
| `Plugin [id: 'pmd', version: '...']` fail | Core plugin bị khai báo external version sai | `plugins { pmd }`, bỏ version |
| `Could not resolve net.sourceforge.pmd...` | PMD analyzer dependency resolution | Project repositories, proxy, version, dependency metadata |
| `Could not resolve com.github.spotbugs:spotbugs...` | SpotBugs analyzer resolution | `spotbugs.toolVersion`, repositories, network |
| `No matching toolchains found` | JDK/toolchain availability | `javaToolchains`, JDK 17 installation/resolver |
| `UnsupportedClassVersionError` trong SpotBugs | Analyzer JVM hoặc compiled class compatibility | Gradle/JDK/plugin version, SpotBugs tool support |
| `pmdMain` báo violations | Source rule findings | PMD HTML/XML report, rule names, locations |
| `spotbugsMain` báo violations | Bytecode bug findings | SpotBugs HTML/XML report, pattern/confidence |
| `spotbugsMain NO-SOURCE` | Không có classes của source set | Source set, compilation outputs, task wiring |
| `pmdTest NO-SOURCE` | Test Java source trống | `src/test/java`, task source set |
| `EmptyCatchBlock rule missing` | PMD rule name/version sai | PMD 7.x ruleset reference XML |
| `Cannot find ruleset file` | PMD ruleset path sai | File `config/pmd/ruleset.xml` tồn tại trong project root |
| `Could not parse FindBugsFilter` | SpotBugs filter XML sai | `FindBugsFilter` root, `Match` selectors, XML syntax |
| `No such property reportLevel` | DSL/API plugin version mismatch | SpotBugs plugin 6.x enum/Gradle version |
| `Could not get unknown property reports` | Nhầm task/extension API | `Pmd.reports` và `SpotBugsTask.reports` khác nhau |
| `check` thành công nhưng không có SpotBugs tasks | Plugin full không apply/`runOnCheck` bị tắt | `./gradlew tasks --all`, `com.github.spotbugs` vs base plugin |
| `test` thành công nhưng PMD không chạy | Sai lifecycle command | Chạy `check` hoặc `pmdMain` |
| SpotBugs phát hiện bug chỉ ở `spotbugsTest` | Test bytecode patterns/fixtures | Xem test report và filter theo source set |
| CI memory error trong analyzer | Heap/parallelism | `maxHeapSize`, `threads`, `--max-workers` |
| HTML báo cáo không tìm thấy | Report chưa required/đường khác | `reports.outputLocation`, task thực có chạy không |
| Phát hiện quá nhiều lỗi sau nâng PMD | Rule category mới/threshold thay đổi | So tool versions, ruleset XML và Git diff |
| Findings biến mất sau thêm filter | Filter quá rộng | Review `exclude.xml` và before/after findings |
| `Build passed` dù vi phạm | `ignoreFailures=true`/`runOnCheck=false` | Kiểm tra policy gating và task links |
| Lỗi chỉ xuất hiện khi `--parallel` | Resource race/corrupt cache/build logic | Xem task outputs/Gradle worker logs, giảm concurrency |

### 14.1. Một chuỗi debug thực tế

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew tasks --all
./gradlew check --dry-run
./gradlew clean compileJava compileTestJava
./gradlew pmdMain --info --stacktrace
./gradlew spotbugsMain --info --stacktrace
./gradlew check
```

**Đọc root cause, không chỉ hai dòng `BUILD FAILED` cuối.** Nếu PMD task fail vì XML ruleset sai, sửa XML; không đổi SpotBugs dependency. Nếu SpotBugs task fail vì thiếu compiled classes, sửa compilation/source set; đừng tắt PMD.

## 15. Vì sao `ignoreFailures` nguy hiểm nếu dùng bừa?

Cả hai công cụ có tùy chọn **bỏ qua violations** để tạo reports mà không fail build. Nó hữu ích ngắn hạn khi đưa analyzer vào codebase legacy, nhưng gây lỗi quản trị nếu trở thành default.

```kotlin
// Một cấu hình KHÔNG NÊN dùng làm quality gate production:
pmd {
    isIgnoreFailures = true
}
spotbugs {
    ignoreFailures = true
}
```

Những dòng này làm CI dễ báo `BUILD SUCCESSFUL` dù có lỗi mã. Nếu cần chuyển tiếp:

1. Chạy scan báo cáo ban đầu, thống kê findings theo category, module, owner.
2. Triaging ưu tiên bug correctness/security thật sự trước.
3. Sửa root cause trong code cho những vấn đề có thể.
4. Với legacy warnings đã xác định, dùng baseline/suppression hẹp, có lý do.
5. Chuyển `ignoreFailures=false` cho modules/violation scopes đã đạt policy.
6. Gỡ ngoại lệ khi sửa được code.
7. Theo dõi **số findings mới**, không chỉ số findings tổng.
8. Ghi quality gate như yêu cầu PR; tránh task skip ngoài ý muốn.

Đừng cho **tất cả** PMD/SpotBugs findings cùng một SLA; mức ưu tiên và chi phí xử lý khác nhau. Nhưng cũng đừng gọi một warning là “style only” khi nó chỉ ra null dereference hoặc resource leak.

## 16. Cách xử lý false positives đúng

### 16.1. Phân loại finding trước khi sửa

Một finding phải được xét:

- Rule/bug pattern ID.
- File/class/method/line cụ thể.
- Source path và source set (main/test/generated).
- Phiên bản tool/plugin tạo report.
- Điều kiện để bug thật sự xảy ra.
- Có annotation/third-party behavior/reflective access khiến analyzer hiểu thiếu context không?
- Risk nếu sửa code so với nếu bỏ qua.
- Có evidence từ test, reproducer hoặc docs không?

**Không tự tin một finding là false positive chỉ vì tests pass**: tests không bao phủ hết paths. Ngược lại, static analyzer có thể thiếu runtime data, nên không nên thay đổi semantics API chỉ để làm report trống nếu finding không đúng.

### 16.2. Ưu tiên thứ tự xử lý

1. Nếu bug thật: sửa code, thêm test hồi quy.
2. Nếu rule PMD gây noise không phù hợp business domain: điều chỉnh ruleset có review, không tắt toàn PMD.
3. Nếu SpotBugs báo false positive: thêm exclusion theo class + bug pattern hoặc annotation method-level, có justification.
4. Nếu code generated: đưa vào đúng source set hoặc có exclusion tập trung; đừng loại `src/main/java` toàn bộ.
5. Nếu tool không hiểu bytecode mới: nâng analyzer/plugin thích hợp, kiểm tra compatibility.
6. Nếu module tạm chưa đạt policy: có migration plan và gate tiến bộ, không tắt vô thời hạn.

### 16.3. Ví dụ SpotBugs narrow exclusion

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
    <!-- Suppress một pattern duy nhất trong một class có review. -->
    <Match>
        <Class name="example.quality.LegacyGeneratedMapper"/>
        <Bug pattern="UUF_UNUSED_FIELD"/>
    </Match>
</FindBugsFilter>
```

Đây là **mẫu sau review**, không tồn tại trong demo baseline. Nếu class tên khác, filter có thể không match. Nếu bug pattern ID sai, filter cũng không có tác dụng; kiểm tra actual SpotBugs XML report trước khi thêm.

## 17. Khi chuyển từ Gradle cũ và SpotBugs plugin cũ

Một dự án Java lâu năm có thể dùng `findbugs` plugin (đã obsolete) hoặc SpotBugs Gradle plugin v4/v5.

Với Gradle mới:

- Dùng **`pmd` core plugin** cho PMD, không dùng `id("net.sourceforge.pmd")` nếu không phải plugin thật.
- Dùng **`com.github.spotbugs` external plugin** cho SpotBugs; không nhầm `com.github.spotbugs-base`.
- Kiểm compatibility Gradle Wrapper/JDK và plugin version mới trước khi nâng.
- Update `effort`/`reportLevel` từ strings cũ sang enums của SpotBugs plugin 6.x.
- Kiểm lại reports DSL, output locations, `ignoreFailures`, filter paths và analyzers `toolVersion`.
- Chạy `./gradlew tasks --all` để so task names/linkage cũ với mới.
- Cần benchmark findings: PMD/SpotBugs rule databases thay đổi nên “tăng warnings” sau nâng tool chưa chắc do mã mới kém chất lượng.
- Không dùng `--refresh-dependencies` như một cách sửa không xác định; khi mismatch/verification fail, xác minh artifact origin trước.

**Không khẳng định plugin 6.5.13 chạy được với mọi Gradle 7/8/9 hoặc Java version.** SpotBugs Gradle plugin docs có minimum requirements và thay đổi qua các release; hãy đọc đúng release notes của phiên bản được pin. PMD analyzer cũng có Java runtime requirements riêng với Gradle Daemon; toolchain API giải quyết JDK selection khi được hỗ trợ.

## 18. PMD + SpotBugs không thay thế các công cụ khác

Một project Java chất lượng cao còn cần:

| Công cụ | Mục tiêu chính | Khác PMD/SpotBugs ở đâu? |
| --- | --- | --- |
| JUnit Jupiter / TestNG | Xác minh hành vi chạy thật bằng test cases | Static analyzers không chạy tất cả business paths |
| JaCoCo | Thu thập code coverage từ tests | 80% coverage không có nghĩa thiếu 0 bug |
| Checkstyle | Enforce style, naming, formatting-related policies | PMD và SpotBugs tập trung rules/bug patterns khác |
| Spotless | Auto-format source | Không thay bytecode analysis |
| Dependency verification | Kiểm checksum/PGP của artifacts được resolve | Không phát hiện bug logic trong code |
| SCA/SBOM | Tìm vulnerabilities/licensing qua dependency graph | Không thay test/bytecode check |
| SonarQube hoặc tương tự | Tổng hợp findings, metrics, quality gates | Cần đúng data source/configuration; không tự chứng minh tool đã chạy |
| Code review | Xem business logic, architecture, security context | Phân tích tĩnh không hiểu mọi contract/domain |

Một quality gate hiệu quả kết hợp nhiều tín hiệu, nhưng **không để số lượng plugin phình ra ngoài khả năng bảo trì**. Chọn những rules có hành động sửa rõ ràng, publish reports có chủ đích và review mỗi lần đổi tool version.

## 19. Checklist nghiệm thu

- [ ] Dự án có Gradle Wrapper/JDK được pin theo compatibility matrix.
- [ ] `pmd` được apply như Gradle core plugin **không gán external version**.
- [ ] `com.github.spotbugs` được apply với external plugin version đã duyệt.
- [ ] `pmd.toolVersion` và `spotbugs.toolVersion` được xác định, không nhầm với Gradle/plugin version.
- [ ] Source sets `main` và `test` có task `pmdMain`, `pmdTest`, `spotbugsMain`, `spotbugsTest` tương ứng.
- [ ] SpotBugs phân tích compiled bytecode; compilation tasks tồn tại và được nối trong task graph.
- [ ] PMD custom XML có đúng namespace, rule references và path.
- [ ] `ruleSets=emptyList()` khi chỉ muốn custom PMD ruleset.
- [ ] PMD priority threshold được hiểu 1 cao nhất, 5 thấp nhất.
- [ ] SpotBugs effort/confidence dùng enum API phù hợp plugin version.
- [ ] SpotBugs exclude filter có XML đúng và scope tối thiểu.
- [ ] HTML/XML reports có output riêng theo task/source set, CI có thể thu thập cả khi check fail.
- [ ] `ignoreFailures=false` trong các task cần làm quality gate.
- [ ] `./gradlew check --dry-run` và `tasks --all` xác nhận task linkage.
- [ ] `./gradlew clean check` chạy thật trên môi trường sạch, không chỉ test/compile.
- [ ] Có cơ chế triage false positive/baseline cho legacy findings.
- [ ] Multi-project policy dùng convention plugin thay vì copy-paste/hardcode paths.
- [ ] Nâng analyzer/plugin có review phát hành, rule database và thay đổi findings.
- [ ] CI không bỏ qua SpotBugs/PMD khi thiếu report hoặc task `NO-SOURCE` không mong muốn.
- [ ] Findings về correctness, nullness, resource leaks có đường xử lý rõ ràng, không chỉ bị suppressed.

## 20. Tự kiểm tra kiến thức

1. **Vì sao `pmd` không cần `version "..."` trong `plugins`?** Vì đây là core Gradle plugin; analyzer version nằm ở `pmd.toolVersion`.
2. **Vì sao `com.github.spotbugs` cần version?** Nó là external Gradle plugin được resolve qua plugin repositories.
3. **SpotBugs plugin 6.5.13 có nghĩa analyzer cũng là 6.5.13?** Không. Plugin và analyzer có vòng đời/versioning riêng.
4. **PMD phân tích gì?** Java source/AST và rulesets, với type resolution theo cấu hình.
5. **SpotBugs phân tích gì?** Compiled bytecode/classes và classpath, dùng bug detectors.
6. **Tại sao `spotbugsMain` phụ thuộc compilation?** Vì nó cần `.class` làm input, không phân tích đơn thuần file `.java`.
7. **`pmdMain` và `pmdTest` có tự dùng rules khác nhau không?** Thường cùng extension policy nếu chưa override; muốn khác phải cấu hình per-task.
8. **Nếu custom PMD ruleset có nhưng vẫn thấy default warnings, kiểm tra gì?** `ruleSets` và `ruleSetFiles` có đang cộng thêm built-in category không?
9. **PMD `rulesMinimumPriority=5` có “chỉ mức nghiêm trọng nhất” không?** Không; 1 là mức ưu tiên cao nhất, 5 nhận cả mức thấp.
10. **SpotBugs `Confidence.DEFAULT` có tương đương PMD priority 5 không?** Không; hai tool có thang và cơ chế khác.
11. **Có thể thêm Find Security Bugs bằng `plugins { id(...) }` không?** Theo plugin SpotBugs, detector mở rộng thường thêm qua `spotbugsPlugins` configuration.
12. **Vì sao `check` cần gọi trong CI?** Vì nó gắn cả test và quality tasks theo lifecycle, còn `test` đơn thuần không đủ.
13. **Bật HTML report làm build fail khi warning không?** Không trực tiếp; enforcement phụ thuộc severity/filter/`ignoreFailures`/tool task outcome.
14. **Một SpotBugs filter có `<Class name="...">` mà không `<Bug>` có thể nguy hiểm ở đâu?** Nó có thể lọc mọi bug trong class, rộng hơn một finding.
15. **Vì sao PMD có thể fail dù SpotBugs report không có finding?** Vì source rules của PMD và bytecode detectors của SpotBugs là hai bộ phân tích riêng.
16. **Vì sao compilation thành công chưa chứng minh SpotBugs chạy?** Vì task SpotBugs có thể bị bỏ qua, không apply, skip hoặc fail ở analyzer runtime.
17. **Khi có generated code, nên disable toàn bộ PMD không?** Không. Nên xác định source set/pattern và exclusion hẹp cho generated files.
18. **Có thể tăng SpotBugs `maxHeapSize` để sửa PMD ruleSet XML error không?** Không. Đó là hai nguyên nhân độc lập.
19. **Nếu CI PASS nhưng báo cáo cũ vẫn tồn tại, kết luận gì?** Chưa đủ bằng chứng analyzer đã chạy lượt hiện tại; kiểm tra task outcomes/timestamps.
20. **Có nên đặt `ignoreFailures=true` vô thời hạn khi legacy có nhiều warnings?** Không. Cần baseline có thời hạn và kế hoạch giảm warnings.

## 21. Ghi nhớ

- **PMD = Gradle core plugin `pmd`, phân tích source**, tạo `pmdMain`/`pmdTest`.
- **SpotBugs = external plugin `com.github.spotbugs`, phân tích compiled bytecode**, tạo `spotbugsMain`/`spotbugsTest`.
- **Plugin version và analyzer toolVersion khác nhau**; phải pin và kiểm compatibility đúng.
- **PMD ruleset XML và SpotBugs FindBugsFilter XML là hai định dạng khác**.
- **PMD priority 1 là cao nhất; SpotBugs confidence/effort là thang riêng**.
- **`check`** là lifecycle gate phù hợp khi dùng cả hai, còn `test` chỉ chạy tests.
- **Reports và enforcement là hai việc khác nhau**; đừng dùng `ignoreFailures=true` làm giải pháp mặc định.
- **SpotBugs có thể phát hiện nullness/resource/concurrency patterns từ bytecode mà PMD ruleset source không báo**, và ngược lại PMD bắt các vấn đề source/style/logic patterns khác.
- **CI phải archive reports và kiểm tasks thực thi**, đồng thời có quy trình triage/suppression hẹp.
- **Convention plugins** giúp quản trị policies thống nhất trong monorepo.

## 22. Tài liệu chính thức

- [Gradle — The PMD Plugin](https://docs.gradle.org/current/userguide/pmd_plugin.html): core plugin, tasks `pmdMain`/`pmdTest`, PMD version, ruleSets, toolchains, threads.
- [Gradle — PMD Task API](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.quality.Pmd.html): `ruleSetFiles`, `maxFailures`, reports, classpath.
- [Gradle — PMD Extension API](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.quality.PmdExtension.html): `toolVersion`, `ignoreFailures`, `rulesMinimumPriority`.
- [PMD — Making Rulesets](https://pmd.github.io/pmd/pmd_userdocs_making_rulesets.html): XML namespace, individual rules, bulk categories, excludes.
- [PMD — Java Best Practices Rules](https://pmd.github.io/pmd/pmd_rules_java_bestpractices.html): `SystemPrintln`, rules priorities.
- [Gradle Plugin Portal — SpotBugs 6.5.13](https://plugins.gradle.org/plugin/com.github.spotbugs/6.5.13): ID và version của external plugin.
- [SpotBugs Gradle Plugin — README](https://github.com/spotbugs/spotbugs-gradle-plugin): extension, task reports, SpotBugs toolVersion, migration v6.
- [SpotBugs — Gradle Integration](https://spotbugs.readthedocs.io/en/stable/gradle.html): `spotbugsMain`/`spotbugsTest`, `check`, compiled class inputs.
- [SpotBugs — Filter Files](https://spotbugs.readthedocs.io/en/stable/filter.html): `FindBugsFilter`, `Match`, `Bug`, `Class`, scope.
- [SpotBugs — Introduction](https://spotbugs.readthedocs.io/en/stable/introduction.html): bytecode analyzer, requirements, bug patterns.
- [Gradle — Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) và [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Java 17 compiler/test setup.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `configureEach`, `tasks.named`.
