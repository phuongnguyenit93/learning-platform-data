# Chia dữ liệu theo thời gian trong Spring Batch

## Mục tiêu bài học

Nhiều workload batch có dấu mốc thời gian tự nhiên: giao dịch phát sinh trong ngày, log theo giờ, sự kiện theo thời điểm xảy ra, hóa đơn theo kỳ kế toán hoặc dữ liệu cần nạp theo từng tháng. **Chia dữ liệu theo thời gian (time-based partitioning)** là cách giao cho mỗi worker một khoảng thời gian rõ ràng để nhiều worker xử lý độc lập, thay vì bắt một reader tuần tự đọc toàn bộ tập dữ liệu.

Bài này thuộc chương **Chia dữ liệu** của module **SPRING_BATCH_SCALING_OPERATIONS**. Nội dung hướng đến việc mở rộng Spring Batch bằng **local/remote partitioning**, đồng thời liên hệ multi-threaded step, parallel steps và các mô hình phân tán. Trọng tâm không chỉ là chia cho đủ phần, mà là thiết kế **ranh giới thời gian, truy vấn, cân bằng tải, thread safety, retry/restart và vận hành** dựa trên tài nguyên thực tế.

Học xong bài này, bạn có thể:

- Chọn đúng timestamp để partition: event time, ingestion time, creation time hoặc business date.
- Thiết kế khoảng **bao gồm cận dưới, loại trừ cận trên** để không chồng lấn hoặc bỏ sót.
- Phân biệt cửa sổ thời gian UTC cố định với ngày lịch trong một múi giờ, kể cả DST.
- Tạo **Partitioner** và **reader @StepScope** để mỗi StepExecution nhận một khoảng thời gian riêng.
- Tối ưu truy vấn, index và số partition theo mật độ dữ liệu thực tế.
- Xử lý late-arriving data, watermark, snapshot, rerun/backfill và idempotent writer.
- Đánh giá local partitioning so với remote partitioning và giới hạn DB nguồn/đích.
- Kiểm tra restart, tính đúng dữ liệu và throughput khi worker lỗi hoặc dữ liệu thay đổi.

## 1. Chia theo thời gian là gì?

Giả sử một batch cần xử lý giao dịch phát sinh từ ngày 1 đến hết ngày 7. Nếu dùng một reader, toàn bộ dữ liệu có thể được đọc tuần tự. Với time-based partitioning, manager tạo các **time window** và giao mỗi window cho một worker StepExecution.

~~~mermaid
flowchart TB
    M["Manager Step / Partitioner"]
    M --> A["Window A: 01/11 → 02/11"]
    M --> B["Window B: 02/11 → 03/11"]
    M --> C["Window C: 03/11 → 04/11"]
    M --> D["... các window tiếp theo"]
    A --> W1["Worker StepExecution A"]
    B --> W2["Worker StepExecution B"]
    C --> W3["Worker StepExecution C"]
    D --> W4["Worker StepExecution D"]
    W1 --> DB[("Nguồn dữ liệu theo thời gian")]
    W2 --> DB
    W3 --> DB
    W4 --> DB
~~~

Trong Spring Batch, **Partitioner không tự truy vấn và chuyển toàn bộ item**. Nó thường tạo **tên partition và ExecutionContext** mô tả phần việc; reader của worker mới thực sự lấy dữ liệu. Local partitioning thực thi các worker step trên các thread trong một JVM. Remote partitioning gửi yêu cầu thực thi đến nhiều JVM và các worker tự đọc phần dữ liệu được giao.

**Ví dụ phạm vi logic:**

| Partition | Bắt đầu (bao gồm) | Kết thúc (loại trừ) |
| --- | --- | --- |
| window-0 | 2026-11-01T00:00:00Z | 2026-11-02T00:00:00Z |
| window-1 | 2026-11-02T00:00:00Z | 2026-11-03T00:00:00Z |
| window-2 | 2026-11-03T00:00:00Z | 2026-11-04T00:00:00Z |

**Lưu ý:** đây là các ngày theo **UTC**. Nếu nghiệp vụ yêu cầu “ngày theo múi giờ Việt Nam” hoặc một múi giờ có DST, ranh giới UTC sẽ khác và phải được chuyển đổi có chủ đích.

## 2. Quy tắc nền tảng: khoảng thời gian nửa mở

Mỗi partition sở hữu một khoảng:

\[
W_i=[t_i,t_{i+1})
\]

Có nghĩa:

- Bản ghi có timestamp **đúng bằng t_i** thuộc window hiện tại.
- Bản ghi có timestamp **đúng bằng t_{i+1}** thuộc window kế tiếp.
- Hai window liền nhau không chồng lấn nếu **end của window trước = start của window sau**.

Truy vấn tương ứng:

~~~sql
SELECT id, occurred_at, amount_cents
FROM source_events
WHERE occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive
ORDER BY occurred_at, id;
~~~

Tránh dùng:

~~~sql
-- KHÔNG nên áp dụng khi hai window liền nhau:
WHERE occurred_at BETWEEN :fromTime AND :toTime;
~~~

Trong SQL, **BETWEEN thường bao gồm cả hai cận**. Một sự kiện có thời điểm đúng 12:00 có thể xuất hiện trong cả window 06:00–12:00 và 12:00–18:00 nếu dùng cận trên bao gồm.

Cũng tránh tự viết cuối ngày bằng `23:59:59.999`: độ chính xác của timestamp có thể là microsecond/nanosecond, và ngày theo múi giờ có thể không dài đúng 24 giờ. Dùng **cận trên loại trừ là mốc đầu window tiếp theo** sẽ rõ và ít lỗi hơn.

### Chứng minh không chồng lấn và không bỏ sót

Giả sử cần xử lý toàn bộ:

\[
W=[T_{\mathrm{start}},T_{\mathrm{end}})
\]

Ta tạo các mốc có thứ tự:

\[
T_{\mathrm{start}}=t_0<t_1<\dots<t_n=T_{\mathrm{end}}
\]

Nếu mỗi partition nhận \([t_i,t_{i+1})\), thì:

- Hợp các khoảng bằng chính \([T_{\mathrm{start}},T_{\mathrm{end}})\).
- Giao của hai khoảng liền nhau rỗng.
- Mỗi timestamp thuộc phạm vi được giao sẽ rơi vào đúng một khoảng.

Đây mới là tính đúng **của thuật toán chia khoảng**. Để dữ liệu thật không mất/trùng, còn cần bản ghi có timestamp ổn định, truy vấn không bỏ sót và cơ chế ghi/restart phù hợp.

## 3. Chọn timestamp nào để chia?

Không phải cột ngày giờ nào cũng phản ánh cùng một ý nghĩa. Trước khi viết Partitioner phải chốt **trục thời gian của nghiệp vụ**.

| Loại thời gian | Ý nghĩa | Hợp với bài toán nào? | Rủi ro |
| --- | --- | --- | --- |
| **Event time** (`occurred_at`) | Thời điểm nghiệp vụ thực sự xảy ra | Phân tích giao dịch, sự kiện, log | Event đến trễ hoặc được sửa thời gian |
| **Ingestion time** (`ingested_at`) | Thời điểm hệ thống nhận/lưu bản ghi | ETL theo đợt nạp, incremental load | Khác ngày nghiệp vụ; thứ tự tới không bằng thứ tự xảy ra |
| **Creation time** (`created_at`) | Thời điểm record được tạo trong nguồn | Nạp bảng append-only, dữ liệu hệ thống | Nếu import/migration ghi lại dữ liệu cũ, không phản ánh thời gian nghiệp vụ |
| **Update time** (`updated_at`) | Thời điểm chỉnh sửa cuối | Quét thay đổi gần đây | Dữ liệu có thể đổi partition giữa lúc job chạy |
| **Business date** (`business_date`) | Kỳ nghiệp vụ (ngày sổ sách, ngày giao dịch) | Kế toán, đối soát, kết sổ | Không nhất thiết là thời điểm UTC hay timestamp duy nhất |

