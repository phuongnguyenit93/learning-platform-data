# Đọc stacktrace từ nguyên nhân gốc thay vì thông báo tổng quát trong Gradle

## 1. Vấn đề: dòng “BUILD FAILED” không phải nguyên nhân gốc

Khi một Gradle build thất bại, console thường kết thúc bằng những dòng như:

```text
FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:compileJava'.

BUILD FAILED in 4s
```

Nếu chỉ đọc `BUILD FAILED` hoặc `Execution failed for task`, ta mới biết **điều gì không hoàn tất**, chưa biết **vì sao nó xảy ra**. Nguyên nhân có thể là import Java sai, dependency không tải được, plugin không tương thích, lỗi JVM, một bài test không đạt, task custom code ném exception hoặc một dịch vụ ngoài từ chối kết nối.

Một Gradle invocation có thể chứa nhiều lớp lỗi:

1. **Gradle build-level message**: build fail, lỗi ở cấu hình hay thực thi.
2. **Task/plugin wrapper**: ví dụ `TaskExecutionException` hoặc `GradleException` do Gradle/plugin ném hoặc bọc.
3. **Domain-specific exception**: ví dụ `IllegalArgumentException` kèm thông điệp từ plugin.
4. **Underlying cause**: ví dụ `NumberFormatException` vì cấu hình port không phải số.
5. **Điểm bắt đầu trong code của bạn**: file, method và line gây lỗi thực tế.
6. **Bằng chứng bổ trợ**: compiler diagnostic, test XML/HTML, dependency graph, JVM/daemon log.

**Mục tiêu bài học:** đọc báo lỗi theo các lớp này, lần theo `Caused by` có ý nghĩa, phân biệt lỗi gốc với triệu chứng, tái hiện tối thiểu, sau đó sửa **đúng vị trí**. Không “chữa” bằng những flags khiến task bị bỏ qua hoặc exception không còn hiển thị.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt `Where`, `What went wrong`, `Try` và `Exception is` trong Gradle failure report.
- Dùng đúng `--stacktrace`/`-s`, `--full-stacktrace`/`-S`, `--info` và `--scan`.
- Đọc các tầng `Caused by:`, `Suppressed:` và `... N more` trong Java stacktrace.
- Xác định task path, phase, file, line, plugin hoặc external tool gây lỗi.
- Không nhầm lỗi `JavaExec`/JUnit/`javac` với lỗi nội bộ của Gradle.
- Tái hiện và xử lý các lỗi dependency/plugin/JDK/daemon/configuration cache.
- Viết bug report có dữ liệu đủ để đồng đội tái hiện mà không lộ credentials.

## 2. Cấu trúc chính thức của Gradle failure report

Một báo lỗi Gradle có thể gồm những phần sau; **không phải mọi lỗi đều hiển thị đủ cả bốn**.

| Phần | Cần đọc để trả lời | Lưu ý |
| --- | --- | --- |
| `* Where:` | File/script và line liên quan đến lỗi là gì? | Có thể vắng mặt, nhất là với lỗi runtime/task |
| `* What went wrong:` | Task/plugin/build operation nào thất bại, thông điệp nào được báo? | Thường chứa wrapper message, có thể có nguyên nhân bên dưới bằng các dấu `>` |
| `* Try:` | Gradle/plugin gợi ý bước chẩn đoán nào? | Là gợi ý chung hoặc theo loại lỗi, không tự chứng minh nguyên nhân |
| `* Exception is:` | Chuỗi exception và các stack frames là gì? | Thường có khi dùng `--stacktrace` |

Theo tài liệu Gradle hiện hành, `Execution failed for task` cho biết lỗi phát sinh **khi thực thi task**, chứ không phải trong lúc cấu hình build. Nếu lỗi ở cấu hình, có thể thấy `A problem occurred configuring project`, `Could not compile build file` hoặc thông điệp khác tùy tình huống.

### 2.1. Đọc từ trên xuống để định vị, rồi đi vào nguyên nhân

Một báo lỗi giả lập có kiểm soát:

```text
FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':validatePort'.
> demoPort must be an integer: not-a-number

* Try:
> Run with --stacktrace option to get the stack trace.

BUILD FAILED in 2s
```

Thông điệp `Execution failed for task ':validatePort'` cho biết **task nào** gặp sự cố; `demoPort must be an integer` cung cấp **dấu hiệu miền nghiệp vụ**. Khi chạy lại với `--stacktrace`, sẽ thấy các frames và các exception lớp dưới. Đó là cách biết lỗi đến từ chuỗi input, mapping của Provider hay code Gradle plugin.

Các dòng trong khối trên là **minh họa cấu trúc**, không phải transcript bảo đảm đúng từng ký tự trên mọi Gradle version.

### 2.2. Không coi `Try` là bản sửa lỗi

Gradle có thể đề xuất:

```text
> Run with --stacktrace option to get the stack trace.
> Run with --info or --debug option to get more log output.
> Run with --scan to get full insights from a Build Scan.
```

Những lựa chọn này **tăng thông tin quan sát**. Chúng không sửa dependency missing, không làm compiler code hợp lệ, không nâng JVM và không khắc phục test assertion.

### 2.3. Một build có nhiều failures

Nếu dùng `--continue`, Gradle cố tiếp tục các task độc lập có thể chạy được và có thể báo:

```text
Build completed with 2 failures.
```

Khi đó cần phân tích **mỗi failure riêng**, tìm lỗi có thể gây ra lỗi khác theo dependency chain. Không chỉ chọn stacktrace cuối cùng. Tuy nhiên `--continue` không có nghĩa Gradle sẽ chạy các tasks phụ thuộc một task đã fail như thể nó thành công.

## 3. Stacktrace Java: lớp bọc, nguyên nhân và call frames

Một exception có thể được ném, bắt rồi bọc lại nhiều lần:

```text
Gradle task wrapper
   |
   v
GradleException("demoPort must be an integer")
   |
   +-- caused by NumberFormatException(
           "For input string: not-a-number"
       )
           |
           +-- first relevant parser/config line
```

Trong Java:

```java
try {
    int port = Integer.parseInt(raw);
} catch (NumberFormatException cause) {
    throw new IllegalArgumentException(
            "Invalid port configuration: " + raw,
            cause
    );
}
```

Đây là **mảnh code**, không phải một file Java hoàn chỉnh. Exception ngoài cho biết ngữ cảnh mà ứng dụng muốn báo; exception trong giữ lại lý do kỹ thuật cụ thể. Mọi công cụ có thể bọc thêm exception mà không làm nguyên nhân trong `cause` biến mất.

### 3.1. `Caused by` nghĩa là gì?

Một stacktrace minh họa rút gọn:

```text
java.lang.IllegalArgumentException: Invalid port configuration: abc
    at demo.PortParser.parse(PortParser.java:17)
    at demo.Main.main(Main.java:8)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at demo.PortParser.parse(PortParser.java:12)
    ... 1 more
```

Cách đọc:

1. Exception ngoài là `IllegalArgumentException`: API đã diễn giải lỗi cho người gọi.
2. `Caused by` trỏ tới `NumberFormatException`: Java không chuyển `abc` thành số.
3. Frame `PortParser.java:12` cho biết **chỗ parse input**.
4. Frame `Main.java:8` cho biết đường đi gọi đến parser.
5. `... 1 more` là cách Java **rút gọn những frames chung với exception bao ngoài**; không phải mất một lỗi khác.

**Không luôn luôn chọn exception cuối cùng là “thủ phạm duy nhất”.** Exception cuối sâu nhất thường là nguyên nhân trực tiếp, nhưng cách sửa cần xét context phía trên. Ví dụ `UnknownHostException` là lỗi kỹ thuật dưới cùng, còn wrapper chỉ ra chính **repository URL bị cấu hình sai**, đó mới là nơi nên sửa.

### 3.2. First useful frame quan trọng hơn nhiều frames `org.gradle`

Trong stacktrace dài, các package:

```text
org.gradle.api.internal.*
org.gradle.execution.*
org.gradle.internal.*
java.base/*
jdk.internal.*
org.codehaus.groovy.*
```

thường xuất hiện vì Gradle điều phối task, Java reflection hoặc Groovy/Kotlin DSL runtime. Chúng có ích để biết đường đi, nhưng **không nhất thiết là nơi cần sửa**.

Nên tìm frame đầu tiên có ý nghĩa thuộc:

- `dev.company.buildlogic.*` — custom Gradle plugin.
- `build.gradle.kts` hoặc `settings.gradle.kts` — script DSL.
- `demo.PortParser.*` — Java application logic.
- `org.junit.jupiter.*`/test class source — test thực thi.
- Package của third-party plugin mà bạn đang áp dụng.
- `javax.net.ssl.*`, `java.net.*` — dấu hiệu TLS/network.
- `org.gradle.api.artifacts.*` — dependency resolution context.

Một frame của Gradle chỉ là **điểm phát hiện hoặc đóng gói lỗi**; xác định nguyên nhân cần kết hợp message và frames của code tương ứng.

### 3.3. `Suppressed` khác `Caused by`

Trong Java:

- `Caused by:` thể hiện chuỗi nguyên nhân chính qua `Throwable.getCause()`.
- `Suppressed:` thể hiện exception bổ sung, thường do `try-with-resources` khi đóng tài nguyên bị lỗi trong lúc một exception khác đã xảy ra.
- `... N more` là rút gọn những frames trùng, không phải một lỗi mới.

Ví dụ:

```text
java.io.IOException: Failed while processing input
    at demo.Processor.run(Processor.java:...)
    Suppressed: java.io.IOException: Closing stream failed
        at demo.Processor.close(Processor.java:...)
Caused by: java.nio.file.NoSuchFileException: config/input.json
    at java.base/...
```

Đây là **sơ đồ minh họa**, không phải log chạy từ lab. Có thể lỗi đóng stream đáng chú ý, nhưng `NoSuchFileException` thường là điểm nên kiểm tra đầu tiên trong trường hợp này.

### 3.4. Khi nào không có `Caused by`?

Có những lỗi nguyên thủy không được bọc, ví dụ `IllegalArgumentException` được ném trực tiếp. Nếu stacktrace không có `Caused by`, hãy xem message, frames đầu tiên của code đang được sửa và input thực tế. Đừng đi tìm `Caused by` bằng mọi giá.

## 4. Chọn cấp độ log theo nhu cầu

| Tùy chọn | Thể hiện thêm gì? | Khi dùng |
| --- | --- | --- |
| `--stacktrace` / `-s` | Stacktrace có rút gọn cho exceptions | **Ưu tiên đầu tiên** khi lỗi chưa rõ |
| `--full-stacktrace` / `-S` | Full stacktrace rất dài | Khi rút gọn che khuất quan hệ classloader/plugin |
| `--info` / `-i` | Sự kiện lifecycle/resolution/task chi tiết hơn | Khi cần biết Gradle làm gì **trước khi lỗi** |
| `--debug` / `-d` | Logging rất chi tiết | Chỉ khi cần, có khả năng lộ dữ liệu nhạy cảm |
| `--console=plain` | Log không có rich progress redraw | CI/ticket/logs dễ đọc |
| `--warning-mode all` | Hiện mọi deprecation warnings | Kiểm tra plugin/script compatibility |
| `--scan` | Build Scan/timeline/env/test/failures | Khi chính sách bảo mật cho phép |
| `--continue` | Cố chạy những tasks độc lập sau lỗi | Thu nhiều lỗi trong một invocation |
| `--rerun-tasks` | Không dựa vào task up-to-date | Tái hiện lỗi task đang bị skip |
| `--no-build-cache` | Không restore outputs từ Build Cache | Phân biệt stale cache và task execution |
| `--no-configuration-cache` | Không reuse configuration state | Cô lập lỗi liên quan configuration cache |

Lệnh tối thiểu nên thử với một task đã biết:

```bash
./gradlew :app:compileJava --stacktrace --console=plain
```

Nếu không có subproject `:app`, dùng task path đúng trong build, ví dụ `./gradlew compileJava ...`.

### 4.1. `--stacktrace` khác `--full-stacktrace`

Theo Gradle Logging Guide, `--stacktrace` đã in stacktrace đủ hữu ích cho nhiều trường hợp và rút gọn bớt frames lặp; `--full-stacktrace` in rất nhiều frames của Groovy/reflection/Gradle internals. Không cần dùng full trace mặc định chỉ vì log dài trông “chuyên nghiệp” hơn.

### 4.2. `--info` bổ sung ngữ cảnh trước lỗi, không thay `--stacktrace`

Ví dụ:

```bash
./gradlew :app:compileJava --info --stacktrace --console=plain
```

Thông tin bổ sung có thể cho biết `javac` command/options, compile inputs, repository request hoặc task execution status. Với lỗi network hoặc dependency resolution, log trước khi exception có thể quan trọng hơn hàng trăm stack frames.

### 4.3. Cảnh báo khi bật `--debug` và `--scan`

- `--debug` có thể ghi URLs, environment, task inputs hoặc dữ liệu nhạy cảm; không chia sẻ raw logs từ CI có secrets.
- Build Scan có thể bao gồm console log, build environment, dependency versions và đường dẫn source. Chỉ tạo/chia sẻ nếu tổ chức cho phép.
- Không paste access tokens, private repo credentials hoặc customer data vào issue công khai.
- Redact bằng quy trình có kiểm soát, đừng xóa những dòng cần thiết để xác định nguyên nhân.

### 4.4. Gradle properties cho stacktrace

Có thể cấu hình mặc định:

```properties
org.gradle.logging.stacktrace=all
```

theo Logging Guide, nhưng với team không nên bật logs verbose cho mọi job nếu chúng làm log quá dài hoặc lộ dữ liệu. Trong điều tra lỗi cụ thể, CLI `--stacktrace` rõ ràng hơn và dễ thu hồi khi hoàn tất.

## 5. Quy trình tìm nguyên nhân gốc trong 8 bước

**Bước 1 — Giữ lại câu lệnh thực sự đã lỗi.** Ví dụ `./gradlew :app:test --stacktrace`. Nếu chỉ có ảnh chụp đoạn `BUILD FAILED`, thông tin thường không đủ.

**Bước 2 — Chọn failure block đầu tiên có nghĩa.** Nếu dùng `--continue`, có nhiều blocks. Phân biệt lỗi chính với lỗi lan truyền.

**Bước 3 — Ghi task path/phase.** `:compileJava` là compilation, `:test` là test, `:run` là JavaExec, `:jar` là packaging, `:help`/settings fail là configuration/plugin resolution. Không sửa class Java nếu Gradle chưa biên dịch đến nó.

**Bước 4 — Đọc `What went wrong` và `Where`.** Nếu có file/line, đến chính file đó. Nếu chỉ có generic wrapper, bật `--stacktrace`.

**Bước 5 — Dò chuỗi `Caused by` và các diagnostic quan trọng.** Tìm nguyên nhân cụ thể như `NumberFormatException`, `cannot find symbol`, `SSLHandshakeException` hoặc `No matching toolchains found`. Đọc các messages trong context; một frame sâu không thay thế được message của task bên ngoài.

**Bước 6 — Xác định lớp chịu trách nhiệm.** Build script, plugin, Java compiler, test framework, Gradle JVM, external repository, cache, IDE hay CI environment?

**Bước 7 — Tái hiện tối thiểu và thay đúng một thứ.** Cố định Gradle Wrapper, JDK, task command và dữ liệu; tránh vừa xóa caches vừa đổi plugin versions vừa sửa code. Với lỗi test, chạy lại test cụ thể sau khi sửa.

**Bước 8 — Xác nhận sửa lỗi qua build đầy đủ.** Sau khi chứng minh fix với task nhỏ, chạy quality gate như `./gradlew clean check`. Không dùng `-x test`, `ignoreFailures=true` hoặc `--continue` để che lỗi.

### 5.1. Cây quyết định nhanh

```text
Build failed
   |
   +-- Trước khi tasks chạy?
   |      |
   |      +-- settings/plugins DSL → plugin ID/version/repositories
   |      +-- build script compilation → file/line/DSL syntax
   |      +-- project configuration → extension/property/provider
   |
   +-- Task execution thất bại?
   |      |
   |      +-- compileJava → javac error đầu tiên / compileClasspath
   |      +-- test → test report + assertion exception
   |      +-- run/JavaExec → spawned JVM stderr + exit code
   |      +-- custom task → exception của plugin/task và @TaskAction
   |      +-- dependency resolve → module/repository/auth/SSL
   |      +-- packaging → output paths / duplicate resources
   |
   +-- Daemon mất kết nối?
          |
          +-- daemon log, JVM crash, OOM, runner termination
```

Không có một “nguyên nhân gốc” giống nhau cho mọi failure. Chọn nguồn bằng chứng theo **phase và tool thực thi**.

## 6. Lab Java 17: nhìn thấy wrapper và nguyên nhân sâu

Bài thực hành có hai đường lỗi chủ động:

1. Một **custom Gradle task** `validatePort` nhận `-PdemoPort=...`, bọc `NumberFormatException` trong `GradleException`.
2. Một **Java application** parse port và có thể fail trong JVM con được Gradle `run` khởi động; Gradle nhìn thấy `JavaExec` exit code 1, còn Java stderr ghi exception của ứng dụng.

Ngoài ra có JUnit 5 tests hợp lệ để học cách phân biệt Gradle test wrapper với assertion failure.

### 6.1. Cấu trúc thư mục

```text
gradle-root-cause-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew                       (sinh từ Gradle Wrapper nếu chưa có)
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/
    │   ├── PortParser.java
    │   └── Main.java
    └── test/java/demo/
        └── PortParserTest.java
```

Yêu cầu JDK 17 và Gradle Wrapper version tương thích. JUnit libraries cần được tải từ Maven Central hoặc cache phù hợp. Không cần Docker, database hoặc network API ngoài dependencies của JUnit.

### 6.2. `settings.gradle.kts`

```kotlin
rootProject.name = "gradle-root-cause-lab"
```

### 6.3. `build.gradle.kts`: custom task có chain `Caused by`

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
}

tasks.test {
    useJUnitPlatform()
}

abstract class ValidatePort : DefaultTask() {
    @get:Input
    abstract val portText: Property<String>

    @TaskAction
    fun validate() {
        val raw = portText.get()

        val port = try {
            raw.toInt()
        } catch (cause: NumberFormatException) {
            throw GradleException(
                "demoPort must be an integer: " + raw,
                cause
            )
        }

        if (port !in 1..65535) {
            throw GradleException(
                "demoPort must be between 1 and 65535: " + port
            )
        }

        logger.lifecycle("validated demoPort=" + port)
    }
}

tasks.register<ValidatePort>("validatePort") {
    portText.set(
        providers.gradleProperty("demoPort")
            .orElse("not-a-number")
    )
}
```

**Điểm đọc lỗi:**

- `providers.gradleProperty("demoPort")` lấy Gradle project property dạng String.
- Default `not-a-number` cố ý không chuyển được thành `Int`, nên task fail.
- `catch (NumberFormatException)` giữ nguyên root exception làm `cause`.
- `GradleException` thêm message có ý nghĩa cho người học/build.
- `@get:Input` mô tả input; task chỉ log, không khai báo output file và không phải task cacheable.
- Với port hợp lệ 1–65535, task in một dòng lifecycle và thành công.
- Lỗi xảy ra **khi task action chạy**, nên wrapper `Execution failed for task ':validatePort'` là phù hợp.

**Vì sao không bắt mọi `Exception`?** Catch quá rộng dễ che lỗi thật. Chỉ bắt lỗi mà mã có thể thêm context hữu ích; với `GradleException` trong nhánh range validation, giữ message tường minh.

### 6.4. `PortParser.java`: source Java có context riêng

**File `src/main/java/demo/PortParser.java`:**

```java
package demo;

public final class PortParser {
    private PortParser() {
    }

    public static int parse(String raw) {
        final int port;

        try {
            port = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException(
                    "Port must be a decimal integer: " + raw,
                    cause
            );
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "Port must be between 1 and 65535: " + port
            );
        }

        return port;
    }
}
```

Phương thức này làm hai việc riêng:

1. Kiểm tra **định dạng**: không chuyển được thành số → ném `IllegalArgumentException` với `NumberFormatException` làm cause.
2. Kiểm tra **khoảng hợp lệ**: số nằm ngoài 1..65535 → ném `IllegalArgumentException` trực tiếp, không có NumberFormatException bên dưới.

Điều này giúp thấy: không phải mọi failure đều có nested cause. Nếu port là `70000`, lỗi xuất phát từ business validation, không phải integer parsing.

### 6.5. `Main.java`: entrypoint Java 17

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String raw = args.length == 0 ? "8080" : args[0];
        int port = PortParser.parse(raw);

        System.out.println("ready on port " + port);
    }
}
```

Với tham số hợp lệ, stdout chính xác:

```text
ready on port 8080
```

Không dùng Gradle `JavaExec` chỉ để xuất stdout này; Java program có thể chạy độc lập bằng `javac` và `java` như phần sau.

### 6.6. `PortParserTest.java`: JUnit 5 tests hợp lệ

**File `src/test/java/demo/PortParserTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class PortParserTest {
    @Test
    void acceptsValidPort() {
        assertEquals(8080, PortParser.parse("8080"));
    }

    @Test
    void preservesRootCauseForInvalidInteger() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> PortParser.parse("abc")
        );

        assertInstanceOf(
                NumberFormatException.class,
                failure.getCause()
        );
    }

    @Test
    void rejectsOutOfRangePortWithoutNumberFormatCause() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> PortParser.parse("70000")
        );

        assertEquals(
                "Port must be between 1 and 65535: 70000",
                failure.getMessage()
        );
    }
}
```

Ba tests này **đều có chủ đích pass**, không cần sửa code rồi xóa test chỉ để CI xanh. Test thứ hai khẳng định `getCause()` giữ `NumberFormatException` — đây là một contract hữu ích trong ứng dụng cần error reporting chất lượng.

### 6.7. Gradle Wrapper

Nếu repository chưa có Wrapper, dùng bản Gradle tương thích đã cài một lần tại root:

```bash
gradle wrapper
```

Sau đó dùng `./gradlew` (Linux/macOS) hoặc `.\gradlew.bat` (PowerShell/Windows). Đừng tải Wrapper JAR từ nguồn ngẫu nhiên hoặc bỏ `gradle-wrapper.jar` khỏi repo nhưng vẫn kỳ vọng `./gradlew` hoạt động.

### 6.8. Chạy baseline thành công

Từ root của lab trên Linux/macOS:

```bash
./gradlew clean test classes --console=plain
./gradlew validatePort -PdemoPort=8080 --console=plain
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test classes --console=plain
.\gradlew.bat validatePort -PdemoPort=8080 --console=plain
.\gradlew.bat run --quiet
```

Dòng do custom task in:

```text
validated demoPort=8080
```

Stdout của `Main.main` khi chạy `run --quiet`:

```text
ready on port 8080
```

Gradle có thể in thêm tên task, BUILD SUCCESSFUL và status. Những khối trên chỉ là **dòng chính xác từ mã demo**, không phải toàn bộ transcript Gradle.

### 6.9. Chạy Java độc lập với `javac`/`java`

Không phụ thuộc JUnit/Gradle application task:

Linux/macOS:

```bash
mkdir -p build/manual-classes
javac -d build/manual-classes src/main/java/demo/PortParser.java src/main/java/demo/Main.java
java -cp build/manual-classes demo.Main 8080
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -d build\manual-classes src\main\java\demo\PortParser.java src\main\java\demo\Main.java
java -cp build\manual-classes demo.Main 8080
```

Stdout:

```text
ready on port 8080
```

Đây là bằng chứng source Java đúng trong trường hợp happy path. Lỗi của custom Gradle task `validatePort` và lỗi Java application parse port **không phải cùng một exception object**, dù cùng bắt nguồn từ ý tưởng “port không hợp lệ”.

## 7. Thí nghiệm có chủ đích: Gradle task thất bại vì nested cause

### 7.1. Kích hoạt lỗi

Từ root:

```bash
./gradlew validatePort --stacktrace --console=plain
```

Vì `demoPort` chưa được cấp, Provider trả `not-a-number`. Task gọi `String.toInt()` rồi ném `NumberFormatException`; `GradleException` bọc nó với message giải thích đúng cấu hình.

Trong log, tìm **những thành phần chính**:

```text
* What went wrong:
Execution failed for task ':validatePort'.
> demoPort must be an integer: not-a-number

* Exception is:
...
Caused by: org.gradle.api.GradleException:
  demoPort must be an integer: not-a-number
...
Caused by: java.lang.NumberFormatException:
  For input string: "not-a-number"
...
```

Đây là **minh họa rút gọn**; số lượng `Caused by`, frames và indentation có thể khác theo Gradle/JDK version. Không dựa vào việc transcript phải trùng tuyệt đối; hãy nhận diện **exception types**, message do mình viết và chain `cause`.

### 7.2. Phân tích tầng lỗi

1. `Execution failed for task ':validatePort'` là **wrapper Gradle task**.
2. `demoPort must be an integer` là **domain message** của custom task.
3. `NumberFormatException` là **kỹ thuật parse root cause**.
4. `ValidatePort.validate()` (cùng line tương ứng) là **first useful code frame**.
5. `providers.gradleProperty("demoPort")` cho biết **nguồn input** là Gradle property.
6. Cách sửa: truyền một số hợp lệ hoặc sửa nguồn cấu hình, **không cần thay JDK hoặc xóa Gradle caches**.

