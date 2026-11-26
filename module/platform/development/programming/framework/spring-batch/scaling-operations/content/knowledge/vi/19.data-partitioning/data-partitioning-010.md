# Tránh bỏ sót bản ghi ở biên khi chia dữ liệu trong Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **gap, overlap và off-by-one** ở ranh giới partition là lỗi tính đúng đắn, không đơn thuần là vấn đề hiệu năng.
- Sử dụng nhất quán quy ước **khoảng nửa mở** `[startInclusive, endExclusive)` cho ID, thời gian và các khóa có thứ tự.
- Chứng minh rằng một tập partition **bao phủ toàn bộ miền** và **không chồng lấn**, thay vì chỉ so sánh tổng số lượng xử lý.
- Nhận diện trường hợp biên khó: ID thưa, giá trị âm, `Long.MAX_VALUE`, partition rỗng, key không duy nhất, timestamp đồng giá trị, precision và múi giờ.
- Thiết kế snapshot/manifest ổn định khi dữ liệu nguồn còn thay đổi và hiểu tại sao `MAX(id)` không tự tạo point-in-time snapshot.
- Triển khai `Partitioner`, reader `@StepScope` và worker step minh họa bằng **Java 17 / Spring Batch 5.x** với predicate SQL đúng ranh giới.
- Phát hiện mất/trùng bản ghi bằng SQL, property-based test, kiểm thử crash/restart và đối soát khóa nghiệp vụ.
- Phân biệt **ranh giới partition** với **checkpoint trong partition**, kiểm soát idempotency và giới hạn tài nguyên khi scale-out.

## 1. Một bản ghi ở biên có thể làm sai toàn bộ job

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, một job cần xử lý hàng chục triệu sự kiện. Để tận dụng nhiều CPU và I/O, nhóm phát triển chia dữ liệu thành bốn khoảng rồi chạy song song bằng local partitioning hoặc remote partitioning.

Một lỗi phổ biến: manager tạo hai partition `[1,100]` và `[100,200]`, còn worker dùng SQL `BETWEEN startId AND endId`. Vì `BETWEEN` bao gồm **cả hai đầu**, bản ghi `id=100` nằm ở **cả hai** partition.

Một lỗi đối xứng: manager khai báo `[1,100)` và `[101,200)`. Khi worker dùng `id >= start AND id < end`, bản ghi `id=100` **không thuộc partition nào**.

| Phân công | Predicate thật | `id=100` | Kết quả |
| --- | --- | --- | --- |
| P0 `[1,100]`, P1 `[100,200]` | `BETWEEN start AND end` | Hai worker nhận | **Trùng** |
| P0 `[1,100)`, P1 `[101,200)` | `id >= start AND id < end` | Không worker nào nhận | **Thiếu** |
| P0 `[1,100)`, P1 `[100,201)` | `id >= start AND id < end` | Chỉ P1 nhận | **Đúng** |
| P0 `[1,101)`, P1 `[101,201)` | `id >= start AND id < end` | Chỉ P0 nhận | **Đúng** |

Bản ghi bị bỏ sót ở biên có thể làm sai tổng tiền, báo cáo tài chính, hóa đơn hoặc trạng thái giao dịch dù job được Spring Batch đánh dấu `COMPLETED`.

**Mục tiêu không phải chỉ để các worker “không đụng nhau”.** Mục tiêu là: *mỗi bản ghi thuộc snapshot đầu vào được xử lý đúng một miền công việc theo kế hoạch*, và mọi lần retry/restart vẫn tôn trọng kế hoạch đó.

## 2. Mô hình toán học: coverage, disjointness và ổn định

Gọi `S` là tập bản ghi hợp lệ của snapshot, `K(r)` là khóa phân vùng của bản ghi `r`, và các miền xử lý là `P0, P1, ..., Pn-1`.

Một thiết kế đúng cần ba bất biến:

1. **Coverage**: với mọi `r ∈ S`, tồn tại ít nhất một partition nhận `K(r)`.
2. **Disjointness**: với mọi `r ∈ S`, không có hai partition khác nhau cùng nhận `K(r)`, trừ khi nghiệp vụ chủ động thiết kế duplicate + dedup.
3. **Stability**: trong các attempt thuộc **cùng `JobInstance`**, tập `S`, tên partition và quy tắc phân công vẫn giữ cùng ý nghĩa.

Với khoảng nửa mở trên trục số:

~~~text
Miền toàn bộ: [1, 1001)

P0: [1,   251)
P1: [251, 501)
P2: [501, 751)
P3: [751,1001)

1               251             501             751            1001
|------- P0 -------|------ P1 ------|------ P2 ------|------ P3 ------|
                   ^               ^               ^
               chỉ P1 nhận     chỉ P2 nhận     chỉ P3 nhận
~~~

Điều kiện để các range **không rỗng, không có gap/overlap và bao phủ toàn miền** khi đã sắp xếp theo đầu khoảng:

~~~text
first.startInclusive == global.startInclusive

for i = 0 .. n-2:
    ranges[i].endExclusive == ranges[i+1].startInclusive

last.endExclusive == global.endExclusive

for each range:
    range.startInclusive < range.endExclusive
~~~

Nếu những bất biến này đúng, mỗi **giá trị khóa trong miền** thuộc đúng một range. Nếu khóa bản ghi **không duy nhất**, hai record có cùng khóa vẫn cùng vào một partition; cần kiểm tra riêng tính duy nhất của business key và ý nghĩa xử lý.

### Chứng minh nhanh tính đúng

Cho hai khoảng liền nhau `A=[a,b)` và `B=[b,c)`, với `a < b < c`. Mọi `x < b` trong miền của A không thể thuộc B vì B yêu cầu `x >= b`. Giá trị `x=b` không thuộc A vì A yêu cầu `x < b`, nhưng thuộc B vì B yêu cầu `x >= b`. Do đó không chồng lấn, không có lỗ hổng tại `b`.

Lập luận này áp dụng cho mọi cặp liền nhau theo quy tắc trên. Nhưng nó **chỉ chứng minh về biên**, chưa chứng minh nguồn không thay đổi hoặc worker thực thi và commit chính xác.

## 3. Chọn một quy ước và dùng nhất quán mọi nơi

Trong hệ có nhiều lớp — `Partitioner`, `ExecutionContext`, SQL, file range, message và checkpoint — không nên để mỗi lớp tự suy luận inclusive/exclusive.

**Quy ước khuyến nghị:**

- `startInclusive`: giá trị đầu **được bao gồm**.
- `endExclusive`: giá trị cuối **không bao gồm**.
- Tên `endExclusive` được ghi đầy đủ, tránh tên mơ hồ như `max`, `to`, `lastId`.
- Worker luôn dùng `key >= :startInclusive AND key < :endExclusive`.
- Tên partition và biên được lưu bền vững trong snapshot/manifest để restart.
- Các biên được kiểm tra trước khi dispatch, không phát hiện sau khi worker đã chạy hết mới sửa.

~~~sql
SELECT id, payload
FROM batch_order_snapshot
WHERE snapshot_id = :snapshotId
  AND id >= :startInclusive
  AND id < :endExclusive
ORDER BY id;
~~~

Ở đây `:param` là cú pháp bind của tầng ứng dụng như `NamedParameterJdbcTemplate`, không phải một phần của cú pháp SQL PostgreSQL thuần.

### Vì sao tránh `BETWEEN`?

~~~sql
-- Không nên cho các partition liền nhau nếu end là
-- đầu partition kế tiếp: BETWEEN bao gồm cả hai đầu.
WHERE id BETWEEN :startInclusive AND :endExclusive;

-- Nên:
WHERE id >= :startInclusive
  AND id < :endExclusive;
~~~

