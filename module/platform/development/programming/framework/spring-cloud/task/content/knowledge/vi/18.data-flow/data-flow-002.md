# Đăng ký ứng dụng Task và tạo định nghĩa tác vụ

Một ứng dụng **Spring Cloud Task** được thiết kế để thực hiện công việc có thời gian chạy hữu hạn: bắt đầu tiến trình Spring Boot, xử lý dữ liệu, ghi trạng thái vào **TaskRepository**, rồi kết thúc. Ví dụ, một ứng dụng nhập đơn hàng nhận mã nguồn dữ liệu và ngày nghiệp vụ, đọc tệp CSV, cập nhật cơ sở dữ liệu và thoát với mã kết thúc phù hợp. Khi muốn vận hành ứng dụng này bằng giao diện, API hoặc lịch, **Spring Cloud Data Flow (SCDF)** cung cấp lớp quản lý để **đăng ký ứng dụng**, **tạo định nghĩa tác vụ** và **khởi chạy từng lượt**.

Bài học thuộc chương **Data Flow**, tập trung trực tiếp vào hai thao tác đầu: **đăng ký Task application trong App Registry** và **tạo Task Definition từ ứng dụng đã đăng ký**. Để hiểu vì sao hai thao tác này cần thiết, bài sẽ nối tiếp đến launch, lịch sử TaskExecution, truyền tham số và kiểm tra lỗi. Các ví dụ dùng Spring Cloud Data Flow Shell và Dashboard, đồng thời chỉ rõ nơi lưu metadata của Data Flow so với metadata do Spring Cloud Task ghi.

> **Lưu ý hệ sinh thái và phiên bản:** Các ví dụ dòng lệnh dựa trên tài liệu Spring Cloud Data Flow **2.11.x**. Từ thông báo chính thức ngày **21/04/2025**, Spring xác định **2.11.x là dòng mã nguồn mở cuối của Spring Cloud Data Flow**; các bản tiếp theo chỉ cung cấp theo hình thức thương mại cho khách hàng đủ điều kiện. Vì vậy, khi triển khai mới phải kiểm tra phiên bản Data Flow, Shell, Spring Boot, Spring Cloud Task, nền tảng Kubernetes/Cloud Foundry và quyền sử dụng thực tế. Cú pháp, UI, schema và tính năng có thể khác giữa các bản.

## 1. Ba khái niệm dễ bị nhầm

Trước tiên cần tách **Task application**, **Task Definition** và **Task Execution**:

| Thành phần | Ý nghĩa | Ví dụ | Được tạo khi nào? |
| --- | --- | --- | --- |
| **Task application** | Artifact có khả năng chạy một tác vụ hữu hạn, ví dụ JAR hoặc container image | `invoice-report-task:1.0.0` | Lúc build/publish ứng dụng |
| **App Registration** | Bản ghi trong **SCDF App Registry** ánh xạ tên logic và loại `task` tới URI artifact | `invoice-report → docker:registry.example.com/batch/invoice-report-task:1.0.0` | Khi chạy `app register` |
| **Task Definition** | Định nghĩa có tên, tham chiếu ứng dụng Task đã đăng ký và có thể chứa cấu hình DSL | `daily-invoice-report → invoice-report` | Khi chạy `task create` |
| **Task Launch** | Yêu cầu Data Flow khởi động một lượt của Task Definition với các đối số/thuộc tính | Chạy kỳ báo cáo `2026-11-23` | Khi chạy `task launch` hoặc chọn Launch trong UI |
| **Task Execution** | Một lần chạy thực tế được nhận diện bởi execution ID, có thời gian, mã thoát, tham số | `TaskExecution ID=4101` | Khi tiến trình Task được thực thi và metadata được ghi |
| **Batch JobExecution** | Lần thực thi Spring Batch Job bên trong Task, nếu có | `JobExecution ID=905` | Khi ứng dụng khởi chạy Batch Job |

**Đăng ký ứng dụng không đồng nghĩa ứng dụng đã chạy.** **Tạo định nghĩa tác vụ cũng chưa sinh kết quả xử lý.** Một định nghĩa có thể được launch nhiều lần với những tham số khác nhau; mỗi lượt tạo lịch sử thực thi riêng, nếu tiến trình khởi động đủ để Spring Cloud Task ghi metadata.

### Sơ đồ toàn bộ vòng đời

