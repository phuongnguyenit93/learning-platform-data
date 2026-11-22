# Tổng hợp báo cáo kiểm thử và chất lượng qua nhiều mô-đun trong Maven

Một repository Maven lớn thường chia thành nhiều module: `core` chứa nghiệp vụ, `api` công bố interfaces, `app` lắp ráp ứng dụng, `integration-tests` chạy kiểm thử liên module, còn `coverage-report` hoặc `quality-report` tổng hợp số liệu. Nếu chỉ nhìn dòng cuối `BUILD SUCCESS`, ta không biết mỗi module có bao nhiêu test, module nào chưa có test, unit test và integration test đã thực sự chạy chưa, độ bao phủ mã nguồn là bao nhiêu, hoặc liệu chất lượng chung của reactor đã đạt ngưỡng phát hành hay chưa.

Để quản trị chất lượng, cần phân biệt **ba việc khác nhau**:

1. **Chạy kiểm thử theo module**: Maven Surefire chạy unit tests; Maven Failsafe chạy integration tests khi được cấu hình. Kết quả mặc định ghi vào **thư mục `target` riêng của từng module**.
2. **Tổng hợp báo cáo**: hệ thống CI, Maven Surefire Report Plugin hoặc JaCoCo `report-aggregate` đọc các dữ liệu đã sinh để tạo góc nhìn toàn reactor. Số liệu từ các nguồn **không tự động nhập thành một file** chỉ vì POM gốc khai `<modules>`.
3. **Áp chất lượng như release gate**: test assertions, Failsafe `verify`, JaCoCo `check`, Checkstyle/PMD/SpotBugs, SonarQube quality gate hoặc CI policy **thật sự làm build/pipeline fail** khi không đạt. Báo cáo HTML/XML đẹp **không đồng nghĩa đã bật gate**.

Bài học này nằm trong chủ đề **Reactor nhiều mô-đun**. Nội dung giải thích luồng build và mối quan hệ giữa aggregation/inheritance, chuẩn output Surefire/Failsafe, JaCoCo unit + integration coverage, báo cáo tổng hợp, CI thu gom XML, kiểm tra số liệu/chống bỏ sót module, và một ví dụ **Maven 3.9.x + Java 17+** hoàn chỉnh có ba module `core`, `app` và `coverage-report`. Dùng plugin versions cụ thể: Surefire/Failsafe **3.5.2**, JaCoCo **0.8.14**, Compiler **3.13.0**, JUnit Jupiter **5.11.0**. Đây là các phiên bản minh họa có thật để tái lập bài học, **không khẳng định luôn mới nhất**.

## 1. Multi-module reactor không phải một lần test đơn lẻ

Một POM gốc thường khai:

```xml
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>app</module>
    <module>coverage-report</module>
</modules>
```

Maven reactor thu thập modules, sắp thứ tự theo quan hệ phụ thuộc thực và thực thi các lifecycle phases cho từng project đã được chọn. Với ví dụ:

```text
reactor-quality/
├── pom.xml                      # root aggregator + parent
├── core/
│   ├── pom.xml
│   └── src/main/java + src/test/java
├── app/
│   ├── pom.xml                  # depends on core
│   └── src/main/java + src/test/java
└── coverage-report/
    └── pom.xml                  # depends on core and app
```

Luồng reactor dự kiến:

```text
root (packaging pom)
       |
       v
core             # compile, unit tests, coverage data/report, JAR
       |
       v
app              # compile with core, unit tests + IT, coverage data/report, JAR
       |
       v
coverage-report  # JaCoCo report-aggregate từ core + app
```

Đây là **thứ tự có quan hệ phụ thuộc thực**, không phải “Maven luôn build modules đúng theo thứ tự khai trong `<modules>`”. Khi module `app` có dependency lên `core`, reactor xây `core` trước. Khi module `coverage-report` khai dependencies lên cả `core` và `app`, nó chạy sau hai module sản xuất dữ liệu test/coverage.

Theo tài liệu Apache Maven, reactor sorting tôn trọng instantiated dependencies, plugin dependencies, build extensions và parent references; `dependencyManagement` hoặc `pluginManagement` **chỉ quản lý version/config**, không tự tạo cạnh phụ thuộc để sắp thứ tự build.

### 1.1. Aggregation khác inheritance

| Khái niệm | Khai báo | Tác dụng |
| --- | --- | --- |
| **Aggregation** | Root `<modules>` | Đưa modules vào cùng reactor invocation |
| **Inheritance** | Child `<parent>` | Kế thừa properties, dependencyManagement, pluginManagement, build configuration theo Maven model |
| **Project dependency** | `<dependencies>` | Tạo dependency graph và cạnh reactor order giữa các modules |
| **Reporting aggregation** | Plugin/CI được cấu hình đọc dữ liệu nhiều modules | Sinh báo cáo tổng hợp sau khi dữ liệu tồn tại |

Một module chỉ có mặt trong `<modules>` không mặc nhiên kế thừa JaCoCo/Compiler/Surefire cấu hình của root. Nó chỉ kế thừa nếu `<parent>` trỏ đến root (hoặc parent chain thích hợp), và cấu hình plugin được kế thừa theo quy tắc Maven.

### 1.2. Mỗi module có target độc lập

Giả sử có unit tests ở `core` và `app`; Maven mặc định ghi:

```text
core/target/surefire-reports/TEST-*.xml
app/target/surefire-reports/TEST-*.xml
```

Nếu `app` có Failsafe integration tests, thêm:

```text
app/target/failsafe-reports/TEST-*.xml
app/target/failsafe-reports/failsafe-summary.xml
```

JaCoCo data/report:

```text
core/target/jacoco.exec
core/target/site/jacoco/index.html
core/target/site/jacoco/jacoco.xml

app/target/jacoco.exec
app/target/site/jacoco/index.html
app/target/site/jacoco/jacoco.xml
```

**Không tự kỳ vọng** có `target/surefire-reports` của root chứa toàn bộ XML từ các child modules. Root `packaging=pom` thường không có test classes, còn các modules chạy Surefire trong build directories của chính mình.

## 2. Phân biệt test results, coverage và code-quality reports

| Dữ liệu | Thực chất đo gì? | Công cụ/nguồn | Định dạng phổ biến |
| --- | --- | --- | --- |
| Unit test results | Test cases đã chạy, passed/failed/skipped, thời gian | Maven Surefire | `target/surefire-reports/TEST-*.xml`, `*.txt` |
| Integration test results | Integration tests passed/failed/skipped và summary để fail tại verify | Maven Failsafe | `target/failsafe-reports/TEST-*.xml`, `failsafe-summary.xml` |
| Coverage execution data | JVM chạy những classes/instructions/branches nào | JaCoCo agent | `target/jacoco.exec` (nhị phân) |
| Coverage report theo module | Tỷ lệ instruction/line/branch/method/class coverage | `jacoco:report` | `target/site/jacoco/index.html`, `jacoco.xml`, `jacoco.csv` |
| Coverage report tổng hợp | Coverage của nhiều modules được chọn | `jacoco:report-aggregate` | `target/site/jacoco-aggregate/index.html` và `jacoco.xml` |
| Static analysis | Code smells, rules, duplication... theo tool | Checkstyle, PMD, SpotBugs | XML/HTML/SARIF tùy tool |
| Quality gate | Chính sách bắt buộc để chấp nhận build | JaCoCo check, PMD check, Enforcer, SonarQube/CI gate | Build exit code, CI status, server result |

**Test count không phải coverage.** Ví dụ 100 tests chạy pass vẫn có thể chỉ cover 20% instructions; ngược lại coverage cao không bảo đảm assertions kiểm tra đúng logic. Cũng không nên cộng phần trăm coverage từng module theo trung bình số học: module có 5 lines và module có 5.000 lines phải có trọng số khác nhau.

