# Tích hợp phân tích tĩnh và phân biệt báo cáo với bước chặn build trong Maven

## 1. Mục tiêu học tập: report không đồng nghĩa quality gate

Trong nhóm **Cổng chất lượng**, câu hỏi quan trọng không phải chỉ là “dự án đã dùng Checkstyle/PMD chưa?” mà còn là **“phân tích có thật sự chặn một build không đạt chuẩn hay chỉ tạo báo cáo?”**.

Hai luồng khác nhau:

```text
Java source/bytecode
       |
       v
Static analysis engine
       |
       +--> REPORT MODE
       |       -> tạo XML / HTML / findings
       |       -> để developers đọc và sửa
       |       -> có findings vẫn có thể BUILD SUCCESS
       |
       +--> QUALITY GATE MODE
               -> đọc/khởi chạy analysis
               -> đánh giá số vi phạm, severity hoặc threshold
               -> vượt chính sách -> Maven BUILD FAILURE
               -> CI nhận exit code khác 0 và chặn bước sau
```

Báo cáo là **kết quả quan sát**, còn gate là **quyết định theo chính sách**. Một file `target/checkstyle-result.xml` có 10 findings nhưng `mvn site` thành công không có nghĩa 10 findings được cho phép trong một build phát hành. Tương tự, CI job mang tên “Static Analysis” nhưng chỉ xuất HTML report chưa chắc đã áp dụng bất kỳ điều kiện FAIL nào.

Trong bài này, bạn sẽ:

1. Hiểu static analysis khác compiler, unit tests và coverage.
2. Phân biệt report goals và check goals của **Maven Checkstyle Plugin**, **Maven PMD Plugin**, **SpotBugs Maven Plugin**.
3. Cấu hình `checkstyle:check` để chặn build ở phase `verify`.
4. Tạo dự án Java 17 với POM, ruleset, Java source, JUnit Jupiter tests **chạy được**.
5. Chủ động tạo violation mà Java vẫn compile và 3 tests vẫn PASS, nhưng Checkstyle quality gate phải FAIL.
6. Đọc log, báo cáo, ngưỡng, cấu hình CI, profile và các tình huống “build xanh giả”.
7. Hiểu cách áp dụng quality gate cho multi-module Maven reactor và codebase có nợ kỹ thuật.

Các plugin versions trong bài được ghim làm ví dụ tái lập, **không tuyên bố là mới nhất**.

## 2. Static analysis tìm những vấn đề gì?

**Static analysis** phân tích code mà không cần thực thi luồng nghiệp vụ như khi chạy unit/integration tests. Công cụ có thể đọc Java source/AST hoặc bytecode.

| Dạng vấn đề | Ví dụ | Công cụ phù hợp |
| --- | --- | --- |
| Coding style | Constant viết sai tên, imports, naming, thiếu cấu trúc tài liệu | Checkstyle |
| Bug patterns | Một số mẫu code dễ sinh bug/runtime error | PMD, SpotBugs |
| Maintainability | Complexity, code smells, thiết kế khó bảo trì | PMD |
| Code duplication | Những đoạn code copy/paste | PMD CPD |
| Coverage threshold | Số phần trăm code được test đi qua | JaCoCo — **không phải static analysis thuần** |
| Test correctness | Kết quả thật so với expected output | Surefire/Failsafe — **dynamic tests** |

Static analysis **không chứng minh chương trình chạy đúng**. Một method đúng style có thể tính sai kết quả; một method đúng thuật toán có thể phạm quy tắc style. Không thể thay compiler/test/security review bằng một công cụ style checker.

Static analysis cũng **khác kiểm tra dependency vulnerabilities**. Một project không bị Checkstyle cảnh báo vẫn có thể dùng thư viện chứa lỗ hổng CVE. Muốn quản lý việc đó phải có công cụ, nguồn advisory và chính sách security riêng.

## 3. Những goal nào là report và những goal nào là gate?

| Maven plugin | Report-oriented goal | Quality gate/check goal | Đặc điểm |
| --- | --- | --- | --- |
| Apache Maven Checkstyle Plugin | `checkstyle:checkstyle` | `checkstyle:check` | Quy tắc Java style/source |
| Apache Maven PMD Plugin | `pmd:pmd` | `pmd:check` | Source rules, bug smells và priority |
| Maven PMD Plugin CPD | `pmd:cpd` | `pmd:cpd-check` | Code duplication |
| SpotBugs Maven Plugin | `spotbugs:spotbugs` | `spotbugs:check` | Phân tích bytecode |
| JaCoCo Maven Plugin | `jacoco:report` | `jacoco:check` | Coverage, nhóm công cụ khác |
| Maven test plugins | XML/HTML test reports | Test failures gây build failure theo cấu hình | Thực thi tests, không phải source static analysis |

**Không suy đoán các plugin có chung tham số.** Chẳng hạn Checkstyle có `failOnViolation` và `maxAllowedViolations`; PMD còn có `failurePriority`; SpotBugs dùng các thông số riêng như `failOnError` và `maxAllowedViolations`.