~~~mermaid
flowchart TD
    A["Build và publish JAR / container image"] --> B["SCDF: app register --type task"]
    B --> C[("App Registry<br/>tên + loại + artifact URI")]
    C --> D["SCDF: task create"]
    D --> E[("Task Definition Repository<br/>tên + DSL")]
    E --> F["SCDF: task launch / Schedule"]
    F --> G["TaskLauncher / Platform Deployer"]
    G --> H["Spring Boot + Spring Cloud Task process"]
    H --> I["Runner / Spring Batch Job / nghiệp vụ"]
    H --> J[("TaskRepository<br/>TaskExecution")]
    I --> K[("CSDL hoặc object storage nghiệp vụ")]
    I --> L["Exit code, log, kết quả"]
    J --> M["SCDF Task Executions / Dashboard"]
~~~

Có thể hiểu SCDF là **mặt điều khiển** để quản lý artifact, định nghĩa và lệnh chạy; Spring Cloud Task nằm trong **tiến trình thực thi** để ghi nhận vòng đời. Hai lớp liên kết nhưng không thay thế vai trò của nhau.

## 2. Điều kiện trước khi đăng ký

SCDF cần truy cập được một **ứng dụng Task đã build và publish**, cùng một nền tảng để khởi chạy ứng dụng. Với một môi trường cụ thể, cần chuẩn bị:

1. **Data Flow Server** đã cấu hình, có App Registry/Task APIs, cơ sở dữ liệu metadata và quyền truy cập của người vận hành.
2. **Data Flow Shell** kết nối đúng server, hoặc dùng Dashboard/REST API. Shell có thể cần cấu hình URL và thông tin đăng nhập theo cách triển khai.
3. **Task platform** hoạt động (ví dụ Kubernetes, Cloud Foundry hoặc nền tảng được phiên bản SCDF hỗ trợ) và tài khoản có quyền tạo workload.
4. **Artifact có thể phân giải** từ nơi thực thi: Maven repository có quyền truy cập, HTTP(S) hoặc Docker registry phù hợp. URI chỉ có ý nghĩa khi SCDF/deployer có thể lấy artifact.
5. **Ứng dụng Spring Boot phù hợp Spring Cloud Task**, với dependency/phiên bản tương thích, DataSource và schema TaskRepository khi muốn lưu lịch sử bền vững.
6. **Bí mật kết nối và quyền truy cập tài nguyên nghiệp vụ** được cấp qua secret manager/cấu hình nền tảng. Không đặt mật khẩu vào Task Definition DSL hoặc launch arguments.

Ví dụ một ứng dụng Java tối giản dùng `ApplicationRunner`:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class InvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvoiceReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner generateReport(InvoiceReportService service) {
        return args -> {
            List<String> dates = args.getOptionValues("business-date");
            if (dates == null || dates.size() != 1
                    || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Expected --business-date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            service.generate(date); // Hoàn tất đồng bộ trước khi trả về.
        };
    }
}

interface InvoiceReportService {
    void generate(LocalDate businessDate);
}
~~~

Đây là **khung minh họa**: cần bean triển khai `InvoiceReportService`, dependency Spring Cloud Task, JDBC driver và cấu hình DataSource thực tế. Nó thể hiện hai điểm quan trọng: tác vụ **kết thúc sau khi công việc hoàn thành** và **tham số phải được xác thực**. Nếu `generate` thất bại, ứng dụng cần phản ánh lỗi/mã thoát để bộ điều phối và TaskRepository có kết quả đúng.

Ví dụ `application.yml` của một ứng dụng Task dùng CSDL do môi trường cấp:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
~~~

Ví dụ giả định **schema TaskRepository đã được tạo bằng migration tương thích** trước khi chạy; bật `initialize-enabled: false` không tự tạo bảng. Đặc biệt khi ứng dụng được SCDF launch, phải xác nhận DataSource được cấp cho Task thực sự trỏ tới kho metadata mà SCDF có thể đọc.

## 3. Bước A: đăng ký Task application trong SCDF

Đăng ký có nghĩa là **đặt một tên logic cho artifact và cho SCDF biết loại ứng dụng là `task`**. Lệnh cơ bản trong Data Flow Shell:

~~~text
dataflow:> app register --name invoice-report --type task --uri maven://com.example.batch:invoice-report-task:1.0.0
~~~

Trong ví dụ:

- `invoice-report` là **tên đăng ký** để tham chiếu trong DSL của Task Definition.
- `task` là **loại ứng dụng**; không dùng `source`, `processor` hoặc `sink` vốn dành cho ứng dụng Stream.
- `maven://com.example.batch:invoice-report-task:1.0.0` là URI tới artifact. Artifact phải tồn tại trong repository có thể phân giải từ môi trường SCDF.

