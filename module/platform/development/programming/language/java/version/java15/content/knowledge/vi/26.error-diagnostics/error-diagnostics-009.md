# Chẩn đoán lỗi Java: kiểm soát dữ liệu nhạy cảm trong thông điệp chẩn đoán

> **Phạm vi Java 15 và JDK hiện đại:** Khi xảy ra lỗi, ứng dụng Java thường tạo exception, stack trace, log event, HTTP error response, distributed trace, JFR recording, heap dump hoặc báo cáo crash. Những kênh này rất hữu ích để tìm nguyên nhân, nhưng cũng có thể tiết lộ mật khẩu, access token, cookie, dữ liệu cá nhân, khóa riêng, thông tin hệ thống hoặc dữ liệu nghiệp vụ. Cách an toàn không chỉ là “ẩn bớt log”: phải **giới hạn ngay dữ liệu được thu thập**, thiết kế schema chẩn đoán theo allowlist, kiểm soát mã lỗi và correlation ID, chống log injection, bảo vệ các tệp chẩn đoán, quyền truy cập và vòng đời lưu trữ. Các ví dụ dùng API chuẩn Java 17+ và cũng áp dụng tư duy bảo mật cho Java 15; không dựa vào kỹ thuật legacy.

## 1. Vì sao chẩn đoán có thể trở thành nguồn rò rỉ?

Xét một chức năng đăng nhập. Một exception chứa thông điệp như sau là nguy hiểm:

~~~text
Authentication failed for password=<secret> and token=<token>
~~~

Nếu ứng dụng ghi `exception.getMessage()` hoặc `printStackTrace()` vào log, chính **exception message** đó có thể được lưu trên console, agent, hệ thống log tập trung, dashboard, thông báo chat hoặc ticket hỗ trợ. Ngay cả khi ứng dụng không bao giờ in biến `password` trực tiếp, **dữ liệu đã đi vòng vào throwable**.

Một ví dụ khác: chương trình chụp **heap dump** để tìm memory leak. Dù application logs được che sạch, bộ nhớ heap có thể chứa `String`/`byte[]`/objects mang dữ liệu nhạy cảm; heap dump vì thế phải được xử lý như **artifact bảo mật cao**, không như một file log thông thường.

### Những đường đi dữ liệu cần mô hình hóa

~~~text
Untrusted / sensitive input
   |
   +--> Exception message / cause / suppressed exception
   +--> Application structured log / console / stdout / stderr
   +--> HTTP / RPC error response
   +--> Tracing spans, baggage, attributes and events
   +--> Metrics labels / exemplars
   +--> JVM recording, JFR custom event, stack traces
   +--> Heap dump / process core dump / hs_err report
   +--> Support bundle / incident ticket / dashboard / alert
                 |
                 v
       Người xem / lưu trữ / hệ thống bên thứ ba
~~~

**Nguyên tắc cốt lõi:** mọi kênh chẩn đoán là một **điểm xuất dữ liệu** cần phân loại, giới hạn và áp chính sách. Không đồng nhất “chỉ nhân viên kỹ thuật xem được” với “an toàn để ghi mọi dữ liệu”.

## 2. Phân loại dữ liệu trước khi thiết kế thông điệp

Một chính sách ví dụ có thể chia dữ liệu thành:

| Lớp | Ví dụ | Cách dùng trong chẩn đoán |
| --- | --- | --- |
| Public/technical | Tên operation từ enum, loại lỗi chuẩn hóa, HTTP status | Có thể ghi nếu thực sự cần, giới hạn kích thước và kiểm soát format |
| Internal operational | Tên service, environment, build version, internal request ID | Ghi theo nhu cầu quan sát, kiểm soát truy cập |
| Personal/sensitive | Email, họ tên, IP có khả năng nhận diện, địa chỉ, hồ sơ cá nhân, số tài khoản | Thường không ghi raw; chỉ xử lý nếu có cơ sở và mục đích hợp lệ |
| Credential/secret | Password, refresh/access token, API key, cookie/session, private key, database password, seed | **Không ghi trực tiếp** vào logs/traces/diagnostics |
| Confidential business | Giá giao dịch, nội dung hợp đồng, dữ liệu khách hàng, query có tham số | Mặc định không ghi raw; cân nhắc field được cho phép, masking/tokenization |

**Lưu ý pháp lý:** dữ liệu nào là PII hoặc sensitive còn phụ thuộc luật, ngành và ngữ cảnh. Bảng là **mẫu tư duy kỹ thuật**, không thay thế chính sách bảo vệ dữ liệu của tổ chức.

Các nguồn thường bị bỏ sót:

- `Authorization: Bearer ...`, `Cookie`, `Set-Cookie`, webhook secret;
- `password`, `client_secret`, OAuth authorization code, signed URL query string;
- DSN/connection URL chứa `user:password@host`;
- HTTP request/response bodies có dữ liệu người dùng;
- SQL parameters, full object `toString()`, JSON serialization toàn DTO;
- Header `X-API-Key` và session correlation nhạy cảm;
- File paths, environment names hoặc JVM arguments mang secret;
- Exception cause lồng nhau do JDBC/HTTP client thư viện bên ngoài tạo ra.

Đặc biệt: **một session ID hoặc token không trở thành an toàn chỉ vì được gọi là correlation ID**.

## 3. Thiết kế schema chẩn đoán theo allowlist, không dùng blacklist toàn văn

Một event hữu ích có thể chỉ cần:

~~~json
{
  "event": "operation_failed",
  "operation": "LOGIN",
  "reason_code": "AUTH_REJECTED",
  "request_id": "req_42",
  "http_status": 401,
  "duration_ms": 12
}
~~~

Các field trên là **ví dụ với dữ liệu thử nghiệm**, không phải log thực tế. Không có password, email, token, request body hoặc thông điệp exception raw.

### Vì sao allowlist tốt hơn regex redaction sau cùng?

**Blacklist** cố tìm mọi dạng secret trong một string tự do: `password=...`, `token=...`, `secret=...`. Nhưng token có thể được đặt trong JSON lồng nhau, URL-encoded, base64, nhiều dòng, không có tên field chuẩn hoặc do thư viện tự thêm. Regex không thể nhận ra mọi loại dữ liệu nhạy cảm.

**Allowlist** chỉ ghi đúng các field đã phê duyệt:

- `event` và `operation` lấy từ enum/controlled vocabulary;
- `reason_code` là mã lỗi cố định, không phải `Throwable.getMessage()`;
- `request_id` là ID nội bộ được sinh bởi server hoặc được validate nghiêm ngặt;
- `http_status`, `duration_ms` là số đo hoặc mã trạng thái;
- Tenant/resource identifiers chỉ đưa vào nếu chính sách cho phép và không tiết lộ dữ liệu liên tenant.

Lợi ích: người viết event **không có API để truyền cả request object** hoặc Exception raw vào payload thông thường.

### Phân biệt event code và human-readable details

Một mã như `UPSTREAM_TIMEOUT` hoặc `DB_UNAVAILABLE` ổn định, dễ search/aggregate và ít rủi ro hơn chuỗi:

~~~text
Connection failed to jdbc:postgresql://user:password@db.internal/...
~~~

Với câu lỗi gửi cho client, nên có **message công khai tách riêng**, không chỉ copy message kỹ thuật từ backend. Một mã HTTP 500 hoặc JSON code ổn định giúp client biết trạng thái mà không tiết lộ nội bộ.

## 4. Exception: điểm rò rỉ phổ biến nhất trong Java

Java `Throwable` có:

- `getMessage()` và `getLocalizedMessage()`;
- `getCause()`, chuỗi nguyên nhân;
- `getSuppressed()`, những exception bổ sung;
- `getStackTrace()`, stack trace elements;
- `toString()` và `printStackTrace()`.

### 4.1. Vì sao in một Throwable có thể lộ thông tin?

Theo Java API, `Throwable.toString()` thường ghép tên exception class với thông điệp được trả bởi `getLocalizedMessage()`. `printStackTrace()` in exception và backtrace; có thể kèm các cause/suppressed exception. Nếu một thông điệp lỗi cấp dưới chứa token, SQL text hoặc URL nhạy cảm, lời gọi:

~~~java
// Mảnh minh họa KHÔNG AN TOÀN khi Throwable chứa dữ liệu nhạy cảm.
System.err.println(exception);
exception.printStackTrace();
logger.log(Level.SEVERE, "Request failed", exception);
~~~

có thể chuyển dữ liệu nhạy cảm sang kênh log. **Parameterized logging không tự loại bỏ điều này**; nhiều framework khi nhận `Throwable` vẫn in message/cause/stack trace.

**Lưu ý chính xác:** stack trace thông thường **không in tất cả local variables mặc định**. Nhưng class names, methods, file/line positions, exception messages và cause chain vẫn có thể nhạy cảm; các công cụ heap/debug/profiling sâu hơn có khả năng truy cập nhiều dữ liệu hơn.

### 4.2. Không tạo exception message chứa secret ngay từ đầu

Không nên:

~~~java
// SAI: thông điệp đã chứa dữ liệu nhạy cảm.
throw new IllegalArgumentException(
        "Bad token: " + suppliedToken);
~~~

Nên:

~~~java
// ĐÚNG VỀ TƯ DUY: mã lỗi được kiểm soát.
throw new IllegalArgumentException("INVALID_AUTH_TOKEN");
~~~

**Tuy nhiên**, một thông điệp cố định không thay thế validation và auth. Ngoài ra, nếu bao gói exception bằng constructor có cause, hãy nhớ rằng tầng logging phía trên **có thể in cả cause chain**, bao gồm thông điệp nhạy cảm từ thư viện bên thứ ba.

### 4.3. Không đưa raw exception vào HTTP response

Pattern nên áp dụng:

~~~text
Internal exception with technical details
        |
        v
Error mapping policy
        |
        +--> client: HTTP status + public error code + request ID
        |
        +--> diagnostics: sanitized event + internal correlation ID
        |
        +--> restricted incident investigation if authorized
~~~

Mẫu trả client:

~~~json
{
  "code": "REQUEST_FAILED",
  "message": "Unable to complete request",
  "requestId": "req_42"
}
~~~

Không gửi stack trace, database connection string, upstream response body hay debug internals cho client trong production. Thông điệp phải nhất quán, tránh tạo oracle tiết lộ thông tin về sự tồn tại tài khoản, credential hoặc tài nguyên nhạy cảm.

### 4.4. Khi vẫn cần stack trace cho điều tra

Đừng giải quyết bằng cách “không bao giờ được có stack trace”: đôi khi điều tra lỗi cần stack trace ở **kênh hạn chế**, với permission, thời hạn và pipeline lọc đã được đánh giá. Nhưng:

1. Kiểm tra message/cause/suppressed exceptions có dữ liệu nhạy cảm không.
2. Chỉ bật mức chi tiết cần thiết trong khoảng thời gian cần thiết.
3. Không tự động gửi raw stack trace vào ticket công khai hoặc chatbot.
4. Nếu không chắc có sạch hay không, **đánh dấu dữ liệu restricted**, thay vì giả định filter regex đủ.
5. Giữ error ID để liên kết với điều tra mà không phải copy nguyên nội dung lỗi.

## 5. Structured logging vẫn có thể gây rò rỉ

Các thư viện logging hiện đại thường hỗ trợ structured fields và parameterized formatting. Nhưng an toàn phụ thuộc **giá trị trường được truyền**.

Ví dụ không an toàn:

~~~java
// Mảnh minh họa với logger bất kỳ; không phải class chạy độc lập.
logger.info("login failed for request {}", request);
logger.error("upstream failed", exception);
~~~

Nếu `request.toString()` hiển thị token, hoặc `exception.getMessage()` chứa credential, parameterization **không cứu được**.

Thay bằng dữ liệu đã được kiểm soát:

~~~java
// Mảnh minh họa: operation, reason, requestId được validate trước.
logger.warn("event=operation_failed operation={} reason={} request_id={}",
        operation.name(), reason.name(), safeRequestId);
~~~

Đây là cú pháp minh họa của logger hỗ trợ placeholders, **không phải API `java.util.logging`**. Trong sản phẩm, dùng framework được duy trì và cấu hình structured JSON encoder để escape strings đúng chuẩn. Không xem `logger.info("{}", value)` là cơ chế chống dữ liệu nhạy cảm.

### Không dùng `toString()` tự động trên domain object

Một lớp:

~~~java
record LoginRequest(String username, String password) {}
~~~

là **mảnh ví dụ Java 17+** (Java records đã thành tính năng chính thức từ Java 16). `record.toString()` có thể biểu diễn tất cả components, bao gồm `password`. Vì vậy không log `request` hoặc `List<LoginRequest>` raw. Cần chủ động tránh sinh các `toString()` có dữ liệu nhạy cảm, đặc biệt với Lombok, IDE-generated methods và JSON serializers.

