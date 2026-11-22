# Báo cáo HTML, XML, tổng hợp kết quả và lưu bằng chứng trên CI với Gradle

## 1. Vì sao cần báo cáo kiểm thử nhiều tầng?

Trong dự án Java, lệnh **./gradlew test** không chỉ trả về trạng thái BUILD SUCCESSFUL hoặc BUILD FAILED. Gradle có thể xuất **HTML report** để developer đọc, **JUnit XML** để hệ thống CI phân tích, và **binary test results** phục vụ tổng hợp kết quả. Khi dự án có nhiều module, nhiều test suites hoặc nhiều job CI, một báo cáo duy nhất thường không đủ để trả lời:

- Bao nhiêu test được phát hiện, đã chạy, pass, fail hoặc skipped?
- Những class/method nào thất bại và stack trace là gì?
- Báo cáo đến từ unit test, integration test hay môi trường Java/OS nào?
- Test fail trước khi chạy hay thực sự có assertion failure?
- Một lần retry có làm test trở thành flaky không?
- Khi CI báo đỏ, các report có được upload trước khi runner bị xóa không?
- Một báo cáo tổng hợp đã bao gồm mọi module cần kiểm tra chưa?
- Có thể truy vết report về commit SHA, pipeline ID và JDK version không?

Bài học thuộc nhóm **Kiểm thử** của **Build Tool Gradle**, với trọng tâm **“Báo cáo HTML, XML, tổng hợp kết quả và lưu bằng chứng trên CI”**.

Sau bài học, bạn có thể:

1. Phân biệt **Test task**, **testLogging**, **test results**, **HTML report**, **JUnit XML**, **binary results** và **aggregate HTML**.
2. Cấu hình **reports.html**, **reports.junitXml**, output locations và lựa chọn ghi stdout/stderr.
3. Đọc các trường JUnit XML như **tests, failures, errors, skipped, time** và testcase names.
4. Dùng **TestReport** và **test-report-aggregation** để tổng hợp kết quả theo dự án/suite.
5. Tạo ví dụ đa module Java 17 với JUnit 5: hai module, bốn test methods, XML/HTML riêng và HTML tổng hợp.
6. Chạy Java code bằng **javac --release 17**/**java** và phân biệt việc này với thực thi JUnit.
7. Viết GitHub Actions workflow bảo toàn exit code Gradle, dùng **--continue** và upload reports với **if: always()**.
8. Áp dụng tương tự trên GitLab CI/Jenkins, đặt artifact retention và quyền truy cập phù hợp.
9. Tránh đếm trùng do retry/matrix, XML merge sai, thiếu reports do task NO-SOURCE hoặc Gradle failure.
10. Kiểm tra quality gate và bảo mật của các artifacts chứa test names, stack traces hoặc logs.

## 2. Dòng chảy từ test execution đến CI artifacts

~~~text
Commit / pull request
         |
         v
Gradle Wrapper + JDK 17 + dependencies
         |
         +--> :calculator:test
         |       +--> HTML
         |       +--> TEST-demo.calc.CalculatorTest.xml
         |       +--> binary test results
         |
         +--> :text:test
                 +--> HTML
                 +--> TEST-demo.text.SlugTest.xml
                 +--> binary test results
         |
         v
Gradle test-report-aggregation
         |
         +--> Aggregate HTML
         |
         v
CI upload (always, kể cả test FAILED)
         |
         +--> JUnit XML artifacts
         +--> Per-module HTML artifacts
         +--> Aggregate HTML artifact
         |
         v
Test UI / reviewer / audit / debugging
~~~

**Thực thi kiểm thử** và **lưu bằng chứng kiểm thử** là hai trách nhiệm riêng. Gradle Test task quyết định kết quả dựa trên tests; CI giữ các tệp để người khác có thể xem sau khi runner kết thúc.

Nếu tests fail nhưng CI chỉ upload artifact ở nhánh success, team có thể mất reports. Nếu CI dùng **|| true** để tránh fail trước bước upload, bạn có thể làm pipeline xanh giả. Quy trình đúng là: **để Gradle fail thật, đồng thời luôn thực hiện bước lưu bằng chứng**.

## 3. Ba định dạng kết quả quan trọng của task Test

| Định dạng | Người dùng chính | Chứa thông tin gì? | Vị trí phổ biến cho task test |
| --- | --- | --- | --- |
| **HTML report** | Developer/QA | Summary, class/method, failures, stack traces | build/reports/tests/test/index.html |
| **JUnit XML** | CI publisher/analytics | Testsuite, testcase, status, thời gian, lỗi | build/test-results/test/TEST-*.xml |
| **Binary test results** | Gradle TestReport/aggregation | Dữ liệu Gradle dùng dựng báo cáo | build/test-results/test/binary/ |

Các đường dẫn trên là **quy ước mặc định phổ biến**, không phải mọi bản Gradle/plugin đều luôn dùng chính xác chúng. Nếu task tên **integrationTest**, đường dẫn thường có **integrationTest** thay **test**. Nếu thay **reporting.baseDirectory**, **java.testResultsDir** hoặc từng report outputLocation, cần sửa các CI glob cho đúng.

### 3.1. HTML report

HTML chứa giao diện điều hướng để xem class/test details và failures. Một số tập tin CSS, JavaScript và asset nằm cạnh **index.html**, vì vậy **không chỉ upload index.html** rồi hy vọng mọi liên kết/format còn hoạt động.

HTML hữu ích khi một reviewer muốn mở report mà không cần cài công cụ XML. Nhưng việc upload HTML không tự làm GitHub/GitLab/Jenkins hiện một test dashboard machine-readable.

### 3.2. JUnit XML

JUnit XML là định dạng “pseudo-standard” được nhiều CI providers hỗ trợ. Ví dụ cấu trúc minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="demo.calc.CalculatorTest"
           tests="2" failures="0" errors="0" skipped="0">
  <testcase classname="demo.calc.CalculatorTest"
            name="addsTwoNumbers" time="0.001"/>
  <testcase classname="demo.calc.CalculatorTest"
            name="rejectsDivisionByZero" time="0.001"/>
</testsuite>
~~~

**Đây là XML minh họa, không phải report thực đã đo.** Gradle có thể thêm timestamps, properties, stdout, stack traces và các thuộc tính khác. CI parser có thể phân biệt **failure** với **error** hoặc cách biểu diễn retries. Không giả định XML từ Gradle, Surefire, TestNG và các runners khác hoàn toàn giống nhau.

### 3.3. Binary test results

Gradle dùng định dạng nhị phân nội bộ để xây dựng và gộp reports. **TestReport** có thể lấy kết quả nhị phân của nhiều Test tasks để tạo HTML mới; **test-report-aggregation** lấy test-result variants của các subprojects.

Đừng tự ghép, chỉnh hoặc parse thư mục **binary/** bằng một script tùy ý rồi coi đó là public stable file format. Khi CI cần đọc test outcomes, **JUnit XML** thường là giao diện phù hợp hơn.

## 4. Cách Java plugin cung cấp task Test

Với:

~~~groovy
plugins {
    id 'java'
}
~~~

Java plugin tạo source set **test** và task **test** kiểu **org.gradle.api.tasks.testing.Test**. Test task có hai thông tin cốt lõi:

- **testClassesDirs**: nơi chứa compiled test classes.
- **classpath**: classes under test, compiled test classes/resources, test framework và runtime dependencies.

Task **test** không phải **compileTestJava**: Java test source có thể compile nhưng test execution vẫn fail vì thiếu JUnit engine/launcher, test configuration hoặc runtime dependencies.

Gradle Java plugin nối task **test** vào **check**. Những test suites tự tạo như **integrationTest** cần wiring riêng (hoặc JVM Test Suite plugin); không suy rằng mỗi task kiểu Test được check chọn tự động.

### 4.1. Đoạn cấu hình JUnit 5 nền tảng

~~~groovy
plugins {
    id 'java'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là đoạn cấu hình minh họa, cần repository và file Java test source mới chạy được. Ví dụ đầy đủ ở mục 10 có **settings.gradle**, các **build.gradle** và toàn bộ Java classes.

**JUnit Jupiter** cung cấp JUnit 5 test API/engine theo dependency metadata. **JUnit Platform Launcher** được khai báo riêng để việc chạy trên Gradle không dựa vào dependency transitive vô tình từ Gradle distribution.

### 4.2. testLogging không thay thế test reports

~~~groovy
tasks.named('test', Test) {
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**testLogging** quyết định các events xuất hiện trong console ở các mức log; nó không thay thế **reports.html** hoặc **reports.junitXml**. Nếu bật **passed** cho hàng chục nghìn test, CI console có thể phình to và làm lộ dữ liệu không cần thiết.

Lệnh **./gradlew test --info** có thể in nhiều thông tin hơn, nhưng một log console dài không phải bằng chứng thay thế cho JUnit XML có cấu trúc.

## 5. Cấu hình reports trong Groovy DSL

Mẫu chung:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
        junitXml.outputPerTestCase = true
        junitXml.includeSystemOutLog = false
        junitXml.includeSystemErrLog = false
    }

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**configureEach** áp dụng cấu hình cho các Test tasks có sẵn và được đăng ký sau, mà không bắt Gradle hiện thực mọi task sớm.

### 5.1. html.required và junitXml.required

- **html.required = true** bật HTML report.
- **junitXml.required = true** bật JUnit XML result files.
- Hai loại báo cáo thường đã bật theo convention nhưng khai báo tường minh giúp CI policy rõ ràng khi plugin khác có thể tắt chúng.
- Việc bật báo cáo **không tự làm một task Test được chọn chạy**. Nếu task NO-SOURCE, SKIPPED, hoặc build fail trước khi test khởi động, report có thể trống/không tồn tại.

### 5.2. outputPerTestCase

**junitXml.outputPerTestCase = true** thay cách gắn output logs vào từng testcase thay vì toàn class/suite khi stdout/stderr được xuất. Nếu đồng thời tắt **includeSystemOutLog** và **includeSystemErrLog**, XML sẽ không lưu các logs đó; flag outputPerTestCase vẫn hợp lệ nhưng gần như không có tác dụng với output đã bị tắt.

### 5.3. includeSystemOutLog/includeSystemErrLog

Gradle thường mặc định lưu stdout/stderr vào XML. Việc test in API token, database URL chứa password hoặc payload khách hàng có thể khiến báo cáo trở thành nguồn rò rỉ. Cần:

- Không log secrets ngay từ test code.
- Mask/sanitize dữ liệu có khả năng nhạy cảm.
- Chỉ bật stdout/stderr export khi thực sự cần debug.
- Hạn chế quyền xem artifacts và retention.
- Hiểu rằng tắt system out/err **không loại được secrets trong exception messages/stack traces hoặc tên testcase**.

### 5.4. Tùy chỉnh output locations

Có thể chỉ đổi task test:

~~~groovy
tasks.named('test', Test) {
    reports.html.outputLocation =
        layout.buildDirectory.dir('reports/tests/unit')

    reports.junitXml.outputLocation =
        layout.buildDirectory.dir('test-results/unit')
}
~~~

**Đoạn này là cấu hình thay thế** cho đường dẫn mặc định của lab. Sau khi đặt custom outputLocation, phải cập nhật glob CI. Không kết luận “thiếu report” nếu nó chỉ bị chuyển sang thư mục khác.

Các conventions cấp project cũng có thể dùng:

~~~groovy
reporting.baseDirectory = file('team-reports')
java.testResultsDir = layout.buildDirectory.dir('my-test-results')
~~~

Đây là minh họa; ảnh hưởng đến một nhóm Test tasks thay vì một task duy nhất. Đừng đổi đường dẫn nếu không có nhu cầu, bởi nhiều CI scripts thường đã dựa vào conventions mặc định.

## 6. Đọc các trường JUnit XML

| Trường | Ý nghĩa thường dùng | Lưu ý |
| --- | --- | --- |
| **tests** | Số testcase executions | Không nhất thiết bằng số method source |
| **failures** | Test assertion failures | Cần fail quality gate |
| **errors** | Lỗi thực thi/framework | Có thể được runner phân biệt với failures |
| **skipped** | Tests không chạy | Phải kiểm tra có chủ đích không |
| **time** | Thời lượng suite/testcase | So sánh cùng convention/runner |
| **testcase.classname/name** | Danh tính một testcase | Parameterized/dynamic names có thể thay đổi |
| **failure/error** | Chi tiết lỗi, stack trace | Có thể chứa dữ liệu nhạy cảm |
| **system-out/system-err** | Logs nếu được bật | Kiểm tra secrets và dung lượng |

Với một định nghĩa metric thường dùng:

~~~text
passed = tests - failures - errors - skipped
executed = tests - skipped
pass_rate = passed / executed
~~~

Nếu **executed = 0**, ghi **N/A — không có test thực thi**; đừng báo pass rate 100%. Công thức chỉ phù hợp khi các trường theo cùng định nghĩa và không bị retries/duplicate counting làm sai cách diễn giải.

### 6.1. XML không phải test report của toàn build

Trong multi-project build:

~~~text
calculator/build/test-results/test/TEST-demo.calc.CalculatorTest.xml
text/build/test-results/test/TEST-demo.text.SlugTest.xml
~~~

Đây là hai output ở **hai build directories khác nhau**. Nếu CI chỉ tìm **build/test-results/test/TEST-*.xml** ở root, nó bỏ qua cả hai.

### 6.2. Không dùng cat để gộp XML

Đoạn sau **cố ý sai**:

~~~bash
cat calculator/build/test-results/test/TEST-*.xml \
    text/build/test-results/test/TEST-*.xml \
    > build/all-tests.xml
~~~

Nối nhiều XML declarations/root elements không tạo một XML document hợp lệ. CI thường nhận **nhiều XML files**; hãy đưa chúng vào publisher bằng glob. Nếu cần một XML duy nhất, dùng công cụ XML-aware hỗ trợ schema và retry semantics cụ thể.

### 6.3. Reruns và flaky tests

Gradle có flag:

~~~groovy
tasks.withType(Test).configureEach {
    reports.junitXml.mergeReruns = true
}
~~~

Khi một runner/plugin **thực sự retry** test fail rồi pass, XML có thể biểu diễn các failures trước đó bằng **flakyFailure** trong một testcase. **mergeReruns không tự thực hiện retry.**

Một số CI parsers không hiểu flakyFailure và có thể hiển thị testcase success mà không thấy lần fail trước. Vì vậy cần xác định chính sách flakiness riêng, lưu evidence của các lượt chạy nếu nhóm muốn truy tìm lỗi nondeterministic.

## 7. Tổng hợp kết quả trong một project

### 7.1. TestReport khác Test

Task **Test** thực thi test. Task **TestReport** nhận test results đã được tạo và sinh báo cáo HTML tổng hợp.

Nếu project đã có **test** và **integrationTest** tasks:

~~~groovy
tasks.register('allJvmTestsReport', TestReport) {
    destinationDirectory =
        layout.buildDirectory.dir('reports/tests/allJvm')

    testResults.from(
        tasks.named('test', Test),
        tasks.named('integrationTest', Test))
}
~~~

**Snippet chỉ chạy khi task integrationTest đã được đăng ký và cấu hình đúng.** TestReport lấy binary test results của hai Test tasks; nó không tự tạo JUnit XML tổng hợp và không thay thế JUnit runtime.

### 7.2. Không tự động gộp mọi source set

Nếu tự tạo source set **integrationTest**, Gradle thường tự tạo compile/resources/classes tasks nhưng **không tự tạo Test task**. Cần:

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs =
        sourceSets.integrationTest.output.classesDirs

    classpath =
        sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

Đây là **đoạn minh họa bổ sung**: muốn chạy được còn phải khai báo sourceSets.integrationTest, dependencies tương ứng và test source. Không trộn nó vào lab ở mục 10 vì lab dùng hai module với default **test** suite.

## 8. Tổng hợp nhiều subprojects: test-report-aggregation

### 8.1. Vì sao dùng plugin chuyên dụng?

Gradle có core plugin **test-report-aggregation**. Nó dùng **variant-aware resolution** để lấy kết quả test được Gradle công bố từ nhiều projects, thường thông qua **testReportAggregation** dependency configuration, rồi xây một HTML report.

Đối với JVM test suite mặc định **test**, những result variants dùng attributes như:

~~~text
org.gradle.category          = verification
org.gradle.testsuite.name    = test
org.gradle.verificationtype  = test-results
~~~

Đây là metadata phục vụ resolve báo cáo, không phải JAR production của thư viện. Consumer root report chọn test-results variant phù hợp thay vì copy một thư mục XML tùy ý.

### 8.2. Root aggregator không phải Java application

Một root project chỉ dùng để báo cáo có thể:

~~~groovy
plugins {
    id 'base'
    id 'test-report-aggregation'
}

dependencies {
    testReportAggregation project(':calculator')
    testReportAggregation project(':text')
}

reporting {
    reports {
        testAggregateTestReport(AggregateTestReport) {
            testSuiteName = 'test'
        }
    }
}
~~~

**Đây là mô hình root của lab ở mục 10.** Root không áp dụng **java** nên phải khai báo AggregateTestReport tường minh theo DSL được Gradle cung cấp. Với build mà project aggregation cũng áp dụng JVM Test Suite, Gradle có thể tự tạo aggregate tasks cho suites có tên tương ứng; task naming/cấu hình cần được kiểm tra theo plugin version.

### 8.3. Đừng nhầm HTML aggregation với XML publishing

- **Aggregate HTML:** Gradle TestReport/test-report-aggregation tạo từ binary test results.
- **JUnit XML per-task/per-module:** có thể được CI publisher parse trực tiếp.
- **CI test dashboard:** tính năng của CI provider hoặc plugin; upload-artifact đơn thuần không tự tạo test dashboard.
- **JaCoCo report:** code coverage, không phải pass/fail testcase.

### 8.4. Chú ý giới hạn

- Report aggregation cần producer projects công bố test-results variants tương ứng.
- **testSuiteName='test'** không tự chọn suite tên **integrationTest**.
- Root không tự có kết quả từ các external Maven libraries hoặc job khác workspace.
- TestReport có thể khó phân biệt các executions của **cùng testcase/class** chạy trong nhiều tasks; gắn suite/task identity khi debug.
- Tài liệu Gradle nêu giới hạn với **com.android.application**; với Android hãy dùng reporting phù hợp với Android Gradle Plugin.
- Tên task/đường dẫn reports có thể thay đổi theo Gradle Wrapper và cấu hình, phải kiểm tra thực tế qua **tasks --all**.

## 9. Khi test fail: báo cáo vẫn cần tồn tại, CI vẫn phải đỏ

### 9.1. --continue

Lệnh:

~~~bash
./gradlew --continue check testAggregateTestReport
~~~

yêu cầu Gradle tiếp tục những task độc lập còn có thể chạy khi một task fail. Nếu test task fail, Gradle vẫn trả status khác 0. **--continue không biến build failed thành success**, cũng không bảo đảm aggregate report luôn hoàn tất nếu dữ liệu hoặc task prerequisites không tồn tại.

Nên upload **per-module HTML/XML đã sinh** trong mọi trường hợp; aggregate HTML có thể vắng mặt khi build fail sớm.

### 9.2. Các trạng thái không thể đánh đồng

| Trạng thái | Ý nghĩa | Có thể kết luận test pass? |
| --- | --- | --- |
| Test task SUCCESS | Task thực thi thành công | Có, trong phạm vi những tests thực sự chạy |
| Test task FAILED | Có test failure hoặc execution problem | Không |
| Test task UP-TO-DATE | Inputs/outputs không đổi | Không có test execution mới |
| Test task FROM-CACHE | Output được phục hồi | Cần hiểu cache provenance, không phải test mới chạy |
| Test task NO-SOURCE | Không có test classes/source phù hợp | Không |
| Test task SKIPPED | Bị bỏ qua theo logic | Không |
| compileTestJava FAILED | Chưa đến giai đoạn chạy JUnit | Không có XML execution mới |
| Aggregate task FAILED/SKIPPED | HTML tổng hợp chưa hoàn tất | Per-module XML vẫn có thể tồn tại |

**BUILD SUCCESSFUL** không phải bằng chứng rằng 100% test cases mong đợi đã được phát hiện. Cần xem reports và test counts; một suite không có test có thể bị bỏ qua mà không tạo những testcase bạn kỳ vọng.

### 9.3. Những anti-patterns trên CI

Sai:

~~~bash
./gradlew test || true
~~~

Sai khi dùng với quality gate:

~~~groovy
tasks.named('test', Test) {
    ignoreFailures = true
}
~~~

Hai cách này có thể làm CI không phản ánh đúng test failures. Thay vì che lỗi, giữ exit status Gradle và để bước upload báo cáo chạy với **always/on-failure**.

### 9.4. failFast khác --continue

**failFast** dừng sớm việc chạy các tests trong một Test task khi gặp lỗi; vì thế report có thể thiếu các tests chưa thực thi. **--continue** ảnh hưởng scheduler giữa Gradle tasks. Cần chọn policy theo mục đích: PR muốn fail sớm hay nightly cần thu mọi failures. Không dùng một tùy chọn để thay thế tùy chọn còn lại.

## 10. Lab runnable: Java 17, hai module và aggregate HTML

Ta sẽ tạo root **test-evidence-lab**, module **:calculator** với 2 JUnit tests và module **:text** với 2 JUnit tests. Root áp dụng aggregation plugin. Ví dụ được thiết kế không có intentional failure; số testcase kỳ vọng từ Java source là **4**, không phải số đã đo từ CI bên ngoài.

### 10.1. Cấu trúc

~~~text
test-evidence-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── calculator/
│   ├── build.gradle
│   ├── src/main/java/demo/calc/Calculator.java
│   ├── src/main/java/demo/calc/CalculatorMain.java
│   └── src/test/java/demo/calc/CalculatorTest.java
├── text/
│   ├── build.gradle
│   ├── src/main/java/demo/text/Slug.java
│   ├── src/main/java/demo/text/SlugMain.java
│   └── src/test/java/demo/text/SlugTest.java
└── .github/
    └── workflows/tests.yml
~~~

Nếu chưa có Wrapper, dùng Gradle CLI đã cài phiên bản tương thích để chạy **gradle wrapper**, commit các Wrapper files và dùng **./gradlew** trên Unix hoặc **.\gradlew.bat** trên Windows. Cần JDK chạy được Gradle Wrapper cùng Java 17 toolchain; các thư viện JUnit được tải từ Maven Central hoặc mirror được phê duyệt. Ví dụ phù hợp với Gradle hiện đại hỗ trợ test-report-aggregation (chẳng hạn Gradle 9.x).

### 10.2. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'test-evidence-lab'
include ':calculator', ':text'
~~~

### 10.3. Root build.gradle

~~~groovy
plugins {
    id 'base'
    id 'test-report-aggregation'
}

group = 'demo.evidence'
version = '1.0'

dependencies {
    testReportAggregation project(':calculator')
    testReportAggregation project(':text')
}

reporting {
    reports {
        testAggregateTestReport(AggregateTestReport) {
            testSuiteName = 'test'
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('testAggregateTestReport'))
}
~~~

Giải thích:

1. **base** tạo lifecycle tasks, gồm **check**, ở root.
2. **test-report-aggregation** cung cấp configuration và reporting API.
3. **testReportAggregation project(...)** chọn các source projects có test result variants.
4. Root không có JVM test suite nên khai báo report type **AggregateTestReport** với suite tên **test**.
5. **testAggregateTestReport** là task/báo cáo tổng hợp tương ứng được Gradle tạo.
6. **check.dependsOn** đưa aggregate HTML vào quality lifecycle; không ngăn việc chạy các per-module test tasks độc lập.

### 10.4. calculator/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.evidence'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
        junitXml.outputPerTestCase = true
        junitXml.includeSystemOutLog = false
        junitXml.includeSystemErrLog = false
    }
}

tasks.register('runDemo', JavaExec) {
    group = 'application'
    dependsOn(tasks.named('classes'))
    classpath = sourceSets.main.runtimeClasspath
    mainClass.set('demo.calc.CalculatorMain')
}
~~~

**java-library** cung cấp test suite/model giúp Gradle có thể xuất test result variant. **runDemo** chỉ để chạy Java Main riêng, không phải JUnit Test task.

### 10.5. calculator/src/main/java/demo/calc/Calculator.java

~~~java
package demo.calc;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static int divide(int a, int b) {
        return a / b;
    }
}
~~~

### 10.6. calculator/src/main/java/demo/calc/CalculatorMain.java

~~~java
package demo.calc;

public final class CalculatorMain {
    private CalculatorMain() {
    }

    public static void main(String[] args) {
        System.out.println("SUM=" + Calculator.add(3, 4));
    }
}
~~~

Stdout:

~~~text
SUM=7
~~~

### 10.7. calculator/src/test/java/demo/calc/CalculatorTest.java

~~~java
package demo.calc;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void rejectsDivisionByZero() {
        assertThrows(
                ArithmeticException.class,
                () -> Calculator.divide(4, 0));
    }
}
~~~

Hai test methods **addsTwoNumbers** và **rejectsDivisionByZero** dự kiến pass. Việc **assertThrows** bắt ngoại lệ mong muốn là một kết quả test pass, không phải failure.

### 10.8. text/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.evidence'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
        junitXml.outputPerTestCase = true
        junitXml.includeSystemOutLog = false
        junitXml.includeSystemErrLog = false
    }
}

tasks.register('runDemo', JavaExec) {
    group = 'application'
    dependsOn(tasks.named('classes'))
    classpath = sourceSets.main.runtimeClasspath
    mainClass.set('demo.text.SlugMain')
}
~~~

Hai module có build logic tương tự để người học theo dõi dễ dàng. Trong monorepo lớn, nên gom các quy ước lặp lại vào convention plugin và vẫn giữ cấu hình JUnit dependency/scopes rõ ràng.

### 10.9. text/src/main/java/demo/text/Slug.java

~~~java
package demo.text;

import java.util.Locale;

public final class Slug {
    private Slug() {
    }

    public static String normalize(String raw) {
        return raw.toLowerCase(Locale.ROOT)
                .trim()
                .replaceAll("[^a-z0-9]+", "-")
                .replaceAll("(^-|-$)", "");
    }
}
~~~

**Locale.ROOT** giúp kết quả chữ hoa/thường ổn định giữa các máy. Demo chỉ hỗ trợ ASCII a–z và số, không phải thuật toán chuyển đổi Unicode tổng quát.

### 10.10. text/src/main/java/demo/text/SlugMain.java

~~~java
package demo.text;

public final class SlugMain {
    private SlugMain() {
    }

    public static void main(String[] args) {
        System.out.println(
                "SLUG=" + Slug.normalize("Hello Gradle!"));
    }
}
~~~

Stdout:

~~~text
SLUG=hello-gradle
~~~

### 10.11. text/src/test/java/demo/text/SlugTest.java

~~~java
package demo.text;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SlugTest {
    @Test
    void normalizesWhitespaceAndCase() {
        assertEquals(
                "hello-gradle",
                Slug.normalize("  Hello Gradle!  "));
    }

    @Test
    void normalizesPunctuation() {
        assertEquals(
                "java-17",
                Slug.normalize("Java_17"));
    }
}
~~~

Hai methods dự kiến pass. Vậy :calculator:test có 2 tests, :text:test có 2 tests, tổng **4 executions** trong một lần chạy bình thường.

## 11. Chạy lab trên Gradle

Linux/macOS:

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all

./gradlew :calculator:test
./gradlew :text:test

./gradlew testAggregateTestReport
./gradlew --continue check testAggregateTestReport

./gradlew -q :calculator:runDemo
./gradlew -q :text:runDemo
~~~

Hai Java main methods in:

~~~text
SUM=7
SLUG=hello-gradle
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :calculator:test
.\gradlew.bat :text:test
.\gradlew.bat testAggregateTestReport
.\gradlew.bat --continue check testAggregateTestReport
.\gradlew.bat -q :calculator:runDemo
.\gradlew.bat -q :text:runDemo
~~~

**Đầu ra báo cáo dự kiến:**

~~~text
calculator/build/reports/tests/test/index.html
calculator/build/test-results/test/TEST-demo.calc.CalculatorTest.xml
calculator/build/test-results/test/binary/...

text/build/reports/tests/test/index.html
text/build/test-results/test/TEST-demo.text.SlugTest.xml
text/build/test-results/test/binary/...

build/reports/tests/testAggregateTestReport/index.html
~~~

Các đường dẫn module dùng conventions. Đường dẫn aggregate có thể khác nếu Gradle/reporting configuration thay đổi; hãy kiểm tra output task hoặc tìm dưới **build/reports/** thay vì giả định cứng.

Kiểm tra JUnit XML để xác nhận test counts, không chỉ suy từ mã nguồn. Nếu không có test execution report, kiểm tra **test** task outcomes và dependency resolution.

### 11.1. Không nhầm UP-TO-DATE với không có test

Lần thứ hai gọi **./gradlew :calculator:test**, task có thể UP-TO-DATE hoặc FROM-CACHE và không in test events; đó không phải bằng chứng có 0 tests. Hãy kiểm tra output report, cache provenance và số testcase. Khi cần ép chạy để điều tra:

~~~bash
./gradlew :calculator:test --rerun-tasks --info
~~~

Không dùng **--rerun-tasks** làm cấu hình CI mặc định khi không cần, vì sẽ làm lại những công việc có thể được Gradle tối ưu hợp lệ.

## 12. Xác minh Java 17 bằng javac/java

Các class production của demo chỉ dùng Java standard library, có thể biên dịch không cần Gradle/JUnit để đối chiếu Java source:

~~~bash
mkdir -p out/calculator out/text

javac --release 17 -d out/calculator \
  calculator/src/main/java/demo/calc/Calculator.java \
  calculator/src/main/java/demo/calc/CalculatorMain.java

javac --release 17 -d out/text \
  text/src/main/java/demo/text/Slug.java \
  text/src/main/java/demo/text/SlugMain.java

java -cp out/calculator demo.calc.CalculatorMain
java -cp out/text demo.text.SlugMain
~~~

Stdout:

~~~text
SUM=7
SLUG=hello-gradle
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\calculator | Out-Null
New-Item -ItemType Directory -Force out\text | Out-Null
javac --release 17 -d out\calculator calculator\src\main\java\demo\calc\Calculator.java calculator\src\main\java\demo\calc\CalculatorMain.java
javac --release 17 -d out\text text\src\main\java\demo\text\Slug.java text\src\main\java\demo\text\SlugMain.java
java -cp out\calculator demo.calc.CalculatorMain
java -cp out\text demo.text.SlugMain
~~~

**Đây không phải test reporting check.** Các lệnh xác minh hai chương trình Java 17, còn **Gradle :calculator:test/:text:test** mới thực thi JUnit và tạo XML/HTML; root **testAggregateTestReport** mới kiểm tra tổng hợp Gradle; CI job mới xác minh việc lưu evidence sau một run.

## 13. GitHub Actions: lưu reports dù build thất bại

Tạo file **.github/workflows/tests.yml**:

~~~yaml
name: Java tests and evidence

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle setup
        uses: gradle/actions/setup-gradle@v6

      - name: Verify tests and build aggregate report
        run: ./gradlew --continue check testAggregateTestReport

      - name: Upload JUnit XML
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-xml
          path: |
            calculator/build/test-results/test/TEST-*.xml
            text/build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14

      - name: Upload HTML reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-html
          path: |
            calculator/build/reports/tests/**
            text/build/reports/tests/**
            build/reports/**
          if-no-files-found: warn
          retention-days: 14
~~~

### 13.1. Tại sao workflow này giữ đúng quality gate?

**Gradle build step** trả exit code thật. Test failure làm job thất bại; workflow không dùng **|| true**, **continue-on-error** hay **ignoreFailures**.

**if: always()** là cú pháp GitHub Actions cho bước phải chạy bất kể trạng thái bước trước, nên hai upload steps vẫn cố giữ những files đã sinh khi test fail.

**--continue** cho Gradle cơ hội chạy các tests độc lập và aggregate report sau một failure. Nó **không bảo đảm mọi report tồn tại** nếu thiếu compiled tests, dependency resolution hỏng hoặc aggregate task không thể chạy. Vì vậy CI upload cả **per-module** reports chứ không chỉ aggregate HTML.

### 13.2. Upload artifact không tự tạo dashboard test

**actions/upload-artifact** lưu file. Để GitHub hiển thị test case annotations hoặc PR check summary từ XML, cần một JUnit publisher/action khác được tổ chức cho phép. Trên GitLab, có thể dùng **artifacts.reports.junit**; trên Jenkins có JUnit plugin.

### 13.3. Retention và permissions

**retention-days: 14** chỉ là ví dụ, không phải chính sách bắt buộc. Dự án thực cần chọn hạn lưu theo quy định và quyền của tổ chức, nhất là khi stack traces/logs có thể chứa thông tin nội bộ.

**permissions: contents: read** hạn chế quyền workflow khi không cần ghi repository. Nếu organization yêu cầu pin SHA cho GitHub Actions để bảo vệ chuỗi cung ứng, dùng SHA đã kiểm duyệt thay cho major tag. Không đưa tokens vào YAML hoặc JUnit XML.

Nếu CI chạy matrix, đặt tên artifact theo OS/JDK/run ID để tránh upload conflicts. Một GitHub Actions run đơn giản chỉ có một job như demo nên tên **junit-xml** và **test-html** không xung đột nội bộ.

### 13.4. Nếu report trống thì sao?

Khi Gradle fail trước lúc task Test chạy, **if-no-files-found: warn** báo không tìm thấy report. Đừng hiểu cảnh báo đó là test pass. Khi policy bắt buộc evidence, thêm validation riêng kiểm tra số XML files/testcase counts và đưa ra failure rõ ràng nếu thiếu.

Không upload cả thư mục repository/workspace chỉ để chắc chắn giữ evidence. Artifact paths nên nhắm đúng HTML/XML và nguồn phụ trợ có chủ đích.

## 14. GitLab CI và Jenkins: cùng nguyên tắc

### 14.1. GitLab CI

Ví dụ **.gitlab-ci.yml**:

~~~yaml
stages:
  - test

java-tests:
  stage: test
  image: eclipse-temurin:17-jdk
  script:
    - bash ./gradlew --continue check testAggregateTestReport

  artifacts:
    when: always
    expire_in: 14 days
    paths:
      - calculator/build/reports/tests/
      - text/build/reports/tests/
      - build/reports/
      - calculator/build/test-results/test/
      - text/build/test-results/test/
    reports:
      junit:
        - calculator/build/test-results/test/TEST-*.xml
        - text/build/test-results/test/TEST-*.xml
~~~

**artifacts.when: always** cho phép giữ các file đã tạo khi script fail. **artifacts.reports.junit** đưa XML vào GitLab test results UI. Cần kiểm tra glob, repository permissions, artifact size và runner environment theo GitLab version thực tế.

### 14.2. Jenkins

Với Jenkins Declarative Pipeline:

~~~groovy
pipeline {
    agent any

    stages {
        stage('Tests') {
            steps {
                sh './gradlew --continue check testAggregateTestReport'
            }
        }
    }

    post {
        always {
            junit testResults:
                '**/build/test-results/test/TEST-*.xml',
                allowEmptyResults: true

            archiveArtifacts artifacts:
                '**/build/reports/tests/**',
                allowEmptyArchive: true
        }
    }
}
~~~

