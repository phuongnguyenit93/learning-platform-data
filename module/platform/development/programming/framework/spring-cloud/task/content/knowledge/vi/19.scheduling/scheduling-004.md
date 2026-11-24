# Kubernetes CronJob và tham số của mỗi lần chạy

**Spring Cloud Task** dùng để xây dựng ứng dụng Spring Boot có thời gian chạy hữu hạn: tiến trình khởi động, nhận tham số, xử lý nghiệp vụ, ghi `TaskExecution` vào `TaskRepository`, rồi kết thúc. Khi muốn chạy tác vụ hằng ngày, hằng giờ hay định kỳ trong Kubernetes, ta có thể dùng **CronJob** làm bộ lập lịch cho các **Kubernetes Job** tạo Pod chạy ứng dụng.

Bài thuộc chương **Lịch chạy**. Trọng tâm là **CronJob quyết định thời điểm yêu cầu thực thi, còn tham số của từng lần chạy quyết định dữ liệu nào được xử lý**. Ví dụ xuyên suốt là tác vụ `daily-invoice-report-task` tạo báo cáo hóa đơn cho *ngày nghiệp vụ hôm trước* theo múi giờ `Asia/Ho_Chi_Minh`. Ta sẽ cấu hình CronJob, truyền và xác thực tham số, xử lý retry/chạy bù, chống trùng lặp và đối chiếu kết quả Kubernetes với Spring Cloud Task.

> **Nguyên tắc:** Kubernetes CronJob không tự ghi `TaskExecution`; Spring Cloud Task không tự lập lịch Kubernetes. CronJob tạo Job/Pod, tiến trình Java bên trong Pod mới ghi metadata Task và xử lý nghiệp vụ.

## 1. Quan hệ CronJob, Job, Pod và TaskExecution

~~~mermaid
flowchart TD
  C["CronJob: 02:00 mỗi ngày"] --> J1["Kubernetes Job kỳ A"]
  C --> J2["Kubernetes Job kỳ B"]
  J1 --> P1["Pod thử lần 1"]
  J1 --> P2["Pod retry khi thất bại"]
  J2 --> P3["Pod kỳ B"]
  P1 --> T1["Spring Cloud Task / TaskExecution #1"]
  P2 --> T2["Spring Cloud Task / TaskExecution #2"]
  P3 --> T3["Spring Cloud Task / TaskExecution #3"]
  T1 --> R[("TaskRepository")]
  T2 --> R
  T3 --> R
  T1 --> D[("Dữ liệu nghiệp vụ")]
  T2 --> D
  T3 --> D
~~~

| Thành phần | Trách nhiệm chính | Không nên nhầm với |
| --- | --- | --- |
| **CronJob** | Diễn giải lịch và tạo Kubernetes Job theo mẫu | Một lần chạy nghiệp vụ duy nhất |
| **Kubernetes Job** | Theo dõi hoàn thành, Pod retry, thời hạn Job | `JobExecution` của Spring Batch |
| **Pod/Container** | Chạy image Java, nhận `args` và `env`, ghi log | Một kỳ dữ liệu duy nhất |
| **Spring Cloud Task** | Ghi `TaskExecution`: tên, thời gian, đối số, mã thoát | Bộ lập lịch hoặc khóa chống trùng |
| **Spring Batch** (nếu dùng) | `JobInstance`, `JobExecution`, `StepExecution`, checkpoint | Kubernetes Job |
| **Nghiệp vụ** | Chọn `businessDate`, tenant, kết quả, idempotency | TaskExecution ID |

Một Kubernetes Job có thể **thử nhiều Pod** nếu lần thử trước lỗi. Mỗi tiến trình Task khởi động thành công đủ xa thường có **TaskExecution ID riêng**. Ngược lại, Pod lỗi từ bước pull image hoặc khởi động context có thể **không để lại** TaskExecution. Vì vậy, không giả định quan hệ luôn là “một lịch = một Job = một TaskExecution”.

### 1.1. Vì sao không dùng @Scheduled trong Task?

`@Scheduled` của Spring thường chạy bên trong một ứng dụng **sống dài hạn** để chờ tới các mốc lịch. Kiến trúc Spring Cloud Task dùng CronJob sẽ tạo **tiến trình mới, chạy đúng một công việc, rồi thoát**. Không cần vừa bật `@Scheduled` trong ứng dụng vừa để CronJob khởi chạy, vì dễ tạo hai tầng lịch không cần thiết.

