# Chọn một job lớn hay nhiều job nhỏ trong Spring Batch

Khi xây dựng một hệ thống batch, quyết định sớm nhưng ảnh hưởng lâu dài là **gom toàn bộ quy trình vào một `Job` gồm nhiều `Step`**, hay **tách thành các `Job` độc lập rồi điều phối chúng**. Cùng một chuỗi xử lý “đọc đơn hàng → kiểm tra dữ liệu → đối soát → xuất báo cáo” có thể triển khai theo cả hai cách, nhưng hành vi **restart, theo dõi tiến độ, triển khai, xử lý lỗi và tính độc lập nghiệp vụ** sẽ khác nhau đáng kể.

Trong *Spring Batch Core Processing*, một `Job` là đơn vị công việc có danh tính riêng (`JobInstance`), tham số chạy (`JobParameters`), lịch sử thực thi (`JobExecution`) và trạng thái kết thúc. Một `Step` là giai đoạn xử lý nằm bên trong job, có lịch sử `StepExecution` và checkpoint riêng. Vì thế, câu hỏi “một job lớn hay nhiều job nhỏ” thực chất là **chọn ranh giới vận hành và ranh giới phục hồi**.

Bài học này trình bày tiêu chí lựa chọn, ví dụ cấu hình Spring Batch 5.2.x, cách đặt job parameters, chiến lược orchestration, failure recovery, và các trường hợp cần cân nhắc mô hình lai. Không có quy tắc “càng nhiều job càng tốt” hay “một job sẽ luôn nhanh hơn”; thiết kế đúng là thiết kế phản ánh **đơn vị nghiệp vụ, mức phụ thuộc và cách hệ thống phải phục hồi**.

## 1. Phân biệt ranh giới Job, Step và Chunk

Spring Batch có ba cấp độ cần tách biệt:

| Cấp độ | Định danh/trạng thái | Mục đích chính | Khả năng phục hồi |
| --- | --- | --- | --- |
| **`Job`** | Tên job, `JobParameters` định danh `JobInstance`; `JobExecution` có trạng thái | Đại diện một công việc nghiệp vụ có thể khởi chạy/quản trị | Restart `JobInstance` khi metadata và job cho phép |
| **`Step`** | Tên step; mỗi lần chạy có `StepExecution` | Một giai đoạn xử lý trong job | Có thể bỏ qua step đã `COMPLETED` và chạy tiếp step chưa xong theo quy tắc restart |
| **`Chunk`** | Ranh giới commit trong chunk-oriented step | Nhóm các item để đọc, xử lý, ghi và commit | Checkpoint reader/writer được lưu theo transaction, giúp tiếp tục sau chunk đã commit |

Ví dụ một job gồm ba step:

```text
Job: dailyOrders
  |
  +-- Step: loadOrders         [chunk size 500]
  |      +-- read -> process -> write -> commit
  |      +-- read -> process -> write -> commit
  |
  +-- Step: validateOrders     [tasklet hoặc chunk]
  |
  +-- Step: publishSummary     [tasklet]
```

Một `Job` lớn **không đồng nghĩa một transaction lớn**. Trong Spring Batch, mỗi chunk/step có cơ chế transaction riêng tùy cấu hình. Nếu `publishSummary` thất bại sau khi `loadOrders` đã commit dữ liệu, Spring Batch **không tự rollback toàn bộ dữ liệu của các step trước**. Điều mà một job nhiều step mang lại là **một dòng điều khiển và một lịch sử restart thống nhất**, không phải tính nguyên tử end-to-end.

Ngược lại, nếu tách thành ba job, mỗi job có `JobInstance` và `JobExecution` riêng. Framework không tự suy ra chúng thuộc cùng kỳ xử lý hoặc phải chạy theo thứ tự; ta phải bổ sung orchestration và correlation.

## 2. Hai mô hình kiến trúc cơ bản

### Mô hình A — Một job gồm nhiều step

```text
Trigger: 02:00 / businessDate=2026-11-15
                |
                v
        Job dailyOrders
                |
         +------+-------+
         |              |
         v              |
    loadOrders          |
         |              |
         v              |
   validateOrders       |
         |              |
         v              |
   publishSummary       |
         |              |
         v              |
    Job COMPLETED <-----+
```

Ưu điểm: một trigger, một tên job, một bộ identifying parameters, một `JobExecution` đại diện cho lần thử chạy và flow `Step` được Spring Batch quản lý. Khi step giữa thất bại, restart cùng `JobInstance` có thể tiếp tục từ đúng step/checkpoint nếu cấu hình đúng.

Hạn chế: các giai đoạn bị ràng buộc vào một vòng đời job, khó lên lịch hay cấp quyền độc lập. Nếu step cuối tạo báo cáo tùy chọn nhưng thất bại, cả `JobExecution` có thể không đạt `COMPLETED`, dù các bước nhập liệu bắt buộc đã thành công. Việc tách deploy/code owner khó hơn nếu tất cả bước nằm trong cùng ứng dụng.

### Mô hình B — Nhiều job độc lập, có orchestration

```text
             Scheduler / Workflow Orchestrator
                          |
                          v
                 Job importOrders
                          |
                 COMPLETED cho kỳ X?
                     /         \
                   No           Yes
                   |             |
                Alert/stop       v
                           Job validateOrders
                                 |
                            COMPLETED?
                             /     \
                           No       Yes
                           |         |
                        Alert        v
                               Job publishSummary
                                     |
                                COMPLETED?
                                     |
                               Finish workflow
```

Ưu điểm: từng job có lịch chạy, SLA, permission, retry/restart và vòng đời triển khai riêng. Job thứ hai có thể được tái sử dụng trong một workflow khác; một job báo cáo tùy chọn có thể có chính sách thất bại riêng.

Hạn chế: cần **bộ điều phối bền vững** để giữ quan hệ phụ thuộc, ghi nhận trạng thái workflow và xử lý kích hoạt trùng. Không thể chỉ gọi `JobLauncher.run(jobA)` rồi `run(jobB)` trong mọi trường hợp, vì `JobLauncher` có thể được cấu hình bất đồng bộ và trả về trước khi A hoàn thành. Trạng thái của từng `JobInstance` riêng cũng không tạo nên trạng thái workflow chung một cách tự động.

