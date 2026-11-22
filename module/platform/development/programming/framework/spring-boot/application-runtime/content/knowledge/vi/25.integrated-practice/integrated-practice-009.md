# Tạo ứng dụng dòng lệnh có mã thoát và kiểm thử bằng tiến trình con

## Mục tiêu học tập

Một ứng dụng Spring Boot dạng dòng lệnh (*command-line application*, CLI), batch job hoặc worker chạy một lần thường cần thông báo **kết quả cho hệ điều hành**: hoàn tất thành công, hoàn tất một phần, dữ liệu đầu vào không hợp lệ, cần thử lại hoặc khởi động thất bại. In một dòng `"FAILED"` ra console không đủ, vì shell, CI/CD, scheduler và container thường quyết định dựa trên **mã thoát của tiến trình** (*process exit code*).

Spring Boot cung cấp `ExitCodeGenerator` và `SpringApplication.exit(...)`; Java cung cấp `System.exit(int)`. Để kiểm tra hợp đồng này, test không thể chỉ gọi method `main` trong JVM JUnit: `System.exit` có thể kết thúc luôn test runner. Một bộ **integration tests dùng `ProcessBuilder` khởi tạo một JVM con**, chạy executable JAR thật, chờ bằng deadline, đọc output và đối chiếu `Process.exitValue()` sẽ phù hợp hơn.

Bài học thuộc **Spring Boot Application Runtime → Thực hành tổng hợp**. Ví dụ hướng đến **Java 17+**, **Spring Boot 3.3.13**, **Gradle**, **JUnit 5** và hoạt động trên Windows/Linux/macOS với đường dẫn Java/JAR được truyền dưới dạng argument riêng biệt.

Sau bài học, bạn có thể:

1. Phân biệt `return` khỏi `main`, `SpringApplication.exit(context)` và `System.exit(code)`.
2. Tạo Spring Boot CLI với `WebApplicationType.NONE`, có `ApplicationRunner` thực thi nghiệp vụ đúng một lần.
3. Lưu trạng thái nghiệp vụ trong một bean và cung cấp mã qua `@Bean ExitCodeGenerator`.
4. Tạo exception startup implements `ExitCodeGenerator`, nhận diện cause chain và truyền exit status có chủ đích.
5. Phân biệt lỗi **khởi tạo context/runner** với nghiệp vụ đã chạy nhưng trả kết quả **non-zero**.
6. Dùng `ProcessBuilder` chạy đúng Java executable và `bootJar` đã build, không phụ thuộc vào shell quoting.
7. Gom stdout/stderr về file tạm để tránh deadlock do pipe buffer; xử lý timeout và hủy tiến trình con.
8. Viết các test assert **mã 0, 12, 21, 30, 43, 64**, log có marker, thứ tự ready/close và các trường hợp lỗi.
9. Tổ chức Gradle `test dependsOn bootJar` để test luôn có artifact mới.
10. Hiểu khác biệt giữa mã của **ứng dụng Java**, mã của **Gradle**, mã của **shell pipeline** và trạng thái container.
11. Thiết kế cách tích hợp CLI vào CI/CD, Kubernetes Job hoặc scheduler, kèm retry/idempotency/observability đúng mức.
12. Mở rộng test để kiểm tra tham số thiếu, chạy lâu, stderr lớn, biến môi trường và resource cleanup.

**Giới hạn cố ý của ví dụ:** Demo không dùng HTTP server, database, Kafka hay mạng thật. Điều này giữ kết quả deterministic và tập trung vào **mã thoát và kiểm thử tiến trình con**. Những thao tác I/O thật cần bổ sung timeout, transaction/idempotency, cleanup và resource management theo đúng SDK.

## 1. Mã thoát là một phần của hợp đồng CLI

Một JVM kết thúc bằng một số nguyên cho process owner. Theo quy ước phổ biến:

- **0:** chương trình hoàn thành thành công.
- **Khác 0:** thất bại hoặc trạng thái khác cần bên điều phối xử lý.
- **Ý nghĩa cụ thể của non-zero:** do **ứng dụng và đội vận hành** định nghĩa, không phải Spring Boot gán sẵn một bảng mã chung.

Ví dụ một job nhập dữ liệu:

| Mã | Tên trạng thái của demo | Ý nghĩa | Gợi ý xử lý |
| ---: | --- | --- | --- |
| `0` | `SUCCESS` | Toàn bộ dữ liệu hợp lệ và job hoàn tất | Không retry |
| `12` | `PARTIAL_RESULT` | Đã xử lý một phần, còn record bị từ chối theo chính sách | Đọc báo cáo và quyết định lại |
| `21` | `INVALID_INPUT` | Dữ liệu nghiệp vụ không hợp lệ | Sửa dữ liệu trước khi chạy lại |
| `30` | `TEMPORARY_UNAVAILABLE` | Hạ tầng tạm chưa sẵn sàng theo chính sách nghiệp vụ | Retry có giới hạn/backoff |
| `43` | `FATAL_STARTUP` | Runner ném một lỗi khởi động đã phân loại | Dừng và kiểm tra nguyên nhân |
| `64` | `USAGE_ERROR` | Tham số CLI không được hỗ trợ | Sửa cách gọi chương trình |
| `1` | `UNCLASSIFIED_FAILURE` | Lỗi khác không có mã chuyên biệt | Điều tra trước khi retry |

**Quan trọng:** Các con số trên là **quy ước riêng của project học tập**, không phải một chuẩn được Spring Boot bảo đảm. Trong production, dùng mã ngắn gọn, document ý nghĩa và thống nhất với batch scheduler.

### Không nhầm 0 và “không có exception”

Một runner có thể hoàn tất việc **thực thi** mà kết quả nghiệp vụ không hoàn toàn đạt yêu cầu. Ví dụ job đọc xong toàn bộ file và thống kê 5 bản ghi không hợp lệ. Việc runner **return bình thường** có thể là đúng về mặt vòng đời Spring Boot, nhưng CLI vẫn cần mã `12` cho bên gọi.

Ngược lại, khi runner ném exception, `SpringApplication.run(...)` không hoàn tất theo đường thành công. Cơ chế xử lý **lỗi startup** có thể cung cấp mã thông qua một exception triển khai `ExitCodeGenerator`.

Hai đường này khác nhau và sẽ được thể hiện riêng trong project:

~~~text
                    SpringApplication.run(args)
                               |
                      ApplicationRunner
                       /             \
          runner return               runner throw
               |                            |
       ApplicationReadyEvent         startup failure path
               |                            |
         context returned            context không trả về
               |                            |
       SpringApplication.exit        lỗi/cause được phân loại
               |                            |
       ExitCodeGenerator bean        mã từ exception hoặc policy
               |                            |
               +------------+---------------+
                            |
                   System.exit(code)
                            |
                   OS/shell nhận exit status
~~~

## 2. Ba API không thể thay thế nhau

### SpringApplication.run(...)

~~~java
ConfigurableApplicationContext context =
        new SpringApplication(CliApplication.class).run(args);
~~~

Đây là **snippet minh họa**, cần class `CliApplication` và imports thích hợp. `run(...)` dựng context và chạy runners. Nếu startup fail, phương thức có thể ném exception trước khi trả về `context`.

### SpringApplication.exit(context)

~~~java
int code = SpringApplication.exit(context);
~~~

Nó tính exit code dựa trên các `ExitCodeGenerator` bean/arguments, phát `ExitCodeEvent` phù hợp và **đóng context** nếu có thể. Theo Javadoc Spring Boot 3.3.13, khi có nhiều generators, mã **khác 0 đầu tiên** sau ordering được sử dụng.

**Phương thức này trả về một `int`. Nó không tự gọi `System.exit` để kết thúc JVM và truyền status cho OS.**

### System.exit(code)

~~~java
System.exit(code);
~~~

Đây là lệnh JVM yêu cầu kết thúc tiến trình với exit status mong muốn. Nó tác động **toàn bộ JVM**, nên chỉ dùng ở **điểm ra ngoài cùng** của ứng dụng CLI khi nghiệp vụ và cleanup đã được xử lý.

Không được gọi `System.exit(...)` trong JUnit test JVM đang chạy, trong bean constructor, trong `@PostConstruct` hoặc trong một mapper theo thói quen. Nếu chương trình chứa non-daemon background threads, `System.exit` có thể cắt ngắn công việc chưa hoàn tất; cần thiết kế drain/cleanup trước.

### Bảng đối chiếu

| Cơ chế | Thực thi startup? | Đóng context? | Trả mã cho OS? |
| --- | --- | --- | --- |
| `SpringApplication.run` | Có | Không trên đường thành công; lỗi có failure cleanup | Không trực tiếp |
| `ApplicationRunner.run` | Bước nghiệp vụ trước Ready | Không mặc định | Không |
| `ExitCodeGenerator.getExitCode` | Không; chỉ cung cấp số | Không | Không |
| `SpringApplication.exit(context)` | Không chạy startup lại | Có | Chỉ trả số cho caller |
| `System.exit(code)` | Không | Gây JVM shutdown; hooks có thể chạy | Có |
| `return` khỏi `main` | Không gọi thêm cơ chế Boot | Không tự đóng bean context chủ động | JVM thường trả 0 nếu kết thúc bình thường |

**Bẫy phổ biến:** In `"EXIT=30"` không làm process exit với mã 30. Chỉ có mã thoát thực `Process.exitValue()`, `$?` hoặc `$LASTEXITCODE` mới chứng minh điều phối nhận đúng trạng thái.

## 3. Vì sao chọn WebApplicationType.NONE?

