# Đã kiểm tra partition coverage

## 1. Mục tiêu của kiểm tra trước production

Khi mở rộng **SPRING_BATCH_SCALING_OPERATIONS** bằng local/remote partitioning, Spring Batch có thể giao nhiều phạm vi dữ liệu cho các worker thực thi đồng thời. **Partition coverage** là việc chứng minh rằng toàn bộ dữ liệu thuộc phạm vi của một lần chạy batch đã được phân chia đúng và không có bản ghi nào bị bỏ sót hoặc được giao cho nhiều partition ngoài chủ đích.

Đây là một cổng kiểm soát chất lượng trước production, đặc biệt khi workload dữ liệu lớn, có retry/restart và cần điều chỉnh `gridSize`, số luồng, số worker hoặc cách phân phối dữ liệu theo tài nguyên. Job báo `COMPLETED` hoặc mọi worker trả về thành công **chưa đủ** để chứng minh coverage nếu cách chia phạm vi đã sai ngay từ đầu.

Một lần kiểm tra đạt yêu cầu cần trả lời được ba câu hỏi riêng biệt:

1. **Coverage của phạm vi:** các partition có phủ hết không gian khóa/cửa sổ dữ liệu được giao, không có khoảng trống hoặc chồng lấn ngoài dự kiến không?
2. **Coverage của bản ghi:** mỗi bản ghi *đủ điều kiện* trong cùng một tập đầu vào xác định có thuộc **đúng một** partition không?
3. **Coverage của kết quả:** sau retry/restart, mỗi bản ghi đó có trạng thái nghiệp vụ cuối cùng bền vững (đã xử lý, hoặc skip có lý do được chấp thuận) không?

Phải có bằng chứng cho cả ba. Kiểm tra chỉ dựa trên số lượng partition hay `readCount` không giải quyết đầy đủ bài toán.

## 2. Định nghĩa rõ tập dữ liệu và invariant

Gọi:

- `E`: tập **khóa nghiệp vụ duy nhất** của các bản ghi đủ điều kiện trong lần chạy, theo một snapshot/cửa sổ dữ liệu và bộ lọc đã cố định;
- `P₀, P₁, …, Pₙ₋₁`: tập khóa được giao cho từng partition theo *đúng predicate mà reader thực sự dùng*;
- `O`: tập khóa đã có outcome cuối cùng, bền vững theo quy tắc nghiệp vụ, ví dụ `COMPLETED` hoặc `SKIPPED_APPROVED`;
- `F`: tập khóa gặp lỗi chưa được giải quyết hoặc chưa có outcome.

Điều kiện đủ để xác nhận coverage theo thiết kế là:

`
Với mọi k thuộc E: count({ i | k thuộc Pᵢ }) = 1
`

Nói cách khác, `E = ⋃ (E ∩ Pᵢ)`, và hai tập `E ∩ Pᵢ`, `E ∩ Pⱼ` không giao nhau khi `i ≠ j`. Đến lúc công bố đầu ra, còn phải đối soát `E = O` theo chính sách cho phép skip; `F` phải rỗng hoặc được xử lý theo quy tắc phát hành cụ thể.

**Cẩn thận với phép đếm:** `SUM(readCount) = COUNT(E)` có thể xảy ra cả khi một khóa bị đọc hai lần và một khóa khác bị bỏ sót. `readCount` cũng có thể khác tập bản ghi cuối cùng do filter, skip, rollback, retry, restart hoặc dữ liệu nguồn thay đổi. Vì vậy hãy so sánh **tập khóa** và trạng thái commit, dùng số đếm làm chỉ báo phụ trợ.

## 3. Chốt “hợp đồng chia partition” trước khi chạy

Trước khi phát hành cần ghi nhận một mô tả cố định, có thể kiểm thử và tái lập:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Phạm vi dữ liệu | Tập nào đủ điều kiện? Có tenant, batch ID, thời điểm chốt, status, soft-delete không? | `batch_id = :batchId AND eligible = true` |
| Khóa định danh | Khóa nào là duy nhất? Có `NULL` hoặc bản ghi trùng không? | `(tenant_id, order_id)` |
| Thuật toán phân vùng | Range, hash, time-window hay khóa nghiệp vụ? Quy tắc định tuyến là gì? | `start_id <= id < end_id` |
| Ranh giới | Bao gồm/loại trừ đầu và cuối như thế nào? | Khoảng nửa mở `[start, end)` |
| Số lượng partition | Giá trị nào quyết định partition count và danh sách tên ổn định? | `gridSize=8` cố định trong cùng job instance |
| Reader | Reader thật sử dụng chính xác predicate nào? | Tham số lấy từ `StepExecutionContext` |
| Khả năng khôi phục | Retry/restart dùng lại snapshot, thuật toán và partition identity nào? | Lưu bounds và `batch_id` của cùng đợt |
| Kết quả | “Đã xử lý” được xác nhận tại ranh giới commit nào? | Bản ghi outcome có unique key trong DB |

Phân biệt `gridSize` với số worker hoặc số task đang chạy đồng thời: `gridSize` là thông tin cấu hình gợi ý số partition cho partitioner; mức thực thi đồng thời còn tùy manager, executor, remote worker và tài nguyên. Số partition **thực tế được tạo** mới là đối tượng cần kiểm tra coverage.

## 4. Kiểm tra partition kiểu range

### 4.1. Ranh giới chuẩn: nửa mở `[start, end)`

Giả sử snapshot dữ liệu có ID nằm trong khoảng từ `1000` (bao gồm) đến `1020` (loại trừ) và chia thành 4 partition:

| Partition | Điều kiện SQL | Các ID số nguyên có thể thuộc phạm vi |
| --- | --- | --- |
| `p0` | `id >= 1000 AND id < 1005` | 1000–1004 |
| `p1` | `id >= 1005 AND id < 1010` | 1005–1009 |
| `p2` | `id >= 1010 AND id < 1015` | 1010–1014 |
| `p3` | `id >= 1015 AND id < 1020` | 1015–1019 |

Cả bốn khoảng phủ đúng `[1000, 1020)`; mỗi ID có đúng một nơi thuộc về. Nếu khóa thực tế có các khoảng nhảy (ví dụ thiếu ID 1006–1009), đó là **khoảng rỗng dữ liệu hợp lệ**, không tự động là lỗ hổng coverage.

Ví dụ sai thường gặp:

- Dùng điều kiện bao gồm cả hai đầu `BETWEEN start AND end` với các ranh giới liền nhau, khiến ID ở biên xuất hiện hai lần.
- Tính `end` bằng phép chia lấy nguyên nhưng quên phân dư, khiến các ID cuối cửa sổ không thuộc partition nào.
- Dùng `id > start` thay vì `id >= start`, vô tình bỏ bản ghi đúng bằng cận đầu.
- Sử dụng giá trị `MAX(id)` làm cận trên nhưng reader dùng `id < end`, khiến bản ghi có ID lớn nhất bị bỏ qua.
- Cố định cận theo `MIN/MAX` rồi để nguồn tiếp tục có thêm bản ghi đủ điều kiện trong cùng job; tập kỳ vọng và tập worker nhìn thấy không còn đồng nhất.

### 4.2. Ví dụ Java: sinh khoảng không trùng, không sót

Đoạn mã sau minh họa một `Partitioner` dùng ranh giới nửa mở, số partition cố định từ `gridSize`, và phép tính `BigInteger` để tránh tràn số khi tính hiệu hai giá trị `long` lớn. Đây là mẫu tạo bounds, cần tích hợp reader, manager step và lưu snapshot phù hợp hệ thống thực:

```java
import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class IdRangePartitioner implements Partitioner {
    private final long startInclusive;
    private final long endExclusive;

    public IdRangePartitioner(long startInclusive, long endExclusive) {
        if (startInclusive >= endExclusive) {
            throw new IllegalArgumentException("Invalid [start, end) range");
        }
        this.startInclusive = startInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        BigInteger lower = BigInteger.valueOf(startInclusive);
        BigInteger span = BigInteger.valueOf(endExclusive).subtract(lower);
        BigInteger requested = BigInteger.valueOf(gridSize);

        // Không tạo partition có khoảng [x, x) khi gridSize > số ID có thể có.
        int count = span.compareTo(requested) < 0
                ? span.intValueExact()
                : gridSize;

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        for (int i = 0; i < count; i++) {
            BigInteger fromOffset = span.multiply(BigInteger.valueOf(i))
                    .divide(BigInteger.valueOf(count));
            BigInteger toOffset = span.multiply(BigInteger.valueOf(i + 1L))
                    .divide(BigInteger.valueOf(count));

            long from = lower.add(fromOffset).longValueExact();
            long to = lower.add(toOffset).longValueExact();

            ExecutionContext context = new ExecutionContext();
            context.putLong("startIdInclusive", from);
            context.putLong("endIdExclusive", to);

            result.put(String.format("range-%05d", i), context);
        }
        return result;
    }
}
```

Reader của **mỗi** worker phải thực sự dùng bounds được truyền cho partition đó:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE batch_id = :batchId
  AND eligible = TRUE
  AND order_id >= :startIdInclusive
  AND order_id <  :endIdExclusive
ORDER BY order_id;
```

Với reader được tạo theo `@StepScope`, ánh xạ `startIdInclusive` và `endIdExclusive` từ `stepExecutionContext` của **worker step**. Mỗi worker cần reader/state riêng nếu reader có trạng thái. Giữ thống nhất tên key, kiểu dữ liệu, bộ lọc và cách lấy `batchId` giữa manager, worker và truy vấn kiểm tra.

**Giới hạn của mẫu:** cận trên `endExclusive` phải biểu diễn được bằng `long`; nếu dữ liệu có khóa `Long.MAX_VALUE` thì phải dùng quy ước cận cuối khác hoặc biểu diễn khoảng thích hợp. Khi cửa sổ đầu vào rỗng, quyết định rõ job sẽ hoàn thành `no-op` hay thất bại vì cấu hình sai; constructor trên cố ý từ chối khoảng rỗng. Nếu định tuyến theo thời gian, composite key hoặc dữ liệu lệch phân phối nặng, cần bộ chia phù hợp thay vì dùng mẫu range ID này một cách máy móc.

### 4.3. Bằng chứng coverage của range

Đối với các khoảng đã sắp theo `start_i`:

1. `start₀ = windowStart`.
2. `end_i = start_(i+1)` với mọi hai khoảng liên tiếp.
3. `end_(n-1) = windowEnd`.
4. `start_i < end_i`, tên partition duy nhất, và bounds thực tế đúng với bounds lưu trong `ExecutionContext`.

Bốn điều kiện này chứng minh các **khoảng** liền nhau, không chồng lấn, phủ hết cửa sổ. Cần kiểm tra tiếp rằng truy vấn reader áp dụng chính xác cùng quy tắc `[start,end)` và đủ các điều kiện lọc nghiệp vụ.

## 5. Nếu chia theo hash, thời gian hoặc khóa nghiệp vụ

### 5.1. Hash partitioning

Với một khóa ổn định `businessKey` và `N` partition, định nghĩa hàm sở hữu rõ ràng:

```text
owner(businessKey) = floorMod(stableHash(canonicalKey), N)
```

Đảm bảo mọi bản ghi có khóa hợp lệ tính ra **đúng một** giá trị trong `0..N-1`, các worker dùng cùng cách chuẩn hóa key, cùng hash và cùng `N`. Hai khóa khác nhau có thể rơi vào cùng partition; đó là điều bình thường. `Math.abs(hash) % N` không an toàn cho giá trị nhỏ nhất của số nguyên có dấu vì `abs` có thể tràn. Thay đổi `N` trong lúc restart có thể đổi owner của cùng khóa; nếu cần mở rộng quy mô, phải có chiến lược chuyển đổi partition ổn định hoặc tái chia và đối soát toàn bộ.

Nếu thao tác của cùng một tài khoản phải đúng thứ tự, hash cùng `accountId` về một partition chỉ giải quyết *định tuyến*; worker bên trong vẫn cần duy trì thứ tự và kiểm soát thực thi đồng thời.

### 5.2. Time-window partitioning

Thống nhất timezone, precision và quy tắc nửa mở (ví dụ `event_time >= startTs AND event_time < endTs`). Kiểm thử biên ở mili/vi giây, đổi ngày, daylight saving nếu áp dụng, sự kiện trễ và timestamp `NULL`. Nếu cửa sổ dựa vào `created_at` trong khi nguồn còn chèn dữ liệu mới, cần xác định cutoff hoặc snapshot để tập xử lý không đổi giữa các worker.

### 5.3. Composite key, skew và giá trị NULL

Nếu ID chỉ duy nhất **trong từng tenant**, khóa coverage phải là `(tenant_id, id)`; dùng riêng `id` có thể cho kết quả đối soát sai. Với `NULL`, điều kiện range thường không bắt được bản ghi; hãy loại chúng khỏi `E` theo quy tắc có văn bản, tạo partition chuyên biệt hoặc xử lý dữ liệu lỗi trước khi chạy. Cần đo skew: một partition có 90% dữ liệu còn các partition khác gần rỗng là coverage vẫn có thể đúng nhưng scaling kém và dễ timeout.

## 6. Đối soát bằng dữ liệu thực

Giả sử hệ thống có bảng chốt dữ liệu `eligible_orders(batch_id, order_id, ...)` với `(batch_id, order_id)` duy nhất, bảng ghi bounds thực tế `partition_bounds(batch_id, partition_name, start_id, end_id)`, và bảng outcome `processing_outcomes(batch_id, order_id, status, ...)`. Hai bảng `partition_bounds` và `processing_outcomes` là **mô hình kiểm chứng minh họa**, không phải bảng metadata mặc định do Spring Batch tạo. Có thể lấy bounds từ `ExecutionContext` rồi tạo dữ liệu kiểm chứng riêng.

### 6.1. Kiểm tra mỗi bản ghi được giao đúng một partition

```sql
SELECT
    e.order_id,
    COUNT(p.partition_name) AS matched_partitions
FROM eligible_orders e
LEFT JOIN partition_bounds p
       ON p.batch_id = e.batch_id
      AND e.order_id >= p.start_id
      AND e.order_id <  p.end_id
WHERE e.batch_id = :batchId
GROUP BY e.order_id
HAVING COUNT(p.partition_name) <> 1;
```

Kết quả bắt buộc **0 hàng**. `matched_partitions = 0` chỉ ra bản ghi không thuộc partition nào; `> 1` chỉ ra các partition có phạm vi chồng lấn trên khóa đó. Điều kiện này bảo vệ coverage **ở mức bản ghi thực tế**, kể cả khi dữ liệu ID có lỗ hổng. Tuy nhiên, để chứng minh cả khoảng dự kiến không có gap/overlap ở các vị trí hiện chưa có dữ liệu, vẫn cần kiểm tra tính liên tục của bounds tại mục 4.3.

### 6.2. Kiểm tra ranh giới và tính hợp lệ của từng partition

```sql
-- Ví dụ SQL có window function LAG (điều chỉnh cú pháp theo RDBMS).
WITH ordered AS (
    SELECT
        partition_name,
        start_id,
        end_id,
        LAG(end_id) OVER (ORDER BY start_id, partition_name) AS prev_end
    FROM partition_bounds
    WHERE batch_id = :batchId
)
SELECT
    partition_name, start_id, end_id, prev_end,
    CASE
        WHEN start_id >= end_id THEN 'INVALID_RANGE'
        WHEN prev_end < start_id THEN 'GAP'
        WHEN prev_end > start_id THEN 'OVERLAP'
        ELSE 'CHECK_WINDOW_ENDPOINTS'
    END AS issue
FROM ordered
WHERE start_id >= end_id
   OR prev_end <> start_id;
```

Ngoài kết quả 0 hàng từ truy vấn này, đối chiếu **`MIN(start_id) = windowStart`**, **`MAX(end_id) = windowEnd`**, không có partition trùng tên và số partition thực tế bằng số đã chốt. Khi không có dòng nào trong bảng bounds, `MIN/MAX` sẽ là `NULL` nên phải coi là lỗi nếu kỳ vọng có dữ liệu. Truy vấn trên chỉ so các khoảng liền kề; nếu có ranh giới hoặc thứ tự dữ liệu bất thường, dùng thêm đối soát ở 6.1 và kiểm tra cấu hình để xác nhận.

### 6.3. Kiểm tra đầy đủ kết quả đã commit

Nếu nghiệp vụ yêu cầu mỗi bản ghi có outcome `COMPLETED` hoặc `SKIPPED_APPROVED`:

```sql
-- Các khóa chưa có trạng thái cuối cùng được chấp nhận.
SELECT e.order_id
FROM eligible_orders e
LEFT JOIN processing_outcomes o
       ON o.batch_id = e.batch_id
      AND o.order_id = e.order_id
      AND o.status IN ('COMPLETED', 'SKIPPED_APPROVED')
WHERE e.batch_id = :batchId
  AND o.order_id IS NULL;
```

Truy vấn phải trả về **0 hàng** trước khi xuất bản thành quả của batch. Đồng thời kiểm tra `processing_outcomes` không có khóa ngoài tập `E` và không có nhiều outcome cuối cùng mâu thuẫn cho cùng khóa. Ràng buộc `UNIQUE(batch_id, order_id)` cùng logic ghi idempotent có thể ngăn duplicate ở tầng database. Nếu hệ thống cho phép skip, phải lưu lý do skip và chính sách công nhận rõ ràng; `skipCount` trong metadata một mình không chứng minh đúng tập bản ghi đã được xử lý.

**Chỉ số cần phân biệt:** coverage của phân vùng (`mỗi khóa được giao đúng 1 lần`) khác với coverage của kết quả (`mỗi khóa có kết quả cuối hợp lệ`). Một partition có thể nhận đúng khóa nhưng worker thất bại; khi đó chia partition đúng nhưng production gate về hoàn thành dữ liệu vẫn chưa đạt.

## 7. Restart, retry và metadata Spring Batch

Spring Batch có `JobRepository`, `JobExecution`, `StepExecution` và `ExecutionContext` để lưu trạng thái chạy và hỗ trợ restart. Với partitioning, manager giao context cho các worker step có danh tính partition; hoàn thành một partition không đồng nghĩa với tất cả partition đã xong.

Trước production cần xác minh:

- **Partition name ổn định qua restart.** Khi chạy lại cùng job instance, không tự sinh tên ngẫu nhiên hoặc thay đổi thuật toán khiến partition cũ không còn khớp với metadata. Với một số cách cấu hình, manager sử dụng trạng thái step trước đó để chọn partition cần chạy lại.
- **Giữ cùng tập đầu vào.** Nếu `MIN/MAX`, cutoff, bộ lọc hoặc `gridSize` được tính lại dựa trên dữ liệu đang biến động, partition cũ và mới có thể chồng lấn/bỏ sót; lưu cấu hình và snapshot theo job instance hoặc có quy trình tái chia được thiết kế tường minh.
- **Độc lập trạng thái reader.** Các worker có reader/stream state riêng; nếu dùng một bean có mutable state chung phải kiểm tra thread safety. Một reader sai predicate có thể phá coverage dù `Partitioner` chia đúng.
- **Commit và idempotency.** Chạy lại partition có thể xử lý lại các chunk trước đó; writer phải có khóa nghiệp vụ, ràng buộc hoặc upsert phù hợp. Tác dụng phụ qua API/broker cần idempotency key, outbox hoặc đối soát riêng vì rollback transaction DB không tự hoàn tác tác dụng bên ngoài.
- **Dừng, lỗi và hoàn tất.** Kiểm tra trạng thái `FAILED`, `STOPPED`, `COMPLETED` của toàn bộ worker steps và điều kiện job flow. Không lấy worker báo hoàn tất sau cùng làm dấu mốc đã xử lý toàn bộ dữ liệu.

Với remote partitioning, kết hợp thông tin giao việc, lần thử, job instance và trạng thái worker để phát hiện partition mất phản hồi, được giao lại hoặc chạy trùng. Việc có thể giao lại công việc yêu cầu xử lý an toàn khi một partition được chạy nhiều lần; chỉ số “đã dispatch thành công” không xác nhận commit.

## 8. Bộ kiểm thử coverage trước khi phát hành

| Trường hợp | Dữ liệu/điều kiện đưa vào | Kỳ vọng |
| --- | --- | --- |
| Ranh giới đầu/cuối | Khóa bằng `windowStart`, `windowEnd - 1` và sát điểm chia | Mỗi khóa thuộc đúng 1 partition; khóa ở `windowEnd` bị loại đúng hợp đồng |
| Chia có dư | Số khóa có thể có không chia hết cho `N` | Không mất phần dư ở cuối, không có gap hoặc overlap |
| Cửa sổ nhỏ | Ít ID hơn `gridSize`, hoặc tập eligible rỗng | Không tạo range đảo/rỗng ngoài chủ đích; xử lý no-op rõ ràng |
| ID không liên tục | Nhiều ID bị thiếu, partition không có bản ghi | Đối soát tập eligible vẫn đạt; partition rỗng không bị hiểu nhầm là mất dữ liệu |
| Giá trị biên | ID âm, cận gần giới hạn `long`, khóa NULL | Không tràn số, không bỏ lọt bản ghi cần xử lý |
| Skew dữ liệu | 1 partition chứa phần lớn dữ liệu | Coverage đúng; thời gian/nguồn lực vẫn đáp ứng SLO |
| Retry và rollback | Writer lỗi sau khi xử lý một phần; chunk rollback | Khôi phục không tạo trùng kết quả hoặc lỗ hổng |
| Crash/restart | Dừng manager/worker giữa chừng và khởi động lại | Chỉ các phần việc cần thiết được chạy lại; tập outcome cuối đầy đủ |
| Worker nhận trùng | Mô phỏng giao lại partition/chạy lặp | Idempotent, không tạo side effect kép |
| Nguồn thay đổi | Insert/update trong khi job đang chạy | Snapshot/cutoff giữ nguyên tập eligible của job |
| Tăng/giảm concurrency | Thay pool size, độ trễ I/O, số worker | Coverage và kết quả không thay đổi theo thứ tự hoàn tất |
| Đổi cấu hình partition | Thử thay `gridSize` hoặc hash algorithm khi restart | Cấu hình bị chặn hoặc đi qua thủ tục tái chia/đối soát an toàn |

Nên chạy ít nhất một bộ kiểm thử dữ liệu lớn với phân phối lệch, inject lỗi tại các biên commit và đo throughput, số retry, số partition chậm nhất. Mục đích vừa chứng minh correctness vừa tìm được nút thắt thực sự khi scale.

## 9. Checklist chấp nhận production

Đánh dấu một mục **PASS** chỉ khi có bằng chứng tái lập, không dựa vào việc “chạy thử thấy ổn”.

- [ ] **Dataset đã chốt:** `batchId`/snapshot/cutoff, bộ lọc, timezone và khóa duy nhất đã được ghi rõ.
- [ ] **Partitioner hợp lệ:** kiểm tra bounds hoặc hàm owner; phạm vi phủ kín, không chồng lấn, có quy tắc xử lý NULL và cận số.
- [ ] **Reader khớp partitioner:** predicate, cận bao gồm/loại trừ và tham số context trùng với hợp đồng đã chốt.
- [ ] **Mỗi khóa thuộc đúng một partition:** truy vấn/kiểm thử tương đương mục 6.1 trả về 0 lỗi.
- [ ] **Khoảng range phủ đủ cửa sổ:** nếu chia range, đã xác minh cận đầu, cận cuối, mọi cặp biên liền kề và partition không hợp lệ.
- [ ] **Phân bổ tài nguyên hợp lý:** số partition, parallelism và mức skew đã được đo; không có worker chậm ngoài giới hạn vận hành chấp nhận.
- [ ] **Restart ổn định:** partition identity, số lượng/cách chia, trạng thái reader và tập dữ liệu được tái sử dụng hoặc có quy trình tái chia an toàn.
- [ ] **Writer chống ghi trùng:** kết quả DB và side effect ngoài transaction có cơ chế idempotency/đối soát thích hợp.
- [ ] **Hoàn tất có thể chứng minh:** kiểm tra tập outcome `COMPLETED`/skip được duyệt, dữ liệu không có missing/unexpected/duplicate keys và lỗi worker còn tồn đọng.
- [ ] **Đã thử tình huống lỗi thực:** crash, retry, redeploy worker và thay đổi độ song song vẫn giữ invariant coverage.
- [ ] **Có khả năng quan sát:** dashboard/cảnh báo cho partition `FAILED`/`STOPPED`, pending quá lâu, tiến độ, số khóa thiếu/trùng và lệch giữa input/outcome.
- [ ] **Có bằng chứng audit:** lưu thông số chia, thời điểm snapshot, kết quả truy vấn coverage, trạng thái các step, bản chạy kiểm thử và người duyệt.

Mẫu biên bản phát hành có thể ghi:

```text
Job: orderProcessingJob
Job instance / business batch: <stable-id>
Snapshot / cutoff: <timestamp-or-snapshot-id>
Expected eligible keys: <count>
Partition strategy: range [startInclusive, endExclusive)
Partition names and bounds: <audit location>
Expected partitions / actual partitions: <n> / <n>
Gap / overlap count: 0 / 0
Keys assigned to 0 or >1 partitions: 0
Missing / unexpected / duplicate outcome keys: 0 / 0 / 0
Allowed skipped keys: <count, reasons and approval>
All required worker steps: COMPLETED
Crash/restart test: PASS
Production coverage gate: PASS / FAIL
```

Nếu có bất kỳ điều kiện về coverage, đầu ra hoặc restart chưa đạt, **không đánh dấu hoàn tất checklist**. Ghi lại khóa bị ảnh hưởng, partition liên quan, trạng thái thực thi, quyết định khôi phục và chạy lại đối soát sau sửa lỗi.

## 10. Cách theo dõi sau khi triển khai

Trong vận hành, dashboard nên liên kết `jobInstanceId`/`jobExecutionId`, partition name, bounds và metrics theo từng worker. Theo dõi ít nhất: số khóa eligible dự kiến, số khóa có outcome, số khóa không có owner hoặc nhiều owner, số partition hoàn tất/thất bại, `read/write/skip/rollback`, latency theo partition và tình trạng backlog. Số liệu từ nhiều lần `JobExecution` khi restart cần được tổng hợp theo **khóa nghiệp vụ và trạng thái đã commit**, tránh cộng dồn `readCount` giữa các lần thử rồi hiểu nhầm là số item duy nhất.

Một chỉ số mismatch hoặc lỗi worker cần dẫn đến drill-down vào các **khóa cụ thể**, không chỉ là cảnh báo số lượng. Khi thay thuật toán chia, số partition hoặc thay đổi schema/filter, chạy lại kiểm thử coverage và lưu bằng chứng như một phần của thay đổi triển khai.

**Tiêu chí kết luận:** mục “Đã kiểm tra partition coverage” chỉ đạt `PASS` khi chứng minh tập dữ liệu đủ điều kiện được giao đúng một lần theo hợp đồng, mọi kết quả cuối được đối soát sau commit/restart và các ranh giới chia vẫn đúng dưới cấu hình production thực tế.
