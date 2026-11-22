# JUnit Jupiter: Assumption, điều kiện môi trường và lý do bỏ qua test

## 1. Mục tiêu và ba kết quả rất dễ nhầm

Khi triển khai kiểm thử tự động với **JUnit Jupiter** trong dự án Spring Boot, có những test **chỉ có ý nghĩa ở một môi trường nhất định**: chạy trên Linux, cần phiên bản Java phù hợp, cần một biến môi trường opt-in hoặc cần hạ tầng tùy chọn. JUnit cho phép không thực thi test trong những hoàn cảnh này, nhưng cần phân biệt đúng **FAILED**, **ABORTED** và **DISABLED/SKIPPED**.

| Trạng thái ở mức JUnit Platform | Khi nào xảy ra? | Mã test/lifecycle đã chạy chưa? | Ý nghĩa cần hiểu |
| --- | --- | --- | --- |
| **SUCCESSFUL / PASSED** | Các assertion thành công, không có lỗi bất ngờ | Có (trừ một số dạng test đặc biệt) | Test **đã thực thi và đạt** |
| **FAILED** | Assertion sai hoặc một exception không được xử lý hợp lệ | Thường đã chạy ít nhất một phần | Có vấn đề cần điều tra; pipeline thường phải coi là đỏ |
| **ABORTED** | `Assumptions.assumeTrue(false)`, `assumeFalse(true)` hoặc `TestAbortedException` | Đã bắt đầu thực thi hoặc chạy đến assumption | Điều kiện tiên quyết **không thỏa**, nên không đủ bằng chứng kết luận đúng/sai |
| **DISABLED / SKIPPED** | `@Disabled` hoặc `ExecutionCondition` loại test trước thực thi | Test method và method-level lifecycle không chạy | Test **không được chọn chạy** vì chính sách/điều kiện |

**Nguyên tắc chính:** Không đồng nhất “không FAIL” với “đã được kiểm chứng”. Một test bị ABORTED hay DISABLED không chứng minh tính năng hoạt động. Các công cụ hiển thị như Maven Surefire, Gradle, IDE, JUnit XML hay dashboard CI có thể gộp ABORTED vào nhóm “skipped”; hãy xem thông tin chi tiết, lý do và số lượng test thực sự chạy.

Ví dụ:

- Máy local không có môi trường thử nghiệm tùy chọn → một integration test có thể ABORTED theo assumption hoặc DISABLED theo annotation.
- Logic tính thuế sai trong mọi môi trường hỗ trợ → phải **FAILED** bằng assertion, không được dùng assumption để che lỗi.
- Tính năng phụ thuộc Linux → sử dụng annotation điều kiện OS để test không chạy trên Windows.
- Test tạm vô hiệu hóa vì lỗi đã được ghi nhận → `@Disabled("... lý do, issue, thời điểm xem lại ...")`, theo dõi thời gian để kích hoạt lại.

## 2. Assumption là gì? Khác assertion ra sao?

Assumption là **giả định về môi trường hoặc điều kiện tiên quyết của phép thử**, không phải một yêu cầu nghiệp vụ của hệ thống. Các API chính nằm trong `org.junit.jupiter.api.Assumptions`:

- `assumeTrue(boolean condition)` / `assumeTrue(condition, message)` / overload lambda: **tiếp tục** nếu điều kiện đúng; **ABORTED** nếu sai.
- `assumeFalse(boolean condition)`: tiếp tục nếu điều kiện sai; ABORTED nếu đúng.
- `assumingThat(boolean condition, Executable block)`: **chỉ chạy block** nếu điều kiện đúng; nếu sai thì bỏ qua **block**, nhưng test vẫn tiếp tục và có thể PASS.
- `Assumptions.abort(...)` (có trong các bản JUnit Jupiter mới) chủ động abort trong trường hợp cần thiết; khi hỗ trợ khác nhau giữa versions, `assumeTrue(false, reason)` dễ hiểu và tương thích rộng hơn.

Khi `assumeTrue` hoặc `assumeFalse` không thỏa, JUnit Jupiter dùng `org.opentest4j.TestAbortedException` để biểu thị test bị hủy. Assertion như `assertTrue` lại ném lỗi assertion, làm test FAILED. **Không gọi assumption để kiểm tra behavior phải luôn đúng.**

### Ví dụ cùng một điều kiện nhưng kết quả khác nhau

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import org.junit.jupiter.api.Test;

class AssumptionOrAssertionTest {

    @Test
    void optionalEnvironmentMayAbort() {
        boolean ready = false; // Giả lập môi trường tùy chọn chưa có.
        assumeTrue(ready, "Môi trường tùy chọn chưa được cung cấp");
        assertEquals(4, 2 + 2); // Không chạy khi ready=false.
    }