## 2. Manifest CronJob mẫu

Manifest sau minh họa task chạy lúc **02:00 mỗi ngày tại Việt Nam**. Giả định namespace `batch-jobs`, ServiceAccount `invoice-task`, Secret `invoice-task-db`, image và bảng TaskRepository đều đã được chuẩn bị.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-invoice-report
  namespace: batch-jobs
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 1800
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  suspend: false
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600
      template:
        spec:
          serviceAccountName: invoice-task
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example.com/batch/daily-invoice-report-task:1.0.0
              imagePullPolicy: IfNotPresent
              args:
                - "--business-zone=Asia/Ho_Chi_Minh"
              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: jdbc-url
                - name: TASK_DB_USER
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: password
              resources:
                requests:
                  cpu: "250m"
                  memory: "512Mi"
                limits:
                  memory: "1Gi"
~~~

Đây là **ví dụ**, không phải tài nguyên đã triển khai. Image cần `ENTRYPOINT` chạy Spring Boot và chuyển các phần tử `args` vào `main(String[] args)`. Nếu image không có entrypoint phù hợp, phải khai báo `command` và `args` tương ứng. Kubernetes `args` ghi đè tham số `CMD` của image, không nhất thiết thay toàn bộ lệnh.

### 2.1. Ý nghĩa các trường quan trọng