### 3.1. Điểm cốt lõi của Checkstyle

Tài liệu chính thức Checkstyle Plugin 3.6.0 nêu:

- `checkstyle:checkstyle` là **reporting goal**, thực hiện analysis và tạo HTML report.
- `checkstyle:check` là **ordinary goal** có khả năng in violations hoặc **fail Maven build** khi kết quả không đạt cấu hình.
- Muốn gate chạy tự động cần bind `check` trong `<build><plugins><executions>` vào phase thích hợp.
- Chỉ khai báo một report dưới `<reporting>` **không kích hoạt gate ở `mvn verify`**.

Đây là khác biệt chính cần kiểm tra bằng thực nghiệm; sẽ có cả positive case và negative case.

## 4. Lifecycle phase quyết định gate có được chạy không

Một phần Maven default lifecycle:

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Maven còn nhiều phase trung gian. Trong một dự án dùng Checkstyle gate bind ở `verify`:

| Lệnh | Có biên dịch? | Có unit tests? | Có đóng JAR? | Có Checkstyle gate? |
| --- | --- | --- | --- | --- |
| `mvn clean test` | Có | Có | Chưa | **Chưa** |
| `mvn clean package` | Có | Có | Có | **Chưa** |
| `mvn clean verify` | Có | Có | Có | **Có** |
| `mvn clean install` | Có | Có | Có | **Có, trước install** |
| `mvn clean deploy` | Có | Có | Có | **Có, trước deploy** |

**Lựa chọn phase:**

- `validate`: kiểm tra rất sớm, phù hợp một số source-only checks. Khi source còn lỗi cú pháp, static parser có thể báo lỗi trước compiler, làm thông tin ít dễ hiểu hơn.
- `verify`: phổ biến vì Java đã compile/test và package, tiện kiểm tra trước install/deploy; cũng phù hợp những analyzers cần bytecode.
- `test`: chạy sớm hơn verify nhưng cần cân nhắc thứ tự so với compiler/test goals.
- `install` hoặc `deploy`: không nên đợi đến đây mới chặn chất lượng nếu có thể kiểm tra sớm hơn; những phase này tác động repository.

**Nếu CI chỉ chạy `mvn test` mà bạn bind Checkstyle ở `verify`, gate không hề thực thi.** Đừng gọi trạng thái PASS đó là “quality gate đã đạt”.

## 5. Dự án Maven Java 17 đầy đủ

Bài thực hành có:

```text
quality-gate-lab/
├── pom.xml
├── checkstyle.xml
└── src/
    ├── main/java/dev/course/
    │   ├── Calculator.java
    │   └── App.java
    └── test/java/dev/course/
        └── CalculatorTest.java
```

Cần JDK 17+, Maven 3.9.x tương thích, kết nối repository (hoặc cache đã có) để lấy plugins/JUnit. Mọi file Java mã hóa UTF-8.

### 5.1. POM hoàn chỉnh có build gate lẫn reporting

Tạo `quality-gate-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>quality-gate-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>checkstyle.xml</configLocation>
                    <encoding>UTF-8</encoding>
                    <includeTestSourceDirectory>false</includeTestSourceDirectory>
                    <failOnViolation>true</failOnViolation>
                    <maxAllowedViolations>0</maxAllowedViolations>
                    <logViolationsToConsole>true</logViolationsToConsole>
                </configuration>
                <executions>
                    <execution>
                        <id>static-quality-gate</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>checkstyle.xml</configLocation>
                    <encoding>UTF-8</encoding>
                    <includeTestSourceDirectory>false</includeTestSourceDirectory>
                </configuration>
                <reportSets>
                    <reportSet>
                        <reports>
                            <report>checkstyle</report>
                        </reports>
                    </reportSet>
                </reportSets>
            </plugin>
        </plugins>
    </reporting>
</project>
```

**Đọc POM theo hai nhánh:**

1. `<build><plugins>` khai báo Checkstyle Plugin và execution `check` ở phase `verify`. Đây là **gate**, có thể fail build khi `maxAllowedViolations=0` và `failOnViolation=true`.
2. `<reporting><plugins>` đăng ký báo cáo Checkstyle cho Maven Site Plugin. Đây là **report**, không tự biến `mvn verify` thành gate.

Checkstyle Plugin version và `configLocation` được nêu ở cả hai nhánh vì Maven documentation chỉ rõ **configuration trong reporting không tự ảnh hưởng executions trong build**. Vì thế phải giữ ruleset/encoding thống nhất khi dùng cả hai.

Compiler chạy Java release 17; Surefire chạy JUnit Jupiter. Plugin JAR tạo binary JAR thông thường, **không tự làm JAR executable**. Trong ví dụ dùng `java -cp target/classes` khi chạy ứng dụng.

### 5.2. File quy tắc checkstyle.xml