### Mô hình C — Kết hợp

Một hệ thống thực tế thường dùng nhiều **job có quy mô vừa**, mỗi job gồm một số step có quan hệ chặt, rồi để scheduler/điều phối workflow quản lý phụ thuộc ở cấp job.

```text
Workflow: daily-finance
  |
  +-- Job A: importOrders
  |     +-- fetch
  |     +-- normalize
  |     +-- writeStaging
  |
  +-- Job B: reconcilePayments
  |     +-- matchTransactions
  |     +-- verifyTotals
  |
  +-- Job C: publishFinancialReport
        +-- aggregate
        +-- render
        +-- deliver
```

Đây là cách cân bằng khi có nhiều đơn vị nghiệp vụ/schedule khác nhau nhưng bên trong mỗi đơn vị vẫn cần checkpoint và restart theo step.

## 3. Các tiêu chí quyết định quan trọng

| Tiêu chí | Nghiêng về **một job nhiều step** | Nghiêng về **nhiều job nhỏ** |
| --- | --- | --- |
| **Đơn vị nghiệp vụ** | Các bước hợp thành một kết quả nghiệp vụ không nên tách rời về trạng thái hoàn tất | Mỗi phần có kết quả nghiệp vụ và tiêu chí hoàn tất riêng |
| **Lịch chạy** | Cùng trigger, cùng kỳ, cùng deadline | Chạy vào giờ khác nhau, on-demand hoặc theo sự kiện khác nhau |
| **Phụ thuộc** | Tuyến tính, phụ thuộc chặt, bước sau chỉ có nghĩa nếu bước trước hoàn tất | Phụ thuộc yếu hoặc có thể mô tả bằng DAG/orchestrator |
| **Restart** | Muốn restart một `JobInstance` và để Batch chọn các step cần chạy lại | Muốn restart từng phần độc lập mà không đụng những phần khác |
| **Dữ liệu trung gian** | Nhỏ hoặc có thể tham chiếu qua `ExecutionContext`/staging nội bộ | Đầu ra có hợp đồng bền vững để job khác đọc |
| **SLA** | Một deadline áp cho toàn bộ quy trình | SLA, cảnh báo và mức ưu tiên riêng cho từng phần |
| **Ownership** | Cùng nhóm chịu trách nhiệm, release cùng nhịp | Nhiều nhóm, codebase, quyền truy cập hoặc deployment riêng |
| **Tài nguyên** | Các bước dùng cấu hình tương đồng, có thể tối ưu chung | Khác hạ tầng, cần scale/cô lập CPU, RAM, connection pool |
| **Độ dài/chạy đồng thời** | Các bước tuần tự với tiến độ gắn kết | Có bước chạy hàng giờ, bước cần realtime, hoặc nhiều workflow dùng lại |
| **Tính độc lập tái xử lý** | Nếu phần nào hỏng thì nên phục hồi trong ngữ cảnh toàn bộ kỳ | Cần rerun báo cáo/đối soát mà không đọc lại nguồn |
| **Quan sát vận hành** | Một `JobExecution` tổng thể là ý nghĩa đúng | Mỗi đơn vị cần history, dashboard và alert riêng |
| **Độ phức tạp hạ tầng** | Muốn dựa nhiều vào orchestration sẵn có của Spring Batch | Đã có scheduler/workflow engine đủ tin cậy |

**Câu hỏi phân định hữu ích nhất:** Nếu bước cuối thất bại, người vận hành có muốn nói “**cả công việc chưa hoàn tất**” và restart cùng một đối tượng công việc, hay muốn nói “**nhập liệu đã hoàn tất; chỉ báo cáo chưa xong**”? Câu trả lời thường chỉ ra ranh giới job hợp lý hơn kích thước source code.

Không dùng **số lượng step** làm tiêu chí duy nhất. Một job gồm 15 step ngắn có thể rất dễ vận hành; một job chỉ có một step đọc API không thể replay lại có thể khó phục hồi hơn nhiều.

## 4. Ví dụ: một job lớn với nhiều step

Giả sử đơn vị nghiệp vụ là “xử lý đơn hàng cho một ngày”. Yêu cầu: phải lấy dữ liệu, kiểm tra chất lượng và ghi kết quả tổng hợp; nếu bước kiểm tra thất bại thì không được công bố báo cáo.

Có thể tạo một `Job` với flow tuần tự:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailyOrdersJobConfig {

    @Bean
    public Job dailyOrdersJob(
            JobRepository jobRepository,
            @Qualifier("loadOrdersStep") Step loadOrders,
            @Qualifier("validateOrdersStep") Step validateOrders,
            @Qualifier("publishSummaryStep") Step publishSummary) {

        return new JobBuilder("dailyOrders", jobRepository)
                .start(loadOrders)
                .next(validateOrders)
                .next(publishSummary)
                .build();
    }
}
```

Đây là **cấu hình Job Spring Batch 5.x**; ba bean `Step` phải được định nghĩa trong application context với `JobRepository`, transaction manager, reader/processor/writer hoặc tasklet thực tế. `.next(...)` thiết lập thứ tự khi flow tiếp tục bình thường. Khi step thất bại, Spring Batch xử lý kết thúc flow/restart theo trạng thái và cấu hình tương ứng, chứ không mặc nhiên chạy step tiếp theo.

### Ý nghĩa của một `JobInstance`

Ví dụ chạy theo `businessDate`:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceVersion", "orders-v3", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Ở Spring Batch 5.2, `true` đánh dấu identifying parameter. `JobInstance` được xác định bởi tên job và identifying values; `requestedBy` được đặt non-identifying để ghi thông tin điều phối mà không đổi danh tính nghiệp vụ.

Trong một job nhiều step, những step có thể cùng sử dụng `businessDate`, `sourceVersion` từ `JobParameters`. Các bean `@StepScope` có thể lấy giá trị này tại runtime. Nếu job thất bại ở `validateOrdersStep`, lần restart cùng identifying parameters sẽ xử lý theo metadata step đã lưu, **không phải bắt đầu một JobInstance mới**.

### Lưu dữ liệu trung gian ở đâu?

Một sai lầm thường gặp là coi `ExecutionContext` như nơi chứa toàn bộ dữ liệu giữa các step. Nó phù hợp cho **checkpoint và metadata nhỏ**, ví dụ ID file staging, ngày nghiệp vụ, offset hoặc khóa lô xử lý. Không nên đặt hàng triệu `Order` hay một DataFrame lớn vào context vì serializer, database metadata và thao tác restart sẽ rất nặng.

Với dữ liệu trung gian lớn:

```text
loadOrdersStep
   -> ghi staging_orders(batch_id, order_id, ...)
   -> ExecutionContext chỉ lưu batch_id / staging location

