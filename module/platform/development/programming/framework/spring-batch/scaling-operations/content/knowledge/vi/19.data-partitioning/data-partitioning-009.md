# Snapshot phạm vi dữ liệu trước khi partitioning trong Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **snapshot phạm vi dữ liệu** là gì và vì sao nó là điều kiện để chia dữ liệu, restart và đối soát kết quả chính xác khi Spring Batch chạy song song.
- Phân biệt **chốt tập khóa đầu vào**, **chốt giá trị/phiên bản bản ghi**, **snapshot transaction của database**, **snapshot materialized** và **watermark**; nhận diện những đảm bảo mà từng kỹ thuật **không** cung cấp.
- Xác định ranh giới dữ liệu theo snapshot ID, business window, khoảng ID, file manifest hoặc CDC offset, kể cả khi dữ liệu nguồn đang thay đổi.
- Thiết kế bảng snapshot và **manifest partition bất biến**, bao phủ đầy đủ, không chồng lấn; dùng `Partitioner` giao các ranh giới qua `StepExecutionContext`.
- Xây dựng ví dụ Spring Batch **5.x / Java 17** với manager step, worker step, reader `@StepScope`, writer idempotent và `TaskExecutor` có giới hạn.
- Phân tích ảnh hưởng của isolation level, checkpoint `ItemStream`, transaction, retry/restart và việc worker chạy trên nhiều JVM.
- Lập kế hoạch retention, dung lượng, quyền truy cập, kiểm thử lỗi và đối soát dữ liệu để lựa chọn kiến trúc mở rộng phù hợp.

## 1. Vấn đề: dữ liệu nguồn thay đổi khi job đang chạy

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, một job phải xử lý 10 triệu đơn hàng. Để giảm thời gian, nhóm phát triển chia dữ liệu thành bốn partition và chạy bốn worker cùng lúc.

Nếu mỗi worker truy vấn trực tiếp bảng `source_order` đang được hệ thống giao dịch cập nhật, có thể xảy ra:

- **Insert mới trong lúc chạy**: một worker thấy bản ghi mới, worker khác không thấy; lần restart có thể quét tập dữ liệu khác.
- **Update bản ghi cũ**: worker A đọc giá trị trước update, worker B đọc giá trị sau update, nên kết quả tổng hợp không cùng một thời điểm logic.
- **Delete**: bản ghi biến mất trước khi worker đọc tới dù nó thuộc phạm vi ban đầu.
- **Đổi khóa phân vùng**: một record chuyển từ miền của worker A sang worker B, có thể bị bỏ sót hoặc xử lý hai lần.
- **Restart từ checkpoint**: reader trở lại “vị trí cũ” nhưng thứ tự hoặc số lượng record đã thay đổi.

~~~mermaid
sequenceDiagram
    participant T as Transactional app
    participant S as Source DB
    participant W0 as Worker partition 0
    participant W1 as Worker partition 1
    T->>S: Có các đơn hàng version 1
    W0->>S: Đọc các ID nhỏ
    S-->>W0: Order 100 / version 1
    T->>S: Update order 900000 / version 2
    W1->>S: Đọc các ID lớn
    S-->>W1: Order 900000 / version 2
    Note over W0,W1: Hai worker có thể thấy những phiên bản khác nhau
~~~

Hai worker xử lý thành công về mặt kỹ thuật **không chứng minh** chúng đã xử lý cùng một tập dữ liệu nhất quán.

**Giải pháp nền tảng:** xác định một **snapshot logic của công việc** trước khi fan-out, rồi giao những miền dữ liệu ổn định cho các worker. Mọi lần retry/restart của **cùng `JobInstance`** phải tiếp tục trên snapshot ấy, thay vì tự xác định lại phạm vi đầu vào.

## 2. “Snapshot phạm vi dữ liệu” gồm những điều gì?

Trong hệ batch, snapshot là **một hợp đồng về dữ liệu đầu vào của một lần xử lý logic**. Tùy nghiệp vụ, hợp đồng phải nêu rõ:

| Khía cạnh | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Membership** | Những bản ghi nào thuộc lần chạy này? | Tất cả order của snapshot `snap-20261125-01` |
| **Version/content** | Giá trị bản ghi ở phiên bản nào? | `source_version` và `payload` tại lúc capture |
| **Boundaries** | Ranh giới mỗi partition nằm ở đâu? | `[1, 2_500_001)`, `[2_500_001, 5_000_001)` |
| **Ordering** | Reader resume dựa trên thứ tự nào? | `ORDER BY id` với khóa duy nhất |
| **Identity** | Lần chạy lại nhận diện snapshot bằng gì? | Identifying `JobParameter snapshotId` |
| **Lifecycle** | Snapshot sẵn sàng, bất biến và được giữ tới khi nào? | `BUILDING → READY → EXPIRED` theo chính sách |
| **Consistency** | Snapshot có đại diện cho một thời điểm đồng nhất không? | DB materialization trong transaction có isolation phù hợp |
| **Reconciliation** | Làm sao chứng minh đã xử lý đủ? | Expected count, business keys, version và checksum |

**Tập dữ liệu ổn định** không đồng nghĩa **giá trị bản ghi ổn định**. Ví dụ danh sách 10 triệu order ID đã chốt nhưng worker vẫn đọc `source_order.payload` bản mới nhất; phép xử lý này có membership cố định nhưng **không có content snapshot**.

### Bốn hình thức thường gặp

| Kỹ thuật | Điều chốt được | Điều không tự bảo đảm |
| --- | --- | --- |
| **ID high-watermark** (`id <= maxId`) | Chặn một số insert có ID lớn hơn watermark | Không ngăn update/delete record cũ; ID có thể commit muộn hoặc được chèn lệch thứ tự |
| **Time watermark** (`updated_at < cutoff`) | Xác định predicate theo mốc thời gian | Timestamp không tự chứng minh dữ liệu nhất quán; update lại làm record ra khỏi predicate |
| **Database MVCC snapshot** | Một góc nhìn dữ liệu nhất quán **trong transaction/snapshot** theo DB và isolation level | Các worker/transaction khác không tự chia sẻ cùng MVCC snapshot; transaction dài tạo chi phí |
| **Materialized immutable snapshot** | Tập khóa và nội dung được copy/chốt tại một version | Cần lưu trữ, thời gian capture, quyền truy cập và retention |
| **Versioned files/manifest** | Danh sách file/object versions và thứ tự được đóng băng | Không bảo vệ nếu dùng file mutable hoặc URL không giữ version |
| **CDC position + consistent snapshot** | Ranh giới chụp ban đầu và thay đổi kể từ log position | Cần protocol CDC đúng, retention log, dedup và ordering |

Không có lựa chọn nào mặc nhiên đúng cho mọi workload. Phần còn lại dùng **materialized snapshot + immutable manifest** làm ví dụ rõ ràng để phân tích correctness; sau đó bàn khi nào chọn watermark, file manifest hoặc CDC.

## 3. Các bất biến cần quyết định trước khi chia partition

Đối với một `snapshotId` cố định, cần có các bất biến có thể **kiểm thử**, không chỉ là quy ước trên giấy.

1. **Danh tính bất biến:** `snapshotId` định danh duy nhất một input đã chốt; không tái sử dụng ID cũ để trỏ tập mới.
2. **Tập đầu vào bất biến:** record của snapshot không bị thêm, sửa, xóa trong suốt thời gian job có thể restart.
3. **Ranh giới deterministic:** cùng partition name luôn tương ứng cùng miền dữ liệu trong các attempt của một `JobInstance`.
4. **Coverage:** mọi business key phải thuộc ít nhất một partition được dự kiến xử lý.
5. **Disjointness:** mỗi key thuộc **tối đa một** partition nếu không có thiết kế dedup/chia sẻ rõ ràng.
6. **Thứ tự đọc xác định:** `ORDER BY` trên khóa hoặc bộ khóa duy nhất, tương thích checkpoint.
7. **Writer replay-safe:** replay cùng bản ghi snapshot không nhân đôi hiệu ứng.
8. **Nguồn bền vững:** cả local và remote worker đều truy cập được đúng snapshot/version.
9. **Không công bố sớm:** worker chỉ bắt đầu khi manifest có trạng thái `READY` và đã được validate.
10. **Retention đủ lâu:** snapshot không biến mất khi worker fail, job restart hoặc cần đối soát theo chính sách.
11. **Bảo vệ an toàn:** snapshot và manifest tuân thủ quyền truy cập, tránh vô tình nhân bản dữ liệu nhạy cảm.

