# Chọn bài kiểm thử cần chạy và đọc báo cáo thất bại trong Spring Boot

## 1. Mục tiêu và mô hình tư duy

Khi làm việc với một dự án Spring Boot dùng Maven hoặc Gradle, không phải lúc nào ta cũng cần chạy toàn bộ test suite. Để sửa nhanh một lỗi, có thể **chọn một lớp test, một nhóm test hoặc một phương thức**; trước khi merge/deploy, lại cần **chạy đầy đủ các kiểm thử bắt buộc**. Sau khi build báo lỗi, bước tiếp theo không phải đoán theo dòng cuối `BUILD FAILURE` mà là tìm **test case đầu tiên thất bại, thông báo assertion/exception, stack trace và báo cáo đã lưu**.

Có ba câu hỏi riêng:

1. **Test nào được chọn?** Lọc theo tên lớp/method, wildcard, JUnit tag hoặc Gradle task/module.
2. **Test có thật sự chạy không?** Phân biệt `Tests run: 0`, `NO-SOURCE`, test `SKIPPED`, Gradle `UP-TO-DATE` với test đã thực thi thành công.
3. **Vì sao thất bại?** Phân biệt sai kết quả mong đợi (assertion failure), exception lúc chạy test, lỗi compile, lỗi Spring context, lỗi kết nối ngoại vi và lỗi runner/plugin.

```text
Thay đổi mã nguồn / phát hiện bug
               |
               v
Chạy test nhỏ nhất tái hiện bug
               |
       +-------+---------+
       |                 |
  Test fail            Test pass
       |                 |
Đọc report,         Có đúng test
sửa nguyên nhân     được phát hiện?
       |                 |
       +---------+-------+
                 |
       Chạy lại test vừa sửa
                 |
        Chạy suite/test task đầy đủ
                 |
       Kiểm tra báo cáo và build CI
```

**Nguyên tắc:** chạy một test để phát triển nhanh, nhưng **không dùng một test pass làm bằng chứng cả dự án pass**. Đảm bảo cuối cùng các test unit, integration và check được cấu hình cho dự án đều chạy trong pipeline tương ứng.

## 2. Phân biệt các tầng kiểm thử và công cụ chạy

| Loại test | Ví dụ | Công cụ/pha thường dùng |
|---|---|---|
| Unit test Java/JUnit 5 | Kiểm tra một phép tính không cần Spring context | Maven Surefire `test`; Gradle `test` |
| Spring test slice | `@WebMvcTest`, `@DataJpaTest` cho một phần ứng dụng | Vẫn chạy qua JUnit 5 và task/goal test tương ứng |
| Spring integration test | `@SpringBootTest`, tương tác nhiều bean hoặc tài nguyên | Có thể chạy bằng Surefire hoặc task riêng/Failsafe, tùy cấu hình |
| End-to-end / smoke | Kiểm tra ứng dụng triển khai thật | Task/pipeline riêng, không tự xuất hiện chỉ vì thêm starter-test |

Một class `@SpringBootTest` không tự biến thành integration-test task: cách phân loại còn phụ thuộc **quy tắc đặt tên và cấu hình Maven/Gradle**. Spring Boot `spring-boot-starter-test` cung cấp thư viện thử nghiệm phổ biến (trong đó có JUnit Jupiter); nó **không tự tạo pipeline e2e**.

### Maven lifecycle

Với Maven:

- `mvn test` đi đến phase `test`; Surefire thường thực thi unit tests được phát hiện.
- `mvn package` đi qua các phase trước đó, gồm `test`, rồi đóng gói nếu không có lỗi chặn build.
- `mvn verify` đi qua `package` và các phase liên quan đến integration test; **Failsafe chỉ chạy integration tests khi đã cấu hình plugin/execution**. Không mặc định `verify` tự sinh test tích hợp.
- Surefire thường ghi báo cáo tại `target/surefire-reports`.
- Failsafe thường ghi báo cáo tại `target/failsafe-reports`.

### Gradle task graph

Với Gradle Java/Spring Boot:

- `./gradlew test` chạy task `test` (test source set mặc định).
- `./gradlew check` chạy các nhiệm vụ kiểm tra mà project đã đăng ký; trong Java plugin thường gồm `test`.
- `./gradlew build` thường phụ thuộc `assemble` và `check`; khi test fail, build thất bại.
- Các task như `integrationTest` **chỉ tồn tại khi build script/plugin tạo chúng**.
- Báo cáo HTML mặc định cho task `test` thường ở `build/reports/tests/test/index.html`; JUnit XML thường ở `build/test-results/test/`.

**Lưu ý:** đa module có nhiều báo cáo theo từng module. Nếu `service-api:test` fail, hãy mở `service-api/build/reports/tests/test/index.html`, không phải báo cáo `test` ở root giả định.

## 3. Maven Surefire: chọn class và nhóm test

Giả sử đã có Maven Wrapper, mở terminal tại root chứa `pom.xml` và `mvnw`. Trên Linux/macOS:

```bash
# Chạy toàn bộ unit tests theo cấu hình dự án
./mvnw test

# Chạy đúng một lớp test
./mvnw -Dtest=TotalCalculatorTest test

# Dùng tên class đầy đủ để tránh trùng tên
./mvnw -Dtest=com.example.testing.TotalCalculatorTest test

# Chọn theo mẫu tên
./mvnw "-Dtest=*CalculatorTest" test

# Chọn nhiều lớp (danh sách ngăn cách bởi dấu phẩy)
./mvnw "-Dtest=TotalCalculatorTest,TotalCalculatorRegressionTest" test

# Chọn JUnit 5 tests gắn tag fast
./mvnw -Dgroups=fast test

# Bỏ các test gắn tag regression
./mvnw -DexcludedGroups=regression test
```

Trong Windows PowerShell, dùng `.\mvnw.cmd`, ví dụ:

```powershell
.\mvnw.cmd "-Dtest=TotalCalculatorTest" test
.\mvnw.cmd "-Dtest=TotalCalculatorTest,TotalCalculatorRegressionTest" test
.\mvnw.cmd "-Dgroups=fast" test
```

Nếu không có Maven Wrapper, thay `./mvnw` bằng `mvn` đã cài. Đặt đối số `-D...` trong dấu nháy khi có ký tự đặc biệt (`*`, `#`, dấu phẩy, `!`), nhất là khi đổi giữa Bash/PowerShell/CI.

### 3.1. Quy tắc phát hiện test mặc định

Nếu không dùng `-Dtest` và chưa cấu hình include/exclude riêng, Maven Surefire thường tìm class theo mẫu tên:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

Ví dụ `TotalCalculatorTest` được phát hiện; `TotalCalculatorIT` mặc định hướng về Failsafe nếu plugin đó được cấu hình, không phải Surefire. Các nested test, parameterized tests, custom JUnit engines và các pattern phức tạp có thể cần cấu hình hoặc cách lọc riêng.

**Chạy theo class** là cách chắc chắn khi đang thử một dự án JUnit Jupiter mới. Surefire cũng có cú pháp lọc phương thức `-Dtest=ClassName#methodName`, nhưng tài liệu plugin về một số mẫu lọc phương thức lưu ý hỗ trợ theo provider/framework (lịch sử ghi JUnit 4/TestNG); với JUnit Jupiter hãy **kiểm tra bản Surefire và xác nhận thực tế số test được chạy** trước khi lệ thuộc vào lựa chọn một phương thức. Ví dụ dạng cú pháp:

```bash
./mvnw "-Dtest=TotalCalculatorTest#addsShipping" test
```

Khi cần lọc test JUnit 5 theo một nhóm ổn định và có thể tái lập trên CI, dùng `@Tag` kết hợp `-Dgroups`/`-DexcludedGroups` hoặc cấu hình JUnit Platform thay vì phụ thuộc những mẫu tên động phức tạp.

### 3.2. Phải hiểu “không tìm thấy test”

Với `-Dtest=MissingTest`, Surefire mặc định **báo lỗi** nếu không chạy được test được chỉ định (`surefire.failIfNoSpecifiedTests=true`). Đây là lỗi **selection/discovery**, không có nghĩa một assertion đã fail.

Có thể chủ động dùng:

```bash
./mvnw "-Dtest=MissingTest" test
```

để nhận biết chọn sai tên. Nếu công cụ báo “No tests matching pattern”, kiểm tra đúng package/class, JUnit engine, đường dẫn `src/test/java` và task/goal.

Trong Maven reactor đa module, lệnh `-pl :service -am -Dtest=SomeTest test` có thể khiến module phụ thuộc phía trước cũng nhận `-Dtest` nhưng không có class trùng tên. Khi đã hiểu rõ phạm vi, có thể dùng `-Dsurefire.failIfNoSpecifiedTests=false` để các module **không có test được chỉ định** không chặn build, rồi xác minh module mục tiêu thật sự có test chạy. Không áp dụng cờ bỏ lỗi này cho mọi pipeline để che nhầm tên class.

### 3.3. Skip tests không phải là chọn tests

| Cách Maven | Kết quả | Khi nào cân nhắc |
|---|---|---|
| `-Dtest=SomeTest` | Chỉ chạy test khớp bộ lọc Surefire | Tái hiện bug cục bộ |
| `-Dgroups=fast` | Chạy tests được gắn tag tương ứng (JUnit 5) | Tập test nhanh được quản lý |
| `-DskipTests` | Bỏ thực thi Surefire tests nhưng thường vẫn compile test sources | Thao tác tạm thời, không thay cho QA |
| `-Dmaven.test.skip=true` | Bỏ cả compile lẫn chạy test theo plugin tương ứng | Chỉ khi có lý do đặc biệt |
| `-DskipITs` | Bỏ integration tests qua Failsafe | Tách pipeline khi cần |

