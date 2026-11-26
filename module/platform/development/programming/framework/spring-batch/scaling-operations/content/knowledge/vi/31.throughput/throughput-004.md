# Write rate và flush cost trong Spring Batch

## 1. Tăng worker nhưng dữ liệu vẫn ghi chậm: vấn đề nằm ở đâu?

Một hệ thống thanh toán xử lý 20 triệu event mỗi đêm. Reader có thể đọc hơn 100.000 event/giây, processor gần như chỉ chuẩn hóa một vài trường, nhưng job chỉ **ghi thành công 8.000 event/giây**. Khi tăng worker từ 4 lên 16, dashboard báo `writeCount` tăng nhanh hơn ở giai đoạn đầu, rồi PostgreSQL xuất hiện nhiều transaction chờ I/O, `WALSync`, lock hoặc connection. Thời gian chạy tổng thể hầu như không giảm.

Tình huống ấy cần hai phép đo khác nhau:

1. **Write rate:** Trong một khoảng thời gian thực, có bao nhiêu item, row hoặc byte đã ghi thành công theo *định nghĩa nghiệp vụ*?
2. **Flush cost:** Việc đẩy dữ liệu từ buffer/driver/persistence context xuống tầng thấp hơn và bảo đảm mức durability mong muốn mất bao nhiêu thời gian, CPU, I/O, transaction hoặc lock?

Hai phép đo liên quan nhưng **không đồng nghĩa**. Một `ItemWriter.write(...)` trả về nhanh không chứng minh transaction đã commit bền vững. Một batch JDBC xử lý 500 tham số trong một lần gọi không bảo đảm driver gửi đúng một SQL statement. Một `EntityManager.flush()` gửi SQL không có nghĩa transaction đã commit. Và một PostgreSQL commit có liên quan đến WAL nhưng **không bắt buộc phải flush toàn bộ data pages ngay lúc commit**.

Bài **“Write rate và flush cost”** thuộc chương **Thông lượng** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các kiến trúc xử lý phân tán; đồng thời đo nút thắt, kiểm soát thread safety, retry/restart và lựa chọn phương án vận hành phù hợp tài nguyên.

Sau bài học, bạn có thể:

- Định nghĩa **attempted, writer-accepted, database-affected và committed business write rate** một cách tách bạch.
- Chỉ ra những lớp flush khác nhau: JDBC batch execute, Hibernate/JPA flush, file buffer flush/fsync và PostgreSQL WAL sync/checkpoint.
- Đo latency của `write()`, chunk commit, transaction, WAL và database I/O mà không đánh đồng các số liệu.
- Điều chỉnh chunk size, JDBC batch size, flush cadence và worker concurrency theo bằng chứng.
- Nhận biết bottleneck ở row lock, connection pool, WAL/disk, network, GC hoặc downstream service.
- Giữ correctness khi gặp crash trước/sau commit, retry, duplicate delivery và restart.
- Lập kế hoạch benchmark trên cùng snapshot, so sánh throughput thực với chi phí tài nguyên.

**Phiên bản dùng trong ví dụ:** Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, Spring JDBC/Micrometer và PostgreSQL. Một số API/import thay đổi ở Spring Batch 6.x; phải kiểm tra phiên bản đang triển khai. Chi tiết PostgreSQL WAL và Hibernate **không tự động áp dụng** cho mọi database hoặc JPA provider.

## 2. Đo write rate nào? Định nghĩa trước khi vẽ dashboard

Không nên gọi mọi đường biểu diễn “rows/s” là write throughput. Trong một job có filter, retry, upsert và duplicate input, các số đếm có ngữ nghĩa khác nhau.

| Đại lượng | Cách hiểu | Điểm dễ hiểu lầm |
|---|---|---|
| **Input/read rate** | Item được reader đưa vào pipeline trong một khoảng thời gian | Đọc nhanh không có nghĩa ghi nhanh |
| **Writer call rate** | Số lượt gọi `ItemWriter.write` trong một giây | Mỗi call có thể chứa 1, 100 hoặc 1.000 item |
| **Writer item rate** | Số item được truyền đến writer trong một giây | Item có thể gặp `ON CONFLICT DO NOTHING` hoặc rollback |
| **DB affected-row rate** | Số row INSERT/UPDATE/DELETE mà DB báo đã tác động | Với upsert, trigger, batch update-count đặc biệt, không bằng số business record |
| **Committed-row rate** | Số thay đổi thực sự commit ở DB theo contract | Cần đo sau commit hoặc đối soát DB, không chỉ trong `write()` |
| **Unique business key rate** | Số khóa nghiệp vụ hợp lệ mới/được chấp nhận sau commit mỗi giây | Phù hợp ETL idempotent, phân biệt duplicate delivery |
| **Write byte rate** | Số byte payload hoặc bytes thật ghi qua một tầng mỗi giây | Payload bytes, WAL bytes và disk bytes là ba mẫu số khác nhau |
| **Retry/rollback rate** | Số lần hoặc tỷ lệ làm lại/rollback | Rate tăng có thể làm worker bận nhưng hữu ích bằng 0 |

### 2.1. Write rate end-to-end

Với một job xử lý immutable snapshot và có thời điểm bắt đầu/kết thúc rõ ràng:

\[
R_{\mathrm{committed}}=
\frac{N_{\mathrm{business\ writes\ committed}}}
{T_{\mathrm{wall}}}
\]

Trong đó `T_wall` là thời gian **thực trôi qua**, bao gồm thời gian job chờ queue, đợi lock, commit, polling metadata và overhead điều phối. Nên báo song song `items/s`, `rows/s`, `MiB/s` và thời gian job hoàn tất nếu nghiệp vụ có bản ghi kích thước không đều.

Ví dụ: job đưa vào writer 1.000.000 item, 40.000 item là duplicate hợp lệ được `ON CONFLICT DO NOTHING` bỏ qua. `writeCount` có thể phản ánh số item đã qua writer, trong khi số row *mới được chấp nhận* chỉ là 960.000. Nếu dashboard dùng `writeCount / wall time` để kết luận 1.000.000 row đã được thêm vào DB thì kết luận sai.

### 2.2. Rate tức thời và trung bình

Một throughput chart nên dùng **delta trên cửa sổ thời gian**:

\[
R_{\Delta t}=\frac{N(t_2)-N(t_1)}{t_2-t_1}
\]

Một giá trị trung bình 20.000 rows/s có thể che đoạn 30 giây gần như không ghi được gì khi WAL sync hoặc lock wait tăng vọt. Nên xem **đồ thị theo thời gian** và phân vị latency `p50/p95/p99` bên cạnh throughput.

**Tránh đếm đôi retry:** nếu item được thử ba lần và chỉ commit một lần, attempted write rate có thể đếm ba lượt nhưng committed business rate chỉ tính **một kết quả hợp lệ**.

### 2.3. Write amplification

Một event nghiệp vụ nhỏ có thể tạo nhiều write ở database: row data, index, WAL, metadata, outbox, trigger, vacuum overhead. Có thể ước lượng:

\[
A_{\mathrm{WAL}}=
\frac{\Delta\mathrm{WAL\ bytes}}
{\mathrm{logical\ payload\ bytes\ committed}}
\]

Đây là **tỷ số quan sát để so sánh cùng workload**, không phải hằng số hay phép đo toàn bộ physical I/O. PostgreSQL WAL là tài nguyên chia sẻ toàn instance; đo một job cùng lúc với workload khác có thể khiến tỷ số bị nhiễu. Full-page images, index maintenance, transaction pattern và checkpoint cadence đều có thể làm WAL tăng.

## 3. Flush đi qua những tầng khác nhau

Từ “flush” có nghĩa khác nhau ở từng layer:

~~~mermaid
flowchart TD
    A[ItemWriter nhận Chunk] --> B[Application / ORM buffer]
    B --> C[JDBC executeBatch / SQL tới DB]
    C --> D[DB thực thi INSERT/UPDATE + ghi WAL buffers]
    D --> E[Transaction COMMIT]
    E --> F[WAL write/sync theo durability config]
    F --> G[Commit được xác nhận theo policy]
    D --> H[Dirty data pages trong shared buffers]
    H --> I[Background writer / checkpoint ghi data pages]
    G --> J[Job tiếp tục checkpoint/next chunk]
~~~

**Đường đi trong sơ đồ chỉ mang tính khái niệm**: DB có thể xen kẽ các hoạt động, WAL có thể được ghi trước commit và checkpoint có thể chạy song song; không phải mỗi chunk đều thực hiện lần lượt đủ tất cả node. Nhưng sơ đồ cho thấy **bốn thao tác không thể coi là một**:

1. **Flush buffer phía ứng dụng/JPA:** phát SQL từ bộ nhớ xuống database.
2. **JDBC batch execution:** driver/server xử lý nhiều bộ tham số.
3. **Transaction commit và WAL synchronization:** database quyết định khi nào báo commit thành công theo cấu hình durability.
4. **Flush dirty data pages/checkpoint:** đưa các trang dữ liệu đã sửa từ cache DB ra storage, có thể **sau commit**.

### Bảng đối chiếu nhanh

| Động tác | Ý nghĩa gần đúng | Có chứng minh business data đã commit và durable? |
|---|---|---|
| `ItemWriter.write(chunk)` trả về | Writer hoàn thành lời gọi theo contract của nó | **Không**, chunk transaction có thể còn chưa commit |
| `PreparedStatement.executeBatch()` trả về | Driver nhận kết quả thực thi batch SQL | **Không** nếu transaction chưa commit |
| `EntityManager.flush()` trả về | Provider đồng bộ persistence context bằng các SQL cần thiết | **Không**, flush khác commit |
| `FileWriter.flush()` trả về | Đẩy buffer từ application sang tầng file/OS | **Không mặc định**, cần xem fsync và filesystem |
| PostgreSQL `COMMIT` được xác nhận | Transaction đã commit theo policy server và replication setting | Có mức bảo đảm phụ thuộc `synchronous_commit`, fsync và topology |
| Database checkpoint hoàn tất | DB ghi tập trang dirty phù hợp và thiết lập điểm phục hồi | Không phải thao tác bắt buộc riêng cho từng chunk |
| Spring Batch checkpoint cập nhật | `ExecutionContext`/`StepExecution` ghi nhận tiến độ theo lifecycle | Không thay thế database/file durability hoặc idempotency |

**Điểm mấu chốt:** đo thời gian của một lời gọi `write()` là đo **writer-call latency**; không đặt tên metric đó là `durable_flush_ms`.

## 4. JDBC batch write: giảm round-trip, không bỏ transaction

Với Spring Batch 5.2, `JdbcBatchItemWriter` thường dùng Spring JDBC batch update để nhận một `Chunk<T>` và gửi các bộ tham số cho một SQL template.

### 4.1. Bảng nguồn và bảng đích

Ví dụ xử lý bản ghi immutable trong snapshot:

~~~sql
CREATE TABLE incoming_payments (
    id           BIGINT PRIMARY KEY,
    snapshot_key VARCHAR(80) NOT NULL,
    account_id   BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_incoming_payments_snapshot_id
    ON incoming_payments (snapshot_key, id);

CREATE TABLE applied_payments (
    snapshot_key VARCHAR(80) NOT NULL,
    payment_id   BIGINT NOT NULL,
    account_id   BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_key, payment_id)
);
~~~

Unique key `(snapshot_key,payment_id)` là hàng rào nhận diện duplicate **cho một snapshot**. Nếu cùng key xuất hiện lại với số tiền khác, `DO NOTHING` sẽ không tự báo sự mâu thuẫn ấy; ứng dụng phải validate/checksum khi hợp đồng nguồn yêu cầu input bất biến.

### 4.2. Writer Java dùng JDBC batching

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record PaymentRow(
        long id, String snapshotKey, long accountId, long amountCents) {}

@Configuration
public class PaymentWriterConfiguration {

    @Bean
    public JdbcBatchItemWriter<PaymentRow> paymentJdbcWriter(
            @Qualifier("businessDataSource") DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<PaymentRow>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO applied_payments
                        (snapshot_key, payment_id, account_id, amount_cents)
                    VALUES
                        (:snapshotKey, :id, :accountId, :amountCents)
                    ON CONFLICT (snapshot_key, payment_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("snapshotKey", item.snapshotKey())
                                .addValue("id", item.id())
                                .addValue("accountId", item.accountId())
                                .addValue("amountCents", item.amountCents()))
                .assertUpdates(false)
                .build();
    }
}
~~~

`PaymentRow` là record package-private đặt cùng package với step/readers; nếu dùng ở package khác, khai báo trong `PaymentRow.java` dưới dạng `public`. `businessDataSource` phải là bean ứng dụng thực sự dùng để ghi data nghiệp vụ.

`assertUpdates(false)` là lựa chọn **có chủ đích** cho `ON CONFLICT DO NOTHING`, vì duplicate hợp lệ gây 0 row inserted. Với một `UPDATE ... WHERE version = :expectedVersion` mà mỗi item *bắt buộc* cập nhật một row, đặt `assertUpdates(true)` và phân loại 0-row conflicts rõ ràng, thay vì giấu mất dữ liệu.

### 4.3. Worker step, chunk và commit

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

// Phương thức thuộc class @Configuration của worker:
@Bean
public Step paymentLoadStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        @Qualifier("paymentReader")
        JdbcCursorItemReader<PaymentRow> paymentReader,
        @Qualifier("meteredPaymentWriter")
        ItemWriter<PaymentRow> meteredPaymentWriter) {

    return new StepBuilder("paymentLoadStep", jobRepository)
            .<PaymentRow, PaymentRow>chunk(500, businessTransactionManager)
            .reader(paymentReader)
            .writer(meteredPaymentWriter)
            .build();
}
~~~

`paymentReader` và `meteredPaymentWriter` cần bean tương ứng; phần tiếp theo xây metered writer. Reader JDBC stateful trong partitioning nên dùng `@StepScope` theo `StepExecution` và `ItemStream` checkpoint ổn định. Việc khai báo kiểu `JdbcCursorItemReader` trong wiring cũng giúp framework nhận diện interface `ItemStream` qua scoped proxy, thay vì che interface đó sau một kiểu trả về `ItemReader` quá chung. Ví dụ minh họa **wiring**, không phải một application hoàn chỉnh chỉ copy là chạy.

### 4.4. `chunk(500)` không có nghĩa “flush đúng 500 row”

Nếu processor filter 50 item, writer có thể chỉ nhận 450 item. Trong 450 item đó, 20 item gặp unique conflict và được `DO NOTHING`, số row mới chỉ có thể là 430. Một chunk cũng có thể chứa ít item hơn ở cuối input hoặc được replay sau rollback.

`writeCount` của Spring Batch phản ánh số item qua tầng writer theo lifecycle; **không phải một đồng hồ đếm row mới đã commit tại database**, nhất là với UPSERT, triggers, skip, retry và hệ thống có nhiều datasource.

### 4.5. pgjdbc reWriteBatchedInserts

PostgreSQL JDBC driver có tùy chọn:

~~~properties
# Ví dụ URL với pgjdbc, không phải property Spring Batch:
jdbc:postgresql://db.internal:5432/app?reWriteBatchedInserts=true
~~~

Với **SQL INSERT phù hợp**, driver *có thể* rewrite các bộ tham số JDBC batch thành dạng multi-row SQL để giảm lượt gọi/overhead. Khả năng áp dụng phụ thuộc **version pgjdbc, SQL shape, RETURNING/UPSERT và batch behavior**. Không tuyên bố rewrite chắc chắn xảy ra với `ON CONFLICT` ở trên: phải quan sát driver/server query logs hoặc benchmark trên đúng version/SQL.

Một batch chứa N parameter sets **không** có nghĩa server luôn nhận một network packet, một statement hoặc một lần flush WAL. Đây là ba tầng tối ưu khác nhau.

## 5. JPA/Hibernate: flush persistence context không phải COMMIT

Với JPA, `EntityManager.persist(entity)` hoặc `merge(entity)` có thể **ghi nhận thay đổi trong persistence context** trước khi SQL thật sự được phát ra. `EntityManager.flush()` yêu cầu provider đồng bộ những thay đổi cần thiết xuống database. Nhưng transaction vẫn có thể rollback sau flush.

~~~mermaid
sequenceDiagram
    participant S as ItemWriter/JpaItemWriter
    participant E as EntityManager
    participant D as Database
    S->>E: persist/merge nhiều entity
    Note over E: Persistence context / dirty checking
    S->>E: flush()
    E->>D: INSERT/UPDATE theo provider/batching
    D-->>E: SQL execution result
    Note over S,D: Transaction chưa chắc đã commit
    S-->>D: commit ở transaction boundary
~~~

### 5.1. Flush cost trong ORM

Chi phí có thể đến từ:

- Dirty checking của nhiều managed entities.
- Lập kế hoạch/thứ tự các SQL INSERT/UPDATE/DELETE.
- Phát statements qua JDBC, kiểm tra optimistic version và constraint.
- Memory/GC do persistence context tích lũy nhiều entity.
- JDBC batch behavior thay đổi theo ID generator, cascade, association và provider settings.

