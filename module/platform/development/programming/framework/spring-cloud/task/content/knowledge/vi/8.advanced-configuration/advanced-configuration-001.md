# Nhóm thuộc tính spring.cloud.task và phạm vi tác dụng

**Spring Cloud Task** hỗ trợ xây dựng ứng dụng Spring Boot có thời gian chạy hữu hạn: khởi động, thực hiện công việc và kết thúc. Framework ghi nhận mỗi lần chạy bằng `TaskExecution` trong `TaskRepository`, gồm thời gian bắt đầu/kết thúc, trạng thái, mã thoát và đối số khởi chạy. Để sử dụng ổn định ở môi trường thật, cần hiểu **thuộc tính nào điều khiển phần nào của hệ thống**, thay vì đặt mọi cấu hình liên quan đến tác vụ dưới một tiền tố duy nhất.

Trong chương **Cấu hình mở rộng**, bài học này phân nhóm các thuộc tính `spring.cloud.task.*` theo tác dụng: **metadata repository và schema**, **vòng đời**, **định danh thực thi**, **giới hạn chạy đồng thời**, **tích hợp Spring Batch**, **sự kiện và quan sát**. Bài cũng chỉ ra các cấu hình của Spring Boot, JDBC và bộ điều phối nằm **ngoài** namespace này.

> **Lưu ý phiên bản:** Tên thuộc tính có thể xuất hiện ở dạng *kebab-case* (`table-prefix`) hoặc *camelCase* (`tablePrefix`) nhờ Spring Boot relaxed binding. Ví dụ dùng kebab-case và dựa trên hướng dẫn Spring Cloud Task hiện đại; hãy kiểm tra metadata cấu hình, BOM và tài liệu của **phiên bản đang triển khai** trước khi áp dụng. Một số thuộc tính và giá trị mặc định đã thay đổi qua các nhánh phát hành.

## 1. Phạm vi của từng tầng cấu hình

~~~mermaid
flowchart TD
    A["Launcher: CronJob / scheduler / API"] --> B["Tiến trình Spring Boot"]
    B --> C["spring.application, spring.main, spring.datasource"]
    C --> D["Spring Cloud Task"]
    D --> E["spring.cloud.task.*"]
    E --> F[("TaskRepository / TaskExplorer")]
    D --> G["ApplicationRunner / CommandLineRunner"]
    G --> H["Xử lý nghiệp vụ"]
    G --> I["Spring Batch Job nếu có"]
    I --> J[("JobRepository")]
    D -. "Quan sát / sự kiện tùy chọn" .-> K["Micrometer / Spring Cloud Stream"]
~~~

| Namespace hoặc cơ chế | Điều chỉnh phần nào? | Ví dụ | **Không** tự làm gì? |
| --- | --- | --- | --- |
| `spring.cloud.task.*` | Lifecycle, repository, execution ID, giới hạn instance và tích hợp Task | `spring.cloud.task.table-prefix` | Không tạo lịch Cron, không định nghĩa nghiệp vụ |
| `spring.application.*` | Thông tin định danh ứng dụng Spring Boot | `spring.application.name` | Không tự tạo khóa chống trùng theo dữ liệu |
| `spring.datasource.*` | Kết nối CSDL do Spring Boot quản lý | `spring.datasource.url` | Không đổi tên bảng Task theo prefix |
| `spring.sql.init.*` | Khởi tạo SQL chung của Spring Boot | `spring.sql.init.mode` | Không thay thế migration/schema Task của mọi phiên bản |
| `spring.batch.*` | Hành vi Spring Batch và Job launcher | `spring.batch.job.enabled` | Không thay thế `TaskRepository` |
| `spring.task.*` | Executor/scheduler của Spring Boot | `spring.task.scheduling.pool.size` | Không phải cấu hình Spring Cloud Task |
| Cron, Kubernetes CronJob, Quartz, workflow engine | Khi nào/bao nhiêu lần khởi chạy tiến trình | `schedule: "0 2 * * *"` | Không tự ghi `TaskExecution` nếu ứng dụng không chạy Task |

**Điểm hay nhầm:** `spring.cloud.task.*` **không** đồng nghĩa với `spring.task.*`. Tên gần giống nhau, nhưng `spring.task` trong Spring Boot cấu hình cơ chế executor/scheduler; `spring.cloud.task` cấu hình framework quản lý **một lần chạy hữu hạn**.

Một tác vụ có thể được gọi đúng 2 giờ sáng bằng CronJob nhưng vẫn ghi metadata lỗi nếu kết nối TaskRepository không hoạt động. Ngược lại, cấu hình `spring.cloud.task.single-instance-enabled=true` không làm chương trình tự chạy vào 2 giờ sáng; nó chỉ can thiệp vào **việc cho phép nhiều lần thực thi cùng tên diễn ra đồng thời**.

