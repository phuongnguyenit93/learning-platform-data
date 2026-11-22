# Quan sát mã thoát bằng ExitCodeEvent trong Spring Boot

**Module:** Spring Boot Application Runtime → **Mã thoát**. Bài học tập trung vào `org.springframework.boot.ExitCodeEvent` — một Spring application event cho phép các listener **quan sát mã thoát được Spring Boot xác định**, nhất là khi `SpringApplication.exit(...)` hoặc cơ chế xử lý lỗi khởi động tìm được mã thoát khác 0. Bài phân biệt mã được tính, sự kiện được phát, thời điểm đóng `ApplicationContext` và **mã kết thúc thật của tiến trình** mà shell, hệ điều hành hay orchestrator nhìn thấy.

Ví dụ chính dùng **Java 17+**, **Spring Boot 3.5.x**, ứng dụng **command-line không có web server**, Maven và `spring-boot-starter`. Thí nghiệm gồm exit 0, exit 7, startup failure có mã 19, cách quan sát bằng `@EventListener` và kiểm chứng `$?`/`$LASTEXITCODE`. Các phần về nhiều generators, exception mapping và ứng dụng web được đánh dấu rõ để không nhầm snippet với chương trình độc lập.

## 1. Mục tiêu học

Sau bài, người học có thể:

1. Import chính xác `ExitCodeEvent` từ package `org.springframework.boot` và đọc `event.getExitCode()`.
2. Mô tả mối quan hệ giữa `ExitCodeGenerator`, `SpringApplication.exit(context)`, `ExitCodeEvent`, `ApplicationContext.close()` và `System.exit(code)`.
3. Giải thích vì sao **exit code bằng 0 không phát `ExitCodeEvent`** trong đường xử lý thoát tiêu chuẩn của Spring Boot 3.5.
4. Tạo bean `ExitCodeGenerator` và listener `@EventListener(ExitCodeEvent.class)` hoặc listener nhận tham số typed.
5. Quan sát một event nonzero được phát **trước** `ContextClosedEvent` khi gọi `SpringApplication.exit(context)`.
6. Phân biệt **mã được Spring Boot trả về** với **mã do JVM trả cho OS**; biết cần `System.exit(code)` ở CLI.
7. Chạy được ví dụ với các mã 0, 7 và 19; so sánh marker trong console và status của shell.
8. Giải thích `ExitCodeGenerator` trên exception và `ExitCodeExceptionMapper` trong startup failure.
9. Biết nhiều generators được sắp xếp bởi `Ordered`/`@Order` và chọn **mã khác 0 đầu tiên**, không phải mặc định mã lớn nhất.
10. Tránh hiểu nhầm `ExitCodeEvent` với `ApplicationFailedEvent`, `ApplicationReadyEvent`, `ContextClosedEvent` và Unix signal.
11. Biết sự kiện không nhất thiết xuất hiện khi bị `SIGKILL`, JVM crash, `Runtime.halt(...)` hoặc đóng context trực tiếp.
12. Thiết kế log, kiểm thử và policy vận hành phù hợp cho batch job, CLI, Docker, Kubernetes và CI/CD.

**Thông điệp chính:** `ExitCodeEvent` báo **mã thoát mà Spring Boot đang xử lý**; nó không phải một API tự kết thúc JVM và **không bao quát mọi nguyên nhân process dừng**. Để đối chiếu đúng, phải quan sát cả **event** và **exit status thực tế** từ process.

## 2. Phân biệt năm đối tượng dễ bị nhầm

| Đối tượng/API | Vai trò | Điều nó **không** bảo đảm |
|---|---|---|
| `ExitCodeGenerator` | Tính số nguyên mã thoát, có method `getExitCode()` | Không tự đóng context hoặc terminate JVM |
| `SpringApplication.exit(context)` | Gom các generators, tính mã, công bố event khi mã khác 0, rồi đóng context | Không tự gọi `System.exit` để trả mã cho OS |
| `ExitCodeEvent` | Event mang mã đã được xác định; `getExitCode()` trả `int` | Không phải signal OS, không bắt mọi kiểu JVM chết |
| `ContextClosedEvent` | Báo context bắt đầu đóng | Không chứa mã thoát OS, không đảm bảo cleanup đã xong |
| `System.exit(code)` | Yêu cầu JVM kết thúc với status code | Không tự tính mã Spring, không nhất thiết phát `ExitCodeEvent` |

**Thêm hai event cần phân biệt:**

- `ApplicationReadyEvent`: Boot đã hoàn thành startup (bao gồm runners) trong đường chạy thành công; **không có nghĩa đang thoát**.
- `ApplicationFailedEvent`: Boot khởi động thất bại; **không đồng nghĩa mặc định luôn có `ExitCodeEvent`**. Exit event chỉ có khi code path tìm được mã khác 0 và có ngữ cảnh phù hợp để publish. Nếu lỗi xảy ra cực sớm, bean listener có thể chưa tồn tại.

### 2.1. Package đúng của ExitCodeEvent

~~~java
import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
~~~

**Không import** `ExitCodeEvent` từ `org.springframework.boot.context.event`. Namespace `org.springframework.boot.context.event` chứa nhiều Boot lifecycle events khác như `ApplicationReadyEvent`/`ApplicationFailedEvent`, nhưng `ExitCodeEvent` nằm trực tiếp trong `org.springframework.boot`.

`ExitCodeEvent` là một `org.springframework.context.ApplicationEvent`. Nó có constructor nhận `source` và mã `int`, và method `getExitCode()`. Trong đường `SpringApplication.exit(context)`, source do Boot dùng là application context.

## 3. Cơ chế chuẩn khi đóng một Spring Boot CLI application

Luồng khi startup thành công và code chủ động quyết định thoát:

~~~text
public static void main(...)
    |
    v
SpringApplication.run(...)
    |
    +-- ApplicationContext refresh
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    |
    v
SpringApplication.exit(context)
    |
    +-- lấy ExitCodeGenerator beans trong context
    +-- lấy ExitCodeGenerator truyền vào exit(...) nếu có
    +-- sắp xếp theo Ordered / @Order
    +-- chọn exit code khác 0 đầu tiên (nếu có)
    |
    +-- nếu code != 0:
    |      context.publishEvent(new ExitCodeEvent(context, code))
    |         -> @EventListener / ApplicationListener quan sát
    |
    +-- close(context)
    |      -> ContextClosedEvent
    |      -> SmartLifecycle stop / bean destruction
    |
    v
