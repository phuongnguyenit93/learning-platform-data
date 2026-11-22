# Tác động của tuần tự hóa JSON, nén và ghi log tới chi phí mỗi yêu cầu

> **Module:** Spring Boot - web-runtime · **Nhóm:** Hiệu năng và giới hạn. Một HTTP request không chỉ tốn thời gian ở controller hay database. Khi trả JSON, server còn phải tạo object graph, chuyển các object thành bytes, có thể nén response, ghi log/metrics/traces và đẩy bytes qua network. Bài phân tích **chi phí CPU, allocation/GC, latency, throughput, băng thông và bộ nhớ** của ba công đoạn **tuần tự hóa JSON, HTTP compression và logging**; đưa ra phép đo thực nghiệm, tiêu chí tối ưu và mã Spring Boot **4.1.2 / Java 17+**. Ví dụ dùng **Spring MVC/Tomcat, Jackson 3, SLF4J/Logback, Actuator/Micrometer**, và giải thích các điểm tương ứng của WebFlux.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Vẽ đường đi response từ controller qua **HttpMessageConverter/Jackson**, HTTP server compression, socket, proxy đến client và xác định công đoạn nào nằm trong request latency.
2. Giải thích vì sao một endpoint trả 200 với truy vấn database nhanh vẫn có thể chậm hoặc quá tải do **JSON serialization**, byte array/buffer, nén GZIP hoặc logger.
3. Phân biệt kích thước object graph trong heap, JSON UTF-8 chưa nén, compressed bytes trên wire và số bytes của log record.
4. Hiểu thay đổi ở **Spring Boot 4.x**: **Jackson 3** là mapper mặc định, auto-config **`tools.jackson.databind.json.JsonMapper`**; không sao chép mặc định `com.fasterxml.jackson.databind.ObjectMapper` của Boot 3.x vào code Boot 4.
5. Dùng `server.compression.enabled`, `server.compression.min-response-size`, `server.compression.mime-types` để thử tác động nén, hiểu `Accept-Encoding`/`Content-Encoding`, chi phí CPU và trade-off payload nhỏ/lớn.
6. Dùng logging levels, **SLF4J parameterized logging**, giới hạn nội dung log, structured logging hoặc async appenders đúng cách, không log raw bodies/tokens.
7. Tạo dự án Spring Boot 4.1.2 chạy được với endpoint JSON có kích thước có kiểm soát; đo bốn biến thể compression/logging bằng cURL, Actuator và profiler.
8. Tránh những kết luận đo sai: `System.nanoTime()` trong controller **không tự đo giai đoạn serialize sau khi method return**, một `curl` đơn lẻ không phải benchmark, compression có thể không xảy ra nếu client không yêu cầu hoặc MIME/body không đạt điều kiện.
9. Đặt ngân sách chi phí theo request, SLO p95/p99, bytes/response, request rate, CPU/request và log volume; tối ưu theo evidence thay vì tắt toàn bộ logs hoặc tăng compression vô điều kiện.

## 2. Một request Spring Boot tiêu tốn những nguồn lực nào?

Đường đi tiêu biểu của Spring MVC REST API:

~~~text
HTTP request đến
   |
   v
Tomcat connector / request threads
   |
   +-- Servlet filters, Spring Security, observation
   |
   v
DispatcherServlet -> @RestController
   |
   +-- gọi service/database/cache
   +-- xây object graph/DTO
   +-- ghi application logs (nếu có)
   |
   v
HttpMessageConverter
   |
   +-- Jackson 3: Java objects -> JSON UTF-8 bytes
   +-- có thể tạo buffers/allocations
   |
   v
Servlet response / HTTP compression (khi đủ điều kiện)
   |
   +-- GZIP/deflate chiếm CPU và bộ đệm
   |
   v
socket/TLS/TCP -> proxy -> client
   |
   +-- client giải nén và parse JSON tiếp
   |
   v
HTTP response hoàn tất / observation metrics
~~~

Mô hình khái niệm để phân tích **một request**:

~~~text
T_total ≈ T_queue + T_request_read + T_decode + T_business
        + T_json_encode + T_compress + T_output_wait
        + T_other_filters + T_logging_critical_path

CPU_per_request ≈ CPU_parse + CPU_business + CPU_json
                + CPU_compression + CPU_log_formatting
                + CPU_TLS + CPU_framework

Memory_pressure ≈ object_graph + JSON_buffers + gzip_buffers
                + log_queue + framework_buffers + in_flight_requests
~~~

Các thành phần **có thể chồng lắp** trong streaming, async I/O hoặc HTTP/2; đây là sơ đồ ngân sách, **không phải công thức đo chính xác** để cộng các counter độc lập. `T_output_wait` có thể bao gồm backpressure/socket write hoặc thread bị block; CPU thấp không nhất thiết chứng minh response rẻ nếu mạng/đầu nhận chậm.

### 2.1. Cùng một request có ba loại kích thước

Giả sử service trả 5.000 record:

| Khái niệm | Ví dụ | Ai tiêu tốn? |
| --- | --- | --- |
| Java object graph | 5.000 records, Strings, Lists | Heap, allocation, GC |
| JSON UTF-8 | 1,2 MiB chưa nén (minh họa) | Encoder, buffers, HTTP write |
| GZIP response | 140 KiB nếu lặp nhiều (minh họa) | CPU nén; network thấp hơn |
| Log event | 1 dòng tóm tắt hoặc 5.000 dòng per item | CPU format, queue, stdout/file, log backend |
| Client decode | Giải GZIP, parse JSON | CPU/heap phía client |

Các số dung lượng trong bảng **chỉ là kịch bản minh họa**, không phải kết quả chạy code của bài. Tỷ lệ nén phụ thuộc phân phối ký tự, trùng lặp, kích thước, header, thuật toán, mức nén và thư viện. Có dữ liệu chứa chuỗi ngẫu nhiên/binary Base64 rất khó nén và JSON lặp schema nhiều lần rất dễ nén.

### 2.2. Amdahl: tối ưu không đúng chỗ ít hiệu quả

Nếu database chiếm 95% request time và JSON chỉ chiếm 2%, tối ưu serialization nhanh gấp đôi chỉ giảm lý tưởng khoảng **1%** thời gian request trong điều kiện không có thành phần khác thay đổi. Ngược lại, với response vài MiB và DB cache hit, JSON/gzip có thể là phần lớn CPU. Vì vậy cần **profiling và A/B** trước.

Cũng không thể chỉ hỏi “nén tốt hơn hay không”: GZIP có thể giảm thời gian truyền với băng thông hạn chế nhưng làm tăng CPU server, từ đó giảm requests/second khi CPU bão hòa. **Latency một client** và **throughput cả cluster** có thể phản ứng ngược nhau.

## 3. Tuần tự hóa JSON: những gì xảy ra sau khi controller trả object

Một Spring REST controller:

~~~java
@GetMapping("/api/orders")
public List<OrderDto> orders() {
    return orderService.listOrders();
}
~~~

Đoạn này là **fragment**: các type `OrderDto` và `orderService` do ứng dụng cung cấp. Controller trả **Java objects**; response chưa phải JSON tại dòng `return`. Spring MVC chọn một `HttpMessageConverter` phù hợp (thường Jackson JSON converter) để serialize object graph thành JSON.

### 3.1. Jackson 3 là mặc định của Spring Boot 4.1

Spring Boot 4.x mặc định tích hợp **Jackson 3** từ starter JSON; khi có Jackson phù hợp classpath, Boot cấu hình bean `JsonMapper`. Package chính dùng trong ví dụ Jackson 3:

~~~java
// Fragment dùng khi thật sự cần thao tác trực tiếp với mapper.
import tools.jackson.databind.json.JsonMapper;
~~~

Trong Spring Boot 3.x, nhiều hướng dẫn nhắc `com.fasterxml.jackson.databind.ObjectMapper` (Jackson 2). Spring Boot 4.x còn có đường hỗ trợ Jackson 2 để chuyển đổi, nhưng **đã đánh dấu deprecated** và không nên mặc định trộn API/version. Để trả JSON trong controller, thường **không cần new JsonMapper**: dùng auto-configured converter và để Boot quản lý modules/defaults.

### 3.2. Nguồn CPU của serialization

Jackson chuyển object graph thành byte stream qua serializer, có các chi phí:

1. Truy cập fields/getters/records qua metadata/serializer đã được chuẩn bị.
2. Duyệt collections/maps, giá trị null, nested objects, generic types.
3. Định dạng số, timestamps, enum và các dạng dữ liệu đặc biệt.
4. Escape ký tự đặc biệt, quote JSON, encode Unicode thành UTF-8.
5. Xử lý custom serializers, filters, mixins, polymorphism hoặc reflective operations.
6. Ghi bytes vào buffer/response output; tạo allocations phụ thuộc mapper/converter và output path.
7. Nếu code tự gọi `writeValueAsString` trước khi trả response, còn tạo thêm String trung gian trước khi HTTP converter có thể serialize một lần nữa.

Một endpoint trả 100 records khác đáng kể so với 100.000 records, kể cả business logic/DB như nhau. Kết quả không nên được đo bằng thời gian method controller riêng, vì JSON writing có thể xảy ra **sau khi method return**.

### 3.3. Object graph ảnh hưởng cả trước khi serialize

Một entity JPA chứa 10 lazy relationships có thể kích hoạt N+1 queries khi serializer gọi getters, tùy session/lazy-loading configuration; hoặc fail do session đã đóng/cycle. Nếu trả entity trực tiếp:

- Có nguy cơ lộ fields không định đưa vào API.
- Lazy association có thể tạo nhiều DB queries/allocations.
- Cyclic references làm serializer đệ quy hoặc phải dùng annotation phức tạp.
- Serialization time khó đoán theo độ sâu graph.
- Tính đúng đắn của response phụ thuộc entity mappings.

Ưu tiên DTO/record định hình response có **kích thước, độ sâu và số phần tử có bounds**. Có thể phân trang/cursor với endpoint trả danh sách lớn, chỉ chọn fields cần thiết, batch database queries và tránh object graphs quá sâu.

### 3.4. Trước/sau: payload quá lớn

Không nên:

~~~java
// Fragment minh họa anti-pattern.
@GetMapping("/api/all-orders")
public List<OrderEntity> allOrders() {
    return repository.findAll(); // có thể trả vô hạn rows/entity graph
}
~~~

Nên:

~~~java
// Fragment minh họa, cần service/cursor DTO thực trong ứng dụng.
@GetMapping("/api/orders")
public OrderPage page(@RequestParam(defaultValue = "100") int limit) {
    int safeLimit = Math.max(1, Math.min(limit, 500));
    return orderService.fetchPage(safeLimit);
}
~~~

Mục tiêu là **bound response data trước khi Jackson xử lý**. Một JSON response nhỏ hơn có thể giảm **DB read, allocations, bytes nén, network write, client parsing và chi phí log nếu log payload** cùng lúc.

### 3.5. Các tối ưu JSON cần đánh giá bằng phép đo

| Phương án | Lợi ích có thể có | Rủi ro/trade-off |
| --- | --- | --- |
| Dùng DTO nhỏ, phân trang | Giảm số object, JSON bytes, query load | Thay đổi API contract, cần cursor/links |
| Bỏ trường không cần thiết | Giảm CPU encode và egress | Có thể phá tương thích client |
| Giữ mapper/serializer tái sử dụng | Tránh setup/metadata mỗi request | Configuration thread-safety; không mutate mapper lúc đang chạy |
| Chỉ tạo đúng fields được yêu cầu | Giảm allocations và depth | Kiểm authorization field-level |
| Serialize theo streaming khi thích hợp | Giảm peak memory và time-to-first-byte | Error handling khi response đã gửi, backpressure, client semantics |
| Chuyển bulk transfer sang binary protocol | Có thể giảm CPU/bytes | Complexity, browser/tooling/contracts |
| Cache JSON bytes ở layer phù hợp | Giảm serialize lặp lại cho cùng representation | TTL/invalidation, auth, Content-Encoding/Vary |
| Tùy chỉnh serializer | Xử lý domain/định dạng hiệu quả hơn | Có thể tạo bug, cần JMH/profile |
| Bỏ pretty-print trong API lớn | Bớt whitespace bytes | Gọn JSON không bảo đảm CPU luôn nhanh |
| Giảm số chữ số/precision theo schema | Có thể giảm bytes và compute | Không tùy tiện mất độ chính xác tài chính |

Không sao chép một “fast serialization trick” mà chưa profile với **JDK/version/DTO/schema thật**. Thay mapper, bật Afterburner, chuyển Jackson 2/3 hay custom deserializer có tác động tương thích; mọi thay đổi phải test JSON contract.

## 4. Nén HTTP: ít bytes hơn nhưng CPU thường cao hơn

Nén response là một công đoạn **sau khi đã có dữ liệu biểu diễn JSON/text**. Nó thường giảm lượng bytes gửi qua network, có thể giúp tổng latency khi băng thông đắt hoặc RTT cao, nhưng phải trả thêm chi phí CPU và buffers.

### 4.1. Điều kiện nén

Các phần liên quan:

~~~http
GET /api/report?count=1000 HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
~~~

Server chỉ nên trả response GZIP nếu negotiation, content type, size, status, connector và cấu hình đều cho phép. Khi nén:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Các headers minh họa **không bảo đảm luôn giống hoàn toàn** trong mọi container/proxy. `Content-Encoding: gzip` cho biết body payload dùng gzip. `Content-Length` nếu có có thể là kích thước compressed body, nhưng response có thể truyền chunked/HTTP2 và không có một Content-Length đã biết.

Nếu client không gửi `Accept-Encoding: gzip`, response thường **không nén** dù server.compression.enabled=true. Nếu body nhỏ, MIME không thuộc danh sách, response đã mã hóa khác hoặc connector/proxy khác, compression cũng có thể không xảy ra.

### 4.2. Spring Boot 4.1.2: cấu hình nén server

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/plain,text/html,text/css,application/javascript
~~~

Theo Spring Boot 4.1, `server.compression.enabled` mặc định là **false**; minimum response size mặc định khoảng **2 KB**; mặc định `application/json` đã thuộc MIME có thể nén. Nếu ghi property `server.compression.mime-types`, bạn đang **đặt lại danh sách**; muốn thêm MIME mới mà giữ defaults, cân nhắc `server.compression.additional-mime-types`.

Nén response được embedded server thực hiện khi hỗ trợ, ví dụ Tomcat, Jetty hoặc Reactor Netty. Đừng coi property này là phép tự động nén **request body gửi đến server**. Request decompression, proxy, client request compression có cơ chế riêng.

**Chi tiết ngưỡng:** Tài liệu mô tả dựa trên ngưỡng kích thước response/Content-Length; với streaming hoặc response không biết length sớm, behavior có thể khác theo connector. Luôn kiểm `Content-Encoding` trên response thực thay vì suy từ `server.compression.min-response-size`.

### 4.3. Tại sao response nhỏ không nên nén?

Với một JSON:

~~~json
{"ok":true}
~~~

GZIP cần header/footer và các thao tác khởi tạo/CRC/deflate. Với response vài bytes, compressed representation có thể **lớn hơn hoặc không đáng kể**. Bật nén mọi thứ có thể tăng CPU, latency và kích thước response nhỏ.

Với JSON 500 KiB có nhiều keys lặp lại, GZIP thường giảm bytes đáng kể. Nhưng nếu response chứa base64 của dữ liệu đã nén, ciphertext hoặc các chuỗi entropy cao, compression ratio có thể thấp.

### 4.4. Mức nén và CPU

| Lựa chọn | Thường có lợi | Chi phí cần đo |
| --- | --- | --- |
| Không nén | CPU rất hạn chế, LAN nhanh, body nhỏ | Tăng network bytes |
| GZIP ở mức phổ biến | JSON/text khá lớn qua mạng hạn chế | CPU encode, memory buffers, client decode |
| Mức nén cao | Egress đắt, payload rất dễ nén và concurrency thấp | CPU tăng, latency tăng |
| Brotli/Zstd khi stack/CDN hỗ trợ | Một số text/static assets tối ưu hơn | Negotiation/compatibility/CPU; không mặc định Boot hỗ trợ mọi codec |
| Nén tại CDN/proxy | Giảm app CPU, cacheable response | Hop TLS, caching, double compression, proxy config |
| Cache compressed representation | Giảm CPU lặp | Correct Vary/ETag/authorization/invalidation |

Không khẳng định “Brotli nhanh hơn gzip” hay “gzip luôn tiết kiệm CPU” trong mọi workload. Codec và level cần so sánh trên **dữ liệu thật** (text, JSON, random/binary) cùng version/hardware.

### 4.5. Tác động lên cache, ETag và response length

Compression tạo representations có thể khác theo `Accept-Encoding`. Caches và CDN cần xử lý `Vary: Accept-Encoding`, ETag weak/strong semantics và tránh phục vụ compressed bytes cho client không hỗ trợ. Với signed payloads, byte-level digest/checksum có thể cần tính đúng trên compressed/uncompressed representation.

**Đừng nén hai lần:** nếu ingress/CDN đã nén, nén lại ở app không chắc mang lợi ích và có thể dẫn đến lỗi representation. Kiểm headers tại app, proxy và client edge. Đừng so Content-Length của một response chunked với raw JSON object size rồi kết luận compressor sai.

### 4.6. Compression side channels và dữ liệu nhạy cảm

Một số kiểu tấn công kiểu **BREACH** khai thác độ dài response nén khi response đồng thời chứa bí mật và dữ liệu do attacker điều khiển. Với phản hồi HTML/JSON nhạy cảm trộn secret+reflected input, cần đánh giá threat model, không đơn giản bật compression cho mọi endpoint. Biện pháp tùy ngữ cảnh gồm tách secrets khỏi phản hồi có reflected input, chống CSRF/XSS, padding hợp lý hoặc tắt compression trên route nhạy cảm; không coi HTTPS tự chặn mọi side channel.

## 5. Ghi log: mỗi request có thể tạo nhiều I/O hơn payload

Logging là thành phần thường bị bỏ qua khi đo chi phí request. Một lệnh:

~~~java
log.info("Processed orderId={} in {} ms", orderId, durationMs);
~~~

có thể tạo định dạng chuỗi, encoder/JSON event, lock/queue, I/O stdout hoặc file, shipper/agent, network tới logging backend và storage. Nếu log **một dòng cho mỗi item**, response 10.000 items có thể sinh 10.000 dòng log cho **một HTTP request**.

### 5.1. Thứ gì làm logger tốn chi phí?

| Công đoạn | Ví dụ | Chi phí/rủi ro |
| --- | --- | --- |
| Xác định level | DEBUG có bật không | Rất thấp nhưng gọi dày vẫn cộng dồn |
| Tạo tham số | Tạo String, đọc object state | Allocation và có thể truy vấn dữ liệu nếu gọi method tốn kém |
| Format/encode | Pattern layout, structured JSON, exception stacktrace | CPU, allocations |
| Append | Console/file/socket | Lock, I/O, flush, backpressure |
| Asynchronous queue | Log event chờ thread ghi | RAM, loss hoặc blocking khi đầy |
| Shipper/aggregation | Đọc stdout, parse JSON, gửi backend | CPU/egress/chi phí lưu trữ ngoài app |
| Retention/search | Index theo fields | Chi phí backend và privacy |
| MDC/tracing | Correlation IDs | Context propagation, scope/cleanup |

Spring Boot starters mặc định dùng **Logback**, thường log ra console, không tự tạo file log nếu không có `logging.file.name/path`. Spring Boot cũng hỗ trợ structured logging theo ECS/GELF/Logstash.

### 5.2. Cách log đúng: SLF4J placeholders

~~~java
// NÊN: định dạng tham số theo logger khi level được bật.
log.debug("Request count={} kind={}", count, kind);
~~~

Tránh ghép String chủ động khi debug bị tắt:

~~~java
// KHÔNG NÊN: String mới được tạo dù DEBUG bị tắt.
log.debug("Request count=" + count + " kind=" + kind);
~~~

Đặc biệt tránh:

~~~java
// NGUY HIỂM VỀ HIỆU NĂNG VÀ RIÊNG TƯ:
// jsonMapper.writeValueAsString() được gọi TRƯỚC log.debug(),
// kể cả khi DEBUG bị tắt.
log.debug("responseBody={}", jsonMapper.writeValueAsString(response));
~~~

Nếu thực sự cần dựng dữ liệu debug tốn kém trong môi trường dev:

~~~java
if (log.isDebugEnabled()) {
    // Chỉ tính một bản summary an toàn, không serialize raw PII/token.
    log.debug("response count={} status={}", responseCount, status);
}
~~~

Các đoạn này là **fragments** trong class có sẵn logger, biến và mapper, không phải Java source độc lập. Chú ý SLF4J placeholders **không trì hoãn việc đánh giá các Java expressions truyền làm arguments**; nếu argument là một lời gọi nặng, guard trước nó.

### 5.3. Tránh log full request/response bodies

Các dữ liệu nguy hiểm:

- `Authorization: Bearer ...`, cookie, session ID, API key.
- Password, refresh token, OTP, payment details, email/số điện thoại.
- Query có PII, toàn bộ URL nếu chứa secret.
- Multipart/file content, binary/Base64.
- Raw JSON vài MiB hoặc arrays hàng chục nghìn records.
- Exception message có SQL/connection string/secrets.

Log body vừa tiêu tốn thêm serialization/encoding, vừa có thể ghi PII vào nhiều hệ thống hơn (stdout/agent/ELK/storage). Dùng **request ID/trace ID, URI template, status, outcome, số items, elapsed time** và các fields được whitelist. Nếu cần debugging đặc biệt, bật có thời hạn, sampling, redaction, size cap và phê duyệt truy cập.

### 5.4. Structured logging có lợi nhưng không miễn phí

Cấu hình Boot 4:

~~~properties
logging.structured.format.console=logstash
~~~

Hoặc:

~~~properties
logging.structured.format.console=ecs
~~~

Structured JSON logs dễ parse/truy vấn theo key nhưng cần format thêm một bản JSON cho **log event**, độc lập với JSON response đang gửi tới client. Nếu một request trả 1 MiB JSON rồi bạn log toàn bộ payload, bạn có thể serialize/escape gần như cùng một dữ liệu **hai lần** và ghi ra một pipeline I/O khác.

Chọn schema log nhỏ, nhất quán: `timestamp`, `level`, `logger`, `trace_id`, `route`, `status`, `elapsed_ms`, `result_count`. Không thêm full payload chỉ vì hệ thống logging có thể nhận JSON.

### 5.5. Đồng bộ và bất đồng bộ

Một synchronous console/file appender có thể nằm trực tiếp trong request critical path. Nếu stdout pipe, terminal, filesystem hoặc log agent chậm, request thread có thể bị block hoặc queue tăng ở các tầng trung gian.

Async appender tách bớt I/O khỏi request thread, nhưng vẫn phải:

- Tạo/ghi log event vào queue có **dung lượng giới hạn**.
- Format hoặc snapshot context theo mức cần thiết.
- Giải quyết overload: **block**, **drop** hoặc fail theo policy.
- Chờ flush khi shutdown nếu events quan trọng.
- Không âm thầm drop **audit/security/financial logs** yêu cầu durability.
- Giám sát queue depth, dropped count, write errors.

Ví dụ **minh họa** Logback `AsyncAppender`; dùng như file `logback-spring.xml` nếu chủ động thay cấu hình Boot logging mặc định:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="CONSOLE"/>
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

**Trade-off:** `neverBlock=false` có thể **chặn producer** khi queue đầy để tránh mất log; `neverBlock=true` có thể bỏ log khi buffer đầy. `discardingThreshold=0` tắt cơ chế discard theo threshold thông thường, nhưng không biến queue thành vô hạn hoặc loại bỏ vấn đề appender bên dưới. Đo p99 latency, queue và log loss trước khi chọn. Nếu thay file Logback, các customizations của Boot có thể cần đưa vào lại; snippet chỉ minh họa chứ không phải lời khuyên bật trên mọi service.

### 5.6. Access log và application log là hai đường khác nhau

Tomcat access log được điều khiển qua `server.tomcat.accesslog.enabled`, mặc định **false** theo Boot 4. Một access log theo mỗi request có thể rất hữu ích để điều tra status, bytes và thời gian xử lý, nhưng làm tăng thêm I/O và retention.

~~~properties
# Tùy chọn lab/production khi đã có policy bảo mật logs.
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%a %s %D
~~~

Pattern này không đưa raw URL vào log, nhưng vẫn có địa chỉ client IP và thời gian xử lý, cần bảo vệ theo chính sách. Pattern common mặc định có thể chứa đường dẫn/query tùy cấu hình. Access log không đồng nghĩa Spring application INFO/DEBUG log, cũng không mặc nhiên cùng format/retention. Đừng bật logs chi tiết ở nhiều tầng gateway/app/sidecar và bỏ qua tổng khối lượng.

### 5.7. WebFlux/MDC

Trong WebFlux, Reactor có thể chạy continuations trên nhiều threads. Một `ThreadLocal MDC` không tự luôn truyền đúng theo reactive chain. Dùng Reactor Context, context propagation phù hợp framework/version và các cơ chế tracing chính thức. Không tự copy MDC từ request A vào singleton mutable object để phục vụ request B; đó có thể gây lẫn thông tin giữa users và tạo thêm chi phí.

## 6. Tương tác của JSON, compression và logging

Không nên đo ba công đoạn riêng rồi tự cho rằng lợi ích cộng tuyến tính.

| Tình huống | JSON encode | Compression | Logging | Hệ quả có thể |
| --- | --- | --- | --- | --- |
| JSON nhỏ, không log | Thấp | Tắt | Thấp | Network thường không phải bottleneck |
| JSON lớn, lặp nhiều | Cao hơn | Giảm wire bytes nhiều | Thấp | Có thể tiết kiệm network nhưng tăng CPU |
| JSON lớn, entropy cao | Cao hơn | Giảm bytes ít | Thấp | Thêm CPU với ít lợi ích |
| JSON lớn + log full body | JSON response + JSON log | Dù bật/tắt | Rất cao | CPU/allocation/I/O/log storage bùng |
| Log 1 dòng metadata | Không thay đổi nhiều | Có thể bật | Có kiểm soát | Thường hữu ích cho vận hành |
| Structured log mọi item | Không nhất thiết thay response | Có thể bật | JSON log/event nhiều lần | Dễ saturate stdout/agent |
| WebFlux streaming | Có thể encode theo chunks | Theo transport | Context cần đúng | Backpressure/flush behavior quan trọng |

### 6.1. Ví dụ trade-off theo hardware

Giả sử server có ngân sách **4 CPU core seconds/s** để xử lý request (lý tưởng hóa), mỗi request cần 8 ms CPU trước nén. Trần lý thuyết chỉ xét CPU là:

~~~text
4 CPU-seconds/s / 0.008 CPU-seconds/request = 500 requests/s
~~~

Nếu bật GZIP khiến chi phí tăng lên 12 ms CPU/request, trần CPU lý thuyết còn:

~~~text
4 / 0.012 ≈ 333 requests/s
~~~

Ngược lại, nếu GZIP giảm dữ liệu xuất mạng đủ lớn để bớt chờ socket/write hoặc giảm network saturation, **throughput thực** có thể tốt hơn dù CPU/request tăng. Các giá trị 8/12 ms hoàn toàn là **ví dụ giả định** để học cách lập ngân sách, không phải benchmark Spring Boot/Tomcat.

### 6.2. In-flight requests nhân memory footprint

Một response có object graph 1 MiB, encoder buffers 0,5 MiB và staging/proxy buffers 0,5 MiB (chỉ minh họa). Với 1.000 requests cùng lúc, mức dùng memory khả dĩ đã là nhiều GiB **trước heap fragmentation, connection pools và framework overhead**. Vì thế giảm response size, streaming, bounded concurrency và hạn chế queue có thể quan trọng hơn tối ưu một hàm serializer vài microseconds.

### 6.3. Cache có thể thay đổi cả ba loại chi phí

Nếu cache response JSON bytes cho nội dung thực sự giống nhau, app có thể tránh xây lại object graph và serialize; CDN/proxy có thể giảm số requests vào backend. Nhưng cache cho dữ liệu phân quyền cần key chính xác, không chia response của user A cho user B. Khi nén, cache phải tôn trọng Content-Encoding/Vary, ETag và invalidation. Cache không giải quyết logging nếu vẫn in nhiều logs trên mỗi cache hit.

## 7. Dự án thực hành: đo JSON, compression và log bằng Spring Boot 4.1.2

Bài lab dưới đây tách được **kích thước response** và **số log lines** qua request parameters có bounds. Dùng Java record DTO, Spring Boot Jackson 3 converter mặc định, HTTP compression và Micrometer metrics. Không cố xây một bộ benchmark hoàn hảo trong controller.

### 7.1. Cấu trúc thư mục

~~~text
cost-per-request-lab/
  pom.xml
  src/main/java/com/example/costlab/
    CostPerRequestApplication.java
    CostController.java
  src/main/resources/
    application.properties
~~~

