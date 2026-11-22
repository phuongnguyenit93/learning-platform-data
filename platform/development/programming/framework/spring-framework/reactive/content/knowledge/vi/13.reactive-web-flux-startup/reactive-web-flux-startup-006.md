# Quan sát yêu cầu, phản hồi và tín hiệu đầu tiên trong Spring WebFlux

## 1. Mục tiêu: quan sát đúng vòng đời HTTP và Reactor

Một request trong Spring WebFlux đi qua nhiều lớp: HTTP server nhận request, WebFilter và handler xử lý, controller tạo `Mono`/`Flux`, service có thể gọi `WebClient`, rồi response được ghi về client. Trong lúc đó, Reactor phát các tín hiệu `onSubscribe`, `onNext`, `onComplete`, `onError`; subscriber cũng có thể gửi `request(n)` và `cancel()`.

Để chẩn đoán đúng, cần phân biệt ba góc nhìn:

1. **HTTP lifecycle**: request đến, route được chọn, response status/header được tạo, body được ghi và kết nối kết thúc hoặc bị ngắt.
2. **Reactor lifecycle**: publisher được subscribe, demand được yêu cầu, phần tử được phát, sequence complete/error hoặc bị cancel.
3. **Cuộc đua giữa nhiều nguồn**: nếu có nhiều publisher cùng cung cấp một kết quả, `firstWithSignal` chọn nguồn phát tín hiệu đầu tiên; `firstWithValue` chọn nguồn phát giá trị đầu tiên.

Một dòng log “request bắt đầu” không chứng minh response đã hoàn tất. Một `Mono<ClientResponse>` phát response headers cũng không có nghĩa body đã được đọc hết. Một publisher bị cancel cũng không phải là publisher complete thành công.

Bài học này tập trung vào cách quan sát request/response ở server và client, cách đọc tín hiệu Reactor, ý nghĩa của “tín hiệu đầu tiên”, và cách viết kiểm thử để xác nhận đúng hành vi.

## 2. Đường đi request và response ở WebFlux

Đường đi server thường có dạng:

```text
HTTP client
    |
    v
Reactor Netty / HTTP server adapter
    |
    v
WebFilter chain
    |
    v
DispatcherHandler -> HandlerMapping -> HandlerAdapter
    |
    v
Controller -> Service -> WebClient / repository
    |
    v
Mono<T> / Flux<T>
    |
    v
HttpMessageWriter / codecs
    |
    v
HTTP response status + headers + body
    |
    v
HTTP client
```

Các điểm quan sát có ý nghĩa khác nhau:

| Điểm quan sát | Điều có thể biết | Điều chưa thể kết luận |
|---|---|---|
| Đầu `WebFilter` | Request đã đi vào filter chain | Handler nào sẽ xử lý, response status cuối |
| Sau `chain.filter(exchange)` complete | Pipeline filter/handler đã hoàn tất | Không phải mọi client đều chắc chắn đã nhận đủ bytes nếu kết nối bị ngắt ở tầng vận chuyển |
| `doOnError` trên chain | Lỗi đã truyền qua vị trí operator đó | Lỗi có thể đã được `@ExceptionHandler` xử lý trước khi thoát ra ngoài |
| `doFinally` | Sequence kết thúc bằng complete, error hay cancel | Cancel không cho biết upstream bên ngoài đã dừng công việc vật lý tức thì |
| `ExchangeFilterFunction` nhận `ClientResponse` | Client đã nhận response metadata/status | Body có thể chưa được đọc hoặc decode |
| `doFinally` sau `bodyToMono` / `bodyToFlux` | Pipeline tiêu thụ body đã kết thúc hoặc bị hủy | Không tự chứng minh nghiệp vụ downstream đã commit thành công |

Một request WebFlux có thể chuyển qua nhiều thread. Thread ID không phải correlation ID đáng tin cậy. Hãy dùng request log ID, trace/span ID hoặc correlation ID được truyền theo context thay vì ghép log chỉ bằng tên thread.

## 3. Tín hiệu Reactive Streams và các operator quan sát

Vòng đời một subscription:

```text
Publisher.subscribe(subscriber)
       |
       v
onSubscribe(subscription)
       |
       +---- request(n) --------------------+
       |                                    |
       v                                    |
onNext(value) <-----------------------------+
       |
       +---- onNext(value) ... (Flux)
       |
       +---- onComplete()   terminal thành công
       |
       +---- onError(error) terminal lỗi

Subscriber có thể cancel() trước terminal.
```

Các operator quan sát quan trọng:

| Operator | Quan sát | Lưu ý |
|---|---|---|
| `doFirst` | Hành động trước khi upstream được subscribe | Không đồng nghĩa với request HTTP đã được gửi |
| `doOnSubscribe` | Subscriber nhận `Subscription` | Có thể ghi nhận bắt đầu subscription |
| `doOnRequest` | Demand đi qua vị trí operator | `request(n)` không phải request HTTP hay request/giây |
| `doOnNext` | Mỗi phần tử được phát | Với Flux có thể chạy nhiều lần |
| `doOnSuccess` | Mono hoàn tất thành công | Giá trị callback là `null` nếu Mono rỗng |
| `doOnComplete` | Flux complete thành công | Mono thường dùng `doOnSuccess` hoặc `doOnEach` |
| `doOnError` | Lỗi đi qua pipeline | Không chạy khi chỉ cancel |
| `doOnCancel` | Nhận yêu cầu cancel | Không phải terminal signal từ publisher |
| `doOnEach` | Nhận `Signal` cho onNext/onError/onComplete | Hữu ích khi muốn một callback quan sát nhiều loại tín hiệu |
| `doFinally` | Complete, error hoặc cancel | Callback chạy sau khi terminal/cancel được truyền downstream |

### `doOnSuccess` khác `doOnNext`

```java
Mono<String> value = Mono.just("OK")
        .doOnNext(v -> log.info("onNext={}", v))
        .doOnSuccess(v -> log.info("mono success={}", v));

Mono<String> empty = Mono.<String>empty()
        .doOnNext(v -> log.info("empty next={}", v))
        .doOnSuccess(v -> log.info("empty success={}", v));
```

- Với `Mono.just("OK")`, cả `doOnNext` và `doOnSuccess` được gọi với `"OK"`.
- Với `Mono.empty()`, `doOnNext` không chạy; `doOnSuccess` chạy với `null`.
- `null` ở callback `doOnSuccess` không có nghĩa Reactor phát `onNext(null)`. Reactive Streams không cho phép `null` làm phần tử.

Đây là snippet minh họa; `log` phải là logger đã khai báo.

### `doOnEach` để quan sát cả value và terminal signal

```java
Mono<String> observed = remoteCall
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                log.debug("value received");
            } else if (signal.isOnComplete()) {
                log.debug("publisher completed");
            } else if (signal.isOnError()) {
                log.warn("publisher failed", signal.getThrowable());
            }
        });
```

`remoteCall` là `Mono<String>` đã có sẵn. Không log toàn bộ giá trị nếu nó có thể chứa token, dữ liệu cá nhân hoặc nội dung nghiệp vụ nhạy cảm. `doOnEach` nhận cả `Signal` mang context của Reactor, hữu ích cho instrumentation; nếu chỉ cần một sự kiện đơn giản, dùng operator chuyên biệt sẽ dễ đọc hơn.

### `doFinally` để phân biệt complete, error và cancel

```java
Mono<String> observed = remoteCall
        .doFinally(signal -> log.info("exchange finished: {}", signal));
```

Các giá trị thường gặp:

- `ON_COMPLETE`: publisher hoàn tất thành công.
- `ON_ERROR`: publisher kết thúc bằng lỗi.
- `CANCEL`: subscriber yêu cầu hủy.

`doFinally` chạy sau khi tín hiệu kết thúc đã được truyền downstream. Vì vậy khi kiểm thử callback, cần đợi cancellation/terminal hoàn tất; không nên giả định side effect của `doFinally` đã chạy trước khi downstream nhìn thấy terminal.

## 4. Quan sát HTTP request ở server bằng `WebFilter`

`WebFilter` là điểm thích hợp để ghi nhận metadata của request ở tầng WebFlux: method, route/path, request ID, status cuối cùng, signal kết thúc và thời gian xử lý.

Ví dụ sau là **snippet trong ứng dụng Spring Boot WebFlux**, cần import `Mono`, `WebFilter`, `WebFilterChain`, `ServerWebExchange`, `HandlerMapping`, `HttpStatusCode`, `Logger` và `LoggerFactory`:

```java
@Component
public class HttpLifecycleFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(HttpLifecycleFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();

        String method = exchange.getRequest()
                .getMethod()
                .name();

        String requestId = exchange.getLogPrefix();

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn("{} request failed: {}",
                                requestId, error.toString()))
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);

                    HttpStatusCode status =
                            exchange.getResponse().getStatusCode();

                    Object pattern = exchange.getAttribute(
                            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                    String route = pattern != null
                            ? pattern.toString()
                            : exchange.getRequest().getPath()
                                    .pathWithinApplication().value();

                    String statusText = status == null
                            ? "not-set"
                            : Integer.toString(status.value());

                    log.info(
                            "{} method={} route={} status={} signal={} durationMs={}",
                            requestId, method, route,
                            statusText, signal, elapsedMs);
                });
    }
}
```

Để snippet biên dịch, thêm các import:

```java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.reactive.HandlerMapping;
import reactor.core.publisher.Mono;
```

Cách đọc:

- `exchange.getLogPrefix()` cung cấp log prefix gắn với request WebFlux; dùng nó để liên kết các dòng log của cùng request.
- `BEST_MATCHING_PATTERN_ATTRIBUTE` có thể chứa route template như `/orders/{id}` sau khi handler mapping chạy. Nếu không có, ví dụ dùng path thực tế; trong hệ thống thật hãy cân nhắc che/mask ID trên path.
- `getStatusCode()` có thể trả `null` nếu response chưa được đặt status tường minh. Đừng tự kết luận `null` chắc chắn là HTTP 200.
- `doOnError` ghi nhận lỗi thoát khỏi filter chain. Nếu exception đã được WebFlux xử lý bằng `@ExceptionHandler`, lỗi có thể không thoát ra đây; response vẫn có thể là 4xx/5xx.
- `doFinally` ghi cả `ON_COMPLETE`, `ON_ERROR` và `CANCEL`, nên phân biệt request kết thúc bình thường với client ngắt kết nối/hủy pipeline.
- `System.nanoTime()` phù hợp đo khoảng thời gian; không dùng `currentTimeMillis()` để tính elapsed time.

`doFinally` của chain là thời điểm kết thúc xử lý reactive ở vị trí filter. Với streaming response, hãy kiểm thử trên server/transport thực tế để xác nhận thời điểm pipeline kết thúc tương ứng với việc ghi body và disconnect theo adapter đang dùng.

## 5. Quan sát outbound request/response bằng `WebClient` filter

`ExchangeFilterFunction` cho phép chặn request và response metadata ở client. Đây là điểm tốt để log method, host, status và thời gian nhận response headers mà không cần đọc body.

```java
ExchangeFilterFunction exchangeLogger =
        (request, next) -> {
            long startedAt = System.nanoTime();

            log.info("outbound start method={} host={}",
                    request.method(),
                    request.url().getHost());

            return next.exchange(request)
                    .doOnNext(response ->
                            log.info("outbound response status={}",
                                    response.statusCode().value()))
                    .doOnError(error ->
                            log.warn("outbound exchange failed",
                                    error))
                    .doFinally(signal -> {
                        long elapsedMs =
                                TimeUnit.NANOSECONDS.toMillis(
                                        System.nanoTime() - startedAt);

                        log.info(
                                "outbound exchange signal={} headerLatencyMs={}",
                                signal, elapsedMs);
                    });
        };

WebClient client = WebClient.builder()
        .filter(exchangeLogger)
        .build();
```

Đây là snippet cần các import `ExchangeFilterFunction`, `WebClient`, `ClientResponse`, `ClientRequest`, `Mono`, `TimeUnit` và logger thích hợp; `ClientResponse`/`ClientRequest` không cần import nếu không khai báo trực tiếp kiểu.

**Quan trọng về thời gian đo:** `next.exchange(request)` trả `Mono<ClientResponse>`. Filter nhận response khi status/header sẵn sàng; `doFinally` trong filter này thường kết thúc sau khi `ClientResponse` được chuyển xuống caller, **trước khi caller tiêu thụ hết response body**. Vì vậy hãy đặt tên metric rõ ràng như `headerLatency`, không gắn nhãn là full body latency.

Nếu muốn đo thời gian đọc và decode body, instrument publisher sau `bodyToMono`, `bodyToFlux` hoặc `toEntity`:

```java
Mono<ResponseEntity<String>> result = client.get()
        .uri("/status")
        .retrieve()
        .toEntity(String.class)
        .doOnNext(entity ->
                log.info("body received status={}",
                        entity.getStatusCode().value()))
        .doOnError(error ->
                log.warn("body processing failed", error))
        .doFinally(signal ->
                log.info("body pipeline ended: {}", signal));
```

Snippet này tiêu thụ toàn bộ body thành `String`; không dùng cách đó cho response stream lớn hoặc SSE nếu không có chủ đích buffer toàn bộ.

### Không đọc body tùy tiện trong filter

`ClientResponse` body là stream có thể tiêu thụ một lần. Nếu filter tự gọi `bodyToMono(String.class)` chỉ để log rồi trả nguyên response cho downstream, downstream có thể không còn body để đọc. Nếu filter xử lý response body, nó phải tiêu thụ, giải phóng hoặc tái tạo body đúng cách. Buffer toàn bộ body còn làm tăng heap và có thể gây lỗi với payload lớn.

Ưu tiên log status, method, host, route template, request ID, elapsed time và kích thước body nếu có metric an toàn. Chỉ triển khai body logging bằng decorator/buffering có giới hạn, kiểm tra release `DataBuffer`, mask bí mật và có chính sách riêng cho streaming.

