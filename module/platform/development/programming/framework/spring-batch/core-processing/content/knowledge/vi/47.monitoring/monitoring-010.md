# Correlation với request hoặc scheduler trong monitoring Spring Batch

Một batch job có thể chạy trong vài giây, vài phút hoặc hàng giờ. Khi một lần chạy thất bại, câu hỏi đầu tiên của đội vận hành thường không phải “exception gì?” mà là: **“Lần chạy này xuất phát từ yêu cầu nào, scheduler nào, xử lý kỳ dữ liệu nào và đã tạo ra kết quả gì?”**

Trong ứng dụng web, yêu cầu ban đầu có thể kết thúc ngay sau khi trả `202 Accepted` nhưng job tiếp tục chạy trên thread khác. Trong hệ thống scheduler, cùng một job có thể được kích hoạt nhiều lần bởi các node khác nhau hoặc bởi một lần retry. Nếu log chỉ có tên job và nội dung exception, rất khó nối nguyên nhân khởi chạy với trạng thái thực thi, dữ liệu đầu vào và các tác động đầu ra.

**Correlation** là kỹ thuật gắn các sự kiện liên quan vào cùng một chuỗi quan sát bằng những định danh ổn định. Với Spring Batch, cần liên kết **request/scheduler trigger → launch attempt → JobInstance → JobExecution → StepExecution → log, trace, metric và kết quả**.

Bài này thuộc **Spring Batch Core Processing → Monitoring**, tập trung vào thiết kế correlation ID, cách truyền thông tin từ HTTP hoặc scheduler vào job, theo dõi qua `JobRepository`, xử lý chạy bất đồng bộ, MDC/tracing, retry/restart, launch trùng và nguyên tắc quan sát an toàn. Ví dụ sử dụng Spring Batch 5.x, Java 17+ và Spring Boot; các tên bảng, field và endpoint ứng dụng chỉ là minh họa.

## 1. Vì sao correlation quan trọng trong batch?

Giả sử một REST API nhận lệnh nhập dữ liệu ngày `2026-11-15`:

~~~text
09:00:00  Client -> POST /imports
09:00:00  API -> 202 Accepted, requestId=req-301
09:00:01  Job importOrdersJob bắt đầu trong background
09:03:40  Step validateOrdersStep hoàn thành
09:08:12  Step writeOrdersStep thất bại
~~~

Nếu ở thời điểm 09:08:12 log chỉ ghi `writeOrdersStep FAILED`, người vận hành chưa biết lỗi này thuộc HTTP request nào. Nếu có thêm hai lần nhập cùng ngày, việc chỉ dựa vào timestamp càng dễ dẫn đến nhầm lẫn.

Đối với scheduler, tình huống tương tự:

~~~text
01:00:00  Scheduler trigger: dailyImportJob cho businessDate=2026-11-15
01:00:02  Batch JobExecution=8102 bắt đầu
01:04:30  JobExecution=8102 FAILED
01:10:00  Scheduler/Operator retry cùng kỳ nghiệp vụ
01:10:01  JobExecution=8103 bắt đầu, cùng JobInstance
~~~

Muốn hiểu toàn bộ chuỗi, hệ thống phải lưu được quan hệ giữa **kỳ xử lý**, **lần kích hoạt** và **lần thực thi**. Khi restart, `JobExecution` thay đổi nhưng `JobInstance` có thể giữ nguyên. Khi một client retry yêu cầu launch, correlation ID của request mới lại có thể khác correlation ID của lần đầu. Vì vậy không thể dùng một ID duy nhất thay thế cho tất cả khái niệm.

## 2. Những loại định danh cần phân biệt

| Định danh | Đại diện cho | Có thay đổi khi nào? | Công dụng |
|---|---|---|---|
| `requestId` | Một HTTP request đến API. | Thường mới cho mỗi request; client retry có thể gửi cùng hoặc khác ID tùy hợp đồng. | Tìm log của request, trả lời người gọi. |
| `schedulerTriggerId` / `fireId` | Một lần scheduler kích hoạt. | Mỗi lần trigger; một số scheduler có ID riêng. | Truy nguồn lịch, trigger, lần retry. |
| `correlationId` | Một chuỗi sự kiện cần quan sát chung. | Theo quy ước hệ thống; thường phát sinh ở điểm vào và được lan truyền. | Nối log, audit và trace qua thành phần. |
| `traceId` / `spanId` | Một distributed trace / span trong hệ thống tracing. | Theo vòng đời trace/span; job dài hạn có thể dùng trace mới liên kết trace cũ. | Phân tích quan hệ dịch vụ và thời gian. |
| `businessKey` | Đơn vị công việc nghiệp vụ, như ngày + nguồn dữ liệu. | Đổi khi công việc thực sự khác. | Phân biệt kỳ xử lý và chống duplicate launch. |
| `jobInstanceId` | Một `JobInstance` trong `JobRepository`. | Giữ nguyên giữa các restart của cùng instance. | Theo dõi một công việc batch logic. |
| `jobExecutionId` | Một lần thử chạy của `JobInstance`. | Mới mỗi execution/restart. | Tra cứu trạng thái và lỗi của lần chạy cụ thể. |
| `stepExecutionId` | Một lần thực thi của step trong job execution. | Có thể khác qua retry/restart execution. | Tìm lỗi trong một step cụ thể. |

**`correlationId` không phải `jobExecutionId`.** Một HTTP request có thể chưa tạo được execution; ngược lại, một JobInstance có thể có nhiều execution do restart. Hai request trùng có thể cùng nhắm tới một JobInstance nhưng chỉ một request được launcher chấp nhận.

Trong vận hành, bộ khóa hữu ích thường là:

~~~text
correlationId + jobName + businessKey
    -> jobInstanceId
    -> jobExecutionId
    -> stepExecutionId
~~~

Không phải mỗi log đều bắt buộc có đủ mọi trường. Log nhận HTTP request có thể chưa có `jobExecutionId`; log của step đã bắt đầu nên gắn được execution ID tương ứng.

## 3. Sơ đồ luồng correlation từ nguồn kích hoạt đến đầu ra

