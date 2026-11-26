# Kiểm chứng coverage của partition trong Spring Batch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **coverage của miền khóa**, **coverage của từng bản ghi** và **tính đúng của output nghiệp vụ**.
- Định nghĩa yêu cầu “mỗi record trong snapshot thuộc đúng một partition” bằng bất biến toán học.
- Kiểm tra khoảng nửa mở `[startInclusive, endExclusive)` về biên đầu/cuối, gap, overlap và tính liên tục.
- Viết SQL PostgreSQL phát hiện record không được giao hoặc được giao nhiều lần, thay vì chỉ so tổng `COUNT(*)`.
- Xây dựng `Partitioner`, reader `@StepScope` và worker/manager Spring Batch **5.x, Java 17** dựa trên manifest đã chốt.
- Phân tích ID thưa, hash bucket, khóa ghép, NULL, timestamp, dữ liệu đến muộn và restart.
- Kiểm thử tính đầy đủ sau crash, retry, remote partitioning và xử lý lại dữ liệu, đồng thời đo bottleneck khi tăng concurrency.

## 1. Bài toán: tất cả worker COMPLETED nhưng vẫn thiếu dữ liệu

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, một job nhập tám triệu đơn hàng được chia thành tám partition và chạy qua nhiều thread hoặc nhiều JVM. Cả tám worker đều báo `COMPLETED`, nhưng kiểm toán phát hiện thiếu đơn hàng tại ranh giới hai miền.

Những lỗi có thể xảy ra:

- Manager tạo `P0=[1,100)` và `P1=[101,200)`, nên ID 100 không thuộc worker nào.
- Manager tạo đúng `[1,100)` và `[100,200)` nhưng worker thứ hai dùng `id > :start`, làm mất ID 100.
- Hai partition cùng đọc ID 100 nhưng writer `ON CONFLICT DO NOTHING` che mất dấu hiệu đọc trùng.
- Dữ liệu nguồn thay đổi sau khi manager đo `MAX(id)`, khiến input khi restart không còn giống trước.
- Paging theo một timestamp không duy nhất khiến một số record bị skip.
- Writer có skip/filter/retry hoặc transaction lỗi nên dữ liệu được giao đủ nhưng output không đủ.

**Coverage là yêu cầu tính đúng, không phải hiệu năng.** Hệ thống không thực sự scale thành công khi chạy nhanh hơn nhưng bỏ sót hoặc nhân đôi tác dụng nghiệp vụ.

~~~mermaid
flowchart TD
    S["Snapshot bất biến S"] --> M["Partition manifest"]
    M --> G1["Gate 1: range coverage"]
    G1 --> G2["Gate 2: assignment đúng từng record"]
    G2 --> W0["Worker 0"]
    G2 --> W1["Worker 1"]
    G2 --> WN["Worker N"]
    W0 --> O["Business output"]
    W1 --> O
    WN --> O
    O --> G3["Gate 3: reconciliation"]
    G3 --> X{"Đúng dữ liệu?"}
    X -->|"Có"| OK["Publish kết quả"]
    X -->|"Không"| FAIL["Chặn publish, điều tra/backfill"]
~~~

## 2. Ba lớp coverage và những điều mỗi lớp không chứng minh

| Lớp | Câu hỏi | Oracle |
| --- | --- | --- |
| **Range coverage** | Các khoảng phân vùng có bao phủ đúng miền khóa và không giao nhau? | Biên đầu/cuối, kiểm tra `LAG` và adjacency |
| **Record assignment coverage** | Mỗi record trong snapshot thực sự thuộc đúng một predicate? | `LEFT JOIN` và `COUNT(partition_name)` theo khóa |
| **Business output coverage** | Output có đủ các business key, đúng version/payload và side effect? | `EXCEPT`, so sánh version, audit/ledger |

Range có thể đúng trong manifest nhưng SQL worker bị sửa sai. Assignment có thể đúng nhưng worker crash, filter nhầm hoặc writer chưa commit. Bảng đích có đủ key vẫn chưa chứng minh một email hoặc một khoản thanh toán không bị thực hiện hai lần.

### Bất biến toán học

Gọi `S` là tập bản ghi của **một snapshot cố định**, `K(r)` là partition key của record `r`, và `belongs(i,r)` là predicate của partition `i`.

~~~text
assignments(r) = số partition i có belongs(i,r) = true

Coverage:        assignments(r) >= 1 với mọi r thuộc S
Disjointness:    assignments(r) <= 1 với mọi r thuộc S
Phân công chính xác: assignments(r) = 1 với mọi r thuộc S
~~~

Nếu hệ thống chủ động xử lý một record nhiều lần để redundancy, phải thay yêu cầu `assignments(r)=1` bằng **multiplicity contract** và triển khai dedup tương ứng. Với ETL partitioning thông thường, đúng một là bất biến rõ ràng nhất.

### Tổng count bằng nhau vẫn có thể sai

Một snapshot có 100 record. Một record được gán **0** partition, một record được gán **2** partition, 98 record còn lại gán đúng một:

~~~text
Tổng assignment = 1*0 + 1*2 + 98*1 = 100
Tổng record trong snapshot = 100
~~~

Hai tổng bằng nhau nhưng vẫn có cả **missing** lẫn **overlap**. Vì vậy `SUM(readCount)` hay tổng các `COUNT(*)` không thể thay thế phép kiểm tra **trên từng business key**.

## 3. Quy tắc nửa mở và coverage của miền khóa

Chọn một quy ước chung: đầu bao gồm, cuối không bao gồm.

~~~text
Global = [1, 1001)

P0 = [1,   251)
P1 = [251, 501)
P2 = [501, 751)
P3 = [751,1001)

1                251             501             751           1001
|------- P0 -------|------ P1 ------|------ P2 ------|------ P3 -----|
~~~

SQL của worker:

~~~sql
WHERE order_id >= :startInclusive
  AND order_id < :endExclusive;
~~~

Gọi các khoảng đã sắp xếp theo đầu là `[s0,e0), ..., [sn,en)`. Điều kiện bao phủ chính xác global `[a,z)`, không gap và không overlap:

~~~text
partition_count > 0
s0 == a
en == z
si < ei                   với mọi partition
ei == s(i+1)              với mọi cặp liền kề
~~~

Nếu `ei == s(i+1)`, giá trị đúng tại biên **không** nằm ở partition i vì không thỏa `x < ei`, nhưng **nằm** ở partition i+1 vì thỏa `x >= s(i+1)`.

| Khoảng của P0 và P1 | Predicate | Record ID 100 |
| --- | --- | --- |
| `[1,100]` và `[100,200]` | `BETWEEN` hai đầu inclusive | Đọc trùng |
| `[1,100)` và `[101,200)` | `>= start AND < end` | Bỏ sót |
| `[1,100)` và `[100,201)` | `>= start AND < end` | Chỉ P1 |
| `[1,101)` và `[101,201)` | `>= start AND < end` | Chỉ P0 |

Tránh dùng `BETWEEN :start AND :endExclusive` vì `BETWEEN` bao gồm cả hai đầu. Với timestamp, không trừ một mili-giây để giả lập cuối ngày; các DB có độ chính xác timestamp khác nhau.