**Unit test reports khác JaCoCo reports.** `TEST-*.xml` chủ yếu mô tả test cases, `jacoco.xml` mô tả code coverage. SonarQube/Jenkins/GitHub CI cần được cấu hình đúng định dạng khi nhập dữ liệu.

## 3. Surefire và Failsafe trong reactor

### 3.1. Surefire chạy unit tests theo module

Trong một module JAR điển hình, lifecycle phase `test` chạy `maven-surefire-plugin:test`. Test sources ở `src/test/java` được compile trước và Surefire tìm test classes theo naming conventions mặc định, ví dụ:

- `**/Test*.java`
- `**/*Test.java`
- `**/*Tests.java`
- `**/*TestCase.java`

Báo cáo sinh tại `${project.build.directory}/surefire-reports`, tức đường `target` của chính module.

Khi unit test lỗi, Surefire thường **fail module build**, và reactor có thể dừng hoặc tiếp tục tùy fail policy. Root `BUILD FAILURE` cuối cùng không cho biết test nào lỗi nếu bạn không mở report XML/log.

### 3.2. Failsafe kiểm thử tích hợp và kết thúc tại verify

Failsafe thường được bind vào hai goals:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
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
```

Đây là **đoạn plugin**, phải đặt ở `build/plugins` của module thực sự chạy IT.

- Goal `integration-test` chạy test và lưu kết quả, thông thường trì hoãn failure của test assertion.
- Phase `post-integration-test` có cơ hội cleanup fixtures/servers.
- Goal `verify` đọc summary và quyết định build fail nếu IT không đạt.
- Output mặc định ở `target/failsafe-reports` **của module có Failsafe**.

Với Maven 3, nên kết thúc chuỗi bằng `mvn verify`; dừng ở `mvn integration-test` có thể không đi qua `post-integration-test` và `failsafe:verify`.

**Quan trọng:** Failsafe không tự được kích hoạt trên mọi module bởi vì root có `<modules>`. Từng module cần execution tương ứng từ parent inheritance hoặc khai riêng. Với một library chỉ có unit tests, không cần bắt nó có Failsafe.

### 3.3. Phân biệt *Test và *IT

- Surefire mặc định chọn `*Test.java`, `Test*.java`, `*Tests.java` và `*TestCase.java`.
- Failsafe mặc định nhắm `*IT.java`, `IT*.java` và `*ITCase.java`.

Một `OrderIntegrationTest.java` có thể bị Surefire chạy ở `test` vì suffix `Test`, dù developer nghĩ nó là integration test. Quy ước `*IT` cho integration giúp tránh chạy test trước khi setup. Test framework `@Tag("integration")` tự nó không chuyển test sang lifecycle phase integration-test.

## 4. JaCoCo: vì sao dữ liệu từng module chưa đủ?

JaCoCo thường có hai bước cơ bản:

1. `jacoco:prepare-agent` đặt `-javaagent` cho JVM chạy tests và ghi execution data.
2. `jacoco:report` đọc classes, sources và execution data của **một project** để tạo report.

Ví dụ module `core` có 80% line coverage, `app` có 50%; project cần biết “toàn codebase có coverage bao nhiêu?”. Không nên lấy trung bình (80+50)/2 rồi gọi 65%: điều đó bỏ qua kích thước và các counter khác nhau.

`jacoco:report-aggregate` tạo báo cáo từ **các projects mà module thực thi goal khai phụ thuộc**, có thể thêm current project nếu cấu hình `includeCurrentProject=true`. Theo JaCoCo docs, dependency scope có vai trò:

| Scope dependency trong reporting module | Nội dung góp vào aggregate |
| --- | --- |
| `compile` / `runtime` / `provided` | **Classes, sources và execution data** của module dependency |
| `test` | **Chỉ execution data** của dependency, phù hợp module chạy IT riêng mà không muốn tính test classes thành application coverage |

Ví dụ một module `integration-tests` chứa các test gọi `core` và `app` có thể được khai ở scope `test` trong reporting module để góp execution data; còn `core`/`app` ở scope compile để đưa classes cần đo vào mẫu số.

**Chỉ khai tên module trong root `<modules>` không đủ để JaCoCo report-aggregate tự gom đúng classes.** Nên tạo reporting module có dependencies tường minh; các cạnh dependency này cũng giúp Maven reactor build modules có code và test trước reporting module.

### 4.1. JaCoCo agent phải chạy trong JVM thực thi test

Các lệnh sau không tương đương:

```text
mvn test
mvn jacoco:report
```

Nếu JaCoCo agent chưa được attach vào JVM test, `jacoco:report` có thể không có `jacoco.exec` để phân tích. Tạo report HTML không tự instrument code sau sự kiện.

Theo JaCoCo Maven docs, **không dùng `forkCount=0` hoặc `forkMode=never`** với Surefire/Failsafe khi dựa vào JaCoCo javaagent theo cách tiêu chuẩn; JVM không được fork thích hợp có thể làm không có coverage data.

Trong ví dụ bài học, Surefire/Failsafe dùng fork behavior mặc định và JaCoCo agent được cấu hình kế thừa từ parent. Nếu project override `argLine` của Surefire/Failsafe, phải bảo đảm nó không làm mất Java agent của JaCoCo. Khi cần VM args riêng, dùng late interpolation `@{argLine}` theo hướng dẫn Surefire, với điều kiện property đã được setup trước test.

### 4.2. report-aggregate và check không đồng nhất

JaCoCo `report-aggregate` tạo **HTML/XML/CSV report**, không mặc định fail build vì tỷ lệ coverage quá thấp. JaCoCo `check` kiểm tra **coverage rules** trên module tương ứng theo classes/exec data nó đọc. Nếu muốn đặt **một ngưỡng tổng thể trên aggregate XML**, cần thiết kế quality gate thật sự đọc/kết luận trên aggregate report (ví dụ server phân tích có quality gate hoặc script tính từ JaCoCo XML), thay vì giả định `jacoco:check` ở POM gốc tự check toàn bộ reactor.

Một lựa chọn khác là áp JaCoCo `check` ở **mỗi module có production code**, tránh module yếu bị module mạnh “bù” bằng weighted average. Hai chính sách — minimum mỗi module và minimum tổng dự án — có thể kết hợp.

## 5. Ví dụ hoàn chỉnh: reactor 3 module + unit/IT + aggregate coverage

Bài thực hành có:

```text
reactor-quality/
├── pom.xml                          # parent + aggregator
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/reactor/core/PriceCalculator.java
│       └── test/java/vn/example/reactor/core/PriceCalculatorTest.java
├── app/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/reactor/app/ReceiptApp.java
│       └── test/java/vn/example/reactor/app/
│           ├── ReceiptAppTest.java
│           └── ReceiptAppIT.java
└── coverage-report/
    └── pom.xml
```

Đây là **tất cả các file cần tạo**. Build từ root bằng `mvn -B clean verify` với JDK 17+, Maven 3.9.x, repository cho phép tải dependencies/plugins. Mục tiêu quan sát:

- `core`: **4 unit test methods** chạy qua Surefire.
- `app`: **1 unit test method** chạy qua Surefire và **1 integration test method** chạy qua Failsafe.
- `coverage-report`: không có source/test riêng, chỉ tổng hợp JaCoCo HTML/XML/CSV từ `core` và `app`.
- Tổng số test methods theo bài mẫu: **5 unit + 1 integration = 6**, khi không có skip/filter/parent override.
- Java application in ra **chính xác** một dòng khi chạy bằng classpath đúng: `receipt-total=12;band=small`.

Lưu ý: các số đếm trên là **kỳ vọng khi thật sự chạy project**, không phải log đã được thực thi trong tài liệu.

### 5.1. Root pom.xml — aggregator và parent

File `reactor-quality/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>reactor-quality</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
        <module>coverage-report</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.0</junit.version>
        <jacoco.version>0.8.14</jacoco.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
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
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-failsafe-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>${jacoco.version}</version>
                <executions>
                    <execution>
                        <id>attach-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>module-coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích POM gốc:**

