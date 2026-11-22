# Vai trò của quality gate và nối công cụ kiểm tra vào check trong Gradle

## 1. Quality gate là gì và vì sao cần một điểm kiểm tra chung?

Một hệ thống Java có thể biên dịch thành công nhưng vẫn chứa lỗi logic, test thất bại, mã vi phạm chuẩn định dạng, vấn đề phân tích tĩnh, tỷ lệ test coverage thấp hoặc những thay đổi không đạt tiêu chuẩn kỹ thuật của nhóm. Lệnh `compileJava` chỉ cho biết compiler xử lý được mã nguồn theo classpath và cấu hình hiện tại; nó **không chứng minh mã đã đáp ứng các tiêu chí chất lượng**.

**Quality gate** là tập điều kiện được quy định trước để quyết định một bản build, commit hoặc pull request có **được tiếp tục** sang bước merge, publish, deploy hay không. Ví dụ:

- Tất cả unit tests bắt buộc phải thành công.
- Không có lỗi Checkstyle ở mức nghiêm trọng mà nhóm đã thống nhất.
- Line coverage phải đạt ít nhất một ngưỡng thí nghiệm, ví dụ 80%.
- Các task phân tích tĩnh quan trọng phải được chạy và không bị âm thầm bỏ qua.
- Trong CI, job chất lượng phải kết thúc với mã thành công trước khi cho phép merge.

Trong Gradle, với project Java, task lifecycle **`check`** là điểm tự nhiên để gom các công việc **verification**. Câu lệnh mà nhóm mong muốn có thể rất ngắn:

```bash
./gradlew check
```

Nhưng để câu lệnh đó là quality gate thật, ta phải biết **task nào đã được nối vào `check`, task nào chưa và task nào có khả năng báo build failure**.

### 1.1. Quality gate không đồng nghĩa với một công cụ đơn lẻ

| Thành phần | Chức năng chính | Có thể trở thành gate? |
| --- | --- | --- |
| `compileJava` | Biên dịch mã Java | Thường là điều kiện nền tảng khi build/check cần compilation |
| `test` | Chạy unit tests | Có, khi test task thực sự chạy và fail khi test fail |
| Checkstyle | Kiểm tra quy tắc phong cách và một số vấn đề nguồn Java | Có, khi task được chạy và violations gây failure |
| PMD | Phân tích tĩnh mã nguồn theo rulesets | Có, nếu plugin/task được nối và cấu hình fail đúng |
| SpotBugs | Phân tích bytecode tìm mẫu lỗi tiềm tàng | Có, với plugin/task phù hợp |
| JaCoCo report | Đo/tạo báo cáo coverage | **Báo cáo đơn thuần chưa phải gate** |
| JaCoCo coverage verification | So sánh coverage với ngưỡng | Có, nếu task được nối vào `check` |
| Formatter `format` | Tự sửa định dạng source | Không nên chạy tự sửa code trong CI gate |
| Formatter `formatCheck` | Chỉ kiểm tra định dạng | Có, nếu task được nối và fail đúng |
| Dependency/security scan | Phát hiện dependency rủi ro theo chính sách | Có, nhưng phải xử lý khả năng false positive và cập nhật dữ liệu |

**Nguyên tắc:** quality gate là **chính sách kiểm soát**; Gradle task graph là cách thực thi chính sách đó; công cụ như Checkstyle/JaCoCo là **nguồn tín hiệu**, không tự tạo toàn bộ chính sách cho dự án.

## 2. Phân biệt `check`, `build`, `test` và `assemble`

Khi áp dụng Java plugin (trực tiếp hoặc qua `application`, `java-library`), Gradle cung cấp các lifecycle tasks liên quan:

- **`assemble`:** tạo các output/artifact được cấu hình, chẳng hạn JAR; tập trung vào sản phẩm build.
- **`check`:** chạy các công việc verification đã được nối vào task này.
- **`build`:** lifecycle task thường phụ thuộc cả `assemble` và `check`.
- **`test`:** chạy test suite mặc định của project Java; thường được Java plugin nối vào `check`.
- **`classes`:** yêu cầu biên dịch classes/resource outputs của source set chính.
- **`compileJava`:** biên dịch Java sources của source set chính.

Quan hệ khái niệm:

```text
                 :build
                 /    \
                v      v
          :assemble   :check
              |         |
              v         +--> :test               (Java plugin)
            :jar        +--> :checkstyleMain    (Checkstyle plugin)
                        +--> :checkstyleTest    (Checkstyle plugin)
                        +--> :jacocoTestCoverageVerification
                        |          (chỉ khi ta nối thủ công)
                        +--> :jacocoTestReport
                                   (nếu muốn report trong gate)
```

Đây là một sơ đồ quan hệ **không phải thứ tự log cố định**. Gradle có thể chạy các task độc lập theo thứ tự khác hoặc song song; task đang up-to-date hoặc không có source có thể `UP-TO-DATE`/`NO-SOURCE`. Không được kết luận một task đã thực hiện kiểm tra chỉ vì tên nó có trong cấu hình.

### 2.1. `check` là task lifecycle, không phải script chạy shell

Lệnh `./gradlew check` không mặc định tự dò mọi công cụ đã cài trên máy. Nó dựa vào **task dependencies** do plugin và build script khai báo.

Nếu nhóm cài thêm một công cụ độc lập `scanSources` nhưng **không nối nó vào `check`**, việc chạy `check` không bảo đảm `scanSources` được thực thi.

Ngược lại, nếu task kiểm tra gây lỗi và được nối đúng qua `dependsOn`, `check` sẽ thất bại theo cơ chế Gradle khi task phụ thuộc thất bại.

### 2.2. `assemble` có thể thành công trong khi `check` thất bại

Một source file có thể hợp lệ về cú pháp, tạo JAR bình thường, nhưng vi phạm Checkstyle hoặc test assertion. Lúc đó:

```bash
./gradlew assemble
```

có thể thành công, còn:

```bash
./gradlew check
```

có thể thất bại. Đây là tình huống hợp lý, không phải Gradle mâu thuẫn. Muốn CI không publish bản có vấn đề, hãy buộc bước publish/deploy phụ thuộc vào **job gate**, không chỉ kiểm tra artifact đã được tạo.

## 3. Hai cách một công cụ trở thành thành phần của `check`

### 3.1. Plugin tự nối task vào `check`

Gradle **Checkstyle plugin** tạo các task như `checkstyleMain` và `checkstyleTest` cho Java source sets. Với Java plugin, các Checkstyle tasks được **tự động đưa vào dependencies của `check`**.

Ví dụ:

```kotlin
plugins {
    java
    checkstyle
}
```

Sau khi cấu hình ruleset và tool phù hợp, `./gradlew check` thường đã chạy Checkstyle tasks mà không cần viết thêm:

```kotlin
// Không cần thêm thủ công với Checkstyle plugin thông thường.
tasks.named("check") {
    dependsOn("checkstyleMain", "checkstyleTest")
}
```

Đoạn thứ hai chỉ nhằm minh họa quan hệ: việc lặp `dependsOn` cho Checkstyle mặc định là thừa. Nếu bạn tạo custom Checkstyle task ngoài source sets mặc định hoặc dùng plugin khác, phải kiểm tra liệu task đó đã được nối chưa.

### 3.2. Phải nối thủ công: `jacocoTestCoverageVerification`

Gradle **JaCoCo plugin** có task `jacocoTestCoverageVerification` để đánh giá coverage threshold, nhưng **không tự động nối task này vào `check`**. Lý do: không phải mọi dự án đều muốn coverage threshold tự làm fail mọi lệnh `check`.

