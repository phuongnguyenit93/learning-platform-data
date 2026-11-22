# Kiểm thử mã thoát bằng tiến trình con thay vì dừng JVM của bộ kiểm thử

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot chạy dạng CLI, batch, import/export hoặc worker thường cần thông báo kết quả cho shell, CI/CD hay job scheduler bằng **exit code của tiến trình**. Thông thường mã `0` là thành công, còn một mã khác `0` là thất bại theo hợp đồng ứng dụng.

Giả sử ứng dụng có `main()` kết thúc bằng:

```java
System.exit(code);
```

Đây là cách hợp lệ để CLI chuyển mã cho hệ điều hành. Nhưng nếu một bài kiểm thử JUnit **gọi trực tiếp `main()` trong chính JVM chạy JUnit**, lệnh `System.exit` có thể kết thúc luôn JVM của Maven Surefire/Failsafe trước khi test báo kết quả, chạy các assertions tiếp theo hoặc hoàn thành cả suite.

**Giải pháp:** dùng `ProcessBuilder` khởi chạy **một JVM con** chạy JAR thực; JUnit ở JVM cha chờ child kết thúc, đọc **`Process.exitValue()`**, kiểm tra stdout/stderr và đảm bảo child được hủy khi timeout.

Bài này hướng dẫn đầy đủ:

1. Phân biệt *business outcome*, giá trị từ `ExitCodeGenerator`/`SpringApplication.exit` và **OS process exit status**.
2. Hiểu vì sao không gọi `main()` chứa `System.exit()` trực tiếp trong test runner.
3. Dùng `ProcessBuilder` với đúng `java` executable, argument list, log redirection và deadline.
4. Cấu hình Maven **Failsafe** chạy integration tests **sau** `package` để executable Spring Boot JAR có sẵn.
5. Viết ứng dụng Spring Boot 3.3.13 / Java 21 trả ba mã `0`, `2`, `17`, có `ApplicationRunner`, `ExitCodeGenerator`, `ExitCodeEvent`, `@PreDestroy`.
6. Kiểm thử logic chọn mã bằng JUnit unit tests; kiểm thử **mã của tiến trình thật** bằng JUnit `ExitProcessIT`.
7. Phân biệt timeout, child bị force-kill, JVM shutdown, lỗi khởi động, lỗi cleanup và trạng thái bất đồng bộ.
8. Khắc phục test bị treo do pipe stdout/stderr đầy, test chạy nhầm JDK, đường dẫn chứa khoảng trắng và mã `0` sai.

**Phạm vi:** các ví dụ dùng Spring Boot 3.3.13, Java 21, JUnit Jupiter, Maven và Spring Boot executable JAR. Demo non-web, không cần database hoặc broker.

## 2. Ba tầng kết quả không được đánh đồng

```text
CLI flags / business input
          |
          v
ApplicationRunner xử lý job
          |
          +-- SUCCESS          -> 0
          +-- INVALID_INPUT    -> 2
          +-- BUSINESS_FAILED  -> 17
          |
          v
ExitCodeGenerator#getExitCode()
          |
          v
SpringApplication.exit(context)
          |
          +-- tính exit code
          +-- đóng Spring context
          |      +-- stop lifecycle components
          |      +-- @PreDestroy / destroy callbacks
          |
          v
main() gọi System.exit(code)
          |
          v
JVM con kết thúc, OS ghi nhận mã
          |
          v
JUnit cha: waitFor -> exitValue -> assert
```

| Tầng | Kiểm tra bằng gì? | Có tự kết thúc JVM không? |
| --- | --- | --- |
| **Kết quả nghiệp vụ** | Hàm/enum thuần Java, unit test | Không |
| **Mã Boot tính được** | `SpringApplication.exit(context)` và `ExitCodeGenerator` | Không |
| **Mã thoát tiến trình** | `Process.exitValue()` sau khi child kết thúc | Đây là kết quả tiến trình JVM con đã kết thúc |

`SpringApplication.exit(context)` **trả `int`** và đóng context nếu phù hợp; nó **không tự gọi `System.exit(int)`**. Vì vậy nếu một ứng dụng CLI chỉ gọi `SpringApplication.exit` rồi return bình thường, shell có thể thấy mã `0` dù generator đã trả `17`.

Mặt khác, kiểm tra `System.exit(code)` trong JVM của JUnit sẽ **không an toàn cho test runner**. Muốn chắc chắn shell/CI nhận đúng mã, hãy chạy child process thật.

### 2.1. Vì sao không chỉ test ExitCodeGenerator?

Ví dụ:

```java
assertEquals(17, outcome.exitCode());
```

Unit test này chứng minh mapping đúng, nhưng không đảm bảo `main()` đã chuyển mã ấy tới `System.exit`. Một lần refactor có thể làm `main` quên gọi `System.exit`, hoặc sửa sang `System.exit(0)` khiến CI báo thành công giả; test thuần vẫn xanh.

Một test kiểu:

```java
int code = SpringApplication.exit(context);
assertEquals(17, code);
```

cũng chỉ chứng minh mã được **Spring trả về**, không chứng minh **OS process** nhận mã. Bởi vậy cần cả hai mức kiểm thử.

### 2.2. Vì sao không test mọi nhánh bằng child?

Mỗi child JVM phải khởi động Java runtime, classpath, Spring context và chạy cleanup. Chi phí lớn hơn nhiều so với một pure unit test. Tốt nhất là unit test đầy đủ các precedence rules, sau đó chọn vài child integration tests đại diện cho các trạng thái quan trọng: `0`, nonzero, cleanup và timeout.

## 3. Anti-pattern: gọi main() chứa System.exit trong JUnit