- `packaging=pom` cho biết root không phải một application JAR.
- `<modules>` đưa child projects vào reactor.
- Child projects phải khai `<parent>` trỏ tới root mới **kế thừa** plugin management và JaCoCo executions.
- `pluginManagement` pin Compiler/Surefire/Failsafe/JAR versions; nó không tự kích hoạt Failsafe trong những module không khai plugin.
- JaCoCo nằm trong `build/plugins` (không chỉ pluginManagement), nên `prepare-agent` và `report` được **kế thừa** bởi child modules theo cấu hình Maven mặc định.
- `prepare-agent` dùng default phase `initialize` theo goal metadata, nên agent có mặt trước `test`.
- `report` được bind vào `verify` để các module có classes/tests tạo HTML/XML report.
- `report-aggregate` không đặt ở root; ta sẽ đặt nó ở **module coverage-report có dependencies thực**, tránh báo cáo không có classes.

Nếu JaCoCo plugin chạy ở root packaging `pom` hoặc `coverage-report` không có classes, `report` có thể skip vì không có dữ liệu/source; điều đó bình thường. Điểm cần kiểm chứng là `core`/`app` và aggregate module đã có data/report mong muốn.

### 5.2. Module core/pom.xml

File `core/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>reactor-quality</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Version `junit-jupiter` đến từ root `dependencyManagement`; đây là **dependency thật** vì nằm trong `dependencies` của module. Không cần thêm Surefire version ở đây vì parent `pluginManagement` được kế thừa và default JAR lifecycle gọi Surefire.

### 5.3. Module app/pom.xml

File `app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>reactor-quality</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
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

Trong XML trên, thẻ `xsi:schemaLocation` nên theo POM chuẩn đầy đủ; giá trị minh họa được sửa ở phiên bản chuẩn sau:

```xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                    https://maven.apache.org/xsd/maven-4.0.0.xsd"
```

**Lưu ý khi chép POM:** hãy dùng `xsi:schemaLocation` chuẩn ở phần đính chính ngay trên, thay thuộc tính schemaLocation một URL trong `app/pom.xml`. Những phần khác là cấu hình sử dụng được; schemaLocation chủ yếu là hint cho validator/IDE, không mang logic build chính.

**Vì sao Failsafe chỉ ở app?** Module `app` mới có `*IT.java`. Root `pluginManagement` quản lý version, còn việc khai Failsafe trong `app/build/plugins` kích hoạt goals. Module `core` chỉ có unit tests. JaCoCo agent từ parent vẫn được kế thừa vào app nên cả unit và integration tests của app góp execution data.

### 5.4. Module coverage-report/pom.xml

File `coverage-report/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>vn.example</groupId>
        <artifactId>reactor-quality</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>coverage-report</artifactId>
    <packaging>pom</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>app</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>aggregate-reactor-coverage</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report-aggregate</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **module báo cáo** chứ không phải module chứa application classes. Hai dependencies `core` và `app` ở scope mặc định compile làm JaCoCo aggregate lấy classes/sources và execution data của cả hai. Những dependency edges cũng khiến reactor sắp `coverage-report` sau `core`/`app`.

Đừng nhầm scope của reporting module với scope của production app. `coverage-report` có thể phụ thuộc vào `app` để **tạo report**, không có nghĩa `core` trong production phải phụ thuộc ngược lại app.

JaCoCo phiên bản được kế thừa từ parent. `report-aggregate` có default output là `${project.reporting.outputDirectory}/jacoco-aggregate`, thường là:

```text
coverage-report/target/site/jacoco-aggregate/index.html
coverage-report/target/site/jacoco-aggregate/jacoco.xml
coverage-report/target/site/jacoco-aggregate/jacoco.csv
```

**Không mong report tự xuất hiện tại root `target/site`.** Module nào chạy goal mới sở hữu output directory của goal đó, trừ khi được cấu hình khác.


### 5.5. Mã Java đầy đủ cho core

File `core/src/main/java/vn/example/reactor/core/PriceCalculator.java`:

```java
package vn.example.reactor.core;

public final class PriceCalculator {

    public int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("negative price or quantity");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }

    public String band(int total) {
        return total >= 100 ? "large" : "small";
    }
}
```

Phương thức `total` nhân hai số nguyên có kiểm soát tràn qua `Math.multiplyExact`; `band` phân loại tổng giá trị. Có các nhánh bình thường, invalid input, overflow và threshold nên ta có thể quan sát coverage từ nhiều test paths.

### 5.6. Bốn unit tests cho core

File `core/src/test/java/vn/example/reactor/core/PriceCalculatorTest.java`:

```java
package vn.example.reactor.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void computesTotal() {
        assertEquals(12, calculator.total(4, 3));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.total(-1, 3)
        );
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> calculator.total(1_500_000_000, 3)
        );
    }

    @Test
    void classifiesBothBands() {
        assertEquals("small", calculator.band(12));
        assertEquals("large", calculator.band(100));
    }
}
```

Có **4 methods `@Test`**. Surefire chạy chúng trong module `core`; JaCoCo agent ghi execution data tại `core/target/jacoco.exec`. Các assertions cố ý chạm nhiều branches; không suy đoán một tỷ lệ coverage chính xác khi chưa chạy thực tế.

### 5.7. Ứng dụng app gọi core

File `app/src/main/java/vn/example/reactor/app/ReceiptApp.java`:

```java
package vn.example.reactor.app;

import vn.example.reactor.core.PriceCalculator;

public final class ReceiptApp {
    private ReceiptApp() {
    }

    public static String render(int unitPrice, int quantity) {
        PriceCalculator calculator = new PriceCalculator();
        int total = calculator.total(unitPrice, quantity);
        return "receipt-total=" + total + ";band=" + calculator.band(total);
    }

