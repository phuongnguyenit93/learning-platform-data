# Kiểm thử console output trong Java Logging: từ System.out đến ConsoleAppender

## 1. Kiểm thử console output là kiểm tra điều gì?

Nhiều ứng dụng Java ghi thông tin ra **console** để developer xem trong IDE, để tiến trình được giám sát bởi hệ điều hành, hoặc để container runtime và log collector thu thập. Một dòng được gọi từ logger chưa chắc đã đến được console; ngược lại, nội dung nhìn thấy ở terminal có thể đến từ logger, từ `System.out.println`, từ Maven hoặc từ một thư viện khác.

**Kiểm thử console output** là xác minh rằng trong một kịch bản xác định:

1. **Đúng sự kiện** được phát ra, không thiếu hoặc phát nhầm.
2. **Đúng luồng** nhận bản ghi: standard output (`stdout`) hoặc standard error (`stderr`).
3. **Đúng định dạng**: level, logger, event code, message, trường ngữ cảnh, dấu xuống dòng, charset.
4. **Đúng số lần và thứ tự khi có hợp đồng**: không nhân đôi ngoài ý muốn; không giả định thứ tự toàn cục giữa hai stream độc lập.
5. **Đúng xử lý lỗi**: loại ngoại lệ, nguyên nhân và stack trace có mặt khi cần.
6. **Không rò rỉ dữ liệu**: token, mật khẩu hoặc thông tin riêng tư không xuất trong message, MDC hay exception.
7. **Đúng tại runtime**: bản ghi qua logger, filter, appender, encoder và cuối cùng tới đầu ra quan sát được.

Điểm cần nhớ: test kiểm tra lời gọi `logger.error(...)` **không tương đương** với test bytes thực sự xuất ra `stderr`. Unit test có thể xác minh sự kiện trong JVM; integration test phải đi qua cấu hình output thật.

Ví dụ hai output mong muốn:

```text
stdout: INFO|OrderService|event=order.created order_id=O-17
stderr: ERROR|PaymentService|event=payment.failed code=UPSTREAM_TIMEOUT
```

Phần `stdout:` và `stderr:` ở trên chỉ là **nhãn để giải thích**. Trong console thật, chúng thường là hai luồng byte riêng, không tự thêm các nhãn đó vào dòng.

### Mục tiêu không phải “assert mọi chữ trong terminal”

Kiểm thử tốt khẳng định **hợp đồng cần bảo vệ**. Nếu timestamp, ID ngẫu nhiên, tên thread hay số dòng stack trace thay đổi hợp lệ, so sánh toàn bộ nội dung terminal như một chuỗi cố định có thể tạo nhiều test lỗi giả. Nhưng nếu hệ thống quy định stdout chỉ chứa JSON Lines, thì **tính hợp lệ của từng JSON object và tên các trường** lại là hợp đồng đáng kiểm thử.

## 2. Stdout và stderr: hai kênh khác nhau

JDK có ba standard stream:

| Luồng | API Java | Mục đích thường gặp |
| --- | --- | --- |
| Standard input | `System.in` | Nhận dữ liệu vào từ terminal hoặc pipeline. |
| Standard output | `System.out` | Thông tin, kết quả chương trình, log được định tuyến ra stdout. |
| Standard error | `System.err` | Chẩn đoán lỗi, cảnh báo hoặc log được định tuyến ra stderr. |

**Không có quy tắc của Java nói rằng mọi log ERROR phải vào stderr.** Việc đó do logging backend và cấu hình appender quyết định. Ví dụ:

- `System.out.println(...)` đi tới `System.out` hiện tại.
- `System.err.println(...)` đi tới `System.err` hiện tại.
- `java.util.logging.ConsoleHandler` mặc định xuất lên `System.err`, nhưng mức, formatter và handler có thể được cấu hình khác.
- `Logback ConsoleAppender` có thể chọn `System.out` hoặc `System.err` bằng `<target>`.
- `Log4j 2 Console` có thể cấu hình `target="SYSTEM_OUT"` hoặc `target="SYSTEM_ERR"`.

Trong container, nền tảng triển khai có thể thu thập cả hai luồng rồi hiển thị trong một giao diện. Việc hai dòng xuất sát nhau trên terminal **không chứng minh** chúng đi qua cùng một stream.

### Có nên đưa INFO ra stdout và ERROR ra stderr?

Đó là một chính sách **có thể chọn**, không bắt buộc. Nếu hạ tầng yêu cầu phân luồng, hãy cấu hình các appender/filter để mỗi mức đi đúng đích. Nếu nền tảng chỉ có một pipeline stdout với trường `level`, việc đưa cả INFO và ERROR ra stdout cũng có thể hợp lý.

Khi kiểm thử, xác nhận **chính sách của dự án**, đừng áp đặt một quy tắc chung lên mọi backend.

## 3. Các tầng kiểm thử console

Có ít nhất bốn mức kiểm tra, mỗi mức bảo vệ điều khác nhau:

| Mức | Quan sát điều gì? | Công cụ thường dùng | Không chứng minh được |
| --- | --- | --- | --- |
| Unit test nghiệp vụ | Tình huống có phát đúng sự kiện/mức log? | Spy/mock logger, ListAppender, CapturingHandler | Output thật ra stream nào và encode ra sao. |
| Test định dạng | Message, Throwable, MDC, pattern/JSON được format thế nào? | Layout/encoder thật + buffer byte | Collector/container nhận dữ liệu hay chưa. |
| Test standard streams trong JVM | Dữ liệu ghi qua `System.out` và `System.err` trong một đoạn code | `System.setOut`, `System.setErr`, `ByteArrayOutputStream` | Appender đã giữ stream khác trước khi thay thế; child process. |
| Integration test bằng tiến trình con | Đầu ra thực của JVM sau startup/configuration | `ProcessBuilder` + file/pipe, exit code | Collector bên ngoài đã lưu và hiển thị chính xác. |