### 3.1. Các loại URI thường gặp

| Cách đóng gói | Ví dụ URI | Khi phù hợp |
| --- | --- | --- |
| **Maven** | `maven://com.example.batch:invoice-report-task:1.0.0` | Máy chủ/deployer có quyền resolve Maven artifact |
| **Docker/OCI image** | `docker:registry.example.com/batch/invoice-report-task:1.0.0` | Triển khai container trên nền tảng hỗ trợ, như Kubernetes |
| **File** | `file:///opt/task-artifacts/invoice-report-task-1.0.0.jar` | Nền tảng xử lý được đường dẫn file từ nơi resolve artifact |
| **HTTPS** | `https://artifacts.example.com/tasks/invoice-report-task-1.0.0.jar` | Artifact được phục vụ qua HTTPS có quyền truy cập thích hợp |

Không phải **mọi URI đều dùng được trên mọi Task platform**. Với `file:`, vị trí tệp phải khả dụng cho thành phần thực sự phân giải; tệp tồn tại trên laptop không có nghĩa Pod có thể đọc nó. Với Docker, registry credentials, quyền pull image, architecture và entrypoint phải phù hợp nền tảng.

**Ví dụ đăng ký image cho Kubernetes:**

~~~text
dataflow:> app register --name invoice-report --type task --uri docker:registry.example.com/batch/invoice-report-task:1.0.0
~~~

Đăng ký artifact là thao tác **khai báo metadata**, không tự chứng minh image đã được tải thành công và cũng không chạy container. Cần kiểm tra khả năng resolve/pull bằng validation và một lượt launch trên môi trường thử nghiệm.

### 3.2. Cú pháp URI Maven và phiên bản

Cú pháp Maven URI được SCDF mô tả là:

~~~text
maven://<groupId>:<artifactId>[:<extension>[:<classifier>]]:<version>
~~~

Chẳng hạn:

~~~text
maven://com.example.batch:invoice-report-task:1.0.0
maven://com.example.batch:invoice-report-task:jar:1.0.0
~~~

Trong hệ thống cần tái hiện kết quả, dùng **phiên bản artifact xác định**, không sử dụng tag trôi như `latest` cho những tác vụ quan trọng. Nếu cùng tên ứng dụng được đăng ký lại hoặc đổi URI, hãy kiểm tra chính sách version/registration của SCDF đang chạy và tác động đến những định nghĩa đã tạo.

**App registration name không phải business key.** Một ứng dụng `invoice-report` có thể chạy cho nhiều ngày hoặc tenant; tên đăng ký xác định **loại artifact**, không xác định **lần phát hành báo cáo**.

### 3.3. Đăng ký qua Dashboard

Với Dashboard của SCDF, luồng thao tác thường là:

1. Mở mục **Applications/Apps**, chọn chức năng thêm hoặc đăng ký ứng dụng.
2. Chọn **Register one or more applications**, loại **Task**.
3. Nhập tên `invoice-report` và URI Maven/Docker của bản artifact đã publish.
4. Lưu/import đăng ký và kiểm tra nó xuất hiện trong App Registry.

Tên nút có thể thay đổi giữa phiên bản UI. Điểm cần xác minh sau thao tác là **tên**, **loại task** và **URI/version** khớp artifact muốn dùng; không nên chỉ dựa vào màu trạng thái trên giao diện.

## 4. Bước B: tạo Task Definition từ ứng dụng đã đăng ký

Sau khi đăng ký `invoice-report`, tạo **một định nghĩa tác vụ có tên riêng**:

~~~text
dataflow:> task create daily-invoice-report --definition "invoice-report"
~~~

Lệnh trên có hai phần với vai trò khác nhau:

| Giá trị | Nghĩa |
| --- | --- |
| `daily-invoice-report` | **Tên Task Definition** trong SCDF |
| `invoice-report` | Tên **Task application đã đăng ký** trong App Registry |
| `--definition "invoice-report"` | DSL mô tả thành phần/chương trình cần chạy |

Cùng một app registration có thể được dùng để tạo nhiều Task Definition:

~~~text
dataflow:> task create daily-invoice-report --definition "invoice-report"
dataflow:> task create month-end-invoice-report --definition "invoice-report"
~~~

Hai định nghĩa đều trỏ cùng artifact logic nhưng **được quản lý và gọi độc lập bằng hai tên khác nhau**. Trong vận hành thực tế, dùng nhiều định nghĩa khi chúng có lịch, người sở hữu, môi trường hoặc mục tiêu sử dụng khác nhau. Nếu mục tiêu chỉ là chạy lại một ngày khác, **một định nghĩa có thể launch nhiều lần với tham số ngày khác nhau**, không cần tạo định nghĩa mới cho mỗi ngày.