`flush()` thường cần khi application cần SQL được thực thi trước một truy vấn/kiểm tra khác trong transaction. **Không chủ động gọi flush từng item để “đảm bảo dữ liệu”**: nó có thể phá hiệu quả batching, tăng round-trip và vẫn chưa tạo commit durable.

### 5.2. JpaItemWriter và cấu hình Hibernate batching

Trong Spring Batch 5.x, `JpaItemWriter` được dùng để ghi entities qua JPA. Với Hibernate, một cấu hình ứng dụng minh họa:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

`hibernate.jdbc.batch_size=50` là **batch size của Hibernate JDBC layer**, khác với `chunk(500)`. Nếu chunk có 500 entities, provider có thể chia thành nhiều lô JDBC nhỏ hơn; số statement thực phụ thuộc loại entity, ID generation, relationship và flush boundaries.

**Các điểm cần thử trên ứng dụng thực tế:**

1. `GenerationType.IDENTITY` có thể hạn chế/bỏ JDBC insert batching trong nhiều phiên bản Hibernate; kiểm tra SQL/log driver thay vì giả định.
2. `saveAll(...)` của một repository JPA **không tự chứng minh** đã dùng JDBC batching hiệu quả.
3. `order_inserts/order_updates` có thể cải thiện nhóm SQL nhưng làm thay đổi thứ tự phát lệnh; phải kiểm thử constraint và business semantics.
4. `JpaItemWriter` có hành vi flush/clear theo implementation/version, không tự thay đổi bằng một `EntityManager.flush()` ở processor.
5. Tương tác với JPA first-level cache, cascade và optimistic locking có thể khiến mỗi chunk giữ nhiều đối tượng hơn số lượng item đơn giản.

### 5.3. Flush rồi rollback

~~~text
Transaction bắt đầu
  persist 100 entity
  EntityManager.flush() trả về thành công
  xảy ra lỗi validation/API/transaction
ROLLBACK

=> 100 row có thể đã được SQL engine xử lý tạm thời,
   nhưng không được commit như kết quả nghiệp vụ hợp lệ.
~~~

Đừng tăng một counter “committed_rows” ngay sau `flush()`. Nếu cần tốc độ ghi bền vững, theo dõi kết quả **sau commit** hoặc đối soát dữ liệu được chấp nhận trong database.

## 6. File output: flush buffer khác fsync và khác hoàn tất job

Write rate cũng áp dụng cho `FlatFileItemWriter`, CSV export hoặc một worker ghi file tạm lên local disk trước khi upload object storage.

| Thao tác | Điều có thể được bảo đảm | Điều chưa được bảo đảm |
|---|---|---|
| `write(...)` vào application buffer | Nội dung được đưa vào bộ đệm writer | Chưa chắc OS đã nhận và chưa commit chunk |
| `flush()` ở writer/file stream | Buffer ở tầng ứng dụng được đẩy xuống tầng kế tiếp | Chưa chắc được đồng bộ bền vững trên thiết bị |
| `FileChannel.force(...)` / fsync tương đương | Yêu cầu OS flush nội dung/metadata ra storage theo filesystem/OS contract | Không biến file output và DB metadata thành một distributed transaction |
| Đóng file | Hoàn tất lifecycle handle/buffer | Không tự xác nhận upload/consumer downstream đã thành công |
| Upload object storage hoàn tất | API báo kết quả theo contract provider | Downstream processing/audit vẫn cần xác nhận riêng |

`FlatFileItemWriter` có tùy chọn `forceSync` trên các phiên bản Spring Batch hỗ trợ; bật tùy chọn tăng yêu cầu đồng bộ file, có thể **tăng latency đáng kể** tùy storage. Không coi mọi `flush()` là fsync, cũng không dựa vào fsync để giải quyết vấn đề restart/idempotency ở tầng job.

### Ví dụ cấu hình FlatFileItemWriter (Spring Batch 5.x)

~~~java
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineAggregator;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

// Đặt trong class @Configuration, đây là method @Bean minh họa:
@Bean
public FlatFileItemWriter<PaymentRow> csvPaymentWriter() {
    DelimitedLineAggregator<PaymentRow> aggregator =
            new DelimitedLineAggregator<>();
    aggregator.setDelimiter(",");
    aggregator.setFieldExtractor(item -> new Object[] {
            item.id(), item.snapshotKey(),
            item.accountId(), item.amountCents()
    });

    FlatFileItemWriter<PaymentRow> writer =
            new FlatFileItemWriterBuilder<PaymentRow>()
                    .name("csvPaymentWriter")
                    .resource(new FileSystemResource(
                            "/var/batch/out/payments.csv"))
                    .lineAggregator(aggregator)
                    .build();

    writer.setForceSync(true); // Cân nhắc chi phí và durability requirement.
    return writer;
}
~~~

Đây là ví dụ writer output, cần cung cấp thư mục/permission, lifecycle, header/escaping, format và input snapshot. `DelimitedLineAggregator` trong ví dụ **chỉ phân tách trường bằng dấu phẩy**, không tự bảo đảm CSV quoting/escaping đầy đủ khi dữ liệu text chứa dấu phẩy, ngoặc kép hoặc xuống dòng; cần bổ sung encoder CSV chuẩn nếu nguồn có những ký tự đó. Trong production, cân nhắc **ghi tệp tạm theo run/partition → đóng và validate → atomic rename trong cùng filesystem hoặc publish object version** để giảm nguy cơ downstream đọc tệp chưa hoàn tất. Rename, object storage publish và `JobRepository` đều có failure semantics riêng.

Nếu nhiều partition cùng ghi **một filename**, dữ liệu có thể lẫn/ghi đè. Mỗi partition nên sở hữu output key riêng; manager có thể merge sau khi tất cả partition hoàn tất. `@StepScope` giúp late-bind tên output riêng theo `StepExecution` nhưng **không tự khiến một file được ghi đồng thời bởi nhiều thread trở nên an toàn**.

## 7. PostgreSQL: commit, WAL sync và checkpoint là ba việc khác nhau

PostgreSQL dùng **Write-Ahead Logging (WAL)**. Khi transaction sửa dữ liệu, database sinh WAL records phục vụ crash recovery. Theo cấu hình durability thông thường, commit acknowledgment liên quan tới việc ghi/đồng bộ WAL thích hợp; **dirty data pages không nhất thiết phải được ghi xuống data files ở cùng thời điểm**.

~~~mermaid
flowchart TD
    U[UPDATE / INSERT] --> B[Buffers + WAL records]
    B --> C[COMMIT request]
    C --> F[WAL write/sync theo synchronous_commit và I/O]
    F --> A[Commit acknowledgment]
    B --> D[Dirty data pages]
    D --> K[Checkpoint/background writer]
    K --> S[(Data files on storage)]
    F --> W[(WAL files)]
~~~

### 7.1. Những thuật ngữ cần phân biệt

- **WAL records/bytes:** log vật lý/logic phát sinh từ các thay đổi theo cơ chế WAL; số byte không phải payload size.
- **WAL write:** chuyển WAL buffer xuống tầng ghi của OS/filesystem theo database implementation.
- **WAL sync:** yêu cầu đồng bộ WAL cần thiết theo durability policy; có thể tạo commit latency.
- **Group commit:** nhiều commit có thể chia sẻ công việc đồng bộ WAL; tổng `wal_sync` không nhất thiết bằng số transaction commit.
- **Checkpoint:** đưa một tập dirty pages ra storage và tạo điểm phục hồi; có thể gây áp lực I/O theo chu kỳ nhưng **không phải là “flush data files của từng chunk ngay tại COMMIT”**.
- **Full-page image:** PostgreSQL có thể ghi thêm hình ảnh trang trong WAL trong một số điều kiện, làm WAL bytes tăng.

### 7.2. Cấu hình durability là quyết định nghiệp vụ

`synchronous_commit` ảnh hưởng thời điểm PostgreSQL xác nhận commit so với WAL sync/replication tùy topology; `fsync` ảnh hưởng bảo đảm crash safety. **Không tắt `fsync` hoặc giảm mức durability của dữ liệu tài chính chỉ để làm biểu đồ write rate đẹp hơn**.

Một thay đổi `synchronous_commit` có thể cải thiện latency trong một số workload nhưng đồng thời chấp nhận **rủi ro mất các giao dịch đã báo thành công khi crash** tùy setting. Bất kỳ thay đổi nào cũng cần business sign-off, recovery objective và diễn tập crash/recovery; không xem đó là một “tuning knob” vô hại.