Đây là mẫu tích hợp, cần agent có JDK phù hợp và JUnit plugin. **allowEmptyResults** tránh publisher che lỗi gốc nếu Gradle fail trước khi sinh test XML, nhưng cần một quality rule riêng nếu reports là bắt buộc. Không bật catchError/bỏ failure status chỉ vì cần lưu artifacts.

## 15. Tổng hợp thống kê JUnit XML đúng cách

Với lab có hai XML files, ta có thể viết một Python 3 script chỉ dùng standard library để kiểm tra counts, không cần parse HTML. Đây là tiện ích thêm, không thay Gradle TestReport.

**scripts/summarize_junit.py**:

~~~python
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

if len(sys.argv) < 2:
    print("Usage: summarize_junit.py <dir> [dir ...]", file=sys.stderr)
    sys.exit(2)

files = []
for directory in sys.argv[1:]:
    files.extend(sorted(Path(directory).glob("TEST-*.xml")))

if not files:
    print("No JUnit XML files found", file=sys.stderr)
    sys.exit(2)

counts = {
    "suites": 0, "tests": 0, "failures": 0,
    "errors": 0, "skipped": 0
}

for file in files:
    root = ET.parse(file).getroot()

    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = root.findall("./testsuite")
    else:
        raise ValueError("Unsupported XML root: " + root.tag)

    if not suites:
        raise ValueError("Missing testsuite in " + str(file))

    for suite in suites:
        counts["suites"] += 1
        for key in ("tests", "failures", "errors", "skipped"):
            counts[key] += int(suite.get(key, "0"))

