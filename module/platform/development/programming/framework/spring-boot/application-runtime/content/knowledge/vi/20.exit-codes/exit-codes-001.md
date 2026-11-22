# Mã thoát tiến trình và ý nghĩa với shell hoặc bộ điều phối

**Mã thoát tiến trình (process exit code / exit status)** là một con số mà **tiến trình** gửi cho hệ điều hành khi kết thúc. Shell, công cụ CI/CD, trình quản lý dịch vụ, Docker và Kubernetes có thể đọc kết quả này để quyết định một lượt chạy **thành công, thất bại, cần retry hoặc cần cảnh báo**.

Với Spring Boot, cần đặc biệt phân biệt **kết quả công việc bên trong ứng dụng**, **`SpringApplication.exit(context)`**, **`System.exit(code)`** và **mã mà tiến trình cha thực sự quan sát được**. Một ứng dụng có thể in log báo lỗi nhưng vẫn trả mã `0`; ngược lại, tiến trình có thể bị hạ tầng dừng và trả mã khác `0` dù code nghiệp vụ chưa từng ném exception.

Bài học thuộc chương **Mã thoát** của module **Spring Boot Application Runtime**, tập trung vào ý nghĩa mã thoát với **shell và bộ điều phối**, áp dụng cho **Spring Boot 3.3.x, Java 17+, Bash, PowerShell, Docker và Kubernetes**.

Sau bài học, bạn có thể:

- Giải thích vì sao `0` thường biểu thị thành công, mã khác `0` biểu thị kết quả không thành công theo quy ước của shell.
- Phân biệt “đóng `ApplicationContext`” với “kết thúc JVM và chuyển exit status”.
- Cài đặt `ExitCodeGenerator` để trả trạng thái công việc cho shell.
- Quan sát và kiểm thử status thực bằng `$?` (Bash), `$LASTEXITCODE` (PowerShell) và công cụ container.
- Phân tích mã `1`, `7`, `126`, `127`, `130`, `137`, `143` đúng mức, không đoán nguyên nhân từ một con số.
- Thiết kế Kubernetes **Job/CronJob** khác **Deployment**, hiểu `restartPolicy` và `CrashLoopBackOff`.
- Tránh mất mã lỗi qua shell wrapper, pipeline, Gradle/Maven hoặc việc bắt exception rồi kết thúc bình thường.
- Đặt chính sách retry, logging và exit code nhất quán cho hệ thống vận hành.

## 1. Mã thoát nằm ở ranh giới giữa các tiến trình

Hãy hình dung một chương trình batch Spring Boot nhận file, xử lý và kết thúc:

~~~text
Shell / CI runner / Container runtime / Kubernetes
                       |
                       | start process
                       v
               Java Virtual Machine
                       |
                       v
               Spring Boot context
                       |
               +-------+--------+
               |                |
               v                v
          Job thành công     Job không thành công
               |                |
               v                v
          exit code 0       exit code khác 0
               |                |
               +-------+--------+
                       |
                       v
                JVM kết thúc
                       |
                       v
                OS ghi exit status
                       |
                       v
          Shell/Container runtime quan sát
                       |
              +--------+--------+
              |                 |
          tiếp tục           báo lỗi / retry /
          pipeline           fail Job / cảnh báo
~~~

Kết quả được truyền **qua ranh giới tiến trình**. Một `int` được lưu trong bean Spring, hoặc một dòng log `ERROR`, **không tự biến thành exit status**. Tiến trình phải thật sự kết thúc và cơ chế chạy phải nhận được mã đó.

### Quy ước cốt lõi

| Exit status | Cách hiểu phổ biến | Có thể suy ra gì? |
| --- | --- | --- |
| `0` | Thành công theo quy ước shell | Tiến trình tự báo hoàn tất thành công; không bảo đảm toàn bộ dữ liệu nghiệp vụ đúng nếu ứng dụng báo sai |
| Khác `0` | Không thành công theo quy ước shell | Cần kiểm tra mã theo **hợp đồng ứng dụng** và tình trạng tiến trình |
| `1` | Thường dùng cho lỗi chung | Không phải “bắt buộc luôn là lỗi Java” |
| `2`, `3`, `7`… | Có thể do ứng dụng tự định nghĩa | Phải tra bảng mã của ứng dụng, không đoán |
| `126` | Bash thường dùng cho command tìm thấy nhưng không thực thi được | Có thể là lỗi shell, không phải kết quả nghiệp vụ Spring Boot |
| `127` | Bash thường dùng khi command không tìm thấy | Có thể Java/JAR/script chưa được gọi |
| `128 + N` | Bash thường dùng khi command bị kết thúc bởi signal số `N` | Không chứng minh ứng dụng tự gọi `System.exit(128+N)` hay không |

Trong môi trường Unix, exit status mà shell thấy thường nằm trong phạm vi **0–255**. Trên nền tảng khác, cách biểu diễn và các mã hệ thống có thể khác. **Đừng xây hợp đồng nghiệp vụ chỉ dựa trên mã lớn hoặc mã âm rồi cho rằng mọi OS sẽ truyền nguyên vẹn.**

## 2. Ba tầng trạng thái phải tách riêng

Với một ứng dụng Spring Boot, có ít nhất ba tầng:

1. **Kết quả nghiệp vụ:** ví dụ đã xử lý 500 record, 5 record sai định dạng, hay file không tồn tại. Đây có thể là một object Java hoặc bản ghi database.
2. **Kết quả của `SpringApplication.exit(context)`:** Spring Boot đóng context và tính mã theo các `ExitCodeGenerator` thích hợp.
3. **Mã thoát của tiến trình Java:** JVM gửi cho OS khi kết thúc, thường bằng `System.exit(code)` hoặc một kết cục tiến trình khác.

### Những lời gọi không tương đương

~~~java
context.close();
~~~

Chỉ đóng container theo hợp đồng của Spring, **không tự gửi exit status tùy biến cho shell**.

~~~java
int code = SpringApplication.exit(context);
~~~

Đóng context và **trả về một số nguyên** phản ánh kết quả từ cơ chế exit code của Spring Boot. Nhưng **nó không tự thực hiện `System.exit`**.

~~~java
System.exit(code);
~~~

Yêu cầu **toàn bộ JVM** kết thúc với exit code được cung cấp. Đây là bước làm cho shell/process supervisor nhận được mã từ tiến trình theo cách trực tiếp.

Cách thường dùng với một ứng dụng CLI/batch tự kết thúc:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là **mã minh họa**, cần class `MyApplication` và import tương ứng. Ví dụ chạy đầy đủ nằm ở phần 7.

**Cảnh báo:** không gọi `System.exit(...)` từ một HTTP controller hoặc một phương thức nghiệp vụ chỉ để báo “request này thất bại”. Nó sẽ kết thúc **cả JVM**, ảnh hưởng mọi request và tác vụ còn lại. HTTP status là cơ chế trả lỗi của một request; process exit code là trạng thái của **toàn tiến trình**.

## 3. `SpringApplication.exit(context)` làm gì trong Spring Boot 3.3?

