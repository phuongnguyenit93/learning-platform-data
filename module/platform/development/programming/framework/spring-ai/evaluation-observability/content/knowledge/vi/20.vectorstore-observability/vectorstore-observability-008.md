# Đối chiếu metric phía ứng dụng với số liệu cơ sở dữ liệu

> **Chương:** Quan sát VectorStore  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt số liệu ở ranh giới ứng dụng, Spring AI VectorStore, connection pool, database client và database server.
2. Hiểu vì sao số lần gọi VectorStore không nhất thiết bằng số câu SQL, số transaction hay số truy vấn được database ghi nhận.
3. Đối chiếu latency, throughput, lỗi, hàng đợi kết nối, cache hit/read và trạng thái backend trong cùng một khoảng thời gian.
4. Dùng số liệu PostgreSQL và pgvector theo hướng chỉ đọc để kiểm tra query workload, index usage, wait events và execution plan.
5. Kết hợp Micrometer, Spring Boot Actuator, HikariCP, Spring AI Observation và database statistics để khoanh vùng nguyên nhân.
6. Thiết kế Java wrapper, PromQL, runbook và thí nghiệm có kiểm soát để giải thích chênh lệch giữa metrics ứng dụng với database.

## 1. Vì sao cần đối chiếu hai phía?

Một API RAG có thể ghi nhận lời gọi VectorStore mất 420 ms. Dashboard PostgreSQL lại cho thấy thời gian thực thi truy vấn trung bình chỉ 70 ms. Hai con số không nhất thiết mâu thuẫn: timer ứng dụng và số liệu database đang đo những phạm vi khác nhau.

Thời gian ở ứng dụng có thể bao gồm:

- Chờ lấy connection từ pool.
- Tạo query embedding nếu adapter tự gọi EmbeddingModel.
- Chuyển đổi SearchRequest thành câu lệnh hoặc request backend.
- Chờ network đến database/proxy.
- Thực thi một hoặc nhiều câu lệnh.
- Chuyển đổi rows thành Document và metadata.
- Đóng result set, trả connection và thực hiện xử lý adapter.

Số liệu database có thể chỉ ghi thời gian server thực thi câu lệnh sau khi request đã tới database. Một số thống kê khác là bộ đếm tích lũy, số lần gọi, block cache hit/read hoặc wait event; chúng không phải latency đầu cuối.

**Mục tiêu đối chiếu là giải thích khoảng thời gian và số lượng ở từng tầng**, không ép tất cả bộ đếm phải bằng nhau.

### 1.1. Các tầng quan sát

~~~mermaid
flowchart TD
  A["HTTP / RAG request"] --> B["Application service"]
  B --> C["Spring AI VectorStore"]
  C --> D["Embedding / adapter processing"]
  C --> E["JDBC / database client"]
  E --> F["Connection pool"]
  F --> G["Network / proxy"]
  G --> H["Database server"]
  H --> I["SQL execution / index / buffer / I/O"]
  I --> G
  G --> F
  F --> E
  E --> C
  C --> B
  B --> J["Response / evaluation"]
  B -.-> M["Application metrics + traces"]
  C -.-> M
  F -.-> M
  H -.-> N["Database statistics + logs"]
  I -.-> N
  M --> O["Time-aligned comparison"]
  N --> O
~~~

Một request RAG có thể thực hiện thêm query rewrite, embedding, rerank hoặc ChatModel call. Vì thế application request duration không thể so trực tiếp với riêng SQL execution time.

### 1.2. Bốn con số khác nhau thường bị nhầm

| Số liệu | Đo ở đâu | Trả lời câu hỏi |
|---|---|---|
| Application request duration | HTTP/service | Người dùng chờ bao lâu? |
| VectorStore operation duration | Ranh giới method/observation Spring AI | Lời gọi VectorStore mất bao lâu trong process? |
| Database client/connection duration | JDBC/client/pool | Lấy connection, gửi lệnh và nhận kết quả mất bao lâu? |
| Database statement execution time | Database server statistics | Server ghi nhận thời gian thực thi SQL bao lâu? |

Không trừ hai percentile để suy ra một thành phần chính xác. Ví dụ p95 của application timer trừ p95 SQL không phải p95 connection-pool wait: hai phân phối có thể đến từ các tập request khác nhau và percentile không tuyến tính.

## 2. Định nghĩa scope trước khi so sánh

Trước khi mở dashboard, cần viết rõ metric đang đo cái gì, đơn vị nào, có bao gồm retry không và mẫu số là gì.

### 2.1. Bản đồ metric

| Tầng | Ví dụ tín hiệu | Đơn vị / semantics |
|---|---|---|
| API | Request count, request duration, HTTP status | Một logical request từ người dùng |
| RAG service | Retrieval workflow duration, selected document count | Một lượt retrieval trong pipeline |
| Spring AI | Observation db.vector.client.operation | Một operation được instrument ở tầng VectorStore |
| Embedding provider | Embedding call count, latency, usage | Một lần gọi provider hoặc batch |
| JDBC/client | Client span, query duration, rows | Một lần gọi driver/database client |
| HikariCP | Active, idle, pending, acquire time, timeout | Trạng thái pool và chờ lấy connection |
| Database | Statement calls, total/mean execution time | Thống kê SQL theo nhóm query |
| Database storage | Buffer hit/read, temp I/O, index scans | Hoạt động lưu trữ/tối ưu của server |

Một operation VectorStore có thể thực hiện một SQL statement hoặc nhiều statement tùy adapter, transaction, metadata lookup, batch write hay cơ chế backend. Với query, một statement có thể trả nhiều rows; số rows không bằng số lần gọi.

### 2.2. Các câu hỏi cần trả lời trước khi so

1. Cửa sổ thời gian có cùng timezone và cùng ranh giới không?
2. Metrics database là counter tích lũy từ lúc reset hay rate trong cửa sổ?
3. Ứng dụng đếm logical requests hay backend attempts?
4. Retry có được tính vào application duration và DB calls không?
5. Một VectorStore operation có thể gọi nhiều SQL statements không?
6. Query có thực sự đi đến database hay được trả từ cache?
7. Database metrics đang lấy từ đúng instance/replica/database không?
8. Application metrics có bao gồm embedding, pool wait, network và mapping không?
9. Có deployment, index migration, stats reset hoặc failover trong cửa sổ đo không?
10. Có sampling hoặc filter làm mất một phần traces/logs không?

Nếu chưa trả lời được, hãy đánh dấu giả thuyết cần xác minh, không tuyên bố hai phía đang mâu thuẫn.

## 3. Spring AI và Micrometer ở phía ứng dụng

Spring AI cung cấp Micrometer Observation cho thao tác VectorStore với tên:

~~~text
db.vector.client.operation
~~~

Thuộc tính operation thường gồm:

| Attribute | Ý nghĩa |
|---|---|
| db.operation.name | add, query, delete hoặc upsert theo operation |
| db.system | Họ backend được adapter nhận diện |
| spring.ai.kind | Thành phần Spring AI |
| db.collection.name | Collection/index nếu implementation cung cấp |
| db.namespace | Namespace nếu implementation hỗ trợ |

Timer có thể được export qua Prometheus thành các series tương ứng như:

~~~text
db_vector_client_operation_seconds_count
db_vector_client_operation_seconds_sum
db_vector_client_operation_seconds_max
~~~

Tên series và tag thực tế phải được xác minh tại registry/exporter của ứng dụng. Version Spring AI, MeterFilter và backend adapter có thể ảnh hưởng các trường được phát.

### 3.1. Count, sum và max

| Series | Nghĩa | Không nên diễn giải thành |
|---|---|---|
| seconds_count | Số phép đo timer đã hoàn tất | Số HTTP requests |
| seconds_sum | Tổng duration đã ghi, tính bằng giây | Latency của một request |
| seconds_max | Maximum theo cửa sổ/registry | p95 hoặc p99 |
| seconds_bucket | Histogram bucket nếu được bật | Luôn có sẵn ở mọi registry |

Throughput query theo backend:

~~~promql
sum by (db_system) (
  rate(db_vector_client_operation_seconds_count{
    db_operation_name="query"
  }[5m])
)
~~~

Latency trung bình của operation query:

~~~promql
sum by (db_system) (
  rate(db_vector_client_operation_seconds_sum{
    db_operation_name="query"
  }[5m])
)
/
sum by (db_system) (
  rate(db_vector_client_operation_seconds_count{
    db_operation_name="query"
  }[5m])
)
~~~

Đây là latency trung bình tại ranh giới observation VectorStore, không mặc nhiên là SQL server execution time.

### 3.2. Đo application wrapper riêng

Ứng dụng có thể tạo timer ở service boundary để đo đúng thời gian mà code gọi VectorStore phải chờ. Đặt tên khác với meter Spring AI để tránh hiểu nhầm hoặc đăng ký meter trùng.

~~~java
import java.util.List;
import java.util.Objects;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

@Service
public final class VectorStoreBoundaryMetrics {
    private final VectorStore vectorStore;
    private final Timer serviceTimer;
    private final Counter success;
    private final Counter error;

    public VectorStoreBoundaryMetrics(
            VectorStore vectorStore,
            MeterRegistry registry) {
        this.vectorStore = Objects.requireNonNull(vectorStore);
        this.serviceTimer = Timer.builder("app.vectorstore.service.duration")
                .description("Thời gian service chờ lời gọi VectorStore")
                .tag("store.role", "policy-search")
                .register(registry);
        this.success = Counter.builder("app.vectorstore.service.outcomes")
                .tag("store.role", "policy-search")
                .tag("outcome", "success")
                .register(registry);
        this.error = Counter.builder("app.vectorstore.service.outcomes")
                .tag("store.role", "policy-search")
                .tag("outcome", "error")
                .register(registry);
    }

    public List<Document> query(String question, int topK) {
        SearchRequest request = SearchRequest.builder()
                .query(question)
                .topK(topK)
                .build();

        return serviceTimer.record(() -> {
            try {
                List<Document> result = Objects.requireNonNull(
                        vectorStore.similaritySearch(request));
                success.increment();
                return result;
            }
            catch (RuntimeException exception) {
                error.increment();
                throw exception;
            }
        });
    }
}
~~~

Đây là ví dụ service boundary, chưa phải DB timer. Nó bao gồm những gì implementation VectorStore thực hiện đồng bộ bên trong method, có thể gồm embedding nội bộ, network, pool wait và mapping. Nếu adapter trả kết quả bất đồng bộ hoặc dùng queue, cần đo thêm thời gian hoàn tất task và context propagation phù hợp.

Không gắn query text, tenant ID, document ID hoặc raw filter vào tags. Store role và outcome phải lấy từ danh mục hữu hạn.

### 3.3. Tránh đếm đôi và hiểu retry

Giả sử một logical retrieval request timeout lần đầu, retry thành công lần hai:

| Đơn vị | Success | Error | Tổng |
|---|---:|---:|---:|
| Logical request | 1 | 0 | 1 |
| VectorStore attempts | 1 | 1 | 2 |
| Database statements | Có thể 1 hoặc nhiều | Có thể 1 hoặc nhiều | Phụ thuộc adapter |

Timer service có thể đo tổng thời gian bao gồm retry nếu retry nằm bên trong method. Timer Spring AI có thể ghi mỗi lần operation nếu mỗi lần retry gọi lại VectorStore. Database statement counter chỉ tăng cho các statement thực sự được server xử lý. Do đó count khác nhau là điều có thể dự đoán.

## 4. Connection pool: khoảng chờ trước database

Với JDBC và HikariCP, application có thể phải đợi một connection rảnh trước khi gửi SQL. Database server không ghi nhận thời gian chờ ở pool này vì request chưa tới server.

### 4.1. Các tín hiệu pool cần quan sát

HikariCP có thể cung cấp các meter theo registry/version như:

| Meter thường gặp | Ý nghĩa |
|---|---|
| hikaricp.connections.active | Số connection đang được sử dụng |
| hikaricp.connections.idle | Số connection đang rảnh |
| hikaricp.connections.pending | Số thread đang chờ connection |
| hikaricp.connections.max | Giới hạn connection |
| hikaricp.connections.min | Mức connection tối thiểu |
| hikaricp.connections.acquire | Thời gian lấy connection |
| hikaricp.connections.usage | Thời gian giữ connection |
| hikaricp.connections.timeout | Số lần lấy connection timeout |

Tên meter chính xác phụ thuộc phiên bản HikariCP, Spring Boot và registry. Kiểm tra endpoint Actuator/exporter thay vì giả định mọi meter đều có.

### 4.2. Đọc trạng thái pool

- Active gần max, pending tăng và acquire time tăng: có thể pool bị bão hòa hoặc connection bị giữ quá lâu.
- Active thấp, pending bằng 0 nhưng DB query chậm: tìm nguyên nhân ở backend, network hoặc execution plan.
- Idle cao không tự chứng minh pool được cấu hình đúng; pool có thể lớn hơn mức database chịu tải.
- Connection timeout có thể xảy ra trước khi database nhìn thấy câu lệnh.

Không giải quyết pool saturation bằng cách tăng max connections ngay lập tức. Tăng pool có thể làm database nhận thêm concurrency và khiến contention nặng hơn. Xem connection usage, query duration, transaction scope và giới hạn database trước.

### 4.3. Tính thời gian chờ theo đúng ranh giới

Nếu instrumentation đo được:

~~~text
service boundary duration = 420 ms
JDBC client span          = 300 ms
pool acquire              = 80 ms
database statement       = 170 ms
~~~

Đây là ví dụ minh họa. Không lấy 420 - 300 - 80 - 170 rồi gọi phần còn lại là mapping time nếu các spans không cùng một request, có overlap hoặc đo ở những ranh giới khác nhau. Cần trace cụ thể để xác định các khoảng bao nhau.

## 5. Đọc số liệu phía PostgreSQL

Phần này dùng PostgreSQL làm ví dụ vì pgvector thường được triển khai trên PostgreSQL. Các truy vấn dưới đây chỉ đọc catalog/statistics views; quyền xem có thể phụ thuộc role, cấu hình và phiên bản. Không chạy lệnh reset statistics hoặc thay đổi index trong lúc điều tra chỉ để làm số liệu đẹp hơn.

### 5.1. pg_stat_statements: số lần gọi và thời gian thực thi theo nhóm SQL

Extension pg_stat_statements thu thập thống kê của các câu lệnh SQL đã chuẩn hóa. Trước khi dùng, DBA cần cấu hình extension theo phiên bản PostgreSQL và cấp quyền phù hợp. Không tự cài/đổi cấu hình production nếu không có quyền vận hành.

Truy vấn tham khảo:

~~~sql
SELECT
    queryid,
    calls,
    rows,
    total_exec_time,
    mean_exec_time,
    max_exec_time,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các cột có thể khác theo phiên bản PostgreSQL/pg_stat_statements. Hãy kiểm tra schema extension thực tế trước khi dùng query trong dashboard. Query text thường được chuẩn hóa nhưng vẫn không nên export raw SQL hoặc literal có thể nhạy cảm.

Ý nghĩa:

- calls: số lần statement được ghi nhận.
- rows: số rows mà statement trả về/thao tác theo semantics của view.
- total_exec_time: tổng thời gian thực thi được ghi nhận.
- mean_exec_time: thời gian trung bình mỗi lần gọi.
- max_exec_time: thời gian cao nhất được ghi nhận.
- shared_blks_hit: số lần tìm thấy block trong shared buffers.
- shared_blks_read: số block cần đọc vào shared buffers từ tầng lưu trữ.
- temp_blks_read/written: hoạt động block tạm, có thể chỉ dấu sort/hash spill.

shared_blks_read không đồng nghĩa chắc chắn với physical disk I/O; dữ liệu có thể đến từ OS page cache hoặc các tầng cache khác. Cần đối chiếu thêm I/O metrics của hệ điều hành/cloud/database.

### 5.2. So sánh theo cửa sổ bằng delta

pg_stat_statements là thống kê tích lũy từ lần reset hoặc thay đổi trạng thái thống kê gần nhất. Để so sánh một khoảng thời gian, chụp snapshot ở đầu và cuối rồi tính delta:

~~~text
delta_calls = calls_end - calls_start
delta_time  = total_exec_time_end - total_exec_time_start
mean_in_window = delta_time / delta_calls
~~~

Chỉ tính mean nếu delta_calls > 0. Nếu counters bị reset, database restart hoặc entry bị deallocate giữa hai snapshot, delta có thể âm hoặc không đáng tin; đánh dấu cửa sổ đó không hợp lệ và lấy lại baseline.

Không lấy tổng total_exec_time từ một snapshot rồi gọi đó là thời gian của 5 phút gần nhất nếu chưa biết thời điểm reset.

### 5.3. pg_stat_activity: trạng thái và wait events

Truy vấn chỉ đọc để xem hoạt động hiện tại:

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

Các trạng thái/wait event có thể giúp phân biệt:

- Session active đang chạy hoặc chờ một sự kiện.
- Chờ lock có thể chỉ ra contention.
- Chờ I/O có thể gợi ý đọc dữ liệu.
- Idle in transaction có thể giữ lock/connection lâu.
- Nhiều session active đồng thời có thể liên quan đến concurrency cao.

Không kết luận query chậm chỉ từ một snapshot pg_stat_activity; đây là ảnh chụp thời điểm. Cần lấy mẫu theo thời gian và kết hợp query statistics/traces. Tránh xuất query text hoặc application_name chứa định danh khách hàng vào telemetry.

### 5.4. pg_stat_user_indexes: index có đang được sử dụng?

Với PostgreSQL:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
~~~

Các counter là tích lũy và có thể reset. idx_scan thấp không tự động chứng minh index vô dụng: workload có thể ít, index mới, query planner chọn sequential scan hợp lý hoặc khoảng đo quá ngắn.

Đối với pgvector, loại index và operator class phải khớp distance operator/query. Ví dụ HNSW hoặc IVFFlat có cấu hình và trade-off khác nhau; việc index tồn tại không đảm bảo query cụ thể sử dụng index đó. Xem execution plan trên query đại diện và dữ liệu an toàn.

### 5.5. pg_stat_database: buffer và temporary I/O

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_hit,
    blks_read,
    temp_files,
    temp_bytes,
    deadlocks,
    conflicts
FROM pg_stat_database
WHERE datname = current_database();
~~~

Các counters này giúp quan sát xu hướng database-wide:

- Buffer hit/read phản ánh hoạt động buffer cache ở phạm vi database.
- Temporary files/bytes tăng có thể liên quan đến sort/hash spill hoặc query workload.
- Deadlocks/rollback tăng có thể liên quan đến transaction contention.
- Conflicts có ý nghĩa tùy loại standby/replication.

Đây không phải số liệu riêng cho VectorStore. Nếu cùng database phục vụ nhiều ứng dụng, cần attribution ở mức statement/query group hoặc trace phù hợp trước khi quy nguyên nhân cho RAG.

### 5.6. EXPLAIN và EXPLAIN ANALYZE

Để xem kế hoạch thực thi, dùng một query đại diện trên dữ liệu test hoặc môi trường được phép:

~~~sql
EXPLAIN (COSTS, VERBOSE)
SELECT id
FROM policy_chunks
ORDER BY embedding <=> '[0.01, 0.02, 0.03]'::vector
LIMIT 5;
~~~

Vector literal trên chỉ minh họa cú pháp và không khớp dimension thật của mọi index. Thay bảng, cột, operator và vector bằng schema/model của môi trường thử nghiệm.

EXPLAIN ANALYZE thực sự chạy statement để đo execution; chỉ dùng trên query an toàn, dữ liệu phù hợp và môi trường được phê duyệt. Với query ghi dữ liệu, side effects có thể xảy ra; không chạy tùy tiện trên production. Với SELECT nặng, nó vẫn tiêu thụ tài nguyên và ảnh hưởng workload.

Khi đọc plan, kiểm tra:

- Index Scan/Index Only Scan hay Seq Scan.
- Số rows ước tính so với thực tế.
- Filter rows bị loại và Rows Removed by Filter.
- Sort/Bitmap/Heap Fetches và buffer usage nếu được hiển thị.
- Index condition/operator có phù hợp vector distance không.
- LIMIT và thứ tự plan có đúng với query thực tế không.

Không đưa query text, vector literal hoặc bind values nhạy cảm vào tài liệu telemetry công khai.

## 6. Đối chiếu metric ứng dụng với DB statistics

### 6.1. Ví dụ đối chiếu theo cửa sổ 5 phút

Giả sử trong 5 phút:

| Tầng | Count | Thời gian |
|---|---:|---:|
| Logical RAG requests | 1.000 | p95 request 1.800 ms |
| VectorStore observations | 1.150 | p95 380 ms |
| JDBC statement calls | 1.300 | Mean 95 ms |
| pg_stat_statements delta calls | 1.280 | Mean 88 ms |

Các số liệu giả định. Chênh lệch có thể đến từ:

- Một số RAG request không cần retrieval.
- Một số request retry.
- Một VectorStore operation gọi nhiều statement.
- Statement được gọi ngoài RAG service khác dùng chung database.
- Cache hoặc code path khác bỏ qua VectorStore.
- Counter delta không đồng bộ chính xác với scrape window.
- Application timer bao gồm pool/network/mapping trong khi DB timer chỉ đo execution.

Không cố làm các count khớp bằng cách nhân/chia một hệ số nếu chưa tìm được semantics từng counter.

### 6.2. Đối chiếu count

| Chênh lệch | Giả thuyết | Cách xác minh |
|---|---|---|
| App VectorStore count > DB statement calls | Cache, query bị hủy trước DB, hoặc metric scope khác | Trace/client spans, cache metrics, DB statement group |
| DB statement calls > VectorStore count | Một operation tạo nhiều SQL statements hoặc app khác dùng chung DB | Query fingerprint, connection/application scope |
| App request count > VectorStore count | Request không phải lúc nào cũng truy xuất, hoặc cache hit | RAG route, cache hit/miss |
| VectorStore count > logical request count | Retry, multi-query retrieval, tool loop | Attempt count, child spans, run manifest |
| DB count dao động sau reset | Statistics reset/deallocate/restart | Reset timestamp, DB uptime, snapshot history |

### 6.3. Đối chiếu latency

| Quan sát | Hướng điều tra |
|---|---|
| App timer cao, DB execution thấp | Pool acquire, embedding nội bộ, network, proxy, row mapping, client retry |
| App timer và DB execution cùng tăng | Query plan, index, buffer/I/O, lock, DB saturation |
| App timer thấp, DB total time cao | Cửa sổ đo không khớp, query chạy async/background, DB dùng chung workload |
| JDBC client span cao, DB execution thấp | Pool, network, protocol, result transfer hoặc client-side processing |
| DB execution cao, app timer thấp | Aggregation scope khác, sampling, async hoặc metric scrape lệch cửa sổ |
| p95 app cao nhưng DB mean ổn định | Tail latency, lock wait, pool wait, outlier hoặc mean che phân phối |

**Không dùng p95 app trừ mean DB** để tính pool wait. Muốn phân rã cần span/client timing hoặc metric pool acquire được đo trực tiếp.

### 6.4. So sánh cùng đơn vị và cùng thời điểm

Một bảng điều tra tốt nên có:

- UTC start/end của cửa sổ.
- Database instance/role và application deployment version.
- Metric name, unit, aggregation và reset semantics.
- Delta calls, delta duration, rows và error counts.
- Application attempts, logical requests và retries.
- Pool active/idle/pending/acquire/usage.
- Trace sample IDs hoặc run references đã được redaction.
- Sự kiện deploy, failover, index build, stats reset và traffic spike.

Không cần lưu raw query hoặc customer identifier vào bảng tổng hợp.

## 7. Java: tạo correlation và metrics có scope rõ ràng

Ví dụ wrapper ở phần trước đo thời gian service gọi VectorStore. Có thể bổ sung observation để nối span ứng dụng với span Spring AI/database client nếu context propagation hoạt động.

~~~java
import java.util.List;
import java.util.Objects;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

@Service
public final class CorrelatedVectorSearch {
    private final VectorStore store;
    private final ObservationRegistry observations;
    private final Timer serviceTimer;

    public CorrelatedVectorSearch(
            VectorStore store,
            ObservationRegistry observations,
            MeterRegistry meters) {
        this.store = Objects.requireNonNull(store);
        this.observations = Objects.requireNonNull(observations);
        this.serviceTimer = Timer.builder("app.vectorstore.service.duration")
                .tag("store.role", "policy-search")
                .register(meters);
    }

    public List<Document> search(String question, String runId) {
        SearchRequest request = SearchRequest.builder()
                .query(question)
                .topK(5)
                .build();

        return Observation.createNotStarted(
                        "app.vectorstore.service.query", observations)
                .lowCardinalityKeyValue("store.role", "policy-search")
                .highCardinalityKeyValue("evaluation.run_id", runId)
                .observe(() -> serviceTimer.record(
                        () -> store.similaritySearch(request)));
    }
}
~~~

Ví dụ chỉ ghi run reference và store role; không gắn query hoặc filter vào span. runId là high-cardinality nên không được chuyển thành metric tag. Nếu run ID có thể liên kết người dùng, hãy tạo opaque random ID và giới hạn quyền tra cứu.

Timer service bao quanh method call; Spring AI VectorStore Observation có thể là span con nếu được cấu hình. DB client span có thể tiếp tục bên dưới nếu JDBC instrumentation được bật. Không giả định trace tự nối qua mọi executor/proxy; kiểm thử parent/child context trên runtime thật.

### 7.1. HikariCP và Actuator

Trong ứng dụng Spring Boot dùng HikariCP, có thể quan sát các meter pool được bind tự động nếu datasource metrics được cấu hình và exporter hỗ trợ. Kiểm tra:

- Connection active/idle/pending.
- Max/min pool size.
- Acquire time và usage time.
- Connection timeout count.
- JDBC connection metrics nếu Spring Boot/registry cung cấp.

Không tạo thêm một timer custom cùng tên Hikari meter. Nếu cần metric business, đặt tên riêng và mô tả scope rõ.

### 7.2. Không nhét trace ID vào SQL comment để correlation tùy tiện

Một số hệ thống có thể truyền application name hoặc query tags để nhận diện workload, nhưng không nên thêm một ID duy nhất cho mỗi request vào SQL text/comment một cách thiếu kiểm soát:

- Có thể phá query normalization và tạo nhiều fingerprint.
- Có thể tăng cardinality của pg_stat_statements hoặc logging.
- Có thể làm lộ correlation ID ở nơi có quyền khác.
- Có thể thay đổi caching hoặc plan reuse tùy driver/backend.

Ưu tiên distributed tracing/JDBC instrumentation được hỗ trợ, application name ổn định theo service/role và correlation reference trong evidence store. Nếu cần query tagging, dùng một tập giá trị hữu hạn, được DBA và security review.

## 8. PromQL và dashboard đối chiếu

### 8.1. Application VectorStore p95

Nếu histogram của Spring AI timer được bật và exporter có bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, db_system) (
    rate(db_vector_client_operation_seconds_bucket{
      db_operation_name="query"
    }[5m])
  )
)
~~~

Nếu bucket không được export, công thức không có dữ liệu. Không thay bằng _max rồi gọi đó là p95.

### 8.2. Application service wrapper p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, store_role) (
    rate(app_vectorstore_service_duration_seconds_bucket[5m])
  )
)
~~~

Tên label có thể được chuẩn hóa thành store_role khi export. Kiểm tra series thật trong Prometheus trước khi dùng query.

### 8.3. Hikari pool pending

Nếu Hikari meter được export với tên chuẩn tương ứng:

~~~promql
max_over_time(hikaricp_connections_pending[5m])
~~~

Theo dõi mức active so với max:

~~~promql
max_over_time(hikaricp_connections_active[5m])
/
max_over_time(hikaricp_connections_max[5m])
~~~

Đây là tỷ lệ snapshot cực đại theo cửa sổ, không phải utilization trung bình. Tên meter có thể khác; xác minh exporter. Một thời điểm active bằng max không đủ chứng minh pool bão hòa nếu pending luôn bằng 0 và acquire time thấp.

### 8.4. Database statement rate và mean execution time

Nếu database exporter cung cấp counters phù hợp, có thể tính rate/delta ở tầng exporter. Không giả định tên metric PostgreSQL giống nhau giữa postgres_exporter, cloud provider exporter hoặc dashboard vendor. Với pg_stat_statements snapshot, cần delta giữa hai lần scrape hoặc exporter chuyên dụng hiểu counter semantics.

Ví dụ dạng khái niệm:

~~~promql
rate(postgresql_stat_statements_calls_total[5m])
~~~

Tên này chỉ là ví dụ minh họa; phải thay bằng metric thật do exporter cung cấp. Nếu exporter expose cumulative total_exec_time và calls, tính mean trong cửa sổ bằng:

~~~text
delta_total_exec_time / delta_calls
~~~

Không dùng rate(total_exec_time) chia rate(calls) nếu exporter không biểu diễn hai trường như counter tích lũy tương thích hoặc có reset không được xử lý.

### 8.5. Dashboard nên chia thành các hàng

| Hàng | Panels |
|---|---|
| Application | RAG request rate, VectorStore operation rate, service p50/p95/p99, errors |
| Spring AI | db.vector.client.operation count/sum/histogram, operation name, store role |
| Connection pool | active, idle, pending, max, acquire, usage, timeout |
| Database | statement calls/time, active sessions, wait events, buffer hits/reads, temp I/O, index scans |
| Retrieval quality | returned count, zero-result, Recall@K, Precision@K, nDCG |
| Correlation | deploy/index version, retry rate, trace references, incident markers |

Metrics database có thể ở phạm vi instance/database và bao gồm nhiều ứng dụng. Đừng hiển thị chúng dưới nhãn “VectorStore” nếu chưa có cách attribution phù hợp.

## 9. Những tình huống chênh lệch thường gặp

### 9.1. Ứng dụng chậm, database nhanh

Giả thuyết:

- Pool acquire wait cao.
- Query embedding được thực hiện bên trong VectorStore call.
- Network/proxy latency cao.
- Driver nhận nhiều rows hoặc payload lớn.
- Adapter mapping metadata/document tốn thời gian.
- Retry ở client hoặc circuit breaker.

Evidence:

- Trace app → embedding → VectorStore → JDBC.
- Hikari acquire/usage/pending.
- Client spans và DB execution stats.
- Rows returned và response size đã được phép thu thập.

### 9.2. Ứng dụng và database cùng chậm

Giả thuyết:

- Query plan đổi.
- Index không được dùng hoặc không khớp operator class.
- Lock/I/O wait.
- Cache hit giảm.
- Corpus tăng hoặc filter selectivity thay đổi.
- Backend concurrency quá cao.

Evidence:

- pg_stat_statements delta.
- pg_stat_activity wait events.
- EXPLAIN trên query đại diện ở môi trường phù hợp.
- Buffer/I/O/CPU và index metrics.

### 9.3. Database có nhiều calls hơn ứng dụng

Có thể database dùng chung cho nhiều service, một VectorStore operation phát nhiều SQL, hoặc background indexing/job khác đang chạy. Kiểm tra query group, database/user/application scope và workload khác trước khi quy toàn bộ calls cho RAG.

### 9.4. Ứng dụng có nhiều calls hơn database

Có thể cache trả kết quả, request bị hủy trước khi gửi SQL, pool timeout, embedding fail trước query hoặc metrics app đếm attempts trong khi DB không nhận được statement. Cần kiểm tra trace stage và client error.

### 9.5. DB mean ổn định nhưng application p95 tăng

Mean DB có thể che tail latency. Một phần nhỏ request có thể bị lock wait, pool wait hoặc network delay. So p95/p99 ở client/pool và database wait samples; không so p95 ứng dụng với mean database như hai phân phối tương đương.

## 10. Runbook điều tra theo trình tự

1. **Chọn cửa sổ UTC:** xác định start/end, instance, database, service deployment và traffic cohort.
2. **Kiểm tra reset:** database restart, statistics reset, pg_stat_statements deallocation, exporter restart và scrape gaps.
3. **Đọc application metrics:** logical requests, VectorStore operations, attempts, retry, duration và error rate.
4. **Đọc Spring AI observations:** operation query/add/delete, store/backend và timer scope.
5. **Đọc pool metrics:** active/idle/pending/max, acquire/usage/timeout.
6. **Đọc database statistics:** delta calls/time, rows, buffer hit/read, temp I/O và wait events.
7. **Mở trace đại diện:** xác định pool wait, client span, embedding, DB span và mapping nếu có.
8. **Kiểm tra execution plan:** chỉ dùng query an toàn, có quyền và môi trường phù hợp.
9. **Đối chiếu quality:** returned count, Recall@K, relevance và context quality để bảo đảm tối ưu hiệu năng không làm retrieval sai.
10. **Ghi giả thuyết và xác minh:** mỗi kết luận phải có evidence ở tầng tương ứng.
11. **Sau thay đổi:** chạy lại workload cùng dataset, tải và cấu hình; so sánh trước/sau.

### 10.1. Mẫu bảng ghi nhận sự cố

| Trường | Ví dụ |
|---|---|
| Incident window UTC | 10:00–10:15 |
| Application build | rag-service-2026.11.27.2 |
| Spring AI adapter | version đã pin trong build |
| Store role/backend | policy-search / PostgreSQL |
| Index version | policy-index-v5 |
| App VectorStore p95 | 420 ms |
| Hikari pending max | 12 |
| DB statement mean | 80 ms |
| DB wait event | lock hoặc I/O nếu quan sát được |
| Retry rate | 3% |
| Retrieval Recall@5 | 0.92 |
| Evidence references | opaque run/trace references có ACL |

Số liệu ở ví dụ chỉ là placeholder minh họa cách lập bảng. Không đưa raw query, document content, tenant ID hoặc credentials vào incident record chung.

## 11. Thí nghiệm và kiểm chứng

### 11.1. Baseline trước khi tối ưu

Chạy một workload cố định và lưu:

- Dataset/corpus/index/embedding versions.
- TopK, threshold, filter profile.
- Số logical requests và attempts.
- Application/VectorStore/JDBC latency distributions.
- Pool metrics và DB statistics deltas.
- Retrieval quality: Recall@K, Precision@K và zero-result.
- Environment, database size, concurrency và warm/cold cache condition.

Nếu chỉ chạy một lần ở trạng thái cache nóng, không đại diện cho workload lạnh. Ghi rõ trạng thái cache hoặc chạy nhiều vòng có phương pháp.

### 11.2. Thay một yếu tố mỗi lần

Ví dụ muốn kiểm tra connection pool:

1. Giữ dataset, query, topK, threshold, index và database workload cố định.
2. Ghi acquire time, active/pending và application duration.
3. Thay pool size trong môi trường thử nghiệm theo capacity giới hạn.
4. Đo lại DB concurrency, wait events và execution time.
5. Kiểm tra latency p95 và error rate có cải thiện không.
6. Đánh giá xem tăng pool có đẩy database vào contention hay không.

Muốn kiểm tra index/query plan, thay đổi index hoặc ANN parameters trong môi trường thử nghiệm và đo riêng. Không đổi pool, index và topK cùng lúc rồi quy kết quả cho một nguyên nhân.

### 11.3. Đừng tối ưu database mà bỏ qua quality

Một index/ANN config có thể làm query nhanh hơn nhưng giảm recall. Release gate cần cả:

~~~yaml
retrievalReleasePolicy: vectorstore-performance-v2
gates:
  vectorStoreP95MsAtMost: 250
  minimumRecallAt5: 0.90
  minimumPrecisionAt5: 0.70
  maximumQueryErrorRate: 0.01
  crossTenantLeakageAllowed: 0
  evaluationCoverageMinimum: 1.0
~~~

Các ngưỡng chỉ là ví dụ; sản phẩm phải đặt theo SLA, dữ liệu và rủi ro. Nếu query p95 đạt nhưng Recall@5 giảm dưới ngưỡng, candidate chưa đạt yêu cầu.

## 12. Bảo mật khi đối chiếu hai phía

Database statistics và traces có thể chứa query text, database/schema/table names, application names hoặc identifiers. Cần:

- Dùng role read-only cho dashboard/statistics queries khi có thể.
- Không cấp superuser chỉ để xem metrics.
- Không xuất query text/raw bind values vào telemetry chung.
- Chuẩn hóa application_name theo service/role, không chứa user hoặc tenant.
- Giới hạn quyền xem pg_stat_activity/pg_stat_statements theo chính sách.
- Redact connection strings, host secrets, tokens và SQL literals.
- Chỉ dùng EXPLAIN ANALYZE trên query/môi trường an toàn.
- Giữ trace references opaque và evidence có ACL.
- Theo dõi quyền truy cập dashboard và dữ liệu export.

DB statistics là nguồn dữ liệu vận hành, không phải nơi lưu evidence RAG đầy đủ. Không dùng query fingerprint để suy ra người dùng cụ thể.

## 13. Những sai lầm thường gặp

1. **So application timer với DB execution time như cùng một phạm vi.** App có thể gồm pool, network, embedding và mapping.
2. **Kỳ vọng VectorStore count bằng SQL calls.** Một operation có thể tạo nhiều statement hoặc không tới DB.
3. **So counter tích lũy với rate trong 5 phút.** Phải tính delta và kiểm tra reset.
4. **Dùng mean DB để giải thích p95 app.** Mean che tail latency.
5. **Coi shared block reads là physical disk reads.** OS cache và storage layers còn ảnh hưởng.
6. **Coi idx_scan thấp là index vô dụng.** Workload, planner và cửa sổ thống kê có thể giải thích.
7. **Tăng Hikari max pool ngay khi thấy pending.** Có thể làm DB quá tải hơn.
8. **Bỏ qua query embedding trong VectorStore timer.** Adapter có thể tự gọi EmbeddingModel.
9. **Cộng thời gian parent và child spans.** Các khoảng có thể bao nhau.
10. **Bật EXPLAIN ANALYZE tùy tiện trên production.** Statement được thực thi và có thể tiêu thụ tài nguyên/side effects.
11. **Đưa trace ID vào SQL comment cho từng request.** Có thể phá query normalization và tăng cardinality.
12. **Gán toàn bộ DB load cho VectorStore.** Database có thể được nhiều service dùng chung.
13. **Chỉ tối ưu latency mà không kiểm tra Recall@K.** Query nhanh hơn có thể trả ít nguồn đúng hơn.
14. **Không ghi nhận reset/restart/failover.** Delta statistics có thể sai.
15. **Ghi raw SQL hoặc bind values vào incident dashboard.** Có thể làm lộ dữ liệu nhạy cảm.

## 14. Bài thực hành tự luyện

