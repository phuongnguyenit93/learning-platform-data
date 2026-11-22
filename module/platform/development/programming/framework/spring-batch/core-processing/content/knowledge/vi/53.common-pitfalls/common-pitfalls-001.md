# Dùng thời gian hiện tại để luôn tạo JobInstance mới — lỗi thường gặp trong Spring Batch

## 1. Vấn đề: “thêm timestamp để job chạy lại” có thể phá hỏng restart

Một đoạn mã rất thường thấy khi mới làm quen với Spring Batch:

```java
JobParameters parameters = new JobParametersBuilder()
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

Người viết muốn tránh lỗi “job đã hoàn thành” hoặc “job instance đã tồn tại” khi chạy cùng job nhiều lần. Mỗi lần gọi lấy thời gian hiện tại và gắn vào parameters để Spring Batch xem đó là một lần chạy khác.

Cách làm này có thể đáp ứng **yêu cầu tạo một đợt chạy độc lập** trong demo, nhưng là **lỗi thiết kế nghiêm trọng** nếu nó được dùng theo thói quen cho tất cả batch jobs. Spring Batch không còn nhận ra hai lần chạy đang xử lý **cùng một công việc nghiệp vụ**. Một execution thất bại có thể bị bỏ dở; lần chạy tiếp theo bắt đầu như job mới, không đọc checkpoint cũ, có khả năng nạp trùng hoặc phát side effect lặp.

Ví dụ job nhập hóa đơn ngày 16/11/2026:

```text
Lần 1:
  jobName    = invoiceImportJob
  businessDate = 2026-11-16
  runAt      = 1794800000000  [identifying]
  JobInstance #100
  JobExecution #200 -> FAILED sau 60.000/100.000 bản ghi

Lần 2:
  jobName    = invoiceImportJob
  businessDate = 2026-11-16
  runAt      = 1794800100000  [identifying, giá trị khác]
  JobInstance #101
  JobExecution #201 -> chạy lại từ đầu

Mong muốn:
  Restart JobInstance #100 bằng JobExecution mới
  và khôi phục checkpoint của step chưa hoàn tất.
```

Timestamp ở trên chỉ là giá trị minh họa. Điều cốt lõi không nằm ở con số, mà ở việc mỗi lần gọi dùng **identifying parameter khác**.

> **Quy tắc cần nhớ:** Một lần chạy lại sau lỗi thường phải tạo **`JobExecution` mới của cùng `JobInstance`**, không phải tạo một `JobInstance` mới bằng cách thay timestamp. Thời gian hiện tại chỉ nên trở thành một phần định danh khi nghiệp vụ thực sự xác định mỗi lần bấm chạy là một đơn vị công việc độc lập.

Bài này thuộc chương **Lỗi thường gặp** của module **Spring Batch Core Processing**. Ví dụ dựa trên Java 17+, Spring Boot 3.x và Spring Batch 5.x. Khi dùng Spring Batch 6.x, đối chiếu thay đổi API, nhưng nguyên tắc identity và restart vẫn cần được giữ.

### Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích cách Spring Batch xác định một `JobInstance` từ `jobName` và identifying `JobParameters`.
- Nhận ra vì sao `System.currentTimeMillis()`, `Instant.now()` hoặc UUID nhận diện làm “né restart”.
- Phân biệt chạy đợt mới, restart sau lỗi, reprocess có chủ ý, rerun và backfill.
- Thiết kế identifying parameters theo **business key/nominal schedule slot** thay vì thời điểm request tới server.
- Dùng `JobLauncher`, `JobOperator`, `JobExplorer` và metadata để quyết định an toàn.
- Kiểm thử tính ổn định identity, restart checkpoint, concurrency, idempotency và kết quả nghiệp vụ.
- Lập phương án sửa một job hiện tại đã sử dụng timestamp sai mà không đánh mất lịch sử xử lý.

---

## 2. Ba khái niệm nền tảng: `Job`, `JobInstance` và `JobExecution`

### 2.1. `Job` là định nghĩa công việc

Một `Job` mô tả luồng xử lý: các step, thứ tự chuyển trạng thái và cấu hình restart. Ví dụ:

```text
invoiceImportJob
   |
   +-- validateInputStep
   |
   +-- importInvoiceStep
   |
   +-- reconcileTotalsStep
```

`Job` không đồng nghĩa một lần chạy cụ thể.

### 2.2. `JobInstance` là một công việc logic

Spring Batch dùng **tên job** cộng với tập **identifying job parameters** để định danh `JobInstance`.

Ví dụ:

```text
jobName = invoiceImportJob

Identifying parameters:
  tenantId     = merchant-42
  businessDate = 2026-11-16

=> một JobInstance cho ngày nghiệp vụ đó của tenant đó
```

Hai lần launch với cùng job name và cùng identifying values thường đề cập tới **cùng `JobInstance`**. Framework phải xem trạng thái của instance để quyết định có tạo execution mới hay từ chối yêu cầu.

Một `JobInstance` không chỉ là timestamp hoặc số lần bạn nhấn nút Run. Nó là một **đơn vị công việc nghiệp vụ cần hoàn thành**.

### 2.3. `JobExecution` là một lần thực thi của instance

Một instance có thể có nhiều executions khi công việc gặp lỗi rồi được restart:

```text
JobInstance #100
  invoiceImportJob(tenantId=merchant-42, businessDate=2026-11-16)
       |
       +-- JobExecution #200: FAILED
       |       validateInputStep: COMPLETED
       |       importInvoiceStep:  FAILED
       |
       +-- JobExecution #202: COMPLETED (restart)
               validateInputStep: thường được bỏ qua
               importInvoiceStep:  tiếp tục theo checkpoint
               reconcileTotalsStep: COMPLETED
```

Một job được thiết kế restart đúng có thể tiếp tục công việc từ metadata đã lưu. Nếu đổi identifying parameter, Spring Batch xem đó là instance khác và không tự áp dụng checkpoint thuộc instance #100.

### 2.4. Mối quan hệ thể hiện bằng công thức

Viết ngắn gọn:

\[
\operatorname{JobInstanceIdentity}
=
(\operatorname{jobName},
\operatorname{identifyingJobParameters})
\]

Cần chú ý **cả tên, giá trị, kiểu dữ liệu và cờ identifying** của parameters. Không chỉ so sánh một map chuỗi “trông giống nhau”.

Ví dụ `businessDate` dưới kiểu `String` và kiểu `LocalDate` trong các cách biểu diễn/phiên bản phù hợp không nên bị giả định tạo cùng identity. Thực tế nên chọn một biểu diễn ổn định và một convention nhất quán cho toàn hệ thống.

---

## 3. `JobParameters` có hai nhóm: identifying và non-identifying

### 3.1. Mặc định là identifying

Trong Spring Batch 5.x, những overload phổ biến của `JobParametersBuilder.addString`, `addLong`, `addDate` khi không truyền cờ identifying thường sử dụng **identifying=true**.

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("tenantId", "merchant-42")
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();
```

Ở đây **cả ba** tham số được xem là nhận diện theo hành vi mặc định của các overload này. `runAt` đổi thì logical identity đổi, dù `businessDate` và `tenantId` giữ nguyên.

### 3.2. Non-identifying là metadata phụ

Có thể đánh dấu một tham số không tham gia identity:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantId", "merchant-42", true)
    .addLong("requestedAtEpochMs",
        System.currentTimeMillis(), false)
    .toJobParameters();
