# Maven Surefire Plugin và quan hệ với phase test

Trong một dự án Maven, `mvn test` là yêu cầu chạy **phase `test` của default lifecycle**. Đối với packaging `jar` thông thường, Maven thực hiện các bước chuẩn bị trước đó — biên dịch code chính, xử lý test resources, biên dịch test source — rồi gọi **goal `surefire:test` của Maven Surefire Plugin** để tìm, chạy và báo cáo kết quả unit tests.

**Điểm mấu chốt:** `test` là **phase**; `surefire:test` là **plugin goal**. Cả hai liên quan trực tiếp nhưng **không đồng nghĩa**. Gọi `mvn surefire:test` trực tiếp không tự động thực hiện toàn bộ phase `test-compile` trước nó; nếu file test vừa thay đổi, có thể chưa được biên dịch lại.

```text
mvn clean test
    |
    +--> clean lifecycle: clean:clean
    |
    +--> default lifecycle (packaging jar)
           |
           +--> process-resources       resources:resources
           +--> compile                 compiler:compile
           +--> process-test-resources  resources:testResources
           +--> test-compile            compiler:testCompile
           +--> test                    surefire:test
                                             |
                                             +-- nhận test classpath
                                             +-- scan test classes
                                             +-- chọn provider/TestEngine
                                             +-- chạy test methods
                                             +-- ghi XML/text reports
                                             +-- báo kết quả cho Maven
```

Đây là sơ đồ khái niệm: Maven còn có nhiều phase không hiển thị, và POM có thể bind thêm goals tùy dự án. Bài sử dụng **Java 17+, Maven 3.x, Maven Surefire Plugin 3.6.1 và JUnit Jupiter 5.11.4** làm bộ ví dụ có version tường minh. Với plugin/framework phiên bản khác, kiểm tra tài liệu tương ứng trước khi suy rộng hành vi.

Mục tiêu sau bài: hiểu lifecycle, tạo test chạy được bằng JUnit 5, xác minh Surefire thực sự đã chạy tests, đọc reports, lọc/chạy lại/skip tests đúng ý nghĩa, phân biệt Surefire với Failsafe và xử lý những lỗi thường gặp trong CI.

## 1. Phase, goal, plugin và framework khác nhau ra sao?

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Phase | `test` | Một mốc trong default lifecycle của Maven. |
| Plugin | `maven-surefire-plugin` | Artifact Maven cung cấp các goals để thực thi tests. |
| Goal | `surefire:test` | Hành động thực tế mà plugin cung cấp. |
| Test framework | JUnit Jupiter | API `@Test`, assertions và engine phát hiện/thực thi test methods. |
| Provider | Surefire/JUnit Platform provider | Cầu nối giữa Surefire và framework engine. |
| Test dependency | `junit-jupiter` với `scope=test` | Thư viện cần cho test source và test runtime. |
| Report | `target/surefire-reports/TEST-*.xml` | Dữ liệu kết quả do test execution ghi cho CI hoặc công cụ báo cáo. |

Surefire **không phải compiler**. Nó không tự biến một file `.java` thành `.class`; việc đó do Compiler Plugin ở phase `test-compile` xử lý. Surefire cũng **không phải JUnit**: JUnit cung cấp `@Test` và assertions, Surefire kết nối với engine của JUnit để chạy các bài kiểm thử trong quy trình Maven.

### 1.1. Hai lệnh nhìn giống nhau nhưng khác việc

Lệnh phase:

```bash
mvn test
```

Maven chạy các phase từ trước đến `test` trong default lifecycle, nên thường có `compiler:testCompile` trước `surefire:test`.

Lệnh goal trực tiếp:

```bash
mvn org.apache.maven.plugins:maven-surefire-plugin:3.6.1:test
```

Chỉ yêu cầu một goal cụ thể; nó **không bảo đảm** đã compile main/test source mới. Dạng rút gọn:

```bash
mvn surefire:test
```

cũng là gọi goal trực tiếp nhưng plugin prefix và version được resolve theo cấu hình Maven. Đây là nguồn nhầm lẫn thường gặp khi tests không phản ánh source vừa sửa.

**Quy tắc:** muốn build đúng lifecycle thì dùng `mvn test` hoặc `mvn clean test`; chỉ gọi riêng `surefire:test` khi bạn có chủ đích chạy trên output/classes đã chuẩn bị.

## 2. Surefire được gọi ở đâu trong default lifecycle?

Với project `<packaging>jar</packaging>` theo bindings tiêu chuẩn, các phase gần unit test:

| Phase | Goal thông dụng | Kết quả |
| --- | --- | --- |
| `validate` | Goal kiểm tra nếu POM cấu hình | Kiểm tra các điều kiện đầu vào. |
| `process-resources` | `resources:resources` | Xử lý main resources. |
| `compile` | `compiler:compile` | Biên dịch `src/main/java` vào `target/classes`. |
| `process-test-resources` | `resources:testResources` | Xử lý `src/test/resources`. |
| `test-compile` | `compiler:testCompile` | Biên dịch `src/test/java` vào `target/test-classes`. |
| **`test`** | **`surefire:test`** | Phát hiện và chạy unit tests. |
| `package` | `jar:jar` với packaging jar | Đóng gói sản phẩm sau khi tests qua. |
| `verify` | Goals đã bind, nếu có | Thực hiện các checks bổ sung sau package. |