Yêu cầu: **JDK 17+**, Maven, cURL. Thử ở localhost, không đưa endpoint load-test công khai ra internet. Các con số thử nghiệm cần được đo trên máy bạn.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cost-per-request-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-webmvc` là starter Spring MVC/Tomcat ở Boot 4.1.2. Jackson 3 JSON converter được cung cấp qua JSON dependencies của Spring web starter/Boot auto-configuration. `spring-boot-starter-actuator` và Micrometer Prometheus registry dùng cho phép đo, không phải yêu cầu để JSON serialization hoặc compression hoạt động.

### 7.3. CostPerRequestApplication.java

~~~java
package com.example.costlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CostPerRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(CostPerRequestApplication.class, args);
    }
}
~~~

### 7.4. CostController.java

~~~java
package com.example.costlab;

import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CostController {

    private static final Logger log =
            LoggerFactory.getLogger(CostController.class);

    private static final String REPETITIVE_DESCRIPTION =
            "Java Spring Boot JSON encoding and HTTP compression. ".repeat(8);

    public record Item(int id, String sku, String description, int quantity) {}

    public record Report(int count, String mode, List<Item> items) {}

    @GetMapping(value = "/report", produces = MediaType.APPLICATION_JSON_VALUE)
    public Report report(
            @RequestParam(defaultValue = "100") int count,
            @RequestParam(defaultValue = "repeated") String mode,
            @RequestParam(defaultValue = "false") boolean logEach) {

        if (count < 1 || count > 3000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "count must be 1..3000");
        }
        if (!mode.equals("repeated") && !mode.equals("varied")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "mode must be repeated or varied");
        }
        if (logEach && count > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "logEach requires count <= 50");
        }

        List<Item> items = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            String description;
            if (mode.equals("repeated")) {
                description = REPETITIVE_DESCRIPTION;
            } else {
                // Chuỗi biến thiên theo i, không phải dữ liệu ngẫu nhiên
                // có chất lượng entropy cao; tránh đánh đồng với "random".
                long code = 0x9E3779B97F4A7C15L * (i + 1L);
                description = "unique-" + i + "-"
                        + Long.toUnsignedString(code, 36);
            }

            items.add(new Item(i, "sku-" + i, description, (i % 7) + 1));

            // Chỉ dùng để thấy chi phí log-per-item ở count nhỏ.
            if (logEach) {
                log.info("lab item generated id={} mode={}", i, mode);
            }
        }

        log.info("report generated count={} mode={} logEach={}",
                count, mode, logEach);

        // Spring MVC/Jackson serialize SAU khi method này return.
        return new Report(count, mode, List.copyOf(items));
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Tính chất của demo:

- Với `mode=repeated`, description lặp dài → body thường dễ nén.
- Với `mode=varied`, description thay đổi theo index → body có pattern khác; **không phải dữ liệu ngẫu nhiên entropy cao**, nên ratio khác thế nào phải đo.
- `count=1..3000` bound object count, tránh một request tạo hàng triệu records.
- `logEach=true` chỉ cho `count<=50` để minh họa log-per-record mà không vô tình phát hàng nghìn log lines ở một request.
- Logger INFO tóm tắt một dòng cho mỗi request; khi so INFO với WARN, giữ các tham số request giống nhau để đánh giá logging level.
- Controller trả một `Report` record, **không tạo JSON String bằng tay**. JSON conversion do Spring MVC/Jackson thực hiện sau khi controller trả về.
- Không nên triển khai endpoint có mode/logEach do người dùng tùy chọn ra public internet. Mục tiêu duy nhất là lab.

### 7.5. application.properties

~~~properties
# Chỉ phục vụ loopback trong lab.
server.address=127.0.0.1
server.port=8080

# Bật response compression, vẫn phụ thuộc negotiation/MIME/size.
server.compression.enabled=true
server.compression.min-response-size=2KB

# app logs ở INFO để minh họa volume.
logging.level.com.example.costlab=INFO

# Chỉ expose endpoints chẩn đoán cần thiết ở localhost.
management.endpoints.web.exposure.include=health,metrics,prometheus

# Không bật Tomcat access log mặc định cho lab để tránh chồng nhiễu.
server.tomcat.accesslog.enabled=false
~~~

Với `server.compression.enabled=true`, chỉ khi client yêu cầu và response đủ điều kiện, server mới nén. Đừng kết luận từ property rằng **mọi response** đều có GZIP. Đặt `server.address=127.0.0.1` và giới hạn actuator exposure vì /metrics/prometheus có thể tiết lộ thông tin vận hành.

### 7.6. Chạy

~~~bash
mvn spring-boot:run
~~~

Gọi:

~~~bash
curl -i http://127.0.0.1:8080/api/ping

curl -i \
  "http://127.0.0.1:8080/api/report?count=2&mode=repeated"
~~~

Body của `/api/ping` là:

~~~text
pong
~~~

Body `/api/report` là JSON có `count=2`, `mode="repeated"` và `items` hai records với các trường `id`, `sku`, `description`, `quantity`. Toàn bộ JSON có thể dài do description lặp; thứ tự properties/JSON format và các headers phụ thuộc Jackson/runtime. Không tự gán một stdout cứng cho response JSON khi chưa thực thi Maven.

Test sai input:

~~~bash
curl -i "http://127.0.0.1:8080/api/report?count=50000"
curl -i "http://127.0.0.1:8080/api/report?mode=unknown"
curl -i "http://127.0.0.1:8080/api/report?count=100&logEach=true"
~~~

Các lệnh phải nhận HTTP **400** khi handler validation chạy, thay vì tạo payload/log vượt bounds. Error body cụ thể do Spring Boot error handling quyết định, không nên copy một JSON error cứng làm expected stdout.

### 7.7. Đo bytes chưa nén và bytes đã nén trên wire

Ở terminal thứ hai (Linux/macOS/WSL):

~~~bash
# Chạy server từ project root trước.

# KHÔNG yêu cầu gzip: lưu body chưa nén.
curl -sS \
  -D /tmp/raw.headers \
  -o /tmp/raw.body \
  -w "raw status=%{http_code} bytes=%{size_download} total=%{time_total}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

# Yêu cầu gzip, lưu bytes trả về chưa tự giải nén.
curl -sS \
  -H "Accept-Encoding: gzip" \
  -D /tmp/gzip.headers \
  -o /tmp/gzip.body \
  -w "gzip status=%{http_code} bytes=%{size_download} total=%{time_total}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

# Kiểm server có THỰC SỰ nén hay không.
grep -i "content-encoding" /tmp/gzip.headers
wc -c /tmp/raw.body /tmp/gzip.body
~~~

Chỉ khi `/tmp/gzip.headers` có `Content-Encoding: gzip` thì so raw/gzip bytes theo ý nghĩa nén. Nếu không có, kiểm MIME, min-response-size, negotiation, server connector, gateway và response headers. `size_download` của cURL là downloaded body bytes cho response đó; không tự đồng nghĩa CPU/heap hoặc business latency.

Nếu dùng `curl --compressed`, cURL tự yêu cầu encoding và **giải nén dữ liệu khi ghi body**; vì vậy không dùng file body từ lệnh `--compressed` để khẳng định nó chứa raw compressed bytes. Muốn kiểm JSON giải nén:

~~~bash
curl --compressed -sS \
  "http://127.0.0.1:8080/api/report?count=10&mode=repeated"
~~~

Với Windows PowerShell, dùng `curl.exe`; các đường dẫn /tmp và `wc`/`grep` ở trên dành cho POSIX/WSL.

### 7.8. So sánh với body nhỏ

~~~bash
curl -sS \
  -H "Accept-Encoding: gzip" \
  -D /tmp/small.headers \
  -o /tmp/small.body \
  "http://127.0.0.1:8080/api/report?count=1&mode=varied"

grep -i "content-encoding" /tmp/small.headers
~~~

Với ngưỡng 2KB, response nhỏ thường không được nén. Tuy nhiên server connector có những điều kiện riêng; hãy đọc headers thật, không hứa mọi máy đều có outcome identical.

### 7.9. So sánh JSON lặp và dữ liệu biến thiên

~~~bash
curl -sS -H "Accept-Encoding: gzip" \
  -o /dev/null \
  -w "repeated=%{size_download}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=repeated"

curl -sS -H "Accept-Encoding: gzip" \
  -o /dev/null \
  -w "varied=%{size_download}\n" \
  "http://127.0.0.1:8080/api/report?count=1000&mode=varied"
~~~

Hai payload khác nhau **không cùng raw size**, nên không thể chỉ nhìn downloaded bytes rồi kết luận “độ entropy khiến nén tốt hơn”. Muốn so compression ratio, đo **cả raw bytes và gzip bytes** cho mỗi shape, rồi tính `compressed/raw` và quan sát CPU riêng.

### 7.10. Thử logging levels một cách công bằng

Lần 1 chạy app với:

~~~bash
java -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.com.example.costlab=WARN \
  --server.compression.enabled=false
~~~

Lần 2 (sau khi dừng process trước) chạy:

~~~bash
java -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.com.example.costlab=INFO \
  --server.compression.enabled=false
~~~

Build JAR trước:

~~~bash
mvn package
~~~

Sau đó chạy cùng workload `count=20&logEach=true` ở cả hai phiên:

~~~bash
curl -sS -o /dev/null \
  "http://127.0.0.1:8080/api/report?count=20&logEach=true"
~~~

Ở WARN, các `log.info` không được append; ở INFO, controller tạo khoảng 21 log events cho request này (20 per-item + 1 summary) nếu request chạy hết. **Đây là số câu lệnh log do code có thể gọi**, không phải số record chắc chắn tồn tại trong log collector khi có sampling/drop/retries. Đo elapsed/CPU/queue với nhiều requests, sau warm-up và cùng tần suất; một cURL đơn không đủ kết luận phần trăm overhead.

### 7.11. Ma trận A/B có kiểm soát

| Thử nghiệm | Compression | Log level | Payload | Mục đích |
| --- | --- | --- | --- | --- |
| A | Off | WARN | repeated, count=1000 | Baseline encode+network, ít app log |
| B | On | WARN | repeated, count=1000 | Chênh lệch compression/network |
| C | Off | INFO | repeated, count=1000 | Chênh lệch một summary log/request |
| D | On | INFO | repeated, count=1000 | Tác động kết hợp GZIP+logging |
| E | Off | WARN | varied, count=1000 | Ảnh hưởng payload shape |
| F | On | WARN | varied, count=1000 | Tỷ lệ nén/CPU trên shape khác |
| G | Off | INFO | repeated, count=20, logEach=true | Stress mức thấp cho log-per-item |
| H | Off | WARN | repeated, count=20, logEach=true | Đối chứng cùng response, log tắt |

Tạo mỗi biến thể bằng CLI properties, **restart application** để thay một yếu tố duy nhất theo lượt test, trừ khi bạn có cơ chế cấu hình động được kiểm soát. Giữ nguyên JDK, heap, CPU quota, profile, GC, client/concurrency, proxy, response data, metrics settings và số request warm-up.

Trong đo production-like, chạy **nhiều lần**, báo median/p95/p99 và confidence interval; không đưa các số “x ms giảm y%” chưa đo vào tài liệu như sự thật.

## 8. Java 17: ví dụ độc lập kiểm GZIP bytes (không dùng Jackson)

Để nhìn rõ **raw bytes → GZIP bytes** mà không phụ thuộc Spring và Maven, tạo `GzipSizeDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPOutputStream;

public class GzipSizeDemo {

    public static void main(String[] args) throws Exception {
        // Chỉ dùng JSON ASCII do ta kiểm soát cho ví dụ bytes.
        // KHÔNG tự nối chuỗi thành JSON cho dữ liệu người dùng.
        String json = "{\"message\":\"" + "A".repeat(4096) + "\"}";
        byte[] raw = json.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(out)) {
            gzip.write(raw);
        }
        byte[] compressed = out.toByteArray();

