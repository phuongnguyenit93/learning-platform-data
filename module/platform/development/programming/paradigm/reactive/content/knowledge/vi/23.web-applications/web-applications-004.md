# WebClient: gửi yêu cầu, đọc phản hồi và xử lý lỗi

Trong một ứng dụng Spring WebFlux, việc gọi dịch vụ HTTP bên ngoài thường là một phần của pipeline reactive. Một yêu cầu có thể cần đọc dữ liệu từ nhiều dịch vụ, kết hợp kết quả, áp dụng timeout, thử lại khi gặp lỗi tạm thời rồi trả dữ liệu cho client. Nếu lời gọi HTTP chặn thread đang xử lý request, khả năng mở rộng của ứng dụng reactive sẽ bị giảm.

WebClient là HTTP client reactive của Spring WebFlux. Nó xây dựng trên một connector bất đồng bộ và trả về Mono hoặc Flux, vì vậy có thể kết hợp trực tiếp với các operator Reactor. Ta có thể mô tả cách gửi request, giải mã response, ánh xạ status lỗi, giới hạn thời gian và hủy công việc trong cùng một pipeline.

Bài học này tập trung vào vòng đời một HTTP exchange: cấu hình client, tạo request, gửi body, đọc response, xử lý status và lỗi truyền tải, rồi kiểm thử hành vi bằng StepVerifier. Các ví dụ dùng Spring Framework 6 / Spring Boot 3 và Java hiện đại.

## 1. WebClient nằm ở đâu trong pipeline reactive?

Một lời gọi WebClient không trả về dữ liệu ngay tại thời điểm tạo biểu thức. Nó trả về publisher mô tả kết quả sẽ được nhận khi có subscription. Ví dụ:

    Mono<Product> product =
        webClient.get()
            .uri("/products/{id}", productId)
            .retrieve()
            .bodyToMono(Product.class);

Biểu thức trên mô tả một GET request và cách giải mã body thành Product. Khi pipeline được subscribe, WebClient mới thực hiện HTTP exchange theo connector đã cấu hình.

WebClient phù hợp khi:

- Ứng dụng cần gọi HTTP từ một pipeline reactive.
- Cần ghép nhiều lời gọi mạng bằng zip, flatMap hoặc các operator khác.
- Muốn quản lý timeout, retry, cancellation và lỗi trong cùng chuỗi.
- Cần đọc dữ liệu dạng stream mà không gom toàn bộ response vào bộ nhớ.
- Muốn chia sẻ cấu hình, filter và connection resources giữa nhiều request.

WebClient không tự làm một API blocking trở thành non-blocking. Khả năng non-blocking phụ thuộc connector và cách thư viện được sử dụng. Tránh gọi block() trong event loop hoặc trong controller reactive; việc đó làm mất lợi ích của pipeline bất đồng bộ.

## 2. Dependency và tạo WebClient

Trong ứng dụng Spring Boot WebFlux, starter thường đã đưa WebClient và Reactor vào classpath:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

Nếu ứng dụng chỉ cần HTTP client mà không dùng auto-configuration của Spring Boot, có thể khai báo spring-webflux cùng các dependency connector phù hợp. Nên để Spring Boot dependency management hoặc BOM quản lý version tương thích giữa Spring Framework và Reactor.

Tạo client đơn giản:

    WebClient client = WebClient.create("https://catalog.example");

Hoặc dùng builder:

    WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example")
        .defaultHeader(
            HttpHeaders.ACCEPT,
            MediaType.APPLICATION_JSON_VALUE
        )
        .build();

Builder phù hợp khi cần cấu hình headers mặc định, filters, codecs hoặc connector. Trong ứng dụng Spring, thường khai báo một bean dùng chung:

    @Configuration
    class HttpClientConfiguration {

        @Bean
        WebClient catalogWebClient(WebClient.Builder builder) {
            return builder
                .baseUrl("https://catalog.example")
                .defaultHeader(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE
                )
                .build();
        }
    }

Spring Boot có thể cung cấp WebClient.Builder đã được cấu hình sẵn. Tạo bean client từ builder giúp giữ các customizer và cấu hình chung của ứng dụng. Không cần tạo một WebClient mới cho mỗi request; WebClient là immutable sau khi build và có thể dùng lại.