SpringApplication.exit trả về int code
    |
    v
System.exit(code)
    |
    v
OS / shell nhận process exit status
~~~

**Quan trọng trong Spring Boot 3.5:** `ExitCodeEvent` chỉ được publish nếu mã được xác định **khác 0**. Khi mọi `ExitCodeGenerator` trả 0, `SpringApplication.exit(...)` vẫn đóng context và trả 0, nhưng **không có `ExitCodeEvent(0)`** theo đường chuẩn. Vì vậy không dùng số `ExitCodeEvent` làm bộ đếm mọi lần ứng dụng kết thúc.

**Thứ tự event so với close:** Trong đường `SpringApplication.exit(context)` có mã khác 0, event exit được phát **trước** khi Boot gọi close context. Listener thuộc context còn có cơ hội ghi log mã. Sau đó mới có `ContextClosedEvent` và các bước stop/destroy. Đừng thực hiện thao tác cleanup phức tạp ngay trong listener exit; lifecycle shutdown đã có các hook riêng.

### 3.1. SpringApplication.exit chưa phải System.exit

Đoạn code:

~~~java
int exitCode = SpringApplication.exit(context);
System.out.println("exit code = " + exitCode);
~~~

**chưa trả mã này cho parent process**. `SpringApplication.exit` đóng context rồi trả về số nguyên. Nếu phương thức `main` chỉ return bình thường, JVM thường kết thúc với **0** khi không có lỗi/bất thường khác, dù bạn vừa in `exit code = 7`. Một lệnh `System.exit(exitCode)` (hoặc exit mechanism tương đương của entrypoint) mới chuyển status mong muốn cho OS.

Trong ứng dụng web phục vụ liên tục, không tự gọi `SpringApplication.exit(...)`/`System.exit(...)` ở cuối `main` ngay sau `run`, vì nó sẽ đóng server vừa khởi động. Mẫu này đặc biệt phù hợp **CLI/batch job có điểm kết thúc rõ ràng**.

### 3.2. ExitCodeEvent không phải “listener thay đổi mã thoát”

`getExitCode()` chỉ đọc giá trị của event; bạn không thể sửa nó bằng setter để thay kết quả. Nếu muốn thay đổi mã thoát, hãy sửa logic `ExitCodeGenerator`, `ExitCodeExceptionMapper` hoặc code truyền vào `SpringApplication.exit(...)` **trước khi event được phát**. Event chỉ là lớp quan sát.

Tránh tự publish `new ExitCodeEvent(this, 9)` rồi tuyên bố process đã thoát 9: đó chỉ là event do chính bạn phát; nó **không** khiến Boot thực hiện exit lifecycle hoặc `System.exit`. Để test hành vi framework, cần đi qua API `SpringApplication.exit` thật.

## 4. Mã thoát 0, nonzero và giới hạn quan sát

Thông lệ cho một CLI/batch process:

| Mã | Diễn giải theo quy ước ứng dụng | Event theo `SpringApplication.exit` |
|---:|---|---|
| `0` | Chạy xong thành công | **Không** phát `ExitCodeEvent` |
| `7` | Lỗi/điều kiện nghiệp vụ mà lab chủ động lựa chọn | Phát `ExitCodeEvent` có code 7 |
| `19` | Lỗi khởi động có mapping trong lab | Có thể phát event nếu Boot tìm được mã 19 và context có thể publish |
| `1` | Mã nonzero thường dùng cho lỗi chung | Phát event nếu đến từ generator hợp lệ trong đường exit |
| `130` / `143` | Thường là convention shell cho signal interrupt/TERM trong môi trường Unix | **Không suy** có ExitCodeEvent từ các con số đó |
| `137` | Thường dùng mô tả process bị kill/SIGKILL trong container Unix | **Không** được lấy làm bằng chứng listener exit đã chạy |

Các mã **7 và 19 là quy ước của riêng bài lab**, không phải bảng mã do Spring Boot quy định. Khi thiết kế sản phẩm, định nghĩa mã theo contract với scheduler/CI/CD và tránh xung đột mã mà môi trường dùng cho signals. Trên nhiều Unix shells, exit status hiệu dụng chỉ có 8 bit; việc trả mã âm hoặc số quá 255 có thể bị ánh xạ/truncated, vì vậy bài lab chỉ dùng các số dương nhỏ hơn 128.

**Không có event** chưa chắc là shutdown thất bại: với mã thành công 0, **không phát event chính là hành vi bình thường**.

## 5. Dự án thực hành chạy được: Java 17 + Spring Boot 3.5

### 5.1. Tạo project

Tạo Maven project có Java 17, Spring Boot 3.5.x, group `com.example`, artifact `exit-code-event-lab`, package `com.example.exitcodelab`. Đây là ứng dụng command-line, **không cần Spring Web hay Actuator**; dependency `spring-boot-starter` là đủ.

Nếu dùng Spring Initializr, giữ Maven Wrapper `mvnw`, `mvnw.cmd` và tạo/cập nhật `pom.xml` theo dependency tương đương dưới đây. Có thể dùng Maven đã cài thay cho Maven Wrapper.

Cấu trúc:

~~~text
exit-code-event-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/exitcodelab/
    ExitCodeEventLabApplication.java
    ExitEventObserver.java
    DemoStartupException.java
  src/main/resources/application.properties
~~~

### 5.2. pom.xml tối thiểu

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>exit-code-event-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>exit-code-event-lab</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

Spring Boot 3.5.16 chỉ là **một bản 3.5.x cụ thể** để ví dụ có dependency pin nhất quán với tài liệu; nếu kho Maven của tổ chức sử dụng bản 3.5.x khác, giữ đúng phiên bản được phê duyệt và đối chiếu behavior tương ứng. Java 17 đủ cho các API trong ví dụ. Không tự thêm starter web chỉ để quan sát exit code.

### 5.3. Main: khởi động, tính mã, đóng context, trả mã cho OS