**ID thưa không phải gap của partition.** Nếu nguồn có ID `1,2,7,9,100,101` thì một interval `[10,50)` không chứa record vẫn có thể đúng về mặt coverage miền khóa.

## 4. Snapshot phải ổn định trước khi kiểm chứng

Nếu bảng nguồn vẫn nhận insert/update/delete, việc “mỗi record được xử lý đúng một lần” chưa có nghĩa vì **tập record cần xử lý** chưa cố định.

Một contract snapshot cần có:

1. **Membership:** danh sách business key thuộc run.
2. **Version/content:** giá trị record phải đọc ở phiên bản nào.
3. **Identity:** `snapshotId` ổn định, dùng làm identifying `JobParameter`.
4. **Ordering:** sort key duy nhất cho paging/checkpoint.
5. **Availability:** worker mới ở JVM khác vẫn đọc được nguồn.
6. **Retention:** snapshot còn tồn tại khi retry/restart và đối soát.
7. **Immutability:** một snapshot `READY` không bị sửa để “bổ sung” record đến muộn.

`MAX(id)` là high-watermark, không tự tạo một database point-in-time snapshot: transaction có ID nhỏ có thể commit muộn, record cũ có thể bị xóa hoặc update. Một transaction `REPEATABLE READ` ở manager cũng không mặc định được chia sẻ qua các connection/worker transaction khác.

~~~mermaid
flowchart LR
    A["Source mutable"] --> B["Capture snapshot BUILDING"]
    B --> C["Chốt membership, version và manifest"]
    C --> V["Kiểm chứng coverage"]
    V --> R["Công bố READY"]
    R --> P["Manager phân công workers"]
~~~

Nếu snapshot được materialize bằng nhiều transaction hoặc object storage, chỉ công bố READY **sau khi** dữ liệu và manifest được kiểm tra. Việc worker nhìn thấy snapshot đang BUILDING có thể dẫn tới job thành công giả.

## 5. PostgreSQL schema minh họa

~~~sql
CREATE TABLE batch_input_snapshot (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('BUILDING', 'READY', 'EXPIRED')),
    first_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL CHECK (expected_count >= 0),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (first_inclusive < end_exclusive)
);

