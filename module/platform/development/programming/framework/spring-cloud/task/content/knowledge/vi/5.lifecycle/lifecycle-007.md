# Đóng ngữ cảnh bằng spring.cloud.task.closecontextEnabled

## 1. Vì sao một task hoàn tất nhưng ứng dụng vẫn chưa dừng?

**Spring Cloud Task** phục vụ các ứng dụng Spring Boot có **vòng đời hữu hạn**: khởi động, thực hiện một công việc, lưu metadata của lần thực thi qua **TaskRepository** rồi kết thúc. Ví dụ điển hình là nạp dữ liệu theo tệp, đối soát đơn hàng cuối ngày hoặc tạo báo cáo theo yêu cầu.

Tuy nhiên, **hoàn tất công việc** và **đóng ứng dụng** là hai sự kiện khác nhau:

- **Công việc hoàn tất:** toàn bộ `ApplicationRunner` và `CommandLineRunner` được Spring Boot gọi đã kết thúc; Spring Cloud Task có thể cập nhật kết quả thực thi vào `TaskRepository`.
- **ApplicationContext đóng:** Spring giải phóng các bean, phát sự kiện đóng context và gọi các callback dọn tài nguyên thích hợp.
- **Tiến trình JVM kết thúc:** hệ điều hành nhận được mã thoát; điều này còn phụ thuộc các luồng chưa dừng và cách ứng dụng quản lý tiến trình.

Trong một task đơn giản, JVM có thể tự kết thúc khi các runner xong và không còn luồng non-daemon giữ tiến trình sống. Nhưng trong một ứng dụng có executor, kết nối hoặc dịch vụ nền, bạn có thể thấy dữ liệu task đã được cập nhật mà tiến trình **vẫn tiếp tục chạy**.

Thuộc tính **`spring.cloud.task.closecontextEnabled`** cho phép Spring Cloud Task **chủ động đóng `ApplicationContext` khi kết thúc task**, giúp quản lý vòng đời đúng với mô hình ứng dụng ngắn hạn. Đây là trọng tâm của bài trong chương **Vòng đời**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của `spring.cloud.task.closecontextEnabled` và giá trị mặc định.
2. Cấu hình bật đóng context bằng YAML, properties hoặc tham số khởi chạy.
3. Phân biệt **TaskExecution kết thúc**, **context đóng** và **JVM thoát**.
4. Quan sát callback hủy bean, log và bản ghi trong `TaskRepository`.
5. Nhận biết rủi ro khi công việc chạy bất đồng bộ, tích hợp Spring Batch hoặc còn luồng nền.
6. Xử lý trường hợp task đã hoàn tất nhưng tiến trình không kết thúc.

## 2. Thuộc tính closecontextEnabled hoạt động thế nào?

Theo tài liệu Spring Cloud Task, khi bật `spring.cloud.task.closecontextEnabled=true`, framework sẽ đóng Spring `ApplicationContext` **sau khi các runner hoàn thành và metadata của task được cập nhật vào TaskRepository**. Giá trị mặc định của thuộc tính trong các phiên bản hiện hành là **`false`**.

| Cấu hình | Hành vi mong đợi | Khi nào dùng? |
| --- | --- | --- |
| Không thiết lập hoặc `false` | Spring Cloud Task không **chủ động** đóng context ngay sau khi task hoàn tất thông qua tính năng này. Context vẫn có thể đóng do shutdown hook hoặc mã ứng dụng. | Ứng dụng tự quản lý vòng đời; cần tìm nguyên nhân tiến trình còn sống trước khi bật. |
| `true` | Spring Cloud Task yêu cầu đóng context sau khi đã xử lý xong vòng đời thực thi; các cơ chế dọn tài nguyên được Spring quản lý có cơ hội chạy. | Ứng dụng chạy hữu hạn, muốn context kết thúc khi runner xong và không còn hoạt động nền cần duy trì. |

**Cần nhớ:** `closecontextEnabled=false` không đồng nghĩa JVM luôn chạy mãi. Nếu không còn luồng non-daemon, JVM có thể kết thúc và Spring Boot vẫn có thể đóng context qua shutdown hook. Ngược lại, `true` **không phải lệnh ép JVM thoát**, không thay thế `System.exit(...)` và không tự hủy an toàn mọi luồng do ứng dụng tự tạo.