Với **Failsafe 3.6.0 trở lên**, `-DskipTests` không còn tự điều khiển skip của Failsafe như trước; dùng `-DskipITs` để bỏ integration tests, hoặc `-Dmaven.test.skip=true` khi thực sự muốn bỏ cả unit/integration test. Luôn kiểm tra phiên bản plugin và log vì parent POM có thể có cấu hình riêng.

**Không chấp nhận “BUILD SUCCESS” từ lệnh bỏ test làm bằng chứng test suite pass.** Bản thân việc skip phải được ghi rõ trong kết quả CI/release.

## 4. Maven Failsafe: integration tests và báo cáo riêng

**Surefire** thường chạy unit tests ở phase `test`. **Failsafe** được thiết kế để chạy integration tests ở các goal `integration-test` và `verify`. Thiết kế Failsafe tránh ngắt lifecycle quá sớm khi integration test fail, cho phép phase `post-integration-test` dọn tài nguyên (nếu được cấu hình).

Nếu dự án có integration tests theo tên `*IT` hoặc `IT*`, cần **thêm execution cho Failsafe**. Đoạn sau chèn **vào `<build><plugins>` của POM đã có**, không phải file POM độc lập:

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

Sau đó:

```bash
# Bao gồm integration-test và verify/cleanup phase theo lifecycle
./mvnw verify

# Nếu cần chọn lớp IT cụ thể cho Failsafe:
./mvnw "-Dit.test=TotalCalculatorIT" verify
```

Nếu Surefire test fail ở phase `test`, Maven có thể dừng **trước** khi đến các phase Failsafe. Muốn xem báo cáo tích hợp, trước hết sửa lỗi unit test hoặc chạy cấu hình được thiết kế riêng để tách integration tests. **Không chạy riêng phase `integration-test` làm bước cuối** nếu pipeline cần các bước post-integration-test và `verify`.

Đường dẫn báo cáo Failsafe thường là:

```text
target/failsafe-reports/
├── TEST-com.example.testing.TotalCalculatorIT.xml
├── com.example.testing.TotalCalculatorIT.txt
└── failsafe-summary.xml
```

Đường dẫn, tên file và số file thay đổi theo cấu hình; không mặc định đã có báo cáo nếu plugin chưa chạy. `failsafe-summary.xml` ghi trạng thái tổng hợp để goal `verify` quyết định build thành công hay thất bại.

## 5. Gradle: chọn test class và method bằng --tests

Khi project dùng Gradle Wrapper:

```bash
# Chạy toàn bộ test task
./gradlew test

# Chỉ chạy một class
./gradlew test --tests "com.example.testing.TotalCalculatorTest"

# Chỉ chạy một method của JUnit Jupiter
./gradlew test --tests "com.example.testing.TotalCalculatorTest.addsShipping"

# Dùng simple class name (bắt đầu bằng chữ hoa)
./gradlew test --tests "TotalCalculatorTest"

# Wildcard với các class có hậu tố CalculatorTest
./gradlew test --tests "*CalculatorTest"

# Nhiều bộ lọc --tests (hợp các tên được chọn)
./gradlew test --tests "*CalculatorTest" --tests "*RegressionTest"

# Test của một module trong multi-project build:
./gradlew :service:test --tests "*CalculatorTest"

# In nhiều log hơn khi phân tích runner:
./gradlew test --tests "*RegressionTest" --info
```

PowerShell dùng `.\gradlew.bat` thay `./gradlew`. Với Gradle, cú pháp lọc method là `ClassName.methodName` (dấu chấm); khác ký hiệu `#` của Maven Surefire. Filter `--tests` được Gradle truyền cho **task Test**, không phải tùy chọn Java launcher.

**Không có test phù hợp** thường khiến Gradle báo kiểu `No tests found for given includes`: kiểm tra method thực, class/package, framework, Java test source set và các filter cố định trong `build.gradle`. Không giải quyết bằng cách xóa hết kiểm tra lỗi trong CI.

### 5.1. Gradle incremental build và việc chạy lại

Gradle tối ưu task bằng up-to-date checks/cache. Nếu `test` được đánh dấu `UP-TO-DATE`, không thể suy rằng nó vừa thực thi tất cả test trên một JVM mới. Khi đang phân tích lỗi ngẫu nhiên hoặc muốn tái hiện trong một lần chạy mới:

```bash
./gradlew test --tests "TotalCalculatorTest" --rerun-tasks
```

`--rerun-tasks` buộc chạy lại task và các dependency task liên quan, không đồng nghĩa `clean` toàn bộ thư mục build. Dùng `--info`/`--stacktrace` để chẩn đoán Gradle khi cần, nhưng lưu ý **stack trace Gradle** chủ yếu mô tả lỗi task; nguyên nhân assertion thường dễ đọc hơn trong **HTML/XML report của test**.

### 5.2. JUnit 5 tags trong Gradle

Đặt tag cho class/method, ví dụ:

```java
@Tag("fast")
@Test
void addsShipping() {
    // logic test
}
```

