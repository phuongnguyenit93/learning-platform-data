# Theo dõi commit count trong Spring Batch

## 1. Vì sao cần theo dõi commit count?

Một Spring Batch Job có thể xử lý hàng triệu bản ghi và chạy trong nhiều phút hoặc nhiều giờ. Khi Job đang ở trạng thái **STARTED**, người vận hành cần biết liệu các Step có thực sự tiến triển, đang chờ I/O, bị lỗi giao dịch hay mắc kẹt. Chỉ nhìn trạng thái Job không đủ để giải thích tiến độ xử lý.

**Commit count** là bộ đếm số transaction commit được Spring Batch ghi nhận trong phạm vi **một StepExecution**. Truy cập bằng phương thức **StepExecution.getCommitCount()**. Với Step xử lý theo chunk, bộ đếm này thường tăng khi các vòng xử lý chunk được commit thành công. Nó rất hữu ích để quan sát checkpoint, nhịp transaction và sự khác biệt giữa một Step đang xử lý bình thường với một Step không tiến triển.

Ví dụ dashboard hiển thị:

~~~text
Job         : importOrdersJob
Step        : importOrdersStep
Status      : STARTED
Read count  : 12 500
Write count : 12 400
Filter count:    100
Commit count:     25
Rollback   :      0
~~~

Các con số minh họa trên cho thấy Step đã đọc và ghi dữ liệu, và có transaction được commit. Tuy nhiên, **commitCount = 25 không có nghĩa Step ghi đúng 25 item**, cũng không chứng minh hệ thống đích đã có đủ 12.400 bản ghi đúng nghiệp vụ. Commit count là một **chỉ số vận hành**, cần được đặt cạnh read/write/skip count, trạng thái Step, thời gian và kết quả thực tế.

Sau bài này, bạn có thể:

- Giải thích **commitCount** và phân biệt nó với **writeCount**, **rollbackCount**.
- Đọc commit count qua **StepExecution**, **JobExplorer** và bảng metadata.
- Log tiến độ theo chunk, phát ra metric với **Micrometer** và thiết kế dashboard.
- Nhận biết những giới hạn khi Step có retry, rollback, tasklet, restart hoặc partition.
- Thiết kế test và cảnh báo theo hành vi thực tế, không dựa vào công thức sai.

## 2. Commit count thuộc về StepExecution nào?

Spring Batch có ba khái niệm liên quan:

~~~text
JobInstance
  |
  +-- JobExecution #1
  |      |
  |      +-- StepExecution #101
  |              readCount, writeCount, commitCount, rollbackCount...
  |
  +-- JobExecution #2 (restart)
         |
         +-- StepExecution #102
                 readCount, writeCount, commitCount, rollbackCount...
~~~

**JobInstance** được nhận diện bằng tên Job và các identifying JobParameters. **JobExecution** là một lần cố gắng chạy Job đó. **StepExecution** ghi nhận một lần thực thi Step cụ thể.

Một Step chạy lại sau failure thường nhận một StepExecution mới. Do đó:

- Commit count của StepExecution #101 cho biết số commit được ghi nhận ở lần thực thi #101.
- Commit count của StepExecution #102 cho biết số commit của lần restart tương ứng.
- Không xem count của StepExecution gần nhất là tổng count của toàn bộ JobInstance.
- Khi cần đối soát số item nghiệp vụ đã hoàn tất qua nhiều lần restart, nên kiểm tra dữ liệu đầu ra và checkpoint thay vì chỉ cộng commit count.

Spring Batch cung cấp các phương thức:

~~~java
StepExecution step = ...;

int commits = step.getCommitCount();
int rollbacks = step.getRollbackCount();
long reads = step.getReadCount();
long writes = step.getWriteCount();

BatchStatus status = step.getStatus();
ExitStatus exit = step.getExitStatus();
~~~

Các count nên theo dõi cùng nhau:

| Thuộc tính | Ý nghĩa | Vai trò giám sát |
| --- | --- | --- |
| **getCommitCount()** | Số transaction commit Step ghi nhận | Quan sát nhịp commit/checkpoint |
| **getRollbackCount()** | Số rollback Step ghi nhận | Phát hiện giao dịch bị hủy, retry và lỗi |
| **getReadCount()** | Số item đọc thành công | Đo tiến độ đọc input |
| **getWriteCount()** | Số item được Step tính là đã ghi | Đo khối lượng output |
| **getFilterCount()** | Số item bị lọc do processor trả về null | Phân biệt lọc nghiệp vụ với lỗi |
| **getSkipCount()** | Tổng số item/lỗi được skip | Quan sát dữ liệu lỗi được chấp nhận bỏ qua |
| **getStatus()** | STARTING, STARTED, COMPLETED, FAILED,... | Xác định tình trạng thực thi |
| **getExitStatus()** | Kết quả kết thúc Step, có thể được ứng dụng tùy chỉnh | Xác định kết quả logic của Step |