Nếu hệ thống nguồn buộc dùng miền đóng `[low,high]`, vẫn có thể dùng hai miền `[1,100]` và `[101,200]` khi khóa là số nguyên rời rạc. Tuy nhiên dễ sai khi đổi sang timestamp, số thực hoặc composite key. Khoảng nửa mở tạo ra một contract đơn giản, dễ hợp thành và thích hợp cho nhiều kiểu khóa có thứ tự.

### Không “bù 1” vào timestamp

Với thời gian, không nên viết `23:59:59.999` hoặc `endTime.minusNanos(1)` để tạo một thời điểm cuối “bao gồm”. Database có thể lưu microsecond thay vì nanosecond, hệ thống khác lưu millisecond. Dùng `timestamp >= from AND timestamp < to`, với `to` là đầu cửa sổ kế tiếp, tránh sai số precision.

## 4. Thiết kế manifest partition có thể kiểm chứng

Một bản **manifest** nên lưu input snapshot, tổng miền và ranh giới từng partition. Dùng PostgreSQL làm ví dụ:

~~~sql
CREATE TABLE batch_snapshot (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('BUILDING', 'READY', 'EXPIRED')),
    first_id BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL
        CHECK (expected_count >= 0),
    CHECK (first_id < end_exclusive)
);

CREATE TABLE batch_order_snapshot (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_snapshot(snapshot_id),
    id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);

CREATE TABLE batch_partition_manifest (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_snapshot(snapshot_id),
    partition_name VARCHAR(100) NOT NULL,
    start_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL
        CHECK (expected_count >= 0),
    PRIMARY KEY (snapshot_id, partition_name),
    CHECK (start_inclusive < end_exclusive)
);

CREATE TABLE batch_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);
~~~

Manifest minh họa có toàn miền `[1,1001)`:

~~~sql
INSERT INTO batch_snapshot(
    snapshot_id, state, first_id, end_exclusive, expected_count)
VALUES ('snap-20261125-01', 'BUILDING', 1, 1001, 1000);

INSERT INTO batch_partition_manifest(
    snapshot_id, partition_name, start_inclusive, end_exclusive,
    expected_count)
VALUES
 ('snap-20261125-01', 'partition0000',   1,  251, 250),
 ('snap-20261125-01', 'partition0001', 251,  501, 250),
 ('snap-20261125-01', 'partition0002', 501,  751, 250),
 ('snap-20261125-01', 'partition0003', 751, 1001, 250);
~~~

Các `expected_count=250` chỉ đúng **nếu snapshot thực sự có đủ 1.000 ID liên tục**. Với dữ liệu ID thưa, phải tính từ `batch_order_snapshot` thay vì lấy độ rộng range. Trạng thái `BUILDING` ở ví dụ chưa cho worker chạy; quy trình capture phải ghi dữ liệu, kiểm chứng và chuyển `READY` **sau khi** mọi bất biến đạt yêu cầu.

**Đừng xem constraint `CHECK(start_inclusive < end_exclusive)` là đủ.** Nó chỉ kiểm tra từng hàng không rỗng; nó không chứng minh không có overlap giữa hai hàng, cũng không chứng minh đã bao phủ toàn bộ miền.

### Snapshot membership và nội dung

Khi worker chạy hàng giờ trên DB nguồn vẫn cập nhật, chỉ lưu `first_id` và `end_exclusive` chưa đủ. Một bản ghi ID cũ có thể bị update, delete hoặc một transaction insert ID thấp commit muộn. Để thật sự tái lập khi restart, cần **immutable materialized snapshot**, versioned file hoặc source cung cấp as-of/CDC guarantee đã được chứng minh.

`snapshotId` nên là **identifying `JobParameter`**. Một `JobInstance` chỉ dùng một snapshot/manifest ổn định; reprocess trên dữ liệu mới là một công việc logic khác.

## 5. Kiểm chứng bằng SQL trước khi công bố READY

Có hai lớp kiểm tra: kiểm tra **hình học các range** và kiểm tra **membership của bản ghi thật**.

### 5.1. Phát hiện gap và overlap giữa các range

~~~sql
WITH ordered AS (
    SELECT
        partition_name,
        start_inclusive,
        end_exclusive,
        LAG(end_exclusive) OVER (
            ORDER BY start_inclusive, end_exclusive, partition_name
        ) AS previous_end
    FROM batch_partition_manifest
    WHERE snapshot_id = :snapshotId
)
SELECT partition_name, previous_end, start_inclusive,
       CASE
           WHEN start_inclusive > previous_end THEN 'GAP'
           WHEN start_inclusive < previous_end THEN 'OVERLAP'
       END AS problem
FROM ordered
WHERE previous_end IS NOT NULL
  AND start_inclusive <> previous_end;
~~~

Kết quả kỳ vọng **0 hàng**. Tuy nhiên, nếu thiếu partition đầu tiên hoặc cuối cùng, truy vấn vẫn có thể trả 0; cần kiểm tra biên toàn miền.

### 5.2. Kiểm tra chính xác biên đầu/cuối và số lượng range

~~~sql
WITH bounds AS (
    SELECT
        MIN(start_inclusive) AS actual_first,
        MAX(end_exclusive) AS actual_end,
        COUNT(*) AS partition_count
    FROM batch_partition_manifest
    WHERE snapshot_id = :snapshotId
)
SELECT
    s.first_id,
    s.end_exclusive AS expected_end,
    b.actual_first,
    b.actual_end,
    b.partition_count
FROM batch_snapshot s
CROSS JOIN bounds b
WHERE s.snapshot_id = :snapshotId;
~~~

Giá trị `actual_first` phải bằng `first_id`, `actual_end` bằng `expected_end` và `partition_count > 0` (trừ khi hệ thống định nghĩa chính sách riêng cho snapshot rỗng). Kiểm tra `MIN/MAX` cần đi cùng kiểm tra adjacency ở mục 5.1; **min/max bằng nhau không tự chứng minh bên trong không có gap**.

### 5.3. Kiểm tra từng record thuộc chính xác một partition

~~~sql
WITH assignment_count AS (
    SELECT s.id,
           COUNT(p.partition_name) AS matching_partitions
    FROM batch_order_snapshot s
    LEFT JOIN batch_partition_manifest p
      ON p.snapshot_id = s.snapshot_id
     AND s.id >= p.start_inclusive
     AND s.id < p.end_exclusive
    WHERE s.snapshot_id = :snapshotId
    GROUP BY s.id
)
SELECT
    COUNT(*) FILTER (WHERE matching_partitions = 0)
       AS unassigned_records,
    COUNT(*) FILTER (WHERE matching_partitions > 1)
       AS multiply_assigned_records
FROM assignment_count;
~~~

Kỳ vọng:

~~~text
unassigned_records    = 0
multiply_assigned_records = 0
~~~

Đây là bài kiểm tra **mạnh hơn** tổng count: nó xác định chính xác record nào nằm ở 0, 1 hay nhiều range. Với hàng chục triệu record, truy vấn có thể tốn I/O; cần có chỉ số phù hợp, chiến lược kiểm chứng tại bước snapshot capture, và đối soát cuối job.

### 5.4. Đối chiếu expected_count theo từng partition

~~~sql
SELECT p.partition_name,
       p.expected_count,
       COUNT(s.id) AS actual_count
FROM batch_partition_manifest p
LEFT JOIN batch_order_snapshot s
  ON s.snapshot_id = p.snapshot_id
 AND s.id >= p.start_inclusive
 AND s.id < p.end_exclusive
WHERE p.snapshot_id = :snapshotId
GROUP BY p.partition_name, p.expected_count
HAVING COUNT(s.id) <> p.expected_count;
~~~