Đây chỉ là **đoạn annotation trên method**, không phải class Java độc lập. Ở `build.gradle` (Groovy DSL):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'fast'
    }
}
```

Cấu hình này làm task `test` **chỉ chạy tag `fast`** cho tất cả lần gọi tiếp theo. Khi muốn suite đầy đủ, phải bỏ/đổi filter hoặc tạo task test riêng; `--tests` trên CLI không nhất thiết vượt qua JUnit tag filter đã cố định. Có thể tạo task `fastTest`/`integrationTest` riêng để chính sách lọc rõ ràng, tránh “test pass” nhưng bỏ hàng loạt test ngoài ý muốn.

## 6. Dự án Spring Boot Java 17 thực hành với một test cố ý thất bại

Ta sẽ tạo **một ví dụ thực thi được**, với hai lớp test:

- `TotalCalculatorTest`: **hai test pass**.
- `TotalCalculatorRegressionTest`: **một test fail có chủ đích** vì expected value sai, nhằm luyện đọc báo cáo.

Sau khi thấy lỗi, sửa expected value rồi chạy lại toàn bộ suite. Ví dụ dùng **Spring Boot 3.5.0** và **Java 17** được pin cho mục đích học, không khẳng định đây là phiên bản mới nhất. Máy cần Maven phù hợp hoặc Maven Wrapper sẵn có, JDK 17+ và quyền truy cập dependency repository.

### 6.1. Cấu trúc file

```text
test-report-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/testing/
    │   ├── TestReportApplication.java
    │   ├── TotalCalculator.java
    │   └── CalculatorConsole.java
    └── test/java/com/example/testing/
        ├── TotalCalculatorTest.java
        └── TotalCalculatorRegressionTest.java
```

### 6.2. pom.xml hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>test-report-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
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

Ở đây Surefire **3.6.1** được khai báo rõ để ổn định ví dụ; không suy rằng mọi Spring Boot parent tự dùng phiên bản này. `spring-boot-starter-test` cung cấp JUnit Jupiter và các công cụ test cần thiết.

### 6.3. Mã nguồn ứng dụng và logic thuần Java

`src/main/java/com/example/testing/TestReportApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestReportApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestReportApplication.class, args);
    }
}
```

Không khai báo starter web nên ví dụ không yêu cầu web server hay database. Các unit tests sắp tạo **không cần khởi động Spring context**: chạy nhanh, ít phụ thuộc môi trường và dễ chẩn đoán assertion.

`src/main/java/com/example/testing/TotalCalculator.java`:

```java
package com.example.testing;

public final class TotalCalculator {
    public int total(int price, int shipping) {
        if (price < 0 || shipping < 0) {
            throw new IllegalArgumentException(
                    "price and shipping must be nonnegative");
        }
        return Math.addExact(price, shipping);
    }
}
```

`src/main/java/com/example/testing/CalculatorConsole.java`:

```java
package com.example.testing;

public final class CalculatorConsole {
    public static void main(String[] args) {
        int result = new TotalCalculator().total(100, 20);
        System.out.println("total=" + result);
    }
}
```

Có thể xác minh **phần Java thuần** bằng JDK 17, không cần Maven/Spring Boot:

```bash
javac -d out \
  src/main/java/com/example/testing/TotalCalculator.java \
  src/main/java/com/example/testing/CalculatorConsole.java

java -cp out com.example.testing.CalculatorConsole
```

Stdout chính xác của `java -cp ...`:

```text
total=120
```

Trên PowerShell, có thể viết lệnh `javac` một dòng và dùng đường dẫn tương tự; việc chạy `java -cp out ...` không thay đổi. `CalculatorConsole` chỉ là công cụ kiểm chứng logic đơn giản, không chạy Spring context và không thay thế cho unit tests.

### 6.4. Test class chạy thành công

`src/test/java/com/example/testing/TotalCalculatorTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("fast")
class TotalCalculatorTest {
    private final TotalCalculator calculator = new TotalCalculator();

