# Commit interval tuning trong Spring Batch

## 1. Commit interval là gì?

Trong **Spring Batch Core Processing**, một Step kiểu *chunk-oriented* thường thực hiện chu trình: đọc item, xử lý item, gom nhiều item thành một chunk, ghi chunk và commit transaction. **Commit interval** (thường gọi là **chunk size**) là số item được tích lũy theo chính sách hoàn thành chunk trước khi framework thực hiện thao tác ghi/commit tương ứng.

Ví dụ với **Spring Batch 5.2.x**:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
~~~

Ở cấu hình trên, Step thường đọc/xử lý tối đa 100 item đầu vào cho một chunk, đưa các item sau xử lý cho writer, cập nhật checkpoint nếu có rồi commit transaction. Chunk cuối có thể ít hơn 100 item.

Điều chỉnh commit interval ảnh hưởng đồng thời đến **throughput**, số transaction, bộ nhớ, thời gian giữ khóa database, chi phí rollback và khả năng restart. Mục tiêu là chọn một khoảng giá trị cho hiệu năng ổn định, đáp ứng yêu cầu dữ liệu và recovery. Không có một commit interval tối ưu chung cho mọi Job.

### Mục tiêu bài học

- Hiểu commit interval tác động thế nào đến ranh giới transaction và checkpoint.
- Phân biệt commit interval với JDBC fetch size, page size, JDBC batch size và concurrency.
- Phân tích lợi ích/chi phí của chunk nhỏ, vừa và lớn.
- Cấu hình Step chunk-oriented bằng API Spring Batch phù hợp.
- Tổ chức benchmark và thu thập metric để tuning có cơ sở.
- Kiểm thử rollback, restart và tính idempotent khi thay commit interval.
- Đưa ra phương án chọn giá trị và triển khai thay đổi trong production an toàn.

## 2. Hình dung chunk và ranh giới commit

Giả sử source chứa 10 item, commit interval là 3:

~~~text
Step bắt đầu
    |
    +-- Transaction #1
    |     read/process 1, 2, 3
    |     writer([1, 2, 3])
    |     COMMIT
    |
    +-- Transaction #2
    |     read/process 4, 5, 6
    |     writer([4, 5, 6])
    |     COMMIT
    |
    +-- Transaction #3
    |     read/process 7, 8, 9
    |     writer([7, 8, 9])
    |     COMMIT
    |
    +-- Transaction #4
          read/process 10
          writer([10])
          COMMIT
~~~

Ở tình huống đơn giản, số **chunk có dữ liệu** xấp xỉ:

~~~text
data_chunks ≈ ceil(input_item_count / commit_interval)

10 items, interval 3 -> 4 data chunks
100.000 items, interval 100 -> 1.000 data chunks
~~~

Cần phân biệt số chunk chứa dữ liệu với `StepExecution.getCommitCount()`. Một số đường thực thi có commit bổ sung khi kiểm tra kết thúc luồng, xử lý skip/retry hoặc cập nhật metadata. Vì vậy không dùng công thức trên để khẳng định giá trị chính xác của cột `COMMIT_COUNT` trong mọi trường hợp.

### Item được đọc và được ghi có thể khác nhau

Processor có thể trả về `null` để **filter** item. Ví dụ trong một chunk đã đọc 100 item nhưng lọc 15 item, writer chỉ nhận 85 item. Skip và retry còn có thể làm phát sinh rollback hoặc xử lý lại.

Do đó:

- `READ_COUNT` đo item đọc theo semantics của Step.
- `FILTER_COUNT` đo item được lọc bởi processor.
- `WRITE_COUNT` đo item ghi theo semantics của Step.
- `READ_SKIP_COUNT`, `PROCESS_SKIP_COUNT`, `WRITE_SKIP_COUNT` đo item bỏ qua do lỗi được policy cho phép.
- `COMMIT_COUNT` và `ROLLBACK_COUNT` đo các transaction theo cách StepExecution ghi nhận.

Không suy ra số lần writer thực hiện hay số transaction chỉ từ phép chia `WRITE_COUNT / chunkSize` khi có filter, retry hoặc skip.

## 3. Chunk quá nhỏ: lợi ích và chi phí

Với `chunk(1, transactionManager)`:

~~~text
read A -> process A -> write A -> COMMIT
read B -> process B -> write B -> COMMIT
read C -> process C -> write C -> COMMIT
...
~~~

Một Job 100.000 item có thể cần xấp xỉ 100.000 lần commit dữ liệu. Mỗi commit có overhead: điều phối transaction, database log, network round-trip và metadata/checkpoint ở các thời điểm phù hợp.

**Ưu điểm của chunk nhỏ:**