### 4.1. DSL của Task Definition

Cú pháp minh họa trong tài liệu SCDF:

~~~text
dataflow:> task create format-year-demo --definition "timestamp --format=\"yyyy\""
~~~

Đây là DSL của **Data Flow**, trong đó `timestamp` là tên ứng dụng đã đăng ký và `--format` là thuộc tính ứng dụng trong định nghĩa. Với bài này, ưu tiên định nghĩa tối giản `"invoice-report"`, rồi truyền ngày nghiệp vụ lúc launch để có thể tái sử dụng.

Một **Composed Task Definition** có thể kết nối nhiều Task application bằng DSL như:

~~~text
taskA && taskB
~~~

SCDF dùng **Composed Task Runner** để điều phối các thành phần khi chạy composed task. Đây là chủ đề mở rộng; khi đang học đăng ký và tạo định nghĩa đơn, chỉ cần hiểu DSL của task đơn có thể là **một tên app**, không cần kết nối START/END bằng ký hiệu trong Shell.

### 4.2. Tạo Task Definition qua Dashboard

Trong UI:

1. Mở mục **Tasks** và chức năng **Create Task**.
2. Chọn app `invoice-report` từ palette hoặc nhập định nghĩa `invoice-report`.
3. Với editor dạng canvas, nối **START → invoice-report → END**.
4. Chọn Create và đặt tên `daily-invoice-report`.
5. Kiểm tra danh sách Task Definitions có định nghĩa với tên và DSL dự kiến.

**Việc tạo xong định nghĩa chưa chạy công việc.** Dashboard có thể hiển thị trạng thái chưa có execution hoặc `UNKNOWN` cho định nghĩa mới; đây không phải bằng chứng Job đã thất bại.

### 4.3. Kiểm tra định nghĩa bằng Shell

Sau khi tạo:

~~~text
dataflow:> task list
dataflow:> task validate daily-invoice-report
~~~

`task list` liệt kê Task Definitions đã tạo. `task validate` giúp kiểm tra ứng dụng được tham chiếu còn có URI hợp lệ theo khả năng phân giải của server; **validation không thay thế launch thật** trên nền tảng Kubernetes/Cloud Foundry, kiểm tra quyền database hay kiểm tra nghiệp vụ.

**Tên định nghĩa chịu giới hạn của nền tảng.** Ví dụ Kubernetes giới hạn độ dài tên tài nguyên; không dùng tên có dấu cách, ký tự đặc biệt hoặc quá dài. Hãy chọn tên ngắn, ổn định và mô tả chức năng như `daily-invoice-report`.

## 5. Bước C: launch định nghĩa và truyền tham số

Sau khi tạo định nghĩa, có thể launch qua Shell:

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23"
~~~

SCDF yêu cầu **tên định nghĩa**, không phải Maven artifact name. Mỗi lần launch là một yêu cầu chạy mới; nếu tiến trình khởi động và TaskRepository ghi metadata bình thường, có thể có TaskExecution mới.

Giả sử runner nhận tham số `business-date` bằng `ApplicationArguments` như ví dụ ở mục 2. Giá trị `--business-date=2026-11-23` được truyền dưới dạng **application argument**, được parse thành `LocalDate`, rồi dùng xác định dữ liệu báo cáo.

### 5.1. Phân biệt arguments và properties

SCDF Shell có hai tùy chọn dễ nhầm:

| Tùy chọn lúc `task launch` | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `--arguments` | `"--business-date=2026-11-23"` | Các đối số command-line dành cho **ứng dụng Task** |
| `--properties` | `"app.daily-invoice-report.example=value"` | Thuộc tính được chuyển cho **TaskLauncher** hoặc ứng dụng/deployer tùy tiền tố và cách triển khai |

Ví dụ dạng tổng quát trong tài liệu SCDF:

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23 --dry-run=true"
~~~

Trong `--properties`, tiền tố **`app.<task-definition-name>.<property>`** được dùng cho application properties và **`deployer.<task-definition-name>.<property>`** dành cho deployment properties; tên property cụ thể và cách launcher đưa vào container phụ thuộc platform.

Không truyền `--business-date` trong `--properties` rồi mặc định `ApplicationArguments` sẽ nhìn thấy nó giống một đối số dòng lệnh. Nếu công việc mong đợi `ApplicationArguments.getOptionValues("business-date")`, dùng **`--arguments`** hoặc thay đổi ứng dụng để đọc cấu hình qua `Environment` theo chủ đích.

