# Điều chỉnh fetch size

Khi Spring Batch đọc hàng triệu bản ghi từ database, một cấu hình nhỏ như `fetchSize=50` hay `fetchSize=2000` có thể tác động đáng kể đến **số đợt trao đổi với JDBC driver/database, thời gian đọc, bộ nhớ đang giữ, độ trễ lấy dòng đầu tiên và áp lực lên connection pool**. Nhưng tăng fetch size không đồng nghĩa đọc nhanh hơn trong mọi hoàn cảnh: JDBC chỉ định nghĩa đây là **gợi ý cho driver**; driver, chế độ transaction/cursor, loại query, network và số worker song song quyết định hành vi thực tế. Đặc biệt, với PostgreSQL, đặt `fetchSize` dương nhưng để connection ở auto-commit có thể khiến driver không sử dụng server-side cursor như kỳ vọng.

**Điều chỉnh fetch size** là bài học thuộc chương **Tối ưu cấu hình** của module **SPRING_BATCH_SCALING_OPERATIONS**, chuyên mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và những mô hình xử lý phân tán thích hợp; đo bottleneck, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực. Mục tiêu là chọn `fetchSize` **bằng quan sát có kiểm soát**, thay vì sao chép một con số rồi gọi đó là tối ưu.

> **Thông điệp chính:** `fetchSize` ảnh hưởng đến cách **JDBC ResultSet lấy dữ liệu**; `chunkSize` ảnh hưởng đến **đơn vị transaction/commit**; `pageSize` ảnh hưởng đến **kích thước truy vấn paging**; `gridSize` ảnh hưởng đến **cách chia partition**. Chúng liên quan về tài nguyên nhưng **không thay thế nhau**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của JDBC `Statement.setFetchSize(int)` và các trường hợp driver có thể bỏ qua gợi ý.
2. Phân biệt `fetchSize` với chunk/commit interval, JDBC batch write size, paging pageSize, partition gridSize, executor queue và HTTP/broker prefetch.
3. Cấu hình `JdbcCursorItemReader` bằng Spring Batch 5.x/Java 17+, hiểu vòng đời mở cursor, đọc hàng và đóng resources.
4. Biết vì sao **PostgreSQL cursor mode** cần xác minh transaction/auto-commit và vì sao các driver MySQL, Oracle, SQL Server có hành vi riêng.
5. Giải thích đánh đổi giữa network round-trips, first-row latency, heap/direct memory, DB cursor lifetime và connection occupancy.
6. Tính **ngân sách bộ nhớ cho nhiều readers/partitions** thay vì chỉ ước lượng một cursor.
7. Đo throughput đọc, committed business throughput, p95/p99 read latency và worker/DB pool contention.
8. Benchmark sweep các fetch sizes với input snapshot bất biến, cùng SQL/query plan, chunk, grid, concurrency và output sink.
9. Duy trì đúng **checkpoint, thread safety, skip/retry/restart và idempotent writer** khi tối ưu reader.
10. Phân tích kết quả benchmark để lựa chọn điểm cân bằng theo SLO, tài nguyên và workload thực tế.

**Tình huống xuyên suốt:** Job `customerSettlementImport` đọc 5 triệu records từ PostgreSQL staging; mỗi record khoảng 1 KiB, xử lý biến đổi và ghi vào một bảng output với unique business key. Manager có thể chạy 1 worker hoặc partition thành 8 worker StepExecutions. Một lần chạy dùng `fetchSize=0` (giá trị có semantics phụ thuộc driver), lần khác dùng `100`, `500`, `2000` hoặc `10000`. Mục tiêu không chỉ là số records đọc trên giây, mà là **business output đúng, JobExecution hoàn tất, p99 ổn định và memory không vượt giới hạn**.

## 2. JDBC fetch size hoạt động ở tầng nào?

Theo mô hình JDBC, ứng dụng mở `Connection`, tạo `Statement/PreparedStatement`, thực thi query để nhận `ResultSet` rồi gọi `ResultSet.next()` để duyệt. Driver có thể **đệm** nhiều rows từ server rồi trả cho từng lời gọi `next()`:

~~~mermaid
flowchart LR
    DB[("Database server")] -->|"row blocks / protocol batches"| D["JDBC driver buffer"]
    D -->|"ResultSet.next()"| R["JdbcCursorItemReader"]
    R --> P["ItemProcessor"]
    P --> W["ItemWriter / chunk transaction"]
    W --> O[("Business output DB")]
~~~

`Statement.setFetchSize(F)` cho driver biết một **mục tiêu/gợi ý về số rows lấy mỗi lượt**, nhưng **không yêu cầu mọi driver phải gửi đúng F rows trong mỗi TCP packet**. Một driver có thể đệm toàn bộ result, dùng server cursor, tối ưu theo bytes hoặc bỏ qua gợi ý trong một số mode.

~~~java
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement("""
         SELECT record_id, amount
         FROM staged_settlement
         WHERE batch_key = ?
         ORDER BY record_id
         """)) {

    ps.setString(1, batchKey);
    ps.setFetchSize(500); // JDBC hint, not a commit interval

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("record_id");
            // xử lý mỗi row theo contract ứng dụng
        }
    }
}
~~~

Đoạn trên minh họa **JDBC thuần**, chưa phải một Spring Batch job. Nó không bảo đảm server-side cursor trên tất cả drivers. Với PostgreSQL, `autoCommit` của connection và cursor settings phải phù hợp; chỉ có `setFetchSize(500)` không đủ.

## 3. Phân biệt sáu tham số thường bị nhầm

| Tham số | Đơn vị | Phạm vi tác động | Không bảo đảm |
| --- | --- | --- | --- |
| **`fetchSize`** | Rows/gợi ý | Driver lấy rows từ `ResultSet` | Số rows một commit |
| **`chunkSize`** | Items/chunk | Spring Batch chunk transaction/checkpoint | Driver fetch theo đúng chunk |
| **`pageSize`** | Rows/trang query | Paging reader tạo query/giới hạn page | Driver đệm chính xác pageSize |
| **JDBC batch write** | SQL parameter sets/đợt | Writer gộp `batchUpdate`/round-trips | Chunk size hoặc fetch size |
| **`gridSize`** | Logical partitions | Partition mapping/manager dispatch | Active workers = gridSize |
| **Executor/pool size** | Threads/connections | Mức đồng thời thực và tài nguyên | Worker luôn tiến hành được SQL |

Ví dụ: `fetchSize=500`, `chunkSize=100`, `gridSize=8`, executor tối đa 4 threads. Khi đã mở 4 worker readers, mỗi driver có thể có buffer gần 500 rows, nhưng worker commit theo từng 100 items; 8 partitions **không** bắt buộc chạy đồng thời. Thứ tự commit các worker StepExecutions cũng có thể đảo.

**Một lỗi phổ biến:** tăng `fetchSize` rồi dự đoán số commits giảm. Số commits chủ yếu liên quan `chunkSize` và xử lý skip/retry/transaction policy, không phải fetch hint.

## 4. Tại sao fetch size có thể cải thiện throughput?

Giả sử database lưu 2 triệu rows cho một cursor. Nếu driver **thực sự dùng fetch size làm số rows mỗi fetch group**, số nhóm lý tưởng:

\[
K(F)=\left\lceil\frac{N}{F}\right\rceil
\]

Với `N=2.000.000`:

| Fetch size F | Số fetch groups lý tưởng | Nhận xét |
| ---: | ---: | --- |
| 50 | 40.000 | Nhiều lần lấy dữ liệu nhỏ |
| 100 | 20.000 | Giảm một nửa số nhóm so F=50 |
| 500 | 4.000 | Có thể che network RTT tốt hơn |
| 2.000 | 1.000 | Giảm thêm overhead |
| 10.000 | 200 | Lợi ích giảm dần, buffer lớn |

Nếu mỗi round-trip có overhead độc lập 2 ms (giả định thuần lý tưởng) thì `40.000 × 2ms = 80s` cho F=50, còn `1.000 × 2ms = 2s` cho F=2000. **Không được hiểu đây là elapsed thực tế hoặc bảo đảm 78s speedup**: protocol pipelining, cursor mode, bandwidth, serialization, CPU, row mapping, DB query plan, transmission bytes và transaction scheduling đều ảnh hưởng. Một driver fetch toàn bộ rows ngay từ đầu thì `K(F)` không mô tả network behavior.

**Bài học:** fetch size nhỏ có thể lãng phí round-trips khi network RTT đáng kể; fetch size lớn hơn có thể amortize fixed overhead, nhưng không thể vượt giới hạn CPU, bandwidth, disk hay business writer.

## 5. Tại sao fetch size lớn lại có chi phí?

- **Driver/client memory:** nhiều rows/column values cùng được đệm, cộng overhead Java objects/bytes và khả năng copy.
- **Time-to-first-row:** nếu driver đợi đủ block lớn hoặc truy vấn/sort tốn thời gian, row đầu có thể xuất hiện trễ hơn; cách hoạt động cụ thể phụ thuộc driver.
- **Network burst:** mỗi lần fetch có thể truyền nhiều bytes, gây spikes hoặc backpressure.
- **Long-running cursor/transaction:** reader cursor sống lâu giữ connection, snapshot và server resources, bất kể fetch block size.
- **GC:** nhiều objects tạo/giữ trong heap; tail GC pause có thể tăng.
- **Partition multiplication:** F lớn × nhiều active readers làm tổng memory/connection pressure tăng.
- **Workload skew:** một số rows 2 KiB, một số 2 MiB; chỉ đếm rows không đủ dự báo memory.

**Không kết luận “fetchSize=10000 thì JVM giữ đúng 10.000 records”**. Nó là hint; driver có thể sử dụng internal buffers, conversion copies hoặc server cursor với behavior khác. Muốn biết thực sự phải đo heap, allocation, resultset traffic và driver fetch events.

## 6. Ước lượng sơ bộ ngân sách bộ nhớ

Một ước lượng thô:

\[
M_{\text{driver-buffers}} \approx
W_{\text{active-readers}} \times F \times B_{\text{row}}
\]

Với 8 readers đồng thời, F=2.000, kích thước dữ liệu serialized trung bình 1 KiB:

\[
8 \times 2.000 \times 1\text{ KiB} \approx 15{,}6\text{ MiB}
\]

Đây **không phải tổng heap cần thiết**: cộng Java object/driver overhead, column decoding, item buffering, `ItemProcessor` objects, writer chunk buffer, JDBC write batch, metadata, GC headroom và các connection/network buffers. Nếu rows có JSON/blob kích thước lớn, giới hạn memory theo `row bytes p95/p99` thay vì mean.

**Khi gridSize tăng nhưng worker threads giữ nguyên**, số active readers có thể không tăng; khi tăng cả pool hoặc remote nodes, tổng memory across workers tăng. Chỉ benchmark F cùng lúc với worker count trong pha đa biến đã lên kế hoạch, không gán toàn bộ chênh lệch cho fetch size.

## 7. Đọc cursor khác đọc paging

Spring Batch cung cấp các kiểu database reader thường gặp:

| Reader | Cách đọc | Vai trò fetchSize | Liên hệ với restart |
| --- | --- | --- | --- |
| `JdbcCursorItemReader` | Một `ResultSet` được duyệt tuần tự qua cursor | Hint cho JDBC statement khi lấy rows | Lưu vị trí/read count theo `ExecutionContext` |
| `JdbcPagingItemReader` | Nhiều SQL queries theo trang, có sort key | Có thể chỉ ảnh hưởng việc driver lấy rows **trong từng page**, tùy version/driver | Restart cần stable sort key và source snapshot |
| `JpaPagingItemReader` | ORM query theo pages | Khác JDBC direct fetch hint; phụ thuộc JPA provider | Paging/EntityManager lifecycle riêng |
| File reader | Đọc stream/file | **Không có JDBC fetchSize** | File position/resource identity |
| Remote API reader | Gọi HTTP/SDK | API page/batch size riêng | Token/cursor/ETag, không phải JDBC `Statement` |

**Quan trọng:** nếu sử dụng `JdbcPagingItemReader` với `pageSize=200`, một `fetchSize=2000` (nếu reader/builder/version cho cấu hình) **không làm một SQL page query trả 2.000 rows**. Page query vẫn do paging provider/SQL quyết định; fetch hint có thể ít hoặc không có tác dụng khi mỗi page đã nhỏ.

## 8. Cursor: read()/next() liên tục, commit theo chunk

~~~text
Open reader / execute SELECT
    ├─ driver fetch một nhóm rows
    ├─ reader.read() trả item 1
    ├─ reader.read() trả item 2
    ├─ ...
    ├─ chunk(200) -> writer / transaction commit
    ├─ reader đọc tiếp từ ResultSet còn mở
    └─ cursor close khi step hoàn tất/được cleanup
~~~

Trong Spring Batch `JdbcCursorItemReader`, reader thông thường giữ cursor trong lifecycle của StepExecution; vòng đời cursor connection có thể **khác** transaction connection dùng để commit từng chunk. Không mặc định mỗi chunk commit sẽ đóng cursor, cũng không mặc định chunk transaction đang active đủ làm PostgreSQL cursor hoạt động ở server mode.

**Khi tách cursor connection và business transaction**, phải tính connection occupancy và nguồn consistency. Khi dùng `useSharedExtendedConnection`/`ExtendedConnectionDataSourceProxy`, semantics giữ cursor qua commit, holdability và driver behavior phải được kiểm tra kỹ; không bật flag chỉ để tăng throughput.

## 9. PostgreSQL: fetch size phụ thuộc cursor mode

Với **PostgreSQL JDBC driver (pgjdbc)**, driver có thể dùng server-side cursor/portal để fetch từng nhóm rows **khi thỏa các điều kiện phù hợp**. Các điểm cần kiểm:

1. `Statement/PreparedStatement.setFetchSize(F)` với **F dương**.
2. Connection đang **không ở auto-commit mode** cho cơ chế cursor fetch phù hợp (cùng với transaction lifecycle hợp lệ).
3. Statement/resultset type/holdability, query shape và driver behavior đáp ứng điều kiện; cấu hình đặc biệt có thể làm driver chọn materialize toàn bộ.
4. Transaction vẫn được quản lý/đóng đúng, không giữ transaction/snapshot lâu vô ý.
5. Benchmark xác nhận **driver đang fetch nhiều nhóm** bằng evidence (driver logs/test instrumentation, network behavior và heap), chứ không chỉ xem `getFetchSize()` trả giá trị mong muốn.

**Cạm bẫy:** ứng dụng gọi `setFetchSize(500)` nhưng connection vẫn `autoCommit=true`; driver có thể lấy toàn bộ kết quả vì không dùng server cursor như kỳ vọng. Thay fetchSize từ 500 lên 2000 trong tình huống này có thể **không tạo khác biệt đáng kể**.

**Không khuyên đặt global Hikari `autoCommit=false` một cách mù quáng**: điều đó thay đổi transaction semantics cho những consumers khác. Trước tiên kiểm connection mà **reader thực sự mở**, cách Spring Batch quản lý cursor/step transaction, driver version và kiến trúc datasource/transaction; chọn chiến lược phù hợp và test commit/rollback/restart.

## 10. MySQL, Oracle, SQL Server: không áp một quy tắc chung

| Hệ/driver | Điều cần hiểu khi tuning | Kiểm tra thực tế |
| --- | --- | --- |
| **PostgreSQL pgjdbc** | Positive fetch size + điều kiện cursor/transaction | Có server cursor? autoCommit connection lúc reader mở? |
| **MySQL Connector/J** | Có các chế độ streaming/cursor fetching khác nhau; với cursor fetching thường cần cấu hình như `useCursorFetch`, server prepared statements và fetch size dương theo driver version | Cấu hình effective URL/driver, heap và network; không mặc định auto-streaming |
| **Oracle JDBC** | Row prefetch/fetch-size behavior phụ thuộc driver, column types, query/resultset và defaults | Driver tracing, per-query latency, memory |
| **Microsoft SQL Server JDBC** | Adaptive buffering/response buffering và fetch size semantics riêng | Client buffer/driver settings, server and client metrics |
| **JPA/Hibernate** | EntityManager/persistence context/ORM fetch strategy tham gia | Không nhầm JDBC fetch size với association fetch/join batching |

**MySQL đặc biệt:** một số driver/version có kỹ thuật streaming cũ dùng fetchSize đặc biệt như `Integer.MIN_VALUE`, khác cursor-based fetching. **Không copy mẹo này sang PostgreSQL, Oracle, Spring Batch builder hoặc production mà không đọc đúng driver behavior.** Nó có thể giữ connection/resultset occupied và gây ràng buộc khi thực thi thêm statements.

**Không dùng sự thành công trên H2 để kết luận fetchSize=500 tối ưu cho PostgreSQL.** H2 là lựa chọn cho unit correctness; benchmark I/O/cursor phải dùng DB/driver sát production, chẳng hạn PostgreSQL Testcontainers cho integration và môi trường staging có network/IO thực tế cho performance.

## 11. Spring Batch 5.x: cấu hình JdbcCursorItemReader

Ví dụ một reader lấy `fetchSize` từ cấu hình ứng dụng và range từ `ExecutionContext` của **worker StepExecution**:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record StagedPayment(
        String batchKey, long recordId, BigDecimal amount) {}

@Bean
@StepScope
JdbcCursorItemReader<StagedPayment> stagedPaymentReader(
        DataSource dataSource,
        @Value("${app.batch.reader.fetch-size:500}") int fetchSize,
        @Value("#{stepExecutionContext['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['sourceVersion']}") String sourceVersion,
        @Value("#{stepExecutionContext['startInclusive']}") Long start,
        @Value("#{stepExecutionContext['endExclusive']}") Long end) {

    if (fetchSize <= 0) {
        throw new IllegalArgumentException(
                "For this benchmark choose a positive fetch size");
    }

    return new JdbcCursorItemReaderBuilder<StagedPayment>()
            .name("stagedPaymentReader")
            .dataSource(dataSource)
            .sql("""
                SELECT batch_key, record_id, amount
                FROM staged_settlement
                WHERE batch_key = ?
                  AND source_version = ?
                  AND record_id >= ?
                  AND record_id < ?
                ORDER BY record_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, batchKey);
                ps.setString(2, sourceVersion);
                ps.setLong(3, start);
                ps.setLong(4, end);
            })
            .rowMapper((rs, rowNum) -> new StagedPayment(
                    rs.getString("batch_key"),
                    rs.getLong("record_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(fetchSize)
            .saveState(true)
            .build();
}
~~~

**Ý nghĩa:**

- `.fetchSize(fetchSize)` truyền fetch hint tới JDBC cursor reader; nó **không đổi số items/chunk**.
- `.name(...)` quan trọng khi lưu ItemStream state; với nhiều reader instances cùng ExecutionContext, tên phải tránh trùng không mong muốn.
- `@StepScope` cho worker reader riêng khi chạy partitioning; không dùng một singleton cursor reader mutable trên nhiều worker threads.
- `batchKey/sourceVersion` xác định snapshot cần đọc; `startInclusive/endExclusive` là hai cận **nửa mở**. Partitioner phải đưa cả bốn giá trị vào worker ExecutionContext.
- `ORDER BY record_id` chỉ đáng tin cho checkpoint nếu record_id unique trong phạm vi `(batch_key,source_version)`, nguồn bất biến, và reader/driver hỗ trợ restart đúng.

**Mã cần ghép với application thực:** bảng `staged_settlement` (mục 23), `Partitioner`, `DataSource`, imports, domain transform, transaction manager và JobRepository là phần còn lại của project. Đây là ví dụ Spring Batch 5.x, không khẳng định mọi legacy builder/version có cùng chữ ký phương thức.

## 12. Đặt fetchSize trong cấu hình, không hardcode khi sweep

~~~yaml
app:
  batch:
    reader:
      fetch-size: 500
      chunk-size: 200

# Những thuộc tính dưới đây là application-defined,
# không phải tên property Spring Batch tự nhận ở mọi phiên bản.
~~~

Chọn một dải thử rõ ràng:

~~~text
fetchSize ∈ {50, 100, 500, 2000, 5000, 10000}
chunkSize = 200, cố định ở pha benchmark fetch.
gridSize  = 4, cố định ở pha đầu.
executor  = 4 active workers, cố định ở pha đầu.
~~~

Trong thí nghiệm **cô lập fetch size**, thay một biến `fetchSize` nhưng giữ SQL, index, dataset, network RTT, JDBC driver, reader implementation, step retry policy và pool sizing giống nhau. Nếu đổi cả `chunkSize` từ 200 lên 2000, hiệu quả của giảm commit overhead sẽ bị nhầm là do fetch size.

**Không nhất thiết thử mọi giá trị trên production**; dải này là điểm bắt đầu cho benchmark nhỏ/staging. Có thể dùng tìm kiếm thưa rồi tinh chỉnh quanh vùng đạt SLO để giảm chi phí thử nghiệm.

## 13. Một worker Step có chunkSize độc lập

~~~java
@Bean
Step importWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<StagedPayment> stagedPaymentReader,
        ItemProcessor<StagedPayment, NormalizedPayment> processor,
        ItemWriter<NormalizedPayment> writer,
        @Value("${app.batch.reader.chunk-size:200}") int chunkSize) {

    return new StepBuilder("importWorkerStep", jobRepository)
            .<StagedPayment, NormalizedPayment>chunk(
                    chunkSize, transactionManager)
            .reader(stagedPaymentReader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Với `fetchSize=500` và `chunkSize=200`, driver **có thể** fetch trước vài trăm rows và worker commit mỗi 200 items. Với `fetchSize=50`, một chunk 200 items **có thể** trải qua nhiều fetch groups. Đây chỉ là hình dung nếu driver thực sự dùng fetch-size buffering; không được suy số network trips chính xác từ tỉ lệ `chunkSize/fetchSize`.

**Transaction boundary:** `ItemWriter.write` được gọi trong chunk transaction nhưng lời gọi trả về chưa nhất thiết có DB commit; đếm business effects phải dựa vào transaction outcome/ledger/reconciliation. Reader cursor connection có thể độc lập khỏi chunk transaction và tiếp tục giữ result set khi một chunk rollback.

## 14. JdbcPagingItemReader: phân biệt pageSize và fetchSize

Một paging reader thường tạo nhiều SQL queries với `LIMIT`/keyset semantics theo `PagingQueryProvider`. Hai knobs:

- `pageSize`: số rows mà **mỗi trang truy vấn** yêu cầu theo provider.
- `fetchSize`: nếu API/driver hỗ trợ, hint cho cách JDBC fetch rows **bên trong kết quả trang đó**.

~~~text
JdbcPagingItemReader(pageSize=250)
   Query page 1: max ~250 rows
   Query page 2: max ~250 rows
   Query page 3: max ~250 rows

fetchSize=2000 không biến page 1 thành 2000 rows.
~~~

Đây là mẫu cấu hình Spring Batch 5.x theo query provider:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<StagedPayment> pagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        @Value("${app.batch.paging.page-size:250}") int pageSize) {

    return new JdbcPagingItemReaderBuilder<StagedPayment>()
            .name("stagedPaymentPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .pageSize(pageSize)
            .rowMapper((rs, rowNum) -> new StagedPayment(
                    rs.getString("batch_key"),
                    rs.getLong("record_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**Chưa đầy đủ:** `PagingQueryProvider` phải được cấu hình `SELECT/FROM/WHERE` và **unique sort key**, cộng các query parameters cho `batchKey`/range/snapshot. Không lấy example thiếu provider rồi dùng như production reader. `JdbcPagingItemReader` không nên được coi là “cursor reader nhưng fetch size bằng page size”.

**Khi benchmark paging:** nên ưu tiên sweep `pageSize` trong một pha riêng, đo SQL query count/plan và memory; chỉ thử driver fetch size nếu API/version/provider có đường cấu hình thực và instrumentation chứng minh nó có ảnh hưởng.

## 15. Quan hệ fetch size – page size – chunk size qua ví dụ

| Cấu hình | Tác động đáng kể | Rủi ro |
| --- | --- | --- |
| Cursor F=50, chunk=200 | Nhiều fetch groups nhỏ nếu driver streaming | Round-trips/latency |
| Cursor F=500, chunk=200 | Có thể đệm dữ liệu của nhiều chunks | Memory/connection cursor |
| Cursor F=5000, chunk=200 | Ít fetch groups hơn nếu supported | Memory/GC, time-to-first |
| Paging page=100, chunk=200 | Một chunk có thể đọc qua nhiều pages | SQL query overhead |
| Paging page=1000, chunk=200 | Một page có thể nuôi vài chunks | Buffer/page memory |
| Paging page=1000, fetch=50 | Driver có thể fetch nhiều nhóm trong mỗi page | Tùy provider/driver |

**Sai lầm cần tránh:** cố đặt cả ba bằng `1000` chỉ để “đồng bộ kích thước”. Mỗi con số phục vụ một **tầng khác nhau**; giá trị phù hợp có thể khác hoàn toàn nếu data row sizes/RTT/DB CPU/transaction cost khác nhau.

## 16. Partitions nhân số active cursors

Spring Batch local partitioning:

~~~mermaid
flowchart TD
    M["Manager / Partitioner: gridSize 8"] --> E["TaskExecutor: 4 threads"]
    E --> P0["Worker P0: cursor F=2000"]
    E --> P1["Worker P1: cursor F=2000"]
    E --> P2["Worker P2: cursor F=2000"]
    E --> P3["Worker P3: cursor F=2000"]
    P0 --> DB[("Shared PostgreSQL")]
    P1 --> DB
    P2 --> DB
    P3 --> DB
    DB --> CP["Connection pool + DB server resources"]
~~~

Với `gridSize=8`, executor tối đa 4, **tối đa khoảng bốn StepExecutions active ở một thời điểm** trong mô hình local này; các partitions còn lại có thể chờ. Nếu tăng executor lên 8, tổng driver buffering và số server cursors/connections cũng có thể tăng.

**Benchmark fetch size một cách công bằng:** giữ active workers không đổi trong pha đầu. Chỉ sau khi tìm dải F phù hợp với một worker mới kiểm `F × workers`, vì giới hạn tốt nhất với W=1 có thể tạo memory/DB pressure khi W=16.

## 17. Cấu hình executor và grid chỉ minh họa

~~~java
@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("fetch-bench-");
    executor.initialize();
    return executor;
}

@Bean
TaskExecutorPartitionHandler partitionHandler(
        @Qualifier("importWorkerStep") Step workerStep,
        @Qualifier("partitionExecutor") TaskExecutor executor) {
    TaskExecutorPartitionHandler handler =
            new TaskExecutorPartitionHandler();
    handler.setStep(workerStep);
    handler.setTaskExecutor(executor);
    handler.setGridSize(8);
    return handler;
}
~~~

**Lưu ý:** `gridSize` là hint số partitions gửi tới `Partitioner`, không tự tăng max threads. Nếu mỗi worker giữ một cursor connection, có thể thiếu connection khi DB pool quá nhỏ; nếu writer/JobRepository sử dụng datasource riêng, phải tính **tất cả các pools**. Không có một công thức `Hikari.maximumPoolSize=gridSize` đúng mọi dự án.

## 18. Server cursor giữ tài nguyên tới khi nào?

Đọc kiểu cursor thường có lifecycle dài:

~~~text
StepExecution start
    → reader.open()
    → connection / statement / resultset được mở
    → reader.read() lặp trong nhiều chunk transactions
    → worker kết thúc hoặc lỗi
    → reader.close() / cleanup
~~~

Hệ quả vận hành có thể gồm:

- Connection bị giữ lâu hơn thời gian một chunk commit.
- Server cursor/portal/transaction snapshot có lifetime liên quan tới reader và driver.
- Một query `ORDER BY` lớn có thể cần sort và tạm dùng disk, bất kể fetchSize.
- Nếu worker bị pause do CPU/DB writer, reader cursor vẫn có thể chiếm connection mà không fetch gì.
- Khi manager chạy nhiều partitions, các worker readers có thể giữ nhiều connections đồng thời.

**Đừng điều chỉnh fetchSize để “giải phóng connection sớm”**: fetchSize chỉ tác động fetching; kết thúc connection/cursor sớm phải thay reader lifecycle/architecture (paging, sharding, ngắn transaction, pre-materialized snapshot) nếu cần.

## 19. Đọc dữ liệu lớn: SELECT columns/row mapping cũng rất quan trọng

Một SELECT kiểu:

~~~sql
SELECT * FROM huge_payment_staging
WHERE batch_key = :batchKey;
~~~

có thể mang theo **JSON/BLOB/TEXT rất lớn** dù processor chỉ cần ID và amount. Fetch size 500 trên rows 50 KiB đệm dữ liệu khác hẳn 500 rows 300 B.

**Nên:**

1. Chỉ `SELECT` columns thực sự cần cho business transformation.
2. Dùng indexed predicate theo `batchKey`, range và stable sort key.
3. Nếu LOBs lớn, cân nhắc fetch tách hoặc API streaming phù hợp, đo row size và JDBC driver handling.
4. Profile `RowMapper`: parsing JSON/BigDecimal/date conversion có thể chiếm CPU dù network không nghẽn.
5. Đo kích thước row p50/p95/p99, tránh giả định mọi row bằng kích thước trung bình.
6. Với phân vùng sparse/skewed, đo actual rows/partition, không chỉ range width.

**Fetch size không sửa được SQL query plan tệ.** Nếu database đang full-scan/sort hàng triệu rows vì thiếu index đúng, thay F từ 200 sang 2000 không chữa nguyên nhân.

## 20. Snapshot consistency khi cursor chạy lâu

Một reader chỉ có thể restart/chạy song song đáng tin khi source identity ổn định. Những vấn đề thường gặp:

- Input rows bị insert/update/delete khi worker đang đọc.
- Trong READ COMMITTED, hai queries/pages có thể nhìn những trạng thái khác nhau nếu source mutable.
- Cursor và paging có snapshot semantics khác nhau tùy DB isolation, transaction và reader lifecycle.
- Tăng F không biến một nguồn đang thay đổi thành immutable snapshot.
- Retry sau rollback có thể xử lý lại cùng row; writer phải idempotent.

**Ví dụ:** recordId 101 bị xóa và một recordId 102 mới thêm trong lúc paging. Nếu reader dùng offset-based pagination mà không có stable snapshot, dữ liệu có thể bị dịch vị trí và tạo **skip/duplicate**. Đây không phải lỗi do fetchSize, nhưng benchmark fetch trên nguồn mutable sẽ không thể so sánh công bằng.

**Phương án:** snapshot staging table/file/object manifest bất biến kèm version, stable sort key, partition bounds cố định và business reconciliation. Với PostgreSQL có thể lựa chọn transaction/snapshot thích hợp nhưng phải cân nhắc long-lived snapshots/connection pressure; đừng tăng transaction lifetime vô hạn chỉ để dễ benchmark.

## 21. Restart/checkpoint không phụ thuộc một giá trị fetchSize

`JdbcCursorItemReader` là `ItemStream` có thể lưu read position/state trong `ExecutionContext` khi `saveState(true)`. **FetchSize không phải offset checkpoint**; nó chỉ gợi ý số rows lấy trong một lần. Nếu worker commit 1.000 logical items, rồi crash khi driver đã prefetch 2.000 rows, việc driver có thể đã đệm thêm rows **không có nghĩa 2.000 rows đã được business commit**.

~~~text
Cursor fetch buffer có thể đã đưa rows 1..2000 vào client.
Worker xử lý/chunk commit rows 1..1000.
Worker JVM chết ở row 1050.

Restart phải dựa committed checkpoint/source snapshot,
không dựa vào "bao nhiêu rows JDBC đã fetch về RAM".
~~~

**Điểm cần kiểm:**

1. StepExecution metadata/chunk checkpoint update theo semantics của JobRepository/transaction manager.
2. Cursor reader position được phục hồi đúng khi `open(ExecutionContext)` ở JobExecution mới.
3. Một số rows có thể được **process lại** khi checkpoint và business DB commit không hoàn toàn atomic; writer phải replay-safe.
4. Với nhiều partitions, mỗi worker `StepExecution` có state riêng; không chia một mutable cursor reader.
5. Input snapshot/version, range bounds, sort key phải **giữ nguyên** giữa failure và restart.
6. Không đổi partitioning strategy/gridSize trên cùng JobInstance chỉ vì benchmark fetch size mới nhanh hơn.

**Không khẳng định `saveState(true)` tự tạo exactly-once business effects.** Nó chỉ tham gia checkpoint/restart framework; độc lập với idempotency của sink và distributed delivery.

## 22. FetchSize khác transaction/rollback blast radius

Giả sử `chunkSize=200`, `fetchSize=2000`. Một chunk thất bại ở item thứ 180 có thể rollback theo fault-tolerant step policy; nó **không mặc định rollback cả 2000 rows driver đã đọc trước**. Ngược lại, khi `chunkSize=2000` và `fetchSize=200`, một chunk có thể chứa work từ nhiều nhóm fetch nhưng transaction lớn hơn.

| Thay đổi | Tác động trực tiếp chính | Rủi ro |
| --- | --- | --- |
| Tăng `fetchSize` | Driver cursor/network buffering | Heap, first-row latency, server cursor behavior |
| Tăng `chunkSize` | Số items/transaction commit | Lock duration, rollback/retry blast radius |
| Tăng `pageSize` | Rows/page query và paging state | Paging buffer/query cost |
| Tăng `gridSize` | Số logical partitions | Metadata/skew/coordination |
| Tăng worker pool | Số requests/cursors concurrent | DB connection, CPU, GC, locks |

**Đừng dùng `fetchSize` làm cách sửa lỗi transaction timeout** khi gốc vấn đề là writer lock contention. Nếu fetch hoạt động rất nhanh nhưng commit chậm, DB writer chứ không phải fetch hint có thể là bottleneck.

## 23. SQL fixture cho benchmark có thể tái hiện

~~~sql
CREATE TABLE staged_settlement (
    batch_key     VARCHAR(120) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    record_id     BIGINT NOT NULL,
    tenant_id     VARCHAR(100) NOT NULL,
    amount        NUMERIC(18,2) NOT NULL,
    payload_hash  VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, source_version, record_id)
);

CREATE TABLE settlement_output (
    benchmark_run VARCHAR(120) NOT NULL,
    batch_key     VARCHAR(120) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    record_id     BIGINT NOT NULL,
    net_amount    NUMERIC(18,2) NOT NULL,
    payload_hash  VARCHAR(128) NOT NULL,
    PRIMARY KEY (benchmark_run, batch_key, source_version, record_id)
);

-- PRIMARY KEY của source đã tạo index B-tree bao gồm
-- (batch_key, source_version, record_id); kiểm execution plan
-- trước khi thêm index khác.
~~~

**Tại sao output có `benchmark_run`?** Mỗi run benchmark chạy trên cùng source snapshot nhưng ghi **một output namespace riêng**, tránh lần chạy sau chỉ làm duplicate no-op khiến throughput có vẻ nhanh hơn. Trong production, business key/idempotency key nên dựa trên **logical effect** và source/version, không phải random benchmark run; `benchmark_run` chỉ là isolation của môi trường test.

### SQL reader phải xác định source version

~~~sql
SELECT batch_key, record_id, amount
FROM staged_settlement
WHERE batch_key = :batchKey
  AND source_version = :sourceVersion
  AND record_id >= :startInclusive
  AND record_id < :endExclusive
ORDER BY record_id;
~~~

`JdbcCursorItemReader` ở mục 11 đã truyền cả `sourceVersion` từ worker ExecutionContext; partitioner phải gắn snapshot version bất biến từ JobParameters/manifest vào từng worker. Không được lọc mỗi `batchKey` rồi hy vọng mọi dòng thuộc đúng source snapshot.

## 24. Idempotent writer trước khi benchmark

Ví dụ một phép biến đổi thuần `netAmount=amount * 0.95` được làm tròn theo quy tắc ứng dụng; writer PostgreSQL có thể dùng conflict handling:

~~~sql
INSERT INTO settlement_output
    (benchmark_run, batch_key, source_version,
     record_id, net_amount, payload_hash)
VALUES
    (:run, :batchKey, :sourceVersion,
     :recordId, :netAmount, :payloadHash)
ON CONFLICT (benchmark_run, batch_key, source_version, record_id)
DO NOTHING;
~~~

**Đây chỉ là một phần của idempotency.** Nếu có output key trùng nhưng `netAmount` hoặc `payloadHash` khác, `DO NOTHING` có thể che lỗi; production và benchmark correctness gate phải **so sánh giá trị hiện hữu với expected**, hoặc dùng transactional business operation ledger/conditional UPSERT có conflict detection. Trong giao dịch cập nhật số dư, chỉ đơn thuần `DO NOTHING` vào một bảng phụ cũng không đủ trừ khi cùng transaction bảo vệ business effect.

**Quan trọng cho benchmark:** `readCount` và `writeCount` không phải luôn là **new committed logical rows**; một writer có thể skip/no-op/conflict. Chỉ đánh giá configuration speedup từ những runs có **input-output equality** theo contract.

## 25. Thiết kế benchmark fetchSize có kiểm soát

| Yếu tố | Cố định ở pha đầu | Vì sao |
| --- | --- | --- |
| Source | Snapshot 5 triệu rows, cùng key/value/checksum | Không đổi workload |
| SQL | Cùng WHERE/ORDER BY và query plan | Không nhầm index optimization |
| JDBC driver | Cùng version/cursor settings | Behavior fetch hint không đổi |
| Reader | `JdbcCursorItemReader` | Không trộn paging/cursor |
| Chunk | `chunkSize=200` | Số commit/rollback blast radius ổn định |
| Partitions | `gridSize=4`, ranges cố định | Partition scheduling ổn định |
| Workers | 4 active threads | Số active cursors ổn định |
| DB pool | Cùng limit và pool configuration | So cùng contention |
| Network | Cùng RTT/bandwidth/topology | Round-trip cost tương đương |
| Writer | Cùng business SQL và target layout | Output timing so sánh được |
| Error policy | Cùng retry/skip/fail | Không nhầm retry amplification |
| Candidate F | 50, 100, 500, 2000, 5000, 10000 | Biến độc lập |

**Thứ tự thực hiện:** preflight → warm-up có ghi nhận → một cấu hình F → đối soát → lưu metrics/run report → cleanup/isolate output → cấu hình khác. Lặp lại nhiều lần, **đảo/randomize thứ tự các giá trị F** để tránh cold cache bias; chọn số lần lặp theo variability.

Không nhất thiết phải reset OS page cache nếu benchmark phản ánh production warm cache; nhưng cần dùng **cùng một chính sách cache** cho mọi cấu hình và báo nó minh bạch. Tắt dịch vụ khác hoặc ghi nhận background load, tránh so một run ban đêm với một run giờ cao điểm.

## 26. Đo đúng những mốc thời gian

~~~text
Job start
  Reader open + execute SELECT
    First ResultSet.next / first item ready
      Subsequent read() durations (fetch groups có thể nằm ở đây)
        ItemProcessor
          ItemWriter SQL + transaction commit
            StepExecution complete
              Reconciliation/publication complete
~~~

Tối thiểu nên đo:

- `reader.open.duration` và **time-to-first-item**: fetch buffer lớn/sort/query startup có làm chậm dòng đầu?
- `reader.read.duration` (histogram sample hoặc aggregate): thời gian `read()` bao gồm những lúc driver chờ nhóm tiếp theo.
- `worker.chunk.duration`: end-to-end chunk time, phân biệt reader/processor/writer.
- `db.connection.acquire.duration` và `db.query/commit.duration`: có nghẽn DB pool/lock không?
- `job.makespan`: toàn job/validation/publication theo SLA.
- `business.committed.records_per_sec` và p95/p99 latencies: không chỉ `readCount/s`.
- `heap.used/alloc_rate/gc.pause`, RSS, direct/native memory nếu driver có buffers ngoài heap.
- `active.readers`, `open.connections`, `executor.queued`, broker queue age nếu remote.

**Không cộng p99 reader + p99 writer rồi gọi là p99 end-to-end:** các observations ở percentile tail có thể thuộc những chunks khác nhau. Dùng instrumentation cùng request/chunk identity và histograms theo định nghĩa.

## 27. Cách đo thời gian read() mà không ghi log mỗi record

Với job hàng triệu rows, log/timer per item với high-cardinality tags có thể làm benchmark bị chi phối bởi observability. Một adapter thu **aggregates** (minh họa, không ghi business state):

~~~java
final class TimedItemReader<T> implements ItemStreamReader<T> {
    private final ItemStreamReader<T> delegate;
    private final LongAdder totalReadNanos = new LongAdder();
    private final LongAdder successfulReads = new LongAdder();
    private final LongAdder readCalls = new LongAdder();

    TimedItemReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        long started = System.nanoTime();
        try {
            T item = delegate.read();
            readCalls.increment();
            if (item != null) {
                successfulReads.increment();
            }
            return item;
        } finally {
            totalReadNanos.add(System.nanoTime() - started);
        }
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }

    long totalReadNanos() { return totalReadNanos.sum(); }
    long successfulReads() { return successfulReads.sum(); }
    long readCalls() { return readCalls.sum(); }
}
~~~

Đoạn minh họa dùng `ItemStreamReader` và `ExecutionContext` của Spring Batch; cần imports/exception signatures đúng version. **Không đồng nghĩa `totalReadNanos()` là network time:** nó bao gồm `RowMapper`, driver decode và mọi thứ trong `delegate.read()`. `LongAdder` aggregates làm giảm contention khi nhiều threads ghi cùng counter nhưng **reader delegate vẫn không tự thread-safe**; wrapper phải ở đúng StepScope/per worker, không dùng một cursor singleton chia sẻ giữa threads.

**Hạn chế:** các aggregate counters trên **không tự reset giữa benchmark runs** nếu reuse bean instance; tạo reader/wrapper mới cho mỗi run và lấy snapshot cuối step. Cần đo riêng first-row/open duration và timeouts; không dùng `System.nanoTime()` của một JVM so với timestamp monotonic JVM khác.

## 28. PostgreSQL: xác minh chế độ fetch thực

Một protocol kiểm:

1. Trong **integration environment**, dùng pgjdbc version/config đúng production và source query đại diện.
2. Quan sát connection autoCommit/transaction state **đúng thời điểm reader.open()`, tránh suy từ transaction manager khác hoặc config global.
3. Cài `fetchSize=100`, chạy query vài nghìn rows; đo heap/time-to-first/read durations.
4. Cài `fetchSize=2000` trên cùng source và conditions; so server/client evidence về số nhóm fetch và memory.
5. Nếu hai giá trị không khác gì, kiểm liệu driver có **thực sự dùng cursor mode**, hay fetch hint bị ignore/result bị materialize ngay.
6. Khi thử cấu hình autoCommit/extended cursor, bảo đảm không làm thay đổi business commit/checkpoint semantics; chạy rollback/restart tests.

**Không cần và không nên bật mọi loại trace log mức DEBUG cho toàn bộ 5 triệu rows trong benchmark timing chính.** Dùng một diagnostic run nhỏ để xác minh protocol, tắt verbose logs trong performance runs vì chính log I/O có thể làm sai latency.

## 29. Testcontainers kiểm driver behavior, nhưng chưa thay load test

Một integration test có thể dùng PostgreSQL Testcontainers và Spring Batch reader với **source fixture vài nghìn rows**:

~~~java
@Test
void positiveFetchSizesReadSameOrderedKeys() throws Exception {
    List<Long> expected = LongStream.range(0, 10_000)
            .boxed().toList();

    List<Long> small = executeReaderWithFetchSize(50);
    List<Long> large = executeReaderWithFetchSize(2000);

    assertEquals(expected, small);
    assertEquals(expected, large);
    assertEquals(new HashSet<>(expected).size(),
                 new HashSet<>(small).size());
}
~~~

`executeReaderWithFetchSize` là **fixture helper phải tự triển khai** với database seed, reader open/read/close và connection setup. Test này chứng minh **correctness theo keys** cho hai fetch sizes, không chứng minh driver đã fetch theo blocks hay cấu hình nào nhanh hơn. Hãy test `autoCommit`/cursor conditions và protocol evidence riêng, đồng thời chạy performance ngoài CI thông thường khi có tài nguyên sát production.

### Test lỗi nguồn và reader exception

- Query timeout khi cursor đang đọc.
- DB connection drop giữa ResultSet.
- Process bị kill sau vài chunks commit.
- Reader throw exception ở một row bất thường (mapping/decimal/null).
- Driver/server restart làm cursor không còn hợp lệ.
- Job restart cùng JobInstance/snapshot với writer idempotent.

**Không dùng `skip(Exception.class)` để làm benchmark “xanh”**. Skip/fail/retry phải theo hợp đồng nghiệp vụ; nếu test chấp nhận skip, có quarantine và data-quality gate.

## 30. SQL đối soát sau mọi run

Giả sử source transformation `netAmount=ROUND(amount*0.95,2)` và một input hợp lệ sinh đúng một output:

~~~sql
-- Thiếu kết quả cho source snapshot:
SELECT s.record_id
FROM staged_settlement s
LEFT JOIN settlement_output o
  ON o.batch_key = s.batch_key
 AND o.source_version = s.source_version
 AND o.record_id = s.record_id
 AND o.benchmark_run = :benchmarkRun
WHERE s.batch_key = :batchKey
  AND s.source_version = :sourceVersion
  AND o.record_id IS NULL;

-- Output không thuộc source snapshot:
SELECT o.record_id
FROM settlement_output o
LEFT JOIN staged_settlement s
  ON s.batch_key = o.batch_key
 AND s.source_version = o.source_version
 AND s.record_id = o.record_id
WHERE o.benchmark_run = :benchmarkRun
  AND o.batch_key = :batchKey
  AND o.source_version = :sourceVersion
  AND s.record_id IS NULL;

-- Giá trị sai hoặc content hash sai:
SELECT s.record_id, s.amount, o.net_amount
FROM staged_settlement s
JOIN settlement_output o
  ON o.batch_key = s.batch_key
 AND o.source_version = s.source_version
 AND o.record_id = s.record_id
WHERE o.benchmark_run = :benchmarkRun
  AND s.batch_key = :batchKey
  AND s.source_version = :sourceVersion
  AND (
       o.net_amount <> ROUND(s.amount * 0.95, 2)
       OR o.payload_hash <> s.payload_hash
  );
~~~

**Kỳ vọng:** cả ba queries trả 0 rows khi mọi input đều phải xuất output và `payload_hash` có semantics thống nhất. Với filter/skip/one-to-many output, thay bằng đối soát theo **expected outcome classes** và cardinality thực; không dùng kiểm `COUNT(*)` đơn lẻ. Chỉ run có JobExecution/StepExecution outcomes hợp lệ **và** reconciliation PASS mới được đưa vào bảng benchmark quyết định cấu hình.

## 31. Bảng kết quả benchmark giả định

**Số liệu dưới đây chỉ minh họa cách đọc kết quả**, không phải phép đo đã thực hiện hoặc cấu hình mặc định được khuyến nghị. Giả sử cùng 5 triệu records, four active readers, chunk=200, server cursor mode **đã được xác minh**, source/target state giống nhau và mọi run đều qua correctness gate:

| Fetch size F | Median job elapsed | Business throughput | Time-to-first-item p95 | Peak JVM heap | Nhận xét |
| ---: | ---: | ---: | ---: | ---: | --- |
| 50 | 1.000 s | 5.000 records/s | 60 ms | 0,9 GiB | Nhiều fetch groups |
| 100 | 750 s | ~6.667 records/s | 75 ms | 1,0 GiB | Giảm network overhead |
| 500 | 550 s | ~9.091 records/s | 95 ms | 1,1 GiB | Điểm cải thiện đáng kể |
| 2.000 | 520 s | ~9.615 records/s | 140 ms | 1,5 GiB | Throughput bắt đầu bão hòa |
| 5.000 | 525 s | ~9.524 records/s | 230 ms | 1,9 GiB | Thêm memory, ít lợi ích |
| 10.000 | 565 s | ~8.850 records/s | 450 ms | 2,4 GiB | GC/memory pressure giả định |

**Diễn giải:** F=500 hoặc F=2000 có thể là những ứng viên tốt hơn F=10000 trong ví dụ vì throughput tương đương nhưng first-row latency và memory thấp hơn. F=2000 có thể nhanh hơn F=500 khoảng 5,5% trong số liệu giả định; cần lặp lại để xem chênh lệch có **lớn hơn run-to-run variability** hay không.

**Không lấy bảng làm “định mức cấu hình chuẩn Spring Batch”.** Các driver, network, JDBC connection modes, row sizes, CPU pressure, sort cost và DB server constraints khác nhau sẽ tạo đường cong khác.

## 32. Không chỉ chọn F có records/s cao nhất

Một cấu hình hợp lệ cần qua nhiều điều kiện:

~~~text
Correctness:
  Job/Step outcomes đúng
  Input→output reconciliation PASS
  Retry/restart không duplicate logical effects

Performance:
  Job deadline đạt
  Committed throughput đạt
  Time-to-first-result / p99 read/chunk latency trong SLO

Resources:
  Heap/GC có headroom
  DB connections và cursor pressure trong budget
  Không gây starving cho workload khác
~~~

**Pareto frontier:** một cấu hình không bị cấu hình khác **vừa nhanh hơn vừa ít latency/memory/resource cost hơn**, theo những tiêu chí có ý nghĩa. Nếu F=2000 nhanh hơn F=500 chỉ vài phần trăm nhưng làm heap tăng 40%, F=500 có thể là lựa chọn an toàn hơn khi production có thêm concurrency.

**Quan trọng:** chọn F cho cả **steady-state** và **worst-case rows**, không chỉ average size; một vài rows chứa blobs lớn có thể đẩy memory p99 vượt ngân sách.

## 33. Khi fetch size tăng mà không thấy speedup

| Quan sát | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| F=100 và F=2000 có heap/throughput gần hệt | Driver ignore hint / không dùng server cursor | AutoCommit/cursor config, driver protocol evidence |
| First-row rất chậm ở cả hai F | SQL scan/sort/index kém | `EXPLAIN`, query duration, disk I/O |
| Reader nhanh nhưng job vẫn chậm | Processor/DB writer là bottleneck | Per-stage durations, commit latency |
| Tăng F làm heap/GC tăng nhiều | Driver buffered rows/larger payload | Allocation/heap profile, row size |
| Tăng F làm DB pool pending tăng | Nhiều cursor connections sống lâu, pool nhỏ | Active/pending/acquisition time, reader lifecycle |
| Thay F kéo dài StepExecution mà DB CPU thấp | Locks/idle waits/executor queue/slow consumer | Worker spans, thread states, pool metrics |
| Paging reader đổi F không khác | Page size/query already bounded | SQL/page query count, provider behavior |
| Remote workers không cải thiện | Network/broker/remote DB bị nghẽn | Queue age, worker CPU, DB locality |
| p99 tăng nhưng mean ổn | Memory bursts, GC, large rows hoặc slow fetch group | Per-item/step latency histogram |
| Repeated runs thay đổi mạnh | Cache/network/CPU interference | Randomize runs, record load, enough samples |

**Trình tự chẩn đoán:** trước tiên chứng minh fetch hint **có tác dụng**, sau đó tìm bottleneck mới; nếu writer chiếm 90% job wall time, giảm reader time 50% chỉ có tác động nhỏ đến job elapsed. Đừng tiếp tục tăng F như một phản xạ khi DB locks đã chi phối.

## 34. Query plan và index có thể quan trọng hơn F

Với PostgreSQL, kiểm query plan trên **test/staging snapshot**:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT record_id, amount
FROM staged_settlement
WHERE batch_key = 'bench-2026-11'
  AND source_version = 'v3'
  AND record_id >= 100000
  AND record_id < 200000
ORDER BY record_id;
~~~

`EXPLAIN ANALYZE` **thực thi query**; với bảng lớn nó tốn tài nguyên, nên không chạy tùy tiện trên DB production trong giờ cao điểm. Tìm index range scan/heap fetch, sort/disk spill, row estimates và buffer hits/reads. Nếu query phải sort nhiều rows hoặc đọc toàn bảng, giảm network fetch groups chưa chắc giải quyết elapsed.

**Phân biệt:** cost trong server và cost từ server tới client. `EXPLAIN ANALYZE` chủ yếu mô tả server execution plan; nó **không đo đầy đủ thời gian truyền/mapping toàn bộ ResultSet qua JVM**, nên vẫn cần end-to-end reader instrumentation.

### Đọc các cột không cần thiết cũng là “fetch” thừa

`SELECT *` có thể chuyển JSON/LOB fields mà business step không dùng. Chọn projection phù hợp, index theo filter/sort, sử dụng `RowMapper` hiệu quả; sau đó mới tuning F. Đổi projection/index là **một experiment riêng**, tránh vừa sửa SQL vừa đổi F.

## 35. Kết hợp fetch size với concurrency sau pha cô lập

Sau khi chọn F candidates khi workers=1 hoặc W=4 cố định, hãy lập bảng:

| FetchSize | Active workers | Tổng buffer thô nếu 1 KiB/row | Câu hỏi |
| ---: | ---: | ---: | --- |
| 500 | 1 | ~0,49 MiB | Single-reader baseline |
| 2000 | 1 | ~1,95 MiB | Có giảm fetch overhead? |
| 500 | 8 | ~3,9 MiB | 8 cursors có cạnh tranh pool/DB không? |
| 2000 | 8 | ~15,6 MiB | Heap/GC còn headroom không? |
| 5000 | 16 | ~78,1 MiB | Row size p99 làm memory biến động ra sao? |

**Số liệu là phép nhân minh họa**, không phản ánh Java object overhead/driver buffering thực. Đừng suy luận gắn F với số records nằm trên heap bằng tỷ lệ cố định. Khi thay cả W và F, hãy thiết kế experiment đa biến rõ để phân tích **interaction**, không gọi kết quả đơn thuần là “tác động fetchSize”.

Ở remote partitioning, **tổng memory là across worker JVMs**, còn shared DB/server connection pressure cộng dồn. Manager có thể hầu như không giữ ResultSet nếu workers trực tiếp đọc source; không tính toàn bộ buffer vào heap của manager.

## 36. Lỗi có thể xuất hiện khi fetchSize lớn

| Kịch bản | Cách thử an toàn | Điều phải xác minh |
| --- | --- | --- |
| F cực lớn + wide rows | Test fixture vài % blobs/JSON lớn | Heap/GC bounded, không OOM bất ngờ |
| Cursor query timeout | Inject deadline nhỏ ở staging | Job FAILED/retry theo policy, không fake COMMITTED |
| Network drop giữa fetch groups | Proxy/network fault test | Exception, cleanup, restart đúng |
| DB restart giữa ResultSet | Kill test DB container | Reader fails, partial commits được đối soát |
| Worker JVM kill giữa chunk | Kill child process có handshake | Replay-safe business effects |
| Worker kill sau DB commit trước checkpoint | Failure hook có commit evidence | Idempotent writer và recovery policy |
| Một partition có row size gấp 50× | Skewed dataset | Active reader memory/tail metrics |
| Source version thay trong restart | Alter test staging snapshot | Detect mismatch, không đọc sai checkpoint |
| DB connection pool cạn | Giảm pool có chủ đích | Bounded timeout/alert, không treo |
| Multiple partition readers dùng singleton | Intentionally bad test config | Detect race/cursor corruption |
| Driver fetch hint ignored | AutoCommit/driver mode thay ở test | Diagnostic chỉ rõ không có streaming |
| Row mapper throw ở một item | Inject conversion error | Skip/quarantine/fail theo policy, không mất rows |
| Paging provider sort key không unique | Duplicate sort values | Test skip/duplicate sau restart |

**Không coi test `throw new RuntimeException()` trong processor là thay thế cho worker JVM crash**. Khi process chết, cursor, broker ACK và StepExecution metadata có thể ở trạng thái khác. Mỗi test cần xác định **mốc lỗi và resource nào đã commit**.

## 37. Khi nào cần đổi kiến trúc thay vì tiếp tục tăng F?

Một vài dấu hiệu:

1. DB server query plan hoặc source I/O là nút thắt, không phải network round-trips.
2. Business writer/transaction commits chiếm phần lớn job elapsed.
3. Cursor giữ connection hàng giờ khiến pool starve.
4. Một worker đọc tuần tự cả file/bảng rất lớn, CPU khác idle.
5. Source mutable làm checkpoint/paging không đáng tin.
6. Remote workers gây excessive shared DB scans hoặc data locality kém.

**Lựa chọn phù hợp có thể là:**

- Index/query optimization, chỉ chọn columns cần thiết.
- Range partitioning với `@StepScope` readers và source snapshot ổn định.
- `JdbcPagingItemReader` với unique sort key nếu cursor connection lifetime là vấn đề.
- Pre-materialized immutable files, object storage manifests hoặc bulk ingestion khi cần data locality/throughput.
- Writer JDBC batching, giảm lock hot spots, stage-per-worker rồi hợp nhất dữ liệu.
- Connection-pool/DB resource tuning theo metrics, không theo `gridSize` cứng.

**Không chuyển sang paging chỉ vì “cursor chậm”**: paging tạo nhiều SQL queries, có thể chậm hơn/khó nhất quán nếu nguồn mutable. Benchmark lại end-to-end và fault/restart semantics cho kiến trúc mới.

## 38. Runbook: điều chỉnh fetch size nhưng job vẫn chậm

1. **Xác nhận symptom:** job makespan, reader time, first-row latency, p95/p99, heap hoặc DB connection waits đang xấu?
2. **Xác nhận dữ liệu:** source snapshot/version, row size distribution, query filters, output reconciliation của run có đúng?
3. **Kiểm actual configuration:** reader nào (`Cursor` hay `Paging`), fetchSize thực, driver version, statement/connection settings?
4. **Nếu PostgreSQL:** cursor/transaction/autoCommit có đủ điều kiện để fetch theo groups? Có evidence chứ không chỉ property?
5. **Kiểm SQL plan:** index range scan, ORDER BY, sort spill, LOB columns và database I/O.
6. **Đo pipeline:** reader open/next, processor CPU, writer DB commits, JobRepository metadata và publication.
7. **Kiểm concurrency:** active workers/cursors, executor queue, gridSize, Hikari active/pending, DB server connections.
8. **Kiểm memory/GC:** driver buffers, allocation, large rows và RSS.
9. **Đo network:** RTT, throughput bytes, broker/backpressure nếu remote; fetch group count khi có instrumentation.
10. **Thử F theo sweep có kiểm soát:** giữ chunk/grid/workers/input/SQL, lặp runs và đảo thứ tự.
11. **Chọn theo SLO/correctness:** business output đầy đủ, p99 và memory trong ngân sách, recovery test PASS.
12. **Ghi quyết định:** F được chọn, bằng chứng, điều kiện rollback và ngưỡng rebenchmark.

### Tình huống A — fetchSize khác nhau nhưng elapsed y hệt

~~~text
F=100:   900 s, heap 1.2 GiB
F=5000:  895 s, heap 1.2 GiB
PostgreSQL reader connection autoCommit=true;
client vẫn buffer result tương tự qua hai thử nghiệm.

=> Cần kiểm cursor mode/driver behavior.
   Không kết luận fetchSize=5000 mặc định là tối ưu.
~~~

### Tình huống B — throughput đọc tăng nhưng job vẫn như cũ

~~~text
Read throughput: 30k → 60k rows/s
Writer committed throughput: ~12k records/s
DB lock wait p99: high
Job elapsed: không giảm đáng kể

=> Writer/DB là bottleneck. Không tiếp tục tăng F.
   Tối ưu SQL/locking/chunk/connection budget ở pha riêng.
~~~

### Tình huống C — job nhanh hơn nhưng production OOM

~~~text
Test: F=10000, W=1, median rows 600 B, heap OK.
Prod: F=10000, W=16, row size p99 250 KiB.
Heap/GC/driver buffer pressure tăng đột biến.

=> Benchmark phải xét F × active readers × row size tail.
   Giảm F/W, hạn chế wide columns, thêm memory headroom.
~~~

**Không chỉnh toàn cục JDBC auto-commit, query transaction isolation, datasource pool hay StepExecution metadata trong production khi chưa có thiết kế/test recovery**. Điều chỉnh fetch size là thay đổi vận hành có khả năng tác động connection behavior và performance; nhưng không nên phá semantics commit chỉ để có kết quả nhanh trong benchmark.

## 39. FetchSize trong remote partitioning và remote chunking

Khi chuyển từ local sang distributed processing, **reader nằm ở đâu** quyết định nơi phải cấu hình và đo `fetchSize`:

| Kiến trúc | Thông thường reader ở đâu? | Nơi fetchSize có tác động | Cần kiểm thêm |
| --- | --- | --- | --- |
| Local partitioning | Mỗi worker StepExecution trong JVM manager | Mỗi local worker reader | Executor pool, shared DB connections |
| Remote partitioning | Mỗi worker JVM theo ExecutionContext partition | **Worker JVMs**, không phải chỉ manager | Aggregate DB connections across pods, source locality |
| Remote chunking | Manager thường sở hữu ItemReader, gửi chunks | **Manager reader** | Manager read rate, chunk dispatch/backpressure, broker |
| Multi-threaded step | Reader/StepExecution trong một JVM với nhiều chunks | Reader `ResultSet` nếu dùng JDBC | Shared-reader thread safety, checkpoint |
| Parallel steps | Tùy step sở hữu reader | Từng reader bean | Flow join, shared datasource capacity |

**Remote partitioning:** đặt fetchSize chỉ trong manager application.properties có thể **không thay đổi gì** nếu worker service có config riêng và chính worker mở JDBC ResultSet. Cần kiểm effective config tại worker pods, driver/autocommit ở worker và pod memory.

**Remote chunking:** tăng fetchSize có thể làm manager reader đọc nhanh hơn nhưng worker DB writer vẫn là bottleneck; nếu dispatch không bounded, broker backlog/record-to-visible latency tăng dù readCount/s đẹp. Fetch hint không phải message chunk size hay broker prefetch.

**Multi-threaded step:** dù fetchSize có tối ưu, một `JdbcCursorItemReader` singleton stateful thường không được chia sẻ tùy tiện cho nhiều threads. Tách reader-per-partition hoặc bảo vệ state theo thiết kế; đồng bộ đọc bằng một lock có thể hạn chế scaling và thay đổi checkpoint/restart behavior.

## 40. Biểu mẫu báo cáo benchmark có thể kiểm toán

Mỗi run cần ghi cấu hình effective và kết quả với **nguồn dữ liệu đã được xác nhận**, không điền con số mặc định rồi suy đoán:

~~~yaml
# Báo cáo minh họa, KHÔNG phải Spring Boot configuration.
runId: fetch-benchmark-F500-run3
experiment: cursor-fetch-size-fixed-workload
application:
  java: "17"
  springBatch: "5.x"
  jdbcDriver: "pgjdbc version from actual runtime"
  readerType: JdbcCursorItemReader
  workerRole: local-partition-worker
input:
  batchKey: synthetic-settlement-2026-11
  sourceVersion: immutable-v3
  expectedRecords: 5000000
  sourceManifestHash: "record-actual-checksum-here"
configuration:
  fetchSize: 500
  chunkSize: 200
  gridSize: 4
  maxActiveWorkers: 4
  jdbcAutoCommitAtReaderOpen: "actual observed value"
  serverCursorVerified: "true/false, with evidence"
  dbPoolLimit: "observed configuration"
results:
  jobBatchStatus: COMPLETED
  sourceRowsCovered: "actual observation"
  committedLogicalRecords: "actual observation"
  wallTimeSeconds: "actual observation"
  timeToFirstItemP95Millis: "actual observation"
  peakHeapMiB: "actual observation"
  dbConnectionPendingMax: "actual observation"
  reconciliation: "PASS/FAIL"
  restartTest: "PASS/FAIL/NOT_RUN"
~~~

**Đây là schema báo cáo tự định nghĩa**, không phải định dạng mà Spring Batch tự tạo. Khi lưu report, thêm source query/schema/index version, driver URL flags, CPU/memory limits, database topology, GC settings, network RTT, time window, raw repeated observations và mục tiêu SLO.

### Khi so hai run

Nếu cả `fetchSize` lẫn `autoCommit` khác nhau, báo cáo phải đánh dấu **two-variable change**; không được kết luận hiệu quả do riêng F. Nếu nguồn snapshot/version khác nhau hoặc input/output reconciliation FAIL, **không dùng run đó để chọn cấu hình**.

## 41. Anti-patterns khi điều chỉnh fetch size

| Sai lầm | Hậu quả | Thay bằng |
| --- | --- | --- |
| Coi `fetchSize` là số items/transaction | Kỳ vọng số commits sai | Phân biệt `chunkSize` và `fetchSize` |
| Coi `fetchSize` là kích thước SQL paging | Kỳ vọng page query trả nhiều rows hơn | Tuning `pageSize` riêng |
| Coi JDBC fetch là network packet count cố định | Ước lượng sai round-trips/bytes | Kiểm driver/protocol behavior |
| Tăng F tới 100.000 mà không đo heap | GC/OOM, tail latency tăng | Sweep và kiểm row-size distribution |
| Bỏ qua PostgreSQL autoCommit/cursor conditions | Driver có thể materialize result | Verify effective reader connection |
| Đặt global autoCommit=false để tối ưu ngay | Đổi transaction semantics toàn ứng dụng | Thử có kiểm soát/correctness tests |
| Copy MySQL `Integer.MIN_VALUE` sang driver khác | Nonportable/wrong streaming mode | Driver-specific documentation/config test |
| Tính memory theo F mà quên worker concurrency | Production heap cao hơn staging | Budget theo active readers và row bytes |
| Benchmark H2 rồi áp lên PostgreSQL | Query plan/driver behavior khác | Production-like DB/driver |
| Đo `readCount/s` và gọi committed throughput | Bỏ qua retry/rollback/dedup | Business output reconciliation |
| Thay F, chunk, grid, SQL cùng lúc | Không tìm được nguyên nhân | Controlled one-factor experiments |
| Chạy lại vào target đã populated | Duplicate no-op làm throughput giả | Isolate output per run |
| Dùng mutable staging để test restart | Checkpoint bị dịch/skip/duplicate | Immutable snapshot + stable sort key |
| Dùng một cursor reader giữa nhiều threads | Race, corrupt cursor/ExecutionContext | `@StepScope` worker reader |
| Nghĩ prefetch lớn = connection trả sớm | Cursor vẫn mở tới reader close | Đo lifecycle/kiến trúc reader |
| Chỉ đo trung bình, bỏ p99 | Tail GC/large rows bị che | p50/p95/p99, heap and queue age |
| Bật verbose SQL logging trong timing run | Log I/O làm sai benchmark | Diagnostic run riêng |
| Không kiểm StepExecution/restart | Có thể duplicate effects sau crash | Idempotent writer + fault tests |
| Chọn F chỉ theo một run tốt nhất | Noise/cache bias | Repeat, rotate order, variation |
| Dùng F lớn để bù query plan tệ | Không xử lý DB scan/sort bottleneck | Index/query tuning trước |

## 42. Bài thực hành cuối bài

**Bối cảnh:** dựng Java 17+/Spring Batch 5.x với PostgreSQL staging **bất biến**. Có nguồn 100.000 rows cho integration profile và 5 triệu rows cho performance profile. Bảng output có unique business key và writer replay-safe. Một job local partitioning có `TaskExecutorPartitionHandler`, reader `JdbcCursorItemReader` `@StepScope` và `chunkSize=200`.

**Phần A — chuẩn bị correctness**

1. Tạo staging source có `batchKey/sourceVersion/recordId`, một phần records có payload lớn và phân bố sparse/skewed.
2. Kiểm partition ranges nửa mở, không overlap/gap, query sort key unique, ItemStream reader state được lưu đúng.
3. Với F=50 và F=2000, assert danh sách output keys/values giống hệt expected, không chỉ counts.
4. Kill một worker giữa step, restart cùng JobInstance với snapshot và partition mapping không đổi; verify replay-safe output.

**Phần B — xác minh driver fetch**

5. Dùng PostgreSQL Testcontainers/driver giống production và mở diagnostic trace ngắn; xác định autoCommit/cursor mode tại reader.
6. So F=50/500/2000 trên query vài nghìn rows, quan sát read durations, first-row time và heap.
7. Thử test config làm driver không dùng cursor mode; giải thích vì sao F đổi nhưng behavior khác hoặc không đổi.
8. Không dùng diagnostic verbose logging khi đo throughput chính.

**Phần C — performance sweep**

9. Giữ SQL/index/driver, chunk=200, grid=4, executor=4, DB pool và network cố định.
10. Chạy F=50/100/500/2000/5000/10000, mỗi lần isolated output và source snapshot giống nhau.
11. Đảo thứ tự/repeat runs; ghi read elapsed, first-row, job wall, committed records/s, GC/heap và DB pending.
12. Đối soát output sau **mỗi run**; loại run sai correctness khỏi lựa chọn cấu hình.
13. Chọn hai F candidates; so tiếp khi active workers=1/4/8 để phát hiện interaction với memory/DB pool.
14. Chạy thêm wide-row outlier, DB disconnect, worker crash và partial chunk rollback.

**Phần D — quyết định**

15. Trình bày đường cong throughput vs F cùng p99/time-to-first/memory và variability.
16. Xác định vì sao F lớn hơn không còn giúp: driver ignore hint, network bão hòa hay writer bottleneck?
17. Đề xuất F có **SLO, memory headroom và recovery correctness** đạt; ghi version/config và điều kiện rollback.

**Tiêu chí đạt:** có bằng chứng driver thực sự áp dụng hay bỏ qua fetch hint, benchmark công bằng, dữ liệu không thiếu/trùng, restart an toàn và quyết định tuning có căn cứ. Không chấp nhận kết luận “F=5000 tốt nhất” chỉ từ số `readCount/s` của một lần chạy.

## 43. Checklist trước production

- [ ] Xác nhận reader là `JdbcCursorItemReader`, `JdbcPagingItemReader` hay một implementation khác.
- [ ] Phân biệt `fetchSize`, `chunkSize`, `pageSize`, writer JDBC batch, `gridSize` và executor concurrency.
- [ ] Driver version và database loại nào đã được ghi rõ; behavior fetch hint được xác minh.
- [ ] Với PostgreSQL, kiểm cursor/transaction/autoCommit **trên reader connection** thay vì chỉ nhìn YAML.
- [ ] Không đổi global connection autoCommit/transaction semantics mà thiếu regression tests.
- [ ] Reader SQL chọn columns cần thiết, có query plan/index ổn, unique sort key và stable snapshot.
- [ ] Partitioned readers dùng `@StepScope`/state riêng; không chia mutable cursor không thread-safe.
- [ ] Snapshot version/range được lưu ổn định trong StepExecution/ExecutionContext cho restart.
- [ ] Fetch size được lấy từ cấu hình rõ, có range validation và ghi vào benchmark report.
- [ ] Đã đo cả time-to-first-row, reader throughput, job elapsed và committed logical records/s.
- [ ] Đã đo heap/GC và row size distribution, bao gồm wide-row outliers.
- [ ] Memory budget tính theo F × active readers × bytes/row, cộng driver/JVM overhead.
- [ ] Đã đo open cursor/connections, Hikari active/pending, timeout, DB server locks/CPU.
- [ ] Cấu hình benchmark giữ cùng source/SQL/driver/chunk/grid/workers/network ở pha cô lập.
- [ ] Đã kiểm paging pageSize riêng nếu sử dụng `JdbcPagingItemReader`.
- [ ] Mỗi run có identifying JobParameters/output namespace riêng, không lặp lại một JobInstance COMPLETED.
- [ ] Nhiều run được lặp, đảo thứ tự, báo median/variation và raw samples.
- [ ] SQL key/value/source-version reconciliation PASS cho mọi run được chọn.
- [ ] Writer idempotent; duplicate key khác payload được detect, không âm thầm `DO NOTHING`.
- [ ] Retry/skip/fail và chunk commit outcome giữ đúng khi reader/cursor gặp lỗi.
- [ ] Đã test DB disconnect, network failure, JVM crash, restart và source snapshot mismatch.
- [ ] Remote partitioning đã kiểm fetchSize hiệu lực tại worker JVMs; remote chunking tại manager reader.
- [ ] Không nhầm broker ACK/request dispatch với business commit và output publication.
- [ ] Metrics/logs không tạo cardinality khổng lồ theo record IDs hoặc request IDs.
- [ ] Có SLO throughput, p95/p99 latency, memory headroom, connection budget và runbook rollback.
- [ ] Có lịch rebenchmark khi driver/DB/index/schema/query, row-size distribution hoặc worker concurrency thay đổi.

**Ghi nhớ:** **điều chỉnh fetch size** là tối ưu **JDBC result fetching**, không phải cách trực tiếp thay transaction size hay số worker. Chọn giá trị hiệu quả đòi hỏi biết **driver có thực sự streaming/cursor-fetch hay không**, đo chi phí network và memory trên workload thật, hiểu ảnh hưởng nhân với số readers đồng thời, giữ snapshot/checkpoint ổn định và đối soát business output sau retry/restart. FetchSize tốt nhất là giá trị **đạt throughput và latency SLO trong ngân sách bộ nhớ/connection, có headroom và kiểm chứng correctness**, chứ không nhất thiết là lớn nhất.