### 7.3. Vì sao chunk quá nhỏ thường tốn commit cost?

Nếu có một triệu item và chunk 50, số chunk transaction nhiều hơn đáng kể so với chunk 500. Nếu mỗi commit có overhead đáng kể, các chunk rất nhỏ có thể làm overhead commit/WAL sync/metadata update chiếm phần lớn thời gian.

Ngược lại, một chunk 20.000 item có thể giữ transaction và locks lâu, tăng memory và chi phí rollback. **Mục tiêu không phải giảm số COMMIT xuống bằng 1**, mà tìm mức throughput tốt nhất với latency, memory, lock và restart an toàn.

## 8. Tách writer-call latency, commit latency và end-to-end rate

Một sơ đồ thời gian của **một chunk**:

~~~text
|--------- READ + PROCESS ---------|
                                  |----- ItemWriter.write() -----|
                                        JDBC executeBatch / JPA flush
                                                                |--- COMMIT ---|
                                                                              | metadata/context
                                                                              | tiếp tục chunk sau

Thời gian gọi ItemWriter.write() != thời gian COMMIT
Thời gian COMMIT != thời gian hoàn tất job
COMMIT thành công ở business DB != bảo đảm metadata/broker cùng commit
~~~

Ba phép đo bổ sung nhau:

- **`writer_call_duration`:** từ trước khi gọi `delegate.write(chunk)` đến lúc method trả về/ném exception.
- **`chunk_duration`:** thời gian cả chunk, bao gồm đọc/xử lý/ghi và transaction boundary theo hook quan sát cụ thể.
- **`committed_business_rate`:** tốc độ business keys thực sự được chấp nhận sau commit, đo từ bảng đích/ledger hoặc thông tin sau commit đáng tin cậy.

Nếu `writer_call_duration` thấp nhưng `chunk_duration` cao, có thể thời gian commit, read/process hoặc metadata update mới là bottleneck. Nếu `chunk_duration` thấp nhưng job wall-clock lớn, cần kiểm tra queue, phân phối partition, polling manager, slowest partition và startup/shutdown overhead.

### 8.1. Đo một writer JDBC bằng Micrometer

Ví dụ một decorator đo thời gian **lời gọi** writer và lượng item đã **được đưa vào attempt**, không gán nhãn “committed”:

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MeteredWriterConfiguration {

    @Bean("meteredPaymentWriter")
    public ItemWriter<PaymentRow> meteredPaymentWriter(
            @Qualifier("paymentJdbcWriter")
            JdbcBatchItemWriter<PaymentRow> delegate,
            MeterRegistry registry) {

        Timer callTimer = Timer.builder("batch.writer.call.duration")
                .tag("writer", "payments")
                .description("Time spent inside delegate ItemWriter.write")
                .register(registry);

        Counter attemptedItems = Counter.builder("batch.writer.items.attempted")
                .tag("writer", "payments")
                .description("Items passed to writer, including retries")
                .register(registry);

        return chunk -> {
            attemptedItems.increment(chunk.size());
            long started = System.nanoTime();
            try {
                delegate.write(chunk);
            } finally {
                callTimer.record(
                        System.nanoTime() - started, TimeUnit.NANOSECONDS);
            }
        };
    }
}
~~~

`PaymentRow` và `paymentJdbcWriter` được khai báo ở phần 4. Hàm `System.nanoTime()` phù hợp đo khoảng thời gian trong process, không phải đồng hồ thời gian thực. `finally` ghi nhận cả lần **thất bại**, vì lỗi là một phần của latency distribution; nên có counter lỗi riêng nếu cần phân biệt success/failure.

**Giới hạn của decorator:**

- Bộ đếm `attemptedItems` **cố ý có thể đếm lại item bị retry**.
- `callTimer` chỉ đo khoảng thời gian `write()`, **không bao gồm commit** xảy ra sau đó.
- `ItemWriter` ở đây chỉ là interface ghi; nếu bọc một delegate có thêm `ItemStream.open/update/close`, decorator phải chuyển tiếp lifecycle phù hợp hoặc để framework đăng ký `ItemStream` riêng. `JdbcBatchItemWriter` không yêu cầu checkpoint reader kiểu cursor.
- Không đưa `jobExecutionId`/`stepExecutionId` làm tag mọi time series dài hạn nếu cardinality quá cao; dùng structured logs/traces để định vị execution cụ thể.

### 8.2. Spring Batch listener đo ở mốc nào?

`ItemWriteListener.beforeWrite/afterWrite/onWriteError` giúp quan sát thời điểm writer. Nhưng `afterWrite` được gọi **trước transaction commit** theo lifecycle chunk, không phải callback xác nhận durability.

`ChunkListener.afterChunk` thường được gọi sau khi transaction chunk hoàn tất thành công trong processing lifecycle. Dù vậy, phải hiểu **transaction manager đang bao phủ resource nào**. Với business DB, metadata DB và broker là các resource tách biệt, một callback phía Spring Batch không tự trở thành biên giới exactly-once xuyên mọi hệ thống.

Để đo kết quả đã commit, có thể kết hợp:

1. Listener/transaction synchronization phù hợp và **không phát sự kiện business sớm trước commit**.
2. Counter từ **bảng ledger/idempotency** hoặc outbox đã commit.
3. Query đối soát snapshot/partition theo business key, chấp nhận độ trễ cập nhật metric.

Trong production, nếu metric mất một lần increment khi pod chết nhưng DB đã commit, đó là lý do **không dùng in-memory counter làm nguồn sự thật tài chính**.

### 8.3. Phân rã latency tương đối

Có thể phân tích một chunk theo:

\[
T_{\mathrm{chunk}}\approx
T_{\mathrm{read}}+T_{\mathrm{process}}
+T_{\mathrm{writer}}+T_{\mathrm{commit}}
+T_{\mathrm{metadata}}+T_{\mathrm{overhead}}
\]

Các thành phần có thể chồng lấn hoặc được tính ở các hook khác nhau; phép cộng là **mô hình tư duy**, không được lấy tổng các timer không đồng nhất rồi suy thành số chính xác. Bắt đầu bằng wall-clock chunk và writer-call timer, sau đó dùng DB transaction/WAL metrics để xác định phần chờ chưa lý giải.

## 9. PostgreSQL metrics cho WAL/flush cost

Để biết WAL có đang giới hạn write throughput hay không, cần đọc số liệu có **phạm vi và thời gian** rõ ràng.

### 9.1. Thống kê WAL toàn instance

Trên các bản PostgreSQL có `pg_stat_wal` và các trường tương ứng:

~~~sql
SELECT wal_records,
       wal_fpi,
       wal_bytes,
       wal_write,
       wal_sync,
       wal_write_time,
       wal_sync_time,
       stats_reset
FROM pg_stat_wal;
~~~

- `wal_records`: số WAL records.
- `wal_fpi`: số full-page images được ghi.
- `wal_bytes`: WAL bytes sinh ra kể từ thời điểm thống kê được reset.
- `wal_write` và `wal_sync`: số thao tác write/sync WAL được ghi nhận theo cơ chế PostgreSQL.
- `wal_write_time` và `wal_sync_time`: thời gian liên quan, **chỉ có ý nghĩa nếu cấu hình thu thập timing phù hợp** (chẳng hạn `track_wal_io_timing` tùy phiên bản).
- `stats_reset`: mốc bắt đầu phạm vi thống kê.

Các counter này **tích lũy**, không phải rate. Nên lấy hai snapshot `t0, t1` rồi tính delta. `pg_stat_wal` thuộc **toàn instance PostgreSQL**, nên các workload khác có thể làm số liệu thay đổi; benchmark cần môi trường cách ly hoặc ghi rõ nhiễu.

### 9.2. Thống kê transaction/IO theo database

~~~sql
SELECT datname,
       xact_commit,
       xact_rollback,
       blks_read,
       blks_hit,
       temp_bytes,
       stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

`xact_commit` là counter transaction commit của **database**, không đồng nghĩa số **Spring Batch chunk committed**: các ứng dụng khác cũng có transaction; một chunk còn có thể dùng nhiều resource/transaction tùy cấu hình.

`blks_read` và `blks_hit` mô tả truy cập block qua buffer manager, không phải toàn bộ byte ghi xuống storage. Muốn nhìn sâu vào data-file IO/checkpoint, tùy phiên bản có thể dùng `pg_stat_io`, `pg_stat_bgwriter`, `pg_stat_checkpointer` và monitoring của storage; **schema/metrics của các view thay đổi theo PostgreSQL version**.