### 5.2. Launch từ Dashboard

Ở mục **Tasks → Task Definitions**, chọn `daily-invoice-report` rồi **Launch**. Giao diện thường cho điền riêng:

- **Arguments:** `--business-date=2026-11-23`.
- **Properties:** thuộc tính ứng dụng/deployer theo cách SCDF chuyển cho TaskLauncher.
- **Platform:** tài khoản/nền tảng chạy khi server đã cấu hình nhiều lựa chọn.

Sau khi gửi yêu cầu, UI có thể chuyển sang trang danh sách execution. Việc nút **Launch** trả phản hồi thành công mới cho biết **yêu cầu chạy được tiếp nhận**; kết quả nghiệp vụ thực tế phải kiểm tra ở execution record, log và kho dữ liệu đích.

### 5.3. Có thể launch nhiều lần

~~~text
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-23"
dataflow:> task launch daily-invoice-report --arguments "--business-date=2026-11-24"
~~~

Hai lệnh sử dụng **một Task Definition** nhưng dữ liệu nghiệp vụ khác nhau. SCDF không tự đảm bảo một kỳ báo cáo chỉ chạy một lần. Đối với kết quả phải **idempotent**, ứng dụng cần khóa nghiệp vụ như `(tenantId, businessDate, reportVersion)`, kiểm tra nguồn và quy tắc ghi kết quả.

Nếu ứng dụng tích hợp Spring Batch, cần phân biệt **Task arguments** với **Spring Batch JobParameters**; việc mapping giữa hai loại tham số phải do launcher hoặc ứng dụng thực hiện đúng phiên bản.

## 6. Nơi lưu định nghĩa và nơi lưu trạng thái thực thi

Khi dùng SCDF, có ít nhất ba tầng dữ liệu cần phân biệt:

~~~mermaid
flowchart LR
    U["Người dùng / SCDF Shell"] --> A["Data Flow Server"]
    A --> AR[("App Registry<br/>tên, loại, URI")]
    A --> TD[("Task Definition store<br/>tên, DSL")]
    A --> P["TaskLauncher / Platform"]
    P --> X["Task application process"]
    X --> TR[("TaskRepository<br/>TaskExecution + args")]
    X --> BR[("Business DB<br/>dữ liệu và kết quả")]
    A -. "đọc execution từ datastore phù hợp" .-> TR
~~~

| Kho dữ liệu | Nội dung chính | Ai tạo/cập nhật? |
| --- | --- | --- |
| **SCDF App Registry** | `task.invoice-report → artifact URI/version` | SCDF khi register/unregister app |
| **SCDF Task Definition Repository** | `daily-invoice-report → invoice-report` | SCDF khi create/destroy definition |
| **Spring Cloud TaskRepository** | `TaskExecution ID`, task name, start/end, exit code, exit message, arguments | Ứng dụng Task qua lifecycle của Spring Cloud Task |
| **Spring Batch JobRepository** (nếu có) | JobInstance, JobExecution, StepExecution, checkpoint | Spring Batch khi chạy Job |
| **CSDL nghiệp vụ** | Báo cáo, bản ghi nhập, trạng thái nguồn, checksum | Logic nghiệp vụ |

SCDF có thể dùng cơ sở dữ liệu để lưu cả thông tin điều khiển và metadata execution, nhưng **không đồng nhất các loại bản ghi**. Task Definition là **mẫu có thể chạy**, còn TaskExecution là **lịch sử một lần thực thi**.

### 6.1. Điều kiện để SCDF thấy TaskExecution

Trong mô hình SCDF truyền thống, khi SCDF launch một Task, nó cấp cho ứng dụng các thuộc tính datasource cần thiết để **Task ghi metadata vào repository mà Data Flow có thể đọc**. Điều này yêu cầu:

1. Ứng dụng có JDBC driver phù hợp với CSDL (ví dụ PostgreSQL nếu Data Flow dùng PostgreSQL).
2. Datasource, thông tin kết nối, quyền và schema TaskRepository là **đúng môi trường** và tương thích Spring Boot/Spring Cloud Task.
3. Data Flow Server có quyền đọc metadata Task trong datastore đó; nếu có nhiều schema/version targets, phải chọn đúng nơi tra cứu.
4. Không vô tình override datasource ứng dụng sang một H2 in-memory riêng hoặc kho khác làm execution “biến mất” khỏi Dashboard.