### Cách viết tên thuộc tính

Trong tài liệu Spring Cloud Task có dạng camelCase:

`spring.cloud.task.closecontextEnabled`

Spring Boot hỗ trợ binding thuộc tính theo quy tắc tên linh hoạt (*relaxed binding*). Trong file YAML, nên dùng dạng kebab-case chuẩn để dễ đọc:

~~~yaml
spring:
  cloud:
    task:
      closecontext-enabled: true
~~~

Hai cách biểu diễn ở trên đều hướng đến cùng lựa chọn cấu hình khi được Spring Boot binding đúng cách. Có thể bật bằng tham số dòng lệnh:

~~~bash
java -jar demo-task.jar --spring.cloud.task.closecontextEnabled=true
~~~

Hoặc trong `application.properties`:

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

Khi triển khai, hãy xác nhận phiên bản Spring Cloud Task tương thích với Spring Boot và file cấu hình thực sự được profile đang chạy nạp vào. Không suy luận rằng một file YAML đã được áp dụng chỉ vì nó tồn tại trong thư mục dự án.

## 3. Thứ tự thực thi trong vòng đời task

Luồng thông thường của một lần chạy thành công có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant P as Tiến trình Spring Boot
    participant C as ApplicationContext
    participant R as ApplicationRunner/CommandLineRunner
    participant T as Spring Cloud Task
    participant DB as TaskRepository/Database
    P->>C: Tạo và khởi tạo context
    T->>DB: Ghi nhận TaskExecution bắt đầu
    C->>R: Gọi các runner
    R->>R: Thực hiện nghiệp vụ hữu hạn
    R-->>C: Runner hoàn tất
    T->>DB: Cập nhật TaskExecution kết thúc
    alt closecontextEnabled = true
        T->>C: Yêu cầu đóng ApplicationContext
        C->>C: Dừng bean, đóng tài nguyên quản lý
    else closecontextEnabled = false
        Note over C: Không chủ động đóng do thuộc tính này
    end
    Note over P: JVM chỉ thoát khi điều kiện kết thúc tiến trình được đáp ứng
~~~

Một vài chi tiết quan trọng:

- `TaskRepository` có thể tạo bản ghi lần chạy trước khi thực thi `ApplicationRunner` / `CommandLineRunner`, sau khi context đã khởi tạo thành công.
- Spring Cloud Task cập nhật thông tin kết thúc khi hoàn thành các runner hoặc khi gặp lỗi được framework ghi nhận.
- Bật `closecontextEnabled` hướng đến bước **đóng context** khi task đã kết thúc; nó không quyết định kết quả nghiệp vụ hoặc tự chạy lại tác vụ.
- Thứ tự từng dòng log của các listener phụ thuộc phiên bản, thread và cấu hình logging. Không dựa duy nhất vào vài dòng log để suy ra mọi tài nguyên đã đóng thành công.

Trong trường hợp khởi tạo `ApplicationContext` thất bại rất sớm, Spring Cloud Task có thể **chưa tạo được TaskExecution**. Nếu JVM bị kill cưỡng bức, callback đóng context cũng có thể không chạy đầy đủ.

## 4. Ví dụ: bật tự đóng context cho task

Ví dụ bên dưới giả định ứng dụng đã được thêm dependency Spring Cloud Task tương thích và có `DataSource` cùng schema metadata phù hợp. Ta xây một công việc tạo báo cáo theo ngày. Nghiệp vụ được đơn giản hóa để tập trung quan sát vòng đời.

### 4.1. application.yml

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-report-task
      closecontext-enabled: true

logging:
  level:
    root: INFO
~~~

Cấu hình `web-application-type: none` giúp tránh khởi động máy chủ HTTP không cần thiết cho task dạng CLI. Nó **không tự tắt executor hoặc luồng nền**. Với nhu cầu lưu trạng thái thực thi bền vững, phải cấu hình `DataSource` và chuẩn bị schema `TaskRepository` tương ứng; ví dụ rút gọn trên không trình bày mật khẩu hoặc URL database.