Ứng dụng dạng job chạy một lần không cần Tomcat hoặc HTTP endpoint. Cấu hình:

~~~java
SpringApplication app = new SpringApplication(CliExitApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
~~~

giúp Spring Boot dùng non-web application context. Nhưng **nó vẫn chạy Spring lifecycle thực**:

- Environment và property sources.
- Bean creation, dependency injection.
- `@PostConstruct` và bean destroy callbacks.
- `ApplicationRunner` hoặc `CommandLineRunner`.
- `ApplicationStartedEvent`, `ApplicationReadyEvent` hoặc `ApplicationFailedEvent` tùy đường.
- `SpringApplication.exit(context)` và close context.

`NONE` **không** tự tắt mọi scheduler, thread pool, database client hoặc message listener được ứng dụng tự khai báo. Một CLI có thể không thoát nếu còn non-daemon threads. Project này không tạo các tài nguyên đó để test không bị treo ngoài ý muốn.

### Khi nào cần WebApplicationType.SERVLET?

Nếu job còn phải lắng nghe HTTP, expose actuator hoặc serve requests, `NONE` sẽ không phù hợp. Nhưng đề bài này là **thực hành CLI với process exit status**; non-web giúp mục tiêu test tập trung và tránh xung đột port.

**Không nhầm `server.port=0` với `NONE`:** Port 0 vẫn tạo web server ở cổng ngẫu nhiên khi app là servlet/reactive web. `NONE` không khởi động embedded HTTP server.

## 4. Hợp đồng và kịch bản của project

Ứng dụng nhận một option:

~~~text
--demo.mode=<mode>
~~~

Các mode hợp lệ:

| Mode | Runner làm gì? | Có Ready? | Đường lấy mã | Exit code |
| --- | --- | --- | --- | ---: |
| `success` | Ghi kết quả SUCCESS, return | Có | Bean `ExitCodeGenerator` | 0 |
| `partial` | Ghi PARTIAL_RESULT, return | Có | Bean `ExitCodeGenerator` | 12 |
| `invalid` | Ghi INVALID_INPUT, return | Có | Bean `ExitCodeGenerator` | 21 |
| `retry` | Ghi TEMPORARY_UNAVAILABLE, return | Có | Bean `ExitCodeGenerator` | 30 |
| `fatal` | Ném `FatalJobException` trong runner | Không | Phân loại cause chứa `ExitCodeGenerator` exception | 43 |
| Mode khác | Ném `CliUsageException` | Không | Phân loại cause chứa `ExitCodeGenerator` exception | 64 |

Nếu không truyền `--demo.mode`, dùng mode `success`. Nếu truyền trùng option hoặc không có giá trị, coi là usage error; không chọn ngẫu nhiên một trong các giá trị.

### Chú ý: Ready không có nghĩa job đã thành công

Với `partial`, `invalid` và `retry`, runner **return bình thường** vì nó đã thực hiện và phân loại nghiệp vụ; Boot có thể phát `ApplicationReadyEvent` trước khi trả context. Tuy nhiên, bean exit-code generator vẫn trả **12, 21 hoặc 30**. Đây không phải mâu thuẫn:

- **Ready:** mốc Boot startup hoàn tất theo đường bình thường.
- **Process status:** kết quả của job theo hợp đồng CLI.

Nếu một điều kiện là **thất bại của chính startup**, như mode `fatal`, runner ném exception và đường Ready không xảy ra.

### Vì sao có một nhánh exception riêng?

Để thực hành hai nguồn mã thoát:

1. **Bean generator:** đã có `ApplicationContext` và kết quả job được ghi vào một bean. `SpringApplication.exit(context)` đọc bean và đóng context.
2. **Exception generator:** `SpringApplication.run(...)` throw trước khi có một context thành công để caller truyền vào `exit`. Handler của main duyệt cause chain và truyền mã lỗi đã phân loại cho `System.exit`.

Spring Boot cũng tự có cơ chế xử lý exception implements `ExitCodeGenerator` trong startup failure path. Demo dùng **phân loại tường minh ở main** để test process status độc lập với khác biệt của launcher/uncaught-exception handler; vì không tạo `ExitCodeExceptionMapper` bean, logic này phù hợp đúng hợp đồng hai exception trong demo.

## 5. Thiết kế architecture

~~~text
+----------------------------------------+
| CLI parent (shell / JUnit / scheduler)  |
|                                        |
|  java -jar app.jar --demo.mode=partial |
|                 |                      |
|                 v                      |
|          child Java process            |
|                 |                      |
|      SpringApplication.run             |
|                 |                      |
|          ApplicationRunner             |
|                 |                      |
|         JobOutcome bean (12)           |
|                 |                      |
|      SpringApplication.exit            |
|                 |                      |
|       Context.close + @PreDestroy      |
|                 |                      |
|           System.exit(12)              |
|                 |                      |
+-----------------+----------------------+
                  |
                  v
     parent Process.waitFor(timeout)
                  |
        +---------+----------+
        |                    |
       DONE                 TIMEOUT
        |                    |
 Process.exitValue()    destroy / destroyForcibly
        |                    |
 Compare 12 + log      fail test with diagnostics
~~~

**Ưu điểm của tiến trình con:** `System.exit` chỉ kết thúc JVM con. JVM của JUnit/Gradle còn sống để assert, ghi báo cáo, thực hiện các testcase khác và cleanup.

## 6. Cấu trúc project hoàn chỉnh

~~~text
cli-process-exit-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/cli/
    │       └── CliExitApplication.java
    └── test/
        └── java/com/example/cli/
            └── CliExitProcessTests.java
~~~

Project cần **JDK 17+** và Gradle tương thích Spring Boot 3.3. Nếu máy chưa có Gradle, tạo Gradle Wrapper tương thích hoặc dùng bản Gradle đã cài. Ví dụ này **không** tạo sẵn các tệp wrapper.

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'cli-process-exit-demo'
~~~

### 6.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

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
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.cli.CliExitApplication'
}

def executableJar = tasks.named('bootJar')

tasks.named('test', Test) {
    useJUnitPlatform()

    // Không chạy test với JAR cũ/chưa build.
    dependsOn executableJar

    // Lấy đúng archiveFile của bootJar, không hardcode filename.
    doFirst {
        systemProperty(
            'demo.jar.path',
            executableJar.get().archiveFile.get().asFile.absolutePath
        )
    }
}
~~~

**Vì sao build.gradle này phù hợp?**

