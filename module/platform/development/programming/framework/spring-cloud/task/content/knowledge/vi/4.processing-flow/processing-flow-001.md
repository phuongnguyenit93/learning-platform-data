# CommandLineRunner và ApplicationRunner trong Spring Cloud Task

## 1. Vai trò trong luồng xử lý một tác vụ ngắn hạn

Một ứng dụng **Spring Cloud Task** thường được khởi chạy từ dòng lệnh, Kubernetes CronJob, bộ điều phối hoặc yêu cầu của hệ thống khác; nó xử lý một công việc hữu hạn rồi kết thúc. Để bắt đầu nghiệp vụ ngay sau khi Spring Boot dựng xong môi trường ứng dụng, hai điểm mở rộng rất phổ biến là **`CommandLineRunner`** và **`ApplicationRunner`**.

Cả hai đều thuộc **Spring Boot**, không phải API chỉ có ở Spring Cloud Task. Spring Cloud Task bổ sung khả năng quản lý vòng đời và lưu **`TaskExecution`** qua **`TaskRepository`**; runner là nơi thuận tiện để gọi **nghiệp vụ cụ thể** như nhập file, xuất báo cáo, đối soát giao dịch hoặc đồng bộ dữ liệu.

Ví dụ, lúc 02:00 hằng ngày, một CronJob chạy:

~~~bash
java -jar revenue-task.jar --date=2026-11-23 --dry-run
~~~

Khi tiến trình khởi động, Spring Boot tạo application context, cấu hình bean và gọi runner với các tham số đã nhận. Runner kiểm tra ngày, gọi service xuất dữ liệu và kết thúc. Spring Cloud Task ghi metadata về lần thực thi để phục vụ giám sát, tra cứu trạng thái và điều tra lỗi. Với `--dry-run`, ứng dụng có thể kiểm tra kế hoạch xử lý mà chưa ghi dữ liệu nghiệp vụ; hành vi cụ thể phải do service tự cài đặt.

**Điểm mấu chốt:** runner xác định **phần nghiệp vụ chạy lúc khởi động**, còn Spring Cloud Task xác định **cách theo dõi một lần chạy ứng dụng**. Không nên xem runner là cơ chế lập lịch hoặc hệ thống hàng đợi bền vững.

## 2. Runner được gọi ở đâu trong vòng đời Spring Boot?

Spring Boot gọi các bean kiểu `ApplicationRunner` và `CommandLineRunner` sau khi application context đã được refresh, các bean cần thiết đã được tạo, và trước khi thông báo ứng dụng sẵn sàng hoàn toàn (`ApplicationReadyEvent`). Trong luồng khởi động thông thường, các runner chạy đồng bộ; `SpringApplication.run(...)` chỉ trả về sau khi chúng đã hoàn thành hoặc luồng khởi động thất bại.

Luồng xử lý ở mức khái niệm:

~~~mermaid
flowchart TD
    A["CLI / CronJob / orchestrator khởi chạy JVM"] --> B["SpringApplication.run(args)"]
    B --> C["Tạo và refresh Spring ApplicationContext"]
    C --> D["Spring Boot gọi các runner theo thứ tự"]
    D --> E["Runner kiểm tra tham số và gọi service nghiệp vụ"]
    E --> F{"Nghiệp vụ hoàn tất?"}
    F -- "Thành công" --> G["SpringApplication.run trả về"]
    F -- "Exception không xử lý" --> H["Khởi động thất bại; xử lý lỗi"]
    G --> I["Đóng context và kết thúc tiến trình"]
    H --> I
    I --> J["Hệ điều phối nhận kết quả/mã thoát"]
~~~

Với Spring Cloud Task được bật và kết nối metadata khả dụng, framework theo dõi sự bắt đầu/kết thúc của task và ghi metadata qua `TaskRepository`. Sơ đồ trên mô tả **nghiệp vụ và vòng đời tổng thể**, không biểu thị chính xác thứ tự từng callback nội bộ của Spring Cloud Task ở mọi phiên bản. Việc repository ghi được thông tin lỗi phụ thuộc thời điểm lỗi và khả năng truy cập CSDL.