    @Test
    void requiredBehaviorMustFail() {
        int calculated = 3; // Giả lập một bug nghiệp vụ.
        assertEquals(4, calculated); // FAILED, tuyệt đối không skip.
    }
}
```

Đây là một ví dụ **cố ý có 1 ABORTED và 1 FAILED để giải thích**, không phải bộ test dùng nguyên trạng cho CI. Trong dự án thật, điều kiện `ready` phải xuất phát từ cấu hình đã xác thực, còn `calculated` là kết quả thực từ mã ứng dụng. Nếu đưa fixture cố ý FAIL vào CI sản xuất, pipeline sẽ đỏ đúng thiết kế.

### Khi nào kiểm tra assumption?

Nên dùng khi **không thể đưa ra kết luận hữu ích** vì môi trường tùy chọn chưa có. Ví dụ một test smoke kiểm tra kết nối tới sandbox được cấp riêng. Nếu server sandbox là phụ thuộc **bắt buộc** của pipeline phát hành, việc mất kết nối phải FAIL để báo hạ tầng không đáp ứng, thay vì luôn abort và khiến dashboard trông “xanh”.

Không dùng assumption để xử lý: kết quả nghiệp vụ không đúng, HTTP 500 bất ngờ, repository lưu sai, message không được phát, dữ liệu sai schema hoặc test luôn timeout. Đó là sự cố cần làm rõ.

## 3. `assumingThat` khác hẳn `assumeTrue`

Một lỗi phổ biến là nghĩ `assumingThat(false, block)` khiến **toàn test ABORTED**. Thực tế nó chỉ không thực hiện block; câu lệnh sau vẫn chạy.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assumptions.assumingThat;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class AssumingThatDemoTest {

    @Test
    void skipsOnlyOptionalBlock() {
        AtomicBoolean optionalBlockRan = new AtomicBoolean(false);

        assumingThat(false, () -> optionalBlockRan.set(true));

        assertFalse(optionalBlockRan.get());
        assertEquals(9, 3 * 3); // Vẫn chạy; test PASS.
    }
}
```

Nên dùng `assumingThat` khi phần kiểm chứng bổ sung thực sự **tùy chọn**, trong khi phần còn lại vẫn có giá trị. Không dùng nó để bao quanh assertion quan trọng nhất của test: lúc đó test có thể báo PASS dù chưa xác minh điều gì thiết yếu.

Nếu mục đích là bỏ **toàn bộ test** trong môi trường không hợp lệ, dùng `assumeTrue`/`assumeFalse` hoặc một annotation điều kiện.

## 4. Hai nhóm cơ chế khác nhau: runtime assumption và điều kiện thực thi

JUnit Jupiter triển khai cơ chế **`ExecutionCondition`** để quyết định bật/tắt test class hoặc test method **trước khi gọi test method**. Các annotation tích hợp nằm chủ yếu ở `org.junit.jupiter.api.condition`.

| Nhu cầu | Cơ chế | Kết quả khi không thỏa |
| --- | --- | --- |
| Chỉ chạy trên Linux/macOS, hoặc không chạy trên Windows | `@EnabledOnOs` / `@DisabledOnOs` | DISABLED |
| Chỉ chạy trên Java 17, 21 hoặc khoảng JRE nhất định | `@EnabledOnJre`, `@DisabledOnJre`, `@EnabledForJreRange`, `@DisabledForJreRange` | DISABLED |
| Chỉ chạy khi biến môi trường được đặt đúng | `@EnabledIfEnvironmentVariable` / `@DisabledIfEnvironmentVariable` | DISABLED |
| Phụ thuộc giá trị JVM system property | `@EnabledIfSystemProperty` / `@DisabledIfSystemProperty` | DISABLED |
| Điều kiện boolean tính được bằng method | `@EnabledIf` / `@DisabledIf` | DISABLED |
| Tạm vô hiệu hóa rõ ràng, chưa phụ thuộc môi trường | `@Disabled("lý do")` | DISABLED |
| Điều kiện chỉ biết trong lúc chạy test | `assumeTrue` / `assumeFalse` | ABORTED |
| Chỉ có một đoạn test tùy chọn | `assumingThat` | Bỏ block, test tiếp tục |

Ưu tiên **annotation có sẵn** nếu điều kiện là thông tin OS/JRE/config rõ ràng trước khi test bắt đầu. Dùng **assumption** khi điều kiện cần tính trong test (ví dụ dữ liệu phát sinh ở bước setup). Các điều kiện tùy biến phức tạp có thể viết một `ExecutionCondition` riêng, nhưng không cần làm vậy khi annotation tích hợp đã đủ.

### 4.1. Bật/tắt test dựa trên hệ điều hành

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.DisabledOnOs;
import org.junit.jupiter.api.condition.OS;

class OsSpecificTest {

    @Test
    @EnabledOnOs(value = {OS.LINUX, OS.MAC},
                 disabledReason = "Chỉ có công cụ này trên Unix-like CI")
    void usesUnixTool() {
        // Kiểm tra thực tế với công cụ dành cho Unix.
    }

