# JaCoCo: thu thập dữ liệu độ bao phủ và tạo báo cáo trong Maven

**JaCoCo (Java Code Coverage)** là công cụ theo dõi mức độ mã Java được thực thi trong một tập lần chạy, thường là unit tests và integration tests. JaCoCo instrument bytecode bằng **Java agent**, lưu execution data vào `*.exec`, rồi dùng class files và source code tương ứng để tạo các báo cáo **HTML, XML, CSV**. Trong Maven, ba goal cơ bản là `jacoco:prepare-agent`, `jacoco:report` và `jacoco:check`.

**Ba hoạt động cần phân biệt rõ:**

1. **Thu thập dữ liệu:** test JVM có JaCoCo agent thì các probes được ghi nhận và lưu thành execution data.
2. **Tạo báo cáo:** JaCoCo phân tích data + class/source files, sinh báo cáo coverage theo class/package/source file.
3. **Áp cổng chất lượng:** một quy tắc coverage (ví dụ LINE ≥ 70%) được thực thi bởi `jacoco:check` hoặc CI/quality server. Chỉ tạo HTML đẹp **không làm build fail** khi coverage thấp.

Một dự án có thể `BUILD SUCCESS` nhưng chưa có coverage nếu tests bị skip, Java agent chưa chạy, không có execution data, hoặc goal report/check chưa được bind. Ngược lại, 100% line coverage vẫn không chứng minh mọi assertion tốt hoặc mọi tình huống nghiệp vụ đúng.

Bài học thuộc nhóm **Cổng chất lượng**, tập trung vào luồng Maven thu thập → báo cáo → kiểm chứng. Có ví dụ **Maven 3.9.x + Java 17 + JUnit Jupiter + Surefire + Failsafe + JaCoCo 0.8.16**: tách dữ liệu unit và integration, gộp thành một `jacoco-merged.exec`, tạo ba báo cáo và áp ngưỡng LINE coverage ở phase `verify`. JaCoCo 0.8.16 là một bản phát hành chính thức ngày 24/10/2026; dùng bản cố định để thuận tiện tái lập, không ngụ ý mọi project phải dùng đúng version này.

## 1. JaCoCo đo điều gì?

Coverage trả lời câu hỏi: **những phần bytecode nào đã thực sự chạy trong test workload?** Không trực tiếp đo test có assert đúng business requirement không, không bảo đảm không có bug, và không thay thế kiểm thử bảo mật, concurrency, performance, migration hay contract.

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `INSTRUCTION` (C0) | Số bytecode instructions được thực thi hoặc chưa chạy | Độc lập với định dạng source; cơ sở quan trọng của JaCoCo |
| `BRANCH` (C1) | Các nhánh trong `if` và `switch` được đi qua | JaCoCo không coi exception handling như branch |
| `LINE` | Dòng Java có instructions được chạy hay chưa | Cần debug line-number information trong class files |
| `METHOD` | Method có ít nhất một instruction chạy hay chưa | Bao gồm constructors/static initializers phù hợp |
| `CLASS` | Class có ít nhất một method được thực thi | Không có nghĩa tất cả methods đều được test |
| `COMPLEXITY` | Cyclomatic complexity và phần đã được covered | Không phải số lượng test methods |

### 1.1. Line coverage và branch coverage không đồng nhất

Ví dụ:

```java
public String label(int quantity) {
    return quantity >= 10 ? "bulk" : "single";
}
```

Một test chỉ gọi `label(12)` có thể thực thi dòng `return`, nhưng chưa đi qua nhánh `quantity < 10`. Báo cáo LINE có thể trông tốt hơn BRANCH, và JaCoCo hiển thị partial-branch diamond khi có source line info.

Tương tự, một test không có assertion vẫn làm coverage tăng nếu nó gọi code. **Code được thực thi ≠ code được xác minh đúng.**

### 1.2. Ý nghĩa màu sắc trong HTML report

Thông thường báo cáo source highlighting dùng:

- **Đỏ:** không có instruction chạy trên dòng tương ứng.
- **Vàng:** chỉ một phần instructions/branches được covered.
- **Xanh:** các instructions trên dòng được covered theo mức JaCoCo hiển thị.

JaCoCo tính trên bytecode; Java compiler có thể sinh synthetic instructions, lambda/switch bytecode hoặc constructors ảnh hưởng counters. Không suy từ màu một dòng rằng mọi đường chạy nghiệp vụ đã được xác minh.

### 1.3. Công thức tỷ lệ coverage

Trong JaCoCo XML có `counter` với `missed` và `covered`, ví dụ minh họa:

```xml
<counter type="LINE" missed="20" covered="80"/>
```

Khi đó:

```text
LINE coverage = covered / (missed + covered)
              = 80 / (20 + 80)
              = 80%
```

Đây là **số minh họa**, không phải output đo từ project bài tập. Nếu `missed + covered = 0`, report có thể không có code được đo; đừng mặc định hiểu là 100%.

## 2. Các thành phần trong luồng JaCoCo Maven

Sơ đồ:

```text
Source Java 17 → Maven compiler → target/classes
                                  |
                  jacoco:prepare-agent ở initialize
                                  |
                  Surefire JVM chạy unit tests
                                  |
                           target/jacoco.exec
                                  |
           jacoco:prepare-agent-integration ở pre-IT
                                  |
                  Failsafe JVM chạy integration tests
                                  |
                          target/jacoco-it.exec
                                  |
                jacoco:merge ở post-integration-test
                                  |
                         target/jacoco-merged.exec
                                  |
       verify: failsafe:verify + JaCoCo reports + check
                                  |
                         BUILD SUCCESS / FAILURE
```