### 9.3. Quan sát wait event ngay khi chậm

~~~sql
SELECT state,
       wait_event_type,
       wait_event,
       count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Gợi ý đọc dữ liệu:

| Tín hiệu | Có thể liên quan | Cần phân biệt thêm |
|---|---|---|
| Wait event thuộc WAL sync/write | WAL I/O hoặc commit path | Storage latency, group commit, config và load khác |
| `wait_event_type='Lock'` | Row/transaction/table lock contention | Hot keys, transaction lifetime, blocker PID |
| `wait_event_type='IO'` | Chờ storage | Read/write IO, buffer cache, checkpoint pressure |
| Nhiều `idle in transaction` | Code giữ transaction quá lâu | Network call/long processor, connection hold |
| Hikari pending cao nhưng DB CPU thấp | Pool starvation hoặc app giữ connection | Cursor reader, nested transactions, lock waits |
| DB CPU cao, WAL thấp | SQL/index/trigger/CPU xử lý | Query plan, JIT/CPU profile, số connection |

**Không quy mọi wait event liên quan I/O thành WAL flush.** PostgreSQL có nhiều loại I/O; tên `wait_event` cụ thể khác nhau giữa version và backend.

### 9.4. Explain có chi phí và gây tác động thật

Để phân tích một câu UPDATE/INSERT trên staging:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE applied_payments
SET amount_cents = amount_cents + 1
WHERE snapshot_key = 'test-snapshot'
  AND payment_id BETWEEN 1000 AND 2000;
~~~

**`EXPLAIN ANALYZE` thực thi câu lệnh**, có thể sửa dữ liệu và tạo WAL. Chỉ chạy với dữ liệu giả hoặc trong transaction kiểm soát và rollback trên staging, không chạy bừa trên production. Kết quả `WAL` của `EXPLAIN` cho biết số liệu của statement đó, không bao gồm mọi tác động hệ thống sau này.

## 10. Một bài toán Little's Law và queue/backpressure

Nếu upstream đẩy 50.000 item/giây nhưng writer stage chỉ commit 20.000 item/giây, hàng đợi đầu vào sẽ lớn dần. Trên một khoảng ngắn trước khi hệ thống chạm giới hạn, backlog tăng gần bằng:

\[
\Delta Q \approx
(R_{\mathrm{arrival}}-R_{\mathrm{committed}})\times \Delta t
\]

Ở trạng thái ổn định, **arrival rate lâu dài phải thấp hơn service capacity bền vững**, hoặc pipeline phải có cơ chế throttle, buffering có giới hạn và xử lý tồn đọng. Đẩy thêm dữ liệu vào JVM/broker không làm một database ghi nhanh hơn.

### Nơi đặt backpressure

~~~mermaid
flowchart LR
    A[Input reader / producer] --> Q[Bounded queue]
    Q --> W[Worker concurrency limiter]
    W --> DB[(Business DB)]
    DB --> M[Commit-confirmed progress]
    M --> C[Checkpoint / next work]
~~~

- **Multi-threaded step:** giới hạn `TaskExecutor` threads/queue, kiểm tra reader thread safety.
- **Local partitioning:** giới hạn partition executor, số cursor readers đồng thời và business pool.
- **Remote partitioning:** giới hạn consumer concurrency/in-flight `StepExecution` và tính `replicas × maximumPoolSize`.
- **Remote chunking:** manager đọc/chia chunk, worker ghi; cần giới hạn số chunk đang in-flight và size message, không để queue tăng vô hạn.
- **Remote step 6.x:** chuyển một logical step tới worker không mặc nhiên chia thành nhiều phần để tăng committed rate.

Tăng concurrency chỉ có ích khi bottleneck đang ở CPU/app layer **và** database/downstream còn dư năng lực. Nếu WAL/disk hoặc hot row đang bão hòa, thêm worker thường làm p95 write/commit latency tăng, thậm chí giảm throughput.

### Little's Law chỉ là công cụ giải thích

Trong một hệ thống tương đối ổn định:

\[
L\approx\lambda W
\]

`L` là số request đang ở hệ thống trung bình, `\lambda` throughput và `W` latency trung bình. Nếu commit latency tăng gấp đôi trong khi muốn giữ throughput, số request đồng thời cần cũng tăng theo; nhưng đây **không phải công thức ấn định pool size** khi có burst, lock, cursor lâu, failure/retry hay database đã bão hòa.

## 11. Chunk size, JDBC batch size và worker count: ba núm cần chỉnh riêng

| Núm chỉnh | Khi tăng có thể cải thiện | Khi tăng quá mức có thể gây |
|---|---|---|
| **Spring Batch chunk size** | Ít commit/checkpoint overhead hơn trên mỗi item | Transaction dài, lock lâu, rollback đắt, memory lớn |
| **JDBC batch size** | Giảm round-trip/driver overhead | BatchUpdateException khó cô lập item, buffer lớn, parameter limit |
| **JPA/Hibernate batch size** | Gộp SQL cùng loại, giảm ORM write overhead | Provider/ID generator có thể giới hạn, persistence context vẫn lớn |
| **Worker concurrency** | Dùng CPU/IO song song nếu bottleneck ở app | Pool/lock/WAL/DB contention, skew và retry storm |
| **Pool maximumSize** | Giảm thời gian đợi connection khi DB còn headroom | Nhiều session tranh CPU/IO/lock, vượt `max_connections` |
| **Flush cadence** | Ít flush thủ công hơn có thể giúp JDBC/ORM batching | Memory lớn, phát hiện lỗi trễ, transaction dài nếu thiếu kiểm soát |

### Ví dụ một thay đổi hợp lý

Giả sử chạy `chunk(50)`, một worker và database có p95 commit đáng kể nhưng gần như không có lock wait. Thử `chunk(200)` rồi `chunk(500)` có thể giảm overhead commit trên mỗi item. Sau đó, **giữ nguyên chunk** và thử tăng worker từ 1 lên 2, 4; nếu WAL sync latency và DB disk pressure tăng mạnh mà throughput không còn tăng, dừng scale.

Ngược lại, nếu một chunk 5.000 item chứa xử lý HTTP chậm trong transaction, giảm chunk và tách HTTP qua outbox có thể cải thiện hơn việc bật JDBC rewrite.

### JDBC và JPA có batch size khác nhau

Một step `chunk(500)` với `JdbcBatchItemWriter` thường đưa tối đa 500 parameter sets vào một lần batch update theo call của writer. Cũng với `chunk(500)` nhưng dùng Hibernate `hibernate.jdbc.batch_size=50`, provider có thể chia nhiều nhóm SQL nhỏ hơn; còn `EntityManager.flush()` là đồng bộ persistence context, không phải cam kết “gửi hết thành một statement”.

**Không cùng lúc chỉnh chunk, Hibernate batch size và số pod** rồi kết luận vì sao write rate tăng. Thay từng yếu tố và giữ snapshot/SQL/index/JDK/driver/pool không đổi giữa các lượt.

## 12. Các chiến lược giảm flush cost mà không đánh đổi tính đúng

### 12.1. Dùng JDBC batching hoặc set-based SQL khi phù hợp

Nếu business transformation có thể diễn đạt hoàn toàn bằng SQL, `INSERT ... SELECT` hoặc `UPDATE ... FROM` theo **partition range** có thể tránh mang từng row qua JVM, giảm overhead mạng và object allocation. Nhưng một statement tác động hàng triệu row vẫn có thể tạo transaction quá lớn; chia thành các tập có checkpoint và idempotency.

Nếu có logic Java phức tạp, `JdbcBatchItemWriter` giúp tái sử dụng prepared SQL và tích hợp transaction của Spring Batch.

### 12.2. Giảm update không cần thiết

Đối với bảng projection, chỉ update khi giá trị thực sự thay đổi:

~~~sql
UPDATE applied_payments
SET amount_cents = :newAmount
WHERE snapshot_key = :snapshotKey
  AND payment_id = :paymentId
  AND amount_cents IS DISTINCT FROM :newAmount;
~~~

Điều kiện trên có thể giảm WAL/dirty page và lock giữ không cần thiết; tuy nhiên nếu writer đang dùng optimistic version, **0 updated rows cần được giải thích**. Không đặt `assertUpdates(false)` rồi coi mọi row không thay đổi là thành công nếu nghiệp vụ bắt buộc phát hiện missing row/conflict.

### 12.3. Giảm index/write amplification có kiểm soát

Mỗi INSERT/UPDATE có thể phải duy trì primary key, secondary indexes, FK và triggers. Xem index nào phục vụ read path và constraint thực, tránh index dư; nhưng **không bỏ unique key bảo vệ idempotency** chỉ để tăng write throughput.