    @Test
    @DisabledOnOs(value = OS.WINDOWS,
                  disabledReason = "Chưa hỗ trợ executable tương ứng trên Windows")
    void worksExceptOnWindows() {
        // Assertion ứng dụng thực tế.
    }
}
```

Hai ví dụ trên minh họa cú pháp điều kiện; phần thân test còn phải chứa assertion có giá trị. Không nên biến tất cả tests thành Linux-only chỉ vì môi trường developer thường là Linux: cần bảo đảm giới hạn OS thực sự thuộc yêu cầu.

### 4.2. Bật/tắt test dựa trên JRE

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledForJreRange;
import org.junit.jupiter.api.condition.EnabledOnJre;
import org.junit.jupiter.api.condition.JRE;

class JavaVersionTest {

    @Test
    @EnabledOnJre(JRE.JAVA_17)
    void specificJava17Behavior() {
        // Test chỉ áp dụng cho Java 17.
    }

    @Test
    @EnabledForJreRange(min = JRE.JAVA_17)
    void worksOnJava17AndNewer() {
        // Test trên Java >= 17.
    }
}
```

Các enum `JRE.JAVA_xx` có sẵn tùy phiên bản JUnit, nên khi nâng JDK lên major mới không được giả định enum tương ứng đã tồn tại. JUnit các phiên bản mới có tham số `minVersion`/`maxVersion`/`versions` khi cần số phiên bản JDK chưa có trong enum. Nếu sử dụng JUnit 6, Java baseline là **17**, và vài lựa chọn JRE cũ trở nên thừa hoặc deprecated.

### 4.3. Biến môi trường so với system property

**Environment variable** đến từ môi trường process của hệ điều hành, đọc bằng `System.getenv("NAME")`. **System property** là thuộc tính JVM, đọc bằng `System.getProperty("name")`; đặt trực tiếp bằng `-Dname=value` hoặc qua cấu hình test task. Không được dùng chúng thay cho nhau.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.DisabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

class ConfigurationConditionTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_SANDBOX_TESTS",
        matches = "true",
        disabledReason = "Sandbox tests chỉ được bật khi đã opt-in")
    void runsWithSandboxOptIn() {
        // Test sandbox thực tế.
    }

    @Test
    @DisabledIfEnvironmentVariable(
        named = "CI",
        matches = "(?i)true",
        disabledReason = "Test này chỉ kiểm tra công cụ đồ họa local")
    void localGraphicsOnly() {
        // Test GUI local, không phù hợp CI headless.
    }

    @Test
    @EnabledIfSystemProperty(
        named = "test.profile",
        matches = "sandbox",
        disabledReason = "Chỉ chạy trong cấu hình test.profile=sandbox")
    void runsWithJvmProperty() {
        // Test thật của profile sandbox.
    }
}
```

Thuộc tính `matches` được hiểu là **biểu thức chính quy (regex)**. `"true"` và `"(?i)true"` có ý nghĩa khác về chữ hoa/thường; tên biến môi trường sai hoặc biến không tồn tại thường làm `@EnabledIf...` không thỏa. Khi áp dụng `@DisabledIfEnvironmentVariable`, biến không tồn tại sẽ **không** kích hoạt điều kiện disable; nếu test chỉ nên chạy khi được phép rõ ràng, dùng `@EnabledIfEnvironmentVariable` (opt-in) sẽ an toàn hơn.

Cảnh báo: `@EnabledIf` của JUnit (`org.junit.jupiter.api.condition.EnabledIf`) **khác** annotation `@EnabledIf` của Spring Test ở `org.springframework.test.context.junit.jupiter.EnabledIf`. Khi IDE auto-import, đối chiếu chính xác package và loại biểu thức mà annotation mong đợi.

### 4.4. Điều kiện bằng một method và custom `ExecutionCondition`

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;

class ConditionMethodTest {

    @Test
    @EnabledIf("hasRequiredProperty")
    void runsOnlyWhenPropertyExists() {
        // Test thực tế.
    }

    static boolean hasRequiredProperty() {
        return System.getProperty("app.test.optin") != null;
    }
}
```

Đối với `@EnabledIf`/`@DisabledIf`, method trả `boolean`, có thể không tham số hoặc nhận một `ExtensionContext`. Method điều kiện phải `static` trong một số trường hợp, gồm khi đặt annotation ở **class-level**, với parameterized test/test template hoặc method nằm ở lớp bên ngoài. Nếu cần logic phong phú cho cả nhóm test, cân nhắc custom `ExecutionCondition` để cung cấp lý do disable rõ ràng và tập trung; không đặt side effect phức tạp trong điều kiện.

## 5. `@Disabled` và cách ghi lý do có thể hành động

`@Disabled` áp dụng trên test method hoặc class. Nếu đặt ở class, toàn bộ test methods thuộc class đó bị vô hiệu hóa. Ví dụ:

```java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class PendingFixTest {

    @Test
    @Disabled("ISSUE-142: kết quả phụ thuộc hệ thống ngoài chưa ổn định; xem lại 2026-12-01")
    void downstreamContract() {
        // Assertion sau khi sửa ISSUE-142.
    }
}
```

Chuỗi trong `@Disabled` nên trả lời đủ ba ý: **vì sao vô hiệu hóa**, **nơi theo dõi**, và **khi nào/điều kiện nào bật lại**. “flaky”, “chạy không được”, “TODO”, “broken” hoặc để trống đều khó quản lý. Lý do mẫu ở trên minh họa cú pháp; mã issue và ngày trong dự án thật phải là thông tin có thật, không sao chép nguyên giá trị ví dụ.

Nên ưu tiên sửa root cause của flaky tests. Với lỗi chưa sửa, tùy chính sách dự án có thể dùng cơ chế quarantine với owner, issue, thời hạn và job riêng báo đỏ nếu test quarantine vẫn FAIL. Không biến `@Disabled` thành nơi giấu regression. Nếu test là requirement bắt buộc cho release, việc tắt mà không có biện pháp coverage thay thế có thể khiến chất lượng bị đánh giá sai.

### `@Disabled` có ngăn mọi lifecycle hook không?

Nếu **một test method** bị disabled, method đó và các lifecycle callback tương ứng `@BeforeEach`/`@AfterEach` của method **không được gọi**. Tuy vậy, việc một method bị disabled **không bảo đảm** class sẽ không được khởi tạo hoặc class-level lifecycle `@BeforeAll`/`@AfterAll` không chạy. Khác với `assumeTrue` được gọi bên trong test: tại thời điểm abort, phần setup trước đó đã có thể chạy và side effect phải được dọn đúng cách.

Cần đặt tài nguyên ngoài (file, server, DB transaction) trong fixture có cleanup đáng tin; không dùng assumption làm thay thế cho cơ chế đóng tài nguyên. Nếu một assertion khác hoặc lỗi teardown cũng xảy ra, kết quả cuối cùng có thể **FAILED** dù trước đó đã có failed assumption.

## 6. Dự án Maven Java 17 có thể chạy và quan sát đủ trạng thái

Để kiểm chứng cơ chế với mã thực thi, tạo một dự án Maven đơn giản **không cần Spring context**. Ví dụ dùng JUnit Jupiter 5.12.2, Java 17, Maven Surefire 3.5.2. Nếu sử dụng **Spring Boot** thật, thay JUnit dependency trực tiếp bằng `spring-boot-starter-test` và để Spring Boot BOM quản lý JUnit; không ép version 5.12.2 lên một dự án Boot 4 đang dùng JUnit 6.

Cấu trúc tệp:

```text
junit-assumptions-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── EnvironmentConditionsTest.java
```

### 6.1. `pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>junit-assumptions-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. `src/test/java/example/EnvironmentConditionsTest.java`

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.junit.jupiter.api.Assumptions.assumingThat;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

class EnvironmentConditionsTest {

    @Test
    void basicUnitTestAlwaysRuns() {
        assertEquals(4, 2 + 2);
    }