Những goals ở sơ đồ **phải được khai và bind vào đúng phases**. Maven không tự thực hiện tất cả chỉ vì project thêm dependency JaCoCo hoặc khai JaCoCo trong `pluginManagement`.

### 2.1. Giải thích từng goal

| Goal | Default/phase phù hợp | Đầu ra/trách nhiệm |
| --- | --- | --- |
| `jacoco:prepare-agent` | `initialize` | Chuẩn bị property `argLine` chứa `-javaagent` để test JVM dùng |
| `jacoco:report` | `verify` | Phân tích `jacoco.exec`, tạo HTML/XML/CSV tại `target/site/jacoco` |
| `jacoco:check` | `verify` | Đánh giá coverage rules và fail build nếu violation |
| `jacoco:prepare-agent-integration` | `pre-integration-test` | Chuẩn bị agent cho IT, mặc định ghi `jacoco-it.exec` |
| `jacoco:report-integration` | `verify` | Phân tích IT data, tạo `target/site/jacoco-it` |
| `jacoco:merge` | Bài này bind `post-integration-test` | Gộp nhiều `*.exec` thành một file |
| `jacoco:report-aggregate` | Trong reporting module của reactor | Báo cáo nhiều projects dựa trên các dependencies của reporting module |
| `jacoco:dump` | Goal tương tác với agent đã cấu hình TCP/JMX | Thu execution data từ JVM còn chạy |

JaCoCo có cả offline instrumentation goals nhưng không cần dùng cho ví dụ Surefire/Failsafe thông thường; ưu tiên on-the-fly Java agent vì dễ vận hành hơn.

### 2.2. Vì sao file *.exec không phải báo cáo?

`jacoco.exec` là dữ liệu **nhị phân** do Java agent ghi khi JVM chạy/kết thúc; không phải text, không chứa tỷ lệ phần trăm dạng HTML/XML. Để tạo report, JaCoCo cần:

1. Execution data.
2. Chính những `.class` tương ứng với code đã chạy.
3. Source files/line-number information nếu muốn mapping và highlighting từng dòng.

Class files thay đổi giữa test và report có thể gây **class ID mismatch**, dẫn tới class 0% dù có execution data. Không trộn exec file của commit cũ với classes vừa compile lại.

### 2.3. Lý do kết thúc Maven bằng verify

Trong Maven 3, `mvn test` chạy Surefire nhưng chưa tới phases Failsafe integration-test, post-integration-test và `verify`. Nếu mục tiêu bài tập cần unit + IT + merge + check, phải chạy:

```bash
mvn -B clean verify
```

`clean` xóa dữ liệu cũ trước khi build. `verify` đi qua packaging, integration-test và hậu xử lý, cuối cùng chạy quality gate. `mvn integration-test` không phải điểm dừng hợp lý cho các bước cleanup/merge/report/check ở các phase phía sau.

## 3. Ví dụ Java 17 hoàn chỉnh có JaCoCo và quality gate

**Cấu trúc file:**

```text
jacoco-quality-lab/
├── pom.xml
└── src/
    ├── main/java/vn/example/coverage/
    │   ├── PriceCalculator.java
    │   ├── ReceiptService.java
    │   └── App.java
    └── test/java/vn/example/coverage/
        ├── PriceCalculatorTest.java
        └── ReceiptServiceIT.java
```

Yêu cầu: Java 17+, Maven 3.9.x, repository có thể resolve plugins/JUnit lần đầu. Không cần DB, Docker hoặc service ngoài. Kết quả dự kiến:

- **5 unit test methods** trong `PriceCalculatorTest`.
- **1 integration test method** trong `ReceiptServiceIT`.
- Raw coverage files: `jacoco.exec`, `jacoco-it.exec`, `jacoco-merged.exec`.
- Ba report directories: `jacoco`, `jacoco-it`, `jacoco-combined`.
- Quality gate combined LINE coverage ≥30% (chỉ để minh họa).
- Java main in một dòng chính xác: `total=36;net=33`.

### 3.1. POM đầy đủ

File `jacoco-quality-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>jacoco-quality-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.0</junit.jupiter.version>
        <coverage.minimum>0.30</coverage.minimum>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <argLine>@{argLine}</argLine>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <argLine>@{argLine}</argLine>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
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
                        <id>attach-unit-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>attach-integration-agent</id>
                        <goals>
                            <goal>prepare-agent-integration</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>merge-coverage-data</id>
                        <phase>post-integration-test</phase>
                        <goals>
                            <goal>merge</goal>
                        </goals>
                        <configuration>
                            <fileSets>
                                <fileSet>
                                    <directory>${project.build.directory}</directory>
                                    <includes>
                                        <include>jacoco.exec</include>
                                        <include>jacoco-it.exec</include>
                                    </includes>
                                </fileSet>
                            </fileSets>
                            <destFile>${project.build.directory}/jacoco-merged.exec</destFile>
                        </configuration>
                    </execution>
                    <execution>
                        <id>unit-coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>integration-coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report-integration</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>combined-coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                        <configuration>
                            <dataFile>${project.build.directory}/jacoco-merged.exec</dataFile>
                            <outputDirectory>${project.build.directory}/site/jacoco-combined</outputDirectory>
                        </configuration>
                    </execution>
                    <execution>
                        <id>coverage-quality-gate</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                        <configuration>
                            <dataFile>${project.build.directory}/jacoco-merged.exec</dataFile>
                            <haltOnFailure>true</haltOnFailure>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>${coverage.minimum}</minimum>
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
```

**POM này minh họa đủ ba nhiệm vụ độc lập:**

