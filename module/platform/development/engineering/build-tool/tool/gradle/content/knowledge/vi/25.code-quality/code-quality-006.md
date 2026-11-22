# Tổng hợp coverage nhiều module và giới hạn của số phần trăm trong Gradle

## Mục tiêu bài học

Trong một ứng dụng Java nhiều module, báo cáo JaCoCo ở từng project chưa đủ để trả lời câu hỏi “toàn hệ thống đã được kiểm thử tới đâu?”. Mỗi module có kích thước khác nhau, một test có thể thực thi bytecode từ module phụ thuộc, và nhiều nhóm unit/integration tests không nhất thiết được đưa vào cùng một báo cáo. Nếu chỉ lấy trung bình cộng những phần trăm coverage đang nhìn thấy, bạn có thể công bố con số sai.

Gradle hỗ trợ **JaCoCo** và plugin **jacoco-report-aggregation** để tổng hợp dữ liệu coverage theo project dependencies và tên JVM Test Suite. Nhưng **code coverage chỉ đo phần mã được thực thi**, không trực tiếp đo correctness, chất lượng assertions, khả năng chịu tải, an toàn bảo mật hoặc mức độ bao phủ yêu cầu nghiệp vụ.

Bài này giúp bạn:

1. Phân biệt **execution data**, **JaCoCo report**, **test results**, **aggregate report** và **coverage verification task**.
2. Đọc các counters **LINE, BRANCH, INSTRUCTION, METHOD, CLASS, COMPLEXITY** và hiểu mẫu số của mỗi tỷ lệ.
3. Tính coverage toàn bộ bằng tổng covered/missed, không lấy trung bình module percentages.
4. Bật plugin **jacoco** trong các Java subprojects, tạo HTML/XML báo cáo riêng.
5. Dùng **jacoco-report-aggregation** trong một project độc lập để gom coverage từ các modules.
6. Hiểu cách Gradle chọn result variants theo **testSuiteName**, và vì sao unit/integration suites không tự trộn vào một báo cáo.
7. Tạo lab Java 17 chạy bằng Gradle gồm **:core**, **:service** và **:coverage**, sử dụng JUnit Jupiter.
8. Áp **jacocoTestCoverageVerification** khi muốn kiểm tra ngưỡng, không nhầm ngưỡng từng module với ngưỡng aggregate.
9. Phát hiện coverage report thiếu module, thiếu test, chứa dữ liệu cũ hoặc thay đổi exclusions.
10. Đánh giá coverage cùng test pass/fail, branch cases, risk-based testing, static analysis và mutation testing.

Ví dụ sử dụng **Groovy DSL**, có phần Kotlin DSL. Cần Gradle Wrapper và JDK 17 tương thích; JUnit và JaCoCo dependencies cần Maven Central/mirror/cache phù hợp. Một số API JVM Test Suite và aggregation vẫn được tài liệu Gradle đánh dấu **incubating**, nên phải xem hướng dẫn đúng phiên bản Gradle Wrapper đang dùng.

## 1. Coverage thực sự là gì?

JaCoCo agent theo dõi probes khi code Java được thực thi trong JVM. Sau khi Test task chạy, Gradle có thể có một file nhị phân như:

~~~text
core/build/jacoco/test.exec
~~~

File **.exec** chứa dữ liệu thực thi, **không phải** report HTML hoặc file có thể lấy ngay tỷ lệ từ cách đếm bytes. Để làm report, JaCoCo phân tích **execution data** cùng compiled class files và khi có thể source files tương ứng.

~~~text
Java classes + JUnit test
           |
           v
Gradle Test task chạy JaCoCo agent
           |
           v
build/jacoco/test.exec
           |
           +----- class files/source files
           |                 |
           v                 v
              JacocoReport
                   |
             HTML / XML / CSV
                   |
             người đọc / CI
~~~

Một module có nhiều Test tasks có thể sinh nhiều file execution data. Mỗi file phản ánh những JVM/test tasks đã được instrument. Nếu chương trình được gọi bằng JavaExec/process ngoài không instrument, JaCoCo của Test task có thể không ghi được code ở quá trình ấy.

### 1.1. Coverage khác test pass rate

**100% tests passed**: toàn bộ tests đã được runner phát hiện và thực thi không có lỗi assertion/failure theo chính sách.

**100% line coverage**: JaCoCo thấy các dòng mã có thể đo trong **phạm vi báo cáo** được thực thi ít nhất một lần.

Không suy ra 100% coverage từ 100% tests passed. Ngược lại, một số tests thất bại vẫn có thể tạo dữ liệu execution coverage rất cao vì code đã chạy trước khi assertions fail. **Coverage cao không được dùng để cho phép release khi tests đang fail.**

### 1.2. Tên metric và scope phải đi cùng nhau

Câu “coverage đạt 85%” là thiếu thông tin. Cần nói rõ:

- **LINE** hay **BRANCH**?
- Scope gồm **:core + :service** hay một project?
- Suite nào: **test**, **integrationTest**, hay dữ liệu gộp?
- Commit, JDK, Gradle/JaCoCo version?
- Generated code hoặc những classes nào bị exclude?
- Test process thực sự chạy hay task NO-SOURCE/SKIPPED?

Không có các thông tin này, hai con số 85% ở hai CI jobs chưa chắc có thể so sánh.

## 2. Các counters JaCoCo

| Counter | Nội dung đo | Giới hạn khi diễn giải |
| --- | --- | --- |
| **INSTRUCTION (C0)** | Bytecode instructions đã chạy | Không đồng nghĩa số dòng hay tính đúng |
| **LINE** | Dòng source có ít nhất một instruction được thực thi | Một dòng có nhiều nhánh vẫn được đánh dấu covered |
| **BRANCH (C1)** | Các nhánh của if và switch | Không đo tất cả tổ hợp điều kiện hoặc exception paths |
| **METHOD** | Method có ít nhất một instruction được chạy | Không bảo đảm mọi trường hợp được thử |
| **CLASS** | Class có method được chạy | Không đo chất lượng test lớp ấy |
| **COMPLEXITY** | Cyclomatic complexity và phần missed/covered | Gợi ý đường đi khó, không phải correctness score |

### 2.1. LINE không tương đương BRANCH

