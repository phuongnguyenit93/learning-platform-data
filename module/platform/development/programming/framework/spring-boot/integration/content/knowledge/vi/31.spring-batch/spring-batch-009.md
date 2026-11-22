# Checkpoint, ExecutionContext và khởi động lại công việc

## 1. Vì sao một batch job cần checkpoint?

Trong module **Spring Boot Integration**, không phải mọi luồng tích hợp đều cần phản hồi tức thời. Một số công việc phải nhập hàng triệu dòng CSV, đồng bộ dữ liệu từ API đối tác, đối soát giao dịch, tái tạo read model hoặc chuyển dữ liệu giữa cơ sở dữ liệu và broker. Những công việc này có thể chạy nhiều phút đến nhiều giờ, nên phải dự kiến trước chuyện ứng dụng bị dừng, database timeout, một bản ghi lỗi hoặc hạ tầng khởi động lại giữa chừng.

Ví dụ, công việc `importPaymentsJob` đọc tệp CSV có 100.000 dòng và ghi bản ghi đối soát vào PostgreSQL theo từng nhóm 100 dòng:

- Nếu tiến trình chết sau 64.700 dòng đã commit, ta không muốn thực hiện lại toàn bộ 64.700 dòng một cách mù quáng.
- Nếu lỗi xảy ra trong lúc đang ghi nhóm 64.701–64.800, nhóm đó phải có hành vi rollback/retry xác định.
- Nếu job được khởi động lại, nó cần biết **cùng một lần xử lý logic** đang ở đâu, những bước nào hoàn tất và trạng thái đã được lưu bền vững nào có thể tin cậy.

**Spring Batch** giải quyết vấn đề này bằng `JobRepository`, metadata của `JobExecution`/`StepExecution`, cơ chế `ExecutionContext` và checkpoint theo transaction. Cần hiểu rằng **checkpoint chỉ giúp khôi phục tiến độ**, còn tránh trùng lặp side effect và bảo đảm nhất quán giữa hai hệ thống vẫn đòi hỏi idempotency, transaction và đôi khi transactional outbox.

