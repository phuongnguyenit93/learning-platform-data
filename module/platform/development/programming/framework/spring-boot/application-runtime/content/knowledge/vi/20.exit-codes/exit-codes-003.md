# Phân biệt đóng context với gọi System.exit trong Spring Boot

## 1. Vấn đề: ứng dụng ngừng phục vụ khác với tiến trình JVM kết thúc

Trong Spring Boot Application Runtime, ta thường cần dừng ứng dụng sau một batch job, kết thúc một lệnh CLI với mã trạng thái, hoặc shutdown web server an toàn. Ba thao tác nhìn có vẻ giống nhau nhưng có **phạm vi và hợp đồng khác nhau**:

- `context.close()` đóng một `ApplicationContext`: dừng các thành phần lifecycle do Spring quản lý, gọi destruction callback và giải phóng tài nguyên của **context đó**.
- `SpringApplication.exit(context)` là helper của Spring Boot để **đóng context và tính một exit code** từ các `ExitCodeGenerator` liên quan. Nó **trả về int**, không tự gọi `System.exit`.
- `System.exit(code)` yêu cầu **toàn bộ JVM** bắt đầu shutdown, chạy các shutdown hook đã đăng ký và kết thúc process với mã trạng thái được truyền. Lời gọi này **không trả về bình thường**.

Đây là bài thuộc nhóm **Mã thoát**. Cần phân biệt rõ: đóng resource ở phạm vi Spring, yêu cầu shutdown JVM ở phạm vi process, và trả mã trạng thái cho hệ điều hành là **ba trách nhiệm khác nhau**.

### Kết luận một dòng

~~~text
context.close()             -> đóng một Spring ApplicationContext
SpringApplication.exit(ctx) -> đóng context + tính/đưa về exit code
System.exit(code)           -> khởi động shutdown TOÀN BỘ JVM với status code
~~~

**Không được suy ra** rằng gọi `context.close()` tức là hệ điều hành nhận exit code khác 0, hoặc gọi `System.exit(7)` có nghĩa mọi resource Spring đã đóng thành công. Muốn một tác vụ CLI trả mã lỗi có kiểm soát, mẫu chính thức thường là:

~~~java
int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là **đoạn minh họa**, cần biến `context` là ApplicationContext hợp lệ và import `SpringApplication`. Code chạy hoàn chỉnh có ở mục 7. Khi chỉ muốn dừng một bean/consumer để có thể start lại, hãy dùng cơ chế `Lifecycle` riêng; `System.exit` không phải công cụ tạm dừng.

## 2. Ba tầng phạm vi: bean/context, JVM, hệ điều hành

~~~text
Host / Kubernetes / shell / CI
       |
       v
    JVM process (một PID)
       |
       +-- Spring ApplicationContext A
       |     +-- beans singleton, SmartLifecycle, DataSource...
       |
       +-- Spring ApplicationContext B (nếu có)
       |     +-- beans và resource riêng của B
       |
       +-- Thread không thuộc Spring, native library, shutdown hooks...
       |
       v
    JVM shutdown -> process exit status -> shell / orchestrator
~~~

**`contextA.close()` chỉ sở hữu việc đóng A**. Nó không tự đóng B, không mặc nhiên kết thúc mọi non-daemon thread hoặc native resource được tạo ngoài các bean của A. Một chương trình có thể đóng context A, tiếp tục dùng context B và vẫn hoạt động bình thường.

Ngược lại, **`System.exit(7)` áp dụng cho cả JVM**, không chỉ context hiện tại. Nó bắt đầu đường JVM shutdown, vì thế các context khác và thư viện cùng tiến trình cũng bị ảnh hưởng.

Sau khi process thực sự thoát, hệ điều hành hoặc bộ điều phối có thể quan sát **exit status**. Trên nhiều hệ thống, `0` quy ước thành công và giá trị khác 0 thể hiện một kết quả không thành công hoặc tình huống được định nghĩa riêng. Không được dùng số exit code một cách tùy tiện nếu scheduler/CI/Kubernetes đang dựa vào nó để quyết định retry.

### “Đã đóng context” và “JVM đã thoát” không có quan hệ một-một

- Một JVM **có thể tiếp tục chạy** sau khi một context được đóng, vì còn thread khác, context khác hoặc code main còn xử lý.
- Một JVM **có thể thoát bình thường** sau khi main kết thúc và không còn non-daemon thread, dù code không gọi `System.exit`; shutdown hooks đã đăng ký có thể thực hiện cleanup.
- `System.exit` có thể khiến JVM thoát dù còn non-daemon thread đang xử lý, nhưng JVM vẫn chạy shutdown hooks trước khi halt theo đường chuẩn.
- Trường hợp `Runtime.halt`, `SIGKILL`, crash hoặc mất điện không có cam kết chạy hooks; **không dùng chúng như cơ chế graceful shutdown**.

## 3. Bảng so sánh chính xác

| Câu hỏi | `context.close()` | `SpringApplication.exit(context)` | `System.exit(code)` |
| --- | --- | --- | --- |
| Thuộc API | Spring Framework | Spring Boot | Java/JVM |
| Phạm vi | Một `ApplicationContext` | Context chỉ định và logic exit code của Boot | Toàn JVM process |
| Dừng `SmartLifecycle` thuộc context? | Có trong close bình thường | Có vì đóng context | Qua shutdown hook/logic khác nếu đã đăng ký |
| Gọi `@PreDestroy`/`DisposableBean.destroy()`? | Có với bean container sở hữu | Có vì đóng context | Không trực tiếp; Boot shutdown hook có thể đóng context |
| Hủy singleton/BeanFactory? | Có | Có | Không trực tiếp, phụ thuộc hooks đã đăng ký |
| Tính mã lỗi theo `ExitCodeGenerator`? | Không | **Có** | Không; dùng số `code` do caller truyền |
| Tự gửi mã exit cho OS? | Không | **Không** | **Có** khi JVM kết thúc |
| Giá trị trả về | `void` | `int` | Không trả về bình thường |
| Tác động tới context khác cùng JVM? | Không tự đóng context khác | Không tự đóng context khác | Có, toàn process shutdown |
| Có thể tiếp tục dòng code sau lời gọi? | Có | Có | Không trên đường JVM exit thông thường |
| Có thể giữ JVM sống sau lời gọi? | Có | Có | Không sau khi shutdown hoàn tất |
| Được dùng trong unit/integration test? | Phù hợp khi test sở hữu context | Phù hợp với test exit-code logic cẩn thận | Tránh dùng trong JVM test runner |
| Hợp với batch CLI muốn trả non-zero? | Chưa đủ | Tính code; cần cơ chế trả status ra OS | Bước cuối tại process entry point |
| Hợp với web service production đang phục vụ? | Khi thực sự yêu cầu shutdown | Hiếm khi cần trực tiếp | Không nên gọi từ controller/service tùy tiện |

**Lưu ý cột `System.exit`:** Spring Boot mặc định đăng ký JVM shutdown hook để đóng context được tạo bằng `SpringApplication`. Vì vậy trong cấu hình bình thường, `System.exit` có thể **gián tiếp** dẫn tới Spring destruction callbacks. Điều đó không có nghĩa `System.exit` tự gọi API `@PreDestroy` hoặc biết mọi Spring bean; nếu shutdown hook bị tắt/không đăng ký, cách suy luận ấy không còn đúng.

## 4. context.close() thực sự làm gì?

`org.springframework.context.ConfigurableApplicationContext` có method `close()`. Trên `AbstractApplicationContext`, đường close bình thường bao gồm những bước khái quát:

~~~text
Code gọi context.close()
   |
   +-- Bắt đầu đóng ApplicationContext
   +-- Phát ContextClosedEvent
   |     +-- Listener biết shutdown đã bắt đầu
   |
   +-- LifecycleProcessor.onClose()
   |     +-- Stop Lifecycle / SmartLifecycle đang chạy
   |     +-- Phối hợp phase và callback dừng
   |
   +-- destroyBeans()
   |     +-- @PreDestroy
   |     +-- DisposableBean.destroy()
   |     +-- @Bean(destroyMethod="close"/"shutdown")
   |
   +-- closeBeanFactory() / hoàn tất close
   |
   v
context.isActive() == false (sau khi close hoàn tất)
~~~

**`ContextClosedEvent` được phát trước khi tất cả destruction callbacks chạy**. Listener nhận event đó không nên khẳng định database pool, executor hoặc client đã đóng xong ngay tại thời điểm event.

Một số nguyên tắc:

1. `close()` hủy cached singleton do context sở hữu; tài nguyên prototype được tạo và bàn giao không tự động nhận destroy callback chỉ vì context đóng.
2. Spring có thể gọi `SmartLifecycle.stop(Runnable)` để phối hợp graceful stop trước khi destroy bean. Callback phải được báo khi stop thực tế hoàn tất.
3. Lời gọi `close()` lặp lại trên context đã đóng được Spring Framework thiết kế để bỏ qua, không hủy cùng bean lần thứ hai.
4. Đóng **child context** không tự đóng parent context; owner tài nguyên dùng chung phải được xác định đúng.
5. Sau khi context đóng, không coi các bean còn giữ tham chiếu bên ngoài là tài nguyên còn hợp lệ; có thể đã bị destroy.
6. `close()` **không phải `System.exit`** và không tự đặt status code cho scheduler hoặc shell.

### Vì sao close không nhất thiết làm JVM thoát?

Một Java process không kết thúc chỉ vì một object Spring đã đóng. Nếu còn các **non-daemon thread**, một context khác hoặc một loop ở main, JVM tiếp tục chạy. Nếu mọi non-daemon thread đã kết thúc, JVM có thể thoát tự nhiên sau khi hoàn thành shutdown sequence.

Ví dụ ý tưởng:

~~~java
ConfigurableApplicationContext context = launchSpringApp();
context.close();
doOtherWorkOutsideSpring();
~~~

Đây là **pseudocode minh họa**, không phải file Java độc lập. `doOtherWorkOutsideSpring()` có thể vẫn chạy nếu không bị exception. Không có `System.exit` nào được gọi ở đây.

Trong test framework, điều này là lý do nên đóng **đúng context do test sở hữu**, nhưng **không được gọi `System.exit`** từ test để “dọn nhanh”; lời gọi đó sẽ kết thúc cả JVM chạy test.

## 5. System.exit(int) thực sự làm gì?

Java 17 định nghĩa `System.exit(status)` là lối gọi thuận tiện tới `Runtime.getRuntime().exit(status)`. Nó yêu cầu JVM **bắt đầu shutdown sequence**, không chỉ đóng một bean hay Spring context. Trên đường bình thường, method này **không trả về**.

~~~text
Thread gọi System.exit(7)
   |
   +-- JVM bắt đầu shutdown sequence
   +-- Khởi chạy shutdown hooks đã đăng ký
   |     +-- Spring Boot hook: đóng context nếu có đăng ký
   |     +-- Hook khác của ứng dụng/thư viện
   |     +-- Thứ tự giữa các JVM shutdown hooks KHÔNG bảo đảm
   |
   +-- Đợi các shutdown hooks hoàn thành
   +-- JVM halt và process trả status được yêu cầu
   |
   v
OS / shell nhận exit status (ví dụ 7)
~~~

**Điểm tinh tế:** JVM shutdown hooks được bắt đầu theo thứ tự **không xác định** và có thể chạy **đồng thời**. Không nên tạo hai hook mà một hook giả định Spring context đã đóng trước khi hook còn lại chạy. Nếu cần thứ tự đóng tài nguyên nội bộ, hãy sử dụng các lifecycle/destroy callbacks của Spring trong **cùng đường close có quản lý**.

Javadoc Java còn cảnh báo:
- Hook có thể chạy vào thời điểm nhiều dịch vụ/thread đã đang shutdown.
- Hook có thể deadlock hoặc block, khiến `System.exit` không tiến tới halt.
- Khi shutdown sequence đã bắt đầu, việc đăng ký/gỡ hook mới có thể ném `IllegalStateException`.
- Gọi `System.exit` từ một shutdown hook đang chạy là nguy hiểm; có thể gây chờ vô hạn tùy trạng thái runtime.
- Một số hệ điều hành/container chỉ dành một khoảng thời gian hữu hạn cho shutdown.
- Bị `SIGKILL`, `Runtime.halt` hoặc crash không bảo đảm hook chạy.

**Không phải “System.exit là force kill ngay lập tức”.** Nó bắt đầu một đường shutdown có hook. Nhưng cũng **không có bảo đảm tuyệt đối graceful completion**: hook có thể hỏng, bị timeout bởi orchestrator hoặc resource ngoài JVM cần cơ chế phục hồi riêng.

### Mã truyền cho System.exit có ý nghĩa gì?

~~~java
System.exit(0);   // Caller yêu cầu mã 0.
System.exit(7);   // Caller yêu cầu mã 7.
System.exit(42);  // Caller yêu cầu mã 42.
~~~

Các dòng trên là minh họa cú pháp, không phải ba lệnh nên chạy liên tiếp. Lệnh đầu tiên khiến chương trình đi vào shutdown và **không chạy các dòng sau** theo đường bình thường.

Quy ước thông dụng là `0` thành công, khác 0 không thành công. Tuy nhiên:
- Ý nghĩa chi tiết của `7` hoặc `42` do ứng dụng/đơn vị vận hành định nghĩa.
- Một số OS/shell có quy tắc biểu diễn/mã hóa trạng thái riêng; trên Unix nhiều shell hiển thị 8 bit thấp của exit status.
- Process chết vì signal, container bị OOMKilled hoặc tool wrapper lỗi có thể được hệ thống điều phối diễn giải khác với một lần `System.exit(code)` bình thường.
- Không nhầm **HTTP status code** 500/503 với **process exit code**. Chúng là hai protocol ở hai tầng khác nhau.

## 6. SpringApplication.exit() nối hai thế giới như thế nào?

Spring Boot cung cấp:

~~~java
public static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators);
~~~

Đây là chữ ký minh họa của `org.springframework.boot.SpringApplication.exit(...)`. Khi gọi với context còn active, API đóng context nếu có thể và trả về **mã exit** dựa trên:
- Các `ExitCodeGenerator` được truyền trực tiếp.
- Các bean trong context implement `ExitCodeGenerator`.
- Quy tắc thứ tự generator và xử lý lỗi tương ứng.

Theo Spring Boot 3.5, nếu có nhiều generator, **mã non-zero đầu tiên theo thứ tự đã sắp xếp** được chọn; có thể điều khiển thứ tự bằng `Ordered` hoặc `@Order` khi cần.

### Interface ExitCodeGenerator

~~~java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

Đây là minh họa chữ ký, không phải định nghĩa cần copy vào project. Spring Boot có sẵn `org.springframework.boot.ExitCodeGenerator`.

Ví dụ trả về mã 7 rồi đóng context:

~~~java
int code = SpringApplication.exit(context, () -> 7);
System.out.println("Requested exit code: " + code);
~~~

Đoạn trên cần biến `context` và import Spring Boot. **Nó có thể in tiếp sau lời gọi**, vì `SpringApplication.exit` **không gọi `System.exit`**.

