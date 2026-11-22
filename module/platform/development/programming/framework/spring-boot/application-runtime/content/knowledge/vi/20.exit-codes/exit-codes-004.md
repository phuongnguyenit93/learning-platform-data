# Triển khai ExitCodeGenerator cho ứng dụng dòng lệnh Spring Boot

## 1. Vì sao ứng dụng CLI cần một mã thoát?

Một chương trình dòng lệnh thường được chạy bởi người dùng, shell script, CI/CD, cron, Docker hoặc Kubernetes Job. Khi tiến trình Java kết thúc, thành phần gọi chương trình cần biết **kết quả cuối cùng** để quyết định chạy bước tiếp theo, cảnh báo, retry hay đánh dấu batch thất bại.

Quy ước phổ biến:

- **Exit code = 0**: chương trình hoàn tất theo nghĩa thành công mà công cụ đã công bố.
- **Exit code khác 0**: chương trình không đạt kết quả thành công; số cụ thể có thể phân loại lỗi hoặc tình huống nghiệp vụ.
- Ý nghĩa **2, 4, 7, 64...** phải do ứng dụng và hạ tầng thống nhất; không có bảng số lỗi riêng được Spring Boot tự áp đặt cho mọi nghiệp vụ.

Spring Boot hỗ trợ interface **`org.springframework.boot.ExitCodeGenerator`** để bean trả về mã thoát khi ứng dụng chuẩn bị exit qua **`SpringApplication.exit(...)`**. Tài liệu Boot 3.3 dùng mô hình:

```java
System.exit(
    SpringApplication.exit(
        SpringApplication.run(MyApplication.class, args)
    )
);
```

Đây là **mẫu minh họa**, cần có `MyApplication` và import phù hợp. Ba lời gọi có vai trò riêng:

1. `SpringApplication.run(...)`: khởi động context và gọi `ApplicationRunner`/`CommandLineRunner`; trả về context khi startup thành công.
2. `SpringApplication.exit(context)`: xác định exit code từ các `ExitCodeGenerator` liên quan, **đóng context**, trả về một giá trị `int`.
3. `System.exit(code)`: yêu cầu **JVM thoát** với mã đó để hệ điều hành/launcher nhận được trạng thái tiến trình.

**Quan trọng nhất:** Chỉ triển khai `ExitCodeGenerator` mà không gọi đường `SpringApplication.exit(...)` phù hợp **không có nghĩa Java tự gửi mã đó cho shell**. Và `SpringApplication.exit(context)` trả về một `int` **không đồng nghĩa** đã gọi `System.exit`. Cần phân biệt Spring-level outcome, JVM process exit và cách môi trường nhận exit status.

Bài sử dụng **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+**. Ví dụ được thiết kế cho **non-web CLI chạy một lần**, không dùng `System.exit` như cách dừng một web service đang phục vụ request.

## 2. Ba loại “kết thúc” khác nhau

| Tầng | Ví dụ | Ý nghĩa và giới hạn |
| --- | --- | --- |
| **Nghiệp vụ hoàn tất** | Job đã nhập dữ liệu hoặc phát hiện input không hợp lệ | Ứng dụng tự xác định status; có thể là 0 hoặc nonzero mà không ném exception |
| **Spring context đóng** | `SpringApplication.exit(context)` | Spring tính mã thoát và đóng context, kích hoạt lifecycle/destruction callbacks khi khả thi |
| **JVM/process kết thúc** | `System.exit(code)` | Hệ điều hành nhận exit status của tiến trình Java; Java không chạy các dòng sau `System.exit` bình thường |
| **Shell/CI quan sát kết quả** | Bash `$?`, PowerShell `$LASTEXITCODE`, Kubernetes Job | Dùng mã process thực sự nhận, có thể bị launcher hoặc wrapper diễn giải |
| **Tài nguyên đã được giải phóng** | `@PreDestroy`/`DisposableBean.destroy()` | Chỉ là cleanup theo lifecycle; không chứng minh đã rollback toàn bộ side effects bên ngoài |

Một số hiểu nhầm:

- `return;` từ `main` là kết thúc method, **không phải gọi ExitCodeGenerator**.
- `System.out.println("status=7")` chỉ in thông báo, **không đổi exit code của process**.
- `SpringApplication.exit(context)` đóng context và **trả int**, nhưng nếu caller bỏ qua kết quả, shell chưa chắc nhận số đó.
- `System.exit(7)` đưa status đến JVM, nhưng nếu gọi quá sớm bên trong runner, bạn có thể phá trình tự cleanup có kiểm soát của Spring.

### 2.1. Tại sao non-web CLI phù hợp với pattern này?

Trong ứng dụng CLI, công việc thường có điểm kết thúc xác định: đọc file, validate, xử lý batch, phát hiện lỗi nghiệp vụ, ghi kết quả rồi thoát. Khi tất cả công việc bắt buộc hoàn tất, main có thể đóng context và trả mã.

Với web server hoặc scheduler chạy lâu dài, `SpringApplication.run(...)` được thiết kế để context tiếp tục hoạt động, và process nhận tín hiệu shutdown từ môi trường. Gọi `System.exit(SpringApplication.exit(...))` ngay sau `run(...)` trong một web app có thể **đóng server gần như ngay lập tức**. Chỉ dùng mô hình CLI khi việc kết thúc sau startup là **chủ đích**.

## 3. ExitCodeGenerator API thực chất là gì?

Trong Spring Boot 3.3, `ExitCodeGenerator` là một functional interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

Đoạn trên chỉ **minh họa chữ ký API**; dự án thật import interface của Spring Boot, không tự định nghĩa lại.

`getExitCode()` là một phép hỏi **mã thoát nên sử dụng**. Nó không mang tham số và trả về một số nguyên. Một implementation đơn giản:

```java
final class JobExitStatus implements ExitCodeGenerator {
    private int code;

    void setCode(int code) {
        this.code = code;
    }

    @Override
    public int getExitCode() {
        return code;
    }
}
```

Đây là **đoạn class minh họa**, cần import `ExitCodeGenerator` và đăng ký instance làm Spring bean nếu muốn `SpringApplication.exit(context)` thu thập nó. Vì `code` khởi tạo mặc định bằng `0`, caller phải cập nhật thành nonzero khi phát hiện outcome tương ứng.

### 3.1. ExitCodeGenerator là bean hay chỉ là object Java?

Một bean implement `ExitCodeGenerator` được `SpringApplication.exit(context)` phát hiện trong các bean của context. Ví dụ:

```java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
```

