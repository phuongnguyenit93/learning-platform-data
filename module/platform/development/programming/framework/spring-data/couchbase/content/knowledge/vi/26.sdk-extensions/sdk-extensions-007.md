# Metadata, cảnh báo và số liệu của kết quả truy vấn

Trong **Spring Data Couchbase**, một câu SQL++ có thể trả đúng các document cần tìm nhưng vẫn chậm, dùng chỉ mục chưa phù hợp hoặc phát sinh cảnh báo. Nếu tầng truy cập chỉ lấy `rows` rồi bỏ phần còn lại, ứng dụng sẽ khó trả lời: **truy vấn nào chậm, phần chậm xảy ra ở máy chủ hay phía client, request nào tương ứng với log Couchbase và liệu kết quả có đi kèm cảnh báo?**

**Couchbase Java SDK** không chỉ trả dữ liệu. Với SQL++ Query Service, `QueryResult` đi kèm `QueryMetaData`, trong đó có định danh request, trạng thái, warnings, metrics, result signature và profiling nếu được yêu cầu. Analytics Service và Search Service cũng có metadata nhưng **kiểu Java và ngữ nghĩa số liệu khác nhau**; không nên gom mọi loại truy vấn vào một bộ thuộc tính giả định giống hệt nhau.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**. Trong quá trình xây dựng tầng truy cập bằng document mapping, Repository, `CouchbaseTemplate`, SQL++, chỉ mục, TTL, CAS, transaction và API reactive, chúng ta cần biết không chỉ **lấy dữ liệu bằng cách nào**, mà còn **kiểm chứng và quan sát kết quả truy vấn ra sao**.

> **Nguyên tắc trọng tâm:** **Rows là dữ liệu nghiệp vụ; metadata là thông tin về việc thực thi truy vấn.** Bật metrics có chủ đích, đọc đúng `Optional`, xử lý warnings theo mức độ nghiêm trọng, đo độ trễ đầu-cuối riêng và chỉ bật profiling nặng khi chẩn đoán. Metadata **không tự bảo đảm** số liệu đúng nghiệp vụ, kết quả hoàn chỉnh hay snapshot nhất quán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `rows` và `QueryMetaData` trong `QueryResult` của Couchbase Java SDK.
2. Truy xuất `requestId()`, `clientContextId()`, `status()`, `warnings()`, `metrics()`, `signature()` và `profile()`.
3. Hiểu vì sao `QueryMetaData.metrics()` là `Optional<QueryMetrics>` và cách bật `queryOptions().metrics(true)`.
4. Diễn giải đúng `elapsedTime`, `executionTime`, `resultCount`, `resultSize`, `sortCount`, `mutationCount`, `errorCount` và `warningCount`.
5. Phân biệt **server-reported timings** với latency quan sát tại Java/HTTP.
6. Biết warnings khác exception, và nhận diện lỗi mapping, timeout, server-side failure hoặc partial results ở từng loại service.
7. Dùng `QueryProfile.PHASES`/`TIMINGS` để điều tra truy vấn chậm, nhưng không bật toàn cục không kiểm soát.
8. Dùng `clientContextId` để liên kết request ứng dụng với Couchbase logs và query monitoring.
9. Đọc metadata của **Analytics** và **Search** mà không trộn nhầm kiểu `QueryMetrics`/`AnalyticsMetrics`/`SearchMetrics`.
10. Thu thập metadata đúng thời điểm khi dùng **ReactiveQueryResult**, tránh chờ metadata trước khi tiêu thụ rows.
11. Thiết kế SDK adapter, monitoring, integration tests và chính sách log an toàn cho dữ liệu đa tenant.
12. Phân biệt count nghiệp vụ, số row trả về và số document thực sự được xử lý.

## 2. Bối cảnh: truy vấn trả 20 đơn hàng nhưng rất chậm

Giả sử đơn hàng nằm ở `shop.sales.orders`:

~~~json
{
  "tenantId": "tenant-01",
  "status": "PAID",
  "channel": "WEB",
  "totalCents": 245000,
  "createdAt": "2026-11-24T09:15:00.000Z"
}
~~~

API:

~~~http
GET /orders?status=PAID&page=0&size=20
~~~

SQL++ tương ứng:

~~~sql
SELECT META(o).id AS id,
       o.status AS status,
       o.totalCents AS totalCents,
       o.createdAt AS createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT $limit OFFSET $offset;
~~~

Giả sử HTTP response có 20 items sau 480 ms. Chỉ nhìn rows chưa thể biết:

- Query Service tốn 400 ms hay 15 ms?
- Phần nào do index scan, `Fetch`, sort hoặc queueing?
- JSON decoding hay ứng dụng hydrate thêm dữ liệu có đắt không?
- Mạng/client thread pool đang nghẽn không?
- Query có warning nhưng vẫn thành công không?
- Query này có request ID nào để liên hệ với diagnostic logs?
- `LIMIT 20` có khiến Query Service chỉ xem 20 documents không?

**Metadata và đo client** giúp đặt đúng câu hỏi. **`EXPLAIN`/profiling** đi sâu vào nguyên nhân, còn kết quả business vẫn phải được kiểm thử riêng.

## 3. Cấu trúc phản hồi SQL++ Query Service

Một JSON response của Query Service có thể có dạng khái niệm:

~~~json
{
  "requestID": "server-request-id",
  "clientContextID": "orders-list-req-42",
  "signature": {
    "id": "string",
    "status": "string",
    "totalCents": "number",
    "createdAt": "string"
  },
  "results": [
    {
      "id": "order::1001",
      "status": "PAID",
      "totalCents": 245000,
      "createdAt": "2026-11-24T09:15:00.000Z"
    }
  ],
  "status": "success",
  "metrics": {
    "elapsedTime": "25ms",
    "executionTime": "18ms",
    "resultCount": 1,
    "resultSize": 118
  }
}
~~~

**Đây là sơ đồ minh họa**, không phải payload cố định: `signature`, `metrics`, `warnings` và `profile` có thể vắng mặt hoặc khác cấu trúc theo request options, câu query và phiên bản Server.

SDK chuyển thành:

~~~text
QueryResult
  ├── rowsAsObject()     -> List<JsonObject>
  ├── rowsAs(Class<T>)  -> List<T>
  └── metaData()        -> QueryMetaData
       ├── requestId()         -> String
       ├── clientContextId()   -> String
       ├── status()            -> QueryStatus
       ├── warnings()          -> List<QueryWarning>
       ├── metrics()           -> Optional<QueryMetrics>
       ├── signature()         -> Optional<JsonObject>
       └── profile()           -> Optional<JsonObject>
~~~

Không đọc `results` như một Java document entity có CAS. Những row có alias `id` chỉ là kết quả query; chúng không tự nhận metadata entity của Spring Data.

## 4. `QueryResult` gồm dữ liệu và metadata

Một truy vấn đơn giản:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryMetaData;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public void inspectQuery(Cluster cluster) {
    QueryResult result = cluster.query(
            "SELECT 1 AS value",
            queryOptions().metrics(true));

    for (JsonObject row : result.rowsAsObject()) {
        System.out.println("Business row: " + row);
    }

    QueryMetaData meta = result.metaData();

    System.out.println("requestId = " + meta.requestId());
    System.out.println("clientContextId = " + meta.clientContextId());
    System.out.println("status = " + meta.status());
}
~~~

Với blocking Java SDK, `QueryResult.rowsAsObject()` trả `List<JsonObject>`. Nó không phải `Flux` và không tự stream một số lượng vô hạn theo backpressure. Nếu query trả hàng triệu rows, cần phương án streaming/reactive hoặc phân trang/batch thay vì lấy một `List` rất lớn.

Nếu query thành công mà không có row, `result.rowsAsObject()` có thể là danh sách rỗng **nhưng vẫn có metadata hợp lệ**. Không đánh đồng `0 rows` với lỗi truy vấn.

## 5. Bật `metrics(true)` và xử lý `Optional`

Trong Java SDK SQL++ Query Service, metadata có:

~~~java
Optional<QueryMetrics> metrics()
~~~

Điều này có nghĩa là **metrics có thể không được gửi**. Tài liệu Java SDK hướng dẫn bật:

~~~java
import com.couchbase.client.java.query.QueryMetrics;

QueryResult result = cluster.query(
        "SELECT 1 AS value",
        queryOptions().metrics(true));

QueryMetaData meta = result.metaData();

meta.metrics().ifPresent(metrics -> {
    System.out.println("elapsed = " +
            metrics.elapsedTime());
    System.out.println("execution = " +
            metrics.executionTime());
    System.out.println("result count = " +
            metrics.resultCount());
});
~~~

**Không viết:**

