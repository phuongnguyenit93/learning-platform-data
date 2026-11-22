# CommandLineRunner với mảng tham số dòng lệnh

Trong Spring Boot, nhiều ứng dụng cần thực hiện một số công việc ngay sau khi Spring container khởi tạo: in thông tin khởi động, đọc tham số CLI, kiểm tra cấu hình, import dữ liệu hoặc kích hoạt một tác vụ batch. `CommandLineRunner` là một giao diện được Spring Boot cung cấp cho tình huống này.

Điểm đặc trưng của interface là phương thức:

```java
void run(String... args) throws Exception;
```

Tham số `String... args` chính là các đối số ứng dụng được chuyển từ lệnh khởi chạy vào chương trình. Trong method, `args` hoạt động như một mảng `String[]`. Runner có thể dựa vào từng phần tử để quyết định công việc cần làm.

Bài học này giải thích cách khai báo `CommandLineRunner`, đường đi của tham số từ terminal tới phương thức `run`, cách đọc và kiểm tra mảng, vai trò của runner trong lifecycle Spring Boot và những khác biệt quan trọng với `ApplicationRunner`.

## 1. CommandLineRunner là gì?

`CommandLineRunner` là functional interface của Spring Boot, thuộc package `org.springframework.boot`. Chữ ký chính của nó có dạng:

```java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Đây là dạng giản lược để tập trung vào method cần triển khai. Khi một bean của Spring implement interface này, Spring Boot sẽ gọi `run(...)` trong quá trình hoàn tất startup.

Các đặc điểm:

- Runner là một **Spring bean**; có thể nhận dependency qua constructor.
- Phương thức `run` được gọi sau khi application context đã refresh.
- Runner chạy trước khi Spring Boot phát `ApplicationReadyEvent`.
- Tham số `args` chứa các application arguments được chuyển vào `SpringApplication.run(...)`.
- Có thể đăng ký nhiều runner và sắp xếp thứ tự bằng `@Order` hoặc `Ordered`.
- Exception chưa được xử lý từ runner có thể làm startup thất bại.

Ví dụ use case: một ứng dụng chỉ để nhập dữ liệu từ CSV. Bạn muốn khởi tạo service/repository thông qua dependency injection rồi thực hiện thao tác import đúng một lần trong **mỗi lần khởi động ứng dụng**. Runner là một điểm thực thi phù hợp.

Tuy nhiên, “một lần mỗi lần khởi động” không phải “đúng một lần trên toàn cluster”: nếu có ba process cùng chạy, runner có thể được gọi tại cả ba process.

## 2. Mảng String... args trong Java

Dấu ba chấm `...` trong `String... args` là cú pháp varargs của Java. Trong thân method, tham số này có thể được dùng như một mảng chuỗi thông thường.

```java
@Override
public void run(String... args) {
    System.out.println("Số tham số: " + args.length);

    for (int i = 0; i < args.length; i++) {
        System.out.println("args[" + i + "] = " + args[i]);
    }
}
```

Các thao tác cơ bản:

- `args.length`: số phần tử.
- `args[0]`: phần tử đầu tiên, nếu tồn tại.
- `args[args.length - 1]`: phần tử cuối, nếu mảng không rỗng.
- `for (String arg : args)`: duyệt lần lượt.
- `Arrays.toString(args)`: biểu diễn mảng cho mục đích kiểm tra, nếu không chứa dữ liệu nhạy cảm.

Trong Java, varargs được biểu diễn bằng mảng ở runtime. Vì thế `String... args` và `String[] args` có hành vi gần như tương đương trong thân method, nhưng dạng varargs phản ánh đúng chữ ký API.

**Lưu ý quan trọng:** mảng có thể rỗng. Truy cập `args[0]` mà không kiểm tra độ dài sẽ dẫn đến `ArrayIndexOutOfBoundsException` khi không có đối số.

## 3. Ví dụ tối thiểu: in tham số lúc khởi động

Tạo lớp application:

```java
package com.example.cli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CliApplication {
    public static void main(String[] args) {
        SpringApplication.run(CliApplication.class, args);
    }
}
```

Tạo runner:

```java
package com.example.cli;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentsPrinter implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Argument count: " + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
```

Chạy ứng dụng:

```bash
java -jar app.jar hello spring boot
```

Phần output do runner tạo ra có dạng:

```text
Argument count: 3
args[0] = hello
args[1] = spring
args[2] = boot
```

Log startup khác của Spring Boot có thể xuất hiện trước hoặc xung quanh những dòng này. Chúng không thay đổi nội dung mảng.

`@Component` khiến Spring đăng ký lớp runner thành bean nếu lớp nằm trong phạm vi component scan. Việc chỉ viết `implements CommandLineRunner` nhưng không đưa object vào Spring container sẽ không khiến Boot tự gọi method.

## 4. Dòng chảy dữ liệu: từ terminal đến run

Câu lệnh:

```bash
java -jar app.jar import orders.csv
```

được Java launcher chuyển thành các ứng dụng arguments truyền vào:

```java
public static void main(String[] args) {
    SpringApplication.run(CliApplication.class, args);
}
```

Spring Boot nhận mảng này khi khởi động; sau khi khởi tạo context, Boot truyền chúng cho startup runners.

```text
Terminal / shell
     │
     ▼