~~~mermaid
flowchart TD
    H["HTTP request\nrequestId / correlationId"] --> L["Launch service"]
    S["Scheduler trigger\nfireId / correlationId"] --> L
    L --> A["Launch attempt log / audit"]
    L --> J["JobLauncher"]
    J --> R["JobRepository\nJobInstance + JobExecution"]
    J --> E["JobExecutionListener"]
    E --> T["StepExecution / Reader / Processor / Writer"]
    T --> O["Logs / traces / metrics"]
    R --> Q["Status API / dashboard"]
    A --> Q
    O --> Q
~~~

Có ba điểm chuyển giao ngữ cảnh cần thiết kế:

1. **Tại điểm vào:** xác định nguồn kích hoạt, business key, request/trigger ID và correlation ID.
2. **Tại lúc launch:** lưu correlation cần cho job vào metadata bền vững hoặc một bảng audit, rồi nhận `jobExecutionId` từ launcher nếu việc tạo execution thành công.
3. **Trong khi chạy:** gắn `jobExecutionId`, `jobInstanceId` và correlation ID vào log/trace của job và step; khi hoàn tất, ghi trạng thái cuối và thông tin lỗi.

Nếu chỉ đặt `correlationId` trong MDC của HTTP thread rồi khởi chạy job bất đồng bộ, thông tin này có thể mất ở bước 2. MDC dựa trên thread local và không tự trở thành metadata được Spring Batch lưu.

## 4. Chọn correlation ID và quy ước truyền từ HTTP

Một quy ước dễ thực hiện:

- Client có thể gửi `X-Request-ID` hoặc một correlation header được hệ thống chấp nhận.
- Gateway/API xác thực định dạng và giới hạn độ dài; nếu thiếu hoặc không hợp lệ, tạo một ID mới.
- API ghi ID vào log ngay khi nhận request, đưa nó vào launch context và trả lại trong response/header để người gọi có thể cung cấp khi báo lỗi.
- Những hệ thống gọi tiếp sử dụng cùng correlation ID khi mục tiêu là theo dõi một luồng công việc; nếu có trace context chuẩn, truyền qua các header W3C Trace Context theo hạ tầng tracing.

Ví dụ HTTP:

~~~http
POST /batch/import-orders HTTP/1.1
Content-Type: application/json
X-Request-ID: req-20261115-301

{"businessDate":"2026-11-15","sourceId":"warehouse-A"}
~~~

Một response có thể mang:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
X-Request-ID: req-20261115-301

{
  "correlationId": "req-20261115-301",
  "jobInstanceId": 410,
  "jobExecutionId": 8102,
  "status": "STARTING"
}
~~~

`STARTING` chỉ là trạng thái ví dụ tại thời điểm phản hồi; nếu launcher đồng bộ thì job có thể đã `COMPLETED`/`FAILED` trước khi API trả lời. Với launcher bất đồng bộ, `202` biểu thị yêu cầu đã được nhận để thực thi, **không** cam kết job xử lý dữ liệu thành công.

**Không tin tuyệt đối vào header bên ngoài.** Correlation ID do client tự cung cấp là dữ liệu không đáng tin cậy: cần giới hạn ký tự, độ dài, loại bỏ xuống dòng/control characters để tránh log injection, và không gắn thông tin cá nhân hoặc token truy cập vào ID.

Nếu cần idempotency HTTP, có thể dùng thêm `Idempotency-Key` theo hợp đồng riêng. Một ID để liên kết log **không tự bảo đảm** request được xử lý đúng một lần.

## 5. Truyền correlation vào Spring Batch bằng JobParameters

`JobParameters` là cách đơn giản để đưa một số thông tin launch vào `JobExecution` và lưu chúng trong `JobRepository`. Nhưng phải phân biệt:

- **Identifying parameters:** xác định `JobInstance` (ví dụ `businessDate` và `sourceId`).
- **Non-identifying parameters:** metadata phụ trợ thay đổi theo mỗi lần launch (ví dụ `correlationId` và `triggerType`).

Ví dụ:

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", LocalDate.of(2026, 11, 15).toString(), true)
    .addString("sourceId", "warehouse-A", true)
    .addString("correlationId", "req-20261115-301", false)
    .addString("triggerType", "HTTP", false)
    .toJobParameters();
~~~

Vì `correlationId` được đặt **non-identifying**, request retry cùng ngày và nguồn không tự tạo `JobInstance` mới chỉ vì có ID theo dõi khác. Đây là lựa chọn phù hợp khi mục tiêu là **cùng một công việc nghiệp vụ → cùng JobInstance**.

Ngược lại:

~~~java
// Anti-pattern cho batch chạy một lần trên mỗi kỳ nghiệp vụ:
.addString("correlationId", randomId, true)
~~~

Mỗi correlation ID mới sẽ khiến key instance khác nhau. Nếu scheduler tạo một UUID cho mỗi trigger, cấu hình trên vô tình biến các yêu cầu trùng nghiệp vụ thành những instance riêng.

### Những giới hạn của JobParameters

`JobParameters` được lưu trong repository và thường được dùng trong logic job. Vì vậy:

- Chỉ lưu thông tin có kích thước vừa phải và chấp nhận được trong metadata, không phải cả HTTP payload.
- Không ghi password, access token, PII nhạy cảm hoặc headers chứa thông tin xác thực.
- Không dùng job parameter làm kho audit cho **mọi request bị từ chối**: khi một lần launch trùng bị ngăn trước khi tạo execution mới, correlation ID của lần bị từ chối có thể **không** được ghi thành một `JobExecution`.
- Không giả định correlation ID bền vững qua mọi restart như business key. Một execution restart có thể đến từ request/scheduler trigger khác. Muốn theo dõi **cả chuỗi instance**, sử dụng thêm `jobInstanceId`/business key.

Một bảng audit riêng là lựa chọn phù hợp khi cần lưu mọi launch attempt và gắn nhiều request/trigger với cùng JobInstance.

## 6. Service launch chung cho HTTP và scheduler