~~~java
// Sai giả định: metrics luôn hiện diện.
QueryMetrics metrics = result.metaData().metrics().get();
~~~

nếu request chưa bảo đảm bật metrics hoặc không xử lý trường hợp thiếu. `Optional.get()` có thể ném `NoSuchElementException` và che nguyên nhân thật.

Hướng an toàn:

~~~java
QueryMetrics metrics = result.metaData()
        .metrics()
        .orElseThrow(() -> new IllegalStateException(
                "Query metrics not returned"));
~~~

Cách này phù hợp **trong test kiểm tra observability** khi metrics bắt buộc. Trong service sản xuất, thường nên xử lý thiếu metrics bằng log/metric tương ứng, không biến một truy vấn nghiệp vụ thành lỗi chỉ vì không nhận được telemetry tùy chọn.

### Bật metrics trên mọi query?

`metrics(true)` có chi phí thấp hơn full query profiling và thường phù hợp với truy vấn cần quan sát ở production. Nhưng hãy cân nhắc:

- Latency và kích thước response theo tải thực.
- Có cần metrics ở mọi request hay chỉ query quan trọng/sampling?
- Chính sách log/traces và cardinality.
- SLA API: có được phép làm query business fail chỉ vì không có metrics không?

Đừng mặc định một cấu hình quan sát hiệu năng cần xuất toàn bộ metadata về frontend.

## 6. Những trường quan trọng của `QueryMetaData`

| Method | Kiểu Java | Dùng để làm gì? |
| --- | --- | --- |
| `requestId()` | `String` | Định danh request do Query Service trả, phục vụ chẩn đoán phía server |
| `clientContextId()` | `String` | Correlation ID do SDK sinh hoặc ứng dụng đặt |
| `status()` | `QueryStatus` | Trạng thái mà Query Service báo cho request |
| `warnings()` | `List<QueryWarning>` | Cảnh báo không terminal; có thể rỗng |
| `metrics()` | `Optional<QueryMetrics>` | Timings/counters nếu được yêu cầu và trả về |
| `signature()` | `Optional<JsonObject>` | Mô tả shape kết quả nếu có |
| `profile()` | `Optional<JsonObject>` | Phân tích plan/timings nếu bật profile |

`Optional` là một phần **hợp đồng Java API**, không chỉ là cách trình bày. Khi có trường absent, điều đúng là **“không có metadata đó”**, không phải tự ghi `0 ms`, `0 rows` hoặc profile rỗng có ý nghĩa.

`warnings()` trả list; list rỗng nghĩa là Query Service không gửi cảnh báo trong metadata, **không chứng minh** query đúng nghiệp vụ hay index đã tối ưu.

## 7. `requestId` và `clientContextId` khác nhau thế nào?

Hai định danh phục vụ cùng mục tiêu truy vết nhưng có nguồn gốc khác:

- **`requestId()`**: được dịch vụ phía Couchbase tạo cho request cụ thể.
- **`clientContextId()`**: SDK Java có thể tự tạo một UUID và gửi theo request; ứng dụng cũng có thể đặt một giá trị có ý nghĩa.

~~~java
import java.util.UUID;

String correlationId = "orders-list-" + UUID.randomUUID();

QueryResult result = cluster.query(
        "SELECT 1 AS value",
        queryOptions()
                .clientContextId(correlationId)
                .metrics(true));

QueryMetaData meta = result.metaData();

System.out.println("clientContextId=" +
        meta.clientContextId());
System.out.println("requestId=" +
        meta.requestId());
~~~

Điều nên làm:

1. Dùng `clientContextId` để kết nối log ứng dụng, telemetry và query request.
2. Giữ `requestId` khi báo lỗi để người vận hành tra cứu Query Service.
3. Không đưa tenant PII, email, token, password hoặc nguyên câu SQL++ chứa bí mật vào ID.
4. Không dùng cùng một `clientContextId` cố định cho mọi request, nếu không sẽ rất khó phân biệt các sự kiện.
5. Nếu có retry, mỗi lần thực thi có thể có request ID mới; ứng dụng có thể giữ chung correlation ID ở mức business command và thêm attempt ID.
6. Không xem hai ID là token cho CAS, transaction, consistency hay idempotency.

### Mẫu correlation gồm nhiều lớp

~~~text
HTTP traceId:       trace-abc123
Business operation: list-paid-orders
SDK clientContextId:orders-list-...-attempt-1
Server requestId:   query-service-generated-id
~~~

Có thể dùng tracing framework để liên kết các lớp; khi log ở SDK adapter, lưu tên operation đã allowlist và định danh truy vết, không log raw PII.

## 8. `QueryMetrics.elapsedTime` và `executionTime`

`QueryMetrics` có hai timing chính:

~~~java
Duration elapsed = metrics.elapsedTime();
Duration execution = metrics.executionTime();
~~~

Theo SDK:

- **`elapsedTime()`**: thời gian tổng từ khi Query Service nhận request đến khi kết quả được trả ở phạm vi thời gian mà server báo.
- **`executionTime()`**: thời gian phần thực thi request, từ khi bắt đầu execution tới khi server trả kết quả theo định nghĩa của Query Service.

Cả hai là `java.time.Duration`, không phải `long` milliseconds. Muốn hiển thị:

~~~java
System.out.println("Server elapsed ms = " +
        metrics.elapsedTime().toMillis());

System.out.println("Server execution ms = " +
        metrics.executionTime().toMillis());
~~~

**Không hiểu** `elapsedTime` là toàn bộ độ trễ HTTP tại trình duyệt. Nó không bao gồm toàn bộ thời gian mạng/client JSON decoding/controller/business processing theo một định nghĩa thống nhất cho ứng dụng.

### Ví dụ đo minh họa

| Lớp | Thời gian minh họa |
| --- | ---: |
| Server execution (QueryMetrics) | 18 ms |
| Server elapsed (QueryMetrics) | 25 ms |
| JVM measured Query SDK call + decode | 43 ms |
| HTTP endpoint end-to-end | 72 ms |

Số liệu chỉ minh họa. Các khoảng thời gian **có thể chồng lấn**, phụ thuộc API timing và serialization. Không trừ chúng một cách máy móc rồi khẳng định phần chênh là “độ trễ mạng” hoặc “thời gian parsing” chính xác.

## 9. Đo latency tại Java bên cạnh metadata server

Một cách đo request từ phía ứng dụng:

~~~java
import java.time.Duration;

long started = System.nanoTime();

QueryResult result = cluster.query(
        "SELECT 1 AS value",
        queryOptions().metrics(true));

var rows = result.rowsAsObject();
long observedNanos = System.nanoTime() - started;

Duration clientElapsed = Duration.ofNanos(observedNanos);

System.out.println("Client observed = " +
        clientElapsed.toMillis() + " ms");
~~~

`System.nanoTime()` phù hợp đo **duration**; không dùng `System.currentTimeMillis()` như đồng hồ có độ phân giải cao chính xác tuyệt đối cho microbenchmark.

Nên định nghĩa rõ điểm bắt đầu/kết thúc:

- Từ ngay trước `cluster.query(...)` tới sau `rowsAsObject()`.
- Từ service entry tới sau mapping DTO.
- Từ controller entry tới khi server hoàn tất gửi HTTP response.
- Từ frontend gửi tới khi render xong.

Bốn phép đo trả lời **bốn câu hỏi khác nhau**. Khi so sánh index/query options, giữ cùng phạm vi đo, concurrency và dataset; không lấy số server của một query đem so với HTTP p95 của endpoint khác rồi kết luận.

## 10. Các counters trong `QueryMetrics`

Tài liệu SDK liệt kê:

| Method | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `resultCount()` | `long` | Số result rows do query trả |
| `resultSize()` | `long` | Số byte của result rows theo server |
| `sortCount()` | `long` | Số kết quả được chọn/đưa vào giai đoạn liên quan sort trước giới hạn `LIMIT` theo định nghĩa Query Service |
| `mutationCount()` | `long` | Số mutation thực hiện bởi query, nếu có |
| `errorCount()` | `long` | Số lỗi server ghi nhận cho request |
| `warningCount()` | `long` | Số cảnh báo server ghi nhận |
| `elapsedTime()` | `Duration` | Server elapsed time |
| `executionTime()` | `Duration` | Server execution time |

Code:

~~~java
meta.metrics().ifPresent(m -> {
    System.out.println("resultCount=" + m.resultCount());
    System.out.println("resultSize=" + m.resultSize());
    System.out.println("sortCount=" + m.sortCount());
    System.out.println("mutationCount=" + m.mutationCount());
    System.out.println("errorCount=" + m.errorCount());
    System.out.println("warningCount=" + m.warningCount());
});
~~~