Tạo `quality-gate-lab/checkstyle.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>
    <module name="TreeWalker">
        <module name="ConstantName">
            <property name="format"
                      value="^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"/>
        </module>
    </module>
</module>
```

Đây là một ruleset **nhỏ có chủ đích**, chỉ kiểm tra tên constants theo regex. Hợp lệ: `BASE_VALUE`, `MAX_RETRY_2`. Không hợp lệ: `badName`, `retryLimit` nếu là constant thuộc phạm vi check.

**Quy tắc Checkstyle khác compiler:** Java cho phép tên constant `badName` về mặt cú pháp, nhưng project có thể không cho phép về style. Điều này giúp tạo negative test mà không phá unit tests.

### 5.3. Calculator.java

Tạo `src/main/java/dev/course/Calculator.java`:

```java
package dev.course;

public final class Calculator {
    public static final int BASE_VALUE = 10;

    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
```

Constant `BASE_VALUE` tuân theo regex. Phương thức `add` thuần Java, không phụ thuộc runtime bên ngoài.

### 5.4. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + Calculator.add(6, 8));
    }
}
```

Stdout **chính xác do ứng dụng tạo**:

```text
RESULT=14
```

### 5.5. CalculatorTest.java

Tạo `src/test/java/dev/course/CalculatorTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void sumsPositiveNumbers() {
        assertEquals(14, Calculator.add(6, 8));
    }

    @Test
    void sumsNegativeNumbers() {
        assertEquals(-5, Calculator.add(-2, -3));
    }

    @Test
    void sumsWithZero() {
        assertEquals(7, Calculator.add(7, 0));
    }
}
```

Đây là **ba unit tests**, đều hợp lệ theo JUnit Jupiter 5. Test source nằm dưới `src/test/java`; cấu hình Checkstyle `includeTestSourceDirectory=false` chỉ nói **Checkstyle không quét test source theo lựa chọn đó**, không làm Surefire skip tests.

## 6. Positive case: quality gate PASS

Trong thư mục có POM:

```bash
mvn -version
mvn clean verify
```

Kỳ vọng khi plugins và dependencies resolve thành công:

- Java 17 compile các classes.
- JUnit Jupiter chạy **3 tests**, không có failure/error.
- Maven JAR Plugin tạo JAR ở `target/quality-gate-lab-1.0.0-SNAPSHOT.jar`.
- Execution `maven-checkstyle-plugin:3.6.0:check (static-quality-gate)` chạy tại `verify`.
- Checkstyle không thấy vi phạm của rule `ConstantName` trong mã chính.
- Maven kết thúc **BUILD SUCCESS**, process exit code **0**.

Log rút gọn để nhận biết:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
... maven-checkstyle-plugin:3.6.0:check (static-quality-gate) ...
BUILD SUCCESS
```

Đây là những dòng đại diện, **không phải nguyên văn full log**.

Chạy ứng dụng:

```bash
java -cp target/classes dev.course.App
```

Stdout:

```text
RESULT=14
```

Lệnh `java -jar target/quality-gate-lab-1.0.0-SNAPSHOT.jar` không phải lệnh chạy được cam kết vì POM không cấu hình entry `Main-Class`. Điều này tách biệt vấn đề executable packaging khỏi quality gate.

## 7. Negative case: code hợp lệ với Java nhưng vi phạm Checkstyle

**Giữ nguyên Calculator.java**, thêm một field ngay sau `BASE_VALUE`:

```java
public static final int badName = 99;
```

Đây chỉ là **đoạn code thêm vào trong class**, không phải một Java source file độc lập. Field `badName` vẫn hợp lệ với Java compiler, không ảnh hưởng kết quả `Calculator.add`, nhưng vi phạm Checkstyle `ConstantName` vì regex chỉ cho phép UPPER_SNAKE_CASE.

### 7.1. Chạy đến test: test PASS nhưng gate chưa chạy

```bash
mvn clean test
```

Expected:

```text
Compile: PASS
Unit tests: 3 PASS
Checkstyle gate: NOT EXECUTED
Maven build: SUCCESS
```

Đây là diễn giải logic; Maven log thực tế có format riêng. **Tại sao build xanh?** Checkstyle check được bind ở phase `verify`, còn command chỉ tới `test`. Không được xem đó là chất lượng đạt gate.

### 7.2. Chạy report goal trực tiếp

```bash
mvn org.apache.maven.plugins:maven-checkstyle-plugin:3.6.0:checkstyle
```

`checkstyle:checkstyle` tạo báo cáo. Nếu `checkstyle.xml` được nạp đúng, report phải ghi nhận `badName` như một violation theo `ConstantName`. XML result thường có thể kiểm tra tại:

```text
target/checkstyle-result.xml
```

Vị trí HTML tùy chạy trực tiếp hay qua Maven Site Plugin và cấu hình outputDirectory. **Không chỉ đoán file path; hãy đọc log và output thực**.