~~~java
public int fee(boolean express) {
    return express ? 30 : 10;
}
~~~

Nếu tests chỉ gọi **fee(true)**, dòng chứa return đã được thực thi, nhưng nhánh trả 10 chưa được thử. Vì vậy một dòng có thể covered trong LINE report mà BRANCH report vẫn chỉ có một phần coverage.

### 2.2. Branch coverage cũng chưa đo hết

JaCoCo tính branches của if/switch. Theo JaCoCo Coverage Counter docs, **exception handling không được tính là branch** trong định nghĩa của metric ấy. Vì vậy một method có if/else và throw/catch cần tests về lỗi độc lập, không suy luận branch 100% nghĩa là exception scenarios hoàn hảo.

Hai boolean độc lập có bốn tổ hợp. Một số tests có thể đi qua true/false của từng boolean mà vẫn không thử một số tổ hợp tương tác. Với business rule rủi ro cao, dùng decision table, boundary/property-based tests và security negative cases.

### 2.3. METHOD/CLASS không phải số ca test

Một class có constructor được chạy có thể được tính class coverage dù các methods quan trọng chưa được gọi. Một method được gọi ít nhất một lần có thể được tính method covered dù thiếu nhiều branches.

Các counters dựa trên bytecode, nên compiler-generated methods, lambdas, records hoặc bytecode transformations có thể tác động tỷ lệ. Khi nâng Java/JaCoCo version, so sánh source code, class files và counter definitions trước khi kết luận tests tốt/xấu hơn.

### 2.4. Công thức đúng

Nếu cùng một counter type, **C=covered**, **M=missed**:

~~~text
total = C + M
ratio = C / total               (với total > 0)
percent = ratio * 100
~~~

Với **total=0**, tỷ lệ không xác định theo công thức này; không tự nhận 100%. Đọc giá trị API/report thực tế và hiểu vì sao module/scope không có code đo được.

## 3. Tổng hợp nhiều module phải có trọng số

Lỗi phân tích: lấy **(coverageA + coverageB)/2** trong khi hai modules có số dòng khác nhau.

### 3.1. Ví dụ đơn giản

| Module | Covered LINE | Missed LINE | LINE % |
| --- | ---: | ---: | ---: |
| core | 10 | 0 | 100% |
| service | 0 | 90 | 0% |
| Tổng | 10 | 90 | 10% |

Trung bình cộng module-level scores là **50%**, nhưng coverage của **100 dòng** được đo là **10%**.

~~~text
Unweighted module average = (100% + 0%) / 2 = 50%
Real aggregate LINE = 10 / (10 + 90) * 100 = 10%
~~~

### 3.2. Công thức cho N module

~~~text
coveredTotal = sum(covered_i)
missedTotal = sum(missed_i)
aggregatePercent =
    100 * coveredTotal / (coveredTotal + missedTotal)
~~~

Đây là công thức cho **cùng counter type**, các modules không bị đếm trùng và có cùng cách chọn scope. Nếu một XML report có counters ở report/package/class/method, **không cộng cả bốn tầng** vì chúng mô tả một số bytecode ở nhiều cấp khác nhau.

### 3.3. Chương trình Java 17 kiểm chứng toán học

Tạo **CoverageMath.java**:

~~~java
import java.util.List;
import java.util.Locale;

public final class CoverageMath {
    record Module(String name, long covered, long missed) {
        double percent() {
            long total = covered + missed;
            return total == 0 ? Double.NaN
                    : covered * 100.0 / total;
        }
    }

    public static void main(String[] args) {
        List<Module> modules = List.of(
                new Module("core", 10, 0),
                new Module("service", 0, 90)
        );

        long covered = 0;
        long missed = 0;
        double sumPercent = 0.0;

        for (Module module : modules) {
            System.out.printf(
                    Locale.ROOT, "%s: %.2f%%%n",
                    module.name(), module.percent()
            );
            covered += module.covered();
            missed += module.missed();
            sumPercent += module.percent();
        }

        System.out.printf(
                Locale.ROOT,
                "Average: %.2f%%%n", sumPercent / modules.size()
        );
        System.out.printf(
                Locale.ROOT,
                "Aggregate: %.2f%%%n",
                covered * 100.0 / (covered + missed)
        );
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CoverageMath.java
java CoverageMath
~~~

Stdout chính xác:

~~~text
core: 100.00%
service: 0.00%
Average: 50.00%
Aggregate: 10.00%
~~~

Đây chỉ là chương trình độc lập tính trên **số liệu giả định**, không phân tích JaCoCo XML. Nó chứng minh vì sao không thể lấy trung bình cộng phần trăm các module để báo coverage toàn codebase.

### 3.4. Trung bình có trọng số cũng chưa là quality score

Một module lớn gồm DTO/getters dễ cover có thể làm tổng 90%, trong khi một module nhỏ về quyền truy cập chỉ có 10% branch coverage. Tổng thể có vẻ đẹp nhưng risk không được kiểm soát.

Cần drill down **module/package/class** và xem code rủi ro cao, không chỉ số ở đầu dashboard.

## 4. Bật JaCoCo trong một Java module

Dùng plugin core:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}
~~~

Khi áp cùng Java plugin, Gradle tạo các tasks **jacocoTestReport** và **jacocoTestCoverageVerification**, và Test tasks được instrument JaCoCo theo conventions.

### 4.1. Tạo HTML/XML

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}
~~~

Nếu có JUnit Jupiter, vẫn cần dependencies framework/launcher trong build. Cấu hình **useJUnitPlatform()** chỉ chọn test runner.

### 4.2. jacocoTestReport không tự chạy test

Tài liệu Gradle chỉ rõ task **jacocoTestReport không có dependsOn test mặc định**. Nếu muốn chạy report là phải có dữ liệu test, khai báo **dependsOn** như trên.

Ngoài ra có thể dùng:

~~~groovy
tasks.named('test') {
    finalizedBy tasks.named('jacocoTestReport')
}
~~~

**finalizedBy** là mối quan hệ finalizer; tùy ngữ cảnh Gradle tiếp tục tạo report khi test task được thực thi. Nó không thay việc đảm bảo test suite thực sự chạy trong CI.

### 4.3. Output mặc định

