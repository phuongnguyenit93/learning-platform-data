# Phân biệt Spring Cloud Task với @Scheduled, @Async và TaskExecutor

## 1. Bốn công cụ giải quyết bốn câu hỏi khác nhau

Trong hệ sinh thái Spring, một công việc như “xuất báo cáo doanh thu mỗi đêm” có thể khiến chúng ta nghĩ đến `Spring Cloud Task`, `@Scheduled`, `@Async` hoặc `TaskExecutor`. Chúng có thể cùng xuất hiện trong một giải pháp, nhưng không cùng chịu trách nhiệm cho một việc.

- **Spring Cloud Task** trả lời: *Một lần chạy ứng dụng có thời gian hữu hạn bắt đầu khi nào, kết thúc ra sao và trạng thái thực thi được lưu ở đâu?*
- **`@Scheduled`** trả lời: *Phương thức này cần được kích hoạt vào thời điểm hoặc chu kỳ nào trong một ứng dụng đang chạy?*
- **`@Async`** trả lời: *Làm thế nào gọi một phương thức mà không buộc luồng gọi phải đợi phương thức chạy xong?*
- **`TaskExecutor`** trả lời: *Công việc kiểu `Runnable` được giao cho luồng hoặc nhóm luồng nào để thực thi?*

Sự khác nhau cốt lõi nằm ở **đơn vị thực thi**. Spring Cloud Task theo dõi **một lần thực thi của ứng dụng Spring Boot** (thường là một tiến trình chạy một việc rồi thoát). Ba công cụ còn lại chủ yếu quản lý **lệnh gọi phương thức và công việc bên trong một ứng dụng đang sống**.

Ví dụ: một hệ thống thương mại điện tử cần chốt doanh thu lúc 02:00, xuất dữ liệu cho đối tác, ghi nhận lần xuất thành công/thất bại và cho phép chạy bù ngày trước đó. Có thể dùng Kubernetes CronJob để **khởi chạy** một ứng dụng Spring Cloud Task lúc 02:00; trong lần chạy đó, ứng dụng dùng `TaskExecutor` để xử lý đồng thời nhiều phần dữ liệu, rồi **kết thúc tiến trình**. `TaskRepository` của Spring Cloud Task ghi lại metadata của lần chạy. Nếu chỉ đặt `@Scheduled` trong ứng dụng API luôn bật, ta có lịch gọi phương thức nhưng chưa tự có vòng đời tiến trình ngắn hạn hay lịch sử thực thi bền vững.

## 2. Bảng so sánh nhanh

| Tiêu chí | Spring Cloud Task | `@Scheduled` | `@Async` | `TaskExecutor` |
|---|---|---|---|---|
| Bản chất | Framework theo dõi vòng đời một lần chạy ứng dụng ngắn hạn | Annotation kích hoạt phương thức theo lịch | Annotation thực thi phương thức theo cơ chế bất đồng bộ | Interface trừu tượng để thực thi công việc trên executor |
| Đơn vị chính | **TaskExecution** của một lần chạy ứng dụng | Một lần gọi phương thức theo lịch | Một lần gọi phương thức thông qua Spring proxy | Một `Runnable` hoặc công việc được executor nhận |
| Kích hoạt | Tiến trình ứng dụng được khởi chạy bởi CLI, scheduler, API điều phối, CronJob… | `fixedDelay`, `fixedRate`, `cron` khi ứng dụng còn sống | Mã gọi phương thức qua Spring-managed proxy | Mã gọi `execute(...)` hoặc API liên quan |
| Cần ứng dụng chạy thường trực? | Thường **không**: hoàn thành và thoát | **Có**: lịch chỉ hoạt động khi ứng dụng còn chạy | Cần một ứng dụng đang chạy để nhận và thực hiện lời gọi | Cần một executor và môi trường thực thi đang sống |
| Lịch chạy tích hợp? | **Không** tự quyết định giờ chạy | **Có**, ở mức nội bộ tiến trình | Không | Không; lập lịch là vai trò khác, như `TaskScheduler` |
| Metadata lịch sử trong CSDL? | **Có**, khi cấu hình repository và CSDL bền vững | Không tự cung cấp | Không tự cung cấp | Không tự cung cấp |
| Xử lý song song? | Không tự động song song hóa nghiệp vụ | Phụ thuộc cấu hình scheduler, số instance và cách gọi | Có thể đẩy lời gọi sang executor | Có, tùy loại executor, pool và hàng đợi |
| Retry, restart, điều phối đa instance? | Có dữ liệu để quan sát lần chạy; **không** tự thay thế công cụ điều phối/retry | Không tự bảo đảm retry bền vững hay chỉ chạy một lần trên toàn cluster | Không tự bảo đảm retry bền vững | Không tự bảo đảm retry bền vững |
| Điểm cần quan tâm | Schema, TaskRepository, mã thoát, idempotency, lần chạy treo | Múi giờ, lịch bị bỏ lỡ, chạy trùng ở nhiều instance | Proxy, xử lý exception, mất việc khi tiến trình dừng | Kích thước pool, queue, rejection, shutdown |