- Plugin `org.springframework.boot` tạo task `bootJar` sản xuất executable JAR có Boot launcher.
- `java` toolchain yêu cầu Java 17, phù hợp Spring Boot 3.3.
- Dependency BOM cho phép không phải gắn version riêng trên các starters.
- `spring-boot-starter` cung cấp core Boot mà không mở web server.
- `spring-boot-starter-test` cung cấp JUnit Jupiter và các công cụ kiểm thử.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` giúp Gradle test runtime có launcher tường minh.
- `tasks.named('test', Test)` bật JUnit Platform.
- `dependsOn executableJar` bảo đảm `bootJar` được build **trước test**.
- `doFirst` chỉ lấy path JAR sau khi task tương ứng đã được cấu hình/thực thi, rồi truyền sang test JVM bằng property `demo.jar.path`.
- Test không phải đoán tên `build/libs/...jar`; nếu version đổi, property vẫn tham chiếu đúng output của `bootJar`.

**Lưu ý:** `dependsOn` không làm test chạy ở trong JAR. Test vẫn chạy trong Gradle test JVM; bên trong test, `ProcessBuilder` tạo **một JVM Java khác** rồi thực thi chính JAR từ `bootJar`.

## 7. Application: kết quả nghiệp vụ và mã thoát

**Tệp đầy đủ `src/main/java/com/example/cli/CliExitApplication.java`:**

~~~java
package com.example.cli;

import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class CliExitApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(CliExitApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        int code;

        try {
            ConfigurableApplicationContext context = app.run(args);

            // Đọc các bean ExitCodeGenerator, rồi đóng context.
            code = SpringApplication.exit(context);
        }
        catch (RuntimeException startupFailure) {
            // run() chưa trả context thành công cho main.
            // Duyệt cause chain để thấy exception bên trong runner.
            code = codeFromFailure(startupFailure);

            System.err.println(
                    "MAIN: startup failure code=" + code);
        }

        System.out.println("MAIN: exitCode=" + code);

        // Truyền mã ra OS. Chỉ gọi ở entrypoint CLI.
        System.exit(code);
    }

    private static int codeFromFailure(Throwable failure) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof ExitCodeGenerator generator) {
                int code = generator.getExitCode();

                if (code != 0) {
                    return code;
                }
            }
        }

        // Không có loại lỗi đã phân loại: báo lỗi chung.
        return 1;
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
        return outcome::getExitCode;
    }

    @Bean
    ApplicationRunner demoRunner(JobOutcome outcome) {
        return args -> {
            List<String> values =
                    args.getOptionValues("demo.mode");

            String mode;

            if (values == null) {
                mode = "success";
            }
            else if (values.size() == 1) {
                mode = values.get(0);
            }
            else {
                System.out.println("JOB: INVALID_ARGUMENT_COUNT");
                throw new CliUsageException(
                        "demo.mode requires exactly one value");
            }

            switch (mode) {
                case "success" -> {
                    outcome.setExitCode(0);
                    System.out.println("JOB: SUCCESS");
                }
                case "partial" -> {
                    outcome.setExitCode(12);
                    System.out.println("JOB: PARTIAL_RESULT");
                }
                case "invalid" -> {
                    outcome.setExitCode(21);
                    System.out.println("JOB: INVALID_INPUT");
                }
                case "retry" -> {
                    outcome.setExitCode(30);
                    System.out.println("JOB: TEMPORARY_UNAVAILABLE");
                }
                case "fatal" -> {
                    System.out.println("JOB: FATAL_STARTUP");
                    throw new FatalJobException(
                            "Mandatory startup step failed");
                }
                default -> {
                    System.out.println("JOB: UNKNOWN_MODE");
                    throw new CliUsageException(
                            "Unsupported demo.mode");
                }
            }
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: READY");
    }

    public static final class JobOutcome {

        // Nếu runner không hoàn tất mà code khác vẫn gọi exit,
        // default là lỗi chung, không ngụy báo thành công.
        private volatile int exitCode = 1;

        public void setExitCode(int exitCode) {
            this.exitCode = exitCode;
        }

        public int getExitCode() {
            return exitCode;
        }

        @PreDestroy
        public void onDestroy() {
            System.out.println("LIFECYCLE: closed");
        }
    }

    public static final class FatalJobException
            extends IllegalStateException implements ExitCodeGenerator {

        public FatalJobException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 43;
        }
    }

    public static final class CliUsageException
            extends IllegalArgumentException
            implements ExitCodeGenerator {

        public CliUsageException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 64;
        }
    }
}
~~~

### 7.1. Vì sao dùng bean JobOutcome?

`JobOutcome` là một bean **theo context**, không phải static field toàn JVM. Runner cập nhật `exitCode` dựa trên kết quả thực thi. Bean `ExitCodeGenerator` là một method reference:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
    return outcome::getExitCode;
}
~~~

SpringApplication.exit lấy mã khi context còn có thể truy vấn các beans rồi thực hiện close. Việc `JobOutcome` dùng `volatile int` là một lựa chọn an toàn cho quan sát giữa thread nếu mở rộng sau này; trong demo, runner và main khởi động tuần tự nên không cần một cơ chế concurrency phức tạp.

**Không viết `return () -> 0` cho mọi mode**: nó sẽ che kết quả nghiệp vụ và khiến shell luôn nghĩ job thành công.

### 7.2. Dùng ApplicationArguments thay vì tự parse String bằng split

`ApplicationRunner` nhận `ApplicationArguments`. `getOptionValues("demo.mode")`:

- Trả `null` khi option không có.
- Trả danh sách giá trị khi option có.
- Có thể trả danh sách rỗng cho `--demo.mode` không kèm giá trị.
- Có thể có nhiều phần tử khi option xuất hiện lặp.

Demo chỉ nhận đúng **một** giá trị nếu option được cung cấp; điều này khiến `--demo.mode=success --demo.mode=partial` không bị diễn giải tùy ý.

Nếu `--demo.mode` thiếu giá trị, code ném `CliUsageException`. Với mode không hỗ trợ, default branch cũng ném loại này.

**Đừng bỏ qua tham số thừa** nếu hợp đồng sản phẩm yêu cầu strict parsing; demo chỉ kiểm tra option `demo.mode`, các option khác có thể được Boot parser giữ mà không bị runner từ chối. Muốn strict CLI, bổ sung validator cho toàn bộ `getOptionNames()` theo chính sách riêng.

### 7.3. Tại sao SpringApplication.exit(context) đứng sau run?

Trên đường nghiệp vụ bình thường:

~~~text
runner sets JobOutcome.exitCode
   |
ApplicationReadyEvent
   |
SpringApplication.run trả context
   |
SpringApplication.exit(context)
   |
bean ExitCodeGenerator trả mã
   |
context.close() → @PreDestroy
   |
main in mã
   |
System.exit(code)
~~~

`@PreDestroy` ở `JobOutcome` in `LIFECYCLE: closed`. Nó chứng minh một managed bean nhận destroy callback khi context đóng. Với real database connection/file/executor, chỉ in log chưa đủ; cần xác minh resource đã release theo contract.

### 7.4. Vì sao main còn có catch RuntimeException?

Nếu runner ném `FatalJobException`, `SpringApplication.run(...)` thực hiện nhánh startup failure và ném exception ra ngoài trước khi trả context. Spring Boot thường bọc lỗi runner trong một `IllegalStateException` mang thông điệp “Failed to execute ApplicationRunner”, nên chỉ kiểm tra exception ngoài cùng bằng `instanceof FatalJobException` có thể bỏ sót.

`codeFromFailure(...)` duyệt `getCause()` cho tới khi gặp exception implements `ExitCodeGenerator`, rồi lấy mã của nó. Nếu không có mã phân loại, trả 1. Main sau đó gọi `System.exit(code)` để process status của demo **tường minh và kiểm thử được**, không phụ thuộc vào việc một exception không được catch có được launcher xử lý thành một mã cụ thể hay không.

**Giới hạn:** Đây là classifier hẹp cho project dạy học. Nếu ứng dụng có các `ExitCodeExceptionMapper` bean và muốn dùng chính sách mapping của Boot khi startup fail, đừng tự viết một classifier khác rồi vô tình override mapper. Boot có cơ chế xác định mã exception trong failure path của nó; với project production, chọn một đường phân loại nhất quán và test đúng phiên bản.

### 7.5. Tại sao không bắt Exception và luôn return 0?

Một anti-pattern:

~~~java
try {
    runJob();
}
catch (Exception error) {
    System.err.println(error);
}
System.exit(0);
~~~

Đây là **snippet sai**, không phải code bổ sung cho project. Nó báo thành công dù job không hoàn tất. Nếu catch để phân loại, phải trả mã khác 0 phù hợp, giữ cause/log và không nuốt lỗi hạ tầng quan trọng.

### 7.6. Tại sao không gọi System.exit ngay trong runner?

Nếu runner tự gọi `System.exit(43)` ngay lúc phát hiện lỗi, Spring có thể không đi qua error reporting/cleanup mà bạn kỳ vọng theo đường `SpringApplication.run`. Với job có resource đang mở hoặc transaction chưa hoàn tất, việc dừng ngay cũng có thể nguy hiểm.

Để runner **return kết quả nghiệp vụ** hoặc **ném domain exception**, rồi để entrypoint/lifecycle quản lý status và close. Không đặt logic process termination trong lớp nghiệp vụ.

## 8. Test ProcessBuilder: khởi động một JVM thật

Ta muốn JUnit kiểm tra:

1. Tạo **JVM con** bằng executable Java từ `java.home` của test runtime.
2. Chạy chính file JAR do `bootJar` build.
3. Truyền từng option dưới dạng **argument riêng**, không tự xây dựng command-line shell string.
4. Gộp stderr với stdout, ghi vào **file tạm**.
5. Chờ process kết thúc **tối đa 60 giây**.
6. Nếu quá hạn, gửi tín hiệu dừng; nếu chưa dừng thì force kill, rồi fail test.
7. Sau khi process kết thúc, đọc `exitValue()` và nội dung file log.
8. Xóa file tạm trong `finally`.
9. Không gọi `System.exit(...)` trong JVM của JUnit.

**Vì sao ghi file tạm thay vì đọc output sau waitFor?** Nếu child ghi quá nhiều vào stdout/stderr pipes, pipe buffer có thể đầy; child bị block chờ parent đọc, trong khi parent lại đang chờ child exit. Dùng `redirectOutput(file)` và `redirectErrorStream(true)` giúp OS ghi log vào file, giảm nguy cơ deadlock do pipe.

## 9. Toàn bộ mã JUnit 5 cho tiến trình con

**Tệp `src/test/java/com/example/cli/CliExitProcessTests.java`:**

~~~java
package com.example.cli;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class CliExitProcessTests {

    private record ChildResult(int code, String output) {
    }

    @Test
    void successReturnsZeroAndClosesContext() throws Exception {
        ChildResult child = runChild("success");

        assertEquals(0, child.code(), child.output());
        assertTrue(child.output().contains("JOB: SUCCESS"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("LIFECYCLE: closed"));
        assertTrue(child.output().contains("MAIN: exitCode=0"));

        // Các marker do chính code demo in, theo thứ tự Boot lifecycle.
        assertBefore(child.output(), "JOB: SUCCESS", "EVENT: READY");
        assertBefore(
                child.output(), "EVENT: READY", "LIFECYCLE: closed");
        assertBefore(
                child.output(), "LIFECYCLE: closed", "MAIN: exitCode=0");
    }

    @Test
    void partialResultReturnsTwelve() throws Exception {
        ChildResult child = runChild("partial");

        assertEquals(12, child.code(), child.output());
        assertTrue(child.output().contains("JOB: PARTIAL_RESULT"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=12"));
    }

    @Test
    void invalidInputReturnsTwentyOne() throws Exception {
        ChildResult child = runChild("invalid");

        assertEquals(21, child.code(), child.output());
        assertTrue(child.output().contains("JOB: INVALID_INPUT"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=21"));
    }

    @Test
    void retryableResultReturnsThirty() throws Exception {
        ChildResult child = runChild("retry");

        assertEquals(30, child.code(), child.output());
        assertTrue(child.output().contains(
                "JOB: TEMPORARY_UNAVAILABLE"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=30"));
    }

    @Test
    void fatalRunnerFailureReturnsFortyThree() throws Exception {
        ChildResult child = runChild("fatal");

        assertEquals(43, child.code(), child.output());
        assertTrue(child.output().contains("JOB: FATAL_STARTUP"));
        assertFalse(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("LIFECYCLE: closed"));
        assertTrue(child.output().contains(
                "MAIN: startup failure code=43"));
        assertTrue(child.output().contains("MAIN: exitCode=43"));
    }

    @Test
    void unsupportedModeReturnsUsageError() throws Exception {
        ChildResult child = runChild("unknown-value");

        assertEquals(64, child.code(), child.output());
        assertTrue(child.output().contains("JOB: UNKNOWN_MODE"));
        assertFalse(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=64"));
    }

    private static ChildResult runChild(String mode) throws Exception {
        String pathProperty = Objects.requireNonNull(
                System.getProperty("demo.jar.path"),
                "Missing demo.jar.path: run tests using Gradle test task");

        Path jar = Path.of(pathProperty).toAbsolutePath();
        assertTrue(Files.isRegularFile(jar), "Missing JAR: " + jar);

        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win") ? "java.exe" : "java";

        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                executable);

        assertTrue(
                Files.isRegularFile(java),
                "Missing Java executable: " + java);

        Path logFile = Files.createTempFile(
                "cli-process-test-", ".log");

        Process process = null;

        try {
            ProcessBuilder builder = new ProcessBuilder(
                    java.toString(),
                    "-Dfile.encoding=UTF-8",
                    "-jar",
                    jar.toString(),
                    "--demo.mode=" + mode);

            // Không để stdout/stderr pipes bị đầy vì parent chờ exit.
            builder.redirectErrorStream(true);
            builder.redirectOutput(logFile.toFile());

            process = builder.start();

            boolean finished =
                    process.waitFor(60, TimeUnit.SECONDS);

            if (!finished) {
                // Timeout phải làm test thất bại, không để CI treo.
                process.destroy();

                if (!process.waitFor(3, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }

                fail("Child JVM exceeded timeout. Output:\n"
                        + Files.readString(
                                logFile, StandardCharsets.UTF_8));
            }

            int code = process.exitValue();
            String output = Files.readString(
                    logFile, StandardCharsets.UTF_8);

            return new ChildResult(code, output);
        }
        finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }

            Files.deleteIfExists(logFile);
        }
    }

    private static void assertBefore(
            String output, String earlier, String later) {

        int first = output.indexOf(earlier);
        int second = output.indexOf(later);

        assertTrue(first >= 0, "Missing marker: " + earlier);
        assertTrue(second >= 0, "Missing marker: " + later);
        assertTrue(first < second, "Wrong order:\n" + output);
    }
}
~~~

### 9.1. Từng assertion chứng minh điều gì?

**`successReturnsZeroAndClosesContext`**

- Child JVM trả đúng 0.
- Runner đã thực thi nghiệp vụ thành công.
- `ApplicationReadyEvent` đã phát.
- Bean đã nhận `@PreDestroy` trong lúc `SpringApplication.exit(context)` đóng context.
- Main chỉ in exit code sau khi event đóng resource đã chạy.
- **Không** dùng code status in log để thay cho `Process.exitValue()`; test kiểm tra cả hai.

**`partialResultReturnsTwelve` và `invalidInputReturnsTwentyOne`**

- Runner **return bình thường**, Boot đạt ready theo lifecycle.
- Bean generator trả mã khác 0 dựa trên kết quả nghiệp vụ.
- Điều phối bên ngoài có thể phân biệt “đã chạy nhưng nghiệp vụ chưa đủ” với “process crash”.

**`retryableResultReturnsThirty`**

- Demo chỉ phân loại “temporary unavailable”; nó **không tự retry**. Test xác nhận scheduler có thể nhận mã 30 để quyết định retry có backoff.
- Không nên tự động lặp một job có side effects nếu không có idempotency/recovery policy.

**`fatalRunnerFailureReturnsFortyThree`**

- Runner ném exception chứa mã 43.
- Boot không phát ready trên đường thành công.
- Main bắt exception do `run` throw, duyệt cause chain để lấy 43.
- Child exit thực là 43, không chỉ một chuỗi trong log.
- Context đã được refresh trước runner; Spring Boot 3.3 xử lý failure bằng cách cố đóng context, nên `@PreDestroy` của bean hoàn chỉnh có thể chạy. Test này kiểm tra cụ thể tình huống runner fail **sau refresh**, không đại diện mọi lỗi cực sớm trong bootstrap.

**`unsupportedModeReturnsUsageError`**

- Mode lạ được phân loại rõ là `USAGE_ERROR` 64.
- Không âm thầm chạy `success` nếu input người dùng sai.

### 9.2. Tại sao dùng record ChildResult?

Java 17 hỗ trợ `record`:

~~~java
private record ChildResult(int code, String output) {
}
~~~

Nó nhóm một process exit code và output lại với nhau mà không cần class có constructor/getters thủ công. Test đọc `child.code()` và `child.output()`; cả hai thuộc **cùng lần chạy**, tránh vô tình lấy log của process A và exit code của process B.

### 9.3. Tại sao dùng java.home?

Đường dẫn Java trong test:

~~~java
Path java = Path.of(
        System.getProperty("java.home"),
        "bin",
        executable);
~~~

giúp gọi executable của chính JDK/JRE đang chạy JVM test. Trên Windows là `java.exe`, trên Unix-like thường là `java`. Không giả định máy có lệnh `java` trong `PATH` hoặc shell được cấu hình giống CI.

Các path có dấu cách được truyền làm **một argument trong ProcessBuilder**, không cần thêm dấu nháy bao quanh path như khi tự ghép một lệnh shell.

### 9.4. Vì sao truyền từng argument tách biệt?

Đúng:

~~~java
new ProcessBuilder(
        java.toString(),
        "-jar",
        jar.toString(),
        "--demo.mode=partial");
~~~

Sai dễ gặp:

~~~java
new ProcessBuilder(
        "java -jar " + jar + " --demo.mode=partial");
~~~

`ProcessBuilder` không mặc định dùng Bash/PowerShell để parse một command string. Truyền một chuỗi ghép như vậy có thể khiến OS tìm một executable tên toàn bộ chuỗi, dẫn đến `IOException`.

**Đừng tự bao jar path bằng dấu nháy literal** trong một argument ProcessBuilder: framework đã truyền cấu trúc argument riêng; thêm dấu `"` vào giá trị path có thể biến dấu nháy thành một phần không mong muốn của tên tệp.