File `src/main/java/com/example/exitcodelab/ExitCodeEventLabApplication.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ExitCodeEventLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ExitCodeEventLabApplication.class, args);

        int code = SpringApplication.exit(context);
        System.out.println("LAB_EXIT_RETURNED=" + code);

        // Day la diem duy nhat dua Spring exit code ra OS.
        System.exit(code);
    }

    @Bean
    ExitCodeGenerator configuredExitCode(Environment env) {
        int configured = env.getProperty(
                "lab.exit-code", Integer.class, 0);

        return () -> configured;
    }

    @Bean
    CommandLineRunner demoRunner(Environment env) {
        return args -> {
            System.out.println("LAB_RUNNER_BEGIN");

            boolean fail = env.getProperty(
                    "lab.fail-startup", Boolean.class, false);

            if (fail) {
                throw new DemoStartupException(
                        "intentional startup failure");
            }

            System.out.println("LAB_RUNNER_DONE");
        };
    }
}
~~~

**Chú giải:**

1. `SpringApplication.run(...)` dựng context, tạo bean listener/generator và chạy `CommandLineRunner`. Trong luồng thành công, nó trả context cho `main`.
2. `configuredExitCode` là bean `ExitCodeGenerator`, trả giá trị từ `lab.exit-code`. Mặc định 0, có thể đổi qua `--lab.exit-code=7`.
3. `SpringApplication.exit(context)` dùng generator bean, phát `ExitCodeEvent` **chỉ khi code khác 0**, rồi đóng context và trả mã.
4. `LAB_EXIT_RETURNED` xác nhận kết quả Java helper **sau khi đóng context**.
5. `System.exit(code)` đưa kết quả đó về shell. Không đưa `System.exit` vào controller, bean callback, listener hoặc unit test.
6. Nếu `lab.fail-startup=true`, runner ném `DemoStartupException` và `SpringApplication.run(...)` không trả về context thành công; dòng `LAB_EXIT_RETURNED` trong `main` **không chạy**. Boot có đường xử lý startup failure riêng mà bài sẽ quan sát ở mục 8.

**Lưu ý:** `System.exit(0)` vẫn yêu cầu JVM kết thúc; `System.exit(7)` cho OS thấy nonzero nếu môi trường không có wrapper làm thay đổi trạng thái. Các logger/framework shutdown hooks có thể in thêm dòng không liên quan giữa những marker.

### 5.4. Listener: nhận ExitCodeEvent và ContextClosedEvent

File `src/main/java/com/example/exitcodelab/ExitEventObserver.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitEventObserver {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println(
                "LAB_EXIT_EVENT=" + event.getExitCode());
        System.out.println(
                "LAB_EXIT_SOURCE_IS_CONTEXT="
                + (event.getSource() instanceof ApplicationContext));
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("LAB_APPLICATION_READY");
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("LAB_CONTEXT_CLOSED");
    }
}
~~~

Khi Spring quản lý bean này, `@EventListener` tạo method-based event listeners tương ứng. Method `onExitCode(ExitCodeEvent event)` đọc mã bằng `getExitCode()`. `ApplicationReadyEvent` được in để tách startup thành công với exit; `ContextClosedEvent` chứng minh context đã bắt đầu đóng.

Trong đường exit chủ động, thứ tự cần kiểm:

~~~text
LAB_APPLICATION_READY
LAB_EXIT_EVENT=7
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=7
~~~

`ApplicationReadyEvent` xuất hiện trước `SpringApplication.exit(...)` vì `run(...)` đã hoàn tất. Khi code khác 0, exit event đến trước close event. Kết quả in thêm log framework có thể xen vào, nhưng thứ tự tương đối giữa marker của lab là bằng chứng chính.

Không phụ thuộc vào thời điểm flush của log async trong sản phẩm để thiết lập semantics; ở lab dùng `System.out.println` để quan sát trực tiếp. Production nên dùng logger/structured telemetry với thời gian và correlation ID.

### 5.5. Exception mang exit code riêng