### 4.2. Ứng dụng Spring Boot

~~~java
import java.time.LocalDate;
import java.util.List;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyReportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner() {
        return args -> {
            List<String> values = args.getOptionValues("reportDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Can truyen --reportDate=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(values.get(0));
            log.info("REPORT_START reportDate={}", date);

            // TODO: Thay bằng công việc nghiệp vụ đồng bộ.
            log.info("REPORT_DONE reportDate={}", date);
        };
    }

    @PreDestroy
    public void onBeanDestroy() {
        log.info("SPRING_BEAN_DESTROY: preparing to release resources");
    }
}
~~~

**Giải thích ví dụ:**

- `@EnableTask` thể hiện việc kích hoạt tích hợp Spring Cloud Task trong ứng dụng mẫu.
- `ApplicationRunner` chạy nghiệp vụ hữu hạn và **chỉ trả về khi công việc đồng bộ đã xong**.
- `@PreDestroy` nằm trên một bean do Spring quản lý, nên là dấu hiệu hữu ích để quan sát quá trình Spring đóng context.
- Phương thức `main` **không gọi `System.exit(...)` hoặc `SpringApplication.exit(...)`**, giúp bạn quan sát hành vi của riêng cấu hình `closecontextEnabled`.
- Dòng `SPRING_BEAN_DESTROY` cho thấy callback hủy bean được gọi trong quá trình đóng context; nó **không tự chứng minh JVM đã thoát** hoặc mọi hệ thống bên ngoài đã hoàn tất công việc.

Ví dụ dùng `jakarta.annotation.PreDestroy`, phù hợp các thế hệ Spring Boot hiện đại. Với dự án dùng thế hệ cũ, package annotation và dependency có thể khác.

### 4.3. Chạy và đọc log

~~~bash
java -jar daily-report-task.jar --reportDate=2026-11-23
~~~

Đoạn sau chỉ là **log minh họa** để nhận diện các mốc; thời gian, tên logger và các dòng nội bộ có thể khác:

~~~text
INFO  ... Starting DailyReportTaskApplication
INFO  ... REPORT_START reportDate=2026-11-23
INFO  ... REPORT_DONE reportDate=2026-11-23
INFO  ... SPRING_BEAN_DESTROY: preparing to release resources
~~~

Điều cần xác minh là **nghiệp vụ hoàn tất trước khi tài nguyên của bean bị hủy**. Log `SPRING_BEAN_DESTROY` chỉ phản ánh hook dọn dẹp; nếu log kết thúc công việc bị thiếu, hãy kiểm tra runner có ném lỗi hoặc trả về quá sớm hay không.

Trong một ứng dụng không còn luồng nền, cả cấu hình `true` lẫn `false` đều có thể kết thúc tiến trình và chạy `@PreDestroy` thông qua các cơ chế shutdown khác nhau. Vì thế **chỉ nhìn thấy `@PreDestroy` không đủ để chứng minh thuộc tính đã được bật**. Hãy kiểm tra giá trị cấu hình được nạp, thời điểm đóng và nguồn giữ tiến trình sống.

## 5. Kiểm tra TaskRepository sau khi context đóng

Đóng context không xóa bản ghi thực thi. Với database bền vững và cập nhật thành công, `TaskRepository` giữ lịch sử từng lần chạy.

Ví dụ truy vấn bảng `TASK_EXECUTION` theo tên task:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-report-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Tên bảng và cột ở đây theo schema SQL thường dùng của Spring Cloud Task; cần đối chiếu với schema của phiên bản ứng dụng. Kết quả minh họa cho lần chạy bình thường:

| TASK_NAME | START_TIME | END_TIME | EXIT_CODE |
| --- | --- | --- | --- |
| daily-report-task | 2026-11-24 08:10:01 | 2026-11-24 08:10:02 | 0 |

