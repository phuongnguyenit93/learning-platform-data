# Trả mã thoát sau khi hoàn tất dọn dẹp tài nguyên — Spring Boot 3.3

## 1. Mục tiêu

Ứng dụng Java dùng như một command-line tool, batch processor hoặc một container worker cần trả về **mã thoát của tiến trình** để shell, CI/CD, scheduler, Docker hoặc hệ thống điều phối biết công việc kết thúc như thế nào.

Trong Spring Boot, một lỗi phổ biến là gọi `System.exit(...)` quá sớm: tiến trình bắt đầu kết thúc trước khi các tác vụ còn chạy, luồng ghi file, connection pool, consumer hoặc bean kịp hoàn tất quy trình cleanup. Lỗi ngược lại là dọn dẹp xong nhưng **không chuyển trạng thái nghiệp vụ thành process exit code**, khiến script gọi bên ngoài tưởng thành công.

Bài này giải quyết chính xác hai yêu cầu:

1. **Trả mã thoát đúng kết quả** (`0` thành công, khác `0` thất bại theo hợp đồng ứng dụng).
2. **Thực hiện dọn dẹp tài nguyên có kiểm soát trước khi tiến trình kết thúc**, và xử lý trường hợp chính việc cleanup có lỗi.

Sau bài học bạn có thể:

- Hiểu khác biệt giữa `SpringApplication.exit(context)`, `ConfigurableApplicationContext.close()` và `System.exit(code)`.
- Dùng `ExitCodeGenerator` để báo mã của job, kể cả khi job thất bại theo quy tắc nghiệp vụ nhưng startup vẫn thành công.
- Biết **thời điểm Spring Boot 3.3.13 tính exit code** so với `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)` và `@PreDestroy`.
- Tổ chức cleanup các resources được quản lý bởi Spring, đồng thời đảm bảo async jobs đã dừng trước khi resource đóng.
- Viết một ứng dụng non-web Java 21 / Spring Boot 3.3.13 chạy được từ Maven, có nhánh exit code `0` và `17`, JUnit và lệnh kiểm tra mã thoát trên Bash, PowerShell và CMD.
- Phân biệt lệnh thoát có chủ đích với SIGTERM, force kill, JVM crash và startup failure.

**Ý chính:** mã thoát của một tiến trình chỉ trở thành thông tin cho hệ điều hành khi **JVM thật sự kết thúc**. `SpringApplication.exit(context)` hỗ trợ tính mã và đóng Spring context; **chính nó không gọi `System.exit`**, cũng không đảm bảo mọi tác vụ nền đã xong nếu bạn thiết kế callback shutdown sai.

## 2. Mã thoát là gì và ai đọc nó?

Ở mức hệ điều hành, một tiến trình báo một mã số khi kết thúc. Trên các CLI thông thường, ta quy ước:

| Mã | Diễn giải do ứng dụng quy định | Ví dụ |
| --- | --- | --- |
| `0` | Thành công | Batch xử lý xong, cleanup thành công |
| `2` | Input/usage không hợp lệ | Thiếu option bắt buộc |
| `17` | Lỗi nghiệp vụ trong demo | File nhập có dữ liệu không đạt quy tắc |
| `74` | Lỗi I/O/cleanup trong demo | Flush/close/xóa tệp tạm thất bại |
| Các mã khác `0` | Thất bại theo hợp đồng riêng | Scheduler quyết định retry/alert |

**Các mã `2`, `17`, `74` ở đây là ví dụ chính sách ứng dụng**, không phải chuẩn bắt buộc do Spring Boot định nghĩa. Trong production, cần công bố hợp đồng exit code có tài liệu và dùng nhất quán.

Để đọc mã:

```bash
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo $?
```

Đây là Bash/zsh trên Unix-like; chạy `echo $?` **ngay sau** lệnh Java cần kiểm tra vì bất kỳ lệnh tiếp theo nào cũng có thể thay `$?`.

Trong PowerShell:

```powershell
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
```

Trong CMD:

```bat
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo %ERRORLEVEL%
```

Nếu Java process kết thúc bằng `System.exit(17)` trong điều kiện thông thường, các shell trên sẽ nhận trạng thái thất bại theo chính sách của nền tảng. Trên Unix, chỉ một phần độ rộng số nguyên có thể được phản ánh qua exit status truyền thống; nên chọn các mã nhỏ, dương và dễ giám sát. Đừng trộn mã do ứng dụng chủ động trả với số mà shell/OS gán khi process bị signal-killed.

### 2.1. `main` trả về khác với process exit

Trong Java, `public static void main(String[] args)` có return type `void`. Nếu `main` trả về và **không còn non-daemon threads giữ JVM sống**, tiến trình thường thoát với mã `0`, trừ khi có failure/handler thay đổi điều kiện này.

Một batch có thể xử lý lỗi nghiệp vụ nhưng không ném exception hoặc gọi exit đúng cách:

```java
public static void main(String[] args) {
    boolean success = processBatch();
    System.out.println("success=" + success);
}
```

Đây là **mẫu minh họa không độc lập**: `processBatch()` chưa được định nghĩa. Khi trả về bình thường, shell vẫn có thể thấy mã `0` dù `success=false`. Muốn caller biết kết quả, cần trả kết quả vào quy trình quyết định exit code.

### 2.2. `System.exit(int)` làm gì?

`System.exit(code)` yêu cầu JVM bắt đầu trình tự shutdown với mã tương ứng. Nếu JVM shutdown hooks được phép chạy, chúng có thể được thực thi. Tuy nhiên:

- `System.exit` **không tự biết** task nào cần drain, resource nào cần flush.
- Nó không tự đợi một async task vô hạn nếu task không nằm trong shutdown protocol.
- Nó không phù hợp để gọi trực tiếp từ `@PreDestroy` hoặc bên trong shutdown hook.
- Nó có thể làm kết thúc toàn JVM, ảnh hưởng những contexts hoặc components khác trong process.

