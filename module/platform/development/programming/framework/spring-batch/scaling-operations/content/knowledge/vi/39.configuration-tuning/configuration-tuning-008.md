# Điều chỉnh batch insert size trong Spring Batch

## 1. Vì sao tăng batch insert size từ 100 lên 5.000 có thể làm job chậm hơn?

Một pipeline nhập 20 triệu giao dịch vào PostgreSQL có bốn worker, mỗi worker đọc dữ liệu, chuẩn hóa rồi ghi bằng `JdbcBatchItemWriter`. Khi `chunkSize=100`, hệ thống hoàn thành trong 28 phút. Nhóm vận hành tăng `chunkSize=5_000` vì nghĩ “càng ít round trip càng nhanh”. Kết quả: lượng memory sử dụng tăng, mỗi transaction giữ connection lâu hơn, thời gian khóa bảng/row kéo dài, một chunk lỗi phải thực hiện lại nhiều item và thời gian job tăng lên 35 phút.

Ngược lại, nếu giữ `chunkSize=1`, mỗi item phải chịu nhiều overhead liên quan transaction/commit, DB network và cơ chế framework; hệ thống cũng có thể chậm.

**Vấn đề không nằm ở việc chọn một con số lớn nhất.** Cần tìm **batch insert size hợp lý theo workload, database, driver, transaction, độ đồng thời và SLA**, đồng thời bảo đảm output chính xác khi job retry/restart.

Bài **“Điều chỉnh batch insert size”** thuộc chương **Tối ưu cấu hình** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; học đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Sau khi học, bạn có thể:

1. Phân biệt **Spring Batch chunk size**, **JDBC batch size**, **Hibernate JDBC batch size**, kích thước một câu `INSERT` nhiều dòng và kích thước request/message.
2. Hiểu `JdbcBatchItemWriter`, `PreparedStatement.addBatch()`/`executeBatch()` và cách transaction commit ảnh hưởng throughput.
3. Cấu hình writer và worker step trong Spring Batch 5.2.x với PostgreSQL, không nhầm `executeBatch` với commit.
4. Chọn điểm khởi đầu, đo throughput, latency, allocation, WAL, locks, pool pressure và xác định điểm bão hòa.
5. Thử các giá trị `chunkSize`/JDBC batch size riêng biệt thay vì thay nhiều biến cùng lúc.
6. Điều chỉnh theo row width, index, `ON CONFLICT`, primary key generation, JPA/Hibernate, native SQL và driver rewrite.
7. Tính ngân sách khi nhiều worker/partition chạy song song và kiểm tra tác động của retry/rollback.
8. Viết test hiệu năng **có đối soát dữ liệu**, kiểm tra idempotency, checkpoint và restart trước production.

**Giả định ví dụ:** Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, Spring JDBC, PostgreSQL, JUnit 5, Testcontainers. Với Spring Batch 6.x/Spring Boot 4.x, Spring Data JPA, database hoặc JDBC driver khác, cần đối chiếu API và cấu hình ở dự án. Các con số batch size dưới đây là **mốc thử nghiệm**, không phải chuẩn áp dụng cho mọi hệ thống.

## 2. “Batch insert size” có ít nhất năm nghĩa

Trong một cuộc thảo luận tuning, câu “đặt batch size = 500” chưa đủ để xác định hệ thống đã thay đổi gì.

| Khái niệm | Tầng cấu hình | Ý nghĩa | Thường tác động đến |
|---|---|---|---|
| **Chunk size** | Spring Batch `StepBuilder.chunk(n, txManager)` | Đọc/xử lý rồi ghi tối đa `n` items trong một chunk transaction (trừ trường hợp filter/skip/EOF và các behavior đặc biệt) | Commit frequency, checkpoint, memory, rollback/replay |
| **JDBC statement batch size** | `PreparedStatement.addBatch()` / `executeBatch()` hoặc writer wrapper | Số parameter sets được gửi trong một JDBC batch call | JDBC/driver overhead, DB round trips |
| **Hibernate JDBC batch size** | `hibernate.jdbc.batch_size` | Số statement DML tương thích được gom vào JDBC batch theo Hibernate | ORM SQL grouping, flush, memory/ID strategy |
| **Multi-row INSERT size** | SQL `INSERT INTO ... VALUES (...), (...)` | Số rows trong **một** câu SQL | SQL parse/bind count, driver/server limits |
| **Remote message/broker batch size** | Spring Integration/JMS/Kafka/transport | Số item/chunk/request được đóng gói hoặc chuyển trong một message/batch ở mô hình tương ứng | Broker payload, in-flight, retry và backpressure |

**Đừng đồng nhất các tầng:** `chunk(500)` không tự đặt `hibernate.jdbc.batch_size=500`. Với `JdbcBatchItemWriter` chuẩn, writer nhận một `Chunk` và tạo JDBC batch từ các items nhận được; ở tình huống chunk-oriented thông thường, JDBC batch call thường chứa khoảng **số output items của chunk**, không phải một cấu hình độc lập bên trong writer. Nếu cần giới hạn `executeBatch` ở 100 nhưng chunk 500, phải implement/customize writer hoặc chọn một cơ chế batching có hỗ trợ tách call; transaction của chunk có thể vẫn chứa đủ 500 items.

### 2.1. Một chunk không nhất thiết ghi đúng n rows

Ví dụ `chunk(500)`:

~~~text
Reader:                    500 input items
ItemProcessor:             30 items được filter (trả null)
ItemWriter nhận:           470 items
ON CONFLICT DO NOTHING:    20 business keys đã có
PostgreSQL new rows:       450
Spring Batch writeCount:  phản ánh writer items theo lifecycle (không
                           phải new rows count từ database)
~~~

Vì vậy, việc đo “500 rows per batch” chỉ đúng khi không filter, writer nhận đủ item, dữ liệu không duplicate và database thật sự insert thành công tất cả.

### 2.2. Đơn vị commit và đơn vị network không phải một

~~~mermaid
flowchart LR
    R["ItemReader"] --> P["ItemProcessor"]
    P --> C["Spring Batch chunk (n items)"]
    C --> W["ItemWriter"]
    W --> J["JDBC addBatch / executeBatch"]
    J --> D[(PostgreSQL)]
    C --> T["Transaction COMMIT or ROLLBACK"]
    T -.-> D
~~~

`executeBatch()` có thể gửi nhiều statements đến DB **trước khi transaction commit**. Một exception trong writer, transaction callback hoặc DB commit có thể khiến tất cả writes của chunk transaction rollback. **JDBC batch thành công không đồng nghĩa dữ liệu đã commit.**

## 3. Vì sao batching giúp tăng throughput?

Nếu insert từng item, có chi phí cho mỗi lần tương tác: method call, parameter binding, network protocol, SQL execution và transaction management. Batching giảm phần overhead có thể gộp được nhưng **không làm chi phí ghi dữ liệu/duy trì index biến mất**.

Một mô hình thô:

\[
T(N,B)\approx
N t_{\mathrm{row}}+
\left\lceil \frac{N}{B}\right\rceil t_{\mathrm{batch}}+
\left\lceil \frac{N}{C}\right\rceil t_{\mathrm{commit}}+
T_{\mathrm{contention}}+
T_{\mathrm{framework}}
\]

Trong đó:

- `N` là số output items, `B` là số items mỗi JDBC batch call, `C` là số items mỗi chunk transaction.
- `t_row` là chi phí xử lý/ghi mỗi row tại DB, không giả định bằng nhau nếu row widths khác nhau.
- `t_batch` là chi phí cố định mỗi batch/round trip có thể giảm khi gom lệnh.
- `t_commit` là overhead transaction/commit.
- `T_contention` gồm lock, WAL/I/O, index contention, pool waits; **có thể tăng khi batch/chunk lớn và nhiều workers**.
- Đây là **mô hình lý giải**, không phải công thức dự đoán chính xác PostgreSQL performance.

Nếu `B` tăng quá lớn:

- Driver giữ nhiều bind values trong memory; network packet và statement size lớn.
- DB phải xử lý statement/batch lớn hơn, tạo thêm CPU, memory và WAL pressure.
- Transaction giữ connection/locks lâu hơn nếu đồng thời tăng `C`.
- Khi failure, nhiều item bị rollback/retry trong cùng chunk.
- Một insert batch có vài row rất rộng có thể tốn nhiều MB dù `B` nhỏ.
- Batching lớn có thể không giúp khi bottleneck là index updates, row locks hoặc downstream constraints.

### 3.1. Chunk size nhỏ và lớn: trade-off

| Kích thước | Mặt lợi | Mặt hại/rủi ro |
|---|---|---|
| Rất nhỏ (1–10) | Memory nhỏ, lỗi làm lại ít items, commit đều | Nhiều commit/checkpoint/round trips, overhead cao |
| Trung bình (50–500) | Thường là mốc thử hợp lý cho nhiều workload | Vẫn phụ thuộc row width, driver, DB, concurrency |
| Lớn (1.000+) | Giảm số chunk commits nếu DB còn headroom | Transaction/rollback lớn, giữ connection lâu, batch payload lớn |
| Rất lớn (10.000+) | Có thể hữu ích cho một số bulk load được thiết kế riêng | Dễ gặp resource/parameter/payload limits, lock/WAL/GC, tail latency |

**Không áp bảng như quy tắc:** PostgreSQL ghi dữ liệu hẹp với `COPY` khác hoàn toàn PostgreSQL ghi JSONB 2 MiB/row, có trigger nặng hoặc nhiều unique indexes. Một hệ thống có thể tối ưu ở 100, hệ khác ở 2.000 hoặc cần bulk loading `COPY` thay JDBC batch.

### 3.2. Ví dụ tính số transaction và JDBC batches

Với 100.003 output items, không filter/skip:

| Chunk size C | Số chunks lý thuyết \(\lceil100003/C\rceil\) | Nếu writer tạo một JDBC batch/chunk, số batch calls |
|---:|---:|---:|
| 1 | 100.003 | 100.003 |
| 50 | 2.001 | 2.001 |
| 100 | 1.001 | 1.001 |
| 250 | 401 | 401 |
| 500 | 201 | 201 |
| 1.000 | 101 | 101 |
| 5.000 | 21 | 21 |

Đây là **đếm lý thuyết trên giả định mỗi chunk commit một lần**, không phải số transactions/JDBC round trips thực khi có retry, skip, processor filter, driver rewrite, pool/metadata operations hoặc multi-step flow. Số `StepExecution.commitCount` của Spring Batch cũng có ngữ nghĩa lifecycle riêng; không mặc định chính xác bằng số dòng bảng trên.

## 4. Ví dụ nghiệp vụ: nhập các payment events theo snapshot

Để benchmark và test restart, dữ liệu nguồn cần **bất biến trong suốt JobInstance**. Dùng business key bền vững thay vì ID của lần thử xử lý.

### 4.1. Schema PostgreSQL

~~~sql
CREATE TABLE source_payments (
    snapshot_key  VARCHAR(80) NOT NULL,
    payment_id    BIGINT NOT NULL,
    account_id    BIGINT NOT NULL,
    amount_cents  BIGINT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (snapshot_key, payment_id)
);

CREATE TABLE posted_payments (
    snapshot_key  VARCHAR(80) NOT NULL,
    payment_id    BIGINT NOT NULL,
    account_id    BIGINT NOT NULL,
    amount_cents  BIGINT NOT NULL,
    posted_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_key, payment_id)
);
~~~

Primary key `(snapshot_key, payment_id)` trong PostgreSQL đã tạo một index tương ứng, thường đủ phục vụ range reader lọc `snapshot_key` rồi tìm khoảng `payment_id`. **Không tạo thêm index trùng key nếu chưa có bằng chứng từ `EXPLAIN`/workload**: mỗi index dư tăng chi phí insert, bộ nhớ và WAL.

### 4.2. Fixture có thể tái lập

~~~sql
INSERT INTO source_payments
    (snapshot_key, payment_id, account_id, amount_cents, created_at)
SELECT
    'insert-bench-001',
    n,
    MOD(n, 101),
    n * 10,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
FROM generate_series(1, 100003) AS g(n);
~~~

Expected **100.003 unique business keys** và tổng tiền:

\[
\sum_{n=1}^{100003} 10n
=10\cdot \frac{100003\cdot 100004}{2}
=50\,003\,500\,060\ \text{cents}.
\]

Ghi rõ `snapshotKey`, input count, amount sum và primary key. Với pipeline có transform/filter, expected output phải là **tập đã xử lý theo business logic**, không so máy móc với raw source.

### 4.3. DTO phù hợp Java 17

~~~java
public record Payment(
        String snapshotKey,
        long paymentId,
        long accountId,
        long amountCents) {}
~~~

Đặt record trong `Payment.java`, package phù hợp với application. Các ví dụ tiếp theo giả định đã khai báo bean `businessDataSource` và `businessTransactionManager` chỉ đến PostgreSQL business database; bean metadata/JobRepository có thể cùng datasource hoặc tách riêng, nhưng phải chọn đúng transaction manager trong worker chunk.

## 5. Cấu hình JdbcBatchItemWriter đúng ranh giới

