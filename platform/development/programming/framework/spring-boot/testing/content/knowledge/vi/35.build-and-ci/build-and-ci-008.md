# JUnit XML, HTML report, log và artifact để điều tra lỗi

## 1. Vì sao test đỏ mà chỉ xem dòng "BUILD FAILED" là chưa đủ?

Một pipeline Spring Boot có thể chạy hàng nghìn test. Dòng `BUILD FAILED` của Gradle chỉ báo tác vụ không thành công; nó không trả lời đầy đủ:

- Test class và test case nào thật sự thất bại?
- Đây là **assertion failure**, **exception/error**, **test bị skip**, hay **không có test nào được chạy**?
- Lỗi xuất hiện tại logic nghiệp vụ, lúc Spring `ApplicationContext` khởi tạo, khi Testcontainers tạo database, hay trước khi Java test bắt đầu vì compilation/dependency resolution?
- Chỉ xảy ra trên một nhánh CI, một JDK, một OS, hay khi chạy nhiều tests song song?
- Trong log, request/correlation ID nào nối các lớp service với lỗi?
- Có stack trace, dữ liệu đầu vào đã khử nhạy cảm, application log, HTTP mock capture, screenshot hoặc container logs nào cần giữ lại?
- Vì sao test chạy lại thì xanh nhưng lần đầu đỏ? Đó là flaky test, race, time dependency, shared resource hay một retry chỉ che lỗi?
- Làm thế nào giữ bằng chứng **sau khi job fail**, thay vì để pipeline dừng trước bước upload?

Bài thuộc nhóm **Build và CI**, chủ đề chính **“JUnit XML, HTML report, log và artifact để điều tra lỗi”** trong module **Spring Boot - testing**. Ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.5**, **Gradle 8.x**, **JUnit Jupiter**, và một workflow **GitHub Actions**. Các hướng dẫn cũng áp dụng cho Jenkins/GitLab CI nhưng đường dẫn, UI và cú pháp upload sẽ khác.

### Mục tiêu học tập

1. Phân biệt JUnit XML, HTML report, console log và CI artifacts: chúng là các lớp bằng chứng bổ sung cho nhau.
2. Biết đường dẫn mặc định của Gradle `Test`: `build/test-results/test/`, `build/reports/tests/test/index.html` và binary test results.
3. Cấu hình `useJUnitPlatform()`, `testLogging`, `reports.junitXml` và `reports.html` mà không tắt signal cần điều tra.
4. Đọc `<testsuite>`, `<testcase>`, `<failure>`, `<error>`, `<skipped>` và stdout/stderr có thể có.
5. Tạo một Spring Boot project có tests xanh mặc định, một failure scenario cố ý **chỉ bật khi yêu cầu** để học cách đọc report.
6. Viết script Python standard library tổng hợp JUnit XML mà không lộ message/body nhạy cảm.
7. Dùng GitHub Actions `if: always()` + `actions/upload-artifact` để thu XML, HTML, Gradle console log sau cả build xanh và đỏ.
8. Giữ **exit code thất bại** khi pipe qua `tee` với `set -o pipefail`, không dùng `|| true` để giả vờ CI thành công.
9. Hiểu khác biệt giữa test failure, build setup failure, test skip, report chưa sinh và report cũ.
10. Biết thu thêm Spring logs, Testcontainers logs, request traces và screenshots theo principle of least privilege.
11. Điều tra flaky/parallel/timeout failures bằng bằng chứng thay vì chạy lại để làm mất lỗi.
12. Thiết lập retention, quyền truy cập và redaction khi log/report được lưu làm artifacts.

**Giới hạn:** Bộ source trong bài là một project minh họa có thể xây dựng/chạy khi có JDK và Gradle đúng phiên bản. Các dòng XML/kết quả minh họa là **mẫu cấu trúc**, không phải output Gradle đã được thực thi trong quá trình viết.

## 2. Bốn loại bằng chứng quan trọng

| Bằng chứng | Do ai tạo | Mục đích chính | Hạn chế |
| --- | --- | --- | --- |
| **JUnit XML** | Gradle `Test` hoặc Surefire/Failsafe | Máy CI đọc số lượng case/fail/skip; xác định class/method; biểu diễn failure stack | Không phải một đặc tả XML thống nhất tuyệt đối; cần biết producer/version |
| **HTML test report** | Gradle, Maven reporting plugins hoặc hệ thống CI | Con người duyệt summary, class, method, stack trace và output | Là tập các file có CSS/JS; tải riêng `index.html` có thể thiếu assets |
| **Console/build log** | Gradle/Maven, JVM, Spring Boot, test runner | Vì sao dependency/compile/startup/test task fail, timestamps, warnings, exception chain | Có thể rất lớn, chứa secrets/PII nếu logger thiếu kiểm soát |
| **CI artifact** | GitHub Actions/Jenkins/GitLab uploader | Giữ **bản sao** XML, HTML, logs, screenshots, dumps sau khi job kết thúc | Cần retention, permission, encryption/redaction và storage quota |

**JUnit XML không phải file chứa toàn bộ mọi log.** Gradle có thể thêm `<system-out>` và `<system-err>` tùy cấu hình; XML từ runner khác có semantics khác. Mặt khác console log có thể chứa lỗi build trước khi JUnit khởi động, tình huống không có JUnit XML.

```text
./gradlew test
   |
   +-- Gradle build setup / Java compile / dependency resolution
   |      |
   |      +-- lỗi trước Test execution -> console log là nguồn chính
   |
   +-- Gradle Test task + JUnit Platform
          |
          +-- test results (binary data)
          +-- XML: build/test-results/test/TEST-*.xml
          +-- HTML: build/reports/tests/test/index.html
          +-- stdout/stderr + stack traces theo cấu hình
                    |
                    v
              CI artifacts + human triage
```

## 3. Ba câu hỏi cần trả lời khi một job đỏ

**Câu hỏi 1: Test đã được thực thi chưa?**

Nếu build fail ở `compileJava`, `compileTestJava`, plugin resolution hay image pull, đừng tìm một `<failure>` tương ứng trong XML — chưa chắc có test results nào. Bắt đầu từ Gradle log và xác định **task failed**.

**Câu hỏi 2: Test đỏ thật hay report/CI đang xử lý sai?**

CI parser có thể đọc nhầm skipped test, không hỗ trợ retry-specific XML tags, hay chỉ thu một module. Một job cũng có thể trở thành xanh giả do `|| true` hoặc pipeline `tee` không bật `pipefail`. Kết luận phải dựa trên cả **process exit code**, XML và stack.

**Câu hỏi 3: Bằng chứng có đủ để tái hiện không?**

Một XML report ghi test method name nhưng không có version JDK, môi trường, fixture, seed hoặc correlation ID có thể chưa đủ. Cần lưu metadata an toàn: commit SHA, runner OS, JDK version, Gradle version, test task, report, logs liên quan và các artifacts đã được khử dữ liệu nhạy cảm.

## 4. Project mẫu: có cả test xanh và test cố ý đỏ có điều kiện

Chúng ta xây `PricingService` nhỏ, dùng `@SpringBootTest` để Spring tạo bean thật, `@ParameterizedTest` để tạo nhiều test cases, `@EnabledIfSystemProperty` để **chỉ bật một failure scenario khi chạy lệnh chẩn đoán**.

Cấu trúc:

```text
junit-report-investigation/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/report/
│   ├── ReportDemoApplication.java
│   └── PricingService.java
├── src/test/java/com/example/report/
│   └── PricingServiceTest.java
├── scripts/
│   └── summarize_junit.py
└── .github/workflows/
    └── test-reports.yml
```

**Quy tắc của demo:** chạy `gradle test` thông thường thì failure scenario có điều kiện **bị skip**. Khi gọi `-PdemoFail=true`, ta cố ý kích hoạt một `assertEquals` sai; Gradle task phải fail và vẫn tạo reports khi đã chạy tests. Không commit cờ gây fail vào workflow CI mặc định.

### Vì sao dùng một lỗi cố ý có cờ?

Nếu một README chứa `@Test void fails()` luôn fail, mọi người không thể chạy build xanh để học CI setup. Nếu luôn skip lỗi, người học khó xem output `<failure>`. Cờ project property tách **chế độ bình thường** và **chế độ tái hiện sự cố** một cách rõ ràng.