Không phải mọi packaging (`pom`, `war`, `maven-plugin`...) đều bind các goal giống `jar`. `<executions>` của POM, plugins trong parent và profiles có thể bổ sung/điều chỉnh. Ngay cả khi phase `test` được chạy, **không thể kết luận có tests thực sự chạy** nếu discovery bị lọc hoặc tests bị skip.

### 2.1. So sánh những lệnh quan trọng

| Lệnh | Compile main | Compile tests | Chạy Surefire |
| --- | --- | --- | --- |
| `mvn compile` | Có | Chưa | Chưa |
| `mvn test-compile` | Có | Có | Chưa |
| `mvn test` | Có | Có | Có |
| `mvn package` | Có | Có | Có, trước khi đóng JAR |
| `mvn verify` | Có | Có | Có, cùng các goal được bind ở giai đoạn sau |
| `mvn surefire:test` | Không tự đi qua các phase trước | Không tự compile lại test | Có thể chạy test classes đã có |
| `mvn clean test` | Xóa build output cũ rồi compile | Có | Có |

Bảng giả định dự án Java jar thông thường, không skip và không có cấu hình đặc biệt. **`mvn package` không phải lệnh “bỏ qua test để đóng gói”**; default lifecycle cần đi qua phase test. Nếu Surefire báo test failure, lệnh package có thể dừng trước khi tạo artifact mới.

### 2.2. Tại sao `mvn test-compile` chưa chạy tests?

`compiler:testCompile` chỉ biên dịch test code. Một file `PriceCalculatorTest.class` có thể xuất hiện trong `target/test-classes` mà chưa có test method nào chạy. Để kiểm tra phương thức `@Test`, phải gọi phase `test` hoặc goal Surefire trên test output hợp lệ.

### 2.3. Có cần tự bind `surefire:test` không?

Trong Maven project `jar`, **không cần** thêm execution tự bind `surefire:test` vào phase `test` nếu chỉ muốn behavior mặc định. Một số cấu hình vô tình làm test chạy **hai lần**, ví dụ một lần do packaging binding, một lần do custom execution trùng phase.

Nếu muốn đổi version, timeout, include/exclude patterns, fork options... thì cấu hình plugin theo POM, nhưng để lifecycle quyết định khi nào gọi nó.

## 3. Cấu trúc source/test mặc định trong Maven

```text
project-root/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── target/
    ├── classes/
    ├── test-classes/
    └── surefire-reports/
```

- `src/main/java`: mã ứng dụng.
- `src/test/java`: code test dùng framework như JUnit/TestNG.
- `src/test/resources`: fixtures và dữ liệu cần cho test, được đưa vào test resources path theo cấu hình.
- `target/classes`: main classes do Compiler Plugin tạo.
- `target/test-classes`: test classes do Compiler Plugin tạo.
- `target/surefire-reports`: reports do Surefire tạo.

`target` không phải nguồn code; nên để Maven tạo lại bằng `mvn clean ...`. Đừng commit artifacts dưới `target` hoặc dùng sự tồn tại của report cũ làm bằng chứng rằng invocation hiện tại đã chạy tests.

### 3.1. `scope=test` có nghĩa gì?

JUnit Jupiter là **test library** nên thường được khai báo:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Đây là **một đoạn dưới `<dependencies>`** chứ không phải POM đầy đủ. Scope test cung cấp JUnit API/engine và các phần liên quan cho test compile/test runtime, không tự đưa chúng vào main runtime dependency graph.

Surefire lại là **build plugin**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
</plugin>
```

Đây là đoạn dưới `<build><plugins>`. Hai artifact thuộc **hai vai trò khác nhau**: JUnit định nghĩa tests; Surefire thực thi tests trong Maven. Chỉ thêm JUnit nhưng dùng Surefire quá cũ/không phù hợp có thể dẫn đến `Tests run: 0`; chỉ thêm Surefire mà không có framework/engine cũng không tạo test methods.

## 4. Maven Surefire Plugin tìm test nào?

Default includes của Surefire sử dụng các pattern theo tên test class:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

Ví dụ:

| Tên file | Mặc định được Surefire xem xét? |
| --- | --- |
| `TestCalculator.java` | Có. |
| `CalculatorTest.java` | Có. |
| `CalculatorTests.java` | Có. |
| `CalculatorTestCase.java` | Có. |
| `CalculatorSpec.java` | Không theo các pattern trên. |
| `CalculatorIT.java` | Không theo các pattern trên; hay dùng với Failsafe. |

Surefire **không chạy source file `.java` trực tiếp**; plugin quét test output classes đã biên dịch, ánh xạ theo naming patterns rồi nhờ provider/engine tìm test methods hợp lệ. Một class đúng tên nhưng không có `@Test` cũng có thể không chạy test method nào.

### 4.1. Tùy biến includes và excludes

Đoạn cấu hình trong plugin Surefire:

```xml
<configuration>
    <includes>
        <include>**/*Test.java</include>
        <include>**/*Spec.java</include>
    </includes>
    <excludes>
        <exclude>**/ExperimentalTest.java</exclude>
    </excludes>