Đây là một **đoạn code không nên chạy trong JVM test**:

```java
@Test
void badTest() {
    ExitChildApplication.main(new String[] {"--business-fail"});

    // JVM test có thể đã bị kết thúc bởi System.exit(17).
    assertEquals(17, expectedCode);
}
```

`main` của ứng dụng đã được thiết kế để gọi `System.exit`. Test trên có thể kết thúc quá trình Surefire trước khi đến assertion hoặc trước khi JUnit tạo báo cáo. Trạng thái thất bại biểu hiện như một fork bị dừng bất thường, chứ không phải một assertion failure có thông tin dễ hiểu.

Các cách tránh sai:

- **Không** sửa production main để bỏ `System.exit` chỉ cho test xanh: hành vi trả mã của CLI sẽ thay đổi.
- **Không** bắt mọi exception rồi trả `0`, vì như vậy mất tín hiệu thất bại cho automation.
- **Không** dựa vào `SecurityManager` chặn exit làm giải pháp chính trên Java 21: API này đã bị deprecated for removal và chặn call cũng không xác nhận status thực của OS.
- **Không** gọi `System.exit` ở bên trong `ApplicationRunner`, repository, service hoặc callback `@PreDestroy`: đặt hành động JVM-wide ở boundary của CLI sau khi hoàn tất công việc.
- **Có** tách logic lựa chọn code thành class có thể unit test và dùng `ProcessBuilder` để gọi JAR trong JVM con.

## 4. SpringApplication.exit và dọn dẹp tài nguyên

Với Spring Boot 3.3:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ExitChildApplication.class, args);

int code = SpringApplication.exit(context);

System.exit(code);
```

Đoạn trên là **minh họa** cần imports và primary source class. `SpringApplication.exit` lấy mã từ `ExitCodeGenerator` beans và các generators được truyền vào. Nó có thể phát `ExitCodeEvent` khi có mã khác `0`, rồi đóng context. Lệnh `System.exit` ở cuối mới chuyển mã thành process status.

### 4.1. ExitCodeGenerator

Đây là hợp đồng Spring Boot:

```java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

Đây là **chữ ký minh họa**, không phải tệp cần tự định nghĩa trong project. Một bean `@Component` có thể implement interface để Spring đọc mã đã được business job quyết định.

Khi có nhiều generators, Boot xem xét các mã theo thứ tự generator đã sắp xếp, lựa chọn **mã khác `0` đầu tiên**. Không coi mã lớn nhất hoặc generator chạy sau là tự động thắng. Nếu business có nhiều loại lỗi, xây **một outcome aggregator** với precedence tường minh sẽ dễ bảo trì hơn.

### 4.2. @PreDestroy và ExitCodeEvent

Đường thành công của một CLI đồng bộ:

```text
ApplicationRunner.run hoàn thành
    |
    v
SpringApplication.exit(context)
    |
    +-- ExitCodeGenerator.getExitCode()
    +-- ExitCodeEvent nếu mã nonzero
    +-- đóng ApplicationContext
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop(...)
          +-- @PreDestroy
    |
    v
SpringApplication.exit trả int
    |
    v
System.exit(int)
```

Một điều phải hiểu rõ: **mã generator có thể được tính trước khi `@PreDestroy` chạy**. Nếu cleanup thất bại lần đầu tại `@PreDestroy`, mã đã được chọn không mặc nhiên đổi theo lỗi ấy. Muốn kết quả exit bao gồm cleanup failures, phải có bước explicit cleanup/await báo kết quả **trước** khi `SpringApplication.exit` tính mã, hoặc một exit coordinator kiểm soát được outcome cuối.

Trong demo, `@PreDestroy` dọn một tệp tạm và in marker; test xác nhận callback được gọi trước khi main thông báo context đã đóng. Test không cố tình mô phỏng lỗi xóa file trong destroy callback.

### 4.3. Khi startup exception xảy ra

Nếu `ApplicationRunner` ném exception trước khi `SpringApplication.run` trả context, đoạn code nằm **sau** `run` có thể không chạy; Boot có đường xử lý startup failure riêng, bao gồm khả năng map code từ exception/mapper. Vì thế các child tests cho controlled business result `2`/`17` không thay thế các tests riêng cho startup failure.

## 5. Vì sao dùng ProcessBuilder và executable JAR?

### 5.1. ProcessBuilder tách JVM

```java
ProcessBuilder builder = new ProcessBuilder(
        "java", "-jar", "target/app.jar", "--business-fail");

Process child = builder.start();

boolean finished = child.waitFor(30, TimeUnit.SECONDS);

if (finished) {
    int actualCode = child.exitValue();
}
```

Đoạn này chỉ **minh họa**, chưa có imports, timeout cleanup và xử lý output; xem test đầy đủ ở mục 9. `ProcessBuilder.start()` tạo một OS process riêng, không gọi main bằng reflection trong cùng JVM. Khi child gọi `System.exit(17)`, JVM cha của JUnit vẫn tồn tại và nhận được `exitValue=17` nếu child kết thúc đúng.

`exitValue()` chỉ được gọi sau khi process đã kết thúc. Nếu child còn sống, `exitValue()` có thể ném `IllegalThreadStateException`.

### 5.2. Dùng argument list, không tự nối shell string

Một lệnh có đường dẫn chứa khoảng trắng rất dễ bị parse sai nếu ghép thủ công:

```java
String command = "java -jar C:\\Program Files\\demo.jar --flag";
```

Đây là **mẫu lỗi** vì tách arguments phụ thuộc cách gọi shell. Thay bằng:

```java
new ProcessBuilder(
        javaExecutable.toString(),
        "-jar",
        jar.toString(),
        "--business-fail");
```

