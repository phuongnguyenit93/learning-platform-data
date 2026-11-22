# Kiểm soát dữ liệu nhạy cảm, chi phí và thời gian lưu log/trace

Một ứng dụng Java sử dụng MongoDB lưu đơn hàng, Redis làm cache và Cassandra lưu dòng sự kiện. Một hôm p99 tăng đột biến. Nhóm vận hành bật DEBUG và ghi request body, MongoDB query, Redis key, stack trace, HTTP headers cùng mọi span attributes. Họ tìm ra truy vấn thiếu index, nhưng sau sự cố phát hiện access token và địa chỉ khách hàng đã xuất hiện trong log, chi phí lưu trữ tăng gấp nhiều lần và bản ghi DEBUG bị giữ chung với audit log trong nhiều tháng.

Đây là bài toán **quản trị dữ liệu quan sát**, không đơn thuần là chọn logger. Log, trace, metric, database profiler và bản ghi audit đều là **dữ liệu có mục đích, chủ sở hữu, mức độ nhạy cảm, chi phí và thời hạn lưu riêng**. Chúng có thể tạo thêm các bản sao dữ liệu cá nhân và bí mật ra ngoài database chính; một lệnh xóa bản ghi nghiệp vụ không tự xóa nội dung đã chảy vào hệ thống quan sát.

Bài học thuộc chương **Quan sát và chẩn đoán**, module **Database No SQL**. Chúng ta sẽ thiết kế hệ quan sát đủ để điều tra slow query, cache miss, replication lag, timeout và lỗi dữ liệu, đồng thời giới hạn thông tin nhạy cảm, cardinality, ingest/index/storage cost, thời gian lưu và quyền truy cập. Các giá trị retention, sampling và chi phí trong ví dụ chỉ mang tính **minh họa**, không phải chính sách pháp lý hoặc cấu hình mặc định cho mọi tổ chức.

## 1. Bốn nhóm tín hiệu không thể dùng chung một chính sách

| Tín hiệu | Câu hỏi chính | Ví dụ | Rủi ro |
|---|---|---|---|
| **Application log** | Một bước xử lý đã xảy ra hay thất bại thế nào? | order.read.failed, DB_TIMEOUT | Dễ ghi raw DTO, exception, PII |
| **Distributed trace** | Một request đi qua các thành phần nào, chậm ở đâu? | API → Redis → MongoDB | Span attributes, baggage, URL mang dữ liệu nhạy |
| **Metric** | Xu hướng hệ thống ra sao theo thời gian? | p99, QPS, retry count | Label cardinality, định danh từng user |
| **Audit/security record** | Ai hành động, trên phạm vi nào, khi nào? | AccessPolicyChanged | Cần toàn vẹn, phân quyền, retention riêng |
| **Database profiler/diagnostic** | Query nào có đường thực thi đắt? | COLLSCAN, keysExamined lớn | Query literals, raw keys, collection nội bộ |

Không nên lưu DEBUG log của cache hit 180 ngày chỉ vì audit log về thay đổi quyền cần giữ lâu. Ngược lại, không sample ngẫu nhiên 99% audit events chỉ vì sampled traces đã đủ phục vụ tối ưu hiệu năng.

## 2. Dòng dữ liệu từ ứng dụng đến nơi lưu telemetry

~~~mermaid
flowchart LR
    API["Java API"] --> L["Structured logs"]
    API --> T["OpenTelemetry spans"]
    DB["NoSQL database"] --> P["Slow-query diagnostics"]
    CACHE["Redis"] --> M["Cache metrics"]
    L --> C["Collector / processors"]
    T --> C
    P --> C
    M --> C
    C --> H["Hot searchable store"]
    C --> A["Restricted audit / archive"]
    H --> D["Dashboard / alerts / incidents"]
    A --> GOV["Retention / access audit"]
~~~

Những nơi có thể chứa bản sao thông tin nhạy cảm:

- Logger trong ứng dụng hoặc driver.
- Console/STDOUT của container và node agent.
- Local collector queue hoặc disk spool.
- Message broker trung gian.
- Backend logs/traces và hệ thống index.
- Alert qua email/chat/pager.
- Export CSV, ticket, dashboard screenshot, notebook.
- Archive, snapshot, backup, disaster-recovery replica.

**Đặt retention 7 ngày ở backend chưa đồng nghĩa dữ liệu chỉ tồn tại 7 ngày trong toàn hệ.** Cần lập inventory cả nguồn, đường truyền, bản sao và sink.

## 3. Phân loại dữ liệu trước khi thu thập

| Loại | Ví dụ | Hướng xử lý |
|---|---|---|
| Secrets/credentials | Password, API key, session cookie, JWT, private key | Không thu; nếu lộ cần response/rotation |
| PII trực tiếp | Email, số điện thoại, tên, địa chỉ | Không thu mặc định; thu tối thiểu theo mục đích |
| PII gián tiếp | IP, user ID, device ID, tenant-resource ID | Phân loại theo khả năng liên kết |
| Tài chính/nhạy cảm cao | Payment instrument, tài khoản, hợp đồng | Không ghi raw payload; policy chặt |
| Nội dung người dùng | Tin nhắn, ghi chú, văn bản, ảnh metadata | Không log request/response body mặc định |
| Hạ tầng nội bộ | DB URI, private hostname, topology | Giới hạn quyền và che credential |
| Dữ liệu vận hành | Error code, duration, query shape, result count | Thường có thể thu có kiểm soát |
| Correlation ID | Trace ID, span ID, operation ID | Cần retention/access policy và validation |

Một giá trị băm của email không tự vô danh: nếu miền đầu vào dễ đoán, attacker có thể đối chiếu. Hai thuộc tính riêng lẻ tưởng không nhạy cũng có thể đủ nhận diện khi kết hợp timestamp và resource path.

## 4. Mục đích và mức tối thiểu phải quyết định từng field

Trước khi thêm một log/trace attribute, hãy trả lời:

1. Nó giúp trả lời **câu hỏi điều tra nào**?
2. Có thể thay giá trị gốc bằng **loại thao tác, query shape, bucket, số lượng, thời gian hoặc safe error code** không?
3. Ai cần xem field này? Có thuộc tenant nào? Người xem phải có quyền gì?
4. Field sẽ được index, truyền đi, lưu và xóa như thế nào?
5. Chi phí bổ sung có phù hợp tần suất của event không?

Một log nguy hiểm:

~~~json
{
  "event": "register.failed",
  "email": "person@example.com",
  "password": "my-secret",
  "requestBody": {
    "address": "user's private address",
    "token": "token-value"
  }
}
~~~

Bản an toàn hơn:

~~~json
{
  "event": "account.create.failed",
  "service": "account-api",
  "operation": "account.create",
  "errorCode": "DUPLICATE_IDENTITY",
  "durationMs": 38,
  "traceId": "4cf0..."
}
~~~

Không có thông tin cá nhân trong mẫu thứ hai, nhưng traceId vẫn cần giới hạn quyền và thời gian lưu vì là khóa kết nối nhiều dữ liệu quan sát.

## 5. Data minimization tốt hơn cố scrub mọi thứ về sau

Ba lựa chọn:

~~~text
A. Log toàn bộ body -> Collector -> cố che email/token.
B. Serialize body -> regex mask -> emit.
C. Chỉ chọn event, operation, duration, errorCode, traceId.
~~~

**Ưu tiên C** vì không tạo dữ liệu nhạy ngay từ đầu. A có thể đã làm lộ raw payload trên network, agent và spool trước khi che. B phụ thuộc vào khả năng nhận biết mọi secret trong nested objects, lỗi exception và field mới.

Redaction ở collector vẫn hữu ích như **lớp dự phòng**, không nên là điểm kiểm soát duy nhất.

## 6. Structured logging: lưu sự kiện, không lưu câu chuyện chứa payload

Không nên:

~~~text
Order order-101 of person@example.com failed
with mongodb://user:pass@internal-host and query {"email":"..."}.
~~~

Nên dùng schema ổn định:

~~~json
{
  "timestamp": "2026-11-14T10:00:00Z",
  "severity": "WARN",
  "event": "order.read.failed",
  "service": "order-api",
  "dependency": "mongodb",
  "operation": "find",
  "errorCode": "DB_TIMEOUT",
  "durationMs": 752,
  "retryAttempt": 2,
  "traceId": "9b0f..."
}
~~~

Structured JSON giúp lọc theo errorCode và operation mà không cần parse chuỗi tự do. **Nhưng JSON không tự an toàn:** nếu gắn raw customer DTO vào một thuộc tính JSON, vấn đề vẫn tồn tại.

## 7. Java: logging theo allowlist

Ví dụ Java/SLF4J mang ý tưởng ghi fields cần thiết:

~~~java
public OrderView readOrder(String orderId) {
    long startNs = System.nanoTime();
    try {
        OrderView result = repository.read(orderId);
        long ms = (System.nanoTime() - startNs) / 1_000_000L;
        log.info("event=order.read.completed dependency=mongodb"
                + " outcome=ok durationMs={}", ms);
        return result;
    } catch (DatabaseTimeoutException e) {
        long ms = (System.nanoTime() - startNs) / 1_000_000L;
        log.warn("event=order.read.failed dependency=mongodb"
                + " errorCode=DB_TIMEOUT durationMs={}", ms);
        throw e;
    }
}
~~~

Không log **orderId**, raw request, domain object hoặc MongoDB filter. Trong code thực, nên dùng structured key-value API của logger và trace context đã được chuẩn hóa thay vì ghép mọi field vào message. Nếu một ID thật sự cần cho debug, hãy phân loại và dùng hệ correlation/token được cấp quyền.

## 8. Các mẫu log Java nên tránh

~~~java
log.debug("request={}", requestDto);
log.info("customer={}", customerDocument);
log.error("query failed: {}", mongoFilter.toJson(), e);
log.error("database connection failed for uri={}", connectionString);
~~~

Những đối tượng trên có thể được mở rộng thêm field bất kỳ qua toString/serializer. Một thay đổi DTO có thể khiến email hoặc token bị log mà không ai sửa logging code.

Thay bằng safe operation name, query shape và diagnostic counters, ví dụ keysExamined/docsExamined/returnedCount.

## 9. Stack trace và exception message cũng có dữ liệu nhạy

Ngay cả dòng:

~~~java
log.error("Unexpected database error", exception);
~~~

có thể chứa URI, literal parameter hoặc raw HTTP response trong exception message. Chính sách:

- Chỉ log errorCode/exception class được cho phép trong luồng thường.
- Dùng stack trace có giới hạn và quyền xem riêng khi thật sự cần.
- Tránh driver/debug mode ghi full command với values.
- Có processor scrub exception attributes như lớp phụ.
- Kiểm test case thư viện ném exception chứa secrets.
- Không coi regex scrub là hoàn hảo.

**Exception là dữ liệu đầu vào chưa được tin cậy để đưa nguyên văn vào kho log diện rộng.**

## 10. Log level không phải chính sách quyền truy cập

| Level | Ví dụ phù hợp | Điều cần tránh |
|---|---|---|
| ERROR | Operation fail với safe error code | Raw payload, secrets |
| WARN | Dependency latency, retries, soft error | Ghi cùng lỗi lặp hàng nghìn lần |
| INFO | State transitions của service, deployment | Log mọi GET nếu chỉ cần metric |
| DEBUG | Diagnostic có scope/time-box | Bật toàn production vĩnh viễn |
| TRACE | Instrumentation rất chi tiết khi cần | Tạo bản sao request/DB data không kiểm soát |

Không nên thay INFO bằng DEBUG vô hạn chỉ vì một incident khó. Một **dynamic debug switch** nên có owner, ticket, allowed fields, TTL tự tắt và cost guard.

## 11. Distributed trace nên đo đường đi, không sao chép dữ liệu

Một trace:

~~~text
GET /orders/{orderId}
  -> authorize
  -> Redis GET cache
  -> MongoDB find
  -> serialize response
~~~

Có thể dùng để biết:

- Request chậm ở Redis hay MongoDB?
- Truy vấn nào retry nhiều?
- Slow span tương ứng backend nào?
- Cache miss có gây source surge không?
- Có timeout ở network hay driver pool không?

Không cần mang toàn bộ order document hoặc thông tin chủ tài khoản vào span để trả lời những câu hỏi này.

## 12. Allowlist OpenTelemetry attributes

Ví dụ attributes có thể phù hợp tùy chính sách:

~~~text
service.name = order-api
db.system.name = mongodb
db.collection.name = orders
db.operation.name = find
app.cache.result = miss
app.retry.attempt = 2
app.error_code = DB_TIMEOUT
~~~

Không tự ghi:

~~~text
http.request.header.authorization
http.request.body
db.connection_string
db.query.text containing customer email
enduser.email
payment.cardNumber
user.password
~~~

Auto-instrumentation và semantic conventions thay đổi theo version; cần xem fields **thật sự được SDK/collector của bạn phát ra**, không chỉ dựa vào tên trong ví dụ.

## 13. Span name và URL là chỗ thường lộ PII

Không đặt:

~~~text
GET /users/person@example.com/profile
GET /orders/order-101
db.find(customer.email=person@example.com)
~~~

Ưu tiên:

~~~text
GET /users/{userId}/profile
GET /orders/{orderId}
mongodb.find.orders
~~~

HTTP route template hữu ích hơn raw path/query string. Đây cũng là cách giảm cardinality, vì span name không cần tạo giá trị mới cho từng email hoặc order.

## 14. Baggage cần quy tắc nghiêm ngặt hơn attributes

Telemetry baggage có thể đi qua nhiều services và trust boundaries. Không chứa:

- JWT, token, API keys.
- Email, phone, address.
- Raw tenant/customer object.
- Các thông tin mà downstream không cần biết.

Trace context dùng để correlation, **không chứng minh identity hoặc authorization**. Không tin tenantId hoặc userId chỉ vì nó có trong baggage do client gửi.

## 15. Head sampling

Giả sử 100.000 traces/s với xác suất lấy mẫu 10%:

\[
N_{\text{sampled}}\approx100.000\times0{,}1=10.000\ \text{traces/s}
\]

Ưu điểm: giảm lượng dữ liệu và network từ sớm, chi phí collector thấp hơn.