Đường dẫn thường gặp:

~~~text
build/jacoco/test.exec
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
~~~

XML chỉ có nếu bật theo report configuration. Tên/thư mục có thể khác ở Gradle version hoặc khi tổ chức đã đổi reportsDirectory; dùng task outputs để cấu hình CI thay vì copy cứng đường dẫn không kiểm tra.

## 5. Cơ chế jacoco-report-aggregation

Plugin **jacoco-report-aggregation** thu JaCoCo execution data từ các project dependencies theo **variant-aware resolution**, sau đó dựng report chung cho những class files/sources tương ứng.

### 5.1. Ai áp plugin nào?

Một mô hình học tập:

~~~text
gradle-coverage-lab
├── :core        java-library + jacoco
├── :service     java-library + jacoco
└── :coverage    base + jacoco-report-aggregation
~~~

Các Java modules sản sinh test execution data. Utility project **:coverage** không cần có code Java; nó chỉ chịu trách nhiệm thu thập và công bố report tổng hợp.

### 5.2. Automatic report và manual report

Gradle có hai cách:

- **Project có JVM Test Suite + jacoco-report-aggregation**: plugin có thể tự tạo reporting objects cho suite names, ví dụ **testCodeCoverageReport**.
- **Standalone utility project chỉ áp base + jacoco-report-aggregation**: phải tự khai báo report object loại **JacocoCoverageReport** với **testSuiteName = 'test'**, và cấu hình **jacocoAggregation** project dependencies.

Không chỉ áp plugin vào root rồi kỳ vọng mọi module tự xuất hiện. Aggregation lấy các direct/transitive project dependencies phù hợp; kiểm tra xem graph có chứa đủ các modules mình muốn tổng hợp hay không.

### 5.3. Matching theo test suite name

Khi chọn dữ liệu từ các projects, Gradle dùng attributes cho các variants:

~~~text
org.gradle.category         = verification
org.gradle.testsuite.name   = test
org.gradle.verificationtype = jacoco-results
~~~

Nó không chọn nhầm JAR production chỉ vì module có dependency edge. Nếu report có **testSuiteName='test'**, một suite riêng tên **integrationTest** không tự được đưa vào report đó.

### 5.4. Plugin aggregation chưa tự là coverage gate

**jacoco-report-aggregation** tạo **JacocoReport** backing task và báo cáo; nó không tự tạo ngưỡng như LINE>=80% áp cho toàn dự án. Quality gate cần một chính sách/test task riêng. Việc báo cáo tạo ra thành công không bảo đảm coverage cao.

### 5.5. JaCoCo aggregation khác Test Report Aggregation

- **jacoco**: instrument Java tests và tạo execution data/report mỗi module.
- **jacoco-report-aggregation**: tổng hợp độ phủ code.
- **test-report-aggregation**: tổng hợp kết quả tests pass/fail, test count và báo cáo kiểm thử.
- **jvm-test-suite**: mô hình sources, framework, dependencies và test targets.

Không coi **100 tests passed** trong aggregated test report là **100% lines covered** trong JaCoCo.

## 6. Lab Java 17 multi-module hoàn chỉnh

Lab gồm module **:core** tính giá, module **:service** sử dụng core và một project **:coverage** tạo báo cáo. Các tests cố ý không cover tất cả branches để report có giá trị đọc hiểu.

### 6.1. Cây thư mục

~~~text
gradle-coverage-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/java/lab/core/PriceCalculator.java
│       └── test/java/lab/core/PriceCalculatorTest.java
├── service/
│   ├── build.gradle
│   └── src/
│       ├── main/java/lab/service/Checkout.java
│       └── test/java/lab/service/CheckoutTest.java
└── coverage/
    └── build.gradle
~~~

Lấy **Gradle Wrapper** do Gradle tạo hoặc từ project tin cậy, không tự chế gradle-wrapper.jar. Cần Gradle tương thích JDK17 và API aggregation đang được dùng; JUnit Jupiter/JaCoCo dependencies cần Maven Central hoặc internal mirror/cache.

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-coverage-lab'

include 'core', 'service', 'coverage'
~~~

### 6.3. build.gradle root

~~~groovy
plugins {
    id 'base'
}
~~~

Root không tự apply jacoco cho mọi nơi; mỗi subproject tự sở hữu plugin và dependencies phù hợp.

### 6.4. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'jacoco'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

jacoco {
    toolVersion = '0.8.15'
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        html.required = true
        xml.required = true
    }
}
~~~

**toolVersion=0.8.15** là version được tài liệu Gradle hiện đại sử dụng làm ví dụ; project thật nên theo policy của tổ chức và tính tương thích JDK/Gradle. JUnit BOM tránh lệch versions trong JUnit components.

### 6.5. core/src/main/java/lab/core/PriceCalculator.java

~~~java
package lab.core;

public final class PriceCalculator {
    public int finalPrice(int cents, boolean loyalCustomer) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative price");
        }
        return loyalCustomer ? cents - cents / 10 : cents;
    }
}
~~~

Các cases cần nghĩ tới: khách hàng trung thành, khách thường, số âm. Lab ban đầu chỉ test hai trường hợp đầu, để lại negative path cho bài tập.

### 6.6. core/src/test/java/lab/core/PriceCalculatorTest.java

~~~java
package lab.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public final class PriceCalculatorTest {
    @Test
    void loyalCustomerGetsDiscount() {
        assertEquals(
                90,
                new PriceCalculator().finalPrice(100, true)
        );
    }

    @Test
    void regularCustomerPaysFullPrice() {
        assertEquals(
                100,
                new PriceCalculator().finalPrice(100, false)
        );
    }
}
~~~

Assertions có kết quả đúng và cụ thể; không viết tests chỉ gọi method rồi bỏ qua output.

### 6.7. service/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'jacoco'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

jacoco {
    toolVersion = '0.8.15'
}

dependencies {
    implementation project(':core')

    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        html.required = true
        xml.required = true
    }
}
~~~

**implementation project(':core')** cung cấp compiled library code của core cho service. JaCoCo Test agent của service có thể thấy các probes ở code được nó thực thi, nhưng local service JacocoReport thường chỉ khai báo sourceSets.main của service; vì vậy cần aggregate report để đọc rộng hơn.