Đoạn thứ hai là **mẫu minh họa**, cần `javaExecutable`, `jar`. `ProcessBuilder` nhận từng argument độc lập. Không thêm dấu ngoặc kép như một phần của tên file: dấu quote thủ công có thể trở thành ký tự của argument trên một số platform.

### 5.3. Chọn Java từ java.home

Nếu chỉ dùng lệnh `"java"`, PATH của máy hoặc CI có thể chọn JDK khác với JUnit runtime. Test tốt hơn nên xác định:

```java
String osName = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT);

String executable = osName.startsWith("windows")
        ? "java.exe" : "java";

Path java = Path.of(
        System.getProperty("java.home"), "bin", executable);
```

Đây là đoạn trong test đầy đủ. Với Java 21, JDK runtime thường có executable tại `bin/java` hoặc `bin/java.exe`; test có thể kiểm tra file tồn tại và fail rõ nếu môi trường không phù hợp.

### 5.4. Tại sao dùng JAR thay vì -cp?

Một subprocess có thể chạy:

```bash
java -cp "runtime-classpath" com.example.exitdemo.ExitChildApplication
```

Nhưng với Maven Surefire/Failsafe, `java.class.path` của test runner có thể chỉ chứa bootstrapping JAR, hoặc một classpath không khớp runtime của ứng dụng. Tự ghép tất cả dependencies là một nguồn lỗi và còn phụ thuộc classpath separator Windows/Unix.

Spring Boot executable JAR sau `package` đã chứa loader và dependencies cần thiết. Do đó:

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar
```

gần với cách ứng dụng CLI được vận hành thực tế hơn và giảm sự phụ thuộc vào internals của test runner.

## 6. Maven Surefire và Failsafe chạy ở những phase nào?

```text
compile
   |
test             <-- Surefire chạy *Test
   |
package          <-- Spring Boot Maven plugin tạo executable JAR
   |
integration-test <-- Failsafe chạy *IT
   |
verify           <-- Failsafe kiểm tra kết quả integration tests
```

Chúng ta cần **đợi JAR được tạo ở `package`** trước khi `ExitProcessIT` dùng nó. Vì vậy test này phải chạy ở phase `integration-test`, không phải trong Surefire `test` nếu JAR chưa có.

Lệnh chuẩn:

```bash
mvn clean verify
```

Lệnh `mvn test` chỉ test logic thuần ở phase `test`, không xác nhận process exit code của JAR mới. Không gọi riêng `mvn integration-test` rồi bỏ qua `verify` nếu muốn Failsafe báo kết quả đầy đủ sau vòng integration teardown.

### 6.1. Tên test

- `JobOutcomeTest.java`: unit tests do Surefire thực thi.
- `ExitProcessIT.java`: integration tests do Failsafe thực thi.

Maven Failsafe hỗ trợ JUnit Jupiter khi dependencies và plugin versions phù hợp. Dự án dưới đây cố định Failsafe `3.2.5`.

### 6.2. Không chạy integration test trước khi package

Nếu `ExitProcessIT` kiểm tra đường dẫn:

```text
target/exit-child-demo-0.0.1-SNAPSHOT.jar
```

mà người lập trình chỉ gọi `mvn test`, file có thể chưa tồn tại hoặc là artifact cũ từ lần build trước. **Không** dùng JAR cũ để khẳng định source hiện tại đã pass. `mvn clean verify` xây từ đầu rồi chạy test trên JAR mới.

## 7. Demo hoàn chỉnh Spring Boot 3.3.13 / Java 21

Project gồm một CLI non-web và hai nhóm test. CLI xử lý ba flags outcome đơn giản, tạo/xóa một temporary file, trả code cho OS. Không mở HTTP port hoặc kết nối server ngoài.

### 7.1. Cấu trúc project

```text
exit-child-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/exitdemo/
    │   ├── ExitChildApplication.java
    │   ├── JobOutcome.java
    │   ├── ExitJob.java
    │   └── ExitCodeObserver.java
    └── test/java/com/example/exitdemo/
        ├── JobOutcomeTest.java
        └── ExitProcessIT.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>exit-child-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <executions>
                    <execution>
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

Spring Boot parent quản lý dependencies và cấu hình plugin phù hợp để `spring-boot-maven-plugin` repackage executable JAR. Failsafe chạy các ITs sau packaging.

`spring-boot-starter` đủ cho `ApplicationRunner`, events và context non-web. `spring-boot-starter-test` mang JUnit Jupiter. Java 21 tương thích với Boot 3.3.13.

### 7.3. JobOutcome.java

Tệp `src/main/java/com/example/exitdemo/JobOutcome.java`:

```java
package com.example.exitdemo;

public enum JobOutcome {

    SUCCESS(0),
    INVALID_INPUT(2),
    BUSINESS_FAILED(17);

    private final int exitCode;

    JobOutcome(int exitCode) {
        this.exitCode = exitCode;
    }

    public int exitCode() {
        return exitCode;
    }

    public static JobOutcome fromFlags(
            boolean invalidInput, boolean businessFailed) {

        if (invalidInput) {
            return INVALID_INPUT;
        }
        if (businessFailed) {
            return BUSINESS_FAILED;
        }
        return SUCCESS;
    }
}
```

Tại đây, mapping business → code thuần Java, dễ test và không liên quan JVM shutdown. Nếu cả `--invalid-input` và `--business-fail` xuất hiện, demo **ưu tiên INVALID_INPUT (2)**. Đây là lựa chọn nghiệp vụ trong ví dụ, không phải mặc định Spring.

### 7.4. ExitJob.java

Tệp `src/main/java/com/example/exitdemo/ExitJob.java`:

```java
package com.example.exitdemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

@Component
public class ExitJob implements ApplicationRunner, ExitCodeGenerator {

    private volatile JobOutcome outcome = JobOutcome.SUCCESS;
    private Path temporaryFile;

    @Override
    public void run(ApplicationArguments args) throws Exception {
        temporaryFile = Files.createTempFile("exit-child-demo-", ".tmp");

        Files.writeString(
                temporaryFile, "demo job completed\n",
                StandardCharsets.UTF_8);

        outcome = JobOutcome.fromFlags(
                args.containsOption("invalid-input"),
                args.containsOption("business-fail"));

        System.out.println("JOB result=" + outcome.name()
                + " code=" + outcome.exitCode());
    }

    @Override
    public int getExitCode() {
        return outcome.exitCode();
    }

    @PreDestroy
    void cleanup() throws IOException {
        boolean deleted = temporaryFile != null
                && Files.deleteIfExists(temporaryFile);

        System.out.println("CLEANUP tempFileDeleted=" + deleted);
    }
}
```

`ExitJob` tạo một **tệp tạm** để có resource cleanup thật, không phải chỉ in chữ “đã dọn xong”. `@PreDestroy` xóa nó trong giai đoạn destroy bean. Nếu không có ngoại lệ, output xác nhận `tempFileDeleted=true`.

**Giới hạn:** tệp tạm trong demo không phải dữ liệu sản phẩm cần lưu bền. Với file kinh doanh thật, không tự xóa output cuối; cần flush/fsync, atomic rename, retry và lưu lỗi phù hợp. Nếu cleanup ở `@PreDestroy` lỗi, không mặc định generator code sẽ được thay đổi; xem mục 13.

`JobOutcome` được giữ trong một field để Spring Boot gọi `getExitCode()` sau `ApplicationRunner`. Demo xử lý đồng bộ, không submit một công việc nền rồi trả về trước khi outcome đã chốt.

### 7.5. ExitCodeObserver.java

Tệp `src/main/java/com/example/exitdemo/ExitCodeObserver.java`:

```java
package com.example.exitdemo;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitCodeObserver {

    @EventListener
    public void observe(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

`ExitCodeEvent` có thể được phát khi `SpringApplication.exit` xác định mã khác `0`, trước khi đóng context. Listener chỉ ghi mốc để test. Nó không tự quyết định mã và không gọi `System.exit`.

### 7.6. ExitChildApplication.java

Tệp `src/main/java/com/example/exitdemo/ExitChildApplication.java`:

```java
package com.example.exitdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ExitChildApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitChildApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);

        int code = SpringApplication.exit(context);

        System.out.println("MAIN contextClosed="
                + !context.isActive() + " code=" + code);

        System.exit(code);
    }
}
```

`WebApplicationType.NONE` cho phép chạy như CLI, không mở port. Khi startup thành công, runner đã chạy trước khi `application.run()` trả context. `SpringApplication.exit(context)` đọc code và đóng context. Chỉ sau đó `System.exit(code)` mới kết thúc JVM.

**Không gọi `main()` này trong một JUnit unit test**. Nó cố tình gọi `System.exit` vì đó là hợp đồng CLI thực.

## 8. Unit tests cho business mapping

Tệp `src/test/java/com/example/exitdemo/JobOutcomeTest.java`:

```java
package com.example.exitdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JobOutcomeTest {

    @Test
    void successReturnsZero() {
        assertEquals(0, JobOutcome.fromFlags(false, false).exitCode());
    }

    @Test
    void businessFailureReturnsSeventeen() {
        assertEquals(17, JobOutcome.fromFlags(false, true).exitCode());
    }

    @Test
    void invalidInputHasPriority() {
        assertEquals(2, JobOutcome.fromFlags(true, true).exitCode());
    }
}
```

Tests chạy cùng JUnit JVM vì chỉ gọi hàm thuần Java, không kết thúc process. Lệnh:

```bash
mvn test
```

sẽ chạy **ba tests** này qua Surefire. Chưa nên tuyên bố đã kiểm thử OS exit status khi chỉ chạy `mvn test`.

## 9. Process integration test có kiểm soát

Tệp `src/test/java/com/example/exitdemo/ExitProcessIT.java`:

```java
package com.example.exitdemo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class ExitProcessIT {

    @TempDir
    Path temporaryDirectory;

    private record RunResult(int exitCode, String output) {
    }

    @Test
    void successReturnsZeroAfterCleanup() throws Exception {
        RunResult result = runChild();

        assertEquals(0, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=SUCCESS code=0",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=0");
    }

    @Test
    void businessFailureReturnsSeventeen() throws Exception {
        RunResult result = runChild("--business-fail");

        assertEquals(17, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=BUSINESS_FAILED code=17",
                "EXIT event=17",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=17");
    }

    @Test
    void invalidInputReturnsTwo() throws Exception {
        RunResult result = runChild(
                "--business-fail", "--invalid-input");

        assertEquals(2, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=INVALID_INPUT code=2",
                "EXIT event=2",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=2");
    }

    private RunResult runChild(String... options) throws Exception {
        Path projectDir = Path.of(
                System.getProperty("user.dir")).toAbsolutePath();

        Path jar = projectDir.resolve("target")
                .resolve("exit-child-demo-0.0.1-SNAPSHOT.jar");

        assertTrue(Files.isRegularFile(jar),
                "Executable JAR chưa có; chạy mvn clean verify: " + jar);

        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);

        String binary = os.startsWith("windows")
                ? "java.exe" : "java";

        Path javaExecutable = Path.of(
                System.getProperty("java.home"), "bin", binary);

        assertTrue(Files.isRegularFile(javaExecutable),
                "Không có Java executable: " + javaExecutable);

        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());
        command.add("-Dfile.encoding=UTF-8");
        command.add("-jar");
        command.add(jar.toString());
        command.add("--spring.main.banner-mode=off");
        command.add("--logging.level.root=ERROR");
        Collections.addAll(command, options);

        Path outputFile = Files.createTempFile(
                temporaryDirectory, "child-", ".log");

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(projectDir.toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(outputFile.toFile());

        Process process = builder.start();

        try {
            if (!process.waitFor(30, TimeUnit.SECONDS)) {
                process.destroy();

                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }

                String partialOutput = Files.readString(
                        outputFile, StandardCharsets.UTF_8);

                fail("Child JVM quá thời hạn 30 giây:\n"
                        + partialOutput);
            }

            String output = Files.readString(
                    outputFile, StandardCharsets.UTF_8);

            return new RunResult(process.exitValue(), output);
        }
        finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }

    private static void assertInOrder(
            String output, String... markers) {

        int previousIndex = -1;

        for (String marker : markers) {
            int currentIndex = output.indexOf(marker);

            assertTrue(currentIndex >= 0,
                    "Thiếu marker " + marker + "\n" + output);

            assertTrue(currentIndex > previousIndex,
                    "Marker sai thứ tự " + marker + "\n" + output);

            previousIndex = currentIndex;
        }
    }
}
```

### 9.1. Những điểm đúng trong ProcessBuilder test

**Chạy JAR có thật.** Test tìm `target/exit-child-demo-0.0.1-SNAPSHOT.jar` sau bước đóng gói. Không dựa vào file `.class` hoặc test classpath của Surefire.

**Đúng JDK.** Java executable được lấy từ `java.home/bin`. Trên Windows có hậu tố `.exe`; trên Linux/macOS dùng `java`. Khi chạy CI có nhiều JDK, tránh lấy nhầm `"java"` từ PATH.

**Đúng truyền tham số.** Mỗi argument là một phần tử của `List<String>`. Đường dẫn như `C:\Program Files\Java\...` không cần tự gắn quote theo shell syntax.

**Không làm nghẽn pipes.** `redirectErrorStream(true)` gộp stderr vào stdout; `redirectOutput(outputFile)` ghi output child trực tiếp vào file. Cha **không** phải đọc các streams trước khi `waitFor`. Khi child đã kết thúc, test đọc file để assert.

**Có timeout.** `waitFor(30, SECONDS)` giới hạn tổng thời gian từ lúc child khởi động, bao gồm Spring bootstrap, runner và shutdown. Nếu quá deadline, child được yêu cầu dừng rồi force kill nếu cần, test thất bại kèm log phần đã ghi.

**Không để lại child.** `finally` sử dụng `process.isAlive()` và `destroyForcibly()` nếu cần. Đây là guard để JUnit không bỏ lại process khi code thay đổi hoặc test lỗi.

**Assertion có ý nghĩa.** Tests kiểm tra cả mã OS (`exitCode`) và các markers `JOB`, `EXIT`, `CLEANUP`, `MAIN`. Không chỉ assert có chữ `BUSINESS_FAILED` trong log mà quên check process code.

### 9.2. Vì sao phải redirect output trước waitFor?

Sai lầm kinh điển:

```java
Process p = builder.start();
p.waitFor();