**Nếu khởi chạy Task bên ngoài SCDF**, nó vẫn có thể được theo dõi bởi SCDF nếu ghi metadata vào datastore mà SCDF sử dụng và tuân theo các yêu cầu cấu hình; tuy nhiên, đó không phải là hệ quả tự động của việc trùng tên ứng dụng.

**Không ghi bí mật vào Task arguments:** Spring Cloud Task có thể lưu đối số vào `TASK_EXECUTION_PARAMS`, chưa kể log và lịch sử lệnh. Kết nối CSDL nên dùng secret/configuration do nền tảng cấp, không nhúng password vào `--arguments`.

## 7. Xem lịch sử TaskExecution sau khi launch

Trong Data Flow Shell, các lệnh kiểm tra được tài liệu mô tả như sau:

~~~text
dataflow:> task execution list
dataflow:> task execution list --name daily-invoice-report
dataflow:> task execution status --id 4101
~~~

`4101` là **ID giả định** để minh họa, phải thay bằng ID thực tế từ `task execution list`. Trạng thái hiển thị có thể bao gồm tên, thời điểm bắt đầu/kết thúc, exit code, exit message và tham số chạy.

| Hiện tượng | Diễn giải hợp lý |
| --- | --- |
| Có execution ID mới, chưa có end time | Task có thể còn chạy hoặc chưa ghi kết thúc; đối chiếu Pod/Job |
| `EXIT_CODE=0`, có end time | Tiến trình kết thúc thành công về kỹ thuật; cần kiểm tra kết quả nghiệp vụ |
| `EXIT_CODE` khác `0` | Task báo lỗi; đọc log và thông tin exception |
| Launch được chấp nhận nhưng không có execution | Kiểm tra TaskLauncher, image pull, startup failure, datasource/schema và log nền tảng |
| Không thấy execution từ một lần chạy độc lập | Kiểm tra TaskRepository dùng chung, kết nối, schema target và quyền đọc |
| Một definition có nhiều execution | Bình thường: một định nghĩa được launch nhiều lần |

Trong Dashboard, vào **Tasks → Task Executions**, chọn một execution ID để xem chi tiết. Khi có tích hợp Spring Batch, giao diện có thể cung cấp liên kết đến JobExecution tương ứng.

### 7.1. Phân biệt launch thành công với tác vụ thành công

~~~text
Task Definition: daily-invoice-report
    │
    ├─ Launch #1: --business-date=2026-11-23
    │      └─ TaskExecution 4101: COMPLETED / exitCode=0
    │
    ├─ Launch #2: --business-date=2026-11-24
    │      └─ TaskExecution 4102: FAILED / exitCode!=0
    │
    └─ Launch #3: --business-date=2026-11-24
           └─ TaskExecution 4103: COMPLETED / exitCode=0
~~~

Đây chỉ là **kịch bản minh họa**. Việc một lần launch được SCDF tiếp nhận không có nghĩa Task đã chạy thành công; TaskExecution ID cũng khác với mã yêu cầu của bộ điều phối. Khi có failure, chạy lại cùng tham số nghiệp vụ phải được thiết kế không tạo dữ liệu trùng.

## 8. Khi nào cần Schedule hoặc Composed Task?

Đăng ký và tạo định nghĩa là **các thao tác chuẩn bị**; tác vụ chỉ chạy khi có yêu cầu launch hoặc lịch được cấu hình. SCDF cung cấp chức năng **Task Scheduling** ở những platform/phiên bản hỗ trợ và khi feature được bật.

Ví dụ cú pháp trong Data Flow Shell 2.11.x:

~~~text
dataflow:> task schedule create --definitionName daily-invoice-report --name daily-invoice-schedule --expression "0 2 * * *"
~~~

Lịch biểu chỉ là minh họa; độ chính xác của biểu thức, timezone, Cron parser và giới hạn scheduler phải kiểm chứng với nền tảng đã cấu hình. Các tính năng scheduling có thể bị **tắt mặc định** và cần bật qua cấu hình server, ví dụ các feature `spring.cloud.dataflow.features.schedules-enabled` và `spring.cloud.dataflow.features.tasks-enabled` trên phiên bản hỗ trợ.

**Định nghĩa tác vụ không phải định nghĩa lịch.** Một Task Definition có thể được chạy ad hoc hoặc theo nhiều yêu cầu khác nhau. Nếu cần thực hiện `import → validate → report` theo các nhánh thành công/thất bại, nghiên cứu **Composed Task Runner** thay vì coi một định nghĩa Task đơn đã tự thực hiện workflow nhiều bước.

## 9. Quản trị thay đổi artifact và Task Definition