Không nên tạo một biểu đồ commit count mà không thể truy ngược **job name**, **step name**, **JobExecution ID** và **StepExecution ID**. Hai StepExecution của cùng Step có thể có count khác nhau vì thuộc các lần chạy khác nhau.

## 3. Commit count phát sinh khi nào?

Xét Step xử lý **chunk size = 4**:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(4, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Một vòng xử lý chunk thông thường:

~~~text
      BẮT ĐẦU TRANSACTION
               |
         ItemReader
               |
        ItemProcessor
               |
         ItemWriter
               |
       Cập nhật checkpoint,
       trạng thái và metadata
               |
             COMMIT
               |
      Tiếp tục chunk tiếp theo
~~~

Trong mô hình này, mỗi chunk được xử lý và commit thành công đóng góp vào tiến độ transaction của Step. Metadata Step và **ExecutionContext** được cập nhật theo cơ chế checkpoint của framework.

**Chunk size không phải commit count.** Chunk size giới hạn số item được gom trong một vòng xử lý; commit count theo dõi transaction commit mà Step ghi nhận. Để hiểu sự khác biệt, hãy xét mười item:

~~~text
Input: 1 2 3 4 5 6 7 8 9 10
Chunk size: 4

Chunk dữ liệu 1: 1 2 3 4  -> commit
Chunk dữ liệu 2: 5 6 7 8  -> commit
Chunk dữ liệu 3: 9 10     -> commit
Kết thúc reader / EOF
~~~

Ta có thể mô tả **ba nhóm dữ liệu** đã xử lý, nhưng không được mặc định mọi Step trong mọi phiên bản sẽ có **getCommitCount() == 3**. Framework có thể thực hiện một vòng cuối để xác nhận hết input; các loại Step và reader khác nhau cũng có lifecycle transaction khác nhau.

Công thức:

~~~text
ceil(numberOfItems / chunkSize)
~~~

là phép ước lượng **số chunk chứa dữ liệu** trong tình huống đơn giản, **không phải hợp đồng luôn đúng của commitCount**. Khi kiểm thử hoặc cảnh báo, nên dựa vào hành vi của Step thực tế, không suy diễn cứng từ số item.

### Một Step có thể commit mà không ghi item

Ví dụ processor lọc toàn bộ item bằng cách trả về null. **writeCount** có thể bằng 0 nhưng Step vẫn đi qua transaction và checkpoint. Tasklet Step có thể thực hiện lệnh cập nhật, kiểm tra hoặc thao tác hệ thống mà không dùng ItemReader/ItemWriter, trong khi transaction vẫn được commit.

Vì vậy, **commitCount > 0 không đồng nghĩa writeCount > 0**.

### Một Step có thể đọc item nhưng chưa commit

Nếu processor xử lý chậm hoặc writer bị chờ lock database, reader có thể đã tiếp cận nhiều item nhưng transaction chunk hiện tại chưa commit. Nếu lỗi xảy ra và transaction rollback, các thao tác thuộc chunk chưa commit có thể cần được xử lý lại sau retry hoặc restart.

Vì vậy, **readCount tăng hoặc các phương thức đã được gọi không đồng nghĩa mọi item đã được commit**.

## 4. Đọc commit count cùng rollback, retry và skip

Khi một chunk gặp exception, Spring Batch có thể rollback transaction. Nếu cấu hình retry, Step có thể thử lại cùng item/chunk; nếu cấu hình skip, nó có thể bỏ qua item lỗi để tiếp tục. Các sự kiện này có thể làm cho những bộ đếm biến động khác nhau.

| Hiện tượng | Khả năng xảy ra | Cần xem thêm |
| --- | --- | --- |
| Commit tăng, rollback không tăng | Các transaction đang commit bình thường | Tốc độ read/write, thời lượng chunk |
| Commit và rollback đều tăng | Có lỗi được retry hoặc xử lý thành công sau rollback | Loại exception, retry policy, skip count |
| Read tăng nhưng commit chưa đổi | Đang xử lý chunk lớn hoặc writer bị chậm | Log, trạng thái database, thời gian chờ |
| Rollback tăng nhanh nhưng commit ít | Có vấn đề transaction, dữ liệu hoặc đích ghi | Constraint, deadlock, timeout, failure exceptions |
| Commit đứng yên, Step vẫn STARTED | Có thể chờ I/O, xử lý chunk lâu hoặc bị treo | Last update, thread dump, connection pool |
| Step COMPLETED nhưng commit thấp | Có thể ít input, nhiều filter hoặc Step dạng tasklet | Read/write count và loại Step |

Một rollback **không nhất thiết** dẫn đến **BatchStatus.FAILED**: lỗi có thể được retry thành công. Ngược lại, một Step **FAILED** có thể đã commit nhiều chunk trước khi lỗi cuối cùng xảy ra.

Ví dụ:

~~~text
Chunk 1: commit thành công
Chunk 2: gặp lỗi tạm thời -> rollback
Chunk 2: retry thành công -> commit
Chunk 3: commit thành công
Step: COMPLETED
~~~

Trong kịch bản này, **rollbackCount > 0** nhưng Step vẫn hoàn thành. Chỉ số commit count giúp quan sát transaction đã hoàn tất; rollback count giúp tìm phần xử lý phải thử lại. Số lần gọi processor/writer trong kịch bản retry có thể nhiều hơn số item thực được ghi sau commit.

### Commit count không đo mọi commit của ứng dụng

Một service có thể mở transaction riêng với **REQUIRES_NEW**, một listener có thể gọi database ngoài transaction chunk, hoặc writer gửi message đến hệ thống không cùng transaction manager. **StepExecution.commitCount** không phải số commit toàn hệ thống và không bảo đảm mọi side effect bên ngoài đã được commit.

Đặc biệt với API, queue hoặc file ngoài transaction, cần theo dõi trạng thái acknowledgment, idempotency key và dữ liệu đích; không dùng commitCount để khẳng định kết quả nghiệp vụ đã bền vững ở mọi hệ thống.

## 5. Log commit count ở cuối Step

Cách đơn giản nhất để ghi lại tổng số commit của mỗi StepExecution là dùng **StepExecutionListener**.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CommitCountAuditListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CommitCountAuditListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "batch step completed: job={}, step={}, stepExecutionId={}, " +
                "status={}, commits={}, rollbacks={}, reads={}, writes={}, " +
                "filtered={}, skipped={}",
                step.getJobExecution().getJobInstance().getJobName(),
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getCommitCount(),
                step.getRollbackCount(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount()
        );

        return null; // Không thay đổi ExitStatus hiện tại.
    }
}
~~~

