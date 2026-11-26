# Theo dõi truy vấn chậm, request ID và ngữ cảnh truy vết

## 1. Bối cảnh: truy vấn chạy chậm, nhưng log chỉ ghi “Couchbase timeout”

Một API lịch sử đơn hàng có lúc trả sau 80 ms, có lúc hơn 2 giây. Đội phát triển thấy `/actuator/health` vẫn `UP` và KV `findById` hoạt động tốt, nhưng `findByCustomerId` không đạt SLO. Log chỉ có:

~~~text
2026-11-25T09:10:40Z ERROR Database timeout
~~~

Thông điệp ấy chưa trả lời được câu hỏi quan trọng: **HTTP request nào**, **SQL++ statement nào**, **Query Service request nào**, **index/query plan nào** và **tầng nào đã tiêu tốn thời gian**? Để phân tích nguyên nhân, cần kết hợp request correlation, profiling và dữ liệu quan sát an toàn.

Bài thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**, nơi xây dựng tầng truy cập Couchbase bằng document mapping, Spring Data Repository, `CouchbaseTemplate` và SQL++; liên quan bucket/scope/collection, chỉ mục, TTL, CAS, transaction, reactive API, consistency và hiệu năng.

**Sau bài học, bạn có thể:**

1. Xác định và dùng đúng **HTTP request/trace ID**, **SQL++ client context ID**, **server Query request ID** và **SDK error context**.
2. Thu latency, timeout, query shape, row count, query plan và metadata mà không log dữ liệu khách hàng.
3. Biết khi nào dùng `EXPLAIN`, profiling/metrics SQL++ và các nguồn active/completed requests trong Query Service.
4. Phân biệt query chậm vì GSI/scan/fetch/sort, consistency wait, tải, client queue, network, mapping hoặc result streaming.
5. Tạo ví dụ Java SDK, Spring Data service và Micrometer để liên kết request chậm với trace ID.
6. Truy vết xuyên reactive streams đúng thời điểm subscription/completion.
7. Thiết kế dashboard, cảnh báo và runbook tương quan application–SDK–Query–Index Service.
8. Bảo vệ PII, credentials, query parameters và hạn chế overhead của profiling/logging.

**Thông điệp cốt lõi:** Một ID giúp *tìm đúng request*, một phép đo giúp *biết request chậm tới đâu*, còn profile/plan/metrics giúp *tìm nguyên nhân*. Không dùng một trong ba thay cho những cái còn lại.

## 2. Ví dụ xuyên suốt: Orders API và SQL++ theo customerId

Ứng dụng dùng namespace:

~~~text
Bucket      : shop
Scope       : sales
Collection  : orders
ID mẫu      : order::o-1001
~~~

Document JSON minh họa:

~~~json
{
  "customerId": "c-1001",
  "status": "PAID",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 480000
}
~~~

Các endpoint:

| API | Spring Data / SDK | Đường Couchbase |
| --- | --- | --- |
| `GET /orders/{id}` | `CouchbaseRepository.findById` | KV get theo key |
| `GET /customers/{id}/orders` | Derived `findByCustomerId` | SQL++ qua Query và thường GSI |
| `GET /orders/recent` | `CouchbaseTemplate.findByQuery` | SQL++ + converter |
| `POST /orders` | `save` / KV mutation | Data Service, có thể CAS/durability |
| `GET /orders/search` | Search API nếu triển khai | Search index; khác SQL++ GSI |

Query minh họa:

~~~sql
SELECT META(o).id AS documentId,
       o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

**Chú ý:** `customerId` là dữ liệu có thể nhạy cảm, không ghi raw parameter vào logs/traces. Query template đặt tên `orders_by_customer_recent` và dùng parameter binding. Trong production, generated SQL++ từ Spring Data có thể khác ví dụ raw SDK vì type discriminator, alias hoặc projection.

## 3. Một truy vấn có nhiều ID: không được gộp nhầm

| ID | Ai tạo / phạm vi | Dùng để làm gì? |
| --- | --- | --- |
| **HTTP request ID** | Gateway/app, một HTTP request | Tra log tuyến HTTP/controller |
| **trace ID** | Hệ thống distributed tracing | Liên kết spans xuyên service/process |
| **span ID** | Tracing cho mỗi span | Phân biệt từng công đoạn trong một trace |
| **SQL++ client context ID** | Client cung cấp khi gửi Query | Tương quan client request với Query Service |
| **Query server request ID** | Query Service tạo/ghi nhận | Tra cứu request tại Query Service, profile/log |
| **SDK operation/error context** | SDK theo operation | Phân tích endpoint, thời gian, retry, timeout |
| **Document ID / CAS** | Couchbase data model/mutation | Định danh dữ liệu và version; **không** phải request ID |

### 3.1. HTTP request ID không nhất thiết là trace ID

Một gateway có thể gắn `X-Request-ID`; OpenTelemetry/Micrometer Tracing có thể tạo một trace ID khác. Một HTTP request cũng có thể phát ra nhiều SQL++ queries. Vì vậy phải có **quan hệ một HTTP request → nhiều spans/DB operations**, không bắt buộc map một-một vào Query server request ID.

### 3.2. clientContextId không phải requestId của server

Với SDK SQL++, client có thể gắn `clientContextId` để server echo/ghi nhận theo API. Server Query request ID là mã khác do Query Service cấp. Khi operation thành công và metadata có đủ trường, nên ghi **cả hai** theo policy an toàn, cùng trace/request ID của ứng dụng.

### 3.3. CAS và mutation token không phải tracing ID

CAS dùng phát hiện xung đột cập nhật; mutation token có thể dùng cho query scan consistency theo mutation. Đừng đưa CAS hay timestamp nghiệp vụ vào `clientContextId` như thể chúng là mã của request; càng không dùng chúng làm substitute cho trace ID.

## 4. Sơ đồ luồng ID và dữ liệu quan sát

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant G as Gateway / Controller
    participant S as Order Service
    participant D as Java SDK
    participant Q as Query Service
    participant I as Index Service

    C->>G: GET /customers/{id}/orders
    Note over G: httpRequestId, traceId
    G->>S: Request context / trace
    S->>D: SQL++ + clientContextId
    D->>Q: Query request + clientContextId
    Note over Q: server requestId
    Q->>I: GSI index scan
    I-->>Q: Document keys / projected data
    Q-->>D: Rows, metadata requestId
    D-->>S: QueryResult hoặc error context
    S-->>G: API response / status
    G-->>C: Response với correlation ID an toàn
~~~

Một request có thể chậm trước khi SQL++ được gửi, trong thời gian Query Service xử lý hoặc sau khi rows trở về (mapping/serialization). Vì vậy log cần **mốc thời gian đo**, không chỉ ID.

## 5. “Slow query” phải có định nghĩa cụ thể

Một query chậm theo góc nhìn nào?

- **HTTP slow:** tổng thời gian người dùng chờ API.
- **Service slow:** khoảng service logic, cache, mapper, DB và response preparation.
- **SDK query slow:** khoảng operation từ SDK API đến khi nhận kết quả theo instrument cụ thể.
- **Query Service slow:** thời gian Query Service xử lý request theo metrics server.
- **Index scan slow:** thời gian/chỉ số phục vụ scan ở GSI path.
- **Time to first row:** quan trọng với streaming; khác tổng thời gian đọc hết rows.
- **Timeout:** chưa hoàn tất trong deadline; không thể coi là row count = 0.

Một API có thể chậm khi query rất nhanh vì application đợi semaphore, mapping một kết quả khổng lồ, cache miss hoặc network. Ngược lại, Query Service p99 có thể xấu do `REQUEST_PLUS` chờ index bắt kịp mutation, dù KV latency vẫn tốt.

