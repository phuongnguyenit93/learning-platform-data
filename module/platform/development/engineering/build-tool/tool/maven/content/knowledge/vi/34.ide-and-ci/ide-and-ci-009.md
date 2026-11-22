# Lưu báo cáo Surefire, Failsafe, chất lượng và log chẩn đoán trong Maven IDE/CI

## 1. Mục tiêu: build đỏ vẫn phải còn bằng chứng để sửa lỗi

Trong nhóm **IDE và CI**, một Maven pipeline đáng tin cần làm hai việc cùng lúc:

1. **Đánh giá đúng kết quả**: nếu unit test, integration test hoặc quality gate không đạt thì CI phải báo thất bại, không đổi trạng thái thành xanh vì một lệnh upload/reporting.
2. **Giữ lại bằng chứng chẩn đoán**: báo cáo XML/TXT, coverage, static analysis, stack trace và log đủ thông tin cần thiết phải còn xem được **ngay cả khi bước `mvn verify` thất bại**.

Báo cáo giúp trả lời “test nào fail, vì sao, ở commit nào?”, còn **exit code của Maven** quyết định có nên tiếp tục merge/deploy không. Hai tín hiệu không thay thế nhau.

```text
Source + POM + Java 17
        |
        v
    mvn clean verify
        |
        +-- Surefire ở test
        |      target/surefire-reports/
        |      TEST-*.xml, *.txt
        |
        +-- Failsafe ở integration-test
        |      target/failsafe-reports/
        |      TEST-*.xml, *.txt, failsafe-summary.xml
        |
        +-- Quality plugins
        |      Checkstyle XML, JaCoCo XML/HTML
        |      PMD/SpotBugs reports nếu đã bật
        |
        +-- Maven console / diagnostics
        |      CI job log hoặc file ghi có kiểm soát
        |
        +-- Failsafe verify / quality gates
               SUCCESS hoặc FAILURE
                    |
                    v
          CI lưu reports (always)
          Không che Maven exit code
          Không publish secrets
```

**Không phải cứ thấy `target/surefire-reports` là integration tests đã chạy.** Surefire và Failsafe là hai plugin có mục đích và báo cáo mặc định riêng. Chúng cũng khác JaCoCo (coverage) và Checkstyle/PMD/SpotBugs (static analysis).

Bài học tập trung Maven **3.9.x**, Java **17**, Maven Surefire/Failsafe **3.5.2**, JUnit Jupiter **5.11.4**, JaCoCo **0.8.13** và Checkstyle Plugin **3.6.0**. Những versions được ghim để minh họa, không có nghĩa chúng mới nhất ở mọi thời điểm.

## 2. Surefire, Failsafe, coverage và static analysis khác nhau

| Thành phần | Công dụng | Goal liên quan | Loại kết quả |
| --- | --- | --- | --- |
| Maven Surefire Plugin | Chạy **unit tests** | `surefire:test`, thường ở phase `test` | JUnit-style XML/TXT, test failures |
| Maven Failsafe Plugin | Chạy **integration tests**, rồi kiểm tra chúng | `failsafe:integration-test` và `failsafe:verify` | XML/TXT và summary XML |
| JaCoCo Maven Plugin | Thu thập test coverage và báo cáo | `jacoco:prepare-agent`, `jacoco:report`, tùy chọn `jacoco:check` | XML/HTML/CSV coverage, exec data |
| Maven Checkstyle Plugin | Kiểm tra coding style | `checkstyle:checkstyle` report; `checkstyle:check` gate | XML/site report và violations |
| Maven PMD Plugin | Source/AST checks, code duplication | `pmd:pmd`/`pmd:check`, CPD goals | XML/HTML/text tùy goal |
| SpotBugs Maven Plugin | Tìm bug patterns trên compiled bytecode | `spotbugs:spotbugs`/`spotbugs:check` | XML/HTML tùy config |
| Maven Surefire Report Plugin | Render HTML từ test XML | `surefire-report:report-only`, `failsafe-report-only` | HTML human-readable |

**Có report ≠ đã bật gate.** Một Checkstyle/PMD report có violations vẫn có thể được tạo thành công. Để chặn build cần goal/check policy đúng. Tương tự JaCoCo `report` chỉ tạo kết quả coverage; muốn chặn coverage thấp cần `jacoco:check` với rules/ngưỡng.

### 2.1. Nên chạy Maven tới phase nào?

Rút gọn default lifecycle:

```text
validate -> compile -> test -> package
         -> integration-test -> post-integration-test -> verify
         -> install -> deploy
```

Có nhiều phase khác giữa các mốc trên. Với các plugin được cấu hình trong bài:

- `mvn test`: chạy Surefire; **chưa chạy Failsafe integration tests**.
- `mvn package`: chạy unit tests và đóng JAR; **chưa chạy Failsafe integration tests**.
- `mvn integration-test`: Failsafe có thể chạy tests, nhưng **chưa thực hiện Failsafe verify** và chưa chạy post-integration-test/verify trọn vẹn theo cách khuyến nghị.
- **`mvn verify`**: chạy đủ unit tests, integration tests và bước Failsafe kiểm tra summary; đó là lệnh khuyến nghị.
- `mvn install` hoặc `mvn deploy`: đi qua verify trước khi ghi artifact; phải để required gates thực sự chạy.

**Không dùng `mvn integration-test` làm cổng CI cuối cùng.** Theo tài liệu Apache Failsafe, plugin cố ý trì hoãn build failure của integration tests tới `failsafe:verify` để bước cleanup `post-integration-test` có cơ hội chạy.

## 3. Những tệp báo cáo mặc định phải biết

Các đường dẫn bên dưới tính từ **thư mục module đang build**, khi plugin chưa tùy chỉnh `reportsDirectory` hoặc `outputDirectory`.

| Công cụ | Đường dẫn thường gặp | Điều cần lưu |
| --- | --- | --- |
| Surefire | `target/surefire-reports/TEST-*.xml` | Test suites/cases, failures/errors, timings |
| Surefire | `target/surefire-reports/*.txt` | Tóm tắt lỗi, stack trace |
| Failsafe | `target/failsafe-reports/TEST-*.xml` | Integration test results |
| Failsafe | `target/failsafe-reports/*.txt` | Logs/tóm tắt kết quả integration test |
| Failsafe | `target/failsafe-reports/failsafe-summary.xml` | Summary mà `failsafe:verify` sử dụng |
| Checkstyle | `target/checkstyle-result.xml` | Violations, files/lines/rules khi goal/config tạo XML |
| PMD | `target/pmd.xml` | Violations nếu PMD reporting goal được gọi với XML output |
| SpotBugs | `target/spotbugsXml.xml` | Bug patterns khi cấu hình XML output |
| JaCoCo | `target/jacoco.exec` | Binary coverage execution data, **không phải XML** |
| JaCoCo | `target/site/jacoco/jacoco.xml` | Machine-readable coverage |
| JaCoCo | `target/site/jacoco/index.html` | Human-readable coverage |
| Maven Site | `target/site/` | Site/report HTML, có thể chứa nhiều tệp phụ |
| CI diagnostic log | Chẳng hạn `.ci-diagnostics/maven-verify.log` | Nội dung console được lưu có kiểm soát, không phải default Maven file |