## 2. Bảng tra cứu nhanh nhóm spring.cloud.task

Các thuộc tính dưới đây được nhóm theo **phạm vi tác động thực tế**:

| Nhóm | Thuộc tính | Ý nghĩa trọng tâm |
| --- | --- | --- |
| **Repository/schema** | `spring.cloud.task.table-prefix` | Tiền tố các bảng metadata Task |
| | `spring.cloud.task.initialize-enabled` | Cho phép/tắt cơ chế khởi tạo bảng Task |
| **Vòng đời** | `spring.cloud.task.closecontext-enabled` | Đóng ApplicationContext sau khi tác vụ kết thúc |
| | `spring.cloud.task.autoconfiguration.enabled` | Bật/tắt tự cấu hình Spring Cloud Task theo phiên bản hỗ trợ |
| **Định danh và quan hệ** | `spring.cloud.task.executionid` | Sử dụng TaskExecution ID đã tạo trước |
| | `spring.cloud.task.external-execution-id` | Gắn mã định danh từ hệ thống bên ngoài |
| | `spring.cloud.task.parent-execution-id` | Liên kết lần chạy con với TaskExecution của tác vụ cha |
| **Chạy đồng thời** | `spring.cloud.task.single-instance-enabled` | Ngăn hai lần chạy **cùng task name** đồng thời |
| | `spring.cloud.task.single-instance-lock-ttl` | Thời gian giữ khóa cho single-instance (nếu phiên bản hỗ trợ) |
| | `spring.cloud.task.single-instance-lock-check-interval` | Khoảng kiểm tra khóa (nếu phiên bản hỗ trợ) |
| **Batch** | `spring.cloud.task.batch.fail-on-job-failure` | Phản ánh Batch Job thất bại thành mã thoát Task không thành công |
| | `spring.cloud.task.batch.application-runner-order` | Thứ tự runner khi dùng cơ chế Batch nói trên |
| | `spring.cloud.task.batch.listener.enabled` | Điều khiển liên kết Task–Batch ở các nhánh có thuộc tính này |
| **Sự kiện/quan sát** | `spring.cloud.task.events.enabled` | Phát sự kiện Task khi có tích hợp Spring Cloud Stream thích hợp |
| | `spring.cloud.task.batch.events.enabled` | Phát sự kiện Batch qua cơ chế tích hợp tương ứng |
| | `spring.cloud.task.observation.enabled` | Bật observation cho `ApplicationRunner` / `CommandLineRunner` ở phiên bản hỗ trợ |

Bảng là **bản đồ lựa chọn cấu hình**, không phải danh sách bắt buộc phải bật đồng loạt. Chẳng hạn, ứng dụng chỉ chạy một runner và ghi kết quả vào PostgreSQL thường không cần Batch, Stream hay giới hạn instance dựa trên Spring Integration.

## 3. Nhóm repository và schema

### 3.1. `spring.cloud.task.table-prefix`: tên bảng metadata

Mặc định Spring Cloud Task dùng tiền tố `TASK_`, tạo nên các tên như `TASK_EXECUTION` và `TASK_EXECUTION_PARAMS`.

~~~yaml
spring:
  cloud:
    task:
      table-prefix: TASK_
~~~

Nếu cần tách bộ bảng Task ở một schema chung, có thể cấu hình tiền tố khác:

~~~properties
spring.cloud.task.table-prefix=OPS_TASK_
~~~

Khi đó, repository kỳ vọng các bảng có tiền tố tương ứng (ví dụ `OPS_TASK_EXECUTION`). **Đổi prefix không tự di chuyển, đổi tên hay chuyển dữ liệu giữa các bảng**. Người vận hành phải tạo đúng DDL của framework với prefix đã chọn, sửa migration và bảo đảm trình truy vấn/reporting nhìn vào đúng bảng.

Một thay đổi prefix giữa hai lần chạy có thể khiến lịch sử cũ dường như “biến mất” vì ứng dụng đang trỏ sang bộ bảng mới. Đây là thay đổi cấu trúc, cần kế hoạch migration và đối soát.

### 3.2. `spring.cloud.task.initialize-enabled`: quyền tạo bảng

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
~~~

Khi `false`, Spring Cloud Task **không thực hiện bước tự tạo schema Task** lúc khởi động. Cách này thường phù hợp môi trường production đã quản lý bảng bằng Flyway, Liquibase hoặc quy trình migration độc lập. Khi bật khởi tạo, Task cố gắng dùng cơ chế và DDL được hỗ trợ cho nền tảng CSDL tương ứng.