## 6. Quan sát response status và lỗi HTTP

`WebClient.retrieve()` mặc định chuyển status 4xx/5xx thành lỗi `WebClientResponseException` nếu không được xử lý bằng `onStatus`. Vì vậy có hai loại tình huống:

1. **HTTP response đã đến** với status 4xx/5xx: filter có thể thấy status response; sau đó `retrieve()` có thể biến nó thành error trong pipeline body.
2. **Không có HTTP response**: DNS/connect/timeout/TLS/network failure; filter có thể nhận `onError` trước khi có `ClientResponse`, nên không có status HTTP để log.

Ví dụ xử lý status rõ ràng:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException())
        .bodyToMono(Order.class)
        .doOnError(WebClientResponseException.class,
                error -> log.warn("HTTP status={} request failed",
                        error.getStatusCode().value()));
```

Đây là snippet cần `id`, `Order`, `client` và logger. `createException()` tạo exception chứa thông tin response; tránh ghi toàn bộ response body vào log nếu nó chứa dữ liệu nhạy cảm.

Nếu cần quyết định decode khác nhau theo status, dùng `exchangeToMono`/`exchangeToFlux`:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Order.class);
            }
            return response.createError();
        });
```

Khi dùng `exchangeToMono`, callback phải quyết định cách tiêu thụ body. Spring kiểm tra và release body nếu nó không được tiêu thụ; không thể decode lại body sau khi đã kết thúc callback. Đây là lý do không nên viết filter quan sát status rồi bỏ qua quản lý body.

## 7. “Tín hiệu đầu tiên”: `firstWithSignal` và `firstWithValue`

Khi có hai hoặc nhiều publisher cạnh tranh để cung cấp kết quả, Reactor có hai operator dễ nhầm:

- **`Mono.firstWithSignal(a, b)`**: chọn nguồn phát **bất kỳ tín hiệu đầu tiên**: `onNext`, `onComplete` rỗng hoặc `onError`.
- **`Mono.firstWithValue(a, b)`**: chọn nguồn phát **giá trị `onNext` đầu tiên**. Nguồn hoàn tất rỗng hoặc lỗi không thắng nếu một nguồn khác vẫn có thể phát giá trị.

Cả hai operator subscribe các nguồn cạnh tranh và hủy các nguồn còn lại khi đã chọn được nguồn thắng. Việc hủy là cancellation ở tầng Reactor; HTTP client/driver có thể cố hủy I/O, nhưng server từ xa có thể đã nhận và tiếp tục xử lý request.

### Timeline ví dụ

```text
Thời gian:       0 ms       10 ms          20 ms           80 ms
Primary:         subscribe  empty/error ------------------->
Backup:          subscribe  ---------------- value -------->
firstWithSignal:             empty/error thắng ngay
firstWithValue:                           backup value thắng
```

Ví dụ: primary trả `Mono.empty()` sau 10 ms, backup trả `"backup"` sau 20 ms:

- `firstWithSignal` kết thúc rỗng ở 10 ms; backup bị cancel.
- `firstWithValue` tiếp tục chờ vì primary không có giá trị; backup phát `"backup"` ở 20 ms và thắng.

Đây là khác biệt quan trọng khi fallback API: **empty/error nhanh không nhất thiết là kết quả hữu ích**.

### Ví dụ chọn phản hồi đầu tiên

```java
Mono<Quote> fastestSignal = Mono.firstWithSignal(
        primaryClient.getQuote(symbol),
        backupClient.getQuote(symbol)
);

Mono<Quote> fastestValue = Mono.firstWithValue(
        primaryClient.getQuote(symbol),
        backupClient.getQuote(symbol)
);
```

`primaryClient` và `backupClient` là các client/service đã được cấu hình. Chỉ dùng race này khi hai nguồn có thể chạy đồng thời và thao tác an toàn khi một nhánh bị cancel. Không race các lệnh POST tạo thanh toán/đơn hàng nếu không có idempotency key và cơ chế chống tạo side effect trùng lặp.

### Xử lý lỗi khi không nguồn nào có giá trị

Với `firstWithValue`, nếu không publisher nào phát `onNext` (tất cả đều empty/error), operator phát `NoSuchElementException` với thông tin lỗi tổng hợp trong cause. Nếu cần phân loại lỗi chi tiết, xem `Exceptions.unwrapMultiple(...)` theo API Reactor của phiên bản đang dùng.

Một chính sách khác là chuẩn hóa từng nguồn trước khi race:

```java
Mono<Quote> primaryValue = primaryClient.getQuote(symbol)
        .onErrorResume(error -> Mono.empty());

Mono<Quote> backupValue = backupClient.getQuote(symbol)
        .onErrorResume(error -> Mono.empty());

Mono<Quote> quote = Mono.firstWithValue(
        primaryValue,
        backupValue);
```