~~~mermaid
flowchart LR
    S["Source đang thay đổi"] --> C["Capture snapshot / versioned manifest"]
    C --> V["Validate: count, coverage, version"]
    V --> R["READY: bất biến"]
    R --> P["Partitioner: tên + ranh giới"]
    P --> W0["Worker 0"]
    P --> W1["Worker 1"]
    P --> W2["Worker N"]
    W0 --> O["Output idempotent"]
    W1 --> O
    W2 --> O
    O --> X["Reconciliation / Job completion"]
~~~

Nếu business logic không cần nội dung tại cùng một thời điểm, có thể nới điều kiện version/content, **nhưng phải ghi rõ** đó là một mô hình nhất quán khác; không dùng thuật ngữ “snapshot hoàn chỉnh” để che đi mức đảm bảo yếu hơn.

## 4. Ví dụ thiết kế: chốt snapshot trước khi manager step chạy

Giả sử bảng nguồn PostgreSQL:

~~~sql
CREATE TABLE source_order (
    id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
~~~

Ứng dụng có thể tiếp tục `INSERT`, `UPDATE` hoặc `DELETE` ở bảng này. Job Batch sẽ **không** đọc trực tiếp dữ liệu đang thay đổi sau khi snapshot được chốt.

Chúng ta sử dụng:

- `batch_snapshot_manifest`: một record cho mỗi snapshot, với lifecycle và expected count.
- `batch_snapshot_order`: bản sao vật lý của **ID, version và payload**.
- `batch_snapshot_partition`: danh sách partition name, range và expected count.
- `batch_order_result`: output có unique business key để replay an toàn.

### Schema PostgreSQL minh họa

~~~sql
CREATE TABLE batch_snapshot_manifest (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('BUILDING', 'READY', 'EXPIRED')),
    start_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL DEFAULT 0
        CHECK (expected_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMPTZ,
    CHECK (start_inclusive < end_exclusive)
);

CREATE TABLE batch_snapshot_order (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_snapshot_manifest(snapshot_id),
    id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);

CREATE TABLE batch_snapshot_partition (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_snapshot_manifest(snapshot_id),
    partition_name VARCHAR(100) NOT NULL,
    start_id BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL CHECK (expected_count >= 0),
    PRIMARY KEY (snapshot_id, partition_name),
    CHECK (start_id < end_exclusive)
);

CREATE INDEX ix_snapshot_partition_range
    ON batch_snapshot_partition(snapshot_id, start_id);

CREATE TABLE batch_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);
~~~

`batch_snapshot_order` có index theo `(snapshot_id, id)` từ primary key, phù hợp query range của worker. `batch_snapshot_partition` lưu ranh giới đủ nhỏ để không phải serialize toàn bộ record vào `ExecutionContext`.

**Lưu ý:** `CHECK (start_id < end_exclusive)` chỉ đảm bảo range có độ dài dương, **không tự đảm bảo** hai hàng không overlap hay bao phủ hết miền. Cần validation có chủ đích hoặc constraint bổ sung phù hợp DB. Mục 7 sẽ nêu quy tắc kiểm tra.

### Vì sao không lưu toàn bộ danh sách record vào ExecutionContext?

Một partition có thể chứa hàng triệu record. `ExecutionContext` là metadata checkpoint, không phải kho dữ liệu hàng loạt. Chỉ lưu `snapshotId`, ranh giới ID, input key nhỏ và state của `ItemStream`; payload nằm trong bảng snapshot hoặc object storage được version hóa.

## 5. Materialize snapshot nhất quán trong PostgreSQL

Một cách đơn giản cho bài toán minh họa là **copy từ bảng nguồn vào bảng snapshot trong một transaction có isolation phù hợp**, sau đó đánh dấu manifest `READY` **sau khi** có dữ liệu và partition mapping hợp lệ.

Giả sử business window yêu cầu các ID trong miền `[1, 10_000_001)`. Một workflow SQL ý tưởng:

~~~sql
-- Các tham số :snapshotId là bind parameters của ứng dụng
-- (chẳng hạn NamedParameterJdbcTemplate), không phải cú pháp psql thuần.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

INSERT INTO batch_snapshot_manifest(
    snapshot_id, state, start_inclusive, end_exclusive
)
VALUES (:snapshotId, 'BUILDING', 1, 10000001);

INSERT INTO batch_snapshot_order(
    snapshot_id, id, source_version, payload
)
SELECT :snapshotId, id, source_version, payload
FROM source_order
WHERE id >= 1 AND id < 10000001;

-- Thêm bốn range, mỗi range được dùng đúng một lần
-- trong cùng transaction; ví dụ một range:
INSERT INTO batch_snapshot_partition(
    snapshot_id, partition_name, start_id,
    end_exclusive, expected_count
)
SELECT :snapshotId, :partitionName, :startId,
       :endExclusive, COUNT(*)
FROM batch_snapshot_order
WHERE snapshot_id = :snapshotId
  AND id >= :startId AND id < :endExclusive;

-- Lặp thao tác trên cho bốn partition có ranh giới
-- [1,2500001), [2500001,5000001),
-- [5000001,7500001), [7500001,10000001).
-- Sau khi ứng dụng kiểm tra coverage/disjointness:

UPDATE batch_snapshot_manifest
SET expected_count = (
        SELECT COUNT(*)
        FROM batch_snapshot_order
        WHERE snapshot_id = :snapshotId
    ),
    state = 'READY',
    ready_at = CURRENT_TIMESTAMP
WHERE snapshot_id = :snapshotId
  AND state = 'BUILDING';

COMMIT;
~~~

Ví dụ mô tả **trình tự transaction và các câu SQL được ứng dụng gọi với bind parameters**, không phải một script có thể paste vào `psql` mà không thay tham số/không lặp đủ range. Trong ứng dụng, nên dùng transaction manager thống nhất để chạy tất cả bước. Nếu validation thất bại, **rollback**, không chuyển `READY`.

Trong PostgreSQL, `REPEATABLE READ` giúp các truy vấn đọc trong **cùng transaction** thấy một MVCC snapshot ổn định theo semantics của DB. Khi copy xong và commit, `batch_snapshot_order` trở thành nguồn đã materialize, nên **worker không cần giữ transaction dài của bước capture**.

### Những điều isolation không tự giải quyết

- Một transaction `REPEATABLE READ` trên manager **không tự chia sẻ MVCC snapshot** với bốn worker trong các transaction khác.
- Nếu copy theo **nhiều transaction độc lập**, mỗi transaction có thể thấy một thời điểm khác; khi đó phải có cơ chế source version/CDC hoặc reconciliation để đạt consistency.
- Nếu dữ liệu cần chụp nằm ở **nhiều database**, một transaction của PostgreSQL không tự bảo đảm atomic snapshot xuyên DB.
- Transaction capture rất dài có thể giữ phiên bản MVCC cũ, làm tăng chi phí vacuum/bloat, WAL, lock/resource và thời gian hoàn thành. Phải đo và chọn chiến lược phù hợp.
- Cột `ready_at` là mốc **manifest sẵn sàng**, không nên diễn giải máy móc là “thời điểm mọi nguồn bên ngoài cùng được chụp”.
- Việc bảng snapshot **không bị sửa sau READY** vẫn cần enforcement bằng quyền, service, transaction/policy hoặc thiết kế immutable storage. Schema ở trên chưa có trigger ngăn update/delete sau READY.

### READY phải là ranh giới công bố dữ liệu

Có hai kiểu triển khai:

1. **Một transaction capture:** tất cả dữ liệu + partition ranges + manifest `READY` cùng commit. Những reader chạy bình thường ở isolation thích hợp sẽ không thấy một snapshot mới công bố ở trạng thái thiếu dữ liệu.
2. **Nhiều batch copy hoặc object storage:** tạo `BUILDING`, copy từng phần ra kho bền vững, kiểm chứng manifest/version/count/checksum, rồi **công bố READY bằng bước cuối**. Khi copy và công bố nằm ở hệ thống khác nhau, không có atomic transaction tổng thể; cần protocol publish và guard không cho worker đọc trước khi đủ dữ liệu.

Với phương án nhiều transaction, cần thêm một **snapshot generation/version** rõ ràng. Một run bị hỏng không được dùng lại cùng `snapshotId` với nội dung khác rồi đánh dấu READY.

## 6. Manifest partition cố định: chia việc chứ không tính lại nguồn

Ví dụ bốn partition của miền `[1, 10_000_001)`:

| Partition | `start_id` | `end_exclusive` | Điều kiện đọc |
| --- | ---: | ---: | --- |
| `partition0000` | 1 | 2500001 | `id >= 1 AND id < 2500001` |
| `partition0001` | 2500001 | 5000001 | `id >= 2500001 AND id < 5000001` |
| `partition0002` | 5000001 | 7500001 | `id >= 5000001 AND id < 7500001` |
| `partition0003` | 7500001 | 10000001 | `id >= 7500001 AND id < 10000001` |

Sử dụng quy ước **đầu bao gồm, cuối không bao gồm** (`[startId, endExclusive)`) giúp tránh record biên bị đọc hai lần.

Với bảng snapshot có ID thưa, các range có thể chứa số record khác nhau. Ví dụ 90% dữ liệu nằm ở đoạn ID cuối, `partition0003` sẽ chậm hơn. Cần chia theo **phân bố/chi phí thật** nếu muốn cân bằng, nhưng mapping đã dùng cho một `JobInstance` phải giữ ổn định khi restart.

### Ba lớp định danh

| Thành phần | Ví dụ | Bất biến restart |
| --- | --- | --- |
| Job identifying parameter | `snapshotId=snap-20261125-01` | Cùng dữ liệu logic, không gán lại snapshot mới |
| Tên partition | `partition0002` | Cùng tên → cùng miền dữ liệu |
| Worker StepExecutionContext | `startId=5000001`, `endExclusive=7500001` | Biên của partition không đổi |
| ItemStream checkpoint | `snapshotReader.read.count` | Khôi phục tiến độ **trong** miền ấy |
| Business output key | `(snapshotId,id)` | Replay cùng item không nhân đôi hiệu ứng |

**Cảnh báo:** nếu job restart mà manager tính lại `MAX(id)` từ bảng nguồn đang thay đổi, `partition0002` có thể nhận range mới. Reader checkpoint cũ lúc đó không còn tham chiếu chính xác tập dữ liệu của nó.

### Chốt partition name trước khi chạy

Các partition name nên deterministic (`partition0000`, `partition0001`), dựa vào danh sách đã ghi trong manifest. Không tạo tên mới theo timestamp/UUID mỗi lần gọi `Partitioner.partition()`. Nếu sử dụng `PartitionNameProvider` để tối ưu restart, tên nó trả về phải khớp tên đã tạo lúc phân công lần đầu.

Đối với bảng partition có hàng nghìn miền, việc chốt danh sách partition trước vẫn có lợi: một lần chạy lại không bị “trượt” vì kế hoạch phân chia mới, mặc dù có thể cần chiến lược rebalancing **cho một JobInstance mới**.

## 7. Kiểm tra coverage và disjointness trước khi READY

Chỉ có `COUNT(*)` bằng nhau là chưa đủ: hai partition có thể chồng lấn hai record và một partition khác bỏ sót đúng hai record; tổng count giả có thể vẫn khớp.

### Kiểm tra tính liên tục của range

Với các interval `[start_id,end_exclusive)` đã sắp xếp, để chúng **bao phủ chính xác toàn miền** của manifest:

1. `start_id` của partition đầu phải bằng `start_inclusive` của manifest.
2. Với mọi partition kế tiếp, `start_id` phải bằng `end_exclusive` của partition ngay trước.
3. `end_exclusive` của partition cuối phải bằng giá trị của manifest.
4. Mỗi range phải có `start_id < end_exclusive`.
5. Tên partition duy nhất và không bị đổi nghĩa giữa các lần chạy.

Ví dụ query phát hiện “gap” hoặc overlap bằng window function PostgreSQL:

~~~sql
WITH ordered AS (
    SELECT partition_name, start_id, end_exclusive,
           LAG(end_exclusive) OVER (
               ORDER BY start_id, end_exclusive, partition_name
           ) AS prior_end
    FROM batch_snapshot_partition
    WHERE snapshot_id = :snapshotId
)
SELECT *
FROM ordered
WHERE prior_end IS NOT NULL
  AND start_id <> prior_end;
~~~

Kết quả **0 hàng** chỉ chứng minh không có gap/overlap **giữa các range liền kề**; vẫn phải kiểm tra **biên đầu/cuối** so với manifest. Nếu chỉ có một range hoặc thiếu range đầu/cuối, query trên có thể vẫn trả 0 hàng.

### Kiểm tra expected count

~~~sql
SELECT
    m.snapshot_id,
    m.expected_count AS total_snapshot_rows,
    COALESCE(SUM(p.expected_count), 0) AS assigned_rows
FROM batch_snapshot_manifest m
LEFT JOIN batch_snapshot_partition p
  ON p.snapshot_id = m.snapshot_id
WHERE m.snapshot_id = :snapshotId
GROUP BY m.snapshot_id, m.expected_count;
~~~

Hai số phải bằng nhau sau khi manifest đã có đủ partition. Với các miền liên tục bao phủ toàn snapshot và expected counts được tính từ bảng snapshot bất biến, phép đối chiếu này là bằng chứng hữu ích.

Nếu cần kiểm tra độc lập ở mức record trong staging hoặc khi phát hiện lỗi chia:

~~~sql
WITH assignments AS (
    SELECT s.id, COUNT(p.partition_name) AS assigned_count
    FROM batch_snapshot_order s
    LEFT JOIN batch_snapshot_partition p
      ON p.snapshot_id = s.snapshot_id
     AND s.id >= p.start_id
     AND s.id < p.end_exclusive
    WHERE s.snapshot_id = :snapshotId
    GROUP BY s.id
)
SELECT
    COUNT(*) FILTER (WHERE assigned_count = 0) AS missing,
    COUNT(*) FILTER (WHERE assigned_count > 1) AS duplicate
FROM assignments;
~~~

Kỳ vọng `missing = 0` và `duplicate = 0`. Truy vấn có thể tốn chi phí với nguồn cực lớn; production có thể kết hợp kiểm tra range ở metadata với phép đối soát mẫu/chunk và toàn bộ output theo chính sách, nhưng không được bỏ qua invariant correctness.

## 8. Java: Partitioner đọc manifest đã chốt

Ví dụ sau áp dụng API phổ biến **Spring Batch 5.x, Java 17**. `Partitioner` đọc bảng `batch_snapshot_partition` của snapshot đã `READY` và chỉ đưa **tham số nhỏ** vào `ExecutionContext`.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.jdbc.core.JdbcTemplate;

record SnapshotRange(
        String name, long startId, long endExclusive,
        long expectedCount) {}

public final class SnapshotManifestPartitioner implements Partitioner {

    private final JdbcTemplate jdbc;
    private final String snapshotId;