validateOrdersStep
   -> đọc staging theo batch_id

publishSummaryStep
   -> đọc kết quả đã kiểm chứng và công bố
```

Cần thiết kế staging data có khóa/phiên bản nhất quán và cleanup rõ ràng. Dữ liệu trung gian bền vững giúp restart không phải dựa vào một object trong RAM; nó cũng khiến việc **tách job về sau** khả thi hơn.

## 5. Ví dụ: tách thành nhiều job và điều phối

Nếu bước nhập đơn hàng chạy lúc 02:00, đối soát thanh toán lúc 05:00, còn báo cáo có thể chạy lại riêng khi định dạng thay đổi, nên cân nhắc ba `Job` độc lập.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersWorkflowJobsConfig {

    @Bean
    public Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {
        return new JobBuilder("importOrders", repository)
                .start(step)
                .build();
    }

    @Bean
    public Job reconcilePaymentsJob(
            JobRepository repository,
            @Qualifier("reconcilePaymentsStep") Step step) {
        return new JobBuilder("reconcilePayments", repository)
                .start(step)
                .build();
    }

    @Bean
    public Job publishReportJob(
            JobRepository repository,
            @Qualifier("publishReportStep") Step step) {
        return new JobBuilder("publishReport", repository)
                .start(step)
                .build();
    }
}
```

Cấu hình này **chỉ khai báo ba job**, không tự nối chúng thành workflow. Các `Step` tương ứng cần được cung cấp. Scheduler hoặc orchestrator chịu trách nhiệm chạy job đúng thời điểm và chỉ kích hoạt bước phụ thuộc sau khi xác nhận điều kiện thành công.

Ví dụ logic orchestration:

```text
workflowKey = (businessDate=2026-11-15, tenant=VN)

1. Start importOrders với key của kỳ xử lý.
2. Chờ execution terminal; kiểm tra status là COMPLETED,
   và các quality gates (số dòng/skip/đối soát) được đáp ứng.
3. Ghi nhận output version/staging dataset của importOrders.
4. Start reconcilePayments trên đúng output version.
5. Sau khi reconcilePayments hoàn tất, cho phép publishReport.
6. Nếu publishReport FAILED, chỉ restart publishReport
   theo quy tắc riêng; không tự chạy lại importOrders.
```

Điểm cần nhớ: một `JobExecution` trả về từ `JobLauncher.run(...)` **không nhất thiết đã kết thúc** nếu `JobLauncher` dùng executor bất đồng bộ. Bộ điều phối phải chờ trạng thái terminal dựa trên API/event/hạ tầng của mình; không khởi chạy job tiếp theo ngay chỉ vì lời gọi `run` đã trả về.

### Các JobParameters không tự liên kết giữa job

Với ba job độc lập:

```text
JobInstance(importOrders, businessDate=2026-11-15, ...)
JobInstance(reconcilePayments, businessDate=2026-11-15, ...)
JobInstance(publishReport, businessDate=2026-11-15, ...)
```

Chúng có **ba định danh job riêng**, dù cùng `businessDate`. Spring Batch không tự biết `reconcilePayments` phụ thuộc kết quả của execution import nào. Orchestrator cần lưu các liên kết, ví dụ:

| Trường workflow | Mục đích |
| --- | --- |
| `workflowId` hoặc `workflowKey` | Nhận diện quá trình tổng thể |
| `businessDate` / `tenant` | Nhận diện kỳ nghiệp vụ |
| `importJobExecutionId` | Chỉ ra lần nhập liệu được chấp nhận |
| `importOutputVersion` | Chỉ ra dataset đầu vào bất biến của job đối soát |
| `reconcileJobExecutionId` | Lần đối soát đã xác minh |
| `reportJobExecutionId` | Lần phát hành báo cáo |
| `workflowStatus` | Kết quả cuối ở cấp orchestration |

Một workflow status là **dữ liệu của orchestrator**, không phải `BatchStatus` có sẵn cho nhiều job. Nên lưu bền vững trạng thái này nếu cần recover sau khi chính orchestrator crash.

## 6. Restart và failure recovery quyết định ranh giới

Tính chất phục hồi là một trong những lý do mạnh nhất để chọn mô hình.

### Một job nhiều step

```text
Job dailyOrders / JobInstance cho ngày X
  loadOrders       COMPLETED
  validateOrders   FAILED
  publishSummary   NOT_STARTED

Restart cùng JobInstance:
  loadOrders       thường được bỏ qua
  validateOrders   chạy lại từ checkpoint/đầu step tùy thiết kế
  publishSummary   chạy sau khi validate thành công
```

Spring Batch sử dụng metadata trong `JobRepository` để biết các step đã hoàn tất. Step từng `COMPLETED` thường không chạy lại khi restart trừ khi cấu hình `allowStartIfComplete(true)`. Step đang dở được khôi phục theo `ExecutionContext` nếu reader/writer hỗ trợ và dữ liệu nguồn ổn định.

**Giới hạn:** một step được đánh dấu `COMPLETED` không có nghĩa mọi side effect nằm ngoài transaction có thể hoàn tác nếu step sau lỗi. Một quy trình cần bù trừ nghiệp vụ phải được thiết kế riêng.

### Nhiều job độc lập

```text
importOrders       COMPLETED
reconcilePayments  COMPLETED
publishReport      FAILED

Chỉ restart publishReport với tham số định danh thích hợp.
Hai job trước không tự chạy lại.
```

Ưu điểm là cô lập phạm vi rerun. Nhưng nếu `publishReport` lấy “dữ liệu mới nhất” thay vì **output version cụ thể** của `reconcilePayments`, sau khi restart có thể đọc dataset khác. Khi tách job, **contract dữ liệu liên job** phải có phiên bản và định danh được ghi bền vững.