### Những sự kiện không nên nhầm lẫn

| Giai đoạn | Ý nghĩa đối với runner |
|---|---|
| Tạo bean và dependency injection | Runner là bean Spring; constructor, cấu hình và các bean phụ thuộc phải được dựng trước khi chạy nghiệp vụ |
| Context được refresh | Phần lớn hạ tầng đã sẵn sàng, bao gồm datasource/service nếu cấu hình thành công |
| `ApplicationStartedEvent` | Được phát trước khi gọi các runner trong trình tự khởi động Spring Boot thông thường |
| `CommandLineRunner.run(...)` / `ApplicationRunner.run(...)` | Chạy logic khởi động, xử lý tham số và gọi service |
| `ApplicationReadyEvent` | Thông báo sau khi runners đã hoàn tất thành công |
| Đóng context, kết thúc ứng dụng | Giải phóng tài nguyên, hoàn thành vòng đời ứng dụng ngắn hạn và cung cấp kết quả cho môi trường chạy |

Nếu một runner ném exception mà không được xử lý, việc khởi động Spring Boot thất bại và `ApplicationReadyEvent` không xảy ra theo nhánh thành công. Vì vậy đây là điểm thích hợp để **bộc lộ lỗi nghiệp vụ nghiêm trọng**, thay vì chỉ in log “thất bại” rồi vẫn cho ứng dụng trả mã thành công.

> **Lưu ý về vòng đời:** “Runner đã trả về” không mặc nhiên đồng nghĩa “JVM đã thoát”. Một web server, luồng không phải daemon, scheduler hoặc tài nguyên giữ tiến trình sống có thể khiến ứng dụng tiếp tục chạy. Ứng dụng Spring Cloud Task thường cần cấu hình không chạy web và có cơ chế đóng context rõ ràng.

## 3. CommandLineRunner: nhận danh sách đối số dạng String

`CommandLineRunner` là functional interface trong package `org.springframework.boot`:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Tham số `String... args` là các đối số được truyền tới ứng dụng. Cách này thuận tiện khi công việc sử dụng **tham số vị trí** hoặc cần tự kiểm soát cách phân tích chuỗi đầu vào, chẳng hạn đường dẫn file nguồn.

Ví dụ một runner nhận đúng một đối số là đường dẫn file:

~~~java
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
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Su dung: java -jar import-task.jar <duong-dan-file.csv>");
        }

        Path source = Path.of(args[0]);
        if (!Files.isRegularFile(source) || !Files.isReadable(source)) {
            throw new IllegalArgumentException(
                "File khong ton tai hoac khong the doc: " + source);
        }

        importService.importCsv(source);
    }
}
~~~

Trong ví dụ, `CsvImportService` là service nghiệp vụ do ứng dụng cung cấp, thực hiện việc đọc/kiểm tra/ghi dữ liệu. Đối số:

~~~bash
java -jar import-task.jar ./input/orders.csv
~~~

Khi dùng `CommandLineRunner` với cú pháp `--date=2026-11-23` hoặc `--force`, chúng vẫn là chuỗi đối số; bạn phải tự phân tích giá trị, xử lý thiếu tham số, trùng tham số và kiểu dữ liệu. Nếu ứng dụng có nhiều option được đặt tên, `ApplicationRunner` thường dễ đọc và bảo trì hơn.

### Trường hợp nên dùng CommandLineRunner

- Ứng dụng có giao diện CLI nhỏ và rất ít tham số, chủ yếu là tham số vị trí.
- Cần xử lý đúng danh sách token đầu vào như một công cụ dòng lệnh.
- Đã có bộ phân tích argument riêng và muốn chuyển toàn bộ `String[]` cho bộ phân tích đó.