Trong CI, nên kết hợp **test nhanh ở tầng sự kiện** với **một số integration test từ tiến trình mới**. Không cần khởi tạo cả server/container để kiểm tra mọi câu log nhỏ, nhưng cũng không nên chỉ kiểm tra `getFormattedMessage()` mà tuyên bố stdout/stderr production chính xác.

## 4. Những tiêu chí assert cần chọn rõ

Một test console có thể kiểm tra:

- **Có dòng cần thiết:** `event=order.created` xuất sau xử lý thành công.
- **Không có dòng cấm:** không có `ERROR` khi thao tác phục hồi thành công.
- **Phân luồng:** `INFO` vào stdout, `ERROR` vào stderr theo cấu hình đã công bố.
- **Level và nội dung:** message không chỉ chứa chữ `error` mà có đúng mức và mã sự kiện.
- **Số lần:** một thất bại cuối cùng có đúng một event code `payment.failed` ở đích quan sát.
- **Ngoại lệ:** stack trace và cause không bị bỏ khi cần chẩn đoán.
- **Dấu kết thúc:** các bản ghi text tách dòng đúng; nhiều dòng exception được xử lý đúng ở collector.
- **Unicode:** chữ tiếng Việt và ký tự ngoài ASCII không bị biến dạng.
- **Bảo mật:** bí mật giả không xuất trong bất kỳ stream hoặc trường nào.
- **Trạng thái tiến trình:** một lệnh lỗi có exit code khác 0 nếu đó là hợp đồng ứng dụng; chỉ có log ERROR **không bắt buộc** làm process exit 1.

Với logging nhiều thread, không nên assert một thứ tự tuyệt đối giữa mọi event trừ khi chương trình có synchronization bảo đảm thứ tự đó. Nếu hai luồng ghi độc lập, **thứ tự khi trộn stdout và stderr không phải một hợp đồng đáng tin**.

## 5. Ví dụ Java 17 chạy độc lập: bắt stdout và stderr trong cùng JVM

Ví dụ đầu tiên không cần thư viện logging ngoài JDK. Nó minh họa cách **tạm thời thay standard streams**, chạy một tình huống, lấy dữ liệu byte, giải mã UTF-8, đối chiếu nội dung **chính xác** và khôi phục stream ban đầu trong `finally`.

Lưu thành **`ConsoleCaptureTest.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ConsoleCaptureTest {
    private ConsoleCaptureTest() {
    }

    private static void scenario() {
        System.out.println("INFO|order.created|order_id=O-17");
        System.err.println("ERROR|payment.failed|code=DOWN");
    }

    private static void requireEquals(
            String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " mismatch: ["
                    + actual + "]");
        }
    }

    public static void main(String[] args) {
        PrintStream savedOut = System.out;
        PrintStream savedErr = System.err;

        ByteArrayOutputStream outBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream errBytes = new ByteArrayOutputStream();

        PrintStream captureOut =
                new PrintStream(outBytes, true, StandardCharsets.UTF_8);
        PrintStream captureErr =
                new PrintStream(errBytes, true, StandardCharsets.UTF_8);

        try {
            System.setOut(captureOut);
            System.setErr(captureErr);
            scenario();
        } finally {
            captureOut.flush();
            captureErr.flush();
            System.setOut(savedOut);
            System.setErr(savedErr);
            captureOut.close();
            captureErr.close();
        }

        String stdout = new String(
                outBytes.toByteArray(), StandardCharsets.UTF_8);
        String stderr = new String(
                errBytes.toByteArray(), StandardCharsets.UTF_8);

        String lineEnd = System.lineSeparator();
        requireEquals(
                "INFO|order.created|order_id=O-17" + lineEnd,
                stdout, "stdout");
        requireEquals(
                "ERROR|payment.failed|code=DOWN" + lineEnd,
                stderr, "stderr");

        System.out.println("PASS stdout");
        System.out.println("PASS stderr");
        System.out.println("PASS streams_separated");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ConsoleCaptureTest.java
java ConsoleCaptureTest
```

**Stdout chính xác:**

```text
PASS stdout
PASS stderr
PASS streams_separated
```

Lý do chỉ có ba dòng PASS: các dòng từ `scenario()` đã đi vào buffer thử nghiệm; sau `finally`, `System.out` và `System.err` được trả lại. Các thông báo PASS được in sau khi khôi phục, nên hiện ra trên console thật.

### Giải thích cơ chế

1. `ByteArrayOutputStream` giữ dữ liệu trong bộ nhớ; mỗi stream có **buffer riêng**.
2. `PrintStream(..., true, StandardCharsets.UTF_8)` biến chữ thành byte UTF-8 và bật auto-flush phù hợp.
3. `System.setOut` và `System.setErr` thay **tham chiếu toàn cục của process**; các lời gọi `System.out.println`/`System.err.println` sau đó thường đi qua stream tạm.
4. `finally` khôi phục hai stream ban đầu **ngay cả khi scenario ném lỗi**; không để test sau đọc nhầm buffer.
5. `captureOut.close()` và `captureErr.close()` chỉ đóng các stream thử nghiệm, không đóng `savedOut` hoặc `savedErr` của JVM.
6. `new String(bytes, UTF_8)` giải mã theo đúng charset mà test dùng để encode.
7. `System.lineSeparator()` phản ánh dấu kết thúc dòng của hệ điều hành; nhờ vậy ví dụ không hard-code `\n` trên hệ thống có `\r\n`.

**Giới hạn quan trọng:** bài test này kiểm tra dữ liệu đi qua tham chiếu `System.out/System.err` tại thời điểm gọi `scenario()`. Nó **không đủ** để xác minh một `ConsoleAppender` đã được khởi tạo trước đó và có thể đã giữ output stream của nó. Một số backend ghi qua stream đã lưu, file descriptor hoặc cơ chế khác; thay `System.out` sau startup có thể không bắt được log. Vì vậy, test output của backend nên dùng appender test hoặc **tiến trình con** như phần tiếp theo.

