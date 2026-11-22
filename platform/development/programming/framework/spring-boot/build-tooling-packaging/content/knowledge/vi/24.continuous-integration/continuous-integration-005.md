# Chạy verify hoặc build và thu thập báo cáo kiểm thử

## 1. Mục tiêu

Một build CI đáng tin cậy cần làm được hai việc: xác nhận mã nguồn vượt qua các bước kiểm tra bắt buộc và lưu bằng chứng đủ chi tiết để điều tra khi có lỗi. Chỉ nhìn dòng “BUILD SUCCESS” hoặc “BUILD FAILED” là chưa đủ; cần biết test nào đã chạy, test nào pass/fail/skip, module nào lỗi, stack trace ra sao và báo cáo được lưu ở đâu.

Bài học hướng dẫn chạy verification/build bằng Gradle hoặc Maven, đọc test reports và cấu hình CI thu thập báo cáo ngay cả khi test thất bại. Trọng tâm là Spring Boot/Java 17, JUnit 5 và GitHub Actions; các nguyên tắc áp dụng được cho CI khác.

Sau bài này, bạn có thể:

- Phân biệt Gradle `check`/`build` với Maven `verify`.
- Chạy unit tests, integration tests và packaging bằng Wrapper.
- Đọc HTML reports dành cho con người và JUnit XML dành cho CI.
- Thu thập báo cáo từ multi-module builds.
- Giữ build ở trạng thái failed khi test fail nhưng vẫn upload báo cáo.
- Phân biệt test reports, coverage reports và static-analysis reports.
- Xử lý test không được phát hiện, test flaky, timeout, report thiếu và lỗi chỉ xuất hiện trên CI.

**Phiên bản ví dụ:** Java 17, JUnit Jupiter 5.10.2, Gradle Wrapper và Maven Wrapper. Các phiên bản chỉ nhằm minh họa; hãy dùng version tương thích với project và đã được tổ chức phê duyệt.

## 2. Build, check, verify và test khác nhau thế nào?

Từ “verify” có ý nghĩa khác nhau tùy build tool. Không nên dùng cùng một command rồi giả định Gradle và Maven có lifecycle giống nhau.

| Build tool | Command/task | Ý nghĩa |
| --- | --- | --- |
| Gradle | `test` | Chạy test tasks đã cấu hình, thường gồm unit tests |
| Gradle | `check` | Chạy verification tasks; mặc định phụ thuộc `test` và có thể gồm quality/integration checks khác |
| Gradle | `assemble` | Tạo outputs/artifacts theo cấu hình |
| Gradle | `build` | Lifecycle task kết hợp `check` và `assemble` |
| Maven | `test` | Chạy test phase, thường qua Maven Surefire |
| Maven | `package` | Chạy các phase trước đó và đóng gói artifact |
| Maven | `verify` | Chạy đến verify phase, gồm các plugin goals được gắn vào integration-test/verify |
| Maven | `install` | Chạy verify rồi cài artifact vào local Maven repository |

### 2.1. Gradle không có lifecycle task verify mặc định

Gradle Java plugin cung cấp các lifecycle tasks tiêu chuẩn như `check`, `assemble` và `build`. Một project có thể tự tạo task tên `verify` hoặc plugin khác cung cấp task đó, nhưng không nên giả định task này luôn tồn tại.

Chạy:

~~~bash
./gradlew tasks --all
./gradlew help --task check
./gradlew help --task build
~~~

Nếu project có task `verify` riêng, xem task graph và tài liệu plugin trước khi sử dụng.

Với CI Java/Spring Boot thông thường:

~~~bash
./gradlew --no-daemon --console=plain clean build
~~~

Nếu chỉ muốn chạy verification mà không assemble artifact:

~~~bash
./gradlew --no-daemon --console=plain clean check
~~~

### 2.2. Maven verify là lifecycle phase chuẩn

Maven có build lifecycle chuẩn. Khi chạy:

~~~bash
./mvnw -B -ntp clean verify
~~~

Maven thực hiện các phase trước verify theo thứ tự, bao gồm compile, test, package và các plugin goals được gắn vào lifecycle. Nếu Failsafe được cấu hình đúng, integration tests chạy ở `integration-test` và kết quả được kiểm tra ở `verify`.

Đối với CI cần kiểm thử và xác minh artifact, `verify` thường là điểm kết thúc phù hợp. Không cần chạy thêm `install` trừ khi pipeline cần cài artifact vào local repository cho một bước build khác.

### 2.3. Không nhầm build pass với có test đã chạy

Một build có thể xanh dù không phát hiện test nào, nếu project/plugin không bật fail-on-no-tests hoặc test sources không được cấu hình đúng. Vì vậy hãy kiểm số test trong báo cáo:

- Số tests được phát hiện.
- Số tests pass.
- Số failures và errors.
- Số skipped/aborted.
- Module/source set nào đã chạy.
- Test task có thực sự nằm trong task graph không.

Nếu module được thiết kế không có test, zero tests có thể là hợp lệ. Nếu module bắt buộc có test, hãy đặt policy riêng để fail khi không phát hiện test.

## 3. Ví dụ Java 17 và JUnit 5

Ta dùng một lớp Java nhỏ để có bộ test độc lập, dễ quan sát report.

### 3.1. Production class

Tạo `src/main/java/com/example/Calculator.java`:

~~~java
package com.example;

public final class Calculator {

    public int add(int left, int right) {
        return left + right;
    }

    public int multiply(int left, int right) {
        return left * right;
    }

    public int divide(int dividend, int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("divisor must not be zero");
        }
        return dividend / divisor;
    }
}
~~~

### 3.2. JUnit 5 test class

Tạo `src/test/java/com/example/CalculatorTest.java`:

~~~java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    private final Calculator calculator = new Calculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(7, calculator.add(3, 4));
    }

    @Test
    void multipliesTwoNumbers() {
        assertEquals(12, calculator.multiply(3, 4));
    }

    @Test
    void rejectsDivisionByZero() {
        ArithmeticException exception = assertThrows(
                ArithmeticException.class,
                () -> calculator.divide(10, 0)
        );

        assertEquals("divisor must not be zero", exception.getMessage());
    }
}
~~~

Test này có ba methods độc lập. Khi JUnit Jupiter được cấu hình và phát hiện đúng, báo cáo sẽ có tổng cộng 3 tests, 0 failures, 0 errors và 0 skipped. Thời gian thực thi và cách trình bày output thay đổi theo runner/plugin.

### 3.3. Cấu hình Java version

Project cần JDK 17 và bytecode target Java 17. Với Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Với Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Compiler release không cài JDK. Runner phải có JDK phù hợp; kiểm tra bằng `java -version` và `javac -version` trước khi chạy build.

## 4. Gradle: cấu hình và chạy test

### 4.1. Groovy DSL

Ví dụ `build.gradle` tối thiểu cho Java/JUnit 5:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    reports {
        junitXml.required = true
        html.required = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = false
    }
}
~~~

JUnit BOM quản lý version đồng bộ cho các JUnit artifacts. `useJUnitPlatform()` yêu cầu Gradle Test task dùng JUnit Platform để phát hiện Jupiter tests.

### 4.2. Kotlin DSL

