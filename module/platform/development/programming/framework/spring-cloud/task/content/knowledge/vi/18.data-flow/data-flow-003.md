# Khởi chạy với tham số và thuộc tính triển khai trong Spring Cloud Data Flow

## 1. Bối cảnh: một task, nhiều lần khởi chạy với cấu hình khác nhau

**Spring Cloud Task** giúp tạo ứng dụng Spring Boot có thời gian chạy hữu hạn, theo dõi thời điểm bắt đầu/kết thúc, mã thoát và tham số qua `TaskExecution` trong `TaskRepository`. Khi vận hành trên nhiều máy hoặc container, **Spring Cloud Data Flow (SCDF)** cung cấp cách đăng ký ứng dụng, định nghĩa task, khởi chạy thủ công, chạy theo lịch và theo dõi những lần thực thi.

Ví dụ doanh nghiệp có ứng dụng `dailyclose` để chốt doanh thu:

- Ngày thường, task xử lý dữ liệu tenant `tenant-A` của ngày hôm qua.
- Khi vận hành chạy bù, cần truyền một `businessDate` cụ thể.
- Lúc tải cao, cần tăng memory limit của container.
- Khi chạy kiểm thử, có thể bật `dry-run` nhưng không ghi kết quả.
- Khi triển khai nhiều môi trường, JDBC URL, secret và tài nguyên của worker không giống nhau.

Thay vì đóng gói lại ứng dụng cho mọi lần chạy, ta tách **tham số nghiệp vụ**, **cấu hình của ứng dụng** và **thuộc tính triển khai**. Ba nhóm có trách nhiệm khác nhau và đi qua các lớp hạ tầng khác nhau.

> **Không nhầm vai trò:** Spring Cloud Task là framework chạy ứng dụng và ghi metadata; Spring Cloud Data Flow là nền tảng điều phối việc đăng ký, launch, schedule và quan sát task. Một ứng dụng Spring Cloud Task có thể chạy bằng `java -jar` hoặc Kubernetes Job mà **không cần** SCDF.

## 2. Phân biệt task application, task definition và task execution

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Task application | Artifact/image `dailyclose` | Mã Spring Boot + Spring Cloud Task được đăng ký |
| Task definition | Tên `daily-close` với định nghĩa `dailyclose` | Cấu hình logic SCDF dùng khi launch |
| Task launch | Người dùng/scheduler yêu cầu chạy task | SCDF chuyển yêu cầu tới TaskLauncher |
| Task platform | Local, Kubernetes hoặc nền tảng được cấu hình | Nơi launcher tạo process/container |
| Task execution | Một lần chạy ứng dụng có ID | Metadata trong TaskRepository/SCDF |
| Application arguments | `--date=2026-11-23`, `--tenant=tenant-A` | Đầu vào của một lần xử lý nghiệp vụ |
| App properties | `app.dailyclose.report.format=csv` | Cấu hình Spring Environment của task khi launch |
| Deployer properties | `deployer.dailyclose.kubernetes.limits.memory=1024Mi` | Chỉ dẫn cho platform deployer, không phải nghiệp vụ |

Cùng một `task definition` có thể được launch nhiều lần, tạo nhiều `TaskExecution`. Các lần chạy có thể khác tham số hoặc tài nguyên, nhưng metadata và kết quả nghiệp vụ vẫn cần được phân biệt cẩn thận.

~~~mermaid
flowchart TD
    U["Người dùng / Scheduler / API"] --> DF["Spring Cloud Data Flow"]
    DF --> TD["Task definition: daily-close"]
    TD --> L["TaskLauncher trên task platform"]
    L --> P["JVM / container dailyclose"]
    P --> A["Spring Boot + Spring Cloud Task"]
    A --> R["ApplicationRunner / service nghiệp vụ"]
    A --> TR["TaskRepository: TaskExecution"]
    R --> BD["CSDL / file / hệ thống đích"]
    DF --> M["Task execution monitoring"]
    TR --> M
~~~

Sơ đồ là mô hình kiến trúc. Cách platform nhận app properties hoặc deployer properties phụ thuộc TaskLauncher được cấu hình.

## 3. Ba nhóm thông số: arguments, app properties và deployer properties

| Cơ chế | Dạng trong SCDF Shell | Ai sử dụng? | Ví dụ |
|---|---|---|---|
| **Launch arguments** | `--arguments "..."` | Ứng dụng nhận arguments khi khởi chạy | `--date=2026-11-23 --dry-run` |
| **Application properties** | `--properties "app.<app>.key=value"` | Spring Environment của ứng dụng | `app.dailyclose.report.format=csv` |
| **Deployment properties** | `--properties "deployer.<app>.<platform>.<key>=value"` | Deployer/TaskLauncher | `deployer.dailyclose.kubernetes.limits.cpu=1000m` |