> **Lưu ý thuật ngữ:** `TaskExecutor` của Spring Framework là interface hạ tầng xử lý công việc; **Spring Cloud Task** là giải pháp ghi nhận vòng đời tác vụ ứng dụng. Chúng không phải hai cách đặt tên cho cùng một loại “task”.

## 3. Spring Cloud Task: một lần chạy có bắt đầu và kết thúc rõ ràng

### 3.1. Vòng đời và TaskRepository

Spring Cloud Task phù hợp với ứng dụng Spring Boot mà nghiệp vụ có điểm hoàn thành xác định, ví dụ đồng bộ dữ liệu, xuất báo cáo, đối soát, nhập file, dọn dữ liệu theo đợt hoặc một bước trong pipeline.

Khi ứng dụng được cấu hình Spring Cloud Task và repository phù hợp, một lần khởi chạy hình thành **`TaskExecution`**. Dữ liệu do **`TaskRepository`** quản lý thường có mã lần chạy, tên task, thời điểm bắt đầu/kết thúc, mã thoát và thông tin lỗi/thoát. **`TaskExplorer`** hỗ trợ đọc và tra cứu các lần chạy đã lưu. Khi dùng CSDL bền vững và schema tương ứng, metadata này tiếp tục tồn tại sau khi tiến trình kết thúc.

~~~mermaid
sequenceDiagram
    participant T as CronJob / CLI / Orchestrator
    participant A as Ứng dụng Spring Cloud Task
    participant R as TaskRepository
    participant D as Hệ thống nghiệp vụ
    T->>A: Khởi chạy tiến trình với tham số
    A->>R: Tạo TaskExecution, ghi thời gian bắt đầu
    A->>D: Đọc, tính toán, xuất hoặc nhập dữ liệu
    alt Thành công
        D-->>A: Hoàn thành
        A->>R: Ghi kết thúc và mã thoát
    else Lỗi có thể xử lý
        D-->>A: Trả lỗi
        A->>R: Ghi thông tin lỗi và kết quả lần chạy
    end
    A-->>T: Tiến trình dừng và trả mã thoát cho bên gọi
~~~

Khả năng ghi metadata có **giới hạn quan trọng**: `TaskRepository` không tự lưu toàn bộ báo cáo, bản ghi đầu ra, log chi tiết hoặc kết quả nghiệp vụ của bạn. Ứng dụng phải lưu những dữ liệu đó vào nơi thích hợp, chẳng hạn bảng nghiệp vụ hay object storage, rồi liên kết với `taskExecutionId` nếu cần truy vết. Nếu tiến trình bị buộc dừng đột ngột (ví dụ `SIGKILL`), bản ghi có thể chưa có thời điểm kết thúc; hệ thống giám sát cần nhận diện lần chạy quá hạn.