Một số tình huống phổ biến:

| Thay đổi | Điều cần kiểm tra |
| --- | --- |
| Đẩy image `invoice-report-task:1.0.1` | Version mới đã publish và có thể pull? SCDF App Registry có còn trỏ version cũ không? |
| Đổi URI registration | Task Definition phụ thuộc tên app nào? SCDF/deployer chọn artifact ở lần launch tiếp theo ra sao? |
| Đổi tham số runner `business-date` thành `report-date` | Những lịch và yêu cầu launch cũ có còn hợp lệ? |
| Đổi DataSource/schema TaskRepository | Execution cũ có còn xuất hiện trong SCDF và có kế hoạch migration? |
| Muốn xóa Task Definition | `task destroy` loại bỏ định nghĩa; đánh giá tác động tới lịch và dữ liệu execution |
| Tăng số lần chạy đồng thời | Thêm giới hạn workload, database capacity và idempotency theo business key |

**Phân biệt `app unregister` và `task destroy`:** unregister liên quan bản ghi đăng ký artifact, còn destroy liên quan định nghĩa tác vụ. Trong tài liệu SCDF, `task destroy <name>` mặc định không xóa lịch sử TaskExecution đã có; một số chế độ cleanup có thể thay đổi điều này. Không dùng thao tác xóa chỉ để “sửa tên” khi hệ thống đang phục vụ lịch sản xuất.

Tổ chức tốt thường quản lý **version của image/JAR**, **định nghĩa tác vụ**, **cấu hình triển khai** và **lịch chạy** như các thành phần có thể kiểm soát thay đổi. Khi cần truy vết báo cáo cũ, giữ đủ thông tin phiên bản artifact, business key và source checksum để tái hiện kết quả.

## 10. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xét | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `task create` báo không tìm thấy app | Chưa register hoặc tên/loại app khác | Kiểm tra App Registry có `task.invoice-report` |
| Register thành công nhưng launch không chạy | Artifact URI không phân giải được; registry credentials; image pull lỗi | `task validate`, logs TaskLauncher/Pod/Job |
| Image chạy nhưng ứng dụng không thoát | Runner khởi tạo background thread hoặc server web | `spring.main.web-application-type=none`, chờ Future/Job hoàn tất |
| Launch thiếu `business-date` | Quên `--arguments`, option sai tên | Xem launch request/Task args và validation trong runner |
| Task có exit code 0 dù báo cáo thất bại | Exception bị nuốt hoặc Batch Job FAILED không phản ánh Task | Xử lý lỗi rõ ràng, kiểm tra JobExecution/mã thoát |
| `TaskExecution` không xuất hiện trong SCDF | Datasource Task khác datastore SCDF, schema sai hoặc startup lỗi sớm | So sánh kết nối, driver, quyền, schema targets và logs |
| UI thấy Task Definition nhưng chưa có execution | Chỉ tạo định nghĩa, chưa launch | Chọn Launch hoặc cấu hình lịch |
| Dùng lại cùng ngày tạo báo cáo trùng | Không có idempotency nghiệp vụ | Unique key/report version, upsert và outbox cho thông báo |
| Không thấy log | Log bị giữ ở platform hoặc retention ngắn | Kiểm tra Pod logs, logging backend và quyền xem |
| Scheduler không tạo lượt chạy | Tính năng schedule chưa bật, platform không hỗ trợ, Cron/timezone sai | Server feature flags, scheduler logs và thực thi manual |

**Cách điều tra hiệu quả:** xác định lỗi xảy ra ở **registration**, **definition**, **launch/platform**, **startup TaskRepository** hay **logic nghiệp vụ**. Một lệnh `app register` thành công chỉ xác nhận SCDF đã lưu metadata đăng ký, không chứng minh bốn giai đoạn sau sẽ thành công.

## 11. Quy trình thực hành trọn vẹn

Giả sử một ứng dụng nhập dữ liệu `csv-import-task` đã build, có thể chạy độc lập, và image có tag cố định `1.0.0`.

### 11.1. Đăng ký, định nghĩa và launch

Trong SCDF Shell:

~~~text
dataflow:> app register --name csv-import --type task --uri docker:registry.example.com/batch/csv-import-task:1.0.0

dataflow:> task create daily-csv-import --definition "csv-import"

dataflow:> task list

dataflow:> task validate daily-csv-import

dataflow:> task launch daily-csv-import --arguments "--source-id=partner-A-2026-11-23 --business-date=2026-11-23"
~~~