    public static void main(String[] args) {
        System.out.println(render(4, 3));
    }
}
```

`app` compile được vì POM của nó có dependency `vn.example:core:1.0.0`; trong reactor Maven dùng project reactor tương ứng. Khi chạy runtime bằng Java CLI **ngoài Maven**, phải cấp cả `app.jar` và `core.jar` trên classpath; ví dụ không tạo shaded/executable JAR.

### 5.8. Một unit test cho app

File `app/src/test/java/vn/example/reactor/app/ReceiptAppTest.java`:

```java
package vn.example.reactor.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptAppTest {
    @Test
    void rendersReceipt() {
        assertEquals(
            "receipt-total=12;band=small",
            ReceiptApp.render(4, 3)
        );
    }
}
```

Surefire sẽ chạy **1 unit test method** ở module `app`. Java method gọi code của `core` qua dependency, nên coverage data của `app` chủ yếu lưu trong `app/target/jacoco.exec`, có thể chứa thông tin execution của classes từ `core` nữa. JaCoCo `report-aggregate` kết hợp execution data tương ứng với class files của dependencies để thể hiện coverage liên module.

### 5.9. Một integration test cho app

File `app/src/test/java/vn/example/reactor/app/ReceiptAppIT.java`:

```java
package vn.example.reactor.app;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptAppIT {

    @TempDir
    Path temporaryDirectory;

    @Test
    void writesAndReadsReceipt() throws Exception {
        Path file = temporaryDirectory.resolve("receipt.txt");
        Files.writeString(
            file,
            ReceiptApp.render(4, 3),
            StandardCharsets.UTF_8
        );
        assertEquals(
            "receipt-total=12;band=small",
            Files.readString(file, StandardCharsets.UTF_8)
        );
    }
}
```

Đây là **1 integration test method** minh họa tương tác hai modules và file I/O trong môi trường tạm; không cần Docker/database. `@TempDir` do JUnit Jupiter quản lý. Tên `*IT.java` phù hợp Failsafe. Nếu app thực tế cần deploy hoặc kết nối DB, cần thêm setup/teardown ở `pre-integration-test`/`post-integration-test` và vẫn kết thúc bằng `verify`.

### 5.10. Chạy reactor từ root

Tại `reactor-quality/`:

```bash
java -version
mvn --version
mvn -B clean verify
```

Nếu mọi file/POM đúng như mẫu, Maven 3.9.x chạy cùng Java 17+ và dependencies/plugins được resolve:

1. Build POM root.
2. Build module `core`, compile `PriceCalculator`, chạy **4 unit tests**, tạo `core.jar` và per-module JaCoCo report.
3. Build module `app`, compile theo `core`, chạy **1 unit test + 1 Failsafe IT**, tạo `app.jar`, per-module coverage report.
4. Build module `coverage-report` sau vì phụ thuộc `core` và `app`, chạy `report-aggregate`, tạo tổng hợp HTML/XML/CSV.
5. Kết thúc `BUILD SUCCESS` nếu không có build/test/goal failure.

Đó là thứ tự mong đợi theo dependency edges. Java test results có thể được in với format log khác nhau, và JaCoCo có thể báo skip khi dữ liệu bị thiếu/skipped. Không coi log minh họa là log đã chạy thật.

### 5.11. Chạy CLI Java không dựa vào IDE

Vì app JAR trong ví dụ là **thin JAR không có Main-Class manifest**, không chạy `java -jar app/target/app-1.0.0.jar`. Thay vào đó, từ reactor root:

```bash
# Linux/macOS - dấu phân tách classpath là :
java -cp "app/target/app-1.0.0.jar:core/target/core-1.0.0.jar" \
    vn.example.reactor.app.ReceiptApp
```

Trên Windows PowerShell:

```powershell
java.exe -cp "app\target\app-1.0.0.jar;core\target\core-1.0.0.jar" vn.example.reactor.app.ReceiptApp
```

**Stdout chính xác do ứng dụng Java in ra**:

```text
receipt-total=12;band=small
```

Lệnh chạy Java ở đây chứng minh classpath `app + core` đầy đủ; nó không đọc Maven local repository tự động. Nếu muốn executable JAR một file, thêm Maven Shade Plugin/Spring Boot packaging theo yêu cầu khác; không trộn bài tổng hợp report với vấn đề packaging chưa được cấu hình.

## 6. Kết quả báo cáo dự kiến sau mvn verify

Khi build chạy và không có skip flags, tìm:

```text
reactor-quality/
├── core/target/
│   ├── surefire-reports/
│   │   ├── TEST-vn.example.reactor.core.PriceCalculatorTest.xml
│   │   └── vn.example.reactor.core.PriceCalculatorTest.txt
│   ├── jacoco.exec
│   └── site/jacoco/
│       ├── index.html
│       └── jacoco.xml
├── app/target/
│   ├── surefire-reports/
│   │   ├── TEST-vn.example.reactor.app.ReceiptAppTest.xml
│   │   └── vn.example.reactor.app.ReceiptAppTest.txt
│   ├── failsafe-reports/
│   │   ├── TEST-vn.example.reactor.app.ReceiptAppIT.xml
│   │   └── failsafe-summary.xml
│   ├── jacoco.exec
│   └── site/jacoco/
│       ├── index.html
│       └── jacoco.xml
└── coverage-report/target/site/jacoco-aggregate/
    ├── index.html
    ├── jacoco.xml
    └── jacoco.csv