</configuration>
```

Nếu chủ động ghi includes, bạn cần **liệt kê tất cả naming patterns còn muốn hỗ trợ**, không mặc định Surefire luôn thêm tất cả patterns mặc định vào sau. Với tests được loại qua excludes hoặc framework tags, việc thiếu coverage thực tế là nguy cơ nên báo cáo minh bạch.

### 4.2. JUnit Jupiter yêu cầu annotation và engine

Với Jupiter, method test thường dùng:

```java
@Test
void calculatesPrice() {
    assertEquals(375, calculator.total(125, 3));
}
```

Đây là **method minh họa bên trong một class test**, không phải chương trình Java độc lập. Import phải đúng `org.junit.jupiter.api.Test` và `org.junit.jupiter.api.Assertions`; TestEngine phải hiện diện trên runtime test classpath. Các phiên bản Surefire khác nhau có quy tắc provider selection khác nhau; dòng Surefire **3.6.x dùng JUnit Platform làm cơ chế chung** cho các framework được hỗ trợ.

### 4.3. Các nested test classes

JUnit Jupiter hỗ trợ `@Nested`, nhưng Surefire class scanner có cơ chế loại trừ một số nested class theo cấu hình mặc định, chẳng hạn pattern liên quan `$`. Nếu nested tests không xuất hiện, cần kiểm tra phiên bản Surefire, engine và excludes thay vì chỉ xem Java annotation.

## 5. Lab chạy được: Java 17, JUnit Jupiter và Surefire

Lab gồm một project Maven đơn với logic tính giá, chương trình Java có `main` và bốn JUnit Jupiter tests. Nó sử dụng:
- JDK 17+.
- Maven 3.x tương thích với Maven Compiler Plugin 3.14.1 và Surefire 3.6.1.
- JUnit Jupiter 5.11.4 qua Maven Central hoặc mirror thích hợp.
- Không cần database, server hoặc credentials.

### 5.1. Cây thư mục

```text
surefire-unit-lab/
├── pom.xml
└── src/
    ├── main/java/dev/training/tests/
    │   ├── PriceCalculator.java
    │   └── App.java
    └── test/java/dev/training/tests/
        └── PriceCalculatorTest.java
```

Linux/macOS:

```bash
mkdir -p surefire-unit-lab/src/main/java/dev/training/tests
mkdir -p surefire-unit-lab/src/test/java/dev/training/tests
cd surefire-unit-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "surefire-unit-lab/src/main/java/dev/training/tests" | Out-Null
New-Item -ItemType Directory -Force -Path "surefire-unit-lab/src/test/java/dev/training/tests" | Out-Null
Set-Location surefire-unit-lab
```

Tạo đúng những file ở các mục sau. Tất cả lệnh Maven/Java tiếp theo giả định bạn đang đứng tại `surefire-unit-lab`. Mỗi code block Java được đánh dấu là **toàn bộ file nguồn** nếu không ghi rõ là snippet.

### 5.2. POM hoàn chỉnh: `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.tests</groupId>
    <artifactId>surefire-unit-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven Compiler Plugin dùng `maven.compiler.release=17`; JUnit Jupiter chỉ tham gia test classpath; Surefire 3.6.1 được ghim version. `failIfNoTests=true` là **chính sách chủ đích của lab** để gây lỗi khi không tìm thấy test nào. Trong multi-module project có parent `pom` hoặc module không có test theo thiết kế, không nên áp đặt flag này lên tất cả modules vô điều kiện.

Không thêm custom execution `surefire:test` ở đây vì packaging jar đã có binding Surefire ở phase test.

### 5.3. File Java chính: `PriceCalculator.java`