Nếu sau đó method main kết thúc và JVM thoát bình thường mà **không có lời gọi `System.exit(7)` hoặc một cơ chế truyền status tương đương**, shell có thể quan sát mã **0**, dù biến Java `code` là 7.

### Mẫu CLI chính thức: tính mã rồi gửi cho JVM

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là đoạn mẫu, cần class `MyBatchApplication`, import và bean/config phù hợp. Đối với CLI, có thể triển khai `ExitCodeGenerator` như một bean để trả mã dựa trên kết quả job.

Một cách khác khi cần policy bên ngoài:

~~~java
int code = SpringApplication.exit(context, () -> 7);
System.exit(code);
~~~

**Sự khác biệt quan trọng:** `SpringApplication.exit` chịu trách nhiệm đóng Spring context và xác định code; `System.exit` chịu trách nhiệm làm code đó thành **process exit status**. Nếu ứng dụng của bạn nằm trong một host khác (ví dụ test runner, desktop app, application server hoặc plugin), **đừng tự gọi System.exit** chỉ vì một module Spring muốn dừng.

### ExitCodeGenerator bean và exception

Spring Boot cho phép đăng ký generator từ container:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
~~~

Đây là đoạn cấu hình minh họa cần đặt trong class có `@Configuration` hoặc `@SpringBootApplication` và import. Trong đường kết thúc có chủ đích, `SpringApplication.exit(context)` có thể lấy mã 42 từ bean này.

Ngoài ra:
- Exception có thể implement `ExitCodeGenerator` để biểu diễn mã lỗi trong các đường xử lý startup failure của Boot.
- `ExitCodeExceptionMapper` có thể ánh xạ exception thành mã lỗi khi Spring Boot xử lý thất bại.
- `ExitCodeEvent` có thể được phát khi exit code được xác định trong các đường lifecycle tương ứng.
- Một startup exception có thể xảy ra **trước khi main nhận được biến context**; lúc đó không thể giả định luôn có context để tự gọi close trong main.

**Không nhầm**: cơ chế phát sinh mã lỗi trong Spring Boot **không tự bảo đảm OS nhìn thấy đúng con số** nếu main hoặc host không đưa code đó ra ngoài bằng cách thích hợp. Tổ chức cần xác định policy exit code thống nhất cho scheduler/CI.

## 7. Demo hoàn chỉnh: 4 cách kết thúc cùng một ứng dụng Java 17+

Ví dụ sau sử dụng **Spring Boot 3.5.16**, Java 17+ và không tạo web server. Nó có một singleton resource do Spring quản lý, một `ApplicationRunner` và bốn chế độ kết thúc:

- `close`: chỉ gọi `context.close()`.
- `spring-exit`: gọi `SpringApplication.exit(context, () -> 7)` nhưng **không** gọi `System.exit`.
- `system-exit`: gọi trực tiếp `System.exit(7)` và để **shutdown hook mặc định của Spring Boot** đóng context.
- `combined`: gọi `SpringApplication.exit(context, () -> 7)` để đóng và tính code, rồi gọi `System.exit(code)`.

**Lưu ý:** chương trình này cố ý chứa `System.exit(7)` chỉ để thực hành ở một process **riêng**. Không gọi demo bằng cách trực tiếp thực thi method main trong cùng JVM của IDE test runner hoặc một server đang phục vụ việc khác.

### 7.1. Cấu trúc project