### 5.1. Writer dùng named parameters

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class PaymentWriterConfiguration {

    @Bean
    public JdbcBatchItemWriter<Payment> paymentWriter(
            @Qualifier("businessDataSource") DataSource businessDataSource) {

        return new JdbcBatchItemWriterBuilder<Payment>()
                .dataSource(businessDataSource)
                .sql("""
                    INSERT INTO posted_payments
                        (snapshot_key, payment_id, account_id, amount_cents)
                    VALUES
                        (:snapshotKey, :paymentId, :accountId, :amountCents)
                    ON CONFLICT (snapshot_key, payment_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(payment ->
                        new MapSqlParameterSource()
                            .addValue("snapshotKey", payment.snapshotKey())
                            .addValue("paymentId", payment.paymentId())
                            .addValue("accountId", payment.accountId())
                            .addValue("amountCents", payment.amountCents()))
                // Replay hợp lệ có thể ảnh hưởng 0 rows.
                .assertUpdates(false)
                .build();
    }
}
~~~

`JdbcBatchItemWriter` là một writer **batch JDBC**, không phải vòng lặp `jdbcTemplate.update(...)` mỗi item do người viết tự tạo. Khi `write(Chunk<? extends Payment>)` được gọi, writer sử dụng JDBC batching cho tập parameter values tương ứng; SQL và driver quyết định cách gửi/execute trên wire.

**Vì sao `assertUpdates(false)`?** Với `ON CONFLICT DO NOTHING`, row đã tồn tại ảnh hưởng 0 row, đây có thể là replay hợp lệ sau restart/redelivery. Nếu business contract là **tất cả IDs đều mới và mọi INSERT phải ảnh hưởng một row**, bật `assertUpdates(true)` (mặc định theo builder/version) có thể phát hiện một số trường hợp 0 affected rows. Cần hiểu driver update-count semantics: một số driver trả `SUCCESS_NO_INFO` khi batching; không coi affected-row counts là checksum nghiệp vụ.

**Điểm quan trọng:** `ON CONFLICT DO NOTHING` cũng có thể che cùng key nhưng **payload/amount khác nhau**. Muốn phát hiện xung đột dữ liệu, phải có immutable snapshot, checksum/version validation, hoặc SQL/business logic tách duplicate cùng payload khỏi duplicate sai payload. Idempotency không đồng nghĩa im lặng bỏ mọi conflict.

### 5.2. Chunk writer theo transaction đã chọn

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PaymentStepConfiguration {

    @Bean
    public Step paymentWorkerStep(
            JobRepository jobRepository,
            @Qualifier("businessTransactionManager")
                PlatformTransactionManager businessTransactionManager,
            JdbcCursorItemReader<Payment> paymentReader,
            JdbcBatchItemWriter<Payment> paymentWriter) {

        return new StepBuilder("paymentWorkerStep", jobRepository)
                .<Payment, Payment>chunk(250, businessTransactionManager)
                .reader(paymentReader)
                .writer(paymentWriter)
                .build();
    }
}
~~~

Đây là **worker step** minh họa (reader ở phần 6); phải định nghĩa `Job` và topology manager/partition handler phù hợp riêng. `chunk(250)` là **tuning knob của chunk**, không phải `hibernate.jdbc.batch_size`. Với không filter/skip, writer thường nhận tối đa 250 Payment items mỗi lần và batch SQL cùng chunk transaction.

**Không tự thêm `@Transactional` lên `JdbcBatchItemWriter` để tạo transaction riêng.** Step chunk transaction đã xác định boundary; nếu writer mở `REQUIRES_NEW` hoặc kết nối auto-commit khác, rollback chunk có thể **không hoàn tác** business rows. Test cụ thể bằng lỗi sau SQL trước COMMIT trước khi benchmark.

## 6. Reader có checkpoint và input range cố định

Batch insert size không cứu được một job **đọc lặp/bỏ sót input**. Trong partitioning, mỗi worker phải nhận range riêng và thứ tự đọc ổn định để restart đúng.

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentReaderConfiguration {

    @Bean
    @StepScope
    public JdbcCursorItemReader<Payment> paymentReader(
            @Qualifier("businessDataSource") DataSource businessDataSource,
            @Value("#{jobParameters['snapshotKey']}") String snapshotKey,
            @Value("#{stepExecutionContext['fromInclusive']}") Long from,
            @Value("#{stepExecutionContext['toExclusive']}") Long to) {

        if (snapshotKey == null || snapshotKey.isBlank()
                || from == null || to == null || from >= to) {
            throw new IllegalArgumentException("Invalid snapshot/ID range");
        }

        return new JdbcCursorItemReaderBuilder<Payment>()
                .name("paymentRangeReader")
                .dataSource(businessDataSource)
                .sql("""
                    SELECT snapshot_key, payment_id,
                           account_id, amount_cents
                    FROM source_payments
                    WHERE snapshot_key = ?
                      AND payment_id >= ?
                      AND payment_id < ?
                    ORDER BY payment_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotKey);
                    ps.setLong(2, from);
                    ps.setLong(3, to);
                })
                .rowMapper((rs, n) -> new Payment(
                        rs.getString("snapshot_key"),
                        rs.getLong("payment_id"),
                        rs.getLong("account_id"),
                        rs.getLong("amount_cents")))
                .saveState(true)
                .build();
    }
}
~~~

**Điều kiện:** các `ExecutionContext` keys phải do `Partitioner` tạo ổn định và job đã được launch với identifying `snapshotKey`. Ở step không partition, có thể thay range bằng job parameters hoặc reader khác. Đoạn trên là một **worker reader**, không tự tạo manager, `Job` hay broker.

- `@StepScope` tạo reader theo **StepExecution** (qua scoped proxy), không tự đảm bảo thread safety nếu cùng StepExecution dùng nhiều chunk threads.
- `[from,to)` là interval nửa mở, tránh duplicate tại boundary giữa partitions.
- `ORDER BY payment_id` bảo đảm key order trong snapshot để checkpoint/restart có ngữ nghĩa; input phải **bất biến** trong suốt job.
- `JdbcCursorItemReader` có state/cursor riêng; thực tế có thể giữ một JDBC connection trong thời gian step đọc, cần tính vào Hikari pool budget.
- Khi tăng `chunkSize`, framework có thể giữ nhiều Payment objects hơn trước khi commit; quan sát memory, JDBC driver fetch behavior và GC.

### 6.1. Chunk size khác fetch size

`JdbcCursorItemReader` có thuộc tính `fetchSize`/driver fetch hint để điều chỉnh cách driver lấy result set. Nó **không** đồng nghĩa writer JDBC batch size hay chunk size. Với PostgreSQL cursor fetching, driver auto-commit/fetch settings có điều kiện áp dụng; không giả định chỉ cần `fetchSize(500)` là server sẽ luôn gửi từng 500 rows trong mọi mode.

| Knob | Hướng dữ liệu | Tuning mục tiêu |
|---|---|---|
| Reader `fetchSize` | DB → reader | Giảm round trips/read buffer phù hợp driver |
| Chunk `chunk(n)` | Reader/process → transaction boundary | Commit/restart/memory |
| Writer JDBC batch size | Writer → DB | Giảm statement/driver/network overhead |
| Broker prefetch | Broker → remote worker | Kiểm soát in-flight messages |

Đánh giá riêng từng knob bằng số liệu. Nếu đọc từ S3/file, reader fetch-buffer logic lại khác JDBC; không “mượn” `fetchSize` để đổi record writer batching.

## 7. Khi muốn JDBC batch size khác chunk size

Với chunk transaction 500 items, ứng dụng có thể muốn gửi tối đa 100 parameter sets mỗi `executeBatch`, nhưng **vẫn commit cả 500 items trong một transaction**.

Spring JDBC có một overload phù hợp:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class PaymentSplitBatchWriterConfiguration {

    @Bean("splitBatchPaymentWriter")
    public ItemWriter<Payment> splitBatchPaymentWriter(
            @Qualifier("businessJdbcTemplate") JdbcTemplate jdbc,
        @Value("${app.insert.jdbc-batch-size:100}") int jdbcBatchSize) {

        if (jdbcBatchSize <= 0) {
            throw new IllegalArgumentException(
                    "app.insert.jdbc-batch-size must be positive");
        }

        return chunk -> {
            jdbc.batchUpdate("""
                INSERT INTO posted_payments
                    (snapshot_key, payment_id, account_id, amount_cents)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (snapshot_key, payment_id) DO NOTHING
                """,
                chunk.getItems(),
                jdbcBatchSize,
                (ps, payment) -> {
                    ps.setString(1, payment.snapshotKey());
                    ps.setLong(2, payment.paymentId());
                    ps.setLong(3, payment.accountId());
                    ps.setLong(4, payment.amountCents());
                });
        };
    }
}
~~~

**Lưu ý code:** `@Value("${app.insert.jdbc-batch-size:100}")` là placeholder hợp lệ của Spring; trong source Java thật **không** thêm dấu backslash trước `$`. `JdbcTemplate.batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` trả về `int[][]` update counts; ví dụ cố tình không dùng chúng làm business committed-row count.

Ví dụ:

~~~yaml
app:
  insert:
    jdbc-batch-size: 100
~~~

Nếu `StepBuilder.chunk(500, businessTransactionManager)`, một chunk 500 output items có thể tạo khoảng **5 JDBC batch calls** 100 items. Cả năm calls vẫn phải tham gia **cùng chunk transaction**, nếu `JdbcTemplate` và transaction manager bind cùng datasource. Exception ở call thứ năm trước commit => các writes trong năm calls **rollback cùng nhau**.

**Giới hạn của giải pháp:**

- Đây là **custom `ItemWriter`**, không phải thuộc tính cấu hình trực tiếp trên `JdbcBatchItemWriter`.
- `batchUpdate` split calls bên trong một transaction không tự tạo thêm checkpoints/commits.
- 500 Payment objects vẫn có thể ở trong memory của chunk dù JDBC batch size là 100.
- Driver có thể có additional internal batching/rewrite/round trips.
- Nếu gọi cùng `JdbcTemplate` trỏ nhầm datasource khác, transaction-boundary test sẽ thất bại.
- `ON CONFLICT DO NOTHING` khiến một số update counts bằng 0; một số drivers dùng `SUCCESS_NO_INFO`, không tính new-business-rows bằng cách cộng mù mọi giá trị.

### 7.1. Matrix độc lập giữa C và B

| Chunk C | JDBC batch B | JDBC calls/chunk (lý thuyết) | Chunk transactions |
|---:|---:|---:|---|
| 500 | 500 | 1 | 1 |
| 500 | 100 | 5 | 1 |
| 500 | 50 | 10 | 1 |
| 1.000 | 100 | 10 | 1 |
| 250 | 100 | 3 (100+100+50) | 1 |
| 250 | 250 | 1 | 1 |

Không mặc định số **network packets**, số SQL statements phía server hoặc thời gian COMMIT bằng “JDBC calls/chunk”; driver/SQL rewrite/protocol quyết định chi tiết. Một benchmark tốt nên giữ `C` cố định khi tìm `B` tốt nhất rồi mới thay `C`.

### 7.2. Đừng đặt `B > C` rồi tin có ích

Nếu writer nhận tối đa 250 items/chunk, cấu hình custom `jdbcBatchSize=2_000` không tạo một batch 2.000 items; nó chỉ gửi **tối đa số items thực nhận**, không tự gom qua nhiều chunk transactions. Tự tích lũy writer buffer qua nhiều chunks để đủ 2.000 items có thể **phá transaction/checkpoint semantics**, vì worker có thể báo chunk đã commit trong khi dữ liệu chưa flush xuống DB.

Muốn gom qua chunk boundaries cần thiết kế lại transaction/outbox/bulk loading rõ, không sửa bằng một mutable `List<Payment>` global trong writer.

## 8. PostgreSQL JDBC: `reWriteBatchedInserts` và giới hạn thực

PostgreSQL JDBC driver (`pgjdbc`) hỗ trợ connection property:

~~~properties
reWriteBatchedInserts=true
~~~

Khi điều kiện phù hợp, driver có thể **rewrite một JDBC batch gồm nhiều compatible INSERTs** thành statement kiểu multi-values để giảm overhead/network round trips.

Ví dụ JDBC URL:

~~~text
jdbc:postgresql://postgres-host:5432/payments?reWriteBatchedInserts=true
~~~

Hoặc cấu hình Hikari qua Spring Boot khi datasource được auto-configure:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres-host:5432/payments
    hikari:
      data-source-properties:
        reWriteBatchedInserts: true
~~~

Với ứng dụng có `businessDataSource` tự tạo từ custom prefix, cấu hình `spring.datasource.*` ở trên **có thể không tác động tới pool đó**. Phải truyền property vào **đúng PostgreSQL JDBC DataSource/HikariConfig** và kiểm tra connection thực đang dùng.

### 8.1. Rewrite không phải lúc nào cũng áp dụng

Khả năng rewrite phụ thuộc:

- SQL có phải một `INSERT` tương thích với pattern driver nhận diện không.
- Statement có `RETURNING`, generated keys, dạng SQL phức tạp hoặc cách lấy update counts ảnh hưởng khả năng gộp không.
- Kiểu `ON CONFLICT` và phiên bản driver có hỗ trợ rewrite cho **đúng SQL** đang dùng hay không.
- Driver version, prepared statement mode, số rows/bind parameters và giới hạn nội bộ.
- Statement có triggers/constraints và behavior riêng cần quan sát không.

**Không hứa rằng bật flag sẽ tăng tốc mọi `INSERT`, kể cả UPSERT hoặc `RETURNING`.** Hãy benchmark `false` và `true` trên cùng input/schema, xem generated SQL/pg_stat_statements/logs phù hợp và xác minh update-count/error semantics.

### 8.2. Ví dụ network/SQL ở mức khái niệm