Dùng nó ở **ranh giới ngoài cùng** của một ứng dụng CLI đã chủ động hoàn tất công việc, không rải rác trong controllers, repositories, listeners và runners.

## 3. Ba API rất dễ nhầm

| API | Tác dụng chính | Có đóng Spring context? | Có trực tiếp kết thúc JVM với mã đã chọn? |
| --- | --- | --- | --- |
| `context.close()` | Dừng lifecycle và destroy Spring beans | **Có** | **Không** |
| `SpringApplication.exit(context)` | Tính mã từ `ExitCodeGenerator`, đóng context nếu có thể | **Có** | **Không** |
| `System.exit(code)` | Bắt đầu JVM shutdown và truyền exit status | Không phải lời gọi đóng context trực tiếp | **Có** |

### 3.1. `ConfigurableApplicationContext.close()`

```java
ConfigurableApplicationContext context = ...;
context.close();
```

Đây là **đoạn minh họa**, cần một context đã khởi động. Trong Spring Framework, close là thao tác đồng bộ với phần shutdown mà container thực sự chờ: phát `ContextClosedEvent`, gọi `LifecycleProcessor.onClose()` và destroy singleton beans.

Tuy nhiên, nó không bảo đảm **mọi công việc mà bean từng submit** đã kết thúc nếu callback/worker được thiết kế sai. Nó cũng không đặt một process exit code theo business result.

### 3.2. `SpringApplication.exit(context)`

```java
int code = SpringApplication.exit(context);
```

API Spring Boot 3.3.13 trả `int`, lấy mã từ các `ExitCodeGenerator` chỉ định và các beans triển khai interface ấy. Nó sẽ cố đóng `ApplicationContext` nếu context hỗ trợ close. **Sau khi trả về**, context thường đã được đóng theo cơ chế của Spring, nhưng JVM vẫn có thể còn tồn tại nếu các non-daemon threads khác còn chạy.

Có thể truyền thêm generator:

```java
int code = SpringApplication.exit(context, () -> 17);
```

Nếu application context có `ExitCodeGenerator` beans, tất cả các generator liên quan được xem xét theo order. Generator truyền vào không mặc nhiên thắng mọi bean khác; quy tắc là **mã khác `0` đầu tiên trong thứ tự generator**, xem mục 5.

### 3.3. `System.exit(SpringApplication.exit(context))`

```java
System.exit(SpringApplication.exit(context));
```

Java phải **đánh giá argument của `System.exit` trước**, nên `SpringApplication.exit(context)` được gọi và trả mã trước khi JVM nhận yêu cầu thoát. Câu lệnh này là **mẫu chính thức** được Spring Boot tài liệu hóa cho ứng dụng command-line.

Bạn cũng có thể tách thành hai dòng để log, kiểm thử và xử lý policy rõ hơn:

```java
int code = SpringApplication.exit(context);
System.exit(code);
```

**Đừng đảo ngược** thành `System.exit(code); context.close();` vì câu lệnh `context.close()` sau `System.exit` thông thường không còn cơ hội được thực thi.

## 4. Một chi tiết quan trọng trong Spring Boot 3.3.13: exit code tính trước khi close

Kiểm tra implementation của `SpringApplication.exit(...)` ở Spring Boot 3.3.13 cho thấy trình tự về mặt khái niệm:

```text
SpringApplication.exit(context, generators...)
   |
   +-- Tìm các beans ExitCodeGenerator trong context
   +-- Kết hợp với generators do caller cung cấp
   +-- Gọi getExitCode() theo thứ tự
   +-- Nếu mã khác 0, phát ExitCodeEvent
   |
   +-- finally: đóng ApplicationContext (nếu closable)
   |      +-- ContextClosedEvent
   |      +-- SmartLifecycle.stop(Runnable) / Lifecycle stop
   |      +-- @PreDestroy / bean destroy
   |
   +-- Xử lý một số exception trong quá trình exit
   +-- Trả int exit code cho caller
```

**Kết luận cực kỳ quan trọng:**

- `SpringApplication.exit(...)` **tính mã trước khi `context.close()`**; mã vẫn chỉ được **trả về** sau khi lệnh close đã hoàn tất hoặc lỗi close đã được xử lý.
- Nếu bạn chỉ phát hiện lỗi flush trong `@PreDestroy`, một `ExitCodeGenerator.getExitCode()` đã được gọi **trước đó** nên **không thể tự “đọc lại” kết quả mới**.
- Khi lỗi đóng context được báo bằng exception, trong implementation Boot 3.3.13, `SpringApplication.exit` log lỗi và dùng mã `1` nếu chưa có mã lỗi khác; nếu đã tính một mã khác `0`, mã đó có thể được giữ nguyên. Không nên dùng đường exception này làm cơ chế báo mã cleanup có chủ đích.
- Có những cleanup errors bị framework log nhưng không propagate ra `SpringApplication.exit` (tùy callback). Khi đó không được mặc định mã `0` sẽ tự đổi thành non-zero.
- Vì vậy **nếu mã thoát phải phản ánh trạng thái cleanup**, hãy chạy và xác minh phần cleanup thiết yếu **trước khi gọi `SpringApplication.exit`**, sau đó generator đọc kết quả đã ổn định. Việc đóng bean còn lại sau đó vẫn cần lifecycle callbacks đúng.
- Nếu cleanup cần thực hiện hoàn toàn trong `@PreDestroy` và mã lỗi ấy bắt buộc phản ánh trong exit status, bạn cần một orchestration rõ ràng ở bên ngoài context hoặc một cách dọn dẹp/trả kết quả **trước bước close**, thay vì kỳ vọng generator được chạy lần hai.

Đây là điểm khác với suy luận dễ mắc: “`SpringApplication.exit` đóng context trước rồi mới hỏi `ExitCodeGenerator`”. **Suy luận đó không đúng với implementation 3.3.13.**

### 4.1. Lỗi nghiệp vụ khác lỗi cleanup

Một job có thể có nhiều kết quả:

```text
BUSINESS_OK + CLEANUP_OK   -> exit 0
BUSINESS_FAIL + CLEANUP_OK -> exit 17
BUSINESS_OK + CLEANUP_FAIL -> exit 74
BUSINESS_FAIL + CLEANUP_FAIL -> exit code theo precedence đã quy định
```

Chọn policy có chủ đích. Ví dụ bài này đặt **cleanup failure (74) cao hơn business failure (17)** để hệ thống vận hành biết dữ liệu/tài nguyên có thể chưa được xử lý an toàn. Trong sản phẩm thực tế, nên báo đồng thời business failure và cleanup failure qua logs/metrics, ngay cả khi chỉ có một process exit status.

### 4.2. ExitCodeEvent

Khi kết quả từ các generator khác `0`, Spring Boot có thể phát `ExitCodeEvent` **trước khi đóng context**. Event có `getExitCode()`. Listener có thể log/metric mã dự kiến, nhưng **không nên** dựa vào listener này để quyết định lại mã hoặc bắt đầu công việc async mới ngay trước shutdown.

Ví dụ minh họa:

```java
@Component
class ExitObserver {
    @EventListener
    void onExitCode(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

Đoạn này cần imports `@Component`, `@EventListener`, `ExitCodeEvent` và phải nằm trong Spring context. Bản demo đầy đủ ở mục 7 cũng có listener tương ứng.

## 5. ExitCodeGenerator và việc chọn mã

`org.springframework.boot.ExitCodeGenerator` là một functional interface:

```java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

Đây là **chữ ký minh họa**, không phải interface cần tự khai báo. Có thể trả mã qua:

1. Một bean implement `ExitCodeGenerator`.
2. Một lambda hoặc object truyền trực tiếp vào `SpringApplication.exit(context, ...)`.
3. Một exception implement `ExitCodeGenerator` khi Spring Boot xử lý startup exception thích hợp.

Ví dụ bean:

```java
@Component
class ImportResult implements ExitCodeGenerator {
    private volatile int result;

    public void markBusinessFailure() {
        result = 17;
    }

    @Override
    public int getExitCode() {
        return result;
    }
}
```

**Mã minh họa**, cần imports `@Component`, `ExitCodeGenerator`. Nó cho phép service/runner đặt trạng thái, rồi Spring Boot lấy mã ở cuối. `volatile` chỉ hỗ trợ visibility của một int; với nhiều threads và nhiều nguồn lỗi cần state machine/atomic policy để tránh race.

### 5.1. Nhiều generators

Nếu có nhiều generator, Spring Boot 3.3 lấy **mã khác `0` đầu tiên** theo thứ tự được xác định bởi `Ordered` hoặc `@Order`. Không có quy tắc mặc định “mã âm ưu tiên hơn dương”, “mã lớn nhất thắng” hay “generator gọi sau cùng thắng”.

Khi thiết kế hệ thống có nhiều failure types, tốt hơn là có **một result aggregator** chọn mã cuối theo precedence nghiệp vụ, tránh để việc sắp bean hoặc thay đổi order quyết định một cách khó thấy.

### 5.2. Cần báo lỗi từ startup exception

Nếu một `ApplicationRunner` ném exception không bắt và làm `SpringApplication.run` thất bại, **bạn có thể không nhận được context đã startup thành công để gọi `SpringApplication.exit(context)` từ main**. Spring Boot có cơ chế gán exit code cho failure exceptions, gồm `ExitCodeGenerator` hoặc `ExitCodeExceptionMapper` phù hợp. Hãy thiết kế riêng đường startup failure, không lấy demo business-failure-in-result-state ở mục 7 làm thay thế cho mọi exception.

### 5.3. Đừng gọi getExitCode quá sớm

Nếu job vẫn đang chạy async, generator đọc state có thể thấy `0` trước khi task thất bại. Cần một completion protocol có timeout, cancellation và state được publish an toàn giữa các threads, sau đó mới gọi `SpringApplication.exit`.

Không nên để generator thực hiện I/O dài, đóng resource hoặc khởi chạy công việc mới. `getExitCode()` nên nhanh, ổn định và chỉ đọc kết quả đã xác lập.

## 6. Thiết kế quy trình đúng: complete → cleanup → calculate → close → exit

Một workflow CLI đáng tin:

```text
SpringApplication.run(args)
   |
   +-- Spring tạo context
   +-- ApplicationRunner xử lý business job
   |
   +-- Đảm bảo business work đã đạt trạng thái cuối
   |     +-- Không nhận job mới
   |     +-- Chờ async Future/ack nếu có
   |
   +-- Cleanup chủ động có kết quả
   |     +-- Flush file/buffer
   |     +-- Close resource owned by job
   |     +-- Checkpoint và kiểm tra lỗi cleanup
   |     +-- Ghi kết quả cuối vào ExitCodeGenerator bean
   |
   +-- SpringApplication.exit(context)
   |     +-- Tính mã từ generators
   |     +-- Đóng context
   |           +-- Stop SmartLifecycle beans
   |           +-- @PreDestroy những bean còn cần cleanup
   |
   +-- Nhận mã đã trả về
   +-- System.exit(code)
   +-- Shell/scheduler đọc mã
```

**Quan hệ phụ thuộc:** những tài nguyên phải còn mở cho bước drain thì không được đóng trước khi consumer dừng. Không được coi `@PreDestroy` của một resource là công cụ tự động đợi mọi task từng sử dụng nó.

### 6.1. Vì sao không đặt System.exit trong runner?

Anti-pattern:

```java
@Component
class DangerousRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        launchBackgroundJobs();
        System.exit(0); // Chưa đợi kết quả hoặc cleanup.
    }
}
```

**Đây là code minh họa không độc lập**. JVM shutdown hooks có thể được gọi, nhưng một task đã submit không mặc nhiên hoàn tất; caller cũng không biết các jobs đã thành công chưa. Với một batch chạy một lần, nên để runner báo kết quả, main hoặc coordinator chờ completion, cleanup rồi mới quyết định exit.

