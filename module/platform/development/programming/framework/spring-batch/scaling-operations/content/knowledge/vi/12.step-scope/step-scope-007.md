# Placeholder input.fileName và late binding trong Spring Batch

## 1. Bài toán: tên tệp chỉ được biết khi job bắt đầu

Một hệ thống nhập dữ liệu theo ngày có thể phải đọc các tệp khác nhau:

~~~text
/data/import/customers-2026-11-24.csv
/data/import/customers-2026-11-25.csv
/data/import/customers-2026-11-26.csv
~~~

Nếu ghi cứng đường dẫn vào bean `FlatFileItemReader`, mỗi lần đổi tệp phải sửa cấu hình hoặc triển khai lại ứng dụng. Cách tốt hơn là để bên khởi chạy job cung cấp tên tệp qua **job parameter** có khóa `input.fileName`; reader chỉ lấy giá trị ấy khi một `StepExecution` bắt đầu.

Trong Spring Batch, biểu thức thường gặp là:

~~~java
@Value("#{jobParameters['input.fileName']}") String inputFileName
~~~

Đây là **late binding**: bean được định nghĩa khi Spring tạo application context, còn giá trị `input.fileName` được gắn vào bean ở thời điểm step thực thi. Bean cần được khai báo **`@StepScope`** (hoặc scope thích hợp khác) để cơ chế hoạt động đúng.

Bài học **“Placeholder input.fileName”** thuộc chương **Step scope** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán; vì vậy ta cần hiểu không chỉ cú pháp placeholder mà cả thread safety, retry/restart, worker service, đo nút thắt và tính đúng dữ liệu.

Sau bài học, bạn có thể:

- Viết chính xác `#{jobParameters['input.fileName']}` và hiểu từng phần của biểu thức.
- Phân biệt **placeholder thuộc tính Spring** `${input.fileName}` với **SpEL** `#{...}` lấy từ job/step context.
- Tạo reader `@StepScope` có tên, checkpoint và đường dẫn file lấy từ job parameter.
- Truyền `input.fileName` khi launch job, hiểu identifying parameters và restart.
- Chuyển từ một file cho một job sang một file cho mỗi partition bằng `stepExecutionContext`.
- Chẩn đoán lỗi thiếu tham số, file không tồn tại, file thay đổi khi restart và worker không truy cập được đường dẫn.

Ví dụ Java sử dụng **Java 17+, Spring Batch 5.x, Spring Boot 3.x**. Khi chuyển major version, cần kiểm tra lại API, import và cơ chế launch job của phiên bản đang dùng.

## 2. input.fileName là một tên khóa có dấu chấm

Phân tích cú pháp:

~~~java
@Value("#{jobParameters['input.fileName']}")
~~~

| Thành phần | Ý nghĩa |
|---|---|
| `@Value(...)` | Spring inject kết quả expression vào parameter hoặc field của bean |
| `#{...}` | Cú pháp Spring Expression Language (**SpEL**) |
| `jobParameters` | Các tham số thuộc job execution đang chạy, được Spring Batch expose trong scope |
| `['input.fileName']` | Truy cập **một key literal** tên chính xác `input.fileName` |
| `inputFileName` | Tên biến Java, không bắt buộc trùng key |

Dấu chấm trong `input.fileName` là **ký tự thuộc tên khóa**, không phải chỉ thị gọi property `fileName` trên đối tượng `input`. Cú pháp dùng dấu nháy bên trong dấu ngoặc vuông là lựa chọn rõ ràng:

~~~java
// Đúng: một key tên "input.fileName".
@Value("#{jobParameters['input.fileName']}") String fileName

// Không nên dùng để diễn tả key có dấu chấm:
// @Value("#{jobParameters.input.fileName}") String fileName
~~~

Những key như `input.fileName`, `input.fileFormat`, `import.businessDate` đều có thể tồn tại; tuy nhiên launcher, scheduler và worker phải thống nhất tuyệt đối chữ hoa/thường và dấu câu của key.

