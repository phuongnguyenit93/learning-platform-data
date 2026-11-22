# Gắn unit test, integration test và cổng chất lượng vào `mvn verify`

## 1. Mục tiêu: một lệnh build phải có ý nghĩa kiểm chứng rõ ràng

Trong một dự án Maven, dòng `BUILD SUCCESS` chỉ đáng tin nếu người đọc biết **những gì thực sự đã chạy**. Một dự án có thể biên dịch được nhưng unit tests chưa được chọn đúng tên; integration tests có thể nằm ở `src/test/java` nhưng không có Failsafe execution; một báo cáo JaCoCo có thể tồn tại trong `target` từ lần build trước; Checkstyle có thể chỉ được cấu hình trong `<reporting>` nên không làm build thất bại.

Đề bài **“Gắn unit test, integration test và cổng chất lượng vào verify”** hướng đến một pipeline mà lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

làm được đồng thời:

1. Kiểm Maven/JDK đã đạt mức tối thiểu.
2. Compile project Java 17.
3. Chạy **unit tests** bằng Maven Surefire Plugin, fail nếu không tìm thấy tests.
4. Package artifact.
5. Chạy **integration tests** bằng Maven Failsafe Plugin.
6. Đến `verify` mới kết luận IT pass/fail, cho phép phase teardown ở trước đó.
7. Ghi số liệu coverage qua JaCoCo agent ở các forked test JVMs.
8. Tạo báo cáo coverage và **fail build nếu không đạt ngưỡng**.
9. Kiểm quy tắc Java source style với Checkstyle, **fail nếu có vi phạm**.
10. Cho CI thu kết quả từng cổng và chỉ cho phép merge/release khi các required checks thành công.

Bài sử dụng **Java 17, Maven 3.9+, JUnit Jupiter 5.11.4**. Ví dụ pin **Compiler 3.16.0, Surefire/Failsafe 3.6.1, JaCoCo 0.8.16, Checkstyle 3.6.0 và Enforcer 3.6.3**. Đây là các phiên bản đã đối chiếu với tài liệu chính thức ở thời điểm viết; tổ chức cần dùng approved plugin versions và giữ nguyên toàn bộ suite khi nâng version.

**Kết quả kiểm chứng trong lab:** bốn unit test methods và bảy integration test methods, tổng **11 JUnit methods**. Phần Java ứng dụng in chính xác `Processed 2 row(s).` khi chuyển đổi một file CSV mẫu. Một lần `verify` thành công có thể tạo Surefire/Failsafe reports, JaCoCo HTML/XML và Checkstyle report; tất cả các gates được cấu hình có khả năng khiến build fail.

## 2. `verify` không phải một plugin goal duy nhất

Maven lifecycle chuẩn cho project `jar` đi qua các phases theo thứ tự. Những điểm liên quan:

~~~text
validate
  |-- enforcer:enforce                 (kiểm Maven/JDK)
initialize
  |-- jacoco:prepare-agent             (đặt argLine cho test JVMs)
process-resources
compile
  |-- compiler:compile
test-compile
  |-- compiler:testCompile
test
  |-- surefire:test                    (unit tests)
package
  |-- jar:jar
pre-integration-test
  |-- tùy chọn: khởi động hạ tầng IT
integration-test
  |-- failsafe:integration-test        (IT execution)
post-integration-test
  |-- tùy chọn: dọn hạ tầng IT
verify
  |-- failsafe:verify                  (kiểm kết quả IT)
  |-- jacoco:report                    (tạo coverage reports)
  |-- jacoco:check                     (kiểm coverage thresholds)
  |-- checkstyle:check                 (kiểm source style)
~~~

Đây là **sơ đồ logic cho cấu hình POM của bài**, không phải mọi Maven project đều tự có tất cả goals đó. Maven `jar` packaging có default bindings cho compiler/test/package, nhưng **Failsafe, JaCoCo coverage gate, Checkstyle và Enforcer phải được kết nối/config rõ**.

Với `mvn verify`, Maven đi qua tất cả phases trước `verify` rồi chạy goals gắn vào chúng. Lệnh `mvn test` **không đi đến** `integration-test`, `post-integration-test` và `verify`. Lệnh `mvn package` cũng không đi đến `verify`. Nếu cổng chất lượng bị bind ở phase `verify`, chỉ chạy `package` để kết luận toàn bộ QA pass là **không đúng**.

### 2.1. Khi fail sớm thì điều gì xảy ra?

Nếu compilation hoặc unit tests fail ở phase `test`, Maven dừng trước khi chạy Failsafe IT và các cổng `verify` ở sau. Điều này là bình thường: pipeline chưa đủ điều kiện tiếp tục.

Nếu Failsafe IT có assertion failure, thiết kế Failsafe **trì hoãn báo thất bại của integration test đến goal `failsafe:verify`**, để `post-integration-test` vẫn có cơ hội dọn môi trường. Không diễn giải cơ chế này thành “integration tests được phép fail”; ở `verify`, lỗi vẫn phải khiến build fail.

Nếu JVM/CI job bị kill, hoặc một plugin khác fail trước `post-integration-test`, cleanup lifecycle **không được bảo đảm tuyệt đối**. Các tài nguyên bên ngoài vẫn cần cleanup/TTL/try-finally ở tầng phù hợp.

## 3. Phân vai bốn lớp test và cổng chất lượng

| Lớp | Plugin / rule | Câu hỏi trả lời | Vị trí trong lifecycle |
| --- | --- | --- | --- |
| Unit tests | Surefire | Hàm/đối tượng cho đúng kết quả trong bộ nhớ không? | `test` |
| Integration tests | Failsafe | Các thành phần kết hợp với filesystem/service/repository có hoạt động không? | `integration-test`, kết luận tại `verify` |
| Coverage | JaCoCo | Có bao nhiêu line/branch của production bytecode được thực thi? | Agent từ `initialize`, `report`/`check` ở `verify` |
| Static style | Checkstyle | Source có vi phạm bộ quy tắc đã khai báo không? | `verify` |
| Environment gate | Enforcer | Toolchain Maven/JDK có đúng baseline không? | `validate` |

Coverage cao **không đồng nghĩa tests tốt**: một test gọi toàn bộ code nhưng không assert kết quả có thể đạt coverage cao mà không phát hiện regression. Checkstyle chỉ kiểm những quy tắc tĩnh được bật; nó không chứng minh behavior, bảo mật, license hoặc architecture đúng.

**Quan hệ đúng:** unit tests và IT cung cấp assertions; JaCoCo bổ sung tín hiệu về vùng chưa được test; Checkstyle và Enforcer giảm lỗi cấu hình/chất lượng source; tất cả được kiểm tại CI, không dùng một chỉ số thay cho toàn bộ các lớp.

## 4. Quy ước tên test: đừng để một test rơi khỏi cả hai plugin

Maven Surefire mặc định phát hiện các dạng tên tương đương:
- `TaskReportTest.java`.
- `TaskReportTests.java`.
- `TestTaskReport.java`.
- `TaskReportTestCase.java`.

Failsafe mặc định phát hiện các dạng:
- `TaskReportIT.java`.
- `ITTaskReport.java`.
- `TaskReportITCase.java`.

Trong lab, đặt **unit tests** ở:

~~~text
src/test/java/com/example/quality/TaskReportTest.java
~~~

và **integration tests** ở:

~~~text
src/test/java/com/example/quality/TaskReportIT.java
~~~

Cả hai vẫn nằm dưới `src/test/java` nên được **biên dịch ở phase `test-compile`**, nhưng **plugin thực thi và phase khác nhau**. Failsafe không tự chạy chỉ vì tên `IT` tồn tại; nó phải có execution được bind.

### 4.1. Tên test có thể khiến QA xanh giả như thế nào?

Nếu chỉ đổi `TaskReportIT.java` thành `TaskReportIntegration.java` mà không điều chỉnh includes, Failsafe mặc định **không chọn class này**. Nếu `failIfNoTests=false`, build có thể không phát hiện thiếu IT. Demo đặt `failIfNoTests=true` cho cả Surefire và Failsafe, nên thiếu toàn bộ suite tương ứng là một lỗi cứng.

**Giới hạn cần hiểu:** `failIfNoTests=true` phát hiện **không có tests nào được tìm thấy** bởi một plugin, không chứng minh mọi test case dự kiến đều chạy. Ví dụ có 8 IT classes nhưng chỉ còn 1 class được chọn, cổng vẫn có thể pass. CI nên so test counts, reports và contract tests theo policy.

### 4.2. `@Test` không thay quy tắc class naming

JUnit Jupiter `@Test` đánh dấu method test cho engine. Maven Surefire/Failsafe trước hết chọn test classes bằng patterns, sau đó provider/JUnit engine thực thi methods. Một test class có annotation đúng nhưng tên không match và chưa cấu hình includes có thể bị bỏ qua.

Không lấy việc IDE có nút “Run Test” chạy được làm bằng chứng rằng `mvn verify` đã chạy test đó.

## 5. Chọn tình huống integration test không cần server ngoài

