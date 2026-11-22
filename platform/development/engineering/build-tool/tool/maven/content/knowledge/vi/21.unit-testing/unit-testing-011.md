# Maven: Phân biệt `skipTests` với `maven.test.skip`

> **Build Tool Maven · Kiểm thử đơn vị**  
> Phạm vi: Maven 3.x, Java 17, Maven Compiler Plugin 3.14.1, Maven Surefire Plugin 3.6.1 và JUnit Jupiter 5.11.4. Với integration tests, bài giải thích thêm thay đổi quan trọng của Maven Failsafe từ phiên bản 3.6.0.

## 1. Hai cờ gần giống nhau nhưng phạm vi rất khác

Hãy so sánh:

```bash
mvn clean package -DskipTests=true
mvn clean package -Dmaven.test.skip=true
```

**`-DskipTests=true`** yêu cầu **Maven Surefire Plugin không thực thi unit tests**, nhưng **Maven Compiler Plugin vẫn biên dịch mã test**. Nếu `src/test/java` có syntax error, type mismatch hoặc import thư viện không tồn tại trên test compile classpath, build vẫn có thể lỗi trước lúc tới phase `package`.

**`-Dmaven.test.skip=true`** yêu cầu **Maven Compiler Plugin bỏ test compilation** và **Surefire không chạy tests**. Đây là lựa chọn rộng hơn: build có thể thành công **dù mã Java trong test sources không biên dịch được**, bởi vì mã ấy chưa được compiler đọc trong invocation đó.

Một cách nhớ ngắn:

```text
skipTests=true
    -> compile main: YES
    -> compile tests: YES
    -> execute unit tests (Surefire): NO

maven.test.skip=true
    -> compile main: YES
    -> compile tests (Compiler Plugin): NO
    -> execute unit tests (Surefire): NO
```

**Hai cờ này không xóa các Maven lifecycle phases.** Chúng làm những plugin có hỗ trợ property thay đổi hành vi. Những plugin khác bind vào cùng phase vẫn có thể chạy; việc skip test không đồng nghĩa bỏ cả `generate-test-sources`, `process-test-resources`, `package`, `verify` hoặc mọi bước static analysis.

### 1.1. Bảng đối chiếu trực tiếp

| Nội dung | Không skip | `-DskipTests=true` | `-Dmaven.test.skip=true` |
| --- | --- | --- | --- |
| Compile `src/main/java` | Có | Có | Có |
| Compile `src/test/java` | Có | **Có** | **Không** |
| Chạy JUnit unit tests qua Surefire | Có nếu tests được phát hiện | **Không** | **Không** |
| Phát hiện lỗi cú pháp trong test Java | Có | **Có** | **Không** nếu compiler thật sự skip |
| Phát hiện test assertion thất bại | Có khi tests chạy | Không | Không |
| Tạo main JAR ở `package` | Có nếu các bước trước PASS | Có nếu các bước trước PASS | Có nếu các bước trước PASS |
| Tạo Surefire reports từ test execution hiện tại | Có | Không có báo cáo test mới | Không có báo cáo test mới |
| Có thể nói “unit tests đã PASS”? | Chỉ nếu tests thực sự chạy và PASS | **Không** | **Không** |
| Bỏ qua toàn bộ các phases liên quan test | Không | Không | Không |
| Mặc định tác động tới Failsafe 3.6.1 | IT chạy nếu đã bind | **Không tự skip IT** | Failsafe hỗ trợ broad skip |

**Điều kiện:** bảng áp dụng cho Maven Compiler/Surefire/Failsafe thông dụng khi không có `<configuration>`, profile hoặc plugin khác cố tình ghi đè tham số. Nếu project nhiều modules có cấu hình riêng, cần kiểm chứng từng module thay vì suy ra từ một dòng lệnh.

### 1.2. Cú pháp CLI chính xác

Các cách viết sau đều biểu thị user property Boolean true trong Maven thông thường:

```bash
mvn package -DskipTests
mvn package -DskipTests=true
```

Với property còn lại:

```bash
mvn package -Dmaven.test.skip=true
```

Không viết nhầm `maven.test.skipTests`, `skipTest`, `skip.tests` hoặc cho rằng `skipTests` và `maven.test.skip` là alias. Đây là **hai property khác nhau**:

```text
skipTests
maven.test.skip
```

`-DskipTests=false` có thể dùng để bật lại Surefire test execution khi POM sử dụng đúng user property đó và **không** có cấu hình khác bật `maven.test.skip=true`.

## 2. Vì sao hành vi khác nhau? Đọc lifecycle

Đối với Java project có `<packaging>jar</packaging>`, chuỗi `default` lifecycle đơn giản hóa:

```text
validate
    |
generate-sources
    |
compile                     -> compiler:compile
    |
generate-test-sources
    |
test-compile                -> compiler:testCompile
    |
test                        -> surefire:test
    |
package                     -> jar:jar
    |
verify
    |
install
    |
deploy
```

Sơ đồ này **lược bỏ** một số phases như `process-resources`, `process-test-resources`, `prepare-package`, `integration-test` để tập trung vào phân biệt compile và execute. Maven vẫn thực thi tất cả phases liên quan trong lifecycle theo thứ tự thực tế.

- **`compile`**: compiler chuyển mã chính thành `.class` ở `target/classes`.
- **`test-compile`**: compiler chuyển mã Java test thành `.class` ở `target/test-classes`.
- **`test`**: Surefire tìm test classes có framework/provider phù hợp, rồi **thực thi** tests.
- **`package`**: JAR plugin đóng gói main classes thành artifact. Unit test classes thường **không** nằm trong main JAR.