`<app>` là tên hoặc label ứng dụng trong định nghĩa task theo cú pháp của SCDF và phiên bản đang sử dụng. Với composed task có nhiều app, cần xác định đúng **label của node** thay vì áp dụng cùng một key cho tất cả.

**Quy tắc chọn nhanh:**

- Nếu dữ liệu thay đổi theo **ý định nghiệp vụ của lần chạy** (ngày, tenant, job ID, dry-run), ưu tiên **arguments**.
- Nếu đó là **thiết lập Spring của ứng dụng** (output format, batching strategy, log level không nhạy cảm), cân nhắc **`app.*`**.
- Nếu đó là **cách nền tảng tạo process/container** (CPU, RAM, image pull policy, working directory), dùng **`deployer.*`**.
- Nếu đó là **secret**, ưu tiên secret manager/secret reference và cấu hình platform hỗ trợ, thay vì chèn giá trị thô vào arguments hoặc properties.

Chọn đúng kênh còn giúp biết liệu thông số có thuộc **TaskRepository** hay được quản lý bởi **platform**: metadata task có thể ghi lại launch arguments, nhưng không nên giả định nó lưu đầy đủ tất cả thuộc tính deployer.

## 4. Quy trình chuẩn: đăng ký ứng dụng, tạo task definition và khởi chạy

Giả sử task application đã được đóng gói và đăng ký với tên `dailyclose` trong SCDF dưới loại `task`. Việc đăng ký có thể dùng Maven artifact, container image hoặc nguồn URI được nền tảng hỗ trợ; cú pháp và URI cụ thể phụ thuộc phiên bản/deployer.

Tại Spring Cloud Data Flow Shell, tạo task definition:

~~~text
dataflow:> task create --name daily-close --definition "dailyclose"
~~~

Khởi chạy không truyền thêm tham số:

~~~text
dataflow:> task launch daily-close
~~~

Khởi chạy kèm đối số nghiệp vụ:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A --dry-run"
~~~

Kết hợp đối số và thuộc tính ứng dụng:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A" --properties "app.dailyclose.report.format=csv"
~~~

Ví dụ tăng giới hạn tài nguyên Kubernetes khi launch:

~~~text
dataflow:> task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A" --properties "deployer.dailyclose.kubernetes.requests.cpu=500m,deployer.dailyclose.kubernetes.limits.cpu=1000m,deployer.dailyclose.kubernetes.requests.memory=640Mi,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

**Các lệnh này là cú pháp SCDF Shell**, không phải lệnh của Java, Spring Boot CLI hoặc `kubectl`. Khi chỉ chạy `java -jar`, không có lớp `app.dailyclose.*` hoặc `deployer.dailyclose.*` của SCDF: ứng dụng sẽ nhận trực tiếp args và các Spring property sources của chính nó.

### Vì sao cùng một tên xuất hiện ở nhiều nơi?

Trong ví dụ:

- `dailyclose` là **tên ứng dụng đã đăng ký** trong definition.
- `daily-close` là **tên task definition** mà người vận hành launch.
- `app.dailyclose.*` và `deployer.dailyclose.*` nhắm vào **ứng dụng `dailyclose`**.
- `spring.cloud.task.name` nếu có được framework dùng xác định tên TaskExecution; không được tự đồng nhất mọi tên hiển thị, đặc biệt trong composed task.

Nếu task definition có DSL nhiều node hoặc label khác, các key phải đổi theo node được target. Do đó nên kiểm tra **definition thực tế** trước khi kết luận “property không được áp dụng”.

## 5. Cách Spring Boot đọc arguments ở trong ứng dụng

Spring Boot cung cấp hai cách phổ biến:

- `CommandLineRunner.run(String... args)` nhận chuỗi tham số.
- `ApplicationRunner.run(ApplicationArguments args)` nhận dữ liệu được phân tích thành option và non-option.

Với đầu vào `--date=2026-11-23 --tenant=tenant-A --dry-run`, `ApplicationArguments` phù hợp để đọc một cách có cấu trúc:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DailyCloseRunnerConfiguration {

    @Bean
    ApplicationRunner dailyCloseRunner(DailyCloseService service) {
        return args -> {
            String tenant = required(args.getOptionValues("tenant"), "tenant");
            LocalDate date = LocalDate.parse(
                required(args.getOptionValues("date"), "date"));
            boolean dryRun = args.containsOption("dry-run");

            // Phải chờ service hoàn tất, không fire-and-forget.
            service.closeDay(tenant, date, dryRun);
        };
    }

    private static String required(List<String> values, String name) {
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Missing --" + name + "=...");
        }
        return values.get(0);
    }
}
~~~