- `prepare-agent` mặc định ở `initialize` đặt `argLine` cho unit-test JVM. Surefire chạy phase `test`, tạo `jacoco.exec`.
- `prepare-agent-integration` mặc định ở `pre-integration-test` cập nhật `argLine` để IT JVM tạo `jacoco-it.exec`. Failsafe chạy `integration-test` và kiểm kết quả qua `failsafe:verify`.
- `merge` ở `post-integration-test` chỉ lấy hai file có tên được khai, ghi `jacoco-merged.exec` sau tests nhưng trước báo cáo.
- Hai goal `report` dùng hai data files/đường output khác nhau: unit default và combined explicit.
- `report-integration` mặc định dùng `jacoco-it.exec`, output `target/site/jacoco-it`.
- `check` đọc **merged data** rồi kiểm `LINE/COVEREDRATIO` tại `BUNDLE` với ngưỡng do property `coverage.minimum` điều khiển.
- `<haltOnFailure>true</...>` làm Maven fail khi có violation. Ngưỡng 0.30 chỉ để học cơ chế; project thật phải chọn policy có ý nghĩa.

**Một chi tiết quan trọng:** `<argLine>@{argLine}</argLine>` là **late property evaluation** của Surefire/Failsafe, cho test JVM nhận argument mà JaCoCo đã đặt ở phase trước. Không thay nó bằng một `argLine` tùy ý khiến Java agent bị mất.


### 3.2. Production class PriceCalculator

File `src/main/java/vn/example/coverage/PriceCalculator.java`:

```java
package vn.example.coverage;

public final class PriceCalculator {

    public int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                "price and quantity must be nonnegative"
            );
        }
        return Math.multiplyExact(unitPrice, quantity);
    }

    public int net(int gross, boolean member) {
        if (gross < 0) {
            throw new IllegalArgumentException("gross must be nonnegative");
        }
        return member ? gross - gross / 10 : gross;
    }

    public String band(int total) {
        return total >= 100 ? "large" : "small";
    }
}
```

Có các nhánh invalid input, member/nonmember và phân loại `band`. Method `band` cố tình **chưa được gọi bởi tests**, giúp người học thấy non-100% coverage. `Math.multiplyExact` ném `ArithmeticException` khi integer overflow.

### 3.3. Production class ReceiptService

File `src/main/java/vn/example/coverage/ReceiptService.java`:

```java
package vn.example.coverage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReceiptService {
    private final PriceCalculator calculator = new PriceCalculator();

    public String render(int unitPrice, int quantity, boolean member) {
        int gross = calculator.total(unitPrice, quantity);
        int net = calculator.net(gross, member);
        return "total=" + gross + ";net=" + net;
    }

    public void writeReceipt(
            Path file, int unitPrice, int quantity, boolean member
    ) throws IOException {
        Files.writeString(
            file,
            render(unitPrice, quantity, member),
            StandardCharsets.UTF_8
        );
    }
}
```

`ReceiptService` có hai đường chạy: render không I/O và viết file text bằng JDK Files API. Điều này đủ để ví dụ IT có tương tác filesystem mà không cần Docker/database.

### 3.4. App main và stdout

File `src/main/java/vn/example/coverage/App.java`:

```java
package vn.example.coverage;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        ReceiptService service = new ReceiptService();
        System.out.println(service.render(12, 3, true));
    }
}
```

Sau khi Maven đóng JAR, chạy:

```bash
java -cp target/jacoco-quality-lab-1.0.0.jar vn.example.coverage.App
```

**Stdout chính xác của Java program:**

```text
total=36;net=33
```

Đây là **plain JAR**, POM không thêm `Main-Class` vào manifest. Vì thế lệnh dùng `-cp` và FQCN, không giả định `java -jar` chạy được. Code production chỉ dùng JDK API; JUnit có scope test nên không cần kèm JUnit JAR ở runtime.

### 3.5. Unit test: năm phương thức

File `src/test/java/vn/example/coverage/PriceCalculatorTest.java`:

```java
package vn.example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void calculatesTotal() {
        assertEquals(36, calculator.total(12, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.total(12, -1)
        );
    }

    @Test
    void catchesMultiplicationOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> calculator.total(1_500_000_000, 3)
        );
    }

    @Test
    void appliesMemberDiscount() {
        assertEquals(33, calculator.net(36, true));
    }

    @Test
    void keepsNonmemberPrice() {
        assertEquals(36, calculator.net(36, false));
    }
}
```

Surefire theo convention `*Test` chạy năm methods này ở phase `test`. Chúng kiểm một số nhánh của `total` và `net`, nhưng không kiểm `band`. Không thể lấy số lượng 5 tests làm tỷ lệ coverage hoặc branch count.

### 3.6. Integration test: một phương thức

File `src/test/java/vn/example/coverage/ReceiptServiceIT.java`:

```java
package vn.example.coverage;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptServiceIT {

    @TempDir
    Path temporaryDirectory;

    @Test
    void writesAndReadsReceipt() throws Exception {
        Path file = temporaryDirectory.resolve("receipt.txt");
        ReceiptService service = new ReceiptService();

        service.writeReceipt(file, 12, 3, true);

        assertEquals(
            "total=36;net=33",
            Files.readString(file, StandardCharsets.UTF_8)
        );
    }
}
```

Failsafe theo convention `*IT` chạy test này ở integration-test phase; `@TempDir` quản lý thư mục tạm. Test minh họa phối hợp production classes và filesystem. Với ứng dụng chạy service trong **JVM/container riêng**, phải gắn JaCoCo agent **vào đúng JVM chứa application code**, không chỉ JVM test gọi HTTP.

## 4. Chạy Maven và đọc kết quả

Từ `jacoco-quality-lab`:

```bash
java -version
mvn --version
mvn -B clean verify
```

Trong môi trường có JDK 17+, Maven 3.9.x và resolved plugins/dependencies, các bước kỳ vọng:

1. `initialize`: JaCoCo unit agent gán Java argument.
2. `test`: Surefire chạy 5 unit tests, JVM dump `jacoco.exec`.
3. `package`: Maven JAR Plugin tạo `jacoco-quality-lab-1.0.0.jar`.
4. `pre-integration-test`: JaCoCo chuyển agent destination sang `jacoco-it.exec`.
5. `integration-test`: Failsafe chạy 1 IT, ghi raw exec và test XML.
6. `post-integration-test`: JaCoCo merge file unit/IT.
7. `verify`: Failsafe chốt kết quả, JaCoCo xuất ba báo cáo và kiểm rule combined coverage.

**Bài không tuyên bố đã chạy Maven trên máy của người học.** Các test counts và stdout trên là kết quả được dự kiến từ source mẫu, cần đối chiếu bằng build log và report khi thực hành.

### 4.1. Cây output quan trọng

```text
target/
├── jacoco-quality-lab-1.0.0.jar
├── jacoco.exec
├── jacoco-it.exec
├── jacoco-merged.exec
├── surefire-reports/
│   └── TEST-vn.example.coverage.PriceCalculatorTest.xml
├── failsafe-reports/
│   ├── TEST-vn.example.coverage.ReceiptServiceIT.xml
│   └── failsafe-summary.xml
└── site/
    ├── jacoco/
    │   ├── index.html
    │   ├── jacoco.xml
    │   └── jacoco.csv
    ├── jacoco-it/
    │   ├── index.html
    │   ├── jacoco.xml
    │   └── jacoco.csv
    └── jacoco-combined/
        ├── index.html
        ├── jacoco.xml
        └── jacoco.csv
```

Đây là **các file tiêu biểu**, không phải tất cả output của Maven. Bảng đối chiếu:

| File | Loại dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `jacoco.exec` | Nhị phân JaCoCo | Unit-test execution probes |
| `jacoco-it.exec` | Nhị phân JaCoCo | Integration-test probes |
| `jacoco-merged.exec` | Nhị phân JaCoCo | Union execution data unit + IT |
| `surefire-reports/TEST-*.xml` | JUnit-style XML | Test cases, failures, errors, skips của Surefire |
| `failsafe-reports/TEST-*.xml` | JUnit-style XML | Integration test results |
| `failsafe-summary.xml` | Failsafe XML | Kết quả để goal `failsafe:verify` đánh giá |
| `site/jacoco/jacoco.xml` | JaCoCo XML | Unit-only coverage counters |
| `site/jacoco-it/jacoco.xml` | JaCoCo XML | IT-only coverage counters |
| `site/jacoco-combined/jacoco.xml` | JaCoCo XML | Combined coverage counters |

**Không nạp JaCoCo XML vào JUnit importer**; đó là hai XML schemas phục vụ mục đích khác. Ngược lại, SonarScanner thường cần JaCoCo XML chứ không đọc binary `*.exec` như một coverage report.

### 4.2. Kiểm tra file tồn tại và không rỗng

Linux/macOS:

```bash
test -s target/jacoco.exec
test -s target/jacoco-it.exec
test -s target/jacoco-merged.exec
test -s target/site/jacoco/jacoco.xml
test -s target/site/jacoco-it/jacoco.xml
test -s target/site/jacoco-combined/jacoco.xml
```

Lệnh `test -s` chỉ trả exit code, không in stdout khi thành công. Presence/size là điều kiện cần, **chưa phải bằng chứng coverage có đúng classes/counters**.

Windows PowerShell:

```powershell
$files = @(
    "target\jacoco.exec",
    "target\jacoco-it.exec",
    "target\jacoco-merged.exec",
    "target\site\jacoco\jacoco.xml",
    "target\site\jacoco-it\jacoco.xml",
    "target\site\jacoco-combined\jacoco.xml"
)
foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing coverage file: $file"
    }
    if ((Get-Item -LiteralPath $file).Length -eq 0) {
        throw "Empty coverage file: $file"
    }
}
```

### 4.3. HTML report cho developer, XML cho máy

Các HTML entrypoint:

```text
target/site/jacoco/index.html
target/site/jacoco-it/index.html
target/site/jacoco-combined/index.html
```

Mở combined HTML và tìm `PriceCalculator.band` chưa covered. Nếu thêm tests cho cả `band(99)` và `band(100)`, một số LINE/BRANCH counters sẽ đổi. Cũng xem `ReceiptService.writeReceipt`, nó được IT chạm vào.

JaCoCo XML có nhiều `counter` ở class, package và report level. Nếu tự tính tổng, dùng **top-level counter** tương ứng ở XML root, tránh cộng package + class counters gây đếm trùng.

### 4.4. Java main không tự làm coverage tăng

Sau Maven verify, chạy:

```bash
java -cp target/jacoco-quality-lab-1.0.0.jar vn.example.coverage.App
```

Stdout:

```text
total=36;net=33
```

Lần chạy Java này **không gắn JaCoCo agent**, nên không tự ghi thêm `jacoco.exec`. Đây là khác biệt giữa application chạy bình thường và application chạy dưới instrumentation.

## 5. Gắn quality gate bằng jacoco:check

Execution trong POM có:

```xml
<rules>
    <rule>
        <element>BUNDLE</element>
        <limits>
            <limit>
                <counter>LINE</counter>
                <value>COVEREDRATIO</value>
                <minimum>${coverage.minimum}</minimum>
            </limit>
        </limits>
    </rule>
</rules>
```

Ý nghĩa:

- `BUNDLE`: phạm vi bundle/module đang được check.
- `LINE`: đo độ bao phủ dòng source.
- `COVEREDRATIO`: tỉ lệ covered lines trên tổng lines JaCoCo tính.
- `coverage.minimum`: property mặc định `0.30`.
- `haltOnFailure=true`: goal `check` làm build fail khi ngưỡng không đạt.

30% là **ngưỡng demo dễ quan sát**. Không dùng nó làm chuẩn tất cả doanh nghiệp. Có thể bổ sung `BRANCH`/`INSTRUCTION`, áp rule ở `CLASS`/`PACKAGE` và đặt giới hạn theo rủi ro module.

### 5.1. Negative test: chứng minh gate có tác dụng

```bash
mvn -B -Dcoverage.minimum=1.00 clean verify
```

Vì source mẫu có code không được tests gọi (như `PriceCalculator.band` và `App.main`), combined LINE coverage dự kiến dưới 100%. JaCoCo `check` ở verify phải báo **coverage rule violation**, làm Maven trả exit code khác 0.

Chạy lại:

```bash
mvn -B clean verify
```

để dùng `coverage.minimum=0.30` theo POM. Nếu các test/agent/goal được thực thi đúng, ngưỡng thấp dự kiến pass. Điều quan trọng là **test âm tính xác minh ngưỡng đã được enforce**, chứ không phải chỉ có XML report.

### 5.2. Gate nhiều counter

Ví dụ **policy độc lập**, không thuộc cấu hình runnable mặc định:

```xml
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
                <minimum>0.70</minimum>
            </limit>
        </limits>
    </rule>
</rules>
```

Nếu có yêu cầu module nghiệp vụ không được dưới 60% coverage cho bất cứ class nào, có thể đặt rule với `element=CLASS`. Nhưng module `pom`/generated-only hoặc class chỉ chứa cấu hình cần quy định riêng để tránh policy vô lý.

### 5.3. Trường hợp không có dữ liệu

Cảnh báo: **JaCoCo check/report có thể skip nếu file execution data cần thiết không tồn tại**. Một build chạy `-DskipTests`/`-DskipITs`, không có forks hoặc report data mất vẫn có thể không đánh giá ngưỡng như mong muốn.

Vì thế release gate phải kiểm:

- Không có skip flags ngoài chính sách cho phép.
- Có Surefire/Failsafe test XML với số test cases phù hợp.
- Có raw exec file và XML report tương ứng với đúng modules/classes.
- `jacoco:check` thật sự chạy và trả kết luận, không chỉ skip.
- CI coi **missing required data/report** là lỗi, không tự xem là “0 failures” hoặc “100% coverage”.

Đừng đưa `failIfNoTests=true` vào mọi POM module nếu module đó chỉ chứa cấu hình hoặc không yêu cầu IT; đặt chính sách vào đúng nơi bắt buộc có test.


## 6. Vì sao unit coverage và IT coverage nên tách khi cần?

Nếu một module có unit tests và integration tests, có hai thiết kế hợp lệ:

- **Một file exec chung:** cả Surefire/Failsafe cùng attach agent ghi vào một `jacoco.exec` với append phù hợp. Ít cấu hình, chỉ có overall report.
- **Hai files riêng rồi merge:** `prepare-agent` ghi `jacoco.exec`; `prepare-agent-integration` ghi `jacoco-it.exec`; sau IT, `merge` tạo `jacoco-merged.exec`, như POM demo.

Cách thứ hai cho phép xem **unit-only**, **IT-only** và **combined**. Combined coverage được tính từ **hợp các probes đã covered**, không cộng phần trăm. Nếu code chạy bởi cả unit lẫn IT, không được tính covered hai lần.

### 6.1. Merge phải chạy sau tests

Goal `jacoco:merge` có default lifecycle binding riêng trong metadata, nhưng bài **cố tình gắn vào `post-integration-test`**. Nếu merge chạy sớm hơn unit/IT, các exec files chưa có; merged output sẽ thiếu dữ liệu.

Với Maven 3, dừng ở `mvn integration-test` sẽ bỏ qua post-integration-test/verify, nên người học không thấy merged report. Dùng `mvn verify` khi cần chuỗi hoàn chỉnh.

### 6.2. Một file exec có thể thiếu mà merge vẫn xong

Merge filesets xử lý files thực sự tồn tại. Nếu IT bị skip và `jacoco-it.exec` thiếu, merged file có thể chỉ chứa unit data. Vì vậy **file merged tồn tại không chứng minh IT đã chạy**. Phải kiểm Failsafe XML, test counts và IT exec data theo quality policy.

### 6.3. Test thất bại ảnh hưởng báo cáo thế nào?

Failsafe thường trì hoãn integration assertion failure tới goal `failsafe:verify`, giúp post-integration-test có cơ hội teardown và merge. Tuy vậy khi Failsafe verify báo failure, các JaCoCo report/check goals chạy sau trong phase verify **có thể không được thực thi** vì Maven dừng.

Để CI vẫn có dữ liệu khi build đỏ, cấu hình artifact upload trong nhánh **always/finally**, thu raw Surefire/Failsafe XML và JaCoCo exec. Nếu cần report HTML ngay cả khi tests fail, dùng một reporting job riêng có điều kiện và không biến failure thành success.

## 7. Những lỗi về JVM fork và argLine

### 7.1. Không đặt forkCount=0

JaCoCo Maven docs cảnh báo không dùng `forkCount=0` hoặc legacy `forkMode=never` trong Surefire/Failsafe nếu cần test JVM chạy cùng Java agent. Với forkCount 0, test có thể chạy nhưng không nhận agent đúng cách để đo coverage.