Goal báo cáo có thể **BUILD SUCCESS** dù thấy violation vì nó không phải gate `checkstyle:check`. Nếu tool lỗi parser, tải plugin hoặc filesystem thì vẫn có thể FAIL — phải phân biệt lỗi công cụ với policy failure.

### 7.3. Tạo site report

Vì POM đã có `<reporting>`, chạy:

```bash
mvn site
```

Maven Site Plugin có thể tạo Checkstyle HTML trong thư mục site, thường:

```text
target/site/checkstyle.html
```

Đây là báo cáo cho người đọc, không phải bằng chứng gate đã chạy. Nếu Site Plugin lỗi vì cấu hình/version, Doxia, skin hoặc repository, cần sửa lỗi tooling; **không ghi “Checkstyle đã tìm 0 vấn đề” khi report không được tạo**.

### 7.4. Chạy đến verify: Checkstyle gate FAIL

```bash
mvn clean verify
```

POM đặt:

```xml
<failOnViolation>true</failOnViolation>
<maxAllowedViolations>0</maxAllowedViolations>
```

Với một constant tên `badName`:

- Java compiler vẫn PASS.
- Surefire vẫn chạy **3 tests PASS**.
- Maven tạo binary JAR trong phase package.
- Goal `checkstyle:check` chạy ở `verify`.
- Violation của `ConstantName` vượt ngưỡng 0.
- Maven trả **BUILD FAILURE**, exit code khác 0.

Minh họa:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Checkstyle: ConstantName violation for badName
BUILD FAILURE
```

Không coi ba dòng trên là raw log chuẩn; thông báo/line number thực tế tùy version. Điều cần kiểm tra là **goal Checkstyle gây FAILURE**, không phải test case thất bại.

**Vì sao có JAR dù build fail?** Checkstyle chạy ở `verify` sau `package`. Artifact có thể đã được đóng gói nhưng **chưa đạt gate**, vì vậy CI phải chặn install/deploy/publish artifact đó.

### 7.5. Sửa để pass

Xóa field `badName`, hoặc đổi tên thành:

```java
public static final int BAD_NAME = 99;
```

Sau đó:

```bash
mvn clean verify
```

Kỳ vọng **3 tests PASS, Checkstyle PASS, BUILD SUCCESS**. Phép thử PASS/FAIL này có giá trị hơn việc chỉ đọc POM vì nó chứng minh gate thực sự chạy.

## 8. Checkstyle: các tham số chính sách thường dùng

Theo Maven Checkstyle Plugin 3.6.0:

| Parameter | Mặc định/ý nghĩa | Lưu ý |
| --- | --- | --- |
| `failOnViolation` | Mặc định `true` | Có fail khi vi phạm vượt ngưỡng không |
| `maxAllowedViolations` | Mặc định `0` | Số vi phạm tối đa trước khi check fails |
| `failsOnError` | Mặc định `false` | Có thể fail sớm vì errors/violations theo plugin, **khác `failOnViolation`** |
| `logViolationsToConsole` | Mặc định `true` | In chi tiết violations khi check |
| `includeTestSourceDirectory` | Mặc định `false` | Có quét Java test source |
| `configLocation` | Quy tắc từ file/resource | Tránh để report/gate dùng khác config |
| `outputFile` | Thường `target/checkstyle-result.xml` | Tệp output tùy goal và config |

Ví dụ ngưỡng cho phép tối đa hai violations:

```xml
<configuration>
    <configLocation>checkstyle.xml</configLocation>
    <failOnViolation>true</failOnViolation>
    <maxAllowedViolations>2</maxAllowedViolations>
</configuration>
```

| Findings được tính | Gate với ngưỡng 2 |
| ---: | --- |
| 0 | PASS |
| 1 | PASS |
| 2 | PASS |
| 3 | FAIL |

Ngưỡng cho phép có thể hữu ích khi xử lý legacy debt theo lộ trình, nhưng **không chứng minh 2 findings là an toàn**. Một vấn đề nghiêm trọng không nên được hợp thức hóa chỉ bằng cách tăng tổng số violations được phép.

**Tham số `failsOnError` không giống `failOnViolation`**: nó có thể fail trước khi goal thực hiện luồng kiểm đếm/ghi console; đừng bật bừa rồi mong `maxAllowedViolations` có cùng tác dụng.

## 9. Chỉ report hay chỉ gate: hai snippet để so sánh

### 9.1. Report-only configuration

Đặt trong `<project>`:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-checkstyle-plugin</artifactId>
            <version>3.6.0</version>
            <configuration>
                <configLocation>checkstyle.xml</configLocation>
            </configuration>
            <reportSets>
                <reportSet>
                    <reports>
                        <report>checkstyle</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
```

Với snippet này, `mvn site` tạo report nếu site tooling hoạt động. **Chưa có execution `check` để chặn `mvn verify`**.

### 9.2. Gate-only configuration