`DailyCloseService` là thành phần nghiệp vụ do dự án xây dựng. Đoạn code minh họa điểm vào và cách validate, **chưa phải một ứng dụng có đầy đủ schema/repository**.

### Tình huống dễ sai

`ApplicationArguments.containsOption("dry-run")` kiểm tra **sự hiện diện** của option, không phải tự parse chuỗi boolean. `--dry-run=false` vẫn làm `containsOption("dry-run")` trả `true`. Nếu muốn hỗ trợ bật/tắt bằng giá trị, hãy đọc `getOptionValues("dry-run")` và validate rõ quy tắc.

`getOptionValues("date")` có thể trả `null`, danh sách rỗng hoặc nhiều giá trị nếu người dùng truyền lặp; đừng mặc định luôn có phần tử thứ nhất.

Các giá trị `date` và `tenant` cần được kiểm tra quyền truy cập, khoảng thời gian và idempotency. **SCDF chỉ chuyển tham số**, không tự xác thực ý nghĩa nghiệp vụ.

## 6. App properties đi vào Spring Environment, không đồng nghĩa ApplicationArguments

Thuộc tính `app.dailyclose.report.format=csv` yêu cầu SCDF/TaskLauncher cung cấp property `report.format=csv` cho ứng dụng. Spring Boot có thể đọc qua `Environment` hoặc `@ConfigurationProperties`, ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
class ReportFormatter {

    private final String format;

    ReportFormatter(
            @Value("${report.format:json}") String format) {
        this.format = format;
    }

    public String format() {
        return format;
    }
}
~~~

`${report.format:json}` trong ví dụ là cú pháp property placeholder của Spring, với mặc định là `json`. Khi cấu hình `app.dailyclose.report.format=csv` được chuyển đúng vào Spring Environment, `format()` có thể trả `csv`.

**Đừng mặc định `ApplicationArguments.getOptionValues("report.format")` trả dữ liệu từ `app.*`.** App properties có thể đến từ environment hoặc hình thức platform quyết định; chúng không nhất thiết xuất hiện trong danh sách CLI arguments của JVM.

Tương tự, `deployer.dailyclose.kubernetes.limits.memory=1024Mi` là **deployment property**, không phải giá trị `limits.memory` mà `@Value` của ứng dụng phải đọc. Nếu cần biết giới hạn thực tế của container, dùng thông tin platform/cgroups và quy trình quan sát tương ứng thay vì coi deployer property như business config.

## 7. Precedence: property nào thắng khi được khai báo nhiều nơi?

Một task có thể nhận cấu hình từ:

1. `application.yml` đóng gói trong artifact.
2. Environment variables hoặc config server.
3. Common task application properties cấu hình ở SCDF server.
4. Properties trong task definition.
5. App properties chỉ định tại lúc launch.
6. Command-line arguments của ứng dụng, nếu được chuyển thành Spring Boot options.

**Không có một bảng precedence duy nhất bất biến giữa mọi hình thức deploy.** Bên trong Spring Boot, thứ tự property sources quyết định giá trị hiệu lực; SCDF và TaskLauncher có thể chọn cách chuyển app properties thành CLI arguments hoặc environment. Ví dụ, một deployer có thể xử lý giá trị khác với deployer còn lại.

Tài liệu SCDF nêu rõ **application properties tại launch có thể ghi đè common task application properties** và trong composed task, properties chỉ định khi launch được ưu tiên hơn cấu hình tương ứng ở definition.

Ví dụ common properties tại SCDF server:

~~~properties
spring.cloud.dataflow.applicationProperties.task.report.format=json
~~~

Khi launch:

~~~text
dataflow:> task launch daily-close --properties "app.dailyclose.report.format=csv"
~~~

Kết quả mong muốn là task nhận `report.format=csv` theo chính sách override của SCDF, miễn property được chuyển đúng. Nhưng nếu còn **option CLI `--report.format=xml`**, Spring Boot có thể áp precedence của command-line property source cao hơn, tùy cách launcher truyền các thông số.

