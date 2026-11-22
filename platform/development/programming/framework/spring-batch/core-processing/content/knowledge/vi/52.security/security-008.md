# Phân quyền launch và stop Job trong Spring Batch

Trong ứng dụng Spring Batch, việc **khởi chạy Job** (*launch*) và **yêu cầu dừng Job đang chạy** (*stop*) là các thao tác vận hành có ảnh hưởng trực tiếp đến dữ liệu, tài nguyên và tính liên tục của quy trình nghiệp vụ. Một người có quyền xem trạng thái xử lý đơn hàng không nhất thiết được quyền chạy lại Job tính phí; người được phép khởi chạy Job báo cáo cũng không mặc nhiên được phép dừng Job đối soát tài chính đang xử lý.

Bài học thuộc nhóm **Security** trong **Spring Batch Core Processing**, tập trung vào việc thiết kế và thực thi phân quyền cho các thao tác điều khiển Job: ai được **launch**, ai được **stop**, trên Job hay JobExecution nào, qua những đường gọi nào, và cách ghi nhận/kiểm thử quyết định đó.

Trọng tâm là **Spring Security ở tầng ứng dụng kết hợp chính sách nghiệp vụ**. `JobRepository`, `JobLauncher` và `JobOperator` quản lý vòng đời Batch, nhưng **không phải cơ chế cấp quyền cho người dùng cuối**. Ứng dụng cần xây dựng lớp bảo vệ bao quanh chúng.

## 1. Rủi ro khi API Batch không có phân quyền

Giả sử ứng dụng có các Job:

- `dailySettlementJob`: đối soát thanh toán cuối ngày.
- `importCatalogJob`: nhập danh mục sản phẩm.
- `customerExportJob`: xuất dữ liệu khách hàng.
- `rebuildSearchIndexJob`: dựng lại chỉ mục tìm kiếm.

Nếu có một API chung:

```http
POST /api/batch/jobs/{jobName}/run
POST /api/batch/executions/{executionId}/stop
```

mà bất kỳ người dùng đăng nhập nào cũng được gọi, kẻ tấn công hoặc người dùng có quyền quá rộng có thể:

1. Khởi chạy Job không thuộc trách nhiệm, gây ghi trùng hoặc ảnh hưởng dữ liệu.
2. Dừng một Job quan trọng trước khi nó hoàn thành.
3. Truyền JobParameters bất thường để đọc/ghi sai ngày, sai tenant, sai file hoặc sai môi trường.
4. Dò các `jobExecutionId` và yêu cầu dừng execution của đơn vị khác.
5. Gọi liên tục để tạo nhiều JobInstance, gây quá tải database, worker pool hoặc hệ thống bên ngoài.
6. Gây khó điều tra vì không có dấu vết ai yêu cầu thao tác và vì sao.

Phân quyền không chỉ là đặt `@PreAuthorize` ở một controller. Cần kiểm soát **danh tính**, **quyền thao tác**, **tài nguyên cụ thể**, **tham số**, **trạng thái vòng đời**, **đường gọi không qua HTTP** và **audit**.

## 2. Phân biệt Job, JobInstance, JobExecution và quyền thao tác

Trong Spring Batch:

- **`Job`** là định nghĩa quy trình, ví dụ `dailySettlementJob`.
- **`JobInstance`** là một đơn vị công việc logic, xác định bởi tên Job cùng **identifying JobParameters**.
- **`JobExecution`** là một lần thực thi cụ thể của JobInstance.
- **`StepExecution`** là một lần thực thi Step thuộc một JobExecution.

```text
Job: dailySettlementJob
│
├── JobInstance #100 (businessDate=2026-11-15)
│   ├── JobExecution #410 -> FAILED
│   └── JobExecution #411 -> COMPLETED (restart)
│
└── JobInstance #101 (businessDate=2026-11-16)
    └── JobExecution #412 -> STARTED
```

Hai thao tác chính có đối tượng cần kiểm tra khác nhau:

| Thao tác | Tài nguyên phải kiểm tra | Ví dụ chính sách |
| --- | --- | --- |
| **Launch** | Tên Job, loại tác vụ, tham số, môi trường và phạm vi dữ liệu sẽ chạy | Người vận hành danh mục được launch `importCatalogJob`, nhưng không được launch Job xuất dữ liệu khách hàng. |
| **Stop** | **JobExecution cụ thể**, JobInstance liên quan, tenant, môi trường và trạng thái hiện tại | Chỉ người có quyền điều hành đối soát được yêu cầu stop execution `#412`. |
| View status | JobExecution và metadata có thể chứa thông tin nhạy cảm | Người xem chỉ nhìn Job thuộc dự án/tenant của mình. |
| Restart | Execution đã lỗi/dừng, khả năng restart, tác động ghi dữ liệu lại | Có thể yêu cầu quyền riêng `BATCH_RESTART` thay vì mặc nhiên kế thừa quyền launch. |

**Không dùng một boolean chung `isBatchAdmin` cho mọi thao tác** nếu nghiệp vụ cần phân quyền tinh hơn. Quyền được phép **xem**, **khởi chạy**, **dừng** và **restart** là các năng lực khác nhau.

## 3. Authentication khác authorization

Hai bước có chức năng riêng:

- **Authentication – xác thực:** người gọi là ai? Ví dụ nhân viên vận hành đăng nhập qua Identity Provider, hoặc dịch vụ scheduler có danh tính máy.
- **Authorization – phân quyền:** danh tính đó có được làm **hành động này** trên **đối tượng này** trong **ngữ cảnh này** không?

```text
Client / Scheduler
       |
       v
[Authentication]
  JWT / mTLS / session / workload identity
       |
       v
[Authorization]
  Action = BATCH_LAUNCH hoặc BATCH_STOP
  Resource = jobName / jobExecutionId
  Context = tenant, environment, data scope, approval
       |
       +-- DENY --> HTTP 403 / internal rejection + audit
       |
       v
[Batch control service]
       |
       +-- Launch --> JobLauncher / JobOperator
       |
       +-- Stop ----> JobOperator
       |
       v
[JobRepository / JobExplorer]
```

`JobLauncher` và `JobOperator` **không tự xác thực một HTTP caller**. Chúng được gọi bởi Java code có quyền truy cập bean/đối tượng. Vì thế phải đặt chính sách ở **tầng service điều phối** hoặc một lớp điều khiển nhất quán, không chỉ dựa vào việc tên method là `start` hay `stop`.

### Quyền chức năng và quyền tài nguyên

Có thể dùng hai tầng:

1. **RBAC / scopes – quyền chức năng:** người gọi có `batch.launch`, `batch.stop`, `batch.read`?
2. **ABAC / resource policy – quyền theo đối tượng:** Job nào, tenant nào, business date nào, môi trường nào, JobExecution của ai, có cần phê duyệt không?

Ví dụ người dùng có scope `batch.stop` vẫn **không được dừng mọi JobExecution trong hệ thống** nếu chỉ quản lý tenant `T1`. Quyền chức năng là điều kiện cần, không phải điều kiện đủ.

## 4. Thiết kế ma trận quyền trước khi viết code

Một ma trận minh họa:

| Danh tính / vai trò | Xem | Launch catalog | Launch settlement | Stop catalog | Stop settlement |
| --- | --- | --- | --- | --- | --- |
| Nhân viên hỗ trợ | Job trong tenant được giao | Không | Không | Không | Không |
| Vận hành danh mục | Job danh mục thuộc phạm vi | Có | Không | Có | Không |
| Vận hành đối soát | Job đối soát thuộc phạm vi | Không | Có trong cửa sổ phê duyệt | Không | Có theo quy trình sự cố |
| Scheduler identity | Job được gán theo lịch | Chỉ Job cấu hình cho scheduler | Chỉ theo lịch đã phê duyệt | Không mặc định | Không mặc định |
| Quản trị Batch | Theo chính sách và phân vùng | Có điều kiện | Có điều kiện | Có điều kiện | Có điều kiện |

Ma trận chỉ là ví dụ. Trong hệ thống thực, các điều kiện về doanh nghiệp, dữ liệu nhạy cảm và phê duyệt phải được xác nhận với chủ sở hữu quy trình.

Nên đặt tên quyền theo **hành động** hơn là một vai trò quá tổng quát:

```text
batch.read
batch.launch
batch.stop
batch.restart
batch.manage-schedule
batch.manage-authorization
```

Các quyền như `batch.launch` có thể được chuyển từ claim/scope của Identity Provider sang authority mà Spring Security hiểu. Đừng tin một trường JSON do client tự gửi như `"role": "admin"` làm bằng chứng cấp quyền.

### Nguyên tắc mặc định

- **Deny by default:** một Job không có trong danh sách cho phép không được chạy qua API điều khiển.
- **Least privilege:** mỗi service account chỉ có quyền cần thiết.
- **Separation of duties:** nếu Job nhạy cảm cần người phê duyệt khác người khởi chạy, thực thi quy tắc đó ở backend.
- **Object-level authorization:** luôn kiểm tra quyền trên JobExecution thật, không chỉ kiểm tra quyền `stop` chung.
- **Defense in depth:** kiểm tra ở HTTP gateway/filter, method/service và lớp policy theo tài nguyên.

## 5. Các đường khởi chạy Job phải được bảo vệ

Spring Batch Job có thể được kích hoạt từ nhiều nơi:

```text
REST API ------┐
Admin UI ------┤
@Scheduled ----┤
Message queue -┤----> BatchControlService ----> JobLauncher
CLI ----------─┤
Internal code -┘
```

Nếu chỉ bảo vệ REST controller, một method nội bộ hoặc một scheduler khác vẫn có thể gọi trực tiếp `JobLauncher`. Điều đó không nhất thiết là lỗi nếu đây là thành phần được tin cậy, nhưng phải có **chính sách và danh tính vận hành tương ứng**.

Nên giới hạn quyền gọi các API nguy hiểm qua một lớp dịch vụ điều phối, ví dụ:

```text
Authenticated HTTP request
        |
        v
  BatchController
        |
        v
  BatchControlService
        |
        v
  BatchAccessPolicy
        |
        +-- requireCanLaunch(actor, job, parameters)
        +-- requireCanStop(actor, storedExecution)
        |
        v
  JobLauncher / JobOperator
        |
        v
  JobRepository
```

Cấu trúc cho phép dùng chung policy khi thêm giao diện quản trị, worker hoặc CLI. Với lịch nội bộ, có thể dùng **scheduler identity có quyền giới hạn** thay cho “bỏ qua toàn bộ phân quyền”; lịch được phê duyệt sẵn phải giới hạn vào đúng Job, tham số và môi trường.

## 6. Bảo vệ REST API bằng Spring Security

Ví dụ sau dùng **Spring Boot 3.x, Spring Security 6.x, Spring Batch 5.x**. Đối với Spring Batch 6.x, các kiểu Job/JobExecution có thay đổi package và cách cấu hình JobOperator có thể khác; nguyên tắc bảo vệ endpoint vẫn giữ nguyên.

### 6.1. Dependency

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Tùy dự án, Spring Boot BOM quản lý phiên bản tương thích của những starter. Ví dụ giả định API nhận **Bearer JWT** từ một Identity Provider đáng tin cậy; ứng dụng phải được cấu hình issuer/JWK và các validator thích hợp.

### 6.2. URL minh họa

API chỉ hỗ trợ Job đã được công bố:

```http
POST /api/batch/jobs/dailySettlementJob/executions
Content-Type: application/json
Authorization: Bearer <access-token>

{"businessDate":"2026-11-16"}
```

Yêu cầu dừng execution:

```http
POST /api/batch/executions/412/stop
Authorization: Bearer <access-token>
```

Dùng `POST` cho hai thao tác làm thay đổi trạng thái; không dùng `GET` để khởi chạy hay dừng Job. Endpoint có thể thêm yêu cầu idempotency key và lý do thay đổi theo quy tắc nghiệp vụ.