```

Khi đó `requestedAtEpochMs` chỉ là thông tin bổ sung, không thay đổi `JobInstance`.

Nhưng cần hiểu hai hạn chế quan trọng:

1. **Non-identifying timestamp không làm một instance đã `COMPLETED` trở thành có thể chạy lại.** Nếu cùng instance đã hoàn thành, Spring Batch có thể ném `JobInstanceAlreadyCompleteException`.
2. **Non-identifying timestamp không thay thế audit request/execution.** Nếu muốn ghi lịch sử người dùng đã bấm nút lúc nào, request ID nào, ai phê duyệt, tốt hơn có audit log/event riêng vì nhiều request có thể trỏ đến cùng instance và có request bị từ chối trước khi tạo execution.

### 3.3. Tham số nào nên identifying?

Một nguyên tắc đơn giản: **Nếu hai request có tham số này khác nhau, chúng có phải hoàn thành hai công việc nghiệp vụ độc lập không?**

| Tham số | Thường identifying? | Giải thích |
| --- | --- | --- |
| `businessDate` | Có | Hai kỳ xử lý khác nhau |
| `tenantId` | Có, nếu công việc chạy riêng tenant | Tránh trộn dữ liệu giữa tenant |
| `sourceFileId` | Có, nếu mỗi file là một import độc lập | Một file cụ thể chỉ nên có một logical ingestion |
| `feedVersion` | Có, nếu version là đơn vị công việc khác nhau | Phụ thuộc contract |
| `scheduledSlot` | Có, khi mỗi nominal slot là một đơn vị công việc | Backfill và duplicate dispatch cùng slot |
| `requestedAt` | Thường không | Thời điểm gửi request không nhất thiết là identity |
| `traceId` / `correlationId` | Thường không | Dùng để theo dõi |
| `operatorName` | Không | Người gửi restart không tạo nghiệp vụ mới |
| `retryAttempt` | Không | Retry phải liên quan cùng instance |
| `run.id` | Chỉ khi thực sự chủ động tạo instance mới | Không dùng để che lỗi restart |
| `runUuid` | Chỉ khi mỗi request thực sự là công việc mới | Không phù hợp cho xử lý lại cùng input |

Tính identifying là **quyết định domain**, không phải chỉ là kỹ thuật né exception.

---

## 4. Vì sao timestamp biến restart thành một job mới?

### 4.1. Hành vi của đoạn mã sai

```java
public void runImport() throws Exception {
    JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addLong("timestamp", System.currentTimeMillis(), true)
        .toJobParameters();

    jobLauncher.run(importJob, params);
}
```

Giả sử execution đầu thất bại sau hai chunk đã commit và lưu checkpoint tương ứng. Trong lần gọi kế tiếp, `timestamp` khác:

```text
Đợt 1:
  timestamp=T1 -> JobInstance A -> FAILED
  metadata lưu ExecutionContext của A

Đợt 2:
  timestamp=T2 -> JobInstance B -> STARTED
  B chưa có lịch sử step/checkpoint của A
  reader có thể bắt đầu từ item đầu tiên
```

Spring Batch không có cơ chế tự đoán rằng A và B phải là một vì cùng business date. Đối với framework, hai bộ identifying parameters khác nhau nghĩa là hai logical jobs khác nhau.

### 4.2. Tác hại lên checkpoint

Ví dụ step nhập 100.000 giao dịch với chunk size 1.000:

```text
JobInstance A:
  chunk 1..60 COMMITTED       60.000 giao dịch
  chunk 61 FAILED
  last persisted checkpoint 60.000

Lần chạy mới dùng timestamp T2:
  JobInstance B:
  reader.open(new context)
  bắt đầu từ bản ghi 1
```

Hậu quả phụ thuộc writer:

- Writer `INSERT` không có unique constraint: có thể tạo **60.000 bản ghi trùng**.
- Writer có unique constraint nhưng không idempotent: job mới có thể `FAILED` ngay vì duplicate key.
- Writer dùng upsert: dữ liệu có thể không trùng, nhưng tốn tài nguyên và có thể kích hoạt audit/trigger/event lần nữa.
- Writer gửi email hoặc thanh toán bên ngoài: side effect có thể lặp, khó hoặc không thể rollback.
- Writer dùng append-only file: có thể xuất file trùng hoặc thêm lại phần đã ghi.

**Không có cơ chế mặc định nào của Spring Batch bảo đảm “mỗi record chỉ xuất hiện một lần” khi bạn cố tạo instance mới để xử lý lại cùng dữ liệu.**

### 4.3. Tác hại lên vận hành

Sử dụng timestamp nhận diện ở mỗi lần bấm Run còn gây:

- Dashboard có hàng chục `JobInstance FAILED` thay vì một instance có tiến trình restart rõ ràng.
- Operator không biết execution nào là nguồn chính và execution nào là chạy lại vô ý.
- Retry scheduler có thể sinh nhiều logical instances cho cùng business date.
- Khó tính SLA “đã xử lý xong ngày N chưa?” từ metadata.
- Nhiều execution đồng thời của **các instance khác nhau** vẫn có thể ghi cùng dữ liệu.
- Cần dọn metadata và nghiệp vụ phức tạp hơn.
- Business reconciliation khó phân biệt bản ghi hợp lệ với bản ghi ghi lại.

### 4.4. Timestamp thậm chí không chắc luôn duy nhất

Tên bài “luôn tạo `JobInstance` mới” mô tả ý định của anti-pattern, nhưng `System.currentTimeMillis()` chỉ có độ phân giải mili giây và đồng hồ hệ thống có thể bị điều chỉnh. Hai lời gọi trong cùng millisecond hoặc nhiều node đồng hồ không đồng bộ **có thể cho cùng giá trị**.

Do đó timestamp không những sai ý nghĩa domain, mà còn **không bảo đảm uniqueness tuyệt đối**. Đổi sang UUID có thể giảm va chạm nhưng vẫn không sửa lỗi bản chất: tạo instance mới cho cùng công việc.

---

## 5. Các trạng thái và kết quả khi chạy cùng parameters

Trong Spring Batch, kết quả `jobLauncher.run(job, parameters)` phụ thuộc trạng thái `JobInstance` đã tồn tại:

| Trạng thái của instance/execution | Yêu cầu với cùng identifying params | Hướng xử lý |
| --- | --- | --- |
| Chưa tồn tại | Tạo instance và execution đầu tiên | Đây là launch hợp lệ |
| Có execution `FAILED`, job restartable | Có thể tạo execution mới cho cùng instance | Restart sau khi xử lý nguyên nhân |
| Có execution `STOPPED`, job restartable | Có thể restart theo cấu hình | Xem stop reason/checkpoint |
| Đã có execution `COMPLETED` | Thường bị từ chối bằng `JobInstanceAlreadyCompleteException` | Nếu cần đợt mới, chọn identity mới **có ý nghĩa** |
| Đang `STARTING`/`STARTED` | Không tạo execution thứ hai của cùng instance | Theo dõi execution hiện tại |
| Job cấu hình `preventRestart()` | Không restart instance đã thực thi | Xem lại nghiệp vụ/chính sách |
| Execution cũ ở trạng thái không nhất quán | Không tự ép launch | Điều tra metadata/process thực tế |

Một số exception thường gặp:

- `JobExecutionAlreadyRunningException`: instance đang có execution chạy.
- `JobInstanceAlreadyCompleteException`: instance đã hoàn thành.
- `JobRestartException`: không thể restart theo trạng thái/định nghĩa job.
- `JobParametersInvalidException`: parameters không vượt qua validator.

**Các exception này thường là tín hiệu về tính đúng đắn của job identity và lifecycle**, không phải lý do tự thêm timestamp để lách qua.

---

## 6. Phân biệt bốn hành động nghiệp vụ

### 6.1. Launch lần đầu

Một job cần xử lý kỳ mới, chẳng hạn dữ liệu ngày 17, trong khi kỳ ngày 16 đã hoàn tất.

```text
invoiceImportJob(tenant=merchant-42, businessDate=2026-11-16)
  => JobInstance #100 COMPLETED

invoiceImportJob(tenant=merchant-42, businessDate=2026-11-17)
  => JobInstance #101 (mới)
```

Ở đây instance mới là đúng vì **businessDate mới**.

### 6.2. Restart sau lỗi

Cùng businessDate, cùng tenant, job chưa hoàn tất:

```text
JobInstance #100
   JobExecution #200 FAILED
   JobExecution #201 COMPLETED (sau restart)