POM demo dùng:

```xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
```

Không có nghĩa mọi project buộc phải chọn duy nhất 1 fork; nó chỉ giúp bài dễ tái lập. Với parallel forks, ghi exec data phải được thiết kế an toàn để không mất sessions hoặc corrupt file.

### 7.2. ArgLine bị ghi đè

Cấu hình sau có thể vô tình làm mất `-javaagent` do JaCoCo chuẩn bị:

```xml
<!-- CỐ TÌNH SAI khi thay toàn bộ args JaCoCo -->
<configuration>
    <argLine>-Xmx512m</argLine>
</configuration>
```

Một cấu hình tốt hơn:

```xml
<configuration>
    <argLine>@{argLine} -Xmx512m</argLine>
</configuration>
```

`@{argLine}` là cú pháp Surefire late property evaluation; nó đọc property mà JaCoCo đã gán ở lifecycle trước đó rồi thêm VM args riêng. Dùng ý tưởng tương tự với Failsafe. Nếu có profile chạy Surefire nhưng không chạy JaCoCo prepare-agent, property chưa được tạo có thể làm JVM báo `Could not find or load main class @{argLine}`; lúc đó xác định profile và cung cấp giá trị rỗng mặc định phù hợp.

### 7.3. Code chạy trong một JVM khác

IT có thể chạy bằng Failsafe test JVM nhưng gọi một HTTP service đang chạy trong container. JaCoCo trong **test JVM** chỉ đo bytecode thực thi ở test JVM. Muốn đo production code trong service process, phải gắn JaCoCo agent vào JVM của service và thu file/dump từ process đó.

Đối với TCP/JMX dump, kiểm soát interface, port, credentials và mạng thử nghiệm. Không mở agent TCP server ra Internet công cộng hoặc thêm agent debug nhạy cảm vào production chỉ để thu coverage.

### 7.4. JVM bị kill hoặc thiếu quyền ghi

Agent ở output mode file thường ghi dữ liệu khi JVM kết thúc. Nếu process bị kill đột ngột, container bị terminate ngay, filesystem không ghi được, session chưa dump thì file exec có thể không tồn tại hoặc thiếu dữ liệu. Cần kiểm test process lifecycle, quyền thư mục `target`, timeout, logs và khi phù hợp dùng dump có kiểm soát.

## 8. Class ID mismatch và 0% coverage giả

JaCoCo gắn execution data với **bytecode class identity**. Nếu runtime thực thi một phiên bản class nhưng lúc tạo report JaCoCo đọc class files khác bytes, các probes không map được; class có thể hiển thị 0% dù test đã gọi method.

Dấu hiệu: mở **Sessions** trong HTML report, tìm class có data nhưng không liên kết tới report entry tương ứng. Cách xử lý:

1. Chạy `mvn -B clean verify` từ cùng commit.
2. Không kết hợp exec từ nhánh/build khác.
3. Kiểm instrumented service/container dùng đúng artifact class bytes.
4. Không sửa classes sau khi test trước khi report.
5. Kiểm offline instrumentation/custom classloaders/bytecode transforms.
6. Đối chiếu JaCoCo release và compiler target.

Cũng có thể source highlighting trống vì compiled classes không có debug line info hoặc source paths không tương ứng. Bytecode instruction coverage vẫn có thể được đo dù line mapping bị hạn chế.

## 9. Excludes và các con số không đáng tin

JaCoCo có nhiều điểm để exclude:

- `prepare-agent/excludes`: giới hạn class instrumentation; chỉ dùng khi cần thật, không mặc định.
- `report/excludes`: loại classes khỏi output report.
- `check/excludes`: loại classes khỏi quality rule.
- `report-aggregate`: có includes/excludes ở reporting context.
- `sonar.coverage.exclusions`: scope của SonarQube, không tự sửa Maven JaCoCo report.

Ví dụ **đoạn cấu hình minh họa cho report**, không chép vô điều kiện vào POM thực hành:

```xml
<configuration>
    <excludes>
        <exclude>**/generated/**</exclude>
        <exclude>**/*Config.class</exclude>
    </excludes>
</configuration>
```

Nếu loại một class khỏi report nhưng check vẫn tính class đó, HTML và gate có thể dùng phạm vi khác nhau. Hãy đồng bộ policy theo ý định và ghi lý do. Không loại domain classes quan trọng chỉ để tăng percentage.

JaCoCo còn có bytecode filters cho một số compiler-generated constructs; không dự đoán một annotation/method luôn bị loại trên mọi JaCoCo release. Kiểm output thực tế và release notes.

## 10. Multi-module: JaCoCo report-aggregate

Với Maven reactor gồm `core`, `app` và `coverage-report`, root `<modules>` không tự tạo HTML/XML tổng hợp. JaCoCo `report-aggregate` lấy dữ liệu từ **dependencies của reporting module**.

Scope trong reporting POM:

| Scope | Cách JaCoCo report-aggregate sử dụng |
| --- | --- |
| `compile` / `runtime` / `provided` | Classes, sources và execution data của dependency module |
| `test` | Chỉ execution data, hữu ích nếu một module integration-tests chỉ chứa tests |

Ví dụ một **đoạn plugin** đặt trong `coverage-report/pom.xml` (chỉ có ý nghĩa khi tồn tại một Maven reactor đầy đủ):

```xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.16</version>
    <executions>
        <execution>
            <id>reactor-aggregate</id>
            <phase>verify</phase>
            <goals>
                <goal>report-aggregate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Reporting module cần dependencies thực tới các code modules muốn tính:

```xml
<dependencies>
    <dependency>
        <groupId>vn.example</groupId>
        <artifactId>core</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>vn.example</groupId>
        <artifactId>app</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