Khi chạy:

```bash
mvn clean package
```

Maven đi qua cả các bước biên dịch main/test, thực thi test rồi package. Khi thêm `-DskipTests`, `compiler:testCompile` **vẫn được gọi**. Khi thêm `-Dmaven.test.skip`, Compiler Plugin nhận skip flag ở testCompile, nên không biên dịch test sources.

### 2.1. Một test class có hai trạng thái độc lập

Giả sử có:

```text
src/test/java/org/example/CalculatorTest.java
```

Khi biên dịch thành công, thường có:

```text
target/test-classes/org/example/CalculatorTest.class
```

Tuy nhiên `.class` tồn tại **không có nghĩa test đã chạy**. Surefire có thể không execute test vì `skipTests=true`, vì không discover đúng framework, hoặc vì test bị filter/exclude. Ngược lại, không có `.class` sau một `mvn clean package -Dmaven.test.skip=true` không chứng minh test source sai; đơn giản nó **chưa được compile**.

Nên kiểm chứng cả:

1. `compiler:testCompile` thực sự làm gì?
2. `surefire:test` có thực thi tests nào không?
3. `target/test-classes/...` có class của lần build hiện tại không?
4. `target/surefire-reports/...` có report mới cho lần build đó không?

### 2.2. `mvn compile` không phải lệnh tốt để kiểm chứng skipTests

Nếu chỉ chạy:

```bash
mvn compile -DskipTests=true
```

lifecycle dừng trước `test-compile` và `test`, nên Surefire **không có cơ hội chạy**. Không thể suy ra `-DskipTests` đúng hay sai chỉ vì không thấy thông báo skip trong lệnh này.

Để so sánh nên chạy đến `test`, `package` hoặc `verify`, tốt nhất có `clean`:

```bash
mvn clean test -DskipTests=true
mvn clean test -Dmaven.test.skip=true
```

`clean` giúp xóa compiled classes và reports cũ, tránh nhìn nhầm output của invocation trước.

## 3. Plugin nào đọc property nào?

### 3.1. Maven Surefire Plugin

Trong bản **3.6.1**, goal `surefire:test` có những parameter quan trọng:

| Parameter | User property | Chức năng |
| --- | --- | --- |
| `skipTests` | `skipTests` | Không chạy tests, **test sources vẫn compile** |
| `skip` | `maven.test.skip` | Không chạy Surefire tests |
| `test` | `test` | Chọn tests qua pattern, ví dụ `CalculatorTest` |
| `failIfNoTests` | `failIfNoTests` | Có thể fail khi không có tests phù hợp |
| `testFailureIgnore` | `maven.test.failure.ignore` | Cho phép bỏ qua tác động của test failure; **khác skip** |

Surefire không trực tiếp là compiler. Chính Maven Compiler Plugin hoặc công cụ test compiler phù hợp sinh test `.class` trước khi Surefire đọc chúng.

**Chú ý về `skip` và `skipTests` trong Surefire:** hai parameter này đều giúp không thực thi tests ở mức runner, nhưng tên user property khác nhau. `maven.test.skip` còn ảnh hưởng Compiler Plugin, là điểm phân biệt cốt lõi.

### 3.2. Maven Compiler Plugin

Goal:

```text
org.apache.maven.plugins:maven-compiler-plugin:3.14.1:testCompile
```

có parameter `<skip>` với:

```text
User Property: maven.test.skip
```

Bật `-Dmaven.test.skip=true` khiến Compiler Plugin bỏ biên dịch test sources. Compiler Plugin **không** coi `skipTests` là một lệnh tương đương cho testCompile. Vì vậy `-DskipTests` không che lỗi Java compiler trong `src/test/java`.

Maven Compiler Plugin thường chạy qua default lifecycle của JAR project. Nếu dự án dùng Kotlin/Scala/Groovy test compiler hoặc code generation plugins khác, mỗi plugin có tham số skip riêng; không bảo đảm `maven.test.skip` được tất cả tools bên ngoài hiểu.

### 3.3. Maven Failsafe Plugin (integration tests)

Failsafe là plugin phổ biến để chạy integration tests trong các phases `integration-test` và `verify` khi được bind đúng. Đối với **Failsafe 3.6.0 trở lên**:

- CLI `-DskipTests=true` **không còn tự skip Failsafe integration tests**. Nó là user property của Surefire.
- Để skip integration tests, dùng `-DskipITs=true`.
- `-Dmaven.test.skip=true` vẫn được Failsafe hỗ trợ cho broad skip, đồng thời compiler bỏ biên dịch test sources.
- Trong Failsafe vẫn có parameter `<skipTests>` được hỗ trợ khi cấu hình **tường minh**, nhưng nó **deprecated** và không còn bind tới user property `skipTests` như trước.

Một số bài viết cũ cho Failsafe 2.x nói `-DskipTests` bỏ cả unit và integration tests. Đó không còn là kết luận đúng cho dự án dùng Failsafe 3.6.1. Khi làm với dự án legacy, phải đọc **version chính xác** trong effective POM và tài liệu của phiên bản ấy.

## 4. Project Java 17 + JUnit 5 đầy đủ để thực hành

Xây một project `maven-test-skip-demo` với một hàm tính tổng và một JUnit Jupiter test. Đây là dự án **runnable độc lập**, không cần database, HTTP server hoặc môi trường cloud.

### 4.1. Cấu trúc thư mục

```text
maven-test-skip-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── org/
    │           └── example/
    │               ├── Calculator.java
    │               └── Main.java
    └── test/
        └── java/
            └── org/
                └── example/
                    └── CalculatorTest.java
```