### Khi nào không nên dùng `System.setOut`?

Không nên dùng bừa trong một test suite chạy song song hoặc trong một ứng dụng đang phục vụ request, vì `System.out` và `System.err` là trạng thái **toàn cục**:

- Test A thay `System.out`, test B đồng thời in log và vô tình rơi vào buffer của A.
- Một thư viện có thể cache tham chiếu stream từ trước.
- Một thread khác vẫn ghi vào stream cũ hoặc stream mới ngoài mong muốn.
- Thao tác setOut không ảnh hưởng log được gửi trực tiếp tới file, socket hoặc native stream.

Nếu dùng kiểu test này, hãy cô lập các test liên quan, không chạy song song những test cùng sửa standard streams, và luôn khôi phục stream trong `finally`. Với hệ thống lớn, ưu tiên chạy một JVM con.

## 6. Ví dụ Java 17: kiểm thử console từ một tiến trình con

**Process-based test** quan sát từ bên ngoài process đích. Nó giúp kiểm tra startup, output thực, exit code và việc phân biệt stdout/stderr. Cách này gần điều kiện triển khai hơn việc chỉ thay `System.out` trong JVM của test.

Ta sẽ tạo **hai file Java** trong cùng thư mục:

```text
console-process-test/
├── ConsoleChild.java
└── ConsoleProcessTest.java
```

### 6.1. Chương trình cần kiểm thử: `ConsoleChild.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ConsoleChild {
    public static void main(String[] args) {
        PrintStream out =
                new PrintStream(System.out, true, StandardCharsets.UTF_8);
        PrintStream err =
                new PrintStream(System.err, true, StandardCharsets.UTF_8);

        out.println("READY|order=O-17|note=Đã tạo đơn");
        err.println("WARN|retry=1|note=Thử lại");

        if (args.length > 0 && "fail".equals(args[0])) {
            System.exit(7);
        }
    }
}
```

Ta chủ động dùng UTF-8 cho cả hai đầu ra để kiểm tra tiếng Việt không phụ thuộc charset mặc định của terminal. Hai wrapper trong ví dụ này **không đóng `System.out` hoặc `System.err`**; tiến trình kết thúc sẽ giải phóng các stream tương ứng.

Chạy với đối số `fail`: chương trình xuất hai dòng rồi thoát bằng **exit code 7**. Đây là hành vi ứng dụng **cố ý mô phỏng**; Logback/JUL không tự biến ERROR hay WARN thành exit code 7.

### 6.2. Chương trình kiểm thử: `ConsoleProcessTest.java`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public final class ConsoleProcessTest {
    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        String javaExe = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java"
        ).toString();

        Path stdoutFile = Files.createTempFile("console-check-", ".out");
        Path stderrFile = Files.createTempFile("console-check-", ".err");

        try {
            Process child = new ProcessBuilder(
                    javaExe,
                    "-cp",
                    System.getProperty("java.class.path"),
                    "ConsoleChild",
                    "fail"
            ).redirectOutput(stdoutFile.toFile())
             .redirectError(stderrFile.toFile())
             .start();

            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                child.destroyForcibly();
                child.waitFor();
                throw new AssertionError("child timeout");
            }

            String stdout = Files.readString(
                    stdoutFile, StandardCharsets.UTF_8);
            String stderr = Files.readString(
                    stderrFile, StandardCharsets.UTF_8);
            String newline = System.lineSeparator();

            require(child.exitValue() == 7, "wrong exit code");
            require(stdout.equals(
                    "READY|order=O-17|note=Đã tạo đơn" + newline),
                    "wrong stdout: " + stdout);
            require(stderr.equals(
                    "WARN|retry=1|note=Thử lại" + newline),
                    "wrong stderr: " + stderr);

            System.out.println("PASS exit_code=7");
            System.out.println("PASS stdout_utf8");
            System.out.println("PASS stderr_utf8");
        } finally {
            Files.deleteIfExists(stdoutFile);
            Files.deleteIfExists(stderrFile);
        }
    }
}
```

### 6.3. Biên dịch và chạy

Từ thư mục chứa hai tệp, bằng JDK 17+:

```bash
javac -encoding UTF-8 ConsoleChild.java ConsoleProcessTest.java
java -cp . ConsoleProcessTest
```

**Stdout chính xác của chương trình kiểm thử:**

```text
PASS exit_code=7
PASS stdout_utf8
PASS stderr_utf8
```

Chương trình con thoát với code 7, nhưng `ConsoleProcessTest` đã xem **7 là kết quả mong đợi**, nên chương trình kiểm thử vẫn hoàn thành thành công nếu mọi điều kiện đúng.

### Vì sao dùng file tạm cho output?

`ProcessBuilder` có thể mở pipe cho stdout/stderr, nhưng nếu test chỉ đọc một pipe trong khi child ghi rất nhiều vào pipe còn lại, buffer hệ điều hành có thể đầy và khiến child bị chặn. Ví dụ này **chuyển hướng hai stream ra hai file tạm** để không phải xử lý việc drain đồng thời và giữ đúng sự tách biệt.

Ngoài ra:

- `waitFor(10, TimeUnit.SECONDS)` ngăn test chờ mãi một child bị treo.
- Khi timeout, `destroyForcibly()` rồi `waitFor()` bảo đảm test cố gắng kết thúc child trước khi dọn dữ liệu.
- `redirectOutput` và `redirectError` giữ hai stream riêng, khác với `redirectErrorStream(true)` là cách **gộp stderr vào stdout**.
- Chờ child kết thúc trước khi đọc file giúp tránh lấy dữ liệu chưa hoàn tất.
- `Files.readString(..., UTF_8)` kiểm tra việc giải mã tiếng Việt đúng.
- `Files.deleteIfExists` dọn tài nguyên ngay cả khi assertion không đạt.