### 3.2. Ví dụ ứng dụng chạy một lần

Giả sử cần xuất doanh thu cho một ngày được truyền từ dòng lệnh. Phần sau minh họa các thành phần chính; nghiệp vụ thực tế đặt trong một service có thể kiểm thử độc lập.

~~~java
import java.time.LocalDate;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class DailyExportTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DailyExportTaskApplication.class, args);
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner exportDailyRevenue(RevenueExportService exportService) {
        return args -> {
            var dates = args.getOptionValues("date");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException("Yeu cau --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            exportService.export(date);
        };
    }
}
~~~

`RevenueExportService` ở đây là service nghiệp vụ do dự án tự xây dựng; ví dụ cố ý không triển khai chi tiết đọc/ghi dữ liệu. Đầu vào khi khởi chạy:

~~~bash
java -jar daily-export-task.jar --date=2026-11-23
~~~

Cấu hình Spring Boot tối thiểu để ứng dụng không khởi động web server và đặt tên task có thể như sau:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-revenue-export
  cloud:
    task:
      name: daily-revenue-export
~~~

Dự án cần dependency Spring Cloud Task tương thích với phiên bản Spring Boot/Spring Cloud và cần cấu hình **DataSource + schema metadata** đúng với phiên bản triển khai nếu muốn lưu TaskExecution bền vững. Với môi trường sản xuất, hãy cấp schema bằng migration có kiểm soát và quyền CSDL phù hợp. Việc bật `@EnableTask` và cách cấu hình khởi tạo schema có thể khác theo phiên bản; kiểm tra tài liệu của phiên bản đang dùng.

Trong ví dụ, `ApplicationRunner` chạy nghiệp vụ một lần khi ứng dụng khởi động. `SpringApplication.exit(context)` đóng Spring context, còn `System.exit(...)` truyền mã thoát cho hệ điều hành. Để kết quả thành công/thất bại rõ ràng, cần có quy ước mã thoát và xử lý exception nhất quán; không chỉ in thông báo lỗi rồi nuốt exception. Với tiến trình bị kill hoặc mất kết nối đến repository, không được giả định mọi lỗi đều có bản ghi kết thúc đầy đủ.

Khi chạy nhiều lần, ta có thể khảo sát lịch sử bằng truy vấn minh họa sau, nếu schema đúng theo thiết kế bảng Spring Cloud Task tương ứng:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

**Một TaskExecution tương ứng một lần thực thi**, do đó chạy bù ngày hôm qua tạo thêm lần chạy mới. Việc nó có được phép xuất cùng một ngày thêm lần nữa và có ghi trùng dữ liệu hay không là quyết định nghiệp vụ, không phải bảo đảm mặc định của TaskRepository.

## 4. @Scheduled: kích hoạt phương thức khi ứng dụng đang chạy

`@Scheduled` thuộc Spring Framework. Khi bật cơ chế scheduling, Spring gọi phương thức theo lịch đã khai báo. Đây là một lựa chọn đơn giản cho quét trạng thái, dọn cache, làm mới dữ liệu, tổng hợp thống kê nhỏ hoặc công việc định kỳ **gắn với vòng đời ứng dụng thường trực**.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class SchedulingConfiguration {
}

@Component
class PeriodicReportJob {

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    public void triggerReport() {
        // Gọi service nghiệp vụ hoặc yêu cầu hệ điều phối
        // khởi chạy ứng dụng Spring Cloud Task.
    }
}
~~~

Ba cách khai báo phổ biến:

- `fixedDelay`: chờ một khoảng thời gian sau khi lần gọi trước hoàn thành rồi mới kích hoạt lần tiếp theo.
- `fixedRate`: định kỳ theo mốc bắt đầu dự kiến; khả năng chạy chồng lấn còn tùy scheduler, số luồng, cấu hình và cách thực thi phương thức.
- `cron`: kích hoạt theo biểu thức lịch; có thể khai báo `zone` để tránh phụ thuộc múi giờ của máy chủ.