print(
    "SUITES={suites} TESTS={tests} FAILURES={failures} "
    "ERRORS={errors} SKIPPED={skipped}".format(**counts)
)
~~~

Lệnh:

~~~bash
python3 scripts/summarize_junit.py \
  calculator/build/test-results/test \
  text/build/test-results/test
~~~

Kết quả dự kiến cho bốn test methods:

~~~text
SUITES=2 TESTS=4 FAILURES=0 ERRORS=0 SKIPPED=0
~~~

**Không mặc định con số này luôn đúng trong dự án khác.** Parser cộng **executions mà XML công bố**, không dedupe retries, test matrix hoặc duplicate cases. Nếu XML có root structure đặc biệt, nested suites hoặc thiếu attributes, cần kiểm tra/adapt chứ không bịa số liệu. Script exit 2 nếu không tìm thấy XML, tránh tuyên bố “0 failures” như bằng chứng pass khi không có data.

Tín hiệu fail của Gradle vẫn là quality gate chính; script summary không sửa exit code của Test task và không thay việc upload XML gốc.

## 16. Matrix CI, parallel tests và phân biệt executions

### 16.1. Chạy cùng test trên nhiều environments

Nếu cùng testcase được chạy trên Java 17/Linux và Java 21/Windows, hai XML có thể báo cùng test name nhưng là **hai executions khác nhau**. Khi cộng các XML, tổng số test executions tăng là điều bình thường.