**Điểm cần nhớ:** những paths của PMD, SpotBugs, Checkstyle và JaCoCo là **đường dẫn thông dụng khi plugin/goal đó thực sự chạy và output config tương ứng**. Không giả định một POM chỉ có Surefire/Failsafe sẽ tự có mọi file báo cáo chất lượng.

HTML test report cũng **không được Surefire/Failsafe tạo mặc định chỉ nhờ chạy tests**. Surefire/Failsafe chủ yếu sinh XML/TXT; muốn HTML site có thể dùng Surefire Report Plugin hoặc một CI report renderer.

### 3.1. Tên tệp báo cáo không phải ngẫu nhiên

Ví dụ class:

```java
package dev.course;
class CalculatorTest { /* unit tests */ }
class CalculatorIT { /* integration tests */ }
```

Tên report mặc định thường tương ứng:

```text
target/surefire-reports/TEST-dev.course.CalculatorTest.xml
target/surefire-reports/dev.course.CalculatorTest.txt

target/failsafe-reports/TEST-dev.course.CalculatorIT.xml
target/failsafe-reports/dev.course.CalculatorIT.txt
target/failsafe-reports/failsafe-summary.xml
```

Nếu thay `reportNameSuffix`, suite name hoặc `reportsDirectory`, tên/path có thể thay đổi. Report của một test class **không nhất thiết có mặt** nếu test bị skip, fail trước khi test engine khởi tạo, JVM crash hoặc plugin không thực thi.

### 3.2. Trong multi-module reactor

Với root parent và hai modules:

```text
project/
├── pom.xml
├── core/target/surefire-reports/
├── core/target/failsafe-reports/
├── app/target/surefire-reports/
└── app/target/failsafe-reports/
```

Không mặc định mọi reports nằm dưới một `root/target` duy nhất. CI phải lưu các đường dẫn tương ứng với **từng module** hoặc sử dụng glob rõ ràng như `**/target/surefire-reports/`.

Khi gom reports của nhiều modules, giữ đủ **tên module tương ứng**, tránh vô tình ghi đè hai file có cùng tên class ở hai modules khác nhau.

## 4. Thế nào là báo cáo đầy đủ và có thể điều tra?

Một report có ích khi người đọc trả lời được:

- Maven build thuộc **commit/tag, branch, build ID** nào?
- Maven/JDK/plugins versions nào thực sự chạy?
- Module và test class nào được thực thi?
- Tổng tests, failures, errors, skipped bao nhiêu?
- Lỗi là assertion failure, exception, timeout, JVM crash hay plugin/config/repository error?
- Integration test đã chạy tới **`failsafe:verify`** chưa?
- Có đủ Surefire/Failsafe XML và text files để xem không?
- Quality reports có xuất hiện vì plugin đã chạy không, hay không tạo vì build dừng sớm?
- File report thuộc **cùng lần CI run** hay là leftover từ build trước?
- Có secrets/PII/private URLs trong stdout, reports hoặc logs không?

Khi build đỏ do một test, **bằng chứng tồn tại không đồng nghĩa chính sách PASS**. CI cần giữ cả status **FAIL** lẫn reports để sửa lỗi; không “đổi xanh” vì đã upload được một archive.

## 5. Bài thực hành: Java 17, Surefire, Failsafe, JaCoCo và Checkstyle

Ví dụ bên dưới là **một dự án Maven độc lập**, có 2 unit tests và 2 integration tests. Chúng ta thiết kế hai cờ thử nghiệm an toàn để chủ động làm hỏng một unit test hoặc một integration test mà không sửa source:

- `-Dlab.failUT=true`: một unit test cố ý FAIL, Surefire dừng build ở phase `test`.
- `-Dlab.failIT=true`: unit tests PASS, integration test ghi lỗi; Failsafe `verify` trả BUILD FAILURE, vẫn giữ XML/TXT/summary.

Mặc định cả hai cờ `false`. Không sử dụng network, database thật, private tokens hoặc external services cho ví dụ này.

### 5.1. Cây thư mục

```text
maven-ci-reports-lab/
├── pom.xml
├── checkstyle.xml
├── .gitignore
└── src/
    ├── main/
    │   └── java/dev/course/
    │       ├── Calculator.java
    │       └── App.java
    └── test/
        └── java/dev/course/
            ├── CalculatorTest.java
            └── CalculatorIT.java
```

Điều kiện: Java 17+, Maven 3.9.x tương thích, quyền tải plugins/JUnit nếu cache chưa có. Mọi file dùng UTF-8.

### 5.2. pom.xml hoàn chỉnh