**Giới hạn của ví dụ:** nó khởi chạy class Java trong cùng thư mục bằng `java.class.path` của test; đối với fat JAR, module path, Maven Surefire hoặc container, cần điều chỉnh lệnh khởi động thành lệnh thật của artifact. Chính ưu điểm của phép thử là có thể dùng **startup command của production** để xác minh thực tế.

## 7. Kiểm thử ConsoleAppender của Logback

Nếu ứng dụng dùng **SLF4J + Logback**, `System.out.println` không tương đương `logger.info`. Ta phải kiểm tra cả cấu hình Logback để biết sự kiện nào vào stdout, sự kiện nào vào stderr.

Ví dụ một chính sách rõ ràng:

- Chỉ sự kiện mức **INFO** tới `System.out`.
- Chỉ sự kiện mức **ERROR** tới `System.err`.
- Cùng một sự kiện không được xuất vào cả hai stream.

Có thể cấu hình hai `ConsoleAppender` và hai `LevelFilter`.

### 7.1. Cấu trúc dự án

```text
logback-console-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackConsoleApp.java
        └── resources/
            └── logback.xml
```

### 7.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logback-console-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` cung cấp backend/provider SLF4J cùng các dependency cần thiết. Phiên bản cố định phục vụ tái lập bài học; **không phải tuyên bố về phiên bản bảo mật mới nhất**. Với ứng dụng thật, hãy tuân theo dependency management và khuyến cáo bảo mật tương thích với framework.

### 7.3. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="INFO_OUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <appender name="ERROR_ERR" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INFO_OUT" />
        <appender-ref ref="ERROR_ERR" />
    </root>
</configuration>
```

**Lý do cần LevelFilter ở cả hai appender:** nếu chỉ dùng `ThresholdFilter level="INFO"` cho stdout, nó thường chấp nhận **cả INFO, WARN và ERROR**, chứ không chỉ đúng INFO. Khi đó một sự kiện ERROR cũng có thể vào stdout và stderr, làm test “đúng một đích” thất bại.

`LevelFilter` trong cấu hình mẫu cho phép **đúng mức** được chỉ định. Vì vậy, `WARN` bị loại khỏi cả hai đích. Đây chỉ là **chính sách bài thực hành**, không phải khuyến nghị bỏ mọi WARN trong production. Một cấu hình thực tế có thể thêm appender WARN riêng hoặc thiết kế các ngưỡng bao phủ mọi mức cần lưu.

### 7.4. Tệp `src/main/java/demo/LogbackConsoleApp.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogbackConsoleApp {
    private static final Logger LOG =
            LoggerFactory.getLogger(LogbackConsoleApp.class);

    private LogbackConsoleApp() {
    }

    public static void main(String[] args) {
        LOG.info("event=start order_id={}", "O-17");
        LOG.error("event=failed code={}", "UPSTREAM_TIMEOUT");
    }
}
```

Biên dịch và chạy từ thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LogbackConsoleApp
```

**Hai bản ghi ứng dụng cần xuất (được tách theo stream):**

```text
stdout: INFO|LogbackConsoleApp|event=start order_id=O-17
stderr: ERROR|LogbackConsoleApp|event=failed code=UPSTREAM_TIMEOUT
```

Các nhãn `stdout:` và `stderr:` là chú thích của tài liệu, **không thuộc message thật**. Lệnh Maven có thể tạo thêm output từ công cụ chạy hoặc môi trường. Khi cả hai stream cùng hiển thị trên một cửa sổ terminal, thứ tự nhìn thấy giữa hai dòng có thể không giống tuyệt đối thứ tự lời gọi do hai stream được xử lý độc lập.

### 7.5. Kiểm thử thế nào cho đúng backend?

Để xác minh cấu hình trên:

1. Khởi chạy **ứng dụng bằng một process mới**, để Logback nạp `logback.xml` trong classpath của process đó.
2. Thu stdout và stderr **riêng biệt**; có thể dùng redirect shell hoặc `ProcessBuilder` theo cách của phần 6.
3. Khẳng định dòng INFO chỉ có ở stdout; dòng ERROR chỉ có ở stderr.
4. Khẳng định không có bản ghi trùng ở cùng đích.
5. Kiểm tra message và các trường ổn định, tránh phụ thuộc timestamp của một pattern khác.
6. Bổ sung ca test WARN và chứng minh behavior khớp chính sách; ở cấu hình học tập nó bị loại khỏi cả hai stream.
7. Đọc lại output nếu sửa dependency, file cấu hình hoặc cách launch; đừng suy luận từ source rằng `logback.xml` chắc chắn đã được nạp.

Nếu chạy thông qua Maven, nhớ phân biệt dòng từ Maven với dòng của chương trình. Để test nghiêm ngặt trên artifact cuối, nên thực thi **lệnh khởi động Java/JAR thực** thay vì so sánh toàn bộ stdout của Maven.

### Cảnh báo về `System.setOut` với Logback

`ConsoleAppender` có thể giữ tham chiếu tới `System.out` hoặc `System.err` trong quá trình khởi tạo. Nếu unit test thay `System.out` **sau khi backend đã khởi tạo**, appender có thể vẫn ghi qua stream cũ, khiến bài test bắt buffer rỗng dù người dùng vẫn thấy log.

Vì vậy, **không khẳng định `System.setOut` bắt được mọi Logback ConsoleAppender**. Với Logback, có thể kiểm thử sự kiện bằng `ListAppender<ILoggingEvent>`, output layout bằng appender test ghi vào `ByteArrayOutputStream`, hoặc kiểm thử **bằng subprocess** cho đường stdout/stderr thực sự.

## 8. Kiểm thử JUL (java.util.logging) console output