    @Test
    void addsShipping() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Test
    void rejectsNegativeAmounts() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(-1, 20)
        );
    }
}
```

Lớp này có **2 test methods**, cả hai đều pass với `TotalCalculator` đã cung cấp. Tag `fast` dùng để chọn bằng Surefire hoặc cấu hình Gradle JUnit Platform.

### 6.5. Test class thất bại có chủ đích

`src/test/java/com/example/testing/TotalCalculatorRegressionTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("regression")
class TotalCalculatorRegressionTest {
    @Test
    void detectsWrongExpectation() {
        TotalCalculator calculator = new TotalCalculator();

        // Cố ý sai: 100 + 20 = 120, không phải 130.
        assertEquals(130, calculator.total(100, 20));
    }
}
```

`@Test` này **fail có chủ ý**. Bản thân class `TotalCalculator` trả đúng `120`. Test đang kỳ vọng sai `130`. Đây là ví dụ để phân biệt “code có bug” với “assertion/specification sai”: báo cáo sẽ chỉ ra kỳ vọng và thực tế, nhưng người sửa vẫn phải xác minh **hợp đồng nghiệp vụ** để biết phải sửa code hay sửa expected value.

## 7. Thực hành Maven: chọn test, tạo lỗi và đọc report

Đứng tại root dự án có `pom.xml`. Khi có wrapper dùng `./mvnw` (Windows PowerShell: `.\mvnw.cmd`). Nếu chưa có wrapper và Maven đã cài, dùng `mvn`.

### 7.1. Chỉ chạy lớp pass

```bash
./mvnw -Dtest=TotalCalculatorTest test
```

Với đúng source ở trên và không có lỗi môi trường, Surefire sẽ chạy 2 tests thuộc `TotalCalculatorTest`; kết quả dự kiến:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **các dòng tóm tắt cần tìm**, không phải nguyên văn toàn bộ console output. Các log Maven/plugin, thời gian chạy và định dạng log có thể khác.

### 7.2. Chạy tất cả và cố ý nhận failure

```bash
./mvnw test
```

Surefire phát hiện cả hai class theo mẫu `*Test`. Kết quả dự kiến trong ví dụ:

```text
Tests run: 3, Failures: 1, Errors: 0, Skipped: 0
BUILD FAILURE
```

Phương thức fail là `TotalCalculatorRegressionTest.detectsWrongExpectation`. Vùng log quan trọng có thể chứa:

```text
org.opentest4j.AssertionFailedError: expected: <130> but was: <120>
```

Dòng lỗi assertion trên thể hiện **nội dung có ý nghĩa cố định** trong ví dụ; vị trí stack trace, thời gian chạy và chi tiết console phụ thuộc phiên bản runner/JUnit. Đọc stack trace tới **file Java và dòng chứa `assertEquals`**, không chỉ nhìn exception class.

### 7.3. Chạy riêng lớp lỗi để sửa nhanh

```bash
./mvnw -Dtest=TotalCalculatorRegressionTest test
```

Đọc báo cáo:

```text
target/surefire-reports/
├── TEST-com.example.testing.TotalCalculatorRegressionTest.xml
└── com.example.testing.TotalCalculatorRegressionTest.txt
```

Dưới report directory thường có thêm file cho class pass, log/stream nếu fork JVM gặp sự cố, hoặc report từ lần chạy trước. **Không cộng tất cả report cũ** để suy số test của lần chạy hiện tại nếu chưa làm sạch kết quả. Có thể dùng `./mvnw clean test` để xóa output cũ và chạy lại khi cần đối chiếu sạch.

### 7.4. Sửa expected value và chạy lại đầy đủ

Trong `TotalCalculatorRegressionTest.java`, thay:

```java
assertEquals(130, calculator.total(100, 20));
```

thành:

```java
assertEquals(120, calculator.total(100, 20));
```

Sau đó:

```bash
./mvnw -Dtest=TotalCalculatorRegressionTest test
./mvnw clean verify
```

Kết quả dự kiến của suite Surefire khi tất cả các test trên đều chạy sau khi sửa:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

`verify` chạy được không còn phụ thuộc các bước build bổ sung của dự án; nếu sau này thêm Failsafe hoặc integration tests, phải tính cả chúng. **Đừng tự động sửa assertion để “làm xanh” test trong dự án thật**: chỉ thay expected value khi tài liệu yêu cầu/thực tế nghiệp vụ cho thấy expected ban đầu sai.

## 8. Đọc báo cáo Surefire/Failsafe từng bước

Maven Surefire báo cáo thường có hai định dạng:

- `target/surefire-reports/com.example.testing.TotalCalculatorRegressionTest.txt`: văn bản tóm tắt và stack trace, đọc nhanh bằng editor/terminal.
- `target/surefire-reports/TEST-com.example.testing.TotalCalculatorRegressionTest.xml`: XML theo định dạng test report, tiện cho CI/Jenkins/GitHub Actions hoặc công cụ tổng hợp.

### 8.1. Trường nào quan trọng trong XML?

Một test failure thường có cấu trúc **minh họa rút gọn**:

```xml
<testsuite name="com.example.testing.TotalCalculatorRegressionTest"
           tests="1" errors="0" skipped="0" failures="1">
    <testcase name="detectsWrongExpectation"
              classname="com.example.testing.TotalCalculatorRegressionTest">
        <failure type="org.opentest4j.AssertionFailedError"
                 message="expected: &lt;130&gt; but was: &lt;120&gt;">
            <!-- Stack trace; vị trí file và dòng assertEquals -->
        </failure>
    </testcase>