java -jar app.jar import orders.csv
     │
     ▼
main(String[] args)
     │
     ▼
SpringApplication.run(CliApplication.class, args)
     │
     ▼
Spring ApplicationContext được refresh
     │
     ▼
CommandLineRunner.run(String... args)
     │
     ▼
args[0] = "import"
args[1] = "orders.csv"
```

Để forwarding đúng, bạn cần truyền `args` vào `SpringApplication.run`. Nếu bootstrap thủ công bằng một instance `SpringApplication`, cách tương tự là:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(CliApplication.class);
    application.run(args);
}
```

Lập trình viên định nghĩa **ý nghĩa** của từng phần tử; Spring Boot không tự coi chuỗi `import` là một subcommand.

## 5. Positional arguments và named options

Có hai dạng CLI arguments thường gặp.

### 5.1. Tham số vị trí

```bash
java -jar app.jar import data/orders.csv
```

Mảng:

```text
["import", "data/orders.csv"]
```

Bạn quy ước phần tử đầu là tên lệnh, phần tử thứ hai là file. Đây là cú pháp ngắn gọn cho CLI nhỏ.

### 5.2. Tham số có tên

```bash
java -jar app.jar --job=import --input=data/orders.csv --dry-run
```

`CommandLineRunner` nhận các chuỗi nguyên vẹn:

```text
["--job=import", "--input=data/orders.csv", "--dry-run"]
```

Nó **không tự tách** `--job=import` thành hai trường `job` và `import`; nếu muốn tách, bạn phải parse chuỗi hoặc sử dụng `ApplicationArguments`.

### 5.3. Đường dẫn có khoảng trắng

```bash
java -jar app.jar import "data/orders November.csv"
```

Khi shell xử lý quote đúng, runner nhận hai phần tử:

```text
args[0] = import
args[1] = data/orders November.csv
```

Quy tắc dấu nháy, escape và phân tách command line có thể khác nhau giữa Bash, PowerShell và Windows CMD. Kiểm tra với đúng môi trường chạy ứng dụng.

### 5.4. JVM options khác application arguments

```bash
java -Duser.timezone=UTC -jar app.jar --job=import orders.csv
```

`-Duser.timezone=UTC` được Java launcher xử lý như JVM system property; nó không đi vào `main(String[] args)`. Trong khi đó `--job=import` và `orders.csv` nằm sau tên JAR nên là application arguments.

## 6. Spring Boot có thể dùng named options làm property

Spring Boot thường đưa đối số dạng `--key=value` vào các property sources của `Environment` khi chức năng command-line property được bật.

Ví dụ:

```bash
java -jar app.jar --spring.profiles.active=dev --server.port=9090
```

Các giá trị này có thể được Spring Boot dùng để bật profile hoặc thiết lập port, đồng thời runner vẫn có thể nhìn thấy hai chuỗi nguyên vẹn trong `args`.

Phân biệt ba khái niệm:

| Nguồn | Dữ liệu nhận | Dùng để làm gì? |
|---|---|---|
| `CommandLineRunner.run(String... args)` | Mảng raw application arguments | Xử lý logic CLI tự viết |
| `Environment` | Property đã resolve từ nhiều nguồn | Cấu hình bean và Boot |
| `ApplicationArguments` | API có option names/values và non-option arguments | Parse CLI theo tên dễ hơn |

Một đối số có tiền tố `--spring....` có thể phục vụ cấu hình Boot, nhưng vẫn nằm trong mảng truyền cho runner. Vì vậy code xử lý theo index, ví dụ luôn coi `args[0]` là tên job, có thể sai nếu người vận hành truyền thêm property ở trước.

## 7. Kiểm tra số lượng tham số trước khi dùng

Đừng giả định mọi lần khởi động đều có tham số.

Sai:

```java
@Override
public void run(String... args) {
    String job = args[0]; // Có thể lỗi nếu args.length == 0
    System.out.println(job);
}
```

Cách xử lý tối thiểu:

```java
@Override
public void run(String... args) {
    if (args.length == 0) {
        System.out.println("Không có lệnh được yêu cầu.");
        return;
    }

    String job = args[0];

    if ("import".equals(job)) {
        System.out.println("Chạy import");
    } else {
        System.out.println("Không nhận diện lệnh: " + job);
    }
}
```

Nếu ứng dụng chỉ được dùng cho batch và **bắt buộc** nhận một lệnh, bạn có thể ném `IllegalArgumentException` với thông báo hướng dẫn thay vì âm thầm bỏ qua. Với ứng dụng web có một runner tùy chọn, việc không có tham số có thể là trạng thái bình thường.

Chính hợp đồng nghiệp vụ quyết định behavior khi mảng rỗng.

## 8. Ví dụ thực tế: runner nhập dữ liệu CSV

Giả sử cú pháp CLI được quy định:

```text
import <file.csv>
```

Một runner dùng service nghiệp vụ:

```java
package com.example.cli;

import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class CsvImportRunner implements CommandLineRunner {

    private final CsvImportService importService;

    public CsvImportRunner(CsvImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) throws Exception {
        if (args.length == 0) {
            return;
        }

        if (!"import".equals(args[0])) {
            return;
        }

        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Cú pháp: import <file.csv>"
            );
        }

        Path file = Path.of(args[1]);

        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException(
                    "Không tìm thấy file: " + file
            );
        }

        importService.importFile(file);
    }
}
```

Ví dụ giả định `CsvImportService` đã được Spring đăng ký làm bean và có method `importFile(Path)`.

Dòng lệnh:

```bash
java -jar app.jar import data/orders.csv
```

Trình tự thực hiện:

1. Runner nhận đúng hai phần tử.
2. Xác nhận lệnh là `import`.
3. Chuyển đường dẫn từ chuỗi sang `Path`.
4. Xác nhận input là file thông thường.
5. Giao việc xử lý dữ liệu cho service.

Cách tổ chức này giúp runner tập trung vào **điều phối startup và parse CLI**, còn đọc CSV, validate bản ghi và ghi database nằm trong service được test riêng.

**Giới hạn của ví dụ:** nếu có thêm option trước `import`, parser hiện tại không hiểu. Đây là lý do phải công bố rõ cú pháp hoặc dùng parser có cấu trúc cho CLI phức tạp.

## 9. Tự parse các option đơn giản

Với cú pháp nhỏ như:

```bash
java -jar app.jar --job=export --output=data/report.csv --dry-run
```

bạn có thể duyệt mảng:

```java
@Override
public void run(String... args) throws Exception {
    boolean exportRequested = false;
    boolean dryRun = false;
    String output = null;

    for (String arg : args) {
        if ("--job=export".equals(arg)) {
            exportRequested = true;
        } else if ("--dry-run".equals(arg)) {
            dryRun = true;
        } else if (arg.startsWith("--output=")) {
            output = arg.substring("--output=".length());
        }
    }

    if (!exportRequested) {
        return;
    }

    if (output == null || output.isBlank()) {
        throw new IllegalArgumentException(
                "Thiếu --output=<path>"
        );
    }

    exportService.exportTo(Path.of(output), dryRun);
}
```

