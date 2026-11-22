# Giới hạn kích thước, phân trang và truyền dữ liệu theo luồng

## Mục tiêu bài học

Trong giao tiếp đồng bộ giữa các Microservices, việc trả dữ liệu đúng mới là điều kiện cần. Một API còn phải kiểm soát **lượng dữ liệu truyền qua mạng, bộ nhớ khi xử lý, thời gian chờ, tài nguyên database và khả năng phục hồi khi kết nối bị ngắt**. Một endpoint xuất một triệu dòng thành một JSON array có thể hoạt động trên máy phát triển, nhưng gây hết heap, timeout ở gateway, giữ connection pool quá lâu hoặc làm chậm mọi request khác trong production.

Ba công cụ thiết kế cần phân biệt:

1. **Giới hạn kích thước:** ngân sách về byte, số bản ghi, thời gian, query complexity, số kết nối và quota của mỗi yêu cầu.
2. **Phân trang (pagination):** yêu cầu từng phần của một tập kết quả, thường phù hợp giao diện danh sách, tìm kiếm, feed và các tác vụ đọc có checkpoint.
3. **Truyền theo luồng (streaming):** gửi hoặc nhận dữ liệu dần trong lúc xử lý, thay vì phải giữ toàn bộ payload trong bộ nhớ trước khi có thể truyền.

Ba khái niệm bổ trợ nhau nhưng không thay thế nhau. Một stream vẫn cần giới hạn bytes và thời gian; một endpoint phân trang vẫn có thể dùng streaming cho từng response; một export quá lớn có thể nên chạy thành job bất đồng bộ thay vì giữ HTTP request mở.

Sau bài này, bạn có thể:
- Đặt giới hạn phù hợp qua client, API gateway, ứng dụng, database và storage.
- Phân biệt offset, keyset và cursor pagination; nhận diện duplicate/missing record khi dữ liệu biến động.
- Chọn NDJSON, SSE, HTTP streaming, gRPC streaming, upload theo chunk hoặc export job theo nhu cầu.
- Thiết kế backpressure, cancellation, timeout, retry và cơ chế tiếp tục khi đường truyền đứt.
- Áp dụng mẫu Spring Boot và kiểm thử hiệu năng, tính đầy đủ và an toàn.

## 1. Tại sao một response lớn lại nguy hiểm?

Giả sử Reporting service lấy tất cả đơn hàng trong tháng từ Ordering:

~~~http
GET /orders?from=2026-10-01&to=2026-10-31
~~~

Một implementation ngây thơ có thể:

1. Query một triệu dòng từ database.
2. Tạo List chứa một triệu entity trong JVM.
3. Ánh xạ tất cả entity thành DTO.
4. Serialize mọi DTO thành một JSON array lớn.
5. Đưa toàn bộ response qua gateway về client.

Chi phí có thể xuất hiện ở nhiều nơi:

| Thành phần | Chi phí |
| --- | --- |
| Database | Scan, sort, join, lock/transaction, I/O |
| Application | Heap, CPU, object allocation, GC |
| Serializer | Buffer, CPU, encoding |
| Network | Băng thông, packet, latency |
| Gateway/proxy | Buffering, timeout, giới hạn body |
| Client | Memory, parse time, khả năng treo giao diện |
| Vận hành | Tăng tải lặp khi client retry, khó kiểm soát concurrency |

Một JSON 100 MB có thể cần lớn hơn 100 MB heap vì entity, object graph, string và các buffer tạm cùng tồn tại. Tỷ lệ cụ thể phụ thuộc model, serializer và luồng xử lý; cần đo thay vì giả định.

Hậu quả thường thấy:
- OutOfMemoryError hoặc GC pause cao.
- p95/p99 latency tăng.
- Connection pool hoặc thread pool bị chiếm dụng.
- Proxy/gateway đóng request trước khi hoàn tất.
- Người dùng chỉ cần 20 kết quả đầu nhưng phải chờ toàn bộ tập.
- Retry khiến cùng truy vấn nặng lặp đi lặp lại.

**Thiết kế tốt phải giới hạn tài nguyên tiêu thụ bởi một thao tác đơn lẻ, không chỉ tăng RAM hoặc timeout.**

## 2. Các loại giới hạn quan trọng

| Giới hạn | Ví dụ minh họa | Mục đích |
| --- | --- | --- |
| Request body bytes | Không nhận payload vượt ngưỡng | Tránh upload/deserialize quá lớn |
| Response rows/bytes | Giới hạn một trang hay một export | Tránh trả tập dữ liệu không kiểm soát |
| Page size | Mặc định 25, tối đa 200 | Bảo vệ query và serialization |
| Query complexity | Giới hạn filter, join, sort và scan cost | Tránh query ít byte nhưng rất nặng |
| Database timeout | Statement/query deadline | Tránh giữ DB vô hạn |
| Connection concurrency | Số stream/export đồng thời | Giữ công bằng cho request khác |
| Upload/download quota | Tổng bytes theo user/tenant | Chống tiêu thụ tài nguyên quá mức |
| Buffer capacity | Bounded queue và write buffer | Ngăn tăng heap khi client chậm |
| Total stream duration | Giới hạn thời gian tồn tại stream | Ngăn kết nối treo |
| API rate limit | Request/s hoặc công việc/giờ | Chống abuse và retry storm |