**Khuyến nghị:** không thiết kế workflow dựa vào nhiều nguồn cùng ghi một property quan trọng. Đặt một nguồn chân lý rõ ràng, bật logging an toàn để quan sát property hiệu lực (không log secret), và kiểm tra thực tế trên platform sẽ triển khai.

## 8. Deployment properties theo platform: Local khác Kubernetes

`deployer.<app>.<platform>.<key>=value` được SCDF chuyển cho TaskLauncher/Deployer. Ý nghĩa property tùy implementation.

### 8.1. Kubernetes task platform

Những key thường gặp của Kubernetes deployer:

| Property | Ý nghĩa |
|---|---|
| `deployer.dailyclose.kubernetes.requests.cpu` | CPU request |
| `deployer.dailyclose.kubernetes.limits.cpu` | CPU limit |
| `deployer.dailyclose.kubernetes.requests.memory` | Memory request |
| `deployer.dailyclose.kubernetes.limits.memory` | Memory limit |
| `deployer.dailyclose.kubernetes.ttlSecondsAfterFinished` | Thời gian dọn Job/Pod sau khi kết thúc, tùy version/platform |
| `deployer.dailyclose.kubernetes.environmentVariables` | Biến môi trường được cung cấp bởi deployer theo cú pháp hỗ trợ |

Ví dụ đặt CPU và RAM:

~~~text
dataflow:> task launch daily-close --properties "deployer.dailyclose.kubernetes.requests.cpu=500m,deployer.dailyclose.kubernetes.limits.cpu=1000m,deployer.dailyclose.kubernetes.requests.memory=640Mi,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

CPU `1000m` tương đương một CPU theo cách định nghĩa resource quantity của Kubernetes; memory `1024Mi` là một GiB theo đơn vị mebibyte. **Container memory limit không tự động đặt `-Xmx` của JVM**. Cần kiểm tra Java container awareness, `JAVA_TOOL_OPTIONS`, heap/GC/native memory và khả năng bị OOMKill.

Nếu thuộc tính target app label không đúng hoặc deployer không hỗ trợ key, request có thể bị từ chối hoặc không được áp dụng như dự kiến. Đối chiếu YAML của Job/Pod được tạo (qua công cụ vận hành có quyền) thay vì chỉ nhìn câu lệnh SCDF.

### 8.2. Local task platform

Local deployer tạo một tiến trình trên host có Data Flow task platform phù hợp; ví dụ những property theo tài liệu:

~~~text
deployer.dailyclose.local.javaOpts=-Xmx1024m
deployer.dailyclose.local.workingDirectoriesRoot=/var/tmp/scdf-tasks
~~~

Không áp dụng key Kubernetes cho Local rồi kỳ vọng có CPU request/limit như Pod. Với Local platform, memory và CPU isolation phụ thuộc hệ điều hành và cách launcher triển khai, không tương đương isolation của Kubernetes.

### 8.3. Thuộc tính không liên quan nghiệp vụ

Dù dùng `deployer.*` để tăng memory, giảm CPU hoặc đổi image, **ngày xử lý và business key không nên thay đổi**. Khi retry cùng nghiệp vụ với mức RAM lớn hơn, đây vẫn là **một ý định nghiệp vụ cũ**, dù TaskExecution mới có resource configuration khác.

## 9. Định nghĩa application version và khả năng tái lập kết quả

Một task definition có thể trỏ tới một app version mặc định. SCDF hỗ trợ cách chỉ định version của ứng dụng trong launch properties ở những dòng tài liệu phù hợp, ví dụ:

~~~text
dataflow:> task launch daily-close --properties "version.dailyclose=3.0.0"
~~~

Để kết quả có thể tái lập, khi triển khai sản xuất nên ghi nhận:

- Artifact/container image **version hoặc digest** đã thực thi.
- Các nghiệp vụ/JobParameters xác định cùng ý định, đặc biệt `tenant`, `businessDate`, `revision`.
- Application config version (khi logic xử lý phụ thuộc config).
- TaskExecution ID và thông tin platform execution để truy vết.
- Database/schema version tương thích với ứng dụng.

Thay app version khi chạy lại một tác vụ cũ có thể khiến thuật toán tính toán thay đổi. Nếu yêu cầu **reprocess có chủ đích** cần revision mới hoặc chính sách điều chỉnh đầu ra. Nếu chỉ là retry do lỗi hạ tầng, ưu tiên dùng input/snapshot có danh tính ổn định.

Cấu hình `version.<app>` và cơ chế resolve version có thể khác nhau theo SCDF release; kiểm tra app registry và task launch thực tế.

## 10. Spring Cloud Task lưu gì trong TaskRepository?