Không nên để runner trực tiếp ôm hết logic đọc file, kiểm tra, mapping, transaction và ghi dữ liệu. Runner chỉ cần xác thực đầu vào, tạo lệnh nghiệp vụ và **ủy quyền cho service**.

## 4. ApplicationRunner: nhận ApplicationArguments đã được phân tích

`ApplicationRunner` cũng là functional interface trong Spring Boot nhưng nhận `ApplicationArguments`:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

`ApplicationArguments` cung cấp cách đọc option dạng `--name=value`, option dạng cờ và non-option args:

| API | Ý nghĩa | Ví dụ |
|---|---|---|
| `getSourceArgs()` | Danh sách đối số gốc | `["--date=2026-11-23", "--dry-run", "manual"]` |
| `getOptionNames()` | Tên các option được chỉ định | `date`, `dry-run` |
| `containsOption("dry-run")` | Có truyền option hay không | `true` nếu có `--dry-run` |
| `getOptionValues("date")` | Các giá trị của một option; có thể `null` khi không có option | `["2026-11-23"]` |
| `getNonOptionArgs()` | Các đối số không phải option | `["manual"]` |

Ví dụ đầu vào:

~~~bash
java -jar revenue-task.jar --date=2026-11-23 --dry-run manual
~~~

Không nên giả định mọi option đều có đúng một giá trị. `getOptionValues("date")` có thể trả về `null` nếu thiếu, danh sách rỗng nếu option xuất hiện nhưng không có giá trị, hoặc nhiều giá trị nếu được truyền lặp. Vì thế, **validate số lượng và nội dung giá trị trước khi ép kiểu**.

Ví dụ đọc tham số một cách an toàn:

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.ApplicationArguments;

public final class RevenueTaskOptions {
    private final LocalDate date;
    private final boolean dryRun;

    private RevenueTaskOptions(LocalDate date, boolean dryRun) {
        this.date = date;
        this.dryRun = dryRun;
    }

    public static RevenueTaskOptions parse(ApplicationArguments args) {
        List<String> dates = args.getOptionValues("date");

        if (dates == null || dates.size() != 1
                || dates.get(0) == null || dates.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Thieu tham so hop le: --date=yyyy-MM-dd");
        }

        LocalDate parsedDate = LocalDate.parse(dates.get(0));
        return new RevenueTaskOptions(
            parsedDate,
            args.containsOption("dry-run")
        );
    }

    public LocalDate date() {
        return date;
    }

    public boolean dryRun() {
        return dryRun;
    }
}
~~~

`LocalDate.parse(...)` sẽ ném `DateTimeParseException` nếu giá trị ngày không đúng định dạng ISO-8601. Ở đây cố ý cho exception lan lên runner để toàn bộ lần chạy thất bại một cách quan sát được. Trong ứng dụng thực tế, có thể bổ sung thông báo lỗi rõ hơn, giới hạn khoảng ngày hợp lệ và kiểm tra option không được hỗ trợ.

Một phân biệt quan trọng: `ApplicationArguments` giúp **đọc và phân loại** tham số, không tự xác thực quy tắc nghiệp vụ như “ngày không được ở tương lai” hoặc “không được chạy ghi thật ở môi trường thử nghiệm”.

## 5. Ví dụ Spring Cloud Task hoàn chỉnh với ApplicationRunner

Ví dụ dưới đây minh họa ứng dụng xuất báo cáo doanh thu theo ngày, có chế độ chạy thử. Để tập trung vào vòng đời runner, service nghiệp vụ chỉ in thông tin; khi áp dụng thực tế, hãy thay bằng truy vấn, tạo báo cáo và lưu kết quả thực sự.