Đừng trình bày số executions như số unique test methods. Metadata nên gắn **OS, JDK, job ID, run attempt, branch, commit SHA**.

### 16.2. Task-level parallelism và forks

Gradle có **--parallel** để chạy tasks độc lập giữa projects, và task Test có **maxParallelForks** để phân phối test classes trên forked JVMs. Tests phải tránh:

- Dùng chung port cố định.
- Ghi chung một thư mục temp tên hardcoded.
- Sửa cùng database state không cô lập.
- Dùng account/data bất biến cho nhiều workers.
- Dựa vào execution order không được bảo đảm.

Test JVM có system property **org.gradle.test.worker**, có thể dùng để phân biệt test worker khi đặt tên temporary resources.

### 16.3. Sharding trên nhiều CI jobs

Nếu CI chạy :calculator:test ở job A và :text:test ở job B, mỗi job có workspace riêng. Root aggregate task ở job B **không tự đọc được binary results của job A**. Cần cơ chế upload/download kết quả hợp lệ, hoặc để CI JUnit publisher tổng hợp XML từ cả hai jobs.

Không tuyên bố aggregate HTML ở một job đơn là đã đại diện tất cả shards nếu chưa thu thập results thật.

## 17. Dữ liệu nhạy cảm trong test evidence

Các báo cáo có thể chứa:

- Test names có customer IDs.
- Stack traces có filesystem/internal paths.
- Database connection strings.
- Payloads được in vào stdout/stderr.
- Screenshots chứa PII.
- Đường dẫn endpoint, API request headers hoặc tokens.
- File fixtures không phải tài liệu công khai.

Chính sách nên gồm:

1. **Không log secrets ngay trong test code.**
2. Tắt XML system stdout/stderr nếu không cần.
3. Mask dữ liệu trong exceptions và logs.
4. Chỉ upload những report directories cần thiết.
5. Đặt permissions/retention rõ ràng.
6. Phân biệt public fork PRs với builds có secrets.
7. Không commit reports sinh tự động vào Git source tree.
8. Nếu cần lưu lâu cho audit, dùng artifact storage nội bộ/immutable versioned evidence thay vì phụ thuộc retention mặc định của CI.

**Lưu ý:** bỏ stdout khỏi JUnit XML không ngăn exception messages hoặc stack traces chứa dữ liệu nhạy cảm. Nên sửa nguồn lộ dữ liệu, không chỉ chỉnh cờ report.

## 18. Test report khác coverage report

| Loại báo cáo | Mục đích | Công cụ thường dùng |
| --- | --- | --- |
| **JUnit XML** | Test execution outcomes | Gradle Test, CI publisher |
| **HTML test report** | Đọc testcase và failures | Gradle Test/TestReport |
| **Aggregate HTML** | Xem nhiều test result variants | Gradle test-report-aggregation |
| **JaCoCo HTML/XML** | Code coverage | Gradle JaCoCo Plugin |
| **Build Scan/Develocity** | Build execution insights | Gradle/Develocity theo policy |
| **Deployment/provenance artifact** | Trace binary/release | CI/CD supply-chain tooling |

