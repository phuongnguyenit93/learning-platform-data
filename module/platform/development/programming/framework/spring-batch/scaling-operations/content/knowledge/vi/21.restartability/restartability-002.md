# Restart chỉ partition lỗi trong Spring Batch

Khi xử lý hàng chục triệu bản ghi, một job có thể chia dữ liệu thành nhiều **partition** và chạy chúng song song trên nhiều luồng hoặc nhiều máy. Nếu ba partition đã xử lý xong nhưng partition thứ tư gặp lỗi, khởi động lại toàn bộ dữ liệu từ đầu vừa tốn tài nguyên vừa có nguy cơ gây tác dụng nghiệp vụ trùng lặp. Với **partitioning** và metadata bền vững của **Spring Batch**, một lần **restart đúng JobInstance** có thể chỉ chạy lại các partition chưa hoàn tất, trong khi giữ nguyên kết quả của những partition đã `COMPLETED`.

Bài học thuộc chương **Restartability** của module **SPRING_BATCH_SCALING_OPERATIONS**. Chủ đề gắn với mục tiêu mở rộng workload dữ liệu lớn qua partitioning và phân tán, đồng thời kiểm soát thread safety, retry/restart, nút thắt tài nguyên và cách vận hành job an toàn. Trọng tâm ở đây là **restart chỉ partition lỗi**; việc phục hồi từ checkpoint *bên trong* partition cũng được giải thích để tránh nhầm “chạy lại partition” với “xử lý lại toàn bộ dữ liệu partition”.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và `JobRepository` đối với restart partition.
2. Phân biệt restart một **JobInstance cũ** với chạy một **JobInstance mới**.
3. Mô tả cách `StepExecutionSplitter` chọn những partition cần chạy lại và cách manager tổng hợp trạng thái.
4. Thiết kế `Partitioner` tạo tên/phạm vi dữ liệu ổn định, dùng reader có checkpoint và writer idempotent.
5. Kiểm thử lỗi một partition, restart đúng lần chạy và xác minh partition đã thành công không bị thực thi lại.
6. Xử lý trường hợp khó trong vận hành: thay đổi input, crash đột ngột, remote worker, mất metadata, thay đổi `gridSize` hoặc triển khai phiên bản mã mới.

## 2. Tình huống thực tế: một partition lỗi, ba partition thành công

Job `invoiceImportJob` nhận một snapshot gồm bốn tệp hóa đơn độc lập và chia thành bốn partition:

| Partition logic | Dữ liệu sở hữu | Kết quả JobExecution lần 1 |
| --- | --- | --- |
| `file-001` | `invoices-001.csv` | `COMPLETED` |
| `file-002` | `invoices-002.csv` | `COMPLETED` |
| `file-003` | `invoices-003.csv` | `FAILED` do DB timeout |
| `file-004` | `invoices-004.csv` | `COMPLETED` |

Manager step không thể kết luận mọi partition đều thành công, nên job kết thúc `FAILED`. Sau khi xử lý nguyên nhân timeout, vận hành viên **restart cùng JobInstance**:

| Partition logic | JobExecution lần 2 | Vì sao? |
| --- | --- | --- |
| `file-001` | Không chạy lại | Partition trước đó đã `COMPLETED` |
| `file-002` | Không chạy lại | Partition trước đó đã `COMPLETED` |
| `file-003` | Được chọn chạy lại | Partition trước đó chưa `COMPLETED` |
| `file-004` | Không chạy lại | Partition trước đó đã `COMPLETED` |

Sau restart thành công, manager tổng hợp thông tin của **cả bốn** partition: ba partition hoàn tất ở lần đầu và một partition vừa phục hồi. Chỉ đếm `StepExecution` mới tạo trong lần 2 sẽ làm thống kê thiếu phần đã hoàn tất trước đó.

~~~mermaid
flowchart TD
    J["JobInstance invoiceImportJob<br/>snapshot=2026-11-25"]
    J --> E1["JobExecution #101<br/>FAILED"]
    E1 --> M1["invoiceManager"]
    M1 --> A1["invoiceWorker:file-001<br/>COMPLETED"]
    M1 --> B1["invoiceWorker:file-002<br/>COMPLETED"]
    M1 --> C1["invoiceWorker:file-003<br/>FAILED"]
    M1 --> D1["invoiceWorker:file-004<br/>COMPLETED"]
    J --> E2["JobExecution #102<br/>restart, same JobInstance"]
    E2 --> M2["invoiceManager"]
    M2 --> C2["invoiceWorker:file-003<br/>restart → COMPLETED"]
    A1 -.-> AG["Tổng hợp kết quả sau restart"]
    B1 -.-> AG
    D1 -.-> AG
    C2 --> AG
~~~

Sơ đồ thể hiện mô hình **partitioned step**; mỗi partition là một `StepExecution` được quản lý độc lập. Việc chỉ chạy lại `file-003` là hành vi bình thường **nếu** cấu hình restart, metadata và danh tính partition vẫn hợp lệ.

## 3. Điều kiện tiên quyết: restart đúng JobInstance

