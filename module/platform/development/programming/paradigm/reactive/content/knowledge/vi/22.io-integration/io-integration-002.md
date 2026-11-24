# HTTP client phản ứng và quản lý tài nguyên kết nối

Trong **REACTIVE_PROGRAMMING**, pipeline `Mono` và `Flux` kết nối các bước xử lý bất đồng bộ bằng hợp đồng `Publisher–Subscriber`, demand và cancellation. Khi ứng dụng gọi dịch vụ HTTP, một HTTP client phản ứng cho phép request, response body và lỗi tham gia trực tiếp vào pipeline. Trong hệ sinh thái Spring WebFlux, `WebClient` thường kết hợp với Reactor Netty để thực hiện I/O non-blocking và quản lý connection pool.

Một HTTP client reactive cần được cấu hình và sử dụng đúng vòng đời: tái sử dụng client và pool, giới hạn số kết nối và request chờ, đặt timeout ở đúng tầng, tiêu thụ hoặc giải phóng response body, và xử lý cancellation khi downstream không còn cần dữ liệu. Những quyết định này ảnh hưởng trực tiếp đến throughput, độ trễ và khả năng phục hồi của ứng dụng.

## 1. HTTP request là một phần của pipeline reactive

`WebClient` cung cấp API fluent để mô tả request. Các phương thức như `retrieve()` và `exchangeToMono()` trả về Publisher; request thường được thực thi khi có subscription.

```java
Mono<User> user = webClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .bodyToMono(User.class);
```

`bodyToMono(User.class)` giải mã response body thành tối đa một `User`. Với response có nhiều phần tử hoặc nội dung dạng stream, có thể dùng `bodyToFlux`:

```java
Flux<PriceUpdate> updates = webClient.get()
    .uri("/prices/stream")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(PriceUpdate.class);
```

Trong ví dụ thứ hai, downstream tiêu thụ từng `PriceUpdate` khi phần tử được phát. Nếu subscriber hủy hoặc giảm demand, cancellation và backpressure có thể truyền qua pipeline đến client theo khả năng của transport và nguồn response.

Không cần gọi `.subscribe()` bên trong một controller hoặc service chỉ để bắt đầu request. Hãy trả `Mono` hoặc `Flux` cho thành phần gọi để subscription, lỗi và cancellation được quản lý trong cùng luồng xử lý.

## 2. Tạo và tái sử dụng WebClient

`WebClient` được thiết kế để tái sử dụng. Không tạo một client mới cho từng request nếu không có lý do cấu hình riêng, vì việc đó có thể làm mất lợi ích của connection pooling và tạo nhiều tài nguyên mạng.

```java
@Configuration
class HttpClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        return WebClient.builder()
            .baseUrl("https://partner.example")
            .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}
```

Khi dùng connector mặc định của Spring WebFlux, ứng dụng có thể để framework quản lý tài nguyên client. Nếu cần cấu hình sâu connection pool và timeout của Reactor Netty, hãy tạo một `ConnectionProvider` có chủ đích và gắn nó vào `HttpClient`.

## 3. Cấu hình connection pool có giới hạn

Mở kết nối TCP mới cho mọi HTTP request thường tốn thời gian và tài nguyên. Connection pool cho phép tái sử dụng các kết nối còn hợp lệ. Tuy nhiên, pool cần giới hạn rõ ràng để số kết nối và số request chờ không tăng vô hạn.

```java
ConnectionProvider connectionProvider = ConnectionProvider.builder("partner-pool")
    .maxConnections(100)
    .pendingAcquireMaxCount(200)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(30))
    .maxLifeTime(Duration.ofMinutes(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();

HttpClient httpClient = HttpClient.create(connectionProvider)
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
    .responseTimeout(Duration.ofSeconds(5));

WebClient partnerClient = WebClient.builder()
    .baseUrl("https://partner.example")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
```

Các cấu hình chính:

| Thuộc tính | Ý nghĩa | Điều cần cân nhắc |
|---|---|---|
| `maxConnections` | Số kết nối tối đa trong pool | Phù hợp với quota và năng lực dịch vụ đích |
| `pendingAcquireMaxCount` | Số yêu cầu tối đa được xếp hàng chờ lấy connection | Giới hạn lượng request chờ trong bộ nhớ |
| `pendingAcquireTimeout` | Thời gian tối đa chờ lấy connection từ pool | Tránh request chờ vô hạn khi pool bận |
| `maxIdleTime` | Thời gian connection được phép nhàn rỗi | Nên phối hợp với idle timeout của server/proxy |
| `maxLifeTime` | Tuổi thọ tối đa của connection | Giúp luân chuyển connection lâu ngày |
| `evictInBackground` | Chu kỳ quét connection cần loại bỏ | Tránh giữ connection idle hoặc quá tuổi lâu hơn cần thiết |

`maxConnections` không phải giới hạn số request tổng thể của toàn ứng dụng. Một HTTP/2 connection có thể multiplex nhiều stream; giới hạn request đồng thời còn phụ thuộc giao thức, server, client và pool. Với HTTP/1.1, số request đồng thời thường gắn chặt hơn với số connection khả dụng.

Khi pool đạt giới hạn, request mới có thể chờ trong pending queue. Nếu queue đầy hoặc chờ quá lâu, thao tác acquire kết thúc bằng lỗi. Đây là cơ chế bảo vệ tài nguyên; ứng dụng cần chuyển lỗi đó thành phản hồi quá tải hoặc xử lý theo chính sách phù hợp.

## 4. Phân biệt các loại timeout

Một request HTTP có nhiều giai đoạn, vì vậy một timeout duy nhất không luôn đủ để chẩn đoán:

1. **Pending acquire timeout:** thời gian chờ lấy connection từ pool.
2. **Connect timeout:** thời gian thiết lập kết nối TCP đến máy chủ.
3. **Response timeout:** giới hạn thời gian giữa các thao tác đọc dữ liệu mạng theo cấu hình Reactor Netty.
4. **Operation timeout:** deadline tổng thể của Publisher ở cấp ứng dụng, có thể bao gồm chờ pool, kết nối, gửi request và đọc body.

Ví dụ:

```java
Mono<User> user = partnerClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .bodyToMono(User.class)
    .timeout(Duration.ofSeconds(8));
```

`timeout` trên Publisher đặt giới hạn tổng thể cho thao tác được bao quanh. Nếu hết thời gian trước khi Publisher phát tín hiệu kết thúc, nó phát lỗi timeout và hủy subscription upstream.

`responseTimeout` của Reactor Netty có ngữ nghĩa ở tầng đọc response; nó không thay thế deadline tổng thể. Một response streaming có thể tiếp tục hoạt động nếu vẫn nhận dữ liệu trong giới hạn khoảng cách giữa các lần đọc, dù tổng thời gian stream dài hơn nhiều. Nếu nghiệp vụ yêu cầu giới hạn toàn bộ phiên stream, cần đặt deadline hoặc điều kiện dừng riêng.

Không nên đặt mọi timeout cùng một giá trị mà không xem xét ngân sách thời gian. Ví dụ, nếu pending acquire đã dùng gần hết deadline tổng thể, request không còn nhiều thời gian để kết nối và đọc response. Hãy phân bổ timeout theo latency mục tiêu và đo phân vị cao trong vận hành.

## 5. Xử lý HTTP status và response body

Với `retrieve()`, các status 4xx và 5xx mặc định được chuyển thành `WebClientResponseException`. Có thể thay đổi cách ánh xạ lỗi bằng `onStatus`:

```java
Mono<User> user = partnerClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .onStatus(HttpStatusCode::is4xxClientError, response ->
        response.bodyToMono(PartnerError.class)
            .defaultIfEmpty(new PartnerError("Client request rejected"))
            .map(body -> new PartnerClientException(
                response.statusCode(), body.message()
            ))
    )
    .onStatus(HttpStatusCode::is5xxServerError, response ->
        response.bodyToMono(PartnerError.class)
            .defaultIfEmpty(new PartnerError("Partner service failed"))
            .map(body -> new PartnerServerException(
                response.statusCode(), body.message()
            ))
    )
    .bodyToMono(User.class);
```

