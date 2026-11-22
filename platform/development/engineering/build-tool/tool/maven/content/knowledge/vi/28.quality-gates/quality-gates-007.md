# Đặt ngưỡng kiểm chứng và hiểu giới hạn của phần trăm bao phủ trong Maven

## 1. Cổng chất lượng là điều kiện kiểm chứng, không phải “chứng chỉ code đúng”

Trong một Maven build, **cổng chất lượng** (*quality gate*) là tập các điều kiện mà dự án phải đáp ứng trước khi được chấp nhận vào nhánh chính hoặc phát hành. Ví dụ: biên dịch thành công, không có test thất bại, các integration tests bắt buộc chạy đủ, mã không vi phạm quy tắc bảo mật quan trọng và **code coverage** vượt một ngưỡng đã được phê duyệt.

Code coverage trả lời câu hỏi **“Bao nhiêu phần của code đã được thực thi trong các lần chạy được đo?”**; nó không trả lời trực tiếp **“Bao nhiêu phần code là đúng?”**. Một test có thể đi qua rất nhiều dòng nhưng không assert điều gì. Ngược lại, một test ngắn ở đúng boundary quan trọng có thể tìm được bug mà hàng chục test happy-path bỏ sót.

Bài này tập trung vào hai kỹ năng:

1. Cấu hình **Maven Surefire + JaCoCo Maven Plugin** để đo `LINE`, `BRANCH` và dùng `jacoco:check` chặn `mvn verify` khi chưa đạt ngưỡng.
2. Đọc số liệu theo **mẫu số, counter, phạm vi, suite đã chạy và limitations**, không nhầm 80% coverage với 80% correctness.

Ví dụ thực hành dùng **Java 17+, Maven 3.9+, JUnit Jupiter 5.11.4, Surefire 3.5.2, JaCoCo Maven Plugin 0.8.16**. Phiên bản JaCoCo 0.8.16 là bản phát hành ổn định trong tháng 10/2026; khi đọc tài liệu trực tuyến `trunk`, không sao chép nguyên version `-SNAPSHOT` ở trang docs vào POM release.

## 2. Coverage, test results và test execution không giống nhau

| Thông tin | Công cụ thường dùng | Nó cho biết | Nó không cho biết |
| --- | --- | --- | --- |
| Kết quả tests | Surefire, Failsafe, JUnit XML | Những assertions có pass | Code chưa được test có đúng không |
| Số tests thật chạy | Test reports | Có bao nhiêu test đã chạy, fail, skip | Các tests có chất lượng cao không |
| LINE coverage | JaCoCo | Dòng code có executable bytecode được chạy | Tất cả ngữ nghĩa của dòng đã đúng |
| BRANCH coverage | JaCoCo | Outcomes của `if`/`switch` bytecode đã đi qua | Mọi combination hoặc mọi path |
| Security quality | Scanner, review, security tests | Một nhóm lỗ hổng/rủi ro được kiểm tra | Không có lỗ hổng chưa biết |
| Mutation score | PIT hoặc công cụ tương tự | Test có phát hiện một tập code mutations không | Mọi bug thực tế đều bị bắt |

Một pipeline **không có tests** đôi khi vẫn in `BUILD SUCCESS`. Một pipeline **có tests** vẫn có thể bỏ qua JaCoCo. Và một JaCoCo report đẹp vẫn có thể đến từ **test suite không assert kết quả**. Vì vậy phải xác minh cả ba tầng: tests đã chạy, tests pass và gate coverage thật sự được đánh giá.

## 3. Cách JaCoCo đo coverage

JaCoCo instrument và phân tích **Java bytecode**, thường bằng một Java agent được gắn vào JVM chạy tests. Counters được tính từ class files và execution data, không chỉ từ việc đếm số câu lệnh Java trong text editor.

| Counter | JaCoCo enum | Ý nghĩa |
| --- | --- | --- |
| Instructions | `INSTRUCTION` | Bytecode instructions đã chạy/chưa chạy |
| Lines | `LINE` | Source lines ánh xạ tới bytecode, cần debug line info |
| Branches | `BRANCH` | Các nhánh của `if`/`switch` ở bytecode level |
| Methods | `METHOD` | Method/constructor có ít nhất một instruction được thực thi |
| Classes | `CLASS` | Class có ít nhất một method được thực thi |
| Complexity | `COMPLEXITY` | Độ phức tạp cyclomatic từ control-flow model |

**Line coverage** cần line number information trong class files. Nếu class được compile không có debug line numbers, JaCoCo vẫn có thể đo instruction/branch, nhưng line report và source highlighting bị hạn chế.

**Branch coverage** theo JaCoCo tính `if` và `switch`; nó **không tính `catch` exception handlers là branches** theo định nghĩa counter này. Việc có 100% branch coverage không chứng minh mọi exception path được kiểm.

### 3.1. Covered ratio và counted values

JaCoCo `check` hỗ trợ các giá trị:

- `COVEREDRATIO`: tỷ lệ covered, trong khoảng **0.0 đến 1.0**.
- `MISSEDRATIO`: tỷ lệ missed.
- `COVEREDCOUNT`: số lượng covered.
- `MISSEDCOUNT`: số lượng missed.
- `TOTALCOUNT`: tổng số phần tử.

Ví dụ giả định có 90 dòng covered trong tổng 100 dòng được tính: **LINE COVEREDRATIO = 0.90 = 90%**. Nếu đi qua 3/4 outcomes của các branches: **BRANCH COVEREDRATIO = 0.75 = 75%**.

Không thể suy ra branch coverage chỉ từ số lines. Một dòng Java có thể tạo nhiều instructions/branches. Ngược lại, một method có thể được đánh dấu đã covered dù test không chạy qua tất cả branches.

### 3.2. Một dòng có thể được tô vàng

Một source line có nhiều instructions, trong đó chỉ một phần được thực thi, có thể được JaCoCo hiển thị **partially covered** (màu vàng). Theo cách tính của JaCoCo, một dòng có thể được tính là covered trong line counter nếu có ít nhất một instruction gắn với dòng đó được thực thi, dù nó còn nhánh/chỉ thị chưa chạy.

**Line coverage 100% không kéo theo branch coverage 100%.** Với short-circuit conditions hoặc `switch`, test có thể đi qua dòng nhưng không đi qua mọi đường điều khiển.

### 3.3. Compiler và bytecode cũng ảnh hưởng report