| Trường | Tác dụng | Rủi ro cần chú ý |
| --- | --- | --- |
| `schedule: "0 2 * * *"` | Cron **5 trường**: phút, giờ, ngày tháng, tháng, thứ | Không phải Cron 6 trường của một số thư viện Java |
| `timeZone` | Múi giờ để Kubernetes diễn giải lịch | Dùng tên IANA; không nhúng `TZ` hoặc `CRON_TZ` vào schedule |
| `concurrencyPolicy: Forbid` | Không chạy chồng các Job của **cùng CronJob** | Có thể bỏ qua một kỳ nếu Job trước kéo dài |
| `startingDeadlineSeconds: 1800` | Cửa sổ cho phép bắt đầu muộn tối đa 30 phút | Không phải giới hạn runtime của Job |
| `backoffLimit: 2` | Số lần thử lại tối đa theo cơ chế Job controller | Retry có thể tạo TaskExecution mới |
| `activeDeadlineSeconds: 3600` | Giới hạn thời gian Job hoạt động | Bị kill trước khi Task ghi thông tin kết thúc |
| `restartPolicy: Never` | Pod lỗi không restart container tại chính Pod đó | Job controller vẫn có thể tạo Pod thay thế |
| `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | Số Job cũ được giữ trong Kubernetes | **Không** xóa dữ liệu TaskRepository |
| `args` | Đối số ứng dụng nhận ở startup | Mẫu mặc định là **cố định qua các lần chạy** |
| `env` | Cấu hình của container/tiến trình | Không tự lưu vào `TaskExecution.arguments` |

`timeZone` trở thành trường ổn định từ **Kubernetes v1.27**. Nếu cluster cũ hơn, kiểm tra hỗ trợ API theo phiên bản. Thời điểm kích hoạt được tính trên control plane, không phụ thuộc múi giờ laptop đang gọi `kubectl`.

### 2.2. Cấu hình Spring Boot tương ứng

Trong image, ứng dụng có thể dùng:

~~~yaml
spring:
  application:
    name: daily-invoice-report-task
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

Cờ `initialize-enabled=false` giả định bảng TaskRepository đã được tạo bằng migration phù hợp với DBMS và phiên bản Spring Cloud Task. Cần JDBC driver, quyền CSDL và cấu hình hạ tầng tương ứng. Nếu ứng dụng có nhiều DataSource, phải xác định đúng DataSource của TaskRepository.

## 3. Hiểu “tham số mỗi lần chạy” là gì

Ba nhóm giá trị thường xuất hiện trong một Task:

| Nhóm | Ví dụ | Phạm vi |
| --- | --- | --- |
| **Cấu hình triển khai** | URL CSDL, username, mật khẩu, image, memory | Một deployment/môi trường |
| **Tham số công việc** | `--business-date`, `--tenant-id`, `--source-id`, `--report-version` | Một kỳ dữ liệu logic |
| **ID lần thử kỹ thuật** | Kubernetes Job UID, Pod UID, TaskExecution ID | Một Job/Pod/tiến trình thực tế |

Ví dụ hai ngày báo cáo:

~~~text
Lần logic A: tenantId=acme, businessDate=2026-11-23
Lần logic B: tenantId=acme, businessDate=2026-11-24
~~~

Nếu lần logic A retry qua ba Pod, **ngày nghiệp vụ vẫn phải là 2026-11-23** ở cả ba. TaskExecution ID có thể khác nhau nhưng business key phải giữ nguyên.

Đối số command-line được Spring Cloud Task lưu trong `TaskExecution.arguments` qua `TaskRepository`, thường ở `TASK_EXECUTION_PARAMS`. Các giá trị chỉ nằm trong biến môi trường hoặc được ứng dụng **tự tính sau startup** không mặc nhiên xuất hiện trong danh sách arguments đã lưu. Khi cần kiểm toán, lưu ngày nghiệp vụ thực tế vào log có cấu trúc hoặc bảng nghiệp vụ, không đưa secrets vào đối số.

## 4. Bẫy lớn nhất: CronJob không tự cập nhật businessDate

Giả sử viết:

~~~yaml
args:
  - "--business-date=2026-11-23"
~~~

Kubernetes sẽ truyền **nguyên giá trị 2026-11-23 trong mỗi Job** tạo từ template này, đến khi manifest được sửa. Nó **không tự tăng ngày**. Các chuỗi dưới đây cũng không tự được nội suy:

~~~yaml
# Sai nếu kỳ vọng Kubernetes tự tính ngày:
args:
  - "--business-date=${YESTERDAY}"
  - "--business-date={{ yesterday }}"
~~~

CronJob không tự có biến `YESTERDAY`, không chạy shell để thay `{{ yesterday }}`, và việc truyền một phần tử `args` không làm biến thành biểu thức tính ngày. Cú pháp `$(NAME)` chỉ tham chiếu env đã được cung cấp trong ngữ cảnh có hỗ trợ; nó không tính “hôm qua”.

Hai chiến lược chính:

1. **Ứng dụng tự tính** ngày từ một `ZoneId` đã quy ước và đồng hồ lúc chạy. Đơn giản, nhưng nhạy cảm với chạy trễ/retry qua ngày mới.
2. **Bộ điều phối chốt businessDate trước khi tạo Job** rồi truyền giá trị bất biến. Phù hợp hơn với backfill, retry kéo dài hoặc kiểm toán một kỳ dữ liệu.

## 5. Cách A: ứng dụng tự tính ngày khi chạy

Ở lịch 02:00 hằng ngày theo `Asia/Ho_Chi_Minh`, quy tắc phổ biến là **xử lý ngày địa phương hôm trước**. Với mốc chạy 24/11/2026 lúc 02:00, ngày cần xử lý là 23/11/2026.

Ví dụ Spring Boot nhận `--business-date` nếu có; nếu không, tự tính ngày hôm trước theo timezone đã chọn. Dùng `Clock` giúp dễ kiểm thử, tránh phụ thuộc timezone mặc định của container.

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyInvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyInvoiceReportTaskApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    ApplicationRunner runReport(ReportService service, Clock clock) {
        return args -> {
            ZoneId zone = ZoneId.of(
                    option(args, "business-zone", "Asia/Ho_Chi_Minh"));
            String explicit = option(args, "business-date", null);
            LocalDate date = explicit == null
                    ? LocalDate.now(clock.withZone(zone)).minusDays(1)
                    : LocalDate.parse(explicit);

            service.generateFor(date); // Đồng bộ cho đến khi hoàn tất.
        };
    }

    private static String option(
            ApplicationArguments args, String key, String fallback) {
        if (!args.containsOption(key)) {
            return fallback;
        }
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + key + "=value");
        }
        return values.get(0);
    }
}

interface ReportService {
    void generateFor(LocalDate businessDate);
}
~~~

Đoạn mã là **khung minh họa**, cần bean `ReportService`, migration, logic kiểm tra ngày, giao dịch và idempotency. Runner phải đợi công việc hoàn tất. Nếu chỉ submit một Future rồi trả về, Task/Pod có thể kết thúc trong khi xử lý vẫn tiếp diễn.

### 5.1. Giới hạn của cách tính theo đồng hồ Pod

~~~text
Mốc Cron dự kiến:  2026-11-24 02:00
Kỳ cần xử lý:      2026-11-23

Job chạy bù trễ:   2026-11-26 08:00
"Hôm qua" lúc đó:  2026-11-25  ← sai kỳ dự kiến
~~~

Khi Pod bị khởi chạy trễ do lỗi control plane, thiếu tài nguyên hoặc retry qua nửa đêm, `LocalDate.now(...).minusDays(1)` có thể đổi giữa các lần thử của **cùng Job**. Điều này đặc biệt nguy hiểm khi lần thử đầu đã ghi một phần dữ liệu.

Do đó, cách A chỉ phù hợp nếu bạn đã kiểm soát thời gian trễ và chấp nhận/giải quyết được rủi ro đó. Đối với dữ liệu quan trọng, cần **chốt ngày cụ thể** trước khi bắt đầu các lần thử.

## 6. Cách B: chốt ngày rồi truyền vào Job

Phương án mạnh hơn là có một **launcher/bộ điều phối** xác định kỳ nghiệp vụ theo mốc lịch, rồi tạo Kubernetes Job với tham số cố định:

~~~text
scheduledAt  = 2026-11-24T02:00:00+07:00
businessDate = 2026-11-23

args:
  --business-date=2026-11-23
  --business-zone=Asia/Ho_Chi_Minh
~~~

Khi Job đó retry, Pod mới vẫn nhận **cùng Pod template/args** của Job. Không còn phải tính “hôm qua” từ đồng hồ của Pod retry.

~~~mermaid
flowchart LR
  S["Mốc lịch 24/11 02:00 +07"] --> C["Tính businessDate = 23/11"]
  C --> J["Tạo Kubernetes Job với args cố định"]
  J --> P1["Pod thử #1"]
  J --> P2["Pod retry #2"]
  P1 --> B[("Cùng businessKey")]
  P2 --> B
~~~

Một CronJob YAML tĩnh **không tự render** `businessDate` theo từng lịch. Nếu muốn giữ CronJob làm tác nhân khởi phát, có thể cho CronJob chạy một *launcher container* ngắn hạn; launcher lấy mốc lịch, tính businessDate, gọi Kubernetes API để tạo Job nghiệp vụ. Cách này yêu cầu thiết kế RBAC, xử lý launcher chạy trùng và quản lý trạng thái Job. Hệ thống cũng có thể dùng workflow engine hoặc lịch ngoài Kubernetes để tạo Job với ngày tường minh.

### 6.1. Annotation mốc lịch từ Kubernetes v1.32

Từ **Kubernetes v1.32**, CronJob controller gắn annotation vào Job tạo từ CronJob:

~~~text
batch.kubernetes.io/cronjob-scheduled-timestamp
~~~

Giá trị là mốc lịch dự kiến ở định dạng RFC3339, ví dụ `2026-11-24T02:00:00+07:00`. Đây là **scheduled time**, có ích khi Job được tạo muộn. Có thể chuyển đổi:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;

OffsetDateTime scheduledAt =
        OffsetDateTime.parse("2026-11-24T02:00:00+07:00");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate businessDate =
        scheduledAt.atZoneSameInstant(zone).toLocalDate().minusDays(1);
~~~

**Lưu ý:** annotation ở **metadata của Kubernetes Job**, không tự xuất hiện như một env variable có sẵn trong Pod. Để ứng dụng đọc nó cần cơ chế truyền cụ thể: launcher truy vấn Job API, một controller/injector hoặc thành phần bổ sung với RBAC tối thiểu. Đừng giả định container có biến `SCHEDULED_AT` nếu chưa cấu hình.

Nếu chạy backfill thủ công, vẫn cần chọn `scheduledAt` hoặc `businessDate` tường minh. Mốc lịch của Job tạo thủ công không nhất thiết có annotation tương ứng với kỳ nghiệp vụ mà bạn muốn xử lý.

## 7. Múi giờ và ranh giới dữ liệu

~~~yaml
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
~~~

CronJob diễn giải 02:00 theo múi giờ IANA đã chỉ định. Cùng lúc đó, code nghiệp vụ phải xác định **ngày dữ liệu** theo múi giờ tương ứng; không nên tin timezone mặc định của JVM sẽ giống timezone của Kubernetes CronJob.

Với dữ liệu lưu timestamp UTC, nên dùng khoảng ngày **nửa mở** `[start, end)`:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.parse("2026-11-23");

Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
// WHERE occurred_at >= start AND occurred_at < end
~~~

`Instant` cần import từ `java.time.Instant`. Với timezone có DST, một ngày địa phương có thể dài **23 hoặc 25 giờ**; không thay `end` bằng `start.plus(Duration.ofHours(24))`. Ở các múi giờ chuyển DST, một thời điểm trên lịch Cron có thể không tồn tại hoặc xuất hiện hai lần; cần chính sách xác định kỳ và xử lý lịch bị lỡ.

### 7.1. startingDeadlineSeconds không phải timeout của Task

`startingDeadlineSeconds` là thời gian tối đa cho phép **bắt đầu muộn** sau mốc lịch. Nếu vượt quá, một kỳ có thể bị bỏ qua; nó **không giới hạn thời gian thực thi** Job. Giới hạn thời gian Job nằm ở `activeDeadlineSeconds`.

Kubernetes docs lưu ý khi đặt `startingDeadlineSeconds` dưới **10 giây**, CronJob có thể không được lên lịch vì controller kiểm tra lịch theo chu kỳ. Ngoài ra, nhiều mốc bị lỡ không đồng nghĩa controller tự chạy bù **đầy đủ**; cần cơ chế kiểm kê kỳ thiếu và backfill riêng.

## 8. Chạy chồng: Allow, Forbid, Replace

| `concurrencyPolicy` | Khi tới mốc mới mà Job cũ còn chạy | Điều cần chuẩn bị |
| --- | --- | --- |
| **Allow** (mặc định) | Cho phép Job mới chạy chồng | Khóa nghiệp vụ/idempotency khi cùng dữ liệu |
| **Forbid** | Bỏ qua lần chạy mới của **cùng CronJob** trong lúc Job cũ đang chạy | Giám sát kỳ bị lỡ; backfill |
| **Replace** | Hủy Job đang chạy để thay bằng Job mới | Khôi phục khi Job bị dừng đột ngột, tránh ghi dở |

Phạm vi `Forbid` chỉ bao gồm **các Job do cùng CronJob tạo**. Một CronJob thứ hai, Job tạo thủ công hoặc Task được launch qua API vẫn có thể xử lý cùng dữ liệu. Nếu cần giới hạn ở nhiều nguồn khởi chạy, phải dùng cơ chế khóa ngoài CronJob.

Spring Cloud Task có tùy chọn `single-instance-enabled` khi được cấu hình với backend khóa phù hợp; nó giới hạn theo **tên Task**, không theo `(tenant, businessDate)`. Nếu cần cho các tenant khác nhau chạy song song nhưng chặn cùng tenant/ngày, hãy dùng **unique constraint hoặc distributed business-key lock**.

**CronJob không đảm bảo exactly-once.** Theo tài liệu Kubernetes, trong một số hoàn cảnh có thể tạo hai Job cho một mốc hoặc không tạo Job; vì vậy ứng dụng cần **idempotent**.

## 9. Retry, mã thoát và TaskExecution

Với:

~~~yaml
jobTemplate:
  spec:
    backoffLimit: 2
    template:
      spec:
        restartPolicy: Never
~~~

Nếu container thoát lỗi, Job controller có thể tạo Pod để thử lại. `restartPolicy: Never` khiến Pod lỗi không restart container tại cùng Pod; Job controller quản lý retry theo `backoffLimit` và điều kiện khác. Với `restartPolicy: OnFailure`, container có thể restart trong cùng Pod.

Ví dụ minh họa:

~~~text
Kubernetes Job của kỳ báo cáo 2026-11-23
  Pod attempt #1 → TaskExecution 4101, exitCode=1
  Pod attempt #2 → TaskExecution 4102, exitCode=1
  Pod attempt #3 → TaskExecution 4103, exitCode=0
~~~

Đây **không phải cam kết chính xác ba Pod hoặc TaskExecution** khi `backoffLimit=2`: cách tính retry có nhiều điều kiện, và một Pod có thể lỗi trước khi Spring Cloud Task ghi TaskExecution.

### 9.1. Truyền lỗi ra khỏi ứng dụng

Không nên bắt exception rồi chỉ ghi log:

~~~java
try {
    service.generateFor(businessDate);
} catch (Exception ex) {
    log.error("Could not generate report", ex);
    // Sai nếu sau đó runner trả về bình thường.
}
~~~

Nếu runner trả về bình thường, process có thể thoát mã `0`, khiến Kubernetes đánh dấu Job `Complete` dù báo cáo sai. Cần để exception lan ra hoặc ánh xạ kết quả sang mã thoát khác `0`.

Khi chạy **Spring Batch** bên trong Task, cần kiểm tra `JobExecution` thất bại có thật sự khiến Task/process trả mã khác `0`. Có thể dùng `spring.cloud.task.batch.fail-on-job-failure=true` trên phiên bản tích hợp hỗ trợ, hoặc tự kiểm tra `JobExecution` trong launcher.

### 9.2. Pod bị kill

Nếu Pod bị kill do OOM, node failure hoặc `activeDeadlineSeconds`, listener kết thúc của Spring Cloud Task có thể không chạy. Một dòng `TASK_EXECUTION.END_TIME` trống không chứng minh tiến trình vẫn còn sống. Phải so sánh với Kubernetes Job/Pod và log hệ thống.

## 10. Business key và idempotency qua các lần thử

Một báo cáo có thể được kích hoạt bởi CronJob, chạy thủ công, retry hoặc backfill. Tất cả phải chia sẻ một khóa logic:

~~~text
businessKey = (tenantId, businessDate, reportVersion)
~~~

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE report_run (
    tenant_id       varchar(100) NOT NULL,
    business_date   date NOT NULL,
    report_version  integer NOT NULL,
    status          varchar(30) NOT NULL,
    artifact_uri    text,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

Tạo claim mới theo business key:

~~~sql
INSERT INTO report_run
    (tenant_id, business_date, report_version, status)
VALUES
    (:tenant_id, :business_date, :report_version, 'RUNNING')
ON CONFLICT (tenant_id, business_date, report_version)
DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` chỉ là **bước đầu**. Nếu hàng đã tồn tại, ứng dụng phải kiểm tra `status`: hoàn tất thì bỏ qua, đang chạy thì từ chối/chờ, thất bại thì có quy tắc tiếp quản an toàn. Khi có lease hoặc timeout, cần owner token/fencing để tiến trình cũ không tiếp tục ghi sau khi mất quyền sở hữu.