~~~mermaid
flowchart LR
    A["CSV input bất biến"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E[("PostgreSQL dữ liệu nghiệp vụ")]
    F[("JobRepository metadata")] <-->|"Job/Step status + ExecutionContext"| B
    F -. "Checkpoint mỗi chunk đã commit" .-> E
~~~

## 2. Hiểu đúng JobInstance, JobExecution, StepExecution và JobRepository

Các khái niệm liên quan chặt chẽ nhưng **không thể dùng thay thế**:

| Thành phần | Ý nghĩa | Vai trò khi restart |
| --- | --- | --- |
| `Job` | Định nghĩa luồng các `Step` cần chạy. | Cùng cấu hình job có thể xử lý nhiều lô nghiệp vụ. |
| `JobParameters` | Các tham số của lần chạy; một số là **identifying**, một số không. | Các identifying parameter cùng với tên job xác định `JobInstance`. |
| `JobInstance` | Một lần xử lý **logic** của một job với tập identifying parameters. | Restart chạy tiếp **cùng JobInstance** khi đủ điều kiện. |
| `JobExecution` | Một **attempt thực thi** của JobInstance, có thời gian, trạng thái và lỗi riêng. | Mỗi lần restart thường tạo JobExecution mới. |
| `StepExecution` | Một attempt thực thi của step, chứa trạng thái và số liệu read/write/skip/commit/rollback. | Spring Batch dùng metadata để biết step nào cần chạy lại. |
| `ExecutionContext` | Map key-value được framework lưu bền vững cho job hoặc step. | Lưu vị trí đọc và trạng thái cần thiết để tiếp tục. |
| `JobRepository` | Thành phần lưu/đọc metadata batch, thường qua JDBC trong database. | Là điểm tham chiếu trạng thái restart qua process khác. |

**Công thức nhận diện quan trọng**:

~~~text
JobInstance = jobName + identifying JobParameters

JobInstance 1
  ├── JobExecution #101: FAILED
  │     └── StepExecution importStep #501: FAILED
  └── JobExecution #102: COMPLETED (restart)
        └── StepExecution importStep #502: COMPLETED
~~~

Trong Spring Batch 5.x, metadata JDBC thường nằm trong các bảng như `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`. Không sửa trực tiếp bảng metadata để “ép” chạy lại trừ khi có quy trình vận hành và hiểu rõ hậu quả; nên dùng API `JobLauncher`, `JobOperator` và công cụ quản trị thích hợp.

### 2.1. Restart khác chạy một JobInstance mới

Giả sử job có `businessDate=2026-11-21` và `sourceId=bank-A-20261121` là identifying parameters:

- Lần đầu chạy thất bại: `JobExecution #101 = FAILED`.
- Chạy lại **cùng tên job và cùng identifying parameters** sau khi lỗi được xử lý: framework có thể tạo JobExecution mới **trong cùng JobInstance** và khôi phục trạng thái.
- Đổi `sourceId` hoặc thêm identifying parameter mới như `run.id=2`: tạo **JobInstance khác**, thường bắt đầu từ đầu, không phải restart.
- Gọi lại cùng JobInstance đã `COMPLETED` thường bị từ chối bằng `JobInstanceAlreadyCompleteException`, trừ khi chính sách/lifecycle bước cho phép trường hợp khác được cấu hình rõ.

Điều này giải thích vì sao dùng `RunIdIncrementer` hoặc tự thêm timestamp mới vào identifying parameters **mỗi lần retry** sẽ phá mục tiêu resume: framework xem đó là lô mới. Nếu cần xử lý một phiên bản dữ liệu mới, hãy đặt version/source ID tương ứng làm identifying parameter có chủ đích.

## 3. Checkpoint trong chunk-oriented processing hoạt động thế nào?

Với một `Step` dạng chunk:

1. `ItemReader` đọc lần lượt các item.
2. `ItemProcessor` biến đổi/kiểm tra (có thể trả `null` để lọc).
3. `ItemWriter` ghi một `Chunk` item đã xử lý.
4. Transaction của chunk commit; metadata step và `ExecutionContext` được cập nhật ở ranh giới checkpoint theo cấu hình.
5. Nếu lỗi trước commit, những thay đổi **thuộc cùng transaction** sẽ rollback; khi restart, reader có khả năng bắt đầu từ checkpoint trước đó.

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant DB as Database
    participant Repo as JobRepository
    Note over R,Repo: Chunk size = 100
    loop Đọc tối đa 100 item
        R->>P: read + process
    end
    P->>W: Chunk đã xử lý
    W->>DB: Ghi dữ liệu trong transaction
    R->>Repo: ItemStream.update(ExecutionContext)
    Repo->>Repo: Lưu StepExecution/ExecutionContext
    Note over DB,Repo: Commit theo transaction manager
    DB-->>W: Transaction commit
    Note over R,Repo: Checkpoint bền vững nếu commit thành công
~~~

**Checkpoint không nhất thiết bằng đúng số dòng nguồn đã đọc.** Bộ đếm `readCount`, `writeCount` và `filterCount` có thể khác nhau, đặc biệt khi processor lọc bản ghi hoặc có skip/retry. Reader có thể lưu **vị trí đọc** (số item, page, cursor key...), trong khi writer lưu số bản ghi đã ghi. Nếu dùng chunk size 100, checkpoint thường ở mỗi chunk commit, nhưng chi tiết phụ thuộc vào item stream, reader, transaction manager và chính sách fault tolerance.

### 3.1. Tình huống crash khi xử lý chunk

Giả sử đã commit 10 chunk, mỗi chunk 100 dòng:

| Thời điểm lỗi | Dữ liệu bền vững kỳ vọng | Khi restart |
| --- | --- | --- |
| Sau khi chunk 10 commit thành công | 1.000 dòng và checkpoint sau chunk 10. | Đọc tiếp gần vị trí dòng 1.001 theo trạng thái reader. |
| Trong quá trình xử lý chunk 11, trước commit | 1.000 dòng; ghi JDBC của chunk 11 trong transaction phải rollback. | Thường đọc lại các item của chunk 11. |
| Sau khi đích ngoài đã nhận tác dụng, nhưng trước commit checkpoint | Side effect ngoài transaction có thể đã xảy ra. | Có thể gọi lại đích → cần idempotency. |
| JobRepository dùng DB khác transaction writer | Checkpoint và dữ liệu nghiệp vụ có thể commit lệch nhau. | Cần thiết kế reconciliation, không giả định atomicity. |

Từ “thường” là chủ ý: việc resume chính xác còn phụ thuộc **đầu vào có bất biến không**, reader có `saveState` hay không, trạng thái được persist khi nào và các thay đổi có thực sự tham gia **một transaction** hay không.

## 4. ExecutionContext: dữ liệu sống qua các lần restart

`ExecutionContext` là một map lưu trạng thái được framework serialize/persist trong `JobRepository`. Có **hai cấp độc lập**:

| Cấp | Cách truy cập | Khi nào phù hợp |
| --- | --- | --- |
| **Step ExecutionContext** | `stepExecution.getExecutionContext()` | Vị trí cursor, offset file, page, state reader/writer riêng cho step đó. |
| **Job ExecutionContext** | `jobExecution.getExecutionContext()` | Dữ liệu cần chia sẻ giữa nhiều step của cùng JobExecution/JobInstance, ví dụ mã file đã kiểm tra. |

Step context thường được persist cùng checkpoint của step. Job context thường được persist tại các ranh giới step; **không giả định ghi một giá trị mới vào job context sẽ bền vững ngay ở mọi thời điểm trong một chunk**.

Ví dụ đọc/ghi một giá trị từ Step ExecutionContext ở thành phần có quyền truy cập `StepExecution`:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

// Phải dùng key có namespace riêng để tránh đụng key framework.
long lastCommittedPage = context.getLong("import.page", 0L);
context.putLong("import.page", lastCommittedPage + 1);
~~~

Đoạn trên **chỉ minh họa thao tác với map**. Thay đổi context trong bộ nhớ không đủ để tạo checkpoint đúng: thành phần đọc/ghi phải cập nhật state tại **đúng callback/lifecycle** và framework phải persist context theo transaction. Không tự cộng page trong listener rồi dùng để skip một lượng dữ liệu khác với thực tế commit.

### 4.1. Vòng đời ItemStream

Các reader/writer có trạng thái thường triển khai `ItemStream`:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

- `open` khôi phục state từ `ExecutionContext` khi step bắt đầu hoặc restart.
- `update` ghi vị trí/trạng thái hiện tại vào context trước checkpoint.
- `close` giải phóng tài nguyên. **Không trông chờ `close` để lưu tiến độ cuối**: process có thể chết mà không chạy callback.

Các triển khai như `FlatFileItemReader`, `JdbcPagingItemReader` và một số reader khác hỗ trợ state khi `saveState=true`. Khi có nhiều instance cùng loại reader trong một step, cần **tên state key khác nhau** để không ghi đè context của nhau.

### 4.2. Những gì không nên lưu vào ExecutionContext

- Không lưu nguyên danh sách hàng triệu item, body HTTP lớn hoặc Java entity/session. Context là **metadata nhỏ**, không phải nơi lưu dữ liệu nghiệp vụ.
- Không lưu token, mật khẩu, private key hay dữ liệu nhạy cảm nếu cơ sở dữ liệu metadata không được bảo vệ phù hợp.
- Không lưu đối tượng không serialize được hoặc cấu trúc phụ thuộc chặt vào class/version dễ biến mất sau khi deploy. Nên ưu tiên `String`, số, boolean, timestamp dưới dạng ổn định và ID.
- Không cho nhiều thread/partition cùng sửa một context mà không xác định ranh giới quản lý. Mỗi `StepExecution` cần state riêng.

Khi nâng version ứng dụng, thay đổi tên reader, định dạng context hoặc serializer có thể làm **job cũ không restart được**. Cần có chiến lược tương thích metadata, migration hoặc quy trình xử lý lô cũ.

## 5. Ví dụ Spring Boot: đọc CSV và ghi JDBC có checkpoint

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Batch 5.x** và PostgreSQL. Một file CSV immutable gồm:

~~~csv
operationId,orderId,amount
op-001,order-101,120000.00
op-002,order-102,350000.00
op-003,order-103,99500.00
~~~

Mỗi hàng biểu diễn một giao dịch cần lưu vào `payment_imports`, khóa nghiệp vụ `operation_id` là duy nhất. Đây là **import dữ liệu đối soát**; không trực tiếp gọi API thu tiền trong writer vì side effect thanh toán ngoài database sẽ cần chiến lược retry/idempotency chặt hơn.

Các dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Trong ứng dụng Spring Boot sử dụng auto-configuration, có thể không cần thêm `@EnableBatchProcessing` thủ công. Annotation này có thể khiến Boot nhường quyền tự cấu hình batch cho cấu hình do ứng dụng kiểm soát; chỉ dùng khi biết rõ cần thiết. Phải có database cho **JobRepository metadata** và tạo schema batch đúng phiên bản bằng migration. Không phụ thuộc việc Boot tự tạo bảng metadata trong production.

Ví dụ `application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_db
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Ở đây `enabled: false` ngăn việc tự khởi chạy job khi ứng dụng bắt đầu; job sẽ do scheduler/API vận hành hoặc `JobLauncher` khởi tạo có kiểm soát. `initialize-schema: never` giả định bảng Batch metadata và bảng nghiệp vụ đã được tạo bằng Flyway/Liquibase. Các biến môi trường được cấp từ cơ chế quản lý bí mật.

Để minh họa transaction cục bộ, ví dụ dùng **cùng PostgreSQL DataSource** cho metadata batch và bảng nghiệp vụ, với transaction manager phù hợp. Trong dự án nhiều DataSource, phải chỉ định rõ transaction manager và vị trí metadata; nếu hai nguồn commit độc lập thì bảo đảm restart cần được đánh giá lại.

### 5.1. Schema đích và tính idempotent

~~~sql
CREATE TABLE payment_imports (
    operation_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Unique key `operation_id` ngăn tạo hai dòng cho cùng một giao dịch khi chunk bị chạy lại. Nếu cùng operation ID xuất hiện với **nội dung khác nhau**, hệ thống phải coi đó là xung đột hợp đồng và đối soát; không dùng upsert để âm thầm sửa số tiền đã ghi nhận.

### 5.2. Record dữ liệu và reader khôi phục trạng thái

~~~java
package com.example.integration.batch;

import java.math.BigDecimal;

public record PaymentRow(
        String operationId,
        String orderId,
        BigDecimal amount) {}
~~~

`FlatFileItemReader` hỗ trợ lưu vị trí đọc bằng `ItemStream`. Bean cần `@StepScope` để lấy tham số `inputFile` khi step thực sự chạy:

~~~java
package com.example.integration.batch;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration(proxyBeanMethods = false)
class PaymentReaderConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<PaymentRow> paymentCsvReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<PaymentRow>()
                .name("paymentCsvReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("operationId", "orderId", "amount")
                .fieldSetMapper(fields -> new PaymentRow(
                        fields.readString("operationId"),
                        fields.readString("orderId"),
                        fields.readBigDecimal("amount")))
                .saveState(true)
                .strict(true)
                .build();
    }
}
~~~

Ý nghĩa các thuộc tính:

- `name("paymentCsvReader")` đặt tên riêng để các key trong `ExecutionContext` không va chạm với reader khác.
- `linesToSkip(1)` bỏ hàng tiêu đề CSV. Cấu trúc file, delimiter và encoding phải được cố định theo hợp đồng; nếu không phải UTF-8 thì khai báo encoding phù hợp bằng builder.
- `saveState(true)` cho reader lưu tiến độ qua `ExecutionContext`, để có thể reopen ở vị trí đã checkpoint.
- `strict(true)` yêu cầu resource tồn tại khi reader mở, tránh việc thiếu file bị hiểu thành lô rỗng hợp lệ.
- `@StepScope` cho phép tạo reader theo `JobParameters` của đúng lần chạy. Bean step-scoped không nên bị tạo/sử dụng ngoài ngữ cảnh step.

**File phải bất biến suốt quá trình và giữa các lần restart.** Nếu thêm/xóa/sắp thứ tự dòng trong file rồi restart theo index đã lưu, reader có thể bỏ sót hoặc xử lý lặp một dòng khác. Nên lưu file dưới đường dẫn immutable, có `sourceId`, checksum, số dòng hoặc metadata đối soát để xác minh đó là **cùng một đầu vào**.

### 5.3. Writer ghi trong transaction của chunk

Ví dụ dùng `JdbcBatchItemWriter` với named parameters, phù hợp record `PaymentRow`:

~~~java
package com.example.integration.batch;

import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration(proxyBeanMethods = false)
class PaymentWriterConfiguration {

    @Bean
    JdbcBatchItemWriter<PaymentRow> paymentJdbcWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<PaymentRow>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO payment_imports
                         (operation_id, order_id, amount)
                     VALUES (:operationId, :orderId, :amount)
                     ON CONFLICT (operation_id) DO NOTHING
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("operationId", item.operationId())
                                .addValue("orderId", item.orderId())
                                .addValue("amount", item.amount()))
                .assertUpdates(false)
                .build();
    }
}
~~~

Đây là SQL **PostgreSQL**: `ON CONFLICT ... DO NOTHING` giúp cùng operation ID không tạo thêm dòng khi đọc lại. `MapSqlParameterSource` ánh xạ tường minh accessor của Java record sang tham số SQL, không phụ thuộc quy ước getter JavaBean. Với `assertUpdates(false)`, writer không coi một lần insert bị bỏ qua là lỗi vì không cập nhật dòng nào. Dù vậy, đây chỉ là **dedupe theo khóa**: trước khi bỏ qua một ID trùng, quy trình đối soát cần xác minh rằng `orderId`/`amount` khớp với dữ liệu đã ghi, vì cùng operation ID nhưng số tiền khác là lỗi nghiêm trọng.

Trong production, có thể dùng staging table, validate hash payload hoặc câu lệnh/constraint phát hiện khác biệt để thất bại có kiểm soát. Transaction chunk bảo vệ các bản ghi trong **cùng database và cùng transaction manager**; nó không bao phủ email, HTTP hay broker nếu các đích không cùng transaction.

### 5.4. Định nghĩa Step và Job bằng API Spring Batch

~~~java
package com.example.integration.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PaymentImportJobConfiguration {

    @Bean
    Step importPaymentsStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<PaymentRow> paymentCsvReader,
            JdbcBatchItemWriter<PaymentRow> paymentJdbcWriter) {

        return new StepBuilder("importPaymentsStep", jobRepository)
                .<PaymentRow, PaymentRow>chunk(100, transactionManager)
                .reader(paymentCsvReader)
                .writer(paymentJdbcWriter)
                .build();
    }

    @Bean
    Job importPaymentsJob(
            JobRepository jobRepository,
            Step importPaymentsStep) {

        return new JobBuilder("importPaymentsJob", jobRepository)
                .start(importPaymentsStep)
                .build();
    }
}
~~~

Trong ví dụ này, writer nhận nguyên `PaymentRow` nên không cần processor; có thể thêm `.processor(...)` khi cần validation hoặc chuẩn hóa dữ liệu. `chunk(100, transactionManager)` đặt ranh giới commit cho tối đa 100 item đọc trong một chunk, với các ngoại lệ như filter/skip/retry cần được tính riêng.

**Điều kiện quan trọng:** `PlatformTransactionManager` được inject phải thực sự quản lý tài nguyên JDBC mà writer sử dụng, và phải phù hợp với cấu hình JobRepository. Nếu dự án có nhiều manager, dùng `@Qualifier` thay vì dựa vào `@Primary` ngầm định. Không tự nhận rằng metadata checkpoint và bảng nghiệp vụ được commit atomically nếu chúng nằm ở hai datasource/transaction manager khác nhau.

## 6. JobParameters: cách khởi động và restart đúng JobInstance

Với một job import mỗi ngày, thiết lập identifying parameters để định danh **đúng tệp dữ liệu logic**:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.launch.JobLauncher;

// Đây là đoạn mã đặt trong service/scheduler có inject Job và JobLauncher.
JobParameters params = new JobParametersBuilder()
        .addString("sourceId", "bank-A-2026-11-21", true)
        .addString("inputFile", "/data/import/bank-A-2026-11-21.csv", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importPaymentsJob, params);
~~~

Hai tham số ở ví dụ là **identifying**. Nếu lần chạy đầu thất bại, việc gọi `jobLauncher.run(importPaymentsJob, params)` với cùng identifying parameters giúp Spring Batch tìm **cùng JobInstance** và tạo execution mới nếu được phép restart. Đừng tạo timestamp hay `run.id` mới mỗi lần thử lại.

Ngoài cách chạy lại bằng `JobLauncher`, có thể dùng `JobOperator.restart(executionId)` để yêu cầu restart một JobExecution thất bại/đã dừng khi hạ tầng Spring Batch được cấu hình đầy đủ. Phải kiểm tra trạng thái execution được phép restart trước khi gọi, đồng thời đảm bảo không có execution khác của cùng instance đang chạy.

### 6.1. Xử lý các trạng thái và điều kiện không thể restart

| Trạng thái/điều kiện | Ý nghĩa vận hành |
| --- | --- |
| `FAILED` | Có thể restart nếu job cho phép và metadata/đầu vào vẫn hợp lệ. |
| `STOPPED` | Có thể restart sau khi dừng an toàn, tùy cấu hình step/job. |
| `COMPLETED` | Thường không restart cùng instance; muốn tái xử lý có chủ đích phải tạo **JobInstance mới** hoặc thiết kế lại yêu cầu. |
| `STARTED` / đang chạy | Không khởi động thêm execution cùng JobInstance chỉ vì job lâu; cần xác minh tiến trình còn hoạt động. |
| `UNKNOWN` / metadata không nhất quán | Không ép trạng thái bằng SQL; cần điều tra, đối soát trước khi can thiệp. |
| Reader không lưu state (`saveState=false`) | Có thể đọc lại từ đầu; chỉ an toàn nếu toàn bộ side effect idempotent và cách kiểm soát trùng được thiết kế. |

Một số trường hợp đặc biệt: `startLimit` giới hạn số lần start step, `allowStartIfComplete(true)` yêu cầu chạy lại step đã hoàn tất khi restart job (ví dụ bước kiểm tra cần chạy lại), còn mặc định step đã `COMPLETED` thường được bỏ qua. Những lựa chọn này có tác động tới công việc ghi dữ liệu, nên phải mô tả và kiểm thử rõ ràng.

## 7. Chuyển dữ liệu giữa các Step ExecutionContext

Một job có thể gồm hai bước:

1. `validateSourceStep` kiểm tra checksum và số dòng của file, lưu `sourceChecksum`.
2. `importPaymentsStep` chỉ xử lý nếu checksum khớp với tệp đã được xác nhận.

Nếu chỉ ghi `sourceChecksum` vào **Step ExecutionContext** của step kiểm tra, step import **không tự đọc được** vì mỗi step có context riêng. Để truyền dữ liệu sang các step khác, có thể:

- Lưu giá trị cần dùng trực tiếp vào **Job ExecutionContext** tại ranh giới phù hợp.
- Dùng `ExecutionContextPromotionListener` để promotion key từ step context sang job context khi step hoàn tất theo trạng thái cho phép.
- Lưu dữ liệu quan trọng, lớn hoặc cần đối soát vào **bảng nghiệp vụ** theo `sourceId`, chỉ đưa ID/checksum nhỏ vào context.

Ví dụ cấu hình listener để promotion:

~~~java
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.context.annotation.Bean;

@Bean
ExecutionContextPromotionListener promoteSourceChecksum() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] { "sourceChecksum" });
    return listener;
}
~~~

Listener này phải được gắn vào **step tạo ra key `sourceChecksum`** (ví dụ với builder `.listener(promoteSourceChecksum())`), và processor/tasklet phải ghi key vào context của step trước khi kết thúc. Promotion xảy ra theo lifecycle step, **không dùng làm cơ chế checkpoint mỗi item**.

Nếu job cần restart sau khi đã hoàn tất `validateSourceStep`, trạng thái job context phải đủ để bước tiếp theo tiếp tục đúng. Hãy tránh truyền toàn bộ file đã parse qua context: metadata có giới hạn kích thước, khó versioning và không phải data store nghiệp vụ.

## 8. Những ranh giới có thể làm checkpoint lệch dữ liệu thực tế

### 8.1. Metadata và dữ liệu nghiệp vụ ở hai database

Giả sử `JobRepository` dùng DB A, `ItemWriter` ghi DB B. Nếu mỗi database sử dụng transaction manager riêng, có thể có hai thứ tự nguy hiểm:

~~~mermaid
sequenceDiagram
    participant Batch as Spring Batch
    participant Meta as DB A - JobRepository
    participant Data as DB B - Business
    Batch->>Data: Ghi chunk
    Data-->>Batch: Commit thành công
    Batch->>Meta: Lưu checkpoint
    Note over Meta: Lỗi/crash trước khi checkpoint commit
    Note over Data,Meta: Khi restart có thể xử lý lại chunk đã ghi
~~~

Hoặc checkpoint được xem là hoàn tất nhưng business write không thành công theo một cơ chế phối hợp sai. Kết quả là **thiếu hoặc trùng dữ liệu** nếu không có đối soát. Các lựa chọn:

1. Dùng cùng database và transaction manager khi có thể, để writer và checkpoint tham gia cùng transaction cục bộ phù hợp.
2. Thiết kế writer **idempotent** (unique key, upsert có kiểm tra xung đột, inbox ledger) để chạy lại chunk an toàn.
3. Khi cần ghi sang nhiều đích, dùng staging/outbox, saga hoặc workflow đối soát. Đừng giả định `JobRepository` tự phối hợp XA giữa hai database.

### 8.2. Gọi HTTP, gửi email hoặc publish broker từ ItemWriter

~~~text
Chunk bắt đầu
  -> POST /payments ở đích (đã tạo authorization)
  -> Process chết trước checkpoint
  -> Restart đọc lại item
  -> POST /payments lần nữa
~~~

Rollback local DB **không đảo ngược** một payment đã tạo hoặc email đã gửi. Trường hợp này cần:

- Operation ID ổn định và được gửi lại qua các attempt.
- API đích hỗ trợ idempotency hoặc tra cứu kết quả theo operation ID.
- Trạng thái `PENDING`/`UNKNOWN` và quy trình reconciliation nếu timeout sau side effect.
- Outbox nếu mục tiêu là **phát event sau commit** một cách đáng tin cậy.

Với broker Kafka/RabbitMQ, ack, retry và redelivery có thể làm message lặp; dùng key/correlation ID đủ bền và dedupe tại consumer. **Checkpoint của Batch không tự tạo exactly-once end-to-end**.

### 8.3. Đầu vào thay đổi và kết quả không còn xác định

Flat file cố định được restart theo item index có thể khôi phục tốt. Nhưng với API phân trang hoặc truy vấn DB thay đổi liên tục:

- `OFFSET/LIMIT` theo một bảng đang bị insert/delete có thể bỏ sót/lặp item khi restart.
- Paging không có `ORDER BY` ổn định khiến cùng page trả bản ghi khác nhau sau deploy hoặc khi query plan thay đổi.
- External API cursor có thể hết hạn; phải có phương án lấy lại snapshot, checkpoint bằng key/marker bền hoặc bắt đầu lô mới an toàn.
- Truy vấn nguồn nên dùng snapshot/batch ID, monotonic keyset pagination hoặc một cửa sổ thời gian/ID đã cố định, tùy nguồn hỗ trợ.

Nếu tính đúng đắn phụ thuộc nguồn là ảnh chụp tại một thời điểm, cần **đóng băng hoặc version nguồn** chứ không chỉ thêm `saveState(true)`.

## 9. Retry, skip và restart: ba cơ chế không giống nhau

| Cơ chế | Khi dùng | Bảo đảm phải xem xét |
| --- | --- | --- |
| **Retry trong cùng StepExecution** | Lỗi tạm thời như deadlock hoặc timeout ngắn. | Có thể gọi lại processor/writer; tác dụng ngoài cần idempotent. |
| **Skip item** | Bản ghi hỏng được phép bỏ qua theo hợp đồng lô. | Phải ghi nhận item bị bỏ và quyết định khi nào lô còn được coi là hoàn tất. |
| **Restart JobInstance** | Lỗi hoặc dừng cả job; khởi chạy JobExecution mới từ checkpoint. | Input/metadata tương thích, side effect đã commit không bị thực hiện lặp có hại. |

Ví dụ cấu hình fault tolerance có chủ đích:

~~~java
return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentRow, PaymentRow>chunk(100, transactionManager)
        .reader(paymentCsvReader)
        .writer(paymentJdbcWriter)
        .faultTolerant()
        .retry(org.springframework.dao.TransientDataAccessException.class)
        .retryLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .skipLimit(5)
        .build();
~~~

Đây là **biến thể minh họa**, không thêm song song với `importPaymentsStep` khác cùng bean name. Bản ghi CSV không đọc được có thể được skip tối đa 5 lần, còn lỗi JDBC tạm thời được retry có giới hạn. `retryLimit` là chính sách số attempt tại framework, nhưng behavior cụ thể còn phụ thuộc exception được ném, rollback và vị trí lỗi.

Không tự bật skip cho mọi exception hoặc mọi lỗi giao dịch: một bản ghi thanh toán bị bỏ qua có thể làm sai đối soát. Cần giữ thống kê `readSkipCount`, `processSkipCount`, `writeSkipCount`, nguyên nhân và có cơ chế xử lý file lỗi đúng quyền truy cập.

## 10. Chạy song song và ảnh hưởng tới ExecutionContext

Để tăng throughput, Spring Batch hỗ trợ multi-threaded step, partitioning, remote chunking và các mẫu điều phối khác. Nhưng checkpoint không còn đơn giản như một chỉ số dòng duy nhất:

- **Multi-threaded step:** reader/writer có state có thể không thread-safe. Một `FlatFileItemReader` không nên bị chia sẻ giữa nhiều thread mà không kiểm soát; wrapper đồng bộ có thể giúp thread safety nhưng không tự bảo đảm thứ tự và restart an toàn khi chunk chạy song song.
- **Partitioning:** mỗi partition có `StepExecution`/`ExecutionContext` riêng; quản lý range/key và trạng thái từng partition để restart riêng các phần thất bại. Tên partition và phân vùng dữ liệu cần ổn định giữa các lần restart.
- **Remote chunking:** việc gửi item/chunk và xác nhận ở worker ngoài process tạo thêm ranh giới không chắc chắn; cần broker ack, dedupe và idempotent writer.
- **Job chạy chồng nhau:** hai JobInstance khác nhau có thể cùng đọc một tệp hoặc ghi một khóa nghiệp vụ nếu đặt identifying parameters sai. Bảo vệ bằng khóa nghiệp vụ và chính sách chỉ cho phép một lần xử lý hợp lệ.

Không bật parallel chỉ vì checkpoint đã có sẵn. Hãy chứng minh state, input partition và write path an toàn trước concurrency.

## 11. Kiểm thử restart có giá trị

Kiểm thử luồng thành công chỉ chứng minh job có thể chạy, chưa chứng minh **khôi phục chính xác sau lỗi**. Cần kiểm thử từ metadata thật, với database thật hoặc Testcontainers, và mô phỏng lỗi đúng ranh giới chunk.

| Kịch bản | Điều phải xác minh |
| --- | --- |
| Job chạy thành công 100.000 dòng | Metadata `COMPLETED`, tổng bản ghi và tổng tiền đúng, không dư/thiếu. |
| Hỏng ở dòng 350 khi chunk size 100 | Các chunk đã commit còn nguyên; restart đọc lại phần chưa commit, hoàn tất đúng tổng. |
| Crash sau khi writer đã ghi nhưng trước checkpoint (side effect ngoài DB) | Idempotency/reconciliation ngăn phát sinh tác dụng lặp có hại. |
| Cùng JobParameters sau `FAILED` | JobExecution mới thuộc cùng JobInstance; không tạo lô mới. |
| JobParameters có `run.id` mới | Tạo JobInstance mới; hệ thống không được nhầm với restart. |
| `@StepScope` nhận `inputFile` đúng | Reader mở đúng resource của lần chạy, không giữ path cũ giữa các execution. |
| File bị thay đổi sau thất bại | Checksum/immutable source check phát hiện khác biệt; không resume theo offset không đáng tin. |
| Rollback chunk do lỗi JDBC | Không còn dữ liệu nửa chunk nếu writer và transaction cùng datasource phù hợp. |
| Processor lọc hoặc skip item | `readCount`/`writeCount`/`filterCount`/`skipCount` phù hợp; dữ liệu nghiệp vụ không lệch. |
| Restart khi Step trước đã hoàn tất | Step completed được bỏ qua theo cấu hình; context chuyển step vẫn khả dụng. |
| Redeploy thay version reader/serialization | Old ExecutionContext vẫn đọc được, hoặc quy trình migration/khôi phục được thực hiện. |
| Hai partition restart | Chỉ partition chưa hoàn thành được chạy lại, không ghi trùng vùng dữ liệu khác. |

### 11.1. Tổ chức kiểm thử với Spring Batch Test

Thêm dependency kiểm thử Spring Batch:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Có thể dùng `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils` cùng `@SpringBootTest` để khởi chạy job/step theo bộ test. Tuy nhiên, với bài kiểm thử restart, **không nên xóa metadata JobRepository giữa attempt FAILED và attempt restart**, vì như vậy mất đúng trạng thái cần kiểm tra. Việc dọn dữ liệu phải diễn ra trước/giữa các test case độc lập theo một kế hoạch rõ ràng.

Trình tự test restart có thể là:

1. Nạp một file fixture **bất biến**, chuẩn bị schema và làm sạch trạng thái trước test.
2. Chèn một failure có kiểm soát khi đã commit một số chunk; xác nhận JobExecution `FAILED`, kiểm tra metadata và số dòng dữ liệu đã commit.
3. Tắt failure nhưng **giữ nguyên identifying JobParameters** và `JobRepository`.
4. Chạy lại job; xác nhận có JobExecution mới thuộc cùng JobInstance và JobExecution cuối `COMPLETED`.
5. Kiểm tra dữ liệu **từng business key** và tổng amount, không chỉ số lượng dòng; assert không có bản ghi trùng hoặc thiếu.
6. Thử lần chạy thứ ba cùng JobInstance đã hoàn tất: framework từ chối hoặc làm theo chính sách đã cấu hình; không âm thầm chạy lại như job mới.

Đừng đánh giá restart chỉ qua `readCount`: một writer có thể bỏ qua duplicate trong database nên tổng dòng đúng dù nó đã đọc lại quá nhiều. Mục tiêu cần xác minh cả **độ đúng nghiệp vụ** và **tiến độ khôi phục**.

## 12. Vận hành, quan sát và bảo vệ metadata

Một dashboard batch tốt cần trả lời:

- JobInstance nào đang xử lý, với những identifying parameters nào? Có attempt nào đang `STARTED` quá lâu không?
- Step nào thất bại, `readCount`, `writeCount`, `commitCount`, `rollbackCount`, `skipCount` thay đổi ra sao?
- Checkpoint/ExecutionContext cập nhật lần cuối khi nào? Có đang kẹt ở cùng item hoặc partition không?
- Độ trễ xử lý, throughput theo phút, số chunk commit/rollback và thời gian giữ transaction/connection là bao nhiêu?
- Có bản ghi nào bị skip, DLQ hoặc cần đối soát thủ công không?
- Sau redeploy, các job cũ còn restart được với phiên bản schema/serializer hiện tại không?

**JobRepository là dữ liệu vận hành quan trọng**: dùng database bền vững, backup, migration có kiểm soát, phân quyền và giám sát kết nối. Không dùng repository trong bộ nhớ cho một job mà cam kết resume sau khi process chết. Giữ lại metadata đủ lâu để hỗ trợ retry/đối soát; khi dọn metadata cần biết job nào còn được phép restart và dữ liệu nghiệp vụ nào vẫn liên kết tới execution cũ.

Chỉ log khóa nghiệp vụ ở mức cần thiết và được phân quyền; tránh ghi toàn bộ dữ liệu cá nhân, số thẻ, token, mật khẩu hoặc raw `ExecutionContext`. Chọn correlation ID/source ID ổn định để lần theo một lô từ input tới DB, event hoặc kết quả đối soát.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Restart chỉ là chạy lại cùng method.” | Khởi tạo JobInstance mới, đọc lại từ đầu. | Restart cần cùng identity job và identifying parameters, có metadata bền vững. |
| “Mỗi lần muốn thử lại cứ thêm timestamp.” | Thay đổi identity lô, mất checkpoint. | Giữ nguyên identifying parameters khi restart cùng lô. |
| “Có ExecutionContext thì mọi thứ được ghi đúng một lần.” | API/email/broker ngoài transaction có thể bị gọi trùng. | Dùng idempotency và đối soát ngoài ranh giới commit. |
| “Đã saveState=true là file muốn sửa thế nào cũng được.” | Offset chỉ vào dòng khác, dữ liệu thiếu/trùng. | Đầu vào phải immutable/versioned hoặc dùng cursor/checkpoint phù hợp. |
| “ExecutionContext là một map chung toàn job.” | Step truy cập nhầm key, mất metadata giữa các bước. | Phân biệt step context, job context và promotion. |
| “Ghi metadata là đủ, không cần transaction writer.” | Dữ liệu business và checkpoint lệch nhau. | Gắn writer với transaction manager đúng, hoặc thiết kế idempotent/reconciliation. |
| “Skip một record hỏng không ảnh hưởng lô.” | Báo cáo và số dư bị thiếu dữ liệu. | Skip phải có chính sách nghiệp vụ, số liệu và xử lý hậu kiểm. |
| “Parallel step luôn giúp tăng tốc an toàn.” | Reader state và chunk commit có thể không xác định. | Kiểm tra thread safety, partition boundaries, ordering và restart. |

## 14. Checklist thiết kế một job có thể restart

- [ ] Đã xác định rõ **JobInstance identity** và identifying JobParameters; retry cùng lô không tạo identity mới.
- [ ] `JobRepository` dùng database bền vững, schema đúng version, có migration/backup và quyền truy cập phù hợp.
- [ ] Reader hỗ trợ state hoặc có chiến lược xử lý lại an toàn; `ItemStream` được đăng ký và có key name duy nhất.
- [ ] Input file/API snapshot bất biến hoặc có version/checksum; phân trang có thứ tự ổn định.
- [ ] `ExecutionContext` chỉ lưu metadata nhỏ, version được và có thể serialize.
- [ ] Transaction manager của chunk phù hợp datasource writer; hiểu rõ khi metadata và dữ liệu nằm ở các nguồn khác nhau.
- [ ] Writer/adapter ngoài database idempotent; có operation/event ID và reconciliation khi timeout/crash sau side effect.
- [ ] Retry, skip, restart, start limit và thứ tự step đã được mô tả theo yêu cầu nghiệp vụ.
- [ ] Đã kiểm thử restart thật với metadata tồn tại xuyên attempts, rollback chunk, input thay đổi và nâng version ứng dụng.
- [ ] Monitoring cho `FAILED`/`STOPPED`, job chạy quá hạn, checkpoint lag, skip/rollback và số liệu đối soát.

Trong **Spring Boot Integration**, checkpoint và `ExecutionContext` giúp Spring Batch ghi nhớ **đã hoàn thành tới đâu**, còn `JobInstance`/`JobExecution` xác định **đang tiếp tục lần chạy logic nào**. Khi kết hợp đúng transaction của chunk, JobRepository bền vững, nguồn dữ liệu ổn định và writer có khả năng xử lý trùng, một batch job có thể phục hồi sau lỗi mà vẫn duy trì hợp đồng dữ liệu và độ tin cậy của luồng tích hợp thực tế.