### 7.3. Sửa lỗi đúng cách

```bash
./gradlew validatePort -PdemoPort=8080 --console=plain
```

Dòng Gradle task in chính xác:

```text
validated demoPort=8080
```

Có thể thử:

```bash
./gradlew validatePort -PdemoPort=70000 --stacktrace
```

Trường hợp này **không còn NumberFormatException** vì `70000` parse thành Int được. Task ném `GradleException` ở range validation; thông điệp:

```text
demoPort must be between 1 and 65535: 70000
```

Điều đó chứng minh cách đọc nguyên nhân: cùng task, nhưng tùy input sẽ có **những lỗi thuộc lớp khác nhau**.

### 7.4. Tránh overfitting vào một stacktrace

Nếu môi trường đã khai báo `demoPort` mặc định từ `gradle.properties` hoặc command line, lab có thể không fail với input vắng mặt. Để chắc chắn tạo lỗi có chủ đích:

```bash
./gradlew validatePort -PdemoPort=abc --stacktrace --console=plain
```

Thí nghiệm cần diễn ra trong lab/bản sao của dự án; không chỉnh property production để tạo lỗi.

## 8. Lỗi của JavaExec khác lỗi Gradle task code

Custom task `validatePort` chạy trong Gradle task action. Nhưng `run` của Application plugin là `JavaExec`: nó khởi động **một JVM con** để thực thi `demo.Main`.

### 8.1. Kích hoạt lỗi Java app

Trong lab, cấu hình `run` nhận args qua CLI:

```bash
./gradlew run --args="abc" --stacktrace --console=plain
```

PowerShell:

```powershell
.\gradlew.bat run --args="abc" --stacktrace --console=plain
```

`Main` nhận `abc`, gọi `PortParser.parse` rồi exit do uncaught `IllegalArgumentException`.

Ở console có thể thấy **hai cụm khác nhau**:

**JVM con in stderr đại diện cho nguyên nhân ứng dụng:**

```text
Exception in thread "main" java.lang.IllegalArgumentException:
  Port must be a decimal integer: abc
    at demo.PortParser.parse(PortParser.java:...)
    at demo.Main.main(Main.java:...)
Caused by: java.lang.NumberFormatException:
  For input string: "abc"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at demo.PortParser.parse(PortParser.java:...)
```

**Gradle báo task JavaExec thất bại ở lớp ngoài:**

```text
* What went wrong:
Execution failed for task ':run'.
> Process 'command ...java...' finished with non-zero exit value 1
```

Các khối trên được **rút gọn và diễn giải**, không phải transcript nguyên văn đầy đủ. Giá trị path/JDK/line phụ thuộc môi trường.

### 8.2. Vì sao root cause không nhất thiết nằm cuối Gradle `Exception is`?

Gradle nhìn thấy process `java` kết thúc với exit code 1 và có thể ném `ExecException`/`ProcessExecutionException` liên quan. **Java application exception được JVM con ghi trên stderr**, không phải một `Throwable` Gradle có thể traverse qua `getCause()`.

Do đó chỉ kéo xuống cuối Gradle `--full-stacktrace` có thể bỏ qua lỗi thực tế từ `PortParser.parse` đã xuất hiện **phía trên** trong output của process con.

**Quy tắc:** đối với `JavaExec`, `Exec`, Docker, Maven hoặc bất kỳ tool subprocess nào, đọc **stderr/stdout của tiến trình con trước generic process exit wrapper**.

### 8.3. Tái hiện riêng mà không chạy Gradle `run`

Sau `./gradlew classes`:

```bash
java -cp build/classes/java/main demo.Main abc
```

Đây là Java process độc lập; terminal sẽ hiển thị `IllegalArgumentException` và `NumberFormatException` mà không có Gradle task wrapper. Command trả non-zero exit code khi exception không được bắt.

Sửa:

```bash
java -cp build/classes/java/main demo.Main 8080
```

Stdout chính xác:

```text
ready on port 8080
```

Kỹ thuật này hữu ích khi cần biết lỗi ở **app runtime** hay **Gradle task orchestration**.

## 9. Thí nghiệm JUnit: generic `test` failure và assertion gốc

JUnit failures là loại phổ biến khiến developer chỉ thấy:

```text
Execution failed for task ':test'.
> There were failing tests. See the report at: ...
```

Đó là wrapper hợp lệ. Root cause thường nằm trong **test report hoặc test JVM output**, không phải trong các frames của Gradle Test task.

### 9.1. Tạo một test thất bại có chủ đích

Trên **bản sao của lab**, thêm **mảnh method sau vào `PortParserTest`**:

```java
@Test
void intentionallyFailsForDiagnosisOnly() {
    assertEquals(9000, PortParser.parse("8080"));
}
```

Đây là **mảnh code đặt bên trong class đã có imports**, không phải một Java source file độc lập. Nó cố tình yêu cầu 9000 trong khi parser trả 8080.

Chạy:

```bash
./gradlew test --tests "demo.PortParserTest.intentionallyFailsForDiagnosisOnly" --rerun-tasks --stacktrace --console=plain
```

`--rerun-tasks` dùng ở đây để chắc chắn task test được thực thi lại trong lab; nó không phải fix cho assertion sai.

### 9.2. Tìm nguyên nhân trong test report

Sau lỗi, xem:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.PortParserTest.xml
```

JUnit assertion thường chỉ ra dạng:

```text
org.opentest4j.AssertionFailedError:
expected: <9000> but was: <8080>
```

Các ký tự định dạng có thể khác theo JUnit version, nhưng **mâu thuẫn expected 9000 vs actual 8080** là điều cần sửa hoặc lý giải.

`--stacktrace` của Gradle chủ yếu giải thích Gradle Test task thất bại. Để tìm test method và assertion line, **test report/stacktrace của JUnit** thường là nguồn tốt hơn.

### 9.3. Cấu hình test logging chi tiết hơn

Mảnh tùy chọn để thêm vào `build.gradle.kts` của lab:

```kotlin
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

tasks.test {
    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
        showCauses = true
        showStackTraces = true
    }
}
```

**Không** xem đoạn này là bắt buộc để Gradle test pass. Nó tăng log khi test fail; với CI công khai, cân nhắc dữ liệu nhạy cảm trong exception messages của tests.

### 9.4. Đảm bảo test failure vẫn là failure

Không sửa bằng:

```kotlin
tasks.test {
    ignoreFailures = true
}
```

hoặc:

```bash
./gradlew build -x test
```

Các cách này chỉ **bỏ hoặc che tín hiệu lỗi**, không sửa expected/actual. Sau thí nghiệm, **xóa method cố tình fail**, rồi chạy lại:

```bash
./gradlew clean check --console=plain
```

Ba tests hợp lệ ban đầu phải pass. Nếu `test` báo `NO-SOURCE` dù đã có source, phải điều tra source set/test engine thay vì coi là thành công.

## 10. Kotlin DSL / Groovy DSL lỗi ở cấu hình thay vì task execution

Không phải lỗi Gradle nào cũng cần đợi đến task action.

### 10.1. Kotlin DSL syntax và unresolved reference

Ví dụ đoạn lỗi cố ý trong `build.gradle.kts`:

```kotlin
tasks.register("badConfig") {
    unknownMethodName()
}
```

Khi Gradle biên dịch Kotlin DSL script, có thể thấy diagnostic:

```text
e: .../build.gradle.kts:...: Unresolved reference: unknownMethodName
```

Đây là **mảnh code cố tình sai và diagnostic minh họa**, không thêm vào lab chạy bình thường. Nguyên nhân ở **Kotlin script compilation**, không phải task `badConfig` được chạy rồi fail.

Nên sửa identifier/import/API theo đúng Gradle Kotlin DSL. `--stacktrace` thêm call frames compiler/runtime, nhưng **dòng diagnostic có file:line và `Unresolved reference`** thường chỉ ra lỗi chính xác hơn.

### 10.2. Missing plugin trong `plugins` DSL

Ví dụ minh họa:

```kotlin
plugins {
    id("dev.example.plugin-that-does-not-exist") version "1.0.0"
}
```

Nếu plugin chưa được publish, plugin repo không chứa marker hoặc ID/version sai, Gradle có thể fail trong plugin resolution trước khi project tasks chạy. Cần kiểm tra:

- `settings.gradle.kts` → `pluginManagement.repositories`.
- Plugin ID và version.
- Plugin marker artifact/implementation repository.
- Authentication, VPN/proxy/offline mode.
- Plugin-producing included build nếu plugin đang phát triển local.

**Không** cố sửa bằng cách thêm plugin implementation module vào `app.dependencies.implementation`. Project application dependencies không thay `plugins` DSL resolution.

### 10.3. Groovy DSL property errors

Trong Groovy DSL, một property hoặc method không tồn tại có thể gây:

```text
Could not get unknown property 'someProperty' for project ...
```

hoặc:

```text
Could not find method someMethod() for arguments ...
```

Nên xem `Where` và frame script DSL đầu tiên. Một stacktrace có nhiều Groovy meta-class frames là bình thường; **đừng sửa Groovy internals** khi lỗi là property sai tên ở build script.

### 10.4. Configuration vs execution

| Dấu hiệu | Phase đáng nghi | Cách kiểm |
| --- | --- | --- |
| `Could not compile build file` | Script compilation | File + line, Kotlin/Groovy DSL API |
| `A problem occurred configuring project` | Configuration | `plugins`, extensions, task configuration |
| `Plugin [id: ...] was not found` | Plugin resolution | Settings plugin repositories |
| `Execution failed for task ':x'` | Task execution | Task action, tool output, inputs |
| `Process ... finished with non-zero exit value 1` | External/Java process | Child stderr/stdout |
| `There were failing tests` | Test execution/reporting | JUnit XML/HTML và test frames |
| `Gradle build daemon disappeared unexpectedly` | Daemon/process | Daemon logs, memory/crash |

Phase xác định nơi debug: một lỗi Gradle Kotlin DSL compiler không được giải quyết bằng cách chỉnh Java source `src/main/java`, và một assertion failure không được giải quyết bằng cách đổi repository.

## 11. Compilation errors: tìm dòng `javac` báo lỗi, không chỉ task wrapper

Ví dụ bạn sửa `Main.java`, dùng một class chưa import hoặc class không có trên compile classpath:

```java
package demo;

