# Đánh đổi structured logging trong Java: lợi ích, chi phí và cách lựa chọn

**Structured logging** (*ghi log có cấu trúc*) là cách biểu diễn một sự kiện log bằng **các trường dữ liệu có tên và kiểu rõ ràng**, thay vì chỉ tạo một câu văn tự do. JSON Lines là định dạng thường gặp: mỗi log event là một JSON object độc lập trên một dòng vật lý.

Ví dụ cùng một sự kiện thanh toán thất bại:

~~~text
WARN checkout_failed requestId=req-17 durationMs=42 attempt=2 outcome=RETRYABLE
~~~

~~~json
{"event":"checkout_failed","level":"WARN","requestId":"req-17","durationMs":42,"attempt":2,"outcome":"RETRYABLE"}
~~~

Dạng JSON cho phép công cụ phân tích biết `durationMs` và `attempt` là số, lọc theo `event` hoặc `outcome` mà không cần tách một câu text bằng regex. Đổi lại, nó đòi hỏi **thiết kế schema, serialization, quản lý dữ liệu nhạy cảm và vận hành pipeline** nghiêm túc hơn.

**Luận điểm của bài:** structured logging không phải “luôn tốt hơn text logging”. Lợi ích lớn nhất xuất hiện khi dữ liệu cần **truy vấn, liên kết, tổng hợp và xử lý tự động**; chi phí tăng khi sự kiện quá nhiều, field không ổn định, giá trị có cardinality cao, hoặc đội ngũ thiếu quy ước schema và retention.

## 1. Đánh đổi nằm ở đâu trong kiến trúc logging?

Luồng tổng quát của một ứng dụng Java:

~~~text
Business event
     |
     v
Logger / facade (SLF4J, JUL, Log4j 2 API)
     |
     v
Gắn ngữ cảnh: level, event, traceId, durationMs...
     |
     v
Backend (Logback, Log4j 2, JUL...)
     |
     v
Encoder/Layout/Formatter
     |                  |
     | text pattern     | structured JSON
     v                  v
Console/file/stream/collector
     |
     v
Parse -> index -> lưu trữ -> truy vấn -> cảnh báo
~~~

Structured logging có thể thay đổi **nhiều mắt xích**, không chỉ formatter. Nếu ứng dụng chỉ tạo một chuỗi `"requestId=... durationMs=..."`, rồi JSON encoder đặt toàn bộ chuỗi ấy vào một field `message`, hệ thống sẽ có một JSON object, nhưng các thành phần trong message **chưa chắc trở thành những field riêng có kiểu dữ liệu**.

Ngược lại, để giữ `durationMs` là số, ứng dụng cần truyền field số hoặc metadata tương ứng, và encoder/collector phải **giữ đúng kiểu** trên đường vận chuyển.

Ba câu hỏi cần phân biệt:

1. **Phát sự kiện nào?** Quyết định của logger, level, sampling và nghiệp vụ.
2. **Mô tả sự kiện bằng field nào?** Quyết định thiết kế structured event và context.
3. **Lưu, lập chỉ mục và truy vấn thế nào?** Quyết định của backend, encoder, log collector và storage.

Việc thêm JSON encoder chỉ giải quyết một phần câu hỏi thứ hai; không tự đưa ra chính sách bảo mật, chi phí hoặc truy vấn.

## 2. Lợi ích: truy vấn theo trường thay vì phân tích text tự do

Trong text logging không có quy ước, cùng một ý có thể xuất hiện dưới nhiều cách viết:

~~~text
Order ord-7 failed after 42ms
payment failed: order=ord-7, elapsed=42
WARN request ord-7, retry in 42 milliseconds
~~~

Muốn đếm các lỗi của một loại sự kiện, hệ thống phải nhận diện nhiều mẫu chuỗi và dựa vào biểu thức chính quy. Khi thay đổi wording, bộ tìm kiếm/alert có thể sai.

Với structured logging, có thể thống nhất:

~~~json
{
  "event": "checkout_failed",
  "level": "WARN",
  "service": "payment-service",
  "orderId": "ord-7",
  "durationMs": 42,
  "outcome": "RETRYABLE"
}
~~~

Một câu truy vấn *mang tính khái niệm, không phải cú pháp của công cụ cụ thể*:

~~~text
event == "checkout_failed"
AND outcome == "RETRYABLE"
AND durationMs > 40
~~~

Những lợi ích rõ nhất:

- **Lọc chính xác hơn:** `event` và `outcome` có giá trị ổn định, không lệ thuộc cách đặt câu.
- **Truy vấn số đúng kiểu:** `durationMs > 100` có nghĩa số học, không phải so sánh chuỗi từ điển.
- **Dễ tạo dashboard/alert:** thống kê lỗi theo service, action hoặc reason code mà không phải parse message.
- **Liên kết giữa service:** `traceId`, `spanId` hoặc `requestId` có thể giúp truy vết một yêu cầu, nếu mọi nơi phát log nhất quán.
- **Dễ xử lý tự động:** hệ thống có thể nhận diện field, đưa vào data pipeline hoặc đối chiếu với metrics/traces.

**Đánh đổi:** các giá trị này chỉ có ích khi schema ổn định, dữ liệu được thu thập đúng và công cụ tìm kiếm biết kiểu dữ liệu. Nếu backend chỉ lưu một blob JSON không được parse, việc truy vấn field có thể vẫn chậm hoặc yêu cầu xử lý sau.

## 3. Bảng tổng quan các lợi ích và chi phí