Những gì `@Scheduled` **không tự làm**: tạo TaskExecution trong CSDL, lưu lịch sử nhiều lần chạy, bảo đảm chạy duy nhất giữa nhiều instance, hoặc chạy bù các lần bị lỡ khi ứng dụng tắt. Nếu hai replica cùng chứa phương thức `@Scheduled`, **mỗi replica có thể kích hoạt lịch riêng**. Cần cơ chế điều phối phù hợp, như chỉ đặt scheduler ở một thành phần, khóa phân tán được thiết kế đúng hoặc scheduler ngoài ứng dụng.

Đặc biệt, chạy một phương thức `@Scheduled` trong web app không khiến toàn bộ web app trở thành ứng dụng Spring Cloud Task. Scheduler có thể dùng để **gửi yêu cầu khởi chạy** một task riêng, nhưng phải có cơ chế khởi chạy tiến trình hoặc container thực sự.

## 5. @Async: không chặn luồng gọi phương thức

`@Async` hữu ích khi một lời gọi có thể chạy trên luồng khác và người gọi không cần chờ hoàn thành ngay. Ví dụ hệ thống API có thể gửi yêu cầu tạo bản xem trước và trả lời sớm; nghiệp vụ phía sau tiếp tục xử lý trên executor.

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;

@Configuration
@EnableAsync
class AsyncConfiguration {
}

@Service
class PreviewService {

    @Async("previewExecutor")
    public CompletableFuture<String> generatePreview(String documentId) {
        // Thực thi trên executor được cấu hình.
        String location = "/previews/" + documentId + ".pdf";
        return CompletableFuture.completedFuture(location);
    }
}
~~~

Khi một **bean khác** gọi `previewService.generatePreview(...)` qua Spring proxy, phần thân phương thức có thể được thực thi trên executor tên `previewExecutor` và trả về `CompletableFuture` cho người gọi. Tên executor này phải được khai báo bằng bean tương ứng (xem mục 6).

Cần hiểu đúng một số giới hạn:

1. **Lời gọi nội bộ cùng bean** (`this.generatePreview(...)`) trong cơ chế proxy thông thường sẽ không đi qua interceptor `@Async`, nên không tạo hành vi bất đồng bộ như mong đợi. Tách sang bean khác hoặc dùng cơ chế phù hợp.
2. Exception trong phương thức trả về `Future`/`CompletableFuture` cần được người gọi quan sát qua future. Với phương thức `void`, lỗi không thể được trả về người gọi theo cách đó; cần cơ chế xử lý exception bất đồng bộ.
3. Công việc đang nằm trong bộ nhớ hoặc hàng đợi của executor có thể bị mất nếu tiến trình dừng. `@Async` tự nó không tạo hàng đợi bền vững hay lịch sử tác vụ trong CSDL.
4. Chạy `@Async` rồi lập tức cho tiến trình Spring Cloud Task kết thúc là một lỗi thiết kế phổ biến. **Ứng dụng ngắn hạn phải đợi các công việc con hoàn thành**, gom lỗi và đảm bảo dữ liệu đã được lưu trước khi chốt TaskExecution/thoát.

Nếu một tác vụ dài phải được tiếp tục sau khi API restart, yêu cầu nghiệp vụ thường cần queue, worker độc lập hoặc một ứng dụng Spring Cloud Task được điều phối, thay vì chỉ dùng `@Async` trong JVM của API.

## 6. TaskExecutor: cách điều khiển luồng, pool và hàng đợi

`TaskExecutor` là interface Spring có phương thức `execute(Runnable task)`. Các triển khai có thể chạy trên luồng mới, dùng thread pool hoặc dùng môi trường thực thi khác. Một dạng thường gặp là `ThreadPoolTaskExecutor`, giúp đặt giới hạn số luồng và số công việc chờ.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class ExecutorConfiguration {

    @Bean("previewExecutor")
    ThreadPoolTaskExecutor previewExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("preview-");
        executor.initialize();
        return executor;
    }
}
~~~