## 5. Gradle: settings.gradle và build.gradle

### settings.gradle

```groovy
rootProject.name = 'junit-report-investigation'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

    // -PdemoFail=true là Gradle project property.
    // Chuyển nó rõ ràng vào JVM đang chạy JUnit.
    systemProperty 'demo.fail',
            providers.gradleProperty('demoFail')
                     .orElse('false')
                     .get()

    reports {
        junitXml.required = true
        html.required = true

        // Gắn captured stdout/stderr với testcase khi CI hỗ trợ.
        junitXml.outputPerTestCase = true

        // Demo không in secrets; production phải redaction.
        junitXml.includeSystemOutLog = true
        junitXml.includeSystemErrLog = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat =
                org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL

        // Không tự đổ toàn bộ stdout vào console.
        showStandardStreams = false
    }
}
```

### Giải thích cấu hình

- `useJUnitPlatform()`: chạy JUnit Jupiter. Nếu thiếu, tests có thể không được discovery theo cách mong muốn.
- `spring-boot-starter-test`: Spring TestContext, JUnit Jupiter, AssertJ và các thư viện kiểm thử phổ biến.
- `junit-platform-launcher` ở `testRuntimeOnly`: hỗ trợ discovery/launcher trong Gradle/JUnit Platform theo khuyến nghị tương thích.
- `systemProperty 'demo.fail', ...`: truyền `-PdemoFail=true` từ Gradle JVM sang **test worker JVM**. Chỉ thêm `-Ddemo.fail=true` vào một lệnh bất kỳ không luôn có cùng ý nghĩa nếu Gradle không chuyển system property sang test JVM.
- `reports.junitXml.required=true` và `reports.html.required=true`: bảo đảm reports được bật; Gradle Java `Test` thường **đã bật cả hai theo mặc định**.
- `outputPerTestCase=true`: stdout/stderr captured có thể liên kết với từng testcase thay vì chỉ level class trong XML.
- `includeSystemOutLog`/`includeSystemErrLog`: phục vụ diagnostic demo; có nguy cơ lộ sensitive output, xem mục bảo mật.
- `testLogging.events`: chọn pass/skip/fail trong Gradle console.
- `TestExceptionFormat.FULL`: in chi tiết stacktrace test-related hơn dạng rút gọn. Nó **khác** Gradle CLI `--stacktrace`, dùng để mở stacktrace lỗi build/task.
- `showStandardStreams=false`: tránh tràn console. Log4j/Logback và Spring logging phải có configuration/redaction phù hợp; setting này không phải chính sách bảo mật đầy đủ.

### Không đổi report paths khi không cần

Gradle mặc định tạo XML ở `build/test-results/test/` và HTML ở `build/reports/tests/test/index.html`. Nếu team hoặc CI đã kỳ vọng các paths ấy, giữ mặc định sẽ đơn giản hơn. Khi custom path bằng `reports.junitXml.outputLocation` hoặc `reports.html.outputLocation`, sửa uploader và parser cùng lúc.

## 6. Spring Boot application root

`src/main/java/com/example/report/ReportDemoApplication.java`:

```java
package com.example.report;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReportDemoApplication.class, args);
    }
}
```

Project có `spring-boot-starter`, **không có web starter** và không cần datasource. Test vẫn dùng `@SpringBootTest(webEnvironment=NONE)` để nạp Spring context, nhưng không mở HTTP port, không truy cập DB hoặc external API. Điều này giúp report tập trung vào JUnit và Spring startup thay vì phụ thuộc mạng.

### Vì sao không dùng một test thuần JUnit duy nhất?

Một test thuần JUnit thích hợp cho utility logic. Tuy nhiên bài thuộc Spring Boot testing, nên `@SpringBootTest` giúp thấy hai lớp failures thường gặp: **Spring context startup** và **JUnit assertion**. Mẫu này không tự tạo context failure, nhưng nội dung triage sẽ chỉ cách phân biệt chúng trong logs.

## 7. PricingService: xử lý thật và log an toàn

`src/main/java/com/example/report/PricingService.java`:

```java
package com.example.report;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    private static final Logger log =
            LoggerFactory.getLogger(PricingService.class);

    public long totalInCents(
            long unitPriceCents,
            int quantity) {

        if (unitPriceCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }

        long amount = Math.multiplyExact(
                unitPriceCents, quantity);

        log.info(
                "pricing calculated quantity={} amountCents={}",
                quantity, amount);

        return amount;
    }
}
```

Log dùng structured placeholders của SLF4J, không concatenation string; nó chỉ chứa quantity và amount, không chứa token, customer name, authorization header hay raw request body. Vì logger phát ở mức INFO, output có thể nằm trong Gradle-captured stdout/stderr hoặc console tùy cấu hình logging.

**Không dựa vào nguyên văn timestamp/logger prefix** khi viết assertion. Logback pattern, timezone và thread name có thể thay đổi theo profile/CI runner. Khi cần assert một sự kiện quan trọng, ưu tiên **business state** hoặc một test appender/observation registry có cấu hình chính xác, không parse text log toàn ứng dụng bằng một regex yếu.

### Math.multiplyExact có thể throw