Nếu project dùng `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }

    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = false
    }
}
~~~

Chỉ chọn một DSL cho module. Nếu project Spring Boot, giữ plugin/dependencies hiện có và bổ sung test dependency/config phù hợp; không thay toàn bộ build file chỉ để thêm JUnit.

### 4.3. Chạy từng mức

Chạy unit tests:

~~~bash
./gradlew --no-daemon --console=plain test
~~~

Chạy toàn bộ verification:

~~~bash
./gradlew --no-daemon --console=plain check
~~~

Build artifact và chạy checks:

~~~bash
./gradlew --no-daemon --console=plain clean build
~~~

Xem task graph:

~~~bash
./gradlew check --dry-run
./gradlew build --dry-run
~~~

`--dry-run` hiển thị tasks dự kiến mà không thực thi chúng. Dùng để xác nhận `test` và các verification tasks nằm trong graph; nó không tạo báo cáo test thật.

### 4.4. Chạy một test cụ thể

Theo class:

~~~bash
./gradlew test --tests "com.example.CalculatorTest"
~~~

Theo method (nếu filter syntax phù hợp với test engine):

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Chạy test theo package/class filter giúp rút ngắn vòng debug. Trước khi merge/release, vẫn chạy đầy đủ verification suite. Nếu filter không match test nào, xem output và báo cáo để tránh hiểu nhầm là test đã pass.

### 4.5. Gradle test reports nằm ở đâu?

Với project đơn:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-com.example.CalculatorTest.xml
        └── binary/
~~~

- HTML report: `build/reports/tests/test/index.html` — mở trên browser để xem summary, class, method, failure details.
- JUnit XML: `build/test-results/test/*.xml` — CI parser đọc để hiển thị test annotations/trends.
- Binary results: dữ liệu nội bộ Gradle dùng để tạo report; không thay JUnit XML trong quy trình upload phổ biến.

Với multi-module, mỗi module có thư mục `build` riêng, ví dụ:

~~~text
service/build/reports/tests/test/index.html
service/build/test-results/test/*.xml
api/build/reports/tests/test/index.html
api/build/test-results/test/*.xml
~~~

Không giả định report chỉ nằm ở root `build/`.

## 5. Gradle: tiếp tục các task độc lập và giữ trạng thái fail

Mặc định, một task failure có thể khiến các task phụ thuộc bị bỏ qua. Với multi-module build, có thể dùng:

~~~bash
./gradlew --no-daemon --console=plain clean build --continue
~~~

`--continue` cho phép Gradle tiếp tục chạy các tasks độc lập sau failure nếu dependency graph cho phép. Kết quả build cuối vẫn thất bại nếu có task thất bại. Nhờ đó CI có thể thu được thêm test reports từ các module khác.

Không dùng cấu hình:

~~~groovy
tasks.withType(Test).configureEach {
    ignoreFailures = true
}
~~~

trong release verification nếu mục tiêu là build phải fail khi test fail. `ignoreFailures=true` có thể làm task Test không truyền failure ra build result như mong muốn. Để lưu report khi fail, dùng CI upload step chạy với điều kiện always; không cần biến test failure thành success.

### 5.1. Test output và report verbosity

Có thể cấu hình:

~~~groovy
tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showCauses true
        showStackTraces true
        showStandardStreams false
    }
}
~~~

Log console nên giúp biết test nào fail và failure summary. HTML/XML report giữ chi tiết để xem sau. Chỉ bật standard output/error của mọi test khi cần, vì logs có thể lớn hoặc vô tình chứa credentials/test data nhạy cảm.

### 5.2. Test parallelism

Gradle có thể chạy test forks song song:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 2
}
~~~

Chỉ tăng song song khi tests độc lập và resource đủ. Test dùng cùng port, database schema, file path hoặc singleton state có thể race khi chạy song song. Một test pass tuần tự nhưng fail song song cần kiểm shared state, isolation và cleanup.

Thuộc tính `maxParallelForks` là số fork cho một Test task; Gradle worker limits/CI CPU cũng ảnh hưởng concurrency tổng. Đừng đặt giá trị cao mà không đo memory và test stability.

## 6. Maven: chạy verify và thu thập reports

### 6.1. Surefire cho unit tests

Maven Surefire Plugin chạy unit tests trong test phase. JUnit Jupiter cần engine/aggregator dependency tương thích.

Trong POM dùng Spring Boot parent, có thể thêm dependency test:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu không dùng Spring Boot parent/BOM, pin JUnit version hoặc import JUnit BOM trong dependency management. Pin Maven plugin versions theo policy dự án; không để build phụ thuộc plugin version ngẫu nhiên.

Một cấu hình Surefire tường minh:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <reportsDirectory>target/surefire-reports</reportsDirectory>
        <useModulePath>false</useModulePath>
    </configuration>
</plugin>
~~~

`useModulePath=false` hữu ích cho một số classpath-based projects khi JPMS/module path gây vấn đề; không phải yêu cầu bắt buộc cho mọi project. Chỉ giữ option này nếu phù hợp module structure thực tế.

### 6.2. Chạy unit tests và xem reports

~~~bash
./mvnw -B -ntp clean test
~~~

Surefire thường tạo:

~~~text
target/
└── surefire-reports/
    ├── TEST-com.example.CalculatorTest.xml
    ├── com.example.CalculatorTest.txt
    └── ...
~~~

- XML: dữ liệu test suites/cases, counts, failures/errors/skips và failure details.
- TXT: console-style report của từng test class, hữu ích để đọc stack trace.
- Console: Maven summary cho biết plugin goal và build result.

Đường dẫn có thể thay đổi nếu POM cấu hình reports directory hoặc project có module-specific build directory.

### 6.3. Maven Failsafe cho integration tests

Surefire phù hợp unit tests chạy nhanh. Maven Failsafe được thiết kế cho integration tests; thông thường test class theo naming patterns như `*IT.java` hoặc patterns đã cấu hình.

Ví dụ plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Failsafe tách việc chạy integration tests ở phase `integration-test` và kiểm kết quả ở phase `verify`. Thiết kế này cho phép các post-integration-test steps (ví dụ dừng test server/compose stack) chạy trước khi kết luận integration test failure tại verify phase.

Chạy:

~~~bash
./mvnw -B -ntp clean verify
~~~

Chỉ chạy `mvn test` sẽ không đi đến integration-test/verify phases; do đó không thể dùng nó để chứng minh Failsafe integration suite đã chạy.

### 6.4. Failsafe reports

~~~text
target/
├── surefire-reports/
│   ├── TEST-...xml
│   └── ...
└── failsafe-reports/
    ├── TEST-...xml
    ├── ...-output.txt
    └── ...
~~~

Surefire và Failsafe có report directories riêng. Upload cả hai khi pipeline chạy unit và integration tests. Không gom nhầm Failsafe report vào Surefire path rồi bỏ sót integration failures.

### 6.5. Maven multi-module

Nếu reactor có nhiều modules và muốn thu thập nhiều report hơn trước khi kết thúc fail, có thể dùng:

~~~bash
./mvnw -B -ntp clean verify -fae
~~~

`-fae`/`--fail-at-end` cho phép Maven tiếp tục các modules không phụ thuộc vào module đã fail rồi báo build failure ở cuối. Module phụ thuộc vào module thất bại có thể vẫn bị skipped. Đây không phải cách biến failure thành success.

Không dùng `-fn`/`--fail-never` trong release gate: option này có thể khiến Maven kết thúc như thành công dù có lỗi.

## 7. Đọc JUnit XML và HTML report

### 7.1. JUnit XML

Một report JUnit XML có dạng khái quát:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.CalculatorTest"
           tests="3"
           failures="0"
           errors="0"
           skipped="0"
           time="0.012">
    <testcase classname="com.example.CalculatorTest"
              name="addsTwoNumbers"
              time="0.003"/>
    <testcase classname="com.example.CalculatorTest"
              name="multipliesTwoNumbers"
              time="0.002"/>
    <testcase classname="com.example.CalculatorTest"
              name="rejectsDivisionByZero"
              time="0.007"/>
</testsuite>
~~~

Đây là ví dụ minh họa schema và counts, không phải report thực từ một lần chạy. Report thật chứa timings, names và failure details phụ thuộc plugin/test engine.

Các thuộc tính cần đọc:

- `tests`: số test cases được ghi nhận.
- `failures`: assertion failures.
- `errors`: lỗi thực thi ngoài assertion hoặc exception không mong đợi.
- `skipped`: test bị skip/disabled/aborted theo reporter.
- `time`: thời gian được reporter ghi nhận.

Một suite có thể có nhiều XML files; tổng số tests cần được tổng hợp từ tất cả suites mà không đếm duplicate report artifacts.

### 7.2. Assertion failure và test error

Ví dụ assertion failure:

~~~text
expected: <7>
 but was: <6>
~~~

Test đã chạy nhưng expected/actual khác nhau.

Ví dụ error:

~~~text
java.lang.IllegalStateException: database connection refused
~~~

Test có thể fail vì setup/runtime/external service trước khi assertion hoàn thành. Phân loại đúng giúp quyết định sửa code, test fixture hay môi trường.

### 7.3. HTML report

HTML report thường thuận tiện để:

- Xem tổng số tests và success rate.
- Mở từng package/class.
- Xem từng test duration.
- Đọc failure stack trace.
- Tìm tests chạy chậm hoặc fail.

CI nên giữ cả HTML và XML: HTML cho người đọc; XML cho CI parser, trend dashboards và integration.

### 7.4. Reports khác nhau không phải cùng một thứ

| Report | Thông tin | Nguồn thường gặp |
| --- | --- | --- |
| Unit test report | Pass/fail/skip, stack trace, duration | Gradle Test / Maven Surefire |
| Integration test report | Kết quả test với DB/service/container | Gradle integrationTest / Maven Failsafe |
| Coverage report | Lines/branches được thực thi | JaCoCo |
| Static analysis | Code smells, bug patterns, violations | Checkstyle, PMD, SpotBugs, Sonar |
| Build scan/build report | Task graph, performance, dependency resolution | Gradle Enterprise/Build Scan hoặc CI |
| Packaging report | Artifact metadata, checksums, image details | Build/publish tooling |

Chạy test không tự động tạo coverage report nếu JaCoCo chưa được cấu hình. Một coverage percentage cao cũng không chứng minh tests có assertions tốt; xem cả report và chất lượng test.

## 8. GitHub Actions: upload Gradle reports kể cả khi test fail

Đây là điểm quan trọng: nếu step chạy Gradle trả exit code khác 0, các step tiếp theo mặc định có thể bị skip. Upload report cần condition `if: always()`.

Ví dụ workflow:

~~~yaml
name: Gradle Verification

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Run Gradle build
        run: ./gradlew --no-daemon --console=plain clean build --continue

      - name: Upload Gradle test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-test-reports
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: warn
          retention-days: 14
~~~

Khi test fail:

- Gradle step trả failure và job vẫn fail.
- Upload step chạy nhờ `if: always()`.
- XML và HTML reports được lưu thành workflow artifact.
- Người review có thể tải report để xem test/module cụ thể.

`if-no-files-found: warn` tránh biến việc không có report (ví dụ build fail trước test execution) thành một lỗi upload thứ hai làm khó đọc nguyên nhân gốc. Nếu project bắt buộc phải có report và việc thiếu report là lỗi policy, đổi thành `error` sau khi chắc chắn path đúng.

Trong production, pin actions bằng full commit SHA đã review thay vì chỉ tag `@v4`. Ví dụ dùng tag để dễ đọc; tag không phải immutable pin.

### 8.1. Vì sao không dùng continue-on-error?

Không đặt:

~~~yaml
- name: Run Gradle build
  continue-on-error: true
  run: ./gradlew clean build
~~~

nếu mục tiêu là merge/release gate phải fail khi tests fail. `continue-on-error` có thể làm step failure không còn chặn job theo cách mong muốn. Upload report bằng step riêng có `if: always()`; giữ nguyên exit code của build step.

### 8.2. Reports trong multi-module Gradle

Pattern:

~~~yaml
path: |
  **/build/test-results/**
  **/build/reports/tests/**
~~~

bao gồm các module con có thư mục `build` riêng. Kiểm tra artifact upload sau một build có ít nhất một module pass và một module fail để bảo đảm report paths được thu thập đúng.

## 9. GitHub Actions: upload Maven Surefire/Failsafe reports

Ví dụ Maven:

~~~yaml
name: Maven Verification

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run Maven verification
        run: ./mvnw -B -ntp clean verify -fae

      - name: Upload Maven test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: maven-test-reports
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: warn
          retention-days: 14
~~~

Nếu Maven verify fail do unit/integration test, upload step vẫn lưu reports có sẵn. `-fae` giúp reactor tiếp tục các modules độc lập khi có failure; cuối cùng job vẫn failed.

Nếu dùng Maven project đơn, path `target/...` đủ. Pattern `**/target/...` hỗ trợ multi-module. Nếu report directory đã được tùy chỉnh trong POM, sửa upload paths theo output thật.

## 10. Thu thập reports ngoài GitHub Actions

Nguyên tắc tương tự áp dụng cho GitLab CI, Jenkins, Azure Pipelines và các hệ thống khác:

1. Chạy build/test và giữ exit code.
2. Luôn chạy bước publish/archive reports ngay cả khi test step fail.
3. Upload JUnit XML cho test result parser.
4. Upload HTML/TXT để người đọc điều tra.
5. Giữ build/job status failed nếu tests fail.
6. Đặt retention phù hợp và hạn chế quyền truy cập.
7. Không publish report nhạy cảm ra public artifacts.

### 10.1. GitLab CI minh họa

~~~yaml
test:
  image: eclipse-temurin:17-jdk
  script:
    - ./gradlew --no-daemon clean test
  artifacts:
    when: always
    reports:
      junit: "**/build/test-results/test/*.xml"
    paths:
      - "**/build/reports/tests/"
      - "**/build/test-results/"
    expire_in: 14 days
~~~

`when: always` yêu cầu lưu artifacts khi job kết thúc, kể cả khi script thất bại. Cú pháp và khả năng glob của GitLab runner cần được đối chiếu với version triển khai. Nếu dùng Maven, thay JUnit report glob bằng Surefire/Failsafe XML paths.

### 10.2. Jenkins Pipeline minh họa

~~~groovy
pipeline {
    agent any

    stages {
        stage('Verify') {
            steps {
                sh './gradlew --no-daemon clean build --continue'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true,
                  testResults: '**/build/test-results/**/*.xml'
            archiveArtifacts allowEmptyArchive: true,
                             artifacts: '**/build/reports/tests/**'
        }
    }
}
~~~

`post { always { ... } }` chạy bước lưu reports kể cả khi stage fail. `allowEmptyResults`/`allowEmptyArchive` phù hợp khi build có thể fail trước khi tạo report; nếu dự án yêu cầu report luôn có, dùng policy nghiêm hơn. Jenkins JUnit plugin cần được cài đặt.

### 10.3. Không che failure bằng bước publish

Report publisher có thể có lỗi riêng, ví dụ XML malformed hoặc path sai. Cần phân biệt:

- Test failure: lỗi sản phẩm/test; build phải fail.
- Report publishing failure: lỗi thu thập evidence; pipeline cũng cần hiển thị rõ.
- Build failure trước test: không có report có thể là kết quả hợp lệ, nhưng cần log cho biết test chưa chạy.

Không đổi build result sang success chỉ vì upload report thành công.

## 11. Multi-module: chạy đủ test và gom đúng báo cáo

### 11.1. Gradle multi-project

Xem modules:

~~~bash
./gradlew projects
~~~

Chạy toàn bộ verification/build:

~~~bash
./gradlew --no-daemon --console=plain clean build --continue
~~~

Gradle tạo reports riêng theo từng project và Test task. Ví dụ:

~~~text
api/build/test-results/test/
service/build/test-results/test/
worker/build/test-results/test/
~~~

Với nhiều Test tasks như `test`, `integrationTest`, `functionalTest`, report nằm trong thư mục tương ứng với task name. Upload pattern rộng hơn:

~~~yaml
path: |
  **/build/test-results/**
  **/build/reports/tests/**
~~~

Nếu có report aggregation plugin, report tổng hợp có thể được tạo ở một project riêng. Không giả định aggregation tự chạy nếu plugin/task chưa được cấu hình.

### 11.2. Maven reactor

Chạy tất cả modules:

~~~bash
./mvnw -B -ntp clean verify -fae
~~~

Maven reactor sắp thứ tự modules theo dependency graph. `-fae` tiếp tục các modules không phụ thuộc module fail; modules phụ thuộc có thể vẫn bị bỏ qua. Reports được tạo trong `target` của từng module.

### 11.3. Đếm test tổng hợp

Không cộng số tests từ HTML và XML cùng lúc vì đó là hai cách biểu diễn của cùng test run. Với multi-module, tổng hợp từ XML files của các module/task duy nhất. Nếu có rerun reports, retries hoặc multiple executions, xem report format/plugin behavior để tránh đếm trùng.

## 12. Test failure, skipped, flaky và no-tests

### 12.1. Failure vs error vs skipped

- **Failure:** assertion không đạt hoặc test framework ghi nhận kiểm tra thất bại.
- **Error:** exception/setup/runtime failure làm test không hoàn thành như dự kiến.
- **Skipped:** test bị disable/assumption false hoặc reporter ghi nhận trạng thái skip.
- **Aborted:** test dừng theo assumption/condition; cách biểu diễn phụ thuộc engine/reporter.

Không xem skipped là pass. Nếu một suite có nhiều skipped, kiểm lý do và policy; một số skip là có chủ đích (ví dụ OS-specific), số khác có thể che test không chạy.

### 12.2. Flaky tests

Flaky test lúc pass lúc fail thường liên quan:

- Shared mutable state hoặc thứ tự test.
- Port/file/database dùng chung.
- Timing, sleep cố định, race condition.
- External service/network không ổn định.
- Timezone/clock/locale.
- Test cleanup thiếu hoặc thread/process còn sống.
- Parallel forks và resource limits.

Ghi lại seed, test order, retry count, environment và log. Không tự động retry vô hạn để làm CI xanh; retry có thể giúp chẩn đoán nhưng không sửa nguyên nhân. Nếu có retry plugin, report cần giữ cả lần fail và lần pass theo policy để không che flaky behavior.

### 12.3. Không có test được phát hiện

Nếu Gradle/Maven build pass nhưng không thấy report:

1. Kiểm task/phase có chạy không.
2. Kiểm test source directories đúng convention chưa.
3. Kiểm class naming patterns.
4. Kiểm JUnit Platform engine/dependency.
5. Kiểm test filters/exclusions.
6. Kiểm report output path đã custom không.
7. Kiểm module có test hay được phép zero tests không.

Gradle Test task và Maven Surefire có cấu hình khác nhau về hành vi khi không có tests. Với module bắt buộc có test, thiết lập fail-on-no-tests phù hợp và xác minh bằng một test cố ý bị filter để kiểm gate.

### 12.4. Timeout và process không dừng

Test có thể bị treo do thread, server, executor hoặc container không cleanup. Dùng test timeout/CI job timeout có giới hạn, giữ thread dump/log khi cần. Không chỉ tăng timeout nếu test đang deadlock hoặc chờ dependency không tồn tại.

## 13. JaCoCo coverage report (phần bổ sung)

Coverage đo code được thực thi trong tests, khác với JUnit test result. Có thể có 100% line coverage mà assertions vẫn yếu; cũng có thể test tốt nhưng coverage chưa cao. Dùng coverage như tín hiệu bổ sung, không thay test review.

### 13.1. Gradle JaCoCo

Bật plugin:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

jacocoTestReport {
    dependsOn test
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Chạy:

~~~bash
./gradlew test jacocoTestReport
~~~

Report mặc định thường ở:

~~~text
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
~~~

Trong multi-module, path nằm dưới project/module tương ứng. JaCoCo task tạo coverage report từ execution data của test tasks đã cấu hình; nếu task chưa chạy hoặc agent không được gắn đúng, report có thể trống/thiếu.

### 13.2. Maven JaCoCo

Có thể cấu hình JaCoCo Maven Plugin với goals `prepare-agent` và `report` trong lifecycle. Version plugin phải được pin. Sau khi chạy verify, HTML/XML coverage reports thường nằm dưới:

~~~text
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
~~~

Kiểm plugin configuration và execution phases thực tế; không giả định Surefire/Failsafe tự tạo JaCoCo report khi chưa có JaCoCo agent.

### 13.3. Upload coverage riêng

CI có thể upload:

~~~yaml
path: |
  **/build/reports/jacoco/**
  **/target/site/jacoco/**
~~~

Đặt artifact name riêng hoặc gom cùng test reports nhưng mô tả rõ. JUnit XML không chứa line/branch coverage; JaCoCo XML không thay danh sách test failures.

## 14. Giữ reports an toàn và hữu ích

Test reports có thể chứa:

- Stack traces và absolute file paths.
- HTTP response/body hoặc test fixtures.
- Database names/URLs.
- Console output từ ứng dụng.
- System properties hoặc environment values do test ghi ra.
- Dữ liệu cá nhân được dùng trong test.

Không ghi secrets vào assertion messages, test stdout hoặc exception text. Không upload file `.env`, Maven `settings.xml`, Gradle properties hoặc test database dumps chỉ vì chúng nằm cạnh reports.

Thiết lập:

- Artifact retention theo yêu cầu audit và chi phí.
- Access controls tương ứng với source/repository confidentiality.
- Redaction ở logger/test fixture.
- Không dùng production customer data trong CI tests.
- Không publish public artifacts từ workflow chạy untrusted pull requests nếu chứa dữ liệu nội bộ.

## 15. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| Gradle `build` pass nhưng không có XML | Test task không chạy hoặc report disabled | Kiểm `build` task graph, Test reports config và module |
| Gradle `verify` không tồn tại | Project không khai báo task đó | Dùng `check`/`build` hoặc kiểm plugin/custom task |
| Maven `verify` pass nhưng thiếu Failsafe reports | Failsafe goals chưa bind hoặc không có IT tests | Kiểm Failsafe execution và naming patterns |
| Test reports chỉ có ở root | Module path/pattern upload sai | Dùng glob multi-module hoặc inspect từng project |
| Upload step bị skipped sau test failure | Thiếu condition luôn chạy | Dùng `if: always()` trên upload step |
| Job xanh dù test fail | `continue-on-error`/`ignoreFailures`/`fail-never` | Khôi phục failure propagation |
| JUnit XML parser không đọc được | XML malformed, report khác schema hoặc path sai | Kiểm XML và phiên bản publisher/parser |
| Không phát hiện test | Naming/source set/engine/filter sai | Kiểm JUnit Platform, Surefire patterns và test task |
| Tất cả tests skipped | Assumptions/conditions/profile hoặc disabled tests | Kiểm test annotations, profile và report reasons |
| Test fail chỉ khi chạy song song | Shared state/resource collision | Isolate DB/schema/ports/files; giảm fork để xác nhận |
| Test flaky | Race, timeouts, external service hoặc cleanup | Ghi seed/order, loại shared state và dùng deterministic waits |
| Failsafe test fail nhưng verify vẫn pass | Plugin goals/policy không được bind đúng | Kiểm execution goals `integration-test` và `verify` |
| Maven dừng sau module đầu tiên | Reactor fail-fast mặc định | Dùng `-fae` nếu cần chạy modules độc lập và giữ fail |
| Gradle dừng sớm ở module lỗi | Tasks phụ thuộc bị skip | Dùng `--continue` để chạy tasks độc lập |
| HTML report trống | Không có test results hoặc report task không chạy | Kiểm XML và test execution trước |
| Coverage report thiếu | JaCoCo agent/task không được cấu hình | Kiểm prepare-agent/execution data/report task |
| Report có secret | Tests ghi environment/credentials vào output | Redact, sửa logging và giới hạn artifact access |
| Build fail trước test | Configuration/dependency/compile error | Không kỳ vọng có test report; dùng build log làm evidence |

## 16. Bài tập thực hành có đáp án

### Bài 1 — Gradle verify

Một project Java dùng Gradle Wrapper; chạy `./gradlew verify` báo task not found. Sửa thế nào?

**Đáp án:** Gradle Java plugin mặc định dùng `check` và `build`, không có lifecycle `verify` chuẩn như Maven. Chạy `./gradlew check` hoặc `./gradlew build`, hoặc kiểm custom task/plugin nếu project quy định `verify`.

### Bài 2 — Maven integration tests

`mvn test` pass nhưng integration tests không chạy. Vì sao?

**Đáp án:** Maven `test` kết thúc trước phase `integration-test`. Cấu hình Failsafe goals và chạy `mvn verify`.

### Bài 3 — Test fail nhưng cần report

Gradle test fail, bước upload report bị skip. Thay đổi nào phù hợp?

**Đáp án:** thêm một upload step có `if: always()`. Giữ nguyên exit code/failure của Gradle step.

### Bài 4 — Multi-module Maven

Module A fail, nhưng muốn module B độc lập vẫn chạy test và tạo report. Dùng gì?

**Đáp án:** `mvn verify -fae`/`--fail-at-end`. Maven vẫn kết thúc failed; modules phụ thuộc A có thể bị bỏ qua.

### Bài 5 — Build xanh, zero tests

Có thể coi là test pass không?

**Đáp án:** không đủ bằng chứng. Kiểm số test trong XML, source directories, engine, naming patterns và test filters. Với module bắt buộc có test, cấu hình fail-on-no-tests.

### Bài 6 — XML và HTML

Hai loại report có thay thế nhau không?

**Đáp án:** không hoàn toàn. HTML phù hợp người đọc; XML phù hợp CI parser/automation. Giữ cả hai nếu pipeline cần xem thủ công và publish test results.

### Bài 7 — Coverage 100%

Có thể kết luận ứng dụng không có bug?

**Đáp án:** không. Coverage chỉ đo code paths/lines/branches được thực thi theo instrumentation; chất lượng assertions, input space, concurrency và requirements vẫn cần review.

### Bài 8 — continue-on-error

Vì sao không bật `continue-on-error` cho test step?

**Đáp án:** nó có thể làm job không phản ánh test failure đúng như release gate yêu cầu. Dùng report upload với `always()` để lưu evidence trong khi giữ build failed.

### Bài 9 — Failsafe

Vì sao Failsafe tách `integration-test` và `verify`?

**Đáp án:** để post-integration-test cleanup/teardown có thể chạy trước khi failure được kết luận ở verify phase. Surefire unit test thường fail trực tiếp ở test phase.

### Bài 10 — Báo cáo thiếu

CI log cho biết Gradle task `test` không chạy vì up-to-date, nhưng XML đã được tạo ở lần trước. Làm sao biết report thuộc run hiện tại?

**Đáp án:** kiểm task outcome và timestamp/artifact lifecycle; chạy clean trong job hoặc xóa outputs theo workspace isolation. Không upload stale report từ workspace/cache cũ như thể đó là test result của commit hiện tại.

## 17. Checklist cho CI verification

- [ ] Gradle dùng `check`/`build` đúng project convention; Maven dùng `verify` khi cần integration-test lifecycle.
- [ ] CI gọi Wrapper đã commit và dùng JDK/toolchain được quy định.
- [ ] JUnit Platform/Surefire/Failsafe được cấu hình để phát hiện đúng tests.
- [ ] Build log cho biết task/module/phase đã chạy.
- [ ] Gradle XML/HTML reports được bật và giữ ở đúng path.
- [ ] Maven Surefire và Failsafe reports được thu thập riêng.
- [ ] Multi-module report globs bao phủ mọi module và test task cần thiết.
- [ ] Build/test failure vẫn làm job thất bại.
- [ ] Upload/archive report chạy với always/finally/post condition.
- [ ] JUnit XML được publish cho CI parser; HTML/TXT được lưu để điều tra.
- [ ] Không dùng `ignoreFailures`, `continue-on-error` hoặc Maven `-fn` để che test failures.
- [ ] Có policy cho module bắt buộc phải phát hiện ít nhất một test.
- [ ] Integration tests có external dependencies và cleanup được kiểm soát.
- [ ] Flaky tests được ghi nhận và xử lý nguyên nhân; retry không che failure.
- [ ] Coverage và static-analysis reports được phân biệt với JUnit results.
- [ ] Reports không chứa secrets/customer data và có retention/access controls phù hợp.
- [ ] CI build/test đúng commit và không upload stale report từ run trước.

**Kết luận:** Gradle dùng `check`/`build` cho verification/build; Maven dùng lifecycle `verify` để chạy cả unit và integration-test goals đã bind. Gradle lưu XML/HTML dưới `build/test-results` và `build/reports/tests`; Maven Surefire/Failsafe lưu dưới `target/surefire-reports` và `target/failsafe-reports`. CI phải upload reports bằng bước luôn chạy sau failure, đồng thời giữ nguyên trạng thái failed của build để không che lỗi kiểm thử.

## 18. Tài liệu chính thức

- Gradle — Java Testing: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Java Plugin and lifecycle tasks: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Test task reports: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Apache Maven Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
- JaCoCo — Gradle Plugin: https://www.jacoco.org/jacoco/trunk/doc/gradle.html
- JaCoCo — Maven Plugin: https://www.jacoco.org/jacoco/trunk/doc/maven.html
- GitHub Actions — Workflow artifacts: https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts
- GitHub Actions — Workflow syntax and status functions: https://docs.github.com/en/actions/learn-github-actions/expressions#status-check-functions

Tên thư mục report và một số option plugin có thể thay đổi theo version/configuration. Khi áp dụng, kiểm tra task/goal thực tế, mở một report do build tạo ra và xác nhận CI upload đúng files của chính lần chạy đó.