String output = new String(
        p.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8);
```

Đây là **anti-pattern** khi child có thể in nhiều log: OS pipe có buffer hữu hạn, child có thể block khi pipe đầy. Cha lại đang đợi process kết thúc, thành **deadlock**. Nếu stdout và stderr có hai pipes riêng, chỉ drain một pipe cũng chưa đủ.

Có hai giải pháp:

- Redirect cả stdout và stderr vào một tệp như demo (đơn giản và phù hợp với logs của test).
- Dùng readers riêng chạy **đồng thời** để tiêu thụ stdout/stderr, có thread management và timeouts.

Không đợi vô hạn rồi mới bắt đầu đọc output khi đang dùng `PIPE` mặc định. Trong các tests xuất rất nhiều log, còn phải giới hạn disk usage hoặc chỉ lưu những đoạn cần thiết.

### 9.3. Timeout không đồng nghĩa code ứng dụng trả về nonzero

Nếu child quá hạn và test gọi `destroyForcibly()`, exit status do OS trả về lúc đó **không phải** bằng chứng application đã gọi `System.exit` với mã tương ứng. Timeout phải được báo như **test failure riêng**, không ghép nó vào phép assert code `2` hay `17` của business logic.

Với Windows, Linux và macOS, semantics `destroy()`/`destroyForcibly()` có thể khác nhau; không coi `destroy()` trên mọi nền tảng là tương đương một POSIX `SIGTERM` cụ thể.

### 9.4. Vì sao không dùng Thread.sleep để đợi JVM con?

Đoạn như:

```java
Process p = builder.start();
Thread.sleep(2000);
assertEquals(17, p.exitValue());
```

**Không đáng tin**: máy CI có thể cần 4 giây để khởi động Spring, hoặc app hoàn tất nhanh hơn nhiều. Sau hai giây child vẫn chạy, `exitValue()` ném `IllegalThreadStateException`; hoặc thời gian ngủ lãng phí.

`waitFor(timeout, TimeUnit.SECONDS)` là đồng bộ hóa theo **completion thật** và có deadline, nên tốt hơn sleep một khoảng tùy ý. Cũng không nên spin liên tục gọi `isAlive()` mà không có timeout và backoff.

### 9.5. Tại sao @TempDir hữu ích?

`@TempDir Path temporaryDirectory` là tính năng JUnit Jupiter tạo một vùng tạm cho test, giúp tránh đụng log file giữa các tests. Log được dọn theo lifecycle extension. Child JVM tạo tệp tạm riêng trong `ExitJob`, và `@PreDestroy` xóa nó khi context đóng đúng đường.

Trong dự án thật, nếu child dùng DB, filesystem chung hoặc ports, cần cô lập tài nguyên đó; child process chỉ cách ly **JVM memory**, không tự cô lập toàn bộ OS, network và storage.

## 10. Kiểm tra đầy đủ bằng Maven

### 10.1. Đầu tiên, chỉ unit tests

```bash
java -version
mvn -version
mvn clean test
```

Với project demo, Surefire dự kiến chạy **3 unit tests** `JobOutcomeTest`; `ExitProcessIT` chưa chạy. Trạng thái `BUILD SUCCESS` ở lệnh này chưa xác nhận mã OS của app.

### 10.2. Sau đó, integration tests với executable JAR

```bash
mvn clean verify
```

Quy trình:

```text
mvn clean verify
     |
     +-- compile
     +-- test: JobOutcomeTest (3 assertions)
     +-- package: executable JAR
     +-- integration-test: ExitProcessIT (3 child JVMs)
     +-- verify: Failsafe tổng hợp trạng thái