Các số trong bảng chỉ minh họa, không phải tiêu chuẩn cố định. Chọn dựa trên kích thước record, workload, latency SLO, băng thông và khả năng vận hành.

### 2.1. Giới hạn thực tế nằm ở nhiều tầng

~~~text
Client
  ↓
WAF / CDN / Load Balancer
  ↓
API Gateway / Ingress
  ↓
Reverse Proxy
  ↓
Application server
  ↓
Framework / JSON parser
  ↓
Service / Database / Object storage
~~~

Nếu gateway chỉ chấp nhận request 10 MB nhưng ứng dụng cấu hình 50 MB, người dùng vẫn bị từ chối ở gateway. Nếu gateway cho phép 100 MB và ứng dụng parse toàn bộ vào byte[], ứng dụng vẫn có thể hết heap. Cần kiểm tra cả các tầng và công bố giới hạn nhất quán.

### 2.2. Không chỉ kiểm tra Content-Length

Không phải mọi HTTP request đều có Content-Length; client có thể truyền body theo cơ chế stream. Hệ thống cần giới hạn **số byte thực sự đã đọc**, không chỉ dựa vào header khai báo. Với body nén, phải cân nhắc cả kích thước nén và kích thước sau giải nén để tránh zip bomb.

JSON nhỏ nhưng có nesting rất sâu hoặc hàng trăm nghìn phần tử cũng có thể tạo gánh nặng parse. Nên có giới hạn nesting depth, số phần tử, độ dài field và thời gian xử lý.

### 2.3. API contract cần công khai giới hạn

Một endpoint nên nêu:
- Page size mặc định và tối đa.
- Các trường filter/sort được phép.
- Điều kiện cursor hợp lệ và thời gian hết hạn.
- Response có totalCount hay chỉ hasMore.
- Semantics nếu bản ghi thay đổi trong lúc phân trang.
- Mã lỗi khi quá giới hạn hoặc cursor không hợp lệ.

Các mã HTTP hữu ích:
- 400 khi limit/cursor/filter sai.
- 413 Content Too Large khi request body vượt giới hạn.
- 414 URI Too Long khi URL quá dài.
- 429 Too Many Requests khi vượt quota.
- 503 khi tạm không thể xử lý.
- 206 Partial Content chỉ dành cho semantics HTTP Range nếu hỗ trợ, không phải cho trang danh sách thông thường.

## 3. Phân trang là gì và khi nào dùng?

Pagination trả một phần của tập kết quả qua từng request, ví dụ 25 đơn hàng một trang. Các trang có thể được lấy khi người dùng chuyển trang, cuộn hoặc một batch job cần đọc tiếp.

**Lợi ích:**
- Response nhỏ và nhanh hơn.
- Giới hạn số rows cần mapping và serialize trong một request.
- Client chỉ tải dữ liệu cần thiết.
- Giảm tác động của request nặng tới service.
- Dễ áp quota và retry theo từng trang.

**Hạn chế:** nhiều request không tự động thuộc cùng một snapshot. Nếu dữ liệu được thêm, xóa hoặc sửa giữa hai trang, tập kết quả có thể thay đổi. Cần nói rõ contract này.

Các chiến lược chính là offset/page-number, keyset và cursor pagination.

## 4. Offset/page-number pagination

Client có thể gọi:

~~~http
GET /orders?page=3&size=20
~~~

Hoặc:

~~~http
GET /orders?offset=60&limit=20
~~~

SQL minh họa:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

### Ưu điểm

- Dễ hiểu với UI có số trang và nút nhảy tới trang bất kỳ.
- Dễ dùng với Spring Data Pageable.
- Phù hợp tập kết quả nhỏ, ít biến động.

### Nhược điểm

**OFFSET sâu có thể đắt.** Database có thể phải xử lý nhiều dòng trước khi trả trang ở vị trí xa, tùy query plan và index. Trang 10.000 có thể chậm hơn đáng kể so với trang 1.

**Có thể bị trùng/bỏ sót khi dữ liệu thay đổi:**

~~~text
Trang 1, limit=3:       A B C
Có thêm X trước A:      X A B C D E
Trang 2, OFFSET 3:      C D E
~~~

C đã xuất hiện ở trang 1 nhưng lặp ở trang 2. Nếu có xóa, chuyển thứ tự hoặc cập nhật sort key, dữ liệu cũng có thể bị bỏ sót.

### ORDER BY ổn định và count query

Luôn có thứ tự xác định nếu nghiệp vụ cần traversal ổn định. Nếu nhiều bản ghi có cùng created_at, thêm id làm tie-breaker. Điều này giải quyết tình huống cùng timestamp nhưng **không tạo snapshot bất biến khi dữ liệu tiếp tục thay đổi**.

Một response Page có thể phải thực hiện COUNT(*) để trả tổng số trang. Với tập dữ liệu và filter phức tạp, COUNT có thể tốn tài nguyên. Khi UI chỉ cần biết còn trang sau không, Slice hoặc truy vấn limit+1 có thể phù hợp hơn.

## 5. Keyset pagination

Keyset pagination dùng khóa sắp xếp của bản ghi cuối đã trả để xác định vị trí trang sau, thay vì yêu cầu bỏ qua OFFSET lớn.

Giả sử kết quả sắp xếp theo created_at giảm dần và id giảm dần:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Trang đầu không có điều kiện sau last key. Trang sau dùng khóa bản ghi cuối đã thấy.

### Ưu điểm