File `src/main/java/com/example/exitcodelab/DemoStartupException.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeGenerator;

public final class DemoStartupException
        extends RuntimeException implements ExitCodeGenerator {

    public DemoStartupException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 19;
    }
}
~~~

Khi runner ném exception này, lỗi startup chứa một `ExitCodeGenerator`. Spring Boot có logic tìm mã từ exception (bao gồm cause chain trong đường xử lý phù hợp), và có thể publish `ExitCodeEvent` mang mã **19** trước khi đóng context nếu context đã tồn tại và event publisher khả dụng. Vì lỗi xảy ra ở `CommandLineRunner` **sau refresh**, bean observer đã được tạo trong dự án mẫu.

Đây là đường **startup failure**, không cần gọi `SpringApplication.exit(context)` ở cuối main vì `run()` đã thất bại. Không tự `catch (Exception ex) { System.exit(0); }` — hành vi đó che giấu lỗi và làm CI/CD hiểu job thành công.

### 5.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=exit-code-event-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

lab.exit-code=0
lab.fail-startup=false
~~~

Ứng dụng không mở web server. `logging.level.root=ERROR` giảm log để dễ quan sát marker, nhưng khi startup fail bạn vẫn có thể thấy stack trace/error logs do Boot và JVM in ra. Việc Spring Boot kết thúc đúng mã **không** phụ thuộc vào cài đặt logger.

## 6. Thử nghiệm A — Exit code 0, không có ExitCodeEvent

### 6.1. Build JAR

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
~~~

Nếu không dùng Maven Wrapper, `mvn clean package` cũng hợp lệ khi máy có Maven tương thích. Đường dẫn JAR của `pom.xml` trên là `target/exit-code-event-lab-0.0.1-SNAPSHOT.jar`.

### 6.2. Chạy và lấy status ở Unix shell

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar
echo $?
~~~

Các **marker chính** kỳ vọng (ngoài các log khác):

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=0
~~~

Lệnh `echo $?` chạy **ngay sau lệnh java** sẽ in:

~~~text
0
~~~

**Điểm cần xác nhận:** **không xuất hiện dòng `LAB_EXIT_EVENT=0`** vì Spring Boot 3.5 không publish `ExitCodeEvent` khi mã được xác định là 0. Không xem thiếu event là bug hoặc listener bị đăng ký sai trong thí nghiệm A.

### 6.3. Chạy và lấy status trong PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
~~~

PowerShell sẽ hiển thị `0` trong trường hợp chạy thành công và Java process trả 0. `$LASTEXITCODE` là trạng thái process native gần nhất; nếu chạy lệnh native khác trước khi đọc, nó có thể thay đổi. Không lấy `$?` của PowerShell làm đối chứng trực tiếp với mã số 7: `$?` diễn giải thành công/thất bại của command theo semantics shell, còn `$LASTEXITCODE` giữ mã số cụ thể.

## 7. Thử nghiệm B — Exit code 7, có ExitCodeEvent

### 7.1. Linux/macOS

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
echo $?
~~~

Các marker quan trọng kỳ vọng:

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY
LAB_EXIT_EVENT=7
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=7
~~~

Lệnh `echo $?` **ngay sau java**:

~~~text
7
~~~

Phép thử này đối chiếu được **ba lớp**:

1. Generator đã trả **7** cho `SpringApplication.exit`.
2. Listener đã quan sát **`ExitCodeEvent.getExitCode()==7`** trước khi context close.
3. `System.exit(7)` khiến shell nhận **7**.

Không chỉ nhìn marker sự kiện mà khẳng định OS code. Nếu chương trình bỏ `System.exit(code)`, rất có thể vẫn thấy event và `LAB_EXIT_RETURNED=7` nhưng shell lại nhận 0 khi `main` return bình thường.

### 7.2. Windows PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
$LASTEXITCODE
~~~

Kết quả số mong đợi: `7`. Dùng `java -jar` thay vì chỉ kiểm lệnh `./mvnw spring-boot:run` vì Maven plugin và wrapper có cơ chế xử lý process/failure status riêng, có thể làm việc xác minh raw OS code khó trực tiếp hơn.

### 7.3. Đổi mã sang 42

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=42
echo $?
~~~

Marker `LAB_EXIT_EVENT=42`, `LAB_EXIT_RETURNED=42` và shell status `42` là kết quả dự kiến nếu không có generator khác can thiệp. Bài này không gán ý nghĩa hệ thống đặc biệt cho 42.

## 8. Thử nghiệm C — Startup failure mang ExitCodeGenerator

Chạy trong một tiến trình mới:

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.fail-startup=true
echo $?
~~~

Phần marker kỳ vọng:

~~~text
LAB_RUNNER_BEGIN
LAB_EXIT_EVENT=19
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
~~~

Ngoài ra sẽ có stack trace hoặc log lỗi chứa `DemoStartupException` / `intentional startup failure`. **Không** có `LAB_RUNNER_DONE`, `LAB_APPLICATION_READY` hoặc `LAB_EXIT_RETURNED` cho lượt khởi động thất bại đó.

Trong mô hình khởi động trực tiếp bằng `java -jar` của Spring Boot 3.5, mã thoát nonzero đã được mapper/exception generator ghi nhận thường được Spring Boot chuyển tới exception handler; dự kiến OS status theo `getExitCode()` là **19**, nhưng phải xác minh bằng `echo $?`/`$LASTEXITCODE` trên JDK, launcher và môi trường thật. Nếu một wrapper bắt lại exception, thay đổi exit code hoặc chạy thành child process, status được báo bên ngoài có thể khác.

**Tại sao vẫn có thể thấy ExitCodeEvent khi app fail?** Vì exception phát sinh **sau khi context đã refresh** trong runner, nên Boot còn cơ hội publish event với exit code khác 0 và observer bean đã tồn tại. Nếu failure xảy ra sớm hơn — lỗi classpath, context chưa tạo, lỗi khởi tạo bean trước event method registration — **không thể hứa** cùng listener bean luôn thấy event.

### 8.1. ApplicationFailedEvent và ExitCodeEvent khác nhau

| Sự kiện | Kích hoạt khi | Có mã thoát `int`? |
|---|---|---|
| `ApplicationFailedEvent` | SpringApplication khởi động thất bại | Không cung cấp `getExitCode()` như ExitCodeEvent |
| `ExitCodeEvent` | Boot xác định exit code khác 0 và publish được | Có `getExitCode()` |
| `ApplicationReadyEvent` | Startup thành công và runners hoàn tất | Không mang mã thoát |
| `ContextClosedEvent` | Context bước vào close lifecycle | Không mang mã thoát |

Một startup failure có thể tạo ra cả `ExitCodeEvent` lẫn `ApplicationFailedEvent`, nhưng **không phải mọi failure** đều có cả hai. Muốn lấy root cause, dùng `ApplicationFailedEvent.getException()` hoặc exception logs; muốn quan sát mã đã tính, dùng `ExitCodeEvent.getExitCode()`. Không ép một listener thay vai trò của listener kia.

## 9. Đăng ký listener bằng ApplicationListener thay cho @EventListener

Trong dự án mẫu, `@EventListener` hoạt động vì bean observer đã được Spring tạo. Nếu cần listener độc lập, có thể implement interface:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyExitCodeLogger
        implements ApplicationListener<ExitCodeEvent> {

    @Override
    public void onApplicationEvent(ExitCodeEvent event) {
        System.out.println(
                "LAB_EARLY_EXIT_CODE=" + event.getExitCode());
    }
}
~~~

Đây là **một file Java bổ sung hoàn chỉnh**, dùng nếu bạn muốn thử registration sớm. Để đăng ký trước khi gọi `run`, thay phần khởi động trong `main` (bản lab mở rộng):

~~~java
SpringApplication app =
        new SpringApplication(ExitCodeEventLabApplication.class);
app.addListeners(new EarlyExitCodeLogger());

ConfigurableApplicationContext context = app.run(args);
int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là **snippet thay thế thân `main`**, không tạo thêm method `main` thứ hai. Khi dùng nó, listener sớm có thể nhận event dù một bean listener trong context chưa kịp được đăng ký, **miễn Boot có publisher và thực sự phát event**. Nếu exception xảy ra trước cả bước có application context hoặc Boot không tạo event, listener đăng ký sớm cũng không thể quan sát một event không tồn tại.

**Cảnh báo trùng đăng ký:** Nếu để `EarlyExitCodeLogger` dưới `@Component` đồng thời `new` rồi `app.addListeners(...)`, bạn có thể tạo hai listener instances cho cùng event. Vì bài chỉ muốn quan sát mã thoát, chọn một đường registration phù hợp; nếu dùng cả hai, log phải có nhãn rõ để không hiểu nhầm event được phát hai lần.

### 9.1. @EventListener vs API vs factories

| Cách | Ví dụ | Phù hợp |
|---|---|---|
| Bean method listener | `@EventListener void onExit(ExitCodeEvent e)` | Context đã refresh, logic cần DI |
| Interface listener bean | `@Component implements ApplicationListener<ExitCodeEvent>` | Bean tồn tại trong context |
| SpringApplication API | `app.addListeners(new EarlyExitCodeLogger())` | Registration trước startup, ít phụ thuộc bean |
| `META-INF/spring.factories` | Key `org.springframework.context.ApplicationListener` | Thư viện muốn auto-register listener |
| Context hierarchy | Parent/child contexts | Cần lọc source/context nếu cùng event đi lên parent |

`ExitCodeEvent` không nằm trong chuỗi các `SpringApplicationEvent` của phase startup thông thường; đây là một event gắn với **tính mã thoát**. Nó có thể được xử lý qua Spring application event publishing mechanism, nhưng không vì thế mà mọi context hoặc mọi shutdown đều phải phát nó.

### 9.2. Đừng làm I/O nặng trong ExitCodeEvent listener

Event listeners mặc định thường xử lý đồng bộ với publisher. Nếu listener gọi API ngoài chậm hoặc ném exception, thời gian thoát và thậm chí mã exit xử lý có thể bị ảnh hưởng. Dùng listener cho việc **log/metrics nhẹ, ghi nhận trạng thái đã tính** và correlation; việc flush/ack transaction cần nằm trong lifecycle/resource owner phù hợp, không trì hoãn vô hạn.

Nếu logging/metrics backend async, `System.exit` sau đó có thể cắt ngang buffer chưa flush. Đừng đảm bảo 100% mọi log sẽ được gửi đến remote storage chỉ vì code đã gọi `println` hoặc logger. Cần thiết kế flush bounded, capture bởi process supervisor, và kiểm external outcome riêng.

## 10. Nhiều ExitCodeGenerator: thứ tự và mã nonzero đầu tiên

Spring Boot 3.5 dùng các `ExitCodeGenerator` được truyền trực tiếp cho `SpringApplication.exit(context, generators...)` **và** các bean cùng interface trong context. Chúng được sắp theo `Ordered` hoặc annotation `@Order`. **Mã khác 0 đầu tiên trong thứ tự ưu tiên** được chọn.

Vì thế:

- `getOrder()` **nhỏ hơn** là ưu tiên **cao hơn**.
- Generator trả **0** nghĩa là “không áp mã lỗi”; framework có thể xét tiếp generator khác.
- Không mặc định chọn số lớn nhất, số âm nhất, hay “generator được tạo sau cùng”.
- Với các generators có cùng priority, không dựa vào thứ tự bất định để xây contract nghiệp vụ.

### 10.1. Ví dụ hai generators có ưu tiên xác định

Đây là **mẫu cấu hình thay thế**, không nên paste vào project mẫu khi còn bean `configuredExitCode` nếu bạn muốn suy luận đúng output mà không kiểm thêm priority:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class OrderedExitCodes {

    @Bean
    ExitCodeGenerator firstGenerator() {
        return new FixedCode(0, -100);
    }

    @Bean
    ExitCodeGenerator secondGenerator() {
        return new FixedCode(12, 100);
    }

    private record FixedCode(int code, int order)
            implements ExitCodeGenerator, Ordered {

        @Override
        public int getExitCode() {
            return code;
        }

        @Override
        public int getOrder() {
            return order;
        }
    }
}
~~~

Lớp này biên dịch với Java 17 và Spring Boot dependencies khi đặt đúng package. Khi **chỉ có hai generators** của cấu hình trên, generator order -100 trả 0 nên Boot xét tiếp generator order 100 trả **12**. Kết quả exit và event là 12. Nếu đổi `firstGenerator()` trả 5, nó sẽ thắng và kết quả là 5. Điều đó chứng minh **thứ tự + first nonzero**, không phải so sánh độ lớn mã.

Trong một cấu hình production, thay vì có nhiều generators tranh nhau cho cùng một business result, hãy xác định rõ một owner tổng hợp kết quả, chính sách precedence và đơn vị test tương ứng.

### 10.2. Generator được truyền trực tiếp cho SpringApplication.exit

Spring Boot cho phép truyền thêm generator:

~~~java
int code = SpringApplication.exit(context, () -> 9);
System.exit(code);
~~~

Đây là snippet thay hai dòng cuối trong `main` (sau `run`). Nếu bean generator của lab trả **0**, generator truyền trực tiếp có mã 9 sẽ cho kết quả **9**, event 9 và OS status 9. Nếu còn những generators nonzero khác, kết quả phụ thuộc ordering và logic first nonzero, **không** được khẳng định tham số explicit luôn thắng bean trong mọi cấu hình.

### 10.3. Mã nonzero nhưng callback listener ném lỗi

`SpringApplication.exit` cố trả một mã dù một số bước đóng gây exception; Javadoc nêu rằng nó không ném lỗi ra ngoài theo contract thông thường nhưng có thể in stack trace và sử dụng fallback tùy tình huống. Đừng coi listener là nơi an toàn để thực hiện một hành động có thể ném exception tùy ý. Khi viết mã vận hành, tách tính exit code khỏi một bước báo cáo có thể fail, và kiểm tra return code thực từ `SpringApplication.exit`.

## 11. ExitCodeExceptionMapper: ánh xạ lỗi khởi động

`org.springframework.boot.ExitCodeExceptionMapper` là functional interface:

~~~java
int getExitCode(Throwable exception);
~~~

Nó giúp map một exception thành mã thoát, thường khi `SpringApplication.run(...)` fail. Ví dụ thêm bean sau vào configuration của ứng dụng nếu muốn ánh xạ `IllegalArgumentException` thành 64:

~~~java
@Bean
ExitCodeExceptionMapper argumentFailureMapper() {
    return failure -> {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (current instanceof IllegalArgumentException) {
                return 64;
            }
        }
        return 0;
    };
}
~~~

Đây là **method snippet**, cần import `org.springframework.boot.ExitCodeExceptionMapper`, đặt trong một Spring configuration class. `getExitCode(...)` trả 0 khi không nhận ra lỗi, để quy tắc khác xử lý. Loop qua `getCause()` hữu ích vì Spring có thể bọc root exception trong lớp khác.

**Khác nhau:**

| Công cụ | Cách cung cấp mã | Thời điểm phổ biến |
|---|---|---|
| `ExitCodeGenerator` bean | `getExitCode()` không có tham số | Đường thoát chủ động qua `SpringApplication.exit(...)` |
| Exception `implements ExitCodeGenerator` | Exception tự mang `getExitCode()` | Startup failure/exception cause chain |
| `ExitCodeExceptionMapper` bean | `getExitCode(Throwable exception)` | Mapping nguyên nhân fail khi Boot xử lý lỗi |
| `ExitCodeEvent` | `getExitCode()` để **đọc** mã đã được xác định | Quan sát nonzero code do Boot publish |

Trong đường xử lý startup failure, nếu mapper beans đã có và tìm được mã khác 0, Boot có thể dùng mã từ mapper. Nếu không, framework có thể tìm `ExitCodeGenerator` ở exception/cause. Tuy nhiên, **nếu context chưa active hoặc chưa có mapper bean**, mapping dựa bean có thể không sẵn có; exception trực tiếp implement `ExitCodeGenerator` vẫn có thể được xét khi phù hợp.

Không dùng `ExitCodeExceptionMapper` để “bắt và nuốt” exception. Nó chọn status báo lỗi; root cause cần được log/analyze độc lập. Nếu một startup failure khiến main không return, đừng kỳ vọng đoạn `SpringApplication.exit(context)` sau `run(...)` vẫn được chạy.

## 12. Một event quan sát được không bảo đảm mọi lần process kết thúc

### 12.1. Những trường hợp không phát event theo đường chuẩn

| Hành động | Có nhất thiết có ExitCodeEvent không? | Lý do |
|---|---|---|
| `SpringApplication.exit(context)`, mã 0 | **Không** | Branch không publish khi exitCode == 0 |
| `SpringApplication.exit(context)`, mã 7 | **Có trong luồng bình thường**, nếu publisher hoạt động | Branch nonzero publish event trước close |
| `context.close()` trực tiếp | **Không** | Close chỉ đóng context; không tính exit code |
| `System.exit(7)` trực tiếp mà không gọi `SpringApplication.exit` | **Không** | JVM exit không đồng nghĩa Boot công bố exit event |
| `Runtime.getRuntime().halt(7)` | **Không bảo đảm** | Bỏ qua hooks/cleanup bình thường |
| JVM bị `SIGKILL` | **Không** có cơ chế Java listener đáng tin | Process bị hủy cưỡng bức |
| Startup fail trước khi context có event publisher | **Không bảo đảm** | Context/listeners có thể chưa tồn tại |
| Startup fail trong runner, exception generator nonzero | **Có thể quan sát** trong lab | Context đã refresh và Boot xử lý exit code |
| Graceful SIGTERM với shutdown hook | **Không tự động tương đương SpringApplication.exit** | Context đóng, không nhất thiết tính generator |
| Kubernetes/Docker container bị kill do timeout/OOM | **Không suy ra event đã phát** | OS/runtime có mã thoát riêng |

### 12.2. Vì sao ExitCodeEvent không xuất hiện khi process bị kill?

Application events là cơ chế **bên trong JVM**. Nếu process bị kill cưỡng bức, kernel hoặc container runtime có thể gán exit status do signal, nhưng không có thời gian để Spring publish event. Do đó không thể dùng listener này làm nguồn duy nhất cho thống kê mọi lần crash/restart.

Một hệ thống observability đầy đủ nên thu thập:

- Log `ExitCodeEvent` khi application tự xác định nonzero code.
- `ApplicationFailedEvent` và root cause khi startup fail.
- `ContextClosedEvent` / shutdown logs cho lifecycle bình thường.
- Exit code và termination reason ở **process supervisor, Docker/Kubernetes, CI/CD hoặc systemd**.
- OOM/restart/health probe và node/system events ở hạ tầng.
- Business job state/transaction outcome từ store bền vững.

### 12.3. ExitCodeEvent không thay thế ContextClosedEvent

`ExitCodeEvent` tập trung vào **quyết định mã nonzero**; `ContextClosedEvent` tập trung vào **context close lifecycle**. Trong demo code=7, cả hai xuất hiện; trong demo code=0, chỉ thấy close. Trong một shutdown do SIGTERM, có thể thấy close event mà không thấy exit event. Đây là hành vi hợp lệ, không phải mất log.

## 13. Vận hành CLI, Docker, Kubernetes Job và CI/CD

### 13.1. CLI hoặc scheduled batch job

Với command-line job chạy xong rồi kết thúc, kết hợp `ExitCodeGenerator` với `SpringApplication.exit` và `System.exit` để parent process nhận status có ý nghĩa. Quy ước:

- 0: hoàn thành.
- 7: kết quả nghiệp vụ yêu cầu upstream xử lý khác.
- 19: không thể khởi động/không đạt điều kiện ban đầu.

Đây là **quy ước riêng của bài lab**; môi trường sản xuất cần định nghĩa contract rõ cho scheduler, shell scripts và monitoring. Nếu một phần job thành công và một phần thất bại, cần chính sách tổng hợp chứ không chỉ lấy số ngẫu nhiên từ listener.

### 13.2. Bash/script pipeline

Một script kiểm soát kết quả có thể chạy:

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
status=$?
printf 'Observed Java process status: %s\n' "$status"

if [ "$status" -ne 0 ]; then
  echo "Job did not succeed"
  exit "$status"
fi
~~~

Script cần đọc `$?` **ngay sau Java**, không sau `echo` hoặc một lệnh khác. Nếu chạy qua pipe `java ... | tee log.txt`, một số shells trả status của `tee` trừ khi dùng `pipefail` hoặc `PIPESTATUS` tương ứng; đừng dùng output logging pipeline để chứng minh raw Java exit status mà không xử lý case đó.

### 13.3. Windows PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
$code = $LASTEXITCODE
Write-Host "Observed Java process status: $code"

if ($code -ne 0) {
    exit $code
}
~~~

PowerShell có semantics riêng cho native process và ErrorAction/terminating errors, vì vậy quan sát `$LASTEXITCODE` là cách minh bạch để lấy mã `System.exit` của Java. Đừng nhầm mã thoát của Maven Wrapper, IDE và raw JAR nếu launcher trung gian làm thay đổi nó.

### 13.4. Docker / Kubernetes

Khi Java là process chính của container, mã exit của Java thường được container runtime ghi nhận. Kubernetes Job controller dựa trên exit status/restart policy để xác định container termination và retry policy. **ExitCodeEvent của Spring Boot không được hạ tầng tự đọc trực tiếp**; hạ tầng chỉ thấy process exit status mà runtime ghi nhận.

Vì vậy nếu code chỉ gọi `SpringApplication.exit(context)` rồi bỏ qua returned int, Kubernetes có thể quan sát status 0 và coi job thành công, mặc dù log bên trong ghi exit code 7. Đó là lý do `System.exit(code)` đặc biệt quan trọng với batch container.

Tại Kubernetes, đối chiếu container termination reason/code từ Pod status, ví dụ field `status.containerStatuses[].state.terminated.exitCode` hoặc `lastState.terminated.exitCode` tùy container còn ở trạng thái terminated hay đã restart. Đừng kết luận từ mã 137/143 rằng Boot đã publish một `ExitCodeEvent`; những mã này có thể đến từ signal/container runtime chứ không phải generator.

### 13.5. Ứng dụng web phục vụ dài hạn

Đối với REST API chạy 24/7, không nên để cuối main có:

~~~java
System.exit(SpringApplication.exit(
        SpringApplication.run(WebApplication.class, args)));
~~~

Đây là **snippet phản ví dụ**; `WebApplication` chỉ là tên minh họa không thuộc lab CLI. Nó sẽ đóng context ngay khi `run` trở về, nên web service không còn phục vụ như mong muốn. Với server lâu dài, dùng shutdown lifecycle, readiness, actuator và supervisor. Chỉ gọi `SpringApplication.exit`/`System.exit` khi nghiệp vụ hoặc operator thực sự chủ động yêu cầu process kết thúc, và phải thiết kế authorization, draining, resource cleanup.

## 14. Kiểm thử đúng cách mà không giết tiến trình test

### 14.1. Phép thử end-to-end qua process riêng

Để kiểm OS exit status, dùng **tiến trình Java độc lập** từ shell hoặc integration test harness. Đây là phép thử phù hợp nhất cho `System.exit` vì không cần can thiệp/giả lập `SecurityManager` (đã thay đổi mạnh qua các phiên bản Java).

Ma trận:

| Chạy JAR | Event marker | Context close | Helper returned | Process status |
|---|---|---|---|---:|
| Mặc định | Không có `LAB_EXIT_EVENT` | Có | 0 | 0 |
| `--lab.exit-code=7` | `LAB_EXIT_EVENT=7` | Có | 7 | 7 |
| `--lab.exit-code=42` | `LAB_EXIT_EVENT=42` | Có | 42 | 42 |
| `--lab.fail-startup=true` | `LAB_EXIT_EVENT=19` khi observer nhận được | Có trong lab sau refresh | Không có | Thường 19; đo thực tế |

Các assertions về OS status áp dụng khi chạy trực tiếp `java -jar` trên môi trường chuẩn, không có launcher trung gian biến đổi status. Nếu startup fail ở phase sớm, test phải điều chỉnh kỳ vọng event/close theo giai đoạn lỗi.

### 14.2. Unit/integration test trong cùng JVM

Nếu test class cần kiểm event nhưng **không được giết runner JUnit**, đừng gọi `System.exit`. Có thể tự tạo `ApplicationContext`, đăng ký một listener ghi mã, gọi `SpringApplication.exit(context)`, rồi assert returned code và danh sách events. **Chú ý:** `SpringApplication.exit` sẽ **đóng context**; không gọi nó lên một `@SpringBootTest` context đang được test suite cache để dùng lại.

Một cách là tạo context riêng bằng `SpringApplicationBuilder` với `WebApplicationType.NONE` và cho test sở hữu vòng đời đó. Khi cần kiểm shell status, chạy Java subprocess và đọc exit value. Đừng “test” bằng cách chỉ publish một `ExitCodeEvent` tự tạo: nó không chứng minh Boot có code path nonzero hay helper close.

### 14.3. Assertion đúng phạm vi

- Event code đúng chỉ xác nhận **giá trị Boot công bố**.
- `SpringApplication.exit` returned đúng xác nhận **helper đã tính mã**.
- `System.exit` status đúng xác nhận **launcher trả mã cho OS**.
- `ContextClosedEvent` xác nhận **đã bước vào close**.
- Business job outcome cần kiểm dữ liệu thật, không thể suy từ exit code nếu generator được cài đặt sai.

Không lấy một trong năm assertions trên thay cho tất cả.

## 15. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Bước kiểm |
|---|---|---|
| Không có exit event với mã 0 | Boot không publish event cho 0 | Đổi `lab.exit-code=7` và quan sát |
| `LAB_EXIT_RETURNED=7` nhưng shell là 0 | Bỏ `System.exit(code)` hoặc wrapper thay status | Đọc main, chạy raw `java -jar` |
| `ExitCodeEvent` import không tìm thấy | Import sai package | Dùng `org.springframework.boot.ExitCodeEvent` |
| Listener không nhận event trong startup failure sớm | Bean listener chưa được tạo/registered | Đăng ký sớm bằng `addListeners` khi phù hợp; kiểm có event thật |
| Chỉ thấy `ContextClosedEvent` | Đóng context trực tiếp hoặc exit code 0 | Kiểm nơi gọi `SpringApplication.exit` |
| Thấy event nhưng process không kết thúc | Chưa gọi `System.exit`, còn non-daemon thread hoặc server | Đọc entrypoint, thread dump, shutdown hooks |
| `System.exit(7)` trực tiếp không có event | Bỏ qua SpringApplication.exit | Gọi helper trước khi terminate nếu cần mã/event |
| Chỉ thấy `ApplicationFailedEvent` | Không có nonzero mapping hoặc context chưa publish được | Xem generator/exception mapper/phase lỗi |
| Mã exit khác ý muốn | Nhiều generators cạnh tranh, order sai | Log generator outputs, `Ordered`/`@Order` |
| Generator luôn trả 0 | Property không bind đúng hoặc rule sai | In `lab.exit-code` và test với 7 |
| Lỗi nằm trong cause nhưng mapper trả 0 | Matcher chỉ nhìn top exception | Duyệt cause chain, phân biệt permanent/transient |
| Listener exit làm shutdown chậm | Có blocking I/O hoặc logging đồng bộ | Đưa I/O dài sang cleanup owner với deadline |
| `ContextClosedEvent` đến trước exit event trong log | Đường close khác, listener async hoặc nhiều contexts | Ghi nguồn, context ID, thread và code path |
| Event xuất hiện nhiều lần | Nhiều contexts, publish nhiều lần, listener registration trùng | Kiểm event source và listener identity |
| CI thấy success nhưng business job fail | ExitCodeGenerator không phản ánh kết quả thật | Tạo rule mã từ outcome đã được lưu |
| Maven task cho status khác raw JAR | Build tool/wrapper báo mã của chính nó | Dùng `java -jar` để kiểm OS status |
| Docker status 137 nhưng không có exit event | OS/runtime kill, không có graceful Java callback | Xem OOMKilled/signal, pod events |
| JUnit process chết khi test | Gọi `System.exit` trong test runner | Tách subprocess hoặc không gọi System.exit |
| Startup exception nhưng không có `LAB_EXIT_RETURNED` | `SpringApplication.run` ném trước khi trả context | Xem failure logs và exception generator |
| Context còn chạy sau return main | Đang có web/server/non-daemon thread | Phân biệt Spring exit helper vs process lifetime |

## 16. Bài tập thực hành

### Bài tập A — Sự khác nhau giữa 0 và nonzero

Chạy project với `lab.exit-code=0` và 7. Đếm `LAB_EXIT_EVENT`, `LAB_CONTEXT_CLOSED`, `LAB_EXIT_RETURNED` và raw shell status. Trả lời vì sao event count không thể dùng làm tổng số lần ứng dụng thoát.

### Bài tập B — Bỏ System.exit trong bản copy

Trong một bản sao lab, tạm thay `System.exit(code)` bằng một lời gọi in log rồi để `main` return bình thường. Chạy `--lab.exit-code=7`, kiểm event/returned vẫn bằng 7 nhưng OS có thể nhận 0 khi mọi threads đã dừng. Khôi phục code ngay sau thí nghiệm. Điều này chứng minh **helper return không tự được chuyển cho OS**.

### Bài tập C — Exception mang mã 19

Chạy `--lab.fail-startup=true`. Tìm root cause, `ExitCodeEvent`, `ContextClosedEvent` và process status. Giải thích tại sao `LAB_EXIT_RETURNED` không xuất hiện khi `run()` ném exception. Nêu trường hợp fail trước refresh khiến observer bean không tồn tại.

### Bài tập D — Hai generators khác thứ tự

Dùng cấu hình `OrderedExitCodes` tách riêng, bỏ generator mặc định để phép thử không bị ảnh hưởng. Chạy với first code 0, second code 12; rồi đổi first code 5. Kiểm event và OS code tương ứng 12 rồi 5. Giải thích tại sao “số lớn hơn thắng” là sai.

### Bài tập E — Mapper cho lỗi kiểm tra tham số

Thêm `ExitCodeExceptionMapper` kiểm `IllegalArgumentException` trong cause chain và trả 64. Thiết kế một runner thử nghiệm ném lỗi này khi input không hợp lệ. Kiểm log root cause và status, rồi thử lỗi không match mapper để xem fallback. Không dùng mapper để che giấu lỗi hay chuyển mọi lỗi thành 0.

### Bài tập F — Process/container bị kill

Chạy một server thử nghiệm hoặc job chờ có kiểm soát, rồi dùng shutdown bình thường và hard kill ở môi trường lab riêng. So marker `ContextClosedEvent`, `ExitCodeEvent` và process status. Không đưa hard kill vào môi trường dữ liệu thật; dựa vào supervisor metrics để thống kê những lần Spring không kịp phát event.

### Bài tập G — Kiểm thử qua subprocess

Viết script kiểm ba lệnh raw `java -jar`. Mỗi lệnh kiểm một giá trị shell status, event marker và close marker; lưu output/err riêng. Điều kiện pass: 0 không có exit event, 7 có event 7, startup fail có nguyên nhân và mã nonzero đã map theo policy.

## 17. Checklist nghiệm thu

- [ ] Nêu được package chính xác `org.springframework.boot.ExitCodeEvent`.
- [ ] Biết `ExitCodeEvent.getExitCode()` đọc giá trị nào.
- [ ] Giải thích `SpringApplication.exit` và `System.exit` là hai bước riêng.
- [ ] Chạy được Java 17 + Spring Boot 3.5 Maven CLI project.
- [ ] Với mã 0: không có ExitCodeEvent nhưng có ContextClosedEvent.
- [ ] Với mã 7: exit event xuất hiện trước context closed event.
- [ ] Đối chiếu được helper result 7 với shell status 7.
- [ ] Với startup exception code 19: phân biệt failure path và successful exit path.
- [ ] Biết `ExitCodeExceptionMapper` và exception implement `ExitCodeGenerator`.
- [ ] Biết many generators dùng `Ordered`/`@Order` và first nonzero.
- [ ] Không nhầm absence of ExitCodeEvent với process không đóng.
- [ ] Không dùng event listener làm nơi tự gọi `System.exit`.
- [ ] Không dùng `System.exit` trực tiếp bên trong HTTP controller/unit test.
- [ ] Phân biệt `ApplicationFailedEvent`, `ApplicationReadyEvent` và `ContextClosedEvent`.
- [ ] Biết SIGKILL/OOM/crash không bảo đảm Spring event và cleanup.
- [ ] Biết lấy exit status từ Unix `$?` hoặc PowerShell `$LASTEXITCODE`.
- [ ] Có quy ước exit codes nghiệp vụ và log/metrics khớp process supervisor.
- [ ] Giữ phép thử trong CLI/subprocess, không phá test runner hoặc web server production.

## 18. Tài liệu chính thức

1. **Spring Boot 3.5 — SpringApplication / Application Exit**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — cách dùng `ExitCodeGenerator`, `SpringApplication.exit` và `System.exit`, xử lý nhiều generators.
2. **Spring Boot 3.5 API — ExitCodeEvent**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeEvent.html — package, constructor và `getExitCode()`.
3. **Spring Boot 3.5 API — ExitCodeGenerator**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeGenerator.html — functional interface và contract `getExitCode()`.
4. **Spring Boot 3.5 API — ExitCodeExceptionMapper**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeExceptionMapper.html — mapping `Throwable` thành mã.
5. **Spring Boot 3.5 API — SpringApplication.exit(...)**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html — đóng context, lựa chọn generator và return code.
6. **Java SE 17 — System.exit(int)**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int) — yêu cầu kết thúc JVM với mã status.
7. **Spring Framework 6.2 — Application Events**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html — cơ chế `ApplicationListener` và `@EventListener`.

**Tổng kết:** `ExitCodeEvent` là tín hiệu quan sát **mã thoát khác 0 được Spring Boot xác định**, thường phát trước khi context đóng trong đường `SpringApplication.exit(context)`. Listener thấy event không tự làm process thoát; phải chuyển kết quả qua `System.exit(code)` nếu muốn shell/CI/Kubernetes nhận mã đó. Với lỗi khởi động, dùng `ExitCodeGenerator` trên exception hoặc `ExitCodeExceptionMapper` và kiểm phase publisher còn hoạt động. Khi process bị OS kill, JVM crash hoặc đóng context trực tiếp, **không được suy rằng luôn có ExitCodeEvent** — hãy kết hợp event, failure logs, context close và exit status của hạ tầng để có kết luận đúng.