### 5.1. Ngưỡng “chậm” phải lấy từ SLO

Không lấy một ngưỡng cố định như “trên 100 ms = slow” áp cho mọi query. Một lookup KV theo ID, một query list `LIMIT 20` và một analytic aggregate có latency mục tiêu khác nhau. Nên định nghĩa SLO theo route và query template:

~~~text
route                    queryTemplate              SLO
GET /orders/{id}         kv_get_order               riêng
GET /customers/{id}/orders orders_by_customer_recent riêng
GET /reports/sales       sales_report               riêng
~~~

Đây là khung định nghĩa, **không phải các giá trị benchmark thực tế**.

## 6. Chuỗi độ trễ: ứng dụng, SDK, Query và Index

~~~text
t0  HTTP request đến application
t1  Service method bắt đầu
t2  Chờ application concurrency/admission gate
t3  Bắt đầu lời gọi Repository/SDK query
t4  SDK dispatch / network
t5  Query Service thực hiện query / GSI scan / Data fetch
t6  SDK nhận metadata/rows theo API
t7  Spring Data mapping + app postprocessing kết thúc
t8  HTTP response hoàn thành
~~~

Một số đại lượng:

\[
L_{\mathrm{http}}=t_8-t_0
\]

\[
W_{\mathrm{admission}}=t_3-t_2
\]

\[
L_{\mathrm{app\_db}}=t_7-t_3
\]

**Không tự cộng** HTTP duration với SDK/server durations — các khoảng có thể lồng trong nhau. `t4`, `t5` không phải lúc nào cũng lấy trực tiếp được bằng `System.nanoTime()` ở app; cần trace/Query Service metrics và profile để xem sâu.

### 6.1. Đồng hồ đơn điệu để đo duration

~~~java
long startedNs = System.nanoTime();
try {
    return repository.findByCustomerId(customerId);
} finally {
    long elapsedNs = System.nanoTime() - startedNs;
    // Ghi vào Timer/histogram, không log customerId.
}
~~~

`System.nanoTime()` phù hợp đo duration trong một process. Dùng wall-clock UTC cho timestamp, không lấy chênh lệch wall-clock giữa những node chưa biết sai số đồng hồ rồi coi là latency chính xác.

### 6.2. Result parsing có thể nằm ngoài duration nếu timer đặt sai

Một SDK call có thể trả `QueryResult` rồi code xử lý `rowsAsObject()` hoặc mapper sau đó. Nếu timer chỉ bọc lời gọi query và không bọc row materialization, duration sẽ không bằng tổng thời gian app cần để có danh sách kết quả. Đặt timer theo đúng mục đích.

## 7. Tạo client context ID cho SQL++ có kiểm soát

Java SDK 3.x hỗ trợ truyền `clientContextId` qua `QueryOptions` trong các phiên bản phù hợp. Giá trị nên là ID **opaque**, không chứa tên khách hàng, JWT hay SQL++ parameters.

Ví dụ dùng ID ngẫu nhiên cho mỗi Query operation:

~~~java
import java.util.UUID;

String clientContextId =
        "orders-query-" + UUID.randomUUID();
~~~

Thiết kế thực tế có thể gắn thêm một request/span prefix ngắn không nhạy cảm, nhưng:

- Không dùng email, user ID hoặc order ID thô.
- Không dùng trace ID làm metric label nếu cardinality quá cao.
- Không cho client bên ngoài tự gắn chuỗi tùy ý chưa kiểm tra vào diagnostics/logging.
- Không lưu ID này như một business primary key.
- Một HTTP request có nhiều DB operations cần **nhiều clientContextIds**, hoặc thêm operation sequence tránh collisions.

### 7.1. Tại sao dùng clientContextId thay vì chỉ log trace ID?

Trace ID thuộc hệ thống tracing của ứng dụng; Query Service không tự biết correlation đó trừ khi được truyền qua mechanism phù hợp. Client context ID là một trường Query protocol hỗ trợ để tìm request từ góc Query Service. Nó là **cầu nối** giữa log ứng dụng và Query engine diagnostics.

## 8. Java SDK: SQL++ có clientContextId, metadata và timeout

Ví dụ dưới đây dành cho SDK 3.x có hỗ trợ các method thể hiện; trước khi đưa vào production phải đối chiếu đúng version dependency.