Các lớp `PartnerError`, `PartnerClientException` và `PartnerServerException` là kiểu dữ liệu/ngoại lệ của ứng dụng. Việc đọc error body trong callback giúp giải mã thông tin lỗi trước khi chuyển thành exception phù hợp.

Nếu cần quyết định phức tạp dựa trên status, header hoặc body, `exchangeToMono()` cho phép xử lý `ClientResponse` trực tiếp:

```java
Mono<User> user = partnerClient.get()
    .uri("/users/{id}", userId)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(User.class);
        }

        return response.bodyToMono(PartnerError.class)
            .defaultIfEmpty(new PartnerError("Unknown partner error"))
            .flatMap(body -> Mono.error(
                new PartnerException(response.statusCode(), body.message())
            ));
    });
```

Khi dùng `exchangeToMono` hoặc `exchangeToFlux`, hãy xử lý body trong callback và trả về Publisher đại diện cho kết quả. Không giữ `ClientResponse` để dùng tùy ý sau khi callback kết thúc. Nếu không cần body, hãy giải phóng/tiêu thụ nó theo API phù hợp; body chưa được xử lý có thể cản trở việc tái sử dụng connection hoặc giữ tài nguyên lâu hơn cần thiết.

## 6. Tiêu thụ response body để giải phóng connection

Connection chỉ có thể được tái sử dụng an toàn khi response body đã được tiêu thụ hoặc được giải phóng theo quy tắc của client và transport. Với `retrieve().bodyToMono(...)` và `bodyToFlux(...)`, Spring WebClient quản lý quá trình đọc body trong Publisher trả về.

Tránh lấy `ClientResponse`, đọc header rồi bỏ body mà không có chính sách cleanup. Ví dụ, nếu chỉ cần status và không cần nội dung:

```java
Mono<HttpStatusCode> status = partnerClient.get()
    .uri("/health")
    .exchangeToMono(response ->
        response.releaseBody()
            .thenReturn(response.statusCode())
    );
```

`releaseBody()` yêu cầu giải phóng body không cần tiêu thụ trước khi trả status xuống downstream. Khi body cần được dùng, hãy chuyển nó thành kiểu dữ liệu bằng `bodyToMono` hoặc `bodyToFlux`.

### DataBuffer và bộ nhớ được quản lý

Trong phần lớn trường hợp, hãy để WebClient giải mã body thành DTO, chuỗi hoặc kiểu domain. Khi làm việc trực tiếp với `DataBuffer`, đặc biệt với pooled buffer, cần tuân thủ ownership và release:

```java
Flux<byte[]> chunks = partnerClient.get()
    .uri("/download")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .map(buffer -> {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes;
        } finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Mapper sao chép dữ liệu sang `byte[]` độc lập rồi giải phóng `DataBuffer`. `doOnDiscard` xử lý buffer bị các operator upstream có hỗ trợ discard loại bỏ, chẳng hạn khi cancellation hoặc khi phần tử bị loại khỏi pipeline. Chỉ đặt hook khi ownership của buffer thuộc pipeline này và bảo đảm không giải phóng cùng buffer hai lần.

Nếu chuyển tiếp `DataBuffer` cho downstream hoặc giữ view tham chiếu đến vùng nhớ gốc, không được release ngay sau khi phát. Khi đó cần chuyển quyền sở hữu hoặc retain/release theo đúng hợp đồng của API đang dùng.

## 7. Streaming response và backpressure

Với dữ liệu lớn hoặc stream liên tục, không nên gom toàn bộ response vào một `Mono<List<T>>` nếu không cần thiết. `bodyToFlux` cho phép xử lý từng phần tử khi chúng đến:

```java
Flux<ServerSentEvent<PriceUpdate>> updates = partnerClient.get()
    .uri("/prices/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<PriceUpdate>>() {});
```

Downstream có thể áp dụng `map`, `filter`, `take`, `timeout` hoặc `onBackpressureBuffer` tùy ngữ nghĩa. Khi subscriber giảm demand hoặc cancel, việc đọc tiếp response có thể được điều tiết hoặc dừng theo giao thức và transport.

Backpressure không tự đảm bảo server ngừng tạo dữ liệu. Với HTTP streaming, client có thể giảm tốc độ đọc socket hoặc hủy request; server và proxy có thể có buffer riêng. Nếu nguồn bên ngoài không thể giảm tốc, cần giới hạn buffer, chọn drop/latest nếu nghiệp vụ cho phép hoặc ghi dữ liệu vào kho bền vững.

## 8. Cancellation và vòng đời kết nối

Cancellation xảy ra khi downstream không còn cần kết quả, ví dụ client đóng kết nối, người dùng hủy thao tác hoặc `take(n)` đã nhận đủ phần tử. Với WebClient, cancellation truyền qua Publisher body đến connector. Reactor Netty sẽ quản lý response và connection theo trạng thái giao thức; connection có thể được trả lại pool nếu đã ở trạng thái an toàn để tái sử dụng, hoặc bị đóng/loại khỏi pool nếu không thể tái sử dụng an toàn.

Không nên tự đóng connection mà WebClient đang quản lý. Ứng dụng làm việc với Publisher body và để connector xử lý lifecycle transport. Nếu ứng dụng tự quản lý resource bên ngoài như file đích, temporary file hoặc transaction, hãy gắn cleanup với `usingWhen`, `doFinally` hoặc cơ chế lifecycle thích hợp.

Ví dụ dừng một stream sau số phần tử cần thiết:

```java
Flux<PriceUpdate> firstHundred = updates.take(100);
```

Sau 100 phần tử, `take(100)` hoàn tất downstream và hủy upstream. Đây là một cách giới hạn phiên đọc; cần bảo đảm nghiệp vụ chấp nhận việc dừng response tại thời điểm đó.

## 9. Retry HTTP an toàn

HTTP request có thể thất bại do lỗi kết nối, timeout hoặc status từ dịch vụ. Retry chỉ phù hợp khi lỗi có khả năng tạm thời và việc gửi lại request an toàn.

```java
Mono<Inventory> inventory = Mono.defer(() ->
        partnerClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class)
    )
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isTransientPartnerFailure)
    );
```

`Mono.defer` tạo request Publisher mới cho mỗi subscription, còn `Retry.backoff` giới hạn số lần thử lại và giãn thời gian giữa các lần. `isTransientPartnerFailure` cần phân biệt lỗi tạm thời với lỗi nghiệp vụ như 400 hoặc 404.

Với `POST`, `PATCH` hoặc thao tác ghi, timeout không chứng minh server chưa thực hiện thay đổi. Nếu response bị mất sau khi server đã ghi thành công, retry có thể tạo giao dịch trùng. Hãy dùng idempotency key, request ID hoặc API có ngữ nghĩa idempotent trước khi tự động retry.

Retry cũng không nên vượt quá deadline tổng thể của request. Nếu pool đang bão hòa hoặc dependency liên tục lỗi, retry dồn dập sẽ tăng tải. Kết hợp backoff, jitter, giới hạn số lần và timeout tổng thể; cân nhắc circuit breaker hoặc trả lỗi quá tải khi dịch vụ không còn khả năng phục vụ.

## 10. Không block trên thread xử lý reactive

`WebClient` thực hiện I/O non-blocking. Hãy giữ kết quả dưới dạng `Mono` hoặc `Flux` thay vì gọi `.block()` trong controller hoặc trong callback chạy trên event loop:

```java
// Reactive: trả Publisher cho framework subscribe.
@GetMapping("/users/{id}")
Mono<User> getUser(@PathVariable String id) {
    return partnerClient.get()
        .uri("/users/{id}", id)
        .retrieve()
        .bodyToMono(User.class);
}
```

Nếu cần tích hợp thư viện blocking cũ sau khi nhận response, bọc riêng lời gọi đó bằng `fromCallable` và chuyển sang `Schedulers.boundedElastic()`. Không chuyển toàn bộ WebClient sang bounded elastic; điều đó làm mất lợi ích non-blocking và có thể tăng số thread không cần thiết.

## 11. Quản lý vòng đời ConnectionProvider

Một `ConnectionProvider` tự tạo là tài nguyên cấp ứng dụng, không phải tài nguyên của từng request. Hãy tạo một lần, chia sẻ với `HttpClient`/`WebClient` tương ứng và dispose khi ứng dụng dừng.

```java
@Configuration
class PartnerHttpConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerConnectionProvider() {
        return ConnectionProvider.builder("partner-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .build();
    }