Test pass 100% không chứng minh coverage 100%. JaCoCo coverage report không chứa đầy đủ testcase pass/fail, và JUnit XML cũng không chứa branch coverage. Nếu có yêu cầu quality gate về coverage, cấu hình JaCoCo verification riêng và lưu artifacts phù hợp.

## 19. Debugging checklist theo từng tầng

### 19.1. Không có HTML/XML

Kiểm tra:

~~~bash
./gradlew --version
./gradlew :calculator:tasks --all
./gradlew :calculator:test --info
./gradlew :text:test --info
~~~

Sau đó xác nhận task Test được chọn, JUnit engine có trên runtime classpath, reports.required=true và outputLocation không bị đổi. **NO-SOURCE/SKIPPED** không thể tự tạo bằng chứng execution thật.

### 19.2. Aggregate task không chạy

~~~bash
./gradlew tasks --all
./gradlew help --task testAggregateTestReport
./gradlew --continue testAggregateTestReport --info
~~~

Kiểm tra root có plugin **test-report-aggregation**, report **testSuiteName='test'**, dependencies tới đúng projects, và producer công bố test-results variants. Nếu báo **No matching variant**, đây là lỗi matching plugin/test suite metadata, không phải thiếu một file XML ở root.

### 19.3. CI không upload

Kiểm tra workflow:

- Upload step có **if: always()**?
- Paths tính từ đúng workspace/root?
- Module directories có report được tạo không?
- Artifact name có bị trùng giữa jobs/matrix?
- Repository permissions và retention có cho phép upload không?
- CI có bị canceled trước upload?
- Có cảnh báo **No files found** không?

Nếu Gradle fail ở phase configuration/compilation, có thể không có reports. Upload always giúp giữ **những gì đã có**, không thể tạo bằng chứng test chưa chạy.

### 19.4. Lệnh xác minh tệp

Linux/macOS:

~~~bash
find calculator/build/test-results \
  -type f -name 'TEST-*.xml'
find text/build/test-results \
  -type f -name 'TEST-*.xml'
find calculator/build/reports/tests \
  -type f -name 'index.html'
find text/build/reports/tests \
  -type f -name 'index.html'
find build/reports \
  -type f -name 'index.html'
~~~

PowerShell:

~~~powershell
Get-ChildItem calculator\build\test-results -Recurse -Filter TEST-*.xml
Get-ChildItem text\build\test-results -Recurse -Filter TEST-*.xml
Get-ChildItem build\reports -Recurse -Filter index.html
~~~

Nếu các directory chưa tồn tại, xác minh **task outcomes** thay vì tạo XML giả rồi upload.

## 20. Bảng lỗi phổ biến

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| BUILD SUCCESSFUL nhưng report không có test | NO-SOURCE, filter sai, engine thiếu | Kiểm tra testClassesDirs, JUnit Platform, testcase counts |
| Có XML nhưng CI test UI trống | Chỉ upload-artifact, chưa bật JUnit publisher | Cấu hình provider-specific parser |
| HTML chỉ có 1 module | Thiếu testReportAggregation dependency | Thêm project và xác minh test-results variant |
| Aggregate report không có | Task chưa đăng ký, testSuiteName sai | Kiểm tra plugin/reporting/task list |
| Report không sinh trên failure | Gradle dừng task graph | Dùng --continue, lưu per-module reports |
| CI đỏ nhưng artifact có | Đây là hành vi đúng | Đọc test failures thay vì xóa artifacts |
| CI xanh khi có assertion fail | ignoreFailures, || true, continue-on-error | Khôi phục exit code thật |
| Một JUnit XML thiếu | Build chưa chạy module đó, glob sai | Kiểm tra module test task/path |
| XML concat parse lỗi | Nhiều XML roots được ghép thô | Giữ file riêng hoặc dùng XML-aware merger |
| Test method bị đếm nhiều lần | Retried/parameterized/matrix executions | Phân biệt executions và unique test cases |
| FlakyFailure không hiện | CI parser không hỗ trợ | Review mergeReruns và retry policy |
| Artifact quá lớn | Upload toàn build directory | Chỉ giữ HTML/XML/cần thiết |
| Artifact lộ secret | Test output/exceptions chứa dữ liệu | Không log secrets, sanitize/restrict |
| Report mất sau clean | Tệp nằm dưới build directory | Upload trước cleanup |
| Test stdout không nằm trong XML | includeSystemOutLog=false | Đây là chủ đích bảo mật |
| JUnit Platform không chạy | Thiếu Launcher/engine hoặc useJUnitPlatform | Sửa testRuntimeOnly và Test task |
| Gradle task UP-TO-DATE | Inputs/outputs không thay đổi | Xem reports, --rerun-tasks khi debug |
| Gradle plugin không hỗ trợ Android | Ecosystem model khác JVM Java plugin | Dùng AGP/CI reporting tương ứng |
| JDK toolchain không tìm thấy | Runner/JDK/Gradle Wrapper không tương thích | Cài và cấu hình JDK đúng |

## 21. Bài tập thực hành

### Bài 1 — Quan sát hai HTML reports