Kỳ vọng **0 hàng** sau khi `expected_count` được tính từ snapshot đã đóng. Kiểm tra này phát hiện count lệch, nhưng một mình nó **không thay thế** kiểm tra coverage/disjointness: các range chồng lấn có thể mang expected count đã tính theo cùng logic sai.

## 6. Java 17: Partitioner tạo khoảng nửa mở không có off-by-one

Khi input là một miền ID liên tục đã được chốt (không nhất thiết record ID liên tục), manager có thể chia theo **độ rộng miền**, rồi cho worker lọc theo predicate `[start,end)`.

Ví dụ dùng API của Spring Batch **5.x**:

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class HalfOpenRangePartitioner implements Partitioner {

    private final long firstInclusive;
    private final long endExclusive;

    public HalfOpenRangePartitioner(
            long firstInclusive, long endExclusive) {
        if (firstInclusive >= endExclusive) {
            throw new IllegalArgumentException("Empty or reversed range");
        }
        // Fail fast khi hiệu có thể overflow signed long.
        Math.subtractExact(endExclusive, firstInclusive);
        this.firstInclusive = firstInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long totalWidth =
                Math.subtractExact(endExclusive, firstInclusive);
        int partitions = (int) Math.min(totalWidth, (long) gridSize);
        long baseWidth = totalWidth / partitions;
        long remainder = totalWidth % partitions;
        long start = firstInclusive;

        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        for (int i = 0; i < partitions; i++) {
            long width = baseWidth + (i < remainder ? 1 : 0);
            long end = Math.addExact(start, width);

            ExecutionContext context = new ExecutionContext();
            context.putLong("startInclusive", start);
            context.putLong("endExclusive", end);
            result.put(String.format(Locale.ROOT, "partition%04d", i),
                       context);

            start = end;
        }

        if (start != endExclusive) {
            throw new IllegalStateException("Partition coverage mismatch");
        }

        return result;
    }
}
~~~

### Các thuộc tính cần kiểm chứng

- Mọi partition có `width > 0`; nếu miền chỉ có 3 giá trị nhưng `gridSize=8`, code tạo **3 partition**, không sinh năm miền rỗng.
- Các range nối tiếp: `end(i) == start(i+1)`.
- Giá trị đầu của partition đầu là `firstInclusive` và giá trị cuối của partition cuối là `endExclusive`.
- `Math.subtractExact` / `Math.addExact` giúp phát hiện tràn số thay vì âm thầm tạo boundary sai.
- Nếu ID có lỗ hổng, range vẫn đúng về **miền khóa**, nhưng số record mỗi worker có thể lệch lớn.
- `gridSize` là số partition mục tiêu, **không phải** số thread hoặc worker JVM đang chạy.
- Tên `partition0000`, `partition0001`… ổn định nếu cùng input và `gridSize`; **không thay `gridSize` khi restart cùng `JobInstance`** mà không có chiến lược bảo toàn mapping.

Đoạn code là lựa chọn cho **lần chia đầu** của một snapshot mới. Khi sản xuất, nên **persist boundary vào manifest** trước khi cho worker chạy. Khi restart, dùng lại mapping đã lưu thay vì gọi thuật toán với một số `gridSize` mới rồi tạo cùng tên nhưng phạm vi khác.

### Test nhanh bằng ví dụ

~~~java
var parts = new HalfOpenRangePartitioner(1, 11).partition(3);

// Có thể thu được:
// partition0000: [1,5)   -> 1,2,3,4
// partition0001: [5,8)   -> 5,6,7
// partition0002: [8,11)  -> 8,9,10
~~~

Không suy luận `partition0000` luôn rộng bằng các partition còn lại; phân phối phần dư làm một số miền nhiều hơn một giá trị, nhưng vẫn không có gap/overlap.

## 7. Biên khó: ID thưa, số âm, giá trị cực đại và miền rỗng

### 7.1. ID thưa không có nghĩa chia bị lỗi

Nguồn có ID:

~~~text
1, 2, 7, 9, 100, 101, 450, 900
~~~

Nếu chia `[1,901)` thành 3 khoảng theo **độ rộng số học**, các miền có thể chứa rất ít hoặc rất nhiều record khác nhau. Tính đúng vẫn đạt nếu mỗi ID thuộc đúng một khoảng; nhưng độ lệch tải gây **straggler**.

Có thể dùng thống kê/quantile hoặc manifest gom record theo **số lượng/cost thực tế** để cân bằng hơn. Khi thay cách chia, vẫn phải kiểm chứng biên và giữ mapping ổn định trong cùng job instance.

### 7.2. ID âm

Các partition không bắt buộc bắt đầu từ 0 hoặc 1. Với miền `[-10,11)`, phép chia nửa mở vẫn đúng. Không viết code giả định `id >= 0` nếu khóa nghiệp vụ cho phép số âm.

Khi chia **hash bucket**, chú ý `x % n` trong Java có thể âm với `x < 0`. Nếu dùng `Math.floorMod(id, bucketCount)` trong Java mà SQL dùng `id % bucketCount` không cùng semantics với số âm, bản ghi có thể không nằm đúng bucket. Cần test đồng nhất Java/SQL, tốt nhất dùng một quy tắc mapping được định nghĩa rõ ở **một nơi**.

### 7.3. `Long.MAX_VALUE` và tràn `endExclusive`

Cách “lấy `MAX(id) + 1` làm exclusive end” có thể tràn `long` khi `MAX(id)=Long.MAX_VALUE`. Khi đó end bị biến thành giá trị âm, có thể làm bỏ sót **toàn bộ miền cuối**.

Những lựa chọn an toàn:

- **Lấy boundary từ manifest** và bảo đảm exclusive end biểu diễn được trong kiểu được chọn.
- Nếu miền thực sự chứa `Long.MAX_VALUE`, dùng **kiểu số rộng hơn** (`BigInteger`/`NUMERIC`) cho tính biên và convert có kiểm tra, hoặc một cấu hình partition cuối dùng upper bound inclusive rõ ràng.
- Với key kiểu timestamp/UUID/string không có “kế tiếp +1” tự nhiên, đừng cố áp dụng phép cộng 1; dùng predicate theo khóa và boundary cho trước.

Không dùng `Math.min(maxId + 1, ...)` để chống tràn: phép cộng đã tràn **trước khi** `Math.min` xử lý.

### 7.4. Miền rỗng

Nếu snapshot không có record, `firstInclusive == endExclusive` không phù hợp với partition có width dương. Đây là một **trạng thái nghiệp vụ cần xử lý riêng**: sau bước kiểm tra input, cho job/step đi theo nhánh no-op, hoặc dùng một partition no-op có behavior đã được thử nghiệm với `PartitionHandler` thực tế.

Đừng mặc định mọi phiên bản/handler xử lý `Map.of()` rỗng theo đúng transition mong muốn; kiểm thử đường chạy không dữ liệu.

## 8. Reader Spring Batch phải dùng đúng predicate và context

Mỗi worker `StepExecution` nhận context chứa `snapshotId`, `startInclusive`, `endExclusive`. Bean `@StepScope` có thể bind các giá trị ấy khi worker bắt đầu.

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(
        String snapshotId, long id,
        long sourceVersion, String payload) {}

@Configuration
class BoundaryReaderConfiguration {