```

**Đây là các file tiêu biểu** chứ không phải toàn bộ cây `target`; các phiên bản plugin có thể sinh thêm metadata, TXT reports, HTML assets và ZIPs.

### 6.1. Mở báo cáo coverage theo module và tổng hợp

Các HTML entry points:

```text
core/target/site/jacoco/index.html
app/target/site/jacoco/index.html
coverage-report/target/site/jacoco-aggregate/index.html
```

XML tương ứng dùng cho máy:

```text
core/target/site/jacoco/jacoco.xml
app/target/site/jacoco/jacoco.xml
coverage-report/target/site/jacoco-aggregate/jacoco.xml
```

`report-aggregate` có thể đưa coverage của module `core` từ cả test JVM ở `core` và `app`, nếu JaCoCo agent đã ghi execution data đúng và JaCoCo có nguồn/classes phù hợp.

**Không kiểm chứng aggregate chỉ bằng việc file HTML tồn tại.** Mở report, xem danh sách modules/packages/classes và counters thực tế. Nếu chỉ có `app` hoặc `core`, kiểm dependencies trong `coverage-report`, reactor execution order và JaCoCo data files.

### 6.2. Có 6 tests không nghĩa là aggregate coverage 100%

Trong bài mẫu, 4 unit tests ở `core`, 1 unit test và 1 IT ở `app` = 6. Nhưng JaCoCo đếm instructions/branches trong **production classes**, không phải số tests; việc có test chạy một codepath không có nghĩa các nhánh đều được cover.

Các counter có thể khác nhau ngay khi sửa compiler version, bytecode generation, agent version hoặc các test cases. Vì vậy bài không bịa một tỉ lệ coverage số học cố định. Đọc số thật từ JaCoCo report và thiết lập ngưỡng dựa trên yêu cầu của sản phẩm.

### 6.3. Test XML là nguồn sự thật về execution

`target/surefire-reports/TEST-*.xml` và `target/failsafe-reports/TEST-*.xml` chứa các `<testsuite>` và `<testcase>` entries do plugins ghi. Khi CI tổng hợp:

- Xác định module gốc của mỗi report để tránh trùng tên lớp test giữa modules.
- Tách unit/integration suites khi muốn policy riêng.
- Quan sát tests, failures, errors, skipped và duration.
- Lưu raw XML làm artifact để điều tra về sau.
- Đừng trộn `failsafe-summary.xml` với `TEST-*.xml` rồi cho đó là một test suite: summary phục vụ Failsafe verdict, định dạng khác.

## 7. Tổng hợp báo cáo test XML từ mọi module trong CI

Nhiều CI products hiểu JUnit-style XML. Thay vì buộc root POM copy XML vào một thư mục, thường đơn giản nhất là **dùng glob xuyên modules**.

Ví dụ đường glob tương đối từ reactor root:

```text
**/target/surefire-reports/TEST-*.xml
**/target/failsafe-reports/TEST-*.xml
```

Cả Jenkins JUnit publisher, GitLab CI/JUnit reports, Azure Pipelines test publishing và nhiều hệ thống khác có cách khai báo glob tương đương. Cú pháp YAML/job config cụ thể **phụ thuộc nền tảng**, không tự copy một mẫu platform khác và kỳ vọng nó chạy.

**CI nên lưu hai nhóm test riêng nếu cần**: unit reports và integration reports, hoặc ít nhất giữ path module trong metadata. Một màn hình duy nhất cần cho phép truy vết test failure về đúng module/class/method.

### 7.1. CI phải đăng báo cáo kể cả khi build fail

Nếu một unit test trong `core` fail, Maven reactor mặc định **fail-fast**, có thể không build tiếp `app` và `coverage-report`. Vì thế file aggregate coverage có thể không tồn tại trong run thất bại, nhưng raw Surefire XML từ `core` vẫn rất có giá trị.

Dùng cơ chế post/finally/**always upload artifacts** của CI để lưu `TEST-*.xml`, Surefire/Failsafe TXT và log bất kể build exit code. Đừng thiết kế pipeline chỉ upload reports trong nhánh `success`: bạn sẽ mất dữ liệu vào lúc cần phân tích nhất.

### 7.2. Không coi missing reports là “0 failures”

Một module có report trống/không tồn tại có thể do:

- Không có tests hợp lệ.
- Plugin không được bind hoặc test source chưa được compile.
- `-DskipTests`, `-DskipITs` hoặc `-Dmaven.test.skip=true`.
- Include/exclude patterns loại hết classes.
- Unit test đã fail ở module trước, reactor chưa chạy module sau.
- Process bị kill, timeout, thiếu dependency/plugin.
- CI glob sai working directory.

Vì vậy một quality dashboard cần cả **module inventory và expected test/report inventory**. “No reports found” nên là tín hiệu cần giải thích, không tự hiểu là “all tests passed”.

### 7.3. Một ma trận trạng thái có ích

| Module | Unit suites | Integration suites | Coverage XML | Quality gate |
| --- | --- | --- | --- | --- |
| `core` | Có `PriceCalculatorTest` | Không yêu cầu ở ví dụ | `core/.../jacoco.xml` | Test pass + policy module |
| `app` | Có `ReceiptAppTest` | Có `ReceiptAppIT` | `app/.../jacoco.xml` | Unit + IT pass |
| `coverage-report` | Không có test source | Không có | `.../jacoco-aggregate/jacoco.xml` | Aggregate completeness |
| Root POM | Không có test source | Không có | Không tự gom | Reactor overall verdict |

Bảng trên không có ý bắt mọi `pom` packaging module phải tạo unit report. Quality policy cần phân biệt **module có code** với **module cấu hình/báo cáo**.

## 8. Maven Surefire Report Plugin: HTML tổng hợp

Maven Surefire Report Plugin là công cụ **khác** Maven Surefire Plugin chạy tests. Nó đọc các `TEST-*.xml` đã tạo và sinh HTML, thường tích hợp với Maven Site/Doxia.

Các goals thường gặp:

- `surefire-report:report`: tạo HTML, có thể gọi test phase trước khi dựng report tùy goal metadata.
- `surefire-report:report-only`: **chỉ dựng report từ kết quả đã có**, không chạy lại tests.
- `surefire-report:failsafe-report-only`: dựng HTML cho kết quả Failsafe, không chạy lại IT.

Plugin có tham số `aggregate` để tạo aggregated report ở root thay vì chỉ per-module reports. Để tránh gọi test lại và báo cáo đè lẫn, ưu tiên chạy `report-only` **sau** khi đã có raw XML từ `mvn verify`.

Lệnh minh họa với plugin version được pin:

```bash
mvn -B clean verify
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.5.2:report-only -Daggregate=true
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.5.2:failsafe-report-only -Daggregate=true
```

**Giới hạn quan trọng:** cách aggregation, thư mục HTML output, Maven Site integration và hành vi khi gọi goal từ root phụ thuộc chính xác phiên bản plugin, reactor selection và reporting configuration. Hãy xem build logs và file HTML thực tế, đừng khẳng định mọi version viết đúng một `target/site/surefire-report.html`. Goals `report-only` chỉ sử dụng XML đã tồn tại; nếu module chưa chạy, HTML không thể bổ sung test bị bỏ qua.

Do report plugin goals không được đánh dấu thread-safe ở một số phiên bản, nên tránh `mvn -T` khi đang tạo HTML aggregate nếu chưa xác minh plugin compatibility. Với CI cơ bản, raw JUnit XML globs thường đáng tin cậy và ít phức tạp hơn.

### 8.1. Aggregate unit report khác aggregate coverage report

| Loại aggregate | Nguồn | Mục đích |
| --- | --- | --- |
| Surefire Report Plugin aggregate | `TEST-*.xml` từ Surefire | Số test methods, pass/fail/skipped/time |
| Failsafe Report HTML | `TEST-*.xml` từ Failsafe | Integration test outcomes |
| JaCoCo `report-aggregate` | `*.exec` và classes/sources reactor dependencies | Instruction/line/branch coverage |
| SonarQube hoặc CI dashboard | Kết quả tool/plugin sau scan/import | Góc nhìn quality policy, trend và gate |

Một report HTML duy nhất có thể hiển thị nhiều test suites nhưng **không tự trở thành một coverage measurement**. Ngược lại `jacoco.xml` không phải JUnit XML để đưa vào JUnit report importer.

## 9. Tạo coverage quality gate thay vì chỉ xuất HTML

### 9.1. Per-module JaCoCo check

Có thể bind `jacoco:check` tại phase `verify` trong các modules có production code và cấu hình rules. Ví dụ **đoạn plugin execution bổ sung**, không nằm sẵn trong POM thực hành:

```xml
<execution>
    <id>enforce-line-coverage</id>
    <phase>verify</phase>
    <goals>
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
                        <minimum>0.70</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</execution>
```

`${project.build.directory}/jacoco.exec` và compiled classes phải có dữ liệu để `check` đánh giá. Con số `0.70` là **ví dụ policy**, không phải yêu cầu toàn cầu. Nếu bạn copy execution này vào parent để mọi modules kế thừa, cần xử lý modules `pom` không có code hoặc modules intentionally excluded. Với dự án đang học, trước hết tạo report và kiểm tra đủ data, rồi mới bật ngưỡng và chạy negative test.

**Không gọi `jacoco:check` trên parent POM và xem đó là “coverage 70% của toàn reactor”** nếu không có cơ chế aggregate-specific gate khác. JaCoCo check làm việc với classes/execution data thuộc project/config cụ thể.

### 9.2. Ngưỡng tổng dự án trên aggregate XML

JaCoCo aggregate XML có counters tương ứng với toàn bộ những classes được chọn. Một CI quality script có thể đọc `coverage-report/target/site/jacoco-aggregate/jacoco.xml`, kiểm tra số `missed` và `covered` trong counter thích hợp, rồi tính:

```text
coveredRatio = covered / (missed + covered)
```

Không tính nếu `missed + covered == 0`; trường hợp report rỗng là **missing coverage data**, không phải 100%. Khi viết script phải chọn đúng `counter type` (LINE/BRANCH/INSTRUCTION) và đúng scope; aggregate XML còn có counter ở nhiều levels nên chỉ cộng **top-level counter** tương ứng, không cộng lại mọi class/package rồi đếm trùng.

Dưới đây là ví dụ Python 3 đọc **top-level LINE counter** trong JaCoCo XML, thích hợp chạy ở CI sau `mvn verify`. Không phụ thuộc package Python ngoài stdlib:

```python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

report = Path(
    "coverage-report/target/site/jacoco-aggregate/jacoco.xml"
)
if not report.is_file():
    raise SystemExit(f"Coverage report missing: {report}")

root = ET.parse(report).getroot()
if root.tag != "report":
    raise SystemExit(f"Unexpected JaCoCo XML root: {root.tag}")

counters = [
    node for node in root.findall("counter")
    if node.get("type") == "LINE"
]
if len(counters) != 1:
    raise SystemExit("Expected one top-level LINE counter")

missed = int(counters[0].attrib["missed"])
covered = int(counters[0].attrib["covered"])
total = missed + covered
if total == 0:
    raise SystemExit("Coverage report has zero lines")

ratio = covered / total
print(f"Aggregate LINE coverage: {ratio:.2%}")
if ratio < 0.70:
    raise SystemExit("Coverage quality gate failed")
