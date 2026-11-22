# Giới hạn kích thước nội dung, thời hạn và dữ liệu nhạy cảm trong log

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Tích hợp bảo mật  
**Mục tiêu:** Thiết lập các lớp bảo vệ Spring WebFlux trước payload quá lớn, request/response kéo dài, rò rỉ credential và PII trong log; phân biệt chính xác giới hạn codec, giới hạn HTTP body, multipart, timeout network và deadline nghiệp vụ.

## 1. Vì sao ba nhóm giới hạn phải đi cùng nhau?

WebFlux không dành một thread riêng cho mỗi request, nhưng vẫn tiêu tốn connection, buffer, CPU, bộ nhớ, file descriptor và dung lượng đĩa. Non-blocking I/O không tự chống denial of service. Ba rủi ro phổ biến:

1. Một client gửi body lớn hơn sức chứa decoder, hoặc stream dữ liệu vô hạn; application aggregate bằng `collectList()`, `bodyToMono(byte[].class)` hoặc `DataBufferUtils.join` không đặt trần.
2. Client gửi request rất chậm, upstream không phản hồi, hoặc pool đã đầy; application vẫn giữ subscription và resource lâu hơn SLA.
3. Request thất bại được log “cho dễ debug” cùng `Authorization`, cookie, URL có token, error payload, file name hoặc thông tin cá nhân.

Cấu hình tốt cần làm ba việc:

- **Byte budget:** giới hạn tại gateway, HTTP parser, decoder, multipart và từng route nghiệp vụ.
- **Time budget:** giới hạn chờ pool, DNS, TCP, TLS, response, input chậm, toàn business operation và streaming idle.
- **Information budget:** cho phép ghi một số metadata đã chọn vào log, không dump request/response của người dùng.

Một thiết kế chỉ có `spring.http.codecs.max-in-memory-size=64KB` **không** có nghĩa mọi HTTP request trên 64 KiB sẽ bị chặn. Đây là giới hạn bộ nhớ cho các codec khi cần tổng hợp dữ liệu, không phải trần byte của mọi luồng body.

## 2. Bản đồ ranh giới bảo vệ

```text
Untrusted browser / partner
          |
          v
Gateway / WAF / reverse proxy
  - header/URI/body quotas
  - concurrent request and rate limits
  - idle and slow-client deadlines
          |
          v
Reactor Netty HTTP server
  - HTTP parser limits
  - socket and connection lifecycle
          |
          v
Spring WebFlux codecs + handler
  - maxInMemorySize
  - multipart memory/disk/parts limits
  - per-route byte counter
  - validation and timeout
          |
          v
Reactive business service
          |
          v
WebClient -> connection pool -> TLS -> upstream
  - acquire / connect / response timeout
  - response decode cap
          |
          v
Logs / metrics / traces
  - method, route pattern, status, duration
  - no secrets, raw body, raw query
```

Các lớp bảo vệ không thay thế lẫn nhau. Gateway chặn request quá lớn trước JVM; decoder bảo vệ quá trình aggregate; route kiểm tra quota nghiệp vụ; deadline giúp giải phóng resource chậm; logging policy giữ dữ liệu nhạy cảm khỏi collector và hệ thống support.

| Giới hạn | Đơn vị | Mục đích | Không đảm bảo |
|---|---|---|---|
| Max header/request line | Byte hoặc ký tự theo server | Chặn header, URL quá lớn | Body size |
| Max HTTP body | Byte | Chặn payload vượt trần | Thời gian gửi |
| Codec maxInMemorySize | Byte aggregate | Chặn buffer quá lớn của decoder | Mọi stream raw |
| Multipart memory threshold | Byte/part | Spill file từ memory xuống disk | Max file upload |
| Multipart maxDiskUsagePerPart | Byte/part | Hạn chế file tạm | Tổng số part |
| Multipart maxParts | Số part | Chặn quá nhiều trường/file | Kích thước từng file |
| Pool acquire timeout | Thời gian | Không chờ pool quá lâu | TCP connect |
| Connect/response timeout | Thời gian | Không treo ở network stage | Toàn workflow |
| Reactor timeout | Thời gian | Deadline hoặc khoảng im lặng của publisher | Tự hủy side effect |
| Log allowlist | Trường dữ liệu | Bảo vệ secret/PII | Resource exhaustion |

## 3. Giới hạn buffer bằng codec WebFlux

WebFlux dùng `HttpMessageReader`, `HttpMessageWriter` và `DataBuffer`. Một số decoder cần gom bytes để tạo ra `String`, DTO JSON, form field hoặc toàn bộ một cấu trúc dữ liệu. Nhiều codec mặc định có giới hạn khoảng **256 KiB** cho buffer cần aggregate.