### Placeholder thuộc tính `${...}` khác SpEL `#{...}`

~~~java
// Đọc thuộc tính môi trường ứng dụng, như application.yml:
@Value("${input.fileName}") String configuredFile

// Đọc JobParameters riêng cho lần chạy batch:
@Value("#{jobParameters['input.fileName']}") String runtimeFile
~~~

| Biểu thức | Nguồn | Trường hợp phù hợp |
|---|---|---|
| `${input.fileName}` | Spring `Environment`: application.yml, system properties, environment variables... | Đường dẫn mặc định hoặc cấu hình **deployment** |
| `#{jobParameters['input.fileName']}` | `JobParameters` của lần chạy | Mỗi lần launch có thể chọn **file khác nhau** |
| `#{jobExecutionContext['input.fileName']}` | `JobExecutionContext` | File do một step trước chuẩn bị cho step sau |
| `#{stepExecutionContext['input.fileName']}` | `StepExecutionContext` | Mỗi step/partition được giao **file riêng** |

Một biểu thức SpEL có thể được Spring đánh giá trong quá trình tạo bean. Nếu bean được tạo quá sớm, **chưa có JobParameters của execution** để lấy. Vì vậy chỉ dùng đúng cú pháp `#{...}` là chưa đủ: bean phải được tạo đúng lúc.

## 3. Vai trò của @StepScope và thời điểm late binding

Bean `@Bean` thông thường có scope singleton, được tạo khi application context bắt đầu. `@StepScope` khai báo một **scoped proxy** để đối tượng thực chỉ được tạo khi có `StepExecution` đang hoạt động.

~~~mermaid
flowchart TD
    A[Spring Boot startup] --> B[Đăng ký Job, Step, scoped reader proxy]
    B --> C[JobLauncher chạy với JobParameters]
    C --> D[StepExecution bắt đầu]
    D --> E[StepScope tạo target reader]
    E --> F["SpEL tra khóa input.fileName"]
    F --> G[FlatFileItemReader mở tệp]
    G --> H[Đọc chunk và checkpoint]
    H --> I[Close reader, StepExecution kết thúc]
~~~

Ví dụ tối giản:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerRow> customerReader(
        @Value("#{jobParameters['input.fileName']}") String path) {
    return createCustomerReader(path);
}
~~~

`createCustomerReader` ở đây là hàm minh họa; phần sau thay bằng builder đầy đủ. Mỗi `StepExecution` có target reader riêng, nên các partition có thể sử dụng giá trị context khác nhau mà không phải chia sẻ một cursor toàn cục.

**`@StepScope` không tạo thêm thread.** Concurrency đến từ `TaskExecutor`, partition handler, parallel flow hoặc worker service. Ngược lại, nếu nhiều thread xử lý chung **một** `StepExecution`, `@StepScope` không tự làm `FlatFileItemReader` thread-safe; vẫn phải đánh giá cách truy cập cursor và checkpoint.

### Vì sao return type của bean quan trọng?

`FlatFileItemReader` cũng triển khai `ItemStream` và cần được gọi `open`, `update`, `close` để checkpoint/restart. Khi viết `@Bean`, nên trả về **kiểu cụ thể** (hoặc interface thể hiện đầy đủ `ItemStream`), thay vì chỉ `ItemReader<CustomerRow>`, để lifecycle được expose đúng qua proxy:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerRow> customerReader(/* ... */) {
    // ...
}
~~~

Đây không chỉ là vấn đề đẹp code. Khi stream lifecycle không được nhận diện đúng, một lần chạy có thể đọc dữ liệu nhưng **không lưu/khôi phục tiến độ** như mong đợi.

## 4. Ví dụ end-to-end: import CSV với input.fileName

Giả sử tệp CSV có header:

~~~csv
id,email
1001,a@example.org
1002,b@example.org
1003,c@example.org
~~~

Và bảng PostgreSQL đích:

~~~sql
CREATE TABLE customer_import (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);
~~~

### 4.1. Bean reader, writer, step và job