```

Kỳ vọng test classes minh họa có **3 unit tests + 3 integration tests**, tổng 6 tests, tất cả pass trong môi trường có JDK 21, Maven và dependencies. Không hardcode thời gian chạy hoặc output Maven đầy đủ trong assertions.

Nếu thấy JAR không tồn tại, kiểm tra `artifactId`, `version`, tên JAR thực tế, Spring Boot Maven plugin, Maven current module và phase đã chạy.

### 10.3. Báo cáo Maven

Các báo cáo thông thường:

```text
target/surefire-reports/
    TEST-com.example.exitdemo.JobOutcomeTest.xml

target/failsafe-reports/
    TEST-com.example.exitdemo.ExitProcessIT.xml
    failsafe-summary.xml
```

Báo cáo giúp phân biệt unit test failure với child exit-code integration test failure. Khi CI thất bại, có thể lưu file child log từ `@TempDir`/test artifacts theo policy hoặc in một đoạn output trong assertion failure; tránh vô tình ghi secrets.

### 10.4. Không chạy Failsafe trước package

Chỉ gọi `mvn test` rồi chạy IT thủ công có thể dùng JAR cũ từ lần trước. Đây là lỗi nguy hiểm: test “xanh” nhưng không đo code phiên bản hiện tại. `mvn clean verify` đảm bảo build từ trạng thái sạch rồi mới chạy IT trên JAR vừa được tạo.

## 11. Chạy JAR thủ công để đối chiếu

Trong Bash/zsh, ngay sau `mvn package` hoặc `mvn verify`:

### 11.1. Thành công

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar
echo $?
```

Các dòng **do code demo chủ động in** theo thứ tự:

```text
JOB result=SUCCESS code=0
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=0
```

Shell in:

```text
0
```

`EXIT event=...` không được phát từ đường chọn code zero. Spring Boot có thể in banner, log và timestamps khác, nên khối trên không phải toàn stdout.

### 11.2. Business failure

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
echo $?
```

Dòng demo theo thứ tự:

```text
JOB result=BUSINESS_FAILED code=17
EXIT event=17
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=17
```

Ngay sau lệnh Java, Bash/zsh in mã:

```text
17
```

### 11.3. Invalid input

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --invalid-input
echo $?
```

Các dòng:

```text
JOB result=INVALID_INPUT code=2
EXIT event=2
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=2
```

Và shell in:

```text
2
```

Nếu truyền cả hai flags, `JobOutcome.fromFlags` ưu tiên invalid input nên mã vẫn là `2`.

### 11.4. PowerShell và CMD

PowerShell:

```powershell
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
$LASTEXITCODE
```

CMD:

```bat
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
echo %ERRORLEVEL%
```

Trong hai trường hợp, mã mong đợi là `17`. Không dùng `$?` của Bash trong PowerShell: `$?` có semantics về trạng thái thành công/thất bại gần nhất, còn `$LASTEXITCODE` là biến thích hợp để xem native process exit code.

**Đọc mã ngay sau lệnh Java**; chạy thêm một lệnh native khác có thể thay đổi biến trạng thái trong shell.

## 12. Khi nào cần kiểm thử context trực tiếp?

Không phải mọi mục tiêu kiểm thử đều cần child process. Một test Spring context có thể viết:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ExitChildApplication.class);