Đây chỉ là ví dụ khi nghiệp vụ cho phép coi lỗi của từng nguồn như “không có giá trị” để thử nguồn khác. Không biến mọi lỗi thành empty nếu cần phân biệt lỗi xác thực, lỗi dữ liệu, quota hoặc sự cố hệ thống.

### `Flux.firstWithSignal`

Với `Flux`, `Flux.firstWithSignal(...)` chọn publisher phát bất kỳ tín hiệu đầu tiên và sau đó chuyển tiếp sequence từ publisher thắng. Nó **không merge** phần tử từ các nguồn và không sắp xếp theo thời gian toàn cục. Nếu mục tiêu là hợp nhất tất cả event, dùng `merge`; nếu chỉ chọn một nguồn thắng, dùng `firstWithSignal`.

## 8. Quan sát tín hiệu trong một cuộc đua

Có thể gắn `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnCancel` và `doFinally` cho từng nhánh để biết nhánh nào thắng và nhánh nào bị hủy:

```java
Mono<String> primary = primaryCall()
        .doOnSubscribe(s -> log.debug("primary subscribed"))
        .doOnNext(v -> log.debug("primary produced value"))
        .doOnError(e -> log.warn("primary failed", e))
        .doOnCancel(() -> log.debug("primary cancelled"))
        .doFinally(s -> log.debug("primary final={}", s));

Mono<String> backup = backupCall()
        .doOnSubscribe(s -> log.debug("backup subscribed"))
        .doOnNext(v -> log.debug("backup produced value"))
        .doOnError(e -> log.warn("backup failed", e))
        .doOnCancel(() -> log.debug("backup cancelled"))
        .doFinally(s -> log.debug("backup final={}", s));

Mono<String> winner = Mono.firstWithValue(primary, backup);
```

Đây là snippet cần `primaryCall()`/`backupCall()` trả `Mono<String>`. Khi một nhánh thắng, nhánh còn lại thường quan sát `CANCEL`; nếu nhánh kia đã terminal trước đó thì nó không thể bị cancel thêm. Đừng ghi log nội dung dữ liệu nếu không cần.

Dùng log cấp nhánh cùng correlation ID để trả lời:

- Hai request đã thực sự được subscribe chưa?
- Nhánh nào phát giá trị đầu tiên?
- Nhánh nào trả empty/error trước?
- Nhánh thua có nhận cancellation không?
- Thời gian từ subscribe đến response header khác thời gian đọc body bao nhiêu?

## 9. Observation, metrics và tracing

Log thủ công giúp điều tra từng request nhưng không thay thế metrics/tracing. Trong ứng dụng Spring, nên ưu tiên **Micrometer Observation** và tracing để có số liệu thống nhất giữa HTTP server, WebClient và các service.

### Bật Observation cho WebClient

`WebClient.Builder` hỗ trợ `observationRegistry(...)`:

```java
@Bean
WebClient webClient(
        WebClient.Builder builder,
        ObservationRegistry observationRegistry) {

    return builder
            .observationRegistry(observationRegistry)
            .build();
}
```

Đây là snippet cấu hình Spring, cần import `ObservationRegistry` từ Micrometer. Trong Spring Boot, builder được auto-configure có thể đã gắn registry khi dependency Actuator/observability thích hợp có mặt; kiểm tra cấu hình thực tế trước khi gắn thêm lần nữa.

Observation của client có thể đo toàn bộ HTTP exchange từ thiết lập kết nối đến đọc/deserialization body, khác với `ExchangeFilterFunction` đơn giản chỉ đo tới lúc response metadata được phát xuống. Tên observation/metric cụ thể và tag có thể khác theo phiên bản Spring/Micrometer convention.

### Server-side metrics

Spring Boot Actuator có thể auto-configure HTTP server observations/metrics cho ứng dụng WebFlux khi có dependency và registry phù hợp. Dùng metrics để xem phân phối latency, số request, status/outcome và lỗi; dùng tracing để nối một request qua nhiều outbound calls.

Không hard-code metric name hoặc tag chưa kiểm tra. Phiên bản Spring Boot, Micrometer convention, OpenTelemetry bridge và exporter có thể ảnh hưởng tên và tập tag. Tránh tag có cardinality cao như user ID, email, full URL có query string, order ID hoặc correlation ID; các giá trị đó phù hợp log/trace hơn metric label.

### Correlation ID và Reactor Context

Một request có thể chuyển thread; `ThreadLocal` không phải cách an toàn để tự truyền context xuyên toàn pipeline reactive. Dùng cơ chế Observation/Tracing propagation hoặc Reactor Context phù hợp với phiên bản Spring/Micrometer.

Không đưa token, session ID bí mật hoặc PII vào baggage/tag/log. Nếu chấp nhận correlation ID từ client, xác thực độ dài/ký tự và tránh để client tự tạo giá trị có thể gây log injection.

## 10. Bảo mật và độ tin cậy khi quan sát HTTP

Quan sát request/response có thể vô tình trở thành một đường rò dữ liệu. Áp dụng nguyên tắc tối thiểu:

- Ghi method, route template, status, elapsed time, request ID và loại lỗi trước khi cân nhắc body.
- Không log `Authorization`, `Cookie`, access token, API key, password hoặc toàn bộ header.
- Tránh log query string chứa email, phone, search text hoặc thông tin định danh.
- Không log request/response body mặc định. Nếu bắt buộc debug, chỉ bật có thời hạn, giới hạn kích thước, mask field nhạy cảm và kiểm soát quyền truy cập log.
- Không buffer vô hạn body streaming để phục vụ logging.
- Khi wrap `DataBuffer`, phải quản lý retain/release đúng cách; nếu đọc body trong filter mà không tái phát lại, downstream có thể nhận body rỗng hoặc connection leak.
- Tránh log một stack trace ở nhiều lớp cho cùng một lỗi; chọn một nơi log đầy đủ, các lớp khác gắn correlation ID và error category.
- Phân biệt lỗi đã được xử lý thành response 4xx/5xx với lỗi thoát khỏi pipeline. Đừng chỉ dựa vào `doOnError` để đếm mọi HTTP error status.

### Phân biệt HTTP status và Reactor terminal signal

| HTTP response | Reactor signal có thể quan sát | Ý nghĩa |
|---|---|---|
| 200 với body | `onNext`, sau đó `onComplete` | Body được phát rồi sequence hoàn tất |
| 204/no content | `onComplete` không có value ở body publisher | Thành công nhưng không có body |
| 404 từ `retrieve()` | `onError(WebClientResponseException)` | HTTP response có status 404 nhưng WebClient chuyển thành error |
| 500 được xử lý bằng `onStatus`/`onErrorResume` | Có thể `onError`, rồi được chuyển thành fallback `onNext`/complete | Lỗi gốc đã được chuyển đổi |
| Client disconnect | `cancel` ở một số publisher/response pipeline | Subscriber không còn nhận; server/remote cancellation phụ thuộc transport |
| DNS/connect timeout | `onError` mà không có HTTP status | Không có response HTTP từ upstream |

Một HTTP 404 không phải `SignalType.ON_ERROR` ở mọi tầng. Nếu dùng `exchangeToMono` và tự xử lý status thành giá trị, pipeline có thể complete thành công. Ngược lại, `retrieve()` mặc định chuyển status lỗi thành exception. Phải quan sát đúng tầng đang instrument.

## 11. Chương trình Java 17+ chạy được: kiểm thử `firstWithSignal` và `firstWithValue`

Ví dụ dưới đây dùng Reactor Core 3.6.6, JUnit Jupiter và `reactor-test`. Đây là dự án Java độc lập để kiểm thử tín hiệu; không cần khởi động Spring Boot hoặc gọi mạng thật.

Cấu trúc:

```text
reactor-first-signal-demo/
├── pom.xml
└── src/test/java/edu/demo/FirstSignalTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-first-signal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/test/java/edu/demo/FirstSignalTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FirstSignalTest {

    @Test
    void firstWithSignalAllowsEmptyToWin() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithSignal(
                        Mono.<String>empty()
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(50))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(60))
                .verifyComplete();
    }

    @Test
    void firstWithValueWaitsForAnActualValue() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithValue(
                        Mono.<String>empty()
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(20))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(30))
                .expectNext("backup")
                .verifyComplete();
    }

    @Test
    void firstWithValueCanIgnoreAnEarlyErrorIfAnotherSourceProducesValue() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithValue(
                        Mono.<String>error(
                                new IllegalStateException("primary failed"))
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(20))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(30))
                .expectNext("backup")
                .verifyComplete();
    }

    @Test
    void firstWithSignalPropagatesTheFirstError() {
        StepVerifier.withVirtualTime(() ->
                Mono.firstWithSignal(
                        Mono.<String>error(
                                new IllegalArgumentException("bad primary"))
                                .delaySubscription(Duration.ofMillis(10)),
                        Mono.delay(Duration.ofMillis(50))
                                .thenReturn("backup")
                ))
                .expectSubscription()
                .thenAwait(Duration.ofMillis(20))
                .expectErrorMessage("bad primary")
                .verify();
    }

    @Test
    void doFinallyDistinguishesCancellation() {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        StepVerifier.create(
                        Mono.<String>never()
                                .doFinally(finalSignal::set))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi khi dependency tải thành công và assertion đúng: **5 test PASS** (`Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`). Các test không cần chờ đồng hồ thực; `withVirtualTime` tạo scheduler ảo trước khi supplier dựng pipeline thời gian.

Ý nghĩa từng test:

1. `firstWithSignalAllowsEmptyToWin`: `onComplete` rỗng ở 10 ms là tín hiệu đầu tiên; backup bị hủy và kết quả complete không có value.
2. `firstWithValueWaitsForAnActualValue`: empty không thắng; backup phát value ở 20 ms.
3. `firstWithValueCanIgnoreAnEarlyErrorIfAnotherSourceProducesValue`: lỗi primary không thắng nếu backup sau đó có value.
4. `firstWithSignalPropagatesTheFirstError`: `onError` đầu tiên thắng và được truyền xuống.
5. `doFinallyDistinguishesCancellation`: subscriber hủy `Mono.never()`, callback thấy `SignalType.CANCEL`.

Đây là kiểm thử ngữ nghĩa operator bằng Reactor Core; chưa phải integration test đo thời gian HTTP thật, TLS, connection pool, body decoding hay hành vi server khi request bị cancel.

## 12. Checklist đưa quan sát vào ứng dụng

Trước khi bật instrumentation ở production, hãy kiểm tra:

1. Có request ID/trace ID nhất quán xuyên server và outbound client không?
2. Log server có method, route template, status, signal và latency không?
3. Log client phân biệt thời gian tới response headers với thời gian đọc/decode body không?
4. `doFinally` có phân biệt `ON_COMPLETE`, `ON_ERROR`, `CANCEL` không?
5. HTTP 4xx/5xx có được ghi nhận ngay cả khi WebClient chuyển chúng thành error/fallback không?
6. Lỗi connect/DNS/timeout có được phân biệt với HTTP response status không?
7. Body và header nhạy cảm đã được mask chưa?
8. Filter có vô tình consume body, buffer không giới hạn hoặc làm mất `DataBuffer` không?
9. Publisher race có hủy nhánh thua không? Tác vụ upstream có hỗ trợ cancellation không?
10. `firstWithSignal` có thể để empty/error nhanh thắng ngoài ý muốn không? Có cần `firstWithValue` không?
11. Metrics tag có cardinality thấp không? Có tránh user ID, request ID, full URL và query string làm label không?
12. Có test cho complete, error, cancel, empty, response status và body consumption không?
13. Có phân biệt lỗi đã được handler xử lý với exception thực sự thoát khỏi WebFilter không?
14. Có giới hạn sampling/volume log để tránh log firehose khi stream phát nhiều phần tử không?

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Coi `doFinally(ON_COMPLETE)` là bằng chứng client đã nhận đủ response | Đánh giá quá mức trạng thái giao nhận | Phân biệt terminal pipeline với xác nhận ở tầng client/transport |
| Chỉ dùng `doOnError` để đếm HTTP 500 | Bỏ sót response status đã được xử lý thành fallback | Ghi status ở response filter/Observation và ghi error signal riêng |
| Đo latency trong `ExchangeFilterFunction` rồi gọi đó là body latency | Số liệu thấp hơn thời gian tiêu thụ body | Instrument publisher sau `bodyToMono`/`bodyToFlux` hoặc Observation |
| Gọi `bodyToMono` trong filter để log rồi trả response cũ | Downstream mất body hoặc buffer không được giải phóng | Không đọc body trong filter nếu không có cơ chế consume/rebuild đúng |
| Log full URL/query/header/body | Rò token, PII và dữ liệu nghiệp vụ | Mask, dùng route template, log metadata tối thiểu |
| Dùng thread ID làm correlation ID | Log mất liên kết khi pipeline đổi thread | Dùng request ID, trace/span và Reactor Context |
| Nhầm `doOnSuccess(null)` là `onNext(null)` | Sai cách hiểu Mono empty | Nhớ Mono empty gọi success callback với null nhưng không phát phần tử |
| Dùng `firstWithSignal` cho fallback cần giá trị | Empty/error nhanh có thể thắng | Dùng `firstWithValue` hoặc chuẩn hóa lỗi/empty theo nghiệp vụ |
| Dùng `firstWithValue` rồi không xử lý trường hợp mọi nguồn đều lỗi/empty | Nhận `NoSuchElementException` tổng hợp | Xác định chính sách lỗi khi không có nguồn nào phát value |
| Race các POST không idempotent | Nhiều request cùng tạo side effect | Không race hoặc dùng idempotency/deduplication thực sự |
| Cho rằng cancel đảm bảo remote server dừng xử lý | Công việc phía remote có thể tiếp tục | Thiết kế timeout/idempotency và kiểm tra driver/server cancellation |
| Đặt metric label là request ID hoặc user ID | Cardinality bùng nổ | Để ID trong log/trace; metrics dùng tag giới hạn |

## 14. Bài tập tự kiểm tra

**Bài 1.** Một WebFilter thấy `chain.filter(exchange)` phát `onError`. Có thể khẳng định response HTTP không tồn tại không?

**Đáp án:** Không. Tùy vị trí xử lý lỗi, exception có thể đã được chuyển thành response ở tầng khác; cần quan sát status và error propagation đúng lớp.

**Bài 2.** `ExchangeFilterFunction` đã log status 200. Có thể khẳng định body đã decode thành công không?

**Đáp án:** Không. Filter nhận `ClientResponse` khi response metadata sẵn sàng; decode/body consumption có thể lỗi sau đó.

**Bài 3.** `Mono.firstWithSignal(Mono.empty(), slowValue)` trả gì nếu empty phát trước?

**Đáp án:** Complete rỗng. `firstWithSignal` chọn bất kỳ tín hiệu đầu tiên, bao gồm `onComplete` không có value.

**Bài 4.** `Mono.firstWithValue(Mono.error(e), slowValue)` trả gì nếu slowValue sau đó phát giá trị?

**Đáp án:** Giá trị từ slowValue. Lỗi sớm không thắng nếu còn nguồn có thể phát value; nếu không nguồn nào phát value thì operator kết thúc lỗi tổng hợp.

**Bài 5.** Vì sao không log body bằng cách gọi `response.bodyToMono(String.class)` trong filter rồi vẫn trả response cho controller?

**Đáp án:** Body là stream tiêu thụ một lần. Filter đã consume body; downstream không thể đọc lại nếu không buffer/rebuild và quản lý buffer đúng cách.

**Bài 6.** `doFinally` nhận `CANCEL` nghĩa là server chắc chắn đã dừng toàn bộ công việc remote?

**Đáp án:** Không. Đó là cancellation ở subscription quan sát; tác vụ vật lý phía driver/server phụ thuộc hỗ trợ cancellation.

**Bài 7.** Nếu muốn chọn API trả value nhanh nhất, nhưng API primary có thể complete empty rất nhanh, dùng operator nào?

**Đáp án:** `Mono.firstWithValue`, nếu ngữ nghĩa nghiệp vụ cho phép đợi nguồn khác; `firstWithSignal` sẽ để empty thắng.

**Bài 8.** Có nên đưa correlation ID vào Micrometer metric tag?

**Đáp án:** Không nên nếu ID có giá trị gần như duy nhất mỗi request. Dùng ID trong log/trace; metric tag nên có cardinality thấp.

## 15. Ghi nhớ

- **HTTP request/response** và **Reactor signals** là hai lớp quan sát liên quan nhưng không đồng nhất.
- `WebFilter` phù hợp quan sát request server; `ExchangeFilterFunction` phù hợp quan sát outbound request/response metadata.
- Đo response headers khác đo thời gian tiêu thụ body. Đặt instrumentation ở đúng vị trí.
- `doOnEach` quan sát value/error/complete; `doFinally` phân biệt complete/error/cancel.
- **`firstWithSignal`** chọn bất kỳ tín hiệu đầu tiên; **`firstWithValue`** chọn giá trị đầu tiên. Empty/error có thể thắng ở operator thứ nhất nhưng không thắng ở operator thứ hai nếu nguồn khác phát value.
- Cancellation là yêu cầu hủy, không phải bằng chứng công việc vật lý đã dừng.
- Ưu tiên Micrometer Observation/tracing cho observability tổng thể; log thủ công chỉ bổ sung thông tin thực sự cần.
- Không đọc body tùy tiện, không log dữ liệu nhạy cảm và không tạo metric tag cardinality cao.

Khi điều tra một request, hãy lần theo thứ tự: **request vào server → handler tạo publisher → outbound response metadata → body được tiêu thụ → terminal signal hoặc cancellation**. Với nhiều nguồn cạnh tranh, xác định rõ hệ thống muốn chọn tín hiệu đầu tiên hay giá trị đầu tiên.

## Tài liệu chính thức

- Spring Framework, **WebFlux – Reactive Core and Logging**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework, **WebClient Filters (`ExchangeFilterFunction`)**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
- Spring Framework, **WebClient Configuration and ObservationRegistry**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework, **WebClient Exchange and Response Body Handling**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework, **Observability Support**: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Project Reactor 3.6.6, **Mono API (`firstWithSignal`, `firstWithValue`, `doOnEach`, `doFinally`)**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html
- Project Reactor 3.6.6, **Flux API (`firstWithSignal`, `firstWithValue`)**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor 3.6.6, **Testing with StepVerifier and virtual time**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html