CREATE TABLE batch_input_order (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_input_snapshot(snapshot_id),
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE batch_partition_manifest (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_input_snapshot(snapshot_id),
    partition_name VARCHAR(100) NOT NULL,
    start_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL CHECK (expected_count >= 0),
    PRIMARY KEY (snapshot_id, partition_name),
    CHECK (start_inclusive < end_exclusive)
);

CREATE INDEX idx_manifest_snapshot_start
    ON batch_partition_manifest(snapshot_id, start_inclusive);

CREATE TABLE batch_output_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

`batch_input_order` là nguồn snapshot vật lý có key `(snapshot_id,order_id)`; `batch_partition_manifest` chứa ranh giới và expected count, còn `batch_output_order` lưu kết quả business. Không đưa toàn bộ item vào `ExecutionContext`: worker chỉ cần `snapshotId`, `startInclusive`, `endExclusive` và state checkpoint.

Schema chưa tự bảo đảm không overlap giữa **hai hàng khác nhau** của manifest. Constraint `CHECK(start < end)` chỉ xác nhận một range không rỗng. Cần thêm gate validation và immutability policy.

### Ví dụ dữ liệu thưa

~~~text
snapshotId = snap-20261125
ID: 1,2,3,4,7,9,10,11,15,19
Global range = [1,20)

P0 = [1,7)    -> 1,2,3,4       expectedCount = 4
P1 = [7,12)   -> 7,9,10,11     expectedCount = 4
P2 = [12,20)  -> 15,19         expectedCount = 2

snapshot.expected_count = 10
~~~

Độ rộng các range là 6, 5, 8 nhưng số record thực là 4, 4, 2. Không tính expected count bằng `end-start` khi ID thưa.

## 6. Gate 1: kiểm tra gap, overlap và global extent bằng SQL

### 6.1. Hai interval liên tiếp có nối đúng không?

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
       END AS defect
FROM ordered
WHERE previous_end IS NOT NULL
  AND start_inclusive <> previous_end;
~~~

Kỳ vọng **0 hàng**. Tuy nhiên, query này **chưa** kiểm tra biên đầu/cuối toàn miền.

### 6.2. Kiểm tra biên ngoài cùng

~~~sql
WITH extent AS (
    SELECT
        MIN(start_inclusive) AS actual_first,
        MAX(end_exclusive) AS actual_end,
        COUNT(*) AS partition_count
    FROM batch_partition_manifest
    WHERE snapshot_id = :snapshotId
)
SELECT
    s.first_inclusive AS expected_first,
    e.actual_first,
    s.end_exclusive AS expected_end,
    e.actual_end,
    e.partition_count
FROM batch_input_snapshot s
CROSS JOIN extent e
WHERE s.snapshot_id = :snapshotId;
~~~

Kỳ vọng:

~~~text
actual_first == expected_first
actual_end   == expected_end
partition_count > 0
~~~

Phải kết hợp kiểm tra **adjacency + extent + nonempty range**. Hai khoảng `[2,10),[10,19)` nối nhau nhưng không bao phủ global `[1,20)`. Hai khoảng `[1,10),[11,20)` có biên ngoài khớp nhưng thiếu khoảng `[10,11)`.

Nếu snapshot thực sự rỗng, cần policy no-op hoặc nhánh step riêng được kiểm thử; không tự giả định mọi partition handler hoạt động như mong muốn khi partitioner trả map rỗng.

## 7. Gate 2: mỗi bản ghi có đúng một assignment

### 7.1. Đếm assignment trên từng business key

~~~sql
WITH assigned AS (
    SELECT
        s.order_id,
        COUNT(p.partition_name) AS assignment_count
    FROM batch_input_order s
    LEFT JOIN batch_partition_manifest p
      ON p.snapshot_id = s.snapshot_id
     AND s.order_id >= p.start_inclusive
     AND s.order_id < p.end_exclusive
    WHERE s.snapshot_id = :snapshotId
    GROUP BY s.order_id
)
SELECT
    COUNT(*) FILTER (WHERE assignment_count = 0) AS missing,
    COUNT(*) FILTER (WHERE assignment_count = 1) AS exactly_one,
    COUNT(*) FILTER (WHERE assignment_count > 1) AS overlap,
    COUNT(*) AS total_input
FROM assigned;
~~~

Kỳ vọng `missing=0`, `overlap=0` và `exactly_one=total_input`.

**Dùng LEFT JOIN là bắt buộc cho bài toán này:** `INNER JOIN` loại record không được gán partition **trước khi đếm**, khiến phần thiếu không xuất hiện.

### 7.2. Lấy tối đa 100 ID lỗi để điều tra

~~~sql
WITH assigned AS (
    SELECT
        s.order_id,
        COUNT(p.partition_name) AS assignment_count
    FROM batch_input_order s
    LEFT JOIN batch_partition_manifest p
      ON p.snapshot_id = s.snapshot_id
     AND s.order_id >= p.start_inclusive
     AND s.order_id < p.end_exclusive
    WHERE s.snapshot_id = :snapshotId
    GROUP BY s.order_id
)
SELECT order_id, assignment_count
FROM assigned
WHERE assignment_count <> 1
ORDER BY order_id
LIMIT 100;
~~~

Giới hạn 100 chỉ để tránh xuất quá nhiều dữ liệu điều tra, **không** phải phép chứng minh rằng số lỗi ≤100.

### 7.3. Đối chiếu expected count từng partition

~~~sql
SELECT
    p.partition_name,
    p.expected_count,
    COUNT(s.order_id) AS actual_count
FROM batch_partition_manifest p
LEFT JOIN batch_input_order s
  ON s.snapshot_id = p.snapshot_id
 AND s.order_id >= p.start_inclusive
 AND s.order_id < p.end_exclusive
WHERE p.snapshot_id = :snapshotId
GROUP BY p.partition_name, p.expected_count
HAVING COUNT(s.order_id) <> p.expected_count;
~~~

Kỳ vọng **0 hàng**, nhưng count vẫn có thể được ghi sai từ đầu hoặc hai lỗi thiếu/trùng triệt tiêu nhau. Kết hợp với kiểm tra record-level để có bằng chứng tốt hơn.

## 8. Gate 3: đối soát kết quả nghiệp vụ

Một partition có thể nhận đúng input nhưng reader/processor/writer vẫn gây thiếu output. Sau khi worker chạy xong và trước khi công bố kết quả, phải xác định tập output **mong đợi theo nghiệp vụ**.

Với ví dụ **copy nguyên snapshot** sang bảng `batch_output_order`:

### 8.1. Khóa bị thiếu ở đích

~~~sql
SELECT order_id
FROM batch_input_order
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT order_id
FROM batch_output_order
WHERE snapshot_id = :snapshotId;
~~~

### 8.2. Khóa thừa ở đích

~~~sql
SELECT order_id
FROM batch_output_order
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT order_id
FROM batch_input_order
WHERE snapshot_id = :snapshotId;
~~~

### 8.3. Đúng khóa nhưng sai version/payload

~~~sql
SELECT s.order_id
FROM batch_input_order s
JOIN batch_output_order o
  ON o.snapshot_id = s.snapshot_id
 AND o.order_id = s.order_id
WHERE s.snapshot_id = :snapshotId
  AND (
       o.source_version IS DISTINCT FROM s.source_version
       OR o.payload IS DISTINCT FROM s.payload
  );
~~~

Cả ba truy vấn phải trả **0 hàng** nếu job chỉ copy nguyên đầu vào. Nếu processor có filter hoặc transform hợp lệ, xác định **expected output set** theo business rule, không mặc định `outputCount=inputCount`.

### Đếm và checksum có giới hạn

Một record bị thiếu và một record thừa có thể khiến tổng count vẫn bằng nhau. Một checksum cộng các giá trị ID cũng có thể trùng khi các sai sót triệt tiêu nhau; mọi checksum hữu hạn đều có xác suất collision. Checksum mạnh có ích cho khoanh vùng, nhưng không nên xem là bằng chứng tuyệt đối của các hiệu ứng nghiệp vụ.

`EXCEPT` của SQL có semantics **tập hợp**. Nếu một business key được phép xuất hiện nhiều lần trong source và multiplicity quan trọng, cân nhắc `EXCEPT ALL`, nhóm theo `(businessKey, occurrenceId)` hoặc ledger sự kiện có định danh duy nhất. Schema ví dụ đã có primary key `(snapshot_id,order_id)` để tránh nhập nhằng.

### Cần kiểm tra cả side effect

Một bảng đích có primary key không phát hiện được hai email đã gửi, hai lần cộng điểm hay hai lần gọi API thanh toán. Khi writer tạo side effect bên ngoài transaction, cần operation ledger, transactional outbox/inbox hoặc cơ chế idempotency/reconciliation riêng.

## 9. Không phải mọi partition đều là khoảng ID

### 9.1. Hash bucket

Với hash partitioning, một bản ghi được gán theo hàm ổn định:

~~~text
bucket = floorMod(stableHash(businessKey), bucketCount)
~~~

Bất biến cần chứng minh:

1. `bucketCount > 0`.
2. Với mỗi record, kết quả bucket luôn nằm trong `[0,bucketCount)`.
3. Mỗi bucket được khai báo đúng một lần trong manifest.
4. Java, database và worker dùng **cùng hash algorithm/encoding/seed**.
5. `bucketCount` và mapping không thay đổi trong những lần restart của cùng `JobInstance`.

Với ID số nguyên, ví dụ SQL PostgreSQL:

~~~sql
SELECT order_id
FROM batch_input_order
WHERE snapshot_id = :snapshotId
  AND ((order_id % :bucketCount) + :bucketCount) % :bucketCount
      = :bucketIndex;
~~~

Biểu thức normalize kết quả cho ID âm khi `bucketCount > 0`. Nếu Java dùng `Math.floorMod(orderId, bucketCount)`, cần test đối chiếu kết quả với SQL cho các biên và kiểu dữ liệu. Không tự cho rằng `String.hashCode()` của Java bằng một hàm hash của PostgreSQL.

Hash coverage không thể kiểm tra bằng `LAG(endExclusive)`. Hãy tạo bảng bucket manifest và `LEFT JOIN` mỗi record với bucket tương ứng rồi đếm số match =0,1,>1 như mục 7.

### 9.2. Khóa ghép

Snapshot có khóa `(tenant_id,order_id)`, hai tenant A/B đều có order ID 42. Nếu nhóm coverage chỉ theo `order_id` sẽ gộp nhầm hai business record.

Có thể phân vùng theo tuple trong PostgreSQL:

~~~sql
SELECT tenant_id, order_id, payload
FROM tenant_order_snapshot
WHERE snapshot_id = :snapshotId
  AND (tenant_id, order_id) >= (:startTenant, :startOrder)
  AND (tenant_id, order_id) < (:endTenant, :endOrder)
ORDER BY tenant_id, order_id;
~~~

Mọi thành phần trong tuple phải có kiểu, collation và quy tắc NULL đồng nhất giữa manager, worker và validator. Tên tenant có thể phân biệt chữ hoa/thường theo collation; đổi collation hoặc Unicode normalization có thể đổi coverage dù code trông không thay đổi.

### 9.3. Partition key NULL

Predicate `key >= start AND key < end` không chọn hàng có `key IS NULL`. Nếu nguồn cho phép NULL, hãy chọn **một** chính sách:

- Reject record và báo lỗi dữ liệu trước READY.
- Tạo partition riêng có predicate `key IS NULL`.
- Chuẩn hóa sentinel không va chạm dữ liệu thật, với contract thống nhất trên mọi process.

Không để Java fallback NULL thành 0 còn SQL validator giữ NULL, vì các record sẽ biến mất khỏi một trong hai góc nhìn.

### 9.4. ID thưa, số âm và giới hạn long

Miền `[-20,100)` hợp lệ nếu business key cho phép ID âm; không hardcode `id >= 0` vô cớ. Độ rộng range không tương đương số lượng record có mặt.

Nếu ID bằng `Long.MAX_VALUE`, phép tính `endExclusive = maxId + 1` sẽ overflow. Có thể dùng kiểu `NUMERIC/BigInteger` cho boundary, một partition cuối có upper-inclusive được định nghĩa riêng hoặc một mô hình khác; không âm thầm dùng signed `long` để biểu diễn exclusive end không tồn tại.

Đối với snapshot rỗng, có thể chọn nhánh no-op sau bước kiểm tra input hoặc một partition no-op với contract đã test. Đừng mặc định mọi partition handler xử lý map rỗng giống nhau.

## 10. Thời gian: coverage theo cửa sổ chưa đủ nếu event đến muộn

Với sự kiện theo ngày, dùng khoảng **đầu bao gồm, cuối không bao gồm**, cùng múi giờ business đã quy định.

Ví dụ cửa sổ ngày **2026-11-25 tại Việt Nam**:

~~~text
Local: [2026-11-25T00:00:00+07:00, 2026-11-26T00:00:00+07:00)
UTC:   [2026-11-24T17:00:00Z,      2026-11-25T17:00:00Z)
~~~

Query:

~~~sql
SELECT event_id, event_at, payload
FROM batch_event_snapshot
WHERE snapshot_id = :snapshotId
  AND event_at >= :fromInclusive
  AND event_at < :toExclusive
ORDER BY event_at, event_id;
~~~

Không dùng `BETWEEN` với mốc đầu ngày kế tiếp nếu hai cửa sổ liền kề; event tại đúng 00:00 có thể được đọc trùng. Không tự lấy `23:59:59.999` để giả lập cuối ngày: độ chính xác có thể là microsecond hoặc nanosecond.

Java 17 tính mốc theo `ZoneId`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

record TimeWindow(Instant startInclusive, Instant endExclusive) {}

static TimeWindow businessDay(LocalDate day, ZoneId zone) {
    Instant from = day.atStartOfDay(zone).toInstant();
    Instant to = day.plusDays(1)
                    .atStartOfDay(zone).toInstant();
    return new TimeWindow(from, to);
}
~~~

Ở những múi giờ có DST, một ngày địa phương có thể không dài đúng 24 giờ. Tính `to` bằng đầu ngày kế tiếp tại `ZoneId` đó, không mặc định `from.plus(24h)`.

### Các event cùng timestamp và checkpoint

Nếu reader paging chỉ dùng:

~~~sql
WHERE event_at > :lastEventAt
ORDER BY event_at
~~~

nó có thể bỏ sót những event khác có **cùng event_at** với item cuối trang trước. Dùng khóa sắp xếp duy nhất như `(event_at,event_id)`:

~~~sql
WHERE (event_at,event_id) > (:lastEventAt,:lastEventId)
ORDER BY event_at,event_id
~~~

Watermark checkpoint phải tương ứng **item cuối đã commit**, không chỉ item vừa đọc trước khi transaction rollback.

### Event time khác ingest time

Một event xảy ra lúc 00:59:59 nhưng tới hệ thống lúc 01:02. Nếu snapshot của `[00:00,01:00)` đã chốt lúc 01:00, nó **không nằm trong snapshot**, dù range timestamp đúng.

Nghiệp vụ cần chọn allowed lateness/watermark, grace period, delta-backfill hoặc reprocess window. Không tự thêm event đến muộn vào snapshot `READY` có checkpoint đang được restart.

## 11. Java: Partitioner đọc immutable manifest và fail-fast

Ví dụ sau dành cho **Spring Batch 5.x, Java 17**, dùng bảng mục 5. Nó kiểm tra trạng thái READY, biên đầu/cuối, adjacency, expected count và uniqueness của tên partition; chỉ tạo `ExecutionContext` chứa dữ liệu nhỏ cho từng worker.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.jdbc.core.JdbcTemplate;

record SnapshotMeta(
        String state, long firstInclusive,
        long endExclusive, long expectedCount) {}

record PartitionRange(
        String name, long startInclusive,
        long endExclusive, long expectedCount) {}

public final class VerifiedManifestPartitioner implements Partitioner {

    private final JdbcTemplate jdbc;
    private final String snapshotId;

    public VerifiedManifestPartitioner(
            JdbcTemplate jdbc, String snapshotId) {
        this.jdbc = jdbc;
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0 || snapshotId == null
                || snapshotId.isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid gridSize or snapshotId");
        }

        SnapshotMeta meta = jdbc.queryForObject("""
            SELECT state, first_inclusive,
                   end_exclusive, expected_count
            FROM batch_input_snapshot
            WHERE snapshot_id = ?
            """,
            (rs, rowNum) -> new SnapshotMeta(
                    rs.getString("state"),
                    rs.getLong("first_inclusive"),
                    rs.getLong("end_exclusive"),
                    rs.getLong("expected_count")),
            snapshotId);

        if (meta == null || !"READY".equals(meta.state())) {
            throw new IllegalStateException("Snapshot not READY");
        }

        List<PartitionRange> ranges = jdbc.query("""
            SELECT partition_name, start_inclusive,
                   end_exclusive, expected_count
            FROM batch_partition_manifest
            WHERE snapshot_id = ?
            ORDER BY start_inclusive, end_exclusive, partition_name
            """,
            (rs, rowNum) -> new PartitionRange(
                    rs.getString("partition_name"),
                    rs.getLong("start_inclusive"),
                    rs.getLong("end_exclusive"),
                    rs.getLong("expected_count")),
            snapshotId);

        if (ranges.isEmpty()) {
            throw new IllegalStateException(
                    "No partitions for snapshot");
        }

        long nextStart = meta.firstInclusive();
        long expectedTotal = 0L;
        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        for (PartitionRange range : ranges) {
            if (range.name() == null || range.name().isBlank()
                    || range.startInclusive() != nextStart
                    || range.endExclusive() <= range.startInclusive()
                    || range.expectedCount() < 0L) {
                throw new IllegalStateException(
                    "Gap, overlap or invalid partition range");
            }

            expectedTotal = Math.addExact(
                    expectedTotal, range.expectedCount());

            ExecutionContext context = new ExecutionContext();
            context.putString("snapshotId", snapshotId);
            context.putLong("startInclusive", range.startInclusive());
            context.putLong("endExclusive", range.endExclusive());
            context.putLong("expectedCount", range.expectedCount());

            if (result.putIfAbsent(range.name(), context) != null) {
                throw new IllegalStateException(
                        "Duplicate partition name");
            }

            nextStart = range.endExclusive();
        }

        if (nextStart != meta.endExclusive()
                || expectedTotal != meta.expectedCount()) {
            throw new IllegalStateException(
                    "Manifest extent or expected count mismatch");
        }

        return result;
    }
}
~~~