Đây là một **đoạn method trong class @Configuration/@SpringBootApplication**, không độc lập. Với bean này, nếu context startup thành công và caller thực hiện `SpringApplication.exit(context)`, generator có thể cung cấp mã `42`.

Ngược lại, việc viết `new JobExitStatus()` ở đâu đó mà **không đăng ký nó làm bean** không khiến Spring tự thu thập object đó. Có thể truyền generator trực tiếp khi gọi `SpringApplication.exit(context, generator1, ...)`, nhưng đó là **đường API khác** và bạn phải chủ động cung cấp instance.

### 3.2. Có cần ném exception để trả exit code nonzero?

**Không.** Một batch có thể chạy bình thường về mặt kỹ thuật nhưng trả kết quả nghiệp vụ “không đạt”: chẳng hạn có bản ghi bị bỏ qua hoặc input không hợp lệ. Runner có thể lưu mã thoát trong một bean `ExitCodeGenerator` và **return bình thường**; `SpringApplication.exit(context)` đọc trạng thái và trả mã nonzero.

Ngược lại, nếu `ApplicationRunner.run(...)` ném exception, `SpringApplication.run(...)` không trả về context theo đường thành công. Đó là **startup failure path** khác với mô hình “normal run + exit status” của ví dụ chính. Cách ánh xạ exception được giải thích riêng ở mục sau.

## 4. Vòng đời chuẩn khi ứng dụng CLI có ExitCodeGenerator

```text
OS/shell gọi java -jar batch.jar --mode=partial
    |
    +--> main(String[] args)
    +--> SpringApplication.run(...)
    |       +--> refresh ApplicationContext
    |       +--> ApplicationStartedEvent
    |       +--> chạy ApplicationRunner / CommandLineRunner
    |       |       +--> xử lý nghiệp vụ
    |       |       +--> cập nhật bean trạng thái
    |       +--> ApplicationReadyEvent
    |       +--> return context
    |
    +--> SpringApplication.exit(context)
    |       +--> thu thập ExitCodeGenerator beans
    |       +--> lấy mã khác 0 đầu tiên theo ordering
    |       +--> đóng context (ContextClosedEvent, Lifecycle stop, bean destroy)
    |       +--> return int exitCode
    |
    +--> System.exit(exitCode)
    |       +--> JVM/process shutdown
    |
    +--> shell/CI/Kubernetes đọc exit status
```

**Lưu ý:** Trong Spring Boot 3.3, `ApplicationReadyEvent` có thể được phát trước khi main gọi `SpringApplication.exit`, ngay cả khi mã nghiệp vụ sẽ là 4 hoặc 7. Đây **không phải mâu thuẫn**: Boot “ready” chỉ nói startup path hoàn tất theo contract, không có nghĩa job nghiệp vụ đã được khai báo “exit 0”. Với CLI chạy một lần, `ApplicationReadyEvent` không nên được dùng làm bằng chứng batch đạt yêu cầu kinh doanh.

Nếu runner dùng thread nền, `ApplicationReadyEvent` cũng không tự đợi mọi future đã submit. Để mã thoát có nghĩa, công việc bắt buộc phải được chờ/đánh giá đầy đủ trước khi `getExitCode()` được gọi, hoặc có status model đủ xác nhận kết quả.

### 4.1. “Exit” trong tên method không có nghĩa System.exit

`SpringApplication.exit(context)` trả `int`. Nó **đóng context** nhưng **không tự gọi `System.exit(int)`**. Vì thế mô hình rõ nghĩa là:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

Đây là đoạn minh họa, cần import và class ứng dụng. Chúng ta cố ý tách hai dòng cuối để có thể log/kiểm thử **mã được chọn** trước khi JVM thực sự exit.

## 5. Ví dụ chạy được: CLI có bốn kết quả 0, 2, 4, 7

Ta tạo một ứng dụng Java 17 / Spring Boot 3.3.13 không mở cổng HTTP. Một `ApplicationRunner` đọc `--mode=...` và xác định kết quả; một singleton bean **triển khai `ExitCodeGenerator`** lưu kết quả đó. Khi runner hoàn tất, main gọi `SpringApplication.exit(context)` để đọc mã và cleanup, rồi gọi `System.exit(code)` để shell nhận status.

Các mode:

| Tham số | Mã thoát | Ý nghĩa mẫu |
| --- | ---: | --- |
| Không có `--mode` hoặc `--mode=ok` | **0** | Batch thành công |
| `--mode=partial` | **4** | Có kết quả từng phần cần xử lý tiếp theo hợp đồng |
| `--mode=fail` | **7** | Tác vụ nghiệp vụ thất bại có kiểm soát |
| `--mode=wrong` hoặc `--mode` không có giá trị | **2** | Tham số đầu vào không hợp lệ |

Đây là **mã do bài học tự chọn** để người học có thể quan sát. Spring Boot **không tự định nghĩa** 2 là invalid argument hoặc 7 là business failure cho mọi dự án.

### 5.1. build.gradle

Tạo project Gradle Groovy có Gradle Wrapper phù hợp, Java 17. File **`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File **`settings.gradle`**:

```groovy
rootProject.name = 'cli-exit-code-lab'
```

File **`src/main/resources/application.properties`**:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Không thêm `spring-boot-starter-web`: đây là **CLI chạy một lần**. Chúng ta chủ động gọi exit khi việc xử lý đã kết thúc, không cần HTTP server hoặc scheduler dài hạn.

### 5.2. File Java hoàn chỉnh

Tạo đúng file **`src/main/java/com/example/exitcode/CliExitCodeApplication.java`**:

```java
package com.example.exitcode;