Ta có thể chủ động áp dụng policy:

```kotlin
tasks.named("check") {
    dependsOn(tasks.named("jacocoTestCoverageVerification"))
}
```

Nếu task coverage cần dữ liệu test, phải bảo đảm test chạy trước:

```kotlin
tasks.named("jacocoTestCoverageVerification") {
    dependsOn(tasks.named("test"))
}
```

**Quan trọng:** `dependsOn` vừa yêu cầu task được đưa vào graph, vừa tạo quan hệ thực thi phụ thuộc. Trong khi đó:

- `mustRunAfter` chỉ ràng buộc thứ tự **nếu cả hai task đã được đưa vào graph**, không tự lên lịch task còn thiếu.
- `shouldRunAfter` là ràng buộc thứ tự mềm hơn; không biến task thành gate.
- `finalizedBy` hữu ích để luôn chạy báo cáo/dọn dẹp sau một task trong những trường hợp phù hợp, nhưng **không thay thế chính sách `check.dependsOn(verificationTask)`**.
- `doLast { println("OK") }` không tự thêm một công cụ kiểm tra và cũng không định nghĩa ngưỡng đạt/chưa đạt.

## 4. Quality gate cần ba điều kiện cùng lúc

Một kiểm tra chỉ thực sự trở thành gate hữu ích khi:

1. **Có task thực hiện kiểm tra.** Ví dụ task Checkstyle có source code, config và classpath phù hợp; JaCoCo có dữ liệu được tạo từ test.
2. **Task phải được đưa vào task graph.** Qua plugin tự nối vào `check` hoặc `check.dependsOn(taskName)`.
3. **Kết quả không đạt phải làm build thất bại.** Không tắt lỗi bằng `ignoreFailures`, `onlyIf { false }` hoặc một action chỉ ghi log mà không báo failure.

Có thể có task mang tên “quality check” nhưng chạy không có input; Gradle hiển thị `NO-SOURCE`. Cũng có thể task trả mã thành công bất chấp violation vì cấu hình ignore-failures. Hai trường hợp đó không tương đương với một gate đã kiểm tra đúng.

### 4.1. Phân biệt ba dạng kết quả

| Trạng thái | Ý nghĩa | Có chứng minh chất lượng đạt không? |
| --- | --- | --- |
| `SUCCESS` | Task đã chạy xong không báo lỗi | Chỉ khi task kiểm tra đúng inputs/ruleset |
| `UP-TO-DATE` | Gradle nhận thấy output vẫn hợp lệ theo inputs/outputs đã khai báo | Có thể hợp lệ, nhưng phải có cấu hình inputs/rules đáng tin |
| `FROM-CACHE` | Output task được khôi phục từ cache | Hợp lệ theo điều kiện cache, không phải bằng chứng scan mới |
| `NO-SOURCE` | Task không có source thích hợp | Không chứng minh source thực đã được kiểm tra |
| `SKIPPED` | Task bị bỏ qua theo điều kiện | Phải điều tra nguyên nhân |
| `FAILED` | Task báo lỗi | Gate không đạt hoặc hạ tầng/configuration lỗi, phải phân loại |

Gradle cung cấp cơ chế up-to-date và build cache để tránh công việc thừa. Không nên mặc định `UP-TO-DATE` là lỗi; cũng không được mặc định `NO-SOURCE` nghĩa là “đã kiểm tra xong mà không có lỗi”.

## 5. Thực hành hoàn chỉnh: Java 17 + JUnit 5 + Checkstyle + JaCoCo

Ta sẽ xây một project Java 17 có thể chạy, với một quality gate cụ thể:

- Mã Java trong `src/main/java`.
- Unit test JUnit Jupiter trong `src/test/java`.
- Checkstyle kiểm tra nguồn main/test với ruleset tối giản.
- JaCoCo tạo HTML/XML coverage report và xác minh **line coverage tối thiểu 80%**.
- `check` được cấu hình để **bắt buộc** chạy coverage verification và tạo báo cáo.
- `build` sẽ bao gồm gate vì Java/Application plugin nối `build` đến `check`.

Thí nghiệm này dùng plugin tích hợp `application`, `checkstyle`, `jacoco` và tool artifacts từ Maven Central. Cần JDK 17/toolchain phù hợp, Gradle tương thích và mạng hoặc dependency cache đã có.

### 5.1. Cấu trúc thư mục

```text
quality-gate-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           ├── Calculator.java
    │           └── Main.java
    └── test/
        └── java/
            └── demo/
                └── CalculatorTest.java
```

Không cần tạo sẵn `build/`; Gradle sẽ sinh output khi các task chạy. Nếu dự án có Gradle Wrapper, nên sử dụng Wrapper của repo.

### 5.2. File settings

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "quality-gate-lab"
```

Một project đơn giản chỉ cần tên root. Không phải multi-project build để tập trung quan sát `check` của Java plugin.

### 5.3. Build script: gắn toàn bộ gate

**`build.gradle.kts`:**

```kotlin
plugins {
    application
    checkstyle
    jacoco
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
}

checkstyle {
    toolVersion = "10.21.4"
}

jacoco {
    toolVersion = "0.8.12"
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.test)
    violationRules {
        rule {
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.80".toBigDecimal()
            }
        }
    }
}

tasks.named("check") {
    dependsOn(
        tasks.jacocoTestReport,
        tasks.jacocoTestCoverageVerification
    )
}
```

Giải thích những phần quan trọng:

- `application` áp dụng khả năng Java và cung cấp task `run`.
- `checkstyle` tạo tasks kiểm tra Java source và tự nối vào `check`.
- `jacoco` gắn coverage agent cho test và tạo report/verification tasks; **coverage verification được nối thủ công**.
- `useJUnitPlatform()` chọn cách chạy JUnit 5, không tự thêm JUnit dependencies.
- `jacocoTestReport.dependsOn(test)` tránh yêu cầu báo cáo khi test chưa chạy.
- `jacocoTestCoverageVerification.dependsOn(test)` bảo đảm có dữ liệu execution của test trước khi đánh giá.
- `check.dependsOn(report, verification)` làm hai task thực sự được lên lịch khi dùng `check`.
- Ngưỡng `0.80` là **ví dụ cho toàn bộ module theo metric LINE COVEREDRATIO**, không phải quy tắc chung bắt buộc cho mọi dự án.

**Ghi chú thứ tự:** `jacocoTestReport` và `jacocoTestCoverageVerification` cùng phụ thuộc `test` nhưng không phụ thuộc vào nhau. Gradle không bắt buộc tạo xong report trước khi verification chạy. Nếu verification thất bại, report có thể đã tạo hoặc chưa, tùy cách thực thi. Khi cần thu thập nhiều lỗi và báo cáo hơn ở CI, xem `--continue` và cấu hình riêng cho báo cáo.

### 5.4. Config Checkstyle

**`config/checkstyle/checkstyle.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="LineLength">
        <property name="max" value="120"/>
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
        <module name="NeedBraces"/>
    </module>
