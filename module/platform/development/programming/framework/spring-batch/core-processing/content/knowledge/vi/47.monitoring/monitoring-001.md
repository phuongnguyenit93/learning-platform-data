# Đếm `read`, `write`, `filter` và `skip` khi giám sát Spring Batch

Một batch job có trạng thái `COMPLETED` chưa đủ để khẳng định dữ liệu đã được xử lý đúng kỳ vọng. Một job nhập 10.000 bản ghi có thể hoàn tất nhưng chỉ ghi 9.400 bản ghi vì 500 bản ghi không đạt điều kiện nghiệp vụ và 100 bản ghi bị bỏ qua do lỗi cho phép. Để đánh giá kết quả thực tế, Spring Batch lưu **các bộ đếm xử lý item** trong `StepExecution`: số đọc thành công (`read`), số ghi thành công (`write`), số lọc theo nghiệp vụ (`filter`) và số bị bỏ qua do lỗi (`skip`).

Bài này tập trung vào bốn nhóm số đếm đó trong phạm vi **Monitoring** của *Spring Batch Core Processing*: ý nghĩa chính xác của từng counter, cách Spring Batch cập nhật, cách đọc từ Java và database, cách theo dõi khi job chạy, cùng những sai lầm dễ gặp khi xử lý retry, rollback hoặc restart.

## 1. Luồng item và nơi phát sinh bộ đếm

Trong một chunk-oriented step điển hình:

```text
                 ItemReader.read()
                         |
            +------------+-------------+
            |                          |
         Trả item                   Ném lỗi
            |                          |
            v                          v
       readCount++             Được phép skip?
            |                          |
            v                          +-- Có --> readSkipCount++
   ItemProcessor.process()             |
            |                          +-- Không --> Step FAILED
       +----+-------------+
       |                  |
       v                  v
   Trả null            Trả item           Ném lỗi
       |                  |                  |
       v                  |                  +-- Được skip --> processSkipCount++
 filterCount++            |                  +-- Không --> Step FAILED
       |                  v
  Không gửi writer     ItemWriter.write(chunk)
                          |
                    +-----+----------+
                    |                |
                    v                v
                Ghi thành công    Ghi lỗi
                    |                |
                    v                +-- Skip item hợp lệ --> writeSkipCount++
               writeCount           +-- Không xử lý được --> Step FAILED
```

Sơ đồ là mô hình khái niệm của kết quả **được chấp nhận** sau cơ chế transaction/chunk. Trên thực tế, writer nhận **cả chunk**, có thể retry hoặc rollback; khi đó số lần gọi `read`, `process`, `write` không nhất thiết bằng các bộ đếm cuối cùng trong `StepExecution`. Thao tác `ItemReader.read()` trả về `null` để báo hết dữ liệu **không** làm tăng `readCount`.

Đơn vị của bộ đếm là **item mà framework xử lý**, không bắt buộc là dòng văn bản, dòng database, số lần gọi phương thức hay số bản ghi vật lý được cập nhật. Ví dụ một `ItemWriter` có thể gọi một stored procedure thay đổi nhiều dòng database cho một item; `writeCount` vẫn được tính theo số item writer xử lý thành công theo mô hình của step.

## 2. Bốn nhóm counter của `StepExecution`

| Counter / getter | Ý nghĩa thực hành | Thời điểm cần chú ý |
| --- | --- | --- |
| `readCount` — `getReadCount()` | Số item đọc **thành công** từ `ItemReader` | Không gồm những lần đọc trả `null` báo hết dữ liệu; read error được skip có bộ đếm riêng |
| `writeCount` — `getWriteCount()` | Số item được writer xử lý thành công theo các chunk đã được framework chấp nhận | Không đồng nhất với số lần gọi `ItemWriter.write(...)` hoặc số dòng SQL thực sự thay đổi |
| `filterCount` — `getFilterCount()` | Số item bị `ItemProcessor` loại khỏi luồng viết bằng cách **trả `null`** | Là quyết định xử lý bình thường, không phải lỗi |
| `readSkipCount` — `getReadSkipCount()` | Số lỗi đọc được chính sách skip chấp nhận | Ví dụ một dòng input hỏng khiến reader ném ngoại lệ có thể skip |
| `processSkipCount` — `getProcessSkipCount()` | Số item bị skip do ngoại lệ trong xử lý | Khác với processor trả `null` |
| `writeSkipCount` — `getWriteSkipCount()` | Số item bị skip do lỗi ở bước ghi | Writer xử lý chunk nên có thể cần rollback và thử từng item để xác định item lỗi |
| `skipCount` — `getSkipCount()` | **Tổng** ba loại skip kể trên | `readSkipCount + processSkipCount + writeSkipCount`; **không** bao gồm `filterCount` |