### 9.5. Vì sao redirectErrorStream(true)?

Child process có thể ghi:

- `System.out.println(...)` vào stdout.
- `System.err.println(...)` hoặc Spring Boot failure logs vào stderr.

Nếu chỉ đọc stdout mà bỏ stderr, buffer của stderr có thể đầy và child bị block. Bằng cách:

~~~java
builder.redirectErrorStream(true);
builder.redirectOutput(logFile.toFile());
~~~

mọi log được ghi vào một file. Test không cần hai reader threads để drain hai pipes đồng thời, và không mất output lỗi.

**Trade-off:** Không còn biết từng dòng xuất phát từ stdout hay stderr; việc trộn có thể làm thứ tự log liên luồng không tuyệt đối. Vì vậy test assert **marker/ordering trong các dòng do cùng application code tạo**, không so sánh chính xác toàn bộ stack trace của framework.

### 9.6. Vì sao phải timeout?

`Process.waitFor()` không tham số có thể chờ **vô hạn** khi:

- Runner bị kẹt trong `while(true)`.
- Một thread non-daemon ngăn JVM thoát.
- Network call không timeout.
- Một shutdown hook chờ task không kết thúc.
- Process vô tình mở một HTTP server và tiếp tục chạy.

`process.waitFor(60, TimeUnit.SECONDS)` trả boolean; nếu false, child chưa thoát sau deadline. Test phải gửi `destroy()`, nếu không thành công thì `destroyForcibly()`, và **báo FAIL** để CI không treo.

`destroyForcibly()` **không đảm bảo process đã biến mất ngay tại dòng gọi**; test còn đợi thêm một khoảng ngắn. Timeout 60 giây ở đây là **ngân sách minh họa** cho một Spring Boot CLI nhẹ, có thể điều chỉnh theo máy CI và cold-start time.

### 9.7. Vì sao file log được xóa ở finally?

Nếu assertion hoặc process startup ném exception, test vẫn phải xóa file tạm. Việc dùng `Files.createTempFile(...)` cấp một path riêng cho từng test, giảm xung đột khi test chạy song song.

Trong production CI, đôi khi nên giữ log của testcase thất bại làm artifact. Khi đó có thể copy log sang thư mục report trước khi xóa, nhưng cần policy lưu trữ, xử lý dữ liệu nhạy cảm và không để log vô hạn làm đầy disk.

## 10. Chạy bộ test

Từ thư mục `cli-process-exit-demo`:

~~~bash
gradle test
~~~

Nếu đã tạo Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Vì `test dependsOn bootJar`, Gradle tự build executable JAR trước khi JUnit tạo child processes.

**Sáu test mong đợi:**

~~~text
successReturnsZeroAndClosesContext                 PASS
partialResultReturnsTwelve                         PASS
invalidInputReturnsTwentyOne                       PASS
retryableResultReturnsThirty                       PASS
fatalRunnerFailureReturnsFortyThree                PASS
unsupportedModeReturnsUsageError                   PASS
~~~

Đây là **danh sách kết quả JUnit mong đợi**, không phải cam kết Gradle sẽ in nguyên văn format này trên console: giao diện test reporting phụ thuộc Gradle version và `testLogging` settings.

### Những điều kiện cần đạt

- `:bootJar` được thực hiện trước `:test` theo task dependencies.
- JUnit thấy `demo.jar.path` và file tồn tại.
- Có Java executable dưới `java.home/bin`.
- Mỗi child process tự exit trong 60 giây ở các kịch bản bình thường.
- Mã thoát bằng đúng expected code.
- Các marker stdout/stderr được ghi vào file tạm và đọc lại đầy đủ.
- Sau mỗi test, file tạm được xóa và process không còn chạy.