</testsuite>
```

Đây là **sơ đồ XML giản lược**, không phải output chính xác từng ký tự do Surefire sinh ra; XML thực có thể thêm timestamps, thời lượng, properties, CDATA và các trường khác.

Ý nghĩa:

| Trường | Cần đọc gì? |
|---|---|
| `tests` | Tổng số test case của suite được ghi |
| `failures` | Assertion thất bại so với expected value |
| `errors` | Lỗi khác khi chạy test, ví dụ exception bất ngờ hoặc lỗi setup |
| `skipped` | Test bị bỏ qua do disabled/assumption/điều kiện phù hợp |
| `testcase name` | Phương thức hoặc tên hiển thị test bị lỗi |
| `failure/error message` | Expected/actual hoặc lời nhắn exception |
| Stack trace | Lớp, method, file, line dẫn tới failure |
| `time` | Thời gian chạy; dùng chẩn đoán slow test nhưng không đủ để kết luận bottleneck |

Ở một số framework/report, assertion cũng có thể được phân loại khác đôi chút; hãy lấy **message và stack trace** làm nguồn chính để tìm nguyên nhân.

### 8.2. Những dấu vết thất bại khác nhau

| Hiện tượng | Chẩn đoán đầu tiên |
|---|---|
| `AssertionFailedError: expected ... but was ...` | So đặc tả/test data với actual result; xem assertion line |
| `NullPointerException` trong test | Xem lỗi xuất phát từ test setup, mock chưa chuẩn bị hay mã sản phẩm |
| `IllegalStateException: Failed to load ApplicationContext` | Đọc chuỗi `Caused by` sâu nhất, cấu hình Spring/test slice, bean, datasource |
| `UnsatisfiedDependencyException` | Bean không được tạo hoặc thiếu dependency; xem nguyên nhân con, không chỉ exception ngoài |
| `BeanCreationException` | Cấu hình property, profile, datasource, migration, mock bị thiếu |
| `ConnectException` / timeout | Phụ thuộc external service/database/test container chưa sẵn hoặc networking |
| `NoClassDefFoundError` / `ClassNotFoundException` | Test/runtime classpath, scope, exclusions, plugin version |
| `Tests run: 0` hoặc không thấy report | Test discovery/filter/scope/task không chọn được test, không phải bằng chứng pass |
| Forked VM terminated / timeout | JVM OOM, `System.exit`, giới hạn fork/timeout, native crash; xem dump/stream file |

Lỗi Spring context thường có **nhiều lớp exception lồng nhau**. Hãy tìm `Caused by` gần nguyên nhân gốc, đặc biệt ở phần cuối chuỗi exception; đừng chỉ sửa lớp ngoài `Failed to load ApplicationContext`.

### 8.3. Quy trình xem lại từ console

1. Xác định **module/task** đang fail.
2. Tìm dòng test summary: `Tests run`, `Failures`, `Errors`, `Skipped`.
3. Tìm tên **class/method** đang fail.
4. Mở `.txt` hoặc `TEST-*.xml` đúng module dưới `surefire-reports`/`failsafe-reports`.
5. Tìm message expected/actual, stack trace và **dòng đầu tiên thuộc mã test/ứng dụng của mình**.
6. Phân biệt lỗi **assertion**, **exception**, **initialization**, **fork** và **không chọn được test**.
7. Chạy lại **test nhỏ nhất** với cùng cấu hình JDK/profile/data.
8. Sau khi sửa, chạy suite đầy đủ và xem báo cáo/CI thay vì chỉ dựa trên một test đã pass.

Có thể tạo báo cáo HTML của Surefire bằng **Maven Surefire Report Plugin** nếu đã cấu hình phù hợp. Bản thân Surefire thường ghi TXT/XML; không giả định `target/surefire-reports` đã có HTML như Gradle.

## 9. Cấu hình Gradle cho đúng ví dụ JUnit 5

Nếu dự án dùng **Gradle thay vì Maven**, giữ nguyên các class Java/JUnit trong mục 6 nhưng dùng `settings.gradle` và `build.gradle` ở root. Đây là **cấu hình Groovy DSL hoàn chỉnh cho bài học** (không nên để cả Maven và Gradle cùng chạy nếu chưa chủ động quản lý hai build riêng):

`settings.gradle`:

```groovy
rootProject.name = 'test-report-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
    }
}
```

Yêu cầu: JDK 17+, phiên bản Gradle tương thích Spring Boot 3.5 (chẳng hạn **Gradle 8.14+** trong nhánh 8.x) và Gradle Wrapper được tạo sẵn. `spring-boot-starter-test` quản lý JUnit Jupiter; `useJUnitPlatform()` là điều kiện quan trọng để task `test` chạy tests JUnit Jupiter. `junit-platform-launcher` được đưa vào test runtime classpath, phiên bản lấy từ BOM.

### 9.1. Chạy theo class, method, tất cả

```bash
# Chỉ 2 test pass
./gradlew test --tests "TotalCalculatorTest"

# Chọn một method JUnit 5
./gradlew test --tests "TotalCalculatorTest.addsShipping"

# Chỉ test sai expected (task thất bại có chủ đích)
./gradlew test --tests "TotalCalculatorRegressionTest"

