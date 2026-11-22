# Nhật ký client, request id và trace có che dữ liệu nhạy cảm

Khi ứng dụng Spring Data Elasticsearch gặp lỗi hoặc phản hồi chậm, cần nối được một thao tác ở API/service với request mà Elasticsearch nhận, log ở client và hoạt động trên shard. Nhật ký có cấu trúc, request ID và distributed trace giúp làm việc đó. Nhưng log request/response thô có thể làm lộ password, API key, thông tin cá nhân, nội dung document hoặc điều kiện tìm kiếm nhạy cảm.

Một thiết kế quan sát an toàn cần đạt hai mục tiêu cùng lúc:

- **Có đủ ngữ cảnh để điều tra**: biết ai gọi ở mức định danh kỹ thuật phù hợp, thao tác nào, index/alias nào, mất bao lâu, lỗi thuộc loại gì và request liên quan trace nào.
- **Giới hạn dữ liệu được ghi**: chỉ log metadata cần thiết, che hoặc loại bỏ secret/PII, kiểm soát quyền truy cập và thời gian lưu log.

Bài học này phân biệt log, request ID và trace; hướng dẫn tạo và truyền correlation ID qua Spring, Elasticsearch client và Reactor; giải thích Elasticsearch header `X-Opaque-Id`; đồng thời trình bày redaction, log transport, slow logs, metrics và cách kiểm thử việc che dữ liệu.

## 1. Log, metric và trace giải quyết ba câu hỏi khác nhau

Observability thường kết hợp ba loại tín hiệu:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra tại một thời điểm? | Bulk ghi index thất bại với HTTP 429 |
| Metric | Sự việc xảy ra thường xuyên đến mức nào? | Tỷ lệ 429 tăng từ 0,1% lên 8% |
| Trace | Một request đã đi qua những service/span nào và tốn thời gian ở đâu? | API → service → Elasticsearch search mất 1,8 giây |

Không nên dùng log để thay metric hoặc dùng trace ID làm metric label.

Một log hữu ích có thể chứa:

- Timestamp và log level.
- Service, environment và version.
- Operation: search, index, update, bulk, delete.
- Index hoặc alias.
- Request ID/correlation ID.
- Trace ID và span ID nếu có distributed tracing.
- Duration, HTTP status, Elasticsearch error type.
- Retry attempt và kết quả.

Một log không nhất thiết phải chứa request body, document source hoặc toàn bộ response. Những dữ liệu đó thường làm log lớn, khó kiểm soát và có thể chứa thông tin nhạy cảm.

## 2. Phân biệt request ID, correlation ID, trace ID và span ID

Các ID này có liên quan nhưng không đồng nghĩa:

| ID | Phạm vi | Mục đích |
|---|---|---|
| Request ID | Một request tại một boundary, thường là API/backend request | Tìm log của một request cụ thể |
| Correlation ID | Một luồng nghiệp vụ có thể đi qua nhiều message/request | Liên kết các bước cùng một công việc |
| Trace ID | Một distributed trace | Nhóm các span thuộc cùng một hành trình |
| Span ID | Một operation trong trace | Xác định một bước cụ thể như gọi Elasticsearch |
| Elasticsearch opaque ID | Một request/task Elasticsearch được gắn nhãn | Tìm request Elasticsearch trong log/task API |

Ví dụ một thao tác publish sản phẩm:

~~~text
HTTP request
  requestId = req-8f2a
  traceId   = 4bf92f...
      |
      v
Product service
  spanId = a12...
      |
      +----> Database
      |       spanId = b31...
      |
      +----> Elasticsearch
              spanId = c45...
              X-Opaque-Id = req-8f2a-es-1
~~~

Một trace có thể chứa nhiều request ID hoặc correlation ID khi công việc tiếp tục qua queue và worker. Một request ID có thể được ghi ở nhiều service nếu nó được truyền theo hợp đồng. Một span ID chỉ đại diện cho một span, không nên tự tạo lại cho mọi log line.

Không dùng request ID làm bằng chứng xác thực hoặc authorization. Biết một ID không được phép giúp người gọi đọc document hay truy cập trace.

## 3. Luồng correlation từ ứng dụng đến Elasticsearch

Một luồng quan sát điển hình:

~~~mermaid
flowchart LR
    A["HTTP client"] --> B["Request filter"]
    B --> C["Spring service"]
    C --> D["Spring Data Elasticsearch"]
    D --> E["HTTP client / transport"]
    E --> F["Elasticsearch"]
    B -. "requestId + trace context" .-> C
    C -. "trace span" .-> D
    E -. "X-Opaque-Id / traceparent" .-> F
    F -. "server logs / task metadata" .-> G["Operations"]
    C -. "structured logs" .-> H["Log platform"]
    D -. "trace spans" .-> I["Tracing backend"]