**Không cần một web server hay cổng TCP.** `WebApplicationType.NONE` của ứng dụng nằm trong chính JAR được JVM con thực thi.

## 11. Chạy JAR bằng tay và đọc mã thoát

Build JAR trước:

~~~bash
gradle bootJar
~~~

Với `rootProject.name` và `version` trong ví dụ, file đầu ra mặc định:

~~~text
build/libs/cli-process-exit-demo-1.0.0.jar
~~~

Nếu thay đổi tên project/version, hãy lấy đường dẫn thực trong `build/libs` hoặc từ `bootJar.archiveFile`; không giữ đường dẫn mẫu một cách mù quáng.

### 11.1. Bash/Zsh — success

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=success
echo $?
~~~

**Các dòng do code demo in**, không tính Spring Boot framework logs:

~~~text
JOB: SUCCESS
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=0
~~~

Shell exit status kỳ vọng: **`0`**.

### 11.2. Bash/Zsh — partial

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=partial
echo $?
~~~

Dòng do demo in:

~~~text
JOB: PARTIAL_RESULT
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=12
~~~

Shell exit status kỳ vọng: **`12`**.

### 11.3. Bash/Zsh — invalid

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=invalid
echo $?
~~~

Dòng do demo in:

~~~text
JOB: INVALID_INPUT
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=21
~~~

Shell exit status kỳ vọng: **`21`**.

### 11.4. Bash/Zsh — retryable

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=retry
echo $?
~~~

Dòng do demo in:

~~~text
JOB: TEMPORARY_UNAVAILABLE
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=30
~~~

Shell exit status kỳ vọng: **`30`**.

### 11.5. Bash/Zsh — fatal startup

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=fatal
echo $?
~~~

**Các marker do demo in**, không gồm stack trace/error report của Spring:

~~~text
JOB: FATAL_STARTUP
LIFECYCLE: closed
MAIN: startup failure code=43
MAIN: exitCode=43
~~~

Shell exit status kỳ vọng: **`43`**. Dòng `MAIN: startup failure code=43` được in vào stderr nên **thứ tự hòa trộn** với Boot logs/đầu ra có thể khác ở một số launcher; test kiểm tra sự hiện diện của marker, không assert toàn bộ log chính xác từng ký tự.

**Không có `EVENT: READY`** vì runner ném exception.

### 11.6. Bash/Zsh — unknown mode

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=no-such-mode
echo $?
~~~

Marker từ demo:

~~~text
JOB: UNKNOWN_MODE
LIFECYCLE: closed
MAIN: startup failure code=64
MAIN: exitCode=64
~~~

Shell exit status kỳ vọng: **`64`**.

### 11.7. Không truyền option

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar
echo $?
~~~

Runner chọn default `success`. Mã thoát kỳ vọng là 0.

### 11.8. Windows PowerShell

~~~powershell
java -jar .\build\libs\cli-process-exit-demo-1.0.0.jar --demo.mode=partial
$LASTEXITCODE
~~~

`$LASTEXITCODE` phản ánh mã của executable Java vừa chạy. Với Bash/Zsh, dùng `$?` **ngay sau lệnh Java**.

**Cẩn thận:** Nếu chạy lệnh khác trước khi đọc `$?`, giá trị có thể bị thay bằng exit status của lệnh đó. Nếu chạy qua pipeline có `tee`, hãy hiểu `pipefail`/`PIPESTATUS` của shell; nếu không, bạn có thể đo mã của `tee` thay vì mã Java.

## 12. Vì sao không dùng gradle bootRun làm nguồn mã thoát?

`gradle bootRun` là một Gradle task chạy ứng dụng Java. Khi child Java process kết thúc non-zero, Gradle thường báo task/build failure với mã của **Gradle process**. Mã đó **không nhất thiết bằng** mã nghiệp vụ `12`, `21` hoặc `43`.

Ví dụ:

~~~bash
gradle bootRun --args="--demo.mode=partial"
echo $?
~~~

Có thể Gradle trả mã build failure chung thay vì 12. Vì thế:

- Dùng `gradle bootRun` để chạy thử chức năng, đọc application logs.
- Dùng `java -jar ...` để đo exit code của **JVM ứng dụng**.
- Dùng `ProcessBuilder` trong test để đo `Process.exitValue()` của đúng JAR.
- Không coi một dòng log `"MAIN: exitCode=12"` là bằng chứng cuối cùng rằng OS nhận 12.

Một test chỉ xác minh nội dung `stdout` và bỏ `exitValue()` sẽ không phát hiện nếu code quên `System.exit(code)`.

## 13. Exception implements ExitCodeGenerator khác bean generator

Project đã minh họa cả hai:

### Bean generator khi run thành công

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
    return outcome::getExitCode;
}
~~~

`SpringApplication.exit(context)` thu thập các bean `ExitCodeGenerator`, lấy mã khác 0 theo contract và đóng context. Trường hợp `success`, kết quả là 0.

### Exception generator khi startup fail

~~~java
public static final class FatalJobException
        extends IllegalStateException implements ExitCodeGenerator {

    public FatalJobException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 43;
    }
}
~~~

Trong đường startup failure, Spring Boot 3.3 có thể tìm exception implements `ExitCodeGenerator` trong cause chain để lấy mã. Main của demo vẫn có một classifier tường minh giúp quá trình test luôn truyền đúng code tới `System.exit` sau khi `run` throw.

### ExitCodeExceptionMapper là lựa chọn thứ ba

Nếu bạn không kiểm soát exception class, Spring Boot còn có `ExitCodeExceptionMapper`:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return error -> {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof IllegalArgumentException) {
                return 64;
            }
        }
        return 0;
    };
}
~~~

**Đây là snippet mở rộng, không nằm trong project runnable.** Cần import `org.springframework.boot.ExitCodeExceptionMapper` và đưa vào một class configuration. Mapper hoạt động trong **đường startup failure khi ApplicationContext active**. Trong Spring Boot 3.3.13, mapped non-zero có ưu tiên trước fallback từ exception implements `ExitCodeGenerator`.

**Không chép snippet vào project mà vẫn giữ classifier main như cũ rồi mong hai chính sách tự đồng bộ**: codeFromFailure của demo không đọc bean mappers trong một context đã startup fail. Khi nâng cấp production, hãy chọn một chính sách thống nhất và viết process-level test cho chính sách thực tế.

### Không dùng mapper cho mọi HTTP request

`ExitCodeExceptionMapper` trong SpringApplication startup failure không tự áp dụng cho mọi exception của Spring MVC, Kafka listener hoặc `@Async` sau khi app ready. Những lỗi đó thuộc cơ chế xử lý runtime riêng. CLI job chạy một lần thường phù hợp hơn để trả process exit code.

## 14. Kiểm thử tiến trình con là kiểm thử black-box

Một process-level integration test quan sát **đầu vào và đầu ra**:

~~~text
Input: executable JAR + CLI arguments + environment
Output: process exit code + stdout/stderr + side effects (nếu có)
~~~

Điều này gần với cách một scheduler thật tương tác với CLI. Test có thể phát hiện những lỗi không thấy trong unit test:

- Quên gọi `System.exit(code)`.
- Tính mã đúng nhưng không đóng context.
- Main không truyền arguments đến `SpringApplication.run(args)`.
- Boot JAR thiếu Main-Class/Start-Class phù hợp.
- Dependency đóng gói thiếu khiến JAR chạy lỗi.
- Ứng dụng tự mở server khiến JVM không thoát.
- Một thread pool không dừng khiến process test timeout.
- Exception bị bọc nhưng main classifier không duyệt cause.
- Shell quoting sai với đường dẫn chứa khoảng trắng.
- Build tool trả mã khác với mã JVM app.

**Giới hạn:** Bản demo không có database/broker thật nên không chứng minh transactional correctness, idempotency, multi-process coordination hoặc khả năng phục hồi khi network lỗi. Cần test riêng cho các phụ thuộc đó.

## 15. Unit test vẫn cần thiết ở tầng nghiệp vụ

Không nên chạy một JVM mới cho mọi trường hợp nhỏ nhất. Nếu xử lý 10.000 trường hợp validation, mỗi lần khởi động Boot JAR sẽ rất chậm.

Một cấu trúc production thường có:

~~~text
JobService
   |
   +-- unit tests: input, output, validation, branch coverage
   |
   +-- Spring integration tests: wiring, runners, lifecycle
   |
   +-- process tests: vài mã thoát đại diện, packaging, shutdown
   |
   +-- system tests: DB/broker/file storage thật khi cần
~~~

Với bài này, sáu child-process tests tập trung vào **hợp đồng từ bên ngoài**. Logic tính kết quả nghiệp vụ được cố ý làm đơn giản để không cần mock database.

### Vì sao không gọi main() trực tiếp trong JUnit?

Một test như:

~~~java
@Test
void badTest() {
    CliExitApplication.main(
            new String[] { "--demo.mode=partial" });
}
~~~

là **anti-pattern** cho project này: `main` gọi `System.exit(12)`, nên có thể kết thúc luôn JVM JUnit/Gradle test worker. `assertThrows` quanh `main` cũng không chuyển `System.exit` thành exception thông thường.

**Giải pháp:** Đưa process termination vào entrypoint ứng dụng và gọi entrypoint **từ JVM con**. Trong test JVM chỉ tương tác với `Process`.

## 16. Những lỗi thường gặp với ProcessBuilder