</module>
```

Đây là một ruleset **đủ nhỏ để học cơ chế gate**, không phải một bộ quy tắc chất lượng doanh nghiệp hoàn chỉnh.

- `LineLength` báo dòng dài hơn 120 ký tự.
- `AvoidStarImport` báo các câu lệnh import dùng `*`.
- `NeedBraces` yêu cầu dùng ngoặc nhọn cho một số control-flow statements.
- Mặc định Checkstyle task có thể làm build fail khi có lỗi, trừ khi bạn cấu hình ignore-failures hoặc mức ngưỡng khác.

Checkstyle plugin thường tìm `checkstyle.xml` trong `config/checkstyle` ở root project. Khi muốn chạy trong multi-project, phải xác định rõ `configDirectory` hoặc vị trí ruleset phù hợp với từng project. Không dựa vào một thư mục được đoán khi project con có layout khác.

### 5.5. Code Java 17: lớp tính toán

**`src/main/java/demo/Calculator.java`:**

```java
package demo;

public final class Calculator {
    public int add(int first, int second) {
        return first + second;
    }
}
```

**`src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Calculator().add(2, 3));
    }
}
```

Kết quả của `Main.main` là số `5`. Đây là chương trình hoàn chỉnh, có thể chạy với Java 17; không có thư viện runtime bên ngoài.

### 5.6. JUnit Jupiter test kiểm tra cả logic và đường chạy ứng dụng

**`src/test/java/demo/CalculatorTest.java`:**

```java
package demo;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, new Calculator().add(2, 3));
    }

    @Test
    void mainPrintsFive() {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        PrintStream original = System.out;

        try (PrintStream capture =
                     new PrintStream(output, true, StandardCharsets.UTF_8)) {
            System.setOut(capture);
            Main.main(new String[0]);
        } finally {
            System.setOut(original);
        }

        assertEquals("5" + System.lineSeparator(),
                output.toString(StandardCharsets.UTF_8));
    }
}
```

Code kiểm thử có hai ý nghĩa:

1. `addsTwoNumbers` xác minh phương thức `Calculator.add`.
2. `mainPrintsFive` gọi ứng dụng rồi so sánh stdout mà chương trình tạo.

`System.out` là tài nguyên global; việc thay nó trong test cần hoàn trả trong `finally`. Ví dụ đơn giản chỉ có một test suite không chạy những test cùng sửa `System.out` song song. Trong dự án lớn, nên ưu tiên kiểm tra logic bằng unit tests không phụ thuộc global I/O hoặc kiểm soát chạy song song nếu có.

Checkstyle ruleset ở mục 5.4 chỉ yêu cầu các quy tắc tương đối nhẹ. Các import trong code không dùng wildcard, có ngoặc nhọn cho các khối cần thiết và không có dòng dài bất thường.

### 5.7. Chạy lệnh và kiểm chứng

Nếu repo đã có Gradle Wrapper, dùng nó. Nếu tạo thư mục mới từ các file trên nhưng **chưa có Wrapper**, máy cần một bản Gradle tương thích đã cài để chạy một lần:

```bash
gradle wrapper
```

Linux/macOS:

```bash
./gradlew --version
./gradlew --quiet run
./gradlew clean check --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat --quiet run
.\gradlew.bat clean check --console=plain
```

**Stdout do chương trình Java `Main` tạo ra:**

```text
5
```

Lệnh `check` thành công khi tests pass, Checkstyle chấp nhận source, coverage execution data đầy đủ và coverage verification đạt threshold. Không khẳng định toàn bộ log Gradle chỉ có dòng `5`: đó là stdout của `run`, trong khi lệnh `check` có các log task trạng thái riêng.

### 5.8. Tìm các task thực sự được lên lịch

Dùng:

```bash
./gradlew check --dry-run --console=plain
```

`--dry-run` cho biết kế hoạch task mà Gradle định chạy, nhưng **không thực hiện phép kiểm tra**. Nó hữu ích để thấy `test`, `checkstyleMain`, `checkstyleTest`, `jacocoTestReport`, `jacocoTestCoverageVerification` và `check` thuộc task graph.

Đừng dùng một kết quả `--dry-run` để chứng minh quality gate đã đạt. Để có kết quả thật, phải chạy `./gradlew check`.

### 5.9. Những báo cáo cần đọc

Với cấu hình Java/Test/Checkstyle/JaCoCo thông dụng, có thể xem:

| Báo cáo | Vị trí thường gặp |
| --- | --- |
| JUnit HTML | `build/reports/tests/test/index.html` |
| Checkstyle main | Dưới `build/reports/checkstyle/` |
| Checkstyle test | Dưới `build/reports/checkstyle/` |
| JaCoCo HTML | `build/reports/jacoco/test/html/index.html` |
| JaCoCo XML | Dưới `build/reports/jacoco/test/` |

Đường dẫn chính xác phụ thuộc các plugin và report settings; nếu build cấu hình `layout.buildDirectory` khác hoặc đổi report destination, dùng đường dẫn thực tế của task. Chỉ có report HTML **không chứng minh gate đã áp đặt threshold**: cần xem nhiệm vụ verification đã chạy và báo trạng thái đúng.

## 6. Thí nghiệm: khiến từng nhóm kiểm tra thất bại có chủ đích

Các bước sau thực hiện trên **bản sao** project hoặc một nhánh thử nghiệm, mỗi lần chỉ thay **một yếu tố** và khôi phục trước khi thử mục kế tiếp.

### 6.1. Khiến Checkstyle báo lỗi

Trong `src/main/java/demo/Calculator.java`, thêm một import dạng wildcard:

```java
package demo;

import java.util.*;