### 6.2. Vì sao không gọi System.exit trong @PreDestroy?

`@PreDestroy` chạy **trong khi context đang được đóng**. Gọi `System.exit` ở đây có thể tạo luồng shutdown lồng nhau, giữ khóa hoặc cắt ngang các destroy callbacks khác. Dùng callback để giải phóng tài nguyên; đưa hành động kết thúc JVM về outermost main/process supervisor.

### 6.3. Vì sao không chỉ return khỏi main rồi mặc định được mã lỗi?

Nếu main trả về bình thường mà không báo lỗi, Java process thường thoát với mã `0` khi không còn non-daemon threads. Việc một service đã log “IMPORT FAILED” không tự biến mã OS thành nonzero. Đặc biệt với CI pipelines, điều này dễ tạo **false-green build**.

## 7. Ví dụ chạy được — Java 21 và Spring Boot 3.3.13

Demo non-web minh họa:

- `FileBatch` triển khai `ApplicationRunner` để mô phỏng job, tạo file tạm và ghi một dòng dữ liệu.
- `FileBatch` đồng thời implement `ExitCodeGenerator`, giữ mã `0` hoặc `17` theo option `--business-fail`; nếu flush/close/xóa file tạm lỗi, báo mã `74`.
- `finishAndCleanup()` thực hiện cleanup **trước khi generator được đọc**, ghi nhận kết quả cuối.
- `@PreDestroy` là fallback để cleanup khi context bị đóng ở đường khác; với đường chuẩn, nó chỉ xác nhận đã cleanup.
- `ExitObserver` quan sát `ExitCodeEvent` chỉ khi exit code khác `0`.
- `CleanupExitApplication` gọi `SpringApplication.exit(context)` rồi **mới gọi `System.exit(code)`**.
- Test JUnit tự chạy/đóng context và kiểm tra các mã, không gọi `System.exit` làm chết test runner.

Demo cố ý không có HTTP server, vì batch CLI có điểm hoàn tất rõ ràng. Không cần database, message broker hay tài khoản bên ngoài.

### 7.1. Cấu trúc dự án

```text
cleanup-exit-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/exit/
    │   ├── CleanupExitApplication.java
    │   ├── FileBatch.java
    │   └── ExitObserver.java
    └── test/java/com/example/exit/
        └── CleanupExitTest.java
```

### 7.2. Maven pom.xml

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
    <artifactId>cleanup-exit-demo</artifactId>
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
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 có minimum Java 17 và tương thích Java 21. `spring-boot-starter` đủ để tạo non-web context và runners; test starter chứa JUnit Jupiter.

### 7.3. Lớp main

Tệp `src/main/java/com/example/exit/CleanupExitApplication.java`:

```java
package com.example.exit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CleanupExitApplication {

    public static void main(String[] args) {
        int code = runAndClose(args);
        System.exit(code);
    }

    public static int runAndClose(String... args) {
        SpringApplication application =
                new SpringApplication(CleanupExitApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        try {
            FileBatch job = context.getBean(FileBatch.class);

            // Cleanup có báo kết quả trước khi getExitCode được gọi.
            job.finishAndCleanup();

            // Tính exit code và đóng Spring context.
            int code = SpringApplication.exit(context);
            System.out.println("MAIN context closed, code=" + code);
            return code;
        }
        finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

**Điểm then chốt:**

- `SpringApplication.run` gọi `ApplicationRunner` trong lúc bootstrap.
- `FileBatch.finishAndCleanup()` đồng bộ hoàn tất việc flush/close/delete và cập nhật trạng thái.
- `SpringApplication.exit` đọc `ExitCodeGenerator`, phát event khi nonzero và đóng context.
- `System.exit` **chỉ xuất hiện trong `main`**, không ở service/runner/`@PreDestroy`.
- `runAndClose` **có thể được gọi trực tiếp từ JUnit mà không tắt JVM test**.
- `finally` là đường dự phòng đóng context nếu có exception trước hoặc trong quá trình exit. Nó không thay thế policy xử lý exception ở startup trước khi `application.run` trả context.

Với production code, cần quy định cả đường lỗi startup và lỗi runtime không mong đợi: nếu `run()` ném exception, Boot có cơ chế tự close context và xử lý exception exit; đừng gọi mù `SpringApplication.exit(null)` hoặc cho rằng phương thức ví dụ luôn nhận được context.

### 7.4. FileBatch.java — ghi kết quả nghiệp vụ và cleanup

Tệp `src/main/java/com/example/exit/FileBatch.java`:

```java
package com.example.exit;

import java.io.BufferedWriter;
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
public class FileBatch implements ApplicationRunner, ExitCodeGenerator {

    private BufferedWriter writer;
    private Path file;
    private int exitCode;
    private boolean cleaned;

    @Override
    public synchronized void run(ApplicationArguments args) throws Exception {
        file = Files.createTempFile("cleanup-exit-", ".txt");
        writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8);
        writer.write("example-batch-entry");
        writer.newLine();