**Đã kiểm tra:** snapshot READY, tập range không rỗng, biên đầu đúng, các range nối tiếp, biên cuối đúng, expected count tổng khớp và partition name không trùng.

**Chưa kiểm tra:** expected count có lấy từ đúng input không; worker có SQL đúng không; snapshot có thật sự bất biến sau READY không; output có đầy đủ không. Vì vậy phải giữ SQL gate mục 6–8 và business reconciliation.

`gridSize` trong code chỉ được kiểm tra là số dương; **số partition lấy từ manifest** và không được tạo lại chỉ vì số worker thay đổi. Đây là lựa chọn có chủ đích để giữ mapping khi restart.

## 12. Java: reader @StepScope gắn đúng miền dữ liệu

Mỗi worker partition có một `StepExecution` và `ExecutionContext` riêng. Bean reader được tạo trong `@StepScope` sẽ bind thông số được manager giao.

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(
        String snapshotId, long orderId,
        long sourceVersion, String payload) {}

@Configuration
class CoverageReaderConfiguration {

    @Bean("coverageReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> coverageReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['snapshotId']}")
                String snapshotId,
            @Value("#{stepExecutionContext['startInclusive']}")
                Long startInclusive,
            @Value("#{stepExecutionContext['endExclusive']}")
                Long endExclusive) {

        if (snapshotId == null || snapshotId.isBlank()
                || startInclusive == null || endExclusive == null
                || startInclusive >= endExclusive) {
            throw new IllegalArgumentException(
                    "Invalid partition StepExecutionContext");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("coverageReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT order_id, source_version, payload
                    FROM batch_input_order
                    WHERE snapshot_id = ?
                      AND order_id >= ?
                      AND order_id < ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startInclusive);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                    snapshotId,
                    rs.getLong("order_id"),
                    rs.getLong("source_version"),
                    rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

- `@StepScope` tạo reader theo `StepExecution`, không phải tự động theo mọi Java thread. Trong local/remote partitioning, mỗi partition có step execution riêng.
- `ORDER BY order_id` là một thứ tự duy nhất vì PK `(snapshot_id,order_id)` của schema.
- `.saveState(true)` cho phép `JdbcCursorItemReader` lưu tiến độ qua `ItemStream`, khi Step quản lý đúng lifecycle `open/update/close`.
- Không tự tính lại `MAX(order_id)` trong reader, không đổi `startInclusive/endExclusive` để “căn chỉnh”.
- Dùng bind parameters thay vì ghép boundary từ message vào SQL.

Nếu bạn tự triển khai multi-threaded step với nhiều thread trong **cùng `StepExecution`**, `@StepScope` không tự tạo nhiều cursor độc lập; cần phân tích thread safety riêng.

## 13. Spring Batch worker, writer và manager step

Wiring local partitioning minh họa Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class CoverageJobConfiguration {

    @Bean("verifiedPartitioner")
    @StepScope
    Partitioner verifiedPartitioner(
            JdbcTemplate jdbc,
            @Value("#{jobParameters['snapshotId']}") String snapshotId) {
        return new VerifiedManifestPartitioner(jdbc, snapshotId);
    }

    @Bean("coverageWriter")
    ItemWriter<OrderRow> coverageWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (OrderRow row : chunk) {
                jdbc.update("""
                    INSERT INTO batch_output_order(
                        snapshot_id, order_id, source_version, payload
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (snapshot_id, order_id) DO UPDATE
                    SET source_version = EXCLUDED.source_version,
                        payload = EXCLUDED.payload
                    WHERE (
                        batch_output_order.source_version,
                        batch_output_order.payload
                    ) IS DISTINCT FROM (
                        EXCLUDED.source_version,
                        EXCLUDED.payload
                    )
                    """,
                    row.snapshotId(), row.orderId(),
                    row.sourceVersion(), row.payload());
            }
        };
    }

    @Bean("coverageWorker")
    Step coverageWorker(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("coverageReader")
                JdbcCursorItemReader<OrderRow> reader,
            @Qualifier("coverageWriter")
                ItemWriter<OrderRow> writer) {

        return new StepBuilder("coverageWorker", repository)
                .<OrderRow, OrderRow>chunk(200, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("coverageExecutor")
    ThreadPoolTaskExecutor coverageExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("coverage-");
        executor.initialize();
        return executor;
    }

    @Bean("coverageManager")
    Step coverageManager(
            JobRepository repository,
            @Qualifier("coverageWorker") Step worker,
            @Qualifier("verifiedPartitioner") Partitioner partitioner,
            @Qualifier("coverageExecutor") TaskExecutor executor) {

        return new StepBuilder("coverageManager", repository)
                .partitioner("coverageWorker", partitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("coverageJob")
    Job coverageJob(
            JobRepository repository,
            @Qualifier("coverageManager") Step manager) {

        return new JobBuilder("coverageJob", repository)
                .start(manager)
                .build();
    }
}
~~~

Ví dụ dùng các class từ mục 11–12 và giả định ứng dụng đã cấu hình `JobRepository`, `JdbcTemplate`, `DataSource`, `PlatformTransactionManager`, cũng như identifying `JobParameter snapshotId` trỏ tới snapshot READY.

Writer dùng `UPSERT` để replay cùng record snapshot giữ **trạng thái cuối** nhất quán. Điều đó không tự bảo đảm email/API/event side effect là idempotent; cần ledger, idempotency key hoặc outbox nếu chúng tồn tại.

### gridSize khác số worker thực

`gridSize(4)` là hint đối với partitioner/handler; `ThreadPoolTaskExecutor` đang cho tối đa bốn worker threads. Nếu manifest có 20 range, code partitioner vẫn trả 20; executor có thể xử lý lần lượt nhiều wave. **Không tăng số partition chỉ để tăng thread**, và đừng tái tạo partition name/range khi restart chỉ vì thay số pod.

## 14. Restart: coverage phải còn đúng sau nhiều attempt

Một `JobInstance` có thể có nhiều `JobExecution` khi restart. Mỗi worker partition có `StepExecutionContext` và checkpoint riêng.

~~~text
Snapshot S: IDs 1..1000 (đã chốt)
P0 [1,251)     COMPLETED
P1 [251,501)   FAILED sau nhiều chunk đã commit
P2 [501,751)   COMPLETED
P3 [751,1001)  worker chết giữa chunk

Restart cùng JobInstance:
- P0/P2 thường được bỏ qua theo restart policy.
- P1/P3 cần khôi phục từ state/checkpoint thích hợp.
- Tên partition, snapshot và boundaries không đổi.
~~~

### Các bất biến phục hồi

1. `snapshotId` vẫn trỏ đúng tập input đã chốt, không đổi version.
2. Tên partition và `[startInclusive,endExclusive)` giữ nguyên.
3. Reader `ItemStream` dùng sort key duy nhất và checkpoint đã persist.
4. Chunk chưa commit có thể được đọc/ghi lại.
5. Nếu business DB commit nhưng metadata `JobRepository` chưa cập nhật, writer phải **idempotent**.
6. Không cho worker cũ tiếp tục ghi song song với worker mới sau timeout nếu business effect không an toàn.
7. Nếu thay identifying `run.id` để tạo `JobInstance` mới, đó là **reprocess**, không phải restart dùng checkpoint cũ.

### readCount và writeCount không phải oracle tuyệt đối

`readCount` có thể khác `writeCount` vì filter/skip/retry, và `writeCount` không phải số hàng cuối cùng bị đổi trong DB khi dùng upsert. Một partition `COMPLETED` vẫn có thể đã đọc sai predicate. Coverage cuối cùng cần dựa vào **immutable snapshot và business reconciliation**, không dựa duy nhất vào status của metadata.

### Remote partitioning và remote chunking

Với remote partitioning, manager gửi yêu cầu gắn `StepExecution` qua middleware, worker ở JVM khác đọc partition và cập nhật state qua repository/protocol tương ứng. Message reply có thể thất lạc dù worker đã commit. Cần kiểm tra metadata, owner và writer idempotency, tránh giao lại gây side effect trùng.

Với remote chunking, manager thường sở hữu reader và gửi item chunks cho worker; không áp dụng nguyên xi giả định mỗi worker có reader theo partition. Tuy nhiên, **coverage của input snapshot**, checkpoint và business-output reconciliation vẫn cần thiết.

## 15. Kiểm thử tự động các bất biến của manifest

Một lỗi off-by-one có thể không xuất hiện trên dataset lớn vì thiếu đúng record ở biên; kiểm thử chỉ dùng dữ liệu ngẫu nhiên rất dễ bỏ qua nó. Nên có **fixture biên cố định** và test invariant cho nhiều miền khác nhau.

Tốt nhất nên tách validator khỏi JDBC để kiểm thử như một pure function. Ví dụ:

~~~java
import java.util.List;

record Range(long startInclusive, long endExclusive) {}

final class CoverageInvariant {

    static void requireExactCoverage(
            long globalStart,
            long globalEndExclusive,
            List<Range> sortedRanges) {

        if (globalStart >= globalEndExclusive
                || sortedRanges == null || sortedRanges.isEmpty()) {
            throw new IllegalArgumentException(
                    "Invalid global range or empty manifest");
        }

        long nextStart = globalStart;

        // Caller sắp xếp theo startInclusive.
        for (Range range : sortedRanges) {
            if (range == null
                    || range.startInclusive() != nextStart
                    || range.endExclusive() <= range.startInclusive()) {
                throw new IllegalArgumentException(
                    "Gap, overlap, invalid order or empty range");
            }
            nextStart = range.endExclusive();
        }

        if (nextStart != globalEndExclusive) {
            throw new IllegalArgumentException(
                    "Manifest does not reach global end");
        }
    }
}
~~~

Đoạn này **chỉ kiểm tra các khoảng** đã sắp xếp, không biết các record nguồn thuộc khoảng nào. Nó cũng không xác thực bản ghi output, nên không thay thế SQL gate.

### JUnit 5 kiểm tra cả gap, overlap và thiếu biên

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class CoverageInvariantTest {

    @Test
    void acceptsContinuousHalfOpenRanges() {
        assertDoesNotThrow(() ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(1, 7),
                    new Range(7, 12),
                    new Range(12, 20))));
    }

    @Test
    void detectsGap() {
        assertThrows(IllegalArgumentException.class, () ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(1, 7),
                    new Range(8, 12),
                    new Range(12, 20))));
    }

    @Test
    void detectsOverlap() {
        assertThrows(IllegalArgumentException.class, () ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(1, 8),
                    new Range(7, 12),
                    new Range(12, 20))));
    }

    @Test
    void detectsMissingOuterBoundaries() {
        assertThrows(IllegalArgumentException.class, () ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(2, 12),
                    new Range(12, 20))));

        assertThrows(IllegalArgumentException.class, () ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(1, 7),
                    new Range(7, 19))));
    }

    @Test
    void detectsEmptyInterval() {
        assertThrows(IllegalArgumentException.class, () ->
            CoverageInvariant.requireExactCoverage(
                1, 20, List.of(
                    new Range(1, 10),
                    new Range(10, 10),
                    new Range(10, 20))));
    }

    @Test
    void acceptsNegativeKeys() {
        assertDoesNotThrow(() ->
            CoverageInvariant.requireExactCoverage(
                -20, 21, List.of(
                    new Range(-20, -3),
                    new Range(-3, 21))));
    }
}
~~~