Lab dùng nghiệp vụ nhỏ: nhận một file CSV gồm các dòng `name,quantity`, chuẩn hóa tên và ghi một file report. Các thành phần:

~~~text
Input CSV on filesystem
        |
        v
TaskReport.convert(input, output)
  +-- đọc UTF-8 file
  +-- bỏ qua dòng trắng
  +-- parse CSV tối giản: name,quantity
  +-- TaskReport.format(name, quantity)
  +-- ghi UTF-8 report
        |
        v
Output file: APPLE:2, ORANGE:3
~~~

**Unit test** chỉ gọi `TaskReport.format`, không cần filesystem. **Integration test** tạo file thật trong `@TempDir`, dùng `TaskReport.convert`/`main`, rồi đọc file output để assert toàn bộ luồng đọc–parse–transform–ghi.

Đây là **integration test theo ranh giới file I/O**, phù hợp cho lab tự chạy không cần database/HTTP container. Trong dự án production, IT có thể kiểm với database test, message broker, REST service hoặc Testcontainers; điều đó cần thêm provisioning, isolation và cleanup.

Không tuyên bố lab này đã kiểm tương tác database hoặc external APIs, vì nó không hề dùng chúng.

## 6. Cấu trúc project Java 17 hoàn chỉnh

~~~text
verify-quality-lab/
├── pom.xml
├── checkstyle.xml
└── src/
    ├── main/
    │   └── java/com/example/quality/
    │       └── TaskReport.java
    └── test/
        └── java/com/example/quality/
            ├── TaskReportTest.java
            └── TaskReportIT.java
~~~

Không cần Docker, internal repository hoặc secrets. Maven có thể cần kết nối artifact repository để tải plugin/JUnit/JaCoCo/Checkstyle lần đầu. Nếu môi trường doanh nghiệp dùng mirror, cấu hình trong Maven settings có quyền phù hợp, không copy token vào project POM.

## 7. `pom.xml`: tất cả cổng nối vào lifecycle