~~~sql
-- Các JDBC parameter sets ban đầu có thể tương đương:
INSERT INTO posted_payments(snapshot_key, payment_id, account_id, amount_cents)
VALUES (?, ?, ?, ?);
-- lặp cho nhiều rows trong batch

-- Driver có thể rewrite khi đủ điều kiện:
INSERT INTO posted_payments(snapshot_key, payment_id, account_id, amount_cents)
VALUES (?, ?, ?, ?),
       (?, ?, ?, ?),
       (?, ?, ?, ?);
~~~

Đây là **minh họa về hình thức SQL**, không phải SQL đã quan sát trên wire trong ứng dụng cụ thể. Driver có thể tách một batch rất lớn thành nhiều statements do giới hạn tham số hoặc lựa chọn nội bộ; lệnh SQL rewrite không thay đổi tính đúng của transaction nếu driver và JDBC connection được dùng đúng.

### 8.3. Không vượt ngân sách bind parameters và payload

PostgreSQL extended query protocol/pgjdbc có giới hạn số bind parameter thực tế cho một statement; rất nhiều phiên bản áp trần ở khoảng **65.535 parameter slots/statement**. Với SQL gồm bốn bind values mỗi row, một câu multi-row rewrite 20.000 rows sẽ cần 80.000 bind slots, vượt mức này nếu không split.

**Không dựa vào 65.535 như con số duy nhất:** còn kích thước payload, memory, server statement limits, JDBC driver split behavior, row width, indexes và biến thể SQL. Với một câu `INSERT ... VALUES (...), ...` tự build, code của bạn phải tự giới hạn số parameters; với pgjdbc rewrite, hãy kiểm tra behavior của đúng driver version.

### 8.4. Rewrite có thể thay đổi cách xử lý lỗi và counts

Khi multi-row INSERT được gộp, một row gây unique violation (không có `ON CONFLICT`) có thể khiến toàn statement lỗi; JDBC `BatchUpdateException`/`getUpdateCounts()` có thể biểu diễn kết quả khác so với các INSERT nhỏ lẻ. Nhưng **transaction rollback** vẫn do transaction manager quyết định; không suy từ partial `SUCCESS_NO_INFO` rằng DB đã durable rows.

Benchmark phải có testcase **một row lỗi giữa batch**, so tính đúng của output sau rollback và fault-tolerant retry/skip nếu step cho phép.

## 9. JPA/Hibernate: `hibernate.jdbc.batch_size` không phải chunk size

Khi worker dùng JPA/Hibernate thay `JdbcBatchItemWriter`, ORM có một batch size riêng. Một cấu hình Spring Boot 3.x/Hibernate 6.x thường có dạng:

~~~yaml
spring:
  jpa:
    properties:
      hibernate.jdbc.batch_size: 50
      hibernate.order_inserts: true
      hibernate.order_updates: true
~~~

**Đây là Hibernate-specific knobs.** Spring Batch `chunk(250)` không tự đặt `hibernate.jdbc.batch_size=50`; Hibernate phải nhận đúng properties của đúng `EntityManagerFactory`. Nếu bạn cấu hình nhiều entity managers/datasources, verify từng factory.

### 9.1. `order_inserts` và ID generation

Hibernate có thể gom SQL statements tốt hơn khi insert các entity cùng table trong thứ tự phù hợp. Tuy nhiên:

- `GenerationType.IDENTITY` thường **hạn chế/không hỗ trợ JDBC insert batching** theo một số Hibernate generation strategies, vì ID cần được trả về sau insert. Cần xác minh với phiên bản ORM/driver.
- `SEQUENCE` với allocation strategy phù hợp có thể tạo điều kiện batching tốt hơn, nhưng phải giữ ID uniqueness/restart semantics.
- Cascades, entity graphs, inheritance, versioning và flush timing có thể chia batch thành nhiều nhóm nhỏ.
- `hibernate.order_inserts=true` có chi phí sorting/ordering và phải test các constraint/order-sensitive side effects.

**Không đổi primary key strategy trên database production chỉ vì muốn batching** khi chưa phân tích schema, migration, business identity và consistency.

### 9.2. Memory và persistence context

Một `JpaItemWriter`/EntityManager giữ entities trong persistence context cho tới khi flush/clear theo lifecycle. Với chunk quá lớn và entity graphs nặng:

- Heap và GC tăng đáng kể.
- Dirty checking, cascade và SQL ordering tốn CPU.
- Flush có thể tạo SQL trước `COMMIT`; exception sau flush vẫn rollback transaction.
- Persistence context stale sau rollback cần xử lý/clear theo contract ORM.

Các phép thử cần đo **allocated bytes, GC pause, max live heap, flush latency** cùng với database throughput. Với job ETL ghi rất nhiều rows không cần entity lifecycle, `JdbcBatchItemWriter` hoặc PostgreSQL `COPY` có thể phù hợp hơn JPA, nhưng phải đánh giá logic, validate và restart/idempotency.

### 9.3. Hai ví dụ dễ bị nhầm

~~~text
Case A:
  Spring Batch chunkSize = 500
  Hibernate jdbc.batch_size = 50
  Hibernate có thể flush nhiều JDBC batches <= 50 statements
  Chunk transaction vẫn chứa tối đa 500 output items.

Case B:
  Spring Batch chunkSize = 50
  Hibernate jdbc.batch_size = 500
  Không tự gom entities từ 10 chunks đã commit thành
  một JDBC batch 500 ở cùng transaction.
~~~

Hãy kiểm tra Hibernate statistics/JDBC SQL traces (nếu bật cho benchmark) để biết **actual executed batches** thay vì suy từ cấu hình.

## 10. PostgreSQL `COPY` và bulk load: khi JDBC batch không còn phù hợp

Với một pipeline append-only nhập hàng trăm triệu rows vào staging table, PostgreSQL `COPY FROM STDIN` có thể hiệu quả hơn nhiều `INSERT` statements nhờ đường tải dữ liệu được tối ưu. Tuy nhiên, nó **không phải chỉ là “batch size = rất lớn”**:

- `COPY` có API/streaming và error behavior riêng.
- Một transaction `COPY` lớn giữ lâu nếu không chia theo khối/partition.
- Direct `COPY` vào table có indexes/constraints vẫn có chi phí; cách staging → validate → merge có trade-off về dung lượng, WAL, indexes và số lần ghi.
- `ON CONFLICT`/row-level UPSERT semantics cần một bước merge thích hợp, không mặc định áp thẳng vào `COPY`.
- Restart cần biết khối dữ liệu nào đã commit, không phát lại toàn bộ mà không có idempotency.
- Nếu nhiều workers đồng thời `COPY` vào cùng target/index nóng, bottleneck DB vẫn có thể tăng.

Một kiến trúc tham khảo:

~~~mermaid
flowchart LR
    S["Immutable snapshot"] --> W["Workers: transform + stream"]
    W --> ST[(Staging table / COPY)]
    ST --> V["Validate counts, keys, checksum"]
    V --> U["INSERT ... SELECT / UPSERT"]
    U --> T[(Final business table)]
    U --> L["Committed batch ledger"]
~~~

Khi nào nên benchmark cả `COPY`?

| Workload | JDBC batches | `COPY` + staging |
|---|---|---|
| Vài nghìn row/job | Đơn giản, đủ nhanh trong nhiều trường hợp | Overhead staging có thể không đáng |
| Hàng triệu append-only rows, ít biến đổi | Đáng đo | Có thể giảm overhead đáng kể |
| UPSERT theo business key, duplicate detection phức tạp | `ON CONFLICT` trực tiếp đơn giản | Cần staging/merge/ledger |
| Per-row API triggers/validation đặc biệt | SQL writer dễ kiểm soát | Cần kiểm tra compatibility |
| Strict chunk restart theo item | Spring Batch dễ quản lý với reader/writer | Phải thiết kế checkpoint/idempotency riêng |

**Không đổi sang `COPY` chỉ vì một benchmark synthetic nhanh**. Hãy đánh giá đúng DDL/indexes, error recovery, business constraints và dữ liệu phát sinh từ worker partitions của hệ thống.

## 11. Những tài nguyên quyết định batch insert size

Batch size tác động tới **toàn pipeline**, không chỉ DB network. Mục tiêu tuning là tìm giới hạn **đầu tiên** bị chạm khi tăng size.

### 11.1. Memory và row width

Một ước tính đơn giản cho `C` items được giữ trong chunk:

\[
M_{\mathrm{chunk}}\approx C\times
(\mathrm{object\ footprint}+\mathrm{payload}+\mathrm{intermediate\ references})
\]

Ví dụ:

- `C=250`, mỗi processed object footprint khoảng 1 KiB ⇒ khoảng 250 KiB cho payload objects, **chưa tính driver bindings, raw input, processor allocations, ORM và thread-local state**.
- `C=5.000`, mỗi object footprint khoảng 64 KiB ⇒ khoảng 312,5 MiB payload objects (tính theo 64 KiB × 5.000 / 1.048.576), **trước** các bản sao/buffer.

Đây là **ước lượng minh họa**, object overhead trong JVM/ORM/driver có thể rất khác. Hãy đo heap allocation, GC pause, max live set và pod memory limit dưới concurrency thật. Một batch size phù hợp record nhỏ có thể gây OOM với JSONB/document lớn.

### 11.2. Transaction duration và lock footprint

Chunk lớn thường làm transaction kéo dài. Điều này quan trọng khi writer:

- UPSERT cùng business key từ nhiều workers.
- Update aggregate row/hot partition.
- Có triggers, foreign keys hoặc constraints đắt tiền.
- Đọc/ghi nhiều tables trong cùng transaction.
- Chờ disk fsync/WAL, replication lag hoặc downstream DB resource.

Với row locks, transaction phải giữ những locks cần thiết tới commit/rollback; tăng `C` có thể tăng thời gian workers khác phải đợi. **Một batch insert nhanh khi chạy một worker có thể làm hệ thống chậm khi chạy 16 workers.**

### 11.3. WAL, indexes và constraints

Mỗi row insert còn làm:

- Ghi heap pages + index entries.
- Tạo WAL và có thể phát sinh full-page images.
- Duy trì primary/unique key, foreign key, triggers.
- Chịu transaction commit/fsync và replication policy.

Gom JDBC calls **không xóa** các chi phí này. Nếu WAL hoặc disk I/O đang bão hòa, tăng batch size có thể chủ yếu chuyển chi phí thành những đợt spike lớn.

**Không tắt unique constraints/triggers hoặc `synchronous_commit` một cách tùy tiện** để làm benchmark đẹp hơn. Những thay đổi này có thể thay durability, replication và correctness contract.

### 11.4. CPU và connection pool

Nếu worker là CPU-bound ở processor, writer batching lớn hơn có thể gần như không thay end-to-end wall clock. Nếu worker luôn đợi Hikari connection, cần xem connection hold, reader cursor, `REQUIRES_NEW`, DB locks và tổng pool sizes trước khi tăng `B`.

**Một pool larger không tự giải quyết DB bottleneck:** nhiều transactions có thể chỉ tạo thêm lock contention và WAL pressure. Theo dõi throughput **unique committed rows/giây** chứ không chỉ các dòng log “batch executed”.

## 12. Multi-threaded step, parallel steps và remote partitioning

Khi Spring Batch được scale-out, batch size hợp lý **ở một worker** chưa chắc hợp lý **trên toàn cluster**.

~~~mermaid
flowchart TB
    M["Manager: partition plan + dispatch"] --> Q[(Broker)]
    Q --> W1["Worker A: chunk C, JDBC batch B"]
    Q --> W2["Worker B: chunk C, JDBC batch B"]
    Q --> W3["Worker C: chunk C, JDBC batch B"]
    W1 --> D[(Shared PostgreSQL)]
    W2 --> D
    W3 --> D
    W1 --> J[(Shared JobRepository)]
    W2 --> J
    W3 --> J
~~~

### 12.1. Một giới hạn ở cluster

Giả sử:

- 8 worker pods.
- Mỗi pod tối đa 4 active partition `StepExecution`.
- `chunkSize=500` và writer batches mặc định theo chunk.
- Hikari business pool max 10 connections/pod.

Tối đa `8×4=32` active executions theo giới hạn listener/worker, và pool có thể mở gần `8×10=80` business connections **nếu có nhu cầu**. Nhưng một `JdbcCursorItemReader` có thể giữ connection khi đọc trong lúc writer transaction cần connection khác; còn phải cộng **manager, metadata pool, các applications khác, rolling deploy surge** nếu chúng cùng dùng PostgreSQL instance.

\[
\mathrm{activeExecutions}_{\max}\le
\mathrm{workerPods}\times\mathrm{maxConcurrentPerPod}
\]

\[
\mathrm{businessPoolConnections}_{\max}\le
\sum_{\mathrm{pods}}\mathrm{maximumPoolSize}_{\mathrm{business}}
\]

Không suy hai giá trị phải bằng nhau hoặc mỗi execution luôn chỉ mượn đúng một connection. Đo Hikari active/idle/pending/acquire p95 và `pg_stat_activity`.

### 12.2. JDBC batches in-flight và memory

Nếu 32 executions đồng thời giữ một chunk 500 Payment objects:

\[
\mathrm{logical\ inMemoryItems}\lesssim 32\times500=16\,000
\]

Đây là **ngân sách minh họa cho chunk payload**, chưa tính reader buffers, input streams, processor intermediates, nested writers, Hibernate persistence contexts và driver bind arrays. Multi-threaded chunk step có thể làm nhiều chunks đồng thời trong **một `StepExecution`**, vì vậy cần đo concurrency thực thay vì nhân tùy tiện số partitions.