Các counters **không phải**:

- Số documents đã được KV get ở toàn bộ service.
- Số index entries được scan, nếu API không nói thế.
- Số kết quả ở mọi trang.
- Số entity trong bucket.
- Số HTTP bytes đã truyền trên mạng.
- Tình trạng chính xác của dataset ở một snapshot xuyên request.

Với chỉ số “index entries scanned” hoặc operator bottleneck, xem **profiling, `EXPLAIN` và Query Service monitoring**, không ép `resultCount`/`sortCount` thành chỉ số đó.

## 11. `resultCount` không phải tổng số bản ghi phù hợp bộ lọc

Một truy vấn:

~~~sql
SELECT META(o).id AS id, o.status
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
LIMIT 20;
~~~

Có thể có 100.000 đơn hàng PAID nhưng server chỉ trả **20 rows**; `metrics.resultCount()` tương ứng với số rows kết quả của request, **không phải 100.000**.

Tương tự:

~~~sql
SELECT COUNT(1) AS totalOrders
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID";
~~~

Query này thường trả **một row**:

~~~json
{
  "totalOrders": 100000
}
~~~

Với query count đó, `metrics.resultCount()` thường là **1**, trong khi `row.getLong("totalOrders")` là **100000**.

Đừng xây `Page<T>` từ `QueryMetrics.resultCount`. Nếu API cần total, dùng câu `COUNT` đúng predicate và ngữ nghĩa; với `GROUP BY` cần đếm **nhóm**, không đếm documents nguồn.

## 12. `resultSize` không phải toàn bộ network payload

`resultSize()` được SDK mô tả là số byte của **kết quả query**. Nó không nên bị hiểu là:

- Kích thước của toàn bộ JSON envelope có mọi metadata.
- Tổng byte các request retransmission, TLS/TCP overhead.
- Kích thước object Java sau decoding.
- Kích thước HTTP JSON response mà Spring trả về client.
- Tổng kích thước của mọi document nguồn đã đọc.

Ví dụ: truy vấn trả 20 DTO nhỏ có `resultSize` thấp, nhưng Query Service vẫn có thể scan hàng triệu index entries. Ngược lại `SELECT o.*` có thể trả body lớn làm `resultSize`/heap lớn.

Do đó quan sát cả:

1. `resultSize`, `resultCount`.
2. Response/client bytes nếu telemetry mạng cung cấp.
3. JVM heap/GC, decoding latency.
4. Query plan, scanned rows và Fetch/sort.
5. CPU/memory/IO của Query Service.

Giảm response payload bằng projection có thể giúp đáng kể nhưng chưa chắc sửa được root cause nếu predicate/index quá tốn.

## 13. `sortCount` và chi phí `ORDER BY`

Một truy vấn:

~~~sql
SELECT META(o).id AS id, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT 20 OFFSET 1000;
~~~

`sortCount()` có thể hữu ích khi đánh giá giai đoạn sort và số kết quả trước giới hạn. Nhưng không suy ra trực tiếp:

~~~text
sortCount = số index entries scanned
~~~

hoặc:

~~~text
sortCount = tổng số document khớp WHERE
~~~

Mức chi tiết phụ thuộc kế hoạch thực thi, index order và Server version.

Hãy kiểm tra:

- Có index hỗ trợ predicate và sort không?
- Query có operator `Order`/`Fetch` không?
- Sort có phải xử lý nhiều rows trước `LIMIT/OFFSET` không?
- Có thể dùng keyset/seek pagination thay vì offset sâu không?
- `sortCount` giảm có đi kèm latency/memory giảm trong benchmark không?

`sortCount` là **tín hiệu**, không phải lời giải thích hoàn chỉnh. Khi cần nguyên nhân, dùng `EXPLAIN` và profiling operator-level.

## 14. `mutationCount` không phải CAS hoặc durability

Nếu chạy một SQL++ DML statement có mutation, `mutationCount()` có thể phản ánh số mutation server đã thực hiện.

~~~sql
UPDATE `shop`.`sales`.`orders` AS o
SET o.reviewed = TRUE
WHERE o.tenantId = $tenantId
  AND o.status = "PAID";
~~~

Ví dụ chỉ để giải thích metadata; không chạy câu cập nhật diện rộng trên production mà không có điều kiện/đánh giá.

Quan trọng:

- `mutationCount` không phải `CAS`/`@Version` của bất kỳ document nào.
- Không chứng minh mutation đạt mức durability mong muốn nếu không có chính sách phù hợp.
- Không thay thế việc kiểm tra business invariant và audit.
- Không dùng nó để tự đoán số documents đã tồn tại trước mutation nếu DML có điều kiện phức tạp.
- Nếu timeout/exception, phải phân loại kết quả có thể ambiguous; không tự khẳng định mutationCount=0 chỉ vì client không nhận metadata.

Với thao tác KV `collection.replace(...)`, đối tượng kết quả là loại KV `MutationResult` có CAS/mutation token; **nó không trả QueryMetaData**. Chọn đúng metadata cho đúng API.

## 15. Cảnh báo không giống lỗi kết thúc truy vấn

`QueryMetaData.warnings()` trả một `List<QueryWarning>`. Warnings là các thông báo không terminal do engine tạo trong quá trình truy vấn.

~~~java
import com.couchbase.client.java.query.QueryWarning;

QueryMetaData meta = result.metaData();

for (QueryWarning warning : meta.warnings()) {
    System.out.println(
            "Warning code=" + warning.code());
    System.out.println(
            "Warning message=" + warning.message());
}
~~~

Một request có thể **thành công** và trả đầy đủ rows theo hợp đồng engine, nhưng vẫn có warnings đáng xem xét.

Ví dụ tình huống cần chú ý:

- Engine chọn một đường thực thi/tối ưu có hạn chế đáng quan sát.
- Có dữ liệu hoặc tình huống bất thường được query engine cảnh báo.
- Một hành vi sẽ đổi trong phiên bản tương lai.
- Một câu truy vấn có điều kiện không như ý định.

**Không bịa mã warning cụ thể** để viết logic sản xuất nếu chưa kiểm chứng với Couchbase Server version thực tế. `warning.code()` có thể phù hợp cho phân loại theo allowlist, còn `warning.message()` là text phục vụ chẩn đoán, có thể thay đổi.

### Policy đề xuất

1. Nếu warnings rỗng, ghi nhận `warningCount=0` khi server có metrics hoặc đơn giản bỏ qua.
2. Nếu warning code có ảnh hưởng đúng/sai theo quy tắc đã định, **nâng severity** và kiểm tra integration test.
3. Nếu chỉ là thông tin chẩn đoán, log code với sampling để tránh spam.
4. Không trả raw warning message có query/body/PII lên client không có quyền.
5. Không biến tất cả warnings thành 500: làm vậy có thể gây outage vì cảnh báo không terminal.
6. Không mặc định mọi warning vô hại: báo cáo quyết toán có thể yêu cầu review và chặn công bố.

## 16. `warningCount` và danh sách warnings không phải một thứ

Khi bật metrics, có:

~~~java
long count = meta.metrics()
        .map(QueryMetrics::warningCount)
        .orElse(-1L);
~~~

Trong khi:

~~~java
int returnedWarnings = meta.warnings().size();
~~~

Hai giá trị có mục đích khác nhau:

- `warningCount` do Query Service báo trong metrics, nếu metrics có mặt.
- `warnings().size()` là số warning objects SDK nhận được.

Đừng buộc chúng bằng nhau trong mọi phiên bản/trường hợp: server có thể áp dụng giới hạn/thay đổi cách biểu diễn warnings hoặc metrics không được gửi. Nếu thấy khác nhau, lưu thông tin chẩn đoán thay vì tự sửa dữ liệu business.

**Không dùng `orElse(0L)` rồi nói server chắc chắn có 0 warnings** khi metadata metrics vắng mặt. Trong telemetry nên phân biệt `0` với **unknown/not-collected**.

## 17. `QueryStatus` và lỗi query

`meta.status()` báo trạng thái raw mà Query Service trả. Với blocking Java SDK, nếu request phát sinh lỗi terminal như parse/planning/timeout/permission, lời gọi `cluster.query(...)` thường **ném exception**, thay vì trả một `QueryResult` dùng được rồi buộc ứng dụng đọc `status` để phát hiện.

Mẫu:

~~~java
try {
    QueryResult result = cluster.query(
            statement,
            queryOptions().metrics(true));

    QueryMetaData meta = result.metaData();
    System.out.println("status=" + meta.status());

} catch (com.couchbase.client.core.error.CouchbaseException ex) {
    // Phân loại theo loại lỗi và ErrorContext,
    // log correlation ID, báo lỗi API phù hợp.
    throw ex;
}
~~~