Ở PostgreSQL, một số UPDATE không thay cột được index có thể dùng **HOT update** nếu điều kiện storage phù hợp, giúp giảm index maintenance; đây là một optimization do database quyết định, không phải bảo đảm mọi update đều HOT.

### 12.4. Chia dữ liệu theo khóa ghi

Một job chia input theo thời gian nhưng mọi partition đều ghi vào cùng row tổng hợp `daily_total` sẽ có hot-row contention. Phương án khác: ghi immutable ledger events (mỗi event có unique ID), sau đó aggregate theo account/tenant trong bước riêng với một owner cho mỗi write key.

### 12.5. Tránh flush từng item ở JPA

Nếu đang dùng JPA, kiểm tra code có gọi `entityManager.flush()` trong mỗi vòng lặp hoặc `saveAndFlush(...)` cho từng entity không. Gộp theo batch/chunk có giới hạn, dùng `JpaItemWriter`/provider đúng lifecycle, và đánh giá `clear`/memory theo version để tránh persistence context phình to.

### 12.6. Không “tối ưu” bằng tắt durability

Đừng chuyển `fsync=off` hoặc thay `synchronous_commit` bừa bãi khi dữ liệu yêu cầu recoverable transaction. Việc mất một lần fsync không được phản ánh trong `writeCount`, nhưng sự cố power loss có thể làm mất dữ liệu đã báo thành công hoặc làm hỏng kỳ vọng vận hành.

## 13. Khi flush cost tăng vì lock thay vì disk

Một worker có thể dành 95% thời gian trong `executeBatch()`, nhưng nguyên nhân là **chờ khóa**, không phải thời gian viết WAL:

~~~text
Worker 1: UPDATE account_id=42 giữ row lock
Worker 2: UPDATE account_id=42 -> chờ
Worker 3: UPDATE account_id=42 -> chờ
...
JDBC executeBatch() chưa trả về
Hikari active connections tăng
DB CPU có thể vẫn thấp
~~~

Đo `pg_stat_activity.wait_event_type` và `pg_blocking_pids(pid)` để xác định blockers:

~~~sql
SELECT a.pid,
       a.application_name,
       a.wait_event_type,
       a.wait_event,
       pg_blocking_pids(a.pid) AS blockers,
       now() - a.xact_start AS transaction_age
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY transaction_age DESC NULLS LAST;
~~~

`transaction_age` là tuổi transaction, **không bằng thời gian chờ khóa chính xác**. Cần kết hợp logs, query traces và blockers để xác định root cause.

Nếu gặp `40P01` (deadlock) hoặc `40001` (serialization failure), thường phải rollback rồi retry **toàn transaction**, theo retry policy có giới hạn và backoff. Đừng retry cùng SQL trong một PostgreSQL transaction đã bị đánh dấu aborted. Writer phải idempotent để không tạo side effects trùng khi chunk được phát lại.

## 14. Flush, commit và restart: xử lý crash ở từng mốc

Một nguyên nhân khiến dashboard báo write throughput cao nhưng business output sai là **đếm result quá sớm** hoặc không thiết kế idempotency cho việc chạy lại.

### 14.1. Các mốc có thể xảy ra crash

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant D as Business database
    participant J as JobRepository
    participant Q as Manager/Broker
    W->>D: JDBC executeBatch cho Chunk
    D-->>W: Batch SQL execution returned
    Note over W,D: Commit có thể chưa xảy ra
    W->>D: COMMIT
    D-->>W: Commit acknowledged
    Note over W,J: Sự cố trước khi metadata phản ánh đầy đủ
    W--xJ: StepExecution/ExecutionContext chưa thấy checkpoint
    Q->>W: Restart hoặc duplicate delivery
    W->>D: Thử ghi lại cùng item
    D-->>W: Unique key / idempotency check
~~~

Sơ đồ **minh họa trường hợp business DB và metadata không nằm trong một transaction nguyên tử**. Nếu hai resource sử dụng đúng một local transaction, kết quả nguyên tử có thể khác. Nhưng không được giả định mọi Spring Batch deployment có cùng DB/transaction manager, đặc biệt với remote partitioning, remote chunking, broker và API ngoài.

| Thời điểm lỗi | Điều có thể đã xảy ra | Hành động an toàn |
|---|---|---|
| Trước `executeBatch` | Chưa gửi dữ liệu ghi của chunk | Framework retry/restart theo trạng thái thực |
| Trong `executeBatch` | Một số statement có thể đã thực thi trong transaction nhưng chưa commit | Rollback transaction, không suy “đã insert N row” từ update counts |
| Sau `executeBatch`, trước commit | SQL thực thi nhưng transaction có thể rollback | Không công bố committed rate từ writer return |
| Khi commit, kết nối đứt | Client **có thể không biết** DB đã commit hay chưa | Tra unique business keys/ledger và restart idempotent |
| Sau business commit, trước metadata/checkpoint | Output đã tồn tại nhưng `StepExecution` có thể chưa theo kịp | Không ghi lại side effect; dùng idempotency/reconciliation |
| Sau metadata commit, trước ACK broker | Broker có thể redeliver | Correlate execution ID, tránh hai worker cùng xử lý và side effect trùng |
| Sau file flush, trước file publish | Có file partial/tạm nhưng downstream chưa nên thấy | Output key/version, rename/publish sau validate, cleanup rõ |

**Không dùng `Thread.sleep` hoặc ngắt kết nối production để tạo lỗi thử.** Fault injection nên diễn ra trong staging có dữ liệu giả và khả năng restore.

### 14.2. Idempotent writer cho duplicate delivery

Với bảng `applied_payments` có unique key:

~~~sql
INSERT INTO applied_payments
    (snapshot_key, payment_id, account_id, amount_cents)
VALUES
    (:snapshotKey, :paymentId, :accountId, :amountCents)
ON CONFLICT (snapshot_key, payment_id) DO NOTHING;
~~~

Cùng một payment ID từ **cùng immutable snapshot** chỉ tạo thêm row tối đa một lần. Nhưng nếu event trùng ID mà `amount_cents` thay đổi, `DO NOTHING` sẽ che bất đồng; cần checksum/version/audit hoặc fail theo nghiệp vụ.

Đối với các update có tính cộng dồn (`balance += delta`), chỉ thêm `ON CONFLICT` vào một bảng tổng hợp **không đảm bảo exactly-once**. Cần một **event ledger** chứa `event_id` duy nhất và cùng transaction guard việc áp dụng delta; hoặc dùng immutable event rồi aggregate theo snapshot.

### 14.3. Restart cùng JobInstance

Spring Batch nhận diện `JobInstance` từ job name và identifying `JobParameters`. Khi restart một job lỗi:

- Dùng **cùng identifying parameters**, không tự sinh `run.id` mới nếu mục tiêu là resume cùng input.
- Giữ partition plan, ranh giới và tên `StepExecution`/`ItemStream` ổn định.
- Reader có checkpoint phù hợp; sort key/snapshot bất biến để không đọc trùng/thiếu.
- Writer idempotent với chunk có thể đã tạo tác động nghiệp vụ trước khi metadata theo kịp.
- Nếu worker remote cũ còn sống, không dispatch cùng execution sang worker mới một cách mù quáng.
- Đối soát business keys/bytes sau restart, không chỉ tổng `writeCount`.

**`JobRepository` là metadata điều phối, không phải một distributed transaction coordinator cho mọi DB, file, broker và API downstream.**

## 15. Benchmark write rate và flush cost có kiểm soát

Benchmark có giá trị khi giữ **cùng input snapshot, cùng target schema/index/unique constraint, driver, SQL, transaction policy, database capacity và JDK/JVM**. Nếu mỗi lượt làm dữ liệu bảng target lớn lên, mức bloat/cache/hot key và số duplicate thay đổi, so sánh write rate có thể không công bằng.

### 15.1. Chuẩn bị phép thử

Giả sử dùng một snapshot có 2.000.000 payment records và input bất biến:

1. **Chuẩn bị baseline:** tạo schema, indexes, nguồn và target state nhất quán trước mỗi lượt; định nghĩa rõ `INSERT mới hoàn toàn` hay `UPSERT với duplicate`.
2. **Warm-up có kiểm soát:** JVM, driver connection pool và DB cache có thể cần ổn định; báo cả cold/warm nếu sản xuất có pattern tương tự.
3. **Chạy một baseline tuần tự:** đo writer-call p95, chunk commit latency, job wall time, WAL bytes và output correctness.
4. **Đổi một biến:** tăng chunk hoặc driver batch size, giữ concurrency cố định.
5. **Sau đó scale worker:** 1 → 2 → 4 → 8, giữ batch/chunk size ổn định.
6. **Lặp phép đo:** ghi median/range giữa các lần chạy, không chỉ một con số tốt nhất.
7. **Fault-injection riêng:** kiểm tra crash/restart/idempotency, không gộp kết quả lỗi vào bảng benchmark happy path mà không ghi chú.

### 15.2. Ma trận thử nghiệm

| Test | Chunk size | Worker active | Điều cần đo |
|---|---:|---:|---|
| A | 50 | 1 | Baseline: commit overhead và write rate |
| B | 200 | 1 | Số commit giảm có cải thiện rate không? |
| C | 500 | 1 | Writer-call latency và WAL sync/bytes |
| D | 1000 | 1 | Transaction p95, memory, lock wait |
| E | 500 | 2 | Scale từ một sang hai execution |
| F | 500 | 4 | DB CPU/IO, pool pending và skew |
| G | 500 | 8 | Điểm bão hòa, retry, WAL pressure |

Đây chỉ là **test plan**, không có số liệu hiệu năng đo sẵn. Đừng biến các số chunk/worker trong bảng thành “best practice” chung; kết quả thật phải đến từ workload của hệ thống.

### 15.3. Mẫu bảng kết quả cần điền

| Trường ghi trong báo cáo | Ý nghĩa |
|---|---|
| Job instance, image/driver/database version | Khả năng tái lập |
| Snapshot key và số unique expected IDs | Mẫu số kiểm tra correctness |
| Chunk size / JDBC/JPA batch size / active workers | Cấu hình đã thử |
| Wall-clock và committed unique rows/s | Write rate thực |
| Writer-call p50/p95/p99 | Độ trễ ở writer |
| Chunk/transaction duration p50/p95/p99 | Kiểm tra commit/boundary overhead |
| WAL bytes delta, wal_sync delta/time | Dấu hiệu áp lực ghi/flush |
| DB IO/CPU/lock wait, Hikari pending | Nút thắt tài nguyên |
| JVM memory/GC và retries/rollbacks | Chi phí ngoài DB |
| Target unique IDs, checksum/aggregate | Kết quả nghiệp vụ sau commit |

### 15.4. Kết luận theo dạng “điểm gãy”

Một biểu đồ speedup có thể tăng tốt từ 1 lên 4 worker, rồi gần như phẳng từ 4 lên 8; ở cùng thời điểm `wal_sync_time` hoặc lock wait tăng và Hikari pending xuất hiện. Từ đó có thể kết luận **điểm gãy tài nguyên** đã xuất hiện; muốn tăng rate phải giảm write amplification/lock/transaction cost hoặc thay kiến trúc, chứ không chỉ thêm worker.

Nếu `writer_call_duration` giảm nhưng `chunk_duration` tăng, có khả năng batching cải thiện execute-call trong khi commit/lock/metadata overhead trở nên nổi trội. Không báo “flush đã nhanh hơn” nếu chỉ một timer được cải thiện.

## 16. Runbook khi write rate giảm hoặc flush cost tăng

### Bước 1 — Chốt định nghĩa số liệu

Xác nhận dashboard đang thể hiện **attempted item rate**, `writeCount`, affected-row rate, unique row committed rate hay WAL bytes/s. Kiểm tra thời gian đo tính từ lúc manager launch hay chỉ lúc worker active; phân biệt queue lag với DB write bottleneck.

### Bước 2 — Xác định vị trí latency

So sánh `ItemWriter.write` timer, chunk duration, transaction duration, end-to-end job wall time và PostgreSQL wait events. Nếu writer nhanh nhưng chunk chậm, xem commit/metadata/reader/processor. Nếu writer chậm, xem SQL, DB lock và JDBC driver behavior.

### Bước 3 — Quan sát DB và pool tại thời điểm chậm

- Lấy delta `pg_stat_wal`, `pg_stat_database`; không đọc counters tích lũy như rate.
- Xem `pg_stat_activity`, `wait_event_type`, lock blockers và long transactions.
- So sánh Hikari active/idle/pending/acquire p95 ở từng business/metadata pool.
- Xem CPU, I/O, WAL device, checkpoint pressure, storage latency và JVM GC.
- Phân biệt **một worker pod** bất thường với **DB instance chung** đang quá tải.

### Bước 4 — Kiểm tra thay đổi gần nhất

Có vừa tăng `chunk size`, bật JPA flush từng item, tăng `replicas`, thêm unique index/trigger, thay SQL upsert, nâng driver, đổi transaction isolation hoặc chuyển output filesystem không? Ghi image digest và configuration để rollback/tái hiện nếu cần.

### Bước 5 — Khắc phục theo bottleneck

| Chẩn đoán | Ưu tiên |
|---|---|
| Writer-call nhiều round-trip, DB còn dư CPU/IO | JDBC batching, pgjdbc rewrite nếu phù hợp, set-based SQL |
| Commit/WAL overhead chiếm phần lớn, lock thấp | Thử tăng chunk hợp lý, giảm commit count; đo durability/latency |
| WAL bytes quá lớn | Tối ưu update không đổi, index dư, batch pattern, full-page image context |
| JPA dirty checking/heap/GC cao | Cấu hình Hibernate batching, quản lý flush/clear, giảm persistence context |
| Hikari pending vì cursor/transaction dài | Rút ngắn hold time, giới hạn concurrency, xem reader strategy |
| Hot-row/unique lock | Partition theo write key, immutable staging, aggregate riêng |
| Queue lag tăng nhưng DB rảnh | Kiểm tra worker count, consumer/manager throughput, broker/backpressure |
| File fsync/storage chậm | Đo filesystem, flush cadence/durability yêu cầu, output partitioning |
| Rất nhiều retry/rollback | Sửa nguyên nhân gốc; giới hạn retry/backoff, idempotency |

### Bước 6 — Không phá durability để “sửa” throughput

Không tắt `fsync`, giảm `synchronous_commit` hoặc loại bỏ unique constraint/idempotency key trong lúc incident nếu business data yêu cầu tính bền vững. Một thay đổi làm write rate tăng nhưng khiến recovery không còn đúng là **thất bại kỹ thuật**, không phải tối ưu thành công.

### Bước 7 — Restart và đối soát

Nếu job có partition/chunk `FAILED`, xác minh các worker cũ đã dừng; dùng Spring Batch lifecycle để restart đúng `JobInstance`, giữ input snapshot và writer idempotent. Đối chiếu unique target IDs/tổng tiền/checksum trước khi cho downstream xử lý.

### Bước 8 — Cập nhật baseline và capacity plan

Ghi lại threshold p95 writer/commit, WAL sync/bytes, active/pending connections, retry và throughput ở số worker an toàn. Đưa ngân sách connection vào HPA/rolling update; mỗi pod thêm có thể tạo pool mới, tăng tải metadata và số transaction tranh khóa.

## 17. Ma trận kiểm thử tính đúng và hiệu năng

| Test | Điều kiện tạo | Tiêu chí đạt |
|---|---|---|
| Chạy tuần tự | Một worker, snapshot bất biến | Unique output IDs/amount khớp input |
| Chunk cuối không đầy | 1.203 item với `chunk(500)` | 500 + 500 + 203 item được xử lý theo lifecycle |
| Filter và duplicate | Có filter và `ON CONFLICT DO NOTHING` | Phân biệt writer items với row mới thực |
| JDBC driver rewrite | So sánh rewrite bật/tắt trên đúng SQL shape | Báo measured effect, không giả định một statement |
| JPA flush mỗi item | So sánh với flush theo batch/chunk | Đo SQL calls, latency, memory và output đúng |
| JPA transaction rollback | Flush thành công rồi ném exception | Không đếm row chưa commit thành business success |
| Cursor connection hold | Nhiều reader partition dài | Pool budget đủ, resource được đóng |
| WAL sync pressure | Tăng worker ở cùng schema | Tìm điểm bão hòa và latency rõ ràng |
| Hot row updates | 80% event chạm vài business keys | Nhận diện lock wait, không tăng worker mù quáng |
| Failed JDBC batch | Một item sai constraint | Transaction/fault policy đúng, item lỗi được xác định theo contract |
| Crash trước COMMIT | Kill worker giữa chunk trên staging | Rollback/restart đúng, không missing data |
| Crash sau business COMMIT | Mất ACK/checkpoint trong topology tách resource | Idempotency/reconciliation tránh side effect trùng |
| File writer partial | Crash trước khi đóng/publish output | Downstream không đọc file tạm như bản final |
| File forceSync | Bật/tắt theo test yêu cầu durability | Đo latency I/O và giải thích semantics |
| DB metadata tách riêng | Ghi business và checkpoint ở hai DB | Không giả định atomicity, test recovery |
| HPA/rolling deployment | Tăng worker pod đồng thời | Không vượt budget connections/IO |
| Benchmark hoàn chỉnh | 1/2/4/8 worker và nhiều chunk sizes | Rate, latency, WAL, locks và correctness cùng được báo |