Theo hướng dẫn tham khảo, hành vi mặc định có thể bật khởi tạo; một số API biểu diễn giá trị cấu hình là `Boolean` và `null` để tương thích thuộc tính cũ. Vì vậy, với sản xuất, **đặt `false` tường minh sau khi migration đã tạo đủ bảng** sẽ dễ kiểm soát hơn việc suy đoán giá trị mặc định.

Tên lịch sử `spring.cloud.task.initialize.enable` đã được đánh dấu deprecated trong tài liệu; ưu tiên `initialize-enabled` trên nhánh hỗ trợ.

**Không nhầm với** `spring.sql.init.mode`: cơ chế SQL initialization của Spring Boot có phạm vi riêng. Tắt một bên không bảo đảm bên kia cũng tắt. Kiểm tra log khởi động và các migration thực tế để chắc chắn cơ chế nào tạo bảng.

### 3.3. CSDL của TaskRepository nằm ở đâu?

Ví dụ cấu hình chung:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      table-prefix: TASK_
      initialize-enabled: false
~~~

`spring.datasource.*` cung cấp DataSource; khi chỉ có một `DataSource` phù hợp, Spring Cloud Task có thể dùng nó cho repository. **Không có thuộc tính `spring.cloud.task.datasource.url` chuẩn để thay thế toàn bộ cấu hình đa nguồn**. Với nhiều DataSource, dùng `TaskConfigurer` để chọn đúng nguồn và transaction manager cho TaskRepository/TaskExplorer; nghiệp vụ có thể dùng DataSource riêng.

Trong môi trường production, tài khoản CSDL dành cho tác vụ cần quyền theo nguyên tắc tối thiểu. Cơ sở dữ liệu metadata phải tồn tại qua nhiều lần chạy; dùng H2 trong bộ nhớ chỉ phù hợp minh họa vì dữ liệu có thể mất khi tiến trình kết thúc.

## 4. Nhóm vòng đời: lúc nào tiến trình kết thúc?

### 4.1. `spring.cloud.task.closecontext-enabled`

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

Khi bật, Spring Cloud Task đóng `ApplicationContext` sau khi các runner hoàn thành và metadata kết thúc đã được cập nhật, giúp giải phóng tài nguyên. Nó đặc biệt hữu ích khi bean hoặc thread pool giữ thread sống khiến JVM chưa thoát dù nghiệp vụ đã xong.

**Điều kiện quan trọng:** runner phải **đợi công việc bất đồng bộ hoàn thành** trước khi trả về. Nếu runner chỉ submit Future rồi kết thúc, việc đóng context có thể làm ngắt công việc còn chạy. Thuộc tính này không biến lời gọi bất đồng bộ thành đồng bộ, cũng không thay thế quy trình graceful shutdown của các tài nguyên nghiệp vụ.

Ví dụ logic đúng về vòng đời:

~~~java
@Bean
ApplicationRunner runReport(ReportService service) {
    return args -> {
        // Hàm tạo báo cáo chỉ trả về khi kết quả đã được ghi xong.
        service.generateAndWait();
    };
}
~~~

Với một `@Scheduled` chạy mãi trong tiến trình server, bật `closecontext-enabled` không khiến nó trở thành tác vụ theo lịch độc lập; mô hình triển khai cần cân nhắc lại cho phù hợp ứng dụng hữu hạn.

### 4.2. `spring.cloud.task.autoconfiguration.enabled`

Tài liệu Spring Cloud Task hỗ trợ tắt auto configuration của framework bằng cấu hình:

~~~properties
spring.cloud.task.autoconfiguration.enabled=false
~~~

Khi tắt, không còn mặc nhiên có các thành phần lifecycle/repository được tạo tự động như ứng dụng Spring Cloud Task thông thường. Chỉ dùng khi thật sự muốn vô hiệu hóa cơ chế Task hoặc cung cấp cấu hình đặc thù đã được kiểm chứng; đây **không** phải cách tạm thời để bỏ qua lỗi kết nối TaskRepository. Nếu cần tùy biến repository, xem `TaskConfigurer` trước khi tắt toàn bộ tự cấu hình.

### 4.3. Đặt tên tác vụ

Tên `TaskExecution.taskName` thường lấy từ `spring.application.name` theo cơ chế `TaskNameResolver` mặc định hoặc từ resolver tùy biến. Ví dụ:

~~~properties
spring.application.name=invoice-report-task
~~~