Khi giới hạn bị vượt, exception thường gặp:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Điều này là cơ chế bảo vệ, không phải lỗi cần xóa bằng cách nâng limit vô hạn.

### 3.1. Thuộc tính Spring Boot 3.5

```properties
spring.http.codecs.max-in-memory-size=64KB
spring.http.codecs.log-request-details=false
```

Trong Spring Boot 3.5, `spring.http.codecs.max-in-memory-size` cấu hình giới hạn bytes khi codec cần aggregate trên WebFlux server và các WebClient được Boot auto-configure. `log-request-details=false` tránh bật logging chi tiết form/headers tại các codec theo cấu hình Boot.

Một số tài liệu cũ dùng `spring.codec.max-in-memory-size`. **Không lấy property từ phiên bản khác** khi đang dùng Boot 3.5; kiểm tra đúng Common Application Properties của phiên bản ứng dụng.

Giới hạn trên không thay thế quota file, không giới hạn một event stream vô hạn và không bảo đảm được áp dụng nếu code tự tạo WebClient/codec mà bỏ qua Boot customizer.

### 3.2. Server: cấu hình trực tiếp

```java
@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(64 * 1024);
    }
}
```

Đây là snippet Spring cần imports. Nếu chỉ muốn chỉnh codec trong ứng dụng Boot, đừng tự thêm `@EnableWebFlux`: annotation đó đưa cấu hình WebFlux về chế độ Framework-managed và làm Boot WebFlux auto-configuration back off.

### 3.3. WebClient: giới hạn response aggregate

```java
WebClient client = WebClient.builder()
        .codecs(codecs ->
                codecs.defaultCodecs()
                        .maxInMemorySize(64 * 1024))
        .build();
```

Trường hợp `bodyToMono(String.class)` hoặc `bodyToMono(Dto.class)` có thể aggregate dữ liệu nên cần giới hạn. `bodyToFlux(DataBuffer.class)` cho phép xử lý bytes theo stream; khi đó ứng dụng chịu trách nhiệm kiểm soát tổng số byte và ownership/release buffer.

Không dùng `collectList()` trên response event vô hạn rồi tin rằng codec sẽ bảo vệ tổng heap; giới hạn codec và aggregate ở operator khác nhau.

## 4. Raw body: kiểm tra tổng số byte thực nhận

Một handler:

```java
@PostMapping("/raw")
public Mono<Void> process(@RequestBody Flux<DataBuffer> data) {
    return doSomethingWithBytes(data);
}
```

nhận raw buffer stream. Khi không qua decoder aggregate, tổng body có thể vượt nhiều lần `maxInMemorySize`. Với payload nhỏ, Spring cung cấp:

```java
Mono<DataBuffer> bounded =
        DataBufferUtils.join(data, 128 * 1024);
```

`DataBufferUtils.join(source, maxByteCount)` gom buffer đến số byte tối đa. Vượt giới hạn có thể phát `DataBufferLimitException`; lúc error/cancel, các buffer đã tích lũy được release theo contract của API. Khi nhận **buffer kết quả**, caller phải đọc và release buffer đó đúng một lần nếu đang sở hữu nó.

Ví dụ đọc buffer sau join:

```java
return DataBufferUtils.join(body, 128)
        .map(buffer -> {
            try {
                byte[] bytes =
                        new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes.length;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

Chỉ dùng `join` khi budget nhỏ và có thể aggregate. Với file 1 GiB, nên streaming tới storage và đếm byte từng buffer theo quota, hủy khi vượt, cleanup file chưa hoàn tất, đồng thời đặt hard cap ở gateway. Không gọi `collectList()` hoặc `join(source)` không giới hạn với dữ liệu không đáng tin.

### 4.1. Content-Length không phải bằng chứng

`Content-Length` có thể giúp từ chối sớm một request đã khai báo lớn, nhưng không thể dùng làm **kiểm tra duy nhất**:

- HTTP/1.1 có thể gửi chunked transfer.
- HTTP/2 và HTTP/3 có cơ chế framing khác.
- Reverse proxy có thể điều chỉnh transfer encoding.
- Client hoặc intermediary có thể khai báo không đáng tin cậy.
- Payload nén có thể nở rất lớn sau giải nén.

Giới hạn cần kiểm tra theo bytes thực tế ở đúng tầng trước khi tạo DTO/file. Nếu đọc archive hoặc compressed content, đặt riêng giới hạn **sau giải nén** để chống decompression/ZIP bomb.

### 4.2. Byte count khác số ký tự

UTF-8 không lưu mỗi ký tự bằng một byte. Chữ `é` có 2 byte UTF-8 nhưng String Java có length 1. Nhiều emoji chiếm 4 byte UTF-8 và 2 UTF-16 code units.

Do đó `String.length() <= 128` không phải quy tắc kiểm tra body <= 128 **bytes**. Hãy đếm bytes trước decode khi quota có đơn vị byte.

## 5. Multipart: memory, disk, headers và số part

Đối với `multipart/form-data`, Spring Boot 3.5 cung cấp:

```properties
spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=8KB
```

Giải nghĩa:

- `max-in-memory-size` giới hạn memory cho non-file part; với file part, là ngưỡng chuyển nội dung sang file tạm trên disk.
- `max-disk-usage-per-part` giới hạn disk usage mỗi part có lưu file.
- `max-parts` giới hạn số part trong request.
- `max-headers-size` giới hạn lượng memory cho header section của từng part.

**Sai:** cho rằng max-in-memory-size=64KB có nghĩa file lớn hơn 64KB bị từ chối. File có thể được ghi ra disk khi vượt ngưỡng. Vì thế phải đặt thêm disk quota, file size, tổng request size, số part và retention/cleanup.

Các kiểm tra bổ sung khi upload: file name từ client không đáng tin; normalize đường dẫn và đặt server-generated file name. Xác minh magic bytes/định dạng nội dung, không chỉ tin `Content-Type` hoặc đuôi file. Cân nhắc malware scanning và quota theo tenant.

### 5.1. Streaming bằng PartEvent

Spring WebFlux có thể xử lý multipart theo stream qua `@RequestBody Flux<PartEvent>`. `FormPartEvent` và `FilePartEvent` mang từng part/segment, với `PartEvent.isLast()` đánh dấu cuối part.

Ví dụ khái niệm:

```java
Flux<PartEvent> events = incomingPartEvents;
return events.windowUntil(PartEvent::isLast)
        .concatMap(window -> handleOnePart(window));
```

`incomingPartEvents` và `handleOnePart` là các abstraction minh họa, không phải chương trình độc lập. Khi dùng `PartEvent`, cần consume hoặc release mọi buffer, gồm các part bị bỏ qua. Hard cap tổng byte và part count vẫn phải được áp dụng ở tầng thích hợp.

## 6. Response upstream cũng cần giới hạn

Một WebClient gọi API bên ngoài có thể nhận response rất lớn hoặc không kết thúc:

```java
Mono<String> page = webClient.get()
        .uri("/reports/export")
        .retrieve()
        .bodyToMono(String.class);
```

Nếu body quá lớn, codec có thể ném `DataBufferLimitException`. Không chữa bằng cách đặt maxInMemorySize cực lớn mặc định cho tất cả client.

Các lựa chọn:

- JSON object nhỏ: `bodyToMono(Dto.class)` và codec limit rõ.
- Danh sách lớn: pagination hoặc cursor.
- NDJSON/SSE: `bodyToFlux(T.class)`, xử lý từng item, hạn chế concurrency.
- File lớn: stream `Flux<DataBuffer>` với byte counter, giới hạn dung lượng, quản lý buffer ownership.
- Error response: đọc error code có giới hạn; không log raw body trả về từ upstream.

Đặt giới hạn cho **response** không kém phần quan trọng so với request inbound. Đối tác có thể gửi payload sai format, lỗi proxy HTML rất dài hoặc file vượt hợp đồng.

## 7. Đừng nhầm size limit với rate limit

Body 1KB có thể nhỏ nhưng 100.000 request/giây vẫn đánh sập service. Cần kết hợp:

- Rate limiting theo principal/API key/tenant.
- Giới hạn số connection/request đồng thời.
- Bounded queue và pool acquire timeout.
- Quota tổng upload theo ngày/tenant.
- Bảo vệ CPU cho parser/decompression.
- Circuit breaker hoặc bulkhead khi gọi upstream.
- Authentication, authorization và audit policy riêng.

Rate limit theo IP có thể không đủ khi có NAT/proxy; `X-Forwarded-For` chỉ được tin khi proxy chain đã được cấu hình trusted. Không mặc định mọi client-provided header là định danh đã xác thực.

## 8. Phân biệt timeout theo từng giai đoạn

Một outbound WebClient request có thể mất thời gian tại nhiều nơi:

```text
subscribe
   |
   +-- DNS lookup
   +-- pool acquire
   +-- TCP connect
   +-- TLS handshake / proxy
   +-- send request
   +-- wait/read response
   +-- decode body
   +-- transform business result
   |
   v