Spring Batch phân biệt ba đối tượng:

| Khái niệm | Ý nghĩa khi restart |
| --- | --- |
| `JobInstance` | Danh tính một đợt xử lý logic, được xác định bởi tên job và **identifying JobParameters** |
| `JobExecution` | Một lần cố gắng chạy của JobInstance; restart thường tạo **JobExecution mới** cho JobInstance cũ |
| `StepExecution` | Một lần chạy step; trong partitioning, mỗi partition được biểu diễn bởi một step execution có tên riêng |

Ví dụ job có identifying parameter `snapshot=2026-11-25`. Lần đầu lỗi, rồi lần sau muốn tiếp tục công việc chưa xong, phải chạy **cùng JobInstance**. Nếu tự ý tăng `run.id` (khi nó là identifying parameter) hoặc đổi `snapshot`, Spring Batch coi đó là **JobInstance khác**, không có lịch sử `COMPLETED` cũ để bỏ qua.

~~~text
invoiceImportJob(snapshot=2026-11-25)
    JobInstance #47
        JobExecution #101 FAILED
        JobExecution #102 COMPLETED  <-- restart

invoiceImportJob(snapshot=2026-11-26)
    JobInstance #48
        JobExecution #103 ...        <-- đợt dữ liệu mới, không phải restart #47
~~~

Các điều kiện thường cần thỏa:

- Job có thể restart: không bật `preventRestart()`/`restartable=false` và JobInstance chưa `COMPLETED`.
- Lần chạy trước có trạng thái cho phép restart như `FAILED` hoặc `STOPPED`; các trạng thái như `STARTED` bị treo sau crash cần được **xác minh và phục hồi theo quy trình vận hành** trước khi thử lại.
- `JobRepository` còn giữ lịch sử JobExecution, StepExecution và ExecutionContext; không xóa/truncate các bảng metadata giữa hai lần chạy.
- Tên worker step, tên partition và định nghĩa dữ liệu ổn định giữa các lần chạy của cùng JobInstance.
- Các reader/writer và side effect chịu được resume/retry; nếu partition đã commit một phần, lần chạy lại không được làm sai kết quả.

**Lưu ý:** Nếu workflow dùng transition `end()` khiến JobInstance có `BatchStatus.COMPLETED` dù step nào đó có lỗi, Spring Batch thông thường **không cho restart** JobInstance ấy. Cần thiết kế trạng thái job và điều kiện failure đúng từ đầu.

## 4. Spring Batch chọn partition cần restart bằng cách nào?

Các thành phần chính của **partitioning**:

- `PartitionStep` (manager): điều phối việc chia và tổng hợp kết quả.
- `Partitioner`: trả về `Map<String, ExecutionContext>`; mỗi key là **tên logic của partition**, còn context là đầu vào như tên tệp hoặc khoảng ID.
- `StepExecutionSplitter`, thường là `SimpleStepExecutionSplitter`: tạo/khôi phục các partition `StepExecution` cần chạy, dựa vào lịch sử trong `JobRepository`.
- `PartitionHandler`: thực thi hoặc phân phối các step executions (ví dụ `TaskExecutorPartitionHandler` cho chạy song song tại chỗ hoặc transport phù hợp cho remote partitioning).
- `JobRepository`: lưu trạng thái và checkpoint cho job/step/partition.

Luồng xử lý ở mức khái niệm:

~~~mermaid
flowchart TD
    A["Restart JobInstance cũ"] --> B["Tạo JobExecution mới"]
    B --> C["Manager partition step chạy"]
    C --> D["StepExecutionSplitter đối chiếu<br/>partition names + JobRepository"]
    D --> E{"Lần hoàn tất trước?"}
    E -->|COMPLETED| F["Bỏ qua partition<br/>dùng trạng thái đã lưu"]
    E -->|FAILED / STOPPED / chưa hoàn tất| G["Khôi phục trạng thái<br/>tạo StepExecution cần chạy"]
    G --> H["PartitionHandler chạy worker"]
    H --> I["Ghi metadata / checkpoint / status"]
    F --> J["Manager tổng hợp tất cả partition"]
    I --> J
~~~

Theo hợp đồng của `StepExecutionSplitter.split(...)`, **`gridSize` là gợi ý** cho việc phân vùng ở lần đầu; **khi restart**, splitter cần tái lập những partition từ lần lỗi trước và chỉ trả về tập cần chạy lại, nên gợi ý `gridSize` có thể bị bỏ qua.

Tên step execution thường có dạng:

~~~text
<workerStepName>:<partitionKey>

invoiceWorker:file-001
invoiceWorker:file-002
invoiceWorker:file-003
invoiceWorker:file-004
~~~

Ở ví dụ này, `file-003` là **key do Partitioner trả về**, còn tên metadata đầy đủ do Spring Batch ghép với tên worker step. Do đó, không nên đổi `invoiceWorker` thành `invoiceWorkerV2` hoặc đổi `file-003` thành `part-3` giữa hai lần chạy của cùng JobInstance mà chưa có kế hoạch di chuyển metadata.