Chạy **./gradlew :calculator:test :text:test**, mở hai file **index.html**, ghi số test và class names. Vì sao mỗi module có path **build/reports/** riêng?

### Bài 2 — Kiểm tra aggregate HTML

Chạy **./gradlew testAggregateTestReport**, mở báo cáo root và đối chiếu tổng dự kiến **4 tests**. Tại sao không thể chỉ copy hai index.html vào chung folder để có aggregation?

### Bài 3 — Làm test fail có chủ đích

Đổi tạm trong CalculatorTest:

~~~java
assertEquals(8, Calculator.add(3, 4));
~~~

Chạy **./gradlew --continue check testAggregateTestReport**. Xem task failure, XML của :calculator và artifacts đã có. Sau đó hoàn tác assertion để suite lại pass.

### Bài 4 — Thử upload thiếu always

Trong một branch thử nghiệm, bỏ **if: always()** khỏi upload step, làm test fail và quan sát các artifact steps bị skip. Khôi phục always; giải thích vì sao không được thay bằng **./gradlew test || true**.

### Bài 5 — Thay XML outputLocation

Thử đặt **reports.junitXml.outputLocation** của module :text thành một thư mục khác. Cập nhật CI upload path tương ứng. Vì sao report có thể tồn tại nhưng glob vẫn trả 0 file?

### Bài 6 — No tests case

Tạm chuyển tên class test hoặc cấu hình filtering để không có tests được phát hiện. Kiểm tra Test task outcome và phân biệt “no tests” với “all pass”.

### Bài 7 — Reruns

Nêu sự khác nhau giữa **mergeReruns=true** và **test retry plugin**. Khi CI parser không hiểu flakyFailure, cần quản trị flakiness thế nào?

### Bài 8 — Matrix CI

Thiết kế jobs Java 17/Linux và Java 21/Windows, đặt artifact name khác nhau. Khi cả hai chạy 4 tests, tổng executions là bao nhiêu? Số unique test methods có thay đổi không?

### Bài 9 — Security audit

Giả sử test cố tình in API token để debug. Chỉ bật **includeSystemOutLog=false** đã đủ an toàn chưa? Cần sửa thêm những chỗ nào để artifacts không lộ dữ liệu?

### Bài 10 — CI summary

Dùng script ở mục 15 đọc XML của hai module. Chạy khi một test fail để xem failures count. Giải thích vì sao script không tự thay thế exit code của Gradle hoặc HTML test report.

## 22. Câu hỏi tự kiểm tra

1. Gradle Test task có thể tạo ba loại kết quả nào?
2. Tại sao CI thường ưu tiên JUnit XML thay vì parse HTML?
3. TestReport có chạy JUnit tests không?
4. Cách bật useJUnitPlatform trong Test task là gì?
5. testLogging khác reports.html ở đâu?
6. Vì sao stdout/stderr trong XML có rủi ro bảo mật?
7. outputPerTestCase ảnh hưởng dữ liệu gì?
8. Một module có hai JUnit test methods thì XML thường thể hiện số testcase ra sao?
9. Khi nào NO-SOURCE khác SUCCESS?
10. Gradle --continue có trả exit status 0 nếu tests fail không?
11. Vì sao upload artifacts cần chạy always?
12. Tại sao không dùng || true trong quality gate?
13. Vì sao XML không nên gộp bằng cat?
14. test-report-aggregation lấy test results từ kiểu variant nào?
15. Vì sao cần testSuiteName đúng?
16. Khi nào aggregate HTML không đại diện đủ mọi CI shards?
17. Số test executions có luôn bằng số unique test methods không?
18. mergeReruns có kích hoạt retry không?
19. Cần lưu metadata nào để trace một artifact về source commit?
20. JaCoCo report có thay JUnit XML được không?
21. Artifact retention có thể ảnh hưởng privacy như thế nào?
22. Vì sao chỉ chạy javac/java production demo chưa chứng minh JUnit reporting thành công?

**Gợi ý đáp án:** (1) HTML, XML, binary; (2) machine-readable; (3) không; (4) useJUnitPlatform(); (5) console so với report files; (6) có thể chứa secret/PII; (7) gắn logs với testcase; (8) hai executions khi suite chạy bình thường; (9) NO-SOURCE không có test được chạy; (10) không; (11) giữ evidence sau fail; (12) che fail; (13) XML roots trùng; (14) verification/test-results; (15) tránh thiếu result variants; (16) khác workspace; (17) không; (18) không; (19) SHA, job/run/attempt, OS/JDK, task; (20) không, coverage khác test outcome; (21) lưu lâu có thể tăng rủi ro; (22) không chạy JUnit hoặc Gradle TestReport.

## 23. Checklist triển khai trong CI production

- [ ] Những Test tasks cần thiết đã được chọn bởi **check** hoặc CI command.
- [ ] Source test được biên dịch, JUnit engine/launcher có trên classpath.
- [ ] Test task có **useJUnitPlatform()** khi dùng JUnit 5.
- [ ] HTML và XML reports được bật ở đúng tasks.
- [ ] CI globs bao phủ đúng từng module và suite.
- [ ] XML chứa testcase thực, không phải 0 test mà được hiểu thành pass.
- [ ] Aggregate task nhận đúng test-results variants và testSuiteName.
- [ ] Khi test fail, Gradle status vẫn nonzero.
- [ ] Dùng --continue khi muốn thu thêm kết quả từ các tasks độc lập.
- [ ] Artifacts upload dùng always/on-failure semantics.
- [ ] Upload toàn thư mục HTML (assets cùng index.html), không chỉ mỗi index.
- [ ] XML được parse bằng JUnit publisher hoặc XML-aware parser, không concat.
- [ ] Retry/matrix/shard metadata được giữ để không đếm trùng.
- [ ] Không chứa secret/PII trong stdout, stack trace hoặc testcase names.
- [ ] Access permissions và artifact retention tuân policy.
- [ ] Artifact names được phân biệt theo run/job/matrix nếu cần.
- [ ] CI xác minh báo cáo hiện hữu, log rõ trường hợp evidence unavailable.
- [ ] Build Wrapper/JDK versions phù hợp và có thể truy vết.
- [ ] JaCoCo coverage (nếu có) được báo cáo riêng, không trộn với JUnit outcomes.
- [ ] Test report paths và task reports được kiểm chứng trên chính Gradle Wrapper của dự án.

## 24. Tài liệu chính thức

- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — The Test Report Aggregation Plugin](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html)
- [Gradle — Test Task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [Gradle — TestReport Task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.TestReport.html)
- [Gradle — The JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html)
- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html)
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [GitHub Actions — Upload Artifacts](https://github.com/actions/upload-artifact)
- [GitLab — Unit Test Reports](https://docs.gitlab.com/ci/testing/unit_test_reports/)
- [Jenkins — JUnit Plugin](https://plugins.jenkins.io/junit/)

**Kết luận:** Một pipeline Gradle đáng tin cần cả **kết quả test thực**, **HTML để con người điều tra**, **JUnit XML để CI phân tích**, **aggregation đúng từ binary test results**, và **artifact storage chạy cả khi tests fail**. Dùng Gradle **TestReport/test-report-aggregation** cùng **--continue**, lưu per-module reports bằng **always**, giữ nguyên exit code thất bại và kiểm soát dữ liệu nhạy cảm. Như vậy kết quả kiểm thử có thể truy vết, debug và mở rộng cho nhiều module hoặc CI jobs mà không đánh đổi tính đúng đắn của quality gate.