Đối với Java 15 target không dùng record stable API, cùng rủi ro vẫn xảy ra trên class/DTO thường.

## 6. Kiểm soát log injection và dữ liệu không tin cậy

Một attacker có thể gửi header hay request ID kiểu:

~~~text
req_42
level=INFO event=admin_login_success
~~~

Nếu ứng dụng nối thẳng chuỗi vào một line log, ký tự xuống dòng có thể tạo ra một **bản ghi giả**. OWASP gọi đây là **log injection/log forging**; CR/LF và control characters là những yếu tố quan trọng.

### 6.1. Cách xử lý phù hợp từng loại field

- **Request/correlation ID:** ưu tiên sinh tại server; nếu nhận từ client, áp allowlist `[A-Za-z0-9_-]{1,32}` hoặc quy định cụ thể, loại giá trị sai.
- **Reason codes:** dùng enum, không cho user tự cung cấp chuỗi.
- **URL, email hoặc free text khi thật sự được phê duyệt để ghi:** encode theo log format, kiểm soát control chars, truncation và Unicode.
- **JSON logs:** dùng serializer/encoder chuẩn có escaping; không tự nối JSON text bằng dấu `+`.
- **CSV/text logs:** escaping và chống newline/CR, delimiter injection theo format tương ứng.

**Mức bảo vệ đầu tiên** luôn là **không đưa secret vào logger**, sau đó mới là chống forging ở những trường được phép ghi.

### 6.2. Không hiểu “xóa newline” là giải pháp cho mọi vấn đề

Xóa `\r`/`\n` có thể giảm log forging ở một số text formats nhưng không xử lý:

- Secret vô tình được log;
- JSON/key-value injection qua ký tự delimiter;
- Unicode control characters khác;
- Dữ liệu quá lớn gây log flooding;
- PII từ `toString()` của DTO;
- Rò rỉ sang tracing hoặc metrics ngoài log.

Cần validation + canonical encoding theo **schema của sink**.

## 7. Correlation ID: liên kết sự kiện mà không lộ identity

Một `requestId` giúp nối sự kiện giữa frontend, API, downstream và dashboard. Nhưng:

- **Không dùng access token hoặc session cookie** làm request ID.
- Không dùng raw email/số điện thoại/ID nhạy cảm nếu mục tiêu chỉ là correlation.
- Nếu ID do client gửi, phải kiểm tra length/charset và không coi nó là nguồn xác thực.
- ID chỉ mang **tính tương quan**, không nên được dùng như authorization credential.
- Đừng lạm dụng correlation để tạo một định danh theo dõi cá nhân xuyên mọi dịch vụ mà không có chính sách.

### 7.1. Pseudonymization không tương đương anonymization

Nếu cần liên kết sự kiện cho cùng một account, có thể tạo **pseudonymous identifier** bằng HMAC với secret key bảo vệ trong KMS/secret manager và rotation policy thích hợp. Nhưng:

- Hash SHA-256 thuần trên email/số điện thoại dễ đoán có thể bị dictionary attack.
- HMAC output vẫn có khả năng là **dữ liệu cá nhân có thể liên kết** nếu hệ thống giữ khóa hoặc mapping.
- Không đưa HMAC key/secret vào source code, JVM arguments hoặc logs.
- Cần giới hạn mục đích, thời gian lưu và quyền tái liên kết.

Một **random opaque request ID** được server sinh ra thường là giải pháp đơn giản nhất cho correlation của **một request**, không cần dùng user identifiers.

### 7.2. Distributed tracing: trace ID cũng không phải bearer token

Các trace IDs giúp đối chiếu spans giữa services. Chúng không được dùng để cấp quyền. Nếu trace context đi qua boundary không tin cậy, validate cấu trúc và policy, đồng thời không dùng arbitrary client-controlled trace values làm identity chứng minh quyền truy cập.

## 8. Metrics và tracing có thể rò rỉ dữ liệu giống logs

### 8.1. Metrics labels và cardinality

Không nên tạo metric:

~~~text
login_errors_total{email="user@example.test",token="..."} 1
~~~

Ví dụ này **chỉ để chỉ ra lỗi**, không chứa token thật. Một metric label nhạy cảm bị lan sang Prometheus, OpenTelemetry collector, remote-write backend, dashboard và alerting.

Labels còn gây **high cardinality** khi dùng request ID, email hoặc raw URL query. Điều này làm tăng memory/cost và khó xử lý.

Nên dùng low-cardinality attributes:

~~~text
login_errors_total{operation="LOGIN",reason="AUTH_REJECTED"} 1
~~~

Nếu cần theo dõi một request, dùng tracing/logging với **correlation ID** được kiểm soát, không nhét mỗi request ID thành metric label.

### 8.2. Traces: attributes, events và baggage

Traces thường chứa span names, attributes, events, exception events và baggage được propagate. Tránh đặt vào:

- Access token, password, cookie, authorization headers;
- Request/response body có PII hoặc secrets;
- Query string chứa session hoặc signed URL token;
- User identifiers không cần thiết;
- Exception messages có thể mang dữ liệu nhạy cảm.

**OpenTelemetry baggage** đặc biệt cần chú ý: baggage có thể được tự động propagate sang downstream qua headers. Vì thế không đưa secrets hoặc thông tin cá nhân nhạy cảm vào baggage dù service hiện tại “chỉ dùng nội bộ”.

### 8.3. Sampling không thay thế sanitization

Sampling 1% nghĩa là **vẫn có thể lấy mẫu chứa secret**. Dù chỉ một trace chứa private key cũng đã là sự cố. Phải chặn dữ liệu nhạy cảm **trước khi** sampler/exporter xử lý; sampling chỉ điều tiết khối lượng, không phải chính sách bảo mật.

### 8.4. Instrumentation tự động

HTTP/JDBC/ORM instrumentation có thể tự ghi attributes/queries/errors. Không đủ nếu chỉ audit các lời gọi `logger.info` do đội ứng dụng tự viết. Phải kiểm tra:

1. Auto-instrumentation của HTTP server/client.
2. Database statement/SQL parameter collection.
3. Exception event attributes.
4. Exporters và collector processors.
5. Sampling/recording profiles.
6. Telemetry vendor transformations và retention.
7. Kênh chuyển tiếp từ OpenTelemetry Collector sang SIEM hoặc bên thứ ba.