Không viết:

~~~java
// Sai về mặt thiết kế:
try {
    return cluster.query(statement).rowsAsObject();
} catch (Exception ignored) {
    return List.of();
}
~~~

Một danh sách rỗng có thể là kết quả hợp lệ; swallow mọi exception khiến lỗi parser/index/RBAC/timeout bị ngụy trang thành “không có đơn hàng”.

### Nhóm lỗi và ý nghĩa

| Nhóm | Ví dụ | Xử lý |
| --- | --- | --- |
| Parsing/planning failure | SQL++ không hợp lệ/không có index | Sửa query/index, không fallback bừa |
| Authentication/authorization | Thiếu RBAC | Từ chối, audit, không tăng đặc quyền |
| Timeout/network | Không hoàn tất trong budget | Trả lỗi tạm thời, phân loại retry |
| Decoding/mapping | JSON alias hoặc kiểu không đúng | Sửa contract/schema, không trả DTO giả |
| Application cancellation | Client hủy request | Không log là business not-found |
| Warning non-terminal | Query trả result và warnings | Áp policy logging/severity |
| Missing optional metrics | Không bật `metrics(true)` | Ghi telemetry unavailable, không fail business vô cớ |

Với SQL++ mutation, timeout có thể mang tính ambiguous; không retry tự động một thay đổi có side effect nếu chưa thiết kế idempotency.

## 18. `signature()` mô tả hình dạng, không tạo schema contract

`meta.signature()` trả `Optional<JsonObject>` nếu server cung cấp:

~~~java
meta.signature().ifPresent(sig -> {
    System.out.println("Result signature: " + sig);
});
~~~

Signature có thể hữu ích để xem shape của kết quả SQL++; ví dụ alias `id`, `status`, `amount`. Tuy nhiên:

- Không phải JSON Schema đầy đủ/validator domain.
- Không thay integration tests cho mapping `NULL`/`MISSING` hoặc kiểu số.
- Có thể vắng mặt.
- Có thể mô tả kiểu query engine, không diễn đạt toàn bộ constraint Java record.
- Với `SELECT RAW` trả scalar, cách metadata biểu diễn có thể khác object rows.
- Signature không mang CAS/ID entity mặc nhiên.

Tránh viết code business phụ thuộc vào `signature()` để tự quyết định query này “có thể save entity”. Kết quả aggregate/projection nên có DTO contract riêng.

## 19. `profile()`: khi nào cần dữ liệu sâu?

Nếu bật profiling:

~~~java
import com.couchbase.client.java.query.QueryProfile;

QueryResult result = cluster.query(
        statement,
        queryOptions()
                .metrics(true)
                .profile(QueryProfile.PHASES));

result.metaData().profile().ifPresent(profile -> {
    System.out.println(profile);
});
~~~

Các mức `QueryProfile`:

| Giá trị | Ý nghĩa | Chi phí tương đối |
| --- | --- | --- |
| `OFF` | Không yêu cầu query profile trong response | Thấp nhất |
| `PHASES` | Tổng hợp thông tin phases và stats | Cao hơn metrics |
| `TIMINGS` | Bao gồm chi tiết plan/operator timings | Chi tiết và có thể nặng hơn |

Khi điều tra sâu:

~~~java
QueryResult result = cluster.query(
        statement,
        queryOptions()
                .metrics(true)
                .profile(QueryProfile.TIMINGS));

result.metaData().profile().ifPresent(profile -> {
    // Đưa vào diagnostic channel có kiểm soát,
    // không phát toàn bộ JSON profile đến end user.
});
~~~

**Profile có thể làm tăng overhead và kích thước response.** Không bật `TIMINGS` trên toàn bộ production queries chỉ vì muốn một con số duration. `metrics(true)` phù hợp hơn cho quan sát thường xuyên.

## 20. `EXPLAIN` khác `profile(TIMINGS)`

`EXPLAIN` giúp xem **kế hoạch dự kiến** mà optimizer chọn:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-01"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT 20;
~~~

`QueryProfile.TIMINGS` cung cấp thông tin **khi truy vấn thực sự được thực thi**, kèm operator timings/counters nếu được server hỗ trợ.

| Công cụ | Trả lời tốt câu hỏi |
| --- | --- |
| `metrics(true)` | Query có chậm không? Trả bao nhiêu rows/bytes? |
| `EXPLAIN` | Có operator IndexScan, Fetch, Order, Join như dự kiến không? |
| `profile(PHASES)` | Phần lớn thời gian nằm ở phase nào? |
| `profile(TIMINGS)` | Operator nào xử lý nhiều items hoặc chiếm thời gian? |
| Client stopwatch/tracing | Thời gian bên ngoài server nằm ở đâu? |
| Index/Query Service dashboards | Cluster đang nghẽn do query khác không? |

Không dùng `EXPLAIN` để thay số liệu chạy thực tế, cũng không dùng `QueryMetrics.resultCount` để kết luận query plan đã tối ưu.

### Cẩn thận với dữ liệu nhạy cảm

`EXPLAIN`/profiling và raw SQL++ có thể chứa tên keyspace, các biểu thức, tham số hoặc thông tin nhạy cảm. Chỉ cho phép diagnostic access với quyền phù hợp và redaction trước khi gửi tới telemetry ngoài cluster.

## 21. Metrics không nói được index scan bao nhiêu

Giả sử `resultCount=20` và `resultSize=1500` bytes. Điều đó không chứng minh server chỉ xem 20 documents.

Một query có thể:

~~~text
IndexScan: xem rất nhiều index entries
Fetch:     đọc nhiều document bodies
Filter:    bỏ đa số rows
Order:     sắp xếp rất nhiều rows
Limit:     trả 20 rows
~~~

Vì vậy cần:

- `EXPLAIN` để thấy plan logic/operators.
- `profile(TIMINGS)` hoặc Query Service monitoring để xem operator counters/timings.
- Thiết kế index phù hợp tenant/status/sort.
- Dùng projection giảm `Fetch` khi hợp lý.
- Tránh `OFFSET` sâu nếu có thể thiết kế seek/keyset.
- Kiểm tra scan consistency `REQUEST_PLUS` có ảnh hưởng latency không.
- Đo cùng workload sau khi thay index.

Đừng gắn nhãn `resultCount` là “records scanned” trong dashboard.

## 22. Metadata hỗ trợ điều tra tốc độ nhưng không bảo đảm correctness

Một truy vấn trả rất nhanh vẫn có thể sai:

~~~sql
SELECT o.channel, SUM(o.totalCents) AS revenue
FROM `shop`.`sales`.`orders` AS o
UNNEST o.items AS item
WHERE o.status = "PAID"
GROUP BY o.channel;
~~~

Nếu mỗi Order có nhiều items, `SUM(o.totalCents)` sau `UNNEST` có thể cộng lại giá trị cấp Order nhiều lần. Metrics có thể ghi:

~~~text
elapsedTime = 3ms
resultCount = 3
warnings = []
~~~

nhưng số liệu doanh thu vẫn **sai nghiệp vụ**. Cần kiểm thử unit-of-analysis, tenant filters, currency, timezone, NULL/MISSING, JOIN cardinality và đặc tả count/sum.

Không lấy `status=success` hay `warningCount=0` làm chứng nhận đúng nghiệp vụ hoặc snapshot.

## 23. `Page`, `Slice` và giới hạn của metadata

Một danh sách phân trang:

~~~sql
SELECT META(o).id AS id, o.status
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT 21 OFFSET 40;
~~~

Nếu size nghiệp vụ là 20, lấy 21 rows để tính `hasNext`. Khi đó:

- `metrics.resultCount()` tối đa 21, **không phải total**.
- `resultCount=21` cho biết query có row look-ahead, có thể giúp suy ra `hasNext=true` theo cách xây window của ứng dụng.
- Nếu client cắt một row look-ahead trước khi trả API, số items hiển thị là 20; server resultCount vẫn 21.
- `PageImpl` chỉ là metadata object do ứng dụng tạo, không tự chạy `COUNT` trên Couchbase.
- `COUNT(1)` riêng phải dùng đúng tenant/status và dữ liệu có thể đổi giữa hai lần query.
- Với `GROUP BY`, total của `Page<AggregateDto>` là số nhóm, không phải tổng source documents.

**Không dùng `sortCount` hay `resultCount` thay số total của `Page`.**

## 24. Từ Repository/Template đến SDK metadata

Repository:

~~~java
public interface OrderRepository
        extends CouchbaseRepository<Order, String> {

    Page<Order> findByStatus(
            String status,
            Pageable pageable);
}
~~~

