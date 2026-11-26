# Kiểm tra khả năng chia nhỏ dữ liệu trước khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định một workload có thể chia thành các phần xử lý độc lập hay không, trước khi chọn multi-threaded step, parallel steps, partitioning hoặc xử lý phân tán.
- Định nghĩa và kiểm chứng các bất biến **bao phủ đầy đủ**, **không chồng lấn**, **có thể tái lập** và **an toàn khi ghi**.
- Chọn khóa chia dữ liệu phù hợp (ID range, thời gian, tenant, hash, file) dựa trên phân bố dữ liệu, truy vấn và yêu cầu nghiệp vụ.
- Ước lượng độ lệch tải, chi phí chia/gộp, giới hạn DB/API và khả năng cân bằng của các partition.
- Thiết kế kiểm thử, checkpoint, retry và restart trước khi tăng concurrency cho workload dữ liệu lớn.

## 1. Vì sao cần kiểm tra khả năng chia nhỏ dữ liệu?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, mục tiêu là mở rộng Spring Batch khi dữ liệu lớn: đa luồng trong step, chạy các flow song song, partitioning và các mô hình worker phân tán. Tuy nhiên, **nhiều thread không mặc nhiên làm một bài toán có thể xử lý song song**.

Ví dụ một job mỗi đêm cần đọc 12 triệu đơn hàng, chuẩn hóa dữ liệu, ghi kết quả vào bảng đích. Job hiện mất 4 giờ, trong khi cửa sổ xử lý chỉ có 90 phút. Nhóm vận hành muốn dùng 8 worker. Câu hỏi đầu tiên không phải “chỉnh `gridSize` bằng bao nhiêu?”, mà là:

> Có thể xác định 8 phần công việc sao cho mọi bản ghi được xử lý đúng phạm vi, các worker không phụ thuộc thứ tự của nhau, và lỗi/restart không làm bỏ sót hoặc ghi trùng kết quả hay không?

Nếu không chứng minh được những điều này, tăng worker có thể chỉ làm tăng số kết nối, số transaction, deadlock và chi phí phục hồi.

### Chia dữ liệu khác với chia bước

| Hình thức | Đơn vị song song | Điều phải kiểm tra |
| --- | --- | --- |
| **Multi-threaded step** | Tác vụ/chunk/processor trong cùng một step, tùy phiên bản Spring Batch | Reader, processor, writer và trạng thái chung có an toàn khi truy cập song song không? |
| **Parallel steps** | Các flow/step tương đối độc lập | Có dependency nghiệp vụ giữa các flow không? Khi nào cần join? |
| **Partitioning** | Nhiều `StepExecution` của cùng worker step; mỗi partition có `ExecutionContext` riêng | Dữ liệu có chia thành các miền độc lập, bao phủ đủ và có thể phục hồi không? |
| **Remote partitioning** | Partition được giao cho worker ở JVM/máy khác | Ngoài tính chia được, cần vận chuyển thông tin partition, xử lý timeout, retry và worker chết |
| **Remote chunking** | Manager đọc, worker xử lý/ghi các chunk được gửi đi | Không tự giải quyết việc chia miền đọc; cần cơ chế giao nhận và chống ghi lặp |

Trong bài này, “chia nhỏ dữ liệu” chủ yếu nói đến **khả năng partition** ở bước đọc/xử lý dữ liệu. Các hình thức song song khác vẫn được xem xét để quyết định kiến trúc đúng.

## 2. Bốn bất biến của một cách chia dữ liệu đúng

Gọi tập dữ liệu cần xử lý tại một **mốc dữ liệu đã xác định** là `D`. Ta dự kiến tạo các partition `P₁, P₂, …, Pₙ`.

### 2.1. Bao phủ đầy đủ (completeness)

Mọi bản ghi thuộc phạm vi nghiệp vụ phải nằm trong ít nhất một partition:

~~~text
D = P1 ∪ P2 ∪ ... ∪ Pn
~~~

Một bản ghi có ID tại ranh giới, nằm ở tenant ít dữ liệu hoặc đến cuối khoảng thời gian không được bị bỏ sót. Nếu nguồn dữ liệu thay đổi trong lúc đọc, phải nói rõ “`D`” là snapshot hay cửa sổ nào; nếu không, khái niệm “bao phủ đủ” không còn cố định.

### 2.2. Không chồng lấn (disjointness)

Một bản ghi không được giao cho hai partition khác nhau:

~~~text
Pi ∩ Pj = ∅ khi i ≠ j
~~~

Đây là bất biến của **phân công dữ liệu đầu vào**. Ngay cả khi writer dùng `UPSERT` để tránh duplicate ở bảng đích, overlap vẫn có thể khiến hai worker tính toán trùng, gọi API hai lần, tăng lock và tạo kết quả phụ thuộc thứ tự.

Với khoảng số nguyên, quy ước dễ kiểm soát nhất là **đầu bao gồm, cuối không bao gồm**:

~~~sql
WHERE id >= :startId
  AND id <  :endExclusive
~~~

Hai khoảng `[1, 250001)` và `[250001, 500001)` liền kề nhưng không trùng ID `250001`.

### 2.3. Có thể tái lập khi restart (repeatability)

Một partition đã được đặt tên, ví dụ `partition002`, cần trỏ tới cùng phạm vi công việc khi job được restart. Điều này đòi hỏi:

- Tên partition và key trong `ExecutionContext` ổn định.
- Ranh giới hoặc quy tắc chia được lưu và tái tạo nhất quán với **cùng `JobInstance`**.
- Tập đầu vào được cố định bằng snapshot, watermark, staging table hoặc nguyên tắc bất biến phù hợp.
- Thứ tự đọc phục vụ checkpoint là xác định được: `ORDER BY` trên khóa duy nhất/ổn định, không dựa vào thứ tự DB ngẫu nhiên.

Nếu chạy lần đầu với `MIN(id)=1`, `MAX(id)=1_000_000`, rồi lần restart tính lại biên từ bảng đã có 200.000 bản ghi mới, cùng tên partition có thể nhận miền khác. Checkpoint cũ khi đó có thể không còn chỉ đúng vị trí.

### 2.4. Độc lập về xử lý và side effect (independence)

Chia tập đầu vào thành các phần rời nhau **chưa đủ** để các worker thực sự độc lập.

Ví dụ, mỗi worker tính tổng tiền của một nhóm đơn hàng riêng nhưng tất cả cùng cập nhật trường `daily_total` bằng cách “đọc giá trị cũ, cộng thêm, ghi lại”. Các tập ID không trùng nhau, nhưng thao tác ghi vẫn có thể tạo **lost update**.

Để an toàn, cần xác minh:

- Processor không phụ thuộc kết quả chưa hoàn tất của partition khác.
- Writer có ràng buộc khóa, transaction và chiến lược upsert/merge phù hợp.
- Không có mutable state dùng chung gây race (cache, accumulator, reader cursor, file handle).
- Các side effect ngoài transaction (HTTP, email, message) có key idempotency/deduplication nếu có khả năng retry.
- Bước tổng hợp toàn cục chỉ chạy sau khi các partition cần thiết hoàn thành và có kết quả hợp lệ.

**Bốn bất biến là cổng kiểm tra tính đúng đắn.** Hiệu năng tốt chỉ được xét sau khi tất cả bất biến phù hợp nghiệp vụ được chứng minh.

## 3. Thu thập dữ liệu trước khi chọn khóa partition

Không thể quyết định cách chia chỉ bằng tổng số bản ghi. Hãy thu thập các thông tin dưới đây từ dữ liệu và pipeline thực tế.

| Câu hỏi kiểm tra | Ví dụ dấu hiệu tốt | Dấu hiệu cần xử lý |
| --- | --- | --- |
| Có khóa định danh ổn định và duy nhất không? | `BIGINT PRIMARY KEY`, khóa tổng hợp duy nhất | Không có khóa, bản ghi trùng hoặc khóa có thể thay đổi |
| Có lọc nhanh theo miền dữ liệu không? | Query dùng index trên `id`/`tenant_id`/thời gian | Mỗi worker quét toàn bảng; tăng worker làm tăng full scan |
| Dữ liệu có đứng yên trong một lần chạy không? | Staging snapshot theo `runKey` | Bản ghi thêm/xóa/sửa làm offset/cursor dịch chuyển |
| Khối lượng có phân bố đều không? | Các khoảng có read count/thời gian gần nhau | Một tenant chiếm 70% dữ liệu, các partition khác hầu như rỗng |
| Có liên kết nhiều bản ghi phải xử lý cùng nhau không? | Mỗi order được xử lý riêng | Cần tính tổng theo customer và toàn bộ giao dịch của customer |
| Output có thể ghi độc lập không? | Upsert theo khóa duy nhất của bản ghi | Nhiều worker cập nhật chung một dòng tổng hợp |
| Có giới hạn bên ngoài không? | DB và API có dư throughput/connection | API rate limit, DB lock, pool nhỏ, disk bão hòa |
| Có hỗ trợ restart đúng ngữ nghĩa không? | Mốc dữ liệu + context + checkpoint ổn định | Cách chia phụ thuộc `NOW()` hoặc trạng thái nguồn biến động |

### Phân biệt số lượng bản ghi và chi phí xử lý

Một partition có 1 triệu bản ghi ảnh nhỏ và partition khác cũng 1 triệu bản ghi video dài có thể khác nhau rất nhiều về CPU, RAM và I/O. Chi phí thực tế nên ước lượng bằng **thời gian xử lý**, số byte, số query, kích thước payload, số request HTTP hoặc trọng số nghiệp vụ thay vì chỉ dựa vào `COUNT(*)`.

Với bảng có ID thưa, chia đều **khoảng ID** không tương đương chia đều **số bản ghi**. Chẳng hạn khoảng `[1, 250001)` có 900.000 bản ghi nhưng khoảng `[750001, 1000001)` chỉ có 5.000 bản ghi; chia đúng về mặt logic nhưng tốc độ bị quyết định bởi partition nặng nhất.

## 4. Các phương án chia dữ liệu thường gặp

| Phương án | Phù hợp khi | Rủi ro chính | Cách cải thiện |
| --- | --- | --- | --- |
| **ID range**: `[start, end)` | Khóa số nguyên ổn định, có index, lọc range hiệu quả | Khoảng ID không đều, khóa đổi, insert trong lúc chạy | Dùng histogram/quantile, snapshot; đo count và thời gian mỗi range |
| **Time window**: `[t0, t1)` | Event có timestamp bất biến, nghiệp vụ theo cửa sổ | Event đến muộn, lệch timezone, timestamp trùng tại ranh giới | Định nghĩa watermark, UTC, chính sách late arrival |
| **Tenant/customer/group key** | Mỗi tenant/khách hàng là miền tính toán độc lập | Một tenant quá lớn (hot partition), khóa không ổn định | Group theo chi phí; cân nhắc chia tiếp tenant lớn nếu nghiệp vụ cho phép |
| **Hash bucket**: `hash(key) mod N` | Phân bố khóa tương đối đều, có thể dùng phân vùng/hash DB | Hash không ổn định, thay `N` làm đổi toàn bộ assignment, query không dùng index | Cố định hàm hash/`N`, lưu mapping, cân nhắc bucket vật lý |
| **Danh sách file** | File độc lập và có thể xử lý từng file | File kích thước lệch; file bị thay thế trong lúc chạy | Manifest cố định gồm path, checksum/version; chia file lớn nếu định dạng cho phép |
| **Byte range của file** | File có thể seek và xác định ranh giới record | Cắt giữa dòng, record nhiều dòng, mã hóa/compression | Tìm ranh giới record thật; không cắt tùy ý gzip không splittable |
| **Partition theo khóa tổng hợp** | `(businessDate, tenantId, id)` xác định miền xử lý | Sai thứ tự lexicographic, thiếu index, overlap phức tạp | Quy ước biên rõ ràng và index phù hợp khóa tổng hợp |

Với **hash**, cần quy định hàm hash và cách chuẩn hóa khóa; không dùng một phương thức phụ thuộc runtime/process rồi mong hai worker hay lần restart cho cùng kết quả. Với số âm, phép modulo của ngôn ngữ có thể tạo bucket âm; phải chuẩn hóa phù hợp. Thay đổi số bucket có thể làm thay đổi assignment, vì vậy phải xét tác động đến restart.

Với **time range**, nên dùng thời điểm chuẩn hóa rõ ràng (thường UTC ở tầng lưu trữ) và tránh `BETWEEN` ở hai partition liền nhau nếu cả hai lấy cả hai đầu: event đúng ranh giới sẽ bị tính hai lần.

### Trường hợp không thể hoặc không nên chia tùy ý

- Tính số dư tuần tự: bản ghi sau phụ thuộc số dư đã tính của bản ghi trước **trong cùng tài khoản**. Có thể chia theo tài khoản, không được chia ngẫu nhiên mọi giao dịch.
- Sinh một số thứ tự toàn cục có ý nghĩa nghiệp vụ theo thời gian: cần cơ chế cấp phát thứ tự hoặc bước merge riêng.
- Một file nén một luồng duy nhất, không thể seek theo record: có thể chỉ chia theo nhiều file hoặc cần bước chuyển đổi định dạng.
- API nguồn chỉ cho một cursor tuần tự hoặc giới hạn một consumer: nhiều worker có thể không giúp đọc nhanh hơn.
- Tính aggregate toàn cục: có thể chia thành **partial aggregates** rồi có bước reduce/merge, nhưng phải chứng minh phép kết hợp đúng (ví dụ tổng/đếm có tính kết hợp; median hay thứ tự toàn cục không cộng thẳng được).

Nếu bài toán không thỏa điều kiện độc lập, giải pháp có thể là **đổi thuật toán** (map → reduce), tách thành các flow có dependency hoặc giữ một worker nhưng tối ưu query/IO.

## 5. Ví dụ: chia dữ liệu snapshot theo ID cho Spring Batch

Giả sử bảng nguồn có ID từ 1 đến 1.000.000. Để dữ liệu ổn định khi restart, job chuẩn bị một **staging snapshot** trước khi gọi manager step. Mỗi snapshot có `run_key` bất biến, ví dụ `orders-2026-11-25`:

~~~sql
CREATE TABLE batch_input_snapshot (
    run_key   VARCHAR(100) NOT NULL,
    source_id BIGINT       NOT NULL,
    payload   TEXT         NOT NULL,
    PRIMARY KEY (run_key, source_id)
);

CREATE TABLE batch_output (
    run_key   VARCHAR(100) NOT NULL,
    source_id BIGINT       NOT NULL,
    payload   TEXT         NOT NULL,
    PRIMARY KEY (run_key, source_id)
);
~~~

Với PostgreSQL, sau khi quyết định tập bản ghi đầu vào, một bước chuẩn bị có thể vật hóa snapshot bằng một câu lệnh `INSERT … SELECT` trong transaction phù hợp. Nếu dữ liệu gồm nhiều bảng cần snapshot nhất quán, phải thiết kế mức isolation hoặc cơ chế snapshot thích hợp; không mặc định các query ở nhiều worker cùng nhìn một snapshot transaction.

Giả sử staging đã hoàn tất, bất biến trong thời gian chạy và chỉ chứa ID cần xử lý trong `[1, 1_000_001)`. Bốn partition sẽ nhận:

| Partition | `startId` | `endExclusive` | Điều kiện đọc |
| --- | ---: | ---: | --- |
| `partition000` | 1 | 250001 | `source_id >= 1 AND source_id < 250001` |
| `partition001` | 250001 | 500001 | `source_id >= 250001 AND source_id < 500001` |
| `partition002` | 500001 | 750001 | `source_id >= 500001 AND source_id < 750001` |
| `partition003` | 750001 | 1000001 | `source_id >= 750001 AND source_id < 1000001` |

Sự liên tiếp của các khoảng bảo đảm không bỏ trống **giá trị ID trong miền dự kiến**, dù thực tế ID có lỗ hổng. Điều này không tự chứng minh phân bố số bản ghi đều.

### 5.1. Một `Partitioner` tạo miền không giao nhau

Đoạn Java bên dưới minh họa API thường dùng ở **Spring Batch 5.x**, Java 17. Ví dụ chỉ tính toán trên miền số nguyên không âm với độ rộng vừa `long`; ranh giới đã được xác định trước và giữ ổn định giữa các lần restart.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class StableRangePartitioner implements Partitioner {
    private final long firstInclusive;
    private final long endExclusive;

    public StableRangePartitioner(long firstInclusive, long endExclusive) {
        if (firstInclusive < 0 || endExclusive < firstInclusive) {
            throw new IllegalArgumentException("Invalid nonnegative ID range");
        }
        this.firstInclusive = firstInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = endExclusive - firstInclusive;
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        if (total == 0) {
            return partitions; // Không có ID cần xử lý.
        }

        int count = (int) Math.min(total, (long) gridSize);
        long base = total / count;
        long remainder = total % count;
        long start = firstInclusive;

        for (int i = 0; i < count; i++) {
            long width = base + (i < remainder ? 1 : 0);
            long end = start + width;

            ExecutionContext context = new ExecutionContext();
            context.putLong("startId", start);
            context.putLong("endExclusive", end);
            partitions.put(String.format("partition%03d", i), context);

            start = end;
        }

        if (start != endExclusive) {
            throw new IllegalStateException("Partition boundaries do not cover range");
        }
        return partitions;
    }
}
~~~

Các lưu ý quan trọng:

- `gridSize` là **số phần dự kiến**, không tự bảo đảm cùng số thread đang hoạt động. Executor và handler quyết định concurrency thực tế.
- `count` không vượt số giá trị ID trong miền. Đây là cách chia theo **độ rộng ID**, không theo số bản ghi thực tế.
- Nếu cho phép thay `gridSize` khi restart rồi tái phân chia lại với cùng tên partition, ranh giới có thể đổi. Cần cố định cấu hình/cách chia cho một `JobInstance` hoặc dựa vào context đã persist đúng quy tắc Spring Batch.
- Nếu bảng nguồn bị thay đổi, tạo lại `MIN/MAX` và chia lại có thể khiến checkpoint không khớp. Vì vậy cần snapshot/manifest hoặc một phương pháp đóng băng miền đọc.

### 5.2. Reader `@StepScope` nhận đúng range của từng partition

Một reader có cursor cần instance và trạng thái riêng cho `StepExecution` của từng worker. Dưới đây là reader mẫu, giả định `runKey` là identifying `JobParameter` bất biến của một lần chạy logic:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(String runKey, long sourceId, String payload) {}

// Khai báo trong một class @Configuration của Spring.
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> snapshotReader(
        DataSource dataSource,
        @Value("#{jobParameters['runKey']}") String runKey,
        @Value("#{stepExecutionContext['startId']}") Long startId,
        @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {

    if (runKey == null || startId == null || endExclusive == null
            || startId >= endExclusive) {
        throw new IllegalArgumentException("Missing partition identity/range");
    }

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("snapshotReader")
            .dataSource(dataSource)
            .sql("""
                SELECT run_key, source_id, payload
                FROM batch_input_snapshot
                WHERE run_key = ?
                  AND source_id >= ?
                  AND source_id < ?
                ORDER BY source_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, runKey);
                ps.setLong(2, startId);
                ps.setLong(3, endExclusive);
            })
            .rowMapper((rs, rowNum) -> new OrderRow(
                    rs.getString("run_key"),
                    rs.getLong("source_id"),
                    rs.getString("payload")))
            .saveState(true)
            .build();
}
~~~

Giá trị `startId` và `endExclusive` đến từ **`StepExecutionContext`**, còn `runKey` đến từ `JobParameters`. Bean `@StepScope` được tạo trễ theo `StepExecution`; không tạo reader dùng chung có cursor mutable giữa các partition. Return type cụ thể `JdbcCursorItemReader<OrderRow>` giúp Batch nhận diện `ItemStream` và quản lý `open/update/close`, checkpoint.

Để tránh ghi trùng khi retry, bảng đích dùng khóa chính `(run_key, source_id)`. Với PostgreSQL, writer stateless có thể upsert từng record:

~~~java
@Bean
ItemWriter<OrderRow> snapshotWriter(JdbcTemplate jdbc) {
    return chunk -> {
        for (OrderRow row : chunk) {
            jdbc.update("""
                INSERT INTO batch_output(run_key, source_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT (run_key, source_id) DO UPDATE
                SET payload = EXCLUDED.payload
                """, row.runKey(), row.sourceId(), row.payload());
        }
    };
}
~~~

Các import `ItemWriter`/`JdbcTemplate` tương ứng đến từ `org.springframework.batch.item.ItemWriter` và `org.springframework.jdbc.core.JdbcTemplate`. Đây là writer dễ đọc để minh họa; với throughput lớn hãy đo và cân nhắc JDBC batch writer. `UPSERT` giúp tránh duplicate theo khóa, nhưng không bảo đảm an toàn với mọi side effect bên ngoài DB.

Manager step cấu hình `.partitioner("workerStep", partitioner).step(workerStep).gridSize(4).taskExecutor(executor)`, còn worker step dùng `.chunk(200, transactionManager).reader(snapshotReader).writer(snapshotWriter)`. Mỗi partition có `StepExecution` và transaction chunk riêng. Bước snapshot cần **hoàn tất trước** khi manager được chạy; nếu cần xuất kết quả chung, đặt bước đó **sau manager** trong cùng flow để chỉ thực hiện khi manager kết thúc thành công theo các transition.

### 5.3. Sơ đồ dữ liệu và điểm kiểm tra

~~~mermaid
flowchart TD
    D["Source data"] --> S["Snapshot theo runKey, hoàn tất trước manager"]
    S --> M["Manager Step / Partitioner"]
    M --> P0["P0: [1,250001)"]
    M --> P1["P1: [250001,500001)"]
    M --> P2["P2: [500001,750001)"]
    M --> P3["P3: [750001,1000001)"]
    P0 --> W0["Worker StepExecution 0"]
    P1 --> W1["Worker StepExecution 1"]
    P2 --> W2["Worker StepExecution 2"]
    P3 --> W3["Worker StepExecution 3"]
    W0 --> T["batch_output: upsert keyed by runKey + sourceId"]
    W1 --> T
    W2 --> T
    W3 --> T
    T --> C["Reconciliation / merge sau manager"]
~~~

## 6. Kiểm chứng bao phủ và không chồng lấn bằng SQL

Trước khi chạy thật, cần xác nhận **mọi bản ghi nguồn được gán đúng một lần**. Với PostgreSQL, truy vấn kiểm tra mẫu:

~~~sql
WITH partitions(partition_name, start_id, end_exclusive) AS (
    VALUES
        ('partition000', 1::BIGINT, 250001::BIGINT),
        ('partition001', 250001::BIGINT, 500001::BIGINT),
        ('partition002', 500001::BIGINT, 750001::BIGINT),
        ('partition003', 750001::BIGINT, 1000001::BIGINT)
),
assignments AS (
    SELECT s.source_id,
           COUNT(p.partition_name) AS assigned_count
    FROM batch_input_snapshot s
    LEFT JOIN partitions p
      ON s.source_id >= p.start_id
     AND s.source_id < p.end_exclusive
    WHERE s.run_key = :runKey
    GROUP BY s.source_id
)
SELECT COUNT(*) AS source_rows,
       COUNT(*) FILTER (WHERE assigned_count = 0) AS missing_rows,
       COUNT(*) FILTER (WHERE assigned_count > 1) AS duplicated_assignments
FROM assignments;
~~~

Kỳ vọng: `missing_rows = 0` và `duplicated_assignments = 0`. Truy vấn giả định `source_id` là duy nhất trong một `run_key` nhờ primary key. Không chỉ dùng `SUM(count_per_partition) = COUNT(*)`: một bản ghi bị đọc hai lần và một bản ghi khác bị bỏ sót có thể triệt tiêu nhau về tổng số.

Muốn xem độ lệch tải theo số bản ghi:

~~~sql
WITH partitions(partition_name, start_id, end_exclusive) AS (
    VALUES
        ('partition000', 1::BIGINT, 250001::BIGINT),
        ('partition001', 250001::BIGINT, 500001::BIGINT),
        ('partition002', 500001::BIGINT, 750001::BIGINT),
        ('partition003', 750001::BIGINT, 1000001::BIGINT)
)
SELECT p.partition_name, COUNT(s.source_id) AS source_rows
FROM partitions p
LEFT JOIN batch_input_snapshot s
  ON s.run_key = :runKey
 AND s.source_id >= p.start_id
 AND s.source_id < p.end_exclusive
GROUP BY p.partition_name
ORDER BY p.partition_name;
~~~

Ngoài SQL đếm bản ghi, phải đối chiếu **đầu ra thực tế** theo `run_key` với đầu vào. Có thể kiểm tra tập khóa thiếu bằng `EXCEPT`:

~~~sql
SELECT source_id
FROM batch_input_snapshot
WHERE run_key = :runKey
EXCEPT
SELECT source_id
FROM batch_output
WHERE run_key = :runKey;
~~~

Kết quả mong đợi là **0 dòng** sau khi job hoàn thành thành công. Để kiểm tra output thừa, đổi thứ tự hai vế `EXCEPT`. Nếu nghiệp vụ lọc bỏ record hợp lệ hoặc tạo nhiều output cho một input, phải thay phép đối chiếu này bằng invariant theo nghiệp vụ.

**Chi phí kiểm chứng:** `COUNT(*)` trên bảng rất lớn và phép join với mọi partition có thể gây I/O đáng kể. Ở production, kết hợp kiểm tra ranh giới bằng thuật toán/metadata, kiểm thử trên tập nhỏ, đo mẫu và reconciliation cuối job; không nhất thiết chạy truy vấn đối chiếu toàn bộ sau mọi chunk. Tuy nhiên, trước khi triển khai, cần ít nhất một phép kiểm chứng đầy đủ trên dataset đại diện.

## 7. Chứng minh tính độc lập ở cấp nghiệp vụ

Khóa ID duy nhất không tự làm thuật toán xử lý độc lập. Hãy kiểm tra **đơn vị bất biến nghiệp vụ** trước khi chia.

### Ví dụ A: mỗi order được chuẩn hóa độc lập

~~~text
order 101 -> chuẩn hóa địa chỉ -> ghi order 101
order 102 -> chuẩn hóa địa chỉ -> ghi order 102
~~~

Có thể chia theo `order.id` nếu processor không cập nhật biến tổng toàn cục, writer có khóa duy nhất và mỗi order không cần dữ liệu vừa tính ở order khác.

### Ví dụ B: tính số dư tài khoản theo thứ tự giao dịch

~~~text
account X: giao dịch 1 -> số dư 1 -> giao dịch 2 -> số dư 2
~~~

Không được chia các giao dịch của **cùng tài khoản** sang nhiều worker rồi xử lý tùy thứ tự. Có thể partition theo `account_id` để mỗi tài khoản đi qua một worker, sau đó sắp xếp giao dịch theo khóa thời gian và tie-breaker duy nhất trong worker. Nếu có tài khoản rất lớn, cần thuật toán prefix-sum/merge có chứng minh tính đúng, không chỉ tăng số partition.

### Ví dụ C: tổng doanh thu toàn hệ thống

Tổng có thể được tính thành tổng cục bộ rồi cộng ở bước reduce, miễn là phép toán/định dạng số và quy tắc làm tròn phù hợp:

~~~text
Partition 0 -> partialSum0
Partition 1 -> partialSum1
Partition 2 -> partialSum2
JOIN/Reduce -> finalSum = partialSum0 + partialSum1 + partialSum2
~~~

Nên dùng kiểu số nguyên nhỏ nhất của đơn vị tiền (ví dụ đồng) hoặc decimal phù hợp; thứ tự cộng số thực dấu phẩy động có thể ảnh hưởng kết quả làm tròn. Worker không nên cùng cập nhật một dòng `total_revenue` theo kiểu đọc-sửa-ghi mà không có transaction/atomic update.

### Ví dụ D: API bên ngoài giới hạn 20 request/giây

Phân tích dữ liệu có thể đạt đủ bốn bất biến, nhưng hệ thống đích chỉ nhận tối đa 20 RPS. Tăng 2 lên 10 worker không cải thiện throughput vượt ngưỡng này và dễ gây 429/retry storm. Cần limiter chung, backoff, độ đo throughput và đôi khi một pipeline gửi tuần tự.

## 8. Độ lệch tải và chi phí chia/gộp: kiểm tra liệu chia có đáng không

Một cách chia đúng có thể vẫn không hiệu quả.

Gọi `Tᵢ` là thời gian xử lý của partition `i`. Với đủ worker và không có contention, thời gian của giai đoạn song song xấp xỉ:

~~~text
T_total ≈ T_setup + max(T1, T2, ..., Tn) + T_merge + T_overhead
~~~

Đây là **ước lượng**, không phải công thức bảo đảm: pool thread, DB, mạng, lock, retry và giới hạn concurrency có thể kéo dài thời gian thực tế. Nếu một worker xử lý 80% khối lượng, thêm worker cho phần còn lại thường không làm giảm đáng kể `max(Tᵢ)`.

Ví dụ job đọc 12 triệu bản ghi. Nếu một worker xử lý ở tốc độ 20.000 record/s thì riêng phần xử lý tuần tự mất khoảng 600 giây. Nếu DB có trần thực tế 45.000 record/s cho tổng các worker, 4 worker không thể đạt thời gian lý tưởng 150 giây; riêng giới hạn throughput DB đã đặt cận dưới khoảng `12.000.000 / 45.000 ≈ 267` giây, chưa kể chi phí khác.

### Ước lượng partition skew

| Partition | Record count giả định | Thời gian thực tế |
| --- | ---: | ---: |
| P0 | 6.800.000 | 350 s |
| P1 | 2.400.000 | 160 s |
| P2 | 1.800.000 | 120 s |
| P3 | 1.000.000 | 85 s |

P0 quyết định đường găng khoảng 350 giây, dù phần lớn worker đã rảnh từ lâu. Có thể dùng **quantile boundary** theo key hoặc chia nhỏ P0 nếu dữ liệu và nghiệp vụ cho phép. Nhưng nếu P0 chậm vì record nặng, chia theo `COUNT(*)` vẫn không cân bằng hoàn toàn; cần ước lượng chi phí từng record/group.

### Bộ chỉ số tối thiểu

- Tổng và số bản ghi mỗi partition; số byte và số request ngoại vi nếu liên quan.
- Thời gian mỗi partition, p50/p95 chunk duration, throughput theo worker.
- DB connection wait, lock wait, deadlock, index scan/table scan, network throughput.
- `readCount`, `writeCount`, `commitCount`, `rollbackCount`, lỗi/retry theo `StepExecution`.
- Số partition rỗng, tỷ lệ `max(duration) / median(duration)` (tránh chia cho 0), số worker đồng thời thực.
- Thời gian bước chuẩn bị snapshot và bước merge. Chia dữ liệu có thể nhanh hơn, nhưng chi phí chuẩn bị/gộp quá lớn làm toàn job chậm hơn.

## 9. Restart, retry, transaction và thread safety

### 9.1. Partition là `StepExecution` độc lập

Trong partitioning, manager giao một `ExecutionContext` cho mỗi partition; worker thực thi cùng worker step nhưng có `StepExecution` riêng. Bean `@StepScope` phù hợp để reader nhận biên từ `stepExecutionContext` và giữ cursor/paging state riêng. Điều này **không** làm biến mutable `static` hoặc singleton delegate của processor/writer trở nên thread-safe.

Các chunk có transaction riêng trong worker theo cấu hình Spring Batch và transaction manager. Nếu worker A commit xong, worker B gặp lỗi, transaction đã commit của A không bị rollback cùng B. Writer phải xử lý an toàn khi retry hoặc restart; không giả định exactly-once với side effect ngoài transaction.

### 9.2. Dữ liệu phải giữ nguyên nghĩa khi phục hồi

Giả sử `partition001` đã commit 20.000 record rồi lỗi. Khi restart cùng `JobInstance`, reader có thể khôi phục vị trí dựa vào `ExecutionContext`. Điều này chỉ đúng về nghiệp vụ nếu:

1. Range của `partition001` vẫn biểu thị cùng miền dữ liệu.
2. Snapshot `runKey` không bị thay thế hoặc sửa sau checkpoint.
3. `ORDER BY` dựa trên khóa xác định; các record không bị chèn/xóa làm lệch vị trí checkpoint.
4. Tên reader/key checkpoint còn ổn định và `ItemStream` lifecycle được quản lý.
5. Ghi đích có thể lặp lại an toàn khi transaction rollback hoặc worker gửi lại công việc.

Khi remote partitioning, manager/worker ở các máy khác nhau, lỗi mạng hoặc timeout có thể khiến trạng thái “đã nhận” và “đã hoàn tất” khó quan sát. Không dựa chỉ vào việc message đã gửi một lần; cần metadata bền vững, key partition và thao tác idempotent.

### 9.3. Kiểm tra sức chứa tài nguyên

Với 8 partition, pool 8 thread và cursor reader giữ connection, số JDBC connection thực tế có thể **lớn hơn 8** vì writer transaction, metadata và các nguồn dữ liệu khác. Hãy đo số connection đồng thời và đặt pool/backpressure phù hợp. Các worker cùng đọc range có index chưa chắc làm DB nhanh hơn nếu storage hoặc cache đã bão hòa.

Trong Spring Batch, multi-threaded step có chi tiết thực thi khác nhau giữa các phiên bản; không lấy quy tắc thread safety của một phiên bản áp cho phiên bản khác. Tuy vậy, nếu reader/processor/writer có mutable state bị truy cập bởi nhiều thread, phải chứng minh concurrency safety trong kiến trúc đang chạy.

## 10. Quy trình đánh giá khả năng chia nhỏ trước khi triển khai

### Bước 1 — Chốt phạm vi và ràng buộc nghiệp vụ

Xác định tập dữ liệu `D`, business date, snapshot/watermark, SLA, yêu cầu thứ tự, duplicate policy, giới hạn API/DB và kết quả cần bảo đảm. Viết acceptance criteria cụ thể: không thiếu key nào, không xử lý trùng side effect, restart được, job hoàn tất trong khung giờ.

### Bước 2 — Chọn khóa và lập sơ đồ ranh giới

Đề xuất 1–3 phương án: ID range, tenant, hash hoặc file. Ghi rõ **predicate lọc**, kiểu đầu/cuối exclusive/inclusive, số partition dự kiến, cách lấy boundary, kiểu index và tên partition ổn định.

### Bước 3 — Chứng minh correctness trên tập dữ liệu nhỏ

Dùng tập có ID ở đúng ranh giới, lỗ hổng, khóa trùng đầu vào cần loại, bản ghi cuối cùng, tenant chỉ một record, timestamp đúng 00:00 và dữ liệu rỗng. Kiểm tra mọi bản ghi thuộc đúng một partition và output khớp kỳ vọng.

### Bước 4 — Tạo snapshot/manifest hoặc chiến lược watermark

Không chạy full-scale với tập nguồn thay đổi liên tục mà chưa định nghĩa cách xử lý late arrival và restart. Quy tắc chọn đầu vào cần được gắn với `JobInstance` bằng key ổn định.

### Bước 5 — Đo phân bố và lập kế hoạch tài nguyên

Ước lượng cardinality/chi phí mỗi partition, số connection, số thread, khối lượng write, giới hạn rate và thời gian setup/merge. Nếu một partition áp đảo hoặc phải full scan toàn bảng N lần, thiết kế lại trước khi tăng `gridSize`.

### Bước 6 — Chạy pilot rồi tăng dần concurrency

Chạy 1 worker để có baseline, sau đó 2, 4 và 8 worker nếu có ích. Mỗi lần so sánh **kết quả dữ liệu**, thời gian toàn job, độ lệch partition, lỗi/rollback và DB contention. Dừng tăng nếu throughput bão hòa hoặc thời gian không còn giảm.

### Bước 7 — Cố tình tạo lỗi và restart

Làm một worker lỗi sau vài chunk đã commit; giữ một số partition khác hoàn thành. Restart cùng `JobInstance`, kiểm tra checkpoint, không thiếu bản ghi và không nhân đôi side effect. Làm thử cả khi một worker timeout hoặc bị dừng giữa transaction; với remote worker cần kiểm tra cả giao nhận lại partition.

### Bước 8 — Chốt phương án và giới hạn vận hành

Ghi lại cách chia, số worker tối đa, yêu cầu index, thông số pool, watermark, retry, timeout, dashboard và quy trình can thiệp khi worker bị treo hoặc snapshot không còn hợp lệ. Không đặt phương án chia thành “đúng mãi mãi”: phân bố dữ liệu và chi phí xử lý có thể thay đổi.

## 11. Bảng quyết định: khi nào nên partition?

| Tình huống | Có nên chia? | Giải thích |
| --- | --- | --- |
| Bảng lớn có primary key ổn định, xử lý từng hàng độc lập, writer upsert | **Có khả năng phù hợp** | Dùng range/hash với snapshot, index và reader theo partition |
| Nhiều file JSON/CSV độc lập đã nằm trên object storage | **Có khả năng phù hợp** | Manifest theo file, cân bằng theo kích thước/record và chống file thay đổi |
| Tính số dư giao dịch theo từng tài khoản | **Có điều kiện** | Chia theo account, giữ thứ tự trong account |
| Tính tổng toàn quốc từ doanh số các tỉnh | **Có điều kiện** | Tính partial aggregate mỗi tỉnh, giảm kết quả ở bước merge |
| Một cursor API tuần tự duy nhất, rate limit thấp | **Thường chưa phù hợp để chia ở nguồn** | Cần tối ưu read, staging hoặc thay API trước |
| Writer cập nhật một số dư chung bằng read-modify-write | **Chưa an toàn** | Chuyển thành partial result/atomic update hoặc tái thiết kế phép ghi |
| Nhiều partition cùng quét toàn bảng không dùng index | **Không hiệu quả** | Lựa chọn predicate/index/physical partitioning khác |
| Nguồn thay đổi và job chưa có snapshot/watermark | **Chưa sẵn sàng** | Giải quyết repeatability/restart trước |

## 12. Bài tập tự kiểm tra

Một bảng có khóa `id` và 11 record: `1, 2, 4, 5, 7, 8, 9, 11, 12, 14, 15`. Đề xuất ba partition:

~~~text
P0: [1, 6)      → 1, 2, 4, 5
P1: [6, 11)     → 7, 8, 9
P2: [11, 16)    → 11, 12, 14, 15
~~~

Kiểm tra:

1. Có record nào thiếu hoặc nằm ở hai partition không?
2. `id=6` và `id=10` không tồn tại có làm sai điều kiện bao phủ không?
3. Nếu record `id=13` được chèn vào giữa lúc worker đang chạy, tập dữ liệu đầu vào còn có thể tái lập không?
4. Nếu P2 mất gấp 5 lần thời gian P0 vì payload lớn, cách nào cân bằng tốt hơn việc chỉ chia đều theo ID?
5. Nếu mọi worker cộng vào cùng dòng `daily_total`, liệu dữ liệu đầu vào không chồng lấn có đủ bảo đảm output đúng không?

**Gợi ý đáp án:** (1) Không có thiếu/trùng với 11 record đã cho; (2) không, miễn là tập cần xử lý chỉ gồm record tồn tại; (3) không nếu chưa cố định snapshot/watermark; (4) chia theo ước lượng chi phí/quantile hoặc chia nhỏ nhóm nặng nếu độc lập; (5) không, cần merge có kiểm soát hoặc atomic/transactional update.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): mô hình multi-threaded step, parallel steps và partitioning.
- [Spring Batch 5.2 Reference – Partitioning](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): `Partitioner`, `ExecutionContext` và worker step.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): reader/writer, cách tổ chức input.
- [Spring Batch Reference – Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): metadata job/step, restart và `JobExplorer`.
- [Spring Batch Reference – Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): phụ thuộc giữa các step/flow và quy tắc chuyển tiếp.

## Ghi nhớ

**Kiểm tra khả năng chia nhỏ dữ liệu là kiểm tra tính đúng đắn trước khi tối ưu tốc độ.** Một phương án partition chỉ sẵn sàng khi dữ liệu được bao phủ đủ, các phần không chồng lấn, ranh giới và thứ tự đọc có thể tái lập khi restart, đồng thời phép xử lý và ghi có thể chạy độc lập. Sau đó mới đo độ lệch khối lượng, bottleneck DB/API, thread safety, transaction và overhead để chọn số worker hoặc kiến trúc Spring Batch phù hợp với tài nguyên thực tế.