Đặt trong `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <configuration>
        <configLocation>checkstyle.xml</configLocation>
        <failOnViolation>true</failOnViolation>
        <maxAllowedViolations>0</maxAllowedViolations>
    </configuration>
    <executions>
        <execution>
            <id>quality-gate</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Với snippet này, `mvn verify` áp chính sách gate; nó không tự yêu cầu tạo Maven HTML site. Các đoạn trên **là cấu hình so sánh**, không phải hướng dẫn thêm plugin/execution trùng vào POM runnable đã có cả hai nhánh.

## 10. PMD: report pmd:pmd và gate pmd:check

Maven PMD Plugin 3.28.0 cũng chia hai goals:

- `pmd:pmd`: reporting goal, tạo PMD report từ source/rulesets.
- `pmd:check`: check goal bind mặc định ở `verify` khi được cấu hình execution; gọi analysis `pmd` trước khi kiểm tra policy.
- `pmd:cpd`: report code duplication.
- `pmd:cpd-check`: gate cho duplication theo rules của CPD.

Snippet **tùy chọn**, chỉ áp dụng sau khi đã thống nhất rulesets:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-pmd-plugin</artifactId>
    <version>3.28.0</version>
    <configuration>
        <failOnViolation>true</failOnViolation>
        <failurePriority>5</failurePriority>
        <maxAllowedViolations>0</maxAllowedViolations>
    </configuration>
    <executions>
        <execution>
            <id>pmd-quality-gate</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

PMD priorities từ **1 (nghiêm trọng nhất) đến 5 (ít nghiêm trọng nhất)**:

- `failurePriority=5`: các priorities 1–5 có thể bị tính như violations gây fail.
- `failurePriority=3`: chỉ priorities 1–3 có thể làm gate fail; 4–5 có thể hiển thị như warnings.
- `maxAllowedViolations=0`: không cho phép violation nào **nằm trong tập bị tính là failure**.
- `failOnViolation=true`: bật quyết định fail theo các điều kiện trên.

**Không suy luận pmd:pmd là gate** chỉ vì nó xuất hiện trong Maven log; phải có `pmd:check` hoặc một chính sách kiểm tra khác thực sự đánh giá exit status.

PMD reporting snippet:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-pmd-plugin</artifactId>
            <version>3.28.0</version>
        </plugin>
    </plugins>
</reporting>
```

Nếu đã có Checkstyle reporting, hãy gộp các report plugins vào **cùng một thẻ `<reporting>`**, không sao chép nhiều thẻ `<reporting>` ở cấp project.

## 11. SpotBugs: phân tích bytecode, không chỉ Java source

SpotBugs Maven Plugin phân tích **compiled bytecode**. Nó khác Checkstyle naming rules:

- `spotbugs:spotbugs`: chạy analysis/tạo kết quả phát hiện bug patterns.
- `spotbugs:check`: kiểm tra findings theo cấu hình và có thể fail build.
- Vì cần bytecode, nên không nên bind bước scan vào phase trước compile mà không xem requirements.

Một snippet gate minh họa dùng plugin 4.10.4.1:

```xml
<plugin>
    <groupId>com.github.spotbugs</groupId>
    <artifactId>spotbugs-maven-plugin</artifactId>
    <version>4.10.4.1</version>
    <configuration>
        <failOnError>true</failOnError>
        <maxAllowedViolations>0</maxAllowedViolations>
    </configuration>
    <executions>
        <execution>
            <id>spotbugs-quality-gate</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **snippet nâng cao**, không thuộc POM runnable chính, và không cam kết đoạn Java Calculator luôn tạo một SpotBugs finding. Test goal `spotbugs:check` khi đã có compile output, xem file XML/report thực, rồi quyết định threshold theo loại bug pattern.

## 12. Static analysis khác test và coverage gates

```text
mvn clean verify
   |
   +-- Maven compiler       -> chặn lỗi Java compile
   +-- Surefire             -> chặn failed unit tests
   +-- Failsafe (nếu có)    -> chặn failed integration tests
   +-- JaCoCo:check (nếu có)-> chặn coverage dưới ngưỡng
   +-- Checkstyle:check     -> chặn style violations
   +-- PMD:check (nếu có)   -> chặn selected PMD violations
   +-- SpotBugs:check       -> chặn selected bug patterns