    @Test
    void optionalTestAbortsWhenNotOptedIn() {
        boolean optIn = "true".equalsIgnoreCase(
                System.getenv("RUN_OPTIONAL_TESTS"));

        assumeTrue(optIn,
                () -> "Thiếu RUN_OPTIONAL_TESTS=true cho optional test");

        assertEquals("ok", "o" + "k");
    }

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_OPTIONAL_TESTS",
        matches = "(?i)true",
        disabledReason = "Chỉ chạy khi RUN_OPTIONAL_TESTS=true")
    void optionalTestSkippedBeforeExecutionWhenNotOptedIn() {
        assertEquals(10, 5 + 5);
    }

    @Test
    @EnabledOnOs(
        value = OS.LINUX,
        disabledReason = "Ví dụ chỉ chạy trên Linux")
    void linuxOnlyTest() {
        assertNotNull(System.getProperty("os.name"));
    }

    @Test
    @Disabled("Ví dụ hướng dẫn @Disabled; không dùng làm coverage chính")
    void sampleExplicitlyDisabledTest() {
        // Test method này không được thực thi.
    }

    @Test
    void assumingThatSkipsOnlyTheOptionalBlock() {
        AtomicBoolean executed = new AtomicBoolean(false);

        assumingThat(false, () -> executed.set(true));

        assertFalse(executed.get());
        assertEquals(9, 3 * 3);
    }
}
```

Các tên class, file, package khớp nhau; không có `@SpringBootTest`, không cần Docker, database hoặc network. Các assertion phần demo là xác định; kết quả thay đổi **có chủ đích** theo môi trường.

### 6.3. Chạy và đọc kết quả

Trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Trên bash, bật cả hai test opt-in:

```bash
RUN_OPTIONAL_TESTS=true mvn test
```

Trong PowerShell:

```powershell
$env:RUN_OPTIONAL_TESTS = 'true'
mvn test
Remove-Item Env:RUN_OPTIONAL_TESTS
```

Bảng kết quả kỳ vọng **theo từng method**:

| Test method | Khi không có `RUN_OPTIONAL_TESTS` trên Linux | Khi `RUN_OPTIONAL_TESTS=true` trên Linux |
| --- | --- | --- |
| `basicUnitTestAlwaysRuns` | PASSED | PASSED |
| `optionalTestAbortsWhenNotOptedIn` | ABORTED (failed assumption) | PASSED |
| `optionalTestSkippedBeforeExecutionWhenNotOptedIn` | DISABLED (condition) | PASSED |
| `linuxOnlyTest` | PASSED | PASSED |
| `sampleExplicitlyDisabledTest` | DISABLED | DISABLED |
| `assumingThatSkipsOnlyTheOptionalBlock` | PASSED | PASSED |

Trên Windows, `linuxOnlyTest` cũng bị DISABLED. Không có stdout ứng dụng cố định: class không gọi `System.out.println`. **Không chốt một dòng output Maven duy nhất** vì Surefire/IDE có thể tổng hợp aborted và disabled khác nhau; điều quan trọng là status mỗi method và lý do. Các báo cáo Maven được tạo trong `target/surefire-reports/` khi plugin test chạy, có thể dùng để điều tra các test không thực thi.

Nếu muốn tránh test luôn disabled xuất hiện ở project thật, bỏ method `sampleExplicitlyDisabledTest` sau khi học xong. Nếu muốn tất cả test thực hiện trong CI, đặt `RUN_OPTIONAL_TESTS=true` trong môi trường test có sandbox **đủ điều kiện**, chứ không đặt biến chỉ để làm tăng tỷ lệ PASS.

## 7. Áp dụng trong Spring Boot: kiểm thử tùy chọn và kiểm thử bắt buộc

Ở dự án Spring Boot, thường đã khai báo:

**Maven (đặt trong `<dependencies>` của `pom.xml`):**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

**Gradle Kotlin DSL:**

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
tasks.withType<Test> {
    useJUnitPlatform()
}
```

JUnit Jupiter có trong starter chung; nhiều dự án Spring Boot 3.x sử dụng JUnit 5, trong khi Spring Boot 4.x dùng hệ JUnit 6. API assumptions và điều kiện trình bày ở đây vẫn sử dụng package `org.junit.jupiter.api` và `org.junit.jupiter.api.condition`. Cần kiểm tra version thực tế của project thay vì chép số version ở ví dụ Maven độc lập.

### 7.1. Trường hợp nên dùng assumption trong integration test

Một test smoke **tùy chọn**, chỉ kiểm tra kết nối đến sandbox nội bộ khi môi trường cho phép:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import org.junit.jupiter.api.Test;

class OptionalSandboxTest {

    @Test
    void validatesOptInBeforeCallingSandbox() {
        String enabled = System.getenv("RUN_SANDBOX_TESTS");
        String sandboxUrl = System.getenv("SANDBOX_URL");

        assumeTrue("true".equalsIgnoreCase(enabled),
                "Chưa bật RUN_SANDBOX_TESTS");
        assumeTrue(sandboxUrl != null && !sandboxUrl.isBlank(),
                "Chưa đặt SANDBOX_URL");

        assertTrue(sandboxUrl.startsWith("https://"));
        // Nếu có HTTP client thực: gọi sandbox và assert kết quả theo contract.
    }
}
```

Đây là **ví dụ runnable chỉ kiểm tra cấu hình opt-in/URL**; chưa kiểm tra khả năng kết nối hoặc business behavior. Nếu bổ sung HTTP call, cần giới hạn timeout, verify status/body và xử lý timeout theo SLA. Khi sandbox đã được yêu cầu bắt buộc ở một CI job, thiếu endpoint/timeout nên FAIL có chủ đích theo quy định pipeline đó; điều chỉnh giả định thay vì để test abort âm thầm.

### 7.2. Điều kiện có thể áp dụng ở class-level

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(
    named = "RUN_DB_INTEGRATION_TESTS",
    matches = "true",
    disabledReason = "DB integration chạy ở job riêng")
class DatabaseIntegrationTest {

    @Test
    void testsDatabaseContract() {
        // Test database thật, ví dụ qua Testcontainers.
    }
}
```

Đoạn trên minh họa **điều kiện class-level**; chưa phải test DB hoàn chỉnh. Khi biến môi trường không đúng, cả class bị disabled. Một test DB thực sự cần repository/driver/migration/schema và có thể cần Testcontainers. Không viết assumption “Docker không chạy thì PASS” cho job CI được giao trách nhiệm kiểm chứng DB: nếu hạ tầng bắt buộc không khả dụng, đó là lỗi job hoặc cấu hình cần xử lý.

### 7.3. Chọn phương án với Testcontainers, file hệ thống và credential