Bean này có thể được `@Async("previewExecutor")` sử dụng, hoặc service khác gọi trực tiếp:

~~~java
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
class ImageProcessingService {
    private final TaskExecutor previewExecutor;

    ImageProcessingService(TaskExecutor previewExecutor) {
        this.previewExecutor = previewExecutor;
    }

    void submit(String imageId) {
        previewExecutor.execute(() -> process(imageId));
    }

    private void process(String imageId) {
        // Xử lý ảnh, lưu kết quả và ghi log/metrics phù hợp.
    }
}
~~~

Ví dụ minh họa giả định `previewExecutor` là bean TaskExecutor được chọn khi inject; nếu dự án có nhiều bean cùng kiểu, hãy dùng `@Qualifier("previewExecutor")` để tránh mơ hồ.

Một pool không có nghĩa công việc chạy vô hạn: khi các luồng bận và queue đầy, yêu cầu mới có thể bị từ chối theo rejection policy. Với các loại executor và cơ chế queue khác nhau, cách tăng số luồng lên `maxPoolSize` cũng khác nhau. Vì vậy phải đo tải và đặt giới hạn phù hợp với CPU, kết nối CSDL, bộ nhớ và dịch vụ bên ngoài.

**`TaskExecutor` không phải `TaskScheduler`.** `TaskExecutor` thực thi công việc được giao; `TaskScheduler` hỗ trợ sắp lịch chạy, còn `@Scheduled` dùng hạ tầng scheduler. Nếu cần lịch chạy, không nên suy luận rằng cứ khai báo `TaskExecutor` là có cron.

## 7. Cách kết hợp các công cụ trong một hệ thống thực tế

Giả sử mỗi đêm cần xuất giao dịch của ngày trước, dữ liệu có thể lớn, phải truy vết được lần chạy và chạy bù khi lỗi.

~~~mermaid
flowchart TD
    S["Kubernetes CronJob hoặc bộ điều phối"] -->|"02:00 / yêu cầu chạy bù"| T["Khởi tạo ứng dụng Spring Cloud Task"]
    T --> R["TaskRepository: mở TaskExecution"]
    T --> B["ApplicationRunner / nghiệp vụ xuất dữ liệu"]
    B --> E["TaskExecutor: xử lý song song có giới hạn"]
    E --> O["Lưu báo cáo và kết quả nghiệp vụ"]
    O --> F["Chốt kết quả, đóng context, thoát"]
    F --> R2["TaskRepository: cập nhật TaskExecution"]
    F --> M["Bộ điều phối đọc mã thoát và quyết định retry/cảnh báo"]
~~~

Lựa chọn kiến trúc có thể như sau:

1. **Lịch và kích hoạt:** Kubernetes CronJob, scheduler ngoài hoặc một API điều phối tạo một phiên chạy Spring Cloud Task, truyền `--date=...`. Nếu lịch nằm trong ứng dụng thường trực, `@Scheduled` chỉ đóng vai trò **kích hoạt yêu cầu**.
2. **Ghi nhận lần chạy:** Spring Cloud Task tạo `TaskExecution`. Repository phải nằm ở CSDL chia sẻ, được cấp schema và kết nối ổn định để các lần chạy được truy vấn sau này.
3. **Nghiệp vụ:** `ApplicationRunner` hoặc `CommandLineRunner` gọi service xuất dữ liệu. Nếu tách công việc thành nhiều phân vùng, có thể dùng `TaskExecutor` hoặc `@Async` với giới hạn rõ ràng.
4. **Chờ và tổng hợp:** đợi các future hoàn tất, gom kết quả, ghi đầu ra và lỗi. Không đóng task trước khi các tác vụ con hoàn tất.
5. **Kết thúc và vận hành:** đóng context, trả mã thoát, bên điều phối quyết định cảnh báo/chạy lại. Thiết kế idempotency theo ngày hoặc khóa nghiệp vụ để retry không gây ghi trùng.