public final class BrokenMain {
    public static void main(String[] args) {
        UnknownHelper.call();
    }
}
```

Đây là **file Java minh họa cố tình không biên dịch**, không được thêm vào lab nếu muốn clean build pass.

`javac` thường báo:

```text
.../BrokenMain.java:5: error: cannot find symbol
        UnknownHelper.call();
        ^
  symbol:   variable UnknownHelper
  location: class BrokenMain
```

Gradle chỉ bao ngoài:

```text
Execution failed for task ':compileJava'.
> Compilation failed; see the compiler output ...
```

**Root cause để sửa nằm trong compiler diagnostic**, không phải một frame nội bộ của Gradle JavaCompile.

### 11.1. Nếu thiếu library

Nếu code import `org.apache.commons.lang3.StringUtils` nhưng project chưa khai báo dependency, hãy xem:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration compileClasspath
```

Lệnh thứ hai chỉ hữu ích khi module xuất hiện trong dependency graph được resolve; nếu project không yêu cầu module, cần xem `dependencies { implementation(...) }` và repositories đúng project.

### 11.2. Lỗi bytecode/JDK

Nếu có:

```text
UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
```

thì class được compile cho Java version cao hơn JVM đang load nó. Cần xác định **JVM nào**:

- Gradle daemon JVM đang load plugin/build logic?
- Java compiler/toolchain?
- Test JVM?
- JavaExec child process?
- Production runtime?

Chạy:

```bash
./gradlew --version
./gradlew javaToolchains
java -version
```

Gradle JVM và Java toolchain không đồng nhất. Không tự đổi `java.toolchain` ở app khi lỗi thực sự do Gradle plugin code load trên daemon JVM.

## 12. Dependency resolution: đọc tọa độ, repository và nguyên nhân network

Với lỗi dạng:

```text
Could not resolve all files for configuration ':runtimeClasspath'
> Could not find org.example:missing-library:1.0.0.
```

đây là **tọa độ minh họa**, không khẳng định artifact tồn tại. Cần hỏi:

1. Module `group:artifact:version` chính xác không?
2. Repository đã cấu hình ở đúng scope chưa?
3. Đây là project dependency repository hay plugin repository?
4. Có credential/token phù hợp không?
5. Server trả 404, 401, 403 hay timeout/SSL error?
6. Build có bật `--offline` nhưng cache chưa có artifact không?
7. Dependency constraints, version catalogs/locks có đang yêu cầu version không tồn tại?
8. Proxy/mirror có bỏ POM/module metadata hoặc bị network chặn không?

### 12.1. Phân biệt thông điệp bọc và nguyên nhân

Ví dụ:

```text
Could not resolve all files for configuration ':compileClasspath'
  > Could not resolve com.example:library:2.0.0
    > Could not GET 'https://repo.example.org/...'
      > PKIX path building failed
```

Nguyên nhân kỹ thuật có thể là **TLS trust chain**/certificate, không phải `implementation` thiếu. Nếu là 401/403 thì là quyền truy cập, nếu 404 là artifact/path không có ở repository đã hỏi.

Đây là mẫu diagnostic **minh họa**; không dùng URL `example.org` làm repository thật. Đừng tắt SSL verification hoặc in credentials để “xác minh” lỗi.

### 12.2. Lệnh chẩn đoán đúng graph

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency library --configuration runtimeClasspath
./gradlew help --stacktrace --info
```

Chọn configuration và project đúng lỗi. Nếu lỗi ở `:app:compileClasspath`, lệnh ở root `runtimeClasspath` có thể trả graph khác hoặc không có configuration đó.

### 12.3. `--refresh-dependencies` không chữa sai coordinates

```bash
./gradlew build --refresh-dependencies --stacktrace
```

chỉ có ích nếu metadata/cache state nghi vấn; Gradle sẽ kiểm tra lại dependencies theo policy. Nó không làm một module không tồn tại xuất hiện trong repository và không sửa credential bị từ chối.

Không bắt đầu bằng xóa toàn bộ `~/.gradle` vì việc đó có thể làm mất cache, ảnh hưởng các project khác và che dấu nguyên nhân gốc.

## 13. Plugin và classpath errors: tìm đúng nơi plugin chạy

Gradle plugin là code thực thi **trong build process**, không phải Java application runtime library. Khi xảy ra:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassCastException: ...
```

hãy tìm:

- Class/method nào thiếu hoặc không còn tương thích.
- Tên plugin và version thực tế được áp dụng.
- Plugin đã biên dịch cho Gradle/JDK version nào.
- Xung đột giữa plugin classpaths, `buildscript` và included build `build-logic`.
- Version của transitive dependency trên plugin classpath.
- Gradle Wrapper version thay đổi gần nhất.
- Frame đầu tiên thuộc implementation package của plugin.

### 13.1. `NoSuchMethodError` có thể do binary incompatibility

Một plugin được compile khi method có tồn tại nhưng chạy với version của API/library không còn cùng chữ ký có thể ném `NoSuchMethodError`. Lỗi không nhất thiết ở Java source của ứng dụng.

Cần đối chiếu plugin changelog/compatibility matrix, Gradle runtime version và dependency tree của **build logic**, không ngẫu nhiên thêm library vào `app:implementation`.

### 13.2. `NoClassDefFoundError` không phải lúc nào là thiếu direct dependency

Class có thể không có trên runtime classpath, bị exclude sai, được compile cho JVM không hợp hoặc fail initialization trong trường hợp cụ thể. Đọc full exception message, chain `Caused by` và những frames liên quan.

Với class initialization failure, exception như `ExceptionInInitializerError` hoặc `NoClassDefFoundError: Could not initialize class...` có thể chỉ vào static initializer đã fail trước đó. Cần tìm **lần lỗi đầu tiên trong cùng process**, không chỉ hiện tượng ở lần load lại sau đó.

### 13.3. Lỗi ở included build `build-logic`

Nếu stacktrace trỏ đến `:build-logic:compileJava` hoặc task/plugin của build logic, hãy xem dependencies của included build đó, không chỉ project app. Với một included build có settings riêng, có thể xem:

```bash
./gradlew -p build-logic dependencies --configuration runtimeClasspath
```

Lệnh này áp dụng nếu repository thực sự có thư mục `build-logic` là một Gradle build độc lập. Nó **không** phải lệnh của lab `gradle-root-cause-lab` (lab không có included build).

## 14. Test task thất bại: phân biệt assertion, test engine và worker process

Một `:test` failure có thể thuộc những nhóm khác nhau.