Đừng tự suy ra rằng `spring.cloud.task.name` là một khóa cấu hình chuẩn trên mọi phiên bản. Hãy dùng `spring.application.name` khi muốn tên ứng dụng/tác vụ nhất quán, hoặc hiện thực `TaskNameResolver` nếu cần quy tắc tên khác.

Tên task rất quan trọng khi bật **single-instance** vì phạm vi khóa là tên tác vụ, không phải ngày báo cáo hoặc source ID.

## 5. Nhóm định danh: TaskExecution ID, external ID và parent ID

### 5.1. `spring.cloud.task.executionid`: cập nhật lần chạy tạo sẵn

Thông thường, mỗi lần khởi chạy tiến trình, Spring Cloud Task tạo một TaskExecution mới và cấp mã số tương ứng. Trong hệ thống điều phối nâng cao, có thể cần tạo TaskExecution **ngay khi tiếp nhận yêu cầu**, sau đó tiến trình thực thi được khởi chạy muộn hơn.

Khi đã tạo trước bản ghi bằng `TaskRepository`, truyền ID đó cho tác vụ:

~~~bash
java -jar invoice-report-task.jar \
  --spring.cloud.task.executionid=81042 \
  --report-date=2026-11-23
~~~

Giá trị `81042` là ví dụ; phải là **ID thực sự tồn tại** trong repository mà tiến trình sẽ dùng, có quyền cập nhật và đúng trạng thái. Không tự đặt số bất kỳ rồi giả định framework sẽ tự tạo bản ghi với số đó.

### 5.2. `spring.cloud.task.external-execution-id`: gắn mã launcher

Một Kubernetes Job, workflow engine hoặc dịch vụ điều phối có thể có mã theo dõi riêng. Gắn mã đó vào TaskExecution để đối soát chéo:

~~~properties
spring.cloud.task.external-execution-id=workflow-run-2026-11-24-001
~~~

Đây là **mã bên ngoài** được lưu cùng metadata Task; nó **không thay thế** TaskExecution ID do TaskRepository quản lý và không tự tạo quy tắc duy nhất cho nghiệp vụ.

### 5.3. `spring.cloud.task.parent-execution-id`: quan hệ cha–con

Nếu Task A khởi chạy Task B, Task B có thể được gắn với TaskExecution ID của Task A:

~~~properties
spring.cloud.task.parent-execution-id=81040
~~~

Khi đó, người vận hành có thể tìm các lần chạy con thuộc một workflow. **Parent ID** là quan hệ truy vết, không phải cam kết rằng con phải thành công hoặc rollback cùng cha; việc xử lý lỗi giữa các task thuộc trách nhiệm của bộ điều phối hoặc logic workflow.

| Thuộc tính | Chỉ tới cái gì? | Thường lấy từ |
| --- | --- | --- |
| `executionid` | TaskExecution **hiện tại**, đã tạo trước | TaskRepository/launcher |
| `external-execution-id` | ID trong hệ thống bên ngoài | CronJob, workflow run, request tracker |
| `parent-execution-id` | TaskExecution của task **cha** | Bộ điều phối các tác vụ liên quan |

Không nên đưa các ID trên thành quy ước chống trùng dữ liệu. Hai lần chạy nhập cùng tệp có thể có hai TaskExecution ID khác nhau; **business key và idempotency** mới quyết định việc ghi lại có hợp lệ không.

## 6. Nhóm kiểm soát chạy đồng thời

### 6.1. `spring.cloud.task.single-instance-enabled`

~~~yaml
spring:
  application:
    name: inventory-sync-task
  cloud:
    task:
      single-instance-enabled: true
~~~

Khi bật, Spring Cloud Task kiểm tra xem đã có một lần chạy **cùng tên task** đang thực thi hay chưa. Nếu có, lần chạy mới bị từ chối và có thể trả mã thoát lỗi. Mặc định tính năng này **không bật**, vì nhiều công việc ngắn hạn được thiết kế chạy song song.

Tính năng single-instance sử dụng cơ chế từ **Spring Integration**; hướng dẫn chính thức yêu cầu bổ sung các module phù hợp như `spring-integration-core` và `spring-integration-jdbc` vào dependencies. Chỉ đổi cờ `true` khi thiếu dependency hoặc schema cho cơ chế khóa có thể khiến khởi động lỗi; cần kiểm thử với đúng CSDL và phiên bản deploy.

**Phạm vi khóa:** tên tác vụ, không phải tham số `--report-date`, `--tenant-id` hay `--source-id`.

Ví dụ:

| Lượt chạy | Task name | Tham số nghiệp vụ | Khi single-instance đang bật |
| --- | --- | --- | --- |
| A | `invoice-report-task` | `date=2026-11-23` | Chạy |
| B, xuất hiện lúc A đang chạy | `invoice-report-task` | `date=2026-11-24` | Bị chặn vì **cùng tên**, dù khác ngày |
| C | `order-import-task` | `source=partner-a` | Không bị chặn chỉ vì A đang chạy |

Nếu nhu cầu là **không chạy trùng cùng tenant và ngày** nhưng cho phép khác ngày chạy song song, hãy dùng khóa/ràng buộc duy nhất theo business key tại tầng nghiệp vụ thay cho khóa bao toàn bộ task name.

### 6.2. TTL và khoảng kiểm tra khóa

Một số nhánh có hai thuộc tính bổ sung:

~~~properties
spring.cloud.task.single-instance-lock-check-interval=500
spring.cloud.task.single-instance-lock-ttl=600000
~~~

Trong các phiên bản công bố nhóm thuộc tính này, đơn vị là **mili giây**: `500` ms giữa các lượt kiểm tra, `600000` ms tương đương 10 phút. Thời gian giữ khóa phải phù hợp thời gian chạy tối đa và cơ chế xử lý tiến trình chết. Đặt TTL quá ngắn có thể cho phép một lượt khác chạy khi lượt trước chưa kết thúc; quá dài làm trì hoãn phục hồi khi có sự cố.

**Kiểm tra hỗ trợ phiên bản** trước khi dùng các khóa TTL/interval, vì tên thuộc tính, mặc định và cơ chế thực thi có thể khác giữa các dòng phát hành.

### 6.3. Phân biệt với giới hạn ở bộ điều phối

Kubernetes CronJob có `concurrencyPolicy: Forbid` để tránh chồng lấn các Job của **cùng CronJob**. Cờ `single-instance-enabled` giới hạn theo **Task name** của ứng dụng khi dùng cơ chế Spring Cloud Task và repository/lock tương thích. Hai phạm vi độc lập: một Job do API gọi thủ công vẫn có thể xuất hiện ngoài CronJob.

Trong triển khai an toàn, nên chọn chính sách ở cả ba tầng: bộ điều phối (đợt chạy), Task (tên tác vụ nếu cần) và nghiệp vụ (business key/idempotency).

## 7. Nhóm tích hợp Spring Batch

Spring Cloud Task quản lý **lần chạy tiến trình**; Spring Batch quản lý **Job, Step, checkpoint và JobRepository**. Cấu hình Task–Batch không thay thế các `spring.batch.*` của Spring Boot.

### 7.1. `spring.cloud.task.batch.fail-on-job-failure`

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Khi chạy một Spring Batch Job trong Task, có tình huống Job thất bại nhưng tiến trình Spring Boot vẫn kết thúc với mã thoát `0` theo hành vi launcher mặc định. Bật thuộc tính trên để tích hợp Task phản ánh Batch Job có `BatchStatus.FAILED` thành **mã thoát khác 0** (thường `1`, hoặc theo `ExitCodeGenerator` đã cấu hình). Đây là điểm quan trọng nếu CronJob/CI/workflow cần phát hiện thất bại từ **exit code của tiến trình**.

Thuộc tính này có tác dụng trong **cấu hình tích hợp Task–Batch tương thích**, khi có Batch Job thực sự được thực thi; nó không khiến mọi exception trong nghiệp vụ được tự động retry hay skip.

### 7.2. Runner order và liên kết JobExecution

Tài liệu mô tả `spring.cloud.task.batch.application-runner-order` để điều chỉnh thứ tự ApplicationRunner đặc thù khi bật `fail-on-job-failure`. Nếu ứng dụng có nhiều runner, thay đổi thứ tự có thể ảnh hưởng thời điểm Batch Job chạy so với bước chuẩn bị dữ liệu.

Một số nhánh có `spring.cloud.task.batch.listener.enabled` để điều khiển liên kết `JobExecution` với `TaskExecution`; trên những nhánh khác, khả năng này còn phụ thuộc module `spring-cloud-task-batch`, auto configuration và listener. Trước khi đổi cờ, hãy xem phiên bản thực tế và kiểm tra bảng liên kết sau khi chạy thử.

`spring.batch.job.enabled` hoặc cấu hình chọn Job khởi chạy của Spring Boot thuộc **namespace Batch**, không phải `spring.cloud.task.batch.job-names` (thuộc tính cũ đã bị deprecated ở những nhánh lịch sử).

### 7.3. Khi nào cần thay đổi các thuộc tính Batch?