Đảm bảo JDK 17+, Maven 3.x và truy cập được repository để tải Compiler Plugin, Surefire Plugin và JUnit.

### 4.2. `pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>maven-test-skip-demo</artifactId>
    <version>1.0.0</version>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ý nghĩa:

- Version Compiler Plugin và Surefire được ghim để tránh thay đổi theo môi trường Maven.
- JUnit Jupiter `5.11.4` ở scope `test`: không cần đưa JUnit API vào runtime classpath của chương trình chính.
- `maven.compiler.release=17` đặt Java compile target.
- Không cấu hình skip mặc định trong POM, để phép thử CLI **chủ động** bật từng lựa chọn.
- Surefire 3.6.1 hỗ trợ JUnit Jupiter/JUnit Platform và sẽ tìm test theo default includes; `CalculatorTest` là tên đúng convention.

### 4.3. `src/main/java/org/example/Calculator.java`

```java
package org.example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
```

Class ứng dụng không phụ thuộc vào JUnit.

### 4.4. `src/main/java/org/example/Main.java`

```java
package org.example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + Calculator.add(2, 3));
    }
}
```

Vì main code chỉ dùng các class trong `target/classes`, có thể chạy bằng Java CLI mà không cần thêm thư viện bên ngoài:

```bash
java -cp target/classes org.example.Main
```

**Stdout chính xác** sau compile:

```text
2 + 3 = 5
```

### 4.5. `src/test/java/org/example/CalculatorTest.java`

```java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {

    @Test
    void addReturnsSum() {
        assertEquals(5, Calculator.add(2, 3));
    }
}
```

JUnit Jupiter cho phép test class và test method package-private như mẫu. Test này không in dòng `"2 + 3 = 5"`; nó chỉ kiểm tra assertion. Khi Surefire chạy một test thành công, bạn sẽ thấy test summary trong Maven logs và report dưới `target/surefire-reports`.

## 5. Thử nghiệm A — không skip gì

Tại thư mục `maven-test-skip-demo/`:

```bash
java -version
javac -version
mvn -version
mvn clean package
```

Các hành vi dự kiến:

1. Compiler Plugin biên dịch `Calculator.java` và `Main.java`.
2. Compiler Plugin biên dịch `CalculatorTest.java`.
3. Surefire thực thi `addReturnsSum()`.
4. Assertion `5 == 5` thành công.
5. Maven JAR Plugin đóng gói main classes.

Surefire có thể in dòng tóm tắt:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **dòng trọng tâm dự kiến**, không phải toàn bộ log theo mọi phiên bản. File quan trọng:

```text
target/classes/org/example/Calculator.class
target/classes/org/example/Main.class
target/test-classes/org/example/CalculatorTest.class
target/surefire-reports/TEST-org.example.CalculatorTest.xml
target/maven-test-skip-demo-1.0.0.jar
```

Có thể còn file `org.example.CalculatorTest.txt` trong thư mục reports. Tên main JAR theo tọa độ POM; JAR mẫu chưa có manifest `Main-Class`, vì thế không giả định `java -jar` sẽ chạy được. Lệnh `java -cp target/classes org.example.Main` là cách đơn giản và đáng tin.

### 5.1. Dấu hiệu test thực sự chạy

**Đừng chỉ nhìn `BUILD SUCCESS`**. Để nói unit test đã chạy, cần xem `surefire:test` logs, test count và report của build **hiện tại**. Trong project multi-module, kiểm tra reports **theo module**, vì một module có thể có 0 tests hoặc cấu hình skip riêng.

Nếu một lần chạy không có report do tests không được discover, `BUILD SUCCESS` không tự chứng minh có test suite.

## 6. Thử nghiệm B — chỉ `skipTests`

Chạy:

```bash
mvn clean package -DskipTests=true
```

Kỳ vọng:

```text
compiler:compile       -> CHẠY
compiler:testCompile   -> CHẠY
surefire:test          -> SKIP thực thi
jar:jar                -> CHẠY nếu phần khác hợp lệ
```

Các file có thể quan sát sau `clean package`:

```text
target/classes/org/example/Calculator.class
target/classes/org/example/Main.class
target/test-classes/org/example/CalculatorTest.class
target/maven-test-skip-demo-1.0.0.jar
```

**Class `CalculatorTest.class` vẫn được tạo.** Đó là bằng chứng chính của `-DskipTests`: tests bị bỏ chạy nhưng test Java **vẫn phải compile**.

Để xác minh bằng JDK tool:

```bash
javap -classpath target/test-classes org.example.CalculatorTest
```

Nếu class được biên dịch, `javap` tìm thấy và hiển thị chữ ký class. Nó không thực thi JUnit test. Có thể thấy Surefire log như:

```text
[INFO] Tests are skipped.
```

Không dựa vào câu log chính xác từng dấu; hãy xem plugin execution và `.class`. Sau `clean`, Surefire **không tạo test execution report mới** cho `CalculatorTest`.

### 6.1. Lợi ích của chế độ này

- Tiết kiệm thời gian **chạy** test suite.
- Vẫn bắt được lỗi compiler trong `src/test/java`.
- Có thể thích hợp tạo artifact tạm để kiểm tra classpath, packaging hoặc cấu hình không liên quan tới behavior tests.

### 6.2. Hạn chế nghiêm trọng