| Dấu hiệu | Nguyên nhân gợi ý | Bằng chứng đúng |
| --- | --- | --- |
| `expected X but was Y` | Assertion không đạt | JUnit XML/HTML và test method |
| `No tests found for given includes` | Filter `--tests` không khớp | Test class/method/package và test engine |
| `Test worker failed to start` | JVM/process args, path, môi trường | Test worker stderr, JDK, Gradle test logs |
| `ClassNotFoundException` ở test JVM | Test runtime dependency thiếu | `testRuntimeClasspath` |
| `NO-SOURCE` | Không có test source theo Gradle model | Source sets và test detection |
| `OutOfMemoryError` | Heap của test worker thiếu hoặc test leak | Worker JVM args/heap dumps |
| `Test task failed` nhưng report còn 0 tests | Test engine/configuration không đúng | Test framework/dependencies, JUnit Platform |

Gradle Java Test task có `testClassesDirs` và `classpath` riêng. Khi gặp lỗi JUnit, phải chọn **test runtime classpath**, không nhầm với main runtime.

### 14.1. Chạy một test hoặc method cụ thể

```bash
./gradlew test --tests "demo.PortParserTest"
./gradlew test --tests "demo.PortParserTest.acceptsValidPort"
```

Nếu lỗi liên quan timing/concurrency, việc chạy một test riêng có thể làm nó biến mất do isolation khác. Khi đó vẫn cần tái hiện trong full suite và xem shared state/order dependencies, không tuyên bố bug đã hết.

### 14.2. Đọc XML trước khi chỉnh `--stacktrace` lần thứ năm

```text
build/test-results/test/TEST-demo.PortParserTest.xml
build/reports/tests/test/index.html
```

Các file này chứa test name, assertions, stacktrace và output theo Gradle/JUnit reporting. Gradle wrapper `There were failing tests` chỉ tổng hợp kết quả.

Nếu project có nhiều custom `Test` tasks, đường dẫn report khác có thể dùng tên task; không giả định tất cả dưới `test`.

## 15. Gradle daemon biến mất: stacktrace có thể không chứa nguyên nhân

Một tình huống đặc biệt:

```text
Gradle build daemon disappeared unexpectedly
```

Nghĩa là Gradle client không còn giao tiếp được với daemon. Nếu process bị OS kill do memory pressure, JVM crash hoặc CI runner bị hủy, daemon có thể không kịp ghi một Java stacktrace bình thường vào console.

Nguồn cần xem:

- Daemon log trong `GRADLE_USER_HOME/daemon/<gradle-version>/daemon-<pid>.out.log`.
- OS/CI OOM kill event và resource charts.
- JVM crash logs `hs_err_pid*.log` hoặc heap dumps nếu có.
- Gradle JVM flags, `org.gradle.jvmargs`, worker count.
- Antivirus/security tools hoặc filesystem permissions.
- Runner timeout, container memory limits hoặc disk full.

### 15.1. Thí nghiệm chẩn đoán ít thay đổi nhất

```bash
./gradlew --version
./gradlew help --stacktrace --info --console=plain
./gradlew check --max-workers=1 --stacktrace --console=plain
```

`--max-workers=1` là **thí nghiệm giảm concurrency** để cô lập resource/race; nó không phải fix tổng quát. Nếu chạy được với một worker nhưng fail ở bốn workers, cần xem memory/parallel state. Không giữ flag giới hạn workers mãi mà không giải thích hậu quả hiệu năng.

### 15.2. `--no-daemon` không hoàn toàn tương đương “không bao giờ fork JVM”

Gradle có thể khởi chạy một **single-use daemon** ngay cả với `--no-daemon` trong một số điều kiện JVM args khác nhau. Vì vậy khi debug JDK/daemon issue, kiểm tra chính Gradle runtime JVM và daemon logs, không chỉ sự hiện diện của CLI flag.

## 16. Configuration Cache và lỗi state của plugin

Gradle Configuration Cache có thể tái sử dụng configuration state. Nếu custom task/plugin giữ `Project` hoặc sử dụng services không đúng thời điểm, Gradle có thể báo lỗi khi lưu hoặc dùng lại cache.

Thử:

```bash
./gradlew check --configuration-cache --stacktrace --console=plain
```

Khi fail, ngoài `--stacktrace` hãy tìm Configuration Cache problems report mà Gradle in path trong log (thường dưới `build/reports/configuration-cache/` hoặc theo layout do Gradle tạo). Nó có thể chỉ ra **task property, object reference và lý do không serialize được**.

Đối chứng để cô lập:

```bash
./gradlew check --no-configuration-cache --stacktrace --console=plain
```

Nếu không lỗi khi tắt cache, đó là **bằng chứng định hướng** đến compatibility/state vấn đề; không phải lý do để luôn tắt cache mà không điều tra.

### 16.1. Một anti-pattern task action

Mảnh minh họa trong `build.gradle.kts`:

```kotlin
tasks.register("badTask") {
    doLast {
        // Đọc Project model tại execution phase có thể làm task không
        // tương thích với Configuration Cache.
        println(project.name)
    }
}
```

Đây là **mảnh minh họa** chứ không nằm trong lab runnable. Với task thật, truyền dữ liệu từ configuration phase qua `Property`/`Provider` vào typed task, tránh capture `Project` trong task action. Đọc problems report rồi sửa đúng code/path.

### 16.2. Không coi `problems=warn` là “fix”

```bash
./gradlew check --configuration-cache --configuration-cache-problems=warn
```

Chế độ warning có thể hữu ích trong giai đoạn migration, nhưng không làm plugin tự tương thích. Với release/quality gate, cần xử lý violations thật trước khi tin vào cache reuse.

## 17. IDE: chẩn đoán qua Gradle invocation thực tế

Khi IntelliJ IDEA, Android Studio hoặc VS Code hiển thị một banner như “Gradle sync failed”, UI có thể rút gọn exception chain. Nên xem cửa sổ Gradle Build/Sync output hoặc chạy command tương đương qua Wrapper để lấy failure blocks đầy đủ.

### 17.1. Các yếu tố IDE dễ khác terminal

| Khác biệt | Triệu chứng |
| --- | --- |
| IDE Gradle JVM khác terminal JAVA_HOME | `UnsupportedClassVersionError`, incompatible Gradle |
| IDE chạy task `idea`/sync thay vì `build` | Lỗi configuration/plugin xuất hiện sớm |
| IDE bật Configuration Cache khác CLI | Lỗi serialize/reuse state |
| IDE dùng Offline Work | Dependency/plugin không tải được |
| IDE import composite/included builds khác | Plugin/build-logic resolution sai |
| IDE thêm VM options/properties | Behavior khác shell |
| IDE dùng test runner riêng | Test output và filtering khác |
| IDE cache/index chưa cập nhật | Unresolved symbols trên IDE dù CLI compile pass |

### 17.2. So sánh environment có cấu trúc

Chạy từ terminal tại root:

```bash
./gradlew --version
./gradlew help --stacktrace --console=plain
./gradlew tasks --all --console=plain
```

Sau đó đối chiếu IDE Gradle JVM setting, Gradle distribution/Wrapper setting, environment/properties và task targets. Không xóa IDE caches như phản xạ đầu tiên khi logs đã chỉ ra một lỗi thiếu dependency/JDK rõ ràng.

### 17.3. Khi CLI pass nhưng IDE fail

Cần biết IDE đang gọi **đúng command và JVM** nào. Gradle sync có thể thực hiện thêm model queries hoặc áp dụng init scripts. CLI `build` pass không tự chứng minh tất cả IDE tooling APIs ổn, nhưng là bằng chứng để khoanh vùng khác biệt.

### 17.4. Khi CLI fail nhưng IDE run pass

IDE có thể chạy compiled classes bằng build system riêng, hoặc đang dùng cached build outputs. Đừng coi việc nút Run hoạt động là bằng chứng `./gradlew clean check` phải pass. Với CI, Wrapper build mới là chuẩn được xác nhận.

## 18. CI: ghi log đủ để tái hiện nhưng không làm lộ secret

Một báo lỗi CI có ích cần ghi:

- Gradle command chính xác, task targets và flags.
- Commit SHA và branch/ref (không chỉ “latest”).
- Gradle Wrapper version, Gradle runtime JVM, Java toolchain.
- OS/runner image và architecture.
- Output của `What went wrong`, `Where` và stacktrace đã redact.
- Test report link/attachment được phân quyền phù hợp.
- Dependency/plugin ID/version liên quan nếu đang là nguyên nhân.
- Task outcomes và việc cache được bật/tắt.
- Bước tái hiện tối thiểu và trạng thái sau sửa.

### 18.1. Mẫu lệnh chẩn đoán CI

Trên runner đáng tin và log storage phù hợp:

```bash
./gradlew --version
./gradlew check --stacktrace --info --console=plain
```

Với GitHub Actions/GitLab/Jenkins, hệ thống CI sẽ capture exit status và logs. Bảo đảm pipeline fail khi Gradle trả nonzero; không thêm `|| true` vô điều kiện để cho job xanh.