Giới hạn: thời điểm quyết định lấy mẫu chưa biết trace sẽ chậm hoặc lỗi; có thể bỏ qua sự cố hiếm. Sampling parent-based và propagation cần nhất quán nếu muốn traces đủ spans.

Dùng metric/error counters riêng để theo dõi **toàn bộ request population**. Không lấy raw count của sampled traces làm số lượng lỗi thật.

## 16. Tail sampling

Tail sampling có thể giữ:

~~~text
Traces có ERROR status.
Traces có duration > ngưỡng.
Một phần healthy traces làm baseline.
~~~

Nhưng collector cần buffer spans để chờ quyết định. Khi tải cao:

- Collector có thể OOM hoặc drop incomplete traces.
- Spans phân tán qua nhiều collectors có thể không gặp đúng điểm quyết định.
- Timeouts có thể khiến trace không đủ dữ liệu.
- Sampling decisions có overhead và độ trễ.

Nên theo dõi buffered-trace count, decision latency, dropped spans và exporter queue, đồng thời đặt memory/CPU budgets.

## 17. Trace sampling khác log sampling

Một policy ví dụ:

| Tín hiệu | Hướng thu |
|---|---|
| Healthcheck success | Metric, không cần INFO mỗi lần |
| Redis hit | Counter/histogram thay vì log từng hit |
| Cache miss bất thường | Sampling/rate limit theo event |
| DB slow query | Diagnostic summary có query shape |
| ERROR nghiêm trọng | Safe error log, có protection chống log storm |
| DEBUG | Phạm vi và thời gian ngắn |
| Audit/security-critical | Thu theo audit contract, không sample tùy tiện |

Không áp dụng tỷ lệ 1% duy nhất cho cả log INFO, trace và sự kiện bắt buộc phải được ghi bền.

## 18. Metric label cardinality cao làm nổ chi phí

Metric phù hợp:

~~~text
db_request_duration_seconds{
  service="order-api",
  operation="find",
  collection="orders",
  outcome="ok"
}
~~~

Metric không phù hợp:

~~~text
db_request_duration_seconds{
  orderId="order-101",
  customerEmail="person@example.com",
  requestId="req-900"
}
~~~

Mỗi ID mới tạo thêm time series mới. Trường này vừa làm tăng bộ nhớ/index/query cost vừa có thể định danh khách hàng. IDs ngẫu nhiên thường nên ở traces/logs có quyền chứ không ở metric labels.

## 19. Nhân bội cardinality

Giả sử một metric có:

~~~text
region: 4 giá trị.
operation: 8.
outcome: 5.
tenantId: 20.000.
~~~

Số tổ hợp lý thuyết:

\[
4\times8\times5\times20.000=3.200.000
\]

Nếu bỏ tenantId, còn:

\[
4\times8\times5=160
\]

Đây không phải chi phí chính xác vì không phải tổ hợp nào cũng xuất hiện, nhưng cho thấy một label high-cardinality có thể nhân bội số series. Nếu cần per-tenant diagnostics, nên tạo hệ thống truy vấn riêng với phân quyền, retention và budget đã định.

## 20. Query shape thay cho query literal

Query NoSQL nguy hiểm khi được log:

~~~javascript
db.users.find({ email: "person@example.com" });
db.orders.find({ customerId: "customer-9", status: "PAID" });
~~~

Diagnostic summary an toàn hơn:

~~~json
{
  "dbSystem": "mongodb",
  "operation": "find",
  "collection": "users",
  "queryShape": "email_eq",
  "durationMs": 112,
  "indexName": "email_unique",
  "keysExamined": 1,
  "docsExamined": 1,
  "resultCount": 1
}
~~~

Query shape cần phản ánh cấu trúc điều kiện/filter/sort chứ không chứa values. Một số tên collection và index cũng có thể là metadata nội bộ cần phân quyền.

## 21. MongoDB profiler và diagnostic logs

MongoDB profiling/change in diagnostic level có thể cung cấp thông tin về truy vấn chậm, kế hoạch thực thi và các field truy vấn tùy version, config và operation.

Trước khi bật trên production:

1. Xác định thật rõ **profiler ghi những trường nào** và có literal values không.
2. Ưu tiên slow threshold hoặc sampling thay vì mọi operation.
3. Chỉ bật cho scope/period được duyệt.
4. Hạn chế quyền truy cập profiler storage.
5. Kiểm retention, capping và log forwarding.
6. Dùng query plan/executionStats, keysExamined/docsExamined khi đủ để chẩn đoán.
7. Tắt mode chi tiết sau incident và xác nhận trạng thái.

Không coi một output explain hay profiler là mặc nhiên vô hại: query filters vẫn có thể chứa dữ liệu cá nhân.

## 22. Redis MONITOR và key privacy

Redis MONITOR hữu ích trong một số tình huống đặc biệt nhưng có thể tạo overhead và hiển thị commands/arguments theo semantics hiện hành. Nếu key chứa email hoặc session token, raw command monitoring có thể tạo bản sao PII.

Ưu tiên:

- Cache hit/miss, latency, memory, eviction metrics.
- Slowlog theo policy và thời lượng.
- Instrumentation theo command type và safe namespace.
- Sampling có giới hạn, chỉ khi có incident được duyệt.

Không chạy MONITOR vô hạn ở production và không dán raw command stream vào ticket công khai.

## 23. Cassandra query tracing

Cassandra tracing có thể giúp nhìn coordinator, replicas, latency, tombstones và đường xử lý truy vấn tùy phiên bản/cấu hình. Nó cũng có overhead và metadata nhạy.

Khi cần debug:

- Chọn query shape cụ thể.
- Giới hạn sampling/thời gian.
- Không log raw partition key nếu có thể nhận diện khách.
- Kiểm lưu trữ và cleanup tracing data.
- Theo dõi impact tới latency và I/O của hệ.

Một trace cho thấy có nhiều tombstones là tín hiệu hiệu năng; không nhất thiết phải ghi mọi giá trị row.

## 24. DynamoDB/managed NoSQL telemetry

Managed database có thể không cho người dùng xem mọi internal buffer/cache, nhưng ứng dụng vẫn đo được:

- Operation name.
- Latency, throttling, retries.
- Consumed capacity theo trường/bucket phù hợp.
- SDK timeout/error code.
- Table alias được phân quyền.
- Client request attempt count.

Không log full GetItem/PutItem/UpdateItem request/response hoặc keys chứa user ID chỉ vì thiếu database internal diagnostics.

## 25. Connection string thường chứa credential

Không log raw:

~~~text
mongodb://username:password@db.internal/commerce
redis://:password@cache.internal:6379
~~~

Thay bằng:

~~~json
{
  "dependency": "mongodb",
  "clusterAlias": "commerce-primary",
  "errorCode": "CONNECTION_TIMEOUT"
}
~~~

Ngay cả hostname và topology cũng có thể thuộc nhóm confidential. Nên sử dụng safe aliases để chẩn đoán và secret manager để quản lý credentials. Nếu URI xuất hiện trong log, cần xử lý như một sự cố secret exposure, không chỉ xóa một dashboard row.

## 26. Masking, tokenization, hashing và encryption