Giảm dữ liệu ngay tại source; filters ở collector là **lớp bổ sung**, không bảo đảm đã chặn được mọi bản sao trước đó.

## 9. JFR và JVM diagnostic artifacts: bảo vệ ngay cả khi app log sạch

Java Flight Recorder (JFR) rất hữu ích để chẩn đoán production vì overhead thường thấp với cấu hình phù hợp, nhưng JFR vẫn là **dữ liệu chẩn đoán có thể nhạy cảm**.

JFR có thể chứa:

- Stack traces, class/method names, thread information;
- JVM environment/system properties hoặc command-line context tùy event/config;
- Allocation, lock contention, I/O và exception events;
- Các **custom JFR events** do ứng dụng định nghĩa, có thể chứa chuỗi được truyền vào;
- Thông tin kỹ thuật nội bộ về service.

**Không** khẳng định mọi JFR file luôn chứa toàn bộ environment variables, tất cả local variables hay raw request bodies. Nội dung phụ thuộc recording settings, enabled events, JVM implementation và custom instrumentation. Nhưng chính vì không thể bảo đảm file không có dữ liệu nhạy cảm chỉ bằng tên “JFR”, phải **phân loại restricted trước khi chia sẻ**.

### 9.1. Mở JFR có kiểm soát

Ví dụ trên JDK 17+ với JVM có JFR:

~~~bash
# Trong môi trường được phê duyệt, ghi ra nơi lưu trữ có quyền hạn chế.
java -XX:StartFlightRecording=filename=diagnostic.jfr,settings=default,dumponexit=true -jar app.jar
~~~

Trong production, đường dẫn thực tế nên là thư mục được kiểm soát quyền, quota/rotation, mã hóa phù hợp và cleanup. `settings=default` là profile thường nhẹ hơn `profile`, nhưng **không thay thế review thông tin bên trong**.

Nếu tiến trình đã chạy, có thể sử dụng `jcmd` khi có quyền attach:

~~~bash
jcmd 12345 JFR.start name=incident settings=default duration=60s filename=incident.jfr
jcmd 12345 JFR.check
~~~

`12345` là **PID minh họa**, không phải giá trị được phép copy vào sản phẩm. Lệnh yêu cầu công cụ/permission phù hợp. Hãy chọn thời lượng đủ để chẩn đoán, không bật recording chi tiết vô hạn khi không cần.

### 9.2. Custom JFR events: dữ liệu field thuộc trách nhiệm của developer

Một custom event như:

~~~java
// Mảnh minh họa API JFR, không phải chương trình chạy độc lập.
@jdk.jfr.Name("demo.AuthFailure")
class AuthFailureEvent extends jdk.jfr.Event {
    String reasonCode;
    String requestId;
}
~~~

có thể hữu ích nếu **chỉ ghi những field đã được duyệt**. Không tạo field `authorizationHeader`, `password` hay `rawRequestBody` trong một event dùng để debug và cho rằng JFR sẽ tự che dữ liệu.

Khi có custom events, thiết kế **schema review** giống structured logging; chỉ ghi codes, durations, counts và opaque correlation IDs cần thiết.

### 9.3. Heap dump: mức nhạy cảm cao hơn log thường

`jcmd` có lệnh tạo heap dump:

~~~bash
# Chỉ làm trên hệ thống được phép, với đường dẫn lưu trữ bảo vệ.
jcmd 12345 GC.heap_dump /secure/diagnostics/heap-incident.hprof
~~~

Vị trí PID và cú pháp diagnostic command được hỗ trợ phải kiểm tra theo `jcmd 12345 help GC.heap_dump` của JDK cụ thể. Tạo heap dump có thể đòi hỏi dung lượng lớn, ảnh hưởng hiệu năng và lưu lại nhiều nội dung bộ nhớ.

**Heap dump có thể chứa mật khẩu/token/PII/cached documents** dưới dạng `String`, `byte[]`, object graphs, retained buffers. Việc che logs **không làm sạch heap dump**.

Các nguy cơ khác:

- `-XX:+HeapDumpOnOutOfMemoryError` có thể tự tạo file khi OOME nếu đã bật, nên không bật bừa mà thiếu nơi lưu trữ/phân quyền.
- `-XX:HeapDumpPath=...` cần được cấu hình cùng chính sách thư mục và disk quota nếu sử dụng dump-on-OOME.
- Core dumps do OS có thể chứa nhiều native memory/process state; cần chính sách riêng.
- Các crash reports `hs_err_pid...log` có thể tiết lộ đường dẫn, JVM flags, system info và một số memory/native details, tùy tình huống.
- Class histogram thường ít trực tiếp hơn heap dump, nhưng vẫn có thể bộc lộ cấu trúc class hoặc quy mô dữ liệu nhạy cảm. Vẫn phải xem xét quyền và retention.

### 9.4. Không copy tệp chẩn đoán sang nơi không được phép

Bất kỳ file `.jfr`, `.hprof`, core dump hoặc support bundle nào cần:

1. Phê duyệt thu thập với mục đích rõ.
2. Chỉ định chủ sở hữu và quyền truy cập hạn chế.
3. Đường dẫn lưu trữ và truyền tải được bảo vệ.
4. Mã hóa khi lưu/truyền theo policy.
5. Thời hạn giữ và hủy cụ thể.
6. Redaction/sanitization được đánh giá nếu phải chia sẻ ra ngoài.
7. Audit access/download/transfer.
8. Không đưa lên public gist, ticket mở, chat bên thứ ba hoặc repository.
9. Có quy trình xử lý sự cố nếu phát hiện data exposure.

## 10. Command line, environment và system properties

Một số thông tin không xuất phát từ application logger nhưng vẫn xuất hiện trong công cụ chẩn đoán.

### 10.1. Không truyền secret trực tiếp trong JVM command line

Không nên:

~~~bash
# KHÔNG AN TOÀN: giá trị minh họa, không phải secret thật.
java -Ddb.password=example-only-secret -jar app.jar
~~~

Các process arguments hoặc JVM flags có thể xuất hiện trong công cụ quản trị, runtime inspection, support bundles và crash reports tùy môi trường. Việc truyền qua dòng lệnh còn có thể để lại shell history hoặc process metadata.

Nên dùng cơ chế quản lý secret được hỗ trợ bởi hạ tầng và **không log lại kết quả**. Dùng env vars cũng cần thận trọng: không phải “đưa vào environment thì không ai có thể đọc”, vì process inspection, container configs, dumps và debug tools có thể lộ dữ liệu.