```

Đây là các **module coordinates minh họa**, không phải artifacts có thể tải công khai. Reporting module nên được build sau code modules nhờ dependency graph. Output mặc định thường là:

```text
coverage-report/target/site/jacoco-aggregate/index.html
coverage-report/target/site/jacoco-aggregate/jacoco.xml
```

Không lấy trung bình 80% coverage của module A và 50% của B thành 65% nếu modules có kích thước code khác nhau. Aggregate ratio phải dựa trên **tổng covered/missed counters** của scope được chọn.

JaCoCo `report-aggregate` **tạo báo cáo**, không mặc nhiên áp quality threshold cho toàn reactor. Muốn aggregate gate, CI/server phải đọc report XML và kiểm module completeness + threshold, hoặc đặt per-module `check` phù hợp.

## 11. CI/CD và SonarQube

Một workflow điển hình:

```text
Checkout → JDK17 + Maven3.9
   |
   +-- mvn -B clean verify
   |     ├─ unit + IT test results
   |     ├─ jacoco.exec + jacoco-it.exec
   |     ├─ merged execution data
   |     ├─ HTML/XML/CSV reports
   |     └─ JaCoCo check quality gate
   |
   +-- publish reports (ALWAYS, kể cả build fail)
   |
   +-- SonarScanner/quality server (nếu dùng)
   |
   +-- merge/deploy chỉ khi mọi required gates PASS