### 6.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class BatchApiSecurityConfig {

    @Bean
    SecurityFilterChain batchApiFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/batch/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/batch/jobs/dailySettlementJob/executions"
                        ).hasAuthority("SCOPE_batch.launch")
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/batch/executions/*/stop"
                        ).hasAuthority("SCOPE_batch.stop")
                        .anyRequest().denyAll()
                )
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

Điểm cần hiểu:

1. `securityMatcher("/api/batch/**")` giới hạn chain này cho API Batch; ứng dụng có các endpoint khác cần chain hoặc chính sách riêng.
2. Endpoint launch yêu cầu authority `SCOPE_batch.launch`; stop yêu cầu `SCOPE_batch.stop`.
3. Với cấu hình resource server JWT mặc định, Spring Security thường chuyển các giá trị scope thành authority có tiền tố `SCOPE_`. Nếu Identity Provider dùng claim không chuẩn, cần cấu hình converter theo nguồn đã được xác thực.
4. `anyRequest().denyAll()` chặn những đường điều khiển Batch chưa được công bố.
5. `@EnableMethodSecurity` cho phép `@PreAuthorize` ở tầng service.
6. Ví dụ **tắt CSRF** vì API giả định xác thực bằng Bearer token stateless, không dùng cookie/phiên browser làm credential. **Không sao chép cấu hình này sang ứng dụng dùng session/cookie** mà không đánh giá lại CSRF.

Trong production, cần cấu hình xác thực issuer, chữ ký, expiry, audience và yêu cầu trust phù hợp. **Client không được tự tạo claim scope hợp lệ** chỉ bằng cách sửa JWT; token phải được cấp và ký bởi nguồn tin cậy.

### 6.4. Filter kiểm tra quyền chức năng, không thay thế resource policy

Nếu một tài khoản có `SCOPE_batch.stop`, cấu hình URL ở trên cho phép nó tới service stop. Nhưng vẫn phải kiểm tra execution ID thực sự thuộc Job và tenant mà tài khoản được điều hành.

`jobExecutionId` có thể là số tăng tuần tự; vì thế API chỉ dựa vào quyền scope chung dễ có lỗ hổng **Insecure Direct Object Reference (IDOR)**: sửa `412` thành `413` để dừng execution của đơn vị khác.

## 7. Xây dựng lớp phân quyền theo tài nguyên

Một policy có thể được định nghĩa bằng interface để tách quy tắc nghiệp vụ khỏi code khởi chạy:

```java
import java.time.LocalDate;

import org.springframework.batch.core.JobExecution;
import org.springframework.security.core.Authentication;

public interface BatchAccessPolicy {

    void requireCanLaunch(
            Authentication actor,
            String jobName,
            LocalDate businessDate);

    void requireCanStop(
            Authentication actor,
            JobExecution execution);
}
```

Đây là interface **do ứng dụng định nghĩa**, không phải API sẵn có của Spring Batch. Implementation phải dùng nguồn dữ liệu ủy quyền đáng tin cậy, chẳng hạn bảng gán quyền người dùng–tenant–Job hoặc policy service nội bộ.

Một bảng quy tắc minh họa:

| Kiểm tra | Launch | Stop |
| --- | --- | --- |
| Người gọi đã xác thực | Bắt buộc | Bắt buộc |
| Quyền chức năng | `batch.launch` | `batch.stop` |
| Job allowlist | Job được phê duyệt để launch | Job gắn với execution được phép stop |
| Phạm vi tenant/project | Phạm vi sẽ được xử lý | Phạm vi lưu ở execution và nguồn gán quyền đáng tin cậy |
| Môi trường | Được phép launch ở môi trường này | Được phép stop ở môi trường này |
| Thời gian/lý do | Có thể cần lịch hoặc phê duyệt | Có thể cần ticket sự cố và reason |
| Trạng thái | Kiểm tra cửa sổ dữ liệu, trùng lặp và restart policy | Phải xét execution có đang chạy hay không |

**Không quyết định quyền stop dựa hoàn toàn vào một `tenantId` do client tự truyền.** Nếu tham số tenant đã được backend tin cậy gắn vào JobParameters lúc launch, nó có thể là thông tin hỗ trợ; tốt hơn là có bảng ánh xạ quyền thực thi riêng, hoặc tra quyền từ owner/dataset bất biến.

Ví dụ một bảng do ứng dụng quản lý:

```sql
CREATE TABLE batch_execution_access (
    job_execution_id BIGINT PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    project_id       VARCHAR(64) NOT NULL,
    submitted_by     VARCHAR(128) NOT NULL,
    classification   VARCHAR(32) NOT NULL,
    created_at       TIMESTAMP NOT NULL
);
```

Bảng này là **metadata phân quyền của ứng dụng**, không phải bảng mặc định của Spring Batch. Phải thiết kế việc ghi nhận/khôi phục mapping sao cho execution không bị mất thông tin quyền vì lỗi giữa bước tạo JobExecution và lưu ánh xạ. Nếu việc tạo mapping và tạo JobExecution không thể giao dịch nguyên tử, giải pháp cần có quy trình reconcile, deny an toàn khi thiếu mapping và audit.

### Không dựa vào role chung để mở mọi Job

Ngay cả quyền quản trị cũng có thể bị giới hạn theo môi trường hoặc phân loại dữ liệu. Một operator production có quyền điều hành catalog không nên mặc nhiên truy cập Job xuất dữ liệu chứa thông tin định danh khách hàng.

Policy phải kiểm tra quyền trên **đối tượng thực**. Đối với stop, lấy `JobExecution` trước, rồi quyết định có được stop execution đó không. Không chỉ đối chiếu tên Job từ query parameter do client cung cấp.

## 8. Service khởi chạy Job với kiểm tra quyền

Một cách đơn giản là chỉ công bố operation cụ thể `launchDailySettlement`; không cho client tùy ý nhập mọi `jobName` và danh sách tham số.

Ví dụ Spring Batch 5.x:

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class BatchControlService {

    private final JobLauncher jobLauncher;
    private final JobOperator jobOperator;
    private final JobExplorer jobExplorer;
    private final Job settlementJob;
    private final BatchAccessPolicy accessPolicy;

    public BatchControlService(
            JobLauncher jobLauncher,
            JobOperator jobOperator,
            JobExplorer jobExplorer,
            @Qualifier("dailySettlementJob") Job settlementJob,
            BatchAccessPolicy accessPolicy) {

        this.jobLauncher = jobLauncher;
        this.jobOperator = jobOperator;
        this.jobExplorer = jobExplorer;
        this.settlementJob = settlementJob;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize("hasAuthority('SCOPE_batch.launch')")
    public LaunchReceipt launchDailySettlement(
            LocalDate businessDate,
            Authentication actor) throws JobExecutionException {

        accessPolicy.requireCanLaunch(
                actor,
                settlementJob.getName(),
                businessDate);

        JobParameters parameters = new JobParametersBuilder()
                .addString(
                        "businessDate",
                        businessDate.toString(),
                        true)
                .addString(
                        "requestId",
                        UUID.randomUUID().toString(),
                        false)
                .toJobParameters();

        JobExecution execution =
                jobLauncher.run(settlementJob, parameters);

        return new LaunchReceipt(
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus().name());
    }

    @PreAuthorize("hasAuthority('SCOPE_batch.stop')")
    public StopReceipt requestStop(
            long executionId,
            Authentication actor) throws Exception {

        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            // Trong API thật, dùng exception mapping phù hợp,
            // tránh rò rỉ sự tồn tại của execution thuộc tenant khác.
            throw new IllegalArgumentException(
                    "Execution not found or not accessible");
        }

        accessPolicy.requireCanStop(actor, execution);

        boolean requested = jobOperator.stop(executionId);

        return new StopReceipt(executionId, requested);
    }

    public record LaunchReceipt(
            Long jobInstanceId,
            Long jobExecutionId,
            String observedStatus) {
    }

    public record StopReceipt(
            long jobExecutionId,
            boolean stopRequested) {
    }
}
```

Để ví dụ gọn, các import `JobOperator` và `JobExplorer` cần bổ sung tương ứng:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.explore.JobExplorer;
```

**Điều kiện của ví dụ:**

- Application context có `Job` bean tên `dailySettlementJob`, `JobLauncher`, `JobOperator` và `JobExplorer`.
- `BatchAccessPolicy` có implementation thực thi quyền theo tenant/Job/ngày xử lý từ nguồn đáng tin cậy.
- `@EnableMethodSecurity` đã bật, và lời gọi tới service đi qua Spring Security proxy.
- `requestId` được sinh ở server và đánh dấu **non-identifying**. `businessDate` là identifying parameter, nên các yêu cầu cùng ngày nhắm đến cùng `JobInstance`, trừ khi Job còn có identifying parameters khác do cấu hình thêm.
- Nếu cần một đơn vị công việc cho **mỗi cửa sổ giờ**, nên dùng `windowStart` làm identifying parameter thay vì chỉ `businessDate`.

Không nên tự sinh `run.id` identifying ở mỗi lần launch chỉ để tránh lỗi trùng, nếu nghiệp vụ thực sự quy định mỗi ngày chỉ có một JobInstance. Làm vậy có thể khiến nhiều execution xử lý trùng cùng cửa sổ dữ liệu.

### Vì sao phải đặt `@PreAuthorize` ở service?

Controller là một entrypoint; service có thể được gọi qua những entrypoint khác. Bảo vệ service giúp gom logic ở một điểm có thể tái sử dụng.

Tuy nhiên, Spring method security sử dụng proxy trong nhiều cấu hình. Một lời gọi **`this.launchDailySettlement(...)` từ trong chính bean** có thể bỏ qua interceptor `@PreAuthorize`. Không xây dựng đường nội bộ đi vòng qua lớp phân quyền. Nên tổ chức các component gọi qua Spring-managed bean hoặc một hàm policy mà mọi đường gọi bắt buộc đi qua.

### Lỗi khi launch không phải lúc nào cũng là lỗi thực thi

`JobLauncher.run(...)` có thể báo:

- `JobExecutionAlreadyRunningException`: một execution của cùng JobInstance đang chạy.
- `JobInstanceAlreadyCompleteException`: instance tương ứng đã hoàn thành.
- `JobRestartException`: việc restart không hợp lệ.
- `JobParametersInvalidException`: tham số không được chấp nhận.

Các lỗi này thường xảy ra **trước khi tạo JobExecution mới thành công**. API phải phân biệt chúng với Job đã khởi chạy nhưng kết thúc `BatchStatus.FAILED`.

## 9. REST controller không nhận tham số tự do

Controller chỉ nhận những trường nghiệp vụ đã được cho phép. Ví dụ dùng `LocalDate` để Spring/Jackson kiểm tra định dạng ngày, thay vì chuỗi đường dẫn file hay câu truy vấn tùy ý.

```java
import java.time.LocalDate;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/batch")
public class BatchControlController {

    private final BatchControlService service;

    public BatchControlController(BatchControlService service) {
        this.service = service;
    }

    @PostMapping(
            "/jobs/dailySettlementJob/executions"
    )
    public ResponseEntity<BatchControlService.LaunchReceipt> launch(
            @Valid @RequestBody LaunchRequest request,
            Authentication actor) throws Exception {

        var result = service.launchDailySettlement(
                request.businessDate(), actor);

        return ResponseEntity.accepted().body(result);
    }

    @PostMapping("/executions/{executionId}/stop")
    public ResponseEntity<BatchControlService.StopReceipt> stop(
            @PathVariable long executionId,
            Authentication actor) throws Exception {

        var result = service.requestStop(executionId, actor);
        return ResponseEntity.accepted().body(result);
    }

    public record LaunchRequest(
            @NotNull LocalDate businessDate) {
    }
}
```

HTTP `202 Accepted` ở đây diễn đạt yêu cầu điều khiển đã được chấp nhận; **không hàm ý Job đã hoàn thành hoặc đã dừng**. Tùy API contract, có thể trả HTTP `200 OK` nếu chạy Job đồng bộ và muốn thông báo ngay kết quả, nhưng phải trình bày rõ trạng thái quan sát được.

Một API hoàn chỉnh nên có thêm endpoint **đọc trạng thái** với quyền `batch.read` được kiểm soát theo execution, ví dụ:

```http
GET /api/batch/executions/412
```

Client cần gọi endpoint đó hoặc dùng sự kiện/notification được bảo vệ để biết kết quả cuối. Không dùng HTTP code `202` như bằng chứng thành công nghiệp vụ.

### Không nhận những tham số sau một cách tùy tiện

Tránh API cho phép client gửi trực tiếp:

```json
{
  "jobName": "anyJobFromContext",
  "parameters": {
    "inputFile": "../../private/export.csv",
    "sql": "DELETE FROM ...",
    "outputBucket": "unapproved-bucket",
    "tenantId": "other-tenant"
  }
}
```

Những giá trị trên là minh họa **dữ liệu đầu vào không đáng tin cậy**. Giải pháp an toàn hơn là định nghĩa contract cho từng Job:

- `businessDate`: chuẩn ngày, kiểm tra phạm vi ngày được phép.
- `tenantId`: lấy từ danh tính/nguồn gán quyền đáng tin cậy, không tin hoàn toàn giá trị client gửi.
- `inputDatasetId`: đối chiếu với dataset/đường dẫn đã đăng ký trong backend.
- `outputLocation`: chọn từ nơi lưu được cho phép, không dùng path tùy ý.
- `runMode`: enum do backend kiểm soát.
- `requestId`: do server sinh hoặc được xác thực/idempotency hóa theo quy tắc.

**Xác thực tham số và phân quyền tham số là hai việc khác nhau.** `businessDate` có định dạng đúng vẫn có thể nằm ngoài khoảng ngày mà operator được phép xử lý.

## 10. Stop Job là yêu cầu dừng có kiểm soát

Điểm thường bị hiểu sai: gọi `JobOperator.stop(executionId)` **không tương đương hủy thread, kill process hoặc rollback toàn bộ dữ liệu đã commit**.

Với Spring Batch, cơ chế stop được thiết kế để yêu cầu Job đang chạy chuyển sang trạng thái dừng và hoàn tất việc dừng ở những điểm thích hợp của quá trình thực thi.

```text
JobExecution #412
     |
     v
  STARTED
     |
     | operator: stop(412)
     v
  STOPPING
     |
     | Step nhận tín hiệu dừng và kết thúc tại điểm phù hợp
     v
  STOPPED
```

Đây là luồng điển hình, không phải bảo đảm rằng mọi Job luôn dừng nhanh. Một Step đang chờ I/O lâu, tasklet không kiểm tra tín hiệu dừng hoặc một integration bị block có thể cần thời gian đáng kể. Job có thể đã hoàn thành trước khi lệnh stop được xử lý; trạng thái cuối cũng có thể khác tùy race và lỗi vận hành.

### Trả kết quả stop thế nào?

Phương thức `JobOperator.stop(long executionId)` ở Spring Batch 5.x trả về một boolean thể hiện yêu cầu dừng có được tiếp nhận theo hợp đồng API; bản thân giá trị đó **không chứng minh Job đã đạt `STOPPED`**.

Cách trả API hợp lý:

```json
{
  "jobExecutionId": 412,
  "stopRequested": true
}
```

Sau đó, client xem trạng thái thật qua `JobExplorer` hoặc endpoint đọc được bảo vệ, chờ `STOPPED`/trạng thái kết thúc với timeout. Không trả thông báo “Đã dừng hoàn toàn” ngay khi `stop(...)` trả về.

### Không dùng stop để che đậy lỗi hoặc thay đổi lịch sử

- Stop không xóa `JobExecution` hay lịch sử `StepExecution`.
- Những chunk đã commit trước khi stop không mặc nhiên được rollback.
- Nếu Job có side effect ngoài transaction, stop không tự hoàn tác email/API/message đã gửi.
- Restart sau stop phụ thuộc cấu hình restartability, Step/Job state và tính idempotent của nghiệp vụ.
- Nếu muốn kill process ở tầng hạ tầng, đó là quyền **khác** với stop Job và cần quy trình an toàn riêng.

Việc stop một Job đối soát có thể cần người phê duyệt hoặc incident ticket vì nó ảnh hưởng SLA và tiến độ xử lý. Policy có thể bắt buộc lý do stop, giới hạn thời điểm stop và yêu cầu xác nhận tại backend.

## 11. Chống IDOR khi stop bằng execution ID

Một API không an toàn:

```java
@PostMapping("/executions/{id}/stop")
public void stop(@PathVariable long id) throws Exception {
    jobOperator.stop(id);
}
```

Dù endpoint yêu cầu đăng nhập, một người có thể sửa ID để chạm đến JobExecution không thuộc phạm vi quyền của mình.

Cách xử lý:

1. Xác thực caller và lấy quyền đã được cấp.
2. Đọc `JobExecution` từ `JobExplorer` dựa trên ID.
3. Xác định JobName, environment, tenant/project và phân loại dữ liệu bằng nguồn đáng tin cậy.
4. Kiểm tra caller có quyền `batch.stop` **và** quyền trên execution cụ thể.
5. Kiểm tra điều kiện vận hành như trạng thái và chính sách approval.
6. Gọi `JobOperator.stop(executionId)`; ghi audit request và kết quả.
7. Quan sát trạng thái terminal sau đó; không suy diễn từ HTTP response.

Có hai điểm tinh tế:

**Thứ nhất, tránh tiết lộ sự tồn tại của execution thuộc tenant khác.** Tùy hợp đồng API, có thể dùng thông báo chung kiểu “không tìm thấy hoặc không có quyền” để không tạo kênh dò ID. Cần thống nhất cách dùng HTTP `403`/`404` và không để thời gian phản hồi tiết lộ quá nhiều.

**Thứ hai, trạng thái có thể thay đổi giữa lúc kiểm tra và lúc gọi stop.** Job có thể chuyển từ `STARTED` sang `COMPLETED`. Đó là race về lifecycle; service phải xử lý kết quả/exception của `JobOperator` và ghi đúng trạng thái quan sát được, thay vì tin rằng mọi stop đều thành công vì một snapshot trước đó báo đang chạy.

## 12. Kiểm tra trạng thái và điều kiện dừng

`JobExplorer` cung cấp khả năng xem execution:

```java
JobExecution execution =
        jobExplorer.getJobExecution(executionId);

if (execution == null) {
    // Không tồn tại trong repository đang truy vấn.
} else {
    var status = execution.getStatus();
    var name = execution.getJobInstance().getJobName();

    // Dùng thông tin này để hỗ trợ policy và trạng thái UI.
}
```

Những trạng thái thường thấy:

| `BatchStatus` | Ý nghĩa | Quyết định stop gợi ý |
| --- | --- | --- |
| `STARTING` | Job đang bắt đầu. | Kiểm tra xem phiên bản/operator có tiếp nhận lệnh stop và policy có cho phép. |
| `STARTED` | Job đang chạy. | Có thể yêu cầu stop khi actor đủ quyền. |
| `STOPPING` | Đang trong quá trình dừng. | Trả trạng thái “đã có yêu cầu dừng”; tránh spam lệnh. |
| `STOPPED` | Job đã dừng. | Không cần tạo thêm một lệnh stop giống hệt. |
| `COMPLETED` | Job hoàn thành. | Không còn là execution đang chạy để stop. |
| `FAILED` | Job thất bại. | Không dùng stop làm thay đổi lịch sử lỗi; có thể xem restart policy. |
| `ABANDONED` | Execution bị đánh dấu không dùng để restart theo quy tắc tương ứng. | Không coi là execution đang chạy. |

Phân loại policy nên hiểu rõ các trạng thái. Việc chỉ kiểm tra `status == STARTED` có thể không bao quát mọi thời điểm chuyển trạng thái; để API chính xác, xử lý theo hợp đồng `JobOperator` và trạng thái metadata thực tế thay vì tự thay đổi trạng thái.

Đặc biệt, **không cập nhật trực tiếp cột `BATCH_JOB_EXECUTION.STATUS` bằng SQL** để “dừng” Job. Ghi như vậy chỉ làm thay đổi metadata, không bảo đảm worker được thông báo; đồng thời có thể gây sai lệch giữa quá trình thực tế và khả năng restart.

## 13. Quyền launch cần gắn với JobParameters và nghiệp vụ

Việc được phép khởi chạy `dailySettlementJob` không có nghĩa được phép xử lý **mọi ngày, mọi tenant hoặc mọi chế độ vận hành**.

Ví dụ chính sách:

```text
Actor: operator-27
Permission: batch.launch
Job allowed: dailySettlementJob
Tenant allowed: tenant-A
Business date allowed: <= current business date
Environment allowed: staging
Approval required in production: yes
```

Đây là policy minh họa. Trong code cần:

- Dùng allowlist tên Job được công bố, không expose toàn bộ `ApplicationContext`/`JobRegistry` cho API công khai.
- Kiểm tra giá trị ngày/cửa sổ nằm trong phạm vi.
- Ràng buộc tenant từ danh tính hoặc nguồn ánh xạ đã được tin cậy.
- Chỉ cho phép mode, input/output và tài nguyên được phê duyệt.
- Kiểm tra limit tần suất, số Job đang chạy và SLA.
- Ghi nhận request ID/idempotency key để phân biệt retry HTTP với một yêu cầu mới.

### Identifying parameters và chạy trùng

Trong Spring Batch, **tên Job + identifying JobParameters** xác định `JobInstance`. Nếu một JobInstance đã hoàn thành, cố chạy lại cùng parameters thường bị từ chối bằng `JobInstanceAlreadyCompleteException`. Nếu đang chạy, yêu cầu cùng instance có thể bị từ chối bằng `JobExecutionAlreadyRunningException`.

Nhưng điều này **không phải cơ chế phân quyền**. Kẻ gọi có quyền launch quá rộng có thể thay identifying parameter để tạo instance mới. Chính sách launch vẫn phải xác định bộ tham số nào được phép.

Khi cần chống chồng lấn của **các instance khác nhau** trên cùng tài nguyên, dùng thêm cơ chế điều phối/khóa phân tán hoặc hàng đợi theo nghiệp vụ. `JobRepository` không mặc định chặn mọi execution cùng tên Job nếu identifying parameters khác nhau.

### Idempotency của API

Một client có thể retry cùng HTTP request sau timeout mạng. Nếu lần đầu đã tạo JobExecution, lần thứ hai không nên vô tình tạo công việc khác chỉ vì một `requestId` ngẫu nhiên được coi là identifying.

Một thiết kế có thể lưu `idempotencyKey` đã được xác thực và mapping từ request đến JobExecution. Các lần retry cùng key và cùng nội dung yêu cầu trả cùng kết quả đã biết (hoặc trạng thái đang xử lý), không khởi chạy lại không kiểm soát. Nếu key trùng nhưng payload khác, trả conflict theo hợp đồng API.

`JobInstance` identity và HTTP idempotency bổ sung cho nhau; chúng không thay thế toàn bộ việc bảo vệ side effect nghiệp vụ.

## 14. Audit mọi yêu cầu launch và stop

Cần trả lời được:

**Ai** yêu cầu, **lúc nào**, **từ đâu**, **trên Job/Execution nào**, **với tham số nào được cho phép**, **vì sao**, **kết quả phân quyền ra sao** và **Job cuối cùng kết thúc thế nào**.

Một audit record minh họa:

```json
{
  "eventId": "evt-000182",
  "timestamp": "2026-11-16T03:15:00Z",
  "actorId": "operator-27",
  "actorType": "HUMAN",
  "action": "BATCH_STOP",
  "resource": {
    "jobName": "dailySettlementJob",
    "jobExecutionId": 412
  },
  "decision": "ALLOW",
  "requestAccepted": true,
  "reasonCode": "INCIDENT_RESPONSE",
  "incidentTicket": "INC-0123",
  "requestId": "rq-0091"
}
```

Đây là ví dụ định dạng audit **do ứng dụng định nghĩa**, không phải schema Spring Batch cung cấp sẵn.

Nên phân biệt các sự kiện:

- `batch.launch.requested`: yêu cầu khởi chạy đến hệ thống.
- `batch.launch.denied`: người gọi không đủ quyền hoặc vi phạm policy.
- `batch.launch.accepted`: Batch đã tạo/chấp nhận JobExecution.
- `batch.launch.rejected`: bị từ chối do điều kiện lifecycle, tham số hoặc lỗi khởi chạy.
- `batch.stop.requested`: yêu cầu dừng đã đến.
- `batch.stop.denied`: quyền stop không hợp lệ.
- `batch.stop.accepted`: yêu cầu dừng được tiếp nhận.
- `batch.job.finished`: JobExecution đạt kết quả cuối và lưu metadata.

**Audit một lệnh stop được tiếp nhận không đồng nghĩa audit Job đã dừng thành công.** Kết quả cuối phải đối chiếu `JobRepository`/`JobExplorer` và các StepExecution.

### Audit của request bị từ chối

Nếu `@PreAuthorize` chặn tại Spring Security proxy, logic bên trong service không được chạy. Vì vậy, **không thể chỉ đặt audit tại dòng đầu service để bảo đảm ghi mọi lần DENY**.

Cần bổ sung cơ chế audit tại điểm phân quyền, như `AccessDeniedHandler`, authorization events, request filter hoặc policy service. Audit của denial chỉ ghi các thuộc tính an toàn, không sao chép toàn bộ Bearer token, JSON payload chứa secret hoặc exception stack trace nhạy cảm.

### Độ bền audit

Nếu yêu cầu tuân thủ bắt buộc phải lưu mọi lần điều khiển, chỉ ghi logger INFO có thể không đủ. Cân nhắc audit table/outbox bền vững, chính sách retention và kiểm soát truy cập. Nếu audit phải atomic với việc tạo một lệnh điều phối, cần thiết kế transactional boundary và xử lý trường hợp database/audit sink lỗi; gọi JobLauncher và ghi audit ở hai giao dịch độc lập **không mặc định tạo bảo đảm exactly-once**.

## 15. Scheduler và service account

`@Scheduled` không có một HTTP user đăng nhập tại thời điểm callback. Nếu một method scheduler gọi service có `@PreAuthorize` dựa vào `SecurityContextHolder`, authentication có thể không tồn tại. Không giải quyết bằng cách tắt bảo mật hoặc tự gán quyền admin cho mọi scheduled task.

Có thể thiết kế:

```text
Trusted Scheduler Identity
  subject = scheduler:settlement
  allowed jobs = [dailySettlementJob]
  allowed action = LAUNCH
  allowed schedule = 02:00 UTC daily
        |
        v
Batch Orchestration
        |
        v
Launch policy (server-side allowlist)
        |
        v
JobLauncher
```

Các lựa chọn kỹ thuật:

- Dùng workload identity/token ngắn hạn khi scheduler gọi một API nội bộ đã bảo vệ.
- Cấp một service principal riêng cho lịch, với quyền launch **chỉ Job được giao**.
- Nếu lịch chạy trực tiếp trong ứng dụng, dùng entrypoint nội bộ riêng có policy kiểm tra định nghĩa lịch và định danh tác vụ được tin cậy, đồng thời ghi audit như service account.
- Không dùng quyền stop cho scheduler nếu không có yêu cầu thực sự.

Với nhiều node, **authorization không chống việc lịch bị chạy hai lần**. Cần thêm coordination và quy tắc xử lý trùng, phù hợp với đặc điểm Job.

### Phân quyền cho CLI và công cụ quản trị

Công cụ CLI hoặc Spring Shell có thể gọi trực tiếp `JobOperator`. Nếu CLI được dành cho vận hành nhạy cảm, cần giới hạn ai có quyền chạy process/command, cách cấp token/danh tính, môi trường và audit; tránh để một command line nội bộ trở thành đường bypass chính sách HTTP.

## 16. Xử lý lỗi HTTP và phản hồi an toàn

API cần nhất quán giữa **authentication/authorization** và **trạng thái Batch**.

| Tình huống | HTTP gợi ý | Ý nghĩa |
| --- | --- | --- |
| Không có hoặc token không hợp lệ | `401 Unauthorized` | Chưa xác thực được người gọi. |
| Đã xác thực nhưng thiếu scope/chính sách | `403 Forbidden` | Không có quyền thao tác. |
| Resource không tồn tại hoặc không được phép tiết lộ | `404 Not Found` hoặc phản hồi che giấu theo policy | Tránh dò ID ngoài phạm vi. |
| Body/parameter không hợp lệ | `400 Bad Request` | Sai định dạng hoặc validation nghiệp vụ. |
| JobInstance đã hoàn thành/đang chạy | `409 Conflict` theo API contract | Trùng lifecycle hoặc yêu cầu không còn hợp lệ. |
| Lệnh launch/stop được tiếp nhận nhưng chưa biết kết quả cuối | `202 Accepted` | Cần theo dõi JobExecution tiếp. |
| Service hạ tầng tạm thời không thể tiếp nhận | `503 Service Unavailable` hoặc lỗi tương ứng | Không giả vờ Job đã được khởi chạy. |

Đây là **gợi ý thiết kế contract**; Spring Batch không tự động ánh xạ các exception sang các HTTP code trên. Ứng dụng cần `@ControllerAdvice` hoặc exception handler nhất quán.

Cần phân biệt:

- **403**: actor không có quyền với thao tác/tài nguyên.
- **409**: actor đủ quyền nhưng trạng thái Job không cho phép yêu cầu đó.
- **JobExecution FAILED**: Job đã chạy nhưng xử lý nghiệp vụ thất bại, không phải lỗi phân quyền.

Không đưa toàn bộ stack trace, token, mật khẩu, cấu hình datasource hoặc tên tài nguyên nhạy cảm vào response client.

## 17. Các lớp bảo vệ bổ sung

### 17.1. Giới hạn tần suất và số Job đồng thời

Một người có scope `batch.launch` vẫn có thể gửi hàng nghìn yêu cầu. Nên giới hạn:

- Request rate theo actor/tenant.
- Số JobExecution đồng thời theo Job hoặc môi trường.
- Số yêu cầu đang chờ.
- Kích thước/payload của request.
- Cửa sổ được phép chạy và quyền kích hoạt lại.

Rate limiting không thay thế authorization nhưng giúp giảm khả năng dùng sai quyền và bảo vệ hệ thống khỏi quá tải.

### 17.2. Chống nhập đường dẫn và dữ liệu không tin cậy

Nếu Job nhận `inputFile`, `outputPath` hoặc `bucket` từ API, không chỉ kiểm tra “không rỗng”. Phải kiểm tra phạm vi tài nguyên được cấp phép, path traversal, các đường dẫn tuyệt đối bị cấm, file symlink, storage namespace và quyền đọc/ghi của tài khoản thực thi.

Đối với JobParameters dùng làm giá trị SQL, luôn dùng prepared statement/parameter binding; không ghép chuỗi SQL trực tiếp. Không cho phép `jobName` từ request được dùng để định vị mọi bean trong application context rồi khởi chạy.

### 17.3. Phân biệt quyền của API và quyền của Job runtime

Người dùng chỉ được quyền **yêu cầu chạy**; Job khi chạy có thể sử dụng database account, object storage credential hoặc service account kỹ thuật riêng. Không nên cấp người dùng quyền DB hoặc secret chỉ vì họ được phép launch.

Bảo đảm runtime credentials của từng Job có phạm vi tối thiểu. Với Job xuất dữ liệu nhạy cảm, quyền launch phải tương thích với quyền truy cập **đầu ra**; không để người dùng chỉ có quyền launch rồi nhận file export không được phép xem.

### 17.4. Tách môi trường và tenant

Staging và production nên dùng identity, permission scope, JobRepository, lock provider, audit và dữ liệu riêng theo thiết kế. Không nên cho token của staging dùng trên production nếu issuer/audience/policy không cho phép.

Tại multi-tenant application, kiểm tra tenant theo object thực tế và nguồn gán quyền; không chỉ gắn `tenantId` vào URL rồi tin rằng người dùng được phép chọn bất kỳ tenant nào.

### 17.5. Giữ bí mật trong metadata và log

`JobParameters` và `ExecutionContext` có thể được lưu vào database metadata. Không đưa access token, mật khẩu, API key hay PII nguyên văn vào tham số Job hoặc audit log. Dùng reference tới secret manager hoặc storage key an toàn với phân quyền riêng khi cần.

## 18. Kiểm thử phân quyền launch/stop

Kiểm thử bảo mật phải có cả **từ chối truy cập** và **kiểm tra Job thực sự không bị ảnh hưởng**. Chỉ assert HTTP `403` chưa đủ nếu một controller đã vô tình khởi chạy Job trước khi security filter trả lỗi.

### 18.1. Ma trận ca kiểm thử

| Test | Điều kiện | Kết quả kỳ vọng |
| --- | --- | --- |
| Chưa đăng nhập gọi launch | Không token | `401`, không tạo JobExecution. |
| Có quyền đọc nhưng không có quyền launch | Token thiếu `batch.launch` | `403`, không launch. |
| Có `batch.launch` nhưng không có quyền Job này | Policy allowlist từ chối | `403`, không launch. |
| Đúng quyền và tham số hợp lệ | Scope và resource policy đều cho phép | Tạo/chấp nhận JobExecution. |
| Tham số ngày ngoài phạm vi | Có scope nhưng vượt business policy | `403` hoặc lỗi policy thống nhất. |
| Người có `batch.stop` yêu cầu dừng execution tenant khác | Object-level policy từ chối | Không gọi `JobOperator.stop(...)`. |
| Có quyền stop execution đang chạy | Permission hợp lệ | Yêu cầu stop được tiếp nhận; sau đó kiểm tra trạng thái cuối. |
| Stop execution đã hoàn thành | Actor có quyền nhưng trạng thái không cho phép | Conflict/trạng thái phù hợp, không báo đã stop thành công. |
| Retry cùng yêu cầu launch | Cùng idempotency key | Không tạo thêm JobInstance trái hợp đồng. |
| Scheduler identity | Chỉ có quyền Job được giao | Launch đúng Job, từ chối Job khác. |

### 18.2. MockMvc với JWT giả lập

Với `spring-security-test` có thể kiểm tra filter và controller. Ví dụ:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BatchApiAuthorizationIT {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void noTokenCannotLaunch() throws Exception {
        mockMvc.perform(
                post("/api/batch/jobs/dailySettlementJob/executions")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"businessDate\":\"2026-11-16\"}")
        ).andExpect(status().isUnauthorized());
    }

    @Test
    void readOnlyScopeCannotLaunch() throws Exception {
        mockMvc.perform(
                post("/api/batch/jobs/dailySettlementJob/executions")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_batch.read")))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"businessDate\":\"2026-11-16\"}")
        ).andExpect(status().isForbidden());
    }
}
```

Test trên kiểm tra **đường HTTP**, chưa thay thế test chi tiết của `BatchAccessPolicy`. Cần cấu hình context có security chain và các bean cần thiết. Khi sử dụng JWT giả lập, test không tự kiểm tra được chữ ký/issuer thực tế của hệ thống identity; cần có các test cấu hình token validation riêng.

### 18.3. Test method security

Với `@EnableMethodSecurity`, kiểm tra rằng gọi service qua Spring bean dưới một Authentication thiếu quyền bị từ chối. Có thể dùng `@WithMockUser(authorities = "SCOPE_batch.read")` trong test tích hợp method security.

Một điểm quan trọng: **không tạo service bằng `new BatchControlService(...)` rồi kỳ vọng `@PreAuthorize` được thực thi**. Method security thường áp dụng qua proxy Spring. Unit test trực tiếp đối tượng phù hợp để kiểm tra logic nội bộ, còn test quyền cần gọi Spring-managed proxy.

### 18.4. Test object-level authorization

Nên tạo hai `JobExecution` thuộc các tenant/phạm vi khác nhau trong repository test:

1. Actor A có `batch.stop` nhưng chỉ được quản lý tenant A.
2. Actor A yêu cầu dừng execution của tenant B.
3. Policy phải từ chối.
4. Kiểm tra `JobOperator.stop(...)` **không được gọi** và metadata của execution B không bị thay đổi bởi yêu cầu đó.
5. Lặp với execution thuộc tenant A và điều kiện trạng thái phù hợp, kiểm tra lệnh stop được gửi.

Nếu dùng mock cho `JobOperator`, có thể kiểm tra không có invocation. Nếu test với Job thật, sử dụng một Tasklet có latch/timeout để giữ Job đang chạy đủ lâu rồi quan sát stop. Tránh `Thread.sleep` cố định làm test không ổn định.

### 18.5. Test lifecycle stop với Job thật

Kịch bản:

```text
Arrange:
  JobExecution A bắt đầu, Step đang chạy có checkpoint/stop point
  Actor có quyền stop đối với A

Act:
  POST /api/batch/executions/{A}/stop

Assert:
  API không khẳng định Job đã STOPPED ngay
  Metadata có thể chuyển qua STOPPING
  Worker kết thúc có kiểm soát
  JobExecution cuối cùng đạt trạng thái phù hợp
  Audit chứa actor/action/executionId
```

Một Tasklet không kiểm tra tín hiệu dừng có thể không phản hồi như chunk-oriented Step; vì vậy fixture phải được thiết kế để kiểm tra đúng hợp đồng dừng của loại Step đang dùng. Test có timeout và dọn worker sau khi hoàn tất.

### 18.6. Test sau khi Job bị restart

Với cùng `JobInstance`, lần restart có `JobExecution` mới. Quyền stop phải kiểm tra **execution ID hiện tại**, không dùng nhầm ID cũ đã `FAILED` hay `STOPPED`. Không dọn metadata giữa lần lỗi và restart trong test; dữ liệu repository cần cho restart và kiểm tra phân quyền.

## 19. Điều kiện vận hành và phê duyệt

Một số Job có tác động lớn như chi trả, đóng sổ, xuất dữ liệu hoặc đồng bộ hàng loạt. Khi đó, scope và quyền tài nguyên có thể chưa đủ; cần thêm quy trình vận hành:

- Yêu cầu reason code khi stop, ví dụ `INCIDENT_RESPONSE`, `WRONG_INPUT`, `MAINTENANCE`.
- Ghi incident/change ticket, người yêu cầu và người phê duyệt.
- Hạn chế launch trong cửa sổ đóng sổ hoặc giờ giao dịch cao điểm.
- Bắt buộc phê duyệt hai bước với Job nhạy cảm; quyền “request” và quyền “approve” khác nhau.
- Hỗ trợ trạng thái `PENDING_APPROVAL` của **lệnh điều phối** mà chưa tạo JobExecution; chỉ sau phê duyệt mới launch.
- Thông báo cho chủ sở hữu Job khi stop được tiếp nhận và khi Job thực sự dừng.

Tách **được phép phát lệnh** khỏi **đã thực thi lệnh** là điều quan trọng để audit. Một bản ghi approval thành công không có nghĩa Job đã được chạy; Job chỉ được coi là launched khi backend thực sự tạo/chấp nhận JobExecution.

## 20. Những lỗi phân quyền thường gặp

### Chỉ dùng `@PreAuthorize("isAuthenticated()")`

Bất kỳ người dùng đăng nhập nào cũng có thể launch/stop. Cần phân quyền hành động, resource và phạm vi nghiệp vụ.

### Dùng mỗi `hasRole("ADMIN")` cho mọi Job

Quyền quá rộng, khó kiểm soát khác biệt giữa xem, launch, stop và restart. Dùng quyền rõ ràng và policy theo Job/tenant/environment.

### Để client truyền bất kỳ `jobName` nào

Một công cụ điều khiển generic có thể gọi Job ngoài phạm vi dự kiến. Dùng allowlist và mapping tên public API sang Job bean được phê duyệt.

### Chỉ bảo vệ controller

CLI, scheduler hoặc service nội bộ có thể gọi launcher trực tiếp. Cần thống nhất các entrypoint và không cho code chưa được tin cậy đi vòng lớp policy.

### Chỉ kiểm tra scope `batch.stop`

Không kiểm tra execution thực sự thuộc tenant/project nào gây lỗ hổng IDOR. Luôn đọc execution và ràng buộc quyền trên đối tượng.

### Tin `tenantId` do client gửi

Người gọi có thể thay tenant ID. Phải dùng thông tin từ danh tính được xác thực hoặc mapping ủy quyền trong backend.

### Cho rằng `stop(id)` trả về nghĩa là Job đã dừng xong

Stop thường là yêu cầu dừng có kiểm soát. Phải quan sát trạng thái cuối và xử lý timeout/race.

### Không kiểm tra execution đã hoàn tất

Một request stop có thể đến khi Job vừa kết thúc; không trả thông báo gây hiểu lầm. Phân biệt không còn đang chạy với stop được tiếp nhận.

### Cho phép thay JobParameters tùy ý để chạy lại

Tham số identifying mới có thể tạo JobInstance khác, xử lý lại dữ liệu. Phải định nghĩa đơn vị công việc, idempotency và quyền chọn tham số.

### Chỉ audit trường hợp thành công

Thao tác bị từ chối cũng cần dấu vết; nếu `@PreAuthorize` chặn trước khi vào service thì phải audit ở tầng authorization/filter.

### Dùng tài khoản runtime với quyền vượt mức

Người chỉ được launch một Job không nên thông qua Job đó có thể đọc/ghi mọi database hoặc xuất dữ liệu bất kỳ. Runtime credential và destination phải được giới hạn.

### Ghi token hoặc dữ liệu nhạy cảm vào log

Không lưu raw Bearer token, mật khẩu hay toàn bộ JobParameters chứa secret. Audit nên ghi ID, action, decision và những tham số đã được phân loại an toàn.

## 21. Bài tập thực hành

Giả sử hệ thống có hai Job:

- `importCatalogJob` nhập danh mục hằng ngày cho một tenant.
- `dailySettlementJob` quyết toán tài chính cuối ngày.

Hệ thống có ba nhóm người dùng: viewer, catalog operator và settlement operator. Một scheduler service account được phép tự động launch `importCatalogJob` theo lịch.

### Phần A – Thiết kế policy

1. Xác định quyền `batch.read`, `batch.launch`, `batch.stop`, `batch.restart`.
2. Lập bảng quyền cho từng nhóm và scheduler.
3. Quy định scope Job/tenant/environment cho từng quyền.
4. Quy định cần reason hoặc approval trước khi stop `dailySettlementJob`.
5. Định nghĩa identifying JobParameters để một ngày nghiệp vụ không bị khởi chạy vô ý nhiều instance.

### Phần B – Bảo vệ API

1. Tạo Bearer-token resource server cho `/api/batch/**`.
2. Dùng `SecurityFilterChain` kiểm soát endpoint launch/stop.
3. Dùng `@EnableMethodSecurity` và `@PreAuthorize` tại service.
4. Dùng `BatchAccessPolicy` để kiểm tra quyền tài nguyên.
5. Chỉ cho phép Job đã đăng ký; không để client tùy ý chọn file path, tenant hoặc arbitrary parameters.
6. Trả `202` với execution ID/stop request state, đồng thời cung cấp endpoint đọc trạng thái có phân quyền.

### Phần C – Kiểm thử âm và dương

1. Không token → `401` và không tạo execution.
2. Viewer launch Job → `403`.
3. Catalog operator launch `importCatalogJob` trong tenant được giao → cho phép.
4. Catalog operator launch `dailySettlementJob` → từ chối.
5. Settlement operator stop execution của tenant khác → từ chối, không gọi `JobOperator.stop`.
6. Settlement operator stop execution của tenant được giao khi Job đang chạy → chấp nhận yêu cầu.
7. Poll `JobExplorer` đến trạng thái cuối, không nhầm `STOPPING` với `STOPPED`.
8. Hai request launch cùng business date → không tạo hai đơn vị công việc không mong muốn.
9. Thử đường CLI/scheduler và xác nhận policy vẫn được áp dụng tương ứng.
10. Kiểm tra audit cả trường hợp `ALLOW`, `DENY` và kết quả Batch sau thao tác.

### Phần D – Tình huống sự cố

Cho `dailySettlementJob` chạy một Step ghi 10.000 bản ghi theo chunk. Khi đã commit một số chunk, actor được phép gửi yêu cầu stop.

Hãy xác minh:

- Request được kiểm tra quyền trước khi gọi `JobOperator`.
- Job dừng ở điểm phù hợp, nhưng các chunk đã commit không tự biến mất.
- Audit nêu rõ actor, JobExecution ID, thời điểm và lý do stop.
- Nếu nghiệp vụ cần restart, metadata và business data còn đủ điều kiện xử lý tiếp mà không ghi trùng.
- Nếu cùng lúc một actor khác gửi stop trùng, hệ thống không trả hai thông báo “đã dừng” sai lệch.

Qua bài tập, điểm mấu chốt là **quyền điều khiển Job phải gắn với hành động, tài nguyên thật, ngữ cảnh nghiệp vụ và trạng thái thực thi**, thay vì chỉ gắn với việc user có đăng nhập hay không.

## Tài liệu tham khảo

- [Spring Batch Reference – Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): JobLauncher, JobParameters, JobInstance và JobExecution.
- [Spring Batch Reference – JobOperator](https://docs.spring.io/spring-batch/reference/job/configuring-operator.html): các thao tác vận hành Job, bao gồm stop/restart theo phiên bản.
- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): trạng thái Job/Step và metadata.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): nguồn lưu execution và thông tin restart.
- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
- [Spring Security Reference – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): bảo vệ request và tài nguyên.
- [Spring Security Reference – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác thực Bearer JWT và xử lý authorities.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và kiểm tra quyền theo đối tượng.