Không phải hệ thống nào cũng cần cả bốn. Nếu chỉ có một thao tác nhẹ mỗi phút trong ứng dụng chạy 24/7, thêm một tiến trình Cloud Task cùng repository có thể làm kiến trúc phức tạp hơn mức cần thiết. Ngược lại, nếu phải audit hàng trăm lần chạy theo lô qua nhiều lần deploy, chỉ thêm `@Scheduled`/`@Async` là thiếu thông tin vận hành.

## 8. Spring Cloud Task và Spring Batch: hai tầng metadata bổ sung

Spring Cloud Task thường phối hợp với **Spring Batch** trong các bài toán ETL, nhập/xuất khối lượng lớn và xử lý hàng loạt cần restart.

| Vai trò | Spring Cloud Task | Spring Batch |
|---|---|---|
| Đơn vị theo dõi | Một lần thực thi ứng dụng (`TaskExecution`) | Một lần chạy batch job và các step (`JobExecution`, `StepExecution`) |
| Repository | `TaskRepository` | `JobRepository` |
| Metadata điển hình | Bắt đầu/kết thúc ứng dụng, tên task, mã thoát, thông tin lỗi | Trạng thái job/step, execution context, bộ đếm đọc/ghi/skip, checkpoint |
| Trọng tâm | Vòng đời và khả năng quan sát ở **mức ứng dụng** | Điều phối bước, xử lý chunk và khả năng restart **mức batch job** |

Ví dụ, một container ứng dụng Spring Cloud Task chạy job “import-2026-11-23”. **TaskRepository** cho biết *container ứng dụng này đã chạy và kết thúc thế nào*. **JobRepository** của Spring Batch cho biết *job có bao nhiêu step, đã đọc bao nhiêu bản ghi, dừng ở checkpoint nào và có thể restart thế nào*.

Hai repository có thể cùng dùng một hệ quản trị CSDL nhưng dùng các bảng/schema metadata riêng; không được đánh đồng TaskExecution với JobExecution. Tính năng retry/restart của Spring Batch phụ thuộc cấu hình job, step và đặc điểm nghiệp vụ, không tự xuất hiện chỉ vì bật Spring Cloud Task.

## 9. Những hiểu lầm dễ gây lỗi sản xuất

### “Đã có @Scheduled thì có lịch sử và cơ chế chống chạy trùng”

**Sai.** Annotation chỉ cung cấp điểm kích hoạt theo lịch trong từng tiến trình đang hoạt động. Nếu dịch vụ chạy ba instance, có thể có ba lần kích hoạt; lịch bị lỡ khi tiến trình tắt cũng không mặc nhiên được chạy bù. Cần scheduler/điều phối thích hợp, idempotency và cơ chế lưu kết quả.

### “@Async là job chạy nền an toàn kể cả khi ứng dụng restart”

**Sai.** Executor xử lý công việc trong vòng đời JVM; chưa có cơ chế lưu hàng đợi, xác nhận và khôi phục công việc bền vững. Nếu điều kiện nghiệp vụ yêu cầu không mất việc, hãy thiết kế bằng hệ thống thông điệp bền vững hoặc worker được điều phối với trạng thái lưu ngoài tiến trình.

### “Spring Cloud Task tự chạy theo cron”

**Sai.** Framework tập trung vào lifecycle/metadata của **một lần chạy**. CronJob, CLI, Spring Cloud Data Flow hay một bộ điều phối khác sẽ quyết định **khi nào** tạo lần chạy đó. Nếu lịch kích hoạt nhiều bản sao, repository vẫn không tự cung cấp khóa phân tán hay quy tắc “chỉ một lần cho mỗi ngày”.