```

Yêu cầu là tiếp tục việc cũ, không phải tự thay identity. Có thể dùng `JobOperator.restart(failedExecutionId)` trong Spring Batch 5.x khi operator và job registry được cấu hình phù hợp.

### 6.3. Rerun một kỳ đã hoàn thành

Đây là yêu cầu **khác restart**: sau khi báo cáo ngày 16 đã `COMPLETED`, nghiệp vụ muốn tính lại vì nguồn đã được sửa.

Cần quyết định rõ:

- Có tạo **report revision** mới không?
- Có thay thế version cũ một cách nguyên tử không?
- Có giữ lịch sử kết quả cũ để audit không?
- Có thể phát sự kiện hoặc thanh toán lại không?
- Business key của revision là gì?

Một phương án là dùng identifying `revision` hoặc `reprocessRequestId` **được quản lý bởi nghiệp vụ**, không lấy timestamp hiện tại vô điều kiện. Ví dụ `businessDate=2026-11-16, revision=2` có nghĩa một lần tính lại được phê duyệt. Writer phải ghi kết quả theo version và tránh trộn kết quả.

### 6.4. Backfill lịch bị bỏ lỡ

Scheduler tắt từ ngày 11 đến ngày 13. Nếu mỗi ngày cần một báo cáo riêng, hãy tạo/khôi phục instance theo nominal business date:

```text
businessDate=2026-11-11 -> JobInstance cho ngày 11
businessDate=2026-11-12 -> JobInstance cho ngày 12
businessDate=2026-11-13 -> JobInstance cho ngày 13
```

Không dùng **thời điểm hệ thống hồi phục** làm identity cho cả ba slot; nếu cả ba chạy lúc 09:00 ngày 13, chúng vẫn phải xử lý đúng kỳ 11, 12 và 13.

---

## 7. Cách sửa đơn giản: xác định identity bằng business key

### 7.1. Ví dụ import theo ngày và tenant

Thay đoạn sai:

```java
// Anti-pattern: mỗi lần gọi tạo identity mới không liên quan nghiệp vụ.
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId)
    .addString("businessDate", businessDate.toString())
    .addLong("runAt", System.currentTimeMillis())
    .toJobParameters();
```

bằng đoạn có ý nghĩa rõ:

```java
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .toJobParameters();
```

Nếu cần thông tin truy vết cho request:

```java
JobParameters params = new JobParametersBuilder()
    .addString("tenantId", tenantId, true)
    .addString("businessDate", businessDate.toString(), true)
    .addString("correlationId", correlationId, false)
    .toJobParameters();
```

Cùng tenant + businessDate trỏ đến cùng `JobInstance`; thay correlationId không làm instance khác.

### 7.2. Ví dụ import một file cụ thể

Nếu input là file có ID ổn định:

```java
JobParameters params = new JobParametersBuilder()
    .addString("feedName", "orders-feed", true)
    .addString("sourceFileId", fileId, true)
    .addString("fileChecksum", checksum, false)
    .toJobParameters();
```

Tuy nhiên, vai trò `fileChecksum` cần được quyết định:

- Nếu cùng `fileId` mà nội dung đổi nghĩa là công việc **khác** cần import lại, checksum/version có thể cần tham gia identity.
- Nếu cùng file ID chỉ được phép import một lần và checksum chỉ để xác minh bất biến, checksum có thể non-identifying nhưng phải **reject** khi phát hiện nội dung khác, không lẳng lặng xử lý như file cũ.
- Nếu file path thay đổi theo nơi lưu trữ nhưng nội dung/ID nghiệp vụ giữ nguyên, đường dẫn thường không phải identity tốt.

Cốt lõi là có hợp đồng rõ về *cái gì được xem là cùng một nguồn*.

### 7.3. Ví dụ đồng bộ theo cửa sổ thời gian

Với một job xử lý event trong khoảng đóng/mở rõ:

```java
JobParameters params = new JobParametersBuilder()
    .addString("windowStartUtc",
        windowStart.toString(), true)
    .addString("windowEndUtc",
        windowEnd.toString(), true)
    .addString("streamName", streamName, true)
    .toJobParameters();
```

`windowStart` và `windowEnd` nên được tính từ lịch **nominal** hoặc watermark bền vững, không phải mỗi lần request tới server lấy `Instant.now()` rồi tự suy ra một cửa sổ mới.

---

## 8. Một service launch có chính sách rõ ràng

Một API quản trị thường nhận `businessDate` và `tenantId`. Service sau chủ động quyết định instance identity từ domain:

```java
package example.batch.launch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Service;

@Service
public class InvoiceImportLaunchService {

    private final JobLauncher jobLauncher;
    private final Job invoiceImportJob;

    public InvoiceImportLaunchService(
            JobLauncher jobLauncher,
            Job invoiceImportJob) {
        this.jobLauncher = jobLauncher;
        this.invoiceImportJob = invoiceImportJob;
    }

    public JobExecution launch(
            String tenantId,
            LocalDate businessDate) throws Exception {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                "tenantId is required");
        }
        if (businessDate == null) {
            throw new IllegalArgumentException(
                "businessDate is required");
        }

        JobParameters parameters = new JobParametersBuilder()
            .addString("tenantId", tenantId, true)
            .addString("businessDate",
                businessDate.toString(), true)
            .toJobParameters();

        return jobLauncher.run(invoiceImportJob, parameters);
    }
}
```

Service không ép tất cả lần gọi phải thành công bằng cách sinh ID mới. Nếu request được gửi lại và instance đã `COMPLETED`, exception là một kết quả vận hành có ý nghĩa; tầng API có thể map thành response “kỳ này đã được xử lý” hoặc trả về status của execution hiện hữu sau khi đối chiếu.

**Không nên nuốt exception rồi tự chạy với timestamp**:

```java
// Sai: né chính sách lifecycle khi gặp lỗi.
try {
    jobLauncher.run(job, businessParams);
} catch (JobInstanceAlreadyCompleteException ex) {
    // Không tự đổi runAt để 'thử lại'.
}
```

Nếu người dùng thực sự yêu cầu rerun completed period, hãy tạo một **workflow reprocess** riêng có authorization, audit và version/target semantics.

---

## 9. Restart đúng bằng `JobOperator`

### 9.1. Thay vì “chạy mới”, dùng execution ID bị lỗi

Trong Spring Batch 5.x:

```java
import org.springframework.batch.core.launch.JobOperator;

Long newExecutionId =
    jobOperator.restart(failedExecutionId);