- Danh sách item trong bộ nhớ nhỏ hơn.
- Transaction thường ngắn hơn, giảm thời gian giữ lock.
- Một chunk rollback thường khiến ít item phải xử lý lại.
- Checkpoint thường xuyên, hữu ích khi restart sau lỗi.
- Step có cơ hội phản hồi tín hiệu dừng ở các ranh giới chunk gần nhau.

**Nhược điểm:**

- Số transaction lớn và metadata được cập nhật thường xuyên hơn.
- Writer ít cơ hội tận dụng batch SQL lớn.
- Chi phí cố định của commit có thể chiếm tỉ trọng lớn.
- Khi database ở xa, nhiều lần round-trip có thể làm giảm throughput.

Nếu mỗi item mất 300 ms để xử lý CPU, chi phí commit có thể chỉ là phần nhỏ. Khi đó tăng chunk từ 10 lên 100 chưa chắc cải thiện đáng kể. Ngược lại, với item nhỏ và writer JDBC, giảm số commit có thể tạo khác biệt rõ.

## 4. Chunk quá lớn: vì sao throughput có thể giảm?

Với `chunk(5_000, transactionManager)`, Step có thể giữ hàng nghìn item và kết quả xử lý trong một transaction. Ít commit hơn nhưng phát sinh rủi ro:

| Tác động | Cơ chế |
| --- | --- |
| Bộ nhớ tăng | Một chunk giữ nhiều object, collection và buffer trước khi writer kết thúc. |
| Transaction dài | Lock, transaction log và session database có thể tồn tại lâu hơn. |
| Rollback tốn hơn | Lỗi ở gần cuối chunk có thể buộc xử lý lại nhiều item chưa commit. |
| Checkpoint thưa | Khi restart, reader có thể phải đọc lại phần lớn chunk chưa commit. |
| Stop phản hồi chậm | Tasklet/Step thường chỉ xử lý yêu cầu dừng tại các điểm framework lấy lại quyền điều khiển. |
| Writer dễ quá tải | Writer phải xử lý nhiều tham số SQL, message hoặc request cùng lúc. |
| Tail latency tăng | Một item chậm có thể kéo dài thời gian hoàn thành cả chunk. |

Database dùng MVCC có thể bị ảnh hưởng bởi transaction dài và việc giữ version dữ liệu. Hệ thống dựa nhiều vào row lock có thể tăng lock wait/deadlock. Nếu transaction timeout nhỏ hơn thời gian xử lý chunk, Job có thể liên tục thất bại.

Vì vậy, biểu đồ hiệu năng thường có **vùng giá trị cân bằng**: ban đầu tăng chunk giúp giảm overhead commit; sau một ngưỡng, bộ nhớ, contention và chi phí phục hồi tăng có thể làm lợi ích biến mất.

## 5. Commit interval khác fetch size, page size, batch size

Những tham số này thường bị đánh đồng:

| Tham số | Điều khiển | Quan hệ với commit |
| --- | --- | --- |
| **Commit interval** | Số item để hoàn thành một chunk và ranh giới transaction Step. | Đây là tham số cần tuning. |
| **JDBC fetch size** | Gợi ý cách driver lấy row từ ResultSet theo từng đợt. | Không quyết định transaction boundary. |
| **Paging page size** | Số row reader dạng paging lấy trong một lần truy vấn/trang. | Không bắt buộc bằng chunk size. |
| **JDBC batch size** | Số SQL statement/parameter được gom thành JDBC batch. | Có thể bị ảnh hưởng bởi chunk, nhưng phụ thuộc writer/driver. |
| **Partition/grid size** | Số phân đoạn dữ liệu/đơn vị xử lý song song. | Ảnh hưởng số chunk/transaction hoạt động đồng thời. |
| **Connection pool size** | Số JDBC connection có thể sử dụng. | Hạn chế mức concurrency, không xác định chunk size. |
| **Retry limit** | Ngân sách thử lại khi lỗi. | Làm thay đổi chi phí xử lý lại, không xác định commit interval. |

Ví dụ `JdbcCursorItemReader` có `fetchSize(500)` nhưng Step có `chunk(100, tx)`: driver có thể fetch theo đợt 500 row trong khi Spring Batch hoàn thành chunk theo 100 item. Ngược lại, đặt chunk 500 không bảo đảm driver gửi duy nhất một lệnh SQL cho 500 item.

Đối với JPA, page size của reader, persistence context của EntityManager và JDBC batching của provider cũng là các tầng khác nhau. Không được giả định tăng chunk sẽ tự tối ưu tất cả.

## 6. Mô hình chi phí để suy nghĩ trước khi thử nghiệm

Có thể biểu diễn gần đúng:

~~~text
T_total ≈ T_read
        + T_process
        + T_write
        + T_commit
        + T_lock_or_contention
        + T_retry_and_rollback