Đăng ký listener trên Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer,
        CommitCountAuditListener auditListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(auditListener)
            .build();
}
~~~

Listener đọc các count sau khi Step kết thúc theo lifecycle bình thường. Vì **afterStep** có thể không được gọi nếu JVM bị kill, container bị dừng đột ngột hoặc process crash, log này **không phải nguồn kiểm toán bền vững duy nhất**. Metadata từ JobRepository cần được duy trì để có thể truy vấn sau sự cố.

Không thay đổi commit count từ listener:

~~~java
// Không tự sửa count do Spring Batch quản lý.
stepExecution.setCommitCount(stepExecution.getCommitCount() + 1);
~~~

Bộ đếm do framework quản lý theo transaction. Listener giám sát chỉ nên **đọc và xuất thông tin**, tránh can thiệp metadata làm sai số liệu.

## 6. Log tiến độ commit khi Step còn chạy

Với Step chạy hàng giờ, chỉ log ở **afterStep** là quá muộn. **ChunkListener.afterChunk** cho phép quan sát sau khi một chunk được xử lý và transaction hoàn tất thành công theo lifecycle của chunk.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class CommitProgressListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(CommitProgressListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        int commits = step.getCommitCount();

        // Giảm lượng log đối với Job có nhiều nghìn chunk.
        if (commits > 0 && commits % 20 == 0) {
            log.info(
                    "batch progress: step={}, executionId={}, " +
                    "commits={}, rollbacks={}, reads={}, writes={}",
                    step.getStepName(),
                    step.getId(),
                    commits,
                    step.getRollbackCount(),
                    step.getReadCount(),
                    step.getWriteCount());
        }
    }
}
~~~

Đăng ký cùng Step:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(progressListener)
        .build();
~~~

Giá trị 20 chỉ là ví dụ cho chính sách lấy mẫu. Job ngắn có thể log mỗi chunk, còn Job lớn cần giảm tần suất log hoặc sử dụng metrics.

Spring Batch cũng có callback **afterChunkError** để phục vụ chẩn đoán khi một chunk gặp lỗi. Nên log exception cùng **jobExecutionId**, **stepExecutionId**, rollback count và thông tin transaction thích hợp. Tuy nhiên, callback và thời điểm metadata được lưu có thể khác nhau; không dùng một dòng log tức thời để kết luận mọi thay đổi transaction đã hoàn toàn bền vững.

### Chú ý khi có nhiều StepExecution đồng thời

Không giữ bộ đếm tiến độ dùng chung trong một field singleton như **lastCommitCount** nếu nhiều JobExecution có thể chạy đồng thời. Một StepExecution của Job A có thể ghi đè snapshot của Job B. Nếu cần cache tiến độ, key phải xác định đúng StepExecution và có chính sách dọn cache; với monitoring tổng hợp, nên ưu tiên **JobExplorer/JobRepository** làm nguồn metadata.

