# Phân biệt lỗi kết nối, timeout, codec và status lỗi khi đọc phản hồi WebClient

## 1. Xác định lỗi phát sinh ở tầng nào

`WebClient` là HTTP client reactive của Spring WebFlux. Một request có thể thất bại ở nhiều thời điểm:

~~~text
Ứng dụng gọi WebClient
        |
        v
  Tạo request / encode body
        |
        v
  Lấy connection từ pool
        |
        v
  DNS -> TCP connect -> TLS
        |
        v
  Gửi request tới server
        |
        v
  Nhận HTTP status + headers
        |
        v
  Đọc response body
        |
        v
  Codec decode bytes thành DTO
        |
        v
  Ứng dụng nhận kết quả
~~~

Bốn nhóm cần phân biệt:

1. **Lỗi kết nối/transport**: client không thiết lập hoặc duy trì được trao đổi HTTP; thường không nhận được một HTTP response hoàn chỉnh.
2. **Timeout**: một giai đoạn như chờ connection, kết nối, TLS hoặc đọc response vượt thời gian cho phép.
3. **Lỗi codec**: đã có response/body nhưng Spring không thể đọc hoặc chuyển bytes thành kiểu Java mà ứng dụng yêu cầu.
4. **Lỗi HTTP status**: server hoặc gateway đã trả một status thuộc nhóm lỗi, thường là 4xx hoặc 5xx.

Điểm quan trọng là **HTTP 504 và timeout do client tạo ra không phải cùng một loại lỗi**. HTTP 504 là một response thực sự từ gateway. Timeout phía client có thể xảy ra trước khi nhận status hoặc trong khi đang đọc body.

## 2. Bảng nhận diện nhanh

| Nhóm | Dấu hiệu thường gặp | Có HTTP status không? | Ví dụ |
| --- | --- | --- | --- |
| Kết nối/transport | `WebClientRequestException`, root cause là IOException hoặc lỗi mạng | Thường không | Connection refused, DNS failure, TLS handshake failure, connection reset |
| Timeout | `TimeoutException`, `ReadTimeoutException`, `ConnectTimeoutException`, `PoolAcquireTimeoutException` | Tùy giai đoạn | Chờ connection pool, connect quá lâu, response không tới kịp |
| Codec | `DecodingException`, `CodecException`, `UnsupportedMediaTypeException`, `DataBufferLimitException` | Có thể đã nhận 2xx | JSON sai cú pháp, Content-Type không có decoder phù hợp, body vượt giới hạn buffer |
| HTTP status | `WebClientResponseException` và các subclass | Có | 400, 401, 404, 429, 500, 503, 504 |

Tên exception là dấu hiệu đầu tiên, không phải toàn bộ chẩn đoán. Một số timeout của Reactor Netty có thể nằm trong cause chain của `WebClientRequestException`. Hãy kiểm tra cả exception ngoài cùng và nguyên nhân sâu nhất.

## 3. Lỗi kết nối: WebClientRequestException

`WebClientRequestException` là exception Spring dùng cho lỗi liên quan tới việc thực hiện request. Nó chứa metadata của request như:

- HTTP method.
- URI.
- Request headers.
- Exception gốc (cause), thường cho biết nguyên nhân transport cụ thể.

Các nguyên nhân thường gặp:

| Root cause / dấu hiệu | Ý nghĩa |
| --- | --- |
| `UnknownHostException` | DNS không phân giải được hostname |
| `ConnectException: Connection refused` | Host có thể truy cập nhưng không có service lắng nghe tại port đó, hoặc firewall chủ động từ chối |
| `ConnectTimeoutException` | Không thiết lập được TCP connection trong thời gian cho phép |
| `SSLException` | TLS/certificate/handshake gặp vấn đề |
| `PrematureCloseException` | Connection đóng trước khi response hoàn tất |
| `IOException` | Lỗi I/O trong lúc gửi hoặc nhận dữ liệu |
| `WebClientRequestException` | Lớp Spring bọc lỗi thực hiện request và giữ request metadata |

### 3.1. Connection refused khác HTTP 503

**Connection refused** xảy ra ở tầng kết nối. Client không nhận được HTTP status từ service đích.

**HTTP 503 Service Unavailable** là một HTTP response có status và headers. Server hoặc gateway đã nhận request ở một mức nào đó và chủ động trả lời rằng service tạm thời không sẵn sàng.

Hai tình huống có hướng xử lý khác nhau:

- Connection refused: kiểm tra hostname, port, service process, network route, firewall, container/service discovery và connection pool.
- HTTP 503: kiểm tra health của service, overload, maintenance, gateway policy, `Retry-After` và giới hạn tải.