Các getter trên có trong `org.springframework.batch.core.StepExecution` của Spring Batch 5.x. Các trường liên quan khác đáng xem là `getCommitCount()`, `getRollbackCount()`, `getStatus()` và `getExitStatus()`. Chúng giúp giải thích vì sao bộ đếm ở một lần chạy có thể khác kỳ vọng.

**Không nên cộng `filterCount` vào `skipCount`.** Hai loại thể hiện hai quyết định khác nhau:

- **Filter**: bản ghi hợp lệ nhưng ứng dụng quyết định không gửi sang writer, chẳng hạn đơn hàng đã hủy hoặc giao dịch ngoài kỳ đối soát.
- **Skip**: gặp lỗi được đánh giá là có thể bỏ qua theo chính sách fault tolerance, chẳng hạn dòng CSV sai định dạng hoặc item vi phạm một quy tắc hợp lệ có thể loại bỏ.

Spring Batch chỉ tăng skip counter khi lỗi được **xử lý theo cơ chế skip**. Một exception được retry rồi thành công không mặc nhiên thành skip; một exception nghiêm trọng làm step `FAILED` cũng không mặc nhiên được ghi như một skipped item.

## 3. Ví dụ tính số liệu cụ thể

Giả sử một step đọc file gồm 10 dòng nghiệp vụ; 2 dòng lỗi định dạng ngay trong reader, 8 dòng được đọc thành công. Trong 8 dòng đó, processor lọc 1 đơn hàng đã hủy, bỏ qua do lỗi 1 đơn hàng sai dữ liệu; writer gặp lỗi có thể skip với 1 item; 5 item còn lại được ghi thành công.

| Số liệu | Giá trị | Giải thích |
| --- | ---: | --- |
| Số dòng nghiệp vụ trong file | 10 | Số quan sát vật lý từ nguồn dữ liệu của ví dụ |
| `readCount` | 8 | Reader trả về thành công 8 item |
| `readSkipCount` | 2 | Hai lần đọc bị lỗi và được phép skip |
| `filterCount` | 1 | Processor trả `null` với một item hợp lệ |
| `processSkipCount` | 1 | Một item phát sinh exception có thể skip khi xử lý |
| `writeSkipCount` | 1 | Một item lỗi khi ghi và được skip |
| `writeCount` | 5 | Năm item ghi thành công |
| `skipCount` | 4 | `2 + 1 + 1`, không cộng filter |

Với **ví dụ đơn giản một item đầu vào tương ứng tối đa một item đầu ra**, không có retry/rollback ảnh hưởng kết quả cuối, ta có:

```text
10 dòng nguồn = 8 read thành công + 2 readSkip

8 read thành công = 1 filter + 1 processSkip + 1 writeSkip + 5 write

skipCount = readSkipCount + processSkipCount + writeSkipCount
          = 2 + 1 + 1 = 4
```

Các đẳng thức đầu chỉ nhằm **diễn giải tình huống một-một cụ thể**, không phải bất biến phổ quát cho mọi step. Một step có writer tổng hợp dữ liệu, reader đọc từ nhiều nguồn, processor có trạng thái, giao dịch rollback hoặc job restart có thể khiến phép cộng này không mô tả đúng tất cả bản ghi nghiệp vụ. Đẳng thức cho `skipCount` là định nghĩa của tổng skip ở cấp step.

## 4. Spring Batch cập nhật counter ở đâu?

Trong chunk-oriented processing, Spring Batch dùng `StepContribution` để thu thập kết quả của đoạn xử lý và hợp nhất chúng vào `StepExecution` khi chunk thành công. `StepExecution` được `JobRepository` lưu định kỳ, thường gắn với ranh giới transaction/commit. Vì vậy, counter trong repository là **kết quả xử lý được ghi nhận**, thay vì một đồng hồ tăng mỗi khi code nghiệp vụ được gọi.