~~~java
package example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class RevenueTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RevenueTaskApplication.class, args);

        // Đóng context; trả mã thoát cho OS/orchestrator.
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner exportRevenue(RevenueReportService service) {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");
            if (dates == null || dates.size() != 1
                    || dates.get(0) == null || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                    "Can truyen --date=yyyy-MM-dd");
            }

            LocalDate targetDate = LocalDate.parse(dates.get(0));
            boolean dryRun = arguments.containsOption("dry-run");

            // Chạy đồng bộ; chỉ trả về sau khi service hoàn tất.
            service.export(targetDate, dryRun);
        };
    }
}

@Service
class RevenueReportService {

    public void export(LocalDate date, boolean dryRun) {
        if (dryRun) {
            System.out.printf(
                "DRY RUN: se xuat bao cao cho %s%n", date);
            return;
        }

        // Ví dụ minh họa: thay bằng truy vấn và lưu báo cáo thật.
        System.out.printf("Da xu ly bao cao cho %s%n", date);
    }
}
~~~

Cấu hình ứng dụng ngắn hạn:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: revenue-export-task
  cloud:
    task:
      name: revenue-export-task
~~~

Chạy tác vụ:

~~~bash
# Chạy thử, không ghi kết quả nghiệp vụ
java -jar revenue-task.jar --date=2026-11-23 --dry-run

# Thực hiện xuất báo cáo
java -jar revenue-task.jar --date=2026-11-23
~~~

Ví dụ giả định dự án có các dependency Spring Boot và Spring Cloud Task **tương thích phiên bản**, cùng một `DataSource` và schema task metadata được cấu hình đúng. Trong môi trường thật, cần dùng CSDL bền vững cho `TaskRepository`, cấu hình migration/schema và tài khoản truy cập thích hợp; mã Java trên chỉ minh họa phần runner và service.

### Tại sao cần SpringApplication.exit(...)?

`SpringApplication.exit(context)` đóng context theo quy trình Spring và lấy mã thoát thích hợp từ các `ExitCodeGenerator` được cấu hình. `System.exit(...)` chuyển mã thoát đó cho tiến trình Java, giúp CronJob, script shell hoặc bộ điều phối quan sát kết quả.

Trong một tác vụ ngắn hạn, chuỗi mục tiêu thường là:

~~~text
Khởi chạy → nhận tham số → chạy nghiệp vụ → chờ hoàn tất
→ ghi nhận kết quả → đóng context → kết thúc tiến trình
~~~

Tuy nhiên, đoạn `SpringApplication.exit(context)` chỉ chạy khi `SpringApplication.run(...)` **trả về bình thường**. Nếu runner ném exception trong giai đoạn khởi động, Spring Boot chuyển sang luồng xử lý lỗi khởi động; không nên dựa vào dòng sau `run(...)` để xử lý nhánh thất bại. Hãy để lỗi được phản ánh bằng mã thoát không thành công và cấu hình exception/exit-code mapping khi nghiệp vụ cần phân loại lỗi.

Ngoài ra, việc đóng context không thay thế nghĩa vụ **chờ các tác vụ con hoàn tất**. Nếu service chỉ gửi một yêu cầu `@Async` hoặc `TaskExecutor.execute(...)` rồi trả về, tiến trình có thể kết thúc trước khi phần việc thực sự hoàn thành.

## 6. So sánh CommandLineRunner và ApplicationRunner

| Khía cạnh | CommandLineRunner | ApplicationRunner |
|---|---|---|
| Package | `org.springframework.boot` | `org.springframework.boot` |
| Phương thức chính | `run(String... args)` | `run(ApplicationArguments args)` |
| Dữ liệu đầu vào | Các chuỗi tham số thô | Tham số đã được Spring Boot phân nhóm thành option và non-option |
| Hợp với bài toán | CLI đơn giản, tham số vị trí, custom parser | Nhiều option có tên, cờ `--dry-run`, tham số chạy theo yêu cầu |
| Thời điểm gọi | Sau khi context refresh, trong quá trình startup | Cùng giai đoạn với CommandLineRunner |
| Chạy đồng bộ mặc định | Có | Có |
| Tự xử lý retry, scheduling, persistence? | Không | Không |
| Được Spring Cloud Task theo dõi khi dùng làm điểm vào? | TaskExecution theo dõi vòng đời ứng dụng, không tự tạo riêng cho từng runner | Tương tự |