    public SnapshotManifestPartitioner(
            JdbcTemplate jdbc, String snapshotId) {
        this.jdbc = jdbc;
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (snapshotId == null || snapshotId.isBlank()) {
            throw new IllegalArgumentException("snapshotId is required");
        }
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Integer readyCount = jdbc.queryForObject("""
            SELECT COUNT(*)
            FROM batch_snapshot_manifest
            WHERE snapshot_id = ? AND state = 'READY'
            """, Integer.class, snapshotId);
        if (readyCount == null || readyCount != 1) {
            throw new IllegalStateException("Snapshot not READY");
        }

        List<SnapshotRange> ranges = jdbc.query("""
            SELECT partition_name, start_id,
                   end_exclusive, expected_count
            FROM batch_snapshot_partition
            WHERE snapshot_id = ?
            ORDER BY start_id
            """,
            (rs, rowNum) -> new SnapshotRange(
                rs.getString("partition_name"),
                rs.getLong("start_id"),
                rs.getLong("end_exclusive"),
                rs.getLong("expected_count")),
            snapshotId);

        if (ranges.isEmpty()) {
            throw new IllegalStateException(
                    "No partitions for snapshot " + snapshotId);
        }

        Map<String, ExecutionContext> parts =
                new LinkedHashMap<>();

        long previousEnd = ranges.get(0).startId();
        for (SnapshotRange range : ranges) {
            if (range.startId() != previousEnd
                    || range.endExclusive() <= range.startId()) {
                throw new IllegalStateException(
                        "Gap, overlap or invalid range");
            }
            ExecutionContext context = new ExecutionContext();
            context.putString("snapshotId", snapshotId);
            context.putLong("startId", range.startId());
            context.putLong("endExclusive", range.endExclusive());
            context.putLong("expectedCount", range.expectedCount());

            parts.put(range.name(), context);
            previousEnd = range.endExclusive();
        }

        // Để ngắn gọn, chưa đối chiếu biên đầu/cuối trong Java.
        // Bước validation ở mục 7 là bắt buộc trước READY.
        return parts;
    }
}
~~~

Mỗi map entry có `new ExecutionContext()` riêng; không được tái sử dụng một object rồi liên tục thay `startId`/`endExclusive`. Tên `range.name()` đến từ manifest **không bị sinh lại** trong mỗi attempt.

Giá trị `gridSize` **không phải số worker thực chạy**. Ví dụ trả tất cả range trong manifest kể cả khi `gridSize=4`; executor/partition handler sẽ giới hạn concurrency. Cách chọn number of partitions ở bước capture cần được cân đối với CPU/DB/metadata overhead.

**Cảnh báo mã ví dụ:** validation trong Java chỉ kiểm tra continuity giữa các row; production phải kiểm tra thêm biên đầu/cuối và số lượng với `batch_snapshot_manifest`, uniqueness của tên, trạng thái READY và tính bất biến của snapshot. `READY` ở đây được xem là một hợp đồng đã được validator bên capture bảo đảm, không phải chỉ một cờ do ai cũng có thể cập nhật.

## 9. Java: reader @StepScope nhận đúng snapshot và range

Một worker step của Spring Batch được gắn một `StepExecutionContext` riêng cho mỗi partition. Bean reader `@StepScope` có thể bind `snapshotId` và boundary, mở cursor **chỉ trên bảng snapshot đã chốt**.

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record SnapshotOrderRow(
        String snapshotId, long id,
        long sourceVersion, String payload) {}

@Configuration
class SnapshotReaderConfiguration {

    @Bean("snapshotReader")
    @StepScope
    JdbcCursorItemReader<SnapshotOrderRow> snapshotReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['startId']}") Long startId,
            @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {

        if (snapshotId == null || snapshotId.isBlank()
                || startId == null || endExclusive == null
                || startId >= endExclusive) {
            throw new IllegalArgumentException(
                    "Invalid snapshot partition context");
        }

        return new JdbcCursorItemReaderBuilder<SnapshotOrderRow>()
                .name("snapshotReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, source_version, payload
                    FROM batch_snapshot_order
                    WHERE snapshot_id = ?
                      AND id >= ?
                      AND id < ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startId);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new SnapshotOrderRow(
                        snapshotId,
                        rs.getLong("id"),
                        rs.getLong("source_version"),
                        rs.getString("payload")))
                .fetchSize(500)
                .saveState(true)
                .build();
    }
}
~~~

- `@StepScope` tạo reader trong scope của **worker `StepExecution`**, nên mỗi partition có cursor và checkpoint riêng.
- Predicate `id >= ? AND id < ?` khớp đúng ranh giới đã chốt.
- `ORDER BY id` xác định thứ tự duy nhất nhờ primary key `(snapshot_id,id)`.
- `.saveState(true)` cho phép `JdbcCursorItemReader` lưu state thông qua `ItemStream` và metadata khi framework quản lý lifecycle đúng.
- `fetchSize(500)` là gợi ý tối ưu JDBC/driver, không phải cam kết mỗi lần mạng luôn fetch đúng 500 row; cần benchmark.

Trong **multi-threaded step** dùng một `StepExecution` cho nhiều thread, `@StepScope` không tự biến reader cursor thành thread-safe. Ví dụ này dựa trên **partitioning**, nơi các worker có `StepExecution` riêng.

### Checkpoint có nghĩa gì khi input đã bất biến?

Khi snapshot và `ORDER BY` cố định, checkpoint theo số item/offset của reader có thể tiếp tục đúng tập. Nếu nguồn còn bị insert/delete, cùng một read count lại có thể chỉ vào record khác. Đó là lý do tính bất biến của snapshot liên quan trực tiếp đến restart.

Với range lớn, một số reader có thể phải điều hướng/skip lại nhiều record để phục hồi cursor, gây chi phí restart đáng kể. Khi yêu cầu RTO thấp, xem xét **keyset paging** (`id > lastCommittedId` trong range) và cơ chế checkpoint được thiết kế/kiểm thử kỹ; không tự lưu `lastReadId` trước commit rồi tưởng rằng nó là `lastCommittedId`.

## 10. Java: writer idempotent, manager step và worker step

Dữ liệu đã chốt vẫn có thể được xử lý **nhiều lần**: worker crash sau DB commit nhưng trước metadata update, retry của step hoặc remote message bị giao lại.

Writer nên có hiệu ứng cuối **ổn định theo business key**. Với snapshot đơn hàng bất biến, ví dụ PostgreSQL:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
class SnapshotWriterConfiguration {