## 7. Truy vấn commit count bằng JobExplorer

Trong production, dashboard thường ở process khác hoặc không có quyền truy cập trực tiếp StepExecution object đang chạy. **JobExplorer** là giao diện đọc metadata Spring Batch đã lưu.

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchCommitQueryService {

    private final JobExplorer jobExplorer;

    public BatchCommitQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepCommitSnapshot> getCommitCounts(long jobExecutionId) {
        JobExecution jobExecution =
                jobExplorer.getJobExecution(jobExecutionId);

        if (jobExecution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return jobExecution.getStepExecutions().stream()
                .map(step -> new StepCommitSnapshot(
                        step.getId(),
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getCommitCount(),
                        step.getRollbackCount(),
                        step.getReadCount(),
                        step.getWriteCount()))
                .toList();
    }

    public record StepCommitSnapshot(
            Long stepExecutionId,
            String stepName,
            String status,
            int commits,
            int rollbacks,
            long reads,
            long writes) {
    }
}
~~~

Ứng dụng có thể dùng service này từ REST endpoint nội bộ hoặc tác vụ polling. Lưu ý hai vấn đề:

**Thứ nhất, snapshot không phải dòng sự kiện tức thời.** JobExplorer đọc metadata đã được ghi vào JobRepository. Khi Step đang xử lý chunk nhưng chưa đến checkpoint, commit count trong repository có thể chưa tăng.

**Thứ hai, cần query lại.** Một JobExecution hoặc StepExecution đã lấy ở lần đọc trước không tự đồng bộ mọi thay đổi mới từ database sang object trong bộ nhớ. Nếu dashboard refresh mỗi 30 giây, hãy truy vấn lại từ repository.

Ví dụ:

~~~text
09:00:00  commitCount = 10
09:00:30  commitCount = 10   <- chunk tiếp theo đang xử lý
09:01:00  commitCount = 11   <- chunk được commit
09:01:30  commitCount = 14
~~~

Khoảng thời gian commitCount đứng yên có thể hoàn toàn bình thường nếu chunk lớn, writer gọi dịch vụ chậm hoặc database đang xử lý transaction. Một cảnh báo cần dựa trên thời lượng bình thường của Step và các chỉ số khác.

## 8. Truy vấn BATCH_STEP_EXECUTION bằng SQL

Spring Batch lưu metadata của StepExecution trong bảng **BATCH_STEP_EXECUTION** thuộc JobRepository. Với schema Spring Batch 5.x, các cột thường gặp là:

- **STEP_EXECUTION_ID**, **JOB_EXECUTION_ID**, **STEP_NAME**
- **STATUS**, **EXIT_CODE**, **EXIT_MESSAGE**
- **COMMIT_COUNT**, **ROLLBACK_COUNT**
- **READ_COUNT**, **WRITE_COUNT**, **FILTER_COUNT**
- **READ_SKIP_COUNT**, **PROCESS_SKIP_COUNT**, **WRITE_SKIP_COUNT**
- **LAST_UPDATED**

SQL minh họa:

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.FILTER_COUNT,
    se.LAST_UPDATED
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY se.STEP_EXECUTION_ID DESC;
~~~

Có thể xây trang quản trị cho những lần thực thi gần nhất:

| JobExecution | StepExecution | Trạng thái | Commit | Rollback | Read | Write |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 2508 | 4712 | COMPLETED | 31 | 0 | 12.000 | 12.000 |
| 2507 | 4711 | FAILED | 8 | 2 | 3.500 | 3.000 |
| 2506 | 4710 | COMPLETED | 16 | 0 | 6.000 | 6.000 |

*Các giá trị chỉ để minh họa cách diễn giải, không phải công thức cố định cho chunk size.*

Một số nguyên tắc vận hành:

- Dùng tài khoản database **read-only** để truy vấn bảng metadata nếu hệ thống hỗ trợ.
- Giới hạn tên Job, thời gian, số dòng khi truy vấn repository lớn.
- Không chỉnh sửa **COMMIT_COUNT** trực tiếp để “sửa” dashboard.
- Không suy diễn **LAST_UPDATED** luôn chính là thời điểm commit nghiệp vụ gần nhất; nó là thời điểm cập nhật metadata.
- Nếu các instance chạy trên nhiều node, dashboard phải truy vấn đúng JobRepository chung.
- Nếu có nhiều schema/repository độc lập, cần xác định rõ phạm vi của từng nguồn dữ liệu.

Truy vấn SQL hữu ích cho dashboard hoặc điều tra production, còn **JobExplorer** phù hợp hơn khi cần làm việc qua API chính thức của Spring Batch.

## 9. Xuất commit count ra Micrometer

Spring Boot Actuator và Micrometer giúp thu thập các số liệu vận hành. Tùy phiên bản, Spring Batch có thể đã xuất các metric liên quan đến Step, chunk hoặc item; nên kiểm tra tên metric tích hợp trước khi thêm metric riêng.

Một lựa chọn là tạo **Counter** cho số commit được StepExecution ghi nhận khi **afterStep** chạy. Ví dụ:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CommitMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;

    public CommitMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        String jobName = step.getJobExecution()
                .getJobInstance()
                .getJobName();

        Counter.builder("app.batch.step.commits")
                .description("Commits of completed StepExecutions")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "status", step.getStatus().name())
                .register(registry)
                .increment(step.getCommitCount());

        Counter.builder("app.batch.step.rollbacks")
                .description("Rollbacks of completed StepExecutions")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "status", step.getStatus().name())
                .register(registry)
                .increment(step.getRollbackCount());

        return null;
    }
}
~~~

