# Partition theo range thời gian trong Spring Batch

## 1. Tại sao chia dữ liệu theo thời gian?

Một hệ thống thanh toán nhận hàng chục triệu sự kiện mỗi ngày. Job đối soát phải đọc sự kiện trong khoảng từ 00:00 ngày hôm trước đến 00:00 ngày hôm nay, tính toán rồi lưu kết quả. Nếu một reader quét toàn bộ khoảng thời gian ấy trên một worker, thời gian hoàn tất bị giới hạn bởi khả năng đọc, xử lý và ghi của một execution.

Khi dữ liệu có trường thời gian đáng tin cậy như `event_time`, `created_at` hoặc `ingested_at`, ta có thể chia workload thành **các cửa sổ thời gian không giao nhau**, ví dụ bốn khoảng sáu giờ. Mỗi cửa sổ được giao cho một `StepExecution`, đọc và checkpoint độc lập. Đây là **partition theo range thời gian** ở tầng Spring Batch.

~~~text
Job input: [2026-11-25T00:00Z, 2026-11-26T00:00Z)

partition0: [00:00Z, 06:00Z)
partition1: [06:00Z, 12:00Z)
partition2: [12:00Z, 18:00Z)
partition3: [18:00Z, 00:00Z ngày tiếp theo)
~~~

Bài **“Partition theo range thời gian”** thuộc chương **Database scaling** của module `SPRING_BATCH_SCALING_OPERATIONS`. Mục tiêu module là mở rộng Spring Batch cho dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và chọn kiến trúc phù hợp tài nguyên.

Sau bài học, bạn có thể:

- Thiết kế các khoảng **nửa mở** `[fromInclusive, toExclusive)` để không đọc trùng hay bỏ sót sự kiện ở ranh giới.
- Viết `Partitioner` tạo `ExecutionContext` theo cửa sổ thời gian và reader `@StepScope` nhận đúng khoảng được giao.
- Xử lý `Instant`, UTC, múi giờ địa phương và ngày có chuyển giờ mùa hè (DST).
- Phân biệt partition **logic của Spring Batch** với partition **vật lý của database**.
- Thiết kế snapshot, cutoff/watermark, xử lý late-arriving data và restart nhất quán.
- Tối ưu SQL/index, chọn độ rộng cửa sổ theo phân bố dữ liệu và đo bottleneck trước khi tăng worker.

Các ví dụ Java chính sử dụng **Java 17+, Spring Batch 5.2.x** và PostgreSQL; khi dùng Spring Batch 6.x, cần đối chiếu import và API builder theo phiên bản. Ví dụ cấu hình được ghi rõ những nơi cần bổ sung bean hoặc tích hợp.

## 2. Quy tắc quan trọng nhất: dùng khoảng nửa mở

Mỗi partition sở hữu khoảng:

\[
W_i=[t_i,t_{i+1})
\]

Nghĩa là nhận sự kiện có timestamp **lớn hơn hoặc bằng đầu khoảng**, đồng thời **nhỏ hơn cuối khoảng**:

~~~sql
WHERE event_time >= :fromInclusive
  AND event_time <  :toExclusive
~~~

Ví dụ một sự kiện có `event_time = 2026-11-25T06:00:00Z`:

- Không thuộc cửa sổ `[00:00Z, 06:00Z)`.
- Thuộc cửa sổ `[06:00Z, 12:00Z)`.

Nhờ đó, hai cửa sổ kề nhau **không giao nhau** và hợp của chúng phủ đúng khoảng tổng nếu có:

\[
t_0<t_1<\dots<t_n,\qquad
\bigcup_{i=0}^{n-1}[t_i,t_{i+1})=[t_0,t_n)
\]

### Vì sao không dùng BETWEEN?

~~~sql
-- Dễ gây xử lý trùng nếu hai khoảng kề nhau dùng cùng mốc:
WHERE event_time BETWEEN :startTime AND :endTime

-- An toàn về ranh giới:
WHERE event_time >= :startTime
  AND event_time < :endTime
~~~

Trong SQL, `BETWEEN` bao gồm **cả hai đầu mút**. Nếu partition A kết thúc 06:00 và partition B bắt đầu 06:00, sự kiện tại đúng 06:00 có thể được đọc **hai lần**.

Không nên sửa bằng cách lấy `endTime - 1 millisecond`: độ chính xác của timestamp trong PostgreSQL có thể tới microsecond, các database khác có kiểu/time precision khác, và ứng dụng có thể dùng nanosecond. **Đầu cuối loại trừ** là quy tắc đơn giản, nhất quán hơn.

### Điều kiện để không bỏ sót

Chỉ chia khoảng đúng chưa đủ. Phải chốt **thời điểm đầu và cuối của cả job**, nguồn dữ liệu không đổi bất ngờ khi đọc, mọi row cần xử lý đều có timestamp hợp lệ, và tất cả partition sử dụng cùng quy tắc múi giờ/kiểu dữ liệu.

## 3. Chọn cột thời gian nào để chia?

Không phải timestamp nào cũng là một khóa partition tốt.

| Cột | Ý nghĩa | Lợi ích | Rủi ro |
|---|---|---|---|
| `event_time` | Thời điểm nghiệp vụ xảy ra | Phù hợp báo cáo theo ngày/giờ nghiệp vụ | Event đến muộn hoặc bị sửa thời gian |
| `created_at` | Thời điểm row được tạo trong DB | Thường gần ổn định | Có thể khác thời gian sự kiện; import backfill có thời gian tạo mới |
| `ingested_at` | Thời điểm ingestion ghi nhận | Thuận lợi xây watermark và incremental ETL | Không trùng lịch nghiệp vụ của event |
| `updated_at` | Thời điểm cập nhật gần nhất | Phù hợp tác vụ đồng bộ thay đổi nếu có CDC/phiên bản | Dễ dịch chuyển giữa partition trong lúc xử lý |
| `business_date` | Ngày hạch toán | Thuận tiện kế toán theo ngày | Không mang thời gian chính xác, lệ thuộc timezone/calendar |

**Ưu tiên cột bất biến trong vòng đời một lần chạy.** Nếu worker vừa đọc row vừa cập nhật cột dùng làm điều kiện `WHERE`, những row còn lại có thể dịch chuyển khỏi tập kết quả, đặc biệt khi đọc bằng paging. Nếu nguồn dữ liệu có thể thay đổi, hãy chốt snapshot/version hoặc chuyển sang manifest bất biến.