Các test dùng cả biên âm và miền không chia đều. Có thể mở rộng bằng jqwik hoặc QuickTheories để sinh nhiều bộ range hợp lệ rồi cố tình tạo mutation:

- Dịch một biên sang phải một đơn vị để tạo gap.
- Dịch một biên sang trái để tạo overlap.
- Xóa partition đầu/cuối, xáo trộn thứ tự.
- Tạo range rỗng hoặc reversed.
- Tạo `gridSize` lớn hơn độ rộng hoặc count thực.
- Dùng `Long.MIN_VALUE`/`Long.MAX_VALUE` để phát hiện overflow trong **công đoạn sinh boundary**.

Không tự lấy `maxId+1` bằng `long` khi record thật có ID đúng `Long.MAX_VALUE`. Có thể chọn `BigInteger/NUMERIC` hoặc một mô hình upper-inclusive cho partition cuối với contract riêng.

### Unit test không thay integration test

Ngay cả khi pure validator PASS, worker có thể viết `order_id <= endExclusive`. Integration test phải tạo record ngay **startInclusive**, **endExclusive−1**, **endExclusive**, và assert mỗi record chỉ được reader tương ứng đọc.

Fixture:

~~~text
Input IDs:
1,2,6,7,11,12,19

P0 [1,7)   -> 1,2,6
P1 [7,12)  -> 7,11
P2 [12,20) -> 12,19
~~~