### 12.3. Tăng chunk size có thể làm partition tail tệ hơn

Một partition chỉ còn 300 rows trong khi `chunk(5_000)`; worker vẫn phải chờ xử lý/commit cả phần cuối rồi mới báo complete. Nếu vài partitions chạm hot rows, transaction lớn có thể kéo dài, khiến các pods khác đã idle vẫn phải chờ **slowest partition**.

Đặt batch size theo **throughput đồng thời, tail latency, rollback cost và số bytes per item**, không chỉ theo peak `rows/s` của một worker.

### 12.4. Remote chunking có một chỗ giữ dữ liệu khác

Trong **remote chunking**, manager đọc và gửi chunks tới workers; tăng chunk size có thể làm **broker message payload**, serialization memory, retry/redelivery size và manager checkpoint behavior tăng mạnh. Ngoài DB write batching, cần đo:

- Message bytes/payload limit.
- Queue age, unacked/in-flight messages và prefetch.
- Worker processing/commit p95.
- Duplicate delivery và side effects khi reply/ACK mất.
- Reader checkpoint của manager và idempotency của worker.

Không áp size 5.000 record/chunk từ local JDBC job sang remote chunking mà không benchmark broker/network và giới hạn transport.

### 12.5. Thread safety là điều kiện tiên quyết

Với **multi-threaded step**, một `@StepScope` reader vẫn có thể bị chia sẻ giữa các chunk threads **cùng `StepExecution`**. Một reader stateful không thread-safe có thể bỏ sót/trùng input khi tăng concurrency, khiến throughput “đẹp” vì bớt dữ liệu đã được xử lý.

Để benchmark có giá trị, phải có **exact business key set/checksum validation**, không chỉ so `readCount/writeCount` và wall clock.

## 13. Các cấu hình dễ bị hiểu nhầm trong production

| Knob | Tác dụng thực | Không nên suy ra |
|---|---|---|
| `chunk(500, tm)` | Commit/checkpoint granularity của chunk step | Hibernate sẽ tạo đúng một statement 500 rows |
| `hibernate.jdbc.batch_size=50` | JDBC DML grouping tại ORM | Spring Batch reader đọc từng 50 items |
| `reWriteBatchedInserts=true` | PgJDBC **có thể** rewrite compatible batched inserts | Mọi UPSERT/RETURNING/JPA SQL sẽ thành multi-values |
| Hikari `maximumPoolSize=20` | Trần connection của **một pool** | Cho phép tối ưu 20 workers hoặc cần tăng chunk size |
| Reader `fetchSize=1000` | Driver/reader fetch hint | Writer JDBC batch size = 1000 |
| `gridSize=16` | Gợi ý/phần chia logic partition tùy handler/partitioner | 16 worker processes chạy song song |
| Broker prefetch=10 | Số delivery in-flight tới consumer theo broker | Chunk transaction chứa 10 items |
| Java `List` buffer 1000 items | Memory batching ở app | Đã JDBC execute hoặc commit |
| `ON CONFLICT DO NOTHING` | Hàng rào duplicate insert theo unique key | Cùng key nhưng payload khác luôn được phát hiện |
| `JdbcTemplate.batchUpdate()` | Thực thi JDBC batch | Dữ liệu đã commit nếu surrounding transaction còn active |

Khi review configuration, bắt đầu bằng câu: **“Batch size ở tầng nào, áp dụng trên mỗi process hay toàn cluster, và commit boundary ở đâu?”**

## 14. Đừng tối ưu INSERT trước khi kiểm tra SQL và index

Một database có thể chậm vì query plan hoặc index/lock, không phải vì `B` quá nhỏ.

### 14.1. Reader có index phục vụ filter/range/sort

Ví dụ:

~~~sql
SELECT snapshot_key, payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = :snapshotKey
  AND payment_id >= :fromInclusive
  AND payment_id < :toExclusive
ORDER BY payment_id;
~~~

Primary key `(snapshot_key, payment_id)` trong phần 4 **đã tạo index phù hợp leading columns** cho trường hợp này. Không tạo thêm một index có key trùng chỉ để thấy biểu đồ nhanh hơn: mỗi index dư làm tăng chi phí insert và WAL.

Trên staging:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT snapshot_key, payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = 'insert-bench-001'
  AND payment_id >= 1
  AND payment_id < 25002
ORDER BY payment_id;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi SELECT thực tế** để đo; với DML hãy làm trên test DB hoặc trong transaction rollback được kiểm soát nếu muốn dùng EXPLAIN ANALYZE (vì DML có side effects). Không chạy test nặng trên production chỉ để lấy một query plan nếu có thể gây tải.

### 14.2. Writer conflicts

Khi target có primary key, unique index, triggers và FK, mỗi insert phát sinh nhiều kiểm tra. Với `ON CONFLICT DO NOTHING`, nếu hầu hết rows đã tồn tại, lần benchmark thứ hai **gần như không tạo output mới**; tổng thời gian so với lần đầu **không còn cùng workload**.

So riêng:

- **Cold insert:** target chưa có các business keys.
- **Replay no-op:** cùng snapshot/keys đã có, hợp lệ về idempotency.
- **Mixed upsert:** ví dụ 80% new, 20% existing theo một fixture ổn định.
- **Conflict mismatch:** cùng key nhưng khác amount, phải phát hiện theo contract.

### 14.3. Quá nhiều nhỏ lẻ cũng tạo transaction overhead

Nếu một worker tạo 100.003 chunks với `chunk(1)`, `JobRepository` có thể phải cập nhật checkpoint/`StepExecution` liên tục; ngoài WAL business writes còn metadata DB traffic. Tuning writer không chỉ giảm network trong business DB, mà còn thay đổi frequency của Batch transaction/metadata lifecycle.

Với **JobRepository DB khác business DB**, chunk commit có thể **không atomic** cùng checkpoint metadata; phải test restart/idempotency, không chỉ throughput.

## 15. Kết hợp retry, skip và rollback khi điều chỉnh size

Một chunk 5.000 rows thất bại sau 4.999 SQL operations chưa commit có thể phải rollback và xử lý lại cả chunk theo policy. Với batch nhỏ 100, số rows bị làm lại do một lỗi cục bộ có thể nhỏ hơn, nhưng số transactions/round trips tăng.

~~~text
Chunk size = 1.000
Input items 1..1.000
Writer executes many statements
Item 999 gây transient DB error
Chunk transaction rollback (nếu đúng transaction wiring)
Retry policy chạy lại work theo Spring Batch lifecycle

Nếu writer có external side effects không nằm trong transaction:
  các side effects của lần thử trước KHÔNG tự rollback.
~~~

### 15.1. Tác động của batch size tới tỷ lệ làm lại

Gọi:

- `B`: số items mỗi JDBC batch call.
- `C`: số items mỗi chunk transaction.
- `p`: xác suất một **item** gây lỗi cần rollback, giả định độc lập và nhỏ.

Xác suất có ít nhất một item lỗi trong chunk là:

\[
P(\mathrm{error\ in\ chunk})=1-(1-p)^C
\]

Đây là **mô hình giả định**, không thay thế đo thực tế: lỗi DB có thể tương quan theo time window, hot key, SQL plan hoặc tài nguyên toàn cluster. Khi `C` tăng, xác suất một chunk gặp ít nhất một lỗi item cũng tăng trong mô hình này; nhưng retry/skip semantics thực còn phụ thuộc loại lỗi và thời điểm SQL executed/commit.

### 15.2. Fault-tolerant step