đã giúp mapper/entity lifecycle, nhưng không có nghĩa mỗi repository method tự trả một `QueryMetaData` cho business layer. Hợp đồng `Page<Order>` cung cấp dữ liệu và phân trang, không phải requestId/QueryMetrics.

Nếu cần metadata Query Service cho một operation riêng, có các lựa chọn:

1. Dùng application tracing/metrics ở Repository và quan sát Query Service độc lập.
2. Sử dụng Template hoặc query API được Spring Data phiên bản đang dùng expose để lấy đủ thông tin khi khả thi.
3. Viết **custom SDK adapter** với `Cluster.query(...)` cho query cần kiểm soát SQL++/result/metadata.

**Đừng chuyển toàn bộ Repository sang SDK chỉ để lấy một con số elapsedTime.** Điều đó có thể làm mất converter, `@Id`/`@Version`, auditing và quy ước collection của Spring Data. Chỉ hạ tầng trừu tượng khi có use case và bằng chứng cụ thể.

## 25. Mẫu SDK adapter trả rows và telemetry nội bộ

Có thể tách read model nghiệp vụ khỏi telemetry:

~~~java
public record OrderCard(
        String id, String status) {}

public record QueryDiagnostics(
        String requestId,
        String clientContextId,
        String status,
        long warnings,
        Long serverResultCount,
        Long serverResultSize,
        Long serverElapsedMillis) {}

public record OrderQueryResponse(
        List<OrderCard> items,
        QueryDiagnostics diagnostics) {}
~~~

`Long` nullable ở đây có chủ ý: nếu metrics không được trả, **không bịa 0**.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryMetaData;
import com.couchbase.client.java.query.QueryMetrics;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;
import java.util.UUID;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public OrderQueryResponse fetch(
        Cluster cluster,
        String tenantId,
        int limit) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Invalid tenant");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid limit");
    }

    String sql = """
        SELECT META(o).id AS id, o.status AS status
        FROM `shop`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
        ORDER BY o.createdAt DESC, META(o).id DESC
        LIMIT $limit
        """;

    String correlationId = "orders-" + UUID.randomUUID();

    QueryResult result = cluster.query(
            sql,
            queryOptions()
                    .parameters(JsonObject.create()
                            .put("tenantId", tenantId)
                            .put("limit", limit))
                    .clientContextId(correlationId)
                    .readonly(true)
                    .metrics(true));

    List<OrderCard> items = result.rowsAsObject().stream()
            .map(row -> new OrderCard(
                    row.getString("id"),
                    row.getString("status")))
            .toList();

    QueryMetaData meta = result.metaData();
    QueryMetrics metrics = meta.metrics().orElse(null);

    QueryDiagnostics diagnostic = new QueryDiagnostics(
            meta.requestId(),
            meta.clientContextId(),
            meta.status().toString(),
            meta.warnings().size(),
            metrics == null ? null : metrics.resultCount(),
            metrics == null ? null : metrics.resultSize(),
            metrics == null ? null :
                    metrics.elapsedTime().toMillis());

    return new OrderQueryResponse(items, diagnostic);
}
~~~

**Lưu ý triển khai:** `QueryDiagnostics` nên lưu cho logging/metrics nội bộ hoặc admin diagnostics. Không nên tự động trả toàn bộ server request metadata cho end-user public API. Tên field và DTO ở đây chỉ là hợp đồng ví dụ.

Adapter cần thêm tenant authorization thực tế, error handling, timeout, logging redaction và production metrics integration.

## 26. Reactive: metadata chỉ sẵn sàng sau khi đọc rows

Couchbase Java SDK reactive dùng:

~~~text
ReactiveQueryResult
  ├── rowsAsObject() -> Flux<JsonObject>
  └── metaData()     -> Mono<QueryMetaData>
~~~

Điểm đặc biệt được SDK ghi rõ:

> Metadata của reactive query **chỉ có sau khi các rows đã được nhận/xử lý xong**.

Vì vậy nếu code đòi metadata trước khi consume rows, nó có thể dẫn tới buffering hoặc thứ tự xử lý không mong muốn.

Sai hướng:

~~~java
// Không nên đòi metadata trước rồi mới consume rows.
cluster.reactive().query(sql)
        .flatMap(result ->
                result.metaData().flatMap(meta ->
                        result.rowsAsObject().collectList()));
~~~

Hướng hợp lý khi query **đã có LIMIT thấp**:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.ReactiveQueryResult;
import reactor.core.publisher.Mono;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public Mono<OrderQueryResponse> fetchReactive(
        Cluster cluster,
        String sql,
        JsonObject params) {

    return cluster.reactive()
            .query(sql, queryOptions()
                    .parameters(params)
                    .metrics(true)
                    .readonly(true))
            .flatMap(result ->
                    result.rowsAsObject()
                            .map(row -> new OrderCard(
                                    row.getString("id"),
                                    row.getString("status")))
                            .collectList()
                            .flatMap(items ->
                                    result.metaData().map(meta -> {
                                        var m = meta.metrics().orElse(null);

                                        var diagnostic =
                                            new QueryDiagnostics(
                                                meta.requestId(),
                                                meta.clientContextId(),
                                                meta.status().toString(),
                                                meta.warnings().size(),
                                                m == null ? null :
                                                    m.resultCount(),
                                                m == null ? null :
                                                    m.resultSize(),
                                                m == null ? null :
                                                    m.elapsedTime().toMillis());

                                        return new OrderQueryResponse(
                                                items, diagnostic);
                                    })));
}
~~~

**Tiền đề:** Query `sql` có giới hạn result rows ở server và phù hợp việc `collectList()`. Nếu trả hàng triệu rows, phải chọn thiết kế streaming/batch khác.

### Vì sao không dùng `Mono.zip(rows, metadata)` ngay?

Nếu subscribe đồng thời hai publisher, metadata có thể phải chờ toàn bộ rows được nhận trong khi downstream chưa xử lý đúng cách. SDK khuyến cáo **consume rows trước, rồi mới truy cập metadata** để tránh buffering không cần thiết.

Luồng trên dùng `collectList().flatMap(...metaData())` nên thứ tự rõ ràng. Với stream lớn, dùng `rowsAsObject().doOnNext(...).then(result.metaData())` để xử lý từng row rồi lấy trailer metadata (thao tác side effect trong `doOnNext` phải non-blocking và có kiểm soát).

## 27. Khi cancellation làm mất metadata

Reactive stream có thể bị hủy:

~~~java
result.rowsAsObject()
        .take(10);
~~~

Nếu server còn nhiều rows, `take(10)` có thể **cancel upstream** khi đạt giới hạn. Khi đó đừng mặc định query đã hoàn tất theo cách bình thường và metadata trailer luôn có đầy đủ.

Nguyên tắc:

1. Đặt `LIMIT` tại SQL++ nếu business cần 10 rows.
2. Consume rows/metadata theo hợp đồng SDK.
3. Quan sát cancellation riêng với success/error.
4. Không ghi success metrics dựa trên metadata chưa đến.
5. Không dùng `Flux.take` như một cách tính tổng số rows.
6. Nếu client rời trang trước khi query xong, telemetry có thể chỉ ghi **client cancellation**, không phải `QueryStatus.SUCCESS`.
7. Query timeout có thể đến trước khi metadata được phát; phân loại lỗi ở reactor `doOnError`/`doFinally` và ErrorContext SDK.

Cancellation cũng không bảo đảm mọi work phía Server đã dừng tức khắc. Tùy operation và timeouts, cần đo service load, không suy từ sự kiện client cancel.

## 28. Metadata của Analytics khác SQL++ Query

Java SDK:

~~~java
import com.couchbase.client.java.analytics.AnalyticsResult;
import com.couchbase.client.java.analytics.AnalyticsMetaData;
import com.couchbase.client.java.analytics.AnalyticsMetrics;

AnalyticsResult result = cluster.analyticsQuery(
        "SELECT 1 AS value");

AnalyticsMetaData meta = result.metaData();
AnalyticsMetrics metrics = meta.metrics();

System.out.println(meta.requestId());
System.out.println(meta.clientContextId());
System.out.println(meta.status());
System.out.println(metrics.executionTime());
System.out.println(metrics.elapsedTime());
System.out.println(metrics.resultCount());
System.out.println(metrics.resultSize());
System.out.println(metrics.processedObjects());
System.out.println(meta.warnings().size());
~~~

Khác biệt then chốt:

- `QueryMetaData.metrics()` trả **`Optional<QueryMetrics>`** với Query Service.
- `AnalyticsMetaData.metrics()` trả **`AnalyticsMetrics`** theo Java SDK Analytics API này, **không phải Optional<QueryMetrics>`**.
- `AnalyticsMetrics.processedObjects()` phản ánh số đối tượng/tuples được Analytics xử lý theo engine semantics, không phải số Search hits hoặc số document KV get.
- Analytics có ingestion/shadow dataset: metrics nhanh và warnings rỗng **không chứng minh** dữ liệu đã mới bằng nguồn Data Service.
- Metadata `signature`/`warnings` có thể có cấu trúc/loại khác.
- Không ép Analytics query thành Query Service chỉ vì hai engine đều nói SQL++.

Nếu cần freshness, quan sát ingestion lag, `AnalyticsScanConsistency` và chính sách báo cáo. Không dùng `QueryScanConsistency.REQUEST_PLUS` thay lựa chọn của Analytics Service.

## 29. Metadata của Search Service có thể chứa partial errors

Couchbase Search/FTS trả `SearchResult` với search hits và `SearchMetaData`.

~~~java
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.SearchResult;

import static com.couchbase.client.java.search.SearchOptions.searchOptions;

SearchResult result = cluster.searchQuery(
        "idx-products-text",
        SearchQuery.match("cà phê").field("name"),
        searchOptions().limit(20));

var meta = result.metaData();

System.out.println("Search total rows: " +
        meta.metrics().totalRows());

if (!meta.errors().isEmpty()) {
    System.out.println("Search partial errors: " +
            meta.errors().size());
}
~~~

**Rất quan trọng:** Search Service có thể trả **một phần hits** cùng với `SearchMetaData.errors()` chứa lỗi shard/partition, thay vì toàn bộ request ném exception.

Vì vậy, đối với API yêu cầu kết quả đầy đủ:

~~~java
if (!result.metaData().errors().isEmpty()) {
    throw new IllegalStateException(
            "Search result may be incomplete");
}
~~~

Không tự chuyển kết quả Search có errors thành “không tìm thấy sản phẩm” hoặc dùng facet totals làm số liệu tài chính chắc chắn.

### Phân biệt các loại metadata

| Dịch vụ | Kết quả | Metadata/métrics đặc thù |
| --- | --- | --- |
| Query Service | `QueryResult` | `QueryMetaData`, `Optional<QueryMetrics>`, warnings, profile |
| Analytics Service | `AnalyticsResult` | `AnalyticsMetaData`, `AnalyticsMetrics.processedObjects` |
| Search Service | `SearchResult` | `SearchMetaData.metrics()`, `errors()`, hits/score/facets |
| KV | `GetResult`, `MutationResult` | CAS, mutation token (khi có), expiry ở đường phù hợp |

Không thể gọi `rowsAsObject`/`metaData.metrics().resultCount()` theo cùng một kiểu trên **mọi service**. Mỗi loại API có contract riêng.

## 30. KV CAS và mutation token không phải query metrics

Khi đọc theo key:

~~~java
var get = collection.get("order::1001");

long cas = get.cas();
var body = get.contentAsObject();
~~~

Khi ghi:

~~~java
var mutation = collection.replace(
        "order::1001",
        updatedBody);

long newCas = mutation.cas();
~~~

CAS là token phiên bản **một document** để optimistic locking. Mutation token (nếu SDK/server cung cấp) có thể được dùng trong một số lựa chọn read-your-own-writes cho query/index.

Nhưng:

- `cas()` không phải elapsed time.
- CAS không phải clientContextId/requestId.
- CAS không phải “số lần chỉnh sửa” có thể so trên mọi documents.
- MutationResult không chứa QueryMetrics cho một `Cluster.query(...)`.
- `resultCount` của SQL++ không cho biết document CAS nào.
- Chọn consistency như `REQUEST_PLUS`/`consistentWith` có thể ảnh hưởng độ mới/latency, không tự biến CAS thành snapshot toàn query.

Vì bài này nói về **metadata kết quả truy vấn**, việc phân biệt KV metadata là cần thiết để không trộn các khái niệm mang tên “metadata” nhưng giải quyết vấn đề khác nhau.

## 31. Chỉ số server không thay tracing toàn hệ thống

Một request HTTP có thể làm:

~~~text
Controller
  |
  +-- Validate/auth
  +-- Query danh sách
  |     +-- Query Service executionTime
  |     +-- Query Service elapsedTime
  |
  +-- 20 KV gets để hydrate
  +-- Map DTO
  +-- JSON serialize
  +-- HTTP send
~~~

Một `QueryMetrics.elapsedTime` chỉ mô tả **một câu Query Service**, không đo:

- 20 KV gets sau đó.
- Thời gian auth, database retry, JSON mapping.
- Queueing trong ứng dụng.
- Network từ API đến browser và render UI.
- Retry attempt khác với request ID khác.

Với monitoring có ý nghĩa, nên đặt **HTTP span**, **service span**, **SDK query span** và **KV spans**; dùng correlation ID chung nhưng phân biệt từng attempt.

### Ví dụ phân tích chậm

| Quan sát | Khả năng cần điều tra |
| --- | --- |
| Server elapsed cao, execution cao | Plan/index/scan/sort/JOIN/compute |
| Server elapsed cao, execution thấp | Queue, wait, consistency hoặc overhead trước execution |
| Client elapsed cao, server elapsed thấp | Network, decoding, connection pool, thread scheduling hoặc downstream |
| resultSize lớn, client heap cao | SELECT body thừa, thiếu projection, pagination |
| Query nhanh nhưng HTTP chậm | Hydration, serialization, external calls |
| query resultCount nhỏ, sortCount lớn | Sort nhiều candidates; kiểm tra `EXPLAIN` |
| Warnings xuất hiện bất thường | Đọc warning code/message, kiểm tra query/index |
| Search errors map không rỗng | Có thể kết quả partial, không coi total chính xác |

Đây là **giả thuyết chẩn đoán**, không phải quy tắc định danh nguyên nhân chắc chắn. Đo thêm bằng profiling và server metrics trước khi sửa code/index.

## 32. Thiết kế telemetry vừa hữu ích vừa an toàn

Nên đưa vào structured logs/metrics:

- Tên operation ở dạng tĩnh: `listPaidOrders`, `revenueByChannel`.
- Service name: `SPRING_DATA_COUCHBASE` hoặc tên subsystem thực tế.
- Loại engine: `query`, `analytics`, `search`.
- `clientContextId`/`requestId` nếu có.
- `status`, warning count, error category.
- `serverElapsedMs`, `serverExecutionMs` khi có.
- `resultCount` và `resultSize` khi có.
- Client observed duration, retry attempts, cancellation.
- Index/query class hoặc một **fingerprint** đã chuẩn hóa, không raw SQL++/secret.
- Giới hạn page size, thông tin query consistency, failure type khi thực sự cần.

**Không** dùng các giá trị có cardinality cực cao như `requestId`, email, document key hay tenant ID trực tiếp làm labels của Prometheus histogram/counter. Những định danh này hợp với **logs/traces có sampling**, còn metrics labels nên là **operation/engine/outcome** có số lượng giá trị hữu hạn.

### Một bảng log gợi ý

~~~json
{
  "operation": "listPaidOrders",
  "engine": "query",
  "outcome": "success",
  "clientContextId": "orders-1e2b",
  "serverRequestId": "server-generated",
  "serverElapsedMs": 25,
  "serverExecutionMs": 18,
  "serverResultCount": 20,
  "serverResultSize": 1800,
  "warningCount": 0,
  "clientElapsedMs": 43
}
~~~

Đây là **format log ứng dụng đề xuất**, không phải JSON mà SDK tự trả nguyên dạng. Khi metrics vắng mặt, để `null` hoặc bỏ key, **không gán 0** rồi hiển thị nó như đo thật.

## 33. Query errors, retries và tính nhất quán

Một query thất bại có thể:

- Chưa kịp chạy trên server.
- Đã được server xử lý một phần rồi client timeout.
- Lỗi do RBAC, parsing hoặc planning.
- Bị cancellation bởi client.
- Đã ghi một phần mutation nếu đó là DML và không có transaction thích hợp.

Vì vậy nên phân loại:

1. **Read-only query**: có thể cân nhắc retry có giới hạn tùy loại lỗi, budget và consistency.
2. **DML/mutation query**: không retry mù khi outcome có thể ambiguous; cần idempotency/transaction policy.
3. **Warning**: không mặc nhiên retry vì thường không phải lỗi terminal.
4. **Missing optional metadata**: không biến thành business failure nếu response đã hợp lệ.
5. **Search partial errors**: tùy hợp đồng completeness; có thể trả partial có nhãn hoặc fail-closed.
6. **Analytics ingestion lag**: retry không bảo đảm ngay có dữ liệu mới; xem scan consistency, lag và SLA.

Phải kiểm tra **ErrorContext**/exception hierarchy của Java SDK trên phiên bản thực tế; requestId/clientContextId có thể xuất hiện ở metadata khi thành công hoặc error context khi thất bại. Không giả định luôn có `QueryMetaData` trong catch branch.

## 34. Kiểm thử metadata với truy vấn thành công

Một integration test tối thiểu nên xác minh:

~~~java
@Test
void queryMetricsAreAvailableWhenEnabled() {
    QueryResult result = cluster.query(
            "SELECT 1 AS value",
            queryOptions().metrics(true));

    assertThat(result.rowsAsObject()).hasSize(1);

    QueryMetaData meta = result.metaData();

    assertThat(meta.requestId()).isNotBlank();
    assertThat(meta.clientContextId()).isNotBlank();
    assertThat(meta.metrics()).isPresent();

    QueryMetrics m = meta.metrics().orElseThrow();
    assertThat(m.resultCount()).isEqualTo(1);
    assertThat(m.elapsedTime())
            .isGreaterThanOrEqualTo(Duration.ZERO);
}
~~~

Đây là **khung test minh họa**: cần khai báo `cluster`, imports JUnit/AssertJ và chọn môi trường test SDK phù hợp. Không được chạy Gradle/Python trong STEP 4; kiểm thử integration thực tế thuộc bước QA.

Với assertion thời lượng, `Duration.ZERO` là mốc tường minh để kiểm tra giá trị không âm:

~~~java
assertThat(m.elapsedTime())
        .isGreaterThanOrEqualTo(Duration.ZERO);
~~~

Đừng assert `elapsedTime` đúng 10 ms, vì latency phụ thuộc tải. Trọng tâm là **hợp đồng API và ý nghĩa số liệu**, không phải timing tuyệt đối của một test môi trường bất định.

## 35. Kiểm thử warnings và query failures

### Warnings

Không nhất thiết mọi Couchbase Server version đều tạo cùng warning cho cùng input. Vì vậy:

- Ưu tiên dùng fixture/query được xác minh trên phiên bản test nếu thật sự cần assertion warning code.
- Đối với business code, unit-test nhánh mapping warnings bằng đối tượng test phù hợp.
- Test rằng cảnh báo không bị bỏ im lặng nếu policy yêu cầu ghi nhận.
- Test rằng cảnh báo không tự biến kết quả hợp lệ thành `HTTP 500` nếu policy không yêu cầu.
- Không assert nguyên văn `warning.message()` vì text có thể đổi giữa phiên bản Server.

### Failures

Các ca cần thử:

| Case | Mong đợi |
| --- | --- |
| SQL++ syntax sai | SDK ném exception phù hợp; không trả rows rỗng giả |
| Index bị xóa/không phù hợp | Planning/query error được quan sát |
| User thiếu RBAC | Không fallback bằng account quyền rộng |
| Query timeout | Có client error telemetry, phân loại retry |
| Decode field sai type | Bắt mapping error, không bỏ row im lặng |
| Metrics tắt/vắng mặt | Business response hợp lệ, diagnostic ghi unavailable |
| QueryProfile tắt | `meta.profile()` absent, không tự dựng profile rỗng |
| Cảnh báo có mặt | Code/message được xử lý an toàn |
| Analytics query thất bại | Không ép thành `QueryResult` |
| Search partial errors | Không nhầm với kết quả đầy đủ |
| Reactive cancel sớm | Không tự khẳng định metadata trailer đầy đủ |

## 36. Kiểm thử phân trang và số liệu kết quả

Giả sử có **105 đơn PAID** thuộc tenant A. Query lấy trang size 20.

| Truy vấn | Rows của SQL++ | `QueryMetrics.resultCount` | Tổng nghiệp vụ |
| --- | ---: | ---: | ---: |
| `SELECT ... LIMIT 20 OFFSET 0` | 20 | 20 | 105 |
| `SELECT ... LIMIT 21 OFFSET 0` | 21 | 21 | 105 |
| `SELECT ... LIMIT 20 OFFSET 100` | 5 | 5 | 105 |
| `SELECT COUNT(1) AS total` | 1 | 1 | Row `total=105` |
| `GROUP BY channel` có 3 nhóm | 3 | 3 | 3 nhóm |

Những số ví dụ giả định dữ liệu không đổi và truy vấn được thực thi thành công với metrics bật.

Điểm kiểm thử:

- `resultCount` là số **result rows của request**, không phải source total.
- `Page` cần count theo đúng predicate.
- `Slice` có thể dùng look-ahead 1 row để suy ra `hasNext`.
- `GROUP BY` đổi đơn vị result từ source document sang **nhóm**.
- Không so số resultCount giữa các query khác SQL++ text để kết luận có mất dữ liệu.
- Dữ liệu thay đổi giữa data query và count query có thể gây total không khớp; metadata không cấp snapshot chung.

## 37. Benchmark và profiling theo lớp

Khi có cảnh báo latency p95 tăng từ 60 ms lên 400 ms:

1. **Xác định operation** qua logs/correlation IDs.
2. Xem `clientElapsedMs` tăng hay chỉ HTTP latency tăng.
3. Đọc `QueryMetrics.elapsedTime/executionTime` khi được bật.
4. Kiểm tra resultCount/resultSize có đột biến không.
5. Kiểm tra warnings, timeout rate và consistency option.
6. Chạy `EXPLAIN` cho statement/params đại diện.
7. Sampling `QueryProfile.PHASES` hoặc `TIMINGS` ở môi trường/tải kiểm soát.
8. Kiểm tra GSI index, `Fetch`, `Order`, `JOIN`, phân trang sâu và scan cap.
9. Kiểm tra Query Service nodes, CPU/RAM, queue và concurrent requests.
10. Nếu server nhanh nhưng client chậm, kiểm tra JSON decoding, mapping DTO, extra KV gets, thread pool và network.
11. So benchmark trước/sau bằng cùng dataset, query options và traffic.
12. Giữ lại clientContextId/requestId của các samples để đối chiếu, không biến ID thành metric label.

Không đổi index bừa chỉ vì `executionTime` cao; query có thể chờ dữ liệu, bị contention hoặc resultSize lớn. Dữ liệu đo phải dẫn đến giả thuyết có thể kiểm chứng.

## 38. Bảng quyết định: đọc chỉ số nào cho câu hỏi nào?

| Câu hỏi | Tín hiệu chính | Bổ trợ |
| --- | --- | --- |
| Query thành công không? | SDK exception/outcome, `QueryStatus` | Server request ID |
| Có cảnh báo? | `warnings()`, `warningCount()` | Warning code/message và query context |
| Server mất bao lâu? | `elapsedTime`, `executionTime` | Phase/operator profiling |
| Người dùng thấy chậm ở đâu? | HTTP/client tracing | Server metrics, network, hydration |
| Query trả bao nhiêu rows? | `resultCount` | `rowsAsObject().size()` nếu bounded |
| Có bao nhiêu documents match? | SQL++ `COUNT(1)` đúng filter | Không dùng resultCount |
| Query đã scan bao nhiêu? | Query profile/IndexScan/EXPLAIN | Query monitoring |
| Server trả nhiều bytes? | `resultSize` | Client/network byte counters |
| Query có thay đổi dữ liệu? | `mutationCount` cho DML | Transaction/audit/CAS |
| Index có mới không? | Scan consistency + thực tế dữ liệu | Không suy chỉ từ metadata |
| Analytics có mới không? | Ingestion lag/Analytics consistency | AnalyticsMetrics |
| Search có kết quả đầy đủ không? | `SearchMetaData.errors()` | SearchMetrics, facets |
| Có snapshot xuyên nhiều requests không? | Hợp đồng snapshot/version riêng | Metadata một query không đủ |

## 39. Checklist review cho SDK adapter

### Metadata và correctness

- [ ] `QueryMetaData.metrics()` được xử lý như `Optional`.
- [ ] Query muốn có metrics đã bật `queryOptions().metrics(true)`.
- [ ] `QueryProfile.TIMINGS` không bật đại trà trên production.
- [ ] `warnings()` được phân loại theo chính sách.
- [ ] `status=success`/`warningCount=0` không bị coi là chứng minh business correctness.
- [ ] `resultCount` không dùng thay `COUNT` hoặc total của `Page`.
- [ ] `sortCount` không bị ghi nhãn “index scanned” sai.
- [ ] `resultSize` không được so trực tiếp với total HTTP bytes.
- [ ] Signature/profile absent được xử lý phù hợp.
- [ ] DML timeout có chiến lược idempotency/ambiguity.

### Lifecycle, reactive và dịch vụ

- [ ] SDK `Cluster` do Spring quản lý và keyspace đúng.
- [ ] Reactive rows được tiêu thụ **trước** metadata.
- [ ] `collectList()` chỉ trên query bounded hoặc batch có kiểm soát.
- [ ] Cancellation/error không bị ghi là success.
- [ ] Analytics/Query/Search metadata không bị ép cùng một kiểu.
- [ ] Search `errors()` được kiểm tra nếu yêu cầu kết quả đầy đủ.
- [ ] KV CAS/mutation token không bị nhầm với QueryMetrics.
- [ ] Không phụ thuộc vào raw JSON/profile fields chưa kiểm chứng phiên bản.

### Bảo mật và vận hành

- [ ] `clientContextId` có tính truy vết và không chứa bí mật.
- [ ] `requestId`/correlation ID nằm trong logs/traces, không làm metric labels cardinality cao.
- [ ] Raw SQL++ params/body/warnings được sanitize và áp redaction.
- [ ] Có p50/p95/p99 cho operation/engine/outcome.
- [ ] Có monitor Query/Analytics/Search Service và index lag tương ứng.
- [ ] Có test metrics vắng mặt, warnings, error, timeout và phân trang.
- [ ] Có integration test trên Couchbase Server/Java SDK đã khóa.
- [ ] Không chạy query profiling/DDL/mutation nguy hiểm từ endpoint public.

## 40. Bài tập thực hành

Xây một **Query Diagnostics Adapter** cho endpoint danh sách Orders.

**Phần A — Query và metadata**

1. Dùng Spring-managed `Cluster`.
2. Viết SQL++ trên `shop.sales.orders` với `$tenantId` và `LIMIT` có kiểm soát.
3. Gọi `queryOptions().metrics(true).clientContextId(...)`.
4. Trả `List<OrderCard>` cho ứng dụng và giữ `QueryDiagnostics` nội bộ.
5. Log `requestId`, `clientContextId`, `status`, warning count, elapsed/execution, resultCount và resultSize khi có.
6. Thử bỏ `metrics(true)` và xác minh không ném `NoSuchElementException`.
7. Tính totalOrders bằng `COUNT(1)` riêng; so với `resultCount` của query data.

**Phần B — Chẩn đoán hiệu năng**

1. Tạo index phù hợp tenant/status/createdAt.
2. Đo QueryMetrics ở trang đầu và trang OFFSET sâu.
3. Chạy `EXPLAIN`, so operator trước/sau index.
4. Bật `profile(QueryProfile.PHASES)` cho một sample.
5. Bật `TIMINGS` trong môi trường kiểm soát và đối chiếu operator latency.
6. So `elapsedTime` server với stopwatch phía Java.
7. Kiểm tra liệu `resultSize` giảm khi chuyển từ `SELECT o.*` sang projection nhỏ.

**Phần C — Reactive**

1. Viết `ReactiveQueryResult.rowsAsObject()` thành `Flux<OrderCard>`.
2. Khi cần trả page nhỏ, `collectList` xong mới gọi `result.metaData()`.
3. Hủy request sớm, quan sát cancellation và việc thiếu trailer metadata.
4. Không dùng `Mono.zip` một cách làm đòi metadata trước rows.
5. Không gọi `block()` trong WebFlux event-loop.

**Phần D — Khác biệt giữa các service**

1. Gọi `analyticsQuery(...)`, lấy `AnalyticsMetrics.processedObjects()`.
2. Gọi Search, đọc `SearchMetaData.metrics()` và `errors()`.
3. Thử Search với partial error trong môi trường test có fault injection.
4. Viết bảng so sánh Query/Analytics/Search/KV metadata.
5. Chứng minh không có metadata một query nào bảo đảm snapshot xuyên nhiều request.

### Câu hỏi tự kiểm tra

1. `QueryResult` có hai nhóm dữ liệu chính nào?
2. Vì sao `QueryMetaData.metrics()` là `Optional`?
3. Phải bật option nào để lấy số liệu SQL++ Query Service?
4. `elapsedTime` và `executionTime` khác nhau theo định nghĩa SDK ra sao?
5. Vì sao HTTP latency có thể lớn hơn server execution time?
6. `resultCount=1` có thể cùng tồn tại với `COUNT(1) AS total=100000` không?
7. `resultSize` có phải tổng HTTP/TCP bytes không?
8. `sortCount` có phải IndexScan rows scanned không?
9. Warnings khác terminal exception như thế nào?
10. `warningCount=0` có chứng minh dữ liệu đúng nghiệp vụ không?
11. `requestId` và `clientContextId` phục vụ việc gì?
12. `QueryProfile.TIMINGS` có nên bật mọi request không?
13. `EXPLAIN` khác profiling thực thi ở điểm nào?
14. `signature()` có thay được Java DTO validation không?
15. Metadata của reactive query được lấy vào thời điểm nào?
16. Vì sao `take(10)` có thể khiến không nhận được complete metadata?
17. `AnalyticsMetaData.metrics()` có cùng kiểu `Optional<QueryMetrics>` không?
18. Vì sao Search `metaData().errors()` phải được đọc khi cần kết quả đầy đủ?
19. KV `GetResult.cas()` có liên quan trực tiếp đến `QueryMetrics.elapsedTime` không?
20. Vì sao request ID không nên dùng làm Prometheus metric label?
21. Nếu server elapsed thấp nhưng client response chậm, cần đo thêm gì?
22. Metadata có giúp quyết định count query và page query dùng một snapshot không?

## 41. Tài liệu chính thức và lưu ý theo phiên bản

- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryResult`, `QueryMetaData`, `metrics(true)`, `clientContextId` và `profile`.
- [Java SDK API — QueryResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryResult.html): `rowsAsObject()`, `rowsAs(...)`, `metaData()`.
- [Java SDK API — QueryMetaData](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryMetaData.html): status, warnings, metrics, signature, profile.
- [Java SDK API — QueryMetrics](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryMetrics.html): elapsed/execution, resultCount/resultSize/sortCount/mutationCount/errors/warnings.
- [Java SDK API — QueryProfile](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryProfile.html): `OFF`, `PHASES`, `TIMINGS`.
- [Java SDK API — QueryOptions](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryOptions.html): `metrics(true)`, `clientContextId`, `profile(...)`, query settings.
- [Java SDK API — ReactiveQueryResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/ReactiveQueryResult.html): `Flux` rows, `Mono<QueryMetaData>`, lưu ý metadata sau rows.
- [Couchbase Java SDK — Analytics](https://docs.couchbase.com/java-sdk/current/howtos/analytics-using-sdk.html): `AnalyticsResult` và khác biệt metrics.
- [Java SDK API — AnalyticsMetaData](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/analytics/AnalyticsMetaData.html): metadata và warnings của Analytics.
- [Java SDK API — AnalyticsMetrics](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/analytics/AnalyticsMetrics.html): `processedObjects` và số liệu analytics.
- [Couchbase Java SDK — Search](https://docs.couchbase.com/java-sdk/current/howtos/full-text-searching-with-sdk.html): `SearchResult`, Search metadata, partial errors.
- [Java SDK API — SearchMetaData](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/search/SearchMetaData.html): `metrics()` và `errors()`.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): query plan trước thực thi.
- [Couchbase Server — Query Monitoring](https://docs.couchbase.com/server/current/manage/monitor/monitoring-n1ql-query.html): hoạt động Query Service, active/completed requests và profiling.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html) và [Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): đường entity/mapping và khả năng mở rộng bằng SDK.

**Giới hạn theo phiên bản:** Bài minh họa API Java SDK 3.x với Couchbase Server tương thích. Các lớp, chữ ký method, trường profiling, warning code/messages, số liệu Search/Analytics và khả năng monitoring có thể đổi theo phiên bản SDK/Server. Cần đối chiếu dependency đã khóa và kiểm thử trên cluster thật; không coi JSON profile, metadata hay ví dụ học thuật là schema bất biến để parse mãi mãi. Content QA chuyên môn/biên dịch thuộc giai đoạn sau bước viết bài.

> **Ghi nhớ:** Metadata giúp trả lời **truy vấn đã được xử lý thế nào**, không phải **kết quả nghiệp vụ chắc chắn đúng hay mới nhất**. Với SQL++ Query Service, bật `metrics(true)` khi cần, đọc `Optional<QueryMetrics>` an toàn, quan sát warnings, request IDs và profiling có kiểm soát. Đo client latency riêng; phân biệt Query, Analytics, Search và KV metadata; với reactive, **consume rows trước rồi mới lấy metadata**. Không dùng `resultCount` thay count nghiệp vụ, không che lỗi thành danh sách rỗng và không đưa telemetry nhạy cảm vào API/logs công khai.