Với tác dụng phụ bên ngoài DB như gửi email, phát sự kiện hoặc ghi tệp vào object storage, dùng **idempotency key**, tên artifact bất biến, outbox hoặc cơ chế tương đương. Unique constraint trên bảng report không tự bảo đảm một email sẽ không được gửi hai lần.

| ID | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| Kubernetes Job UID | UID do API cấp | Theo dõi Job kỹ thuật |
| Pod UID | UID của một Pod | Điều tra lần thử/container |
| TaskExecution ID | `4103` | Lịch sử Spring Cloud Task |
| Spring Batch JobInstance | Job name + identifying JobParameters | Restart/checkpoint Batch |
| Business key | `acme, 2026-11-23, v1` | Bảo vệ kết quả dữ liệu logic |

Không dùng TaskExecution ID để chống trùng: mỗi lần thử kỹ thuật có thể có ID mới nhưng **cùng một business key**.

## 11. Chạy thủ công và backfill

Lệnh Kubernetes tạo Job từ CronJob:

~~~bash
kubectl create job \
  --from=cronjob/daily-invoice-report \
  manual-invoice-report \
  -n batch-jobs
~~~

Lệnh này **sao chép mẫu Job**, bao gồm `args` hiện tại. Nó **không** tự điền một ngày mới dựa trên tên Job, cũng không tự hiểu Job thủ công đang xử lý kỳ nào.