```

**Đây là code runnable độc lập** khi được lưu thành `check_aggregate_coverage.py` và có sẵn XML đúng ở path trên. Output phần trăm phụ thuộc coverage thực tế của build; bài **không bịa giá trị phần trăm dự kiến**. Exit code khác 0 khi thiếu file, cấu trúc XML sai, thiếu line counter hoặc ratio thấp hơn 70%.

Nếu policy yêu cầu nhiều module, script cần kiểm tra aggregate XML có đủ bundles/classes được kỳ vọng (ví dụ `core` và `app`), chứ không cho phép một report chỉ chứa module nhỏ vượt ngưỡng rồi pass.

### 9.3. Vì sao không lấy trung bình số học của module coverage?

Giả sử module A có 10 lines, cover 9 (90%); B có 990 lines, cover 495 (50%). Trung bình hai tỷ lệ là 70%, nhưng toàn bộ code có:

```text
covered = 9 + 495 = 504
total   = 10 + 990 = 1000
aggregate LINE coverage = 50.4%
```

**Đây là ví dụ số học minh họa, không phải kết quả của source code trong mục 5.** Coverage tổng phải tính theo counter weights và class scope, chứ không bình quân số modules. Nếu report aggregate rỗng hoặc thiếu module, ngay cả công thức đúng cũng cho kết quả sai về tổng dự án.


## 10. Tích hợp SonarQube/quality dashboard cho multi-module

SonarScanner for Maven có thể phân tích Maven multi-module project bằng chính Maven project model. Dữ liệu mà scanner dùng bao gồm source/tests/binary info, còn **coverage report phải được tạo trước** và được chỉ đúng đường dẫn JaCoCo XML; scanner không tự tạo code coverage từ việc chỉ có `pom.xml`.

Trong project có JaCoCo aggregate XML, nhiều pipeline đặt `sonar.coverage.jacoco.xmlReportPaths` trỏ tới:

```text
coverage-report/target/site/jacoco-aggregate/jacoco.xml
```

**Cẩn thận với đường dẫn trong multi-module:** property này có thể được đánh giá theo module basedir của scanner. Khi khai trong child module, cần điều chỉnh thành đường tương đối từ child (ví dụ `../coverage-report/target/...`) hoặc dùng đường dẫn tuyệt đối đã xác minh. Không tự cho rằng đường tương đối từ reactor root tự đúng cho mọi module.

Một pipeline khái quát:

```text
mvn -B clean verify
  ├─ core/app Surefire/Failsafe outputs
  ├─ JaCoCo per-module reports
  └─ coverage-report JaCoCo aggregate XML
        |
        v
SonarScanner for Maven (configured token/server/project)
        |
        v
SonarQube dashboard + quality gate
```

Ví dụ gọi scanner theo tài liệu, sau khi project đã build, trong môi trường đã cấu hình token/host (không hardcode secrets vào source):

```bash
mvn org.sonarsource.scanner.maven:sonar-maven-plugin:sonar
```

**Đây là lệnh minh họa chức năng**, không phải lệnh chạy được nếu chưa có SonarQube server, token và project config. Khi chạy scanner thành invocation riêng cho multi-module project, SonarSource có lưu ý có thể cần bước `mvn install` trước đó để đảm bảo các artifact reactor dependencies sẵn có cho scanner. Hãy xem tài liệu scanner version đang dùng, đặc biệt từ dòng 5.x có JRE auto-provisioning và yêu cầu Java runtime riêng.

Không đưa token vào tài liệu hoặc CI console logs. Sử dụng secret manager và biến môi trường do CI cung cấp. Quality gate của server cũng cần CI có cơ chế **chờ/đánh giá kết quả** nếu muốn chặn merge/deploy; việc scanner upload report không tự đồng nghĩa pipeline đã đợi kết luận từ server.

### 10.1. Static analysis và coverage là hai luồng khác nhau

Các plugins như Maven Checkstyle, PMD, SpotBugs hay Enforcer có nhiệm vụ khác JaCoCo:

- **Checkstyle**: quy ước/style và nhiều source-level rules.
- **PMD**: static code analysis; PMD Plugin còn có goals aggregate như `aggregate-pmd`/`aggregate-cpd` và checks tương ứng trong các version hỗ trợ.
- **SpotBugs**: bytecode static analysis; cần được bind/check ở modules có compiled classes.
- **Enforcer**: Maven/JDK/dependency/version/build policy constraints.
- **JaCoCo**: coverage từ code thực thi trong test JVMs.
- **SonarQube**: phân tích/hiển thị/trend và quality gates theo scanner+server config.

Chỉ plugin có goal aggregate phù hợp mới tự làm được phân tích tổng hợp. `pmd:aggregate-pmd` không đồng nghĩa `pmd:aggregate-pmd-check`: cái trước tạo report, cái sau có thể fail build theo violations. Tương tự, `jacoco:report-aggregate` không thay `jacoco:check`.

## 11. Chính sách báo cáo trong reactor khi test fail

### 11.1. Fail-fast, fail-at-end, fail-never

Maven reactor hỗ trợ:

| Switch | Mục đích | Hệ quả với reports |
| --- | --- | --- |
| `-ff` / `--fail-fast` | Dừng sớm khi module fail (mặc định) | Những modules phía sau chưa có reports |
| `-fae` / `--fail-at-end` | Tiếp tục những modules có thể build, báo failures cuối cùng | Thu được thêm reports từ modules độc lập |
| `-fn` / `--fail-never` | Cố tiếp tục và trả exit code 0 dù có failures | **Nguy hiểm nếu CI chỉ nhìn exit code** |

Với `-fae`, **dependent modules vẫn có thể bị skip** nếu một module mà chúng cần fail: ví dụ `app` phụ thuộc `core`, `coverage-report` phụ thuộc cả `core` và `app`; nếu `core` fail, không mặc nhiên có aggregate report.

**Không dùng `-fn` làm lệnh kiểm định release**, vì CI có thể xanh dù Maven báo module failure. `-fae` hữu ích cho job thu thập feedback, nhưng gate cuối phải nhận biết failures và tình trạng thiếu modules.

### 11.2. -pl, -am và phạm vi báo cáo

Ví dụ từ root:

```bash
# Chạy core và những dependencies cần thiết
mvn -pl :core -am verify

# Build app cùng core dependency
mvn -pl :app -am verify