import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CliExitCodeApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CliExitCodeApplication.class, args);

        // Tính exit code và ĐÓNG context, nhưng chưa thoát JVM.
        int code = SpringApplication.exit(context);

        System.out.println("EXIT requested=" + code);

        // Đưa mã thoát cho hệ điều hành / shell.
        System.exit(code);
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ApplicationRunner processBatch(JobOutcome outcome) {
        return args -> {
            List<String> values = args.getOptionValues("mode");

            // Không có option -> mặc định ok.
            // Có 0 hoặc nhiều hơn 1 value -> invalid.
            String mode = values == null
                    ? "ok"
                    : (values.size() == 1 ? values.get(0) : "invalid");

            int code = switch (mode) {
                case "ok" -> 0;
                case "partial" -> 4;
                case "fail" -> 7;
                default -> 2;
            };

            // Trạng thái được ghi TRƯỚC khi runner return.
            outcome.setCode(code);
            System.out.println("RUN mode=" + mode + " code=" + code);
        };
    }

    @Bean
    CloseProbe closeProbe() {
        return new CloseProbe();
    }

    // Đây là Spring bean implement ExitCodeGenerator.
    static final class JobOutcome implements ExitCodeGenerator {
        private int code = 0;

        void setCode(int code) {
            this.code = code;
        }

        @Override
        public int getExitCode() {
            return code;
        }
    }

    static final class CloseProbe {
        @PreDestroy
        public void onClose() {
            System.out.println("CLEANUP @PreDestroy");
        }
    }
}
```

**Chương trình dùng Java 17 switch expression và không cần thư viện ngoài Spring Boot starter.** Mọi class cần thiết nằm trong một file, tên package trùng đường dẫn.

### 5.3. Vì sao mã này hoạt động đúng?

1. `@SpringBootApplication` khởi tạo context. `processBatch(...)` đăng ký một bean `ApplicationRunner`.
2. `JobOutcome` do `@Bean` tạo ra, nằm trong Spring container và **implement `ExitCodeGenerator`**, nên `SpringApplication.exit(context)` sẽ thu thập nó.
3. `ApplicationArguments.getOptionValues("mode")` lấy danh sách giá trị của CLI option. Không có option thì `null`; option có một value hợp lệ sẽ được dùng để xét mode; giá trị trống, không hợp lệ hoặc nhiều giá trị chuyển sang mã 2.
4. Runner tính mã theo **kết quả nghiệp vụ mẫu**, cập nhật bean và return bình thường. Nó không gọi `System.exit` và không throw exception.
5. `SpringApplication.run(...)` chỉ trả context sau startup bình thường và sau các runner. Khi main gọi `SpringApplication.exit(context)`, bean exit generator trả mã vừa lưu.
6. `SpringApplication.exit(context)` đóng context. `CloseProbe` là singleton có `@PreDestroy`, nên nó có cơ hội in `CLEANUP` **trước khi main in mã exit**.
7. `System.exit(code)` mới gửi mã đó cho operating system. Không có dòng Java nào sau `System.exit` được kỳ vọng chạy trong chương trình bình thường.
8. Vì chỉ có **một** `ExitCodeGenerator` bean và không truyền thêm generator vào `exit`, không có tranh chấp thứ tự chọn code.

**Chú ý trạng thái đồng thời:** Trong ví dụ, runner và main thực hiện tuần tự trên thread chính, nên field `code` đơn giản là đủ. Nếu nhiều thread cập nhật outcome, phải chọn cơ chế đồng bộ hóa/atomic và quy tắc chốt kết quả rõ ràng. Không để một async job còn pending cập nhật exit code **sau khi** `SpringApplication.exit` đã đọc.

### 5.4. Build executable JAR

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

macOS/Linux:

```bash
./gradlew bootJar
```

Đầu ra tiêu chuẩn theo project configuration là file:

```text
build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar
```

File sẽ có khi Gradle build thành công và wrapper/toolchain resolve được dependencies. Dùng `java -version` để xác nhận JVM tối thiểu Java 17.

### 5.5. Chạy ở Bash và đọc exit code

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=ok
echo $?
```

Các dòng **do chương trình Java in**:

```text
RUN mode=ok code=0
CLEANUP @PreDestroy
EXIT requested=0
```

Dòng `echo $?` tiếp theo sẽ in:

```text
0
```

Với mode từng phần:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=partial
echo $?
```

Các dòng từ Java:

```text
RUN mode=partial code=4
CLEANUP @PreDestroy
EXIT requested=4
```

`echo $?` in `4`.

Với mode thất bại nghiệp vụ:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=fail
echo $?
```

Các dòng từ Java:

```text
RUN mode=fail code=7
CLEANUP @PreDestroy
EXIT requested=7
```

`echo $?` in `7`.

Với option không hợp lệ:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=wrong
echo $?
```

Chương trình in:

```text
RUN mode=wrong code=2
CLEANUP @PreDestroy
EXIT requested=2
```

`echo $?` in `2`. Nếu chạy không có `--mode`, chương trình mặc định `mode=ok` và thoát 0.

**Lưu ý:** `echo $?` trong Bash phải chạy **ngay sau lệnh Java** nếu muốn biết exit status của Java. Một command xen giữa có thể ghi đè biến trạng thái của lệnh gần nhất.

### 5.6. Chạy và lấy exit code trong PowerShell

```powershell
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=fail
$LASTEXITCODE
```

PowerShell sẽ hiển thị số `7` cho mã thoát của process `java` vừa chạy. Có thể dùng:

```powershell
if ($LASTEXITCODE -ne 0) {
    Write-Host "Batch failed with code $LASTEXITCODE"
}
```

Trong Windows PowerShell, **`$LASTEXITCODE`** là tín hiệu trực tiếp cho exit status của native executable gần nhất. `$?` có ngữ nghĩa kết quả command pipeline PowerShell và cách phản ánh native exit code còn phụ thuộc phiên bản/cấu hình, nên không thay thế mặc định cho `$LASTEXITCODE` trong bài kiểm tra này.

### 5.7. Vì sao nên kiểm thử qua java -jar thay vì chỉ bootRun?

`gradlew bootRun` chạy Java qua **một Gradle task**. Khi ứng dụng gọi `System.exit(7)`, Gradle có thể đánh dấu task thất bại, rồi bản thân Gradle process trả mã riêng. Do đó exit status của **`gradlew`** không phải lúc nào cũng chính là **7**. Muốn xác minh **mã do Java CLI thật sự trả cho hệ điều hành**, nên build JAR rồi chạy trực tiếp `java -jar`, như ví dụ trên.

Trong test tự động cũng vậy: kiểm tra exit status của **process ứng dụng**, không chỉ text “EXIT requested=7” trong stdout.


## 6. Tách nhiệm vụ runner và generator để code dễ bảo trì

Pattern tốt có ba phần trách nhiệm:

```text
Runner (xử lý nghiệp vụ)
    |
    +--> xác định outcome rõ ràng
    |
    v
JobOutcome (lưu kết quả cuối cùng)
    |
    +--> implement ExitCodeGenerator.getExitCode()
    |
    v
SpringApplication.exit(context)
    |
    +--> lấy code và đóng resources
    |
    v