Theo API Spring Boot **3.3.13**:

~~~java
int code = SpringApplication.exit(
        applicationContext,
        exitCodeGenerator1,
        exitCodeGenerator2);
~~~

Phương thức `exit(ApplicationContext, ExitCodeGenerator...)`:

- Cho phép lấy mã từ những `ExitCodeGenerator` truyền trực tiếp và từ **Spring beans** triển khai `ExitCodeGenerator`.
- Theo thứ tự các generator đã được sắp xếp, lấy **mã khác 0 đầu tiên**; nếu không có mã khác 0, kết quả thành công thường là `0`.
- Hỗ trợ `Ordered` hoặc `@Order` để kiểm soát thứ tự chọn nếu có nhiều nguồn.
- Đóng `ApplicationContext` khi có thể, để Spring thực hiện những lifecycle callback cần thiết.
- **Trả về mã** cho caller, không tự buộc JVM kết thúc.

Giao diện `ExitCodeGenerator` đơn giản:

~~~java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

Đây là **chữ ký rút gọn phục vụ học tập**, không phải toàn bộ source/Javadoc. Ta có thể triển khai bằng class, lambda hoặc bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

Đoạn trên nằm trong class cấu hình Spring, cần import `@Bean` và `ExitCodeGenerator`; chỉ minh họa một generator luôn trả `7`. Trong ứng dụng thật, mã nên phản ánh **kết quả công việc thực tế**.

### Một điểm dễ nhầm

Nếu chỉ gọi:

~~~java
int code = SpringApplication.exit(context);
System.out.println("Calculated code = " + code);
~~~

rồi để `main` kết thúc bình thường mà **không gọi `System.exit(code)`**, shell có thể nhận `0` dù `code` là `7`. Đối tượng Java `int code` không tự truyền qua OS.

Ngược lại, gọi trực tiếp:

~~~java
System.exit(7);
~~~

có thể khiến shell nhận `7` ngay cả khi không dùng `ExitCodeGenerator`. Nhưng khi bỏ qua `SpringApplication.exit`, bạn không sử dụng cơ chế tính mã từ Spring beans, và việc đóng context khi JVM shutdown phụ thuộc shutdown hook còn hoạt động.

## 4. `ExitCodeGenerator` có thể được đặt ở đâu?

### Dưới dạng bean

~~~java
@Bean
ExitCodeGenerator operationOutcome(OperationResult result) {
    return result::getExitCode;
}
~~~

Đây là fragment, giả định `OperationResult` là bean đã tồn tại, có method `getExitCode()`. Spring Boot đọc generator khi gọi `SpringApplication.exit(...)`.

### Truyền trực tiếp vào `exit`

~~~java
int code = SpringApplication.exit(
        context, () -> calculationWasValid ? 0 : 7);
~~~

`calculationWasValid` là biến boolean được xác định trước đó trong code, không phải bean bắt buộc. Cách này hữu ích cho CLI có kết quả đã có ngay trong `main`.

### Khi có nhiều generator

Giả sử:

~~~text
Generator A (độ ưu tiên cao): 0
Generator B (độ ưu tiên tiếp): 7
Generator C (độ ưu tiên thấp): 4
~~~

Theo hợp đồng Spring Boot, **mã khác 0 đầu tiên** sau khi sắp xếp sẽ được dùng: ở ví dụ này là `7`. Đừng mặc định “mã lớn nhất thắng”, “mã sau cùng thắng” hoặc “Spring cộng tất cả mã”.

Nếu các nguồn kết quả có thể mâu thuẫn, thiết kế **một thành phần tổng hợp kết quả nghiệp vụ** và phát một exit code theo chính sách rõ ràng thường dễ bảo trì hơn phụ thuộc nhiều generator.

## 5. Lỗi khởi động: `ExitCodeGenerator` trên exception và `ExitCodeExceptionMapper`

Khi startup gặp exception, Spring Boot có cơ chế lấy exit code từ exception triển khai `ExitCodeGenerator` hoặc từ một `ExitCodeExceptionMapper` phù hợp.

Ví dụ một exception mang mã:

~~~java
public final class InvalidInputException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidInputException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 4;
    }
}
~~~

Đây là class minh họa trong dự án Spring Boot, cần import `org.springframework.boot.ExitCodeGenerator`. Trong code thực tế, có thể gặp exception được framework bọc bằng exception khác; phải kiểm thử toàn bộ chuỗi nguyên nhân trên **đúng phiên bản Spring Boot**.

`ExitCodeExceptionMapper` là chiến lược ánh xạ `Throwable` sang mã:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return error -> {
        if (error instanceof InvalidInputException) {
            return 4;
        }
        return 0;
    };
}
~~~

Đây là fragment trong lớp cấu hình Spring có `InvalidInputException`, cần import `@Bean` và `ExitCodeExceptionMapper`. Với lỗi xảy ra **trước khi bean mapper được tạo**, bean này có thể chưa khả dụng; không thể bảo đảm mọi lỗi hạ tầng sớm nhất sẽ được ánh xạ theo ý muốn.

**Khác biệt quan trọng:** ví dụ batch phần 7 cố ý **không ném exception**, mà lưu kết quả nghiệp vụ vào một bean để `SpringApplication.exit(context)` đọc. Nhờ vậy, cả luồng thành công và thất bại được mô tả/tái hiện rõ ràng mà không dựa vào chi tiết xử lý exception trong `SpringApplication.run`.

### `ExitCodeEvent`

Spring Boot còn có `ExitCodeEvent` được phát khi xác định exit code qua `ExitCodeGenerator` trong các đường xử lý phù hợp. Event này có `getExitCode()` để quan sát mã được xác định; nó **không tự thay thế `System.exit`**.

Không coi việc thấy `ExitCodeEvent` trong log là bằng chứng hệ điều hành đã nhận cùng mã: phải kiểm tra status của **tiến trình Java thực sự**.

## 6. Quy ước exit code cho ứng dụng batch

Spring Boot **không bắt buộc** các ứng dụng tự đặt những mã `2`, `4`, `7` theo một ý nghĩa toàn cầu. Đội ngũ nên định nghĩa một bảng mã riêng và áp dụng nhất quán.

Một quy ước minh họa:

| Mã | Ý nghĩa do ứng dụng tự định nghĩa | Cách xử lý mong muốn |
| --- | --- | --- |
| `0` | Hoàn tất toàn bộ công việc theo tiêu chí thành công | Không retry |
| `2` | Input sai cú pháp hoặc thiếu tham số | Báo lỗi cấu hình; thường không retry nguyên input |
| `3` | Dữ liệu nghiệp vụ không hợp lệ, không thể xử lý | Đưa vào DLQ/đánh dấu thất bại, không retry vô hạn |
| `4` | Cấu hình hoặc secret bắt buộc không hợp lệ | Cần sửa cấu hình |
| `7` | Job thất bại theo kết quả nghiệp vụ | Tùy tính chất lỗi mà quyết định retry hay điều tra |
| `10` | Phụ thuộc ngoài tạm thời không khả dụng | Retry có giới hạn, backoff/jitter |
| `11` | Hết thời gian chờ nội bộ | Kiểm tra downstream và timeout |
| `12` | Lỗi tài nguyên/quota | Cần quan sát dung lượng và giới hạn |