    @Bean("snapshotWriter")
    ItemWriter<SnapshotOrderRow> snapshotWriter(JdbcTemplate jdbc) {
        // Không có mutable currentItem/cursor dùng chung.
        return chunk -> {
            for (SnapshotOrderRow row : chunk) {
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
}
~~~

Trong snapshot bất biến, replay cùng record có **cùng giá trị cuối** ở bảng output. Điều này không tự bảo đảm mọi side effect ngoài DB (HTTP, email, broker, trigger audit) đều idempotent; với những hiệu ứng đó cần transactional outbox, ledger hoặc idempotency key tương ứng.

### Cấu hình local partitioning trong một JVM

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.batch.item.database.JdbcCursorItemReader;

@Configuration
class SnapshotPartitionJobConfiguration {

    @Bean("manifestPartitioner")
    @StepScope
    Partitioner manifestPartitioner(
            JdbcTemplate jdbc,
            @Value("#{jobParameters['snapshotId']}") String snapshotId) {
        return new SnapshotManifestPartitioner(jdbc, snapshotId);
    }

    @Bean("snapshotWorker")
    Step snapshotWorker(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("snapshotReader")
                JdbcCursorItemReader<SnapshotOrderRow> reader,
            @Qualifier("snapshotWriter")
                ItemWriter<SnapshotOrderRow> writer) {

        return new StepBuilder("snapshotWorker", repository)
                .<SnapshotOrderRow, SnapshotOrderRow>chunk(
                        200, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("snapshotExecutor")
    ThreadPoolTaskExecutor snapshotExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("snapshot-part-");
        executor.initialize();
        return executor;
    }

    @Bean("snapshotManager")
    Step snapshotManager(
            JobRepository repository,
            @Qualifier("snapshotWorker") Step worker,
            @Qualifier("manifestPartitioner") Partitioner partitioner,
            @Qualifier("snapshotExecutor") TaskExecutor executor) {

        return new StepBuilder("snapshotManager", repository)
                .partitioner("snapshotWorker", partitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("snapshotImportJob")
    Job snapshotImportJob(
            JobRepository repository,
            @Qualifier("snapshotManager") Step manager) {

        return new JobBuilder("snapshotImportJob", repository)
                .start(manager)
                .build();
    }
}
~~~

Ba class configuration trong mục 9 và 10 được dùng cùng nhau; `SnapshotOrderRow` và `SnapshotManifestPartitioner` được định nghĩa trong các snippet trước. Giả định Spring Boot đã cung cấp `JdbcTemplate`, `DataSource`, `JobRepository`, `PlatformTransactionManager` và sơ đồ metadata Spring Batch. `snapshotId` phải được truyền dưới dạng **identifying `JobParameter`** trỏ vào manifest đã `READY`.

Ví dụ này minh họa logic chính, không triển khai đầy đủ cơ chế tạo snapshot, transaction capture, bảo mật, migration và đối soát thành một project chạy ngay. Những bước đó phải được tích hợp đúng lifecycle trước production.

**Lưu ý version:** API `StepBuilder`/`JobBuilder` trong ví dụ phù hợp với dòng **Spring Batch 5.x**. Trước khi dùng ở Spring Batch 6.x hoặc release khác, đối chiếu lại API, executor semantics và transaction model của phiên bản đó.

## 11. Snapshot và restart: một JobInstance, một phạm vi bất biến

Giả sử các partition của snapshot `snap-20261125-01` có kết quả:

| Partition | Trạng thái khi lỗi | Điều xảy ra khi restart |
| --- | --- | --- |
| `partition0000` | `COMPLETED` | Theo policy mặc định, thường được bỏ qua |
| `partition0001` | `COMPLETED` | Giữ output đã commit |
| `partition0002` | `FAILED` sau 180 chunk đã commit | Tiếp tục từ checkpoint phù hợp hoặc xử lý lại phần chưa chắc chắn |
| `partition0003` | Worker JVM chết khi xử lý chunk | Cần phục hồi metadata và transaction còn dang dở |

Nếu snapshot không đổi, reader của `partition0002` có thể mở lại đúng **cùng range, cùng thứ tự và cùng nội dung**. Nếu lúc restart manager thay `snapshotId` hay dựng lại range từ nguồn, checkpoint trước đó không còn an toàn.

### Phân biệt ba hành động

| Hành động | Nhận diện | Hệ quả |
| --- | --- | --- |
| **Restart** | Cùng `JobInstance`, identifying parameters không đổi | Dùng metadata/checkpoint để phục hồi phần cần chạy |
| **Reprocess snapshot cũ** | Tạo `JobInstance` mới có chủ đích trên cùng snapshot | Có thể quét lại tất cả dữ liệu; phải idempotent/reconcile |
| **Processing snapshot mới** | Snapshot version/ID mới, dữ liệu scope mới | Bắt đầu công việc logic mới với manifest mới |

Một timestamp/`run.id` identifying mới có thể tạo `JobInstance` mới và bỏ qua checkpoint cũ. **Đừng gọi đó là restart** chỉ vì mục đích là “thử lại cho xong”.

### Một số chi tiết dễ sai

- `JobRepository` giữ `StepExecutionContext` riêng cho từng partition; tên context key giống nhau không gây xung đột giữa partitions.
- `ItemStream` lưu state theo lifecycle; một biến `static` hoặc `AtomicLong` trong JVM không phải checkpoint bền vững.
- Nếu business DB và metadata DB nằm ở **hai transaction manager khác nhau**, không mặc định commit writer và checkpoint là atomic. Worker có thể ghi thành công nhưng metadata chưa phản ánh.
- Nếu crash để lại `JobExecution` ở `STARTED`, phải xác minh worker cũ thật sự dừng và dùng runbook/`JobOperator` phù hợp để phục hồi. Không xóa bảng `BATCH_*` để “mở khóa”.
- Khi restart, `PartitionNameProvider` hoặc partitioner phải giữ tên/mapping tương thích; không tự re-partition cùng snapshot đang có execution history.

## 12. Vì sao MAX(id) hoặc updated_at không luôn là snapshot?

### High-watermark chỉ đóng “trần ID”

Giả sử trước khi chạy:

~~~sql
SELECT MAX(id) FROM source_order;  -- Ví dụ trả 10.000.000
~~~

Worker đọc `WHERE id <= 10000000`. Điều này ngăn nhiều insert có ID lớn hơn 10 triệu, nhưng **không ngăn**:

1. Một record ID 900.000 bị update sau khi worker A đọc và trước khi worker B tính aggregate.
2. Một record cũ bị delete trước khi tới lượt worker đọc.
3. Một transaction insert ID nhỏ hơn 10 triệu **commit muộn** sau khi watermark đã được đo.
4. Một record chuyển tenant hoặc khóa partition do nghiệp vụ cập nhật.
5. Một lần retry đọc payload khác trong cùng ID.

Vì thế high-watermark có thể đủ với **nguồn append-only có cam kết ID/commit ordering**, nhưng không mặc nhiên tương đương materialized snapshot.

### Watermark theo thời gian cũng cần hợp đồng

Query:

~~~sql
SELECT id, payload
FROM source_order
WHERE updated_at < :cutoff;
~~~

có thể loại một record ban đầu thuộc tập nếu record đó được update sau cutoff: `updated_at` mới khiến nó không còn match. Ngược lại, hệ thống có backdated timestamp hoặc clock skew có thể đưa record mới vào “quá khứ”.

Nếu business yêu cầu snapshot *as-of* một thời điểm, cần nguồn cung cấp **temporal history**, CDC hoặc dữ liệu versioned để truy lại giá trị tại cutoff; chỉ predicate theo một cột mutable không đủ.

### Có thể dùng transaction snapshot của DB cho toàn job?

Về mặt lý thuyết, một số DB có cơ chế export/share snapshot hoặc temporal query. Nhưng:

- Một transaction `REPEATABLE READ` của manager **không tự lan qua thread/process/connection**.
- Worker cần sử dụng đúng protocol và điều kiện của DB để chia snapshot; không thể chỉ gửi timestamp rồi nghĩ rằng đã chia sẻ MVCC.
- Giữ transaction nhất quán hàng giờ có thể tạo gánh nặng DB, connection, vacuum/retention và khó phục hồi khi JVM chết.
- Với hệ thống distributed nhiều DB, consistency xuyên nguồn càng cần thiết kế riêng.

Materialize snapshot nhanh rồi xử lý nhiều giờ thường dễ restart hơn trong nhiều workload, đổi lại tốn dung lượng và thời gian capture. Nếu không thể materialize, cần chứng minh đảm bảo tương đương bằng công cụ/versioned source cụ thể.

## 13. CDC, event log và snapshot nhiều nguồn

Khi input đến từ database có Change Data Capture (CDC), một mẫu kiến trúc thường là:

1. **Chốt vị trí log/offset phù hợp** theo protocol CDC.
2. **Lấy snapshot nhất quán của dữ liệu ban đầu**, đồng thời theo dõi thay đổi xảy ra trong khoảng capture.
3. **Reconcile các event** để tránh mất hoặc đếm hai lần ở ranh giới snapshot → streaming.
4. Đóng manifest của một **business window** hoặc một `as-of version` có định nghĩa rõ.
5. Cho batch partitioning xử lý manifest bất biến, hoặc tiếp tục streaming riêng.

~~~mermaid
flowchart LR
    DB["Source DB đang thay đổi"] --> SS["Consistent initial snapshot"]
    DB --> LOG["CDC log / offset"]
    SS --> MERGE["Reconcile snapshot ↔ change events"]
    LOG --> MERGE
    MERGE --> MAN["Immutable manifest / version"]
    MAN --> PART["Batch Partitioner"]
    PART --> WORK["Workers"]
~~~

Chi tiết cách lấy consistent snapshot và log position **phụ thuộc DB, connector, isolation và CDC protocol**. Không tự lấy `MAX(id)` cộng với một Kafka offset rồi cho rằng đã có atomic point-in-time snapshot; có thể mất hoặc lặp những transaction đang commit quanh thời điểm chốt.

### Nhiều database hay file nguồn

Một job hợp nhất dữ liệu từ CRM, billing và inventory có thể không có transaction chung. Cần chọn:

- **Eventual-consistent business snapshot**: mỗi nguồn có version riêng, manifest ghi vector version và quy tắc reconcile được doanh nghiệp chấp nhận.
- **As-of snapshot có lịch sử**: các nguồn hỗ trợ time travel/versioned reads với mốc đã thống nhất.
- **Materialization có bước xác nhận**: copy vào staging, kiểm tra completeness, chỉ phát `READY` khi đạt các invariant.
- **Compensation/reconciliation**: khi không thể có một thời điểm chung, phải chấp nhận phát hiện và xử lý sai lệch sau.

Điều quan trọng là **ghi rõ consistency contract**, không tuyên bố mạnh hơn những gì hạ tầng cung cấp.

## 14. Local vs remote partitioning: snapshot giúp gì?

Với **local partitioning**, manager và worker chạy cùng JVM; mỗi worker nhận range riêng và đọc bảng snapshot ổn định. Với **remote partitioning**, các worker chạy trên các JVM/host khác nhau, nhưng vẫn dùng cùng manifest và `snapshotId`.

| Câu hỏi | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Reader chạy ở đâu? | Worker thread cùng JVM | Worker JVM/process khác |
| Nguồn snapshot | Chung DB/storage hoặc datasource | Phải truy cập được qua network/ACL từ từng worker |
| Boundary | `StepExecutionContext` per partition | Cùng logic, metadata/protocol qua mạng |
| Checkpoint | Theo `StepExecution` | Theo `StepExecution` và repository/protocol tương ứng |
| Failure | Một JVM chết ảnh hưởng mọi worker local | Worker mất network/ACK/reply, cần ownership/recovery |
| Bottleneck | CPU/DB/memory một node | DB/metadata/network/broker dùng chung toàn cluster |
| Snapshot immutability | Bắt buộc theo contract | Càng quan trọng vì worker có thể restart trên máy khác |

Snapshot ổn định cho phép **retry/restart đúng dữ liệu**, nhưng không làm các transaction worker trở thành một transaction chung. Worker A commit chunk không tự rollback khi worker B gặp lỗi.

### Remote chunking có khác không?

Trong **remote chunking**, manager thường sở hữu `ItemReader` và gửi **chunk items** tới worker qua broker. Snapshot của reader ở manager vẫn cần ổn định khi restart, nhưng **worker không mặc nhiên tự đọc một partition range** như trong remote partitioning.

Nếu chunk payload chứa dữ liệu nhạy cảm hoặc cực lớn, cân nhắc đổi sang remote partitioning/reference-based model khi nguồn cho phép. Không tự gửi toàn bộ snapshot data qua `ExecutionContext` hay broker nếu chỉ cần truyền tham số nguồn.

## 15. Tính dung lượng và hiệu năng trước khi chốt snapshot

Một snapshot vật lý tăng chi phí **capture + lưu trữ + đọc lại**. Điều đó cần được tính cùng throughput mục tiêu thay vì chỉ đo thời gian xử lý worker.

Giả sử:

- 10.000.000 record.
- Payload trung bình 1 KiB/record trong snapshot (chỉ giả định kích thước dữ liệu).
- Tốc độ copy snapshot thực tế `15.000 record/s`.
- Bốn worker, mỗi worker có thể xử lý `4.000 record/s` khi không bị nghẽn.
- Business DB writer đạt tối đa `11.000 record/s` trên toàn hệ.

~~~text
Dung lượng payload snapshot lý tưởng:
10.000.000 × 1 KiB ≈ 9,54 GiB

Thời gian capture:
10.000.000 / 15.000 ≈ 667 giây ≈ 11,1 phút

Worker capacity lý tưởng:
4 × 4.000 = 16.000 record/s

Throughput worker thực tế bị DB giới hạn:
min(16.000, 11.000) = 11.000 record/s

Thời gian xử lý:
10.000.000 / 11.000 ≈ 909 giây ≈ 15,2 phút

Nếu capture và processing tuần tự:
Tổng ≈ 11,1 + 15,2 ≈ 26,3 phút
~~~

Các con số là **giả định sizing**, không phải benchmark Spring Batch. Dung lượng thật còn có index, tuple/page overhead, WAL, replication, backup, object metadata và nhiều bản snapshot chờ restart. Nếu cần hai snapshot đồng thời và retention dài, ngân sách tăng tương ứng.

### Những bottleneck cần đo

| Thành phần | Số đo | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Capture | Rows/s, isolation wait, WAL/IO, transaction age | Transaction quá dài, DB nguồn bị ảnh hưởng |
| Snapshot storage | Dung lượng, read IOPS, scan latency, index hit rate | Bốn worker cùng đọc gây nghẽn IO |
| Partitioning | Record/byte per range, duration/skew | Một partition chứa phần lớn dữ liệu |
| Worker | CPU, heap, GC, read/write count, chunk p95 | Worker CPU-bound hoặc GC pause |
| JDBC pool | Active, pending, acquisition wait | Tổng worker nhiều process làm cạn connection |
| Business DB | Commit latency, deadlocks, lock wait | Writer đạt trần, tăng worker không hiệu quả |
| JobRepository | Metadata write latency, step count | Too many partitions/chunk checkpoint overhead |
| Business result | Unique keys/s, missing/duplicate/version mismatch | Throughput kỹ thuật không phản ánh kết quả |

**Bài học scaling:** nếu snapshot capture tốn 50 phút còn xử lý song song chỉ tốn 10 phút, tối ưu worker từ 10 xuống 5 phút chỉ giảm tổng 60 xuống 55 phút. Nên đo **critical path end-to-end**, bao gồm capture, validation, processing và reconciliation.

### Chunk size và overhead checkpoint

Chunk 100 giúp checkpoint thường xuyên nhưng tăng transaction/metadata overhead; chunk 2.000 giảm số commit nhưng tăng rollback/retry work và memory. Không có giá trị chuẩn cho mọi DB/payload. Ưu tiên đo với snapshot thật và lỗi giả lập, thay vì tối ưu riêng số record/s khi không có lỗi.

## 16. Bảo mật và vòng đời snapshot

Materialized snapshot có thể chứa **một bản sao đầy đủ dữ liệu cá nhân/tài chính**, làm tăng nguy cơ nếu retention và quyền không được kiểm soát.

- **Phân quyền nguồn:** chỉ process capture có quyền đọc nguồn và ghi snapshot; worker thường chỉ cần quyền đọc snapshot.
- **Phân quyền đích:** writer chỉ ghi output được phân công, không dùng credential admin nếu không cần.
- **Mã hóa:** bảo vệ storage/backup at rest và kết nối in transit theo chính sách; tránh log payload nhạy cảm.
- **Least data:** nếu chỉ cần ID và source version, đừng copy các cột PII khác vào snapshot.
- **Không chứa secret:** `ExecutionContext` và manifest không nên giữ token, password, signed URL dài hạn hoặc blob nhạy cảm.
- **Truy cập remote worker:** mọi JVM cần resolve đúng snapshot từ nguồn dùng chung; không gửi path local ephemeral mà máy khác không thấy.
- **Retention:** giữ snapshot đủ cho restart và đối soát theo yêu cầu; xóa có kiểm soát sau khi hết nghĩa vụ, kể cả backup/derived artifacts.
- **Audit:** theo dõi ai tạo READY, thay policy, truy cập snapshot hoặc xóa dữ liệu.
- **Immutable enforcement:** DB permissions, append-only/versioned object hoặc policy/trigger phù hợp; cờ `READY` một mình chưa ngăn người dùng sửa dữ liệu.
- **Phân loại snapshot:** dữ liệu test phải là synthetic hoặc đã được xử lý theo chính sách, không tự copy snapshot production sang staging.

Một snapshot đã bị mất version hoặc bị sửa khi job đang chạy không nên được xử lý tiếp như thể nó còn bất biến. Fail rõ ràng và đối soát là an toàn hơn âm thầm đọc nội dung mới bằng checkpoint cũ.

## 17. Những lỗi phổ biến cần tránh

| Anti-pattern | Hậu quả | Cách thiết kế an toàn |
| --- | --- | --- |
| Chỉ chốt `MAX(id)` và gọi là snapshot hoàn chỉnh | Update/delete/commit muộn làm scope lệch | Chứng minh append-only hoặc materialize/version nguồn |
| Dùng `updated_at < cutoff` trên bảng mutable | Update làm record rời tập, clock skew/backdate | Dùng temporal/CDC hoặc snapshot bất biến |
| Worker tự chạy `SELECT MAX(id)` | Mỗi worker có phạm vi khác nhau | Một manifest đã chốt trước fan-out |
| Snapshot `READY` trước khi copy đủ | Worker đọc dữ liệu thiếu | Validation/publish step cuối theo protocol |
| Snapshot row vẫn cho UPDATE sau READY | Checkpoint cùng ID thấy payload khác | Quyền/immutability enforcement |
| Tái tạo tên partition theo UUID/timestamp | Không map vào metadata restart cũ | Tên deterministic trong manifest |
| Đổi grid/range khi restart cùng `JobInstance` | Checkpoint sai miền | Giữ mapping cũ hoặc tạo run mới có kiểm soát |
| Dùng `BETWEEN` với biên liền nhau đều inclusive | Record biên được đọc hai lần | `[start,endExclusive)` |
| Dùng offset paging trên nguồn thay đổi | Trang dữ liệu dịch chuyển | Snapshot bất biến và deterministic order |
| Nghĩ `@StepScope` tự thread-safe | Nhiều thread trong cùng StepExecution vẫn chia bean | Phân biệt partitioning với multi-threaded step |
| Lưu toàn bộ record vào `ExecutionContext` | Metadata phình to, serialize chậm | Chỉ lưu snapshot/range/checkpoint nhỏ |
| Xóa snapshot ngay khi manager fail | Không thể restart / mất đối soát | Retention theo lifecycle JobInstance |
| Business DB commit nhưng checkpoint chưa lưu | Replay item tạo effect trùng | Idempotent writer/ledger/outbox |
| Tăng worker khi DB đạt trần | Lock, IO và timeout tăng | Tối ưu DB và dữ liệu trước |
| Tin `writeCount` bằng số business effect duy nhất | Retry/upsert gây chênh lệch | Reconciliation theo business key |
| Giữ MVCC transaction nhiều giờ mà không đo | Bloat, resource/connection pressure | Materialize sớm hoặc protocol snapshot chuyên dụng |

## 18. Kiểm thử correctness và fault injection

Trước khi đưa snapshot partitioning vào production, hãy kiểm tra cả **scope**, **version** và **khả năng phục hồi**:

1. **Snapshot ban đầu:** lấy một tập dữ liệu chuẩn, tạo `snapshotId`, xác nhận status chuyển `BUILDING → READY` sau validation.
2. **Insert khi capture:** trong staging, tạo transaction insert trước/sau điểm snapshot của DB; xác minh membership theo isolation contract.
3. **Update và delete nguồn khi worker chạy:** output phải phản ánh **snapshot đã materialize**, không phản ánh dữ liệu mới nhất.
4. **Transaction capture rollback:** tạo lỗi trước READY; snapshot lỗi không được công bố như hoàn chỉnh.
5. **Copy nhiều transaction:** giả lập một segment thất bại; không cho manager chạy trước khi mọi segment và checksum/count hợp lệ.
6. **Range boundary:** bản ghi tại `endExclusive` chỉ thuộc partition kế tiếp; các ID thưa vẫn được xử lý.
7. **Coverage/disjointness:** kiểm tra cả số row của range và các phép join cho missing/duplicate assignments.
8. **Partition skew:** tạo 80% record ở một range; đo critical path, thử manifest chia theo quantile.
9. **Late binding:** mỗi `@StepScope` reader chỉ đọc đúng snapshot/range được giao.
10. **Crash trước commit chunk:** worker rollback phần chưa commit và tiếp tục đúng dữ liệu.
11. **Crash sau business commit trước checkpoint:** replay không tạo duplicate effect.
12. **Restart cùng `JobInstance`:** completed partitions thường được bỏ qua; failed partitions tiếp tục trên **cùng snapshot và boundaries**.
13. **Reprocess instance mới:** phải có contract nghiệp vụ rõ; output tránh duplicate với bản trước khi cần.
14. **Remote worker failure:** worker mới trên host khác có quyền đọc snapshot/version và không phụ thuộc file local tạm.
15. **Snapshot retention:** thử restart sau một khoảng chờ dài; snapshot chưa bị cleanup nếu còn cần.
16. **Security:** worker chỉ đọc đúng snapshot/resource; log, broker, metadata không lộ secret/PII không cần thiết.
17. **Load test:** thay số worker 1 → 2 → 4 → 8, đo throughput hữu ích, DB IO/lock/connection, JobRepository và RTO.
18. **Reconciliation:** so sánh tập khóa, version và payload giữa snapshot và output theo business invariant.

**Một test bắt buộc:** chạy job, để một partition `COMPLETED`, một partition `FAILED`, sửa bản ghi nguồn ngoài snapshot rồi restart. Nếu output sau restart bị thay đổi theo nguồn mới, hệ thống **chưa có snapshot isolation phù hợp với hợp đồng**.

## 19. Đối soát kết quả bằng dữ liệu, không chỉ bằng status

Với ví dụ copy snapshot sang bảng kết quả, câu hỏi cuối cùng là:

- Có record snapshot nào **thiếu** trong output không?
- Có record output nào **không thuộc snapshot** không?
- Có bản ghi nào đúng ID nhưng **sai version/payload** không?
- Có side effect ngoài bảng output nào bị lặp hoặc bỏ sót không?

### Thiếu khóa

~~~sql
SELECT id
FROM batch_snapshot_order
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT id
FROM batch_order_result
WHERE snapshot_id = :snapshotId;
~~~

### Khóa thừa

~~~sql
SELECT id
FROM batch_order_result
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT id
FROM batch_snapshot_order
WHERE snapshot_id = :snapshotId;
~~~

### Sai phiên bản hoặc payload

~~~sql
SELECT s.id
FROM batch_snapshot_order s
JOIN batch_order_result r
  ON r.snapshot_id = s.snapshot_id
 AND r.id = s.id
WHERE s.snapshot_id = :snapshotId
  AND (
      r.source_version IS DISTINCT FROM s.source_version
      OR r.payload IS DISTINCT FROM s.payload
  );
~~~

Kỳ vọng **0 hàng** ở cả ba phép kiểm tra nếu nghiệp vụ là copy nguyên version/payload. Nếu processor hợp lệ có transform/filter, phải đối soát với output kỳ vọng theo business rule, không bắt output giống raw input.

### Metadata là dấu vết, không phải bằng chứng tuyệt đối

`BATCH_STEP_EXECUTION` giúp biết partition nào chạy, status, `readCount`, `writeCount` và commit count. Nhưng `writeCount` không luôn bằng số row cuối cùng được thay đổi khi writer dùng `UPSERT`, skip, filter, retry hoặc side effect ngoài DB. Metadata phục vụ chẩn đoán và restart; **business reconciliation mới chứng minh tính đúng đầu ra**.

## 20. Runbook khi snapshot hoặc partition drift

Khi phát hiện một partition đọc ngoài phạm vi, snapshot bị sửa hoặc không thể restart, vận hành theo trình tự:

1. **Khoanh vùng**: xác định `snapshotId`, `JobInstance`, job/step execution ID, partition names và worker đang chạy.
2. **Ngừng phát việc mới có kiểm soát**; tránh hai owner cùng ghi trong lúc điều tra.
3. **Đọc manifest và trạng thái**: snapshot có `READY` hợp lệ, bản ghi và version có còn nguyên, các boundary có đổi không?
4. **Xác minh nguồn gốc**: audit người/hệ thống ghi snapshot, transaction capture, checksum/version, object retention.
5. **Bảo vệ dữ liệu đã commit**: không xóa output hoặc bảng metadata `BATCH_*` để “thử chạy lại”.
6. **Đối soát**: xác định bản ghi đã xử lý, thiếu, trùng hoặc phiên bản sai; phân loại side effect ngoài DB.
7. **Kiểm tra worker cũ dừng** nếu có network timeout/lease expiration; tránh owner cũ tiếp tục ghi.
8. **Đánh giá recoverability**: có thể phục hồi đúng snapshot từ backup/versioned storage và restart với checkpoint cũ không?
9. **Nếu không thể phục hồi**: lập kế hoạch reprocess instance mới có snapshot ID mới, writer idempotent và reconciliation, không giả vờ tiếp tục từ checkpoint sai.
10. **Khắc phục và phòng ngừa**: thêm immutable enforcement, validation trước READY, fixture/test restart, alert khi source/version drift.

### Cảnh báo về cleanup

Một snapshot `EXPIRED` không nên còn là input đang được xử lý; trạng thái này phải được đặt theo chính sách lifecycle sau khi xác minh không còn job/restart/reconciliation phụ thuộc. Xóa vật lý có thể cần phối hợp backup retention và nghĩa vụ dữ liệu. Không thiết kế GC chỉ dựa trên “job status cuối là FAILED” vì chính job lỗi thường **cần** snapshot để restart.

## 21. Bài tập tình huống

Một hệ thống có bảng `source_order` cập nhật liên tục, cần tổng hợp **6 triệu đơn hàng trước 06:00**. Nhóm đề xuất:

- **A:** Tại 02:00 lấy `MAX(id)` rồi chia ID range. Các worker đọc trực tiếp `source_order`, bất kể có update/delete tới 06:00.
- **B:** Chụp danh sách order ID vào manifest, nhưng worker vẫn đọc `payload` mới nhất từ `source_order`.
- **C:** Materialize `(snapshotId,id,source_version,payload)` vào snapshot bất biến với cơ chế capture nhất quán; validate manifest/partition, công bố READY rồi chạy các worker theo ranh giới đã chốt.
- **D:** Dùng cơ chế temporal/CDC có as-of version được chứng minh đúng, giao các worker đọc snapshot logic theo version ấy mà không cần copy toàn bộ payload.

Trong lần chạy C:

~~~text
snapshotId = snap-20261125-01
partition0000 = [1, 1500001)
partition0001 = [1500001, 3000001)
partition0002 = [3000001, 4500001)
partition0003 = [4500001, 6000001)

Trước khi lỗi:
  partition0000  COMPLETED
  partition0001  COMPLETED
  partition0002  FAILED sau 90 chunk commit
  partition0003  STARTED, worker JVM bị kill
~~~

Trong thời gian job bị dừng, `source_order.id=3_200_000` được cập nhật từ version 1 sang version 2, còn bảng snapshot của C vẫn giữ version 1.

**Câu hỏi:**

1. A có bảo đảm cả membership lẫn content ổn định không? Vì sao?
2. B đã giải quyết khía cạnh nào và còn thiếu khía cạnh nào?
3. C cần chứng minh những invariant nào trước khi trạng thái chuyển READY?
4. Khi restart C cùng identifying `snapshotId`, bản ghi `id=3_200_000` phải dùng version nào?
5. Nếu manager đổi `partition0002` thành `[3000001, 5000001)` khi restart, điều gì có thể sai?
6. Nếu writer cộng `daily_total = daily_total + amount`, replay chunk có an toàn không?
7. D có thể tránh copy vật lý trong điều kiện nào? Có thể chỉ dùng timestamp trên bảng mutable không?
8. Giả sử capture tốn 12 phút, worker bị DB giới hạn 20 phút và reconciliation tốn 3 phút. Tổng end-to-end nếu ba pha tuần tự là bao nhiêu?
9. Nếu snapshot chứa PII, việc materialize thêm bản sao đòi hỏi những kiểm soát nào?

### Gợi ý đáp án

- **(1)** Không. `MAX(id)` chỉ tạo một điều kiện lọc, không ngăn update/delete và commit muộn của ID nhỏ.
- **(2)** B chốt membership danh sách ID nhưng không chốt content/version; worker vẫn có thể xử lý payload khác thời điểm.
- **(3)** Snapshot đủ record đúng business window, phiên bản nội dung ổn định, partition coverage/disjointness, expected count/checksum phù hợp, trạng thái công bố sau validation.
- **(4)** Version **1** đã nằm trong snapshot C; xử lý version 2 là một công việc mới hoặc delta/backfill có chủ đích.
- **(5)** Checkpoint cũ của partition002 chỉ tới miền cũ; range mới có thể chồng lên partition003 hoặc gây bỏ sót/ghi trùng.
- **(6)** Không. Cần partial aggregate + merge, operation ledger hoặc cách ghi idempotent khác.
- **(7)** D cần nguồn hỗ trợ temporal/CDC consistent version và protocol rõ; timestamp mutable đơn thuần không đủ.
- **(8)** `12 + 20 + 3 = 35 phút`, chưa tính overhead khác.
- **(9)** Least privilege, encryption, audit, retention/cleanup, không log payload và kiểm soát remote worker.

## Checklist thiết kế trước production

- [ ] Định nghĩa rõ **membership + version/content** của snapshot theo nghiệp vụ.
- [ ] Chọn snapshot materialized, versioned files, temporal/CDC hoặc watermark với guarantee được chứng minh.
- [ ] Chỉ công bố `READY` khi input, manifest và partition mapping đã hoàn chỉnh/được validation.
- [ ] Snapshot ID là identifying `JobParameter` và mapping partition **không đổi** khi restart.
- [ ] Worker nhận `StepExecutionContext` nhỏ, đọc dữ liệu bất biến qua `@StepScope`.
- [ ] Các range không overlap, bao phủ nguồn và có `ORDER BY` deterministic.
- [ ] Reader/checkpoint và writer idempotent được kiểm thử bằng crash giữa các commit.
- [ ] Worker remote có quyền đọc snapshot đúng version; broker không phải nơi chở toàn bộ payload nếu không cần.
- [ ] Có dung lượng/IO/WAL/connection budget cho capture và processing.
- [ ] Snapshot chứa dữ liệu nhạy cảm có retention, quyền, encryption và audit phù hợp.
- [ ] Có metric theo snapshot/partition, query/DB bottleneck, restart latency và throughput business hữu ích.
- [ ] Có reconciliation đủ khóa/version/payload và kế hoạch xử lý lỗi/reprocess rõ ràng.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): local/remote partitioning, `Partitioner`, `StepExecution` và `StepScope`.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cấu hình manager/worker và API của Spring Batch dòng 5.x.
- [Spring Batch – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`.
- [Spring Batch – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): `ItemStream`, cursor và checkpoint.
- [Spring Batch – Restarting Jobs](https://docs.spring.io/spring-batch/reference/job.html): lifecycle job, parameters và restart.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): transaction snapshot, `READ COMMITTED`, `REPEATABLE READ`.
- [PostgreSQL – MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html): cách đọc dữ liệu nhất quán trong transaction.
- [PostgreSQL – Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): backup/WAL và khôi phục dữ liệu.
- [Debezium Documentation](https://debezium.io/documentation/): CDC và quy trình snapshot theo connector.
- [Spring Batch – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): phân phối worker qua messaging khi scale-out.

## Ghi nhớ

**Snapshot phạm vi dữ liệu là hợp đồng bất biến về những record nào và phiên bản nội dung nào thuộc một lần xử lý logic.** Chỉ chia `ID range` hoặc lấy `MAX(id)` không đủ nếu nguồn còn bị update/delete hoặc commit muộn. Với Spring Batch dữ liệu lớn, hãy **chốt snapshot/manifest trước fan-out**, giao ranh giới qua `Partitioner` và `StepExecutionContext`, để reader `@StepScope` đọc đúng tập dữ liệu, lưu checkpoint theo `ItemStream` và ghi output idempotent. Đừng thay snapshot, tên partition hoặc boundary khi restart cùng `JobInstance`. Đánh giá cả chi phí capture, dung lượng, source/DB bottleneck, retention và phép đối soát đầu ra; **mở rộng concurrency chỉ an toàn khi cùng một công việc có thể được phục hồi trên cùng một snapshot đúng nghĩa**.