### Lỗi 1 — Ghép toàn bộ lệnh vào một String

Sai:

~~~java
new ProcessBuilder(
        "java -jar app.jar --demo.mode=partial");
~~~

`ProcessBuilder` không phải shell command parser. Cần tách executable và arguments.

### Lỗi 2 — Hardcode lệnh java trong PATH

Nếu CI có nhiều JDK, lệnh `java` từ PATH có thể không giống JDK mà Gradle dùng. Lấy từ `java.home/bin` giúp đồng nhất môi trường test.

### Lỗi 3 — Chỉ đọc stdout mà không đọc stderr

Child có thể block khi stderr pipe đầy. Dùng redirectErrorStream + redirectOutput file, hoặc tạo hai reader tasks thật sự tiêu thụ cả hai streams song song.

### Lỗi 4 — Đọc toàn bộ output trước khi waitFor nhưng blocking sai

`readAllBytes()` trên pipe có thể chờ EOF rất lâu nếu child không kết thúc; chỉ đọc sau khi process exit và có deadline, hoặc đọc bất đồng bộ. Trong project, file redirect làm luồng chờ dễ kiểm soát.

### Lỗi 5 — waitFor() không timeout

Một regression tạo thread sống mãi có thể treo CI vô hạn. Dùng `waitFor(timeout, unit)`, destroy và fail rõ.

### Lỗi 6 — Timeout nhưng không kill process

Test kết thúc nhưng child JVM còn sống nền, tiếp tục dùng CPU/file/port. Trong `finally` phải kiểm tra `isAlive()` và force kill khi cần.

### Lỗi 7 — Giết child rồi coi test thành công

Timeout phải là **test FAIL**, dù lệnh destroy trả về. Kill chỉ là cleanup, không chứng minh job đã hoàn tất.

### Lỗi 8 — Dùng Process.exitValue() trước khi process kết thúc

`exitValue()` ném `IllegalThreadStateException` nếu child chưa kết thúc. Chỉ gọi sau khi `waitFor(...)` trả `true` hoặc bạn biết process đã exit.

### Lỗi 9 — Đặt sai charset

Nếu output chứa tiếng Việt hoặc ký tự Unicode, phải bảo đảm encoding của JVM con, file và reader tương thích. Project in markers ASCII để kiểm tra ổn định giữa hệ điều hành, đồng thời truyền `-Dfile.encoding=UTF-8` trong child command.

### Lỗi 10 — Đọc log sau khi đã xóa file

Đọc output **trước** `Files.deleteIfExists(...)`. `finally` trong helper chỉ xóa khi `ChildResult` đã chứa String output hoặc khi test gặp lỗi.

### Lỗi 11 — Không quản lý biến môi trường

`ProcessBuilder` thường kế thừa environment của parent. Một property/secret từ môi trường CI có thể thay đổi behavior của child. Với ứng dụng thật, định nghĩa test profile và environment overrides rõ; không vô tình xóa toàn bộ environment (có thể mất PATH, HOME, TMP).

### Lỗi 12 — Kiểm tra đúng stdout nhưng sai exit code

Một app in “SUCCESS” rồi gọi `System.exit(21)` vẫn là thất bại theo process contract. Test phải kiểm tra **cả hai**.

### Lỗi 13 — Kiểm tra đúng exit code nhưng không biết nguyên nhân

`exitCode=21` không đủ chẩn đoán nếu app crash trước khi chạy job và dùng nhầm mã 21. Thêm marker và logging/error category giúp phân biệt.

### Lỗi 14 — Đảm bảo thứ tự từng dòng Boot log

Spring Boot/Gradle logger có thể khác theo version, log level và stdout/stderr merging. Chỉ assert các marker thuộc hợp đồng demo và các quan hệ trước–sau được lifecycle bảo đảm.

### Lỗi 15 — Test JAR cũ

Nếu JAR không được build lại khi code thay đổi, test có thể pass dựa trên phiên bản trước. `test dependsOn bootJar` và lấy `archiveFile` tránh sai lệch cơ bản này.

## 17. Mã thoát trên Unix, Windows và shell pipeline

### Unix-like shells

Trên các môi trường POSIX thông thường, exit status mà shell thể hiện nằm trong dải 0–255; những giá trị rất lớn hoặc âm có thể bị ánh xạ thành 8 bit thấp, khiến status khó dự đoán.

Vì vậy sample dùng các mã **dương nhỏ** như 12, 21, 30, 43 và 64. Không dùng `Integer.MAX_VALUE` làm mã lỗi portable.

Một số shell dùng các status phổ biến:

- `126`: command không thể thực thi.
- `127`: command không tìm thấy.
- `128 + signal`: termination do tín hiệu trong nhiều shell.

Không gán những giá trị đặc biệt đó làm business code nếu scheduler cần phân biệt các tình huống.

### PowerShell

Dùng `$LASTEXITCODE` sau executable Java. Không mặc định coi `$?` của PowerShell là một số nguyên giống Bash; `$?` trong PowerShell là trạng thái thành công/không thành công dạng boolean của lệnh.

### Pipeline có tee

Nếu chạy:

~~~bash
java -jar app.jar --demo.mode=partial | tee output.log
echo $?
~~~

trong một shell không bật `pipefail`, `$?` thường là trạng thái của **tee**, không phải Java. Nếu cần biết mã Java, có thể dùng Bash `PIPESTATUS` hoặc bật `set -o pipefail` tùy shell, nhưng phải hiểu ảnh hưởng tới các lệnh khác trong script.

**ProcessBuilder trong project không dùng shell pipeline**, nên `Process.exitValue()` đọc trực tiếp trạng thái của Java child process.

## 18. Tích hợp với CI/CD và job scheduler

Giả sử một pipeline chạy CLI:

~~~text
Checkout source
   |
Build executable Boot JAR
   |
Run CLI job
   |
Capture process exit code
   |
   +-- 0: success
   +-- 12: partial; inspect report
   +-- 21/64: input/usage error; no blind retry
   +-- 30: temporary; bounded retry
   +-- 43/1: startup or unknown failure; investigate
~~~

Pipeline có thể sử dụng mã thoát để:

- Dừng một stage khi cấu hình sai.
- Báo thành công một job nhập liệu.
- Tách lỗi dữ liệu khỏi lỗi hạ tầng.
- Retry có backoff khi dependency tạm unavailable.
- Tạo alert kèm correlation ID và link tới log/artifact.
- Tránh chạy downstream steps nếu upstream result không thỏa hợp đồng.

### Đừng retry vô hạn chỉ vì mã non-zero

Mã `21` của dữ liệu sai không tự sửa sau nhiều lần gọi. Mã `30` có thể retry nhưng cần:

- Số lần thử tối đa và deadline.
- Backoff/jitter.
- Timeout của mọi network operation.
- Idempotency key hoặc checkpoint nếu job tạo side effects.
- Telemetry cho số lần retry và kết quả cuối.

Một scheduler không được mặc định retry **mọi mã khác 0** với cùng chiến lược.

### Bash script minh họa phân nhánh

~~~bash
#!/usr/bin/env bash

java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=partial

code=$?

case "$code" in
  0)
    echo "Job completed"
    ;;
  12)
    echo "Partial result: inspect report"
    ;;
  21|64)
    echo "Fix input or CLI invocation"
    ;;
  30)
    echo "Retryable: schedule bounded retry"
    ;;
  *)
    echo "Unexpected failure: $code"
    ;;
esac

exit "$code"
~~~

**Đây là script minh họa Bash**, không phải Gradle/JUnit source. Nếu shell chạy với `set -e`, lệnh Java non-zero có thể kết thúc script **trước khi tới case**; cần tạm kiểm soát errexit hoặc dùng cấu trúc `if java ...; then ... else ... fi` phù hợp. Khi cần giữ mã thất bại cho parent scheduler, cuối script trả lại `exit "$code"`.

## 19. Kubernetes Job và container

Trong container CLI, entrypoint nên truyền tín hiệu exit chính xác:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/cli-process-exit-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--demo.mode=success"]
~~~

Đây là **Dockerfile minh họa** chạy được khi JAR đã build và base image được tải, không phải yêu cầu bắt buộc để chạy tests. Dùng exec-form `ENTRYPOINT` giúp Java là process nhận tín hiệu/exit status trực tiếp, tránh một shell wrapper vô tình trả 0 dù Java trả mã khác.

Một Kubernetes `Job` có thể:

- Đánh dấu Pod/container failed khi process trả non-zero.
- Khởi động lại/ tạo pod mới tùy `restartPolicy` và `backoffLimit`.
- Chỉ coi Job thành công khi đạt chính sách completions tương ứng.

**Không nhầm:** Kubernetes không tự biết `21` là dữ liệu sai hay `30` là tạm thời trừ khi bạn định nghĩa policy thông qua controller/operator/script phù hợp. Một Kubernetes Job mặc định chủ yếu nhìn kết quả success/failure, không thực hiện toàn bộ business retry matrix của ứng dụng.

Với side effect, nếu Job được chạy lại sau node failure/SIGKILL, cần idempotency và durable progress; việc gọi `SpringApplication.exit` trên đường bình thường không thể bảo đảm callback chạy khi host chết.

## 20. Mở rộng ứng dụng: thực thi nghiệp vụ thật

Demo chỉ dùng switch để gán code. Một ứng dụng nhập liệu thật thường tách:

~~~text
CliExitApplication
   |
   +-- ApplicationRunner
          |
          +-- JobService.execute(input)
                   |
                   +-- JobResult(status, accepted, rejected, ...)
          |
          +-- map JobResult -> exit code
          |
          +-- JobOutcome bean
   |
   +-- SpringApplication.exit(context)
   |
   +-- System.exit(code)