Khi cần backfill một ngày cụ thể, tạo **Job manifest riêng** hoặc để launcher tạo Job với `--business-date` cố định:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: manual-invoice-report-20261123
  namespace: batch-jobs
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch/daily-invoice-report-task:1.0.0
          args:
            - "--business-date=2026-11-23"
            - "--business-zone=Asia/Ho_Chi_Minh"
          envFrom:
            - secretRef:
                name: invoice-task-runtime
~~~

Ví dụ cần Secret `invoice-task-runtime` chứa đúng các biến `TASK_DB_*`, image, quyền pull và những cấu hình triển khai khác. Đừng đưa password vào `args` hay commit Secret dạng rõ. Job được tạo thủ công nên có **quy trình phê duyệt/đối soát** để tránh phát hành trùng một ngày đã hoàn tất.

## 12. Quan sát ba nguồn dữ liệu

### 12.1. Quan sát Kubernetes

~~~bash
kubectl get cronjobs -n batch-jobs
kubectl describe cronjob daily-invoice-report -n batch-jobs
kubectl get jobs -n batch-jobs
kubectl describe job ACTUAL_JOB_NAME -n batch-jobs
kubectl get pods -n batch-jobs \
  -l batch.kubernetes.io/job-name=ACTUAL_JOB_NAME