```

Sơ đồ này **chỉ minh họa các loại cổng**, không có nghĩa POM mẫu đã kích hoạt Failsafe, JaCoCo, PMD và SpotBugs.

- Unit tests chạy code để kiểm tra output/behavior; source có thể test PASS dù style FAIL.
- JaCoCo đo code coverage khi tests chạy; coverage cao không chứng minh behavior đúng.
- Static analyzers tìm những patterns source/bytecode mà tests có thể bỏ sót.
- Dependency security scanning cần thêm nguồn dữ liệu advisory; static analysis một mình không đủ.
- Manual review vẫn cần thiết cho business logic và security context.

Một nhóm nên chọn **tập chính sách bổ trợ**, tránh bật trùng các rules làm dev nhận cùng issue nhiều lần từ nhiều tools.

## 13. Multi-module reactor: gate cho module nào?

Trong Maven reactor:

```text
parent/ (packaging=pom)
├── core/ (packaging=jar)
└── app/  (packaging=jar; dependency core)
```

Một Checkstyle gate được cấu hình tại parent có thể **kế thừa** xuống children theo Maven model, nhưng cần kiểm tra effective POM của từng module:

```bash
mvn help:effective-pom
mvn -pl :app -am clean verify
```

- `-pl :app` chọn App module.
- `-am` kéo Core và các module upstream được App dùng trong reactor.
- Nếu cả Core và App đã kích hoạt Checkstyle gate qua inheritance/effective POM, cả hai có thể được phân tích.
- Nếu chỉ dùng `-pl :app` mà không có `-am`, Core có thể **không được build**, do đó gate của source Core không chạy trong invocation này.
- Root `packaging=pom` không nhất thiết có Java sources, nên cần chọn rõ phạm vi kiểm tra.
- `pluginManagement` chỉ quản lý version/config khi plugin được dùng, không tự bảo đảm mọi child thực thi goal check.

Checkstyle có reporting goal `checkstyle:checkstyle-aggregate` dành cho báo cáo tổng hợp nhiều modules. **Báo cáo aggregate không tự thay thế gate `checkstyle:check` ở từng module**.

Một multi-module build có thể fail fast ở module đầu không đạt, khiến modules phụ thuộc chưa chạy. Nếu cần reports của tất cả module trong cùng một invocation, hãy cân nhắc reactor failure modes/CI jobs phù hợp; đừng đánh giá “chưa thấy report” thành “0 lỗi”.

## 14. Quality gate policy: ruleset, severity và ngưỡng

Một policy có ích phải xác định rõ:

1. **Ruleset:** tổ chức dùng những rules nào, version Checkstyle/PMD/SpotBugs nào?
2. **Phạm vi:** quét main source, test source, generated source, các modules nào?
3. **Vi phạm chặn:** tất cả findings, severity nào, priority nào?
4. **Threshold:** zero hay baseline cho phép trong giai đoạn chuyển đổi?
5. **Phase:** gate chạy ở validate/test/verify, CI có thực sự đi tới phase đó?
6. **Ngoại lệ:** cách ghi lý do và ngày hết hạn, không tắt rộng không cần thiết.
7. **Artifacts:** báo cáo XML/HTML được lưu để dev sửa khi gate FAIL?
8. **Ownership:** ai duy trì cấu hình và xử lý false positives?

### 14.1. Lộ trình từ báo cáo tới cổng bắt buộc

Với dự án cũ nhiều warnings:

- **Giai đoạn A — report only:** khảo sát findings, không lập tức chặn mọi developer.
- **Giai đoạn B — hiệu chỉnh:** loại rules trùng, sửa false positives, chốt exceptions có lý do.
- **Giai đoạn C — bảo vệ code mới:** đưa một số rules nghiêm trọng vào gate hoặc giảm ngưỡng vi phạm dần.
- **Giai đoạn D — siết chính sách:** hướng tới zero cho những rule đã ổn định, giám sát chặt bypass flags.
- **Giai đoạn E — bảo trì:** nâng plugin versions, rà compatibility, đo tác động thực và kiểm tra lại negative tests.

Không xem việc tăng `maxAllowedViolations` để “build xanh” là sửa vấn đề. Ngưỡng là chính sách tạm hoặc theo rủi ro, không thể thay code review.

### 14.2. Skip flags và profile

Các tham số kiểu `-Dcheckstyle.skip=true` (tùy plugin) có thể tắt analysis. Đừng dùng skip để âm thầm làm một required CI gate PASS.

**Maven profile** có thể bật/tắt plugin execution; CI phải dùng đúng profile. Một build `SUCCESS` sau khi gate bị skip **không tương đương** với PASS do analyzer chạy và không thấy violation.

Cần đặc biệt phân biệt lỗi công cụ:

- **Plugin config error:** file ruleset không tồn tại hoặc XML sai.
- **Dependency/repository error:** không tải được plugin/artifact.
- **Analysis findings:** tool chạy thành công và tìm vi phạm.
- **Quality gate failure:** findings vượt ngưỡng/chính sách nên trả non-zero.

Những lỗi khác nhau cần được ghi log và xử lý khác nhau.

## 15. Tích hợp vào CI

Một job CI có thể chỉ cần gọi đúng Maven lifecycle:

```yaml
name: Java quality gate
on:
  push:
  pull_request:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Compile, test and run quality gate
        run: mvn -B -ntp clean verify