# Build module report và các module mà report phụ thuộc
mvn -pl :coverage-report -am verify
```

Lệnh thứ ba có thể tạo aggregate coverage đúng **nếu** modules/test executions thực sự chạy trong invocation này. Nếu chỉ chạy `-pl :coverage-report` mà không có `-am` trong workspace chưa install/build những dependencies tương ứng, Maven có thể không resolve artifacts hoặc JaCoCo không có exec data.

Với đa module, lệnh `mvn -pl :app test` không có `-am` có thể lỗi dependency `core` chưa cài vào local repository. Khi dùng `-pl`/`-am` để tối ưu CI, cần biết report nào bị giới hạn bởi module selection; **không nhầm partial coverage report với toàn reactor**.

### 11.3. Parallel reactor và shared reporting files

Maven có `-T` chạy modules song song, nhưng một số reporting goals (đặc biệt Surefire Report Plugin HTML goals) không được đánh dấu thread-safe. Nếu nhiều modules ghi chung một output path không được thiết kế để concurrency-safe, reports có thể bị ghi đè hoặc không nhất quán.

Thiết kế an toàn:

- Giữ per-module data trong `${project.build.directory}` của chính module.
- Reporting module có dependency edges để được xếp sau code/test modules.
- Chỉ dùng `-T` sau khi xác minh các plugin/goal versions hỗ trợ parallel builds.
- Không dùng một `coverage.exec` duy nhất trong root cho nhiều JVM song song nếu chưa có cơ chế dữ liệu và locking phù hợp.

## 12. Mất coverage do cấu hình fork hoặc argLine

JaCoCo Maven Plugin chuẩn bị Java agent thông qua property `argLine` cho Surefire/Failsafe. Các lỗi phổ biến:

- Surefire `forkCount=0` làm JaCoCo agent không được gắn vào forked JVM theo cách yêu cầu.
- `<argLine>-Xmx512m</argLine>` ghi đè hoàn toàn property do JaCoCo tạo, vì vậy agent biến mất.
- Test được thực thi bằng custom JVM/process không có JaCoCo agent.
- Failsafe chạy `-DskipITs`, khiến module `app` không có IT coverage.
- `mvn -DskipTests verify` tạo reporting module nhưng không có `jacoco.exec`.
- Không chạy `clean` và vô tình dùng `jacoco.exec` của lần trước, làm tỷ lệ không phản ánh commit hiện tại.
- Execution data file path khác mặc định, nhưng report-aggregate chưa cấu hình `dataFileIncludes` hoặc file không được thu.
- Code chạy trong forked server/container từ IT, nhưng server process không có JaCoCo agent; test JVM coverage không phản ánh code ở process server.

### 12.1. Cấu hình JVM args đúng cách

Một đoạn Surefire configuration minh họa khi cần thêm VM options:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <argLine>@{argLine} -Xmx512m</argLine>
    </configuration>
</plugin>
```

Late substitution `@{argLine}` cho phép Surefire sử dụng property mà JaCoCo plugin đã đặt trong lifecycle trước đó, thay vì đóng cứng một chuỗi và bỏ `-javaagent`. Nếu một profile tắt JaCoCo mà vẫn giữ `@{argLine}`, tùy cấu hình phải khai default argLine rỗng để tránh unresolved placeholder; trong ví dụ chính JaCoCo luôn chạy ở initialize.

Đừng đặt đoạn này vào root POM rồi giả định mọi test JVM/custom runner đều nhận nó: plugin-specific configuration, fork handling và module inheritance vẫn phải được xác minh từ logs.

### 12.2. Unit và integration coverage trong cùng jacoco.exec

Trong ví dụ, `prepare-agent` được kế thừa và sử dụng cho các forked test JVMs. Các lần thực thi JaCoCo agent thường **append** dữ liệu vào file execution data của module, nên unit và integration coverage của `app` có thể cùng đóng góp vào `app/target/jacoco.exec`.

Nếu dự án muốn **tách riêng unit và integration coverage** rõ ràng, JaCoCo có `prepare-agent-integration` và `report-integration`, với file dữ liệu mặc định có thể là `jacoco-it.exec`. Sau đó cấu hình report-aggregate `dataFileIncludes` để thu cả hai loại exec nếu cần. Không tự kết luận tổng coverage đã bao gồm IT khi chưa biết agent path/execution.

## 13. Kiểm tra tính đầy đủ của một quality dashboard

Một bảng KPI nên có tối thiểu:

| Chỉ tiêu | Tính/đọc từ đâu | Nguy cơ diễn giải sai |
| --- | --- | --- |
| Module count trong reactor | Các modules được chọn từ POM/build log | `-pl` có thể chỉ chạy subset |
| Modules có production classes | Artifact/classes thực tế | POM reporting module không cần test |
| Unit tests run | Surefire `TEST-*.xml` | Zero tests không đồng nghĩa pass |
| Integration tests run | Failsafe `TEST-*.xml` | `-DskipITs`/goal chưa bind |
| Test failures/errors | JUnit XML + build status | Fail-at-end/module skip làm totals thiếu |
| Test skipped | JUnit XML | Skipped lớn có thể làm dashboard xanh giả |
| Module coverage LINE/BRANCH | JaCoCo per-module XML | Không bình quân phần trăm giữa modules |
| Aggregate coverage LINE/BRANCH | JaCoCo aggregate XML | Có thể thiếu code modules nếu dependencies sai |
| Static analysis violations | PMD/Checkstyle/SpotBugs XML | Report tạo ra không có nghĩa gate đã bật |
| Quality gate pass/fail | Maven exit code + rules/CI/server status | `-fn` trả 0, skipped gates |
| Reporting artifacts present | CI upload inventory | Missing report không phải 0 failures |

### 13.1. Ví dụ toán học về test count

Trong bài thực hành:

```text
core/Surefire: 4 tests
app/Surefire:  1 test
app/Failsafe:  1 test
--------------------
Total:         6 test methods
```

Trong JUnit XML, hãy dùng các attributes/testsuites phù hợp để xác nhận số thật. JUnit dynamic/parameterized tests, reruns và flaky-test handling có thể khiến số testcases khác con số source methods, nên policy trong CI phải định nghĩa “test count” là **executed test cases reported by the runner**, không mặc định là số phương thức có `@Test` trong source.

### 13.2. Không đếm trùng giữa báo cáo

Nếu một CI job thu `**/TEST-*.xml` quá rộng, có thể bắt cả Surefire, Failsafe, TestNG, generated/cached reports hoặc report của lần build cũ. Dùng thư mục `target/surefire-reports`, `target/failsafe-reports` cụ thể và `mvn clean` khi muốn tránh stale data.

Nếu cùng một class bị chạy bởi cả Surefire và Failsafe do naming/includes sai, tổng số test tăng nhưng không có nghĩa có nhiều coverage thật. Phân tách `*Test`/`*IT` và đọc report classname/path.

## 14. Troubleshooting khi báo cáo multi-module thiếu hoặc sai

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Root `target/surefire-reports` trống | Reports nằm ở child module | Thu globs dưới `**/target/surefire-reports` |
| `coverage-report` không có JaCoCo aggregate | Không bind `report-aggregate`, chạy partial reactor, plugin skip | Xem plugin execution, build logs, `-pl/-am` |
| Aggregate HTML có file nhưng không có `core` | Reporting module không phụ thuộc core | Thêm dependency core scope phù hợp |
| Aggregate chỉ thấy một module | Thiếu source/classes/exec data hoặc dependency | Kiểm scope, JaCoCo files và module order |
| Unit reports có nhưng `jacoco.exec` không có | Agent không chạy/argLine bị override/forkCount=0 | Kiểm `prepare-agent` logs và JVM |
| Module `app` có IT test nhưng report không có | Failsafe chưa bind/cấu hình class name sai | Khai hai goals, chạy `verify` |
| `mvn test` pass nhưng integration coverage không có | Failsafe chạy ở phases sau package | Chạy `mvn verify` |
| Root báo fail trước reporting module | Reactor fail-fast do unit/IT/compile lỗi | CI luôn upload raw XML; sửa lỗi rồi build lại |
| Quality HTML xanh nhưng JUnit XML có failures | Report cũ, pipeline dùng `-fn`, cache sai | `clean`, xem exit code và timestamps |
| SonarQube không nhận coverage | Sai XML path hoặc scanner chạy trước JaCoCo | Tạo XML trước, set reportPaths đúng basedir |
| CI test count 0 | Globs sai hoặc tests bị skip | Kiểm build logs, path/filename, skip flags |
| Coverage 100% bất ngờ | Report chỉ chứa module nhỏ hoặc 0 class | Audit module completeness và counters |
| Quality gate không fail khi coverage thấp | Chỉ tạo report, chưa bind `check` hoặc server gate | Thêm rule/check và negative test |
| Maven `-T` báo lỗi reports bất thường | Reporting goal không thread-safe, shared output | Chạy sequential reporting hoặc kiểm plugin |
| Báo cáo static analysis chỉ có root | Plugin chạy ở `pom` root, không được child kế thừa | Kiểm `build/plugins` vs pluginManagement/inheritance |
| POM có dependencies nhưng reactor build order sai | Chỉ dùng `dependencyManagement`, chưa khai actual dependency | Khai `dependencies` nếu cần edge |
| Test coverage khác sau `-pl :app` | Partial module set và data | Ghi rõ scope, tránh so với full-reactor report |