Default constructor, bridge methods, synthetic code, Java records, lambdas và annotation-generated code có thể làm counters khác với trực giác đọc source. Khi đổi JDK/compiler hoặc JaCoCo version, percentages có thể biến động dù source business logic gần như không đổi.

Không nên xem một thay đổi coverage nhỏ giữa hai compiler là bằng chứng test suite tốt lên nếu chưa đối chiếu file/class scope và bộ đếm thực.

## 4. “80%” luôn phải đi kèm phạm vi được đo

Một rule:

~~~xml
<rule>
    <element>BUNDLE</element>
    <limits>
        <limit>
            <counter>LINE</counter>
            <value>COVEREDRATIO</value>
            <minimum>0.80</minimum>
        </limit>
    </limits>
</rule>
~~~

nghĩa là: **line covered ratio của bundle phải ít nhất 80%**.

Các phần của rule:

- `<element>`: cấp áp dụng, như `BUNDLE`, `PACKAGE`, `CLASS`, `SOURCEFILE`, `METHOD`.
- `<counter>`: loại số đo, ví dụ `LINE`, `BRANCH`, `INSTRUCTION`.
- `<value>`: dạng giá trị, ví dụ `COVEREDRATIO`, `MISSEDCOUNT`.
- `<minimum>`/`<maximum>`: mức nhỏ nhất/lớn nhất được chấp nhận.

JaCoCo cho phép tỷ lệ như `0.80` hoặc `80%`. Ví dụ chọn `0.80` để một Maven property có thể truyền giá trị số thập phân dễ dàng.

| Element | Cách hiểu | Bẫy thường gặp |
| --- | --- | --- |
| `BUNDLE` | Tổng bundle của project đang được phân tích | Không đảm bảo từng class đều vượt threshold |
| `PACKAGE` | Kiểm từng package thuộc rule | Không phải trung bình của toàn bộ packages |
| `CLASS` | Kiểm từng class thuộc rule | Có thể quá nghiêm với code generated hoặc utility |
| `SOURCEFILE` | Kiểm từng source file | File có nhiều classes cần hiểu line mapping |
| `METHOD` | Kiểm từng method | 100% mọi method thường không là policy hợp lý |

Một bundle có 85% LINE coverage vẫn có thể chứa một package bảo mật **0% coverage**. Vì thế cần kết hợp coverage với risk-based tests và policy cho code quan trọng.

## 5. Maven lifecycle: JaCoCo chuẩn bị agent, Surefire chạy test, JaCoCo kiểm ngưỡng

Lệnh:

~~~bash
mvn -B clean verify
~~~

sẽ đi qua các phase theo thứ tự liên quan:

~~~text
clean
  -> initialize
       jacoco:prepare-agent
       đặt Maven property argLine với Java agent option
  -> compile
  -> test-compile
  -> test
       surefire:test trong JVM được fork
       JUnit 5 tests thực thi code ứng dụng
       JaCoCo ghi target/jacoco.exec khi JVM kết thúc
  -> package
  -> verify
       jacoco:report -> HTML/XML/CSV
       jacoco:check  -> kiểm coverage rules
~~~

**`prepare-agent` không chạy test.** Nó tạo Java agent options để JVM tests sử dụng. **`report` không tự enforce threshold**; nó tổng hợp execution data thành báo cáo. **`check` mới đánh giá rules và có thể khiến Maven exit nonzero**.

Nếu goals `report` và `check` được bind tại `verify`, chạy chỉ `mvn test` hoặc `mvn package` **chưa thực hiện gate**. Dùng `mvn verify`, thường kết hợp `clean` trong CI để tránh dữ liệu từ build cũ.

## 6. Demo đầy đủ: Maven, Java 17, JUnit 5 và JaCoCo check

Demo đo một class `ShippingPolicy` chứa bốn loại nhánh nghiệp vụ: tiền âm, miễn phí theo ngưỡng, phí thành viên, và format trạng thái miễn phí. Mục tiêu là có assertions đúng và một coverage gate thật.

### 6.1. Cấu trúc thư mục

~~~text
coverage-gate-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/quality/
    │   └── ShippingPolicy.java
    └── test/java/com/example/quality/
        └── ShippingPolicyTest.java
~~~

Project không dùng database hoặc network; build cần Maven 3.9+, JDK 17+ và repository có các plugin/dependencies được khai báo.

### 6.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>coverage-gate-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <coverage.line.minimum>0.80</coverage.line.minimum>
        <coverage.branch.minimum>0.75</coverage.branch.minimum>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>@{argLine}</argLine>
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
                <version>0.8.16</version>
                <executions>
                    <execution>
                        <id>attach-coverage-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>report-and-check</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                            <goal>check</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>${coverage.line.minimum}</minimum>
                                        </limit>
                                        <limit>
                                            <counter>BRANCH</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>${coverage.branch.minimum}</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đọc POM theo vai trò:**

1. `maven.compiler.release=17` chọn Java language/API/bytecode target cho compiler.
2. JUnit Jupiter thuộc `test` scope, không được đưa vào application JAR runtime.
3. Surefire 3.5.2 chạy JUnit 5 tests ở phase `test`.
4. `<forkCount>1</forkCount>` tạo test JVM riêng; đây là điều kiện quan trọng để agent được truyền qua `argLine`.
5. `<argLine>@{argLine}</argLine>` là **late property evaluation** của Surefire. Nó nhận Java agent option JaCoCo chuẩn bị ở initialize.
6. Property `<argLine></argLine>` là giá trị rỗng dự phòng nếu JaCoCo không thiết lập property.
7. `jacoco:prepare-agent` có default phase `initialize`, nên execution đầu không cần ghi `<phase>` riêng.
8. `jacoco:report` và `jacoco:check` được gọi ở `verify` theo thứ tự khai báo goals.
9. Các rules kiểm tổng BUNDLE `LINE >= 0.80` **và** `BRANCH >= 0.75`. Nếu một limit không thỏa, check fail.
10. `coverage.line.minimum`/`coverage.branch.minimum` là Maven properties tự đặt; cho phép thử bằng CLI `-D`.
11. JaCoCo `haltOnFailure` mặc định `true`, nên POM không bật chế độ bỏ qua failure.

**Đừng viết mỗi `<properties><coverage.line.minimum>0.80</...>` rồi tưởng Maven tự enforce nó.** Phải thực sự tham chiếu property trong `<minimum>` của JaCoCo check rule.

### 6.3. ShippingPolicy.java — production code