Tạo `maven-ci-reports-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>maven-ci-reports-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <lab.failUT>false</lab.failUT>
        <lab.failIT>false</lab.failIT>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <lab.failUT>${lab.failUT}</lab.failUT>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.13</version>
                <executions>
                    <execution>
                        <id>coverage-prepare</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>checkstyle.xml</configLocation>
                    <failOnViolation>true</failOnViolation>
                    <maxAllowedViolations>0</maxAllowedViolations>
                    <logViolationsToConsole>true</logViolationsToConsole>
                </configuration>
                <executions>
                    <execution>
                        <id>code-style-gate</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <lab.failIT>${lab.failIT}</lab.failIT>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích các lựa chọn kỹ thuật quan trọng:**

1. Surefire mặc định được bound vào `test` cho `packaging=jar`. Test class `*Test.java` được nhận diện theo convention.
2. Failsafe cần **cả hai goals** `integration-test` và `verify`. Failsafe nhận class `*IT.java` theo convention.
3. `lab.failUT` và `lab.failIT` là **cờ giả lập không nhạy cảm**, không phải secrets. POM truyền chúng vào forked JVM để unit tests có thể đọc chính xác.
4. `failIfNoTests=true` giúp phát hiện cấu hình sai khiến không có test nào chạy, thay vì báo xanh giả.
5. JaCoCo `prepare-agent` chạy sớm để thu thập coverage; `report` chạy ở `verify` sau tests.
6. Checkstyle có ruleset tối giản để minh họa quality report/gate mà không ép các convention phức tạp lên mã lab.
7. Trong POM, JaCoCo và Checkstyle đứng **trước** Failsafe. Khi các goals đều bind `verify` và integration test FAIL, chúng có thể tạo báo cáo trước khi `failsafe:verify` báo thất bại. Thứ tự thực tế vẫn phải xác nhận trong Maven log/effective build plan của version đang dùng.
8. Mỗi plugin ghi báo cáo dưới `target/` theo default của nó; không cấu hình đường dẫn lạ để CI dễ thu thập.
9. Version được ghim để tránh bản plugin mới thay đổi output/report semantics ngoài ý muốn.

**Giới hạn:** POM lab mới chỉ bật JaCoCo + Checkstyle, không tự tạo PMD/SpotBugs reports. Mục riêng bên dưới giải thích cách lưu các reports đó khi dự án thật đã cài plugin tương ứng.

### 5.3. checkstyle.xml tối giản

Tạo `maven-ci-reports-lab/checkstyle.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <module name="FileTabCharacter"/>
</module>
```

Rule `FileTabCharacter` phát hiện tab trong Java source; các file Java của lab dùng spaces, nên Checkstyle `check` dự kiến PASS. Đây là **ruleset minh họa**, không phải quality policy đầy đủ cho một codebase sản xuất.

### 5.4. Calculator.java

Tạo `src/main/java/dev/course/Calculator.java`:

```java
package dev.course;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static String format(int number) {
        return "Giá trị: " + number;
    }
}
```

### 5.5. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static String message() {
        return "APP: " + Calculator.format(Calculator.add(3, 4));
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**Dòng stdout chính xác** của chương trình:

```text
APP: Giá trị: 7
```

### 5.6. CalculatorTest.java — unit tests

Tạo `src/test/java/dev/course/CalculatorTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void exposesIntentionalUnitFailureOnlyWhenRequested() {
        boolean fail = Boolean.getBoolean("lab.failUT");
        assertFalse(fail, "Unit-test failure requested for CI lab");
    }
}
```

Surefire sẽ chạy hai tests; mặc định `lab.failUT=false` nên cả hai PASS.

### 5.7. CalculatorIT.java — integration tests

Tạo `src/test/java/dev/course/CalculatorIT.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class CalculatorIT {
    @Test
    void integratesApplicationComponents() {
        assertEquals("APP: Giá trị: 7", App.message());
    }

    @Test
    void exposesIntentionalIntegrationFailureOnlyWhenRequested() {
        boolean fail = Boolean.getBoolean("lab.failIT");
        assertFalse(fail,
                "Integration-test failure requested for CI lab");
    }
}
```

Failsafe nhận diện tên class kết thúc `IT`. Trong ví dụ, test tích hợp nhiều class nội bộ, **không truy cập mạng hay database**; một dự án thật có thể cần Docker/database lifecycle ở pre/post-integration-test, nhưng những phụ thuộc đó không cần thiết để học cách lưu báo cáo.

### 5.8. .gitignore

Tạo `.gitignore`:

```gitignore
target/
.ci-diagnostics/
*.log
```

Reports có thể được giữ trong **CI artifact storage với retention**, nhưng không nên commit `target/` vào Git. `*.log` là gợi ý cho lab; dự án thật cần rà lại patterns để không bỏ sót tệp log fixtures được quản lý trong source.

## 6. Chạy happy path và xác nhận từng loại báo cáo

Trong thư mục `maven-ci-reports-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.course.App
```

Nếu Maven/JDK/dependencies hợp lệ, các dấu hiệu cần thấy:

```text
maven-surefire-plugin:3.5.2:test
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0

maven-failsafe-plugin:3.5.2:integration-test
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0

maven-failsafe-plugin:3.5.2:verify
BUILD SUCCESS
```

**Đây là các dòng đại diện để đối chiếu**, không phải log chính xác toàn bộ (prefix, execution IDs, thứ tự các đoạn log có thể thay đổi). Test count của lab là **2 unit + 2 integration = 4**.

Ứng dụng in chính xác:

```text
APP: Giá trị: 7
```

Trong `target/`, khi các goals đã chạy, cần có:

```text
target/
├── surefire-reports/
│   ├── TEST-dev.course.CalculatorTest.xml
│   └── dev.course.CalculatorTest.txt
├── failsafe-reports/
│   ├── TEST-dev.course.CalculatorIT.xml
│   ├── dev.course.CalculatorIT.txt
│   └── failsafe-summary.xml
├── checkstyle-result.xml
├── jacoco.exec
├── site/
│   └── jacoco/
│       ├── index.html
│       └── jacoco.xml
└── maven-ci-reports-lab-1.0.0-SNAPSHOT.jar
```

Danh sách trên **rút gọn**, vì plugin còn tạo nhiều files khác. Các paths này phụ thuộc cấu hình/plugin versions; xác nhận bằng lệnh liệt kê filesystem thực.

Trên Bash/zsh:

```bash
find target/surefire-reports target/failsafe-reports -type f
find target/site/jacoco -type f
```

Trên Windows PowerShell:

```powershell
Get-ChildItem target\surefire-reports -File
Get-ChildItem target\failsafe-reports -File
Get-ChildItem target\site\jacoco -Recurse -File
```

Không dùng `java -jar target/maven-ci-reports-lab-1.0.0-SNAPSHOT.jar` nếu chưa cấu hình manifest `Main-Class`. POM lab tạo ordinary JAR; chạy `java -cp target/classes dev.course.App` như hướng dẫn.

## 7. Điều gì xảy ra khi unit test thất bại?

Chạy **chỉ trong project lab**:

```bash
mvn -B -ntp -Dlab.failUT=true clean verify
```

Cờ này cố tình làm test `exposesIntentionalUnitFailureOnlyWhenRequested` FAIL. Dự kiến:

1. Java source/test compile thành công.
2. Surefire chạy 2 unit tests, một PASS và một FAIL.
3. XML/TXT dưới `target/surefire-reports/` được tạo.
4. Maven **BUILD FAILURE** ở test phase (Surefire), chưa đến integration-test/verify.
5. Do đó **Failsafe/JaCoCo report ở verify có thể chưa có** trong lần chạy này.

Dấu hiệu rút gọn:

```text
Tests run: 2, Failures: 1, Errors: 0, Skipped: 0
maven-surefire-plugin:3.5.2:test
BUILD FAILURE
```

**Không báo “integration tests PASS” khi Failsafe chưa chạy.** Đó là trạng thái NOT RUN, không phải zero errors. Cũng không dùng một file Failsafe XML từ lần build cũ làm bằng chứng; `clean` đã xóa `target/` trước chạy lại.

Xem:

```bash
cat target/surefire-reports/dev.course.CalculatorTest.txt
```

Hoặc trên PowerShell:

```powershell
Get-Content target\surefire-reports\dev.course.CalculatorTest.txt
```

Đọc trong môi trường riêng nếu report có dữ liệu nội bộ. Không copy nguyên report từ production khi chưa rà secrets.

## 8. Điều gì xảy ra khi integration test thất bại?

Chạy:

```bash
mvn -B -ntp -Dlab.failIT=true clean verify
```

Kỳ vọng:

1. Surefire chạy 2 unit tests và PASS.
2. Maven đóng JAR tại package.
3. Failsafe `integration-test` chạy 2 integration tests, trong đó một FAIL; plugin tạo `TEST-*.xml`/`*.txt` và `failsafe-summary.xml`.
4. Maven tiến tiếp qua các phases tới verify; theo cấu hình và thứ tự plugins, JaCoCo report và Checkstyle check có cơ hội chạy tại verify.
5. Failsafe `verify` đọc summary và trả **BUILD FAILURE** vì integration test lỗi.

Dấu hiệu rút gọn:

```text
Surefire: Tests run: 2, Failures: 0
Failsafe: Tests run: 2, Failures: 1
maven-failsafe-plugin:3.5.2:verify
BUILD FAILURE
```

Cần đặc biệt đọc:

```text
target/failsafe-reports/TEST-dev.course.CalculatorIT.xml
target/failsafe-reports/dev.course.CalculatorIT.txt
target/failsafe-reports/failsafe-summary.xml
```

**Khác với Surefire:** Failsafe được thiết kế để không fail build ngay ở `integration-test`, nhằm cho `post-integration-test`/cleanup được chạy khi cần. Lỗi được đánh giá tại `failsafe:verify`. Nếu CI gọi `mvn integration-test` và dừng ở đó, pipeline có thể xanh giả dù integration test đã FAIL.

### 8.1. Không tắt lỗi bằng maven.test.failure.ignore

Tham số như `-Dmaven.test.failure.ignore=true` có thể làm build không fail theo test result, nhưng **không sửa test**. Một CI bắt buộc tests PASS không nên bật flag này chỉ để tạo đầy đủ reports.

Nếu muốn thu báo cáo khi build thất bại, sử dụng **CI conditional upload**, không làm Maven bỏ qua lỗi. Phân biệt:
- `-DskipTests`: bỏ qua chạy tests, có thể không tạo reports mới.
- `-Dmaven.test.skip=true`: có thể bỏ qua cả compile/testCompile theo plugin behavior.
- `-DskipITs=true`: skip Failsafe integration tests.
- `maven.test.failure.ignore`: không phải giải pháp lưu evidence; là thay đổi ngữ nghĩa build outcome.

### 8.2. Khôi phục happy path

Sau khi thử negative test, chạy lại:

```bash
mvn -B -ntp clean verify
```

POM property mặc định `lab.failUT=false` và `lab.failIT=false` nên 4 tests lại PASS. Không cần sửa source hoặc commit changes.

## 9. XML report chứa thông tin gì?

JUnit-style XML có cấu trúc khái niệm như sau (ví dụ **minh họa**, không phải output nguyên văn Surefire):

```xml
<testsuite name="dev.course.CalculatorTest"
           tests="2" errors="0" failures="1" skipped="0">
    <testcase classname="dev.course.CalculatorTest"
              name="exposesIntentionalUnitFailureOnlyWhenRequested">
        <failure message="Unit-test failure requested for CI lab">
            ... stack trace được tool ghi ...
        </failure>
    </testcase>
