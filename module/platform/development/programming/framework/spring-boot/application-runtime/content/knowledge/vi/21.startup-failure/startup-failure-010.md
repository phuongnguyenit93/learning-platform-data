# Giải phóng tài nguyên và trả mã lỗi khi khởi động thất bại trong Spring Boot

## 1. Vì sao lỗi khởi động cần hai cơ chế độc lập?

Khi một ứng dụng Spring Boot không khởi động được, có ít nhất **hai hậu quả** phải xử lý đúng:

1. **Tài nguyên đã được cấp phát** trong những giai đoạn khởi động trước lỗi phải được dọn dẹp: connection, thread, executor, file handle, socket, message consumer, temporary file, subscription và các tài nguyên bên ngoài.
2. **Tiến trình phải báo trạng thái thất bại** cho shell, CI/CD, container orchestrator hoặc job scheduler bằng một **exit code khác 0**, nếu ứng dụng chạy theo mô hình process/CLI tương ứng.

Hai việc này liên quan nhưng **không đồng nhất**:

- Log có dòng `APPLICATION FAILED TO START` không có nghĩa mọi tài nguyên đã được dọn sạch.
- Chạy xong `@PreDestroy` không tự bảo đảm JVM trả đúng mã lỗi.
- Gọi `System.exit(1)` không phải một chiến lược dọn tài nguyên: nó có thể gây bỏ qua các bước cleanup do luồng ứng dụng đáng lẽ thực hiện.
- `SpringApplication.exit(context)` không phải “lối thoát thay thế” khi `SpringApplication.run()` đã ném exception trước khi trả về context.

Trong Spring Boot 3.3.x / Spring Framework 6.1.x và Java 17+, chiến lược tốt là:

**Để Spring quản lý vòng đời của tài nguyên đã đăng ký đúng cách; dùng `try/finally` hoặc `try-with-resources` cho tài nguyên chưa thuộc container; ném exception diễn đạt lỗi khởi động; định nghĩa mã lỗi tại một điểm được kiểm soát; và kiểm tra exit code ở cấp tiến trình.**

### 1.1. Một sơ đồ tổng quan

```text
SpringApplication.run(...)
       |
       +-- Chuẩn bị Environment / cấu hình
       |
       +-- Tạo ApplicationContext
       |
       +-- Nạp bean definitions / refresh
       |     +-- Một số bean đã được khởi tạo
       |
       +-- ApplicationStartedEvent
       |
       +-- ApplicationRunner / CommandLineRunner
       |
       +-- ApplicationReadyEvent, nếu thành công
       |
       +-- Trả về context, nếu thành công

Nếu lỗi:
       |
       +-- Spring Boot xác định exit code (nếu có ánh xạ)
       +-- Thông báo ApplicationFailedEvent phù hợp
       +-- Báo cáo nguyên nhân lỗi
       +-- Đóng context nếu đã được tạo
       |     +-- Dừng lifecycle components phù hợp
       |     +-- Hủy singleton còn được quản lý
       |
       +-- Ném lại lỗi cho caller
       +-- Mã thoát tiến trình theo cơ chế launcher/JVM
```

Đây là bản mô tả **đường đi chủ yếu**, không phải thứ tự log tuyệt đối và không nói rằng context luôn tồn tại ở mọi lỗi. Tại một lỗi cực sớm trong chuẩn bị environment, context có thể **chưa được tạo**. Trong refresh failure, Spring Framework còn có đường dọn các singleton đã tạo trước khi lỗi được đẩy lên Spring Boot.

## 2. Phân loại lỗi theo thời điểm để xác định ai dọn tài nguyên

| Giai đoạn | Ví dụ lỗi | Context ở thời điểm lỗi | Cần chú ý |
| --- | --- | --- | --- |
| Trước khi tạo context | Sai tham số, thiếu file cấu hình, lỗi parse environment | Có thể `null` | Không có bean destruction để bảo vệ tài nguyên đã mở thủ công |
| Đang tạo context / nạp definitions | Lỗi initializer, metadata hoặc bean definition | Có thể đã tạo nhưng chưa refresh | Chỉ một số hạ tầng và đối tượng đã tồn tại |
| Trong `refresh()` | Dependency thiếu, constructor ném lỗi, `@PostConstruct` lỗi, bind/validation lỗi | Context đã được tạo, refresh chưa hoàn tất | Spring cố dọn singleton đã được tạo, nhưng bean lỗi **chưa hoàn tất** có thể chưa có destructor được đăng ký |
| Sau refresh, trong runner | `ApplicationRunner`/`CommandLineRunner` ném exception | Context đã refresh thành công | Boot đi qua failure handler và đóng context |
| Trong callback `ApplicationReadyEvent`/ready phase | Listener lỗi hoặc callback sẵn sàng ném exception | Context có thể active | Phải bảo đảm cleanup và không tuyên bố startup thành công |
| Lỗi ngoài đường khởi động, sau khi `run()` trả về | Request HTTP lỗi, scheduled job lỗi | Context đang chạy | **Không mặc nhiên** là startup failure; cần cơ chế runtime failure riêng |

Phân loại này quan trọng vì rất nhiều tài nguyên được tạo **trước khi** Spring có thể sở hữu chúng.

Ví dụ, code:

```java
Socket socket = new Socket(host, port);
SpringApplication.run(DemoApplication.class, args);
```

là **pseudo-code** có các biến và import chưa được định nghĩa. Nếu lệnh `SpringApplication.run` lỗi, socket chỉ có cơ hội được đóng nếu đã được bao bọc bằng cơ chế ownership/cleanup rõ ràng. Không có bảo đảm Spring biết tới local variable `socket`.

Ngược lại, một bean singleton đã tạo thành công, được đăng ký destructor, thường được Spring dọn khi context đóng hoặc refresh thất bại. Tuy nhiên không nên khẳng định tất cả callback destruction của mọi bean đều đã chạy trong mọi loại lỗi.

## 3. ApplicationContext có trách nhiệm dọn dẹp những gì?

Khi Spring quản lý một singleton bean và biết callback destruction, framework có thể gọi:

- `@PreDestroy` — chú thích Jakarta trong Spring Boot 3.
- `DisposableBean.destroy()` — hợp đồng trực tiếp với Spring.
- Custom destroy method — ví dụ `@Bean(destroyMethod = "close")` hoặc `@Bean(destroyMethod = "shutdown")`.
- Phương thức `close()` / `shutdown()` được suy luận theo cơ chế `@Bean` khi phù hợp.
- `SmartLifecycle.stop(Runnable callback)` đối với các lifecycle beans thích hợp, trong đường đóng context bình thường.

Ví dụ đơn giản:

```java
@Configuration
class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ClientHandle clientHandle() {
        return new ClientHandle();
    }
}
```

Đây là **snippet**: cần định nghĩa `ClientHandle implements AutoCloseable` và import `Configuration`/`Bean`. Khi instance được trả về thành công và đăng ký làm bean singleton, Spring có cơ chế gọi `close()` khi destroy bean.

### 3.1. Trách nhiệm ownership

Một nguyên tắc rất hữu ích:

> **Bên nào hoàn tất việc nhận quyền sở hữu tài nguyên thì bên đó có trách nhiệm bảo đảm tài nguyên được đóng.**

Có thể phân loại:

| Tài nguyên | Ai đang sở hữu? | Cơ chế đề xuất |
| --- | --- | --- |
| Singleton bean đã được Spring tạo xong | Container Spring | Destructor bean được đăng ký |
| `AutoCloseable` local được mở trong một method | Method/caller | `try-with-resources` |
| Tài nguyên mở dở trong constructor/factory rồi ném lỗi | Constructor/factory | `try/catch/finally` ngay tại điểm cấp phát |
| Worker thread được mở trước `SpringApplication.run` | Code bootstrap | Cleanup tường minh hoặc ownership riêng |
| Bean `prototype` | Caller sau khi Spring cấp instance | Caller tự đóng; Spring không tự hủy từng prototype |
| Tài nguyên ngoài hệ thống như lock/lease | Chủ thể sở hữu lease/lock | Release có deadline + cơ chế expiration/recovery |
| Virtual thread/executor tự tạo ngoài container | Code tạo executor | Quản lý cancellation/shutdown riêng |