### Một bộ invariant tối thiểu

~~~text
expectedKeys = tất cả business keys hợp lệ trong immutable snapshot
actualKeys   = tất cả unique keys đã commit ở output snapshot

assert actualKeys == expectedKeys
assert payload/amount checksum phù hợp contract
assert không có side effect ngoài ý muốn sau replay/restart
~~~

Đây là **pseudocode**, không phải một API mặc định của Spring Batch. Nếu một phần input được filter hợp lệ, `expectedKeys` phải phản ánh chính sách filter đã được duyệt. Không chỉ so sánh tổng `writeCount`: một item bị ghi đôi và một item khác bị thiếu có thể tạo tổng số lượng trùng nhau.

## 18. Checklist trước khi đưa write throughput tuning lên production

- [ ] Đã định nghĩa rõ write rate là attempted, writer-accepted, affected rows hay committed unique business rows.
- [ ] Dashboard không dùng `ItemWriter.write()` return làm bằng chứng transaction durable.
- [ ] Phân biệt JDBC `executeBatch`, JPA `flush`, file `flush/fsync` và PostgreSQL WAL sync/checkpoint.
- [ ] Đã đo writer-call latency, chunk/commit latency, DB wait events và job wall-clock cùng lúc.
- [ ] Có immutable input snapshot, identifying JobParameters và partition plan ổn định để restart.
- [ ] Unique business key/idempotency và duplicate-with-different-payload policy rõ ràng.
- [ ] `JdbcBatchItemWriter.assertUpdates` phù hợp với `INSERT/UPDATE/UPSERT` và 0-row semantics.
- [ ] Không lẫn số item trong chunk, JDBC batch size và số SQL statements/transactions.
- [ ] Hibernate JDBC batching được kiểm chứng thực tế nếu dùng JPA; không flush từng entity vô tội vạ.
- [ ] Với file output, có ownership theo partition, file temp/publish và durability policy rõ.
- [ ] Đã xét WAL/commit latency, lock, index, I/O, CPU, memory, checkpoint và storage capacity.
- [ ] Không tắt `fsync`/durability hoặc unique constraints chỉ để tăng tốc.
- [ ] Reader/processor/writer có thread safety phù hợp với mô hình multi-thread/partition.
- [ ] Connection pool budget tính theo số pod tối đa, metadata/business DB và rolling surge.
- [ ] Thử thay từng biến chunk/batch/concurrency, cùng snapshot và DB target state.
- [ ] Retry có giới hạn và backoff; worker cũ không xử lý trùng khi remote request redeliver.
- [ ] Đã kiểm thử crash trước/sau commit và đối soát tập business keys sau restart.
- [ ] Có runbook cho WAL pressure, lock contention, pool pending, queue lag và slowest partition.

## 19. Bài tập thực hành

### Bài tập 1 — Tính đúng write rate

Một job đưa 50.000 item vào writer, trong đó 1.500 item bị `ON CONFLICT DO NOTHING` vì đã tồn tại. Job chạy 10 giây. Hãy tính **writer item rate** và **unique new row rate**; nêu vì sao hai kết quả khác nhau và cách kiểm chứng trong bảng `applied_payments`.

### Bài tập 2 — Phân loại các loại flush

Xếp các thao tác `EntityManager.flush()`, `PreparedStatement.executeBatch()`, `FileChannel.force(true)`, PostgreSQL `COMMIT`, PostgreSQL checkpoint và `ItemStream.update()` vào tầng tương ứng. Với mỗi thao tác, trả lời: “Có đủ để tuyên bố business result đã durable và job có thể restart chính xác không?”

### Bài tập 3 — Viết metered JDBC writer

Dùng `PaymentRow` và `JdbcBatchItemWriter` của phần 4; bọc bằng `ItemWriter` decorator ghi timer như phần 8. Cố tình ném exception từ JDBC writer khi một row sai constraint. Kiểm tra attempted counter có đếm item lỗi và tại sao timer không được gọi là committed write latency.

### Bài tập 4 — Đo WAL delta trên staging

Chụp `pg_stat_wal` trước/sau job 2 triệu row trên PostgreSQL staging; tính delta `wal_bytes`, `wal_sync` và `wal_sync_time`. Ghi chú có workload nào khác dùng chung instance không, timing collection có được bật không và vì sao các số này không tương đương số disk bytes của riêng job.

### Bài tập 5 — JDBC so với JPA flush

Thiết kế hai worker ghi cùng tập bản ghi: một dùng `JdbcBatchItemWriter`, một dùng JPA/Hibernate. Thử Hibernate batch size 1, 20, 50 với chunk size không đổi; đo SQL calls, writer-call p95, commit p95, heap/GC và output correctness. Xác minh có `IDENTITY`/cascade nào làm batching khác dự kiến không.

### Bài tập 6 — Chọn chunk và concurrency

Chạy `chunk(50)`, `chunk(200)`, `chunk(500)` và `chunk(1000)` với worker 1, 2, 4, 8 trên immutable snapshot. Báo bảng wall-clock, committed unique rows/s, WAL bytes, lock wait, Hikari pending và rollback. Chọn cấu hình **dựa trên điểm gãy throughput/latency và tính đúng**, không theo giá trị lớn nhất.

### Bài tập 7 — Crash giữa các biên giới durability

Cho business DB commit một chunk rồi mô phỏng worker crash trước khi metadata/ACK được cập nhật trong một topology tách resource. Restart cùng `JobInstance`. Dùng unique key/idempotency để không tạo bản ghi trùng; chứng minh `writeCount` hoặc counter trong JVM không phải nguồn sự thật cho output cuối.

### Bài tập 8 — File flush và publish

Viết báo cáo CSV theo các partition riêng, thử `forceSync` theo khả năng filesystem; cho worker bị dừng giữa file. Thiết kế cách xuất tệp tạm, xác minh row count/checksum rồi publish một tên final/versioned output để downstream không đọc file partial.

### Bài tập 9 — Điều tra WAL hay lock?

Một job tăng 4 lên 16 worker, `writer_call_p95` tăng gấp ba. Ở môi trường A, `pg_stat_activity` chủ yếu chờ WAL-related I/O; ở môi trường B, phần lớn đang chờ row lock cùng account ID. Nêu hai kế hoạch tuning **khác nhau** và vì sao tăng pool size hoặc tắt fsync không phải câu trả lời chung.

**Câu hỏi tự kiểm tra:** `writeCount` có phải số row mới commit không? `EntityManager.flush()` khác `COMMIT` thế nào? Vì sao dirty data pages có thể flush sau commit? Tại sao `pg_stat_wal.wal_bytes` không phải số byte do riêng một worker tạo ra? Khi nào tăng chunk giúp giảm commit overhead nhưng tăng lock cost? Vì sao một lời gọi `write()` nhanh chưa đủ chứng minh job throughput cao? Cần làm gì khi commit trả lỗi kết nối nhưng không biết transaction đã commit chưa?

## 20. Tổng kết

**Write rate** nên được hiểu là tốc độ tạo ra **kết quả nghiệp vụ hợp lệ đã commit** qua một khoảng thời gian xác định, không chỉ là số item đưa vào `ItemWriter` hoặc số lần gọi JDBC. **Flush cost** phải được phân biệt ở từng tầng: JDBC batch execution, JPA persistence-context flush, file buffer/fsync, PostgreSQL WAL sync và data-page checkpoint. Những tầng này có thể chồng lấn về thời gian nhưng **khác nhau về tính bền vững và ngữ nghĩa transaction**.

Để nâng throughput một cách an toàn, cần **đo writer-call và commit/DB latency riêng biệt**, tối ưu chunk/JDBC/JPA batching, giới hạn worker theo CPU/IO/WAL/lock/pool, dùng backpressure khi writer chậm hơn upstream và duy trì input snapshot cùng writer idempotent để restart chính xác. Một thay đổi chỉ thực sự tốt khi **committed business rate tăng, tài nguyên còn trong ngân sách và dữ liệu vẫn đúng sau retry/crash**.