public final class Calculator {
    public int add(int first, int second) {
        return first + second;
    }
}
```

Mã Java này vẫn biên dịch được, nhưng `AvoidStarImport` từ Checkstyle sẽ báo violation. Lệnh:

```bash
./gradlew check --console=plain
```

dự kiến **thất bại ở `checkstyleMain`**, cho thấy việc build thành công về mặt cú pháp Java không đủ để đạt gate. Sau khi quan sát lỗi, hãy bỏ dòng import wildcard và khôi phục `Calculator.java`.

### 6.2. Khiến unit test thất bại

Trong test `addsTwoNumbers`, đổi expected từ `5` thành `99`:

```java
@Test
void addsTwoNumbers() {
    assertEquals(99, new Calculator().add(2, 3));
}
```

Đây là một **mảnh phương thức để thay**, không phải file Java độc lập. Task `test` sẽ báo assertion failure và vì Java plugin nối `test` vào `check`, quality gate thất bại.

Chạy:

```bash
./gradlew test --console=plain
./gradlew check --console=plain
```

Sửa lại expected thành `5` sau thí nghiệm.

### 6.3. Khiến coverage verification thất bại

Giữ unit tests chạy thành công, nhưng trong `build.gradle.kts` đổi ngưỡng JaCoCo từ `0.80` thành một giá trị lớn hơn khả năng đo được trên project. Ví dụ đặt `1.00` có thể khiến gate thất bại nếu source có dòng/constructor chưa được test; tuy nhiên nếu coverage thực sự đạt 100%, nó vẫn có thể pass.

Một cách **chắc chắn kiểm tra đường lỗi** là đặt threshold lớn hơn `1.00`, nhưng JaCoCo ratio phải nằm trong khoảng 0..1; giá trị sai phạm như vậy không phải một threshold hợp lệ. **Không dùng giá trị phi nghĩa để kiểm chứng sản phẩm.**

Phương án có ý nghĩa hơn:

1. Chỉ để lại `addsTwoNumbers`, tạm bỏ test `mainPrintsFive`.
2. Giữ threshold `0.80` (hoặc điều chỉnh một ngưỡng thực tế cao hơn coverage đo được).
3. Chạy `./gradlew clean check --console=plain`.
4. Quan sát `jacocoTestCoverageVerification` báo thiếu coverage nếu metric thực tế dưới threshold.
5. Mở report JaCoCo để xem những dòng/method nào chưa được chạy.
6. Khôi phục test `mainPrintsFive` và chạy lại gate.

Vì coverage còn tùy cách công cụ tính bytecode, **đừng hứa chỉ xóa một test chắc chắn đưa ratio xuống dưới 80%**. Hãy đọc ratio thật trước, chọn ngưỡng hợp lệ lớn hơn ratio để minh họa việc gate chặn, rồi đưa policy về giá trị đã thống nhất.

### 6.4. Vì sao `jacocoTestReport` thành công mà gate vẫn có thể không đạt?

`jacocoTestReport` chỉ tổng hợp dữ liệu và tạo báo cáo. Nếu coverage = 40%, task báo cáo vẫn có thể thành công vì nó không tự coi 40% là lỗi. Task `jacocoTestCoverageVerification` mới chứa `violationRules` và làm build thất bại khi tỷ lệ không đạt.

Bảng đối chiếu:

| Task | Vai trò | Nếu coverage thấp |
| --- | --- | --- |
| `test` | Chạy test và tạo execution data qua JaCoCo agent | Test có thể vẫn pass |
| `jacocoTestReport` | Tạo XML/HTML coverage report | Có thể vẫn pass |
| `jacocoTestCoverageVerification` | So sánh coverage với rules | Thất bại nếu vi phạm |
| `check` | Điểm tổng hợp verification | Thất bại nếu dependency gate bị fail |

**Kết luận:** đo lường không đồng nghĩa áp đặt quy tắc. Một quality gate cần cả **measurement** lẫn **enforcement**.

## 7. `dependsOn`, `mustRunAfter`, `finalizedBy`: sử dụng đúng

Sự khác biệt này đặc biệt quan trọng khi đội phát triển tự viết task kiểm tra.

| API | Điều gì được đảm bảo? | Có tự đưa task mới vào graph? | Dùng cho gate? |
| --- | --- | --- | --- |
| `dependsOn(task)` | Task phụ thuộc phải được chạy/giải quyết trước task hiện tại | **Có** | **Có** |
| `mustRunAfter(task)` | Nếu cả hai được lên lịch, thứ tự là bắt buộc | Không | Không đủ một mình |
| `shouldRunAfter(task)` | Tối ưu thứ tự khi phù hợp | Không | Không đủ |
| `finalizedBy(task)` | Đưa finalizer chạy sau task theo semantics của Gradle | Có, dưới dạng finalizer | Dùng cho cleanup/report, không thay gate |
| `doFirst/doLast` | Thêm action trong task đang chạy | Không thêm một task kiểm tra độc lập | Chỉ có ích nếu action thật sự verify và fail khi sai |
| `onlyIf` | Quyết định task có được thực hiện không | Không | Có thể vô tình làm bỏ qua gate |

**Sai lầm thường gặp:**

```kotlin
tasks.named("jacocoTestCoverageVerification") {
    mustRunAfter(tasks.named("test"))
}
```

Đoạn trên **không khiến `test` tự chạy** khi gọi `jacocoTestCoverageVerification`. Để tạo quan hệ producer–consumer cho coverage data, dùng `dependsOn(tasks.named("test"))`, như ví dụ chính.

### 7.1. Không biến `check` thành task “in kết luận”

Ví dụ không đủ:

```kotlin
tasks.named("check") {
    doLast {
        println("All checks passed")
    }
}
```

Dòng log chỉ in ra khi task chạy tới action, nhưng không xác nhận test/coverage/analysis thực sự tồn tại hoặc đủ input. Nếu nhiệm vụ kiểm tra không được khai báo, gate có thể “xanh” giả.

Muốn tóm tắt gate, có thể tạo báo cáo theo kết quả các task thật; tuy nhiên CI nên dựa vào **exit code của lệnh Gradle** và artifacts/reports, không đọc chuỗi “All checks passed” rồi tự suy ra build đạt.

### 7.2. Thêm một task verification tự viết

Nếu tổ chức có quy tắc cụ thể không có trong plugin, có thể tạo task riêng rồi nối vào `check`. Ví dụ demo **chỉ kiểm tra sự tồn tại của file hướng dẫn**:

```kotlin
val verifyReadme by tasks.registering {
    group = "verification"
    description = "Require a README.md in the root project"

    val readme = layout.projectDirectory.file("README.md")
    inputs.file(readme)

    doLast {
        check(readme.asFile.isFile) {
            "README.md is required"
        }
    }
}