- Không chạy assertion, không phát hiện regression từ tests.
- Không tạo dữ liệu coverage mới do unit tests thực thi.
- Không chạy test fixtures/initialization có tác dụng kiểm tra hệ thống.
- Test compilation có thể vẫn tốn thời gian đáng kể nếu dự án có rất nhiều test classes/annotation processors.
- Maven vẫn có thể phải resolve JUnit/Mockito/test compile dependencies vì test compiler vẫn cần chúng.

**Không đánh dấu “tests passed”** chỉ vì lệnh với `skipTests` trả exit code 0.

## 7. Thử nghiệm C — `maven.test.skip`

Chạy từ trạng thái sạch:

```bash
mvn clean package -Dmaven.test.skip=true
```

Kỳ vọng:

```text
compiler:compile       -> CHẠY
compiler:testCompile   -> SKIP biên dịch test sources
surefire:test          -> SKIP
jar:jar                -> CHẠY nếu build còn lại hợp lệ
```

Files mong đợi:

```text
target/classes/org/example/Calculator.class
target/classes/org/example/Main.class
target/maven-test-skip-demo-1.0.0.jar
```

**Không có** test `.class` do compiler mới tạo:

```text
target/test-classes/org/example/CalculatorTest.class
```

Đây là dấu hiệu phân biệt quyết định. Trong project thực, một plugin khác có thể tạo thư mục `target/test-classes` hoặc copy files vào đó; đừng chỉ dựa trên **sự tồn tại của thư mục**. Hãy kiểm tra chính test class cần biên dịch và log `compiler:testCompile`.

Maven vẫn có thể chạy các goals khác gắn vào những phases liên quan test (ví dụ generator/test resources) **nếu các goals đó không tự skip**. `maven.test.skip` không phải nút “bỏ mọi thứ có chữ test”.

### 7.1. Khi nào có thể dùng?

Chỉ trong nhu cầu có chủ đích như đóng gói artifact tạm khi không cần kiểm tra test Java source, và phải có một job khác **bắt buộc** compile/run tests trước merge/release. Đây là lựa chọn nhanh nhưng **mất nhiều tín hiệu chất lượng hơn `skipTests`**.

Không lưu `maven.test.skip=true` trong parent POM hoặc `.mvn/maven.config` của mọi build nếu tiêu chí nhóm là CI luôn kiểm tra tests.

## 8. Thí nghiệm cố tình làm test compile lỗi

Thí nghiệm này cho thấy khác biệt **ngay cả khi không chạy một test assertion nào**.

**Chỉ trong project demo hoặc branch riêng**, tạo tạm:

`src/test/java/org/example/BrokenTest.java`

```java
package org.example;

final class BrokenTest {
    void broken() {
        int number = "wrong type";
        System.out.println(number);
    }
}
```

Đây là **mã Java cố ý sai**: `String` không gán được cho biến `int`. Không phải nội dung production và không được để lại sau thí nghiệm.

### 8.1. Chạy với skipTests

```bash
mvn clean package -DskipTests=true
```

**Kết quả kỳ vọng: build FAIL ở `compiler:testCompile`.** Java compiler thấy `BrokenTest.java` và báo lỗi tương tự:

```text
incompatible types: java.lang.String cannot be converted to int
```

Đây là **mẫu thông điệp lỗi**, không phải log đầy đủ cố định. Vì test compilation thất bại ở phase trước package, Maven không hoàn tất packaging cho invocation đó.

**Kết luận:** `skipTests` không che compile error trong test code.

### 8.2. Chạy với maven.test.skip

```bash
mvn clean package -Dmaven.test.skip=true
```

**Kết quả kỳ vọng: main code vẫn compile và JAR được package**, nếu không có lỗi khác, vì test compilation đã bị skip. Nhưng `BrokenTest.java` vẫn sai; bạn **chưa sửa lỗi**, chỉ bỏ qua bước có thể phát hiện nó.

**Kết luận:** `maven.test.skip` che cả lỗi compilation của tests và lỗi assertion/runtime tests.

### 8.3. Khôi phục

Xóa **chỉ file `BrokenTest.java` tạo cho thí nghiệm**, rồi:

```bash
mvn clean verify
```

Kỳ vọng dự án gốc lại biên dịch test sources và Surefire chạy `CalculatorTest` thành công. Không kết thúc bài tập với source sai hoặc trạng thái skip đang được lưu trong POM.

## 9. Quan trọng khi dùng Failsafe 3.6.1: Unit test và integration test không còn dùng chung skipTests CLI

Đây là sự khác biệt theo version đặc biệt quan trọng trong các build mới.

**Surefire** thông thường chạy unit tests trong phase `test`.

**Failsafe** thường chạy integration tests tại `integration-test` và `verify` nếu bạn khai báo plugin executions. Tên tests mặc định có thể có dạng `*IT.java`, `IT*.java`, `*ITCase.java`; cần có test framework/engine phù hợp.

### 9.1. Hành vi theo phiên bản

Từ **Failsafe 3.6.0**, plugin không còn liên kết `<skipTests>` của Failsafe với Maven user property `skipTests`. Vì thế:

```bash
mvn verify -DskipTests=true
```

**bỏ unit tests chạy bằng Surefire**, nhưng **integration tests của Failsafe 3.6.1 vẫn có thể chạy** nếu đã được bind và không có tham số skip khác.

Muốn skip ITs:

```bash
mvn verify -DskipITs=true
```

Muốn skip cả unit và integration test executions nhưng **vẫn compile test sources**:

```bash
mvn verify -DskipTests=true -DskipITs=true
```

Muốn broad skip cả test compilation và test execution được các plugin hỗ trợ:

```bash
mvn verify -Dmaven.test.skip=true
```