Ví dụ giả định `exportService` được inject từ Spring và có method `exportTo(Path, boolean)`.

Parser này có chủ ý chỉ để minh họa `String... args`. Nó chưa xử lý option trùng, dữ liệu xung đột, option không biết hoặc thông báo help phong phú. Nếu số option lớn, nên dùng `ApplicationRunner` hoặc thư viện CLI phù hợp.

Một chú ý nữa: method `String.startsWith(...)` không tự hiểu dấu quote hoặc các quy tắc shell. Ở thời điểm runner nhận chuỗi, shell đã tạo argument vector cho JVM.

## 10. CommandLineRunner và ApplicationRunner

Spring Boot còn có `ApplicationRunner`, cũng được gọi trong giai đoạn startup nhưng nhận đối tượng `ApplicationArguments`:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

So sánh:

| Tiêu chí | CommandLineRunner | ApplicationRunner |
|---|---|---|
| Tham số `run` | `String... args` | `ApplicationArguments` |
| Dạng dữ liệu | Raw strings | Parsed options và non-option arguments |
| Kiểm tra `--dry-run` | Tự tìm trong mảng | `containsOption("dry-run")` |
| Đọc `--input=file.csv` | Tự tách chuỗi | `getOptionValues("input")` |
| Lấy tham số vị trí | Dùng index và parser riêng | `getNonOptionArgs()` |
| Lấy mảng gốc | Đã có trực tiếp | `getSourceArgs()` |
| Thứ tự startup | Có thể áp dụng `@Order` | Có thể áp dụng `@Order` |

Cả hai cùng là startup runners và được Boot gọi khi tương ứng là bean của context. Khác biệt quan trọng nhất là **API đọc tham số**, không phải thứ tự lifecycle.

## 11. ApplicationArguments khi CLI nhiều named options

Ví dụ thay thế cho parser option thủ công:

```java
import java.nio.file.Path;
import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StructuredImportRunner implements ApplicationRunner {

    private final CsvImportService service;

    public StructuredImportRunner(CsvImportService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> jobs = args.getOptionValues("job");
        if (jobs == null || !jobs.contains("import")) {
            return;
        }

        List<String> files = args.getOptionValues("input");
        if (files == null || files.size() != 1 ||
                files.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Cần đúng một --input=<file.csv>"
            );
        }

        boolean dryRun = args.containsOption("dry-run");

        service.importFile(
                Path.of(files.get(0)),
                dryRun
        );
    }
}
```

Ví dụ giả định service có overload `importFile(Path, boolean)`.

Với lệnh:

```bash
java -jar app.jar --job=import --input=data/orders.csv --dry-run
```

`ApplicationArguments` cung cấp:

- `getOptionValues("job")`: danh sách chứa `import`.
- `getOptionValues("input")`: danh sách chứa `data/orders.csv`.
- `containsOption("dry-run")`: `true`.
- `getNonOptionArgs()`: danh sách các phần tử không phải option.
- `getSourceArgs()`: mảng chuỗi gốc.

`getOptionValues(...)` trả `null` nếu option không xuất hiện. Với flag có mặt mà không có giá trị, nó có thể trả về danh sách rỗng; chỉ kiểm tra sự hiện diện thì `containsOption` thường rõ ràng hơn.

**Không đăng ký đồng thời hai runner cùng xử lý một lệnh import** khi bạn chỉ cần một tác vụ. Các ví dụ sử dụng hai interface để so sánh, không có nghĩa Boot sẽ tự chọn một trong hai nếu cả hai đều là bean.

## 12. Khai báo runner bằng @Bean và lambda

Vì `CommandLineRunner` là functional interface, có thể tạo runner trực tiếp bằng lambda từ method `@Bean`:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupConfiguration {

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> {
            System.out.println(
                    "Số tham số khi khởi động: " + args.length
            );
        };
    }
}
```

Spring Boot sẽ gọi lambda này khi startup, miễn configuration được nạp và bean được đăng ký.

Nếu cần service:

```java
@Configuration(proxyBeanMethods = false)
public class JobConfiguration {