    @Bean("boundaryReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> boundaryReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['startInclusive']}") Long start,
            @Value("#{stepExecutionContext['endExclusive']}") Long end) {

        if (snapshotId == null || snapshotId.isBlank()
                || start == null || end == null
                || start >= end) {
            throw new IllegalArgumentException(
                    "Invalid snapshot or partition boundary");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("boundaryReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, source_version, payload
                    FROM batch_order_snapshot
                    WHERE snapshot_id = ?
                      AND id >= ? AND id < ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, start);
                    ps.setLong(3, end);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                        snapshotId,
                        rs.getLong("id"),
                        rs.getLong("source_version"),
                        rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

**Chú ý:**

- `@StepScope` tạo reader theo **worker `StepExecution`** trong partitioning; không phải mặc định mỗi Java thread ở mọi mô hình đều có reader riêng.
- `.name("boundaryReader")` xác định namespace checkpoint của reader trong `StepExecutionContext`.
- `.saveState(true)` cho phép `ItemStream` lưu tiến độ; reader phải được Step quản lý đúng lifecycle `open/update/close`.
- `ORDER BY id` duy nhất vì `(snapshot_id,id)` là primary key. Không có `ORDER BY` thì offset/checkpoint dễ sai ngay cả khi snapshot bất biến.
- Dùng prepared statement, **không** ghép trực tiếp boundary từ message vào câu SQL.
- Ví dụ giả định Spring Batch 5.x và datasource/transaction manager phù hợp, chưa bao gồm tất cả bean khởi tạo job.

### Đừng tự bù ranh giới trong worker

Nếu manager đã đặt `endExclusive=501`, worker không được viết `id <= 501` hoặc `id < 500`. Một lớp phải là **nguồn sự thật của quy ước biên**; tất cả reader, query kiểm tra và manifest cùng dùng quy tắc đó.

## 9. Ghép vào worker step và local partitioning

Spring Batch có thể chạy bốn partition đồng thời trong một JVM qua `TaskExecutorPartitionHandler`/API builder tương ứng, hoặc phân phối trên nhiều JVM qua remote partitioning. Dưới đây là wiring minh họa **Spring Batch 5.x** với `TaskExecutor` có giới hạn.

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class BoundaryPartitionJobConfiguration {

    @Bean("boundaryPartitioner")
    Partitioner boundaryPartitioner() {
        // Lấy các giá trị này từ manifest của snapshot đã chốt.
        return new HalfOpenRangePartitioner(1, 1001);
    }

    @Bean("boundaryWriter")
    ItemWriter<OrderRow> boundaryWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (OrderRow row : chunk) {
                jdbc.update("""
                    INSERT INTO batch_order_result(
                        snapshot_id, id, source_version, payload
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (snapshot_id, id) DO UPDATE
                    SET source_version = EXCLUDED.source_version,
                        payload = EXCLUDED.payload
                    WHERE (
                        batch_order_result.source_version,
                        batch_order_result.payload
                    ) IS DISTINCT FROM (
                        EXCLUDED.source_version, EXCLUDED.payload
                    )
                    """,
                    row.snapshotId(), row.id(),
                    row.sourceVersion(), row.payload());
            }
        };
    }

    @Bean("boundaryWorker")
    Step boundaryWorker(
            JobRepository repository,
            PlatformTransactionManager tx,
            @Qualifier("boundaryReader")
                JdbcCursorItemReader<OrderRow> reader,
            @Qualifier("boundaryWriter") ItemWriter<OrderRow> writer) {

        return new StepBuilder("boundaryWorker", repository)
                .<OrderRow, OrderRow>chunk(200, tx)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("boundaryExecutor")
    ThreadPoolTaskExecutor boundaryExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("boundary-");
        pool.initialize();
        return pool;
    }

    @Bean("boundaryManager")
    Step boundaryManager(
            JobRepository repository,
            @Qualifier("boundaryWorker") Step worker,
            @Qualifier("boundaryPartitioner") Partitioner partitioner,
            @Qualifier("boundaryExecutor") TaskExecutor executor) {

        return new StepBuilder("boundaryManager", repository)
                .partitioner("boundaryWorker", partitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("boundaryJob")
    Job boundaryJob(
            JobRepository repository,
            @Qualifier("boundaryManager") Step manager) {

        return new JobBuilder("boundaryJob", repository)
                .start(manager)
                .build();
    }
}
~~~

**Giả định:** bean `boundaryReader` từ mục 8, `OrderRow` và `HalfOpenRangePartitioner` từ các mục trước, `JobRepository`/`DataSource`/`JdbcTemplate`/`PlatformTransactionManager` từ cấu hình ứng dụng. `snapshotId` phải được truyền làm identifying job parameter, snapshot phải đã `READY`. Ví dụ local chia `[1,1001)` để dễ quan sát; production cần dùng **partition manifest đã persist** thay vì hardcode hoặc tính lại range theo dữ liệu đang thay đổi.

Writer dùng business key `(snapshot_id,id)` để replay cùng record giữ trạng thái cuối như cũ. Nếu có trigger audit, HTTP call, message publish hoặc phép cộng dồn, bản thân `UPSERT` chưa đủ đảm bảo mọi side effect idempotent; cần ledger/outbox hoặc giao thức nghiệp vụ riêng.

### Vì sao “không thiếu ở biên” còn cần checkpoint đúng?

Giả sử worker `partition0001` được giao `[251,501)` và đã commit đến ID 400. Khi restart, phải khôi phục **cả range ban đầu lẫn checkpoint reader trong range**. Nếu manager đổi `partition0001` thành `[301,551)` nhưng reader vẫn dùng checkpoint theo số item đọc trước đó, worker có thể bỏ sót `301..400` hoặc ghi chồng vùng của worker khác.

**Không đổi tên partition, boundary, snapshot hoặc cách sort đầu vào** của một `JobInstance` đang cần restart nếu chưa có cơ chế migration state được chứng minh đúng.

## 10. Timestamp: biên ngày, độ chính xác và múi giờ

Một workload xử lý sự kiện theo ngày dễ phát sinh off-by-one theo thời gian hơn ID.

Giả sử cần xử lý các event thuộc ngày **2026-11-25 theo múi giờ Việt Nam**. Cửa sổ nghiệp vụ là:

~~~text
Local start: 2026-11-25 00:00:00 +07:00
Local end:   2026-11-26 00:00:00 +07:00

Tương ứng UTC:
[start, end) =
[2026-11-24T17:00:00Z, 2026-11-25T17:00:00Z)
~~~

Predicate PostgreSQL:

~~~sql
SELECT event_id, event_at, payload
FROM event_snapshot
WHERE snapshot_id = :snapshotId
  AND event_at >= :fromInclusive
  AND event_at < :toExclusive
ORDER BY event_at, event_id;
~~~

**Không** dùng `event_at BETWEEN '2026-11-25 00:00' AND '2026-11-25 23:59:59.999'` làm cửa sổ cho timestamp có độ chính xác không chắc chắn. Event ở `23:59:59.999500` có thể bị bỏ sót; event ở đúng `00:00:00` ngày hôm sau cần vào cửa sổ kế tiếp, không vào cả hai.

### Chuyển từ ngày business sang Instant ở Java

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

record TimeWindow(Instant startInclusive, Instant endExclusive) {}

static TimeWindow businessDay(
        LocalDate date, ZoneId businessZone) {

    Instant start = date.atStartOfDay(businessZone).toInstant();
    Instant end = date.plusDays(1)
                      .atStartOfDay(businessZone)
                      .toInstant();

    return new TimeWindow(start, end);
}

// Ví dụ:
// businessDay(LocalDate.of(2026, 11, 25),
//             ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Định nghĩa **ZoneId của nghiệp vụ**, không lấy timezone mặc định của máy worker. Với vùng có daylight saving time (DST), một ngày địa phương có thể không dài đúng 24 giờ. Cách tính bằng đầu ngày kế tiếp theo `ZoneId` tránh giả định `start.plus(24h)` luôn là ranh giới ngày đúng.

### Timestamp đồng giá trị và checkpoint

Nhiều event có thể cùng `event_at`. Nếu paging chỉ dùng:

~~~sql
WHERE event_at > :lastEventAt
ORDER BY event_at
~~~

thì các event khác có **cùng timestamp** với event cuối trang trước có thể bị bỏ sót. Cần một khóa sắp xếp **duy nhất và ổn định**, ví dụ `(event_at,event_id)`:

~~~sql
SELECT event_id, event_at, payload
FROM event_snapshot
WHERE snapshot_id = :snapshotId
  AND event_at >= :fromInclusive
  AND event_at < :toExclusive
  AND (
       :lastEventAt IS NULL
       OR (event_at, event_id) >
          (:lastEventAt, :lastEventId)
      )
ORDER BY event_at, event_id
LIMIT :pageSize;
~~~

Ở đây `:lastEventAt`/`:lastEventId` phải cùng đại diện **khóa bản ghi đã được commit đầy đủ**, không đơn thuần là bản ghi cuối vừa đọc trước khi writer rollback. `lastEventId` có thể null ở trang đầu, nhưng nhánh `:lastEventAt IS NULL` cần được xử lý/typed parameter phù hợp với driver SQL; trong code thật có thể chọn hai câu SQL riêng cho page đầu và các page sau để tránh ambiguity của bind null PostgreSQL.

## 11. Khóa ghép và keyset pagination: không bỏ sót khi nhiều record cùng giá trị

Không chỉ timestamp: phân vùng theo tenant và order ID hoặc theo `(created_at,id)` là những tình huống **composite key**.

Ví dụ dữ liệu có khóa `(tenant_id, order_id)`:

~~~text
tenant=A: order 1, 2, 3
tenant=B: order 1, 2, 3
~~~

Nếu query trong partition chỉ `ORDER BY order_id`, thứ tự **không duy nhất trên toàn snapshot**. Reader có thể gặp nhiều record `order_id=2` của tenant khác nhau và skip sai khi trang trước kết thúc giữa nhóm đó.

Cách an toàn:

- Chọn **khóa sort duy nhất**, ví dụ `ORDER BY tenant_id, order_id`.
- Nếu phân vùng theo tenant, giữ predicate `tenant_id = :tenantId` và trong tenant dùng `order_id` duy nhất.
- Nếu cắt range trên **khóa ghép**, phải so sánh tuple theo cùng thứ tự và cùng collation:
  
~~~sql
SELECT tenant_id, order_id, payload
FROM order_snapshot
WHERE snapshot_id = :snapshotId
  AND (tenant_id, order_id) >=
      (:startTenant, :startOrder)
  AND (tenant_id, order_id) <
      (:endTenant, :endOrder)
ORDER BY tenant_id, order_id;
~~~

PostgreSQL hỗ trợ so sánh row-value theo thứ tự từ điển cho các kiểu có operator phù hợp. Nếu một thành phần khóa có `NULL`, semantics so sánh ba giá trị có thể làm bản ghi **không khớp điều kiện**. Cần khai báo khóa partition `NOT NULL`, hoặc định nghĩa riêng một miền cho bản ghi NULL.

### Offset pagination trên tập dữ liệu thay đổi

Dùng:

~~~sql
SELECT id
FROM live_order
ORDER BY id
OFFSET 100000 LIMIT 1000;
~~~

trên nguồn có insert/delete có thể khiến record dịch vị trí giữa các lần gọi. Với snapshot bất biến, offset paging dễ lý giải hơn nhưng có thể tốn chi phí skip lớn. Keyset pagination thường tốt hơn với source/index thích hợp, nhưng **keyset cũng cần snapshot ổn định và checkpoint sau commit**.

## 12. NULL, collation, hash và khóa không có thứ tự đơn giản

### 12.1. `NULL` không thuộc các range bằng so sánh thông thường

Trong SQL:

~~~sql
WHERE partition_key >= :startInclusive
  AND partition_key < :endExclusive
~~~

sẽ **không chọn** các hàng có `partition_key IS NULL`. Nếu nghiệp vụ cho phép null, cần chính sách rõ:

- Reject bản ghi không có partition key ở bước validate nguồn.
- Giao một **partition riêng** có predicate `partition_key IS NULL`.
- Chuẩn hóa một giá trị sentinel **chỉ khi không xung đột dữ liệu thật** và mọi thành phần dùng thống nhất.

Không tự hiểu null là 0 hoặc chuỗi rỗng trong một worker nhưng giữ null ở worker khác.

### 12.2. String range phụ thuộc collation

Chia key theo `'A' <= key < 'M'` và `'M' <= key < 'Z'` có thể sai khi source/worker/DB dùng collation khác nhau (case sensitivity, Unicode normalization). Cần dùng collation/encoding đã chốt, hoặc một khóa phân vùng kỹ thuật ổn định thay cho tên người hoặc chuỗi locale-dependent.

Với UUID không có quy tắc “cộng 1”, có thể phân công bằng prefix/hash bucket hoặc số thứ tự trong manifest thay vì cố tạo `uuid + 1`.

### 12.3. Hash partitioning cũng có “biên”

Với hash bucket `0..N-1`, nguyên tắc là **mọi record phải đi vào đúng một bucket**:

~~~text
bucket = floorMod(stableHash(businessKey), N)
~~~

Không dùng `String.hashCode()` của Java rồi tùy tiện thay bằng một hàm hash khác của PostgreSQL; hash function, encoding, overflow và salt/version phải thống nhất. Với ID số nguyên, `Math.floorMod(id, N)` trong Java và biểu thức SQL phải được thiết kế cùng semantics, nhất là với số âm:

~~~sql
-- PostgreSQL: normalization cho id âm, N > 0.
WHERE ((id % :bucketCount) + :bucketCount) % :bucketCount
      = :bucketIndex;
~~~

Hash bucket không phải range; nó có thể khó tận dụng index range và phân bổ không đều theo tính chất key. Đổi `N` giữa các attempt sẽ đổi mapping gần như toàn bộ dữ liệu, làm restart/checkpoint sai nếu không persist theo version.

## 13. Record “đến muộn” là lỗi biên thời gian khác với off-by-one

Một job chốt dữ liệu cho `[00:00,01:00)` vào lúc 01:00, nhưng sự kiện xảy ra lúc 00:59:58 được ingest lúc 01:02. So sánh timestamp chính xác vẫn không làm event xuất hiện trong input tại lúc snapshot được tạo.

Cần phân biệt:

- **Event time**: thời điểm sự kiện thực sự xảy ra theo nguồn nghiệp vụ.
- **Ingest/processing time**: thời điểm hệ thống nhận hoặc xử lý event.
- **Capture/snapshot time**: thời điểm tạo tập dữ liệu đầu vào.
- **Watermark**: cam kết hoặc giả định mức độ hoàn tất của sự kiện tới một mốc event time.

### Chiến lược cho late arrival

| Chiến lược | Cách làm | Đánh đổi |
| --- | --- | --- |
| Chờ một **grace period** | Chốt cửa sổ sau một khoảng trễ có định nghĩa | Tăng latency trước khi có báo cáo |
| **Watermark theo nguồn** | Chốt khi nguồn cam kết event đến đủ tới mốc | Cần protocol/guarantee thực sự của nguồn |
| **Delta/backfill job** | Tạo snapshot delta riêng cho late events | Writer/aggregate phải idempotent và đối soát |
| **Recompute window** | Chạy lại trọn cửa sổ với input version mới | Tốn tài nguyên; cần quy tắc thay thế kết quả |
| **CDC/temporal history** | Chụp version và merge thay đổi theo log position | Phức tạp về consistency và retention |

Không tự thêm một event đến muộn vào **snapshot đã READY** đang có checkpoint, vì như thế thay tập input của `JobInstance` cũ. Nên tạo delta snapshot mới hoặc reprocess có chủ đích với version mới và phép cập nhật nghiệp vụ rõ ràng.

### Commit muộn của ID nhỏ

Tương tự, `MAX(id)=1000000` không bảo đảm tất cả transaction chứa `id <= 1000000` đã commit. Một transaction đã cấp ID 999999 có thể commit sau khi manager đọc `MAX(id)`. Nếu worker chạy chỉ trên dữ liệu đã thấy lúc đó, record 999999 có thể không xuất hiện; khi restart, nó lại xuất hiện. **ID sequence không phải transaction commit order**.

Muốn đảm bảo membership nhất quán, cần snapshot transaction/materialization hoặc nguồn versioned/CDC với protocol tương thích, chứ không chỉ so sánh số ID.

## 14. Checkpoint, transaction và restart ở ranh giới chunk

Ranh giới **partition** quyết định worker được phép đọc **miền nào**. Ranh giới **chunk/checkpoint** quyết định đã commit phần nào **bên trong miền đó**. Hai loại boundary phải được giữ nhất quán cùng nhau.

Ví dụ `partition0001=[251,501)`, reader đọc tới 400, writer commit các chunk tới 399. Nếu process chết trong chunk tiếp theo, lần restart phải cho phép xử lý lại phần chưa commit; không được tự đặt lower bound mới thành `401` chỉ vì log cho biết “đã đọc 400”.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant W as Worker partition0001
    participant R as Snapshot Reader
    participant D as Business DB
    participant J as JobRepository
    M->>W: Range [251,501)
    W->>R: open(checkpoint)
    loop Chunk đã commit
      R-->>W: items
      W->>D: Ghi transaction chunk
      W->>J: Cập nhật checkpoint theo lifecycle
    end
    R-->>W: Đọc item tiếp theo
    Note over W,D: Crash trước commit chunk
    M->>W: Restart cùng JobInstance / range
    W->>R: open(checkpoint cuối hợp lệ)
    R-->>W: Đọc lại phần chưa commit
~~~

Sơ đồ đơn giản hóa: thứ tự vật lý và tính atomic của business commit so với metadata update phụ thuộc cấu hình `DataSource`/`PlatformTransactionManager`/`JobRepository`. Nếu chúng không cùng transaction vật lý, có thể có trường hợp output đã commit mà checkpoint chưa cập nhật. Vì vậy cần **writer idempotent**, không chỉ checkpoint chính xác.

### Không tự đánh dấu hoàn thành dựa trên `readCount`

`readCount`, `writeCount`, skip/filter/retry và số row thực đã commit không phải lúc nào bằng nhau. Nếu writer dùng `UPSERT`, một item được ghi thử nhiều lần vẫn có thể chỉ tạo một row cuối. Nếu dữ liệu được filter hợp lệ, `writeCount < readCount` không có nghĩa mất record. Phải xác định **business invariant** để đối soát đúng kết quả.

### Tên partition phải ổn định

`partition0001` của attempt trước chỉ tới `[251,501)`. Sau khi scale lên tám worker, không được tái dùng tên ấy cho `[126,251)` trong cùng `JobInstance` nếu checkpoint cũ còn hiệu lực. Nên giữ manifest partition cố định và để executor/remote worker pool quyết định số slot chạy song song; **số worker thực thi** có thể khác **số partition đã chia**.

## 15. Remote partitioning: biên đúng nhưng worker khác máy vẫn phải đọc đúng

Trong **local partitioning**, manager giao các `StepExecutionContext` riêng cho thread trong JVM. Trong **remote partitioning**, worker trên JVM khác nhận thông tin `StepExecution` qua protocol/messaging và tự đọc dữ liệu.

~~~mermaid
flowchart LR
    M["Manager / Manifest [start,end)"] --> Q["Broker request"]
    Q --> A["Worker JVM A: P0"]
    Q --> B["Worker JVM B: P1"]
    Q --> C["Worker JVM C: P2"]
    A --> S["Immutable snapshot DB"]
    B --> S
    C --> S
    A --> O["Business DB"]
    B --> O
    C --> O
~~~

Cần kiểm tra thêm:

1. **Cùng snapshot version**: mọi worker phải truy cập đúng snapshot, không dùng một path local chỉ tồn tại trên manager.
2. **Cùng boundary contract**: manager và worker cùng dùng end-exclusive; không đổi semantics giữa các release.
3. **Cùng kiểu dữ liệu**: `long`/timestamp precision, timezone và collation đồng nhất.
4. **Cùng metadata**: với các cơ chế remote partitioning tra `StepExecution` qua `JobRepository`, manager/worker phải tương thích schema/serializer/repository.
5. **Không chạy hai owner cùng partition** sau timeout/lease hết hạn nếu nghiệp vụ có side effect không idempotent; kiểm tra trạng thái worker cũ, fencing hoặc takeover an toàn.
6. **Reply/ack có thể mất** dù worker đã commit; phải dựa trên metadata/reconciliation và idempotency, không tự coi timeout là chưa xử lý.
7. **Không nhân dữ liệu nhạy cảm qua broker** khi chỉ cần giao partition ID/range và để worker đọc nguồn có phân quyền.

**Remote chunking là mô hình khác**: manager thường sở hữu reader và chia chunk để gửi item cho worker. Nó vẫn cần snapshot ổn định và checkpoint đúng, nhưng không mặc định có reader riêng ở worker như remote partitioning.

## 16. Tăng throughput không được làm giảm độ tin cậy

Một số lỗi ở biên chỉ xuất hiện khi tăng concurrency:

- Worker đọc với nhiều connection có **snapshot thời điểm khác nhau**.
- Một partition xử lý quá lâu, dữ liệu snapshot bị cleanup giữa chừng.
- Executor tăng thread nhưng JDBC pool không đủ connection, gây timeout và retry.
- Các worker cùng cập nhật bảng tổng hợp, gây deadlock hoặc **lost update**.
- Bản ghi đến muộn làm một số partition được nạp thêm data trong lúc partition khác đã hoàn thành.
- Số partition đổi trên restart khiến mapping tên/boundary khác đi.
- Skew khiến worker nhanh hết việc nhưng worker chứa nhiều bản ghi ở biên cuối kéo dài toàn job.

### Đo lường gợi ý

| Tầng | Metric | Mục tiêu |
| --- | --- | --- |
| Snapshot | expected key count, data version, state READY | Biết chính xác input được chốt |
| Partition manifest | range count, gap/overlap count, expected_count từng range | Kiểm chứng phân công |
| Worker | `StepExecution` status, read/write/commit/rollback count | Tìm partition chậm/lỗi |
| Executor | Active worker, queue depth, rejected tasks | Không vượt concurrency capacity |
| JDBC pool | Active/pending/acquire wait | Không tạo connection bottleneck |
| Database | Lock wait, deadlock, query plan, IO/WAL | Tìm writer/reader bottleneck |
| Nghiệp vụ | Missing/duplicate key, wrong payload/version | Chứng minh output đúng |
| Restart | Time to recover, replayed items, checkpoint age | Đáp ứng RTO |

Đừng lấy `throughput=50.000 read/s` làm thành công nếu 100 ID ở biên bị bỏ sót. **Thông lượng hữu ích** phải được đo cùng phép đối soát kết quả.

## 17. Kiểm thử property-based cho Partitioner

Các ví dụ nhỏ dễ làm người phát triển tưởng mọi range đều đúng. Cần thử cả miền có width lẻ, số partition lớn hơn width, các giá trị âm và vùng gần giới hạn `long`.

Một phép kiểm tra độc lập, dùng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class HalfOpenRangePartitionerTest {

    @Test
    void coversDomainWithoutGapOrOverlap() {
        for (long first = -15; first <= 15; first++) {
            for (long width = 1; width <= 31; width++) {
                for (int gridSize = 1; gridSize <= 40; gridSize++) {
                    long last = first + width;
                    Map<String, ExecutionContext> parts =
                        new HalfOpenRangePartitioner(
                            first, last).partition(gridSize);

                    List<long[]> ranges = new ArrayList<>();
                    parts.values().forEach(ec -> ranges.add(
                        new long[] {
                            ec.getLong("startInclusive"),
                            ec.getLong("endExclusive")
                        }
                    ));
                    assertFalse(ranges.isEmpty());

                    long next = first;
                    for (long[] range : ranges) {
                        assertEquals(next, range[0]);
                        assertTrue(range[0] < range[1]);
                        next = range[1];
                    }
                    assertEquals(last, next);

                    // Chứng minh mọi khóa trong miền thuộc đúng 1 range.
                    for (long id = first; id < last; id++) {
                        int matches = 0;
                        for (long[] range : ranges) {
                            if (id >= range[0] && id < range[1]) {
                                matches++;
                            }
                        }
                        assertEquals(1, matches);
                    }
                }
            }
        }
    }

    @Test
    void rejectsInvalidAndOverflowingDomain() {
        assertThrows(IllegalArgumentException.class,
            () -> new HalfOpenRangePartitioner(5, 5));
        assertThrows(ArithmeticException.class,
            () -> new HalfOpenRangePartitioner(
                    Long.MIN_VALUE, Long.MAX_VALUE));
    }

    @Test
    void supportsRangesNearLongMaxWithoutOverflow() {
        var partitions = new HalfOpenRangePartitioner(
                Long.MAX_VALUE - 10, Long.MAX_VALUE)
                .partition(4);
        assertEquals(4, partitions.size());
    }
}
~~~

Đây là **quét nhiều trường hợp nhỏ**, chưa phải thư viện property-based chuyên dụng. Khi dùng jqwik/QuickTheories có thể sinh hàng nghìn bộ input ngẫu nhiên và kiểm chứng các bất biến; vẫn nên giữ test deterministic cho những biên đã từng lỗi.

Bài test trên tránh sinh `endExclusive = Long.MAX_VALUE + 1` vì Java `long` không biểu diễn được. Trường hợp record thật có ID đúng `Long.MAX_VALUE` cần cách phân vùng riêng đã thảo luận ở mục 7.3.

### Test SQL bằng dữ liệu biên

Tạo fixture:

~~~sql
-- Tất cả bản ghi của một snapshot giả định:
-- id = 1, 2, 249, 250, 251, 500, 501, 750, 751, 1000
--
-- Mong đợi:
-- [1,251)     -> 1,2,249,250
-- [251,501)   -> 251,500
-- [501,751)   -> 501,750
-- [751,1001)  -> 751,1000
~~~

Với mỗi ID ranh giới `251`, `501`, `751`, hãy assert **chính xác một** worker nhận, và ID `1001` không thuộc miền. Đây là test phát hiện sai khác giữa Java boundary generator và SQL predicate.

## 18. Fault injection và đối soát sau retry/restart

Một bộ kiểm thử tích hợp cần vượt qua việc chỉ unit-test `Partitioner`:

1. **Snapshot rỗng**: không có dữ liệu, job chọn đúng nhánh nghiệp vụ thay vì chạy reader range vô nghĩa.
2. **ID thưa**: có gap lớn trong dãy số nhưng không có record nào bị bỏ sót.
3. **Boundary ID**: record ở đầu, cuối và ngay ranh giới liền kề thuộc đúng một worker.
4. **Khóa âm và lớn**: kiểm tra số âm, gần `Long.MIN_VALUE`/`Long.MAX_VALUE` và overflow được từ chối đúng.
5. **Khoảng nhiều hơn record**: không tạo partition rỗng ngoài chính sách.
6. **Composite key**: hai tenant có cùng order ID; reader/paging không được skip khi chỉ số thứ tự phụ trùng nhau.
7. **Timestamp cùng giá trị**: nhiều event cùng microsecond nhưng khác event ID; keyset pagination không bỏ event.
8. **Timezone/DST**: biên ngày business được đổi sang Instant nhất quán trên mọi worker.
9. **NULL và collation**: nguồn có key NULL/Unicode; có policy phân vùng rõ và thống nhất.
10. **Late insert/commit**: thay đổi bảng nguồn sau snapshot; worker vẫn xử lý đúng snapshot.
11. **Update/delete nguồn**: input version không thay đổi trong cùng `JobInstance`.
12. **Lỗi trước commit chunk**: worker rollback rồi restart; item cuối chunk được đọc lại nếu cần.
13. **Lỗi sau business commit trước metadata**: writer replay-safe, output không nhân đôi.
14. **Worker crash khi gần ranh giới**: dừng worker ở ID `250` hoặc `251`, restart vẫn đủ hai ID.
15. **Manager/worker khác version**: cả hai hiểu cùng `startInclusive`/`endExclusive` và serializer.
16. **Scale 1 → 2 → 4 → 8 worker**: không làm thay đổi số bản ghi output hợp lệ; đo DB contention và hiệu năng.
17. **Đổi `gridSize` khi restart**: policy từ chối hoặc dùng lại manifest cũ, không âm thầm đổi ranh giới.
18. **Reconciliation cuối job**: đủ business keys, đúng payload/version và side effects theo yêu cầu.

### SQL tìm record snapshot thiếu ở đích

~~~sql
SELECT id
FROM batch_order_snapshot
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT id
FROM batch_order_result
WHERE snapshot_id = :snapshotId;
~~~

Kỳ vọng **0 hàng** với bài toán copy đủ toàn bộ dữ liệu. Muốn tìm output thừa, đảo hai vế `EXCEPT`.

### SQL phát hiện version hoặc payload sai

~~~sql
SELECT s.id
FROM batch_order_snapshot s
JOIN batch_order_result o
  ON o.snapshot_id = s.snapshot_id
 AND o.id = s.id
WHERE s.snapshot_id = :snapshotId
  AND (
       s.source_version IS DISTINCT FROM o.source_version
       OR s.payload IS DISTINCT FROM o.payload
  );
~~~

Cũng kỳ vọng **0 hàng** khi output phải giống snapshot. Nếu có filter hoặc transform hợp lệ, cần xác định tập output và phép so sánh tương ứng thay vì yêu cầu mọi record được copy nguyên trạng.

**Đối soát khóa không phát hiện được hết side effect trùng.** Nếu một record dẫn tới hai email hoặc hai lần debit, bảng `batch_order_result` có thể vẫn chỉ có một hàng. Phải có ledger/event audit/transactional outbox hoặc phép đo nghiệp vụ phù hợp.

## 19. Runbook khi phát hiện thiếu record ở biên

Khi hệ thống báo job `COMPLETED` nhưng nguồn và đích lệch record ở `startId`/`endExclusive`, không nên sửa SQL ngay rồi chạy lại vô điều kiện.

1. **Khoanh vùng**: lấy `snapshotId`, `JobInstance`/`JobExecution`, partition name và business keys bị thiếu.
2. **Bảo vệ bằng chứng**: giữ manifest, metadata `StepExecution`, query plan/log an toàn và snapshot version.
3. **Kiểm tra ranh giới đã lưu**: mỗi partition có đúng `[start,end)` không? Có biên 100/101, lỗi inclusive/exclusive, overflow, timestamp precision không?
4. **Kiểm tra predicate thật trên worker**: application SQL dùng `< endExclusive` hay `<= endExclusive`? Driver/parser có đổi kiểu thời gian không?
5. **Kiểm tra dữ liệu nguồn**: record có thuộc snapshot đã READY không hay mới được insert/commit sau capture?
6. **Kiểm tra checkpoint**: range của partition có đổi sau restart; `ItemStream` có sort ổn định; writer commit và checkpoint có khác transaction không?
7. **Kiểm tra overlap và concurrency**: hai worker có cùng ghi một business key không, có owner cũ còn chạy không?
8. **Đối soát nguồn–đích**: xuất danh sách missing/extra/version mismatch theo khóa, không chỉ so `readCount`.
9. **Đánh giá phương án sửa**: có thể chạy **backfill có chủ đích** cho record thiếu với writer idempotent, hoặc phải reprocess snapshot mới không?
10. **Không xóa metadata `BATCH_*`** để “reset” job; cần dùng runbook restart hợp lệ và hiểu tác động của các chunk đã commit.
11. **Đặt regression test** với chính ranh giới gây lỗi, cùng dữ liệu snapshot, timezone và serializer/phiên bản.
12. **Theo dõi sau khắc phục**: metric missing/duplicate bằng 0 theo business invariant, các side effect ngoài DB không bị lặp.

Một câu truy vấn tìm lỗi biên có thể dùng để điều tra dữ liệu giả:

~~~sql
SELECT id, payload
FROM batch_order_snapshot
WHERE snapshot_id = :snapshotId
  AND id IN (:boundaryMinusOne, :boundaryId, :boundaryPlusOne)
ORDER BY id;
~~~

Với PostgreSQL và `NamedParameterJdbcTemplate`, parameter danh sách trong `IN` cần được bind/expand đúng; nếu dùng JDBC thuần, hãy sử dụng số placeholder tương ứng.

## 20. Bài tập tình huống

Một hệ thống chạy Spring Batch remote partitioning cho snapshot gồm các ID:

~~~text
1, 2, 7, 9, 100, 101, 102, 199, 200, 201, 300, 301
~~~

Manager dự định dùng ba partition:

~~~text
partition0000: [1, 101)
partition0001: [101, 201)
partition0002: [201, 302)
~~~

Worker đọc bằng:

~~~sql
SELECT id
FROM batch_order_snapshot
WHERE snapshot_id = :snapshotId
  AND id >= :startInclusive
  AND id < :endExclusive
ORDER BY id;
~~~

Trong một phiên bản lỗi, developer đổi predicate thành `id <= :endExclusive`, sau đó sửa tên/miền `partition0001` thành `[102,202)` khi restart mà không tạo `JobInstance` mới.

**Câu hỏi:**

1. Với predicate đúng, mỗi partition nhận những ID nào?
2. Nếu đổi `< endExclusive` thành `<= endExclusive`, ID nào có thể bị xử lý hai lần?
3. Nếu đổi riêng `partition0001` từ `[101,201)` sang `[102,202)`, những ID nào có thể bị thiếu/trùng?
4. Vì sao lỗi này không thể được xử lý chỉ bằng cách đặt `chunkSize=1`?
5. Nếu nguồn còn được update sau khi đã chốt `MAX(id)=301`, điều kiện ID tối đa có bảo đảm payload nhất quán không?
6. Nếu worker ghi output bằng `INSERT ... ON CONFLICT DO NOTHING`, tình trạng record thiếu ở biên có tự được sửa không?
7. Khi timestamp trong source có nhiều event cùng `2026-11-25T00:00:00Z`, keyset pagination chỉ dựa vào `event_at > lastEventAt` gặp vấn đề gì?
8. Nếu snapshot có ID `Long.MAX_VALUE`, biểu thức `endExclusive = maxId + 1` còn đúng không?
9. Nêu ít nhất ba kiểm thử cần chạy trước khi scale từ 3 lên 12 worker.

### Gợi ý đáp án

- **(1)** P0: `1,2,7,9,100`. P1: `101,102,199,200`. P2: `201,300,301`.
- **(2)** ID `101` thuộc P0 và P1; ID `201` thuộc P1 và P2 nếu tồn tại. Predicate sai có thể gây duplicate.
- **(3)** ID `101` không còn thuộc partition0001, cũng không thuộc P0 nên **thiếu**. Các miền khác không thay thì không có overlap mới trong ví dụ cụ thể, nhưng `[102,202)` còn chồng lấn `[201,302)` ở giá trị `201`.
- **(4)** Chunk size chỉ thay transaction/checkpoint, không sửa predicate phân công.
- **(5)** Không. ID ceiling không chốt version/content; bản ghi cũ vẫn có thể update/delete.
- **(6)** Không. `UPSERT/DO NOTHING` có thể ngăn duplicate **ghi**, nhưng không tạo lại bản ghi chưa bao giờ được đọc.
- **(7)** Những event cùng timestamp bị skip khi checkpoint chỉ lưu timestamp; cần tie-breaker duy nhất như `(event_at,event_id)`.
- **(8)** Không. `long` overflow; cần thiết kế upper bound khác hoặc kiểu rộng hơn.
- **(9)** Coverage/disjointness SQL, boundary fixtures, snapshot stability, crash/restart, duplicate reply và business-key reconciliation.

## Checklist trước khi production

- [ ] Tài liệu contract dùng nhất quán `[startInclusive,endExclusive)` ở manager, SQL, worker và test.
- [ ] Kiểm tra **range đầu/cuối, adjacency** và **count**; không chỉ kiểm tra một trong ba.
- [ ] Có phép thử record ở đầu, cuối và ngay biên các partition.
- [ ] ID thưa, âm, cực đại, miền rỗng, NULL, timestamp precision/collation đều có policy rõ.
- [ ] Snapshot/manifest bất biến và identifying `snapshotId` ổn định cho cùng `JobInstance`.
- [ ] Partition name và boundary không tự đổi khi restart hoặc scale worker count.
- [ ] Reader `@StepScope` nhận đúng `StepExecutionContext` và dùng predicate `>= start AND < end`.
- [ ] Paging/`ItemStream` checkpoint dùng sort key duy nhất, lưu state theo commit hợp lệ.
- [ ] Writer có business-key idempotency; side effect ngoài DB có ledger/outbox theo yêu cầu.
- [ ] Worker remote đọc được snapshot/version và dùng contract boundary giống manager.
- [ ] Có test crash ngay trước/sau commit, metadata readback và phép đối soát source–target.
- [ ] Theo dõi throughput hữu ích, DB locks, JDBC pool, partition skew và kết quả thiếu/trùng.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, `Partitioner`, worker `StepExecution`, local/remote scaling.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): API và cấu hình partitioning của Spring Batch 5.x.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `StepExecution`, `ExecutionContext` và restart semantics.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): `ItemStream`, `JdbcCursorItemReader` và checkpoint.
- [Spring Batch Reference – Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và binding worker context.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning, giao việc qua message.
- [PostgreSQL – Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): range predicates và `BETWEEN`.
- [PostgreSQL – Row and Array Comparisons](https://www.postgresql.org/docs/current/functions-comparisons.html): so sánh tuple/row value.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): consistency của source read.
- [Java SE 17 – Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact` và `floorMod`.
- [Java SE 17 – java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): Instant, ZoneId và ranh giới ngày nghiệp vụ.

## Ghi nhớ

**Tránh bỏ sót bản ghi ở biên là bảo đảm mọi record của snapshot hợp lệ thuộc đúng một partition, được đọc với cùng quy ước và có thể khôi phục sau lỗi.** Hãy dùng **`[startInclusive,endExclusive)`**, kiểm tra biên đầu/cuối và tính liên tục giữa các range, thử record ngay tại ranh giới, và dùng khóa sort duy nhất cho paging/checkpoint. Với timestamp, đừng trừ một mili-giây để giả lập cuối ngày; với ID, đừng cộng 1 khi có nguy cơ overflow; với dữ liệu mutable, đừng coi `MAX(id)` là snapshot đầy đủ. Quan trọng nhất, **giữ snapshot, partition names và boundary ổn định khi restart**, để writer idempotent xử lý replay và đối soát business keys chứng minh đầu ra không thiếu/trùng. Tăng concurrency chỉ có ý nghĩa khi kết quả vẫn đúng tại mọi biên.