### Nếu job A thất bại sau khi đã ghi dữ liệu?

Tách nhỏ **không tự xử lý** trường hợp A commit một phần dữ liệu rồi `FAILED`. Job B chỉ nên được kích hoạt khi A đạt điều kiện thành công phù hợp, hoặc khi đã có một hợp đồng rõ cho phép xử lý kết quả từng phần. Đừng coi mỗi batch job có tính nguyên tử nghiệp vụ chỉ vì nó là một đơn vị trên scheduler.

| Sự cố | Một job nhiều step | Nhiều job |
| --- | --- | --- |
| Step giữa lỗi | Restart job có thể dùng metadata step để tiếp tục | Restart job chứa giai đoạn đó; orchestrator quản lý dependency |
| Bước báo cáo cuối lỗi | Có thể khiến job tổng thể `FAILED` | Job báo cáo `FAILED`, job nhập liệu vẫn `COMPLETED` |
| Cần chạy lại mỗi báo cáo | Có thể cần thiết kế `allowStartIfComplete` hoặc job riêng | Chạy/restart job báo cáo độc lập |
| Input bị đổi sau failure | Có thể làm checkpoint reader không còn hợp lệ | Có thể làm job sau đọc sai version dữ liệu |
| Scheduler/orchestrator bị crash | Flow trong một `JobExecution` nằm trong metadata Batch | Cần phục hồi workflow state ngoài các `JobExecution` |
| Dữ liệu đã ghi vào API ngoài nhưng metadata chưa commit | Cần idempotency/đối soát | Vẫn cần idempotency/đối soát; chia job không giải quyết nguyên tử |

## 7. Transaction và tính nguyên tử end-to-end

Một quan niệm sai nguy hiểm: “Gộp mọi bước vào một job sẽ rollback toàn bộ nếu step cuối thất bại.” Spring Batch **không bảo đảm giao dịch ACID duy nhất xuyên qua mọi step của job**.

Ví dụ:

```text
Step 1: nạp 100.000 đơn hàng vào DB      COMMITTED
Step 2: đối soát giao dịch                COMMITTED
Step 3: gọi API công bố kết quả           FAILED
```

Khi step 3 thất bại, hai step trước có thể đã ghi dữ liệu bền vững. Muốn undo những thay đổi ấy cần quy tắc bù trừ phù hợp, chẳng hạn trạng thái `PENDING`/`PUBLISHED`, release marker, outbox hoặc saga. Điều này đúng cả trong một job và nhiều job.

Một chiến lược phổ biến cho nghiệp vụ phát hành là **staging → validation → publish**:

1. Bước nhập liệu ghi vào staging theo `batchId`.
2. Bước kiểm tra xác nhận số lượng, dữ liệu và quy tắc chất lượng.
3. Bước publish chuyển trạng thái dataset thành `READY`/`PUBLISHED` hoặc phát outbox event, có tính idempotent.
4. Consumer chỉ nhìn thấy dataset đã publish.

Nếu bước 3 lỗi sau khi bước 1–2 hoàn tất, hệ thống có thể retry publish một cách an toàn mà không cần xóa staging. Cơ chế này là **thiết kế dữ liệu và transaction**, không phải tính năng tự động do số lượng job quyết định.

## 8. Tham số và danh tính cần thiết kế từ đầu

Dù một hay nhiều job, `JobParameters` phải phản ánh cách nghiệp vụ định nghĩa **một công việc logic**.

Ví dụ:
 
```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("tenant", "vn", true)
        .addString("inputVersion", "orders-v3", true)
        .addString("correlationId", "daily-finance-2026-11-15", false)
        .toJobParameters();
```

Ở Spring Batch 5.2.x, `addString(name, value, true)` chọn identifying parameter. Với **cùng job name** và identifying parameters, framework nhận diện cùng `JobInstance`. `correlationId` không định danh có thể dùng liên kết log/workflow, nhưng phải chọn giá trị phù hợp với quy tắc vận hành.

Khi tách thành nhiều job, mỗi job có thể cần **bộ identifying parameters khác nhau**:

| Job | Identifying parameters ví dụ | Vì sao |
| --- | --- | --- |
| `importOrders` | `businessDate`, `tenant`, `sourceVersion` | Một kỳ có thể được nạp lại từ phiên bản nguồn mới được quản lý |
| `reconcilePayments` | `businessDate`, `tenant`, `stagingVersion` | Cần biết chính xác dataset được đối soát |
| `publishReport` | `businessDate`, `tenant`, `reportVersion` | Có thể xuất lại một phiên bản báo cáo mà không chạy nhập liệu |

Đừng đưa `jobExecutionId` của A vào identifying parameters của B một cách mặc định. Nếu A restart tạo execution mới nhưng vẫn cùng output logic, có thể vô tình tạo một `JobInstance` B mới và chạy trùng. Nếu B **thật sự** cần chạy một lần cho mỗi output version được A công bố, hãy dùng **định danh output bền vững**, không dùng ID execution chỉ phản ánh một lần thử chạy.

### Đổi tên Job khi tách mô hình

Tên job là một phần của `JobInstance` identity. Nếu từ `dailyOrders` chuyển thành `importOrders` và `publishReport`, Spring Batch không thể tự chuyển các checkpoint cũ của `dailyOrders` sang hai job mới. Cần kế hoạch chuyển đổi: hoàn tất hoặc xử lý các instance đang dở, lưu lại các ID/contract, lên lịch chuyển giao và kiểm tra những nguồn output đã xử lý.

## 9. Khi nào nên chỉ thêm Step thay vì tạo Job mới?

Không phải mỗi pha xử lý đều cần một job riêng. Nên ưu tiên **step trong cùng job** khi:

- Bước không có ý nghĩa nghiệp vụ nếu chạy đơn độc.
- Bước luôn dùng cùng kỳ, cùng input identity và chỉ phục vụ flow hiện tại.
- Kết quả của bước là dữ liệu trung gian, không có SLA/consumer độc lập.
- Nếu bước lỗi, người vận hành muốn restart **cùng công việc** chứ không tạo workflow khác.
- Không có yêu cầu tách deploy hoặc scale tài nguyên riêng.