**Không có “runner nào tích hợp Spring Cloud Task tốt hơn” theo bản chất framework.** Sự khác biệt chủ yếu nằm ở cách đọc tham số. Với một task nghiệp vụ nhận `--date`, `--source`, `--dry-run` hoặc `--tenant`, `ApplicationRunner` thường làm mã dễ hiểu hơn.

## 7. Nhiều runner: thứ tự, phụ thuộc và xử lý lỗi

Một ứng dụng có thể đăng ký **nhiều bean** `CommandLineRunner` và `ApplicationRunner` cùng lúc. Spring Boot gọi tất cả các runner có trong context và áp dụng cơ chế sắp xếp thứ tự như `Ordered` hoặc `@Order`.

Ví dụ:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PreflightRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Kiem tra tien dieu kien");
    }
}

@Component
@Order(20)
class ExportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Thuc hien export");
    }
}
~~~

Trong ví dụ, `PreflightRunner` được ưu tiên chạy trước `ExportRunner`. Cơ chế sắp xếp áp dụng **trên các runner**, không coi interface nào mặc định luôn chạy trước interface kia. Nếu không khai báo thứ tự, không nên viết logic dựa vào một thứ tự ngầm định.

Khi một runner ném exception và không có xử lý phù hợp, quá trình gọi runners dừng theo nhánh lỗi; các runner sau có thể không được gọi. Điều này giúp tránh thực hiện nghiệp vụ khi bước kiểm tra đầu vào thất bại, nhưng cũng tạo ra vấn đề nếu ta rải các bước của một giao dịch qua nhiều runner mà không quản lý tính nhất quán.

**Khuyến nghị thiết kế:** nếu “kiểm tra → đối soát → ghi kết quả” là **một tác vụ nghiệp vụ**, hãy sử dụng một runner chính làm điểm vào và gọi một service điều phối, có transaction và quy tắc phục hồi rõ ràng. Dùng nhiều runner khi thật sự có nhiều hoạt động khởi động độc lập và thứ tự của chúng được quản lý minh bạch.

### Tránh vô tình đăng ký hai lần

Một class vừa có `@Component` vừa được tạo lại qua `@Bean` có thể dẫn đến nhiều runner cùng tồn tại, khiến nghiệp vụ chạy hai lần. Tương tự, nếu đã đăng ký cả runner nhập file và runner xuất dữ liệu trong một ứng dụng, **cả hai có thể chạy ở mỗi lần khởi động** trừ khi có điều kiện bật/tắt rõ ràng. Có thể dùng `@Profile`, `@ConditionalOnProperty` hoặc tách ứng dụng theo tác vụ.

## 8. Xử lý exception và trạng thái tác vụ

Để Spring Cloud Task cung cấp trạng thái hữu ích, **ngoại lệ nghiệp vụ phải ảnh hưởng đến kết quả chạy**. Một số tình huống tiêu biểu:

| Tình huống | Hành vi nên thiết kế |
|---|---|
| Thiếu `--date` | Ném lỗi đầu vào, log thông điệp an toàn, kết thúc không thành công |
| Ngày có định dạng sai | Từ chối trước khi ghi dữ liệu |
| Không kết nối được CSDL nghiệp vụ | Cho lỗi lan lên runner hoặc ánh xạ sang lỗi có mã thoát phù hợp |
| Một trong nhiều phân vùng xử lý thất bại | Gom lỗi, không tuyên bố toàn bộ task thành công |
| Đã ghi một phần dữ liệu rồi crash | Thiết kế transaction/checkpoint và idempotency để chạy lại an toàn |
| Mất kết nối TaskRepository khi khởi tạo | Không giả định repository có bản ghi đầy đủ của lần chạy thất bại |
| Bị `SIGKILL` hoặc container chết đột ngột | Có thể để lại TaskExecution chưa được chốt; cần phát hiện timeout |