## 3. Cấu hình base URL, headers và URI

baseUrl đặt gốc cho các URI tương đối. Mỗi request có thể thêm path và biến:

    Mono<Product> findProduct(String productId) {
        return catalogWebClient.get()
            .uri("/products/{id}", productId)
            .retrieve()
            .bodyToMono(Product.class);
    }

Với query parameter, dùng uriBuilder để encode giá trị đúng cách:

    Flux<Product> search(String keyword, int page) {
        return catalogWebClient.get()
            .uri(builder -> builder
                .path("/products")
                .queryParam("q", keyword)
                .queryParam("page", page)
                .build())
            .retrieve()
            .bodyToFlux(Product.class);
    }

Tránh nối chuỗi URI bằng tay từ dữ liệu người dùng. URI builder giúp encode các ký tự đặc biệt và làm rõ path với query parameter.

Headers có thể đặt ở cấp client hoặc từng request:

    Mono<Product> findPrivateProduct(
        String productId,
        String accessToken
    ) {
        return catalogWebClient.get()
            .uri("/products/{id}", productId)
            .headers(headers ->
                headers.setBearerAuth(accessToken)
            )
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(Product.class);
    }

Không đặt token người dùng hoặc dữ liệu nhạy cảm vào default header của một WebClient dùng chung nếu mỗi request có danh tính khác nhau. Hãy truyền thông tin xác thực theo request hoặc qua cơ chế security context đã được cấu hình rõ ràng.

## 4. Gửi request có body

Với POST hoặc PUT, bodyValue nhận một đối tượng để codec chuyển thành body, thường là JSON khi Jackson có mặt:

    record CreateProductRequest(
        String name,
        long priceCents
    ) {}

    record Product(
        String id,
        String name,
        long priceCents
    ) {}

    Mono<Product> createProduct(CreateProductRequest command) {
        return catalogWebClient.post()
            .uri("/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(command)
            .retrieve()
            .bodyToMono(Product.class);
    }

Nếu body là một publisher, dùng body để gửi dữ liệu theo luồng:

    Flux<UploadReceipt> uploadEvents(
        Flux<UploadChunk> chunks
    ) {
        return catalogWebClient.post()
            .uri("/uploads/stream")
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(chunks, UploadChunk.class)
            .retrieve()
            .bodyToFlux(UploadReceipt.class);
    }

Định dạng body phải phù hợp với hợp đồng server. application/json thường biểu diễn một document; application/x-ndjson biểu diễn các JSON document phân tách theo dòng. Đừng chọn media type chỉ vì nguồn đầu vào là Flux.

Nếu gửi một publisher lớn, connector và codec có thể truyền dữ liệu theo luồng. Cần xác nhận server hỗ trợ streaming và định dạng tương ứng; nếu server yêu cầu một JSON array hoàn chỉnh, việc gửi NDJSON sẽ không tương thích.

## 5. Đọc response bằng retrieve

retrieve() là cách ngắn gọn để lấy body khi xử lý status mặc định là đủ. Dùng bodyToMono cho response có tối đa một body object:

    Mono<Product> product =
        catalogWebClient.get()
            .uri("/products/{id}", productId)
            .retrieve()
            .bodyToMono(Product.class);

Dùng bodyToFlux khi response là một chuỗi phần tử:

    Flux<Product> products =
        catalogWebClient.get()
            .uri("/products")
            .retrieve()
            .bodyToFlux(Product.class);

Nếu endpoint không trả body, có thể nhận một Mono<Void>:

    Mono<Void> deleteProduct(String id) {
        return catalogWebClient.delete()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Void.class);
    }

Hoặc dùng toBodilessEntity() khi cần xác nhận status và headers mà không giải mã body:

    Mono<ResponseEntity<Void>> deleteProduct(String id) {
        return catalogWebClient.delete()
            .uri("/products/{id}", id)
            .retrieve()
            .toBodilessEntity();
    }

Nếu cần status, headers và body đã giải mã, dùng toEntity:

    Mono<ResponseEntity<Product>> createProduct(
        CreateProductRequest command
    ) {
        return catalogWebClient.post()
            .uri("/products")
            .bodyValue(command)
            .retrieve()
            .toEntity(Product.class);
    }