### “Cứ nộp mọi việc vào TaskExecutor là task đã hoàn thành”

**Sai.** `execute(...)` thường chỉ xác nhận đã giao công việc (hoặc báo lỗi khi không thể tiếp nhận), không có nghĩa công việc đã chạy xong. Với ứng dụng ngắn hạn, phải chờ completion một cách có kiểm soát, kiểm tra exception và tiến hành graceful shutdown; tránh trả thành công trong khi công việc con chưa lưu xong kết quả.

### “TaskRepository sẽ lưu mọi kết quả nghiệp vụ”

**Sai.** Repository lưu **metadata thực thi**, không phải tự động các file báo cáo, output hoặc toàn bộ log nghiệp vụ. Dùng kho dữ liệu nghiệp vụ, logs và metrics riêng; liên kết bằng task execution ID/correlation ID khi cần.

### “Kết thúc không báo lỗi thì lần chạy chắc chắn thành công”

**Không luôn đúng.** Lỗi bị nuốt, timeout chưa được kiểm tra hoặc công việc `@Async` chưa hoàn tất có thể khiến kết quả bề ngoài thành công. Hãy xác định tiêu chí hoàn tất ở mức nghiệp vụ, kiểm tra mọi future và thống nhất exit code với nơi điều phối.

## 10. Checklist chọn công cụ

| Yêu cầu thực tế | Lựa chọn khởi đầu | Điều kiện bổ sung |
|---|---|---|
| Quét cache/refresh dữ liệu nhỏ mỗi 5 phút trong service luôn bật | `@Scheduled` | Theo dõi lỗi, tránh chạy trùng khi có nhiều instance |
| Cần xử lý một lời gọi mà không chặn request | `@Async` | Pool phù hợp, xử lý exception, không dùng làm hàng đợi bền vững |
| Muốn điều phối hàng chục công việc CPU/I/O trong một JVM | `TaskExecutor` | Giới hạn concurrency/queue, backpressure và graceful shutdown |
| Một lần import/export có điểm kết thúc, cần lưu metadata từng lần chạy | Spring Cloud Task | Repository bền vững, schema, tham số và exit code |
| Import/export theo lịch trên Kubernetes | CronJob + Spring Cloud Task | Concurrency policy, retry, idempotency và giám sát |
| Pipeline xử lý nhiều bước/chunk cần checkpoint và restart | Spring Batch, có thể kết hợp Spring Cloud Task | JobRepository và TaskRepository có vai trò tách biệt |
| Một API cần kích hoạt tác vụ nặng theo yêu cầu | API/bộ điều phối khởi chạy Cloud Task hoặc worker độc lập | Ghi request ID, bảo vệ khỏi chạy trùng và theo dõi kết quả |

Khi quyết định, hãy trả lời lần lượt ba câu hỏi:

- **Ai kích hoạt?** Lịch trong app (`@Scheduled`), người dùng, hệ thống thông điệp hay bộ điều phối bên ngoài?
- **Cái gì được xem là hoàn thành?** Một lời gọi phương thức, tất cả công việc trong executor, hay toàn bộ một lần chạy ứng dụng?
- **Cần lưu trạng thái ở mức nào?** Không cần lịch sử, chỉ cần phản hồi của future, metadata vòng đời (`TaskRepository`), hay trạng thái/ checkpoint chi tiết của Spring Batch (`JobRepository`)?

Nếu ứng dụng cần **chạy hữu hạn, kết thúc rõ ràng và để lại lịch sử lần chạy trong CSDL**, Spring Cloud Task là thành phần phù hợp. `@Scheduled` có thể đảm nhiệm lịch kích hoạt; `@Async` và `TaskExecutor` có thể xử lý đồng thời bên trong lần chạy. Sử dụng chúng đúng tầng trách nhiệm sẽ giúp triển khai tác vụ theo lịch hoặc theo yêu cầu, xử lý lỗi có kiểm soát và vận hành an toàn.