Mẫu xử lý đúng trong runner:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    var request = parseRequest(args);
    service.process(request); // Ném exception nếu nghiệp vụ thất bại.
}
~~~

Mẫu **dễ gây hiểu nhầm kết quả**:

~~~java
@Override
public void run(ApplicationArguments args) {
    try {
        service.process(parseRequest(args));
    } catch (Exception ex) {
        log.error("Xu ly that bai", ex);
        // Nếu chỉ log rồi trả về, Spring Boot có thể coi
        // runner đã kết thúc bình thường.
    }
}
~~~

Nếu cần log thêm ngữ cảnh, có thể **ghi log và ném lại exception**, thay vì nuốt lỗi. Nếu có yêu cầu trả mã lỗi khác nhau cho lỗi đầu vào, lỗi tạm thời hoặc lỗi nghiệp vụ, hãy áp dụng cơ chế exit code của Spring Boot, chẳng hạn `ExitCodeGenerator` hoặc `ExitCodeExceptionMapper` theo phiên bản đang dùng.

Metadata của Spring Cloud Task như tên task, thời gian bắt đầu/kết thúc, mã thoát và thông điệp lỗi giúp quan sát lần chạy; **TaskRepository không tự lưu báo cáo, dữ liệu xuất hoặc trạng thái từng bản ghi**. Những kết quả này phải được lưu trong kho nghiệp vụ và có thể gắn `taskExecutionId` hoặc correlation ID để truy vết.

## 9. Runner với @Async, TaskExecutor và Spring Batch

### 9.1. Runner và công việc bất đồng bộ

Runner khởi động theo cơ chế đồng bộ; nhưng chính service được gọi có thể dùng `@Async`, `CompletableFuture` hoặc `TaskExecutor`. Khi đó runner phải quyết định **khi nào được coi là xong**.

Ví dụ service trả về futures:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner importAll(ImportService importService) {
    return args -> {
        List<CompletableFuture<Void>> tasks =
            importService.submitAllPartitions();

        // Đợi các phân vùng hoàn thành và làm lộ lỗi nếu có.
        CompletableFuture.allOf(
            tasks.toArray(new CompletableFuture<?>[0])
        ).join();
    };
}
~~~

`ImportService` và phần việc của từng phân vùng là thành phần nghiệp vụ cần triển khai trong dự án. `join()` sẽ ném exception nếu future thất bại; vì vậy runner không kết thúc thành công khi một phân vùng báo lỗi. Nếu dùng `TaskExecutor.execute(Runnable)` mà không có future hoặc cơ chế đồng bộ, chỉ việc gọi `execute` **không** chứng minh tác vụ đã xong.

Cũng cần tính đến các việc được đưa vào queue nhưng chưa chạy, việc đang giữ lock hoặc sử dụng connection, và graceful shutdown. Chạy song song không thay thế việc bảo đảm **idempotency**, giới hạn tải và đóng tài nguyên.

### 9.2. Runner và Spring Batch

Một ứng dụng Spring Cloud Task có thể khởi chạy một **Spring Batch Job**. Spring Batch sở hữu khái niệm `Job`, `Step`, checkpoint/restart và `JobRepository`, trong khi Spring Cloud Task sở hữu `TaskExecution` ở mức ứng dụng.

Nếu ứng dụng có Spring Batch và được bật cơ chế tự khởi chạy job của Spring Boot, job có thể được kích hoạt trong quá trình startup. Khi thêm runner riêng để cũng gọi `JobLauncher`, phải kiểm tra cấu hình để tránh **khởi chạy job trùng lặp**. Có thể lựa chọn một trong hai cách: dùng tự động khởi chạy job có kiểm soát hoặc tự gọi `JobLauncher` từ runner rồi tắt tự khởi chạy khi cần.