```

- `failedExecutionId` là **ID của `JobExecution` trước đó**, không phải `JobInstance ID`.
- `restart` sử dụng metadata để tìm định nghĩa job và parameters cũ.
- Framework tạo một `JobExecution` mới gắn với **cùng `JobInstance`**.
- Step từng `COMPLETED` thường được bỏ qua, trừ cấu hình như `allowStartIfComplete(true)`.
- Step chưa hoàn tất có thể dùng `ExecutionContext` persisted để khôi phục reader/writer state.

### 9.2. Ví dụ service restart có precheck

```java
package example.batch.launch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class InvoiceRestartService {

    private final JobExplorer explorer;
    private final JobOperator operator;

    public InvoiceRestartService(
            JobExplorer explorer,
            JobOperator operator) {
        this.explorer = explorer;
        this.operator = operator;
    }

    public long restartFailed(long oldExecutionId)
            throws Exception {

        JobExecution previous =
            explorer.getJobExecution(oldExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "Unknown execution: " + oldExecutionId);
        }

        if (previous.getStatus() != BatchStatus.FAILED
                && previous.getStatus() != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Cannot restart execution in state "
                    + previous.getStatus());
        }

        // Kiểm tra quyền, DB health, side effects, job definition
        // và concurrency tại lớp nghiệp vụ trước khi thao tác.
        return operator.restart(oldExecutionId);
    }
}
```

Precheck không phải khóa chống race: giữa lúc đọc trạng thái và gọi restart, một node khác có thể đã khởi chạy cùng instance. `JobRepository`/`JobOperator` sẽ kiểm tra điều kiện ở thời điểm thao tác; tầng API cần xử lý thông báo “already running/already completed” rõ ràng.

### 9.3. Không mặc định lệnh restart đã hoàn thành

`JobOperator.restart(...)` trả về ID execution mới. Với launcher bất đồng bộ, execution có thể vẫn đang `STARTING` hoặc `STARTED`. Cần theo dõi bằng `JobExplorer` hoặc hệ thống giám sát đến trạng thái terminal, rồi xác nhận kết quả nghiệp vụ.

```text
restart(#200) -> newExecutionId=#202
                       |
                       v
             JobExplorer.getJobExecution(202)
                       |
              +--------+--------+
              |                 |
         STARTED             COMPLETED
              |                 |
         tiếp tục theo dõi     kiểm tra output
```

Nếu execution mới lại `FAILED`, điều tra nguyên nhân mới; không tự tạo JobInstance mới bằng timestamp để tránh việc instance cũ thất bại.

---

## 10. Metadata và những gì Spring Batch thực sự so sánh

Với JDBC `JobRepository`, một số bảng quan trọng gồm:

| Bảng | Thông tin |
| --- | --- |
| `BATCH_JOB_INSTANCE` | ID instance, tên job, key đại diện identifying parameters |
| `BATCH_JOB_EXECUTION` | Các executions của mỗi instance, trạng thái, thời gian |
| `BATCH_JOB_EXECUTION_PARAMS` | Parameter name/type/value và cờ identifying theo schema phiên bản |
| `BATCH_STEP_EXECUTION` | Step status, counts, commits, rollbacks |
| `BATCH_STEP_EXECUTION_CONTEXT` | State/checkpoint của step để restart |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context ở cấp job |

### 10.1. `JOB_KEY` không phải request ID

`BATCH_JOB_INSTANCE.JOB_KEY` là giá trị được repository tạo từ identifying parameters theo cơ chế framework. Không tự dùng `JOB_KEY` như một business key đọc được hoặc chỉnh tay hash để “gom lại” các instance do timestamp tạo ra.

Nếu hai executions khác timestamp identifying, chúng có thể thuộc hai hàng `BATCH_JOB_INSTANCE` khác nhau, dù business date giống nhau.

### 10.2. Cách kiểm tra các instance bất thường

Một query chẩn đoán đơn giản, chưa cần phụ thuộc vào schema tham số, có thể là:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'invoiceImportJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

Nếu thấy hàng loạt instance riêng cho các executions cùng business date, cần đối chiếu parameters tại `BATCH_JOB_EXECUTION_PARAMS`.

Trong **Spring Batch 5.x** schema phổ biến có các cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE` và `IDENTIFYING`:

```sql
SELECT
    p.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS p
WHERE p.JOB_EXECUTION_ID IN (200, 201, 202)
ORDER BY p.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

Schema metadata có khác biệt giữa major versions; không áp dụng nguyên SQL này nếu project đã tùy biến hoặc còn schema Spring Batch 4.x.

### 10.3. JobInstance identity là trách nhiệm của repository

Không cố gắng sửa trực tiếp `BATCH_JOB_INSTANCE` hoặc `BATCH_JOB_EXECUTION_PARAMS` để “hợp nhất” các instance khác nhau. Các bảng metadata có quan hệ, versioning và execution contexts liên quan. Nếu cần migration dữ liệu lịch sử, phải thiết kế theo một kế hoạch được kiểm soát với backup, audit và reconciliation, không chỉnh hash bằng SQL ad hoc.

---

## 11. Dấu hiệu anti-pattern trong codebase

Khi đọc Java code hoặc tài liệu vận hành, những pattern sau nên được xem xét kỹ:

```java
// Mỗi request tạo một identifying timestamp mới:
new JobParametersBuilder()
    .addLong("time", System.currentTimeMillis())
    .toJobParameters();
```

```java
// Mỗi request tạo identifying UUID mới:
new JobParametersBuilder()
    .addString("requestId", UUID.randomUUID().toString())
    .toJobParameters();
```

```java
// Đổi run.id để né việc job đã COMPLETED hoặc FAILED:
new JobParametersBuilder()
    .addLong("run.id", nextSequence())
    .toJobParameters();
```

```java
// Bắt lỗi lifecycle rồi cưỡng chế tạo instance khác:
try {
    return jobLauncher.run(job, stableParams);
} catch (JobInstanceAlreadyCompleteException ex) {
    return jobLauncher.run(job, withTimestamp(stableParams));
}
```

```java
// Scheduler tự dùng actual start time làm period identity:
@Scheduled(cron = "0 0 2 * * *")
public void scheduled() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
        .addString("period", Instant.now().toString())
        .toJobParameters();
    jobLauncher.run(reportJob, parameters);
}
```

Không phải dòng nào cũng tự động sai. **Sai là khi giá trị mới không biểu diễn công việc mới**. Với tác vụ chụp ảnh trạng thái “mỗi request là một snapshot độc lập” và writer ghi version có ý nghĩa, một ID duy nhất có thể hợp lệ. Nhưng khi đó nên dùng `snapshotRequestId` hoặc request domain ID được quản lý, không lấy thời gian hiện tại chỉ để khiến framework chấp nhận.

---

## 12. `RunIdIncrementer` có phải là giải pháp?

Spring Batch có `RunIdIncrementer`, có thể được dùng để cung cấp tham số `run.id` tăng dần khi chủ động bắt đầu một instance mới:

```java
@Bean
Job reportJob(
        JobRepository jobRepository,
        Step reportStep) {

    return new JobBuilder("reportJob", jobRepository)
        .start(reportStep)
        .incrementer(new RunIdIncrementer())
        .build();
}
```

Cần phân biệt:

- `RunIdIncrementer` giúp tính **parameters của instance tiếp theo**, không tự động “fix lỗi không restart được”.
- `JobOperator.startNextInstance(jobName)`, khi được cấu hình, là một thao tác **chủ động bắt đầu instance tiếp theo** theo job incrementer.
- Nếu nghiệp vụ cần mỗi lần chạy một đợt hoàn toàn mới, cách này có thể hợp lý.
- Nếu nghiệp vụ cần **tiếp tục instance FAILED**, dùng restart, không dùng incrementer.
- Nếu cùng một business date không được tạo hai báo cáo độc lập, một `run.id` mới là không đủ để định nghĩa tính đúng.

### 12.1. Bảng so sánh

| Mục tiêu | API / kỹ thuật | Identity |
| --- | --- | --- |
| Chạy kỳ đầu tiên | `JobLauncher.run(job, params)` | business key của kỳ |
| Retry/restart kỳ thất bại | `JobOperator.restart(executionId)` hoặc launch cùng identifying params theo contract | **Giữ nguyên** |
| Chạy kỳ tiếp theo | New businessDate/window/fileId; có thể dùng incrementer khi thích hợp | **Mới có chủ đích** |
| Rerun kỳ completed | Quy trình revision/reprocess riêng với business ID rõ ràng | Mới theo version/revision |
| Điều tra lỗi | `JobExplorer`, metadata, step failure | Không đổi |
| Ghi log thời điểm bấm chạy | Audit event / non-identifying metadata | Không cần đổi identity |

Một script vận hành “nếu báo already completed thì tăng run.id cho tới khi launch được” là dấu hiệu workflow đang thiếu quyết định nghiệp vụ.

---

## 13. Scheduler: dùng nominal slot thay vì `Instant.now()`

### 13.1. Vấn đề của actual launch time

Giả sử báo cáo chạy mỗi ngày 02:00 nhưng node bị restart lúc 09:00. Nếu scheduler nhận được một trigger hồi phục và truyền `Instant.now()` làm identifying parameter, lần chạy sẽ có identity 09:00, không nói được nó đang đại diện cho ngày nào.

Đặc biệt khi scheduler retry cùng một trigger:

```text
02:00:00 slot S
02:00:05 attempt A -> timeout
02:00:06 attempt B -> identifying runAt đổi
02:00:07 attempt C -> identifying runAt đổi

Ba JobInstances tiềm năng cho cùng slot S.
```

Thay vào đó, cần một **nominal scheduled slot** độc lập với thời điểm thực sự gửi request.

### 13.2. Mapping một slot thành JobParameters

```java
public JobParameters paramsForSlot(
        String tenantId,
        Instant scheduledAt,
        LocalDate businessDate) {

    return new JobParametersBuilder()
        .addString("tenantId", tenantId, true)
        .addLong("scheduledAtEpochMs",
            scheduledAt.toEpochMilli(), true)
        .addString("businessDate",
            businessDate.toString(), false)
        .toJobParameters();
}
```

Ví dụ này giả định `tenantId + scheduledAt` là khóa ổn định cho một scheduled slot. `businessDate` có thể được đánh dấu identifying nếu là một phần quan trọng của identity; quyết định phải nhất quán với cách job được lập lịch. Không nên để một định danh đầy đủ được sinh từ nominal slot rồi lại thêm actual start time.

### 13.3. Khi dùng `@Scheduled`

`@Scheduled` thường chỉ gọi method tại thời điểm callback, không cung cấp một persistent “danh sách tất cả nominal slots bị mất trong downtime”. Để xử lý đủ từng kỳ, tốt hơn tách:

```text
@Scheduled tick
      |
      v
Schedule reconciler
      |
      v