complete / error / cancel
```

| Timeout | Bảo vệ | Ví dụ cấu hình |
|---|---|---|
| DNS query | Resolver | Netty resolver `queryTimeout` |
| Pending acquire | Chờ connection pool | `pendingAcquireTimeout` |
| TCP connect | Thiết lập socket | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake | SSL/TLS negotiation | `handshakeTimeout` |
| Proxy connect | Thiết lập proxy tunnel | `connectTimeoutMillis` |
| Response read | Chờ/đọc dữ liệu response | `HttpClient.responseTimeout` |
| Whole operation | Publisher nghiệp vụ | Reactor `timeout(Duration)` |
| Inbound slow request | Client gửi request quá chậm | Gateway/HTTP-server read/idle policy |
| Long-lived stream | Khoảng im lặng có thể chấp nhận | Streaming idle/heartbeat policy |

Ví dụ pool và transport:

```java
ConnectionProvider pool =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient netty = HttpClient.create(pool)
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000)
        .responseTimeout(Duration.ofSeconds(3));
```

Đây là snippet minh họa, cần import Reactor Netty/Netty. `ConnectionProvider` tự tạo cần được dispose theo lifecycle của ứng dụng; không tạo một provider trong mỗi request.

### 8.1. Reactor timeout: Mono và Flux có khác biệt

```java
Mono<Result> result = client.get()
        .uri("/result/{id}", id)
        .retrieve()
        .bodyToMono(Result.class)
        .timeout(Duration.ofSeconds(5));
```

Với `Mono` đơn giá trị, timeout hữu ích như deadline cho phép nhận kết quả. Nhưng `Flux.timeout(Duration)` thường giới hạn **khoảng im lặng giữa các tín hiệu**, không tự đảm bảo tổng lifetime stream không quá một con số. Một SSE stream hợp lệ 24 giờ vẫn có thể hoạt động nếu heartbeat đều và không có tổng deadline.

Đặt time budget riêng cho request business hữu hạn, và idle/heartbeat policy cho streaming vô hạn. Đừng dùng cùng một `timeout(3s)` cho JSON API và server-sent events.

### 8.2. Timeout và cancellation

Khi downstream timeout, nó thường cancel nguồn. Điều này có thể giải phóng socket/connection/buffer, nhưng **không bảo đảm** external side effect đã xảy ra ở upstream được rollback.

Với POST/payment, cần idempotency key và retry policy cẩn thận. Việc kết nối bị timeout không chứng minh upstream chưa xử lý giao dịch. Không tự động retry mọi lỗi với cùng request side-effecting.

### 8.3. Inbound slow client

`WebClient.responseTimeout` không bảo vệ HTTP server khỏi client inbound gửi từng byte rất chậm. Đặt timeout đọc header/body/idle ở gateway và server transport, cùng max concurrent connections và quota.

Không áp read timeout quá ngắn cho upload hợp lệ, nhưng cũng không để kết nối treo vô hạn. Chọn policy theo loại endpoint và mạng khách hàng; đo số request bị timeout thực tế.

## 9. Mã lỗi HTTP cần phản ánh nguyên nhân

| Trường hợp | Status phù hợp trong nhiều API | Lưu ý |
|---|---|---|
| Request body lớn hơn quota | 413 Content Too Large | Chủ động map nếu muốn ổn định |
| Header quá lớn | 431 Request Header Fields Too Large | Có thể bị proxy chặn |
| URI quá dài | 414 URI Too Long | Không log raw URI |
| JSON/form không hợp lệ | 400 Bad Request | Không chuyển mọi decode error thành 413 |
| Vượt rate limit | 429 Too Many Requests | Có thể dùng Retry-After |
| Gateway timeout khi gọi upstream | 504 Gateway Timeout | Không phải mọi timeout trong service là 504 |
| Server quá tải | 503 Service Unavailable | Có thể dùng Retry-After |
| Client hủy kết nối | Có thể không còn response để gửi | Cleanup/cancel đúng lifecycle |

`DataBufferLimitException` không bắt buộc tự biến thành HTTP 413 trong mọi phiên bản và đường xử lý. Nếu contract cần 413, xử lý exception rõ ràng và viết integration test.

Thông báo cho client nên dùng error code ngắn, không chứa stack trace, SQL, request body hoặc upstream error payload.

## 10. Threat model cho log

Logs, traces và metrics có thể được xuất sang collector, nhà cung cấp giám sát, object storage, support tickets và các dashboard nhiều người truy cập. Một token tồn tại trong log có thể sống lâu hơn phiên request.

**Không ghi mặc định:**

- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`.
- Access/refresh token, password, OTP, session ID, private key.
- Thông tin thanh toán, số định danh, email, số điện thoại hoặc PII không có mục đích rõ.
- Request/response body hoặc file upload content.
- Raw query string, full URI, webhook secret, signed URL.
- Error body/exception message của upstream khi chưa sanitize.
- Baggage/tracing metadata do caller cung cấp tùy ý.
- File name từ user, user agent hoặc referer nếu chứa dữ liệu riêng tư.

Không thể bảo vệ hoàn toàn chỉ bằng regex “mask password=...”: một field mới hoặc exception mới có thể lọt qua. Thiết kế **allowlist** — chỉ log những trường được phê duyệt — an toàn hơn log mọi thứ rồi cố redact.

### 10.1. Metadata nên ghi

Cho request HTTP:

- Method: `GET`, `POST`...
- Route **template**: `/api/orders/{id}`, không phải `/api/orders/8924`.
- Status hoặc outcome đã xác định.
- Thời gian xử lý, tính bằng milliseconds.
- Service name, environment, instance ID.
- Correlation/trace ID do thành phần đáng tin tạo.
- Error category hoặc mã lỗi đã chuẩn hóa.
- Byte count nếu có mục đích và được làm tròn/giới hạn thích hợp.

Không dùng raw URI, user ID hoặc request ID duy nhất làm **metric tag** có cardinality cao. Với traces, giữ attribute theo allowlist và không tự đính kèm body.

### 10.2. Log request details và wiretap

Spring Boot 3.5:

```properties
spring.http.codecs.log-request-details=false
logging.level.org.springframework.web=INFO
logging.level.reactor.netty=INFO
```

Tùy mức DEBUG/TRACE, request detail logging có thể ghi form data và headers nếu bật rõ. Tắt flag này không có nghĩa mọi custom filter, proxy hoặc APM sẽ tự bảo vệ dữ liệu.

Reactor Netty có wiretap để debug I/O. Không bật trong production có dữ liệu nhạy cảm:

```java
HttpClient riskyDiagnosticClient =
        HttpClient.create().wiretap(true);
```

Đoạn trên chỉ để nhận diện cấu hình rủi ro, **không** phải hướng dẫn cấu hình nên đưa vào production. Wiretap hoặc network trace có thể lộ headers/body. Muốn debug, dùng môi trường synthetic data, quyền đọc hạn chế và tắt sau chẩn đoán.

### 10.3. Exception log và error body

Cách nguy hiểm:

```java
log.error("request failed headers={} response={}",
        headers, rawResponseBody);
```

Cách tốt hơn:

```java
log.warn("upstream_failure service={} status={} code={}",
        "billing", upstreamStatus, normalizedErrorCode);
```

Các biến là minh họa. `normalizedErrorCode` phải đến từ allowlist của ứng dụng, không phải raw exception message được đổi tên. Nếu cần stack trace để debug, phải đảm bảo exceptions không nhúng request payload, và truy cập log được giới hạn.

## 11. Correlation ID và Reactor Context

Request ID giúp liên kết sự kiện mà không cần body. Nhưng nếu log nguyên `X-Request-Id` do attacker gửi, có thể gặp giá trị quá dài, ký tự xuống dòng hoặc log injection.

Ví dụ kiểm tra:

```java
static String safeRequestId(String value) {
    if (value != null
            && value.length() <= 64
            && value.matches("[A-Za-z0-9-]+")) {
        return value;
    }
    return UUID.randomUUID().toString();
}
```

Đây là snippet minh họa. Trong production, ưu tiên tracing/gateway ID có trust boundary rõ. Không dùng request ID như authentication credential.

WebFlux thường chạy nhiều request trên event-loop thread và chuyển thread giữa các operator. Vì thế `MDC` dựa trên `ThreadLocal` không tự bảo đảm propagation đúng theo subscriber. Dùng Reactor Context, Micrometer Context Propagation hoặc OpenTelemetry integration theo version. Nếu bridge MDC thủ công, phải cleanup cho complete, error và cancellation.

## 12. Ví dụ WebFilter chỉ ghi metadata

```java
@Component
public class SafeAccessLogFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        long started = System.nanoTime();

        String method = exchange.getRequest()
                .getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping
                                    .BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched" : pattern.toString();

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();
                    String code = status == null
                            ? "unknown"
                            : Integer.toString(status.value());

                    long ms = (System.nanoTime() - started)
                            / 1_000_000;

                    log.info(
                            "method={} route={} status={} duration_ms={} signal={}",
                            method, route, code, ms, signal.name());
                });
    }
}
```

Đây là snippet Spring với các imports tương ứng. Filter chỉ đọc method, **route pattern** và status/outcome; không đọc body, query hoặc headers. `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể null nếu không có route phù hợp.

Status tại thời điểm `doFinally` có thể chưa phải status cuối cùng của tầng error handler ngoài filter; vì thế trả “unknown” khi chưa biết, không suy đoán mọi error là 500. Muốn access log phản ánh status đã commit thì instrument ở đúng lifecycle server/gateway.

## 13. Bảo vệ dữ liệu log sau khi ghi

Các biện pháp vận hành:

1. Phân quyền đọc logs/traces theo least privilege.
2. Encryption khi truyền và khi lưu.
3. Giới hạn retention, tránh giữ debug log vô hạn.
4. Không gửi production payload đến workspace test/support.
5. Tách security audit log khỏi log ứng dụng thông thường.
6. Có quy trình ứng phó khi token/PII đã bị log.
7. Quét định kỳ log fields, proxy access logs, APM attributes.
8. Hạn chế sampling của traces nhạy cảm và sanitize từ instrumentation layer.
9. Không bật Logbook/HTTP body recorder vô điều kiện.
10. Test log policy như một thành phần của security QA.

Sampling chỉ giảm tần suất ghi, **không** biến dữ liệu nhạy cảm thành an toàn.

## 14. Chương trình Java 17+ chạy được: hard cap, safe log và timeout

Project dưới đây dùng **Spring Boot 3.5.16** và Java 17. Endpoint `POST /api/notes` nhận `text/plain` qua `Flux<DataBuffer>`. Ứng dụng chặn vượt **128 byte** bằng `DataBufferUtils.join(body, 128)` và trả HTTP 413. Một client outbound có giới hạn codec 64 KiB và Netty connect/response timeout. Filter ghi method, route template, status, thời gian, không ghi body.

Integration test gửi đúng 128 ASCII byte, 129 byte và 65 ký tự `é` (130 byte UTF-8). Test cuối xác nhận `timeout` phát error theo virtual time.

### 14.1. Cấu trúc

```text
secure-webflux-limits/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SecurityLimitApplication.java
    │   ├── java/demo/LimitedNotesController.java
    │   ├── java/demo/SafeAccessLogFilter.java
    │   ├── java/demo/OutboundClientConfiguration.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/SecurityLimitTest.java
```

### 14.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>secure-webflux-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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
```

### 14.3. application.properties

```properties
spring.application.name=secure-webflux-limits
server.port=8080

spring.http.codecs.max-in-memory-size=64KB
spring.http.codecs.log-request-details=false

spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=8KB

logging.level.org.springframework.web=INFO
logging.level.reactor.netty=INFO
```

Nhớ rằng giới hạn 128 byte của endpoint là code trong controller; các properties này chỉ đặt policy codec và multipart cho toàn ứng dụng.