Dòng này cho biết framework ghi nhận một lần chạy đã kết thúc với mã thoát `0`. Nó **không khẳng định Spring context đã đóng**, bởi trạng thái đóng context không phải trường chuyên biệt trong `TASK_EXECUTION`; cũng không bảo đảm file báo cáo hoặc dữ liệu nghiệp vụ đúng. Cần đối chiếu đồng thời:

1. **Log nghiệp vụ**: có `REPORT_DONE` và dữ liệu thực sự được tạo đúng không?
2. **Repository**: bản ghi có thời gian kết thúc, mã thoát và thông tin lỗi phù hợp không?
3. **Vòng đời ứng dụng**: có callback dọn dẹp và tiến trình/pod kết thúc hay vẫn còn hoạt động?
4. **Hệ thống vận hành**: scheduler hoặc orchestrator ghi nhận mã thoát tiến trình và timeout thế nào?

Nếu `END_TIME` trống, **không** vội kết luận task đang chạy: tiến trình có thể đã bị dừng cưỡng bức hoặc không cập nhật repository kịp. Xác minh trạng thái thực tế ở hệ điều hành/container và log hạ tầng.

## 6. Rủi ro lớn nhất: runner trả về trước khi xử lý bất đồng bộ kết thúc

Khi `closecontextEnabled=true`, Spring Cloud Task có thể đóng context ngay sau khi các runner **đã trả về**. Nếu runner chỉ **khởi động** một công việc nền rồi thoát, metadata có thể đánh dấu task hoàn tất trong khi công việc nền vẫn đang chạy.

Ví dụ cách làm **không phù hợp** cho tác vụ cần đợi công việc thực sự kết thúc:

~~~java
@Bean
ApplicationRunner prematureRunner(ReportService reportService) {
    return args -> {
        reportService.generateAsync();
        // Runner trả về ngay, công việc bất đồng bộ còn đang chạy.
    };
}
~~~

Tác động có thể gặp:

- Bean executor, DataSource hoặc client HTTP do Spring quản lý bị đóng khi công việc vẫn đang sử dụng.
- Công việc bị ngắt hoặc hoàn thành một phần nhưng `TaskExecution` đã được ghi nhận hoàn tất.
- Task bị coi là thành công; lần chạy lại có thể ghi trùng dữ liệu.
- Có luồng không chịu quản lý của Spring tiếp tục giữ JVM sống dù context đã đóng.

**Giải pháp:** chỉ để runner kết thúc khi tất cả phần việc bắt buộc đã thành công hoặc đã được kết luận thất bại.

Ví dụ dùng `CompletableFuture` và đợi trước khi runner trả về:

~~~java
@Bean
ApplicationRunner awaitedRunner(ReportService reportService) {
    return args -> {
        CompletableFuture<Void> result =
                reportService.generateAsync();
        result.join(); // Đợi hoàn tất; lỗi async sẽ được chuyển ra runner.
    };
}
~~~

Đoạn này giả định `generateAsync()` trả về `CompletableFuture<Void>` đại diện đúng cho **toàn bộ** công việc. Nếu chỉ trả về một future cho bước đầu, việc gọi `join()` vẫn chưa bảo đảm các bước sau đã xong. Trong production, nên đặt timeout, xử lý hủy công việc, truyền lỗi lên caller và bảo đảm chính sách retry/idempotent. Nếu dùng `@Async`, phải có executor thích hợp và future phản ánh kết quả thật; thao tác kiểu fire-and-forget không phù hợp với việc xác định task đã hoàn tất.

### Với Spring Batch

Khi ứng dụng Spring Cloud Task dùng **Spring Batch**, cần phân biệt:

- **TaskRepository** ghi nhận vòng đời của ứng dụng task.
- **JobRepository** ghi nhận job, step, trạng thái xử lý và checkpoint của Spring Batch.

Nếu một `JobLauncher` được cấu hình chạy bất đồng bộ, runner có thể trả về khi Batch job vẫn đang xử lý. Bật tự đóng context lúc đó có thể gây lỗi hoặc ngắt công việc chưa hoàn tất. Hãy thiết kế để lần chạy task **đợi Batch job kết thúc** và phản ánh chính xác trạng thái job, thay vì xem việc gửi yêu cầu chạy job là hoàn thành nghiệp vụ.