Đăng ký listener trên Step cần giám sát:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(commitMetricsListener)
        .build();
~~~

**Cách hiểu metric rất quan trọng:** Counter ở ví dụ chỉ tăng **khi StepExecution kết thúc và afterStep được gọi**. Nó là tổng số commit được các callback báo cáo trong thời gian sống của process, **không phải giá trị commit count trực tiếp của một Step đang chạy**.

Các giới hạn:

1. Nếu process chết trước khi callback chạy, metric có thể thiếu commit đã lưu trong JobRepository.
2. Nếu process restart, Counter trong memory thường bắt đầu lại; hệ thống quan sát cần xử lý counter reset.
3. Nếu một Step restart, callback của từng StepExecution có thể cộng vào Counter; đó là thống kê transaction theo lần thực thi, không phải số item duy nhất của JobInstance.
4. Nếu ứng dụng có nhiều instance, Counter tồn tại trên từng instance; khi vẽ tổng dịch vụ, cần gộp series từ tất cả instance.
5. Tránh cập nhật cùng một Counter theo **afterChunk** và cộng lại toàn bộ **getCommitCount()** trong **afterStep**, vì sẽ đếm trùng.

Nếu yêu cầu dashboard **live theo từng chunk**, có thể xuất metric delta từ ChunkListener hoặc lấy các snapshot JobExplorer theo chu kỳ; mỗi metric cần có cách diễn giải thống nhất.

### Không dùng label có cardinality cao

Các label như **jobExecutionId**, **stepExecutionId**, **UUID**, **customerId** hoặc đường dẫn file ngẫu nhiên tạo ra một series mới mỗi lần Job chạy. Số lượng series có thể tăng rất nhanh và gây tốn tài nguyên Prometheus.

Nên ưu tiên:

~~~text
job    = "importOrdersJob"
step   = "importOrdersStep"
status = "COMPLETED"
~~~

Dùng **JobExecution ID** và **StepExecution ID** ở log hoặc metadata query để truy vết lần chạy cụ thể. Metric thích hợp cho xu hướng tổng hợp theo Job/Step; không cần gắn mọi ID nghiệp vụ vào mỗi metric.

## 10. Biểu diễn commit count trên dashboard

Một dashboard hữu ích không chỉ có một ô **commitCount**. Nên đặt các nhóm chỉ số liên quan cạnh nhau:

| Khu vực | Chỉ số | Câu hỏi cần trả lời |
| --- | --- | --- |
| Trạng thái | Job/Step status, start time, duration | Job đã hoàn tất hay còn chạy? |
| Tiến độ | readCount, writeCount, filterCount | Bao nhiêu item đã được tiếp nhận và ghi? |
| Giao dịch | commitCount, rollbackCount | Transaction có đang commit? |
| Chất lượng | read/process/write skip count | Có bao nhiêu lỗi được bỏ qua? |
| Hiệu năng | items/giây, commits/phút, chunk duration | Tốc độ xử lý có giảm? |
| Metadata | last update, thời gian từ checkpoint gần nhất | Snapshot còn mới hay đã lâu? |
| Nghiệp vụ | count thực tế tại bảng đích, checksum hoặc tổng số tiền | Output có đúng dữ liệu kỳ vọng? |

### Đo commits/giây

Giả sử metric Micrometer **app.batch.step.commits** được registry Prometheus xuất theo tên **app_batch_step_commits_total**. Một biểu thức PromQL có thể là:

~~~promql
sum by (job, step) (
  rate(app_batch_step_commits_total[5m])
)
~~~

Kết quả là **commit/giây trung bình** trong cửa sổ 5 phút dựa trên Counter. Nếu muốn hiển thị commit/phút, có thể nhân 60. Tên metric thực tế phụ thuộc cấu hình exporter và naming convention.