System.exit(code) -> shell/CI
```

**Runner không nên tự gọi `System.exit(7)`** khi phát hiện record lỗi. Nếu làm vậy, nó có thể ngăn các runner tiếp theo, bỏ qua giai đoạn quyết định exit code hợp nhất hoặc ngắt shutdown theo cách không mong muốn. Đặc biệt nguy hiểm nếu task đã submit nhiều side effects rồi exit mà không đợi acknowledgment/cleanup.

Nếu chương trình có nhiều bước, một `JobOutcome` nên định nghĩa chính sách tổng hợp status:

- `0` chỉ khi **mọi bước bắt buộc đạt điều kiện thành công**.
- Mã cho input invalid khi không có phần nào của job nên chạy.
- Mã cho kết quả từng phần khi policy cho phép output đã tạo nhưng cần người vận hành rà soát.
- Mã cho thất bại không thể tiếp tục.
- Xác nhận mọi Future hoặc transaction bắt buộc đã hoàn tất trước khi công bố kết quả.
- Không chọn trạng thái thành công chỉ vì worker **đã được submit** vào executor.

Một mẫu state thread-safe có thể dùng `AtomicInteger`, nhưng **atomicity của một int chưa giải quyết race trong việc chọn trạng thái cuối**. Ví dụ hai worker cùng ghi 4 rồi 0 có thể khiến 0 ghi đè thất bại. Cần quy tắc ưu tiên/aggregation và finalization rõ ràng.

### 6.1. Có thể chỉ dùng lambda @Bean?

Có. Nếu code chỉ cần một exit code cố định, method bean ngắn nhất:

```java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
```

Nhưng với job thật, exit code thường phụ thuộc kết quả sau runner; do đó một bean stateful `JobOutcome implements ExitCodeGenerator`, cập nhật đúng lúc, dễ diễn đạt hơn một hằng số 42.

### 6.2. Có thể truyền generator trực tiếp cho SpringApplication.exit?

Có:

```java
int exitCode = SpringApplication.exit(
        context,
        () -> 8
);
System.exit(exitCode);
```

Đây là **đoạn minh họa**, cần biến `context` là `ApplicationContext` đang mở và import phù hợp. API nhận nhiều `ExitCodeGenerator...` từ caller, **ngoài** các generator beans được tìm từ context.

Nếu có nhiều generators, **đừng giả định lambda vừa truyền vào luôn “thắng”**: Spring chọn mã khác 0 đầu tiên sau ordering. Nên chỉ có một owner chịu trách nhiệm trạng thái cuối nếu không cần thật sự tổng hợp nhiều nguồn.

## 7. Khi có nhiều ExitCodeGenerator, mã nào được chọn?

Theo Spring Boot 3.3.13:

> **Mã exit khác 0 đầu tiên trong danh sách generator đã được sắp theo order sẽ được dùng.**

Spring hỗ trợ thứ tự bằng `org.springframework.core.Ordered` hoặc `org.springframework.core.annotation.Order`. **Số order càng nhỏ càng ưu tiên trước** theo quy ước ordering thông thường của Spring.

Ví dụ ý tưởng:

```java
@Order(10)
final class ValidationExitCode implements ExitCodeGenerator {
    @Override
    public int getExitCode() {
        return 2;
    }
}

@Order(20)
final class ReportingExitCode implements ExitCodeGenerator {
    @Override
    public int getExitCode() {
        return 7;
    }
}
```

Đây là **đoạn class minh họa**, chưa phải file độc lập; cần import annotation/interface và đăng ký **các object làm Spring bean** hoặc truyền đúng instance vào `SpringApplication.exit`. Khi cả hai nằm trong tập generator được xét với thứ tự này, mã khác 0 đầu tiên là **2**; Spring không cộng hai mã thành 9, cũng không mặc định chọn mã số học lớn nhất.

Nếu `ValidationExitCode.getExitCode()` trả `0` còn Reporting trả `7`, thì mã được chọn là **7**. `0` được hiểu là nguồn đó **không cung cấp mã lỗi nonzero** trong phép lựa chọn.

### 7.1. Ordered#getOrder() và @Order

Class có thể implement cả `ExitCodeGenerator` lẫn `Ordered`:

```java
final class ValidationExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

Đây cũng là snippet cần import Spring interfaces. Nếu order phải tính runtime hoặc truyền qua constructor, `Ordered#getOrder()` linh hoạt hơn; với order cố định, `@Order` trên class là dễ đọc.

Không đặt đồng thời `@Order(10)` và `getOrder()=50` trên cùng instance rồi hi vọng Spring cộng/trung bình hai giá trị; hãy chọn một nguồn ordering rõ.

### 7.2. Nếu hai generator có cùng order?

Không được xem thứ tự giữa hai generator bằng nhau là một business contract. Thứ tự đăng ký bean, scanner hoặc thay đổi Spring version có thể làm kết quả bất ngờ khi cả hai trả mã khác 0.

Để có tính xác định:

1. Dùng `@Order`/`Ordered` khác nhau và tài liệu hóa precedence;
2. Hoặc tốt hơn, **một generator tổng hợp** các điều kiện nghiệp vụ để trả một mã duy nhất.

### 7.3. ExitCodeGenerator không phải @Order của runner

Runner `@Order(5)` và ExitCodeGenerator `@Order(5)` thuộc **hai danh sách khác nhau**. Runner order ảnh hưởng **trình tự chạy tác vụ khi startup**; generator order ảnh hưởng **trình tự chọn mã exit khi SpringApplication.exit**. Không dùng cùng một con số để suy rằng runner này luôn điều khiển mã của generator kia.

## 8. Trường hợp runner ném exception: đường xử lý khác

Ví dụ chính cố ý **không ném exception**, vì mục đích là chứng minh bean ExitCodeGenerator được hỏi khi `SpringApplication.exit(context)` được gọi sau startup.

Nếu một `ApplicationRunner` ném exception ra ngoài:

```text
SpringApplication.run(...)
    |
    +--> refresh context thành công
    +--> ApplicationStartedEvent
    +--> runner throw
    |
    +--> startup failure handling
    +--> ApplicationFailedEvent (khi khả thi)
    +--> cleanup/close context (khi khả thi)
    +--> exception thoát khỏi SpringApplication.run(...)
    |
    X   main không nhận được context từ run(...)
    X   không đi theo đoạn SpringApplication.exit(context) bình thường
```

Do đó **không nên** chỉ đặt một bean `ExitCodeGenerator` để tin rằng nó chắc chắn sẽ được gọi như bình thường **sau khi run đã throw**. Khi `run` thất bại, đường tính mã lỗi nằm trong **startup failure handling**. Nếu muốn phân loại exception, Spring Boot còn hỗ trợ các cơ chế riêng.

### 8.1. Exception tự implement ExitCodeGenerator

Spring Boot cho phép chính exception implement `ExitCodeGenerator`. Ví dụ:

```java
final class InvalidInputException
        extends RuntimeException implements ExitCodeGenerator {

    InvalidInputException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

Đây là **đoạn class minh họa**, cần import `ExitCodeGenerator`. Theo tài liệu Spring Boot, khi một exception như vậy được encounter trong startup failure handling, Boot có thể lấy mã từ `getExitCode()` và dùng cho thông tin exit code của ứng dụng.

**Không suy diễn quá mức:** code trên **không tự tạo dòng `System.exit(2)` trong `main`**. Cách launcher/Boot xử lý mã lỗi cuối cùng khi exception được ném còn liên quan startup failure path và cách tiến trình được khởi chạy. Muốn xác nhận số shell thực nhận, phải chạy **một process thực** và đọc exit status, thay vì chỉ thấy method `getExitCode() == 2`.

### 8.2. ExitCodeExceptionMapper

Spring Boot cũng có `org.springframework.boot.ExitCodeExceptionMapper` với method:

```java
int getExitCode(Throwable exception);
```

Đây là chữ ký rút gọn của interface API. Mục đích là ánh xạ một exception thành mã lỗi, thay vì yêu cầu mọi exception domain tự implement `ExitCodeGenerator`.

Ví dụ snippet cấu hình:

```java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return throwable -> {
        Throwable cause = throwable;
        while (cause.getCause() != null) {
            cause = cause.getCause();
        }
        if (cause instanceof IllegalArgumentException) {
            return 2;
        }
        return 0;
    };
}
```

Đây là method **minh họa**, không phải file độc lập; cần import `ExitCodeExceptionMapper` và `@Bean`. Return `0` nghĩa là mapper này không xác định mã lỗi nonzero cho trường hợp ấy. Trong production, mapping phải theo **các exception nghiệp vụ cụ thể**, không biến mọi `RuntimeException` thành cùng một mã và làm mất phân loại.

### 8.3. ExitCodeEvent là gì?

Spring Boot có event **`org.springframework.boot.ExitCodeEvent`**, được phát khi framework xác định mã thoát từ `ExitCodeGenerator` trong những đường xử lý tương ứng. Event có method `getExitCode()`. Nó **không phải** `ContextClosedEvent` và cũng không phải thay thế `System.exit(...)`.

Listener chỉ nên dùng để quan sát/log/metric nhanh nếu cần; không dựa vào event này để dừng mọi worker hoặc bảo đảm transaction được rollback. Với lỗi rất sớm, bean listener có thể chưa tồn tại; đừng giả định mọi listener nhận đủ mọi startup failure.

### 8.4. Không bắt exception rồi return 0 giả

Đoạn phản ví dụ:

```java
try {
    loadRequiredData();
} catch (Exception ignored) {
    // Bỏ qua lỗi và để runner return thành công.
}
```

Đây là code minh họa không độc lập, nhưng sai trong bối cảnh dữ liệu bắt buộc. Nếu runner nuốt lỗi, `SpringApplication.run` có thể return bình thường; `JobOutcome` giữ mặc định 0; sau đó `SpringApplication.exit` trả 0 và CI đánh dấu job thành công **sai thực tế**.

Hai lựa chọn hợp lý:

- Xử lý lỗi nghiệp vụ có kiểm soát, **đặt outcome nonzero** rồi return nếu job đã kết thúc được đánh giá;
- Hoặc **ném exception** để Boot đi vào startup failure handling khi không thể tiếp tục an toàn.

Không vừa nuốt exception vừa trả code 0 chỉ để pipeline hiển thị xanh.


## 9. Mã thoát và graceful shutdown

Một vấn đề thiết kế quan trọng là **thời điểm đóng context**.

Với CLI mẫu:

```text
Runner đã hoàn tất và chốt outcome
    |
    +--> SpringApplication.exit(context)
    |      +--> tính mã ExitCodeGenerator
    |      +--> ContextClosedEvent
    |      +--> LifecycleProcessor dừng Lifecycle/SmartLifecycle
    |      +--> @PreDestroy / DisposableBean / destroy-method
    |      +--> close context
    |
    +--> System.exit(code)
```

`SpringApplication.exit` đóng context trước khi main gọi `System.exit`. Điều này tạo cơ hội dừng scheduler, executor, connection pool và những singleton resource theo lifecycle của Spring.

**Nhưng:** cleanup callbacks có thể thất bại hoặc timeout; `SpringApplication.exit` không tự rollback mọi database transaction đã commit, message đã gửi hay file đã tạo. Nếu job có side effects quan trọng, phải dùng transaction, idempotency, commit/ack và reconciliation đúng contract.

### 9.1. Tại sao không nên System.exit ngay trong ApplicationRunner?

```java
@Bean
ApplicationRunner unsafeRunner() {
    return args -> {
        performWork();
        System.exit(7); // Phản ví dụ: bỏ qua bước exit/cleanup có kiểm soát ở main.
    };
}
```

Đây là **đoạn phản ví dụ**, cần định nghĩa `performWork()`. Khi `System.exit` gọi trong runner, Spring không thể chạy phần còn lại của chuỗi startup và main không nhận được context theo đường hoàn tất để gọi `SpringApplication.exit`. Shutdown hook có thể giúp cleanup, nhưng vẫn không thay cho một chiến lược lifecycle rõ ràng và mã thoát được tính tập trung.

### 9.2. Tránh double close hoặc gọi exit khi context chưa sẵn sàng

- Nếu `SpringApplication.run` throw exception, **không có context được trả về** để bạn dùng như đường thành công.
- Nếu caller đã gọi `SpringApplication.exit(context)`, context đã được đóng; không cần gọi thêm `context.close()` cho cùng lifecycle thông thường.
- Nếu code dùng `try-with-resources` đóng context trước khi hỏi generator, sẽ khó gọi `SpringApplication.exit` đúng lúc vì generator beans có thể đã bị destroy.
- Nếu bean ExitCodeGenerator truy cập một resource đã shutdown, nó có thể không lấy được mã chính xác. Tính/chốt outcome **trước khi đóng**, để `getExitCode()` đơn giản và an toàn.
- Không tạo thread mới trong `@PreDestroy` rồi mong `SpringApplication.exit` tự chờ chúng hoàn tất.

### 9.3. CLI và web service có mục tiêu khác nhau

**CLI:** Mục tiêu là thực hiện việc hữu hạn, đóng context và exit với mã rõ.

**Web service:** Mục tiêu là tiếp tục nhận traffic sau startup. Dừng chủ yếu theo SIGTERM/context shutdown; không đặt `System.exit(SpringApplication.exit(...))` trực tiếp ngay sau `run(...)` như CLI, vì nó sẽ đóng ứng dụng sau khi vừa mở.

**Scheduled service:** Nếu job lặp dài hạn, không nên cho một tick scheduler tự quyết định exit của toàn bộ JVM. Cần thiết kế contract khi nào service dừng và cách orchestration xử lý status.

## 10. Cách shell, CI/CD, container và Kubernetes đọc mã

### 10.1. Bash trên Linux/macOS

`$?` chứa exit status của command gần nhất trong shell:

```bash
java -jar batch.jar --mode=fail
code=$?
echo "Java exit status: $code"
if [ "$code" -ne 0 ]; then
    echo "Batch failed"
    exit "$code"