**Bối cảnh:** Một ứng dụng Spring AI dùng PostgreSQL/pgvector làm VectorStore. Sau khi tăng lưu lượng, application VectorStore p95 tăng từ 120 ms lên 430 ms. Database statement mean vẫn khoảng 85 ms. Đội vận hành cần xác định thời gian còn lại nằm ở pool, embedding, network hay adapter.

Yêu cầu:

1. Bật Spring AI VectorStore observations và xác minh timer/labels thực tế.
2. Thêm application wrapper timer có tên riêng; ghi rõ scope.
3. Bật Hikari metrics và thu active, idle, pending, max, acquire, usage, timeout.
4. Dùng pg_stat_statements snapshot ở đầu/cuối cửa sổ để tính delta calls và execution time.
5. Dùng pg_stat_activity lấy wait-event snapshots theo chu kỳ.
6. Đọc pg_stat_user_indexes và kiểm tra index phù hợp với operator class của truy vấn vector.
7. Chạy EXPLAIN trên query đại diện trong môi trường phù hợp; chỉ dùng EXPLAIN ANALYZE khi được phép.
8. Thu trace đại diện để tách embedding, pool/client, DB execution và result mapping nếu instrumentation hỗ trợ.
9. Giải thích count mismatch giữa VectorStore operations và SQL statements.
10. Đối chiếu latency với returned count và Recall@5 để bảo đảm thay đổi hiệu năng không làm giảm chất lượng.
11. Viết dashboard có cùng time window và cảnh báo khi pool pending, query p95 hoặc DB waits tăng.
12. Viết runbook nêu rõ giới hạn của mỗi nguồn số liệu và các điều kiện reset.

**Câu hỏi tự kiểm tra:**

- Vì sao VectorStore timer có thể lớn hơn pg_stat_statements mean execution time?
- Khi nào một VectorStore operation tạo nhiều SQL statements?
- Vì sao pg_stat_statements cần delta snapshots để đo một cửa sổ thời gian?
- shared_blks_read có đồng nghĩa physical disk I/O không?
- Hikari pending tăng nhưng database active sessions thấp gợi ý điều gì?
- Vì sao p95 application không thể trừ mean database để ra pool wait?
- Khi pg_stat_activity cho thấy wait event, cần lấy thêm bằng chứng gì?
- Tại sao không nên thêm trace ID duy nhất vào SQL comment cho mỗi request?
- Vì sao index scan count thấp không đủ kết luận index không cần thiết?
- Khi query nhanh hơn nhưng Recall@5 giảm, release có nên được chấp nhận không?

## 15. Checklist triển khai

- [ ] Định nghĩa scope, unit, aggregation và mẫu số của từng metric.
- [ ] Phân biệt logical request, VectorStore operation, backend attempt và SQL statement.
- [ ] Xác minh Spring AI observation db.vector.client.operation và các operation labels.
- [ ] Đo application wrapper riêng, không trùng tên meter framework.
- [ ] Theo dõi Hikari active/idle/pending/max/acquire/usage/timeout.
- [ ] Thu DB statement statistics theo delta và xử lý reset/restart.
- [ ] Dùng pg_stat_activity wait events như snapshot, không kết luận từ một lần chụp.
- [ ] Kiểm tra index usage và execution plan bằng query đại diện.
- [ ] Hiểu buffer hit/read và giới hạn của việc diễn giải physical I/O.
- [ ] Đối chiếu cùng UTC window, database instance, deployment và workload cohort.
- [ ] Dùng trace/client spans để phân rã pool, network, embedding, database và mapping khi có hỗ trợ.
- [ ] Không cộng duration của span cha/con hoặc trừ percentile để suy thời gian thành phần.
- [ ] Không dùng SQL comment/metric tags chứa ID duy nhất cho từng request.
- [ ] Không xuất raw SQL, bind values, query, tenant ID hoặc document content vào dashboard chung.
- [ ] Kiểm tra quality metrics như Recall@K/Precision@K song song với latency.
- [ ] Có runbook cho count mismatch, latency mismatch, pool saturation và DB wait.

## Tổng kết

Metric phía ứng dụng và số liệu cơ sở dữ liệu quan sát cùng một hoạt động ở các ranh giới khác nhau. Spring AI VectorStore timer có thể bao gồm embedding, pool wait, network và xử lý adapter; PostgreSQL statistics phản ánh statement calls, execution time, buffer và trạng thái server theo semantics riêng. HikariCP cho biết tình trạng pool trước khi request tới database. Vì vậy count và duration không cần bằng nhau, nhưng mọi chênh lệch cần được giải thích bằng scope, retry, batching, cache, nhiều statement hoặc workload dùng chung.

Một quy trình điều tra đáng tin cậy căn chỉnh cửa sổ thời gian, kiểm tra reset counters, kết hợp application observations, JDBC/client traces, pool metrics và DB statistics, rồi xác minh bằng query plan khi phù hợp. Cuối cùng, đối chiếu hiệu năng với returned count và retrieval quality để bảo đảm tối ưu cơ sở dữ liệu không làm suy giảm chất lượng RAG.

## Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): VectorStore observations và thuộc tính operation.
- [Spring AI — Vector Databases](https://docs.spring.io/spring-ai/reference/api/vectordbs.html): VectorStore API và SearchRequest.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, datasource và pool metrics.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): timer count, total time, max và histogram.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): connection pool behavior và metric integration.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity, pg_stat_database và statistics views.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): thống kê statement calls và execution time.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc execution plans và EXPLAIN ANALYZE.
- [pgvector](https://github.com/pgvector/pgvector): vector operators, index types và query behavior.
- [OpenTelemetry — Database Spans](https://opentelemetry.io/docs/specs/semconv/database/): database client span conventions.