```java
package dev.training.tests;

public final class PriceCalculator {

    public int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("price and quantity must be non-negative");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

`Math.multiplyExact` là Java standard API, báo `ArithmeticException` khi phép nhân vượt phạm vi `int`. Kiểm tra số âm khiến input như quantity -1 báo `IllegalArgumentException`.

### 5.4. File `App.java` để chạy Java riêng

```java
package dev.training.tests;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println(new PriceCalculator().total(125, 3));
    }
}
```

`App.main` giúp phân biệt **chạy ứng dụng Java** với **Surefire chạy tests**. Không cần JUnit trên runtime classpath của `App`.

### 5.5. File test: `PriceCalculatorTest.java`

```java
package dev.training.tests;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void multipliesPriceAndQuantity() {
        assertEquals(375, calculator.total(125, 3));
    }

    @Test
    void zeroQuantityProducesZero() {
        assertEquals(0, calculator.total(125, 0));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> calculator.total(125, -1));
    }

    @Test
    void refusesIntegerOverflow() {
        assertThrows(ArithmeticException.class,
            () -> calculator.total(Integer.MAX_VALUE, 2));
    }
}
```

Đây là **bốn JUnit Jupiter test methods**. Class name `PriceCalculatorTest` khớp default `**/*Test.java`. Methods không cần `public` vì Jupiter hỗ trợ package-private test methods. Không có `main` trong test class; Jupiter engine sẽ thực thi qua Surefire provider.

Các tình huống được kiểm tra là phép nhân bình thường, số lượng bằng 0, số lượng âm và tràn số nguyên. Output/exception được kiểm tra bằng assertions; test không cần in ra console để được tính là pass.

### 5.6. Biên dịch và chạy test

```bash
mvn -version
mvn -B -ntp clean test
```

Khi môi trường đáp ứng yêu cầu, Maven đi qua `compile`, `test-compile` và `test`. Surefire tìm `PriceCalculatorTest` và Jupiter engine chạy bốn methods, tất cả pass.

Một dòng tóm tắt **theo nội dung thống kê kỳ vọng** có dạng:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Đây **không phải toàn bộ stdout chính xác**, vì Maven có thể thêm `[INFO]`, tên class, thông tin thời gian, plugin goal headings và các dòng khác.

Điểm cần xác minh trong log:
- Goal `compiler:testCompile` đã được thực hiện.
- Goal `surefire:test` đã thực hiện sau testCompile.
- Bốn tests đã được tính trong thống kê.
- Không có failure/error.
- Kết quả lệnh Maven thành công.

Nếu có `BUILD SUCCESS` nhưng test count bằng 0, không nên kết luận bài thực hành đã kiểm thử đúng; phải kiểm tra test discovery và skip flags.

### 5.7. Chạy Java `main` độc lập

Linux/macOS:

```bash
java -cp target/classes dev.training.tests.App
```

Windows PowerShell:

```powershell
java -cp target\classes dev.training.tests.App
```

**Stdout chính xác của Java application:**

```text
375
```

Lệnh này không gọi JUnit test methods. Nó chạy `App.main()`; chỉ cần `target/classes` do Maven Compiler Plugin tạo. Khi chạy từ thư mục khác, điều chỉnh relative classpath.

### 5.8. Test reports được lưu ở đâu?

Sau lượt Surefire, thư mục mặc định:

```text
target/surefire-reports/
    dev.training.tests.PriceCalculatorTest.txt
    TEST-dev.training.tests.PriceCalculatorTest.xml
```

Tên files là convention thường gặp; cấu hình tùy chọn như `reportNameSuffix` và `reportsDirectory` có thể làm khác. File XML chứa dữ liệu test suite/test case giúp CI có thể tổng hợp; file text hỗ trợ người đọc nhanh.

Linux/macOS:

```bash
ls target/surefire-reports
```

PowerShell:

```powershell
Get-ChildItem -Path target/surefire-reports
```

Một report còn lại từ lần chạy cũ **không chứng minh lượt hiện tại đã thực thi tests**. Dùng `mvn clean test` khi cần kiểm chứng mới và đối chiếu timestamp, test count, log goal thực tế.

## 6. Chạy một test class hoặc một method với -Dtest

Để chọn một class:

```bash
mvn -B -ntp test -Dtest=PriceCalculatorTest
```

Để chọn một method (trên shell có hỗ trợ cú pháp):

```bash
mvn -B -ntp test "-Dtest=PriceCalculatorTest#multipliesPriceAndQuantity"
```

Khi chỉ chọn method này trong lab, kết quả kỳ vọng là một test method được thực thi. Không đồng nghĩa ba methods còn lại đã được kiểm tra. `-Dtest` là test selector của Surefire, không phải Java compiler flag.

Khi muốn lọc pattern:

```bash
mvn -B -ntp test "-Dtest=*CalculatorTest"
```

Dấu nháy giúp tránh một số thao tác glob của shell. Kết quả chính xác còn phụ thuộc tên class, includes/excludes và provider.

### 6.1. Trường hợp -Dtest không khớp

Ví dụ:

```bash
mvn test -Dtest=NonExistingTest
```

Surefire có thể báo lỗi **không tìm thấy test được yêu cầu** theo chính sách `failIfNoSpecifiedTests`. Không thêm `-DfailIfNoSpecifiedTests=false` chỉ để làm CI xanh: nếu selector sai, có thể bạn vừa bỏ qua phần kiểm thử quan trọng.

### 6.2. Lọc bằng JUnit Jupiter tags

Có thể đánh dấu một method:

```java
@Test
@org.junit.jupiter.api.Tag("fast")
void multipliesPriceAndQuantity() {
    assertEquals(375, calculator.total(125, 3));
}
```

Đây là **đoạn thay thế method trong `PriceCalculatorTest.java`**, không phải Java class độc lập. Sau khi thật sự thêm tag, Surefire/JUnit Platform hỗ trợ filters như:

```bash
mvn test -Dgroups=fast
```

Không kết luận tất cả tests đã chạy khi chủ động lọc theo tag. Tham số nhóm/tag cần đối chiếu phiên bản Surefire/JUnit Platform và cấu hình trong POM.

## 7. Tests fail: Surefire ảnh hưởng build thế nào?

Trong `PriceCalculatorTest.java`, tạm thay:

```java
assertEquals(375, calculator.total(125, 3));
```

thành:

```java
assertEquals(376, calculator.total(125, 3));
```

rồi chạy:

```bash
mvn clean test
```

Giá trị thực là 375, nên assertion mong đợi 376 thất bại. Surefire ghi **test failure** vào report; Maven thường hiển thị **BUILD FAILURE** và trả exit code khác 0. Dòng thống kê có thể cho biết một failure trong bốn tests, nhưng stack trace/log tiền tố/timing tùy phiên bản.

**Khôi phục `assertEquals(375, ...)` sau khi thực hành** rồi chạy lại `mvn clean test`. Bài học không yêu cầu duy trì một bài kiểm thử cố ý fail.

### 7.1. Compilation failure và test failure không giống nhau

| Giai đoạn | Ví dụ lỗi | Công cụ chịu trách nhiệm |
| --- | --- | --- |
| `compile` | Source chính sai cú pháp | Maven Compiler Plugin. |
| `test-compile` | Thiếu import JUnit/API không tìm thấy | Maven Compiler Plugin với test classpath. |
| `test` | Assertion sai | JUnit engine qua Surefire. |
| `test` | Provider/engine không load được | Surefire/JUnit Platform/test runtime. |
| `package` | JAR packaging lỗi sau tests qua | Maven JAR Plugin hoặc plugin packaging khác. |

Khi build thất bại, xem **tên goal xuất hiện ngay trước error**, không đoán mọi `BUILD FAILURE` đều từ unit tests.

### 7.2. testFailureIgnore là một rủi ro

Cấu hình:

```xml
<configuration>
    <testFailureIgnore>true</testFailureIgnore>
</configuration>
```

có thể khiến Maven tiếp tục dù Surefire phát hiện tests thất bại. Đây là **cấu hình nguy hiểm nếu dùng làm release gate** mà không có kiểm soát khác. Mặc định thông thường là thất bại build khi tests fail; nên giữ chính sách đó cho CI phát hành.

## 8. -DskipTests và -Dmaven.test.skip=true

Hai tùy chọn không tương đương:

```bash
mvn clean package -DskipTests
```

```bash
mvn clean package -Dmaven.test.skip=true
```

| Tùy chọn | Biên dịch test source | Surefire thực thi tests |
| --- | --- | --- |
| Không truyền flag | Có | Có. |
| `-DskipTests` | **Vẫn biên dịch** test source trong luồng Maven thông thường. | **Bỏ qua** test execution. |
| `-Dmaven.test.skip=true` | **Bỏ qua biên dịch tests** theo Maven Compiler Plugin. | Bỏ qua Surefire/Failsafe tests tương ứng. |

Surefire, Failsafe và Compiler Plugin có hỗ trợ property `maven.test.skip`. Trong project có các plugins tùy chỉnh, đừng giả định một flag sẽ tắt mọi quality checks; chúng có thể có cấu hình khác.

**Nguy cơ:** `mvn package -DskipTests` có thể đóng gói JAR mà chưa kiểm tra nghiệp vụ bằng unit tests. Chỉ sử dụng khi pipeline thật sự có lượt test riêng đã qua và có gate tương ứng.

### 8.1. Xác minh bằng log thay vì tin vào dòng BUILD SUCCESS

Với `-DskipTests`, Maven có thể vẫn chạy `compiler:testCompile` nhưng Surefire bỏ test execution. Với `maven.test.skip=true`, test source compilation thường được Compiler Plugin bỏ qua. Hãy xem goal logs để biết phần nào đã chạy; không lấy một file `target/test-classes` còn lại từ lượt cũ làm bằng chứng.

Khi hoàn tất thực hành:

```bash
mvn -B -ntp clean verify
```

để quay về luồng kiểm thử bình thường.

## 9. Surefire khác Failsafe ở đâu?

**Surefire**: chạy unit tests ở phase `test`, khi test failure thường làm build dừng sớm.

**Failsafe**: dùng cho integration tests ở các phase sau khi package; thường chạy ở `integration-test` và kiểm tra kết quả tại `verify`. Mô hình này cho phép cleanup ở `post-integration-test` có cơ hội chạy trước khi Maven kết luận build thất bại vì integration tests.

```text
test                   surefire:test  (unit tests)
  |
package                đóng gói ứng dụng
  |
pre-integration-test   thiết lập môi trường nếu được bind
  |
integration-test       failsafe:integration-test nếu được bind
  |
post-integration-test  dọn môi trường nếu được bind
  |
verify                 failsafe:verify nếu được bind
```

Nếu dự án có Failsafe, thường nên dùng `mvn verify` thay vì chỉ `mvn integration-test`, vì dừng trước `post-integration-test`/`verify` có thể làm thiếu cleanup và không kiểm tra đầy đủ test results.

### 9.1. Quy ước đặt tên integration tests

Failsafe thường chọn các classes theo pattern:

```text
**/IT*.java
**/*IT.java
**/*ITCase.java
```

Surefire mặc định lại chọn các file kiểu `*Test.java`, `Test*.java`, `*Tests.java` hoặc `*TestCase.java`. Chỉ đổi tên thành `DatabaseIT.java` **không tự chạy Failsafe**: còn cần khai báo plugin/bind goals phù hợp.

Đoạn ví dụ cấu hình Failsafe **nếu dự án có integration tests**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là đoạn trong `<build><plugins>`, **không bắt buộc trong lab unit tests**. Với hệ thống thật còn phải thiết kế startup/shutdown database/server và tách cách thức kiểm thử phù hợp.

## 10. Forked JVM, argLine và parallel tests

Surefire có thể chạy tests trong JVM fork riêng với Maven, tùy cấu hình `forkCount`, `reuseForks`, `argLine`.

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Dfile.encoding=UTF-8</argLine>
    </configuration>
</plugin>
```