Một callback destruction không thể đóng tài nguyên mà container **không hề biết đã tồn tại**. Nếu bean chưa hoàn tất khởi tạo, không mặc định rằng Spring đã đăng ký destructor của bean đó.

## 4. Tại sao refresh failure vẫn thường dọn được singleton đã tạo?

`AbstractApplicationContext.refresh()` của Spring Framework có xử lý lỗi cho quá trình refresh. Khi một lỗi phù hợp xảy ra, Spring sẽ tìm cách:

1. Ngăn refresh tiếp tục.
2. Dọn những singleton đã được tạo trong bean factory.
3. Đánh dấu context không còn ở trạng thái refresh thành công.
4. Đẩy exception ra cho caller/Boot để thực hiện xử lý lỗi cấp ứng dụng.

Trong Spring Framework 6.1, trách nhiệm hủy singleton đã tạo khi refresh thất bại là một phần quan trọng của hợp đồng `refresh()`.

Nhưng có các giới hạn thực tế:

- Bean bị lỗi **giữa constructor và hoàn tất đăng ký** có thể chưa có destructor để container gọi.
- Tài nguyên tạo qua một biến local trong `@Bean` factory method **trước khi return** chưa chắc đã được container biết tới.
- `prototype` không được container quản lý destruction theo cách của singleton.
- External process, socket, thread hoặc file mở trong custom static initializer có thể không thuộc bean lifecycle.
- Một callback hủy có thể ném lỗi, bị block hoặc gặp deadline từ môi trường.
- Nếu JVM bị kill cưỡng bức, đường cleanup có thể không được thực thi.

Vì vậy **auto cleanup của Spring là một lớp bảo vệ quan trọng, không phải bảo đảm tuyệt đối cho mọi resource allocation**.

### 4.1. Lỗi trong @Bean factory method

Mẫu dễ làm rò rỉ:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() {
    RemoteSession session = new RemoteSession();
    session.connect(); // Nếu lỗi ở đây, @Bean chưa trả session về container.
    return session;
}
```

Đây là **pseudo-code** vì `RemoteSession` cần được định nghĩa riêng. Nếu `connect()` mở một phần tài nguyên rồi ném exception, bean chưa được trả về thành công; không nên trông chờ Spring gọi `close()` trên local variable `session`.

Viết theo cơ chế ownership đúng:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();

    try {
        session.connect();
        return session;  // Bàn giao ownership cho Spring.
    } catch (Exception | Error failure) {
        try {
            session.close();
        } catch (Exception closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
```

Snippet này giả định `RemoteSession.connect()` và `close()` có hợp đồng phù hợp, là một bean factory method trong `@Configuration`. Nếu lỗi xảy ra trước khi `return`, method tự đóng tài nguyên và giữ nguyên nguyên nhân gốc (lỗi cleanup được thêm thành *suppressed exception*).

**Một lựa chọn tốt hơn:** thiết kế `RemoteSession` để constructor/connect an toàn khi thất bại và có thể cleanup riêng từng bước. Không nên cấp phát tác vụ background/connection theo nhiều bước mà không có rollback.

### 4.2. Lỗi trong constructor

Ví dụ:

```java
public final class SocketWorker {

    private final ResourcePart partA;
    private final ResourcePart partB;

    public SocketWorker() throws Exception {
        ResourcePart openedA = openPartA();

        try {
            ResourcePart openedB = openPartB();
            this.partA = openedA;
            this.partB = openedB;
        } catch (Exception | Error failure) {
            try {
                openedA.close();
            } catch (Exception cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }
}
```

Đây là **minh họa thiết kế**; `ResourcePart`, `openPartA` và `openPartB` chưa được định nghĩa. Ý tưởng là: resource A đã mở thì nếu mở B thất bại, constructor phải tự đóng A. Không thể dựa vào `@PreDestroy` của một bean chưa xây dựng xong để bảo vệ những bước đó.

Nếu `openPartB` có thể tự cấp phát một phần rồi lỗi, chính `openPartB` cũng phải bảo đảm rollback phần chưa bàn giao.

## 5. Ví dụ runnable: lỗi trong ApplicationRunner và cleanup bean

Demo dưới đây dùng **Java 17+**, **Spring Boot 3.3.x** và chỉ cần `spring-boot-starter`. Một bean resource được tạo thành công, sau đó `ApplicationRunner` cố tình ném exception.

Mục tiêu của ví dụ là kiểm chứng:

1. Bean resource đã được Spring tạo và sở hữu.
2. Lỗi trong runner là lỗi ở **giai đoạn startup**, dù context đã refresh.
3. Spring Boot xử lý failure và đóng context.
4. Custom destroy method của resource được gọi.
5. Một exception có `ExitCodeGenerator` có thể đưa mã lỗi cụ thể vào cơ chế exit handling của Boot.

### 5.1. Cấu trúc project

```text
startup-failure-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          failure/
            StartupFailureApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'startup-failure-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đây là một phiên bản Spring Boot thuộc nhánh 3.3 để minh họa API; dự án thực tế cần chọn phiên bản còn được bảo trì theo chính sách tổ chức. Cấu hình này cần Gradle/Gradle wrapper tương thích và JDK 17+. `./gradlew` chỉ có sau khi đã tạo wrapper cho dự án.

`src/main/resources/application.properties`:

```properties
spring.application.name=startup-failure-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

Dùng `web-application-type=none` để không cần server HTTP. Nhờ vậy có thể tập trung vào lifecycle và mã thoát mà không làm thay đổi cổng mạng.

### 5.2. Source Java đầy đủ

File `src/main/java/demo/failure/StartupFailureApplication.java`:

```java
package demo.failure;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupFailureApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupFailureApplication.class, args);
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner failingRunner(DemoResource resource) {
        return args -> {
            if (resource.isClosed()) {
                throw new IllegalStateException("Resource closed too early");
            }

            System.out.println("runner.start");
            throw new StartupRejectedException();
        };
    }
}

final class DemoResource implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean(false);

    DemoResource() {
        System.out.println("resource.open");
    }

    boolean isClosed() {
        return closed.get();
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("resource.close");
        }
    }
}

final class StartupRejectedException
        extends RuntimeException implements ExitCodeGenerator {

    StartupRejectedException() {
        super("Demonstration startup failure");
    }

    @Override
    public int getExitCode() {
        return 23;
    }
}
```

Lưu ý:

- Trong cùng một file Java, chỉ `StartupFailureApplication` là top-level `public`; hai class còn lại package-private và hợp lệ.
- `DemoResource` implements `AutoCloseable`; `@Bean(destroyMethod = "close")` khai báo rõ quyền dọn dẹp của Spring.
- `isClosed()` chỉ phục vụ kiểm tra trạng thái trong demo.
- `failingRunner` inject `DemoResource`, bảo đảm Spring đã tạo resource trước khi runner chạy.
- `StartupRejectedException` là exception nghiệp vụ minh họa, có message cố định và implements `ExitCodeGenerator`.
- `getExitCode() == 23` biểu thị một mã lỗi khác 0; đây là **quy ước demo**, không phải exit code chuẩn của mọi ứng dụng.
- Không gọi `System.exit` trong bean, runner, destructor hay failure listener.

### 5.3. Chạy ứng dụng

Sau khi dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Hoặc:

```bash
./gradlew bootJar
java -jar build/libs/startup-failure-demo-1.0.0.jar
```

Tên JAR ở lệnh trên dựa trên group/name/version trong build demo; nếu project có cấu hình khác, lấy tên file được build thực tế.

Các **marker do code demo in ra** khi runner thất bại:

```text
resource.open
runner.start
resource.close
```

Spring Boot còn có thể in stack trace và `Application run failed`, Gradle có thể in thông báo task thất bại. Ba dòng trên **không phải toàn bộ stdout/stderr**, mà là thứ tự tương đối của log ứng dụng do demo tạo.

Khi chạy đường `main` bình thường với failure handler của Spring Boot 3.3, exception có thể được nhận diện qua cause chain và `getExitCode()` cung cấp **23** cho cơ chế xử lý mã thoát. Cần kiểm tra exit status cuối cùng của tiến trình Java bên ngoài, vì công cụ chạy bao quanh (Gradle, IDE, test runner) có thể có quy tắc báo mã thoát riêng.