Để hai nguồn kích hoạt tạo metadata giống nhau, xây một service nhận `businessDate`, `sourceId`, `triggerType` và `correlationId`. Trạng thái của `JobRepository` vẫn quyết định lần chạy có được phép bắt đầu.

~~~java
import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ImportLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public ImportLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(
            LocalDate businessDate,
            String sourceId,
            String triggerType,
            String correlationId)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        JobParameters params = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("sourceId", sourceId, true)
            .addString("triggerType", triggerType, false)
            .addString("correlationId", correlationId, false)
            .toJobParameters();

        return jobLauncher.run(importOrdersJob, params);
    }
}
~~~

Trong ví dụ này `businessDate` + `sourceId` đại diện cho kỳ xử lý nghiệp vụ. Hai nguồn HTTP và scheduler cùng gửi công việc ấy sẽ nhắm tới cùng `JobInstance`. `triggerType` và `correlationId` giải thích **ai yêu cầu** nhưng không làm thay đổi công việc cần xử lý.

Tùy chính sách, một request đến khi instance đã `COMPLETED` có thể bị `JobInstanceAlreadyCompleteException`; khi đang chạy có thể bị `JobExecutionAlreadyRunningException`. Trong trường hợp trước đó `FAILED` và job cho phép restart, lời gọi cùng identifying parameters có thể tạo **JobExecution mới của cùng JobInstance**.

**Luồng audit cần ghi cả launch attempt thành công và thất bại.** Service có thể ghi log vào thời điểm bắt đầu với correlation ID trước khi gọi launcher; sau khi launcher trả về, ghi thêm execution ID. Khi launcher ném exception, ghi outcome và business key đã yêu cầu, sau đó tra cứu execution hiện tại nếu cần liên kết người gọi tới lần chạy đã tồn tại.

## 7. Khởi chạy từ REST API: request kết thúc trước job

Với API, có hai vòng đời độc lập:

1. **Request lifecycle:** nhận yêu cầu, xác thực, quyết định launch, trả response.
2. **Job lifecycle:** tạo execution, chạy step/chunk, ghi checkpoint và kết thúc.

Nếu job bất đồng bộ, request có thể kết thúc chỉ sau vài mili giây còn job chạy nhiều phút. Vì vậy không nên chỉ dựa vào servlet filter hoặc request MDC để gắn correlation cho batch.

Một controller minh họa:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.batch.core.JobExecution;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record ImportRequest(LocalDate businessDate, String sourceId) {}

record LaunchResponse(
    Long jobInstanceId,
    Long jobExecutionId,
    String correlationId,
    String status
) {}

@RestController
@RequestMapping("/batch")
class ImportController {

    private final ImportLaunchService launchService;

    ImportController(ImportLaunchService launchService) {
        this.launchService = launchService;
    }

    @PostMapping("/import-orders")
    ResponseEntity<LaunchResponse> launch(
            @RequestBody ImportRequest request,
            @RequestHeader(value = "X-Request-ID", required = false)
            String incomingRequestId) throws Exception {

        // Demo: thực tế cần validate định dạng/độ dài header.
        String correlationId =
            incomingRequestId == null || incomingRequestId.isBlank()
                ? UUID.randomUUID().toString()
                : incomingRequestId;

        JobExecution execution = launchService.launch(
            request.businessDate(),
            request.sourceId(),
            "HTTP",
            correlationId
        );

        LaunchResponse response = new LaunchResponse(
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            correlationId,
            execution.getStatus().name()
        );
        return ResponseEntity.accepted()
            .header("X-Request-ID", correlationId)
            .body(response);
    }
}
~~~

Ví dụ này tập trung vào đường truyền correlation. Một API production còn cần kiểm tra request body, xác thực quyền, mapping ngoại lệ của launcher và lưu kết quả launch attempt. Nếu controller bắt mọi exception rồi trả `500` không phân biệt, client sẽ khó biết yêu cầu đã có execution chạy hay chưa.

Nên có endpoint theo dõi như:

~~~http
GET /batch/executions/8102
~~~

Response có thể chứa `jobExecutionId`, `jobInstanceId`, `jobName`, business key, trạng thái `STARTED/COMPLETED/FAILED`, thời gian bắt đầu/kết thúc và thông tin lỗi đã được rút gọn. Khi query chi tiết từ `JobExplorer`, phải xác thực quyền truy cập vì metadata có thể chứa tham số nghiệp vụ.

### Không nhầm “request nhận thành công” với “job thành công”

Khi API trả `202 Accepted`, đó là dấu mốc request được chấp nhận, không phải một bằng chứng toàn bộ batch đã hoàn tất. Trong dashboard nên hiển thị riêng:

| Mốc | Ví dụ | Đánh giá |
|---|---|---|
| `launch.requested` | API nhận request lúc 09:00:00 | Ghi dấu yêu cầu đến. |
| `launch.accepted` | JobExecution 8102 được tạo | Batch đã có execution để theo dõi. |
| `job.started` | Execution chuyển vào giai đoạn thực thi | Công việc thực tế bắt đầu. |
| `step.failed` | writeOrdersStep lỗi lúc 09:08:12 | Lỗi nằm ở step cụ thể. |
| `job.failed` | JobExecution 8102 `FAILED` | Kết quả cuối không thành công. |

Không nên gộp tất cả thành một metric “request success” hoặc một trường `status=OK`.

## 8. Khởi chạy từ scheduler: trigger identity và kỳ nghiệp vụ

Scheduler không có HTTP request ID, nhưng luôn có thông tin nguồn kích hoạt. Nếu scheduler như Quartz cung cấp fire identifier, trigger name và scheduled fire time, có thể chuyển các trường cần thiết vào monitoring. Nếu chỉ dùng `@Scheduled` của Spring, ứng dụng có thể tự tạo `schedulerTriggerId` cho mỗi lần callback, đồng thời dùng tên lịch cố định để nhận biết nguồn.