**Đây là bảng mã do bài học đề xuất làm ví dụ, không phải bảng mã được Spring Boot hoặc Linux định nghĩa.** Trong production, nên tài liệu hóa từng mã cùng tác nhân xử lý và khả năng retry.

Đặc biệt, **non-zero không đồng nghĩa “hãy retry mãi”**. Một file sai định dạng vẫn sai sau 100 lần chạy. Hệ thống điều phối cần chính sách retry phân loại theo lỗi, không chỉ dùng một vòng lặp vô hạn.

## 7. Ví dụ chạy được: Spring Boot CLI trả exit code cho hệ điều hành

Tạo một ứng dụng console **Spring Boot 3.3.13 + Java 17 + Gradle**. Ví dụ có hai chế độ:

- Không có đối số `--fail`: job thành công, mã `0`.
- Có đối số `--fail`: job chủ động đánh dấu thất bại nghiệp vụ, mã `7`.

Có một bean `@PreDestroy` để quan sát rằng `SpringApplication.exit(context)` đã đóng context **trước khi** process trả mã cho OS.

### 7.1. Cấu trúc thư mục

~~~text
exit-code-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exitcode/
    └── ExitCodeDemoApplication.java
~~~

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'exit-code-demo'
~~~

### 7.3. `build.gradle`

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
    // Quản lý phiên bản cho starter và Jakarta Annotations bằng BOM.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

**Lưu ý dependency:** chỉ áp dụng plugin `org.springframework.boot` mà không có dependency management/BOM thì starter không có version tường minh **có thể không phân giải được**. Ví dụ khai báo **Gradle native BOM** để chạy độc lập. Cần JDK 17+ và Gradle tương thích với Spring Boot 3.3.

### 7.4. `ExitCodeDemoApplication.java`

~~~java
package com.example.exitcode;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExitCodeDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitCodeDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        ConfigurableApplicationContext context = application.run(args);

        // Tính mã dựa trên ExitCodeGenerator bean, đồng thời đóng context.
        int code = SpringApplication.exit(context);
        System.out.println("PROCESS exitCode=" + code);

        // Chuyển mã này cho JVM/OS, không chỉ giữ trong một biến Java.
        System.exit(code);
    }

    @Bean
    JobResult jobResult() {
        return new JobResult();
    }

    @Bean
    ExitCodeGenerator jobExitCodeGenerator(JobResult result) {
        return result::getExitCode;
    }

    @Bean
    ApplicationRunner runJob(JobResult result) {
        return args -> {
            if (args.containsOption("fail")) {
                result.markFailed(7);
                System.out.println("JOB result=FAILED");
            } else {
                System.out.println("JOB result=SUCCESS");
            }
        };
    }

    @Bean
    CleanupMarker cleanupMarker() {
        return new CleanupMarker();
    }

    static final class JobResult {
        private final AtomicInteger exitCode = new AtomicInteger(0);

        int getExitCode() {
            return exitCode.get();
        }

        void markFailed(int code) {
            exitCode.set(code);
        }
    }

    static final class CleanupMarker {
        @PreDestroy
        void cleanup() {
            System.out.println("CONTEXT cleanup");
        }
    }
}
~~~

Mẫu này có các điểm đáng chú ý:

1. `WebApplicationType.NONE`: ứng dụng không cần Tomcat hoặc cổng HTTP; phù hợp job có điểm kết thúc rõ ràng.
2. `ApplicationRunner` chạy **trước khi `SpringApplication.run(args)` trả về** trên đường khởi động thành công.
3. Runner cập nhật `JobResult`. Vì `JobResult` là một singleton do context quản lý, bean `ExitCodeGenerator` đọc đúng mã sau khi runner hoàn tất.
4. `SpringApplication.exit(context)` lấy mã từ generator và đóng context.
5. `@PreDestroy` trên `CleanupMarker` in dấu mốc dọn dẹp trong quá trình đóng context.
6. `System.exit(code)` chuyển mã ra ngoài JVM.
7. `AtomicInteger` ở đây chỉ giúp biểu diễn state đơn giản; trong ví dụ runner đồng bộ, không cần cơ chế song song phức tạp. Trong job thật, cần chờ mọi task bắt buộc hoàn tất **trước khi quyết định mã**.

**Quan trọng:** `--fail` ở demo là một tùy chọn dùng để mô phỏng thất bại **theo kết quả nghiệp vụ**, không phải một exception. Điều này có nghĩa Spring Boot vẫn có thể hoàn thành giai đoạn startup và `ApplicationReadyEvent` trước khi `main` gọi exit. Đừng coi sự kiện ready là bản báo cáo cuối cùng cho kết quả một batch job.

### 7.5. Build

Nếu thư mục dự án có Gradle Wrapper tương thích:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

Nếu chưa tạo wrapper nhưng đã có Gradle tương thích:

~~~bash
gradle clean bootJar
~~~

Với `rootProject.name` và `version` như trên, tên JAR thường là:

~~~text
build/libs/exit-code-demo-1.0.0.jar
~~~

Tên thật có thể khác nếu cấu hình build được tùy chỉnh; hãy xác nhận artifact đã tạo.

### 7.6. Chạy thành công

Trong Bash, từ thư mục project:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar
echo "JAVA_EXIT=$?"
~~~

Các dòng **do chương trình Java của demo in bằng `System.out.println`** trên đường thành công là:

~~~text
JOB result=SUCCESS
CONTEXT cleanup
PROCESS exitCode=0
~~~

Sau đó Bash in:

~~~text
JAVA_EXIT=0
~~~

Đây không nhất thiết là **toàn bộ stdout/stderr**, vì Spring Boot hoặc công cụ chạy có thể ghi log khác. Cần so sánh các marker của demo theo thứ tự.

### 7.7. Chạy thất bại nghiệp vụ

Dùng **một tiến trình Java mới**:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
echo "JAVA_EXIT=$?"
~~~

Các dòng của demo:

~~~text
JOB result=FAILED
CONTEXT cleanup
PROCESS exitCode=7
~~~

Bash sau đó in:

~~~text
JAVA_EXIT=7
~~~

Kết quả quan trọng: **process thực sự thoát với mã `7`**, không chỉ in chữ “FAILED”.

Trên đường chạy này, `@PreDestroy` đã được gọi qua `SpringApplication.exit(context)` và context đã đóng trước `System.exit(7)`. Nếu JVM bị kill cưỡng bức, không thể bảo đảm các callback tương tự chạy đầy đủ.

### 7.8. Vì sao không chỉ dùng Gradle `bootRun` để đo mã?

Chạy:

~~~bash
./gradlew bootRun --args="--fail"
~~~

có thể khiến task Gradle `bootRun` **thất bại** vì process Java kết thúc khác `0`. Nhưng exit code của **Gradle wrapper/Gradle process** mà shell nhìn thấy **không phải hợp đồng bảo đảm giữ nguyên đúng mã `7` của JVM con**. Công cụ build có thể chuyển đổi lỗi thành exit code của chính nó, kèm stack trace.