~~~

Ví dụ domain object Java 17:

~~~java
public record ImportResult(
        int acceptedCount,
        int rejectedCount,
        boolean dependencyUnavailable) {

    public int exitCode() {
        if (dependencyUnavailable) {
            return 30;
        }
        if (rejectedCount > 0) {
            return 12;
        }
        return 0;
    }
}
~~~

Đây là **class record minh họa độc lập về Java**, có thể đặt trong `ImportResult.java`, nhưng không được dùng trực tiếp trong project đã hoàn chỉnh ở mục 7 nếu chưa tạo file tương ứng.

Nếu có exception trong `JobService`:

- Ngoại lệ **không thể tiếp tục startup** có thể propagate từ runner; Boot sẽ đi failure path.
- Một **kết quả nghiệp vụ** được xử lý đầy đủ có thể được map thành exit code trong `JobOutcome` mà không cần throw.
- Không nên gộp “chấp nhận partial result” và “khởi động thất bại” thành một case nếu scheduler cần phân biệt.

### Idempotency khi scheduler retry

Giả sử job đã ghi 8.000 bản ghi vào DB rồi process bị kill trước khi cập nhật progress. Lần chạy mới có thể ghi trùng. Vì vậy cần:

- Job ID/correlation ID ổn định.
- Unique constraint hoặc idempotency key.
- Transaction/outbox/checkpoint theo business operation.
- Retry budget và dead-letter/reporting phù hợp.
- Tránh chỉ dựa vào local in-memory flags.

Process exit code chỉ **báo kết quả**; nó không tự tạo exactly-once execution.

## 21. Mở rộng ProcessBuilder test với input và environment

Project chuẩn truyền một CLI option. Khi job cần file path hoặc environment variable, tiếp tục truyền qua argument list:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        java.toString(),
        "-jar",
        jar.toString(),
        "--demo.mode=success",
        "--job.input=" + inputFile.toAbsolutePath());
~~~

Đây là **snippet minh họa**, giả định đã có `java`, `jar`, `inputFile` kiểu `Path`. Không cần tự quote path chứa dấu cách.

Environment override riêng cho child:

~~~java
builder.environment().put(
        "APP_TEST_MODE", "true");
~~~

Nên chỉ override những keys test cần, tránh xóa toàn bộ environment. Nếu có secret dùng trong CI, đừng in toàn bộ environment hoặc ghi vào test logs.

### Test thiếu file hoặc file không đọc được

Một process-level test có thể tạo file tạm ở parent, truyền absolute path cho child, cho child parse rồi trả mã 21 nếu input sai. Parent phải cleanup file temp và test report sau đó. Điều này tăng tính thực tế hơn chỉ dùng switch, nhưng cũng tăng chi phí I/O và phải kiểm soát file lock trên Windows.

### Test stderr độc lập

Nếu cần phân biệt stderr với stdout, **không** dùng `redirectErrorStream(true)`. Thay vào đó redirect ra **hai file riêng** hoặc hai reader tasks đồng thời. Không đọc tuần tự hai streams mà đợi vô hạn khi child có thể ghi nhiều dữ liệu vào stream còn lại.

### Test output lớn

Một job có thể ghi gigabytes log. Trong test như vậy, không nên đọc toàn bộ file log vào String sau exit. Có thể giới hạn log size, parse dòng cần thiết theo streaming, lưu artifact khi fail và tự xóa logs cũ. Demo dùng output ngắn nên `Files.readString(...)` là phù hợp.

## 22. Phân biệt startup failure, normal exit và hard kill

| Tình huống | Có context thành công? | Có SpringApplication.exit? | Mã được xác định bằng cách nào? |
| --- | --- | --- | --- |
| Runner return SUCCESS | Có | Có | Bean generator trả 0 |
| Runner return PARTIAL | Có | Có | Bean generator trả 12 |
| Runner return INVALID_INPUT | Có | Có | Bean generator trả 21 |
| Runner return TEMPORARY_UNAVAILABLE | Có | Có | Bean generator trả 30 |
| Runner throw FatalJobException | Không trả context thành công cho main | Không ở main | Catch phân loại cause, explicit System.exit(43) |
| Args không hỗ trợ | Không trả context thành công | Không ở main | Catch phân loại usage error, explicit System.exit(64) |
| Process bị SIGKILL | Không có đảm bảo callback Java chạy | Không bảo đảm | OS/orchestrator xác định status theo signal |
| JVM/host crash | Không | Không bảo đảm | External supervisor nhận failure/signal theo môi trường |

**Điểm mấu chốt:** `SpringApplication.exit(context)` là giải pháp tốt khi **đã có một context chạy được**. Không truyền `null` vào nó sau khi `run` throw.

### ContextClosedEvent không phải kết quả nghiệp vụ

Một context có thể đã đóng và mọi Spring-managed bean destroy callback đã chạy, nhưng job vẫn có kết quả PARTIAL. Đừng lấy `ContextClosedEvent` hoặc “shutdown complete” làm tín hiệu SUCCESS cho scheduler. Cần kết hợp **job result**, **resource cleanup**, **process exit status**.

### Đóng context trước System.exit

Khi gọi `SpringApplication.exit(context)` trước `System.exit(code)`, ứng dụng cho các bean có cơ hội chạy destruction callbacks/flush phù hợp. Nếu app có task nền, phải dừng nhận việc và drain theo deadline trước khi đóng resource cần thiết; không giả định một callback destroy ngắn đủ chờ mọi job dài hạn.

## 23. Các lỗi dễ mắc khi thiết kế CLI

**1. “In exitCode=12 là OS đã nhận 12.”** Sai. Phải `System.exit(12)` hoặc cơ chế tương đương.

**2. “SpringApplication.exit sẽ tự dừng JVM.”** Không. Nó trả mã `int` và đóng context, khác `System.exit`.

**3. “Mã ExitCodeGenerator chỉ dùng khi exception throw.”** Không. Bean có thể cung cấp mã kết quả nghiệp vụ khi exit(context).

**4. “Nếu runner hoàn thành bình thường thì exit luôn 0.”** Không. Bean generator có thể trả 12/21/30.

**5. “ApplicationReadyEvent đồng nghĩa job nghiệp vụ thành công.”** Không. Ready là mốc lifecycle sau runner return bình thường, không tự đọc JobOutcome.

**6. “Khi runner throw, main vẫn có context để gọi SpringApplication.exit.”** Không. `run` chưa trả context thành công.

**7. “Chỉ check exception ngoài cùng là đủ.”** Không. Runner failure có thể bị Spring Boot wrap; cần cause chain.

**8. “Dùng ExitCodeExceptionMapper đồng thời với classifier thủ công thì Boot tự đồng bộ cả hai.”** Không. Chọn một chính sách nhất quán và test.

**9. “System.exit trong runner giúp code ngắn hơn.”** Có thể cắt ngang error reporting/cleanup; nên đặt tại entrypoint.

**10. “JUnit gọi main trực tiếp rồi kiểm tra code.”** Có nguy cơ kết thúc luôn JVM test.

**11. “ProcessBuilder hiểu chuỗi giống PowerShell/Bash.”** Không. Dùng argument list riêng.

**12. “Cứ thêm dấu nháy vào path truyền cho ProcessBuilder.”** Có thể biến quote thành dữ liệu literal; đừng tự quote.

**13. “Process.waitFor() không deadline là an toàn vì demo rất nhỏ.”** Regression có thể tạo thread không thoát; cần timeout.

**14. “destroyForcibly() là test PASS.”** Không. Force kill chỉ cleanup process bị treo, test phải FAIL.

**15. “Không cần đọc stderr.”** Có thể gây deadlock nếu child ghi nhiều vào error pipe.

**16. “Dùng Files.readAllBytes trên pipe trước waitFor là luôn an toàn.”** Không nếu child không bao giờ đóng output; nên drain bất đồng bộ hoặc redirect file.

**17. “Mã của gradle bootRun giống mã java -jar.”** Không bảo đảm; Gradle có thể wrap lỗi thành build failure.

**18. “Chỉ assert exitValue là đủ.”** Có thể đúng mã tình cờ; cần thêm marker/log và nếu cần side effect checks.

**19. “Hardcode build/libs/name.jar luôn ổn.”** Không khi project version thay đổi; lấy `bootJar.archiveFile`.

**20. “Một test JAR cũ cũng là integration test có ý nghĩa.”** Không; phải có dependency build artifact trước test.

**21. “Có WebApplicationType.NONE là chắc chắn không còn background thread.”** Không; user-created threads, schedulers và consumers vẫn có thể chạy.

**22. “Mã exit âm hoặc trên 255 luôn giữ nguyên trong mọi shell.”** Không có bảo đảm portability; dùng số dương nhỏ và test OS đích.

**23. “Mã 30 nghĩa là scheduler phải retry vô hạn.”** Không. Retry cần budget và idempotency.

**24. “Partial result có thể coi như 0 vì ứng dụng không crash.”** Không nếu hợp đồng scheduler yêu cầu phân biệt partial.

**25. “Kubernetes hiểu từng business exit code.”** Không tự động, cần policy/controller/script phù hợp.

**26. “@PreDestroy chạy được cả khi SIGKILL.”** Không. Hard kill bỏ qua Java cleanup hooks.

**27. “Mỗi test process phải dùng cùng một file log.”** Không. Có nguy cơ đè dữ liệu khi test chạy song song; dùng temp file riêng.