Ví dụ cấu hình thường gặp để chủ động điều khiển job bằng runner trong những phiên bản Spring Boot hỗ trợ thuộc tính này:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Khi áp dụng, cần kiểm tra cấu hình Spring Boot/Spring Batch cụ thể của dự án. Nếu job được chạy bất đồng bộ, runner cũng phải xử lý việc chờ kết quả và kiểm tra trạng thái của `JobExecution` trước khi cho task kết thúc.

## 10. Vận hành an toàn khi chạy theo lịch hoặc theo yêu cầu

Runner hoạt động mỗi lần tiến trình khởi động. Vì vậy việc **ai khởi chạy** và **chạy bao nhiêu lần** phải do tầng điều phối quy định.

~~~mermaid
sequenceDiagram
    participant C as CronJob / API / CLI
    participant B as Spring Boot
    participant R as Runner
    participant S as Business Service
    participant T as TaskRepository
    C->>B: Khởi chạy với --date=2026-11-23
    B->>T: Spring Cloud Task ghi nhận lần thực thi
    B->>R: run(arguments)
    R->>R: Kiểm tra tham số, tạo yêu cầu nghiệp vụ
    R->>S: export(date)
    alt Hoàn thành
        S-->>R: Kết quả thành công
        R-->>B: run() trở về bình thường
    else Có lỗi
        S-->>R: Ném exception
        R-->>B: Lỗi lan lên startup
    end
    B->>T: Cập nhật metadata khi vòng đời cho phép
    B-->>C: Tiến trình kết thúc, mã thoát
~~~

### Các thực hành quan trọng

1. **Dùng tham số rõ ràng và kiểm tra sớm:** xác định ngày cần xử lý, nguồn dữ liệu, tenant và chế độ chạy. Tránh sử dụng “hôm nay” theo múi giờ mặc định của container nếu yêu cầu nghiệp vụ phụ thuộc ngày địa phương.
2. **Không truyền bí mật qua CLI nếu có thể tránh:** tham số tiến trình có thể xuất hiện trong log, metadata hoặc hệ thống giám sát. Dùng secret manager, biến môi trường bảo mật hoặc cơ chế cung cấp bí mật phù hợp.
3. **Thiết kế chạy lại an toàn:** CronJob có thể khởi chạy lại; API có thể nhận yêu cầu trùng; việc thất bại sau khi ghi một phần dữ liệu có thể dẫn tới chạy bù. Dùng khóa nghiệp vụ, upsert, idempotency key, transaction hoặc checkpoint tùy bài toán.
4. **Theo dõi cả trạng thái kỹ thuật lẫn kết quả nghiệp vụ:** kết hợp exit code, lịch sử `TaskExecution`, log, metrics và dữ liệu đầu ra. “Không có exception” chưa bảo đảm kết quả nghiệp vụ đúng.
5. **Cấu hình giới hạn thời gian và tài nguyên:** thời gian chạy tối đa, số luồng, connection pool, chính sách retry và cảnh báo lần chạy quá hạn cần thuộc thiết kế vận hành.
6. **Giữ tiến trình hữu hạn:** dùng `spring.main.web-application-type: none` nếu không cần HTTP, tránh scheduler chạy vô hạn và chờ mọi công việc con trước khi đóng context.
7. **Quản lý repository bền vững:** schema phù hợp phiên bản, migration có kiểm soát, phân quyền CSDL và khả năng tra cứu những lần chạy bất thường.

Ví dụ với một yêu cầu chạy bù `--date=2026-11-21`, chính runner không biết ngày này đã được xuất hay chưa. Service nên tra khóa nghiệp vụ tương ứng, phát hiện trùng, quyết định ghi đè có kiểm soát hoặc bỏ qua; còn `TaskRepository` vẫn có thể ghi nhận **một lần chạy mới** cho yêu cầu đó.