~~~

Ở mỗi boundary, cần biết ID nào được giữ lại, ID nào được tạo mới và ID nào được chuyển tiếp.

Một nguyên tắc dễ vận hành:

- Tạo hoặc xác thực request ID tại ingress/API boundary.
- Dùng tracing instrumentation để quản lý trace/span context.
- Truyền correlation ID trong message envelope cho công việc bất đồng bộ.
- Gắn một opaque ID phù hợp vào request Elasticsearch nếu cần tìm phía server.
- Không tạo một ID mới ở từng lớp rồi làm mất liên kết với request ban đầu.

## 4. Tạo request ID ở Spring MVC

Với ứng dụng Servlet, có thể dùng `OncePerRequestFilter` để tạo request ID nếu chưa có, đưa vào MDC và trả lại trong response header.

Ví dụ:

~~~java
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-ID";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);

        // Có thể luôn tạo ID nội bộ; nếu chấp nhận ID từ upstream,
        // chỉ nhận chuỗi có độ dài và ký tự nằm trong allowlist.
        String requestId = supplied != null
                && SAFE_ID.matcher(supplied).matches()
                ? supplied
                : UUID.randomUUID().toString();

        try {
            MDC.put("requestId", requestId);
            response.setHeader(HEADER, requestId);
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Đăng ký filter trong application context hoặc security/filter chain theo thứ tự phù hợp với ứng dụng.

Lưu ý:

- Nếu API gateway đã tạo request ID đáng tin cậy, có thể giữ ID đó sau khi validate.
- Nếu không tin nguồn upstream, tạo ID nội bộ mới và lưu ID upstream ở một field riêng đã validate.
- Giới hạn độ dài và ký tự để tránh log injection, newline hoặc giá trị cực dài.
- Luôn xóa MDC trong `finally`; thread pool sẽ tái sử dụng thread cho request khác.
- Không dùng request ID để quyết định quyền truy cập.

Với Spring WebFlux, không nên bê nguyên cách dùng ThreadLocal/MDC của Servlet sang mọi callback reactive. Reactor có thể chuyển execution giữa thread; phần context cần được truyền theo Reactor Context hoặc Micrometer Context Propagation.

## 5. Correlation ID cho message và background job

Một request HTTP có thể tạo event để worker xử lý sau đó. Khi request kết thúc, worker không còn chạy trong cùng thread hoặc cùng request context.

Hãy truyền metadata cần thiết trong message envelope:

~~~json
{
  "eventId": "evt-184",
  "correlationId": "order-flow-72a1",
  "causationId": "req-8f2a",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "eventType": "ProductPublished",
  "payload": {
    "productId": "P-1001"
  }
}
~~~

Ý nghĩa:

- `eventId`: định danh event, dùng cho deduplication.
- `correlationId`: liên kết các bước trong cùng business flow.
- `causationId`: chỉ ra hành động hoặc message tạo ra event này.
- `traceparent`: W3C Trace Context nếu hệ thống tracing có truyền trace qua message.
- `payload`: dữ liệu nghiệp vụ tối thiểu cần cho consumer.

Không dùng một field thay thế tất cả. Event ID phục vụ tính duy nhất và idempotency; correlation ID phục vụ điều tra; trace context phục vụ phân tích latency. Tránh đặt email, access token hoặc nội dung cá nhân trong các ID này.

Nếu message broker/client đã hỗ trợ header propagation cho tracing, ưu tiên cơ chế instrumentation/propagator chuẩn thay vì tự parse và nối `traceparent` bằng string.

## 6. Distributed tracing với W3C Trace Context

W3C Trace Context định nghĩa header phổ biến:

- `traceparent`: chứa version, trace ID, parent span ID và trace flags.
- `tracestate`: mang thông tin vendor-specific nếu có.

Ví dụ dạng `traceparent`:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Ứng dụng thường không nên tự tạo trace ID và span ID bằng UUID rồi coi đó là distributed tracing. Trace backend cần span relationship, timing, status và parent-child context hợp lệ.

Với Spring Boot, Micrometer Tracing và OpenTelemetry instrumentation có thể tạo/propagate trace context và đưa trace/span ID vào log theo cấu hình. Elasticsearch HTTP client cần được instrumentation hỗ trợ hoặc được cấu hình để span outbound được tạo và context được truyền đi.

Một trace có thể giúp phân biệt:

- Thời gian chờ ở controller/service.
- Thời gian mapping/conversion phía client.
- Thời gian request qua HTTP transport.
- Thời gian server báo trong Elasticsearch response.
- Thời gian downstream xử lý sau khi search hoàn tất.

Đừng coi trace span duration bằng Elasticsearch field `took`. Span thường bao gồm cả network, connection pool, serialization và thời gian chờ; `took` là thời gian Elasticsearch báo cho phần xử lý request tương ứng.

## 7. Gắn X-Opaque-Id cho request Elasticsearch

Elasticsearch hỗ trợ header `X-Opaque-Id` để gắn một giá trị do client cung cấp với request. Giá trị này có thể giúp liên hệ request với log hoặc task phía Elasticsearch, tùy API và cấu hình/version.

Ví dụ HTTP:

~~~http
GET /products/_search
X-Opaque-Id: req-8f2a-es-search-1
~~~

Một số nguyên tắc:

- Dùng giá trị ngắn, không chứa PII hoặc secret.
- Có thể đưa request ID/correlation ID vào opaque ID.
- Có thể thêm operation suffix để phân biệt search, bulk hoặc update.
- Không dùng cùng một opaque ID cố định cho mọi request vì sẽ khó phân biệt.
- Không xem opaque ID là authentication token hoặc quyền truy cập.
- Xác nhận header được client gửi và server nhận trong môi trường đang chạy.

Opaque ID không thay thế W3C `traceparent`. Một giá trị phục vụ tra cứu request Elasticsearch không tự tạo ra trace span hoặc parent-child relationship.

## 8. Cấu hình header trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `ClientConfiguration` để cấu hình kết nối và một số HTTP headers mặc định. Với các version có API `withHeaders(...)`, có thể thêm header cho request qua supplier:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration =
        ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .withHeaders(() -> {
                    HttpHeaders headers = new HttpHeaders();
                    headers.add("X-Opaque-Id", "integration-test");
                    return headers;
                })
                .build();
~~~

Ví dụ trên dùng giá trị cố định phù hợp cho một test/client chuyên biệt. Chữ ký và hành vi của header supplier cần đối chiếu đúng version Spring Data Elasticsearch đang dùng.

Nếu muốn opaque ID thay đổi theo từng request:

1. Xác nhận supplier được gọi ở thời điểm gửi từng request trong version đang dùng.
2. Đọc request context từ cơ chế context propagation phù hợp.
3. Không đọc MDC ThreadLocal trong reactive flow nếu chưa có propagation.
4. Nếu API chỉ hỗ trợ default headers cố định, dùng HTTP client/transport interceptor hoặc request options có hỗ trợ per-request headers.
5. Kiểm thử header thực sự được gửi ở mỗi request và không bị giữ từ request trước.

Không cấu hình `X-Opaque-Id` thành một chuỗi cố định cho toàn bộ production traffic nếu mục tiêu là phân biệt từng request. Một header cố định chỉ có ích để nhận diện client/workload, không đủ để correlate từng operation.

Với trace propagation, ưu tiên OpenTelemetry/Micrometer instrumentation của HTTP client. Tránh tự gắn một `traceparent` tĩnh trong `ClientConfiguration`; traceparent phải phản ánh span hiện hành.

## 9. Request ID và trace context trong Reactor

Trong Spring WebFlux hoặc reactive Elasticsearch operations, một request có thể chạy trên nhiều thread. MDC dựa trên ThreadLocal không tự bảo đảm context được giữ nguyên khi Reactor chuyển scheduler.

Ví dụ flow:

~~~java
return productRepository.findByStatus("PUBLISHED")
        .flatMap(product -> enrichProduct(product))
        .doOnNext(product ->
                log.info("Product enriched")
        );
~~~

Nếu request ID chỉ được đặt vào MDC ở thread ban đầu, log bên trong `flatMap` có thể thiếu ID hoặc lấy nhầm giá trị khi context không được propagate đúng.

Các hướng xử lý:

- Dùng Micrometer Context Propagation và cấu hình Reactor integration phù hợp với Spring Boot version.
- Giữ request/correlation metadata trong Reactor Context.
- Dùng Micrometer Tracing/OpenTelemetry để quản lý trace context.
- Chỉ đưa giá trị cần log vào MDC tại boundary đã được context propagation hỗ trợ.
- Dọn ThreadLocal sau khi sử dụng; không tự giữ actor/request ID trong thread pool.

Minh họa đặt giá trị trong Reactor Context:

~~~java
return productRepository.findByStatus("PUBLISHED")
        .contextWrite(context ->
                context.put("correlationId", correlationId)
        );
~~~

Đọc context trong operator cần dùng API Reactor phù hợp, ví dụ `deferContextual`:

~~~java
Mono<String> currentCorrelationId =
        Mono.deferContextual(context ->
                Mono.just(context.get("correlationId"))
        );
~~~

Đây là ví dụ về Reactor Context, không phải một MDC bridge hoàn chỉnh. Trong ứng dụng thực tế, dùng instrumentation/context propagation đã được cấu hình và kiểm thử thay vì tự viết hook toàn cục thiếu kiểm soát.

## 10. Structured logging thay cho nối chuỗi tự do

Log có cấu trúc giúp truy vấn theo field, lọc theo service/index/operation và tạo dashboard.

Ví dụ log JSON:

~~~json
{
  "timestamp": "2026-11-13T10:15:30.123Z",
  "level": "INFO",
  "service": "catalog-api",
  "environment": "test",
  "message": "Elasticsearch search completed",
  "requestId": "req-8f2a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "operation": "search",
  "index": "products",
  "httpStatus": 200,
  "hitCount": 25,
  "durationMs": 42
}
~~~

Có thể ghi log theo key-value:

~~~java
log.info(
        "Elasticsearch operation completed: operation={}, index={}, durationMs={}, hitCount={}",
        "search",
        "products",
        duration.toMillis(),
        hitCount
);
~~~

Nếu dùng structured logging encoder, hãy cấu hình field thành JSON property thay vì chỉ tạo một message string dài.

Không đưa các giá trị sau vào log mặc định:

- Toàn bộ `_source` của document.
- Toàn bộ query DSL nếu chứa email, phone, token hoặc search term nhạy cảm.
- Password, API key, Authorization header.
- Cookie, session token, private key hoặc keystore password.
- URL có userinfo hoặc secret trong query parameter.
- Dữ liệu cá nhân không cần cho mục đích vận hành.

## 11. Allowlist field log an toàn

Một cách dễ kiểm soát là xác định allowlist metadata được phép log:

| Field | Có thể log? | Quy tắc |
|---|---|---|
| `requestId` | Có | Giới hạn độ dài/ký tự |
| `traceId`/`spanId` | Có | Lấy từ tracing instrumentation |
| `operation` | Có | Enum/giá trị do ứng dụng kiểm soát |
| `index` | Có điều kiện | Dùng tên index đã chuẩn hóa, không chứa secret |
| `durationMs` | Có | Số đo kỹ thuật |
| `httpStatus` | Có | Số trạng thái |
| `errorType` | Có | Loại lỗi, sau khi giới hạn độ dài |
| `documentId` | Có điều kiện | Có thể là dữ liệu định danh; hash/tokenize nếu cần |
| `tenantId` | Có điều kiện | Chỉ log nếu policy cho phép; cân nhắc pseudonymize |
| `queryBody` | Mặc định không | Chỉ log bản đã redact trong môi trường kiểm soát |
| `documentSource` | Mặc định không | Không log payload đầy đủ |
| `Authorization` | Không | Luôn loại bỏ |
| `password/apiKey` | Không | Luôn loại bỏ |

Allowlist thường an toàn hơn denylist. Denylist dễ bỏ sót field nhạy cảm mới được thêm vào sau này.

Nếu cần biết document nào gây lỗi, cân nhắc dùng ID đã hash bằng HMAC với secret quản lý riêng, thay vì ghi trực tiếp ID có thể chứa email hoặc mã khách hàng. Hash thường không thay thế hoàn toàn việc phân loại dữ liệu; vẫn cần đánh giá khả năng suy ngược và chính sách retention.

## 12. Redaction ở nhiều lớp

Che dữ liệu nên được thực hiện trước khi log rời khỏi ứng dụng, không chỉ dựa vào dashboard hoặc quyền xem log.

Các lớp nên xem xét:

1. **Application logging**: chỉ log metadata allowlist; không log object/query body mặc định.
2. **HTTP client logging**: tắt hoặc redact header/body nhạy cảm trước khi ghi.
3. **Exception logging**: kiểm tra exception message có chứa URL, query hoặc payload không.
4. **Proxy/gateway logs**: loại bỏ Authorization, Cookie và query parameter nhạy cảm.
5. **Elasticsearch slow logs**: giới hạn quyền truy cập và cân nhắc nội dung query.
6. **Log pipeline**: áp dụng masking bổ sung như lớp phòng vệ, không thay thế redaction tại nguồn.

Ví dụ một log an toàn:

~~~json
{
  "message": "Elasticsearch request failed",
  "requestId": "req-8f2a",
  "operation": "index",
  "index": "products-v2",
  "httpStatus": 400,
  "errorType": "mapper_parsing_exception",
  "field": "price",
  "durationMs": 18
}
~~~

Ví dụ log không an toàn:

~~~json
{
  "message": "Request failed",
  "authorization": "ApiKey ...",
  "password": "...",
  "document": {
    "customerEmail": "person@example.com",
    "phone": "+84...",
    "privateNotes": "..."
  }
}
~~~

Đừng chỉ thay password thành dấu sao nhưng vẫn ghi nguyên header Authorization hoặc toàn bộ body. Secret có thể xuất hiện ở nhiều dạng và nhiều lớp.

## 13. Không bật HTTP wire logging tràn lan

HTTP wire logging có thể hiển thị raw headers và request/response body. Đây là công cụ chẩn đoán sâu, nhưng có rủi ro lớn:

- Lộ Authorization/API key.
- Lộ document source và thông tin cá nhân.
- Lộ query search chứa dữ liệu người dùng.
- Tăng dung lượng log rất nhanh.
- Tạo overhead CPU/I/O và làm thay đổi timing của request.
- Log có thể bị gửi tới hệ thống lưu trữ có phạm vi truy cập rộng hơn Elasticsearch.

Chỉ bật trong thời gian ngắn, trên môi trường test/staging có dữ liệu giả, với quyền truy cập log hạn chế và quy trình tắt rõ ràng.

Tên logger cụ thể phụ thuộc HTTP client/transport và version, ví dụ logger của Apache HTTP client hoặc Netty. Không copy một logger name từ stack cũ rồi giả định nó bao phủ mọi transport.

Nếu cần kiểm tra header, ưu tiên log tên header và trạng thái có/không có credential thay vì giá trị header. Nếu cần kiểm tra body, dùng payload giả hoặc bản đã redact và giới hạn kích thước.

Không dùng packet capture hoặc wire log để thu thập credential production khi không có mục đích, quyền và quy trình bảo vệ phù hợp.

## 14. Log phía Elasticsearch và slow logs

Client log cho biết ứng dụng đã gửi request gì ở mức metadata và nhận kết quả ra sao. Elasticsearch server log giúp biết node xử lý request, shard và task như thế nào.

Các nguồn hữu ích:

- Elasticsearch server logs.
- Index search slow logs.
- Index indexing slow logs.
- Cluster/node stats và thread pool stats.
- Task API.
- Audit logs nếu security auditing được bật và cấu hình phù hợp.

Slow logs có thể ghi thông tin về query hoặc source tùy loại log và cấu hình. Query DSL có thể chứa dữ liệu người dùng; do đó, slow logs cũng cần quyền truy cập, retention và redaction phù hợp.

Một quy trình điều tra:

1. Lấy request ID/opaque ID từ application log.
2. Tìm cùng giá trị trong Elasticsearch server logs hoặc task metadata nếu version/API ghi nhận.
3. So sánh thời gian và index.
4. Xem slow log hoặc shard/node metrics quanh thời điểm đó.
5. Đối chiếu trace span để tách thời gian client/network/server.
6. Kết thúc điều tra bằng một thay đổi có thể đo lường, không để wire logging bật vô thời hạn.

Không phải mọi API hoặc log format đều lưu opaque ID giống nhau. Hãy xác minh trên phiên bản Elasticsearch đang dùng trước khi dựa vào nó như một khóa tra cứu duy nhất.

## 15. Tương quan giữa client duration và Elasticsearch took

Ví dụ log:

~~~json
{
  "operation": "search",
  "clientDurationMs": 820,
  "elasticsearchTookMs": 35,
  "httpStatus": 200,
  "hitCount": 50
}
~~~

Client duration lớn hơn nhiều so với Elasticsearch `took` có thể chỉ ra thời gian ngoài phần xử lý server:

- Chờ connection pool.
- DNS hoặc mở kết nối mới.
- TLS handshake.
- Network/load balancer.
- Serialize request và deserialize response.
- Retry ở client.
- Scheduler queue hoặc downstream backpressure.

Nếu cả hai cùng cao, cần điều tra query/shard/cluster load. Nếu Elasticsearch `took` thấp nhưng ứng dụng chậm, đừng vội tối ưu Query DSL; kiểm tra transport, connection pool và phần xử lý sau response.

Hai số đo không hoàn toàn đồng nhất vì cách đo và phạm vi khác nhau. Dùng trace span và client metrics để phân tích khoảng chênh.

## 16. Log bulk theo item mà không ghi payload

Bulk request có thể chứa hàng trăm hoặc hàng nghìn item. Nếu chỉ log một dòng "bulk failed", khó biết item nào thất bại. Nếu log toàn bộ body, có thể làm lộ toàn bộ dữ liệu.

Nên log summary và kết quả từng item ở mức metadata:

~~~json
{
  "message": "Elasticsearch bulk completed with failures",
  "requestId": "req-import-51",
  "operation": "bulk",
  "index": "products-v2",
  "itemCount": 500,
  "successCount": 493,
  "failureCount": 7,
  "failureTypes": {
    "mapper_parsing_exception": 5,
    "version_conflict_engine_exception": 2
  },
  "durationMs": 640
}
~~~

Với từng item lỗi, chỉ log field cần thiết:

- Item position hoặc internal item reference.
- Document ID đã được bảo vệ.
- Action type.
- Status/error type.
- Retry count.
- Event ID/correlation ID nếu không nhạy cảm.

Không log source đầy đủ để chỉ ra lỗi mapping. Có thể log tên field lỗi và loại dữ liệu dự kiến/thực tế đã được phân loại, tránh ghi giá trị cá nhân hoặc secret.

Nếu bulk được xử lý lại, giữ event ID/document ID để liên kết lần retry với lần đầu. Tránh dùng request ID mới làm mất liên hệ với batch gốc; có thể có một request ID mới cho lần gửi lại và giữ correlation ID chung.

## 17. Trace cho request reactive và async

Với reactive pipeline, trace context cần theo được publisher qua scheduler và outbound client. Với job async, context phải được truyền sang executor/message boundary theo instrumentation hoặc message propagator.

Các tình huống cần chú ý:

- `@Async` tạo thread mới.
- `CompletableFuture` chạy trên executor.
- Reactor `publishOn`/`subscribeOn`.
- Kafka/RabbitMQ listener.
- Scheduled job.
- Retry tạo nhiều attempt.
- Bulk worker xử lý nhiều event trong một batch.

Không tự copy mỗi `traceId` sang MDC rồi giả định span relationship được bảo toàn. Tracing framework phải tạo child span và quản lý context lifecycle.

Với message được xử lý sau nhiều phút hoặc nhiều giờ, có thể chọn tiếp tục trace qua message hoặc bắt đầu trace mới có link tới context cũ, tùy tracing design và retention. Correlation ID nghiệp vụ vẫn có thể tồn tại lâu hơn trace.

## 18. Log exception an toàn

Khi log exception, giữ stack trace để điều tra root cause, nhưng phải xem xét nội dung exception message.

Ví dụ:

~~~java
try {
    operations.save(document, indexCoordinates);
} catch (RuntimeException ex) {
    log.error(
            "Elasticsearch write failed: requestId={}, operation={}, index={}, documentId={}",
            requestId,
            "save",
            safeIndexName,
            safeDocumentReference,
            ex
    );
    throw ex;
}
~~~

Nếu exception message có request URL hoặc body, logger có thể vô tình ghi dữ liệu nhạy cảm dù các tham số log đã an toàn. Với client/exception version cụ thể, cần xác định thông tin nào exception giữ lại và có sanitizer phù hợp.

Không viết:

~~~java
log.error("Elasticsearch request failed: {}", requestBody, ex);
~~~

Cũng không ghi `ex.getMessage()` vào response HTTP công khai. Thông tin kỹ thuật chi tiết nên ở log có kiểm soát; client nhận mã lỗi ổn định và correlation ID để hỗ trợ tra cứu.

## 19. Log level và thời gian bật chẩn đoán

Một chính sách log level thực tế:

| Level | Dùng cho | Ví dụ |
|---|---|---|
| ERROR | Operation thất bại và cần xử lý | Search dependency unavailable |
| WARN | Kết quả không hoàn chỉnh hoặc retry gần hết giới hạn | Bulk có item lỗi, search shard partial |
| INFO | Mốc nghiệp vụ/operation quan trọng | Reindex bắt đầu/kết thúc |
| DEBUG | Chi tiết kỹ thuật đã được redact | Query type, index, page size |
| TRACE | Chẩn đoán sâu trong thời gian ngắn | HTTP transport detail trên test data |

Không ghi một INFO log cho mọi document trong bulk nếu ingestion có throughput cao. Dùng summary theo batch và metrics để theo dõi số lượng.

Nếu bật DEBUG/TRACE theo runtime logger configuration, cần có:

- Thời gian bật/tắt.
- Người phê duyệt hoặc ticket điều tra nếu môi trường yêu cầu.
- Phạm vi service/index cụ thể.
- Kiểm tra redaction trước khi bật.
- Tự động hoặc thủ công khôi phục log level.
- Theo dõi dung lượng và quyền truy cập log.

## 20. Metrics không nên dùng request ID làm label

Metrics thường được lưu theo chuỗi thời gian và label tạo ra các series riêng. Nếu mỗi request ID tạo một label value, cardinality sẽ tăng gần bằng số request và làm hệ thống metrics tốn bộ nhớ.

Nên dùng label có tập giá trị giới hạn:

~~~text
elasticsearch_requests_total{
  operation="search",
  outcome="success"
}

elasticsearch_requests_total{
  operation="bulk",
  outcome="failure"
}

elasticsearch_request_duration_seconds{
  operation="search"
}
~~~

Không nên:

~~~text
elasticsearch_requests_total{
  request_id="req-8f2a"
}
~~~

Request ID, trace ID và document ID phù hợp với log/trace để tra cứu một lần gọi cụ thể. Metrics nên tổng hợp theo operation, outcome, status class, index family hoặc service đã chuẩn hóa.

## 21. Bảo vệ log, trace và telemetry data

Log và trace có thể chứa dữ liệu nhạy cảm ngay cả khi không có password. Query search có thể chứa email, tên người dùng, số điện thoại, tenant ID hoặc nội dung người dùng nhập. Trace attribute có thể vô tình ghi URL/path chứa dữ liệu cá nhân.

Cần xác định:

- Ai có quyền xem log và trace.
- Dữ liệu nào được phép thu thập.
- Thời gian retention.
- Mã hóa khi truyền và khi lưu.
- Cách xóa/ẩn dữ liệu theo policy.
- Cách xử lý khi credential bị ghi nhầm.
- Cách ngăn secret xuất hiện trong alert, dashboard và CI artifact.

Không dùng trace baggage để mang token hoặc PII. Baggage có thể được propagate qua nhiều service và làm dữ liệu nhạy cảm lan rộng hơn.

Nếu cần liên kết một user với request, ưu tiên pseudonymous ID có chính sách rõ ràng thay vì email hoặc tên đầy đủ. Đừng thêm thông tin người dùng vào span name; span name nên mô tả operation như `Elasticsearch search products`.

## 22. Kiểm thử redaction và correlation

Không chỉ kiểm tra log bằng mắt trong một lần chạy. Nên có test bảo đảm secret không xuất hiện trong output.

Ví dụ test ý tưởng:

~~~java
@Test
void logsRequestMetadataWithoutCredentialOrDocumentSource() {
    // 1. Tạo request test với API key giả và document có dữ liệu nhạy cảm giả.
    // 2. Gửi request qua service với appender ghi log vào buffer.
    // 3. Đọc log output.
    // 4. Xác nhận requestId/operation/index/status có mặt.
    // 5. Xác nhận API key, password, email và source body không xuất hiện.
}
~~~

Các kịch bản nên có:

- Request ID được tạo khi header thiếu.
- Request ID đầu vào quá dài hoặc có newline bị từ chối/thay thế.
- Request ID được trả trong response header theo policy.
- Trace ID/span ID xuất hiện ở log khi tracing được bật.
- Opaque ID được gửi tới Elasticsearch client nếu đã cấu hình.
- Correlation ID được truyền qua message consumer.
- MDC được xóa sau request để tránh rò sang request tiếp theo.
- Reactor context được giữ qua scheduler boundary.
- Authorization/API key/password bị redact.
- Query/document payload không xuất hiện trong log mặc định.
- Exception có thông tin nhạy cảm không bị đưa nguyên văn vào public response.

Dùng secret giả có marker dễ tìm như `TEST_SECRET_DO_NOT_LOG`. Test có thể assert marker không xuất hiện trong captured logs. Không dùng credential production làm fixture kiểm thử.

## 23. Quy trình điều tra một request chậm hoặc thất bại

Khi có request ID từ người dùng hoặc alert:

1. Tìm request ID trong application logs.
2. Lấy trace ID và mở distributed trace tương ứng.
3. Xác định span gọi Elasticsearch và operation/index.
4. Đọc client duration, status, retry và exception category.
5. Lấy opaque ID nếu được gắn vào request Elasticsearch.
6. Tìm server log, slow log hoặc task metadata liên quan.
7. So sánh Elasticsearch `took` với client span duration.
8. Kiểm tra shard failure, timeout, thread pool hoặc mapping/authorization nếu có.
9. Đối chiếu bulk item summary nếu operation là bulk.
10. Xác định lỗi nằm ở ứng dụng, transport, cluster hay downstream.
11. Sửa nguyên nhân và xác nhận bằng trace/metric sau deploy.
12. Tắt diagnostic logging tạm thời và kiểm tra retention/access của dữ liệu thu thập.

Nếu không có trace backend, request ID và structured log vẫn có thể hỗ trợ điều tra. Nếu không có server-side opaque ID, vẫn có thể đối chiếu theo timestamp, index, operation và node logs, nhưng độ chính xác sẽ thấp hơn.

## 24. Những lỗi thường gặp

### Dùng một ID mới ở mọi lớp

Mỗi service tạo correlation ID riêng làm mất liên kết. Giữ request/correlation ID qua boundary và dùng trace/span framework để tạo span riêng.

### Dùng request ID như trace ID

Một request ID không tạo span tree hoặc timing. Dùng distributed tracing chuẩn và giữ request ID như metadata bổ sung.

### Đặt X-Opaque-Id cố định

Mọi request có cùng ID sẽ khó phân biệt. Dùng giá trị theo request nếu client hỗ trợ per-request header.

### Dựa vào MDC trong reactive flow

ThreadLocal có thể không theo publisher qua scheduler. Dùng Reactor Context và Micrometer/OpenTelemetry context propagation.

### Log toàn bộ request/response

Có thể làm lộ document, query, password hoặc API key. Ưu tiên allowlist metadata và redaction tại nguồn.

### Chỉ che Authorization header

Secret có thể xuất hiện trong exception message, URL, query parameter, environment dump hoặc wire logs. Kiểm tra nhiều lớp.

### Bật HTTP wire logging lâu dài

Wire log có payload, tốn tài nguyên và tăng lượng dữ liệu nhạy cảm. Chỉ bật ngắn hạn với dữ liệu giả và quyền truy cập hạn chế.

### Dùng trace ID làm metric label

Cardinality tăng nhanh. Giữ ID trong log/trace, metrics dùng label có tập giá trị giới hạn.

### Log raw query để điều tra search

Query có thể chứa thông tin người dùng. Log query type, field, page size và duration; chỉ dùng bản đã redact khi thực sự cần.

### Không dọn MDC

Thread pool tái sử dụng thread có thể mang request ID cũ sang request mới. Luôn cleanup trong finally.

### Coi log đã redact ở dashboard là đủ

Secret vẫn tồn tại trong log gốc hoặc bản sao. Redact trước khi ghi và kiểm thử output thực tế.

### Ghi opaque ID chứa PII

Opaque ID có thể xuất hiện trong log/task metadata. Dùng ID kỹ thuật ngẫu nhiên hoặc pseudonymous, không dùng email/token.

## 25. Quy trình triển khai

Khi xây dựng logging, request ID và tracing an toàn cho Spring Data Elasticsearch:

1. Xác định request ID, correlation ID, trace ID và span ID có vai trò riêng.
2. Tạo hoặc validate request ID tại API boundary.
3. Dùng Micrometer Tracing/OpenTelemetry cho distributed trace context.
4. Truyền correlation metadata qua async executor và message envelope.
5. Gắn Elasticsearch `X-Opaque-Id` khi cần tra cứu request phía server.
6. Xác nhận cơ chế header là per-request nếu ID cần thay đổi theo từng operation.
7. Dùng structured logging với allowlist field.
8. Không log source, query body hoặc Authorization header mặc định.
9. Redact exception, proxy, HTTP client và slow log theo cùng policy.
10. Giữ MDC lifecycle đúng và cấu hình Reactor Context propagation.
11. Dùng log level DEBUG/TRACE có thời hạn và scope nhỏ.
12. Dùng metrics label có cardinality thấp.
13. Giới hạn quyền truy cập và retention cho log/trace.
14. Kiểm thử correlation, context propagation và secret redaction.
15. Dùng request ID/trace/opaque ID để nối client log với Elasticsearch server log khi điều tra.

## Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Data Elasticsearch — Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch — X-Opaque-Id header](https://www.elastic.co/guide/en/elasticsearch/reference/current/api-conventions.html#api-opaque-id)
- [Elasticsearch — Search slow log](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-slowlog.html)
- [Elasticsearch — Indexing slow log](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-slowlog.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

## Kết luận

Log có cấu trúc cho biết operation và kết quả; request/correlation ID giúp tìm các log liên quan; trace ID/span ID mô tả hành trình và thời gian qua nhiều service; Elasticsearch `X-Opaque-Id` giúp gắn nhãn request phía server. Trong Spring Data Elasticsearch, hãy truyền context qua API, Reactor và message boundary bằng cơ chế phù hợp, đồng thời xác nhận header opaque ID thực sự được gửi theo từng request nếu cần. Dùng allowlist metadata, redaction tại nguồn và test bảo đảm secret/PII không xuất hiện trong log. Tránh log raw body, Authorization, API key hoặc wire traffic lâu dài; kết hợp client duration, Elasticsearch `took`, slow logs và trace để điều tra mà không làm lộ dữ liệu nhạy cảm.
