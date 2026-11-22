# Đo tải với dữ liệu và phân bố truy cập đại diện

Một câu SQL chạy trong 4 ms trên máy phát triển không có nghĩa API Java sẽ phản hồi nhanh khi có hàng nghìn request, nhiều tenant, giao dịch ghi cạnh tranh và dữ liệu lớn hơn bộ nhớ đệm. Ngược lại, một bài benchmark tạo hàng triệu dòng giả nhưng luôn truy cập những khóa ngẫu nhiên, đồng đều cũng có thể cho kết quả lạc quan hoặc bi quan sai lệch so với lưu lượng thật.

**Đo tải có giá trị khi dữ liệu, hành vi truy cập, mức đồng thời và điều kiện vận hành đủ đại diện cho mục tiêu cần quyết định.** Không chỉ hỏi “DB xử lý được bao nhiêu query/giây?”, ta phải hỏi “với phân bố khách hàng, bảng và transaction thực tế, hệ thống đáp ứng được bao nhiêu yêu cầu *đúng* trong giới hạn p95/p99 và tỷ lệ lỗi chấp nhận được?”.

Trong chương **Hiệu năng** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài này kết nối kiến thức về lược đồ, chỉ mục, truy vấn, transaction, connection pool, kiểm soát đồng thời và tối ưu Java persistence. Ta sẽ thiết kế một workload có tỷ lệ đọc/ghi, *hot keys*, độ lớn tenant và nhịp tải rõ ràng; xây dữ liệu thử nghiệm; đo theo nhiều lớp; phân tích kết quả; và tránh các sai lầm làm benchmark không có ý nghĩa.

## 1. “Đại diện” nghĩa là đại diện cho điều gì?

Đối tượng thử nghiệm là **một hệ thống đang thực hiện các use case**, không chỉ một câu SQL rời rạc. Tính đại diện có ít nhất năm chiều:

1. **Dữ liệu:** số hàng, kích thước hàng, số tenant, tuổi dữ liệu, dữ liệu NULL, phân bố trạng thái, độ trùng giá trị, index và tỷ lệ dữ liệu có thể nằm trong RAM.
2. **Truy cập:** tỷ lệ từng loại yêu cầu, tham số được truy vấn, độ lệch về tenant/khóa, quét phạm vi hay tra một hàng, đọc trang đầu hay trang sâu.
3. **Thời gian:** request đều hay theo đợt, giờ cao điểm, burst ngắn, thời gian chuẩn bị, số lần chạy lại và tác vụ nền cùng hoạt động.
4. **Đồng thời:** số client, số transaction, độ dài transaction, tranh chấp cùng hàng, connection pool, retry, timeout và mức cô lập.
5. **Hạ tầng:** CPU, RAM, IOPS, network, DB version/config, connection pool, cache, replica/replication, WAL/checkpoint, GC và tài nguyên của bộ phát tải.

Nếu mục tiêu là cải thiện endpoint tìm kiếm đơn hàng, có thể ưu tiên các phân bố và metric của endpoint đó. Nếu mục tiêu là đánh giá **sức chịu tải cả nền tảng**, phải bổ sung các command thay đổi trạng thái, background jobs, replication lag và cạnh tranh tài nguyên giữa nhiều use case.

| Benchmark | Đo được | Không được suy ra |
| --- | --- | --- |
| `EXPLAIN (ANALYZE, BUFFERS)` của một SQL | Kế hoạch và thời gian thực thi một lần trong điều kiện cụ thể | p99 API, tải tối đa, độ trễ lấy connection hoặc tác động của traffic burst |
| Microbenchmark mapping Java | Chi phí đoạn code/ánh xạ trong điều kiện cô lập | Khả năng chịu tải DB hoặc độ trễ end-to-end |
| DB-only load test | Năng lực truy vấn/giao dịch dưới một hỗn hợp tải | Chi phí HTTP, xác thực, serialization và mạng phía người dùng |
| API end-to-end load test | Trải nghiệm qua ứng dụng, pool, mạng và DB | Chi tiết nút thắt DB nếu không có trace/metric nội bộ |
| Soak test nhiều giờ | Tích lũy connection, memory, bloat, WAL, GC, sự cố dài hạn | Đỉnh tải ngắn nếu không có stress/burst riêng |

Chọn benchmark theo câu hỏi. Một con số “100.000 operations/giây” không có giá trị so sánh nếu không biết operation đó là một SELECT trong cache hay một transaction gồm nhiều UPDATE và commit.

## 2. Từ telemetry thật đến workload model

Giả sử một dịch vụ Java quản lý đơn hàng cho nhiều tenant. Các số sau **chỉ là kịch bản minh họa**, không phải số liệu đã đo của một ứng dụng cụ thể:

| Tham số | Kịch bản thử nghiệm minh họa |
| --- | --- |
| Quy mô | 1 triệu đơn hàng, 1.000 tenant, dữ liệu của 90 ngày gần nhất |
| Phân bố yêu cầu | 70% từ 10 tenant “nóng”; 30% từ 990 tenant còn lại |
| Hỗn hợp | 70% danh sách đơn, 20% tra chi tiết, 10% cập nhật |
| Dữ liệu | 65% `PAID`, 25% `PENDING`, 10% `CANCELLED` |
| Trang đọc | Chủ yếu trang 1; cần một kịch bản riêng cho trang sâu |
| Độ trễ kỳ vọng | Tự đặt SLO đo từ HTTP ingress đến response, không suy từ SQL duration |
| Nền tải | Có ingestion, cleanup, checkpoint/vacuum và replica nếu kiến trúc thật có chúng |