| Điều kiện | Có thể tùy chọn khi nào? | Cách xử lý nên cân nhắc |
| --- | --- | --- |
| Container runtime không có trên máy developer | Test integration chạy ở CI riêng đã bảo đảm runtime | Annotation opt-in cho local; CI integration phải fail khi Docker cần thiết mà thiếu |
| Sandbox API không được cấp cho local | Job smoke riêng được cấp URL/credential | Opt-in + kiểm tra cấu hình; không in secret vào reason/log |
| File dữ liệu mẫu chỉ có trong một job | Test thực sự chỉ thuộc job đó | Condition theo môi trường/đường dẫn; nếu file là test fixture phải có trong repo thì thiếu file nên FAIL |
| Feature flag chưa bật | Contract chỉ áp dụng khi flag bật | Condition theo flag đã công bố; job riêng xác minh tính năng khi bật |
| JDK/OS không hỗ trợ | Hợp đồng chính thức chỉ cam kết môi trường được hỗ trợ | Annotation OS/JRE, ghi lý do; ít nhất một job kiểm thử trên môi trường được hỗ trợ |
| Lỗi ứng dụng, HTTP 500, SQL lỗi | Không phải “điều kiện tùy chọn” | Assertion/exception FAILED, sửa nguyên nhân hoặc theo dõi issue rõ ràng |

Không sử dụng assumption như một `catch` chung cho mọi exception:

```java
// PHẢN VÍ DỤ: đừng biến lỗi hệ thống thành skipped test.
try {
    executeRequiredOperation();
} catch (Exception ex) {
    assumeTrue(false, "Bỏ qua vì operation lỗi");
}
```

Đoạn trên **chỉ minh họa anti-pattern** và không biên dịch độc lập (thiếu `executeRequiredOperation()`). Nếu operation thuộc phạm vi test bắt buộc, để exception làm test FAILED hoặc assert ngoại lệ dự kiến. Nếu chỉ kiểm tra một phụ thuộc tùy chọn, nên kiểm tra điều kiện opt-in trước khi gọi operation và định nghĩa rõ khi nào quyền abort còn hợp lệ.

## 8. Parameterized test, nested test và lifecycle: các bẫy phổ biến

### 8.1. Assumption trong `@ParameterizedTest`

Nếu một invocation không thỏa assumption, invocation đó có thể ABORTED trong khi invocation khác vẫn PASSED. Vì vậy một parameterized test có 10 input nhưng 9 aborted chỉ chứng minh được **1 input**. Không báo “10 trường hợp đã kiểm chứng”.

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ParameterAssumptionTest {

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3})
    void verifiesOnlySupportedSamples(int value) {
        assumeTrue(value > 0, "Mẫu 0 không thuộc miền test này");
        assertTrue(value * 2 > value);
    }
}
```

Ở fixture minh họa này, invocation `0` ABORTED, còn `1,2,3` PASSED. Trong bài test nghiệp vụ thật, **giá trị đầu vào không hợp lệ phải được kiểm thử như một case lỗi có assertion**, không tự abort nếu nó thuộc requirement. Dùng hai bộ test “valid data” và “invalid data” là lựa chọn rõ hơn khi có thể.

### 8.2. Lifecycle

- Điều kiện annotation được xét trước khi gọi test method; test disabled không thực thi `@BeforeEach`/`@AfterEach` tương ứng với method. Nhưng class-level setup vẫn có thể xảy ra nếu class còn test khác.
- Assumption nằm trong test method: `@BeforeEach` có thể đã khởi tạo dữ liệu hoặc kết nối trước khi abort. Cleanup/rollback phải vẫn đúng và an toàn.
- Một exception/assertion failure từ lifecycle có thể khiến kết quả FAILED dù assumption đã abort. Đừng dựa vào thứ tự lỗi để giấu lỗi cleanup.
- Nếu việc kiểm tra môi trường quá tốn kém và có thể quyết định sớm, cân nhắc condition thay cho việc khởi động cả Spring context rồi mới `assumeTrue`.
- `@Disabled` ở class-level áp dụng cho tất cả tests của class; với `@Nested` hoặc lớp kế thừa, cần đọc chính xác semantics cho phiên bản đang dùng thay vì suy đoán inheritance.

### 8.3. Nhiều điều kiện cùng lúc

Có thể kết hợp điều kiện OS và env var:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.condition.OS;

class CombinedConditionsTest {

    @Test
    @EnabledOnOs(OS.LINUX)
    @EnabledIfEnvironmentVariable(named = "RUN_OPTIONAL_TESTS", matches = "true")
    void onLinuxWhenExplicitlyEnabled() {
        // Test thật.
    }
}
```

Test chỉ được bật khi **tất cả điều kiện enabled được thỏa**. Nếu một condition disable, JUnit có thể dừng đánh giá các condition còn lại; **không bảo đảm** mọi điều kiện đều được chạy hoặc gom mọi lý do vào report. Vì vậy đặt logic phức tạp, có side effect hoặc phụ thuộc thứ tự trong condition là thiết kế không tốt.