**Failsafe trước 3.6.0 có thể có semantics khác:** trước đây CLI `skipTests` được chia sẻ với Failsafe và Surefire. Nếu project có bản cũ, đừng suy theo bảng của 3.6.1; đọc tài liệu đúng version/plugin descriptor.

### 9.2. Bảng lựa chọn khi cả hai plugin đều chạy

Giả sử Surefire **3.6.1**, Failsafe **3.6.1**, có test source hợp lệ và Failsafe được bind:

| Lệnh Maven tới `verify` | Surefire UT | Failsafe IT | Test source compilation |
| --- | --- | --- | --- |
| Không có skip | Chạy | Chạy | Có |
| `-DskipTests=true` | Skip | Chạy | Có |
| `-DskipITs=true` | Chạy | Skip | Có |
| `-DskipTests=true -DskipITs=true` | Skip | Skip | Có |
| `-Dmaven.test.skip=true` | Skip | Skip | **Không** |

Bảng nói về **skip semantics**, không bảo đảm project thực tế có ITs: Failsafe phải được cấu hình/bind. Chỉ đặt version Failsafe trong `<pluginManagement>` không tự khiến nó chạy tests.

### 9.3. Failsafe plugin configuration minh họa

Đây là **fragment POM bổ sung**, **không cần cho demo unit test ở mục 4**:

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

Thêm fragment vào `<build><plugins>` nếu project thực sự có integration tests và cơ chế chuẩn bị/kết thúc môi trường phù hợp. Goal Failsafe `integration-test`/`verify` có default phase bindings tương ứng. Không dùng `mvn test` để kiểm chứng Failsafe ở phase sau package, vì invocation chưa tới đó.

Một class tên `CalculatorIT` dùng JUnit Jupiter có thể được Failsafe phát hiện khi có engine, nhưng gọi nó là *integration test thật* chỉ khi nó kiểm tra sự tương tác với nhiều thành phần như database, server hoặc filesystem như dự án đặt ra.

## 10. Phân biệt skip với các cờ liên quan khác

| Cấu hình/lệnh | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `-DskipTests=true` | Surefire không chạy unit tests, test code vẫn compile | `maven.test.skip` |
| `-Dmaven.test.skip=true` | Compiler bỏ testCompile; Surefire/Failsafe skip tests | “Bỏ mọi Maven phase liên quan tests” |
| `-DskipITs=true` | Failsafe skip integration test execution | Bỏ unit tests Surefire |
| `-Dtest=CalculatorTest` | Chọn một test class cho Surefire | Skip toàn bộ tests |
| `-Dtest=CalculatorTest#addReturnsSum` | Chọn một test method | Không compile test sources |
| `-Dmaven.test.failure.ignore=true` | Tests vẫn có thể chạy nhưng failures không làm fail build | Skip test execution |
| `-DfailIfNoTests=true` | Fail nếu không có test nào phù hợp trong Surefire theo option | Bật tests bị skip |
| `mvn test-compile` | Biên dịch test sources, **không** chạy test phase | `mvn test` |
| `mvn compile` | Chỉ compile main (và phases trước đó) | Chạy tests |
| `mvn verify` | Chạy tới verify; tác động phụ thuộc plugin bindings | “Chắc chắn đã chạy integration tests” |

**Không dùng `maven.test.failure.ignore` như một cách viết khác của `skipTests`.** Nó có thể chạy tests, ghi lỗi assertion và report, rồi không làm Maven build thất bại. Về quality gates, đó là loại rủi ro khác nhưng vẫn có thể khiến `BUILD SUCCESS` không phản ánh test suite khỏe.

### 10.1. Khi `-DskipTests=false` vẫn không chạy tests

Xem liệu bạn đang có:

```bash
mvn test -DskipTests=false -Dmaven.test.skip=true
```

Trường hợp này Compiler Plugin vẫn skip test compilation theo `maven.test.skip=true`. `skipTests=false` **không** tự tắt một property **khác tên**. Tương tự, POM có thể hardcode `<skipTests>true</skipTests>`, hoặc một profile có skip khác.

Phải kiểm tra **tham số hiệu lực** trong plugin thực tế chứ không chỉ nhìn lệnh CLI.

## 11. Đặt skip trong POM: mặc định nào là tốt?

Trong phần lớn project, **nên để tests bật mặc định** và chỉ skip qua một invocation được ghi rõ lý do. Nếu thực sự có cấu hình skip theo property, có thể dùng hai fragments sau.

### 11.1. Property cấp project

```xml
<properties>
    <skipTests>false</skipTests>
</properties>
```

### 11.2. Plugin configuration

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <skipTests>${skipTests}</skipTests>
    </configuration>
</plugin>
```

Hai blocks là **fragments ở hai vị trí khác nhau** trong POM. Chúng liên kết property `skipTests` với tham số của Surefire. Khi không có override khác:

```bash
mvn clean test -DskipTests=true
mvn clean test -DskipTests=false
```

đều có ý nghĩa nhất quán.

**Không nên** hardcode:

```xml
<configuration>
    <skipTests>true</skipTests>
</configuration>
```

rồi quên rằng Surefire tests sẽ không chạy ở mọi build. Nếu team dùng parent POM, tác động có thể lan tới các child modules do inheritance. Xem effective POM từng module để tìm nguồn skip.

### 11.3. Cẩn trọng với parent property

Parent POM đặt:

```xml
<properties>
    <maven.test.skip>true</maven.test.skip>