Đây là snippet cấu hình tùy chọn, **không cần thêm vào POM lab**. `argLine` ảnh hưởng forked JVM, không tự đổi Maven JVM. Nếu dùng JaCoCo hoặc Java agents, cần ghép `argLine` theo tài liệu plugin vì ghi đè tham số có thể làm mất agent arguments.

**`mvn -T 4`** chủ yếu yêu cầu Maven chạy song song **reactor modules**, không tự làm bốn JUnit methods của một class chạy song song. JUnit Jupiter có cấu hình parallel riêng; cần kiểm thử thread safety của fixtures và shared state trước khi bật.

Cân nhắc:
- Test methods không nên phụ thuộc thứ tự chạy.
- Không giữ mutable static state hoặc một file chung không khóa.
- Dùng temp resources và teardown hợp lý.
- Không dựa vào timezone, OS locale hay network bất định.
- Forking giúp phân tách một số side effects nhưng tăng chi phí khởi tạo JVM.

## 11. System properties, tài nguyên test và secrets

Surefire hỗ trợ cấu hình system properties cho JVM test:

```xml
<configuration>
    <systemPropertyVariables>
        <app.testMode>true</app.testMode>
        <app.region>local</app.region>
    </systemPropertyVariables>
</configuration>
```

Đây là một phần trong Surefire plugin configuration. Test Java có thể đọc:

```java
String region = System.getProperty("app.region", "unknown");
```

Đây là một dòng Java minh họa, không phải file Java độc lập.

**Không đưa credentials thật vào POM hoặc dòng lệnh `-Dpassword=...` rồi chia sẻ logs**. Logs, Surefire reports (nhất là `system-out`), stack traces và output của `mvn -X` có thể chứa đường dẫn, tokens, tên hệ thống hoặc dữ liệu nhạy cảm. Với project nội bộ, sử dụng secret manager/CI mechanisms được phê duyệt, cấp quyền tối thiểu và kiểm duyệt log trước khi chia sẻ.

## 12. Surefire không tự làm coverage

Một test pass chỉ chứng minh assertions trong test đã được thực thi thành công, không có nghĩa code coverage 100%.

| Công cụ | Nhiệm vụ |
| --- | --- |
| Maven Compiler Plugin | Biên dịch main/test sources. |
| JUnit Jupiter | Cung cấp annotations, assertions và engine. |
| Maven Surefire Plugin | Phát hiện/chạy unit tests, ghi reports. |
| JaCoCo Maven Plugin | Coverage instrumentation và report khi cấu hình. |
| Maven Failsafe Plugin | Integration test execution/verification. |
| Maven Surefire Report Plugin | Trình bày dữ liệu reports theo định dạng riêng. |

Ví dụ bốn tests của lab có thể pass nhưng chưa kiểm thử mọi điều kiện nghiệp vụ khi phần mềm phát triển thêm. Coverage cũng không chứng minh thiếu bug; cần assertions có ý nghĩa, integration tests và các checks khác tùy sản phẩm.

## 13. Surefire với JPMS Java 9+

Với project có `module-info.java` và JDK 9+, Surefire hỗ trợ module-path-related execution thông qua `useModulePath` và cơ chế tương thích với JUnit/test runtime.

```xml
<configuration>
    <useModulePath>true</useModulePath>
</configuration>
```

Đây là snippet Surefire, không nên thêm vô điều kiện nếu chưa biết project dùng JPMS. Có thể gặp:
- Test code không đọc được named module.
- Framework reflection bị `InaccessibleObjectException`.
- Test package không được `opens`/`exports` phù hợp.
- Provider/JUnit engine không được quan sát trên module path.

Không mặc định tắt JPMS bằng `useModulePath=false` để “chữa” lỗi mà chưa hiểu việc đổi classpath/module-path làm thay đổi semantics. Đối chiếu tài liệu **Surefire – Java Modularity (JPMS) in Tests**, module descriptors và JDK version.

Lab chính không có `module-info.java` để giữ trọng tâm ở **quan hệ phase test và Surefire**.

## 14. Khi dùng Maven reactor nhiều module

Với aggregator:

```text
project/
├── pom.xml             (packaging=pom)
├── core/
│   ├── pom.xml         (packaging=jar)
│   └── src/test/java/...
└── api/
    ├── pom.xml         (packaging=jar)
    └── src/test/java/...
```

Chạy `mvn test` ở root khiến reactor xử lý các modules liên quan và Surefire chạy ở những project có binding/tests thích hợp. Mỗi module thường có report directory riêng:

```text
core/target/surefire-reports/
api/target/surefire-reports/
```

CI có thể thu thập:

```text
**/target/surefire-reports/TEST-*.xml
```

Đây là **glob pattern**, không phải shell command. Nếu CI chỉ đọc report root, nó có thể bỏ sót kết quả từ child modules.