### 14.1. Quy trình điều tra thực tế

1. Chạy từ **reactor root** và in môi trường: `mvn --version`.
2. Xem reactor build order trong Maven logs: module nào thực sự được chọn/chạy.
3. Xem parent/child effective POM: `mvn help:effective-pom -Doutput=target/effective-pom.xml` (lưu ý goal có thể chạy cho từng module theo invocation).
4. Chạy `mvn -B clean verify` không có skip flags.
5. Kiểm `core/target/surefire-reports`, `app/target/surefire-reports` và `app/target/failsafe-reports`.
6. Kiểm `core/target/jacoco.exec`, `app/target/jacoco.exec`.
7. Mở `coverage-report/target/site/jacoco-aggregate/index.html` xem bundles/classes/modules.
8. Đối chiếu test counts và JaCoCo XML counters với policy.
9. Chạy negative case có chủ đích (trên branch/test environment): làm fail 1 unit/IT test, hạ coverage bằng xóa assertion/case, xác minh pipeline báo failure.
10. Đảm bảo CI vẫn giữ raw test XML khi có module failure và không xuất báo cáo cũ như bản mới.

**Bảo mật:** log `mvn -X` có thể lộ repository URLs, đường dẫn, VM args, build environment và thông tin hạ tầng. Lọc secrets trước khi chia sẻ.

## 15. Checklist thiết kế báo cáo chất lượng đáng tin

- Root aggregator được khai `<modules>` rõ và child `<parent>` đúng nếu cần kế thừa cấu hình.
- Reactor dependencies thể hiện đúng code dependency, và reporting module có actual dependencies lên các modules cần đo.
- Maven/plugin/JDK versions được pin; mỗi module có lifecycle phù hợp.
- Surefire unit tests và Failsafe integration tests **thật sự chạy**, không chỉ plugins xuất hiện trong POM.
- Bảo đảm report file paths được tạo trong `target` của các modules, không đoán mọi thứ nằm ở root.
- JaCoCo agent gắn vào JVM test trước khi chạy test, không bị `argLine`/forkCount override.
- `jacoco:report-aggregate` chạy sau modules có data, kiểm được danh sách classes và module coverage.
- Chỉ tổng hợp coverage theo counters có trọng số, không bình quân tỷ lệ modules.
- JaCoCo report khác `check`; HTML khác quality gate; cấu hình policy chặn release rõ ràng.
- CI lưu raw Surefire/Failsafe XML, JaCoCo XML/HTML và analysis artifacts; ưu tiên upload kể cả khi job fail.
- Quality dashboard công bố các modules đã chạy/không chạy, test counts và missing reports.
- `-pl`, `-am`, `-fae`, `-T` được dùng có chủ đích, tránh so partial data với full reactor.
- Với CI scanner bên ngoài, report phải sinh trước scanner và paths phải đúng theo module basedir.
- Ít nhất một negative test chứng minh thiếu test/coverage hoặc module build failure thực sự làm gate đỏ.
- Mọi dữ liệu từ report/CI gắn với một commit/build ID; không trộn reports từ các bản code khác nhau.

## 16. Câu hỏi tự luyện và đáp án

**Câu 1.** Root POM có `<modules>core,app</modules>`. Vì sao `root/target/surefire-reports` không tự chứa kết quả unit tests của core/app?

**Đáp án:** Mỗi child project chạy Surefire và ghi vào build directory riêng. Reactor aggregation không tự hợp nhất reports.

**Câu 2.** Nếu module `coverage-report` chỉ nằm trong `<modules>` mà không có `<dependencies>` lên `core` và `app`, JaCoCo `report-aggregate` có tự biết cần tính chúng vào coverage không?

**Đáp án:** Không theo cơ chế chuẩn của goal. Nó dùng dependencies của reporting project để xác định classes/sources/exec data, nên phải khai dependencies (và scope phù hợp) thực tế.

**Câu 3.** Module `integration-tests` không có production classes nhưng chạy tests trên `core` và `app`. Khi khai dependency từ reporting module tới integration-tests với scope `test`, JaCoCo aggregate sử dụng phần nào?

**Đáp án:** Theo JaCoCo docs, dependency scope test chỉ góp execution data, không thêm test module classes/sources vào coverage denominator.

**Câu 4.** `mvn verify` thành công và có `jacoco.xml` nhưng tại sao chưa chắc coverage 70% đã được enforce?

**Đáp án:** `report`/`report-aggregate` tạo báo cáo; cần `jacoco:check` rule hoặc CI/server quality gate thực sự đọc kết quả và fail khi thấp.

**Câu 5.** Vì sao không lấy trung bình 80% và 50% của hai modules để báo coverage toàn dự án là 65%?

**Đáp án:** Tỷ lệ module phụ thuộc số instructions/lines/branches; aggregate phải tính từ tổng covered/missed counters, không phải trung bình không trọng số.

**Câu 6.** App có `ReceiptAppIT` nhưng `mvn test` không chạy. Phải dùng command nào để thực hiện Failsafe và chốt kết quả?

**Đáp án:** `mvn verify` với Failsafe được bind cả `integration-test` và `verify`.

**Câu 7.** Để thu JUnit XML từ các modules, CI nên chọn những đường glob nào?

**Đáp án:** `**/target/surefire-reports/TEST-*.xml` và `**/target/failsafe-reports/TEST-*.xml`, có tính đến working directory và CI-specific glob syntax.

**Câu 8.** Lệnh `mvn -pl :coverage-report -am verify` giúp gì?

**Đáp án:** Chọn reporting module và các reactor dependencies cần để build nó, giảm nguy cơ thiếu classes/exec data nếu chỉ chọn report module. Vẫn phải xác minh plugin/test executions và module scope.

**Câu 9.** Khi Surefire trong module core fail, tại sao aggregate JaCoCo file có thể không được tạo?

**Đáp án:** Reactor mặc định fail-fast; app/coverage-report phụ thuộc core có thể bị skip. CI nên publish raw test reports ngay cả khi build fail.

**Câu 10.** Code mẫu có bao nhiêu unit/IT test methods nếu mọi module chạy đầy đủ?

**Đáp án:** `core` 4 unit, `app` 1 unit và 1 integration = 6 methods, nhưng phải đọc thực tế `TEST-*.xml` để xác minh executed test cases.

## 17. Tài liệu chính thức

- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — POM Reference (Aggregation / Inheritance)](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Introduction and Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin — Introduction and Lifecycle](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Surefire Report Plugin — Introduction](https://maven.apache.org/surefire/maven-surefire-report-plugin/)
- [Maven Surefire Report Plugin — report-only goal](https://maven.apache.org/surefire/maven-surefire-report-plugin/report-only-mojo.html)
- [Maven Surefire Report Plugin — failsafe-report-only goal](https://maven.apache.org/surefire/maven-surefire-report-plugin/failsafe-report-only-mojo.html)
- [JaCoCo Maven Plugin — Overview and Goals](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [JaCoCo — report-aggregate goal](https://www.jacoco.org/jacoco/trunk/doc/report-aggregate-mojo.html)
- [JaCoCo — check goal](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [Maven PMD Plugin — Aggregator Goals](https://maven.apache.org/plugins/maven-pmd-plugin/plugin-info.html)
- [SonarScanner for Maven — Maven multi-module and coverage](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/scanners/sonarscanner-for-maven)