    @Bean
    WebClient partnerClient(ConnectionProvider partnerConnectionProvider) {
        HttpClient httpClient = HttpClient.create(partnerConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(5));

        return WebClient.builder()
            .baseUrl("https://partner.example")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
```

Spring gọi `dispose()` khi bean bị hủy trong quá trình shutdown. Nếu dùng Reactor Netty global resources hoặc cơ chế quản lý tài nguyên của Spring Boot, hãy để framework quản lý lifecycle theo cấu hình của nó. Tránh vừa để framework dispose global resources vừa tự dispose chúng từ nhiều nơi.

Không gọi `dispose()` sau từng request. Việc đó đóng pool đang được các request khác sử dụng và làm mất khả năng tái sử dụng connection.

## 12. Kiểm thử HTTP client reactive

Nên kiểm thử với HTTP server giả lập như MockWebServer hoặc WireMock để chủ động response, status, delay và việc đóng kết nối. Một test cơ bản với MockWebServer:

```java
MockWebServer server = new MockWebServer();
server.enqueue(new MockResponse()
    .addHeader("Content-Type", "application/json")
    .setBody("{\"id\":\"u-42\",\"name\":\"An\"}"));
server.start();

try {
    WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

    Mono<User> result = client.get()
        .uri("/users/u-42")
        .retrieve()
        .bodyToMono(User.class);

    StepVerifier.create(result)
        .expectNextMatches(user ->
            user.id().equals("u-42") && user.name().equals("An")
        )
        .verifyComplete();

    RecordedRequest request = server.takeRequest();
    assertEquals("GET", request.getMethod());
    assertEquals("/users/u-42", request.getPath());
} finally {
    server.shutdown();
}
```

`User` là DTO của ứng dụng; MockWebServer là dependency test. `StepVerifier` xác minh tín hiệu reactive, còn `RecordedRequest` xác minh HTTP request thực sự được gửi với method và path đúng.

Các tình huống quan trọng nên có test riêng:

- 4xx/5xx và nội dung error body được ánh xạ đúng.
- Response body rỗng hoặc sai định dạng.
- Connect timeout, response timeout và deadline tổng thể.
- Pool hết connection, pending queue đầy hoặc acquire timeout.
- Retry có đúng số lần, chỉ retry lỗi được phép và không retry lỗi nghiệp vụ.
- Cancellation khi đọc streaming body.
- DataBuffer được release khi decode thành công, lỗi hoặc bị discard.
- Connection được tái sử dụng sau khi response body đã được tiêu thụ.
- ConnectionProvider được dispose khi ứng dụng dừng.

Với test liên quan thời gian, có thể dùng `StepVerifier.withVirtualTime` cho các operator Reactor như `timeout` hoặc delay do ứng dụng thêm. Virtual time không thay thế test socket, connection pool hoặc timeout mạng thực; những phần đó cần server giả lập và timeout ngắn, có kiểm soát.

## 13. Theo dõi hiệu năng và sự cố kết nối

Một HTTP client reactive cần metrics ở cả tầng pool lẫn tầng request:

| Chỉ số | Giúp phát hiện |
|---|---|
| Active connections | Số kết nối đang được sử dụng |
| Idle connections | Khả năng tái sử dụng pool và connection nhàn rỗi |
| Pending acquire count | Request đang chờ lấy connection |
| Acquire latency/timeout | Pool bão hòa hoặc connection bị giữ quá lâu |
| Connect latency và connect errors | Sự cố mạng hoặc máy chủ không nhận kết nối |
| Response latency/status | Dịch vụ đích chậm hoặc trả lỗi |
| Response body duration/bytes | Stream kéo dài, body lớn hoặc consumer chậm |
| Retry count | Dependency không ổn định hoặc chính sách retry quá rộng |
| Cancellation count | Caller hủy, timeout hoặc downstream không còn cần dữ liệu |

Nếu active connections luôn đạt max và pending acquire tăng, cần kiểm tra concurrency, thời gian giữ response body và năng lực server. Nếu active thấp nhưng connect errors tăng, nguyên nhân có thể nằm ở DNS, mạng hoặc server. Nếu request hoàn tất header nhưng body đọc rất lâu, cần quan sát riêng thời gian tiêu thụ body.

Không tăng `maxConnections` chỉ dựa trên pending queue. Tăng pool có thể làm server đích quá tải hoặc làm cạn socket ở phía client. Hãy điều chỉnh dựa trên throughput, latency, giới hạn dependency và ngân sách tài nguyên của toàn hệ thống.

## 14. Các lỗi tích hợp thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo WebClient/ConnectionProvider cho từng request | Mất pooling, tăng socket và tài nguyên | Tái sử dụng bean hoặc client cấp ứng dụng |
| Đọc status rồi bỏ response body | Connection khó được tái sử dụng, tài nguyên body còn giữ | Dùng `releaseBody()` hoặc tiêu thụ body |
| Gọi `.block()` trên event loop | Chặn thread xử lý reactive và giảm throughput | Trả `Mono`/`Flux`; chỉ cô lập blocking legacy trên bounded elastic |
| Chỉ đặt response timeout | Pool acquire hoặc connect có thể chờ quá lâu | Đặt timeout riêng cho acquire, connect và deadline tổng thể |
| Retry mọi lỗi HTTP | Lặp lại 4xx hoặc thao tác ghi không an toàn | Lọc lỗi tạm thời, giới hạn retry và dùng idempotency key |
| Tăng connection pool vô hạn | Tạo áp lực lên client và server | Đặt max connection, pending limit và timeout |
| Quên release pooled DataBuffer | Rò rỉ bộ nhớ native | Dùng API decode hoặc release theo ownership và discard path |
| Dispose pool sau mỗi request | Làm gián đoạn request khác và mất connection reuse | Dispose đúng lifecycle ứng dụng |

## 15. Checklist trước khi đưa HTTP client vào vận hành

1. WebClient và ConnectionProvider có được tái sử dụng thay vì tạo theo request không?
2. Pool có giới hạn connection và pending acquire không?
3. Pending acquire, connect, response và operation timeout có được phân biệt không?
4. Response body có luôn được tiêu thụ hoặc release không?
5. DataBuffer hoặc pooled payload có ownership và cleanup rõ ràng không?
6. Streaming body có được tiêu thụ theo nhu cầu và có điều kiện cancellation không?
7. Retry có lọc lỗi, giới hạn số lần, backoff/jitter và bảo đảm idempotency không?
8. Không có `.block()` trên event loop hoặc trong pipeline reactive chính?
9. ConnectionProvider tự tạo có lifecycle dispose rõ ràng không?
10. Test có bao phủ status, timeout, pool saturation, cancellation và connection reuse không?

HTTP client phản ứng đưa request, response body, lỗi và cancellation vào cùng pipeline `Mono`/`Flux`. Để sử dụng an toàn, hãy tái sử dụng client và connection pool có giới hạn, đặt timeout ở đúng tầng, tiêu thụ hoặc giải phóng body, quản lý pooled buffer theo ownership và dispose tài nguyên ở lifecycle ứng dụng. Kết hợp kiểm thử HTTP giả lập với metrics pool và request giúp phát hiện sớm tình trạng chờ kết nối, rò rỉ tài nguyên và quá tải dependency.