JDK cung cấp `java.util.logging.Logger` và `ConsoleHandler`. Một điểm dễ nhầm: `ConsoleHandler` chuẩn của JUL thường ghi lên **stderr**, ngay cả khi bản ghi có mức `INFO`. Mức `INFO` không tự khiến JUL chuyển sang stdout.

Ví dụ đoạn code minh họa:

```java
java.util.logging.Logger log =
        java.util.logging.Logger.getLogger("demo.payment");

log.info("event=payment.started");
```

Nếu default JUL ConsoleHandler đang được dùng, kết quả có thể xuất trên stderr với timestamp và tên logger do `SimpleFormatter` quyết định; không nên hard-code một dòng stdout cụ thể khi chưa kiểm soát cấu hình.

### Kiểm tra mức ở cả logger và handler

JUL có thể có mức ở logger nguồn và ở handler. Một log `FINE` bị logger nguồn chặn thì handler không nhận được. Nếu logger chấp nhận `FINE` nhưng handler đang ở `INFO`, bản ghi vẫn có thể bị loại tại handler.

Kiểm thử nên xét:

- Tên logger và mức hiệu lực.
- Handler gắn ở logger con/cha.
- `useParentHandlers` có dẫn tới log trùng không.
- Handler target/formatter có đúng stream và encoding không.
- Ngoại lệ được truyền vào `LogRecord` có hiện diện trong output không.

**Không đánh đồng mức JUL với Logback:** JUL dùng `SEVERE` cho mức nghiêm trọng cao, không có hằng `Level.ERROR`; Logback và Log4j 2 dùng `ERROR`.

### Test sự kiện JUL không cần bắt console

Khi mục tiêu chỉ là xác minh message, level và Throwable, có thể tạo một `Handler` giữ `LogRecord` vào bộ nhớ, tắt parent handlers trong test, rồi kiểm tra `getLevel()`, `getMessage()` và `getThrown()`. Đây là **test sự kiện**, không chứng minh formatter của ConsoleHandler đã xuất đúng text.

Khi mục tiêu là xác minh stderr trên tiến trình thật, hãy chạy subprocess và thu riêng stderr. Phân biệt hai mục tiêu sẽ tránh rất nhiều test dễ vỡ.

## 9. JUnit 5: tổ chức test mà không làm hỏng các test khác

Khi chuyển hai ví dụ Java 17 thành JUnit test, điều quan trọng nhất là **cô lập trạng thái**.

### Kiểm tra output từ một phương thức thuần Java

Có thể dùng pattern sau trong một test class đã có JUnit 5, `out`/`err` được tạo với UTF-8:

```java
PrintStream originalOut = System.out;
PrintStream originalErr = System.err;

try {
    System.setOut(capturedOut);
    System.setErr(capturedErr);

    // Gọi một phương thức cần thử trong cùng JVM.
    applicationAction.run();
} finally {
    System.setOut(originalOut);
    System.setErr(originalErr);
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: `capturedOut`, `capturedErr` và `applicationAction` phải được khai báo. Trong một bài test JUnit hoàn chỉnh, thêm `@Test`, assert và dọn các buffer/stream thử nghiệm; chạy tuần tự hoặc khóa tài nguyên chia sẻ để tránh hai test cùng thay standard streams.

JUnit 5 có các cơ chế điều phối chạy song song và resource lock, nhưng hiệu lực chỉ đầy đủ khi mọi test sử dụng tài nguyên toàn cục cùng tuân thủ quy tắc cô lập. Không thể mong một resource lock trong một test ngăn toàn bộ thư viện ngoài tiếp tục ghi ra stdout.

### Nếu chỉ muốn kiểm tra sự kiện Logback

Có thể dùng `ListAppender<ILoggingEvent>` trong test để thu sự kiện mà không đụng `System.out`. Khi đó kiểm tra:

- `getLevel()` có bằng `Level.ERROR`/`Level.INFO` không.
- `getLoggerName()` có khớp thành phần phát log không.
- `getFormattedMessage()` có mã sự kiện và ngữ cảnh cần thiết không.
- `getThrowableProxy()` có hiện diện khi ghi ngoại lệ không.
- Các trường MDC và key-value được gắn đúng theo backend/version không.

Sau test cần gỡ và dừng appender tạm, hoàn nguyên mức logger và additivity trong `finally`; loggers của backend thường là đối tượng chia sẻ trong JVM, không chỉ sống trong một test method.

**Điểm giới hạn:** `ListAppender` chứng minh sự kiện đã tới appender test, **không chứng minh** `ConsoleAppender` thực tế ghi đúng stdout/stderr. Hãy có thêm integration test cho stdout/stderr khi đó là yêu cầu quan trọng.

## 10. Kiểm tra chuỗi output: những gì ổn định và không ổn định

### 10.1. Khi có thể so sánh toàn bộ chuỗi

So sánh nguyên văn rất phù hợp với mẫu xác định:

```text
INFO|order.created|order_id=O-17
```

nếu code và pattern không chứa dữ liệu thay đổi theo lần chạy. Trong test, nên dựng expected với `System.lineSeparator()` nếu chương trình dùng `println` theo nền tảng.

Đặc biệt, trong ví dụ `ConsoleCaptureTest.java`, so sánh hai stream riêng và cả dấu newline là một hợp đồng có chủ đích.

### 10.2. Khi không nên so sánh toàn bộ chuỗi

Pattern thực tế thường có:

```text
%d{ISO8601} %-5level [%thread] %logger - %msg%n
```

Timestamp và tên thread có thể thay đổi. Stack trace có số dòng source cũng thay đổi sau refactor.

Ở trường hợp này:

- Parse hoặc trích riêng level, event code, trace ID và message.
- Kiểm tra timestamp hợp lệ, nằm trong khoảng thời gian hợp lý.
- Kiểm tra logger name theo mục đích (đầy đủ hay rút gọn).
- Với exception, kiểm tra loại, cause và dấu hiệu stack trace chứ không phụ thuộc số dòng.
- Với logging bất đồng bộ, chờ sự kiện/tiến trình hoàn tất có giới hạn.
- Khi nhiều thread ghi log, so sánh tập bản ghi hoặc nhóm theo correlation ID thay vì buộc thứ tự toàn cục.

### 10.3. Kiểm tra hiện tượng log trùng

Một sự kiện `order.created` xuất hai lần có thể do:

1. Code gọi logger hai lần.
2. Logger con và root cùng gắn appender khi additivity/propagation vẫn bật.
3. Hai appender cùng ghi vào một stream.
4. Một framework và một bridge logging được cấu hình không nhất quán.
5. Collector nhận lại bản ghi do retry rồi nhân đôi.
6. Một thao tác nghiệp vụ thực sự chạy hai lần do retry hoặc client gửi lại.

Test nên xác định **đích đếm**: trong stdout của một process, trong stderr, trong từng file, hay trong kho tập trung. Hai appender cố ý xuất cùng một sự kiện tới **hai đích khác nhau** không nhất thiết là lỗi.

## 11. Charset, Unicode và newline trong console output

### Charset

Chuỗi Java là Unicode, nhưng đầu ra console là các **byte**. Một logger/encoder có thể dùng UTF-8, trong khi terminal hoặc collector giải mã theo bảng mã khác. Kết quả là chữ tiếng Việt bị biến dạng.

Đối với test:

- Khi tạo `PrintStream` thử nghiệm, chỉ định `StandardCharsets.UTF_8`.
- Khi đọc `byte[]` hoặc file, dùng `StandardCharsets.UTF_8`.
- Với Logback hoặc Log4j 2, chỉ định charset tương ứng trong encoder/layout khi cần.
- Khi test terminal thật, kiểm tra cả nơi phát và nơi đọc, đừng chỉ sửa `toString()` của object.
- Với byte stream đã qua collector, cần kiểm tra charset xuyên toàn pipeline.

Ở ví dụ tiến trình con, code chủ động dùng `PrintStream(..., UTF_8)` và test đọc `Files.readString(..., UTF_8)` để bắt lỗi Unicode một cách xác định.

### Dấu xuống dòng

`System.out.println` dùng dấu kết thúc dòng theo môi trường. Với text layout, conversion `%n` thường thêm newline thích hợp. Khi test trên Windows và Linux:

- Đừng hard-code `\n` nếu hợp đồng là “newline theo OS”.
- Nếu dự án quy định LF cố định (ví dụ JSON Lines gửi qua giao thức), có thể assert `\n` theo hợp đồng đó.
- Nếu **bình thường hóa CRLF → LF**, chỉ làm ở test mà dự án chấp nhận hai dạng; không chuẩn hóa nếu bạn cần phát hiện lỗi định dạng.
- Đừng dùng `trim()` tùy tiện khi muốn kiểm tra chính xác khoảng trắng, newline hoặc nội dung trống. `trim()` có thể che lỗi thiếu/dư ký tự.

### Multiline và stack trace

Một bản ghi exception có thể xuất nhiều dòng vật lý. Nếu hệ thống quan sát xem “một dòng = một sự kiện”, parser có thể chia stack trace thành nhiều bản ghi giả.

Test cần phân biệt:

- **Số lần logger phát sự kiện:** được kiểm tra ở tầng sự kiện hoặc bằng event ID.
- **Số dòng console:** có thể lớn hơn số sự kiện khi có stack trace.
- **Số record được collector lưu:** phụ thuộc cấu hình multiline hoặc structured logging.

Nếu contract yêu cầu một JSON object mỗi dòng, dùng encoder JSON đúng chuẩn với escaping và kiểm tra từng dòng JSON parse được, không tự ghép JSON thô bằng pattern.

## 12. Kiểm tra mức log và đích nhận

Một ma trận test nên ghi rõ đầu vào và kết quả:

| Tình huống | Level | Mục tiêu kiểm tra |
| --- | --- | --- |
| Tạo đơn thành công | INFO | Có sự kiện thành công trong kênh dự kiến, không có ERROR giả. |
| Retry tạm thời lỗi rồi phục hồi | WARN/DEBUG (theo chính sách) | Không ghi “thất bại cuối cùng” nhầm. |
| Thanh toán cuối cùng thất bại | ERROR/SEVERE | Có event code, error code, trace và Throwable khi cần. |
| DEBUG bị tắt | DEBUG | Không tạo output DEBUG, dù code có lời gọi. |
| Logger ghi vào appender có filter | INFO/WARN/ERROR | Stream nhận đúng những mức filter cho phép. |
| Mất stdout collector | Không phụ thuộc level | Console có dữ liệu nhưng có thể thiếu trong kho tập trung. |

**Không có quy tắc chuẩn bắt buộc WARN phải vào stderr.** Một số ứng dụng đưa tất cả mức ra stdout và thêm trường `level`; một số khác tách theo severity. Test phải xuất phát từ sơ đồ logging đã được quyết định, không chỉ từ tên mức.

## 13. Kiểm tra dữ liệu nhạy cảm và log injection

Console log có thể được gửi tới dịch vụ bên ngoài hoặc được giữ nhiều tháng. Vì vậy, “chỉ là console” không có nghĩa là dữ liệu có thể xuất tùy ý.

Hãy tạo test dùng **token giả**, ví dụ:

```text
SECRET_TEST_TOKEN_123
```

Sau đó bảo đảm **cả stdout và stderr** không chứa chuỗi này trong các tình huống lỗi. Kiểm tra cả:

- Message đã format.
- MDC/ThreadContext hoặc các key-value bổ sung.
- Exception message và stack trace.
- Các sự kiện của thư viện/SDK có thể in request hoặc header.
- Mọi appender cùng xuất tới console/file.
- Log collector, nếu có phép test tích hợp.

Ví dụ cần tránh:

```java
log.info("Authorization={}", authorizationHeader);
```

Đây là đoạn minh họa khi có biến `log` và `authorizationHeader`. Dùng placeholder `{}` **không tự che token**. Log injection cũng có thể xảy ra nếu một giá trị đầu vào chứa newline rồi bị ghi vào console như nhiều dòng giả. Nên dùng trường có kiểu, encoder có escaping phù hợp và chính sách ghi dữ liệu được phép.

**Không dùng secret thật trong bài test**. Với thông tin nhạy cảm, thử bằng chuỗi giả có hình dạng tương tự.

## 14. Những bẫy khi test console trong CI/CD

### 14.1. Maven/Gradle cũng ghi vào console

Một lệnh như:

```bash
mvn test
```

có thể in thông tin build, warning và lỗi của plugin, ngoài output ứng dụng. Nếu test so sánh toàn bộ stdout của `mvn` với một câu cố định, rất dễ bị hỏng do môi trường hoặc phiên bản plugin thay đổi.

Thực hành tốt là:

1. Chạy ứng dụng JAR/class riêng hoặc dùng API của test runner để chỉ quan sát output của child process.
2. Nếu vẫn cần kiểm tra output từ Maven, lọc theo định danh rõ như `event_code`, không coi mọi dòng build là log ứng dụng.
3. Lưu riêng stdout và stderr trong CI khi cần chẩn đoán.
4. Khi test fail, in phần output đã bắt được vào báo cáo test **sau khi khôi phục stream**, tránh làm nhiễu dữ liệu đang assert.

### 14.2. Console có thể bị redirect ngoài ứng dụng

Shell có thể gửi stdout vào file và stderr đến màn hình; container có thể gom cả hai; IDE có thể tô màu hoặc nhóm theo thread. Kiểm tra output bằng cách mở terminal **không đủ** để biết byte nào thuộc stream nào. Subprocess với redirect tách biệt cho phép xác minh rõ ràng.

### 14.3. Color/ANSI và chế độ tương tác

Một số backend hoặc framework có thể dùng ANSI escape codes để tô màu log. Output nhìn bằng mắt là `ERROR` nhưng chuỗi thực có thêm ký tự điều khiển. Khi test:

- Tắt màu nếu hợp đồng production là plain text.
- Hoặc parse/bỏ ANSI theo quy tắc được phép nếu màu chỉ là trình bày, không phải thông tin cần bảo vệ.
- Không strip toàn bộ ký tự điều khiển một cách mù quáng khi cần phát hiện log injection.

### 14.4. Các test chạy song song

Khi nhiều thread/process ghi đồng thời, log có thể xen kẽ theo thứ tự scheduler. Một test ổn định sẽ:

- Gắn event ID hoặc request ID.
- Đồng bộ các tác vụ khi cần assert thứ tự.
- Chờ có timeout rõ ràng.
- Kiểm tra tập hợp bản ghi thay vì giả định trình tự.
- Không để một test `System.setOut` ảnh hưởng test khác.

### 14.5. Test timeout và tiến trình mồ côi

Một subprocess bị treo có thể khiến CI treo theo. Dùng `waitFor(timeout, unit)`, hủy tiến trình khi quá hạn và thu kết quả chẩn đoán. Nếu chương trình tạo **các tiến trình con khác**, việc hủy một PID cha chưa chắc đã chấm dứt toàn bộ cây tiến trình; với workflow phức tạp cần quản lý process tree hoặc sandbox của CI.

## 15. Bảng lỗi thường gặp khi kiểm thử console output

| Dấu hiệu | Khả năng xảy ra | Hướng xử lý |
| --- | --- | --- |
| Buffer `System.out` rỗng nhưng màn hình có log | Backend đã giữ stream trước khi `setOut` | Dùng subprocess hoặc test appender/encoder. |
| Có INFO trong stderr với JUL | JUL ConsoleHandler thường xuất stderr | Kiểm tra backend và handler, không suy luận từ level. |
| ERROR xuất cả stdout và stderr | Hai appender dùng ngưỡng chồng nhau | Dùng LevelFilter hoặc chính sách route không chồng lấn khi cần. |
| Hai dòng được in khác thứ tự | Hai standard stream được hiển thị/trộn độc lập | Assert từng stream, không ép thứ tự giữa stdout và stderr. |
| Test qua Windows thất bại | CRLF, charset hoặc shell redirection khác | Dùng `System.lineSeparator()` và charset tường minh. |
| Chữ Việt bị lỗi | Encoder hoặc nơi đọc không cùng UTF-8 | Kiểm tra byte đầu ra và decode đúng. |
| Test pass nhưng collector không có log | Chỉ kiểm tra JVM, chưa kiểm tra pipeline | Bổ sung integration test staging với collector. |
| Test timeout | Child bị block trên pipe hoặc deadlock/khởi động chậm | Drain đồng thời, redirect ra file hoặc gộp stream có chủ đích; đặt timeout. |
| Một ERROR thành nhiều dòng | Stack trace nhiều dòng | Kiểm tra event và cấu hình multiline. |
| Chỉ log message, không thấy cause | Truyền `ex.getMessage()` thay vì Throwable | Kiểm tra event có Throwable và formatter xuất stack trace. |
| Không có log DEBUG | Logger level/filter chặn | Kiểm tra mức hiệu lực, handler/appender, provider. |
| Chạy `mvn exec` tạo nhiều dòng lạ | Maven/plugin cũng ghi vào console | Phân biệt output ứng dụng và công cụ chạy. |
| Log chứa secret | Đưa dữ liệu nhạy cảm vào event hoặc Throwable | Test token giả, bảo vệ mọi stream và appender. |
| Test sau bị lỗi kỳ lạ | Quên khôi phục `System.out/System.err` | Luôn `finally`, cô lập test toàn cục. |
| Đã ghi console nhưng process exit 0 | Logging không quyết định exit code | Test exit code như một hợp đồng riêng. |

## 16. Bài tập vận dụng

### Bài 1 — Phân biệt hai stream

Cho code:

```java
System.out.println("INFO|ready");
System.err.println("ERROR|failed");
```

Hỏi: có thể khẳng định dòng ERROR sẽ xuất **sau** dòng INFO khi nhìn trong terminal không?

**Gợi ý:** Không. Hai câu lệnh được gọi theo thứ tự đó trong thread, nhưng stdout và stderr là hai stream độc lập, có thể được terminal/IDE/collector gom theo cách không bảo toàn thứ tự giữa hai luồng. Hãy assert riêng từng stream.

### Bài 2 — Kiểm tra cửa sổ debug

Một logger cấu hình root level `INFO`. Code có:

```java
log.debug("event=diagnostic id={}", id);
```

Tại sao thay pattern để thêm `%msg` vẫn không thấy `DEBUG`?

**Gợi ý:** Sự kiện có thể đã bị loại ở logger level trước khi tới formatter/appender. Cần kiểm tra mức hiệu lực và filter, không chỉ sửa layout.

### Bài 3 — Sửa test gây ảnh hưởng toàn cục

Một test gọi `System.setOut(new PrintStream(buffer))` rồi kết thúc mà không khôi phục. Hệ quả?

**Gợi ý:** Các test và thư viện khác có thể tiếp tục ghi vào buffer, dẫn đến output thiếu hoặc assertion chồng chéo. Dùng `try/finally` và giữ tham chiếu stream gốc. Khi có parallel tests, nên dùng subprocess.

### Bài 4 — Tránh deadlock khi đọc child process

Một child ghi lượng dữ liệu rất lớn vào cả stdout và stderr. Parent chỉ gọi `child.getInputStream().readAllBytes()` rồi mới đọc stderr. Rủi ro là gì?

**Gợi ý:** Child có thể bị chặn vì stderr pipe đầy và không thể kết thúc; parent lại đợi stdout hoàn tất. Dùng hai thread đọc đồng thời, redirect vào hai file, hoặc `redirectErrorStream(true)` nếu **không cần** phân biệt stream.

### Bài 5 — Assert output Logback

Với cấu hình phần 7, hãy trả lời:

1. Sự kiện INFO đi đâu?
2. Sự kiện ERROR đi đâu?
3. Sự kiện WARN đi đâu?
4. Vì sao thay `LevelFilter` bằng `ThresholdFilter level="INFO"` ở stdout có thể làm xuất trùng ERROR?

**Gợi ý:** INFO vào stdout, ERROR vào stderr, WARN bị cả hai filter loại (theo cấu hình **minh họa**). Threshold INFO chấp nhận cả mức cao hơn, nên ERROR có thể vào stdout lẫn stderr. Trong production, cần chính sách đầy đủ cho WARN thay vì vô tình làm mất cảnh báo.

### Bài 6 — Kiểm thử secret

Một đoạn code log token giả thông qua `logger.error("failed token={}", token)`. Test có nên chỉ kiểm tra `System.out` không?

**Gợi ý:** Không. Bản ghi có thể được định tuyến vào stderr hoặc nhiều appender khác. Test mọi đích cần được bảo vệ, exception message và structured fields; không dùng token thật.

### Bài 7 — Unit test và integration test

Unit test thấy `ILoggingEvent.getFormattedMessage()` đúng, nhưng ứng dụng chạy thật không có log trong hệ thống tập trung. Liệt kê các tầng cần kiểm tra.

**Gợi ý:** Provider/backend đang chạy, logger level/filter, appender/target, formatter/encoder, stdout/stderr hoặc file, collector/agent, parser/multiline, index, quyền truy cập và thời gian tìm kiếm. `ILoggingEvent` đúng chỉ là một phần của đường đi.

## 17. Checklist trước khi coi console output test đã đạt

1. **Biết chính xác backend:** JUL, Logback hay Log4j 2; không suy luận chỉ từ import Java.
2. **Biết stream mục tiêu:** stdout, stderr, file hay cả hai.
3. **Có ca thành công và thất bại:** không chỉ thử một dòng ERROR.
4. **Kiểm tra event và output tách biệt:** unit test semantic + integration test stream.
5. **Không làm bẩn trạng thái JVM:** khôi phục `System.out/System.err` và logger/appender nếu thay.
6. **Chống treo subprocess:** timeout, dọn process và quản lý buffer/pipe.
7. **Kiểm tra charset:** UTF-8, đặc biệt với Unicode và tiếng Việt.
8. **Kiểm tra định dạng:** level, event code, message, context, newline và Throwable.
9. **Kiểm tra log trùng và mất:** trong từng stream, appender và collector; không chỉ đếm số dòng có chữ ERROR.
10. **Kiểm tra bảo mật:** secret giả không xuất ở stdout, stderr, stack trace, MDC hoặc các kênh khác.
11. **Không assert dữ liệu động như hằng số:** timestamp, thread và số dòng stack trace phải có cách kiểm tra phù hợp.
12. **Chạy bằng artifact/lệnh thật khi cần:** output từ Maven/IDE không thay cho kết quả của JVM deployed.
13. **Xác minh collector nếu đó là hợp đồng:** thấy console có log không mặc nhiên nghĩa là hệ thống tập trung nhận được.

**Kết luận:** Kiểm thử console output không chỉ là “thấy chữ in ra màn hình”. Hãy xác minh **sự kiện → logger/filter → appender/encoder → stdout hoặc stderr → collector** theo đúng mục tiêu. Dùng `ByteArrayOutputStream` cho code đơn giản trong một JVM, dùng test appender để kiểm tra sự kiện logger và dùng `ProcessBuilder` khi cần khẳng định đầu ra console thật, exit code, charset và cấu hình runtime.