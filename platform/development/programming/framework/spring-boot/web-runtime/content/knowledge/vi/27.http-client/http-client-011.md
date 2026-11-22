# Tránh block() trên event loop và thử lại yêu cầu không lũy đẳng

## 1. Tình huống: một HTTP client có thể vừa làm nghẽn hệ thống vừa tạo tác động trùng

Một dịch vụ Spring Boot gọi HTTP API của đối tác để đọc danh mục hàng hóa và tạo đơn hàng. Hai thao tác đều có thể đi qua `WebClient`, nhưng chúng có **hai rủi ro hoàn toàn khác nhau**:

1. **Rủi ro luồng thực thi:** developer gọi `webClient.get().retrieve().bodyToMono(...).block()` trong một WebFlux handler. Thread đang phụ trách nhiều kết nối bị giữ lại để chờ kết quả; trong các non-blocking scheduler của Reactor, `block()` còn có thể ném `IllegalStateException` ngay. Độ trễ p95/p99 tăng, connection chờ lâu và khả năng phục vụ giảm.
2. **Rủi ro ngữ nghĩa nghiệp vụ:** developer thêm `retryWhen(Retry.max(3))` cho mọi HTTP request. Với một lệnh `POST /payments`, lần đầu server đã ghi giao dịch nhưng response mất; retry tạo giao dịch thứ hai nếu server không chống trùng. HTTP timeout hoặc 503 **không chứng minh tác động phía server chưa xảy ra**.

**Không được dùng retry để chữa blocking** và cũng không mặc định cho rằng WebClient tự bảo đảm “exactly once”. Phải giải hai vấn đề ở **hai lớp khác nhau**: điều phối non-blocking ở runtime và bảo đảm idempotency ở hợp đồng API/server.

Bài này thuộc mục **HTTP client** của Spring Boot web runtime, tập trung vào:
- Event loop của Reactor Netty, `Mono`/`Flux`, `block()`, `subscribe()`, `subscribeOn`/`publishOn` và `Schedulers.boundedElastic()`.
- Retry dưới dạng **resubscription**, lọc lỗi, backoff + jitter, timeout, request body có thể phát lại và retry budget.
- HTTP safe/idempotent methods theo RFC 9110; nguy cơ với `POST`/`PATCH`, kể cả 502/503/504 và network timeout.
- `Idempotency-Key`, atomic deduplication, payload fingerprint, xử lý in-flight operation, TTL và multi-instance.
- Ví dụ Spring Boot **Java 17+ chạy được**: GET lỗi 503 rồi thành công, POST **đã áp dụng tác động nhưng trả 503**, client retry cùng khóa và vẫn chỉ có một tác động nghiệp vụ.
- Kiểm thử, log/metric, cảnh báo khi gọi service thật và phương án thay thế khi không thể bảo đảm idempotency.

> **Phiên bản thực hành:** Spring Boot 3.5.x, Java 17+, `spring-boot-starter-webflux`, WebClient + Project Reactor. Với Boot 4.x, chọn đúng starter và API theo phiên bản. Demo chạy độc lập trên `localhost:8080`, không gọi cổng thanh toán thật; object store trong RAM **chỉ minh họa**, không đủ cho production.

## 2. Phân biệt HTTP client với web server, MVC với WebFlux

Spring Framework có hai hướng lập trình HTTP client phổ biến:

| Client | Cách gọi | Đặc tính chính | Thường hợp phù hợp |
|---|---|---|---|
| `RestClient` / `RestTemplate` | Đồng bộ/blocking theo API | Caller chờ đến khi có response | Ứng dụng MVC/JDBC hoặc job đồng bộ |
| `WebClient` | `Mono`/`Flux`, reactive | Có thể giữ call-chain không chặn event loop | WebFlux, streaming, composition bất đồng bộ |
| Reactor Netty `HttpClient` | Low-level reactive network client | Kiểm soát connection, timeouts, transport | Khi cần custom Netty transport bên dưới WebClient |

**WebClient dùng được cả trong Spring MVC lẫn WebFlux.** Một MVC controller chạy trên Servlet thread có thể dùng `WebClient.block()` ở biên đồng bộ khi đã tính capacity; điều đó **không đồng nghĩa lỗi `block()` giống trên WebFlux event loop**. Nhưng vì caller vẫn phải chờ, trong hệ thống MVC thuần có thể đơn giản hơn khi dùng `RestClient`.

Với **Spring WebFlux**, handler nên trả `Mono<T>`, `Flux<T>` hoặc reactive wrapper phù hợp để runtime tự subscribe. Không ép WebFlux thành mô hình đồng bộ bằng cách gọi `block()` trong `@GetMapping`.

### Event loop là gì?

Reactor Netty dùng một số lượng thread event-loop tương đối nhỏ để xử lý nhiều kết nối HTTP bất đồng bộ. Khi chờ socket/network I/O, thread có thể phục vụ công việc khác thay vì đứng đợi một request riêng. Các thread thường có tên giống `reactor-http-nio-*`, nhưng tên phụ thuộc môi trường.

Sơ đồ:

~~~text
Inbound HTTP request -> Reactor Netty event loop
                            |
                            +--> WebFlux handler trả Mono
                                      |
                                      +--> WebClient request (async)
                                      |
                                      +--> callback khi response đến
                                      |
                                      +--> ghi response cho caller
                            |
                            +--> event loop còn khả năng xử lý kết nối khác
~~~

Nếu một đoạn code chiếm event loop trong hàng trăm mili-giây hoặc vài giây, nhiều kết nối khác bị ảnh hưởng. Việc có “nhiều CPU cores” không giải quyết được nếu mọi thread event-loop đều bị block bởi `Thread.sleep`, JDBC, filesystem/network I/O đồng bộ hoặc `block()`.

**Non-blocking không có nghĩa nhanh vô hạn.** Dù không block, ứng dụng vẫn chịu giới hạn connection pool, CPU, downstream concurrency, memory, event-loop lag và backpressure.

## 3. Vì sao `Mono.block()` là anti-pattern trên event loop?

Phản ví dụ trong một ứng dụng WebFlux:

~~~java
// SAI khi chạy trên event-loop trong handler WebFlux.
@GetMapping("/orders/{id}")
public OrderDto order(@PathVariable String id) {
    return webClient.get()
            .uri("/remote/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .block(); // Chặn thread đang thực thi handler.
}
~~~

Đây là fragment minh họa, `OrderDto` và `webClient` không được định nghĩa để chạy độc lập. Nếu callback/handler chạy trên thread có marker `NonBlocking`, Reactor thường ném lỗi tương tự:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Thông điệp thực tế và tên thread phụ thuộc version/runtime. **Đừng dựa vào exception này làm hệ thống phát hiện blocking duy nhất**: nhiều tác vụ blocking như file I/O, JDBC hay `Thread.sleep` có thể không tự ném lỗi, nhưng vẫn làm chậm event loop.

### Cách đúng: trả publisher, để WebFlux quản lý subscribe

~~~java
// Fragment ĐÚNG trong controller WebFlux.
@GetMapping("/orders/{id}")
public Mono<OrderDto> order(@PathVariable String id) {
    return webClient.get()
            .uri("/remote/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class);
}
~~~

Request được mô tả bằng một pipeline, sau đó **framework subscribe** ở ranh giới xử lý HTTP. Handler không cần tạo một thread riêng, không cần `block()` và không cần `subscribe()` thủ công.

Nếu cần biến đổi hay gọi tiếp service:

~~~java
// Fragment: orderClient và inventoryClient là hai WebClient phù hợp.
Mono<OrderView> view(String id) {
    return orderClient.get()
            .uri("/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderDto.class)
            .flatMap(order ->
                inventoryClient.get()
                    .uri("/stock/{sku}", order.sku())
                    .retrieve()
                    .bodyToMono(StockDto.class)
                    .map(stock -> new OrderView(order, stock))
            );
}
~~~

Đây là fragment thiết kế: `OrderDto`, `StockDto`, `OrderView` là records/DTOs giả định trong ứng dụng. `flatMap` kết hợp công việc bất đồng bộ; `map` dành cho phép biến đổi đồng bộ rất nhanh. **Không gọi blocking method trong lambda của `map`**.

## 4. `subscribe()` thủ công cũng thường sai trong controller

Phản ví dụ:

~~~java
@GetMapping("/fire-and-forget")
public String wrong() {
    webClient.post()
            .uri("/remote/orders")
            .retrieve()
            .bodyToMono(Void.class)
            .subscribe(); // Tách khỏi vòng đời request, không quản lý lỗi.
    return "queued";
}
~~~

Đây **không phải** bằng chứng đơn hàng đã được ghi. Handler trả `queued` trước khi nhận kết quả, và lỗi HTTP có thể xảy ra sau response. Cancellation, tracing, retry, lifecycle và error propagation có thể mất liên kết; test rất khó kiểm tra.

Cách đúng tùy mục đích:
- **Caller cần kết quả:** trả `Mono<Receipt>` hoặc `Mono<ResponseEntity<...>>` để framework đợi non-blocking.
- **Công việc nền thật sự:** ghi một công việc bền vào queue/outbox với state/idempotency, trả `202 Accepted` cùng operation ID, có endpoint kiểm tra trạng thái. Không biến `subscribe()` không giám sát thành hàng đợi đáng tin cậy.
- **Test/main hoặc biên đồng bộ được kiểm soát:** có thể subscribe/block ở nơi phù hợp và hiểu rõ lifecycle, nhưng không làm vậy trong callback đang chạy trên event loop.

Một `Mono` lạnh (**cold publisher**) có thể **thực hiện lại HTTP request khi được subscribe thêm lần nữa**. Do đó double subscription vô ý cũng là nguyên nhân tác động trùng độc lập với `retryWhen`.

## 5. Khi có thư viện đồng bộ: dùng boundedElastic đúng cách

Không phải mọi phần mềm có phiên bản non-blocking. Bạn có thể đang dùng JDBC, thư viện ký tài liệu, SDK đồng bộ hoặc filesystem API blocking. Không gọi trực tiếp các hàm đó trên Reactor event loop.

Ví dụ hợp lệ để bọc **một lời gọi blocking** (fragment service):

~~~java
Mono<Customer> loadCustomer(String id) {
    return Mono.fromCallable(() -> legacyJdbcClient.findCustomer(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Cần imports `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`; `legacyJdbcClient` và `Customer` là service/DTO của project thật. `Mono.fromCallable` trì hoãn thực thi cho đến lúc subscribe, còn `subscribeOn(Schedulers.boundedElastic())` chuyển **việc thực thi source** sang scheduler phù hợp cho các tác vụ blocking có kiểm soát.

**Không sửa bằng cách viết:**

~~~java
// SAI: blocking xảy ra trước khi Mono được tạo.
Customer value = legacyJdbcClient.findCustomer(id);
return Mono.just(value).subscribeOn(Schedulers.boundedElastic());
~~~

Ở đoạn sai, JDBC đã block thread hiện tại trước khi `subscribeOn` có cơ hội tác động. `Mono.just(...)` tạo publisher từ một kết quả đã được tính xong, không trì hoãn `findCustomer`.

### subscribeOn và publishOn khác nhau

| API | Ảnh hưởng |
|---|---|
| `subscribeOn(scheduler)` | Lựa chọn scheduler cho **subscription/source**; phù hợp `fromCallable` với blocking legacy call |
| `publishOn(scheduler)` | Chuyển execution context cho các **operator downstream** kể từ vị trí đó |
| `Schedulers.boundedElastic()` | Pool có giới hạn dành cho tác vụ chờ/blocking, không phải event loop |
| `Schedulers.parallel()` | Dành cho công việc CPU/non-blocking; không phải nơi offload blocking I/O |
| `Schedulers.single()` | Một worker shared; không dùng cho blocking I/O |

`boundedElastic` không làm JDBC trở thành reactive. Nó chỉ cô lập phần chờ khỏi event loop; nếu số lời gọi blocking vượt giới hạn scheduler, công việc bị chờ trong queue và latency vẫn có thể tăng. Với workload database lớn, cân nhắc **R2DBC** hoặc kiến trúc service có thread pool, connection pool và concurrency budget tương ứng.

Không gọi `block()` bên trong `Mono.fromCallable` chỉ để “hợp pháp hóa” việc sử dụng WebClient nếu có thể giữ nguyên pipeline reactive. Với blocking SDK bắt buộc, cô lập một **lệnh đồng bộ thực** và theo dõi capacity.

## 6. Retry trong Reactor thực sự có nghĩa gì?

Một lệnh:

~~~java
someMono.retryWhen(Retry.backoff(2, Duration.ofMillis(100)))
~~~

không “chạy tiếp” cùng HTTP response lỗi. Reactor **resubscribe vào upstream publisher** sau một tín hiệu `onError`, theo chiến lược Retry. Nếu upstream là một HTTP request lạnh từ WebClient, **mỗi subscription mới có thể gửi một HTTP request mới**.

Với `Retry.backoff(2, ...)`:
- Lần đầu: một attempt.
- Tối đa **hai lần retry** sau lỗi phù hợp.
- Tối đa **ba attempts** tổng cộng.
- Không retry khi publisher đã thành công hoặc lỗi không thỏa `filter`.
- Khi hết retry, Reactor có thể phát lỗi retry-exhausted chứa cause cuối, nếu không tùy chỉnh `onRetryExhaustedThrow`.

Một retry chain đúng thường gồm:
1. **Eligibility:** thao tác có an toàn để lặp lại không?
2. **Error classification:** loại lỗi nào có khả năng tạm thời?
3. **Budget:** tối đa bao nhiêu retries và tổng thời gian?
4. **Backoff/jitter:** tránh mọi client retry đồng loạt.
5. **Observability:** phân biệt attempts, retry reasons, exhausted, result.
6. **Idempotency:** nếu có side effect, ai bảo đảm tác động nghiệp vụ không trùng?

### Retry là resubscription, không tự hiểu nghiệp vụ

~~~text
subscribe #1 -> POST /charge -> server đã ghi giao dịch
             -> response bị mất / timeout / 503
                         |
                         v
                 retryWhen(...)
                         |
                         v
subscribe #2 -> POST /charge -> server có thể ghi giao dịch lần hai
~~~

Câu hỏi quan trọng **không phải** “HTTP client có được retry không?” mà là “**sau khi retry, hệ thống có giữ nguyên đúng một tác động nghiệp vụ không?**”.

## 7. Idempotent và safe methods theo RFC 9110

HTTP định nghĩa ý nghĩa của các phương thức theo chuẩn, không theo mong muốn của riêng HTTP client.

| Method | Safe theo semantics? | Idempotent theo RFC 9110? | Gợi ý về retry |
|---|---|---|---|
| `GET` | Có | Có | Thường có thể retry lỗi tạm thời nếu endpoint tuân nghĩa GET |
| `HEAD` | Có | Có | Tương tự GET |
| `OPTIONS` | Có | Có | Cân nhắc theo hợp đồng và tầng trung gian |
| `TRACE` | Có | Có | Thường bị vô hiệu hóa trong hệ thống thực tế |
| `PUT` | Không | Có | Có thể retry cùng replacement state nếu API tuân semantics PUT |
| `DELETE` | Không | Có | Về **intended effect** là idempotent; response 404 sau xóa lặp vẫn có thể hợp lệ |
| `POST` | Không | **Không bảo đảm** | Không tự động retry nếu không có hợp đồng idempotency |
| `PATCH` | Không | **Không bảo đảm** | Retry an toàn chỉ khi patch operation/hợp đồng có tính idempotent |

Theo **RFC 9110 `9.2.2**, một method là idempotent nếu hiệu ứng **được người dùng yêu cầu** sau nhiều request giống nhau như khi chỉ gửi một request. Nó **không yêu cầu các response phải giống hệt nhau**: DELETE đầu tiên có thể trả 204, lần sau trả 404 mà intended state vẫn là resource đã bị xóa.

**Safe** và **idempotent** là hai khái niệm khác: GET được định nghĩa safe (không yêu cầu thay đổi trạng thái server), còn PUT/DELETE idempotent nhưng vẫn thay đổi trạng thái.

### Tên method không cứu được endpoint thiết kế sai

Nếu endpoint `GET /transfer-money` thực tế chuyển tiền, nó vi phạm semantics GET dù developer tự cho là “GET thì retry được”. Ngược lại, một `POST /operations` có thể được thiết kế **idempotent ở mức nghiệp vụ** bằng key/deduplication; sau khi hợp đồng đó được kiểm chứng, client mới có căn cứ retry.

`PUT` cũng không loại bỏ mọi rủi ro: server có thể gửi event/notification cho mỗi request, request conditional `If-Match` có thể khiến response lần hai khác, hoặc upstream API không tuân semantics. Cần kiểm chứng **effect mà nghiệp vụ quan tâm**.

## 8. Vì sao timeout/503 không chứng minh POST thất bại?

Giả sử client gọi `POST /payments`:

~~~text
T0 Client gửi request, amount = 500, order = O-1
T1 Server nhận request và ghi transaction vào DB
T2 Server commit thành công
T3 Load balancer đóng kết nối / client timeout
T4 Client không thấy response
T5 Client retry POST
T6 Server ghi transaction lần nữa nếu không dedupe
~~~

Client chỉ biết rằng **chưa xác nhận được kết quả**, không biết thao tác ở T2 đã commit hay chưa. Đây là **ambiguous outcome**, còn gọi “unknown outcome”.

Tương tự:
- `502 Bad Gateway`: gateway có thể mất upstream connection sau khi upstream đã commit.
- `503 Service Unavailable`: có thể xuất hiện trước hoặc sau khi một tầng nhận/xử lý request.
- `504 Gateway Timeout`: upstream có thể vẫn tiếp tục thực thi sau khi gateway hết thời gian chờ.
- TCP reset / read timeout: request có thể đã được truyền đến server.
- Client cancellation: hủy publisher phía client không luôn hủy tác động đã commit phía server.

**Tuyệt đối không đặt quy tắc “POST gặp 5xx thì chắc chắn chưa thực thi”**. Một phản hồi lỗi chỉ là tín hiệu của HTTP processing, không phải bằng chứng rollback transaction.

### Trường hợp nào có thể retry POST?

Chỉ khi có **bằng chứng/hợp đồng** phù hợp, ví dụ:
- Server chấp nhận `Idempotency-Key` và bảo đảm cùng key + cùng payload chỉ tạo **một effect** trong khoảng retention.
- Endpoint POST có semantics idempotent được tài liệu hóa và kiểm thử.
- Client có thể chứng minh request **chưa hề được áp dụng**, điều này thường khó với generic network errors.
- Client thực hiện **status reconciliation** qua operation ID và server xác nhận chưa có tác động.

Ngay cả với key, cần xử lý các tình huống trùng từ **hai client hoặc nhiều replica**, không chỉ retry của một WebClient trong một JVM.

## 9. Retry có bộ lọc lỗi, giới hạn và backoff

Với endpoint GET idempotent, một policy minh họa:

~~~java
// Fragment WebClient call dùng Reactor, không phải class độc lập.
Mono<Catalog> catalog = webClient.get()
        .uri("/catalog")
        .retrieve()
        .bodyToMono(Catalog.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(error ->
                    error instanceof WebClientResponseException e
                        && (e.getStatusCode().value() == 503
                            || e.getStatusCode().value() == 429))
        );
~~~

Imports: `reactor.util.retry.Retry`, `java.time.Duration`, `org.springframework.web.reactive.function.client.WebClientResponseException`. `Catalog` là DTO giả định. Với `retrieve()`, mặc định 4xx/5xx biến thành `WebClientResponseException`; API `onStatus(...)` có thể tùy biến mapping.

**Đây mới là policy ví dụ**, chưa tự động “production-safe”: 
- `429 Too Many Requests` có thể mang `Retry-After`, cần **tôn trọng thời điểm server yêu cầu**. `Retry.backoff` không tự parse/áp dụng `Retry-After`.
- `503` có thể mang `Retry-After` và phải xem tài liệu đối tác.
- Network connection reset/timeout cũng có thể tạm thời, nhưng policy phải cân nhắc có an toàn về **request semantics** và ngân sách retry.
- Không retry bừa các lỗi `400`, `401`, `403`, `404`, `409`, `422`. Chúng thường yêu cầu sửa request, credentials, quyền hoặc xử lý conflict.
- Với GET, `404` thường không được giải quyết bằng thử liên tiếp, trừ khi API có eventual consistency contract cụ thể.
- `Retry.max(n)` hoặc `Retry.backoff(n, ...)` dùng **n retries**, khác **n attempts**.

### Backoff + jitter

~~~text
Attempt #1  -> 503
Chờ gần 100 ms (có jitter)
Attempt #2  -> 503
Chờ gần 200 ms (có jitter, maxBackoff có thể giới hạn)
Attempt #3  -> 200 hoặc lỗi cuối
~~~

Thời gian trên chỉ minh họa khi minBackoff là 100ms và exponential backoff; khi jitter bật, thời điểm **không cố định**. Mục đích là tránh “retry storm”: hàng nghìn client cùng gặp 503 rồi cùng thử lại chính xác sau 100ms.

**Cần total retry budget**, không chỉ maxRetries. Chẳng hạn request có deadline 2s nhưng backoff và timeout mỗi attempt tổng cộng 10s thì client tổng thể có thể vi phạm SLO. Giới hạn attempts, response timeout, total elapsed time, số connection và số concurrent in-flight operations cần phối hợp.

## 10. Đặt timeout ở đâu so với retryWhen?

Reactor `timeout(Duration)` tạo lỗi `TimeoutException` khi pipeline không phát tín hiệu đúng hạn. Vị trí operator làm thay đổi phạm vi:

~~~java
// Mỗi attempt có timeout riêng; retryWhen có thể xử lý
// TimeoutException nếu policy filter cho phép.
Mono<Catalog> perAttempt = fetchCatalog()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy);
~~~

~~~java
// Timeout áp cho tổng pipeline gồm các lần retry + backoff.
Mono<Catalog> overall = fetchCatalog()
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(5));
~~~

Đây là fragments; `fetchCatalog` và `retryPolicy` được khai báo trong service thật.

- **Attempt timeout** đặt trước `retryWhen` có thể phát lỗi cho từng subscription; nếu filter retry không chấp nhận `TimeoutException`, lỗi đó **không được retry**.
- **Overall timeout** đặt sau `retryWhen` đặt giới hạn cho toàn bộ công việc.
- Có thể dùng cả hai khi policy rõ ràng, nhưng phải test hành vi cancellation và user-facing errors.
- HTTP connector (Reactor Netty `responseTimeout`, connect timeout, pool acquire timeout) có các giới hạn khác. Một timeout từ HTTP transport **không mặc nhiên có nghĩa server chưa commit**.

**Không lạm dụng timeout cực ngắn** để “giúp fail fast”: có thể biến request bình thường thành chuỗi retries, tăng tải downstream và tạo nhiều uncertain outcomes.

## 11. Lặp lại ở đúng vị trí: retry chỉ phần HTTP được phép thử lại

Reactor retry **lặp cả upstream publisher** ở phía trước operator. Giả sử có:
- `debitWallet()`: trừ tiền không có idempotency.
- `notifyPartner()`: gửi một HTTP request.

Phản ví dụ:

~~~java
// SAI: debitWallet() nằm upstream của retryWhen nên có thể chạy lại.
return debitWallet()
        .then(notifyPartner())
        .retryWhen(Retry.max(2));
~~~

Nếu `debitWallet()` là một cold publisher tạo side effect ở mỗi subscription, lệnh trên có thể trừ tiền nhiều lần. Chuyển retry vào nhánh HTTP (chỉ sau khi phía đối tác bảo đảm idempotency) giúp thu hẹp phạm vi:

~~~java
// Minh họa cấu trúc; vẫn phải thiết kế outbox/transaction đúng nghiệp vụ.
return debitWallet()
        .then(notifyPartner().retryWhen(partnerSafeRetry));
~~~

**Không suy ra cách thứ hai tự bảo đảm exactly-once**: nếu cả `debitWallet` và `notifyPartner` là hai giao dịch trên hai hệ thống, vẫn cần outbox, saga hoặc reconciliation. Sửa vị trí `retryWhen` chỉ loại bớt việc vô tình lặp tác động ở upstream.

### Không nuốt lỗi trước khi retry

~~~java
// Phản ví dụ: lỗi HTTP đã biến thành giá trị thành công,
// nên retryWhen bên dưới không còn thấy onError.
return fetch()
    .onErrorReturn(fallbackValue)
    .retryWhen(retryPolicy);
~~~

Nếu muốn retry một lỗi tạm thời trước khi fallback, thứ tự thường là:

~~~java
return fetch()
    .retryWhen(retryPolicy)
    .onErrorReturn(fallbackValue);
~~~

Nhưng fallback value có thể che giấu trạng thái dữ liệu không cập nhật. Cần quy định khi nào được dùng cached/stale data và khi nào phải báo lỗi rõ ràng.

## 12. Body của request phải có thể phát lại

`retryWhen` resubscribe upstream. Với WebClient, request body phải có nguồn dữ liệu có thể tạo lại:

~~~java
// Thường có thể serialize lại cùng immutable DTO.
.bodyValue(new OrderRequest("O-1", 500))
~~~

Nguy hiểm hơn:

~~~java
// Fragment: chỉ đọc InputStream một lần; source có thể không replayable.
// Không sao chép cách này vào ứng dụng thật để retry file upload.
.body(BodyInserters.fromDataBuffers(oneShotDataBufferFlux))
~~~

Một `Flux<DataBuffer>` đọc từ file stream một lượt, publisher có state bên ngoài hoặc stream đã đóng có thể **không phát lại được** khi retry. Nếu body được phép retry, cần thiết kế **replayability** (tạo stream mới cho mỗi attempt, nguồn dữ liệu bền hoặc buffer có giới hạn và quản lý DataBuffer đúng chuẩn).

Ngoài ra phải giữ nhất quán:
- Payload JSON/file bytes.
- Request method và URL.
- `Idempotency-Key`.
- Nội dung quan trọng để server fingerprint.
- Authentication context; refresh token nếu cần qua một luồng riêng, không tự retry vô hạn.
- Retry count và deadline.

Một request POST có key ổn định nhưng body khác khi retry là **vi phạm hợp đồng** và phải được server từ chối, không được coi như tiếp tục cùng operation.

## 13. Idempotency-Key: cơ chế nghiệp vụ bảo vệ POST

Client tạo một khóa **duy nhất cho một thao tác nghiệp vụ**, ví dụ:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7c7c6a4c-29db-46c6-90cc-89d066eb72e1

{"orderId":"O-1","cents":500}
~~~

Nếu client phải retry, **gửi lại cùng key + cùng payload**:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7c7c6a4c-29db-46c6-90cc-89d066eb72e1

{"orderId":"O-1","cents":500}
~~~

Các giá trị chỉ là ví dụ. Một khóa thực tế nên được sinh đủ ngẫu nhiên (như UUID), không tái sử dụng giữa **hai** thao tác thật. Khi người dùng nhấn “Mua” hai lần cho cùng một thao tác đã được xác nhận, hệ thống cần xác định đó là **retry của cùng operation** hay một **đơn mới**; chính nghiệp vụ quyết định.

### Sinh key ở ngoài phạm vi retry

Đúng:

~~~java
// Fragment: key được tạo một lần cho một business operation.
String key = UUID.randomUUID().toString();
OrderRequest command = new OrderRequest("O-1", 500);
Mono<OrderReceipt> call = sendOrder(key, command)
        .retryWhen(safePostRetry);
~~~

Sai nếu mỗi attempt đổi key:

~~~java
// SAI: mỗi resubscription tạo khóa khác, server coi là đơn khác.
Mono<OrderReceipt> call = Mono.defer(() ->
        sendOrder(UUID.randomUUID().toString(), command))
        .retryWhen(safePostRetry);
~~~

Nếu method `sendOrder` bên trong **đã** gắn `retryWhen`, không thêm một lớp retry trùng ở ngoài mà không tính tổng số attempts. Nên đưa policy về một nơi dễ quan sát và phân loại.

### Key không đủ nếu server không thực thi đúng

Client gửi `Idempotency-Key` chỉ là một header. Nó **không tự khóa** transaction. Server cần một hợp đồng rõ ràng và thường có các bước:

1. Xác thực user/tenant và kiểm tra input.
2. Chuẩn hóa hoặc băm fingerprint của payload cùng các trường định danh scope.
3. Tìm/đăng ký key **atomically** trong store chung.
4. Nếu key mới, thực hiện operation **một lần**, ghi trạng thái và kết quả bền.
5. Nếu key cũ và payload **giống**: trả kết quả đã lưu hoặc trạng thái operation đang xử lý.
6. Nếu key cũ nhưng payload **khác**: từ chối, thường `409 Conflict` (theo contract).
7. Nếu operation đang xử lý đồng thời: trả trạng thái phù hợp, có thể `409`/`202` tùy contract; client nên poll/reconcile thay vì bắn requests vô hạn.
8. TTL/retention phải dài hơn retry window và thời gian user có thể lặp lại request.

### Scope và bảo mật của idempotency keys

Deduplication phải định danh key theo **tenant/principal + endpoint/operation type + key** hoặc scope tương đương. Không cho user A đọc lại kết quả từ key của user B. Store có thể lưu fingerprint body và reference tới bản ghi nghiệp vụ; tránh lưu plaintext secrets/card data trong cache idempotency.

Idempotency key là **định danh request**, không phải access token. Tuy vậy vì nó liên hệ với hành vi nhạy cảm, vẫn nên hạn chế log/full exposure và tạo key không đoán được. Không dùng timestamp giây làm key duy nhất.

**Trên thực tế:** tên header `Idempotency-Key` được nhiều API sử dụng và có tài liệu IETF HTTPAPI dự thảo riêng; hành vi chi tiết (lưu kết quả nào, lỗi nào được replay, retention, mismatch status) vẫn phụ thuộc **hợp đồng của nhà cung cấp API**. Đừng giả định mọi dịch vụ sẽ xử lý giống nhau khi nhìn thấy header này.

## 14. Demo chạy được: WebFlux + WebClient, GET retry và POST không bị nhân đôi

Demo là **một ứng dụng Spring Boot 3.5.x tự gọi HTTP endpoint nội bộ qua localhost** để không cần dịch vụ thứ ba. Nó mô phỏng:
- `GET /server/catalog` trả 503 ở request đầu và 200 ở request kế tiếp.
- `GET /client/catalog` gọi server bằng WebClient và retry 503; không `block()`.
- `POST /server/orders` **ghi nhận một tác động** theo key, cố ý trả 503 lần đầu **sau khi ghi nhận**; lần sau cùng key trả kết quả đã lưu.
- `POST /client/orders` giữ nguyên key/payload và retry **một lần** với 503; không tạo tác động thứ hai.
- `GET /debug/state` cho số request đến server và số side effects đã được ghi nhận trong RAM.

> **Cảnh báo:** `ConcurrentHashMap`/`AtomicInteger` trong demo chỉ là bộ nhớ **một instance**, không có transaction bền, không cluster-safe sau restart và không kết nối tiền thật. **Không áp dụng trực tiếp** mô hình in-memory này cho payment/order production.

### 14.1. Khởi tạo dự án

Tạo project bằng Spring Initializr:
- Java 17+, Spring Boot 3.5.x, Gradle.
- Dependency **Spring Reactive Web (WebFlux)**, không thêm MVC starter vào bài này.

Nếu đã có Boot Gradle plugin/dependency management, dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Đây là fragment trong project Boot, không phải toàn bộ `build.gradle`. Project từ Initializr có sẵn Gradle wrapper.

### 14.2. Một tệp Java hoàn chỉnh

Tạo `src/main/java/demo/retry/RetryDemoApplication.java`:

~~~java
package demo.retry;

import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@SpringBootApplication
@RestController
public class RetryDemoApplication {

    private final WebClient client =
            WebClient.create("http://localhost:8080");

    private final AtomicInteger catalogAttempts = new AtomicInteger();
    private final AtomicInteger appliedOrders = new AtomicInteger();

    private final Map<String, StoredOrder> orders =
            new ConcurrentHashMap<>();
    private final Set<String> failedOnceKeys =
            ConcurrentHashMap.newKeySet();

    public static void main(String[] args) {
        SpringApplication.run(RetryDemoApplication.class, args);
    }

    public record Catalog(String name) { }
    public record OrderRequest(String orderId, int cents) { }
    public record OrderReceipt(
            String orderId, int cents, String status) { }

    private record StoredOrder(
            OrderRequest request, OrderReceipt receipt) { }

    // Chỉ retry 503; giới hạn 1 retry (tối đa 2 attempts).
    private static Retry retry503Once() {
        return Retry.backoff(1, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(300))
                .jitter(0.2)
                .filter(ex ->
                    ex instanceof WebClientResponseException w
                        && w.getStatusCode().value() == 503
                );
    }

    // ========== Mock downstream: GET idempotent ==========
    @GetMapping("/server/catalog")
    public ResponseEntity<Catalog> serverCatalog() {
        if (catalogAttempts.incrementAndGet() == 1) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
        return ResponseEntity.ok(new Catalog("catalog-ready"));
    }

    // ========== WebClient GET: không block event loop ==========
    @GetMapping("/client/catalog")
    public Mono<Catalog> clientCatalog() {
        return client.get()
                .uri("/server/catalog")
                .retrieve()
                .bodyToMono(Catalog.class)
                .retryWhen(retry503Once());
    }

    // ========== Mock downstream: POST được dedupe ==========
    @PostMapping(
            path = "/server/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderReceipt> serverOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody OrderRequest command) {

        if (key.isBlank()
                || command.orderId() == null
                || command.orderId().isBlank()
                || command.cents() <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid order");
        }

        StoredOrder stored = orders.computeIfAbsent(key, k -> {
            appliedOrders.incrementAndGet();
            return new StoredOrder(
                    command,
                    new OrderReceipt(
                            command.orderId(),
                            command.cents(),
                            "APPLIED")
            );
        });

        // Không được đổi payload nhưng tái sử dụng cùng key.
        if (!stored.request().equals(command)) {
            return ResponseEntity
                    .status(HttpStatus.CONFLICT).build();
        }

        // Mô phỏng failure SAU KHI effect đã được ghi nhận.
        if (failedOnceKeys.add(key)) {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }

        return ResponseEntity.ok(stored.receipt());
    }

    // ========== WebClient POST: giữ key, chỉ retry 503 ==========
    @PostMapping(
            path = "/client/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<OrderReceipt> clientOrder(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody OrderRequest command) {

        return client.post()
                .uri("/server/orders")
                .header("Idempotency-Key", key)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(command)
                .retrieve()
                .bodyToMono(OrderReceipt.class)
                .retryWhen(retry503Once())
                // Giữ status downstream cho lỗi không retry như 409.
                .onErrorMap(
                    WebClientResponseException.class,
                    ex -> new ResponseStatusException(
                        ex.getStatusCode(),
                        "Downstream rejected order", ex)
                );
    }

    @GetMapping("/debug/state")
    public Map<String, Integer> state() {
        return Map.of(
            "catalogAttempts", catalogAttempts.get(),
            "appliedOrders", appliedOrders.get(),
            "uniqueKeys", orders.size()
        );
    }
}
~~~

**Vì sao code non-blocking?** Các handler WebFlux trả `Mono`, WebClient request xử lý bất đồng bộ, không có `block()` hay `Thread.sleep`. Các cấu trúc `AtomicInteger`/`ConcurrentHashMap` dùng trong demo là thao tác nhanh trong RAM; chúng không thực hiện I/O blocking. Reactor Netty có thể phục vụ request client → server trên cùng ứng dụng mà không phải dừng event loop.

**Vì sao POST retry an toàn trong demo?** Server mock **dedupe theo key** bằng `computeIfAbsent`, cùng payload thì trả `StoredOrder` cũ; side effect counter chỉ được tăng trong nhánh tạo key mới. `failedOnceKeys` mô phỏng lần đầu **đã ghi nhận** nhưng trả 503. Đó là ví dụ minh họa đảm bảo ở một JVM, **không phải giải pháp production**.

**Lưu ý về `onErrorMap`:** khi server trả 409, `retrieve()` mặc định tạo `WebClientResponseException`. Nếu không map đúng, API proxy có thể biến lỗi downstream thành status không mong muốn ở frontend. Ở đây `onErrorMap` nằm **sau retryWhen**, nên lỗi 503 được retry theo rule, còn status không retry được ánh xạ sang `ResponseStatusException`. Các status của retry-exhausted có thể được Reactor bọc; production cần policy lỗi đầy đủ cho trường hợp đó.

### 14.3. Khởi động

Từ thư mục root project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Mặc định server chạy `http://localhost:8080`. Tắt ứng dụng khác đang dùng port đó. Nếu bạn đổi `server.port`, phải cập nhật **cả** địa chỉ `WebClient.create(...)` đang hardcode cho demo; production nên inject `WebClient.Builder` với base URL cấu hình từ environment.

### 14.4. Thử GET có retry

~~~bash
curl -sS -i http://localhost:8080/client/catalog
~~~

Với một JVM vừa khởi động, server catalog lần đầu trả 503 rồi lần thứ hai trả 200. WebClient nhận lỗi 503, Reactor retry một lần, response cuối có status `200 OK` và **body JSON kỳ vọng**:

~~~json
{"name":"catalog-ready"}
~~~

Nếu gọi lại GET sau đó, catalog tiếp tục thành công không cần retry. Khi nhìn `catalogAttempts` sẽ thấy ít nhất 2 sau lần test đầu tiên; những test đã gọi catalog trước đó làm số count thay đổi.

### 14.5. Thử POST: lỗi 503 nhưng chỉ một effect

Client tạo key cho một operation; trong ví dụ manual dùng `order-demo-1` để dễ quan sát:

~~~bash
curl -sS -i \
  -H 'Idempotency-Key: order-demo-1' \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"O-1","cents":500}' \
  http://localhost:8080/client/orders
~~~

Flow:
1. WebClient POST lần 1 với key `order-demo-1`.
2. `serverOrder` lưu `StoredOrder`, tăng `appliedOrders` lên 1.
3. Server cố ý trả **503** sau khi lưu.
4. WebClient thấy `WebClientResponseException` 503, đợi backoff rồi retry.
5. WebClient POST lần 2 với **cùng key và cùng body**.
6. Server tìm `StoredOrder` cũ, **không tăng `appliedOrders`**, trả receipt.

HTTP body cuối cùng kỳ vọng:

~~~json
{"orderId":"O-1","cents":500,"status":"APPLIED"}
~~~

**Đây là điểm then chốt:** nếu mock server cứ tăng counter cho mọi POST mà không dedupe, retry có thể gây **hai effects**. Chúng ta chỉ đạt một effect trong demo vì **server biết khóa và kiểm tra trạng thái**, không phải do magic của `retryWhen`.

### 14.6. Kiểm tra state

~~~bash
curl -sS http://localhost:8080/debug/state
~~~

Nếu sau khi startup bạn chỉ gọi `GET /client/catalog` một lần và `POST /client/orders` một lần như trên, ba giá trị trong JSON sẽ là:
- `catalogAttempts = 2`
- `appliedOrders = 1`
- `uniqueKeys = 1`

Định dạng object có thể như:

~~~json
{"catalogAttempts":2,"appliedOrders":1,"uniqueKeys":1}
~~~

Thứ tự field JSON không được bảo đảm vì `Map.of(...)`. Nếu có nhiều lần gọi API hay test trước đó, counters sẽ khác. Hãy dùng giá trị số bên trong field thay vì so sánh raw body nguyên văn.

Thử **gửi lại chính POST trên** với key `order-demo-1` và payload giống hệt: server trả receipt đã có, `appliedOrders` vẫn 1.

### 14.7. Key cũ nhưng payload khác phải bị từ chối

~~~bash
curl -sS -i \
  -H 'Idempotency-Key: order-demo-1' \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"O-2","cents":500}' \
  http://localhost:8080/client/orders
~~~

Server thấy `orderId` khác dưới cùng key, trả **409 Conflict** theo policy demo. Client không retry 409, và `onErrorMap` ánh xạ status downstream thành `ResponseStatusException` để bên ngoài nhìn thấy 409; JSON lỗi chi tiết có thể thay đổi theo Spring Boot error handling config. `appliedOrders` vẫn 1.

Nếu gửi **key mới** cho một order mới, counter tăng lên 2 như một hoạt động nghiệp vụ khác; đừng tái sử dụng cùng key cho nhiều orders thật.

## 15. Tại sao demo không đủ cho production?

Demo dùng memory và `computeIfAbsent` để giải thích logic. Production thường có nhiều replicas và có thể restart:

~~~text
Client POST (key=K) -> instance A: ghi payment
Client retry K      -> instance B: B không thấy K nếu chỉ lưu RAM
                                  -> có nguy cơ ghi payment lần hai
~~~

Muốn bảo đảm idempotency ở mức nghiệp vụ thực, cần **store chia sẻ và bền**:
1. Unique constraint hoặc khóa bảo đảm **một key trong scope** được đăng ký atomic.
2. Ghi fingerprint, trạng thái `IN_PROGRESS/SUCCEEDED/FAILED` và kết quả theo contract.
3. Transaction phù hợp để kết nối việc đăng ký key với bản ghi nghiệp vụ, hoặc thiết kế recovery khi không thể atomic cùng một DB.
4. Với external side effects (gửi tiền qua bên thứ ba), dùng **outbox, saga, workflow orchestration hoặc reconciliation**; không thể chỉ dựa vào local DB transaction mà kết luận hệ thống phân tán có exactly-once end-to-end.
5. Chặn hai request đồng thời cùng key: request thứ hai có thể chờ ngắn, nhận 202 + polling, hoặc nhận conflict/in-progress response theo API contract.
6. TTL đủ dài; khi record đã hết retention, key có thể được coi là mới. Client phải hiểu cửa sổ bảo vệ.
7. Store/replay response theo policy khi đã hoàn thành, bao gồm status và body có thể tái lập một cách an toàn.

### Redis SETNX có đủ chưa?

`SET key value NX` có thể là một phần của cơ chế **claim key** tạm, nhưng:
- Key có thể hết TTL giữa lúc operation chưa hoàn tất.
- Worker chết giữa “claim key” và commit effect.
- Hai hệ thống có thể không cùng transaction.
- Không thể chỉ dựa vào một khóa Redis rồi tuyên bố exactly-once.

Nếu side effect nằm trong một database, cách thiết kế rõ hơn thường là **unique business key + transaction trong cùng DB**, kết hợp outbox cho việc phát event sau commit. Nếu effect ở partner, buộc phải sử dụng idempotency contract của partner hoặc reconciliation.

## 16. Replay response, 202 và key đang xử lý

Không phải API nào cũng trả receipt cuối ngay:

~~~text
POST /payments (Idempotency-Key: K)
   -> 202 Accepted + operationId

GET /operations/{id}
   -> PENDING / SUCCEEDED / FAILED
~~~

Đây là một thiết kế phù hợp nếu xử lý lâu. Khi client timeout sau POST, nó nên tra `operationId`/`merchantOrderId` hoặc gửi lại cùng key theo contract, chứ không tạo payment mới.

Khi nhận lại K:
- **Đã thành công:** trả receipt cũ hoặc đường dẫn tra cứu.
- **Đang xử lý:** trả cùng operation ID/trạng thái chờ.
- **Key tồn tại với fingerprint khác:** từ chối rõ ràng.
- **Chưa thấy K:** chỉ thực hiện mới sau cơ chế đăng ký atomic.
- **Có kết quả thất bại:** quyết định replay lỗi hay cho phép retry phải là **quy tắc server đã tài liệu hóa**. Không tùy tiện biến lỗi nghiệp vụ cuối cùng thành một operation mới cùng key.

Nếu server chỉ trả `202` mà client coi là “đã thanh toán xong”, logic nghiệp vụ sẽ sai. 202 nghĩa là request được chấp nhận để xử lý, không phải bằng chứng tác động cuối đã hoàn tất.

## 17. Retry-After, rate limiting và backpressure

### 429 và 503 không đồng nghĩa “thử lại ngay”

Server có thể gửi:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
~~~

`Retry-After` có thể là số giây hoặc HTTP-date theo semantics HTTP. Client phải đọc/parsing đúng nếu hợp đồng yêu cầu, tính tổng deadline và tránh những retry vượt ngân sách. `Retry.backoff` **không tự hiểu header này** khi chỉ nhận một `WebClientResponseException` qua generic retry filter.

Nếu hàng nghìn WebClient cùng retry:
- Downstream có thể bị “retry storm”.
- Connection pool queue/phân bổ timeout tăng.
- Tài nguyên event loop và memory bị áp lực dù không `block()`.
- Retry có thể làm outage nặng thêm.

Giải pháp hệ thống:
- Backoff theo exponential + jitter.
- Giới hạn total attempts và overall deadline.
- Circuit breaker, bulkhead/concurrency limit, rate limiter khi có nhu cầu.
- Retry budget theo service/tenant, không chỉ từng HTTP call.
- `Retry-After` hoặc server-side load shedding policy.
- Tracing/metrics phân biệt initial requests và retry attempts.

**Đặc biệt với POST không lũy đẳng:** rate limiter/circuit breaker chỉ giảm tải, **không tạo idempotency**. Vẫn cần server dedupe/status reconciliation.

## 18. Timeout và retry không phải cùng một lỗi

Bảng tóm tắt chính sách gợi ý **sau khi phân loại semantics**:

| Tín hiệu | GET/HEAD idempotent | POST/PATCH chưa có idempotency |
|---|---|---|
| `429` có Retry-After | Có thể retry sau delay hợp lệ | Không tự retry; cần hợp đồng chống trùng và budget |
| `503` tạm thời | Có thể backoff và retry | Có thể đã áp dụng effect, không blind retry |
| `502/504` từ proxy | Có thể retry có giới hạn | Outcome có thể unknown, cần reconcile/key |
| Connect failure rõ ràng trước khi gửi bytes | Có thể retry | Chỉ retry nếu **chứng minh** request chưa được áp dụng; generic exception không tự đủ |
| Read timeout khi chờ response | Có thể retry GET | Outcome không rõ; có thể đã commit |
| `400/401/403/409/422` | Thường không retry cùng request | Không blind retry |
| Deserialization error | Thường lỗi contract/schema | Không retry vô hạn |
| Cancelled by caller | Dừng pipeline theo lifecycle | Không suy ra đã rollback effect upstream |

Một số APIs cho phép retry `POST` với fixed unique request ID; khi đó policy phải **theo endpoint**, không chỉ theo HTTP method hoặc status code. Nếu không có idempotency hoặc trạng thái có thể tra cứu, lựa chọn an toàn là trả **unknown/pending** và yêu cầu reconciliation thay vì tạo lệnh mới.

## 19. Những điểm cần quan sát trong log và metrics

Nên theo dõi:
- **Event-loop lag** và độ trễ p50/p95/p99 của HTTP client/server.
- Số kết nối Reactor Netty, active/idle/pending acquire và connection timeout.
- Tỷ lệ lỗi 4xx/5xx, phân bố connect timeout vs response timeout vs read timeout.
- Số attempts trên một operation và tỷ lệ retry-exhausted.
- Độ trễ tổng qua initial + backoff + retry; không chỉ latency của attempt cuối.
- Tỷ lệ `Idempotency-Key` replay, key mismatch/conflict, in-flight dedupe và status reconciliation.
- Số records business side effect đã thực thi so với số HTTP attempts.
- Circuit breaker/rate-limit/bulkhead trạng thái khi sử dụng.

**Không dùng raw idempotency key, customer ID, Authorization token làm label Prometheus/Micrometer**: có thể lộ dữ liệu và gây metric cardinality rất cao. Dùng một trace/correlation ID an toàn và route template, kết hợp log có kiểm soát.

### Dấu hiệu blocking

Một số triệu chứng thường gặp:
- Reactor Netty thread xuất hiện trong thread dump đang chờ JDBC, file I/O hoặc `Thread.sleep`.
- Log báo `block() are blocking, which is not supported...`.
- Event-loop latency tăng dù CPU vẫn còn.
- Khi downstream chậm, toàn bộ API cùng trên event loop tăng latency.

Có thể dùng **BlockHound** trong test/dev để phát hiện một số blocking calls trong non-blocking threads, nhưng không khẳng định nó phát hiện mọi thư viện hoặc luôn tương thích với mọi JVM. Event-loop profiling và kiểm thử dưới tải vẫn cần thiết.

## 20. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `IllegalStateException` khi gọi `block()` trong WebFlux | Blocking trên `NonBlocking` event-loop thread | Trả `Mono`/`Flux`, dùng `flatMap`; không block trong handler |
| Không ném exception nhưng latency tăng | `Thread.sleep`, JDBC, blocking SDK trong callback | `Mono.fromCallable(...).subscribeOn(boundedElastic)` hoặc client thật sự reactive |
| API trả 200/202 sớm nhưng HTTP downstream thất bại sau đó | `subscribe()` thủ công, fire-and-forget | Return publisher hoặc queue/outbox có operation ID |
| Mỗi retry tạo một đơn mới | POST không được dedupe | Idempotency key ổn định + server atomic dedupe |
| Đã gửi key nhưng vẫn tạo đơn trùng | Server không lưu key bền, multi-instance hoặc TTL quá ngắn | Shared store, unique constraint/transaction, TTL/reconcile |
| Key giống nhau nhưng body khác | Client sinh payload mới mỗi retry hoặc tái sử dụng key sai | Payload fingerprint, 409, một key cho một operation |
| Retry chưa từng chạy | Lỗi đã được `onErrorResume/onErrorReturn` nuốt trước `retryWhen` | Đặt retry trước fallback, giữ `onError` cho policy |
| Số lần gọi cao hơn dự kiến | `Retry.max(3)` nghĩa là 3 retry + attempt đầu | Đếm attempts và tất cả các tầng retry |
| Một lần call lỗi nhưng server vẫn đã xử lý | Timeout/503 sau commit | Không coi transport failure là rollback; tra operation state |
| Upload body rỗng trong lần retry | Source stream chỉ dùng một lần | Dùng replayable body/source mới mỗi attempt |
| Service bị quá tải khi hồi phục | Mọi client retry cùng lúc | Exponential backoff + jitter, Retry-After, budget |
| Retry 401/403 mãi | Authentication/authorization lỗi | Đổi credentials theo flow đúng, không blind retry |
| Retry 409 làm lặp thao tác | Key conflict/business conflict | Xử lý conflict theo contract, không tự tạo key mới cho cùng operation |
| `block()` trong MVC vẫn chạy nhưng throughput thấp | Đang giữ Servlet thread trong lúc chờ | Chọn RestClient cho sync hoặc thiết kế async với capacity phù hợp |
| Retry ở cuối pipeline làm trừ tiền nhiều lần | `retryWhen` bao cả upstream business side effect | Thu hẹp scope; outbox/reconciliation cho distributed workflow |
| Thấy “2 retries” nhưng không biết thực tế đã retry | Không đo attempt và operation effects | Thêm metric attempt count, retry reason và dedupe hit |
| Downstream bị ảnh hưởng bởi HTTP/2 stream reset | Client không thể biết effect đã commit hay chưa | Dùng idempotency contract/status lookup cho non-idempotent operations |

## 21. Kiểm thử: đừng chỉ nhìn response 200

### Kiểm thử resubscription đơn thuần

Nếu có test dependencies `spring-boot-starter-test` và `io.projectreactor:reactor-test` (fragment Gradle):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Ví dụ **test độc lập** tại `src/test/java/demo/retry/RetrySemanticsTest.java`:

~~~java
package demo.retry;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetrySemanticsTest {

    @Test
    void retriesResubscribeSource() {
        AtomicInteger subscriptions = new AtomicInteger();

        Mono<String> upstream = Mono.defer(() -> {
            if (subscriptions.incrementAndGet() == 1) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        });

        StepVerifier.create(upstream.retryWhen(Retry.max(1)))
                .expectNext("ok")
                .verifyComplete();

        assertEquals(2, subscriptions.get());
    }
}
~~~

Đây là class JUnit 5 chạy được với dependencies phù hợp. Nó chứng minh `retryWhen(Retry.max(1))` làm source được subscribe **hai lần** khi lần đầu lỗi; **không chứng minh HTTP POST an toàn**.

Chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Khi test pass, Gradle báo `BUILD SUCCESSFUL` (chi tiết output phụ thuộc Gradle version). Không nên chỉ assert số request retries mà bỏ kiểm tra side effects ở server.

### Kịch bản integration test cần có

| Kịch bản | Điều cần xác minh |
|---|---|
| GET 503 lần đầu, 200 lần sau | Client trả 200, số attempts tăng đúng policy |
| POST commit rồi trả 503 | Retry cùng key **không tăng** business effect count |
| Cùng key, khác payload | Server từ chối, không tạo effect mới |
| Hai concurrent POST cùng key | Chỉ một operation được claim/commit theo policy |
| Client timeout sau commit | Operation vẫn tra được, không gửi lệnh mới vô điều kiện |
| Server restart giữa attempts | Store bền/unique constraint giữ idempotency |
| Request đến hai replicas | Dedupe hoạt động giữa nodes |
| Idempotency record hết TTL | Client không được coi retry quá muộn là vô hại |
| Body streaming khó replay | Retry policy chặn hoặc tạo mới source hợp lệ |
| POST không có key | Fail fast theo contract cho endpoint quan trọng |
| 429 có Retry-After | Backoff tôn trọng retry delay và overall deadline |
| 400/401/403/409 | Không retry tự động |
| Cancelled subscriber | Không kết luận remote effect đã được rollback |
| Event-loop blocking | Handler không gọi `block()`/JDBC trực tiếp, latency không tăng bất thường |

### Chú ý dùng mock HTTP client

Test từ `StepVerifier` ở trên kiểm tra Reactor mechanics. Với WebClient HTTP thật, dùng **mock HTTP server/WireMock/MockWebServer** hoặc demo local `/server/*` để phát response 503/200 có kiểm soát. Quan trọng phải thử tình huống **server commit rồi response mất**; chỉ mô phỏng 503 trước khi commit sẽ bỏ lỡ bug duplicate payment lớn nhất.

## 22. Khi nào nên dùng RestClient thay vì WebClient?

Trong một ứng dụng **Spring MVC** xử lý request trên Servlet threads, lời gọi HTTP đồng bộ có thể là thiết kế có chủ đích. Khi đó:

~~~java
// Fragment MVC sync; RestClient bean/imports có trong project.
String body = restClient.get()
        .uri("/catalog")
        .retrieve()
        .body(String.class);
~~~

Đây là cách lập trình blocking có chủ ý. Không làm nó non-blocking bằng cách đổi sang WebClient rồi viết `.block()` nếu không có nhu cầu reactive composition. Dù dùng RestClient, **quy tắc retry idempotency vẫn giữ nguyên**: một HTTP client đồng bộ retry POST không an toàn có thể gây trùng như WebClient.

Nếu ứng dụng WebFlux đang gọi phần lớn downstream bằng thư viện chỉ hỗ trợ blocking, cân nhắc kỹ:
- Cô lập blocking SDK qua boundedElastic với giới hạn concurrency.
- Thay thế bằng reactive client ở nơi I/O lớn.
- Tách service/job worker đồng bộ khi đó là biên giới hợp lý.
- Đo tác động memory, thread pool và connection pool thay vì chỉ thay kiểu return của controller.

Không có giải pháp vạn năng “WebFlux nhanh hơn MVC” hoặc “boundedElastic xử lý được vô hạn tasks”.

## 23. Checklist triển khai an toàn cho HTTP client

- [ ] Xác định HTTP caller đang chạy trên WebFlux event loop, Servlet thread, scheduled worker hay background job.
- [ ] Không gọi `block()`/`Thread.sleep`/JDBC trực tiếp trong Reactor event loop.
- [ ] Reactive handler trả publisher; không `subscribe()` thủ công để tạo job không giám sát.
- [ ] Blocking SDK được bọc `fromCallable` và `subscribeOn(boundedElastic)` khi chưa thể thay.
- [ ] Mỗi endpoint outbound được phân loại GET/HEAD/PUT/DELETE vs POST/PATCH theo **semantics thực tế**, không chỉ method name.
- [ ] Retry errors được lọc, số retries và overall deadline có giới hạn.
- [ ] Có backoff + jitter, tôn trọng `Retry-After` khi applicable.
- [ ] Không retry 4xx không recoverable hoặc lỗi schema/credentials vô hạn.
- [ ] Không retry POST/PATCH tự động khi chưa có idempotency contract/reconciliation.
- [ ] Idempotency key được tạo một lần **trước** retry, giữ nguyên cả payload.
- [ ] Server dedupe theo key + fingerprint + tenant/operation scope **atomically** trong store bền.
- [ ] Có xử lý concurrent in-flight requests, TTL, expired key, replay result và key conflict.
- [ ] Không đòi “exactly once” chỉ từ `retryWhen`/Redis lock.
- [ ] Với transaction nhiều hệ thống, đã thiết kế outbox/saga/reconciliation.
- [ ] Request body streaming có khả năng replay hoặc bị loại khỏi retry.
- [ ] Test server đã commit nhưng response 503/timeout; test nhiều replica và restart.
- [ ] Quan sát attempts, dedupe hits, operation outcomes, event-loop lag và pool saturation.
- [ ] Không log raw token, idempotency key nhạy cảm hay PII ở metric labels.

## 24. Câu hỏi tự kiểm tra

**1.** WebFlux controller có thể gọi `WebClient.bodyToMono(...).block()` để “lấy giá trị cho dễ” không?

**Đáp án:** Không nên. Nó có thể chặn hoặc gây `IllegalStateException` trên non-blocking event-loop thread. Trả `Mono`/`Flux` và compose bằng `map`/`flatMap`.

**2.** `Mono.fromCallable(legacyCall).subscribeOn(Schedulers.boundedElastic())` có làm legacy I/O thành non-blocking không?

**Đáp án:** Không. Nó chuyển công việc blocking sang pool phù hợp, giảm tác động lên event loop. I/O vẫn block một worker và chịu giới hạn pool/queue.

**3.** `Retry.backoff(2, ...)` là tối đa hai lần gọi HTTP phải không?

**Đáp án:** Không. Tối đa hai **retries**, cộng attempt đầu ⇒ tối đa ba attempts khi nguồn liên tục lỗi phù hợp.

**4.** Request POST có HTTP 503 nghĩa là server chưa tạo đơn hàng phải không?

**Đáp án:** Không. Server có thể đã commit rồi mới trả 503 hoặc gateway bị lỗi trên đường phản hồi. Kết quả phía client là chưa xác định.

**5.** Có phải mọi POST không bao giờ được retry?

**Đáp án:** Không. Có thể retry khi hợp đồng endpoint đảm bảo idempotency, hoặc có bằng chứng request chưa được áp dụng. Không được **tự động** retry mù khi không có bảo đảm.

**6.** `PUT`/`DELETE` idempotent có nghĩa response HTTP của hai lần gọi phải giống nhau?

**Đáp án:** Không. Idempotent nói về intended effect, không đòi status/body giống hệt; DELETE lần đầu 204, lần sau 404 vẫn có thể thỏa semantics.

**7.** Client sinh UUID mới ở mỗi retry cho `Idempotency-Key` có tốt không?

**Đáp án:** Không. Cần một key cho **một operation**, giữ nguyên qua attempts. Key mới làm server coi là operation khác.

**8.** Chỉ thêm `Idempotency-Key` vào header có bảo đảm exactly once không?

**Đáp án:** Không. Server cần atomic dedupe, durable store, payload fingerprint, scope và recovery; các tác động ngoài DB có thể cần outbox/saga/reconciliation.

**9.** `retryWhen` sau cả `debitWallet().then(notifyPartner())` có thể làm gì?

**Đáp án:** Retry resubscribe vào toàn bộ upstream, có thể lặp `debitWallet` nếu đó là cold publisher có side effect. Phải thu hẹp retry scope và thiết kế transaction phù hợp.

**10.** Vì sao `Retry.backoff` không tự tuân thủ `Retry-After` của 429?

**Đáp án:** Strategy chỉ biết exception và backoff config; nó không tự parse header HTTP của mọi downstream response. Ứng dụng cần logic/adapter phù hợp và budget.

**11.** Cùng một key nhưng payload khác thì server phải làm gì?

**Đáp án:** Không áp dụng payload mới như cùng operation. Từ chối theo contract, demo trả 409 Conflict.

**12.** Tại sao sau khi WebClient timeout lại nên tra cứu trạng thái order?

**Đáp án:** Vì request có thể đã commit. Lookup/reconciliation giúp xác định effect trước khi phát một operation mới.

## 25. Nguồn tham khảo chính thức

- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
- [Project Reactor — Retry and Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — RetryBackoffSpec JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework — WebClient retrieve() and onStatus](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework — WebClient configuration / Reactor Netty resources](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html)
- [RFC 9110 `9.2.2 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)
- [RFC 9110 — Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#field.retry-after)
- [IETF HTTPAPI — Idempotency-Key Header (Internet-Draft, kiểm tra trạng thái bản mới nhất)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)

**Điểm cốt lõi:** `WebClient` non-blocking chỉ mang lại lợi ích khi bạn **không chặn event loop** và **không tự tách subscription không kiểm soát**. `retryWhen` là cơ chế chạy lại publisher khi lỗi, **không phải** bảo đảm một tác động nghiệp vụ duy nhất. Đặc biệt với POST/PATCH, hãy đòi **hợp đồng idempotency thật ở server, key ổn định, durable atomic dedupe và status reconciliation**, rồi mới bật retry có giới hạn.