Sau khi một ứng dụng Spring Cloud Task khởi động với DataSource/schema phù hợp, nó có thể lưu metadata của lần thực thi:

| Thông tin | Mục đích |
|---|---|
| `TaskExecutionId` | Định danh một lần chạy |
| Task name | Tên task được resolver xác định |
| Start/end time | Theo dõi vòng đời |
| Exit code/exit message | Quan sát kết quả kỹ thuật |
| Arguments | Đầu vào CLI mà framework ghi nhận |
| External execution ID | Liên kết tới nền tảng điều phối nếu được cung cấp |

**TaskRepository không đồng nghĩa deployment configuration store.** Không mặc định mọi `deployer.*` hoặc toàn bộ biến môi trường của Pod xuất hiện trong TaskExecution. Kết quả nghiệp vụ cũng không tự được lưu ở đây.

Với SCDF Shell, có thể tra cứu:

~~~text
dataflow:> task execution list
dataflow:> task execution list --name daily-close
dataflow:> task execution status --id 549
~~~

`549` là ID ví dụ, phải thay bằng ID thật trong hệ thống. Nếu task chưa tạo bản ghi TaskExecution vì lỗi khởi động quá sớm, không được kết luận “chưa từng launch” chỉ từ việc thiếu row trong repository: cần kiểm tra Data Flow launch record, TaskLauncher result và platform logs.

SCDF có thể quản lý tập metadata riêng để biết task definition và launch; ứng dụng Spring Cloud Task thực thi bên trong JVM là nơi cung cấp dữ liệu lifecycle theo khả năng của nó.

## 11. Khác biệt khi task có Spring Batch JobParameters

Nếu ứng dụng `dailyclose` dùng Spring Batch, phải phân biệt:

- **SCDF launch arguments:** những chuỗi gửi cho ứng dụng.
- **Spring Boot application properties:** cấu hình Spring Environment.
- **Spring Batch JobParameters:** các tham số được chuyển vào JobLauncher/JobOperator để xác định JobInstance, có cờ **identifying**.

Một `ApplicationRunner` tùy chỉnh có thể đọc arguments rồi tạo JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", tenant, true)
    .addString("businessDate", businessDate.toString(), true)
    .addLong("revision", 1L, true)
    .addString("traceId", traceId, false)
    .toJobParameters();
~~~

Ví dụ minh họa Spring Batch 5, với các biến `tenant`, `businessDate` và `traceId` đã được validate. Nếu dùng auto-launch của Spring Boot/SCDF, cú pháp convert CLI argument thành JobParameters **có thể khác** so với custom runner; không tự suy rằng chuỗi `--date=...` sẽ thành JobParameter identifying.

**Restart đúng JobInstance:** giữ cùng tên Job và bộ identifying parameters. Không thêm timestamp hoặc `run.id` mới dưới dạng identifying chỉ vì một lần launch mới được tạo. TaskExecution ID mới không có nghĩa JobInstance mới.

Các thuộc tính deployer như CPU/RAM và phần lớn app properties về logging/format không nên được nhầm thành JobParameters. Nếu property **thực sự làm thay đổi dữ liệu nghiệp vụ** (ví dụ source snapshot hoặc algorithm revision), cần có chính sách đưa nó vào định danh, snapshot/fingerprint hay revision thích hợp.

## 12. Khởi chạy qua API, lịch và composed task

SCDF cung cấp REST API và UI để launch, bên cạnh Shell. Khi dùng API:

- Request launch thường có task definition name, danh sách arguments và map properties theo schema của phiên bản API.
- TaskLauncher chuyển properties cho platform và arguments cho ứng dụng theo hợp đồng triển khai.
- Bảo mật và quyền gọi API quyết định ai có thể launch task với dữ liệu nào.

Vì endpoint/body có thể đổi giữa các release, nên xem OpenAPI/REST reference của Data Flow version đang dùng thay vì copy một JSON request không khớp.

### Khi chạy theo lịch

Với schedule, định nghĩa task và những properties dành cho schedule được lưu/quản lý theo chức năng scheduling. Cần kiểm tra:

- Tham số ngày được lấy từ đâu: cố định tại schedule, tính tại startup, hay truyền động qua một scheduler ngoài.
- Múi giờ và quy tắc xử lý ngày nghiệp vụ: tránh dùng timezone mặc định không kiểm soát.
- Tài nguyên/kênh secret được áp dụng cho lần launch thực tế hay chỉ cấu hình schedule.
- Retry/backoff của platform và cơ chế chống chạy trùng lịch.