Tạo `src/main/java/com/example/quality/ShippingPolicy.java`:

~~~java
package com.example.quality;

public final class ShippingPolicy {

    private ShippingPolicy() {
        // Utility class không nên được tạo instance.
    }

    public static int feeCents(int subtotalCents, boolean member) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be non-negative");
        }

        if (subtotalCents >= 10_000) {
            return 0;
        }

        if (member) {
            return 200;
        }

        return 500;
    }

    public static String label(int feeCents) {
        if (feeCents == 0) {
            return "FREE";
        }
        return "PAID " + feeCents;
    }

    public static String summary() {
        return "Member: " + label(feeCents(5_000, true))
                + "\nGuest: " + label(feeCents(5_000, false))
                + "\nLarge order: "
                + label(feeCents(10_000, false));
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
~~~

Tiền dùng integer **cents** để tránh lỗi làm tròn của floating point ở ví dụ đơn giản. `feeCents` có ba điều kiện quan trọng: giá trị âm, ngưỡng miễn phí, và cờ thành viên. `label` có một điều kiện nữa.

JaCoCo đo branches từ bytecode. Test chỉ chạy nhánh thành viên `true` mà không chạy `false` thì branch coverage không đầy đủ, dù method đã được gọi và có những dòng đã covered.

### 6.4. ShippingPolicyTest.java — 6 test methods có assertions

Tạo `src/test/java/com/example/quality/ShippingPolicyTest.java`:

~~~java
package com.example.quality;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> ShippingPolicy.feeCents(-1, false));
        assertEquals("subtotalCents must be non-negative",
                error.getMessage());
    }

    @Test
    void makesLargeOrdersFree() {
        assertEquals(0, ShippingPolicy.feeCents(10_000, false));
    }

    @Test
    void chargesMembersLess() {
        assertEquals(200, ShippingPolicy.feeCents(5_000, true));
    }

    @Test
    void chargesGuestsStandardRate() {
        assertEquals(500, ShippingPolicy.feeCents(5_000, false));
    }

    @Test
    void labelsFreeAndPaidRates() {
        assertEquals("FREE", ShippingPolicy.label(0));
        assertEquals("PAID 500", ShippingPolicy.label(500));
    }

    @Test
    void mainPrintsExpectedSummary() {
        PrintStream previous = System.out;
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (PrintStream capture = new PrintStream(
                buffer, true, StandardCharsets.UTF_8)) {
            System.setOut(capture);
            ShippingPolicy.main(new String[0]);
        } finally {
            System.setOut(previous);
        }

        String normalized = buffer.toString(StandardCharsets.UTF_8)
                .replace("\r\n", "\n");
        assertEquals(
                "Member: PAID 200\n"
                        + "Guest: PAID 500\n"
                        + "Large order: FREE\n",
                normalized);
    }
}
~~~

**Có sáu methods gắn `@Test`:** kiểm exception, phí miễn, phí thành viên, phí khách thường, định dạng và stdout `main`.

Mỗi test **assert kết quả mong đợi**, không chỉ gọi hàm để tăng line coverage. Trong các methods nghiệp vụ, các outcomes của `if` được test đi qua. Private constructor không được gọi, nên có thể còn một phần code chưa covered.

Trong test cuối, `System.out` bị đổi tạm thời rồi khôi phục trong `finally`. Ví dụ chạy một suite nhỏ với JUnit parallel execution mặc định không bật. Nếu dùng parallel tests thật, nên tránh sửa global `System.out` hoặc dùng một cấu trúc truyền output stream để các tests không tranh chấp.

### 6.5. Chạy build và đọc báo cáo

Tại thư mục có `pom.xml`:

~~~bash
mvn -version
java -version
mvn -B clean verify
~~~

Kỳ vọng nếu Java/Maven/repositories hợp lệ:

- Compiler build class Java 17.
- Surefire chạy 6 JUnit 5 tests, không failure.
- JaCoCo agent ghi `target/jacoco.exec`.
- `jacoco:report` tạo HTML/XML/CSV.
- `jacoco:check` đánh giá `LINE >= 0.80` và `BRANCH >= 0.75` ở cấp bundle.
- Gate được kỳ vọng pass với các test cases đã có.
- Maven kết thúc `BUILD SUCCESS` nếu không có lỗi khác.

Đường dẫn báo cáo điển hình:

~~~text
target/
├── jacoco.exec
├── site/jacoco/
│   ├── index.html
│   ├── jacoco.xml
│   └── jacoco.csv
└── surefire-reports/
    ├── com.example.quality.ShippingPolicyTest.txt
    └── TEST-com.example.quality.ShippingPolicyTest.xml
~~~

**Không đoán một tỷ lệ phần trăm chính xác bằng cách đếm source lines thủ công**; xem JaCoCo report được tạo từ compiled class files. Trong code mẫu, một số constructors/line mappings có thể ảnh hưởng ratios, nên bài chỉ nêu đúng **ngưỡng** và expected pass, không khẳng định một tỷ lệ cụ thể chưa được đo.

### 6.6. Chạy `main` và stdout chính xác

Sau khi compile/verify, từ project root:

~~~bash
java -cp target/classes com.example.quality.ShippingPolicy
~~~

**Stdout chính xác từ ứng dụng:**

~~~text
Member: PAID 200
Guest: PAID 500
Large order: FREE
~~~

Lệnh `java -cp` này không được tự động gắn JaCoCo Java agent. Nó không cập nhật `target/jacoco.exec` theo cấu hình plugin hiện tại. Coverage của demo đến từ các **JVM chạy Surefire tests**.

## 7. Chứng minh cổng thất bại khi ngưỡng cao hơn số đo

Trong POM demo, bạn có thể override threshold bằng Maven CLI, không sửa file POM:

~~~bash
mvn -B -Dcoverage.line.minimum=1.00 clean verify
~~~

Lệnh yêu cầu **BUNDLE LINE coverage 100%**. Class `ShippingPolicy` có private constructor không được tests gọi, nên JaCoCo thường ghi nhận ít nhất một phần executable bytecode chưa covered. Vì vậy lệnh trên được kỳ vọng khiến `jacoco:check` fail ở verify với thông báo tương đương **“Coverage checks have not been met”**.

Một số details của line counts phụ thuộc compiler/debug information. Nếu report thực trên một toolchain khác cho kết quả bất ngờ, **xem measured ratio trong XML/HTML rồi chọn threshold thực sự cao hơn nó**; không coi một số 100% viết trong bài là số đo universal.