Đây là **ví dụ**, không tự chạy trong tài liệu; Docker registry và image phải được thay bằng tài nguyên mà môi trường SCDF có quyền truy cập. Nếu ứng dụng không có option `--source-id` và `--business-date`, hãy điều chỉnh runner trước.

### 11.2. Quan sát và chạy lại

~~~text
dataflow:> task execution list --name daily-csv-import

dataflow:> task execution status --id 4101
~~~

Ghi lại kết quả:

| Thông tin | Kết quả cần ghi |
| --- | --- |
| App registration | Loại `task`, URI, version |
| Task Definition | `daily-csv-import`, DSL `csv-import` |
| Launch arguments | `source-id`, `business-date` |
| TaskExecution | ID, start/end, exit code, exit message |
| Kết quả nghiệp vụ | Tổng số dòng nhập, số lỗi, checksum |
| Bằng chứng chạy lại | Chạy cùng source ID hai lần không nhân đôi bản ghi |

Sau khi chạy lần đầu, thử **chạy lại cùng tham số** và kiểm tra idempotency ở bảng nghiệp vụ. Mỗi lần chạy kỹ thuật có thể tạo TaskExecution ID riêng; không nên coi đó là tín hiệu có dữ liệu mới.

### 11.3. Thử những trường hợp lỗi quan trọng

1. **URI sai:** đăng ký một image không tồn tại trong môi trường thử nghiệm, gọi `task validate`, rồi thử launch để xem lỗi resolver/deployer.
2. **Tham số thiếu:** launch mà không truyền `--business-date`; xác nhận runner ném lỗi và exit code phù hợp.
3. **Datasource sai:** cho Task trỏ tới repository khác, rồi giải thích vì sao SCDF không thấy execution đó.
4. **Nguồn xử lý trùng:** gọi cùng `source-id` hai lần, đối chiếu unique key và số dòng sau nhập.
5. **Image version mới:** đăng ký version mới theo quy trình hỗ trợ rồi xác nhận định nghĩa/lượt chạy sử dụng artifact mong muốn.

**Tiêu chí đạt:** người học có thể giải thích bằng lời và bằng kết quả thử nghiệm **đăng ký app → tạo định nghĩa → launch → xem execution**; biết bản ghi nào do SCDF quản lý, bản ghi nào do Spring Cloud Task ghi, và có khả năng tìm nguyên nhân khi “đã bấm Launch nhưng không thấy Task chạy”.

## 12. Các điểm cần ghi nhớ

1. **`app register --type task`** ánh xạ tên logic của một Task application tới URI artifact; bước này **chưa chạy** ứng dụng.
2. **`task create <name> --definition "<app-name>"`** tạo Task Definition có thể tái sử dụng. Tên định nghĩa và tên app đã đăng ký là **hai tên độc lập**.
3. **`task launch <definition-name>`** tạo yêu cầu chạy. **`--arguments`** truyền đối số tới ứng dụng, còn **`--properties`** thuộc cơ chế TaskLauncher/deployer.
4. **TaskDefinition khác TaskExecution**: một định nghĩa có thể sinh nhiều lần thực thi; mỗi lượt cần đối soát start/end, exit code và kết quả nghiệp vụ.
5. SCDF quản lý **registry, definitions, launch, lịch và giao diện quan sát**; Spring Cloud Task quản lý **lifecycle và metadata TaskExecution**; Spring Batch nếu có quản lý **Job/Step metadata**.
6. Muốn SCDF xem được lịch sử, **TaskRepository và cấu hình DataSource/schema phải nhất quán**, kể cả khi launcher và Task chạy ở những tiến trình khác nhau.
7. Đăng ký và tạo định nghĩa **không thay thế** validation, logging, secrets, idempotency, kiểm soát chạy đồng thời và quản lý version artifact.

### Nguồn tham khảo

- [Spring Cloud Data Flow Reference Guide 2.11.x — Lifecycle of a Task](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.3/reference/htmlsingle/#_the_lifecycle_of_a_task)
- [Spring Cloud Data Flow — Getting Started with Task Processing](https://dataflow.spring.io/docs/batch-developer-guides/getting-started/task/)
- [Spring Cloud Data Flow — Deploying a Spring Cloud Task application](https://dataflow.spring.io/docs/batch-developer-guides/batch/data-flow-simple-task/)
- [Spring Cloud Data Flow — Short-lived Applications](https://dataflow.spring.io/docs/concepts/architecture/)
- [Spring Cloud Data Flow — Tooling](https://dataflow.spring.io/docs/concepts/tooling/)
- [Spring Blog — End of Open-Source (21/04/2025)](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