</properties>
```

có thể khiến toàn bộ children kế thừa broad skip nếu Compiler/Surefire/Failsafe nhận property. Một reactor lớn có thể package thành công với test code hoàn toàn không được kiểm tra. Đây không nên là mặc định cho release/merge quality gates.

Nếu có profile dành cho đóng gói nhanh, hãy bảo đảm có job CI khác **bắt buộc** compile và run tests, và không vô tình bật profile skip trong release pipeline.

## 12. CI/CD: khi nào có thể skip?

### 12.1. Build để kiểm chứng thay đổi

Ví dụ merge gate:

```bash
mvn -B clean verify
```

Kết quả cần đọc từ từng module và test runner: số tests, failures, errors, skipped tests (theo JUnit), exit code, integration tests nếu có và coverage. `BUILD SUCCESS` ở cuối không đủ nếu Surefire/Failsafe bị skip từ cấu hình.

### 12.2. Build tạm để kiểm tra artifact

Khi bạn chỉ cần JAR để kiểm tra manifest/package content và test suite đang chạy ở job khác:

```bash
mvn -B clean package -DskipTests=true
```

Đây thường là lựa chọn **ít mất kiểm tra hơn** so với `maven.test.skip` vì vẫn compile test Java source. Nhưng lệnh này vẫn chưa chứng minh assertions PASS.

### 12.3. Lựa chọn mạnh chỉ trong tình huống thật sự cần

```bash
mvn -B clean package -Dmaven.test.skip=true
```

Đây là lựa chọn bỏ cả test compilation. Cần ghi nhãn rõ trong pipeline/report:

```text
Main compilation: PASS
Test compilation: SKIPPED
Unit test execution: SKIPPED
Integration tests: depends on plugin policy; broad skip typically applies
Artifact packaging: PASS
Quality gate based on tests: NOT RUN
```

**Không** gom kết quả thành “All tests passed”. Nếu yêu cầu phát hành gồm test/coverage gates, lệnh này không đáp ứng yêu cầu ấy.

### 12.4. Vì sao `skipTests` có thể không tiết kiệm nhiều?

Với dự án có hàng nghìn test classes:

- Test compilation vẫn phải chạy.
- Maven vẫn có thể resolve JUnit/Mockito/test-scoped dependencies.
- Annotation processors và generated test sources có thể tiêu tốn thời gian.
- Test resources và plugin goals khác có thể vẫn chạy.
- Multi-module build cần qua nhiều module.

`skipTests` chủ yếu cắt **thời gian thực thi tests**. Nếu test compilation mới là nút thắt, nó sẽ không nhanh như broad skip. Tuy vậy, **tắt compile tests để tối ưu tốc độ** cần đánh đổi chất lượng có chủ đích và job kiểm tra độc lập.

### 12.5. Test reports có thể cũ khi không clean

Nếu chạy `mvn package -DskipTests=true` **không có `clean`**, thư mục `target/surefire-reports` có thể giữ XML từ lần trước. Một dashboard đọc file cũ có thể hiển thị tests xanh dù commit hiện tại không chạy test.

Khi chẩn đoán skip và trong CI, dùng workspace/cache có quy tắc rõ và tránh lẫn test results giữa invocations. Trong demo, luôn chạy `mvn clean ...` để đối chiếu chắc chắn.

## 13. Multi-module, code generation và plugin khác

Các property skip thường được Maven truyền vào reactor projects trong **cùng invocation**, nhưng hiệu ứng khác nhau theo module:

- Module A có JUnit tests và Surefire `3.6.1`: `skipTests` bỏ chạy UT, compiler vẫn compile tests.
- Module B không có test sources: build có thể thành công dù testCompile không có gì để compile; không thể suy ra skip chỉ từ câu `No sources to compile`.
- Module C có Failsafe `3.6.1` đã bind: `-DskipTests` **không tự bỏ ITs**; cần `-DskipITs`.
- Module D dùng một compiler/plugin khác không hỗ trợ `maven.test.skip`: có thể tiếp tục compile tests theo cơ chế của nó.

Trong các project có generated test sources:

```text
generate-test-sources
    -> code generator tạo .java
test-compile
    -> compiler:testCompile
test
    -> surefire:test
```

`-Dmaven.test.skip` có thể bỏ compiler:testCompile, **nhưng code generator vẫn chạy** nếu nó không có skip option tương ứng. Vì vậy đừng định nghĩa broad skip như “mọi task test đều không chạy”, đặc biệt nếu có JaCoCo, Checkstyle, Enforcer, source generators hoặc code-analysis plugins bind riêng.

### 13.1. Một POM có thể dùng pluginManagement nhưng không chạy test

`<pluginManagement>` quản lý version/configuration khi plugin được dùng; nó không tự bind mọi plugin goal vào lifecycle. Surefire thường có binding mặc định trong Java JAR lifecycle; Failsafe thường cần explicit execution cho goals integration-test/verify. Khi phân tích reports, xem `<build><plugins>` và `<executions>` hiệu lực ở từng module.

### 13.2. Properties có thể đến từ nhiều nơi

Các nguồn cần xem:

1. CLI `-D...`.
2. `pom.xml` properties/configuration.
3. Parent POM inheritance.
4. Active profiles.
5. `.mvn/maven.config`.
6. Maven runner settings/IDE/CI arguments.
7. Plugin-specific skip parameters và version compatibility.

**Đừng đoán override precedence** nếu một POM ghi `<skipTests>true</skipTests>` cứng, trong khi CLI đặt `-DskipTests=false`. Hãy xem effective POM và plugin logs trong invocation thực tế.

## 14. Lệnh kiểm tra và chẩn đoán

Tại root project:

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean test
mvn clean package -DskipTests=true
mvn clean package -Dmaven.test.skip=true
mvn -X clean test -DskipTests=true
```

