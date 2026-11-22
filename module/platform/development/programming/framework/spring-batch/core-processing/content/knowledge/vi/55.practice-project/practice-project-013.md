# Dự án thực hành: Tạo runbook cho failure và recovery trong Spring Batch

Một batch job chạy thành công nhiều ngày liền có thể gặp sự cố vào ngày quan trọng nhất: file nguồn thiếu, schema CSV thay đổi, database hết kết nối, writer bị lỗi ở giữa chunk, một pod chết sau khi đã commit dữ liệu, hoặc API bên ngoài xử lý xong nhưng không trả response. Khi đó, đội vận hành cần biết **phải kiểm tra gì, bằng chứng nào đủ tin cậy, có được retry/restart không và làm sao xác minh dữ liệu sau phục hồi**.

Một câu trả lời kiểu “xem log rồi chạy lại job” không đủ. Trong Spring Batch, một `JobInstance` có thể có nhiều `JobExecution`; các chunk đã commit không tự rollback khi chunk sau lỗi; `JobRepository` chứa checkpoint cần cho restart; còn side effect tới file, broker hoặc HTTP không được database transaction tự động hoàn tác. Một hành động chạy lại sai key có thể tạo dữ liệu trùng dù đã xử lý được lỗi ban đầu.

**Runbook** là tài liệu vận hành theo tình huống, cung cấp một trình tự xử lý có thể lặp lại: *phát hiện → phân loại → khoanh vùng → bảo toàn bằng chứng → hành động phục hồi đã được phê duyệt → đối chiếu đầu ra → đóng sự cố*. Trong chủ đề **Spring Batch Core Processing → Dự án thực hành**, bài này hướng dẫn tạo một runbook hoàn chỉnh cho failure và recovery, kèm dự án mẫu, mẫu tài liệu, SQL đọc metadata, cách phân loại lỗi, bài diễn tập và tiêu chí bàn giao.

Ví dụ sử dụng **Spring Batch 5.x**, **Java 17+**, **Spring Boot 3.x** và **PostgreSQL**. Những tên job, đường dẫn, ID và câu lệnh đều là dữ liệu minh họa; trước khi dùng trên production phải điều chỉnh theo schema, quyền truy cập, chính sách thay đổi và hợp đồng dữ liệu của hệ thống thực tế.

## 1. Kết quả cần tạo ra sau dự án

Sau khi hoàn thành bài thực hành, người học có một **runbook có thể dùng để xử lý sự cố thực tế**, không chỉ là tài liệu giải thích API. Bộ bàn giao nên có:

| Thành phần | Nội dung cần có | Lý do |
|---|---|---|
| **Tổng quan job** | Nguồn kích hoạt, business key, input/output, phụ thuộc, thời điểm chạy. | Để người trực sự cố hiểu mình đang vận hành hệ thống nào. |
| **Bảng phân loại failure** | Dấu hiệu, nguyên nhân có thể, hành động cho phép, trường hợp phải escalation. | Không xử lý mọi exception theo một cách. |
| **Các truy vấn điều tra** | Tra `JobInstance`, `JobExecution`, `StepExecution` và dữ liệu nghiệp vụ. | Có bằng chứng thay vì suy đoán từ một dòng log. |
| **Quy trình recovery** | Điều kiện retry, restart, stop, reprocess, phục hồi tài nguyên, xử lý dữ liệu sai. | Giảm nguy cơ làm tình hình nặng hơn. |
| **Quy trình reconciliation** | Kiểm tra count, business key, tổng giá trị, skip/reject, outbox nếu có. | Xác nhận dữ liệu đúng sau khi job báo thành công. |
| **Mẫu thông báo sự cố** | Tình trạng, tác động, quyết định, người phụ trách, bằng chứng. | Giúp phối hợp nhất quán và có audit. |
| **Bộ kịch bản diễn tập** | Lỗi reader, writer, crash giữa chunk, lỗi repository, duplicate launch. | Kiểm chứng runbook có thể thực hiện được. |
| **Quy tắc bảo mật** | Không log payload/credential; hạn chế quyền thao tác dữ liệu. | Tránh rò rỉ khi đang khắc phục sự cố. |

Tài liệu này sẽ trình bày một **runbook mẫu đã điền thông tin cho một job giả định**; người học có thể dùng cấu trúc đó để chuyển thành runbook riêng của dự án mình.

## 2. Bối cảnh dự án mẫu

### 2.1. Job cần vận hành

Giả định ứng dụng có job `dailyPaymentImportJob` để nhập một file thanh toán của ngày nghiệp vụ:

~~~text
Scheduler / REST API
       |
       v
dailyPaymentImportJob
       |
       +-- preflightSourceStep
       |     Kiểm tra file, schema và source manifest
       |
       +-- importPaymentsStep
       |     CSV reader -> processor -> JDBC writer
       |     Chunk size: 100
       |
       +-- reconcilePaymentsStep
       |     Đối chiếu count, amount và tập event_id
       |
       +-- publishPaymentsStep
             Công bố batch version đã đạt quality gate
~~~

Input là CSV đặt tại một vùng tiếp nhận có version và checksum; output được ghi vào PostgreSQL dưới khóa `batchKey`. `JobRepository` dùng JDBC metadata để quản lý execution và restart. Dữ liệu giả lập, không chứa thông tin khách hàng thật.

### 2.2. Bảng thông tin vận hành

| Thuộc tính | Giá trị minh họa |
|---|---|
| Job name | `dailyPaymentImportJob` |
| Mục tiêu | Nhập giao dịch hợp lệ cho một ngày và một nguồn. |
| Trigger | Scheduler hằng ngày; API vận hành có phân quyền khi cần recovery. |
| Business key | `businessDate + sourceId + sourceVersion`. |
| Ví dụ business date | `2026-11-15` theo timezone nghiệp vụ đã thống nhất. |
| Ví dụ source ID | `warehouse-A`. |
| Ví dụ source version | `v1`. |
| Batch key | `2026-11-15:warehouse-A:v1`. |
| Identifying JobParameters | `businessDate`, `sourceId`, `sourceVersion`. |
| Non-identifying JobParameters | `correlationId`, `triggerType` khi chỉ dùng cho quan sát. |
| Source manifest | Tên nguồn logic, phiên bản, checksum, số dòng dữ liệu kỳ vọng. |
| Output | Bảng `processed_payment`, ràng buộc duy nhất `(batch_key, event_id)`. |
| Chất lượng dữ liệu | Filter/reject chỉ theo hợp đồng; publish sau reconciliation. |
| Quản lý transaction | Chunk JDBC cùng transaction manager phù hợp. |
| Metadata | Các bảng `BATCH_*` của Spring Batch. |
| Monitoring | Job/step status, counters, correlation ID, alert và log có cấu trúc. |

Đối với dự án thực tế, các mục còn thiếu như chủ sở hữu job, tài liệu SLA/SLO, endpoint dashboard, môi trường, nhóm liên hệ và quyền thao tác cần được điền trước khi runbook được đưa vào sử dụng.

### 2.3. Tập input nhỏ phục vụ diễn tập

~~~csv
event_id,currency,amount
PAY-001,USD,100.00
PAY-002,USD,50.00
PAY-003,USD,abc
PAY-004,USD,0.00
PAY-005,USD,25.00
PAY-006,USD,25.00
~~~

Giả định quy tắc của **job demo không phải sổ cái bắt buộc**:

- `PAY-001`, `PAY-002`, `PAY-005` và `PAY-006` được ghi.
- `PAY-003` bị read skip vì amount không parse được; lỗi phải có báo cáo reject.
- `PAY-004` được filter vì amount bằng 0 theo một quy tắc minh họa.
- File có **6 dòng dữ liệu, không tính header**.
- `readCount=5`, `readSkipCount=1`, `filterCount=1`, `writeCount=4` và tổng amount đầu ra bằng `200.00 USD` nếu không có lỗi khác.

**Lưu ý về nghiệp vụ:** Đây là bài tập minh họa cơ chế điều phối và đối chiếu. Với job tài chính yêu cầu không bỏ giao dịch, một lỗi parse của một bản ghi có thể phải làm toàn bộ batch **không được publish** thay vì được phép skip.

## 3. Runbook phải phân biệt trạng thái kỹ thuật và trạng thái dữ liệu

Spring Batch có các khái niệm:

- **`Job`:** định nghĩa một quy trình.
- **`JobInstance`:** công việc logic, xác định bằng tên job và identifying `JobParameters`.
- **`JobExecution`:** một lần cố gắng chạy của một instance; restart có thể tạo execution mới.
- **`StepExecution`:** metadata của lần thực thi một step, có bộ đếm và trạng thái.
- **`BatchStatus`:** trạng thái vòng đời như `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED` hoặc `UNKNOWN` theo ngữ cảnh.
- **`ExitStatus`:** kết quả thực thi dùng cho điều khiển flow và vận hành, có thể mang exit code khác trạng thái vòng đời.
- **`ExecutionContext`:** trạng thái lưu cho restart/checkpoint, không được sửa thủ công tùy tiện.

Một quy tắc runbook cần ghi nổi bật:

> **`COMPLETED` không tự chứng minh output đúng; `FAILED` không tự chứng minh output đã rollback hết.**

Trong chunk processing, chunk trước đã commit có thể tồn tại khi chunk sau thất bại. Nếu writer gọi API bên ngoài, side effect ở đó có thể tồn tại ngay cả khi transaction database rollback. Do đó quyết định recovery phải dựa trên **metadata và dữ liệu đã commit**.

### Sơ đồ thời điểm failure