T_commit ≈ number_of_commits * fixed_commit_overhead
number_of_data_chunks ≈ ceil(total_input_items / commit_interval)
~~~

Khi commit interval tăng, `number_of_data_chunks` giảm. Tuy nhiên, `T_lock_or_contention` và `T_retry_and_rollback` có thể tăng; `T_write` còn phụ thuộc writer có gom SQL hay không.

Ví dụ phép tính lý thuyết cho 100.000 item, chưa xét filter/skip/retry:

| Commit interval | Số chunk có dữ liệu ước tính |
| ---: | ---: |
| 1 | 100.000 |
| 10 | 10.000 |
| 50 | 2.000 |
| 100 | 1.000 |
| 250 | 400 |
| 500 | 200 |
| 1.000 | 100 |
| 5.000 | 20 |

Bảng này **không phải benchmark** và không chứng minh chunk 5.000 nhanh hơn chunk 100. Nó chỉ giúp ước tính quy mô overhead cố định của transaction trong đường chạy đơn giản.

## 7. Cấu hình thực hành với Spring Batch 5.2.x

Ví dụ dùng Java 17, Spring Boot 3 và Spring Batch 5.2.x, cùng **JDBC JobRepository**. Job đọc bảng source và ghi bảng đích qua JDBC writer.

### 7.1. Bảng dữ liệu

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);

CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

Primary key ở bảng đích giúp phát hiện ghi trùng trong bài test restart. Ở production, cần thiết kế khóa nghiệp vụ và idempotency/upsert phù hợp.

### 7.2. Model

~~~java
import java.math.BigDecimal;

public class OrderRecord {
    private final Long id;
    private final BigDecimal amount;