### 4.1. “Chỉ partition lỗi” không đồng nghĩa chỉ xử lý lại các bản ghi lỗi

Một partition có thể xử lý 10.000 dòng theo chunk 200 bản ghi, commit 8.000 dòng rồi lỗi. Khi restart:

1. **Partition được chọn chạy lại** vì `BatchStatus` của nó chưa `COMPLETED`.
2. Nếu `ItemReader`/`ItemStream` lưu checkpoint đúng trong `ExecutionContext` và input không đổi, reader có thể tiếp tục từ **checkpoint đã commit** thay vì dòng đầu tiên.
3. Chunk đang xử lý khi crash thường có thể bị phát lại vì chưa commit; writer phải có ngữ nghĩa phù hợp để xử lý lại.
4. Nếu reader không lưu trạng thái, không khôi phục được checkpoint hoặc input thay đổi, partition có thể đọc lại từ đầu, xử lý sai hoặc cần khôi phục thủ công.

**Hai tầng phục hồi khác nhau:** Spring Batch chọn **partition cần chạy** dựa vào metadata step; bên trong partition, checkpoint quyết định **vị trí tiếp tục đọc**.

## 5. Tên partition và dữ liệu đầu vào phải ổn định

Đây là điều kiện quan trọng nhất với partitioner tùy biến.

### 5.1. Partition theo file

Với một snapshot có ba file bất biến:

| Key partition | `ExecutionContext` được cấp lần đầu |
| --- | --- |
| `file-001` | `inputFile=/data/snapshots/2026-11-25/invoices-001.csv` |
| `file-002` | `inputFile=/data/snapshots/2026-11-25/invoices-002.csv` |
| `file-003` | `inputFile=/data/snapshots/2026-11-25/invoices-003.csv` |

Key phải xác định theo **danh tính logic ổn định** của file, không theo thứ tự tình cờ của `File.listFiles()` hoặc số thứ tự tùy thuộc `gridSize`. Input snapshot nên bất biến trong suốt vòng đời JobInstance.

Ví dụ sai:

~~~java
// Không phù hợp nếu danh sách/thứ tự file thay đổi trước restart.
int i = 0;
for (File file : inputDirectory.listFiles()) {
    partitions.put("partition" + i++, contextFor(file));
}
~~~

Nếu ngày đầu `partition1` trỏ tới `A.csv` nhưng ngày sau cùng key trỏ tới `B.csv`, cơ chế skip theo tên có thể vô tình bỏ qua công việc mới hoặc gắn checkpoint cũ vào dữ liệu khác.

Thiết kế an toàn: ghi snapshot/manifest cố định, lấy tên partition từ ID ổn định của từng phần dữ liệu và giữ nội dung đầu vào bất biến. File mới đến sau khi job lỗi nên thuộc JobInstance mới hoặc phải được xử lý theo quy trình bổ sung có chủ đích.

### 5.2. Partition theo khoảng ID

Nếu chia khoảng `[1..100000]`, `[100001..200000]`, v.v., tránh tính lại ranh giới dựa trên `MAX(id)` tại thời điểm restart khi dữ liệu liên tục phát sinh. Ví dụ:

~~~text
partition-0001 -> minId=1       maxId=100000
partition-0002 -> minId=100001  maxId=200000
partition-0003 -> minId=200001  maxId=300000
~~~

Phạm vi cần được xác định từ snapshot hoặc mốc dữ liệu đã cố định trong lần đầu. Query reader phải giới hạn đúng phạm vi đã cấp, có ordering ổn định và chính sách nhất quán đối với record thay đổi trong lúc xử lý.

### 5.3. `PartitionNameProvider` để tối ưu restart

Spring Batch có interface tùy chọn `PartitionNameProvider`. Nếu `Partitioner` triển khai interface này, khi restart splitter có thể gọi `getPartitionNames(int gridSize)` để lấy **tên** thay vì bắt partitioner tính lại mọi `ExecutionContext` tốn kém; context của partition cũ được khôi phục từ metadata.

~~~java
// Phác họa interface; danh sách name phải giống key của partition(...).
public Collection<String> getPartitionNames(int gridSize) {
    return List.of("file-001", "file-002", "file-003");
}
~~~

Không dùng interface này như cơ chế sinh tên khác ở lần restart. Danh sách key phải trùng với partitioner đã dùng; đây là cách tối ưu việc truy vấn tên, **không phải cách để repartition** dữ liệu đã chạy.

## 6. Ví dụ Java: local partitioning có thể restart