# Toàn suite (1 failure có chủ đích cho tới khi sửa)
./gradlew test
```

Khi test fail, Gradle có thể in:

```text
> Task :test FAILED
There were failing tests.
See the report at: .../build/reports/tests/test/index.html
BUILD FAILED
```

Phần `...` là **đường dẫn tùy môi trường**, không phải output chuẩn xác từng ký tự. Khi đã sửa expected value thành `120`, chạy lại:

```bash
./gradlew test --rerun-tasks
./gradlew check
```

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`. Đừng thêm `--tests` ở lần cuối nếu muốn xác minh suite đầy đủ.

### 9.2. Đọc báo cáo Gradle

Cấu trúc thường gặp sau task `test`:

```text
build/
├── reports/tests/test/
│   ├── index.html
│   ├── classes/
│   └── packages/
└── test-results/test/
    ├── TEST-com.example.testing.TotalCalculatorTest.xml
    └── TEST-com.example.testing.TotalCalculatorRegressionTest.xml
```

Mở `build/reports/tests/test/index.html` bằng trình duyệt để xem:

- Tổng số **tests**, **failures**, **ignored/skipped**, thời gian và success rate.
- Tab/panel theo **class**, **package**, các test case có trạng thái failed.
- Stack trace kèm method, file và line nếu reporter thu được.
- Một số phiên bản/config cung cấp standard output/error của test để hỗ trợ chẩn đoán.

Dữ liệu XML thích hợp cho CI, có thể parse máy móc, nhưng HTML thường dễ đọc nhất khi đang sửa lỗi. Không nhầm báo cáo của `:service:test` với `:other-module:test`; mỗi task/module có thư mục riêng.

**Nếu report HTML chưa được tạo**, kiểm tra task `test` thật sự chạy chưa, cấu hình `reports.html.required`, quyền ghi `build` hoặc nơi report đã bị đổi trong build script. `--stacktrace` báo chi tiết lỗi task Gradle nhưng không thay cho report JUnit.

## 10. Test được chọn theo tag, điều kiện và naming convention

JUnit Jupiter hỗ trợ `@Tag("fast")`, `@Tag("regression")`, `@Disabled`, `@EnabledOnOs`, `@EnabledIfEnvironmentVariable` và nhiều điều kiện. Chúng ảnh hưởng discovery/execution nhưng không tự chuyển thành Maven/Gradle task riêng.

| Bộ lọc | Dùng trong trường hợp |
|---|---|
| Tên class | Sửa nhanh một class có lỗi |
| Tên method | Muốn kiểm tra duy nhất một behavior; Gradle `--tests Class.method` hỗ trợ trực tiếp |
| JUnit tag | Suite nhanh/chậm/regression có chính sách rõ ràng |
| Gradle task cụ thể | `test`, `integrationTest` hoặc task riêng được khai báo |
| Maven Surefire/Failsafe | Phân tách unit và integration theo phase/config |
| Maven/Gradle module selector | Build nhiều module, chỉ chạy phần liên quan |

Một test `@Disabled` có thể được phát hiện nhưng ở trạng thái **skipped**, khác với không được discovery do filter không khớp. Một test được filter khỏi suite có thể **không xuất hiện trong report hiện tại**. Khi QA số lượng test, hãy so **kỳ vọng của suite** với số test thực sự chạy, không chỉ tổng failures = 0.

### Spring Boot @SpringBootTest khác unit test thuần

`@SpringBootTest` khởi động ApplicationContext, nên có thể chậm hơn và chịu ảnh hưởng environment/profile/bean. Đối với logic không phụ thuộc Spring, unit test Java thuần như ví dụ là lựa chọn hợp lý. Đối với controller/repository, ưu tiên slice tests thích hợp nếu chỉ cần một lớp chức năng. Với integration test cần database, message broker hoặc external service, phải quản lý lifecycle, tài nguyên và thời điểm sẵn sàng.

Vì vậy khi test fail:

- Unit test: ưu tiên inspect assertion, input/output, mock.
- Slice test: kiểm tra cấu hình slice và các bean/mock trong slice.
- `@SpringBootTest`: đọc stack trace tới nguyên nhân gốc, profile, datasource, cấu hình import.
- Integration/e2e: xem log của ứng dụng, container/service, timeouts và test data.