kubectl logs -n batch-jobs job/ACTUAL_JOB_NAME
kubectl get events -n batch-jobs --sort-by=.lastTimestamp
~~~

Thay `ACTUAL_JOB_NAME` bằng tên Kubernetes Job thực tế. Nếu có nhiều Pod do retry, cần xem log của **từng Pod**, không chỉ một lệnh `kubectl logs job/...`. Nếu Job/Pod đã bị dọn, dùng hệ thống log tập trung.

### 12.2. Quan sát TaskRepository

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-invoice-report-task'
ORDER BY START_TIME DESC;
~~~

TaskExecution lưu trạng thái ứng dụng, không phải trạng thái controller Kubernetes. Để nối hai lớp, gắn correlation ID không nhạy cảm như **Job name/UID hoặc Pod name** trong log hoặc metadata nghiệp vụ. Pod name không tự hiện dưới biến môi trường `POD_NAME`; có thể cấu hình **Downward API**:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

Đây là mảnh cấu hình thêm vào container, không phải cả manifest CronJob. Pod name **không phải business key**, vì các lần retry có thể tạo Pod mới.

### 12.3. Phân loại sự cố

| Triệu chứng | Nơi cần kiểm tra |
| --- | --- |
| CronJob không tạo Job | `suspend`, schedule/timeZone, deadline, controller events |
| Job tồn tại nhưng không có Pod chạy | Scheduler, quotas, image pull, RBAC/admission |
| Pod chạy nhưng TaskExecution không xuất hiện | Ứng dụng chưa startup tới lifecycle, datasource/schema sai |
| Job `Complete` nhưng dữ liệu thiếu | Runner nuốt exception, thiếu đối soát đầu ra |
| `END_TIME` trống | Tiến trình đang chạy hoặc đã chết đột ngột |
| Hai lần xử lý cùng ngày | Retry, hai CronJob, Job thủ công, thiếu khóa nghiệp vụ |
| Sai ngày sau retry | Ứng dụng tính “hôm qua” theo giờ Pod thay vì giá trị chốt |
| `Forbid` làm thiếu kỳ | Job trước chạy lâu, mốc mới bị bỏ lỡ |
| Lịch lệch giờ | `timeZone`, DST, timezone nội bộ app không nhất quán |
| Có Batch Job `FAILED` nhưng Pod `Complete` | Chưa phản ánh Batch failure thành mã thoát tiến trình |