tasks.named("check") {
    dependsOn(verifyReadme)
}
```

Đoạn này là **mảnh cấu hình riêng**, chỉ nên áp dụng nếu project thật có chính sách bắt buộc README. Nếu mục đích là kiểm tra file thiếu, `inputs.file(readme)` có thể bị Gradle validation báo lỗi trước khi action chạy khi input file không tồn tại; khi thiết kế task chuẩn nên dùng input tùy chọn hay logic kiểm tra tồn tại phù hợp. Điều quan trọng là task custom phải có **input semantics** đúng, fail rõ khi vi phạm và được nối vào `check`.

Với rule phức tạp hoặc nhiều project, nên viết custom task type có input/output annotations thay vì nhồi logic kiểm tra vào anonymous `doLast`. Đây là một ví dụ để hiểu wiring, không phải plugin hoàn chỉnh để dùng trong production.

## 8. Cách nối các công cụ khác vào `check`

Không phải mọi plugin có cùng cơ chế wiring.

### 8.1. PMD (plugin tích hợp)

Gradle có plugin `pmd` cho phân tích tĩnh Java. Khi áp dụng cùng Java plugin:

```kotlin
plugins {
    java
    pmd
}
```

Gradle tạo task PMD cho source sets và có cơ chế nối các kiểm tra của plugin vào `check` theo mô hình verification. Nhưng PMD cần tool version/ruleset phù hợp. Không nên suy luận “đã có `pmd` tức mọi loại lỗi đã được phát hiện”. Một bộ ruleset quá ít hoặc nguồn không khớp vẫn có thể cho kết quả trống.

### 8.2. SpotBugs (plugin bên ngoài)

Một plugin bên ngoài như SpotBugs có thể tạo tasks `spotbugsMain`/`spotbugsTest`, nhưng cơ chế auto-wiring, version và cấu hình báo lỗi có thể khác theo plugin/release.

Ví dụ **mảnh cấu hình chỉ khi plugin đã được áp dụng và task đã tồn tại**:

```kotlin
tasks.named("check") {
    dependsOn(tasks.named("spotbugsMain"))
}
```

Không dán đoạn này vào ví dụ chính khi chưa áp dụng plugin SpotBugs; Gradle sẽ báo task không tồn tại. Hãy đọc tài liệu của **đúng phiên bản plugin** để xác định có cần wiring thủ công hay không.

### 8.3. Formatter: kiểm tra thay vì tự sửa mã

Nhiều formatter cung cấp hai nhóm task:

- `format`/`apply`: thay đổi source.
- `formatCheck`/`check`: xác nhận source có đúng định dạng hay không.

Một CI gate tốt nên **kiểm tra** và fail nếu không đúng, thay vì âm thầm sửa code checkout rồi trả “pass”. Ví dụ khái niệm:

```kotlin
tasks.named("check") {
    dependsOn(tasks.named("formatCheck"))
}
```

Task `formatCheck` chỉ là tên giả định cho một plugin cụ thể; không có sẵn trong Gradle Java plugin. Hãy dùng đúng tên task mà plugin đã đăng ký, ví dụ `spotlessCheck` nếu đang dùng Spotless và tài liệu phiên bản phù hợp.

### 8.4. Security/dependency scans

Một security scanner có thể nhận dữ liệu từ database CVE, policy máy chủ hoặc repository bên ngoài. Nếu task scan được nối vào `check`:

- Cần xác định thế nào là severity làm build fail.
- Cần kiểm soát ngoại lệ đã được review, có hạn sử dụng.
- Cần phân biệt “scan thất bại do hạ tầng” và “scan hoàn tất, tìm thấy lỗ hổng”.
- Cần bảo vệ token/credential của scanner, không đưa vào logs/reports công khai.
- Cần xem xét chế độ offline/CI khi dịch vụ scan không khả dụng.

Không nên đồng nhất việc có “một plugin security” với việc pipeline đã bảo vệ đầy đủ software supply chain.

## 9. Tổ chức gate trong multi-project build

Một hệ thống thực tế có thể có:

```text
root
├── :core             (java-library)
├── :service          (application)
├── :adapter-http     (java-library)
├── :test-fixtures    (test helpers)
└── :platform         (java-platform)
```

Mỗi Java project có task `:module:check` riêng. Nếu muốn chạy toàn bộ verification của những project đã áp dụng Java plugin, có thể gọi:

```bash
./gradlew check
```

Tuy nhiên, cần hiểu task selection của Gradle trong multi-project và cấu trúc project thực tế; việc có `check` ở root hay không, các task cùng tên được chọn như thế nào và plugin nào được áp dụng phụ thuộc model build. Lệnh chính xác và ổn định nhất cho một project cụ thể là:

```bash
./gradlew :core:check
./gradlew :service:check
```

Để tạo một **aggregate gate tường minh**, ở root có thể đăng ký task:

```kotlin
tasks.register("qualityGate") {
    group = "verification"
    description = "Run checks for the main JVM subprojects"

    dependsOn(
        ":core:check",
        ":service:check",
        ":adapter-http:check"
    )
}
```

Đây là ví dụ **chỉ hợp lệ khi những project/task paths đó thực sự tồn tại**, không phải mảnh cần dán vào bài lab một project. Trong tổ chức lớn, một convention plugin dùng chung giúp các Java modules có cùng policy mà không phải copy từng khối Checkstyle/JaCoCo.

### 9.1. Convention plugin cho Java quality policy

Một team có thể tạo plugin `company.java-quality`, bên trong:

1. Áp dụng Java/Checkstyle/JaCoCo theo ngữ cảnh thích hợp.
2. Thiết lập version Checkstyle/JaCoCo và rulesets đã được review.
3. Cấu hình JUnit Platform khi project dùng JUnit 5.
4. Tạo/nối coverage verification vào `check` theo chính sách.
5. Thêm report formats CI cần.
6. Có cơ chế ngoại lệ minh bạch cho module đặc biệt.
7. Hạn chế cấu hình không phù hợp với platform projects hoặc project không có Java.

Lưu ý việc gom toàn bộ policy vào root `subprojects { ... }` có thể tăng coupling và phụ thuộc thứ tự cấu hình. Convention plugin thường dễ bảo trì hơn khi hệ thống lớn, nhưng không nhất thiết phải tạo plugin phức tạp chỉ cho một project.

### 9.2. Module khác nhau có ngưỡng khác nhau

Có thể quy định:

- Thư viện lõi: line coverage cao hơn vì logic quan trọng.
- Application shell: cần test tích hợp và kiểm tra hành vi ngoài đơn vị.
- Generated code: exclude hợp lý khỏi metric nếu phù hợp policy và có bằng chứng.
- API contract modules: ưu tiên compatibility tests và schema checks.
- Platform BOM project: không có Java source, nên không cần Checkstyle/JaCoCo theo cùng kiểu.

Một số chính sách nên thống nhất cho cả tổ chức; một số chỉ cần áp dụng cho project thích hợp. **Không ép mọi project dùng một ngưỡng coverage mà không quan tâm vai trò/độ phức tạp.**

## 10. Quality gate trong CI: từ PR đến merge và release

Mô hình workflow:

```text
Pull request
    |
    v
Checkout + Gradle Wrapper
    |
    v
Restore dependency cache / provision JDK 17
    |
    v
./gradlew clean check --console=plain
    |
    +-- FAIL --> ghi nhận status đỏ, lưu reports, chặn merge
    |
    +-- PASS --> có thể chạy integration/contract/security checks
                    |
                    v
              policy review / approval
                    |
                    v
                cho phép merge
                    |
                    v
              build/publish/deploy theo pipeline