Nếu `id=7` được hai worker đọc hoặc không worker nào đọc, test phải fail ngay.

## 16. Fault injection: coverage sau crash và phân phối lại

Có thể kiểm chứng manifest đúng nhưng vẫn mất dữ liệu sau sự cố. Một bộ kiểm thử tích hợp cần đi qua vòng đời transaction và recovery:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Snapshot còn `BUILDING` | Không dispatch worker |
| Tên partition trùng hoặc range gap/overlap | Preflight fail trước khi có business write |
| Snapshot có ID thưa | Không bỏ bản ghi dù một range ít/không có data |
| Worker crash trước commit chunk | Chunk chưa commit được chạy lại đúng cách |
| Business DB commit nhưng metadata chưa lưu | Replay không tạo output/side effect trùng |
| Manager mất reply | Không suy luận timeout = chưa commit; xem metadata/reconciliation |
| Worker cũ chưa chết sau timeout | Không có hai owner gây business effect sai |
| Restart cùng `JobInstance` | Giữ đúng snapshot, partition names và boundaries |
| Đổi `gridSize`/worker slots | Mapping manifest cũ không bị âm thầm thay |
| Thay input source sau READY | Worker vẫn đọc đúng snapshot/version hoặc fail rõ |
| Đổi tên key checkpoint giữa release | Backward compatibility hoặc migration đã kiểm thử |
| Remote worker khác host | Đọc được cùng input, serializer và repository metadata tương thích |
| Worker dùng SQL cũ end-inclusive | Boundary fixture phát hiện duplicate |
| Số partition lớn/worker ít | Tất cả partition vẫn được dispatch và hoàn tất theo policy |
| Filter/skip hợp lệ | Output reconciliation tính theo tập sau filter |
| Retry DLQ/poison message | Không publish kết quả thiếu; có runbook xử lý |