| Tình huống | Điều chỉnh cần cân nhắc |
| --- | --- |
| Chạy Job Import nhiều chunk, cần JobExecution gắn với Task | Module Task–Batch và listener liên kết |
| Job lỗi nhưng workflow bên ngoài vẫn thấy mã 0 | `spring.cloud.task.batch.fail-on-job-failure=true` |
| Có runner chuẩn bị dữ liệu và runner khởi động Batch | Kiểm tra `application-runner-order` và cơ chế launcher |
| Cần chỉ chạy một Job trong nhiều Job bean | Cấu hình Spring Batch/Spring Boot phù hợp phiên bản; xác minh Job được chọn |
| Cần restart Job từ checkpoint | JobRepository, JobParameters, restart policy **của Spring Batch**, không phải `TaskExecution ID` |

## 8. Nhóm sự kiện, observation và giám sát

### 8.1. `spring.cloud.task.events.enabled`

Trong hệ thống có Spring Cloud Stream và binder phù hợp, Spring Cloud Task có thể phát các sự kiện lifecycle Task qua message channel. Với tích hợp đó:

~~~properties
spring.cloud.task.events.enabled=false
~~~

sẽ **vô hiệu hóa phát sự kiện Task**. Đừng hiểu rằng cờ này tắt việc ghi `TaskExecution` vào cơ sở dữ liệu; phát message và lưu metadata là hai cơ chế khác nhau. Cờ chỉ hữu ích khi integration events có dependency và cấu hình thực sự được dùng.

### 8.2. `spring.cloud.task.batch.events.enabled`

~~~properties
spring.cloud.task.batch.events.enabled=false
~~~

Trong tích hợp Batch events thích hợp, cờ này có thể tắt việc phát sự kiện cho Job/Step/Chunk. Một số phiên bản hỗ trợ tắt riêng `job-execution`, `step-execution`, `chunk`, `item-read`, `item-process`, `item-write`, `skip` dưới `spring.cloud.task.batch.events.*.enabled`.

Bật/tắt phát sự kiện **không thay thế** JobRepository, TaskRepository hay giám sát trạng thái Job. Nếu cần quan sát chi tiết, phải thiết kế kênh nhận, retry, quyền truy cập và chính sách lưu event.

### 8.3. `spring.cloud.task.observation.enabled`

Các nhánh hiện đại cho phép bật observation đối với `ApplicationRunner` / `CommandLineRunner`:

~~~properties
spring.cloud.task.observation.enabled=true
~~~

Để xuất số liệu/tracing thực tế, cần cấu hình Micrometer, Actuator, registry/tracing exporter tương ứng. Một boolean **không tự tạo dashboard** và không tự gắn nhãn nghiệp vụ vào mọi phép đo. Giữ các nhãn có cardinality phù hợp, tránh đưa token, đường dẫn chứa PII hoặc TaskExecution ID số lượng rất lớn thành tag metric nếu không cần.

## 9. Ví dụ cấu hình theo môi trường

### 9.1. Cấu hình cơ bản cho task chạy một lần

Giả sử ứng dụng `daily-report-task` được đóng gói cùng `spring-cloud-starter-task`, JDBC driver và các dependency tương thích với phiên bản Spring Boot:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      table-prefix: TASK_
      initialize-enabled: false
      closecontext-enabled: true
~~~

**Điều kiện trước khi chạy:** người vận hành đã tạo bảng Task theo migration tương thích với CSDL, schema, prefix và phiên bản thư viện. Biến `TASK_DB_*` do môi trường chạy/secret manager cung cấp; không commit mật khẩu vào tệp.

Đối với ứng dụng dùng `ApplicationRunner`:

~~~java
@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner runReport(ReportService reports) {
        return args -> {
            List<String> values = args.getOptionValues("date");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Expected one --date=yyyy-MM-dd");
            }
            LocalDate date = LocalDate.parse(values.get(0));
            reports.generate(date); // Đồng bộ đến khi báo cáo đã hoàn tất.
        };
    }
}

interface ReportService {
    void generate(LocalDate date);
}
~~~

Các import tương ứng: `java.time.LocalDate`, `java.util.List`, `ApplicationRunner`, `SpringApplication`, `SpringBootApplication`, `@EnableTask`, `@Bean`. `ReportService` chỉ là hợp đồng nghiệp vụ; ứng dụng thật cần bean cài đặt interface này. Đoạn code không tự tạo lịch.

Chạy thủ công:

~~~bash
java -jar daily-report-task.jar --date=2026-11-23
~~~

Kết quả mong đợi: một TaskExecution có tên `daily-report-task`, danh sách đối số gồm `--date=2026-11-23`, thời điểm bắt đầu/kết thúc và mã thoát tương ứng. Đối với lỗi đầu vào, runner cần ném exception để framework/bộ điều phối thấy thất bại, thay vì chỉ log rồi trả về bình thường.