### 6.8. service/src/main/java/lab/service/Checkout.java

~~~java
package lab.service;

import lab.core.PriceCalculator;

public final class Checkout {
    public int total(
            int cents, boolean loyalCustomer,
            boolean expressDelivery
    ) {
        int discounted = new PriceCalculator()
                .finalPrice(cents, loyalCustomer);

        if (expressDelivery) {
            return discounted + 30;
        }
        return discounted + 10;
    }
}
~~~

### 6.9. service/src/test/java/lab/service/CheckoutTest.java

~~~java
package lab.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public final class CheckoutTest {
    @Test
    void loyalCustomerNormalDelivery() {
        assertEquals(
                100,
                new Checkout().total(100, true, false)
        );
    }
}
~~~

Giải thích: 100 giảm 10% còn 90; normal delivery cộng 10 thành **100**. Chưa có test expressDelivery=true; hãy quan sát missed branches của Checkout trong JaCoCo.

### 6.10. coverage/build.gradle

~~~groovy
plugins {
    id 'base'
    id 'jacoco-report-aggregation'
}

repositories {
    mavenCentral()
}

dependencies {
    jacocoAggregation project(':core')
    jacocoAggregation project(':service')
}

reporting {
    reports {
        testCodeCoverageReport(JacocoCoverageReport) {
            testSuiteName = 'test'
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('testCodeCoverageReport')
}
~~~

Đây là cấu hình utility aggregator đúng cho Gradle hiện đại:

- **jacocoAggregation** ghi rõ hai modules muốn thu coverage.
- **testSuiteName='test'** lấy dữ liệu từ suite test tương ứng của hai Java projects.
- **testCodeCoverageReport** là report task được plugin tạo từ report object.
- **:coverage:check** sẽ chạy report vì ta đã nối task dependency.
- Không cần tạo Java classes trong project coverage.

**Lưu ý phiên bản:** các ví dụ Gradle cũ dùng thuộc tính **testType**; API mới dùng **testSuiteName**. Không sao chép hai cú pháp vào cùng script. JVM Test Suite và aggregation plugin còn có API incubating, nên chạy theo Gradle Wrapper đã chọn và kiểm tra docs của version đó.

### 6.11. Chạy báo cáo từng module

Linux/macOS:

~~~bash
./gradlew :core:test :core:jacocoTestReport
./gradlew :service:test :service:jacocoTestReport
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :core:test :core:jacocoTestReport
.\gradlew.bat :service:test :service:jacocoTestReport
~~~

Thư mục HTML thông thường:

~~~text
core/build/reports/jacoco/test/html/index.html
service/build/reports/jacoco/test/html/index.html
~~~

XML report của mỗi module được bật trong build.gradle. Nếu đường dẫn thực tế khác, đọc task outputs hoặc cấu hình reportsDirectory.

### 6.12. Chạy báo cáo aggregate

Linux/macOS:

~~~bash
./gradlew :coverage:testCodeCoverageReport
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :coverage:testCodeCoverageReport
~~~

Gradle thu matching JaCoCo result variants từ các project dependencies, dựng một report cho suite **test**, thường ở:

~~~text
coverage/build/reports/jacoco/testCodeCoverageReport/
├── html/index.html
└── testCodeCoverageReport.xml
~~~

**Kiểm tra artifact path do Gradle thực sự ghi** vì reporting directory có thể được cấu hình lại hoặc đổi theo phiên bản. Không đưa ra tỷ lệ % cố định cho lab trước khi chạy: counters phụ thuộc compiled bytecode, class/source scope và JaCoCo/JDK version.

### 6.13. Chạy lifecycle

~~~bash
./gradlew :coverage:check
~~~

Vì **:coverage:check dependsOn testCodeCoverageReport**, lệnh này tạo aggregate report. Nó **không tự fail** vì LINE hoặc BRANCH thấp; muốn threshold phải thêm coverage verification policy riêng.

Nếu muốn kiểm tra tasks nào sẽ chạy:

~~~bash
./gradlew :coverage:testCodeCoverageReport --dry-run
~~~

**--dry-run không thực thi tests**, chỉ preview graph. Đừng dùng nó làm chứng cứ report tồn tại hoặc tests pass.

### 6.14. Thu report khi test thất bại

~~~bash
./gradlew :coverage:testCodeCoverageReport --continue
~~~

Theo Gradle docs, **--continue** cho phép tiếp tục các tasks độc lập khi có failure để thu thêm báo cáo. Điều này không bảo đảm mọi artifact tồn tại nếu một test không chạy được; build cuối cùng vẫn phải được coi là failed khi tests fail.

**Không sử dụng ignoreFailures=true để biến test failure thành pipeline xanh chỉ vì cần đọc coverage.**

### 6.15. Bật CSV nếu CI cần

Tùy chọn bổ sung trong coverage/build.gradle:

~~~groovy
tasks.named('testCodeCoverageReport', JacocoReport) {
    reports {
        html.required = true
        xml.required = true
        csv.required = true
    }
}
~~~

Default của aggregate report trên Gradle hiện đại có HTML/XML; cấu hình này bật thêm CSV. Khi một dashboard muốn đọc percentages, nên ưu tiên dữ liệu **covered/missed counters** từ XML/CSV thích hợp thay vì parse HTML hoặc trung bình các tỷ lệ hiển thị.

## 7. Những giới hạn khi aggregation nhiều suites

### 7.1. Aggregation theo tên suite, không theo tất cả tasks

Giả sử một module dùng JVM Test Suite:

~~~groovy
testing {
    suites {
        test {
            useJUnitJupiter('5.11.4')
        }
        integrationTest(JvmTestSuite) {
            useJUnitJupiter('5.11.4')
            dependencies {
                implementation project()
            }
        }
    }
}
~~~

Đây là **fragment trong Java project**, chưa là build.gradle hoàn chỉnh. Nếu aggregator chỉ cấu hình testSuiteName='test', coverage từ **integrationTest** không được tự merge vào report test. Để có report riêng cho integrationTest, trong project aggregator khai báo thêm:

~~~groovy
reporting {
    reports {
        integrationTestCodeCoverageReport(JacocoCoverageReport) {
            testSuiteName = 'integrationTest'
        }
    }
}
~~~

Điều kiện: những producers phải có suite/result variants mang tên integrationTest và được JaCoCo instrument. Nếu chỉ có một Test task thủ công không nằm trong JVM Test Suite variants, aggregate plugin có thể không lấy được dữ liệu như mong muốn.

### 7.2. Hai reports không đồng nghĩa merged report

**testCodeCoverageReport** và **integrationTestCodeCoverageReport** là **hai reports**. Không lấy trung bình LINE % của hai reports rồi xem là combined coverage; cùng class có thể được instrument cả hai, và denominator giữa reports có thể trùng.

Muốn gộp thật cần một JacocoReport dùng đúng **class files + source files + execution data từ cả hai test tasks**, tránh double count. Có thể thiết lập custom report trong mỗi project rồi cân nhắc cơ chế cross-project tương ứng.

### 7.3. Gộp nhiều Test tasks của một Java project

Gradle JaCoCo docs hiện hành nêu mẫu:

~~~groovy
def testTasks = tasks.withType(Test)
def allExecutionData = files()

testTasks.configureEach {
    def ext = extensions.getByType(JacocoTaskExtension)
    allExecutionData.from(provider { ext.destinationFile })
}

tasks.register('allSuitesCoverageReport', JacocoReport) {
    dependsOn testTasks
    executionData allExecutionData
    sourceSets sourceSets.main

    reports {
        html.required = true
        xml.required = true
    }
}
~~~

Đây là **fragment cho một Java project áp jacoco**, cần các Test tasks thực sự tồn tại. Không truyền trực tiếp **executionData(testTasks)** trong **tasks.register** nếu API/Gradle mutation guard từ chối; sử dụng FileCollection được góp dữ liệu bởi **configureEach** và **Provider** theo mẫu tài liệu.

**executionData không tự tạo task execution dependency**. **dependsOn testTasks** mới khiến các tests trong scope được chạy trước report.

### 7.4. Nhiều targets trong một suite

Một JvmTestSuite có thể có targets chạy Java17 và Java21, chia sẻ cùng sources. Gradle 8.x/9.x đã có thay đổi API và cách xuất result variants cho multi-target. Đừng mặc định mỗi target trở thành một suite name hoặc report độc lập; kiểm tra Gradle Wrapper version và outgoing variants thực tế.

### 7.5. Một test có thể cover module khác

Service test gọi **PriceCalculator** từ :core. Execution data của service process có thể chứa probes của lớp core. Muốn đưa chúng vào report core/aggregate cần class files của core và matching execution data. Local service report không tự hiển thị toàn bộ source của core nếu JacocoReport chỉ dùng sourceSets.main của service.

Đó là lý do phải kiểm tra **module/class list trong report**, không chỉ tổng tỷ lệ.

### 7.6. Nếu thiếu một module, denominator bị co lại

Nếu **:payment** không có trong jacocoAggregation graph hoặc thiếu matching coverage variant, report sẽ không tự tính các lớp của nó thành uncovered. Một dashboard có thể bất ngờ nhảy từ 75% lên 90% **mà không tăng test nào** do thay đổi phạm vi.

Mọi aggregate policy phải đối chiếu danh sách expected modules với danh sách thực sự trong report.

## 8. Đọc XML/HTML đúng tầng

### 8.1. HTML quan sát gì?

Trong JaCoCo HTML, xem:

- Những packages/classes hoàn toàn đỏ hoặc không xuất hiện.
- Các methods có missed complexity lớn.
- Yellow branches: mới chạy một phần điều kiện.
- Những code paths rủi ro cao: authorization, payment, migration, error handling.
- Số counters covered/missed, không chỉ %.
- Sự khác biệt sau một PR: test được thêm hay chỉ exclusion thay đổi?

HTML là công cụ cho reviewer. XML là dữ liệu machine-readable dùng trong CI.

### 8.2. Ví dụ XML counter rút gọn

~~~xml
<report name="example">
    <counter type="INSTRUCTION" missed="9" covered="41"/>
    <counter type="BRANCH" missed="4" covered="6"/>
    <counter type="LINE" missed="10" covered="90"/>
</report>
~~~

Đây là **ví dụ cấu trúc**, không phải XML thật của lab. Nó cho:

- INSTRUCTION = 41/50 = 82%.
- BRANCH = 6/10 = 60%.
- LINE = 90/100 = 90%.

JaCoCo XML thực tế có counters ở **report, package, class, method, sourcefile**. Muốn tỷ lệ tổng, đọc counters tại **report-level** (hoặc dùng API aggregate thích hợp). **Không cộng lẫn các tầng** vì cùng class có thể đã được tính nhiều lần.

### 8.3. Không trộn counter types

Công thức không hợp lệ:

~~~text
(covered LINE của core + covered BRANCH của service)
----------------------------------------------------
(total LINE của core + total BRANCH của service)
~~~

Cần tổng riêng LINE, riêng BRANCH, riêng INSTRUCTION. Khi dùng dashboard, đặt tên **aggregateLineCoverage**, **aggregateBranchCoverage** rõ ràng.

### 8.4. Không trộn execution data với bytecode phiên bản khác

Nếu chạy tests trên commit A nhưng report dùng class files từ commit B, JaCoCo có thể báo class mismatch hoặc bỏ qua probes. CI nên tạo tests và reports từ **cùng commit, cùng compiled outputs, cùng toolchain policy**.

Không ép merge những file .exec từ build khác bằng cách nối bytes. Dùng report tasks và execution data inputs được Gradle model hóa.

## 9. Coverage verification khác report

Java project có JaCoCo plugin sẽ có **jacocoTestCoverageVerification**. Task này kiểm tra threshold rules, và **không tự là dependency của check** theo mặc định.

### 9.1. Rule LINE cho một module

Thêm vào **core/build.gradle** hoặc **service/build.gradle** nếu team muốn gate:

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('test')

    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.70
            }
        }
    }
}
~~~