| Cách | Ý nghĩa | Giới hạn |
|---|---|---|
| Masking | Ẩn một phần field | Có thể vẫn nhận diện người |
| Random token | Thay value bằng mapping | Cần bảo vệ mapping store |
| Plain hash | Hash ổn định không có secret | Có thể bị dictionary attack |
| HMAC/keyed hash | Correlation có kiểm soát bằng secret | Key management, dữ liệu vẫn có thể liên kết |
| Encryption | Che giá trị khỏi người không có key | Người có key có thể giải mã, không làm data vô danh |
| Không thu | Tránh tạo bản sao | Có thể mất một số chi tiết debug |

Ví dụ correlation token:

~~~text
token = HMAC(secretKey, tenantScope + ":" + customerId)
~~~

Cần domain separation theo mục đích, key rotation/version, access control và đánh giá re-identification. Không log chính secretKey. **Pseudonymized data vẫn có thể là dữ liệu cá nhân** theo bối cảnh.

## 27. Redaction theo nhiều lớp

~~~mermaid
flowchart TD
    S["Instrumentation source"] --> A["Field allowlist"]
    A --> C["Collector: drop/redact/transform"]
    C --> R["Route theo data class"]
    R --> H["Operational hot store"]
    R --> AU["Audit/restricted archive"]
    H --> TTL["Index lifecycle"]
    AU --> GOV["Retention/legal hold/access audit"]
~~~

Quan trọng là thứ tự:

~~~text
Nếu raw data -> vendor A -> scrub tại vendor B,
thì vendor A đã nhận raw data.
~~~

Test các biến thể:
- Header authorization với chữ hoa/thường.
- JSON nested arrays.
- URL query strings.
- Exception messages.
- Base64-encoded tokens.
- Fields tự động từ SDK/driver.
- Span events và baggage.
- User-controlled operation names.

Redaction rule có false negatives; **chỉ emit allowlisted fields** vẫn là cách giảm rủi ro nền tảng.

## 28. Không sao chép input nguyên bản rồi trừ field nhạy

Ví dụ pseudo không tốt:

~~~text
safe = copyAll(request)
delete safe.password
delete safe.email
emit(safe)
~~~

Nếu ngày mai DTO thêm accessToken, nó đi vào log ngay.

Ưu tiên:

~~~text
safe = {
  event: approvedEventName,
  operation: approvedOperation,
  outcome: approvedOutcome,
  errorCode: approvedErrorCode,
  durationMs: measuredDuration,
  traceId: validatedTraceId
}
emit(safe)
~~~

Field được phép cũng cần validation. Không để user input tùy ý trở thành event name hoặc metric dimension.

## 29. Chi phí log có nhiều thành phần

Một mô hình:

\[
C_{\mathrm{total}} =
C_{\mathrm{ingest}} +
C_{\mathrm{index}} +
C_{\mathrm{hotStorage}} +
C_{\mathrm{archive}} +
C_{\mathrm{query}} +
C_{\mathrm{egress}} +
C_{\mathrm{collector}} +
C_{\mathrm{operations}}
\]

Theo backend, hóa đơn có thể phụ thuộc ingest bytes, event count, indexed dimensions, stored GB-month, query compute, archive retrieval hoặc network transfer.

**Giảm số bytes không nhất thiết giảm chi phí tỷ lệ thuận**, đặc biệt khi gói giá có fixed fees, tiers, replicas và query charges. Cần kiểm billing metrics thực tế.

## 30. Ví dụ tính raw log ingest

Giả định:

~~~text
20.000 requests/giây.
2 log records/request.
1,5 KB (decimal)/record.
~~~

Số event mỗi giây:

\[
E=20.000\times2=40.000\ \mathrm{events/s}
\]

Lưu lượng thô:

\[
40.000\times1{,}5\ \mathrm{KB/s}
=60.000\ \mathrm{KB/s}
=60\ \mathrm{MB/s}
\]

Nếu ổn định 24 giờ:

\[
60\times86.400=5.184.000\ \mathrm{MB/day}
\]

tức khoảng **5,184 TB/ngày raw** theo đơn vị thập phân. Đây chưa tính sampling, compression, index, replicas, archiving hoặc traffic biến đổi theo giờ.

Vì thế chỉ thêm một log INFO cho mỗi request có thể tạo chi phí lớn trên hệ QPS cao.

## 31. Công thức lưu trữ và retention

Một ước tính đơn giản:

\[
S_{\mathrm{retained}} \approx
D_{\mathrm{day}}\times T_{\mathrm{days}}\times F
\]

Trong đó:

- \(D_{\mathrm{day}}\): dữ liệu giữ lại mỗi ngày sau sampling/filter.
- \(T_{\mathrm{days}}\): số ngày retention.
- \(F\): hệ số thực nghiệm của compression, indexing và replication.

Ví dụ giả định:

~~~text
100 GB/ngày ingested/retained.
14 ngày searchable.
Storage factor F=1,4.
~~~

Suy ra:

\[
100\times14\times1{,}4 = 1.960\ \mathrm{GB}
\]

**1,4 chỉ là giả định mô hình**, không phải overhead chuẩn. Một số dịch vụ thu phí ingest riêng dù dữ liệu chỉ lưu vài ngày.

## 32. Ví dụ trace volume

Giả sử:

~~~text
10.000 requests/s.
12 spans/request.
900 bytes/span.
Head sample 5%.
~~~

Spans được giữ kỳ vọng:

\[
10.000\times12\times0{,}05 = 6.000\ \mathrm{spans/s}
\]

Volume thô:

\[
6.000\times900=5{,}4\ \mathrm{MB/s}
\]

Nếu lưu lượng không đổi:

\[
5{,}4\times86.400=466.560\ \mathrm{MB/day}
\]

tức **466,56 GB/ngày raw** theo đơn vị thập phân. Trong thực tế, số spans/trace, routing, sampling consistency, exporter drops và backend metadata làm kết quả khác.

## 33. Sampling không thay giới hạn kích thước

Một trace sampled vẫn có thể có:
- Hàng chục nghìn span events.
- Attributes quá dài.
- Full SQL/NoSQL query payload.
- Raw request headers.
- User identifiers có cardinality lớn.

Do đó phải giới hạn:
- Số attributes/spans/events/links.
- Max attribute value length.
- Log event size.
- Baggage length.
- Collector queue/memory.
- Indexed dimensions.

Sampling làm giảm volume kỳ vọng; **data minimization** quyết định nội dung được phép chảy vào pipeline.

## 34. Retention theo mục đích

Bảng minh họa, **không phải chính sách pháp lý**:

| Data class | Mục đích | Retention minh họa | Quyền |
|---|---|---|---|
| DEBUG diagnostics | Điều tra ngắn hạn | 1–3 ngày | Incident engineers theo ticket |
| INFO/WARN operational logs | Vận hành gần đây | 7–14 ngày | On-call liên quan |
| Sampled traces | Đường đi requests | 3–14 ngày | SRE/developers có quyền |
| Slow-query summaries | Tối ưu query | 14–30 ngày | Database/platform team |
| Metrics chi tiết | SLO/alert | 30–90 ngày, có rollup | Operations |
| Security/audit events | Truy vết hành động | Theo policy/compliance | Restricted auditors |
| Incident evidence | Điều tra vụ việc | Theo case/hold và review | Time-bound access |