retrieve() mặc định chuyển response có status 4xx hoặc 5xx thành WebClientResponseException. Các status thành công tiếp tục tới bước giải mã body. Có thể tùy chỉnh hành vi status bằng onStatus.

## 6. Ánh xạ status lỗi bằng onStatus

Một API thường trả error body có cấu trúc riêng. Ta có thể đọc body và chuyển thành exception domain:

    record ApiError(
        String code,
        String message
    ) {}

    final class CatalogApiException extends RuntimeException {
        private final HttpStatusCode status;
        private final String errorCode;

        CatalogApiException(
            HttpStatusCode status,
            String errorCode,
            String message
        ) {
            super(message);
            this.status = status;
            this.errorCode = errorCode;
        }

        HttpStatusCode status() {
            return status;
        }

        String errorCode() {
            return errorCode;
        }
    }

    Mono<Product> findProduct(String id) {
        return catalogWebClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .onStatus(
                HttpStatusCode::is4xxClientError,
                response -> response.bodyToMono(ApiError.class)
                    .defaultIfEmpty(
                        new ApiError(
                            "UNKNOWN_CLIENT_ERROR",
                            "Yêu cầu không hợp lệ"
                        )
                    )
                    .map(error -> new CatalogApiException(
                        response.statusCode(),
                        error.code(),
                        error.message()
                    ))
            )
            .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> response.bodyToMono(ApiError.class)
                    .defaultIfEmpty(
                        new ApiError(
                            "CATALOG_UNAVAILABLE",
                            "Dịch vụ catalog đang gặp lỗi"
                        )
                    )
                    .map(error -> new CatalogApiException(
                        response.statusCode(),
                        error.code(),
                        error.message()
                    ))
            )
            .bodyToMono(Product.class);
    }

Handler của onStatus phải trả về Mono phát ra một Throwable. Khi handler phát exception, pipeline kết thúc bằng onError. Trong ví dụ, body lỗi được đọc và chuyển thành CatalogApiException để tầng nghiệp vụ không phụ thuộc trực tiếp vào schema lỗi thô của dịch vụ bên ngoài.

Nếu muốn giữ exception mặc định, không cần thêm onStatus. Nếu handler trả Mono.empty(), status đó được xem như không kích hoạt xử lý lỗi tùy chỉnh và response tiếp tục qua bước giải mã body. Điều này không tự biến response thành empty; hãy chỉ dùng khi đó thực sự là semantics mong muốn.

Response body là stream một lần. Khi đã đọc body trong onStatus, không thể tiếp tục giải mã cùng body lần thứ hai như thể nó chưa bị tiêu thụ.

## 7. Dùng exchangeToMono khi cần kiểm soát response chi tiết

retrieve() phù hợp với luồng xử lý status phổ biến. Khi cách xử lý phụ thuộc nhiều vào status, headers hoặc body, dùng exchangeToMono:

    Mono<Product> findProductOrEmpty(String id) {
        return catalogWebClient.get()
            .uri("/products/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class);
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                        .then(Mono.empty());
                }

                return response.createException()
                    .flatMap(error -> Mono.error(error));
            });
    }

Trong ví dụ:

- 2xx giải mã body thành Product.
- 404 giải phóng body rồi trả Mono rỗng.
- Các status khác được chuyển thành WebClientResponseException.

exchangeToMono trao cho callback quyền quyết định cách xử lý ClientResponse. Hãy tiêu thụ body hoặc chủ động giải phóng nó trong nhánh tương ứng. Sau khi publisher do callback trả về kết thúc, WebClient sẽ giải phóng body chưa được tiêu thụ theo lifecycle của exchange; không giữ ClientResponse để đọc body ở một thời điểm tùy ý sau đó.

Nếu kết quả là nhiều phần tử, có thể dùng exchangeToFlux. Chọn API theo cardinality của body và bảo đảm mọi nhánh đều xử lý tài nguyên response đúng cách.

## 8. Phân biệt lỗi HTTP với lỗi truyền tải

Một lời gọi WebClient có thể thất bại ở nhiều tầng:

| Nhóm lỗi | Ví dụ | Cách quan sát thường gặp |
|---|---|---|
| HTTP status | Server trả 404, 429 hoặc 503 | WebClientResponseException hoặc exception do onStatus tạo |
| Kết nối | DNS lỗi, connection refused, TLS handshake thất bại | Exception từ connector |
| Timeout | Không nhận response trong deadline | TimeoutException từ operator hoặc timeout của connector |
| Giải mã | JSON không khớp DTO hoặc body sai định dạng | Codec/decoding exception |
| Hủy | Downstream cancel hoặc dispose | Cancellation, không phải lỗi nghiệp vụ thông thường |
| Lỗi ứng dụng | Mapper hoặc callback ném exception | onError từ pipeline |

Không nên gom tất cả thành “dịch vụ trả lỗi”. Ví dụ, 404 có thể là kết quả nghiệp vụ hợp lệ, 503 có thể thử lại, còn lỗi giải mã thường cần sửa hợp đồng dữ liệu hoặc schema. Phân loại đúng giúp chọn chính sách retry và fallback an toàn.

## 9. Xử lý lỗi ở tầng nghiệp vụ

Sau khi WebClient chuyển lỗi thành onError, các operator Reactor có thể xử lý:

onErrorMap đổi loại exception nhưng vẫn kết thúc bằng lỗi:

    Mono<Product> product =
        findProduct(id)
            .onErrorMap(
                WebClientResponseException.class,
                error -> new CatalogUnavailableException(
                    "Không thể truy cập catalog",
                    error
                )
            );

onErrorResume chuyển sang publisher dự phòng:

    Mono<Product> product =
        findProduct(id)
            .onErrorResume(
                CatalogUnavailableException.class,
                error -> productCache.find(id)
            );

doOnError quan sát lỗi để ghi log hoặc metric, nhưng không phục hồi:

    Mono<Product> product =
        findProduct(id)
            .doOnError(error ->
                metrics.incrementCatalogFailures()
            );

Không chuyển mọi lỗi thành Mono.empty() chỉ để tránh response lỗi. Điều đó có thể làm tầng gọi nhầm lẫn giữa “không tồn tại” và “dịch vụ không thể truy cập”. Nếu endpoint quy định 404 là không có dữ liệu, ánh xạ riêng 404 bằng exchangeToMono hoặc exception domain cụ thể.

## 10. Timeout và retry

Timeout đặt deadline cho publisher:

    Mono<Product> product =
        findProduct(id)
            .timeout(Duration.ofSeconds(2));

Khi không có tín hiệu phù hợp trước thời hạn, timeout phát lỗi timeout và hủy upstream subscription. Việc connector có đóng request hoặc kết nối bên dưới hay không phụ thuộc implementation. Timeout ở tầng Reactor không bảo đảm server từ xa đã ngừng xử lý request.

Retry chỉ nên áp dụng cho lỗi có khả năng tạm thời:

    Mono<Product> product =
        findProduct(id)
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                    .filter(error ->
                        error instanceof WebClientResponseException response
                            && response.getStatusCode()
                                .is5xxServerError()
                    )
            );

Ví dụ chỉ thử lại lỗi HTTP 5xx, tối đa ba lần với backoff. Trong production, cần cân nhắc thêm:

- 429 và Retry-After nếu API có quy định giới hạn tốc độ.
- Deadline tổng của request để retry không kéo dài vô hạn.
- Jitter để nhiều client không retry cùng một thời điểm.
- Circuit breaker hoặc bulkhead nếu hệ thống cần bảo vệ trước dịch vụ lỗi kéo dài.
- Idempotency của thao tác trước khi retry POST, thanh toán hoặc side effect khác.

Retry tạo subscription mới cho nguồn. Nếu request đã được server xử lý nhưng response bị mất, gửi lại có thể lặp side effect. Chỉ retry thao tác không gây hại khi lặp hoặc có idempotency key được server hỗ trợ.

## 11. Đọc response dạng stream và kiểm soát bộ nhớ

bodyToFlux cho phép xử lý từng phần tử khi response là stream:

    Flux<ServerSentEvent<PriceUpdate>> prices =
        webClient.get()
            .uri("/prices/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(
                new ParameterizedTypeReference<
                    ServerSentEvent<PriceUpdate>
                >() {}
            );

Không gọi collectList() trên một stream vô hạn. Thao tác đó chờ nguồn hoàn tất và giữ toàn bộ phần tử trong bộ nhớ. Với stream liên tục, xử lý từng phần tử, giới hạn buffer và xác định chiến lược khi downstream chậm.