## 7. Dọn dẹp tài nguyên đúng cách

Đóng Spring context là tín hiệu cho các thành phần được Spring quản lý đi qua vòng đời hủy. Các cơ chế thường gặp gồm:

- `@PreDestroy` trên bean được Spring quản lý để đóng file, kết nối hoặc tài nguyên chuyên dụng.
- `DisposableBean` hoặc destroy method của bean để dọn dẹp tài nguyên.
- `SmartLifecycle.stop()` đối với thành phần có vòng đời do context kiểm soát.
- Cơ chế shutdown của executor, pool kết nối, client và thư viện do Spring quản lý.

Ví dụ một tài nguyên được tạo riêng cho task:

~~~java
@Component
public class ReportFileHandle {

    private final Logger log =
            LoggerFactory.getLogger(ReportFileHandle.class);

    @PreDestroy
    void cleanup() {
        log.info("Closing report file handle");
        // Đóng handle thực tế nếu đang sở hữu tài nguyên đó.
    }
}
~~~

Ví dụ chỉ minh họa callback; không nên ghi `@PreDestroy` để tạo kết quả nghiệp vụ chính hoặc thực hiện một giao dịch dài quan trọng. Nếu shutdown bị cắt ngang, đoạn xử lý dọn dẹp có thể không kịp hoàn tất. Dữ liệu nghiệp vụ cốt lõi cần được commit **trước khi runner trả về**.

**Đóng context không đảm bảo mọi luồng đều bị dừng.** Luồng tạo bằng `new Thread(...)`, executor không đăng ký làm bean hoặc thư viện không tôn trọng shutdown có thể vẫn giữ JVM sống. Đồng thời, gọi `System.exit(...)` cưỡng bức có thể bỏ qua công việc đang dở hoặc giới hạn thời gian dọn dẹp; không dùng nó như một cách sửa nhanh cho thiếu quản lý tài nguyên.

## 8. So sánh với các cách kết thúc ứng dụng khác

| Cách làm | Phạm vi tác động | Lưu ý |
| --- | --- | --- |
| `spring.cloud.task.closecontextEnabled=true` | Yêu cầu Spring Cloud Task đóng context khi hoàn tất vòng đời task | Thích hợp khi runner kết thúc sau toàn bộ nghiệp vụ; không ép dừng mọi thread. |
| `SpringApplication.exit(context)` | Đóng context được truyền và tính exit code theo Spring Boot | Ứng dụng chủ động điều khiển thời điểm; cần tránh đóng trước khi task cập nhật và xử lý xong. |
| `System.exit(code)` | Yêu cầu JVM thoát với mã được chỉ định | Không nên gọi giữa nghiệp vụ; có thể cắt ngang tiến trình và công việc nền. |
| `spring.main.web-application-type=none` | Không khởi động loại web application của Spring Boot | Hữu ích cho CLI, nhưng không đảm nhận đóng context sau task. |
| Dừng pod/job ở hạ tầng | Kết thúc vòng đời tiến trình/container theo chính sách nền tảng | Timeout, tín hiệu và thời gian graceful shutdown có thể ảnh hưởng cập nhật repository. |

**Không cần kết hợp tất cả các cách trên.** Khi chọn `closecontextEnabled=true`, hãy để runner trả về tự nhiên và để Spring Cloud Task xử lý vòng đời. Nếu ứng dụng cần mã thoát hệ điều hành khác `0`, cần thiết kế ánh xạ ngoại lệ và exit code riêng, rồi kiểm chứng trong môi trường khởi chạy thực tế; thuộc tính đóng context không phải thiết lập exit code.

## 9. Tình huống thực tế và lựa chọn cấu hình

### Tình huống A — Tạo báo cáo theo lịch

Ứng dụng nhận `--reportDate=yyyy-MM-dd`, truy vấn dữ liệu, tạo file và tải lên kho lưu trữ. Khi tất cả bước hoàn tất, runner trả về. **Nên bật** `closecontextEnabled=true`, kết hợp `web-application-type=none` khi phù hợp và để Kubernetes CronJob hoặc scheduler khác quyết định thời điểm khởi chạy.