- Thường hiệu quả với traversal sâu nếu index phù hợp.
- Phù hợp infinite scroll, feed, audit log và batch processing.
- Ít phụ thuộc vị trí tuyệt đối khi có bản ghi mới được thêm trước điểm đã đọc.
- Không cần nhảy qua hàng nghìn trang bằng OFFSET.

### Hạn chế

- Không thuận tiện để nhảy thẳng tới trang số 100.
- Cần các khóa sort ổn định, có thứ tự đầy đủ.
- Cập nhật sort key có thể khiến record di chuyển qua ranh giới và gây trùng/bỏ sót.
- Cần index theo filter và ORDER BY để có hiệu năng tốt.

Ví dụ index minh họa:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index thực tế phải chọn theo workload và query plan; không có công thức chung. Cần xem khả năng selectivity, điều kiện lọc, database engine và tỷ lệ cập nhật.

### Tie-breaker và thứ tự

Nếu chỉ sắp xếp theo timestamp mà hai record trùng giá trị, thứ tự của chúng có thể không xác định. Dùng khóa ID làm tie-breaker. Tuy nhiên UUID ngẫu nhiên không tự thể hiện thứ tự thời gian, nó chỉ giúp phân xử giữa các record cùng timestamp.

Nên chọn sort key ít thay đổi khi một consumer cần quét hàng loạt dữ liệu.

## 6. Cursor pagination

Cursor là token do server trả để client tiếp tục lấy trang. Nó thường chứa keyset position nhưng còn có thể gồm version, filter fingerprint, snapshot marker và expiry.

Ví dụ:

~~~http
GET /orders?status=PAID&limit=50
~~~

~~~json
{
  "items": [
    {"id":"ord-101","createdAt":"2026-11-01T08:00:00Z"},
    {"id":"ord-100","createdAt":"2026-11-01T07:58:00Z"}
  ],
  "nextCursor":"opaque-token",
  "hasMore":true
}
~~~

Client gửi lại token:

~~~http
GET /orders?cursor=opaque-token&limit=50
~~~

Một cursor ở mức logic có thể chứa:

~~~json
{
  "version":1,
  "lastCreatedAt":"2026-11-01T07:58:00Z",
  "lastId":"ord-100",
  "sort":"createdAt_desc,id_desc",
  "filterFingerprint":"hash-of-filters",
  "expiresAt":"2026-11-01T10:00:00Z"
}
~~~

### An toàn cho cursor

- Token nên opaque đối với client.
- Không đưa PII hoặc secrets vào token chỉ Base64; Base64 không phải mã hóa bảo mật.
- Có thể ký HMAC hoặc lưu token tham chiếu ở server để chống giả mạo.
- Ràng buộc tenant, filter, sort, version và thời hạn hợp lệ.
- Mỗi lần dùng cursor vẫn phải thực hiện authentication/authorization.
- Một cursor hết hạn phải trả lỗi rõ thay vì âm thầm dùng sai vị trí.

**Cursor và keyset không đồng nghĩa hoàn toàn:** cursor là hợp đồng API, keyset là một cách truy vấn ở database.

### Tránh bỏ sót dòng thừa

Để tính hasMore, server có thể query size+1 dòng. Nếu có nhiều hơn size dòng, trả size dòng đầu và tạo nextCursor từ **dòng cuối đã trả**, không phải dòng thứ size+1 dùng để kiểm tra. Nếu lấy dòng thừa làm checkpoint, client có thể bỏ sót chính dòng đó.

## 7. Tính nhất quán qua nhiều trang

Một API cần công bố kỳ vọng:

1. **Live list:** mỗi trang phản ánh dữ liệu tại thời điểm truy vấn; các trang có thể không cùng snapshot.
2. **Stable traversal:** giảm trùng/bỏ sót khi đi tuần tự bằng keyset và sort key ổn định.
3. **Snapshot chính xác:** cần toàn bộ dữ liệu ở một phiên bản/thời điểm xác định.

Keyset không tự đảm bảo snapshot nếu bản ghi bị update/delete hoặc sort key thay đổi. Snapshot chính xác có thể cần:
- Database snapshot/MVCC ở phạm vi phù hợp.
- Version/snapshot ID được lưu.
- High-water mark với giả định rõ về dữ liệu bất biến.
- Vật chất hóa tập export tại một thời điểm.
- Job xuất dữ liệu có kết quả cố định.

Không nên giữ database transaction xuyên hàng chục phút chỉ vì client đang cuộn trang: việc đó có thể làm tăng MVCC retention, lock hoặc giữ connection. Với báo cáo cần snapshot nghiêm ngặt, một export job riêng thường hợp lý hơn.

## 8. Ví dụ Spring Boot: API phân trang an toàn

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderQueryController {
    private static final int MAX_SIZE = 200;
    private final OrderQueryUseCase useCase;

    public OrderQueryController(OrderQueryUseCase useCase) {
        this.useCase = useCase;
    }

    @GetMapping
    public OrderListResponse list(
            @RequestParam(defaultValue = "25") int size,
            @RequestParam(required = false) String cursor,
            Authentication authentication) {

        if (size < 1 || size > MAX_SIZE) {
            throw new IllegalArgumentException(
                    "size must be between 1 and " + MAX_SIZE);
        }

        String tenantId = currentTenant(authentication);
        return useCase.list(tenantId, cursor, size);
    }
}
~~~

Đây là ví dụ kiến trúc: currentTenant, useCase và DTO cần triển khai; lỗi page size cần được exception handler ánh xạ thành 400 thay vì 500.

Use case thường thực hiện:
1. Xác minh tenant, quyền truy cập và tham số filter.
2. Giải mã/kiểm tra cursor.
3. Truy vấn tối đa size+1 dòng bằng thứ tự ổn định.
4. Trả tối đa size dòng.
5. Tạo nextCursor từ dòng cuối thực trả nếu còn dòng.
6. Trả hasMore và metadata theo contract.

Không cho client dùng tùy ý tên trường database trong Sort/Pageable vì có thể kích hoạt query rất nặng hoặc lộ cấu trúc nội bộ. Nên whitelist field sort và filter.

## 9. Streaming là gì?

Streaming gửi/nhận dữ liệu theo từng phần khi được tạo hoặc đọc, thay vì đợi toàn bộ payload hiện diện trong bộ nhớ.

~~~text
Không streaming:
DB → List(1 triệu rows) → JSON 200MB → Network → Client

Streaming end-to-end:
DB → Batch → Serialize → Write → Client processes
DB → Batch → Serialize → Write → Client processes
...
~~~

**Lợi ích tiềm năng:**
- Có thể giảm thời gian đến byte đầu tiên (time-to-first-byte).
- Giảm peak memory nếu nguồn dữ liệu và serializer thật sự xử lý incremental.
- Client có thể bắt đầu xử lý trước khi server hoàn tất.
- Phù hợp export, luồng cập nhật hoặc tệp lớn.

**Chi phí:**
- Giữ kết nối lâu.
- Cần xử lý client chậm và backpressure.
- Proxy có thể buffer khiến streaming không thực sự tới client sớm.
- Khi đã gửi headers, không thể đơn giản đổi HTTP 200 thành 500 nếu lỗi giữa luồng.
- Một DB cursor hoặc transaction có thể bị giữ quá lâu.
- Retry/resume khó hơn vì client có thể đã nhận dữ liệu một phần.

**Streaming không tự làm hệ thống ít tốn RAM nếu code đã tải toàn bộ dữ liệu vào List trước khi stream.**

## 10. Các hình thức streaming

| Hình thức | Hướng | Phù hợp |
| --- | --- | --- |
| HTTP response streaming | Server → client | CSV hoặc kết quả lớn |
| NDJSON | Server → client | Các object JSON liên tiếp theo dòng |
| Server-Sent Events | Server → client | Tiến độ job, trạng thái thay đổi |
| gRPC server streaming | Server → client | Nhiều protobuf messages |
| gRPC client streaming | Client → server | Gửi nhiều record có kiểm soát |
| gRPC bidirectional streaming | Hai chiều | Trao đổi message liên tục |
| Multipart/resumable upload | Client → server/storage | Tệp lớn cần upload theo chunk |
| Object storage download | Storage → client | Tệp lớn có thể tải trực tiếp |
| Export job bất đồng bộ | Worker tạo file, client tải sau | Báo cáo rất lớn, thời gian dài |

Đừng chọn giao thức chỉ vì nó hỗ trợ streaming. Cần biết dữ liệu hữu hạn hay liên tục, client có cần xử lý ngay không, có thể resume không, có deadline và quota nào.

## 11. NDJSON: mỗi dòng là một JSON object

Một response NDJSON:

~~~text
{"orderId":"o1","status":"PAID"}
{"orderId":"o2","status":"PENDING"}
{"orderId":"o3","status":"SHIPPED"}
~~~

Content-Type thường dùng là application/x-ndjson. Mỗi dòng JSON có thể được parse độc lập; client không cần chờ toàn bộ JSON array.

### Lợi ích

- Dễ xử lý từng record.
- Từng batch được serialize và truyền dần.
- Không yêu cầu giữ JSON array hoàn chỉnh trong bộ nhớ.
- Phù hợp một số công cụ ETL và export.

### Hợp đồng kết thúc

Nếu stream đứt sau 700/1.000 dòng, client không được coi dữ liệu đã đầy đủ. Có thể dùng:
- Checkpoint/cursor để tiếp tục.
- Export job có trạng thái SUCCEEDED và checksum.
- Manifest với expected row count khi có thể biết.
- End-of-stream marker có schema được thống nhất.
- Cơ chế thông báo lỗi và kết quả riêng.

HTTP 200 được trả khi headers bắt đầu không chứng minh body đã chuyển hoàn chỉnh. Không được gửi một error JSON tùy tiện giữa data records rồi mong mọi client nhận ra là lỗi; cần schema/event type rõ.

## 12. Spring MVC StreamingResponseBody

Một ví dụ dùng batch reader để không tải toàn bộ tập dữ liệu:

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderExportController {
    private final ObjectMapper mapper;
    private final OrderExportReader reader;

    public OrderExportController(
            ObjectMapper mapper,
            OrderExportReader reader) {
        this.mapper = mapper;
        this.reader = reader;
    }

    @GetMapping(value = "/export",
                produces = "application/x-ndjson")
    public ResponseEntity<StreamingResponseBody> export(
            Authentication authentication) {

        String tenantId = currentTenant(authentication);

        StreamingResponseBody body = output -> {
            String cursor = null;
            do {
                ExportBatch batch =
                        reader.nextBatch(tenantId, cursor, 200);

                for (OrderExportRow row : batch.rows()) {
                    byte[] json = mapper.writeValueAsBytes(row);
                    output.write(json);
                    output.write('\n');
                }

                output.flush();
                cursor = batch.nextCursor();
            } while (cursor != null);
        };

        return ResponseEntity.ok()
                .header("Cache-Control", "no-store")
                .body(body);
    }
}
~~~

ExportBatch, OrderExportRow và OrderExportReader là các abstraction cần triển khai. Ví dụ này minh họa cấu trúc; hệ thống thực cần authentication, timeout, quota, xử lý IOException, cancellation và trạng thái kết thúc.

Lưu ý:
- nextBatch phải query có giới hạn thật, không gọi findAll rồi chia nhỏ in-memory.
- Số row mỗi batch cần được đo để cân bằng query và serialization.
- Không flush từng byte nếu gây overhead quá lớn.
- Hạn chế số stream đồng thời và cấu hình executor cho Spring MVC async.
- Khi client ngắt, ngừng đọc tiếp và đóng tài nguyên.
- Đảm bảo bộ nhớ không tăng theo tổng số row.

### Bẫy JPA Stream và transaction

Nếu repository trả Stream<T> phụ thuộc một JPA session, session/transaction có thể kết thúc trước khi callback streaming xử lý. Ngược lại, giữ transaction mở suốt khi một client chậm tải 10 phút có thể làm cạn DB connection.

Một lựa chọn thực dụng là đọc từng batch trong transaction ngắn, đóng connection rồi gửi batch. Tuy nhiên cách đó không tự giữ snapshot toàn cục. Nếu cần snapshot nhất quán tuyệt đối, hãy thiết kế snapshot/export job thay vì chỉ ghép batch queries.

## 13. Server-Sent Events (SSE)

SSE truyền event một chiều từ server xuống client qua HTTP:

~~~http
GET /exports/export-471/events
Accept: text/event-stream
~~~

~~~text
id: 101
event: progress
data: {"percent":30}

id: 102
event: progress
data: {"percent":70}

id: 103
event: completed
data: {"downloadUrl":"/exports/export-471/download"}
~~~

Phù hợp cập nhật tiến độ, trạng thái tác vụ và một số event feed. SSE không phải giải pháp mặc định để truyền tệp nhị phân nhiều GB.

Khi client reconnect, nó có thể cung cấp Last-Event-ID. Nếu muốn replay event đã bỏ lỡ, server phải lưu event history/checkpoint tương ứng. Có event ID không tự tạo bảo đảm delivery chính xác một lần.

Cần heartbeat, kiểm soát số connection, authentication, timeout, cleanup và kiểm tra proxy buffering.

## 14. gRPC streaming

Trong gRPC có các kiểu RPC:

~~~proto
service OrderExport {
  rpc GetOrder(GetOrderRequest) returns (OrderReply);
  rpc StreamOrders(StreamRequest) returns (stream OrderReply);
  rpc UploadOrders(stream UploadItem) returns (UploadSummary);
  rpc Synchronize(stream SyncRequest) returns (stream SyncReply);
}
~~~

- Unary: một request, một response.
- Server streaming: một request, nhiều response messages.
- Client streaming: nhiều request messages, một response cuối.
- Bidirectional: cả hai phía gửi messages.

gRPC thường sử dụng HTTP/2 flow control, nhưng ứng dụng vẫn phải:
- Giới hạn message size, tổng bytes và concurrency.
- Tránh buffer vô hạn trong consumer.
- Truyền deadline và xử lý cancellation.
- Quản lý trạng thái partial stream và retry.
- Bảo vệ idempotency nếu stream chứa command có side effect.

Tính năng transport flow control không bảo đảm một database query phía sau tự dừng khi client chậm. Tương tự, chia file thành nhiều message không tự làm toàn bộ upload thành một transaction nguyên tử.

## 15. Backpressure và slow consumers

Nếu server tạo 40.000 rows/giây nhưng client chỉ nhận 500 rows/giây, buffer sẽ tăng nếu producer không được điều tiết:

~~~text
Producer DB → Buffer → Network → Slow client
  40k rows/s                  500 rows/s
                ↑
      Phải giới hạn hoặc chặn producer
~~~

**Backpressure** là cơ chế điều chỉnh lượng dữ liệu tạo ra theo khả năng downstream tiêu thụ.

Các nguyên tắc:
- Đọc batch mới khi batch trước đã được xử lý hoặc còn đủ buffer.
- Có queue capacity/buffer cap tường minh.
- Với reactive pipeline, đảm bảo data source thực sự đáp ứng demand.
- Khi slow consumer vượt deadline, dừng stream và giải phóng tài nguyên.
- Có rate limit và concurrency cap cho export.
- Truyền cancellation để ngừng query/producer khi khả thi.

Ví dụ sau **không chứng minh end-to-end streaming**:

~~~java
Flux<OrderDto> rows =
        Flux.fromIterable(repository.findAll());
~~~

Nếu findAll đã load mọi record trong RAM thì Flux chỉ phát một danh sách đã tồn tại. Tương tự, một toán tử collectList không giới hạn có thể làm pipeline tích tụ toàn bộ dữ liệu.

## 16. Proxy buffering, compression và timeout

Một service có thể flush mỗi batch nhưng browser vẫn không thấy dữ liệu cho đến khi response kết thúc. Nguyên nhân có thể là:
- Proxy/gateway đang buffer response.
- Compression giữ dữ liệu trước khi phát chunk.
- Client library chỉ đọc body sau khi nhận đầy đủ.
- Content negotiation hoặc middleware biến stream thành buffer.
- Idle timeout ngắt kết nối dài.
- Nền tảng quan sát log giữ toàn bộ response body.

Cần thử nghiệm **đường đi thực tế qua gateway/ingress/CDN**, không chỉ localhost. Header riêng của từng proxy phải được kiểm chứng chứ không suy đoán luôn có hiệu lực.

Với nén gzip/Brotli, tiết kiệm băng thông có thể đánh đổi CPU và độ trễ phát chunk. Cần đo Time-To-First-Byte (TTFB), total duration, bytes/s và CPU.

## 17. Upload dữ liệu lớn

Streaming áp dụng cả chiều client → server. Với file lớn:
- Không nhận toàn bộ file vào byte[].
- Đọc/ghi từng chunk có giới hạn.
- Giới hạn bytes thực đọc, số multipart parts, kích thước part và tổng thời gian.
- Kiểm tra content type thực, checksum và file metadata.
- Có temporary storage và cleanup khi upload bị ngắt.
- Chỉ công bố object sau khi finalize/validate thành công.
- Dùng quota và giới hạn số upload đồng thời.

Ví dụ cấu hình Spring Boot cho multipart trong một môi trường:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 25MB
~~~

Chỉ là số minh họa; còn phải phối hợp với gateway, ingress và hạ tầng. Nếu endpoint là raw streaming body thay vì multipart, cấu hình multipart không tự giới hạn mọi bytes.

Với tệp rất lớn, cân nhắc direct upload vào object storage qua signed URL có thời hạn, resumable upload hoặc multipart upload. Server nghiệp vụ cấp upload intent, kiểm soát quyền/quota, xác minh checksum và chỉ mark COMPLETE khi object đã được finalize.

## 18. Download file lớn và HTTP Range

File export lớn có thể phù hợp với object storage thay vì relay liên tục qua một service:

~~~text
Client ── POST /exports ──> Export service
                                |
                           enqueue job
                                |
                                v
                      Worker tạo CSV/Parquet
                                |
                                v
                         Object storage
                                |
Client <── status + download link ── Export service
                                |
Client ───────── file download ─────> Storage
~~~

Nếu storage và client hỗ trợ, HTTP byte Range cho phép tải tiếp một phần file. Response có thể dùng 206 Partial Content và Content-Range. Một yêu cầu Range khác với một page của danh sách: Range làm việc trên bytes của một representation, pagination làm việc trên tập record theo business order.

Signed URL cần thời gian sống phù hợp, quyền truy cập và kiểm soát dữ liệu nhạy cảm. Nên lưu checksum, kích thước và metadata để client kiểm tra file hoàn chỉnh.

## 19. Khi nào nên dùng export job bất đồng bộ?

Nếu truy vấn mất nhiều phút hoặc xuất hàng triệu rows, việc giữ HTTP request mở có thể gây khó khăn cho timeout, restart và tài nguyên.

API có thể:

~~~http
POST /exports
Content-Type: application/json

{"type":"orders","from":"2026-10-01","to":"2026-10-31"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /exports/export-471

{"exportId":"export-471","status":"PENDING"}
~~~

Client truy vấn:

~~~http
GET /exports/export-471
~~~

Khi SUCCEEDED, server trả metadata và URL tải file có thời hạn.

Ưu điểm:
- Không giữ request đang mở để chờ báo cáo hoàn tất.
- Có thể áp concurrency quota và ưu tiên xử lý.
- Lưu tiến độ, retry theo checkpoint và recover sau restart.
- Tạo file có checksum và công bố khi đã hoàn chỉnh.
- Dễ tách snapshot/reporting load khỏi database giao dịch.

POST tạo export cũng có side effect. Nếu timeout khi tạo job, cần idempotency key hoặc stable export request ID để tránh tạo job trùng.

## 20. Chọn phương án theo nhu cầu

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| UI quản lý hiển thị 25 dòng | Offset có giới hạn hoặc cursor pagination |
| Infinite scroll rất dài | Keyset/cursor |
| Muốn nhảy tới trang số | Offset/page-number, kèm giới hạn |
| Query cần duyệt đủ dữ liệu theo lô | Keyset và checkpoint |
| Export vài nghìn dòng, xử lý dần | NDJSON/CSV streaming |
| Báo cáo hàng triệu dòng hoặc kéo dài | Async export job và object storage |
| Tiến độ job cập nhật liên tục | SSE |
| Nhiều messages protobuf | gRPC streaming |
| Upload nhiều GB | Resumable/direct object storage upload |
| Báo cáo tài chính cần snapshot chính xác | Snapshot/export job có version |

Một số sản phẩm kết hợp nhiều lựa chọn: list page dùng cursor, cập nhật tiến độ dùng SSE, và download sau khi export job hoàn tất. Không có yêu cầu phải chọn một kỹ thuật duy nhất cho mọi endpoint.

## 21. Timeout, retry và resume

### Pagination

Mỗi trang là một request độc lập. Khi timeout, client có thể retry cùng cursor nếu contract cho phép. Nhưng dữ liệu live có thể thay đổi nên kết quả trang lặp không luôn byte-identical. Với batch processing quan trọng, lưu checkpoint ở item cuối đã xử lý thành công; consumer phải idempotent nếu một trang được xử lý lại.

### Streaming

Khi network ngắt sau 700 trên 1.000 rows, một HTTP 200 ban đầu không chứng minh đã nhận toàn bộ. Client phải có cơ chế:
- Kiểm tra completeness bằng manifest, checksum hoặc expected row count.
- Resume theo checkpoint/cursor nếu được hỗ trợ.
- Hoặc tải lại từ đầu, xử lý duplicate phù hợp.
- Với file export, chỉ công bố link khi job đã thành công.

### Deadline và cancellation

Phân biệt connect timeout, idle timeout, write timeout, total duration và business deadline. Client đóng kết nối cần kích hoạt cleanup và ngừng đọc database khi có thể. Nếu export đã được tạo thành job, client ngắt SSE status không nhất thiết hủy job.

### Retry amplification

Gateway, service và client cùng retry nhiều lần có thể tạo tải theo cấp số nhân. Cần một retry owner rõ, giới hạn attempts, backoff/jitter, circuit breaker phù hợp và metrics đo request amplification.

## 22. Bảo mật và nhiều tenant

- TenantId/owner filter phải lấy từ identity đã xác thực, không tin cursor do client sửa.
- Cần authorization trên từng trang/stream/export.
- Whitelist sort và filter, tránh SQL injection hoặc query cost abuse.
- Không expose domain entity hoặc trường nhạy cảm chỉ vì response là export.
- Signed URL phải giới hạn quyền, phạm vi, thời gian và được bảo vệ khỏi rò rỉ.
- Đặt quota theo user/tenant cho số stream, rows, bytes và jobs.
- Có audit đối với export dữ liệu cá nhân hoặc tài chính.
- Base64 của cursor không có tác dụng bảo mật; token ký cũng không thay authentication.

Một endpoint phân trang không giới hạn có thể trở thành cơ chế thu thập dữ liệu hàng loạt, nên ngoài page size còn cần quota tổng thể.

## 23. Quan sát và đo lường

| Chỉ số | Câu hỏi |
| --- | --- |
| Request/response bytes | Payload thực tế lớn tới đâu? |
| Page size, rows scanned | Database làm bao nhiêu việc để trả một trang? |
| Deep offset latency | Trang sâu có chậm dần không? |
| p50/p95/p99 latency | Có gây đuôi độ trễ cao không? |
| Time-to-first-byte | Streaming có gửi dữ liệu sớm thật không? |
| Stream duration | Connection giữ bao lâu? |
| Active stream count | Có quá nhiều stream đồng thời không? |
| Heap và buffer usage | Có tích tụ dữ liệu khi client chậm không? |
| DB connection hold time | Stream có chiếm kết nối DB quá lâu? |
| Bytes/s và records/s | Tốc độ truyền và serialize? |
| Client cancellations/partial responses | Bao nhiêu stream bị ngắt? |
| HTTP 413/429/5xx/timeout | Chính sách bảo vệ hoạt động ra sao? |
| Export backlog/job age | Có report đang chờ quá lâu? |

Nên tách dashboard endpoint phân trang thông thường khỏi endpoint export lớn. Trộn số liệu GET 25 rows và export 100 MB có thể tạo ra p95 khó hiểu.

## 24. Kiểm thử có chủ đích

**Giới hạn:**
1. Body đúng ngưỡng được chấp nhận, body vượt ngưỡng bị từ chối.
2. Request không có Content-Length vẫn bị giới hạn theo bytes thực đọc.
3. Body gzip nhỏ nhưng giải nén rất lớn không gây cạn RAM.
4. JSON quá sâu, quá nhiều phần tử hoặc query quá phức tạp bị xử lý an toàn.
5. Gateway và ứng dụng phản hồi nhất quán, không có tầng nào crash trước khi chặn.

**Pagination:**
1. Max page size được thực thi.
2. ORDER BY có tie-breaker khi timestamp trùng.
3. Cursor dùng dòng cuối đã trả, không bỏ sót dòng size+1.
4. Cursor sai phiên bản/hết hạn/sai tenant bị từ chối.
5. Filter/sort thay đổi không dùng lại cursor cũ sai semantics.
6. Dữ liệu được thêm/xóa/sửa giữa trang có kết quả đúng contract.
7. Trang sâu và count query được kiểm tra query plan và latency.

**Streaming:**
1. Không tải toàn bộ dữ liệu trước khi stream.
2. TTFB thực sự cải thiện qua proxy/gateway.
3. Client đọc chậm không làm buffer tăng vô hạn.
4. Client disconnect giúp ngừng query/producer và giải phóng resource.
5. Lỗi giữa stream không bị hiểu là hoàn tất.
6. SSE/gRPC reconnect hoặc resume theo contract.
7. Concurrency cap bảo vệ thread pool và DB connections.
8. Export hoàn chỉnh có metadata, checksum hoặc trạng thái job rõ.

Sử dụng dữ liệu kích thước đại diện, network throttling, slow client và fault injection; chỉ unit test serialize một array nhỏ không chứng minh được tài nguyên dưới tải production.

## 25. Những hiểu lầm phổ biến

**“Streaming chắc chắn giảm tổng thời gian.”** Không hẳn. Streaming có thể giảm TTFB và peak memory, nhưng tổng thời gian vẫn phụ thuộc query, serialize, network và consumer.

**“Dùng Flux là không thể hết RAM.”** Không đúng nếu repository.findAll() đã materialize toàn bộ dữ liệu hoặc buffer không giới hạn.

**“Keyset đảm bảo không bao giờ duplicate/missing.”** Không đúng nếu sort key đổi hoặc yêu cầu snapshot chính xác.

**“Cursor chỉ là offset mã hóa Base64.”** Có thể có API như thế nhưng không tận dụng được keyset và không thể hiện đầy đủ semantics nếu thiếu contract.

**“Tăng timeout giải quyết export lớn.”** Có thể giữ connection và DB resource lâu hơn; export job có thể hợp lý hơn.

**“Content-Length đã chặn upload quá lớn.”** Không đủ vì streaming body có thể không có header đó và nén có thể phình dữ liệu.

**“HTTP 200 chứng minh stream đã hoàn tất.”** Nếu stream bị ngắt giữa chừng, client có thể chỉ có một phần body.

**“SSE tự bảo đảm event không mất khi reconnect.”** Chỉ khi server lưu/replay theo semantics có chứng minh.

**“Range là pagination.”** Range chọn byte trong một representation; pagination chọn các item trong tập dữ liệu.

## 26. Bài tập tình huống

**Bài 1.** GET /orders đang trả một triệu bản ghi nhưng người dùng chỉ xem 50 dòng. Nên thiết kế lại thế nào? Gợi ý: giới hạn page size, phân trang, query trường cần thiết và index.

**Bài 2.** Trang đầu trả A,B,C; có thêm X trước A; trang hai OFFSET 3 trả C,D,E. Vì sao trùng và lựa chọn nào giúp giảm vấn đề? Gợi ý: keyset/cursor với sort key ổn định, snapshot khi cần tính nhất quán chính xác.

**Bài 3.** Cursor được Base64 và client sửa tenantId trong token. Hệ thống cần bảo vệ gì? Gợi ý: integrity, expiry, filter binding và authorization cho mọi trang.

**Bài 4.** Controller trả StreamingResponseBody nhưng gọi repository.findAll trước khi ghi. Vì sao vẫn OOM? Gợi ý: nguồn dữ liệu đã được materialize; dùng batch reading hoặc cursor thật.

**Bài 5.** Client nhận 700/1.000 dòng NDJSON rồi mất mạng. Có thể coi thành công không? Gợi ý: không, phải có completeness contract hoặc checkpoint/resume.

**Bài 6.** Server flush từng batch nhưng browser chỉ thấy dữ liệu khi kết thúc. Cần kiểm tra gì? Gợi ý: proxy buffering, compression, client library, timeout và gateway.

**Bài 7.** File upload nhiều GB, gateway giới hạn 20 MB và service nhận toàn bộ vào byte[]. Có nên chỉ tăng heap? Gợi ý: resumable/direct upload, chunk size, quota, checksum và finalize.

**Bài 8.** Báo cáo tài chính yêu cầu snapshot 08:00 chính xác trong khi dữ liệu tiếp tục thay đổi. Keyset có đủ không? Gợi ý: cần snapshot/version hoặc export job có kết quả cố định.

## 27. Checklist thiết kế

- [ ] Có max request bytes, response bytes và max page size rõ?
- [ ] Có giới hạn bytes thực đọc và decompressed bytes?
- [ ] Filter/sort được whitelist, query complexity có giới hạn?
- [ ] ORDER BY xác định và có tie-breaker?
- [ ] Đã chọn offset, keyset hoặc cursor phù hợp UX?
- [ ] Cursor có version, filter, tenant, expiry và integrity?
- [ ] Có contract về consistency khi dữ liệu thay đổi giữa các trang?
- [ ] Đã đo COUNT và deep-offset query cost?
- [ ] Streaming thật sự incremental từ data source tới network?
- [ ] Có bounded buffer, backpressure và slow-consumer policy?
- [ ] Có deadline, timeout, cancellation và cleanup?
- [ ] Đã kiểm tra proxy buffering và compression trên đường thực?
- [ ] Client biết khi nào stream hoàn tất hoặc bị cắt?
- [ ] Có resume/checkpoint hoặc async export job khi cần?
- [ ] Upload/download có quota, authorization, checksum?
- [ ] Đã đo TTFB, p95/p99, stream duration, memory và DB connection hold time?
- [ ] Đã test client chậm, network reset, nhiều tenant và quá tải?

## 28. Kết luận

**Giới hạn kích thước** bảo vệ từng tầng và từng loại tài nguyên. **Pagination** chia tập kết quả thành những request có quy mô kiểm soát được, với offset cho trang số, keyset/cursor cho traversal sâu và các contract rõ về thứ tự và nhất quán. **Streaming** giúp xử lý dữ liệu dần, giảm nhu cầu giữ toàn bộ payload trong bộ nhớ và có thể trả dữ liệu sớm, nhưng đòi hỏi backpressure, cancellation, completeness và cơ chế phục hồi khi lỗi mạng.

Danh sách UI thường phù hợp pagination; feed dài phù hợp keyset/cursor; cập nhật tiến độ phù hợp SSE; trao đổi message tuần tự phù hợp gRPC streaming; export cực lớn hoặc snapshot chính xác thường phù hợp async job + object storage. Chọn theo **ngữ nghĩa dữ liệu, ngân sách tài nguyên, độ tin cậy và số liệu đo được**, không chỉ theo độ lớn một response.