    @Bean
    CommandLineRunner jobRunner(JobService jobService) {
        return args -> jobService.execute(args);
    }
}
```

Ở đây `JobService` cần có method `execute(String[])` hoặc overload tương thích với mảng chuỗi.

Phân biệt:

- `@Component` + class triển khai interface: phù hợp khi parser phức tạp, cần constructor injection và test riêng.
- `@Bean` + lambda: phù hợp với startup task ngắn, có thể đọc trực tiếp.
- Logic nghiệp vụ vẫn nên ở service chuyên trách, tránh để factory method hoặc runner chứa toàn bộ xử lý domain.

## 13. Thời điểm runner được gọi trong lifecycle

Các mốc chính của một lần startup thành công:

```text
main(String[] args)
       │
       ▼
SpringApplication.run(...)
       │
       ▼
Chuẩn bị Environment và ApplicationContext
       │
       ▼
Refresh context, khởi tạo các bean cần thiết
       │
       ▼
ApplicationStartedEvent
       │
       ▼
ApplicationRunner / CommandLineRunner
       │
       ▼
ApplicationReadyEvent
       │
       ▼
Ứng dụng được coi là ready
```

`ApplicationStartedEvent` được phát sau khi context đã refresh nhưng trước khi các runner được gọi. `ApplicationReadyEvent` được phát sau khi runners hoàn tất thành công.

Hệ quả:

- Runner có thể sử dụng repository/service được Spring inject.
- Runner chạy lâu sẽ kéo dài thời gian trước khi ứng dụng được đánh dấu ready.
- Runner ném exception chưa xử lý có thể khiến startup không hoàn tất.
- Runner không chạy lại mỗi khi HTTP request đến.

Với web application, embedded server có thể đã bind port trong quá trình context refresh. Tuy nhiên, “port lắng nghe” và “ứng dụng đạt readiness” là hai trạng thái khác nhau; khi triển khai cần dựa vào readiness/liveness cơ chế phù hợp.

### 13.1. Khác với @PostConstruct

`@PostConstruct` là callback của một bean khi bean đó đang được khởi tạo. `CommandLineRunner` chạy sau khi application context đã refresh, nên hợp lý hơn cho một tác vụ cần nhiều bean đã sẵn sàng.

Nếu cần validate cấu hình của một object, có thể dùng `@ConfigurationProperties` validation. Nếu cần bootstrap một công việc dựa trên service, runner có thể phù hợp. Không nên dồn mọi initialization logic vào runner theo thói quen.

## 14. Nhiều runner và @Order

Ứng dụng có thể có nhiều `CommandLineRunner` và `ApplicationRunner`. Spring Boot sắp xếp các startup runner theo order metadata.

```java
@Component
@Order(10)
public class PrepareRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Prepare");
    }
}
```

```java
@Component
@Order(20)
public class ExecuteRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Execute");
    }
}
```

Trong cơ chế ordering, số nhỏ hơn được ưu tiên trước:

```text
PrepareRunner (10)
       │
       ▼