Trên shell POSIX, chạy JAR trực tiếp và xem mã thoát:

```bash
java -jar build/libs/startup-failure-demo-1.0.0.jar
printf 'exit=%s\n' "$?"
```

Kết quả mong đợi khi Spring Boot dùng failure-handler mặc định của `main` là:

```text
exit=23
```

Dòng này do `printf` của shell in ra **sau khi tiến trình Java kết thúc**, không phải do `DemoResource` in. Trên PowerShell, cần dùng biến `$LASTEXITCODE` của lệnh native tương ứng.

### 5.4. Vì sao resource.close vẫn chạy?

Lỗi xảy ra **trong runner sau khi context refresh đã hoàn thành**. `SpringApplication.run` đi vào đường xử lý lỗi của Spring Boot; handler nắm được context đã tạo, xử lý failure và đóng context. Khi context đóng, singleton bean `DemoResource` được hủy qua custom destroy method `close()`.

Điều này khác trường hợp `new DemoResource()` được tạo thành local variable rồi không đăng ký làm bean: Spring không biết đến resource đó, nên không thể tự gọi `close()` thay cho người sở hữu.

### 5.5. Đừng dùng System.exit trong runner

Không nên sửa runner thành:

```java
@Bean
ApplicationRunner dangerousRunner() {
    return args -> {
        System.err.println("Invalid startup input");
        System.exit(23);
    };
}
```

Đây là **phản ví dụ**. Khi JVM bắt đầu thoát, shutdown hooks có thể được gọi trong điều kiện bình thường, nhưng chính lệnh `System.exit` đã làm việc điều khiển tiến trình trở nên khó kiểm thử và có thể bỏ qua mã cleanup nằm phía sau method. Nếu chương trình đang chạy trong IDE, test runner hoặc JVM dùng chung, nó còn kết thúc toàn bộ process.

Tốt hơn: **ném exception có mã lỗi/ánh xạ phù hợp**, cho Spring Boot thực hiện failure handling, rồi để process launcher xử lý exit status.

## 6. Ba cách xác định mã thoát

Cần phân biệt **cơ chế startup failure** với **cơ chế exit chủ động sau khi startup thành công**.

| Cách | Khi dùng | Điều cần hiểu |
| --- | --- | --- |
| Exception implements `ExitCodeGenerator` | Startup thất bại bởi exception có ý nghĩa nghiệp vụ | Boot có thể đọc mã lỗi trên exception/cause chain |
| Bean `ExitCodeExceptionMapper` | Muốn ánh xạ nhiều loại exception theo policy | Bean mapper chỉ khả dụng khi context active và đã tạo đủ để tra cứu |
| `SpringApplication.exit(context, generators...)` | `run` đã trả về context, ứng dụng chủ động kết thúc | Tính mã thoát và đóng context; **không tự kết thúc JVM** |

Ngoài ra, **top-level launcher** có thể có một `catch` để bảo đảm exit code riêng theo đặc thù CLI. Nhưng cần tránh tính mã lỗi ở hai nơi độc lập dễ mâu thuẫn.

### 6.1. ExitCodeGenerator trên exception

`ExitCodeGenerator` là interface của Spring Boot:

```java
public interface ExitCodeGenerator {
    int getExitCode();
}
```

Đây là **chữ ký minh họa**; phải import `org.springframework.boot.ExitCodeGenerator`, không tự định nghĩa lại khi code ứng dụng.

Có thể implement trên một exception:

```java
public final class InvalidStartupConfigurationException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidStartupConfigurationException() {
        super("Startup configuration is invalid");
    }

    @Override
    public int getExitCode() {
        return 64;
    }
}
```

Đây là class Java độc lập có thể đặt ở file `InvalidStartupConfigurationException.java` trong package phù hợp, cần import `ExitCodeGenerator`. Mã `64` chỉ là **policy của ứng dụng**, không phải mã Spring Boot bắt buộc.

Ưu điểm:

- Logic lỗi biểu đạt trực tiếp mã thoát.
- Không cần context đã active để đọc giá trị từ chính exception.
- Phù hợp với lỗi rất sớm hoặc lỗi trong runner đã được Spring Boot bắt giữ.
- Có thể dùng cause chain để tìm exception thực thi interface trong trường hợp bị bọc.

Cần nhớ: việc có mã lỗi không đồng nghĩa mọi caller gọi `SpringApplication.run` đều bị `System.exit` ngay. `run` vẫn ném exception để caller xử lý; Spring Boot hỗ trợ default exception handling khi khởi động từ main thread.

### 6.2. ExitCodeExceptionMapper

Nếu không muốn exception nghiệp vụ phụ thuộc vào interface Spring, có thể dùng một bean ánh xạ:

```java
@Configuration
class ExitCodeConfiguration {

    @Bean
    ExitCodeExceptionMapper startupExitMapper() {
        return exception -> {
            Throwable cursor = exception;

            while (cursor != null) {
                if (cursor instanceof InvalidInputException) {
                    return 64;
                }
                cursor = cursor.getCause();
            }

            return 0;
        };
    }
}
```

Đoạn này là **snippet tích hợp**, cần import `Configuration`, `Bean` và `ExitCodeExceptionMapper`, đồng thời định nghĩa class `InvalidInputException`. Không cần implement `ExitCodeGenerator` trên exception nếu policy nằm ở mapper.

**Giới hạn lớn:** Boot lấy mapper dưới dạng bean **khi context tồn tại và active**. Một lỗi trước khi context được tạo hoặc trước refresh thành công có thể làm mapper không dùng được. Vì vậy đừng kỳ vọng bean mapper xử lý **mọi** lỗi khởi động sớm.

Trong mã nguồn `SpringApplication` của Boot 3.3, việc tính exit code khi thất bại xem xét bean mappers khi context active, sau đó xét exception/cause chain có `ExitCodeGenerator` nếu chưa có mã khác. Khi viết quy tắc ưu tiên, nên kiểm tra đúng version Spring Boot được triển khai.

### 6.3. ExitCodeEvent

Spring Boot có `ExitCodeEvent` để thông báo mã thoát khác 0 trong những đường xử lý hỗ trợ event. Đây là **thông báo về exit code**, không phải lệnh tự đóng socket hoặc hủy bean.

Một listener:

```java
@Component
class ExitStatusObserver {

    @EventListener
    void onExitCode(ExitCodeEvent event) {
        System.out.println("app.exitCode=" + event.getExitCode());
    }
}
```

Đây là snippet cần import `Component`, `EventListener` và `org.springframework.boot.ExitCodeEvent`. Với lỗi quá sớm, **không nên dựa vào bean listener được tạo muộn**: context có thể chưa active hoặc hạ tầng event chưa được đăng ký.

Ngoài ra, không phải sự kiện exit code nào cũng được quan sát bởi mọi listener trong mọi giai đoạn. Khi cần giám sát startup failures rất sớm, ưu tiên listener được đăng ký trước `run` hoặc công cụ giám sát ở ngoài process.

### 6.4. SpringApplication.exit khi run đã thành công

Ví dụ cho một **CLI chủ động đóng**:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

Đoạn này cần class `BatchApplication` được định nghĩa và import `SpringApplication`, `ConfigurableApplicationContext`. Nó đúng với **trường hợp `run` trả về thành công**.

`SpringApplication.exit(context)`:

- Tìm những `ExitCodeGenerator` beans thích hợp cùng các generators được truyền vào.
- Sắp xếp và chọn giá trị theo hợp đồng của Boot khi nhiều generators tồn tại.
- Đóng context khi có thể.
- **Trả về số nguyên**, không tự gọi `System.exit(...)`.

Nếu muốn process thực sự trả status đó, caller ở tầng `main` có thể gọi `System.exit(code)`. Nhưng không đưa cách này vào một server long-running hoặc test framework mà không có sự chủ đích.

**Bẫy:** nếu `SpringApplication.run(...)` ném exception, phép gán `context = ...` không hoàn tất; không có biến context hợp lệ để gọi `SpringApplication.exit(context)` theo đường này. Boot đã thực hiện failure cleanup qua code của `run`; không nên tạo context mới chỉ để gọi exit.