| Khía cạnh | Structured logging đem lại | Đánh đổi cần chấp nhận |
| --- | --- | --- |
| Truy vấn | Lọc/tổng hợp theo field, ít regex | Phải quy ước field name và type |
| Định dạng | Máy xử lý được JSON/field map | Serialization, escaping, encoder và parse |
| Độ dài bản ghi | Có metadata, context hữu ích | Tên field lặp lại khiến payload thô có thể lớn hơn |
| CPU và cấp phát | Có thể giảm regex parsing ở downstream | Tạo map/object, serialize JSON, xử lý context |
| Lưu trữ | Dữ liệu truy vấn được, compression có lợi khi lặp field | Index, retention và query có thể tốn chi phí đáng kể |
| Cardinality | Có requestId/traceId để truy vết chính xác | Nhiều giá trị duy nhất gây tốn index/aggregation nếu cấu hình thiếu kiểm soát |
| Bảo mật | Có thể chọn/ẩn từng field theo policy | PII, token và secrets trở nên dễ truy vấn/sao chép |
| Schema | Có cấu trúc ổn định để tích hợp hệ thống | Cần versioning, tương thích và kiểm tra kiểu |
| Vận hành | Collector và alert mạnh hơn | Cần giám sát lỗi encoder, queue, ingestion và mapping |
| Quan sát phân tán | Dễ gắn correlation context | Context không tự truyền qua thread/service |
| Khả năng đọc tay | Các trường rõ ràng, máy parse được | JSON dài hơn và khó đọc nhanh trên terminal |
| Khả năng đổi backend | Có thể chuẩn hóa một contract log chung | Encoder/field naming/MDC khác nhau giữa các stack |

Bảng này không nói rằng JSON luôn chậm hơn hay luôn lớn hơn trong mọi hệ thống. **Chi phí end-to-end** phụ thuộc kích thước sự kiện, định dạng text cũ, tốc độ tạo log, thuật toán nén, công cụ indexing và cách dữ liệu được truy vấn.

## 4. Chi phí dung lượng: JSON có thể dài hơn text

Giả sử cùng một event được phát như sau:

~~~text
INFO order_accepted ord-7 42ms
~~~

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"orders","event":"order_accepted","orderId":"ord-7","durationMs":42}
~~~

Bản JSON có nhiều **tên trường lặp lại ở mọi event**. Khi log volume lớn, overhead đó có thể đáng kể; nhưng nó cũng chứa nhiều metadata hơn ví dụ text, nên để so sánh công bằng phải bảo đảm **cùng thông tin được lưu**.

### Mô hình tính dung lượng (giả định)

Giả sử hệ thống phát **100 event/giây**, trung bình sau encoding:

- Một event text dài **200 byte**.
- Một event structured dài **400 byte**.

Số event mỗi ngày là `100 × 86.400 = 8.640.000`.

| Đại lượng | Text | Structured |
| --- | ---: | ---: |
| Byte/event giả định | 200 | 400 |
| Event/ngày | 8.640.000 | 8.640.000 |
| Tổng byte/ngày | 1.728.000.000 | 3.456.000.000 |
| GB thập phân/ngày | 1,728 GB | 3,456 GB |
| Chênh lệch | — | 1,728 GB/ngày |

**Đây chỉ là phép tính minh họa, không phải benchmark.** Kích thước thực phải đo bằng bytes **sau encoder** trên tập event đại diện. Nếu backend nén dữ liệu, các key JSON lặp lại thường có thể nén tốt. Ngược lại, chi phí **index**, bản sao dữ liệu, retention và truy vấn có thể lớn hơn phần tăng payload thô.

Không suy ra chi phí tiền chỉ từ byte event: mỗi hệ thống logging tính phí và lưu trữ khác nhau. Phải tính cả ingestion, replicated storage, searchable retention, archive và egress nếu có.

### Giảm chi phí mà vẫn giữ cấu trúc

1. Chỉ ghi các field **có giá trị tra cứu hoặc chẩn đoán thực tế**.
2. Không đính kèm toàn bộ DTO, request/response body hoặc stack trace ở mỗi event INFO.
3. Chọn log level/sampling theo nhu cầu, giảm sự kiện không cần thiết trước khi serialization.
4. Dùng chính sách retention, compression và indexing phù hợp.
5. Cân nhắc giữ một vài trường quan trọng để search, các trường khác chỉ lưu mà không lập index nếu nền tảng cho phép.
6. Đo **payload + index + chi phí query**, không chỉ độ dài JSON.

## 5. Chi phí CPU, cấp phát và đường đi hot path

Một event có cấu trúc thường trải qua:

~~~text
Xác định event / field
        |
        v
Tạo Map / object / metadata
        |
        v
Thay tham số, chuẩn hóa kiểu
        |
        v
JSON serialization + escaping
        |
        v
Ghi/queue/batch/network
~~~

Những bước đó có thể tốn CPU và cấp phát bộ nhớ. Trái lại, log text cũng cần interpolation, pattern formatting, timestamp, stack trace và I/O; **không thể kết luận structured luôn chậm hơn text** nếu chưa đo cùng dữ kiện và cùng backend.

Đặc biệt, một lệnh như:

~~~java
// Minh họa trong phương thức có logger kiểu SLF4J.
logger.debug("payload={}", expensiveSerialize(request));
~~~

vẫn gọi `expensiveSerialize(request)` **trước khi** thư viện kiểm tra mức DEBUG (do cách đánh giá tham số của Java). Nếu payload nặng, cần bảo vệ:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("payload={}", expensiveSerialize(request));
}
~~~

Đây cũng chỉ là **hai đoạn minh họa**, không phải class độc lập. Nhu cầu structured logging không làm thay đổi nguyên tắc lazy evaluation này.

**Cẩn trọng với một điểm khác:** nếu backend đã bỏ DEBUG tại logger nhưng mã nguồn tạo một object/Map lớn trước câu lệnh log, overhead đó vẫn phát sinh. Trong hot path, nên chuẩn bị field tối thiểu ở đường thường, và chỉ tạo dữ liệu chẩn đoán nặng khi level/sampling cho phép.