```text
     StepExecution (tổng của step)
           ^
           | apply / cập nhật theo chunk
           |
     StepContribution (kết quả chunk hiện tại)
           ^
           |
   read / process / filter / write / skip
           |
           v
   Transaction commit hoặc rollback
```

Trong những step chuẩn do `TaskletStep` và chunk machinery điều khiển, framework tự tính counter. Ta không cần gọi `stepExecution.setReadCount(...)` hay `setWriteCount(...)` bằng tay chỉ để theo dõi các hoạt động của `ItemReader`/`ItemWriter` thông thường.

Các điểm ảnh hưởng đến cách hiểu:

1. **Chunk commit:** `readCount` và `writeCount` quan sát trong lúc step đang chạy có thể chưa phản ánh hoàn toàn chunk hiện hành vì counter phải được đồng bộ và lưu vào repository.
2. **Rollback:** một lần thử ghi không thành công có thể phải xử lý lại chunk hoặc từng item. Counter cuối cùng không được diễn giải như số lần phương thức writer đã bị gọi.
3. **Retry:** một item được thử nhiều lần trước khi thành công có thể chỉ đóng góp một item vào kết quả; không dùng callback `onProcessError`/`onWriteError` để suy ra skipCount.
4. **Skip:** ngoại lệ phù hợp với skip policy làm tăng một trong ba skip counter. Lỗi không được skip có thể dừng step và để lại trạng thái `FAILED`.
5. **Restart:** một `JobInstance` có thể có nhiều `JobExecution`, mỗi lần chạy lại tạo `StepExecution` tương ứng khi step được thực thi. Cần chọn đúng lần chạy để đọc counter.

## 5. Đọc số liệu trực tiếp từ `StepExecution`

Ở Spring Batch 5.x, API getter có thể được dùng trong test, listener, service nội bộ hoặc sau khi nhận `JobExecution` từ launcher:

```java
import org.springframework.batch.core.StepExecution;

public record StepCounts(
        long read,
        long write,
        long filter,
        long readSkip,
        long processSkip,
        long writeSkip,
        long totalSkip,
        long commits,
        long rollbacks) {

    public static StepCounts from(StepExecution step) {
        return new StepCounts(
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

`record` yêu cầu Java 16+; Spring Batch 5.x thường được dùng với Java 17. Nếu dự án dùng Java phiên bản thấp hơn ở nhánh Spring Batch cũ, có thể thay bằng class thông thường.

Để lấy số liệu của các step sau khi job chạy:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

public void printStepCounts(JobExecution execution) {
    for (StepExecution step : execution.getStepExecutions()) {
        StepCounts counts = StepCounts.from(step);
        System.out.printf(
                "jobExecution=%s step=%s status=%s read=%d write=%d " +
                "filter=%d skip=%d [read=%d process=%d write=%d]%n",
                execution.getId(),
                step.getStepName(),
                step.getStatus(),
                counts.read(),
                counts.write(),
                counts.filter(),
                counts.totalSkip(),
                counts.readSkip(),
                counts.processSkip(),
                counts.writeSkip());
    }
}
```

`JobExecution.getStepExecutions()` trả về collection của các `StepExecution` gắn với **lần chạy job đang xét**. Không mặc định rằng mỗi job chỉ có một step; khi có nhiều step, số liệu được đặt tên theo `stepName` để tránh nhầm.

## 6. Log counter bằng `StepExecutionListener`

Nếu muốn có dòng log khi step kết thúc (thành công hoặc thất bại), `StepExecutionListener.afterStep(...)` là nơi thuận tiện để lấy bản tổng hợp từ `StepExecution`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepCountsLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepCountsLoggingListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "step={} jobExecution={} batchStatus={} exitStatus={} " +
                "read={} write={} filter={} " +
                "readSkip={} processSkip={} writeSkip={} totalSkip={} " +
                "commit={} rollback={}",
                step.getStepName(),
                step.getJobExecutionId(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());

        // Không yêu cầu thay đổi ExitStatus do framework đã quyết định.
        return null;
    }
}
```

`afterStep` có thể trả về `ExitStatus` để tham gia điều chỉnh exit status; trả `null` nghĩa là không đóng góp trạng thái mới. Listener này chỉ quan sát dữ liệu, không tự sửa các bộ đếm.

Gắn listener khi cấu hình step:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> orderReader,
                      ItemProcessor<Order, ProcessedOrder> orderProcessor,
                      ItemWriter<ProcessedOrder> orderWriter) {
    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener(new StepCountsLoggingListener())
            .build();
}
```