Tìm các slot PENDING / FAILED trong ledger
      |
      v
Launch bằng stable slot key, hoặc restart existing execution
```

Ví dụ sketch:

```java
@Scheduled(fixedDelayString = "PT1M")
public void reconcileDueReports() {
    // Đọc lịch từ bảng expected slots đã persist.
    // Với mỗi slot đến hạn: claim độc quyền.
    // Tra JobRepository để launch/restart/reconcile.
    scheduleReconciler.runDueSlots();
}
```

Đây là kiến trúc minh họa; `scheduleReconciler` là service nghiệp vụ do ứng dụng viết. Không suy ra đủ các slot trong downtime chỉ từ `LocalDate.now()` ở callback.

### 13.4. Quartz và misfire

Quartz có misfire policy như `DoNothing`, `FireAndProceed`, `IgnoreMisfires`, nhưng các policy này không tự bảo đảm mỗi business date cũ có một Batch job đã hoàn tất.

Một Quartz adapter có thể dùng `scheduledFireTime` của trigger hiện tại để lập parameters, nhưng khi misfire được điều chỉnh (đặc biệt `FireAndProceed`), không nên mặc định thời điểm đó là danh sách đầy đủ các slot bị lỡ. Với backfill, dùng **slot ledger** và business calendar đã được định nghĩa trước.

---

## 14. Định danh ổn định vẫn cần chống race condition

Chuyển từ identifying timestamp sang `businessDate` cố định là bước đúng, nhưng chưa giải quyết mọi tình huống concurrency.

Ví dụ hai request:

```text
Node A: launch(tenant=A, businessDate=2026-11-16)
Node B: launch(tenant=A, businessDate=2026-11-16)
```

Khi cùng dùng một JDBC `JobRepository` và cùng identifying params, framework có cơ chế quản lý tạo instance/execution và kiểm tra trạng thái. Một request có thể được chấp nhận, request còn lại bị từ chối vì instance đang chạy hoặc đã hoàn thành. Điều đó tốt hơn hai instances song song, nhưng tầng API vẫn phải xử lý race và cung cấp response rõ ràng.

### 14.1. Nhận diện request trùng tại tầng nghiệp vụ

Một mô hình có thể là:

```sql
CREATE TABLE batch_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    business_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL,
    job_execution_id BIGINT,
    CONSTRAINT uq_batch_request
        UNIQUE (job_name, tenant_id, business_date)
);
```

Bảng này là **business request ledger**, không phải metadata có sẵn của Spring Batch. Unique constraint giúp hai nodes không thể claim hai business requests độc lập cho cùng kỳ.

Quy trình gợi ý:

1. Nhận request với business key.
2. Insert-if-absent hoặc atomic claim trên row tồn tại.
3. Tra `JobExplorer`/`JobRepository` để biết instance nào đang chạy/đã completed/failed.
4. Launch lần đầu hoặc restart instance cũ theo trạng thái.
5. Cập nhật ledger và reconciler để xử lý crash giữa các bước.
6. Trả về instance/execution ID thay vì bịa một timestamp mới.

### 14.2. `JobRepository` bảo vệ identity, không bảo vệ mọi side effect

Hai `JobInstance` khác business key nhưng cùng đọc/ghi một resource vật lý vẫn có thể gây tranh chấp. Ví dụ import file A và file B chứa cùng external order ID. Cần unique constraint, partition ownership, idempotent writer và nguyên tắc transaction bên cạnh Spring Batch metadata.

### 14.3. Khi request timeout không rõ đã launch chưa

Client gửi launch nhưng bị timeout trước khi nhận `JobExecution ID`:

```text
Client -------- request --------> Server
Client <------- timeout ---------x
                              Server đã tạo execution?
```

Không sinh identifying timestamp mới rồi gửi lại. Hãy query theo stable business key để nhận diện job instance/execution đã tồn tại. Nếu có execution đang chạy, tiếp tục theo dõi; nếu completed, trả kết quả; nếu failed, phục hồi theo runbook.

---

## 15. Checkpoint và `ExecutionContext`: vì sao restart đúng instance mới có tác dụng?

Trong chunk-oriented processing, reader/writer có thể implement `ItemStream` để lưu/khôi phục state. Ví dụ một file reader giữ vị trí dòng:

```text
JobInstance A
  StepExecution 1:
    open(context offset=0)
    chunk 1 commit -> offset=100
    chunk 2 commit -> offset=200
    chunk 3 lỗi, rollback
  Repository checkpoint: offset=200

JobInstance A, StepExecution 2 (restart):
    open(context offset=200)
    xử lý tiếp phần chưa commit

JobInstance B, timestamp mới:
    open(new context, offset=0)
    xử lý lại từ đầu