`@Tag("integration")` và filter `includeTags`/`excludeTags` giúp **chọn** tập test khi build. Test bị filter không nhất thiết xuất hiện dưới dạng DISABLED trong báo cáo vì JUnit có thể không đưa test vào test plan. Đừng dùng số “skipped” để suy ra toàn bộ test không được chạy bởi filters.

## 9. Thiết kế lý do bỏ qua test cho CI có thể giám sát

Một chính sách tốt trả lời được: **test nào**, **vì sao**, **khi nào được chạy**, **ai cần xử lý**, **bằng chứng nằm ở đâu**.

| Nguyên nhân không chạy | Tình trạng mong đợi | Lý do cần ghi | Cách làm để không mất coverage |
| --- | --- | --- | --- |
| OS/JDK nằm ngoài hỗ trợ chính thức | DISABLED có điều kiện | Phiên bản/OS hỗ trợ, điều kiện chính xác | Có job CI chạy trên OS/JDK được hỗ trợ |
| Job không phải integration job | DISABLED có điều kiện/tag filter | Tên cờ opt-in, cấu hình job chịu trách nhiệm | Integration job riêng chạy đầy đủ |
| Sandbox tùy chọn vắng mặt | ABORTED hoặc DISABLED tùy thời điểm kiểm tra | Thiếu biến/cấu hình nào, cách bật | Job sandbox bắt buộc đo PASS/FAIL |
| Test tạm bị tắt vì bug đã biết | `@Disabled` | Issue, người phụ trách, mốc mở lại | Theo dõi quarantine, báo cáo số ngày disable |
| Dependency bắt buộc gặp lỗi | FAILED | Root error, stack trace/log an toàn | Sửa hạ tầng hoặc mã, không gắn assumption |
| Test bị loại bởi tag filter | Không được chọn trong test run | Filter build, cấu hình test task | Có job bao phủ tag khác |

**Nên ghi lý do đầy đủ nhưng không lộ bí mật.** Ví dụ tốt: “RUN_SANDBOX_TESTS=true chưa bật; job sandbox-integration có trách nhiệm chạy test”. Ví dụ xấu: nối vào lý do toàn bộ giá trị `SANDBOX_TOKEN`, mật khẩu, connection URL có credential hoặc dữ liệu cá nhân.

Với `@Disabled`, dùng issue tracker thay cho ghi chú rời rạc trong code. Đặt giới hạn thời gian review; cảnh báo khi số test disabled tăng hoặc test thuộc luồng phát hành không được chạy ở bất kỳ job nào.

### Ví dụ quy ước CI

- **Fast PR job:** pure unit tests và slice tests bắt buộc, không phụ thuộc Docker/network ngoài.
- **Integration job:** cấp DB/container/credentials cần thiết; bật các test integration và coi outage là lỗi hạ tầng để FAILED.
- **Platform matrix:** thử các OS/JDK mà sản phẩm cam kết hỗ trợ; annotation chỉ vô hiệu hóa đúng trường hợp không tương thích.
- **Quarantine job:** tiếp tục theo dõi test lỗi chưa sửa, có issue và deadline; không để chúng biến mất khỏi lịch chạy.

Khi đánh giá test suite, nên theo dõi cả **số test thực sự chạy**, **failed**, **aborted**, **disabled**, **filtered-out**, cùng nguyên nhân. Dashboard chỉ hiện màu xanh mà không hiện trường hợp bị bỏ qua dễ tạo cảm giác an toàn giả.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Dùng `assumeTrue(response.isSuccessful())` để “kiểm tra” HTTP endpoint | HTTP lỗi trở thành ABORTED thay vì FAILED | Dùng `assertTrue` hoặc `assertEquals` với expected HTTP contract |
| Cho rằng `assumingThat(false, ...)` làm toàn test ABORTED | Test PASS dù assertion quan trọng không chạy | Dùng `assumeTrue` nếu cả test không có ý nghĩa; nếu block optional, giữ assertion chính bên ngoài |
| Luôn đặt `assumeTrue(false)` khi gặp bất kỳ IOException | Che lỗi network/DB thật | Phân biệt optional prerequisite và dependency bắt buộc |
| Quên giá trị `RUN_*` trên CI | Integration test không chạy nhưng pipeline xanh | Cấu hình opt-in trong job; kiểm tra executed count |
| Đổi từ env var sang JVM `-D` nhưng giữ `@EnabledIfEnvironmentVariable` | Condition không tìm thấy biến | Dùng `@EnabledIfSystemProperty` hoặc truyền đúng environment variable |
| `matches="true"` trong khi CI cấp `TRUE` | Điều kiện regex không khớp | Thống nhất giá trị hoặc `(?i)true` |
| Dùng `@Disabled` mà không có lý do | Test bị quên vô thời hạn | Ghi issue + lý do + điều kiện kích hoạt lại |
| Chỉ nhìn tổng skipped count | Không biết test bị disable hay abort | Mở report từng test và các condition/assumption messages |
| Chỉ có test chạy trên Linux dù hỗ trợ Windows | Bỏ trống coverage Windows | Duy trì platform CI matrix cho OS được hỗ trợ |
| Assumption đặt sau thao tác side effect | Test abort nhưng dữ liệu đã thay đổi | Kiểm tra prerequisite sớm; cleanup/transaction an toàn |
| Annotation điều kiện import nhầm từ Spring Test | Điều kiện hoạt động khác mong muốn | Dùng `org.junit.jupiter.api.condition...` khi muốn JUnit condition |
| Một method bị disabled nhưng `@BeforeAll` vẫn thao tác phụ thuộc | Job vẫn tốn tài nguyên hoặc lỗi setup | Di chuyển setup đúng scope, điều kiện class-level khi hợp lý |