Đoạn cấu hình minh họa cách gắn listener trong **Spring Batch 5.x**, giả sử các kiểu `Order`, `ProcessedOrder` và bean reader/processor/writer đã được ứng dụng định nghĩa. Những import cần thiết là `org.springframework.batch.core.Step`, `org.springframework.batch.core.job.builder` không dùng ở đây, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.item.ItemReader`, `ItemProcessor`, `ItemWriter`, cùng `org.springframework.transaction.PlatformTransactionManager`. Với nhiều step, có thể dùng cùng một listener không giữ trạng thái mutable nội bộ.

**Khi nào log trong `afterStep`?** Khi muốn một bản ghi tổng kết cho mỗi `StepExecution`, kể cả các lần bị `FAILED`. Khi muốn tỷ lệ theo thời gian thực, cần thêm cơ chế đọc metadata hoặc giám sát trong quá trình chạy; không nên biến `afterStep` thành bộ đếm live vì callback này chỉ được gọi ở cuối step.

## 7. Ví dụ đầy đủ: filter một item và skip một item

Ví dụ sau minh họa **Spring Batch 5.2.x**, giả định application context đã có `JobRepository` và `PlatformTransactionManager` phù hợp. Reader cung cấp sáu chuỗi; processor xử lý theo ba trường hợp:

- `FILTER`: processor trả `null`, tăng `filterCount`.
- `SKIP`: processor ném `IllegalArgumentException`, được cấu hình là exception có thể skip, tăng `processSkipCount`.
- Các chuỗi còn lại: processor chuyển sang chữ thường và chuyển cho writer.

```java
import java.util.List;
import java.util.Locale;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MonitoringStepConfig {

    // Tạo một reader riêng cho mỗi lần thực thi step.
    @Bean
    @StepScope
    public ItemReader<String> monitoredReader() {
        return new ListItemReader<>(List.of(
                "OK-1", "FILTER", "OK-2", "SKIP", "OK-3", "OK-4"));
    }

    @Bean
    public Step monitorStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("monitoredReader") ItemReader<String> reader) {

        ItemProcessor<String, String> processor = item -> {
            if ("FILTER".equals(item)) {
                return null; // Lọc theo nghiệp vụ, không phải skip.
            }
            if ("SKIP".equals(item)) {
                throw new IllegalArgumentException("Invalid item");
            }
            return item.toLowerCase(Locale.ROOT);
        };

        ItemWriter<String> writer = chunk -> {
            for (String item : chunk) {
                System.out.println("Written: " + item);
            }
        };

        return new StepBuilder("monitorStep", jobRepository)
                .<String, String>chunk(3, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .skip(IllegalArgumentException.class)
                .skipLimit(2)
                .listener(new StepCountsLoggingListener())
                .build();
    }
}
```

Sơ đồ dữ liệu logic:

```text
Reader (6 item đọc thành công)
  OK-1   -> processor -> ok-1  -> writer
  FILTER -> processor -> null  -> filter
  OK-2   -> processor -> ok-2  -> writer
  SKIP   -> processor -> exception được skip
  OK-3   -> processor -> ok-3  -> writer
  OK-4   -> processor -> ok-4  -> writer

Kỳ vọng (step COMPLETED):
  readCount        = 6
  writeCount       = 4
  filterCount      = 1
  readSkipCount    = 0
  processSkipCount = 1
  writeSkipCount   = 0
  skipCount        = 1