Lệnh để trở về defaults:

~~~bash
mvn -B clean verify
~~~

`-Dcoverage.line.minimum=1.00` là **override chỉ trong invocation**, không sửa `<coverage.line.minimum>0.80</coverage.line.minimum>` của POM.

### Maven exit status không phải coverage percentage

Nếu JaCoCo check fail thì **Maven command** trả nonzero và CI có thể chặn bước publish. Không được suy Maven exit code phải bằng một coverage count hay tỷ lệ. Đọc log/report để biết rule nào vi phạm.

Không dùng:

~~~bash
mvn -Djacoco.haltOnFailure=false clean verify
~~~

như một cách chữa build đỏ. Cách này bỏ cơ chế chặn build khi check thất bại; nếu muốn chạy báo cáo **audit-only**, phải gọi chính xác là *non-blocking report*, không tuyên bố *enforced gate*.

## 8. Khi nào `mvn test` không đủ?

| Lệnh | Surefire tests | JaCoCo report/check ở verify | Ý nghĩa |
| --- | --- | --- | --- |
| `mvn test` | Chạy | Không | Chưa đánh giá gate như cấu hình demo |
| `mvn package` | Chạy | Không | Chưa qua verify |
| `mvn verify` | Chạy | Chạy | Đánh giá thresholds nếu instrumentation/data đúng |
| `mvn clean verify` | Chạy, dọn output cũ | Chạy | Phù hợp baseline/CI |
| `mvn -DskipTests verify` | Có thể skip | Có thể skip do thiếu data | Không chứng minh coverage |
| `mvn -Djacoco.skip=true verify` | Có thể vẫn chạy | Không đo/kiểm theo mong đợi | Không chứng minh coverage |

Với gate đặt ở verify, **không kết luận “đã qua coverage gate” từ `mvn package`**. Một release pipeline cần chọn lifecycle phase và các profiles/options đúng.

## 9. Bẫy: thiếu `jacoco.exec` có thể khiến check bị skip

Theo tài liệu JaCoCo, khi không có execution data file, report/check có thể log:

~~~text
Skipping JaCoCo execution due to missing execution data file
~~~

và **bỏ qua bước phân tích**. Khi đó Maven vẫn có khả năng kết thúc `BUILD SUCCESS` dù cổng chưa thật sự đo được gì.

Các nguyên nhân:

1. Không có tests.
2. Surefire không phát hiện tên class test đúng.
3. `-DskipTests` hoặc `-Dmaven.test.skip=true`.
4. `-Djacoco.skip=true`.
5. `forkCount=0`/không tạo JVM test có agent.
6. `<argLine>` của Surefire bị override, mất `-javaagent`.
7. Test JVM chết bất thường trước khi ghi data.
8. `destFile` của agent và `dataFile` của report/check không giống nhau.
9. Report đang chạy trong **module khác** với module đã tạo `jacoco.exec`.

**Không coi skip do thiếu file là một gate pass có ý nghĩa.** CI nên kiểm tra cả số tests thật chạy, file JaCoCo mới và log/report check.

### Guard cơ bản trong POSIX CI

Sau Maven step:

~~~bash
mvn -B clean verify
test -s target/jacoco.exec
test -s target/site/jacoco/jacoco.xml
~~~

`test -s` kiểm file tồn tại và không rỗng. Đây **mới chỉ là guard cơ bản**, chưa xác nhận test count hoặc metadata của commit, và chỉ áp dụng cho shell POSIX.

### Guard cơ bản trong PowerShell

~~~powershell
if (-not (Test-Path "target/jacoco.exec")) {
    throw "JaCoCo execution data missing"
}
if (-not (Test-Path "target/site/jacoco/jacoco.xml")) {
    throw "JaCoCo XML coverage report missing"
}
~~~

Khi triển khai pipeline release, thêm bước parse JUnit XML để đảm bảo suite bắt buộc có số tests lớn hơn 0 và số skipped nằm trong policy. Một report file từ build trước không được tái sử dụng làm bằng chứng cho commit hiện tại.

## 10. JaCoCo agent và late `argLine` của Surefire

`jacoco:prepare-agent` tạo property `argLine` chứa phần `-javaagent` cần cho forked JVM. Nếu Surefire có:

~~~xml
<argLine>@{argLine}</argLine>
~~~

thì Surefire hỗ trợ **late property evaluation** để lấy giá trị JaCoCo vừa thiết lập. Khi muốn thêm heap option:

~~~xml
<argLine>@{argLine} -Xmx512m</argLine>
~~~

Ngược lại, nếu bạn đặt cứng:

~~~xml
<argLine>-Xmx512m</argLine>
~~~

và vô tình bỏ agent option, test có thể chạy bình thường nhưng không tạo coverage data.

### `forkCount=0` là nguyên nhân quan trọng

Khi Surefire/Failsafe chạy không fork, Java agent option do JaCoCo chuẩn bị **không được áp dụng như một JVM startup flag mới** lên Maven JVM đang chạy sẵn. Tài liệu JaCoCo cảnh báo không dùng `forkCount=0` hoặc chế độ forkMode `never` nếu muốn data ghi từ agent như cấu hình Maven plugin.

Ví dụ giữ `<forkCount>1</forkCount>` và kiểm log của plugin. **Không suy ra `mvn -version` là thông tin đầy đủ của test JVM/toolchain** nếu project có cấu hình forked test JDK riêng.

## 11. Đặt ngưỡng theo mức rủi ro, không theo một “con số thần kỳ”

Các dự án có đặc điểm khác nhau:

- Library logic có nhiều branches/conditions.
- Web controllers mỏng, behavior quan trọng nằm trong integration/HTTP test.
- Generated DTO/client code không mang nhiều logic handwritten.
- Legacy system có tổng coverage thấp nhưng code mới cần kiểm chặt.
- Authorization/payment logic có rủi ro cao dù chỉ vài chục dòng.

Một chính sách thực dụng:

1. Đo **baseline** bằng clean CI build.
2. Xem missed lines/branches theo package/class.
3. Phân loại source code do team viết, generated code, framework glue và platform internals.
4. Đặt ngưỡng initial không làm pipeline fail vô nghĩa; ví dụ LINE ≥ 0.75 và BRANCH ≥ 0.60 chỉ là số minh họa, **không phải chuẩn phổ quát**.
5. Ưu tiên bổ sung assertions cho các luồng nghiệp vụ rủi ro cao.
6. Tăng threshold có review khi test suite cải thiện.
7. Kết hợp policy cho **code mới/thay đổi** nếu có công cụ VCS diff hỗ trợ.
8. Ghi nhận mọi exclusion và lý do của nó.
9. Không dùng `haltOnFailure=false` hay skip flags để che suy giảm coverage.
10. Theo dõi cả flaky tests và khả năng tái hiện.

Coverage threshold là **guardrail**. Nó hỗ trợ kỹ sư phát hiện vùng thiếu test, nhưng không thể thay lời đánh giá security/architecture/domain correctness.

## 12. Tỷ lệ BUNDLE cao vẫn có thể che class rất rủi ro

Xét dữ liệu minh họa:

| Thành phần | Covered lines | Total lines | Tỷ lệ |
| --- | ---: | ---: | ---: |
| Helpers và formatters | 900 | 1.000 | 90% |
| Authorization rules | 0 | 50 | 0% |
| Tổng | 900 | 1.050 | Khoảng 85,71% |

Một gate **BUNDLE LINE ≥ 80%** vẫn pass, mặc dù toàn bộ Authorization rules chưa được kiểm thử.

Những hành động phù hợp hơn việc chỉ nâng toàn bundle lên 90%:

- Viết unit tests cho allow/deny, role, resource ownership, invalid identity.
- Viết integration tests qua auth middleware/API thực.
- Chọn một gate/rule cho package/class trọng yếu nếu cách đo phù hợp.
- Dùng threat modeling và security review.
- Test negative cases, boundary values, data isolation.
- Theo dõi coverage của code mới hoặc code thay đổi để ngăn tích thêm nợ.

**Chất lượng một nhánh nguy hiểm không thể bị “bù” bằng nghìn dòng util được test kỹ.**

## 13. Rule ở cấp CLASS và các exclusions

Có thể bổ sung rule cho từng class:

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
        </limits>
    </rule>
    <rule>
        <element>CLASS</element>
        <excludes>
            <exclude>*Generated*</exclude>
        </excludes>
        <limits>
            <limit>
                <counter>LINE</counter>
                <value>COVEREDRATIO</value>
                <minimum>0.50</minimum>
            </limit>
        </limits>
    </rule>
</rules>
~~~

Đây là **fragment thay thế phần `<rules>`**, không phải một POM hoàn chỉnh. `*Generated*` chỉ minh họa một pattern; một dự án thực phải kiểm danh sách classes bị match và review policy.

Điểm quan trọng:

- Rule CLASS có thể kiểm **mỗi class** riêng.
- Rule BUNDLE kiểm tổng, **không tự áp cùng tỷ lệ cho từng class**.
- `<excludes>` trong một **check rule** chỉ ảnh hưởng phạm vi rule ấy, không nhất thiết xóa class khỏi toàn bộ JaCoCo report.
- Agent instrumentation excludes, report excludes và check rule excludes là **các lớp cấu hình khác nhau**.
- Không được loại tất cả class “khó test” để đưa coverage lên cao một cách giả tạo.

Generated code có thể được loại nếu thực sự ít giá trị unit test handwritten, nhưng vẫn cần tests cho generator/contracts hoặc integration. Không bỏ qua code có business logic chỉ vì file được tool sinh.

## 14. “Có 100% line coverage” vẫn có thể có bug

Hàm minh họa:

~~~java
public static int price(boolean vip) {
    if (vip) {
        return 100;
    }
    return 200;
}
~~~

Nếu test chỉ gọi `price(true)` rồi assert rằng kết quả **lớn hơn 0**, nó có thể tăng coverage nhưng **không phát hiện** một bug khiến `price(true)` trả 200 thay vì 100.

Ngay cả khi gọi cả `price(true)` và `price(false)`, nếu hai tests chỉ assert kết quả dương, branch coverage có thể đạt 100% đối với hàm trên, nhưng assertions vẫn yếu.

Vì vậy cần:

- Assert **giá trị nghiệp vụ chính xác**.
- Test cả valid và invalid inputs.
- Test giá trị ngay trước, tại và sau boundary.
- Test side effects và state changes khi có.
- Test error messages/types khi thuộc contract.
- Dùng integration tests với dependencies thật cho các behavior liên thành phần.

**100% line/branch coverage không tương đương full path coverage**. Ba `if` có thể tạo nhiều tổ hợp outcomes; từng `if` được thử hai phía không chứng minh mọi tổ hợp đã được test. JaCoCo branch coverage cũng không phải MC/DC hoặc kiểm hết concurrency interleavings.

## 15. Boundary tests có thể bắt lỗi mà coverage không thể diễn giải

Trong demo:

~~~java
if (subtotalCents >= 10_000) {
    return 0;
}
~~~

Một bug đơn giản:

~~~java
if (subtotalCents > 10_000) {
    return 0;
}
~~~

Nếu test chỉ gọi `subtotalCents=12_000`, cả hai versions có thể trả cùng kết quả 0. Test tại đúng **10.000** mới phân biệt `>=` với `>`.

Bảng test case bổ sung có giá trị:

| Input | Expected | Lý do |
| --- | --- | --- |
| -1, guest | Exception | Input invalid |
| 0, guest | 500 | Lower boundary valid |
| 5.000, member | 200 | Member path |
| 5.000, guest | 500 | Non-member path |
| 9.999, guest | 500 | Ngay dưới threshold |
| 10.000, guest | 0 | Đúng threshold |
| 10.001, member | 0 | Sau threshold |
| `label(0)` | FREE | Định dạng free |
| `label(500)` | PAID 500 | Định dạng paid |

**Bảng này chứa các case mở rộng chưa có hết trong 6 tests mẫu**. Nó là gợi ý nâng assertions/edge-case coverage, không phải báo cáo kết quả tests đã chạy.

## 16. Mutation testing đo khả năng tests nhận ra lỗi

**Mutation testing** tạo các biến thể của code như đổi `>=` thành `>`, đảo boolean, thay constant trả về hoặc xóa condition. Sau đó chạy tests:

- Mutant **killed** nếu tests phát hiện qua failure.
- Mutant **survived** nếu tests vẫn pass dù code bị đổi.
- Một số mutants **equivalent** hoặc không có ý nghĩa nghiệp vụ, cần đánh giá.

Với ví dụ ngưỡng miễn phí, test tại 10.000 có thể *kill* mutant đổi `>=` thành `>`.