~~~text
exit-boundary-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/exitboundary/
                └── ExitBoundaryApplication.java
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>exit-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter` đủ cho demo CLI; không cần `spring-boot-starter-web`, cơ sở dữ liệu hay Docker. Dùng JDK 17+ và Maven phù hợp phiên bản Boot.

### 7.3. Java đầy đủ có thể biên dịch

Tệp `src/main/java/com/example/exitboundary/ExitBoundaryApplication.java`:

~~~java
package com.example.exitboundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExitBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitBoundaryApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // Giữ nguyên shutdown hook mặc định của Spring Boot.
        ConfigurableApplicationContext context = application.run(args);

        String mode = context.getEnvironment()
                .getProperty("demo.mode", "close");

        System.out.println("AFTER_RUN mode=" + mode
                + " active=" + context.isActive());

        switch (mode) {
            case "close" -> {
                context.close();
                System.out.println("AFTER_CONTEXT_CLOSE active="
                        + context.isActive());
            }
            case "spring-exit" -> {
                int code = SpringApplication.exit(context, () -> 7);
                System.out.println("AFTER_SPRING_EXIT code=" + code
                        + " active=" + context.isActive());
            }
            case "system-exit" -> {
                System.out.println("CALL_SYSTEM_EXIT code=7");
                System.out.flush();
                System.exit(7);
            }
            case "combined" -> {
                int code = SpringApplication.exit(context, () -> 7);
                System.out.println("CALL_SYSTEM_EXIT code=" + code);
                System.out.flush();
                System.exit(code);
            }
            default -> {
                context.close();
                throw new IllegalArgumentException(
                        "Unknown demo.mode: " + mode);
            }
        }
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner demoRunner(DemoResource resource) {
        return args -> System.out.println(
                "RUNNER resourceClosed=" + resource.isClosed());
    }

    public static final class DemoResource implements AutoCloseable {
        private boolean closed;

        public DemoResource() {
            System.out.println("RESOURCE_OPEN");
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("RESOURCE_CLOSE");
        }
    }
}
~~~

Đây là **toàn bộ file Java** cùng pom.xml cần để chạy bốn chế độ. Không có method placeholder, fake class hay dòng lệnh phụ thuộc một server bên ngoài.

**Vì sao ví dụ đúng mục đích?**

1. `DemoResource` là singleton do Spring sở hữu qua `@Bean(destroyMethod = "close")`; constructor in `RESOURCE_OPEN`.
2. `ApplicationRunner` inject resource đó, bảo đảm bean được tạo trước khi runner in `RUNNER resourceClosed=false`.
3. `SpringApplication.run` kết thúc thành công rồi main mới chọn mode. Như vậy bài tập **không thử dừng JVM giữa một bean constructor hoặc giữa startup event**.
4. `--demo.mode=...` là command-line property do Spring Boot đưa vào `Environment` theo mặc định, nên có thể đọc bằng `getProperty`.
5. `context.close()` và `SpringApplication.exit` đều làm Spring dọn DemoResource, nhưng chỉ helper thứ hai trả một `int`.
6. Chế độ `system-exit` dựa vào **Boot JVM shutdown hook mặc định**. Nếu hook bị tắt bằng `setRegisterShutdownHook(false)`, không còn cơ sở đảm bảo tài nguyên được đóng ở nhánh này.
7. Chế độ `combined` thực hiện đóng Spring context trước khi yêu cầu JVM exit, làm thứ tự cleanup ở cấp Spring explicit và dễ kiểm chứng.
8. `DemoResource.close()` idempotent; nếu Boot hook còn tồn tại và kiểm tra context đã đóng, Spring không hủy cùng singleton lần hai.
9. `System.out.flush()` giúp thông điệp ngay trước System.exit được đẩy ra output trong ví dụ; nó **không bảo đảm** mọi log của framework hay dữ liệu ngoài process đã được lưu bền vững.

### 7.4. Biên dịch chương trình

Trong thư mục chứa `pom.xml`:

~~~bash
mvn package
~~~

Có thể chạy:

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=close
~~~

Nên thử bằng `java -jar` thay vì chỉ dựa vào `mvn spring-boot:run`, vì plugin Maven hoặc IDE có thể dùng một process wrapper và truyền/diễn giải exit code không giống việc chạy JAR trực tiếp.

### 7.5. Trường hợp A — chỉ đóng context

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=close
~~~

Những dòng **do mã ví dụ in** có thứ tự:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=close active=true
RESOURCE_CLOSE
AFTER_CONTEXT_CLOSE active=false
~~~

Đây là output marker, chưa tính banner và log của Spring Boot. Giải thích:
- Context đã khởi động và runner chạy trước khi main đi tới câu lệnh close.
- `DemoResource.close()` được gọi qua destruction callback.
- Sau close, context không active; nhưng dòng `AFTER_CONTEXT_CLOSE` **vẫn chạy**, vì đây là một method Java bình thường trả về.
- Trong demo không-web, khi main kết thúc và không còn non-daemon thread, process thường thoát **tự nhiên với exit status 0**.
- **Không có mã exit khác 0 nào được yêu cầu** dù context đã đóng.

### 7.6. Trường hợp B — SpringApplication.exit tính 7 nhưng không gọi System.exit

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=spring-exit
~~~

Marker dự kiến:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=spring-exit active=true
RESOURCE_CLOSE
AFTER_SPRING_EXIT code=7 active=false
~~~

Giải thích:
- `SpringApplication.exit(context, () -> 7)` lấy exit code từ generator lambda.
- Helper đóng context, nên `RESOURCE_CLOSE` xuất hiện.
- Nó trả `int 7` cho caller, vì thế dòng `AFTER_SPRING_EXIT` **vẫn chạy**.
- **Nếu main kết thúc bình thường như demo**, process exit status thường là **0**, không phải 7. Giá trị `7` ở đây chỉ nằm trong Java, chưa được chuyển cho JVM.

Đây là trường hợp dễ nhầm nhất: **một biến exit code chứa 7 không tự làm shell nhận 7**.

### 7.7. Trường hợp C — System.exit(7) trực tiếp

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=system-exit
~~~

Marker dự kiến với **shutdown hook mặc định của Spring Boot được bật**:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=system-exit active=true
CALL_SYSTEM_EXIT code=7
RESOURCE_CLOSE
~~~

Giải thích:
- Khi `System.exit(7)` chạy, main không tiếp tục sang dòng nào phía sau nó.
- JVM bắt đầu shutdown và gọi Boot shutdown hook. Hook đóng context, dẫn tới `RESOURCE_CLOSE`.
- Process yêu cầu exit status **7**, khác với trường hợp chỉ đóng context.
- Không có một dòng `AFTER_SYSTEM_EXIT` vì lời gọi không trả về trên đường bình thường.

**Cần giới hạn kỳ vọng:** marker `RESOURCE_CLOSE` đến từ Boot hook theo cấu hình mặc định. Nếu có hook khác hoặc log asynchronous, **không dựa vào thứ tự của các thông điệp giữa những hook khác nhau**. Ví dụ chỉ có một tài nguyên in-memory của Spring, nên không có các hook tùy biến cạnh tranh in marker.

### 7.8. Trường hợp D — đóng Spring trước, rồi exit JVM với code

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
~~~

Marker dự kiến:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=combined active=true
RESOURCE_CLOSE
CALL_SYSTEM_EXIT code=7
~~~

Giải thích:
- `SpringApplication.exit` tính 7 và đóng context trước, nên `RESOURCE_CLOSE` xuất hiện trước.
- Sau đó chương trình mới in `CALL_SYSTEM_EXIT` và gọi `System.exit(7)`.
- Process exit status là **7**.
- Shutdown hook của Boot có thể được khởi chạy khi JVM thoát, nhưng không có lần đóng thứ hai hữu hiệu đối với context đã đóng.
- Đây là cách dễ lý giải và kiểm thử nhất khi cần **cleanup có kiểm soát + status code xác định** cho batch job.

### 7.9. Bảng tổng kết demo

| Mode | Context được close? | Code từ SpringApplication.exit | Có gọi System.exit? | Process status thường quan sát |
| --- | --- | --- | --- | --- |
| `close` | Có, explicit | Không gọi helper | Không | 0 nếu main kết thúc bình thường |
| `spring-exit` | Có, qua helper | 7 | Không | 0 nếu main kết thúc bình thường |
| `system-exit` | Qua Boot shutdown hook mặc định | Không gọi helper | `System.exit(7)` | 7 |
| `combined` | Có, trước JVM exit | 7 | `System.exit(7)` | 7 |

Bảng giả định chạy Java 17+ bình thường, không có SecurityManager chặn exit, hook không bị treo và process không bị kill cưỡng bức. Nó mô tả **exit status của process Java**, không nhất thiết là exit code mà Maven/IDE wrapper trả về.

### 7.10. Kiểm tra process exit code trên hệ điều hành

**Bash / zsh / các shell POSIX tương thích:**

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
echo $?
~~~

Kết quả dòng cuối thường là:

~~~text
7
~~~

**Windows PowerShell:**

~~~powershell
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
$LASTEXITCODE
~~~

Kết quả:

~~~text
7
~~~

**Windows cmd.exe:**

~~~bat
java -jar target\exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
echo %ERRORLEVEL%
~~~

Kết quả:

~~~text
7
~~~

Nếu thử mode `spring-exit` thay vì `combined`, chương trình demo vẫn in `AFTER_SPRING_EXIT code=7`, nhưng khi JVM kết thúc bình thường các shell thường báo **0**. Đây là kiểm chứng thực tế nhất cho sự khác biệt giữa *mã trong biến Java* và *mã process trả về*.

**Lưu ý với PowerShell:** `$LASTEXITCODE` chứa mã của native process cuối cùng. Hãy đọc ngay sau lệnh Java, trước khi chạy một native command khác làm thay đổi giá trị.

## 8. Spring Boot JVM shutdown hook: tiện nhưng có giới hạn

Theo tài liệu Spring Boot 3.5, mỗi `SpringApplication` mặc định đăng ký shutdown hook với JVM để đảm bảo `ApplicationContext` được đóng khi JVM đi vào shutdown trên đường được hỗ trợ.

~~~text
System.exit(7)
   |
   v
JVM shutdown
   |
   +-- Spring Boot shutdown hook
   |       |
   |       +-- ApplicationContext.close()
   |               +-- SmartLifecycle.stop(...)
   |               +-- @PreDestroy / destroyMethod
   |
   +-- Các JVM shutdown hook khác (thứ tự không xác định)
   |
   v
Process kết thúc với code 7
~~~

Tùy cấu hình, Boot có API `SpringApplication.setRegisterShutdownHook(boolean)`. Nếu chủ động vô hiệu hóa hook, **mã của bạn phải chịu trách nhiệm explicit cleanup** trước khi gọi System.exit hoặc khi JVM tự kết thúc.

### Tại sao không nên dùng hook để làm mọi nghiệp vụ cleanup?

JVM shutdown là giai đoạn nhạy cảm:
- Hook khác có thể đã đang dừng tài nguyên cần thiết cho hook của bạn.
- Hook nên ngắn, thread-safe và tránh đợi vô hạn.
- Có thể không chạy nếu process bị kill cưỡng bức.
- Kết nối mạng hoặc broker ngoài process có thể không trả lời.
- Một hook ném exception có thể dừng riêng thread hook; không bảo đảm hệ thống tự đổi process code theo ý bạn.

Nếu thứ tự thực sự quan trọng, hãy đặt cleanup trong Spring bean lifecycle như `SmartLifecycle`, `@PreDestroy` và destroyMethod; để Spring điều phối khi context close. Tránh viết nhiều hook JVM độc lập rồi dùng timing của chúng để điều phối client/pool/consumer.

### Nếu có nhiều ApplicationContext?

Spring có thể đăng ký shutdown hook cho từng context được quản lý. Khi JVM thoát, mỗi hook/handler có thể yêu cầu context tương ứng đóng. Nhưng JVM không cung cấp thứ tự giữa các hook độc lập. Một Spring context **không tự đóng parent context** khi close; nếu chia sẻ resource giữa context, ownership phải được thiết kế rõ.

Trong demo này chỉ có **một** context để tránh điều kiện bất định.

## 9. Khi nào JVM thực sự thoát nếu không gọi System.exit?

Java có hai con đường phổ biến vào shutdown:

1. **Tự nhiên:** các non-daemon thread đã kết thúc; JVM có thể bắt đầu shutdown.
2. **Chủ động:** một thread gọi `System.exit(status)` / `Runtime.exit(status)`.

Vì vậy, với batch CLI đơn giản, sau `context.close()` và sau khi main trả về, không còn non-daemon thread nào thì JVM sẽ kết thúc. Nhưng một executor tự tạo, một timer, một client hoặc một thread ứng dụng không được dọn vẫn có thể khiến process chạy mãi.

### Context.close không phải cách ép thread lạ dừng

Ví dụ ý tưởng:

~~~java
Thread worker = new Thread(() -> runForever());
worker.start();
context.close();
~~~

Đây là **pseudocode**: `runForever()` và `context` chưa định nghĩa. Nếu worker là non-daemon và không được dừng, JVM có thể tiếp tục sống sau khi context đã đóng. Cần thiết kế cancellation/interrupt, `ExecutorService.shutdown()` và đợi termination theo thời hạn phù hợp, không lấy `System.exit(0)` để che một leak rồi tuyên bố shutdown hoàn hảo.

### System.exit cũng không chữa được lỗi resource ownership

`System.exit` có thể làm process biến mất trong khi vẫn còn tasks chưa commit, messages chưa ack hoặc file chưa flush. Shutdown hook chỉ là cơ hội dọn dẹp; nếu một operation quan trọng phải đảm bảo không mất dữ liệu, cần transaction, idempotency key, durable queue, checkpoint và recovery policy riêng.

**Phân biệt hai yêu cầu vận hành:**

- “**Không còn process chạy**” → kiểm tra PID/process exit, timeout, orchestrator.
- “**Mọi tác vụ đã kết thúc an toàn**” → kiểm tra graceful shutdown, in-flight work, transaction completion và resource cleanup.

Hai việc này liên quan nhưng không đồng nghĩa.

## 10. ExitCodeGenerator và lập chính sách mã thoát

Trong job CLI, exit code có thể là một hợp đồng công khai:

| Code | Ý nghĩa ví dụ | Hệ thống gọi có thể làm gì |
| ---: | --- | --- |
| 0 | Job thành công | Ghi nhận hoàn thành |
| 2 | Đầu vào không hợp lệ | Không retry tự động, yêu cầu sửa dữ liệu |
| 3 | Dependency tạm lỗi | Retry có backoff, giới hạn |
| 7 | Job nghiệp vụ thất bại theo contract demo | Ghi nhận lỗi, cảnh báo |
| 10 | Không đạt điều kiện nghiệp vụ | Xử lý theo tài liệu của job |

Đây là **bảng quy ước ví dụ**, không phải mã tiêu chuẩn Spring Boot hay mã OS bắt buộc. Mỗi sản phẩm nên có một tài liệu mapping code ổn định, tránh thay đổi ý nghĩa sau khi scheduler/CI đã phụ thuộc vào nó.

### Dùng một bean ExitCodeGenerator

Một bean đơn giản:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

Nếu context chứa bean này và bạn gọi `SpringApplication.exit(context)`, Spring Boot có thể dùng generator đó để tính code. Trong dự án thật, bean thường phản ánh kết quả job được lưu trong một state holder hoặc service có lifecycle rõ.

**Không cần `ExitCodeGenerator` nếu ứng dụng chỉ muốn trả 0 hoặc tự chọn code từ một biến:** bạn có thể truyền lambda cho `SpringApplication.exit(context, () -> code)` như ví dụ. Nhưng nếu logic mã thoát được chia sẻ qua nhiều component, bean generator giúp contract tường minh hơn.

### Có nhiều generator?

Spring Boot 3.5 nói các generator được sắp xếp theo `Ordered` hoặc `@Order`, và giá trị non-zero đầu tiên được dùng. Vì thế:
- Không dựa vào thứ tự đăng ký bean ngẫu nhiên.
- Tránh nhiều generator trả các mã khác nhau khi chưa thống nhất precedence.
- Test case có nhiều lỗi cùng lúc để biết code nào sẽ được chọn.
- Đừng coi “mã số lớn hơn luôn thắng” hoặc “mã cuối cùng thắng” là quy tắc mặc định.

### ExitCodeExceptionMapper và lỗi lúc khởi động

Khi `SpringApplication.run` thất bại trước khi trả context cho main:
- Code trong main **chưa có một biến context hoàn chỉnh** để gọi `SpringApplication.exit(context)`.
- Spring Boot có đường xử lý startup failure và có thể sử dụng exception implement `ExitCodeGenerator` hoặc `ExitCodeExceptionMapper` để xác định mã thích hợp.
- Các callback cleanup khả dụng phụ thuộc bean/resource nào đã được tạo thành công và giai đoạn lỗi.
- Không viết `catch (Exception e) { System.exit(0); }` vì biến một startup failure thành tín hiệu thành công cho scheduler.

Một application entry point nên xử lý lỗi một cách có chủ đích: log ngữ cảnh an toàn, bảo toàn nguyên nhân và trả mã phù hợp; không nuốt stack trace rồi mặc định “success”.

## 11. Web service production: có nên tự gọi System.exit?

Thường **không nên gọi `System.exit` từ controller, service hoặc endpoint quản trị**. Đó là API cấp JVM, không có cách chỉ kết thúc “một request” hay “một Spring module” bằng nó.

Nếu một HTTP endpoint gọi `System.exit(0)`:
- Toàn bộ process có thể đi vào shutdown giữa lúc các request khác đang xử lý.
- Những non-daemon thread khác cũng không giữ process sống lâu dài sau shutdown.
- Response của request yêu cầu exit có thể không gửi xong.
- Load balancer/Kubernetes có thể chưa kịp rút pod khỏi traffic.
- Nếu status là 0, scheduler/orchestrator có thể coi việc ứng dụng bất ngờ dừng là bình thường, che mất lỗi.

Để vận hành web app, ưu tiên:
1. Orchestrator gửi tín hiệu dừng (thường `SIGTERM`) theo cơ chế deployment.
2. Spring Boot shutdown hook/handler đóng context trên đường JVM shutdown bình thường.
3. Spring web server graceful shutdown ngừng nhận request mới và cho in-flight requests một khoảng thời gian hoàn tất.
4. Các `SmartLifecycle` khác dừng consumer/worker theo phase.
5. Resource owner đóng pool/client sau khi borrower dừng.
6. Nếu quá deadline, orchestrator có thể force-kill; cần recovery cho dữ liệu chưa commit.

Nếu cần một endpoint “yêu cầu shutdown”, thiết kế nó với phân quyền, audit, không tự gọi `System.exit` giữa request thread và có chính sách điều phối an toàn; trong nhiều hệ thống cách tốt nhất là để nền tảng deployment quản lý.

### Graceful shutdown trong Spring Boot 3.5

Theo tài liệu Spring Boot 3.5, graceful shutdown được bật mặc định cho các embedded server được hỗ trợ và xảy ra **khi ApplicationContext đóng**. Timeout theo phase có thể cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

`server.shutdown=graceful` ghi rõ ý định; property còn lại đặt thời gian chờ cho các lifecycle phases. Đây **không phải cam kết** mọi request chắc chắn hoàn tất trước 30 giây; logic ứng dụng phải có timeout/cancellation riêng và Kubernetes có termination grace period tương ứng.

Chú ý khác biệt giữa server:
- Một số server ngừng nhận connection mới ở tầng network.
- Server khác có thể trả HTTP 503 cho request mới khi đang graceful shutdown.
- Khi HTTP server đã dừng, readiness endpoint có thể **không trả response nào**.
- Không dùng một kết quả probe HTTP đơn lẻ để chứng minh mọi destroy callback đã chạy.

## 12. Tín hiệu từ hệ điều hành, kill và shutdown hook

### SIGTERM

Trên Unix/container, tín hiệu `SIGTERM` thường yêu cầu process chấm dứt theo cách có thể thực hiện shutdown hooks nếu JVM có cơ hội xử lý bình thường. Với Spring Boot mặc định, đó là một đường phổ biến dẫn tới context close.

Tuy nhiên:
- Process có thể cài signal handler đặc biệt.
- Docker entrypoint dạng shell không `exec` có thể làm signal không tới JVM như dự kiến.
- Orchestrator có thể giới hạn deadline và sau đó gửi `SIGKILL`.
- Kết quả exit status khi chết do signal phụ thuộc shell/runtime/container và không giống tuyệt đối một lời gọi `System.exit(15)`.

### SIGKILL / Runtime.halt

`SIGKILL` và `Runtime.halt` không chạy chu trình shutdown hook bình thường. Không thể bảo đảm `@PreDestroy`, `SmartLifecycle.stop` hay `DemoResource.close()` sẽ được gọi. Với dữ liệu quan trọng cần giao thức recovery độc lập.

### Container exit status

Kubernetes hiển thị container termination reason và exit code. Ví dụ:
- Một process Java tự gọi `System.exit(7)` có thể kết thúc với exit code 7 và gây quyết định restart tùy workload policy.
- OOMKilled thường có termination reason đặc biệt; mã process hiển thị có thể khác theo runtime.
- Pod bị `SIGTERM` rồi timeout có thể dẫn tới force termination, không phải graceful close hoàn tất.
- Startup probe/readiness/liveness là những tín hiệu khác với process exit code; **readiness 503 không bằng exit code 503**.

Cần kiểm tra log, sự kiện Kubernetes và process status cùng nhau thay vì suy một giá trị từ giá trị còn lại.

## 13. Vấn đề khó: shutdown hooks và thứ tự cleanup

### 13.1. Hai shutdown hook Java không có thứ tự bảo đảm

Ví dụ:

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("HOOK_A")));

Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("HOOK_B")));
~~~

Đây là đoạn minh họa cú pháp. Không được khẳng định HOOK_A luôn xuất hiện trước HOOK_B, vì JVM khởi chạy các hooks theo thứ tự không xác định và chúng có thể chạy đồng thời.

Một hook Spring Boot có thể đang đóng context khi một hook tự viết cố dùng bean từ context ấy. Đây là race nguy hiểm. Nếu logic của bạn cần database/client Spring, hãy thực hiện nó **trong đúng lifecycle của Spring bean trước destroy**, không phụ thuộc timing của hook JVM tự tạo.

### 13.2. Gọi System.exit từ bên trong shutdown hook?

Tránh. Khi JVM đang shutdown, gọi `Runtime.exit` thêm có thể chặn vô hạn tùy giai đoạn. Không bao giờ thiết kế hook A yêu cầu System.exit để “buộc” hook B xong. Nếu cần forced stop vì hook treo, đó là chính sách của bên ngoài tiến trình với deadline, chứ không phải một lời gọi exit chồng chéo thiếu kiểm soát.

### 13.3. Dọn resource trước rồi mới đưa exit code là rõ nhất

Với một CLI/batch mà main **sở hữu toàn bộ context**, quy trình dễ kiểm tra:

~~~text
Run batch
  |
  +-- Thu thập kết quả và code mong muốn
  +-- SpringApplication.exit(context) hoặc context.close()
  |      +-- SmartLifecycle stop
  |      +-- Destroy managed resources
  +-- System.exit(code) tại process entry point
  |
  v
Scheduler nhận code
~~~

**Không** gọi `System.exit` trong một `ApplicationRunner` khi startup vẫn đang chạy trừ khi bạn thật sự hiểu sự kiện startup/cleanup và lý do kỹ thuật. Thông thường nên để runner kết thúc, main thu thập kết quả và quyết định mã thoát.

## 14. Pattern thực tế cho batch job

### Pattern A — job thành công và muốn JVM thoát tự nhiên

~~~java
try (ConfigurableApplicationContext context =
         SpringApplication.run(MyBatchApplication.class, args)) {
    // Spring runner/job đã thực thi trong SpringApplication.run().
}
~~~

Đây là mẫu minh họa, cần class `MyBatchApplication` và import. `try-with-resources` đóng context; nếu main kết thúc bình thường và không còn non-daemon thread, JVM thoát với mã thành công thường là 0.

Dùng khi:
- Job có thể coi kết quả bình thường là success.
- Không cần truyền mã business khác 0.
- Không cần cưỡng chế JVM exit và muốn giữ code dễ test.

### Pattern B — có ExitCodeGenerator và cần trả code cho scheduler

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Dùng khi:
- Scheduler/CI phụ thuộc process exit code.
- Spring Boot có bean `ExitCodeGenerator` hoặc explicit generator.
- Code thuộc **process entry point**, không phải thư viện hoặc test đang chạy trong JVM của ứng dụng khác.

### Pattern C — mã thoát tính trong main

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int resultCode = evaluateJobResult();
int exitCode = SpringApplication.exit(
        context, () -> resultCode);
System.exit(exitCode);
~~~

Đây là **pseudocode minh họa**: `evaluateJobResult()` và `MyBatchApplication` cần định nghĩa. Lưu ý biến được capture trong lambda phải effectively final theo Java. Khi code phụ thuộc kết quả job, nên có state/result object rõ ràng, tránh đọc trạng thái của bean đã bị destroy sau `SpringApplication.exit`.

### Pattern D — ứng dụng host dùng Spring như một module

~~~java
ConfigurableApplicationContext moduleContext = createModuleContext();
try {
    runModule(moduleContext);
} finally {
    moduleContext.close();
}
continueHostApplication();
~~~

Đây là pseudocode. Trong plugin, IDE, test runner hoặc desktop app, module **không được tự `System.exit`** vì sẽ giết cả host. Code host quyết định việc kết thúc JVM. Đây là một ranh giới ownership tương tự resource ownership nhưng ở cấp process.

### Pattern E — nhiều job con

Nếu một JVM chạy nhiều job trong cùng process, không nên có một job con gọi `System.exit`. Mỗi job trả một result object cho orchestrator nội bộ; orchestrator tổng hợp và tại **entry point cuối cùng** mới quyết định đóng các context cần thiết và process exit status.

## 15. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân phổ biến | Cách sửa |
| --- | --- | --- |
| In `exitCode=7` nhưng shell báo 0 | Chỉ gọi `SpringApplication.exit`, không gọi `System.exit` | Nếu process entry point cần code, dùng `System.exit(code)` |
| Gọi `context.close()` nhưng process vẫn chạy | Non-daemon thread/context khác còn sống | Tìm thread leak, đóng resource do owner quản lý |
| Gọi `System.exit(0)` trong runner làm job ngừng đột ngột | System.exit tác động toàn JVM | Đưa quyết định exit về main, chạy sau khi job hoàn thành |
| Resource không được @PreDestroy khi System.exit | Boot shutdown hook bị tắt, chưa đăng ký, hoặc process bị force-kill | Explicit close trước exit; xác minh shutdown path |
| Resource được close hai lần | Nhiều owner/hook cùng cleanup, không idempotent | Một owner rõ ràng và close idempotent |
| JVM shutdown treo | Hook deadlock, I/O không timeout, callback không bao giờ hoàn tất | Thread dump, timeout, tránh dependency vòng |
| Process bị kill nhưng không có log cleanup | SIGKILL/crash/OOM | Thiết kế recovery/lease ngoài JVM |
| Scheduler coi lỗi là thành công | Exit code 0 hoặc wrapper che code | Mapping code và kiểm tra thực tế process status |
| `System.exit` làm chết toàn bộ test suite | Unit test gọi process exit trong JVM test runner | Tách logic tính mã và dùng subprocess khi test System.exit |
| `ContextClosedEvent` đến nhưng resource chưa đóng | Event được phát trước destroy | Đo destruction callback thay vì event đơn thuần |
| Mã exit từ nhiều generator không như dự đoán | Thứ tự generator/first non-zero | Dùng Ordered/@Order, test precedence |
| Gọi exit từ controller không trả response đầy đủ | JVM shutdown giữa HTTP request | Để orchestrator điều phối shutdown |
| Process exit status không giống `echo $?` sau Maven | Maven/IDE wrapper trả status riêng | Chạy JAR bằng `java -jar` và đo trực tiếp |
| Mất job in-flight khi shutdown | Timeout/quá trình dừng chưa hoàn tất | Graceful drain, checkpoint/transaction và retry |
| Đóng một child context làm mất pool chia sẻ | Child tự đóng resource parent-owned | Sửa resource ownership, parent lifecycle độc lập |

### Chẩn đoán theo thứ tự

1. Xác định **ai gọi** thao tác: main, runner, listener, request handler, container orchestrator hay shutdown hook.
2. Xác định **mục tiêu**: dừng bean, đóng Spring context, trả code cho OS hay dừng toàn process.
3. Ghi log an toàn các mốc: request shutdown, ContextClosedEvent, SmartLifecycle stop, bean destroy, mã do ExitCodeGenerator trả.
4. Kiểm tra `ApplicationContext.isActive()` sau explicit close nếu code vẫn tiếp tục.
5. Nếu process vẫn sống, xem non-daemon threads và context khác; không chỉ tìm log “Spring context closed”.
6. Nếu process đã thoát, đọc **OS/container exit code thực tế** thay vì biến Java đã in.
7. Nếu không có cleanup, kiểm tra Boot shutdown hook, dấu hiệu SIGKILL/OOM/crash và thời gian termination.
8. Đối chiếu mã lỗi với contract của CI/scheduler; đừng đổi code nhằm “chữa” lỗi không có nguyên nhân rõ.

## 16. Bảo mật, độ tin cậy và khả năng kiểm thử

### Không dùng System.exit như cơ chế xử lý exception thông thường

Một library method nên **throw exception hoặc trả result**, không trực tiếp kết thúc JVM. Gọi `System.exit` làm người sử dụng library mất quyền quyết định retry, rollback, giao diện hiển thị lỗi và thứ tự cleanup.

Ngay cả trong CLI, người gọi cuối cùng nên quyết định code. Nếu lỗi không thể phục hồi, cần log context phù hợp trước khi chấm dứt, tránh vô tình ghi password, token hoặc stack trace chứa dữ liệu nhạy cảm.

### Kiểm thử System.exit ở subprocess

Đừng gọi trực tiếp mode `system-exit` trong JVM test runner. Test nên:
- Kiểm tra code/tình trạng context bằng method riêng **không** gọi System.exit.
- Khi thật sự cần xác minh exit status, chạy JAR trong **child process** qua `ProcessBuilder` hoặc framework test process phù hợp.
- Chờ process với timeout; đọc stdout/stderr để không bị nghẽn pipe.
- Đối chiếu `exitValue()` hoặc result của `waitFor()`, không chỉ log.
- Đảm bảo không bỏ lại subprocess khi test fail/timeout.

### Shutdown cần đúng ownership

Spring chỉ dọn resource được context quản lý và những resource có cleanup tích hợp. Tài nguyên tạo bằng `new Thread` hoặc client ngoài Spring mà không đăng ký dọn dẹp vẫn là trách nhiệm của code sở hữu. Đừng chuyển trách nhiệm ấy sang `System.exit` rồi coi như đã xử lý resource leak.

### Không lạm dụng force exit

`Runtime.halt(code)` bỏ qua shutdown hook bình thường nên có thể mất dữ liệu. Chỉ cân nhắc ở tầng điều phối khẩn cấp khi đã hiểu hậu quả; không đưa nó thành mẫu code ứng dụng trong bài học này.

## 17. Câu hỏi ôn tập

**Câu 1:** `context.close()` có tự trả mã 7 cho shell không?

**Trả lời:** Không. Nó đóng context và không yêu cầu process exit status 7. Nếu main kết thúc bình thường, shell thường thấy 0.

**Câu 2:** `SpringApplication.exit(context, () -> 7)` có kết thúc JVM không?

**Trả lời:** Không. Nó tính code, đóng context nếu có thể và trả `int 7`. Cần một lời gọi `System.exit(7)` hoặc cách tương đương ở cấp host để truyền code ra OS.

**Câu 3:** `System.exit(7)` có trực tiếp gọi `@PreDestroy` không?

**Trả lời:** Không. Nhưng Spring Boot mặc định có JVM shutdown hook đóng context, và đường close đó gọi destroy callbacks của managed singleton. Nếu hook tắt hoặc JVM bị kill cưỡng bức, không có đảm bảo cleanup.

**Câu 4:** Vì sao Spring Boot có shutdown hook?

**Trả lời:** Để khi JVM đi vào shutdown bình thường, application context được đóng và các lifecycle/destruction callbacks có cơ hội dọn resource.

**Câu 5:** JVM shutdown hook A luôn chạy trước hook B theo thứ tự addShutdownHook không?

**Trả lời:** Không. Java không bảo đảm thứ tự, chúng có thể chạy đồng thời. Cần dùng lifecycle của Spring để kiểm soát thứ tự đóng bean.

**Câu 6:** Vì sao `System.exit` có thể không kết thúc nhanh?

**Trả lời:** JVM đợi shutdown hooks hoàn thành. Hook bị deadlock hoặc block I/O có thể khiến quá trình dừng bị treo và orchestrator phải force-kill.

**Câu 7:** Gọi close khi còn non-daemon thread tự tạo, process có tự dừng ngay không?

**Trả lời:** Không chắc. Thread chưa kết thúc có thể giữ JVM sống. Cần quản lý cancellation và shutdown tài nguyên do ứng dụng sở hữu.

**Câu 8:** Có thể gọi `SpringApplication.exit` để lấy mã rồi vẫn chạy thêm code trong main?

**Trả lời:** Có. Method trả `int` như ví dụ mode spring-exit, trong khi System.exit không trả về bình thường.

**Câu 9:** `ExitCodeGenerator` bean trả 42, vì sao OS có thể vẫn thấy 0?

**Trả lời:** Vì Spring chỉ tính code. Nếu không truyền code đó tới System.exit hoặc cơ chế host tương đương, kết thúc bình thường có thể là 0.

**Câu 10:** Một controller Spring Boot nên gọi `System.exit(0)` để tự restart pod?

**Trả lời:** Không phải thiết kế mặc định an toàn. Nó giết cả process, có thể làm gián đoạn request khác và che lỗi bằng code 0. Nên dùng orchestration và shutdown policy có kiểm soát.

**Câu 11:** JVM bị SIGKILL thì Boot shutdown hook có chạy không?

**Trả lời:** Không được bảo đảm và thông thường không. Phải dùng transaction/checkpoint/lease/TTL/recovery cho tài nguyên ngoài.

**Câu 12:** Trong mode combined, thứ tự `RESOURCE_CLOSE` và `CALL_SYSTEM_EXIT` là gì?

**Trả lời:** RESOURCE_CLOSE trước vì SpringApplication.exit đóng context rồi trả code, sau đó main mới gọi System.exit.

**Câu 13:** Nếu chạy demo mode spring-exit và in code 7, lệnh `echo $?` trên Bash thường hiển thị gì?

**Trả lời:** 0, vì JVM kết thúc bình thường mà không được yêu cầu exit 7. Đó là mục đích cốt lõi của demo.

**Câu 14:** Đóng context con có tự đóng context cha không?

**Trả lời:** Không. Một lời gọi close của child không tự close parent. Ngược lại, System.exit áp dụng toàn process nên có thể khiến cả hai nhận shutdown theo hooks đã đăng ký.

**Câu 15:** `SpringApplication.exit` có chọn mã lớn nhất của tất cả generator không?

**Trả lời:** Không. Theo Boot 3.5, các generator được sắp theo order và giá trị non-zero đầu tiên được chọn.

## 18. Bài tập thực hành

### Bài tập A — nhìn thấy hai lớp “đóng”

Chạy mode `close` và `system-exit`. So sánh marker, exit status thực tế và nơi gọi cleanup. Giải thích tại sao code sau context.close được thực thi nhưng code sau System.exit thì không.

### Bài tập B — exit code không tự lan ra hệ điều hành

Chạy mode `spring-exit`. Thấy `AFTER_SPRING_EXIT code=7 active=false`. Ngay sau đó đọc `echo $?` hoặc `$LASTEXITCODE`; giải thích vì sao thường là 0. Chạy lại mode `combined` để thấy mã 7 thực sự được truyền ra.

### Bài tập C — đổi ExitCodeGenerator

Thay lambda `() -> 7` trong demo bằng `() -> 12`. Dự đoán marker và process status ở spring-exit và combined, rồi chạy kiểm tra. Viết mapping code 12 cho scheduler và giải thích khi nào retry.

### Bài tập D — bean ExitCodeGenerator

Thêm `@Bean ExitCodeGenerator` vào project với mã 5 và gọi `SpringApplication.exit(context)` không truyền lambda. Quan sát mã trả về; tiếp đó thử hai generator có `@Order` khác nhau để kiểm tra quy tắc first non-zero.

### Bài tập E — hook bật/tắt

Chỉ trong môi trường thử nghiệm, gọi `application.setRegisterShutdownHook(false)` trước `run`, rồi chạy mode system-exit. Quan sát resource destroy marker có còn xuất hiện không. Sau đó dùng mode combined để kiểm tra explicit SpringApplication.exit vẫn đóng context trước JVM exit. Không dùng hook disabled trong production mà không thay bằng cơ chế cleanup tương ứng.

### Bài tập F — thread không thuộc Spring

Tạo một non-daemon worker có điểm dừng theo interrupt/cancellation rõ ràng. Gọi context.close và xem process còn sống trong lúc worker chạy. Sau đó chỉnh code để worker được quản lý qua `SmartLifecycle` hoặc `ExecutorService` có shutdown/cancellation đúng. Test với timeout, không để thread loop vô hạn.

### Bài tập G — graceful shutdown web app

Tạo ứng dụng với `spring-boot-starter-web`, thêm endpoint long-running có giới hạn thời gian và bật graceful shutdown. Gửi tín hiệu shutdown bằng cơ chế OS/orchestrator, so sánh log graceful drain với trường hợp gọi System.exit từ một request handler. Không đưa ví dụ gọi exit trực tiếp vào endpoint production.

### Bài tập H — kiểm thử subprocess

Dùng `ProcessBuilder` hoặc script riêng để khởi chạy JAR mode close, spring-exit, combined và system-exit. Đọc stdout/stderr, đợi process với timeout, lấy exit code. Viết test matrix đối chiếu bốn mode, tách process status khỏi marker in trong Java.

## 19. Tài liệu chính thức

Đối chiếu API theo đúng phiên bản Spring Boot / Spring Framework / Java đang chạy:

- [Spring Boot 3.5 — SpringApplication, Application Exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): shutdown hook mặc định, `ExitCodeGenerator`, ví dụ `System.exit(SpringApplication.exit(...))`.
- [Spring Boot 3.5.16 — SpringApplication API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): `exit(ApplicationContext, ExitCodeGenerator...)` và `setRegisterShutdownHook`.
- [Spring Boot 3.5.16 — ExitCodeGenerator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeGenerator.html): method `getExitCode()`.
- [Spring Boot 3.5.16 — ExitCodeExceptionMapper API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeExceptionMapper.html): exception-to-code strategy.
- [Spring Framework 6.2 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `close()` và trách nhiệm giải phóng singleton.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): lifecycle phase, embedded server graceful shutdown và timeout.
- [Java SE 17 — System.exit(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)): JVM termination với process status.
- [Java SE 17 — Runtime.exit và addShutdownHook](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): thứ tự hook không xác định, shutdown sequence, rủi ro deadlock.

## 20. Checklist trước khi chọn cách kết thúc

1. Mục tiêu là **dừng một worker**, **đóng Spring context** hay **kết thúc toàn bộ JVM**?
2. Code hiện đang ở **main/process entry point**, trong một **bean**, hay trong một **thư viện/test runner**?
3. Có **context khác** hoặc non-daemon thread bên ngoài Spring đang dùng chung process không?
4. Tài nguyên cần đóng có được Spring quản lý và có **destruction callback** đúng không?
5. Nếu cần process code khác 0, ai **tính code**, ai **truyền code ra OS**?
6. Có `ExitCodeGenerator` bean hoặc exception mapper nào sẽ ảnh hưởng kết quả không?
7. Có nhiều JVM shutdown hooks và dependency về thứ tự giữa chúng không?
8. Có thể bị stop/close lặp lại, force-kill hoặc shutdown timeout không?
9. Với web app, readiness/drain/graceful shutdown và thời gian điều phối đã hợp lý chưa?
10. Scheduler/CI/Kubernetes cần xử lý mã lỗi như thế nào và có test process status thực không?
11. Nếu startup fail trước khi nhận context, có kế hoạch cleanup partial resource và báo lỗi không?
12. Có tránh gọi `System.exit` trong bean, request handler, test runner và thư viện không?

### Ghi nhớ cuối cùng

- `context.close()` **đóng Spring context**, không tự đặt JVM exit status và không bảo đảm toàn process kết thúc ngay.
- `SpringApplication.exit(context)` **đóng context và trả int code** từ `ExitCodeGenerator`; nó **không gọi System.exit**.
- `System.exit(code)` **yêu cầu toàn JVM shutdown**, kích hoạt registered shutdown hooks và trả mã cho OS khi quá trình kết thúc; method không trả về bình thường.
- Spring Boot mặc định có shutdown hook đóng context khi JVM shutdown, nhưng hook có thể bị tắt/không chạy khi forced termination.
- JVM shutdown hooks **không có thứ tự bảo đảm** và có thể đồng thời; resource cleanup có thứ tự nên nằm trong lifecycle của Spring.
- Mẫu CLI cần cả cleanup và code là **`System.exit(SpringApplication.exit(context))`** hoặc hai lệnh tương đương ở process entry point.
- Một biến Java chứa exit code 7 **không đồng nghĩa** shell nhận 7; cần đo mã process thực.
- Không lạm dụng `System.exit` trong web request, library hoặc test; dùng orchestration, graceful shutdown và chính sách recovery thích hợp.