Trong ví dụ xuyên suốt, `event_time` là thời gian sự kiện theo UTC và `snapshot_id` là định danh tập đầu vào được **đóng băng trước khi job chạy**. `id` là khóa chính duy nhất. Đây là giả định quan trọng: chỉ thêm điều kiện `snapshot_id` mà nguồn vẫn tiếp tục append/edit cùng ID **không** tự tạo snapshot bất biến.

## 4. Mô hình dữ liệu và chỉ mục PostgreSQL

Giả sử nguồn đã được chuẩn bị thành tập dữ liệu theo snapshot:

~~~sql
CREATE TABLE business_events (
    id          BIGINT PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    payload     TEXT NOT NULL
);

CREATE INDEX idx_business_events_snapshot_time_id
    ON business_events (snapshot_id, event_time, id);

CREATE TABLE processed_events (
    snapshot_id VARCHAR(64) NOT NULL,
    event_id    BIGINT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, event_id)
);
~~~

Chọn `TIMESTAMPTZ` để PostgreSQL so sánh theo **instant thực tế**; timezone hiển thị có thể khác nhau theo session nhưng giá trị được chuẩn hóa để so sánh. Ứng dụng truyền `Instant`/`OffsetDateTime` UTC vào prepared statement, không ghép chuỗi thời gian theo timezone của server.

Chỉ mục ghép `(snapshot_id, event_time, id)` phục vụ truy vấn lọc theo snapshot rồi quét dải thời gian và sắp thứ tự theo `event_time, id`. Thứ tự cột trong index là một giả thuyết cần **kiểm chứng với dữ liệu và query plan**: nếu workload thường lọc theo tenant, status hoặc có phân bố khác, chỉ mục phù hợp có thể khác.

### Truy vấn chuẩn cho worker

~~~sql
SELECT id, snapshot_id, event_time, payload
FROM business_events
WHERE snapshot_id = :snapshotId
  AND event_time >= :fromInclusive
  AND event_time <  :toExclusive
ORDER BY event_time ASC, id ASC;
~~~

`ORDER BY event_time, id` là **thứ tự tổng xác định** vì `id` duy nhất, ngay cả khi hàng nghìn sự kiện có cùng timestamp. Nếu chỉ `ORDER BY event_time`, các sự kiện trùng timestamp có thể được trả theo thứ tự khác nhau giữa những lần đọc, gây rủi ro cho các kỹ thuật paging/checkpoint dựa trên vị trí.

### Xem execution plan trước khi tăng số worker

Ví dụ với tham số đã được thay bằng literal khi kiểm tra thủ công:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, snapshot_id, event_time, payload
FROM business_events
WHERE snapshot_id = 'snap-2026-11-25-v1'
  AND event_time >= TIMESTAMPTZ '2026-11-25 06:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-11-25 12:00:00+00'
ORDER BY event_time, id;
~~~

`EXPLAIN ANALYZE` **thực thi truy vấn** và có thể tạo tải; nên chạy trên staging hoặc trong thời điểm an toàn. Quan sát index/seq scan, số row thực, buffer hit/read, sort spill, latency và sự khác biệt giữa cửa sổ ít/nhiều sự kiện. Một index scan không mặc nhiên nhanh hơn sequential scan khi range chứa phần rất lớn của bảng.

## 5. Kiến trúc partition theo thời gian của Spring Batch

~~~mermaid
flowchart TD
    J[JobParameters: fromUtc, toUtc, snapshotId] --> M[Manager partition step]
    M --> P[TimeWindowPartitioner]
    P --> A["window_00000: [00:00Z,06:00Z)"]
    P --> B["window_00001: [06:00Z,12:00Z)"]
    P --> C["window_00002: [12:00Z,18:00Z)"]
    P --> D["window_00003: [18:00Z,00:00Z hôm sau)"]
    A --> W1[Worker StepExecution A]
    B --> W2[Worker StepExecution B]
    C --> W3[Worker StepExecution C]
    D --> W4[Worker StepExecution D]
    W1 --> DB[(Indexed events DB)]
    W2 --> DB
    W3 --> DB
    W4 --> DB
    M <-->|Metadata| R[(JobRepository)]
    W1 --> R
    W2 --> R
    W3 --> R
    W4 --> R
~~~

Ba đối tượng có trách nhiệm khác nhau:

1. **`Partitioner`** chia thời gian và tạo `ExecutionContext` cho từng partition. Nó không cần giữ JDBC cursor hay xử lý record.
2. **Worker `Step`** là định nghĩa xử lý dùng lại cho mọi partition. Reader `@StepScope` lấy `fromInclusive/toExclusive` từ context của **chính `StepExecution`**.
3. **`PartitionHandler`** quyết định chạy worker executions tại đâu: thread trong JVM (local partitioning) hoặc qua middleware tới worker services (remote partitioning).

`gridSize` là gợi ý khi lập partition; nó **không tự tạo thread, pod hoặc connection**. Có thể có 48 partition nhưng chỉ 4 worker đang xử lý đồng thời.

## 6. Triển khai TimeWindowPartitioner

Sử dụng `Instant` để biểu diễn ranh giới trên timeline UTC; `Duration` cho độ rộng cửa sổ cố định (ví dụ 6 giờ). Đặt tên partition **xác định**, không phụ thuộc thread hoặc thời điểm worker bắt đầu.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class TimeWindowPartitioner implements Partitioner {
    private final Instant startInclusive;
    private final Instant endExclusive;
    private final Duration windowWidth;

    public TimeWindowPartitioner(
            Instant startInclusive,
            Instant endExclusive,
            Duration windowWidth) {

        if (startInclusive == null || endExclusive == null
                || !startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }
        if (windowWidth == null || windowWidth.isNegative()
                || windowWidth.isZero()) {
            throw new IllegalArgumentException("Window must be positive");
        }
        this.startInclusive = startInclusive;
        this.endExclusive = endExclusive;
        this.windowWidth = windowWidth;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        // gridSize điều khiển mức concurrency ở cấu hình handler;
        // với fixed-duration partition, số cửa sổ do khoảng thời gian quyết định.
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        Instant cursor = startInclusive;
        int index = 0;

        while (cursor.isBefore(endExclusive)) {
            if (index >= 10_000) {
                throw new IllegalStateException("Too many time windows");
            }
            Instant candidate = cursor.plus(windowWidth);
            Instant next = candidate.isAfter(endExclusive)
                    ? endExclusive : candidate;

            ExecutionContext context = new ExecutionContext();
            context.putString("fromInclusive", cursor.toString());
            context.putString("toExclusive", next.toString());

            String partitionName = String.format(
                    Locale.ROOT, "window_%05d", index);
            partitions.put(partitionName, context);
            cursor = next;
            index++;
        }
        return partitions;
    }
}
~~~