ExecuteRunner (20)
```

Có thể implement `Ordered` thay cho `@Order`:

```java
@Component
public class CleanupRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public void run(String... args) {
        System.out.println("Cleanup");
    }
}
```

Cần phân biệt:

- Order điều khiển **thứ tự gọi runner**, không điều khiển thứ tự tạo mọi bean trong container.
- `ApplicationRunner` cũng tham gia cơ chế ordering.
- Nếu runner có cùng order, không nên dựa vào thứ tự xuất hiện trong file Java.
- Nếu bước B phụ thuộc chặt chẽ vào kết quả bước A, một orchestration service gọi A rồi B rõ ràng thường dễ bảo trì hơn hai runner tách rời chỉ liên hệ bằng order.

## 15. Xử lý exception và startup thất bại

`run(String... args)` cho phép ném `Exception`:

```java
@Override
public void run(String... args) throws Exception {
    if (args.length == 0) {
        throw new IllegalArgumentException(
                "Thiếu tham số tác vụ"
        );
    }

    jobService.execute(args);
}
```

Nếu exception thoát khỏi runner, Spring Boot thường coi startup thất bại. `ApplicationReadyEvent` không được phát như trong lần khởi động thành công; ứng dụng có thể phát `ApplicationFailedEvent` và đóng context.

Đôi khi fail-fast là đúng: một batch job bắt buộc phải báo thất bại khi file không tồn tại hoặc tham số sai. Với web server, một công việc phụ không nên vô tình chặn ứng dụng phục vụ HTTP nếu nghiệp vụ không yêu cầu điều đó.

Ví dụ xử lý lỗi có log:

```java
@Override
public void run(String... args) throws Exception {
    try {
        jobService.execute(args);
    } catch (IOException ex) {
        log.error("Không thể xử lý input", ex);
        throw ex;
    }
}
```

Ví dụ giả định class có logger `log` và service có thể ném `IOException`. Ném lại exception giữ nguyên ý nghĩa startup failure; cần tránh log trùng cùng lỗi ở nhiều lớp.

Nếu lỗi có thể phục hồi, thiết kế retry/compensation tại service hoặc job infrastructure thích hợp. Không nên bắt mọi exception rồi im lặng để context báo ready sai thực tế.

## 16. Runner có chạy trong web application không?

Có. `CommandLineRunner` hoạt động trong ứng dụng `WebApplicationType.NONE`, `SERVLET` hoặc `REACTIVE` khi bean được đăng ký.

Ví dụ:

```java
@Component
public class StartupNoticeRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Application context đã khởi động");
    }
}
```

Runner trên vẫn được gọi nếu chương trình là web server. Nó chỉ chạy ở startup, không chạy khi người dùng gửi HTTP request.

Đối với batch/CLI, có thể tắt web server bằng:

```properties
spring.main.web-application-type=none
```

`NONE` không tắt dependency injection hoặc runner. Nó chỉ yêu cầu Spring Boot tạo non-web application context.

Nếu cùng codebase có web và batch, cần kiểm soát runner nào được đăng ký để tránh một tác vụ import chạy ngoài ý muốn mỗi khi deploy lại web server.

## 17. Chỉ bật runner khi cần: Profile và Condition

Có thể dùng `@Profile` để giới hạn runner:

```java
@Component
@Profile("batch-import")
public class BatchImportRunner implements CommandLineRunner {

    private final CsvImportService service;

    public BatchImportRunner(CsvImportService service) {
        this.service = service;
    }

    @Override
    public void run(String... args) throws Exception {
        service.runImport(args);
    }
}
```

Chạy khi profile phù hợp được bật:

```bash
java -jar app.jar --spring.profiles.active=batch-import --job=import --input=data/orders.csv
```

Khi đó `args` có cả option `--spring.profiles.active=batch-import`, nên service/parser cần hiểu các chuỗi này hoặc sử dụng `ApplicationRunner` cho named options.

Có thể dùng conditional bean registration:

```java
@Component
@ConditionalOnProperty(
    prefix = "jobs.csv-import",
    name = "enabled",
    havingValue = "true"
)
public class ConditionalImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        // Chỉ gọi khi jobs.csv-import.enabled=true.
    }
}
```

Khi condition không thỏa, runner bean không được đăng ký nên không được Boot gọi.

Kết hợp profile/condition với validation tham số giúp chương trình rõ ràng: *khi nào có job*, *người dùng yêu cầu job nào* và *tham số bắt buộc của job là gì* là các quyết định khác nhau.

## 18. Batch runner, process exit và exit code

Runner không có nghĩa JVM tự đóng ngay khi `run` kết thúc. Với ứng dụng `NONE`, JVM có thể thoát khi không còn non-daemon thread hoặc thành phần nào giữ tiến trình hoạt động. Một listener, scheduler hoặc connection pool vẫn có thể duy trì process tùy cách cấu hình.

Nếu muốn một batch application chạy rồi trả kết quả cho scheduler, có thể quản lý context và exit code ở entry point:

```java
@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BatchApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

`SpringApplication.exit(context)` đóng context và lấy exit code theo các `ExitCodeGenerator` phù hợp. `System.exit(exitCode)` kết thúc process với mã đó.

Ví dụ này dành cho batch entry point có chủ đích. Không nên đặt `System.exit` trong runner của một web service vì nó có thể dừng cả HTTP server ngay sau startup.