Do ví dụ Counter chỉ cập nhật ở **afterStep**, đồ thị sẽ ghi nhận các đợt tăng khi Step kết thúc, **không cho biết chính xác thời điểm từng chunk được commit**. Với Job rất dài, nên dùng snapshot/metric phát sinh trong lúc Step chạy nếu muốn biểu diễn tiến độ live.

### Tính tốc độ từ snapshot

Với một StepExecution đang chạy, giả sử dashboard lấy dữ liệu theo thời gian:

~~~text
Thời gian    commitCount   readCount   writeCount
09:00:00         10          5000        5000
09:00:30         12          6000        6000
09:01:00         14          7000        7000
09:01:30         14          7000        7000
09:02:00         17          8500        8500
~~~

Tốc độ trên một khoảng:

~~~text
commits/sec = delta(commitCount) / delta(seconds)
reads/sec   = delta(readCount) / delta(seconds)
writes/sec  = delta(writeCount) / delta(seconds)
~~~

Tại 09:01:30, count đứng yên có thể do một chunk đang xử lý lâu. Không nên cảnh báo ngay chỉ dựa vào một mẫu 30 giây. Cần kết hợp thời lượng chunk bình thường và trạng thái hệ thống.

**Không dùng writeCount / commitCount để suy ra chính xác chunk size.** Việc lọc, skip, transaction khi hết input, retry và các loại Step khác nhau có thể khiến tỷ lệ này thay đổi.

## 11. Cảnh báo dựa trên commit count

### 11.1. Step không tiến triển

Một quy tắc tham khảo:

~~~text
Nếu Step đang STARTED
và commitCount không tăng trong N phút
và thời lượng Step đã vượt ngưỡng quan sát bình thường
thì tạo cảnh báo điều tra.
~~~

Giá trị **N** phải dựa trên các lần chạy thực tế. Step có chunk dài 15 phút không nên bị đánh dấu stuck chỉ vì commitCount không thay đổi trong 3 phút.

Các tín hiệu đi kèm gồm:

- Mốc **LAST_UPDATED** trong metadata.
- Thread state và log của reader/processor/writer.
- Connection pool, database lock waits và thời gian giao dịch.
- Tốc độ read/write và thời điểm chunk hoàn thành gần nhất.
- JobStatus/StepStatus và ngưỡng SLA.

### 11.2. Rollback bất thường

**rollbackCount** tăng nhanh trong khi commitCount ít tăng có thể chỉ ra lỗi constraint, deadlock, timeout hoặc retry lặp lại. Có thể dùng tỷ lệ để quan sát xu hướng:

~~~text
rollbackRatio = rollbackCount / max(1, rollbackCount + commitCount)
~~~

Đây chỉ là **chỉ số tham khảo**, không phải tỷ lệ lỗi chuẩn do Spring Batch định nghĩa. Cần đối chiếu exception và retry policy, vì rollback được chấp nhận trong một số kịch bản fault tolerance.

### 11.3. SLA bị trễ

Ví dụ Job chốt sổ chạy lúc 01:00 và phải hoàn thành trước 02:00. Cảnh báo có giá trị nhất là **không có JobExecution thành công cho kỳ nghiệp vụ cần xử lý**, hoặc dữ liệu đích chưa đáp ứng điều kiện đối soát.

Commit count giúp giải thích tiến độ tại thời điểm SLA bị trễ, nhưng **nhiều commit không có nghĩa Job đã COMPLETED**. Một Step có thể commit thành công hàng trăm chunk rồi thất bại ở cuối.

## 12. Restart và cách tổng hợp count

Giả sử Job xử lý một file lớn, lỗi sau vài chunk và được restart:

~~~text
JobInstance: importOrdersJob(businessDate=2026-11-15)

JobExecution #1: FAILED
  StepExecution #41
  commitCount   = 5
  writeCount    = 2500
  rollbackCount = 1

JobExecution #2: COMPLETED
  StepExecution #42
  commitCount   = 7
  writeCount    = 3000
  rollbackCount = 0
~~~

Những giá trị là giả định minh họa.

Khi giám sát:

- Đọc **StepExecution #41** để biết tiến độ và lỗi của lần chạy đầu.
- Đọc **StepExecution #42** để biết tiến độ của lần restart.
- Kiểm tra bảng/file đích để biết **kết quả nghiệp vụ cuối cùng**.

Nếu muốn thống kê **tổng transaction commit được Step ghi nhận qua các lần thực thi**, có thể tổng hợp count của những StepExecution liên quan, sau khi xác định rõ phạm vi và tránh đếm trùng dữ liệu đã được aggregator tổng hợp.

Nếu muốn thống kê **số đơn hàng duy nhất đã import**, phải dựa trên business key, checkpoint và output thực tế. Tổng commit count qua restart không thay thế số bản ghi cuối cùng.