</testsuite>
```

Trong XML thực tế còn có attributes, durations, properties, system-out/system-err và các fields khác tùy phiên bản/plugin. **Không coi XML minh họa là schema đầy đủ**.

Thông tin quan trọng khi làm CI parser:

- `tests`: số tests đã được đếm.
- `failures`: assertion failures.
- `errors`: errors/exceptions hoặc sự cố test tùy provider.
- `skipped`: tests không chạy.
- `testcase`: tên test method/class và duration.
- `failure`/`error`: message/stack trace để chẩn đoán.
- `system-out`/`system-err`: output capture, có thể nhạy cảm.

**Đừng chỉ đếm số file XML.** Một suite có thể chứa nhiều testcases; một class có thể chạy parameterized tests. Parsers nên đọc cấu trúc test suite/test case, không suy luận 1 XML = 1 test.

### 9.1. Failsafe summary có vai trò riêng

`failsafe-summary.xml` là trạng thái tổng hợp mà plugin `failsafe:verify` sử dụng. Nó không thay thế các file `TEST-*.xml` chi tiết, và cũng không phải format JUnit XML chuẩn cho mọi CI test-report adapter.

Muốn hiển thị testcases trên CI, ưu tiên nạp `TEST-*.xml`; giữ summary để chẩn đoán và xác nhận cơ chế Failsafe.

## 10. Lưu log Maven mà vẫn giữ exit code thất bại

Một lỗi rất phổ biến trên Bash/CI:

```bash
# Chưa đủ an toàn: pipeline shell có thể trả exit code của tee
mvn clean verify 2>&1 | tee maven.log
```

Nếu không có xử lý pipeline status phù hợp, `tee` chạy thành công có thể khiến shell/CI báo success mặc dù Maven trả non-zero.

### 10.1. Bash/zsh trên Linux/macOS

Trong project lab, lưu log **ngoài `target/`** vì `mvn clean` xóa thư mục target:

```bash
mkdir -p .ci-diagnostics
set -o pipefail
mvn -B -ntp clean verify 2>&1 | tee .ci-diagnostics/maven-verify.log
```

`set -o pipefail` khiến pipeline trả trạng thái thất bại nếu Maven thất bại, thay vì chỉ trả status của `tee`. Trên một script CI nghiêm ngặt có thể thêm `set -e`; cần kiểm tra cách shell điều khiển execution để bước upload reports vẫn chạy thông qua CI condition độc lập.

**Không ghi log vào `target/maven.log` trước khi gọi `mvn clean`**: Maven Clean Plugin có thể xóa chính file/thư mục khi pipeline đang chạy, gây mất hoặc không lưu được log.

Khi chỉ cần lưu log để debug local:

```bash
mvn -B -ntp clean verify > .ci-diagnostics/maven-verify.log 2>&1
```

Lệnh này chỉ chuyển output sang file, không in ra terminal. Phải tạo `.ci-diagnostics` trước. Với CI, lệnh `tee` có pipefail dễ theo dõi hơn vì vừa nhìn thấy console vừa giữ file.

### 10.2. Windows PowerShell

Trong PowerShell, một cách trực tiếp là:

```powershell
New-Item -ItemType Directory -Force .ci-diagnostics |
    Out-Null

mvn -B -ntp clean verify *> .ci-diagnostics\maven-verify.log
$mavenExitCode = $LASTEXITCODE

Write-Host "Maven exit code: $mavenExitCode"
if ($mavenExitCode -ne 0) {
    exit $mavenExitCode
}
```

Ví dụ này dùng PowerShell redirection để giữ output và **bảo toàn Maven exit code**. Hành vi của native process streams và redirection có thể khác giữa Windows PowerShell 5.1 và PowerShell 7; kiểm tra trong môi trường CI cụ thể.

**Lưu ý bảo mật:** file log vừa tạo có thể chứa internal URLs, system properties, stack traces hoặc thông tin nhạy cảm. Đừng tự động upload file raw này ra kho công khai, nhất là khi Maven được chạy với credentials.

## 11. CI: upload báo cáo ngay cả khi Maven FAIL

Ví dụ **GitHub Actions** dùng project lab không có secrets hoặc private repositories. Artifact action được ghim major version để dễ đọc; trên production nên pin commit SHA của action theo chính sách supply-chain.

Tạo `.github/workflows/maven-reports.yml`:

```yaml
name: Maven test and quality reports

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build, test and retain local diagnostic log
        shell: bash
        run: |
          mkdir -p .ci-diagnostics
          set -o pipefail
          mvn -B -ntp clean verify 2>&1 | tee .ci-diagnostics/maven-verify.log

      - name: Upload Maven test and quality reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            target/surefire-reports/
            target/failsafe-reports/
            target/checkstyle-result.xml
            target/site/jacoco/
          if-no-files-found: warn
          retention-days: 7

      # Chỉ dùng raw log artifact trong lab KHÔNG có secret.
      - name: Upload lab-only diagnostic log
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-lab-log-${{ github.run_id }}-${{ github.run_attempt }}
          path: .ci-diagnostics/maven-verify.log
          if-no-files-found: warn
          retention-days: 3