Cần thêm kiểm tra kết quả đầu ra, khả năng chạy lại an toàn và timeout tại hạ tầng. Thuộc tính đóng context không tạo lịch chạy, không tự thử lại tác vụ.

### Tình huống B — Task có executor giữ thread

Một task đã ghi `END_TIME` vào repository nhưng tiến trình vẫn hoạt động vì executor còn thread. **Có thể bật** `closecontextEnabled=true` nếu executor là bean Spring có chính sách shutdown phù hợp, đồng thời runner đã đợi mọi việc quan trọng kết thúc. Nếu luồng không thuộc Spring, phải sửa cách quản lý luồng thay vì kỳ vọng thuộc tính này giải quyết hoàn toàn.

### Tình huống C — Task phát lệnh chạy job nền

Runner gọi API khởi tạo một job dài hạn rồi trả về. Nếu mục tiêu của task chỉ là **gửi lệnh**, kết quả nghiệp vụ của chính task phải được định nghĩa rõ là “đã gửi lệnh thành công”; việc hoàn tất job ở hệ thống khác cần được theo dõi độc lập. Nếu mục tiêu là **hoàn tất job**, runner phải đợi kết quả job và phản ánh lỗi đúng.

### Tình huống D — Ứng dụng web kiêm task

Ứng dụng mở HTTP server để phục vụ request liên tục nhưng cũng có một runner khởi động. Bật `closecontextEnabled=true` có thể làm đóng web context khi runner hoàn tất, khiến dịch vụ HTTP dừng ngoài ý muốn. **Không dùng tùy chọn này cho cùng một process cần phục vụ liên tục**; tách công việc hữu hạn thành ứng dụng task riêng nếu cần.

## 10. Thực hành quan sát hai cấu hình

Với ứng dụng minh họa ở phần 4, thực hiện trong môi trường thử nghiệm:

**Lần 1 — bật tự đóng context:**

~~~bash
java -jar daily-report-task.jar \
  --reportDate=2026-11-23 \
  --spring.cloud.task.closecontextEnabled=true
~~~

**Lần 2 — tắt cơ chế tự đóng của Spring Cloud Task:**

~~~bash
java -jar daily-report-task.jar \
  --reportDate=2026-11-24 \
  --spring.cloud.task.closecontextEnabled=false
~~~