```

Đây là ví dụ GitHub Actions, không phải yêu cầu mọi công ty dùng GitHub. Trên CI thực tế nên ghim action versions/commits theo chính sách supply chain.

**Vì sao `clean verify` quan trọng?** POM mẫu bind Checkstyle vào `verify`. Nếu thay bằng `mvn test`, quality gate không chạy. Nếu Checkstyle FAIL, Maven exit code khác 0 và CI step thường FAIL.

Một pipeline phát hành:

```text
checkout
  |
  v
mvn clean verify
  |
  +-- FAIL -> lưu báo cáo (diagnostic), không deploy
  |
  +-- PASS -> sign/package/publish theo release policy
```

Sau gate FAIL, file JAR có thể vẫn tồn tại ở `target/` vì package chạy trước verify. **Không publish JAR chỉ vì file xuất hiện**; phải đợi required gates PASS.

Khi gate FAIL, CI vẫn có thể upload XML/HTML reports bằng step chạy ngay cả khi các bước trước thất bại; thao tác upload report **không được làm job required đổi thành xanh**.

### 15.1. Server-side quality gates khác Maven-local gates

Một hệ thống như SonarQube có thể nhận analysis từ scanner, xử lý kết quả trên server và đánh giá quality gate sau đó. **Scanner upload thành công không đảm bảo server đã đánh giá PASS**.

Nếu muốn chặn CI theo server-side gate, pipeline phải thực sự lấy/chờ trạng thái gate hoặc dùng integration/status-check theo phiên bản hiện hành. Không đồng nhất scanner exit code với kết quả quality gate, cũng không commit credentials vào POM.

Checkstyle gate của ví dụ là **Maven-local**: goal `checkstyle:check` ngay trong `verify` quyết định Maven BUILD FAILURE. Hai cơ chế có thể kết hợp, nhưng khác thời điểm/quy tắc.

## 16. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| HTML report có violations nhưng `mvn test` PASS | Gate bind ở verify, test chưa tới phase này | Chạy `mvn verify` |
| `mvn site` có report nhưng `mvn verify` không chặn | Chỉ có reporting, thiếu check execution | Bind `checkstyle:check` |
| `mvn verify` vẫn PASS dù có findings | Threshold cho phép, scope khác hoặc gate bị skip | Kiểm tra effective POM và config |
| Unit tests PASS nhưng verify FAIL | Static analysis gate fail, không phải Surefire | Xem goal cuối báo ERROR |
| Rule `ConstantName` không hoạt động | configLocation sai/ruleset khác | Kiểm tra checkstyle.xml và log |
| Plugin báo lỗi parser | Source syntax/Checkstyle-Java compatibility | Sửa source hoặc dùng plugin phù hợp |
| Report và gate đếm khác findings | Reporting/build config khác nhau | Đồng bộ ruleset, source scope, encoding |
| Test source không có trong Checkstyle report | `includeTestSourceDirectory=false` | Bật khi muốn kiểm tra test source |
| Gate không chạy trong selected module | `pluginManagement` chưa kích hoạt hoặc reactor selection khác | Xem effective POM và `-pl/-am` |
| PMD check báo FAIL | Vi phạm vượt threshold/priority | Xem report và `failurePriority` |
| SpotBugs check báo thiếu classes | Bytecode chưa compile | Chạy sau compile và kiểm tra output |
| Không có HTML sau verify | Check goal không đồng nghĩa site report | Chạy reporting goal hoặc `mvn site` |
| Build FAIL do HTTP 429/timeout | Không phân giải plugin/repository | Xử lý network/quota, không gọi là style issue |
| Checkstyle bị skip trong CI | CLI/profile/environment tắt gate | Loại bypass, xác minh execution |
| JAR đã tạo nhưng build đỏ | Package trước verify | Không publish artifact thất bại gate |
| Dashboard báo FAILED nhưng scanner xanh | CI không kiểm tra server-side gate status | Thêm status check/wait |
| Codebase cũ có quá nhiều warnings | Ruleset quá rộng hoặc legacy debt | Tạo baseline, lộ trình giảm |
| Generated code gây nhiều noise | Source scope không rõ | Cấu hình excludes có review |
| Checkstyle/PMD báo lỗi trùng | Overlapping rulesets | Chọn tool owner cho từng quy tắc |

Lệnh chẩn đoán:

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn clean verify
mvn org.apache.maven.plugins:maven-checkstyle-plugin:3.6.0:checkstyle
```

Khi cần log chi tiết:

```bash
mvn -X clean verify
```

Log debug có thể chứa paths, environment data hoặc repository URLs; xem trước khi chia sẻ.

## 17. Bộ test tối thiểu cho chính quality gate

Một gate thật nên có **positive case** và **negative case**:

| Case | Source | Expected compiler/tests | Expected gate |
| --- | --- | --- | --- |
| A | `BASE_VALUE` hợp lệ | Compile PASS, 3 tests PASS | Verify PASS |
| B | Thêm `badName` | Compile PASS, 3 tests PASS | Verify **FAIL** |
| C | Sửa `badName` thành `BAD_NAME` | Compile PASS, 3 tests PASS | Verify PASS |
| D | Chỉ chạy `mvn test` với `badName` | Compile PASS, 3 tests PASS | **Gate chưa chạy** |