```

**Bốn chi tiết trọng tâm:**

1. **`if: ${{ always() }}`**: bước upload được xét chạy kể cả khi Maven step thất bại; nếu workflow chưa đến bước tạo reports, `if-no-files-found: warn` chỉ cảnh báo thiếu file.
2. **`set -o pipefail`**: Maven failure vẫn làm job FAIL, dù `tee` và các upload steps chạy thành công.
3. **`path` chỉ định thư mục/file report cần thiết**, không upload toàn bộ `target/` (có thể có binaries, dumps, secrets) hoặc toàn workspace.
4. **`retention-days`** giới hạn thời gian giữ artifact; giá trị thực phải nằm trong policy và mức tối đa mà GitHub organization/repository cho phép.

Đây là **template học tập**, không có release secrets. Trong **production**, **xóa bước `Upload lab-only diagnostic log`** hoặc thay bằng một quy trình rà soát/redaction có chính sách và phân quyền trước khi archive. Đừng cho raw `-X` logs hoặc private credentials vào artifacts.

### 11.1. Vì sao if-no-files-found không nên làm mất nguyên nhân lỗi?

Khi compiler fail trước Surefire, có thể **không có bất kỳ XML test nào**. `if-no-files-found: warn` cho biết thiếu report; lỗi Maven gốc vẫn nằm ở CI build step, với exit code nonzero.

Nếu policy của tổ chức bắt buộc có report sau khi test goal đã chạy, nên kiểm tra sự hiện diện **đúng giai đoạn** bằng một bước kiểm định riêng. Không tự buộc mọi build phải có Failsafe reports khi lỗi đã xảy ra ở `compile` trước đó.

### 11.2. Không làm Maven “xanh giả” chỉ để lưu artifact

Đoạn sai:

```bash
# PHẢN VÍ DỤ: che thất bại test/quality
mvn clean verify || true
```

Đoạn khác cũng có thể sai:

```bash
# PHẢN VÍ DỤ nếu không bật pipefail trên Bash
mvn clean verify | tee maven.log
```

Vì các đoạn này có thể khiến CI không thấy Maven failure.

**Mục tiêu:** build step vẫn FAILED, bước thu thập evidence vẫn chạy. Đây là hai trạng thái hoàn toàn tương thích.

### 11.3. Upload artifact không bằng hiển thị JUnit ngay trên CI

`actions/upload-artifact` lưu các file thành artifact archive để người có quyền tải về. Nó **không tự phân tích JUnit XML thành danh sách testcases/annotations trong giao diện Checks**.

Nếu muốn dashboard test results, cần một CI-native test publisher hoặc JUnit XML adapter/action thích hợp. Khi thêm adapter:

- Chỉ feed `TEST-*.xml` tương thích, không đưa `failsafe-summary.xml` như thể JUnit testcase report.
- Giữ nguyên build/test exit status.
- Phân quyền truy cập reports.
- Trong multi-module, giữ các file paths phân biệt module để tránh collision.

## 12. Multi-module CI: chọn glob và không ghi đè file

Ví dụ Maven reactor:

```text
parent/
├── pom.xml
├── data/
│   └── target/surefire-reports/
├── api/
│   └── target/surefire-reports/
└── application/
    └── target/failsafe-reports/
```

Ở root CI job, có thể dùng:

```yaml
- name: Upload reports from all modules
  if: ${{ always() }}
  uses: actions/upload-artifact@v7
  with:
    name: reactor-reports-${{ github.run_id }}
    path: |
      **/target/surefire-reports/
      **/target/failsafe-reports/
      **/target/checkstyle-result.xml
      **/target/site/jacoco/
    if-no-files-found: warn
    retention-days: 7
```

**Cẩn thận:** glob, relative paths và cách action xây cấu trúc thư mục archive phụ thuộc version action; hãy kiểm tra artifact thực. Nếu aggregator/CI framework làm phẳng filenames, hai modules đều có `TEST-dev.course.CommonTest.xml` có thể va chạm. Cần giữ per-module directories hoặc đặt artifact name riêng cho từng module.

Với `mvn -pl :app -am verify`, chỉ các modules được chọn tham gia reactor. Report của module ngoài selection không có. Nếu chính sách yêu cầu toàn bộ project, chạy full reactor hoặc các jobs có coverage rõ.

### 12.1. Phân biệt test failures và skipped modules

Một reactor có thể dừng ở module A do test failure khiến module B ở trạng thái SKIPPED, nhưng thư mục reports của B không được tạo. Khi tổng hợp CI status:

- Module A: FAIL, có Surefire XML.
- Module B: NOT RUN, không có reports.
- Không đánh giá B là PASS vì không có failure report.

Nếu muốn tiếp tục modules không phụ thuộc để thu nhiều failures, có thể cân nhắc reactor options như `-fae` (fail at end), nhưng cần hiểu dependency graph và vẫn giữ final nonzero outcome. Không thay thế fail-fast policy một cách ngẫu nhiên khi có side effects deployment.

## 13. Báo cáo Checkstyle và PMD: findings khác gate result

Static analysis reports trả lời “vấn đề nào ở file/line nào?”, còn gate quyết định có chặn build không.

### 13.1. Checkstyle

Với POM lab, `checkstyle:check` chạy trong `verify` và thường tạo:

```text
target/checkstyle-result.xml
```

Nếu coding style không đạt, gate có thể FAIL và XML vẫn hữu ích để chẩn đoán. Kết quả report nên được upload khi phù hợp, nhưng không coi report hiện hữu là gate đã PASS.

Muốn tạo HTML report độc lập, có thể chạy reporting goal:

```bash
mvn org.apache.maven.plugins:maven-checkstyle-plugin:3.6.0:checkstyle
```

Plugin có thể tạo HTML/site output theo configuration; **không suy luận chính xác HTML path từ tên goal** khi chưa xem outputDirectory/site settings. Các dự án thật thường dùng Maven Site Plugin cho các report pages.

### 13.2. PMD

PMD Plugin có `pmd:pmd` để tạo report và `pmd:check` để kiểm tra policy. Một ví dụ report goal:

```bash
mvn org.apache.maven.plugins:maven-pmd-plugin:3.28.0:pmd
```

Nếu output dạng XML theo cấu hình thông dụng, file:

```text
target/pmd.xml
```

có thể được tạo. Nhưng **POM lab không cấu hình PMD**, nên file này chỉ có sau khi chủ động gọi goal hoặc thêm plugin; không coi path của PMD là report được tạo tự động mỗi lần `mvn verify`.

CI upload path có thể mở rộng:

```yaml
path: |
  target/surefire-reports/
  target/failsafe-reports/
  target/checkstyle-result.xml
  target/pmd.xml