Ví dụ chạy 01:00 theo múi giờ nghiệp vụ, xử lý ngày hôm trước:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class DailyImportScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final ImportLaunchService launchService;

    DailyImportScheduler(ImportLaunchService launchService) {
        this.launchService = launchService;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    void importPreviousBusinessDay() throws Exception {
        LocalDate businessDate =
            LocalDate.now(BUSINESS_ZONE).minusDays(1);

        String correlationId = UUID.randomUUID().toString();

        launchService.launch(
            businessDate,
            "warehouse-A",
            "SCHEDULER",
            correlationId
        );
    }
}
~~~

Ví dụ dùng UUID làm **correlation ID non-identifying** cho từng lần scheduler kích hoạt, còn `businessDate` và `sourceId` là identifying. Hai pod cùng đến giờ chạy vẫn tạo cùng `JobInstance` nếu dùng repository chia sẻ và cùng quy tắc tính ngày.

Các thông tin scheduler hữu ích gồm:

| Trường | Ví dụ | Vai trò |
|---|---|---|
| `triggerType` | `SCHEDULER` | Phân biệt nguồn với HTTP/manual/event. |
| `scheduleName` | `daily-order-import` | Định danh lịch cấu hình. |
| `scheduledFor` | `2026-11-16T01:00:00+07:00` | Thời điểm dự kiến chạy, phục vụ so sánh với thời điểm thực tế. |
| `firedAt` | `2026-11-16T01:00:02+07:00` | Thời điểm callback được kích hoạt. |
| `schedulerTriggerId` | `fire-782` | Định danh một lần kích hoạt, nếu scheduler có. |
| `businessDate` | `2026-11-15` | Kỳ dữ liệu cần xử lý. |
| `correlationId` | `e6f7...` | Nối log của callback với execution được tạo. |

Chỉ có `@Scheduled` không tự cung cấp `fireId` chuẩn giống một số scheduler chuyên dụng. Nếu cần audit lịch chính xác (misfire, retry, cluster coordination), hãy dùng metadata thực do scheduler cung cấp hoặc lưu một record trigger riêng.

**Phân biệt `scheduledFor` với `businessDate`.** Lịch chạy ngày 16 có thể xử lý dữ liệu ngày 15. Nếu một node tính ngày theo UTC còn node khác theo giờ Việt Nam, chúng có thể tạo hai business key khác nhau cho cùng ý định xử lý.

## 9. Gắn correlation vào log bằng MDC

`Mapped Diagnostic Context` (MDC) của SLF4J/Logback cho phép thêm trường ngữ cảnh vào các log được ghi trên thread có MDC tương ứng. Với batch, một `JobExecutionListener` có thể cài correlation ID và execution ID ở thời điểm job bắt đầu, rồi dọn chúng sau khi job kết thúc.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CorrelationJobExecutionListener
        implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(CorrelationJobExecutionListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        install(execution);
        log.info("batch.job.started");
    }

    @Override
    public void afterJob(JobExecution execution) {
        try {
            install(execution);
            log.info("batch.job.finished status={} exitCode={}",
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
        } finally {
            MDC.remove("correlationId");
            MDC.remove("jobName");
            MDC.remove("jobInstanceId");
            MDC.remove("jobExecutionId");
        }
    }

    private void install(JobExecution execution) {
        String correlationId =
            execution.getJobParameters().getString("correlationId");

        if (correlationId == null || correlationId.isBlank()) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }

        MDC.put("jobName",
            execution.getJobInstance().getJobName());
        MDC.put("jobInstanceId",
            String.valueOf(execution.getJobInstance().getInstanceId()));
        MDC.put("jobExecutionId",
            String.valueOf(execution.getId()));
    }
}
~~~

Gắn listener vào job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step readAndWriteOrdersStep,
        CorrelationJobExecutionListener correlationListener) {
    return new JobBuilder("importOrdersJob", jobRepository)
        .listener(correlationListener)
        .start(readAndWriteOrdersStep)
        .build();
}
~~~

Trong trường hợp job chạy trên một thread theo cách thông thường, MDC đã được gắn trong `beforeJob` có thể xuất hiện ở log của các xử lý trên cùng thread. Tuy nhiên **MDC là ThreadLocal**, nên listener không tự bảo đảm correlation xuất hiện trong mọi worker thread của step, executor bất đồng bộ hoặc thư viện có thread pool riêng.

`afterJob` dọn MDC để các thread được tái sử dụng không mang thông tin của execution trước. Với pipeline bất đồng bộ hoặc listener custom, cũng nên kiểm soát cleanup ở đúng ranh giới thread/task: nếu lỗi xảy ra trước khi listener kết thúc bình thường, cách đặt ngữ cảnh cần có chiến lược dọn phù hợp.

### Một dòng log có cấu trúc

~~~json
{
  "timestamp": "2026-11-16T09:08:12+07:00",
  "level": "ERROR",
  "event": "batch.step.failed",
  "correlationId": "req-20261115-301",
  "triggerType": "HTTP",
  "jobName": "importOrdersJob",
  "jobInstanceId": 410,
  "jobExecutionId": 8102,
  "stepName": "writeOrdersStep",
  "stepExecutionId": 9204,
  "businessDate": "2026-11-15",
  "sourceId": "warehouse-A",
  "errorCode": "OUTPUT_WRITE_FAILED"
}
~~~

Đây là **một ví dụ schema log do ứng dụng lựa chọn**, không phải danh sách trường mà Spring Batch tự xuất ra mặc định. Để tạo JSON log, cần cấu hình logging encoder phù hợp; `MDC.put` chỉ đặt field trong ngữ cảnh logging, không tự quyết định format đầu ra.

Trong log lỗi, nên giữ stack trace có ích ở hệ thống log nội bộ, đồng thời dùng `errorCode` ổn định để lọc và tổng hợp. Không đưa toàn bộ item chứa dữ liệu nhạy cảm vào log chỉ để tiện truy vết.

## 10. Correlation trong Step, chunk và xử lý đa luồng

Ở mức step, các trường hữu ích thêm là `stepName` và `stepExecutionId`. Có thể dùng `StepExecutionListener` để gắn các trường này khi một step bắt đầu và dọn sau khi kết thúc:

~~~java
import org.slf4j.MDC;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class CorrelationStepExecutionListener
        implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        MDC.put("stepName", stepExecution.getStepName());
        MDC.put("stepExecutionId",
            String.valueOf(stepExecution.getId()));
    }

    @Override
    public org.springframework.batch.core.ExitStatus afterStep(
            StepExecution stepExecution) {
        MDC.remove("stepName");
        MDC.remove("stepExecutionId");
        return null; // Không thay đổi ExitStatus hiện tại.
    }
}
~~~

`StepExecutionListener.afterStep(...)` có thể trả `null` khi không muốn thay đổi exit status. Listener mẫu giúp gắn MDC cho các callback trên **cùng thread**; nó chưa xử lý trường hợp item processing chạy trên những executor worker riêng.

### Khi dùng TaskExecutor hoặc partitioning

Một step đa luồng, asynchronous item processor, partitioned step hoặc remote chunking có thể xử lý item trên thread/process khác:

~~~text
Job thread (MDC: correlationId=A)
    |
    +--> Worker thread 1: read/process/write
    +--> Worker thread 2: read/process/write
    +--> Remote worker JVM: xử lý partition
~~~

MDC của job thread không tự truyền sang worker. Với Spring `ThreadPoolTaskExecutor`, có thể gắn một `TaskDecorator` để chụp ngữ cảnh lúc submit task và khôi phục trong worker:

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;
import org.springframework.context.annotation.Bean;