Một task chạy mỗi ngày nhưng luôn được launch với `--date=2026-11-23` sẽ **luôn xử lý cùng ngày**; Data Flow không tự thay đổi option ngày nghiệp vụ chỉ vì đến ngày mới.

### Khi composed task có nhiều node

Một composed task có thể gồm `task-a && task-b` hoặc các nhánh. Khi truyền properties phải xác định **label node** trong graph. Ví dụ trong tài liệu composed task, dạng `deployer.task-a.kubernetes.limits.cpu=1000m` nhắm vào node `task-a`.

Tham số của composed task runner không tự trở thành tham số của mọi child task. Cần dùng cú pháp truyền chung/riêng được phiên bản Composed Task Runner hỗ trợ (ví dụ cơ chế `composedTaskArguments` khi phù hợp), và kiểm chứng trực tiếp ở child execution.

Không dùng ví dụ `app.dailyclose.*` cho composed task có label khác mà không điều chỉnh.

## 13. An toàn thông tin khi truyền arguments và properties

**Không truyền password, token, private key hoặc chuỗi kết nối có credential thô trong `--arguments`** nếu tránh được. Những giá trị này có thể xuất hiện trong:

- Process list và JVM command line.
- TaskExecution arguments trong TaskRepository.
- Data Flow launch history, request logs, audit logs.
- Kubernetes Job/Pod spec và `kubectl describe` tùy entrypoint style.
- Shell history hoặc script CI/CD.

Tương tự, `app.*` không mặc định là kho secret an toàn. Tài liệu SCDF có lưu ý rằng cách cấu hình `entryPointStyle` có thể khiến app properties biến thành command-line arguments. Một số cấu hình khuyến nghị `shell` hoặc `boot` thay `exec` để giảm rủi ro lộ qua args; song **điều đó không tự bảo đảm bí mật không hiển thị trong Pod spec hoặc output công cụ vận hành**.

Với Kubernetes, ưu tiên:

1. Kubernetes Secrets/secretKeyRef hoặc nền tảng quản lý secret được tổ chức chấp thuận.
2. Role/service account và RBAC giới hạn người có thể đọc Pod/Secret.
3. Phân tách quyền của Data Flow server và task launcher.
4. Không log toàn bộ `ApplicationArguments` hoặc dump Spring Environment khi có secret.
5. Nếu SCDF cung cấp cơ chế dùng Kubernetes Secrets cho database credentials, bật và kiểm thử theo đúng phiên bản server.
6. Rotation secret và kiểm tra worker dùng đúng giá trị mới mà không cần đưa password vào launch command.

Ví dụ application có thể nhận DB username/password từ environment:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://db.internal:5432/taskdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: dailyclose
~~~

`${DB_USER}` và `${DB_PASSWORD}` trong ví dụ sẽ được viết thành Spring placeholders khi lưu, và phải được cung cấp bởi cơ chế bí mật/environment thực tế.

## 14. Một lần launch thành công khác với nghiệp vụ thành công

Data Flow có thể trả thông tin “task launched” khi TaskLauncher chấp nhận tạo tiến trình hoặc Pod. Điều này **không chứng minh** task đã xử lý dữ liệu thành công.

~~~mermaid
sequenceDiagram
    participant O as Operator / Scheduler
    participant D as Spring Cloud Data Flow
    participant L as TaskLauncher
    participant J as JVM / Pod
    participant R as TaskRepository
    participant B as Business DB

    O->>D: task launch + arguments + properties
    D->>L: Launch request
    L->>J: Tạo process/container
    L-->>D: External launch info
    D-->>O: Launch accepted
    J->>R: TaskExecution bắt đầu
    J->>B: Xử lý nghiệp vụ
    alt Thành công
        B-->>J: Commit kết quả
        J->>R: Ghi kết thúc, exit code phù hợp
    else Thất bại / crash
        B-->>J: Exception hoặc mất kết nối
        J->>R: Có thể ghi lỗi nếu JVM còn hoạt động
    end
    O->>D: Tra cứu execution status
~~~

Nếu ứng dụng có `ApplicationRunner` hoặc `CommandLineRunner`, runner nên **chỉ hoàn tất sau khi công việc bắt buộc thực sự hoàn thành**, thay vì gửi việc `@Async` rồi trả về. Khi runner ném exception, cần cho lỗi ảnh hưởng tới mã thoát thay vì chỉ log rồi tiếp tục.

Khi JVM bị `SIGKILL` hoặc node mất điện, TaskRepository có thể có bản ghi chưa chốt. Đối chiếu Data Flow launch, Pod/Job status, TaskExecution và kết quả nghiệp vụ trước khi retry.