### 9.2. Bật cờ chỉ cho lần chạy cần thiết

Ví dụ kiểm soát chạy trùng theo tên ở môi trường có đầy đủ Spring Integration dependency và schema khóa:

~~~bash
java -jar daily-report-task.jar \
  --date=2026-11-23 \
  --spring.cloud.task.single-instance-enabled=true
~~~

Vì đối số dòng lệnh Spring Boot có thể ghi vào `TaskExecution.arguments`, **không truyền secret** bằng `--spring.datasource.password=...` hay `--token=...`. Dùng biến môi trường, secret store và phân quyền repository.

**Ưu tiên cấu hình cố định bằng profile/deployment** cho những thuộc tính mang tính hạ tầng (schema prefix, quyền khởi tạo bảng, repository datasource). Để mỗi lần gọi tùy tiện đổi `table-prefix` hoặc `initialize-enabled` rất dễ tạo lệch schema giữa các lượt.

### 9.3. Tầng cấu hình và phạm vi tác động

Trong Spring Boot, `application.yml`, `application-{profile}.yml`, biến môi trường và đối số command-line có thể cùng cung cấp giá trị một thuộc tính; độ ưu tiên phụ thuộc quy tắc **externalized configuration** của phiên bản Spring Boot. Đối số command-line thường có độ ưu tiên cao hơn cấu hình đóng gói, nhưng hãy kiểm chứng khi có Config Server, Kubernetes hoặc custom PropertySource.

| Nơi đặt | Ví dụ | Phạm vi thường gặp |
| --- | --- | --- |
| `application.yml` | `spring.cloud.task.closecontext-enabled=true` | Mặc định cho artifact |
| `application-prod.yml` | `spring.cloud.task.initialize-enabled=false` | Khi profile `prod` được kích hoạt |
| Biến môi trường | `SPRING_CLOUD_TASK_TABLE_PREFIX=TASK_` | Tiến trình/container có biến đó |
| Đối số ứng dụng | `--spring.cloud.task.external-execution-id=run-001` | Một lần khởi chạy |
| Deployment/launcher | CronJob schedule, retries, backoff | Lịch và chính sách của hệ điều phối |

Các thuộc tính đọc khi **startup** không bảo đảm cập nhật động giữa chừng nếu nguồn cấu hình thay đổi. Muốn thay đổi hành vi cho lượt tiếp theo, cập nhật cấu hình triển khai rồi khởi chạy tiến trình mới.

## 10. Vấn đề thực tế và cách chẩn đoán

| Triệu chứng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Không có hàng trong `TASK_EXECUTION` | Task auto configuration đã bật? Context khởi tạo tới lifecycle chưa? | Kiểm tra datasource, schema, startup logs và cờ auto configuration |
| Lỗi “table does not exist” | `table-prefix` có khớp DDL? `initialize-enabled` đã tắt? | Tạo migration đúng prefix, kiểm tra schema/search path và quyền DB |
| Hai tiến trình cùng tên chạy song song | `single-instance-enabled` mặc định false hoặc thiếu integration | Bật đúng cơ chế và dependency; kiểm tra storage khóa |
| Job Batch báo `FAILED` nhưng launcher thấy exit code 0 | `fail-on-job-failure` và runner tích hợp | Bật cơ chế phù hợp, kiểm thử mã thoát thật |
| Task không thoát sau khi runner hoàn thành | Thread pool/bean còn thread sống | Cân nhắc `closecontext-enabled=true`, bảo đảm đợi công việc async |
| Task mất lịch sử sau khi khởi động lại | Dùng H2 in-memory hoặc đổi `table-prefix` | Dùng CSDL bền vững, xác nhận cùng repository |
| Truy vết không nối được với Job/K8s | Thiếu external/parent ID hoặc liên kết Task–Batch | Truyền ID hợp lệ, bật listener đúng phiên bản, đối chiếu bảng liên kết |
| Không thấy metric hay event | Thiếu Actuator/Micrometer/registry hoặc Stream/binder | Xác minh dependency, exporter, cờ feature và quyền truy cập |
| Bị chặn khi chạy hai ngày báo cáo khác nhau | Single-instance khóa theo **task name** | Thiết kế lại phạm vi chạy hoặc dùng business-key lock |

**Nguyên tắc tìm lỗi:** xác định tầng chịu trách nhiệm trước. Vấn đề lịch chạy thuộc bộ điều phối, lỗi kết nối CSDL thường thuộc DataSource/migration, lỗi metadata thuộc TaskRepository, còn sai kết quả nhập dữ liệu thuộc mã nghiệp vụ. Đổi bừa các cờ `spring.cloud.task.*` khó giải quyết đúng nguyên nhân.