```

`ListItemReader` chỉ dùng làm dữ liệu minh họa. Trong hệ thống thực tế, các lỗi đọc có thể phát sinh từ `FlatFileItemReader`, `JdbcCursorItemReader` hoặc nguồn dữ liệu khác. Writer ở ví dụ in ra console; khi dùng database hoặc API ngoài, cần bảo đảm transaction và cơ chế idempotency tương thích với retry/restart. `@StepScope` giúp tạo reader riêng theo lần chạy step, tránh tái sử dụng vị trí đọc còn sót từ execution trước.

### Assertion qua `JobLauncherTestUtils`

Trong một ứng dụng Spring Boot có cấu hình Batch hợp lệ, có thể dùng `spring-batch-test` để thực thi riêng step theo tên và kiểm tra counter ngay từ `JobExecution` trả về:

```java
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

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MonitorStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Test
    void countsReadWriteFilterAndSkip() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testCase", "countsReadWriteFilterAndSkip")
                .toJobParameters();

        // Context phải chứa bean Step tên "monitorStep".
        JobExecution jobExecution = launcher.launchStep("monitorStep", parameters);

        StepExecution step = jobExecution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("monitorStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(6L, step.getReadCount());
        assertEquals(4L, step.getWriteCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(1L, step.getSkipCount());
    }
}
```

Bài test giả định có `MonitoringStepConfig`, datasource/repository test và cấu hình Spring Batch được nạp vào context. Nếu `JobRepository` giữ metadata của một job đã `COMPLETED` với cùng identifying parameters từ lần chạy trước, phải cô lập/làm sạch repository test hoặc chọn cơ chế chuẩn bị instance phù hợp với mục đích kiểm thử. Không dùng các tham số ngẫu nhiên để che lỗi restart hoặc kiểm thử danh tính job.

## 8. Khi nào là `filter`, khi nào là `skip`?

Xét một job chuyển đơn hàng từ dữ liệu thô sang bảng bán hàng:

| Tình huống | Hành vi nên cân nhắc | Counter |
| --- | --- | --- |
| Đơn hàng đã hủy, chính sách không cần ghi | Processor trả `null` | `filterCount` tăng |
| Đơn hàng không thuộc kỳ dữ liệu | Processor trả `null` | `filterCount` tăng |
| Dòng CSV sai định dạng được policy cho bỏ qua | Reader ném exception có thể skip | `readSkipCount` tăng |
| Mã sản phẩm không hợp lệ, nghiệp vụ cho phép bỏ qua | Processor ném exception thuộc skip policy | `processSkipCount` tăng |
| Writer không thể ghi một item, lỗi thuộc skip policy | Lỗi writer được xử lý theo fault tolerance | `writeSkipCount` tăng |
| Database không truy cập được, lỗi không thuộc policy | Step thất bại, cần điều tra/restart | Không được mặc nhiên xem là skip |
| Writer thất bại tạm thời nhưng retry thành công | Retry rồi commit thành công | Không tính skip chỉ vì từng có exception |

**Quy tắc:** `return null` là cách lọc item có chủ đích; `throw` là báo lỗi. `skip` chỉ xảy ra khi step được cấu hình `faultTolerant()` và exception đáp ứng `skip(...)` hoặc `skipPolicy(...)` phù hợp. Không nên dùng skip cho mọi lỗi để ép job đạt `COMPLETED`; đặc biệt trong nghiệp vụ tiền tệ, skip có thể che mất dữ liệu quan trọng.

Ví dụ cấu hình giới hạn skip trong **Spring Batch 5.x**:

```java
new StepBuilder("importStep", jobRepository)
        .<Input, Output>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(RecoverableRecordException.class)
        .skipLimit(10)
        .build();
```

`Input`, `Output` và `RecoverableRecordException` là các kiểu do ứng dụng định nghĩa. Với `skipLimit(10)`, tổng số skip thuộc cả ba pha read/process/write có thể đạt tối đa 10; lỗi có thể skip tiếp theo sẽ làm step thất bại. Đây là giới hạn **tổng skip**, không phải mỗi pha có một quota 10 riêng. `filterCount` không tiêu thụ quota skip.

## 9. Dùng `SkipListener` để tìm nguyên nhân, không thay bộ đếm hệ thống

Counter cho biết **bao nhiêu** item bị bỏ qua; vận hành thường còn cần biết **vì sao**. `SkipListener` cung cấp callback theo ba pha:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class InvalidRecordListener implements SkipListener<String, String> {

    private static final Logger log =
            LoggerFactory.getLogger(InvalidRecordListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Skipped while reading: {}", error.toString());
    }

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        log.warn("Skipped while processing item={}: {}", item, error.toString());
    }

    @Override
    public void onSkipInWrite(String item, Throwable error) {
        log.warn("Skipped while writing item={}: {}", item, error.toString());
    }
}
```

Gắn bằng `.listener(new InvalidRecordListener())` ở step builder phù hợp. Ở pha read, reader có thể không tạo ra được một item, vì vậy callback chỉ nhận nguyên nhân lỗi; ở process và write, callback nhận thêm item. Khi log, không ghi toàn bộ dữ liệu nhạy cảm của bản ghi vào hệ thống giám sát.