Ví dụ gọi:

~~~java
TimeWindowPartitioner p = new TimeWindowPartitioner(
        Instant.parse("2026-11-25T00:00:00Z"),
        Instant.parse("2026-11-26T00:00:00Z"),
        Duration.ofHours(6));

Map<String, ExecutionContext> plan = p.partition(4);
// Có 4 entry: window_00000 ... window_00003.
~~~

### Những lựa chọn có chủ đích trong ví dụ

- `Instant`/ISO-8601 UTC giúp tránh giải thích sai timestamp theo múi giờ mặc định của JVM.
- Class `TimeWindowPartitioner` không khai báo `final` vì phần cấu hình minh họa bên dưới dùng `@StepScope` với scoped proxy kiểu class; proxy cần có khả năng tạo subclass của target. Nếu chỉ sử dụng singleton partitioner với input cố định, ràng buộc proxy này không còn cần thiết.
- `[start,end)` bảo đảm mỗi mốc thời gian được gán tối đa một cửa sổ; cửa sổ cuối có thể ngắn hơn `windowWidth`.
- `String.format("window_%05d", index)` tạo tên partition ổn định nếu **cùng input, độ rộng và thuật toán** được giữ nguyên khi restart.
- Dùng `LinkedHashMap` giúp thứ tự tạo plan rõ ràng, **không** cam kết worker chạy theo thứ tự này.
- Giới hạn 10.000 cửa sổ là guard minh họa, không phải giới hạn của Spring Batch.
- `gridSize` không dùng để đổi thời lượng: một plan gồm N cửa sổ có thể được chạy bởi ít hơn N thread/worker.

**Lưu ý kỹ thuật:** `Instant.plus(Duration)` có thể ném exception nếu cộng vượt miền thời gian mà Java hỗ trợ; cần giới hạn job time range hợp lý ngay từ API/scheduler. Không truyền một job có thời lượng vô hạn hoặc khoảng 1 giây cho tập dữ liệu kéo dài nhiều thập kỷ.

### Cấp ranh giới từ JobParameters mà không hardcode

Trong ứng dụng thực tế, manager nhận `fromUtc`, `toUtc`, `snapshotId` từ `JobParameters`. Vì các tham số chỉ có khi job chạy, có thể tạo partitioner theo step scope:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

// Method thuộc class @Configuration của manager:
@Bean
@StepScope
public TimeWindowPartitioner timeWindowPartitioner(
        @Value("#{jobParameters['fromUtc']}") String fromUtc,
        @Value("#{jobParameters['toUtc']}") String toUtc) {

    if (fromUtc == null || toUtc == null) {
        throw new IllegalArgumentException("Missing time parameters");
    }
    return new TimeWindowPartitioner(
            Instant.parse(fromUtc),
            Instant.parse(toUtc),
            Duration.ofHours(6));
}
~~~

`snapshotId` được reader lấy trực tiếp từ job parameters; nó phải xác định một dataset đã được chốt. Khi khởi chạy job, nên dùng identifying parameters phù hợp để restart tham chiếu **cùng `JobInstance`**, tránh dùng `run.id` mới nếu mục tiêu là khôi phục execution bị lỗi.

## 7. Worker reader @StepScope theo range thời gian

`JdbcCursorItemReader` có trạng thái mutable: JDBC cursor, vị trí đọc và checkpoint. Không chia sẻ một instance singleton giữa nhiều partition. `@StepScope` tạo target reader riêng theo `StepExecution`; các dependency singleton như `DataSource` vẫn có thể chia sẻ theo contract thread-safe của pool.

### Một cấu hình reader cụ thể (Spring Batch 5.2.x)

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Event(
        long id,
        String snapshotId,
        Instant eventTime,
        String payload) {}