Mutation testing bổ sung cho code coverage. Code có 100% LINE nhưng assertions yếu thường có mutants sống sót. Dù vậy mutation score cũng không phải tuyệt đối: có giới hạn tập mutations, equivalent mutants, chi phí thực thi và flaky tests.

Trong Maven ecosystem có **PIT Mutation Testing**, nhưng ví dụ POM ở phần 6 không bắt buộc chạy PIT; nó chủ đích minh họa **JaCoCo quality gate** trước khi mở rộng thêm công cụ.

## 17. Coverage của unit tests không tự bao gồm integration tests

Trong demo chỉ cấu hình:

- Surefire ở phase `test`.
- JaCoCo `prepare-agent` cho forked Surefire JVM.
- Report/check dựa trên `target/jacoco.exec`.

**Không có Failsafe integration tests**, service backend hoặc database. Vì vậy tỷ lệ ở demo phản ánh **những lần thực thi production code bởi unit tests**.

Khi ứng dụng có Failsafe, cần thiết kế:

1. `jacoco:prepare-agent-integration` cho integration tests.
2. `jacoco:report-integration` để tạo báo cáo IT riêng.
3. File `jacoco-it.exec` hoặc file do dự án cấu hình.
4. `jacoco:merge` nếu muốn gộp execution data phù hợp.
5. `jacoco:report-aggregate` cho một tập multi-module nếu cần.
6. Quy tắc check/gate áp lên đúng file và đúng phạm vi.

**Không chỉ thêm `maven-failsafe-plugin` rồi khẳng định JaCoCo BUNDLE đã tính cả integration tests.** Nếu test gọi một HTTP server nằm trong process khác, JVM của server đó cũng cần instrumentation/thu thập data nếu muốn đo code server được chạy qua request.

### 17.1. Vì sao Failsafe `verify` quan trọng?

Failsafe thường chạy `integration-test` rồi kiểm kết quả tại `failsafe:verify`. `mvn verify` đi qua `post-integration-test` cleanup trước khi kết luận lỗi IT. Trong pipeline có integration coverage, phải thiết kế lifecycle/số liệu để check coverage diễn ra sau các bước test cần đo.

Nếu một test fail ở phase trước verify, Maven có thể dừng sớm và không tạo JaCoCo HTML report; CI nên lưu lại logs/execution data có được và điều tra test failure trước.

## 18. Multi-module: `BUNDLE` thường là phạm vi từng module, không phải cả reactor

Một Maven reactor:

~~~text
root/pom.xml            (packaging=pom)
├── domain-core
├── persistence
├── web-api
└── coverage-report
~~~

Nếu JaCoCo `check` được bind trong từng child, `BUNDLE` thường là **classes của từng project** mà goal đang chạy. Root aggregator `packaging=pom` không tự có Java class files của tất cả modules để đo.

Do đó:

- `domain-core` có thể pass threshold.
- `web-api` có thể fail.
- Một module dùng riêng cho reports có thể tạo **aggregate report**.
- Không nên gọi số aggregate đó là bằng chứng tất cả modules đã pass **per-module gate**.

`report-aggregate` là công cụ tạo báo cáo, **không tự biến mọi aggregate statistic thành một `jacoco:check` enforcement** theo đúng cách kiểm BUNDLE của project con.

Khi cần overall gate:
- Xác định các module/classes được đưa vào aggregate.
- Quy định test suite nào chạy và data files nào được thu thập.
- Dùng quality platform hoặc công cụ kiểm XML/aggregate phù hợp.
- Cân nhắc thêm per-package/per-module thresholds để tránh một module lớn bù cho code chưa test ở module rủi ro cao.

## 19. Coverage của code mới và code thay đổi

Một hệ thống legacy có hàng trăm nghìn dòng, coverage tổng 50%. Nếu thêm 20 dòng code quan trọng không có test, tổng percentage có thể chỉ tụt rất ít.

Một số tổ chức kết hợp:

- **Overall coverage**: tránh chất lượng giảm dài hạn.
- **New/changed code coverage**: kiểm những dòng thay đổi theo Git diff/PR baseline.
- **Critical package rules**: yêu cầu tests cho security/payment/domain.
- **Mutation score** hoặc assertions review cho behavior quan trọng.

JaCoCo `BUNDLE` check **không tự phân tích Git diff** để biết dòng nào mới. Muốn quality gate cho changed lines cần kết hợp source control và công cụ có chức năng đó; không ghi `minimum=0.80` rồi mô tả là “mọi dòng mới đều có 80% coverage”.

## 20. Exclusions và số liệu giả tăng

Giả sử report tính 100 dòng, tests cover 70 dòng → 70%. Nếu exclude 20 dòng chưa chạy, mẫu số còn 80 và coverage thành 70/80 → 87.5%.

**Đây là một thay đổi phạm vi đo**, không phải test suite tốt hơn.

Những lý do exclusion có thể hợp lệ:

- Class hoàn toàn generated từ schema, có tests xác nhận generator/contract.
- Framework plumbing không chứa business logic và khó kiểm phù hợp với suite này.
- Code đặc thù OS/native được test trong matrix khác với coverage gate chính.

Những lý do không nên chấp nhận:

- “Class này 0% nên bỏ ra cho xanh”.
- “Code permission checks khó test nên exclude”.
- “Chỉ cần tăng report cho dashboard đẹp”.

Mọi exclusion nên được review, ghi scope rõ và kiểm tra các classes thực tế bị loại. **Coverage là số đo có điều kiện theo denominator**; khi mẫu số đổi, phải công bố phạm vi đo.

## 21. CI gate cần kiểm không bị bypass

Một pipeline gợi ý:

~~~text
Checkout exact commit
    |
    v
Pin Maven/JDK/JaCoCo/Surefire versions
    |
    v
mvn -B clean verify
    |
    +-- Compiles?
    +-- Required test suites executed and passed?
    +-- No unauthorized skip flags?
    +-- JaCoCo agent recorded execution data?
    +-- Report exists and uses correct bytecode/scope?
    +-- jacoco:check ran and passed thresholds?
    |
    v
Upload JUnit/coverage reports (also on failure)
    |
    v
Additional security/static/mutation checks
    |
    v
Publish artifacts only if gates pass
~~~

Các điều kiện report-presence/test-count và security checks trong sơ đồ cần được triển khai ở **CI**, không tự xuất hiện chỉ vì POM chứa JaCoCo Plugin.