Muốn kiểm thử chính xác process exit code, ưu tiên:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
~~~

và đọc status **ngay sau lệnh Java**. Tương tự với việc chạy qua Maven plugin, IDE, service wrapper hay một script bao ngoài: luôn hỏi **process nào** đang được shell/CI quan sát.

## 8. Bash: đọc `$?` và điều khiển script

Trong Bash, `$?` chứa exit status của **lệnh/pipeline vừa hoàn tất gần nhất**. Ví dụ:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
status=$?
printf 'java exit=%s\n' "$status"
~~~

**Phải lưu `$?` ngay.** Nếu chạy một lệnh khác trước khi đọc, bạn có thể đang đọc mã của `echo`, `printf` hoặc `grep` thay vì mã của Java.

### Quyết định trong `if`

~~~bash
if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
    echo "JOB SUCCEEDED"
else
    status=$?
    echo "JOB FAILED with exit=$status"
fi
~~~

Nhánh `else` đọc `$?` ngay sau khi Java không thành công. Nếu dùng `set -e`, một lệnh non-zero đứng một mình có thể khiến script kết thúc **trước khi** chạy tới dòng lưu trạng thái. Đặt lệnh vào điều kiện `if` là một cách rõ ràng để chủ động xử lý non-zero.

### Truyền lỗi từ script bao ngoài

Nếu script quyết định phải báo cùng mã:

~~~bash
#!/usr/bin/env bash
if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
    exit 0
else
    status=$?
    exit "$status"
fi
~~~

Script này có thể được CI gọi. Nếu Java trả `7`, script trả `7`; nếu Java thành công, script trả `0`.

### Pipeline với `tee` có thể che mã Java

Ví dụ:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee app.log
echo "$?"
~~~

Theo quy tắc Bash mặc định, status của pipeline trên thường là status của **lệnh cuối `tee`**. Nếu `tee` thành công, script có thể in `0` **dù Java trả `7`**.

Với Bash, bật:

~~~bash
set -o pipefail
java -jar build/libs/exit-code-demo-1.0.0.jar --fail 2>&1 | tee app.log
status=$?
printf 'pipeline status=%s\n' "$status"
~~~

Nếu Java là thành phần duy nhất lỗi và `tee` thành công, pipeline sẽ trả mã non-zero của Java. **`pipefail` là tính năng Bash**, không được mặc định có trong mọi `/bin/sh`. Nếu cần phân tích status **của từng stage** khi nhiều lệnh có thể thất bại, dùng cơ chế `PIPESTATUS` của Bash hoặc script wrapper được thiết kế rõ.

### `&&` và `||`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar &&
    echo "Next stage can run"
~~~

Với exit code `0`, lệnh tiếp theo chạy. Với non-zero, nhánh sau `&&` không được chạy.

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail ||
    echo "Job failed; investigate"
~~~

Đoạn `||` xử lý lỗi, nhưng nếu script kết thúc bằng một `echo` thành công thì **exit status cuối của script có thể trở thành `0`**. Nếu muốn CI nhận lỗi, phải `exit` với mã phù hợp sau khi ghi log.

## 9. PowerShell và Windows: đọc đúng loại trạng thái

Trong **PowerShell**, sau khi gọi một chương trình native như `java.exe`, mã thoát nằm trong `$LASTEXITCODE`:

~~~powershell
java -jar .\build\libs\exit-code-demo-1.0.0.jar --fail
$code = $LASTEXITCODE
Write-Output "JAVA_EXIT=$code"
~~~

Kết quả nếu demo chạy đúng:

~~~text
JAVA_EXIT=7
~~~

**Đừng nhầm `$?` của PowerShell với `$?` của Bash**. Trong PowerShell, `$?` thường biểu thị **thành công/thất bại của thao tác PowerShell dưới dạng Boolean** theo ngữ nghĩa phiên bản shell, không phải bản sao nguyên vẹn của mã `7`. Khi cần con số process exit status, dùng **`$LASTEXITCODE`**.

Để test:

~~~powershell
java -jar .\build\libs\exit-code-demo-1.0.0.jar --fail
$code = $LASTEXITCODE
if ($code -ne 7) {
    throw "Expected exit 7 but got $code"
}
Write-Output "PASS exit code 7"
~~~

Trong **Windows Command Prompt (cmd.exe)**, trạng thái thường được đọc qua `ERRORLEVEL`:

~~~bat
java -jar build\libs\exit-code-demo-1.0.0.jar --fail
echo JAVA_EXIT=%ERRORLEVEL%
~~~

Đoạn trên là ví dụ chạy tương tác trong cmd; trong batch file có block lệnh/đặc thù expansion thì cần kiểm tra thời điểm mở rộng `%ERRORLEVEL%`.

**Cảnh báo:** Windows/Linux có khác biệt ở phạm vi mã và cách hệ điều hành biểu diễn tín hiệu. Bảng `128+signal` là quy ước của Bash/Unix, **không chuyển nguyên xi thành bảng nghĩa của mọi mã Windows**.

## 10. Docker: exit code của container có thể khác mã JVM nếu wrapper xử lý sai

Trong container, platform quan sát **tiến trình chính của container**. Nếu JVM được chạy trực tiếp theo exec-form:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/exit-code-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

và build image theo artifact mẫu, tham số khi chạy được chuyển cho Java:

~~~bash
docker run --rm exit-code-demo:local --fail
echo "CONTAINER_EXIT=$?"
~~~

Nếu image có tên `exit-code-demo:local` (được build riêng), Docker CLI thường trả theo status của process container trên đường chạy thành công của chính lệnh `docker run`; khi Java thoát `7`, ta kỳ vọng thấy non-zero tương ứng. Tuy nhiên, cần phân biệt **lỗi của Docker CLI/daemon/image startup** với lỗi mà JVM thật sự đã chạy. Trong môi trường giám sát, ưu tiên đọc **container termination state** chứ không chỉ dựa vào output của một wrapper.

### Dùng shell wrapper phải bảo toàn status

Nếu image chạy một script:

~~~sh
#!/bin/sh
exec java -jar /app/app.jar "$@"
~~~

`exec` thay thế shell bằng tiến trình Java, giúp tín hiệu và exit code đi tới tiến trình chính rõ ràng hơn. Phần `"$@"` truyền nguyên các tham số caller.

Một wrapper dễ làm mất mã:

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
echo "Java finished"
~~~

Lệnh cuối của script là `echo`. Nếu Java trả `7` nhưng `echo` thành công, script có thể kết thúc với `0`. Điều này khiến container/CI tưởng job thành công.

Nếu cần ghi log sau Java:

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
status=$?
echo "Java finished with $status"
exit "$status"
~~~

Đây là đường wrapper có chủ đích; cần xem thêm truyền tín hiệu đến tiến trình con khi shell làm PID 1. Với container production, **exec-form ENTRYPOINT hoặc script dùng `exec`** thường dễ quản lý tín hiệu hơn.