int code = SpringApplication.exit(context);
assertEquals(0, code);
```

Đây là **mẫu minh họa không độc lập**. Nó cho biết bean wiring, exit generator và close logic có thể hoạt động trong một JVM. Nếu **không gọi `main`**, test này không làm dừng JUnit process.

Nhưng nó vẫn **không chứng minh** CLI main thực sự truyền mã vào `System.exit(code)`. Trong đề bài hiện tại, xác nhận mã của OS là mục tiêu chính, vì vậy child test là phần không được bỏ.

| Kiểu test | JVM riêng? | Xác nhận OS exit status? | Dùng khi nào |
| --- | --- | --- | --- |
| Unit test mapping code | Không | Không | Mọi precedence rule và input validation |
| Spring context integration test | Không | Không | Bean lifecycle, `ExitCodeGenerator`, DI |
| `ProcessBuilder` + packaged JAR | **Có** | **Có** | `main`, `System.exit`, shell code, cleanup và deployment artifact |

## 13. Những tình huống ngoài đường thành công

### 13.1. `ApplicationRunner` ném exception

Nếu runner ném exception trước khi `SpringApplication.run` trả context, main trong demo có thể chưa tới dòng `SpringApplication.exit`. Spring Boot xử lý startup failure bằng cơ chế riêng, gồm xử lý exception, shutdown context và exit-code mapper khi cấu hình. Test controlled business failure (`--business-fail`) ở demo **không ném exception**, nhờ đó ta có thể quan sát code do generator chọn.

Muốn test startup exception code, thêm một test child riêng, có error mapping được đặc tả và assertion mã OS. Không gộp mọi exception vào `System.exit(0)`.

### 13.2. Cleanup error sau khi generator được đọc

`@PreDestroy` chạy khi Spring đóng bean. Nếu `getExitCode()` được gọi trước `@PreDestroy`, mã đã được tính. Một lỗi xóa tệp trong destroy callback có thể được log nhưng **không chắc** làm OS exit code đổi từ `0` sang một giá trị phù hợp.

Nếu yêu cầu **mã phải phản ánh cleanup outcome**, tổ chức explicit cleanup trước khi gọi `SpringApplication.exit`:

```java
CleanupOutcome cleanup = job.cleanupAndAwait();

int plannedCode = decideCode(job.outcome(), cleanup);

int returnedCode = SpringApplication.exit(
        context, () -> plannedCode);