## 11. Quy trình quyết định khi viết một test mới

1. **Xác định điều cần chứng minh.** Nếu behavior bắt buộc, test phải PASS hoặc FAILED, không bị abort để né lỗi.
2. **Liệt kê prerequisite bên ngoài.** OS, JDK, config, sandbox, database, Docker, file, credential; đánh dấu **bắt buộc** hay **tùy chọn** cho job hiện tại.
3. **Chọn lúc kiểm tra.** Biết ngay từ môi trường → annotation `@Enabled...`/`@Disabled...`; cần tính trong quá trình chạy → `assumeTrue`/`assumeFalse`.
4. **Nếu chỉ có một đoạn kiểm tra tùy chọn**, dùng `assumingThat` nhưng bảo đảm phần assert chính luôn chạy.
5. **Ghi reason hữu ích**: điều kiện bị thiếu, nơi bật test, issue/mốc xử lý nếu vô hiệu hóa tạm. Không in secret.
6. **Tạo đường chạy bắt buộc cho coverage.** Nếu test bị disable trên local, phải có job nào đó chạy nó; tránh cả hệ thống không bao giờ kiểm chứng.
7. **Xem kết quả ở mức invocation.** Đặc biệt parameterized tests: kiểm tra PASS/FAILED/ABORTED/DISABLED và lọc tag; quan sát trạng thái không chỉ “BUILD SUCCESS”.
8. **Rà soát định kỳ.** Giảm skipped không có lý do, sửa flaky tests, bỏ `@Disabled` đã hết hạn, cập nhật điều kiện theo OS/JDK/framework.

### Checklist tự đánh giá

- [ ] Đã phân biệt assumption với assertion và nêu rõ vì sao test có thể ABORTED?
- [ ] Đã xác định test phụ thuộc môi trường **tùy chọn** hay yêu cầu bắt buộc?
- [ ] Annotation điều kiện sử dụng đúng package và loại cấu hình (env vs system property)?
- [ ] Regex `matches` phản ánh giá trị cấu hình thực tế?
- [ ] `@Disabled`/`disabledReason` có thông tin cụ thể, không để trống?
- [ ] `assumingThat` chỉ bao quanh assertion phụ, không che assertion chính?
- [ ] Cleanup/lifecycle vẫn an toàn nếu test abort sau setup?
- [ ] Có CI job thực sự chạy mọi nhóm test quan trọng trên môi trường hỗ trợ?
- [ ] Report phân biệt được passed, failed, aborted, disabled và tests filtered?
- [ ] Ví dụ Maven/Gradle dùng đúng JUnit version được dự án Spring Boot quản lý?

## 12. Tài liệu gốc để đối chiếu

- [JUnit User Guide — Assumptions](https://docs.junit.org/6.1.3/writing-tests/assumptions.html): các API `assumeTrue`, `assumeFalse`, `assumingThat` và test aborted.
- [JUnit User Guide — Disabling Tests](https://docs.junit.org/6.1.0/writing-tests/disabling-tests.html): `@Disabled`, class-level và lifecycle.
- [JUnit User Guide — Conditional Test Execution](https://docs.junit.org/6.0.2/writing-tests/conditional-test-execution.html): OS, JRE, environment variable, system property, custom method condition.
- [JUnit Jupiter 5.10 User Guide](https://docs.junit.org/5.10.0/user-guide/index.html): đối chiếu cú pháp khi dự án vẫn sử dụng JUnit 5.
- [JUnit 6 Migration Notes](https://github.com/junit-team/junit-framework/wiki/Upgrading-to-JUnit-6.0): Java baseline và API/điều kiện bị deprecated khi nâng cấp.

**Ghi nhớ:** Assertion trả lời **“hành vi có đúng không?”**; assumption trả lời **“có đủ điều kiện để đánh giá hành vi lúc này không?”**; annotation điều kiện trả lời **“test này có thuộc tập cần thực thi trong môi trường hiện tại không?”**. Test bị bỏ qua có lý do là một lựa chọn có kiểm soát, nhưng luôn phải được theo dõi để không đánh mất coverage.