Đây là một class cấu hình Spring Batch 5.x. Ứng dụng phải cung cấp `JobRepository`, `PlatformTransactionManager`, `DataSource` và schema metadata Spring Batch tương ứng.

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class CustomerImportJobConfiguration {
    public record CustomerRow(long id, String email) {}

    @Bean
    @StepScope
    public FlatFileItemReader<CustomerRow> customerReader(
            @Value("#{jobParameters['input.fileName']}") String inputFileName) {

        if (inputFileName == null || inputFileName.isBlank()) {
            throw new IllegalArgumentException(
                    "Required job parameter: input.fileName");
        }

        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerReader")
                .resource(new FileSystemResource(inputFileName))
                .encoding("UTF-8")
                .strict(true)
                .linesToSkip(1) // Bỏ header "id,email"
                .delimited()
                .names("id", "email")
                .fieldSetMapper(fs -> new CustomerRow(
                        fs.readLong("id"),
                        fs.readString("email")))
                .saveState(true)
                .build();
    }

    @Bean
    public JdbcBatchItemWriter<CustomerRow> customerWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<CustomerRow>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO customer_import (id, email)
                    VALUES (:id, :email)
                    ON CONFLICT (id)
                    DO UPDATE SET email = EXCLUDED.email
                    """)
                .itemSqlParameterSourceProvider(row ->
                        new MapSqlParameterSource()
                                .addValue("id", row.id())
                                .addValue("email", row.email()))
                .build();
    }

    @Bean
    public Step importCustomersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<CustomerRow> customerReader,
            JdbcBatchItemWriter<CustomerRow> customerWriter) {

        return new StepBuilder("importCustomersStep", jobRepository)
                .<CustomerRow, CustomerRow>chunk(200, transactionManager)
                .reader(customerReader)
                .writer(customerWriter)
                .build();
    }

    @Bean
    public Job importCustomersJob(
            JobRepository jobRepository,
            Step importCustomersStep) {

        return new JobBuilder("importCustomersJob", jobRepository)
                .start(importCustomersStep)
                .build();
    }
}
~~~

Các điểm quan trọng:

1. Reader lấy tên file từ **`JobParameters` của execution đang chạy**, không phải biến môi trường hay field singleton.
2. `@StepScope` làm cho tham số `@Value` được đánh giá khi step thực thi; khi cấu hình `Step`, dependency chỉ là proxy.
3. `name("customerReader")` giúp `ItemStream` lưu checkpoint dưới một tên ổn định.
4. `strict(true)` khiến resource không mở được thành lỗi rõ ràng thay vì xử lý lặng lẽ 0 record.
5. `linesToSkip(1)` bỏ header CSV. Nếu file không có header, phải điều chỉnh.
6. `chunk(200)` giới hạn số item trong mỗi transaction/chunk, **không** tạo 200 thread.
7. SQL `ON CONFLICT` là cú pháp **PostgreSQL**; nó minh họa upsert lặp an toàn với cùng ID. Database khác cần cách upsert tương ứng.

Ứng dụng thật còn cần validation schema CSV, chính sách xử lý dòng hỏng, quyết định skip/retry và đối soát record. Upsert idempotent ở bảng này **không bảo đảm** các side effect khác (API, email, message broker) cũng idempotent.

### 4.2. Cung cấp tham số khi launch job

Dùng `JobParametersBuilder` để minh họa rõ ràng việc truyền key, không phụ thuộc cú pháp command-line của một phiên bản Spring Boot:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

// Trong method của service đã được inject JobLauncher và Job:
JobParameters parameters = new JobParametersBuilder()
        .addString("input.fileName",
                   "/data/import/customers-2026-11-26.csv", true)
        .addString("businessDate", "2026-11-26", true)
        .toJobParameters();

jobLauncher.run(importCustomersJob, parameters);
~~~

`true` trong `addString(..., true)` đánh dấu tham số **identifying**. Đoạn code được đặt bên trong method của service/command handler, còn `jobLauncher` và `importCustomersJob` là dependency được inject.

Nếu chủ động launch job bằng API/scheduler/code, thường dùng:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

để Spring Boot không tự chạy job lúc startup ngoài luồng điều phối dự kiến. **Đừng mặc định** tham số `--input.fileName=/path` trên command line trở thành một Spring Batch `JobParameter` trong mọi phiên bản hoặc cơ chế startup; nó có thể chỉ trở thành Spring `Environment` property. Hãy kiểm tra cách ứng dụng chuyển các argument vào `JobParameters`.

### 4.3. Identifying parameter và JobInstance

Spring Batch xác định `JobInstance` theo job name và **các identifying `JobParameters`**. Nếu đổi file là đổi tập dữ liệu, đánh dấu `input.fileName` identifying giúp mỗi file là một instance độc lập:

| Lần launch | `input.fileName` | `businessDate` | Kết quả về định danh |
|---|---|---|---|
| Lần 1 | `customers-2026-11-25.csv` | `2026-11-25` | Job instance cho ngày 25 |
| Lần 2 | `customers-2026-11-26.csv` | `2026-11-26` | Job instance khác |
| Restart lần 2 | `customers-2026-11-26.csv` | `2026-11-26` | Cùng identifying values, dùng metadata cũ theo lifecycle |

Nếu job instance đã `COMPLETED`, launch lại với identifying parameters cũ thường bị từ chối (ví dụ `JobInstanceAlreadyCompleteException`). Với instance thất bại, restart bằng cùng identifying parameters giúp framework dùng thông tin thực thi trước đó. Nếu tự thêm `run.id` mới, có thể vô tình tạo **job instance khác** và xử lý lại từ đầu.

**Đường dẫn giống nhau không bảo đảm dữ liệu giống nhau.** File có thể bị ghi đè dưới cùng một tên. Khi cần khôi phục chính xác, hãy chốt thêm checksum, file version, object generation hoặc snapshot key và kiểm tra chúng trước khi restart.

## 5. Cùng key input.fileName nhưng có ba phạm vi dữ liệu khác nhau

### 5.1. JobParameters: một file cho lần chạy

~~~java
@Value("#{jobParameters['input.fileName']}") String inputFileName
~~~

Dùng khi scheduler hoặc API chọn file ở lúc launch. Mọi step trong cùng job execution có thể truy cập parameter đó; worker service từ xa cũng cần metadata execution phù hợp để late bind.

### 5.2. JobExecutionContext: file do step trước tạo

~~~java
@Value("#{jobExecutionContext['input.fileName']}") String inputFileName
~~~

Giả sử `prepareInputStep` tạo snapshot và ghi đường dẫn vào **step context** của chính nó. `consumeInputStep` **không tự đọc được** key đó bằng `stepExecutionContext[...]`, vì hai step sở hữu hai context khác nhau. Có thể promote key bằng `ExecutionContextPromotionListener`:

~~~text
prepareInputStep:
  stepExecutionContext["input.fileName"] = "/data/snapshots/input-v3.csv"
  -- promotion --> jobExecutionContext["input.fileName"]

consumeInputStep:
  @Value("#{jobExecutionContext['input.fileName']}")
~~~

Phải đăng ký listener promotion vào step tạo dữ liệu và đặt thứ tự bước phù hợp. Không dùng `JobExecutionContext` như shared concurrent map để nhiều parallel step ghi liên tục; nếu cần manifest dùng chung, một record DB hoặc object store versioned thường dễ kiểm soát hơn.

### 5.3. StepExecutionContext: một file cho mỗi partition

~~~java
@Value("#{stepExecutionContext['input.fileName']}") String inputFileName
~~~

Đây là lựa chọn phù hợp khi **mỗi partition xử lý một file riêng**. Manager/`Partitioner` tạo các context khác nhau:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class FileListPartitioner implements Partitioner {
    private final List<String> immutableFiles;

    public FileListPartitioner(List<String> immutableFiles) {
        this.immutableFiles = List.copyOf(immutableFiles);
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> plan = new LinkedHashMap<>();
        for (int i = 0; i < immutableFiles.size(); i++) {
            ExecutionContext context = new ExecutionContext();
            context.putString("input.fileName", immutableFiles.get(i));
            plan.put("filePartition" + i, context);
        }
        return plan;
    }
}
~~~

`gridSize` không trực tiếp quyết định số partition trong ví dụ này: số entry bằng số file trong manifest bất biến. Production nên lấy danh sách file từ một manifest **ổn định trong suốt vòng đời job instance**, không quét lại một thư mục đang thay đổi rồi đánh số partition khác ở lúc restart.

Thay biểu thức của reader để lấy file của **đúng partition**:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerRow> partitionedCustomerReader(
        @Value("#{stepExecutionContext['input.fileName']}") String fileName) {

    if (fileName == null || fileName.isBlank()) {
        throw new IllegalArgumentException("Missing partition file name");
    }
    return new FlatFileItemReaderBuilder<CustomerRow>()
            .name("partitionedCustomerReader")
            .resource(new FileSystemResource(fileName))
            .linesToSkip(1)
            .delimited()
            .names("id", "email")
            .fieldSetMapper(fs -> new CustomerRow(
                    fs.readLong("id"), fs.readString("email")))
            .build();
}
~~~

Đây là **biến thể thay thế**, không phải bean dùng chung với `customerReader` trong cùng một step. `CustomerRow` là DTO/record ở ví dụ trước, cần import hoặc chuyển sang package dùng chung nếu đặt trong class khác.

**Cảnh báo:** nếu manager tạo 12 partition nhưng cả 12 reader vẫn lấy `#{jobParameters['input.fileName']}`, chúng có thể cùng đọc **toàn bộ cùng một file** và xử lý trùng. `@StepScope` giúp mỗi partition có reader riêng, **không tự chia ranh giới dữ liệu**. Ranh giới phải do partition plan hoặc reader đảm nhận.

### Tránh fallback âm thầm sang file chung

Một expression có thể chọn file ở step context khi có, rồi fallback về job parameter. Nhưng nếu mục tiêu là **mỗi partition một file**, fallback có thể che lỗi thiếu key trong dispatch và khiến nhiều worker xử lý file chung. Với tác vụ quan trọng, hãy **fail fast** nếu context của partition thiếu `input.fileName`.

## 6. Remote worker và đường dẫn tệp thực tế

Ở local partitioning, reader mở tệp trên filesystem của ứng dụng. Trong **remote partitioning**, target reader được tạo ở **worker process**; đường dẫn `input.fileName` phải truy cập được từ môi trường của worker, không chỉ máy manager.

~~~mermaid
flowchart LR
    S[Scheduler] -->|JobParameters| M[Manager]
    M -->|StepExecutionRequest| Q[(Broker)]
    Q --> W1[Worker A]
    Q --> W2[Worker B]
    W1 -->|Đọc input.fileName| FS[(Shared storage)]
    W2 -->|Đọc input.fileName| FS
    M <-->|Metadata| JR[(JobRepository)]
    W1 <-->|Metadata| JR
    W2 <-->|Metadata| JR
~~~

Manager chạy trên máy có `/home/me/customers.csv` không có nghĩa worker container cũng có file ở path đó. Một số mô hình phù hợp:

- **Shared volume:** mount dữ liệu ở một đường dẫn nhất quán, ví dụ `/data/import/...`, trên mỗi worker pod.
- **Object storage:** truyền object key/URI cùng version và dùng resource/adapter có khả năng tải/đọc đối tượng; `FileSystemResource` **không tự hiểu** URI như `s3://...`.
- **Manifest:** chia danh sách file/key thành từng partition ổn định, mỗi worker tự đọc phần được giao.
- **Staging step:** chuẩn bị snapshot tại nơi worker có quyền truy cập, ghi địa chỉ/version vào context rồi mới chạy step tiêu thụ.

Job parameter thường chỉ chứa **định danh nguồn**, không chứa bytes của file. Một tệp lớn trên shared volume cũng có thể tạo nút thắt I/O khi nhiều worker đọc đồng thời; cần đo storage throughput và read latency trước khi tăng pod.

### Bảo vệ khi tên tệp đến từ API

Nếu người gọi được truyền `input.fileName`, không nên mở bất kỳ path nào được nhập. Cần kiểm tra allowlist directory/prefix, quyền truy cập, extension/format, dung lượng, symlink/path traversal và resource ownership. Với object storage, áp IAM tối thiểu. Không lưu token, mật khẩu hoặc presigned URL nhạy cảm trong `JobParameters`/log nếu chúng có thể tồn tại lâu trong metadata.

## 7. Checkpoint và restart với tên tệp động

`FlatFileItemReader` triển khai `ItemStream`; khi xử lý chunk, framework điều phối việc đọc và lưu tiến độ vào `StepExecutionContext`. Một context có thể trông như:

~~~text
JobParameters:
  input.fileName = "/data/import/customers-2026-11-26.csv"

StepExecutionContext:
  customerReader.read.count = 400  (minh họa)
  ...                              (key nội bộ khác)
~~~

Không tự thay các key checkpoint do reader quản lý. Tên `customerReader` là một phần của cách lưu trạng thái; thay tên khi restart có thể khiến reader không tìm thấy checkpoint cũ.

Điều kiện phục hồi đáng tin cậy:

1. Launch lại **cùng JobInstance** bằng identifying `JobParameters` cũ khi execution lỗi.
2. Giữ nguyên file được tham chiếu **và nội dung/version của file**.
3. Giữ tên step, tên partition và tên `ItemStream` ổn định.
4. Bật lưu state và dùng lifecycle `open/update/close` đúng cách.
5. Đảm bảo định dạng CSV, encoding, header và thứ tự dòng không thay đổi.
6. Writer và side effect ngoài transaction phải có cơ chế idempotency.

Nếu file bị ghi đè dưới cùng path khi worker đã xử lý 400 dòng, dòng thứ 401 lúc restart có thể là record khác. Spring Batch **không tự xác minh checksum** nếu ứng dụng chỉ cung cấp tên file. Đối với dữ liệu quan trọng, lưu và kiểm tra checksum/version, hoặc chuyển input sang immutable snapshot.

### Retry và side effect

Trong ví dụ PostgreSQL, upsert theo `id` cho phép thực thi lại cùng record mà không sinh row trùng. Nhưng nếu một writer còn gửi event hoặc gọi API, việc transaction database commit và side effect bên ngoài có thể không nguyên tử. Cần idempotency key, transactional outbox hoặc cơ chế deduplication, không chỉ dựa vào checkpoint.

**Không đổi `input.fileName` giữa một `StepExecution` đang chạy** để reader tự chuyển sang file khác. Nếu muốn xử lý nguồn mới, hãy dùng một step/partition hoặc job instance được định danh và điều phối rõ ràng.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `inputFileName == null` | Job không có key `input.fileName` hoặc key viết sai chữ hoa/thường | Kiểm tra parameter launch và validate bắt buộc |
| `No context holder available for step scope` | Truy cập target bean ngoài `StepExecution` | Để framework chạy step hoặc dùng test scope utilities |
| `${input.fileName}` không đổi giữa các job | Đang đọc application property thay vì parameter theo lần chạy | Dùng `#{jobParameters['input.fileName']}` |
| SpEL key có dấu chấm đọc sai | Dùng property navigation thay vì literal key | Dùng `jobParameters['input.fileName']` |
| Reader không mở được tệp | File không tồn tại trên worker, thiếu quyền, sai mount | Kiểm tra mount/permission tại đúng worker process |
| Mọi partition đọc cùng file | Reader lấy parameter cấp job thay vì context riêng | Dùng `stepExecutionContext['input.fileName']` |
| Restart đọc sai vị trí | Input thay đổi, reader đổi tên, không lưu checkpoint | Chốt snapshot, giữ stream name, test restart |
| Job đã hoàn thành không chạy lại | Cùng identifying parameters với instance `COMPLETED` | Tôn trọng lifecycle hoặc tạo instance mới có chủ đích |
| Tăng worker nhưng throughput giảm | Storage/DB pool bị nghẽn hoặc file bị phân bố lệch | Đo I/O, JDBC wait, duration từng partition |

### Kiểm tra scoped bean bằng spring-batch-test

`StepScopeTestUtils` giúp kích hoạt scope trong test. Đây là **khung minh họa**, chưa phải test đầy đủ:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.scope.StepScopeTestUtils;

StepExecution execution = MetaDataInstanceFactory.createStepExecution();

StepScopeTestUtils.doInStepScope(execution, () -> {
    // Trong callback, lấy bean @StepScope từ ApplicationContext.
    // Muốn kiểm tra jobParameters['input.fileName'], hãy tạo JobExecution
    // với JobParameters có key đó và gắn StepExecution tương ứng.
    return null;
});
~~~

Để chứng minh reader thật sự bind đúng, test cần khởi tạo `JobExecution` có `JobParameters` thông qua factory/builder phù hợp, resolve scoped reader, mở file test, đọc record đầu và đóng stream. Bổ sung integration test với DB metadata và file thực, bao gồm kịch bản lỗi giữa chunk rồi restart.

## 9. Hiệu năng và quan sát khi scale Spring Batch

`@StepScope` giúp cô lập state, **không trực tiếp tăng throughput**. Số worker và năng lực I/O mới giới hạn tốc độ:

| Phạm vi | Chỉ số nên theo dõi | Câu hỏi |
|---|---|---|
| Job/step | `jobExecutionId`, `stepExecutionId`, duration, `readCount`, `writeCount`, rollbacks | Reader đã lấy đúng nguồn và đọc đủ chưa? |
| Partition | Tên partition, file key, số dòng, duration p95/p99 | Có file quá lớn làm job chờ partition chậm nhất? |
| Storage | Read latency, throughput, open file descriptors, error rate | Nhiều worker có bão hòa storage? |
| JVM | CPU, heap/GC, thread count, file handles | Có quá nhiều reader đồng thời? |
| Database | JDBC pool active/pending, SQL latency, lock wait | Writer/metadata DB có là bottleneck? |
| Nghiệp vụ | Record dự kiến, thành công, lỗi, trùng ID, input version | Restart có đúng dữ liệu không? |

Ví dụ có 40 file và 4 worker, manager có thể tạo 40 partition nhưng tối đa 4 partition thực thi cùng lúc nếu mỗi worker chỉ nhận một nhiệm vụ. Tăng lên 8 worker có thể tăng throughput **nếu** storage, DB và pool còn capacity; ngược lại, nhiều worker đọc từ một đĩa chậm có thể làm latency tăng.

Với **multi-threaded step** mà nhiều chunk cùng chia sẻ một reader trong một `StepExecution`, `FlatFileItemReader` không mặc định thread-safe. Thường nên tách thành các `StepExecution` độc lập theo file/range, hoặc thiết kế đồng bộ và checkpoint rất cẩn thận nếu không thể phân vùng.

### Runbook lỗi tên tệp trên production

1. Từ `jobExecutionId`, xem `JobParameters` có key `input.fileName` và giá trị nguồn nào; tránh log URI nhạy cảm.
2. Kiểm tra reader lấy từ **job parameter** hay **step execution context** theo thiết kế.
3. Xác minh file/object version, quyền truy cập và mount ở chính worker đang lỗi.
4. Khi restart, đối chiếu checksum/version và checkpoint của `ItemStream`.
5. Xác minh các partition không trùng file/range và đối soát số record trước khi phát lại.
6. Đo storage/DB wait trước khi tăng concurrency hoặc thay cấu hình pool.

## 10. Checklist áp dụng placeholder đúng

- [ ] Tên key khi launch là `input.fileName`, đúng chữ hoa/thường.
- [ ] Dùng `#{jobParameters['input.fileName']}` cho tham số theo lần chạy; không nhầm với `${input.fileName}`.
- [ ] Reader dùng `@StepScope`, kiểu trả về expose `ItemStream`, tên reader ổn định.
- [ ] Validation phát hiện key thiếu, path rỗng, file không mở được và sai định dạng.
- [ ] Partition theo file dùng `#{stepExecutionContext['input.fileName']}` với file riêng cho từng partition.
- [ ] Identifying parameters, manifest, input version và checkpoint nhất quán khi restart.
- [ ] Worker service thực sự truy cập được file ở môi trường của nó.
- [ ] Writer idempotent; side effect ngoài transaction có chống trùng.
- [ ] Log/metric theo execution/partition và định danh input không nhạy cảm.
- [ ] Đã thử file thiếu, header lỗi, worker chết giữa chunk và file bị thay đổi khi restart.

## 11. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — So sánh hai placeholder

Tạo `application.yml` chứa `input.fileName: /data/default.csv`, rồi launch job với `JobParametersBuilder.addString("input.fileName", "/data/actual.csv", true)`. Viết hai bean demo dùng `${input.fileName}` và `#{jobParameters['input.fileName']}`. Giải thích vì sao chúng đọc hai nguồn khác nhau.

### Bài tập 2 — Parameter không tồn tại

Launch job thiếu key `input.fileName`, sau đó viết sai thành `input.filename`. Quan sát lỗi và thêm validation rõ ràng ngay khi reader được tạo. Kiểm tra rằng job không báo hoàn tất giả tạo với 0 record.

### Bài tập 3 — Một file mỗi partition

Tạo manifest gồm sáu CSV độc lập. Dùng `FileListPartitioner` để tạo sáu `StepExecutionContext` với `input.fileName` riêng; thay expression ở reader và chạy lần lượt bằng hai rồi bốn worker. Đối soát không file nào bị thiếu hoặc xử lý trùng.

### Bài tập 4 — Restart theo checkpoint

Làm writer thất bại sau vài chunk. Restart với **cùng identifying `JobParameters`** và file bất biến, đối chiếu checkpoint và dữ liệu. Trong môi trường test riêng, thử sửa file dưới cùng path để giải thích vì sao không thể tin vào checkpoint nếu nguồn đã thay đổi.

### Bài tập 5 — Worker không thấy file

Giả sử manager dùng `/host/input/customers.csv` nhưng worker container chỉ mount `/mnt/data/customers.csv`. Thiết kế volume/path mapping hoặc object key dùng chung; thêm validation, phân quyền và log chẩn đoán an toàn.

**Tự kiểm tra:** Dấu chấm trong `input.fileName` mang ý nghĩa gì khi dùng `['...']`? Tại sao cần `@StepScope` khi SpEL đã đúng? Khác nhau giữa file name trong `JobParameters` và `StepExecutionContext` là gì? Vì sao restart phải giữ nguồn bất biến? Tại sao tăng từ hai lên tám worker không đảm bảo đọc file nhanh gấp bốn lần?

## 12. Kết luận

`input.fileName` là một khóa đầu vào điển hình cho late binding. `#{jobParameters['input.fileName']}` cho phép mỗi lần launch chọn file khác nhau mà không sửa cấu hình ứng dụng; kết hợp `@StepScope` giúp reader nhận giá trị đúng lúc `StepExecution` bắt đầu và giữ checkpoint riêng.

Khi scale, chọn **đúng phạm vi của placeholder**: `JobParameters` cho đầu vào toàn job, `JobExecutionContext` cho dữ liệu được chuẩn bị và chia sẻ giữa các step, `StepExecutionContext` cho đầu vào riêng từng partition. Tính đúng còn phụ thuộc **file bất biến khi restart, quyền truy cập của worker, vòng đời ItemStream, idempotency và giới hạn tài nguyên thực tế**; không placeholder hay scope nào tự bảo đảm những điều kiện này.