```

Chỉ thêm `target/pmd.xml` nếu job thật sự chạy PMD, và kiểm tra plugin output version/config.

### 13.3. Tránh báo cáo XML có secrets

Static reports có thể chứa source paths, snippets, internal repository names hoặc configuration data; tùy plugin và ruleset. Không tự động đăng công khai toàn bộ reports để “tăng minh bạch”. Áp dụng cùng policy bảo vệ reports như với logs/test XML.

## 14. SpotBugs: cần compiled classes và output config phù hợp

SpotBugs phân tích Java bytecode và có thể chạy tại giai đoạn sau compile. Các goal thông dụng:

- `spotbugs:spotbugs`: phân tích và tạo output, thường XML khi cấu hình tương ứng.
- `spotbugs:check`: đánh giá bug instances và có thể fail build theo policy.

Một vị trí report thường gặp:

```text
target/spotbugsXml.xml
```

Tuy nhiên phải xác nhận **plugin version, `xmlOutput`, `xmlOutputFilename`, `outputDirectory`**. Không assume SpotBugs luôn tạo file đó nếu chỉ chạy `mvn test` hoặc plugin chưa được cấu hình.

Ví dụ snippet SpotBugs để chạy sau compile, chỉ là **tham khảo** (không thêm vào POM lab khi chưa kiểm tra phù hợp với codebase):

```xml
<plugin>
    <groupId>com.github.spotbugs</groupId>
    <artifactId>spotbugs-maven-plugin</artifactId>
    <version>4.10.4.1</version>
    <configuration>
        <xmlOutput>true</xmlOutput>
    </configuration>
    <executions>
        <execution>
            <id>spotbugs-report</id>
            <phase>verify</phase>
            <goals>
                <goal>spotbugs</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Goal `spotbugs` phân tích và báo cáo; **chưa tự bảo đảm gate**. Nếu cần chặn build, thêm `spotbugs:check` và policy thích hợp trong một configuration review riêng.

## 15. JaCoCo: coverage report khác execution data và coverage gate

JaCoCo có những output dễ nhầm:

| File/goal | Vai trò |
| --- | --- |
| `target/jacoco.exec` | **Binary data** ghi coverage khi JVM tests chạy; không phải XML hay HTML |
| `jacoco:report` | Sinh HTML/XML/CSV từ data + classes/source |
| `target/site/jacoco/index.html` | Trang HTML dành cho người đọc |
| `target/site/jacoco/jacoco.xml` | XML dành cho CI/coverage adapters |
| `jacoco:check` | Gate kiểm tra ngưỡng coverage, không chỉ tạo report |

Trong POM lab, JaCoCo `prepare-agent` thiết lập Java agent trước tests; Surefire và Failsafe sử dụng agent configuration nếu không bị override. JaCoCo `report` chạy ở verify, sau khi tests đã diễn ra.

**Không gán `jacoco:report` là “coverage gate”**: nó có thể tạo báo cáo với coverage thấp mà vẫn thành công. Nếu policy yêu cầu tối thiểu 80%, phải cấu hình `jacoco:check` với rule/limit thực và kiểm chứng negative case.

### 15.1. Khi coverage file không xuất hiện

Các nguyên nhân phổ biến:

- Tests đã skip nên không có dữ liệu agent.
- `argLine` của Surefire/Failsafe bị override, làm mất JaCoCo `-javaagent`.
- Java fork/debug mode khiến agent không attach như kỳ vọng.
- Maven dừng ở phase test do Surefire FAIL trước khi đến JaCoCo report ở verify.
- Plugin execution không bind đúng lifecycle phase.
- Multi-module project chỉ build một số modules.

**Không lấp chỗ trống bằng coverage 0% hoặc 100% tự đoán.** Cần báo NOT GENERATED cùng nguyên nhân/phase.

## 16. Giữ các reports nhưng kiểm soát bảo mật

**Reports và logs có thể chứa bí mật**, dù mục tiêu ban đầu chỉ là chẩn đoán lỗi:

- Surefire/Failsafe có thể capture `system-out`/`system-err`, assertion expected/actual và exception stack traces.
- HTTP integration tests có thể in authorization headers, query tokens, cookies hoặc private URLs.
- Maven `-X` có thể để lộ plugin config/system properties và hạ tầng.
- Static analyzers/SBOM có thể chứa internal artifact coordinates và source paths.
- Screenshots, Java heap dumps và test attachments có thể chứa dữ liệu cá nhân.
- Một `.ci-diagnostics/maven-verify.log` được archive có thể tồn tại nhiều ngày và nhiều người có quyền tải.

**Áp dụng các biện pháp tối thiểu:**

1. Test và plugin **không in credentials ngay từ nguồn**.
2. Không truyền token qua `-Dpassword=...` hoặc POM/plain text.
3. Maven servers đọc credentials từ user/CI settings và trusted secret store; không cấp cho untrusted PR.
4. Dùng retention tối thiểu cần thiết và access controls ở CI artifact storage.
5. Tránh upload toàn bộ workspace, `~/.m2/settings.xml`, `.env`, `target/` hoặc raw `-X` logs.
6. Khi cần chia sẻ report, rà token, private URLs, stack traces, test payloads và quyền xem.
7. CI masking không bảo đảm che token đã bị Base64/URL-encoded hoặc chia nhỏ.
8. Nếu secret đã lộ, **revoke/rotate trước**, rồi kiểm tra phạm vi logs/artifacts/CI downloads, xóa hoặc hạn chế truy cập theo incident policy.

**Báo cáo test từ một build FAIL vẫn cần được giữ, nhưng không vì vậy mà được công khai mặc định.**

## 17. Khi nào cần HTML test report?

Surefire và Failsafe tạo machine-readable XML/TXT; một số người muốn HTML để duyệt trong trình duyệt.

Maven Surefire Report Plugin cung cấp:
- `surefire-report:report-only`: tạo báo cáo từ Surefire XML mà **không chạy lại tests**.
- `surefire-report:failsafe-report-only`: tạo HTML từ Failsafe XML theo plugin hỗ trợ.
- `surefire-report:report`: goal tạo report với lifecycle/reporting behavior riêng.

Sau khi đã chạy tests, muốn render chỉ từ XML hiện có, ví dụ:

```bash
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.5.2:report-only
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.5.2:failsafe-report-only
```