Trong log, tìm:

```text
maven-compiler-plugin:...:compile
maven-compiler-plugin:...:testCompile
maven-surefire-plugin:...:test
Tests are skipped
Tests run: ...
```

Các dòng trên là **pattern cần tìm**, không phải cam kết từng bản Maven in nguyên văn. `-X` tạo debug logs rất dài và có thể chứa URL nội bộ hoặc dữ liệu nhạy cảm; không đăng công khai toàn bộ nếu chưa kiểm tra.

Trong demo, kiểm tra chính test class:

```bash
javap -classpath target/test-classes org.example.CalculatorTest
```

Sau `-DskipTests`, lệnh kỳ vọng tìm được compiled class. Sau `maven.test.skip` và `clean`, lệnh có thể báo class không tồn tại (đó là điều phù hợp với việc compiler bỏ test compilation).

### 14.1. Phân biệt `Tests run: 0` với test skip

Test count 0 có thể do:

- Không có test class nào.
- Tên test class không khớp Surefire include patterns.
- Thiếu JUnit engine/provider tương thích.
- Test bị `@Disabled`, tag/filter hoặc exclusion.
- Sources không nằm trong `src/test/java` và chưa được đăng ký test root.
- `-Dtest=...` lọc hết tests.
- Tests đã bị skip.
- Maven chưa chạy tới phase `test`.

Vì vậy **không** chẩn đoán `Tests run: 0` thành `maven.test.skip` một cách tự động. Cần phối hợp report, plugin version, compiled test `.class`, execution log và flags CLI.

### 14.2. `No tests were executed` trong CI

Surefire có parameter `failIfNoTests`; cấu hình strict có thể giúp phát hiện module **đáng ra phải có tests** nhưng không discover gì. Tuy nhiên trong reactor cũng có modules không cần test suite, vì vậy áp chính sách theo module thích hợp. Nếu build chủ động skip, không dùng `failIfNoTests` như cách chứng minh tests đã chạy.

### 14.3. Kết quả Java main không chứng minh kết quả JUnit

Chạy:

```bash
java -cp target/classes org.example.Main
```

sẽ in:

```text
2 + 3 = 5
```

Dù Surefire đã chạy hay bị skip, chương trình chính vẫn có thể in đúng dòng đó. Nó chỉ kiểm tra logic khi chạy main, **không thay thế JUnit test report**. Đây là một minh chứng thực hành rằng “ứng dụng chạy” và “unit test suite PASS” là hai tuyên bố khác nhau.

## 15. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| `-DskipTests` vẫn có lỗi Java ở test sources | Test compilation không bị skip | Đúng hành vi; sửa test code |
| `-Dmaven.test.skip` build xanh dù test code sai | Compiler không testCompile | Không công bố tests PASS; chạy lại đầy đủ |
| `BUILD SUCCESS` nhưng không có Surefire XML mới | Skip, no tests discovered hoặc chưa tới test phase | Xem logs, test class và report timestamps |
| `-DskipTests=true` vẫn chạy ITs | Failsafe **3.6.0+** đã tách khỏi user property này | Dùng `-DskipITs=true` |
| `mvn test -DskipTests=false` vẫn không compile tests | `maven.test.skip=true` còn hiệu lực | Tắt broad skip và kiểm tra effective config |
| `-DskipITs` không có tác dụng | Project không dùng/bind Failsafe, hoặc plugin version khác | Xem executions và plugin version |
| `-DskipTests` ít tăng tốc | Test compilation và dependency resolution vẫn chạy | Xác định bottleneck, tránh tắt tests bừa |
| `target/test-classes` còn sau broad skip | Output cũ hoặc goal khác tạo | `clean`, kiểm tra `.class` cụ thể |
| Report cũ hiện xanh khi skip | Không clean hoặc pipeline trộn artifacts | Tách reports/workspaces, timestamp |
| Test methods có `@Test` nhưng không chạy | Surefire provider/naming/filter/version | Kiểm tra JUnit Jupiter engine và test discovery |
| `mvn compile` không in `Tests are skipped` | Surefire chưa được gọi | Chạy tới phase `test` |
| Build vẫn fail vì Enforcer/Checkstyle | Skip property không điều khiển mọi plugins | Sửa lỗi plugin tương ứng |
| Dùng `maven.test.failure.ignore` mà build xanh với failures | Tests vẫn chạy nhưng failure impact bị bỏ qua | Xem Surefire reports, tránh trên release |
| Parent bật skip ngoài ý muốn | Property/configuration được kế thừa | Xem effective POM từng module |
| Test `.class` có nhưng JAR không có test class | Đúng default packaging JAR | Test classes ở `target/test-classes`, không phải main JAR |
| Muốn skip UT nhưng vẫn chạy IT | Cần Surefire3.6+ và Failsafe3.6+ semantics | `-DskipTests=true` rồi `mvn verify` |
| Muốn skip IT nhưng chạy UT | Failsafe hiểu `skipITs` | `-DskipITs=true` rồi `mvn verify` |
| Main compile error dù `maven.test.skip=true` | Main compilation không bị skip | Sửa main source/dependency |
| Skip test vẫn tải plugins | Maven vẫn resolve plugins được bind | Kiểm tra network/repository; skip không sửa lỗi download |

## 16. Câu hỏi tự kiểm tra

**1.** `skipTests` khác `maven.test.skip` ở điểm nào?  
**Đáp án:** `skipTests` bỏ chạy Surefire unit tests nhưng vẫn biên dịch test sources; `maven.test.skip` bỏ cả test compilation (Compiler Plugin) và test execution được các plugin hỗ trợ.