Cờ có thể làm vô hiệu ý nghĩa gate:

~~~text
-DskipTests
-Dmaven.test.skip=true
-Djacoco.skip=true
-Djacoco.haltOnFailure=false
~~~

Nếu contributor có thể sửa pipeline hoặc gọi Maven với:

~~~bash
mvn -B -Dcoverage.line.minimum=0.01 clean verify
~~~

thì người đó đã **hạ policy** để dễ pass. Với branch protection, threshold phải được kiểm soát trong cấu hình review/CI đáng tin hoặc có mechanism phát hiện unauthorized overrides.

Một quality gate tốt **không trao cho chính tác giả thay đổi quyền âm thầm hạ ngưỡng** mà vẫn báo “protected checks passed”.

## 22. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Build xanh nhưng không có coverage XML | JaCoCo report bị skip hoặc chưa tới verify | Log JaCoCo goals, file data, lifecycle |
| Không có `target/jacoco.exec` | Tests không chạy hoặc agent không gắn | Surefire test count, argLine, forkCount |
| Test pass nhưng LINE=0% | Agent/data file mismatch, class files không khớp | Kiểm agent log, dataFile và compiled classes |
| `mvn test` pass nhưng quality gate không được kiểm | Gate ở phase verify | Dùng `mvn verify` |
| CI đỏ dù HTML báo ~80% | Counter/rule khác, rounding, threshold override | So log check, XML metrics và effective POM |
| LINE cao, BRANCH thấp | Thiếu invalid/negative/boundary cases | Đọc branch report, thêm meaningful assertions |
| Tổng BUNDLE pass nhưng class quan trọng 0% | Aggregate che region có rủi ro | Per-class/package policy và risk tests |
| Coverage tụt sau đổi JDK | Bytecode/line mapping hoặc synthetic methods đổi | So toolchain và class files |
| Coverage tăng sau exclude | Denominator giảm | Audit exclusions và review phạm vi đo |
| Report vẫn xanh dù không có tests | Stale `jacoco.exec`/reports, check skip | Clean build, kiểm reports mới/test count |
| Không có JaCoCo agent trong fork | Surefire `<argLine>` ghi đè | Dùng `@{argLine}` đúng cách |
| Tests chạy trong Maven JVM | `forkCount=0` | Bật fork để agent hoạt động |
| App runtime coverage thấp dù IT pass | IT gọi process/server khác chưa instrument | Instrument server hoặc merge data phù hợp |
| Multi-module report thiếu class | Aggregate setup/module selection sai | Xem project list, artifacts, data files |
| `jacoco:check` fail ngay sau thêm một class | Class mới làm missed total tăng | Viết tests hoặc review rule/baseline |
| 100% branch mà bug `>` vs `>=` lọt | Tests thiếu boundary assertion | Thử threshold boundary, mutation tests |
| Maven test failed nên report không có | Lifecycle dừng trước verify | Đọc Surefire failure trước, giữ logs |
| “0 skipped” nhưng suite quan trọng không có | Test naming/provider/excludes sai | Kiểm suite inventory và JUnit XML |
| Dev chạy `-Djacoco.skip=true` rồi bảo gate pass | Cấu hình bị bypass | Chính sách CI, kiểm JaCoCo check evidence |
| Private constructor làm mất 100% LINE | Constructor không được gọi, vẫn có bytecode | Review source/metric, không tạo fake test chỉ vì số |
| JUnit XML reports chứa secret | Test log config/token | Redaction, không in secrets, hạn chế report access |

## 23. Quy trình debug ngắn

**Bước 1 — Kiểm Maven/JDK:**

~~~bash
mvn -version
java -version
~~~

**Bước 2 — Xem effective POM:**

~~~bash
mvn help:effective-pom
~~~

Tìm JaCoCo version, executions `prepare-agent`, `report`, `check`, `<rules>`, property thresholds, Surefire `forkCount` và `<argLine>`.

**Bước 3 — Build từ dữ liệu sạch:**

~~~bash
mvn -B clean verify
~~~

Xem log thứ tự test → report → check. Nếu tests fail, xử lý lỗi đầu tiên thay vì gọi `jacoco:check` thủ công để “cho xanh”.

**Bước 4 — Xem test report và số tests:**

~~~text
target/surefire-reports/
target/surefire-reports/TEST-com.example.quality.ShippingPolicyTest.xml
~~~

Dự kiến 6 tests trong suite demo. Đọc chính xác `tests`, `failures`, `errors`, `skipped`.

**Bước 5 — Kiểm execution/report files:**

~~~text
target/jacoco.exec
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
~~~

`.exec` là binary, không phải JSON/XML. XML có counters phục vụ tools khác; HTML thích hợp để developer xem dòng/branch chưa được thực thi.

**Bước 6 — Thử hạ hoặc nâng threshold có chủ đích trong sandbox:**

~~~bash
mvn -B -Dcoverage.line.minimum=1.00 clean verify
~~~

Xem fail ở JaCoCo check và log ratio measured. Sau đó chạy lại defaults:

~~~bash
mvn -B clean verify
~~~

**Bước 7 — Điều tra các ngoại lệ:**

- Có skip flags hoặc profile khác không?
- `argLine` có agent không?
- Mismatch `destFile`/`dataFile`?
- Build đang xử lý module nào?
- Report có stale data?
- Exclusions có thay đổi?
- Test có assert business behavior?
- Với IT, process của backend có instrument không?
- Threshold có bị override bởi CI?
- Artifact có được publish dù Maven status nonzero không?

## 24. Bài tập tự kiểm tra

**Câu 1.** `LINE COVEREDRATIO=0.80` có nghĩa 80% code là đúng không?

**Đáp:** Không. Nó chỉ đo tỷ lệ executable lines được JaCoCo xác định là covered trong phạm vi đã phân tích.

**Câu 2.** BUNDLE LINE 80% có bắt mọi CLASS LINE 80% không?

**Đáp:** Không; rule áp tổng bundle, class riêng có thể rất thấp.

**Câu 3.** BRANCH của JaCoCo có tính `catch` là một branch không?

**Đáp:** Không theo định nghĩa counter này. Exception paths vẫn phải được test khi cần.

**Câu 4.** `prepare-agent` có trực tiếp thực thi JUnit tests không?

**Đáp:** Không. Nó chuẩn bị Java agent options; Surefire/Failsafe thực thi tests.