Hai lệnh trên minh họa cú pháp shell hỗ trợ nối dòng bằng dấu `\` (Linux/macOS). Trên PowerShell, đặt toàn bộ tham số trên **một dòng**:

~~~powershell
java -jar daily-report-task.jar --reportDate=2026-11-24 --spring.cloud.task.closecontextEnabled=false
~~~

Quan sát theo các bước:

1. Xác nhận profile và giá trị `closecontextEnabled` thực sự đã được nạp ở mỗi lần chạy.
2. Ghi nhận log `REPORT_START` và `REPORT_DONE`; bảo đảm nghiệp vụ hoàn tất.
3. Tìm thông điệp `SPRING_BEAN_DESTROY` và kiểm tra tiến trình có kết thúc hay còn thread sống.
4. Đối chiếu bản ghi `TASK_EXECUTION` cho từng lần chạy. Hai lần chạy phải có ID riêng; trong môi trường bình thường cả hai đều có thể có thời gian kết thúc.
5. Kết luận dựa trên **hành vi thực tế và cấu hình**, không chỉ dựa trên việc có hay không có dòng `@PreDestroy`. Với task đơn giản, khác biệt có thể không dễ nhìn thấy vì JVM shutdown hook cũng đóng context ở cấu hình `false`.

Nếu muốn khảo sát lý do tiến trình còn chạy, dùng một executor **được Spring quản lý** trong môi trường thử nghiệm và có cơ chế dừng, timeout rõ ràng. Không tạo vòng lặp vô hạn hoặc luồng không kiểm soát chỉ để “thử xem JVM có treo không”.

## 11. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `closecontextEnabled=true` nhưng JVM không thoát | Non-daemon thread chưa dừng, executor tự tạo, callback shutdown bị kẹt | Lấy thread dump, kiểm tra bean/executor, timeout và tín hiệu dừng. |
| Context đóng khi công việc vẫn đang chạy | Runner khởi động async rồi trả về sớm | Chờ `Future`/`CompletableFuture` hoặc completion thật trước khi runner kết thúc. |
| Không thấy callback `@PreDestroy` | Bean không do Spring quản lý, context bị kill, log bị lọc hoặc task lỗi quá sớm | Kiểm tra lifecycle bean, mức log, stack trace và cách dừng tiến trình. |
| `TaskExecution` có `END_TIME` nhưng kết quả nghiệp vụ chưa có | Xử lý async hoặc coi việc gửi yêu cầu là hoàn thành | Chỉ đánh dấu thành công sau khi xác nhận tác động nghiệp vụ. |
| Không có bản ghi thực thi | Context chưa bootstrap hoàn chỉnh, DataSource/schema lỗi hoặc task chưa kích hoạt | Kiểm tra log khởi động, dependency, `@EnableTask`, kết nối database. |
| Task chạy tốt khi CLI nhưng lỗi trên Kubernetes | Hạ tầng gửi tín hiệu, timeout hoặc đóng container quá sớm | So sánh termination grace period, log pod, mã thoát và trạng thái repository. |
| Dịch vụ HTTP bất ngờ dừng | Dùng tùy chọn đóng context trên ứng dụng vốn cần chạy liên tục | Tách task thành process hữu hạn riêng; xem lại phân chia chức năng. |

### Checklist trước khi dùng trong production

- [ ] Từng runner chỉ trả về khi **toàn bộ công việc cần hoàn tất** đã xong hoặc lỗi đã được báo.
- [ ] Không còn công việc “fire-and-forget” chưa được theo dõi; có timeout rõ ràng cho các Future.
- [ ] Executor, pool kết nối và tài nguyên nền được Spring quản lý hoặc có phương thức shutdown minh bạch.
- [ ] Đã kiểm tra trường hợp thành công, lỗi nghiệp vụ, lỗi database và dừng tiến trình bất thường.
- [ ] `TaskRepository` lưu metadata ở database phù hợp; đối chiếu được lần chạy với log.
- [ ] Có mã thoát và quy tắc retry phù hợp cho scheduler/orchestrator.
- [ ] Nếu tích hợp Spring Batch, trạng thái job và task được theo dõi đúng trách nhiệm của từng repository.
- [ ] Ứng dụng là task hữu hạn, không phải dịch vụ bắt buộc giữ context sống liên tục.
- [ ] Có giám sát thời gian chạy, tài nguyên, bản ghi chưa kết thúc và chính sách vận hành khi task bị kẹt.

## 12. Tổng kết

`spring.cloud.task.closecontextEnabled=true` là một lựa chọn quản lý vòng đời dành cho ứng dụng **Spring Cloud Task chạy hữu hạn**: sau khi các runner đã hoàn tất và metadata thực thi được cập nhật, framework chủ động đóng Spring `ApplicationContext`. Trong YAML, có thể dùng dạng `spring.cloud.task.closecontext-enabled: true`; mặc định thuộc tính là `false` trong các phiên bản hiện hành.

Hãy luôn phân biệt **task hoàn tất**, **context đóng** và **JVM thoát**. Điều kiện để dùng tùy chọn này an toàn là runner phản ánh đúng sự hoàn tất của công việc, tài nguyên được quản lý đúng cách và cơ chế chạy lại không tạo tác động trùng lặp. Từ đó, bạn có thể triển khai task theo lịch, theo yêu cầu hoặc phối hợp với Spring Batch mà vẫn kiểm soát được trạng thái thực thi và kết quả trong database.

### Tài liệu tham khảo

- [Spring Cloud Task Reference — The lifecycle of a Spring Cloud Task](https://docs.spring.io/spring-cloud-task/reference/features.html#the-lifecycle-of-a-spring-cloud-task)
- [Spring Cloud Task Reference — Closing the Context](https://docs.spring.io/spring-cloud-task/reference/features.html#closing-the-context)
- [Spring Cloud configuration properties](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