@Configuration
public class TimeWindowReaderConfiguration {
    @Bean
    @StepScope
    public JdbcCursorItemReader<Event> timeWindowEventReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['fromInclusive']}") String from,
            @Value("#{stepExecutionContext['toExclusive']}") String to) {

        if (snapshotId == null || snapshotId.isBlank()
                || from == null || to == null) {
            throw new IllegalArgumentException("Missing window context");
        }
        Instant fromInstant = Instant.parse(from);
        Instant toInstant = Instant.parse(to);
        if (!fromInstant.isBefore(toInstant)) {
            throw new IllegalArgumentException("Empty time window");
        }

        return new JdbcCursorItemReaderBuilder<Event>()
                .name("timeWindowEventReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, snapshot_id, event_time, payload
                    FROM business_events
                    WHERE snapshot_id = ?
                      AND event_time >= ?
                      AND event_time < ?
                    ORDER BY event_time, id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setObject(2, OffsetDateTime.ofInstant(
                            fromInstant, ZoneOffset.UTC));
                    ps.setObject(3, OffsetDateTime.ofInstant(
                            toInstant, ZoneOffset.UTC));
                })
                .rowMapper((rs, rowNum) -> new Event(
                        rs.getLong("id"),
                        rs.getString("snapshot_id"),
                        rs.getObject(
                                "event_time", OffsetDateTime.class).toInstant(),
                        rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

Với PostgreSQL JDBC driver hiện đại, `OffsetDateTime` là lựa chọn phù hợp cho `TIMESTAMPTZ`; cần kiểm thử binder và extraction với **driver/database thực tế**. Với database/driver khác, kiểu truyền tham số timestamp có thể cần điều chỉnh. Không chuyển một chuỗi thời gian local mơ hồ thành `java.sql.Timestamp` mà không xác định timezone.

**Kiểu trả về bean là `JdbcCursorItemReader<Event>`**, để lifecycle `ItemStream.open/update/close` được framework nhận diện qua scoped proxy. `.name("timeWindowEventReader")` giữ key checkpoint ổn định; nhiều partition dùng cùng tên reader vẫn có context khác nhau vì mỗi partition có `StepExecution` riêng.

### Một worker step và writer idempotent

Writer mẫu dùng PostgreSQL để mỗi `(snapshot_id,event_id)` được ghi tối đa một row:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TimeWindowWorkerConfiguration {
    @Bean
    public JdbcBatchItemWriter<Event> eventWriter(
            DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<Event>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO processed_events
                        (snapshot_id, event_id, payload)
                    VALUES (:snapshotId, :eventId, :payload)
                    ON CONFLICT (snapshot_id, event_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(e ->
                        new MapSqlParameterSource()
                                .addValue("snapshotId", e.snapshotId())
                                .addValue("eventId", e.id())
                                .addValue("payload", e.payload()))
                .assertUpdates(false)
                .build();
    }

    @Bean
    public Step eventWorkerStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<Event> timeWindowEventReader,
            JdbcBatchItemWriter<Event> eventWriter) {
        return new StepBuilder("eventWorkerStep", repository)
                .<Event, Event>chunk(250, transactionManager)
                .reader(timeWindowEventReader)
                .writer(eventWriter)
                .build();
    }
}
~~~

`Event` là record package-private đã định nghĩa trong ví dụ reader; khi chia thành nhiều file Java, đặt record ở package dùng chung (hoặc khai báo `public` trong tệp `Event.java` riêng) và import đúng. `assertUpdates(false)` cần thiết trong ví dụ vì `ON CONFLICT DO NOTHING` có thể cập nhật 0 row cho bản ghi đã tồn tại; nếu không, một số cấu hình writer mặc định kiểm tra row update count và có thể báo lỗi. **Không dùng `DO NOTHING` để che dữ liệu khác nhau dưới cùng business key**: nếu business logic cần cập nhật lại kết quả, phải thiết kế version/checksum/upsert được kiểm soát.

Nếu worker vừa ghi vào DB vừa gửi message ra broker hoặc gọi API, tính idempotent của phép insert này **không** làm side effect ngoài transaction tự động idempotent. Cần transactional outbox, idempotency key hoặc downstream dedupe.

### Manager step: mô hình wiring local partitioning

Với Spring Batch 5.2.x, cấu hình local partitioning có thể theo mẫu:

~~~java
// Trong class @Configuration của manager:
@Bean
public Step timeWindowManagerStep(
        JobRepository repository,
        TimeWindowPartitioner timeWindowPartitioner,
        Step eventWorkerStep,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("timeWindowManagerStep", repository)
            .partitioner("eventWorkerStep", timeWindowPartitioner)
            .step(eventWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Ví dụ trên **lược bỏ import và cấu hình `TaskExecutor`**; cần cấp executor có giới hạn thread/queue và các dependency theo project. Số partition thực do `TimeWindowPartitioner.partition(...)` trả về, còn executor giới hạn những partition thực thi đồng thời. Với remote partitioning, thay `PartitionHandler`/messaging để gửi mỗi `StepExecution` tới worker process; **hợp đồng cửa sổ thời gian và reader không thay đổi**.

## 8. Timezone, DST và ngày nghiệp vụ

Nếu job xử lý dữ liệu theo **UTC duration** (ví dụ mỗi 6 giờ trên timeline), `Instant` và `Duration.ofHours(6)` là lựa chọn thẳng. Nhưng nếu yêu cầu là “mỗi ngày nghiệp vụ theo giờ địa phương”, **không mặc định một ngày dài 24 giờ**.

### Đổi một ngày địa phương thành range UTC

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("America/New_York");
LocalDate businessDate = LocalDate.of(2026, 3, 8);

Instant fromUtc =
        businessDate.atStartOfDay(businessZone).toInstant();
Instant toUtc =
        businessDate.plusDays(1)
                .atStartOfDay(businessZone).toInstant();

long hours = Duration.between(fromUtc, toUtc).toHours();
// 23 giờ trong ngày chuyển sang daylight saving ở New York.
~~~

Vào ngày chuyển khỏi giờ mùa hè, một ngày địa phương có thể dài **25 giờ**. Dùng `localDate.atStartOfDay(zone)` và **ngày tiếp theo** để tính hai đầu UTC; không cộng cố định `Duration.ofDays(1)` nếu yêu cầu là ngày lịch theo vùng có DST.

Đối với Việt Nam, ví dụ `Asia/Ho_Chi_Minh` không dùng DST hiện hành, nhưng hệ thống đa quốc gia vẫn phải xét lịch sử timezone và chính sách timezone tương ứng. Tránh dùng `ZoneId.systemDefault()` vì mỗi pod có thể có cấu hình timezone khác nhau.

### Những lỗi chuyển thời gian phổ biến

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Dùng `LocalDateTime` không có zone làm cursor | Cùng chuỗi giờ có thể tương ứng nhiều instant, đặc biệt khi DST fallback | Chuyển sang `Instant` theo business zone ngay từ đầu |
| Cộng 24 giờ để lấy ngày lịch trong vùng DST | Bỏ hoặc thêm một giờ dữ liệu | Lấy đầu ngày địa phương kế tiếp rồi đổi UTC |
| Dùng `BETWEEN` trên hai range kề nhau | Double-count tại timestamp ranh giới | Dùng `>= from` và `< to` |
| Ép timestamp xuống giây hoặc millisecond | Trùng/thiếu tại phần thập phân | Dùng kiểu JDBC/timestamp cùng độ chính xác phù hợp |
| Truyền timestamp string không kèm zone | Phụ thuộc timezone session DB/worker | Dùng `Instant` hoặc `OffsetDateTime` rõ UTC |
| Giả định `event_time` luôn đáng tin | Late events/clock skew lọt khỏi lần quét | Dùng watermark và chính sách backfill |

### Nếu cần một partition theo ngày thay vì theo giờ

Không sử dụng cố định `Duration.ofDays(1)` cho lịch địa phương. Có thể lập các cặp `LocalDate` liên tiếp theo `ZoneId`, chuyển **hai đầu mỗi ngày** sang `Instant` và lưu mỗi khoảng `[fromUtc,toUtc)`. Khi restart, giữ nguyên version timezone rules hoặc lưu hẳn ranh giới UTC đã tính trong manifest.

## 9. Late arrivals, cutoff và watermark

Một sự kiện có `event_time = 10:00` có thể chỉ được ingest lúc `13:00` do mạng chậm. Nếu job chạy lúc 11:00, quét `event_time < 11:00`, sự kiện này **chưa tồn tại trong DB** nên không được đọc. Nó xuất hiện sau khi job đã hoàn tất, dù timestamp của nó nằm trong range đã xử lý.

Đây là vấn đề **late-arriving data**, không phải lỗi thuật toán `Partitioner`.

### Những chiến lược xử lý

1. **Freeze snapshot:** trước khi chạy, chốt dataset/version và tạo manifest. Job chỉ đọc tập đầu vào cố định; batch sau xử lý sự kiện mới.
2. **Event-time watermark:** chỉ coi khoảng thời gian đủ “ổn định” sau một độ trễ chờ, ví dụ xử lý đến `maxObservedEventTime - allowedLateness` theo quy ước của nguồn. Watermark là một **đảm bảo của hệ thống dữ liệu** cần được kiểm chứng; không phải cứ trừ 2 giờ là mọi late event đã được bao phủ.
3. **Ingestion-time cutoff:** cắt theo `ingested_at` để đảm bảo dữ liệu đã tới hệ thống, rồi tổng hợp kết quả theo `event_time`/ngày nghiệp vụ.
4. **Reprocessing/backfill có kiểm soát:** chạy lại cửa sổ cũ sau khi event đến muộn; dùng output idempotent/versioned để tránh nhân đôi.
5. **CDC hoặc event log:** dùng offset/transaction ID bất biến để theo dõi thay đổi, thay vì giả định một truy vấn theo thời gian là đủ mọi cập nhật.

**Không dùng `MAX(event_time)` đơn lẻ như bằng chứng không còn late events.** Một nguồn có thể gửi sự kiện rất cũ sau hàng giờ hoặc ngày. SLA lateness và logic bù dữ liệu phải là một phần của contract với upstream.

### Chốt đầu vào theo JobParameters

Ví dụ một job launch với:

~~~text
fromUtc    = "2026-11-25T00:00:00Z"
toUtc      = "2026-11-26T00:00:00Z"
snapshotId = "snap-2026-11-25-v1"
~~~

Những identifying parameters này cần gắn với **cùng tập dữ liệu** khi restart. `snapshotId` chỉ hữu ích nếu snapshot đó thực sự bất biến hoặc có version rõ; không dùng một tên logic có thể trỏ sang dữ liệu khác vào ngày hôm sau.

Nếu là workload liên tục, nên ghi lại watermark/offset **sau khi kết quả cửa sổ trước đã commit** theo thiết kế transaction thích hợp. Không chỉ lưu “đã đến giờ 12:00” rồi bỏ qua việc xác minh cửa sổ trước có thực sự hoàn tất.

## 10. Checkpoint, restart và tính nhất quán

Partitioning giúp mỗi cửa sổ có `StepExecutionContext` và checkpoint riêng, nhưng restart vẫn có thể sai nếu plan bị tạo lại khác hoặc input thay đổi.

### Kịch bản bình thường

~~~text
window_00000 [00:00,06:00): COMPLETED
window_00001 [06:00,12:00): COMPLETED
window_00002 [12:00,18:00): FAILED ở chunk thứ 20
window_00003 [18:00,24:00): COMPLETED

Restart cùng JobInstance:
  -> framework kiểm tra metadata partition
  -> các partition đã hoàn tất thường không cần chạy lại
  -> partition lỗi tiếp tục theo checkpoint nếu reader/step restartable
~~~

Điều này phụ thuộc version/config và trạng thái thực tế trong `JobRepository`; không nên tự thao tác `BATCH_STEP_EXECUTION` bằng SQL để thay status.

### Các bất biến phải giữ qua restart

- **Cùng identifying `JobParameters`:** `fromUtc`, `toUtc`, `snapshotId` (nếu nhận diện job instance) phải nhất quán. Tự sinh `run.id` mới có thể tạo instance khác.
- **Partition names và ranh giới ổn định:** không đổi `windowWidth` hay thuật toán chia trong cùng job instance sau khi một số partition đã commit.
- **Input bất biến:** bản ghi không bị thêm/xóa/đổi `event_time`/`snapshot_id` hoặc thay payload làm checkpoint trở nên vô nghĩa.
- **Thứ tự đọc ổn định:** `ORDER BY event_time, id`; với JDBC paging/keyset, sort key phải ổn định và đủ duy nhất.
- **`ItemStream` lifecycle:** có `open/update/close`, `saveState(true)` và tên reader nhất quán giữa các lần chạy.
- **Writer idempotent:** mọi side effect cần có chiến lược thực thi lại an toàn.
- **Không đồng thời chạy cùng một execution ở hai worker:** broker redelivery/manager restart có thể gây duplicate dispatch nếu không kiểm soát.

**ExecutionContext không phải một distributed lock.** Nó lưu metadata và checkpoint; cần transaction, unique constraint, idempotency key hoặc lease/fencing khi nhiều process có thể cùng tác động lên một tài nguyên.

### Vì sao chỉ đếm tổng record có thể đánh lừa?

Nếu partition A ghi trùng một ID và partition B bỏ sót một ID, tổng `writeCount` có thể vẫn đúng. Cần đối soát **tập khóa nghiệp vụ** hoặc checksum theo partition, ví dụ số ID độc nhất, không chỉ cộng `readCount`/`writeCount`.

### Reader cursor so với paging

`JdbcCursorItemReader` trong ví dụ giữ JDBC cursor trong quá trình step, có thể kéo dài vòng đời kết nối. Với workload lớn, cân nhắc `JdbcPagingItemReader` để đọc theo trang có thứ tự ổn định hoặc thiết kế keyset pagination. Nhưng:

- Paging chỉ restart được đáng tin khi **sort keys ổn định/duy nhất** và dataset không dịch chuyển.
- Offset pagination trên bảng đang bị insert/update/delete có thể bỏ hoặc đọc lại record.
- Keyset pagination theo `(event_time,id)` có thể ổn định hơn cho quét tiến về phía trước, nhưng vẫn cần snapshot/cutoff và checkpoint của key cuối.
- Đừng thay reader implementation giữa hai lần chạy của một job instance mà không kiểm tra migration checkpoint.

## 11. Partition Spring Batch khác partition vật lý trong database

Hai khái niệm có chữ “partition” nhưng **độc lập**:

| Thuộc tính | **Spring Batch partitioning** | **Database table partitioning** |
|---|---|---|
| Chia cái gì? | Workload/`StepExecution` | Dữ liệu vật lý của bảng |
| Ai quyết định? | `Partitioner` và manager step | DDL/table layout/planner DB |
| Lợi ích chính | Xử lý song song và restart theo đơn vị công việc | Partition pruning, quản lý retention, index/storage per partition |
| Số phần | Theo plan batch, có thể vài chục/nhìn workload | Theo tháng/ngày/tenant và chiến lược DBA |
| Có buộc dùng cùng nhau? | Không | Không |

Ví dụ PostgreSQL table partition theo tháng:

~~~sql
CREATE TABLE business_events_native (
    id          BIGINT NOT NULL,
    snapshot_id VARCHAR(64) NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    payload     TEXT NOT NULL
) PARTITION BY RANGE (event_time);

CREATE TABLE events_2026_11
    PARTITION OF business_events_native
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO ('2026-12-01 00:00:00+00');

CREATE INDEX idx_events_native_snapshot_time_id
    ON business_events_native (snapshot_id, event_time, id);
~~~

Đây là **ví dụ riêng** cho native partitioning, không yêu cầu thay bảng `business_events` ở phần đầu. Trong PostgreSQL, unique/primary key của bảng partitioned có giới hạn liên quan tới partition key; không thể đơn giản tuyên bố `PRIMARY KEY(id)` trên mọi layout partition mà không xét khóa phân vùng. Cần thiết kế khóa, retention và default partition theo dữ liệu thực tế.

**Partition pruning** giúp planner loại bỏ các table partition ngoài khoảng thời gian được truy vấn, nếu điều kiện `event_time` và metadata partition cho phép. Nhưng dù DB có partition theo tháng, Spring Batch vẫn có thể tạo cửa sổ 6 giờ để scale xử lý trong một tháng. Ngược lại, một table thường có index tốt vẫn có thể được đọc bởi nhiều worker batch theo các cửa sổ không giao nhau.

Không tạo hàng chục nghìn table partitions chỉ vì batch có hàng chục nghìn StepExecutions: số partition vật lý lớn có chi phí planning, catalog, maintenance riêng.

## 12. Chọn độ rộng cửa sổ và xử lý partition skew

Giả sử 24 giờ dữ liệu có phân bố:

| Cửa sổ 6 giờ | Số sự kiện | Thời gian xử lý minh họa |
|---|---:|---:|
| 00:00–06:00 UTC | 0,8 triệu | 4 phút |
| 06:00–12:00 UTC | 1,2 triệu | 6 phút |
| 12:00–18:00 UTC | 8,0 triệu | 32 phút |
| 18:00–24:00 UTC | 2,0 triệu | 10 phút |

Dù có 4 worker, job vẫn đợi partition nặng nhất gần **32 phút** (chưa kể overhead), thay vì lý tưởng 13 phút. Đây là **partition skew**, không phải lỗi Spring Batch.

### Ba chiến lược cân tải

1. **Fixed duration:** mỗi cửa sổ 1/3/6 giờ. Đơn giản, dễ restart; phù hợp phân bố khá đều.
2. **Adaptive boundaries:** dùng histogram hoặc count theo giờ trong snapshot để chọn ranh giới khác nhau sao cho số record/chi phí gần đồng đều. Cần lưu **manifest các ranh giới đã chọn** để restart không chia lại.
3. **Hai chiều:** chia theo thời gian và thêm `hash(id)`/tenant/bucket khi một giờ quá nóng. Khi ấy mỗi partition có cả `[from,to)` và `bucketId`; bảo đảm các bucket độc lập và bao phủ toàn tập.

Không tự đổi `gridSize` hoặc độ rộng cửa sổ giữa restart chỉ vì máy mới có nhiều CPU hơn; việc thay plan có thể làm mất liên hệ với các checkpoint của partition đã chạy.

### Ví dụ kết hợp thời gian và hash

~~~sql
SELECT id, snapshot_id, event_time, payload
FROM business_events
WHERE snapshot_id = :snapshotId
  AND event_time >= :fromInclusive
  AND event_time <  :toExclusive
  AND MOD(id, :bucketCount) = :bucketId
ORDER BY event_time, id;
~~~

Điều kiện bucket chỉ minh họa một công thức xác định cho ID không âm; trong SQL PostgreSQL, `mod` của số âm có quy tắc phần dư có dấu, nên cần chuẩn hóa nếu khóa có thể âm. Một biểu thức `MOD(id, bucketCount)` thường **khó tận dụng btree index thông thường**, nên cần đo plan hoặc dùng hash bucket đã materialize/index. Không đổi `bucketCount` giữa restart cùng job instance.

## 13. Tính ngân sách concurrency và database connection

Một `Partitioner` tạo 48 cửa sổ không có nghĩa 48 worker nên chạy đồng thời. Giả sử có `P=48` partition, `N=4` worker pod và mỗi pod xử lý tối đa `L=2` execution:

\[
C_{\mathrm{active}}\le \min(P,N\times L)
=\min(48,4\times2)=8
\]

Nếu mỗi execution giữ một cursor connection, transaction writer và các lượt metadata update, DB có thể bị nghẽn trước khi CPU đạt tối đa. Ước lượng về số connection **có thể mở**:

\[
C_{\mathrm{cluster}}\approx
N\times P_{\mathrm{pool/worker}}
+P_{\mathrm{manager}}
+P_{\mathrm{other}}
\]

Đây là capacity/giới hạn cấu hình, **không phải** số connection active hay số kết nối mỗi partition luôn chiếm. Với hai `DataSource` (business và metadata), tính riêng từng DB; tránh cộng nhầm hai pool phục vụ hai database độc lập rồi so với một `max_connections`.

### Khi tăng worker không tăng tốc

| Dấu hiệu | Nút thắt khả dĩ | Hành động đo/điều chỉnh |
|---|---|---|
| Worker CPU thấp, DB pool pending cao | Thiếu connection hoặc query chậm | Giảm concurrency, tối ưu query/index, kiểm tra DB capacity |
| DB I/O 100%, buffer read tăng | Range scan gây nhiều disk read | Đo explain/buffers, cache và vật lý bảng |
| CPU worker cao, DB rảnh | Processor CPU-bound | Có thể tăng worker hoặc CPU limit |
| Partition duration lệch xa | Skew theo thời gian | Histogram/adaptive boundaries |
| Deadlock/lock wait tăng | Các worker ghi vào vùng/chỉ mục nóng | Giảm đồng thời, tối ưu transaction và khóa |
| `BATCH_STEP_EXECUTION` cập nhật chậm | Metadata DB quá tải | Đo commit/polling latency, tránh quá nhiều partition nhỏ |
| Queue chờ nhiều nhưng DB còn dư | Worker/consumer thiếu | Scale worker trong giới hạn pool và thread safety |

Mỗi cửa sổ quá nhỏ làm tăng overhead tạo `StepExecution`, metadata rows, transaction setup và scheduling. Mỗi cửa sổ quá lớn làm tăng skew, giảm khả năng phục hồi từng phần. Độ rộng tốt nhất phải dựa trên **số record và thời gian thực tế**, không chọn chỉ theo tính đẹp của lịch.

### Benchmark có thể lặp lại

Chạy các mức concurrency 1, 2, 4, 8 trên **cùng immutable snapshot**. Thu:

- Job wall-clock time, throughput (records/s), p50/p95 duration per partition.
- Rows scanned/returned, query latency, buffer read/cache hit, sort spill.
- Pool active/idle/pending, DB CPU/IOPS, lock wait, transaction rollback.
- Worker CPU, heap/GC, active threads và connection lifetime.
- `readCount`/`writeCount`/skip/retry, checkpoint age và **tập khóa output đúng**.

Không kết luận partitioning tốt chỉ vì wall-clock giảm nếu có dữ liệu trùng/thiếu. Chất lượng kết quả phải là invariant của benchmark.

## 14. Quan sát và runbook xử lý lỗi range

### Metric và log theo đúng partition

~~~text
jobName, jobExecutionId, stepExecutionId
partitionName
fromInclusive, toExclusive (UTC)
snapshotId hoặc hashed snapshot key
workerInstanceId
readCount, writeCount, commitCount, rollbackCount
durationMs, DB pool waitMs, query latency
last checkpoint / execution status
~~~

Vì `JobParameters`/`ExecutionContext` có thể được lưu lâu dài trong metadata, không đặt credential/token hoặc dữ liệu cá nhân nhạy cảm ở đó. Log nên chỉ ghi những key/bounds an toàn và có quyền truy cập phù hợp.

### Tình huống A — Có bản ghi bị đọc hai lần ở mốc 06:00

1. Kiểm tra tất cả query có dùng `>= from AND < to` không, có chỗ nào dùng `BETWEEN` hay `<= to` không.
2. Đối chiếu `fromInclusive/toExclusive` của hai `StepExecution` liền kề.
3. Xác minh time precision và timezone binder/driver, không ép cắt milli/microsecond sai.
4. Kiểm tra output có trùng business key vì **retry/duplicate dispatch** chứ không phải vì khoảng thời gian giao nhau.
5. Thêm test boundary với sự kiện đúng mốc 06:00 trước khi chạy lại.

### Tình huống B — Số record ngày hôm qua thiếu

1. Kiểm tra `fromUtc`/`toUtc` và timezone dùng để đổi từ ngày nghiệp vụ.
2. Xác định có late-arriving event hay row đã bị sửa `event_time`/snapshot hay không.
3. Kiểm tra skip/filter/read errors và dữ liệu thỏa `snapshot_id`.
4. Đối chiếu watermark/manifest và tập event ID thực tế.
5. Backfill/reprocess có idempotency; không chỉ tăng `gridSize`.

### Tình huống C — Một cửa sổ chậm bất thường

1. Đo số row thật trong cửa sổ, so sánh partition khác.
2. Chạy `EXPLAIN (ANALYZE, BUFFERS)` trên staging/safe window để xem index/pruning.
3. Kiểm tra DB pool pending, IO latency, lock wait, query sort spill.
4. Đề xuất histogram/adaptive partition plan cho **job instance mới** nếu cần; không tự chia lại partition đang restart.

### Tình huống D — Worker chết giữa chunk

1. Tra metadata `StepExecution` và checkpoint; xác minh worker cũ đã dừng.
2. Đối chiếu side effect đã commit và input snapshot bất biến.
3. Restart cùng `JobInstance`/partition plan, không tự sinh job instance mới để né status lỗi.
4. Đối soát output theo khóa nghiệp vụ, kiểm tra redelivery nếu chạy remote partitioning.

### Tình huống E — DB quá tải khi scale

1. Giảm đồng thời để bảo vệ hệ thống, đo connection pending và latency.
2. Kiểm tra index, range scan và số partition chạy đồng thời.
3. Tách metadata/business pool, giới hạn cursor connection nếu cần.
4. Tăng worker chỉ khi DB/IO/CPU có capacity; nếu không, tối ưu SQL hoặc dời job ngoài giờ cao điểm.

## 15. Ma trận kiểm thử cần có

| Kịch bản | Input | Kỳ vọng |
|---|---|---|
| Ranh giới đúng | Event ở 05:59:59.999999, 06:00:00, 06:00:00.000001 | Mỗi event thuộc chính xác một cửa sổ |
| Khoảng không chia hết | 13 giờ, windowWidth 6 giờ | Các cửa sổ 6h, 6h, 1h; không vượt `toExclusive` |
| Không có record | Một cửa sổ trống | Worker hoàn tất với 0 item, không lỗi nếu nghiệp vụ cho phép |
| Timestamp trùng nhau | 1.000 row cùng `event_time` | `ORDER BY event_time,id` ổn định, đủ ID |
| Dữ liệu lệch | Một giờ chứa 80% event | Đo skew, không biến sai dữ liệu thành lỗi concurrency |
| DST forward/backward | Ngày lịch New York qua DST | 23/25 giờ thực, đúng ngày nghiệp vụ |
| Late event | Event tới sau khi window đã hoàn tất | Có watermark/backfill policy, không “mất im lặng” |
| Worker crash | Kill giữa chunk đã có commit | Restart đúng checkpoint, writer idempotent |
| Plan thay đổi | Đổi windowWidth khi restart | Phát hiện/không cho phép âm thầm đổi partition identity |
| Duplicate request | Broker redeliver một partition | Không ghi trùng business key |
| DB pool nhỏ | Tăng worker vượt capacity | Cảnh báo/pending rõ, không sai dữ liệu |
| Physical partition pruning | Query một cửa sổ trong bảng partitioned | Planner loại được phân vùng không liên quan khi điều kiện phù hợp |

### Test kiểm tra tính phủ và không giao nhau

Với một plan tạo ra N window, có thể xác minh logic:

~~~text
assert windows[0].fromInclusive == job.fromUtc
assert windows[N-1].toExclusive == job.toUtc

for i = 0..N-1:
    assert windows[i].fromInclusive < windows[i].toExclusive
    if i > 0:
        assert windows[i-1].toExclusive == windows[i].fromInclusive

for each input event:
    assert countOfMatchingWindows(event.eventTime) == 1
~~~

Đây là **pseudocode**. Test cần dùng timestamps ở mép khoảng, giá trị cùng timestamp, timezone/DST và payload trong snapshot thực; một test chỉ so sánh tổng count chưa chứng minh không có một item trùng và một item thiếu.

## 16. Checklist triển khai production

- [ ] Đã chọn đúng timestamp cho contract nghiệp vụ (`event_time`, `ingested_at` hoặc `business_date`).
- [ ] Tất cả cửa sổ dùng **`[fromInclusive, toExclusive)`**; SQL không dùng `BETWEEN` ở ranh giới.
- [ ] `fromUtc/toUtc` được xác định theo timezone đúng, có xử lý ngày lịch/DST khi cần.
- [ ] `JobParameters` và plan partition ổn định cho cùng job instance; input snapshot/cutoff bất biến.
- [ ] `Partitioner` tạo các `ExecutionContext` độc lập và partition names xác định.
- [ ] Reader dùng `@StepScope`, `ItemStream` có tên/checkpoint ổn định; không chia sẻ cursor mutable.
- [ ] SQL có sort key duy nhất/ổn định, index và query plan đã được kiểm tra.
- [ ] Có chính sách watermark/late events/backfill cho dữ liệu đến muộn.
- [ ] Writer idempotent; side effect ngoài DB có transactional outbox/deduplication nếu cần.
- [ ] Đã phân biệt Batch partitioning với DB physical partitioning và chi phí của mỗi loại.
- [ ] Số partition/concurrency được cân theo DB connection, CPU, IO, lock và metadata load.
- [ ] Có metric/log theo `stepExecutionId`, `partitionName`, time range và snapshot.
- [ ] Đã thử restart giữa chunk, duplicate request và đối soát tập khóa output.
- [ ] Không tự đổi plan, sửa status metadata bằng SQL hoặc tăng worker khi chưa đo nút thắt.

## 17. Bài tập thực hành

### Bài 1 — Vẽ và kiểm chứng các cửa sổ

Với job `[2026-11-25T00:00Z, 2026-11-26T00:00Z)` và cửa sổ `Duration.ofHours(5)`, liệt kê toàn bộ partition. Chứng minh cửa sổ cuối không vượt `toUtc`. Tạo bốn sự kiện tại 04:59:59.999999, 05:00:00, 09:59:59.999999 và 10:00:00, chỉ rõ mỗi event thuộc partition nào.

### Bài 2 — Viết worker StepScope

Từ `TimeWindowPartitioner`, tạo manager step và worker `JdbcCursorItemReader`. Dùng `@Value("#{stepExecutionContext['fromInclusive']}")` và `toExclusive`, `jobParameters['snapshotId']`. Bổ sung test một worker nhận đúng range và không đọc dữ liệu của partition liền kề.

### Bài 3 — Ngày nghiệp vụ và DST

Tính `fromUtc`/`toUtc` cho ngày `2026-03-08` và `2026-11-01` ở `America/New_York`. So sánh với việc cộng cố định 24 giờ. Giải thích vì sao một job đối soát theo **ngày địa phương** cần tính biên khác một job chia 24 giờ UTC.

### Bài 4 — Late events và watermark

Một sự kiện xảy ra lúc 10:00 nhưng `ingested_at=13:00`, job đã xử lý `[00:00,12:00)` lúc 12:10. Thiết kế hai phương án: (a) chờ watermark phù hợp SLA lateness; (b) backfill cửa sổ cũ với writer idempotent. Nêu cách không tạo trùng output.

### Bài 5 — Cân tải theo dữ liệu thật

Có bốn cửa sổ 6 giờ với số record lần lượt 1, 2, 12 và 1 triệu. Đề xuất plan thích ứng bằng histogram sao cho một worker không phải gánh gần toàn bộ dữ liệu. Mô tả cách **lưu manifest** để giữ plan ổn định khi restart.

### Bài 6 — Benchmark có kiểm soát

Trên cùng snapshot, chạy 1, 2, 4 và 8 worker. Ghi throughput, DB pool pending, CPU/IO, p95 partition duration và tập event ID đã xử lý. Kết luận tại mức nào tăng worker không còn có ích và kiểm tra có phải vấn đề index, skew hay contention.

**Câu hỏi tự kiểm tra:** Vì sao điều kiện `event_time < toExclusive` tốt hơn `BETWEEN`? Vì sao mỗi worker cần `@StepScope` khi reader có cursor? Giữ `gridSize` lớn có tự tăng số partition/worker thực thi không? Vì sao một ngày lịch có thể dài 23 giờ? Khi nào watermark khác snapshot? Vì sao index theo thời gian chưa đủ nếu dữ liệu skew? Tại sao không nên đổi tên partition hoặc key checkpoint khi restart?

## 18. Tổng kết

**Partition theo range thời gian** giúp Spring Batch chia workload dữ liệu lớn thành các `StepExecution` độc lập, có thể thực thi song song và checkpoint riêng. Nguyên tắc cốt lõi là dùng **cửa sổ nửa mở `[fromInclusive, toExclusive)`**, xác định ranh giới UTC rõ ràng, giữ partition plan ổn định và bảo đảm SQL có thứ tự đọc xác định.

Scale đúng không dừng ở việc tạo nhiều cửa sổ. Cần có **snapshot/watermark và chính sách late arrivals, reader `@StepScope` có thể restart, writer idempotent, index/query plan phù hợp và ngân sách connection/CPU/IO thực tế**. Phân biệt partition logic của Batch với partition vật lý database, đo partition skew và đối soát khóa nghiệp vụ sẽ giúp mở rộng hệ thống mà không đánh đổi tính đúng hoặc khả năng khôi phục dữ liệu.