```

Quality gate nên là **required check** theo chính sách repository: nếu job không đạt, pull request chưa được merge. Chỉ viết `./gradlew check` trong README nhưng không cấu hình CI branch protection thì mới là hướng dẫn, chưa phải cơ chế cưỡng chế trong quy trình cộng tác.

### 10.1. Ví dụ pipeline shell tối giản

```bash
set -e
./gradlew --version
./gradlew clean check --console=plain
```

`set -e` phù hợp với shell POSIX trong ví dụ này; nó không phải cú pháp PowerShell. CI runner cần JDK/toolchain, Gradle Wrapper và dependencies có thể resolve. Mã thoát của `./gradlew check` là tín hiệu quan trọng để CI đánh dấu thất bại.

Nếu dùng một nền tảng CI cụ thể (GitHub Actions, GitLab, Jenkins, Azure Pipelines), còn cần khai báo checkout, JDK setup, caching, artifact upload, merge policy và credentials theo nền tảng. Không nên phát minh một YAML “chạy ở mọi CI” mà không chỉ rõ hệ thống.

### 10.2. Dùng `--continue` để thu thập thêm lỗi

Mặc định, khi một task fail, Gradle có thể dừng việc thực thi các task phụ thuộc và không chạy tiếp một số công việc. Để cố gắng chạy những task còn độc lập và thu thập nhiều kết quả:

```bash
./gradlew check --continue --console=plain
```

`--continue` không biến một build lỗi thành thành công. Nó cho Gradle tiếp tục những task **có thể chạy độc lập** rồi báo các failure được phát hiện. Những task phụ thuộc trực tiếp vào task đã lỗi vẫn có thể bị bỏ qua. Vì vậy đừng hứa sẽ có đầy đủ mọi report trong mọi lần fail.

### 10.3. Lưu report cả khi job thất bại

Với CI, nên lưu:

- JUnit HTML/XML test results.
- Checkstyle XML/HTML hoặc SARIF khi đã cấu hình.
- JaCoCo HTML/XML.
- Các báo cáo SpotBugs/PMD/security scanner nếu project sử dụng.
- Thông tin Gradle Wrapper/JDK và task failure có liên quan.

Artifact upload step cần cấu hình chạy **kể cả khi `check` fail**, theo cú pháp của CI nền tảng. Tránh ghi credential, token, secret vào reports hoặc artifact logs.

## 11. Thiết kế ngưỡng và chính sách gate đáng tin

Một threshold coverage không phải số “càng cao càng đúng” trong mọi dự án. Ví dụ gate 80% line coverage có thể có ích như tín hiệu tối thiểu, nhưng:

- Coverage cao không chứng minh assertion có chất lượng.
- Một test chạy code nhưng không kiểm tra output vẫn có thể tăng coverage.
- Branch coverage khác line coverage.
- Unit coverage chưa thay thế integration/contract/end-to-end tests.
- Code sinh tự động có thể cần chính sách đo khác code viết tay.
- Một class quan trọng ở 0% có thể bị che bởi cả module 90%.

**Chọn metric rõ ràng.** JaCoCo có thể đo INSTRUCTION, BRANCH, LINE, METHOD, CLASS và nhiều loại counter; `value = "COVEREDRATIO"` là ratio 0..1, không phải số phần trăm 80. Một gate toàn module nên được bổ sung bằng kiểm tra các vùng rủi ro cao nếu phù hợp.

### 11.1. Phân biệt “module đạt 80%” với “mọi class đạt 80%”

Trong JaCoCo, rule mặc định thường áp dụng ở mức `BUNDLE`. Khi chỉ khai báo:

```kotlin
violationRules {
    rule {
        limit {
            counter = "LINE"
            value = "COVEREDRATIO"
            minimum = "0.80".toBigDecimal()
        }
    }
}
```

ý định là threshold coverage cho phạm vi bundle/module theo rule. Nếu cần mỗi class đáp ứng ngưỡng riêng, có thể dùng:

```kotlin
violationRules {
    rule {
        element = "CLASS"
        limit {
            counter = "LINE"
            value = "COVEREDRATIO"
            minimum = "0.80".toBigDecimal()
        }
    }
}
```

Đoạn này là **phương án thay thế**, không tự thêm vào project lab nếu muốn giữ threshold module. Thực tế có thể cần loại trừ generated classes một cách minh bạch, hoặc có ngưỡng phù hợp theo module.

### 11.2. Khi chuyển từ chưa có gate sang gate nghiêm ngặt

Một codebase lớn có thể đang có nhiều vi phạm. Nếu đưa ngưỡng cao vào ngay mà không có kế hoạch, CI sẽ đỏ liên tục và nhóm dễ bị cám dỗ tắt gate.

Một lộ trình có thể là:

1. Đo baseline hiện tại bằng report có thể kiểm chứng.
2. Xác định rule lỗi nghiêm trọng cần chặn ngay.
3. Phân loại vi phạm có thể sửa tự động và vi phạm cần refactor.
4. Đặt policy tối thiểu khả thi, rõ phạm vi và người chịu trách nhiệm.
5. Tăng threshold có kế hoạch, theo dõi không để chất lượng giảm trở lại.
6. Duy trì ngoại lệ có lý do, reviewer và thời hạn.
7. Không biến mọi warning thành blocker nếu không có giá trị hoặc gây quá nhiều false positives.

Nếu team chọn chính sách “không giảm coverage ở code mới”, cần công cụ đo trên changed lines và baseline so sánh phù hợp. **JaCoCo plugin cơ bản không tự cung cấp khái niệm changed-line coverage trong `check`**; cần pipeline hoặc công cụ bổ sung và dữ liệu so sánh đáng tin.

### 11.3. Tránh làm giả kết quả đạt

Một số anti-pattern:

```kotlin
// KHÔNG LÀM trong quality gate bắt buộc:
tasks.withType<org.gradle.api.plugins.quality.Checkstyle>().configureEach {
    isIgnoreFailures = true
}
```

`isIgnoreFailures = true` có thể cho phép Checkstyle task hoàn thành thành công dù có violations. Có thể hữu ích tạm thời trong giai đoạn quan sát, nhưng **không phù hợp khi team đang tuyên bố Checkstyle là điều kiện bắt buộc**.

Tương tự, `onlyIf { false }` hoặc `enabled = false` trên verification task làm nó không chạy; CI xanh sau đó không chứng minh policy đã được kiểm tra. Nếu cần ngoại lệ, hãy ghi rõ phạm vi và điều kiện thay vì âm thầm vô hiệu hóa.

## 12. Các quan hệ task graph cần kiểm tra

### 12.1. `dependsOn` của `check` có thể được plugin khác bổ sung

Một plugin có thể tự gọi:

```kotlin
tasks.named("check") {
    dependsOn(tasks.named("customLint"))
}
```

Nếu task `customLint` được plugin đó đăng ký, đây là wiring hợp lệ. Nhưng khi project chưa có plugin/task, `tasks.named("customLint")` sẽ báo lỗi configuration. Không nên copy mảnh code từ tài liệu của một plugin khác khi chưa áp dụng nó.

### 12.2. `test.finalizedBy(report)` không phải policy coverage

Có thể viết:

```kotlin
tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}
```

Khi `test` được đưa vào graph, report là finalizer và được lên lịch theo semantics tương ứng. Đây là cách tạo báo cáo hữu ích **sau** test, kể cả trong một số tình huống test fail. Nhưng **không tự áp đặt tỷ lệ coverage** và không làm `jacocoTestCoverageVerification` thành dependency của `check`.

Nếu bắt buộc coverage threshold, luôn xem rule và connection của verification task.

### 12.3. Không nhầm `dependsOn` với artifact input/output

Một task kiểm tra chất lượng có thể cần class files, test execution data, ruleset và source directories. Khai báo `dependsOn` chỉ đảm bảo các task liên quan được đưa vào graph và có thứ tự phụ thuộc; nó không tự biến một tập file bất kỳ thành **input/output được khai báo chính xác**.

Với task custom phức tạp, dùng typed properties và input/output annotations để Gradle theo dõi cache/up-to-date đúng. Đừng viết một task gọi công cụ qua shell mà không khai báo file đầu vào, rồi coi build cache chính xác.

## 13. Tốc độ, cache và việc chạy gate trong developer workflow

Một quality gate quá chậm có thể khiến developer ít chạy hơn; một gate quá nhẹ có thể bỏ sót vấn đề. Cân bằng bằng cách:

- Chạy unit tests + static checks nhanh trong `check` cục bộ và PR.
- Tách integration/end-to-end tests dài sang một nhóm task hoặc job riêng nếu thật sự tốn thời gian.
- Có job comprehensive cho release hoặc merge vào nhánh quan trọng.
- Sử dụng Gradle parallel execution, build cache và configuration cache khi plugin/tasks tương thích.
- Chỉ áp dụng công cụ cho project/source set liên quan.
- Tránh tải nhiều plugin scan giống chức năng mà không có giá trị thêm.

**Không dùng `--offline` để “tăng tốc gate” nếu plugin cần dữ liệu cập nhật** như security advisories. Nếu repository/cache không có artifact, offline build có thể fail do hạ tầng, chứ không phải code quality.

### 13.1. `--rerun-tasks` và việc tin vào kết quả

```bash
./gradlew check --rerun-tasks --console=plain
```

Tùy chọn này yêu cầu chạy lại các task thay vì dựa vào up-to-date checks thông thường; có thể hữu ích khi điều tra đầu vào không được theo dõi. Nó không sửa sai ruleset, không tự thêm task bị thiếu và không chứng minh mọi report độc lập đều hợp lệ.

### 13.2. Cache hit không thay thế tính đúng đắn của task

Nếu Checkstyle/JaCoCo task hoặc custom analysis dùng cache, Gradle cần biết inputs như source, tool version, ruleset và execution data. Khi plugin hoặc task khai báo không đúng, cache có thể tái sử dụng kết quả không phù hợp.

Đó là lý do nên dùng plugin/task APIs chuẩn, pinned tool versions và cấu hình rõ thay vì một `Exec` task chạy script tùy ý không có inputs/outputs.

## 14. Chẩn đoán lỗi khi `check` không chạy công cụ như dự kiến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Task 'check' not found` | Project không áp dụng plugin Java/base/verification phù hợp | Kiểm tra plugins và `tasks --all` |
| `check` chạy nhưng không thấy `test` | Task graph chưa nối test hoặc target project khác | Kiểm tra `check --dry-run` và project path |
| Checkstyle chạy `NO-SOURCE` | Source set không có Java file hoặc path sai | Kiểm tra `src/main/java` và `src/test/java` |
| Checkstyle không thấy ruleset | `config/checkstyle/checkstyle.xml` sai vị trí/không hợp lệ | Kiểm tra `configDirectory` và XML |
| Checkstyle báo vi phạm nhưng `check` xanh | Có `ignoreFailures` hoặc task không nối đúng | Đọc Checkstyle config và task graph |
| `jacocoTestReport` chạy nhưng không có data | Test chưa chạy hoặc JaCoCo agent không được gắn | Đặt `dependsOn(test)`, kiểm tra `build/jacoco` |
| Coverage report 40% nhưng gate xanh | Chỉ có report, chưa có verification trong `check` | Thêm `check.dependsOn(jacocoTestCoverageVerification)` |
| Verification chạy trước test | Thiếu dependency cụ thể | Thêm `verification.dependsOn(test)` |
| `mustRunAfter(test)` nhưng test không chạy | Ordering không tự đưa task vào graph | Dùng `dependsOn(test)` |
| JaCoCo kiểm tra sai module | Task default chỉ lấy data/source của suite cấu hình | Kiểm tra executionData/sourceSets và aggregation |
| CI xanh dù test có lỗi | Test task bị skip/ignoreFailures hoặc CI bỏ qua exit code | Kiểm tra task config và required job |
| `./gradlew assemble` xanh, `check` đỏ | Compile/package không có nghĩa chất lượng đạt | Chặn merge/release theo `check` |
| JUnit test báo `No tests found` | Engine/dependency/platform hoặc path/class naming sai | Kiểm tra JUnit deps và `useJUnitPlatform()` |
| `test` chạy trên JVM khác yêu cầu | Toolchain/test launcher chưa cấu hình | Kiểm tra `javaToolchains` và test Java launcher |
| SpotBugs task not found | Plugin chưa áp dụng hoặc tên task khác | Chạy `tasks --all` và xem docs đúng version |
| Checkstyle version báo lỗi Java class | Tool Checkstyle yêu cầu JDK tương thích | Đối chiếu Checkstyle tool version và Gradle/JDK toolchain |
| Build lâu bất thường | Task scan phạm vi quá rộng, thiếu cache, chạy nhiều kiểm tra nặng | Profile tasks và tối ưu có kiểm chứng |
| CI không lưu được report sau fail | Artifact upload chỉ chạy khi job thành công | Cấu hình upload step có điều kiện always |
| Coverage 80% nhưng bug vẫn lọt | Coverage chỉ đo code được chạy, không bảo đảm test đúng | Viết assertions, edge cases và integration tests |