### Khi nào job thực sự hoàn tất?

Tùy nghiệp vụ, một job có thể có Step `COMPLETED` nhưng các message bắt buộc còn trong DLQ hoặc side effect pending. Không nên công bố dữ liệu cuối chỉ dựa vào trạng thái Batch; cần gate business và đối soát.

### Idempotent không đồng nghĩa “không có duplicate assignment”

Writer upsert có thể khiến **bảng đích** không trùng, nhưng hai worker vẫn đọc và tính toán cùng record. Nếu processor gọi API hoặc tạo event, duplicate assignment có thể gây hậu quả. Phải sửa lỗi manifest/reader ở tầng phân công thay vì chỉ dựa vào unique constraint.

### Reprocess khác restart

Restart giữ identifying `JobParameters` của `JobInstance` và dùng state đã lưu. Một lần chạy với identifying `run.id` mới thường tạo instance mới, có thể quét lại toàn bộ snapshot; phải có chính sách output dedup, side effect và reconciliation riêng. Đừng gọi đó là resume checkpoint cũ.

## 17. Hiệu năng của coverage validation và cách đặt gate đúng lifecycle

Với 40 triệu record và 80 partition, record-level assignment join trên toàn snapshot có thể tiêu tốn I/O. Tuy nhiên bỏ hoàn toàn validation dễ làm mất dữ liệu chỉ được phát hiện sau nhiều ngày.

Gợi ý chia tầng kiểm chứng:

| Tầng | Thời điểm | Chi phí tương đối | Phát hiện |
| --- | --- | --- | --- |
| Range sanity | Trước READY/dispatch | Thấp | Gap/overlap và biên manifest |
| Per-partition count | Sau capture, trước READY | Thấp–trung bình tùy index | Count lệch từng range |
| Record assignment audit | Trước READY hoặc audit theo block | Trung bình–cao | Record không được giao hoặc giao nhiều lần |
| Worker metadata | Trong khi chạy | Thấp | Worker chậm/lỗi và tiến độ |
| Business reconciliation | Sau các worker, trước publish | Tùy số bản ghi/index | Thiếu, thừa, sai version/payload |
| Monitoring sampling | Liên tục | Thấp nếu sampling đúng | Cảnh báo sớm, **không phải chứng minh toàn bộ** |

### Phép tính sizing minh họa

Giả sử:

~~~text
Snapshot: 40.000.000 record
Partitions: 80
Số record trung bình: 500.000 / partition
Worker slots: 8
Mỗi partition tốn 120 giây (giả định cân bằng)

Số wave lý tưởng: 80 / 8 = 10
Thời gian processing lý tưởng:
10 * 120 = 1.200 giây = 20 phút
~~~

Đây là ước lượng **lý tưởng**, chưa tính skew, transaction, DB contention, checkpoint, dispatch và reconciliation. Nếu gate coverage mất 90 giây nhưng tránh một lần backfill hàng chục triệu record, chi phí đó có thể hợp lý.

Điều không hợp lý là để **mỗi worker quét lại toàn bộ snapshot ở mỗi chunk** để kiểm tra coverage; chi phí sẽ tăng theo số chunk và worker. Hãy đặt gate pre-dispatch một lần trên manifest, còn output reconciliation chạy khi dữ liệu đã sẵn sàng.

### Resource limits khi scale

- `gridSize` không đồng nghĩa số thread/pod.
- `JdbcCursorItemReader` có thể giữ connection/cursor; nhiều worker tiêu thụ thêm pool DB.
- `JobRepository` ghi metadata theo step/chunk; quá nhiều partition và commit rất nhỏ tăng overhead.
- SQL join coverage cần index/planner hợp lý, tránh cạnh tranh IO cực mạnh với business workload giờ cao điểm.
- Range được chia theo độ rộng ID có thể rất lệch record count. Đo `expectedCount`/byte và duration per partition.
- Tăng worker khi writer DB đã đạt trần có thể làm lock wait, deadlock và retry tăng, không tăng throughput hữu ích.

## 18. Observability: chỉ số và ngưỡng dừng publish

Một bộ chỉ số thực tế (tên metric là gợi ý, không mặc định có sẵn):

| Metric | Ý nghĩa |
| --- | --- |
| `snapshot_expected_records` | Số record đầu vào thuộc snapshot |
| `partition_manifest_total` | Số partition cần được dispatch |
| `partition_gap_total` | Số gap tìm thấy ở manifest |
| `partition_overlap_total` | Số overlap tìm thấy |
| `unassigned_record_total` | Record có assignment = 0 |
| `multiple_assignment_record_total` | Record có assignment > 1 |
| `partition_failed_total` | Partition không hoàn tất theo policy |
| `output_missing_key_total` | Business key bắt buộc bị thiếu |
| `output_extra_key_total` | Key đích không có trong expected set |
| `output_version_mismatch_total` | Sai source version/payload |
| `reconciliation_duration_seconds` | Tác động của audit vào critical path |
| `unique_business_items_committed_per_second` | Throughput hữu ích, không đếm retry như work mới |

Đừng dùng `orderId`, `customerId` hoặc input key cardinality cao làm nhãn metric time-series. Muốn điều tra key cụ thể, dùng log/audit có quyền và dữ liệu đã được làm sạch.

**Gates nên có:**

1. **Trước worker:** snapshot READY, range sanity PASS, expected counts/record assignment theo policy PASS.
2. **Sau worker:** toàn bộ required partitions đã đạt trạng thái hợp lệ và các retry/DLQ quan trọng được xử lý.
3. **Trước publish:** business output reconciliation PASS theo đúng filter/transform contract.
4. **Sau sự cố:** giữ snapshot, manifest, execution metadata và đối soát để có thể tái lập.

Một `JobExecution` có status `COMPLETED` nhưng `output_missing_key_total > 0` không nên tự động publish dữ liệu như thể đã đầy đủ.

## 19. Runbook khi coverage không đạt

Khi validator phát hiện gap/overlap hoặc output thiếu record:

1. **Xác định `snapshotId`, `JobInstance`, `JobExecution`, step/partition name và version triển khai.**
2. **Ngừng publish kết quả sai** và hạn chế dispatch thêm nếu manifest đã hỏng.
3. **Giữ bằng chứng:** bản manifest, snapshot version, metadata `StepExecution`, query kết quả và log an toàn.
4. **Phân loại lỗi theo ba lớp:** interval sai, predicate assignment sai hay writer/output sai.
5. **Kiểm tra SQL thực tế:** `>= start`, `< end`, điều kiện tenant, timestamp precision, NULL và collation.
6. **Kiểm tra nguồn:** snapshot READY có thật sự bất biến không? Có insert commit muộn hoặc source drift không?
7. **Kiểm tra checkpoint/restart:** tên/range/sort key có bị đổi nghĩa so với attempt trước không?
8. **Kiểm tra concurrency:** worker cũ còn sống, duplicate delivery/reply hay transaction chưa hoàn tất?
9. **Đối soát business key, payload/version và side effect ngoài DB.**
10. **Chọn cách phục hồi có chủ đích:** backfill tập key thiếu với writer idempotent hoặc reprocess snapshot/job plan mới.
11. **Không xóa bảng `BATCH_*` hoặc sửa serialized checkpoint trực tiếp** để “reset” trạng thái.
12. **Thử cách sửa trên staging** với chính snapshot, ID biên và failure window gây lỗi.
13. **Bổ sung regression test**, rồi chạy lại pre-dispatch và business reconciliation gates.
14. **Đóng sự cố** chỉ khi đã chứng minh input assignment và output đúng; giữ audit phù hợp.