### Chi phí của stack trace và caller location

Exception stack trace, source file, line number hoặc method name có thể tốn chi phí hơn vài field JSON. Không tự bật caller location cho mọi event nếu không cần. Với async logging, việc xác định caller/context có thể phải được thực hiện **trước khi** chuyển event sang thread khác.

Đo bằng benchmark/profile trên ứng dụng thật, gồm throughput, allocation rate, tail latency (p95/p99), GC, CPU và tải collector. Đừng chỉ chạy một vòng lặp `ObjectMapper.writeValueAsString` rồi kết luận toàn bộ logging stack chậm nhanh thế nào.

## 6. Cardinality: field rất hữu ích nhưng có thể đắt

**Cardinality** của một field là số lượng giá trị khác nhau mà nó nhận trong một tập dữ liệu.

| Field | Cardinality thường gặp | Cách dùng |
| --- | --- | --- |
| `level` | Thấp (INFO, WARN, ERROR...) | Dễ nhóm, lọc, thống kê |
| `service` | Thấp/trung bình | Dashboard theo service |
| `event` | Thấp/trung bình nếu quản trị tốt | Phân tích loại sự kiện |
| `outcome` | Thấp | Tỷ lệ thành công/thất bại |
| `region` | Thấp/trung bình | Tình trạng theo vùng |
| `requestId` | Rất cao, thường gần duy nhất | Tìm đúng một request |
| `traceId` | Rất cao | Liên hệ log với distributed trace |
| `userId` hoặc `orderId` | Có thể rất cao | Điều tra mục tiêu khi được phép |
| `rawUrl` gồm query parameters | Có thể cực cao | Thường nên chuẩn hóa route template |

**Field cardinality cao không phải luôn xấu.** `requestId` và `traceId` có thể rất cần thiết cho điều tra từng request. Vấn đề xuất hiện khi **mọi giá trị đều được tạo thành dimension/index/aggregation** đắt đỏ hoặc chuyển thành **metric label** với số chuỗi thời gian bùng nổ.

Ví dụ nên tránh trong metrics:

~~~text
http_requests_total{requestId="req-17"} 1
http_requests_total{requestId="req-18"} 1
...
~~~

Một metric có `requestId` khác nhau mỗi lần có thể sinh rất nhiều time series. **Log field và metric label là hai công cụ khác nhau.** Có thể giữ requestId trong log để truy vết nhưng không đưa requestId thành label metric; việc index log field nào vẫn cần quyết định theo nhu cầu tìm kiếm và chi phí thực tế.

### Không tạo tên field động

Tránh:

~~~json
{"request_req-17": true, "request_req-18": true}
~~~

Thay bằng:

~~~json
{"requestId":"req-17"}
~~~

Tên field động làm schema thay đổi, tạo nhiều mapping khác nhau và phá vỡ truy vấn. Một field cố định với giá trị thay đổi có thể vẫn mang cardinality cao, nhưng nó giữ schema và khả năng xử lý nhất quán.

Với endpoint HTTP, ưu tiên `route="/orders/{id}"` khi cần nhóm theo endpoint, thay vì dùng `path="/orders/123456"` làm dimension thống kê không giới hạn; route template cũng cần được lấy từ nguồn tin cậy để tránh mất thông tin ngữ cảnh quan trọng.

## 7. Schema governance: khi nào thêm field là một thay đổi lớn?

Với log text, đổi câu “Order accepted” thành “Payment processed” có thể chỉ ảnh hưởng cách đọc (nhưng có thể phá regex). Với structured logging, đổi:

~~~json
{"durationMs":42}
~~~

thành:

~~~json
{"durationMs":"42"}
~~~

có thể làm query/aggregation sai vì **kiểu của cùng field đổi từ number sang string**. Một số nền tảng áp dụng type mapping tự động và có thể từ chối hoặc xử lý khác các sự kiện không đồng nhất.

### Quy ước schema tối thiểu

Nên thống nhất những trường cốt lõi:

| Field | Kiểu nên dùng | Mục đích |
| --- | --- | --- |
| `timestamp` | Timestamp chuẩn có timezone (thường UTC) | Thời điểm sự kiện |
| `level` | Giá trị chuẩn hóa | INFO/WARN/ERROR... |
| `service` | String từ danh sách tên được quản lý | Nguồn sự kiện |
| `event` | String ổn định | Loại sự kiện |
| `message` | String | Câu giải thích cho con người |
| `traceId` / `requestId` | String, có thể vắng | Liên kết yêu cầu |
| `durationMs` | Number | Độ trễ/chi phí thời gian |
| `outcome` | Enum/string ổn định | SUCCESS/FAILED/RETRYABLE... |
| `errorType` | String ổn định khi có lỗi | Loại ngoại lệ |
| `schemaVersion` | String hoặc integer theo hợp đồng | Nhận diện format khi cần versioning |

Tên/kiểu chính xác có thể tuân theo chuẩn chung mà tổ chức chọn; ví dụ OpenTelemetry Logs có mô hình attribute riêng. **Không cần phát minh lại một schema mới cho từng service**, nhưng cũng không phải mọi hệ thống đều phải dùng cùng một bộ field trong mọi trường hợp.

### Những thay đổi cần có kế hoạch

- **Rename field:** `elapsedMs` → `durationMs` có thể phá dashboard cũ.
- **Thay kiểu:** `durationMs` number → string làm mất truy vấn số học.
- **Đổi ý nghĩa:** `latencyMs` từng đo thời gian HTTP nhưng nay đo riêng thời gian DB.
- **Đổi đơn vị:** milli giây → giây mà không đổi tên field tạo lỗi âm thầm.
- **Null và absent:** field không có, field bằng `null`, field bằng chuỗi rỗng không nhất thiết đồng nghĩa.
- **Nested object:** `user.id` và `userId` có thể thành hai schema khác nhau tùy collector.
- **Field collision:** backend tự phát `level` nhưng application cũng ghi `level`; phải có quy tắc ưu tiên/namespace rõ.

Chiến lược tốt là review thay đổi schema như một **hợp đồng dữ liệu**, viết test cho field quan trọng và triển khai tương thích với truy vấn đang hoạt động. Khi cần thay đổi lớn, có thể xuất hai field cũ/mới trong một giai đoạn chuyển tiếp hoặc cập nhật bộ thu thập và dashboard có phối hợp.

## 8. Quy ước event quan trọng hơn việc tạo JSON thật dài

Một bản ghi JSON có 40 field nhưng `event` và `message` thay đổi tùy ý có thể khó vận hành hơn log text 5 field được quản trị tốt.

Ví dụ **đặt tên event ổn định**:

~~~json
{"event":"payment_retry","outcome":"SCHEDULED","attempt":2,"reason":"TIMEOUT"}
~~~

Không nên biến event name thành câu giải thích động:

~~~json
{"event":"payment retry for order ord-7 at 10:15:30 with timeout"}
~~~

Sự kiện phía sau chứa ID, thời điểm và wording trong chính tên event, phá khả năng nhóm. Hãy dùng `event="payment_retry"` ổn định và thêm field `orderId`, `attempt`, `reason` **khi được phép ghi**.

Để tối ưu truy vấn:

1. **Tên event mô tả một loại hành vi**, không phải một instance.
2. **Field name nhất quán** giữa các service khi cùng ý nghĩa.
3. **Giữ type/đơn vị nhất quán**, ví dụ `durationMs` là số millisecond.
4. **Chọn field theo câu hỏi điều tra**: nếu không ai dùng một field và nó tăng chi phí/bảo mật, cân nhắc bỏ.
5. **Lưu message cho con người** nhưng đừng biến message thành nguồn dữ liệu duy nhất cho aggregation.

Structured logging tốt là **thiết kế sự kiện**, không chỉ một tác vụ đổi console pattern thành JSON.

## 9. Bảo mật và quyền riêng tư: dễ tìm cũng là dễ lộ

Structured logging làm dữ liệu dễ tìm và trích xuất theo field, vì vậy nếu vô tình ghi `email`, `accessToken`, `Authorization` hoặc thông tin thanh toán, rủi ro **lan truyền/khai thác thông tin nhạy cảm** có thể tăng.

Không nên ghi:

~~~json
{
  "event": "login_failed",
  "password": "plaintext-password",
  "authorization": "Bearer secret-token"
}
~~~

Đây là **ví dụ dữ liệu KHÔNG ĐƯỢC GHI**, không phải hướng dẫn đưa thông tin thật vào hệ log.

Thay vào đó, chọn field tối thiểu:

~~~json
{
  "event": "login_failed",
  "outcome": "DENIED",
  "reason": "INVALID_CREDENTIALS",
  "requestId": "req-17"
}
~~~

Nguyên tắc:

- **Allowlist field ở nguồn phát:** chỉ ghi thứ có mục đích vận hành xác định.
- **Không log secrets**: password, token, API key, session cookie, private key, dữ liệu thẻ, payload xác thực.
- **Giảm khả năng định danh cá nhân:** nếu cần điều tra một tài khoản, xem xét ID nội bộ/pseudonym phù hợp và chính sách bảo vệ.
- **Redaction phải đúng thứ tự:** lý tưởng là trước khi serialization/ingestion; tránh tin vào việc một regex sau đó sẽ tìm được mọi secret.
- **Phân quyền và retention:** structured log có thể được sao chép đến collector, index, archive, dashboard và export; mỗi nơi cần quyền/trách nhiệm dữ liệu.
- **Region/tenant separation:** nếu có yêu cầu dữ liệu theo khu vực hoặc tenant, phải áp dụng trong pipeline và storage.
- **Exception cũng chứa dữ liệu:** message hoặc stack trace có thể chứa URL, SQL, tham số hoặc payload nhạy cảm.

**JSON escaping không phải redaction.** Một thư viện JSON chuẩn giúp bảo toàn cấu trúc khi gặp dấu nháy/newline, nhưng không tự biết field nào là bí mật. Tương tự, truyền tham số `{}` của SLF4J không tự che token.

Một rủi ro khác là **log injection**: text không escape newline có thể tạo “dòng log giả”; JSON Lines với encoder đúng có thể giữ các ký tự điều khiển trong value dưới dạng escaped. Điều đó giúp bảo toàn ranh giới event, nhưng không thay thế việc validate nguồn dữ liệu.

## 10. Async logging: throughput tăng nhưng có đánh đổi về độ tin cậy

Structured events thường được gửi qua queue/buffer hoặc appender bất đồng bộ để tránh thread nghiệp vụ chờ serialization/I/O. Cơ chế async có thể tăng throughput và giảm độ trễ trung bình, nhưng đưa thêm:

- **Queue capacity:** queue đầy thì hệ thống xử lý thế nào?
- **Backpressure:** có chặn thread ứng dụng để bảo toàn log không?
- **Drop policy:** có chủ động bỏ log debug/info khi quá tải không?
- **Shutdown/flush:** sự kiện trong queue có được ghi xong trước khi process dừng không?
- **Ordering:** thứ tự bản ghi giữa thread/process có giữ như người đọc mong đợi không?
- **Metadata capture:** requestId/traceId/MDC đã được chụp khi tạo event chưa?
- **Memory overhead:** event/map/object trong queue chiếm bộ nhớ và có thể gây GC pressure.
- **Lỗi downstream:** network/file/collector không nhận thì có retry, buffer hay cảnh báo không?