    public OrderRecord(Long id, BigDecimal amount) {
        this.id = id;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

### 7.3. Reader và writer

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderIoConfiguration {

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRecord> ordersReader(DataSource dataSource) {
        return new JdbcCursorItemReaderBuilder<OrderRecord>()
                .name("ordersReader")
                .dataSource(dataSource)
                .sql("SELECT id, amount FROM source_orders ORDER BY id")
                .rowMapper((rs, rowNum) -> new OrderRecord(
                        rs.getLong("id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(300)
                .saveState(true)
                .build();
    }

    @Bean
    JdbcBatchItemWriter<OrderRecord> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderRecord>()
                .dataSource(dataSource)
                .sql("INSERT INTO imported_orders(id, amount) " +
                     "VALUES (:id, :amount)")
                .beanMapped()
                .build();
    }
}
~~~

`ORDER BY id` tạo thứ tự đọc ổn định **nếu nguồn không đổi**. Với nguồn có thể thêm/xóa row trước vị trí checkpoint, offset lưu trong reader có thể không đủ an toàn; cần snapshot dữ liệu hoặc chiến lược checkpoint theo business key.

`saveState(true)` cho phép reader lưu vị trí đọc vào ExecutionContext, hỗ trợ restart. `@StepScope` tạo reader mới cho từng StepExecution; tránh chia sẻ một cursor có state giữa các execution.

### 7.4. Step với commit interval 100

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
class OrderJobConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager tx,
            JdbcCursorItemReader<OrderRecord> ordersReader,
            JdbcBatchItemWriter<OrderRecord> ordersWriter) {

        final int commitInterval = 100;

        return new StepBuilder("importOrdersStep", repository)
                .<OrderRecord, OrderRecord>chunk(commitInterval, tx)
                .reader(ordersReader)
                .processor(order -> order)
                .writer(ordersWriter)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository,
            Step importOrdersStep) {

        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }
}
~~~

Trong môi trường thực, nên chuyển `commitInterval` thành cấu hình ứng dụng, ví dụ `batch.tuning.commit-interval=100`, rồi bind bằng `@ConfigurationProperties`. Đây là **thuộc tính tự định nghĩa**, không phải Spring Batch tự đọc. Khi parse cấu hình, cần yêu cầu giá trị dương và đặt giới hạn hợp lý cho workload.

Reader, writer và Step nên dùng transaction manager/DataSource tương thích. Nếu metadata và writer sử dụng resource hoặc transaction manager khác nhau, cần kiểm chứng hành vi nhất quán của commit, checkpoint và recovery.

## 8. CompletionPolicy cho chunk linh hoạt

Nếu không muốn dùng một số item cố định, Spring Batch hỗ trợ **CompletionPolicy** để quyết định thời điểm kết thúc chunk theo chính sách.

Ví dụ ở Spring Batch 5.2:

~~~java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.SimpleCompletionPolicy;

@Bean
CompletionPolicy simplePolicy() {
    return new SimpleCompletionPolicy(100);
}
~~~

Builder có thể nhận CompletionPolicy thay cho kích thước chunk cố định:

~~~java
new StepBuilder("policyStep", repository)
        .<OrderRecord, OrderRecord>chunk(simplePolicy, transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

`SimpleCompletionPolicy(100)` vẫn giới hạn theo số item. Các policy khác có thể dựa trên thời gian hoặc điều kiện kết thúc riêng. Với workload có thời gian xử lý item biến thiên lớn, một policy thích hợp có thể giúp kiểm soát độ dài transaction. Tuy nhiên, cần hiểu rõ semantics của policy trong đúng phiên bản và test các ranh giới khi kết thúc chunk; không giả định một policy dựa trên thời gian có khả năng ngắt lập tức lời gọi JDBC/HTTP đang bị chặn.

## 9. Commit interval tác động thế nào đến restart?

Khi Step fail, các chunk đã commit thường được giữ nguyên; chunk đang xử lý có thể rollback tùy transaction. Reader có `ExecutionContext` hỗ trợ restart sẽ dùng checkpoint đã lưu.

Ví dụ 1.000 item, commit interval 100, processor cố ý lỗi tại item 231:

~~~text
Execution 1:
  item 1..100   -> COMMIT
  item 101..200 -> COMMIT
  item 201..231 -> processor lỗi -> ROLLBACK chunk
  Job           -> FAILED

Execution 2 (restart cùng JobInstance):
  khôi phục từ checkpoint sau item 200
  item 201..300 -> COMMIT
  ...
  item 901..1000 -> COMMIT
  Job           -> COMPLETED
~~~

Nếu interval = 10, phần công việc chưa commit khi lỗi tại 231 nhỏ hơn. Nếu interval = 500, lỗi tại 231 có thể làm phải đọc/xử lý lại tất cả item trong chunk đầu khi restart.

Điều kiện để ví dụ đúng:

- Reader lưu state và đọc theo thứ tự ổn định.
- Các thao tác JDBC của writer chịu cùng transaction theo thiết kế.
- Metadata `BATCH_*` được giữ nguyên giữa hai execution.
- Không có side effect ngoài transaction bị gọi lại mà thiếu idempotency.
- Không dùng identifying JobParameters mới khi muốn restart.

**Chạy lại không mặc nhiên bảo đảm exactly-once** với HTTP API, email, file hay message broker. Nếu một API ngoài đã nhận 80 request nhưng chunk fail trước commit metadata, restart có thể gửi lại chúng. Khi đó cần idempotency key ổn định theo business key, unique constraint, outbox hoặc đối soát.

Để tuning an toàn, phải đo cả **chi phí recovery sau lỗi**, không chỉ duration khi mọi item đều thành công.

## 10. Tương tác với database và writer

| Kiểu writer | Những điều nên đo khi tăng interval |
| --- | --- |
| `JdbcBatchItemWriter` | Round-trip, batch JDBC thực, transaction log, index update, lock wait và throughput ghi. |
| `JpaItemWriter` | Flush/clear của EntityManager, persistence context, dirty checking, JDBC batch và heap. |
| File writer | Flush, buffer, checkpoint, khả năng truncate/rollback sau restart. |
| HTTP/API writer | Timeout, rate limit, idempotency, số request và latency; chunk không tự tạo bulk API. |
| Message writer | ACK/transaction broker, dữ liệu trùng và cơ chế khôi phục. |
| Writer sang database thứ hai | Tính nhất quán giữa nhiều resource và phương án bù/đối soát. |

### JDBC batch không đồng nghĩa commit interval

`JdbcBatchItemWriter` dùng khả năng batching của JDBC. Dù vậy, driver có thể chia batch SQL, tối ưu/rewrite theo dialect hoặc chịu các giới hạn riêng. Việc tăng chunk không bảo đảm giảm số network round-trip theo đúng tỉ lệ.

Nếu writer đơn giản gọi `JdbcTemplate.update(...)` một lần cho mỗi item, việc tăng chunk chủ yếu giảm một phần transaction overhead; nó không tự chuyển các call thành một batch JDBC. Vì vậy phải tối ưu đúng tầng gây nghẽn.

### Lock, isolation và transaction timeout

Transaction dài có thể giữ lock và tăng contention. Với workload cùng cập nhật những bảng có nhiều người dùng, chunk 1.000 có thể làm hàng đợi database tăng hơn chunk 100. Nếu transaction timeout ngắn hoặc một item gọi API mất nhiều giây, interval lớn có thể khiến Step fail liên tục.

Cần đo p95/p99 thời gian transaction, không chỉ trung bình. Một số item bất thường có thể khiến một chunk bị kéo dài đột biến.

## 11. Bộ nhớ và concurrency

Mức bộ nhớ của một chunk có thể ước tính:

~~~text
memory ≈ items_in_chunk * average_item_footprint
       + processed_output_buffers
       + reader/writer_buffers
       + framework_and_application_state
~~~

Nếu mỗi item dùng khoảng 50 KiB sau khi tạo object:

| Chunk size | Footprint item ước tính, chưa tính overhead |
| ---: | ---: |
| 10 | khoảng 0,49 MiB |
| 100 | khoảng 4,88 MiB |
| 1.000 | khoảng 48,83 MiB |
| 10.000 | khoảng 488,28 MiB |

Đây là phép tính minh họa, không phải số liệu heap thực. Payload lớn, object graph hoặc cache của JPA có thể khiến footprint cao hơn nhiều.

Với partitioning hoặc multi-threaded Step, số chunk đang hoạt động cùng lúc cũng ảnh hưởng memory:

~~~text
Partition A -> chunk(100) -> transaction A
Partition B -> chunk(100) -> transaction B
Partition C -> chunk(100) -> transaction C
Partition D -> chunk(100) -> transaction D
~~~

Bốn partition có thể cùng giữ bốn chunk, còn cần connection, reader buffer, writer buffer và metadata transaction. Nếu tăng cả chunk size và concurrency trong một lần benchmark, rất khó xác định nguyên nhân hiệu năng hoặc lỗi.

Tối ưu commit interval và tối ưu concurrency là hai phép thử **riêng**, sau đó mới đánh giá tổ hợp đã chọn.

## 12. Thiết kế benchmark để chọn interval

Một quy trình benchmark đáng tin cậy cần có đường chạy bình thường, đường chạy gặp lỗi và đường chạy có tải cạnh tranh.

### Bước 1: xác định tiêu chí

Các chỉ tiêu thường cần:

- **Throughput**: số item nghiệp vụ hoàn thành mỗi giây.
- **End-to-end duration**: thời gian Job kết thúc.
- **Heap/GC**: peak heap, allocation rate, GC pause.
- **Database**: CPU, transaction latency, lock wait, deadlock, log I/O.
- **Step metadata**: read/write/filter/skip/commit/rollback count.
- **Recovery cost**: số item phải xử lý lại và thời gian restart sau lỗi.
- **SLA**: Job có hoàn thành đúng hạn mà không gây ảnh hưởng các tác vụ khác không?

Ví dụ nếu 100.000 item được ghi đúng trong 250 giây:

~~~text
throughput = 100000 / 250 = 400 item/second
~~~

Đây là phép tính minh họa. Với Job có filter/skip, cần định nghĩa rõ “completed item” là item đọc, item ghi hay đơn vị nghiệp vụ thành công.

### Bước 2: cố định các biến số khác

Trong một lượt thử, chỉ đổi chunk size; giữ nguyên:

- Số lượng, phân bố kích thước và thứ tự dữ liệu.
- Reader, processor, writer, SQL và index.
- JDBC driver, fetch size, page size, transaction isolation.
- JVM heap/GC, CPU, database instance và connection pool.
- Concurrency/partition count và mức tải cạnh tranh.
- Retry/skip policy, timeout và logging.
- Cách seed/reset dữ liệu và JobRepository giữa **những bài benchmark độc lập**.

Chạy warm-up, lặp lại mỗi cấu hình nhiều lần, đảo thứ tự chạy giữa các vòng để tránh thiên lệch từ cache nóng. Thống kê median/p95 thay vì chỉ lấy một lần nhanh nhất.

### Bước 3: thử một dải giá trị

Khởi đầu có thể thử:

~~~text
10 -> 50 -> 100 -> 250 -> 500 -> 1000
~~~

Đây là **dải thử**, không phải khuyến nghị mặc định. Item lớn hoặc HTTP call chậm có thể cần thử 1, 5, 10, 20. Với JDBC writer ghi row rất nhỏ, có thể mở rộng sang các giá trị lớn hơn sau khi chứng minh memory và lock vẫn ổn định.

Bảng ghi nhận thực nghiệm:

| Chunk size | Duration (s) | Throughput | Peak heap | DB lock wait | Rollbacks | Nhận xét |
| ---: | --- | --- | --- | --- | --- | --- |
| 10 | Đo | Đo | Đo | Đo | Đo | Điền sau run |
| 50 | Đo | Đo | Đo | Đo | Đo | Điền sau run |
| 100 | Đo | Đo | Đo | Đo | Đo | Điền sau run |
| 250 | Đo | Đo | Đo | Đo | Đo | Điền sau run |
| 500 | Đo | Đo | Đo | Đo | Đo | Điền sau run |
| 1000 | Đo | Đo | Đo | Đo | Đo | Điền sau run |

Không điền kết quả giả định rồi chọn giá trị thắng cuộc. Kết luận cần đến từ hệ thống và dataset thật.

### Bước 4: fault injection

Đo riêng tình huống lỗi tại item 231 hoặc gần cuối một chunk. Kiểm:

- Dữ liệu đã commit trước lỗi.
- Rollback của chunk chưa hoàn thành.
- Khả năng restart từ checkpoint.
- Dữ liệu cuối đủ, không trùng.
- Thời gian và số item bị xử lý lại.
- Side effect bên ngoài có được idempotency bảo vệ không.

Giá trị có throughput tốt khi không lỗi có thể làm chi phí restart tăng mạnh, nên cần nhìn cả hai kết quả.

### Bước 5: thử dưới contention

Chạy Job cùng lưu lượng thật hoặc một workload giả lập cạnh tranh trên database. Quan sát transaction timeout, lock wait, độ trễ tác vụ khác và connection pool. Giá trị tốt nhất ở máy benchmark trống có thể gây nghẽn trong production.

## 13. Monitoring qua StepExecution và Micrometer

Spring Batch lưu những metadata quan trọng trong `StepExecution`. Ví dụ listener Spring Batch 5.2.x:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepPerformanceListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepPerformanceListener.class);

    @Override
    public void afterStep(StepExecution step) {
        log.info(
            "step={} read={} write={} filter={} " +
            "commits={} rollbacks={} status={}",
            step.getStepName(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getStatus()
        );
    }
}
~~~

Đăng ký listener trên builder của Step:

~~~java
.listener(new StepPerformanceListener())
~~~

Những count này hỗ trợ đánh giá transaction và kết quả nghiệp vụ. Tuy nhiên:

- `COMMIT_COUNT` có thể không bằng chính xác `ceil(READ_COUNT / chunkSize)`.
- `ROLLBACK_COUNT` khác retry count.
- `READ_COUNT` và `WRITE_COUNT` khác nhau khi có filter/skip.
- Metadata không tự có p95 thời gian mỗi chunk hoặc thời gian giữ lock.

Nên kết hợp **Micrometer** (timer của Job/Step, metric xử lý item/chunk theo phiên bản), metric JVM và database. Nếu cần đo duration từng chunk, instrument ở listener phù hợp nhưng tránh log quá nhiều trên đường nóng.

Ví dụ các câu hỏi dashboard cần trả lời:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Step duration | Chunk size mới làm Step nhanh hơn không? |
| Throughput item/s | Bao nhiêu item thực được ghi thành công mỗi giây? |
| Commit/rollback count | Tần suất transaction và lỗi thay đổi thế nào? |
| Heap/GC | Chunk lớn có gây pressure bộ nhớ không? |
| DB lock wait, deadlock | Transaction dài có ảnh hưởng workload khác không? |
| Connection pool wait | Concurrency có vượt khả năng datasource không? |
| Recovery time | Job restart tốn bao lâu sau lỗi? |

Không gắn `jobExecutionId` hay item ID vào label Prometheus vì chúng tạo cardinality cao. Có thể giữ những ID này trong structured logs/traces, còn metrics dùng label ổn định như Job/Step/environment.

## 14. Test commit interval và rollback

Một integration test nên sử dụng **JDBC JobRepository thật** để kiểm checkpoint/restart. Không xóa metadata `BATCH_*` giữa lần fail và lần restart trong cùng test.

### Các ranh giới cần kiểm

| Tổng item | Chunk size | Mục đích |
| ---: | ---: | --- |
| 0 | 10 | Nguồn trống, Step kết thúc an toàn. |
| 1 | 10 | Một chunk cuối không đầy. |
| 9 | 10 | Ít hơn interval. |
| 10 | 10 | Bằng interval. |
| 11 | 10 | Một chunk đầy, một chunk cuối nhỏ. |
| 100 | 1 | Đường chạy nhiều transaction. |
| 100 | 100 | Đường chạy một chunk dữ liệu. |
| 101 | 100 | Phần dư qua ranh giới chunk. |

Với lỗi không retryable tại item 231, chunk size 100 và dataset 1.000 item có thứ tự ổn định, kỳ vọng đơn giản là 200 row đã commit ở bảng đích. Sau restart cùng JobInstance, có 1.000 row không trùng.

### Khung integration test Spring Batch 5.2.x

Giả sử có Job `importOrdersJob`, reader/writer JDBC, và một processor dùng `FailureSwitch` có thể ném exception xác định ở item 231:

~~~java
@SpringBatchTest
@SpringBootTest
class CommitIntervalIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    FailureSwitch failureSwitch;

    @Test
    void failedChunkRollsBackAndRestartResumes() throws Exception {
        // Trước test: seed 1.000 source rows, xóa output
        // và xóa metadata của test khác trên database test riêng.
        failureSwitch.failOnId(231L);

        JobParameters params = new JobParametersBuilder()
                .addString("caseKey", "chunk100-failure")
                .toJobParameters();

        JobExecution first = launcher.launchJob(params);
        assertEquals(BatchStatus.FAILED, first.getStatus());

        Integer beforeRestart = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_orders", Integer.class);
        assertEquals(200, beforeRestart);

        failureSwitch.disable();
        JobExecution second = launcher.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertEquals(first.getJobInstance().getInstanceId(),
                     second.getJobInstance().getInstanceId());

        Integer finalCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_orders", Integer.class);
        assertEquals(1000, finalCount);
    }
}
~~~

Đây là **khung minh họa**, cần tự triển khai `FailureSwitch`, dữ liệu test, các import và cấu hình bean. Để kỳ vọng 200 row đúng, processor phải ném lỗi **trước writer** ở item 231, Step không skip/retry lỗi đó, và writer phải tham gia transaction JDBC phù hợp. Nếu framework chạy bất đồng bộ, cần chờ trạng thái cuối trước khi assert.

Không đặt `@Transactional` bao trùm toàn bộ integration test nếu nó che khuất commit/rollback thực của Step. Test độ đúng của dữ liệu cần quan sát các transaction mà Batch đã commit.

### Kiểm test theo kích thước sau khi tuning

Với mỗi chunk size candidate, nên kiểm:

- Job `COMPLETED` khi dữ liệu hợp lệ.
- Kết quả nghiệp vụ đầy đủ, không duplicate.
- Rollback đúng và restart đúng khi lỗi giữa chunk.
- Không vi phạm transaction timeout.
- Không vượt giới hạn bộ nhớ khi dữ liệu lớn.
- Không gây deadlock khi chạy cùng tải cạnh tranh.

## 15. Tuning theo từng loại workload

**CPU-bound:** nếu ItemProcessor xử lý tính toán nặng, commit overhead có thể không phải bottleneck. Dùng profiler và đo CPU; cân nhắc partition/concurrency riêng nếu reader/writer/thread safety cho phép.

**JDBC write-heavy:** nếu row nhỏ và writer batch tốt, chunk vừa phải thường tạo lợi ích lớn hơn chunk 1. Đo JDBC batch thực, log I/O, lock và index; tăng chunk sau một ngưỡng có thể không giúp thêm.

**JPA:** chú ý persistence context, flush/clear và lazy relations. Một chunk lớn có thể giữ nhiều entity và tăng dirty-checking/GC. Không chỉ nhìn số lần commit.

**Large payload:** item vài MB nên thử chunk nhỏ. Memory footprint của object và buffer quan trọng hơn giảm vài lần commit.

**API-bound:** chunk lớn không giúp HTTP call tuần tự chạy song song. Nên ưu tiên timeout, bulk endpoint, cách gọi API, rate limit và idempotency.

**Mixed latency:** nếu một số item chỉ mất 1 ms nhưng item khác mất vài giây, chunk 100 có thể có duration rất khác nhau. Đo tail latency và cân nhắc completion policy phù hợp.

## 16. Thay đổi cấu hình trong production

Một thay đổi từ 100 lên 1.000 có thể cải thiện throughput nhưng cũng làm tăng transaction duration và chi phí restart. Quy trình phù hợp:

1. Ghi baseline: throughput, duration, GC, DB contention, rollback/recovery.
2. Chọn vài giá trị candidate và benchmark trên dataset đại diện.
3. Test lỗi có chủ đích, restart và side effect/idempotency.
4. Tách tác động chunk size khỏi fetch size/concurrency.
5. Cấu hình qua deployment và chỉ áp dụng ở lần tạo Step mới phù hợp.
6. Theo dõi sát số liệu sau triển khai, so với baseline.
7. Quay lại giá trị trước nếu SLA hoặc độ ổn định suy giảm.

Thay `application.yml` không bảo đảm Step đang chạy đổi commit interval ngay; cấu hình được đưa vào khi Step được tạo/cấu hình. Với một JobInstance `FAILED` sẽ restart, việc đổi interval có thể thay đổi transaction boundary mới. Điều đó cần được test với checkpoint, writer và dữ liệu cuối, nhất là khi code/schema/serializer cũng đổi.

Nếu một Job đã fail và đang chờ restart, **không xóa metadata** để thử lại bằng cách tạo JobInstance mới. Hãy giữ lịch sử, dùng JobParameters đúng và kiểm tính tương thích của thay đổi.

## 17. Khác biệt API Spring Batch 5.2 và 6.x

Cú pháp của bài ví dụ sử dụng Spring Batch 5.2.x:

~~~java
new StepBuilder("loadStep", jobRepository)
        .<Input, Output>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

Trong Spring Batch 6.x, cấu hình transaction manager được thể hiện bằng API builder tương ứng:

~~~java
new StepBuilder("loadStep", jobRepository)
        .<Input, Output>chunk(100)
        .transactionManager(transactionManager)
        .reader(reader)
        .writer(writer)
        .build();
~~~

Ở dòng 6.x, các reader/writer và interface item đã được tổ chức lại trong các module/package infrastructure, nên phải điều chỉnh import và dependency theo phiên bản đang dùng. Việc thiết lập JobRepository JDBC cũng cần tương thích với Spring Batch/Boot thực tế.

**Nguyên lý tuning giữ nguyên:** chunk size ảnh hưởng transaction, memory, writer throughput, rollback và restart. Nhưng không so sánh hiệu năng của hai phiên bản chỉ dựa vào commit count nếu datasource, transaction manager, JDBC driver, metadata schema hoặc cấu hình writer khác nhau.

## 18. Các sai lầm thường gặp

**Đặt chunk càng lớn càng tốt.** Chunk lớn có thể tăng memory, lock wait, transaction timeout và thời gian recovery.

**Đồng nhất fetch size với chunk size.** Đây là hai tầng khác nhau của reader và Step.

**Chỉ nhìn số commit lý thuyết.** Phải đo thời gian thực, throughput, heap và tải database.

**Không kiểm lỗi giữa chunk.** Một Job chạy thành công chưa chứng minh rollback/checkpoint và idempotency đúng.

**Dùng nhiều partition rồi tăng chunk cùng lúc.** Không thể nhận diện biến gây thay đổi hiệu năng.

**Không để ý filter/skip/retry.** Số item đọc và ghi không còn tương ứng trực tiếp; metadata cần được diễn giải đúng.

**Cho rằng rollback JDBC hoàn tác HTTP/email.** Side effect ngoài transaction có thể đã thành công và bị lặp khi restart.

**Thay interval khi restart mà bỏ qua tương thích state.** Reader, writer và ExecutionContext có thể phụ thuộc logic phiên bản trước.

**Không xét tải các ứng dụng khác trên database.** Kết quả benchmark chạy một mình có thể làm hại SLA chung.

**Bỏ qua dữ liệu lớn bất thường.** Item payload lớn có thể khiến cùng chunk size sử dụng memory gấp nhiều lần mức trung bình.

## 19. Bài tập thực hành

### Bài 1 — So sánh baseline

Dùng Job JDBC nhập 100.000 row. Chạy lần lượt chunk 10, 50, 100, 250, 500 và giữ nguyên các tham số khác. Ghi duration, throughput, commit/rollback, peak heap và lock wait. Chọn giá trị dựa trên cả hiệu năng lẫn ổn định.

### Bài 2 — Lỗi tại item 231

Chèn lỗi vào processor, chạy Job với chunk 10, 100 và 500. Quan sát số row đã commit trước lỗi và lượng dữ liệu phải xử lý lại khi restart. Kiểm dữ liệu cuối không thiếu/trùng.

### Bài 3 — Fetch size độc lập

Giữ chunk 100, thử fetchSize 50, 300 và 1.000 với JdbcCursorItemReader. Đo latency và memory theo JDBC driver. Giải thích vì sao fetch size thay đổi mà số chunk không nhất thiết thay đổi.

### Bài 4 — Filter và skip

Processor trả null cho 10% item, skip một số exception có thể bỏ qua. Kiểm read/write/filter/skip count; phân tích vì sao writer không luôn nhận đủ số item của commit interval.

### Bài 5 — Item lớn và multi-partition

Giả lập payload lớn và chạy với một partition, sau đó bốn partition. Giữ concurrency cố định trong từng phép so chunk size; đo peak heap, GC pause, DB contention và throughput.

### Bài 6 — API ngoài transaction

Writer gọi API với idempotency key ổn định theo business key; mock API trả timeout sau khi đã ghi hiệu lực thành công. Restart cùng JobInstance và kiểm không có tác dụng nghiệp vụ trùng.

### Bài 7 — Quyết định triển khai

Từ số liệu thực nghiệm, lập bảng tiêu chí gồm throughput tối thiểu, memory tối đa, transaction duration p95, lock wait và recovery time. Chọn một commit interval trong vùng hiệu năng ổn định và trình bày phương án rollback cấu hình nếu điều kiện production xấu đi.

## 20. Tài liệu tham khảo chính thức

- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers.html)
- [Spring Batch — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html)
- [Spring Batch — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html)
- [Spring Batch 5.2 — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — StepBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/step/builder/StepBuilder.html)