Những lệnh trên có thể cần Maven Site/Doxia dependencies và môi trường plugins phù hợp. **Không chạy `mvn clean` trước khi render** nếu reports dưới `target/` chưa được archive, vì nó sẽ xóa chính XML đầu vào.

HTML site output path còn phụ thuộc reporting/site configuration. Khi CI cần test annotations, thông thường **JUnit XML adapter** trực tiếp tiện hơn HTML.

## 18. Một chiến lược giữ lại báo cáo theo mức độ giá trị

| Loại artifact | Nên giữ lúc nào | Thời hạn/phân quyền gợi ý |
| --- | --- | --- |
| Surefire XML | Mọi build chạy unit tests, đặc biệt FAILED | Ngắn-vừa; quyền team/CI |
| Failsafe XML + summary | Mọi build chạy integration tests, đặc biệt FAILED | Ngắn-vừa; hạn chế test payload |
| JaCoCo XML/HTML | Build có coverage analysis | Theo policy chất lượng và dashboard |
| Checkstyle/PMD/SpotBugs XML | Build có analysis | Theo policy quality/security |
| Raw Maven console log | Khi cần điều tra, đã đánh giá dữ liệu nhạy cảm | Retention ngắn, quyền hạn chế |
| Maven -X debug log | Chỉ khi thật sự cần và môi trường riêng | **Rất ngắn, không public** |
| Test screenshots/videos | UI/e2e failures, đủ bằng chứng | Giới hạn quyền và dung lượng |
| Heap/core dumps | Chỉ với sự cố đặc biệt có phê duyệt | Nhạy cảm cao; không đưa vào artifact mặc định |
| Maven settings/credentials | **Không upload làm report** | Luôn ở secret store, không trong CI artifact |

Không có một số ngày retention phù hợp cho mọi tổ chức. Ví dụ workflow sử dụng `7` ngày cho reports và `3` ngày cho lab log; những giá trị này phải điều chỉnh theo policy, độ nhạy cảm, compliance và giới hạn nền tảng.

**Đừng xóa sạch reports quá sớm nếu pipeline cần điều tra lỗi, nhưng cũng đừng lưu vô hạn raw logs chứa dữ liệu riêng.**

## 19. Chẩn đoán các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `mvn test` PASS nhưng không có Failsafe reports | Chưa tới integration-test/verify | Chạy `mvn verify` |
| Failsafe XML có test FAIL nhưng command xanh | Chỉ chạy `integration-test`, bỏ `verify` | Chạy đầy đủ verify |
| Surefire XML có failure, CI không còn thấy log | Upload step chỉ chạy khi success | Dùng `if: always()` |
| CI báo PASS dù Maven test FAIL | Dùng `|| true` hoặc `tee` thiếu pipefail | Giữ Maven exit code |
| Không có XML khi compile FAIL | Test phase chưa tới | Không coi là tests PASS |
| JUnit XML không có testcase khi test skip | `skipTests` hoặc naming config | Kiểm tra skips và plugin logs |
| Report ở local IDE nhưng CI không thấy | IDE runner khác Maven CLI | Chạy Maven goals trong IDE/CI |
| Surefire chạy luôn integration test | Class naming/includes cấu hình sai | Tách `*Test` và `*IT`, xem includes |
| Failsafe không nhận `CalculatorIT` | Plugin không có execution hoặc test discovery sai | Bind integration-test + verify |
| Failsafe verify không phát hiện lỗi | Summary không được tạo/verify bị skip | Xem `failsafe-summary.xml` và log |
| XML có nhưng không có HTML | HTML cần reporting plugin/CI renderer | Dùng Surefire Report Plugin |
| Coverage XML trống hoặc vắng | JaCoCo agent/report chưa chạy | Xem execution, argLine, skip |
| Checkstyle report không có | Plugin goal không chạy hoặc output path đổi | Kiểm tra effective POM và log |
| PMD/SpotBugs report path không đúng | Plugin version/config output khác | Kiểm tra outputFile/outputDirectory |
| Reports bị ghi đè ở reactor | Flatten paths hoặc trùng class names | Giữ tên module/directory |
| CI archive không có file | Glob sai, working directory khác, phase dừng sớm | Kiểm tra paths và if-no-files-found |
| Report chỉ còn số tổng, không còn stack trace | Chỉ lưu summary, bỏ XML/TXT | Lưu cả files cần thiết |
| Artifact upload thành công nhưng job đỏ | **Hành vi đúng** nếu Maven FAIL | Sửa failure gốc, không ép xanh |
| Test failure report chứa token | Test/HTTP log in secret | Revoke/rotate, hạn chế report |
| `mvn clean` xóa log/report | Đặt log trong target hoặc chạy clean sau test | Giữ log ngoài target, archive sớm |
| `mvn -pl` chỉ có reports vài module | Các modules khác không được build | Đọc reactor selection |
| XML parse fail ở CI dashboard | Parser không tương thích report/summary hoặc file hỏng | Feed đúng TEST-*.xml, kiểm tra schema |
| HTML artifact quá nặng | Upload toàn bộ target/site hoặc binary | Chọn thư mục cần thiết, retention ngắn |
| Không biết build run nào tạo XML | Artifact naming thiếu run ID/attempt | Gắn metadata build ID/commit |

Khi debug, nên kiểm tra **goal thực sự được thực thi**, rồi **thời điểm failure**, rồi **file path**, sau đó mới **CI upload condition**. Đừng bắt đầu bằng xóa cache hoặc tăng quyền cho cả pipeline.

## 20. IDE và Maven: báo cáo được tạo ở đâu?

IntelliJ IDEA, Eclipse/Buildship và các IDE khác có thể chạy JUnit bằng **IDE test runner riêng**. Lúc đó IDE có kết quả test trong UI, nhưng **Surefire/Failsafe XML có thể không tồn tại** vì Maven plugins không được gọi.

Nếu muốn đồng bộ cách chạy local/CI:

1. Chọn JDK tương ứng với CI (Java 17 trong lab).
2. Chạy Maven goal `clean verify` qua Maven tool window hoặc terminal.
3. Kiểm tra Maven profiles/system properties giống CI.
4. Đọc `target/surefire-reports`, `target/failsafe-reports` và quality paths.
5. Khi dùng IDE test runner, chỉ coi kết quả đó là **IDE runner result**, không chứng minh Failsafe verify đã chạy.
6. Không bật `-DskipTests` ở local/CI profile mà không nhận ra.

**Maven Wrapper** (`./mvnw` hoặc `mvnw.cmd` khi project đã cấu hình) giúp chuẩn hóa Maven distribution version. Nó không tự ghim JDK/compiler/plugin outputs, nhưng là một thành phần hữu ích của reproducible CI.

## 21. Checklist cho người quản trị CI