**0.70 nghĩa là 70%**, không phải 70 lines. Đây là một **policy ví dụ**, không phải ngưỡng được Gradle khuyến nghị chung. Mức nào phù hợp phải do nhóm chọn theo mức độ rủi ro và tính chất module.

### 9.2. Nối vào check nếu thực sự muốn fail pipeline

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

Từ đó **:core:check** hoặc **:service:check** có thể fail nếu không đạt threshold. Việc này **không làm :coverage:testCodeCoverageReport tự kiểm tra aggregate ratio**.

### 9.3. Gate BRANCH cùng LINE

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.70
            }
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.60
            }
        }
    }
}
~~~

Đây là **fragment thay thế** cho rule đơn ở trên, không copy lặp cả hai tùy tiện. Một module không có branch cần được xem xét chính sách riêng; không đặt gate BRANCH cứng nhắc khi metric không meaningful.

### 9.4. Gate cho aggregate cần thiết kế riêng

Plugin aggregation tạo **JacocoReport** backing task; nó **không tự sinh một aggregate JacocoCoverageVerification** với minimum đã chọn. Nếu tổ chức muốn aggregate threshold, có thể:

- Đọc root-level counters của aggregate XML bằng công cụ CI đã được kiểm thử.
- Tạo custom coverage verification task với **executionData và class/source dirs chính xác**.
- Dùng external quality service có scope/counter policy rõ.