## 11. Các lỗi cấu hình thường gặp khi chọn và chạy test

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Maven chạy `test` nhưng 0 tests | Tên không khớp Surefire pattern hoặc thiếu engine | Kiểm tra `src/test/java`, class name và JUnit dependencies |
| `-Dtest=FooTest` báo không tìm thấy | Sai tên/package hoặc build chưa compile test | Xem tên class thực, đúng module/POM và log discovery |
| Lọc method Maven chạy khác mong đợi | Provider/phiên bản Surefire và cú pháp `#method` | Chọn cả class hoặc dùng tag; xác nhận số tests |
| Gradle `No tests found for given includes` | `--tests` pattern sai, filter khác, test method không được discover | Dùng class FQN, xem `test` config và JUnit Platform |
| Gradle `UP-TO-DATE` | Task được coi không cần chạy lại | Dùng `--rerun-tasks` khi cần quan sát một lần thực thi mới |
| Maven `BUILD SUCCESS` dù không test gì | Skip flag, không có tests hoặc bộ lọc rộng | Kiểm tra `Tests run`, `skipTests`, `maven.test.skip` |
| Chỉ một test pass nhưng CI vẫn đỏ | Suite khác fail, IT fail hoặc plugin khác | Chạy `verify`/`check` đầy đủ và đọc đúng report |
| Spring context fail | Sai profile, thiếu bean, datasource/test configuration | Đọc `Caused by` gốc, không chỉ wrapper exception |
| Test pass local, fail CI | Java version, timezone, locale, concurrency, file path, env/secrets, ngoại vi | Đối chiếu JDK, args, profile, dữ liệu và logs |
| Test fail ngẫu nhiên | Shared state, thứ tự test, race, thời gian, dịch vụ ngoài | Chạy lại có kiểm soát, cô lập trạng thái, không chỉ dùng retry |
| Đọc nhầm report cũ | Task chưa chạy hoặc cache/output chưa được dọn | Xác nhận timestamp/log, dùng clean hoặc rerun phù hợp |
| Gradle không tạo HTML | Report disabled hoặc task không chạy | Kiểm tra `reports.html.required` và đúng thư mục module |
| Maven có Failsafe nhưng không chạy IT | Chưa bind goals hoặc chỉ chạy `test` | Cấu hình Failsafe rồi chạy `verify` |
| CI báo failure khi local nhìn thấy 3 test pass | Chạy khác task/module/profile hoặc test suite nhiều hơn | Đối chiếu command, test selectors, XML/HTML artifacts |

### Thế nào là flaky test?

**Flaky test** là test có thể pass hoặc fail khi code không đổi vì môi trường, timing, thứ tự, concurrency hoặc dữ liệu. Surefire có cơ chế chạy lại failing tests (`surefire.rerunFailingTestsCount` ở phiên bản hỗ trợ), nhưng retry **không chữa nguyên nhân gốc** và có thể làm mất tín hiệu thất bại nếu chỉ xem trạng thái cuối.

Khi cần triage flaky:
1. Ghi lại test class/method, seed, JDK, runner, cấu hình CI và thời điểm.
2. Chạy riêng test và chạy cùng suite (để phát hiện phụ thuộc thứ tự).
3. Kiểm tra shared database/files, clock, network, parallelism và mock tĩnh.
4. Thu thập report từng lần retry; không xóa bằng chứng.
5. Sửa tính không xác định rồi chạy lại suite đầy đủ.

## 12. Quy trình kiểm tra bản dựng trước khi merge/release

1. **Tái hiện nhỏ:** chọn class/method/tag của test lỗi.
2. **Giải thích lỗi:** mở report, đối chiếu expected/actual và stack trace.
3. **Sửa nguyên nhân:** thay logic hoặc assertion khi đã xác nhận hợp đồng đúng.
4. **Xác minh cục bộ:** chạy lại đúng test và ghi nhận pass.
5. **Chạy nhóm liên quan:** service tests, slice tests, database tests...
6. **Chạy suite được yêu cầu:** Maven `verify` hoặc Gradle `check`/`build` theo cấu hình dự án.
7. **Kiểm tra số lượng:** tổng tests/failed/errors/skipped có hợp lý không?
8. **Lưu report CI:** tải/publish JUnit XML, HTML nếu cần, để lỗi được truy vết.
9. **Không che thất bại:** tránh skip flags, `ignoreFailures`, `testFailureIgnore` hoặc filter chỉ chọn những test pass.
10. **Kiểm tra môi trường:** JDK, build tool version, test profiles, external services, credentials.

**Checklist tự đánh giá:**

- [ ] Biết đang chọn test bằng Surefire `-Dtest` hay Gradle `--tests`.
- [ ] Biết class name và method name có được framework discover không.
- [ ] Đã xem số test thực sự chạy, không chỉ thấy build xanh.
- [ ] Đã tìm đúng báo cáo `target/surefire-reports`, `target/failsafe-reports` hoặc `build/reports/tests/test`.
- [ ] Đã đọc tên testcase, assertion/exception và stack trace đến dòng trong project.
- [ ] Đã phân biệt assertion thất bại, lỗi runtime, lỗi Spring context, lỗi test discovery.
- [ ] Sau khi sửa đã chạy lại **toàn bộ test suite cần thiết**, không chỉ một method.
- [ ] Không bỏ qua integration tests chỉ vì Surefire unit tests pass.
- [ ] Không publish thông tin nhạy cảm từ test logs, report hoặc stack trace.

**Ghi nhớ:** Lọc test giúp vòng phát triển nhanh hơn, **báo cáo giúp định vị lỗi chính xác**, và chỉ **chạy lại đúng suite/phase/task bắt buộc** mới chứng minh bản dựng đủ điều kiện tiếp tục.

### Tài liệu tham khảo chính thức

- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Maven Surefire — Test Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Surefire — Introduction and Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe — Integration Tests and Reports](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)