~~~java
import java.time.Duration;
import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public final class OrderHistoryDao {
    private static final String SQL = """
        SELECT META(o).id AS documentId,
               o.status, o.createdAt
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.customerId = $customerId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    private final Cluster cluster;

    public OrderHistoryDao(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult findRecent(String customerId) {
        String clientId = "orders-" + UUID.randomUUID();

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .clientContextId(clientId)
                .scanConsistency(QueryScanConsistency.NOT_BOUNDED)
                .timeout(Duration.ofSeconds(2));

        return cluster.query(SQL, options);
    }
}
~~~

**Kết quả:** Khi query thành công, có thể lấy `QueryResult.metaData()` để trích `requestId` của Query Service và thông tin client context nếu SDK/version cung cấp. Ví dụ khái niệm:

~~~java
QueryResult result = dao.findRecent(customerId);

String serverRequestId = result.metaData().requestId();

// clientContextId có thể được lưu ở scope của lời gọi
// và/hoặc lấy qua metadata theo API SDK version phù hợp.
// Không log JSON row hoặc parameters vì dữ liệu nhạy cảm.
~~~

### 8.1. Kiểm tra điểm phân tách ID

Trong production, giữ `clientId` cùng scope thực hiện query (hoặc một context/wrapper riêng). Không tạo một UUID trong caller rồi quên truyền vào `QueryOptions`; cũng không tạo ID mới khi log success khiến log và server không thể nối lại.

### 8.2. Có thể lặp cùng query với nhiều clientContextIds

`clientContextId` là nhãn tương quan **per invocation**. Không tạo một ID cố định “orders-query” cho mọi request rồi trông đợi nó giúp tra chính xác một incident. Tên query template cố định là một field khác, như `queryShape=orders_by_customer_recent`.

### 8.3. Không coi SDK code trên là instrumentation hoàn chỉnh

Một timeout có thể xảy ra **trước khi có QueryResult**, nên không có metadata `requestId()` trả về qua success path. Cần logging exception/error context và client-side correlation ID **kể cả khi query fail**. Đó là lý do ID phải được tạo và lưu trước khi gửi.

## 9. Ba trường nên log cùng nhau khi SQL++ thành công

Một record minh họa do ứng dụng định nghĩa:

~~~text
ts=2026-11-25T09:10:40Z
route=GET /customers/{id}/orders
traceId=4ab6...   (opaque)
requestId=req-174  (HTTP app ID)
db.service=query
db.operation=sqlpp
db.queryShape=orders_by_customer_recent
db.clientContextId=orders-...  (opaque)
db.serverRequestId=...         (khi metadata có)
db.keyspace=shop.sales.orders
db.consistency=NOT_BOUNDED
db.rows=20
db.durationMs=78
db.outcome=success
~~~

Đây **không phải log mặc định của SDK** và các giá trị chỉ minh họa cấu trúc. Trong deployment thật, dùng log JSON/structured logging và cho phép đọc những trường nhạy cảm theo role.

### 9.1. Khi có Query timeout

Không có `QueryResult` thành công thì metadata request ID có thể không lấy được theo đường success. Thay vào đó log:

~~~text
traceId=...
db.clientContextId=...
db.queryShape=orders_by_customer_recent
db.service=query
db.durationMs=2001
db.outcome=timeout
db.exceptionClass=<tên lớp exception thực>
~~~

Nếu SDK exception/error context chứa server-side request ID hoặc endpoint information, trích những field được hỗ trợ theo version và **redact**. Không tự tạo một server request ID giả để lấp chỗ trống.

## 10. Phân biệt server request ID với HTTP gateway request ID

Hai ID đều có thể có nhãn “request ID” trong logs:

| Ngữ cảnh | Tên nên dùng trong hệ thống |
| --- | --- |
| Reverse proxy/ingress | `http.requestId` |
| Distributed trace | `trace.id`, `span.id` |
| SQL++ client-provided context | `db.query.clientContextId` |
| Query Service generated | `db.query.serverRequestId` |
| SDK operation context | `db.sdk.operationId` nếu SDK thực sự cung cấp |

Đặt tên **có namespace** giúp tránh việc dashboard tự join sai. Không tự giả định header `X-Request-ID` của ingress được Couchbase Query Service lưu nguyên văn; phải truyền context qua mechanism được hỗ trợ.

### 10.1. HTTP và SQL++ có cardinality khác nhau

Một request HTTP có thể chạy 0, 1 hoặc nhiều KV/Query operations. Khi cần correlation, lưu mỗi operation là một span/event có cùng trace ID nhưng clientContextId riêng. Tránh nén tất cả vào một field `lastQueryId` và vô tình bỏ mất những query đầu request.

## 11. Log chậm tại application boundary với Timer

Đo latency ở tầng ứng dụng giúp biết người dùng thực sự phải đợi bao lâu quanh lời gọi Repository/Template. Ví dụ sau minh họa code đồng bộ có quyền kiểm soát thời điểm:

~~~java
import java.time.Duration;
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public final class OrderHistoryService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHistoryService.class);

    private final OrderRepository repository;
    private final MeterRegistry meters;

    public OrderHistoryService(
            OrderRepository repository,
            MeterRegistry meters) {
        this.repository = repository;
        this.meters = meters;
    }

    public List<OrderDocument> history(String customerId) {
        Timer.Sample sample = Timer.start(meters);
        long started = System.nanoTime();
        String outcome = "success";

        try {
            return repository.findByCustomerId(customerId);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            long elapsedMs =
                    (System.nanoTime() - started) / 1_000_000;

            sample.stop(Timer.builder("app.db.query.duration")
                    .tags("service", "query",
                          "queryShape", "orders_by_customer",
                          "outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meters));

            if (elapsedMs >= 500) {
                log.warn(
                        "event=slow_db_call service=query"
                        + " queryShape=orders_by_customer"
                        + " durationMs={} outcome={}",
                        elapsedMs, outcome);
            }
        }
    }
}
~~~

**Lưu ý:**

- `500 ms` chỉ là **ngưỡng minh họa**, không phải SLO chuẩn cho Couchbase.
- Log không có raw customerId, JSON body hoặc SQL++ parameter.
- `Timer.Sample` ghi cả duration của success và exception; nhưng cách phân loại `outcome=error` còn thô.
- Khi Repository return empty list vì không match, đó có thể là **success**, không phải lỗi Query.
- Code này không tự gắn SQL++ `clientContextId` cho derived query. Nếu muốn correlation chặt với Query Service, cần một hook/SDK path rõ ràng thay vì giả định annotation Repository có cùng API.
- Timer này đo **service method synchronous call**, có thể gồm converter/mapping, không nhất thiết bằng server execution time.

### 11.1. Log theo threshold có thể bỏ sót timeout cao?

Nếu operation throw sau timeout, `finally` vẫn ghi một slow event. Nhưng nếu event loop bị nghẽn, process crash hoặc log pipeline lỗi, không phải mọi request đều có log. Do đó **metrics aggregate và traces** vẫn quan trọng.

## 12. Phân loại lỗi: truy vấn không trả row khác truy vấn thất bại

| Kết quả | Ý nghĩa | Khuyến nghị log |
| --- | --- | --- |
| SQL++ trả 0 rows, HTTP contract cho phép | Query thành công | `success`, rowCount=0 |
| KV get key không tồn tại | Not found có thể hợp lệ | `not_found`, không “Couchbase DOWN” |
| Query syntax/semantic error | Statement hoặc schema sai | `query_invalid` |
| Index không tồn tại/online | Đường query không được phục vụ như plan | `index_unavailable` hoặc error class phù hợp |
| Permission denied | RBAC/identity sai | `permission` |
| Query timeout | Query không hoàn tất trong deadline | `timeout` |
| SQL++ cancelled | Client/server cancellation | `cancelled` |
| Index còn lag | Freshness issue, có thể query success | Freshness metric riêng |
| Cache trả dữ liệu cũ | Query có thể chưa chạy | Cache hit/invalidation, không mặc định DB error |

Đừng dùng raw exception message làm metric tag vì cardinality, biến động version và khả năng lộ SQL parameters. Tạo một classifier hữu hạn từ exception type/cause và test logic của classifier.

## 13. SQL++ Query metrics: dùng đúng phạm vi

Couchbase Query Service có các metrics/metadata có thể mô tả thời gian query, số rows, lỗi, warnings và những giai đoạn xử lý; API và trường cụ thể phụ thuộc Server/SDK version.

Khi cần, SDK `QueryOptions` có thể yêu cầu Query metrics:

~~~java
import com.couchbase.client.java.query.QueryOptions;

QueryOptions options = QueryOptions.queryOptions()
        .metrics(true);
~~~

Khi có metadata:

~~~java
var metadata = result.metaData();
var metrics = metadata.metrics();

// Nếu metrics.isPresent(), đọc các trường metrics tương ứng
// theo API SDK của phiên bản đang dùng.
// Không đoán tên field hoặc đơn vị từ một version khác.
~~~

### 13.1. Không đồng nhất Query execution time và HTTP time

Server query metrics có ranh giới đo khác SDK/application. Một query có thể hoàn thành execution nhanh nhưng client chậm vì network, output lớn, result processing hoặc ứng dụng đợi admission gate trước khi gửi SQL++.

### 13.2. Chỉ ghi số cần thiết

Nên có:

- Query duration và elapsed time theo definition của API.
- Result count/size nếu có.
- Error/warnings count.
- Thời gian/index scan hoặc các timing nội bộ khi profile được bật.
- Server Query request ID và client context ID.
- Query shape, consistency mode, keyspace và version.

Không đưa raw query text có literal khách hàng vào log thông thường.

## 14. EXPLAIN: tìm kế hoạch thực thi, không phải phép đo thời gian

SQL++ `EXPLAIN` mô tả query plan và index được chọn, nhưng **không phải** là một lần chạy business query đầy đủ.

~~~sql
EXPLAIN
SELECT META(o).id AS documentId,
       o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "example"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một index phù hợp để cân nhắc:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

**Dùng `EXPLAIN` để trả lời:**

1. Query dùng named index nào?
2. Có index scan quá rộng không?
3. Có fetch document body từ Data Service không?
4. Có sort/aggregate tốn kém không?
5. Projection có thể cover index không?
6. `LIMIT` được push-down/áp dụng ở giai đoạn nào theo plan?
7. Query generated bởi Spring Data có type discriminator hoặc filter khác query raw không?

### 14.1. Không áp DDL từ health/profiling endpoint

`CREATE INDEX` thuộc migration/deployment. Không tự tạo/rebuild index chỉ để một health check xanh vì DDL có chi phí và yêu cầu quyền khác. Trên production, `EXPLAIN`/index metadata cần được truy cập với RBAC phù hợp.

### 14.2. Plan có thể đổi

Data distribution, statistics, server version, query text/params hoặc index definitions thay đổi làm query plan khác. Trong điều tra slow query, ghi plan **tại thời điểm/sát thời điểm xảy ra sự cố** nếu có thể; đừng dùng một EXPLAIN cũ rồi khẳng định server vẫn thực thi y hệt.

## 15. Query profiling: quan sát các giai đoạn thực thi

Khi Query Service có hỗ trợ profiling, Java SDK có thể gửi tùy chọn profile trên request bằng API tương ứng, ví dụ `QueryProfile.TIMINGS` theo Java SDK 3.x.

~~~java
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryProfile;

QueryOptions diagnosticOptions = QueryOptions.queryOptions()
        .profile(QueryProfile.TIMINGS)
        .metrics(true);
~~~

Profile có thể chứa timing của các operators như index scan, fetch, filter, sort, projection tùy query plan/server version. Dùng nó để phân biệt:

- Chờ index / request consistency.
- GSI scan nhiều entries.
- Fetch document lớn/nhiều.
- Sort hoặc aggregate trên tập dữ liệu lớn.
- Phân phối thời gian trong các operators.
- Tác động của result materialization và client-side handling.

**Quan trọng:** Profile có thể phát sinh chi phí hoặc thêm dữ liệu/metadata vào response. Không bật chi tiết cho **mọi request production vĩnh viễn** nếu chưa đo overhead và chính sách logging. Dùng sampling, temporary flags hoặc synthetic query có kiểm soát.

### 15.1. Lấy profile khi query thành công

Một QueryResult có thể cung cấp metadata profile theo API SDK; ví dụ khái niệm:

~~~java
var metadata = result.metaData();
var profile = metadata.profile();

if (profile.isPresent()) {
    // Phân tích operator timings / scan rows theo
    // schema đang chạy; tránh log raw profile công khai.
}
~~~

Không tự ép `profile.isPresent() == true` nếu query không yêu cầu profile hoặc SDK/server không cung cấp theo version.

### 15.2. Profile có thể không có khi timeout

Query bị timeout/cancel hoặc SDK không nhận được response hoàn chỉnh có thể không có metadata profile trong `QueryResult`. Khi đó cần clientContextId, SDK error context, server-side completed/active requests và metrics để chẩn đoán. **Không fabricate profile** từ elapsed time phía client.

## 16. Active và completed requests: tra cứu ở Query Service

Couchbase Query Service có những nguồn thông tin chẩn đoán như **active requests** và **completed requests**, thường có các system keyspaces `system:active_requests` và `system:completed_requests` trong những phiên bản hỗ trợ. Cấu hình giữ completed requests, sampling/threshold, field names và quyền truy cập thay đổi theo phiên bản.

Trên môi trường được cấp phép, một thao tác khám phá khái niệm:

~~~sql
SELECT *
FROM system:active_requests
LIMIT 10;
~~~

~~~sql
SELECT *
FROM system:completed_requests
LIMIT 10;
~~~

**Không copy nguyên kết quả ra log công khai.** Các rows có thể chứa statement text, địa chỉ/endpoint, client context ID và nội dung hỗ trợ vận hành, có thể nhạy cảm.

### 16.1. Active requests phục vụ câu hỏi gì?

- Có request nào đang chạy/chờ lâu không?
- Chúng thuộc Query Service instance nào?
- Có clientContextId/server requestId để nối log?
- Statement/query shape và trạng thái/trường timing nào được báo?
- Có nhiều request giống nhau cùng tăng không?

### 16.2. Completed requests phục vụ câu hỏi gì?

- Những query nào đã hoàn thành (bao gồm một số query chậm theo cấu hình retention/threshold)?
- Chúng có duration, errors, result counts hoặc profile metadata nào?
- Có request ID/clientContextId để tìm đúng call từ application không?

**Không mặc định mọi Query đều xuất hiện trong completed requests.** Lưu trữ phụ thuộc cấu hình, ngưỡng slow query, bộ nhớ/retention, server version và tải. Một request không có trong bảng **không chứng minh** nó chưa được thực thi.

### 16.3. Tìm theo ID phải đối chiếu field schema thực tế

Những tài liệu/phiên bản khác nhau có thể dùng tên field như `requestId`, `clientContextID` hoặc quy ước khác. Trước khi viết SQL++ filter, xem schema thực ở môi trường được ủy quyền và tài liệu server version. Không xây dashboard dựa trên field tự suy đoán.

## 17. Liên kết request chậm theo một quy trình có thể kiểm chứng

Khi có phản ánh API chậm, đừng bắt đầu bằng việc truy vấn ngẫu nhiên `system:completed_requests`. Một quy trình có trật tự:

1. Tìm `http.requestId` hoặc `trace.id` từ API response/log.
2. Mở trace và chọn đúng DB operation span có `queryShape`.
3. Lấy `clientContextId` mà ứng dụng đã gửi qua QueryOptions.
4. Nếu nhận QueryResult thành công, lấy `serverRequestId` trong Query metadata.
5. Đối chiếu active/completed request logs của Query Service theo **ID, thời gian và service instance**.
6. Mở `EXPLAIN` và profile/metrics của đúng query shape/plan.
7. So với Query Service, GSI Index, SDK/client metrics ở cùng cửa sổ.
8. Kết luận có bằng chứng: Query/Index đang chậm hay trước/sau SDK bị chờ?

~~~mermaid
flowchart TD
    A["HTTP requestId / traceId"] --> B["Application request log"]
    B --> C["DB span + queryShape"]
    C --> D["SQL++ clientContextId"]
    D --> E{"Có serverRequestId?"}
    E -->|Có| F["Query Service request records"]
    E -->|Không| G["SDK error context + time window"]
    F --> H["EXPLAIN, profile và service metrics"]
    G --> H
    H --> I["Root cause / hành động / đo SLO lại"]
~~~

**Khi mất thông tin ở bước nào, ghi rõ giới hạn.** Ví dụ query timeout trước metadata thì không lấy được request ID từ `QueryResult`, nhưng clientContextId được sinh trước dispatch vẫn có ích.

### 17.1. Một HTTP request có thể gọi nhiều SQL++ queries

Một endpoint có thể gọi query A lấy Orders, query B đếm và query C kiểm tra trạng thái. Chúng chia sẻ traceId của HTTP request nhưng có **span ID và clientContextId riêng**, nếu SDK/query hook được instrument như vậy.

### 17.2. ID của một retry không nhất thiết giống ID ban đầu

Phân biệt một logical business operation với nhiều application retries, và các retries do SDK quyết định. Một HTTP request có thể tương ứng nhiều server Query requests. Đừng dùng serverRequestId của một attempt để giải thích toàn bộ logical operation nếu ứng dụng có retry.

## 18. Một wrapper SDK có correlation an toàn

Ví dụ gom việc sinh clientContextId, gửi SQL++, đo elapsed và log metadata trong một boundary. Đây là code đồng bộ, hoạt động trên SDK 3.x hỗ trợ các options được dùng.

~~~java
import java.time.Duration;
import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CorrelatedOrderQueries {
    private static final Logger log =
            LoggerFactory.getLogger(CorrelatedOrderQueries.class);

    private static final String SQL = """
        SELECT META(o).id AS documentId, o.status
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.customerId = $customerId
        ORDER BY o.createdAt DESC
        LIMIT 20
        """;

    private final Cluster cluster;

    public CorrelatedOrderQueries(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult recentOrders(String customerId) {
        String clientId = "orders-" + UUID.randomUUID();
        long startNs = System.nanoTime();

        try {
            QueryResult result = cluster.query(
                    SQL,
                    QueryOptions.queryOptions()
                            .clientContextId(clientId)
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .scanConsistency(
                                    QueryScanConsistency.NOT_BOUNDED)
                            .timeout(Duration.ofSeconds(2)));

            long elapsedMs =
                    (System.nanoTime() - startNs) / 1_000_000;

            log.info("event=db_query service=query"
                    + " shape=orders_recent clientContextId={}"
                    + " serverRequestId={} elapsedMs={}"
                    + " outcome=success",
                    clientId,
                    result.metaData().requestId(),
                    elapsedMs);

            return result;
        } catch (RuntimeException failure) {
            long elapsedMs =
                    (System.nanoTime() - startNs) / 1_000_000;

            log.warn("event=db_query service=query"
                    + " shape=orders_recent clientContextId={}"
                    + " elapsedMs={} outcome=error errorClass={}",
                    clientId,
                    elapsedMs,
                    failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
~~~

**Chú ý:** Mã không log `customerId`, document body, query parameters hoặc raw SQL++ statement. Khi timeout không có QueryResult thì chỉ ghi clientContextId, **không tự tạo một serverRequestId giả**.

### 18.1. SDK success khác HTTP success

DAO có thể nhận QueryResult thành công, nhưng tầng Spring Data converter, JSON serialization hoặc controller sau đó có lỗi. `dbQuery=success` và `httpOutcome=error` có thể cùng đúng; cần rõ boundary đo.

### 18.2. Thêm trace ID thế nào?

Ứng dụng có thể lấy `traceId` từ Micrometer Tracing hoặc MDC theo cấu hình đã được kiểm chứng. Không tự tin gọi `MDC.get("traceId")` và cho rằng nó tồn tại trên mọi Thread/Reactive signal; kiểm tra context propagation trên bản Spring Boot đang chạy.

## 19. Repository và Template không đồng nhất với QueryOptions

Spring Data Couchbase có `CouchbaseRepository`, `@Query` và `CouchbaseTemplate` để dựng SQL++. SDK `Cluster.query` cho phép tùy chỉnh QueryOptions sát với protocol hơn.

**Không mặc định** mọi phiên bản Spring Data đều cho gắn `clientContextId` trên derived query bằng cùng API SDK. Nếu cần:

1. Xác định extension/options API được hỗ trợ trong phiên bản Spring Data đang dùng.
2. Truyền context bằng hook chính thức nếu có.
3. Nếu không có hook phù hợp, instrument ở service/Repository boundary để đo query shape, duration, traceId.
4. Dùng SDK trực tiếp cho những diagnostic operations được kiểm soát, nhưng so SQL++ của SDK và Repository trước khi so latency.
5. Không sửa SDK nội bộ hoặc global mutable query settings chỉ để ép correlation.

### 19.1. Generated SQL++ có thể thêm type discriminator

Spring Data mapper có thể thêm điều kiện type. Raw SDK query trả rows không có nghĩa Repository cùng điều kiện phải trả giống hệt. Khi điều tra, kiểm tra generated SQL++/converter/`@Document` mapping và type filter trước khi quy dữ liệu thiếu là GSI lag.

### 19.2. Cache có thể không gọi Couchbase

Một `@Cacheable` hit ở service có thể trả result mà không gửi SQL++. Không có clientContextId ở Query Service cho HTTP request đó là bình thường. Instrument cache hit/miss và invalidation riêng.

## 20. Tracing với Spring Boot và Micrometer

Nếu ứng dụng thêm Micrometer Tracing và một exporter backend phù hợp, cấu trúc trace mong muốn:

~~~text
HTTP GET /customers/{id}/orders (traceId)
  Service: customerHistory (spanId)
    cache.lookup (spanId)
    couchbase.sqlpp orders_by_customer_recent (spanId)
      event query.dispatched
      event query.completed / query.failed
~~~

Đây là **mô hình cần thiết kế**, không bảo đảm mọi SDK/Boot version tự tạo đủ các spans.

| Span attribute | Nên ghi | Không nên ghi |
| --- | --- | --- |
| Route | `/customers/{id}/orders` | URL gắn customer ID cụ thể |
| Database system | `couchbase` | Login username/secret |
| Operation | `query` / `kv_get` | Raw JSON body |
| Query name | `orders_by_customer_recent` | SQL++ parameter values |
| Keyspace | `shop.sales.orders` nếu policy cho phép | Tenant ID động |
| Query client context | Opaque ID trong trace/log đã bảo vệ | Prometheus label |
| Status | `success/timeout/permission` | Raw exception text có PII |

### 20.1. Tracing sampling và slow request

Sampling giúp giới hạn overhead, nhưng có thể bỏ lỡ một request chậm hiếm. Dù một trace không được sample, metrics/histogram và application logs có correlation tối thiểu nên vẫn đủ cho alert. Nếu muốn tail-based sampling, phải xác minh backend/pipeline hỗ trợ và đánh giá retention/security.

### 20.2. Không đặt request ID làm metric tag

`clientContextId`, `serverRequestId` và `traceId` có cardinality cao. Dùng chúng ở logs/traces có quyền truy cập và lưu giữ hợp lý; metrics dùng service, queryShape, route template và outcome hữu hạn.

## 21. Reactive WebFlux: timer bắt đầu tại subscription

Với `ReactiveCouchbaseRepository` hoặc SDK reactive, tạo một `Mono` chưa chắc đã bắt đầu I/O. Do đó cách sau **đo sai**:

~~~java
long started = System.nanoTime();
Mono<OrderDocument> order = reactiveRepository.findById(id);
long elapsed = System.nanoTime() - started; // chỉ đo tạo Publisher
~~~

Ví dụ wrapper bằng `Mono.defer`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public final class ReactiveQueryTimer {
    private final MeterRegistry registry;

    public ReactiveQueryTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> Mono<T> measure(
            String shape,
            Mono<T> queryPublisher) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            AtomicReference<String> outcome =
                    new AtomicReference<>("success");

            return queryPublisher
                    .doOnError(error ->
                            outcome.set("error"))
                    .doOnCancel(() ->
                            outcome.set("cancelled"))
                    .doFinally(signal ->
                        sample.stop(Timer.builder(
                                "app.couchbase.query.duration")
                                .tags("shape", shape,
                                      "outcome", outcome.get())
                                .register(registry)));
        });
    }
}
~~~

**Caveat:**

- `shape` phải thuộc tập nhãn hữu hạn, không lấy từ SQL++ text/user input.
- Khi có `retryWhen`, vị trí wrapper quyết định đo logical operation hay attempts.
- Nếu Publisher phát nhiều rows qua `Flux`, phải phân biệt time-to-first-row và time-to-terminal-signal.
- `doFinally` giúp ghi sample cả khi error/cancel.
- Một số hệ thống Reactor dùng operator instrumentation khác; cấu trúc này chỉ minh họa boundary.

### 21.1. MDC không tự theo mọi scheduler

WebFlux có thể chuyển thread; dùng Reactor Context hoặc Micrometer context propagation theo version. Viết integration test để chứng minh traceId và clientContextId vẫn được nối đúng khi chuyển scheduler.

### 21.2. Không `block()` trong event loop để lấy profile

Một `block()` trực tiếp trong WebFlux event loop có thể làm nghẽn xử lý HTTP và gây tail latency. Dùng reactive API hoặc chạy diagnostic blocking ngoài event loop với concurrency/timeout giới hạn.

## 22. Timeout khi chưa có server request ID

Một Query timeout có thể khiến không có `QueryResult`, do đó không có metadata để trích `requestId()` theo success path.

Quy trình phù hợp:

1. Sinh opaque clientContextId trước Query call.
2. Log start event hoặc giữ context trong trace/span đã được thiết kế.
3. Gửi QueryOptions với clientContextId.
4. Catch lỗi, ghi elapsed time và error category.
5. Nếu SDK error context có endpoint/request information hữu ích, lấy qua API đúng version và redact.
6. Dựa trên clientContextId + time window để tra Query Service active/completed requests theo quyền và retention thực.
7. Nếu không thấy record, xem Query Service retention/threshold, network/dispatch, timeout hoặc log sampling trước khi kết luận request chưa tới server.

**Không suy client timeout đồng nghĩa server đã ngừng xử lý ngay.** Với một số loại cancellation/timeout, request phía server có thể kết thúc khác thời điểm client hết deadline.

### 22.1. Trường hợp ứng dụng tự retry

Một logical call có thể phát thêm query request ID khác. Nếu SDK cũng retry nội bộ, cần xem retry reason theo SDK instrumentation, không tự đoán số attempts từ số log line. Với query có mutation side effects, timeout và retry cần xem xét idempotency chặt hơn.

## 23. Phân tích các kiểu Query chậm

| Bằng chứng | Giả thuyết | Kiểm tra tiếp |
| --- | --- | --- |
| Plan chọn index không phù hợp | GSI scan quá rộng | `EXPLAIN`, index definitions |
| Scan/fetch nhiều entries | Query thiếu selectivity hoặc không cover | Filter, index keys, projection |
| Sort lớn | Index không hỗ trợ `ORDER BY` tốt | Index order, pushdown, `LIMIT` |
| Query return nhiều rows | Payload và conversion tốn thời gian | Pagination, row count, size |
| SDK chậm nhưng server execution nhanh | Client queue, retries, network, mapping | SDK spans, app admission |
| `REQUEST_PLUS` chậm khi write cao | Index freshness wait | GSI mutation backlog |
| Query engine `SELECT RAW 1` nhanh | Query basic path khỏe | Không suy GSI query khỏe |
| Một pod chậm, pod khác nhanh | Network/CPU/GC/config cục bộ | SDK diagnostics trên từng pod |
| Result rỗng dù KV thấy Order | Query filter/type/cache/index lag | SQL++ plan, mapping, consistency |

### 23.1. EXPLAIN là kế hoạch, profile là đo execution

Không thay profile bằng `EXPLAIN`. Một plan nhìn hợp lý vẫn có thể chậm dưới data distribution/tải thật. Ngược lại, profile của một query có thể không đại diện cho toàn bộ distribution khi nhiều query parameters khác nhau.

### 23.2. Query ở tầng SDK chưa chắc đại diện Repository mapping

Một raw `SELECT RAW META(o).id` có thể cover GSI, trong khi Repository trả entity đầy đủ phải fetch body và deserialize. So p99 của hai câu query khác nhau mà không ghi projection và converter là thiếu căn cứ.

### 23.3. Pagination và Query shape

Nếu `OFFSET` sâu, Query có thể phải xử lý lượng lớn entries trước khi lấy trang cuối. Cân nhắc keyset/seek pagination khi thiết kế domain cho phép, nhưng phải benchmark và xác minh semantics thay vì đổi kỹ thuật một cách máy móc.

## 24. Tính nhất quán có thể khiến truy vấn chậm mà vẫn đúng

| SQL++ scan consistency | Yêu cầu | Tác động latency |
| --- | --- | --- |
| `NOT_BOUNDED` | Không buộc chờ mốc mutation gần nhất của request | Có thể nhanh hơn nhưng cho phép index chưa mới |
| `REQUEST_PLUS` | Chờ index đạt mốc request phù hợp | Có thể chậm nếu backlog |
| `consistentWith(MutationState)` | Chờ các mutation tokens đã cung cấp | Read-after-specific-writes với phạm vi hỗ trợ |

Một API vừa tạo Order và đọc lịch sử có thể yêu cầu read-after-write. Không chuyển `REQUEST_PLUS` sang `NOT_BOUNDED` chỉ vì biểu đồ p99 tăng, nếu điều này vi phạm hợp đồng độ mới.

### 24.1. Log consistency mode

Ghi một giá trị cố định như `consistency=request_plus` hoặc `not_bounded` cùng queryShape giúp phân tích tại sao các query cùng plan lại có latency khác nhau. Không lấy mutation token làm metric label.

### 24.2. Index online vẫn có thể lag

Index Service online không chứng minh GSI đã xử lý mutation cuối. Cần metric backlog/freshness và test theo mutation nếu có SLO về độ mới; một probe Query Engine nhanh không phản ánh điều đó.

## 25. Histogram p95/p99 và SLO theo query shape

Ví dụ **khung mục tiêu** chưa gán benchmark:

~~~text
route: GET /customers/{id}/orders
queryShape: orders_by_customer_recent
latency SLO: threshold do đội thống nhất
availability SLO: success/error theo API contract
time window: rolling 5m / 1h
consistency mode: được ghi rõ
~~~

- p95/p99 phải kèm sample count và histogram bucket resolution.
- Không tính trung bình p99 của nhiều pods để lấy p99 toàn hệ thống.
- Timeout/cancellation phải được báo riêng; success-only latency không đủ.
- Slow-query threshold log nên tách khỏi latency SLO: một dùng để lấy mẫu chẩn đoán, một để đánh giá phục vụ.
- Khi traffic thấp, percentile một phút dễ nhiễu; alert cần điều kiện đủ samples/vi phạm kéo dài.

### 25.1. Slow logs và metrics phục vụ hai câu hỏi khác nhau

Slow logs giúp tìm **những request cá biệt và ID của chúng**. Histogram/metrics cho biết **tần suất và phân phối**. Sampling/retention có thể khiến một phần requests không có log; không lấy thiếu log làm bằng chứng không có lỗi.

## 26. Prometheus: ví dụ query cho Timer tự định nghĩa

Giả sử exporter thực tế của Micrometer chuyển `app.couchbase.query.duration` thành các series sau (tên/version cần được xác minh):

~~~text
app_couchbase_query_duration_seconds_bucket
app_couchbase_query_duration_seconds_count
app_couchbase_query_duration_seconds_sum
~~~

Query rate:

~~~promql
sum by (shape) (
  rate(app_couchbase_query_duration_seconds_count[5m])
)
~~~

p95 cho các query shapes:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, shape) (
    rate(app_couchbase_query_duration_seconds_bucket[5m])
  )
)
~~~

p99 cho Orders query success:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(app_couchbase_query_duration_seconds_bucket{
      shape="orders_by_customer_recent",
      outcome="success"
    }[5m])
  )
)
~~~

**Lưu ý:** Histogram chỉ có khi Timer được cấu hình xuất histogram/SLAs buckets phù hợp. Đừng copy PromQL rồi cho rằng exporter luôn sinh đủ series. Nếu dùng success-only p99, dashboard **phải có timeout/error rate bên cạnh** để tránh báo SLO xanh giả.

### 26.1. Không đưa clientContextId vào labels

ID truy vấn là giá trị duy nhất cho từng operation, gây cardinality explosion. Dùng nó ở logs/traces có quyền truy cập, không để trong Prometheus labels. Tag `shape` thuộc tập tên template cố định.

## 27. Benchmark/query profiling có kiểm soát

Trước khi kết luận tối ưu một GSI làm Query nhanh hơn:

1. Ghi Couchbase Server, Java SDK, Spring Data, Spring Boot và Micrometer versions.
2. Chuẩn bị test cluster riêng, dataset có kích thước và phân phối đại diện.
3. Xác nhận bucket/scope/collection, index definitions/online state.
4. Giữ SQL++ shape, projection, pagination và consistency mode rõ ràng.
5. Warm-up JVM/SDK và prepared query plans nếu thích hợp; tách cold start.
6. Chạy workload theo các mức concurrency có giới hạn.
7. Thu SDK/app/HTTP durations, Query/Index metrics, error/timeouts.
8. Chọn một số queries có profile/metrics sâu, ghi operator timings trong môi trường an toàn.
9. Lưu clientContextId và serverRequestId khi SDK response có metadata.
10. Không bỏ các timeout/cancelled samples khỏi báo cáo tổng.
11. Theo dõi recovery khi hạ tải.
12. Lặp lại; tránh kết luận từ một request chậm.

### 27.1. Coordinated omission

Load generator chỉ phát request tiếp theo khi request trước xong có thể giảm tốc độ gửi đúng lúc server chậm, làm phân phối latency trông tốt hơn một arrival rate cố định. Báo actual QPS, client concurrency và kiểu open-loop/closed-loop khi capacity study.

### 27.2. Không profiling chi tiết mọi request production

Profiling chi tiết có overhead và có thể đưa statement/metadata nhạy cảm vào logs. Đặt sampling/feature flag có thời hạn, giới hạn operator access và tắt sau incident.

## 28. Integration test xác minh query IDs bằng SDK

Một test trên **cluster Couchbase thử nghiệm**, có Query Service và Spring Boot cấu hình Cluster bean:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class QueryCorrelationIT {
    @Autowired
    private Cluster cluster;

    @Test
    void queryResponseContainsServerRequestId() {
        String clientId = "it-" + UUID.randomUUID();

        var result = cluster.query(
                "SELECT RAW 1",
                QueryOptions.queryOptions()
                        .clientContextId(clientId)
                        .metrics(true));

        String serverRequestId = result.metaData().requestId();
        assertNotNull(serverRequestId);
        assertFalse(serverRequestId.isBlank());

        // clientId phải là đúng giá trị đã gửi trong QueryOptions;
        // không assert serverRequestId == clientId.
    }
}
~~~

`SELECT RAW 1` chỉ kiểm tra Query Engine, không chứng minh GSI của Orders online. Muốn test GSI thực, chạy SQL++ theo customerId với index/fixture đúng và xác minh `EXPLAIN`.

### 28.1. Unit test đường query timeout

Fake/mock gateway có thể ném timeout trước khi trả QueryResult; assert clientContextId đã được tạo/gửi, log outcome/error class/duration mà **không truy cập `result.metaData()`**. Test cả redaction: không có full customerId/email/token trong logs.

### 28.2. Không cố tạo Query timeout trên production

Fault test với Query Service/network unavailable phải chạy trên cluster lab cô lập và có runbook khôi phục. Không tắt dịch vụ production để xem completed requests.

## 29. Runbook: tìm nguyên nhân từ request ID

~~~mermaid
flowchart TD
    A["HTTP/API SQL++ chậm"] --> B["Tra traceId / HTTP requestId"]
    B --> C["Tìm queryShape và clientContextId"]
    C --> D{"Có serverRequestId?"}
    D -->|Có| E["Query Service request record"]
    D -->|Không| F["SDK error context, time window"]
    E --> G["EXPLAIN, profile, Query/Index metrics"]
    F --> G
    G --> H{"Query/server hay client/application?"}
    H -->|Server| I["GSI scan/fetch/sort/consistency"]
    H -->|Client| J["Queue/retry/network/mapping/cache"]
    I --> K["Khắc phục và đo lại SLO"]
    J --> K
~~~

**Checklist on-call tuần tự:**

1. Xác định route, thời điểm, mức ảnh hưởng, p95/p99 và error rate.
2. Lấy HTTP request ID/trace ID, tìm các DB spans cùng request.
3. Lấy queryShape và `clientContextId`, phân biệt nhiều SQL++ trong một HTTP call.
4. Nếu có metadata, lưu server request ID; nếu timeout, dùng SDK error context và timestamp.
5. Tra active/completed requests theo schema/retention/permissions của Query Service thực.
6. Ghi `EXPLAIN` cho generated SQL++ của phiên bản đang chạy.
7. So profile/Query metrics với Index Service backlog, Query CPU/queue và server timings.
8. Nếu server nhanh nhưng client chậm, kiểm tra SDK retries, app admission, network, mapper và serialization.
9. Nếu query chờ index, xem consistency mode và freshness SLO.
10. Nếu không có Query ID tại server, xem cache hit hoặc lỗi trước dispatch thay vì đoán.
11. Giới hạn retry/concurrency, điều chỉnh index/query/pagination hoặc capacity theo bằng chứng.
12. Đo lại p95/p99, errors, throughput và business correctness sau thay đổi.
13. Tắt DEBUG/profiling tạm thời, redact incident artifacts và cập nhật runbook.

## 30. Bảo mật khi lưu Query metadata, profile và trace

Một Query profile/completed request có thể chứa SQL++ statement, endpoint, thông tin vận hành và literal dữ liệu nếu code không dùng binding. Request IDs cũng có thể giúp tương quan thông tin khách hàng qua nhiều systems.

**Nguyên tắc:**

- Dùng named parameters trong SQL++.
- Log queryShape thay vì raw statement và parameters.
- `clientContextId` là opaque, không chứa user ID/email/order ID.
- Không gửi query profile/raw SDK exception về public HTTP.
- Quyền xem system keyspaces/completed requests chỉ cho operator phù hợp.
- Giới hạn retention, sampling, rate limit và audit.
- Tách test credentials/namespace khỏi production.
- Ẩn host/private IP, TLS details và credential khi chia sẻ incident.
- Dùng correlation ID cho hỗ trợ khách hàng nhưng không tiết lộ dữ liệu truy vấn.

### 30.1. Đừng làm mất khả năng chẩn đoán vì redact quá mức

Giữ `queryShape`, duration, outcome, timestamp và opaque IDs ở kênh bảo mật để nối sự kiện. Cân bằng giữa quyền riêng tư và khả năng điều tra, thay vì công khai toàn bộ SQL parameters.

## 31. Những lỗi phổ biến

1. Gộp HTTP request ID và server Query request ID thành một field.
2. Sinh clientContextId nhưng quên truyền vào QueryOptions.
3. Gắn cùng clientContextId cho hàng nghìn SQL++ calls.
4. Log SQL parameters hoặc full customerId cùng raw statement.
5. Dùng traceId/clientContextId/serverRequestId làm metric labels.
6. Chỉ ghi “Couchbase timeout” không có queryShape/operation.
7. Đọc QueryResult metadata ở catch block khi result chưa tồn tại.
8. Completed requests không có record thì khẳng định Query chưa chạy.
9. `SELECT RAW 1` chạy được thì coi GSI Orders khỏe.
10. `EXPLAIN` được coi như execution profiler.
11. Bật `QueryProfile.TIMINGS` trên toàn bộ traffic mãi mãi.
12. Coi Query server duration và HTTP latency có cùng boundary.
13. Bỏ timeout/error samples làm p99 đẹp giả.
14. Lấy average p99 của từng pod thành fleet p99.
15. Không xét QUERY `REQUEST_PLUS` đang chờ GSI backlog.
16. Tối ưu query raw SDK nhỏ rồi suy Repository entity mapping tương đương.
17. Không phân biệt cache hit với query mới.
18. Nhầm empty rows với Query Service failure.
19. Không kiểm thử WebFlux trace context propagation.
20. Đo reactive Mono trước khi subscription.
21. Không tính stream cancellation hoặc time-to-first-row.
22. Cho end users truy cập raw `system:completed_requests`.
23. Tạo synthetic heavy query ở liveness/readiness.
24. Thử network partition trên production để kiểm tra timeout.
25. Tăng Query timeout vô hạn mà không xem query plan, capacity hoặc RBAC.
26. Quên giảm SDK DEBUG/profiling sau incident.

## 32. Bài tập tình huống

### A. Có ba ID

Một HTTP request có HTTP request ID, Query clientContextId và server request ID.

**Yêu cầu:** Giải thích ai sinh mỗi ID và cách nối chúng.

**Đáp án định hướng:** HTTP/gateway/app, client QueryOptions và Query Service tương ứng; lưu chúng trong một operation event/span để correlate, không buộc giá trị bằng nhau.

### B. Query timeout không có metadata

Developer cố lấy `result.metaData().requestId()` khi `cluster.query` throw.

**Đáp án:** Sinh clientContextId trước call, log start/failed event, dùng error context và server diagnostics khi có; không fabricate server request ID.

### C. SELECT RAW 1 nhanh, Query lịch sử chậm

**Đáp án:** Query Engine có thể khỏe trong khi GSI/index plan/fetch/sort/consistency wait gây chậm. Dùng `EXPLAIN`, profile, Index metrics và SDK timeline.

### D. GSI chưa thấy Order mới

KV get thấy Order nhưng `NOT_BOUNDED` query chưa thấy.

**Đáp án:** Phân biệt freshness và availability; kiểm tra GSI update, lựa chọn `REQUEST_PLUS` hoặc mutation-state consistency khi nghiệp vụ cần.

### E. p99 success thấp, timeout tăng

**Đáp án:** SLO không thể coi là tốt; báo error rate và success-only latency riêng, không bỏ timeout.

### F. Trace mất sau chuyển scheduler WebFlux

**Đáp án:** Dùng Reactor Context/Micrometer context propagation đúng version, kiểm thử spans end-to-end và MDC, không suy ThreadLocal tự hoạt động.

### G. Query profile chứa dữ liệu khách hàng

**Đáp án:** Redact/ẩn dữ liệu, RBAC admin-only, retention/sampling; không xuất raw profile ra ticket công khai.

### H. Completed requests rỗng khi client chậm

**Đáp án:** Kiểm tra retention/threshold/server version, request có tới Query Service hay không và SDK/client queue; bảng rỗng chưa đủ kết luận.

### I. Một HTTP call chạy ba Query requests

**Đáp án:** Một trace ID chung, ba spans/clientContextIds khác nhau, mỗi server request ID tương ứng khi có.

### J. LIMIT 20 nhưng query vẫn sort nhiều

**Đáp án:** Xem `ORDER BY`, leading index keys, plan pushdown, scan count và data distribution; không chỉ thêm LIMIT.

## 33. Checklist trước khi triển khai

- [ ] Slow-query SLO theo route/queryShape, không một ngưỡng chung?
- [ ] HTTP requestId, traceId, clientContextId, serverRequestId được phân biệt?
- [ ] clientContextId tạo trước dispatch, truyền vào QueryOptions và log khi fail?
- [ ] Mỗi SQL++ operation có correlation riêng khi một HTTP call tạo nhiều queries?
- [ ] Không bịa requestId server nếu SDK timeout?
- [ ] Traces nối Controller → Service → Repository/SDK đúng version?
- [ ] Logs có queryShape, duration, keyspace, consistency, outcome?
- [ ] Không log SQL params, customerId, credential, document body?
- [ ] Không dùng opaque request IDs làm Prometheus metric tags?
- [ ] QueryResult metaData/metrics/profile được đọc đúng SDK API/version?
- [ ] Có phân biệt Query server execution, SDK client, app mapper và HTTP duration?
- [ ] `EXPLAIN` dựa trên generated SQL++ và index plan hiện hành?
- [ ] Profile chỉ bật có tần suất/thời hạn/overhead được kiểm soát?
- [ ] System active/completed requests có retention, RBAC và field schema rõ?
- [ ] Empty completed-record list không bị coi là request chưa chạy?
- [ ] Đã xem Index backlog và consistency mode khi Query p99 tăng?
- [ ] Cache hit/miss và mapping issues được đo/điều tra riêng?
- [ ] Retry ở app và SDK có logical/attempt correlation đúng?
- [ ] WebFlux timer bắt đầu lúc subscribe, ghi complete/error/cancel?
- [ ] Query shape metrics có histogram/count và timeout rate riêng?
- [ ] Percentiles có sample count và bucket resolution hợp lý?
- [ ] Không lấy average p99 từ nhiều pods?
- [ ] Test IDs, slow query threshold và redaction trên môi trường cô lập?
- [ ] Fault injection không thực hiện trên production?
- [ ] Diagnostic system keyspaces và Query profiles không công khai?
- [ ] Runbook có bước nối trace ID tới server request/profile/plan?
- [ ] Có đo lại SLO và tắt debug/profiling sau incident?

## 34. Câu hỏi tự đánh giá

**1. clientContextId có phải Query requestId của server?** Không. Client gửi ID ngữ cảnh; Query Service cấp ID riêng.

**2. Tại sao clientContextId phải tạo trước query?** Vì timeout có thể không trả QueryResult metadata, nhưng vẫn cần ID tương quan trong log lỗi.

**3. `EXPLAIN` cho biết điều gì?** Query plan và index được chọn, không phải timing của một execution đầy đủ.

**4. Query profile dùng làm gì?** Phân tích các giai đoạn/operator timings khi có; có overhead và cần quyền/bảo mật.

**5. Tại sao completed_requests có thể không chứa query đang tìm?** Retention, slow threshold, version, sampling, cancellation hoặc request chưa tới server.

**6. Query `SELECT RAW 1` nhanh có bảo đảm GSI của Orders online?** Không.

**7. Query `REQUEST_PLUS` chậm có chắc Query Service down?** Không; có thể chờ GSI bắt kịp mutation.

**8. Reactive timer nên bắt đầu lúc nào?** Tại subscription thực hiện I/O, kết thúc ở terminal signal/cancellation theo scope đã định.

**9. Vì sao không đưa request ID vào metric labels?** Cardinality rất cao, tốn lưu trữ và có thể lộ thông tin tương quan.

**10. Có nên log raw SQL++ parameter để debug?** Không ở logs thông thường; dùng query shape và redacted context.

## 35. Kết luận

**Theo dõi truy vấn chậm của Spring Data Couchbase là bài toán kết nối trải nghiệm người dùng tới đúng SQL++ request và query plan.** HTTP request/trace ID, `QueryOptions.clientContextId`, Query Service request ID và SDK error context có phạm vi riêng; khi được liên kết đúng, chúng giúp tìm được một query cụ thể thay vì chỉ thấy “Database timeout”.

Hãy ghi **query template, duration, outcome, consistency mode và ID tương quan** ở mức an toàn; dùng `EXPLAIN` để xem plan, Query metrics/profile để tìm giai đoạn tốn thời gian, active/completed requests để đối chiếu server và tracing để xem thời gian trước/sau SDK. Phân biệt **application queue, network/retry, Query Service, Index Service, mapping và cache**, đồng thời báo p95/p99 cùng timeout/error rate.

Một hệ thống dễ vận hành là hệ thống **có thể truy lại đúng request, giải thích bằng bằng chứng vì sao nó chậm, khắc phục an toàn và đo lại SLO mà không làm lộ dữ liệu hoặc đánh đổi tính nhất quán**.