        // Ví dụ thất bại nghiệp vụ vẫn được ghi nhận thành result,
        // thay vì System.exit ngay bên trong runner.
        exitCode = args.containsOption("business-fail") ? 17 : 0;
        System.out.println("JOB desiredCode=" + exitCode);
    }

    public synchronized void finishAndCleanup() {
        if (cleaned) {
            return;
        }

        IOException failure = null;

        if (writer != null) {
            try {
                writer.flush();
            }
            catch (IOException ex) {
                failure = ex;
            }

            try {
                writer.close();
            }
            catch (IOException ex) {
                if (failure == null) {
                    failure = ex;
                }
                else {
                    failure.addSuppressed(ex);
                }
            }
            writer = null;
        }

        if (file != null) {
            try {
                Files.deleteIfExists(file);
            }
            catch (IOException ex) {
                if (failure == null) {
                    failure = ex;
                }
                else {
                    failure.addSuppressed(ex);
                }
            }
        }

        cleaned = true;

        if (failure == null) {
            System.out.println("CLEANUP completed");
        }
        else {
            // Demo ưu tiên cleanup failure so với business failure.
            exitCode = 74;
            System.err.println("CLEANUP failed: "
                    + failure.getClass().getSimpleName());
        }
    }

    public synchronized boolean isCleaned() {
        return cleaned;
    }

    @Override
    public synchronized int getExitCode() {
        return exitCode;
    }

    @PreDestroy
    void destroy() {
        // Nếu có đường close context khác, thử cleanup best-effort.
        finishAndCleanup();
        System.out.println("BEAN preDestroy");
    }
}
```

Trong demo, `FileBatch` tạo một tệp tạm, ghi dữ liệu, flush/close writer rồi xóa tệp khi đã sử dụng xong. Mục đích là minh họa resource lifecycle, không phải cách ghi một báo cáo business thực cần tồn tại sau process exit.

**Không xóa dữ liệu nghiệp vụ thật** sau khi xử lý: việc xóa tệp tạm ở demo chỉ áp dụng cho tài nguyên do job tạo với vai trò temporary output. Với durable output, phải flush/fsync/atomic rename theo yêu cầu bền vững riêng.

`finishAndCleanup()` được `synchronized` để tránh hai callers cùng đóng writer trong demo và `cleaned` tránh double cleanup. Ở production, cần xem thêm concurrency với các tác vụ có thể vẫn ghi writer: chỉ synchronized method ở owner **không đủ** nếu background threads không tham gia cùng admission/drain protocol.

**Chú ý về lỗi:** method thử flush, close và xóa tệp một cách best-effort, gom một lỗi đầu tiên và giữ các lỗi sau dưới dạng suppressed. Nó đặt `74` để caller không báo thành công. Trong production, nên log cả nguyên nhân với stack trace, vị trí file an toàn, retry policy và đảm bảo không che giấu dữ liệu cần khôi phục. Việc đánh dấu `cleaned=true` ở đây nghĩa là **đã thực hiện một lượt cleanup và ghi kết quả**, không hứa tài nguyên đã giải phóng trọn vẹn khi có lỗi.

### 7.5. ExitObserver.java

Tệp `src/main/java/com/example/exit/ExitObserver.java`:

```java
package com.example.exit;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitObserver {

    @EventListener
    public void onExit(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

`ExitCodeEvent` được phát khi `SpringApplication.exit` xác định một mã khác `0`. Nó được phát **trước bước đóng context**. Listener này chỉ log; không submit thêm job hoặc thay đổi business status ở phút cuối.

### 7.6. Build và chạy

Cài Java 21 và Maven. Trong thư mục `cleanup-exit-demo`:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo $?
```

Ở Bash/zsh, các dòng **do code demo chủ động in** theo thứ tự trong nhánh thành công:

```text
JOB desiredCode=0
CLEANUP completed
BEAN preDestroy
MAIN context closed, code=0
```

Sau khi process kết thúc, `echo $?` in:

```text
0
```

Spring Boot còn in banner/log startup khác; các khối trên không phải toàn bộ stdout. Vì `code=0`, `ExitCodeEvent` không được phát từ lời gọi exit này, nên không có dòng `EXIT event` trong nhánh thành công.

### 7.7. Chạy nhánh thất bại nghiệp vụ

```bash
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
echo $?
```

Các dòng do code in sẽ là:

```text
JOB desiredCode=17
CLEANUP completed
EXIT event=17
BEAN preDestroy
MAIN context closed, code=17
```

Ngay sau lệnh Java, `echo $?` in:

```text
17
```

`EXIT event=17` xảy ra trước `BEAN preDestroy`, minh họa chính xác: **generator quyết định exit code trước khi context cleanup/destroy**. Cleanup chủ động đã chạy trước nên mã có thể phản ánh lỗi của bước ấy.

### 7.8. Vì sao không ép cleanup failure bằng quyền file trong demo?

Thử gây lỗi I/O thật qua quyền file hoặc ép filesystem full có thể làm test lệ thuộc OS/container và gây tác dụng phụ. Trong production code, hãy thêm một abstraction có thể mock cho file operations hoặc một `CleanupOutcome` rõ ràng rồi unit test nhánh failure bằng injected fake, thay vì thao tác trên filesystem thật để mô phỏng lỗi.

Không sửa demo thành `throw new IOException` ngay trong `@PreDestroy` rồi kỳ vọng `ExitCodeGenerator` thấy lỗi: thời điểm generator đã qua và nhiều destroy exceptions có thể chỉ được log.

## 8. JUnit: xác minh code trả về mà không dừng JVM test

Tệp `src/test/java/com/example/exit/CleanupExitTest.java`:

```java
package com.example.exit;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanupExitTest {

    @Test
    void successCodeIsReturnedAfterCleanupAndContextClose() {
        verifyExit(0);
    }

    @Test
    void businessFailurePreservesItsCodeAfterCleanup() {
        verifyExit(17, "--business-fail");
    }

    private void verifyExit(int expectedCode, String... args) {
        SpringApplication app =
                new SpringApplication(CleanupExitApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        try {
            FileBatch job = context.getBean(FileBatch.class);
            job.finishAndCleanup();

            assertTrue(job.isCleaned());
            assertEquals(expectedCode, job.getExitCode());

            int returnedCode = SpringApplication.exit(context);

            assertEquals(expectedCode, returnedCode);
            assertFalse(context.isActive());
        }
        finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng class trên có **2 tests thành công**, không cần gọi `System.exit()` trong JUnit. `SpringApplication` tạo context độc lập cho từng test, gọi `ApplicationRunner`, còn `SpringApplication.exit` tính mã và đóng context.

Các assertions kiểm tra:

1. Job đã chạy và cleanup chủ động đã được gọi.
2. `ExitCodeGenerator` giữ đúng business code sau cleanup.
3. `SpringApplication.exit` trả đúng mã.
4. Context đã được đóng.

Test này **không chứng minh mã OS của subprocess** vì không spawn JVM khác. Muốn test OS exit end-to-end, chạy `java -jar` như một subprocess hoặc dùng CLI script/CI job rồi đọc exit status. Không gọi thẳng `CleanupExitApplication.main(...)` trong test vì `System.exit` có thể kết thúc toàn bộ JUnit process.

### 8.1. Kiểm tra mã trên Windows

PowerShell:

```powershell
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
$LASTEXITCODE
```

CMD:

```bat
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
echo %ERRORLEVEL%
```

Kỳ vọng mã `17` trong nhánh có option. Với nhánh bình thường, mã `0`.

### 8.2. Kiểm thử nhiều generators

Một test bổ sung có thể thêm hai `ExitCodeGenerator` lambdas:

```java
int code = SpringApplication.exit(context, () -> 0, () -> 23);
```

**Đây là đoạn minh họa**, không nên đặt sau khi đã `SpringApplication.exit(context)` ở test chính, vì context đã đóng. Với nhiều generator, xác nhận thứ tự/sorting theo Spring Boot, không suy luận “generator cuối cùng thắng”. Nếu cần hợp đồng precedence chặt chẽ, dùng một aggregator trả một mã duy nhất.

## 9. Khi cleanup là bất đồng bộ

Trong các ứng dụng thực tế, cleanup có thể bao gồm:

- Chờ các HTTP requests đang thực hiện.
- Dừng Kafka/RabbitMQ consumer và acknowledge các messages đã xử lý.
- Chờ `CompletableFuture`, executor tasks hoặc scheduled jobs.
- Flush file stream, commit/rollback transaction hoặc checkpoint.
- Hủy/subscription đóng client network.
- Sau cùng mới đóng datasource, broker connection, thread pool và những shared resources.

Một trình tự đúng:

```text
ACCEPTING
   |
   | request shutdown
   v
STOPPING: không nhận job mới
   |
   | chờ task đã nhận với timeout / retry policy
   v
DRAINED
   |
   | flush/commit/ACK (dependencies vẫn còn sống)
   v
CLEANED
   |
   | SpringApplication.exit(context)
   v
CONTEXT CLOSED
   |
   | System.exit(code)
   v
JVM EXITED
```

### 9.1. SmartLifecycle.stop(Runnable)

Ví dụ **mẫu kiến trúc**:

```java
@Override
public void stop(Runnable callback) {
    stopAccepting();

    CompletionStage<Void> drained = drainWithTimeout();
    drained.whenComplete((unused, failure) -> {
        if (failure != null) {
            recordFailure(failure);
            handleRetryOrCancel();
        }
        markStopped();
        callback.run();
    });
}
```

Đoạn này **không biên dịch độc lập**; phải định nghĩa các methods, imports và đồng bộ hóa. Nó cho thấy `stop(Runnable)` không được gọi callback ngay khi mới submit drain. Nếu callback chạy sớm, lifecycle processor có thể đóng resource provider ở phase tiếp theo, trong khi task còn sử dụng nó.

**Quan trọng:** phần stop do Spring thực hiện khi `SpringApplication.exit` đóng context diễn ra **sau lúc generator đã trả mã**, vì vậy lỗi cleanup được phát hiện lần đầu tại đây không mặc nhiên đổi exit code. Nếu cần mã phản ánh lỗi, bạn phải có một **phase drain explicit trước exit** hoặc một exit orchestrator khác có thể nhận completion/error trước khi chốt mã.

### 9.2. Không tạo deadlock khi đợi pool

Một ví dụ lỗi:

```text
Executor: chỉ một worker
   |
   +-- Worker chạy shutdown coordinator
           |
           +-- Submit cleanup task vào cùng executor
           +-- future.get() đợi cleanup
                  |
                  +-- Cleanup không bao giờ được schedule
```

Nếu `Future.get(timeout)` hoặc latch timeout được dùng, cần xét executor đang chạy coordinator có còn đủ capacity để hoàn tất task mà nó đợi hay không. Có thể cần một coordinator thread riêng, callback-based completion hoặc cách dừng đồng bộ bên ngoài pool.

### 9.3. Timeout không có nghĩa đã clean

`Future.get(5, TimeUnit.SECONDS)` hết hạn **không tự cancel** task nền. `Future.cancel(true)` chỉ yêu cầu interrupt nếu task có thể hợp tác; I/O có thể vẫn tiếp diễn, DB transaction có thể còn chờ.

Vì thế khi deadline hết, hãy:

1. Ghi trạng thái job chưa hoàn tất.
2. Yêu cầu cancel phù hợp và chờ xác nhận nếu có thể.
3. Gắn mã lỗi/metric cụ thể.
4. Đảm bảo nguồn dữ liệu có thể retry hoặc rollback.
5. Không công bố “cleanup completed” khi task vẫn đang có quyền dùng resource.

Khi không thể đạt cleanup hoàn toàn, return nonzero exit code và bảo đảm recovery state bền vững là quan trọng hơn việc log thành công giả.

### 9.4. Transaction và resource ownership

Một task `@Async` chạy ở thread khác không tự kế thừa transaction thread-local của caller. Đừng đóng `DataSource` ngay khi business method trả về nếu có background transaction vẫn dùng connection pool.

Resource owner (container, connection manager) chịu trách nhiệm đóng pool; consumer chỉ đóng **borrowed connections** sau khi hoàn tất. Nếu task quan trọng không được mất khi process chết, dùng transactional outbox/durable queue và idempotent processing, không trông chờ Java shutdown hooks.

## 10. Exit code khi đóng context có lỗi

Một bảng quyết định:

| Trạng thái | Mã đề xuất | Ghi chú |
| --- | --- | --- |
| Business thành công, explicit cleanup thành công | `0` | Đi qua Spring context close trước `System.exit` |
| Business thất bại, explicit cleanup thành công | `17` | Business result đã chốt trước generator |
| Explicit cleanup thất bại | `74` | Báo lỗi cao hơn business theo policy demo |
| Exception trong `context.close()` sau khi generator báo `0` | Có thể là `1` theo Boot 3.3 exit helper | Phụ thuộc exception được propagate tới helper |
| Exception trong `context.close()` khi mã đã là nonzero | Helper có thể giữ mã nonzero ban đầu | Không nên dùng để thay thế logic cleanup-result |
| Async task bị kill, không báo completion | Không có bảo đảm mã do ứng dụng mong muốn | Cần recovery/deadline/process supervision |

**Đừng dựa vào exception ở `@PreDestroy` để chốt mã 74:** code generator thường chạy trước; một số destroy errors có thể bị framework ghi log và bỏ qua theo contract bean destruction.

### 10.1. Error mapping trong Spring Boot

Một exception implement `ExitCodeGenerator` hoặc mapper phù hợp có thể làm Spring Boot báo mã lỗi khi startup/run thất bại. Đây là một đường riêng so với tình huống `SpringApplication.exit(context)` trên context đã khởi động thành công.

Nếu `ApplicationRunner` ném exception và `SpringApplication.run` không trả context, không đặt logic cleanup/exit trong đoạn code **chỉ chạy sau `run()`** rồi kỳ vọng nó luôn được gọi. Thực tế cần:

- Gắn cleanup với resource owner và Spring failure shutdown callbacks.
- Có chính sách retry/exception mapping cho startup failure.
- Không gọi `System.exit(0)` trong catch block để che giấu lỗi.
- Ghi lỗi vào stderr và log structured khi môi trường giám sát yêu cầu.

### 10.2. ExitCodeEvent không báo cleanup hoàn tất

`ExitCodeEvent` có thể được phát khi nonzero generator code **trước close**. Vì vậy listener của nó không phải sự kiện “all resources cleaned” hoặc “JVM about to be physically terminated” theo nghĩa mọi hooks đã xong.

Nếu muốn ghi mốc **cleanup completed**, hãy ghi sau completion signal của chính coordinator hoặc sau khi `SpringApplication.exit` trả về; cần nêu rõ có thể còn các unrelated JVM shutdown hooks do `System.exit` kích hoạt sau đó.

## 11. Khác biệt giữa CLI batch và ứng dụng server

### 11.1. CLI batch

Batch có điểm hoàn tất tự nhiên. Có thể tổ chức:

```text
run job -> await result -> explicit cleanup -> SpringApplication.exit -> System.exit
```

Khi cần code OS chính xác để cron/CI biết job thành công, `System.exit` ở main là một lựa chọn hợp lý.

### 11.2. Web service chạy dài hạn

Server thông thường **không** gọi `System.exit` sau `SpringApplication.run`, vì nó cần phục vụ requests. Khi nhận `SIGTERM` hoặc container orchestration termination, Spring Boot shutdown hook thường đóng context. Mã mà OS/container báo trong kịch bản signal termination không mặc nhiên được tạo bằng `ExitCodeGenerator` bean; cần phân biệt **process signal status** và **chủ động gọi SpringApplication.exit**.

Spring Boot 3.3 hỗ trợ graceful web shutdown qua:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là ví dụ cho **web server**, không mở endpoint HTTP trong project CLI ở mục 7. Graceful HTTP shutdown không tự chờ các async jobs tách khỏi request lifecycle; workers cần stop/drain riêng.

### 11.3. Shutdown trong Docker và Kubernetes

Nền tảng điều phối thường gửi tín hiệu dừng, đợi grace period rồi force kill nếu quá hạn. Muốn process có cơ hội trả mã đáng tin:

- Đảm bảo JVM thực nhận signal (đúng PID/entrypoint, không bị wrapper nuốt).
- Grace period đủ cho traffic drain, worker drain và bean cleanup.
- Tránh `SIGKILL`/OOM/power loss; nếu xảy ra, không bảo đảm shutdown hooks.
- Thiết kế durable work và khả năng retry sau restart.
- Trong health/rollout, đừng coi `exit 0` là bằng chứng mọi dữ liệu ngoài tiến trình đã được đồng bộ bền vững nếu workflow không bảo đảm.

**Không ép ứng dụng server gọi `System.exit` trong một controller chỉ vì muốn trả một mã lỗi HTTP.** HTTP status code và process exit code là hai cơ chế khác nhau.

## 12. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `System.exit(0)` ngay trong `ApplicationRunner` | Task nền/cleanup có thể chưa xong | Chờ kết quả, cleanup, `SpringApplication.exit`, sau cùng `System.exit` |
| `System.exit` rồi mới `context.close()` | Code sau thường không chạy | Đảo thứ tự, đóng context trước |
| Chỉ gọi `SpringApplication.exit(context)` và nghĩ OS nhận code | Helper chỉ trả `int`, không tự exit JVM | Ở outermost main, `System.exit(code)` nếu thực sự cần |
| Chỉ gọi `context.close()` và nghĩ mã lỗi nghiệp vụ được truyền | Close không có business exit code | `ExitCodeGenerator`/explicit result |
| Tin rằng `@PreDestroy` lỗi có thể tự đổi exit generator code | Generator được hỏi trước bước destroy | Cleanup có kết quả trước khi gọi `exit` |
| Tính mã khi async job còn chạy | Generator đọc trạng thái chưa cuối | Chờ completion/timeout, chốt result trước |
| `getExitCode()` có network I/O dài | Làm exit phức tạp, có thể timeout | Generator chỉ đọc trạng thái cuối |
| Nhiều ExitCodeGenerator không có quy tắc | Thứ tự chọn first-nonzero không rõ | Dùng `Ordered` hoặc một aggregator |
| Gọi `System.exit` trong `@PreDestroy` | Reentrant shutdown, khóa/lỗi cleanup | Dừng tại outermost boundary |
| Lỗi cleanup bị `catch` rồi báo `0` | CI nhận false-green | Nonzero code và log error |
| Chỉ nhìn mã `0` để kết luận job durable | Async write/DB có thể chưa commit | Flush/fsync/transaction/ack theo contract |
| Chờ future vô hạn trong shutdown | Process có thể bị kill trước khi xong | Timeout, cancellation, checkpoint/retry |
| Test gọi `main` có `System.exit` | JUnit JVM bị kết thúc | Test method `runAndClose`, subprocess cho end-to-end |
| Không kiểm tra `$?` ngay sau Java | Shell status đã bị lệnh khác thay đổi | Đọc status ngay |
| Nhầm HTTP status `500` với process exit code | Hai tầng báo lỗi khác nhau | HTTP code cho request, exit code cho toàn process |
| Kỳ vọng SIGKILL chạy cleanup | JVM không nhận được cơ hội | Durable state, retry/recovery |

## 13. Checklist trước khi vận hành

1. Mã `0` và các mã nonzero có được định nghĩa trong hợp đồng với scheduler/CI?
2. Business job đã thực sự hoàn tất (hoặc được chốt FAILED) trước khi tính mã?
3. Có công việc đã submit nhưng chưa bắt đầu hay còn trong executor queue?
4. Có explicit cleanup những resources mà generator cần biết kết quả không?
5. Có phân biệt cleanup failure với business failure và log cả hai?
6. `ExitCodeGenerator.getExitCode()` có ổn định, thread-safe và nhanh không?
7. Có một result aggregator hoặc order rõ nếu nhiều generators?
8. `SpringApplication.exit(context)` có được gọi trên context hợp lệ đã startup?
9. Có `context.close()`/Spring-managed destroy và SmartLifecycle stop đúng phase?
10. `stop(Runnable)` có gọi callback sau khi drain thật, không quá sớm?
11. Có deadline/shutdown phase timeout phù hợp với platform?
12. Có tránh gọi `System.exit` trong runner, worker và destroy hooks?
13. Shell/CI có thực sự kiểm tra process exit status?
14. Test có tách method trả code khỏi `main` để không giết JVM test?
15. Có kịch bản startup failure khiến `run()` không trả context?
16. Có kịch bản SIGTERM/SIGKILL và khả năng recover job bị ngắt?
17. Có bảo đảm flush/commit/ack cho dữ liệu cần lưu bền vững?
18. Có metrics/log phân biệt `cleanup requested`, `cleanup completed` và `context closed`?
19. Có bảo đảm resource không bị đóng khi consumer còn dùng?
20. Khi context close có lỗi, code/exception được ghi lại để điều tra?

## 14. Bài tập thực hành

1. Nêu khác biệt giữa `context.close()`, `SpringApplication.exit(context)` và `System.exit(code)`.
2. Vì sao `System.exit(SpringApplication.exit(context))` đóng context trước khi process exit?
3. Với Java `main` trả về bình thường sau khi in `"FAILED"`, mã OS mặc định có thể là gì?
4. Tại sao `ExitCodeGenerator` không nên chờ network call trong `getExitCode()`?
5. Trong implementation Boot 3.3.13, generator được gọi **trước hay sau** `@PreDestroy`?
6. Vì sao không nên tính mã cleanup chỉ trong `@PreDestroy` nếu generator đã được đọc trước?
7. Chạy demo không có option; xác nhận `CLEANUP completed` trước `BEAN preDestroy`.
8. Chạy `--business-fail`; xác nhận process exit `17` bằng Bash `$?` hoặc PowerShell `$LASTEXITCODE`.
9. Giải thích vì sao `EXIT event=17` xảy ra trước `BEAN preDestroy`.
10. Nếu cleanup thất bại, vì sao bài dùng mã `74` ưu tiên hơn `17`?
11. Viết một `ExitCodeGenerator` bean cho ba states `SUCCESS`, `INPUT_ERROR`, `IO_ERROR`.
12. Nếu hai ExitCodeGenerators cùng báo lỗi, Spring Boot chọn mã nào?
13. Trong JUnit, vì sao không gọi trực tiếp `CleanupExitApplication.main`?
14. Viết subprocess test chạy JAR, chờ tiến trình và assert exit code.
15. Thêm fake `FileOperations` để kiểm thử lỗi `close()` mà không thay permissions của OS.
16. Nếu `ApplicationRunner` ném exception trong `SpringApplication.run`, vì sao code sau `run` có thể không chạy?
17. Giải thích vai trò `ExitCodeExceptionMapper` trong đường startup failure.
18. Khi nào dùng `@PreDestroy` như fallback, và vì sao không nên để mã chính phụ thuộc fallback này?
19. Thiết kế shutdown/drain cho một worker có hàng trăm task đang chạy trên thread pool.
20. Vì sao timeout ở future không đồng nghĩa worker đã dừng?
21. Nếu container nhận `SIGKILL`, hook nào không được bảo đảm thực thi?
22. Với HTTP service, vì sao không gọi `System.exit` sau khi server startup?
23. So sánh trạng thái HTTP 503, process exit code 17 và readiness refusing.
24. Khi cần bảo đảm không mất công việc sau crash, đề xuất outbox/durable queue/idempotency.
25. Thiết kế một runbook có các bước: stop accepting, wait, flush, checkpoint, exit code, close context, exit JVM.

**Tiêu chí đạt:** chạy được code Java 21/Boot 3.3, phân biệt kết quả business và cleanup, biết `SpringApplication.exit` lấy mã trước khi context đóng nhưng trả mã sau khi đóng, không gọi `System.exit` quá sớm, và hiểu rõ giới hạn của shutdown trong JVM/crash/platform.

## 15. Tài liệu chính thức

- Spring Boot 3.3.13 — `SpringApplication.exit(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — Application Exit và ExitCodeGenerator: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — `ExitCodeEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- Spring Boot 3.3.13 — Mã nguồn `SpringApplication.exit`: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Framework 6.1 — `ConfigurableApplicationContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.3 — Graceful shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Java 21 — `System.exit` và JVM runtime shutdown: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