Để chạy subset Maven modules:

```bash
mvn -pl :api -am test
```

`-pl` chọn module, `-am` yêu cầu upstream reactor projects. Cần lưu ý phase hiện tại có đủ artifacts cho downstream dependency resolution hay không; đôi khi phải build/install ở phase khác hoặc cấu hình module/project phù hợp.

**Cảnh báo `failIfNoTests=true`:** module `pom` hoặc một module chỉ chứa cấu hình có thể không có tests theo thiết kế. Nên đặt cờ này ở modules cần policy đó thay vì thừa kế gây lỗi toàn reactor.

## 15. Chẩn đoán “Tests run: 0”

Khi `mvn test` báo thành công nhưng không chạy test, lần lượt kiểm tra:

1. **File test nằm đúng chỗ?** `src/test/java` thay vì `src/main/java`?
2. **Tên class khớp Surefire includes?** `PriceCalculatorTest`, `TestPriceCalculator`...?
3. **Test class đã được biên dịch?** Xem log `compiler:testCompile` và `target/test-classes`.
4. **Import đúng framework?** `org.junit.jupiter.api.Test` hay import nhầm annotation?
5. **Có JUnit TestEngine thích hợp?** Kiểm tra `junit-jupiter` trong test scope.
6. **Surefire version tương thích?** Dòng cũ có thể không chạy Jupiter đúng mặc định.
7. **Có skip/filter?** `skipTests`, `maven.test.skip`, `-Dtest`, `groups`, `excludes` hoặc `@Disabled`?
8. **Có đúng module/POM?** Với multi-module, root `packaging=pom` có thể không có tests.
9. **JPMS/fork/engine config đúng?** Nếu dùng module-info hoặc custom classpath.
10. **Report có thuộc lượt build mới?** Dùng `clean test` để loại dữ liệu cũ.

Không sửa bằng cách thêm nhiều dependency/framework ngẫu nhiên. Ghi nhận test count thật và tìm nguyên nhân chính xác trước khi cho phép CI tiếp tục.

## 16. Các lỗi khác và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` | Test compile không thấy JUnit API. | Kiểm tra test dependency scope/GAV và repository. |
| `No tests matching pattern` | `-Dtest` sai tên. | Xem class/method, package, compiled tests. |
| `BUILD FAILURE` ở `test-compile` | Test source không compile. | Sửa Java code/test dependencies, không sửa assertion đơn thuần. |
| Surefire report có failures | Assertion mismatch. | Đọc report class/method và root cause. |
| Forked JVM exited unexpectedly | JVM crash, `System.exit`, OOM, native library, agent... | Đọc dump, fork logs, JVM args; không suy luận duy nhất do plugin. |
| Test pass local, fail CI | JDK/locale/filesystem/timezone/network khác. | Pin môi trường và loại dependencies ngoài không cần thiết. |
| Tests chạy hai lần | Custom execution trùng mặc định. | Kiểm tra POM/effective executions. |
| Test class `OrderIT` không chạy `mvn test` | Không khớp Surefire includes. | Dùng Failsafe cho IT và bind phù hợp. |
| Report thiếu khi tests không chạy | `skipTests`, filters, config report hoặc failed fork. | Xem log goal, output thực và reportsDirectory. |
| Plugin resolution fail | Surefire artifact/dependencies không tải được. | Kiểm tra plugin repository/mirror, credentials và Maven/JDK compatibility. |
| `mvn surefire:test` không phản ánh test mới | Chưa compile test source mới. | Chạy `mvn test` hoặc `mvn clean test`. |

### 16.1. Vì sao lỗi compilation không phải lỗi Surefire?

JUnit API import chỉ được compiler kiểm tra ở `test-compile`. Nếu thiếu dependency JUnit, Maven có thể dừng trước `surefire:test`. Phải sửa `<dependencies>` hoặc version/scope, không cố set `testFailureIgnore=true`.

### 16.2. Vì sao báo cáo Surefire XML quan trọng?

Dòng console có thể bị rút ngắn trên CI; XML reports giúp biết từng test case, failure/skip, thời gian và các thuộc tính tương ứng. Nếu report có nội dung nhạy cảm từ stdout/stack trace, phải bảo vệ quyền đọc báo cáo thay vì chỉ che console.

### 16.3. Vì sao `mvn -DskipTests package` không phải “QA PASS”?

Vì đã yêu cầu bỏ qua test execution. Build có thể thành công mà không có kiểm chứng từ JUnit assertions. QA thực tế phải xem pipeline có lượt test riêng đã chạy và kết quả còn hợp lệ với commit/artifact được phát hành hay không.

## 17. Checklist CI cho unit tests bằng Surefire