Đặc biệt, **StepExecution khác nhau có thể có commitCount khác nhau ngay cả khi tên Step giống hệt nhau**; không nên cache tiến độ chỉ theo step name khi có nhiều JobExecution.

## 13. Commit count trong những kiểu xử lý đặc biệt

### 13.1. Tasklet Step

Một Tasklet có thể thực hiện kiểm tra file, cập nhật trạng thái hay chạy SQL mà không đi qua ItemReader/ItemWriter. Khi đó **readCount/writeCount** có thể bằng 0 nhưng **commitCount** vẫn phản ánh các transaction được Step ghi nhận. Không áp dụng công thức chunk size cho Tasklet.

### 13.2. Multi-threaded Step

Khi cấu hình Step sử dụng nhiều worker thread theo cách được framework hỗ trợ, thứ tự chunk hoàn thành và thời điểm commit có thể không còn tuyến tính theo vị trí item. Commit count vẫn hữu ích để quan sát giao dịch, nhưng không thể mặc nhiên coi nó là offset liên tục trong file input.

### 13.3. Partitioned Step

Một Step được chia partition có thể có nhiều worker StepExecution và một manager StepExecution:

~~~text
importOrders.manager
  +-- importOrders:partition0
  +-- importOrders:partition1
  +-- importOrders:partition2
~~~

Manager có thể tổng hợp count qua **StepExecutionAggregator**. Nếu lấy tổng cả manager và các worker, dashboard có thể **đếm trùng**. Khi cần thống kê theo partition, chọn worker executions; khi cần tổng hợp, đọc metadata được aggregator cung cấp hoặc cộng đúng một tập dữ liệu nhất quán.

### 13.4. Writer gọi hệ thống ngoài

Trong remote chunking, API/queue hoặc file nằm ngoài transaction của Step, commit count không đồng nghĩa với việc remote side effect đã chắc chắn xảy ra đúng một lần. Một request có thể thành công nhưng Step crash trước checkpoint; khi restart, request có thể bị gửi lại.

Cần xem thêm xác nhận từ đích, outbox, transaction boundary và idempotency key. Không dùng riêng commit count để tuyên bố tính chất exactly-once.

## 14. Kiểm thử commit count

### 14.1. Integration test Step thành công

Ví dụ theo **Spring Boot 3.x, Spring Batch 5.x, JUnit 5, AssertJ và spring-batch-test**. Giả định context đã có Job chứa **importOrdersStep**, dữ liệu fixture gồm đúng bảy item và writer ghi đủ bảy item.

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersCommitMonitoringTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void shouldRecordCommitProgress() throws Exception {
        // Reader được chuẩn bị để trả về đúng 7 item.
        JobParameters parameters = new JobParametersBuilder()
                .addString("caseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchStep("importOrdersStep", parameters);

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getReadCount()).isEqualTo(7);
        assertThat(step.getWriteCount()).isEqualTo(7);
        assertThat(step.getSkipCount()).isZero();
        assertThat(step.getRollbackCount()).isZero();

        // Không suy ra chính xác số commit chỉ từ chunk size.
        assertThat(step.getCommitCount()).isPositive();
    }
}
~~~

Dữ liệu test nên được cô lập bằng caseId hoặc database riêng. Nếu trong context có nhiều Job, phải cấu hình **JobLauncherTestUtils** theo Job mục tiêu. Nếu launcher bất đồng bộ, cần đợi trạng thái kết thúc trước khi kiểm tra count.

Không nên assert **commitCount == ceil(7 / chunkSize)** một cách máy móc nếu chưa xác định semantics của Step dưới cấu hình thực tế. Chỉ assert đúng số commit khi mục tiêu test chính là transaction boundary và test kiểm soát được kịch bản, phiên bản framework và đầu vào.

### 14.2. Unit test logic monitoring

**MetaDataInstanceFactory** trong spring-batch-test giúp tạo StepExecution giả lập cho service hoặc listener cần đọc count:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

StepExecution step = MetaDataInstanceFactory.createStepExecution();
step.setCommitCount(6);
step.setRollbackCount(1);
step.setReadCount(120);
step.setWriteCount(118);

// Truyền step vào service hoặc listener monitor cần kiểm thử.
// Assert DTO, log event hoặc metric mà logic đó tạo ra.
~~~

Việc tự **setCommitCount(6)** rồi kiểm tra lại getter **không chứng minh Spring Batch đã commit sáu transaction**. Nó chỉ là fixture để kiểm thử cách ứng dụng hiển thị hoặc xử lý metadata. Muốn kiểm tra count thực sự do framework tạo ra, phải chạy Step/Job trong integration test.

### 14.3. Kiểm tra rollback/retry

Với Step **faultTolerant()**, có thể tạo một lỗi xác định tại processor hoặc writer để kiểm tra callback giám sát:

- Lần xử lý đầu tạo lỗi khiến transaction rollback.
- Retry hoặc skip xảy ra đúng cấu hình.
- Step kết thúc với BatchStatus mong đợi.
- Log/metric chứa commit count và rollback count phù hợp.
- Dữ liệu đầu ra đúng sau lỗi và sau retry.

Nếu muốn xác minh tính chất rollback của JDBC, test cần writer và transaction manager phù hợp. Một mock không tham gia transaction sẽ không đại diện cho mọi hành vi database.

## 15. Lỗi diễn giải thường gặp

### Commit count không tăng nhưng read count có thay đổi

Có thể Step đang ở giữa một chunk chưa commit. Nên kiểm tra trạng thái transaction và log xử lý trước khi cảnh báo. Khi một chunk phải đọc và xử lý rất nhiều item, khoảng thời gian không commit có thể dài hơn chu kỳ polling.

### Commit count tăng nhưng không có thêm bản ghi trong bảng đích

Có thể tất cả item bị filter, writer thực hiện update thay vì insert, hoặc có transaction checkpoint không ghi item. Nếu writer gửi dữ liệu ra hệ thống ngoài, cần xem xác nhận từ hệ thống đó.

### Commit count nhỏ hơn số chunk dự đoán

Kiểm tra cách Step kết thúc, rollback, retry, EOF, skip, tasklet behavior và dữ liệu đầu vào. Commit count là metadata thực tế của StepExecution; không cần ép nó khớp một công thức chung.

### Dashboard mất số liệu khi application restart

Micrometer Counter trong bộ nhớ có thể reset theo process. Truy vấn **JobRepository** để lấy snapshot bền vững và dùng công cụ monitoring có xử lý counter reset; không phụ thuộc hoàn toàn vào Counter trong JVM.

### Restart làm biểu đồ tăng bất thường

Mỗi lần restart tạo StepExecution mới và có commit count riêng. Cần phân biệt total commit theo execution với output duy nhất theo kỳ nghiệp vụ. Cũng cần tránh đếm trùng manager/worker khi có partition.

### Log và SQL hiển thị count khác nhau

Có thể do khác thời điểm snapshot, metadata chưa được cập nhật ở checkpoint, hoặc đang xem nhầm execution. Hãy đưa **jobExecutionId** và **stepExecutionId** vào log để đối chiếu chính xác với bảng metadata.

### Metric có quá nhiều series

Không gắn UUID, customer ID, file path, jobExecutionId vào metric label tổng hợp. Dùng chúng trong log/tracing hoặc metadata query; để metric tập trung ở nhãn ổn định như job, step, status.

## 16. Quy trình theo dõi commit count trong production

Một quy trình triển khai có thể gồm các bước:

1. **Xác định Job quan trọng** và ngưỡng SLA theo nghiệp vụ.
2. **Đọc metadata gốc** từ JobRepository: status, commitCount, rollbackCount, read/write/filter/skip count và thời gian cập nhật.
3. **Thêm log tiến độ** ở ChunkListener cho Job dài, và log tổng kết ở StepExecutionListener.
4. **Xuất metric tổng hợp** với Micrometer nếu cần dashboard nhiều instance; định nghĩa rõ metric được cập nhật theo chunk hay sau Step.
5. **Đặt cảnh báo có ngữ cảnh**: commit không tăng quá lâu, rollback cao, Step quá SLA hoặc không có kết quả thành công cho kỳ xử lý.
6. **Đối chiếu output thực tế** bằng record count, checksum hoặc quy tắc nghiệp vụ.
7. **Kiểm tra fault scenarios**: writer chậm, retry, rollback, restart, partition và crash.
8. **Duy trì lịch sử và retention** của JobRepository sao cho có thể điều tra thất bại mà không gây quá tải hệ thống theo dõi.

Ví dụ màn hình quan sát:

~~~text
Job         : dailyImportJob
BusinessDate: 2026-11-15
Execution   : 2608
Status      : STARTED

Step        : importOrdersStep
StepExec ID : 4712

READ        WRITE       FILTER     SKIP
12 500      12 400      100        0

COMMIT      ROLLBACK    LAST UPDATED
25          0           01:42:18 UTC

Business result: chờ Step hoàn thành để đối soát.
~~~

**Commit count tăng** là một tín hiệu hữu ích rằng Step đã ghi nhận các transaction thành công. Tuy nhiên, **tính đúng đắn của batch** còn phụ thuộc trạng thái cuối cùng, cách xử lý rollback và skip, checkpoint/restart, và dữ liệu nghiệp vụ thực sự được ghi. Khi theo dõi tất cả các tín hiệu đó cùng nhau, commit count trở thành một thước đo thực tế giúp phát hiện sớm Step bị nghẽn và giải thích tiến độ xử lý.