System.exit(returnedCode);
```

Đây là **pseudocode kiến trúc**, cần định nghĩa `CleanupOutcome`, `decideCode`, `job` và context; không phải class biên dịch độc lập. Chú ý nếu còn `ExitCodeGenerator` bean khác, thứ tự lựa chọn mã phải được xác định rõ. Nên dùng một result aggregator duy nhất nếu cần precedence chặt.

### 13.3. Async task chưa xong

Nếu runner chỉ gọi `executor.submit(...)` và return, Boot có thể tính exit code khi task chưa hoàn tất. Khi đóng context, resource provider có thể bị destroy trong lúc task còn dùng nó.

Để an toàn:

1. Ngừng nhận task mới.
2. Chờ in-flight work với deadline hữu hạn.
3. Đảm bảo kết quả, checkpoint/ack, hoặc ghi tình trạng cần retry.
4. Chốt mã sau khi đã biết success/failure.
5. Cho Spring dừng `SmartLifecycle` theo phase/dependency.
6. Sau khi context đóng phù hợp, gọi `System.exit(code)`.

Đừng gọi `SmartLifecycle.stop(Runnable callback)` rồi chạy callback ngay khi chỉ mới submit một tác vụ drain. Callback nên báo stop **thật sự hoàn tất** hoặc trạng thái timeout/failure theo policy; nếu gọi quá sớm, provider có thể bị đóng khi consumer vẫn hoạt động.

### 13.4. SIGTERM, SIGKILL và kill do test

`System.exit(17)` là exit do ứng dụng chủ động chọn. Nếu JVM con bị `SIGKILL` hoặc `destroyForcibly`, OS có thể trả một mã riêng cho termination, **không phải** mã do business logic chọn. Trên Unix shell, convention có thể biểu diễn signal termination bằng mã dạng `128 + signal`, nhưng không áp dụng tuyệt đối cho mọi launcher/OS.

Không đưa case timeout/force kill vào cùng một assertion rằng `exitCode == 17` của business failure. Với forced termination, test phải kiểm chứng **failure mode và recovery** khác, không giả định `@PreDestroy` đã chạy.

### 13.5. Process con có thể tạo process cháu

`process.destroyForcibly()` thường xử lý một process handle, không mặc định quản lý toàn bộ descendants do app tạo. Nếu test dùng launcher shell, wrapper hoặc subprocesses con khác, cần process-tree cleanup qua `ProcessHandle.descendants()` với chính sách rõ ràng.

Demo chạy `java -jar` **trực tiếp** và không spawn thêm process nên không cần logic bổ sung này.

### 13.6. Resource ngoài JVM vẫn được chia sẻ

Một child JVM tách classloader, threads và memory nhưng không cô lập:

- File system của host.
- Database, broker hoặc Redis test.
- TCP ports.
- Environment variables và secrets.
- CPU/RAM/disk quota của CI.

Với project lớn cần dùng `@TempDir`, port động, testcontainers hoặc fake dependencies tùy tình huống. Tránh thử bằng cách xóa file production hoặc kết nối nhầm hệ thống thật.

## 14. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Surefire fork bị tắt bất thường | Test gọi `main` chứa `System.exit` | Dùng child JVM, unit test logic riêng |
| `mvn test` xanh nhưng chưa chạy `ExitProcessIT` | Failsafe chỉ chạy sau package | `mvn clean verify` |
| JAR không tồn tại ở `target/` | Chưa package hoặc sai artifact path | Kiểm tra POM/phase/working dir |
| `no main manifest attribute` | Chưa dùng Spring Boot repackaging phù hợp | Kiểm tra Spring Boot Maven plugin |
| `ClassNotFoundException` khi dùng `-cp` | Classpath của test launcher không đầy đủ | Dùng executable JAR |
| Child chạy JDK sai version | `"java"` lấy từ PATH | Dùng `java.home/bin/java[.exe]` |
| Path có khoảng trắng bị lỗi | Ghép arguments thành một shell string | Dùng `ProcessBuilder(List<String>)` |
| `waitFor()` treo khi child in log nhiều | Pipes stdout/stderr đầy | Redirect file hoặc đọc streams đồng thời |
| Test đọc `exitValue()` khi child còn sống | Chưa `waitFor` thành công | Đợi có deadline |
| Child timeout nhưng test không thoát | Không có cleanup fallback | `destroy`, `destroyForcibly`, `finally` |
| `Thread.sleep` rồi assert bị flaky | Sleep không chứng minh process hoàn tất | `waitFor(timeout, TimeUnit.SECONDS)` |
| JVM con không có quyền tạo temp file | Môi trường CI/read-only filesystem | Cấp temp directory phù hợp và điều tra lỗi |
| Cleanup marker thiếu | Context không đóng, stdout mất log, lỗi startup | Kiểm tra log, process path, exit helper |
| Business failure mà OS code `0` | `main` không gọi `System.exit(code)` | Child IT kiểm tra code thực |
| Test assert toàn bộ Boot log | Banner/version/timing thay đổi | Assert stable markers và thứ tự |
| JUnit test chết sau khi pass một case | Test gọi `main` trong JVM cha | Không gọi trực tiếp, dùng subprocess |
| Test song song xung đột port | Child sử dụng cùng fixed port | Non-web demo hoặc port động |
| Cleanup failure không đổi OS code | Exit generator đọc trước destroy | Explicit cleanup trước tính code |
| App bị SIGKILL nhưng test đòi @PreDestroy | Force kill bỏ qua shutdown hooks | Phân biệt force-kill recovery test |

### 14.1. Checklist chẩn đoán

1. Test có thật sự khởi chạy process con, hay chỉ gọi `main` cùng JVM?
2. `mvn verify` có chạy `ExitProcessIT` và tạo failsafe report?
3. JAR ở đúng path, đúng version, đúng module?
4. Process command có các args tách riêng, không quote nhầm?
5. Java executable có đúng JDK 21 không?
6. Child có bị trùng port/resource ngoài JVM?
7. Stdout/stderr có bị pipe đầy gây deadlock?
8. `waitFor` có deadline và timeout failure không?
9. Test có cleanup child trong `finally`?
10. Có assert exit code thực cùng business marker?
11. `@PreDestroy` có chạy trước thông báo context đóng?
12. Nếu log nonzero, exit code có được `System.exit` chuyển ra OS?
13. Nếu cleanup lỗi, có explicit kết quả trước `SpringApplication.exit`?
14. Có output bí mật bị ghi vào test log?
15. Có test recovery khi process bị kill đột ngột?

## 15. Bài tập và câu hỏi tự kiểm tra

1. Vì sao một JUnit test gọi `ExitChildApplication.main` có thể kết thúc Surefire JVM?
2. Phân biệt business outcome, Spring exit-code calculation và OS exit status.
3. Khi nào `System.exit(17)` là hợp lệ?
4. Vì sao `SpringApplication.exit(context)` không thay thế `System.exit(code)` cho CLI cần mã OS?
5. Tại sao phải đặt `System.exit` ở outermost main, không ở runner hoặc `@PreDestroy`?
6. Trong demo, vì sao `@PreDestroy` chạy trước `MAIN contextClosed`?
7. Nếu cleanup thất bại sau `getExitCode()`, mã có chắc thay đổi không?
8. Vì sao mapping `JobOutcome.fromFlags` nên được unit test riêng?
9. Tại sao `ExitProcessIT` nên chạy sau `package`?
10. Phân biệt Maven Surefire và Failsafe.
11. `mvn clean test` có chạy `ExitProcessIT` không?
12. `mvn clean verify` có tạo JAR trước khi test OS code không?
13. Vì sao `ProcessBuilder` với argument list tránh lỗi đường dẫn chứa khoảng trắng?
14. Ưu điểm của chọn java executable từ `System.getProperty("java.home")`?
15. Trong test, vì sao phải đọc `exitValue()` sau `waitFor`?
16. Vì sao không dùng `Thread.sleep(2000)` để đợi child?
17. Trường hợp nào một `waitFor()` không deadline có thể treo vô hạn?
18. Vì sao không nên chỉ đọc stdout sau khi `waitFor()` nếu giữ pipes mặc định?
19. Dùng `redirectErrorStream(true)` có đánh đổi điều gì?
20. `@TempDir` giải quyết điều gì khi nhiều tests chạy?
21. Nếu child vượt 30s, test phải làm gì để không để lại process?
22. Lệnh `destroyForcibly()` có bảo đảm process kết thúc tức thì không?
23. Vì sao exit code từ forced kill không có nghĩa app đã tự gọi `System.exit(code)`?
24. Nếu child tạo thêm process cháu, làm sao kiểm tra process tree cleanup?
25. Viết test mới cho option `--permission-error` trả code `13`.
26. Vì sao không assert timestamps/banner Spring Boot?
27. Nếu `ApplicationRunner` ném exception trước khi `run` trả context, chuyện gì khác?
28. Làm sao test cleanup failure của file operations mà không phá filesystem host?
29. CI nên lưu failsafe reports và child logs thế nào khi test fail?
30. Đề xuất quy trình kiểm thử gồm pure unit tests, Spring context tests và packaged-JAR child integration tests.

**Tiêu chí đạt:** ứng dụng CLI Java 21/Spring Boot 3.3 trả code `0`, `2`, `17`; `mvn clean verify` chạy ba unit tests và ba process integration tests; JUnit JVM không bị `System.exit` của child kết thúc; test không deadlock do output pipes, có timeout, cleanup process và assertions trên mã OS thực.

## 16. Tài liệu tham khảo

- Spring Boot 3.3.13 — `SpringApplication.exit`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Application Exit, `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Maven Failsafe — `integration-test`/`verify`: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Maven Failsafe — Usage: https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html
- Java 21 — `ProcessBuilder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 21 — `Process.waitFor(timeout)`, `exitValue()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html
- Java 21 — `ProcessHandle`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html
- JUnit Jupiter — `@TempDir`: https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory
