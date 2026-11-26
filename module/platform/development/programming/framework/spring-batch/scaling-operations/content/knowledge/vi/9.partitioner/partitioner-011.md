# Đảm bảo phân vùng không chồng lấn trong Spring Batch

Một hệ thống đối soát cuối ngày có 24 triệu giao dịch. Để đáp ứng SLA, nhóm phát triển chia bảng giao dịch thành 24 partition rồi cho nhiều worker chạy đồng thời. Job kết thúc nhanh và trả về trạng thái `COMPLETED`, nhưng tổng tiền trong báo cáo lớn hơn số liệu nguồn. Điều tra cho thấy hai partition đều xử lý giao dịch có ID 1.000.000 vì cùng dùng ranh giới `BETWEEN 1 AND 1000000` và `BETWEEN 1000000 AND 2000000`. Một bản ghi đã đi qua **hai worker**.

Lỗi này không được Spring Batch tự phát hiện. `Partitioner` chỉ cung cấp tên partition và `ExecutionContext`; framework không biết các query hoặc file mà worker thực sự đọc có chồng lấn hay không. Khi scale từ local partitioning sang remote partitioning, lỗi càng khó tìm vì nhiều JVM cùng ghi ra database, API hoặc message broker.

Bài **“Đảm bảo phân vùng không chồng lấn”** thuộc chương **Partitioner**, module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và chọn kiến trúc phù hợp tài nguyên thực tế. Nội dung ở đây tập trung vào **thiết kế, chứng minh và giám sát tính không chồng lấn của partition** mà vẫn giữ đầy đủ dữ liệu và khả năng phục hồi sau sự cố.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phát biểu chính xác các bất biến **coverage**, **disjointness**, **stability** và **ownership** của một partition plan.
2. Chia dữ liệu bằng khoảng **nửa mở** `[startInclusive, endExclusive)` để tránh trùng biên.
3. Thiết kế partitioner theo ID, file, khóa nghiệp vụ, hash bucket và thời gian với điều kiện rõ ràng.
4. Viết `Partitioner` Spring Batch 5.2.x tạo `ExecutionContext` có phạm vi không chồng lấn.
5. Gắn `@StepScope` reader với giới hạn của từng worker `StepExecution`, không đọc rộng hơn phạm vi được giao.
6. Nhận diện lỗi do dữ liệu nguồn thay đổi, phép join mở rộng phạm vi, key không ổn định, duplicate file và phân vùng sai khi restart.
7. Kiểm chứng không trùng/không thiếu bằng thuật toán, SQL, JUnit và kiểm thử crash/restart.
8. Phân biệt **một bản ghi được gán vào hai partition** với **một bản ghi được xử lý lại do retry**.
9. Bảo đảm writer có transaction/idempotency và dữ liệu cuối cùng đạt reconciliation trước khi công bố kết quả.
10. Tối ưu số partition, concurrency và khả năng cân bằng tải mà không phá tính đúng đắn.

## 2. Hiểu đúng thế nào là “không chồng lấn”

Đầu tiên phải định nghĩa **tập dữ liệu nghiệp vụ** cần xử lý. Gọi `S` là tập các record đủ điều kiện tại một **snapshot/cutoff xác định**. `Partitioner` chia `S` thành các tập `P_0, P_1, ..., P_{n-1}`.

Một partition plan đúng cần tối thiểu hai bất biến:

**Coverage — không bỏ sót:**

\[
\bigcup_{i=0}^{n-1} P_i=S
\]

**Disjointness — không chồng lấn:**

\[
P_i\cap P_j=\varnothing \qquad \text{với mọi } i\ne j.
\]

Có thể kết hợp thành **exactly-one assignment**:

\[
\forall x\in S:\quad
\sum_{i=0}^{n-1}\mathbf 1[x\in P_i]=1.
\]

Nói cách khác, mỗi bản ghi trong snapshot hợp lệ phải thuộc **đúng một** partition. Không bản ghi nào bị bỏ quên hoặc đồng thời thuộc hai partition.

### 2.1. Bốn lớp tính đúng đắn khác nhau

| Lớp | Câu hỏi cần kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| **Partition assignment** | Mỗi record thuộc đúng một partition chưa? | Hai range cùng chứa ID biên |
| **Read semantics** | Query/reader có thực sự chỉ đọc phạm vi được giao? | Context có `maxId` nhưng SQL quên điều kiện `id < maxId` |
| **Execution/restart** | Một partition có bị chạy hai lần ngoài ý muốn không? | Worker cũ vẫn ghi khi worker mới restart |
| **Business effects** | Retry/chunk rollback có làm ghi trùng hiệu ứng không? | `balance = balance + amount` thực thi lại |

**Không chồng lấn partition không đồng nghĩa exactly-once processing.** Dù mỗi record chỉ được giao cho một partition, chunk của partition ấy vẫn có thể được retry sau rollback, worker có thể crash và request remote có thể được giao lại. Vì vậy cần bảo vệ **hai lớp độc lập**: partition plan không chồng lấn **và** writer an toàn khi xử lý lại.

### 2.2. Định nghĩa “record” phải nhất quán

Nếu input là bảng `transaction_event`, một event ID có thể là đơn vị xử lý. Nhưng nếu nghiệp vụ muốn tạo **một kết quả cho mỗi tài khoản**, một tài khoản có thể có nhiều event cùng kỳ; đưa event của một tài khoản vào hai partition khác nhau có thể vẫn thỏa disjointness theo event ID nhưng lại gây tranh chấp khi ghi **cùng account**.

Vì thế phải chọn đơn vị partition theo bất biến cần bảo vệ:

- Theo `event_id` khi mỗi event được xử lý độc lập và writer idempotent theo event.
- Theo `account_id` khi toàn bộ event của một account phải được áp dụng có thứ tự.
- Theo `tenant_id` khi cần cô lập tenant/rate limit.
- Theo file/object ID khi mỗi file là một snapshot độc lập, checksum không đổi.
- Theo time bucket khi các event được phân tuyến bằng **một múi giờ và quy tắc cutoff thống nhất**.

Định nghĩa unit trước khi chọn thuật toán chia; **không chỉ kiểm tra range ID đẹp về mặt số học**.

## 3. Vì sao Spring Batch không tự kiểm tra trùng phạm vi?

Trong Spring Batch partitioning:

1. `Partitioner.partition(int gridSize)` trả một `Map<String, ExecutionContext>`.
2. `StepExecutionSplitter` tạo hoặc khôi phục worker `StepExecution` theo tên.
3. `PartitionHandler` thực thi worker step ở cùng JVM hoặc từ xa.
4. Mỗi worker nhận context rồi **tự quyết định query/file/khóa phải đọc**.

~~~mermaid
flowchart LR
    S[("Snapshot nguồn S")] --> P["Partitioner<br/>tạo context + tên"]
    P --> M["Manager PartitionStep"]
    M --> H["PartitionHandler"]
    H --> A["workerStep:range-00<br/>[1, 100000)"]
    H --> B["workerStep:range-01<br/>[100000, 200000)"]
    H --> C["workerStep:range-02<br/>[200000, 300000)"]
    A --> O[("Output")]
    B --> O
    C --> O
    M --> R[("JobRepository")]
    A --> R
    B --> R
    C --> R
~~~

`ExecutionContext` là dữ liệu do ứng dụng quyết định; Spring Batch không phân tích SQL, không xác định hai file có nội dung trùng và không biết ràng buộc kinh doanh của hai writer.

Ví dụ hai partition nhận context:

~~~text
range-00: startInclusive=1,       endExclusive=100000
range-01: startInclusive=100000,  endExclusive=200000
~~~

Nhưng nếu reader dùng `WHERE id BETWEEN :startInclusive AND :endExclusive`, **hai partition vẫn trùng ID 100000**, vì `BETWEEN` gồm cả hai biên. Framework không thể tự sửa SQL đó; trách nhiệm thuộc thiết kế partitioner **và** reader.

## 4. Chia khoảng nửa mở để loại lỗi trùng biên

Cách biểu diễn an toàn, dễ kết hợp là:

\[
P_i=[a_i,b_i)=\{x\mid a_i\le x<b_i\}
\]

Mỗi partition gồm biên đầu `a_i` và **không gồm** biên cuối `b_i`.

Ví dụ xử lý các ID `1..300000`:

| Key | startInclusive | endExclusive | Record cuối cùng nếu ID nguyên |
| --- | ---: | ---: | ---: |
| `range-00` | 1 | 100001 | 100000 |
| `range-01` | 100001 | 200001 | 200000 |
| `range-02` | 200001 | 300001 | 300000 |

Điều kiện reader:

~~~sql
SELECT event_id, amount
FROM transaction_event
WHERE event_id >= :startInclusive
  AND event_id <  :endExclusive
ORDER BY event_id;
~~~

Bây giờ ID 100001 chỉ thuộc `range-01`; `range-00` kết thúc **trước** ID đó. Không cần cộng/trừ 1 ở điều kiện SQL của từng worker.

### 4.1. Bất biến của một dãy range liên tiếp

Với tập ID cần phủ trong `[L,U)`, dãy range đúng phải thỏa:

1. Mỗi range hợp lệ: `a_i < b_i`.
2. Range đầu: `a_0=L`.
3. Range cuối: `b_{n-1}=U`.
4. Các range đã sắp xếp nối đúng nhau: `b_i=a_{i+1}`.
5. Không dùng một query tổng hợp khác làm rộng phạm vi `[a_i,b_i)`.

Nếu `b_i > a_{i+1}` là **chồng lấn**; nếu `b_i < a_{i+1}` là **khoảng trống**. Nếu một miền ID thực sự không có record, khoảng trống số học không nhất thiết gây mất dữ liệu; tuy vậy kế hoạch range phủ toàn bộ `[L,U)` thường dễ chứng minh hơn khi xử lý nguồn có thể phát sinh ID mới.

### 4.2. Không thay nửa mở bằng BETWEEN tùy tiện

~~~sql
-- SAI nếu endExclusive thuộc range kế tiếp:
WHERE event_id BETWEEN :startInclusive AND :endExclusive
~~~

~~~sql
-- ĐÚNG với [startInclusive, endExclusive):
WHERE event_id >= :startInclusive
  AND event_id <  :endExclusive
~~~

Nếu hệ thống bắt buộc dùng `BETWEEN`, hãy biểu diễn context bằng `minInclusive` và `maxInclusive`, bảo đảm partition kế tiếp bắt đầu sau `maxInclusive` cũ. Không trộn hai quy ước trong cùng pipeline.

### 4.3. Cảnh giác overflow

Khi thiết kế range dùng kiểu `long`, biểu thức `maxId + 1` có thể overflow tại `Long.MAX_VALUE`. Nếu domain có thể chạm biên trên của `long`, hãy dùng kiểu biên có khả năng biểu diễn sentinel lớn hơn (ví dụ `BigInteger` hoặc khóa/composite bound có quy tắc riêng), hay chọn phép so sánh và domain được thiết kế không cần cộng 1.

Đừng dùng `Math.abs(hashCode)` để tạo bucket vì `Math.abs(Integer.MIN_VALUE)` vẫn âm. Dùng `Math.floorMod` với số bucket dương và thuật toán hash ổn định.

## 5. Code Java: Partitioner chia range không chồng lấn

Đây là một ví dụ **Spring Batch 5.2.x, Java 17+**, tạo `P` range từ một snapshot có miền ID `[startInclusive, endExclusive)`. Số partition được cố định theo **partition plan của JobInstance**; tham số `gridSize` được xem là hint và cố ý không làm thay đổi plan đã chốt.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class StableRangePartitioner implements Partitioner {

    private final long startInclusive;
    private final long endExclusive;
    private final int partitionCount;

    public StableRangePartitioner(
            long startInclusive,
            long endExclusive,
            int partitionCount) {

        long span = Math.subtractExact(endExclusive, startInclusive);
        if (span <= 0) {
            throw new IllegalArgumentException("Empty/invalid ID interval");
        }
        if (partitionCount <= 0 || span < partitionCount) {
            throw new IllegalArgumentException(
                    "Must have 1..span non-empty partitions");
        }

        this.startInclusive = startInclusive;
        this.endExclusive = endExclusive;
        this.partitionCount = partitionCount;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long span = Math.subtractExact(endExclusive, startInclusive);
        long baseWidth = span / partitionCount;
        long remainder = span % partitionCount;

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long cursor = startInclusive;

        for (int i = 0; i < partitionCount; i++) {
            // Phân phối các ID dư vào những range đầu tiên.
            long width = baseWidth + (i < remainder ? 1L : 0L);
            long next = Math.addExact(cursor, width);

            ExecutionContext ctx = new ExecutionContext();
            ctx.putLong("startInclusive", cursor);
            ctx.putLong("endExclusive", next);

            String partitionKey = String.format(
                    Locale.ROOT, "range-%04d", i);
            result.put(partitionKey, ctx);

            cursor = next;
        }

        if (cursor != endExclusive) {
            throw new IllegalStateException("Coverage mismatch");
        }
        return result;
    }
}
~~~

### 5.1. Cách dùng

~~~java
Partitioner partitioner =
        new StableRangePartitioner(1L, 300_001L, 3);

Map<String, ExecutionContext> parts =
        partitioner.partition(3);

// range-0000: [1,      100001)
// range-0001: [100001, 200001)
// range-0002: [200001, 300001)
~~~

Ví dụ có 300.000 giá trị ID nguyên trong miền và ba partition bằng nhau. `baseWidth=100000`, `remainder=0`. Với 10 ID chia 3 partition, kích cỡ là 4, 3 và 3, không bị thiếu hoặc gán chồng biên.

### 5.2. Vì sao code an toàn về số học?

- `Math.subtractExact` phát hiện overflow khi tính chiều rộng miền.
- `partitionCount` không vượt `span` nên không tạo range rỗng trong ví dụ.
- `Math.addExact` phát hiện overflow khi tính biên tiếp theo.
- Các range được tạo liên tiếp từ `cursor`, nên `endExclusive` của range trước đúng bằng `startInclusive` range sau.
- Tên partition `range-%04d` ổn định khi **snapshot bounds và partitionCount không đổi**.
- Không có shared mutable counter giữa các worker; partitioner chỉ tạo **context mô tả miền**.
- `LinkedHashMap` cho phép kiểm tra thứ tự để đọc log dễ hơn, nhưng không dùng thứ tự Map như danh tính checkpoint; **key** mới là identity.

**Phạm vi áp dụng:** code kiểm chứng phủ miền số học `[startInclusive,endExclusive)`. Nó không biết có bản ghi nào nằm ngoài khoảng, có bản ghi bị thêm/sửa sau snapshot hay có hai bản ghi khác nhau cùng business key hay không. Cần bổ sung điều kiện nguồn và reconciliation.

### 5.3. Khi gridSize thay đổi

`gridSize` có thể được manager truyền như gợi ý số partition; trong ví dụ trên, `partitionCount` là một phần của **kế hoạch đã chốt**. Cách này tránh tạo danh tính khác trong lần restart cùng JobInstance.

Nếu muốn sử dụng gridSize để chọn P ở **lần chạy đầu**, hãy tính P trước khi bắt đầu JobInstance, lưu P và khoảng ID trong manifest/snapshot của JobInstance, rồi dùng lại cùng P khi restart. Không cho thay đổi số worker JVM hoặc thread pool tự làm đổi tên/range trong lịch sử.

## 6. Worker reader phải giữ đúng ranh giới được giao

Ngay cả partitioner hoàn hảo cũng có thể thất bại nếu worker query sai hoặc bỏ filter.

### 6.1. JdbcCursorItemReader với StepScope

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public JdbcCursorItemReader<EventRow> eventRangeReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['startInclusive']}")
                Long startInclusive,
        @Value("#{stepExecutionContext['endExclusive']}")
                Long endExclusive,
        @Value("#{jobParameters['snapshotId']}")
                String snapshotId) {

    return new JdbcCursorItemReaderBuilder<EventRow>()
            .name("eventRangeReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT event_id, account_id, amount
                 FROM event_snapshot
                 WHERE snapshot_id = ?
                   AND event_id >= ?
                   AND event_id < ?
                 ORDER BY event_id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotId);
                ps.setLong(2, startInclusive);
                ps.setLong(3, endExclusive);
            })
            .rowMapper((rs, rowNum) -> new EventRow(
                    rs.getLong("event_id"),
                    rs.getLong("account_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

`EventRow` là record/class do ứng dụng định nghĩa. `event_snapshot` là bảng snapshot bất biến theo `snapshot_id`, có khóa định danh `event_id` duy nhất trong snapshot. Code là **mảnh cấu hình reader**, không phải ứng dụng độc lập; hạ tầng DataSource, transaction và Spring Batch được cấu hình ở chỗ khác.

**Điểm then chốt:**

- `@StepScope` làm bean reader được tạo theo **worker StepExecution**, hữu ích với local/remote partitioning.
- Reader bắt buộc dùng cả `startInclusive` và `endExclusive`; thiếu một điều kiện có thể tạo chồng lấn dù context đúng.
- `snapshot_id` ngăn worker này đọc dữ liệu từ các kỳ khác khi bảng lưu nhiều snapshot.
- `ORDER BY event_id` với khóa duy nhất giúp checkpoint/cursor có thứ tự xác định.
- `saveState(true)` cho phép reader ghi state phục vụ restart khi framework quản lý đúng vòng đời `ItemStream`.
- Nếu một StepExecution được thực thi lại trên JVM khác, reader có thể dùng context trong `JobRepository` và snapshot nguồn được truy cập chung.

`@StepScope` không tự giải quyết một singleton writer dùng mutable buffer chung. Nó cũng không tự bảo đảm việc reader retry/restart sẽ không phát lại item: cần transaction và writer idempotent.

### 6.2. Mở rộng SQL bằng join có thể làm đổi ngữ nghĩa record

Giả sử mỗi event được join với nhiều dòng `event_tag`:

~~~sql
SELECT e.event_id, t.tag_id
FROM event_snapshot e
JOIN event_tag t ON t.event_id = e.event_id
WHERE e.snapshot_id = :snapshotId
  AND e.event_id >= :startInclusive
  AND e.event_id < :endExclusive;
~~~

Query vẫn không đọc **event ID ngoài range**, nhưng một event có ba tag sẽ tạo ba **hàng kết quả**. Đây **không phải chồng lấn giữa partition**; đó là fan-out trong phép join. Nếu writer kỳ vọng một output cho mỗi event, phải gom/aggregate hoặc thay model dữ liệu. Phân biệt lỗi **trùng identity logic** do join với lỗi **cùng record đi vào hai partition**.

## 7. Chia theo file: không chồng lấn identity khác không chồng lấn nội dung

Một partitioner chia theo file thường gán **mỗi file URI hoặc file ID** cho một worker. Điều này đúng khi:

1. Manifest của một snapshot liệt kê mỗi **physical source shard** đúng một lần.
2. Cùng một shard không xuất hiện dưới hai URI/alias khác nhau nếu chúng cùng chứa dữ liệu cần dedupe.
3. File immutable theo checksum/version, đặc biệt khi retry/restart.
4. Worker thực sự chỉ đọc các file được gán cho partition.
5. Nếu một logical partition gồm nhiều file, không file nào bị nhóm vào hai logical partition.

Ví dụ manifest:

~~~text
group-000 -> [file-A.csv, file-B.csv]
group-001 -> [file-C.csv, file-D.csv]
group-002 -> [file-E.csv]
~~~

Sai:

~~~text
group-000 -> [file-A.csv, file-B.csv]
group-001 -> [file-B.csv, file-C.csv]   // file-B thuộc hai group
~~~

Nếu file `B` chứa 200.000 dòng, mỗi dòng của nó có thể được xử lý hai lần.

### 7.1. Tên URI có chắc định danh dữ liệu duy nhất?

Không nhất thiết. Object storage có thể chứa hai object URI khác nhau nhưng nội dung trùng; một file có thể được mount qua hai path; một file có thể đã được tách/lưu lại rồi nạp lần nữa. Cần xác định chuẩn **đơn vị duy nhất** của nghiệp vụ:

- Nếu ingest theo **object identity**, key có thể là `bucket + objectKey + versionId`.
- Nếu ingest theo **source event identity**, phải kiểm tra `event_id` xuyên mọi file.
- Nếu file là một snapshot tái xuất của cùng dữ liệu, cần một ingest-run/snapshot policy để tránh nạp chồng kỳ cũ.

Checksum giúp xác minh nội dung và phát hiện duplicate candidates, nhưng **hai file giống checksum không nhất thiết được loại một cái** nếu nghiệp vụ coi chúng là hai tài liệu hợp lệ. Cần chính sách business rõ ràng.

### 7.2. Gộp nhiều file nhỏ

Khi nhiều file rất nhỏ, gộp thành các logical partitions có thể giảm `StepExecution` overhead. Gộp không được làm file xuất hiện hai nhóm và reader multi-file phải checkpoint **file index + offset** đúng. Lưu group manifest bất biến thay vì để worker list thư mục “latest” vào lúc chạy.

## 8. Chia theo khóa nghiệp vụ và hash bucket

Khoảng ID không phải lúc nào cũng phù hợp. Nếu cùng `account_id` phải được xử lý tuần tự trong một worker, chia theo **hash bucket của account** có thể tránh hai worker cùng cập nhật một tài khoản.

Quy tắc khái niệm:

\[
\operatorname{bucket}(k)
=\operatorname{floorMod}(H(k),B)
\]

Với `B > 0` cố định, mỗi khóa `k` được gán **đúng một** bucket từ `0` tới `B-1`.

~~~java
public final class AccountRouter {
    private final int bucketCount;

    public AccountRouter(int bucketCount) {
        if (bucketCount <= 0) {
            throw new IllegalArgumentException("bucketCount > 0 required");
        }
        this.bucketCount = bucketCount;
    }

    public int bucketFor(String accountKey) {
        if (accountKey == null) {
            throw new IllegalArgumentException("accountKey required");
        }

        // Java String.hashCode có quy tắc xác định.
        // Production phải version hóa chuẩn hóa key và thuật toán hash.
        return Math.floorMod(accountKey.hashCode(), bucketCount);
    }
}
~~~

**Không dùng** `Math.abs(hashCode) % B` vì `Math.abs(Integer.MIN_VALUE)` vẫn âm. Bản thân hash collision giữa hai account là bình thường: hai account có thể cùng bucket; điều cần đảm bảo là **mỗi account không xuất hiện ở hai bucket khác nhau** trong một partition plan.

### 8.1. Những điểm làm hash partition bị chồng hoặc sai tuyến

- Manager dùng `accountKey.trim().toLowerCase()`, worker khác lại dùng key chưa chuẩn hóa.
- Một service dùng Java `String.hashCode`, service khác dùng MurmurHash nhưng cùng gọi “hash bucket”.
- Một worker dùng `B=16`, worker mới deploy dùng `B=32`.
- Account ID thay đổi hoặc có alias trong quá trình xử lý.
- SQL ở worker quên điều kiện bucket và đọc toàn bộ bảng.
- Hệ thống dùng các source data snapshots khác nhau nên cùng record được phân tuyến trong hai version của plan.

Dùng **một thuật toán hash có version, một chuẩn mã hóa/normalize, một giá trị B cho cùng snapshot**, và lưu chúng trong manifest/JobParameters. Nếu filter SQL không triển khai được cùng hàm hash với Java một cách tin cậy, có thể tạo bảng staging ánh xạ `account_id → bucket_id` tại thời điểm snapshot.

### 8.2. Chia theo tenant và composite keys

Một record có thể được nhận diện bằng bộ `(tenant_id, event_id)` thay vì chỉ `event_id`. Nếu hai tenant đều có event_id=42, không được dedupe toàn hệ thống theo event_id trần.

Ví dụ:

~~~sql
SELECT tenant_id, event_id, amount
FROM event_snapshot
WHERE snapshot_id = :snapshotId
  AND tenant_id = :tenantId
  AND event_id >= :startInclusive
  AND event_id < :endExclusive;
~~~

Lúc này partition identity có thể là `tenant-007-range-03`; coverage/disjointness được kiểm tra trên **khóa tổng hợp** của snapshot.

## 9. Chia theo thời gian và các lỗi ranh giới

Với dữ liệu event theo thời điểm, dùng khoảng nửa mở thời gian:

\[
[t_0,t_1),\ [t_1,t_2),\ [t_2,t_3)
\]

Ví dụ xử lý ba giờ liên tiếp:

~~~sql
SELECT event_id, occurred_at
FROM event_snapshot
WHERE occurred_at >= :windowStartUtc
  AND occurred_at <  :windowEndUtc
  AND snapshot_id = :snapshotId;
~~~

Dùng `Instant`/UTC khi lưu và so sánh các mốc. Múi giờ nghiệp vụ như `Asia/Ho_Chi_Minh` chỉ được dùng nhất quán để xác định **business date/cutoff** rồi chuyển sang Instant. Với vùng có DST, một ngày nghiệp vụ có thể dài 23 hoặc 25 giờ; không mặc định cắt thành 24 khối “mỗi giờ tường” mà bỏ qua khoảng giờ không tồn tại hoặc bị lặp.

### 9.1. Event time và ingestion time không thể hoán đổi

Nếu ngày D được định nghĩa theo `occurred_at` mà partitioner chia theo `ingested_at`, một event đến muộn có thể xuất hiện ở kỳ xử lý khác. Khi đó dãy time window theo ingestion vẫn không chồng nhau, nhưng **coverage theo business event time** lại sai.

Hãy chốt:

- Timestamp nào định nghĩa đơn vị dữ liệu cần xử lý.
- Cửa sổ và cutoff nào là bất biến của snapshot.
- Late-arriving event đi vào reprocess hay kỳ sau theo chính sách.
- Cách cập nhật output khi có correction mà không ghi đè dữ liệu mới bằng bản cũ.

## 10. Một snapshot bất biến là điều kiện nền tảng

Giả sử partitioner tính `MIN(id)` và `MAX(id)` lúc 00:30 rồi các worker chạy từ 00:30–04:00. Trong thời gian đó, nguồn tiếp tục insert/update/delete.

Ngay cả nếu các **range số học không chồng lấn**, việc xử lý vẫn có thể không tương ứng với **một snapshot logic**:

- Record có ID nằm trong range đã hoàn tất được insert muộn: nó không được xử lý.
- Một record bị xóa/đổi trạng thái trước khi worker đọc: nó biến mất khỏi tập dự kiến.
- Cùng một record được cập nhật giữa hai lượt query: kết quả không nhất quán với dữ liệu lúc cutoff.
- Partition được restart bằng query mới trên bảng đã thay đổi: checkpoint số dòng/cursor không còn đúng.

**Điều kiện `updated_at <= cutoff` không tự chứng minh snapshot bất biến** nếu bản ghi có thể được sửa/hồi tố hoặc điều kiện lọc thay đổi trong quá trình đọc. Cần một trong các chiến lược đã được kiểm chứng:

1. **Materialized snapshot/staging** bất biến theo `snapshot_id`.
2. **Object/file manifest versioned** có checksum, xác nhận nguồn đã hoàn tất.
3. **Database snapshot/transaction isolation** phù hợp, cùng điểm nhìn logic giữa các worker — điều này khó bảo đảm khi nhiều connection/transaction độc lập, cần thiết kế rõ.
4. **Event log immutable + watermark** có chính sách xử lý sự kiện đến muộn/correction.
5. **Versioned rows** với query được định nghĩa theo effective version/cutoff chính xác.

Không phát biểu “partition không chồng nên kết quả exactly-once” khi đầu vào chưa có định nghĩa snapshot.

## 11. Restart phải dùng lại partition plan cũ

Tính không chồng lấn phải giữ được **giữa các JobExecution của cùng JobInstance**, không chỉ trong một lần chạy.

Ví dụ plan lần đầu:

~~~text
JobInstance: dailyImport(snapshot=v42)
  range-0000 => [1,      100001)  COMPLETED
  range-0001 => [100001, 200001)  FAILED
  range-0002 => [200001, 300001)  COMPLETED
~~~

Khi restart, `SimpleStepExecutionSplitter` dùng tên partition và metadata trong `JobRepository` để chọn phần cần chạy lại. Nếu code mới đổi số partition hoặc phạm vi:

~~~text
SAI khi restart cùng JobInstance:
  range-0000 => [1,      75001)
  range-0001 => [75001, 150001)
  range-0002 => [150001,225001)
  range-0003 => [225001,300001)
~~~

Khả năng xảy ra: range cũ `[1,100001)` đã hoàn tất, nhưng range mới `[75001,150001)` lại bao phủ `[75001,100001)`. Nếu mapping và restart metadata bị kết hợp sai, các bản ghi có thể được ghi lần nữa hoặc bỏ qua.

### 11.1. Các điều kiện restart đúng

- Cùng tên job và **identifying JobParameters** của JobInstance cần phục hồi.
- Cùng `snapshotId` và dữ liệu nguồn bất biến.
- Tên worker step và partition keys ổn định.
- Các giới hạn range/key/file mapping không thay đổi.
- `JobRepository` và `ExecutionContext` của partition cũ còn đầy đủ.
- Reader `ItemStream` có checkpoint hợp lệ và query deterministic.
- Writer idempotent hoặc có giao dịch/dedup phù hợp.
- Worker đời cũ đã dừng hoặc có **fencing/ownership** ngăn chạy chồng khi remote.

**Đừng tăng `run.id` chỉ để tiếp tục một job đã lỗi**; tham số định danh mới có thể tạo JobInstance mới và làm mất cơ chế bỏ qua các partition đã hoàn tất.

### 11.2. PartitionNameProvider không phải công cụ sửa chồng lấn

`PartitionNameProvider#getPartitionNames(int gridSize)` có thể giúp restart không phải tính lại plan tốn kém, bằng cách trả **tên của các partition đã tạo**. Splitter dùng context lịch sử từ repository.

Nhưng interface này không kiểm chứng query range, không tạo dữ liệu snapshot và không tự phát hiện hai partition có nội dung trùng. Nó là **tối ưu đường lấy tên**, không phải bằng chứng disjointness.

Một thiết kế tốt lưu immutable partition manifest tại lần chạy đầu, gồm:

| snapshot_id | partition_key | start_inclusive | end_exclusive | plan_version |
| --- | --- | ---: | ---: | --- |
| `v42` | `range-0000` | 1 | 100001 | `ranges-v1` |
| `v42` | `range-0001` | 100001 | 200001 | `ranges-v1` |
| `v42` | `range-0002` | 200001 | 300001 | `ranges-v1` |

Khi restart, **lấy plan đã lưu**, không tự tính lại dựa trên `MAX(id)` hiện tại hoặc số worker pods mới.

## 12. Chống ghi trùng dù đã chia đúng

Có hai loại duplicate thường bị nhầm:

1. **Cross-partition duplicate:** cùng record thuộc hai partition — sửa thuật toán và query phân vùng.
2. **Replay duplicate:** cùng record/chunk thuộc một partition được thực thi lại sau rollback, timeout, worker crash hoặc redelivery — cần transaction/idempotency.

Ví dụ không idempotent:

~~~sql
UPDATE account_balance
SET balance = balance + :delta
WHERE account_id = :accountId;
~~~

Nếu worker thực hiện lại cùng event, số dư có thể cộng hai lần dù event chỉ thuộc một partition.

Ví dụ upsert kết quả xác định theo event ID và source version:

~~~sql
CREATE TABLE normalized_event (
    event_id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    calculated_amount NUMERIC(18, 2) NOT NULL
);

INSERT INTO normalized_event(event_id, source_version, calculated_amount)
VALUES (:eventId, :sourceVersion, :calculatedAmount)
ON CONFLICT (event_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    calculated_amount = EXCLUDED.calculated_amount
WHERE normalized_event.source_version < EXCLUDED.source_version;
~~~

Nếu `event_id` chỉ duy nhất **trong từng tenant**, khóa chính ở đây phải là `(tenant_id,event_id)` và query/upsert cần mang tenant ID; không lấy ví dụ đơn tenant áp dụng cho mô hình multi-tenant.

Nếu cùng version có payload mâu thuẫn, phải định nghĩa cách báo conflict hoặc reconciliation; upsert không tự giải quyết. Với side effects ngoài DB transaction (HTTP thanh toán, gửi email, đẩy broker), cần idempotency key ở hệ thống đích, outbox/inbox và cơ chế đối soát tương ứng.

### 12.1. Remote partitioning có rủi ro trùng thực thi

Manager gửi một `StepExecutionRequest` cho worker A. Network lỗi khiến manager không quan sát được kết quả; đồng thời worker A vẫn xử lý. Nếu một execution mới cũng chạy cùng partition, có nguy cơ hai process cùng thực hiện side effects.

`JobRepository` giúp định danh/khôi phục StepExecution, nhưng không phải distributed mutex bảo đảm mọi external action chạy đúng một lần. Cần lựa chọn chính sách worker ownership, xác minh liveness, fencing tokens nếu cần và writer idempotent. Không “restart ngay” khi trạng thái còn `STARTED` mà chưa điều tra worker cũ.

## 13. Kiểm tra partition plan trước khi dispatch

Một plan cần được kiểm tra **trước khi phát worker tasks**. Việc này nhanh hơn nhiều so với điều tra hàng triệu dòng sau khi dữ liệu đã ghi sai.

### 13.1. Kiểm tra dãy range bằng Java

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public record IdRange(
        String key, long startInclusive, long endExclusive) {}

public final class RangePlanValidator {

    public static void requireContiguousNonOverlapping(
            List<IdRange> ranges,
            long expectedStart,
            long expectedEndExclusive) {

        if (ranges.isEmpty() || expectedStart >= expectedEndExclusive) {
            throw new IllegalArgumentException("Invalid plan/domain");
        }

        List<IdRange> sorted = new ArrayList<>(ranges);
        sorted.sort(Comparator
                .comparingLong(IdRange::startInclusive)
                .thenComparingLong(IdRange::endExclusive));

        long cursor = expectedStart;
        for (IdRange range : sorted) {
            if (range.startInclusive() >= range.endExclusive()) {
                throw new IllegalStateException(
                        "Empty range: " + range.key());
            }
            if (range.startInclusive() < cursor) {
                throw new IllegalStateException(
                        "Overlapping range: " + range.key());
            }
            if (range.startInclusive() > cursor) {
                throw new IllegalStateException(
                        "Gap before: " + range.key());
            }
            cursor = range.endExclusive();
        }

        if (cursor != expectedEndExclusive) {
            throw new IllegalStateException("Wrong final boundary");
        }
    }
}
~~~

Hàm kiểm tra tính liên tiếp của range trong **miền số**. Production cần thêm kiểm tra `partitionKey` duy nhất, context không null, dữ liệu snapshot hợp lệ và xử lý nếu miền dữ liệu có khoảng trống chủ đích.

Ví dụ `[1,101)`, `[101,201)` là hợp lệ; `[1,101)`, `[100,201)` bị báo overlap; `[1,101)`, `[102,201)` bị báo gap.

### 13.2. SQL phát hiện overlap và gap trên manifest

Giả sử bảng `batch_partition_plan` có:

~~~sql
CREATE TABLE batch_partition_plan (
    snapshot_id VARCHAR(100) NOT NULL,
    partition_key VARCHAR(100) NOT NULL,
    start_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    PRIMARY KEY(snapshot_id, partition_key),
    CHECK (start_inclusive < end_exclusive)
);
~~~

Truy vấn phát hiện các đoạn **kề nhau** bị overlap hoặc gap:

~~~sql
WITH ordered AS (
    SELECT
        partition_key,
        start_inclusive,
        end_exclusive,
        LAG(end_exclusive) OVER (
            ORDER BY start_inclusive, end_exclusive, partition_key
        ) AS prev_end
    FROM batch_partition_plan
    WHERE snapshot_id = :snapshotId
)
SELECT
    partition_key,
    start_inclusive,
    end_exclusive,
    prev_end,
    CASE
        WHEN prev_end > start_inclusive THEN 'OVERLAP'
        WHEN prev_end < start_inclusive THEN 'GAP'
    END AS issue
FROM ordered
WHERE prev_end IS NOT NULL
  AND prev_end <> start_inclusive;
~~~

Kết quả rỗng **chưa đủ chứng minh toàn bộ plan đúng**: phải kiểm tra range đầu/cuối có khớp domain kỳ xử lý, không có duplicate keys và các row không vi phạm CHECK. Với các interval chồng lấn phức tạp, chỉ so `LAG(end_exclusive)` của khoảng liền trước có thể bỏ sót interval nằm bên trong một khoảng lớn trước đó.

Ví dụ:

~~~text
A = [1, 1000)
B = [100, 200)
C = [300, 400)
~~~

Ở C, `LAG(end_exclusive)=200` của B không phát hiện rằng C vẫn nằm trong A. Để phát hiện overlap tổng quát, dùng **running maximum** của end trước đó:

~~~sql
WITH ordered AS (
    SELECT
        partition_key,
        start_inclusive,
        end_exclusive,
        MAX(end_exclusive) OVER (
            ORDER BY start_inclusive, end_exclusive, partition_key
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS max_prev_end
    FROM batch_partition_plan
    WHERE snapshot_id = :snapshotId
)
SELECT partition_key, start_inclusive, end_exclusive, max_prev_end
FROM ordered
WHERE max_prev_end > start_inclusive;
~~~

Với kế hoạch yêu cầu **phủ liên tục**, ngoài kiểm tra overlap tổng quát còn dùng phép kiểm `start_inclusive` của row kế tiếp so `end_exclusive` của row trước, cộng kiểm tra domain đầu/cuối. Với plan có nhiều miền rời rạc hợp lệ, chỉ kiểm tra overlap và **coverage theo tập nguồn** chứ không kết luận mọi khoảng trống số học là lỗi.

### 13.3. Kiểm chứng assignment ở mức bản ghi

Khi có snapshot ổn định, có thể kiểm tra số partition khớp mỗi record. Ví dụ PostgreSQL với plan theo range ID:

~~~sql
SELECT
    e.event_id,
    COUNT(p.partition_key) AS matched_partitions
FROM event_snapshot e
LEFT JOIN batch_partition_plan p
       ON p.snapshot_id = e.snapshot_id
      AND e.event_id >= p.start_inclusive
      AND e.event_id < p.end_exclusive
WHERE e.snapshot_id = :snapshotId
GROUP BY e.event_id
HAVING COUNT(p.partition_key) <> 1;
~~~

Kết quả trả về những event được khớp **0 partition** hoặc **hơn 1 partition**. Truy vấn chỉ hợp lệ để suy ra mỗi event đúng một partition khi `event_id` là khóa duy nhất trong snapshot; nếu nguồn có nhiều row cùng `event_id`, dùng khóa nguồn đầy đủ hoặc grouped logic khác.

Trên bảng hàng tỷ dòng, kiểm tra toàn bộ join có thể đắt; cân nhắc kiểm tra interval bằng metadata trước, dùng sampling/stratified checks lúc preflight và **reconciliation đầy đủ** theo cách tối ưu sau batch. Sampling không thay thế bảo đảm chính xác nếu SLA yêu cầu không thiếu/trùng.

## 14. Kiểm thử ranh giới và property-based bằng JUnit

Unit test nên kiểm tra **tập hợp partition** chứ không chỉ kiểm tra một range mẫu.

### 14.1. Test biên đơn giản

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class StableRangePartitionerTest {

    @Test
    void mustUseExclusiveUpperBound() {
        Map<String, ExecutionContext> p =
                new StableRangePartitioner(1L, 301L, 3)
                        .partition(3);

        assertEquals(3, p.size());

        assertEquals(1L,
                p.get("range-0000").getLong("startInclusive"));
        assertEquals(101L,
                p.get("range-0000").getLong("endExclusive"));

        assertEquals(101L,
                p.get("range-0001").getLong("startInclusive"));
        assertEquals(201L,
                p.get("range-0001").getLong("endExclusive"));

        assertEquals(201L,
                p.get("range-0002").getLong("startInclusive"));
        assertEquals(301L,
                p.get("range-0002").getLong("endExclusive"));
    }

    @Test
    void rejectsEmptyRangeAndTooManyPartitions() {
        assertThrows(IllegalArgumentException.class,
                () -> new StableRangePartitioner(10L, 10L, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new StableRangePartitioner(1L, 3L, 3));
    }
}
~~~

### 14.2. Test nhiều miền dữ liệu nhỏ

Đối với các domain nhỏ, có thể kiểm tra **mỗi ID** được gán đúng một lần:

~~~java
@Test
void everyIdBelongsToExactlyOnePartition() {
    for (long start = -5; start <= 5; start++) {
        for (long length = 1; length <= 25; length++) {
            long end = start + length;

            for (int p = 1; p <= length; p++) {
                var partitions = new StableRangePartitioner(
                        start, end, p).partition(p);

                for (long id = start; id < end; id++) {
                    final long candidate = id;

                    long matches = partitions.values().stream()
                            .filter(ctx ->
                                    candidate >= ctx.getLong("startInclusive")
                                    && candidate < ctx.getLong("endExclusive"))
                            .count();

                    assertEquals(1L, matches,
                            "id=" + id + ", p=" + p);
                }
            }
        }
    }
}
~~~

Đây là ví dụ JUnit bổ sung (cùng class/imports như test trên). Test bao gồm cả ID âm, chia không đều và partitionCount lớn nhất bằng span. Với domain rất lớn, dùng kiểm tra tính chất của các biên và một tập mẫu có biên, không lặp qua toàn bộ 64-bit domain.

### 14.3. Test sai quy tắc query

Một loại test rất quan trọng là **đưa ID đúng bằng biên**:

~~~text
Nguồn: 100000, 100001, 200000, 200001
Range A = [1,100001)          -> chỉ nhận 100000
Range B = [100001,200001)     -> nhận 100001 và 200000
Range C = [200001,300001)     -> nhận 200001
~~~

Integration test phải chạy **reader SQL thực**, không chỉ test map `ExecutionContext`. Nếu reader nhầm `<` thành `<=`, test biên sẽ phát hiện ngay.

## 15. Kiểm thử nhiều partition cùng chạy và sau restart

Một partition plan chỉ được chứng minh đúng khi kiểm tra cả assignment, thực thi và output.

| Kịch bản | Cách kiểm tra | Điều mong đợi |
| --- | --- | --- |
| Coverage | Tạo dữ liệu có ID ở đầu/cuối mọi range | Mọi record hợp lệ khớp đúng một partition |
| Boundary overlap | Dùng ID đúng `endExclusive` của range trước | Chỉ range sau đọc được ID này |
| Sparse IDs | Có nhiều lỗ trong dãy ID | Không tạo record giả, không thiếu record có thật |
| File duplicate | Manifest liệt kê cùng physical file hai lần | Bị từ chối trước dispatch |
| Alias file | Hai URI khác nhau trỏ cùng content snapshot | Phát hiện theo business source identity/policy |
| Hash negative | Hash có giá trị âm và `Integer.MIN_VALUE` | Bucket vẫn thuộc `[0,B)` |
| Hash drift | Thay algorithm/bucket count ở worker mới | Từ chối plan/version không tương thích |
| Multi-tenant | Hai tenant cùng event ID | Không dedupe nhầm tenant; phân vùng theo composite key |
| Time boundary | Event đúng 00:00:00 tại ranh giới ngày | Thuộc một window theo quy tắc UTC/timezone |
| Source mutability | Sửa/xóa/thêm record khi các worker chạy | Snapshot/version policy phát hiện thay đổi |
| Join fan-out | Một event có nhiều tag | Phân biệt duplicate do join với cross-partition overlap |
| Concurrent writers | Chạy 2/4/8 worker | Output đúng dù commit không theo thứ tự |
| Retry/rollback | Gây lỗi chunk trước commit | Có retry có giới hạn, không mất/trùng business effect |
| Process crash | Kill worker sau vài chunk commit | Restart từ checkpoint, không bỏ sót record |
| Remote duplicate request | Deliver lại cùng StepExecutionRequest | Có ownership/idempotency, không ghi trùng |
| Restart changed gridSize | Thay concurrency nhưng giữ JobInstance | Plan/key/context cũ không bị đổi |
| Plan changed unexpectedly | Đổi manifest trong cùng JobInstance | Fail rõ ràng, không silently reprocess |

### 15.1. Tiêu chí nghiệm thu dữ liệu

Không nên dùng riêng phép so:

~~~text
sum(readCount) == expectedCount
~~~

Vì một record bị đọc hai lần và một record bị bỏ sót có thể làm số lượng vẫn đúng. Cần ít nhất:

~~~text
1. Every eligible source business key is covered.
2. Every source business key maps to exactly one partition.
3. No output business key outside the approved snapshot exists.
4. Committed output keys and version match expected source keys.
5. Aggregate totals / checksums match independent reference.
6. Clean run output == failed-then-restarted run output.
7. No duplicate external business effect is observed on replay.
~~~

Một job có `BatchStatus.COMPLETED` chỉ chứng minh framework hoàn tất các step theo trạng thái đã cấu hình, **không chứng minh bất biến dữ liệu**. Hệ thống phải có bước reconciliation trước khi xuất bản output cho downstream.

## 16. Tối ưu cân bằng tải mà không phá phân vùng

Sau khi bảo đảm coverage và disjointness, mới tối ưu số partition và concurrency.

| Cách chia | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Range ID bằng độ rộng | Đơn giản, dễ chứng minh không trùng | Dữ liệu sparse/skew, hot range |
| Range theo phân vị số record | Số record cân bằng hơn | Cần histogram/snapshot ổn định |
| Hash key cố định | Trải key tương đối đều, cùng key về một bucket | Đổi hash/bucket count gây drift, skew do hot key |
| File manifest | Dễ cô lập input/checkpoint | File nhỏ tạo overhead; duplicate URI/content |
| Work-group manifest | Gộp nhiều shard nhỏ, giảm metadata | Phải bảo đảm mỗi shard chỉ một group |
| Time windows | Hữu ích cho event theo thời gian | DST, late events, sai event/ingestion time |
| Composite key | Cô lập tenant/account có thứ tự | Phức tạp ranh giới và routing |

Đừng dùng `gridSize=100` để kết luận có 100 worker đồng thời. **Số partition logic**, **worker concurrency** và **chunk size** là ba biến khác nhau.

Nếu muốn giảm skew, có thể tạo nhiều partition nhỏ hơn số worker để các worker nhận thêm việc sau khi hoàn tất shard. Nhưng khi đổi số partition giữa các lần chạy cùng JobInstance, danh tính/context checkpoint có thể không còn khớp. Vì vậy:

- **Trong một JobInstance:** giữ plan và partition keys bất biến.
- **Giữa các JobInstance mới:** có thể thử nghiệm chiến lược chia mới và so sánh throughput/tail latency.
- **Khi restart:** thay số worker pods hoặc executor threads nếu hợp lệ, nhưng không tự repartition dữ liệu cũ.

### 16.1. Nút thắt downstream không được chữa bằng tăng partition

Nếu DB đã bão hòa IOPS/row locks, thêm worker chỉ tăng contention. Với `P` partition và `C` worker, ước lượng:

\[
T_{\mathrm{job}}\approx
T_{\mathrm{dispatch}}
+\max(\text{worker critical paths})
+T_{\mathrm{aggregate/validate}}.
\]

Tăng P có thể giảm skew, nhưng cũng tăng metadata; tăng C có thể cải thiện throughput khi DB/API còn headroom, hoặc làm tăng latency khi đã bão hòa. Phải đo **committed throughput**, DB lock waits, Hikari pending, retry/rollback và p95/p99 partition duration.

## 17. Runbook khi nghi có partition chồng lấn

Khi thấy số lượng hoặc tổng tiền lớn hơn kỳ vọng, không chỉ restart job ngay. Có thể làm theo quy trình:

1. **Dừng/giới hạn publish output** để downstream không dùng kết quả chưa đối soát.
2. Ghi lại `JobInstance`, `JobExecution`, snapshot/cutoff, phiên bản partition plan và tên các StepExecution đang hoạt động.
3. Kiểm tra worker còn chạy không, nhất là khi remote partitioning; tránh hai thế hệ ghi đồng thời.
4. Trích xuất **manifest/ranges đã chốt**; kiểm tra uniqueness, overlap và coverage.
5. Đối chiếu query reader: dấu `<`/`<=`, `BETWEEN`, tenant/snapshot filters, hash policy và timezone.
6. Tìm các business keys bị ghi trùng và phân biệt **cross-partition overlap**, **join fan-out**, **duplicate source rows** hay **replay do retry**.
7. Kiểm tra transaction/idempotency của writer, output version, event side effects ngoài DB.
8. Xác định phương án sửa: rollback snapshot output, chạy reprocess có đánh dấu version mới hoặc phục hồi checkpoint hợp lệ theo runbook.
9. Không tự sửa `BATCH_STEP_EXECUTION.STATUS` thành `COMPLETED` hoặc đổi partition keys trong JobInstance cũ chỉ để cho chạy tiếp.
10. Bổ sung regression tests ở **boundary values** và kịch bản lỗi dẫn đến sai khác.

Để điều tra hiệu quả, log theo `snapshotId`, `partitionKey`, `StepExecutionId` và phạm vi. Với SQL reader, có thể ghi SQL template và params biên (không log dữ liệu nhạy cảm) ở mức debug có kiểm soát.

## 18. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “Cứ chia mỗi range cùng độ rộng thì không chồng lấn.” | Có thể trùng biên nếu dùng inclusive endpoints sai. |
| “`BETWEEN` tương đương `[start,end)`.” | `BETWEEN` thường gồm cả hai biên, gây chồng nếu end là start của range kế tiếp. |
| “Partitioner đã trả các range khác nhau là đủ.” | Reader SQL vẫn có thể bỏ filter/đổi biên hoặc đọc snapshot khác. |
| “Không chồng lấn nghĩa là không cần idempotency.” | Chunk retry/worker crash vẫn có thể phát lại cùng record. |
| “Map partition key unique thì data unique.” | Key duy nhất không chứng minh context/range/file không trùng. |
| “Hai file URI khác nhau luôn có dữ liệu khác nhau.” | Có thể là alias/copy cùng nội dung, cần source identity policy. |
| “Nếu ID có nhiều lỗ thì thiếu coverage.” | Gap số học có thể hợp lệ; kiểm tra theo tập dữ liệu thực. |
| “Đã dùng hash bucket thì không thể sai phân vùng.” | Normalize, hash version, B và SQL routing phải đồng nhất. |
| “`@StepScope` loại mọi race giữa workers.” | Reader context được tách, nhưng writer/API/DB vẫn chia sẻ tài nguyên. |
| “Sau restart có thể chia lại để cân bằng tốt hơn.” | Thay plan có thể phá danh tính StepExecution/checkpoint cũ. |
| “Chỉ cần count output bằng count input.” | Một duplicate có thể che một missing record. |
| “Dữ liệu nguồn thay đổi không ảnh hưởng vì range cố định.” | Input snapshot và checkpoint có thể không còn nhất quán. |
| “Manager `COMPLETED` là dữ liệu đã đối soát.” | Cần kiểm tra business keys, totals, freshness và publication. |

## 19. Checklist trước production

- [ ] Đã xác định tập `S` (snapshot/cutoff) và đơn vị business record cần xử lý.
- [ ] Mỗi record thuộc **đúng một** partition: coverage + disjointness.
- [ ] Đã chọn và ghi rõ quy ước range (ưu tiên nửa mở).
- [ ] Đã test ID ở biên, miền rỗng/nhỏ, số âm và overflow theo domain thực.
- [ ] `Partitioner` tạo tên/context ổn định; reader thực hiện đúng filter từ context.
- [ ] File/tenant/hash/time partition có định danh và quy tắc normalize nhất quán.
- [ ] Partition manifest gắn với JobInstance, snapshot bất biến và version rõ ràng.
- [ ] SQL/metadata preflight phát hiện overlap, gap không hợp lệ và duplicate shard assignment.
- [ ] Reader `@StepScope` dùng context riêng; shared writer/service có kiểm tra thread safety.
- [ ] Writer có transaction, idempotency hoặc cơ chế chống tác dụng phụ lặp.
- [ ] `JobRepository`/`ExecutionContext` hỗ trợ restart và lưu mapping cũ.
- [ ] Đã kiểm thử chunk rollback, worker crash, retry, remote redelivery và restart.
- [ ] Có reconciliation theo business keys/checksum, không chỉ đếm số dòng.
- [ ] Có logs/metrics per partition và khả năng truy lại source query/range.
- [ ] Đã benchmark concurrency/throughput **sau** khi tính đúng dữ liệu.
- [ ] Có runbook khi phát hiện chồng lấn trước publish và khi worker cũ vẫn chạy.

## 20. Câu hỏi tự kiểm tra

1. Hai bất biến `coverage` và `disjointness` khác nhau như thế nào?
2. Với hai range `[1,100)` và `[100,200)`, ID 100 thuộc range nào? Nếu dùng `BETWEEN 1 AND 100` cho range đầu thì chuyện gì xảy ra?
3. Tại sao một map `Map<String,ExecutionContext>` có keys khác nhau vẫn không đủ chứng minh các partition không chồng lấn?
4. Có 10 ID nguyên liên tiếp chia ba range bằng ví dụ `StableRangePartitioner`. Kích cỡ ba range là bao nhiêu?
5. Vì sao `event_id` được join với ba `tag_id` sinh ba hàng chưa chắc là lỗi chồng lấn partition?
6. Một file xuất hiện trong hai logical groups, nhưng key group đều unique. Bất biến nào bị vi phạm?
7. Hash key âm có nên tính bằng `Math.abs(hashCode) % B` không? Tại sao `Math.floorMod` tốt hơn?
8. Với snapshot đa tenant, tại sao output unique key chỉ gồm `event_id` có thể sai?
9. Nếu tính lại `MAX(id)` và tăng số range khi restart, có thể ảnh hưởng ra sao đến `StepExecution` cũ?
10. Cùng record bị chạy lại do worker crash dù plan hoàn toàn không chồng lấn. Đây là lỗi assignment hay retry/replay?
11. Tại sao hai worker query với `updated_at <= cutoff` chưa chắc cùng nhìn một snapshot dữ liệu?
12. Kiểm tra `LAG(end_exclusive)` của range liền trước có thể bỏ sót kiểu overlap nào? Cần bổ sung gì?
13. Một báo cáo có cùng số dòng với nguồn nhưng một dòng trùng và một dòng thiếu: nên dùng reconciliation gì?
14. `@StepScope` hỗ trợ điều gì khi reader có state? Nó không thay thế được biện pháp nào?
15. Nếu business cần giữ thứ tự các giao dịch của một account, bạn sẽ chọn đơn vị partition nào và bảo vệ writer ra sao?

**Gợi ý:** (1) Coverage không thiếu, disjointness không trùng; cả hai tạo exactly-one assignment. (2) ID 100 thuộc range thứ hai; `BETWEEN` gây trùng ở biên. (3) Context và query có thể cùng đọc một miền. (4) 4, 3, 3. (5) Có thể do join fan-out bên trong một partition. (6) File thuộc hai partition. (7) Không, `Integer.MIN_VALUE` vẫn âm sau `abs`; dùng `floorMod`. (8) Nhiều tenant có thể trùng event ID. (9) Tên/context checkpoint không khớp, gây bỏ sót hoặc xử lý lại. (10) Retry/replay, cần transaction/idempotency. (11) Bản ghi có thể bị sửa/hồi tố hoặc mỗi transaction nhìn trạng thái khác nhau. (12) Overlap bị che bởi interval dài trước đó; dùng running max hoặc kiểm tra tổng quát. (13) So tập khóa duy nhất, version, checksum/tổng tiền độc lập. (14) Cô lập reader theo StepExecution, không bảo đảm writer shared state/idempotency. (15) Cùng account trong một partition hoặc có bảo vệ ordering/version/locking tương đương.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, `Partitioner`, `StepExecutionSplitter`, local và remote handlers.
- [Spring Batch 5.2 Reference — Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): kiến trúc manager/worker StepExecution và contract partitioning.
- [Spring Batch 5.2 API — Partitioner](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/Partitioner.html): `Map<String,ExecutionContext> partition(int gridSize)`.
- [Spring Batch 5.2 API — PartitionNameProvider](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/PartitionNameProvider.html): khôi phục tên partition khi restart mà không phải chia lại work.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): late binding từ `stepExecutionContext` và bean scope.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, checkpoint và ExecutionContext.
- [PostgreSQL Documentation — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): `LAG` và các aggregate window functions để xác minh interval plan.

**Điểm cốt lõi:** Partitioning đúng phải bảo đảm **mỗi record thuộc đúng một partition của một snapshot xác định**. Ưu tiên range nửa mở, giữ quy ước biên nhất quán giữa `Partitioner` và reader, kiểm tra tên/file/key/time routing và lưu partition manifest bất biến để restart không đổi phạm vi. Vì retry vẫn có thể khiến worker xử lý lại cùng item, hãy luôn kết hợp **disjointness, checkpoint, transaction/idempotency và reconciliation**. Tăng concurrency chỉ đáng giá khi tốc độ cải thiện mà dữ liệu cuối cùng vẫn đúng, đủ và có thể kiểm chứng.