`ItemReadListener.onReadError`, `ItemProcessListener.onProcessError` và `ItemWriteListener.onWriteError` là tín hiệu **có lỗi**, chưa đủ xác nhận item đã bị skip: lỗi có thể được retry thành công hoặc làm step thất bại. `SkipListener` phù hợp hơn để log những item đã thực sự bị bỏ qua. Tuy vậy, nguồn số liệu chính thống vẫn là `StepExecution` cùng metadata của `JobRepository`; tránh tự tăng một `AtomicLong` ở mỗi callback lỗi rồi gọi đó là `skipCount`, vì retry/rollback làm số callback có thể khác số item skip đã commit.

## 10. Xem counter sau khi chạy từ `JobExplorer`

Trong ứng dụng vận hành, service giám sát có thể đọc lịch sử các step từ `JobExplorer` bằng ID của job execution mà không cần giữ object ban đầu trong bộ nhớ:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class BatchStepMonitor {

    private final JobExplorer jobExplorer;

    public BatchStepMonitor(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepCounts> countsOfJobExecution(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId: " + executionId);
        }

        return execution.getStepExecutions().stream()
                .map(StepCounts::from)
                .toList();
    }

    public StepExecution findStep(long jobExecutionId, long stepExecutionId) {
        StepExecution step = jobExplorer.getStepExecution(
                jobExecutionId, stepExecutionId);
        if (step == null) {
            throw new IllegalArgumentException("Unknown step execution");
        }
        return step;
    }
}
```

Mã ví dụ dùng API Spring Batch 5.x và Java 17. Thực tế, DTO trả về dashboard nên có thêm `jobExecutionId`, `stepExecutionId`, `stepName`, `BatchStatus`, `ExitStatus` và thời điểm cập nhật để người vận hành biết các counter đang thuộc **lần chạy nào**. Phương thức `getJobExecution(...)` có thể trả `null` nếu ID không tồn tại.

Khi đang chạy, kết quả `JobExplorer` phản ánh **snapshot đã được repository lưu** tới thời điểm truy vấn; chunk hiện tại có thể chưa được commit, nên số liệu có độ trễ. Tần suất polling nên phù hợp với kích thước chunk, thời gian thực thi, tải database và nhu cầu dashboard.

## 11. Tra cứu trực tiếp bảng metadata `BATCH_STEP_EXECUTION`

Với `JobRepository` dùng JDBC và schema Batch mặc định, các counter thường nằm trong bảng `BATCH_STEP_EXECUTION`:

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    (READ_SKIP_COUNT + PROCESS_SKIP_COUNT + WRITE_SKIP_COUNT) AS TOTAL_SKIP,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`:jobExecutionId` là placeholder ở dạng named parameter (chẳng hạn khi dùng `NamedParameterJdbcTemplate`); khi chạy trực tiếp trong SQL client, thay bằng ID thật theo cú pháp mà công cụ hỗ trợ. Nếu hệ thống thay table prefix mặc định hoặc dùng loại repository khác, cần điều chỉnh cách truy vấn.

**Lưu ý:** metadata của job là dữ liệu vận hành quan trọng cho restart và theo dõi trạng thái. Không cập nhật các cột `READ_COUNT`, `WRITE_COUNT` hay `*_SKIP_COUNT` trực tiếp bằng SQL để “sửa báo cáo”. Thay đổi thủ công có thể làm sai lịch sử thực thi, che giấu lỗi và gây khó khăn khi điều tra.

Khi một job có nhiều step, nên hiển thị từng dòng theo **`JOB_EXECUTION_ID` + `STEP_EXECUTION_ID`**. `STEP_NAME` có thể giống nhau ở những lần chạy khác nhau nên không đủ làm khóa duy nhất cho dữ liệu giám sát.

## 12. Counter và Micrometer: hai loại chỉ số khác nhau

Spring Batch tích hợp Micrometer và cung cấp metric có tiền tố `spring.batch`, ví dụ:

| Metric được cung cấp | Loại metric | Đang đo gì? |
| --- | --- | --- |
| `spring.batch.job` | Timer | Thời gian chạy job |
| `spring.batch.step` | Timer | Thời gian chạy step |
| `spring.batch.item.read` | Timer | Thời gian thực hiện thao tác đọc item |
| `spring.batch.item.process` | Timer | Thời gian xử lý item |
| `spring.batch.chunk.write` | Timer | Thời gian viết chunk |

Những timer này hữu ích cho phân tích hiệu năng, nhưng **không đồng nghĩa** với `StepExecution.readCount`, `writeCount`, `filterCount` và `skipCount`. Chẳng hạn số mẫu timer `spring.batch.chunk.write` phản ánh số lần đo hoạt động ghi chunk, không phải số item được ghi thành công. Một lần ghi chunk có thể chứa 100 item, hoặc được thử lại sau lỗi.

Để đưa thống kê item lên dashboard Prometheus/Grafana hoặc hệ thống báo cáo khác, nên chọn rõ mục tiêu:

- **Báo cáo chính xác theo lần thực thi:** lấy các counter từ `StepExecution` hoặc `JobExplorer`, kèm ID/status/timestamp; xuất bản snapshot khi chunk commit hoặc khi step kết thúc theo thiết kế vận hành.
- **Theo dõi hiệu năng gần thời gian thực:** dùng Micrometer timers của framework cho duration và throughput gần đúng, kết hợp polling metadata với độ trễ có kiểm soát.
- **Phân tích nguyên nhân bỏ qua:** dùng `SkipListener` ghi lại thông tin tối thiểu về lỗi, mã lỗi và loại bản ghi; không dùng số lần callback làm tổng skip bền vững.

Nếu xuất metric tùy chỉnh, cần chú ý **cardinality** của tag. Đưa `jobExecutionId`, UUID item hoặc thông tin người dùng vào tag của mọi time series có thể khiến số lượng chuỗi tăng rất nhanh. Có thể lưu ID chi tiết trong log hoặc event store, còn metric tổng hợp theo tên job/step và loại kết quả.

## 13. Đọc số liệu trong lỗi, retry, rollback và restart

### Retry khác với skip

```text
Item X -> writer lần 1: timeout
       -> retry lần 2: thành công
       -> writeCount tăng theo item ghi thành công
       -> writeSkipCount không tăng do timeout đã được phục hồi