## 11. Các lỗi thường gặp và cách phòng tránh

### Runner không chạy

Kiểm tra class có thực sự là bean Spring (`@Component` hoặc `@Bean`), có thuộc package được component scan, có profile/conditional đang vô hiệu hóa không, và application context có khởi động thành công hay không. Phương thức `run(...)` của một class Java thông thường không được Spring Boot tự gọi nếu class đó không được đăng ký bean.

### Runner chạy nhiều hơn dự kiến

Có thể có hai bean cùng loại cùng gọi một service, nhiều tiến trình/container được khởi chạy hoặc scheduler kích hoạt trùng. Phân biệt rõ **nhiều runner trong một process** và **nhiều TaskExecution do nhiều process**. Dùng điều kiện bật runner, idempotency và giám sát số lần thực thi.

### Tham số được đọc sai

Với `CommandLineRunner`, `--date=2026-11-23` là chuỗi cần tự phân tích. Với `ApplicationRunner`, hãy đọc `getOptionValues("date")` và kiểm tra có đúng một giá trị hay không; `containsOption("dry-run")` chỉ kiểm tra sự xuất hiện của cờ, không phải tự chuyển chuỗi `true/false`.

### Runner hoàn tất nhưng tiến trình vẫn sống

Ứng dụng có thể đã khởi động web server, scheduler hoặc luồng nền. Chọn cấu hình non-web khi phù hợp; đợi công việc cần thiết, đóng context và trả mã thoát. Không dùng `System.exit(0)` trước khi dữ liệu đã được lưu hoặc các future đã hoàn thành.

### Task báo thành công dù dữ liệu thiếu

Thường xảy ra do catch exception rồi không ném lại, khởi chạy công việc bất đồng bộ nhưng không chờ, hoặc coi “đã gửi yêu cầu” là “đã xử lý xong”. Cần xác định **tiêu chí hoàn tất nghiệp vụ** rồi để runner chỉ trở về bình thường khi tiêu chí đó đã đạt.

### Kết quả không tìm thấy trong TaskRepository

Kiểm tra `@EnableTask`, dependency, datasource, schema, profile và quyền CSDL. Đừng nhầm bảng metadata với bảng nghiệp vụ. Nếu JVM bị kill quá sớm hoặc kết nối repository lỗi, có thể không có bản ghi kết thúc đầy đủ.

## 12. Cách chọn và kết luận

| Bối cảnh | Lựa chọn phù hợp |
|---|---|
| Task chỉ nhận đường dẫn file từ CLI, ít tham số | `CommandLineRunner` |
| Task nhận `--date`, `--source`, `--dry-run`, cờ và tham số có tên | `ApplicationRunner` |
| Cần theo dõi start/end/exit code của một lần chạy ứng dụng | Spring Cloud Task + `TaskRepository`, dùng một runner làm điểm vào |
| Cần gọi nhiều service theo một chuỗi nghiệp vụ | Một runner điều phối một service cấp cao với luồng và transaction rõ ràng |
| Cần thực thi song song bên trong một lần chạy | Runner gọi service dùng `TaskExecutor`/`@Async` và **chờ kết quả** |
| Cần xử lý batch theo step, checkpoint và restart | Spring Batch; có thể chạy trong ứng dụng Spring Cloud Task |
| Cần lịch chạy | CronJob, scheduler hay hệ điều phối; runner không tự tạo lịch |

Hãy dùng **`CommandLineRunner`** khi cần xử lý tham số thô, **`ApplicationRunner`** khi cần bộ tham số có cấu trúc, và **Spring Cloud Task** để quản lý vòng đời, metadata và kết quả thực thi của ứng dụng ngắn hạn. Dù dùng runner nào, một lần chạy chỉ nên được đánh dấu hoàn thành khi **nghiệp vụ thực sự đã hoàn tất**, lỗi được phản ánh rõ ràng và tiến trình có thể đóng an toàn.