Reactive Streams có backpressure ở ranh giới publisher/subscriber. Tuy nhiên, HTTP server bên ngoài có thể không hỗ trợ tạm dừng phát dữ liệu theo nhu cầu của ứng dụng. Connector, codec và protocol có thể buffer một lượng dữ liệu; cần cấu hình và kiểm thử theo tải thực tế.

Nếu chỉ cần trạng thái mới nhất, có thể áp dụng onBackpressureLatest ở một ranh giới phù hợp. Nếu mọi phần tử đều quan trọng, không drop tùy tiện; hãy dùng buffer có giới hạn, cơ chế ghi bền vững hoặc broker có khả năng lưu giữ dữ liệu.

## 12. Cấu hình codec và giới hạn body

WebClient dùng codec để chuyển đổi body. Khi ứng dụng xử lý payload lớn, cần cân nhắc giới hạn bộ nhớ của codec:

    WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example")
        .codecs(configurer ->
            configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024)
        )
        .build();

Giá trị trên đặt giới hạn 2 MiB cho dữ liệu được codec gom trong bộ nhớ ở những trường hợp áp dụng. Tăng giới hạn không phải cách thay thế cho streaming; payload rất lớn nên được đọc theo luồng hoặc xử lý theo từng phần.

Khi nhận lỗi DataBufferLimitException, hãy xem response có bị gom toàn bộ vào memory không, codec nào đang đọc body và server có thể cung cấp pagination hoặc streaming hay không. Đừng tăng giới hạn vô hạn để che giấu một response không được kiểm soát.

## 13. Filter cho logging, authentication và correlation

ExchangeFilterFunction cho phép can thiệp request/response ở cấp client. Có thể dùng filter để gắn header chung, ghi metric hoặc truyền correlation ID:

    ExchangeFilterFunction correlationFilter =
        (request, next) ->
            Mono.deferContextual(context -> {
                ClientRequest outgoing =
                    ClientRequest.from(request)
                        .headers(headers -> {
                            if (context.hasKey("correlationId")) {
                                headers.set(
                                    "X-Correlation-ID",
                                    context.get("correlationId")
                                );
                            }
                        })
                        .build();

                return next.exchange(outgoing);
            });

    WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example")
        .filter(correlationFilter)
        .build();

Gắn Context cho một request:

    Mono<Product> product =
        client.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .contextWrite(context ->
                context.put("correlationId", "req-42")
            );

Filter được chạy trong chuỗi reactive của request và có thể đọc Reactor Context. Không giả định ThreadLocal hoặc MDC tự động có mặt trên mọi thread của connector. Nếu cần context propagation, cấu hình theo hướng dẫn của phiên bản Spring/Reactor đang dùng.

Logging request/response cần tránh ghi token, cookie, thông tin cá nhân hoặc toàn bộ body nhạy cảm. Trong production, ưu tiên log method, URI đã loại query nhạy cảm, status, thời gian, trace ID và kích thước payload.

## 14. Kiểm thử WebClient với MockWebServer và StepVerifier

Kiểm thử adapter HTTP nên xác nhận cả dữ liệu lẫn request thực sự được gửi. Có thể dùng OkHttp MockWebServer làm server giả. Ví dụ dependency test:

    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>

Ví dụ kiểm thử GET:

    @Test
    void readsProductFromHttpResponse() throws Exception {
        MockWebServer server = new MockWebServer();
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader(
                "Content-Type",
                "application/json"
            )
            .setBody("""
                {
                  "id": "p-7",
                  "name": "Keyboard",
                  "priceCents": 4500
                }
                """));
        server.start();

        try {
            WebClient client = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

            Mono<Product> result = client.get()
                .uri("/products/{id}", "p-7")
                .retrieve()
                .bodyToMono(Product.class);

            StepVerifier.create(result)
                .expectNextMatches(product ->
                    product.id().equals("p-7")
                        && product.name().equals("Keyboard")
                        && product.priceCents() == 4500
                )
                .verifyComplete();

            RecordedRequest request = server.takeRequest();
            assertEquals("GET", request.getMethod());
            assertEquals("/products/p-7", request.getPath());
        } finally {
            server.shutdown();
        }
    }