Phải đảm bảo **tests fail vẫn fail build** và **báo cáo đủ modules**, nếu không aggregate gate có thể chấp nhận một mẫu số đã bị thu hẹp.

## 10. Giới hạn của phần trăm coverage

### 10.1. Một test không assertion vẫn tăng coverage

~~~java
@Test
void runsWithoutCheckingResult() {
    new PriceCalculator().finalPrice(100, false);
}
~~~

Đoạn này có thể làm dòng/method được thực thi, nhưng không bảo đảm output đúng. **Coverage không đọc ý nghĩa assertions**.

### 10.2. 100% LINE không chứng minh 100% business scenarios

Một method trả về kết quả cho happy path, nhưng không thử negative input, null, boundary, overflow, timeout hoặc unauthorized user. Dù mọi dòng đã chạy, các yêu cầu đó vẫn có thể sai.

### 10.3. 100% BRANCH không chứng minh mọi path

Hai điều kiện độc lập có bốn tổ hợp. Cover mỗi true/false không nhất thiết cover cả bốn. JaCoCo cũng không tính exception handling thành BRANCH. Dùng decision table, combinatorial/property-based testing khi cần.

### 10.4. Module bỏ sót làm % “đẹp giả”

Nếu mã chưa test không được đưa vào aggregate project graph, nó không thuộc mẫu số. Phải kiểm tra expected module list và measured module list ở mỗi lần report.

### 10.5. Generated code và exclusions

Excluding generated DTOs hoặc vendor-generated adapters có thể có lý do tốt, nhưng exclusion mọi controller/security package vì coverage thấp là anti-pattern. Mỗi exclusion làm thay denominator; cần code review và thay đổi scope có version trong Git.

### 10.6. Coverage không đo rủi ro

Một module tràn getters/boilerplate có thể đạt 95%, trong khi validation/security rule chỉ 10%. Nếu dùng một tỷ lệ toàn hệ thống, các lines lớn ít rủi ro có thể “hòa loãng” vùng quan trọng.

Phân loại **critical packages**, dùng branch/negative tests và review độc lập thay vì xem một số % là giấy chứng nhận.

### 10.7. Coverage không đo hiệu năng hoặc concurrency

JaCoCo không thay latency p95/p99, throughput, memory profiling, race-condition testing, performance tests hoặc resilience checks. Nó cũng không phát hiện dependencies có CVE hay security misconfiguration.

### 10.8. Mutation testing bổ sung cho assertions

Mutation testing cố đổi nhỏ code (toán tử, điều kiện, return value) rồi xem tests có phát hiện thay đổi. Một suite có 95% LINE nhưng mutation score thấp có thể thiếu assertions. Mutation score cũng có hạn chế về equivalent mutants và chi phí, nên chỉ dùng bổ sung.

### 10.9. Coverage tăng vì xóa code không có nghĩa tests tốt lên

Một PR xóa nhiều dòng chưa được cover có thể tăng tổng ratio mà không hề bổ sung test. Một PR thêm code mới tốt nhưng chưa kịp thêm test có thể làm tỷ lệ giảm. Reviewer cần đọc **diff + reports**, không chỉ dashboard trend.

### 10.10. Test failures vẫn là failures

JaCoCo ghi probes khi code chạy, bất kể assertion fail sau đó. Do đó một build có test fail vẫn có thể sinh coverage 100%. Pipeline không nên dùng coverage đạt ngưỡng để bỏ qua test failures.

## 11. Nâng chất lượng lab bằng tests có giá trị

Thêm vào **PriceCalculatorTest.java** một import và test:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void rejectsNegativePrice() {
    assertThrows(
            IllegalArgumentException.class,
            () -> new PriceCalculator().finalPrice(-1, true)
    );
}
~~~

Đây là **fragment**, đặt method vào class test đã có; không phải file Java độc lập.

Thêm vào **CheckoutTest.java**:

~~~java
@Test
void expressDeliveryAddsSurcharge() {
    assertEquals(
            120,
            new Checkout().total(100, true, true)
    );
}
~~~

100 giảm 10% thành 90; express +30 thành **120**.

Thêm test regular customer:

~~~java
@Test
void regularNormalDelivery() {
    assertEquals(
            110,
            new Checkout().total(100, false, false)
    );
}
~~~

Chạy lại Gradle tests và aggregate report, quan sát missed branches/lines thay đổi. **Không khẳng định trước số phần trăm**: compiled bytecode, instrumented probes, Java version và class scope quyết định counters thực tế.

Ngay khi thêm ba tests, các trường hợp như integer overflow, rounding cents, không có dữ liệu người dùng, ngoài-range inputs hoặc concurrency vẫn có thể chưa được kiểm thử.