### 10.2. `jcmd VM.command_line` là dữ liệu phải hạn chế

Ví dụ:

~~~bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
~~~

Những lệnh này hữu ích để kiểm tra JVM config, nhưng output có thể chứa **thông tin nội bộ hoặc giá trị từ arguments**. Không copy toàn bộ ra ticket công khai; review trước khi chia sẻ.

### 10.3. URL và query string

Nếu full URL có signed token:

~~~text
https://example.invalid/download?token=<secret>
~~~

đưa URL đó vào exception message, log HTTP client hoặc tracing attributes có thể làm rò rỉ. Nên ghi **HTTP method, route template, status code, duration** và một mã lỗi chuẩn hóa; tránh query string hoặc auth headers raw.

## 11. Bảo vệ đường đi log và file từ đầu tới cuối

Dữ liệu chẩn đoán thường đi theo chuỗi:

~~~text
Application logger / JVM tool
      |
      v
Console or file
      |
      v
Container runtime / agent
      |
      v
Collector / broker
      |
      v
Index / storage / dashboard
      |
      v
Alerts / export / support system
~~~

Tại mỗi hop, hỏi:

- Ai đọc được?
- Có được chuyển sang tài khoản hoặc vùng địa lý khác không?
- Có lưu trữ cả raw log lẫn phiên bản đã được redact không?
- Tồn tại bao lâu?
- Tài khoản máy/agent có quyền lớn đến đâu?
- Có thể truy hồi và xóa theo chính sách không?
- Đã có audit truy cập và phát hiện download bất thường chưa?

### Defense in depth

- **Ở ứng dụng:** allowlist fields, reason codes, validation, không log secrets.
- **Ở instrumentation/collector:** dropping/masking nhạy cảm theo schema, đánh giá rules với test cases.
- **Ở lưu trữ:** role-based access, least privilege, encryption, retention.
- **Ở dashboard/alerts:** không để raw body/token trong notifications hoặc query URLs.
- **Ở support workflow:** xem xét classification và secure transfer trước khi chia sẻ.
- **Ở CI/testing:** secret-canary tests, static checks cho `toString()`/`getMessage()`/`printStackTrace()` trong hot paths.

**Lưu ý:** một secret đã được đưa vào log agent hoặc stream buffer từ trước khi filter chạy **có thể đã được sao chép**. Không được hứa rằng “chúng tôi có filter sau collector” nghĩa là mọi bản sao đều được xóa.

## 12. Chương trình Java 17+ hoàn chỉnh: chỉ phát thông điệp chẩn đoán đã duyệt

Mục tiêu: minh họa một API chỉ nhận **enum** cho operation/reason và ID đã kiểm tra cú pháp. Chương trình cố tình **không** in password, token, raw exception message hoặc request object. Nó cũng minh họa loại bỏ một request ID có ký tự xuống dòng (log forging) và xóa vùng `char[]` do chương trình chủ động sở hữu sau khi dùng.

Lưu file **`SafeDiagnosticDemo.java`**:

~~~java
import java.util.Arrays;

public final class SafeDiagnosticDemo {
    private enum Operation {
        LOGIN, PAYMENT
    }

    private enum FailureCode {
        AUTH_REJECTED, UPSTREAM_TIMEOUT
    }

    // Client-supplied IDs không tin cậy, dù đã có trace context.
    private static String safeRequestId(String candidate) {
        if (candidate != null
                && candidate.matches("[A-Za-z0-9_-]{1,32}")) {
            return candidate;
        }
        return "invalid";
    }

    private static String diagnostic(
            Operation operation, FailureCode reason, String requestId) {
        return "event=operation_failed"
                + " operation=" + operation.name()
                + " reason=" + reason.name()
                + " request_id=" + safeRequestId(requestId);
    }

    // Thông báo công khai không lấy Throwable.getMessage().
    private static String publicError(FailureCode code) {
        switch (code) {
            case AUTH_REJECTED:
                return "Unable to authenticate";
            case UPSTREAM_TIMEOUT:
                return "Service temporarily unavailable";
            default:
                return "Request failed";
        }
    }