| Chính sách khi queue đầy | Lợi ích | Rủi ro |
| --- | --- | --- |
| Chặn producer | Ít mất log hơn nếu backend phục hồi | Tăng latency, lan backpressure tới nghiệp vụ |
| Bỏ bớt event theo level/sampling | Giữ thread nghiệp vụ phản hồi nhanh | Mất thông tin điều tra đúng lúc có sự cố |
| Buffer/retry ở tầng ngoài | Tăng khả năng phục hồi ngắn hạn | Tốn bộ nhớ/đĩa, có giới hạn và cần vận hành |

Không có lựa chọn chung tối ưu: app giao dịch có yêu cầu audit khác ứng dụng xử lý ảnh hoặc game telemetry. **Application log không tự nhiên là hệ thống audit bền vững**. Nếu một sự kiện cần được xác nhận ghi và không được mất theo hợp đồng nghiệp vụ, cần một cơ chế lưu trữ đáng tin riêng với transaction/acknowledgement phù hợp.

## 11. Structured logging và correlation context trong Java

Khi một request đi qua nhiều lớp, có thể thêm `traceId`, `spanId`, `requestId` hoặc thông tin tenant có kiểm soát. Tùy API/backend, các dữ liệu này có thể được truyền qua **MDC** hoặc SLF4J 2.x fluent API.

### MDC có ưu và nhược điểm gì?

MDC (*Mapped Diagnostic Context*) thường là một map các **string** theo ngữ cảnh thực thi. Ví dụ SLF4J:

~~~java
// Đoạn minh họa trong một method đã có requestId và logger.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", requestId)) {
    logger.info("event=order_accepted");
}
~~~

Điểm mạnh: mã bên trong scope có thể gắn cùng requestId mà không cần truyền nó vào mọi message thủ công. Điểm yếu: MDC thường dựa trên cơ chế context theo thread, vì vậy **không mặc nhiên truyền qua thread pool, CompletableFuture, reactive pipeline hoặc một service khác**.

Nếu quên xóa MDC ở thread pool, một request sau có thể nhận nhầm ID request trước; đặt trong `try-with-resources` hoặc cơ chế context propagation của framework giúp hạn chế rò rỉ context.

**MDC string không bảo đảm field JSON giữ kiểu number/boolean.** Nếu bạn lưu `durationMs="42"` trong MDC, encoder có thể xuất thành JSON string; để có typed value cần encoder/API hỗ trợ dữ liệu có kiểu.

### SLF4J 2 fluent key-value API

SLF4J 2.x hỗ trợ thêm cặp khóa–giá trị ở mức event:

~~~java
// Đoạn minh họa trong một method có logger SLF4J 2.x.
logger.atInfo()
        .addKeyValue("event", "order_accepted")
        .addKeyValue("durationMs", durationMs)
        .addKeyValue("orderId", orderId)
        .log("Order accepted");
~~~

Đây **không phải chương trình độc lập**; `durationMs` và `orderId` là biến trong scope. API cho phép đính metadata, nhưng **không cam kết mọi backend/encoder sẽ tự đưa chúng thành JSON fields đúng kiểu**. Cần cấu hình/test output thực tế. Ví dụ Logback text pattern có converter cho key-value pairs, nhưng pattern text vẫn không tự trở thành một object JSON typed.

Khi dùng SLF4J facade, việc ghi structured đúng còn phụ thuộc **provider, backend, encoder và collector**. Nếu backend đang là JUL hoặc NOP, thêm key-values không tự tạo một pipeline JSON.

## 12. Ví dụ Java 17+ chạy được: text đối chiếu JSON an toàn

Ví dụ này tạo cùng một message với dấu nháy và ký tự newline, so sánh bản text nối chuỗi với bản JSON được Jackson serialize đúng. Nó cũng minh họa field số và allowlist: chương trình **không đưa `apiKey` vào event map**.

Đây là ví dụ về **encoding và thiết kế log event**, chưa tự cài backend SLF4J/Logback hoặc ghi ra file. Trong production, đối tượng event thường được encoder của backend biến thành JSON. Ta dùng thư viện JSON chuyên dụng thay vì tự ghép JSON để không giới thiệu cách làm dễ sai.

### 12.1. Cấu trúc dự án

~~~text
structured-tradeoff-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StructuredTradeoffDemo.java
~~~

### 12.2. pom.xml

Ví dụ sử dụng Java 17+, Maven và Jackson `jackson-databind:2.18.4` (một version minh họa đã kiểm thử, **không khẳng định là version mới nhất**).

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>structured-tradeoff-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>2.18.4</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 12.3. StructuredTradeoffDemo.java

~~~java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;

public final class StructuredTradeoffDemo {
    public static void main(String[] args) throws Exception {
        String untrustedMessage = "gateway said: \"retry\"\nplease wait";
        String plain = "WARN checkout_failed requestId=req-17 durationMs=42"
                + " message=" + untrustedMessage;

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("event", "checkout_failed");
        event.put("level", "WARN");
        event.put("requestId", "req-17");
        event.put("durationMs", 42);
        event.put("attempt", 2);
        event.put("outcome", "RETRYABLE");
        event.put("message", untrustedMessage);

        String json = new ObjectMapper().writeValueAsString(event);

        System.out.println("plainPhysicalLines=" + plain.split("\\R", -1).length);
        System.out.println("jsonPhysicalLines=" + json.split("\\R", -1).length);
        System.out.println("durationIsNumber=" + (event.get("durationMs") instanceof Number));
        System.out.println("hasSensitiveField=" + event.containsKey("apiKey"));
        System.out.println("json=" + json);
    }
}
~~~

Chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StructuredTradeoffDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
plainPhysicalLines=2
jsonPhysicalLines=1
durationIsNumber=true
hasSensitiveField=false
json={"event":"checkout_failed","level":"WARN","requestId":"req-17","durationMs":42,"attempt":2,"outcome":"RETRYABLE","message":"gateway said: \"retry\"\nplease wait"}
~~~