Ví dụ một giao dịch diễn ra lúc **23:58** nhưng đến hệ thống lúc **00:04** ngày hôm sau. Nếu chia theo **occurred_at**, nó thuộc ngày giao dịch trước. Nếu chia theo **ingested_at**, nó thuộc đợt nạp ngày sau. Cả hai có thể đúng, nhưng phải trả lời **người dùng cuối đang yêu cầu số liệu theo ngày nào**.

**Quy tắc chọn trục thời gian:**

1. Xác định báo cáo/đầu ra cần gắn với loại ngày giờ nào.
2. Xác nhận cột có immutable hoặc có cơ chế theo dõi phiên bản hay không.
3. Xác định sự kiện tới muộn có được sửa kết quả cũ không.
4. Kiểm tra timezone và độ chính xác của dữ liệu nguồn.
5. Đảm bảo truy vấn có thể dùng index theo cột đã chọn.
6. Ghi chính sách time window vào JobParameters và log vận hành.

Đừng lấy `updated_at` làm partition key rồi mặc nhiên coi vị trí một bản ghi không đổi trong suốt job. Nếu timestamp đổi từ window A sang B khi các worker đang đọc, bản ghi có thể bị đọc hai lần hoặc không lần nào, tùy isolation và lịch thực thi.

## 4. UTC, múi giờ địa phương và DST

**Instant** biểu diễn một thời điểm trên trục UTC. **LocalDate** biểu diễn một ngày lịch. Hai đối tượng này không thay thế nhau.

Ví dụ một ngày theo `Asia/Ho_Chi_Minh` bắt đầu lúc 00:00 theo giờ Việt Nam, tương ứng **17:00 UTC ngày hôm trước** vì múi giờ là UTC+07 trong bối cảnh hiện tại. Truy vấn theo “ngày lịch Việt Nam” không nên lấy máy chủ đang dùng UTC rồi cắt theo 00:00 UTC.

Ở những múi giờ có **Daylight Saving Time (DST)**, một ngày địa phương có thể dài **23 hoặc 25 giờ**. Nếu lấy midnight địa phương rồi cộng `Duration.ofHours(24)` để tìm midnight kế tiếp, ranh giới có thể sai vào ngày chuyển DST.

### Cách đúng khi cần từng ngày lịch địa phương

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("America/New_York");
LocalDate businessDay = LocalDate.of(2026, 11, 1);

Instant fromInclusive =
        businessDay.atStartOfDay(businessZone).toInstant();

Instant toExclusive =
        businessDay.plusDays(1)
                   .atStartOfDay(businessZone)
                   .toInstant();
~~~

Đoạn mã tạo khoảng từ **đầu ngày lịch này đến đầu ngày lịch kế tiếp** theo quy tắc múi giờ, bao gồm việc chuyển DST. Vào ngày quay lại giờ mùa đông ở khu vực ví dụ, khoảng này dài 25 giờ thực, không phải một lỗi chia khoảng.

**Khác với window UTC 6 giờ:** khi yêu cầu là “mỗi sáu giờ tuyệt đối”, dùng `Instant.plus(Duration.ofHours(6))` là phù hợp. Khi yêu cầu là “theo từng ngày/tháng nghiệp vụ”, dùng `LocalDate`, `YearMonth`, `ZoneId` và chuyển cận sang `Instant`.

### Nguyên tắc kỹ thuật

- Ghi/so sánh timestamp bằng một quy ước nhất quán, thường là UTC Instant hoặc kiểu DB tương đương.
- Lưu **ZoneId nghiệp vụ** riêng nếu cần tái dựng ngày lịch, không chỉ dùng offset hiện tại.
- Không suy ra timezone từ timezone mặc định của JVM.
- Không parse thời điểm mơ hồ kiểu `2026-11-01 01:30` ở vùng chuyển DST nếu thiếu offset/quy tắc chọn.
- Kiểm tra JDBC driver, DB column type và precision để cận thời gian không bị chuyển đổi sai.
- Khi dữ liệu là `DATE` thuần, chia theo **LocalDate** và điều kiện ngày; không cần cưỡng ép thành timestamp nếu nghiệp vụ không có giờ.

## 5. Chọn kích thước window theo dữ liệu, không chỉ theo lịch

Một thiết kế đơn giản có thể chia theo **ngày**, **giờ**, **tuần** hoặc **tháng**. Nhưng mỗi ngày không chắc chứa cùng số record.

Giả sử một bảng có phân bố:

| Ngày UTC | Số sự kiện | Ước lượng chi phí |
| --- | ---: | --- |
| Thứ Hai | 500.000 | Thấp |
| Thứ Ba | 700.000 | Trung bình |
| Thứ Tư | 4.000.000 | Rất cao |
| Thứ Năm | 650.000 | Trung bình |
| Thứ Sáu | 600.000 | Trung bình |

Nếu giao **một ngày cho một partition**, phần việc Thứ Tư có thể giữ toàn job dù bốn worker đã rảnh. Điều này gọi là **data skew / straggler**.

### Ba chiến lược chia

**1. Window cố định theo thời lượng.** Ví dụ mỗi sáu giờ UTC. Dễ sinh tên và tái lập, thích hợp phân bố dữ liệu tương đối đều.

**2. Window theo lịch nghiệp vụ.** Ví dụ mỗi ngày theo zone được xác định, mỗi tháng kế toán. Đầu ra gắn ranh giới nghiệp vụ rõ, thuận tiện đối soát; tải có thể rất lệch.

**3. Window thích nghi từ histogram/count.** Dùng số record theo giờ/ngày hoặc ước lượng query để chọn cận nhằm cân bằng số item mỗi partition. Có thể tốt hơn nhưng Partitioner phức tạp hơn và phải **cố định quyết định chia** qua restart.

Không nên mặc định rằng nhiều partition luôn nhanh hơn: mỗi StepExecution có khởi tạo, metadata, reader, connection và callback. Partition quá nhỏ làm chi phí điều phối tăng; quá lớn khiến worker cuối kéo dài job và phần việc retry tốn nhiều thời gian.

### Dùng thêm khóa phụ khi có “hot time window”

Một số hệ thống có hàng triệu sự kiện trong vài phút, nên chia chỉ theo giờ chưa đủ. Nếu dữ liệu cho phép, có thể chia window nóng tiếp theo **tenant, customer range, hash của ID hoặc shard**. Khi đó khóa phân vùng trở thành cặp:

\[
(\mathrm{timeWindow},\mathrm{shard})
\]

Ví dụ `[12:00,13:00)` được chia thành bốn shard ID. Cần chứng minh tổ hợp điều kiện này **phủ đủ và không chồng lấn**, đồng thời đánh giá index/query plan: biểu thức `MOD(id,4)` trong `WHERE` có thể không tận dụng index như một range ID thông thường.

## 6. Luồng thực thi trong Spring Batch

Ở **partitioning**, manager và worker có trách nhiệm rõ ràng.

~~~mermaid
sequenceDiagram
    participant J as Job
    participant M as Manager Step
    participant P as Time Partitioner
    participant R as JobRepository
    participant W as Worker Step
    participant D as Source/Target DB

    J->>M: Khởi chạy manager
    M->>P: partition(gridSize)
    P-->>M: Map tên → ExecutionContext
    M->>R: Quản lý các worker StepExecution
    M->>W: Dispatch window A
    M->>W: Dispatch window B
    W->>R: Lấy StepExecution / context
    W->>D: SELECT theo [from,to)
    W->>D: Process + write theo chunk
    W->>R: Checkpoint / trạng thái
    W-->>M: Worker hoàn tất/thất bại
    M-->>J: Tổng hợp trạng thái