~~~mermaid
flowchart TD
    A["Nhận trigger và business key"] --> B["JobRepository tạo JobExecution"]
    B --> C["Preflight nguồn"]
    C --> D["Đọc/xử lý/ghi theo chunk"]
    D --> E["Commit từng chunk"]
    E --> F["Reconciliation"]
    F --> G["Publish"]
    A -. "Trùng lịch/API request" .-> H["Duplicate launch"]
    B -. "Repository/credential lỗi" .-> I["Failure trước hoặc lúc tạo execution"]
    C -. "File/schema sai" .-> J["Failure nguồn"]
    D -. "Reader/processor/writer lỗi" .-> K["Failure trong chunk"]
    E -. "Timeout/commit outcome không rõ" .-> L["Cần xác minh trạng thái đích"]
    F -. "Count/sum/key mismatch" .-> M["Failure chất lượng dữ liệu"]
    G -. "Broker/API/file lỗi" .-> N["Failure công bố/đầu ra ngoài DB"]
~~~

Runbook phải cho người trực biết **lỗi xảy ra trước hay sau khi có `JobExecution`**, **trước hay sau commit**, và **trước hay sau publish**. Đây là những ranh giới quyết định có an toàn để chạy lại hay không.

## 4. Mẫu runbook: phần thông tin cố định

Phần đầu của một runbook cần đủ thông tin để người mới nhận ca trực bắt đầu mà không phải đoán:

~~~yaml
runbook:
  id: RB-BATCH-PAYMENTS-001
  title: "dailyPaymentImportJob - Failure & Recovery"
  ownerTeam: "Data Platform (minh họa)"
  jobName: dailyPaymentImportJob
  environment: "Điền môi trường thực tế"
  businessTimezone: "Asia/Ho_Chi_Minh"
  businessKey: ["businessDate", "sourceId", "sourceVersion"]
  metadataRepository: "Tên alias database metadata"
  businessDatabase: "Tên alias database đầu ra"
  inputManifestLocation: "Đường dẫn logic manifest"
  statusDashboard: "Đường dẫn dashboard nội bộ"
  loggingDashboard: "Đường dẫn tra correlationId/jobExecutionId"
  onCallTeam: "Nhóm trực vận hành"
  dataOwner: "Người phê duyệt chất lượng dữ liệu"
  escalationContact: "Kênh escalation nội bộ"
  lastReviewed: "Ngày kiểm tra runbook"
~~~

Các trường “điền môi trường thực tế” phải được thay bằng thông tin đã xác minh khi bàn giao runbook. Không đưa password, token, private key hoặc JDBC URL chứa secret vào tài liệu. Nếu cần chi tiết kết nối, chỉ lưu **alias/tên hệ thống** và liên kết đến nguồn cấu hình có phân quyền.

### Phạm vi trách nhiệm

| Vai trò | Trách nhiệm trong sự cố |
|---|---|
| **On-call / operator** | Nhận alert, xác định scope, thu thập metadata, thực hiện bước đọc trạng thái được phép, ghi nhật ký sự cố. |
| **Batch engineer** | Phân tích reader/processor/writer, checkpoint, retry/skip, thiết kế recovery và restart. |
| **Data owner** | Quyết định dữ liệu thiếu/sai có được bỏ, sửa hoặc reprocess không; phê duyệt publish khi cần. |
| **DB/platform engineer** | Xử lý database outage, grant, schema, connection pool, secret rotation hoặc hạ tầng scheduler. |
| **Security/on-call chuyên trách** | Phối hợp nếu nghi credential bị lộ, truy cập trái phép hoặc dữ liệu nhạy cảm rơi vào log. |
| **Incident commander** | Điều phối trường hợp ảnh hưởng rộng, ghi quyết định và thời điểm khôi phục theo quy trình tổ chức. |

Runbook nên tách rõ **quyền quan sát** (đọc log/metadata), **quyền thay đổi trạng thái** (stop/restart/rollout) và **quyền thay đổi dữ liệu** (sửa source, bù trừ, reprocess, can thiệp DB). Không coi mọi thành viên có quyền mở dashboard đều được quyền sửa metadata production.

## 5. Quy trình tiếp nhận sự cố

### Bước 1: Xác nhận alert có liên quan tới job nào

Thu thập tối thiểu:

| Trường | Ví dụ |
|---|---|
| `incidentId` | `INC-2026-1116-001` |
| `jobName` | `dailyPaymentImportJob` |
| `businessDate` | `2026-11-15` |
| `sourceId` / `sourceVersion` | `warehouse-A` / `v1` |
| `batchKey` | `2026-11-15:warehouse-A:v1` |
| `jobInstanceId` | `410` nếu đã có |
| `jobExecutionId` | `8102` nếu đã có |
| `stepName` / `stepExecutionId` | `importPaymentsStep` / `9204` |
| `correlationId` | `req-301` hoặc scheduler trigger ID |
| `detectedAt` | Timestamp kèm timezone |
| `alertSource` | Batch dashboard, metric, scheduler, API hoặc data quality gate |
| `businessImpact` | Kỳ dữ liệu chưa publish, downstream nào chịu ảnh hưởng |

Nếu lỗi xảy ra **trước khi tạo JobExecution**, có thể chưa có `jobExecutionId`. Khi đó phải truy từ scheduler/API launch attempt, correlation ID và lỗi kết nối `JobRepository`; không tự gán ID giả để nối sự kiện.

### Bước 2: Đánh giá mức ảnh hưởng

Một ví dụ phân loại nội bộ:

| Mức minh họa | Dấu hiệu | Quy tắc xử lý |
|---|---|---|
| **SEV-1** | Dữ liệu đã được công bố sai, giao dịch có nguy cơ nhân đôi, rò rỉ secret, hoặc nhiều hệ thống bị ảnh hưởng. | Chặn publish/consumer khi có quyền và cần thiết; báo incident commander, data owner và nhóm chuyên trách. |
| **SEV-2** | Một kỳ quan trọng bị trễ, job thất bại, kết quả chưa công bố hoặc reconciliation không đạt. | Điều tra theo runbook; recovery cần phê duyệt theo trách nhiệm. |
| **SEV-3** | Một nguồn không thiết yếu bị trễ, retry tạm thời đã xử lý, chưa có tác động dữ liệu. | Theo dõi và ghi nhận; đánh giá cải thiện sau sự cố. |

Đây là **ví dụ**, không phải chuẩn severity của Spring Batch. Mỗi tổ chức phải dùng chính sách SLA/SLO, mức tác động và cơ chế escalation của mình. Một lỗi kỹ thuật nhỏ vẫn có thể nghiêm trọng nếu dữ liệu mang tính pháp lý/tài chính.

### Bước 3: Tạm ngăn thiệt hại lan rộng khi cần

Nếu nghi output sai, điều cần làm trước khi restart có thể là **ngừng công bố phiên bản dữ liệu** hoặc giữ downstream ở trạng thái an toàn. Những hành động như pause scheduler, stop execution hoặc vô hiệu hóa consumer là thao tác thay đổi production: thực hiện theo quyền và thủ tục phê duyệt có sẵn, ghi rõ thời điểm và lý do.

Không tùy tiện kill pod hoặc xóa dữ liệu để “giải phóng job”. Một execution còn `STARTED` sau khi process chết và một execution vẫn đang chạy hợp lệ có thể trông tương tự trên dashboard; cần xác minh bằng dữ liệu về workload/process, lock/transaction và log.

## 6. Bước điều tra 1: đọc trạng thái từ JobRepository

Spring Batch lưu metadata trong các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và các bảng parameters/context. Nên dùng `JobExplorer`, API vận hành có phân quyền hoặc công cụ truy vấn chỉ đọc. Ví dụ dưới đây dùng tên bảng mặc định của schema Spring Batch và cú pháp PostgreSQL.

### 6.1. Tìm những JobExecution gần đây của job

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = :jobName
ORDER BY je.CREATE_TIME DESC, je.JOB_EXECUTION_ID DESC
LIMIT 20;
~~~

`:jobName` là ký hiệu **bind parameter** trong công cụ JDBC/SQL client có hỗ trợ named parameters, không phải cú pháp placeholder được mọi SQL console chấp nhận nguyên văn. Khi dùng một client khác, thay bằng cú pháp bind của client; không nối dữ liệu không tin cậy trực tiếp vào SQL string.

Với ví dụ `dailyPaymentImportJob`, cần đối chiếu kết quả với `businessDate` và `sourceVersion`. Chỉ lọc theo tên job **không đủ** vì có thể tồn tại nhiều `JobInstance` thuộc nhiều kỳ dữ liệu.

### 6.2. Kiểm tra identifying parameters