### 18.2. Không in credentials/URL có token

**Anti-pattern:**

```kotlin
println(System.getenv("INTERNAL_MAVEN_TOKEN"))
```

Không làm như vậy. Khi cần điều tra auth, chỉ kiểm tra identity/role, endpoint không chứa secret và error status, không in token thật vào issue hoặc Build Scan.

### 18.3. Log chưa được redact không nên gửi lên public tracker

- Loại bỏ password, bearer token, client secret, private endpoint không được chia sẻ.
- Giữ phần error type/task/path, nhưng thay nhãn bảo mật bằng placeholder trong **bug report**, không thay raw logs trong production environment.
- Nếu cần stacktrace đầy đủ, gửi qua kênh nội bộ được bảo vệ.
- Đọc Điều khoản/chính sách Build Scan trước khi tạo `--scan`.
- Đừng đính kèm toàn bộ Gradle User Home/cache directory; có thể chứa credentials hoặc artifact nội bộ.

## 19. Groovy DSL tương đương cho lab task

Nếu dự án dùng `build.gradle` Groovy, dưới đây là **phương án thay thế** cho Kotlin DSL `validatePort`. Java source và JUnit tests ở mục 6 không đổi.

**File `build.gradle`:**

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

application {
    mainClass = 'demo.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

abstract class ValidatePort extends DefaultTask {
    @Input
    abstract Property<String> getPortText()

    @TaskAction
    void validate() {
        String raw = portText.get()
        int port

        try {
            port = Integer.parseInt(raw)
        } catch (NumberFormatException cause) {
            throw new GradleException(
                    'demoPort must be an integer: ' + raw,
                    cause
            )
        }

        if (port < 1 || port > 65535) {
            throw new GradleException(
                    'demoPort must be between 1 and 65535: ' + port
            )
        }

        logger.lifecycle('validated demoPort=' + port)
    }
}

tasks.register('validatePort', ValidatePort) {
    portText.set(
            providers.gradleProperty('demoPort')
                    .orElse('not-a-number')
    )
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'gradle-root-cause-lab'
```

Chọn **một DSL** cho project tương ứng; không đặt cả `build.gradle` và `build.gradle.kts` đồng thời rồi kỳ vọng Gradle gộp hai scripts.

### 19.1. Vẫn giữ được nested exception

Java `Integer.parseInt` ném `NumberFormatException`, Groovy task catch và bọc bằng `GradleException`. Vì vậy thao tác:

```bash
./gradlew validatePort -PdemoPort=abc --stacktrace
```

vẫn có lớp nguyên nhân tương tự Kotlin DSL. Các dòng source/line/stack frames có thể khác vì DSL khác.

## 20. Những thói quen chẩn đoán sai nên tránh

**Sai lầm 1 — Chỉ đọc dòng cuối `BUILD FAILED`.** Kết luận thiếu căn cứ vì chưa biết task/exception nào.

**Sai lầm 2 — Chỉ xem `Execution failed for task`.** Đó là lớp wrapper; phải xem cause, compiler/test/subprocess diagnostics.

**Sai lầm 3 — Luôn sửa exception sâu nhất mà không xem context.** `UnknownHostException` có thể do URL cấu hình sai; `NumberFormatException` có thể do property được cấp sai ở CI.

**Sai lầm 4 — Cho rằng mọi `org.gradle.internal` frame là bug Gradle.** Thường Gradle chỉ điều phối và bọc lỗi từ custom plugin/application.

**Sai lầm 5 — Bật `--debug` vô điều kiện và đưa log lên public issue.** Có thể lộ secrets/metadata nội bộ.

**Sai lầm 6 — Tắt tests vì `:test` fail.** Là che lỗi, không phải fix.

**Sai lầm 7 — Xóa toàn bộ Gradle caches trước khi đọc lỗi.** Che đi evidence và tốn thời gian nếu lỗi là API/config sai.

**Sai lầm 8 — Nhầm child JVM stderr với Gradle exception chain.** Với `JavaExec`, lỗi app có thể nằm ngoài `Exception is`.

**Sai lầm 9 — Sửa dependency runtime của app khi lỗi ở plugin classpath.** Phải chọn đúng project/configuration.

**Sai lầm 10 — Đổi Gradle, JDK, plugin versions cùng một lần.** Không biết thay đổi nào thực sự sửa lỗi.

**Sai lầm 11 — Dùng `--continue` như giải pháp.** Nó có thể thu thêm failures, nhưng không loại bỏ root cause.

**Sai lầm 12 — Dùng `ignoreFailures=true` hoặc `-x test` để build xanh.** Không còn cùng quality gate.

**Sai lầm 13 — Cho rằng `--full-stacktrace` càng dài càng tốt.** Nhiều frames nội bộ làm khó nhìn frame quan trọng.

**Sai lầm 14 — Đọc Gradle IDE banner mà bỏ Build/Sync output.** UI rút gọn có thể ẩn chỗ có nguyên nhân thực.

**Sai lầm 15 — Thấy daemon biến mất là “lỗi Java code trong app”.** Có thể là OOM, JVM crash hoặc CI runner terminated.

**Sai lầm 16 — Khi Configuration Cache lỗi, tắt feature mãi mãi mà không kiểm code.** Cần đọc problems report và sửa plugin/task state.

## 21. Bảng chẩn đoán theo thông điệp thường gặp

| Thông điệp chính | Không kết luận vội | Nơi tìm root cause |
| --- | --- | --- |
| `BUILD FAILED` | Không biết lỗi gì | `What went wrong`/`Exception is` |
| `Execution failed for task ':x'` | Không đồng nghĩa Gradle core bug | Task action/tool diagnostics |
| `Process ... non-zero exit value 1` | Không đồng nghĩa JVM config sai | Child process stderr và exit reason |
| `Compilation failed` | Không nhất thiết dependency thiếu | `javac`/Kotlin compiler diagnostic đầu tiên |
| `There were failing tests` | Không nhất thiết test task implementation lỗi | JUnit HTML/XML/test method |
| `Plugin not found` | Không sửa bằng app `implementation` | Settings pluginManagement/marker/versions |
| `Could not resolve ...` | Không tự giả định artifact không có | Repository/auth/metadata/SSL/offline |
| `Could not compile build file` | Không sửa Java `src/main` | DSL script line và compile errors |
| `Unknown property/method` | Không chỉnh Gradle internals | Build script/extension/task API |
| `NoClassDefFoundError` | Không mặc định JVM quá cũ | Runtime classpath/class initialization |
| `NoSuchMethodError` | Không mặc định source compile lỗi | Plugin/library binary compatibility |
| `UnsupportedClassVersionError` | Không sửa bằng cache wipe | JVM loading class vs compiled bytecode |
| `SSLHandshakeException` | Không tắt TLS verification | Certificate/truststore/proxy |
| `Connection refused` | Không mặc định Gradle bug | Host/port/server/network |
| `Gradle daemon disappeared` | Không thể đòi Java stacktrace trong mọi trường hợp | Daemon/OS/CI crash logs |
| `Configuration cache problems` | Không chỉ dùng `problems=warn` | Cache problems report và plugin state |
| `NO-SOURCE` ở test | Không mặc định tests pass | Source sets/test discovery |
| `UP-TO-DATE` dù đã thay input | Không mặc định mọi việc đều đúng | Task declared inputs/outputs |
| `FROM-CACHE` nhưng output sai | Không mặc định compiler bug | Cache key/input tracking/trust |

## 22. Viết một bug report có thể tái hiện

Một báo lỗi chất lượng không chỉ đính kèm “Build failed”. Mẫu:

```text
Title:
  validatePort fails when demoPort contains non-numeric text

Environment:
  Gradle Wrapper: [actual version from ./gradlew --version]
  Gradle JVM: [actual JDK vendor/version]
  OS: [actual OS]
  Source commit: [actual commit SHA]

Exact command:
  ./gradlew validatePort -PdemoPort=abc --stacktrace --console=plain

Observed:
  Execution failed for task ':validatePort'.
  demoPort must be an integer: abc
  Caused by: NumberFormatException from string parsing

Expected:
  Task should accept only integer demoPort values
  or report an actionable validation error

Suspected root cause:
  Invalid Gradle project property demoPort supplied by invoker

Evidence:
  Redacted What went wrong + relevant Exception is frames
  Build script/task line
  Exit code and relevant logs
  No credentials or private paths in public report

Fix and verification:
  Supply -PdemoPort=8080 or fix environment property source
  Re-run same task; then ./gradlew clean check
```

Dấu ngoặc mô tả các thông tin phải điền bằng **dữ liệu môi trường thật**, không giả định version/commit của người học. Với lỗi phức tạp, thêm minimal reproducer repo hoặc log đã được redact để người khác có thể xác minh.

### 22.1. Nhận diện correlation với thay đổi gần nhất

Nếu lỗi xuất hiện sau nâng plugin/Gradle/JDK, so:

- Last known-good commit/version.
- First failing commit/version.
- Có dependency lock/verification metadata thay đổi không?
- Có source file/generated task input mới không?
- IDE Gradle JVM và CI JDK còn như trước không?
- Có remote repository/cache outage vào thời điểm lỗi không?

Bisect hữu ích nhưng phải kiểm test có tính lặp lại. Nếu lỗi intermittent, có thể cần nhiều lượt chạy và environmental diagnostics để tránh kết luận sai.

### 22.2. Khi nên báo lỗi Gradle hay third-party plugin

Chỉ nghi ngờ bug Gradle core khi có minimal reproduction, plugin/application code đã được loại trừ hợp lý, và version compatibility được xác nhận. Nếu stacktrace chủ yếu nằm ở third-party plugin, hãy kiểm plugin documentation/issues và compatibility matrix trước. Báo với Gradle khi có bằng chứng bug ở Gradle public behavior; kèm version, reproducer và sanitized stacktrace.

## 23. Bài tập thực hành

**Bài tập A — nhận diện wrapper.** Một log có `Execution failed for task ':validatePort'` và `NumberFormatException`. Hãy viết ba câu: task nào fail, context lỗi là gì và input nào sai.

**Bài tập B — dựng lab.** Tạo `gradle-root-cause-lab` theo mục 6, chạy `clean test classes`, `validatePort -PdemoPort=8080` và `run --quiet`. Xác nhận stdout `ready on port 8080`.

**Bài tập C — nested cause.** Chạy `validatePort -PdemoPort=abc --stacktrace`. Tìm `GradleException` và `NumberFormatException` trong output, ghi lại frame đầu tiên thuộc custom task.

**Bài tập D — direct validation.** Chạy `validatePort -PdemoPort=70000 --stacktrace`. Vì sao lỗi range không có nested `NumberFormatException`?

**Bài tập E — child JVM.** Chạy `run --args=abc --stacktrace`. Phân biệt stderr của `demo.Main` với Gradle `JavaExec` exit-code wrapper.

**Bài tập F — Java độc lập.** Biên dịch `PortParser` và `Main` bằng `javac`, chạy `java ... demo.Main abc` và `java ... demo.Main 8080`. Vì sao command thứ nhất không chứa Gradle task wrapper?

**Bài tập G — JUnit.** Thêm method `intentionallyFailsForDiagnosisOnly` ở bản sao, chạy test filter, xem `build/test-results/test` và xác định expected/actual.

**Bài tập H — Kotlin DSL compilation.** Thử sai identifier `unknownMethodName` trên bản sao build script. Tìm file/line `Unresolved reference`. Vì sao stacktrace dài không giúp bằng compiler diagnostic?

**Bài tập I — missing plugin.** Dùng một plugin ID không tồn tại trên bản sao, so `pluginManagement.repositories` với project `repositories`. Cách khắc phục đúng nằm ở đâu?

**Bài tập J — dependency failure.** Giả lập một library không tồn tại bằng coordinates thử nghiệm, tìm `Could not find ...` trong failure report. Tại sao xóa cache không tạo artifact được?

**Bài tập K — 401/403/SSL.** Với một repository private trong môi trường thử nghiệm có quyền, phân loại lỗi authentication, authorization, certificate trust và network; không in credentials.

**Bài tập L — JDK compatibility.** So `./gradlew --version`, `java -version`, `javaToolchains`. Nêu trường hợp plugin Java 21 chạy trên daemon Java 17 sẽ fail ở đâu.

**Bài tập M — IDE vs CLI.** Khi IDE sync fail nhưng Wrapper help pass, ghi lại task, Gradle JVM và settings khác nhau. Chỉ ra đâu là chứng cứ gợi ý bug IDE integration.

**Bài tập N — daemon crash.** Tìm daemon log khi daemon disappeared; kể ba nguyên nhân mà Java stacktrace không nhất thiết xuất hiện trong console.

**Bài tập O — Configuration Cache.** Viết một custom task cố đọc `project.name` ở execution phase trên bản sao, bật Configuration Cache, đọc problems report và đề xuất typed task input.

**Bài tập P — full stacktrace.** So output của `--stacktrace` và `--full-stacktrace` trên cùng lỗi. Vì sao không nên coi frame `org.gradle.internal` đầu tiên là root cause?

**Bài tập Q — failures độc lập.** Dùng `--continue` trên project có hai tasks độc lập cố ý fail. Phân tích mỗi failure block và không gộp nguyên nhân.

**Bài tập R — bảo mật log.** Tạo bug report từ CI logs có URL private và token giả lập. Redact thông tin nhạy cảm nhưng giữ exception class/task/file:line hữu ích.

**Bài tập S — không che lỗi.** Một người sửa `:test` failure bằng `ignoreFailures=true`. Giải thích vì sao fix không hợp lệ, rồi khôi phục test gate.

**Bài tập T — regression test.** Sau sửa property `demoPort`, chạy task đơn và `clean check`. Khi nào còn cần integration test cho configuration từ CI?

### Câu hỏi tự kiểm tra

1. Vì sao `BUILD FAILED` không phải root cause?
2. `Where` và `What went wrong` trả lời những câu hỏi nào?
3. `Exception is` xuất hiện khi nào?
4. `--stacktrace` khác `--full-stacktrace` ở đâu?
5. `--info` giúp gì bên cạnh `--stacktrace`?
6. Tại sao `--debug` có thể nguy hiểm trong CI?
7. `Caused by` mô tả điều gì trong Java Throwable?
8. `Suppressed` khác `Caused by` thế nào?
9. `... N more` có phải N exception mới không?
10. Vì sao không luôn sửa deepest cause mà bỏ context?
11. Task path `:compileJava` gợi ý đọc thông tin ở đâu?
12. Lỗi Kotlin DSL unresolved reference là configuration hay task execution?
13. Vì sao plugin not found phải xem `pluginManagement`?
14. Lỗi `JavaExec` có thể cần đọc stderr ở đâu?
15. Process exit code 1 có chứng minh Gradle bug không?
16. Khi `:test` fail, test HTML/XML giúp gì?
17. `--tests` giúp khoanh vùng như thế nào?
18. Vì sao `NO-SOURCE` không chứng minh tests pass?
19. `UnsupportedClassVersionError` liên quan hai JVM/bytecode contexts nào?
20. `NoSuchMethodError` có thể xuất hiện do điều gì?
21. Vì sao lỗi dependency SSL không được chữa bằng tắt TLS?
22. `--refresh-dependencies` có tạo module chưa publish không?
23. Khi daemon biến mất, cần đọc những logs ngoài console nào?
24. Configuration Cache problems report gợi ý root cause ở đâu?
25. Vì sao xóa cache ngay có thể làm mất dấu vết chẩn đoán?
26. `--continue` có sửa lỗi đang xảy ra không?
27. Khi IDE khác CLI, nên đối chiếu các biến môi trường nào?
28. Vì sao bug report cần exact Gradle command/commit/JDK?
29. Khi nào cần rerun task thay vì tin UP-TO-DATE?
30. Thế nào là dấu hiệu fix đúng: task pass riêng nhưng release gates còn fail?
31. Vì sao không nên đăng đầy đủ Build Scan nội bộ lên public tracker?
32. Khi nào nên nghi bug Gradle core thay vì plugin/build logic?

## 24. Tài liệu chính thức

- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Gradle Command-Line Interface](https://docs.gradle.org/current/userguide/gradle_command_line.html)
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle — Build Scans](https://docs.gradle.org/current/userguide/inspect.html)
- [Oracle Java — Throwable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)

**Ghi nhớ:** Gradle failure report có thể bọc nhiều tầng lỗi. Dùng `Where`/`What went wrong` để định vị phase và task, `--stacktrace` để lần theo exception/cause, `--info` để xem bối cảnh trước lỗi, và compiler/test/subprocess reports để tìm **nguyên nhân ở đúng công cụ thực thi**. `Caused by` và frame thuộc mã của bạn thường hữu ích hơn generic `BUILD FAILED`, nhưng không bỏ qua contextual wrapper. Sửa một nguyên nhân có bằng chứng, tái hiện và chạy lại quality gate; đừng che lỗi bằng skip tasks, xóa cache hoặc tăng verbosity vô hạn.