Thêm một thử nghiệm report:

```bash
mvn org.apache.maven.plugins:maven-checkstyle-plugin:3.6.0:checkstyle
```

Nó có thể tạo report có finding `badName` mà không làm build fail, còn:

```bash
mvn clean verify
```

phải fail khi `failOnViolation=true`, `maxAllowedViolations=0` và rule đang được áp dụng. Đây là cách phát hiện pipeline báo cáo nhưng không có **bước chặn build thực sự**.

## 18. Bài tập thực hành

1. Giải thích khác biệt giữa analyzer report và policy gate.
2. Phân biệt `checkstyle:checkstyle` với `checkstyle:check`.
3. Chỉ ra hai nhánh `<build>` và `<reporting>` trong POM mẫu, vì sao cả hai cùng dùng `checkstyle.xml`?
4. Tạo đủ các file POM, checkstyle.xml, Calculator.java, App.java và CalculatorTest.java.
5. Chạy `mvn clean verify`, kiểm tra ba tests PASS và Checkstyle gate PASS.
6. Chạy `java -cp target/classes dev.course.App` và ghi stdout chính xác.
7. Thêm field `badName` vào Calculator, chạy `mvn clean test`. Vì sao Maven vẫn có thể SUCCESS?
8. Chạy reporting goal, tìm vi phạm trong XML/HTML report.
9. Chạy `mvn clean verify`, xác định goal gây BUILD FAILURE và nguyên nhân.
10. Khi gate FAIL nhưng JAR đã có dưới `target/`, pipeline được phép deploy ngay không?
11. Đặt `maxAllowedViolations=2`; dự đoán hành vi khi có 0, 1, 2, 3 violations.
12. PMD `failurePriority=3` khác 5 thế nào?
13. Tại sao SpotBugs thường cần bytecode đã compile?
14. Một JaCoCo coverage gate có phải static analysis source không?
15. Một CI chỉ chạy `mvn package` có kích hoạt Checkstyle gate ở verify không?
16. Làm cách nào xác định effective execution của Checkstyle trong module con?
17. Vì sao `checkstyle:checkstyle-aggregate` không thay thế per-module gate?
18. Nếu server-side quality dashboard FAIL nhưng scanner trả 0, CI còn thiếu bước nào?
19. Phân biệt plugin configuration error với policy violation.
20. Tại sao cần chạy negative test đối với quality gate trong CI?

## 19. Tổng kết

**Static analysis** giúp phát hiện vấn đề từ source/bytecode. **Report** chỉ cung cấp findings; **quality gate** biến một bộ findings thành kết quả PASS/FAIL có khả năng chặn Maven build.

Trong Maven:

- Checkstyle: `checkstyle:checkstyle` tạo report; `checkstyle:check` thực thi gate.
- PMD: `pmd:pmd` tạo report; `pmd:check` thực thi gate.
- SpotBugs: `spotbugs:spotbugs` phân tích bytecode; `spotbugs:check` có thể chặn build.
- Muốn tự động chặn, bind check goal vào lifecycle (thường `verify`) trong `build/plugins/executions`. Chỉ khai báo `reporting` không đủ.
- Test PASS không đồng nghĩa static gate PASS; JAR đã tạo không đồng nghĩa artifact được phép publish.

Ví dụ Java 17 chứng minh **3 tests PASS** trong khi Checkstyle gate **FAIL** vì constant `badName`. Kết quả là một pipeline đáng tin phải xác minh **goal thực sự chạy**, **rule và ngưỡng đúng**, và **negative test thật sự chặn build**.

## 20. Tài liệu chính thức

- [Maven Checkstyle Plugin — Usage: reports và checking for violations](https://maven.apache.org/plugins/maven-checkstyle-plugin/usage.html)
- [Maven Checkstyle Plugin — checkstyle:check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
- [Maven Checkstyle Plugin — checkstyle:checkstyle](https://maven.apache.org/plugins/maven-checkstyle-plugin/checkstyle-mojo.html)
- [Maven Checkstyle Plugin — FAQ](https://maven.apache.org/plugins/maven-checkstyle-plugin/faq.html)
- [Maven PMD Plugin — pmd:check](https://maven.apache.org/plugins/maven-pmd-plugin/check-mojo.html)
- [Maven PMD Plugin — pmd:pmd](https://maven.apache.org/plugins/maven-pmd-plugin/pmd-mojo.html)
- [Maven PMD Plugin — Usage](https://maven.apache.org/plugins/maven-pmd-plugin/usage.html)
- [SpotBugs Maven Plugin — spotbugs:check](https://spotbugs.github.io/spotbugs-maven-plugin/check-mojo.html)
- [Maven Site Plugin](https://maven.apache.org/plugins/maven-site-plugin/)
- [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