**2.** Vì sao một lỗi `int x = "hi";` trong `src/test/java` vẫn làm `mvn package -DskipTests` lỗi?  
**Đáp án:** Vì Compiler Plugin vẫn chạy testCompile và phát hiện type mismatch.

**3.** Cùng lỗi, vì sao `mvn package -Dmaven.test.skip` có thể tạo JAR?  
**Đáp án:** Vì test compilation đã bị bỏ qua, không phải code được sửa.

**4.** `-DskipTests=true` có nghĩa Surefire tests PASS?  
**Đáp án:** Không. Surefire không thực thi chúng trong invocation đó.

**5.** `-Dmaven.test.skip` có bỏ compiler:compile của main Java source?  
**Đáp án:** Không. Nó nhằm test compilation/execution.

**6.** Failsafe 3.6.1 có skip ITs khi chỉ có `-DskipTests=true`?  
**Đáp án:** Không tự skip; dùng `-DskipITs=true` cho Failsafe.

**7.** Failsafe 2.x chắc chắn có hành vi giống 3.6.1?  
**Đáp án:** Không. Các bản trước 3.6.0 từng dùng chung user property `skipTests`; kiểm tra docs đúng version.

**8.** `mvn compile -DskipTests` có thể dùng chứng minh Surefire skip?  
**Đáp án:** Không, vì phase test chưa chạy.

**9.** File nào là bằng chứng test compilation trong demo?  
**Đáp án:** `target/test-classes/org/example/CalculatorTest.class`.

**10.** Thư mục `target/surefire-reports` còn file từ hôm trước có chứng minh test hôm nay chạy?  
**Đáp án:** Không; phải kiểm tra reports mới và logs, tốt nhất sau clean.

**11.** `-Dmaven.test.failure.ignore` có giống skipTests?  
**Đáp án:** Không. Nó có thể vẫn chạy tests, nhưng bỏ qua failure impact.

**12.** Dùng `-DskipTests=false -Dmaven.test.skip=true` có compile tests không?  
**Đáp án:** Compiler Plugin vẫn có thể skip vì `maven.test.skip` vẫn true.

**13.** Nếu muốn chỉ bỏ ITs và giữ UTs, dùng lệnh nào?  
**Đáp án:** `mvn verify -DskipITs=true` với Failsafe đã bind.

**14.** Một plugin generator test-source có tự skip theo `maven.test.skip` không?  
**Đáp án:** Không mặc định; phụ thuộc plugin. Cờ này không phải cơ chế tắt mọi plugin.

**15.** Khi nào dùng `maven.test.skip` an toàn hơn?  
**Đáp án:** Chỉ khi nhiệm vụ thực sự không cần xác minh test code, có lý do rõ và một job khác bắt buộc compile/run tests trước merge/release.

## 17. Checklist ứng dụng

- [ ] Xác định rõ mục tiêu: không chạy tests hay không biên dịch cả tests.
- [ ] Dùng `-DskipTests=true` khi chỉ cần bỏ unit test **execution**.
- [ ] Hiểu rằng test compile errors vẫn có thể chặn build với `skipTests`.
- [ ] Dùng `-Dmaven.test.skip=true` chỉ khi chấp nhận bỏ cả test compilation.
- [ ] Không coi build có skip là bằng chứng tests PASS.
- [ ] Ghim Maven Compiler/Surefire/Failsafe versions và kiểm tra semantics theo version.
- [ ] Biết Failsafe 3.6.0+ tách `-DskipTests` khỏi IT skip; dùng `-DskipITs`.
- [ ] Với project có cả Surefire/Failsafe, biết loại tests nào vẫn chạy đến verify.
- [ ] Dùng `mvn clean ...` để không nhầm test `.class`/XML report cũ.
- [ ] Kiểm tra test class thực sự tồn tại sau skipTests và không tồn tại sau broad skip.
- [ ] Không nhầm test selection `-Dtest=...` với test skipping.
- [ ] Không nhầm `maven.test.failure.ignore` với `skipTests`.
- [ ] Không hardcode skip=true vào parent mà mọi modules kế thừa ngoài ý muốn.
- [ ] Nếu có codegen/test roots, kiểm tra từng plugin có tự skip hay không.
- [ ] Thiết kế CI bắt buộc unit/integration tests và coverage phù hợp trước merge/release.
- [ ] Kết thúc thử nghiệm bằng `mvn clean verify` không skip và xem report mới.

## 18. Tài liệu chính thức

1. [Apache Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
2. [Apache Maven Surefire Plugin — surefire:test (skipTests, skip)](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
3. [Apache Maven Compiler Plugin — compiler:testCompile (maven.test.skip)](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
4. [Apache Maven Failsafe Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html)
5. [Apache Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
6. [Apache Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
7. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
8. [Maven Central — JUnit Jupiter 5.11.4](https://central.sonatype.com/artifact/org.junit.jupiter/junit-jupiter/5.11.4)
9. [Apache Maven Surefire — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)

**Kết luận:** **`skipTests` = vẫn compile tests, không chạy Surefire unit tests. `maven.test.skip` = không compile tests và không chạy tests qua các plugins hỗ trợ.** Khi có integration tests, kiểm tra Failsafe version: với **3.6.0+**, `-DskipTests` không tự bỏ ITs, còn `-DskipITs` mới là cờ bỏ integration test execution. Bất kỳ build nào đã skip các bước test đều phải được gắn nhãn rõ ràng, không thay thế một lần `mvn clean verify` kiểm thử đầy đủ.