~~~

Ở **local partitioning**, manager thường dispatch bằng TaskExecutor tới worker threads trong cùng JVM. Ở **remote partitioning**, PartitionHandler/cơ chế tích hợp giao phần việc tới worker JVM riêng. Hai kiến trúc có thể dùng cùng **Partitioner** và cùng kiểu **StepExecutionContext**.

**Điểm quan trọng:** Spring Batch không tự hiểu businessDate, cột event_time hay cách chia theo sáu giờ. Developer phải định nghĩa Partitioner và reader để bảo đảm mỗi worker chỉ đọc phần của mình.

## 7. Tên partition và ExecutionContext phải ổn định

Một Partitioner thường trả về:

~~~text
time-0000 -> fromInclusive=2026-11-01T00:00:00Z
             toExclusive=2026-11-01T06:00:00Z

time-0001 -> fromInclusive=2026-11-01T06:00:00Z
             toExclusive=2026-11-01T12:00:00Z

time-0002 -> fromInclusive=2026-11-01T12:00:00Z
             toExclusive=2026-11-01T18:00:00Z
~~~

Tên là định danh cần có ý nghĩa **ổn định trong cùng JobInstance**. Thông tin cận dưới/cận trên là input của StepExecution, không phải state chỉ tồn tại trên stack của Partitioner.

### Các lỗi dễ gây mất dữ liệu khi restart

- Mỗi lần khởi tạo lại Partitioner lấy `Instant.now()` và sinh window khác.
- Thay kích thước window trong lúc restart cùng JobInstance.
- Đổi timezone mặc định của máy chủ giữa các lần chạy.
- Sinh partition name bằng UUID ngẫu nhiên thay vì cách đặt tên có tính quyết định.
- Đọc MAX(event_time) mới rồi mở rộng phạm vi mà không có chính sách cutoff.
- Đổi thứ tự hoặc điều kiện lọc reader nhưng giữ checkpoint cũ.
- Dùng toàn bộ input trong ExecutionContext, khiến metadata lớn và khó serialize.

**Thiết kế an toàn hơn:** job nhận `windowStart`, `windowEnd`, `timeZone` hoặc chính sách partition đã **được chốt** bằng JobParameters/metadata phù hợp. Khi restart, cùng danh tính phần việc phải quay lại đúng input đã định nghĩa. Nếu muốn xử lý một kỳ khác, tạo JobInstance mới hoặc quy trình backfill có kiểm soát.

## 8. Ví dụ Java: Partitioner chia mỗi sáu giờ UTC

Ví dụ này dùng **Spring Batch 5.x, Java 17**. Hai JobParameters `windowStart` và `windowEnd` là chuỗi ISO-8601 UTC, chẳng hạn:

~~~text
windowStart = 2026-11-01T00:00:00Z
windowEnd   = 2026-11-03T00:00:00Z
~~~

Khoảng 48 giờ được chia thành **8 partition sáu giờ**, từ `time-0000` đến `time-0007`. Nếu khoảng cuối ngắn hơn sáu giờ, nó nhận phần dư thay vì làm tròn rộng phạm vi.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public Partitioner sixHourTimePartitioner(
        @Value("#{jobParameters['windowStart']}") String windowStart,
        @Value("#{jobParameters['windowEnd']}") String windowEnd) {

    Instant begin = Instant.parse(windowStart);
    Instant finish = Instant.parse(windowEnd);

    if (!begin.isBefore(finish)) {
        throw new IllegalArgumentException(
                "windowStart must be before windowEnd");
    }

    Duration width = Duration.ofHours(6);

    return gridSize -> {
        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        int index = 0;
        for (Instant from = begin;
             from.isBefore(finish);
             from = from.plus(width)) {

            Instant candidateEnd = from.plus(width);
            Instant to = candidateEnd.isBefore(finish)
                    ? candidateEnd : finish;

            ExecutionContext context = new ExecutionContext();
            context.putString(
                    "fromInclusive", from.toString());
            context.putString(
                    "toExclusive", to.toString());

            String name = String.format(
                    Locale.ROOT, "time-%04d", index++);
            result.put(name, context);
        }

        return result;
    };
}
~~~

### Vì sao dùng chuỗi ISO Instant?

- Chuỗi có dạng rõ ràng, dễ ghi log/đối chiếu.
- ExecutionContext chỉ chứa kiểu dữ liệu đơn giản.
- Worker có thể parse về Instant và bind SQL bằng timestamp type phù hợp.
- Không phụ thuộc timezone mặc định của process.

### gridSize trong ví dụ có ý nghĩa gì?

Tham số `gridSize` được framework truyền cho `Partitioner`. **Ví dụ trên cố ý không dùng gridSize để quyết định ranh giới**: số partition do độ dài khoảng và width sáu giờ quyết định. Đây là lựa chọn hợp lệ, nhưng cần hiểu rằng `gridSize(8)` ở manager **không tự bảo đảm đúng tám partition** nếu job có khoảng thời gian khác.

Nếu muốn gridSize tác động đến số window, phải thiết kế phép chia đủ chính xác và ổn định. Không dùng `gridSize` như một tín hiệu để tự thay kết quả partition tùy số worker JVM khi restart.

**Giới hạn minh họa:** với phạm vi cực lớn cần xem số partition và khả năng `Instant.plus` vượt giới hạn biểu diễn; production nên validate kích thước window, số partition tối đa, input ISO timestamp và cấu hình có thể tạo quá nhiều StepExecution.

## 9. Worker reader @StepScope theo time window

Để partitioner có tác dụng, reader trong worker step phải truy vấn đúng cặp cận:

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

public record EventRow(
        long id,
        Instant occurredAt,
        long amountCents) {}

@Bean
@StepScope
public JdbcCursorItemReader<EventRow> timeWindowReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromInclusive']}")
                String fromInclusive,
        @Value("#{stepExecutionContext['toExclusive']}")
                String toExclusive) {

    Instant from = Instant.parse(fromInclusive);
    Instant to = Instant.parse(toExclusive);

    if (!from.isBefore(to)) {
        throw new IllegalArgumentException(
                "Invalid time window");
    }

    return new JdbcCursorItemReaderBuilder<EventRow>()
            .name("timeWindowReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, occurred_at, amount_cents
                 FROM source_events
                 WHERE occurred_at >= ?
                   AND occurred_at < ?
                 ORDER BY occurred_at, id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setObject(1, OffsetDateTime.ofInstant(
                        from, ZoneOffset.UTC));
                ps.setObject(2, OffsetDateTime.ofInstant(
                        to, ZoneOffset.UTC));
            })
            .rowMapper((rs, index) -> new EventRow(
                    rs.getLong("id"),
                    rs.getObject(
                            "occurred_at",
                            OffsetDateTime.class).toInstant(),
                    rs.getLong("amount_cents")))
            .saveState(true)
            .build();
}
~~~

Mã giả định PostgreSQL cột `occurred_at` kiểu **TIMESTAMPTZ**, driver JDBC 4.2+ hỗ trợ bind/read `OffsetDateTime`, và có record/bean hạ tầng tương ứng. Đây là mẫu kiến trúc Spring Batch 5.x; muốn biên dịch trong một file Java thật cần đặt record ở vị trí hợp lệ và bổ sung import/class/configuration phù hợp.

**Vì sao @StepScope?** Mỗi worker StepExecution có cặp cận trong ExecutionContext của nó. Scoped target reader được tạo cho step execution tương ứng, tránh một reader singleton bị chia sẻ con trỏ giữa nhiều partition.