        System.out.println("raw bytes: " + raw.length);
        System.out.println("gzip smaller: " + (compressed.length < raw.length));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GzipSizeDemo.java
java GzipSizeDemo
~~~

Stdout của chương trình:

~~~text
raw bytes: 4110
gzip smaller: true
~~~

Giải thích phép đếm: JSON này có 4.096 chữ `A` (ASCII), cùng 14 bytes của phần `{"message":"..."}` nên tổng 4.110 bytes UTF-8. Mẫu rất dễ nén, do đó GZIP nhỏ hơn raw. Con số **compressed bytes cụ thể** không được hardcode vì mức nén/JDK có thể khác. Ví dụ cũng **không** đo CPU, latency qua HTTP hay chi phí Jackson; nó chỉ kiểm raw-vs-gzip bytes trên một payload cố định.

Nếu input chứa ký tự không phải ASCII, `String.length()` không còn phản ánh chính xác UTF-8 bytes. Muốn so dung lượng JSON API thật, đo bytes sau serializer và/hoặc response HTTP thật.

## 9. Đo performance đúng cách: từ endpoint tới profiler

### 9.1. Http.server.requests và Actuator

Spring Boot Actuator instrument Spring MVC/HTTP handlers với meter logic `http.server.requests`. Bật:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

Sau khi có traffic:

~~~bash
curl -sS http://127.0.0.1:8080/actuator/metrics
curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -sS http://127.0.0.1:8080/actuator/prometheus
~~~

`/actuator/metrics/http.server.requests` dùng để chẩn đoán, không nên làm nguồn scrape production. `/actuator/prometheus` dành cho Prometheus scrape khi có registry và endpoint được expose. HTTP timer thường đo elapsed của request framework, bao gồm phần lớn xử lý response; nhưng **không tự tách JSON vs GZIP vs logging**, và có thể khác ở async I/O, proxy buffering, client nhận chậm. Muốn tách các stages phải bổ sung profiling/benchmark instrumentation tại đúng điểm.

### 9.2. PromQL gợi ý

Lưu lượng mỗi route:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Trung bình duration (giây):

~~~promql
sum by (uri) (rate(http_server_requests_seconds_sum[5m]))
/
clamp_min(sum by (uri) (rate(http_server_requests_seconds_count[5m])), 1e-9)
~~~

Nếu cấu hình histogram phù hợp và exporter có `_bucket`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Không mặc định `_bucket` sẽ có nếu chưa bật histograms. Cũng không gắn request ID, user ID, full URI query, payload size byte-by-byte hoặc arbitrary logging message thành labels: **cardinality explosion** sẽ khiến chính hệ observability quá tải.

### 9.3. CPU, GC và memory

Quan sát:

- Process CPU utilization/load, CPU throttling của container.
- JVM heap used, allocation rate, GC pause/time, humongous allocations.
- Thread pool active/queued requests, Tomcat busy threads.
- Response bytes (uncompressed/compressed), network egress Mbps.
- Log events/sec, bytes/sec, async log queue backlog, dropped logs.
- HTTP request rate, errors, p50/p95/p99 duration.
- Compression ratio theo MIME/body shape.
- Heap retained bởi object graphs, JSON buffers và logging queues.

Spring Boot Actuator/metrics auto-config cung cấp một số JVM/process/log events metrics; **không phải** mọi metric như “CPU JSON encoder per request” hay “bytes in async log queue” có sẵn mặc định. Với stage-specific cần JFR/profiler hoặc custom instrumentation có overhead được kiểm soát.

### 9.4. JDK Flight Recorder

Với Java 17 và app đã đóng JAR, có thể chạy:

~~~bash
java -XX:StartFlightRecording=filename=cost.jfr,dumponexit=true \
  -jar target/cost-per-request-lab-0.0.1-SNAPSHOT.jar
~~~

Đây là **ví dụ lệnh Java 17**; profiler/JFR settings, quyền ghi file và môi trường có thể khác. Dùng Java Mission Control/JFR viewer tìm CPU samples, allocation hotspots, GC pauses và blocked threads. Một số điểm nóng có thể đến từ Jackson serializer, Deflater/GZIP, Logback encoder/appenders hoặc business logic.

Nếu muốn chi tiết CPU flamegraph/allocations dưới load, dùng async-profiler/JFR/JMH với phiên bản tương thích, nhưng không profile trên production lâu không giám sát overhead/PII. Method timer trong controller chỉ đo thời gian **trước return**, bỏ lỡ HTTP converter hoạt động sau đó; đừng lấy nó làm “thời gian JSON serialization”.

### 9.5. Microbench với JMH

Nếu cần so đúng serializer/DTO/schema:

- Dùng **JMH** để benchmark Jackson serialization riêng, có warm-up, forks và blackhole/consume output.
- Tạo dữ liệu bên ngoài measured method, giữ size/shape xác định.
- Chạy cùng JDK/JVM flags, CPU pinning khi cần, heap và mapper config.
- Có thử throughput và allocations (gc profiler), nhiều payload distributions.
- So JVM serialization benchmark với HTTP end-to-end load test; một bên đo code path cụ thể, một bên đo network/framework tổng thể.
- Không dùng `System.nanoTime()` loop một lần rồi tuyên bố một framework nhanh hơn 100%: JIT, dead-code elimination, cache, GC và scheduler có thể gây sai lệch.

### 9.6. Load generator và môi trường

Tools như wrk/k6/Gatling/hey có thể đo RPS và latency percentiles. Cần:

1. Bảo đảm **load generator không bão hòa trước server**.
2. Xác định số concurrent users/connection reuse/keepalive.
3. Cho server warm-up trước, pre-populate caches khi đúng workload.
4. Đo **nhiều kịch bản response size**, không chỉ 1 KiB.
5. Không dùng stdout terminal tương tác như một log sink benchmark production: tốc độ terminal có thể là bottleneck.
6. Dùng network profile gần production (RTT, băng thông, proxy, TLS).
7. Thử tail latency khi burst/GC/log agent tắc.
8. So ít nhất baseline và thay **một biến** mỗi lượt.
9. Báo kết quả theo interval ổn định, không chỉ một request đầu.
10. Có error thresholds: HTTP 500/timeouts là dấu hiệu test không hợp lệ dù RPS trông cao.

## 10. Spring MVC so với WebFlux: cùng loại chi phí, khác thực thi

### 10.1. MVC/Servlet

- Controller thường chạy trên Servlet request threads; việc đồng bộ/blocking JSON conversion/logging/I/O có thể giữ thread lâu.
- Jackson converter serialize object để tạo response, có thể tạo buffers; nén do embedded container thực hiện khi response đủ điều kiện.
- Nếu log sink blocking trên request path, request thread bị giữ; khi đủ requests có thể saturate Tomcat threads.
- `server.compression.enabled` có thể tác động embedded Tomcat/Jetty; kiểm response headers thực.

### 10.2. WebFlux/Reactor Netty

- Reactive response writing diễn ra trong Publisher pipeline; JSON encoder và nén vẫn tiêu thụ CPU/heap.
- **Reactive không tự làm JSON serialization miễn phí**. Nếu encode hoặc log payload cực lớn trên event loop, CPU work vẫn có thể chiếm event loop, làm nhiều connections trễ.
- Tránh `block()`, blocking file appenders/custom logging I/O hoặc JDBC trên Netty event loop; offload blocking work đúng cách nếu thực sự cần và có bounded concurrency/queue.
- Reactor backpressure có thể giảm demand upstream trong một số pipeline nhưng **không tự giới hạn mọi hot producer hay socket/proxy buffers**.
- Khi stream `Flux<T>` JSON/SSE, phải cân nhắc element-by-element serialization, codec buffers, flushing và client chậm. Nén streaming có thể thay đổi time-to-first-byte và khả năng flush.
- Không dùng `spring.codec.max-in-memory-size` như một “trần tổng CPU/response bytes” chung; đó là giới hạn buffer của một số codecs, không thay payload policy, client count và logging.

### 10.3. Không gắn logging context của user A cho user B

Trong Reactor, context có thể chuyển giữa schedulers. MDC truyền thống thường dựa trên ThreadLocal; muốn correlation đúng dùng context propagation phù hợp với Spring/Observation/trace integration, không giữ mutable request metadata trong singleton shared fields. Việc log nhiều ở WebFlux event loop có thể tạo bottleneck dùng chung cho nhiều sessions.

## 11. Streaming, pagination và response buffering

Với JSON rất lớn, giảm số records thường là bước đầu. Các lựa chọn:

| Cách trả | Tác dụng tốt | Những giới hạn |
| --- | --- | --- |
| Một `List<DTO>` lớn | Code đơn giản | Nhiều heap objects, JSON encode, latency, GC |
| Cursor/pagination | Bound response size và DB rows | Client phải điều phối nhiều requests, consistency |
| NDJSON streaming | Xử lý từng record, có thể stream liên tục | Client phải hiểu newline framing; proxy/compression flush |
| SSE streaming | Server push updates | Slow consumers, proxy buffering, event IDs/replay |
| Response body streaming | Giảm peak buffer khi thực hiện đúng | Exception sau commit, backpressure/thread semantics |
| Binary download | Phù hợp large files | Không cùng API semantics với JSON |
| Cached/precomputed JSON | Giảm CPU lặp | Invalidation, auth, Content-Encoding/Caching |

Spring MVC có `StreamingResponseBody` cho streaming bytes và WebFlux có `Flux<DTO>` codecs. Đừng tự ghép JSON arrays thủ công bằng StringBuilder không bound chỉ để “bỏ Jackson”; rất dễ sai escape/encoding. Khi streaming, cần hiểu client cancellation, backpressure, content-length, chunk boundaries và errors sau response commit.

### 11.1. Nén streaming

Với response streaming, gzip/HTTP encoder có thể giữ bytes để đạt compression efficiency trước khi flush. Việc bật nén có thể làm **time-to-first-byte hoặc event latency** xấu đi ngay cả khi giảm total bytes. SSE thời gian thực thường cần thử qua proxy với compression và buffering thực tế; không giả định thiết lập compression cho mọi text/event-stream là tốt.

### 11.2. Cache key và bảo mật

Nếu cache response đã serialized, phải phân vùng theo auth/tenant, locale, fields selection, API version và Content-Encoding. Không lấy JSON cache của user A trả user B. Với response có signed payload/digest, nén thay đổi bytes nên verify correct representation và ETag semantics. Không dùng public CDN cho dữ liệu nhạy cảm nếu policy không cho phép.

## 12. Tối ưu ghi log mà vẫn đủ điều tra sự cố

### 12.1. Chọn đúng log level

- **ERROR:** lỗi cần xử lý, không log cùng stacktrace lặp 100 lần từ mọi tầng.
- **WARN:** tình trạng bất thường nhưng còn phục hồi, có rate limit/sampling nếu bùng phát.
- **INFO:** business state transitions/summaries có giá trị, không log từng item trong list lớn.
- **DEBUG/TRACE:** chỉ bật có kiểm soát, tạm thời, giới hạn lưu lượng, không chứa secrets.

Một request summary tốt:

~~~text
route=/api/report status=200 count=1000 duration_ms=34 trace_id=... 
~~~

Đây là **format minh họa**, không phải stdout cố định của demo. Đừng gắn một raw URL có query chứa PII vào metric label hoặc log vô hạn; dùng URI template và redaction.

### 12.2. Ghi log lỗi đúng tầng

Một lỗi DB timeout có thể được ghi ở repository, service, controller, exception handler, gateway và collector. Nếu mỗi tầng in stacktrace, một request có thể tạo nhiều MB logs. Chọn một điểm ghi đầy đủ stacktrace theo ownership, các tầng khác truyền context bằng exception cause/trace ID; vẫn bảo đảm audit và security events quan trọng được lưu.

### 12.3. Rate-limit và sampling logs

Khi một lỗi lặp hàng nghìn lần/s:

- Dùng sampling (ví dụ 1/100) cho diagnostics non-critical.
- Aggregate count theo metric/route/status và gửi logs chi tiết cho mẫu được chọn.
- Dùng token bucket/rate limit theo key hữu hạn, không theo từng ID tự do.
- Giữ các audit events bắt buộc **không bị sampling/drop**; nếu log infrastructure không đảm bảo durability, dùng durable audit channel riêng.
- Có alert cho dropped diagnostic logs và async queue full.

**Sampling log khác sampling trace/metrics.** Thường nên giữ metrics aggregate đầy đủ và sample high-cost diagnostic detail; không đánh đổi việc mất lỗi nghiệp vụ để tăng benchmark score.

### 12.4. File vs stdout

Trong container/k8s, thường ghi structured JSON logs ra stdout cho collector, nhưng stdout cũng có buffer, pipe và backpressure. Nếu logging agent bị chậm, appender có thể block hoặc queue. File appender có thêm filesystem writes, rotation, disk quota và cleanup. Chọn đường đi log theo platform SLO/retention, không coi một logger API call là “không có I/O”.

## 13. Bảo mật và dữ liệu riêng tư trong phép đo

Không log raw request/response bodies để benchmark production nếu chưa loại bỏ PII. GZIP với HTML/JSON phản hồi có secrets và reflected input cần đánh giá side channels; TLS không tự loại hết rủi ro compression ratio leakage.

Với test lab:

- Dùng synthetic data, không dùng user/order/token thật.
- Bind port về loopback, giới hạn endpoints Actuator.
- Không publish endpoint cho phép chọn số items/logEach ra public.
- Giới hạn total request size, max count, concurrency và timeout.
- Không bật tracing/debug/access logs chứa Authorization header hoặc cookies.
- Không đưa secrets vào URLs/query để rồi bị ghi bởi proxy/access logs.
- Với JSON deserialization inbound, giới hạn nesting/document length và schema; CPU/memory cost không chỉ nằm ở output.
- Có quyền và retention cho JFR/profiler artifacts, vì allocation/stack traces có thể tiết lộ dữ liệu.

## 14. Công thức ngân sách request và các quyết định trade-off

### 14.1. CPU request budget

Giả định một service có 8 vCPU, mục tiêu CPU sustained 70%, tức ngân sách khoảng 5,6 CPU-seconds trên một giây (mô hình đơn giản). Với request rate 1.000 RPS, ngân sách CPU trung bình cho mỗi request khoảng:

~~~text
CPU_budget_per_request ≈ 5.6 / 1000 = 0.0056 CPU-second
                       = 5.6 ms CPU/request
~~~

Nếu JSON encode + GZIP + logging đã chiếm 4 ms CPU/request, business/DB, TLS và framework còn rất ít headroom. Nhưng CPU utilization của container, vCPU shares/throttling và multi-threading có thể làm số đo thực khác mô hình. Không coi đây là lời hứa 8 vCPU luôn chạy đúng 8 CPU-seconds/s.

### 14.2. Network budget

Giả định mỗi response không nén 1 MiB, 1.000 RPS sẽ cần khoảng 1.000 MiB/s payload trước TLS/TCP overhead. Nếu nén còn 100 KiB, egress giảm nhiều, nhưng compressor phải tạo throughput tương ứng. Quyết định phụ thuộc cổng mạng, egress cost, CPU, RAM, payload shape, RTT và client decoder. Không dùng một mẫu JSON cực kỳ lặp để dự đoán ratio cho dữ liệu thực.

### 14.3. Log budget

Nếu mỗi request tạo 10 log events, mỗi event trung bình 1 KiB và có 1.000 RPS:

~~~text
10 events/request × 1 KiB/event × 1,000 requests/s
= 10,000 KiB/s ≈ 9.77 MiB/s logs
~~~

Chỉ riêng log stream ~9,77 MiB/s chưa kể index/replication, và **864.000 MiB/ngày** nếu tốc độ giữ nguyên (xấp xỉ 844 GiB/ngày) trước compression/retention. Dùng sampling, metadata summary hoặc giảm log points để cắt chi phí mà vẫn giữ tính quan sát.

### 14.4. Nhìn request cost theo 4 trục

| Trục | Câu hỏi | Công cụ đo |
| --- | --- | --- |
| Latency | p95/p99 end-to-end và TTFB bao nhiêu? | HTTP load test, Micrometer timers |
| CPU | CPU/request và hotspots ở đâu? | JFR, async-profiler, container CPU |
| Memory | Allocations/request, heap retained, GC pause? | JFR allocation, JVM metrics |
| I/O | Raw/compressed response bytes, log bytes, egress cost? | cURL, network, logging collector |

Nếu tối ưu một trục, kiểm cả ba trục còn lại. Ví dụ bật gzip giảm egress nhưng đẩy CPU utilization từ 50% lên 95% có thể làm p99 tệ và gây autoscaling; bật async logging giảm request latency nhưng khi queue đầy có thể mất logs hoặc đẩy memory pressure.

## 15. Những lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm/sửa |
| --- | --- | --- |
| Controller chạy vài ms, client mất vài giây | JSON encode/compression/network sau return | HTTP-level profiling, response size, JFR |
| Response size lớn dù DB nhanh | Trả entity graph/too many records | DTO, pagination, projection |
| Thêm gzip nhưng không thấy Content-Encoding | Client không gửi Accept-Encoding, MIME/size không đạt, proxy | cURL inspect headers, compression config |
| gzip không giảm bytes nhiều | Payload ngẫu nhiên/đã nén, body nhỏ | Đo compression ratio theo shape |
| gzip giảm egress nhưng RPS giảm | CPU deflate tăng, CPU bão hòa | Profile CPU, threshold, codec/level |
| gzip làm SSE latency cao | Buffer/flush tại server/proxy | Test event delivery và streaming config |
| JSON logger rất tốn | Double serialization/log body, structured logs nhiều | Log metadata, bound sampling |
| DEBUG tắt nhưng CPU vẫn tăng | Eager string concatenation hoặc mapper call làm argument | Placeholder và isDebugEnabled guard |
| Synchronous console log blocking | stdout pipe/agent hoặc file chậm | Tuning/sampling/async với queue policy |
| Async log queue OOM/loss | Queue quá lớn hoặc full/neverBlock=true | Bound queue, alert, audit channel |
| Có 100.000 meter series | Tag raw URI/user ID | Dùng template/bounded labels |
| GC pause tăng khi trả list lớn | Object graph + byte arrays + queued logs | Limit count, stream/paginate, profile allocation |
| Jackson 2 import không compile Boot 4 | Dùng package/mapper cũ | Jackson 3/JsonMapper, đúng dependencies |
| REST endpoint trả String thủ công có JSON escape sai | Hand-built JSON | Trả DTO/record cho mapper |
| Curl --compressed file size gây hiểu lầm | cURL tự giải nén output | Kiểm raw wire download & headers |
| Mọi request được log access + app + proxy | Trùng logging nhiều tầng | Đặt owner/retention/sampling |
| Log exception nhiều lần | Mỗi layer in stacktrace | Chọn điểm log có trace correlation |
| Microbenchmark cho ra số đẹp nhưng prod không cải thiện | Khác workload, JIT, network, concurrency | JMH + end-to-end A/B |
| Nén lỗi ẩn sau proxy | Compression/double compress/Vary | Inspect edge/backend headers |
| Bật JFR không tìm Jackson | Workload bottleneck là DB/network/logs | Profile đúng load, xem CPU vs wall clock |
| Nén response chứa secrets phản chiếu user input | Side-channel risk | Threat model, route-specific policy |

## 16. Checklist triển khai production

### JSON và dữ liệu

- [ ] DTO/record định hình response, limit số items và độ sâu object graph.
- [ ] Không expose JPA entities/lazy relationships trực tiếp mà chưa kiểm.
- [ ] Không encode JSON hai lần (mapper stringify rồi converter stringify).
- [ ] Serialize path dùng Jackson 3 và Boot-configured mapper đúng version.
- [ ] Có test output JSON schema/ordering/precision khi đổi mapper/modules.
- [ ] Có giới hạn kích thước inbound JSON, array/nesting và parser allocations.

### Nén và HTTP response

- [ ] Đã đo raw/gzip bytes theo MIME, body size và content type thực.
- [ ] Client gửi đúng Accept-Encoding, server trả Content-Encoding thật.
- [ ] Ngưỡng min-response-size phù hợp, không tốn CPU nén JSON quá nhỏ.
- [ ] Compression không double tại app/proxy/CDN; cache Vary/ETag đúng.
- [ ] Đã kiểm compression ratio vs CPU/request, RPS, p95/p99.
- [ ] Có đánh giá streaming/SSE flush và secrets+reflected input side channels.

### Logging

- [ ] Không log raw payload, Authorization, cookie, PII hoặc tokens.
- [ ] Parameterized logging và guard cho expensive debug arguments.
- [ ] Log level/sampling phù hợp; không bật TRACE cho tất cả requests.
- [ ] Structured logging chỉ thêm fields có ích, không serialize body một lần nữa.
- [ ] Nếu async logging, queue bounded và có loss/blocking policy.
- [ ] Có retention, rotation, collector capacity và xử lý log backpressure.
- [ ] MDC/Reactor Context đúng, không rò user/trace ID giữa requests.

### Hiệu năng và quan sát

- [ ] Đã đo CPU, allocation/GC, network bytes, log volume và p99 theo cùng workload.
- [ ] Có baseline và ma trận một biến mỗi lượt; warm-up, repeated runs.
- [ ] Có test tải cao, lỗi HTTP, client chậm, proxy và container CPU limits.
- [ ] Không coi method controller timer là đầy đủ serialization/compression time.
- [ ] Actuator endpoints bảo vệ, metric labels low cardinality.
- [ ] Có capacity budget và SLO: bytes/response, CPU/request, p99, egress, log bytes/s.
- [ ] Chốt rollback plan nếu bật nén/structured logs làm CPU hoặc latency tệ hơn.

## 17. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Tại sao controller method trả `List<DTO>` trong 2 ms nhưng request p99 mất 120 ms?

**Đáp án:** Serialization sau return, compression, socket/network wait, filters/logging và queueing vẫn có thể tốn thời gian. Timer trong controller không bao phủ toàn bộ lifecycle.

**Câu 2.** Spring Boot 4.1 mặc định dùng Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper` hay Jackson 3?

**Đáp án:** Jackson 3 là mặc định; Boot auto-config `JsonMapper` của Jackson 3 khi dependencies phù hợp. Jackson 2 được hỗ trợ tạm thời để chuyển đổi và đã deprecated.

**Câu 3.** `server.compression.enabled=true` có bảo đảm mọi response JSON được nén không?

**Đáp án:** Không. Cần client `Accept-Encoding` và server xét MIME/size/connector/headers. Phải kiểm `Content-Encoding` thật.

**Câu 4.** Khi nào gzip có thể làm throughput xấu đi dù giảm bytes?

**Đáp án:** Khi CPU nén trở thành bottleneck, đặc biệt body khó nén, nhỏ hoặc RPS cao; cần so CPU/RPS/p99 và egress.

**Câu 5.** Log `log.debug("payload={}", mapper.writeValueAsString(dto))` có tránh serialize khi DEBUG tắt không?

**Đáp án:** Không. Argument method được Java đánh giá trước, dù log event không được ghi. Dùng guard, và thường không log full body.

**Câu 6.** Async log appender có giải quyết hoàn toàn chi phí logging không?

**Đáp án:** Không. Vẫn có format/queue/memory/I/O; khi đầy phải block/drop và có thể mất logs. Không dùng cơ chế lossy cho audit không được phép mất.

**Câu 7.** Cách giảm JSON CPU tốt hơn có phải luôn là đổi Jackson sang một serializer khác?

**Đáp án:** Không. Giảm fields/rows, DTO, tránh N+1 và cache hợp lệ có thể cắt CPU/bytes ở nhiều tầng; đổi serializer có rủi ro và chỉ nên làm theo profile.

**Câu 8.** Vì sao hai response JSON cùng kích thước raw có thể có gzip ratios khác nhau?

**Đáp án:** GZIP phụ thuộc độ trùng lặp và entropy của dữ liệu. Các values lặp rất dễ nén; random/binary/đã nén khó hơn.

**Câu 9.** Vì sao không gắn userId/full URL vào Micrometer `http.server.requests` tags khi đo performance?

**Đáp án:** Tập giá trị không giới hạn làm nổ time series và có thể lộ dữ liệu. Dùng URI templates, method/status và các bounded labels.

**Câu 10.** Nếu response GZIP ít bytes hơn nhưng p99 xấu đi, phải làm gì?

**Đáp án:** Đo CPU compression, network, queue, proxy và response size; điều chỉnh threshold/MIME/offload strategy hoặc tắt nén trên endpoint không có lợi. Không kết luận từ một request.

**Câu 11.** Có thể để `logging.level.root=ERROR` ở production chỉ để benchmark đẹp không?

**Đáp án:** Tắt phần lớn logging làm mất khả năng chẩn đoán và có thể vi phạm audit/security requirements. Chọn levels/sampling có chính sách; giữ critical events.

**Câu 12.** Kiểm tra `gzipSmaller=true` của chương trình JDK có chứng minh Spring Boot response luôn nén không?

**Đáp án:** Không. Nó chỉ kiểm GZIP cho một payload rất dễ nén trong memory. HTTP negotiation/threshold/connector/streaming mới quyết định response có Content-Encoding hay không.

## 18. Tài liệu chính thức

- [Spring Boot — JSON Support (Jackson 3 default)](https://docs.spring.io/spring-boot/reference/features/json.html).
- [Spring Boot — Embedded Web Servers, Enable Response Compression](https://docs.spring.io/spring-boot/how-to/webserver.html).
- [Spring Boot — Common Application Properties, server.compression.*](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Spring Boot — Logging, Logback and Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Spring Boot — Metrics and HTTP request observations](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Enabling Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/enabling.html).
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html).
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).
- [Spring Framework — WebFlux Reactive Web](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Micrometer — Concepts: Timers and Metrics](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Oracle — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/).
- [OpenJDK — JMH](https://github.com/openjdk/jmh).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Kết luận:** Chi phí một HTTP request trong Spring Boot gồm nhiều bước hơn controller: **Jackson tạo JSON**, **compressor chuyển bytes** và **logger ghi events** đều tiêu thụ CPU, allocation, thời gian, I/O và tiền hạ tầng. Payload nhỏ/ít trường, DTO/phân trang, ngưỡng nén hợp lý, log summary có kiểm soát và benchmark đúng workload thường đem lại kết quả bền vững hơn việc nén mọi thứ hoặc log mọi payload. Hãy đo **p95/p99, CPU/request, raw/compressed bytes, GC và log bytes/s** cùng lúc; một tối ưu chỉ thành công nếu cải thiện mục tiêu vận hành mà không làm vỡ tính đúng đắn, bảo mật và khả năng điều tra sự cố.