Ví dụ `loadCsv → validateRows → writeOrders` trong một pipeline nhập liệu thường hợp lý là ba step của **một job**. Cả ba cùng tạo nên kết quả “orders for businessDate X have been imported”.

Ngược lại, “công bố báo cáo phân tích cho khách hàng” có thể là một job riêng nếu cần lịch theo giờ, version mẫu báo cáo độc lập, quyền vận hành riêng và khả năng xuất lại mà không nạp CSV.

### `Flow` và điều kiện trong một job

Nếu một job có nhiều nhánh, Spring Batch cung cấp flow transition, `JobExecutionDecider` và khả năng tách flow chạy song song trong những cấu hình phù hợp. Không bắt buộc tạo job mới chỉ vì có nhánh “nếu số bản ghi lỗi vượt ngưỡng thì chuyển sang bước quarantine”.

Một flow trong cùng job vẫn gắn với lifecycle của job; **flow không thay đổi bản chất của `JobInstance` identity** và không biến các step đã commit thành một transaction toàn cục.

### `JobStep` có thay thế orchestrator không?

Spring Batch cho phép mô hình một job được dùng như step của job cha thông qua `JobStep` và thành phần builder tương ứng. Cách này có thể hữu ích khi muốn tái sử dụng job con nhưng vẫn biểu diễn thứ tự dưới một parent job trong cùng hệ thống.

Tuy nhiên, nó tạo thêm lớp identity, job parameters và restart semantics giữa parent/child. Nếu nhu cầu chỉ là ba bước rất chặt, ba `Step` thường dễ hiểu hơn. Nếu nhu cầu là độc lập deploy, SLA và trigger theo hệ thống ngoài, parent `JobStep` không thay thế được toàn bộ workflow orchestration phân tán.

## 10. Lập lịch, tính phụ thuộc và độ tin cậy orchestration

Tách thành nhiều job chỉ thành công khi phụ thuộc giữa các job được điều phối bền vững. Lựa chọn có thể là Spring scheduler, Quartz, Kubernetes CronJob phối hợp với orchestrator, hoặc workflow engine như Airflow/Argo và các hệ thống tương tự theo hạ tầng của tổ chức.

Cần trả lời ít nhất sáu câu hỏi:

1. **Trigger:** điều gì tạo job A/B — đồng hồ, sự kiện, request hay dữ liệu sẵn sàng?
2. **Success criterion:** B được chạy sau khi A có `BatchStatus.COMPLETED`, hay còn cần quality gate về record count/skip ratio?
3. **Deduplication:** nếu scheduler phát sự kiện hoàn tất hai lần, làm sao B không chạy trùng?
4. **Recovery:** nếu orchestrator chết sau khi A hoàn tất nhưng trước khi tạo B, ai sẽ phát hiện và tiếp tục?
5. **Dependency data:** B đọc chính xác phiên bản output nào của A?
6. **Backfill:** khi cần xử lý lại ngày X trong lúc ngày Y đang chạy, làm sao tách hai workflow?

Một **DAG** đơn giản là:
 
```text
importOrders(X) ──> reconcile(X) ──> publish(X)
                        ^
                        |
              exchangeRates(X)
```

Nhìn vào DAG này, `reconcile(X)` có hai input và có thể bắt đầu khi cả hai nguồn đã hoàn thành, thay vì bị trói vào một job cố định chỉ đọc một kết quả. Tình huống phụ thuộc nhiều nguồn/nhóm thường là tín hiệu mạnh để dùng **nhiều job + orchestrator**.

Đồng thời, orchestration không nên tự tăng `run.id` của job sau mỗi lần hệ thống nhận lại sự kiện. Nó cần hợp đồng về `JobInstance`, version đầu vào và restart để tránh xử lý trùng.

## 11. Hiệu năng: không nên chọn theo kích thước Job đơn thuần

Một job có mười step không mặc nhiên chậm hơn mười job một step, và tách job không tự tăng throughput.

Các yếu tố hiệu năng thực sự thường là:

- Reader lấy dữ liệu theo cursor/paging/streaming hay tải hết vào RAM.
- `chunkSize`, số commit và cost của transaction.
- Throughput của writer, batch insert, network, API rate limits.
- CPU của processor và khả năng scale/partition.
- Connection pool, lock contention và database isolation.
- Overhead khởi tạo context, job execution metadata và scheduler.
- Lượng dữ liệu trung gian phải ghi rồi đọc lại giữa các bước.

### Khi cần chạy song song

Trong **một job**, có thể cân nhắc `split` flow, `partitioning` hoặc các cơ chế parallelism của Spring Batch khi semantics cho phép. Một job đơn không có nghĩa tất cả work buộc chạy tuần tự.

Với **nhiều job**, có thể scale/deploy riêng từng job, ví dụ nhập dữ liệu trên worker có băng thông cao, đối soát trên worker CPU mạnh và xuất báo cáo trên worker có tài nguyên phù hợp. Nhưng tăng job đồng thời cũng có thể gây tranh chấp database và message broker.

| Nút thắt | Giải pháp nên xem trước khi tách Job |
| --- | --- |
| Một step xử lý 10 triệu record chậm | Tối ưu reader/writer, chunk, paging, partitioning |
| Các bước tuần tự đang chờ I/O | Điều chỉnh pipeline, async hoặc flow song song khi hợp lệ |
| Một job cần tài nguyên khác hẳn job còn lại | Xem xét job/deployment riêng để scale độc lập |
| Nhiều job cùng ghi một bảng bị lock | Điều phối concurrency, partition keys, transaction/isolation |
| Startup metadata/context quá tốn kém | Kiểm tra overhead khi tách job thành nhiều process và lịch chạy |

Không dùng “số lượng job” như thông số tối ưu hiệu năng chính. Đo duration và throughput **theo step**, đọc `readCount`/`writeCount`/`rollbackCount`, rồi mới đánh giá kiến trúc.

## 12. Failure isolation, SLA và quyền vận hành

Tách job có thể tạo ranh giới điều khiển và giám sát tốt hơn, nhưng cũng tăng số thực thể và quy tắc cần quản lý.

Ví dụ ba chức năng có chính sách rất khác:

| Chức năng | SLA | Phản ứng khi lỗi | Ranh giới gợi ý |
| --- | --- | --- | --- |
| Nhập dữ liệu ngày | Trước 04:00 | Dừng công bố downstream, kiểm tra input và restart | Một job nhập liệu có nhiều step |
| Đối soát giao dịch | Trước 07:00 | Cảnh báo mức cao; có thể chạy lại theo kỳ | Job đối soát độc lập |
| Gửi báo cáo email | Trước 09:00, có thể retry riêng | Không được nhập lại dữ liệu chỉ vì email lỗi | Job phát hành độc lập hoặc tác vụ delivery idempotent |

Nếu gộp tất cả vào `dailyFinance`, một sự cố SMTP lúc 08:55 có thể làm toàn bộ job bị đánh dấu `FAILED`, khiến dashboard khó phân biệt “dữ liệu đã đối soát xong” với “email chưa gửi”. Tách delivery là hợp lý **nếu** nghiệp vụ công nhận đối soát hoàn tất độc lập với gửi email.

Tuy nhiên, nếu báo cáo phải được phát hành như một phần không thể tách rời của SLA nghiệp vụ thì vẫn cần **workflow-level success criterion**: dù có tách job, toàn bộ kỳ chưa đạt SLA đến khi publish thành công. Độc lập trạng thái kỹ thuật không được thay thế định nghĩa thành công của nghiệp vụ.

### Ranh giới quyền và thay đổi

Nhiều job là lựa chọn có giá trị khi:
 
- Nhóm A được phép restart import nhưng không được chạy lại settlement.
- Nhóm B phát hành report theo mẫu mới mà không redeploy import pipeline.
- Từng job có ngân sách tài nguyên, retention/logging và chính sách cảnh báo riêng.
- Hạ tầng scheduler hỗ trợ phê duyệt backfill riêng cho từng công việc.

Một job lớn với nhiều step vẫn có thể có quyền log/metadata theo step, nhưng tác vụ vận hành cấp job thường khó cấp quyền chi tiết theo từng giai đoạn hơn.

## 13. Giám sát khi có nhiều ranh giới job

Trong một job nhiều step, `JobExplorer` có thể trả một `JobExecution` cùng các `StepExecution` của lần chạy ấy; dashboard trình bày quan hệ cha-con tương đối trực tiếp.

Với nhiều job, hệ thống cần **correlation xuyên job**:

```text
workflowId: daily-finance:2026-11-15:VN
  |
  +-- importOrders JobExecution 801     COMPLETED
  +-- reconcilePayments JobExecution 815 COMPLETED
  +-- publishReport JobExecution 902    FAILED
  +-- publishReport JobExecution 911    COMPLETED (restart)
```

Không nên tính “workflow hoàn tất” bằng cách tìm **jobName hiện diện trong registry**; `JobRegistry` chỉ giúp tìm định nghĩa job đang đăng ký. Lịch sử chạy nằm ở `JobRepository`, có thể đọc qua `JobExplorer`. Một job **đáng lẽ chạy nhưng chưa có execution** còn cần đối chiếu với lịch dự kiến từ scheduler/orchestrator.

Các KPI có ích:

| Góc nhìn | KPI | Nguồn |
| --- | --- | --- |
| Job | `BatchStatus`, `ExitStatus`, duration, số lần restart | `JobExecution`/`JobExplorer` |
| Step | read/write/filter/skip, commit/rollback, duration | `StepExecution` |
| Workflow | trạng thái tổng thể, phần phụ thuộc đang chờ, end-to-end latency, SLA | Orchestrator + các execution IDs |
| Chất lượng | số bản ghi hợp lệ, số bị loại, tỷ lệ skip, đối soát số lượng | Metadata Batch + business validation |
| Hiệu năng | step/job latency, throughput, thời gian DB/API | Micrometer, logs/traces và ứng dụng |

Nếu tách job thành nhiều phần, dashboard phải hỗ trợ phân biệt **job A completed** với **workflow overall completed**, không đánh mất sự cố downstream.

## 14. Mô hình ra quyết định từng bước

Có thể dùng cây quyết định sau cho một nhóm bước dự kiến cùng workflow:

```text
Các bước có cùng một kết quả nghiệp vụ bắt buộc?
  |
  +-- Không --> Cân nhắc nhiều Job với SLA/trigger riêng.
  |
  +-- Có
       |
       v
  Có cần khởi chạy, restart, cấp quyền hoặc triển khai
  độc lập từng nhóm bước không?
       |
       +-- Có --> Tách những nhóm đó thành Job riêng;
       |          định nghĩa output contract và orchestration.
       |
       +-- Không
            |
            v
       Có cần khôi phục theo Step/Chunk và
       tuần tự theo cùng JobParameters không?
            |
            +-- Có --> Một Job gồm nhiều Step là mặc định hợp lý.
            |
            +-- Không --> Xem xét tasklet đơn, flow hoặc thiết kế khác.
```

Tính “mặc định hợp lý” không thay thế việc phân tích dữ liệu trung gian, transaction boundary và nguồn có thể replay hay không.

### Ma trận chấm điểm cho một dự án

Nhóm thiết kế có thể chấm mỗi yếu tố từ 1 đến 5 theo nhu cầu thực tế; dưới đây là **ví dụ minh họa**, không phải công thức framework:

| Yếu tố | Ưu tiên dự án | Nếu ưu tiên cao, thường nghiêng về |
| --- | ---: | --- |
| Restart xuyên các bước như một đơn vị | 5/5 | Một job nhiều step |
| Lịch chạy và SLA độc lập | 2/5 | Nhiều job |
| Deploy và ownership độc lập | 1/5 | Nhiều job |
| Giữ orchestration đơn giản | 5/5 | Một job nhiều step |
| Cần backfill từng khâu mà không rerun toàn bộ | 4/5 | Nhiều job |
| Dữ liệu trung gian có output contract/version riêng | 4/5 | Nhiều job |
| Các bước sử dụng một input bất biến, cùng kỳ | 5/5 | Một job nhiều step |

Nếu nhiều tiêu chí kéo về hai phía khác nhau, giải pháp thường là **nhóm các step chặt chẽ thành các job quy mô vừa**, thay vì chọn tuyệt đối một job bao trùm hoặc một job cho mỗi thao tác nhỏ.

## 15. Ba kịch bản thiết kế cụ thể