- [ ] Maven/JDK/plugins versions đã được xác nhận.
- [ ] Surefire chạy unit tests, tạo XML/TXT trong `target/surefire-reports`.
- [ ] Failsafe được bind cả `integration-test` và `verify`.
- [ ] Integration tests có naming/selection đúng và không bị skip.
- [ ] Surefire/Failsafe không báo xanh giả khi không tìm thấy tests (nếu policy yêu cầu test hiện hữu).
- [ ] Checkstyle/PMD/SpotBugs reports chỉ được kỳ vọng khi plugin tương ứng chạy.
- [ ] JaCoCo agent/report và optional coverage gate được cấu hình đúng.
- [ ] Maven CI chạy tới `verify`, không dừng ở `integration-test`.
- [ ] Negative test cho Surefire và Failsafe thực sự tạo nonzero Maven exit code.
- [ ] Log qua `tee` vẫn giữ failure bằng `pipefail`.
- [ ] Diagnostic log không nằm trong `target` trước `clean`.
- [ ] Upload reports bằng condition xử lý failure, không ép Maven exit code thành 0.
- [ ] Paths/globs giữ đúng modules, không overwrite hoặc flatten mất thông tin.
- [ ] Artifact names chứa run ID/attempt khi hữu ích.
- [ ] Artifact retention, compression, quyền tải được review.
- [ ] Surefire/Failsafe XML được dùng bởi test-report adapter, không đưa summary XML nhầm schema.
- [ ] HTML reports chỉ render khi cần, không xóa XML đầu vào trước render.
- [ ] Không upload toàn bộ source/workspace/target vì tiện.
- [ ] Secret scan/review áp dụng cho test stdout/stderr, reports và diagnostic logs.
- [ ] Không tự động upload raw `-X` logs từ build có credentials.
- [ ] Không chạy `install/deploy` sau khi verify FAIL.
- [ ] Đã kiểm tra báo cáo của một pipeline FAILED còn xem được sau khi job kết thúc.

## 22. Bài tập kiểm tra hiểu biết

1. So sánh trách nhiệm Surefire và Failsafe, kể tên default report directories.
2. Giải thích vì sao `mvn integration-test` không phù hợp làm required CI gate cuối.
3. Một class `CalculatorTest` được Surefire nhận diện như thế nào?
4. Một class `CalculatorIT` được Failsafe nhận diện như thế nào?
5. Viết đường dẫn XML và TXT của `CalculatorIT` trong lab.
6. `failsafe-summary.xml` phục vụ bước nào và vì sao không thay các TEST-*.xml?
7. Xây project Java 17 hoàn chỉnh từ POM và các source files, chạy `mvn clean verify`.
8. Xác nhận 2 unit tests + 2 integration tests PASS và stdout `APP: Giá trị: 7`.
9. Chạy `-Dlab.failUT=true`; nêu vì sao Failsafe reports có thể chưa được tạo.
10. Chạy `-Dlab.failIT=true`; phân biệt test result ở integration-test và failure tại verify.
11. Vì sao `maven.test.failure.ignore` không phải giải pháp cho việc lưu reports?
12. Trong Bash, `mvn ... | tee file.log` có nguy cơ nào nếu thiếu `pipefail`?
13. Vì sao không nên ghi diagnostic log vào `target/` trước lệnh `mvn clean`?
14. Sửa một workflow CI để upload reports cả khi `mvn verify` thất bại.
15. Tại sao `actions/upload-artifact` không tự tạo dashboard JUnit test annotations?
16. Phân biệt Checkstyle `checkstyle:check` và `checkstyle:checkstyle`.
17. Vì sao JaCoCo `jacoco.exec` không phải file XML coverage?
18. Khi `jacoco:report` có coverage 20%, build có tự fail do coverage thấp không?
19. Multi-module reporter cần bảo toàn thông tin module như thế nào?
20. Vì sao một module bị SKIPPED trong reactor không thể được ghi là PASS?
21. Nếu Surefire XML chứa Authorization header, bạn làm gì trước khi chia sẻ?
22. Tại sao report retention phải theo sensitivity và policy thay vì lưu mãi?
23. Khi chạy tests qua IDE runner, có chắc Surefire reports được tạo không?
24. Nếu SpotBugs được cấu hình output JSON/HTML thay vì XML, CI upload path có cần đổi không?
25. Thiết kế pipeline vừa giữ đầy đủ bằng chứng failures, vừa không biến job đỏ thành xanh.
26. Khi job fail trước `test` vì dependency resolution, nên báo thế nào về các tests?
27. Một report-only goal có thể có violations nhưng BUILD SUCCESS không?
28. Phân biệt artifact upload success với artifact compilation/test success.
29. Nêu các trường dữ liệu quan trọng nên đọc trong JUnit XML.
30. Vì sao không được tự bật `mvn -X` và archive raw log có token thật?

## 23. Tổng kết

**Surefire**, **Failsafe**, **quality plugins** và **Maven diagnostics** tạo ra những bằng chứng khác nhau trong cùng một build:

- `target/surefire-reports/` ghi **unit tests**.
- `target/failsafe-reports/` ghi **integration tests** và `failsafe-summary.xml` phục vụ bước **verify**.
- Checkstyle/PMD/SpotBugs ghi vấn đề source/bytecode nếu đã bật; JaCoCo ghi coverage khi tests có agent.
- Log Maven giúp tìm lỗi compile/plugin/dependency/repository khi chưa kịp tạo XML test.
- CI phải **giữ đúng Maven exit code**, lưu reports ngay cả khi build FAIL và quản lý retention/security.

Ví dụ Java 17 của bài có **4 tests (2 Surefire + 2 Failsafe)**, chương trình in đúng:

```text
APP: Giá trị: 7
```

Cùng POM có thể minh họa Surefire failure (`-Dlab.failUT=true`) và Failsafe verification failure (`-Dlab.failIT=true`). Đây là cách kiểm tra **báo cáo thật sự tồn tại và CI không che thất bại**, thay vì chỉ đọc tên plugin trong POM.

**Một pipeline tốt có thể FAILED về chất lượng nhưng SUCCESS trong việc giữ bằng chứng chẩn đoán. Không được vì bước lưu báo cáo thành công mà đổi kết quả build thất bại thành thành công.**

## 24. Tài liệu chính thức

- [Apache Maven Surefire Plugin — Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven Surefire Report Plugin](https://maven.apache.org/surefire/maven-surefire-report-plugin/)
- [Apache Maven Checkstyle Plugin — checkstyle:check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
- [Apache Maven Checkstyle Plugin — checkstyle:checkstyle](https://maven.apache.org/plugins/maven-checkstyle-plugin/checkstyle-mojo.html)
- [Apache Maven PMD Plugin — pmd:pmd](https://maven.apache.org/plugins/maven-pmd-plugin/pmd-mojo.html)
- [SpotBugs Maven Plugin](https://spotbugs.github.io/spotbugs-maven-plugin/)
- [JaCoCo Maven Plugin — jacoco:report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)
- [JaCoCo Maven Plugin — jacoco:check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [GitHub Actions — upload-artifact usage and retention](https://github.com/actions/upload-artifact)
- [GitHub Docs — Store and Share Data with Workflow Artifacts](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow)