`successfulJobsHistoryLimit` và `failedJobsHistoryLimit` chỉ điều khiển **Job Kubernetes đã kết thúc** được giữ lại. Nếu dùng `ttlSecondsAfterFinished`, Kubernetes còn có thể dọn Job/Pod theo TTL. Cả hai **không thay thế chính sách retention** trong TaskRepository hoặc Spring Batch JobRepository.

## 13. Tạm dừng, chỉnh lịch và chạy bù

Để ngăn tạo Job theo các mốc tiếp theo:

~~~yaml
spec:
  suspend: true
~~~

`suspend: true` **không dừng** Job đã bắt đầu. Khi bật lịch trở lại, các mốc bị lỡ có thể ảnh hưởng tới cách controller bắt kịp, tùy `startingDeadlineSeconds` và quy tắc missed schedules. Không giả định mọi ngày bị lỡ đều sẽ chạy bù; cần một bảng đối soát **ngày nghiệp vụ đã xử lý**.

Chỉnh `jobTemplate` (image, args, env) chỉ áp dụng cho **Job được tạo sau khi cập nhật**. Các Job/Pod đã chạy không bị thay đổi ngược. Hãy dùng version image cố định, quản lý lịch và tham số qua thay đổi có kiểm soát.

Khi đổi lịch từ 02:00 sang 01:00, đừng âm thầm đổi quy tắc ngày báo cáo. Lịch là **khi nào chạy**; businessDate là **dữ liệu nào thuộc lần chạy**.