~~~java
return new StepBuilder("resilientPaymentWorkerStep", jobRepository)
        .<Payment, Payment>chunk(250, businessTransactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .build();
~~~

**Mô tả code:** các types `TransientDataAccessException` của Spring, `InvalidPaymentException` của nghiệp vụ và các beans reader/writer cần được cấu hình. Retry cần phân loại SQLState/error semantics; không retry mọi exception đến từ PostgreSQL như nhau. `40P01` deadlock/`40001` serialization failure thường yêu cầu **rollback rồi retry cả transaction**; `23505` có thể là business duplicate hoặc payload mismatch, không retry mù.

### 15.3. Writer skip có thể bị gọi lại nhiều lần

Khi một JDBC batch chứa một item lỗi, framework có thể phải rollback/replay/scan để xác định item cần skip trong fault-tolerant step. `ItemWriter.write()` có thể được gọi lại với subgroups; số **attempted JDBC statements** có thể lớn hơn số committed new rows.

Do đó không dùng `writerInvocationCount` hoặc số lần `batchUpdate` trả về để suy business output. Test phải đo:

- Expected valid unique business keys.
- Skipped item IDs và `read/process/writeSkipCount` đúng policy.
- Không có partial committed writes của chunk đã rollback.
- Retry/backoff có giới hạn, không retry storm.
- Idempotency trong mọi lần replay, đặc biệt nếu worker dùng nhiều resource.

### 15.4. `noRollback` không phải cách cứu batch quá lớn

Không dùng `noRollback(...)` để giữ những INSERT đã thực hiện khi PostgreSQL transaction đã bị đánh dấu aborted bởi SQL error. Nó có thể khiến statements tiếp theo tiếp tục fail, hoặc tạo trạng thái khó giải thích. Tối ưu transaction phải dựa trên error classification, DB semantics và business invariant, không né rollback chỉ để giảm thời gian.

## 16. Thiết kế benchmark: đo size tối ưu thay vì đoán

Mục tiêu benchmark không phải “size nào có peak `writeCount/s` cao nhất”, mà là **size nào đạt nhiều business rows hợp lệ đã commit nhất trong một đơn vị thời gian/tài nguyên**, dưới cùng workload, trong khi đáp ứng tail latency, memory và restart SLO.

### 16.1. Xác lập baseline

Trước khi đổi configuration:

1. Cố định **input snapshot** và expected count/checksum.
2. Ghi số worker processes, consumer concurrency, partition ranges, `chunkSize` và JDBC batch settings.
3. Ghi JDK, Spring Batch/Boot, PostgreSQL, pgjdbc version, Hikari và JVM heap limits.
4. Chọn DDL/index/constraint/trigger giống production; không tắt durability để lấy số đẹp.
5. Đo **end-to-end job wall clock** từ một mốc thống nhất, `time-to-first-chunk` và slowest partition.
6. Đo `writer-call` p50/p95, `chunk elapsed` p95, DB commit latency và Hikari acquire p95 nếu quan sát được.
7. Ghi PostgreSQL lock/WAL/IO/CPU và Hikari active/idle/pending; phân biệt resource chung với riêng job.
8. Đối soát unique business keys, payload/aggregate và StepExecution trạng thái sau khi hoàn tất.

Benchmark cần thực hiện trên **test/staging** với dữ liệu được cô lập và năng lực tài nguyên ổn định; không đẩy 100.000 jobs production chỉ để đo.

### 16.2. Thử chunk size theo dãy có khoảng

Một dãy thử ban đầu hợp lý:

~~~text
chunkSize: 1, 50, 100, 250, 500, 1000, 2000
~~~

**Đây là grid thử nghiệm, không phải giá trị khuyến nghị mặc định.** Với JSONB lớn, có thể chỉ thử 10/25/50/100; với narrow bulk load có thể thử thêm 5.000. Thử `B` và `C` tách biệt:

| Phase | Cố định | Thay đổi | Mục tiêu |
|---|---|---|---|
| A | Workers=1, JDBC writer theo chunk, DB/DDL cố định | `chunkSize=1/50/100/250/500/1000` | Tìm commit/round-trip overhead và memory trade-off |
| B | `chunkSize=500`, workers=1, custom split writer | `jdbcBatchSize=25/50/100/250/500` | Tách ảnh hưởng JDBC calls khỏi chunk transactions |
| C | `chunkSize=250`, `jdbcBatchSize` đã chọn | `reWriteBatchedInserts=false/true` | Đo driver rewrite trên SQL thật |
| D | `chunkSize`/`B` đã chọn, cùng snapshot | 1/2/4/8/16 worker slots | Tìm DB saturation và scaling efficiency |
| E | Cấu hình được chọn | Uniform vs skewed data; new vs replay | Kiểm tra tail, conflict và idempotency |

**Không so ngay phase A chunk 250 với phase C rewrite true, workers 16** rồi kết luận một knob đã cải thiện throughput: nhiều biến cùng thay đổi và kết quả không có quan hệ nhân quả rõ.

### 16.3. Mỗi run phải dùng target state tương đương

Với writer `ON CONFLICT DO NOTHING`, một lỗi benchmark phổ biến:

~~~text
Run 1: 100.003 source items -> INSERT 100.003 new rows
Run 2: 100.003 same source items -> DO NOTHING 100.003 conflicts
Run 3: 100.003 same source items -> DO NOTHING 100.003 conflicts
~~~

So thời gian ba run **không phản ánh cùng loại công việc**. Muốn benchmark **cold new insert**, reset target/test schema theo quy trình an toàn giữa các run hoặc dùng snapshot/test partition khác có **cùng dữ liệu/size/constraints**. Muốn benchmark replay, chạy tất cả cấu hình trong **cùng điều kiện target keys đã tồn tại**.

Nếu dùng `TRUNCATE` để reset, chỉ thực hiện ở DB/schema riêng của benchmark, không trên bảng dùng chung với worker/test khác.

### 16.4. Random hóa thứ tự và thu nhiều mẫu

Nếu chạy size 1 trước, size 100 rồi 1.000, database cache/JIT có thể đã warm ở các size sau. Để giảm confounding:

- Chạy warm-up trước khi đo steady-state, hoặc ghi riêng cold/warm.
- Hoán đổi thứ tự các sizes giữa các vòng.
- Thu nhiều repetitions trên cùng fixture tương đương.
- Báo median, p95 và độ biến động; không chỉ chọn run nhanh nhất.
- Ghi tình trạng cache, vacuum/checkpoint, replication, contention từ workload khác.
- Với job ngắn hơn Prometheus scrape interval, dùng timestamps/traces/job metadata thay cho `rate(...[5m])` không đủ samples.

### 16.5. Ví dụ kết quả minh họa

Bảng sau là **số giả định phục vụ cách đọc**, không phải benchmark đo được:

| Chunk size | End-to-end unique rows/s | Chunk duration p95 | Writer/transaction symptoms |
|---:|---:|---:|---|
| 1 | 1.200 | 4 ms | Nhiều transaction/metadata overhead |
| 50 | 6.200 | 18 ms | Round-trip efficiency tốt hơn |
| 100 | 7.800 | 30 ms | Tăng ổn định |
| 250 | 9.100 | 60 ms | Có thể là ứng viên tốt |
| 500 | 9.500 | 120 ms | Throughput nhỉnh hơn, rollback chunk tốn hơn |
| 1.000 | 9.200 | 280 ms | Latency/locks bắt đầu tăng |
| 5.000 | 7.900 | 1.400 ms | Transaction/pool/GC pressure |

Nếu SLO yêu cầu chunk p95 dưới 100 ms, **250** trong bảng giả định có thể phù hợp hơn **500** dù 500 có thêm khoảng 4,4% unique throughput. Nhưng p95 và số workers/DB resources phải cùng điều kiện; không đưa ra kết luận cho hệ thống thật từ số minh họa.

### 16.6. Chỉ số ra quyết định

Nên đặt cạnh nhau:

\[
\mathrm{usefulRate}=\frac{\text{new valid unique business keys}}
{\text{job wall time}}
\]

\[
\mathrm{speedup}(N)=\frac{T(1)}{T(N)},\qquad
\mathrm{efficiency}(N)=\frac{\mathrm{speedup}(N)}{N}
\]

Tối ưu theo **SLO và resource budget**, không phải theo rate đơn lẻ. Nếu size 500 nhanh hơn 3% nhưng p99 commit latency tăng gấp đôi và thêm deadlocks, lựa chọn size 250 có thể an toàn hơn.

## 17. Các số đo thực tế cần lấy khi tuning

### 17.1. Spring Batch metadata

Qua `JobExplorer`/`JobRepository` hoặc truy vấn read-only trên schema đúng version:

~~~sql
SELECT STEP_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       READ_COUNT,
       WRITE_COUNT,
       FILTER_COUNT,
       COMMIT_COUNT,
       ROLLBACK_COUNT,
       READ_SKIP_COUNT,
       PROCESS_SKIP_COUNT,
       WRITE_SKIP_COUNT,
       START_TIME,
       END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

`writeCount` phản ánh writer items theo semantics Batch, **không đồng nghĩa số rows mới** khi writer dùng `DO NOTHING`, multi-table updates, retries hay triggers. `commitCount`/`rollbackCount` là counters của StepExecution lifecycle, không thể suy trực tiếp số business SQL statements commit/rollback. Đặc biệt khi job restart, một logical partition có thể có nhiều executions.

### 17.2. Business output oracle

~~~sql
SELECT count(*) AS committed_unique_keys,
       sum(amount_cents) AS total_amount_cents
FROM posted_payments
WHERE snapshot_key = 'insert-bench-001';
~~~

Với fixture phần 4, kỳ vọng:

~~~text
committed_unique_keys = 100003
total_amount_cents    = 50003500060
~~~

Primary key bảo đảm tối đa một output row cho mỗi `snapshot_key,payment_id`, nhưng **count và tổng tiền vẫn chưa đủ phát hiện mọi payload swap/missing row** nếu nghiệp vụ thay đổi. Kiểm tra set hai chiều:

~~~sql
-- Input expected nhưng output thiếu:
SELECT payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = 'insert-bench-001'
EXCEPT
SELECT payment_id, account_id, amount_cents
FROM posted_payments
WHERE snapshot_key = 'insert-bench-001';

-- Output thừa hoặc payload không khớp:
SELECT payment_id, account_id, amount_cents
FROM posted_payments
WHERE snapshot_key = 'insert-bench-001'
EXCEPT
SELECT payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = 'insert-bench-001';
~~~

Cả hai tập phải rỗng nếu transformation là **identity**, còn với filter/transform phải so output với **expected transformed set**. `EXCEPT` dùng set semantics; nếu output không có unique constraint, phải kiểm tra duplicate multiplicity riêng.

### 17.3. HikariCP connection pool

Một số signals cần thu (tên Prometheus/Actuator tùy registry):

~~~text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
~~~

Chờ connection acquisition tăng khi `chunkSize` hoặc workers tăng có thể chỉ ra pool starvation, long reader cursor, `REQUIRES_NEW` hoặc DB lock waits. Không mặc định tăng pool là tối ưu; cần xác định nguyên nhân **connection được giữ lâu**.

### 17.4. PostgreSQL wait events

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Xem blockers nếu nghi lock:

~~~sql
SELECT
    pid, application_name, state,
    wait_event_type, wait_event,
    pg_blocking_pids(pid) AS blockers,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

`transaction_age` không phải thời gian chờ lock chính xác. Workload nhiều writers có thể bị `transactionid`/row lock contention; nên kết hợp query/SQL logs và resource metrics để tìm hot keys.

### 17.5. WAL và write amplification

Trên PostgreSQL có các field phù hợp:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
~~~

Các giá trị này thường là **counters cấp PostgreSQL cluster/instance**, không thuộc riêng một worker. `wal_write_time`/`wal_sync_time` tùy tracking configuration (ví dụ `track_wal_io_timing` ở các phiên bản hỗ trợ). Lấy **delta cùng thời gian** giữa runs, chú ý workload khác trên DB; không so WAL bytes của môi trường có 3 indexes với môi trường bỏ hết indexes.

### 17.6. Quan sát SQL thực được chạy

Có thể sử dụng PostgreSQL `pg_stat_statements` khi extension được cài và quyền cho phép, query sampling/auto-explain/logging phù hợp hoặc APM JDBC observations. Kiểm tra:

- Số SQL executions/batch calls và mean/p95 theo khả năng công cụ.
- Có thật sự rewrite thành multi-row `INSERT` hay không.
- Có SQL `RETURNING`/UPSERT làm driver không rewrite không.
- Số affected rows và lỗi/`BatchUpdateException`.
- WAL/lock duration/commit latency.

**Không bật log mọi parameter values trên production**: log có thể rò thông tin nhạy cảm và tự làm chậm benchmark.

## 18. Instrument đúng: attempted vs committed

Một `ItemWriter` decorator có thể đo **writer call duration** và **số items đưa vào writer**:

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class TimedPaymentWriter implements ItemWriter<Payment> {

    private final ItemWriter<Payment> delegate;
    private final Counter attemptedItems;
    private final Timer writerCallDuration;

    public TimedPaymentWriter(
            ItemWriter<Payment> delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.attemptedItems = Counter.builder(
                "batch.insert.writer.items.attempted")
                .tag("step_role", "payment-worker")
                .register(registry);
        this.writerCallDuration = Timer.builder(
                "batch.insert.writer.call.duration")
                .tag("step_role", "payment-worker")
                .register(registry);
    }

    @Override
    public void write(Chunk<? extends Payment> chunk) throws Exception {
        attemptedItems.increment(chunk.size());
        long began = System.nanoTime();
        try {
            delegate.write(chunk);
        } finally {
            writerCallDuration.record(
                    System.nanoTime() - began, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

**Không gọi `attemptedItems` là committed new rows.** Nếu writer ném lỗi sau khi `executeBatch` đã thực thi nhưng transaction rollback, counter vẫn tăng. Timer đo duration của `write()`, **không bao gồm** transaction COMMIT sau khi writer return.

Nếu delegate implement `ItemStream`, wrapper chỉ implement `ItemWriter` có thể **che `open/update/close` lifecycle**; cần forward/delegate lifecycle hoặc đăng ký component đúng kiểu khi kết hợp reader/writer stateful. Với `JdbcBatchItemWriter` thông thường, xác minh threading/bean scope đúng cấu hình; đừng chia sẻ writer có mutable state không thread-safe.

### 18.1. Micrometer/Prometheus chỉ phục vụ quan sát

Nếu counter xuất ra dưới dạng Prometheus `batch_insert_writer_items_attempted_total`:

~~~promql
sum(rate(batch_insert_writer_items_attempted_total[5m]))
~~~

Để so theo role:

~~~promql
sum by (step_role) (
  rate(batch_insert_writer_items_attempted_total[5m])
)
~~~

**Tên xuất thực tế phụ thuộc registry**; kiểm tra endpoint `/actuator/prometheus` hoặc collector tương đương. Luôn tính `rate` trên **từng counter series trước khi `sum`** để xử lý pod restart/counter resets, nhưng metric chưa scrape trước khi process chết **không thể tự phục hồi**. Business database/ledger là nguồn đối soát thật.

Đừng gắn `paymentId`, `jobExecutionId`, `stepExecutionId`, `partitionName` có số lượng vô hạn thành metric tags. Dùng low-cardinality `step_role`, `error_category`, `pool_name`; giữ IDs chi tiết trong structured logs/traces với retention phù hợp.

### 18.2. Commit duration không có sẵn từ writer timer

Nếu cần đo chính xác commit latency, instrument tại transaction manager/JDBC/DB resource hoặc các transaction lifecycle hooks có ngữ nghĩa rõ. `beforeCommit`/`afterCommit` callback không đồng nghĩa client đã quan sát **mọi resource** commit hoặc metric sẽ không mất khi process crash. Với separate metadata DB và business DB, phải ghi rõ transaction nào được đo.

### 18.3. Tại sao không lấy throughput cao nhất mà bỏ latency?

Một batch 5.000 items có thể giảm writer-call overhead nhưng chunk commit p99 tăng tới vài giây; trong remote chunking, message timeout/redelivery có thể khởi động replay không cần thiết, còn trong DB, row locks khiến worker khác đợi lâu hơn. Tuning cần nhìn:

~~~text
unique committed business rows/s
job wall-clock / deadline
writer-call latency p95
chunk/commit latency p95, p99
rollback/retry count
Hikari pending/acquire p95
PostgreSQL lock/WAL/IO
GC/heap/CPU
partition max duration / broker queue age
~~~

**Rate không thay thế quality hoặc resilience**. Một job chạy nhanh nhưng bỏ 20 payment IDs không phải tối ưu.

## 19. Test transaction: chia nhiều JDBC batches nhưng vẫn rollback cả chunk

Nếu tự tách writer `JdbcTemplate.batchUpdate` thành các call 100 items bên trong chunk 500, test phải chứng minh **500 items vẫn nằm trong một transaction**. Một lỗi ở batch call cuối không được để các call trước tự commit.

### 19.1. PostgreSQL Testcontainers và Spring Boot Test

Ví dụ dưới đây **kiểm tra local Spring JDBC transaction với hai JDBC batches trong một transaction**. Đây là tầng test nền tảng, **chưa phải E2E Spring Batch job**. Với ứng dụng đang có Spring Boot main class, có thể thay `TestApplication` bằng app/test configuration thực tế.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(classes = SplitJdbcBatchRollbackIT.TestApplication.class,
        properties = {
            "spring.batch.job.enabled=false",
            "spring.batch.jdbc.initialize-schema=always"
        })
class SplitJdbcBatchRollbackIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("batch_size_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {}

    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;

    record Row(long id, long amount) {}

    @BeforeEach
    void setUp() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS insert_probe (
                payment_id BIGINT PRIMARY KEY,
                amount_cents BIGINT NOT NULL
            )
            """);
        jdbc.update("DELETE FROM insert_probe");
    }

    private void insertInTwoJDBCBatches(List<Row> rows) {
        jdbc.batchUpdate("""
            INSERT INTO insert_probe(payment_id, amount_cents)
            VALUES (?, ?)
            """, rows, 2, (ps, row) -> {
                ps.setLong(1, row.id());
                ps.setLong(2, row.amount());
            });
    }

    @Test
    void throwsAfterAllJDBCCallsAndRollsBackWholeTransaction() {
        List<Row> rows = List.of(
                new Row(1L, 10L), new Row(2L, 20L),
                new Row(3L, 30L), new Row(4L, 40L));

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        assertThatThrownBy(() ->
                tx.executeWithoutResult(status -> {
                    insertInTwoJDBCBatches(rows);
                    // Đã thực thi 2 JDBC batch calls nhưng chưa COMMIT.
                    throw new IllegalStateException("Injected rollback");
                }))
                .isInstanceOf(IllegalStateException.class);

        // Query từ test thread sau transaction callback đã thoát.
        Long committed = jdbc.queryForObject(
                "SELECT count(*) FROM insert_probe", Long.class);
        assertThat(committed).isZero();
    }

    @Test
    void commitsAllFourRowsWhenNoFailure() {
        List<Row> rows = List.of(
                new Row(1L, 10L), new Row(2L, 20L),
                new Row(3L, 30L), new Row(4L, 40L));

        new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> insertInTwoJDBCBatches(rows));

        Long committed = jdbc.queryForObject(
                "SELECT count(*) FROM insert_probe", Long.class);
        assertThat(committed).isEqualTo(4L);
    }
}
~~~

**Điều kiện để chạy thực tế:** dependencies `spring-boot-starter-jdbc`, PostgreSQL JDBC driver, Spring Boot Test, JUnit 5, AssertJ, Testcontainers JUnit/PostgreSQL module và container runtime. Khi có Spring Batch Starter, property `spring.batch.jdbc.initialize-schema=always` khởi tạo metadata schema trên **database test độc lập**, không dùng trên database production có metadata cần bảo toàn. `spring.batch.job.enabled=false` tắt việc tự launch job của Boot theo cấu hình; ứng dụng có nhiều transaction managers thì inject **đúng business manager bằng qualifier**. Test method **không có `@Transactional`**, tránh transaction của chính JUnit test che kết quả rollback.

Test chứng minh **JDBC calls chia nhỏ không tự tạo thêm commit boundaries** nếu cùng transaction. Nó **không chứng minh** `JdbcBatchItemWriter` của Spring Batch đang dùng cùng datasource, và không kiểm tra `ExecutionContext`/restart. Cần test bước kế tiếp.

### 19.2. Integration test Spring Batch step

Trên Spring Batch Test 5.2.x với một `JobRepository` thật:

1. Tạo reader với 1.003 immutable Payments, writer giống phần 5/7, `chunk(250)`.
2. Ghi output bằng một business transaction manager đã định rõ.
3. Inject writer failure sau SQL cho chunk chứa `payment_id=600`, trước COMMIT.
4. Chờ job/worker `FAILED` (đối với fail-fast policy).
5. Đọc output bằng connection độc lập: chunk chứa 600 **không có rows committed**, các chunks trước vẫn còn.
6. Restart **cùng JobInstance** với checkpoint/reader hỗ trợ restart và writer idempotent.
7. Sau khi `COMPLETED`, so exact 1.003 keys + amount sum, không duplicate.

Nếu thử `JdbcBatchWriter` chỉ với `ListItemReader` tạo một lần rồi dùng lại cho nhiều runs, bạn có thể test nhầm do reader bị tiêu thụ; dùng `@StepScope`/`ItemStream` reader đúng lifecycle hoặc khởi tạo reader mới theo từng attempt trong fixture.

### 19.3. Fault injection trước và sau COMMIT

| Mốc | Có rollback được? | Test oracle |
|---|---|---|
| Writer vừa `addBatch` nhưng chưa `executeBatch` | Có theo transaction; chưa nhất thiết có SQL | No committed output |
| `executeBatch` đã chạy, trước COMMIT | Có nếu cùng physical transaction và rollback thành công | No rows của chunk lỗi |
| PostgreSQL COMMIT đang thực hiện, kết nối bị mất | **Unknown outcome** có thể xảy ra | Reconcile business key trước replay |
| Business COMMIT đã xác nhận, trước StepExecution metadata | Không “undo” business commit bằng exception Java | Idempotent restart/reconciliation |
| Reply/ACK mất sau business COMMIT | Business output có thể đã có | Không đếm duplicate effect khi redelivery |

**Không gộp “failure sau batchUpdate” và “failure sau commit” thành một testcase.** Lỗi gần ranh giới COMMIT là nơi phải kiểm tra transaction outcome, không đoán theo stack trace.

## 20. Benchmark concurrency mà không tạo kết quả sai

Thử 1/2/4/8/16 worker slots chỉ có ý nghĩa khi:

- Input snapshot và số business keys giống nhau giữa runs.
- Writer SQL/indexes/constraints không bị đổi ngoài biến đang test.
- Partition plans có coverage nửa mở `[from,to)`, không overlap, sort key ổn định.
- Mỗi worker reader/transaction state tách biệt.
- Có **ít nhất hai workers thực sự chạy overlap** nếu muốn đo distributed concurrency.
- Output sau mỗi run đối soát exact unique keys/payload/aggregate.
- Không dùng tổng `writeCount` qua retry như business committed count.

### 20.1. Range partition fixture

Với `payment_id` từ 1 tới 100.003, bốn ranges:

~~~text
P0 [1, 25002)       25.001 IDs
P1 [25002, 50003)   25.001 IDs
P2 [50003, 75004)   25.001 IDs
P3 [75004, 100004)  25.000 IDs
~~~

Reader SQL dùng `payment_id >= fromInclusive AND payment_id < toExclusive`. Nếu `<= toExclusive`, các boundary keys sẽ overlap; unique constraint có thể làm số rows cuối trông vẫn đúng nhưng **đọc/ghi duplicate attempts** và throughput benchmark bị lệch.

### 20.2. Worker-to-database budget

Một worker step đọc cursor giữ connection, writer tham gia một transaction trên another connection khi cần, metadata pool có thể khác:

| Metríc | Tại sao cần |
|---|---|
| Số worker pods + concurrent partitions/pod | Upper bound work active |
| Hikari business max per pod | Trần business connection theo pod |
| Reader cursor/statement lifetime | Connection giữ lâu làm pool pending |
| Transaction duration p95 | Lock và connection hold |
| PostgreSQL `max_connections`/other workloads | Budget toàn DB chứ không riêng job |
| JobRepository metadata pool | Additional connections khi nhiều partitions |
| Rolling deployment surge | Pod cũ và mới cùng mở pool |

Nếu PostgreSQL bị lock hoặc WAL I/O bão hòa, tăng JDBC batch size và worker count cùng lúc có thể **giảm unique committed throughput**. Tăng connection pool cũng không chắc có ích; đo root cause.

### 20.3. Partition skew và batch size

Nếu một partition chỉ có records nhỏ còn partition khác gồm documents lớn, cùng `chunk(500)` có **khác biệt lớn về bytes/chunk**. Tail partition có thể quyết định toàn bộ job wall-clock trong khi nhiều pods đã idle.

Phân tích:

- Rows, bytes và payload distributions theo partition.
- Mean/p95/max partition duration.
- DB lock/IO/CPU, GC theo worker instance.
- Slowest partition, retry/rollback count.
- Có cần điều chỉnh partition boundaries/weighting ở **job instance mới** không.

Không đổi partition names/ranges giữa một failed job restart rồi giả định old `ExecutionContext` checkpoints vẫn hợp lệ.

### 20.4. Tránh OOM ở remote chunking

Trong remote chunking, manager gửi một chunk payload qua broker. Nếu chunk 5.000 gồm mỗi Payment payload 64 KiB, raw payload đã khoảng **312,5 MiB**, chưa tính serialization, headers và bản sao memory. Message có thể vượt giới hạn broker/producer/consumer, bị retry hoặc tạo áp lực GC rất lớn.

Đừng dùng batch size từ local PostgreSQL writer làm message batch size mặc định cho distributed remote chunking. Cần đo broker message bytes, prefetch, in-flight count và contract retry/checkpoint riêng.

## 21. Ma trận kiểm thử batch insert size

Một thay đổi size đi vào production cần cả **performance tests** lẫn **correctness/recovery tests**. Không coi `JobExecution.COMPLETED` hay một số `rows/s` lớn là đủ.

| Test ID | Điều kiện | Expected outcome |
|---|---|---|
| BS-01 | `chunkSize=1`, 1 worker | Baseline và exact business keys |
| BS-02 | `chunkSize=50/100/250/500/1000` | Đo throughput, p95 latency, heap, retry, WAL |
| BS-03 | `chunkSize=250`, 100.003 input items | Chunk cuối lẻ không bỏ một item |
| BS-04 | Processor filter 30/500 items | Writer batch size theo actual output, không input count |
| BS-05 | `chunkSize=500`, JDBC batch B=100 | Nhiều JDBC calls nhưng một transaction chunk |
| BS-06 | JDBC batch call thứ năm throw trước COMMIT | Toàn bộ chunk writes rollback nếu cùng transaction |
| BS-07 | Chunk 1 commit, chunk 2 rollback | Chỉ chunk 1 output tồn tại |
| BS-08 | PostgreSQL unique constraint violation | Không partial committed rows của failed transaction |
| BS-09 | `ON CONFLICT DO NOTHING` replay | Không thêm duplicate business keys |
| BS-10 | Cùng business key nhưng khác payload | Phát hiện conflict sai dữ liệu theo policy |
| BS-11 | `reWriteBatchedInserts=false/true` | Hiệu quả đo được trên cùng SQL/schema, semantics đúng |
| BS-12 | Driver `RETURNING`/generated keys | Rewrite eligibility/counts được xác minh |
| BS-13 | Very wide JSONB records | Không OOM; throughput và chunk bytes hợp lý |
| BS-14 | Nhiều bind params/row | Tách batch đúng giới hạn driver/server |
| BS-15 | Hibernate IDENTITY vs SEQUENCE | Quan sát actual JDBC batching, không giả định |
| BS-16 | ORM flush rồi throw | Rollback transaction; không coi flush là commit |
| BS-17 | Deadlock `40P01`/serialization `40001` | Bounded retry toàn transaction, output idempotent |
| BS-18 | Process crash sau business COMMIT | Restart không double effect |
| BS-19 | Network mất khi COMMIT outcome unknown | Reconcile theo key và retry an toàn |
| BS-20 | Worker A rollback, worker B commit | Transaction independence, data vẫn đúng |
| BS-21 | 1/2/4/8/16 worker slots | Speedup/efficiency và DB saturation |
| BS-22 | Hot row cùng aggregate key | Lock waits không dẫn tới mất/double updates |
| BS-23 | Partition skew | Slowest partition/worker tail được đo |
| BS-24 | Remote partitioning broker duplicate request | Business output không duplicate |
| BS-25 | Remote chunking payload lớn | Không vượt message limits/in-flight budget |
| BS-26 | Hikari pool undersized | Có timeout/backpressure rõ, không mất dữ liệu |
| BS-27 | Pod churn/rolling deployment | Correctness/restart và connection surge budget |
| BS-28 | Target rỗng vs target đã tồn tại | Benchmark không trộn insert mới với replay no-op |
| BS-29 | Mixed success/skip/retry | `writeCount` khác committed new row count đúng semantics |
| BS-30 | Spring Batch `JobInstance` restart | Identifying params, checkpoint, partition plan ổn định |

### 21.1. Dữ liệu theo dõi mỗi run

Để so được giữa các lần chạy, ghi vào benchmark report:

~~~text
testRunId:
inputSnapshot:
inputRows / expectedKeys / expectedSum:
rowWidthDistribution:
schema/indexes/triggers:
springBatchVersion / pgjdbcVersion / postgresVersion:
chunkSize / jdbcBatchSize / rewriteBatchedInserts:
workerPods / concurrentPartitions / brokerPrefetch:
businessHikariMax / metadataHikariMax:
jobWallTime / timeToFirstChunk:
attemptedWriterRows / committedUniqueRows:
readCount / writeCount / commitCount / rollbackCount:
writerP95 / chunkP95 / transactionP95:
HikariPending / DBLockWait / WALBytes / CPU / GC:
exactKeySetMismatchCount:
~~~

**Không đưa thông tin nhạy cảm/raw production payload vào CI artifacts**. Với dữ liệu thực, chọn snapshot anonymized/reproducible hoặc synthetic theo đúng distribution.

### 21.2. Có thể kết luận “batch 500 tốt hơn 250” khi nào?

Chỉ khi:

- Cùng input, output state, SQL/index, hardware và workload competition.
- Kết quả được lặp đủ lần, không phải một run may mắn.
- Useful business throughput tăng **có ý nghĩa** so với variance.
- Writer/commit tail, memory, Hikari pending, WAL/locks không vượt SLO.
- Retry/rollback và idempotency tests đều PASS.
- Scale-out ở concurrency production vẫn có lợi, không chỉ test một worker.

Nếu thay đổi chỉ giúp worker throughput nhưng job wall-clock bị chậm bởi slowest partition, ưu tiên cân bằng workload/partition size thay vì tăng `B`.

## 22. Chọn size theo dạng workload

### 22.1. Input nhỏ, pipeline thiên CPU

Nếu mỗi item có processor mất 20 ms và insert chỉ mất 0,1 ms (số minh họa), writer batching không phải bottleneck. Tăng `chunkSize` có thể chỉ làm heap lớn và lỗi tốn công rollback. Thay vào đó đo CPU, allocation, GC, algorithm và thread safety trước.

### 22.2. Data hẹp, inserts append-only

Nếu rows hẹp, index ít và DB còn dư WAL/IO:

- `JdbcBatchItemWriter` + chunk trung bình là baseline tốt.
- Benchmark pgjdbc rewrite theo SQL thực.
- Với volume lớn, thử `COPY`/staging khi business constraints/restart cho phép.
- Đừng bỏ unique keys nếu output cần idempotency.

### 22.3. Heavy UPSERT/ON CONFLICT

Nếu phần lớn rows đã có hoặc cần `DO UPDATE`:

- Unique-index lookup, row locks và update writes có thể chiếm chi phí chính.
- Driver rewrite có thể không tạo lợi ích như append-only.
- Chunk lớn kéo dài lock ownership.
- Nếu cùng business key xuất hiện ở nhiều partitions, cần ownership/aggregation design, không chỉ tăng `B`.
- Business update phải idempotent khi broker redelivery/restart.

### 22.4. Wide JSONB, BLOB hoặc large entity graph

Nếu payload lớn:

- Dùng **bytes/chunk** như một ngưỡng bảo vệ, không chỉ item count.
- Giảm `C`/`B` nếu heap, network packet hoặc DB memory bão hòa.
- Với JPA, persistence context/dirty-checking có thể gây memory pressure lớn.
- Xem streaming/`COPY` hoặc staging tùy DB và business contract.

### 22.5. Workload ghi vào nhiều tables

Một item có thể cần insert vào parent, child, audit và outbox. Nếu transaction cần đảm bảo tất cả hoặc không:

- Giữ operations cùng transaction/business manager.
- JDBC batch theo table có thể cần ordering để tôn trọng FK.
- Batch writer “one JDBC batch 500 rows” không tự tồn tại nếu mỗi item có nhiều statements/tables.
- Hibernate `order_inserts` có thể giúp nhóm SQL nhưng phải test constraints/flush behavior.
- Rollback và retry phải an toàn nếu một table ghi thành công trước khi table khác lỗi.

### 22.6. Cấu hình phải có default và giới hạn

Ví dụ application-specific:

~~~yaml
app:
  insert:
    chunk-size: 250
    jdbc-batch-size: 100
    max-workers-per-pod: 4
~~~

Đây là **custom application properties**, không phải Spring Batch tự áp dụng. Code `StepBuilder.chunk(...)` phải đọc `app.insert.chunk-size` qua `@Value`/`@ConfigurationProperties`, validate `>0` và chọn giới hạn hợp lý. Đừng để người vận hành đặt `chunkSize=-1` hay 1.000.000 qua environment variable mà không có validation.

**Thay đổi size phải tạo execution/JobInstance tương thích:** không tự ý thay chunk size giữa restart của job đang fail mà chưa kiểm tra reader state, checkpoint, repeatability và writer idempotency. Một thay đổi tuning có thể cần áp dụng cho **job instance mới**, không được đánh đồng với hot reload an toàn.

## 23. Rollout cấu hình theo từng bước

Không nên bật chunk size mới trên toàn bộ workers và trộn cùng thay đổi schema/driver/SQL. Một quy trình có kiểm soát:

1. **Baseline:** chụp snapshot configuration, metrics, throughput và output oracle.
2. **Staging:** thử size candidates trên target state tương đương, cold/warm được ghi rõ.
3. **Fault tests:** rollback-before-commit, crash-after-commit, replay và restart.
4. **Load/stress:** tăng workers tới production concurrency, quan sát DB lock/WAL/pool.
5. **Canary:** áp cấu hình mới cho một tập job instances/worker deployment có scope rõ.
6. **Compare:** cùng input/workload class, unique business outcomes/s, wall-clock, error rate, tail latency và DB saturation.
7. **Rollback config:** nếu regression, trả về size cũ cho **job mới**; giữ nhất quán với jobs đang chạy/khả năng restart.
8. **Document:** ghi quyết định, giả định, driver versions, DBA limits và threshold cần alert.

### 23.1. Cảnh báo rolling deployment

Nếu scale từ 4 lên 8 pods trong lúc rollout, có thể tạm xuất hiện pod cũ và mới cùng chạy, mở nhiều connection pools và xử lý partitions với các batch sizes khác nhau. Cần:

- Tính **surge** trong total Hikari connections.
- Bảo đảm tương thích schema/message converters.
- Giữ `JobRepository` và partition plan consistent.
- Drain worker cũ hoặc bảo vệ stale worker effects.
- Ghi configuration version theo `JobExecution`/worker instance để điều tra.

Không cắt phiên làm việc JDBC giữa chunk commit chỉ để thay `B`; dùng lifecycle shutdown/stop/restart có kiểm soát.

### 23.2. Khi nào revert?

Nên rollback canary nếu có một trong các dấu hiệu:

- Output mismatch hoặc duplicate business effect.
- Job failure/retry tăng rõ sau thay đổi.
- Chunk/commit p95/p99 vượt SLO.
- PostgreSQL lock/WAL/IO hoặc Hikari pending bão hòa kéo dài.
- Heap/GC hoặc OOM risk vượt ngân sách.
- Job wall-clock không cải thiện dù writer rate tăng.
- Broker queue age/consumer timeouts tăng do chunks/messages quá lớn.

**Correctness regression là blocker**, không đánh đổi với vài phần trăm throughput.

## 24. Runbook: batch insert size lớn làm throughput giảm

Giả sử nhóm vận hành thay `chunkSize=250` thành `2_000`, rồi thấy:

~~~text
writer-attempts/s:         45k -> 66k
new-unique-business/s:     39k -> 31k
Hikari pending:             0  -> 28
DB Lock waits:             tăng mạnh
chunk p95:                 80ms -> 920ms
rollback/retry rate:       tăng 3x
job wall-clock:            18m -> 25m
~~~

Đây **không** phải tối ưu thành công chỉ vì writer attempts tăng. Rất có thể system đang làm lại work, giữ transactions/locks lâu hơn, tranh connection và giảm **kết quả có ích đã commit**.

### Bước 1 — Xác minh size nào thực sự thay đổi

Kiểm tra:

- `chunkSize` ở `StepBuilder.chunk(...)`.
- `jdbcBatchSize` ở custom writer hoặc Hibernate.
- PostgreSQL `reWriteBatchedInserts` trên **đúng business datasource**.
- Row width và SQL `INSERT/UPSERT/RETURNING`.
- Số worker/partitions active, broker prefetch và Hikari pool.

Đừng gọi một environment variable là “batch size” nếu code không đọc nó. Kiểm tra configuration version và các pods cũ/mới còn sống trong rolling deploy.

### Bước 2 — Chốt numerator và denominator

Dashboard đang hiển thị writer **attempted** items/s, `StepExecution.writeCount/s` hay **new unique committed business keys/s**? Có retry, filter, skip hoặc `ON CONFLICT DO NOTHING` không? Đo trên cùng snapshot và cùng cửa sổ thời gian, đừng cộng các worker peaks khác lúc.

### Bước 3 — Xác nhận input/output chính xác

So expected unique keys/amount/checksum bằng output SQL; nếu mismatch, dừng rollout và điều tra data integrity. Không “sửa” bằng cách tăng chunk size lớn hơn hoặc skip thêm item để job `COMPLETED`.

### Bước 4 — Tìm transaction boundary và commit cost

Xác định `businessTransactionManager`, connection, pool và `ItemWriter`. Có writer mở `REQUIRES_NEW`/auto-commit không? SQL `executeBatch` khác `COMMIT`; nếu transaction bị rollback, các SQL trong transaction không được tính thành output mới. Nếu commit outcome unknown, đối soát trước khi retry.

### Bước 5 — Phân tích database

Đọc `pg_stat_activity`, `pg_blocking_pids`, WAL rates, disk latency, CPU, indexes, triggers, `pg_stat_statements` nếu sẵn có. Nếu lock waits/transaction age tăng khi size lớn:

- Giảm chunk size/concurrency cho **work mới**.
- Tìm hot update key hoặc foreign key/index contention.
- Tối ưu transaction duration/SQL plan.
- Tránh tăng connection pool chỉ để có thêm threads chờ cùng một lock.

### Bước 6 — Phân tích memory/JVM

Kiểm tra heap allocation, GC pause, RSS/pod memory và payload bytes per item. Nếu chunk lớn giữ hàng nghìn entity graphs/JSONB, giảm chunk/JDBC batch size hoặc dùng streaming/staging có contract đúng. Không chọn size theo item count khi row widths biến thiên lớn.

### Bước 7 — Phân tích reader/broker/metadata

Nếu worker writer không phải nút thắt:

- Reader `fetchSize`, SQL `EXPLAIN`, input network/I/O.
- JobRepository write latency, partition count/manager aggregation.
- Broker queue age, ready/unacked messages, prefetch, serialization bytes.
- CPU-bound processor, GC hoặc external API.

Nếu node chỉ có một partition tail chậm, điều chỉnh `Partitioner`/workload balance ở **job mới** có thể tốt hơn thay batch size.

### Bước 8 — Giảm tải an toàn và bảo vệ retry

Giảm số worker mới/manager dispatch hoặc consumer concurrency theo backpressure policy. Đặt bounded retries/backoff/jitter với `40P01`/`40001`. Không giết hàng loạt worker ở giữa chunk commit chỉ để thử “có nhanh hơn không”, vì có thể tạo thêm unknown commit outcomes/replays.

### Bước 9 — Quay về cấu hình tốt đã kiểm chứng

Đối với **JobInstance mới**, đưa `chunkSize/JDBC batch size/driver flag` về giá trị baseline đã benchmark. Với job `FAILED` đang restart, kiểm tra checkpoint, input snapshot, partition names, chunk semantics và writer idempotency trước khi thay bất kỳ knob nào.

### Bước 10 — Benchmark lại và bổ sung regression

Chạy lại fixture tương đương, ghi **useful throughput, job wall-clock, p95/p99, WAL/locks, Hikari pending, retries, output oracle**. Thêm testcase đúng failure boundary đã phát hiện, không chỉ tăng timeout rồi kết luận vấn đề đã hết.

## 25. Anti-patterns khi tuning batch insert size

| Anti-pattern | Vì sao nguy hiểm | Cách làm đúng |
|---|---|---|
| “Càng nhiều rows/batch càng nhanh” | Memory, locks, WAL, rollback cost tăng | Benchmark các size với SLO/DB pressure |
| Nhầm `chunkSize` với `hibernate.jdbc.batch_size` | Hai tầng khác nhau | Tách transaction granularity khỏi ORM/JDBC batches |
| Chỉ thay `fetchSize` để tối ưu insert | Reader knob không phải writer knob | Đo reader/write/commit riêng |
| Ghi từng row qua `JdbcTemplate.update()` nhưng gọi là JDBC batching | Nhiều SQL calls/round trips | `JdbcBatchItemWriter` hoặc `batchUpdate` |
| Tự buffer items qua nhiều committed chunks | Checkpoint có thể đi trước data flush | Giữ write trong transaction hoặc thiết kế staging/outbox |
| `ON CONFLICT DO NOTHING` rồi gọi `writeCount` = new rows | Duplicate no-op và update-count semantics | Business unique count/checksum |
| Chạy benchmark lần 2 trên target đã đầy | Đo no-op, không phải new inserts | Reset/reseed target state tương đương |
| Bật `reWriteBatchedInserts` và giả định mọi SQL được rewrite | SQL/driver/version có restrictions | Inspect actual SQL và benchmark on/off |
| Build multi-row INSERT không giới hạn bind count | Vượt PostgreSQL/driver limits | Split theo params/payload capacity |
| Dùng Hibernate `IDENTITY` mà mặc định batching luôn hoạt động | ID generation có thể cản batch | Kiểm tra ORM SQL statistics |
| Bỏ primary/unique index để tăng throughput | Có thể phá idempotency | Giữ correctness constraints |
| Thêm duplicate index “để đọc nhanh” | Tăng insert/WAL overhead | Dùng EXPLAIN và index inventory |
| Đếm `BatchUpdateException.updateCounts` thành committed rows | SQL execution không phải commit | Read output sau transaction kết thúc |
| `EntityManager.flush` được coi là COMMIT | Flush có thể rollback | Test physical transaction boundary |
| Writer dùng datasource ngoài chunk transaction | Rollback không hoàn tác output | Wiring đúng manager + rollback test |
| `REQUIRES_NEW` để “tránh rollback” với mọi insert | Inner commit còn sau outer rollback | Chỉ dùng nếu business semantics cố ý |
| Benchmark một worker rồi áp ngay 16 workers | Shared DB bão hòa/locks | Load test concurrency production |
| Tăng Hikari pool khi DB đã lock-bound | Nhiều connection đợi hơn | Tìm blocker, giảm contention |
| Chỉ đo peak writer attempts/s | Retry có thể tạo số ảo | Unique business outcome và wall-clock |
| Đưa `paymentId` vào metric labels | Cardinality cao | Low-cardinality tags + logs |
| Retry vô hạn batch lỗi | Retry storm và duplicate side effects | Bounded retry/backoff/idempotency |
| Thay `run.id` khi restart | Tạo JobInstance khác, bỏ checkpoint | Same identifying parameters |
| Đổi partition plan giữa restart | Work ownership/checkpoint lệch | Stable plan hoặc migration riêng |
| Test chunk lớn bằng H2 để khẳng định PostgreSQL behavior | Transaction/SQL/locks khác nhau | Real PostgreSQL Testcontainers |
| Trả “COMPLETED” chỉ từ manager reply | Reply khác business commit | Shared repository + business reconciliation |

## 26. Checklist trước khi quyết định batch insert size

- [ ] Đã phân biệt `chunkSize`, JDBC batch size, Hibernate batching, multi-row SQL và remote message batch size.
- [ ] Đã xác định goal: throughput hữu ích, wall-clock SLA, resource budget, rollback/restart.
- [ ] Input snapshot bất biến và output target state có thể tái lập.
- [ ] Reader có stable sort key, non-overlap partition ranges và checkpoint phù hợp.
- [ ] `JdbcBatchItemWriter`/custom writer trỏ **đúng business datasource**.
- [ ] Chunk step dùng transaction manager bao phủ SQL writer.
- [ ] Đã test SQL executed rồi throw trước COMMIT, output chunk rollback đúng.
- [ ] Chunk trước đã commit không bị kỳ vọng rollback khi chunk sau fail.
- [ ] Nếu tách `jdbcBatchSize < chunkSize`, vẫn giữ cùng transaction boundary.
- [ ] Không giữ custom writer buffer qua nhiều chunk commits mà chưa có recovery design.
- [ ] `ON CONFLICT DO NOTHING` có rule cho duplicate key **khác payload**.
- [ ] Nếu có external API/broker/file writes, đã thiết kế outbox/idempotency/compensation khi cần.
- [ ] Không dùng `writeCount` hoặc JDBC update counts làm business committed-row oracle.
- [ ] Có exact key set/checksum/totals sau mỗi benchmark/restart.
- [ ] `reWriteBatchedInserts` được cấu hình trên **đúng pool** và SQL thực đã được kiểm tra.
- [ ] Có test rewrite true/false trên cùng driver/database/SQL.
- [ ] Batch bind parameter count và payload bytes ở dưới giới hạn thực tế.
- [ ] Nếu dùng Hibernate, đã kiểm tra `jdbc.batch_size`, `order_inserts`, entity ID strategy và actual SQL.
- [ ] Đã đo heap, GC và row-width distribution ở chunk size dự kiến.
- [ ] Đã đo Hikari active/idle/pending/acquire p95.
- [ ] Đã đo PostgreSQL lock waits, WAL, index/triggers, I/O và CPU.
- [ ] Không thêm duplicate indexes khi primary key index đã đủ.
- [ ] Benchmark giữ riêng chunk size, JDBC batch size và worker concurrency theo từng phase.
- [ ] Có nhiều runs, median/variance, warm-up và thứ tự cấu hình được kiểm soát.
- [ ] Đã thử 1/2/4/8/16 worker slots trên workload thực tế.
- [ ] Có slowest partition/max duration để phát hiện skew/tail.
- [ ] Với remote chunking, đã kiểm tra message bytes, broker limits và redelivery.
- [ ] Retry/skip policy có max attempts/backoff và tests trên PostgreSQL thật.
- [ ] Đã thử worker crash trước/sau commit và restart cùng JobInstance.
- [ ] Không đổi chunk size/partition plan giữa restart khi chưa kiểm tra compatibility.
- [ ] Canary/rolling deploy có ngân sách connection surge và worker draining.
- [ ] Có rollback config/runbook nếu throughput giảm hoặc data mismatch.
- [ ] Có dashboard useful rows/s, job wall-clock, p95/p99, retries và DB pressure.
- [ ] Chỉ chọn size sau khi cả performance lẫn data correctness đều đạt.

## 27. Bài tập thực hành

### Bài tập 1 — Phân biệt C và B

Một worker sử dụng `chunkSize=600`, custom writer chia mỗi JDBC batch tối đa 125 items và có 1.330 items hợp lệ cần ghi.

1. Tính số chunks lý thuyết (không filter/skip/retry).
2. Tính số JDBC batch calls trong từng chunk (gồm chunk cuối).
3. Nếu call thứ tư của chunk đầu throw trước COMMIT, các calls trước của **cùng chunk** có giữ rows trong business DB không?
4. Nếu chunk đầu đã COMMIT rồi chunk thứ hai fail, output của chunk đầu còn không?

**Gợi ý:** nhớ phân biệt số `executeBatch` calls và số transaction commits. Chia JDBC calls bên trong chunk không tự đổi transaction boundary.

### Bài tập 2 — Benchmark chunk size

Seed 100.003 Payments theo phần 4. Chạy cùng một worker với `chunkSize=1/50/100/250/500/1000`:

- Reset/reseed target staging trước mỗi run.
- Giữ DDL, driver, Hikari và resource budget cố định.
- Đo job wall-clock, throughput unique business keys/s, chunk p95 và PostgreSQL WAL/locks.
- Chạy ít nhất ba rounds với thứ tự size khác nhau.
- Chọn size dựa trên SLO và variance chứ không chỉ lần nhanh nhất.

Giải thích tại sao lượt chạy thứ hai trên output đã có đầy đủ với `DO NOTHING` sẽ cho kết quả sai lệch so với lần insert mới.

### Bài tập 3 — Giữ chunk size, tách JDBC batch size

Dùng `chunk(500)` và custom writer `JdbcTemplate.batchUpdate(sql, items, batchSize, setter)`. Thử `B=25/50/100/250/500` trên cùng input/target state. Đọc `int[][]` returned counts để hiểu driver behavior nhưng **không** dùng counts ấy làm bằng chứng commit; sau khi job hoàn tất, query unique business rows.

### Bài tập 4 — Test rollback nhiều JDBC calls

Lấy `SplitJdbcBatchRollbackIT` ở phần 19. Thay `batchSize=2` bằng 1, 3, 4; giữ transaction chứa bốn records, inject exception **sau batchUpdate trước COMMIT**. Với mọi size, output expected sau rollback là **0 rows**. Sau đó bỏ exception, output expected là **4 rows**.

Điều gì xảy ra nếu `JdbcTemplate` trỏ sai datasource và connection tự auto-commit? Thiết kế một negative test trong test database để phát hiện.

### Bài tập 5 — Driver rewrite

Trên PostgreSQL/pgjdbc thực, tạo hai pool configurations khác nhau chỉ ở `reWriteBatchedInserts`. So:

1. Simple parameterized `INSERT`.
2. `INSERT ... ON CONFLICT DO NOTHING`.
3. Insert cần returned generated keys/`RETURNING`.

Ghi SQL behavior thực tế, execution time, update counts, memory và output correctness. Giải thích vì sao không thể tuyên bố rewrite luôn có ích hoặc luôn áp dụng chỉ từ config flag.

### Bài tập 6 — Giới hạn bind parameters

Một câu multi-row insert do ứng dụng tự tạo có 12 placeholders/row. Với giới hạn thực tế đã được xác nhận là 65.535 binds/statement ở driver/protocol đang dùng, tính **số rows tối đa theo riêng ràng buộc bind count**:

\[
\left\lfloor \frac{65535}{12}\right\rfloor.
\]

Sau đó thiết kế giới hạn **thấp hơn theo payload bytes, memory và transaction latency**. Không giả định kết quả toán học là size vận hành tối ưu.

### Bài tập 7 — JPA ID strategy

Tạo entity `PaymentEntity` được insert bằng JPA. Benchmark `hibernate.jdbc.batch_size=50` với ID strategy `IDENTITY` và một strategy sequence allocation được dự án hỗ trợ. Đọc Hibernate/JDBC statistics và SQL actual batches. Giải thích vì sao `chunk(500)` không chứng minh Hibernate sẽ gửi đúng 500 rows trong một JDBC batch.

### Bài tập 8 — Row width và memory

Tạo hai fixtures, cùng 100.000 items:

- A: mỗi Payment payload nhỏ (cỡ vài trăm bytes).
- B: mỗi record mang JSONB hoặc document cỡ 64 KiB.

So `chunkSize=100/500/2000` với cùng worker/memory limit. Đo heap/GC/RSS, writer p95, DB WAL/IO và OOM risk. Thiết kế **max bytes per chunk** hoặc split writer strategy khi row widths biến động lớn.

### Bài tập 9 — Thêm worker có còn lợi?

Chạy cùng snapshot với 1/2/4/8/16 workers ở cấu hình chunk 250. Tính speedup và efficiency từ job wall-clock. Khi Hikari pending/DB lock waits tăng mà unique throughput giảm, lựa chọn số worker/batch size mới; không tự tăng connection pool rồi coi là giải pháp.

### Bài tập 10 — Partition tail

Tạo bốn partitions, ba partition mỗi cái 25.000 narrow rows, partition thứ tư có 25.000 wide rows/hot keys. Đo max partition duration, worker utilization và job wall-clock với cùng `chunkSize`. Đề xuất partition weighting cho **job instance mới**; giải thích vì sao không được đổi partition map khi restart một instance lỗi.

### Bài tập 11 — Replay idempotent

Chạy writer với 1.003 payments rồi mô phỏng retry chunk đã commit vì worker mất reply. `ON CONFLICT DO NOTHING` giữ unique keys không đổi; đo khác biệt giữa writer attempts, `writeCount` và affected new rows. Sau đó thay amount của một payment nhưng giữ cùng `payment_id` và thiết kế policy phát hiện **duplicate sai payload** thay vì âm thầm cho qua.

### Bài tập 12 — Failure giữa JDBC batch

Tạo một unique constraint violation tại item thứ 125 trong một chunk 250. So:

- Fail-fast: chunk rollback, job `FAILED`, không có partial committed rows của chunk.
- Fault-tolerant skip: framework xử lý retry/scan/skip theo policy, commit valid items đúng một lần.

Xác nhận `read/write/skip/rollback counts`, exact key set và không gửi side effects ngoài transaction khi writer được replay.

### Bài tập 13 — Remote chunking message size

Một message có 1.000 items, mỗi item trung bình 100 KiB trước serialization. Ước tính raw payload MiB; khảo sát broker message/frame/prefetch limits và memory copying overhead. Thiết kế chunk size an toàn, retry/ACK/correlation strategy và test mất reply sau business commit.

### Bài tập 14 — So JDBC batches với PostgreSQL COPY

Trên staging, nhập 5 triệu append-only records theo hai phương án:

1. `JdbcBatchItemWriter`/custom `batchUpdate` với index/business constraints giữ nguyên.
2. PostgreSQL `COPY` vào staging, validate, rồi merge sang final table.

Ghi total wall time, DB/WAL/IO, disk footprint, idempotency/restart steps, data integrity và operational complexity. Không tuyên bố `COPY` tốt hơn cho mọi workload nếu staging merge trở thành nút thắt hoặc semantics khác.

### Bài tập 15 — Runbook sự cố

Một hệ thống thay đổi từ `chunkSize=250` sang 5.000 và scale từ 4 lên 16 workers cùng lúc. Sau rollout:

~~~text
Hikari pending:      0 -> 44
DB Lock waits:       tăng
WAL write latency:   tăng
writer attempts/s:   1.8x
business rows/s:     giảm 25%
job wall-clock:      tăng
rollback count:      tăng
~~~

Viết thứ tự điều tra để xác định:

- Có phải batch size gây lỗi, worker count gây lỗi hay cả hai?
- Transaction manager và writer SQL thực dùng là gì?
- Có duplicate/retry/`DO NOTHING` làm attempted rate “ảo” không?
- Nên giảm concurrency, chunk size, tối ưu hot key/index hay tăng pool?
- Làm thế nào rollback canary và giữ restart correctness?

Đề xuất một ma trận benchmark lần sau chỉ thay đổi **một biến mỗi phase**.

### Bài tập 16 — Thiết kế production guardrails

Xây `@ConfigurationProperties` cho `chunk-size` và `jdbc-batch-size`, validate `min=1` và giá trị max dựa trên row-width/DB budget của dự án. Ghi configuration version vào log/trace của worker. Mô phỏng config invalid, pod rolling deployment, worker stale request và restart một job `FAILED`. Xác minh application reject config sai **trước khi launch job** và không khiến logic partition/checkpoint thay đổi âm thầm.

### Câu hỏi tự kiểm tra

- Chunk size và JDBC batch size có thể khác nhau không?
- `JdbcBatchItemWriter` thông thường gom items theo đơn vị nào?
- Tại sao `JdbcTemplate.batchUpdate()` thành công chưa phải commit?
- Nếu chia chunk 500 thành năm JDBC batch calls 100 items, một call lỗi có thể khiến cả 500 items rollback không?
- `hibernate.jdbc.batch_size` liên quan thế nào tới `GenerationType.IDENTITY`?
- Tại sao `reWriteBatchedInserts=true` không tự chứng minh SQL đã được rewrite?
- Bind parameter count và row width ảnh hưởng gì tới batch size?
- Vì sao database có 100.003 rows ở run đầu khiến run thứ hai dùng `ON CONFLICT DO NOTHING` không phải benchmark tương đương?
- Vì sao không thể dùng `StepExecution.writeCount` làm số row mới của PostgreSQL?
- Khi nhiều worker chạy đồng thời, tại sao size tối ưu của một worker có thể trở nên tệ?
- Vì sao `COPY` cần thiết kế staging/restart riêng?
- Cần những phép thử nào trước khi đổi chunk size của một job đã fail và cần restart?
- Nếu p95 commit latency vượt SLO nhưng throughput tăng chút ít, nên quyết định thế nào?

## 28. Tổng kết

**Điều chỉnh batch insert size** là tối ưu một chuỗi ranh giới: **reader fetch, Spring Batch chunk transaction, JDBC/Hibernate batching, PostgreSQL execution/commit và độ đồng thời của workers**. Các kích thước này **không đồng nghĩa**, cũng không tự tăng cùng nhau khi thay `chunkSize`.

Một quy trình đáng tin cậy là:

1. **Định nghĩa lại “nhanh”** bằng unique valid committed business rows/s, job wall-clock, tail latency và ngân sách tài nguyên.
2. **Giữ dữ liệu/DDL tương đương**, đo baseline và thay lần lượt `chunkSize`, JDBC `batchSize`, driver rewrite rồi mới tăng workers.
3. **Kiểm tra transaction boundary** bằng test PostgreSQL: các JDBC batches nằm trong một chunk phải rollback cùng nhau nếu cùng physical transaction.
4. **Theo dõi toàn pipeline:** heap/GC, writer latency, commit/WAL/locks, Hikari pending, broker/JobRepository và partition tail.
5. **Bảo vệ correctness:** business unique keys/checksum, retry/skip, idempotency, checkpoint, restart cùng `JobInstance` và xử lý commit outcome unknown.
6. **Triển khai có kiểm soát:** staging, load tests, canary, rollout, backpressure và runbook rollback cấu hình.

**Không có một giá trị batch insert size tối ưu cho mọi workload.** Giá trị tốt nhất là giá trị đã được benchmark trên hệ thống thật, đạt throughput hữu ích cao trong giới hạn memory/database/latency, và vẫn tạo kết quả nghiệp vụ chính xác sau rollback, retry hoặc restart.