```

Ở một step có item filtering, retries, skips hoặc paging, checkpoint có thể phức tạp hơn con số offset. Nhưng nguyên tắc vẫn giữ: **restart dựa trên trạng thái step/execution của instance cũ**, không phải dựa trên việc job name giống nhau hoặc dữ liệu input trông tương tự.

### 15.1. `allowStartIfComplete` không sửa lỗi instance mới

Một step có thể cấu hình:

```java
Step step = new StepBuilder("validateStep", jobRepository)
    .tasklet(validateTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

Thiết lập này làm step được phép chạy lại **trong một restart của cùng instance** dù từng completed. Nó không buộc Spring Batch nhận diện hai instances khác timestamp là một. Không dùng nó thay cho thiết kế identifying parameters.

### 15.2. `preventRestart` và `startLimit`

`preventRestart()` ở job có thể cấm restart. `startLimit` ở step giới hạn số lần khởi chạy step trong cùng instance. Nếu bạn luôn tạo instance mới bằng timestamp, các giới hạn restart **gắn với instance cũ** có thể bị né tránh. Điều này nguy hiểm khi những giới hạn đó được đặt để bảo vệ side effects, chi phí, hoặc nghiệp vụ chỉ được làm một lần.

### 15.3. Tại sao reset `ExecutionContext` không phải lời giải

Nếu checkpoint đã không phù hợp vì reader implementation hoặc dữ liệu nguồn thay đổi, đừng tạo instance mới chỉ để bỏ qua lỗi. Cần đánh giá migration checkpoint, reprocess policy hoặc chạy remediation có version. Việc “sửa nhanh” bằng timestamp chỉ che bất đồng dữ liệu/metadata.

---

## 16. Thiết kế writer idempotent khi có rerun và retry

Ngay cả khi restart đúng `JobInstance`, một số chunk có thể bị xử lý lại nếu commit outcome không rõ hoặc metadata checkpoint chưa persist. Vì thế writer phải có hợp đồng đối với item lặp.

### 16.1. Khóa nghiệp vụ ở database

Ví dụ:

```sql
CREATE TABLE imported_invoices (
    tenant_id VARCHAR(100) NOT NULL,
    external_invoice_id VARCHAR(120) NOT NULL,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    CONSTRAINT uq_imported_invoice
        UNIQUE (tenant_id, external_invoice_id)
);
```

Unique key buộc một invoice chỉ xuất hiện một lần theo contract ví dụ. Với dữ liệu thực, có thể cần thêm version hoặc businessDate nếu external IDs được tái sử dụng; khóa cần phản ánh domain.

### 16.2. UPSERT không phải vạn năng

Một PostgreSQL writer có thể dùng:

```sql
INSERT INTO imported_invoices (
    tenant_id,
    external_invoice_id,
    business_date,
    amount
)
VALUES (?, ?, ?, ?)
ON CONFLICT (tenant_id, external_invoice_id)
DO UPDATE SET
    amount = EXCLUDED.amount,
    business_date = EXCLUDED.business_date;
```

Cách này có thể idempotent về row state nếu input không thay đổi. Nhưng UPDATE lặp lại có thể kích hoạt trigger/event, tạo audit row mới hoặc ghi đè phiên bản dữ liệu được chỉnh sửa hợp lệ. Với tài chính, có thể cần append-only ledger hoặc write-once + correction events, không dùng upsert tùy tiện.

### 16.3. Side effect ngoài transaction

Gửi email, payment request hoặc Kafka event từ processor/writer có thể xảy ra trước khi checkpoint commit. Dùng identifying timestamp mới không giải quyết duplicate side effects; trái lại còn tăng khả năng phát lại toàn bộ.

Các kỹ thuật thích hợp:

- Idempotency key theo business operation.
- Transactional outbox khi phù hợp.
- Consumer deduplication.
- Unique constraint và reconciliation.
- Đối chiếu external delivery/payment state trước khi rerun.

### 16.4. Correctness phải được kiểm tra bằng business output

Một job `COMPLETED` không chứng minh dữ liệu không trùng nếu nó đã xử lý lại toàn bộ. Kiểm tra:

- Số unique invoices/orders theo business key.
- Tổng amount/checksum theo kỳ.
- Chỉ một báo cáo published version nếu contract quy định.
- Không có duplicate events/payment requests.
- Không có orphaned failed instances không được đối soát.

---

## 17. Unit test xác minh định danh JobParameters

Không cần khởi động Spring context để kiểm tra một service tạo parameters.

### 17.1. Factory thuần hàm

```java
package example.batch.launch;

import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public final class InvoiceJobParametersFactory {

    public JobParameters create(
            String tenantId,
            LocalDate businessDate,
            String correlationId) {

        return new JobParametersBuilder()
            .addString("tenantId", tenantId, true)
            .addString("businessDate",
                businessDate.toString(), true)
            .addString("correlationId", correlationId, false)
            .toJobParameters();
    }
}
```

### 17.2. Test cùng business key, khác correlation ID

```java
import java.time.LocalDate;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameter;
import org.springframework.batch.core.JobParameters;

import static org.junit.jupiter.api.Assertions.*;

class InvoiceJobParametersFactoryTest {

    private final InvoiceJobParametersFactory factory =
        new InvoiceJobParametersFactory();

    @Test
    void identifyingValuesStayStableAcrossRequests() {

        LocalDate date = LocalDate.of(2026, 11, 16);

        JobParameters first =
            factory.create("merchant-42", date, "trace-A");
        JobParameters second =
            factory.create("merchant-42", date, "trace-B");

        Map<String, JobParameter<?>> a =
            first.getIdentifyingParameters();
        Map<String, JobParameter<?>> b =
            second.getIdentifyingParameters();

        assertEquals(a, b);
        assertEquals(2, a.size());
        assertFalse(a.containsKey("correlationId"));
    }

    @Test
    void aDifferentBusinessDateChangesIdentity() {
        JobParameters first = factory.create(
            "merchant-42",
            LocalDate.of(2026, 11, 16),
            "trace-1");

        JobParameters second = factory.create(
            "merchant-42",
            LocalDate.of(2026, 11, 17),
            "trace-2");

        assertNotEquals(
            first.getIdentifyingParameters(),
            second.getIdentifyingParameters());
    }
}
```

Ví dụ dùng `getIdentifyingParameters()` của `JobParameters` trong Spring Batch 5.x. Test so sánh tập identifying parameters như một biểu diễn trực tiếp của ý định thiết kế; integration test với `JobRepository` vẫn cần thiết để xác minh lifecycle thật.

### 17.3. Test phát hiện anti-pattern

Một test có thể gọi factory hai lần với cùng business key ở hai thời điểm khác nhau rồi assert identifying parameters vẫn bằng nhau. Nếu ai thêm `System.currentTimeMillis()` thành identifying, test sẽ có khả năng phát hiện thay đổi ý nghĩa identity. Có thể inject `Clock` để kiểm soát thời gian test thay vì dùng sleep, tránh test flaky.

---

## 18. Integration test: job thất bại rồi restart cùng instance

Một integration test cần chứng minh không chỉ parameters ổn định mà cả `JobInstance` thực sự được tái sử dụng khi restart.

### 18.1. Kịch bản kiểm thử

```text
invoiceImportJob
  prepareStep  : luôn COMPLETED
  importStep   : lần 1 throw exception
                 lần 2 thành công

Launch với identifying businessDate=2026-11-16:
  JobExecution #1 FAILED

Restart execution #1:
  JobExecution #2 COMPLETED

Assertions:
  execution IDs khác nhau
  JobInstance IDs bằng nhau
  prepareStep chỉ thực hiện một lần
  importStep thực hiện hai lần
```

### 18.2. Cấu hình test

Gradle ví dụ với Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`src/test/resources/application-identity-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
  datasource:
    generate-unique-name: true
```

H2 in-memory phù hợp để test hai executions **trong cùng context**. Restart qua JVM/container restart thật đòi metadata repository bền vững.

### 18.3. JUnit 5 / Spring Batch 5 integration test

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = StableIdentityRestartTest.TestApp.class
)
@ActiveProfiles("identity-test")
class StableIdentityRestartTest {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JobOperator operator;

    @Autowired
    JobExplorer explorer;

    @Autowired
    AtomicInteger prepareCalls;

    @Autowired
    AtomicInteger importCalls;

    @Test
    void restartCreatesNewExecutionOnSameInstance()
            throws Exception {

        JobParameters params = new JobParametersBuilder()
            .addString("tenantId", "merchant-42", true)
            .addString("businessDate", "2026-11-16", true)
            .toJobParameters();

        JobExecution first = launcher.launchJob(params);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, prepareCalls.get());
        assertEquals(1, importCalls.get());

        Long restartedId = operator.restart(first.getId());
        JobExecution restarted =
            explorer.getJobExecution(restartedId);