## 14. Bài tập thực hành

Giả sử hệ thống có hai tác vụ: `orders-import-task` nhập đơn hàng lúc 01:30 và `daily-invoice-report-task` tạo báo cáo lúc 02:00 theo `Asia/Ho_Chi_Minh`.

1. Viết hai CronJob, chọn `concurrencyPolicy`, deadline, retry và giới hạn tài nguyên. Giải thích vì sao `Forbid` của CronJob báo cáo không chặn Job nhập đơn hàng.
2. Truyền DB credentials qua Secret, không qua command-line arguments.
3. Dùng `Clock` cố định để kiểm tra công thức “ngày hôm trước” với mốc 24/11/2026; sau đó mô phỏng Job bắt đầu trễ vào 26/11/2026.
4. Thiết kế launcher truyền `--business-date=2026-11-23` cho một Job; thử retry sau nửa đêm và xác nhận các Pod cùng nhận ngày.
5. Giải thích annotation `batch.kubernetes.io/cronjob-scheduled-timestamp` và cách đưa giá trị vào app **mà không giả định nó tự có trong Pod env**.
6. Cho một Pod trả exit code khác `0`, xem `kubectl get jobs/pods` và đối chiếu TaskExecution. Thử tình huống tiến trình bị kill.
7. Dùng unique key `(tenantId, businessDate, reportVersion)` để bảo vệ phát hành trùng khi Job bị chạy lại thủ công.
8. Tạm dừng lịch, cho qua hai mốc, mở lại và xác định các ngày còn thiếu cần backfill bằng Job manifest riêng.

**Tiêu chí đạt:** giải thích đúng **CronJob → Kubernetes Job → Pod → TaskExecution**, nhận biết `args` của CronJob là tĩnh, phân biệt *scheduled time* với *actual start time*, và bảo toàn businessDate khi retry/chạy bù.

## 15. Kết luận

- CronJob **lập lịch**, Kubernetes Job **quản lý Pod/retry**, Spring Cloud Task **theo dõi tiến trình**, còn code nghiệp vụ **quản lý kết quả và business key**.
- `schedule` là Cron 5 trường; `timeZone` quy định thời gian lên lịch. Múi giờ JVM không thay thế `timeZone` của CronJob.
- `args` trong `jobTemplate` **không tự tính giá trị cho mỗi lần chạy**. Đừng hardcode một ngày rồi kỳ vọng Kubernetes tăng ngày.
- Tính `LocalDate.now().minusDays(1)` ở Pod đơn giản nhưng **không ổn định khi retry hoặc chạy bù qua nhiều ngày**; giải pháp đáng tin cậy là truyền businessDate đã chốt.
- Kubernetes v1.32+ cung cấp annotation scheduled timestamp trên Job, nhưng ứng dụng phải có cơ chế đọc/truyền nó.
- `Forbid`, `Allow`, `Replace` chỉ điều chỉnh mức chồng lấn **của một CronJob**, không đảm bảo exactly-once.
- `startingDeadlineSeconds` giới hạn **trễ khởi chạy**, `activeDeadlineSeconds` giới hạn **thời gian Job**, `backoffLimit` liên quan **retry**.
- Một Job có thể tương ứng nhiều Pod/TaskExecution. **TaskExecution ID không phải khóa nghiệp vụ**; cần idempotency.
- Khi điều tra, xem đồng thời **Kubernetes Job/Pod, TaskRepository và bảng kết quả nghiệp vụ**; quản lý riêng retention, secrets và quy trình backfill.

### Tài liệu tham khảo

- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes API — CronJobSpec](https://kubernetes.io/docs/reference/kubernetes-api/batch/cron-job-v1/)
- [Kubernetes — Well-Known Labels and Annotations](https://kubernetes.io/docs/reference/labels-annotations-taints/)
- [Spring Cloud Task — Features và TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Tích hợp Spring Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html)