@Bean
TaskDecorator mdcTaskDecorator() {
    return task -> {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
~~~

Phải **gắn decorator vào đúng executor thực sự được step sử dụng**, ví dụ qua `ThreadPoolTaskExecutor.setTaskDecorator(...)`. Chỉ khai báo một bean `TaskDecorator` không có nghĩa mọi executor trong ứng dụng tự sử dụng nó. Decorator chụp MDC của thread submit tại thời điểm task được giao; nếu submitter chưa có correlation thì worker vẫn không nhận được thông tin mong đợi.

Đối với remote partitioning hoặc message-driven workers, cần đưa correlation fields vào **message headers/payload** với quy tắc truyền nhận và xác thực rõ ràng; một `TaskDecorator` trong JVM của manager không thể truyền ThreadLocal sang JVM khác. Worker nhận message cần tạo lại log context của chính nó và dọn sau xử lý.

Ngoài MDC, luôn giữ **định danh bền vững** (job/step execution IDs, business key) trong metadata hoặc payload. MDC giúp log dễ tìm, nhưng không phải nguồn chân lý cho việc restart hoặc xác định trạng thái batch.

## 11. Distributed tracing: liên kết request trace và batch execution

Tracing theo chuẩn như OpenTelemetry thường dùng `traceId`, `spanId` và quan hệ parent/child để thấy thời gian gọi qua các dịch vụ. Nhưng job chạy hàng giờ hoặc được xử lý không đồng bộ có vòng đời khác request HTTP chỉ kéo dài vài mili giây.

Hai cách biểu diễn có ý nghĩa:

1. **Cùng trace qua một chuỗi công việc có vòng đời phù hợp:** các span ngắn tiếp tục truyền ngữ cảnh qua bước async bằng hạ tầng tracing.
2. **Trace mới cho job, liên kết tới trace yêu cầu kích hoạt:** lưu `triggerTraceId` hoặc tạo **Span Link** tới ngữ cảnh trước đó nếu hạ tầng tracing hỗ trợ. Cách này phù hợp khi job có vòng đời dài, chạy theo scheduler hoặc được restart sau nhiều giờ.

Một mô hình:

~~~text
HTTP Trace T1
  └─ span POST /batch/import-orders
       └─ launch accepted, jobExecutionId=8102

Batch Trace T2  [link to T1]
  ├─ jobExecutionId=8102
  ├─ Step readOrders
  └─ Step writeOrders
~~~

Nếu job không xuất phát từ HTTP mà từ scheduler, có thể tạo trace tại lúc scheduler fire, sau đó tạo trace/span theo vòng đời batch. `correlationId` là cầu nối thuận tiện giữa log, audit và các trace; `jobExecutionId` là khóa tới `JobRepository`.

**Không mặc định Spring Batch tự tạo đúng toàn bộ quan hệ trace trên mọi phiên bản/thư viện.** Spring Boot Actuator, Micrometer Observation/Tracing và OpenTelemetry cung cấp các thành phần quan sát; độ phủ instrumentation, việc truyền context bất đồng bộ và cách xuất trace phụ thuộc phiên bản và cấu hình. Hãy xác định nơi tạo span, nơi link span và field nào được lưu bền vững trong hệ thống thực tế.

### Không dùng traceId làm business key

Một trace ID thay đổi theo yêu cầu hoặc mỗi lần retry. Nếu dùng nó làm identifying JobParameter, client retry cùng ngày có thể tạo một JobInstance mới. Trace ID phục vụ **quan sát**, còn business key phục vụ **định danh công việc**; hai vai trò không nên bị trộn lẫn.

## 12. Metrics và cardinality: ID nào nên làm tag?

Metrics phục vụ câu hỏi tổng hợp: job nào thường thất bại, thời gian chạy bao lâu, số lần retry/skip tăng ở đâu. Logs và traces phục vụ câu hỏi chi tiết: execution 8102 thất bại vì item nào.

| Field | Log/tracing | Metric label/tag |
|---|---|---|
| `jobName` | Nên có | Thường phù hợp. |
| `stepName` | Nên có ở step | Thường phù hợp nếu số step hữu hạn. |
| `status` / `exitCode` | Nên có | Thường phù hợp nếu dùng giá trị giới hạn. |
| `triggerType` | Nên có | Phù hợp nếu tập giá trị nhỏ: HTTP, SCHEDULER, MANUAL. |
| `correlationId` | Rất hữu ích | **Không nên** dùng làm tag thông thường. |
| `requestId` / `fireId` | Hữu ích | Không nên: gần như duy nhất mỗi request. |
| `jobExecutionId` / `jobInstanceId` | Hữu ích | Không nên: tăng theo mỗi execution/instance. |
| `businessDate` | Hữu ích trong log/audit | Cân nhắc; ngày khác nhau liên tục làm tăng cardinality. |
| `sourceId` | Hữu ích | Chỉ nên dùng làm tag nếu tập source nhỏ và kiểm soát được. |

Một metric gắn cả `correlationId` và `jobExecutionId` có thể tạo một chuỗi thời gian mới cho gần như mỗi lần chạy. Điều đó làm tăng tải hệ thống metrics và giảm giá trị tổng hợp. Hãy đưa high-cardinality IDs vào **log, trace hoặc audit**, rồi dùng dashboard/drilldown để chuyển từ metric tổng quan tới execution cụ thể.

Một bộ số đo hữu ích:

- Số lần launch accepted, rejected as already running, rejected as already complete.
- Số execution `COMPLETED`, `FAILED` hoặc `STOPPED` theo job/step.
- Thời lượng job và step, thời gian chờ từ trigger tới bắt đầu.
- Số item đọc, ghi, lọc, skip và retry theo phạm vi metric được hệ thống cung cấp.
- Tuổi của execution còn đang chạy và độ trễ xử lý so với `scheduledFor`.

Nếu dùng Spring Batch observability/metrics sẵn có, nên kiểm tra metric thực sự được xuất ở phiên bản ứng dụng và chỉ bổ sung custom metrics cho thông tin còn thiếu. Không mặc định tên metric hay bộ tag giống nhau giữa mọi phiên bản.

## 13. Correlation khi duplicate launch và HTTP retry

Đây là trường hợp dễ gây hiểu lầm trong monitoring.

Giả sử:

~~~text
Request A: correlationId=req-A
            businessDate=2026-11-15, sourceId=warehouse-A
            -> JobInstance 410, JobExecution 8102 STARTED

Request B: correlationId=req-B (retry / nhấn nút lần hai)
            businessDate=2026-11-15, sourceId=warehouse-A
            -> launch bị từ chối vì instance 410 đang chạy
~~~

`req-B` không tự động xuất hiện trong JobParameters của `JobExecution 8102`. Execution 8102 đã được tạo bởi request A; B là một **launch attempt riêng**. Muốn người vận hành tìm `req-B` và đến đúng job đang chạy, API cần log/audit B cùng business key và, nếu tra cứu được, `jobInstanceId=410`/`jobExecutionId=8102`.

Một bảng audit minh họa cho PostgreSQL:

~~~sql
CREATE TABLE batch_launch_attempt (
    launch_attempt_id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(100) NOT NULL,
    trigger_type VARCHAR(30) NOT NULL,
    job_name VARCHAR(100) NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outcome VARCHAR(40) NOT NULL,
    job_instance_id BIGINT,
    job_execution_id BIGINT
);

CREATE INDEX idx_batch_launch_correlation
    ON batch_launch_attempt(correlation_id);
~~~

Các `outcome` có thể là `REQUESTED`, `ACCEPTED`, `ALREADY_RUNNING`, `ALREADY_COMPLETE`, `RESTART_ACCEPTED` hoặc `ERROR` theo chính sách ứng dụng. Đây là bảng **audit tùy chọn do ứng dụng tự quản lý**, không thuộc các bảng metadata chuẩn của Spring Batch.

Khi cập nhật audit, cần nghĩ đến crash giữa việc tạo execution và ghi kết quả audit. Nếu quan hệ đó là yêu cầu nghiệp vụ nghiêm ngặt, phải có transaction hoặc cơ chế đối soát/reconcile thích hợp; không nên giả định hai lệnh ghi ở hai hệ thống khác nhau tự có atomicity.

Một kho audit còn hữu ích khi nhiều kênh kích hoạt cùng một job: scheduler, API và message listener đều có thể dùng chung cách ghi launch attempt.

## 14. Restart và chuỗi correlation nhiều execution

Khi một `JobExecution` thất bại và được restart hợp lệ, `JobInstance` vẫn là cùng công việc logic nhưng execution mới có ID khác. Nguồn khởi chạy restart cũng có thể khác nguồn ban đầu:

~~~text
JobInstance=410  businessDate=2026-11-15  sourceId=warehouse-A
  |
  +-- JobExecution=8102
  |   correlationId=fire-782
  |   triggerType=SCHEDULER
  |   status=FAILED
  |
  +-- JobExecution=8103
      correlationId=req-restart-15
      triggerType=HTTP
      status=COMPLETED
~~~

Để xem toàn bộ lịch sử kỳ dữ liệu, tìm theo **`JobInstance 410`** hoặc business key; để điều tra một lần lỗi cụ thể, tìm theo **`JobExecution 8102`**; để hiểu ai đã yêu cầu restart, tìm theo **`correlationId=req-restart-15`**.

Trong một số luồng, caller còn cần `parentCorrelationId` hoặc `restartOfExecutionId` nhằm mô tả nguồn gốc restart. Nếu lưu thêm các trường này ở JobParameters, nên đánh dấu non-identifying khi chúng chỉ dùng để quan sát. Các trường bổ sung không thay thế quan hệ execution-instance chuẩn trong `JobRepository`.

### Một job kích hoạt job khác

Nếu `parentJob` tạo yêu cầu chạy `childJob`, child có JobInstance/Execution riêng. Có thể lưu `parentJobExecutionId` và `parentCorrelationId` ở metadata/audit của child, đồng thời tạo correlation ID phù hợp với chuỗi gọi:

~~~text
Request req-301
  -> parentJobExecution=8102
        -> childJobExecution=8110
~~~

Không tự tạo job instance mới mỗi lần gọi child chỉ vì parent execution ID thay đổi khi restart, trừ khi parent execution ID thực sự là một phần của định danh nghiệp vụ child. Quan hệ cha-con là **observability lineage**; business key của child cần được thiết kế theo công việc mà child xử lý.

## 15. Tìm lỗi theo correlation: ví dụ điều tra thực tế

Giả sử người dùng báo “Lệnh nhập ngày 15 chưa có kết quả”, cung cấp `req-20261115-301`.

Luồng điều tra khả dụng:

1. **Tìm entry point.** Tra log hoặc audit theo `correlationId` để biết request/trigger đến lúc nào, nguồn kích hoạt, business key và launch outcome.
2. **Tra execution.** Nếu outcome `ACCEPTED`, lấy `jobExecutionId`; nếu `ALREADY_RUNNING`, tra execution đang liên quan qua business key/`JobInstance`.
3. **Đọc metadata Spring Batch.** Qua `JobExplorer`/dashboard, kiểm tra `BatchStatus`, `ExitStatus`, thời gian bắt đầu/kết thúc và từng `StepExecution`.
4. **Khoanh vùng step.** Lọc log theo `jobExecutionId`, `stepExecutionId` và event lỗi; đối chiếu read/write/skip count với dữ liệu kỳ xử lý.
5. **Xác nhận đầu ra.** Tra các bản ghi writer tạo hoặc file/messaging result bằng business key; không chỉ dựa vào trạng thái API `202`.
6. **Liên kết retry/restart.** Nếu execution đầu `FAILED`, tra các execution tiếp theo của cùng `JobInstance` và launch attempt dẫn đến restart.

Một timeline minh họa:

| Thời điểm | Event | Correlation/Execution | Ý nghĩa |
|---|---|---|---|
| 09:00:00 | `launch.requested` | `req-301` | HTTP API nhận yêu cầu. |
| 09:00:00 | `launch.accepted` | `req-301` / `exec 8102` | Repository đã tạo execution. |
| 09:00:01 | `job.started` | `exec 8102` | Job bắt đầu. |
| 09:03:40 | `step.completed` | `stepExec 9203` | Bước đọc/validation hoàn tất. |
| 09:08:12 | `step.failed` | `stepExec 9204` | Writer gặp lỗi. |
| 09:08:13 | `job.failed` | `exec 8102` | Execution thất bại. |
| 09:10:00 | `launch.requested` | `req-302` | Người vận hành yêu cầu restart. |
| 09:10:01 | `launch.accepted` | `req-302` / `exec 8103` | Cùng instance, execution mới. |
| 09:14:00 | `job.completed` | `exec 8103` | Kỳ xử lý hoàn tất sau restart. |

Timeline cho thấy `req-301` và `req-302` là hai trigger khác nhau, nhưng cùng thuộc một công việc logic. Nếu dashboard chỉ gom theo correlation ID, người xem có thể tưởng là hai batch độc lập; vì vậy phải cho phép đi từ một execution tới **JobInstance và các execution liên quan**.

## 16. Correlation trong log phân tán và retention

Trong hệ thống có nhiều service, cần thống nhất tên trường và định dạng trước khi triển khai rộng:

| Field chuẩn nội bộ | Định dạng gợi ý |
|---|---|
| `correlationId` | Chuỗi UTF-8 ngắn, giới hạn ký tự và độ dài. |
| `triggerType` | Enum hữu hạn: `HTTP`, `SCHEDULER`, `MANUAL`, `MESSAGE`. |
| `jobName` | Tên job Spring Batch. |
| `jobInstanceId` / `jobExecutionId` | ID số hoặc string theo serializer của log. |
| `stepName` / `stepExecutionId` | Có khi vào scope step. |
| `businessKey` | Phiên bản chuẩn hóa có thể giải mã/tra cứu, tránh dữ liệu nhạy cảm. |
| `requestId` / `schedulerTriggerId` | ID riêng của entry point. |
| `traceId` / `spanId` | Chuẩn tracing của hệ thống, có thể không tồn tại ở mọi entry point. |
| `outcome` | Giá trị trạng thái launch/job/step được phân loại rõ. |

Với JSON log, hãy thống nhất **kiểu dữ liệu**: ví dụ `jobExecutionId` luôn là số hoặc luôn là string, không thay đổi tùy service. Đồng bộ múi giờ cho timestamp (thường dùng ISO 8601/UTC trong log) và lưu rõ `businessDate` theo timezone nghiệp vụ.

**Retention của log và metadata có thể khác nhau.** Log lưu vài ngày, `JobRepository` lưu lịch sử lâu hơn hoặc ngược lại. Nếu yêu cầu tra cứu audit sau nhiều tháng, cần một nguồn lưu có retention phù hợp. `JobRepository` là kho metadata vận hành batch; không mặc định nó thay thế audit trail pháp lý/kinh doanh.

Không log toàn bộ HTTP request hay dữ liệu từng item nếu không có nhu cầu cụ thể. Correlation hoạt động tốt khi **ID liên kết đúng**, không cần sao chép dữ liệu nhạy cảm vào mọi hệ thống.

## 17. Kiểm thử correlation từ HTTP và scheduler

Kiểm thử tốt nên quan sát quan hệ giữa request, execution và dữ liệu audit thay vì chỉ kiểm tra một đoạn log chứa ID.

| Kịch bản | Đầu vào | Điều cần xác nhận |
|---|---|---|
| HTTP request có ID | Header `X-Request-ID=req-A` | Launch ghi `correlationId=req-A`; response và audit có thể tra lại. |
| HTTP request thiếu ID | Không có header | Gateway/API sinh ID hợp lệ, trả lại và truyền vào job. |
| HTTP request có header không an toàn | ID quá dài hoặc chứa newline | Request được chuẩn hóa/từ chối theo hợp đồng, không gây log injection. |
| Scheduler chạy theo lịch | Business date cố định | Log có `triggerType=SCHEDULER` và ID trigger; execution có business key đúng. |
| Job bất đồng bộ | API trả trước khi job hoàn tất | Job log vẫn có correlation/JobExecution ID sau khi request thread kết thúc. |
| Hai launch trùng | Cùng identifying parameters, correlation khác nhau | Chỉ một execution được chấp nhận; cả hai launch attempts vẫn tra cứu được. |
| Restart sau FAILED | Cùng business key, correlation mới | JobInstance giữ nguyên; JobExecution mới; audit thể hiện nguồn restart. |
| Multi-threaded step | Worker threads khác thread launcher | Log worker có context theo thiết kế hoặc luôn tra được bằng execution metadata. |
| Remote worker | Message mang job/partition correlation | Worker từ xa nhận và log đúng ID, không dựa vào MDC của JVM gốc. |
| Metrics | Nhiều correlation ID khác nhau | Metric không tạo một time series riêng cho mỗi request/execution ID. |

Ví dụ kiểm thử cấp service có thể tạo `JobParameters` với `correlationId` khác nhau nhưng cùng `businessDate`/`sourceId`, rồi khẳng định cờ identifying đúng. Test tích hợp nên khởi chạy job thực trên repository test, đọc lại `JobExecution.getJobParameters()` và tra bảng audit ứng dụng khi có.

Với thử nghiệm async, cần điều khiển thời điểm job bắt đầu/kết thúc bằng cơ chế đồng bộ test rõ ràng. Không chứng minh correlation bằng cách `Thread.sleep(...)` và hy vọng job đã chạy: test dễ trở nên không ổn định trên CI.

## 18. Những sai lầm thường gặp

### “Đã có traceId trong HTTP log nên batch sẽ tự tìm được”

Không chắc. HTTP request có thể kết thúc trước khi job chạy. Tracing context và MDC thường chỉ tồn tại trong một phạm vi thread/task nhất định. Muốn điều tra batch nhiều giờ sau, cần **lưu ID liên kết trong metadata/audit** và truyền context tới worker khi cần log theo cùng ID.

### “Dùng correlationId làm identifying parameter để dễ truy vấn”

Điều này thường gây tạo JobInstance mới cho mỗi request, phá mục tiêu nhận diện launch trùng. Hãy giữ **business key** identifying, còn correlation ID non-identifying hoặc lưu ở bảng audit.

### “Có JobExecution ID là đủ, không cần request ID”

Một launch bị từ chối có thể chưa tạo execution mới. Nếu không log request/trigger ID tại điểm vào, sẽ không biết ai đã yêu cầu lần launch đó hoặc vì sao UI nhận “already running”.

### “Có requestId là đủ, không cần JobInstance”

Một job có thể restart với request ID mới nhưng vẫn xử lý cùng kỳ dữ liệu. Nếu chỉ tìm theo request ID, sẽ bỏ sót lịch sử execution của cùng instance.

### “MDC của launcher sẽ xuất hiện trong mọi thread”

MDC dựa trên thread local và không được truyền tự động sang mọi executor/process. Dùng task context propagation, message headers và listeners ở đúng scope. Luôn dọn MDC để thread pool không lẫn dữ liệu giữa job.

### “Mọi ID nên đưa vào metric tags”

Các ID gần như duy nhất tạo cardinality rất lớn; hệ thống metrics có thể tốn tài nguyên và khó tổng hợp. Đưa những ID đó vào log/tracing/audit; metric chỉ nên dùng các phân loại có số lượng hữu hạn.

### “Cứ lưu toàn bộ request payload vào JobParameters để điều tra”

JobParameters là metadata bền vững, có thể xuất hiện trong log hoặc dashboard; lưu secrets/PII hoặc payload lớn là rủi ro. Chỉ lưu các field cần cho định danh, thực thi và correlation; những dữ liệu lớn/nội dung nhạy cảm có nguồn lưu riêng với quyền truy cập phù hợp.

### “Scheduler fire lúc 01:00 thì businessDate chắc chắn là hôm nay”

Nhiều job xử lý ngày trước hoặc kỳ đối soát riêng. Việc tính ngày phải theo timezone nghiệp vụ và luật xác định kỳ dữ liệu, không suy luận từ thời điểm log hoặc clock của node.

## 19. Quy trình thiết kế correlation có thể áp dụng ngay

1. **Định nghĩa business key** cho job (ví dụ `businessDate` + `sourceId`) và xác định identifying parameters.
2. **Chuẩn hóa entry point** cho HTTP, scheduler, thao tác thủ công và message, gồm `triggerType`, request/trigger ID và `correlationId`.
3. **Ghi launch attempt trước khi gọi launcher**, sau đó cập nhật kết quả accepted/rejected/error, gắn `jobInstanceId`/`jobExecutionId` nếu có.
4. **Truyền metadata cần thiết vào execution**, dùng non-identifying JobParameters hoặc audit store cho correlation fields.
5. **Bổ sung log structured** ở ranh giới job/step, bao gồm trạng thái cuối và các ID từ Spring Batch.
6. **Thiết kế truyền context cho async/remote worker**, phân biệt MDC/tracing tạm thời với metadata bền vững.
7. **Xây dashboard drilldown** từ request/trigger tới JobInstance, các JobExecution và StepExecution; hỗ trợ xem chuỗi restart.
8. **Giữ metrics có cardinality phù hợp**, để ID chi tiết nằm trong logs, traces hoặc audit.
9. **Kiểm thử các trường hợp khó**, đặc biệt duplicate launch, HTTP timeout, scheduler nhiều node, restart và multi-threaded step.

## Kết luận

Trong monitoring của Spring Batch, **correlation với request hoặc scheduler** là khả năng trả lời đầy đủ: *ai đã kích hoạt job, cho kỳ dữ liệu nào, launch được chấp nhận hay bị từ chối, execution nào đã chạy, các step diễn ra ra sao và cuối cùng đầu ra có đúng không*. Để làm được điều đó cần kết hợp **ID từ entry point**, **business key**, **metadata của JobRepository**, **log/tracing có ngữ cảnh** và, khi cần, một **launch audit** lưu cả yêu cầu không tạo được execution.

Hãy giữ `businessDate`/business key ở vai trò định danh `JobInstance`; xem `correlationId` và `traceId` là thông tin quan sát; dùng `jobExecutionId` để kiểm tra từng lần thực thi và `jobInstanceId` để nhìn toàn bộ vòng đời qua restart. Khi các khóa này được liên kết rõ ràng, người vận hành có thể đi từ một HTTP request hoặc scheduler trigger đến chính xác lỗi của một step, kể cả khi request đã kết thúc từ lâu và job đang chạy ở thread hoặc node khác.