## 11. Kubernetes: mã thoát được dùng thế nào?

Kubernetes quản lý container theo **Pod lifecycle** và `restartPolicy`. Hai bối cảnh có ý nghĩa khác nhau rõ rệt:

### A. Deployment — tiến trình dịch vụ chạy lâu

Deployment thường dùng Pod có `restartPolicy: Always`. Khi container kết thúc, kubelet cố khởi động lại container theo chính sách, **kể cả khi exit code `0`**.

~~~text
Deployment / application web
   |
   +-- Process 0: tự thoát sạch
   |       -> restart do restartPolicy Always
   |
   +-- Process 7: thoát lỗi nghiệp vụ
   |       -> restart do restartPolicy Always
   |
   +-- Process bị kill / liveness failure
           -> kubelet có thể restart
~~~

Điểm cần nhớ: **mã `0` không có nghĩa Deployment sẽ không restart**. Một web service có `main` tự kết thúc sau vài giây nhưng được triển khai như Deployment có thể bị restart liên tục, không phải vì business code trả lỗi.

Nếu restart diễn ra liên tiếp, Kubernetes có thể hiện trạng thái **`CrashLoopBackOff`** với backoff tăng dần. Đây **không phải một exit code** và cũng không tự xác định nguyên nhân gốc.

### B. Job/CronJob — tiến trình có điểm kết thúc

Job có mục đích hoàn thành một công việc. Thông thường:

- Exit code `0` của main container được coi là một tín hiệu hoàn thành thành công của lần chạy container.
- Exit code khác `0` thường biểu thị lần chạy không thành công.
- Kubernetes có thể retry theo `restartPolicy` và chính sách của Job, cho tới khi đạt điều kiện thành công hoặc thất bại.
- CronJob tạo Jobs theo lịch; tình trạng Job phản ánh thành công/thất bại của công việc chạy theo lịch, không chỉ việc Pod đã từng ở trạng thái Running.

### Ví dụ Job

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: exit-code-demo-job
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: batch
          image: registry.example.com/demo/exit-code-demo:1.0.0
          args: ["--fail"]
~~~

Đây là **manifest mẫu**, dùng image giả định để minh họa; image thật phải được build/push với `ENTRYPOINT` chạy JAR ví dụ. Với `--fail`, Java trả `7`. Vì `restartPolicy: Never`, container của Pod thất bại không được restart trong chính Pod đó theo chính sách; **Job controller có thể tạo Pod thử lại** theo `backoffLimit` và logic Job. Sau khi hết cơ hội retry theo chính sách, Job được đánh dấu Failed.

Nếu bỏ `--fail` và job không có lỗi khác, Java trả `0`; Job có thể đạt trạng thái Succeeded khi các điều kiện hoàn thành của Job được đáp ứng.

**Không đồng nhất `backoffLimit: 2` với “chắc chắn tạo đúng hai Pod và sau đó dừng”** trong mọi tình huống. Cách tính retry/backoff, parallelism và các lỗi hạ tầng ảnh hưởng số lần khởi chạy thực tế; hãy xem tài liệu Job theo phiên bản cluster.

### `restartPolicy` theo Pod

| Chính sách | Exit `0` | Exit non-zero |
| --- | --- | --- |
| `Always` | Restart | Restart |
| `OnFailure` | Không restart vì container kết thúc thành công | Restart container có lỗi |
| `Never` | Không restart container này | Không restart container này |

Các quy tắc trên là mô hình cơ bản cho Pod container theo tài liệu Kubernetes; các đặc thù sidecar, init container và chính sách restart ở phiên bản cluster mới có thể cần xử lý riêng.

**Job controller** còn có logic tạo Pod/đếm thất bại ở mức cao hơn. Vì vậy, câu “`restartPolicy: Never` nên không retry Job” là **sai**: nó chỉ nói kubelet không restart **container trong Pod đó**; controller vẫn có thể tạo Pod mới.

## 12. Các mã `130`, `137`, `143`: đừng gắn nguyên nhân cứng

Trong môi trường Bash/Unix, khi một tiến trình **bị kết thúc bởi signal số `N`**, Bash thường báo status **`128 + N`**.

| Mã quan sát thường gặp | Cách tính trong Bash | Diễn giải có thể có |
| --- | --- | --- |
| `130` | `128 + 2` | `SIGINT`, thường do Ctrl+C |
| `137` | `128 + 9` | `SIGKILL`, có thể OOM kill hoặc kill cưỡng bức |
| `143` | `128 + 15` | `SIGTERM`, có thể từ yêu cầu dừng bình thường |
| `1` | Không phải mã signal theo công thức trên | Có thể do ứng dụng/JVM/launcher báo lỗi chung |
| `7` | Không phải mã signal theo công thức trên | Có thể do chính ứng dụng tự quy định |

**Không kết luận mọi `137` = OOM.** Một quản trị viên có thể dùng `kill -9`, hoặc orchestrator gửi `SIGKILL` khi vượt grace period. Để phân biệt, kiểm tra `reason: OOMKilled`, sự kiện Pod, memory metrics, kernel/container logs và thời điểm shutdown.

**Không kết luận mọi `143` = ứng dụng lỗi.** Một tiến trình có thể nhận `SIGTERM` do rolling deployment hoặc scale-down bình thường. Cũng có thể JVM xử lý tín hiệu, chạy hook và tự trả một mã khác. Tình trạng thực tế phụ thuộc runtime và cách process kết thúc.

Và **không thể chỉ dựa vào mã số để khẳng định chắc chắn đã nhận một signal**: ứng dụng vẫn có thể gọi `System.exit(143)` theo ý muốn. Phải dùng thêm thông tin `signal`, `reason`, log và hoạt động của controller.

### Shutdown hook không bảo đảm exit code bằng 0

Trong Spring Boot, `ApplicationContext` thường được đóng khi JVM shutdown bình thường nhờ shutdown hook. Nhưng `@PreDestroy` chạy đầy đủ chỉ chứng minh đã đi qua một phần cleanup; **mã thoát vẫn phụ thuộc cách JVM được yêu cầu kết thúc và kết quả thực của tiến trình**.

Nếu container gửi `SIGTERM` rồi sau đó `SIGKILL` do quá hạn, kết quả cuối có thể là `137` bất kể một số callback đã bắt đầu. Cần phối hợp timeout của Spring, thời gian grace của Kubernetes và thời gian drain thực tế.

## 13. Đọc mã thật từ Kubernetes

Giả sử Pod tên `my-batch-pod`, namespace `jobs`:

~~~bash
kubectl get pod my-batch-pod -n jobs -o wide
kubectl describe pod my-batch-pod -n jobs
kubectl logs my-batch-pod -n jobs --container=batch
~~~

Với container đã kết thúc, có thể đọc trực tiếp mã trong trạng thái `terminated`:

~~~bash
kubectl get pod my-batch-pod -n jobs \
  -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}'
~~~

Nếu container đã bị restart và hiện đang chạy, mã của lần trước có thể nằm ở:

~~~bash
kubectl get pod my-batch-pod -n jobs \
  -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'
~~~

Hai đường `jsonpath` trên là ví dụ khi container đầu tiên trong `containerStatuses` chính là container cần điều tra; ở Pod nhiều container, **đừng mặc định index 0 luôn là container bạn muốn**. Đọc `name` hoặc lọc theo tên khi triển khai script giám sát.

Xem thêm `reason`, `message`, `startedAt`, `finishedAt` và số restart. Ví dụ:

~~~text
state.terminated.exitCode = 137
state.terminated.reason   = OOMKilled
~~~

Đây là **một cặp giá trị minh họa**, không phải status được lấy từ cluster hiện có. Nếu thực sự thấy `OOMKilled` cùng mã `137`, hướng điều tra memory limit và memory usage có căn cứ hơn việc suy từ `137` đơn độc.

Với Job, xem:

~~~bash
kubectl get job exit-code-demo-job -n jobs
kubectl describe job exit-code-demo-job -n jobs
~~~

Trạng thái tổng của Job (`Succeeded`/`Failed`) và mã exit của một container là **hai cấp khác nhau**. Một Job có thể đã trải qua nhiều Pod hoặc lần retry trước khi đạt kết quả cuối.

## 14. Exit code và readiness/liveness không phải một

| Tín hiệu | Xảy ra lúc nào? | Ai sử dụng? |
| --- | --- | --- |
| HTTP status `200` / `500` | Khi một request hoàn tất | HTTP client, gateway |
| `ReadinessState` / readiness probe | Trong khi process còn chạy | Hệ thống định tuyến traffic |
| `LivenessState` / liveness probe | Trong khi process còn chạy | Kubelet/giám sát khả năng phục hồi |
| `ApplicationReadyEvent` | Sau runners của Spring Boot | Code trong JVM biết mốc startup |
| Process exit code | Khi tiến trình kết thúc | Shell, CI, OS, container runtime, Job controller |
| Job status | Sau các lần chạy container/Pod theo chính sách | Kubernetes Job/CronJob, workflow controller |

Một endpoint HTTP trả `500` **không có nghĩa JVM phải thoát `1`**. Một readiness probe thất bại **không tự biến thành mã thoát**; nếu liveness failure khiến kubelet restart container, tiến trình có thể kết thúc sau đó theo cơ chế riêng.

Ngược lại, ví dụ chương trình CLI ở phần 7 có thể phát `ApplicationReadyEvent`, nhưng runner đã ghi `JOB result=FAILED`. Sau đó `SpringApplication.exit(context)` xác định mã `7` và JVM trả non-zero. **Startup thành công không phải bằng chứng batch job thành công.**

Đối với ứng dụng web chạy lâu, không nên dùng process exit code để truyền kết quả từng request. Đối với ứng dụng batch có vòng đời hữu hạn, exit code lại rất phù hợp làm **hợp đồng cuối cùng** giữa job và scheduler.

## 15. CI/CD và workflow engine nên xử lý mã như thế nào?

Một pipeline thường muốn dừng khi job thất bại:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

java -jar build/libs/exit-code-demo-1.0.0.jar
echo "Next stage: publish results"
~~~

Nếu Java trả `0`, stage tiếp theo chạy; nếu Java trả non-zero, `set -e` trong tình huống lệnh đơn thông thường khiến script thất bại. Nhưng `set -e` có nhiều ngoại lệ liên quan `if`, `while`, `&&`/`||` và subshell; khi cần xử lý retry, nên lưu status rõ ràng thay vì trông vào mọi chi tiết ngầm định của shell.

Nếu job thất bại nhưng có thể retry:

~~~bash
#!/usr/bin/env bash
attempt=1
while [ "$attempt" -le 3 ]; do
    if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
        echo "Succeeded"
        exit 0
    else
        status=$?
        echo "Attempt $attempt failed with $status"
    fi
    attempt=$((attempt + 1))
done
exit "$status"
~~~

Đây là script minh họa **chủ đích luôn truyền `--fail`**, nên job sẽ thất bại cả ba lần; nó dùng để quan sát cách truyền mã, **không phải ví dụ retry một lỗi có khả năng hồi phục**. Production cần phân loại lỗi và backoff/jitter, không retry vô hạn một lỗi input cố định.

### Phân loại retry theo mã

| Nhóm lỗi | Mã ví dụ | Nên retry tự động? |
| --- | --- | --- |
| Thành công | `0` | Không |
| Input sai vĩnh viễn | `2` hoặc `3` | Thường không |
| Secret/config sai | `4` | Không cho tới khi sửa cấu hình |
| Lỗi mạng tạm thời | `10` | Có giới hạn, nếu công việc idempotent |
| Timeout tạm thời | `11` | Xét nguyên nhân và số lần |
| `SIGTERM` do scale-down | Có thể `143` hoặc mã khác | Không mặc định coi là business failure cần chạy lại |
| `SIGKILL`/OOM | Có thể `137` | Điều tra memory/grace trước retry |

Đây là **chính sách ví dụ**, không phải contract chung. Kubernetes `restartPolicy: OnFailure` có logic đơn giản non-zero→restart; nếu cần phân loại lỗi vĩnh viễn/khả hồi theo mã, phải dùng chính sách Job/controller phù hợp hoặc đưa logic quyết định vào workflow theo tính năng mà cluster hỗ trợ.

## 16. Mã thoát và exception: đừng âm thầm biến thất bại thành `0`

Ví dụ dễ sai:

~~~java
try {
    processFile();
} catch (Exception ex) {
    log.error("Job failed", ex);
}
// main kết thúc bình thường; shell có thể nhận 0!
~~~

Đây là fragment trong một chương trình đã có `processFile`/`log`, không phải source độc lập. Log `ERROR` không được OS tự diễn giải làm exit status.

Có ba cách phù hợp tùy tình huống:

1. **Cho exception lan tới cơ chế xử lý startup thất bại**, đồng thời cấu hình exit code khi cần; kiểm thử status từ tiến trình thật.
2. **Bắt lỗi, ghi state kết quả**, để `ExitCodeGenerator` trả mã non-zero như demo rồi gọi `System.exit(code)`.
3. **Bắt lỗi và trực tiếp chọn status**, sau khi dọn dẹp có kiểm soát, nếu ứng dụng CLI không cần cơ chế Spring exit-code.

Không nên vừa nuốt exception vừa `return` bình thường nếu scheduler/CI cần phát hiện lỗi. Cũng không nên gọi `System.exit` từ tầng repository hoặc service thấp; việc quyết định thoát là trách nhiệm của lớp **điều phối vòng đời tiến trình**.

### Lỗi đồng thời sau khi startup

Nếu main đã trả về và một background thread ném exception, JVM **không nhất thiết tự thoát với mã non-zero**: các luồng khác có thể tiếp tục chạy. Khi viết batch có executor/async task, cần:

- Chờ `Future`/`CompletableFuture`/job completion một cách có timeout.
- Ghi nhận lỗi bất đồng bộ và gộp vào kết quả cuối.
- Không kết thúc `main`/gọi `SpringApplication.exit` trước khi các task bắt buộc hoàn tất.
- Thiết kế cancellation và shutdown khi một task thất bại.