## 11. Kiểm tra trước khi đưa cấu hình vào production

- **Phiên bản:** BOM Spring Cloud Task có tương thích Spring Boot, Java và Spring Batch? Các khóa dự định dùng có tồn tại trong metadata của đúng phiên bản?
- **Repository:** schema và `table-prefix` đã khớp, có migration và quyền SQL tối thiểu? Lịch sử TaskExecution có được giữ đủ lâu để truy vết?
- **Vòng đời:** runner có đợi việc async hoàn thành? Tiến trình có kết thúc với mã thoát có ý nghĩa?
- **Định danh:** nếu dùng `executionid`, bản ghi tạo trước có tồn tại trong đúng repository? external ID và parent ID có đúng workflow?
- **Đồng thời:** muốn khóa toàn bộ task name hay chỉ một business key? Có xử lý crash/timeout/khôi phục khóa?
- **Batch:** Batch Job thất bại có làm launcher phát hiện lỗi? Có phân biệt TaskExecution và JobExecution?
- **Quan sát:** logs, metrics, event và lỗi có truy vết được nhưng không để lộ thông tin nhạy cảm?
- **Triển khai:** thay đổi flag có được rà soát bằng startup logs và một lần chạy thử với dữ liệu an toàn?

### Bài tập tự kiểm tra

Thiết kế cấu hình cho một tác vụ `monthly-invoice-task` tạo hóa đơn hàng tháng:

1. Cấu hình TaskRepository dùng PostgreSQL, prefix mặc định; schema được quản lý bởi migration, không tự khởi tạo lúc task bắt đầu.
2. Đặt tên để mọi TaskExecution của ứng dụng có thể tra cứu theo `monthly-invoice-task`.
3. Bảo đảm task kết thúc tiến trình sau khi xuất xong tệp và cập nhật trạng thái.
4. Giả sử tác vụ có thể được gọi từ API lẫn CronJob: xác định có cần single-instance theo tên hay nên dùng khóa `(tenant, month)` của nghiệp vụ.
5. Nếu tác vụ chạy Spring Batch, cấu hình để Batch Job thất bại phản ánh thành mã thoát lỗi.
6. Khi Task được launch từ workflow có `workflow-run-id`, chọn thuộc tính để lưu mã này mà không can thiệp TaskExecution ID nội bộ.
7. Giải thích vì sao đổi `spring.cloud.task.table-prefix` không tự đổi các bảng đã tồn tại.

Đáp án gợi ý: dùng `spring.datasource.*`, `spring.cloud.task.initialize-enabled=false`, `spring.application.name`, `spring.cloud.task.closecontext-enabled=true`, chọn single-instance hay business-key lock theo phạm vi, bật `spring.cloud.task.batch.fail-on-job-failure` nếu có tích hợp Batch và dùng `spring.cloud.task.external-execution-id` để truy vết workflow.

## 12. Các điểm cần nhớ

1. `spring.cloud.task.*` chủ yếu điều chỉnh **hạ tầng và lifecycle Spring Cloud Task**; không điều khiển bộ lập lịch hay xử lý nghiệp vụ.
2. `table-prefix` và `initialize-enabled` ảnh hưởng **schema metadata**; `spring.datasource.*` và `TaskConfigurer` quyết định kết nối repository.
3. `closecontext-enabled` ảnh hưởng **đóng context**; công việc bất đồng bộ phải hoàn tất trước khi runner kết thúc.
4. `executionid`, `external-execution-id`, `parent-execution-id` có **ba vai trò khác nhau**: ID lần chạy hiện tại, ID hệ thống ngoài và ID tác vụ cha.
5. `single-instance-enabled` giới hạn chạy chồng lấn theo **task name**. Chống trùng theo khóa nghiệp vụ cần cơ chế riêng.
6. Các thuộc tính `spring.cloud.task.batch.*`, `events.*` và `observation.*` chỉ có ý nghĩa đầy đủ khi đúng **module tích hợp và dependencies** đã được cấu hình.
7. Với mọi thay đổi, kiểm tra **version, phạm vi tác động, giá trị mặc định, quy trình migration và cách xác minh bằng một lần chạy thật**.

### Nguồn tham khảo chính thức

- [Spring Cloud Task — Features và Configuration](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Tích hợp Spring Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Tích hợp Spring Cloud Stream](https://docs.spring.io/spring-cloud-task/reference/stream.html)
- [Spring Cloud — Configuration Properties (tra cứu theo phiên bản)](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