Giải thích:

1. Chuỗi `untrustedMessage` chứa **một dấu nháy và một ký tự newline thật**. Khi nối trực tiếp vào plain text, event tạo **hai dòng vật lý**, có thể làm collector đọc nhầm thành hai bản ghi.
2. Jackson encode dấu nháy thành chuỗi escaped `\\\"` và newline thành `\\n`; object JSON vẫn nằm trên **một dòng vật lý**.
3. `durationMs` và `attempt` được truyền dưới dạng số nên serializer xuất numeric literals, không phải chuỗi `"42"` hay `"2"`.
4. `hasSensitiveField=false` chỉ chứng minh chương trình **không đưa key `apiKey` vào map**. Đây không phải bộ lọc bí mật tổng quát; value của `message` trong ứng dụng thật vẫn cần được kiểm soát.
5. `LinkedHashMap` giúp output giữ thứ tự chèn field trong ví dụ. **Đừng xây dashboard phụ thuộc thứ tự thuộc tính JSON**: theo nguyên tắc trao đổi dữ liệu, field name/type mới là phần quan trọng.
6. Ví dụ chưa có timestamp để kết quả không thay đổi giữa các lần chạy. Ở production, cần timestamp của **thời điểm event**, kèm timezone rõ ràng.

**Đánh đổi của chính ví dụ:** Jackson và `ObjectMapper` thêm dependency, công việc serialize và cấp phát object/chuỗi. Trong backend logging chuyên dụng, nên quản lý encoder được hỗ trợ và tránh tự tạo một `ObjectMapper` hoặc event map lớn cho mọi message nếu không cần thiết.

## 13. Mỗi event một dòng chưa đủ cho structured logging tốt

Một JSON object hợp lệ có thể chứa dữ liệu không truy vấn được nếu bạn gom tất cả vào `message`:

~~~json
{"message":"checkout failed; requestId=req-17; durationMs=42"}
~~~

Người đọc vẫn phải parse chuỗi bên trong nếu muốn lấy duration. Tốt hơn:

~~~json
{"event":"checkout_failed","requestId":"req-17","durationMs":42}
~~~

Tuy nhiên không nên cực đoan chuyển **mọi từ trong message thành field**. Field quá nhiều làm schema cồng kềnh, tăng storage/index và khó giữ thống nhất. Chỉ tách các giá trị cần lọc, nhóm, truy vết hoặc có ý nghĩa contract lâu dài.

### Có nên bỏ message vì đã có event/fields?

Không nhất thiết. `message` ngắn, rõ nghĩa giúp người vận hành đọc nhanh khi ở terminal; `event` và field cho phép máy truy vấn. Cả hai có thể cùng tồn tại nếu không tạo dữ liệu nhạy cảm hoặc sự dư thừa vô ích.

Ví dụ:

~~~json
{
  "level": "WARN",
  "event": "payment_retry",
  "message": "Retry scheduled after gateway timeout",
  "reason": "TIMEOUT",
  "attempt": 2
}
~~~

Ở đây message là cho con người; `event`, `reason` và `attempt` phục vụ automation.

## 14. Hạn chế với hệ thống thu thập và truy vấn

Tạo JSON trong Java **không đảm bảo** backend quan sát nhận được object có cấu trúc:

- **Ingestion parser** có thể không parse JSON Lines mà lưu cả dòng như string.
- **Field mapping** có thể coi `durationMs` là string vì event đầu tiên chứa `"42"`.
- **Nested fields** có thể bị flatten thành tên khác; ví dụ `http.status` và object `{"http":{"status":200}}` không phải lúc nào cũng tương đương.
- **Field name conflict** có thể xảy ra khi hai service dùng cùng key khác type.
- **Dropped events** có thể xuất hiện nếu queue/collector/backpressure bị quá tải.
- **Indexing policy** có thể tạo hoặc không tạo index cho field tùy cấu hình.
- **Timestamp parsing** có thể dùng ingestion time thay vì event time nếu field không được map đúng.
- **Multiline parsing** vẫn cần với stack trace text; JSON serializer chỉ đảm bảo các control characters trong *giá trị JSON* được escape đúng.
- **Retention/tiering** quyết định một bản ghi có còn searchable sau nhiều ngày không, không phải ở phía Java.

Muốn xác minh structured logging đã thành công, hãy làm một **end-to-end test**:

1. Phát event có một ID kiểm thử không nhạy cảm.
2. Xem raw output là JSON hợp lệ, một object/event.
3. Xác nhận collector đọc được, các field và kiểu đúng.
4. Thử query bằng field số, enum và traceId/requestId.
5. Kiểm tra phân quyền và cách dữ liệu nhạy cảm được xử lý.
6. Tạo tình huống queue đầy hoặc backend chậm trong môi trường thử.
7. Xác nhận kết quả ở nơi lưu/hiển thị cuối cùng, không chỉ `System.out.println`.

Một file JSON đẹp nhưng dashboard không parse được không đáp ứng mục tiêu structured logging.

## 15. Structured logging không thay thế metrics và tracing

Ba tín hiệu quan sát có vai trò khác nhau:

| Tín hiệu | Phù hợp nhất cho | Giới hạn |
| --- | --- | --- |
| **Logs có cấu trúc** | Chi tiết từng sự kiện, lỗi, quyết định, ngữ cảnh | Dung lượng lớn, query/index tốn chi phí |
| **Metrics** | Tốc độ, tỷ lệ, percentile, cảnh báo xu hướng | Thường không lưu từng request; label cardinality phải kiểm soát |
| **Distributed traces** | Quan hệ các span và đường đi của request giữa service | Sampling và instrumentation có thể bỏ một số trace |

Có `traceId` trong logs giúp liên kết chúng với traces, nhưng **không tự tạo span**. Đưa `durationMs` vào từng log giúp điều tra một request, nhưng muốn cảnh báo p99 latency theo service thường cần metrics/histograms hoặc công cụ aggregate phù hợp.

Không cố dùng log event riêng lẻ để thay mọi metric: logging cho mọi thao tác hot path có thể đắt. Ngược lại, metric lỗi tổng không cung cấp requestId/stack trace cụ thể; structured log hỗ trợ điều tra nguyên nhân.

## 16. Khi nào nên chọn structured, text hoặc kết hợp?

| Bối cảnh | Hướng phù hợp | Lý do |
| --- | --- | --- |
| Microservices có collector, dashboard, tracing | Structured logging theo schema chung | Lọc và liên hệ dữ liệu qua nhiều service |
| Ứng dụng cần truy vấn lỗi theo event/reason/duration | Structured cho các event trọng yếu | Có field và type ổn định |
| Script CLI nhỏ, người dùng chủ yếu đọc console | Text gọn có thể đủ | Tránh vận hành schema/index không cần |
| Java service nhỏ nhưng dự kiến tăng trưởng | Text console cho dev, JSON trong môi trường ingest | Dùng encoder theo profile, giữ API log phù hợp |
| Hệ thống có volume log rất cao | Structured chọn lọc + level/sampling/retention | Giảm chi phí ở nguồn trước indexing |
| Hệ thống yêu cầu audit không mất sự kiện | Cơ chế audit bền vững riêng | Logging thông thường không bảo đảm transactional durability |
| Thiết bị/ứng dụng tài nguyên hạn chế | Đo chi phí encoder và chọn cấu hình nhẹ | CPU, bộ nhớ, lưu trữ và uplink là ràng buộc |
| Ứng dụng legacy với log text ổn định | Di trú từng nhóm event có giá trị | Không cần đổi tất cả trong một lần |

**Không nên quyết định chỉ theo “JSON trông hiện đại hơn”.** Hãy trả lời: những truy vấn nào phải nhanh, bao nhiêu event mỗi giây, chi phí lưu/search chấp nhận được là bao nhiêu, dữ liệu nào được phép ghi và ai chịu trách nhiệm schema.

Một cách triển khai thực dụng là **cùng API phát event nhưng có hai output profile**: text dễ đọc ở môi trường phát triển và JSON Lines cho collector ở môi trường cần phân tích. Tuy nhiên hãy kiểm tra rằng **field semantics và level** nhất quán giữa các profile.

## 17. Quy trình triển khai từng bước và đo kết quả

### Bước 1 — Xác định câu hỏi quan sát

Ví dụ:

- “Bao nhiêu lần retry thanh toán trong 15 phút gần nhất?”
- “Các lỗi timeout ở service nào?”
- “Những request có `durationMs > 1000` đang thuộc route nào?”
- “Một `traceId` đã đi qua những service nào?”

Các câu hỏi dẫn tới field: `event`, `reason`, `service`, `durationMs`, `route`, `traceId`.

### Bước 2 — Lập schema tối thiểu

Chọn danh sách field cần thiết, type, đơn vị và ý nghĩa. Viết rõ: `durationMs` là **number tính bằng millisecond**; `event` là enum string ổn định; `timestamp` dùng UTC/offset rõ.

### Bước 3 — Chọn API và encoder

Với Java, xem SLF4J 2 fluent key-value, MDC/context propagation, Logback/Log4j 2 encoder hoặc JUL logging pipeline phù hợp. Kiểm tra dependency backend; **có SLF4J API không đồng nghĩa tự có JSON encoder**.

### Bước 4 — Bảo vệ dữ liệu ngay từ nguồn

Áp dụng field allowlist, redaction, giới hạn độ dài và kiểm tra exception. Không đưa raw HTTP headers, token hay request body vào structured event chỉ vì serializer làm điều đó dễ dàng.

### Bước 5 — Chạy song song có kiểm soát

Có thể thử trên một service/nhóm event quan trọng, so sánh text và structured outputs hoặc chuyển một phần lưu lượng. Cần tránh vô ý **ghi trùng cùng event vào hai pipeline tính phí** mà không đo chi phí.

### Bước 6 — Benchmark end-to-end

Đo:

- CPU, allocation, GC và p99 latency của application.
- Bytes/event thực tế sau encoder và compression.
- Ingest throughput và lỗi parse/mapping.
- Index/storage/retention cost.
- Query latency và chất lượng alert.
- Event drop/backpressure lúc collector bị chậm.
- Tỷ lệ event thiếu các trường bắt buộc.

### Bước 7 — Quản lý schema như code

Đặt tên field, types, sample event và contract test trong repository cấu hình/phần mềm phù hợp. Khi đổi schema, review tác động đến dashboard, ingestion và chính sách bảo mật.

### Bước 8 — Điều chỉnh retention và indexing

Không lập index mọi field theo quán tính. Tách nhu cầu tìm kiếm gần hạn với lưu trữ dài hạn, giới hạn truy cập dữ liệu nhạy cảm và kiểm tra các truy vấn thực tế cần giữ.