Một dòng stack trace từ một worker thread không phải tự động là mã thoát của toàn process.

## 17. Cách bảo toàn exit code qua Dockerfile và entrypoint

### Tốt: chạy Java làm tiến trình chính

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/exit-code-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tham số runtime như `--fail` được chuyển đến Java main. Tín hiệu dừng đi tới process Java rõ ràng hơn.

### Tốt khi cần wrapper: `exec`

~~~sh
#!/bin/sh
echo "Starting batch JVM"
exec java -jar /app/app.jar "$@"
~~~

Vì `exec` thay thế shell bằng Java, code Java quyết định trạng thái tiến trình chính.

### Dễ sai: bỏ mã Java

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
echo "Finished"
~~~

Wrapper kết thúc ở `echo`; nếu không chủ động `exit "$status"`, có thể khiến kết quả lỗi biến thành `0`.

### Dễ sai: chạy trong background rồi wrapper thoát

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@" &
echo "Started Java in background"
~~~

Nếu shell PID 1 kết thúc, vòng đời container có thể bị kết thúc trong khi Java con chưa hoàn tất, không có mã kết quả đúng. Nếu thực sự cần quản lý nhiều tiến trình, dùng init/supervisor phù hợp và xử lý `wait`, tín hiệu và exit status một cách chủ đích.

## 18. Lỗi vận hành phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Console in `FAILED` nhưng CI xanh | Chỉ ghi log, không trả non-zero | `System.exit`/`SpringApplication.exit`, shell status, script wrapper |
| `SpringApplication.exit` trả `7` nhưng shell nhận `0` | Không chuyển mã cho JVM | Có gọi `System.exit(code)` chưa? |
| Chạy `bootRun` và nhận `1` thay vì `7` | Đó là mã của Gradle task/process | Kiểm tra bằng `java -jar` trực tiếp |
| Dùng `tee` rồi pipeline nhận `0` | Không bật `pipefail` hoặc đọc status của stage cuối | `set -o pipefail`, lưu status ngay |
| PowerShell in `True` thay vì `7` | Đang dùng `$?` như Bash | Dùng `$LASTEXITCODE` |
| Cmd xử lý status sai | `ERRORLEVEL` bị thay đổi bởi command khác | Đọc/copy ngay sau `java` |
| Docker thoát `0` dù Java trả `7` | Entrypoint shell in log và thoát `0` | Dùng exec form hoặc `exit "$status"` |
| Pod restart sau exit `0` | Pod thuộc Deployment với `restartPolicy: Always` | Kiểm tra workload type và Pod spec |
| Job thất bại mã `7` rồi thử lại | `backoffLimit`/restart policy | Kiểm tra Job controller, Pod history |
| `CrashLoopBackOff` bị xem như exit code | Nhầm status/backoff với exit status | Xem `lastState.terminated.exitCode` |
| Thấy `137` và kết luận OOM ngay | `SIGKILL` còn nhiều nguyên nhân | `reason=OOMKilled`, kernel/memory metrics, grace timeout |
| Thấy `143` và báo lỗi code | Có thể Pod nhận `SIGTERM` bình thường | Lý do scale-down/rollout, signal, log shutdown |
| App web trả HTTP `500` nhưng process exit `0` | HTTP và process là hai tầng độc lập | Xem HTTP metrics, liveness/restart riêng |
| Một async worker ném exception, JVM vẫn sống | Lỗi chưa được đưa vào kết quả tiến trình | Await futures, exception handler, supervisor |
| Exit code khác giữa Windows và Linux | Khác OS/shell/process wrapper | Chuẩn hóa môi trường và dải mã |
| `@PreDestroy` không chạy | `SIGKILL`, hook bị tắt, object ngoài container | Phân biệt forced kill với lỗi Spring lifecycle |
| Job thành công nhưng dữ liệu chưa commit | Báo success trước transaction/write durable | Chỉ trả `0` sau tiêu chí hoàn thành xác thực |

## 19. Cần giám sát gì trong production?

Một dashboard hoặc runbook tối thiểu nên liên kết:

- **Mã thoát số nguyên** và **exit reason** từ container/runtime, không chỉ tên trạng thái Pod.
- **Workload kind:** Deployment, StatefulSet, Job, CronJob; mỗi loại có semantics khác.
- **Tên container** và lần restart, vì Pod có thể có nhiều container.
- **Thời điểm start/finish**, version image, commit và command line đã được ẩn dữ liệu nhạy cảm.
- **Log nguyên nhân lỗi** từ application, kèm correlation/job ID.
- **`OOMKilled`, memory/CPU, termination grace**, signal và liveness/readiness events.
- **Số lần retry/backoff**, kết quả cuối của Job và lượng công việc đã xử lý.
- **Kết quả nghiệp vụ** riêng biệt: số record thành công/thất bại, checksum, transaction commit hoặc checkpoint.
- **Thời gian cleanup**, callback stop/destroy và số task còn đang chạy.

Đừng giữ nguyên bí mật, mật khẩu, token hay command line chứa credential trong log chẩn đoán. Exit code là tín hiệu ngắn và an toàn để tổng hợp, nhưng cần kèm ngữ cảnh để suy luận nguyên nhân.

## 20. Quy trình điều tra khi một Job bị Failed

1. **Xác định workload:** đây là Job/CronJob hay Deployment? Job có `restartPolicy` và `backoffLimit` nào?
2. **Lấy đúng Pod/container:** kiểm tra trạng thái hiện tại và lần trước nếu có restart.
3. **Đọc `exitCode` + `reason` + thời điểm:** mã `7` có thể là business failure, `137` có thể do KILL/OOM, `143` có thể do TERM.
4. **Đọc logs đúng lần chạy:** với Pod đang restart, cân nhắc `kubectl logs --previous` nếu container vẫn tồn tại và có lần trước.
5. **Đối chiếu quy ước mã của ứng dụng:** `7` có nghĩa gì theo code/version hiện tại?
6. **Kiểm tra wrapper:** Java có thực sự là PID chính, script có truyền status không, pipeline/Gradle có che mã?
7. **Tìm nguyên nhân gốc:** input, config, dependency, transaction, memory, timeout, signal, pod eviction.
8. **Quyết định retry có điều kiện:** lỗi input không nên retry vô hạn; lỗi tạm thời cần backoff/jitter và idempotency.
9. **Khắc phục và xác nhận:** chạy lại trên input thử nghiệm an toàn, xem cả mã OS và kết quả nghiệp vụ.
10. **Bổ sung kiểm thử hồi quy:** ngăn mã lỗi bị vô tình chuyển thành `0` về sau.

### Mã thoát không phải toàn bộ câu chuyện

Đôi khi job xử lý thành công 99% nhưng trả `0`, trong khi tiêu chí nghiệp vụ yêu cầu xử lý **100%**. Ngược lại, job có thể trả non-zero dù một phần dữ liệu đã commit và cần tránh chạy lại gây trùng. Do đó, phải định nghĩa **điều kiện thành công** và chính sách idempotency/checkpoint theo dữ liệu thật; exit code chỉ là kết luận ngắn để bộ điều phối hành động.