### 14.1. Quy trình debug nhanh

1. Chạy `./gradlew tasks --all` để xác nhận task tồn tại.
2. Chạy `./gradlew check --dry-run` để xem tasks nào được lên lịch.
3. Kiểm tra source locations và Checkstyle ruleset path.
4. Chạy từng task: `test`, `checkstyleMain`, `checkstyleTest`, `jacocoTestReport`, `jacocoTestCoverageVerification`.
5. Đọc stacktrace/report thật khi có failure.
6. Kiểm tra `ignoreFailures`, `onlyIf`, `enabled` và các rules có hiệu lực.
7. Chạy `check` thật, không chỉ `--dry-run`.
8. Trên CI, xác minh **exit code** và việc job quality là required check.

## 15. Cần phân biệt lỗi chất lượng với lỗi hạ tầng

Quality gate có thể không hoàn thành do nhiều lý do:

- Test assertion thật sự sai.
- Checkstyle tìm thấy violation thật.
- JaCoCo coverage dưới threshold.
- Maven Central hoặc proxy không thể tải JUnit/Checkstyle/JaCoCo.
- JDK 17 toolchain chưa được cung cấp.
- CI hết bộ nhớ, runner bị hủy hoặc file system lỗi.
- Security scanner không kết nối dịch vụ metadata.
- Plugin không tương thích phiên bản Gradle đang chạy.

Với lỗi nhóm đầu, cần sửa code/test/policy theo quy trình. Với lỗi môi trường, cần sửa hạ tầng/configuration; **không tắt gate chỉ để job xanh**.

Một build không hoàn thành vì infrastructure vẫn phải được nhìn nhận là **chưa đạt điều kiện để merge**, dù không chứng minh code kém chất lượng. CI nên có nhãn/phân loại lỗi để người xử lý không phải đoán.

## 16. Khi nào nên chạy `check` ở local, PR và release?

| Giai đoạn | Mục tiêu | Gate phù hợp |
| --- | --- | --- |
| Developer đang sửa code | Phản hồi nhanh | Unit tests và static checks liên quan |
| Trước push | Phát hiện vi phạm cơ bản | `./gradlew check` khi đủ nhanh |
| PR validation | Điều kiện merge được cưỡng chế | `check` + các job bắt buộc khác |
| Merge vào nhánh chính | Bảo vệ integration | Gates toàn repo hoặc affected modules đáng tin |
| Release | Chất lượng sản phẩm/phát hành | `build` + integration/security/compatibility checks |
| Production deploy | Bảo vệ vận hành | Approval, artifact provenance, rollout checks, monitor |

Không phải mọi phép thử đều phải nằm vào **một** task `check` duy nhất. Ví dụ integration test cần database/container thật có thể là một job riêng, vẫn được CI yêu cầu trước merge hoặc release. Quality gate cấp tổ chức là **tập điều kiện**, còn `check` là điểm vào chuẩn cho những verification tasks trong Gradle project.

## 17. Các nhầm lẫn về `check` cần tránh

### 17.1. “Tôi đã cài JaCoCo nên `check` tự chặn coverage thấp”

Không. JaCoCo tạo coverage data/report/verification task, nhưng **`jacocoTestCoverageVerification` không tự được `check` phụ thuộc**. Cần thêm rule ngưỡng và wiring rõ.

### 17.2. “Có báo cáo HTML thì là quality gate”

Không. HTML là một artifact để đọc. Nó không tự khiến CI fail nếu vượt ngưỡng. Task verification hoặc chính sách CI phải biến kết quả thành trạng thái đạt/chưa đạt.

### 17.3. “Chỉ cần `mustRunAfter` là đủ”

Không. `mustRunAfter` không lập lịch task. Nếu `check` không phụ thuộc task, task có thể không chạy.

### 17.4. “`check` xanh thì mã không có bug”

Không. `check` chỉ chứng minh các quy tắc **được cấu hình và thực thi** đã không báo lỗi trong phạm vi được kiểm tra. Một test suite nhỏ, ruleset hẹp hoặc coverage thấp vẫn có thể để lọt bug.

### 17.5. “Chạy `build` không cần quan tâm `check`”

Java `build` thường phụ thuộc `check` và `assemble`, nhưng nếu build script tùy chỉnh thay đổi task graph hoặc một plugin không nối công cụ vào `check`, việc chạy `build` vẫn không đảm bảo mọi scan khác trong tổ chức được thực hiện. Hãy kiểm tra task graph thực tế.

### 17.6. “Tắt `ignoreFailures` ở mọi nơi là đủ”

Không. Một công cụ có thể chạy `NO-SOURCE`, thiếu rule, không có data hoặc không được nối vào task graph. Policy phải kiểm tra cả **sự hiện diện và chất lượng inputs**.

## 18. Checklist đưa một công cụ mới vào quality gate

Khi team muốn thêm một scanner/linter/plugin mới, nên trả lời:

1. Công cụ giải quyết loại lỗi nào mà các công cụ hiện có chưa giải quyết?
2. Phiên bản plugin/tool đã được cố định, tương thích Gradle Wrapper và Java toolchain chưa?
3. Rule config nằm ở đâu, được review bằng PR không?
4. Task kiểm tra tên chính xác là gì? Có thực sự được tạo ở project cần áp dụng không?
5. Task có tự nối vào `check` không? Nếu không, đã viết `dependsOn` chưa?
6. Task có đủ inputs (source, bytecode, metadata, test results) chưa?
7. Nếu một rule bị vi phạm, task có thực sự fail build không?
8. Nếu inputs không có, task có `NO-SOURCE`, có cần coi đó là lỗi policy?
9. Kết quả/report sẽ được lưu ở đâu, ai có quyền xem?
10. CI có chặn merge khi task quality đỏ không?
11. Có kế hoạch triage false positives/ngoại lệ có hạn dùng không?
12. Tác động hiệu năng có chấp nhận được không?
13. Công cụ có cần network hoặc secret? Chúng được cấp an toàn chưa?
14. Có test ví dụ cố tình vi phạm để chứng minh gate đang thật sự hoạt động không?
15. Đã chạy trên CI sạch, không chỉ laptop có cache chưa?

Một gate tốt không phải danh sách plugin thật dài. Nó là **bộ điều kiện đo được, được thực thi, có chủ sở hữu và có cách xử lý khi không đạt**.

## 19. Bài tập tự thực hành

**Bài tập A — phân biệt lifecycle tasks.** Trong project mục 5, chạy `assemble`, `check` và `build`. Quan sát task graph và giải thích vì sao một build có thể đóng gói JAR nhưng vẫn không đủ điều kiện chất lượng.

**Bài tập B — xem wiring.** Chạy `./gradlew check --dry-run`. Liệt kê những task do Java plugin, Checkstyle plugin và JaCoCo plugin tạo. Đâu là task được tự nối và đâu là task phải nối thủ công?

**Bài tập C — xung đột Checkstyle.** Thêm import wildcard vào `Calculator.java` rồi chạy `check`. Task nào fail? Sửa lại mã và chạy lại.

**Bài tập D — test failure.** Đổi expected `5` thành `99` trong `CalculatorTest`. Vì sao `test` fail làm `check` fail? Báo cáo JUnit nằm ở đâu?

**Bài tập E — coverage threshold.** Chạy `jacocoTestReport`, đọc line coverage hiện tại, rồi tăng ngưỡng hợp lệ lên mức cao hơn tỷ lệ đo được. Tại sao chỉ có report HTML không đủ để chặn merge?

**Bài tập F — bỏ wiring.** Tạm xóa `check.dependsOn(jacocoTestCoverageVerification)` nhưng giữ rule `violationRules`. Khi chạy `check`, điều gì xảy ra với coverage gate? Khôi phục wiring.

**Bài tập G — `mustRunAfter` vs `dependsOn`.** Đổi `verification.dependsOn(test)` thành `verification.mustRunAfter(test)` trên bản sao, rồi chạy riêng task verification trong môi trường sạch. Vì sao thứ tự không tự thêm test vào graph?

**Bài tập H — thêm custom task.** Tạo một task `verifyProjectMetadata` kiểm tra một file metadata đã định nghĩa trước và được nối vào `check`. Nếu file thiếu, task cần báo failure có ý nghĩa như thế nào?

**Bài tập I — multi-project.** Có `:core`, `:service`, `:adapter-http`. Hãy thiết kế `:qualityGate` tại root phụ thuộc các `:module:check`, và giải thích trường hợp nào nên dùng convention plugin để thống nhất rulesets.

**Bài tập J — CI report retention.** Thiết kế pipeline shell/CI trong đó `./gradlew clean check` là điều kiện merge, các báo cáo HTML/XML vẫn được upload nếu build fail và token không xuất hiện trong logs.

**Bài tập K — coverage không phải correctness.** Một test gọi method rồi không assert gì vẫn tăng coverage. Hãy viết assertion kiểm tra edge cases để chỉ ra vì sao metric coverage cần đi cùng test quality.

**Bài tập L — false positive và ngoại lệ.** Một Checkstyle rule gây nhiều cảnh báo không có giá trị trong generated sources. Hãy đề xuất cách giới hạn chính sách, ghi lý do loại trừ, reviewer và thời hạn thay vì tắt tất cả.

### Câu hỏi tự kiểm tra

1. Quality gate khác một task `compileJava` như thế nào?
2. Task `check` phục vụ mục đích gì trong Java project?
3. `assemble` có tự bảo đảm unit tests đạt không?
4. `build` thường liên quan `assemble` và `check` ra sao?
5. Gradle Checkstyle plugin có nối `checkstyleMain` và `checkstyleTest` vào `check` không?
6. `jacocoTestCoverageVerification` có tự được `check` chạy khi chỉ áp dụng `jacoco` không?
7. `jacocoTestReport` khác `jacocoTestCoverageVerification` như thế nào?
8. Vì sao `dependsOn` quan trọng hơn `mustRunAfter` cho việc lập lịch quality gate?
9. Khi verification cần test execution data, quan hệ dependency nào nên được khai báo?
10. Tại sao một task `NO-SOURCE` chưa chứng minh nguồn Java đã được phân tích?
11. `ignoreFailures` tác động kết quả quality gate như thế nào?
12. Line coverage 80% có bảo đảm mọi business rule được test đúng không?
13. `counter = "LINE"` và `value = "COVEREDRATIO"` có nghĩa gì?
14. Nếu muốn từng class đạt ngưỡng thay vì toàn module, cần thay đổi loại rule nào?
15. Vì sao không nên tự chạy formatter `apply` như một gate sửa code âm thầm?
16. Làm sao kiểm tra task nào được `check` lên lịch mà chưa chạy chúng?
17. Khi Checkstyle fail và JaCoCo report chưa được tạo, `--continue` giúp gì, có giới hạn gì?
18. Trong multi-project, vì sao `:core:check` khác `:service:check`?
19. Tại sao CI cần dùng exit code của Gradle thay vì đọc dòng “quality passed” tự in?
20. Khi security scanner lỗi mạng, có nên đánh dấu chất lượng mã đạt không? Vì sao?
21. Convention plugin giúp tổ chức quality policy qua nhiều module như thế nào?
22. Tại sao ruleset, tool versions và report outputs nên được quản lý bằng version control?
23. Sự khác biệt giữa `UP-TO-DATE` và một task hoàn toàn không được lên lịch là gì?
24. Khi nào nên tách integration/security gate ra job khác nhưng vẫn bắt buộc trước merge?

**Tài liệu chính thức:** [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html), [Gradle — Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html), [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html), [Gradle — Task Dependencies](https://docs.gradle.org/current/userguide/controlling_task_execution.html), [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/).

**Ghi nhớ:** `check` là **điểm tổng hợp verification** của Java build, không tự động phát hiện mọi công cụ bạn mong muốn. Checkstyle plugin tự nối các task chuẩn vào `check`, còn JaCoCo coverage verification phải được cấu hình ngưỡng và nối bằng `dependsOn`. Một quality gate đáng tin cần **task thực thi thật + input/ruleset hợp lệ + failure propagation + chính sách CI chặn merge**; reports và coverage metrics chỉ là dữ liệu hỗ trợ quyết định.