Mục tiêu là có **owner, data class, mục đích, thời hạn và deletion policy** cho từng dataset. Không cho rằng retention mặc định của vendor đã được phê duyệt.

## 35. Searchable retention khác archive và backup

Một thiết kế:

~~~text
Hot searchable log index: 7 ngày.
Archive: 30 ngày.
Backup snapshots: 14 ngày.
Collector disk spool: tối đa vài giờ.
~~~

Không thể tuyên bố “log chỉ giữ 7 ngày”: bản sao archive/backup vẫn có thể tồn tại sau khi biến mất khỏi search UI.

Ngoài ra, xóa từ index có thể là bất đồng bộ. TTL, compaction hoặc object-store lifecycle rules có semantics vật lý khác nhau. Cần xác định **retention thực tế của toàn bộ đường đi**, và kiểm chứng deletion completion theo khả năng của mỗi backend.

## 36. Mẫu khai báo chính sách một dataset

~~~yaml
dataset: order-api-operational-logs
purpose: incident-diagnostics
owner: platform-observability
classification: internal-restricted
allowedFields:
  - timestamp
  - severity
  - event
  - operation
  - dependency
  - errorCode
  - durationMs
  - traceId
hotRetentionDays: 7
archiveRetentionDays: 0
accessRole: production-oncall-reader
samplingPolicy: "by event class"
deletionPolicy: "lifecycle + verification"
~~~

Đây là schema tùy chọn để mô tả chính sách, không phải cấu hình thực thi của vendor. Production có thể cần security/privacy approvers, region restrictions, tenant isolation và legal hold workflow.

## 37. Diagnostic log và audit log phải tách

Audit sự kiện thay đổi quyền:
- Có actor/role.
- Có action và resource scope.
- Có timestamp và outcome.
- Có yêu cầu chống sửa, access audit và completeness.
- Có retention theo hợp đồng/pháp luật.

DEBUG log chậm database:
- Có query shape, duration, safe errorCode.
- Có thể sample.
- Thường có retention ngắn hơn.
- Không cần giữ raw request hoặc identity.

**Audit đầy đủ không có nghĩa audit phải giữ mọi secret hay payload.** Thu đúng evidence cần thiết thay vì toàn bộ nội dung giao dịch.

## 38. Retention, legal hold và quyền xóa

Một số dữ liệu cần được giữ để điều tra, trong khi dữ liệu cá nhân phải được xóa/hạn chế theo yêu cầu cụ thể. Không giải bằng cách “log immutable chứa tất cả PII mãi mãi”.

Hướng thiết kế:
- Không đưa PII vào bản ghi dài hạn nếu không cần.
- Tách identity mapping có thể thu hồi khỏi event facts.
- Tokenization hoặc crypto controls phù hợp.
- Legal hold có owner, lý do và review deadline.
- Deletion lifecycle ở hot/archive/backup.
- Lưu bằng chứng xử lý yêu cầu mà không tái tạo raw PII.

Không tự khẳng định một thời hạn cụ thể là đúng luật cho mọi quốc gia; phải có đánh giá pháp lý và chính sách của tổ chức.

## 39. Quyền truy cập và multi-tenant isolation

Nếu backend chứa logs của nhiều tenants, một filter tenantId ở UI **không phải cơ chế authorization**. Người dùng có thể thay URL hoặc query.

Cần:
- RBAC/ABAC ở nơi thực thi truy vấn.
- Tenant isolation theo index, dataset hoặc policy khi phù hợp.
- Quyền export/download riêng.
- Cấm dashboard public chứa dữ liệu production.
- Phân quyền archived data tương đương hot data.
- Audit việc search/export.
- Không dùng traceId làm proof of ownership.

Một on-call engineer không nhất thiết phải được xem logs của toàn bộ tenants nếu chỉ trực một phạm vi dịch vụ.

## 40. Break-glass access

Một tình huống điều tra đặc biệt có thể cần quyền rộng hơn bình thường:

~~~text
Incident ticket.
Approval theo vai trò.
Time-limited elevation.
Action/export auditing.
Automatic expiration.
Post-incident review.
~~~

Không chia sẻ raw stack traces/log dumps bằng link không cần xác thực. Một trace URL chỉ là locator; backend phải kiểm quyền trước khi trả nội dung.

## 41. Mã hóa và secret management

Đường dữ liệu:

~~~text
App -> Agent -> Collector -> Broker -> Backend -> Archive.
~~~

Cần xem:
- TLS/encrypted transport.
- Encryption at rest.
- KMS/secret manager và key rotation.
- Agent credentials theo quyền tối thiểu.
- Hạn chế connector/vendor export.
- Encryption của collector disk queues.
- Backup access và key lifecycle.

Mã hóa **không thay** data minimization hoặc RBAC: nếu backend cho phép người xem giải mã dữ liệu, họ vẫn có thể đọc nội dung.

## 42. Audit truy cập telemetry

Những hành động nên được ghi nhận theo mức rủi ro:
- Export hàng triệu log records.
- Xem security/audit dataset.
- Cấp quyền production trace.
- Thay retention hoặc legal hold.
- Tắt redaction.
- Bật DEBUG ở diện rộng.
- Tạo API token của observability platform.

Log của những hành động trên nên ghi actor, action, dataset, outcome, ticket và timestamp, **không cần ghi nguyên truy vấn chứa email/token** của người dùng.

## 43. Cost do indexing và high-cardinality fields

Không phải field nào giữ trong log cũng cần searchable.

Ví dụ:
- Index: service, environment, event, operation, severity, errorCode.
- Giữ tùy quyền: safe stack fingerprint, limited trace correlation.
- Không thu: password, token, request body.
- Không làm metric label: requestId, orderId, userEmail, traceId.

Chi phí index bao gồm memory, storage, compute và thời gian query. Một số backend vẫn hỗ trợ tìm dữ liệu không được index nhưng chậm/đắt hơn; hãy lựa chọn theo truy vấn điều tra thường dùng.

## 44. Log storms do retries

Khi MongoDB timeout:

~~~text
Một API request.
Ba retries.
Năm ERROR logs mỗi lần.
Collector retry export.
~~~

Volume có thể tăng mạnh đúng lúc hạ tầng đang yếu.

Biện pháp:
- Tổng hợp attempts thành retryCount.
- Dùng metric cho lỗi lặp.
- Rate limit repetitive diagnostics.
- Chỉ giữ representative detailed traces.
- Bounded exporter queues.
- Ưu tiên critical error/audit classes.

Không drop vô điều kiện mọi event quan trọng; cần priority và completeness policy theo loại dữ liệu.

## 45. Observability pipeline cũng có backpressure

~~~text
Application exporter queue full.
Collector memory high.
Backend ingest throttled.
Retry buffers growing.
Records dropped.
~~~

Theo dõi:
- Generated/accepted/rejected/dropped logs/spans.
- SDK exporter queue depth.
- Collector memory/CPU.
- Retry delay và oldest buffered age.
- Ingest throttling.
- Partial traces.
- Unsent audit events theo policy.