Ví dụ `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân tràn kiểu `long`. Đây là contract hợp lệ của Java 17, nhưng nếu production cần map thành domain exception (vd. invalid amount) thì phải thiết kế thêm và test riêng. Bài tập trung vào report nên không giả định một hệ thống pricing hoàn chỉnh.

## 8. PricingServiceTest: parameterized, skipped và intentionally failed

`src/test/java/com/example/report/PricingServiceTest.java`:

```java
package com.example.report;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PricingServiceTest {

    private static final Logger log =
            LoggerFactory.getLogger(PricingServiceTest.class);

    @Autowired
    PricingService pricing;

    @ParameterizedTest(
            name = "[{index}] price={0} quantity={1} expected={2}")
    @CsvSource({
        "125, 2, 250",
        "199, 3, 597",
        "0, 4, 0"
    })
    void calculatesExpectedTotals(
            long price,
            int quantity,
            long expected) {

        assertEquals(
                expected,
                pricing.totalInCents(price, quantity));
    }

    @Test
    @DisplayName("rejects negative quantities")
    void rejectsNegativeQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> pricing.totalInCents(125, -1));

        assertTrue(error.getMessage()
                .contains("non-negative"));
    }

    @Test
    void logsASafeDiagnosticEvent(TestInfo testInfo) {
        long total = pricing.totalInCents(75, 2);

        log.info(
                "test-check method={} scenario={} totalCents={}",
                testInfo.getTestMethod()
                        .orElseThrow()
                        .getName(),
                "normal-pricing",
                total);

        assertEquals(150L, total);
    }

    @Test
    @DisplayName("intentional diagnostic failure (opt in)")
    @EnabledIfSystemProperty(
            named = "demo.fail",
            matches = "true")
    void intentionalFailureForReportTraining() {
        long actual = pricing.totalInCents(125, 2);

        // Cố tình sai: actual là 250, expected là 251.
        assertEquals(
                251L,
                actual,
                "diagnostic demo: expected amount mismatch");
    }
}
```

**Số phương thức khai báo:** ba phương thức `@Test` thông thường (hai luôn chạy, một conditional) và một `@ParameterizedTest` có ba invocations. Nói chính xác hơn: **4 test methods trong source**, nhưng **6 test cases/invocations tiềm năng** khi JUnit thực thi (3 parameterized cases, 2 always-enabled tests, 1 conditional test). Trạng thái xanh/đỏ/skip phụ thuộc cờ `demo.fail` và việc test có chạy thành công hay không.

### Vì sao phải phân biệt method count với case count?

JUnit parameterized test tạo nhiều executions từ **một** Java method. Dùng `@RepeatedTest` hay `@TestFactory` có thể tạo thêm executions. Một số reporters đếm **testcases** chứ không đếm phương thức có annotation; điều tra CI cần đọc `tests`, `failures` và `skipped` từ output thật, không suy bằng cách đếm annotation.

### Test cố ý fail chỉ chạy khi bật cờ

Bình thường, `@EnabledIfSystemProperty(named="demo.fail",matches="true")` disable riêng method failure. Khi `-PdemoFail=true` được Gradle build script truyền sang test JVM, JUnit sẽ chạy method và `assertEquals(251L,250L,...)` fail. Đây là **một cơ chế thực hành**, không phải tình huống app production tự bị lỗi.

Đừng dùng `@Disabled` rồi cố chạy test bằng `--tests`; `@Disabled` vẫn không execute chỉ vì Gradle filter chọn nó. Muốn bật/tắt có điều kiện, dùng conditional annotation hoặc tag/feature flag có cấu hình tường minh.

## 9. Lệnh chạy trên macOS/Linux và Windows

Nếu repository đã có Gradle Wrapper:

```bash
./gradlew clean test
./gradlew clean test -PdemoFail=true
./gradlew test --tests 'com.example.report.PricingServiceTest'
./gradlew test --tests 'com.example.report.PricingServiceTest.intentionalFailureForReportTraining' -PdemoFail=true
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat clean test -PdemoFail=true
.\gradlew.bat test --tests "com.example.report.PricingServiceTest"
```

Nếu chưa có Wrapper, dùng Gradle 8.x tương thích đã cài hoặc tạo Wrapper theo chuẩn project:

```bash
gradle clean test
gradle clean test -PdemoFail=true
```

**Lưu ý:** project tree trong bài chỉ liệt kê các file nội dung. Nếu bạn không tự tạo Wrapper, `./gradlew` sẽ không tồn tại. Không lầm lỗi “command not found” với failure của JUnit.

### Các flags Gradle hữu ích

| Lệnh/flag | Khi dùng | Lưu ý |
| --- | --- | --- |
| `clean test` | Cần report mới không lẫn file từ lần trước | Xóa build outputs trước khi chạy |
| `--tests 'package.Class.method'` | Reproduce một testcase | Tên Java method có thể khác display name |
| `--rerun-tasks` | Task được đánh dấu UP-TO-DATE nhưng cần chạy lại | Có thể tốn thời gian; không phải cơ chế sửa flaky |
| `--stacktrace` | Xem Gradle build/task failure stack | Test assertion thường rõ hơn trong HTML/XML |
| `--info` | Cần chi tiết Gradle task/classpath/startup | Log nhiều, nguy cơ lộ thông tin |
| `--debug` | Điều tra sâu và có quyền phù hợp | Rất verbose, không upload tùy tiện |
| `--continue` | Chạy tiếp các tasks độc lập khi task khác fail | Build cuối vẫn fail; không đảm bảo mọi dependent task chạy |
| `--fail-fast` | Dừng thử nghiệm sớm khi test đầu fail | Report không thể coi là toàn bộ suite |
| `--no-daemon` | CI one-off muốn process lifecycle rõ | Không liên quan trực tiếp report contents |
| `--console=plain` | Log ổn định khi pipe vào file | Không thay stacktraces hay status |

Khi bật failure scenario, **process exit code phải khác 0**. Tắt `-PdemoFail=true` trước khi commit CI workflow thông thường. Không dùng `ignoreFailures=true` cho một test quan trọng chỉ để pipeline xanh; nó có thể che một regression.

## 10. Đường dẫn Gradle JUnit XML và HTML thực tế

Với một project Gradle Java đơn và task `test` mặc định:

```text
build/
├── test-results/
│   └── test/
│       ├── TEST-com.example.report.PricingServiceTest.xml
│       └── binary/
│           └── ... internal Gradle test result data ...
└── reports/
    └── tests/
        └── test/
            ├── index.html
            ├── classes/
            │   └── com.example.report.PricingServiceTest.html
            ├── packages/
            │   └── com.example.report.html
            ├── css/
            └── js/
```

Đây là **cấu trúc điển hình**, không bảo đảm tên từng CSS/JS file giữ nguyên giữa Gradle versions. **Đường dẫn output của một task là theo tên task**: nếu có `integrationTest` task, JUnit XML và HTML report thường nằm ở `build/test-results/integrationTest/` và `build/reports/tests/integrationTest/`.

### Không chỉ upload index.html

Trang `index.html` thường link tới pages theo class/package cùng CSS/JS. Nếu chỉ upload một file HTML mà không có subfolders, người điều tra có thể thấy trang trắng, thiếu style hoặc links lỗi. Hãy upload **toàn bộ `build/reports/tests/test/`** và mở file index sau khi tải/extract artifact.

### Binary test results dùng để làm gì?

Gradle lưu dữ liệu binary nội bộ để tạo/aggregate reports. Đó **không phải JUnit XML** và không phải định dạng portable khuyên dùng cho các CI parsers. Nếu cần giữ binary results cho Gradle report aggregation chính thức, có thể thu riêng nhưng phải quản lý tương thích Gradle versions. Khi chỉ cần human/CI inspection, XML và HTML thường đủ.

## 11. JUnit XML là một pseudo-standard, không phải schema chung bất biến

Một file XML từ Gradle thường có ý nghĩa cấu trúc như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite
    name="com.example.report.PricingServiceTest"
    tests="..."
    skipped="..."
    failures="..."
    errors="..."
    time="...">
  <testcase
      classname="com.example.report.PricingServiceTest"
      name="calculatesExpectedTotals(...)"
      time="..."/>
  <testcase
      classname="com.example.report.PricingServiceTest"
      name="intentionalFailureForReportTraining()"
      time="...">
    <failure type="..." message="...">
      ...stack trace...
    </failure>
  </testcase>
</testsuite>
```

**Đây là XML sơ đồ**, với dấu `...` biểu diễn attributes/stacktrace chưa biết; **không phải XML file thật do ví dụ vừa chạy**. Số tests, tên parameterized case, time, exception type và stack trace phải được đọc từ generated XML. Đừng chép số/failure message được đoán vào báo cáo CI.

### Ý nghĩa các phần tử

| Thành phần | Ý nghĩa phổ biến | Cảnh báo |
| --- | --- | --- |
| `<testsuite>` | Group/class/suite với summary attrs | Không phải producer nào cũng có attributes như nhau |
| `<testcase>` | Một invocation được report | Parameterized/repeated tests có thể sinh nhiều entries |
| `<failure>` | Assertion/test failure | `message` và text có thể chứa data nhạy cảm |
| `<error>` | Exception/error của test runner hay test | Một số producer biểu diễn khác `failure` |
| `<skipped>` | Test chưa chạy do condition/disable/skip | Skipped không có nghĩa passed |
| `<system-out>` | Captured standard output | Có thể ở suite/testcase level tùy config |
| `<system-err>` | Captured error output | Có thể chứa stack traces, tokens |
| `time` | Thời gian execution do producer report | Không phải SLA, chưa chắc gồm context startup |
| `tests`, `failures`, `errors`, `skipped` | Summary counters | Cần hiểu reruns/merges/containers và producer |

Gradle gọi định dạng này **JUnit XML pseudo-standard**, vốn được các CI tools hỗ trợ rộng nhưng không có schema thống nhất cho mọi extensions. Đừng viết parser dựa vào một attribute không có ở mọi XML producer.

### Một failure không nhất thiết là cùng một defect với trước

Khi retry plugin chạy lại test, có thể xuất hiện nhiều `<testcase>` executions hoặc thông tin rerun/flaky tùy Gradle report option. `junitXml.mergeReruns` khi được bật chỉ **thay đổi cách ghi report**, **không tự tạo cơ chế retry**. Một CI parser không hiểu `<flakyFailure>` có thể coi testcase là pass và che lỗi ban đầu. Vì vậy khi điều tra flaky, lưu raw XML và retry logs/attempt metadata, không chỉ nhìn summary green.

## 12. HTML report: cách đọc để điều tra lỗi theo class và method

Mở `build/reports/tests/test/index.html`. Trong một report Gradle thông thường, điều tra theo thứ tự:

1. **Summary:** số tests/failures/ignored, duration và success rate. Xem đây là summary của **task và tập tests thực sự đã chạy**, không phải lời bảo đảm toàn repo pass.
2. **Packages:** khoanh vùng packages và modules có failure, ví dụ `com.example.report`.
3. **Classes:** đi vào `PricingServiceTest`; tập trung methods có fail/error/skip.
4. **Test case:** mở mục lỗi có assertion message và stacktrace; tìm dòng source fail thật đầu tiên ở code của bạn.
5. **Standard output/error:** xem khi report có captured outputs; tránh chọn log đầu tiên một cách máy móc nếu nhiều threads in xen kẽ.
6. **Liên hệ commit:** so sánh failure mới xuất hiện sau thay đổi nào, không suy “mọi lần fail cùng một lỗi” chỉ từ test class name.

Khi dùng `@ParameterizedTest`, nhiều dòng invocation có thể cùng Java method name nhưng khác input/display name. Đọc case ID, parameters đã được phép log và exception. Nếu report format gộp method, cần trace input qua failure messages có context nhưng **không** chứa PII.

### Vì sao không dùng HTML làm nguồn máy parse?

HTML là định dạng hiển thị và có thể đổi CSS/DOM giữa Gradle releases. CI dashboards nên đọc JUnit XML hoặc result APIs; con người dùng HTML để drill down. Nếu phải tạo aggregate dashboard, dùng parser chuẩn/CI integration, không regex HTML.

## 13. Console log: nhìn đúng lỗi đầu tiên và đúng boundary

Có ba nguồn logs thường được trộn khi chạy Gradle:

- **Gradle build logs:** tasks, dependency resolution, compiler diagnostics, toolchain/configuration failure.
- **Spring Boot application/test logs:** `ApplicationContext` startup, bean creation, profiles, Hibernate/JDBC, HTTP clients, Logback/SLF4J.
- **Test stdout/stderr & stack traces:** assertions, exception chains, test framework events, tự in của người viết test.

Một log bị noisy có thể chứa vài trăm dòng “WARN” không liên quan. Khi fail, xác định `Task :test FAILED` hay `Task :compileTestJava FAILED` trước. Nếu test thực thi, đi tới report class/method và tìm **first meaningful `Caused by`** hoặc assertion line, không chỉ “BUILD FAILED” cuối file.

### Case: Spring context failed to load

Nếu thấy `Failed to load ApplicationContext`, `BeanCreationException`, `UnsatisfiedDependencyException` hay `NoSuchBeanDefinitionException`, đây thường là một **startup/wiring failure**, không phải assertion của business method. Xem active profiles, property binding, required dependency, migrations, port collisions và conditional auto-config. `@SpringBootTest` có thể cache context; nhiều test methods fail cùng root cause. Đừng đếm mỗi failed method thành một defect độc lập.

### Case: Timeout hoặc Testcontainers

Nếu thấy `ContainerLaunchException`, Docker socket unavailable, image pull failure, DB connection refused hoặc Kafka partition assignment timeout, lỗi hạ tầng/fixture có thể xảy ra trước khi assertion. Cần thêm container logs, image version, resource limits, readiness checks. Không suy rằng logic transaction sai chỉ vì `@SpringBootTest` không tạo được DataSource.

## 14. Lưu console log trong terminal mà vẫn giữ exit code

Linux/macOS Bash:

```bash
set -o pipefail
./gradlew --no-daemon clean test --stacktrace \
  --console=plain 2>&1 | tee gradle-test-console.log
```

**`set -o pipefail` rất quan trọng.** Không có nó, status của pipeline thường là status của `tee`; Gradle có thể fail nhưng `tee` ghi log thành công nên CI shell trả 0. Với pipefail, lỗi Gradle tiếp tục làm step fail trong khi log vẫn được lưu để uploader chạy sau.

### Không dùng một path bị clean xóa

Nếu chạy `./gradlew clean test` và cùng lúc `tee build/diagnostics/gradle.log`, task `clean` có thể xóa `build/` khi `tee` đang mở file; kết quả log có thể bị mất/ghi lỗi. Trong ví dụ, `gradle-test-console.log` nằm ở **project root**, ngoài folder `build` bị xóa bởi `clean`.

### Không làm xanh giả

Sai:

```bash
./gradlew test || true
```

Sai nếu dùng để che lỗi:

```bash
./gradlew test 2>&1 | tee test.log
# Không bật pipefail: status Gradle có thể bị mất.
```

Một step thu artifact có thể dùng `if: always()`, nhưng **step chạy test phải giữ exit code lỗi**. Nếu workflow policy muốn tiếp tục nhiều independent test tasks, dùng Gradle `--continue` và vẫn giữ final nonzero, hoặc tổ chức jobs riêng cho từng task.

### Windows PowerShell

PowerShell 5.1 và PowerShell 7 có xử lý native process pipelines/`$LASTEXITCODE` khác nhau, nên không copy nguyên cú pháp Bash `set -o pipefail` sang PowerShell. Nếu cần log trên Windows agent, dùng command wrapper riêng ghi console và **trả chính xác native process exit code**; test bằng một lệnh cố ý fail trước khi chấp nhận wrapper đó. Đơn giản nhất cho demo là chạy `.\gradlew.bat test` trực tiếp và lấy log do CI runner tự thu.

## 15. Script nhỏ để tổng hợp JUnit XML

Một số hệ thống CI đã có JUnit-report parser; nếu chỉ muốn in summary nhanh ở local/CI không cần thêm library, có thể dùng Python standard library. Script sau đọc đúng files `TEST-*.xml` từ Gradle result directories, đếm `<testcase>` và phân biệt fail/error/skip. Nó **không in message, raw logs hay stack traces** để giảm nguy cơ dữ liệu nhạy cảm trong CI summary.

Tạo `scripts/summarize_junit.py`:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

result_root = Path("build/test-results")
files = sorted(result_root.rglob("TEST-*.xml"))

if not files:
    print("No JUnit XML files found under build/test-results")
    print("Check whether the test task actually executed.")
    sys.exit(2)

total = 0
passed = 0
failed = 0
skipped = 0
failed_names = []

for path in files:
    try:
        tree = ET.parse(path)
    except ET.ParseError as error:
        print(f"Malformed report: {path}: {error}")
        sys.exit(2)

    for case in tree.iter("testcase"):
        total += 1
        failure = case.find("failure")
        error = case.find("error")
        skip = case.find("skipped")

        if failure is not None or error is not None:
            failed += 1
            classname = case.get("classname", "unknown")
            name = case.get("name", "unknown")
            failed_names.append(f"{classname}#{name}")
        elif skip is not None:
            skipped += 1
        else:
            passed += 1

print(f"XML files: {len(files)}")
print(f"Test cases: {total}")
print(f"Passed: {passed}")
print(f"Failed or error: {failed}")
print(f"Skipped: {skipped}")

if failed_names:
    print("Failed cases:")
    for name in failed_names:
        print(f"  - {name}")

# Báo cáo thông tin; Gradle test step giữ trạng thái gate.
# Nếu không có XML hoặc XML parse lỗi, script trả 2.
```

### Điều script làm và không làm

- Dùng `ElementTree`, không parse XML bằng regex.
- Đếm từng `testcase` thực tế trong files; không suy số từ annotations.
- Phân biệt `failure`, `error`, `skipped` bằng phần tử XML.
- Nếu files không tồn tại, **trả exit code 2**, báo cần xem lỗi build sớm.
- Không in nội dung exception, secrets hoặc stdout.
- **Không** quyết định build status: status của Gradle test step vẫn là nguồn kiểm soát CI, script chỉ giúp điều tra.
- Chỉ đọc `build/test-results` của **module hiện tại**; multi-project cần script nhận paths hoặc chạy từ từng subproject.
- Nếu report có `<flakyFailure>`, retry metadata, multiple test runs hay custom producer, summary đơn giản này chưa diễn giải đủ; cần CI parser tương thích/thiết kế rộng hơn.
- Nếu có duplicated XML files từ nhiều tasks/shards dưới cùng root, phải bảo đảm scope không double count.
- Với untrusted test case names, nên giới hạn/escape text in ra CI output; demo không lấy tên từ external user input.

Lệnh chạy:

```bash
python3 scripts/summarize_junit.py
```

**Không dùng script để “sửa” CI gate.** Nếu Gradle fail mà summary parser tình cờ in `Failed or error: 0`, nguyên nhân có thể là fail ở `compileTestJava`/Docker/setup, hoặc XML chỉ phản ánh một subset; CI phải vẫn đỏ.

## 16. GitHub Actions: giữ báo cáo ngay cả khi test thất bại

Tạo `.github/workflows/test-reports.yml`:

```yaml
name: Spring test reports

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run tests, retain Gradle exit status
        shell: bash
        run: |
          set -o pipefail
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace \
            --console=plain 2>&1 | tee gradle-test-console.log

      - name: Summarize JUnit results
        if: ${{ always() }}
        shell: bash
        run: |
          set -o pipefail
          python3 scripts/summarize_junit.py | tee junit-summary.txt

      - name: Upload test diagnostics
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: junit-diagnostics-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            build/test-results/test/
            build/reports/tests/test/
            gradle-test-console.log
            junit-summary.txt
          if-no-files-found: warn
          retention-days: 7