Đoạn mã giả định Product là record có ba field như JSON, cùng các import JUnit, MockWebServer và Reactor Test. MockWebServer kiểm tra request ở ranh giới HTTP; StepVerifier kiểm tra tín hiệu của publisher.

Kiểm thử status lỗi cũng cần xác nhận loại exception hoặc exception domain:

    server.enqueue(new MockResponse()
        .setResponseCode(503)
        .addHeader("Content-Type", "text/plain")
        .setBody("maintenance"));

    Mono<Product> result = client.get()
        .uri("/products/p-7")
        .retrieve()
        .bodyToMono(Product.class);

    StepVerifier.create(result)
        .expectError(WebClientResponseException.class)
        .verify();

Ngoài ra, nên có test cho 404, 429, 5xx, body rỗng, JSON sai định dạng, timeout, retry và cancellation. Dùng publisher điều khiển được hoặc server giả có độ trễ để kiểm tra thời gian; tránh dựa vào dịch vụ mạng thật trong unit test.

## 15. Những lỗi thường gặp khi dùng WebClient

Gọi block trong luồng WebFlux. block() chờ đồng bộ và có thể chặn event loop. Hãy trả Mono hoặc Flux cho framework điều phối.

Dùng bodyToMono cho response nhiều phần tử. Nếu endpoint trả stream, dùng bodyToFlux; nếu gom danh sách, xác nhận nguồn hữu hạn và kích thước có giới hạn.

Đọc response body hai lần. Body là stream một lần. Nếu onStatus đã đọc body lỗi, không thể giải mã lại nó ở bước sau.

Chỉ xử lý status mà bỏ qua lỗi kết nối. DNS, TLS, connection reset, timeout và decoding failure không phải HTTP status. Cần phân loại riêng.

Retry mọi exception. Retry lỗi validation, 404 hoặc lỗi lập trình không giúp ích và có thể tăng tải. Chỉ retry lỗi tạm thời và thao tác an toàn khi lặp.

Cho rằng timeout đã dừng server. Timeout hủy subscription ở client; server từ xa có thể vẫn tiếp tục side effect.

Nối URI từ dữ liệu không tin cậy. Dùng URI builder để encode path và query parameter đúng cách.

Tạo WebClient mới cho mỗi request. Dùng client được cấu hình và tái sử dụng để chia sẻ connection resources, filter và codec configuration.

Ghi toàn bộ body vào log. Điều đó có thể làm lộ token, dữ liệu cá nhân và thông tin nghiệp vụ nhạy cảm.

Tăng maxInMemorySize vô hạn. Xác định kích thước payload, dùng streaming hoặc pagination và đặt giới hạn hữu hạn.

## 16. Checklist thiết kế một HTTP client reactive

Trước khi đưa lời gọi WebClient vào production, hãy xác định:

1. Base URL, method, path và query parameter có được tạo bằng URI builder không?
2. Headers và thông tin xác thực có đúng phạm vi từng request không?
3. Request body có media type và codec tương thích với server không?
4. Response là một object, body rỗng hay stream nhiều phần tử?
5. Status 4xx/5xx được giữ nguyên hay ánh xạ sang exception domain?
6. Lỗi kết nối, timeout và decoding được phân loại ra sao?
7. Timeout có phù hợp deadline tổng của request không?
8. Retry có giới hạn, có lọc lỗi và an toàn với side effect không?
9. Response body và DataBuffer có được tiêu thụ/giải phóng đúng cách không?
10. Payload lớn có streaming hoặc giới hạn bộ nhớ phù hợp không?
11. Filter có tránh ghi log dữ liệu nhạy cảm và truyền correlation ID đúng cách không?
12. Test đã kiểm tra request thực tế, response, lỗi, timeout và cancellation chưa?

WebClient cho phép gửi HTTP request và xử lý response trong cùng mô hình publisher của Reactor. retrieve() giúp xử lý status thông dụng gọn gàng, onStatus ánh xạ lỗi theo hợp đồng dịch vụ, còn exchangeToMono phù hợp khi cần quyết định chi tiết theo response. Khi kết hợp đúng với timeout, retry có chọn lọc, backpressure, cấu hình codec và kiểm thử StepVerifier, các lời gọi HTTP có thể tham gia pipeline reactive mà vẫn giữ rõ lỗi, vòng đời và giới hạn tài nguyên.