## 12. Debug report thiếu module hoặc sai scope

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không thấy **testCodeCoverageReport** | Aggregator thiếu reporting object hoặc nhầm Gradle API version | Kiểm tra build.gradle, Wrapper và tasks --all |
| Report chỉ chứa :service | Không lấy được :core result variant | Kiểm tra jacocoAggregation và outgoing variants |
| Report có 0% dù tests chạy | Agent không ghi data hoặc source/classes không khớp | Kiểm tra build/jacoco, Test tasks, classfiles |
| **NO-SOURCE** | Sai source root, test classes không được compile | Kiểm tra src/test/java, compileTestJava |
| **SKIPPED** report | Không có execution data hợp lệ | Kiểm tra test task dependencies và file .exec |
| Report thiếu integrationTest | Chỉ chọn suite name test | Tạo report riêng hoặc custom merge |
| Report cao bất thường sau thay excludes | Denominator giảm | So class list, file filters, Git diff |
| local pass CI thiếu data | Test tasks, cache, JDK, repo hoặc Gradle version khác | Chạy cùng Wrapper/CI settings, xem artifacts |
| JaCoCo class mismatch | .exec và classfiles khác build | Tạo report từ cùng commit/outputs |
| XML chưa có | xml.required=false hoặc report chưa chạy | Bật XML và chạy task |
| jacocoTestReport không chạy test | Không có dependsOn mặc định | Thêm dependsOn test |
| Coverage verification không chạy với check | Chưa nối task | Thêm check.dependsOn có chủ đích |
| Aggregate report không fail khi thấp | Report không phải gate | Thiết kế verification riêng |
| No matching coverage variant | Producer chưa có matching JaCoCo/JVM suite variant | Áp plugin đúng và inspect outgoingVariants |
| Test Report Aggregation có dữ liệu nhưng JaCoCo không | Hai loại reports khác | Kiểm tra jacoco agent và coverage plugin |
| Compile Java mới nhưng JaCoCo cũ | JaCoCo agent chưa hỗ trợ bytecode version | Cập nhật toolVersion phù hợp |

### 12.1. Lệnh debug

~~~bash
./gradlew projects
./gradlew :core:tasks --all
./gradlew :service:tasks --all
./gradlew :coverage:tasks --all
./gradlew :core:outgoingVariants
./gradlew :service:outgoingVariants
./gradlew :coverage:dependencies --configuration jacocoAggregation
./gradlew :coverage:testCodeCoverageReport --info
~~~

Kiểm tra: (1) các Test tasks có thật, (2) các producer có variants đúng **test suite name**, (3) aggregator lấy đủ project dependencies, (4) các test execution data files được tạo từ cùng build.

**--dry-run chỉ lập lịch, không chạy tests**; đừng lấy BUILD SUCCESSFUL của dry-run làm bằng chứng quality gate.

## 13. Kotlin DSL cho project aggregator

**coverage/build.gradle.kts** tương đương:

~~~kotlin
plugins {
    base
    id("jacoco-report-aggregation")
}

repositories {
    mavenCentral()
}

dependencies {
    jacocoAggregation(project(":core"))
    jacocoAggregation(project(":service"))
}

reporting {
    reports {
        create<JacocoCoverageReport>("testCodeCoverageReport") {
            testSuiteName = "test"
        }
    }
}

tasks.named("check") {
    dependsOn(tasks.named("testCodeCoverageReport"))
}
~~~

Đoạn Kotlin DSL trên áp dụng cho **:coverage** dùng **base** + aggregation. Java modules vẫn cần **java-library + jacoco** và JUnit dependencies.

Một Java module Kotlin DSL có thể thiết lập report:

~~~kotlin
plugins {
    java
    jacoco
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
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Với module **:service** cần thêm **implementation(project(":core"))** và chọn plugin **java-library** khi cần các variants/library semantics tương ứng. Không copy Kotlin code vào Groovy build.gradle vì syntax khác nhau.

## 14. Thiết kế quality policy cho team

Một tài liệu chính sách coverage nên ghi:
- Danh sách các modules được tính.
- Suite names: unit/integration/functional.
- Metrics và ngưỡng: LINE, BRANCH, critical packages.
- Exclusion rules, generated code, source directories.
- Gradle Wrapper/JaCoCo/JDK versions.
- Cách xử lý failed/no-source/ignored tests.
- Ai duyệt ngoại lệ, cách cập nhật baseline.
- CI reports artifacts và thời gian lưu trữ.

### 14.1. Các tầng chất lượng

| Tầng | Ví dụ yêu cầu | Tại sao |
| --- | --- | --- |
| Test correctness | Tests có assertions và phải pass | Coverage không thay test pass/fail |
| Scope correctness | Đủ modules/suites đã định | Không chấp nhận dashboard thiếu mẫu số |
| Aggregate LINE | Đạt baseline/threshold tổ chức phê duyệt | Theo dõi coverage toàn project |
| Module/critical BRANCH | Mức tối thiểu riêng cho code rủi ro | Ngăn vùng nhỏ bị che bởi module lớn |
| Changed code | Thay đổi hành vi có tests tương ứng | Tập trung chất lượng của PR mới |
| Security/performance | Tests chuyên biệt khi cần | Những đặc tính coverage không đo |

Các con số **70%, 80%, 90%** chỉ là ví dụ. Không có ngưỡng một size phù hợp mọi project. Mục tiêu là **số liệu chân thực + quyết định dựa trên rủi ro**, không khiến developers viết tests vô nghĩa để tăng điểm.

### 14.2. Code mới phải được review theo hành vi

Thay vì nói “PR phải tăng coverage ít nhất 1%”, xem:
- Ca nào đã thay?
- Đường đi lỗi nào cần regression test?
- Có negative/edge cases không?
- Assertions có kiểm tra output/side effects?
- Integration tests có chạy đúng environment?
- Có source/counter bị loại khỏi report mới không?

Một PR có coverage tổng không đổi vẫn có thể cải thiện chất lượng đáng kể bằng tests cho critical code.

### 14.3. Không đồng nhất coverage và bảo mật

100% coverage với happy path không kiểm tra phân quyền sai, request giả mạo, dữ liệu tấn công hoặc race conditions. Khi review hệ thống nhạy cảm, bổ sung threat-based tests, fuzzing, policy checks, static analysis và dependency verification.

## 15. Bài tập kèm đáp án

### Bài 1 — Trung bình sai

Core 10/10 covered, service 0/90.

**Đáp án:** module average = 50%, aggregate line coverage = 10%.

### Bài 2 — Test pass rate

20 tests đều pass nhưng LINE=40%.

**Đáp án:** pass rate 100% không đồng nghĩa code coverage 100%; có nhiều mã chưa được test thực thi.

### Bài 3 — LINE vs BRANCH

Một dòng if/else chỉ chạy nhánh true.

**Đáp án:** dòng có thể đã covered, branch false vẫn missed; thêm test đúng false path.

### Bài 4 — Task report không tạo data

Chạy jacocoTestReport nhưng test chưa chạy.

**Đáp án:** report không dependsOn test mặc định. Cần chạy test trước hoặc đặt dependsOn/finalizedBy hợp lý.

### Bài 5 — Report thiếu core

**Đáp án:** kiểm tra jacocoAggregation graph, producer jacoco plugin, outgoing variants, suite name và execution data.

### Bài 6 — Cần gộp unit và integration?

**Đáp án:** JaCoCo aggregation theo suite names, thường tạo reports riêng. Gộp thực sự cần custom JacocoReport với execution data/classfiles đúng scope.

### Bài 7 — Một suite có nhiều targets?

**Đáp án:** các targets có thể chia sẻ sources và tạo Test tasks khác nhau. Đọc Gradle version để hiểu cách variants được tổng hợp; không tự coi mỗi target là một suite khác tên.

### Bài 8 — Báo cáo tăng từ 70% lên 90% nhưng không thêm test

**Đáp án:** kiểm tra exclusions, modules bị bỏ khỏi graph, source/class directories và tool versions trước khi kết luận tích cực.

### Bài 9 — Coverage Verification và check

**Đáp án:** jacocoTestCoverageVerification không được check gọi mặc định; nếu policy muốn gate phải nối task bằng dependsOn.

### Bài 10 — Một module pass 80%, có phải cả repo 80%?

**Đáp án:** không. Task verification scope module không tự kiểm tra aggregate ratio.

### Bài 11 — 100% BRANCH có kiểm tra tất cả exceptions?

**Đáp án:** không. JaCoCo định nghĩa branch cho if/switch, không tính exception handling thành branches.

### Bài 12 — Report XML có counters ở package và root

**Đáp án:** dùng root-level counters cho tổng; không cộng lại các counters của các tầng nested.

### Bài 13 — Test chỉ gọi method, không assert

**Đáp án:** coverage có thể tăng mà không phát hiện output sai. Thêm assertions/negative tests.

### Bài 14 — Lock data ở commit A, classfiles từ commit B

**Đáp án:** .exec và bytecode identity có thể không tương thích; tạo tests và reports từ cùng compiled outputs/commit.

### Bài 15 — Code security đã chạy happy path

**Đáp án:** cần unauthorized/boundary/negative cases và review domain. Coverage không là bằng chứng policy đúng.

### Bài 16 — Build test fail nhưng coverage cao

**Đáp án:** build vẫn thất bại. Không dùng coverage để vượt qua test failures.

### Bài 17 — Test ở service gọi core

**Đáp án:** execution probes có thể cover core, nhưng report cần core classes/source và aggregate setup đúng; service local report không tự là report tất cả project code.

### Bài 18 — Khi nào chọn custom aggregation?

**Đáp án:** khi cần merge nhiều suites/processes hoặc các projects không xuất đúng coverage variants. Cần tests cho aggregator logic và tránh double counting.

## 16. Checklist trước khi công bố coverage

- [ ] Đã xác nhận mọi module cần đo đều có trong aggregate graph?
- [ ] Các Test tasks đã chạy, không NO-SOURCE/SKIPPED ngoài dự kiến?
- [ ] Các producers có JaCoCo execution data/result variants?
- [ ] Report chọn đúng testSuiteName và đủ suite names?
- [ ] Không nhầm JUnit Test Report với JaCoCo Coverage Report?
- [ ] Không lấy trung bình phần trăm các module khác mẫu số?
- [ ] Báo rõ LINE/BRANCH/INSTRUCTION metric đang nói tới?
- [ ] XML counters được đọc ở đúng tầng, không double count?
- [ ] Execution data cùng version compiled class files?
- [ ] Generated-code exclusions có lý do và được review?
- [ ] Các packages rủi ro cao được xem riêng, không bị hòa loãng?
- [ ] Test assertions và negative/boundary cases đủ ý nghĩa?
- [ ] CI vẫn fail khi test fail?
- [ ] jacocoTestReport nối Test task khi cần sinh report?
- [ ] Coverage threshold được khai báo bằng verification task/gate riêng?
- [ ] Không nhầm aggregate report với aggregate quality gate?
- [ ] JaCoCo/Gradle/JDK versions có tương thích và được ghi nhận?
- [ ] HTML/XML artifacts được CI lưu trữ đúng phạm vi?
- [ ] Baseline/quality policy có owner, kỳ đánh giá lại và ngưỡng hợp lý?

## Tài liệu tham khảo chính thức

- [Gradle — The JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): Test agents, JacocoReport, verification rules, multiple suites và outgoing variants.
- [Gradle — JaCoCo Report Aggregation](https://docs.gradle.org/current/userguide/jacoco_report_aggregation_plugin.html): jacocoAggregation, report objects, testSuiteName, manual/automatic aggregation.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): suite names, targets, JUnit framework và variants.
- [Gradle — Testing Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test task, JUnit runtime và CI reporting.
- [Gradle — Test Report Aggregation](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html): kết quả test pass/fail, khác code coverage.
- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): định nghĩa chính xác LINE, BRANCH, INSTRUCTION, METHOD, CLASS, COMPLEXITY.
- [Gradle — Upgrading within 8.x](https://docs.gradle.org/current/userguide/upgrading_version_8.html): các thay đổi của JVM Test Suite/aggregation APIs.
- [Gradle — Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html): Gradle Wrapper và JDK versions.

**Kết luận:** Multi-module coverage phải dựa trên **tổng các counters của đúng modules, đúng test suites và đúng compiled classes**, không phải trung bình cộng những tỷ lệ đã được hiển thị. Gradle JaCoCo aggregation hỗ trợ việc đó, nhưng mỗi report chỉ nói về **phạm vi được chọn**. Một tỷ lệ cao không đồng nghĩa code đúng hoặc đã test đủ các tình huống quan trọng: hãy kết hợp **coverage, test assertions, branch/negative cases, risk review và quality gate minh bạch**.