Nếu cần quy ước mã như 0 = thành công, 2 = tham số sai, 3 = không có input, hãy định nghĩa chính sách exit code riêng và kiểm thử. Đó không phải bộ mã do `CommandLineRunner` tự cung cấp.

## 19. Runner và transaction

Runner có thể gọi repository thông qua service:

```java
@Component
public class SeedRunner implements CommandLineRunner {

    private final SeedService service;

    public SeedRunner(SeedService service) {
        this.service = service;
    }

    @Override
    public void run(String... args) {
        service.seedIfNeeded();
    }
}
```

Service nghiệp vụ:

```java
@Service
public class SeedService {

    private final ProductRepository repository;

    public SeedService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void seedIfNeeded() {
        if (repository.count() == 0) {
            repository.save(new Product("DEMO"));
        }
    }
}
```

Ví dụ giả định entity/repository và transaction infrastructure đã được cấu hình. `CommandLineRunner` tự nó không tạo transaction cho toàn bộ `run(...)`; việc đặt transaction boundary thuộc thiết kế service.

Với nhiều application instances, `repository.count() == 0` rồi insert có thể race giữa nhiều process. Muốn bảo đảm dữ liệu nhất quán, cần constraint, migration hoặc phối hợp concurrency phù hợp. Runner không cung cấp distributed lock hay exactly-once guarantee.

## 20. Lỗi thường gặp khi sử dụng String... args

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `ArrayIndexOutOfBoundsException` | Đọc `args[0]` khi mảng rỗng. | Kiểm tra `args.length`. |
| Không nhận tham số | `main` không truyền `args` tới `SpringApplication.run` hoặc lệnh CLI sai. | Kiểm tra bootstrap và command line. |
| `--job=import` không được tách | `CommandLineRunner` nhận raw strings. | Parse chuỗi hoặc dùng `ApplicationRunner`. |
| Path có khoảng trắng thành nhiều phần tử | Quote/escape không đúng cho shell. | Quote path theo shell thực tế. |
| Runner không được gọi | Class không là bean hoặc profile/condition không thỏa. | Kiểm tra component scan, `@Bean`, profile và condition. |
| Job chạy lại khi restart web server | Runner chạy mỗi lần context startup. | Điều kiện hóa job và thiết kế idempotence. |
| Hai lần import | Có nhiều runner cùng xử lý lệnh hoặc nhiều instances khởi động. | Chỉ định owner và kiểm soát concurrency. |
| Startup không ready | Runner chặn lâu hoặc ném exception. | Chọn lifecycle thích hợp, xử lý lỗi có chủ đích. |
| `@Order` không ảnh hưởng bean creation | Ordering này dành cho runner invocations. | Mô tả dependency trực tiếp bằng DI/service. |
| `-Dkey=value` không có trong args | Đó là JVM option. | Dùng System properties hoặc application option `--key=value`. |

Ngoài ra, không in nguyên toàn bộ command line ở production nếu nó có thể chứa token, mật khẩu hoặc đường dẫn nhạy cảm. Nên log tên job, trạng thái và dữ liệu vận hành an toàn; ẩn hoặc không log secret.

## 21. Kiểm thử runner

### 21.1. Unit test bằng lời gọi trực tiếp

Vì runner là một Java object thường, có thể tạo instance với mock/fake service rồi gọi `run(...)`:

```java
@Test
void ignoresUnknownCommand() throws Exception {
    CsvImportService service = mock(CsvImportService.class);
    CsvImportRunner runner = new CsvImportRunner(service);

    runner.run("help");

    verifyNoInteractions(service);
}
```

Ví dụ dùng Mockito và JUnit; các import/test dependencies cần có tương ứng trong project. Không cần khởi động web server chỉ để kiểm tra nhánh parse một lệnh.

Với testcase import hợp lệ, dùng `@TempDir` tạo file tạm, gọi runner với `"import"` và path, rồi xác nhận service được gọi đúng. Nên test cả không có args, thiếu path và path không tồn tại.

### 21.2. Integration test với @SpringBootTest

`@SpringBootTest` hỗ trợ truyền application arguments vào Spring application test:

```java
@SpringBootTest(args = {"--mode=test", "--dry-run"})
class StartupArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Test
    void hasDryRunFlag() {
        assertTrue(arguments.containsOption("dry-run"));
    }
}
```

Ví dụ cần Spring Boot Test/JUnit cùng các imports tương ứng.

**Chú ý:** runner beans vẫn có thể được chạy khi `@SpringBootTest` tạo application context. Tránh để integration test vô tình gọi import production hoặc gửi request đến dịch vụ thật. Hãy giới hạn startup job bằng profile/condition hoặc thay dependency bằng mock/fake phù hợp.

## 22. Bài tập thực hành

### Bài tập A — Quan sát mảng tham số

Tạo `ArgumentsPrinter` như phần 3. Chạy:

```bash
java -jar app.jar one two three
```

và:

```bash
java -jar app.jar one "two three"
```

So sánh `args.length` và nội dung từng phần tử.

### Bài tập B — Lệnh import file

Thiết kế runner nhận `import <file.csv>`. Khi thiếu file thì báo cú pháp; khi file không tồn tại thì báo lỗi rõ. Tách bước đọc CSV sang service.

### Bài tập C — Named options

Đọc `--job=export --output=report.csv --dry-run` bằng `CommandLineRunner`. Sau đó viết lại bằng `ApplicationRunner` và so sánh độ phức tạp của parser.

### Bài tập D — Nhiều runner

Tạo hai `CommandLineRunner` với `@Order(10)` và `@Order(20)`. Quan sát thứ tự. Thêm một `ApplicationRunner` với order trung gian rồi kiểm tra thứ tự chung.

### Bài tập E — Profile và readiness

Dùng `@Profile("batch")` để chỉ đăng ký runner import trong profile batch. Quan sát behavior khi không bật profile, khi bật profile với tham số hợp lệ và khi thiếu input.

### Bài tập F — Lỗi startup

Cho runner ném `IllegalArgumentException` khi input sai. Quan sát startup outcome. Sau đó thiết kế thông báo lỗi và exit code cho một batch job, tránh nuốt exception.

### Bài tập G — Multi-instance

Giả lập hai application instances cùng khởi động với runner seed dữ liệu. Giải thích vì sao runner có thể chạy hai lần và cách giữ dữ liệu nhất quán bằng transaction, unique constraint, migration hoặc một cơ chế phối hợp phù hợp.

## 23. Ghi nhớ

1. `CommandLineRunner` là startup hook được Spring Boot gọi khi bean triển khai interface này tồn tại trong context.
2. `run(String... args)` nhận mảng chuỗi application arguments thô theo thứ tự chuyển vào `SpringApplication.run`.
3. `String...` là varargs; trong method có thể dùng như `String[]`.
4. Luôn kiểm tra `args.length` trước khi đọc theo chỉ số.
5. Option dạng `--key=value` vẫn là một chuỗi trong `CommandLineRunner`; `ApplicationRunner` phù hợp hơn khi cần phân tích named options.
6. Runner phải được đăng ký qua `@Component`, `@Bean` hoặc cơ chế Spring bean registration phù hợp.
7. Có thể đăng ký nhiều runner và sắp xếp bằng `@Order` hoặc `Ordered`.
8. Runner chạy sau khi context refresh và trước `ApplicationReadyEvent`; exception chưa xử lý có thể khiến startup thất bại.
9. Runner cũng chạy trong ứng dụng web nếu bean được đăng ký; nó không phải HTTP request handler.
10. Runner chạy mỗi lần ứng dụng startup, không bảo đảm exactly-once toàn cluster.
11. Tách parse CLI, validation, business logic và transaction ra những trách nhiệm rõ ràng.
12. Với batch process, quyết định riêng web application type, cơ chế shutdown và exit code.

Khi thiết kế một `CommandLineRunner`, hãy xác định rõ: **người dùng truyền những chuỗi nào, runner kiểm tra những điều kiện gì và service nào xử lý nghiệp vụ?** Sau đó chọn cách bật runner, thứ tự thực thi và chính sách lỗi để startup behavior của ứng dụng dễ dự đoán và dễ vận hành.