### Kịch bản A — Nhập một file CSV, chuẩn hóa và ghi cơ sở dữ liệu

Yêu cầu: mỗi file có một `businessDate`, phải parse, validate, deduplicate và ghi DB. Tất cả bước thuộc cùng giao dịch nghiệp vụ “import file X”.

**Gợi ý:** một `Job` `importCsvOrders` có nhiều step, hoặc một step chunk và một step kiểm tra tổng kết nếu cần. Reader có checkpoint, writer idempotent, dữ liệu lỗi quarantine theo policy. Chỉ tách riêng một job quarantine nếu nó có lịch/quyền/SLA độc lập.

Vì sao: tất cả bước cùng input identity, cùng yêu cầu restart và không có mục đích khởi chạy riêng.

### Kịch bản B — Import đơn hàng, đối soát và gửi báo cáo

Yêu cầu: import chạy đêm, đối soát phải chờ nguồn ngân hàng, báo cáo gửi theo giờ làm việc và có thể xuất lại khi mẫu thay đổi.

**Gợi ý:** ba job độc lập, một workflow điều phối theo `businessDate` và phiên bản output:
 
```text
importOrders(datasetVersion=X)             COMPLETED
                 |
                 +--> reconcile(bankSnapshot=Y) COMPLETED
                               |
                               +--> publishReport(reportVersion=Z)
```

Vì sao: khác trigger, khác nguồn phụ thuộc, SLA và vòng đời thay đổi. Orchestrator phải giữ quan hệ giữa X/Y/Z, đồng thời bảo đảm publish idempotent.

### Kịch bản C — Chạy 50 phân vùng của một phép tính lớn

Yêu cầu: cùng thuật toán xử lý dữ liệu theo vùng hoặc khoảng ID, cần scale và restart từng partition.

**Không nên mặc định tạo 50 job riêng**. Spring Batch hỗ trợ **partitioning**, cho phép cùng một job/step có nhiều `StepExecution` độc lập theo partition, mỗi worker nhận khoảng dữ liệu riêng. Khi đó orchestration ở cấp job vẫn gọn và metadata partition phục vụ điều tra.

Tạo nhiều job có thể phù hợp nếu mỗi vùng là một **đơn vị nghiệp vụ có lịch, quyền và SLA riêng**, nhưng số worker không phải lý do duy nhất để chia job.

## 16. Migrate từ một job lớn sang nhiều job nhỏ

Khi một job trở nên khó bảo trì, nên tách theo **ranh giới nghiệp vụ có output contract**, không tách theo phương pháp Java hay tên class.

Lộ trình gợi ý:

1. **Vẽ lại flow hiện tại:** liệt kê mọi step, đầu vào/đầu ra, checkpoint, side effect, thời lượng và phụ thuộc.
2. **Nhóm theo kết quả độc lập:** xác định khâu nào thật sự có SLA, trigger, ownership hoặc rerun độc lập.
3. **Tạo contract dữ liệu trung gian:** dataset ID, schema version, completeness marker, checksum và khóa nghiệp vụ.
4. **Thiết kế identifying parameters:** business date, tenant và version thích hợp cho từng job mới.
5. **Bổ sung orchestration state:** workflow ID, mapping từ execution IDs đến output versions, cơ chế dedup trigger.
6. **Chuyển lịch và quyền:** xử lý job instance cũ đang `FAILED`/`STARTED`, quyết định restart ở code cũ hay replay có kiểm soát.
7. **Đo song song trong staging:** so sánh data counts, correctness, latency, failure behavior và restart scenarios.
8. **Chuyển production có runbook:** tránh để cả job cũ lẫn job mới cùng ghi một tập dữ liệu không được phân biệt.
9. **Giữ lịch sử:** có mapping từ job/instance cũ sang workflow mới phục vụ audit và điều tra.

**Đừng xóa metadata Batch để làm sạch lịch sử khi tách job.** Tên job mới tạo danh tính mới; cần đối soát dữ liệu đã xử lý và lưu dấu vết để không backfill trùng.

### Khi gộp nhiều job thành một

Quá trình gộp cũng cần xem xét: có thể mất khả năng restart/tái chạy độc lập, yêu cầu refactor `JobParameters` và lịch mới, thay đổi quyền vận hành và làm cho sự cố ở bước cuối kéo cả job về `FAILED`. Nếu các job trước đó có external consumers hoặc output versions độc lập, không nên xóa những hợp đồng ấy chỉ vì chuyển thành step.

## 17. Kiểm thử lựa chọn kiến trúc

Không chỉ test “chạy xanh”, mà phải test **cách thất bại và cách phục hồi** phù hợp ranh giới đã chọn.

| Test | Một job nhiều step | Nhiều job độc lập |
| --- | --- | --- |
| Happy path | Các step hoàn tất đúng thứ tự; job `COMPLETED` | Orchestrator chạy dependency đúng thứ tự |
| Fail ở bước giữa | Job `FAILED`, step sau chưa chạy | Downstream job không được trigger |
| Restart cùng kỳ | Step đã hoàn tất được skip, step lỗi tiếp tục đúng | Restart job lỗi, không tự rerun job trước |
| Fail sau commit dữ liệu | Không có duplicate hoặc mất dữ liệu khi restart | Output version/idempotency bảo đảm downstream an toàn |
| Job/worker chạy song song | State/checkpoint không race | Không trigger hai execution cạnh tranh cùng identity |
| Input bị thay phiên bản | Phát hiện nguồn thay đổi so với checkpoint | Downstream bị chặn nếu output version không còn phù hợp |
| Scheduler mất kết nối | Không tạo `JobInstance` trùng ngoài ý muốn | Workflow state phục hồi được khi orchestrator restart |
| Backfill lịch sử | Không ảnh hưởng kỳ đang chạy | Các job liên quan xử lý đúng tập dữ liệu của kỳ backfill |
| Quality gate không đạt | Flow dừng hoặc chuyển nhánh theo chính sách | Downstream bị chặn dù job upstream có `COMPLETED` kỹ thuật |
| Observability | Tra được toàn bộ `StepExecution` theo job | Tra được toàn bộ execution IDs theo workflow ID |