## 7. Exit code 0 và khác 0 có ý nghĩa gì?

Theo quy ước của hệ điều hành và nhiều công cụ CI:

- `0`: process báo hoàn tất thành công.
- Non-zero: process báo thất bại hoặc tình trạng bất thường.
- Ý nghĩa cụ thể của mã `2`, `23`, `64` hoặc mã khác cần được **định nghĩa bởi ứng dụng**.

Một bảng policy minh họa:

| Mã | Ý nghĩa do ứng dụng định nghĩa |
| ---: | --- |
| 0 | Thành công |
| 2 | Đối số CLI không hợp lệ |
| 10 | Không thể nạp cấu hình bắt buộc |
| 20 | Không thể kết nối dependency chính |
| 23 | Khởi động tác vụ bị từ chối (demo) |
| 30 | Kiểm tra dữ liệu khởi động không đạt |
| 70 | Lỗi nội bộ không phân loại |

Đây là **bảng quy ước ví dụ**, không phải hằng số Spring Boot chuẩn. Một hệ thống sản xuất nên công bố những mã cần cho automation và duy trì tính tương thích.

Đừng chỉ làm:

```java
System.err.println("Startup failed");
return;
```

trong `main` rồi kỳ vọng shell nhận non-zero. Nếu method `main` kết thúc bình thường mà không có cơ chế khác đặt mã thoát, process thường trả `0`.

Tương tự, in `error` vào log **không thay đổi exit status**. Exit code là **kết quả tiến trình**; phải kiểm tra ở cấp process.

### 7.1. Quan sát exit code trong shell

Trên Linux/macOS:

```bash
java -jar app.jar
code=$?
printf 'exit=%s\n' "$code"
```

Trên PowerShell:

```powershell
java -jar app.jar
Write-Output ("exit=" + $LASTEXITCODE)
```

Đây là các đoạn lệnh shell. Giá trị chính xác phụ thuộc vào exit code của process Java và vào chính sách Boot/launcher. Nếu chạy ứng dụng bằng Gradle, Maven, Docker hoặc Kubernetes, phải phân biệt **exit code của Java process** với mã trả về của wrapper.

### 7.2. Không dùng System.exit trong cleanup

Không gọi `System.exit` trong:

- `@PreDestroy`.
- `DisposableBean.destroy()`.
- `SmartLifecycle.stop(Runnable)`.
- `ApplicationFailedEvent` listener.
- `close()` của một resource.
- Callback async từ thread pool đang được shutdown.

Nguyên nhân là những callback đó được gọi **bên trong quy trình dọn tài nguyên**. Kết thúc JVM tại đó có thể làm logic cleanup khác bị cắt ngắn hoặc làm khó kiểm thử, gây trạng thái khó dự đoán.

Định nghĩa exit status ở **ranh giới quy trình**; để Spring hoàn tất cleanup theo hợp đồng trước khi process kết thúc nếu có thể.

## 8. ApplicationFailedEvent: theo dõi lỗi nhưng không thay thế cleanup

Spring Boot phát `ApplicationFailedEvent` khi `SpringApplication` gặp lỗi khởi động phù hợp. Event chứa exception và có thể chứa application context — nhưng **context có thể null nếu lỗi xảy ra trước khi tạo context**.

### 8.1. Vì sao @EventListener bean có thể bỏ lỡ lỗi sớm?

Một bean:

```java
@Component
class StartupFailureLogger {

    @EventListener
    void onFailure(ApplicationFailedEvent event) {
        // Chỉ chạy nếu bean listener đã tồn tại và được đăng ký.
    }
}
```

cần các import thích hợp và chỉ là snippet. Nếu lỗi xảy ra **trước bean creation**, listener này chưa tồn tại trong hạ tầng event và có thể không bao giờ nhận sự kiện.

Muốn quan sát lỗi ở giai đoạn sớm, hãy đăng ký listener trực tiếp **trước `SpringApplication.run(...)`**:

```java
SpringApplication app = new SpringApplication(BatchApplication.class);
app.addListeners(new EarlyFailureObserver());
app.run(args);
```

Đoạn này cần `BatchApplication` và `EarlyFailureObserver` được khai báo, là mẫu đặt trong phương thức `main`.

### 8.2. Listener sớm, không đòi context tồn tại

Ví dụ class độc lập:

```java
package demo.failure;

import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyFailureObserver
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        String type = event.getException().getClass().getSimpleName();
        boolean contextExists = event.getApplicationContext() != null;

        System.err.println("startup.failureType=" + type);
        System.err.println("startup.contextExists=" + contextExists);
    }
}
```

Để dùng nó, đăng ký instance `new EarlyFailureObserver()` với `SpringApplication.addListeners(...)` trước `run`. Listener này **không phải bean** và không dùng injection từ Spring; vì vậy không truy cập repository, datasource hoặc các service chưa chắc đã tồn tại.

**Lưu ý:** class exception có thể là wrapper framework thay vì root cause nghiệp vụ. Nếu cần phân loại lỗi, duyệt cause chain có giới hạn và tránh log message nhạy cảm từ input chưa được lọc.

### 8.3. Callback event có thể chạy trước cleanup hoàn tất

Trong đường failure handling của Spring Boot 3.3, các listener lỗi được thông báo trong quá trình xử lý failure. Đừng coi việc nhận `ApplicationFailedEvent` là dấu hiệu:

- Các singleton đã bị destroy hết.
- Tài nguyên do bean nắm giữ đã đóng.
- External compensating action đã hoàn tất.
- Process đã có exit code cuối cùng.
- Có thể an toàn gọi mọi bean khác.

**Dùng event để ghi nhận/quan sát lỗi**, không phải thay thế `try/finally` hoặc bean destruction.

## 9. Nguyên tắc cleanup khi thất bại ở từng giai đoạn

### 9.1. Trước tạo context: bootstrap resources

Ví dụ phải đọc một file cấu hình phụ trước khi gọi Spring:

```java
try (InputStream in = Files.newInputStream(path)) {
    // Kiểm tra dữ liệu cần thiết.
    // Chỉ sau khi đạt yêu cầu mới bắt đầu SpringApplication.
}
SpringApplication.run(BatchApplication.class, args);
```

Đây là **snippet** với `path` đã được định nghĩa, import `InputStream` và `Files`, và `BatchApplication` hợp lệ. File stream được đóng khi rời block, ngay cả khi validation ném exception.

Nếu resource phải tồn tại suốt runtime, hãy tổ chức bàn giao ownership cho một bean hoặc một manager rõ ràng, không chỉ đặt tất cả resource ở biến static rồi hy vọng JVM sẽ xử lý.

### 9.2. Đang tạo bean: một phần tài nguyên đã mở

Đặt `try/catch` ngay quanh thao tác cấp phát. Nếu phương thức factory không thể return bean, **người tạo** phải rollback các resource đã mở. Giữ exception gốc và gắn cleanup failure dưới dạng suppressed exception nếu phù hợp.

### 9.3. Trong refresh: singleton đã hoàn tất và singleton đang lỗi

Spring cố dọn singleton đã hoàn tất tạo trước đó. Nhưng không dựa vào destructor của **chính bean đang fail** nếu nó chưa hoàn tất construction/initialization.

Hãy kiểm tra các callback:

- `@PostConstruct` của bean lỗi có thể đã mở tài nguyên rồi ném exception.
- `@PreDestroy` của bean đó có thể không có cơ hội được đăng ký và gọi.
- Dependency singleton **đã tạo thành công** có thể nhận destructor.
- Tài nguyên bên ngoài do bean tạo bằng static helpers hoặc threads có thể cần cleanup riêng.

### 9.4. Runner lỗi sau refresh

Đây là trường hợp thuận lợi hơn cho Spring-managed resources: context đã được refresh, các singleton cần thiết đã được đăng ký. Boot xử lý lỗi và đóng context.

Nhưng `ApplicationReadyEvent` **không phát ra như một sự kiện startup thành công** khi runner ném lỗi. Phần mềm giám sát không nên coi dòng “Started application” trước runner là bằng chứng ứng dụng đã sẵn sàng nghiệp vụ.

### 9.5. Lỗi sau startup không phải ApplicationFailedEvent