- [ ] Ghim Maven/JDK versions hoặc dùng Maven Wrapper/Toolchains.
- [ ] Ghim Maven Compiler Plugin và Surefire Plugin versions.
- [ ] Test framework/engine có mặt trong `scope=test`.
- [ ] Test code có đúng source root, package, class name và `@Test`.
- [ ] Dùng `mvn -B -ntp clean test` hoặc `clean verify` ở job phù hợp.
- [ ] Xác nhận Surefire goal đã thực thi, test count đạt kỳ vọng.
- [ ] Không bật skip/ignore-failure cho release gate mà không có phương án kiểm thử bù.
- [ ] Thu thập XML reports của mọi Maven module.
- [ ] Giữ log/reports không lộ credentials.
- [ ] Tests có dữ liệu deterministic và cleanup đúng.
- [ ] Tách integration tests và setup/teardown sang Failsafe.
- [ ] Theo dõi lỗi flaky giữa developer/CI, không chỉ rerun cho xanh.
- [ ] Kiểm tra coverage riêng nếu cần chính sách coverage.
- [ ] Không dùng test report còn lại từ build khác để chứng minh job hiện tại thành công.

## 18. Câu hỏi ôn tập và đáp án

**Câu 1.** Trong `mvn test`, `test` là gì?

**Đáp án:** Là **default lifecycle phase**. Với packaging jar tiêu chuẩn, nó có goal `surefire:test` được bind vào.

**Câu 2.** Maven Compiler Plugin và Surefire khác nhau ra sao?

**Đáp án:** Compiler Plugin biên dịch main/test source. Surefire chạy test classes qua framework engine sau khi biên dịch.

**Câu 3.** `mvn test-compile` có tự thực thi JUnit tests không?

**Đáp án:** Không. Nó chỉ biên dịch test source, chưa đi đến phase `test`.

**Câu 4.** Vì sao `mvn surefire:test` có thể chạy test cũ?

**Đáp án:** Đó là gọi goal trực tiếp; không tự chạy `compiler:testCompile` trên source mới.

**Câu 5.** Dự án lab có mấy JUnit Jupiter test methods?

**Đáp án:** **4**, kiểm tra phép nhân thường, quantity 0, quantity âm và overflow.

**Câu 6.** Stdout của lệnh `java -cp target/classes dev.training.tests.App` là gì?

**Đáp án:** `375`. Đây là stdout ứng dụng, **không phải thống kê Surefire**.

**Câu 7.** Class `PriceCalculatorSpec` có được Surefire mặc định chọn không?

**Đáp án:** Không theo default patterns nêu trong bài; cần cấu hình includes hoặc đổi tên.

**Câu 8.** `mvn package` có chạy tests không?

**Đáp án:** Có, với project jar/binding mặc định không skip, vì `package` đi qua `test` trước.

**Câu 9.** Phân biệt `-DskipTests` và `-Dmaven.test.skip=true`.

**Đáp án:** `skipTests` thường bỏ chạy tests nhưng vẫn compile test source; `maven.test.skip=true` yêu cầu cả Compiler/Surefire bỏ test compilation/execution.

**Câu 10.** Chỉ chạy một method trong lab bằng lệnh nào?

**Đáp án:** `mvn test "-Dtest=PriceCalculatorTest#multipliesPriceAndQuantity"`.

**Câu 11.** Vì sao Surefire report không phải coverage report?

**Đáp án:** Surefire ghi test results; coverage instrumentation/reporting cần công cụ khác như JaCoCo.

**Câu 12.** Vì sao không nên dừng pipeline ở `mvn integration-test` khi có Failsafe?

**Đáp án:** Có thể bỏ phase teardown/verify cần thiết; thường dùng `mvn verify`.

**Câu 13.** `mvn -T 4` có nghĩa bốn unit tests chạy song song không?

**Đáp án:** Không. `-T` điều khiển Maven reactor parallelism, JUnit test parallelism có cơ chế riêng.

**Câu 14.** Test class tên đúng nhưng `Tests run: 0`. Kiểm tra gì?

**Đáp án:** Test compile output, `@Test`, JUnit engine, Surefire includes, skip/filter flags và Maven module đang chạy.

**Câu 15.** Điều gì xảy ra nếu cố sửa assertion thành `assertEquals(376, 375)`?

**Đáp án:** Jupiter báo assertion failure; Surefire ghi failure và Maven thường kết thúc build với exit code khác 0.

**Câu 16.** Có nên bật `failIfNoTests=true` trên mọi module `pom` không?

**Đáp án:** Không. Aggregator chỉ chứa cấu hình có thể không có tests theo thiết kế; áp policy theo module phù hợp.

## 19. Tài liệu tham khảo chính thức

- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): liên hệ phase `test` và goal `surefire:test` theo packaging.
- [Apache Maven Surefire Plugin – Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/): tổng quan test execution/reports.
- [Apache Maven Surefire Plugin – `surefire:test` goal](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html): parameters `test`, `skipTests`, `failIfNoTests`, `forkCount` và `argLine`.
- [Apache Maven Surefire Plugin – JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): JUnit Jupiter/TestEngine/provider trong Surefire 3.6.x.
- [Apache Maven Surefire Plugin – Inclusion/Exclusion](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html): default class naming patterns.
- [Apache Maven Surefire Plugin – Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html): hai cơ chế skip.
- [Apache Maven Surefire Plugin – Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html): `-Dtest` chọn test class/method.
- [Apache Maven Failsafe Plugin – Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration tests và verify/cleanup phases.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter API, TestEngine, assertions và Maven integration.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): main/test compilation và `--release`.