### 14.4. SecurityLimitApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLimitApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLimitApplication.class, args);
    }
}
```

### 14.5. LimitedNotesController.java

```java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class LimitedNotesController {

    private static final int MAX_BYTES = 128;

    @PostMapping(
            path = "/api/notes",
            consumes = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> upload(
            @RequestBody Flux<DataBuffer> body) {

        return DataBufferUtils.join(body, MAX_BYTES)
                .map(buffer -> {
                    try {
                        byte[] bytes =
                                new byte[buffer.readableByteCount()];

                        buffer.read(bytes);

                        String note = new String(
                                bytes, StandardCharsets.UTF_8);

                        if (note.isBlank()) {
                            return ResponseEntity.badRequest()
                                    .body("empty note");
                        }

                        // Không log hoặc phản hồi lại nội dung note.
                        return ResponseEntity.ok(
                                "bytes=" + bytes.length);
                    }
                    finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .switchIfEmpty(Mono.just(
                        ResponseEntity.badRequest()
                                .body("empty note")))
                .onErrorResume(
                        DataBufferLimitException.class,
                        e -> Mono.just(
                                ResponseEntity
                                        .status(HttpStatus.PAYLOAD_TOO_LARGE)
                                        .body("payload too large")));
    }
}
```

Code đếm raw bytes bằng `DataBufferUtils.join` trước khi decode thành String, nên 65 chữ `é` có 130 byte và sẽ bị chặn. `finally` release buffer kết quả. `DataBufferUtils` xử lý accumulated buffer cleanup khi join chưa thành công vì error/cancel. Handler trả message an toàn, không chứa body.

Đây là ví dụ giới hạn một note nhỏ; ứng dụng thực tế phải bổ sung authentication, validation, anti-abuse, gateway quota và storage security. Không dùng `join` để lưu upload lớn.

### 14.6. SafeAccessLogFilter.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class SafeAccessLogFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAccessLogFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        long started = System.nanoTime();
        String method =
                exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
                .doFinally(signal -> {
                    Object pattern = exchange.getAttribute(
                            HandlerMapping
                                    .BEST_MATCHING_PATTERN_ATTRIBUTE);
                    String route = pattern == null
                            ? "unmatched"
                            : pattern.toString();

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();

                    String code = status == null
                            ? "unknown"
                            : Integer.toString(status.value());

                    long ms = (System.nanoTime() - started)
                            / 1_000_000;

                    log.info(
                            "method={} route={} status={} duration_ms={} signal={}",
                            method, route, code, ms, signal.name());
                });
    }
}
```

Filter chỉ ghi route pattern (không raw URI), method và metadata. Nếu exception handler ngoài filter quyết định status sau đó, status tại `doFinally` có thể chưa phải HTTP status cuối; đây là instrumentation phục vụ học, không phải thay thế đầy đủ access log của gateway. Không có request body/headers/query string trong thông điệp log này.

### 14.7. OutboundClientConfiguration.java

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfiguration {

    @Bean
    WebClient partnerClient(WebClient.Builder builder) {
        HttpClient netty = HttpClient.create()
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder
                .baseUrl("https://api.example.org")
                .clientConnector(
                        new ReactorClientHttpConnector(netty))
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(64 * 1024))
                .build();
    }
}
```

`HttpClient.create()` dùng shared Reactor Netty resources theo mặc định, tránh việc demo tự tạo pool cần dispose riêng. Bean chỉ làm mẫu cấu hình; test không truy cập host bên ngoài. Trong production, nếu cần pool riêng, hãy tạo `ConnectionProvider` do lifecycle bean hoặc `ReactorResourceFactory` quản lý.

### 14.8. SecurityLimitTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityLimitTest {

    @Autowired
    WebTestClient client;

    @Test
    void permitsBodyAtExactByteLimit() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(128))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("bytes=128");
    }

    @Test
    void rejectsOneByteOverLimit() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(129))
                .exchange()
                .expectStatus().isEqualTo(413)
                .expectBody(String.class)
                .isEqualTo("payload too large");
    }

    @Test
    void unicodeIsMeasuredInUtf8Bytes() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("é".repeat(65))
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void timeoutCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                        Mono.delay(Duration.ofSeconds(10))
                                .thenReturn("late")
                                .timeout(Duration.ofSeconds(1)))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }
}
```

Chạy từ thư mục project, với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả dự kiến:** bốn test PASS, Maven exit code 0. Test 1 xác nhận status 200 và body `bytes=128`. Test 2 và 3 xác nhận status 413, trong đó test 3 phân biệt bytes UTF-8 và Java String length. Test 4 xác nhận `TimeoutException` bằng virtual time.

Nhật ký build/startup, port ngẫu nhiên và thời gian test khác nhau theo môi trường; không nên hard-code stdout. Test virtual time **không thay thế** test timeout transport: muốn kiểm tra Netty connect/response timeout, dùng server giả lập chậm và test pool/DNS/network failure riêng.

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

Gửi một note thường:

```bash
curl -i -X POST "http://localhost:8080/api/notes" -H "Content-Type: text/plain" --data-binary "hello"
```

HTTP status dự kiến là 200, body:

```text
bytes=5
```

Không đặt secret ở command line thật; command history hoặc process list có thể lưu lệnh và header nhạy cảm.

## 15. Kiểm tra bằng integration test và chaos test

Ngoài bốn test demo, cần kiểm tra các luồng thực tế:

| Test | Mục tiêu |
|---|---|
| Request 0 byte hoặc blank note | 400 theo contract |
| Request đúng max | Chấp nhận byte count chính xác |
| Request max+1 | 413 |
| Nhiều Unicode và emoji | Đếm byte thay ký tự |
| Chunked input không Content-Length | Quota vẫn được áp dụng |
| Compressed input | Không vượt budget sau giải nén |
| Multipart nhiều file | Disk quota và max parts |
| Client cancel giữa upload | Buffer/temp file cleanup |
| Upstream response quá lớn | Codec/streaming cap |
| Upstream chậm hơn response timeout | Dừng hoặc lỗi đúng policy |
| Connection pool bão hòa | Pending acquire timeout |
| Client gửi rất chậm | Gateway/server read timeout |
| Logs có Authorization/cookie/body | Không có secrets |
| Error body chứa token | Chỉ log normalized error code |
| Request ID chứa newline | Validate hoặc thay ID |
| SSE hợp lệ với heartbeat | Không bị timeout sai |

Đối với outbound WebClient, cần mock HTTP server/embedded Netty server để mô phỏng response chậm, lớn, malformed hoặc đóng kết nối. Không chỉ dùng fake `ExchangeFunction` nếu mục tiêu là kiểm chứng TCP timeout hoặc pool.

Với logging, dùng output capture hoặc test appender để khẳng định sample secret không xuất hiện trong logs của application. Thử cả error path, DEBUG/TRACE, upstream exception, reverse proxy và APM.

## 16. Lỗi phổ biến

1. **Dùng `maxInMemorySize` như total request cap.** Raw streaming không tự chịu giới hạn aggregate của codec.
2. **Nâng codec limit vô hạn.** Gây heap pressure và mở đường DoS.
3. **Đếm `String.length()` thay byte.** UTF-8 nhiều byte, quota sai.
4. **Chỉ tin `Content-Length`.** Chunked, proxy hoặc compressed body có thể khác.
5. **Coi multipart max-in-memory-size là max file size.** File có thể spill ra disk.
6. **Không đặt max-parts.** Request có nhiều trường/file gây tốn tài nguyên.
7. **Không giới hạn disk hoặc dọn file tạm.** Có thể đầy filesystem.
8. **`join` toàn body lớn không giới hạn.** Memory spike hoặc DataBuffer leak.
9. **Không release DataBuffer owned.** Netty pooled buffer có thể leak.
10. **Release DataBuffer hai lần.** Ownership sai có thể gây lỗi.
11. **Dùng responseTimeout như total deadline.** DNS/pool/connect/TLS khác với response read.
12. **Đặt timeout quá ngắn cho SSE/streaming.** Heartbeat và idle policy cần riêng.
13. **Retry POST sau timeout không idempotency.** Có thể tạo side effect trùng.
14. **Bật wiretap trong production.** Nguy cơ lộ HTTP body và credentials.
15. **Log toàn bộ headers.** Authorization/Cookie/API key rò rỉ.
16. **Log full URI/query.** Signed URL, email hoặc token có thể nằm trong query.
17. **Log raw exception message.** Upstream exception có thể chứa URL/bind values.
18. **Ghi actual user ID thay route pattern.** Rò dữ liệu và metric cardinality cao.
19. **Tin raw X-Request-Id.** Log injection hoặc giá trị dài ngoài kiểm soát.
20. **MDC ThreadLocal không bridge đúng.** Có thể lẫn request trong reactive chain.
21. **Dùng một policy cho JSON, upload và SSE.** Mỗi loại payload có SLA riêng.
22. **Không giới hạn outbound response.** Data từ upstream cũng không tin cậy.
23. **Cho rằng INFO log là bảo đảm an toàn.** Proxy, APM hoặc custom filter vẫn có thể log body.
24. **Chỉ bật sampling nhưng không mask secret.** Một token vẫn có thể bị lộ.
25. **Trả stack trace/SQL tới client.** Lộ internals và dữ liệu nhạy cảm.
26. **Dùng 504 cho mọi timeout.** 504 chủ yếu đúng khi gateway/upstream timeout.
27. **Bỏ qua hậu quả cancellation.** Side effect đã thực hiện có thể không rollback.
28. **Không đo pool queue/active connections.** Size cap không xử lý resource contention.
29. **Không test error path của giới hạn.** Có thể trả status sai hoặc leak buffer khi lỗi.
30. **Coi non-blocking là security control.** Reactive I/O không thay authentication/quota.

## 17. Checklist trước production

- Đã có header/request-line/body limit ở edge/gateway?
- Codec `maxInMemorySize` phù hợp JSON/form aggregation?
- Raw body và streaming upload có tổng byte hard limit riêng?
- Multipart có memory/disk/part/header limit và cleanup?
- Quota tính bytes thật, không chỉ `String.length()` hoặc Content-Length?
- Có giới hạn dữ liệu sau decompression để tránh ZIP bomb?
- Rate/concurrency quotas có phù hợp user/tenant?
- WebClient có response decode cap, bounded pool, connect/read timeout?
- Timeout inbound slow client và outbound upstream được tách biệt?
- Deadline Mono/Flux có hiểu khác biệt first signal vs inter-signal?
- Cancellation dọn resource, đồng thời side effects có idempotency?
- Log chỉ có method, route pattern, status, duration, ID hợp lệ?
- Không log Authorization, Cookie, body, query, exception payload?
- `spring.http.codecs.log-request-details` và Netty wiretap an toàn?
- Metrics/tracing không chứa PII hoặc high-cardinality user input?
- Log retention, encryption, access control và incident response đã rõ?
- Test có bao phủ bytes 128/129, Unicode, multipart, slow client, errors và logs?
- Các cấu hình được chọn theo đúng Spring Boot/Netty version?

**Ghi nhớ:** Bảo mật WebFlux cần phối hợp **content size**, **time limits** và **log minimization**. `spring.http.codecs.max-in-memory-size` bảo vệ codec aggregation, không phải mọi request. Multipart cần cả memory/disk/max-parts; raw `DataBuffer` cần hard cap byte và release đúng contract. Timeout pool/connect/TLS/response khác deadline toàn publisher, và không tự bảo vệ inbound slow client. Log an toàn dựa trên allowlist metadata, không dựa vào việc log hết rồi mask sau. Kiểm chứng bằng integration tests và quan sát tài nguyên thực tế.

## Tài liệu tham khảo

- Spring Boot 3.5 — [Common Application Properties: HTTP codecs and multipart limits](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- Spring Framework — [WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [WebClient Configuration: maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [DataBufferUtils.join with maxByteCount Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
- Spring Framework — [Multipart Content, PartEvent streaming](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html).
- Spring Framework — [Reactive Core, DataBuffer and codec limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Boot — [Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html).
- Reactor Netty — [HTTP Client timeout configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- OWASP — [Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).