```

### 11.1. Report paths cần lưu

```text
target/surefire-reports/TEST-*.xml
target/failsafe-reports/TEST-*.xml
target/jacoco.exec
target/jacoco-it.exec
target/jacoco-merged.exec
target/site/jacoco/jacoco.xml
target/site/jacoco-it/jacoco.xml
target/site/jacoco-combined/jacoco.xml
target/site/jacoco-combined/index.html
```

Multi-module dùng `**/target/...` khi CI supports glob. Nếu một test fail, Maven có thể dừng trước khi có tất cả reports; raw Surefire/Failsafe XML và exec files vẫn nên được upload trong CI `always`.

### 11.2. SonarQube và XML

SonarScanner thường nhập JaCoCo XML qua property:

```properties
sonar.coverage.jacoco.xmlReportPaths=target/site/jacoco-combined/jacoco.xml
```

Đây là **ví dụ cấu hình SonarQube**, không phải file Spring application properties. Scanner phải chạy sau khi XML được tạo, và path phải đúng theo scanner working directory/module base dir. Multi-module có thể cần một aggregate XML và đường dẫn tương đối khác.

**Upload coverage không đồng nghĩa SonarQube quality gate đã PASS.** Pipeline cần cấu hình server-side quality gate và chờ/đọc verdict nếu muốn chặn merge/deploy.

### 11.3. Bảo vệ tính toàn vẹn kết quả CI

- Không cache `target/jacoco.exec` qua nhiều commits/branches như dữ liệu chung.
- Chạy `clean` ở full CI build để tránh stale exec/XML.
- Kiểm test suite counts và report presence thay vì chỉ exit code.
- Không dùng `mvn -fn` làm release gate vì lệnh có thể trả exit 0 dù có errors.
- Nếu dùng `-pl` chọn subset modules, báo coverage là **partial**, không so với full-reactor threshold.
- Khi chạy Maven `-T` hoặc nhiều JVM forks, không cho tất cả ghi đè một file exec dùng chung mà không có cơ chế an toàn.
- Kiểm chính xác JaCoCo version và JDK/compiler; thay toolchain có thể đổi filters/bytecode counters.
- Bảo vệ secrets trong Maven/Sonar logs; không đưa tokens, passwords vào POM.

## 12. Bảng chẩn đoán khi JaCoCo không hoạt động

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không có `jacoco.exec` | Agent không chạy, tests skip, JVM không fork, destination sai | JaCoCo prepare-agent logs, Surefire fork, test XML |
| Surefire tests PASS nhưng coverage 0% | `argLine` ghi đè agent, class ID mismatch | Forked JVM args, Sessions trong HTML |
| Report goal skip | Không có execution data hoặc classes phù hợp | `target` paths, plugin executions |
| Unit có coverage, IT không có | Failsafe/IT agent chưa bind hoặc IT skip | `failsafe-reports`, `jacoco-it.exec` |
| Combined report thiếu IT data | Merge chạy sớm/IT exec vắng mặt | Phase order, filesets, data file size |
| Java test process chạy ở container khác | Agent chỉ được gắn vào test JVM | Attach JaCoCo vào service JVM |
| HTML không highlight source | Thiếu debug info hoặc source path không khớp | Compiler line numbers, report source root |
| 100% coverage lạ thường | Report thiếu classes hoặc excludes quá rộng | Class/package inventory, counters |
| Check không fail khi threshold bị vi phạm | Check chưa bind, data missing/skip, wrong dataFile | Check logs, report XML, negative CLI |
| JVM báo `@{argLine}` là main class | Property late interpolation thiếu | JaCoCo execution, default argLine |
| Coverage giảm sau recompile | Bytecode filters/class IDs thay đổi | Clean build, class version, JaCoCo docs |
| CI không có reports ở build FAIL | Upload artifacts chỉ ở success | Publish luôn ở finally/always |
| App main chạy không tăng exec | JVM chạy ngoài instrumentation | Chạy main với JaCoCo agent nếu cần đo |
| Maven root không có jacoco.xml | Reports nằm ở từng module `target` | Kiểm child module hoặc aggregate module |
| Branch ratio thấp nhưng lines cao | Các đường true/false chưa được test | Xem branch diamonds và thêm edge tests |

### 12.1. Quy trình debug theo thứ tự

1. `java -version` và `mvn --version` để xác nhận Java/Maven.
2. `mvn -B clean verify` không có skip flags.
3. Xem plugin `prepare-agent`/`prepare-agent-integration` và property `argLine` thực tế.
4. Xem Surefire/Failsafe `TEST-*.xml` có đúng test methods đã chạy không.
5. Kiểm `jacoco.exec`/`jacoco-it.exec` và `jacoco-merged.exec`.
6. Kiểm `target/site/jacoco*/jacoco.xml` xuất hiện, có classes/counters mong muốn.
7. Mở HTML/Sessions để phát hiện class ID mismatch.
8. Xem `jacoco:check` execution log đã thật sự chạy chưa.
9. Chạy `-Dcoverage.minimum=1.00` như negative test với project demo.
10. Với code ở JVM khác, kiểm agent trên **runtime process** thật.
11. Khôi phục chính sách coverage sau thử nghiệm và lưu báo cáo vào CI.

## 13. Câu hỏi tự luyện và đáp án

**Câu 1.** Chỉ thêm JaCoCo dependency có tự sinh coverage report không?

**Đáp án:** Không. Cần Maven plugin/executions, agent trên JVM test và goal report; dependency bình thường không kích hoạt instrumentation.

**Câu 2.** File `target/jacoco.exec` có phải là XML để SonarQube nhập không?

**Đáp án:** Không. Nó là binary execution data. XML report thường là `target/site/jacoco/jacoco.xml` hoặc combined path.

**Câu 3.** Có 100% LINE coverage đồng nghĩa các branches và nghiệp vụ đều đúng không?

**Đáp án:** Không. Branch coverage là counter khác, còn correctness cần assertions, edge cases và kiểm thử theo yêu cầu.

**Câu 4.** IT gọi API trên một JVM server khác. Agent gắn vào Failsafe JVM có đo code server không?

**Đáp án:** Không. Cần gắn agent vào JVM chứa application code, rồi thu data phù hợp.

**Câu 5.** Vì sao `forkCount=0` có thể khiến JaCoCo không ghi data?

**Đáp án:** Surefire/Failsafe không chạy test JVM với Java agent command-line theo cách JaCoCo cần; tài liệu JaCoCo cảnh báo trường hợp này.

**Câu 6.** `jacoco:report` và `jacoco:check` khác nhau như thế nào?

**Đáp án:** Report tạo HTML/XML/CSV, check đánh giá threshold/rules và có thể fail Maven build.

**Câu 7.** Vì sao nên gắn `merge` ở `post-integration-test` trong bài mẫu?

**Đáp án:** Lúc đó cả unit và IT exec files đã được tạo, nhưng reports/check ở verify chưa chạy. Gắn merge quá sớm sẽ thiếu input.

**Câu 8.** Nếu merged exec tồn tại nhưng IT bị skip, có thể tuyên bố full coverage unit+IT không?

**Đáp án:** Không. Merge có thể nhận chỉ unit file; phải kiểm IT report/test count và `jacoco-it.exec`.

**Câu 9.** Lệnh nào giúp kiểm tra coverage gate âm tính ở project mẫu?

**Đáp án:** `mvn -B -Dcoverage.minimum=1.00 clean verify`. Vì một số methods chưa được tests chạy, check dự kiến fail.

**Câu 10.** Root multi-module có `<modules>` thì report-aggregate tự biết modules cần tính không?

**Đáp án:** Không. JaCoCo report-aggregate dùng dependencies và scopes của reporting module để lấy classes/sources/exec data.

## 14. Checklist hoàn thành bài thực hành

- [ ] Tạo đầy đủ POM và 5 Java source files đúng package.
- [ ] Chạy Maven 3.9.x bằng Java 17+; `mvn -B clean verify` đạt.
- [ ] Surefire có 5 unit tests và Failsafe có 1 integration test.
- [ ] `jacoco.exec`, `jacoco-it.exec`, `jacoco-merged.exec` tồn tại và có dữ liệu.
- [ ] Có HTML/XML/CSV tại `target/site/jacoco`, `jacoco-it` và `jacoco-combined`.
- [ ] HTML combined chứa các production classes và `PriceCalculator.band` chưa covered theo thiết kế.
- [ ] JaCoCo check rule `BUNDLE/LINE/COVEREDRATIO` được thực thi tại `verify`.
- [ ] Negative `-Dcoverage.minimum=1.00` thực sự làm Maven build fail.
- [ ] Java CLI in chính xác `total=36;net=33`.
- [ ] CI bảo vệ tính đúng đắn test counts, XML paths, report presence, không chấp nhận skipped gate.
- [ ] Không trộn execution data của commit khác hoặc JVM khác chưa instrument.
- [ ] Khi chuyển sang reactor, khai reporting module dependencies rõ ràng.

## Tài liệu tham khảo chính thức

- [JaCoCo — Maven Plug-in](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html)
- [JaCoCo — prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)
- [JaCoCo — prepare-agent-integration](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-integration-mojo.html)
- [JaCoCo — report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)
- [JaCoCo — report-integration](https://www.jacoco.org/jacoco/trunk/doc/report-integration-mojo.html)
- [JaCoCo — merge](https://www.jacoco.org/jacoco/trunk/doc/merge-mojo.html)
- [JaCoCo — check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JaCoCo — report-aggregate](https://www.jacoco.org/jacoco/trunk/doc/report-aggregate-mojo.html)
- [JaCoCo — Class IDs and matching](https://www.jacoco.org/jacoco/trunk/doc/classids.html)
- [JaCoCo — Official Releases](https://www.jacoco.org/jacoco/index.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