Ví dụ sau minh họa **Spring Batch 5.2.x**. Có một manager step, một worker step và ba file đầu vào cố định. `invoiceWriter` là writer nghiệp vụ cần được cung cấp riêng; writer này phải ghi theo transaction và thực hiện idempotently (xem mục 7). Ví dụ tập trung vào cấu hình partition và reader checkpoint.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class InvoicePartitionConfig {

    @Bean
    public Partitioner invoicePartitioner() {
        // Snapshot cố định. Trong thực tế tải manifest theo JobInstance.
        Map<String, String> files = new LinkedHashMap<>();
        files.put("file-001", "/data/snapshots/2026-11-25/invoices-001.csv");
        files.put("file-002", "/data/snapshots/2026-11-25/invoices-002.csv");
        files.put("file-003", "/data/snapshots/2026-11-25/invoices-003.csv");

        return gridSize -> {
            Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
            files.forEach((partitionName, inputFile) -> {
                ExecutionContext context = new ExecutionContext();
                context.putString("inputFile", inputFile);
                partitions.put(partitionName, context);
            });
            return partitions;
        };
    }

    @Bean
    @StepScope
    public FlatFileItemReader<String> invoiceReader(
            @Value("#{stepExecutionContext['inputFile']}") String inputFile) {
        return new FlatFileItemReaderBuilder<String>()
                .name("invoiceReader")
                .resource(new FileSystemResource(inputFile))
                .lineMapper((line, lineNumber) -> line)
                .saveState(true) // lưu vị trí đọc vào ExecutionContext
                .build();
    }

    @Bean
    public Step invoiceWorker(JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<String> invoiceReader,
            @Qualifier("invoiceWriter") ItemWriter<String> invoiceWriter) {
        return new StepBuilder("invoiceWorker", jobRepository)
                .<String, String>chunk(200, transactionManager)
                .reader(invoiceReader)
                .writer(invoiceWriter)
                // Không bật allowStartIfComplete(true) nếu muốn skip partition đã xong.
                .build();
    }

    @Bean
    public TaskExecutor partitionTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(3);
        executor.setThreadNamePrefix("invoice-partition-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step invoiceManager(JobRepository jobRepository,
            Partitioner invoicePartitioner,
            @Qualifier("invoiceWorker") Step invoiceWorker,
            @Qualifier("partitionTaskExecutor") TaskExecutor executor) {
        return new StepBuilder("invoiceManager", jobRepository)
                .partitioner("invoiceWorker", invoicePartitioner)
                .step(invoiceWorker)
                .gridSize(3)
                .taskExecutor(executor)
                .build();
    }

    @Bean
    public Job invoiceImportJob(JobRepository jobRepository,
            @Qualifier("invoiceManager") Step invoiceManager) {
        return new JobBuilder("invoiceImportJob", jobRepository)
                .start(invoiceManager)
                .build();
    }
}
~~~

**Điều kiện để ví dụ chạy thực tế:** dự án cần Spring Batch, transaction manager, JobRepository, cấu hình bootstrap, tệp đầu vào tồn tại và bean `@Qualifier("invoiceWriter")` thực thi ghi dữ liệu thật. Cần khai báo ứng dụng và dependency phù hợp với phiên bản dự án. Đây là cấu hình khung, không phải ứng dụng khởi chạy độc lập.

Những điểm cần hiểu:

- `invoicePartitioner` dùng cùng các key `file-001`/`file-002`/`file-003` qua mọi lần chạy của JobInstance. `gridSize` được bỏ qua trong partitioner minh họa vì số file đã cố định.
- `@StepScope` tạo reader riêng theo **StepExecution/partition**, tránh chia sẻ vị trí đọc giữa worker threads; SpEL lấy đúng `inputFile` từ context của partition.
- `saveState(true)` cho phép reader ghi checkpoint trong metadata qua `ItemStream`. Reader phải có tên ổn định và job repository phải lưu được context.
- `ThreadPoolTaskExecutor` giới hạn concurrency tại đây là ba thread; tăng concurrency phải đi kèm kiểm tra DB pool, I/O, lock và writer thread safety.
- `invoiceManager` và `invoiceWorker` có tên step cố định. Không đặt `allowStartIfComplete(true)` ở worker nếu yêu cầu là chỉ restart partition chưa hoàn tất.
- `TaskExecutorPartitionHandler` chạy local threads; với remote partitioning, dùng `PartitionHandler` phù hợp để phân phối StepExecution, nhưng ngữ nghĩa chọn partition restart vẫn dựa trên metadata.

### 6.1. Thao tác restart đúng lần thực thi

Sau khi xác nhận JobExecution cũ có thể restart, dùng `JobOperator`:

~~~java
// Spring Batch 5.2.x, trong dịch vụ vận hành có inject JobOperator.
long previousExecutionId = 101L; // JobExecution đã FAILED/STOPPED
long restartedExecutionId = jobOperator.restart(previousExecutionId);

// new JobExecution ID, cùng JobInstance với previousExecutionId.
~~~

`JobOperator.restart(long)` nhận **JobExecution ID**, không nhận partition name và không có tham số “chạy file-003”. Framework dựa vào metadata để tự chọn partition cần chạy. Một cách khác là chạy lại cùng tên job cùng bộ **identifying parameters** với JobLauncher khi JobInstance trước đó ở trạng thái restartable. Không sử dụng tham số `run.id` mới hoặc `startNextInstance` nếu mục tiêu là phục hồi đợt cũ.

**Không nên tự chạy lẻ `invoiceWorker:file-003` bằng cách tạo JobInstance khác:** cách đó bỏ qua quan hệ manager/partition metadata và dễ làm mất tính nhất quán của tổng hợp hoặc checkpoint.