Khi `SpringApplication.run` đã trả context và một scheduled job ném exception sau đó, đó là **lỗi runtime**. `ApplicationFailedEvent` phục vụ lỗi trong quá trình run/startup; không phải event toàn cục cho mọi exception.

Nếu lỗi runtime phải khiến app dừng, cần policy riêng:

- Ghi nhận trạng thái không khỏe/readiness thích hợp.
- Ngừng nhận công việc mới.
- Hủy task/đóng resource.
- Đóng application context.
- Quyết định exit code ở ranh giới process.

Đừng ném exception trong một background thread rồi mặc định toàn JVM sẽ thoát với mã lỗi bạn mong muốn.

## 10. Dọn dẹp tài nguyên song song: thread, executor, scheduler

Một bean có thể đã khởi chạy background thread ngay trong constructor hoặc `@PostConstruct`. Khi startup thất bại sau đó, các thread này có thể tiếp tục làm việc nếu không dừng.

Ví dụ về thiết kế tài nguyên riêng:

```java
public final class WorkerGroup implements AutoCloseable {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    public void submit(Runnable task) {
        executor.execute(task);
    }

    @Override
    public void close() {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là class Java đầy đủ trong một file `WorkerGroup.java`, cần import:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
```

Đặt nó vào `@Bean(destroyMethod = "close")` hoặc tạo trong `try-with-resources` để đảm bảo ownership. Hàm `close()` có bounded wait, tránh block vô hạn.

**Giới hạn của ví dụ:** nếu thread/tác vụ không hỗ trợ interrupt hoặc kẹt ở I/O không có timeout, `shutdownNow()` chỉ phát tín hiệu hủy, không bảo đảm tài nguyên đã ngừng an toàn. Production cần shutdown policy theo nghiệp vụ, không phụ thuộc chỉ vào một lời gọi `shutdownNow`.

### 10.1. Tại sao tạo thread trong constructor là rủi ro?

Constructor có thể khởi chạy thread trước khi bean được Spring đăng ký hoàn chỉnh. Nếu constructor ném exception ở bước tiếp theo, thread đã chạy nhưng framework chưa có một bean hoàn tất để gọi destructor.

Thay vào đó, ưu tiên:

- Khởi tạo resource tối thiểu trong constructor.
- Bắt đầu hoạt động ở `SmartLifecycle.start()` hoặc điểm lifecycle phù hợp.
- Khi start thất bại, chủ động rollback.
- Khi stop, ngừng nhận việc và chờ/cancel tasks có hạn.
- Khi destroy, giải phóng resource còn lại.

### 10.2. SmartLifecycle và thứ tự stop

Với nhiều lifecycle components, Spring có thể stop theo `phase` đảo chiều và quan hệ dependency:

```text
START:
DatabaseConnection (phase -100)
        ↓
JobConsumer (phase 100)

STOP:
JobConsumer (phase 100)
        ↓
DatabaseConnection (phase -100)
```

Đây là mô hình minh họa khi các bean được đăng ký/điều phối đúng.

Nếu `JobConsumer` cần database để checkpoint trong lúc shutdown, việc stop consumer trước database rất quan trọng. Chỉ đóng toàn bộ connections trong một `@PreDestroy` ngẫu nhiên có thể làm job chưa kết thúc.

**Trong lỗi refresh rất sớm**, không thể giả định đầy đủ các phase/start/stop đã hoàn tất. Component đã tự mở tài nguyên trước khi lifecycle processor nhận diện cần đặc biệt cẩn thận.

## 11. @PreDestroy, DisposableBean và destroyMethod khi app fail

Ba callback destruction tiêu chuẩn cho cùng một bean có thứ tự thường là:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method trong bean definition nếu khác và được đăng ký.

Nhưng cần nhớ chúng chỉ có ý nghĩa khi bean được Spring quản lý và đã được tạo đến trạng thái container có thể đăng ký destruction callback.

Ví dụ:

```java
@Component
class TemporaryCache implements DisposableBean {

    @PreDestroy
    public void clear() {
        System.out.println("cache.preDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("cache.disposableBeanDestroy");
    }
}
```

Đây là snippet cần import `Component`, `DisposableBean` và `jakarta.annotation.PreDestroy`. Nó không chứng minh mọi lỗi startup đều gọi hai callback; nếu bean chưa từng tạo hoặc chưa hoàn tất tạo thì không có bảo đảm.

Không dùng cả ba cơ chế chỉ để “cho chắc” vì có thể gây đóng resource trùng. Thay vào đó, xác định **một điểm sở hữu cleanup** và dùng callback phù hợp.

### 11.1. Prototype không được tự hủy

Spring tạo prototype bean khi cần nhưng không tự theo dõi destruction của từng instance giống singleton. Nếu prototype giữ file handle, object nhận prototype phải chủ động đóng.

Đây là bẫy cả khi startup thành công lẫn khi startup fail: thêm `@PreDestroy` vào prototype không tự biến nó thành resource tự giải phóng.

### 11.2. Lazy bean chưa từng được tạo

Nếu bật `spring.main.lazy-initialization=true` hoặc đặt `@Lazy` trên bean, một singleton chưa được yêu cầu có thể **không có instance** khi startup fail. Không có instance thì không có destructor để chạy. Đây là hành vi đúng, không phải cleanup bị bỏ sót.

Nếu bean đã được tạo và đăng ký trong container, destructor có thể được thực hiện khi context hủy singleton theo đường lỗi.

## 12. Làm gì khi cleanup cũng ném exception?

Khi cả **operation** và **cleanup** đều lỗi, phải ưu tiên giữ **nguyên nhân khởi động thất bại**, không vô tình thay bằng một IOException từ `close()`.

Với Java, `try-with-resources` tự động giữ lỗi chính và gắn lỗi đóng dưới dạng **suppressed exception**.

Ví dụ Java 17 thuần, có thể chạy độc lập:

```java
public class SuppressedFailureDemo {

    static final class Resource implements AutoCloseable {

        @Override
        public void close() {
            System.out.println("resource.close");
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("startup failed");
        } catch (RuntimeException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println(
                    "suppressed=" + failure.getSuppressed().length);
            System.out.println(
                    "suppressedType=" +
                    failure.getSuppressed()[0].getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac SuppressedFailureDemo.java
java SuppressedFailureDemo
```

Output chính xác:

```text
resource.close
primary=startup failed
suppressed=1
suppressedType=IllegalStateException
```

Giải thích:

- Lỗi chính `IllegalArgumentException("startup failed")` phát sinh trong block.
- Khi rời block, Java gọi `close()` và nhận thêm `IllegalStateException`.
- Java giữ lỗi chính và gắn lỗi cleanup dưới dạng suppressed.
- Bằng cách này, người xử lý lỗi vẫn truy vết được **vì sao startup thất bại trước**, và **cleanup sai ở bước nào sau**.

Với `finally` thủ công, nếu `close()` ném exception mà không được xử lý, nó có thể che lỗi startup gốc. Dùng `try-with-resources` khi có thể, hoặc `addSuppressed` trong những luồng cleanup phức tạp.

### 12.1. Có nên nuốt mọi lỗi trong close()?

Không. Destructor nên có chiến lược **best effort** và ghi nhận lỗi phù hợp, nhưng không được tự kết luận việc đóng luôn thành công. Khi không thể giải phóng connection/lease, hệ thống vận hành cần có telemetry và cơ chế recovery.

Cách phù hợp:

- Log loại lỗi và resource identifier đã phân loại an toàn.
- Không log password/token/connection string.
- Đặt thời gian chờ hữu hạn.
- Giữ root cause của startup failure.
- Nếu cleanup error có thể gây data loss, báo động theo mức độ ưu tiên thích hợp.
- Tránh retry vô hạn trong shutdown.

## 13. ExitCodeGenerator khi có nhiều nguồn mã lỗi

Một ứng dụng có thể đăng ký nhiều `ExitCodeGenerator` beans hoặc truyền generators vào `SpringApplication.exit(...)`. Theo Javadoc Boot 3.3, những generators có thể được sắp theo `Ordered` hoặc `@Order`, và **mã khác 0 đầu tiên theo thứ tự** được sử dụng.

Ví dụ:

```java
@Bean
ExitCodeGenerator validationExitCode() {
    return () -> 0;
}

@Bean
ExitCodeGenerator jobExitCode() {
    return () -> 12;
}
```

Đây là snippet trong `@Configuration`, cần import `Bean` và `ExitCodeGenerator`. Nó mô tả hai generator, **không phải một contract đảm bảo generator nào luôn chạy trước** khi chưa có thứ tự khai báo rõ.

Một lựa chọn tốt hơn là có **một thành phần quyết định kết quả batch**, hoặc một policy có thứ tự rõ, thay vì nhiều generator trả mã không nhất quán.

**Không nhầm:** `ExitCodeGenerator` bean cho đường `SpringApplication.exit(context)` khác với việc **exception implements ExitCodeGenerator** khi Boot xử lý startup failure. Chúng dùng chung interface nhưng được tập hợp ở **những thời điểm khác nhau**.

## 14. Xử lý lỗi trước SpringApplication.run

Nếu validation xảy ra ngay tại `main` **trước khi Boot tạo context**, có thể dùng mã thoát tường minh ở ranh giới chương trình.

Ví dụ Java 17 thuần:

```java
public final class PreflightCli {

    public static void main(String[] args) {
        int code = execute(args);
        System.exit(code);
    }

    private static int execute(String[] args) {
        if (args.length != 1 || !"--check".equals(args[0])) {
            System.err.println("Usage: java PreflightCli --check");
            return 2;
        }

        System.out.println("preflight.ok");
        return 0;
    }
}
```

Chạy:

```bash
javac PreflightCli.java
java PreflightCli --check
```

Output:

```text
preflight.ok
```

Với lời gọi sai:

```bash
java PreflightCli --unknown
```

Phần stderr:

```text
Usage: java PreflightCli --check
```

Và process trả mã 2. Đây là một chương trình Java **không sử dụng Spring Boot**, cố tình đặt validation trước bootstrap để phân biệt với `ApplicationRunner` vốn được gọi sau refresh.

Khi tích hợp vào ứng dụng Spring Boot, có thể thực hiện preflight đơn giản trước `SpringApplication.run(...)` và chỉ bắt đầu Boot khi đầu vào đủ điều kiện. Nhưng cần tránh cấp phát tài nguyên khó đóng ở preflight; nếu đã mở tài nguyên, hãy dùng `try-with-resources`.

### 14.1. Tại sao không dùng ApplicationRunner cho mọi validation?

`ApplicationRunner` chạy **sau khi context refresh**. Nếu một tham số phải hợp lệ **trước khi tạo bean đắt tiền hoặc mở web server**, kiểm tra trong runner có thể quá muộn. Với cấu hình dạng property, cân nhắc `@ConfigurationProperties` validation; với argument CLI đơn giản, preflight ở `main` cũng có thể hợp lý.

Tuy nhiên, **phải phân biệt preflight lỗi trước context** với **runner lỗi sau refresh** khi đánh giá resource cleanup.

## 15. FailureAnalyzer và thông báo hướng dẫn sửa lỗi

Spring Boot có hệ thống `FailureAnalyzer` để biến những exception phổ biến thành thông báo startup failure dễ hành động, thường gồm:

```text
APPLICATION FAILED TO START

Description:
...

Action:
...
```

Ví dụ port HTTP đã được dùng có thể tạo một failure analysis mô tả nguyên nhân và hướng xử lý. Đây là **giao diện chẩn đoán**, không phải một cơ chế dọn tài nguyên hay đặt exit code duy nhất.

Có thể viết custom `FailureAnalyzer` khi một domain exception cần mô tả rõ hơn. Tuy nhiên một số analyzers được Boot nạp qua metadata/hạ tầng sớm, không phải chỉ thêm `@Component` tùy ý rồi kỳ vọng nó luôn được gọi trong mọi lỗi trước context.

**Nguyên tắc thiết kế:**

- `FailureAnalyzer` trả lời: *Lỗi gì và làm sao sửa?*
- `ExitCodeGenerator`/`ExitCodeExceptionMapper` trả lời: *Process báo status nào?*
- `ApplicationFailedEvent` trả lời: *Ai cần quan sát lỗi khởi động?*
- Bean destructor/`AutoCloseable` trả lời: *Ai giải phóng tài nguyên?*

Không dùng một cơ chế để thay thế cả ba cơ chế còn lại.

## 16. Lỗi xảy ra khi đóng context: thứ tự stop và destroy

Với context đã khởi động những lifecycle components, `close()` thường thực hiện:

```text
ContextClosedEvent
      |
      v
LifecycleProcessor.onClose()
      |
      +-- Dừng SmartLifecycle beans theo phase
      +-- Chờ stop(Runnable) trong giới hạn
      |
      v
Destroy singleton beans
      |
      +-- @PreDestroy
      +-- DisposableBean.destroy()
      +-- custom destroyMethod
      |
      v
Context close completes
```

Tuy nhiên trong **refresh failure**, trạng thái lifecycle có thể chỉ mới hoàn tất một phần. Vì vậy không nên khẳng định mọi phase stop được chạy trong mọi lỗi trước refresh. Spring cố cleanup các singleton đã tồn tại, nhưng những task do code tạo sớm ngoài lifecycle vẫn cần sở hữu riêng.

### 16.1. stop(Runnable) phải báo hoàn tất