    public static void main(String[] args) {
        char[] transientSecret = {'d', 'e', 'm', 'o'};

        // Không truyền transientSecret, DTO, hay Throwable tới logger.
        String accepted = diagnostic(
                Operation.LOGIN, FailureCode.AUTH_REJECTED, "req_42");
        System.out.println(accepted);

        // Dòng xuống dòng bị loại khỏi toàn bộ diagnostic field.
        String attackerSupplied = "req_42\nlevel=INFO";
        String rejected = diagnostic(
                Operation.LOGIN, FailureCode.AUTH_REJECTED,
                attackerSupplied);
        System.out.println(rejected);

        System.out.println(
                "newline_in_record=" + rejected.contains("\n"));
        System.out.println(
                "public_error=" + publicError(FailureCode.AUTH_REJECTED));

        // Xóa mảng do mình sở hữu khi không còn cần.
        Arrays.fill(transientSecret, '\0');
        System.out.println(
                "owned_char_array_cleared="
                        + (transientSecret[0] == '\0'));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac SafeDiagnosticDemo.java
java SafeDiagnosticDemo
~~~

**Stdout xác định của chương trình:**

~~~text
event=operation_failed operation=LOGIN reason=AUTH_REJECTED request_id=req_42
event=operation_failed operation=LOGIN reason=AUTH_REJECTED request_id=invalid
newline_in_record=false
public_error=Unable to authenticate
owned_char_array_cleared=true
~~~

### Giải thích cơ chế

1. `Operation` và `FailureCode` là enums nên không thể nhận arbitrary secret string qua API `diagnostic`.
2. `safeRequestId` chỉ chấp nhận ID dài 1–32 ký tự ASCII từ tập `A–Z`, `a–z`, `0–9`, `_` hoặc `-`. Không có whitespace/control chars.
3. Giá trị `req_42\nlevel=INFO` không được in nguyên văn; được thay bằng giá trị kiểm soát `invalid`.
4. `publicError` trả message cố định, không lấy text từ exception hoặc upstream.
5. `Arrays.fill(transientSecret,'\0')` xóa **mảng char[] hiện đang sở hữu**.
6. Kết quả stdout không phụ thuộc ngày giờ, ngẫu nhiên, JDK vendor hoặc mạng.

### Giới hạn quan trọng của demo

- `System.out.println` dùng để **minh họa nội dung record**; production nên dùng structured logger/encoder, retention, export controls và centralized access policy.
- Enum whitelist giúp API khó ghi raw fields, nhưng developer vẫn có thể tạo logger khác hoặc ghi ra stdout nơi khác. Cần code review và automated tests.
- `safeRequestId` chọn cách **reject ID sai**. Nếu muốn ghi hash/pseudonymization phải dùng chính sách riêng và thuật toán phù hợp; không được hash bừa mà coi đã anonymous.
- `char[]` giảm khả năng giữ secret không thể xóa chủ động so với `String`, **nhưng không bảo đảm xóa mọi bản sao**, không xóa những `String` hoặc native copies có thể đã được tạo. Hơn nữa, JIT/OS/runtime có thể giữ dữ liệu ngoài phạm vi mảng đó.
- Không dùng `transientSecret` trong bất kỳ cryptographic/authentication operation nào: đây chỉ là mảng giả để minh họa lifecycle.
- Một attacker ID bị thay thành `invalid` có thể làm mất correlation, vì vậy nên sinh **server request ID riêng** và giữ client ID trong trường isolated/validated nếu thực sự cần.
- Phần mềm production phải dùng permissions, encryption, audit và retention ở log pipeline; không thể giải quyết tất cả bằng một helper method.

### Tương thích Java 15

Code chỉ dùng Java APIs ổn định, không cần records hoặc preview. Trên JDK compiler hỗ trợ target 15:

~~~bash
javac --release 15 SafeDiagnosticDemo.java
~~~

Bài học mô tả một cách viết hiện đại có thể biên dịch từ Java 15; việc chạy trên JDK17+ tránh phụ thuộc bản JDK 15 đã qua thời gian hỗ trợ của nhiều nhà phân phối.

## 13. Thiết kế kiểm thử không làm lộ secret trong chính test

Một số test fixtures nên chứa chuỗi **giả**, dễ phát hiện nếu xuất hiện ở sai vị trí:

~~~text
SECRET_CANARY_DO_NOT_LOG_92846
FAKE_BEARER_CANARY_92846
USER_EMAIL_CANARY@example.invalid
~~~

Đây là **marker thử nghiệm**, không phải secret thật. Dùng chúng để kiểm tra chẩn đoán không phát tán.

### 13.1. Unit tests cho event schema

- Event chỉ chứa đúng các field trong allowlist.
- Không có field `password`, `authorization`, `cookie`, `secret`, `rawBody`.
- Mã lỗi là enum; unknown reason map về mã được kiểm soát.
- Request ID không có CR/LF, tab, dấu phân cách nguy hiểm hoặc Unicode controls.
- Chuỗi vượt max length được reject hoặc xử lý theo policy.
- Không có exception/cause raw trong output.
- Những trường cần ghi như duration/status đúng kiểu số, có range.

### 13.2. Integration tests cho logging pipeline

Một test tốt có thể:

1. Gửi request thử nghiệm với dữ liệu marker `SECRET_CANARY_DO_NOT_LOG_92846`.
2. Kích hoạt các lỗi điển hình: invalid input, auth failure, DB timeout, HTTP 4xx/5xx.
3. Thu **console logs, agent logs, exported structured logs và tracing spans** từ môi trường test.
4. Đảm bảo marker **không xuất hiện** trong các đầu ra chẩn đoán không được phép.
5. Kiểm tra error response trả cho client không chứa stack trace hoặc path nội bộ.
6. Thử input CR/LF, JSON escaped chars và chuỗi dài để phát hiện log injection/DoS.
7. Test khi framework tự serializes exception/DTO.
8. Test multi-service propagation của tracing baggage.
9. Test log sample/alert/notification pipelines.
10. Nếu tạo JFR/heap dump cho điều tra, gắn nhãn restricted và kiểm tra kênh bảo vệ, **không công bố raw artifact như kết quả test thông thường**.

### 13.3. Test ở cả debug và production configuration

Rò rỉ có thể chỉ xuất hiện khi bật:

- `DEBUG` hoặc `TRACE` của HTTP clients;
- SQL parameter tracing;
- HTTP wire dumps;
- Error stack trace chi tiết;
- JFR profile hoặc custom events;
- Full request/response logging tại reverse proxy/gateway.

Do đó tests phải bao phủ **các chế độ chẩn đoán cho phép vận hành**, không chỉ log level mặc định.

## 14. Quy trình xử lý sự cố: vừa có bằng chứng, vừa bảo vệ dữ liệu

Khi service gặp lỗi thật, một runbook nên đi theo:

### Bước 1 — Tạo correlation ID có kiểm soát

Lấy ID server-generated hoặc đã validate. Đừng đưa session token vào incident ticket chỉ để liên kết logs.

### Bước 2 — Thu thập mức thấp nhất đủ chẩn đoán

Bắt đầu bằng **error code, count, timing, affected component, status, version**. Không thu cả body/headers nếu không cần.

### Bước 3 — Xác nhận quyền và mục đích của mức chi tiết cao hơn

Nếu cần stack trace/JFR, ghi ai yêu cầu, thời điểm, khoảng thời gian và scope. Nếu cần heap dump hoặc core dump, áp process duyệt cao hơn do nguy cơ chứa nội dung bộ nhớ.

### Bước 4 — Dùng đường truyền và lưu trữ hạn chế

Đặt artifacts ở private storage, least privilege, access logs, encryption và TTL. Không tự động attach heap dump vào email hoặc gửi lên công cụ hỗ trợ ngoài tổ chức.

### Bước 5 — Phân tích và phát hành bản tóm tắt đã làm sạch

Bản tóm tắt nên nêu:

~~~text
Incident: API authentication failures
Time window: approved interval
Error code: AUTH_REJECTED
Affected service: auth-service
Request IDs: approved internal identifiers
Root cause: configuration mismatch
Action: rotate config and add validation
~~~

Không cần đưa password, token, full headers, request body hoặc stack trace nguyên văn vào postmortem phổ biến.

### Bước 6 — Hủy artifact và kiểm tra bản sao

Thực thi chính sách retention/deletion của logs, recordings, dumps, local downloads và ticket attachments. Những bản sao qua CI/cache/backup có thể có vòng đời riêng; không tuyên bố đã xóa sạch nếu chưa xác minh.

## 15. Khi có sự cố rò rỉ dữ liệu qua log

Nếu phát hiện secret đã được log, **không chỉ thêm regex redaction rồi đóng sự cố**.

Các hành động theo kế hoạch bảo mật:

1. **Ngăn nguồn rò:** loại bỏ field/call path gây lộ, tắt capture nhạy cảm khi cần.
2. **Giới hạn truy cập:** tạm thời thu hẹp quyền trên log index, dashboards và exports.
3. **Xác định phạm vi:** hệ thống nhận nào, thời gian nào, dữ liệu loại gì, ai đã truy cập.
4. **Rotate/revoke credentials** có nguy cơ đã bị lộ theo policy (token, API key, password, signing secret).
5. **Xử lý dữ liệu đã tồn tại:** xóa/cách ly theo khả năng của storage/retention và quy định pháp lý.
6. **Audit downstream copies:** alerts, SIEM, error tracking, tickets, object storage, backup.
7. **Đánh giá nghĩa vụ thông báo và tuân thủ** nếu có PII/financial data.
8. **Bổ sung regression tests** với canary để tránh lặp lại.
9. **Không copy nội dung nhạy cảm vào báo cáo hậu kiểm** khi mô tả sự cố.
10. Ghi lại những điều **đã xác minh** thay vì khẳng định mọi bản sao đã bị loại bỏ.

**Hạn chế quan trọng:** rotate secret không làm các dữ liệu cá nhân từng lộ biến mất. Vì vậy không thể xử lý mọi rò rỉ chỉ bằng credential rotation.

## 16. Những sai lầm cần loại bỏ

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| Log cả `request`/DTO bằng `toString()` | Có thể gồm password, token, PII | Allowlist trường và custom safe diagnostic schema |
| Log `exception.getMessage()` raw | Thư viện có thể đưa secret vào message | Stable reason code và restricted exception policy |
| Log `Throwable` vào mọi trường hợp | Cause/suppressed chứa thông tin nhạy cảm | Chỉ log restricted stack khi được duyệt |
| Trả stack trace cho HTTP client | Lộ paths, class names, internals và thông điệp lỗi | Public error code + opaque request ID |
| Copy `Authorization`/`Cookie` header | Lộ bearer/session credentials | Không thu; nếu cần chứng minh header có/không, chỉ log boolean/code |
| Chỉ mask `password=` bằng regex | Bỏ qua token trong JSON, URL, exceptions | Allowlist trước, filter bổ sung sau |
| Ghi email vào metrics label | PII và high cardinality | Low-cardinality code/operation label |
| Đưa token vào tracing baggage | Có thể tự propagate ra downstream | Baggage chỉ chứa thông tin cho phép, không secret |
| Sampling 1% coi như an toàn | Vẫn có thể xuất secret ở 1% | Sanitization trước sampler |
| Lấy client requestId làm quyền hạn | ID không phải authentication | Validate và tách authorization |
| Nối trực tiếp user text vào text log | CR/LF log forging | Escaping/validation và structured format |
| Dùng `println(secret)` lúc debug rồi quên | Console vẫn được log aggregator thu | Cấm ghi secret ngay cả trong debug |
| Đưa database password qua `-D...` | Có thể lộ trong arguments/diagnostics | Secret manager và không log config |
| Đăng JFR lên public issue | Recording có thể mang internals/sensitive fields | Restricted artifact + review |
| Gửi heap dump qua email | Heap có thể chứa token, PII, key | Secure transfer, approval, TTL |
| Nghĩ JFR luôn không có nhạy cảm | Custom events/system info có thể chứa giá trị | Review event settings và field schema |
| Nghĩ stack trace luôn in locals | Không đúng với stack trace thông thường | Phân biệt stack trace với heap/debug dumps |
| Bật dump-on-OOME không có storage policy | Tự tạo .hprof chứa dữ liệu bí mật | Secure path, permissions, quota, retention |
| Chỉ xóa log index sau sự cố | Downstream/cache/backup vẫn có bản sao | Incident response toàn pipeline |
| Để log retention “vô hạn cho tiện” | Mở rộng exposure và chi phí | Retention theo purpose và policy |
| Dùng hash email thuần để ẩn danh | Dễ dictionary attack, vẫn liên kết cá nhân | Random ID hoặc HMAC với key và mục đích rõ |
| Rely vào logging framework để tự che tất cả | Encoder không biết business sensitivity | Application policy và schema |
| Chỉ test log level INFO | DEBUG/TRACE/auto-instrumentation vẫn lộ | Test mọi diagnostic mode được phép |

## 17. Checklist triển khai cho ứng dụng Java hiện đại

- [ ] Có phân loại dữ liệu và danh sách field **không bao giờ log raw**.
- [ ] Định nghĩa event schema allowlist cho các lỗi quan trọng.
- [ ] Dùng `reason_code`/`operation` ổn định, không copy exception message.
- [ ] Dùng server-generated hoặc validated correlation IDs; không là session secrets.
- [ ] HTTP/gRPC responses không xuất stack traces, token, DSN hoặc internal config.
- [ ] Không serialize nguyên request/response/DTO có sensitive fields.
- [ ] Structured logger escape dữ liệu theo sink; input được validate/bounded.
- [ ] Bảo vệ log injection, newline/control chars và oversized values.
- [ ] Không đưa secrets/PII vào metric labels, span attributes, tracing baggage.
- [ ] Auto-instrumentation được kiểm soát với HTTP/JDBC/ORM/errors.
- [ ] JFR custom events dùng allowlisted fields; recordings là restricted.
- [ ] Heap/core dumps, hs_err files có access/retention policy nghiêm ngặt.
- [ ] Không bật `HeapDumpOnOutOfMemoryError` khi chưa có storage security.
- [ ] Tránh truyền secrets qua JVM arguments hoặc log environment/config.
- [ ] Log pipeline có authentication, RBAC, encryption, TTL và audit.
- [ ] Tickets/alerts/support bundles dùng bản tóm tắt đã kiểm tra nội dung.
- [ ] Canaries và integration tests phát hiện sensitive markers ở mọi sink.
- [ ] DEBUG/TRACE policies có thời hạn, scope và phê duyệt.
- [ ] Có runbook xử lý log exposure, credential rotation, data deletion.
- [ ] Khi bắt buộc điều tra sâu, chọn **mức thu thập tối thiểu** đủ trả lời câu hỏi.

## 18. Bài tập có đáp án

**Bài 1.** `Throwable.printStackTrace()` có thể tiết lộ secret không nếu source code không viết `logger.info(password)`?

**Đáp án:** Có. Exception message/cause/suppressed exceptions do thư viện hoặc code khác tạo ra có thể đã mang secret. In toàn bộ throwable có thể chuyển dữ liệu đó tới log.

**Bài 2.** Parameterized logging như `logger.info("{}", request)` có tự xóa password trong `request` không?

**Đáp án:** Không. Framework vẫn có thể gọi `toString()` hoặc encoder serialize DTO. Phải kiểm soát field ngay tại source.

**Bài 3.** Có nên dùng email đầy đủ làm correlation ID không?

**Đáp án:** Không nếu không cần. Dùng random request ID server-generated. Nếu phải liên kết cùng account, cân nhắc pseudonymization và privacy policy; email raw là dữ liệu cá nhân.

**Bài 4.** Một request ID có `\nlevel=INFO` có thể tạo lỗi gì?

**Đáp án:** Log injection/forging khi nối vào unstructured line log. Validate ID và escape đúng format.

**Bài 5.** Vì sao metrics label chứa `token=...` nguy hiểm dù dashboard chỉ cho nội bộ?

**Đáp án:** Metrics được lưu, replicate, export và có thể truy cập bởi nhiều hệ thống/tài khoản. Secret có thể bị phát tán và lưu dài; không ghi token vào label.

**Bài 6.** Sampling 0,1% traces có thay sanitization không?

**Đáp án:** Không. Chỉ một sampled trace có secret cũng là rò rỉ. Phải lọc trước khi sampling/export.

**Bài 7.** Vì sao OpenTelemetry baggage không nên mang password hoặc user PII?

**Đáp án:** Baggage có thể được propagate tự động qua downstream HTTP headers, thậm chí qua các boundaries không dự kiến.

**Bài 8.** Java heap dump có an toàn vì application log đã redact không?

**Đáp án:** Không. Heap có thể chứa objects/arrays/strings còn giữ credential/PII. Phải bảo vệ .hprof riêng.

**Bài 9.** Vì sao không đưa password trong `-Ddb.password=...`?

**Đáp án:** JVM arguments/process configuration có thể hiện trong tools, crash reports hoặc support bundles, nên cần secret management thay thế.

**Bài 10.** `Throwable.getStackTrace()` mặc định có xuất toàn bộ local variables không?

**Đáp án:** Không. Stack trace chủ yếu mô tả frames; nhưng message/cause/class/method/files vẫn có thể nhạy cảm. Heap/debug tools có phạm vi dữ liệu khác.

**Bài 11.** Chỉ dựa vào regex `password=[^ ]+` để mask đủ không?

**Đáp án:** Không. Tên field, encoding, JSON, URL, stack trace và downstream exports đa dạng. Dùng allowlist event fields trước.

**Bài 12.** Mỗi lần auth thất bại, nên log raw username/email để thuận tiện tìm kiếm không?

**Đáp án:** Mặc định không. Ghi operation/reason/request ID. Nếu cần identity cho security audit, áp purpose, access và retention policy riêng.

**Bài 13.** `Arrays.fill(charArray, '\0')` có bảo đảm secret biến mất khỏi mọi bản sao memory không?

**Đáp án:** Không. Nó chỉ ghi đè mảng đang sở hữu; Strings/copies/native memory và GC snapshots trước đó có thể giữ bản sao.

**Bài 14.** Nếu JFR chỉ bật `settings=default`, có thể chia sẻ công khai không?

**Đáp án:** Không. Recording có thể chứa stack/thread/JVM/system information hoặc custom events nhạy cảm; cần review và xử lý restricted.

**Bài 15.** Nên đưa nguyên chuỗi SQL/DB URL vào error response khi DB timeout để client tự debug không?

**Đáp án:** Không. Trả stable error code và request ID; server điều tra qua kênh hạn chế, không gửi internal DSN/query tới client.

**Bài 16.** Khi phát hiện access token bị log, chỉ xóa regex output là đủ chưa?

**Đáp án:** Chưa. Cần ngăn nguồn rò, giới hạn access, rotate/revoke token và rà soát bản sao downstream theo incident plan.

**Bài 17.** Vì sao không được coi trace ID từ request là bằng chứng user đã được xác thực?

**Đáp án:** Trace/request ID chỉ để correlation, có thể do client cung cấp hoặc giả mạo. Authorization phải dùng identity/credential validation riêng.

**Bài 18.** Tại sao một heap dump có thể cần quy trình phê duyệt chặt hơn GC log thông thường?

**Đáp án:** Heap dump có thể chứa nội dung trực tiếp của object graphs/arrays, bao gồm credential/PII. Rủi ro disclosure lớn hơn một tập metrics/GC events đã giới hạn.

## 19. Tài liệu chính thức, còn áp dụng

- **OWASP Logging Cheat Sheet — Data to Exclude, Log Injection, Verification:** https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **Oracle Java SE 17 — `Throwable` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
- **Oracle Java SE 17 — `java.util.logging.Logger` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- **Oracle JDK 25 Troubleshooting Guide — Diagnostic Tools, JFR, jcmd, heap dumps:** https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html
- **Oracle JDK 17 Troubleshooting Guide — Diagnostic Tools:** https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- **Oracle Java SE 17 — `jdk.jfr.Event` API:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html
- **Oracle JDK 25 — `jcmd` tool specification:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html
- **OpenTelemetry — Baggage and security considerations:** https://opentelemetry.io/docs/concepts/signals/baggage/
- **OpenTelemetry — Semantic conventions for sensitive attributes:** https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/
- **CWE-117 — Improper Output Neutralization for Logs:** https://cwe.mitre.org/data/definitions/117.html

**Kết luận:** kiểm soát dữ liệu nhạy cảm trong chẩn đoán Java phải bắt đầu **trước khi ghi**: dùng allowlist diagnostic fields, stable reason codes, correlation ID an toàn, không log raw requests, Throwable messages/cause, tokens hoặc PII. Bảo vệ cùng nguyên tắc cho logs, traces, metrics, JFR và heap/core dumps; thêm validation/escaping chống log injection, quyền truy cập tối thiểu, mã hóa, retention và kiểm thử canary. Khi cần điều tra sâu, thu **đúng lượng dữ liệu cần thiết** và bảo vệ artifact theo mức nhạy cảm thực tế. Một hệ thống vừa **chẩn đoán được lỗi** vừa **không tạo điểm rò thông tin mới** là mục tiêu của thiết kế này.