Trong schema Spring Batch 5.x, bảng parameters thường có các cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE` và `IDENTIFYING`:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :jobExecutionId
  AND PARAMETER_NAME IN (
      'businessDate', 'sourceId', 'sourceVersion', 'correlationId'
  )
ORDER BY PARAMETER_NAME;
~~~

**Bảo mật:** chỉ tra các parameter đã được xác nhận là an toàn. `JobParameters` có thể chứa dữ liệu nhạy cảm do cấu hình sai; không dùng `SELECT *` rồi copy kết quả vào chat/ticket. Trong dự án thật, có thể thay truy vấn trực tiếp bằng endpoint chỉ trả các trường allowlist.

Những điều cần ghi vào incident:

- `jobName` và **tập identifying parameters** của execution.
- `JobInstanceId` và những `JobExecutionId` khác của cùng instance.
- Có execution nào `STARTING`/`STARTED`/`STOPPING` không?
- Lần gần nhất thuộc `FAILED`, `STOPPED`, `COMPLETED` hay trạng thái đặc biệt?
- Có hai request khác correlation ID nhưng cùng business key không?

### 6.3. Kiểm tra các StepExecution

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    START_TIME,
    END_TIME,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Query cho biết step lỗi và mức độ công việc đã thực hiện. Không suy ra:

- `WRITE_COUNT=100` nghĩa chính xác 100 hàng mới đã commit: writer có thể UPSERT, tách/gộp, hoặc ghi ra hệ thống ngoài transaction.
- `ROLLBACK_COUNT=1` nghĩa toàn bộ dữ liệu job đã rollback: những chunk trước có thể còn.
- `COMPLETED` nghĩa không có dữ liệu bị skip/filter: cần đọc counters.
- `EXIT_CODE` luôn mô tả nguyên nhân gốc đầy đủ: phải kết hợp log, exception category và dữ liệu đích.

Không nên truy xuất `EXIT_MESSAGE` hay serialize toàn bộ `ExecutionContext` vào ticket nếu chúng có thể chứa raw exception, SQL parameters, payload hoặc secrets.

### 6.4. Dùng JobExplorer trong Java

Nếu ứng dụng có API vận hành nội bộ, có thể đọc execution qua `JobExplorer`:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchExecutionInspector {

    private final JobExplorer jobExplorer;

    public BatchExecutionInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException("JOB_EXECUTION_NOT_FOUND");
        }

        System.out.printf(
            "jobExecutionId=%d jobInstanceId=%d status=%s%n",
            execution.getId(),
            execution.getJobInstance().getInstanceId(),
            execution.getStatus()
        );

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf(
                "step=%s status=%s read=%d write=%d skip=%d rollback=%d%n",
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount()
            );
        }
    }
}
~~~

Đây là snippet **đọc metadata**, không thực hiện restart hoặc sửa trạng thái. Output chỉ dùng execution IDs, trạng thái và counters. API thật phải có xác thực/phân quyền; không cung cấp dữ liệu batch metadata rộng rãi cho mọi người gọi HTTP.

## 7. Bước điều tra 2: kiểm tra tiến trình, log và tài nguyên

Metadata là một nguồn thông tin quan trọng nhưng có thể **không phản ánh chính xác tình trạng process khi nó crash đột ngột**. Một `JobExecution` đang `STARTED` có thể tương ứng process còn sống, đang chờ DB lock, kẹt mạng hoặc đã chết mà chưa kịp cập nhật trạng thái.

Với deployment trên Kubernetes, các ví dụ **chỉ đọc trạng thái**:

~~~bash
# Lệnh minh họa; thay namespace/label theo hệ thống thật.
kubectl -n payments get pods -l app=payment-import
kubectl -n payments describe pod payment-import-abc123
kubectl -n payments logs deployment/payment-import --since=30m
~~~

Lệnh `logs` có thể hiển thị dữ liệu nhạy cảm nếu ứng dụng đã log sai; người dùng cần quyền phù hợp và **không copy nguyên log chứa payload/secret vào nơi chia sẻ rộng rãi**. Trước khi kết luận node đã chết, cần xem pod history, restart count, termination reason và sự kiện scheduler, không chỉ một lần `kubectl get pods`.

Các tín hiệu hữu ích:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| `correlationId` và trigger ID | Lần chạy đến từ scheduler, API, message hay thao tác thủ công? |
| `jobExecutionId` / `stepExecutionId` | Log thuộc execution nào, step nào? |
| OOMKilled, restart count, exit code container | Process có bị kill hoặc restart ngoài dự kiến? |
| Database connection pool | Có timeout lấy connection hoặc nhiều kết nối giữ quá lâu không? |
| DB locks / deadlocks | Writer có đang chờ khóa hoặc transaction không? |
| Disk/volume space | Reader/writer file có bị lỗi lưu trữ không? |
| Network/DNS/TLS | Job có thật sự kết nối được database và API đích không? |
| Outbox pending/age | DB đã commit nhưng event vẫn chưa phát? |
| Input manifest/checksum | Source file có bị thay trong lúc chạy không? |
| Scheduler overlap | Có nhiều trigger cùng business key hoặc chạy song song instance khác nhau không? |

Một log an toàn:

~~~json
{
  "event": "batch.step.failed",
  "jobName": "dailyPaymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "correlationId": "scheduler-fire-301",
  "errorCode": "DATABASE_TRANSIENT",
  "rollbackCount": 2
}
~~~

`errorCode` là giá trị **do ứng dụng chuẩn hóa**; Spring Batch không tự xuất JSON này mặc định. Không đưa email, số tài khoản, nguyên dòng CSV, exception message chưa kiểm soát, JDBC URL có password hoặc `ExecutionContext` toàn phần vào log.

## 8. Bước điều tra 3: phân loại failure trước khi hành động

Runbook cần phân loại theo **nguyên nhân có thể và mức độ an toàn khi replay**, không đơn thuần theo tên exception:

| Nhóm failure | Dấu hiệu thường gặp | Hành động đầu tiên | Khi nào không restart ngay? |
|---|---|---|---|
| **Nguồn không tồn tại/không sẵn sàng** | Preflight không thấy file/manifest, object storage báo lỗi. | Xác minh lịch bàn giao nguồn, version và quyền truy cập. | Khi nguồn đang upload dở hoặc checksum chưa chốt. |
| **Schema/format sai toàn file** | Header thiếu cột, field mapping lỗi hàng loạt. | Chặn publish, so khớp contract/sourceVersion. | Khi chưa có phiên bản nguồn đã được xác nhận. |
| **Một số record invalid** | Read/process skip tăng, reject có errorCode. | Đánh giá chính sách reject và tỷ lệ lỗi. | Khi record critical bị skip hoặc quality gate chưa đạt. |
| **Reader lỗi hạ tầng** | Network timeout, quyền `SELECT` thiếu, source DB down. | Kiểm tra kết nối/quyền và tình trạng nguồn. | Khi reader state hoặc snapshot không còn nhất quán. |
| **Writer bị DB deadlock/timeout** | Transaction rollback, SQL transient. | Xác định retry policy và tình trạng DB. | Khi output commit outcome chưa rõ hoặc writer không idempotent. |
| **Writer vi phạm constraint** | Unique, foreign key, not-null violation. | Phân biệt duplicate hợp lệ với dữ liệu sai/schema lỗi. | Khi chưa biết item nào đã commit và có được bỏ hay không. |
| **JobRepository/credential lỗi** | Không tạo execution, cập nhật checkpoint thất bại. | Khắc phục DB metadata/secret/quyền, bảo toàn lịch sử. | Khi metadata và output có nguy cơ lệch. |
| **Process crash/OOM** | Pod restart, execution còn `STARTED`. | Xác minh workload đã dừng và output đã commit. | Khi có thể vẫn còn writer/API call đang chạy. |
| **Duplicate launch** | `JobExecutionAlreadyRunningException` hoặc already complete. | Tra business key và execution hiện hữu. | Không tạo identifying parameter ngẫu nhiên để vượt guard. |
| **Outbox/broker/API failure** | Batch DB thành công nhưng event pending, HTTP timeout. | Tra trạng thái remote/outbox/idempotency key. | Khi không biết side effect ngoài DB đã xảy ra chưa. |
| **Reconciliation mismatch** | Count/sum/key không khớp nguồn manifest. | Giữ staging, điều tra missing/extra/mismatch. | Không publish chỉ vì `loadStep COMPLETED`. |
| **Job dừng theo yêu cầu** | `STOPPING` hoặc `STOPPED`. | Xác nhận ai stop, tại sao, checkpoint và kết quả. | Khi chưa có quyết định cho phép tiếp tục. |

### Phân biệt transient với permanent

Một lỗi transient như deadlock đôi khi thích hợp để retry có giới hạn/backoff. Sai schema, password hết hạn chưa được refresh, thiếu quyền, business validation sai hoặc bug processor **không tự biến mất khi retry nhiều lần**.

Không nên biến tất cả lỗi thành `.retry(Exception.class)` hoặc `.skip(Exception.class)` để tránh job đỏ. Một step có thể `COMPLETED` dù đã skip phần lớn input nếu chính sách quá rộng; quality gate mới quyết định output có được công bố hay không.

## 9. Quy tắc quyết định: quan sát, stop, retry, restart hay reprocess?

### 9.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Có incident cho một batchKey"] --> B{"Có execution đang thật sự chạy?"}
    B -->|Có| C{"Có nguy cơ ghi sai / tác động trùng?"}
    C -->|Không| D["Quan sát; kiểm tra tiến độ, timeout và hạ tầng"]
    C -->|Có| E["Escalate, cân nhắc stop/pause có phê duyệt"]
    B -->|Không hoặc đã dừng| F{"Trạng thái execution trước?"}
    F -->|COMPLETED| G["Đối chiếu output; nếu cần xử lý lại\nthiết kế revision mới"]
    F -->|FAILED/STOPPED| H["Khắc phục nguyên nhân\n+ xác minh side effect/commit"]
    F -->|STARTED tồn đọng| I["Xác minh process đã chết;\nquy trình phục hồi metadata được phê duyệt"]
    H --> J{"Restart cùng instance có an toàn?"}
    J -->|Có| K["Restart có kiểm soát\ncùng identifying parameters"]
    J -->|Không| L["Reconciliation / bù trừ /\nphương án recovery riêng"]
    K --> M["Chạy quality gate\nvà xác minh dữ liệu cuối"]
    G --> M
    L --> M
~~~

### 9.2. Các lựa chọn và điều kiện

| Lựa chọn | Khi dùng | Điều kiện bắt buộc |
|---|---|---|
| **Quan sát, không can thiệp** | Job vẫn chạy đúng, retry nằm trong giới hạn và không có nguy cơ dữ liệu sai. | Có tín hiệu tiến độ đáng tin; không bỏ qua SLA/quality alerts. |
| **Stop theo cơ chế batch** | Cần dừng an toàn khi job còn chạy và stop hỗ trợ. | Được phê duyệt; hiểu stop là yêu cầu hợp tác, không phải kill ngay lập tức. |
| **Retry trong step** | Lỗi tạm thời và thao tác replay-safe. | `retryLimit`, backoff, transaction/idempotency phù hợp. |
| **Restart JobInstance** | Execution trước `FAILED` hoặc `STOPPED` và job restartable. | Giữ identifying parameters, metadata/checkpoint, fix nguyên nhân, xác minh output. |
| **Reprocess phiên bản mới** | Kỳ đã `COMPLETED` nhưng cần làm lại vì input/logic thay đổi. | Có `revision`/`sourceVersion` có ý nghĩa, output versioning và phê duyệt nghiệp vụ. |
| **Quarantine/sửa record** | Một số record lỗi độc lập, business cho phép sửa/reject. | Record được định danh, audit, chính sách phân loại và đối chiếu sau sửa. |
| **Bù trừ/đối soát remote** | API/broker/file ngoài DB có side effect chưa rõ. | Có business key/idempotency key, xác nhận ở đích và quy trình phục hồi riêng. |
| **Can thiệp metadata thủ công** | Trường hợp ngoại lệ như execution stale, không có đường phục hồi được hỗ trợ. | Chỉ qua thủ tục được phê duyệt bởi người hiểu `JobRepository`/checkpoint; sao lưu, audit và xác minh process. |

**Cấm coi “thay timestamp, thêm `run.id` mới” là một thao tác restart.** Nếu tham số mới là identifying, Spring Batch sẽ tạo `JobInstance` khác, có nguy cơ đọc lại nguồn và ghi trùng đầu ra.

## 10. Quy trình restart an toàn của một JobInstance

Giả sử:

~~~text
Job name: dailyPaymentImportJob
Identifying parameters:
  businessDate=2026-11-15
  sourceId=warehouse-A
  sourceVersion=v1

JobInstance=410
  JobExecution=8102 FAILED
~~~

### Trước khi restart

1. **Xác nhận lần chạy cũ đã thực sự ngừng.** Không chỉ dựa trên một timestamp stale trong metadata. Kiểm tra pod/process/task bên ngoài còn đang hoạt động hay không.
2. **Đọc trạng thái JobRepository.** Ghi lại `JobInstanceId`, `JobExecutionId`, status, các `StepExecution`, checkpoint liên quan và skip/rollback counters.
3. **Khắc phục nguyên nhân gốc.** Ví dụ khôi phục DB connection, sửa grant, triển khai mapper đúng version hoặc sửa dữ liệu đã được phê duyệt.
4. **Chốt nguồn dữ liệu.** File `v1` có còn nguyên checksum không? Nếu file bị thay nội dung, phải xem xét quy trình source revision mới, không giả định checkpoint cũ tương thích.
5. **Xác minh output đã commit.** Các chunk trước có thể còn; writer phải có business key/idempotency phù hợp để chịu replay.
6. **Xác minh side effect ngoài DB.** Nếu writer từng gọi API, cần tra kết quả theo idempotency key trước khi gửi lại.
7. **Xác định quyền và phê duyệt.** Ghi người yêu cầu, người phê duyệt, điều kiện rollback của quyết định và cách theo dõi.

### Thực hiện restart

Spring Batch cung cấp `JobOperator` cho các thao tác vận hành như tra cứu, stop, restart và start. Cách gọi cụ thể tùy phiên bản/cấu hình; một dịch vụ vận hành nội bộ có thể gọi `jobOperator.restart(jobExecutionId)` đối với execution được phép restart.

~~~java
// Pseudocode trong một service vận hành có xác thực/phân quyền.
// Không gọi tùy tiện trên production mà không kiểm tra preconditions.
long newExecutionId = jobOperator.restart(8102L);
~~~

Chỉ gọi khi đã xác nhận execution trước thực sự ở trạng thái có thể restart, job không `preventRestart`, định danh và checkpoint còn đúng, nguyên nhân đã được xử lý. `restart` tạo `JobExecution` mới cho **cùng JobInstance**; nó không tạo dữ liệu mới bằng cách thay identifying parameters.

Trong một số hệ thống, recovery được kích hoạt bằng `JobLauncher.run(job, sameIdentifyingParameters)` khi execution trước `FAILED`/`STOPPED` và job cho phép restart. Nếu có non-identifying parameters thay đổi để ghi correlation mới, cần hiểu chúng **không đổi danh tính JobInstance**. Chính sách vận hành phải chọn một đường nhất quán, không thực hiện nhiều lệnh restart song song.

### Sau restart

1. Ghi `newJobExecutionId` và liên kết nó với `JobInstanceId` cũ.
2. Theo dõi trạng thái và các `StepExecution` mới; step đã `COMPLETED` trước đó có thể được bỏ qua khi restart theo cấu hình, còn step lỗi có thể được chạy lại.
3. Kiểm tra số item được ghi, skip, rollback và kết quả DB theo business key.
4. Chạy/đọc **reconciliation** theo source manifest.
5. Xác minh publish gate và trạng thái downstream/outbox.
6. Chỉ đóng incident khi đạt tiêu chí dữ liệu cuối, không chỉ khi `JobExecution` mới `COMPLETED`.

### Những thao tác không nằm trong restart thông thường

- Không xóa bảng `BATCH_JOB_INSTANCE` hoặc `BATCH_JOB_EXECUTION` để “tạo lại cho sạch”.
- Không update trực tiếp `BATCH_JOB_EXECUTION.STATUS` thành `FAILED` chỉ vì thấy `STARTED` lâu.
- Không xóa `ExecutionContext` trước khi hiểu checkpoint và reader/writer restart.
- Không sửa input snapshot v1 tại chỗ rồi khẳng định restart vẫn xử lý cùng dữ liệu.
- Không phát lại toàn bộ file ra API ngoài khi chưa chứng minh idempotency.

Nếu metadata bị hỏng hoặc stale sau crash, **chỉ người được ủy quyền** mới thực hiện một thủ tục recovery đặc biệt sau khi xác minh process/DB side effects và có phương án backup/audit. Tài liệu chung không nên đưa ra một câu SQL `UPDATE BATCH_*` để copy-paste cho mọi tình huống.

## 11. Khi JobExecution vẫn STARTED nhưng pod đã chết

Đây là một tình huống khó trong vận hành. Spring Batch lưu metadata bền vững, nhưng nếu JVM bị kill đột ngột, execution có thể không được cập nhật trạng thái cuối. `JobRepository` vẫn xem instance đang chạy và từ chối launch trùng.

Runbook cần:

1. Tra pod/process thực tế, node, thời điểm stop và termination reason.
2. Kiểm tra có **worker, partition hoặc task ngoài JVM khác** còn tiếp tục ghi dữ liệu không.
3. Kiểm tra DB transaction còn mở, khóa tài nguyên, connection và hoạt động writer.
4. Xác minh cuối cùng đã commit những chunk nào; nếu có outbox/API, xác minh event/side effect ở bên ngoài.
5. Sao lưu/ghi nhận metadata cần thiết cho phân tích trước khi thực hiện thủ tục sửa trạng thái.
6. Escalate tới batch engineer/DB owner để áp dụng **quy trình phục hồi metadata được kiểm soát**, tương thích version Spring Batch và tình trạng execution thực tế.
7. Chỉ restart sau khi bảo đảm không còn execution cũ chạy đồng thời và writer có khả năng replay an toàn.

`JobOperator.stop(executionId)` là **yêu cầu dừng hợp tác** khi execution có khả năng tiếp tục xử lý stop signal; nó không tự phục hồi một JVM đã chết hoặc thay thế điều tra metadata stale. Cũng không được coi pod biến mất là bằng chứng chắc chắn API bên ngoài chưa nhận request cuối cùng.

## 12. Runbook cho failure ở từng giai đoạn

### 12.1. Preflight thất bại vì file không sẵn sàng

**Dấu hiệu:** `preflightSourceStep FAILED`, không tìm thấy file, manifest thiếu hoặc checksum khác giá trị chốt.

**Điều tra:** kiểm tra source ID, ngày, version, quy tắc nhận file, quyền đọc và trạng thái upload. Không đọc “file hiện tại” nếu cùng path đang bị ghi đè.

**Recovery:** yêu cầu upstream cung cấp file hoàn chỉnh, chốt checksum/version, sau đó restart hoặc launch theo hợp đồng JobInstance. Nếu file v1 đã thay đổi nội dung, cân nhắc **sourceVersion mới** và output revision tương ứng thay vì âm thầm thay dữ liệu dưới checkpoint cũ.

**Tiêu chí đóng:** manifest, checksum và input version khớp; load thành công; reconciliation kiểm tra output đúng kỳ.

### 12.2. Reader gặp dữ liệu parse sai

**Dấu hiệu:** `FlatFileParseException` hoặc lỗi parse được chuẩn hóa, `readSkipCount` tăng.

**Điều tra:** xác định lỗi một dòng độc lập hay toàn file đổi schema. Kiểm tra header/schema version trước khi cho skip số lượng lớn.

**Recovery:** với nguồn tham khảo có policy reject rõ, có thể skip trong ngưỡng, ghi quarantine theo line/source ref rồi reconcile. Với dữ liệu bắt buộc, fail và sửa nguồn hoặc tạo revision mới. Không bật `.skip(Exception.class)` để làm xanh job.

**Tiêu chí đóng:** số dòng nguồn được giải thích thành accepted/filter/reject; không vượt chính sách chất lượng; đầu ra đã commit khớp kỳ vọng.

### 12.3. Processor lỗi nghiệp vụ

**Dấu hiệu:** `processSkipCount` tăng hoặc step `FAILED` với validation error.

**Điều tra:** phân biệt record không hợp lệ theo hợp đồng với bug lập trình như `NullPointerException`, sai mapping hoặc quy tắc mới chưa triển khai. Xác minh record critical có bị skip không.

**Recovery:** sửa dữ liệu hoặc code, chọn restart/reprocess theo snapshot/version. Nếu cho reject, phải có mã lỗi và chủ sở hữu xử lý.

**Tiêu chí đóng:** không có record critical bị mất, bộ đếm process skip và dữ liệu đích nhất quán.

### 12.4. Writer database lỗi giữa chunk

**Dấu hiệu:** SQL transient/permanent error, rollback count tăng, `importPaymentsStep FAILED`.

**Điều tra:** xác minh transaction manager, DataSource, unique constraint, quyền `INSERT`, deadlock/lock timeout và chunk đã commit. Không đồng nhất “writer đã chạy” với “đã commit”.

**Recovery:** lỗi transient có thể retry có giới hạn/backoff; lỗi schema/grant phải sửa hạ tầng; dữ liệu constraint cần xác định có phải duplicate hợp lệ không. Restart bằng cùng instance sau khi đối chiếu. Nếu commit outcome không rõ, kiểm tra DB theo `(batchKey, eventId)`.

**Tiêu chí đóng:** không có hàng trùng, không thiếu business keys, số amount/count đúng, metadata kết thúc phù hợp.

### 12.5. Duplicate launch từ scheduler/API

**Dấu hiệu:** `JobExecutionAlreadyRunningException` hoặc `JobInstanceAlreadyCompleteException`, hai trigger cùng business key.

**Điều tra:** so `jobName` và identifying parameters, xem các trigger có sinh `run.id`/timestamp identifying mới không, đối chiếu repository dùng chung các node.

**Recovery:** nếu đã có execution hợp lệ, trả ID/trạng thái execution đó; không tạo instance thứ hai. Nếu instance đã `COMPLETED` nhưng cần xử lý lại do business revision, phải phê duyệt và tạo version có nghĩa.

**Tiêu chí đóng:** một đơn vị công việc không có hai execution của cùng instance chạy song song; kết quả đích duy nhất theo business key.

### 12.6. JobRepository không truy cập được

**Dấu hiệu:** lỗi tạo/đọc `JobExecution`, metadata không cập nhật, DB metadata mất kết nối hoặc credential hết hạn.

**Điều tra:** phân biệt network, TLS, DB outage, thiếu `GRANT`, secret rotation và pool exhaustion. Tra nguồn kích hoạt khi chưa có execution ID.

**Recovery:** phục hồi repository/secret/quyền, xác minh checkpoint và output đã commit, rồi mới quyết định restart. Không chuyển sang repository cục bộ tạm trên một pod hoặc reset bảng `BATCH_*`.

**Tiêu chí đóng:** repository ổn định, metadata tương ứng các execution, không duplicate processing do nhiều nguồn trigger.

### 12.7. HTTP writer timeout hoặc mất phản hồi

**Dấu hiệu:** gọi API đối tác timeout; không rõ request đã được xử lý chưa.

**Điều tra:** tra `eventId`/`idempotencyKey` ở phía đích, phân biệt HTTP 4xx permanent với 429/503 transient, đối chiếu những request đã có side effect.

**Recovery:** nếu endpoint hỗ trợ idempotency, retry có kiểm soát bằng **cùng key**; nếu chưa rõ outcome, tra trạng thái hoặc dùng quy trình bù trừ. Không bỏ qua item rồi gọi lại bằng ID mới.

**Tiêu chí đóng:** mỗi event tạo đúng một tác động nghiệp vụ cuối; có audit về request đã xử lý và các trường hợp chờ đối soát.

### 12.8. Outbox có backlog dù batch hoàn tất

**Dấu hiệu:** `dailyPaymentImportJob COMPLETED` nhưng outbox `PENDING`/`IN_FLIGHT` tăng, tuổi event vượt ngưỡng.

**Điều tra:** DB đã commit business row và outbox intent chưa, dispatcher/CDC đang hoạt động không, broker có ACK không, lease còn hiệu lực, event nào bị `DEAD`.

**Recovery:** sửa broker/dispatcher/schema, xử lý event poison theo policy, để dispatcher gửi lại bằng event ID cũ. Không xóa PENDING chỉ để giảm backlog.

**Tiêu chí đóng:** backlog trở lại ngưỡng cho phép, event được ACK và consumer xử lý theo hợp đồng; duplicate đã được consumer idempotent xử lý.

### 12.9. Reconciliation thất bại

**Dấu hiệu:** `reconcilePaymentsStep FAILED` dù import step `COMPLETED`; output count/sum/key khác manifest.

**Điều tra:** kiểm tra source snapshot, skip/filter, duplicate policy, writer UPSERT, dữ liệu đã commit, các execution trước của cùng instance và đích bên ngoài.

**Recovery:** giữ output ở staging, xác định missing/extra/mismatch key, sửa nguồn/code/hạ tầng hoặc dùng phiên bản reprocess theo phê duyệt. Không tự sửa số expected bằng cách copy count từ output.

**Tiêu chí đóng:** các phép đối chiếu theo hợp đồng đều PASS; chỉ publish khi dữ liệu đạt điều kiện.

## 13. Bước xác minh dữ liệu: không đóng incident bằng một trạng thái xanh

Runbook cần một **reconciliation checklist** áp dụng sau mọi recovery. Với job demo, định nghĩa bảng:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);
~~~

### 13.1. Đếm output thực tế theo kỳ

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT event_id) AS distinct_ids,
    COALESCE(SUM(amount), 0.00) AS output_amount
FROM processed_payment
WHERE batch_key = :batchKey
  AND currency = 'USD';
~~~

Với file demo:

~~~text
sourceDataLines   = 6
readSkipCount     = 1
filterCount       = 1
expectedOutput    = 4
actualOutput      = 4
expectedAmountUSD = 200.00
actualAmountUSD   = 200.00
~~~

Phép đếm này có giả định: mỗi dòng nguồn được phân loại đúng một lần, hai loại skip/filter là toàn bộ nguyên nhân loại trừ, writer 1:1 và job đã hoàn thành theo policy. Với job có dedup, one-to-many, many-to-one hoặc nhiều nguồn/đích, cần điều chỉnh grain và cách tính.

### 13.2. Tìm ID trùng

~~~sql
SELECT event_id, COUNT(*) AS occurrences
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY event_id
HAVING COUNT(*) > 1;
~~~

Với khóa chính ví dụ, query không thể trả về ID trùng trong cùng `batch_key`; nó vẫn hữu ích khi làm việc với bảng lịch sử/chưa có constraint hoặc để minh họa invariant. **Không coi ràng buộc unique là bằng chứng không thiếu ID.**

### 13.3. Tìm ID thiếu/thừa

Giả sử có bảng `accepted_payment` chứa tập ID và amount kỳ vọng **đã được xác định độc lập** từ snapshot nguồn sau validation:

~~~sql
-- Đã được chấp nhận nhưng không có output.
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;

-- Output không thuộc tập được chấp nhận.
SELECT p.event_id
FROM processed_payment p
LEFT JOIN accepted_payment a
  ON a.batch_key = p.batch_key
 AND a.event_id = p.event_id
WHERE p.batch_key = :batchKey
  AND a.event_id IS NULL;
~~~

Hai query phải trả **0 hàng** khi output là mapping 1:1 theo tập accepted. Nếu `accepted_payment` được tạo bằng cách copy từ `processed_payment` sau xử lý, phép kiểm tra không còn độc lập và có thể hợp thức hóa lỗi thiếu dữ liệu.

### 13.4. Kiểm tra sai amount theo ID

~~~sql
SELECT
    a.event_id,
    a.expected_amount,
    p.amount AS actual_amount
FROM accepted_payment a
JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND a.expected_amount <> p.amount;
~~~

Số count và tổng amount có thể bằng nhau ngay cả khi hai record sai theo hướng bù trừ. Vì vậy đối chiếu ID + amount theo từng record vẫn có giá trị. Với multi-currency, luôn đối chiếu theo currency và quy tắc rounding đã chốt.

### 13.5. Nếu có side effect ngoài transaction

Đối với API/broker/file:

- Xác minh idempotency/event IDs ở hệ thống nhận.
- Phân biệt outbox `SENT` với consumer **đã áp dụng nghiệp vụ**.
- Nếu file được công bố, kiểm tra manifest, checksum, số dòng và version.
- Nếu có retry sau timeout, xác định kết quả ở remote trước khi lặp lại thao tác.
- Nếu có nhiều `JobExecution` của cùng instance, kiểm tra đầu ra **cuối cùng theo business key**, không cộng mọi `writeCount` một cách máy móc.

## 14. Runbook cho skip, retry và rollback

Một `Step` có thể được cấu hình fault-tolerant:

~~~java
@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(org.springframework.dao.TransientDataAccessException.class)
        .retryLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .skipLimit(2)
        .build();
}
~~~

Đây là **cấu hình ví dụ**; các bean `PaymentInput`, `PaymentOutput` và reader/processor/writer phải được định nghĩa trong ứng dụng. Trước khi cho skip `FlatFileParseException`, preflight phải kiểm tra **format/schema của toàn file**, vì lỗi parse có thể biểu thị một thay đổi contract chứ không chỉ một record xấu. Với job bắt buộc xử lý đủ mọi payment, không nên cho skip lỗi parse.

### Quy tắc ghi trong runbook

| Tình huống | Có được tiếp tục? | Cách xác minh |
|---|---|---|
| Một record tùy chọn sai định dạng, policy cho reject | Có thể skip trong giới hạn. | Quarantine + count + source record reference. |
| `skipLimit` vượt ngưỡng | Không theo policy. | Step FAILED, đánh giá phạm vi reject. |
| DB deadlock transient | Có thể retry giới hạn, nếu writer replay-safe. | DB ổn, rollback và output cuối không trùng. |
| Sai SQL/schema/permission | Fail-fast, sửa hạ tầng. | Không chuyển thành write skip. |
| Writer JDBC lỗi giữa chunk | Rollback chunk nếu cùng transaction. | Query output, không chỉ dựa vào log write. |
| Writer HTTP timeout | Kết quả remote có thể đã xảy ra. | Tra idempotency key trước retry. |
| Process crash sau commit trước checkpoint | Có thể replay trên restart. | Unique business key, dữ liệu cuối và checkpoint. |

Không sử dụng `.skip(Exception.class)` với ngưỡng rất lớn chỉ để đạt trạng thái `COMPLETED`. Mọi reject phải được giải thích và **quality gate** phải có quyền chặn publish.

## 15. Mẫu hành động thay đổi production: cần kiểm soát rõ

Runbook nên phân loại mỗi thao tác:

| Mức hành động | Ví dụ | Chính sách |
|---|---|---|
| **Đọc, không thay đổi** | Xem dashboard, `JobExplorer`, `SELECT` metadata/output, đọc pod events. | Theo quyền read-only được cấp; bảo vệ dữ liệu nhạy cảm. |
| **Điều khiển job** | Yêu cầu stop, restart execution, tạm dừng scheduler. | Cần điều kiện thực thi rõ, owner/approval và ghi audit. |
| **Thay đổi cấu hình** | Sửa grant, rotate secret, đổi pool size, deploy code. | Theo quy trình change management của tổ chức. |
| **Thay đổi dữ liệu** | Quarantine, sửa file nguồn, backfill, compensation, reprocess. | Data owner phê duyệt; có snapshot/backup và reconciliation. |
| **Thay đổi metadata batch** | Phục hồi trạng thái stale/hỏng ở bảng `BATCH_*`. | Trường hợp ngoại lệ, chuyên gia có quyền và phương án riêng; không cung cấp SQL cập nhật chung. |

### Ví dụ phiếu phê duyệt recovery

~~~text
Incident: INC-2026-1116-001
Job / Batch: dailyPaymentImportJob
Business key: 2026-11-15:warehouse-A:v1
Existing JobInstance: 410
Failed JobExecution: 8102
Requested action: Restart same JobInstance after DB connectivity restored
Reason: Transient database failure; writer uses unique (batch_key,event_id)
Preconditions:
  - Previous execution confirmed no longer running
  - Database connectivity recovered
  - Source version/checksum unchanged
  - Prior committed output checked
  - No unresolved external side effect
Approved by: <designated owner>
Operator: <authorized operator>
Expected evidence:
  - New JobExecution ID
  - Reconciliation PASS
  - Published version matches source manifest
~~~

Các placeholder owner/operator chỉ được điền bằng danh tính thật trong quy trình vận hành nội bộ; ví dụ này không phải một phê duyệt đã được cấp.

## 16. Mẫu giao tiếp trong lúc có sự cố

Để tránh thông tin rời rạc, nên có một định dạng cập nhật ngắn:

> **Sự cố:** `dailyPaymentImportJob` cho `2026-11-15:warehouse-A:v1` dừng ở `importPaymentsStep`, `JobExecution=8102`.
>
> **Tình trạng:** `FAILED`; có ít nhất một chunk đã commit, publish chưa được xác nhận.
>
> **Tác động:** Dữ liệu kỳ này chưa được công bố; dashboard downstream có thể chậm. Chưa có bằng chứng về mất dữ liệu vĩnh viễn.
>
> **Bằng chứng:** Metadata job/step, error category `DATABASE_TRANSIENT` và truy vấn output theo batch key; không đính kèm payload nhạy cảm.
>
> **Hành động:** Đang xác minh DB phục hồi và output idempotency trước khi xin restart cùng JobInstance.
>
> **Điều kiện đóng:** Reconciliation PASS, source version đúng, output không trùng, publish thành công.

Thông báo nên dùng **timestamp cụ thể kèm timezone**, không viết “vừa rồi” hoặc “hôm qua” khi nhiều ca trực ở múi giờ khác nhau. Không tuyên bố “không mất dữ liệu” nếu chưa có bằng chứng ở nguồn/đích.

## 17. Mẫu nhật ký sự cố và quyết định

Một **incident timeline** giúp phân biệt cái đã quan sát với điều chỉ là giả thuyết:

| Thời điểm minh họa | Loại | Ghi nhận |
|---|---|---|
| 01:00:00 +07:00 | Observation | Scheduler kích hoạt batch key `2026-11-15:warehouse-A:v1`. |
| 01:00:01 +07:00 | Observation | `JobExecution 8102` tạo thành công. |
| 01:02:10 +07:00 | Observation | `importPaymentsStep` gặp DB timeout; `rollbackCount` tăng. |
| 01:02:12 +07:00 | Observation | `JobExecution 8102 FAILED`. |
| 01:05:00 +07:00 | Investigation | DB connectivity được kiểm tra; không ghi giá trị credential vào ticket. |
| 01:07:00 +07:00 | Investigation | Đối chiếu các `event_id` đã commit theo batch key. |
| 01:10:00 +07:00 | Decision | Data owner/batch engineer cho phép restart cùng JobInstance. |
| 01:11:00 +07:00 | Action | `JobExecution 8103` bắt đầu. |
| 01:15:00 +07:00 | Observation | Import hoàn thành; reconciliation PASS. |
| 01:16:00 +07:00 | Observation | Publish hoàn thành; downstream xác nhận version mới. |

Đây là timeline **giả lập cho bài thực hành**, không phải lịch sử thực của hệ thống. Khi tạo runbook thật, cần lưu người thực hiện, ID ticket/change và liên kết bằng chứng theo chính sách tổ chức.

## 18. Dự án thực hành: triển khai các tình huống failure có kiểm soát

Để runbook không chỉ nằm trên giấy, hãy diễn tập trên **môi trường test cô lập** với dữ liệu giả và một PostgreSQL dùng cho integration test. Không dùng dữ liệu khách hàng thật, credential production hoặc câu lệnh sửa metadata không được phê duyệt.

### 18.1. Chuẩn bị môi trường

Yêu cầu tối thiểu:

1. Ứng dụng Spring Boot có job mẫu gồm preflight, import, reconciliation và publish step.
2. `JobRepository` JDBC hoạt động với schema metadata thích hợp.
3. Bảng `processed_payment` có unique key theo `(batch_key,event_id)`.
4. File CSV sáu dòng của mục 2 với manifest đã chốt.
5. Logging có `jobExecutionId`, `stepExecutionId` và `errorCode`; không in toàn bộ item.
6. Một cách chạy job với identifying parameters cố định, ví dụ:

~~~java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceId", "warehouse-A", true)
    .addString("sourceVersion", "v1", true)
    .addString("correlationId", "exercise-001", false)
    .toJobParameters();
~~~

`correlationId` non-identifying phục vụ theo dõi lần kích hoạt; không tạo JobInstance khác khi request ID thay đổi. Nếu muốn **chạy lại bài tập từ đầu trên một instance mới**, cần làm việc với môi trường test được reset có kiểm soát hoặc chủ động chọn **sourceVersion mới** theo kịch bản, chứ không dùng timestamp ngẫu nhiên để lấp sự thiếu nhất quán.

### 18.2. Kịch bản A — nguồn không có file

**Setup:** Cho manifest trỏ đến file test chưa tồn tại.

**Mong đợi:** `preflightSourceStep FAILED`, writer không được chạy, bảng output không có dữ liệu cho batch key đó.

**Thực hành runbook:** xác minh file, manifest, quyền và source version; mô tả ai phải cung cấp lại nguồn; thực hiện recovery trong test sau khi file đúng đã có.

**Bằng chứng bàn giao:** trạng thái preflight, log error code `SOURCE_NOT_READY`, kết quả query output và execution mới nếu có restart.

### 18.3. Kịch bản B — một dòng CSV sai định dạng

**Setup:** Dòng `PAY-003` có amount `abc`.

**Mong đợi:** Theo policy demo, một `readSkipCount`, bốn output records và tổng `200.00 USD`. Nếu runbook chọn policy strict cho payment, mong job fail/block publish.

**Thực hành:** phân biệt lỗi một dòng với schema toàn file sai, kiểm tra quarantine và quality gate, không chỉ nhìn `BatchStatus`.

**Bằng chứng:** read skip count, reject error code, source data line count, output set và sum.

### 18.4. Kịch bản C — writer JDBC lỗi giữa chunk

**Setup:** Dùng writer test cố ý ném exception sau khi đã thực hiện một hoặc vài lệnh `INSERT` của chunk chưa commit:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

final class FailingPaymentWriter implements ItemWriter<PaymentOutput> {

    private final JdbcTemplate jdbc;

    FailingPaymentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends PaymentOutput> chunk) {
        for (PaymentOutput row : chunk) {
            jdbc.update("""
                INSERT INTO processed_payment(
                    batch_key, event_id, currency, amount)
                VALUES (?, ?, ?, ?)
                """,
                row.batchKey(),
                row.eventId(),
                row.currency(),
                row.amount()
            );

            if ("PAY-005".equals(row.eventId())) {
                throw new IllegalStateException(
                    "DELIBERATE_WRITER_FAILURE"
                );
            }
        }
    }
}
~~~

Đây là **writer dành riêng cho fault injection trong test**, không phải code production. `PaymentOutput` là model ví dụ có property `batchKey`, `eventId`, `currency` và `amount`.

**Mong đợi:** Nếu `JdbcTemplate` dùng cùng datasource/transaction manager của chunk, các thay đổi chưa commit của chunk bị rollback khi exception không được retry/skip. Những chunk trước đã commit vẫn có thể còn.

**Thực hành:** đối chiếu database thực, không chỉ đếm số lời gọi writer. Thực hiện restart an toàn sau khi bỏ fault injection và xác nhận không trùng business keys.

### 18.5. Kịch bản D — chunk trước commit, chunk sau thất bại

**Setup:** Với dữ liệu hợp lệ, chọn `chunkSize=2`; cho lỗi có kiểm soát xảy ra ở chunk sau khi chunk đầu đã commit.

**Mong đợi:** Các row của chunk đầu tồn tại sau `FAILED`; chunk lỗi rollback nếu cùng transaction. Lần restart cùng JobInstance xử lý phần còn lại theo checkpoint.

**Thực hành:** ghi rõ “đã commit” và “chưa commit” trong incident, kiểm tra `JobExecution` mới liên kết instance cũ. Writer phải có unique key và an toàn khi replay.

**Bằng chứng:** query output trước và sau restart, metadata hai executions, reconciliation cuối.

### 18.6. Kịch bản E — lỗi kết nối DB tạm thời

**Setup:** Trong test, dùng fake writer hoặc cấu hình fault injection ném một exception transient được policy retry cho phép ở một lần thử, sau đó thành công.

**Mong đợi:** Retry diễn ra trong giới hạn; job đạt `COMPLETED` khi lỗi qua đi; output cuối đúng một lần theo business key.

**Thực hành:** phân biệt transient với sai credential/schema vĩnh viễn. Không cho job thử lại `Exception.class` vô hạn.

**Bằng chứng:** retry/rollback metrics, trạng thái execution, output không trùng và tổng amount đúng.

### 18.7. Kịch bản F — hai nguồn cùng launch một business key

**Setup:** Hai thread hoặc hai application instance cùng gọi `JobLauncher.run(...)` cho `businessDate`, `sourceId`, `sourceVersion` giống nhau; dùng một step có latch để giữ execution đầu ở trạng thái đang chạy.

**Mong đợi:** Không có hai `JobExecution` của cùng JobInstance **chạy đồng thời** khi repository chia sẻ được cấu hình đúng. Lời gọi cạnh tranh được từ chối/giải quyết theo repository; có thể gặp `JobExecutionAlreadyRunningException` khi execution đầu thực sự đang chạy.

**Thực hành:** báo cho caller biết execution hiện hữu; không thêm identifying timestamp mới để “né” lỗi. Ghi hai correlation IDs của launch attempt vào audit nếu cần.

**Bằng chứng:** metadata JobInstance/Execution, launch outcomes, số output duy nhất.

### 18.8. Kịch bản G — crash sau commit nhưng trước phản hồi

**Setup:** Mô phỏng mất kết nối/response sau khi thao tác ghi có thể đã commit. Với HTTP writer, dùng fake server nhận request rồi làm client timeout; với DB, sử dụng fault injection và query trạng thái thực.

**Mong đợi:** Runbook không tuyên bố “chắc chắn rollback” chỉ từ timeout. Kết quả được xác minh ở hệ thống đích theo `eventId` hoặc idempotency key.

**Thực hành:** quyết định retry, restart hoặc bù trừ dựa trên trạng thái remote; tránh tạo tác động trùng.

**Bằng chứng:** request ID, trạng thái server giả lập, số side effect cuối và kết quả reconciliation.

### 18.9. Kịch bản H — quality gate FAIL dù load COMPLETED

**Setup:** Làm output thiếu một ID hoặc đổi amount của một ID sau load trong database test để mô phỏng một sai lệch.

**Mong đợi:** Reconciliation phát hiện mismatch, `publishPaymentsStep` không được chạy theo flow thành công.

**Thực hành:** dùng anti-join và sum theo business key, lập phiếu điều tra data quality thay vì chạy lại ngay.

**Bằng chứng:** expected/actual rows, missing/extra IDs, amount mismatch và trạng thái publish.

## 19. Ma trận diễn tập và tiêu chí nghiệm thu runbook

| Mã | Sự cố | Dấu hiệu cần nhận ra | Recovery mong đợi | Bằng chứng cần lưu |
|---|---|---|---|---|
| A | Missing source | Preflight FAILED | Khôi phục file/version, restart có kiểm soát | Manifest/checksum, không có output trước xử lý |
| B | CSV bad record | Read skip hoặc fail theo policy | Reject/quarantine hoặc sửa nguồn | Skip counts, source count, quality result |
| C | Writer rollback | Step FAILED, rollback count | Sửa nguyên nhân, restart, replay-safe | Output trước/sau, không trùng |
| D | Partial chunks committed | Execution FAILED | Tiếp tục theo checkpoint | Chunk trước tồn tại, output cuối đầy đủ |
| E | Transient DB outage | Retry/rollback | Backoff/retry giới hạn | Không duplicate, job hoàn thành |
| F | Duplicate launch | Already running/complete | Dùng execution hiện hữu | Một JobInstance theo business key |
| G | Unknown remote outcome | Timeout | Tra idempotency/remote trước retry | Một side effect cuối |
| H | Reconciliation mismatch | Load xong nhưng reconcile FAIL | Chặn publish, điều tra missing/mismatch | Anti-join, sum và publish gate |

**Runbook đạt yêu cầu** khi một người không viết job vẫn có thể đọc được phần cố định, thu thập đúng metadata, phân loại nguyên nhân, xác định có được phép thay đổi production hay không, đưa ra quyết định recovery có lý do và xác minh đầu ra bằng dữ liệu. “Tất cả step test đều xanh” không đủ nếu tài liệu thiếu người phê duyệt, thiếu trường hợp outcome không rõ hoặc hướng dẫn xóa metadata quá dễ dàng.

## 20. Kịch bản mẫu: một incident được xử lý từ đầu đến cuối

### Tình trạng ban đầu

Scheduler phát lệnh xử lý `2026-11-15:warehouse-A:v1`. `dailyPaymentImportJob` tạo `JobInstance 410`, `JobExecution 8102`. Preflight thành công; import được một số chunk thì database trả lỗi kết nối và step thất bại.

### Phân tích theo runbook

1. Operator nhận alert `JobExecution=8102 FAILED`, thu thập `batchKey` và correlation ID.
2. Từ `BATCH_STEP_EXECUTION`, xác định `importPaymentsStep` bị lỗi, có `COMMIT_COUNT > 0` và `ROLLBACK_COUNT > 0`.
3. Kiểm tra hạ tầng cho thấy database kết nối lại bình thường. Chỉ kết luận nguồn đã hồi phục sau khi có bằng chứng kiểm tra kết nối/transaction phù hợp.
4. Truy vấn `processed_payment` theo `batchKey` để biết các hàng đã commit. Một phần output đã tồn tại, nên **không xóa dữ liệu và chạy lại từ đầu**.
5. Xác minh source manifest/version/checksum không thay đổi; writer có primary key `(batch_key,event_id)` và chính sách replay an toàn.
6. Batch engineer/data owner xác nhận không có side effect HTTP không rõ; phê duyệt restart của execution `8102`.
7. Một `JobExecution` mới, ví dụ `8103`, được tạo cho **cùng JobInstance 410**.
8. Sau khi job chạy xong, reconciliation xác minh tập accepted IDs, output count 4 và total 200.00 USD theo fixture.
9. Chỉ sau khi quality gate đạt, publish step cho phép công bố batch version.
10. Operator đóng incident kèm ID execution mới, báo cáo đối chiếu, timeline và nguyên nhân gốc.

### Bài học từ tình huống

Nếu chỉ thấy `FAILED` rồi xóa `BATCH_*` để tạo lại job, hệ thống có nguy cơ đọc lại và phát tác động trùng. Nếu chỉ thấy `COMPLETED` sau restart mà không query dữ liệu, vẫn có nguy cơ thiếu hoặc thừa record. Runbook đúng buộc người vận hành kiểm tra **vòng đời execution và trạng thái dữ liệu cuối**.

## 21. Bảo mật trong runbook

Trong lúc khắc phục sự cố, người vận hành thường bật log chi tiết và xuất dữ liệu để điều tra. Đây là thời điểm dễ làm lộ thông tin nhất nếu runbook không quy định rõ:

- Không ghi password, API key, bearer token, private key hoặc full JDBC URL có secret vào ticket.
- Không log/dump toàn bộ `JobParameters`, `ExecutionContext`, `Chunk`, item object hoặc dòng CSV có PII.
- Dùng `jobExecutionId`, `stepExecutionId`, `correlationId` đã kiểm tra, error code và source record reference an toàn.
- Nếu cần xem bản ghi reject, truy cập **kho nguồn/quarantine có phân quyền**, không copy raw payload vào chat công khai.
- Khi trao đổi log, chỉ đính kèm đoạn đã được giảm thiểu dữ liệu hoặc liên kết tới hệ thống log với quyền phù hợp.
- Các truy vấn `SELECT` vẫn phải tuân theo quyền data access; “chỉ đọc” không đồng nghĩa được phép xem mọi bảng.
- Nếu nghi credential rò rỉ, chuyển sang quy trình ứng phó bảo mật và rotate/revoke theo chính sách; không coi đây là lỗi retry thông thường.

Runbook phải ghi rõ **dữ liệu nào có thể xuất trong incident record** và **ai được phép thực hiện thao tác điều tra nâng cao**.

## 22. Bảo trì và cập nhật runbook sau sự cố

Runbook không nên được viết một lần rồi bỏ quên. Khi schema, `JobParameters`, transaction boundary, output destination hoặc cảnh báo thay đổi, quy trình cũ có thể dẫn tới recovery sai.

Các thời điểm cần rà soát:

- Job chuyển từ JDBC writer sang API/broker hoặc thêm outbox.
- Đổi chunk size, reader checkpoint, cấu hình retry/skip hoặc restartability.
- Đổi schema input, nguồn file, source version hoặc reconciliation rules.
- Thêm partitioning/đa node hoặc thay scheduler.
- Tách `JobRepository` và business database sang các datasource khác.
- Thay cơ chế credential, secret rotation hoặc quyền DB.
- Phát hiện incident mới chưa có trong bảng quyết định.
- Một cuộc diễn tập cho thấy câu lệnh, dashboard, người liên hệ hoặc điều kiện phê duyệt không còn đúng.

Một bản cập nhật cần có version, ngày review, người review và thay đổi hành vi. Nếu runbook lưu trong Git, có thể review như code: mô tả lý do, phạm vi, sự thay đổi rủi ro và bằng chứng diễn tập.

### Mẫu post-incident review

~~~text
Incident ID:
Job / batchKey:
Detection source:
Customer/business impact:
Actual root cause:
First observed failure point:
Committed output at failure:
External side effects:
Recovery action and approver:
New JobExecution ID / jobInstance ID:
Final reconciliation result:
Evidence links:
What worked in the runbook:
What was missing or confusing:
Preventive change:
Owner and follow-up date:
~~~

Không dùng post-incident review chỉ để đếm số lần retry hoặc quy trách nhiệm cá nhân. Mục tiêu là xác nhận nguyên nhân, giảm khả năng tái diễn và làm cho lần recovery tiếp theo **an toàn hơn, nhanh hơn về thao tác và dễ kiểm chứng hơn**.

## 23. Mẫu runbook rút gọn có thể sao chép cho job khác

~~~markdown
# Runbook: <jobName> — Failure and Recovery

## 1. Thông tin cố định
- Owner / on-call:
- Môi trường / dashboard:
- Nguồn kích hoạt:
- Business key và identifying JobParameters:
- JobRepository / business datastore aliases:
- Source manifest/snapshot:
- Output destinations:
- SLA và quality gate:

## 2. Đầu vào một incident
- Incident ID / detection time:
- JobInstanceId / JobExecutionId:
- StepExecutionId / failing step:
- Business key / source version:
- Correlation/trigger ID:
- Alert / error category:
- Business impact:

## 3. Điều tra chỉ đọc
1. Tra execution và step counters.
2. Đối chiếu process/pod với metadata.
3. Kiểm tra nguồn, checksum và version.
4. Kiểm tra DB output đã commit.
5. Kiểm tra side effect ngoài DB.

## 4. Phân loại
- Reader/processor/writer/repository/publish/reconciliation?
- Transient hay permanent?
- Có execution khác còn chạy không?
- Commit outcome có rõ không?
- Có thể restart an toàn không?

## 5. Recovery được phê duyệt
- Action:
- Preconditions:
- Approver / operator:
- Execution mới (nếu có):
- Dữ liệu/side effect cần xác minh:

## 6. Reconciliation
- Source snapshot và expected:
- Actual output count/sum/keys:
- Rejected/filter/skip:
- Duplicate/missing/mismatched keys:
- Remote/outbox results:
- Publish result:

## 7. Đóng incident
- Final BatchStatus / ExitStatus:
- Final quality result:
- Evidence links:
- Owner confirmation:
- Follow-up/prevention:
~~~

Đây là **template** cần điền đúng hệ thống, không phải lệnh tự động có quyền thao tác trên production. Khi hoàn thiện, nên để các liên kết dashboard và query mẫu sát tình huống nhất có thể, đồng thời loại bỏ mọi thao tác không được đội vận hành ủy quyền.

## 24. Những sai lầm khi viết runbook

**“Nếu job lỗi, chạy lại cùng command.”** Không biết command có thêm timestamp identifying không, job cũ còn chạy không hoặc đích đã có dữ liệu gì. Cần xác minh trước và giữ đúng semantics restart.

**“Thấy trạng thái `STARTED` lâu thì sửa thành `FAILED` bằng SQL.”** Metadata có thể stale nhưng process vẫn chạy hoặc side effect ngoài DB chưa kết thúc. Can thiệp metadata là thao tác đặc biệt, không phải phản xạ mặc định.

**“Job `COMPLETED` thì đóng incident.”** Có thể có skip, filter, UPSERT bỏ record hoặc outbox chưa dispatch. Phải kiểm tra quality gate và dữ liệu cuối.

**“Writer lỗi nghĩa là mọi dữ liệu được rollback.”** Chunk đã commit trước vẫn có thể tồn tại. API/file/broker ngoài transaction cũng có thể còn tác động.

**“Timeout API nghĩa là request chưa tới nơi.”** Phía đích có thể đã commit; cần idempotency key hoặc truy vấn trạng thái remote.

**“Có `writeCount` là không cần query output.”** Counter phản ánh xử lý Spring Batch, không luôn bằng số business rows đã commit trong mọi writer.

**“Thêm `run.id` mới là restart.”** Đổi identifying parameters tạo JobInstance mới. Restart đúng là JobExecution khác của cùng JobInstance khi trạng thái cho phép.

**“Runbook càng nhiều lệnh sửa DB càng tốt.”** Không. Runbook phải ưu tiên **quan sát, bảo toàn bằng chứng và các thao tác được hỗ trợ**, tránh một lệnh copy-paste có thể phá checkpoint.

**“Chỉ cần lưu exception message.”** Message có thể chứa PII/secret và không mô tả đủ tác động dữ liệu. Dùng error category, execution IDs, source reference và báo cáo reconciliation.

**“Một ngưỡng skip chung áp dụng mọi job.”** Ngân sách reject là quyết định nghiệp vụ; một bản ghi kế toán bắt buộc không thể được đánh đồng với một dòng dữ liệu tham khảo tùy chọn.

**“Không cần diễn tập runbook nếu đã viết đầy đủ.”** Một đường dẫn dashboard lỗi, cú pháp truy vấn không dùng được hoặc checkpoint không có như mô tả chỉ được phát hiện khi thực hành trong môi trường an toàn.

## 25. Nguyên tắc cuối cùng khi bàn giao

Một runbook tốt cho Spring Batch phải cho phép người vận hành trả lời theo trình tự:

1. **Job nào, instance nào, execution nào và kỳ dữ liệu nào?**
2. **Failure xảy ra ở bước nào và trước/sau ranh giới commit nào?**
3. **Có tiến trình khác hoặc tác động ngoài transaction còn hoạt động không?**
4. **Nguyên nhân transient, dữ liệu sai, logic sai hay hạ tầng sai?**
5. **Những gì đã commit và những gì còn thiếu/chưa rõ?**
6. **Ai có quyền quyết định stop/restart/reprocess hoặc sửa dữ liệu?**
7. **Hành động nào giữ đúng business key, checkpoint và idempotency?**
8. **Sau phục hồi, output có đúng theo snapshot nguồn và quality contract không?**
9. **Downstream đã nhận dữ liệu đúng và incident có thể đóng chưa?**

Nếu không trả lời được một câu hỏi, runbook phải nói rõ **dừng hành động, thu thập thêm bằng chứng hoặc escalation tới đúng owner**, thay vì cung cấp một thao tác mặc định nguy hiểm.

## Kết luận

**Tạo runbook cho failure và recovery** trong Spring Batch là biến kiến thức về `JobRepository`, chunk transaction, retry/skip, restart, idempotency và reconciliation thành **một quy trình vận hành có thể thực hiện và kiểm chứng**. Runbook không nên dừng ở lệnh “restart job”; nó phải xác định công việc nghiệp vụ, ranh giới commit, dữ liệu đã được ghi, các side effect ngoài database, quyền phê duyệt và điều kiện công bố kết quả.

Qua dự án `dailyPaymentImportJob`, người học có thể diễn tập các tình huống từ thiếu file, parse lỗi, rollback writer, DB transient, duplicate launch đến output mismatch và API timeout. Khi từng tình huống có **bằng chứng điều tra, hành động phục hồi có điều kiện và kiểm chứng đầu ra cuối**, runbook trở thành công cụ giảm rủi ro vận hành thực sự — đặc biệt trong những thời điểm cần phục hồi nhanh nhưng vẫn phải bảo đảm không mất hoặc nhân đôi dữ liệu nghiệp vụ.