Một `SmartLifecycle` dừng bất đồng bộ cần gọi `callback.run()` **sau khi thật sự hoàn tất**, không phải ngay sau khi gửi tín hiệu dừng.

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingWork();

    completionFuture.whenComplete((value, failure) -> {
        try {
            running = false;
        } finally {
            callback.run();
        }
    });
}
```

Đây là **pseudo-code**: cần định nghĩa `stopAcceptingWork`, `completionFuture` và `running` trong implementation thật.

Nếu callback không được gọi, lifecycle processor có thể chờ đến timeout của shutdown phase. Nhưng timeout không thể bảo đảm background task đã thực sự kết thúc; có thể tới lượt destruction khi task vẫn còn đang dùng dependency.

### 16.2. Shutdown timeout

Spring Boot 3.3 hỗ trợ:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là thời gian chờ **mỗi phase** trong lifecycle shutdown, không phải một deadline chắc chắn cho mọi cleanup. Nhiều phase, destructor khác và thời gian scheduler/container đều có thể làm tổng thời gian lớn hơn.

Nếu process bị môi trường hạ tầng giết trước khi hết cleanup, không còn bảo đảm destructor hoàn tất. Khi chạy trên Kubernetes hoặc hệ thống orchestration khác, cần phối hợp grace period với deadline riêng của ứng dụng.

## 17. Vì sao ApplicationFailedEvent không phải “cuối cùng mọi thứ đã đóng”?

Trong mã nguồn Spring Boot 3.3, failure handler tính exit code, thông báo run listeners về failure, report nguyên nhân và đóng context. Vì vậy listener nhận `ApplicationFailedEvent` **có thể chạy khi một số singleton vẫn còn tồn tại**.

Đây là lý do:

- Không coi event này là tín hiệu tất cả resource đã release.
- Không cố sử dụng repository hoặc client có thể đang ở trạng thái lỗi/đang đóng.
- Không tạo thêm thread dài hạn từ failure listener.
- Không dùng failure listener để tự gọi `System.exit`.
- Không gọi lặp `context.close()` trong listener nếu không có lý do đặc biệt; Boot đang điều phối failure cleanup.

Nếu cần ghi nhận rằng **cleanup đã hoàn tất**, hãy dùng điểm quan sát/metrics ở bên sở hữu resource hoặc wrapper process/test, thay vì suy luận từ việc nhận event failure.

## 18. Kiểm tra chính xác exit code trong test end-to-end

Một unit test gọi trực tiếp method `getExitCode()` chỉ chứng minh **đối tượng trả số đúng**. Nó không chứng minh tiến trình Java thực sự thoát với status đó.

Cần phân tầng kiểm thử:

### 18.1. Unit test cho mã lỗi

```java
StartupRejectedException failure = new StartupRejectedException();
System.out.println(failure.getExitCode());
```

Đoạn này cần class `StartupRejectedException` từ demo mục 5 và nằm trong method/test có quyền truy cập package phù hợp. Kết quả là:

```text
23
```

Nhưng test này không tạo context, không kiểm tra cleanup.

### 18.2. Integration test cho bean cleanup

Một integration test có thể khởi động context độc lập với resource demo, kích hoạt runner thất bại và quan sát marker `resource.close`.

Cần lưu ý:

- Test runner có thể không dùng default uncaught-exception handling của `main`.
- Việc `run(...)` ném exception không có nghĩa JVM của test được thoát.
- Không gọi `System.exit` trong test process.
- Có thể dùng một recorder/`AtomicBoolean` để kiểm tra resource `close` được gọi, thay vì parse toàn bộ logs.
- Tránh test dùng context cache chung nếu bạn cố tình tạo startup failure.

### 18.3. Process-level test cho exit status

Tạo JAR, chạy như một tiến trình con rồi chờ process kết thúc có timeout. Trong Java có thể dùng `ProcessBuilder` hoặc từ shell chạy `java -jar` để kiểm tra status.

Với demo:

```bash
java -jar build/libs/startup-failure-demo-1.0.0.jar
status=$?
printf '%s\n' "$status"
```

Nếu môi trường chạy Boot default failure handler trên main thread thông thường, status mong đợi là:

```text
23
```

Không dùng `./gradlew bootRun` như chứng cứ duy nhất cho mã 23, vì Gradle có thể báo mã của task/wrapper theo quy tắc riêng. Muốn kiểm tra Java process thì chạy **JAR trực tiếp**.

Trên Windows PowerShell, sau `java -jar ...`, đọc `$LASTEXITCODE`, không dùng `$?` như thay thế một cách không phân biệt.

### 18.4. Kiểm tra không rò rỉ tài nguyên

Các phép kiểm tra bổ sung:

- File/port/socket có được giải phóng sau startup failure không?
- DB pool active connections có trở về trạng thái phù hợp không?
- Background workers có còn nhận công việc không?
- Temporary files có cần được xóa hay giữ để phân tích sự cố?
- Lease/lock có deadline và cơ chế recovery khi process bị kill không?
- Cleanup exceptions có được giữ dưới dạng suppressed hoặc log riêng không?
- Có còn thông tin nhạy cảm trong failure report không?

**Thành công của một lần chạy test không chứng minh an toàn trong mọi kiểu crash.** Phải kết hợp code-level cleanup với idempotency và recovery ở tầng bên ngoài.

## 19. Những lỗi phổ biến khi xử lý startup failure

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Có log failure nhưng process exit 0 | `main` trả bình thường hoặc wrapper nuốt lỗi | Kiểm tra đường exception/exit và process-level status |
| Đã gọi `System.exit(1)` nhưng resource chưa đóng | Gọi exit quá sớm trong runner/callback | Để Spring đóng context, không exit ở giữa cleanup |
| `@PreDestroy` của bean lỗi không chạy | Bean chưa hoàn tất khởi tạo/đăng ký destructor | Cleanup các bước resource allocation ngay trong constructor/factory |
| Bean singleton khác đã tạo không được release | Thiếu destructor hoặc quản lý tài nguyên ngoài Spring | Thêm `@Bean(destroyMethod=...)`/`@PreDestroy` và xác nhận ownership |
| Prototype resource bị leak | Spring không tự hủy prototype instances | Caller dùng `try-with-resources`/`close` |
| `ApplicationFailedEvent` listener bean không chạy | Lỗi quá sớm, listener bean chưa được tạo | Đăng ký listener trước `run` |
| Failure listener truy cập context null | Lỗi trước tạo context | Kiểm tra `event.getApplicationContext() != null` |
| Exception close che mất startup exception | Cleanup ném lỗi trong `finally` | Dùng `try-with-resources`/`addSuppressed` |
| Runner sau vẫn được mong chạy dù runner trước lỗi | Lỗi làm chuỗi runner bị ngắt | Đừng đặt cleanup trọng yếu chỉ trong runner cuối |
| `SpringApplication.exit(context)` không được gọi sau lỗi | `run` không trả context | Phân biệt startup failure với chủ động exit sau thành công |
| ExitCodeExceptionMapper không xử lý lỗi env cực sớm | Mapper là bean, context chưa active | Dùng exception `ExitCodeGenerator` hoặc preflight ngoài context |
| Spring Boot tự report stack trace chứa token | Exception message/args chứa secret | Không ghép dữ liệu nhạy cảm vào exception; sanitize logs |
| App fail rồi nhưng thread không dừng | Tạo thread ngoài bean lifecycle | Quản lý executor bằng resource bean hoặc ownership tường minh |
| SmartLifecycle callback không hoàn thành | Thiếu `callback.run()` hoặc task block vô hạn | Sửa stop protocol, timeout và cancellation |
| App được báo Started trước lỗi trong runner | Started xảy ra trước runners | Theo dõi ApplicationReadyEvent/readiness |
| Vẫn còn lock sau khi SIGKILL | Không có shutdown hook | Sử dụng lease timeout/idempotency/recovery |
| Cleanup xảy ra hai lần | Resource được close thủ công và bởi container | Quy hoạch một owner; làm cleanup idempotent |
| Mã lỗi 23 thành mã 1 trong CI | CI/Gradle/wrapper chuyển mã | Kiểm tra Java process riêng và hợp đồng pipeline |

### 19.1. Quy trình chẩn đoán

1. Xác định **exception đầu tiên** và mốc lỗi: environment, create context, refresh, runner, ready hay runtime.
2. Xác định **tài nguyên đã được tạo** trước thời điểm đó; ai đang sở hữu chúng?
3. Kiểm tra bean đó đã **hoàn tất tạo** và được container đăng ký destructor chưa.
4. Nếu tài nguyên được mở trong constructor/`@Bean` mà lỗi trước return, kiểm tra rollback tại allocation site.
5. Nếu runner lỗi sau refresh, kiểm tra Spring Boot failure handler đã đóng context và gọi destructor phù hợp chưa.
6. Nếu resource là thread/executor, kiểm tra nó thật sự ngừng, không chỉ nhận signal.
7. Xác định cách tính exit code: exception `ExitCodeGenerator`, mapper bean hay `SpringApplication.exit` chủ động.
8. Chạy JAR trực tiếp, không chỉ xem log từ Gradle/IDE.
9. Kiểm tra có ai gọi `System.exit` quá sớm hoặc nuốt exception làm process báo 0 không.
10. Kiểm tra phần log failure có lộ password, token, connection URL hoặc user input không.
11. Test thêm tình huống cleanup cũng ném lỗi, không chỉ đường thành công.
12. Đối chiếu timeout với deadline của môi trường triển khai.

## 20. Chính sách bảo vệ bí mật trong log thất bại

Lỗi khởi động thường làm Spring Boot in nguyên nhân và stack trace. Đây là thông tin quý để debug, nhưng có thể chứa secret nếu code viết exception message thiếu cẩn thận.

Không nên:

```java
throw new IllegalStateException(
        "Cannot connect with token=" + apiToken);
```

Cách an toàn hơn:

```java
throw new IllegalStateException(
        "Required upstream authentication is unavailable");