**Câu 5.** `mvn test` có chạy JaCoCo check tại verify không?

**Đáp:** Không, vì lifecycle dừng trước verify.

**Câu 6.** Nếu không có `jacoco.exec`, Maven vẫn có thể thành công không?

**Đáp:** Có. JaCoCo check/report có thể skip khi không có data, nên CI phải xác nhận đã đo thật.

**Câu 7.** `forkCount=0` có phù hợp để JaCoCo gắn agent vào Surefire JVM không?

**Đáp:** Không theo cơ chế chuẩn được tài liệu hóa; JVM test không nhận startup `-javaagent` mới như một fork.

**Câu 8.** 100% branch có đồng nghĩa kiểm mọi combination inputs không?

**Đáp:** Không. Branch coverage không phải full path hoặc exhaustive condition coverage.

**Câu 9.** Đặt `minimum=0.80` có tự kiểm coverage code mới trong Git diff không?

**Đáp:** Không. JaCoCo BUNDLE không tự biết dòng mới; cần changed-code tool/policy riêng.

**Câu 10.** Tại sao đổi `>= 10_000` thành `> 10_000` có thể lọt qua tests chỉ thử 12.000?

**Đáp:** Vì cả hai biểu thức true ở 12.000. Test đúng boundary 10.000 mới phân biệt.

**Câu 11.** Exclude 20 dòng chưa test làm percentage tăng có chứng minh assertions tốt hơn không?

**Đáp:** Không. Mẫu số đã giảm nên tỷ lệ thay đổi dù không có test mới.

**Câu 12.** `jacoco.haltOnFailure=false` dùng ở protected release gate có phù hợp không?

**Đáp:** Không. Nó có thể không chặn build khi rules bị vi phạm.

**Câu 13.** Có thể dùng report-aggregate thay mọi per-module check trong Maven Reactor không?

**Đáp:** Không mặc định. Phải thiết kế mục tiêu aggregate/per-module và công cụ enforce cụ thể.

**Câu 14.** Coverage của Surefire unit tests có tự bao gồm code thực thi trong HTTP server process ngoài không?

**Đáp:** Không. Server process phải được instrument và dữ liệu được thu thập/gộp đúng.

**Câu 15.** Một test chỉ gọi method nhưng không assert có thể làm coverage tăng không?

**Đáp:** Có, dù nó hầu như không xác minh tính đúng đắn.

**Câu 16.** Mutation testing giúp đánh giá gì?

**Đáp:** Test suite có phát hiện các thay đổi nhỏ làm sai behavior không; đây là thông tin bổ sung cho execution coverage.

**Câu 17.** Vì sao `target/site/jacoco/jacoco.xml` cần được lưu khi gate fail?

**Đáp:** Để developer xem measured counters và missed code; không nên chỉ upload reports sau build thành công.

**Câu 18.** Tại sao cần kiểm số JUnit tests thực chạy?

**Đáp:** Build có thể xanh dù suite bị skip, không phát hiện hoặc test inventory trống.

**Câu 19.** Có nên đặt một threshold giống hệt cho mọi library, generated DTO và security package?

**Đáp:** Không nhất thiết. Policy phải xét ownership, testing strategy và rủi ro.

**Câu 20.** Khi LINE 95% nhưng một authorization class 0%, cổng nên đánh giá điều gì thêm?

**Đáp:** Test nghiệp vụ/negative security scenarios của class ấy, risk-based gate theo package/class và changed-code policy; không chỉ tỷ lệ chung.

## 25. Checklist tích hợp quality gate vào Maven/CI

1. Xác định đúng modules/classes là đối tượng đo.
2. Pin JaCoCo/Surefire/Failsafe/Maven/JDK versions.
3. Gắn `prepare-agent` ở trước test JVM.
4. Giữ `forkCount>0` cho test JVM cần JaCoCo.
5. Đảm bảo `@{argLine}` giữ `-javaagent`.
6. Đặt `report` trước `check` trong execution tại verify.
7. Chọn `BUNDLE` hoặc rule PACKAGE/CLASS phù hợp.
8. Chọn `LINE`/`BRANCH` thay vì dùng một metric duy nhất theo quán tính.
9. Hiểu `0.80 = 80%`, không phải 80 dòng.
10. Giữ `haltOnFailure=true` trong gate bắt buộc.
11. Chạy `mvn -B clean verify` trong CI baseline.
12. Kiểm số tests >0 và tỷ lệ skip phù hợp policy.
13. Kiểm file execution data/report XML tồn tại và không stale.
14. Xem log `jacoco:check` thực sự thực thi thay vì skip.
15. Không cho phép PR âm thầm hạ threshold qua CLI.
16. Không dùng `skipTests`, `jacoco.skip` hay `fail-never` cho release gate.
17. Dùng boundary, invalid và negative tests có assertions đúng.
18. Không để BUNDLE tổng cao che code nghiệp vụ trọng yếu 0%.
19. Có policy minh bạch cho generated code và exclusions.
20. Dùng review hoặc mutation testing để đánh giá test strength.
21. Cân nhắc changed-code coverage thay vì chỉ overall coverage.
22. Với integration tests, instrument đúng JVM và report data.
23. Với Reactor nhiều module, xác định per-module vs aggregate gate.
24. Lưu JUnit/JaCoCo reports kể cả khi check fail.
25. Dùng reports từ build clean cùng commit/versions để so trend.
26. Không diễn giải coverage thành xác suất code đúng hoặc không có lỗi.
27. Kết hợp security, static analysis, integration, load và mutation checks theo rủi ro.
28. Chặn publish nếu Maven verify trả nonzero.
29. Ghi lại versions, thresholds, test counts và exclusions của release.
30. Review ngưỡng định kỳ khi codebase/test suites thay đổi.

## Tài liệu tham khảo chính thức

- [JaCoCo — Maven Plugin](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html)
- [JaCoCo — prepare-agent goal](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)
- [JaCoCo — report goal](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)
- [JaCoCo — check goal, rules và limits](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JaCoCo — Official Stable Releases](https://www.jacoco.org/jacoco/index.html)
- [JaCoCo — prepare-agent-integration goal](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-integration-mojo.html)
- [Apache Maven Surefire — FAQ về argLine và JaCoCo](https://maven.apache.org/surefire/maven-surefire-plugin/faq.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Failsafe — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)
- [PIT Mutation Testing — Maven Quickstart](https://pitest.org/quickstart/maven/)