## 18. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| JSON có nhưng vẫn phải regex message | Dồn mọi dữ liệu vào `message` | Tách field ổn định có ý nghĩa truy vấn |
| Query `durationMs > 1000` sai | Field là string hoặc mapping type sai | Giữ numeric type, test ingestion mapping |
| Index/storage tăng mạnh | Nhiều field, cardinality cao, retention dài | Đo chi phí, chọn field index, giới hạn log volume |
| JSON bị vỡ khi input có newline/dấu nháy | Nối JSON thủ công | Dùng JSON serializer/encoder hợp lệ |
| Có field requestId trên thread khác nhưng sai giá trị | MDC không được dọn/truyền context đúng | Scope rõ, try/finally, context propagation |
| Log thiếu traceId ở async job | Thread boundary làm mất context | Capture/propagate context trước khi tạo event |
| CPU/GC tăng khi bật structured | Serialize object lớn, stack trace, caller location | Đo profile, rút gọn field và lazy data creation |
| Service p99 latency tăng khi collector chậm | Async queue đầy rồi block producer | Thiết kế backpressure/drop theo nhu cầu |
| Bản ghi bị mất khi shutdown | Queue chưa flush hoặc backend lỗi | Đo shutdown behavior, xử lý lifecycle và audit riêng |
| Field `service` hoặc `event` không thống nhất | Không quản trị schema | Schema contract, enum và code review |
| Field `durationMs` đổi đơn vị | Không có quy ước type/unit | Đặt đơn vị vào tên và test |
| Secrets xuất hiện trên dashboard | Ghi raw DTO/headers, không có allowlist | Chặn/redact ở nguồn, rà index/archive |
| JSON encoder đã bật nhưng collector lưu chuỗi | Parser/ingestion pipeline chưa cấu hình | Test raw→collector→index→query |
| Developer console khó đọc | JSON dài, nhiều metadata | Tạo dev text profile hoặc trình xem có render field |
| Dùng requestId làm metric label | Cardinality cực cao | Giữ trong log, dùng label metric có cardinality thấp |
| Message thay đổi làm cảnh báo hỏng | Alert dựa regex text | Alert theo `event`/`reason` ổn định |

## 19. Bài tập tự kiểm tra

**Bài 1.** Một service xuất `{"durationMs":"42"}` và `{"durationMs":100}`. Điều gì có thể xảy ra?

**Đáp án:** cùng field có type không nhất quán; collector có thể map lỗi, bỏ field hoặc xử lý khác nhau. Cần chuẩn hóa `durationMs` thành numeric ở nguồn và test ingestion.

**Bài 2.** Vì sao không nên đưa `requestId` vào label của một metric counter dù nó rất hữu ích trong log?

**Đáp án:** requestId thường gần như duy nhất, khiến cardinality của time series bùng nổ. Log field phục vụ tìm một request còn metric label phục vụ phân nhóm hữu hạn; chúng có ràng buộc khác nhau.

**Bài 3.** JSON có khả năng tránh log injection tự động không?

**Đáp án:** JSON encoder đúng sẽ escape dấu nháy/newline/control characters để bảo vệ cấu trúc, nhưng không bảo đảm không có secret, không thay validation và không ngăn nội dung sai lệch từ nguồn không tin cậy.

**Bài 4.** Tại sao một log event có đủ `event` và `traceId` vẫn có thể không xuất hiện trong dashboard?

**Đáp án:** provider/encoder có thể cấu hình sai, logger level bị lọc, queue drop, collector không parse/index, hoặc dữ liệu nằm ngoài retention. Cần kiểm tra end-to-end thay vì chỉ xem object Java.

**Bài 5.** Nếu JSON payload tăng gấp đôi text, có thể kết luận tổng chi phí logging tăng gấp đôi không?

**Đáp án:** Không. Compression, indexing, tiering, query volume, replication, network và backend pricing làm tổng chi phí thay đổi khác. Cần đo trên hệ thống thực.

**Bài 6.** Một đội chỉ có script CLI và đọc log bằng terminal. Có cần áp dụng JSON cho mọi dòng debug không?

**Đáp án:** Không bắt buộc. Nếu không có nhu cầu truy vấn theo field hoặc pipeline ingest, text gọn có thể đủ. Có thể chỉ tạo structured output ở nơi cần tự động hóa.

## 20. Checklist trước khi chọn structured logging

- [ ] Đã nêu rõ các câu hỏi truy vấn/alert cần field thay vì regex.
- [ ] Phân biệt message text với **event name và typed fields**.
- [ ] Có schema tối thiểu cho timestamp, level, service, event, reason, ID và số liệu.
- [ ] Tên field và đơn vị ổn định; không tạo field name động theo request ID.
- [ ] Tách **log fields** khỏi **metric labels** có cardinality thấp.
- [ ] Chỉ giữ các field có giá trị; không serialize nguyên request/DTO lớn theo quán tính.
- [ ] Dùng encoder JSON được kiểm chứng, không nối JSON bằng string tùy tiện.
- [ ] Áp dụng allowlist/redaction ở nguồn; không ghi token, password hoặc dữ liệu nhạy cảm.
- [ ] Kiểm tra MDC/context propagation qua thread pool và async execution.
- [ ] Kiểm thử exception, newline, Unicode, trường null/missing và type.
- [ ] Đo CPU, allocation, p99 latency, bytes/event, index/storage và query.
- [ ] Xác định hành vi queue đầy, drop/backpressure, flush và shutdown.
- [ ] Cấu hình mapping/parse ở collector, phân quyền và retention.
- [ ] Xác nhận một log event đi trọn đường **Java → backend → collector → truy vấn**.
- [ ] Với audit yêu cầu độ bền, dùng cơ chế lưu trữ xác nhận riêng.
- [ ] Chọn structured, text hoặc kết hợp dựa trên **nhu cầu và số liệu đo được**.

**Kết luận:** Structured logging đổi **sự linh hoạt của text tự do** lấy **khả năng truy vấn và tự động hóa bằng field có kiểu**, đồng thời đưa thêm chi phí serialization, storage/index, schema governance, cardinality và bảo vệ dữ liệu. Cách áp dụng hiệu quả là **ghi đúng sự kiện, với đúng field, đúng type, đúng context và retention**, sau đó đo kết quả end-to-end. Khi chưa có nhu cầu truy vấn theo field hoặc tài nguyên rất hạn chế, text logging tốt vẫn là một lựa chọn hợp lý.