### Vì sao không sửa manifest đang chạy?

Nếu worker `partition0001` đã commit 80 chunk với `[251,501)` mà bạn đổi partition đó thành `[301,551)` trong cùng `JobInstance`, checkpoint của reader có thể nằm giữa tập dữ liệu cũ. Đổi mapping trực tiếp không giúp “tự động xử lý lại những record thiếu”; nó có thể tạo **lỗi mới** và duplicate.

Nếu cần sửa phân chia, thiết kế một **job plan mới** hoặc backfill nhắm đúng business keys với quyền và ledger rõ ràng. Phân biệt restart bằng checkpoint với reprocess toàn bộ dữ liệu.

## 20. Bài tập tình huống

Snapshot có các ID:

~~~text
1, 2, 3, 5, 7, 8, 10, 11, 16, 18, 19
~~~

Global range `[1,20)`. Manifest ban đầu:

~~~text
partition0000 = [1,7)
partition0001 = [7,13)
partition0002 = [13,20)
~~~

Sau một lỗi deploy, manifest bị thay thành:

~~~text
partition0000 = [1,7)
partition0001 = [8,13)
partition0002 = [12,20)
~~~

Một phiên bản worker khác lại đổi SQL thành `order_id <= endExclusive`. Một partition đã `COMPLETED`, một partition đang cần restart.

**Câu hỏi:**

1. Theo manifest **đúng** và predicate `>= start AND < end`, mỗi worker nhận những ID nào?
2. Với manifest **lỗi**, ID nào bị thiếu assignment?
3. Manifest lỗi có overlap ở miền khóa không? Overlap đó có chứa record thật trong snapshot này không?
4. Nếu worker dùng `<= endExclusive` trên manifest đúng, ID biên nào có thể bị đọc trùng?
5. Vì sao tổng assignment count có thể vẫn bằng snapshot count dù có missing và overlap?
6. Nếu `partition0001` `COMPLETED` nhưng output thiếu ID 10, phải điều tra những lớp nào?
7. Nếu chunk chứa ID 10 commit thành công nhưng worker chết trước metadata update, restart phải bảo vệ điều gì?
8. Nếu tăng worker slots từ 3 lên 12 mà không đổi manifest, tập input assignment có cần đổi không?
9. Nếu ID 4 commit vào source **sau** snapshot READY, có mặc nhiên thuộc snapshot cũ không?
10. Nếu processor lọc record `status=INVALID`, có nên yêu cầu `sourceCount=outputCount`?

### Gợi ý đáp án

- **(1)** P0: `1,2,3,5`; P1: `7,8,10,11`; P2: `16,18,19`.
- **(2)** ID `7` không thuộc P0 (đã end-exclusive) cũng không thuộc P1 (bắt đầu 8).
- **(3)** Hai range P1 `[8,13)` và P2 `[12,20)` overlap miền `[12,13)`. Snapshot hiện không có ID 12 nên **range sai** nhưng không có duplicate assignment thực tại ID 12.
- **(4)** ID `7` ở cuối P0/đầu P1 và có thể bị trùng khi P0 dùng `<=7`. ID 13 cũng là biên lý thuyết nhưng snapshot không có ID 13.
- **(5)** Một record gán 0 lần và một record gán 2 lần khiến tổng không đổi.
- **(6)** Range/assignment có thể đúng, nhưng reader, processor, writer, transaction, checkpoint hoặc filter đều có thể gây output thiếu. Cần so business key và version.
- **(7)** Writer idempotent theo business key, checkpoint trong đúng snapshot/range, không tạo side effect lặp.
- **(8)** Không. Số slot thực thi có thể thay đổi nhưng mapping các partition đã chốt phải ổn định khi restart.
- **(9)** Không mặc định. Membership của snapshot cố định; late commit phải theo delta/reprocess policy.
- **(10)** Không nếu filter là hợp lệ. Cần tính expected output sau filter rồi đối soát kết quả thật.

## Checklist trước production

- [ ] Input membership và content version được chốt theo `snapshotId`.
- [ ] Manifest giữ tên, số lượng và ranh giới ổn định cho cùng `JobInstance`.
- [ ] Kiểm tra global first/end, adjacency và độ rộng hợp lệ với range partition.
- [ ] Record-level audit kiểm tra **assignment = 1**; không chỉ so tổng count.
- [ ] Expected counts được tính từ snapshot thật, không từ độ rộng ID interval.
- [ ] Với hash/composite/NULL/timestamp có oracle tương ứng và semantics thống nhất.
- [ ] Reader `@StepScope` dùng đúng `StepExecutionContext` và predicate giống validator.
- [ ] Paging/checkpoint có sort key duy nhất và phục hồi theo commit hợp lệ.
- [ ] Writer chống replay theo business key; side effect ngoài DB có ledger/outbox khi cần.
- [ ] Reconciliation kiểm tra missing/extra/wrong version theo đúng filter/transform contract.
- [ ] Gates không cho publish kết quả thiếu dù worker `COMPLETED`.
- [ ] Đã test crash trước/sau commit, redelivery, restart và thay số worker slots.
- [ ] Có ngân sách CPU/DB/metadata, chỉ số coverage và runbook điều tra.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): `Partitioner`, local/remote partitioning, `StepExecution` và các giới hạn scaling.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): API manager/worker trong dòng 5.x.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `StepExecution` và `ExecutionContext`.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): `JdbcCursorItemReader`, `ItemStream` và checkpoint.
- [Spring Batch Reference – Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và worker parameters.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking.
- [PostgreSQL – Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): range predicates, `BETWEEN` và NULL semantics.
- [PostgreSQL – Window Functions](https://www.postgresql.org/docs/current/functions-window.html): `LAG` và thứ tự các range.
- [PostgreSQL – UNION, INTERSECT, EXCEPT](https://www.postgresql.org/docs/current/queries-union.html): đối soát tập key và multiplicity.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): consistency của source snapshots.
- [Java SE 17 – Date and Time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): `Instant`, `LocalDate` và `ZoneId`.

## Ghi nhớ

**Kiểm chứng coverage của partition không chỉ là nhìn tổng số bản ghi các worker đã đọc.** Cần ba mức kiểm chứng: (1) các range bao phủ miền và không overlap; (2) từng record của immutable snapshot có **đúng một assignment**; (3) output nghiệp vụ đầy đủ, đúng version và không có side effect sai sau retry/restart. Giữ snapshot, tên partition, boundary và checkpoint ổn định trong cùng `JobInstance`. Tăng concurrency chỉ đáng giá khi các phép kiểm chứng trên vẫn đạt: **hệ thống phải nhanh hơn mà không bỏ sót, không nhân đôi hoặc làm sai kết quả nghiệp vụ**.