## 21. Bài tập kiểm chứng có thể lặp

### Bài tập A — Xác nhận exit `0`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar
status=$?
test "$status" -eq 0
echo "PASS: zero exit"
~~~

### Bài tập B — Xác nhận exit `7`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
status=$?
test "$status" -eq 7
echo "PASS: business failure exit 7"
~~~

Hai đoạn trên phù hợp khi chạy trong shell tương tác **không bật `set -e`**. Nếu script có `set -e`, đặt lệnh Java trong `if` rồi kiểm tra status có chủ đích, để non-zero không làm script dừng trước bước xác minh.

### Bài tập C — Chứng minh log không phải exit status

Tạm thời **bỏ dòng `System.exit(code)`** trong source demo rồi build lại, chạy nhánh `--fail`. Code có thể in `PROCESS exitCode=7`, nhưng khi `main` trả về bình thường và JVM không còn non-daemon threads, shell có thể nhận `0`. Khôi phục `System.exit(code)` sau thử nghiệm.

Không dùng biến thể sai này trong CI hoặc production.

### Bài tập D — Chứng minh `tee` che lỗi

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee failed.log
echo "pipeline=$?"
~~~

Trong Bash mặc định, có thể thấy `pipeline=0`. Chạy lại trên **một tiến trình Java mới**:

~~~bash
set -o pipefail
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee failed.log
echo "pipeline=$?"
~~~

Nếu `tee` thành công và Java trả `7`, pipeline theo `pipefail` sẽ trả `7`. Nếu các lệnh khác cũng lỗi, cần đọc trạng thái từng stage; không giả định pipeline status luôn đồng nhất với Java.

### Bài tập E — Kiểm tra Job

Triển khai manifest Job ví dụ bằng **image thử nghiệm thật**, sau đó:

~~~bash
kubectl get jobs
kubectl get pods
kubectl describe job exit-code-demo-job
~~~

Đối chiếu status của container và Job. Không dùng cluster production hoặc input thật chỉ để mô phỏng `--fail`; không tạo một Job thất bại không giới hạn retry.

## 22. Câu hỏi tự kiểm tra

1. **Exit code là trạng thái của HTTP request hay tiến trình?** Của tiến trình.
2. **Theo quy ước Bash, `0` thường có nghĩa gì?** Lệnh/tiến trình thành công.
3. **`SpringApplication.exit(context)` có tự gọi `System.exit` không?** Không.
4. **Cách đưa mã từ `ExitCodeGenerator` ra shell?** `System.exit(SpringApplication.exit(context))` hoặc các bước tương đương.
5. **Nếu runner in `ERROR` rồi `main` kết thúc bình thường, shell chắc chắn nhận non-zero?** Không.
6. **Khi nhiều `ExitCodeGenerator` có kết quả khác nhau, Spring Boot chọn theo quy tắc gì?** Mã khác `0` đầu tiên theo thứ tự generator được sắp xếp.
7. **Làm sao kiểm soát thứ tự generator?** `Ordered` hoặc `@Order`.
8. **Trong Bash đọc status qua gì?** `$?`, ngay sau lệnh cần kiểm tra.
9. **Trong PowerShell đọc numeric status Java qua gì?** `$LASTEXITCODE`.
10. **Trong cmd.exe đọc gì?** `ERRORLEVEL`.
11. **Vì sao pipeline `java ... | tee` dễ khiến CI báo xanh sai?** Status mặc định của pipeline thường lấy từ lệnh cuối `tee`.
12. **Muốn giữ non-zero qua Bash pipeline?** Dùng `set -o pipefail` và xử lý status có chủ đích.
13. **`Gradle bootRun` có bảo đảm shell nhận nguyên mã JVM con `7` không?** Không; shell nhận mã của Gradle process.
14. **`restartPolicy: Always` có restart sau exit `0` không?** Có.
15. **`restartPolicy: Never` ở Job có nghĩa Job controller không retry không?** Không; có thể tạo Pod mới theo chính sách Job.
16. **`137` chắc chắn là OOM?** Không; cần kiểm tra `reason` và metrics.
17. **`143` chắc chắn là lỗi ứng dụng?** Không; có thể là `SIGTERM` trong shutdown bình thường.
18. **`CrashLoopBackOff` có phải exit code số không?** Không; là trạng thái/backoff do restart lặp.
19. **`ApplicationReadyEvent` có bảo đảm một batch job hoàn thành nghiệp vụ thành công không?** Không.
20. **HTTP `500` có nghĩa JVM trả exit `1` không?** Không.
21. **Một exception trong background thread có tự khiến JVM non-zero không?** Không nhất thiết.
22. **Khi nào nên trả `0` cho job?** Sau khi các tiêu chí hoàn thành nghiệp vụ đã được xác thực, không chỉ vì context khởi động thành công.
23. **Vì sao `System.exit` không nên nằm trong HTTP handler?** Vì nó dừng toàn bộ JVM, không chỉ request đó.
24. **Khi cần retry một job lỗi, có nên retry mọi non-zero vô hạn không?** Không; phân loại lỗi vĩnh viễn/tạm thời, giới hạn retry và bảo đảm idempotency.

**Kết luận:** Mã thoát tiến trình là **hợp đồng giữa ứng dụng và hệ thống bên ngoài**. Trong Spring Boot, `ExitCodeGenerator` và `SpringApplication.exit(context)` giúp xác định mã từ kết quả công việc và đóng context; `System.exit(code)` chuyển mã tới JVM/OS. Shell đọc `$?` hoặc `$LASTEXITCODE`; Docker/Kubernetes đọc trạng thái kết thúc của tiến trình/container và áp dụng restart/retry theo loại workload. Muốn vận hành đúng, hãy **bảo toàn mã qua wrapper, không đoán nguyên nhân từ 137/143, phân biệt Job với Deployment, và kiểm thử process exit code thật thay vì chỉ kiểm tra log**.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — **SpringApplication: Application Exit** (`ExitCodeGenerator`, `System.exit`, thứ tự generator): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **`SpringApplication.exit` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — **`ExitCodeGenerator` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — **`ExitCodeExceptionMapper` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3.13 — **`ExitCodeEvent` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- GNU Bash Reference Manual — **Exit Status** (0/non-zero, 128+signal, 126/127): https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html
- GNU Bash Reference Manual — **Pipelines** (status cuối pipeline và `pipefail`): https://www.gnu.org/software/bash/manual/html_node/Pipelines.html
- Kubernetes — **Pod Lifecycle**, container restart policy, `CrashLoopBackOff`: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — **Jobs** (retry, `backoffLimit`, Pod failure): https://kubernetes.io/docs/concepts/workloads/controllers/job/
- Kubernetes — **CronJob**: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
- Docker — **Dockerfile ENTRYPOINT** (exec form vs shell form): https://docs.docker.com/reference/dockerfile/#entrypoint