```

Hai đoạn trên là snippets; biến `apiToken` giả định đã tồn tại. Đừng log:

- `ApplicationArguments.getSourceArgs()` nguyên dạng.
- Password/token/JDBC URL có chứa credential.
- Full environment hoặc property sources không được sanitize.
- Nội dung file cấu hình nhạy cảm.
- Stack trace của exception tự tạo mà message chứa secret.

Nên log những trường **đã biết là an toàn**: exception type, mã lỗi ứng dụng, tên config key không nhạy cảm và action mà operator có thể thực hiện.

**Cleanup cũng là điểm rủi ro leak:** nếu `close()` ném exception chứa URL/token, suppressed exception cũng có thể đi vào báo cáo. Cần thiết kế message của cả lỗi chính lẫn lỗi cleanup phù hợp với chính sách log.

## 21. Mức độ bảo đảm của graceful shutdown

Không có callback Java nào bảo đảm chạy khi:

- JVM bị `SIGKILL`/`kill -9`.
- Máy mất điện hoặc kernel crash.
- Process bị hủy cưỡng bức trước deadline.
- Runtime không thể cấp phát tài nguyên cần cho cleanup.
- Code mắc kẹt trong thao tác không thể hoàn tất trong thời gian shutdown.

Vì vậy với tài nguyên ngoài ứng dụng:

- Transaction nên có rollback/consistency policy ở DB.
- Distributed lock nên có lease/expiration.
- Message processing nên có idempotency và redelivery policy.
- Temporary files nên có janitor/reconciliation khi restart.
- External session nên có timeout/expiration bên server.
- Scheduler/job run nên có trạng thái restartable/checkpoint phù hợp.

**Graceful cleanup là tối ưu hóa an toàn trong điều kiện bình thường; crash recovery là hàng phòng thủ khi cleanup không chạy.** Phải có cả hai cho hệ thống quan trọng.

## 22. Bài tập thực hành

### Bài 1 — Lỗi sau khi refresh

Chạy demo mục 5. Dự đoán thứ tự marker:

```text
resource.open
runner.start
resource.close
```

Giải thích vì sao `resource.close` được gọi dù `SpringApplication.run` không trả về context thành công.

### Bài 2 — Lỗi trước bean return

Thay resource factory thành:

```java
@Bean(destroyMethod = "close")
DemoResource brokenResource() {
    DemoResource resource = new DemoResource();
    throw new IllegalStateException("failure before return");
}
```

Đây là biến thể **thay thế** cho factory cũ. Nếu không có code cleanup nội bộ, có chắc `resource.close` chạy không? **Không**: resource chưa được bàn giao cho Spring. Sửa bằng `try/catch` và `resource.close()` ở chỗ cấp phát.

### Bài 3 — Lỗi trong @PostConstruct

Tạo một bean mở file trong `@PostConstruct` rồi cố tình ném exception. Giải thích vì sao không được dựa vào `@PreDestroy` của **chính bean đó** để bảo vệ file đã mở nếu initialization fail trước khi destructor được đăng ký. Đưa việc mở file vào `try-with-resources` hoặc thiết kế roll-back ngay trong initialization.

### Bài 4 — ExitCodeGenerator

Đổi mã trong `StartupRejectedException.getExitCode()` từ 23 thành 42. Build lại JAR, chạy trực tiếp và kiểm tra shell status. Đừng coi message log “42” là thay thế cho kiểm tra `$?` / `$LASTEXITCODE`.

### Bài 5 — ExitCodeExceptionMapper

Tạo exception `InvalidInputException` không implement `ExitCodeGenerator` và thêm một mapper bean trả 64 nếu cause chain có loại đó. Thử lỗi **sau refresh trong runner**, rồi so sánh với lỗi **trước khi context active**. Giải thích vì sao mapper có thể không sẵn sàng trong trường hợp sớm.

### Bài 6 — Suppressed exception

Chạy `SuppressedFailureDemo`. Vì sao có hai lỗi nhưng chỉ một `catch(RuntimeException)` và `suppressed=1`? Viết lại bằng `finally` sai để xem lỗi cleanup có thể che lỗi gốc, rồi sửa bằng `addSuppressed`.

### Bài 7 — Shutdown với background executor

Đăng ký `WorkerGroup` bằng `@Bean(destroyMethod="close")`. Cho runner ném exception. Quan sát việc gọi `shutdown` và xử lý task in-flight; đừng chỉ kiểm tra thread count ngay tại thời điểm startup fail.

### Bài 8 — Lỗi trước main SpringApplication

Thêm preflight kiểm tra một option bắt buộc **trước** `SpringApplication.run`. Nếu option sai, in usage an toàn và trả exit 2. Cần làm gì với những file/socket đã mở trước preflight?

### Bài 9 — Test không làm chết JVM test runner

Thay vì gọi `System.exit(23)` trong JUnit, kiểm tra exception, flags cleanup và việc Spring Boot báo exit code; sau đó chạy JAR như process con để kiểm tra mã thoát thật.

## 23. Checklist trước khi đưa ứng dụng vào vận hành

- [ ] Đã xác định các giai đoạn startup có thể thất bại.
- [ ] Mọi resource đều có owner rõ ràng.
- [ ] Bean singleton sở hữu resource có destructor được đăng ký.
- [ ] Resource mở trong constructor/factory được rollback khi initialization fail.
- [ ] Không dựa vào `@PreDestroy` của bean chưa hoàn tất khởi tạo.
- [ ] Prototype và resource tạo ngoài Spring được caller đóng.
- [ ] Không khởi chạy background thread mà thiếu shutdown/cancellation policy.
- [ ] Không gọi `System.exit` trong runner, destructor hoặc failure listener.
- [ ] Exit status khác 0 khi startup thất bại trong process mode.
- [ ] Các mã lỗi ứng dụng có policy và tài liệu.
- [ ] Đã phân biệt exception `ExitCodeGenerator` với `SpringApplication.exit(context)`.
- [ ] Mapper bean không được xem là sẵn sàng ở mọi failure stage.
- [ ] Early failure listener được đăng ký trước `run` nếu phải nhận lỗi sớm.
- [ ] Listener không giả định context khác `null`.
- [ ] Cleanup không che exception chính, có suppressed errors phù hợp.
- [ ] Error messages không chứa secret.
- [ ] Có timeout cho shutdown và external calls.
- [ ] Có policy cho failure khi shutdown cũng bị lỗi.
- [ ] Đã kiểm tra SIGTERM và timeout của orchestrator.
- [ ] Có cơ chế recovery khi SIGKILL/crash.
- [ ] Test thật exit status bằng `java -jar`, không chỉ xem log hoặc Gradle.
- [ ] Không nhầm `ApplicationStartedEvent` với hoàn tất runner/`ApplicationReadyEvent`.
- [ ] Đã test cả lỗi trước context, giữa refresh và sau refresh.

## 24. Tổng kết

1. Khi startup fail, **Spring Boot xử lý failure và đóng context nếu đã được tạo**, còn Spring Framework có cơ chế dọn những singleton đã tạo khi refresh thất bại. Điều đó bảo vệ nhiều bean-managed resources nhưng **không bảo vệ mọi resource đang được mở dở**.
2. **`@PreDestroy`, `DisposableBean` và `destroyMethod`** dùng để giải phóng những bean đã được container quản lý đúng cách. Tài nguyên trong constructor/factory method **chưa bàn giao** cần cleanup trực tiếp bằng `try/catch/finally` hoặc `try-with-resources`.
3. **`ExitCodeGenerator` trên exception** phù hợp để gắn mã lỗi với nguyên nhân startup failure. **`ExitCodeExceptionMapper`** là bean ánh xạ exception nhưng có giới hạn nếu context chưa active. **`SpringApplication.exit(context)`** phục vụ trường hợp đã có context và chủ động exit, không phải lệnh gọi thay cho run thất bại.
4. **`ApplicationFailedEvent`** hữu ích để quan sát startup failure, nhưng context có thể `null` và listener dạng bean có thể không tồn tại ở lỗi rất sớm. Event **không xác nhận cleanup đã hoàn tất**.
5. **`System.exit` thuộc ranh giới tiến trình**, không thuộc destructor. Gọi exit sớm trong callback có thể làm mất cleanup cần thiết; process-level test mới xác nhận exit status thật.
6. **Lỗi cleanup không nên che lỗi chính**; giữ suppressed exceptions, thiết lập timeout và log không chứa secret.
7. **Không có callback nào chạy trong mọi kiểu crash**. Với tài nguyên quan trọng, phối hợp lifecycle cleanup và cơ chế recovery/idempotency/lease expiration.

### Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication, Application Exit và Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): application events, `ExitCodeGenerator`, thông báo startup failure.
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `run(...)` và `exit(...)`.
- [Spring Boot 3.3 — ExitCodeGenerator Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html): hợp đồng trả mã lỗi.
- [Spring Boot 3.3 — ExitCodeExceptionMapper Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html): ánh xạ exception sang exit code.
- [Spring Boot 3.3 — ApplicationFailedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html): context có thể `null` khi lỗi trước tạo context.
- [Spring Framework 6.1 — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh error, destroyBeans, close context.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean` và custom destruction callbacks.
- [Java 17 — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): tự động đóng resource và suppressed exceptions.
