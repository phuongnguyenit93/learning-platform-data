# Đặt giới hạn truy vấn, tải đồng thời và tài nguyên mỗi tenant

## 1. Bài toán: một tenant có thể làm cả cụm chậm dù không đọc dữ liệu của ai khác

Một nền tảng SaaS có 300 doanh nghiệp cùng dùng cụm NoSQL. Mỗi doanh nghiệp là một **tenant**. API Java hỗ trợ tìm đơn hàng, xuất báo cáo và cập nhật tồn kho.

Trong giờ bình thường:

```text
Tenant A:     80 requests/s, chủ yếu point lookup
Tenant B:    120 requests/s, nhiều cập nhật nhỏ
Tenant C:     30 requests/s, báo cáo tổng hợp
Các tenant còn lại: 1.500 requests/s
```

Bất ngờ, tenant C chạy 50 báo cáo toàn năm cùng lúc. Mỗi báo cáo quét hàng triệu documents, gọi nhiều shards, dùng nhiều RAM để sắp xếp và giữ connection lâu. CPU một data node lên 100%; `GET /orders/{id}` của tenant A tăng từ p99 40 ms lên 2 giây.

Không hề có lỗi truy cập chéo dữ liệu: C chỉ đọc records của C. Nhưng đây là **noisy-neighbor problem** — một tenant chiếm tài nguyên dùng chung, làm tenant khác không đạt SLO.

Giải pháp không phải đơn giản “thêm cache” hoặc “nâng toàn bộ cluster”. Cần quản lý đồng thời:

- Tenant được gửi bao nhiêu yêu cầu trong một khoảng thời gian?
- Có bao nhiêu thao tác cùng chạy và cùng chờ?
- Mỗi truy vấn được phép quét/trả bao nhiêu dữ liệu, chạy trong bao lâu?
- Tenant có thể tiêu thụ bao nhiêu CPU, I/O, throughput, bộ nhớ, connection và chi phí?
- Khi cụm quá tải, ai được ưu tiên, ai phải đợi và ai bị từ chối?
- Làm sao đo **tính công bằng**, không chỉ throughput tổng?

Bài học **Database No SQL → Vận hành cụm → Đặt giới hạn truy vấn, tải đồng thời và tài nguyên mỗi tenant** xây dựng câu trả lời từ thiết kế chính sách đến triển khai Java, cấu hình sản phẩm, kiểm thử và vận hành.

---

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **rate limit**, **concurrency limit**, **queue limit**, **query timeout** và **resource quota**.
2. Tạo chính sách giới hạn dựa trên tenant đã được xác thực và tier dịch vụ.
3. Hiểu token bucket, fixed/sliding window, weighted admission và fair queuing.
4. Thiết kế các **bulkhead** riêng theo tenant, loại tác vụ và tài nguyên nguồn.
5. Đặt hạn mức số bản ghi, số trang, vùng quét, byte trả về, thời gian xử lý và tổng chi phí truy vấn.
6. Phân biệt giới hạn tại HTTP gateway, Java worker pool, NoSQL client và database server.
7. Bảo vệ cả các đường `Query`, aggregation, scan, bulk write, export, CDC và background job.
8. Xử lý deadline, cancellation, retry, lỗi throttle và write outcome chưa biết một cách đúng đắn.
9. Thiết kế kiểm soát cho MongoDB, Cassandra, DynamoDB, Redis và Elasticsearch/OpenSearch mà không giả định mọi sản phẩm có native per-tenant quota.
10. Đánh giá trade-off giữa fairness, throughput, độ trễ, chi phí và tính đúng đắn dữ liệu.
11. Kiểm thử với tenant nóng, phân phối tải lệch, node mất, backfill và backup.
12. Xây dashboard, runbook và cơ chế điều chỉnh quota có kiểm soát.

## 3. Ba ranh giới phải giữ: bảo mật, hiệu năng và chi phí

Một hệ multi-tenant có ít nhất ba loại cô lập:

| Ranh giới | Câu hỏi | Biện pháp thường dùng |
| --- | --- | --- |
| **Bảo mật** | Tenant A có thể xem/sửa dữ liệu B không? | Tenant-scoped keys, AuthZ, least privilege |
| **Hiệu năng** | Tải A có làm p99 của B vượt SLO không? | Rate/concurrency budgets, fairness, bulkheads |
| **Chi phí** | Ai trả chi phí của scan, export, index, storage? | Metering, quotas, chargeback, tier policies |

Phân quyền đúng **không bảo đảm** công bằng tài nguyên. Ngược lại, rate limiter tốt không bảo đảm truy vấn có tenant predicate. Cần duy trì cả ba ranh giới.

### 3.1. Tenant context phải đến từ nguồn đáng tin

Ví dụ request:

```http
GET /reports?tenantId=tenant-big
Authorization: Bearer token-of-tenant-small
```

Không được lấy `tenantId` tùy ý từ URL để chọn quota rộng hơn. Cần:

```text
Verified subject/session
  -> Validate membership và active tenant
  -> Resolve plan/tier và policy revision
  -> Apply tenant ID to authorization và quota
  -> Create a scoped query
```

Một user thuộc nhiều tenants vẫn có quota tương ứng với **active tenant được xác minh**.

## 4. Bảng phân biệt các cơ chế giới hạn

| Cơ chế | Giới hạn cái gì? | Có bảo vệ điều gì? | Không bảo vệ được nếu đứng riêng |
| --- | --- | --- | --- |
| Rate limit | Requests / tokens / thời gian | Bùng nổ tốc độ gọi | 1 query giữ tài nguyên 1 giờ |
| Concurrency limit | In-flight operations | Pool, worker, backend saturation | Tổng calls mỗi ngày |
| Queue limit | Số chờ và wait budget | Rò bộ nhớ, chờ vô hạn | Query CPU quá đắt |
| Query timeout | Thời gian thực thi/chờ | Truy vấn kéo dài | Burst hàng nghìn query ngắn |
| Result limit | Số items/bytes trả về | Network, serialization | Scan lớn trước khi limit |
| Scan/cost limit | Dữ liệu được đọc hoặc tài nguyên ước lượng | Expensive query | Hot partition nếu estimator sai |
| Storage quota | Dung lượng lưu của tenant | Chi phí, disk pressure | Peak read/write QPS |
| Per-tenant reserved share | Khả năng phục vụ tối thiểu | Fairness | Waste nếu đặt tĩnh và không work-conserving |
| Global admission | Tổng tải lên cụm | Bảo vệ hệ chung | Một tenant chiếm hết nếu không có local limits |
| Background-job budget | Backfill, export, index, repair | Bảo vệ traffic chính | Foreground traffic không giới hạn |

**Một policy vận hành đúng thường kết hợp nhiều cơ chế**, không chọn chỉ một.

## 5. Tư duy về ngân sách tài nguyên

Mỗi logical operation có thể tiêu tốn một vector:

\[
\mathbf{c} =
(c_{\text{request}},
c_{\text{CPU}},
c_{\text{read}},
c_{\text{write}},
c_{\text{memory}},
c_{\text{network}},
c_{\text{duration}})
\]

Ví dụ:

```text
GET order by PK:
  1 operation
  low read cost
  small response

Export 100.000 orders:
  1 HTTP request
  very high read + network + memory/streaming cost
```

Nếu chỉ đếm HTTP request, hai tác vụ trên có cùng “giá 1 request” dù chi phí khác xa.

### 5.1. Từ request quota tới cost-aware quota

Một policy nhiều tầng có thể dùng:

```text
1 point read          = 1 credit
1 bounded range page  = 3 credits
1 aggregation report  = 20 credits
1 export task         = 100 credits + metering theo bytes
```

Các trọng số chỉ **minh họa**. Cần hiệu chỉnh bằng metrics thực và rủi ro mỗi query shape. Không coi 20 credits tương đương 20 RCUs DynamoDB hay 20 ms CPU nếu chưa có phép quy đổi đã kiểm chứng.

### 5.2. Không được dùng ước lượng như bằng chứng chính xác

Chi phí có thể thay theo selectivity, indexes, partition sizes và cache state. Có thể dùng **estimate trước khi nhận** và **actual metering sau khi thực thi**, cộng thêm hard limits để chặn truy vấn phát sinh vượt xa dự báo.

## 6. Rate limit là điều tiết tốc độ, không phải số thao tác đang chạy

Giả sử tenant A được phép:

```text
100 requests/second
```

Nếu mỗi request chạy 10 giây, 100 RPS vẫn có thể tạo khoảng 1.000 in-flight operations ở trạng thái ổn định, tùy mô hình arrival.

Vì vậy:

\[
L \approx \lambda W
\]

Theo Little's Law trong hệ ổn định:

- \(\lambda\): throughput trung bình.
- \(W\): latency trung bình end-to-end.
- \(L\): số thao tác tồn tại đồng thời trung bình.

**Giới hạn RPS không suy ra concurrency an toàn** khi request duration rất dài hoặc queueing tăng.

### 6.1. Ví dụ kết hợp

```text
tenant A:
  rate <= 100 requests/s
  concurrency <= 20 in-flight queries
  max queue wait <= 50 ms
  max page size <= 100 items
  max read deadline <= 2 seconds
```

Chỉ sau khi biết backend capacity và SLO mới chọn giá trị thật.

## 7. Fixed window: dễ triển khai nhưng có burst ở ranh giới

Với quota 100 requests/phút:

```text
12:00:00–12:00:59 -> 100 requests được phép
12:01:00–12:01:59 -> quota làm mới
```

Một client có thể gửi 100 requests lúc 12:00:59 và 100 requests lúc 12:01:00, tức **200 requests trong khoảng 2 giây quanh ranh giới**.

### 7.1. Không nên quảng bá fixed window là “100 requests trong mọi 60 giây”

Đó là cam kết mạnh hơn. Fixed calendar window không bảo đảm bất kỳ khoảng trượt nào cũng chứa tối đa 100 requests.

### 7.2. Ưu nhược điểm

- Dễ đếm và quản lý.
- Có thể dùng atomic counter với TTL.
- Có burst ở biên.
- Cần quyết định đồng hồ/window anchoring và failover behavior.
- Không bảo vệ concurrent long-running queries.

## 8. Sliding window

Sliding window cố theo dõi số requests trong **khoảng thời gian trượt** gần hiện tại, giảm hiện tượng burst tại ranh giới fixed window.

Lựa chọn triển khai:

- Sliding log lưu timestamps, chính xác hơn nhưng tốn bộ nhớ/CPU.
- Sliding counter gần đúng bằng các buckets và trọng số.
- Dùng cửa sổ nhỏ nhiều buckets nếu cần phân giải cao.

### 8.1. Chi phí lưu trạng thái

Nếu mỗi request tạo một record timestamp trong Redis cho hàng triệu tenants, limiter tự có thể trở thành bottleneck. Dùng data structures và cleanup phù hợp workload.

### 8.2. Không có bảo đảm tuyệt đối trong mọi failure mode

Distributed replicas, clock skew, network partitions và retry có thể gây oversubscription hoặc fail-closed tùy implementation. Phải nêu giới hạn độ chính xác.

## 9. Token bucket: cho phép burst có giới hạn

Token bucket có:

- **Capacity \(B\):** số token tối đa tích lũy.
- **Refill rate \(r\):** số token bổ sung mỗi giây.
- **Operation cost \(c\):** token tiêu thụ mỗi call.

Quy tắc khái niệm:

\[
T_{\text{new}} =
\min(B,T_{\text{old}}+r\Delta t)
\]

Cho một operation khi \(T_{\text{new}}\ge c\), sau đó trừ \(c\).

### 9.1. Ví dụ

```text
Capacity B = 200 credits
Refill r  = 50 credits/s

Trạng thái ban đầu: 200
Một burst 150 point reads: cho phép nếu mỗi read=1
Trạng thái còn: 50
Sau 2 giây không dùng: hồi phục về 150
```

Token bucket cho phép burst trong phạm vi \(B\) nhưng giữ long-term average gần \(r\), nếu thuật toán/clock/atomicity được triển khai đúng.

### 9.2. Cẩn thận khi operation cost lớn hơn bucket

Nếu export có cost 300 nhưng capacity chỉ 200, nó **không bao giờ được nhận**, trừ khi có workflow reservation hoặc bucket riêng. Cần policy cho những tác vụ lớn, không ngầm chuyển chúng thành miễn phí.

## 10. Leaky bucket và kiểm soát nhịp thực thi

Leaky-bucket-style scheduler có thể cho tasks ra khỏi hàng theo một nhịp gần ổn định, giúp tránh burst xuống backend.

```text
Incoming bursts -> bounded queue -> controlled dispatch rate -> DB
```

Nhưng nếu hàng chờ không giới hạn, một tenant có thể tạo hàng triệu tasks chờ, chiếm RAM và tăng latency. Vì vậy phải có:

```text
max queue length
max queue wait
request deadline
cancellation handling
per-tenant queue allowance
```

### 10.1. Rate limiter trước hay sau queue?

- Admit trước queue: ít bị backlog không hợp lệ; từ chối sớm.
- Queue trước limiter: có thể làm hàng đợi phình.
- Một scheduler có fair queues có thể chờ theo chính sách, nhưng vẫn cần admission và hard caps.

Phải định nghĩa rõ “accepted” nghĩa là **đã bắt đầu xử lý** hay chỉ **đã nhận job để thực hiện sau**.

## 11. Concurrent in-flight limit: kiểm soát saturation

Một tenant có thể chỉ được chạy tối đa 8 truy vấn backend cùng lúc:

```text
Tenant A: 8 active DB calls
Tenant B: 8 active DB calls
Tenant C: 8 active DB calls
Global:   100 active DB calls across service
```

Cần xem concurrency ở **nhiều lớp**:

- HTTP requests đang xử lý.
- Workers trong executor.
- Database client pool acquisitions.
- Commands thực sự in-flight ở driver.
- Truy vấn còn đang chạy trên server dù client đã timeout.

### 11.1. Không nhầm HTTP concurrency với DB concurrency

Một HTTP request có thể fan-out đến 20 shard queries. Dù HTTP concurrency chỉ 10, DB concurrency có thể cao hơn đáng kể.

### 11.2. Điều kiện chọn limit

Giới hạn phải cân bằng:

- Query mix/cost.
- Backend CPU/IO/network.
- SLO và timeout.
- Queue size.
- Replica/partition placement.
- Tối đa connection/in-flight của SDK.
- Headroom khi mất một node.

## 12. Global bulkhead và per-tenant bulkhead cần cùng tồn tại

Một chỉ có global semaphore 100 slots:

```text
Tenant A tới trước: 100 active requests
Tenant B tới sau:   0 slots
```

Global pool vẫn trong ngưỡng 100 nhưng **B bị starvation**.

Nếu chỉ có per-tenant limit 20 mà có 100 tenants:

```text
100 tenants × 20 = 2.000 potential queries
```

thì vẫn quá tải database.

Mô hình đúng hơn:

```text
Per-tenant concurrency cap
         AND
Global concurrency cap
         AND
Per-operation/source capacity cap
```

### 12.1. Hai cách phân bổ

- **Hard partitions:** đặt slot riêng mỗi tenant, dễ cô lập nhưng lãng phí khi tenant không dùng.
- **Shared pool có fair admission:** tenant nhàn trả lại capacity cho người khác, nhưng phải có minimum/maximum và chính sách tránh starvation.

Quyết định phụ thuộc số tenants, tiers và SLO.

## 13. Java: bulkhead theo tenant và toàn dịch vụ

Mẫu Java dùng `Semaphore` và danh sách tenants đã được đăng ký:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;

public final class QueryAdmissionGate {
    private final Semaphore global;
    private final Map<String, Semaphore> tenantSlots;

    public QueryAdmissionGate(
            int globalMax,
            Map<String, Integer> tenantLimits) {
        if (globalMax <= 0) {
            throw new IllegalArgumentException("globalMax");
        }

        this.global = new Semaphore(globalMax, true);

        Map<String, Semaphore> local = new HashMap<>();

        tenantLimits.forEach((tenantId, max) -> {
            if (max == null || max <= 0) {
                throw new IllegalArgumentException("tenant max");
            }
            local.put(tenantId, new Semaphore(max, true));
        });

        this.tenantSlots = Map.copyOf(local);
    }

    public <T> T execute(
            TenantContext context,
            Callable<T> databaseWork) throws Exception {

        Semaphore tenant = tenantSlots.get(context.tenantId());
        if (tenant == null) {
            throw new SecurityException("Unknown tenant");
        }

        if (!tenant.tryAcquire()) {
            throw new TenantBusyException();
        }

        boolean acquiredGlobal = false;
        try {
            acquiredGlobal = global.tryAcquire();
            if (!acquiredGlobal) {
                throw new SharedCapacityBusyException();
            }
            return databaseWork.call();
        } finally {
            if (acquiredGlobal) {
                global.release();
            }
            tenant.release();
        }
    }

    public static final class TenantBusyException
            extends RuntimeException {}

    public static final class SharedCapacityBusyException
            extends RuntimeException {}
}
```

`TenantContext` phải do lớp xác thực đáng tin tạo. Ví dụ này giả định có một record/context chứa `tenantId()` được xác minh.

### 13.1. Nó bảo vệ được gì?

- Không một tenant nào vượt số concurrent calls đã đăng ký **trong một JVM**.
- Tổng concurrent `databaseWork` trong JVM không vượt global cap.
- Không có queue chờ vô hạn trong ví dụ (fail fast).
- `finally` trả permits dù operation ném exception.

### 13.2. Nó không bảo đảm điều gì?

- Không bảo đảm quota **toàn cluster** khi có 20 instances Java.
- Không bảo đảm sự công bằng theo arrival order giữa tất cả tenants.
- Không giới hạn CPU/bytes/query scan của một call.
- Không tự cancel server-side query sau HTTP timeout.
- Không tự update quota khi tenant đổi plan.
- Không tự giải quyết tenant có hàng triệu IDs: phải quản lý map lifecycle hoặc dùng tenant registry.

### 13.3. Fair semaphore không phải fair scheduler đa tenant

Tham số `true` áp fairness đối với những threads đợi **trên chính semaphore** theo cơ chế Java. Ở ví dụ dùng nonblocking `tryAcquire()` nên không suy ra fairness toàn cụm. Nếu cần weighted fairness, dùng scheduler có per-tenant queues và chính sách chọn công việc.

## 14. Phân biệt timeout, deadline và queue wait

Một API có ngân sách tổng 800 ms:

```text
Ingress/authz:              50 ms
Admission/queue wait:       60 ms
DB client pool wait:        40 ms
Network + server execution: 500 ms
Serialization:              40 ms
Safety margin:             110 ms
```

Nếu chỉ đặt server query timeout 800 ms, toàn request có thể vượt xa 800 ms do các thành phần khác.

### 14.1. Deadline end-to-end

Dùng một **deadline** có thời điểm hết hạn; từng tầng dùng thời gian còn lại:

```text
remaining = deadline - monotonic_now
```

Nếu remaining nhỏ hơn thời gian tối thiểu cần thiết, từ chối sớm thay vì xếp hàng thêm.

### 14.2. Timeout không tự hủy công việc ở server

Khi HTTP client ngừng chờ, NoSQL engine có thể vẫn tiếp tục query hoặc write. Phải dùng cancellation/operation kill đúng capability và vẫn có hard source limits.

### 14.3. Write timeout có thể là kết quả chưa biết

Nếu server commit write rồi ACK mất, timeout không chứng minh write thất bại. Không retry bằng idempotency key mới; cần stable operation ID, conditional semantics và authoritative outcome lookup.

## 15. Query budget không chỉ là `LIMIT 100`

Một truy vấn:

```text
SELECT-like:
  Scan 10.000.000 records
  Filter status = PAID
  Return first 100
```

Có thể **trả 100 records nhưng đã quét 10 triệu** nếu index/partition design không hỗ trợ predicate.

Vì vậy phải tách:

| Budget | Hạn chế |
| --- | --- |
| Max returned rows | Kích thước response |
| Max scanned documents/items | Backend work |
| Max shards/partitions touched | Fan-out/routing |
| Max execution duration | Thời gian |
| Max result bytes | Network/serialization |
| Max intermediate group cardinality | Memory/aggregation |
| Max sort/aggregation memory | Spill/heap pressure |
| Max read/write capacity units | Cost/throttle |
| Max pages per logical request | Pagination amplification |
| Max retries and attempts | Amplified workload |

**`LIMIT` là một phần guardrail, không phải tổng ngân sách tài nguyên.**

## 16. Dùng query catalog thay vì raw NoSQL DSL

Một API cho client tự gửi query:

```json
{
  "collection": "orders",
  "filter": {"$or": [{"status": "PAID"}, {}]},
  "sort": {"anyField": 1},
  "limit": 1000000
}
```

gây rủi ro:

- Injection/bypass tenant scope.
- Scan/aggregation không giới hạn.
- Expose dữ liệu không được phép.
- CPU/IO/heap spike.
- Index plan không kiểm soát.

### 16.1. Query templates/allowlist

Một API an toàn hơn có thể cho:

```text
orders.getById
orders.listRecentByStatus
orders.listByCustomer
orders.aggregateDailyRevenue
```

Mỗi template xác định:

- Tenant predicate/partition key.
- Allowed filters.
- Allowed sort.
- Maximum page size.
- Required indexes.
- Maximum time/cost.
- Permission.
- Result projection.
- Rate/concurrency cost weight.

### 16.2. Advanced search DSL cần parser và cost guard

Nếu sản phẩm bắt buộc cho truy vấn tự do, hãy parse thành AST có giới hạn depth/operators/fields, gắn tenant scope ở server, kiểm tra planning và **chặn query vượt budget trước khi chạy** khi có thể.

Không để client cung cấp raw `$where`, arbitrary scripts, wildcard regexp hoặc unbounded traversal trong đường public theo mặc định.

## 17. Pagination để tránh truy vấn và response lớn

Một endpoint:

```http
GET /orders?limit=100000
```

không nên cho 100.000 items chỉ vì tenant có nhiều records.

Gợi ý:

```text
default page size: 50
maximum page size: 200
cursor TTL: 15 minutes
maximum pages per exported interactive session: policy-defined
```

Các số chỉ là ví dụ.

### 17.1. Keyset/cursor thay OFFSET rất sâu khi phù hợp

Với MongoDB:

```text
tenantId = trustedTenant
AND (createdAt, _id) < cursor
SORT createdAt DESC, _id DESC
LIMIT 50
```

Cần chỉ mục phù hợp, stable tie-breaker, bảo vệ cursor tenant/filter scope và xử lý updates giữa các trang. Keyset không tự tạo snapshot nhất quán khi dữ liệu thay đổi.

### 17.2. Cursor cũng tiêu tài nguyên

Một server-side cursor giữ state, snapshot hoặc connections có thể tốn tài nguyên. Đặt idle timeout, batch size, lifecycle cleanup và giới hạn cursors đồng thời mỗi tenant nếu backend hỗ trợ.

## 18. Giới hạn aggregation và group cardinality

Một truy vấn:

```text
Group by userId + minute + productId
across a year of event logs
```

có thể sinh hàng triệu groups, khiến memory tăng mạnh và spill ra disk.

Cần guard:

- Allowed grouping dimensions.
- Maximum date range.
- Maximum buckets/groups.
- Preaggregation/rollup cho báo cáo nặng.
- Time and memory constraints.
- Maximum source documents/read bytes.
- Async jobs cho báo cáo lớn.
- Per-tenant report concurrency limit.

### 18.1. `allowDiskUse` không phải cách sửa quyền dùng RAM

Cho phép engine spill xuống disk có thể giúp một aggregation hoàn tất nhưng chuyển áp lực sang I/O và làm tenants khác chậm hơn. Không bật vô hạn như thay cho query design/cost budget.

### 18.2. Truy vấn cross-shard

Scatter–gather tác động nhiều shards; một report của tenant có thể tiêu cluster-wide resources. Tenant targeting/shard key và query shape cần được đo, không chỉ giới hạn số documents kết quả.

## 19. MongoDB: những guardrail hữu ích

Đối với MongoDB, có thể xem:

- `maxTimeMS` cho những operations hỗ trợ.
- `limit` và `batchSize` cho cursors.
- Query shape/index design và `explain` trong môi trường được phép.
- Bounded aggregation pipelines và memory/spill policy.
- Connection pool sizing và wait queue behavior.
- Shard targeting.
- Read preference/concern và write concern theo business.
- Rate/concurrency ở ứng dụng hoặc gateway.

### 19.1. `maxTimeMS` không thay tổng deadline

`maxTimeMS` là một cơ chế hạn chế thời gian server-side cho những operations phù hợp, nhưng **không tự bao gồm mọi thời gian chờ connection pool, DNS/TLS, retries hoặc serialization**. Server interruption có thể xảy ra tại những điểm kiểm tra; không hứa request ngừng chính xác ở millisecond đã đặt.

### 19.2. Java MongoDB point và list queries

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Sorts.*;

public final class TenantOrderQueries {
    private final MongoCollection<Document> orders;

    public TenantOrderQueries(
            MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public FindIterable<Document> recentOrders(
            String trustedTenantId,
            String status,
            int requestedLimit) {

        int pageSize = Math.min(
            Math.max(requestedLimit, 1), 100);

        return orders.find(and(
                eq("tenantId", trustedTenantId),
                eq("status", status)))
            .sort(descending("createdAt", "_id"))
            .limit(pageSize)
            .batchSize(50)
            .maxTime(500, TimeUnit.MILLISECONDS);
    }
}
```

**Đây là code minh họa**, không phải toàn bộ AuthZ: service phải xác minh membership, permission và status đầu vào; wrapper cần quản lý cursor lifecycle và kết quả theo contract.

### 19.3. Không dùng timeout để “chữa” index bị thiếu

Nếu `maxTimeMS` luôn được chạm, cần xem query plan, index, scan volume, shard routing và workload. Timeout chỉ giới hạn thiệt hại; không biến truy vấn tốn 5 giây thành truy vấn 50 ms.

## 20. MongoDB multi-tenant: quota không tự xuất hiện từ `tenantId`

Một shared MongoDB collection có thể chứa records của hàng nghìn tenants. MongoDB index theo `tenantId` có ích cho targeting, nhưng **không tự giới hạn tenant A ở 200 queries/second**.

Giới hạn đó thường phải thực thi ở:

```text
API gateway
Java admission layer
Query service
Dedicated tenant resource deployment
```

với quan sát source-level query cost.

### 20.1. Query planner và `explain`

`explain`/profiler có thể giúp phân biệt:

```text
COLLSCAN vs IXSCAN
docsExamined vs returned
sort stage / spill
shards targeted
```

Nhưng diagnostic queries cũng có chi phí và có thể cần quyền riêng. Không cho user bất kỳ tùy ý gọi `explain` trên production cluster.

### 20.2. Kiểm tra index theo tenant tier

Một query chạy nhanh cho tenant nhỏ có thể scan hàng triệu records của tenant lớn. Benchmark phải có datasets/skew thực tế, không chỉ tập tenant mẫu rất nhỏ.

## 21. Cassandra: partition budget và giới hạn paging

Cassandra yêu cầu thiết kế table theo access pattern và partition key. Một truy vấn có partition key đúng có thể hiệu quả, nhưng **partition quá rộng/hot** vẫn gây tail latency.

Cần guard:

- Partition size và number of rows per partition theo data model.
- Query bắt buộc đủ key fields.
- Page size.
- Max pages/time/bytes per API call.
- Client request timeout và driver in-flight/pool limits.
- Tenant-aware admission trước CQL.
- Compaction/tombstone/repair overhead.
- Consistency level đúng yêu cầu.

### 21.1. CQL paging không phải hard cap tổng dữ liệu

Page size hướng dẫn lượng dữ liệu trong một page; ứng dụng có thể tiếp tục fetch cho tới khi quét hàng triệu rows. Cần giới hạn tổng số pages/bytes và deadline logical query.

### 21.2. `LIMIT` không giới hạn mọi I/O

Tombstones, partition layout và filtering có thể làm công việc thực lớn hơn số rows trả về. Chọn schema và partition strategy đúng; không chỉ tăng timeout.

### 21.3. Role permission khác resource quota

Cassandra permissions thường áp theo keyspace/table/resource. Một shared table role không mặc nhiên có per-tenant RPS/CPU quota; enforcement cần ở application/proxy hoặc topology chuyên biệt.

## 22. DynamoDB: RCU, WCU và token/credit budget

DynamoDB có mô hình capacity dành cho reads/writes tùy API, item size, consistency và capacity mode.

Một số khái niệm:

- **RCU/read request units:** đọc dữ liệu theo size/consistency và service semantics.
- **WCU/write request units:** ghi dữ liệu theo size và service semantics.
- **Provisioned vs on-demand capacity:** hành vi giới hạn và scaling khác nhau.
- **Throttling:** hệ từ chối hoặc trì hoãn phục vụ vượt một số capacity/partition limits.
- **GSI:** index access có chi phí/capacity và hạn mức riêng theo mode.

**Không xem một `GetItem` luôn có chi phí đúng một đơn vị**, hoặc `Scan` là cách rẻ để lọc tenant.

### 22.1. Cost quota phía ứng dụng

Ví dụ:

```text
tenant A:
  5.000 read credits/minute
  1.000 write credits/minute

tenant B:
  50.000 read credits/minute
  10.000 write credits/minute
```

Credits là đơn vị chính sách nội bộ. Có thể điều chỉnh theo `ConsumedCapacity` thực tế, nhưng phải xử lý latency ghi nhận/thiếu thông tin và retry attempts. Không suy những con số trên là RCU/WCU chính thức của AWS.

## 23. DynamoDB: `Limit`, `Query`, `Scan` và filter

Trong DynamoDB, `Query` nên hướng tới partition key được định danh rõ. Một `FilterExpression` được áp sau khi service đọc items theo key condition, nên **ít kết quả trả về không đồng nghĩa ít read capacity**.

Một Query có giới hạn số items evaluated hoặc kích thước trang theo service, rồi trả `LastEvaluatedKey` khi còn dữ liệu. API Java cần đặt:

- Target partition key gắn verified tenant.
- Max page size/number of pages.
- Total read credit budget.
- Deadline và retry budget.
- Projection cần thiết.
- Quyền đọc index/table phù hợp.

### 23.1. Quota theo tenant không mặc nhiên là account-wide capacity

DynamoDB native throttling có thể dựa trên table/index/partition/capacity. Một table shared giữa tenants không tự cho mỗi tenant một ngân sách độc lập. Java service phải **accounting và admission theo tenant** nếu muốn product-tier quota.

### 23.2. Hot partition

Một tenant có thể dồn traffic vào một partition key. Tăng table capacity toàn cục chưa chắc loại bỏ giới hạn của hot partition. Thiết kế key distribution, query model, batching và client backoff có thể quan trọng hơn.

## 24. IAM `LeadingKeys` và capacity limit là hai vấn đề

Một số policy IAM có thể sử dụng điều kiện `dynamodb:LeadingKeys` để giới hạn phạm vi partition keys tùy operation và schema.

Cơ chế này giải quyết một phần **security scope**. Nó không phải per-tenant CPU/throughput scheduler.

Đồng thời, IAM control có thể không bao phủ mọi `Scan`, GSI, multi-key và admin operation giống nhau; phải kiểm tra policy đúng theo API và key schema thực tế.

**Không nới IAM để khắc phục throttling, và không dựa vào throttling để thay authorization.**

## 25. Redis: phân biệt memory quota, ACL và workload limiter

Redis có thể dùng làm:

1. Cache/read model.
2. Shared counter store cho rate limiting.
3. Queue hoặc session store.
4. Một data store chính với durability policy riêng.

Các giới hạn Redis thường như memory/eviction/client connections mang tính instance/cluster theo deployment, **không tự có per-tenant quota** nếu tenants dùng chung namespace và user.

### 25.1. ACL là bảo mật, không phải quota

Redis ACL có thể giới hạn lệnh và key patterns. Một user chỉ được `GET tenant:A:*` vẫn có thể gửi rất nhiều `GET` nếu application không có rate limit.

### 25.2. Chú ý heavy commands và scripts

Commands quét nhiều keys hoặc Lua scripts chạy lâu có thể ảnh hưởng responsiveness của Redis. Không cho tenant gọi raw Redis commands/procedures không kiểm soát qua API public.

### 25.3. Redis `SCAN` không phải “scan không tốn tài nguyên”

`SCAN` chia iteration theo cursor và `COUNT` là hint, nhưng gọi lặp toàn keyspace vẫn tốn CPU/network. Cần giới hạn tổng iterations, duration và tenant namespace.

## 26. Redis Lua: ví dụ atomic fixed-window limiter

Đây là ví dụ **giới hạn số operation theo tenant trong một cửa sổ neo ở request đầu tiên**, không phải distributed concurrency control.

```lua
-- KEYS[1] = scoped quota key từ trusted tenant
-- ARGV[1] = số operation tối đa
-- ARGV[2] = thời lượng cửa sổ (milliseconds)
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])

if not limit or limit < 1 or not windowMs or windowMs < 1 then
    return redis.error_reply("invalid limiter arguments")
end

local count = tonumber(redis.call("GET", KEYS[1]) or "0")

if count >= limit then
    return 0
end

local newCount = redis.call("INCR", KEYS[1])

if newCount == 1 then
    redis.call("PEXPIRE", KEYS[1], windowMs)
end

return 1
```

### 26.1. Ưu điểm

- Kiểm tra và tăng counter thực thi nguyên tử trong một Lua script trên Redis node chứa key.
- State có TTL tự cleanup.
- Nhiều Java service instances có thể dùng cùng key để chia sẻ một quota.
- Nguyên lý dễ minh họa và test.

### 26.2. Giới hạn

- Fixed window anchored không bảo đảm mọi khoảng trượt.
- Redis failover/replication async có thể làm mất counter gần nhất tùy deployment.
- Cache store outage đặt ra quyết định fail-open/fail-closed.
- Một operation sau khi được nhận có thể chạy rất lâu; quota này không hạn chế concurrency.
- Chính limiter cũng chịu tải và có thể thành hot key.
- Quota key phải xây từ trusted tenant identity; không lấy raw tenant ID/limit từ request.
- Redis Cluster yêu cầu dữ liệu multi-key (nếu mở rộng) theo slot rules.

Một limiter chính xác tuyệt đối trong mọi network partition không thể chỉ được suy từ một đoạn Lua nhỏ.

## 27. Multi-instance rate limiting: chỗ nào cần tính toàn cụm?

Giả sử quota:

```text
Tenant A = 100 req/s toàn service
```

Có 10 Java instances. Nếu mỗi instance có local limiter 100 req/s, tenant A có thể được chấp nhận xấp xỉ tới **1.000 req/s** khi traffic phân đều.

Các lựa chọn:

- **Centralized/distributed limiter** cho quota toàn cụm.
- **Hierarchical quotas:** global shared budget và local safety caps.
- **Sharded quota counters** có tổng hợp/ước lượng, chấp nhận bounded overshoot.
- **Gateway limiter** tại một ingress được kiểm soát.
- **Lease/credit allocation** theo batch tới instances, hạn chế central hot key.

### 27.1. Trade-off consistency và availability

Khi quota store không truy cập được:

- Fail-closed có thể bảo vệ backend nhưng từ chối cả traffic hợp lệ.
- Fail-open duy trì availability nhưng có thể cho burst vượt quota.
- Local emergency limits giúp giảm thiểu nhưng không bảo đảm strict global quota.

Chọn chính sách theo hành động: API đọc công khai, truy vấn cực tốn tài nguyên hay admin writes có thể có yêu cầu khác nhau.

## 28. Distributed concurrency không chỉ là một counter có TTL

Một mô hình ngây thơ:

```text
INCR inFlight
if inFlight > limit: reject
decrement when done
```

có thể sai nếu:

- Process crash trước `DECR`.
- Retry đếm hai lần.
- Lease TTL hết hạn khi query vẫn chạy.
- Worker A chậm vẫn đang dùng DB, worker B nhận slot mới.
- Network partition tạo hai quan điểm về số slot.
- Đọc counter rồi tăng ở hai steps không atomic.

### 28.1. Hướng khả thi

- Per-instance hard caps và backend connection limits.
- Distributed leases với owner token, expiry/renewal và cleanup.
- Fencing/version mechanism nếu dùng lease để bảo vệ side effect.
- Scheduler tập trung có bounded work queues.
- Chấp nhận mức oversubscription đã tính toán nếu workload cho phép.

Không khẳng định “giới hạn 50 concurrent toàn cụm, tuyệt đối không bao giờ 51” nếu thuật toán và failure model chưa chứng minh được điều đó.

## 29. Fairness: chia đều không luôn là công bằng

Một tenant trả tiền cho tier lớn có thể được hưởng capacity cao hơn.

Ví dụ trọng số:

```text
Free:      weight 1
Business:  weight 3
Enterprise:weight 8
```

Có thể dùng weighted fair queuing/deficit round robin hoặc scheduler khác để phân phối năng lực phục vụ khi backlog.

### 29.1. Ba tiêu chí cần cân bằng

- **Isolation:** tenant A không bóp nghẹt B.
- **Work conservation:** nếu B không dùng quota, A có thể tận dụng capacity nhàn trong giới hạn.
- **Tier commitments:** tenant có hợp đồng cao hơn nhận ưu tiên/budget tương ứng.

### 29.2. Weighted fairness không có nghĩa mọi truy vấn có cost như nhau

Nếu một export giữ 8 slots nhiều phút còn 8 point reads chỉ chạy 5 ms, phân slot theo số request có thể rất bất công. Cần cost weights, job classes hoặc preemption/cooperative scheduling nơi được hỗ trợ.

## 30. Workload classes và priority queues

Một SaaS NoSQL thường có các luồng:

```text
P0: authorization / order-critical checks
P1: interactive reads
P2: interactive writes bình thường
P3: reports/export
P4: backfill/reindex/background maintenance
```

Đây là ví dụ về classes; ưu tiên thật phải dựa business criticality và correctness.

### 30.1. Tách budget

```text
interactive-read pool: 100 max concurrent
critical-write pool:   40 max concurrent
background-report:      5 max concurrent
```

Không dùng chung unlimited executor và DB connection budget cho mọi loại.

### 30.2. Priority inversion

Nếu báo cáo nặng đã chiếm hết connections trước khi critical write đến, gắn nhãn P0 ở Java queue **không lấy lại được** slot ở source. Cần hard reserved capacity và admission ở đúng tầng.

### 30.3. Starvation

Nếu P0 luôn có traffic, P3 có thể không chạy mãi. Cần deadline, aging, reserved maintenance windows hoặc minimum share để background work vẫn hoàn thành mà không phá SLO.

## 31. Rate limit khi vừa giảm capacity do node mất

Healthy cluster có 4 data nodes, một node mất. Nếu vẫn giữ mọi tenant quotas như cũ, cụm có thể quá tải.

Một adaptive admission controller có thể giảm capacity budget:

```text
Normal mode:
  Global read capacity budget = 100%

Degraded one-node-down mode:
  Global admitted work budget = 70%
  Background jobs temporarily limited further
```

Tỷ lệ chỉ minh họa, không suy theo node count tuyến tính.

### 31.1. Tránh phản hồi quá nhạy

Một controller tăng/giảm quota mỗi giây theo CPU tức thời có thể oscillate và tạo tải dao động. Cần smoothing, hysteresis, minimum hold time, safety floors và operator override.

### 31.2. Không âm thầm hạ consistency

Khi cluster thiếu capacity, không tự hạ read/write quorum hoặc bỏ điều kiện tồn kho chỉ để nhận thêm requests. Correctness contract được giữ, còn admission có thể từ chối có kiểm soát.

## 32. Concurrency limit khi số tenant rất lớn

Tạo một semaphore, queue, histogram và worker pool riêng cho **mỗi tenant từng xuất hiện** có thể làm bộ nhớ vô hạn.

Các cách quản lý:

- Chỉ tạo state cho active tenants.
- TTL/eviction sau idle với concurrency-safe lifecycle.
- Bounded state registry và hashed buckets ở mức approximation.
- Dedicated state cho top tenants/enterprise tiers.
- Partition tenant scheduler state theo instances.
- Limit active tenant count và per-tenant pending requests.
- Cẩn thận không xóa state khi còn active operations.

### 32.1. Eviction race

Nếu xóa semaphore của tenant A trong lúc vẫn có active requests rồi tạo semaphore mới, tổng concurrency có thể vượt giới hạn. Cleanup phải dựa vào reference counts/idle state hoặc một protocol nhất quán.

### 32.2. Hot key ở limiter

Một tenant lớn có thể tạo contention trên một Redis quota key. Quota infrastructure cũng cần capacity test và sharding/lease allocation phù hợp.

## 33. Phân bổ ngân sách khi operation chạy nhiều tầng

Một request report có thể:

```text
GET report
  -> Redis cache
  -> MongoDB read
  -> Elasticsearch search
  -> Object storage export
```

Nếu mỗi tầng độc lập cho phép 100 requests, một logical request có thể dùng nhiều loại tài nguyên cùng lúc.

Cân nhắc **resource-specific budgets**:

```text
Tenant A:
  sourceReadCredits
  searchCostCredits
  exportConcurrentJobs
  objectStorageBytesPerDay
  outboundBandwidth
```

Một single credit bucket cho mọi tài nguyên có thể quá thô: 10.000 Redis GET rẻ khác 10.000 MongoDB aggregates.

### 33.1. Không double-count tùy tiện

Nếu một logical operation dùng MongoDB hai lần do retry, metering có thể có:

- Logical request count = 1.
- Backend attempts = 2.
- Actual source work = 2 attempts.

Billing/quota policy phải nêu nó tính theo **intents** hay **actual resource consumption**. Không lấy một con số mà dùng cho cả reliability và billing nếu semantics không khớp.

## 34. Hedging, fan-out và retries làm khuếch đại tài nguyên

Một API request có thể gửi 10 subqueries song song.

```text
1 logical HTTP request
    -> 10 shard/search subrequests
```

Nếu retry toàn bộ request hai lần:

```text
up to 20+ backend attempts
```

Vì vậy limiter chỉ đếm HTTP entry không kiểm soát được **backend amplification**.

### 34.1. Bounded retry budget

- Giới hạn số attempts.
- Exponential backoff + jitter.
- Tôn trọng deadline còn lại.
- Chỉ retry error classes phù hợp.
- Có admission cho retry traffic.
- Theo dõi attempts/logical operation.
- Không retry writes không idempotent khi outcome unknown.

### 34.2. Hedged reads

Hedging có thể giảm tail latency khi gửi thêm một request dự phòng, nhưng **tăng tải nguồn**. Chỉ bật với read operations phù hợp và budget chặt; không dùng như cách mặc định chữa DB overload.

## 35. Khi bị từ chối: 429, 503, 504 và Retry-After

Ở HTTP boundary, có thể dùng:

| Tình huống | Phản hồi thường phù hợp | Ghi chú |
| --- | --- | --- |
| Vượt quota tenant theo policy | `429 Too Many Requests` | Có thể kèm `Retry-After` |
| Tổng service overload/unavailable | `503 Service Unavailable` | Cân nhắc backoff |
| Upstream vượt deadline | `504 Gateway Timeout` hoặc error theo service contract | Không chứng minh write chưa commit |
| Người gọi thiếu quyền | `403 Forbidden` hoặc opaque 404 | Không dùng quota để che authorization |
| Chưa xác thực | `401 Unauthorized` | Theo HTTP auth contract |
| Job được nhận xử lý sau | `202 Accepted` | Cần job ID/trạng thái/retention |

**Không có status duy nhất phù hợp mọi deployment**. Gateway, gRPC và các SDK có error mappings riêng.

### 35.1. `Retry-After` không phải lời hứa tuyệt đối

Một ví dụ:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
```

Client nên có backoff/jitter; server có thể vẫn overloaded sau hai giây. Không để toàn bộ clients retry đồng bộ ngay tại mốc đó.

### 35.2. Không trả bí mật trong quota response

Một API có thể cho biết `remaining` theo hợp đồng, nhưng không phơi global cluster capacity, tenant khác hay internal queue topology nếu không cần.

## 36. Admission decision theo pipeline

```mermaid
flowchart TD
    A["HTTP request"] --> B["AuthN + trusted tenant + role"]
    B --> C{"Action được phép?"}
    C -->|Không| X["Deny"]
    C -->|Có| D["Resolve query template + cost estimate"]
    D --> E{"Tenant rate/credit budget?"}
    E -->|Không| L["429 / request rejected"]
    E -->|Có| F{"Per-tenant concurrency?"}
    F -->|Không| L
    F -->|Có| G{"Global/source capacity?"}
    G -->|Không| O["503 / bounded queue"]
    G -->|Có| H["Run bounded NoSQL operation"]
    H --> I["Measure actual work, outcome, release budget"]
    I --> J["Response or async job status"]
```

Thứ tự thực thi có thể khác theo kiến trúc, nhưng mỗi bước phải có:

- Phạm vi tenant.
- Owner của quota.
- Policy revision.
- Timeout/deadline.
- Cơ chế hoàn trả tài nguyên/cleanup.
- Metrics và audit.

### 36.1. Không tính quota trên request chưa được xác thực như tenant thật

Traffic không hợp lệ cần được giới hạn ở ingress/global/IP/actor cấp phù hợp, nhưng không để người lạ tùy ý chỉ định `tenantId` của người khác để làm cạn quota của họ.

## 37. Async export: biến truy vấn rất lớn thành job có ngân sách

Một report export 10 triệu records không nên giữ một HTTP request/DB cursor không giới hạn.

Mô hình:

```text
POST /exports
  -> AuthZ + tenant-scoped export criteria
  -> estimate cost and reserve job budget
  -> enqueue a bounded job
  -> return 202 + jobId

Worker:
  -> per-tenant job semaphore
  -> bounded pages/bytes
  -> checkpoint and progress
  -> upload file under tenant-scoped storage
  -> mark complete/fail
```

### 37.1. Những quota cần có

- Maximum concurrent export jobs.
- Maximum queued exports.
- Maximum date range/query shape.
- Total result bytes per export/day.
- Source read budget per worker.
- Object storage and network budget.
- Job deadline/expiry.
- Retention and download authorization.

### 37.2. Không giữ nhiều documents trong RAM

Dùng streaming/chunking với backpressure; giới hạn in-flight pages và serializer buffers. Nhưng streaming cả bảng vẫn có thể đắt ở source, nên phải có read budget và query plan tốt.

### 37.3. Job ID phải có tenant scope

Tenant A không được xem/download export của B bằng cách đoán job ID. Quota và AuthZ đều phải áp cho `GET /exports/{jobId}`.

## 38. Backfill, reindex và migration cũng là tenant workload

Một migration chạy với admin credential có thể bỏ qua API rate limits và quét toàn bộ source.

Quy trình vận hành cần:

- Hạn mức data movement/bytes/s.
- Max batch size và max active workers.
- Per-tenant scheduling.
- Checkpoints/resume.
- Idempotent writes và version guards.
- Chống gây hot partitions.
- Kill switch.
- Ưu tiên thấp hơn critical traffic.
- Giám sát replication lag, compaction và backup schedule.

### 38.1. Không xóa hạn mức khi chạy job nội bộ

Admin jobs có thể cần quota khác, nhưng không nên “unlimited by default”. Hãy định nghĩa **maintenance budget** độc lập có thể giảm ngay khi cluster degraded.

## 39. Backup, compaction, repair và tài nguyên chung

Cụm NoSQL có những tác vụ nền không thuộc tenant trực tiếp:

- Snapshot/backup.
- LSM compaction.
- Shard relocation/rebalance.
- Index rebuild/merge.
- Replica catch-up/repair.
- TTL/tombstone cleanup.
- CDC log retention.
- Security re-encryption.

Chúng tranh chấp CPU, disk, network và memory với API tenants.

### 39.1. Giới hạn tenant chưa đủ bảo vệ cụm

Nếu backup dùng 60% disk bandwidth, global query budget phải điều chỉnh theo **capacity còn lại**; tenant rate limit không ngăn backup gây p99 spike.

### 39.2. Resource reservation

Đặt headroom cho:

```text
failover/re-replication
backup maintenance
peak writes
CDC backlog drain
GC/compaction variability
```

Không benchmark chỉ lúc cụm hoàn toàn idle và suy đó là capacity production an toàn.

## 40. Elasticsearch/OpenSearch: giới hạn search theo query cost

Các hệ tìm kiếm phân tán có thể có:

- Search query timeout/coordination.
- Max result window cho deep pagination.
- `search_after`/PIT cho pagination phù hợp.
- Index-level/shard-level query constraints.
- Request circuit breakers, memory limits và thread pools.
- Giới hạn aggregation buckets.
- Tùy sản phẩm/phiên bản có workload management/task cancellation và resource controls.

### 40.1. Những đường query nguy hiểm

```text
Wildcard trên field cardinality cao
Regex rộng
Aggregation quá nhiều buckets
Sort thiếu trường/index phù hợp
Search across thousands of shards
Vector nearest neighbors không filter tenant
Deep page via from + size rất lớn
```

### 40.2. Dùng chính sách ở ứng dụng

Một search endpoint cho tenant:

```json
{
  "query": {
    "bool": {
      "filter": [
        {"term": {"tenantId": "T-A"}},
        {"term": {"status": "PAID"}}
      ]
    }
  },
  "size": 50
}
```

Dù `size=50`, aggregation hoặc vector query vẫn có thể tốn nhiều tài nguyên. Áp allowlist, max time/range/buckets và per-tenant search credits.

### 40.3. Timeout và partial results

Một search timeout/early termination có thể trả **partial results** tùy API/config. Phải kiểm tra kết quả shard/task status và hợp đồng nghiệp vụ; không nhận báo cáo thiếu records như thành công đầy đủ.

## 41. Đo query cost: estimate và actual

Một mô hình query catalog:

| Template | Estimated cost | Trạng thái cho phép |
| --- | ---: | --- |
| `orders.byId` | 1 | Interactive |
| `orders.recent` | 3 | Interactive |
| `orders.byCustomer` | 5 | Interactive |
| `orders.dailySummary` | 20 | Interactive có giới hạn |
| `orders.fullYearExport` | 200+ | Async only |
| Raw arbitrary scan | Không được định nghĩa | Reject |

Sau khi thực thi, đo:

```text
recordsExamined
recordsReturned
bytesRead
bytesReturned
duration
shardsVisited
backendAttempts
RU/RCU/WCU (nếu service có)
spills / throttling
```

### 41.1. Chấm điểm theo chi phí thực

Nếu reports lâu dần nặng hơn vì dataset tăng, “cost=20” có thể không còn phù hợp. Có thể dùng rolling estimates và đặt hard caps.

### 41.2. Tránh phản ứng quá mức với một outlier

Một report bị GC pause một lần không nên khiến quota của tenant giảm vĩnh viễn. Dùng percentile/cost distribution và business contract khi điều chỉnh.

## 42. Giới hạn bộ nhớ và backpressure trong Java

Nếu một report trả 500 MB JSON, ứng dụng có thể:

```text
Load all results into List
Serialize to one giant String
Buffer all bytes before response
```

khiến heap/GC spike và ảnh hưởng mọi tenants chung JVM.

### 42.1. Thay thế

- Cursor/streaming với bounded buffers.
- Max page/result bytes.
- Bounded executor queues.
- Reactive backpressure khi framework hỗ trợ và được triển khai đúng.
- Output cancellation/cleanup.
- Spooling ra object storage với quota nếu cần.
- Giới hạn tổng số streaming responses đồng thời.

### 42.2. Backpressure phải tới nguồn

Một downstream consumer chậm mà upstream vẫn fetch vô hạn chỉ chuyển queue từ server này sang server khác. Hệ nên giảm nhu cầu đọc hoặc dừng/giới hạn cursor theo flow control.

### 42.3. Java heap quota không hoàn toàn theo tenant

Một JVM chia sẻ heap, thread pool và GC. Nếu cần isolation tài nguyên cứng, có thể tách tenant tier/service process/container/cluster; in-process counters chỉ bảo vệ theo chính sách ứng dụng.

## 43. Bộ kết nối và phân vùng nguồn: tài nguyên hữu hạn

Một Java service có thể dùng shared connection pool tới NoSQL.

Nếu:

```text
Pool capacity = 100 connections
Tenant A dùng 100 connections
Tenant B tới -> chờ timeout
```

đây là một cơ chế noisy-neighbor khác.

Biện pháp:

- Per-tenant in-flight limits trước pool acquisition.
- Max pool wait time phù hợp deadline.
- Bounded driver request queue.
- Shared pool fairness/priority hoặc tách pools theo criticality.
- Giới hạn fan-out/batch concurrency.
- Per-node/region monitoring.

### 43.1. Tách pool không tự là công bằng ở database

Hai pools riêng vẫn có thể cùng đánh vào một shard/partition đang 100% CPU. Phải có source-level capacity budget và, nếu cần, topology separation.

## 44. Retry và quota: tính logical request hay mỗi attempt?

Khi database bị throttle:

```text
Logical request: 1
Attempt 1: throttled
Attempt 2: throttled
Attempt 3: success
```

Nếu limiter chỉ trừ một token HTTP trong khi backend chịu ba attempts, service có thể vượt nguồn tài nguyên.

### 44.1. Hai tầng accounting

- **Business quota:** một intent có thể tính một operation theo hợp đồng.
- **Resource-protection quota:** retry attempts vẫn tiêu CPU/network/DB capacity và phải được giới hạn.

Hai metric:

```text
logical_requests_total
backend_attempts_total
```

Không nên đồng nhất chúng.

### 44.2. Backoff trong thời gian còn lại

Một retry sau 5 giây không có ích nếu API deadline còn 200 ms. Kiểm tra deadline trước khi retry; tránh retry storm khi node failover.

### 44.3. Không phạt tenant vì lỗi hệ thống tùy tiện

Nếu DB outage làm tăng retries do service, việc tính thêm phí cho tenant có thể trái chính sách billing. Resource protection vẫn cần, nhưng metering thương mại nên tách biệt và minh bạch.

## 45. Monitoring: bảng điều khiển nhiều chiều

Một dashboard tối thiểu:

```text
A. User-visible success/error/timeout and p50/p95/p99
B. Offered/sent/completed throughput
C. Total DB in-flight / connection pool pending
D. Tenant rate-limit accepted/rejected by tier
E. Query-cost credits estimated and actual
F. Per-class queue length and oldest pending age
G. Backend per-node/shard CPU/IO/network/GC
H. Scan/aggregation spill, rows examined/returned
I. Retry/throttle/unknown-write outcomes
J. Top resource-consuming tenants (secure, bounded view)
K. Node failure/rebalance/backup markers
L. Quota configuration and policy rollout versions
```

### 45.1. Không dùng raw tenantId ở Prometheus labels cho mọi tenant

Nếu có hàng triệu tenants:

```text
query_latency{tenantId="..."}
```

tạo số time series khổng lồ. Sử dụng:

- `tenant_tier`, `workload_class`, `region`, `operation`, `outcome` — bounded labels.
- Top-N diagnostics giới hạn và phân quyền.
- Auditable per-tenant metering ledger riêng để billing/troubleshoot.
- Sampled traces với identity references được bảo vệ.

### 45.2. Một tenant bị giới hạn thành công vẫn cần quan sát

Tỷ lệ rejected của tenant có thể tăng vì tenant dùng vượt plan, hoặc policy sai làm gián đoạn hoạt động bình thường. Theo dõi cả quota depletion, user impact và support tickets.

## 46. Công bằng nên được đo bằng SLO của tenant khác

Một global p99 đẹp có thể che một tenant nhỏ bị đói tài nguyên trong khi tenant lớn dùng phần lớn traffic.

Đo:

- Good-event SLO cho từng tier.
- Worst affected tenant trong một tập tenant được giám sát có quyền.
- Queue wait distribution.
- Rejection/timeout ratio theo tier và workload.
- Achieved throughput so với offered load và entitlement.
- Cost-per-completed-operation.
- Recovery time sau heavy-tenant burst.

### 46.1. Jain's fairness index

Một chỉ số tham khảo về mức công bằng của allocated throughput:

\[
J=\frac{(\sum_{i=1}^{n}x_i)^2}
{n\sum_{i=1}^{n}x_i^2}
\]

với \(x_i\ge0\) là allocation **đã chuẩn hóa theo entitlement/need phù hợp** nếu tiers khác nhau. Khi mọi \(x_i\) bằng nhau, \(J=1\). Khi lệch mạnh, \(J\) nhỏ hơn.

**Không dùng Jain index làm thước đo duy nhất:** tenants có nhu cầu khác nhau; chia đều cho người không dùng capacity có thể tạo chỉ số “công bằng” theo cách không hữu ích. Phải xem cả SLO và work conservation.

## 47. Quota phải gắn với hợp đồng dịch vụ, không chỉ kỹ thuật

Một mẫu policy:

| Tier | Read rate | Burst | Concurrent report | Storage | Max export |
| --- | --- | --- | --- | --- | --- |
| Starter | Thấp | Nhỏ | 1 | Theo gói | Async nhỏ |
| Business | Trung bình | Vừa | 3 | Theo gói | Async nhiều hơn |
| Enterprise | Theo cam kết | Theo SLA | Theo capacity | Theo hợp đồng | Dedicated/priority |

Bảng chỉ minh họa cấp độ; không có ngưỡng sản phẩm cụ thể.

### 47.1. Soft limit và hard limit

- **Soft limit:** cảnh báo, giảm tốc hoặc cho burst ngắn.
- **Hard limit:** từ chối thêm requests/job.
- **Grace period:** chuyển tiếp có kiểm soát sau upgrade/renewal.
- **Emergency override:** có audit, TTL và phê duyệt.

### 47.2. Không mở rộng quota không giới hạn khi khách nâng tier

Plan tăng phải gắn với **capacity thực**. Nếu backend chỉ chịu 5.000 RU/s, ký quota tổng 50.000 RU/s mà không có oversubscription policy/capacity plan có thể phá SLO.

## 48. Điều chỉnh quota khi tenant tăng trưởng

Một tenant mới có 100 orders, sau sáu tháng có 50 triệu. Query template không đổi nhưng scan cost có thể tăng mạnh.

Theo dõi:

```text
tenant data size / record count (trong metering có quyền)
hot key distribution
query plan changes
source cost per operation
long-running job backlog
p99 and quota rejections
```

### 48.1. Review định kỳ

- Chuẩn hóa cost weights theo query.
- Nâng index/read model.
- Điều chỉnh partitioning.
- Cân nhắc dedicated resources cho tenant lớn.
- Update entitlement theo contract.
- Chạy load test trước khi rollout quota lớn.

### 48.2. Không tăng limit để che query design xấu

Nếu một query thiếu index dùng 500 lần resource so với point lookup, tăng quota cho tenant chỉ chuyển bottleneck sang cả cụm. Sửa access pattern trước.

## 49. Multi-region quota và failover

Một tenant có traffic tại Region A và B. Nếu hai vùng mỗi nơi độc lập cho phép 100 RPS, tổng có thể đạt 200 RPS trong điều kiện bình thường.

Cần quyết định:

- Quota là **toàn cầu** hay **theo vùng**?
- Nếu toàn cầu, đồng bộ limiter thế nào với latency/cost chấp nhận?
- Nếu partition mạng, ưu tiên availability hay strict cap?
- Khi region failover, tenant có nhận tạm double burst không?
- Chính sách quota có version/rollout đồng bộ không?

### 49.1. Strict global cap có chi phí

Để giữ cap toàn cầu thật chặt, cần cơ chế phối hợp phân tán đủ mạnh. Điều này có thể thêm latency hoặc giảm availability khi coordinator không truy cập được.

### 49.2. Emergency failover budget

Một policy có thể cấp tạm ngân sách riêng ở vùng dự phòng với TTL, audit và capacity guard. Không giả định hai vùng tự cộng quota đúng nếu chỉ dùng local counters.

## 50. Bảo vệ quota configuration khỏi spoofing

Nếu client được gửi:

```http
X-Tenant-Tier: enterprise
X-Quota-Limit: 1000000
```

và service tin các headers này, mọi giới hạn đều vô nghĩa.

### 50.1. Policy source

Quota phải được lấy từ:

- Verified tenant account/plan.
- Server-side policy registry.
- Signed/controlled configuration có version.
- Approved admin override có TTL/audit.

### 50.2. Deny-by-default cho unknown tenant

Một tenant chưa được xác thực không thể mặc định nhận “unlimited”. Định nghĩa admission cho invalid/unknown context; không tự động tạo policy có quyền cao.

### 50.3. Negative quota abuse

Đừng cho người dùng A tiêu budget B bằng cách truyền tenant ID của B. Limiter key phải lấy từ trusted context, và authorization diễn ra trước quota scoping.

## 51. Test workload: một tenant nóng và nhiều tenant bình thường

Một bài kiểm thử có thể dùng:

```text
100 tenants
  95 tenants: 20 RPS, point reads
   4 tenants: 100 RPS, mixed operations
   1 tenant: 3.000 RPS, 20% heavy reports
```

Đo với và không có admission guard:

- p99 của 95 tenants bình thường.
- HTTP error/rejection rate.
- Total source QPS.
- CPU/IO max shard.
- Queue wait.
- Backend attempts.
- Query cost distribution.
- Thời gian phục hồi sau burst.

### 51.1. PASS không đơn thuần là bảo vệ cluster

Nếu limiter từ chối mọi request của tenant nóng, cluster có thể khỏe nhưng hợp đồng tenant ấy bị vi phạm. Test cần phân biệt **traffic vượt quota** và **traffic nằm trong entitlement**.

### 51.2. Thử cùng key với nhiều tenants

IDs có thể trùng; test quota key, cache key và metrics scope không bị trộn, đồng thời AuthZ vẫn ngăn cross-tenant reads.

## 52. Test load ladder và tìm điểm bão hòa

Ví dụ tăng offered load:

```text
500 -> 1.000 -> 2.000 -> 3.000 -> 4.000 RPS
```

Ở mỗi bước:

```text
target arrivals
actual sent
completed success
rejected due to tenant quota
rejected due to global capacity
timeouts and unknown outcomes
p50/p95/p99
source in-flight and throttle
```

### 52.1. Không chỉ nhìn throughput thành công

Nếu hệ hoàn tất 3.000 RPS nhưng queue không ngừng tăng, đó chưa phải steady-state capacity.

### 52.2. Tách load generator saturation

Nếu tool chỉ gửi 2.000 RPS khi target 4.000, không được kết luận hệ chịu 4.000. Theo dõi dropped iterations/scheduling gaps và tài nguyên của generator.

## 53. Test tail latency và coordinated omission

Khi backend stall 2 giây, một closed-loop generator chỉ gửi request mới sau response có thể giảm rate phát trong lúc stall, làm p99 trông tốt hơn một arrival model độc lập.

Nếu production arrivals gần open-loop, nên dùng load generator có **scheduled arrival rate** và ghi queue wait/offered vs achieved.

### 53.1. Quantile không phải metric duy nhất

Đo:

```text
p50/p95/p99
count > SLO threshold
timeout/error rate
rejections
queue length and max wait
oldest active query age
```

Một p99 của successful requests đẹp nhưng 20% traffic bị reject có thể không đáp ứng SLO.

## 54. Test khi quota store mất kết nối

Redis/distributed limiter không truy cập được:

```text
API -> quota store timeout
```

Những hành vi cần thử:

- Fail-open mọi requests: backend có bị quá tải?
- Fail-closed: có tạo toàn bộ service outage?
- Fallback local limiter: vượt strict global quota bao nhiêu?
- Redis reconnect: có hot-key retry storm?
- State reset: tenant có nhận thêm burst ngoài dự kiến không?
- Policy update trễ: tenant mới bị áp quota sai không?

### 54.1. Quy định theo workload

Một report dùng hàng nghìn CPU-ms có thể fail-closed nếu không xác minh được ngân sách; point read quan trọng có thể có emergency local budget đã phê duyệt.

Không có đáp án chung cho mọi hệ.

## 55. Test khi database bị mất nút hoặc đang rebalance

Với một node mất:

- Capacity còn lại giảm.
- Partition placement và leader/replica routing thay đổi.
- Retries tăng.
- Backend concurrency an toàn giảm.
- Replication catch-up sẽ tiêu I/O khi node trở lại.

Quotas cấu hình cứng ở peak healthy có thể không còn an toàn.

### 55.1. Kịch bản

1. Chạy baseline với tenants nóng/lạnh.
2. Ghi metrics.
3. Làm một node unavailable trong môi trường được phép.
4. Giữ offered load.
5. Kích hoạt degraded admission policy theo contract.
6. Đo impact lên từng tier và critical writes.
7. Khôi phục node.
8. Theo dõi re-replication/catch-up và recovery.
9. Đối soát correctness/unknown writes.
10. Khôi phục quotas bình thường có hysteresis.

**Không tự chạy chaos trên production** nếu chưa có phê duyệt, kill switch và blast-radius guard.

## 56. Test backup và background overload

Một tenant đang chạy export lớn, đồng thời backup toàn cụm chạy.

Cần đo:

- Disk IOPS và latency.
- Network egress.
- CPU compression/serialization.
- Search/aggregation spill.
- Replica lag.
- Foreground p99.
- Background job progress.
- Backup validity và RPO.
- Quota rejection và queue wait.

Một hệ đạt p99 khi không backup chưa chắc đạt SLO trong maintenance. Giảm background budgets có thể cần nhưng không được khiến backup trượt RPO/RTO nếu business yêu cầu.

## 57. Test quota bypass qua các đường phụ

| Đường | Bypass thường gặp | Kiểm thử |
| --- | --- | --- |
| HTTP GET | Gọi nhiều endpoints dùng pool chung | Quota nhất quán |
| GraphQL | Một HTTP request chứa nhiều nested fetches | Complexity/depth budget |
| gRPC | Streaming RPC duy trì lâu | Concurrency/bytes/time |
| WebSocket | Một connection gửi hàng nghìn messages | Per-message admission |
| Export | 1 POST tạo scan khổng lồ | Async job budgets |
| BatchWrite | 1 call chứa hàng trăm items | Item/byte credits |
| Search | Query fan-out nhiều shards | Search cost and time |
| Vector search | `topK` lớn/không filter tenant | Candidate/budget guard |
| CDC consumer | Không qua HTTP gateway | Worker quotas |
| Scheduler | Admin identity bypass mọi limiter | Maintenance budget |
| Retry | Attempts không tính | Backend attempt budget |
| Cache MISS | Load source đột ngột | Single-flight/fallback budget |

Một HTTP rate limit ở gateway **không bao phủ tự động** mọi consumer và worker.

## 58. Incident runbook: tenant A làm tenant B chậm

1. Xác minh dấu hiệu noisy neighbor: p99 B tăng cùng source saturation.
2. Phân loại hotspot: query shape, shard, pool, CPU/IO, network hay cache misses.
3. Phân biệt tenant A vượt quota hay nằm trong entitlement.
4. Xem per-tenant active queries/credits với quyền phù hợp.
5. Kiểm tra global admission/bulkhead và queue wait.
6. Tạm giới hạn background/heavy query classes theo runbook.
7. Ưu tiên business-critical traffic mà không phá consistency.
8. Tránh tắt toàn bộ tenant nếu không có cơ sở/chính sách.
9. Nếu query thiếu index, áp query guard và sửa access path.
10. Theo dõi p99/error của mọi tenants sau mitigation.
11. Kiểm tra deadline, cancellation và unknown writes.
12. Điều chỉnh quota/capacity có audit, TTL rollback.
13. Tái diễn workload trong staging và bổ sung regression test.

### 58.1. Không tự coi đỉnh CPU là root cause

CPU cao có thể là hậu quả retry/compaction; xem query plan, pool wait, disk latency, shard placement và timeline trước khi kết luận.

## 59. Incident runbook: nhiều requests bị 429

1. Xác định policy/tier/revision đang áp dụng.
2. Xác minh trusted tenant identity, không có spoofed header.
3. So actual usage với entitlement.
4. Phân biệt legitimate burst, retry storm và abuse.
5. Xem token refill/counter TTL và các cửa sổ limiter.
6. Nếu multi-region, xem global vs regional quota.
7. Kiểm quota store health/failover.
8. Kiểm background jobs có chiếm budget interactive không.
9. Nếu cấu hình sai, rollback qua change control.
10. Nếu nhu cầu hợp lệ tăng, cân nhắc queue/async/capacity/plan nâng cấp.
11. Xác minh `Retry-After`, SDK backoff và thông báo khách hàng.

## 60. Incident runbook: query vẫn vượt budget

1. Kiểm tra operation có đi qua đúng admission layer không.
2. Xem path bypass qua scheduler/broker/admin/internal API.
3. Xác nhận timer đo đúng end-to-end.
4. Kiểm source-side query timeout và cancellation support.
5. Đo docs/bytes examined vs returned.
6. Xem query plan, index và partition targeting.
7. Kiểm `LIMIT` bị hiểu nhầm thành scan cap không.
8. Kiểm concurrency fan-out/retries.
9. Xem memory spill/large response.
10. Bổ sung query allowlist/cost guard/hard limits.
11. Test với tenant lớn, keys nóng và failure mode.
12. Theo dõi p99/source saturation và correctness sau sửa.

## 61. Anti-patterns thường gặp

| Anti-pattern | Vì sao sai | Cách tốt hơn |
| --- | --- | --- |
| Một quota RPS chung cho mọi tenant | Tenant lớn chiếm tài nguyên | Per-tenant rate/concurrency |
| Chỉ có per-tenant limit | Tổng tenants có thể quá tải DB | Thêm global/source caps |
| Chỉ có global pool | Tenant A chiếm hết slots | Fair admission/bulkheads |
| RPS thấp nghĩa query rẻ | Một scan rất tốn | Cost/query shape budget |
| `LIMIT 100` nghĩa đọc tối đa 100 rows | Engine có thể scan lớn | Index/scan budget |
| Chỉ đo p99 success | Rejections/timeouts biến mất | Good-event SLO |
| Mỗi pod limit 100 nghĩa toàn cluster 100 | 10 pods có thể cho 1.000 | Distributed/global policy |
| Redis counter là strict global guarantee mọi outage | Replication/failover có giới hạn | Failure contract/emergency limit |
| Một TTL counter là distributed concurrency lock | Crash/lease expiry | Lease protocol + local cap |
| Xóa semaphore khi còn in-flight | Tạo 2 bộ permits | Safe lifecycle management |
| `Semaphore(true)` là fair across tenants | Chỉ local queue semantics | Weighted scheduler |
| Tạo unlimited tenant state | Memory leak | Active state lifecycle |
| Tenant header do client quyết định quota | Spoofing/quota depletion | Trusted identity |
| Coi IAM/ACL là throughput quota | Chỉ là security controls | Resource admission |
| Quota theo số HTTP calls | Fan-out, batch, retry bị bỏ | Cost/attempt accounting |
| Tắt all retries | Có thể giảm resilience | Bounded classified retries |
| Retry vô hạn khi 429 | Amplification | Backoff/jitter/Retry-After |
| Tăng timeout để chữa slow query | Giữ slot lâu hơn | Query plan/admission |
| Gỡ tenant filter để truy vấn nhanh | Cross-tenant leak | Index/partition phù hợp |
| Queue không giới hạn | RAM/latency phát nổ | Bounded queue |
| Chỉ limit foreground | Backfill/backup gây overload | Maintenance budgets |
| Thêm node luôn chữa hot key | Hot partition vẫn nóng | Data modeling/partitioning |
| Hard quota làm tenant nằm trong plan cũng bị reject | Vi phạm entitlement/SLO | Capacity planning/fairness |
| Quota store down thì fail-open vô hạn | Có thể sập source | Emergency local budgets |
| Log tenant ID vào mọi metric label | Cardinality/PII | Bounded tier labels + ledger |
| Một p99 toàn cluster chứng minh fairness | Che tenant nhỏ | Per-tier/worst-tenant checks |
| Tính retries vào billing ngoài hợp đồng | Có thể phạt lỗi hệ | Tách protection vs billing |
| Static config không version/rollback | Lỗi khó khắc phục | Policy revision/canary |
| Query optimizer bỏ consistency | Data correctness mất | Giữ invariant |
| Background job `unlimited` vì admin | Có thể phá mọi SLO | Separate maintenance quota |

## 62. Checklist trước khi phát hành quota policy

- [ ] Tenant context và plan được xác minh từ server-side source.
- [ ] AuthZ và tenant predicates vẫn được kiểm cho mọi query.
- [ ] Rate, burst, concurrency, queue, timeout đều có mục tiêu riêng.
- [ ] Query catalog có allowed filters/sort/projection/index.
- [ ] Max page size, bytes và số trang có giới hạn.
- [ ] Scan/aggregation cost được đo và có guardrails.
- [ ] Global capacity budget và per-tenant budget cùng tồn tại.
- [ ] Có reserved capacity cho critical operations.
- [ ] Background/export/reindex/backup có budgets riêng.
- [ ] Driver pool wait và source in-flight được đo.
- [ ] Timeout/deadline và cancellation behavior được định nghĩa.
- [ ] Retry attempts không vô hạn, writes có idempotency.
- [ ] Distributed limits có failure/consistency contract rõ.
- [ ] Quota state không tăng bộ nhớ vô hạn theo tenant count.
- [ ] Multi-region failover policy được kiểm thử.
- [ ] Không đưa raw tenantId/PII vào high-cardinality metrics.
- [ ] Có secure per-tenant metering cho billing/support.
- [ ] `429/503/504`, Retry-After và async `202` có semantics rõ.
- [ ] Không lộ global capacity hoặc dữ liệu tenant khác.
- [ ] Load test có tenant nóng, hot keys và workload lệch.
- [ ] Đo offered/sent/completed, timeout/rejection và p95/p99.
- [ ] Capacity N-1/backup/rebalance được thử theo risk model.
- [ ] Đối soát correctness, authz và data freshness.
- [ ] Policy config có version, owner, approval và rollback.
- [ ] Dashboard, alerts, runbook và emergency controls sẵn sàng.

## 63. Bài tập thực hành

### Bài 1 — RPS và concurrency

Tenant A được 100 RPS. Mỗi query chạy 5 giây, workload ổn định.

**Hỏi:** Có thể có bao nhiêu in-flight query nếu không đặt concurrency cap?

**Gợi ý:** Gần 500 theo \(\lambda W\), trong mô hình ổn định phù hợp.

### Bài 2 — Global và per-tenant

100 tenants, mỗi tenant max 20 in-flight; global max 100.

**Hỏi:** Vì sao cả hai hạn mức cần thiết?

**Gợi ý:** Per-tenant chặn monopolization, global chặn tổng vượt backend capacity.

### Bài 3 — Fixed window

Quota 100 req/min, client gửi 100 lúc 12:00:59 và 100 lúc 12:01:00.

**Hỏi:** Tại sao có thể chấp nhận 200 trong 2 giây?

**Gợi ý:** Reset ở ranh giới fixed windows.

### Bài 4 — Token bucket

Bucket max 200 tokens, refill 50/s, có 40 tokens còn lại. Sau 3 giây không gọi, còn bao nhiêu?

**Gợi ý:** \(\min(200,40+50\times3)=190\).

### Bài 5 — Query weighting

Một GET by ID dùng 1 credit, full-year report dùng 100 credits.

**Hỏi:** Có nên cho cả hai cùng giá một request?

**Gợi ý:** Không nếu mục tiêu bảo vệ source cost.

### Bài 6 — LIMIT

Query trả 10 records nhưng quét 1 triệu documents.

**Hỏi:** `limit(10)` đã bảo vệ source chưa?

**Gợi ý:** Chưa; cần index/scan/cost guard.

### Bài 7 — MongoDB maxTimeMS

Một query có `maxTimeMS=500` nhưng HTTP mất 2 giây.

**Hỏi:** Có mâu thuẫn không?

**Gợi ý:** Không; pool wait/network/retries và server semantics khác end-to-end.

### Bài 8 — Cassandra paging

Một `pageSize=100` client tải 10.000 pages.

**Hỏi:** Tổng rows có được giới hạn 100 không?

**Gợi ý:** Không; giới hạn number of pages/bytes/deadline.

### Bài 9 — DynamoDB FilterExpression

Query GSI đọc nhiều items rồi filter còn 3 kết quả.

**Hỏi:** RCU có tương đương 3 items trả không?

**Gợi ý:** Không; filtering sau read không nhất thiết giảm read cost.

### Bài 10 — IAM vs quota

IAM giới hạn `LeadingKeys` theo tenant.

**Hỏi:** Nó có bảo đảm tenant không gửi 100.000 QPS?

**Gợi ý:** Không; security scope khác resource quota.

### Bài 11 — Redis ACL

Redis user chỉ được `GET tenant:A:*`.

**Hỏi:** User có mặc định bị giới hạn 100 GET/s?

**Gợi ý:** Không; cần rate limiter/admission riêng.

### Bài 12 — Redis limiter outage

Quota Redis mất kết nối.

**Hỏi:** Có nên fail-open vô hạn?

**Gợi ý:** Tùy workload/risk; emergency local caps giúp bảo vệ source.

### Bài 13 — Mười API instances

Mỗi instance cap 50 RPS/tenant.

**Hỏi:** Tenant có thể đạt bao nhiêu toàn cluster?

**Gợi ý:** Có thể tới khoảng 500 RPS nếu traffic được phân bổ và không có global cap.

### Bài 14 — Concurrency lease

Một worker lấy distributed slot TTL 10s, query chạy 20s.

**Hỏi:** Rủi ro?

**Gợi ý:** Slot hết hạn khi query vẫn chạy; có thể oversubscribe.

### Bài 15 — Fair semaphore

Semaphore dùng fair=true nhưng `tryAcquire` và không có per-tenant queue.

**Hỏi:** Đã là weighted fair scheduling chưa?

**Gợi ý:** Chưa.

### Bài 16 — Unknown tenant

Client gửi `X-Tenant-Tier: enterprise`.

**Hỏi:** Server có nên tin không?

**Gợi ý:** Không; tier từ verified policy registry.

### Bài 17 — Priority inversion

Background exports giữ hết 100 DB connections; payment write đến.

**Hỏi:** Cần thiết kế gì?

**Gợi ý:** Reserved critical write budget/bulkhead tại tầng trước pool.

### Bài 18 — Hard vs soft quota

Tenant vượt soft warning một chút nhưng chưa vượt hard limit.

**Hỏi:** Có nhất thiết trả 429 không?

**Gợi ý:** Tùy policy; soft limit có thể cảnh báo/throttle khác.

### Bài 19 — 429 Retry-After

Client thấy `429` kèm `Retry-After: 2`, 10.000 clients retry đúng 2 giây.

**Hỏi:** Rủi ro?

**Gợi ý:** Synchronized retry burst; thêm jitter và backoff budget.

### Bài 20 — Query fan-out

Một HTTP request chạy 15 shard subqueries.

**Hỏi:** Chỉ đếm một HTTP token đã giới hạn backend requests chưa?

**Gợi ý:** Chưa; cần fan-out/cost budget.

### Bài 21 — Trùng quota khi multi-region

Region A và B đều cho tenant 100 RPS local.

**Hỏi:** Tổng có thể hơn global target 100 không?

**Gợi ý:** Có; cần policy coordination hoặc chấp nhận bounded overshoot.

### Bài 22 — Tenant A ảnh hưởng B

p99 B tăng gấp 20 lần khi A chạy báo cáo nặng.

**Hỏi:** Chỉ xem p99 toàn cluster đủ chưa?

**Gợi ý:** Không; xem per-tier/per-tenant protected diagnostics và source hotspots.

### Bài 23 — Hot partition

Thêm 2 data nodes nhưng một tenant còn ghi một hot partition.

**Hỏi:** Vì sao p99 không cải thiện?

**Gợi ý:** Logical hotspot vẫn tập trung; cần remodel key/distribution.

### Bài 24 — Queue không giới hạn

Mỗi tenant được 10 active queries nhưng 1 triệu jobs chờ.

**Hỏi:** Hệ đã an toàn?

**Gợi ý:** Chưa; cần bounded queue/wait/deadline.

### Bài 25 — Async report

Một report lớn tạo bằng `POST /exports`.

**Hỏi:** Cần quota nào ngoài RPS?

**Gợi ý:** Concurrent/queued jobs, read/byte budget, retention, deadline, storage.

### Bài 26 — Retry

Một request bị throttled hai lần rồi thành công attempt thứ ba.

**Hỏi:** Business request count và backend attempts lần lượt bao nhiêu?

**Gợi ý:** Một logical request, ba attempts.

### Bài 27 — Policy scaling

Quota bình thường tạo quá tải khi một data node mất.

**Hỏi:** Sửa gì?

**Gợi ý:** Adaptive global admission/degraded mode có hysteresis, giữ correctness.

### Bài 28 — Backup

Backup bắt đầu làm disk saturate; interactive p99 tăng.

**Hỏi:** Tenant limiter có tự chữa được không?

**Gợi ý:** Không; maintenance budget và global headroom cần phối hợp.

### Bài 29 — Metrics

Prometheus có label `tenantId` với hai triệu tenants.

**Hỏi:** Rủi ro?

**Gợi ý:** Cardinality lớn; dùng bounded tags và metering ledger riêng.

### Bài 30 — Thiết kế tổng hợp

Một SaaS Java có MongoDB shared source, Redis L2, Elasticsearch Search, DynamoDB idempotency ledger và 1.000 tenants. Top 5 tenants chiếm 60% reads; mỗi đêm có backup, cuối tuần có export nặng. Cụm phải chịu mất một node mà vẫn giữ correctness.

**Yêu cầu:**

1. Định nghĩa trusted tenant context và tenant-tier policy.
2. Tạo global/per-tenant rate, concurrency, queue và query-cost limits.
3. Tách budgets cho critical writes, reads, reports và maintenance.
4. Giới hạn MongoDB scan/aggregation, Search buckets/fan-out, DynamoDB read credits.
5. Dùng cache và distributed rate limiter với failure policy.
6. Thiết kế retry budget, deadline, partial results và unknown-write handling.
7. Lập load test hot tenant, multi-region, quota store down, backup và node loss.
8. Định nghĩa PASS/FAIL theo SLO, fairness, backend cost, error rates và correctness.
9. Đưa ra quy trình đổi quota có audit, canary và rollback.

**Gợi ý:** Dùng nhiều lớp bảo vệ; không chỉ tăng máy hoặc hạ consistency. Kết hợp workload-aware cost model, bounded per-tenant admission, global source headroom, secure metering và negative/failure tests.

## 64. Tài liệu tham khảo và hướng triển khai

Khi dùng sản phẩm thật, cần đọc tài liệu **đúng phiên bản, SDK và deployment mode**:

- MongoDB query operations: https://www.mongodb.com/docs/manual/tutorial/query-documents/
- MongoDB cursor methods: https://www.mongodb.com/docs/manual/reference/method/db.collection.find/
- MongoDB Java Sync Driver: https://www.mongodb.com/docs/drivers/java/sync/current/
- Apache Cassandra documentation: https://cassandra.apache.org/doc/latest/
- DynamoDB read/write capacity mode: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html
- DynamoDB Query API: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.html
- DynamoDB IAM fine-grained access: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html
- Redis scripting: https://redis.io/docs/latest/develop/programmability/eval-intro/
- Redis ACL: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- Elasticsearch query DSL: https://www.elastic.co/docs/
- OpenSearch documentation: https://docs.opensearch.org/
- Micrometer metrics: https://docs.micrometer.io/micrometer/reference/
- Prometheus histogram guidance: https://prometheus.io/docs/practices/histograms/
- OpenTelemetry Java: https://opentelemetry.io/docs/languages/java/
- OWASP API security: https://owasp.org/API-Security/

Các liên kết hỗ trợ tra cứu. Không giả định tên setting, server limits hoặc native quota capabilities giống nhau giữa versions hay managed services.

## 65. Kết luận

**Đặt giới hạn truy vấn, tải đồng thời và tài nguyên mỗi tenant là bài toán kiểm soát năng lực phục vụ và tính công bằng, không chỉ là cấu hình một con số RPS.** Một tenant có thể vượt mức bằng một query quét rất lớn, một aggregation nhiều buckets, hàng nghìn pages, retries, export jobs hoặc cache misses, ngay cả khi số HTTP requests rất thấp. Nếu chỉ dùng global pool, tenant nóng có thể làm tenant khác đói tài nguyên; nếu chỉ giới hạn riêng từng tenant, tổng tài nguyên vẫn có thể vượt khả năng của cluster.

Một thiết kế vững cần kết hợp **trusted tenant identity, admission control theo rate/credit, concurrency caps riêng và toàn cụm, bounded queues, end-to-end deadlines, query-shape/cost guards, reserved capacity theo workload và giới hạn background maintenance**. MongoDB, Cassandra, DynamoDB, Redis và Elasticsearch/OpenSearch có những controls riêng nhưng không mặc nhiên áp native per-tenant quota cho shared data; ứng dụng, gateway và scheduler thường phải thực thi phần còn thiếu.

Cuối cùng, **quota chỉ thực sự hiệu quả khi được kiểm thử dưới tải lệch và sự cố**: một tenant nóng, nhiều tenant nhỏ, cluster mất nút, backup, limiter Redis unavailable và retry storm. Quan sát p95/p99 cùng error/rejection rate, throughput thực, backend cost, tài nguyên từng node và quyền dữ liệu; giữ idempotency, consistency và tenant isolation. Mục tiêu không phải từ chối càng nhiều càng tốt, mà là **cho mỗi tenant khả năng phục vụ phù hợp hợp đồng, tận dụng công suất nhàn hợp lý và bảo vệ toàn cụm trước tải bất thường mà không đánh đổi dữ liệu đúng**.