Tương tự, gateway trả HTTP 502/504 vẫn là một response có status. Đừng gộp chúng với trường hợp client không kết nối được tới gateway.

### 3.2. Đọc request metadata và root cause

~~~java
try {
    client.get()
            .uri("/v1/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .block(Duration.ofSeconds(5));
}
catch (WebClientRequestException ex) {
    log.warn("Request failed: method={}, uri={}, cause={}",
            ex.getMethod(),
            ex.getUri(),
            ex.getMostSpecificCause().getClass().getSimpleName());
    throw ex;
}
~~~

Đây là ví dụ ở boundary đồng bộ hoặc trong test. Trong service reactive, nên compose error signal bằng `doOnError`, `onErrorMap` hoặc `onErrorResume` thay vì gọi `block()`.

Không log toàn bộ request headers nếu có Authorization, Cookie hoặc API key. URI cũng có thể chứa token hoặc dữ liệu cá nhân trong query string; hãy redact trước khi log.

## 4. Timeout: xác định timeout ở giai đoạn nào

Một request WebClient có nhiều mốc thời gian. Cấu hình một timeout chung có thể che mất nguyên nhân thật.

### 4.1. Các giai đoạn timeout

| Giai đoạn | Cấu hình / exception thường gặp | Ý nghĩa |
| --- | --- | --- |
| DNS | Resolver query timeout; ví dụ `UnknownHostException` hoặc lỗi resolver | Không tìm được địa chỉ IP kịp thời |
| Connection pool | `pendingAcquireTimeout` / `PoolAcquireTimeoutException` | Không lấy được connection rảnh từ pool |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` / `ConnectTimeoutException` | Không thiết lập TCP connection kịp thời |
| TLS handshake | `handshakeTimeout` / lỗi SSL | Không hoàn tất thương lượng TLS |
| Response/read | `responseTimeout`, `ReadTimeoutHandler` / lỗi read timeout | Server không gửi dữ liệu response trong khoảng thời gian cho phép |
| Publisher-level | `Mono.timeout(Duration)` / `TimeoutException` | Reactive operation không phát signal trong thời gian quy định |

Với Reactor Netty, tài liệu hiện hành ghi nhận các mặc định đáng chú ý:

- Pending connection acquire timeout: 45 giây.
- TCP connect timeout: 30 giây.
- TLS handshake timeout: 10 giây.
- DNS query timeout: 5 giây.
- `responseTimeout` không được đặt mặc định.

Các con số phụ thuộc connector, resolver và cấu hình ứng dụng. Nếu dùng JDK HttpClient, Jetty hoặc Apache HttpComponents thay cho Reactor Netty, cách cấu hình và exception có thể khác.

### 4.2. Cấu hình connection timeout và response timeout

Với Reactor Netty:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

- `CONNECT_TIMEOUT_MILLIS` giới hạn thời gian thiết lập TCP connection.
- `responseTimeout` cấu hình timeout cho response/read phase của Reactor Netty.
- Hai cấu hình này không phải deadline tổng cho toàn bộ business operation.

Nếu ứng dụng dùng connection pool riêng, có thể cấu hình thời gian chờ lấy connection:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("partner-api")
        .maxConnections(50)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));
~~~

Chỉ tạo pool riêng khi có nhu cầu vận hành cụ thể. Connection pool có giới hạn giúp kiểm soát concurrency; pending acquire timeout giúp request thất bại sớm khi pool đã bão hòa.

### 4.3. Timeout ở mức Reactor Publisher

Có thể đặt deadline cho operation:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(8));
~~~

`timeout` của Reactor áp dụng trên Publisher từ lúc subscribe và bao phủ quá trình thực hiện operation tới khi có signal tiếp theo. Với `Mono` có một kết quả, cách này thường được dùng như deadline tổng cho request. Với `Flux` streaming, timeout có semantics theo khoảng chờ giữa các signal; nó không nhất thiết là giới hạn tổng thời gian của toàn stream.

Nên dùng timeout chuyên biệt của connector cho từng giai đoạn và thêm Publisher timeout làm giới hạn tổng phù hợp với SLA. Đừng đặt một timeout quá ngắn rồi retry liên tục, vì điều đó có thể làm tăng tải lên service đang chậm.

### 4.4. ReadTimeoutHandler và WriteTimeoutHandler

Khi cần kiểm soát read/write ở mức Netty channel:

~~~java
HttpClient httpClient = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

Các handler này có phạm vi ở tầng channel. Cần hiểu cách chúng tương tác với connection pooling và nhiều request dùng chung connection trước khi áp dụng toàn cục. Với đa số WebClient request/response thông thường, bắt đầu bằng connect timeout và response timeout thường dễ kiểm soát hơn.

### 4.5. HTTP 504 khác TimeoutException

| Tình huống | Cách nhận diện |
| --- | --- |
| Gateway trả 504 | `WebClientResponseException.GatewayTimeout` hoặc `WebClientResponseException` với status 504 |
| Reactor timeout | `java.util.concurrent.TimeoutException` |
| Netty read timeout | Thường có `ReadTimeoutException` trong cause chain |
| Connect timeout | Có thể có `ConnectTimeoutException` trong cause chain |
| Pool acquire timeout | Có thể có `PoolAcquireTimeoutException` |

Nếu gateway trả 504, client đã nhận một HTTP response. Nếu Reactor timeout trước khi có response, client không có status để đọc. Đây là khác biệt quan trọng khi log, retry và đo SLA.

## 5. Lỗi codec: response đã tới nhưng body không giải mã được

Codec chuyển dữ liệu HTTP thành kiểu Java. Ví dụ:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Spring chọn decoder dựa trên kiểu target và Content-Type của response. Một request có thể nhận status 200 nhưng vẫn thất bại khi đọc body.

### 5.1. JSON sai cú pháp hoặc không khớp kiểu dữ liệu

Server trả:

~~~json
{
  "id": "not-a-number",
  "name": "WebFlux"
}
~~~

Trong khi DTO khai báo:

~~~java
public record Product(long id, String name) {
}
~~~

Jackson có thể không chuyển chuỗi `not-a-number` thành `long`. Lỗi được biểu diễn qua `DecodingException` hoặc exception codec liên quan, tùy decoder và phiên bản.

Cần kiểm tra:

- JSON có hợp lệ không.
- Tên field có khớp contract không.
- Kiểu dữ liệu có tương thích không.
- Nullable/missing field có được hỗ trợ không.
- DTO có constructor/record/accessor mà Jackson nhận diện được không.
- Server có trả trang HTML hoặc nội dung proxy thay cho JSON không.

### 5.2. Content-Type không phù hợp

Ví dụ server trả JSON nhưng khai báo `Content-Type: text/plain`, trong khi client yêu cầu `Product.class`. Spring có thể không tìm được decoder phù hợp và phát `UnsupportedMediaTypeException`.

Phân biệt hai tình huống:

- **Client codec không đọc được response media type**: lỗi codec ở phía client.
- **Server trả HTTP 415 Unsupported Media Type**: đây là HTTP status response từ server, thường liên quan tới media type của request mà server không chấp nhận.

Tương tự, HTTP 406 Not Acceptable là status server trả khi không thể đáp ứng representation mà client yêu cầu; nó không đồng nghĩa với lỗi JSON decoder phía client.

### 5.3. DataBufferLimitException

Spring đặt giới hạn buffer để tránh việc đọc một response quá lớn vào memory. Với default codecs, giới hạn mặc định là 256 KiB. Khi body cần aggregate vượt giới hạn, có thể gặp:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Nếu payload hợp lệ và nghiệp vụ cần buffer lớn hơn, có thể tăng giới hạn:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Cấu hình này tăng giới hạn lên 2 MiB cho default codecs. Không tăng vô hạn để che lỗi. Với file lớn, JSON stream hoặc dữ liệu liên tục, hãy dùng streaming API như `bodyToFlux` thay vì gom toàn bộ response vào một object.

### 5.4. Codec error không phải lỗi kết nối

Khi client đã nhận status 200 và headers, nhưng JSON malformed, đây là lỗi decode. Server có thể vẫn hoạt động bình thường và TCP connection vẫn tốt.

Cách điều tra:

1. Ghi nhận status và response Content-Type.
2. Xác minh response body có đúng contract không.
3. Kiểm tra target DTO và decoder được đăng ký.
4. Kiểm tra giới hạn buffer.
5. So sánh body thực tế trong môi trường test với payload mong đợi.
6. Không log body chứa token, PII hoặc dữ liệu nhạy cảm.

## 6. HTTP status lỗi: WebClientResponseException

Khi dùng `retrieve()`, mặc định Spring biến response 4xx và 5xx thành `WebClientResponseException`. Một số status phổ biến có subclass riêng:

| Status | Subclass thường gặp | Ý nghĩa |
| --- | --- | --- |
| 400 | `WebClientResponseException.BadRequest` | Request không hợp lệ |
| 401 | `WebClientResponseException.Unauthorized` | Thiếu hoặc sai authentication |
| 403 | `WebClientResponseException.Forbidden` | Không đủ quyền |
| 404 | `WebClientResponseException.NotFound` | Không tìm thấy resource |
| 409 | `WebClientResponseException.Conflict` | Xung đột trạng thái |
| 415 | `WebClientResponseException.UnsupportedMediaType` | Server không chấp nhận request media type |
| 429 | `WebClientResponseException.TooManyRequests` | Bị giới hạn tốc độ |
| 502 | `WebClientResponseException.BadGateway` | Gateway nhận phản hồi upstream không hợp lệ |
| 503 | `WebClientResponseException.ServiceUnavailable` | Service tạm thời không sẵn sàng |
| 504 | `WebClientResponseException.GatewayTimeout` | Gateway không nhận được phản hồi upstream kịp thời |

Exception này chứa dữ liệu HTTP response như status, headers và response body. Có thể đọc:

~~~java
catch (WebClientResponseException ex) {
    log.warn("Partner API returned status={}, body={}",
            ex.getStatusCode(),
            redact(ex.getResponseBodyAsString()));
    throw ex;
}
~~~

Trong production, chỉ log error code hoặc các field đã redact. Không ghi nguyên response body nếu nó có thể chứa token, email, địa chỉ, thông tin thanh toán hoặc dữ liệu cá nhân.

### 6.1. Tùy chỉnh lỗi bằng onStatus

`onStatus` cho phép ánh xạ status thành exception domain:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException()
                        .map(ex -> new ProductNotFoundException(id, ex)))
        .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> response.createException())
        .bodyToMono(Product.class);
~~~

Đây là đoạn minh họa, giả định có `ProductNotFoundException` với constructor nhận ID và cause. `response.createException()` tạo exception chứa response status, headers và body.

Nếu handler của `onStatus` trả `Mono.empty()`, response được xem là bình thường và việc đọc body tiếp tục ở downstream. Chỉ làm vậy khi nghiệp vụ thật sự muốn coi status đó là kết quả bình thường.

### 6.2. Đọc error body thành DTO

~~~java
public record ApiError(String code, String message) {
}

.onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError(
                        "UNKNOWN", "No error details"))
                .map(error -> new PartnerApiException(
                        response.statusCode(), error)))
~~~

Đây là một đoạn minh họa cần kiểu `PartnerApiException` do ứng dụng định nghĩa. Cần cân nhắc trường hợp error body không đúng JSON hoặc Content-Type sai: khi đó lỗi decode có thể che mất status ban đầu. Nếu cần bảo toàn status trong mọi tình huống, dùng `response.createException()` rồi đọc body raw một cách an toàn ở tầng xử lý exception.

## 7. retrieve() hay exchangeToMono()?

### 7.1. retrieve(): cách mặc định cho request thông thường

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Dùng khi response 2xx được giải mã theo một kiểu cố định và 4xx/5xx mặc định được xem là lỗi.

### 7.2. exchangeToMono(): khi status quyết định cách đọc body

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }

            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }

            return response.createError();
        });
~~~

Dùng khi status khác nhau cần decode body theo các kiểu khác nhau hoặc khi 404 là kết quả rỗng theo contract.

Sau khi Publisher do callback trả về hoàn tất, Spring kiểm tra response body. Nếu callback chưa consume body, Spring release body để tránh leak bộ nhớ và connection. Vì vậy, không giữ `ClientResponse` rồi định đọc body tiếp ở downstream ngoài callback.

### 7.3. Không đọc response body hai lần

Response body là stream. Nếu đã đọc body thành DTO hoặc String, không thể giả định có thể đọc lại nguyên vẹn. Nếu cần log error body, hãy đọc nó một lần, chuyển thành representation cần thiết rồi xử lý tiếp.

## 8. Xử lý lỗi reactive mà không che mất nguyên nhân

### 8.1. onErrorMap: chuyển exception thành domain exception

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorMap(
                WebClientRequestException.class,
                ex -> new PartnerUnavailableException(
                        "Cannot reach partner API", ex));
~~~

Giữ cause gốc trong exception domain. Không chỉ tạo exception mới từ message vì sẽ mất root cause, stack trace và metadata cần cho điều tra.

Timeout của Reactor Netty có thể nằm bên trong `WebClientRequestException`. Nếu muốn phân loại timeout riêng, hãy kiểm tra cause chain trước khi chuyển mọi request exception thành PartnerUnavailable.

### 8.2. onErrorResume: fallback có điều kiện

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                ex -> Mono.empty());
~~~

Chỉ dùng fallback khi đó là semantics của nghiệp vụ. Không biến mọi lỗi thành `Mono.empty()`:

~~~java
// Anti-pattern: mất thông tin lỗi kết nối, timeout, codec và status.
.onErrorResume(Exception.class, ex -> Mono.empty())
~~~

Đoạn trên khiến caller không phân biệt được resource không tồn tại với service chết, timeout hoặc response hỏng.

### 8.3. Ghi log mà không làm thay đổi kết quả

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .doOnError(error ->
                log.warn("Product request failed: type={}",
                        error.getClass().getSimpleName()));
~~~

`doOnError` chỉ quan sát lỗi và giữ nguyên error signal. Không dùng side effect để subscribe một lần nữa hoặc gọi request lần hai.

## 9. Retry: chỉ retry lỗi có khả năng hồi phục

Không phải lỗi nào cũng nên retry.

| Nhóm lỗi | Có nên retry? | Lý do |
| --- | --- | --- |
| DNS tạm thời, connection reset, một số transport failure | Có thể | Nếu nguyên nhân transient và request có thể lặp an toàn |
| Timeout | Có thể | Nhưng server có thể đã xử lý request trước khi response bị mất |
| HTTP 429 | Có thể | Tuân thủ `Retry-After` hoặc backoff policy của API |
| HTTP 502/503/504 | Có thể | Thường là lỗi tạm thời của gateway/upstream |
| HTTP 400/401/403/404/422 | Thường không | Thường cần sửa input, authentication hoặc quyền |
| Codec/JSON parse error | Không | Retry cùng payload thường cho cùng lỗi |
| DataBufferLimitException | Không | Cần xử lý kích thước/streaming hoặc cấu hình buffer |

Ví dụ retry giới hạn cho status transient:

~~~java
Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
        .filter(error ->
                error instanceof WebClientResponseException response
                && Set.of(502, 503, 504)
                        .contains(response.getStatusCode().value()));

Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(retryPolicy);
~~~

Đây là ví dụ minh họa, cần import `reactor.util.retry.Retry` và `java.util.Set`. Nó chỉ retry một số HTTP status cụ thể; transport timeout cần một policy riêng dựa trên cause chain và loại operation.

Với POST hoặc thao tác tạo/cập nhật, timeout không chứng minh rằng server chưa xử lý request. Nếu retry, có thể tạo dữ liệu trùng. Chỉ retry khi API có idempotency key hoặc contract đảm bảo idempotency.

Không retry vô hạn. Dùng số lần retry nhỏ, exponential backoff, jitter, tổng deadline và giới hạn concurrency. Khi server gửi `Retry-After`, tôn trọng policy đó thay vì retry ngay.

## 10. Cấu hình WebClient cho timeout và codec

Một WebClient có thể cấu hình connector timeout và codec limit:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Cấu hình này giới hạn TCP connect timeout ở 3 giây, đặt Reactor Netty response timeout 5 giây và tăng giới hạn buffer của default codecs lên 2 MiB.

Trong ứng dụng Spring Boot, nên tạo WebClient bean theo từng external API, lấy base URL và timeout từ configuration, không hard-code mỗi endpoint một client mới. Dùng timeout phù hợp với SLA và đặc điểm payload của từng service.

Nếu response lớn hoặc streaming, ưu tiên:

~~~java
Flux<Event> events = client.get()
        .uri("/v1/events")
        .retrieve()
        .bodyToFlux(Event.class);
~~~

thay vì aggregate toàn bộ dữ liệu vào `Mono<List<Event>>` nếu không cần. Điều này giảm memory pressure và cho phép xử lý theo backpressure.

## 11. Observability: log gì để phân loại lỗi?

Một log hữu ích nên có:

- Service đích hoặc client name.
- HTTP method.
- Route template hoặc URI đã redact.
- Correlation/trace ID.
- Thời gian request.
- HTTP status nếu có.
- Exception class và root cause class.
- Timeout phase nếu xác định được.
- Retry count.
- Kích thước response hoặc payload metadata nếu cần.

Ví dụ:

~~~text
partner-api GET /v1/products/{id} status=503 error=WebClientResponseException
partner-api GET /v1/products/{id} status=none error=WebClientRequestException cause=ConnectException
partner-api GET /v1/products/{id} status=200 error=DecodingException
partner-api GET /v1/products/{id} status=none error=ReadTimeoutException
~~~

Không ghi Authorization, Cookie, token, toàn bộ query string nhạy cảm hoặc raw response body. Khi cần điều tra codec, dùng payload mẫu đã redact trong môi trường test.

Metric nên tách HTTP status code, transport failure, timeout theo phase, codec failure, retry count, latency theo service/route và connection pool pending acquire.

## 12. Chương trình Java 17+ chạy được: tái hiện bốn nhóm lỗi

Chương trình dưới đây tạo HTTP server local bằng JDK và gọi nó bằng WebClient. Không cần gọi internet hoặc API bên ngoài.

| Endpoint | Hành vi |
| --- | --- |
| `/ok` | Trả JSON hợp lệ và HTTP 200 |
| `/status` | Trả JSON và HTTP 503 |
| `/bad-json` | Trả HTTP 200 nhưng JSON sai cú pháp |
| `/slow` | Trì hoãn response để tái hiện response timeout |
| Port đã đóng | Không có server lắng nghe, tái hiện connection refused |

Chương trình phân loại exception theo cause chain và assert kết quả mong đợi.

### 12.1. Cấu trúc dự án

~~~text
webclient-error-demo/
  pom.xml
  src/main/java/example/errors/WebClientErrorDemo.java
~~~

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Boot BOM quản lý Spring Framework, Reactor Netty và codec tương thích.

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-error-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. WebClientErrorDemo.java

~~~java
package example.errors;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeoutException;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.core.codec.CodecException;
import org.springframework.core.codec.DecodingException;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.UnsupportedMediaTypeException;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

public final class WebClientErrorDemo {

    public record Product(long id, String name) {
    }

    private static void send(
            HttpExchange exchange,
            int status,
            String contentType,
            String body) throws IOException {

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", contentType);

        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static boolean hasCause(
            Throwable error, Class<?> expectedType) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (expectedType.isInstance(current)) {
                return true;
            }
        }

        return false;
    }

    private static boolean hasCauseNamed(
            Throwable error, String simpleName) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current.getClass().getSimpleName()
                    .equals(simpleName)) {
                return true;
            }
        }

        return false;
    }

    private static String classify(Throwable error) {
        if (hasCause(error, WebClientResponseException.class)) {
            return "HTTP_STATUS";
        }

        if (hasCause(error, TimeoutException.class)
                || hasCauseNamed(error, "ReadTimeoutException")
                || hasCauseNamed(error, "ConnectTimeoutException")
                || hasCauseNamed(error, "PoolAcquireTimeoutException")) {
            return "TIMEOUT";
        }

        if (hasCause(error, DecodingException.class)
                || hasCause(error, CodecException.class)
                || hasCause(error, DataBufferLimitException.class)
                || hasCause(error, UnsupportedMediaTypeException.class)) {
            return "CODEC";
        }

        if (hasCause(error, WebClientRequestException.class)
                || hasCause(error, IOException.class)) {
            return "CONNECTION";
        }

        return "OTHER";
    }

    private static void expectFailure(
            String label,
            Mono<?> publisher,
            String expectedCategory) {

        try {
            publisher.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    label + " should have failed as " + expectedCategory);
        }
        catch (RuntimeException error) {
            String actual = classify(error);

            if (!expectedCategory.equals(actual)) {
                throw new AssertionError(
                        label + ": expected " + expectedCategory
                                + " but got " + actual,
                        error);
            }

            System.out.println(label + "=" + actual);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService serverExecutor =
                Executors.newCachedThreadPool();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.setExecutor(serverExecutor);

        server.createContext("/ok", exchange ->
                send(exchange, 200, "application/json",
                        "{\"id\":7,\"name\":\"demo\"}"));

        server.createContext("/status", exchange ->
                send(exchange, 503, "application/json",
                        "{\"code\":\"TEMP_UNAVAILABLE\"}"));

        server.createContext("/bad-json", exchange ->
                send(exchange, 200, "application/json",
                        "{\"id\":\"not-a-number\",\"name\":"));

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(400);
                send(exchange, 200, "application/json",
                        "{\"id\":8,\"name\":\"slow\"}");
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });

        server.start();

        int closedPort;
        try (ServerSocket socket = new ServerSocket(
                0, 0, InetAddress.getByName("127.0.0.1"))) {
            closedPort = socket.getLocalPort();
        }

        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            HttpClient shortResponseTimeout = HttpClient.create()
                    .responseTimeout(Duration.ofMillis(100));

            WebClient slowClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .clientConnector(
                            new ReactorClientHttpConnector(
                                    shortResponseTimeout))
                    .build();

            Product product = client.get()
                    .uri("/ok")
                    .retrieve()
                    .bodyToMono(Product.class)
                    .block(Duration.ofSeconds(3));

            System.out.println("ok=" + product);

            expectFailure(
                    "status",
                    client.get()
                            .uri("/status")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "HTTP_STATUS");

            expectFailure(
                    "codec",
                    client.get()
                            .uri("/bad-json")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "CODEC");

            expectFailure(
                    "timeout",
                    slowClient.get()
                            .uri("/slow")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "TIMEOUT");

            WebClient unreachable = WebClient.builder()
                    .baseUrl("http://127.0.0.1:" + closedPort)
                    .build();

            expectFailure(
                    "connection",
                    unreachable.get()
                            .uri("/")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "CONNECTION");
        }
        finally {
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
~~~

### 12.4. Chạy chương trình

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.errors.WebClientErrorDemo
~~~

**Stdout dự kiến:**

~~~text
ok=Product[id=7, name=demo]
status=HTTP_STATUS
codec=CODEC
timeout=TIMEOUT
connection=CONNECTION
~~~

Giải thích:

- `/ok` trả JSON hợp lệ nên codec tạo được Product.
- `/status` trả HTTP 503 nên `retrieve()` phát `WebClientResponseException`.
- `/bad-json` trả HTTP 200 nhưng body sai cú pháp nên lỗi nằm ở decoder.
- `/slow` mất 400 ms, vượt response timeout 100 ms của client riêng.
- Port đã đóng khiến TCP connect bị từ chối; Spring bọc lỗi request và giữ cause transport.

Đây là demo local, không gọi internet. Phần phân loại timeout kiểm tra cause chain vì wrapper exception có thể khác nhau theo connector, phiên bản và hệ điều hành.

## 13. Kiểm thử WebClient trong ứng dụng

Ngoài local server, có thể dùng `MockWebServer`, WireMock hoặc mock connector để kiểm tra:

- HTTP 200 với JSON hợp lệ.
- HTTP 400/404/429/503/504.
- Response body lỗi theo error schema.
- Response Content-Type không hỗ trợ.
- JSON malformed hoặc field sai kiểu.
- Body vượt `maxInMemorySize`.
- Connection reset và timeout.
- Redirect và proxy behavior nếu ứng dụng dùng.
- Retry count và idempotency key.
- Cancellation khi caller không còn cần response.

Dùng `StepVerifier` cho Publisher khi muốn kiểm tra error signal mà không gọi block:

~~~java
StepVerifier.create(service.findProduct(id))
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
~~~

Đây là đoạn minh họa, cần dependency Reactor Test và một service được cấu hình để giữ nguyên 404 thành `WebClientResponseException.NotFound`.

Với timeout và transport, integration test qua connector thật có giá trị vì mock response đơn thuần không tái hiện DNS, TCP, TLS, pool và network delay.

## 14. Các lỗi thường gặp khi xử lý WebClient exception

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi mọi lỗi là WebClientResponseException | Bỏ sót connection và codec failure | Phân loại theo exception và cause chain |
| Coi HTTP 504 là timeout do Reactor | Nhầm response gateway với timeout client | Kiểm tra status code trước |
| Coi mọi WebClientRequestException là connection refused | Mất phân biệt DNS, TLS, reset và timeout | Đọc root cause |
| Chỉ catch TimeoutException | Bỏ sót Netty timeout được bọc trong request exception | Kiểm tra cả cause chain và phase |
| Tăng maxInMemorySize để sửa mọi lỗi codec | Có thể che lỗi payload quá lớn và tăng memory pressure | Xác định lỗi decode hay giới hạn buffer |
| Coi HTTP 415 và UnsupportedMediaTypeException là một | Nhầm status server với lỗi chọn decoder client | Kiểm tra class exception và status |
| Dùng onErrorResume(Exception.class, empty) | Mất lỗi gốc và biến outage thành kết quả rỗng | Chỉ fallback cho exception cụ thể |
| Retry tất cả lỗi | Tăng tải, lặp side effect và kéo dài outage | Retry lỗi transient có giới hạn |
| Retry POST khi timeout mà không idempotency key | Có thể tạo dữ liệu trùng | Dùng idempotency contract |
| Đọc error body nhiều lần | Body stream không còn nguyên | Consume một lần và giữ representation cần thiết |
| Log toàn bộ headers/body | Có thể lộ token và PII | Redact và chỉ log field cần thiết |
| Chỉ đặt Reactor timeout | Không biết phase nào bị chậm | Cấu hình timeout riêng cho pool/connect/response |
| Không đặt response timeout | Request có thể chờ response quá lâu | Chọn timeout theo SLA |
| Dùng bodyToMono cho response lớn | Aggregate nhiều bytes vào memory | Dùng bodyToFlux hoặc streaming |
| Chỉ test status 200 | Bỏ sót error handling, timeout và codec | Test đủ bốn nhóm lỗi |

## 15. Checklist trước khi đưa WebClient client vào production

- [ ] Biết connector đang dùng: Reactor Netty, JDK HttpClient, Jetty hay Apache HttpComponents.
- [ ] Phân biệt WebClientRequestException và WebClientResponseException.
- [ ] Ghi nhận root cause thay vì chỉ log message ngoài cùng.
- [ ] Tách timeout theo DNS, pool acquire, connect, TLS, response và Publisher deadline khi cần.
- [ ] Cấu hình response timeout phù hợp với SLA.
- [ ] Có giới hạn connection pool và pending acquire phù hợp với concurrency.
- [ ] Xử lý 4xx/5xx bằng onStatus hoặc exchangeToMono.
- [ ] Xác minh response Content-Type và DTO contract.
- [ ] Xử lý DecodingException và UnsupportedMediaTypeException rõ ràng.
- [ ] Đặt maxInMemorySize phù hợp; ưu tiên streaming cho payload lớn.
- [ ] Không log Authorization, Cookie, token hoặc raw body nhạy cảm.
- [ ] Chỉ retry lỗi transient và có giới hạn/backoff.
- [ ] Tôn trọng Retry-After cho 429 hoặc service có quy định.
- [ ] Không retry non-idempotent operation nếu chưa có idempotency key.
- [ ] Dùng fallback cho lỗi nghiệp vụ cụ thể, không nuốt toàn bộ exception.
- [ ] Test HTTP status, connection failure, timeout, codec và response body lỗi.
- [ ] Theo dõi status, error class, root cause, latency, retry và pool metrics.

## 16. Tự kiểm tra

**Câu 1.** `WebClientResponseException` cho biết điều gì?

Client đã nhận được HTTP response và Spring biểu diễn status lỗi cùng response data trong exception.

**Câu 2.** `WebClientRequestException` khác gì `WebClientResponseException`?

Request exception chứa request metadata và thường đại diện lỗi khi thực hiện request; response exception chứa dữ liệu HTTP response thực tế như status, headers và body.

**Câu 3.** Connection refused có HTTP status không?

Không. TCP connection bị từ chối trước khi client nhận được HTTP response từ service.

**Câu 4.** HTTP 503 có phải connection error không?

Không. Đó là một HTTP response có status 503; server hoặc gateway đã trả lời request.

**Câu 5.** Vì sao HTTP 200 vẫn có thể làm WebClient phát lỗi?

Body có thể không đúng JSON, Content-Type không có decoder phù hợp, dữ liệu không tương thích DTO hoặc vượt giới hạn buffer.

**Câu 6.** `DecodingException` thường chỉ ra điều gì?

Lỗi nội dung khi decoder đọc stream, ví dụ JSON parse failure hoặc dữ liệu không phù hợp kiểu đích.

**Câu 7.** `DataBufferLimitException` có phải lỗi kết nối không?

Không. Nó chỉ ra dữ liệu cần buffer vượt giới hạn cấu hình của codec/reader.

**Câu 8.** `responseTimeout` và `Mono.timeout` khác nhau thế nào?

responseTimeout thuộc Reactor Netty response/read phase; Mono.timeout đặt deadline cho Publisher từ khi subscribe đến khi có signal.

**Câu 9.** HTTP 504 khác `TimeoutException` ra sao?

504 là response từ gateway; TimeoutException là signal timeout do client/reactive pipeline phát ra.

**Câu 10.** Khi nào dùng `exchangeToMono`?

Khi cần tự quyết định cách decode response theo status, hoặc xử lý các status như 404 thành kết quả rỗng theo contract.

**Câu 11.** Có nên retry mọi WebClient exception không?

Không. Chỉ retry lỗi transient, giới hạn số lần, dùng backoff và bảo đảm operation có thể lặp an toàn.

**Câu 12.** Vì sao cần kiểm tra cause chain?

Timeout và transport exception có thể được bọc trong exception của Spring hoặc connector. Root cause giúp xác định chính xác giai đoạn thất bại.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): tổng quan WebClient, request/response và các API chính.
- [Spring Framework — retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): mặc định 4xx/5xx tạo WebClientResponseException và tùy chỉnh onStatus.
- [Spring Framework — Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): exchangeToMono, exchangeToFlux và cleanup response body.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): codec limits, connector và timeout configuration.
- [WebClientRequestException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientRequestException.html): request method, URI, headers và request failure metadata.
- [WebClientResponseException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html): status, response headers, body và các subclass theo status.
- [DecodingException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/codec/DecodingException.html): lỗi decode nội dung.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer, codec và buffer lifecycle.
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pool acquire, connect, response, TLS và DNS timeout.
- [Reactor Core — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): xử lý lỗi reactive, retry và fallback.

**Ghi nhớ:** HTTP status lỗi nghĩa là đã nhận response; connection error nghĩa là trao đổi HTTP không hoàn tất; timeout cần xác định phase; codec error xảy ra khi chuyển response bytes thành kiểu Java. Kiểm tra status trước, rồi exception và cause chain; cấu hình timeout theo từng giai đoạn, giữ nguyên nguyên nhân, retry có điều kiện và không biến mọi lỗi thành kết quả rỗng.