fi
```

Đây là **script minh họa**; `batch.jar` phải là file có thật. Nếu muốn wrapper shell trả lại đúng code, phải **chủ động propagate nó**. Nếu wrapper luôn kết thúc bằng `echo "done"` rồi trả 0, CI có thể coi pipeline thành công dù Java đã trả 7.

Lưu ý với pipeline:

```bash
java -jar batch.jar | tee batch.log
```

Trong Bash, exit status của pipeline thường là status của command cuối cùng (`tee`), nên Java trả 7 vẫn có thể bị che. Hãy dùng `set -o pipefail` khi phù hợp, hoặc lấy `PIPESTATUS` ngay sau pipeline. Không coi log “Batch failed” là đủ; pipeline phải trả status đúng.

### 10.2. PowerShell

`$LASTEXITCODE` thường cho biết mã thoát của native process gần nhất:

```powershell
java -jar batch.jar --mode=fail
$code = $LASTEXITCODE
Write-Host "Java exit status: $code"
if ($code -ne 0) {
    exit $code
}
```

Lưu ý `exit $code` sẽ kết thúc PowerShell script/session theo nơi chạy; thích hợp khi script đó là entrypoint của CI. Nếu chỉ thử trong interactive shell và không muốn thoát shell, chỉ in code thay vì gọi `exit`.

### 10.3. Docker

Nếu dùng **exec-form entrypoint**:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là **Dockerfile minh họa**, cần image/tag khả dụng và file JAR đã build. Container process Java trả mã 0/2/4/7, môi trường container có thể quan sát đúng code.

Nếu dùng shell wrapper, hãy bảo đảm wrapper **propagate** mã Java. Một wrapper không dùng `exec` hoặc không `exit "$code"` có thể làm container thấy một mã khác. Tránh việc ghi log/cleanup shell xong vô tình trả 0.

### 10.4. Kubernetes Job

Kubernetes Job coi kết quả của Pod/container dựa vào process status và các policy của Job. Theo ngữ nghĩa thường gặp, exit code 0 được coi là hoàn thành thành công, còn nonzero có thể được xem là thất bại và kích hoạt retry/backoff tùy `backoffLimit`, `restartPolicy` và cấu hình.

**Không mặc định “exit 4 là cảnh báo nhưng Kubernetes sẽ đánh dấu Job thành công”**. Với nhiều bộ điều phối, **mọi mã khác 0 là failure** trừ khi có quy tắc phân loại riêng. Nếu `partial=4` là kết quả chấp nhận được trong một workflow, phải cấu hình chính sách orchestration/next step tương ứng hoặc cân nhắc contract trả 0 và lưu cảnh báo ở một kênh khác.

### 10.5. Tính di động của mã

Trên các hệ điều hành và shell Unix-like, exit status thường được trình bày trong dải `0–255`; số lớn hoặc số âm có thể được hệ thống biến đổi/truncation theo tầng gọi. Windows có cách biểu diễn process exit status khác. Để dễ mang qua shell, container và CI, nên chọn **mã nhỏ, không âm**, như 0, 2, 4, 7 trong thí nghiệm.

Đừng dùng exit code để nhồi mọi chi tiết lỗi: cần cả **log/structured event, job ID, số record lỗi và nguyên nhân hành động được**. Exit code là tín hiệu ngắn để caller quyết định, không phải toàn bộ báo cáo.

## 11. Phương pháp test và kiểm tra mã thoát

### 11.1. Unit test logic tạo exit code

Phần lớn business logic nên kiểm tra **độc lập với System.exit**. Có thể tách hàm ánh xạ trạng thái:

```java
static int toExitCode(String mode) {
    return switch (mode) {
        case "ok" -> 0;
        case "partial" -> 4;
        case "fail" -> 7;
        default -> 2;
    };
}
```

Đây là **method minh họa**, không thuộc chương trình chính nếu chưa thêm vào class. Unit test có thể gọi `toExitCode("fail")` và assert `7` mà không cần khởi tạo cả Spring container.

### 11.2. Integration test: hỏi generator trước System.exit

Có thể khởi động một context test hoặc CLI runner từ harness, lấy bean `ExitCodeGenerator` và assert `getExitCode()`, hoặc gọi `SpringApplication.exit(context)` rồi assert giá trị `int`. **Không gọi `System.exit(...)` trong cùng JVM của JUnit**, vì nó có thể kết thúc test runner.

Ví dụ ý tưởng:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(CliExitCodeApplication.class, "--mode=partial");

int code = SpringApplication.exit(context);

assertEquals(4, code);
```

Đây là **đoạn snippet test**, không phải file chạy độc lập; cần imports và testing framework, đồng thời quản lý profile/log phù hợp. Với mã chính có `System.exit` ở `main`, test gọi `SpringApplication.run` trực tiếp như snippet thay vì gọi `main`.

### 11.3. End-to-end test: chạy một process riêng

Muốn kiểm tra **mã OS thực nhận**, dùng `ProcessBuilder` hoặc shell khởi động `java -jar` như **một tiến trình con**, chờ nó kết thúc có timeout, rồi assert exit status.

Ví dụ Java 17 standalone kiểm tra file JAR đã build (chạy riêng trong thư mục project):

```java
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ExitCodeProcessCheck {
    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(
                System.getProperty("java.home"), "bin", "java").toString();

        Process process = new ProcessBuilder(
                javaBinary,
                "-jar",
                "build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar",
                "--mode=fail")
                .inheritIO()
                .start();

        boolean finished = process.waitFor(20, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IllegalStateException("CLI process timeout");
        }

        int code = process.exitValue();
        if (code != 7) {
            throw new AssertionError("Expected 7, got " + code);
        }

        System.out.println("CHECK PASS: exit=7");
    }
}
```

File ở trên có thể lưu dưới tên **`ExitCodeProcessCheck.java`** tại project root, sau đó chạy:

```bash
javac ExitCodeProcessCheck.java
java ExitCodeProcessCheck
```

Cần JDK 17+ và JAR demo đã được build. `inheritIO()` cho phép quan sát stdout của process con; `waitFor(20, TimeUnit.SECONDS)` tránh test treo vô hạn. Nếu dùng Windows, `Path.of(java.home,"bin","java")` cũng được JVM tìm theo executable resolution thông thường; trong môi trường có yêu cầu cụ thể, có thể chỉ định `java.exe` hoặc đường Java launcher rõ ràng.

Khi process con chạy đúng demo, bạn sẽ thấy các dòng Java CLI:

```text
RUN mode=fail code=7
CLEANUP @PreDestroy
EXIT requested=7
CHECK PASS: exit=7
```

Dòng cuối do process kiểm tra in. Cách này tách `System.exit(7)` khỏi JVM chạy test, nên tránh vô tình giết JUnit/IDE.

### 11.4. Đừng chỉ assert stdout

Một chương trình có thể in “EXIT requested=7” rồi bị một wrapper che lỗi hoặc bị kill trước khi process return status tương ứng. Trong acceptance test, cần quan sát **exitValue của process thật**. Ngược lại, thấy shell status 7 mà không thấy log nguyên nhân thì vận hành vẫn thiếu dữ liệu để xử lý; kiểm tra cả hai.

## 12. Những lỗi phổ biến

| Triệu chứng / khẳng định | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| “Đã implement ExitCodeGenerator thì shell tự nhận mã” | Generator chỉ được framework hỏi theo đường tương ứng | Gọi `SpringApplication.exit(context)` và `System.exit(code)` cho CLI |
| “`SpringApplication.exit` tự tương đương `System.exit`” | Method trả `int` và đóng context | Caller truyền mã cho process exit |
| “Chỉ in `status=7` là batch failed” | Log không thay exit status | Assert code thực tế |
| “`System.exit(7)` trong runner luôn tốt hơn” | Bỏ qua orchestration/cleanup có chủ đích | Chốt outcome, exit ở main |
| “`ApplicationReadyEvent` chứng minh exit code 0” | Ready đến sau runner, trước main tính status; business outcome độc lập | Theo dõi status job |
| “Runner throw mà main vẫn chắc nhận context để gọi exit” | `SpringApplication.run` có thể throw trước khi return | Xử lý startup failure/exception mapping riêng |
| “Nhiều generator thì Spring lấy mã lớn nhất” | Boot lấy mã khác 0 đầu tiên theo order | Đặt `@Order`/`Ordered` hoặc một tổng hợp |
| “Giá trị 0 của generator luôn thắng” | 0 là không có mã lỗi nonzero trong phép lựa chọn | Hiểu first nonzero |
| “Hai generator cùng order chạy cố định theo class name” | Thứ tự tie không phải contract đáng dựa vào | Đặt order khác hoặc hợp nhất |
| “@Order của runner điều khiển cả ExitCodeGenerator” | Hai extension points khác nhau | Tách runner order và generator ordering |
| “Async submit xong nghĩa job đủ điều kiện exit 0” | Future có thể chưa hoàn thành hoặc thất bại | Await và xác minh business ACK |
| “`SpringApplication.exit` không đóng bean” | API đóng context nếu có thể | Thiết kế `@PreDestroy`/Lifecycle đúng |
| “Đã có @PreDestroy nên rollback được DB” | Cleanup không thay transaction/compensation | Thiết kế consistency |
| “Chạy `gradlew bootRun` return 7 nghĩa Java trả 7” | Wrapper Gradle có thể đổi mã | Kiểm chứng `java -jar` trực tiếp |
| “PowerShell `$?` luôn giống mã process Java” | `$?` phụ thuộc command semantics/version | Đọc `$LASTEXITCODE` |
| “Bash pipeline qua tee giữ nguyên exit status Java” | Mặc định pipeline có thể lấy status command cuối | Dùng pipefail hoặc capture status |
| “Mã 4 là warning nên Kubernetes coi Job success” | Nhiều orchestrator coi mọi nonzero là lỗi | Chọn contract và chính sách rõ |
| “Có thể gọi System.exit trong unit test bình thường” | Nó có thể kết thúc JVM của test runner | Test logic riêng, process test riêng |
| “Mã thoát âm hoặc rất lớn được giữ nguyên ở mọi OS” | Exit status có giới hạn/chuẩn diễn giải khác nhau | Chọn dải nhỏ, không âm |

## 13. Checklist thiết kế CLI production

1. **Định nghĩa hợp đồng exit code**: 0 nghĩa gì, 2/4/7 đại diện gì, khi nào được retry hay cảnh báo?
2. **Phân biệt business status với exception**: input invalid có thể là kết quả được phân loại hoặc exception, nhưng phải nhất quán.
3. **Chọn owner**: một bean `ExitCodeGenerator` tổng hợp kết quả nếu có nhiều bước; chỉ dùng nhiều generator khi thực sự có lý do.
4. **Khởi tạo state an toàn**: 0 mặc định không được che việc chưa chạy job bắt buộc. Có thể dùng trạng thái `PENDING` và chỉ map về 0 sau khi xác minh completed.
5. **Runner trả về đúng lúc**: đợi Future/transaction/ack cần thiết; không coi submit vào queue là done.
6. **Không gọi System.exit sớm**: trả outcome rồi cho main exit theo đường có cleanup.
7. **Đóng context**: gọi `SpringApplication.exit(context)` cho đường thành công; biết rằng nó thực hiện destruction callbacks.
8. **Xử lý startup failure**: không giả định `run` luôn trả context; dùng exception mapping/hành vi launcher có kiểm chứng.
9. **Không ném lỗi trong getExitCode nếu tránh được**: generator nên đọc một kết quả đã chốt, đơn giản, deterministic và không cần I/O từ bean sắp bị destroy.
10. **Kiểm tra shell status thực**: dùng `$?`/`$LASTEXITCODE` hoặc `Process.exitValue()`, không chỉ log.
11. **Chú ý CI/container wrapper**: truyền nguyên exit status đúng cho entrypoint, không ghi đè bằng script.
12. **Đảm bảo dữ liệu không bị mất khi restart**: batch cần idempotent/checkpoint, đặc biệt khi có một phần tác vụ đã commit nhưng status nonzero.
13. **Log an toàn**: job ID, mode, số record xử lý/thất bại, nguyên nhân cụ thể; không ghi token/password/customer payload chỉ để debug.
14. **Thử đường fail thật**: invalid input, business partial, executor rejected, timeout, DB unavailable, SIGTERM và OOM/crash nếu môi trường cho phép.
15. **Tránh khởi chạy sai mô hình**: web service không nên dùng pattern CLI exit ngay sau `run`.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Bean `ExitCodeGenerator` trả 7. Nếu `main` chỉ gọi `SpringApplication.run(...)` rồi return, có bảo đảm shell nhận exit code 7?