Đối với Spring Batch 5.2.x, `spring-batch-test` cung cấp `JobLauncherTestUtils`, `JobRepositoryTestUtils` và hỗ trợ scope cho integration tests. Với bài test restart, dùng `JobRepository` test có dữ liệu bền vững qua **hai lần thực thi trong cùng kịch bản**, không dọn metadata giữa lần `FAILED` và lần restart. Chỉ làm sạch repository trước/sau test khi phù hợp để các test độc lập.

### Một assertion điển hình cho job nhiều step

```java
// Pseudocode: các bean job/step, database test và fault injection
// được định nghĩa bởi ứng dụng.
JobExecution first = launcher.run(dailyOrdersJob, fixedParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

disableFailureInValidateStep();

JobExecution second = launcher.run(dailyOrdersJob, fixedParameters);
assertEquals(BatchStatus.COMPLETED, second.getStatus());

// Kiểm tra loadOrders không ghi dữ liệu trùng.
// Kiểm tra publishSummary chỉ chạy khi validate thành công.
// Đối chiếu business IDs đầu ra, không chỉ StepExecution.writeCount.
```

Đây là **pseudocode minh họa**, không phải unit test tự chạy vì thiếu phần hạ tầng và phương thức `disableFailureInValidateStep`. Để thử multi-job, cần thêm kiểm thử orchestration: event upstream hoàn tất bị gửi hai lần thì downstream chỉ tạo một công việc logic; orchestrator crash giữa hai trigger vẫn có thể resume đúng.

## 18. Những lựa chọn sai thường gặp

| Sai lầm | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| “Mỗi class xử lý là một job” | Quá nhiều triggers, params, metadata, quyền và phụ thuộc | Nhóm thành step theo công việc nghiệp vụ |
| “Một job là một transaction duy nhất” | Tưởng bước trước tự rollback khi bước cuối lỗi | Thiết kế transaction/staging/compensation |
| Tách job nhưng không có orchestration bền vững | Job sau chạy sai thứ tự hoặc bị bỏ quên sau crash | Workflow state, dependency và retry/dedup rõ ràng |
| Lấy “job A có `COMPLETED`” là đủ chạy B | Quality gate/đối soát có thể chưa đạt | Tách technical status và business acceptance |
| Dùng dữ liệu “mới nhất” giữa các job | Restart đọc input khác với lần trước | Version hóa output/dataset và truyền định danh rõ |
| Đổi `run.id` để chạy lại thay vì restart | Tạo `JobInstance` mới, nguy cơ duplicate | Giữ identifying parameters khi restart đúng instance |
| Dùng `ExecutionContext` lưu data lớn | Metadata cồng kềnh, serializer lỗi, restart chậm | Staging bền vững và context chỉ chứa reference |
| Bật `allowStartIfComplete(true)` để chữa mọi lỗi | Step hoàn tất bị chạy lại ngoài ý muốn | Chỉ bật khi có yêu cầu và idempotency |
| Tăng số job để tăng tốc | Overhead và tranh chấp tài nguyên có thể tăng | Đo bottleneck, xem partition/chunk trước |
| Dùng một job khổng lồ cho các SLA khác nhau | Khó cảnh báo và rerun từng phần | Tách theo domain, SLA, deploy và quyền |
| Chỉ xem `JobRepository` để xác định missing run | Job chưa trigger sẽ không có metadata | So với lịch chạy kỳ vọng của orchestrator |
| Mỗi job có DB độc lập nhưng không đối soát | Không có giao dịch xuyên job; dữ liệu trung gian thiếu nhất quán | Durable output contracts, idempotency, replay policy |

## 19. Nguyên tắc chốt thiết kế

Khi cần lựa chọn, hãy viết câu định nghĩa hoàn tất của mỗi đơn vị:

> “Đối với `businessDate` X, công việc `importOrders` chỉ hoàn tất khi dữ liệu nguồn được parse, kiểm tra, ghi và đối soát đủ số lượng. Nếu một bước chưa xong, phải restart công việc ấy từ checkpoint an toàn.”

Nếu câu này mô tả chính xác một pipeline liên tục, **một job nhiều step** thường hợp lý.

> “Đối với `businessDate` X, `importOrders` hoàn tất và phát hành dataset version V. `reconcilePayments` dùng V và nguồn ngân hàng; `publishReport` có thể chạy lại độc lập trên kết quả đối soát đã xác nhận.”

Nếu đây mới là cách nghiệp vụ muốn vận hành, **nhiều job có output contract và orchestrator** hợp lý hơn.

Khi chưa có nhu cầu rõ ràng về lịch, quyền, SLA hay triển khai độc lập, **không cần chia job chỉ để tránh một file cấu hình dài**. Khi các bước thật sự độc lập, **không cần ép chúng vào một `JobInstance` chỉ để dashboard có một dòng trạng thái**. Giữ ranh giới theo nhu cầu phục hồi, dữ liệu và vận hành, không theo số lượng lớp Java.

## 20. Tài liệu tham khảo

Các ví dụ trên dùng API **Spring Batch 5.2.x**. Ở Spring Batch 6.x, một số package/API đã đổi; cần dùng tài liệu phù hợp với dependency của dự án khi sao chép cấu hình.

- [Spring Batch Reference 5.2 — Job domain và JobInstance](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch Reference 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html)
- [Spring Batch Reference 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch Reference 5.2 — Configuring Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html)
- [Spring Batch Reference 5.2 — ItemStream và ExecutionContext](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html)
- [Spring Batch Reference 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html)
- [Spring Batch Reference 5.2 — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch Reference 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 API — JobBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/job/builder/JobBuilder.html)
- [Spring Batch 5.2 API — JobExplorer](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)

**Kết luận:** Nên chọn **một `Job` gồm nhiều `Step`** khi các bước cùng tạo một kết quả nghiệp vụ, chạy trong cùng kỳ và cần một cơ chế restart thống nhất. Nên chọn **nhiều `Job`** khi mỗi phần cần trigger, SLA, deploy, quyền vận hành hoặc rerun độc lập; đổi lại phải có orchestration bền vững và hợp đồng dữ liệu liên job rõ ràng. Dù chọn cách nào, tính đúng đắn khi restart vẫn phụ thuộc vào checkpoint, transaction, source version và writer idempotent — chứ không tự đến từ số lượng job.