**28. “$? của Bash là mã của Java ngay cả sau tee hoặc echo.”** Không nhất thiết. Lấy status ngay sau process trực tiếp, hoặc xử lý pipeline đúng cách.

**29. “Không cần xử lý timeout trong test CI.”** Sai. Một process treo có thể khóa cả pipeline.

**30. “Result code 0 trong bean có nghĩa mọi tài nguyên đã flush.”** Không. Cần đặt thời điểm xác định SUCCESS sau commit/ack thật sự và có cleanup đảm bảo.

## 24. Checklist code review

Trước khi triển khai CLI vào scheduler, rà soát:

1. **Entrypoint:** Có `SpringApplication.run(args)` nhận args và đặt `WebApplicationType.NONE` nếu không cần web?
2. **Nghiệp vụ:** Runner thực hiện đúng một lần và chuyển kết quả sang cấu trúc domain rõ?
3. **Exit contract:** Bảng mã có tên/ý nghĩa/retry policy ổn định?
4. **Bean generator:** `ExitCodeGenerator` có đọc đúng kết quả cuối cùng, không trả 0 mặc định sai?
5. **Startup exception:** Lỗi runner được phân loại, cause chain không bị mất?
6. **Exit ordering:** Cleanup/context close xảy ra trước `System.exit` ở đường bình thường?
7. **Non-web:** Không vô tình start server hoặc thread giữ JVM sống?
8. **Build:** `bootJar` tạo executable JAR đúng `mainClass` và version?
9. **Tests:** Dùng `ProcessBuilder` chạy **JAR của build hiện tại**, không classpath ngẫu nhiên?
10. **OS portability:** Java executable và JAR path truyền thành arguments riêng?
11. **Output:** stdout/stderr được tiêu thụ hoặc redirect; log không gây deadlock?
12. **Timeout:** Child có deadline và force cleanup khi quá hạn?
13. **Assertions:** Kiểm tra cả exit status lẫn các marker/side effects?
14. **Isolation:** Mỗi test có temp output riêng, không static mutable state?
15. **CI:** Mã non-zero không bị shell/Gradle wrapper chuyển thành 0?
16. **Operations:** Retry cho đúng mã, có idempotency, deadline và cảnh báo?
17. **Secrets:** Không log credential hoặc biến môi trường nhạy cảm?
18. **Failure recovery:** Nếu SIGKILL/host crash, có checkpoint/reconciliation không?
19. **Deployment:** Docker/Kubernetes entrypoint bảo toàn mã JVM?
20. **Versioning:** Khi nâng cấp Spring Boot/JDK/Gradle, process tests được chạy lại?

## 25. Bài thực hành

1. Mô tả các vai trò khác nhau của `SpringApplication.run`, `SpringApplication.exit` và `System.exit`.
2. Tại sao một CLI non-web vẫn cần `ApplicationContext` và `ApplicationRunner`?
3. Chạy `gradle test` rồi xác định task nào tạo JAR trước JUnit.
4. Chạy `--demo.mode=success`. Vì sao có `EVENT: READY` trước `LIFECYCLE: closed`?
5. Chạy `--demo.mode=partial`. Vì sao có Ready nhưng process exit 12?
6. Thử `--demo.mode=invalid`. Điều gì khiến mã là 21 thay vì JVM tự chọn 1?
7. Chạy `--demo.mode=retry`. Scheduler nên retry với chính sách nào? Vì sao không retry vô hạn?
8. Chạy `--demo.mode=fatal`. Vì sao không có `EVENT: READY`?
9. Lỗi `FatalJobException` có thể bị wrap. Code nào trong main tìm được mã 43?
10. Bỏ `System.exit(code)` ở cuối main. Test nào sẽ phát hiện sai hợp đồng? Kết quả process status thay đổi thế nào?
11. Đổi `ExitCodeGenerator` bean luôn trả 0. Những test nào thất bại?
12. Đưa `System.exit(12)` trực tiếp vào runner. Những cleanup markers/lifecycle nào có thể mất?
13. Gọi `CliExitApplication.main(...)` trực tiếp trong JUnit. Vì sao đây là anti-pattern?
14. Sửa test để chỉ kiểm tra log `MAIN: exitCode=12` mà không assert `exitValue`. Lỗi nào có thể lọt?
15. Cố ý xóa `dependsOn bootJar` rồi chạy test sau khi sửa Java source. Rủi ro gì xảy ra?
16. Đổi version trong Gradle từ 1.0.0 thành 1.0.1. Vì sao test vẫn tìm đúng JAR?
17. Đổi JAR path sang một path chứa dấu cách. Vì sao ProcessBuilder argument list xử lý tốt hơn shell string?
18. Thử bỏ `redirectErrorStream(true)` và để child ghi nhiều stderr. Những dạng deadlock nào có thể xảy ra?
19. Thay `redirectOutput(file)` bằng `getInputStream().readAllBytes()` trước khi child thoát. Nếu child treo, vấn đề gì xảy ra?
20. Thêm mode `hang` chỉ cho sandbox. Bộ test có timeout/hủy child đúng không?
21. Trong test, thử gọi `process.exitValue()` ngay sau `start()`. Exception nào có thể xảy ra?
22. Thêm mode không truyền giá trị `--demo.mode`. Code `ApplicationArguments` xử lý ra sao?
23. Truyền `--demo.mode=success` hai lần. Vì sao demo trả usage error thay vì chọn một value?
24. Chạy `java -jar` trong Bash rồi `echo $?` ngay sau. Vì sao không nên chạy `echo hello` ở giữa?
25. Chạy ứng dụng qua pipeline với `tee`. Làm thế nào giữ exit code của Java?
26. Chạy trong PowerShell. Vì sao `$LASTEXITCODE` phù hợp hơn dùng `$?` để lấy số nguyên?
27. Thêm bean có `@PreDestroy` ghi nhận một tài nguyên đã đóng. Assert ra sao để không chỉ tin log?
28. Thiết kế một `JobResult` record và method map status → code theo business rules.
29. Một job commit DB thành công nhưng crash trước khi gửi ack. Vì sao process test không thể bảo đảm exactly-once?
30. Thêm một mode `unexpected` ném exception không implements generator. Main trả mã fallback nào?
31. Viết test `ProcessBuilder.environment()` để truyền một giá trị cấu hình riêng cho child mà không đổi system properties của test JVM.
32. Thêm test cho process exit code 64 khi tham số không được hỗ trợ, nhưng log không lộ giá trị secret trong input.
33. So sánh một `@SpringBootTest` test thành công với child-process test: cái nào kiểm tra OS exit status thật?
34. Nếu cần kiểm tra 1.000 biến thể validation, nên đặt bao nhiêu test là unit test và bao nhiêu test là process-level? Giải thích trade-off.
35. Tích hợp JAR vào Kubernetes Job: controller mặc định hiểu gì khi exit 12, và cần logic ngoài nào nếu muốn xử lý riêng?
36. Nếu CI có JDK 17 và 21 đồng thời, vì sao dùng `java.home` cho test child giảm rủi ro?
37. Một child process ghi log nhiều gigabytes. Bạn sẽ sửa helper để tránh `Files.readString` load toàn bộ vào RAM như thế nào?
38. Khi process bị SIGKILL, Java `@PreDestroy` có được bảo đảm không? Cần recovery strategy nào?
39. Thiết kế một bảng codes cho job nhập file: thành công, partial, bad input, dependency temporary, permission denied, unknown.
40. Đề xuất checklist trước khi release một CLI có mã thoát là API contract cho bên điều phối.

## Ghi nhớ

- **Kết quả nghiệp vụ và vòng đời Spring Boot là hai tầng khác nhau.** Runner có thể return bình thường và Boot phát Ready, nhưng CLI vẫn trả non-zero qua `ExitCodeGenerator` bean.
- `SpringApplication.exit(context)` **lấy mã từ generator và đóng context**, còn `System.exit(code)` mới truyền mã cho process owner.
- Khi `SpringApplication.run` throw, main không nhận được context thành công; có thể phân loại exception/cause chain và trả mã startup failure rõ ràng.
- Không gọi `System.exit` ngay trong JUnit hay một bean lifecycle callback; **dùng JVM con**.
- `ProcessBuilder` nhận **executable + từng argument riêng**, không phải một shell command string.
- Khi test child process, phải **drain/redirect stdout+stderr**, có `waitFor(timeout)`, hủy tiến trình khi quá hạn và cleanup file log trong `finally`.
- `Process.exitValue()` sau khi child kết thúc là dữ kiện xác minh **OS-level exit status**; không thay thế bằng một dòng in trong log.
- `test dependsOn bootJar` và property trỏ tới `bootJar.archiveFile` giúp kiểm tra **đúng JAR hiện tại**.
- Không dùng `gradle bootRun` làm nguồn chân lý duy nhất cho business exit code; Gradle có mã thoát build riêng.
- Sử dụng mã nhỏ, ổn định và tài liệu hóa retry policy; tránh các giá trị không portable qua shell/OS.
- Với job có side effects, exit code không thay thế timeout, transaction, idempotency, checkpoint hay recovery.

### Tài liệu tham khảo

- Spring Boot 3.3 — Application Exit và ExitCodeGenerator: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — SpringApplication Javadoc (exit, run, WebApplicationType): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — ExitCodeGenerator Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3 — ExitCodeExceptionMapper Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3 — ApplicationRunner và ApplicationArguments: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — SpringApplication failure/exit-code source: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Java SE 17 — Process: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html
- Java SE 17 — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java SE 17 — System.exit: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Task Dependencies: https://docs.gradle.org/current/userguide/part2_gradle_tasks.html
- Kubernetes — Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
