# Lưu test report, coverage, log và artifact để chẩn đoán trong Gradle CI/CD

## 1. Vì sao CI thất bại nhưng lại không có bằng chứng?

Hãy tưởng tượng pipeline GitHub Actions/GitLab CI hiển thị một dòng:

~~~text
> Task :test FAILED
~~~

Developer muốn biết test nào lỗi, assertion expected/actual ra sao, lỗi chỉ xuất hiện trên Java 17 hay trên CI Linux, và JaCoCo đã đo được coverage đến mức nào. Nhưng job kết thúc với exit code khác 0 rồi runner dọn workspace; thư mục `build/reports` không còn truy cập được. Việc chạy lại trên máy cá nhân có thể không tái hiện lỗi.

**Một CI pipeline đáng tin phải làm hai việc song song:**

1. **Báo trạng thái đúng**: test/coverage/build thất bại thì job phải báo thất bại, không nuốt exit code.
2. **Giữ chứng cứ phù hợp**: lưu JUnit XML, HTML test report, JaCoCo XML/HTML/exec, Gradle console log và artifact build vào hệ thống artifacts có kiểm soát, **kể cả khi job fail**.

Các artifacts này phục vụ chẩn đoán, đối chiếu lịch sử, báo cáo merge request, audit release và phối hợp giữa developer, QA, SRE. Chúng **không phải** cùng một thứ với Gradle Build Cache và không nên được giữ mãi nếu chứa dữ liệu nhạy cảm.

Bài thuộc chủ đề **Tích hợp CI/CD** của module **Build Tool Gradle**. Ví dụ sử dụng Java 17, Gradle Kotlin DSL, JUnit Jupiter, JaCoCo, và cấu hình thực hành cho GitHub Actions, GitLab CI, Jenkins.

### 1.1. Kết quả học tập

Sau bài này, bạn sẽ:

1. Biết chính xác Gradle `Test` xuất **JUnit XML**, **HTML report** và **binary test results** ở đâu.
2. Bật JaCoCo `xml` và `html` reports, hiểu file `.exec` và coverage metrics.
3. Hiểu vì sao `jacocoTestReport` không tự động chạy `test` hoặc chạy sau `test` nếu không cấu hình thứ tự.
4. Sử dụng `finalizedBy` để tạo coverage report sau khi test chạy, kể cả khi test có assertion failure, khi execution data tồn tại.
5. Phân biệt **test report**, **coverage report**, **build log**, **binary release artifact**, **diagnostic snapshot** và **Gradle Build Cache**.
6. Ghi log ra file nhưng vẫn bảo toàn exit code của Gradle, kể cả khi dùng `tee`.
7. Upload artifacts khi thành công/thất bại qua `if: always()` (GitHub Actions) và `artifacts: when: always` (GitLab).
8. Đăng ký JUnit reports với CI để xem test cases trực tiếp, không chỉ download ZIP.
9. Nhận diện vấn đề multi-project, multi-suite, dynamic report paths, test retry, flaky test và crash giữa chừng.
10. Thiết lập retention, size limits, quyền truy cập, kiểm soát log chứa secrets và policy cho PR không tin cậy.
11. Viết/ chạy một project Java 17 có kiểm thử JUnit với case **fail có chủ đích**, thu thập evidence sau failure.
12. Thiết kế runbook triage để từ một CI run tìm được nguyên nhân và tái hiện trên local.

## 2. Định nghĩa đúng loại dữ liệu muốn lưu

Một pipeline Gradle có nhiều đầu ra khác nhau:

| Loại dữ liệu | Dùng để làm gì? | Ví dụ thông dụng |
| --- | --- | --- |
| **JUnit XML test results** | CI phân tích số tests, failures, thời gian, testcase names | `build/test-results/test/TEST-*.xml` |
| **HTML test report** | Developer duyệt failures/stacktraces trên trình duyệt | `build/reports/tests/test/index.html` |
| **Binary test results của Gradle** | Dữ liệu máy đọc để tạo/aggregate Gradle reports | `build/test-results/test/binary/` |
| **JaCoCo execution data** | Dữ liệu thực thi do JaCoCo agent ghi | `build/jacoco/test.exec` |
| **JaCoCo XML coverage** | Tool/CI parse counters, annotations, gates | `build/reports/jacoco/test/jacocoTestReport.xml` |
| **JaCoCo HTML coverage** | Con người xem lớp, phương thức và dòng được cover | `build/reports/jacoco/test/html/index.html` |
| **Gradle console log** | Task order, root cause, compiler/test exceptions, stacktraces | `ci-output/gradle-test.log` |
| **JAR/WAR/distribution artifact** | Tái hiện binary đã tạo, kiểm packaging/version | `build/libs/*.jar` hoặc `build/distributions/*` |
| **Environment/build manifest** | Gắn evidence với commit/JDK/OS/Gradle/build number | `ci-output/build-context.txt` |
| **Heap dump/thread dump** | Chẩn đoán JVM memory/deadlocks, khi cần | file do JVM và công cụ tạo |
| **Build Scan/Develocity link** | Profiling/dependency/Task insights | URL có quyền truy cập riêng |

Những paths trên là **mặc định cho Java plugin, JaCoCo test suite `test` và project ví dụ**, không phải quy tắc mọi plugin/task. Khi có `integrationTest`, custom reports directories, nhiều subprojects hoặc JaCoCo aggregation, đường dẫn sẽ khác.

### 2.1. Report và artifact không giống nhau

- **Report**: nội dung mô tả kết quả, như JUnit XML hoặc HTML test report.
- **Artifact**: file/directory được CI server giữ lại cho một run, có thể bao gồm reports và cả compiled JARs.
- **CI test report integration**: cơ chế CI **đọc** file JUnit XML để hiển thị test cases trong giao diện.
- **Artifact retention**: cơ chế CI **lưu bytes** để tải xuống sau này.
- **Build Cache**: cache task outputs để tăng tốc build dựa vào cache key; **không phải** kho lưu test failures để điều tra.

Một XML có thể **vừa** được đăng ký cho CI parser, **vừa** được lưu như artifact thông thường. Đó thường là cách tốt nhất.

### 2.2. Report nào người đọc nên mở trước?

Sau failure:

1. Xem **CI log** để biết task nào fail và build có dừng trước khi test bắt đầu không.
2. Nếu `:test FAILED`, xem **JUnit XML / CI Tests tab / HTML test report** để định vị testcase và assertion.
3. Nếu coverage threshold fail, xem **JaCoCo XML/HTML** và violation rule.
4. Nếu class-loading/compiler failure, xem **Gradle `--stacktrace`** và Java/Gradle versions.
5. Nếu packaging/release failure, mở **JAR/distribution**, manifest, metadata và checksums.

Không cố đọc JaCoCo HTML để giải thích một lỗi `compileJava` trước khi tests chạy: khi đó coverage report có thể chưa tồn tại.

## 3. Gradle Test task mặc định tạo gì?

Khi áp `java`/`java-library` hoặc `application`, Gradle thường tạo `test` task kiểu `org.gradle.api.tasks.testing.Test`.

Theo tài liệu Gradle hiện hành, Test task có ba nhóm kết quả chính:

1. **HTML report** để người đọc.
2. **JUnit-compatible XML results** để các CI servers và tools phân tích.
3. **Gradle binary results** dùng nội bộ và cho test report aggregation.

Cấu trúc điển hình của project một module:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-dev.example.ci.FeeCalculatorTest.xml
        └── binary/
            └── (Gradle binary test result files)
~~~

Lưu ý: tên file XML phụ thuộc fully qualified test class names, output có thể thêm files/dirs khác, và cấu trúc report thay đổi theo Gradle version.

### 3.1. XML khác HTML ở điểm nào?

JUnit XML có thể chứa:

~~~xml
<testsuite name="dev.example.ci.FeeCalculatorTest"
           tests="3" failures="1">
  <testcase name="addsFee" classname="dev.example.ci.FeeCalculatorTest"/>
</testsuite>
~~~

Đây là **XML trích đoạn minh họa**, không phải file báo cáo được tạo nguyên văn. Thực tế XML có timestamps, durations, stacktraces, stdout/stderr hoặc namespace khác.

- CI parser thường đọc `TEST-*.xml`.
- Người đọc thường mở HTML.
- HTML không phải lựa chọn tốt để CI tổng hợp test counts nếu có JUnit XML sẵn.
- XML có thể chứa stacktraces và test stdout/stderr, do đó cần security policy.

### 3.2. Test report không nhất thiết có khi build fail

Nếu build fail ở `compileJava`, `compileTestJava`, dependency resolution, plugin application hoặc JVM startup, `test` có thể chưa thực thi. Khi đó **không có JUnit XML/HTML mới**. Pipeline upload cần xử lý việc thiếu files một cách hợp lý và vẫn lưu console log.

Nếu test process crash/OS kill trước khi Gradle flush results, report có thể bị thiếu hoặc không đầy đủ. `always()` trong CI **không tự tạo report đã mất**; nó chỉ upload các files còn tồn tại.

### 3.3. Bật JUnit XML rõ ràng

Trong Kotlin DSL:

~~~kotlin
tasks.test {
    useJUnitPlatform()
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}
~~~

Với JUnit Jupiter cần đúng dependencies/test engine và Java plugin. `useJUnitPlatform()` chỉ chọn JUnit Platform, không tự cài JUnit Jupiter.

### 3.4. Log riêng cho tests

Gradle `Test.testLogging` hỗ trợ:

~~~kotlin
tasks.test {
    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = false
    }
}
~~~

`FULL` cho thông tin exceptions chi tiết hơn; đừng bật `showStandardStreams=true` trên CI nếu tests có thể in access tokens/PII. JUnit XML cũng có options `includeSystemOutLog`, `includeSystemErrLog` và `isOutputPerTestCase` để kiểm soát dữ liệu sẽ được lưu.

## 4. JaCoCo: coverage data khác coverage report

Gradle `jacoco` plugin hỗ trợ đo coverage code Java thông qua JaCoCo agent.

~~~kotlin
plugins {
    java
    jacoco
}
~~~

Sau khi chạy tests với JaCoCo agent:

~~~text
build/jacoco/test.exec
~~~

là **execution data**, không phải HTML report và không phải XML cho CI parser. Nó cần class/source thông tin tương ứng để tạo report.

`jacocoTestReport` có thể sinh:

~~~text
build/reports/jacoco/test/
├── jacocoTestReport.xml
└── html/
    └── index.html
~~~

### 4.1. Chú ý dependency giữa test và report

Theo Gradle JaCoCo plugin guide, **`jacocoTestReport` không tự phụ thuộc `test`**. Bạn phải đảm bảo tests chạy trước khi tạo report.

Khi muốn report chạy sau `test`, cấu hình:

~~~kotlin
tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}
~~~

`finalizedBy` là finalizer task relationship: Gradle cố chạy report sau khi test task đã được scheduled/executed, kể cả khi test task báo thất bại. Nó **không** cứu được dữ liệu nếu JVM/runner bị kill hoặc JaCoCo execution file chưa từng được tạo.

Bạn cũng có thể dùng:

~~~kotlin
tasks.jacocoTestReport {
    dependsOn(tasks.test)
}
~~~

trong tình huống muốn chạy report theo yêu cầu trước khi tests chưa được chạy. Nhưng **không dựa riêng vào `dependsOn(test)` để bảo đảm report chạy sau một test task FAILED**: dependency đã fail có thể khiến task downstream bị skip. Để có reports trên assertion failures, cấu hình finalizer và thiết kế CI upload `always`.

### 4.2. JaCoCo metrics không phải một con số duy nhất

JaCoCo có thể báo các counters:

- Instruction coverage.
- Branch coverage.
- Line coverage.
- Method coverage.
- Class coverage.
- Complexity-related metrics.

CI có thể hiển thị line coverage, instruction coverage hoặc custom metric theo tool. **Không** nói “coverage 80%” nếu chưa chỉ rõ denominator/counter, tập classes và test suites.

### 4.3. Coverage là tín hiệu, không chứng minh correctness

100% line coverage vẫn có thể bỏ sót edge cases và assertions vô nghĩa. Ngược lại, một số generated code/DTOs không hợp lý để yêu cầu 100%. Quality gate nên kết hợp tests, code review, static analysis và security checks.

### 4.4. JaCoCo XML dành cho CI integrations

Với `jacocoTestReport.reports.xml.required=true`, có thể upload XML vào GitLab code-coverage diff annotations hoặc coverage services. HTML dùng để đọc thủ công. Không dùng `test.exec` thay cho XML trong `artifacts:reports:coverage_report`.

## 5. Project thực hành đầy đủ: Java 17 + JUnit + JaCoCo

Bài lab tạo project độc lập và một lỗi test có thể bật bằng property. Mục tiêu là chứng minh: **failure vẫn được ghi nhận, các report files vẫn có cơ hội được tạo, CI vẫn fail và diagnostics vẫn được upload**.

### 5.1. Cấu trúc files

~~~text
gradle-ci-evidence/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── wrapper/                  (nếu dùng Wrapper, lấy từ Gradle)
├── gradlew                         (nếu đã tạo Wrapper)
├── gradlew.bat                     (nếu đã tạo Wrapper)
├── src/
│   ├── main/java/dev/example/ci/
│   │   ├── FeeCalculator.java
│   │   └── DemoMain.java
│   └── test/java/dev/example/ci/
│       └── FeeCalculatorTest.java
├── ci-output/                      (tạo trong CI)
├── .github/workflows/gradle.yml    (GitHub Actions variant)
└── .gitlab-ci.yml                  (GitLab variant)
~~~

Không nhất thiết sử dụng đồng thời GitHub Actions và GitLab CI trong một repo; chúng là **hai cấu hình thay thế**. Core plugins `java` và `jacoco` không yêu cầu external plugin id; JUnit Jupiter dependency có thể cần Internet/cache.

### 5.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-ci-evidence"
~~~

### 5.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

plugins {
    java
    jacoco
}

group = "dev.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

jacoco {
    toolVersion = "0.8.15"
}

tasks.test {
    useJUnitPlatform()

    // Thí nghiệm fail có chủ đích, mặc định là false.
    systemProperty(
        "demo.fail",
        providers.gradleProperty("demoFail")
            .orElse("false")
            .get()
    )

    reports {
        junitXml.required.set(true)
        html.required.set(true)

        junitXml.isOutputPerTestCase = true

        // An toàn hơn khi không đưa stdout/stderr tùy ý vào XML.
        junitXml.includeSystemOutLog = false
        junitXml.includeSystemErrLog = false
    }

    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = false
    }

    // Tạo report cả khi test assertion fail, nếu còn execution data.
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    reports {
        xml.required.set(true)
        html.required.set(true)
        csv.required.set(false)
    }
}
~~~

**Vì sao cấu hình này quan trọng?**

- `java` tạo `test` task, compile main/test source sets và `jar`.
- `jacoco` instrument test process, tạo execution data và task report.
- JUnit BOM giữ versions của JUnit Jupiter/Platform modules nhất quán.
- `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` giúp Gradle sử dụng JUnit Platform launcher đúng dependency graph.
- Java toolchain/`options.release=17` đảm bảo compile target Java17.
- `-PdemoFail=true` làm một assertion sai có chủ đích để kiểm đường failure.
- `junitXml` và `html` được bật tường minh.
- `junitXml.includeSystemOutLog/ErrLog=false` giảm việc đưa stdout/stderr tùy ý vào archived XML, **không tự scrub stacktrace/assertion text**.
- `TestExceptionFormat.FULL` cung cấp trace hữu ích trong console log khi có test fail.
- `finalizedBy(jacocoTestReport)` cho phép report chạy sau Test task ngay cả khi Test failure, miễn process Gradle vẫn sống và execution file hợp lệ.
- Không đặt `ignoreFailures=true`: điều đó có thể khiến CI báo xanh dù tests fail.
- Không bắt JaCoCo report task dùng `dependsOn(test)` trong project lab, vì ta chạy `test` rồi lấy finalizer.

### 5.4. FeeCalculator.java

Đặt file `src/main/java/dev/example/ci/FeeCalculator.java`:

~~~java
package dev.example.ci;

public final class FeeCalculator {
    private FeeCalculator() {
    }

    public static int total(int subtotal, int fee) {
        if (subtotal < 0 || fee < 0) {
            throw new IllegalArgumentException(
                    "subtotal and fee must be nonnegative"
            );
        }
        return Math.addExact(subtotal, fee);
    }
}
~~~

Method dùng `Math.addExact` để không âm thầm overflow `int`. Một số nhánh sẽ được cover bằng JUnit tests phía dưới.

### 5.5. DemoMain.java

Đặt file `src/main/java/dev/example/ci/DemoMain.java`:

~~~java
package dev.example.ci;

public final class DemoMain {
    private DemoMain() {
    }

    public static void main(String[] args) {
        System.out.println(
                "TOTAL=" + FeeCalculator.total(100, 10)
        );
    }
}
~~~

Không cần `application` plugin để chạy `DemoMain` thủ công; bài lab tập trung `java`/`test`/`jacoco`.

### 5.6. FeeCalculatorTest.java

Đặt file `src/test/java/dev/example/ci/FeeCalculatorTest.java`:

~~~java
package dev.example.ci;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class FeeCalculatorTest {
    @Test
    void addsFee() {
        assertEquals(110, FeeCalculator.total(100, 10));
    }

    @Test
    void rejectsNegativeInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> FeeCalculator.total(-1, 2)
        );
    }

    @Test
    void optionalFailureForCiDiagnostics() {
        int expected = Boolean.getBoolean("demo.fail") ? 7 : 5;
        assertEquals(
                expected,
                FeeCalculator.total(2, 3),
                "Intentional demonstration of CI failure"
        );
    }
}
~~~

Khi không truyền `-PdemoFail`, cả ba tests pass. Khi truyền `-PdemoFail=true`, method `optionalFailureForCiDiagnostics` kỳ vọng 7 nhưng nhận 5 và fail **có chủ đích**. Những tests khác vẫn pass. Đây là cách kiểm pipeline lưu artifacts khi test fail mà không cần sửa source.

### 5.7. Chạy thành công

Đứng trong project:

~~~bash
gradle clean test
~~~

Nếu Gradle/JDK/JUnit deps có sẵn, kỳ vọng `:test` pass và finalizer `:jacocoTestReport` chạy. Những file quan trọng:

~~~text
build/test-results/test/TEST-dev.example.ci.FeeCalculatorTest.xml
build/reports/tests/test/index.html
build/jacoco/test.exec
build/reports/jacoco/test/jacocoTestReport.xml
build/reports/jacoco/test/html/index.html
~~~

Tên và paths trên mô tả convention của Gradle Java Test/JaCoCo cho task `test` khi không đổi report directories.

### 5.8. Chạy cố ý fail

~~~bash
gradle clean test -PdemoFail=true --stacktrace --console=plain
~~~

Dù test fail:

- `test` phải đưa exit code khác 0 cho Gradle process.
- JUnit results được Gradle cố tạo từ tests đã chạy.
- `jacocoTestReport` là finalizer; thường chạy nếu JaCoCo execution data tồn tại.
- Job CI phải vẫn **FAILED**, không chuyển thành PASS chỉ để xuất report.
- Lưu artifact step sau đó phải dùng "always" trigger.

**Lưu ý:** Nếu CI process bị SIGKILL/OOMKilled trước khi finalizer chạy, report vẫn có thể không tồn tại. Đó là lý do cần lưu logs và CI runner context ngoài Gradle.

### 5.9. Javac/java độc lập với Gradle

Với JDK17, trên Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -d out \
    src/main/java/dev/example/ci/FeeCalculator.java \
    src/main/java/dev/example/ci/DemoMain.java

java -cp out dev.example.ci.DemoMain
~~~

Stdout **chính xác**:

~~~text
TOTAL=110
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out src\main\java\dev\example\ci\FeeCalculator.java src\main\java\dev\example\ci\DemoMain.java

java -cp out dev.example.ci.DemoMain
~~~

Cũng in `TOTAL=110`. Lệnh Java độc lập **không chạy JUnit/JaCoCo** và không tạo Gradle report; muốn kiểm pipeline artifacts phải chạy `gradle test`.

## 6. Đọc JUnit XML và JaCoCo report đúng cách

### 6.1. JUnit XML

Sau test:

~~~bash
cat build/test-results/test/TEST-dev.example.ci.FeeCalculatorTest.xml
~~~

Tìm:

- `testsuite`: tests/failures/errors/skipped counts, time.
- `testcase`: tên class/method.
- `failure`: assertion message/stacktrace.
- `error`: ngoại lệ từ execution infrastructure hoặc test code.
- `skipped`: disabled/skipped tests, nếu có.
- `system-out`/`system-err` nếu được cho phép.

JUnit XML thực tế không phải tiêu chuẩn XML duy nhất bất biến; mỗi CI parser có tập khả năng khác nhau. Gradle cung cấp JUnit-compatible XML format, nhưng nên kiểm tên report pattern và CI parsing warnings.

### 6.2. JaCoCo XML

~~~bash
cat build/reports/jacoco/test/jacocoTestReport.xml
~~~

XML có `counter` với các loại như `INSTRUCTION`, `BRANCH`, `LINE`, `METHOD`, `CLASS`. Một trích đoạn giả lập:

~~~xml
<counter type="INSTRUCTION" missed="4" covered="12"/>
~~~

Nếu công cụ tính instruction coverage từ đoạn ví dụ trên:

~~~text
12 / (4 + 12) = 75%
~~~

**Đây chỉ là ví dụ tính metric**, không khẳng định coverage thực tế của project lab là 75%. Coverage thực phụ thuộc bytecode, JaCoCo version, tập classes, tests và exclude rules.

### 6.3. Mở HTML reports

Linux:

~~~bash
xdg-open build/reports/tests/test/index.html
xdg-open build/reports/jacoco/test/html/index.html
~~~

macOS:

~~~bash
open build/reports/tests/test/index.html
open build/reports/jacoco/test/html/index.html
~~~

Windows PowerShell:

~~~powershell
Start-Process .\build\reports\tests\test\index.html
Start-Process .\build\reports\jacoco\test\html\index.html
~~~

Không mở HTML của artifact **không đáng tin** từ nguồn không xác định trong context có quyền đặc biệt; với CI artifacts nội bộ vẫn cần quyền truy cập phù hợp.

### 6.4. Vì sao upload cả XML và HTML?

- XML: CI/MR test summaries, coverage annotations và tools đọc máy.
- HTML: developer đọc failure drill-down và những class/method chưa cover.
- `.exec`: hỗ trợ re-create JaCoCo reports khi có đúng class/source data.
- Log: thấy Gradle task failures trước khi report được tạo.

Chỉ upload HTML có thể khiến CI không nhận test counts; chỉ upload XML có thể khó duyệt coverage trực quan.

## 7. Thu Gradle console log mà không nuốt exit code

Một sai lầm hay gặp:

~~~bash
./gradlew test | tee gradle-test.log
~~~

Nếu shell chỉ trả exit code của `tee`, Gradle fail nhưng shell command vẫn có thể trả 0. Khi đó CI báo PASS giả.

### 7.1. Bash: bật pipefail

~~~bash
set -o pipefail
mkdir -p ci-output

./gradlew clean jar test --stacktrace --console=plain \
    2>&1 | tee ci-output/gradle-test.log
~~~

- `2>&1` gộp stderr vào stdout để log file đủ context.
- `tee` vừa in vừa ghi file.
- `set -o pipefail` khiến pipeline trả nonzero khi Gradle command fail.
- `--console=plain` giảm ANSI/color/progress rendering khó đọc trong archived logs.
- `--stacktrace` bổ sung trace hữu ích. Nếu quá nhiều, bắt đầu với default log/`--stacktrace` và chỉ dùng `--info` khi cần.
- `jar` được đặt trước `test`, nên JAR có cơ hội tồn tại dù JUnit assertions fail; compiler failure vẫn có thể chặn cả hai.
- `test` có finalizer tạo coverage report ngay cả khi tests fail (nếu Gradle còn chạy).

**Không** thêm `|| true` ở cuối chỉ để job tiếp tục upload. Dùng CI cleanup/upload step với trigger always để giữ failure status.

### 7.2. Bash: thu exit code riêng khi cần

~~~bash
set -o pipefail
mkdir -p ci-output

set +e
./gradlew clean jar test --stacktrace --console=plain \
    > ci-output/gradle-test.log 2>&1
gradle_status=$?
set -e

cat ci-output/gradle-test.log
exit "$gradle_status"
~~~

Đây là script độc lập. Nó không dùng `tee`; capture exit status trước khi `cat` để không bị kết quả của lệnh in log che. Phù hợp khi cần thêm bước thống kê/log sanitization nội bộ.

### 7.3. PowerShell: kiểm LASTEXITCODE

~~~powershell
New-Item -ItemType Directory -Force ci-output | Out-Null

& .\gradlew.bat clean jar test --stacktrace --console=plain *>&1 |
    Tee-Object -FilePath ci-output\gradle-test.log

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "Gradle failed with exit code $exitCode"
}
~~~

Đây là mẫu PowerShell để minh họa exit status; behavior native process/pipelines có thể khác giữa Windows PowerShell 5.1 và PowerShell 7. Trong CI production, nên ưu tiên wrapper chạy trực tiếp rồi kiểm `$LASTEXITCODE` ngay sau call, hoặc dùng PowerShell script được team xác minh. Không giả định một transcript log chỉ ra build PASS khi native exit status nonzero.

### 7.4. Mức log nào nên lưu?

| Option | Dùng khi nào | Rủi ro |
| --- | --- | --- |
| `--console=plain` | CI logs text dễ tìm | Ít định dạng màu/progress |
| `--stacktrace` | Build/plugin/task failure | Trace dài, có paths |
| `--info` | Dependency/Task/Cache diagnostics | Rất nhiều log, có metadata |
| `--debug` | Điều tra sâu tạm thời | Có thể lộ headers/credentials và quá lớn |
| `--scan` | Profiling/troubleshooting được phép | Có thể chia sẻ metadata tới service khác |
| JVM GC/heap dumps | JVM crash/OOM chuyên sâu | Dung lượng và độ nhạy cao |

**Quy tắc:** debug verbosity tăng theo nhu cầu triage, không bật tất cả flags lên mọi PR build.

## 8. GitHub Actions: luôn upload evidence sau test failure

Ví dụ file `.github/workflows/gradle.yml` dùng các action major versions được tài liệu chính thức công bố ở thời điểm biên soạn: `actions/checkout@v7`, `actions/setup-java@v6`, `gradle/actions/setup-gradle@v6` và `actions/upload-artifact@v7`. Với repo sản xuất, tổ chức có thể yêu cầu pin full commit SHA để chống supply-chain substitution.

### 8.1. Workflow đầy đủ cho project mẫu

~~~yaml
name: Gradle test diagnostics

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  java-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Run tests and collect console log
        shell: bash
        run: |
          set -o pipefail
          mkdir -p ci-output
          ./gradlew clean jar test --stacktrace --console=plain \
            2>&1 | tee ci-output/gradle-test.log

      - name: Upload CI diagnostics even on failure
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: gradle-ci-diagnostics
          retention-days: 7
          if-no-files-found: warn
          path: |
            ci-output/gradle-test.log
            build/test-results/test/
            build/reports/tests/test/
            build/jacoco/
            build/reports/jacoco/test/
            build/libs/

      - name: Upload JUnit XML for independent parsing
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: junit-xml
          retention-days: 7
          if-no-files-found: warn
          path: build/test-results/test/TEST-*.xml
~~~

### 8.2. Vì sao upload phải dùng if: always()?

GitHub Actions steps có mặc định status check khiến bước upload sau test failure bị skip nếu không override. `if: always()` cho phép bước upload được chạy ngay cả khi bước test trước đã fail.

**Giới hạn:** Nếu whole job/runner bị force-terminated, process bị kill trước khi flush report hoặc GitHub service unavailable, upload vẫn có thể thất bại. `always()` không tạo lại lost files và không làm failure trở thành success.

### 8.3. Không che failure status

Workflow không dùng:

~~~yaml
continue-on-error: true
~~~

cho test step. Nó cũng không dùng shell `|| true`. Khi tests fail, test step nonzero và job vẫn red dù artifact step có thể thành công.

### 8.4. if-no-files-found: warn có nghĩa gì?

Nếu test chưa chạy do compile failure, JUnit XML có thể thiếu. `if-no-files-found: warn` tạo warning thay vì fail thêm artifact step. Điều này hữu ích vì **root failure đã nằm ở Gradle step**.

Tuy nhiên, nếu test step báo SUCCESS mà JUnit XML vẫn thiếu, cần quality gate riêng phát hiện “no tests executed” hoặc XML path sai. Đừng dùng warn mãi để che configuration bug.

### 8.5. Retention days

`retention-days: 7` là ví dụ policy ngắn hạn. GitHub Actions artifact retention chịu repository/org/enterprise policies, plan và giới hạn của upload action. Đừng mặc định artifact tồn tại vĩnh viễn hoặc có thể truy cập công khai.

### 8.6. Một upload hay nhiều uploads?

Ví dụ cố ý dùng hai uploads:

- `gradle-ci-diagnostics`: đầy đủ log, reports, coverage data và JAR nếu có.
- `junit-xml`: JUnit XML riêng, tiện tích hợp downstream tools.

Với `actions/upload-artifact` hiện đại, artifacts là immutable upload units; không để **nhiều steps/jobs ghi chồng cùng artifact name**. Nếu matrix JDK17/JDK21/OS có nhiều jobs, dùng tên phân biệt theo job/matrix/run hoặc merge artifacts bằng action chuyên dụng phù hợp.

### 8.7. GitHub không tự hiển thị JUnit XML thành test dashboard

`actions/upload-artifact` chỉ lưu files. Để hiện test annotations/checks, cần một reporter/tool/action thích hợp có quyền phù hợp, và phải cân nhắc security của `pull_request` từ forks. Không tự thêm action có quyền write token vào untrusted PR chỉ để đọc XML khi chưa review threat model.

## 9. GitLab CI: artifacts:when:always + reports:junit + coverage_report

GitLab cho phép upload artifacts kể cả khi job failed và **đăng ký reports để hiện Test summary/MR**.

### 9.1. .gitlab-ci.yml đầy đủ

~~~yaml
stages:
  - test

gradle-verification:
  stage: test
  image: eclipse-temurin:17-jdk

  script:
    - mkdir -p ci-output
    - bash -o pipefail -c './gradlew clean jar test --stacktrace --console=plain 2>&1 | tee ci-output/gradle-test.log'

  artifacts:
    when: always
    expire_in: 7 days

    paths:
      - ci-output/gradle-test.log
      - build/test-results/
      - build/reports/tests/
      - build/jacoco/
      - build/reports/jacoco/
      - build/libs/

    reports:
      junit: build/test-results/test/TEST-*.xml
      coverage_report:
        coverage_format: jacoco
        path: build/reports/jacoco/test/jacocoTestReport.xml
~~~

Đây là pipeline **cho project một module**. Image cung cấp JDK17; repository phải có `gradlew`, `gradlew.bat` và Wrapper JAR/properties được commit, và file `gradlew` phải có execute bit hợp lệ trên Linux runner.

### 9.2. Vì sao cả paths và reports?

- `artifacts.paths` giữ raw XML/HTML/exec/log/JAR để download và mở.
- `artifacts.reports.junit` cho GitLab parse test cases vào Tests tab/MR summaries.
- `artifacts.reports.coverage_report` cho GitLab đọc JaCoCo XML và hiển thị **line-by-line diff annotations** khi tính năng hỗ trợ.
- `artifacts.when: always` yêu cầu lưu files khi job FAILED hoặc SUCCESS, nếu runner còn khả năng upload.
- `expire_in: 7 days` đặt TTL cơ bản, subject to GitLab instance/latest-job retention policy.

GitLab JaCoCo coverage visualization không có nghĩa coverage percentage tự động xuất hiện trong mọi MR widget: với GitLab, % coverage và line-diff annotations là **hai tính năng khác nhau**. Tài liệu GitLab có lưu ý khả năng aggregate JaCoCo multi-module vẫn bị giới hạn; kiểm chính xác version/server đang triển khai.

### 9.3. Khi paths không tồn tại

Nếu `test` chưa được gọi do compiler failure, `build/test-results/test` không có. GitLab runner có thể in warning khi không tìm thấy report/file. Đừng coi đó là root cause; xem `ci-output/gradle-test.log` hoặc primary job trace.

### 9.4. Đừng dùng allow_failure để được upload artifacts

~~~yaml
allow_failure: true
~~~

trên job test sẽ khiến thất bại được coi là có thể bỏ qua, không phù hợp test quality gate chính. Dùng `artifacts.when: always` là cách **giữ evidence nhưng vẫn giữ kết luận fail**.

### 9.5. GitLab JaCoCo multi-module

Nếu có nhiều `**/build/reports/jacoco/test/jacocoTestReport.xml`, xem docs GitLab về multi-module class-name ambiguity và aggregated JaCoCo reports. Không giả định pattern wildcard tự giải quyết mọi vấn đề module/package overlap.

## 10. Jenkins declarative pipeline: post always

Với Jenkins, có thể chạy Gradle và lưu báo cáo trong `post { always { ... } }`:

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'jdk17'
    }

    stages {
        stage('Test') {
            steps {
                sh './gradlew clean jar test --stacktrace --console=plain'
            }
        }
    }

    post {
        always {
            junit(
                testResults: '**/build/test-results/test/TEST-*.xml',
                allowEmptyResults: true
            )

            archiveArtifacts(
                artifacts: '**/build/reports/**,**/build/jacoco/**,**/build/libs/*.jar',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }
    }
}
~~~

**Điều kiện môi trường:** Jenkins agent là Unix-like có `sh`, công cụ JDK có tên `jdk17` đã được cấu hình trong Jenkins, và các plugins pipeline/JUnit/artifact archive có sẵn. Trên Windows agent phải dùng `bat`/`powershell` phù hợp; vì vậy snippet này **không chạy độc lập trên mọi Jenkins installation**.

- `junit(...)` đăng ký test results với Jenkins UI.
- `archiveArtifacts(...)` lưu raw reports/JAR.
- `post.always` được thực thi sau stage kết thúc khi pipeline có cơ hội cleanup.
- `allowEmptyResults/allowEmptyArchive` tránh tạo secondary failure nếu compile dừng sớm.
- `fingerprint: true` phục vụ artifact traceability của Jenkins, **không phải** cryptographic signature thay thế release attestation.

Trong production, nên thêm console log capture riêng khi Jenkins job trace/retention không đủ, và giới hạn artifact lưu theo policy.

## 11. Multi-project Gradle: phải thu thập đúng mọi module

Một root Gradle build có:

~~~text
root/
├── settings.gradle.kts
├── api/
│   └── build/
│       ├── reports/tests/test/
│       ├── test-results/test/
│       └── reports/jacoco/test/
├── service/
│   └── build/
│       ├── reports/tests/test/
│       ├── test-results/test/
│       └── reports/jacoco/test/
└── app/
    └── build/
        └── libs/
~~~

Một path chỉ `build/test-results/test/*` ở root có thể bỏ sót results của `:api:test` và `:service:test`.

### 11.1. Paths cho multi-module artifact upload

GitHub Actions `path` dạng:

~~~yaml
path: |
  **/build/test-results/*/TEST-*.xml
  **/build/reports/tests/**
  **/build/reports/jacoco/**
  **/build/jacoco/*.exec
  **/build/libs/*.jar
  ci-output/*.log
~~~

Trên GitLab có thể dùng patterns thích hợp:

~~~yaml
artifacts:
  when: always
  paths:
    - api/build/test-results/
    - api/build/reports/
    - service/build/test-results/
    - service/build/reports/
    - app/build/libs/
  reports:
    junit:
      - api/build/test-results/test/TEST-*.xml
      - service/build/test-results/test/TEST-*.xml
~~~

Hai snippets ở trên là **những fragments thay thế path cho ví dụ một module**, không phải đầy đủ workflows. Với mono-repo sâu, kiểm glob semantics của CI provider: `**`, leading root, hidden files, symlinks và artifact path root có thể khác nhau.

### 11.2. IntegrationTest là một Test task khác

Ví dụ có `test` và `integrationTest`:

~~~text
build/test-results/test/TEST-*.xml
build/test-results/integrationTest/TEST-*.xml
build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html
~~~

Khi bạn chỉ upload `test/*`, integration failures có thể không được giữ. Nên chọn `**/build/test-results/*/TEST-*.xml` và relevant reports dirs, hoặc liệt kê suites riêng để CI Tests tab phân loại.

### 11.3. JaCoCo report từ test suite nào?

Mặc định `jacocoTestReport` là report cho `test` suite. Nếu có `integrationTest`, cần thêm corresponding execution data/aggregated report bằng Gradle tasks đúng, **không tự đoán** `jacocoTestReport` đã bao gồm tất cả tests.

Có thể dùng Gradle **JaCoCo Report Aggregation Plugin** cho multi-project/test suites theo các constraints của nó. Cần cấu hình JVM Test Suites/outgoing variants và xác nhận coverage XML cuối thực sự bao gồm modules mong muốn.

### 11.4. Tổng hợp JUnit results

Gradle có **Test Report Aggregation Plugin** để tạo HTML aggregate và CI có thể lấy nhiều JUnit XML files. Đừng concat XML đơn giản bằng `cat TEST-*.xml > combined.xml`: nhiều XML documents nối trực tiếp không thành một tài liệu XML hợp lệ.

### 11.5. Artifact names cần tránh đụng nhau

Trong GitHub Actions matrix, tạo tên như `test-jdk17-linux` và `test-jdk21-windows` để nhận dạng platform rõ. Nếu chỉ có `gradle-ci-diagnostics` cho nhiều jobs, upload action có thể từ chối viết nhiều artifact cùng tên ở phiên bản hiện hành.

## 12. Coverage threshold: fail đúng nhưng vẫn giữ report

Một số nhóm quy định CI phải fail nếu coverage dưới ngưỡng. Gradle có task `jacocoTestCoverageVerification`.

Ví dụ bổ sung vào `build.gradle.kts`:

~~~kotlin
import org.gradle.testing.jacoco.tasks.JacocoCoverageVerification

tasks.named<JacocoCoverageVerification>(
    "jacocoTestCoverageVerification"
) {
    violationRules {
        rule {
            limit {
                minimum = "0.80".toBigDecimal()
            }
        }
    }
}
~~~

Đây là **fragment mở rộng**, không thuộc project lab tối thiểu. Ngưỡng 0.80 là ví dụ metric mặc định của rule; trong production cần chỉ rõ counter (`LINE`/`INSTRUCTION`/`BRANCH`), value (`COVEREDRATIO`/`MISSEDRATIO`) và scope (`BUNDLE`/`CLASS`). Ngưỡng phải phản ánh quality policy, không copy máy móc.

### 12.1. Thứ tự chạy coverage verification

Một cách rõ ràng:

~~~bash
./gradlew clean test
./gradlew jacocoTestCoverageVerification
~~~

Dòng thứ hai **chỉ chạy nếu dòng đầu pass** trong CI script có default fail-fast. Khi tests fail, report finalizer vẫn có thể tạo coverage, nhưng coverage gate không cần thay failure nguyên nhân thành violation thứ cấp.

### 12.2. Khi coverage gate fail

Nếu tests pass nhưng `jacocoTestCoverageVerification` fail, pipeline phải:

- Giữ `build/reports/jacoco/test/` và `build/jacoco/test.exec`.
- Giữ log chứa violation rule.
- Báo job FAILED.
- Cho developer nhìn line/branch coverage thực tế.
- Không tự thay đổi threshold để được green nếu chưa được review.

### 12.3. Cách nối vào GitHub Actions workflow

Sau bước test của mục 8, có thể thêm step:

~~~yaml
- name: Check coverage gate
  shell: bash
  run: ./gradlew jacocoTestCoverageVerification --stacktrace --console=plain
~~~

Step này chỉ chạy khi các steps trước pass theo default GitHub Actions status behavior. Bước `Upload CI diagnostics` với `if: always()` nên nằm **sau coverage gate** để giữ cả report của coverage fail. Không dùng `continue-on-error: true` cho gate bắt buộc.

### 12.4. Vì sao không dùng coverage XML như một test report?

JaCoCo XML có counters/packages/classes, **không** có JUnit testcase failures theo định dạng `testsuite/testcase`. CI muốn Tests tab cần JUnit XML; muốn line annotations/coverage phải dùng JaCoCo XML đúng adapter.

## 13. Log trong test reports: cân bằng chẩn đoán và bảo mật

### 13.1. Bật log chi tiết có mục đích

Kotlin DSL:

~~~kotlin
tasks.test {
    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = false
    }
}
~~~

Khi cần điều tra flaky test, có thể bật stdout/stderr có chọn lọc trong một **job giới hạn quyền truy cập**, sau khi bảo đảm không in tokens/passwords/PII.

### 13.2. JUnit XML cũng có log capture

~~~kotlin
tasks.test {
    reports {
        junitXml.includeSystemOutLog = true
        junitXml.includeSystemErrLog = true
        junitXml.isOutputPerTestCase = true
    }
}
~~~

Đây là **cấu hình thay thế** cho thiết lập an toàn hơn của project lab, không được dùng vô điều kiện. Nó có thể khiến logs rất lớn và lưu secret strings vào artifacts.

### 13.3. Những thứ không nên lưu public

- Cloud/CI tokens, OAuth bearer tokens, database passwords.
- HTTP request headers có `Authorization`/`Cookie`.
- Personal data thật trong test fixtures.
- Full environment dumps chứa secrets.
- Production database snapshots.
- Heap dumps hoặc core dumps khi chưa redacted/kiểm quyền.
- Bản build artifact có embedded secrets/key files.
- Sensitive generated configuration files.

Artifact được CI giữ lại không mặc nhiên là “nội bộ an toàn”: quyền download phụ thuộc provider, repository visibility, fork/PR permission settings và retention policy.

### 13.4. Redaction phải diễn ra trước upload

CI secret masking chủ yếu áp vào console logs theo cơ chế provider; **không bảo đảm** scrub toàn bộ JUnit XML, JaCoCo report, heap dump hoặc ZIP đã upload. Đừng ghi secrets vào files từ đầu, hoặc dùng sanitization có kiểm thử và access controls.

### 13.5. PR từ forks và không tin cậy

Pull request code có thể điều khiển test output. Không đưa production secrets vào workflow chạy untrusted fork code, không dùng privileged workflow events một cách tùy tiện và không cho external reporter action quá nhiều quyền. Tách build/test permissions khỏi release/publish credentials.

## 14. Bảo quản artifacts đúng chính sách

### 14.1. Retention: chọn theo giá trị chẩn đoán

Một chính sách tham khảo:

| Nhóm evidence | Gợi ý retention | Lý do |
| --- | --- | --- |
| PR test XML/HTML/coverage | 7–14 ngày | Debug vòng đời PR gần |
| Main-branch integration reports | 14–30 ngày | So regressions dài hơn |
| Release checksums/attestations | Theo audit/release policy | Traceability |
| Debug logs/heap dumps nhạy cảm | Cực ngắn, giới hạn quyền | Giảm leakage |
| Production binaries | Artifact registry với lifecycle riêng | Release reproducibility |

Các mốc chỉ là **gợi ý thiết kế**, không phải retention defaults/requirements chính thức của provider. Cần xét compliance, storage cost, branch/run policies và nhu cầu phục hồi incident.

### 14.2. Name artifacts có ngữ cảnh

Đặt tên biểu thị:

- Component/module.
- Branch/commit SHA hoặc run ID.
- Build job.
- JDK/OS matrix.
- Loại report.
- Test suite.

Ví dụ tên con người đọc được:

~~~text
gradle-ci-diagnostics-linux-jdk17
junit-xml-module-api
coverage-service-integration
release-jar-1.0.0
~~~

CI có thể tạo names tự động với context expressions; trong doc dùng literal để không vô tình lộ internal IDs.

### 14.3. Artifact size management

Đừng upload toàn bộ `build/` hay `~/.gradle` cho mọi job:

- `build/tmp` và incremental compiler caches có thể rất lớn.
- Build caches chứa intermediate files không cần để xem test failure.
- Dữ liệu debug nội bộ có thể nhạy cảm.
- File artifacts nhiều khiến upload/download chậm và tốn tiền.

Chọn đúng `reports/`, `test-results/`, `jacoco/`, `libs/` và `ci-output/`. Chỉ giữ `.exec`/binary test results khi cần regenerate/report aggregation hoặc debug chuyên sâu.

### 14.4. Artifact registry khác CI run artifact

JAR phục vụ deployment nên publish lên Maven/Nexus/Artifactory/GitHub Packages hoặc registry phù hợp, với version/metadata/checksum/signing. Một ZIP tải về từ CI artifact step **không thay** immutable artifact repository và release promotion process.

## 15. Tạo build-context manifest để tái hiện

Bên cạnh reports, lưu một file text ngắn với môi trường chạy:

~~~bash
mkdir -p ci-output
{
  echo "=== Gradle ==="
  ./gradlew --version
  echo "=== Java ==="
  java -version 2>&1
  echo "=== Git commit ==="
  git rev-parse HEAD
  echo "=== OS ==="
  uname -s
} > ci-output/build-context.txt
~~~

Đây là script **Linux/macOS**, giả định repo có Gradle Wrapper và Git. Nó phục vụ reproducibility; file có thể chứa đường JDK, OS/architecture và môi trường. Không in toàn bộ `env` hoặc `gradle properties`: có nguy cơ để lộ credentials.

### 15.1. Những trường nên thu

- Git commit SHA / CI job URL và run ID.
- Gradle Wrapper version + JVM đang chạy Gradle.
- JDK17 toolchain/vendor ở relevant stage.
- OS/architecture/runner type.
- Task commands và flags quan trọng.
- Project/module/test suite.
- Lockfile/dependency graph reference khi đã được kiểm duyệt.
- Artifact checksum nếu là release candidate.

### 15.2. Manifest không thể thay full build reproduction

Muốn tái hiện hoàn toàn còn cần dependency versions, repository accessibility, system services, test data và clock/timezone/locale khi tác động behavior. Một manifest ngắn chỉ giúp phân loại nhanh nguyên nhân.

## 16. Phân biệt các kiểu lỗi khi không có report

| Triệu chứng | Đọc bằng chứng gì? | Hướng xử lý |
| --- | --- | --- |
| `compileJava FAILED` | Gradle log/stacktrace | Sửa compile error, không mong có JUnit XML |
| `compileTestJava FAILED` | Gradle log/test deps | Sửa test imports/engine versions |
| `test NO-SOURCE` | Task outcome, test discovery | Kiểm source set/test dirs |
| `test` chạy nhưng 0 tests | Test counts, JUnit deps | Kiểm `useJUnitPlatform`, class/package discovery |
| `test FAILED` assertion | JUnit XML/HTML, CI Tests tab | Tái hiện exact testcase |
| Test JVM crash/OOM | Daemon/test worker logs, OS events | Đúng JVM heap/worker/process |
| JaCoCo XML missing | `jacocoTestReport` task outcome | Kiểm finalizer/execution data/XML toggle |
| JaCoCo XML có nhưng GitLab không hiện | GitLab report path/parser/rules | Kiểm coverage_report format và MR support |
| XML có nhưng GitHub Tests tab trống | Upload artifact chỉ giữ bytes | Cần reporter integration phù hợp |
| Artifact upload skipped | Upload step default conditional | Dùng `if: always()` / `when: always` |
| Artifact upload failed | Path, permissions, quota, service | Kiểm uploader logs/policies |
| CI green dù test failure | `tee` exit status, `|| true`, ignoreFailures | Giữ Gradle nonzero status |
| Test report cũ từ lần trước | Reused workspace và stale build dirs | `clean`, run isolation, actual task verification |
| Coverage lệch local/CI | JDK/compiler/instrumentation/test selection | Pin environment và kiểm tasks/suites |
| Log không đọc được | ANSI progress/binary data | `--console=plain`, UTF-8/sanitization |

### 16.1. Coverage report không có khi test fail

Các nguyên nhân thường gặp:

1. `jacocoTestReport` không được scheduled.
2. Chỉ khai `dependsOn(test)` và upstream test failed.
3. Test JVM bị kill trước khi xuất execution data.
4. Task `jacocoTestReport` thấy no source/no execution data và SKIPPED.
5. JaCoCo XML bị disable.
6. Upload path trỏ sai module/suite.
7. Cleanup xóa file trước khi upload.
8. CI job/runner không đi được tới upload step.

Khắc phục theo **thứ tự failure chain**, không chỉ bật `xml.required` và mong đầy đủ.

### 16.2. CI parser báo invalid JUnit XML

Tìm nguyên nhân:

- HTML bị đưa vào path JUnit.
- Nhiều XML documents bị nối bằng text.
- File XML bị cắt vì runner process crash.
- Custom parser/schema incompatibility.
- Output chứa ký tự không hợp lệ trong XML do tool xuất không đúng.
- Reporter đang scan files cũ từ workspace khác.

Khi cần inspect XML, dùng XML parser chuẩn hoặc công cụ CI parser logs; đừng sửa test counts thủ công.

## 17. Flaky tests và retries

Một testcase fail lần đầu, pass lần thứ hai có thể làm CI green nếu retry plugin/job được cấu hình, nhưng điều đó **không đồng nghĩa không có lỗi**.

### 17.1. Retain evidence của từng attempt

Nên giữ:

- Test class/method.
- Attempt number.
- Original failure stacktrace.
- Rerun result.
- Environment/time.
- CI run/commit.
- Logs của attempts thất bại.

Đừng chỉ lưu report của lần cuối rồi xóa toàn bộ dấu vết lỗi tạm thời.

### 17.2. Gradle JUnit XML mergeReruns

Gradle Test XML reporting có tùy chọn `junitXml.mergeReruns` để thể hiện các reruns theo schema được hỗ trợ. Một số CI parsers hiểu `flakyFailure`, một số có thể bỏ qua phần đó; behavior tùy provider. Chỉ bật sau khi test reporter/retry engine và CI adapter đã được kiểm tương thích.

### 17.3. Không nên retry mọi failure vô hạn

Nếu retry làm pipeline xanh nhưng failure vẫn xuất hiện thường xuyên, chất lượng thực tế có vấn đề. Tách flaky tests dashboard và đặt ngưỡng/policy thay vì che failure bằng `ignoreFailures`.

## 18. Trường hợp coverage thấp nhưng tests vẫn pass

Đây là **quality gate khác** test failure:

- `Test` pass: các assertions đã chạy không fail.
- JaCoCo reports: cho biết phần code được executed.
- Coverage verification: fail nếu metric dưới ngưỡng đã khai.
- SAST/security scans: xét những vấn đề khác với line coverage.

Một pipeline có thể có:

~~~text
BUILD=SUCCESS
TESTS=PASS
COVERAGE_REPORT=GENERATED
COVERAGE_GATE=FAIL
ARTIFACT_UPLOAD=SUCCESS
CI_JOB=FAILED
~~~

Đây là **mẫu trạng thái logic**, không phải output mặc định của Gradle. Khi coverage gate fail, artifacts vẫn phải có và job vẫn fail.

## 19. Build artifacts: phục vụ debug và release

### 19.1. Vì sao lưu JAR nếu pipeline fail?

Nếu JAR đã được tạo thành công trước khi một integration test fail, lưu nó có thể giúp:

- Reproduce classpath/package content.
- Kiểm manifest/main class/resources.
- So checksums giữa CI runs.
- Chẩn đoán class loading issues trên JDK khác.
- Test lại binary trong controlled sandbox.

**Không** deploy một artifact từ job FAILED như release đã qua QA; đây là **diagnostic artifact**, trừ khi release policy cho phép bước riêng.

### 19.2. JAR không phải bao gồm cả dependencies

Java `jar` task bình thường tạo project artifact, thường không phải fat JAR chứa mọi runtime deps. Nếu failure do missing transitive dependency, lưu `build/libs/*.jar` thôi có thể chưa đủ; nên giữ Gradle dependency graph hoặc runtime resolution evidence theo policy.

### 19.3. Checksums

Linux/macOS:

~~~bash
sha256sum build/libs/*.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\build\libs\gradle-ci-evidence-1.0.0.jar -Algorithm SHA256
~~~

SHA-256 giúp nhận biết bytes thay đổi, nhưng **không tự xác minh publisher identity/signature**. Đối với production release cần artifact signing/provenance và trusted registry workflow phù hợp.

### 19.4. Manifest và GAV

Lưu version, Git SHA và release coordinates trong metadata đáng tin, tránh phụ thuộc các artifact names có timestamp tùy ý. Khi build reproducibility được yêu cầu, pin Gradle Wrapper/JDK/dependencies và kiểm reproducible ZIP/JAR rules.

## 20. Build Cache, CI artifacts và workspace cleanup

### 20.1. Không dùng Build Cache làm report archive

Gradle Build Cache lưu task outputs theo cache keys cho **hiệu năng**, không cung cấp UI lịch sử test failures theo CI run. Cache entries có thể bị evict, task input change, hoặc chỉ tồn tại trên một máy.

### 20.2. Không upload toàn bộ GRADLE_USER_HOME

`~/.gradle` chứa dependencies, daemon logs, Gradle distributions, caches và có thể chứa user properties/secrets. Upload nguyên thư mục vào CI artifacts là anti-pattern bảo mật và size. Nếu cần daemon logs vì Gradle crash, thu **đúng file/đúng PID**, scrub và giới hạn access.

### 20.3. Cleanup order quan trọng

Thứ tự tốt:

~~~text
checkout -> setup JDK/Gradle
         -> clean/build/test
         -> finalizers tạo reports
         -> upload JUnit/coverage/log/JAR
         -> CI cleanup workspace
~~~

Thứ tự sai:

~~~text
test fail -> rm -rf build -> upload artifacts
~~~

Khi cleanup sớm, report bị mất dù upload step dùng always.

### 20.4. Lưu artifacts kể cả khi Test task SKIPPED?

Nếu không chạy tests do workflow selection, upload JUnit path có thể trống. Job cần phân biệt **test intentionally skipped** với **test should have run but no tests discovered**. CI quality gate có thể dùng `failOnNoDiscoveredTests` hoặc equivalent policy theo Gradle version/test task APIs và explicit check trên files/test counts.

## 21. Lỗi thường gặp và cách xử lý

### Lỗi 1. Chỉ giữ stdout trên CI

Job retention ngắn hoặc web console logs bị truncate.

**Sửa:** lưu riêng `ci-output/gradle-test.log` cùng JUnit XML/HTML và coverage.

### Lỗi 2. Upload step bị skip sau test failure

Thiếu `if: always()` hoặc `artifacts.when: always`.

**Sửa:** dùng provider-specific cleanup/upload hook, không nuốt Gradle failure.

### Lỗi 3. Dùng || true hoặc ignoreFailures

CI xanh dù tests fail.

**Sửa:** giữ exit code nonzero; upload độc lập với test success.

### Lỗi 4. Dùng tee mà không có pipefail

Shell trả exit code của tee thay vì Gradle.

**Sửa:** `set -o pipefail` hoặc capture `PIPESTATUS`/exit status đúng.

### Lỗi 5. Chỉ upload HTML

GitLab/Jenkins không có JUnit XML để parse.

**Sửa:** upload `TEST-*.xml` và đăng ký CI test report integration.

### Lỗi 6. Chỉ upload XML

Developer khó đọc stacktrace/coverage trực quan.

**Sửa:** giữ HTML và console logs khi cần.

### Lỗi 7. Upload JaCoCo .exec làm coverage_report

GitLab cần JaCoCo XML theo parser; `test.exec` là raw execution data.

**Sửa:** bật `jacocoTestReport.reports.xml` và trỏ XML path.

### Lỗi 8. Nghĩ jacocoTestReport tự chạy sau test

Mặc định task report không tự phụ thuộc vào test.

**Sửa:** `test.finalizedBy(jacocoTestReport)` theo failure-retention workflow.

### Lỗi 9. Chỉ dùng report.dependsOn(test) khi test fail

Downstream report có thể bị skip sau dependency failure.

**Sửa:** dùng finalizer nếu cần tạo report sau failing tests và giữ execution data.

### Lỗi 10. Coverage report chưa tồn tại vì compile fail

JaCoCo không thể báo code chưa compile/test.

**Sửa:** giữ Gradle stacktrace và xác định lifecycle stage, không coi missing coverage là root bug.

### Lỗi 11. Test logs chứa secrets

JUnit XML/console/CI artifacts có tokens.

**Sửa:** không in secrets, cấu hình output capture hạn chế, redact và giới hạn quyền/TTL.

### Lỗi 12. Upload cả ~/.gradle

Rò user properties/caches và artifacts quá lớn.

**Sửa:** chỉ chọn evidence directories có giá trị.

### Lỗi 13. Multi-project path chỉ ở root build

Bỏ sót `:api:test`.

**Sửa:** upload từng module hoặc glob `**/build/test-results/*/TEST-*.xml` và reports tương ứng.

### Lỗi 14. IntegrationTest results không được lưu

Chỉ dùng `test` path.

**Sửa:** include `integrationTest` task paths và coverage execution data nếu relevant.

### Lỗi 15. CI green mà không chạy test nào

Test task NO-SOURCE/skipped hoặc discovery sai.

**Sửa:** kiểm test counts, JUnit engine và test filters; đặt policy kiểm no-tests.

### Lỗi 16. Upload artifact cùng tên từ nhiều matrix jobs

Artifact conflict/overwrites bị cấm trong các uploader hiện đại.

**Sửa:** tên unique theo OS/JDK/job/run hoặc merge có kiểm soát.

### Lỗi 17. File paths chứa environment-specific directory

Artifact uploader không tìm thấy reports.

**Sửa:** xem Gradle `layout.buildDirectory`, `Test.reports` custom paths, multi-project dirs; kiểm file tồn tại trước upload.

### Lỗi 18. Cleanup xóa reports trước upload

**Sửa:** upload ở post/always trước cleanup.

### Lỗi 19. Thấy coverage 80% nhưng không biết metric

CI tool có thể hiển thị instruction/line/branch khác nhau.

**Sửa:** ghi rõ type/denominator/scope và threshold policy.

### Lỗi 20. Coverage gate fail nhưng artifacts step không chạy

Upload step dùng default success condition.

**Sửa:** bảo đảm luôn upload sau coverage verification thất bại.

### Lỗi 21. Chỉ lưu JaCoCo HTML cho MR annotations

GitLab cần `coverage_report` XML.

**Sửa:** bật XML và cấu hình reports coverage_format jacoco.

### Lỗi 22. Dùng GitHub upload-artifact để mong Tests tab tự có

Upload raw XML không tự tạo CI test checks/annotations.

**Sửa:** dùng reporter integration phù hợp với quyền, security policy.

### Lỗi 23. Dùng Jenkins allowEmptyResults=true rồi bỏ qua mọi report thiếu

Có thể che lỗi test discovery.

**Sửa:** chỉ dùng để tránh secondary failures khi compile fail, kết hợp check test task execution/expected counts.

### Lỗi 24. Coverage report từ test suite khác

Mặc định `jacocoTestReport` cho `test`, không tự merge `integrationTest`.

**Sửa:** cấu hình aggregation/executionData đúng suites.

### Lỗi 25. Runner mất nguồn điện/OOMKilled nhưng kỳ vọng luôn có files

Artifacts chỉ được upload nếu runner còn sống và files đã flush.

**Sửa:** dựa thêm CI runner logs/event, OOM monitoring và external log shipping khi cần.

### Lỗi 26. Retention quá ngắn

Artifacts hết hạn trước khi bug được điều tra.

**Sửa:** chọn TTL theo incident triage window và release compliance.

### Lỗi 27. Retention quá dài

Lưu PII/secrets/artifacts lớn không cần thiết.

**Sửa:** data classification, access control, TTL, deletion policy.

### Lỗi 28. Release JAR lấy từ failing job

**Sửa:** phân biệt diagnostic artifact và promoted release artifact; chỉ publish theo policy các builds đã qua gates.

## 22. Bài tập có đáp án

### Bài 1. Test fail, upload step có chạy?

GitHub Actions không khai `if` cho upload step đặt sau test failed.

**Đáp án:** Mặc định step có thể bị skip do implicit success condition. Dùng `if: always()` cho upload, không đổi test exit status.

### Bài 2. GitLab upload cả khi fail?

**Đáp án:**

~~~yaml
artifacts:
  when: always
~~~

Đồng thời khai paths/reports đúng.

### Bài 3. File JUnit XML mặc định ở đâu?

**Đáp án:** `build/test-results/test/TEST-*.xml` trong single-module Java project mặc định.

### Bài 4. File HTML test report?

**Đáp án:** `build/reports/tests/test/index.html`.

### Bài 5. File JaCoCo XML?

**Đáp án:** `build/reports/jacoco/test/jacocoTestReport.xml` khi `xml.required=true` cho `jacocoTestReport`.

### Bài 6. JaCoCo exec có phải XML?

**Đáp án:** Không. `build/jacoco/test.exec` là execution data binary.

### Bài 7. Dùng tee mà pipeline xanh giả?

**Đáp án:** Nếu không `pipefail`, shell có thể trả code của `tee`. Bật pipefail/capture Gradle exit.

### Bài 8. Vì sao không dùng ignoreFailures=true?

**Đáp án:** Nó có thể che test failures khỏi CI gate.

### Bài 9. finalize report khi test fails?

**Đáp án:** `tasks.test { finalizedBy(tasks.jacocoTestReport) }`, report vẫn phụ thuộc execution data tồn tại.

### Bài 10. Test chưa compile?

**Đáp án:** JUnit XML có thể không tồn tại; giữ console log/stacktrace để chẩn đoán compile failure.

### Bài 11. Coverage gate 80% nhưng tests pass?

**Đáp án:** CI vẫn fail nếu `jacocoTestCoverageVerification` violation; upload reports ở always hook.

### Bài 12. Multi-module test paths?

**Đáp án:** Xem `api/build/test-results/test/...`, `service/build/test-results/test/...`; không chỉ root.

### Bài 13. Mở HTML để xem failure?

**Đáp án:** `build/reports/tests/test/index.html` hoặc artifact tải về tương ứng.

### Bài 14. GitHub upload JUnit XML là đủ cho Tests tab?

**Đáp án:** Không. Upload chỉ giữ files; cần adapter/reporter integration để có checks/test annotations.

### Bài 15. Logs có secrets bị masked bởi CI UI thì artifact an toàn?

**Đáp án:** Không chắc. Raw XML/ZIP có thể vẫn giữ dữ liệu; sanitize trước upload và giới hạn quyền.

### Bài 16. Test mới chạy fail trên CI, local pass?

**Đáp án:** Lưu Gradle/JDK versions, OS, commit, test output và CI environment info đã lọc; dùng test XML/log tái hiện.

### Bài 17. CI jar upload đủ làm release promotion?

**Đáp án:** Không. Cần all required gates, immutable artifact registry/checksums/signing/provenance theo policy.

### Bài 18. Project lab Java17 stdout từ javac/java?

**Đáp án:**

~~~text
TOTAL=110
~~~

### Bài 19. Bật -PdemoFail=true?

**Đáp án:** `optionalFailureForCiDiagnostics` cố ý fail expected7 actual5; CI phải red, JUnit XML/HTML và JaCoCo report vẫn có cơ hội được giữ.

### Bài 20. CI runner bị OOMKilled?

**Đáp án:** Upload always không bảo đảm, vì runner process có thể đã chết. Xem CI events/system logs và memory metrics.

## 23. Checklist cho PR và pipeline review

| Mục | Điều kiện đạt |
| --- | --- |
| Java/Gradle | Wrapper và Java17 toolchain pin, build thực sự chạy tests |
| JUnit XML | `TEST-*.xml` tồn tại khi tests đã executed |
| HTML Test | `build/reports/tests/test/index.html` có thể đọc |
| JaCoCo data | `build/jacoco/test.exec` được tạo khi instrumentation chạy |
| JaCoCo XML/HTML | `jacocoTestReport` chạy, reports enabled |
| Test failure | Gradle command có exit code !=0, CI job FAILED |
| Coverage gate | Violation làm CI FAILED, report vẫn lưu |
| Log capture | `--console=plain --stacktrace`, pipefail/exit preserved |
| Always upload | GitHub `if: always()`/GitLab `when: always`/Jenkins `post.always` |
| Artifact scope | Không upload secrets/cache dirs hoặc files quá lớn |
| Multi-project | Paths đúng tất cả modules và custom Test suites |
| CI parser | JUnit XML được đăng ký, JaCoCo XML đúng coverage adapter |
| Missing files | Compile failure không bị che; zero-test được kiểm khi cần |
| Security | Redaction, least privilege, fork PR threat model |
| Retention | TTL phù hợp support/compliance/cost |
| Reproducibility | Commit, JDK, Gradle version, OS/build commands có manifest |
| Release | Diagnostic JAR không tự được promote nếu failing job |
| Triage | Developer biết mở Tests tab/HTML/coverage/log theo thứ tự |

**Kết luận:** CI/CD Gradle không chỉ cần chạy `test` rồi chuyển job sang đỏ/xanh. Cần **giữ lại bằng chứng đúng định dạng**: JUnit XML cho test parsers, HTML cho người đọc, JaCoCo XML/HTML/exec cho coverage, Gradle `--stacktrace` log cho lỗi build và JAR/metadata khi cần truy vết. `finalizedBy` giúp coverage report có cơ hội được tạo ngay cả khi test assertion fail, còn GitHub `if: always()`, GitLab `artifacts: when: always` và Jenkins `post { always { ... } }` giúp artifact upload không bị bỏ qua vì failure. Luôn **bảo toàn exit code** để CI không xanh giả, giới hạn artifact retention/permissions, và phân biệt rõ diagnostic outputs với release artifacts.

## 24. Tài liệu tham khảo chính thức

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html) — Test task, HTML/JUnit XML/binary results, test logging và JUnit 5.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html) — report tasks, finalizers, execution data, XML/HTML, coverage verification và aggregation.
- [Gradle — Test DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html) — test reports, testLogging và fail behavior.
- [Gradle — Test Report Aggregation Plugin](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html) — multi-project TestReport aggregation.
- [Gradle — JaCoCo Report Aggregation Plugin](https://docs.gradle.org/current/userguide/jacoco_report_aggregation_plugin.html) — coverage across Gradle subprojects.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html) — `--stacktrace`, `--info`, `--console=plain` và exit codes.
- [Gradle — GitHub Actions integration](https://docs.gradle.org/current/userguide/github-actions.html) — official setup-gradle action và caching.
- [GitHub Actions — upload-artifact](https://github.com/actions/upload-artifact) — `path`, `retention-days`, `if-no-files-found`, immutable artifact uploads.
- [GitHub Actions — workflow status check functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) — `always()` và job/step conditions.
- [GitHub Actions — setup-java](https://github.com/actions/setup-java) — Java17 setup và runner/toolcache behavior.
- [GitLab CI — Unit test reports](https://docs.gitlab.com/ci/testing/unit_test_reports/) — `artifacts:reports:junit`, MR/Pipeline Tests tab.
- [GitLab CI — JaCoCo coverage visualization](https://docs.gitlab.com/ci/testing/code_coverage/jacoco/) — `coverage_format: jacoco`, line-diff annotations, limitations.
- [GitLab CI — Artifacts reports types](https://docs.gitlab.com/ci/yaml/artifacts_reports/) — `junit` và `coverage_report` semantics.
- [GitLab CI — Job artifacts](https://docs.gitlab.com/ci/jobs/job_artifacts/) — `when`, `expire_in`, storage/retention.
- [Jenkins Pipeline — Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/) — Declarative `post { always { ... } }`.
- [Jenkins — Recording tests and artifacts](https://www.jenkins.io/doc/pipeline/tour/tests-and-artifacts/) — `junit` và `archiveArtifacts` steps.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `--release 17`, Java compile.