## 7. An toàn dữ liệu: checkpoint, transaction và idempotency

Khả năng bỏ qua partition `COMPLETED` **không đủ** để bảo đảm output đúng. Partition thất bại có thể đã commit dữ liệu một phần. Các tình huống thường gặp:

| Điểm lỗi trong partition | Điều gì đã bền vững? | Khi restart |
| --- | --- | --- |
| Trước commit chunk | DB transaction rollback, checkpoint chưa tiến | Chunk chưa commit có thể được xử lý lại |
| Sau commit chunk nhưng trước chunk tiếp theo | Dữ liệu chunk cũ và checkpoint đã lưu (nếu phối hợp đúng) | Đọc tiếp từ checkpoint đã commit |
| Ghi API ngoài transaction rồi xảy ra lỗi | Side effect bên ngoài có thể đã xảy ra | Có thể gọi lại; cần idempotency key/outbox |
| Ghi DB và cập nhật checkpoint không cùng ranh giới giao dịch | Dữ liệu và cursor có nguy cơ lệch | Cần sửa thiết kế transaction hoặc xử lý lặp an toàn |
| File nguồn đổi sau lần lỗi | Offset có thể trỏ sang record khác | Snapshot input bất biến hoặc phục hồi thủ công |

Mỗi lần cập nhật `ExecutionContext` chỉ có ý nghĩa khi writer và transaction tuân thủ semantics phù hợp. `saveState(true)` không biến mọi reader/writer thành exactly-once: việc gọi REST API hoặc cập nhật hệ thống khác vẫn phải có bảo đảm riêng.

### 7.1. Ví dụ SQL ghi idempotent

Giả sử mỗi hóa đơn có `invoice_id` duy nhất, lần chạy lại có thể ghi lại **cùng kết quả** an toàn:

~~~sql
CREATE TABLE invoice_totals (
    invoice_id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- PostgreSQL: gán kết quả xác định thay vì cộng dồn.
INSERT INTO invoice_totals (invoice_id, amount)
VALUES (:invoice_id, :amount)
ON CONFLICT (invoice_id) DO UPDATE
SET amount = EXCLUDED.amount,
    processed_at = now();
~~~

Ngược lại, phép `UPDATE balance = balance + :amount` sẽ cộng lặp nếu một item được xử lý lần thứ hai. Với side effect không thể thực hiện lại (thu tiền, phát email, gọi API đối tác), cần idempotency key bền vững ở đích, transaction/outbox hoặc cơ chế đối soát.

Một writer idempotent giúp hệ thống an toàn hơn khi chunk chưa commit bị gửi lại, metadata bị phục hồi hoặc khi một worker remote gặp lỗi mà trạng thái hoàn thành chưa được ghi nhận kịp.

### 7.2. Mỗi partition có checkpoint riêng

`FlatFileItemReader` là stateful. Nếu nhiều partition dùng **cùng instance reader mutable** hoặc tài nguyên StepScope không hoạt động như mong muốn, cursor có thể bị ghi đè giữa các thread. `@StepScope` giải quyết việc tạo instance theo StepExecution; vẫn cần kiểm tra writer/processor và mọi state dùng chung.

Trong môi trường phân tán, worker không được dùng file cục bộ chỉ có ở một node nếu partition có thể được retry trên node khác. Tệp cần được truy cập từ storage chung, hoặc được tải theo manifest có checksum. Dữ liệu đầu vào nên bất biến, có phiên bản và có thể đọc lại sau sự cố.

## 8. Tình huống khiến “chỉ restart partition lỗi” không hoạt động

| Tình huống | Triệu chứng | Cách khắc phục |
| --- | --- | --- |
| Chạy job với identifying `run.id` mới | Tất cả partition chạy như đợt mới | Restart cùng JobInstance/JobExecution cũ |
| Mất `BATCH_STEP_EXECUTION` hoặc `BATCH_STEP_EXECUTION_CONTEXT` | Không nhận diện được partition đã hoàn tất hoặc thiếu checkpoint | Bảo vệ/backup JobRepository; không xóa metadata khi còn job có thể restart |
| Partitioner đổi key theo thứ tự file | Partition bị skip sai hoặc nhận input không đúng | Cố định manifest, tên và mapping partition |
| Đổi tên worker step khi nâng phiên bản | Không khớp `StepExecution` cũ | Giữ identity qua restart, lên kế hoạch migration |
| Bật `allowStartIfComplete(true)` cho worker | Partition đã hoàn tất có thể được chạy lại | Giữ mặc định `false` nếu không có yêu cầu chạy lại |
| Đặt `startLimit(1)` | Partition lỗi có thể bị từ chối lần chạy tiếp theo | Đặt giới hạn phù hợp với chính sách restart |
| Job bị `COMPLETED` do flow `end()` | JobInstance không cho restart | Dùng transition `fail()`/`stop()` phù hợp với nghiệp vụ |
| Crash cứng làm metadata còn `STARTED`/`UNKNOWN` | Không thể restart an toàn ngay | Xác nhận worker đã dừng, đối soát output, phục hồi metadata theo thủ tục hợp lệ |
| Thay đổi dữ liệu nguồn sau thất bại | Checkpoint không còn chỉ đúng item | Giữ snapshot đầu vào bất biến |
| Retry remote mà writer không idempotent | Ghi lặp dù partition name đúng | Thiết kế output và side effect có thể chạy lại |

### 8.1. `allowStartIfComplete` có tác động cụ thể nào?

Mặc định, step đã `COMPLETED` thường được bỏ qua khi restart. Đặt `allowStartIfComplete(true)` ở worker step **cho phép** splitter chọn chạy lại partition đã hoàn tất. Đây là thiết lập có mục đích cho một số bước cần chạy lại; nó làm thay đổi chính sách “chỉ partition lỗi”.

Nếu **manager step** đã `COMPLETED` ở lần trước nhưng một step khác sau đó lỗi, restart job thường bỏ qua toàn bộ manager step. Không được kết luận “partitioning không restart” trong trường hợp này: đơn giản là partitioned step đã thành công và không cần chạy lại.

### 8.2. `gridSize` không phải công cụ sửa partition lỗi

Giả sử lần đầu dùng `gridSize=16` và một số partition lỗi. Đổi thành `gridSize=8` trong lần restart **không có nghĩa** Spring Batch gộp lại 8 partition hoặc tính lại biên dữ liệu: splitter có thể bỏ qua hint grid size khi khôi phục tập partition cũ.

Nếu cần thay đổi cách chia shard để tối ưu hiệu năng, nên áp dụng với **JobInstance mới** trên snapshot mới, hoặc có quy trình migration rõ ràng. Không dùng thay đổi partition count để “reset” lỗi restart.

## 9. Local partitioning và remote partitioning: điểm chung, điểm khác

| Tiêu chí | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Thực thi worker | Nhiều thread trong cùng tiến trình | Worker trên nhiều JVM/container/node |
| Partition identification | Tên worker step + partition key | Cùng nguyên tắc |
| Nguồn sự thật cho restart | `JobRepository` | `JobRepository`, cần được worker/manager truy cập hoặc tích hợp nhất quán |
| Phục hồi sau lỗi | Thread/step fail, local manager theo dõi | Ngoài lỗi step còn có lỗi broker, mạng, worker crash, reply trễ |
| Input | Có thể đọc ổ đĩa chung cùng máy | Cần file/object storage/database có thể truy cập giữa node |
| Idempotency | Cần cho retry/checkpoint | Càng quan trọng do trạng thái hoàn thành có thể không đồng bộ tức thời |

Spring Batch cung cấp metadata partition để hỗ trợ restart độc lập với việc thực thi local hay remote, nhưng transport tùy biến vẫn phải thực hiện đúng hợp đồng `PartitionHandler` và cập nhật trạng thái nhất quán. Trong remote partitioning, “worker đã ghi xong” và “manager đã biết worker xong” là **hai sự kiện khác nhau**. Nếu response mất hoặc trạng thái báo sai, phải đối soát metadata và output trước khi phát lại.

Không khẳng định “chỉ partition lỗi” nghĩa là exactly-once trên toàn hệ thống. Framework giúp tránh cố ý chạy lại partition đã hoàn tất; tác dụng nghiệp vụ vẫn cần transaction và idempotency.

## 10. Quan sát metadata để quyết định restart

Spring Batch lưu thông tin trong các bảng metadata, thường bao gồm:

- `BATCH_JOB_INSTANCE`: danh tính JobInstance.
- `BATCH_JOB_EXECUTION`: trạng thái từng lần chạy job.
- `BATCH_STEP_EXECUTION`: `STEP_NAME`, `STATUS`, `READ_COUNT`, `WRITE_COUNT`, thời gian và thông tin lỗi cho manager/worker.
- `BATCH_STEP_EXECUTION_CONTEXT`: checkpoint/state từng StepExecution.

Truy vấn **chỉ đọc** minh họa với schema metadata mặc định:

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS job_status,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS step_status,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
JOIN BATCH_STEP_EXECUTION se
    ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = :jobName
  AND ji.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY je.JOB_EXECUTION_ID, se.STEP_NAME;
~~~

Khi kiểm tra `invoiceWorker:file-003`, cần nhìn **cả lịch sử JobExecution của cùng JobInstance**: một partition có StepExecution `FAILED` ở lần đầu và StepExecution `COMPLETED` ở lần sau. Tổng hợp chỉ trong một JobExecution sẽ không kể đủ các partition đã hoàn tất ở lần cũ.

Không sửa trực tiếp các bảng `BATCH_*` như một cách “đánh dấu xong” khi gặp lỗi. Nếu trạng thái không nhất quán, cần phân tích nguyên nhân, xác nhận không còn worker đang chạy, đối soát side effect và thực hiện quy trình recovery có kiểm soát.

### 10.1. Các chỉ số nên theo dõi

| Chỉ số | Giúp trả lời câu hỏi |
| --- | --- |
| Số partition `COMPLETED`/`FAILED`/`STOPPED` | Còn bao nhiêu việc cần phục hồi? |
| Lần cuối một partition commit/checkpoint | Phần dữ liệu nào có thể cần xử lý lại? |
| Read/write/skip/retry count theo partition | Partition nào có bất thường hoặc lỗi dữ liệu? |
| Thời gian từng partition, p95/p99 | Có skew hoặc shard quá lớn làm chậm cả job? |
| DB pool, lock wait, CPU, memory, I/O | Restart nhiều partition có làm quá tải đích? |
| Broker queue backlog và số worker sống | Có remote partition bị thất lạc/phản hồi trễ? |

Khi restart chỉ một partition, tổng thời gian job có thể giảm mạnh so với chạy lại mọi partition; nhưng không nên kỳ vọng thời gian luôn tỉ lệ với số partition vì partition lỗi có thể là shard lớn nhất hoặc nút thắt nằm ở DB/I/O.

## 11. Kiểm thử thực chiến: chứng minh chỉ partition lỗi chạy lại

Thiết lập ba file bất biến tương ứng `file-001`, `file-002`, `file-003`, mỗi file có số hóa đơn và kết quả kiểm tra được. Gắn log `jobExecutionId`, `stepExecutionId`, `stepName` cho từng partition.

**Kịch bản chính:**

1. Cho job chạy với một identifying parameter cố định, ví dụ `snapshot=2026-11-25`.
2. Chủ động tạo lỗi nhất thời tại `file-002` **sau khi ít nhất một chunk đã commit**. Để `file-001` và `file-003` hoàn tất.
3. Kiểm tra `invoiceManager`/job `FAILED` và metadata từng worker: hai `COMPLETED`, một `FAILED`.
4. Khắc phục nguyên nhân lỗi, giữ nguyên input, tên partition và JobParameters nhận diện.
5. Dùng `JobOperator.restart(failedExecutionId)`; quan sát JobExecution mới thuộc JobInstance cũ.
6. Xác minh ở lần mới chỉ xuất hiện **worker StepExecution cần phục hồi** (trong tình huống này: `invoiceWorker:file-002`). Hai partition `COMPLETED` trước đó không tăng số lần thực thi nghiệp vụ.
7. Đối soát tổng output cuối cùng, checkpoint của `file-002` và không có hóa đơn nhân đôi.

Kỳ vọng khi đếm **các lần worker step được thực thi**:

| Partition | Lần 1 | Restart lần 2 | Tổng lần được thực thi |
| --- | --- | --- | --- |
| `file-001` | 1 lần, thành công | 0 | 1 |
| `file-002` | 1 lần, thất bại | 1 lần, thành công | 2 |
| `file-003` | 1 lần, thành công | 0 | 1 |

Giá trị “2” ở `file-002` là **hai lần thử thực thi partition**, không có nghĩa mỗi item bị ghi hai lần. Checkpoint có thể giúp tiếp tục phần chưa commit.

**Thử nghiệm bổ sung cần có:**

| Tình huống | Kỳ vọng/điều cần xác minh |
| --- | --- |
| Restart khi job đã `COMPLETED` | Không tạo job restart thông thường; nhận lỗi phù hợp |
| Đổi identifying `run.id` | Tạo JobInstance mới; minh chứng khác với restart |
| Đổi `gridSize` khi restart | Không kỳ vọng chia lại partition đã có |
| Đổi thứ tự file trả về từ filesystem | Key/manifest vẫn giữ mapping ổn định |
| Worker crash ngay trước và ngay sau commit | Output đúng, checkpoint hợp lệ, retry an toàn |
| Remote worker mất kết nối sau khi ghi DB | Không tạo side effect lặp khi khôi phục |
| Bật `allowStartIfComplete(true)` có chủ đích | Kiểm chứng chính sách chạy lại khác mặc định |
| Input thay đổi giữa hai lần thử | Phát hiện bất biến snapshot bị vi phạm và ngừng phục hồi |

Với kiểm thử integration, nên dùng `JobRepository` bền vững và dữ liệu đầu ra thật có thể đối soát. Test chỉ mock một `Partitioner` trả về vài key nhưng không restart qua hai `JobExecution` không chứng minh được yêu cầu này.

## 12. Checklist vận hành trước khi bấm Restart

- **Xác định đúng JobInstance:** kiểm tra tên job, identifying parameters và JobExecution lỗi gần nhất.
- **Ngăn chạy song song ngoài ý muốn:** xác nhận không có execution/worker cũ đang còn thực sự xử lý partition.
- **Đối soát metadata:** tên partition nào `COMPLETED`, `FAILED`, `STOPPED` hoặc đang không rõ trạng thái?
- **Bảo vệ input:** manifest, file, khoảng ID và version dữ liệu đúng với lần chạy trước.
- **Kiểm tra checkpoint:** reader/writer có lưu `ExecutionContext` phù hợp và transaction có giữ được nhất quán không?
- **Kiểm soát side effect:** DB upsert, unique key, outbox và API idempotency theo đúng nghiệp vụ.
- **Bảo đảm đủ tài nguyên:** worker concurrency, DB pool, network, I/O và thời gian timeout phù hợp.
- **Theo dõi sau restart:** chỉ partition cần phục hồi phát sinh step execution mới, job hoàn tất và dữ liệu cuối cùng được đối soát.

Nếu bất kỳ điều kiện nhận diện partition hoặc checkpoint nào không còn đáng tin cậy, không nên “ép chạy” bằng cách thay `run.id` hoặc chỉnh bảng metadata. Cần thiết kế một đợt **reprocess** riêng có đối soát, thay vì coi nó là restart an toàn.

## 13. Những hiểu nhầm thường gặp

| Nhận định | Đánh giá |
| --- | --- |
| “Một partition lỗi thì toàn bộ partition phải chạy lại.” | **Sai** với partitioning restart được cấu hình đúng: các partition `COMPLETED` được giữ nguyên. |
| “Đổi `run.id` để restart cho nhanh.” | **Sai** nếu đây là identifying parameter: đó là JobInstance mới. |
| “Đổi `gridSize` sẽ chia lại partition lỗi khi restart.” | **Sai**: splitter có thể khôi phục danh tính partition cũ và bỏ qua hint mới. |
| “Tên partition chỉ có tác dụng để hiển thị log.” | **Sai**: tên là khóa logic để đối chiếu StepExecution trong metadata. |
| “Restart một partition nghĩa là luôn đọc lại từ record đầu.” | **Không nhất thiết**: reader có checkpoint hợp lệ có thể tiếp tục từ chunk đã commit. |
| “Không có lỗi ghi trùng nếu Spring Batch skip partition thành công.” | **Sai**: partition lỗi có thể đã commit một phần và side effect ngoài transaction vẫn có thể bị lặp. |
| “`allowStartIfComplete(true)` giúp restart an toàn hơn.” | **Không mặc định**: có thể làm partition hoàn tất bị chạy lại, trái yêu cầu bài này. |
| “Remote partitioning được bảo đảm exactly-once ở mọi hệ thống bên ngoài.” | **Sai**: cần xét ranh giới giao dịch, metadata, transport và idempotency. |

## 14. Câu hỏi tự đánh giá

1. Một job có năm partition, bốn `COMPLETED` và một `FAILED`. Khi restart đúng JobInstance, worker step nào sẽ chạy lại? Manager tổng hợp read/write count ra sao?
2. Vì sao việc tạo thêm identifying parameter `run.id=2` có thể khiến job xử lý lại tất cả file?
3. `Partitioner` đặt key `partition0` cho một file khác sau khi danh sách thư mục đổi thứ tự. Hậu quả có thể là gì?
4. Partition đã commit 800/1.000 dòng trước khi lỗi. Cần điều kiện nào để restart chỉ đọc tiếp phần còn lại?
5. Khi nào nên dùng `PartitionNameProvider`? Interface này có cho phép thay đổi danh tính partition không?
6. Một remote worker đã ghi dữ liệu nhưng manager chưa nhận kết quả. Vì sao không nên kết luận ngay rằng worker chưa chạy?
7. Phân biệt tăng worker concurrency, thay `gridSize` và tạo JobInstance mới trong điều chỉnh kiến trúc vận hành.

**Gợi ý tự kiểm tra:** (1) Chỉ partition chưa hoàn tất phải chạy lại theo chính sách mặc định; kết quả manager bao gồm cả những partition đã hoàn tất trước đó. (2) JobInstance thay đổi. (3) Metadata và checkpoint gắn sai dữ liệu. (4) Input bất biến, ItemStream checkpoint bền vững, transaction và writer an toàn. (5) Tối ưu tra cứu tên, yêu cầu cùng key. (6) Side effect và báo nhận là hai sự kiện khác nhau. (7) Concurrency điều chỉnh khả năng xử lý, `gridSize` là hint cho chia partition, còn JobInstance mới là một đợt xử lý riêng.

## Tài liệu tham khảo

- [Spring Batch 5.2 Reference — Scaling and Parallel Processing / Partitioning](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cơ chế partition, manager/worker, restart và `PartitionNameProvider`.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): tài liệu phiên bản hiện hành; kiểm tra khác biệt API nếu nâng cấp từ Spring Batch 5.x.
- [Spring Batch 5.2 API — `SimpleStepExecutionSplitter`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/SimpleStepExecutionSplitter.html): dùng `JobRepository` và lịch sử để xác định partition cần chạy, `gridSize` khi restart.
- [Spring Batch 5.2 Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `startLimit` và `allowStartIfComplete`.
- [Spring Batch API — `JobOperator`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): `restart(executionId)` và các trạng thái cần thiết.

**Điểm cốt lõi:** “Restart chỉ partition lỗi” là sự phối hợp của **cùng JobInstance**, **metadata bền vững**, **tên partition ổn định**, **splitter chỉ chọn StepExecution cần chạy** và **checkpoint/idempotency**. Khi những điều kiện này được giữ đúng, có thể phục hồi nhanh job dữ liệu lớn mà không lãng phí nguồn lực chạy lại các partition đã hoàn tất và không làm sai kết quả nghiệp vụ.