Nếu logger đồng bộ block business request, một sự cố ở observability backend có thể kéo sập API. Operational telemetry thường nên có **bounded async queues và failure behavior rõ**, còn audit bắt buộc có thể cần một đường ghi durable khác.

## 46. Fail open hay fail closed?

**Diagnostic logs:**

~~~text
Backend unavailable -> drop/buffer bounded,
business API vẫn xử lý nếu các ràng buộc khác cho phép.
~~~

**Mandatory audit:**

~~~text
Không thể ghi evidence bắt buộc -> business operation
có thể phải dừng hoặc dùng durable fallback theo security contract.
~~~

Không có câu trả lời chung cho mọi tín hiệu. Phải phân biệt business invariant, yêu cầu pháp lý và observability optimization.

## 47. Collector spool và queue cũng có retention

Một collector có thể dùng disk queue rồi retry khi backend không truy cập được. Những bản ghi raw ở spool vẫn là dữ liệu cần bảo vệ.

Cần policy:
- Max queue bytes và age.
- Encryption và file permissions.
- Dọn sau successful export.
- Retry budgets.
- Dead-letter queue retention.
- Xử lý disk-full và crash.
- Giám sát queue không giữ quá thời hạn.

“Backend chỉ giữ 7 ngày” không đủ nếu collector disk queue tồn tại hàng tuần.

## 48. Alert, ticket và chat là những bản sao khác

Một alert sai:

~~~text
Slow MongoDB query for person@example.com,
filter={"email":"person@example.com"}, token="...".
~~~

Một alert phù hợp hơn:

~~~text
order-api: MongoDB find p99 above SLO.
collection=orders
queryShape=tenant_eq_status_eq
traceLink=restricted-observability-url
~~~

Đường link cần kiểm quyền. Không cho phép alert payload mang raw user data sang hệ chat/email mà các bên có quyền rộng hơn backend.

## 49. Dynamic DEBUG phải time-box

Quy trình ví dụ:

1. Mở incident ID và giả thuyết cần xác minh.
2. Chọn một service/operation, không toàn bộ tenants.
3. Xác định fields được phép thu.
4. Có người phê duyệt và ghi action audit.
5. Đặt thời gian 15 phút theo ví dụ và tự động expire.
6. Theo dõi QPS, ingest cost, exporter queue và sensitive-data detections.
7. Xác minh log level đã trở về bình thường.
8. Xử lý dữ liệu/exports có thời hạn riêng nếu đã tạo.

**DEBUG flag không phải giấy phép thu raw secrets.**

## 50. Kết nối log với trace bằng correlation IDs

~~~json
{
  "event": "db.query.slow",
  "service": "order-api",
  "dependency": "mongodb",
  "operation": "find",
  "queryShape": "tenant_eq_createdAt_range",
  "durationMs": 380,
  "traceId": "9b0f...",
  "spanId": "5f21..."
}
~~~

Trace ID giúp liên kết các sự kiện log với trace nếu trace được sample và còn retention. Nếu trace không có, log safe summary vẫn hữu ích. **Không đưa traceId thành metric label** vì mỗi request tạo giá trị mới.

## 51. Mẫu diagnostics an toàn cho MongoDB

~~~json
{
  "event": "db.query.slow",
  "dbSystem": "mongodb",
  "collection": "orders",
  "operation": "find",
  "queryShape": "tenant_eq_status_eq_createdAt_range",
  "indexUsed": "tenant_status_createdAt",
  "keysExamined": 50000,
  "docsExamined": 18000,
  "returnedCount": 20,
  "durationMs": 310
}
~~~

Thông tin trên đủ để nhận ra query scan lớn hơn kết quả mà không phải lưu tenantId, danh sách đơn hàng hoặc filter literal. Tên index/collection vẫn phải được kiểm soát trong môi trường có schema nhạy.

## 52. Mẫu diagnostics an toàn cho Redis

~~~json
{
  "event": "cache.operation",
  "cacheSystem": "redis",
  "command": "GET",
  "cacheNamespace": "product-summary",
  "result": "miss",
  "durationMs": 8,
  "sourceFallback": "mongodb"
}
~~~

Theo dõi thêm hit/miss ratio, evictions, expired keys, memory, Redis latency và source QPS. Không log raw key nếu key chứa email/customer ID, và không log value.

Từng cache hit thường nên được **đếm bằng metrics** thay vì emit một log INFO riêng.

## 53. Mẫu diagnostics cho Cassandra

~~~json
{
  "event": "db.query.slow",
  "dbSystem": "cassandra",
  "table": "events_by_account",
  "queryShape": "partition_eq_time_range",
  "consistency": "QUORUM",
  "durationMs": 190,
  "tombstonesScannedBucket": "1k-10k"
}
~~~

Nên ưu tiên bucket/shape thay raw partition key. Khi điều tra, có thể ghép thêm per-node repair/compaction metrics và replica latency thay vì đọc payload event.

## 54. Mẫu diagnostics cho DynamoDB

~~~json
{
  "event": "dynamodb.operation",
  "operation": "Query",
  "tableAlias": "user-preferences",
  "outcome": "throttled",
  "retryCount": 2,
  "durationMs": 420,
  "consumedCapacityBucket": "1-5"
}
~~~

Những trường hợp khác nhau cần chính sách dữ liệu và API semantics khác nhau, nhưng không nên đưa item values, signing credentials hoặc raw partition key vào logs.

## 55. Data deletion ở hệ quan sát

Một yêu cầu xử lý dữ liệu cá nhân có thể cần xem xét:

~~~text
Hot log index.
Trace backend.
Archived object storage.
Collector disk spool.
Data warehouse exports.
Backup snapshots.
Alert/chat/ticket copies.
Metric exemplars hoặc labels.
```

Quy trình:
1. Inventory datasets và data owners.
2. Tìm các bản sao trong phạm vi yêu cầu.
3. Xác định legal hold/retention requirements.
4. Thực hiện xóa hoặc crypto-controls theo policy.
5. Kiểm nhận ở mỗi sink, không chỉ hot index.
6. Ghi bằng chứng xử lý không tái tạo raw dữ liệu.

Nếu đã tránh log PII từ nguồn thì yêu cầu xóa thường đơn giản hơn nhiều.

## 56. DLP/secret scanning là lớp hỗ trợ

Scanner có thể phát hiện email patterns, JWT-like strings, URI chứa credentials, payment-number-like strings. Nhưng:

- Có false positive và false negative.
- Secrets có thể encoded hoặc có định dạng lạ.
- Nested stack traces/attachments khó quét hết.
- Scanner cần xử lý raw data trong phạm vi tin cậy.
- Một field nhạy không có pattern dễ nhận diện.

Dùng kết hợp **allowlist, integration tests, scanning và incident response**, không coi một kết quả scan sạch là bảo đảm an toàn tuyệt đối.

## 57. Metrics theo dõi chi phí/retention của hệ observability

| Metric | Câu hỏi |
|---|---|
| ingest_bytes_per_day | Dataset nào làm tăng hóa đơn? |
| log_events_per_second | Có log storm không? |
| avg_event_size | Có raw payload mới? |
| span_count/exported/dropped | Trace sampling pipeline khỏe không? |
| indexed_field_cardinality | Index có bùng nổ không? |
| active_metric_series | Metrics storage có bị nhân bội? |
| hot_storage_bytes | Footprint hot index |
| archive_bytes/age | Bản sao lưu dài hạn |
| deletion_queue_age | Dữ liệu chờ xóa lâu không? |
| collector_queue_depth | Pipeline có nghẽn không? |
| ingest_rejections | Backend có từ chối? |
| sensitive_data_detection_count | Có khả năng leakage không? |
| debug_mode_active_count | DEBUG có bị bỏ quên? |
| telemetry_access_exports | Ai export dữ liệu? |

Không gắn chính token hoặc user ID vào label của metric giám sát leakage.

## 58. Runbook: phát hiện access token trong log

1. Ngừng nguồn ghi token, rollback hoặc chỉnh instrumentation.
2. Xác định token type, privileges, thời điểm và phạm vi lộ.
3. Thu hồi/rotate token và credentials liên quan theo security procedure.
4. Khoanh vùng quyền truy cập log, archive, exports và alert copies.
5. Kiểm collector spool, backend, archive, tickets và các bên nhận.
6. Thực hiện xử lý xóa/cách ly theo incident/privacy policy.
7. Kiểm access/export audit và ảnh hưởng có thể xảy ra.
8. Thêm regression test và allowlist rule.
9. Báo cáo security incident theo quy trình tổ chức.

**Chỉ xóa một dòng log mà không thu hồi token có thể chưa xử lý nguy cơ từ token đã lộ.**

## 59. Runbook: chi phí tăng bất thường

Giả sử ingest tăng từ 50 GB/ngày lên 2 TB/ngày.

1. Tách theo service, environment, severity và event type.
2. So events/s và average bytes/event.
3. Kiểm DEBUG switch, retries, exception loops.
4. Tìm field mới lớn hoặc raw payload.
5. Kiểm indexed fields/cardinality.
6. Kiểm duplicate forwarding hoặc collector retries.
7. Chỉ throttle/sample tín hiệu có giá trị thấp theo policy.
8. Bảo vệ critical audit và alerts.
9. Đối chiếu storage/retention và budget.
10. Bổ sung alert về volume growth và field drift.

Đừng drop mọi ERROR logs vô điều kiện nếu chúng đang cần cho điều tra outage.

## 60. Runbook: không tìm được trace sau sự cố

Nguyên nhân:
- Trace chưa được sample.
- Collector/exporter drop.
- Backend reject/throttle.
- Trace đã hết retention.
- Archive cần restore.
- Cross-service trace context propagation bị hỏng.
- Log không mang traceId tương ứng.

Cải thiện:
- Giữ safe error logs cho incident classes quan trọng.
- Tail sampling với resource limits.
- Metric lỗi đầy đủ trên tất cả requests.
- Theo dõi dropped/partial traces.
- Quy trình time-boxed incident evidence khi được phê duyệt.

Không kéo dài retention vô hạn chỉ vì một lần thiếu trace.

## 61. Quy trình thiết kế policy từ đầu

~~~mermaid
flowchart TD
    A["Business/incident questions"] --> B["Phân loại signal và field"]
    B --> C["Allowlist và privacy review"]
    C --> D["Sampling, cardinality, size limits"]
    D --> E["Estimate volume và cost"]
    E --> F["RBAC, encryption, tenant isolation"]
    F --> G["Retention + archives + deletion"]
    G --> H["Monitoring và incident drills"]
    H --> I["Review theo dữ liệu thật"]
~~~

Các bước cụ thể:
1. Liệt kê queries/diagnostic questions.
2. Xác định signal nào trả lời tốt nhất.
3. Thiết kế schema chỉ giữ fields cần.
4. Chặn secrets/PII tại nguồn.
5. Sampling hợp với từng event class.
6. Đặt cardinality và event-size budget.
7. Tính ingest, index, storage, query, archive và transfer.
8. Xác định retention/owner/permissions.
9. Thiết lập collector limits, spool encryption và telemetry-loss metrics.
10. Kiểm exports, alerts, archives, backups.
11. Thử incident giả lập token leak/log storm/collector outage.
12. Review thường kỳ chi phí, retention và rủi ro.

## 62. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
|---|---|---|
| Log JSON tự an toàn | JSON vẫn có token/PII | Allowlist |
| DEBUG chỉ bật lúc cần nên vô hại | Incident traffic làm volume tăng | Scope/time-box |
| Regex scrub là đủ | Nested/encoded secrets lọt qua | Source minimization |
| Hash email là vô danh | Có thể dictionary attack | Tokenization/privacy review |
| Trace ID chứng minh danh tính | ID chỉ correlation | Authz riêng |
| Baggage chỉ ở service hiện tại | Có thể truyền xuyên trust boundary | Không chứa secrets |
| db.query.text luôn an toàn | Có literal filters | Query shape |
| MongoDB profiler không chứa PII | Có thể ghi command details | Kiểm config/version |
| Redis MONITOR không có chi phí | Overhead và raw arguments | Dùng có kiểm soát |
| Cassandra tracing phải bật tất cả | Overhead lớn | Targeted sampling |
| orderId là metric label tốt | Cardinality lớn | Logs/traces phân quyền |
| Head sample giữ đủ mọi lỗi | Lỗi hiếm bị bỏ | Metrics và tail sampling |
| Tail sample giữ mọi trace lỗi | Collector có thể drop | Loss metrics |
| Hot index 7 ngày nghĩa mọi dữ liệu 7 ngày | Archive/backup/spool còn | Full lifecycle |
| TTL xóa vật lý đúng giờ | Deletion async | Verify retention |
| Audit phải giữ mọi payload | Rủi ro quá mức | Facts cần thiết |
| Tắt logging khi backend down luôn đúng | Critical audit có thể bắt buộc | Per-signal failure policy |
| Collector không lưu dữ liệu | Disk spool có thể tồn tại | Retention/encryption |
| Alert không phải storage | Email/ticket có bản sao | Sanitize notifications |
| Mã hóa thay thế RBAC | Người có quyền vẫn đọc | Layered controls |
| Sampling làm giảm mọi loại phí tuyến tính | Billing có nhiều yếu tố | Model theo vendor |
| Index mọi field để tìm dễ | Tăng storage/cardinality | Index theo mục đích |
| Backend ingest = số events thật | Drops/sampling/retries | End-to-end metrics |
| Tăng DEBUG toàn production là nhanh nhất | Lộ PII, phí và overload | Targeted diagnostics |
| Xóa log là đã xử lý credential leak | Token vẫn có thể dùng | Revoke/rotate |
| Privacy chỉ áp cho production | Staging cũng có thể chứa real data | Phân loại mọi môi trường |

## 63. Bài tập thực hành

### Bài tập 1 — Phân loại field

Cho: email, orderId, traceId, password, errorCode, db URI, indexName, durationMs, IP, customerAddress, sourceVersion. Phân loại risk, chọn field được log, token hóa hoặc loại bỏ. Giải thích mục đích.

### Bài tập 2 — Sửa Java logging

Một service log nguyên request DTO và customer document. Viết lại thành structured event theo allowlist và mô tả test chống log secret khi DTO có field mới.

### Bài tập 3 — Exception chứa database URI

Một exception chứa mongodb://user:password@db. Làm sao giữ dependency/errorCode/traceId mà không lộ credential? Runbook xử lý credential đã lộ?

### Bài tập 4 — Query shape

Thay MongoDB filter theo email/customerId bằng query shape; chọn thêm keysExamined/docsExamined/indexUsed/duration. Vì sao vẫn debug được index?

### Bài tập 5 — Trace span

Thiết kế MongoDB find span với safe attributes và route template. Phân biệt span name và raw request path.

### Bài tập 6 — Baggage

Một team truyền JWT và email qua baggage để theo dõi user. Phân tích rủi ro và đưa ra context thay thế.

### Bài tập 7 — Cardinality

Metric có region 4, operation 8, status 5, tenantId 20.000. Tính số tổ hợp lý thuyết; thiết kế metric labels thấp cardinality.

### Bài tập 8 — MongoDB profiler

Một người muốn bật profiler toàn bộ 30 ngày. Đề xuất slow threshold, sampling, scope, access, retention và cách kiểm fields nhạy.

### Bài tập 9 — Redis diagnostics

Khi Redis p99 tăng, tại sao MONITOR có thể nguy hiểm? Thiết kế metrics, slowlog và controlled sampling thay thế.

### Bài tập 10 — Cassandra tracing

Query theo partition/time range có nhiều tombstones. Chọn diagnostic fields đủ tìm nguyên nhân mà không ghi raw partition key.

### Bài tập 11 — DynamoDB throttling

Thiết kế log cho Query bị throttled: retries, duration, table alias, capacity bucket, outcome. Không log item values.

### Bài tập 12 — Head sampling

100.000 traces/s, tỷ lệ 10%. Tính traces/s kỳ vọng; giải thích vì sao lỗi hiếm vẫn bị bỏ sót.

### Bài tập 13 — Tail sampling

Thiết kế policy ưu tiên error/slow traces. Nêu bộ nhớ, timeout và loss metrics của collector.

### Bài tập 14 — Log sampling và audit

Có đề xuất sample 1% toàn bộ signals kể cả security audit. Vì sao sai? Phân loại completeness requirements.

### Bài tập 15 — Tính ingest

20.000 req/s, 2 logs/request, 1,5 KB mỗi log. Tính events/s, MB/s và TB/ngày theo đơn vị thập phân.

### Bài tập 16 — Tính storage

100 GB/ngày, 14 ngày retention, factor 1,4. Tính footprint; so 7/30 ngày, nêu những phí khác chưa tính.

### Bài tập 17 — Tính trace volume

10.000 req/s, 12 spans/request, 900 bytes/span, head sample 5%. Tính spans/s và GB raw/ngày.

### Bài tập 18 — Cost model

Tạo mô hình gồm ingest, index, hot storage, archive, query, egress, collector và operations. Cần dữ liệu billing nào để hiệu chỉnh?

### Bài tập 19 — Retention matrix

Đề xuất retention riêng cho DEBUG, INFO, sampled traces, query summaries, metrics và audit. Nêu owner và deletion verification.

### Bài tập 20 — Multi-tenant log access

Một dashboard chỉ lọc tenantId ở URL. Thiết kế backend RBAC/ABAC và test không truy cập chéo tenant.

### Bài tập 21 — HMAC token

Cần correlation các incidents của một customer mà không log ID gốc. Thiết kế HMAC/tokenization, key scope/rotation và retention.

### Bài tập 22 — Redaction pipeline

Ứng dụng gửi raw body rồi collector mới xóa email. Hãy liệt kê chỗ đã nhận raw data và cách sửa nguồn thu thập.

### Bài tập 23 — DLP scanning

Viết test cases cho authorization header, nested JSON, connection string và base64 token. Vì sao scan sạch chưa chứng minh không có PII?

### Bài tập 24 — Alert payload

Một alert chứa raw MongoDB filter/email. Viết alert mới có query shape, p99, safe trace link và quyền xem.

### Bài tập 25 — Incident token exposure

Phát hiện access token trong logs ba ngày trước. Viết runbook stop source, rotate/revoke, tìm copies, xử lý archive và audit accesses.

### Bài tập 26 — Cost spike

Ingest tăng từ 50 GB/ngày lên 2 TB/ngày. Phân tích event count, mean size, retry loop, DEBUG switch, duplicate forwarding và index cost.

### Bài tập 27 — Collector outage

Collector bị lỗi 30 phút. Đề xuất bounded queue/fail-open cho DEBUG và durable policy cho audit bắt buộc.

### Bài tập 28 — Debug time-box

Thiết kế bật DEBUG 15 phút cho một operation với ticket, approval, allowed fields, budget và automatic expiry.

### Bài tập 29 — Xóa dữ liệu

Một user yêu cầu xóa trong lúc PII đã vào hot logs, traces, archive, ticket exports và backup. Hãy lập inventory, policy exceptions, hành động và verification.

### Bài tập 30 — Trace không tìm thấy

Sau hai ngày, traceId không có trong backend. Phân biệt sampling, exporter drops, retention, archive và context propagation.

### Bài tập 31 — Observability platform plan

Thiết kế hệ Java API + MongoDB + Redis + Cassandra + OpenTelemetry. Bao gồm: signal taxonomy, safe schema, query shapes, sampling, cardinality budget, cost estimate, retention tiers, RBAC, encryption, tenant isolation, deletion lifecycle, collector failure policy.

### Bài tập 32 — Phản biện kiến trúc sai

Một thiết kế đề xuất:

~~~text
Log mọi MongoDB command và response body.
Đưa userEmail vào span và metric label.
Bật DEBUG cho mọi tenant 30 ngày.
Chuyển raw logs tới vendor rồi mới redact.
Hot index retention 365 ngày, không xét backups.
Trace link mở được nếu biết URL.
Backend lỗi thì logger đồng bộ chờ vô hạn.
~~~

Chỉ ra lỗi, hậu quả và thay bằng một chính sách **chẩn đoán đủ, dữ liệu tối thiểu, chi phí có ngân sách, retention rõ chủ sở hữu và API an toàn khi telemetry lỗi**.

---

**Kết luận:** Log, trace, metric và profiler không chỉ là dữ liệu kỹ thuật vô hại. Chúng là **các bản sao của thông tin trong hệ NoSQL** có vòng đời, khả năng liên kết, chi phí và quyền truy cập riêng. Cách kiểm soát tốt bắt đầu bằng **không thu secrets/PII/payload không cần thiết tại nguồn**, ghi structured events và query shapes, dùng trace names/attributes có allowlist, hạn chế baggage, sampling và cardinality đúng mục tiêu. Chi phí phải được tính từ ingest, index, storage, archive, query và collector overhead; retention phải bao gồm cả hot index, archive, spool, backup và exported copies. **Audit quan trọng không bị đánh đồng với DEBUG**, và mọi chế độ chẩn đoán sâu phải có phạm vi, thời hạn, quyền và ngân sách. Một hệ thống quan sát đáng tin giúp tìm lỗi NoSQL nhanh hơn mà không trở thành nguyên nhân rò rỉ dữ liệu hoặc làm phát sinh một sự cố vận hành mới.