        // Test giả định JobLauncher đồng bộ; launcher async
        // phải poll đến terminal status trước khi assert.
        assertNotNull(restarted);
        assertEquals(
            BatchStatus.COMPLETED,
            restarted.getStatus());

        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId());

        assertEquals(1, prepareCalls.get());
        assertEquals(2, importCalls.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(TestJobs.class)
    static class TestApp { }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJobs {

        @Bean
        AtomicInteger prepareCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicInteger importCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicBoolean failFirst() {
            return new AtomicBoolean(true);
        }

        @Bean
        Step prepareStep(
                JobRepository repository,
                PlatformTransactionManager tx,
                AtomicInteger prepareCalls) {

            return new StepBuilder("prepareStep", repository)
                .tasklet((contribution, context) -> {
                    prepareCalls.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
        }

        @Bean
        Step importStep(
                JobRepository repository,
                PlatformTransactionManager tx,
                AtomicInteger importCalls,
                AtomicBoolean failFirst) {

            return new StepBuilder("importStep", repository)
                .tasklet((contribution, context) -> {
                    importCalls.incrementAndGet();

                    if (failFirst.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated temporary failure");
                    }

                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
        }

        @Bean
        Job invoiceImportJob(
                JobRepository repository,
                Step prepareStep,
                Step importStep) {

            return new JobBuilder(
                "invoiceImportJob", repository)
                .start(prepareStep)
                .next(importStep)
                .build();
        }
    }
}
```

**Giải thích:**

- `AtomicBoolean` là fixture tạo lỗi một lần; nó không phải checkpoint nghiệp vụ.
- `JobLauncherTestUtils` trong context này chỉ có một job để chọn. Với context nhiều jobs, cần cấu hình job under test rõ ràng.
- `prepareStep` completed lần đầu nên mặc định bỏ qua trên restart.
- `importStep` failed lần đầu, chạy tiếp lần hai.
- `operator.restart(first.getId())` tạo execution mới trong cùng instance.
- `JobExplorer` đọc lại metadata persisted để kiểm tra quan hệ instance/execution.
- Nếu dùng launcher async, một lần đọc ngay sau restart chưa đủ để assert terminal `COMPLETED`.

### 18.4. Test riêng cho timestamp anti-pattern

Tạo một job thử nghiệm không có side effect và launch hai lần với cùng `businessDate` nhưng hai timestamp identifying **khác nhau do test chủ động đặt**. Assert repository tạo hai `JobInstance` khác nhau. Test này cho thấy ý nghĩa identity một cách deterministic, không dựa vào `Thread.sleep` hay hy vọng hai `System.currentTimeMillis()` khác nhau.

Sau đó chạy cùng job với stable parameters; nếu instance đầu đã completed, launch lần nữa sẽ không tạo thêm execution như một instance mới. Đó là cơ chế bảo vệ lifecycle mong muốn.

### 18.5. Test checkpoint thật

Fixture tasklet đơn giản không chứng minh reader có restart đúng checkpoint. Với chunk job đọc 100 items, commit interval 20, cố tình fail sau một số chunk và restart:

- Xác minh checkpoint persisted trong `ExecutionContext`.
- Reader implement `ItemStream` và nhận state đúng khi `open`.
- Số unique output records sau restart là 100.
- Không xử lý lại/ghi trùng phần đã commit ngoài hợp đồng.
- Nếu test chọn writer idempotent, assert kết quả cuối thay vì chỉ đếm method calls.

---

## 19. Migration: sửa job production đã dùng timestamp từ lâu

Nếu code đang luôn thêm `runAt` nhận diện, việc bỏ tham số này sẽ thay đổi `JobInstance` identity kể từ thời điểm triển khai. Những failed instances lịch sử vẫn tồn tại trong metadata. Không nên giả định sửa một dòng code sẽ tự biến các instance cũ thành một.

### 19.1. Khảo sát trước khi đổi

1. Liệt kê tất cả jobs có timestamp/UUID/run.id identifying.
2. Xác định nhóm nghiệp vụ: snapshot độc lập, import file, daily report, settlement, backfill...
3. Truy vấn `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION_PARAMS` để xem số instances theo business key.
4. Xác định instance nào `COMPLETED`, `FAILED`, đang `STARTED`, hoặc có output chưa đối soát.
5. Đối chiếu dữ liệu nghiệp vụ: đã có duplicate rows/events/file exports không?
6. Kiểm tra có orchestrator hoặc API bên ngoài đang tự gửi timestamp theo contract cũ không.
7. Phê duyệt business identity mới và chính sách reprocess completed period.

### 19.2. Phân nhóm lịch sử

| Dữ liệu cũ | Cách xử lý thường hợp lý |
| --- | --- |
| Instance completed, output đúng | Giữ audit; đánh dấu kỳ đã hoàn thành trong ledger nghiệp vụ |
| Nhiều instances completed cho cùng kỳ | Reconcile versions/output, xác định bản chính thức và xử lý trùng |
| Instance failed, checkpoint còn hợp lệ | Cân nhắc restart **đúng instance cũ** trước khi bỏ cơ chế timestamp hoàn toàn |
| Instance failed, checkpoint không còn tương thích | Quy trình remediation/reprocess có kiểm soát; không tự SQL merge |
| Instance đang `STARTED` sau process crash | Xác minh worker đã dừng và thực hiện recovery metadata phù hợp |
| Không tìm thấy execution nhưng output đã tồn tại | Reconcile output và request log trước khi launch mới |

### 19.3. Tránh thay đổi schema hoặc metadata bằng tay

Đừng xóa tham số `runAt` từ `BATCH_JOB_EXECUTION_PARAMS` hoặc sửa `JOB_KEY` để ép Spring Batch gộp instances cũ. Những thao tác này phá quan hệ identity/metadata và có thể làm mất khả năng restart, audit hoặc đồng nhất state.

Phương án bền vững hơn:

- Giữ nguyên lịch sử Spring Batch.
- Xây/migrate một **business request ledger** theo key ổn định.
- Tách logic “launch kỳ mới” và “restart execution cũ”.
- Cho phép xử lý những failed instances cũ theo runbook.
- Nếu bắt buộc reprocess, tạo revision có semantics rõ và writer idempotent.
- Bổ sung unit/integration tests để chặn việc timestamp nhận diện tái xuất hiện.

### 19.4. Cách rollout thận trọng

```text
Giai đoạn 1: quan sát
  - Log jobName/identifying parameters
  - Thống kê duplicate business keys
  - Lập bản đồ failed instances và checkpoint

Giai đoạn 2: bổ sung business identity
  - Tạo params factory + tests
  - Tạo request/slot ledger nếu cần
  - Bổ sung query/reconciliation

Giai đoạn 3: chuyển scheduler/API
  - Dùng stable identifying params
  - Return existing status khi duplicate request
  - Gọi restart cho FAILED instance

Giai đoạn 4: xác minh
  - Không tạo JobInstance mới cho retry cùng kỳ
  - Không duplicate business output
  - Theo dõi tỷ lệ restart thành công
```

Đây là ví dụ rollout, không thay thế change management của môi trường có dữ liệu quan trọng.

---

## 20. Quy tắc cho API và runbook vận hành

### 20.1. Không biến mọi nút “Run” thành request mới

Một UI vận hành có thể có ba action rõ ràng:

| Action | Mục đích | Parameter semantics |
| --- | --- | --- |
| **Start business period** | Xử lý một kỳ chưa từng chạy | Stable tenant/date/file/slot key |
| **Restart failed execution** | Tiếp tục cùng công việc đã lỗi | Execution ID cũ, same instance |
| **Reprocess completed period** | Tạo revision mới theo phê duyệt | Revision ID + target output policy |

Tách action giúp tránh tình huống người vận hành nhấn “Run again” nhưng không biết job sẽ đọc tiếp, chạy lại từ đầu hay ghi đè kết quả.

### 20.2. Trước khi restart

- Đọc job name, JobInstance ID, identifying parameters, JobExecution ID và status.
- Xác minh instance chưa `COMPLETED` bởi execution mới hơn.
- Kiểm tra job definition/step names và `ExecutionContext` tương thích.
- Xác định nguyên nhân thất bại đã được xử lý.
- Đối chiếu side effect và transaction outcome nếu lỗi gần commit.
- Xác nhận không có execution/worker khác đang chạy.
- Ghi audit ai/điều gì yêu cầu restart, không sửa parameters nhận diện bằng tay.

### 20.3. Sau khi restart

- Ghi nhận new JobExecution ID.
- Theo dõi đến terminal status.
- Kiểm tra checkpoint, read/write/skip/rollback counts.
- Đối chiếu business output và dữ liệu nguồn.
- Đánh dấu một kỳ hoàn thành khi kết quả nghiệp vụ đúng.
- Không coi “API trả execution ID” đồng nghĩa job đã thành công.

### 20.4. Khi dữ liệu đã bị ghi trùng

Nếu nhiều instances timestamp khác nhau đã ghi cùng dữ liệu, **đừng chỉ dọn những dòng trong `BATCH_JOB_INSTANCE`**. Cần ưu tiên:

1. Ngừng tạo request trùng.
2. Phân loại output bằng business key và version.
3. Xác định bản ghi/event nào là chính thức theo audit.
4. Thực hiện remediation nghiệp vụ có transaction/reconciliation.
5. Kiểm tra downstream side effects.
6. Giữ lịch sử đủ để giải thích sự cố.

Metadata Spring Batch không tự quyết định một payment/email/file đã gửi ngoài hệ thống nên được thu hồi như thế nào.

---

## 21. Kiến trúc đáng tin cậy cho scheduled và manual batch

```text
       Scheduler / REST / Operator
                   |
                   v
          Business request layer
          - tenant
          - businessDate / sourceFileId
          - optional revision
                   |
                   v
          Stable parameters factory
          - identifying business keys
          - non-identifying trace details
                   |
                   v
        Query JobExplorer / Repository
                   |
          +--------+----------+
          |                   |
     No instance           Existing instance
          |                   |
          v             +-----+---------------------+
   JobLauncher.run      |           |              |
                    FAILED       STARTED        COMPLETED
                       |           |              |
                       v           v              v
                JobOperator     monitor       return status /
                restart        existing       explicit reprocess
                       |
                       v
                 JobExecution new
                 same JobInstance
                       |
                       v
          Validate business output
```

Business request layer có thể dùng một bảng ledger với unique constraint theo business key để tránh các request đồng thời hoặc retry mạng gây race. Dùng `JobExplorer` để tra cứu execution, nhưng đừng dựa vào “check then launch” như khóa tuyệt đối; repository và atomic claim trong database vẫn phải được thiết kế đúng.

Đối với job có nhiều tenant, phân quyền không được dựa chỉ vào việc client biết JobExecution ID. Một endpoint restart cần kiểm tra job/tenant ownership và role trước khi gọi operator.

---

## 22. Một số câu hỏi thường gặp

### 22.1. “Muốn chạy job mỗi ngày, sao không lấy ngày giờ hiện tại?”

Có thể lấy **ngày nghiệp vụ** để xác định kỳ mới, nhưng không nên dùng **thời điểm request nhận tại node** như một ID duy nhất. Với job mỗi ngày, `businessDate` hoặc nominal schedule slot là khóa có ý nghĩa hơn. Nếu batch chạy lúc 02:00 để xử lý dữ liệu ngày trước, giá trị identifying nên là ngày dữ liệu cần xử lý chứ không đơn giản là ngày hiện tại.

### 22.2. “Đánh dấu timestamp `identifying=false` thì đã giải quyết hết chưa?”

Không. Nó giúp thời gian đó không tạo `JobInstance` mới, nhưng vẫn cần chính sách rõ cho:

- Request trùng khi instance đang chạy.
- Request sau khi instance đã completed.
- Restart instance failed.
- Audit ai gửi request và khi nào.
- Định danh dữ liệu nguồn/đợt xử lý.
- Khả năng lặp lại side effect khi commit outcome không chắc chắn.

### 22.3. “Có phải mọi job đều nên restart được?”

Không. Một số job được thiết kế không restartable do thao tác không thể lặp lại an toàn. Khi đó cần một quy trình compensation/reprocess riêng. Nhưng việc tạo JobInstance mới bằng timestamp **không tự biến một thao tác không an toàn thành an toàn**; có thể còn vượt qua cơ chế `preventRestart()` được đặt để bảo vệ nghiệp vụ.

### 22.4. “Nếu muốn chạy lại job đã `COMPLETED` thì sao?”

Một `JobInstance` completed không thể restart theo lifecycle thông thường. Hãy xác định mục tiêu reprocess có thật, version của kết quả và ảnh hưởng downstream. Nếu cần logical run mới, tạo một **business revision** rõ ràng (ví dụ `revision=2`), chứ không âm thầm dùng timestamp để tạo instance khác.

### 22.5. “Dùng UUID thay timestamp thì có tốt hơn không?”

UUID giúp tránh va chạm ID nếu thật sự cần mỗi request là một đơn vị công việc độc lập. Nhưng nếu đây là retry cùng business period hoặc cùng source file, UUID identifying vẫn gây ra **một `JobInstance` khác**, nên không khôi phục checkpoint cũ. Vấn đề là ý nghĩa của identity, không phải chọn thuật toán sinh ID.

### 22.6. “JobParameters có cần truyền mọi thông tin nghiệp vụ không?”

Không. Chỉ đưa vào identifying params những thuộc tính cần thiết để định danh logical run. Các dữ liệu lớn/nhạy cảm hoặc thay đổi theo từng item nên được lưu ở nguồn dữ liệu chuyên biệt và truy cập qua ID, không nhồi vào JobParameters. Các trường audit có thể ở non-identifying params hoặc request log.

### 22.7. “Restart bằng `JobLauncher.run` với cùng parameters có được không?”

Có những trường hợp framework có thể restart instance failed khi launch cùng job và cùng identifying parameters, nếu trạng thái và cấu hình cho phép. Tuy nhiên, trong vận hành, `JobOperator.restart(executionId)` thể hiện ý định rõ và tận dụng metadata của execution cũ. Dù dùng cách nào, **đừng thay identifying parameters một cách vô cớ**.

### 22.8. “Nếu `System.currentTimeMillis()` trùng giá trị ở hai request?”

Hai requests có thể cùng identity ngoài ý muốn; framework sẽ xử lý theo trạng thái instance tương ứng, có thể từ chối một request đang chạy/đã completed. Timestamp không phải business ID chuẩn; nếu thực sự cần mỗi invocation độc lập, thiết kế request ID/sequence bền vững, nhưng phải có hợp đồng dữ liệu và idempotency phù hợp.

---

## 23. Bài thực hành

### Bài 1 — Xác định số `JobInstance`

Cho ba bộ parameters của cùng `invoiceImportJob`:

```text
A: businessDate=2026-11-16 [true], runAt=1000 [true]
B: businessDate=2026-11-16 [true], runAt=2000 [true]
C: businessDate=2026-11-16 [true], runAt=3000 [true]
```

Hãy xác định số logical instances framework sẽ nhìn thấy. Sau đó chuyển `runAt` sang `identifying=false` và giải thích điều gì thay đổi; lưu ý trạng thái completed/running vẫn kiểm soát khả năng launch.

### Bài 2 — Viết JobParameters factory

Tạo `JobParametersFactory` cho job import hóa đơn theo tenant + business date, thêm non-identifying `correlationId`. Viết unit test:

- Cùng tenant/date, correlation khác -> identifying params bằng nhau.
- Khác tenant hoặc date -> identifying params khác nhau.
- Không có timestamp/UUID nhận diện.
- Đảm bảo timezone và định dạng businessDate được chuẩn hóa.

### Bài 3 — Mô phỏng lỗi restart

Tạo chunk job nhập 100 item, chunk size 20, cố tình lỗi sau khi 40 item đã commit. Thử hai phương án:

1. Chạy lại bằng identifying timestamp mới.
2. Restart execution cũ bằng `JobOperator`.

So sánh JobInstance IDs, reader checkpoint, số records writer nhận và số unique records đã ghi. Giải thích vì sao phương án 1 có thể gây trùng.

### Bài 4 — Scheduler sau downtime

Giả sử cron 02:00 mỗi ngày, ứng dụng dừng ngày 11–12 và khởi động lại 09:00 ngày 13. Xây danh sách nominal slots bị lỡ và ánh xạ mỗi slot vào identifying parameters ổn định.

Viết reconciler có thể nhận request trùng nhưng không tạo JobInstance mới cho cùng slot; thêm giới hạn backfill tối đa hai slots mỗi lần.

### Bài 5 — Completed rerun có phê duyệt

Báo cáo ngày 16 đã `COMPLETED`, nguồn được sửa và cần tính lại. Thiết kế `revision` và bảng published reports để lần rerun sinh version 2 thay vì tạo file/row trùng không kiểm soát. Nêu cách giữ lịch sử version 1 và tránh phát lại side effect.

### Bài 6 — Phát hiện instances lịch sử không đúng

Dựa vào bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` và `BATCH_JOB_EXECUTION_PARAMS`, viết query/listing xác định các executions cùng business date nhưng khác identifying `runAt`. Xây runbook phân loại failed/completed, đối soát output trước khi đổi code.

### Bài 7 — API idempotency

Hai request cùng tenant/date đến trong cùng millisecond và một request timeout sau khi server đã tạo execution. Thiết kế unique business request ledger, atomic claim và truy vấn trạng thái existing execution. Chứng minh không cần thêm timestamp để caller nhận được phản hồi ổn định.

---

## 24. Checklist trước khi phát hành một Batch launcher

- [ ] Mỗi identifying parameter biểu diễn một phần **business identity** có ý nghĩa.
- [ ] Timestamp request/trace ID không trở thành identifying chỉ để né duplicate.
- [ ] Mỗi kỳ hoặc source file có định dạng key ổn định qua retry và deployment.
- [ ] Trạng thái `FAILED`/`STOPPED` có đường restart rõ ràng.
- [ ] Trạng thái `STARTED` được giám sát thay vì tạo instance mới.
- [ ] Trạng thái `COMPLETED` được trả về rõ thay vì “tăng run.id cho chạy lại”.
- [ ] Reprocess completed period có revision, audit và chính sách output riêng.
- [ ] Scheduler sử dụng nominal slots và có cơ chế xử lý missed schedule khi cần.
- [ ] Writer có unique business keys/idempotency theo yêu cầu retry/restart.
- [ ] JobRepository bền vững qua process restart, giữ `ExecutionContext` cho checkpoint.
- [ ] Unit test kiểm tra identifying params; integration test kiểm tra JobInstance ID và restart.
- [ ] Metrics/logs phân biệt số JobInstances mới, số restarts và số business periods hoàn tất.

Khi code launcher buộc phải sinh thời gian hiện tại để “Spring Batch chịu chạy”, hãy xem đây là dấu hiệu cần thiết kế lại **identity và lifecycle**. Giải pháp thường là business keys ổn định cho công việc cũ, restart đúng execution, và quy trình rerun riêng cho công việc thực sự mới.

## 25. Tài liệu tham khảo

- [Spring Batch Reference — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobParameters`, trạng thái completed/running và job launch.
- [Spring Batch Reference — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, `JobExplorer` và restart theo execution ID.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): quản lý execution/instance metadata.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` và tham số nhận diện.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint và trạng thái phục hồi.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` và job test utilities.
- [Spring Batch 5.2 API — JobParametersBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/JobParametersBuilder.html): xác định identifying/non-identifying parameters.
- [Spring Batch 5.2 API — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): restart và startNextInstance.