Tạo `verify-quality-lab/pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.quality</groupId>
    <artifactId>verify-quality-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <argLine></argLine>
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
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>require-build-toolchain</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>@{argLine}</argLine>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>@{argLine}</argLine>
                </configuration>
                <executions>
                    <execution>
                        <id>integration-tests-and-verification</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.16</version>
                <executions>
                    <execution>
                        <id>attach-coverage-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                        <configuration>
                            <append>true</append>
                        </configuration>
                    </execution>
                    <execution>
                        <id>coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>coverage-quality-gate</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                        <configuration>
                            <haltOnFailure>true</haltOnFailure>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.80</minimum>
                                        </limit>
                                        <limit>
                                            <counter>BRANCH</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.60</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>checkstyle.xml</configLocation>
                    <encoding>UTF-8</encoding>
                    <includeTestSourceDirectory>true</includeTestSourceDirectory>
                    <consoleOutput>true</consoleOutput>
                    <failOnViolation>true</failOnViolation>
                </configuration>
                <executions>
                    <execution>
                        <id>style-quality-gate</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.1. Tại sao không cấu hình Failsafe vào phase `test`?

Phase `test` thuộc Surefire unit suite. Để cleanup IT đúng, Failsafe phải có:
- Goal `integration-test` ở phase `integration-test`.
- Goal `verify` ở phase `verify`.

Với mặc định goal bindings của Failsafe 3.6.1, khai báo hai goals trong một execution như POM trên là đủ; mỗi goal có default phase riêng. Đối với dự án yêu cầu kiểm soát chặt hơn, có thể tách thành hai executions và ghi `<phase>` tường minh.

**Chỉ khai báo plugin version không làm integration tests chạy.** Execution là phần quyết định.

### 7.2. Thứ tự goals ở phase `verify`

POM đặt Failsafe trước JaCoCo và Checkstyle. Khi các executions được bind cùng phase và plan được Maven dựng từ POM này, ý định là:
1. `failsafe:verify` xác nhận IT.
2. `jacoco:report` tạo báo cáo.
3. `jacoco:check` áp coverage threshold.
4. `checkstyle:check` áp style rules.

Nếu `failsafe:verify` fail thì các goals sau có thể chưa chạy. **Đây là fail-fast bình thường**, không phải coverage/Checkstyle đã pass. CI cần ghi nguyên nhân đầu tiên và không gộp các goals chưa chạy vào danh sách “passed gates”.

### 7.3. JaCoCo `argLine` được truyền vào cả hai test JVMs

JaCoCo `prepare-agent` chạy từ phase `initialize`, thiết lập Maven property `argLine` chứa tham số Java agent. Vì Surefire/Failsafe **fork JVM** với `forkCount=1`, hai plugins cần dùng giá trị mới.

Đoạn:

~~~xml
<argLine>@{argLine}</argLine>
~~~

dùng **late property evaluation** của Surefire/Failsafe, thay vì Maven model interpolation quá sớm. `@{argLine}` được thay khi plugin chạy; `<argLine></argLine>` trong `<properties>` là giá trị rỗng dự phòng nếu không có agent.

**Không viết** `<argLine>-Xmx512m</argLine>` đè mất JaCoCo agent. Nếu cần JVM options thêm, dùng:

~~~xml
<argLine>@{argLine} -Xmx512m</argLine>
~~~

Đây là **fragment tùy chọn**, chỉ thay dòng `argLine` ở từng plugin; không tạo một POM thứ hai.

### 7.4. Vì sao pin plugin versions?

Plugin defaults của Maven có thể đổi theo Maven distribution, repositories và lifecycle bindings. Khi QA phải tái hiện được:
- Compiler `--release 17`.
- Surefire và Failsafe cùng family/provider tương thích JUnit 5.
- JaCoCo agent và report hiểu bytecode JDK đang dùng.
- Checkstyle checker rules giống nhau giữa local và CI.
- Enforcer toolchain range không bị bỏ qua.

Định kỳ nâng versions có kiểm tra, nhưng tránh đặt `LATEST`/range động trong production POM nếu đang cần reproducibility.

## 8. `checkstyle.xml` tối giản và có thể chạy

Tạo file `verify-quality-lab/checkstyle.xml` tại root, cùng cấp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
        "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
        "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="FileTabCharacter">
        <property name="eachLine" value="true"/>
    </module>

    <module name="NewlineAtEndOfFile"/>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
~~~

Quy tắc demo:
- `FileTabCharacter`: không dùng tab trong source.
- `NewlineAtEndOfFile`: file cần newline cuối.
- `AvoidStarImport`: không dùng wildcard imports.

Đây là **bộ rules tối giản cho bài học**, không phải chuẩn coding style đầy đủ cho hệ thống lớn. Khi team muốn Google/Sun style hoặc custom conventions, thay `checkstyle.xml` bằng bản đã review, không âm thầm biến một style rule thành tiêu chí chất lượng nghiệp vụ.

Dòng `<includeTestSourceDirectory>true</includeTestSourceDirectory>` trong POM yêu cầu Checkstyle xét cả production và test Java files. Nếu bỏ dòng này, Checkstyle Plugin có default không kiểm tất cả test sources như người dùng dễ suy đoán.

### 8.1. Tại sao chọn `checkstyle:check` thay vì chỉ `checkstyle:checkstyle`?

`checkstyle:checkstyle` chủ yếu dành cho report. Goal `checkstyle:check` kiểm violations và có thể **làm Maven build fail**. Cấu hình ở `<reporting>` chỉ định report cho Maven Site không đảm bảo enforcement trong standard `mvn verify`.

POM lab gắn:

~~~xml
<execution>
    <id>style-quality-gate</id>
    <phase>verify</phase>
    <goals>
        <goal>check</goal>
    </goals>
</execution>
~~~

và `failOnViolation=true`. Đây là phần chuyển một report thành **cổng chất lượng bắt buộc**.

## 9. `TaskReport.java`: chương trình Java 17 hoàn chỉnh

Tạo `src/main/java/com/example/quality/TaskReport.java`:

~~~java
package com.example.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class TaskReport {

    private TaskReport() {
    }

    public static String format(String item, int quantity) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException(
                    "item must not be blank");
        }

        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "quantity must not be negative");
        }

        String normalized = item.strip()
                .toUpperCase(Locale.ROOT);
        return normalized + ":" + quantity;
    }

    public static int convert(Path input, Path output)
            throws IOException {

        List<String> raw = Files.readAllLines(
                input, StandardCharsets.UTF_8);
        List<String> converted = new ArrayList<>();

        for (String row : raw) {
            if (row.isBlank()) {
                continue;
            }

            String[] fields = row.split(",", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException(
                        "Expected name,quantity");
            }

            int quantity = Integer.parseInt(
                    fields[1].strip());
            converted.add(format(fields[0], quantity));
        }

        Files.write(output, converted, StandardCharsets.UTF_8);
        return converted.size();
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: TaskReport INPUT OUTPUT");
        }

        int processed = convert(
                Path.of(args[0]), Path.of(args[1]));
        System.out.println(
                "Processed " + processed + " row(s).");
    }
}
~~~

**Giải thích:**
- `format` là logic thuần, phù hợp unit tests.
- `convert` tích hợp file I/O, parser và formatter, phù hợp IT.
- `Files.readAllLines` đọc toàn bộ file vào RAM. Đây là lab cho input nhỏ, **không tối ưu** cho CSV nhiều GB.
- `row.split(",", -1)` là parser hai cột tối giản. Nó **không hỗ trợ đầy đủ chuẩn CSV** như trường quoted có dấu phẩy, escaped quotes hoặc newline trong field. Production nên dùng parser CSV thư viện phù hợp.
- `Integer.parseInt` ném `NumberFormatException` cho quantity không hợp lệ; đó là expected validation error trong lab.
- `Files.write` ghi file, nhưng không áp dụng atomic replace policy; với hệ thống sản xuất nên thêm temp file/atomic move khi nghiệp vụ yêu cầu.
- `Locale.ROOT` giữ việc uppercasing độc lập hơn với default locale của máy chạy.
- `main` in một thông điệp thành công sau khi convert hoàn tất; không gọi `System.exit` trong tests.
- Không có credentials, network, clock, random hoặc global mutable state.

## 10. Unit tests: `TaskReportTest.java`

Tạo `src/test/java/com/example/quality/TaskReportTest.java`:

~~~java
package com.example.quality;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskReportTest {

    @Test
    void formatsAndNormalizesName() {
        assertEquals("APPLE:2",
                TaskReport.format(" apple ", 2));
    }

    @Test
    void handlesZeroQuantity() {
        assertEquals("ORANGE:0",
                TaskReport.format("orange", 0));
    }

    @Test
    void rejectsMissingName() {
        assertThrows(IllegalArgumentException.class,
                () -> TaskReport.format(null, 1));
        assertThrows(IllegalArgumentException.class,
                () -> TaskReport.format("   ", 1));
    }

    @Test
    void rejectsNegativeQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> TaskReport.format("apple", -1));

        assertEquals("quantity must not be negative",
                error.getMessage());
    }
}
~~~

Có chính xác **4 unit test methods**.

**Tính chất unit:**
- Không đụng filesystem/network/database.
- Mỗi test gọi một public function và assert kết quả/exception.
- Không lệ thuộc `target/`, shell hay directory hiện hành.
- Chạy nhanh và deterministic theo cùng JDK.

Một lần `mvn test` sau khi đã tải plugins/dependencies có thể thực thi bốn tests này, nhưng **chưa có nghĩa IT hoặc coverage gate ở `verify` đã chạy**.

## 11. Integration tests: `TaskReportIT.java`

Tạo `src/test/java/com/example/quality/TaskReportIT.java`:

~~~java
package com.example.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskReportIT {

    @TempDir
    Path tempDir;

    @Test
    void convertsRealInputFileToReport() throws IOException {
        Path input = tempDir.resolve("orders.csv");
        Path output = tempDir.resolve("report.txt");

        Files.writeString(input,
                " apple ,2\norange,3\n\n",
                StandardCharsets.UTF_8);

        int count = TaskReport.convert(input, output);

        assertEquals(2, count);
        assertEquals(
                List.of("APPLE:2", "ORANGE:3"),
                Files.readAllLines(
                        output, StandardCharsets.UTF_8));
    }

    @Test
    void rejectsMalformedRow() throws IOException {
        Path input = tempDir.resolve("bad.csv");
        Path output = tempDir.resolve("unused.txt");

        Files.writeString(input,
                "wrong-format\n", StandardCharsets.UTF_8);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> TaskReport.convert(input, output));

        assertEquals("Expected name,quantity",
                error.getMessage());
    }

    @Test
    void rejectsNegativeQuantityInInput() throws IOException {
        Path input = tempDir.resolve("negative.csv");
        Path output = tempDir.resolve("unused.txt");

        Files.writeString(input,
                "apple,-1\n", StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> TaskReport.convert(input, output));
    }

    @Test
    void rejectsNonNumericQuantity() throws IOException {
        Path input = tempDir.resolve("letters.csv");
        Path output = tempDir.resolve("unused.txt");

        Files.writeString(input,
                "orange,three\n", StandardCharsets.UTF_8);

        assertThrows(NumberFormatException.class,
                () -> TaskReport.convert(input, output));
    }

    @Test
    void reportsMissingInputAsIoFailure() {
        Path missing = tempDir.resolve("missing.csv");
        Path output = tempDir.resolve("unused.txt");

        assertThrows(IOException.class,
                () -> TaskReport.convert(missing, output));
    }

    @Test
    void mainIntegratesWithFilesystem() throws IOException {
        Path input = tempDir.resolve("one.csv");
        Path output = tempDir.resolve("one.txt");

        Files.writeString(input,
                "pear,5\n", StandardCharsets.UTF_8);

        TaskReport.main(new String[]{
                input.toString(), output.toString()
        });

        assertEquals(
                List.of("PEAR:5"),
                Files.readAllLines(
                        output, StandardCharsets.UTF_8));
    }

    @Test
    void mainRejectsWrongArgumentCount() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> TaskReport.main(new String[0]));

        assertEquals("Usage: TaskReport INPUT OUTPUT",
                error.getMessage());
    }
}
~~~

Có đúng **7 integration test methods**. JUnit 5 `@TempDir` giúp mỗi test dùng thư mục riêng để giảm tranh chấp file. Không sử dụng fixed port hay shared database. Filesystem behavior được kiểm thật, không mock `Files`.

### 11.1. Vì sao có `IOException` trong signature của một số tests?

Các phương thức gọi `Files.writeString`/`Files.readAllLines` có thể ném checked `IOException`; JUnit 5 cho phép test method khai báo `throws IOException`. Các assertions cho error path dùng `assertThrows` và lambda có thể ném exception, không phải bắt thủ công rồi bỏ lỗi.

### 11.2. Vì sao integration test cũng nằm ở `src/test/java`?

Đây là thiết kế Maven thông dụng: `maven-compiler-plugin:testCompile` compile tất cả Java test sources; Surefire/Failsafe quyết định **thực thi lớp nào ở phase nào**. Nếu project dùng `src/it/java` thay thế, phải cấu hình `build-helper-maven-plugin` hoặc test sources riêng; không tự cho rằng Maven mặc định compile thư mục đó.

### 11.3. Một test gọi `main` có làm hỏng output trong CI không?

`mainIntegratesWithFilesystem()` gọi `main` với một dòng input, vì vậy nó có thể in `Processed 1 row(s).` vào Surefire/Failsafe logs hoặc XML. Đây là output **của một test**, không phải stdout của lệnh chạy chương trình CSV mẫu ở phần sau. Test assert **file output**, tránh dựa vào thứ tự log khi CI chạy tests song song.

## 12. Chạy lab và quan sát toàn bộ cổng

Trước tiên kiểm toolchain:

~~~bash
mvn -version
java -version
javac -version
~~~

Đứng tại folder `verify-quality-lab/` chứa `pom.xml`, chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu Maven 3.9+, Java17+ và dependencies/plugins resolve được, kỳ vọng:

- Enforcer xác nhận Maven/JDK requirements.
- Java source/test source compile thành công.
- Surefire chạy **4 unit tests**.
- JAR được package ở `target/verify-quality-lab-1.0.0.jar`.
- Failsafe chạy **7 integration tests**.
- Failsafe `verify` đọc summary và pass.
- JaCoCo tạo `target/jacoco.exec` và report, kiểm ngưỡng **LINE ≥ 80%** và **BRANCH ≥ 60%** trên bundle.
- Checkstyle kiểm Java production + tests theo file `checkstyle.xml`.
- Maven trả exit code 0 và `BUILD SUCCESS` nếu tất cả bước có trong execution plan đều pass.

Không trông chờ thứ tự từng dòng trong Maven log giống tuyệt đối: log formatting, download messages, Java version và plugin versions có thể thêm thông tin khác. **Không tuyên bố đã chạy kiểm thử trong bài viết**; đây là quy trình/kết quả kỳ vọng cho người học thực hành.

### 12.1. Chạy chương trình với input mẫu

Trên Linux/macOS:

~~~bash
printf ' apple ,2\norange,3\n' > input.csv
java -cp target/classes com.example.quality.TaskReport input.csv output.txt
cat output.txt
~~~

Stdout **chính xác từ lệnh `java`**:

~~~text
Processed 2 row(s).
~~~

Nội dung file `output.txt` (không bao gồm stdout trên):

~~~text
APPLE:2
ORANGE:3
~~~

`java -cp target/classes` dùng compiled classes của project. JAR demo là JAR thường chưa cấu hình `Main-Class` manifest, vì vậy **không dùng `java -jar target/verify-quality-lab-1.0.0.jar`** để chạy CLI nếu chưa thêm manifest.

### 12.2. Tạo input UTF-8 không BOM trên Windows PowerShell

Trên Windows PowerShell 5.1, tránh một số `Set-Content -Encoding UTF8` có thể tạo UTF-8 BOM ảnh hưởng đến parser đơn giản. Thay bằng:

~~~powershell
$inputPath = Join-Path (Get-Location) "input.csv"
$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $inputPath,
    " apple ,2`norange,3`n",
    $encoding
)

java -cp target/classes com.example.quality.TaskReport input.csv output.txt
Get-Content output.txt
~~~

Java stdout vẫn `Processed 2 row(s).`, và `Get-Content` in hai dòng `APPLE:2`, `ORANGE:3`.

Vì parser demo không xử lý CSV quoted fields/BOM, production không nên sao chép parser tối giản này cho dữ liệu khách hàng. Chủ đích ở đây là **pipeline QA và integration test lifecycle**.

## 13. Surefire: kiểm unit tests đã thực thi thật

Maven Surefire mặc định tạo báo cáo dưới:

~~~text
target/surefire-reports/
    com.example.quality.TaskReportTest.txt
    TEST-com.example.quality.TaskReportTest.xml
~~~

Khi chạy đúng, `TaskReportTest` có 4 tests, không failures/errors. Báo cáo có thể bổ sung properties/time/stdout, không dùng chúng như định dạng log cố định.

`failIfNoTests=true` khiến build fail nếu Surefire không phát hiện test nào. Nhưng nếu project có cả nhiều modules mà một module không có unit test, việc bật cờ này ở POM parent cho mọi module **có thể sai**. Trong Reactor thực tế, áp cờ cho modules có hợp đồng bắt buộc có tests, hoặc đặt policy cho aggregator/POM-only modules riêng.

### 13.1. `mvn test` kiểm được gì?

~~~bash
mvn -B -ntp clean test
~~~

Lệnh sẽ đi qua unit test phase. **Chưa đi qua Failsafe IT và verify gates**. Dùng trong vòng lặp developer nhanh là hợp lý; không sử dụng nó làm thay thế required CI `clean verify`.

### 13.2. `-Dtest` chỉ chọn một subset

~~~bash
mvn -B -ntp -Dtest=TaskReportTest test
~~~

Dùng khi debug một class; nó **không phải full quality gate**. Nếu CI chính thức luôn chạy `-Dtest=...`, các tests khác có thể không được thực thi, dù command trả success.

## 14. Failsafe: IT không nên làm dừng build trước teardown

Maven Failsafe Plugin có hai goals chính:

~~~xml
<goals>
    <goal>integration-test</goal>
    <goal>verify</goal>
</goals>
~~~

`failsafe:integration-test` thực thi IT và ghi report/summary, rồi Maven có thể chạy `post-integration-test`. `failsafe:verify` kiểm kết quả để fail build nếu IT không đạt.

Nếu thay Failsafe bằng việc bind `surefire:test` trực tiếp vào `integration-test`, một test failure có thể làm lifecycle dừng **trước phase cleanup**. Failsafe được thiết kế để tránh lỗi triển khai này.

### 14.1. `mvn integration-test` chưa phải gate cuối

~~~bash
mvn -B -ntp integration-test
~~~

Lệnh dừng ngay sau phase `integration-test`, **không chạy `post-integration-test` hoặc Failsafe `verify`**. Đây là một bẫy quan trọng: IT có thể fail nhưng status chưa được kiểm theo semantics Failsafe hoàn chỉnh. CI phải chạy:

~~~bash
mvn -B -ntp verify
~~~

Trong lab, không có service để start/stop nên issue cleanup ít rõ. Tuy nhiên vẫn cần duy trì cấu hình đúng cho lúc chuyển sang Docker/database/HTTP IT thật.

### 14.2. Báo cáo Failsafe

Khi chạy đúng:

~~~text
target/failsafe-reports/
    com.example.quality.TaskReportIT.txt
    TEST-com.example.quality.TaskReportIT.xml
    failsafe-summary.xml
~~~

`failsafe-summary.xml` là dữ liệu Failsafe `verify` đọc để kết luận suite. Khi error, xem nội dung XML/text report trước khi suy đoán plugin fail.

## 15. JaCoCo: agent chạy cả unit và IT JVMs

Cấu hình JaCoCo trong POM:

~~~xml
<execution>
    <id>attach-coverage-agent</id>
    <goals>
        <goal>prepare-agent</goal>
    </goals>
    <configuration>
        <append>true</append>
    </configuration>
</execution>
~~~

JaCoCo `prepare-agent` mặc định bind ở `initialize`, tạo `argLine` cho JVM test. Cả Surefire và Failsafe được cấu hình `@{argLine}`, nên thực thi test bytecode được JaCoCo instrumentation/measurement.

Dùng chung default output:

~~~text
target/jacoco.exec
~~~

`append=true` cho phép execution data từ unit-test và IT forks bổ sung vào file, thay vì IT ghi đè dấu vết unit tests. Đây là lựa chọn minh họa cho một project đơn module, chạy suites tuần tự theo lifecycle.

**Đừng dùng cùng file JaCoCo `.exec` giữa hai Maven processes hoặc CI jobs độc lập ghi đồng thời trên một shared workspace**. Cần isolated workspaces/build directories, hoặc quy trình merge data files phù hợp.

### 15.1. JaCoCo đo cái gì?

- `LINE` coverage: tỷ lệ source lines có executable instructions được đánh dấu covered.
- `BRANCH` coverage: tỷ lệ branch outcomes của bytecode control flow được chạm tới.
- `INSTRUCTION` coverage: bytecode instructions được thực thi.

Coverage không phải tỷ lệ “số tests đã pass”. Một test có thể execute nhiều lines mà assert sai, trong khi coverage vẫn ghi nhận line được chạy.

### 15.2. Cổng JaCoCo trong ví dụ

~~~xml
<rules>
    <rule>
        <element>BUNDLE</element>
        <limits>
            <limit>
                <counter>LINE</counter>
                <value>COVEREDRATIO</value>
                <minimum>0.80</minimum>
            </limit>
            <limit>
                <counter>BRANCH</counter>
                <value>COVEREDRATIO</value>
                <minimum>0.60</minimum>
            </limit>
        </limits>
    </rule>
</rules>
~~~

Đây là **fragment** đã có trong POM đầy đủ. Nếu ratio dưới một trong hai ngưỡng, `jacoco:check` với `haltOnFailure=true` làm build fail.

Ngưỡng 80% line và 60% branch là **mức minh họa của lab**, không phải chuẩn bắt buộc cho mọi domain. Với code critical, team có thể cần giới hạn riêng theo package/class, mutation tests hoặc coverage diff cho code mới. Chọn gate sao cho bắt regression nhưng không khuyến khích viết tests vô nghĩa để chạy theo chỉ số.

### 15.3. Report khác check

`jacoco:report` tạo HTML/XML/CSV theo cấu hình mặc định. `jacoco:check` đánh giá thresholds. **Một báo cáo HTML đẹp không tự fail CI** nếu bạn chưa bind `check` hoặc chưa đặt rule.

Các paths mong đợi:

~~~text
target/jacoco.exec
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
target/site/jacoco/jacoco.csv
~~~

Đây là kết quả kỳ vọng khi agent có data và report goal chạy bình thường. Nếu `.exec` không có vì test JVM không fork đúng/agent chưa attach, một số JaCoCo goals có thể **skip do thiếu execution data**, không nhất thiết làm build fail theo cách người đọc mong muốn. Trong CI, nên xác minh files/report có tồn tại và test counts thật, ngoài `jacoco:check`.

## 16. Checkstyle và Enforcer: hai loại gate khác coverage

### 16.1. Checkstyle fail khi source vi phạm rule

Nếu trong một Java source cố tình thêm wildcard import:

~~~java
// PHẢN VÍ DỤ: fragment có violation trong checkstyle.xml.
import java.util.*;
~~~

Checkstyle `AvoidStarImport` sẽ báo vi phạm và `checkstyle:check` có thể fail build. **Đây là ví dụ fragment**, không phải file Java hoàn chỉnh, và không nên đưa vào baseline code của lab.

Tương tự, tab character hoặc thiếu newline cuối file sẽ bị rules tương ứng phát hiện.

Khi style check fail:
1. Xem file, dòng và tên rule Checkstyle.
2. Sửa code hoặc cập nhật ruleset bằng PR có review nếu rule không phù hợp.
3. Chạy lại `mvn clean verify`.
4. Không đặt `checkstyle.skip=true` trong CI chính thức để giả vờ pass.

### 16.2. Enforcer fail sớm khi build toolchain không đạt

Lab yêu cầu:

~~~xml
<requireMavenVersion>
    <version>[3.9,4.0)</version>
</requireMavenVersion>
<requireJavaVersion>
    <version>[17,)</version>
</requireJavaVersion>
~~~

Điều này đòi Maven 3.9.x/3.10.x và JDK Maven runtime >=17. Nó không tự cài JDK/Maven hoặc lựa chọn toolchain cho Surefire; `mvn -version` và CI setup vẫn phải đúng.

Nếu `mvn -version` báo Maven 4, demo deliberately fail Enforcer ở `validate`. Đó là hợp đồng project trong bài, không phải khẳng định Maven 4 không bao giờ chạy được với các plugin.

### 16.3. Một quality gate hiệu quả có thuộc tính gì?

Nên có:
- **Ownership:** team biết ai quản lý rule/threshold.
- **Determinism:** cùng inputs/môi trường tương đương cho cùng kết quả.
- **Evidence:** báo cáo machine-readable/console, linked tới CI job.
- **No bypass by default:** CI required check không dùng skip flags.
- **Actionability:** failure chỉ rõ rule/test/module và cách sửa.
- **Versioning:** rule config và plugin versions được review cùng POM.
- **Scope:** tránh áp threshold của module có tests lên POM-only aggregator gây false failures.
- **Recovery:** có cách chạy lại từ clean worktree khi nghi cache/stale reports.

## 17. Test một cách chủ động rằng cổng thật sự chặn sai sót

Một quality gate **chưa được kiểm nghiệm** có thể cấu hình sai mà không ai biết. Trong branch sandbox, thử những lỗi có kiểm soát rồi **khôi phục source trước khi merge**.

| Thử nghiệm | Cách tạo lỗi có kiểm soát | Gate phải phản ứng |
| --- | --- | --- |
| Unit regression | Đổi expected `"APPLE:2"` thành `"APPLE:9"` trong `TaskReportTest` | Surefire fail ở `test` |
| IT regression | Đổi `TaskReportIT` expected output thành sai | Failsafe chạy IT, fail ở `verify` |
| Coverage below threshold | Tăng minimum LINE lên 1.00 rồi bỏ test một nhánh | JaCoCo check fail nếu coverage thật dưới 100% |
| Source style violation | Thêm wildcard import trong Java file | Checkstyle check fail |
| Wrong Java | Chạy Maven bằng JDK thấp hơn 17 | Enforcer/compile fail |
| Wrong Maven | Chạy Maven 4 với hợp đồng `[3.9,4.0)` | Enforcer fail |
| Missing all unit tests | Đổi tên hoặc bỏ toàn bộ `*Test` classes | Surefire `failIfNoTests=true` fail |
| Missing all ITs | Bỏ/đổi tên mọi `*IT` class | Failsafe `failIfNoTests=true` fail |
| Lost JaCoCo agent | Ghi đè `argLine` hoặc skip prepare-agent | Report/data missing; CI artifact check phải phát hiện |

**Không dùng những thay đổi gây fail này trên nhánh release production.** Mục tiêu là một PR/sandbox “quality gate smoke test”, chạy test negative, lưu evidence rồi revert.

### 17.1. Khác biệt giữa test assertion fail và build plugin failure

Nếu lỗi ở `TaskReportIT` do output sai, Failsafe report có testcase failure và final `failsafe:verify` fail. Nếu `maven-failsafe-plugin` không thể resolve dependency, goal có thể fail trước khi test chạy. Khi debug cần phân biệt:
- Test assertion failure.
- Test engine/provider discovery failure.
- Plugin resolution/configuration error.
- Environment provisioning failure.
- Timeout/IO/external service unavailable.
- Coverage/style rule violation.

Chỉ dựa vào dòng cuối `BUILD FAILURE` không đủ để xác định cổng nào chặn.

## 18. Vì sao `mvn test`, `mvn package`, `mvn integration-test` và `mvn verify` không tương đương?

| Lệnh | Unit tests | Failsafe IT | IT result final verify | Coverage/Checkstyle ở verify |
| --- | --- | --- | --- | --- |
| `mvn test` | Có | Không | Không | Không |
| `mvn package` | Có | Không | Không | Không |
| `mvn integration-test` | Có | Có | **Chưa** | Không |
| `mvn verify` | Có | Có | **Có** | **Có** |
| `mvn clean verify` | Có và xóa output cũ trước | Có | **Có** | **Có** |

Bảng giả định POM lab và không có skip flags. Lệnh `mvn verify` không nhất thiết chạy đủ nếu trước đó fail ở phase sớm hơn. Bởi vậy cần đọc logs/reports theo kết quả thật.

Với CI gate phải bảo đảm integration-service teardown, **không gọi `mvn integration-test` đơn lẻ**. Chạy `verify` để đi qua `post-integration-test` và kiểm Failsafe summary.

## 19. `-DskipTests`, `-DskipITs`, `-Dmaven.test.skip` là đường vòng nguy hiểm

Một số flags hữu ích để debug local nhưng không phải kết quả QA hoàn chỉnh:

~~~bash
mvn -DskipTests clean verify
mvn -DskipITs clean verify
mvn -Dmaven.test.skip=true clean verify
mvn -Djacoco.skip=true clean verify
mvn -Dcheckstyle.skip=true clean verify
~~~

Ý nghĩa cần phân biệt:
- `skipTests`: thường bỏ thực thi tests ở Surefire/Failsafe theo cấu hình/provider.
- `skipITs`: Failsafe có cờ riêng để skip integration tests, không đồng nghĩa unit tests pass.
- `maven.test.skip=true`: có thể bỏ cả test compilation trong Compiler/Surefire/Failsafe.
- `jacoco.skip=true`: có thể bỏ agent/report/check; nếu vẫn có old files, dễ đọc nhầm stale coverage.
- `checkstyle.skip=true`: bỏ style enforcement.

**Không dùng các flags trên ở required CI quality gate.** Với POM này, `failIfNoTests=true` vẫn không bảo vệ tuyệt đối trước cờ skip được người dùng cố tình truyền. Có thể bổ sung policy checks để fail trên CI commands chứa skip flags, protected workflows, codeowners, required checks và kiểm output reports.

### 19.1. Vì sao `mvn -fn` không dùng làm CI gate?

Flag `-fn` (fail never) có thể khiến Maven không trả exit code phản ánh failure, tùy phiên bản/kiểu failure. Một CI job dựa hoàn toàn vào exit code có thể bị đánh lừa.

Đừng đặt `-fn`, `|| true`, `continue-on-error` hay shell step cố tình nuốt exit code cho required `verify` jobs.

## 20. Kiểm báo cáo bằng máy, không chỉ đọc “BUILD SUCCESS”

Sau `mvn clean verify` thật sự pass, từ project root trên Linux/macOS:

~~~bash
test -s target/surefire-reports/TEST-com.example.quality.TaskReportTest.xml
test -s target/failsafe-reports/TEST-com.example.quality.TaskReportIT.xml
test -s target/failsafe-reports/failsafe-summary.xml
test -s target/jacoco.exec
test -s target/site/jacoco/jacoco.xml
test -s target/site/jacoco/index.html
test -s target/checkstyle-result.xml
~~~

Mỗi `test -s` kiểm file tồn tại và không rỗng; nếu bất kỳ lệnh nào trả nonzero, stop/fail CI job. Chúng **không tự kiểm** số tests/coverage contents; hãy parse XML và đối chiếu expected counts/threshholds ở CI nếu cần.

Một pipeline robust nên:
1. Chạy `clean verify` để tránh artifacts cũ.
2. Kiểm Maven exit code.
3. Kiểm Surefire/Failsafe XML reports tồn tại.
4. Đọc `tests`, `failures`, `errors`, `skipped` theo schema thực tế.
5. Kiểm `jacoco.xml` tồn tại và chứa metrics mong muốn.
6. Đối chiếu Checkstyle summary/violations.
7. Lưu/đính kèm reports như build artifacts có thời hạn; không đưa secrets vào logs.

### 20.1. Đường dẫn báo cáo trên Windows

PowerShell:

~~~powershell
$required = @(
    "target/surefire-reports/TEST-com.example.quality.TaskReportTest.xml",
    "target/failsafe-reports/TEST-com.example.quality.TaskReportIT.xml",
    "target/failsafe-reports/failsafe-summary.xml",
    "target/jacoco.exec",
    "target/site/jacoco/jacoco.xml",
    "target/checkstyle-result.xml"
)

foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing QA artifact: $path"
    }
    if ((Get-Item -LiteralPath $path).Length -eq 0) {
        throw "Empty QA artifact: $path"
    }
}
~~~

Đây là một **fragment kiểm presence**. Nếu có reports nhưng test count sai hoặc Failsafe summary báo failed tests, build vẫn phải fail nhờ plugin và/hoặc parser validation.

## 21. CI GitHub Actions: một required `verify` job

Ví dụ `.github/workflows/verify.yml` cho source lab ở repository root:

~~~yaml
name: Maven verify quality gates

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show actual environment
        run: |
          java -version
          javac -version
          mvn -version

      - name: Run all quality gates
        run: mvn -B -ntp clean verify

      - name: Confirm QA reports exist
        run: |
          test -s target/surefire-reports/TEST-com.example.quality.TaskReportTest.xml
          test -s target/failsafe-reports/TEST-com.example.quality.TaskReportIT.xml
          test -s target/jacoco.exec
          test -s target/site/jacoco/jacoco.xml
          test -s target/checkstyle-result.xml

      - name: Upload test and coverage reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: maven-quality-reports
          if-no-files-found: warn
          path: |
            target/surefire-reports/
            target/failsafe-reports/
            target/site/jacoco/
            target/checkstyle-result.xml
~~~

**Đây là CI minh họa**, giả sử runner có Maven3.9+ và plugin repositories truy cập được. `actions/setup-java` chọn JDK nhưng **không pin Maven distribution**; khi cần ổn định tuyệt đối, dùng Maven Wrapper đã commit hoặc approved Maven image và xác minh `mvn -version`.

### 21.1. Cổng ở CI phải là required status check

Không đủ khi workflow chỉ tồn tại. Cần branch protection/rulesets yêu cầu job `verify` pass trước merge hoặc release. Một workflow chạy `continue-on-error` hoặc không phải required check có thể bị bỏ qua.

`actions/upload-artifact` chỉ phục vụ chẩn đoán; **nó không quyết định pass/fail quality gate**. Khi `verify` fail, `if: always()` vẫn cho phép upload reports còn tạo được. Nếu lỗi ở `compile`, không nhất thiết có IT/coverage reports; đó là bình thường.

### 21.2. Không cho test dùng production secrets

Lab không cần token. Production IT dùng protected sandbox/staging endpoints, secrets scoped theo job, tránh đưa credentials thật vào logs/reports/JaCoCo/attached artifacts. Không chạy untrusted PR source với production deploy tokens.

### 21.3. CI dependency cache khác build-output reuse

`cache: maven` của `setup-java` thường cache Maven local dependencies để tăng tốc tải. Nó **không bảo đảm** Surefire/Failsafe/JaCoCo/Checkstyle goals đã chạy. Đừng rút ngắn required gate bằng việc restore `target/` hoặc dùng cached test XML mà không có provenance và cache policy đã kiểm.

## 22. Một bảng lỗi tiêu biểu khi nối gates

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm/sửa |
| --- | --- | --- |
| `mvn test` pass, `mvn verify` fail | IT/coverage/Checkstyle chạy muộn hơn | Đọc goal đầu tiên fail tại `verify` |
| IT class có `@Test` nhưng không chạy | Tên không match Failsafe includes hoặc execution thiếu | `*IT` naming, executions, failIfNoTests |
| Không có `failsafe-reports` | Failsafe không bind hoặc build fail sớm | Effective POM, Maven phase, logs |
| IT fail nhưng `mvn integration-test` exit success | Failsafe trì hoãn failure | Luôn chạy `mvn verify` |
| Teardown không chạy | Goal fail trước cleanup hoặc job bị kill | Kiểm Failsafe phases, external cleanup/TTL |
| JaCoCo report 0% | Agent không gắn fork JVM, wrong argLine | `prepare-agent`, `@{argLine}`, forks |
| `Could not find or load main class @{argLine}` | Placeholder late evaluation không thay | Property fallback và plugin config |
| JaCoCo check không chạy vì thiếu `.exec` | Tests skipped hoặc agent disabled | Xác minh execution data file trong CI |
| JaCoCo line gate fail | Coverage không đạt threshold | Thêm test có assertions thật, không hạ gate vô cớ |
| Checkstyle không chặn violation | `checkstyle:check` chưa bind hoặc skip | Build/plugins execution và failOnViolation |
| `checkstyle.xml` không được tìm thấy | Sai `configLocation`/working directory | Đặt config tại root POM hoặc path đúng |
| Test compile fail | Source imports/JUnit dependency sai | JUnit Jupiter test scope, compiler version |
| Enforcer fail ngay ở validate | Maven/JDK ngoài range | `mvn -version`, JAVA_HOME, update toolchain |
| `Tests run: 0` nhưng build xanh | Discovery/skip flags/gate thiếu | failIfNoTests, patterns, reports |
| Failsafe chạy cùng test với Surefire | Includes custom trùng nhau | Tách naming patterns rõ ràng |
| IT đọc nhầm file khác | Fixed path, shared temp directory | Dùng `@TempDir`, module-specific output |
| CI lỗi file permission | Build runner không ghi temp path | Kiểm permissions, không cấp admin mặc định |
| IT timeout ngẫu nhiên | Resource contention hoặc external service chưa ready | Readiness checks/timeouts/isolation |
| JaCoCo `.exec` chứa dữ liệu cũ | Không clean build, append từ run khác | `mvn clean verify`, isolated workspaces |
| `checkstyle:checkstyle` tạo HTML nhưng CI vẫn xanh | Chỉ report, không có check goal | Bind `checkstyle:check` |
| `mvn package` xanh nhưng chưa có XML IT | Chưa đến IT/verify phases | Dùng `verify` |
| JAR được ký/publish trước QA | Lifecycle hoặc CI job order sai | Chặn publish đến khi required verify pass |
| `-DskipITs` giúp build xanh | Bỏ qua IT chứ không sửa lỗi | Không dùng skip flags trong required CI |
| Pipeline upload reports lộ secret | Logs/outputs chứa environment credentials | Redact, least-privilege, retention policy |

## 23. Mô hình mở rộng sang HTTP/database integration tests

Một IT thực tế thường cần:
- Service chạy và sẵn sàng trước test.
- Dữ liệu cô lập/test database migration đã chuẩn bị.
- Credentials có scope test, không dùng production secrets.
- Port/hostname được truyền qua configuration chứ không hardcode máy developer.
- Resource cleanup sau test, kể cả assertion failure.
- Network failure/timeout được báo với nguyên nhân rõ.
- Tests có thể chạy trên runner sạch, không phụ thuộc service đã mở sẵn trên laptop.

### 23.1. `pre-integration-test` và `post-integration-test`

Một mô hình lifecycle:

~~~text
pre-integration-test: start test service, await readiness
integration-test:     Failsafe runs *IT classes
post-integration-test: stop service, collect logs
verify:               Failsafe verifies test results
~~~

**Không bắt buộc** lab file I/O phải có start/stop goals. Nhưng khi có database/test server, phải cấu hình start/stop tại phases đúng.

Một setup lỗi thường gặp là khởi động server bằng `exec:exec` blocking command trong `pre-integration-test`. Khi process không daemonize, Maven có thể chờ mãi không vào IT. Cần plugin/công cụ start async/daemon và readiness check phù hợp; không copy lệnh start background tùy OS mà không quản lý PID/cleanup.

### 23.2. Không phụ thuộc hạ tầng production trong required IT

Tests trên staging nên không phá data, có fixture setup/teardown và isolation. Với CI parallel workers, dùng database/schema riêng hoặc container riêng. Không cho IT của hai PRs ghi cùng tables/queues như thể chúng là một suite tuần tự.

### 23.3. Flaky integration tests khác assertion failure thật

Flake do network timing/port conflict có thể bị che bằng retries. Trước khi bật retry:
1. Thu logs và evidence failure.
2. Phân loại timeout/readiness/shared state.
3. Cố định test data và environment.
4. Sửa synchronization/cleanup.
5. Dùng bounded retries chỉ với loại lỗi policy chấp nhận, không biến flaky test thành ignored gate.

Không cho `-DskipITs` trở thành cách chữa flake mặc định.

## 24. Multi-module Reactor: chất lượng per-module và aggregate khác nhau

Với project:

~~~text
root/ (pom aggregator)
├── api/
├── core/
├── app/
└── integration-tests/
~~~

các plugin cấu hình ở parent `<build><plugins>` có thể kế thừa cho children. Tuy nhiên:
- Root `packaging=pom` có thể không có test classes: `failIfNoTests=true` áp cho root có thể gây fail không mong muốn.
- Module `api` có unit tests, module `integration-tests` có IT; không nhất thiết mỗi module đều có cả hai.
- `jacoco:report` mặc định report trong **một project/module**, không tự gom mọi modules.
- `jacoco:check` với `BUNDLE` xét **bundle module hiện tại**; không phải coverage tỷ lệ toàn Reactor.
- Checkstyle config path cần phù hợp khi goals chạy ở modules có basedir khác root.
- Module dependencies và Reactor ordering ảnh hưởng thời điểm IT có thể dùng artifacts.
- `mvn -pl :app -am verify` không chạy những modules không có trong selected reactor, vì vậy coverage/test policy phải dựa trên module set thực tế.

### 24.1. Khi cần coverage tổng cho Reactor

JaCoCo có goal `report-aggregate` để tổng hợp execution data/classes từ dependencies theo mô hình project, thường sử dụng **một reporting module riêng**. Không chỉ đặt `report-aggregate` trong parent rồi tự nhận `BUNDLE` check là toàn repo.

Nếu target là coverage toàn sản phẩm, thiết kế:
1. Per-module `prepare-agent` và tests.
2. Per-module reports cho debugging.
3. Module chuyên tổng hợp `report-aggregate` với dependencies cần thiết.
4. XML aggregate report được gửi cho quality service.
5. Gate aggregate riêng hoặc script/CI integration có parsing rõ.
6. Chính sách cho modules không có tests hoặc generated sources.

Không để một module có coverage rất cao che phủ một critical module không được test mà không có threshold theo risk.

### 24.2. IT ở module riêng có ưu/nhược điểm gì?

Ưu điểm:
- Test application assembly sau build.
- Quản lý hạ tầng riêng.
- Giữ unit test của modules nhỏ, nhanh.
- Dễ chọn CI job cho integration suite.

Nhược điểm:
- Cần dependency graph hợp lệ để IT module nhận đúng artifacts.
- Lifecycle packaging/classifier có thể ảnh hưởng tests.
- Test report thuộc module IT, còn coverage production classes nằm ở upstream modules; JaCoCo aggregate cần setup riêng.
- Dùng `-pl` không `-am` có thể fail khi chưa install upstream artifacts.

## 25. Điều chỉnh coverage thresholds theo tính chất sản phẩm

Trong lab: `LINE` 80%, `BRANCH` 60%, BUNDLE-level.

Tuy nhiên một ứng dụng thực tế có:
- DTO/records và generated code ít giá trị coverage.
- Security/business rules cần branch tests chặt hơn.
- Exception/error handlers khó chạm nhưng quan trọng.
- Integration classes với nhiều external branches.
- Legacy modules cần kế hoạch nâng ngưỡng có lộ trình.

Policy tốt thường kết hợp:
- Tỷ lệ tối thiểu toàn module.
- Threshold cao hơn cho critical packages.
- Coverage của code mới/changed lines.
- Assertions có chất lượng, edge cases, property-based tests.
- Mutation testing khi phù hợp.
- Review exclusions có lý do minh bạch.

**Không auto-exclude toàn bộ class có coverage thấp** để làm CI xanh. Exclusion chỉ áp dụng cho những thành phần được policy xác định (generated code, adapters không đo được trong suite tương ứng), và luôn có reviewer.

### 25.1. Nếu chỉ report coverage nhưng không check thì sao?

`jacoco:report` có thể tạo `index.html`, `jacoco.xml` nhưng Maven exit code vẫn 0 dù coverage thấp. Cần bind `jacoco:check`, giới hạn `minimum` và `haltOnFailure=true`.

### 25.2. Nếu gate check không thấy execution data?

Một số JaCoCo goal có thể báo skip vì không có data file. Vì vậy CI nên kiểm `target/jacoco.exec`, Surefire/Failsafe XML và coverage XML **không rỗng**, rồi parse counters nếu policy yêu cầu. Đây là một **quality gate second line of defense**, không lặp lại vô ích với JaCoCo threshold.

## 26. Chọn phase Checkstyle: `validate` hay `verify`?

Hai lựa chọn thường gặp:
- Bind Checkstyle ở `validate`: fail sớm trước compile/tests, tiết kiệm thời gian khi code style sai.
- Bind ở `verify`: cùng bước kiểm chất lượng cuối, cho phép compilation/test failures lộ trước nếu code không biên dịch được.

Lab chọn `verify` vì đề yêu cầu **gắn cổng chất lượng vào verify**. Với dự án lớn, có thể chạy style check sớm ở `validate`, hoặc một CI job riêng nhưng **vẫn là required check**. Đừng chuyển sang phase sớm chỉ để bỏ qua unit/IT ở các jobs khác.

### 26.1. Static analysis bổ sung

Ngoài Checkstyle, có thể dùng:
- SpotBugs: tìm patterns lỗi code.
- PMD: static code rules.
- OWASP Dependency-Check hoặc SCA scanner: known dependency vulnerabilities, với database update policy.
- SonarQube/SonarCloud: phân tích và quality gate từ service riêng.
- License checks, API compatibility checks, reproducible build checks.

**Không phải tool nào cũng bind trực tiếp vào `verify` đúng như JaCoCo/Checkstyle**. Nếu dùng external service/scan jobs, CI phải chờ kết quả và đánh dấu required status. Tránh claim “`mvn verify` đảm bảo không có vulnerability” chỉ vì có một static style checker.

## 27. Đảm bảo CI dùng cùng build command và cấu hình local

Một bug thường gặp:
- Local dùng `mvn clean verify`, JDK17.
- CI dùng `mvn test -DskipTests`, JDK21.
- Release dùng `mvn deploy` từ một container có plugin versions khác.
- Team vẫn nói “đã kiểm cùng một pipeline”.

Giải pháp:
1. Pin Maven Wrapper hoặc CI Maven distribution và plugin versions.
2. Ghi `mvn -version`, `java -version` trong CI logs.
3. Dùng một command chuẩn để làm QA gate.
4. Không truyền skip flags trong required status checks.
5. Chạy trên clean checkout/build dir.
6. Tách cache dependency khỏi generated outputs.
7. Đảm bảo env/config được định nghĩa qua profiles/settings/CI variables.
8. Với JDK matrix, chạy gates trên các JVM cần hỗ trợ.
9. Kiểm JUnit reports theo từng JDK/job, không upload chung và overwrite.
10. Không publish nếu một required job chưa pass.

### 27.1. Maven profiles ảnh hưởng gates

Nếu cấu hình Failsafe/JaCoCo chỉ nằm trong `<profile id="quality">`, lệnh `mvn verify` không có `-Pquality` có thể bỏ cổng. Nếu yêu cầu **mọi `verify`** phải đầy đủ, đặt plugins trong default `<build><plugins>` như lab, hoặc có activation/CI gate được thực thi nhất quán.

Không đặt mọi gates trong profile không kích hoạt mặc định rồi viết tài liệu rằng “chạy `mvn verify` là đủ” khi thực tế phải cần `-P...`.

## 28. Các lỗi của pipeline dễ phát hiện bằng readback reports

Nếu CI thấy `BUILD SUCCESS`, vẫn nên kiểm:

~~~text
Surefire tests:
  TaskReportTest      -> 4 tests, failures=0

Failsafe tests:
  TaskReportIT        -> 7 tests, failures=0

JaCoCo:
  agent data file     -> exists and non-empty
  HTML/XML report     -> exists and contains counters
  LINE gate           -> >= 0.80
  BRANCH gate         -> >= 0.60

Checkstyle:
  checker config      -> loaded from checkstyle.xml
  violations          -> 0 for configured rules

Enforcer:
  Maven version       -> within [3.9,4.0)
  Java version        -> >= 17

Build:
  project JAR         -> created
  Maven exit status   -> 0
~~~

Các giá trị trên là **expected validation criteria của lab**, không phải báo cáo đã chạy thực tế ở môi trường này.

### 28.1. Vì sao số tests quan trọng?

Nếu developer xóa một integration test class, Failsafe có thể vẫn tìm thấy 6 tests và pass. `failIfNoTests=true` không phát hiện mất từng test. Report counts/quality policy cần giúp nhận diện test count drift khi số tests là một contract.

Không ép mọi dự án luôn có đúng 11 tests; con số này chỉ gắn với source lab đã cung cấp.

## 29. Cẩn trọng với `-T` và tests dùng tài nguyên chung

Khi Maven Reactor chạy với `-T 2`, các modules khác nhau có thể thực thi Surefire/Failsafe cùng lúc. Bản thân Surefire/Failsafe thread safety không tự làm test suite dùng shared port/database an toàn.

Thực hành:
- `@TempDir` cho files.
- Port động, không hardcode 8080 cho mọi IT.
- Container/database riêng per module hoặc per CI job.
- Namespace/queue/topic của test tách theo unique run id.
- Cleanup chắc chắn, không để orphaned server giữa jobs.
- Tránh JUnit tests mutate JVM-wide static state không được đồng bộ.
- Với JaCoCo, để output `.exec` trong `${project.build.directory}` của từng module.
- Aggregate reports sau khi mọi modules đã kết thúc.

Không dùng shared `target/` giữa hai Maven processes chạy cùng checkout. `mvn clean` từ job A có thể xóa output job B đang đọc, tạo flake không liên quan business logic.

## 30. Troubleshooting khi một gate chỉ fail trên CI

### 30.1. Local unit tests pass nhưng CI integration test fail

Kiểm CI environment trước: Java/Maven version, filesystem permissions, locale, timezone, case-sensitivity, network, test ports, external services, profiles và test data. Chạy `mvn -version`, đọc `failsafe-summary.xml` và individual IT XML.

Không đổi test từ Failsafe thành Surefire chỉ để CI xanh. Chuyển phase không giải quyết nguyên nhân tích hợp.

### 30.2. JaCoCo không ghi `jacoco.exec`

Kiểm:
- `prepare-agent` có chạy ở `initialize` không.
- Tests được fork (`forkCount>0`) không.
- Surefire/Failsafe `argLine` có `@{argLine}` không.
- Có plugin/profile override argLine không.
- Tests có bị skip không.
- Build có dừng trước khi test JVM exit không.
- Có nhiều parallel jobs share cùng target path không.

Sau sửa, dùng `mvn clean verify` và kiểm data/report files. Đừng copy `.exec` từ máy khác để “chữa” mất coverage.

### 30.3. Checkstyle báo lỗi cả tests nhưng local không báo

POM lab đặt `includeTestSourceDirectory=true`. Kiểm project local/CI có dùng cùng POM/profile không, file `checkstyle.xml` có được checkout không, source encoding/newline endings có khác không, Checkstyle Plugin version/ruleset có bị override không.

### 30.4. Maven báo `No tests to run` trong Failsafe

Kiểm class `TaskReportIT`, JUnit Jupiter engine dependency, test compilation, plugin include patterns, `failIfNoTests`, Maven goal execution plan. Không kết luận “không có IT” từ việc tên file có `@Test` trong IDE mà chưa xem Maven convention.

### 30.5. Surefire báo tests=0 sau khi đổi class names

Kiểm `*Test`, `Test*`, `*Tests`, `*TestCase`, test engine, disabled tests và Surefire includes. Xem `target/surefire-reports` từ clean run. Không bỏ `failIfNoTests` để che class discovery issue.

### 30.6. Coverage fail sau khi thêm branch mới

Thêm tests có assertions cho nhánh nghiệp vụ mới. Nếu branch không thể chạm do dead code, cân nhắc refactor. Nếu code generated hoặc non-testable by design, làm exception có review và reason, không tắt toàn bộ coverage gate.

### 30.7. `verify` fail ở Checkstyle nhưng tests đã pass

Đây là behavior đúng: QA gate có nhiều lớp. Xem violation rule/path/line và sửa style. Không lấy “unit+IT pass” để bỏ cổng static style mà team đã chọn là required.

### 30.8. `mvn integration-test` báo success dù IT có assertion failure

Đừng coi đó là bug tự động. Failsafe ghi kết quả và chờ `failsafe:verify` để báo fail, nhằm giữ cơ hội cleanup. Dùng `mvn verify` ở CI.

### 30.9. CI không có JaCoCo XML dù build success

Kiểm agent/report, goal execution, missing `.exec`, config skip. Bổ sung artifact existence checks. Không đánh dấu gate PASS khi không có report/data chứng minh coverage.

### 30.10. Re-running Maven không thay đổi kết quả test lỗi không ổn định

Nếu một test flake, log phải chỉ rõ seed/data/inputs/resources. Cố định timezone, locale, clock abstractions, network readiness, test isolation. Retry vô hạn hoặc `-DskipITs` chỉ che vấn đề.

## 31. Một checklist cho code review của POM

1. POM là version 4.0.0 hợp Maven 3.9+.
2. Java baseline là 17, Maven/JDK đều đúng.
3. Compiler version pin và có `maven.compiler.release`.
4. JUnit Jupiter dependency có `test` scope.
5. Unit test tên đúng `*Test`.
6. IT tên đúng `*IT`.
7. Surefire version pin, có execution qua default lifecycle.
8. Failsafe có goals `integration-test` **và** `verify`.
9. Unit và IT không bị includes trùng nhau.
10. `failIfNoTests` được áp hợp lý theo module.
11. JaCoCo `prepare-agent` chạy trước tests.
12. Surefire/Failsafe fork và `@{argLine}` giữ agent.
13. JaCoCo data từ hai suite được thu đúng file/merge policy.
14. `jacoco:report` bind ở `verify`.
15. `jacoco:check` có thresholds và `haltOnFailure=true`.
16. Checkstyle config file đã checkout và path đúng.
17. Checkstyle dùng goal `check` chứ không chỉ report.
18. Checkstyle thực sự fail trên violation.
19. Enforcer chạy ở `validate`.
20. Không có skip flags trong required CI command.
21. CI dùng `mvn clean verify`, không chỉ `test` hoặc `package`.
22. Không dùng `-fn`, `continue-on-error` để nuốt failures.
23. Reports Surefire/Failsafe/JaCoCo/Checkstyle được giữ.
24. CI xác minh reports/data không thiếu và không rỗng.
25. Unit tests thực sự assert logic.
26. IT test chạm ranh giới thật, không chỉ gọi cùng function unit.
27. IT dùng test-only resources/credentials.
28. Cleanup IT phù hợp với `post-integration-test`.
29. JUnit fixture cô lập với `@TempDir`/ports dynamic.
30. Không share `target`/JaCoCo exec giữa CI jobs.
31. Coverage policy minh bạch và phù hợp domain.
32. Không hạ threshold để che regression.
33. Profile activation của CI đã được kiểm.
34. Multi-module parent không áp gate sai cho aggregator không có tests.
35. JaCoCo aggregate có module/report riêng nếu cần.
36. Plugin versions được nâng có review và full `verify`.
37. Quality gates có owners và cách debug.
38. Unit/IT/style/coverage negative tests đã được thử trong sandbox.
39. Release job phụ thuộc required verify status.
40. Không công bố artifacts từ build chưa kiểm đủ gates.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** `mvn test` đã chạy integration tests của Failsafe chưa?

**Đáp:** Chưa. Theo lifecycle lab, Failsafe ở các phase `integration-test` và `verify`, chạy đầy đủ bằng `mvn verify`.

**Câu 2.** Vì sao Failsafe có cả hai goals?

**Đáp:** `integration-test` thực thi IT và ghi kết quả; `verify` kết luận success/failure sau cơ hội cleanup `post-integration-test`.

**Câu 3.** Chạy `mvn integration-test` là CI gate đáng tin cho IT chưa?

**Đáp:** Chưa. Lệnh không đi qua phase teardown và `failsafe:verify`.

**Câu 4.** `TaskReportTest.java` do plugin nào mặc định chạy?

**Đáp:** Surefire ở phase `test`.

**Câu 5.** `TaskReportIT.java` do plugin nào mặc định phát hiện khi đã cấu hình execution?

**Đáp:** Failsafe ở phase `integration-test`.

**Câu 6.** JaCoCo `prepare-agent` làm gì?

**Đáp:** Cung cấp Java agent JVM argument cho tests, mặc định qua Maven property `argLine` đối với jar project.

**Câu 7.** Vì sao cần `@{argLine}`?

**Đáp:** Surefire/Failsafe đánh giá property muộn khi goal chạy, nhận giá trị agent do JaCoCo thiết lập ở `initialize`.

**Câu 8.** `jacoco:report` có tự fail nếu coverage 10% không?

**Đáp:** Không như một threshold gate. Cần `jacoco:check` với rules/minimum và haltOnFailure.

**Câu 9.** `LINE=0.80` và `BRANCH=0.60` là gì?

**Đáp:** Ngưỡng coverage tối thiểu của bundle trong lab: 80% lines và 60% branch outcomes.

**Câu 10.** Checkstyle XML có thể thay thế tests không?

**Đáp:** Không. Nó kiểm quy tắc tĩnh như imports/tabs/newline, không chứng minh runtime behavior.

**Câu 11.** Nếu test class IT bị đổi tên thành không match, `failIfNoTests=true` giúp gì?

**Đáp:** Fail nếu Failsafe không tìm thấy bất kỳ test nào; không đảm bảo mọi expected tests đều còn.

**Câu 12.** `-DskipITs` có phù hợp required `verify` không?

**Đáp:** Không, vì bỏ một phần quan trọng của cổng chất lượng.

**Câu 13.** Vì sao CI vẫn cần kiểm `jacoco.exec`/XML sau `verify`?

**Đáp:** Một số goals có thể skip khi thiếu data; phải chắc rằng coverage thật đã được thu và báo cáo được tạo.

**Câu 14.** Nếu unit fail, Checkstyle ở verify có chắc đã chạy không?

**Đáp:** Không. Maven thường dừng ở phase `test` trước khi tới `verify`.

**Câu 15.** Bài lab có bao nhiêu tests?

**Đáp:** 4 unit methods + 7 IT methods = 11 JUnit methods.

**Câu 16.** IT dùng filesystem có thực sự là integration test không?

**Đáp:** Có trong phạm vi đã nêu: kiểm liên kết parser/formatter với filesystem I/O. Nó không chứng minh database/HTTP integration.

**Câu 17.** `@TempDir` giải quyết điều gì?

**Đáp:** Tạo thư mục tạm cô lập cho test, giảm phụ thuộc working directory và tránh tranh file của tests khác.

**Câu 18.** `mvn package` tạo JAR có chứng minh Checkstyle/JaCoCo check pass không?

**Đáp:** Không. Các cổng này đang gắn ở phase `verify`, sau `package`.

**Câu 19.** JaCoCo BUNDLE gate trong một module có tự đại diện coverage toàn Reactor không?

**Đáp:** Không. Cần thiết kế report-aggregate và gate tổng cho multi-module nếu muốn.

**Câu 20.** Thế nào là một `verify` gate đáng tin?

**Đáp:** Các plugins thực sự được bind và thực thi, tests không bị skip, report/threshold được kiểm, build fail khi điều kiện bị vi phạm và CI yêu cầu status check trước merge/release.

## 33. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin — Overview](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Surefire Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Failsafe Plugin — Overview](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven Failsafe Plugin — Integration-test Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe Plugin — Verify Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [JaCoCo — Official Releases](https://www.jacoco.org/jacoco/)
- [JaCoCo — Maven Prepare Agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)
- [JaCoCo — Maven Report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)
- [JaCoCo — Maven Check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JaCoCo — Report Aggregate](https://www.jacoco.org/jacoco/trunk/doc/report-aggregate-mojo.html)
- [Apache Maven Checkstyle Plugin — Usage](https://maven.apache.org/plugins/maven-checkstyle-plugin/usage.html)
- [Apache Maven Checkstyle Plugin — Check Goal](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
- [Checkstyle — Configuration Modules](https://checkstyle.org/config)
- [Apache Maven Enforcer Plugin — Require Maven Version](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Apache Maven Enforcer Plugin — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)
- [GitHub Actions — Setup Java](https://github.com/actions/setup-java)