```

**Đây là một workflow tối giản cho repository có Gradle Wrapper.** Cần tạo/commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và Wrapper JAR đúng chuẩn trước khi workflow chạy. `chmod +x ./gradlew` chỉ cấp executable bit, không tạo Wrapper nếu file thiếu. Không thêm `-PdemoFail=true` vào workflow mặc định.

### Giải thích các điểm quan trọng trong YAML

- `actions/checkout` lấy source/Gradle Wrapper.
- `actions/setup-java` chọn JDK 17.
- `gradle/actions/setup-gradle` thiết lập Gradle caching và tích hợp Gradle action trong CI; tránh cấu hình trùng cache ở nhiều actions mà không hiểu effects.
- `set -o pipefail` giữ result của Gradle khi pipe qua tee.
- `2>&1 | tee ...` lưu stdout và stderr vào cùng console log, thuận tiện xem stack/error.
- `if: always()` đảm bảo summary và upload steps **vẫn được xem xét chạy sau test failure**; nếu runner bị hủy cứng hoặc job bị kill thì không có bảo đảm uploader hoàn tất.
- `actions/upload-artifact@v4` upload toàn bộ directories và logs làm một artifact.
- `name` chứa run ID/attempt để tránh trùng trong một workflow run/retry và giúp trace CI iteration.
- `if-no-files-found: warn` không biến một lỗi compile (chưa tạo XML/HTML) thành lỗi uploader thứ hai. Console log vẫn là tài liệu quan trọng.
- `retention-days: 7` là ví dụ; repository/org/enterprise retention policies có thể áp giới hạn thấp hơn.
- `permissions: contents: read` là principle of least privilege cho workflow đơn giản.

**Không bắt buộc dùng upload-artifact v4 mãi mãi.** Đây là major version hiện có tài liệu GitHub Actions hỗ trợ; khi team nâng major, kiểm tra release notes/compatibility và cân nhắc pin action bằng immutable commit SHA theo chính sách supply chain.

### Điều gì xảy ra khi cố ý chạy test fail?

Nếu cấu hình một workflow **chẩn đoán riêng** truyền `-PdemoFail=true`, task `test` trả nonzero vì assertion; step chạy test đỏ. Các steps `if: always()` vẫn có thể đọc XML/HTML/log và upload artifact. Trạng thái job cuối cùng **vẫn fail**. Không cần `continue-on-error: true` ở test step chỉ để chạy uploader.

### Điều gì xảy ra khi compile fail?

`compileTestJava` hoặc dependency resolution có thể fail trước test execution: `build/test-results/test/` không tồn tại. Summary script trả 2 (và có thể tạo `junit-summary.txt` với diagnostic), uploader cảnh báo paths thiếu nhưng vẫn giữ `gradle-test-console.log` nếu shell step đã tạo file. Hãy đọc compile error trước; không coi “No JUnit XML” là một test method thất bại.

## 17. GitHub Actions artifact là một archive, không phải một JUnit parser

Sau khi workflow hoàn tất, tab **Actions → workflow run → Artifacts** cung cấp artifact để tải. Tải và giải nén nguyên cây; mở `build/reports/tests/test/index.html` ở máy có browser. Một số security policies hạn chế xem HTML trực tiếp trong CI UI; download/view cục bộ bằng browser phù hợp.

Upload-artifact **không tự tạo biểu đồ tests passed/failed** từ XML. Nếu muốn có annotation/check runs/test dashboard, cần một action/plugin khác có thể đọc JUnit XML, và phải đánh giá quyền của nó khi chạy trên Pull Request từ forks/untrusted code. Không cung cấp `checks: write` hay repository tokens quá rộng cho một test-report workflow chỉ upload files.

### Retention và quyền truy cập

Report có thể chứa stack trace, filesystem path, môi trường, headers hoặc test input. Artifact retention phải cân nhắc:
- độ nhạy dữ liệu;
- thời gian đội cần triage;
- quota/storage cost;
- compliance/data residency;
- quyền tải artifact của nhóm/đối tác;
- cách purge/expire và chia sẻ ra ngoài.

**Không upload .env, credentials files, Docker config, kubeconfig, full application heap dump hoặc raw production data.** Nếu buộc phải giữ một dump, cần sanitization và storage ACL đúng; đừng gom tất cả `build/` vào artifact để dễ rồi vô tình chứa build secrets.

## 18. Maven tương đương: Surefire và Failsafe

Bài runnable dùng Gradle, nhưng khi điều tra dự án Maven, paths khác:

| Công cụ | XML/test reports thường ở | Mục đích |
| --- | --- | --- |
| Gradle `test` | `build/test-results/test/` | Test task XML |
| Gradle `test` HTML | `build/reports/tests/test/` | Human-readable |
| Maven Surefire | `target/surefire-reports/` | Unit tests; XML và .txt summaries |
| Maven Failsafe | `target/failsafe-reports/` | Integration tests; thường dùng phases integration-test/verify |
| Jenkins JUnit publisher | Theo glob được cấu hình | CI test trend/dashboard |
| GitLab test report | Theo `artifacts:reports:junit` | Merge request/pipeline test UI |

Maven `surefire-reports` thường có `TEST-*.xml` và một file `*.txt` theo test class; **không mặc định** có đúng cấu trúc HTML như Gradle `build/reports/tests/test/index.html`. Failsafe chạy integration tests theo lifecycle và cần goal `verify` để build fail đúng khi integration tests fail. Đừng dùng glob Surefire cho Failsafe rồi báo “No tests” trong khi tests có chạy.

### Đừng áp cùng pattern cho mọi build system

Nếu CI đang publish `target/surefire-reports/TEST-*.xml`, thay đổi Gradle task sẽ không đi vào dashboard đó. Mỗi module/task phải biết producer và output path. Nếu dùng Maven Surefire JSON/JUnit Platform launcher chuyên biệt, kiểm tra format/paths thực, không đoán từ tên framework.

## 19. Multi-module và nhiều Test tasks: tránh bỏ sót failures

Trong Gradle multi-project:

```text
root/
├── service-a/build/test-results/test/TEST-*.xml
├── service-a/build/reports/tests/test/
├── service-b/build/test-results/test/TEST-*.xml
├── service-b/build/test-results/integrationTest/TEST-*.xml
└── service-b/build/reports/tests/integrationTest/
```

Workflow single-module ở mục 16 chỉ upload root `build/...`. Với nhiều modules, cần một uploader glob thích hợp, ví dụ:

```yaml
path: |
  **/build/test-results/**/TEST-*.xml
  **/build/reports/tests/**
  gradle-test-console.log
```

Đây là **snippet paths**, không phải workflow đầy đủ. Kiểm tra glob matching thực trên CI và lưu đủ relative path để phân biệt cùng class name xuất hiện trong modules khác nhau.

### Test task mới cần report path mới

Nếu tạo `integrationTest` task riêng, build plugin có thể đặt report ở `build/test-results/integrationTest`, không phải `.../test`. Đừng chỉ upload `**/test-results/test` rồi tuyên bố integration suite xanh. Nếu Gradle báo `:module:integrationTest FAILED`, cần đọc report của đúng task đó.

### Aggregated report

Gradle hỗ trợ `TestReport` và **Test Report Aggregation Plugin** để tổng hợp dữ liệu giữa nhiều Test tasks/projects, khi cấu hình producer/variants đúng. Một aggregated HTML không nên được tự chế bằng cách nối nội dung của nhiều `index.html`; paths/CSS/links sẽ hỏng. Raw XML cần giữ nguyên để CI parser dùng independently.

### Matrix builds và tên artifacts

Nếu workflow có matrix JDK/OS, mỗi job/variant cần artifact name **khác nhau**, chẳng hạn:

```yaml
name: reports-${{ matrix.os }}-jdk${{ matrix.java }}-${{ github.run_id }}
```

Đây là **snippet**, chỉ dùng khi workflow khai báo `matrix.os` và `matrix.java` tương ứng. Với `upload-artifact@v4`, nhiều jobs không nên cố upload nối tiếp vào **cùng một immutable artifact name**; hãy dùng mỗi variant một artifact hoặc chiến lược merge được hỗ trợ.

## 20. Làm rõ fail, error, skipped và aborted

JUnit Jupiter test outcomes có nhiều trạng thái:

- **Successful:** test case đã chạy và assertions pass.
- **Failed:** assertion/test execution ném lỗi và fail.
- **Aborted:** test dừng vì assumption (`Assumptions.assumeTrue`) hoặc điều kiện tương ứng; reporter có thể hiển thị skipped/aborted theo format.
- **Disabled/Skipped:** test bị `@Disabled`, `@EnabledIfSystemProperty` không match hoặc filter không chọn; không có nghĩa test logic đúng.
- **Not discovered/not executed:** test không được JUnit Platform tìm thấy, Gradle filter loại hoặc build fail trước Test; không nhất thiết có `<testcase>` để báo skipped.

Vì vậy, **0 failed tests không đồng nghĩa toàn bộ test suite đã chạy**. Theo dõi tổng test count, số skipped, thay đổi số lượng cases so với baseline và các tasks thực sự executed.

### Khi test discovery bằng 0

Kiểm tra:
- `useJUnitPlatform()` có được bật?
- Jupiter engine có trên test runtime classpath?
- Test class/method được Gradle test source set nhận diện?
- `--tests` filter có match đúng class/method?
- Có test tasks khác ngoài `test`?
- Tests có `@Disabled` hoặc conditions không?
- Có cấu hình includes/excludes/tags không mong muốn?
- Build có dừng ở compile hay integration setup không?

Một pipeline “xanh” nhưng chạy 0 tests là một regression CI policy cần được phát hiện, không phải thành tích.

## 21. Logs nên có gì để điều tra nhanh?

Một dòng log an toàn, dễ tìm, nên giúp xác định:

- `event=...` hoặc operation name.
- `correlationId`/`traceId` hoặc test run ID an toàn, không phải secret.
- `outcome`: success/error/timeout/rejected.
- `dependency` logical name (không high-cardinality).
- `attempt` nếu có retry.
- `elapsedMs` hoặc timing metrics khi có measurement thật.
- exception class và stack trace ở lỗi quan trọng.
- test class/method/run ID khi có test infrastructure log.
- môi trường: app version, JVM version, active profiles và CI shard (metadata an toàn).

**Không dùng email, raw JWT, Authorization header, password, customer payment data hoặc full request body làm correlation ID.** Trong metrics, tránh dùng user/order IDs làm tags vì high cardinality. Trong log, quyết định retention/ACL/redaction phải tuân policy của tổ chức.

### Liên kết log với một test method

JUnit XML với `outputPerTestCase=true` giúp gắn test stdout/stderr vào testcase theo cách nhiều parsers hỗ trợ. Nhưng nếu test khởi chạy worker threads hoặc HTTP server, background logs có thể đến sau method hoàn thành hoặc được ghi ở process context khác. Đừng dựa vào việc Gradle capture chắc chắn quy mọi dòng log async đúng method.

Với Spring Boot integration tests, dùng test-specific correlation IDs trong event/request; chờ async work có timeout rồi assert business outcome trước khi test kết thúc. Không dùng `Thread.sleep` làm cách ghép log lỏng lẻo.

## 22. Khi nào cần giữ thêm artifacts ngoài JUnit XML/HTML?

| Loại test | Artifacts có giá trị | Lưu ý |
| --- | --- | --- |
| Spring MVC/MockMvc | Safe request/response summaries, MvcResult diagnostics | Redact headers/body |
| Spring WebFlux | StepVerifier failure trace, filtered logs | Không log sensitive Reactor Context |
| Testcontainers PostgreSQL | Container logs, DB version, SQL migration failure context | Không upload full DB/credentials |
| Kafka/RabbitMQ | Topic/group/queue names test-owned, sanitized broker/listener logs | Không xóa shared topics để “lấy sạch” |
| REST client | MockWebServer/WireMock request journal, response status/timing | Redact Authorization, cookies |
| Browser/E2E | Screenshot, trace, short screen recording | Blur PII, remove access tokens |
| Performance | Histograms, samples, JVM GC logs | Không coi perf test là JUnit threshold duy nhất |
| Flaky/concurrent | Thread dump, async state, seed, shard metadata | Dump có thể chứa sensitive memory/path info |
| Migration/schema | Flyway/Liquibase logs, schema revision | Không lưu production dumps |
| Security/auth | Redacted error codes/status, audit event ID | Không lưu raw secrets |

### Thu logs Testcontainers

Khi chạy một `PostgreSQLContainer`/Kafka container trong dedicated test environment, test framework có thể lấy `container.getLogs()` sau fail hoặc stream qua log consumer. **Không** upload nguyên log từ một shared production database, và không giả rằng container logs luôn có đủ error business state. Thay vì thu tất cả container outputs, nên lọc theo instance ID/test run và giới hạn size.

### Screenshots và browser traces

Một test UI có thể xuất screenshot/traces khi fail. Cần lưu đúng folder theo test ID và upload bằng uploader `if: always()`. Hãy bảo đảm screenshot không hiển thị token, private customer data, bản đồ vị trí riêng tư hoặc payment info; dùng synthetic fixtures, mask/redaction và artifact ACL.

### Heap dumps và thread dumps

Thread dumps rất hữu ích khi deadlock/timeouts; heap dumps cực kỳ nhạy cảm vì có thể chứa credentials và dữ liệu người dùng trong memory. Chỉ thu khi được phép và lưu trong kênh bảo mật thích hợp, không cho mọi PR artifacts mở rộng quyền xem.

## 23. Phân loại nguyên nhân theo nơi failure bắt đầu

| Biểu hiện | Nghi vấn đầu tiên | Nguồn đọc chính |
| --- | --- | --- |
| `:compileJava FAILED` | Java syntax/toolchain/dependency | Gradle console log |
| `:compileTestJava FAILED` | Test code/imports/API mismatch | Gradle console log |
| `:test FAILED` + assertion | Business assertion sai | JUnit XML/HTML |
| `Failed to load ApplicationContext` | Spring bean/config/profile/setup | XML stack + Spring logs |
| `ContainerLaunchException` | Docker image/network/container lifecycle | Console + container logs |
| `BindException Address already in use` | Fixed port/shared resource | Console + test setup |
| `SocketTimeoutException` | Downstream chậm/network | App/HTTP mock logs + cause chain |
| `AssertionFailedError expected/actual` | Input, value, assertion | HTML testcase |
| `TimeoutException` trong async test | Await signal chưa hoàn thành | Test trace + executor/event logs |
| JUnit XML trống, build fail | Test chưa execute hoặc report path sai | Build log/tasks |
| Skipped tăng bất thường | Conditions, tags, filters | XML plus build configuration |
| CI green, test log cho thấy exception | Exception bị catch/suppress hoặc non-gating task | Test logic/Gradle exit status |
| Test fail chỉ khi chạy cả suite | Shared state/parallelism/order/flaky | Historical artifacts, run ID, seed |

**Đừng sửa bằng cách tăng timeout hoặc retry trước khi xác định nguyên nhân.** Một deadlock sẽ không hết về bản chất khi timeout tăng từ 5s lên 30s; nó chỉ làm CI chậm hơn.

## 24. Quy trình điều tra một failure trong 10 bước

1. Mở **job status + commit SHA + JDK/Gradle versions**, xác nhận test step thật sự trả nonzero hay pipeline đã mask exit.
2. Tìm **failing Gradle task** đầu tiên. Nếu chưa chạy tests, ưu tiên console log thay vì chờ XML xuất hiện.
3. Tải artifact chứa **toàn bộ XML/HTML/log**, không chỉ screenshot của dòng đỏ cuối.
4. Mở HTML index, chọn class/method fail; xác định assertion hay error/setup failure.
5. So sánh XML: `classname`, `name`, `failure`/`error`/`skipped`, số invocations và stack.
6. Tìm first meaningful `Caused by` trong exception chain; phân biệt Spring startup vs assertion vs external dependency.
7. Dùng correlation/run ID nối logs với test input và output; không log secrets.
8. Reproduce đúng test method/parameter/filter bằng `--tests` và same JVM/profile/config; dùng `--rerun-tasks` khi cần tránh stale up-to-date.
9. Chạy lại ở phạm vi **cả suite hoặc parallel shard** nếu chỉ fail khi nhiều tests chia tài nguyên; single-test pass không phủ định race.
10. Kết luận root cause, lưu evidence, thêm regression assertion và chỉ sau đó cân nhắc retry/quarantine cùng issue tracking.

### Tại sao không chạy lại ngay trước khi tải artifacts?

Một retry có thể làm xanh tạm thời và xóa dấu vết race, file tạm, failing container logs hoặc timing. Thu snapshot lần thất bại trước; sau đó mới reproduce. Nếu CI artifacts expire sau vài ngày, cần download kịp trong retention window.

## 25. Flaky tests và retries: đừng tạo tín hiệu xanh giả

Flaky test là một test có kết quả thay đổi giữa các lần chạy **khi code và đầu vào được cho là giống nhau**. Nguyên nhân thường có:

- Shared database/schema/queue/cache hoặc static mutable state.
- `Thread.sleep` thay vì synchronization/await có deadline.
- Clock/timezone và random seed không kiểm soát.
- Test execution order hoặc parallel scheduling.
- Port/folder fixed names.
- External network/provider.
- Resource exhaustion trên CI.
- Spring TestContext cache và lifecycle container không tương thích.
- Undeclared dependency giữa tests.
- Browser animation/timing và non-deterministic selectors.

### Retry policy

Một retry plugin có thể có giá trị khi thu thập thêm signal, nhưng **không được coi là sửa defect**. Nên giữ:
- số lần attempts;
- first failure message/stack;
- bản ghi case đã pass-on-retry;
- seed/shard/environment;
- issue tracking và flakiness rate.

Nếu bật Gradle `junitXml.mergeReruns=true`, cần chắc chắn CI JUnit parser hiểu `flakyFailure`; không phải parser nào cũng hiển thị rerun failures. XML “xanh” vì parser bỏ qua unknown rerun tags có thể che regression.

### Quarantine phải minh bạch

Nếu một integration test bị disable vì môi trường bị lỗi, ghi rõ ticket, owner, deadline và coverage tạm thay thế. Không vĩnh viễn `@Disabled`/`ignoreFailures` chỉ để đạt green dashboard.

## 26. Bảo vệ báo cáo khỏi dữ liệu nhạy cảm

JUnit XML/HTML có thể chứa:

- AssertJ/JUnit expected/actual values.
- Full SQL query và bound params nếu logging được bật quá rộng.
- HTTP request/response headers/body.
- JWT, session cookies, password, API key trong stack traces/logs.
- Local paths hoặc hostnames.
- Screenshots/traces của giao diện đã login.

Các bước nên làm:

1. Dùng **synthetic test data**, không dùng production customer records.
2. Tắt verbose request/SQL parameter logging mặc định trên CI public forks.
3. Redact Authorization, Cookie, Set-Cookie, credentials và PII trước khi ghi files.
4. Không đặt secret trong assertion message, `@DisplayName`, test case parameters hoặc artifact filenames.
5. Giới hạn quyền download artifacts theo repository/org policy; kiểm soát PR from forks.
6. Cấu hình retention phù hợp; không lưu vô hạn.
7. Không upload entire home directory, `.env`, kubeconfig, Docker credentials, cloud credentials.
8. Cân nhắc hạn chế `includeSystemOutLog/ErrLog` nếu tests có nguy cơ in sensitive data; khi tắt, vẫn giữ enough sanitized logs qua kênh được kiểm soát.
9. Thêm giới hạn file size/dump collection, tránh log hàng GB gây chi phí và quá tải.
10. Khi cần chia sẻ với vendor, tạo một sanitized bundle riêng thay vì chuyển nguyên CI artifact.

### Redaction trước upload không phải sau upload

Nếu một secret đã xuất hiện trong console log và artifact được upload, xóa/redact bản tải về sau đó không sửa bản lưu trên CI. Phòng từ nguồn: không in secrets, test fixture sạch, log filters và scanner/retention policy. Nếu lộ secret thật, kích hoạt quy trình xử lý sự cố/rotate credential thay vì chỉ xóa link artifact.

## 27. Tránh báo cáo “test pass” khi không có bằng chứng

Những câu đúng:

- “Đã viết 4 methods và 6 potential invocations trong source; **chưa chạy JUnit**.”
- “Gradle `test` đã chạy, XML cho biết N cases, F failures, S skipped” — chỉ nói khi có file/report thật.
- “Build fail tại `compileTestJava`, chưa có JUnit XML.”
- “Artifact upload thành công” — chỉ sau khi GitHub Actions hoặc plugin xác nhận.
- “Bước upload được cấu hình `if: always()`, nhưng việc job runner bị kill vẫn có thể ngăn upload.”

Những câu sai:

- “17 tests PASSED” chỉ vì thấy 17 `@Test` annotations.
- “0 failures nghĩa là không có lỗi” khi toàn bộ tests bị skip/not discovered.
- “Đã lưu artifact” khi mới viết YAML mà workflow chưa chạy.
- “XML xác nhận container hoạt động” nếu test setup skip do no Docker.
- “Gradle full suite đã pass” khi chỉ chạy một method với `--tests`.
- “CI xanh” khi câu lệnh bị `|| true` hoặc `tee` che exit status.

**Trong bài Knowledge này không chạy Gradle hoặc GitHub Actions thực.** Mọi commands, expected behavior và report layouts là hướng dẫn tái hiện; status PASS thật phụ thuộc môi trường người đọc.

## 28. Tối ưu thời gian triage và artifact cost

Không nên upload vô hạn:
- toàn bộ `build/` với class files và caches nếu chỉ cần test results;
- hàng nghìn raw HTTP bodies;
- screenshots ở mọi step của mọi passing test;
- Docker images/dumps;
- test runner debug logs chưa redaction.

Mẫu hợp lý:
- Luôn giữ raw JUnit XML và HTML khi run thất bại hoặc khi team cần trend.
- Giữ một console log `--console=plain`.
- Thu extra sanitized logs/trace/screenshots **chỉ khi test fail**.
- Gắn run ID, CI attempt và module/task vào artifact name.
- Retention ngắn với PR, dài hơn với release/regression investigation nếu chính sách cho phép.
- Tiết kiệm bằng compression phù hợp, cap file size và cleanup.
- Chọn một CI test-report aggregator thay vì mỗi module tự dựng dashboard khác nhau.

Nếu artifact quá lớn và upload step fail, lỗi chính của test có thể bị che giữa logs uploader. Đặt file limits, cảnh báo kích thước và phân nhóm artifacts theo unit/integration/E2E.

## 29. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| Build fail nhưng không có XML | Compile/dependency/setup fail trước Test | Xem Gradle console log |
| CI đọc 0 tests dù Gradle chạy | Sai report glob/task/module | Kiểm tra `build/test-results/<task>` |
| HTML index mở nhưng trống style | Chỉ tải index, không có CSS/JS | Upload toàn bộ directory |
| Test đỏ, step upload không chạy | Uploader không có `if: always()` | Dùng always cho diagnostics |
| Gradle đỏ, CI step xanh | `tee` không có pipefail hoặc `|| true` | Preserve exit status |
| Tên testcase không như method | DisplayName/parameterized invocations | So XML classname/name/display |
| “skipped” bị coi “passed” | CI dashboard aggregation sai | Report counts rõ |
| Report vẫn có lỗi cũ | Task UP-TO-DATE, artifact stale, không clean | `clean test` hoặc `--rerun-tasks` |
| Test failure chỉ xuất hiện dưới một module | Uploader chỉ scan root build | Multi-module globs |
| Failsafe IT không có trong dashboard | Chỉ publish Surefire paths | Thêm failsafe-reports |
| XML parse lỗi | Partial/truncated report, producer khác | Lưu raw XML; check task lifecycle |
| Stacktrace không đủ | Test logging truncated/short format | `TestExceptionFormat.FULL`, HTML |
| Log chứa token | Verbose HTTP/SQL logging | Redaction, synthetic fixtures |
| XML rất lớn | Captured stdout quá nhiều | output limits / log level |
| Flaky pass-on-retry “mất” lỗi | Rerun merge/parser không hiểu | Giữ retries/attempt logs |
| Artifact v4 upload xung đột matrix | Nhiều jobs cùng artifact name | Tên unique theo matrix |
| Không có Gradle Wrapper | Chưa commit wrapper files | Tạo/commit Wrapper hoặc dùng installed Gradle |
| Test XML có 1 failure nhưng Gradle job pass | ignoreFailures/continue-on-error/exit masking | Sửa pipeline gate |
| JUnit report 0 failures nhưng Spring app lỗi | Exception bị catch/log, assertion không bảo vệ | Thêm business outcome assertion |
| Binary test-results không đọc được | Gradle internal format | Dùng XML/HTML cho triage |
| Report hoàn tất nhưng uploader bị cancel | CI runner/job bị dừng cứng | Retention/cancellation policy, log upstream |
| CI chỉ upload vào successful runs | `if: success()` mặc định | Dùng `if: always()` khi phù hợp |

## 30. Checklist QA cho một pipeline Spring Boot

- [ ] JDK/Gradle/Spring Boot/JUnit versions có thể xác định từ build logs?
- [ ] JUnit Jupiter chạy qua `useJUnitPlatform()`?
- [ ] Test task có thực thi tests, không “0 tests discovered” ngoài ý định?
- [ ] JUnit XML và HTML reports được bật?
- [ ] Paths của tất cả Test tasks/subprojects được upload?
- [ ] TestLogging hiển thị failed tests và exception details hữu ích?
- [ ] Console logs có giữ đúng exit code nếu pipe qua tee?
- [ ] Uploader và diagnostic steps chạy khi test task fail (`if: always()`)?
- [ ] Không dùng `|| true`/`ignoreFailures` để che failure?
- [ ] Artifacts giữ full HTML directory, không chỉ index?
- [ ] JUnit XML parser hỗ trợ format producer và retries?
- [ ] Có baseline test count/skip count khi cần phát hiện missing coverage?
- [ ] Assertions có messages giúp định vị domain failure mà không leak secrets?
- [ ] Có phân biệt test failure với Spring context/Docker/compile failure?
- [ ] Logs có correlation ID/test run/shard metadata an toàn?
- [ ] Không bật debug logging vô hạn trong public CI?
- [ ] File upload có retention và quyền truy cập rõ?
- [ ] Test fixtures không chứa PII/production secrets?
- [ ] Extra artifacts chỉ thu đúng test resource, không quét cả workspace?
- [ ] Matrix artifact names khác nhau cho OS/JDK/variant?
- [ ] Flaky retries vẫn lưu first failure evidence?
- [ ] CI run bị cancel/killed được nhận diện là không đủ bằng chứng?
- [ ] Sau khi fix lỗi, có regression test ngăn lỗi quay lại?

## 31. Bài tập thực hành

1. Tạo các file project và chạy `gradle clean test`.
2. Tìm `build/test-results/test/TEST-...xml` và `build/reports/tests/test/index.html`, mở summary/class pages.
3. Bật `-PdemoFail=true` rồi chạy lại, xem assertion expected/actual ở report.
4. Chạy riêng method `intentionalFailureForReportTraining` bằng `--tests` với cờ đúng.
5. Chạy script `summarize_junit.py` và so sánh counts với HTML; phân biệt skipped.
6. Bỏ `useJUnitPlatform()` trong sandbox, kiểm tra build behavior và đưa lại.
7. Tắt `reports.html.required`, xem artifact upload mất nội dung nào.
8. Bật `outputPerTestCase` rồi so sánh XML output placement.
9. Tắt `includeSystemOutLog`, giải thích tradeoff giảm rủi ro dữ liệu nhạy cảm.
10. Thử pipe Gradle failure vào `tee` có/không có `set -o pipefail`, kiểm tra exit code.
11. Thêm một test bị `@Disabled`; xác minh skipped count, không giả đó là passed.
12. Thêm `@ParameterizedTest` có nhiều cases và xem count tăng so với annotation count.
13. Tạo compile error có chủ đích trong sandbox, quan sát vì sao không có XML mới sau `clean`.
14. Tạo workflow GitHub Actions trong một test repository, verify artifacts trên failed run.
15. Cho workflow có hai JDK matrix variants, đặt artifact names unique cho mỗi variant.
16. Tạo một Gradle `integrationTest` task và thêm path vào uploader.
17. Thêm một test Spring context startup failure trong dedicated branch, học đọc `Caused by`.
18. Thêm MockWebServer/WireMock trong integration test, thu sanitized request journal khi fail.
19. Chạy một test flaky do shared static variable trong sandbox, thử `--tests` riêng và cả suite.
20. Thử Gradle retry plugin trong sandbox, so sánh raw failure logs với `mergeReruns`.
21. Đặt `retention-days` ngắn cho PR và xem org policy có override không.
22. Rà soát artifact zip để xác nhận không có tokens, credentials, customer data.
23. Viết một checklist triage cho team: task, class, case, stack, environment, correlation, reproduction.
24. Sau khi sửa lỗi, chạy full suite và quan sát số cases/skip/failed thật trên CI.

## 32. Nguồn tham khảo đáng tin cậy

- [Gradle User Guide — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Java Test task, JUnit XML/HTML report paths, logging, outputPerTestCase, TestReport aggregation, XML rerun semantics.
- [Gradle DSL — Test](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): `useJUnitPlatform`, reports, testLogging, filters và fail-fast.
- [Gradle DSL — JUnitXmlReport](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.JUnitXmlReport.html): `includeSystemOutLog`, `includeSystemErrLog`, `outputPerTestCase` và `mergeReruns`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, Spring context/slice test semantics.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.0/user-guide/): `@Test`, `@ParameterizedTest`, `@EnabledIfSystemProperty` và test discovery.
- [GitHub Docs — Store and share data with workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data): upload/download artifacts, retention.
- [GitHub actions/upload-artifact](https://github.com/actions/upload-artifact): `if-no-files-found`, `retention-days` và major-version behavior.
- [GitHub Docs — Expressions and status check functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions): `always()` và conditional steps.
- [Maven Surefire Reports](https://maven.apache.org/surefire/maven-surefire-plugin/examples/reporting.html): Surefire XML/text reports.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration-test/verify lifecycle.
- [JUnit Platform — Console Launcher](https://junit.org/junit5/docs/current/user-guide/): khác biệt giữa JUnit Platform output và Gradle reporting.

## 33. Kết luận

**Để điều tra lỗi Spring Boot trên CI, không chỉ cần biết test đỏ mà cần giữ đủ bằng chứng và đúng exit status.** Gradle JUnit XML phục vụ máy đọc test cases, HTML report phục vụ con người điều tra stack traces, console log cho thấy build/setup/startup failures, còn CI artifact giữ mọi thứ sau khi job kết thúc.

Một workflow tốt: chạy tests thật, giữ Gradle nonzero khi fail, sinh XML/HTML theo task, upload toàn bộ reports và console logs bằng bước `if: always()`, đặt retention và quyền an toàn, sau đó liên hệ Gradle task → test class → test case → stack/cause → logs/correlation → môi trường/commit để tái hiện. Đừng coi một skipped test là passed, đừng coi 0 failures là full coverage nếu không có test nào chạy, và đừng để retry hoặc `|| true` làm mất tín hiệu lỗi.

Bộ code Java 17+/Spring Boot 3.3.5 minh họa **4 test methods, tối đa 6 executions** khi bật failure scenario có điều kiện. Kết quả chạy thực tế phải được xác nhận bằng Gradle/JUnit reports chứ không suy từ code hoặc bài viết.