**Nhưng @StepScope không bằng per-thread:** nếu một worker step được cấu hình **multi-threaded chunks trong cùng StepExecution**, các thread có thể dùng **cùng target reader**. Để giữ mô hình dễ phục hồi, ví dụ này cho từng partition xử lý chunk tuần tự; concurrency nằm **giữa partition**.

### Điều kiện của restartable reader

`saveState(true)` chỉ là một phần trong thiết kế checkpoint:

- Tập dữ liệu cần đủ ổn định khi worker đọc và khi restart.
- `ORDER BY occurred_at, id` tạo thứ tự rõ, giả định `id` là khóa duy nhất.
- Nếu bản ghi đến trễ hoặc timestamp đổi giữa các lượt, vị trí checkpoint có thể không còn tương ứng với tập dữ liệu ban đầu.
- Driver/DB phải hỗ trợ cursor, transaction và cách lấy timestamp đúng với kiểu cột.
- Writer cần xử lý được tình huống item/chunk bị chạy lại.

Trường hợp có thay đổi nguồn liên tục, có thể cần snapshot, high-watermark hoặc chiến lược paging/checkpoint khác. Không coi `@StepScope` hoặc `saveState(true)` là chứng nhận tự động rằng job có khả năng restart chính xác.

## 10. Writer idempotent theo business key

Phân vùng theo thời gian không ngăn một worker xử lý lại sau lỗi. Nếu ghi sang bảng đích, nên thiết kế writer có ngữ nghĩa **lặp lại an toàn**.