## 15. Idempotency khi cùng tham số được launch nhiều lần

Giả sử người vận hành launch hai lần:

~~~text
task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A"
task launch daily-close --arguments "--date=2026-11-23 --tenant=tenant-A"
~~~

Hai lần launch có thể sinh **hai TaskExecution** khác nhau. SCDF/TaskRepository không tự bảo đảm chỉ một lần ghi doanh thu cho cùng tenant/ngày.

Một khóa nghiệp vụ phù hợp:

~~~text
(tenantId, operation, businessDate, revision)
= (tenant-A, CLOSE_DAY, 2026-11-23, 1)
~~~

Kho kết quả nên có unique key/idempotency rule tương ứng:

~~~sql
CREATE TABLE daily_close_result (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    revision       INTEGER NOT NULL,
    total_amount   NUMERIC(19, 2) NOT NULL,
    PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

Khi retry, service kiểm tra key và quyết định trả kết quả cũ, tiếp tục checkpoint hoặc báo conflict nếu nguồn thay đổi. **Không dùng TaskExecutionId làm khóa nghiệp vụ**, vì nó đổi mỗi lần khởi chạy.

Thay property `deployer.dailyclose.kubernetes.limits.memory` chỉ làm thay đổi tài nguyên, không khiến cùng business date trở thành nghiệp vụ mới.

## 16. Chẩn đoán lỗi truyền tham số và thuộc tính triển khai

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Task khởi chạy nhưng không thấy `--date` | Cú pháp `--arguments` sai, bị shell cắt, definition khác | Kiểm tra launch request và cách `ApplicationRunner` đọc args |
| `@Value` vẫn lấy giá trị mặc định | Sai prefix `app.*`, sai label hoặc không được launcher chuyển vào Environment | Kiểm tra definition, effective config an toàn |
| `ApplicationArguments` không có app property | App property không nhất thiết là CLI argument | Đọc qua `Environment`/`@ConfigurationProperties` |
| Kubernetes Pod không tăng RAM | Dùng nhầm key `app.*` thay vì `deployer.*`, sai platform hoặc tên app | Kiểm tra deployer property và Pod spec |
| Local platform không nhận Kubernetes property | Deployer không hỗ trợ property của nền tảng khác | Dùng đúng namespace `deployer.<app>.local.*` |
| JVM bị OOM dù memory limit lớn | Java heap/native memory không phù hợp, memory leak | Kiểm tra JVM flags, container usage, GC, logs |
| Task launched nhưng không có TaskExecution | JVM chết sớm, DB/schema/task config lỗi | Đối chiếu platform logs và TaskRepository |
| Task exit 0 nhưng kết quả thiếu | Runner trả về trước async worker hoặc nuốt exception | Chờ future và để lỗi lan lên |
| Hai lần launch ghi trùng | Không có business key/idempotency | Unique constraint, transaction, checkpoint |
| Một schedule luôn xử lý cùng ngày | Tham số `--date` hardcode | Thiết kế cách tính business date có kiểm soát |
| Secret xuất hiện trong task execution args | Truyền secret qua CLI hoặc app property thành CLI | Chuyển sang secret manager/environment |
| Chạy sai phiên bản app | Registry/default version khác kỳ vọng | Chỉ định/kiểm tra app version và image digest |
| Batch JobInstance mới trên mỗi retry | Timestamp/`run.id` identifying thay đổi | Giữ identifying JobParameters ổn định |

### Quy trình kiểm tra gọn

1. Đọc **task definition** và app label thực tế trong SCDF.
2. Xác định nguồn giá trị: `--arguments`, `app.*`, `deployer.*` hay `application.yml`.
3. Kiểm tra launch request và external execution ID, không in secret.
4. Kiểm tra Pod/process đã được tạo với CPU/RAM và environment theo kỳ vọng.
5. Đọc TaskExecution và log ứng dụng; với Spring Batch, đọc thêm JobExecution.
6. Đối chiếu kết quả nghiệp vụ và idempotency key trước khi retry.

## 17. Bài thực hành từng bước

Mục tiêu: launch `dailyclose` cho hai ngày khác nhau, dùng app property chọn format và deployer property điều chỉnh RAM.

1. **Chuẩn bị ứng dụng:** Spring Boot/Spring Cloud Task tương thích, `ApplicationRunner` parse `--tenant`/`--date`/`--dry-run`, DataSource và schema TaskRepository bền vững.
2. **Đăng ký ứng dụng `dailyclose`** trên SCDF phù hợp với nền tảng Local/Kubernetes; tạo task definition `daily-close`.
3. **Chạy lần đầu:**

~~~text
dataflow:> task launch daily-close --arguments "--tenant=tenant-A --date=2026-11-23 --dry-run"
~~~

4. **Chạy lần hai** có định dạng báo cáo và memory limit dành cho Kubernetes:

~~~text
dataflow:> task launch daily-close --arguments "--tenant=tenant-A --date=2026-11-24" --properties "app.dailyclose.report.format=csv,deployer.dailyclose.kubernetes.limits.memory=1024Mi"
~~~

5. **Kiểm tra Spring config:** `report.format` được ứng dụng đọc qua Spring Environment, không suy ra từ `getOptionValues("report.format")`.
6. **Kiểm tra deployer:** Pod có memory limit phù hợp; trên Local platform dùng một thuộc tính Local tương ứng thay vì key Kubernetes.
7. **Tra TaskExecution:** `task execution list --name daily-close` và `task execution status --id <ID>` với ID thực.
8. **Thử đầu vào lỗi:** không truyền ngày hoặc dùng `--date=invalid`; xác minh runner báo lỗi và trạng thái task phản ánh thất bại.
9. **Thử retry cùng ngày:** xác nhận TaskExecution mới nhưng kết quả nghiệp vụ không bị ghi trùng.
10. **Kiểm tra bảo mật:** args và logs không chứa password, token, JDBC credential thô.
11. **Nếu có Batch Job:** giữ identifying JobParameters ổn định giữa các lần retry của cùng kỳ.

| Đối tượng kiểm tra | Kỳ vọng |
|---|---|
| Launch arguments | `tenant`, `date`, `dry-run` tới được runner |
| App property | `report.format` được resolve đúng trong Spring Environment |
| Deployer property | Pod resource được áp dụng trên đúng platform |
| TaskExecution | Lưu lần chạy và kết quả theo khả năng framework |
| Batch JobParameters | Identifying key nhất quán nếu sử dụng Batch |
| Business output | Không nhân đôi kết quả khi launch lặp |
| Security | Không lộ bí mật trong CLI/TaskRepository/log |

## 18. Checklist production và kết luận

- **Tách ba kênh:** arguments cho đầu vào lần chạy; `app.*` cho Spring configuration; `deployer.*` cho nền tảng triển khai.
- **Khóa phiên bản:** app artifact/image, Data Flow, Spring Boot/Spring Cloud Task và deployer phải tương thích.
- **Đúng app label:** đặc biệt trong composed task và khi định nghĩa task name khác application name.
- **Không để nguồn cấu hình mâu thuẫn:** kiểm tra precedence thực tế theo cách launcher chuyển properties.
- **Có nguồn secret an toàn:** không truyền mật khẩu trong arguments, properties thô hoặc JobParameters.
- **Quan sát hai tầng:** “launch accepted” chưa phải “task completed”; theo dõi TaskExecution và Pod/process.
- **Chờ công việc hoàn tất:** runner không kết thúc trước khi nghiệp vụ đã commit và các future bắt buộc hoàn thành.
- **Có retry policy và idempotency:** cùng business key được xử lý an toàn qua nhiều TaskExecution.
- **Xử lý lỗi đặc thù platform:** timeout, quota, resource limits và launch failure.
- **Vận hành theo lịch có timezone rõ ràng:** không nhầm ngày chạy với business date.

**Kết luận:** Khi dùng Spring Cloud Data Flow để khởi chạy ứng dụng Spring Cloud Task hữu hạn, hãy phân biệt **`--arguments`** (đầu vào lần chạy), **`app.<app>.*`** (cấu hình ứng dụng) và **`deployer.<app>.*`** (cấu hình nền tảng). Sự phân chia này giúp người vận hành thay ngày xử lý, định dạng đầu ra hoặc CPU/RAM mà không sửa mã nguồn, đồng thời kiểm soát bảo mật, khả năng truy vết TaskExecution và an toàn khi chạy lại.

### Tài liệu tham khảo

- [Spring Cloud Data Flow Reference — Launching a Task](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_launching_a_task)
- [Spring Cloud Data Flow Reference — Kubernetes Deployer Properties](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/#_deployer_properties_2)
- [Spring Cloud Data Flow — Composed Task: Passing Properties](https://dataflow.spring.io/docs/feature-guides/batch/composed-task/)
- [Spring Cloud Task Reference](https://docs.spring.io/spring-cloud-task/reference/)