```

Với item Y lỗi không thể phục hồi nhưng được skip policy chấp nhận, `writeSkipCount` mới tăng khi framework quyết định skip. Không lấy số lỗi từ `ItemWriteListener.onWriteError` để suy ra số skipped items.

### Rollback có thể làm callback chạy nhiều lần

Nếu một chunk ghi lỗi, Spring Batch có thể rollback và xử lý lại các item, nhất là để phân biệt item nào có thể skip. `getRollbackCount()` là tín hiệu cần xem xét khi số lần log xử lý lớn hơn số item cuối cùng. Số lần gọi `process()` hoặc `write()` không tự chứng minh item đã được commit.

### Restart làm xuất hiện những `StepExecution` khác nhau

Ví dụ một `JobInstance` xử lý theo ngày nghiệp vụ có hai lần thực thi:

| Lần thực thi | Step status | `readCount` | `writeCount` | Giải thích |
| --- | --- | ---: | ---: | --- |
| `JobExecution 101` | `FAILED` | 500 | 450 | Step thất bại sau các chunk đã xử lý |
| `JobExecution 102` | `COMPLETED` | 550 | 545 | Restart xử lý tiếp theo trạng thái lưu được |

Không tự kết luận job đã đọc đúng 1.050 bản ghi **duy nhất** hoặc ghi 995 bản ghi **duy nhất** chỉ bằng cách cộng hai dòng. Tùy reader, checkpoint, transaction và hành vi writer, một số item có thể đã được thử lại; nghiệp vụ có thể cần đối chiếu theo khóa dữ liệu đầu ra. Nếu mục tiêu là thống kê mỗi lần chạy, giữ số liệu riêng cho từng `JobExecution`; nếu mục tiêu là tổng số bản ghi nghiệp vụ hoàn tất, cần một quy tắc tổng hợp tương thích với restart/idempotency của ứng dụng.

### Không phải step nào cũng có các bộ đếm item

Một tasklet chỉ gọi API hoặc chạy SQL tổng hợp có thể hoàn thành công việc nhưng có `readCount = writeCount = filterCount = skipCount = 0`, vì nó không xử lý qua chu trình `ItemReader` → `ItemProcessor` → `ItemWriter` chuẩn. Với tasklet đặc thù, số đối tượng nghiệp vụ đã cập nhật nên được đo bằng metric, log hoặc báo cáo riêng của ứng dụng; không nên gán ý nghĩa sai cho item counters mặc định.

## 14. Những tình huống gây hiểu sai khi giám sát

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `readCount > writeCount` dù không có lỗi | Processor đã filter một số item | Xem `filterCount` trước khi kết luận mất dữ liệu |
| `skipCount = 0` nhưng log có exception | Lỗi được retry thành công hoặc làm step thất bại; không có item được skip | Phân biệt error callback, retry, failure và skip policy |
| `readSkipCount > 0` nhưng `readCount` không tính dòng lỗi | `readCount` chỉ tính item đọc thành công | Đọc hai counter riêng; không coi readCount là tổng dòng vật lý |
| `writeCount` khác số dòng DB thay đổi | Một item writer có thể ghi nhiều dòng, ghi batch hoặc upsert | Dùng số liệu nghiệp vụ riêng nếu cần đếm database rows |
| Counter live tạm đứng yên | Chunk chưa commit hoặc snapshot repository chưa cập nhật | Quan sát thời điểm commit, `lastUpdated`, thời gian chunk và polling |
| Cùng một item xuất hiện nhiều lần trong log | Retry/rollback gọi lại reader/processor/writer | Dùng `StepExecution` cho tổng kết; thiết kế writer idempotent |
| `skipCount` cao nhưng step vẫn `COMPLETED` | Policy cho phép bỏ qua các lỗi đó trong giới hạn | Đánh giá ngưỡng chất lượng dữ liệu độc lập với batch status |
| Tổng counter của nhiều step bị đếm trùng | Một item đi qua nhiều step khác nhau | Báo cáo theo step hoặc định nghĩa rõ ý nghĩa phép tổng hợp |
| Sau restart, tổng đọc/ghi tăng khó hiểu | Có nhiều `JobExecution`/`StepExecution` | Gắn counter với execution ID và đối chiếu checkpoint |
| Dashboard chỉ thấy timer Micrometer | Metrics framework đo thời gian chứ không xuất mọi counter như số bản ghi thành công | Lấy counter từ metadata hoặc xuất thêm statistic riêng |

Khi cần đặt cảnh báo, nên xét đồng thời **trạng thái step, số skip, tỷ lệ filter, số item ghi, số lần rollback và số lượng đầu vào dự kiến**. Một job `COMPLETED` với `writeCount=0` có thể là kết quả hợp lệ khi không có dữ liệu, cũng có thể là lỗi cấu hình reader/filter; cần ngữ cảnh nghiệp vụ để phân biệt.

## 15. Tài liệu và phạm vi phiên bản

Ví dụ code trong bài chủ yếu dùng **Spring Batch 5.2.x**, Spring Framework 6.x và Java 17. Các getter item counter tiếp tục là khái niệm cốt lõi trong Spring Batch 6, nhưng một số package và chữ ký cấu hình step/chunk đã thay đổi; cần đối chiếu API của đúng phiên bản project trước khi sao chép import.

- [Spring Batch 5.2 Reference — Domain: `StepExecution`](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch 5.2 API — `StepExecution`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecution.html)
- [Spring Batch 5.2 API — `StepContribution`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepContribution.html)
- [Spring Batch 5.2 Reference — Chunk-oriented processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 Reference — Skip logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch 5.2 Reference — Intercepting step execution và listeners](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 API — `JobExplorer`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)
- [Spring Batch 5.2 Reference — Monitoring and metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)

Khi giám sát một Spring Batch step, hãy đọc `readCount`, `writeCount`, `filterCount` và ba loại skip từ **cùng một `StepExecution`**, kèm trạng thái và ID thực thi. `filter` cho biết dữ liệu được loại theo quy tắc bình thường, còn `skip` phản ánh lỗi được chấp nhận theo chính sách fault tolerance; retry, rollback và restart quyết định cách các con số cần được diễn giải. Sử dụng `afterStep` để ghi tổng kết, `JobExplorer` hoặc metadata SQL để đọc số liệu lịch sử, và Micrometer để quan sát hiệu năng. Khi tách rõ ba lớp này, dashboard có thể phản ánh cả **số lượng xử lý** lẫn **chất lượng xử lý** mà không nhầm số lần gọi phương thức với kết quả batch đã được ghi nhận.