Ví dụ PostgreSQL:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<EventRow> eventSummaryWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<EventRow>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO event_summary
                     (event_id, occurred_at, amount_cents)
                 VALUES (?, ?, ?)
                 ON CONFLICT (event_id) DO UPDATE SET
                     occurred_at = EXCLUDED.occurred_at,
                     amount_cents = EXCLUDED.amount_cents
                 """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setLong(1, item.id());
                ps.setObject(2, OffsetDateTime.ofInstant(
                        item.occurredAt(), ZoneOffset.UTC));
                ps.setLong(3, item.amountCents());
            })
            .build();
}
~~~

Giả định `event_summary.event_id` có **UNIQUE/PRIMARY KEY**. Upsert phù hợp khi **ghi lại giá trị hiện có** là kết quả nghiệp vụ mong muốn. Nếu writer **cộng dồn** hoặc gọi thanh toán/email/HTTP, upsert này không đủ: phải dùng idempotency key, ledger, transactional outbox hoặc cách đối soát theo giao dịch thích hợp.

Một trường hợp khó hơn là **event được cập nhật có version**. Nếu lần replay cũ ghi đè dữ liệu mới, idempotency về mặt “không thêm dòng trùng” vẫn chưa đủ. Có thể cần `source_version` và điều kiện chỉ cập nhật khi phiên bản đến sau mới hơn, cùng chính sách đối soát.

## 11. Tạo worker step, manager step và TaskExecutor

Tiếp tục các bean trên, cấu hình local partitioning minh họa:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step timeWindowWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<EventRow> timeWindowReader,
        JdbcBatchItemWriter<EventRow> eventSummaryWriter) {

    return new StepBuilder(
            "timeWindowWorkerStep", jobRepository)
            .<EventRow, EventRow>chunk(500, transactionManager)
            .reader(timeWindowReader)
            .writer(eventSummaryWriter)
            .build();
}

@Bean
public TaskExecutor timeWindowExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("time-window-");
    executor.initialize();
    return executor;
}

@Bean
public Step timeWindowManagerStep(
        JobRepository jobRepository,
        @Qualifier("sixHourTimePartitioner")
                Partitioner timePartitioner,
        @Qualifier("timeWindowWorkerStep")
                Step workerStep,
        @Qualifier("timeWindowExecutor")
                TaskExecutor taskExecutor) {

    return new StepBuilder(
            "timeWindowManagerStep", jobRepository)
            .partitioner(
                    "timeWindowWorkerStep", timePartitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

Đây là **các đoạn cấu hình ghép với ví dụ ở trên**, không phải dự án standalone: ứng dụng vẫn cần khai báo `Job`, JobRepository, transaction manager, DataSource, schema và các dependency Spring Batch. Các bean method cần nằm trong lớp `@Configuration` hợp lệ hoặc cấu hình tương đương. Tên package/API cần được đối chiếu với phiên bản Spring Batch đang triển khai; mã hướng tới dòng **5.x**.

### Đừng nhầm ba tham số

| Tham số | Tác động | Ví dụ |
| --- | --- | --- |
| **Window width** | Quy mô dữ liệu mỗi partition | Sáu giờ UTC |
| **Grid size** | Tham số manager chuyển cho Partitioner/handler; ngữ nghĩa cụ thể tùy cấu hình | 8 |
| **Executor concurrency** | Số worker local thực thi đồng thời theo cấu hình pool và handler | 4 thread |
| **Chunk size** | Số item đầu vào mục tiêu trên mỗi transaction/chunk | 500 |

Trong ví dụ, 48 giờ tạo tám partition; bốn thread có thể xử lý chúng theo nhiều lượt. Nếu job nhận 30 ngày đầu vào, Partitioner có thể tạo **120 partition**, dù gridSize vẫn là 8. Khi đó cần xem lại số StepExecution, queue, metadata, kích thước worker và chi phí vận hành.

**Thread safety:** reader @StepScope được tách theo StepExecution. Writer bean singleton trong ví dụ chỉ nên dùng chung nếu implementation và resource bên dưới có hợp đồng concurrent use phù hợp; nếu nó giữ mutable buffer theo partition thì cần thiết kế scope riêng hoặc cách cô lập state khác. Các transaction của nhiều worker vẫn có thể tranh chấp DB.

## 12. Index và truy vấn quyết định lợi ích của chia theo thời gian

Time-based partitioning chỉ hiệu quả khi DB có thể tìm nhanh từng khoảng.

Với truy vấn:

~~~sql
SELECT id, occurred_at, amount_cents
FROM source_events
WHERE occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive
ORDER BY occurred_at, id;
~~~

Một ứng viên index là:

~~~sql
CREATE INDEX idx_source_events_occurred_id
    ON source_events (occurred_at, id);
~~~

Index này có thể giúp lọc range và đọc theo thứ tự, nhưng **không tự động là tối ưu** trong mọi schema/phân bố dữ liệu. Cần kiểm tra query plan, số row scan, I/O, memory và thời gian thực tế. Với nguồn lọc thêm tenant:

~~~sql
SELECT id, occurred_at, amount_cents
FROM source_events
WHERE tenant_id = :tenantId
  AND occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive
ORDER BY occurred_at, id;
~~~

Có thể cân nhắc index bắt đầu bằng `tenant_id` rồi đến `occurred_at, id` nếu tương thích với pattern truy vấn và workload chung.

### Tránh biến đổi cột ngay trong WHERE khi không cần

~~~sql
-- Có thể khiến index thông thường trên occurred_at
-- khó được khai thác hiệu quả:
WHERE DATE(occurred_at) = :businessDate;
~~~

Thay bằng điều kiện range trên giá trị timestamp đã chuyển đổi về cận đúng:

~~~sql
WHERE occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive;
~~~

Một số DB hỗ trợ expression index hoặc partition pruning riêng; vì vậy phải xác nhận bằng **EXPLAIN** thay vì coi mọi cách dùng DATE là sai tuyệt đối.

### Table partitioning không đồng nghĩa Spring Batch partitioning

- **Spring Batch partitioning:** chia **công việc thực thi** thành StepExecution và reader theo window.
- **Database table partitioning:** chia **lưu trữ vật lý** theo range/list/hash trong DB để quản trị dữ liệu và tối ưu truy vấn.

Hai cơ chế có thể kết hợp, ví dụ bảng nguồn partition theo tháng còn Spring Batch worker theo ngày/giờ. Nếu điều kiện query hỗ trợ **partition pruning**, DB có thể giảm I/O. Nhưng nếu tạo nhiều worker quét cùng một physical partition nóng, tranh chấp vẫn xuất hiện.

## 13. Cursor, paging và thứ tự đọc ổn định

Một window có thể có hàng triệu item. Reader vẫn cần chiến lược lấy dữ liệu và checkpoint.

**JdbcCursorItemReader:**
- Đọc từ ResultSet/cursor, thường giữ tài nguyên truy vấn/connection trong suốt việc đọc.
- Có thể phù hợp khi driver streaming tốt và số reader đồng thời được kiểm soát.
- Dùng state đọc/position để restart theo cơ chế của ItemStream.
- Cần chú ý snapshot, transaction isolation, cursor lifetime, DB timeout và driver fetch size.

**JdbcPagingItemReader:**
- Chia truy vấn thành trang và thường cần sort key đủ ổn định/duy nhất.
- Có overhead query theo trang nhưng phù hợp với một số nguồn và cách reconnect.
- Nếu bản ghi mới/chỉnh sửa xuất hiện trong lúc quét, paging cũng có thể bị dịch vị trí hoặc đổi thứ tự.
- Page size không phải commit interval, và các sort key cần được định nghĩa cẩn thận.

Với timestamp trùng nhau, **ORDER BY occurred_at** chưa đủ để xác định thứ tự giữa các bản ghi. Thêm khóa phụ duy nhất như `id` giúp tạo thứ tự tổng:

~~~sql
ORDER BY occurred_at ASC, id ASC
~~~

Nếu xây keyset pagination riêng, cần so đồng thời cả cặp:

~~~sql
WHERE occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive
  AND (
        occurred_at > :lastOccurredAt
        OR (
             occurred_at = :lastOccurredAt
             AND id > :lastId
           )
      )
ORDER BY occurred_at, id
LIMIT :pageSize;
~~~

Mẫu keyset minh họa cần xử lý riêng **trang đầu tiên** khi chưa có last key và phải lưu checkpoint của cặp `(occurred_at, id)` theo đúng transaction. Đừng tự thay reader của Spring Batch bằng một truy vấn keyset mà không thiết kế trạng thái restart.

## 14. Snapshot và watermark: dữ liệu có đứng yên hay không?

Time window chỉ xác định **bản ghi nào đủ điều kiện theo timestamp**. Nó không bảo đảm những bản ghi đó đã có mặt trong DB tại thời điểm job bắt đầu hoặc giữ nguyên cho đến cuối job.

### 14.1. Nguồn append-only đã chốt

Nếu nguồn có dữ liệu bất biến và cửa sổ đã đóng, các worker có thể đọc các time window độc lập. Đây là trường hợp dễ nhất.

### 14.2. Nguồn tiếp tục có sự kiện mới

Giả sử job xử lý event time `[00:00,06:00)` lúc 06:10. Một event xảy ra lúc 05:55 nhưng đến nguồn lúc 06:30: nó **không tồn tại** khi job quét lúc 06:10. Nó sẽ bị bỏ lỡ nếu hệ thống coi window đã xử lý xong vĩnh viễn.

Các chính sách có thể chọn:

- **Watermark/delay:** chỉ xử lý các window được coi là đủ ổn định sau một khoảng trễ đã thỏa thuận.
- **Ingestion cutoff:** chốt `ingested_at <= cutoff` cùng event-time window để định nghĩa snapshot logic của đợt nạp.
- **Replay/backfill:** chạy lại các window cũ có kiểm soát và ghi idempotent.
- **Versioned updates:** nếu event thay đổi nội dung, dùng version hoặc thời điểm cập nhật hợp lệ khi hợp nhất.
- **Change Data Capture hoặc reconciliation:** theo dõi dữ liệu đến sau để cập nhật kết quả.

**Watermark không phải cam kết rằng sẽ không bao giờ có event muộn hơn.** Nó là chính sách về mức trễ chấp nhận được; late data vượt watermark phải có quy trình nghiệp vụ rõ.

### 14.3. Ingestion cutoff có giới hạn

Giả sử tất cả worker dùng cùng một cutoff đã chốt:

~~~sql
SELECT id, occurred_at, amount_cents
FROM source_events
WHERE occurred_at >= :fromInclusive
  AND occurred_at < :toExclusive
  AND ingested_at < :ingestionCutoff
ORDER BY occurred_at, id;
~~~

Điều kiện này giúp định nghĩa tập record theo thời điểm ingest **nếu ingested_at được ghi ổn định và việc xuất hiện/commit record phù hợp với cutoff**. Nó **không mặc nhiên tạo snapshot database**: một transaction ghi muộn nhưng gắn ingested_at cũ, hoặc một bản ghi bị update/delete, vẫn có thể làm tập kết quả thay đổi. Với yêu cầu snapshot nghiêm ngặt, cân nhắc transaction snapshot/consistent export, staging table bất biến hoặc nguồn versioned.

## 15. Rerun, backfill và time window chồng lấn có chủ đích

Không phải mọi window chồng lấn đều là bug. Một số kiến trúc cố ý **đọc lại cửa sổ gần nhất** để nhận late events. Nhưng lúc đó phải phân biệt:

- **Chồng lấn giữa partition của cùng một lần chạy:** thường là lỗi vì hai worker cùng sở hữu một item.
- **Chồng lấn giữa các lần chạy/backfill:** có thể là chính sách hợp lệ nếu writer idempotent và việc đối soát rõ ràng.

Ví dụ mỗi ngày chạy lại hai ngày gần nhất:

~~~text
Run A: [2026-11-01, 2026-11-03)
Run B: [2026-11-02, 2026-11-04)
                   ^^^
      Window 02/11 được xử lý lại có chủ đích
~~~

Trong trường hợp này, `event_id` duy nhất hoặc `(source_id, source_version)` cần được dùng để xác định bản ghi đã xử lý. Không dựa vào `runId` làm khóa duy nhất của bản ghi nghiệp vụ nếu replay sẽ tạo ra bản ghi trùng qua mỗi lần chạy.

### Khi nào phải dùng JobInstance mới?

Nếu chủ đích thay đổi tập input, ví dụ backfill một kỳ khác hoặc chạy lại với rule/version mới, thường nên tạo JobInstance/JobParameters thích hợp và lưu lịch sử đối soát rõ. **Restart** là tiếp tục một công việc logic đã xác định; không nên âm thầm đổi `windowEnd` hoặc cách chia khi restart rồi coi đó là cùng công việc.

Khi cần thay đổi thuật toán partitioning đã chạy một phần, phải có kế hoạch migration/reconciliation, không chỉ đổi code rồi restart trên metadata cũ.

## 16. Retry, rollback và idempotency theo window

Partitioner có thể tạo window hoàn hảo nhưng worker vẫn lỗi giữa chunk.

### Ví dụ lỗi sau commit

1. Worker A xử lý window 00:00–06:00.
2. Một chunk đã ghi thành công xuống DB.
3. Worker/JVM bị hủy trước khi trạng thái phản hồi về manager.
4. Manager hoặc quy trình restart xác định còn phần việc cần phục hồi.
5. Những item đã ghi có thể được đọc/xử lý lại tùy checkpoint và cơ chế điều phối.

Cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| **ExecutionContext** | Input window và state checkpoint của StepExecution |
| **ItemStream** | Quản lý `open/update/close` để restart reader/writer khi phù hợp |
| **Transaction manager** | Commit/rollback các resource được quản lý trong transaction |
| **JobRepository** | Metadata thực thi và trạng thái có thể khôi phục |
| **Idempotent writer** | Đảm bảo lặp lại thao tác ghi không làm sai kết quả nghiệp vụ |
| **Đối soát dữ liệu** | Chứng minh record cuối kỳ đúng, không trùng/thiếu |

`COMPLETED` của StepExecution cho biết trạng thái thực thi theo framework, **không tự chứng minh side effect ngoài transaction được ghi exactly once**. Với API ngoài, có thể cần idempotency key, outbox hoặc cơ chế bù trừ.

### Tránh xử lý lại một partition đang chạy

Nếu worker remote mất kết nối nhưng vẫn đang thực thi, việc giao lại cùng `StepExecution` cho JVM khác thiếu kiểm soát có thể tạo truy cập đồng thời vào cùng phạm vi. Phải xem trạng thái JobRepository, heartbeat/timeout, cơ chế partition handler và thiết kế sở hữu phần việc.

## 17. Thread safety theo từng mô hình scaling

Một phương pháp chia time window có thể được dùng trong nhiều topology, nhưng thread safety không giống nhau.

| Mô hình | Time window nằm ở đâu? | Rủi ro nổi bật |
| --- | --- | --- |
| **Step tuần tự** | Reader đọc lần lượt nhiều window | Khó tận dụng nhiều CPU; đơn giản để debug |
| **Multi-threaded step** | Một StepExecution, nhiều chunk threads có thể đọc chung | Reader mutable/cursor, thứ tự commit/checkpoint |
| **Parallel steps** | Mỗi flow/step có thể được giao kỳ thời gian khác | Các flow có thể cùng ghi đích hoặc có dependency |
| **Local partitioning** | Mỗi partition có StepExecution và reader @StepScope | DB chung, skew, writer singleton, metadata |
| **Remote partitioning** | Mỗi worker JVM tự đọc một window | Network/điều phối, JobRepository, nguồn/đích chung |
| **Remote chunking** | Manager thường đọc rồi gửi chunk | Không mặc nhiên chia reader theo time window ở worker |

Với dataset có khóa timestamp rõ và reader giữ cursor, **local/remote partitioning** thường dễ phân định quyền sở hữu hơn việc dùng chung một reader trong multi-threaded step. Tuy nhiên `@StepScope` gắn với **StepExecution**, không phải từng chunk thread. Nếu worker step tự bật multi-threading bên trong partition, lại cần đánh giá thread safety của reader/writer.

## 18. Remote partitioning: giữ hợp đồng window khi scale out

Giả sử một JVM đã hết CPU nhưng DB nguồn chịu được nhiều reader theo time window. Remote partitioning cho phép dùng chính **Partitioner** tạo các khoảng rồi điều phối worker JVM khác nhau.

~~~mermaid
flowchart LR
    M["Manager: tạo time windows"] --> Q[["Request channel"]]
    Q --> W1["Worker JVM 1: window A"]
    Q --> W2["Worker JVM 2: window B"]
    Q --> W3["Worker JVM 3: window C"]
    W1 --> D[("Nguồn & đích")]
    W2 --> D
    W3 --> D
    R[("JobRepository bền vững")] --- M
    R --- W1
    R --- W2
    R --- W3
~~~

Worker nhận yêu cầu StepExecution, đọc `fromInclusive`/`toExclusive` từ ExecutionContext rồi chạy cùng worker step. Các JVM không chia sẻ Java heap nhưng vẫn:

- Truy vấn cùng database nguồn; nhiều worker có thể gây full scan/connection wait.
- Ghi cùng bảng đích và index.
- Cập nhật metadata trong JobRepository.
- Chịu chi phí dispatch, serialization và giám sát message.
- Cần idempotency và kiểm soát request chạy lại.

**Không nên chuyển sang remote chỉ để có số worker lớn hơn.** Trước tiên đo throughput của reader/DB đích và xác nhận giới hạn của một JVM. Nếu DB đã bão hòa với bốn worker local, nhiều JVM có thể chỉ làm thời gian chờ và rollback tăng.

## 19. Capacity planning: số partition, số worker và SLA

Giả sử một batch có tổng **N** bản ghi, mỗi worker xử lý được **r** item/s khi chạy một mình và có **p** worker song song. Giới hạn lý tưởng của bước xử lý là `p × r`, nhưng throughput end-to-end còn bị giới hạn bởi nguồn/đích:

\[
R_{\mathrm{job}}\leq
\min(p\,r,R_{\mathrm{read}},R_{\mathrm{write}})
\]

Công thức giả định mỗi input tạo một output và các throughput ở cùng đơn vị; nếu processor lọc/sinh thêm item phải quy đổi. Ngoài ra worker có thể chậm đi do contention khi tăng `p`.

### Ví dụ giới hạn DB đích

- Mỗi worker: tối đa 3.000 item/s khi chạy riêng.
- Bốn worker: năng lực tính toán lý tưởng 12.000 item/s.
- DB nguồn: tối đa 15.000 item/s cho workload tương ứng.
- DB đích: tối đa 9.000 item/s.

Khi đó:

\[
R_{\mathrm{job}}\leq\min(12.000,15.000,9.000)
=9.000\ \mathrm{item/s}
\]

Thêm worker thứ năm hoặc thứ sáu không tự vượt trần ghi 9.000 item/s.

### Giới hạn ở partition chậm nhất

Nếu một partition có 2 triệu item, các partition còn lại chỉ 100 nghìn item, thời gian job có thể bị partition lớn quyết định. Số partition nên đủ để cân bằng, nhưng tăng quá nhiều lại tốn tạo StepExecution, mở cursor và cập nhật JobRepository.

### Tổng ngân sách kết nối

Nếu mỗi worker JVM có pool tối đa 10 connection và có sáu JVM, tổng hạn mức cấu hình từ các worker có thể là **60 connection**, chưa tính manager và ứng dụng khác. Đó không phải số active connection thực. Cần đo connection wait, CPU DB, lock wait và throughput để chọn mức concurrency chấp nhận được.

## 20. Quan sát time-based partitions trong production

Một hệ thống time partitioning phải có metric theo **JobExecution**, **StepExecution**, window và worker để phát hiện lỗi ở ranh giới hoặc straggler.

| Metric | Ý nghĩa |
| --- | --- |
| `fromInclusive`, `toExclusive` | Phạm vi mà worker thực sự nhận |
| `readCount`, `writeCount`, `filterCount` | Kết quả đọc/ghi của mỗi partition |
| `commitCount`, `rollbackCount`, skip/retry | Dấu hiệu fault tolerance và chi phí phục hồi |
| Partition elapsed time | Cửa sổ nặng/chậm nhất |
| SQL p95 latency, rows scanned | Có index/pruning phù hợp không? |
| DB connection wait, lock wait | Nguồn/đích có bão hòa khi tăng worker? |
| Heap/GC, CPU của worker | Giới hạn JVM và chi phí reader/processor |
| Queue depth/age (remote) | Worker có chờ request hoặc broker tồn đọng không? |
| Số event late và số event replay | Chính sách watermark có đáp ứng thực tế? |
| Số business key thiếu/trùng | Tính đúng dữ liệu sau job và restart |

Ví dụ log có cấu trúc:

~~~text
jobExecutionId=5310
stepExecutionId=5412
partitionName=time-0007
fromInclusive=2026-11-02T18:00:00Z
toExclusive=2026-11-03T00:00:00Z
worker=worker-jvm-02
readCount=420000
writeCount=420000
rollbackCount=0
elapsedSeconds=77
status=COMPLETED
~~~

Các số liệu chỉ minh họa. Khi xuất metric từ Prometheus hoặc hệ tương tự, tránh dùng mọi `stepExecutionId` hay giá trị timestamp động làm nhãn có cardinality vô hạn; có thể ghi ID chi tiết vào log/traces và xuất histogram theo nhóm window phù hợp.

## 21. Tình huống thực tế: 24 triệu sự kiện trong hai ngày

Một hệ thống phân tích phải xử lý **24 triệu sự kiện** của 48 giờ gần nhất. Dữ liệu có `occurred_at` chuẩn UTC và ID duy nhất; sau khi chốt ingestion cutoff, nguồn được xem là ổn định cho đợt xử lý. SLA là **25 phút** tính từ thời điểm bắt đầu job đến khi hoàn thành.

### Bước 1 — Tính throughput yêu cầu

\[
R_{\mathrm{required}}=
\frac{24.000.000}{25\times60}
=16.000\ \mathrm{item/s}
\]

Cần có dư địa cho khởi tạo, metadata và lỗi, nên mức mục tiêu vận hành nên cao hơn cận lý tưởng này.

### Bước 2 — Chia thành tám window sáu giờ

~~~text
time-0000: [D1 00:00, D1 06:00)
time-0001: [D1 06:00, D1 12:00)
time-0002: [D1 12:00, D1 18:00)
time-0003: [D1 18:00, D2 00:00)
time-0004: [D2 00:00, D2 06:00)
time-0005: [D2 06:00, D2 12:00)
time-0006: [D2 12:00, D2 18:00)
time-0007: [D2 18:00, D3 00:00)
~~~

Tất cả mốc thuộc **UTC** và cận trên loại trừ. Đây là ví dụ logic, D1–D3 là các ngày kế tiếp.

### Bước 3 — Đo bottleneck trước khi tăng worker

Kết quả benchmark **giả định**:

| Cấu hình | Throughput toàn job | Thời gian tối thiểu ước lượng | Nhận xét |
| --- | ---: | ---: | --- |
| Step tuần tự | 5.000 item/s | 80 phút | Chưa đạt SLA |
| 2 partition workers local | 9.000 item/s | 44,4 phút | Tăng nhưng chưa đủ |
| 4 partition workers local | 15.000 item/s | 26,7 phút | Gần SLA, còn thiếu |
| 8 workers remote | 17.500 item/s | 22,9 phút | Vượt mức lý tưởng tối thiểu |
| 12 workers remote | 17.700 item/s | 22,6 phút | Lợi ích biên rất nhỏ |

Thời gian trong bảng là phép chia `N/throughput` và không phải cam kết job hoàn thành đúng mức ấy; khi throughput được đo cho toàn job thì còn phải xác nhận cách lấy mẫu và overhead. Mọi số liệu đều **giả định**, không đại diện cho hiệu năng mặc định của Spring Batch.

Dữ liệu cho thấy tăng từ 8 lên 12 worker chỉ thêm khoảng 1,1% throughput; cần xem DB I/O, connection và lock trước khi mở rộng nữa.

### Bước 4 — Phát hiện window nặng

Một window 18:00–00:00 chứa 8 triệu event, các window khác chia 16 triệu event. Bốn worker có thể hoàn thành phần lớn dữ liệu sớm nhưng chờ window nặng.

Giải pháp cân nhắc:

- Tách riêng window nặng thành 3 hoặc 6 window nhỏ hơn, vẫn dùng `[start,end)`.
- Tạo histogram theo giờ để chọn cận gần cân bằng số record.
- Giữ tên partition và danh sách cận **được chốt** trước khi chạy/restart.
- Xem các window quá nhỏ có gây quá nhiều StepExecution và cursor không.

Nếu dùng thuật toán tự cân bằng từ COUNT theo DB, quyết định chia cần được lưu/giữ ổn định, không tính lại theo dữ liệu mới ở lần restart.

### Bước 5 — Kiểm tra lỗi và late events

Giả lập kill một worker giữa chunk, restart và đối soát `event_id`. Sau khi job hoàn tất, một số event thuộc ngày trước đến muộn. Hệ thống áp dụng backfill cho window cũ với writer idempotent, giữ audit trail về lần chạy và cutoff.

**Kết luận tình huống:** giá trị của time partitioning đến từ **phạm vi dữ liệu có thể phân chia đúng và đọc hiệu quả**, không chỉ từ việc chạy nhiều JVM. Cách chia không cân bằng, DB bão hòa hoặc input thay đổi có thể triệt tiêu lợi ích.

## 22. Kịch bản kiểm thử bắt buộc

### 22.1. Unit test thuật toán chia window

Với input `[00:00,12:30)` và width sáu giờ, kỳ vọng:

| Partition | Cận dưới | Cận trên |
| --- | --- | --- |
| 0 | 00:00 | 06:00 |
| 1 | 06:00 | 12:00 |
| 2 | 12:00 | 12:30 |

Kiểm tra:

- Partition đầu có from đúng start.
- Mỗi end bằng from của partition kế tiếp.
- Partition cuối có end đúng `windowEnd`.
- Không có window rỗng hoặc `from >= to`.
- `windowStart >= windowEnd` fail rõ.
- Cùng JobParameters tạo **cùng tên và cùng cận** khi gọi lại.

Ví dụ một hàm assertion độc lập với DB:

~~~java
static void assertContiguous(
        java.util.List<java.time.Instant[]> windows,
        java.time.Instant expectedStart,
        java.time.Instant expectedEnd) {

    if (windows.isEmpty()) {
        throw new AssertionError("No windows");
    }

    java.time.Instant cursor = expectedStart;
    for (java.time.Instant[] w : windows) {
        if (!w[0].equals(cursor) || !w[0].isBefore(w[1])) {
            throw new AssertionError(
                    "Gap/overlap or empty partition");
        }
        cursor = w[1];
    }

    if (!cursor.equals(expectedEnd)) {
        throw new AssertionError("Wrong final boundary");
    }
}
~~~

Đây là helper minh họa; khi dùng với Partitioner thật cần chuyển Map các ExecutionContext sang danh sách window có thứ tự trước khi gọi.

### 22.2. Boundary và precision

Tạo ba event có timestamp:

~~~text
event A: 05:59:59.999999 UTC
event B: 06:00:00.000000 UTC
event C: 06:00:00.000001 UTC
~~~

Với hai window `[00:00,06:00)` và `[06:00,12:00)`, A thuộc window đầu; B và C thuộc window sau. Dùng kiểu timestamp và precision thực tế của DB/driver để đối chiếu.

### 22.3. Múi giờ và DST

- Một ngày `Asia/Ho_Chi_Minh` phải bắt đầu theo 00:00 local, không phải 00:00 UTC.
- Ngày chuyển DST ở vùng có DST có thể dài 23/25 giờ.
- Xác nhận không có window bị lặp ở giờ đồng hồ quay lại.
- So sánh `Instant` và offset khi log; không chỉ so chuỗi local time.

### 22.4. Retry/restart

1. Chạy vài chunk, kill một worker và kiểm tra state.
2. Khởi động lại bằng đúng JobParameters/partition input.
3. Đối soát business key, số record và giá trị đầu ra.
4. Thử worker commit thành công nhưng mất xác nhận.
5. Thử một event đến muộn sau cutoff và quy trình backfill.
6. Thử DB timeout, retry/backoff, deadlock và lỗi payload.
7. Thử worker khác JVM cùng chạy một StepExecution thiếu kiểm soát; thiết kế phải ngăn hoặc phát hiện tình huống này.

### 22.5. Hiệu năng

So sánh cùng snapshot dữ liệu:

- Step tuần tự.
- Local partitioning 2, 4, 8 threads.
- Remote partitioning nếu một JVM là bottleneck thật.
- Window theo giờ/ngày và window cân bằng từ histogram.
- Query plan, rows scanned, DB connection wait, partition elapsed time.
- Throughput và total elapsed time **cùng** tính đúng sau fault injection.

Không cùng lúc thay DB index, chunk size, số worker và window width rồi kết luận nguyên nhân tăng tốc.

## 23. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Mỗi ngày là một partition thì tải sẽ đều.” | Số event mỗi ngày có thể rất lệch; cần đo phân bố. |
| “BETWEEN hai mốc liên tiếp không gây trùng.” | BETWEEN thường bao gồm hai cận; dùng `>= from AND < to`. |
| “Kết thúc ngày là 23:59:59.999.” | Precision/timezone thay đổi; dùng đầu ngày kế tiếp làm cận trên loại trừ. |
| “Ngày địa phương luôn dài 24 giờ.” | DST có thể tạo ngày 23 hoặc 25 giờ. |
| “Event time và ingestion time thay thế được nhau.” | Chúng đại diện hai khái niệm nghiệp vụ và late-arrival khác nhau. |
| “@StepScope cho reader tự chia dữ liệu.” | Partitioner phải tạo context, reader phải áp điều kiện SQL. |
| “GridSize(8) chắc chắn tạo tám partition.” | Số partition thực tùy logic Partitioner; ví dụ sáu giờ không dùng gridSize. |
| “Thêm partition không bao giờ làm chậm.” | Metadata, connection, query và DB contention có thể tăng. |
| “Reader restartable thì nguồn cập nhật liên tục vẫn đúng.” | Checkpoint phụ thuộc tập dữ liệu/thứ tự; cần snapshot hoặc chiến lược thay đổi dữ liệu. |
| “Chạy lại window cũ chắc chắn tạo duplicate.” | Có thể replay an toàn nếu writer idempotent và business semantics rõ. |
| “Time partitioning và table partitioning trong DB là một.” | Một bên chia StepExecution, một bên chia lưu trữ vật lý. |
| “Remote partitioning làm DB nguồn tự nhanh hơn.” | Nhiều worker vẫn dùng cùng DB và có thể gây nghẽn. |
| “Job COMPLETED chứng minh không mất event late.” | Cần chính sách watermark/backfill và đối soát dữ liệu. |

## 24. Checklist thiết kế time-based partitioning

- [ ] Đã chọn rõ trục thời gian: event, ingestion, creation, update hay business date.
- [ ] Xác định business timezone/ZoneId và quy tắc DST nếu dùng ngày lịch.
- [ ] Dùng window `[fromInclusive,toExclusive)` không chồng lấn trong cùng lần chạy.
- [ ] Cận thời gian có precision tương thích DB và JDBC driver.
- [ ] JobParameters/chính sách cutoff ổn định qua restart.
- [ ] Tên partition deterministic; ExecutionContext chỉ giữ input nhỏ cần thiết.
- [ ] Reader @StepScope nhận đúng context, validate `from < to`.
- [ ] SQL áp dụng đúng cặp cận và có `ORDER BY` đủ ổn định cho reader/checkpoint.
- [ ] Query plan/index/table pruning được kiểm tra bằng dữ liệu thực.
- [ ] Đã đo mật độ record theo window và đánh giá skew/straggler.
- [ ] Số partition, worker concurrency, chunk size và connection pool được tune độc lập.
- [ ] Không bật multi-threaded chunk trong cùng partition nếu reader stateful chưa an toàn.
- [ ] Có chính sách snapshot/watermark cho late-arriving và dữ liệu thay đổi.
- [ ] Backfill/rerun có idempotent writer và quy trình đối soát.
- [ ] Không thay partition name/range tùy ý khi restart cùng JobInstance.
- [ ] Đã thử kill worker, rollback, retry và mất phản hồi trong mô hình phân tán.
- [ ] Theo dõi read/write count, elapsed time từng partition, DB wait và throughput toàn job.
- [ ] Đảm bảo SLA và chi phí tài nguyên hợp lý trước khi tăng số worker JVM.

## 25. Câu hỏi tự kiểm tra

**1. Vì sao window theo thời gian nên dùng cận trên loại trừ?**

Để một event có timestamp đúng ở ranh giới chỉ nằm trong window kế tiếp. Hai khoảng `[00:00,06:00)` và `[06:00,12:00)` không trùng nhau và vẫn phủ đủ mốc 06:00.

**2. Nếu yêu cầu là “ngày theo giờ Việt Nam”, có nên chia theo 00:00 UTC không?**

Không. Cần dùng `LocalDate` và `ZoneId` nghiệp vụ để lấy đầu ngày local và đầu ngày kế tiếp, rồi chuyển sang Instant dùng trong truy vấn.

**3. Vì sao chia theo updated_at có rủi ro khi nguồn đang thay đổi?**

Một bản ghi có thể chuyển từ window này sang window khác khi timestamp được cập nhật, dẫn tới đọc trùng hoặc bỏ sót theo thời điểm quét. Cần snapshot, CDC hoặc chiến lược versioning thích hợp.

**4. gridSize = 8 nhưng Partitioner chia mỗi sáu giờ của 30 ngày. Có đúng tám partition không?**

Không. Nếu logic Partitioner bỏ qua gridSize, 30 ngày nhân bốn window/ngày sẽ tạo khoảng **120 partition**. Concurrency worker là một quyết định khác.

**5. Vì sao chỉ thêm index trên occurred_at chưa chắc giải quyết toàn bộ bottleneck?**

Còn phụ thuộc query plan, độ chọn lọc, sort key, bảng đích, connection pool, I/O và khả năng nhiều reader cùng quét nguồn. Cần benchmark tổng pipeline.

**6. Event xảy ra trước 06:00 nhưng tới DB lúc 06:30 sau khi window đã hoàn thành. Có cách nào xử lý?**

Dùng watermark/delay, ingestion cutoff kết hợp quy trình late event, hoặc backfill window cũ với writer idempotent. Phải xác định chính sách nghiệp vụ rõ ràng.

**7. Vì sao local partitioning thường dễ kiểm soát state của JdbcCursorItemReader hơn một multi-threaded step dùng chung reader?**

Mỗi partition có StepExecution và target reader @StepScope riêng, có phạm vi SQL và checkpoint riêng. Multi-threaded step có nhiều chunk threads cùng một StepExecution, có thể chia sẻ reader mutable.

**8. Nếu worker commit xong nhưng mất reply, có thể coi việc gửi lại request là vô hại không?**

Không. Phải xác minh StepExecution status và tránh thực thi song song cùng phần việc; writer cần idempotent vì đã có side effect được commit.

**9. Dùng UTC Instant chia mỗi 24 giờ và dùng LocalDate theo vùng có DST khác nhau ở đâu?**

Khoảng UTC 24 giờ luôn dài 24 giờ thực; một ngày lịch địa phương tại vùng có DST có thể dài 23 hoặc 25 giờ. Cần chọn theo ý nghĩa nghiệp vụ.

**10. Khi nào nên đổi từ local sang remote partitioning?**

Khi đã xác minh một JVM/host là giới hạn thật và nguồn/đích còn năng lực cho nhiều worker. Nếu DB đã bão hòa hoặc window skew chưa xử lý, remote không tự cải thiện.

---

**Ghi nhớ:** Chia dữ liệu theo thời gian hiệu quả khi mỗi worker sở hữu một **khoảng thời gian nửa mở, ổn định và truy vấn được bằng index**. Spring Batch cung cấp Partitioner, StepExecution/ExecutionContext và StepScope để thực thi nhiều phần việc; còn việc chọn timestamp, múi giờ, watermark, snapshot, idempotency và cân bằng tải là trách nhiệm thiết kế. Hãy đo bottleneck thực tế, giữ ranh giới ổn định qua restart và chỉ tăng worker khi **throughput cùng tính đúng dữ liệu** đều được chứng minh.