**Đáp:** Không. Cần đường tính mã qua `SpringApplication.exit(context)` và truyền mã sang `System.exit(code)` hoặc cơ chế kết thúc process phù hợp.

**Câu 2.** `SpringApplication.exit(context)` làm gì?

**Đáp:** Thu thập generators, chọn exit code theo contract, đóng context nếu có thể và trả về `int`. Nó không tự thay caller gọi `System.exit`.

**Câu 3.** Có ba generator theo order 10, 20, 30 lần lượt trả 0, 4, 7. Mã nào được chọn?

**Đáp:** **4**, vì đó là mã khác 0 đầu tiên theo ordering.

**Câu 4.** Có cần throw exception chỉ để CLI trả mã 4 sau khi xử lý từng phần?

**Đáp:** Không. Runner có thể chốt outcome 4 rồi return; bean generator trả 4 khi exit.

**Câu 5.** Runner ném exception trước khi `SpringApplication.run` trả về. Main có context nào được trả để gọi `SpringApplication.exit(context)` theo đường thành công không?

**Đáp:** Không. Đây là startup failure path, cần exception mapping và kiểm thử launcher riêng.

**Câu 6.** Nếu `System.exit(7)` được gọi ngay trong runner, có thể có vấn đề gì?

**Đáp:** Bỏ qua đường chốt outcome và đóng context tập trung, cắt ngắn các runner khác; nên dùng logic điều phối ở main.

**Câu 7.** Tại sao `@PreDestroy` chạy trong ví dụ trước dòng EXIT?

**Đáp:** `SpringApplication.exit` đóng context trước khi return mã về main; singleton destruction callback được gọi trong close bình thường.

**Câu 8.** Chạy `java -jar ... --mode=fail` rồi `echo $?` ngay sau trong Bash cho kết quả nào?

**Đáp:** **7** với demo này, vì main gọi `System.exit(7)`.

**Câu 9.** Một job CLI có `@Async` future chưa xong nhưng generator trả 0. Có ổn không?

**Đáp:** Chỉ khi công việc là tùy chọn và hợp đồng cho phép. Nếu bắt buộc, status 0 là quá sớm; phải chờ kết quả hoặc dùng mô hình job khác.

**Câu 10.** `ExitCodeGenerator` cho CLI có phù hợp để dừng web server ngay sau startup không?

**Đáp:** Không theo pattern demo. Web server dài hạn nên sống tới khi nhận shutdown signal, không exit ngay sau `run`.

**Câu 11.** Vì sao mã 4 cần cân nhắc trong Kubernetes Job?

**Đáp:** Nhiều hệ điều phối coi mọi nonzero là thất bại và có thể retry; mã 4 chỉ có ý nghĩa “partial” nếu platform/workflow được cấu hình hiểu nó.

**Câu 12.** Unit test có nên trực tiếp gọi `CliExitCodeApplication.main` không?

**Đáp:** Không nếu main gọi `System.exit`, vì có thể kết thúc JVM kiểm thử. Dùng unit test logic hoặc process con.

**Câu 13.** Một shell wrapper chạy Java exit 7 nhưng dòng cuối wrapper trả 0. CI thấy gì?

**Đáp:** CI có thể thấy 0. Wrapper phải propagate code đúng; ví dụ lưu `$?` và `exit "$code"`.

**Câu 14.** Nếu nhiều generator cùng order và cùng trả nonzero, có nên dựa vào tên bean để chọn?

**Đáp:** Không. Dùng order khác nhau hoặc một generator tổng hợp để có contract deterministic.

## 15. Ghi nhớ và nguồn tham khảo

- **`ExitCodeGenerator`** là contract một method `int getExitCode()`. Bean implement nó có thể cung cấp mã khi `SpringApplication.exit(context)` chạy.
- **`SpringApplication.run`** khởi động và gọi runners; **`SpringApplication.exit`** tính mã/đóng context; **`System.exit`** đưa mã tới OS.
- **Mã 0** biểu diễn thành công theo hợp đồng CLI; **nonzero** biểu diễn kết quả khác thành công. Các mã số cụ thể phải được dự án tài liệu hóa.
- **Nhiều generators:** Spring Boot chọn **mã khác 0 đầu tiên** theo `Ordered`/`@Order`, không lấy mã lớn nhất.
- **Exception-based exit code** là một đường riêng; exception có thể implement `ExitCodeGenerator` hoặc được ánh xạ qua `ExitCodeExceptionMapper` trong startup failure handling.
- **Không gọi System.exit trong runner** khi có thể thiết kế main thu thập outcome/cleanup rõ ràng.
- **Kiểm thử process thật** bằng `java -jar` và exit status; cẩn thận wrapper, pipeline và tool launcher.
- **Không đánh đồng job submitted với completed**, context closed với JVM exited, hay exit code với durable rollback.

Nguồn chính thức cho Spring Boot 3.3.13:

1. [Spring Boot 3.3 — SpringApplication: Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), ví dụ `System.exit(SpringApplication.exit(...))`, exception và nhiều generators.
2. [Spring Boot 3.3.13 API — SpringApplication.exit](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html), collect beans, chọn first nonzero và close context.
3. [Spring Boot 3.3.13 API — ExitCodeGenerator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html), chữ ký `getExitCode()`.
4. [Spring Boot 3.3.13 API — ExitCodeExceptionMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html), ánh xạ Throwable sang exit code.
5. [Spring Boot 3.3.13 API — ExitCodeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html), event khi mã thoát được xác định.
6. [Spring Boot 3.3 — ApplicationRunner and CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), các bước thực thi trước khi run trả về.
7. [Spring Framework 6.1 — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), nguyên tắc cleanup singleton khi context đóng.

**Kết luận:** `ExitCodeGenerator` giúp ứng dụng dòng lệnh **diễn đạt outcome dưới dạng mã**. Muốn hệ điều hành nhận đúng mã, hãy chốt kết quả một cách xác định, dùng `SpringApplication.exit(context)` để đọc mã và đóng Spring context, rồi để `System.exit(code)` chuyển trạng thái đó tới tiến trình bên ngoài. Đó là sự khác biệt giữa “một bean biết mã lỗi” và “CLI thực sự báo đúng thành công/thất bại cho hệ thống gọi”.