Đây mới là **giả thuyết workload**. Trước khi coi nó đại diện, phải kiểm tra telemetry thực:

- Lấy tỷ lệ request theo endpoint và thời điểm (giờ thường, giờ cao điểm, chiến dịch).
- Thu phân bố tenant theo **số request, số hàng, số byte và số thao tác ghi**; chúng có thể lệch nhau.
- Phân tích query fingerprint/shape từ log tổng hợp hoặc metric DB, không chỉ URL API.
- Tách đọc từ cache với đọc thực sự tới DB; cache hit ratio thay đổi theo tenant và thời điểm.
- Đo số hàng trả về, độ sâu trang, số bản ghi trong transaction và tỷ lệ optimistic conflict/deadlock.
- Lấy thông tin chính xác về giá trị NULL, chuỗi dài, giá trị trùng và độ chọn lọc của predicate.

**Không lấy dữ liệu sản xuất chứa thông tin nhạy cảm rồi đưa nguyên xi vào môi trường test.** Cần ẩn danh, tổng hợp hoặc sinh dữ liệu có cùng thuộc tính thống kê, theo chính sách bảo mật. Việc thay email bằng giá trị giả nhưng giữ nguyên khóa định danh liên kết hoặc dữ liệu quá hiếm vẫn có thể làm lộ thông tin; kiểm tra tính riêng tư trước khi xuất dữ liệu.

### Phân biệt phân bố dữ liệu với phân bố yêu cầu

Một tenant có 20% số đơn nhưng chỉ 1% request, trong khi tenant khác giữ 1% số đơn mà phát sinh 35% request. Nếu generator giả định **xác suất truy cập tỷ lệ thuận số hàng**, bài test sẽ bỏ sót tenant nóng có ít dữ liệu nhưng gây contention. Vì vậy, nên biểu diễn hai phân bố riêng:

```text
             Phân bố lưu trữ               Phân bố truy cập
             ----------------              ----------------
Tenant A     20% số hàng                   1% request
Tenant B      1% số hàng                  35% request
Tenant khác  79% số hàng                  64% request

Lưu trữ quyết định kích thước/index/cache.
Truy cập quyết định hot rows, khóa, CPU và I/O đang chịu tải.
```

Phân bố có thể gần Zipf/Pareto: một nhóm nhỏ khóa nhận phần lớn lượt truy cập. Không cần ép dữ liệu thật vào một phân phối toán học nếu histogram thực tế đã đủ; điều quan trọng là **giữ lại độ lệch**, thay vì dùng uniform random cho mọi tham số.

## 3. Chuẩn bị dữ liệu có cấu trúc và thống kê thực tế

Schema thử nghiệm PostgreSQL sau được tạo **trong database test độc lập**. Không chạy thao tác sinh/xóa dữ liệu hay lệnh cập nhật benchmark lên production:

```sql
CREATE TABLE bench_orders (
    order_id     BIGINT PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    total_amount NUMERIC(18, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX bench_orders_tenant_recent
ON bench_orders (tenant_id, status, created_at DESC, order_id DESC);
```

Một cách sinh **dữ liệu giả có chủ ý tạo độ lệch** cho ví dụ 1 triệu hàng:

```sql
-- Chỉ chạy trong database dành riêng cho benchmark.
-- setseed giúp chuỗi random() có điểm khởi đầu lặp lại
-- trên một session, không bảo đảm mọi môi trường giống hệt.
SELECT setseed(0.42);

WITH generated AS (
    SELECT g AS order_id,
           random() AS status_draw,
           random() AS age_draw
    FROM generate_series(1, 1000000) AS g
)
INSERT INTO bench_orders (
    order_id, tenant_id, status, total_amount, created_at, version)
SELECT order_id,
       CASE
           WHEN order_id % 10 < 7
               THEN 1 + ((order_id / 10) % 10)
           ELSE 11 + ((order_id / 10) % 990)
       END AS tenant_id,
       CASE
           WHEN status_draw < 0.65 THEN 'PAID'
           WHEN status_draw < 0.90 THEN 'PENDING'
           ELSE 'CANCELLED'
       END AS status,
       round((10 + (order_id % 100000) * 0.01)::numeric, 2),
       CURRENT_TIMESTAMP
           - ((age_draw * 90 * 24 * 3600)::int * INTERVAL '1 second'),
       0
FROM generated;

ANALYZE bench_orders;
```

Phép `CASE` ở đây đưa xấp xỉ 70% hàng tới mười tenant đầu, 30% tới những tenant còn lại. Mỗi hàng dùng mẫu random để chọn status và tuổi; **đây vẫn là dữ liệu giả**: số tiền và thời gian có tương quan nhân tạo với `order_id`/phép sinh, không có payload lớn, trả hàng, hoàn tiền hay mùa vụ. Không mặc định nó đã mô phỏng ứng dụng thật.

Trước khi chạy, kiểm tra dữ liệu generator thực sự tạo ra:

```sql
SELECT COUNT(*) AS orders_count,
       COUNT(DISTINCT tenant_id) AS tenant_count,
       MIN(created_at) AS oldest_order,
       MAX(created_at) AS newest_order
FROM bench_orders;

SELECT status, COUNT(*)
FROM bench_orders
GROUP BY status ORDER BY status;

SELECT tenant_id, COUNT(*) AS orders_count
FROM bench_orders
GROUP BY tenant_id
ORDER BY orders_count DESC
LIMIT 20;
```

Thử nghiệm gần production hơn thường cần thêm **nhiều bảng và tương quan khóa ngoại**: `orders`, `order_items`, `payments`, `shipments`, `outbox_events`. Một transaction cập nhật nhiều bảng và ghi WAL không thể được mô phỏng trung thực bằng một câu `UPDATE version = version + 1`. Với dữ liệu lớn, cũng cần giữ đúng tỷ lệ hàng lớn, cột nullable, giá trị hiếm, lịch sử xóa/sửa và table/index bloat.

**Sau bulk load phải cập nhật statistics** phù hợp (ở PostgreSQL có `ANALYZE` hoặc autovacuum/autoanalyze); nếu planner chưa có thống kê đại diện, benchmark có thể chỉ đo tác động của plan sai do khâu chuẩn bị, không phải kiến trúc được thử.

## 4. Mô hình query shape và tỷ lệ đọc/ghi

Một workload hữu ích nên là tập những **operation có ý nghĩa**, ví dụ:

| Operation | Tỷ lệ ví dụ | SQL/transaction chính | Điều cần mô phỏng |
| --- | ---: | --- | --- |
| `listRecentPaid(tenantId)` | 70% | Filter + sort + limit | Tenant nóng/lạnh, số row trả về, trang đầu và cache |
| `getOrder(tenantId, orderId)` | 20% | Lookup theo khóa | Tỷ lệ hit/miss, tenant đúng, index lookup |
| `updateOrder(...)` | 10% | UPDATE có điều kiện hoặc transaction | Hot rows, khóa, optimistic conflict, WAL/commit |

SQL list thực tế của ví dụ:

```sql
SELECT order_id, created_at, total_amount, version
FROM bench_orders
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Lookup chi tiết:

```sql
SELECT order_id, status, total_amount, version
FROM bench_orders
WHERE order_id = ? AND tenant_id = ?;
```

Một command giả lập tối thiểu phục vụ đo **chi phí ghi và khóa**:

```sql
-- Chỉ dành cho bộ dữ liệu test có thể tạo lại.
UPDATE bench_orders
SET version = version + 1
WHERE order_id = ? AND tenant_id = ?;
```

Câu UPDATE cuối **không đại diện cho giao dịch nghiệp vụ thật** và **không idempotent**; nó chỉ tạo write load đơn giản. Trong bài test đánh giá khả năng chịu tải nghiệp vụ, thay bằng command thực tế: kiểm tra trạng thái/version, cập nhật nhiều bảng trong một transaction, tạo outbox nếu cần, commit hoặc rollback theo đúng quy tắc, và ghi nhận conflict như một kết quả riêng.

**Không nên trộn lẫn “90% query là SELECT” với “90% chi phí là đọc”.** Một thao tác ghi có thể phát sinh nhiều index update, WAL, khóa và đồng bộ; một SELECT có thể quét hàng triệu hàng. Đo từng nhóm và cả hỗn hợp để hiểu tác động chéo.

### Truy vấn cùng hình dạng nhưng tham số khác

Với cùng câu `WHERE tenant_id = ?`, tenant lớn có thể trả hàng nghìn kết quả trước LIMIT, tenant nhỏ chỉ có vài hàng. Một truy vấn phân trang sâu hoặc `status` hiếm có thể dùng kế hoạch khác. Cần lấy mẫu theo **độ chọn lọc** của bind values, không chỉ thay ngẫu nhiên `order_id`.

Trên PostgreSQL, prepared statements có thể dùng **custom plan** hoặc **generic plan** theo điều kiện của engine. Một lần `EXPLAIN` với literal chưa chắc đại diện cho kế hoạch của câu SQL mà JDBC gửi thực tế. Khi so sánh trước/sau tối ưu, ghi lại cách driver bind, khả năng server-side prepare, thống kê và phân bố tham số.

## 5. Độ lệch truy cập, hot keys và tranh chấp khóa

Nếu hai mươi thread cập nhật cùng một hàng, database phải phối hợp khóa và version; thông lượng không tăng tuyến tính theo số thread. Nếu các thread cập nhật hai mươi hàng độc lập, kết quả có thể khác hẳn.

```text
Workload A — phân bố đều:
  T1 -> row 1     T2 -> row 2     T3 -> row 3
  Ít tranh chấp trên cùng khóa (nhưng vẫn tranh chấp I/O)

Workload B — hot key:
  T1 -> row 42 <- T2
            ^      ^
            T3     T4
  Các transaction phải phối hợp ghi trên cùng hàng
```

Do đó nên tạo ít nhất ba kịch bản truy cập:

1. **Uniform/control:** tham số phân đều để đo baseline có ít tranh chấp.
2. **Observed skew:** mô phỏng histogram tenant/khóa gần thực tế; đây là kịch bản dùng cho quyết định chính.
3. **Stress hot spot:** tăng lệch, chẳng hạn dồn nhiều update vào cùng một nhóm khóa, để đo headroom và khả năng hệ thống xuống cấp có kiểm soát.

Cần ghi riêng **tỷ lệ conflict, lock wait, deadlock, số lần retry, transaction duration**. Một lần retry do deadlock thường chạy lại **toàn transaction**, không thể chỉ đo thời gian của SQL cuối. Retry vô hạn hoặc không có idempotency khiến benchmark vừa sai hiệu năng vừa nguy hiểm về tính đúng đắn.

## 6. Cách phát tải: mô hình đóng và mô hình mở

Hai kiểu mô phỏng tải không tương đương:

**Closed-loop (số client cố định):** mỗi virtual user gửi request, chờ kết quả, có thể chờ thêm *think time*, rồi mới gửi request tiếp. Nếu server chậm, tốc độ phát request tự giảm. Kiểu này phản ánh một số hành vi người dùng và phù hợp bài test concurrency cố định.

**Open-loop (arrival rate cố định/định trước):** bộ phát tạo request theo lịch/tốc độ đích tương đối độc lập với tốc độ server trả lời. Khi server chậm, số request đang chờ có thể tăng. Kiểu này hữu ích khi yêu cầu đến từ hệ thống ngoài, queue hoặc traffic burst.

```text
Closed-loop:
client -> request -> chờ response -> think time -> request kế tiếp
                     |
               server chậm -> số request/s thực phát giảm

Open-loop:
clock  -> req 1
       -> req 2 -> vẫn đến dù req 1 chưa xong
       -> req 3
                     |
               server chậm -> queue/tồn đọng tăng
```

Sai lầm phổ biến là dùng benchmark closed-loop với 20 threads, thấy p99 ổn và kết luận hệ thống chịu được 2.000 request/giây. **Concurrency không phải arrival rate**. Phải đo tốc độ thực phát, số request hoàn tất và thời gian chờ; một phép ước lượng ở trạng thái ổn định theo Little's Law là:

\[
L \approx \lambda \times W
\]

Trong đó `L` là số yêu cầu trung bình đang ở trong hệ thống, `λ` là throughput (request hoàn tất/giây) và `W` là thời gian tồn tại trung bình của yêu cầu. Công thức là **quan hệ trung bình trong điều kiện hệ thống ổn định**, không cho phép suy thẳng p99 từ số thread, cũng không đúng nếu cứ tăng arrival rate trong khi backlog tăng vô hạn.

### Coordinated omission

Một công cụ chỉ phát request mới **sau khi request trước hoàn tất** có thể bỏ sót những request *đáng lẽ phải đến* trong khoảng server bị treo. Kết quả latency histogram có thể **đẹp giả tạo**, vì không ghi nhận thời gian chờ của các lượt đến theo lịch.

Đối với workload open-loop, cần đo latency từ **thời điểm request theo lịch được xem là đến** hoặc dùng công cụ có cơ chế xử lý coordinated omission phù hợp. Nếu bộ phát tải không theo kịp lịch, phải ghi nhận *missed/late starts*, không lặng lẽ giảm request rate rồi vẫn báo đã đạt mục tiêu.

## 7. Java/JDBC: một bộ đo tải nhỏ có chủ đích

Ví dụ sau là **harness đóng (closed-loop)** với `ExecutorService`, mỗi worker mượn connection riêng cho từng operation. Nó dùng dataset ở phần 3 và minh họa cách phối hợp ba operation, lấy mẫu hot tenant, đo latency end-to-end **ở lớp JDBC**, đếm lỗi và hoàn trả tài nguyên.

Đây **không thay thế công cụ tải production-grade**: nó chưa hỗ trợ arrival schedule, histogram streaming, HTTP latency, think time, warmup riêng, TLS, phân tán bộ phát hoặc bảo vệ khỏi coordinated omission. Số dòng dữ liệu và UPDATE được cố định cho database benchmark độc lập; **không chạy trên production**.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class JdbcWorkloadProbe {
    private static final long ROW_COUNT = 1_000_000L;

    public record Summary(
            long attempted, long errors, double elapsedSeconds,
            double requestsPerSecond, double p50Ms, double p95Ms,
            double p99Ms) {}

    public static Summary run(DataSource dataSource, int workers,
                              int operationsPerWorker) throws Exception {
        if (workers <= 0 || operationsPerWorker <= 0) {
            throw new IllegalArgumentException("Số worker/operation phải > 0");
        }

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch startGate = new CountDownLatch(1);
        LongAdder attempts = new LongAdder();
        LongAdder errors = new LongAdder();
        ConcurrentLinkedQueue<Long> samplesNs =
                new ConcurrentLinkedQueue<>();
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int workerId = 0; workerId < workers; workerId++) {
                final int id = workerId;
                tasks.add(executor.submit(() -> {
                    SplittableRandom random =
                            new SplittableRandom(1000L + id);
                    startGate.await();
                    for (int n = 0; n < operationsPerWorker; n++) {
                        long orderId = chooseOrderId(random);
                        long tenantId = tenantForOrder(orderId);
                        double op = random.nextDouble();
                        long started = System.nanoTime();
                        attempts.increment();
                        try {
                            if (op < 0.70) {
                                listRecentPaid(dataSource, tenantId);
                            } else if (op < 0.90) {
                                readOne(dataSource, tenantId, orderId);
                            } else {
                                touchVersion(dataSource, tenantId, orderId);
                            }
                        } catch (SQLException failure) {
                            errors.increment();
                            // Không tự retry: retry policy là một phần workload.
                        } finally {
                            samplesNs.add(System.nanoTime() - started);
                        }
                    }
                    return null;
                }));
            }

            long startNs = System.nanoTime();
            startGate.countDown();
            for (Future<?> task : tasks) {
                task.get(); // Không bỏ sót exception từ worker.
            }
            long elapsedNs = System.nanoTime() - startNs;

            List<Long> latencies = new ArrayList<>(samplesNs);
            Collections.sort(latencies);
            double seconds = elapsedNs / 1_000_000_000.0;
            return new Summary(
                    attempts.sum(), errors.sum(), seconds,
                    attempts.sum() / seconds,
                    percentileMs(latencies, 0.50),
                    percentileMs(latencies, 0.95),
                    percentileMs(latencies, 0.99));
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static long chooseOrderId(SplittableRandom random) {
        // Cùng phép phân bucket được dùng lúc sinh dataset ở mục 3.
        // 70% yêu cầu nhắm vào nhóm tenant nóng.
        boolean hot = random.nextDouble() < 0.70;
        long orderId;
        do {
            orderId = random.nextLong(1L, ROW_COUNT + 1);
        } while ((orderId % 10 < 7) != hot);
        return orderId;
    }

    private static long tenantForOrder(long orderId) {
        return orderId % 10 < 7
                ? 1 + ((orderId / 10) % 10)
                : 11 + ((orderId / 10) % 990);
    }

    private static void listRecentPaid(DataSource dataSource, long tenantId)
            throws SQLException {
        String sql = """
            SELECT order_id, created_at, total_amount, version
            FROM bench_orders
            WHERE tenant_id = ? AND status = 'PAID'
            ORDER BY created_at DESC, order_id DESC LIMIT 50
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setQueryTimeout(3);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    // Phải tiêu thụ kết quả: không đo chỉ executeQuery().
                    rs.getLong("order_id");
                    rs.getBigDecimal("total_amount");
                    rs.getLong("version");
                }
            }
        }
    }

    private static void readOne(
            DataSource dataSource, long tenantId, long orderId)
            throws SQLException {
        String sql = """
            SELECT order_id, status, total_amount, version
            FROM bench_orders WHERE order_id = ? AND tenant_id = ?
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setLong(2, tenantId);
            ps.setQueryTimeout(3);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Thiếu row dự kiến trong data test");
                }
                rs.getString("status");
                rs.getBigDecimal("total_amount");
            }
        }
    }

    private static void touchVersion(
            DataSource dataSource, long tenantId, long orderId)
            throws SQLException {
        String sql = """
            UPDATE bench_orders
            SET version = version + 1
            WHERE order_id = ? AND tenant_id = ?
            """;
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setLong(2, tenantId);
            ps.setQueryTimeout(3);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("UPDATE không khớp row test");
            }
        }
    }

    private static double percentileMs(List<Long> sorted, double fraction) {
        if (sorted.isEmpty()) return Double.NaN;
        int index = Math.max(0,
                (int) Math.ceil(fraction * sorted.size()) - 1);
        return sorted.get(index) / 1_000_000.0;
    }
}
```

Ví dụ cách gọi sau khi khởi tạo `DataSource` bằng pool của ứng dụng test:

```java
// Đo sau khi đã có bước warmup riêng, trên database có dữ liệu đã seed.
var result = JdbcWorkloadProbe.run(dataSource, 16, 2500);
System.out.printf(
    "attempted=%d errors=%d rps=%.1f p50=%.1fms p95=%.1fms p99=%.1fms%n",
    result.attempted(), result.errors(), result.requestsPerSecond(),
    result.p50Ms(), result.p95Ms(), result.p99Ms());
```

### Những giới hạn bắt buộc ghi trong báo cáo

- Đây là **closed-loop**: mỗi worker chờ operation trước hoàn tất rồi mới gọi operation sau. Tăng `workers` không tương đương đặt một arrival rate độc lập.
- `attempted / elapsedSeconds` tính **throughput đã được thử**, gồm cả yêu cầu lỗi; để báo **goodput**, cần riêng `success = attempted - errors` và xác nhận các kết quả “đúng nghiệp vụ”. Một lệnh `SELECT` trả HTTP 200 nhưng dữ liệu sai không được tính là thành công.
- Latency đo từ trước `getConnection()` đến sau khi đọc/ghi xong, vì vậy bao gồm **thời gian chờ pool và thời gian JDBC**, nhưng **không** bao gồm HTTP, deserialize request, serialize response, mạng từ load generator hay side effect khác.
- Mọi mẫu latency được giữ trong RAM và sort sau test; chỉ phù hợp lượt test có kích thước hạn chế. Chạy hàng triệu/billion request nên dùng histogram streaming/công cụ chuyên dụng, tránh tự tạo áp lực heap ở load generator.
- `touchVersion()` là phép ghi giả lập không có kiểm tra nghiệp vụ, dùng trên **database test có thể reset**. Nó không mô phỏng hết transaction thật và có thể làm thay đổi distribution/cache trong quá trình benchmark.
- Dataset generator cũng dùng khóa suy từ `order_id`; hai phân bố dữ liệu và truy cập ở đây được gắn với nhau để ví dụ có thể tái lập. Một workload có tính đại diện hơn phải điều chỉnh độc lập hai phân bố từ telemetry đã tổng hợp.
- Cần đo tỷ lệ lỗi/timeout, không được xóa mẫu chậm hoặc chỉ báo percentile trên yêu cầu thành công. Nếu connection pool quá nhỏ hoặc hệ thống đến ngưỡng, lỗi có thể tăng trong khi p99 của **nhóm thành công** nhìn có vẻ ổn.

## 8. Thiết kế pha thử nghiệm và đường cong tải

Một bài đo chỉ chạy 30 giây ở 16 threads chưa đủ. Cần xác định **điểm đạt SLO, điểm bão hòa và cách hệ thống hồi phục**.

| Pha | Cách thực hiện | Mục đích |
| --- | --- | --- |
| Chuẩn bị | Tạo schema/data/index, cập nhật statistics, kiểm tra tỷ lệ và phân bố | Tránh benchmark sai do dữ liệu không đúng |
| Warmup | Chạy tải vừa phải rồi bỏ metric trong khoảng warmup khỏi kết quả chính | Ổn định JIT, pool, cache và kế hoạch truy vấn |
| Baseline | Chạy mức tải hiện tại theo phân bố thực | So sánh sau thay đổi |
| Step/ramp | Tăng arrival rate hoặc concurrency theo từng nấc, giữ đủ lâu ở mỗi nấc | Tìm ngưỡng p95/p99, error rate và bão hòa |
| Burst | Tăng nhanh tải theo kịch bản đỉnh ngắn | Đo backlog, pool wait và khả năng hồi phục |
| Soak | Giữ tải trong nhiều giờ theo mục tiêu | Phát hiện bloat, memory leak, log growth, GC và suy giảm theo thời gian |
| Recovery | Hạ tải, xem hệ thống thoát backlog; tùy mục tiêu thử failover | Đo khả năng phục hồi sau quá tải/sự cố |

Khi so sánh index A và B, dùng **cùng workload, cùng quy mô dữ liệu, cùng hạ tầng và trạng thái được kiểm soát**; chạy nhiều lần và ghi lại độ biến thiên. Không so một kịch bản cache lạnh với một kịch bản đã cache nóng rồi kết luận index mới giúp nhanh gấp đôi.

### Cache nóng và cache lạnh đều có giá trị

- **Warm cache:** nhiều index/data pages đã ở RAM; phản ánh hệ thống ổn định nếu working set vừa bộ nhớ và truy cập lặp.
- **Cold/recovery cache:** nhiều page chưa được nạp; phản ánh startup, failover hoặc thay đổi working set. Có thể tăng disk I/O và latency rõ rệt.

Không nên xóa cache hệ điều hành trên máy chung hoặc can thiệp vào hệ thống khác để “thử cache lạnh”. Dùng môi trường độc lập, restart có kiểm soát hoặc một phương pháp được đội vận hành chấp thuận. Ghi rõ mức cache đạt được; đừng khẳng định “cold” chỉ vì vừa chạy lệnh nào đó.

## 9. Đo đúng metric ở cả Java và cơ sở dữ liệu

Một API có p99 tăng có thể do chờ pool, khóa DB, network, GC hoặc SQL scan. Cần đo ở các lớp để tìm nút thắt.

| Lớp | Metric cần thu | Câu hỏi |
| --- | --- | --- |
| Bộ phát tải | Requests scheduled/sent/completed, late starts, lỗi phía client, CPU | Công cụ có phát đúng tốc độ đích không? |
| HTTP/API | End-to-end p50/p95/p99, goodput, timeout, status codes | Người dùng trải nghiệm thế nào? |
| Java runtime | CPU, heap, GC pause, thread count, queue depth | Có nghẽn trước khi chạm DB không? |
| Connection pool | Active/idle/pending, acquire time, usage time | Yêu cầu đang đợi pool hay giữ connection quá lâu? |
| JDBC/ORM | SQL count, query duration, N+1, flush/commit time | Một use case thực hiện bao nhiêu SQL và round-trip? |
| DB execution | Plan, rows scanned/returned, buffers, temp files, I/O | SQL dùng index/scan/sort ra sao? |
| Concurrency | Lock waits, deadlocks, retries, transaction duration | Có hotspot/transaction dài hay không? |
| Durability/replication | WAL rate, checkpoints, replication lag, disk free | Tải ghi có đẩy rủi ro sang log/replica không? |

**p95 và p99 không phải trung bình.** Nếu có 10.000 yêu cầu, p99 gần phản ánh mốc mà khoảng 99% mẫu có latency không vượt quá (theo quy ước percentile được dùng); nó không có nghĩa 1% còn lại “không quan trọng”. Các lỗi timeout phải được báo riêng, vì tùy cách đo chúng có thể bị loại khỏi histogram thành công.

Phân tích truy vấn bằng PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount, version
FROM bench_orders
WHERE tenant_id = 123 AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` thực thi câu SQL; ví dụ là SELECT phù hợp để kiểm tra trên môi trường test. Với UPDATE/DELETE, chạy `EXPLAIN ANALYZE` có thể thay đổi dữ liệu; đừng dùng trực tiếp trên production mà không có biện pháp an toàn. Khi workload có nhiều tenant lớn/nhỏ, chạy trên các mẫu tham số **đại diện**, không chỉ một tenant “đẹp”.

Khi đọc execution plan, quan sát loại scan, filter, row estimate so với actual, sort method, temporary files, buffer hits/reads và I/O timing nếu đã bật. Một index mới có thể giúp tenant nóng nhưng làm ghi chậm hơn; đánh giá **cả hệ thống** chứ không chỉ thời gian câu SELECT sau khi tạo index.

## 10. Đọc kết quả và quyết định có tối ưu hay chưa

Không có “số RPS tốt” độc lập với yêu cầu. Đặt **SLO và điều kiện pass/fail trước khi chạy**, chẳng hạn (ví dụ giả định):

```text
Mức tải mục tiêu: 300 arrival requests/giây, chạy ổn định 20 phút
Yêu cầu:
  - tỷ lệ lỗi hạ tầng dưới 0,1%
  - p95 end-to-end dưới 180 ms
  - p99 end-to-end dưới 400 ms
  - không xuất hiện lỗi vi phạm bất biến đơn hàng
  - replica lag và thời gian chờ pool trong ngưỡng vận hành đã chọn
```

Các con số này chỉ minh họa phương pháp đặt điều kiện; không phải mức chuẩn chung cho Java hay PostgreSQL.

Một bảng báo cáo mẫu nên **tránh điền số giả làm kết quả thật**:

| Chỉ số | Baseline | Sau thay đổi | Nguồn |
| --- | --- | --- | --- |
| Kịch bản và data version | Ghi mã phiên bản | Giữ nguyên hoặc ghi khác biệt | Manifest môi trường |
| Arrival rate / sent / completed | Giá trị đo | Giá trị đo | Load generator |
| Goodput và lỗi/timeout | Giá trị đo | Giá trị đo | Client/server traces |
| API p50/p95/p99 | Giá trị đo | Giá trị đo | Histogram/metrics |
| Pool acquire p95/p99 | Giá trị đo | Giá trị đo | Pool metrics |
| DB CPU/I/O, lock wait | Giá trị đo | Giá trị đo | DB monitoring |
| WAL rate/replica lag | Giá trị đo | Giá trị đo | DB/replication |
| Vi phạm bất biến | Số lượng + bằng chứng | Số lượng + bằng chứng | Kiểm tra trạng thái dữ liệu |

Đọc kết quả theo thứ tự:

1. **Bài test có hợp lệ?** Generator có đúng lịch, có lỗi phía client, dữ liệu có đúng phân bố, ứng dụng có hoàn thành đúng công việc?
2. **SLO có đạt ở mức tải mục tiêu?** Cần đánh giá p95/p99, lỗi, goodput và backlog *cùng nhau*.
3. **Hệ thống nghẽn ở đâu?** Pool, SQL, lock, disk, WAL, CPU, GC, network hay dependency ngoài?
4. **Thay đổi có tạo trade-off khác?** Index mới giảm SELECT nhưng tăng chi phí UPDATE, cache giúp p50 nhưng p99 vẫn chịu timeout, batch tăng throughput nhưng transaction dài hơn?
5. **Kết quả có lặp lại được?** Cùng manifest và môi trường, nhiều lần chạy có cho kết quả cùng xu hướng không?

Trước khi kết luận “tối ưu thành công”, kiểm tra **tính đúng đắn**: số đơn không âm nếu invariant yêu cầu, không có booking trùng, không mất outbox event, số hàng cập nhật đúng, không có lỗi idempotency. Performance tốt trên dữ liệu sai không phải hiệu năng đạt yêu cầu.

## 11. Những sai lầm thường khiến benchmark vô nghĩa

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| 100 dòng dữ liệu thay vì hàng triệu | Toàn bộ dữ liệu nằm trong cache, query plan khác | Seed số hàng, kích thước hàng và thống kê đại diện |
| Mọi tenant đều giống nhau | Bỏ sót hot tenant, lệch dữ liệu và tranh chấp | Giữ histogram tenant/key/query thực tế |
| Mọi request đều `SELECT 1` | Không phản ánh JOIN, sort, transaction và WAL | Mô phỏng operation/use case thật |
| Chỉ đọc trang đầu | Bỏ sót trang sâu, filter hiếm và báo cáo | Phân mẫu theo page depth, predicate, số hàng |
| Không có job nền | Thiếu cạnh tranh I/O, lock, vacuum và log | Chạy những background task quan trọng |
| Không warmup hoặc so cold vs warm | JIT/cache và plan thay đổi giữa hai lượt | Quy định warmup/cache state và chạy nhiều lần |
| Chỉ tăng số thread | Không kiểm soát arrival rate hay backlog | Dùng open-loop khi mục tiêu là lưu lượng đến |
| Đếm attempted là successful | Timeout/data corruption bị che | Ghi sent/completed/goodput/error/correctness riêng |
| Chỉ đo trung bình | Bỏ lỡ tail latency và timeout | p95/p99, histogram và error rate |
| Load generator hết CPU | Bài test đo khả năng generator, không phải server | Giám sát generator và phân tán khi cần |
| Sử dụng data production không được bảo vệ | Vi phạm quyền riêng tư và an toàn | Dùng dữ liệu tổng hợp/ẩn danh đúng quy trình |
| Chạy UPDATE benchmark trên production | Tạo dữ liệu sai và khóa thật | Chỉ chạy trên môi trường cách ly có thể reset |

## 12. Bài tập thực hành

### Bài tập 1: dữ liệu đều nhưng traffic lệch

Một bộ đo có 1.000 tenant, mỗi tenant đúng 1.000 đơn và mỗi tenant được chọn với xác suất 0,1%. Thực tế 5 tenant tạo ra 80% yêu cầu. Bài benchmark có nguy cơ bỏ sót điều gì?

**Đáp án:** bỏ sót tenant/khóa nóng, cache và lock contention, mức sử dụng tài nguyên lệch giữa tenant, cũng như khả năng query planner có lựa chọn khác cho tenant nhiều dữ liệu. Phải mô hình hóa phân bố **lưu trữ** và **truy cập** riêng, lấy mẫu theo telemetry.

### Bài tập 2: p99 cải thiện nhưng tỷ lệ lỗi tăng

Trước tối ưu: p99 của nhóm thành công là 300 ms, lỗi 0,1%. Sau tối ưu: p99 của nhóm thành công là 150 ms, lỗi 8%. Có thể coi hệ thống nhanh hơn không?

**Đáp án:** không. Nhiều request chậm có thể đã thành timeout và bị loại khỏi histogram. Phải báo sent/completed/goodput, lỗi, timeout và latency của tất cả request theo chính sách đo; nếu vượt error budget thì thay đổi không đạt.

### Bài tập 3: concurrency không phải RPS

Một script có 10 worker, mỗi worker gọi SQL và đợi phản hồi rồi mới gọi tiếp. Khi DB chậm, số RPS giảm còn một nửa. Điều này chứng minh hệ thống chịu được arrival rate ban đầu không?

**Đáp án:** không. Đây là closed-loop với tốc độ phát tự giảm khi server chậm. Nếu mục tiêu là tải đến cố định, cần mô hình open-loop và ghi backlog/late starts, đồng thời tránh coordinated omission.

### Bài tập 4: chọn chỉ số để tối ưu

API p99 tăng vào giờ cao điểm. SQL duration p95 chỉ 8 ms, nhưng pool pending tăng, thời gian mượn connection p99 lên 900 ms. Nên chỉ thêm index trước không?

**Đáp án:** chưa có đủ bằng chứng. Cần điều tra connection được giữ quá lâu (HTTP bên trong transaction, ORM lazy loading, connection leak, transaction dài) và cấu hình pool/DB. Thêm index chỉ có ích khi query plan là nút thắt được đo.

### Bài tập 5: benchmark UPDATE nhưng bỏ kiểm tra nghiệp vụ

Trong production, đặt chỗ dùng transaction đọc tồn, giảm số lượng có điều kiện, insert booking và outbox. Benchmark chỉ chạy `UPDATE version=version+1` rồi báo throughput cao. Có thể dùng kết quả đó để chọn kích thước DB production không?

**Đáp án:** không trực tiếp. Workload giả bỏ qua nhiều SQL, index update, transaction boundary, WAL/commit, lock và tính đúng đắn. Cần bổ sung transaction tương đương, kiểm tra kết quả, retries và contention thực tế.

### Checklist chuẩn bị trước khi công bố kết quả

- Đã ghi rõ **câu hỏi benchmark**, workload, SLO, cấu hình và phạm vi đo chưa?
- Dữ liệu có đúng số hàng, kích thước, tenant, độ lệch, lịch sử và trạng thái/NULL/quan hệ quan trọng chưa?
- Phân bố **traffic và tham số** có phản ánh hot keys, filter, page depth, read/write mix và background tasks chưa?
- Có tách closed-loop với open-loop, kiểm soát rate, think time, concurrency và coordinated omission chưa?
- Đã warmup, kiểm soát cache, kiểm tra CPU của bộ phát, lập lại nhiều lượt và lưu manifest môi trường chưa?
- Có đo p50/p95/p99, goodput, lỗi, backlog, pool wait, SQL plan, lock wait, WAL và replica lag chưa?
- Có kiểm tra correctness, transaction/idempotency, dữ liệu test an toàn và khả năng reset sau từng lượt không?
- Kết luận có dựa trên mức tải đạt SLO và trade-off, không chỉ một con số RPS đẹp không?

**Kết luận:** Benchmark persistence đáng tin cậy không bắt đầu từ công cụ phát tải, mà bắt đầu từ **mô hình dữ liệu và truy cập đủ đại diện**. Cần giữ đúng độ lệch tenant/khóa, tỷ lệ đọc–ghi, transaction, mức đồng thời, cache và hạ tầng; sau đó đo cùng lúc latency đuôi, throughput thành công, lỗi và độ đúng nghiệp vụ. Khi các điều kiện thử và dữ liệu được ghi chép, kiểm chứng và lặp lại được, kết quả mới đủ giá trị để quyết định thêm chỉ mục, chỉnh query, tăng pool, đổi chiến lược transaction hoặc mở rộng database.
