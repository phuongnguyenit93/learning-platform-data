# exchangeToMono và exchangeToFlux cho xử lý theo từng nhánh status trong Spring WebClient

## 1. Khi nào cần rẽ nhánh theo HTTP status?

Spring WebClient có hai cách phổ biến để đọc response:

- **retrieve()** phù hợp khi response thành công được giải mã theo một kiểu thống nhất và lỗi 4xx/5xx được xử lý bằng onStatus hoặc WebClientResponseException.
- **exchangeToMono()** và **exchangeToFlux()** phù hợp khi cách giải mã hoặc kết quả nghiệp vụ phụ thuộc trực tiếp vào status, header hoặc loại body của response.

Ví dụ API tra cứu sản phẩm có thể trả:

| HTTP status | Body | Kết quả client mong muốn |
| --- | --- | --- |
| 200 OK | Product JSON | Giải mã thành Product |
| 201 Created | Product JSON | Giải mã thành Product |
| 204 No Content | Không có body | Kết quả rỗng |
| 404 Not Found | Error JSON hoặc text | Optional.empty hoặc domain result not-found |
| 400 Bad Request | Error JSON | Exception nghiệp vụ có mã lỗi |
| 503 Service Unavailable | Error body | WebClientResponseException giữ status và body |

Nếu mọi status thành công đều trả cùng kiểu dữ liệu và chỉ cần mặc định lỗi 4xx/5xx, retrieve() thường ngắn và dễ đọc hơn. Nếu 404 phải trở thành Optional.empty, 204 phải thành kết quả rỗng, 400 phải decode ErrorPayload và 503 phải giữ WebClientResponseException, exchangeToMono() giúp đặt các nhánh tại cùng một nơi.

Với API trả luồng nhiều phần tử như danh sách lớn, NDJSON hoặc server-sent events, dùng exchangeToFlux() để kiểm tra status trước khi phát dữ liệu.

## 2. WebClient và ClientResponse

### 2.1. WebClient là reactive HTTP client

WebClient cung cấp API fluent dựa trên Reactor, không blocking và hỗ trợ streaming. Một request thường có các bước:

~~~text
WebClient request builder
        |
        v
HTTP request được gửi
        |
        v
ClientResponse nhận status + headers + body
        |
        v
exchangeToMono / exchangeToFlux callback
        |
        +--> decode body thành object
        +--> phát Flux dữ liệu
        +--> tạo lỗi
        +--> bỏ body có chủ đích
~~~

ClientResponse cho phép đọc:

- statusCode(): HTTP status dưới dạng HttpStatusCode.
- headers(): header response.
- cookies(): cookie response.
- bodyToMono(Class): giải mã body thành tối đa một object.
- bodyToFlux(Class): giải mã body thành luồng object.
- releaseBody(): tiêu thụ và giải phóng body khi không cần nội dung.
- createException(): tạo WebClientResponseException chứa status, headers, body và request gốc.
- createError(): trả Mono phát lỗi WebClientResponseException chứa thông tin response.

Không giữ ClientResponse để dùng sau callback. Hãy quyết định cách tiêu thụ body bên trong callback của exchangeToMono hoặc exchangeToFlux.

### 2.2. HttpStatusCode trong Spring hiện đại

Spring Framework 6 dùng abstraction **HttpStatusCode** cho status API. Không cần ép mọi status về enum HttpStatus vì server có thể trả status code hợp lệ nhưng không có hằng enum tương ứng.

~~~java
HttpStatusCode status = response.statusCode();

if (status.is2xxSuccessful()) {
    // 2xx
} else if (status.is4xxClientError()) {
    // 4xx
} else if (status.is5xxServerError()) {
    // 5xx
}

int code = status.value();
~~~

Có thể so sánh chính xác bằng status.value() == 404 hoặc status.isSameCodeAs(HttpStatus.NOT_FOUND). Kiểm tra theo nhóm 2xx linh hoạt hơn so với chỉ so sánh 200 OK, vì API có thể trả 201 Created hoặc 202 Accepted.

## 3. exchangeToMono(): rẽ nhánh trả về một kết quả

### 3.1. Contract

exchangeToMono nhận function xử lý ClientResponse và yêu cầu function trả về Mono:

~~~java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            return response.createError();
        });
~~~

Đoạn code là minh họa cơ bản. Callback nhận response sau khi status và headers đã có. Callback phải quyết định body được decode thành kiểu nào hoặc response được chuyển thành lỗi.

Kết quả có thể là Mono phát một giá trị, Mono hoàn tất rỗng, Mono phát error hoặc một pipeline reactive khác dựa trên dữ liệu đã decode.

### 3.2. Quy tắc quan trọng về response body

Sau khi Mono do callback trả về hoàn tất, WebClient kiểm tra response body. Nếu callback chưa tiêu thụ body, framework tự giải phóng body để tránh rò bộ nhớ và connection.

Điều này có nghĩa:

1. Nếu cần dữ liệu, callback phải gọi bodyToMono, bodyToFlux hoặc API decode phù hợp.
2. Nếu cố ý bỏ qua body, có thể gọi releaseBody() để thể hiện rõ ý định.
3. Sau khi callback hoàn tất, không thể lấy ClientResponse ra rồi decode body ở downstream.
4. Body response là nguồn one-shot. Không gọi bodyToMono hai lần để vừa log vừa decode.
5. Nếu cần inspect nội dung rồi dùng lại, hãy decode một lần thành byte[], String hoặc DTO rồi thao tác trên giá trị đã có.

Cơ chế tự release là lớp bảo vệ tài nguyên, không phải cách để bỏ qua việc thiết kế nhánh xử lý body.

### 3.3. 404 thành kết quả nghiệp vụ rỗng

Một endpoint GET /products/{id} có thể coi 404 là không tìm thấy sản phẩm thay vì lỗi hệ thống:

~~~java
Mono<Optional<Product>> findProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                int status = response.statusCode().value();

                if (status == 404) {
                    return response.releaseBody()
                            .thenReturn(Optional.<Product>empty());
                }

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class)
                            .map(Optional::of)
                            .defaultIfEmpty(Optional.<Product>empty());
                }

                return response.createError();
            });
}
~~~

Nhánh 404 tiêu thụ và giải phóng body rồi trả Optional.empty(). Nhánh 2xx giải mã Product; nếu server trả response thành công nhưng body rỗng, defaultIfEmpty cũng trả Optional.empty().

Nếu nghiệp vụ cần phân biệt 404 với 204, dùng kiểu kết quả rõ hơn như sealed interface hoặc record có trạng thái. Không gộp hai status nếu chúng mang ý nghĩa nghiệp vụ khác nhau.

### 3.4. 204 No Content

204 là response thành công nhưng không có nội dung. Không cố decode nó thành DTO:

~~~java
if (status == 204) {
    return response.releaseBody()
            .thenReturn(Optional.<Product>empty());
}
~~~

Đối với API cập nhật chỉ cần xác nhận thành công, có thể trả Mono<Void>:

~~~java
Mono<Void> updateProduct(String id, ProductUpdate update) {
    return webClient.put()
            .uri("/products/{id}", id)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(update)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.releaseBody();
                }
                return response.createError();
            });
}
~~~

Nếu endpoint có thể trả 200 với body hoặc 204 không body, xử lý riêng hai nhánh để giữ đúng contract.

### 3.5. 400/422 decode error body thành domain exception

Một số API trả cấu trúc lỗi riêng:

~~~json
{
  "code": "INVALID_PRODUCT_ID",
  "message": "Product identifier is invalid"
}
~~~

Client có thể giải mã payload rồi tạo exception nghiệp vụ:

~~~java
if (status.is4xxClientError()) {
    return response.bodyToMono(ApiError.class)
            .defaultIfEmpty(new ApiError(
                    "UNKNOWN",
                    "Remote service returned an empty error body"
            ))
            .flatMap(error -> Mono.<Optional<Product>>error(
                    new RemoteApiException(status.value(), error)
            ));
}
~~~

Body đã được decode trong nhánh này. Exception giữ status code và ApiError để tầng gọi quyết định trả HTTP status, thông báo hoặc mã nghiệp vụ phù hợp.

Nếu API đối tác không bảo đảm error body luôn là JSON đúng schema, có thể đọc thành String để giữ nội dung thô:

~~~java
return response.bodyToMono(String.class)
        .defaultIfEmpty("")
        .flatMap(raw -> Mono.<Optional<Product>>error(
                new RemoteApiException(status.value(), raw)
        ));
~~~

Cách đọc String tránh lỗi decode DTO khi đối tác trả plain text hoặc JSON không đúng cấu trúc mong đợi. Vẫn cần giới hạn kích thước body bằng codec configuration và không ghi raw error body nhạy cảm vào log.

### 3.6. 5xx giữ nguyên WebClientResponseException

Với lỗi 5xx không có logic domain riêng, dùng createError():

~~~java
if (status.is5xxServerError()) {
    return response.createError();
}
~~~

createError() tạo Mono kết thúc bằng WebClientResponseException. Exception chứa status, headers, body và request gốc; có thể kiểm tra response body khi xử lý lỗi:

~~~java
.onErrorResume(WebClientResponseException.class, error -> {
    int status = error.getStatusCode().value();
    String body = error.getResponseBodyAsString();
    return Mono.error(new UpstreamUnavailableException(status, body));
})
~~~

Đoạn này minh họa xử lý sau exchangeToMono. Nếu cần giữ nguyên exception gốc, không cần onErrorResume.

### 3.7. Đọc headers trước khi decode body

Callback có thể chọn cách giải mã theo status và Content-Type:

~~~java
.exchangeToMono(response -> {
    HttpStatusCode status = response.statusCode();
    MediaType contentType = response.headers()
            .contentType()
            .orElse(MediaType.APPLICATION_OCTET_STREAM);

    if (status.is2xxSuccessful()
            && MediaType.APPLICATION_JSON.isCompatibleWith(contentType)) {
        return response.bodyToMono(Product.class);
    }

    return response.createError();
});
~~~

Ví dụ này yêu cầu body thành công phải là JSON. Trong ứng dụng thực tế, nên định nghĩa rõ media type được chấp nhận và cách xử lý khi header sai.

## 4. exchangeToFlux(): rẽ nhánh trả về một luồng

### 4.1. Contract

exchangeToFlux cũng nhận ClientResponse nhưng callback trả về Flux:

~~~java
Flux<Product> products = webClient.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .exchangeToFlux(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToFlux(Product.class);
            }
            return response.createError().flux();
        });
~~~

Dùng exchangeToFlux khi response có thể chứa zero, one hoặc nhiều phần tử:

- Danh sách JSON được giải mã thành từng Product.
- NDJSON phát từng dòng thành một object.
- Server-sent events phát từng event.
- Stream dữ liệu dài được tiêu thụ theo backpressure.

Không cần collectList() nếu downstream có thể xử lý từng phần tử. Gom toàn bộ stream vào List sẽ tăng memory theo kích thước response và làm mất lợi ích streaming.

### 4.2. 404 trả Flux.empty()

Ví dụ danh sách sản phẩm không tồn tại được coi là danh sách rỗng:

~~~java
Flux<Product> listProducts() {
    return webClient.get()
            .uri("/products")
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToFlux(response -> {
                int status = response.statusCode().value();

                if (status == 404) {
                    return response.releaseBody()
                            .thenMany(Flux.empty());
                }

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(Product.class);
                }

                return response.createError().flux();
            });
}
~~~

Nhánh 404 giải phóng body rồi phát Flux rỗng. Nhánh 2xx trả trực tiếp luồng decode. Các status còn lại chuyển thành error signal.

### 4.3. Xử lý error stream theo status

Một API có thể trả một kiểu dữ liệu khi thành công và một error body khác khi thất bại. exchangeToFlux cho phép decode lỗi trước khi phát error:

~~~java
.exchangeToFlux(response -> {
    if (response.statusCode().is2xxSuccessful()) {
        return response.bodyToFlux(Product.class);
    }

    if (response.statusCode().is4xxClientError()) {
        return response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError("UNKNOWN", "No error body"))
                .flatMapMany(error -> Flux.error(
                        new RemoteApiException(
                                response.statusCode().value(),
                                error
                        )
                ));
    }

    return response.createError().flux();
});
~~~

bodyToMono đọc một error payload. flatMapMany chuyển payload thành một Flux kết thúc bằng exception. Không gọi bodyToFlux sau khi bodyToMono đã tiêu thụ response.

### 4.4. Backpressure và cancellation

Với response streaming:

- Trả Flux trực tiếp từ callback để downstream điều khiển demand.
- Dùng concatMap khi cần xử lý từng phần tử tuần tự.
- Chỉ dùng flatMap khi các phần tử có thể xử lý đồng thời và concurrency được giới hạn.
- Không gọi subscribe() bên trong callback.
- Không gọi block() trong WebFlux request path.
- Không chuyển Flux thành List nếu response có thể lớn.
- Nếu consumer hủy subscription, cancellation phải truyền qua pipeline để HTTP stream dừng theo cơ chế của client connector.

Với stream vô hạn như SSE, callback trả Flux cho consumer; kiểm thử cả complete, error lẫn cancel.

## 5. So sánh retrieve, onStatus và exchangeTo*

| Nhu cầu | API phù hợp |
| --- | --- |
| Giải mã body thành một DTO; lỗi 4xx/5xx mặc định thành exception | retrieve().bodyToMono() |
| Giải mã một luồng DTO | retrieve().bodyToFlux() |
| Tùy chỉnh exception cho 4xx hoặc 5xx nhưng vẫn dùng kiểu body thành công thống nhất | retrieve().onStatus(...) |
| 404 thành Optional.empty, 204 thành kết quả rỗng, 400 decode error DTO | exchangeToMono() |
| Thành công trả Flux, 404 trả Flux.empty, lỗi khác phát error | exchangeToFlux() |
| Chọn decoder khác nhau theo status hoặc header | exchangeToMono() hoặc exchangeToFlux() |

### 5.1. retrieve() với onStatus

Ví dụ retrieve() xử lý lỗi tùy chỉnh:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError, response ->
                response.bodyToMono(ApiError.class)
                        .map(error -> new RemoteApiException(
                                response.statusCode().value(),
                                error
                        )))
        .onStatus(HttpStatusCode::is5xxServerError, response ->
                response.createException())
        .bodyToMono(Product.class);
~~~

retrieve() tự xử lý status 4xx/5xx mặc định bằng WebClientResponseException nếu không có status handler phù hợp. onStatus cho phép đổi cách tạo exception. Sau đó body thành công vẫn được decode thành Product.

### 5.2. Khi nào không cần exchangeToMono?

Không nên dùng exchangeToMono cho mọi request chỉ vì nó linh hoạt hơn. Nếu chỉ cần lấy body và để 4xx/5xx thành exception mặc định, retrieve() diễn đạt đúng ý định với ít code hơn.

Dùng exchangeToMono khi status thay đổi **kiểu kết quả hoặc hành vi nghiệp vụ**, không chỉ thay đổi message lỗi.

### 5.3. exchange() cũ đã deprecated

API exchange() cũ trả ClientResponse ra ngoài mà không quản lý đầy đủ việc tiêu thụ body. Từ Spring Framework 5.3, exchange() đã deprecated do nguy cơ rò bộ nhớ và connection nếu response body không được xử lý đúng.

Dùng retrieve(), exchangeToMono() hoặc exchangeToFlux(). Không bắt đầu code mới bằng exchange().

## 6. Response body là one-shot: các lỗi cần tránh

### 6.1. Đọc body hai lần

Sai:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(String.class)
                .flatMap(raw -> {
                    log.info("Response: {}", raw);
                    return response.bodyToMono(Product.class);
                })
)
~~~

bodyToMono đầu tiên đã tiêu thụ body. Lần gọi thứ hai không thể đọc lại response từ đầu; có thể nhận body rỗng hoặc lỗi decode.

Cách đúng là decode một lần rồi dùng lại giá trị. Nếu cần parse từ String, dùng Mono.fromCallable để xử lý API parse có checked exception:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(String.class)
                .flatMap(raw -> Mono.fromCallable(
                        () -> objectMapper.readValue(raw, Product.class)
                ))
)
~~~

Nếu muốn kiểm tra schema, hãy decode một lần thành JsonNode hoặc DTO thích hợp. Không log raw body trong production nếu nó có token, thông tin cá nhân hoặc dữ liệu nhạy cảm.

### 6.2. Trả ClientResponse ra ngoài callback

Không nên làm:

~~~java
Mono<ClientResponse> responseMono = webClient.get()
        .uri("/products/1")
        .exchangeToMono(Mono::just);
~~~

exchangeToMono được thiết kế để callback quyết định cách xử lý response. Sau khi callback kết thúc, body chưa tiêu thụ có thể được release. Trả ClientResponse ra ngoài khiến code downstream phụ thuộc vào response đã hết lifecycle.

Hãy trả DTO, Optional, domain result, error hoặc Flux dữ liệu đã decode.

### 6.3. Bỏ body mà không thể hiện ý định

Nếu status 404 được xem là không tìm thấy và body không cần thiết:

~~~java
return response.releaseBody()
        .thenReturn(Optional.<Product>empty());
~~~

WebClient có cơ chế auto-release body chưa tiêu thụ khi callback hoàn tất. releaseBody() giúp nhánh bỏ body rõ ràng và dễ review.

### 6.4. Gọi subscribe() lồng nhau

Sai:

~~~java
.exchangeToMono(response -> {
    response.bodyToMono(Product.class).subscribe(this::save);
    return Mono.empty();
})
~~~

subscribe() tạo subscription độc lập nằm ngoài pipeline mà WebClient đang quản lý. Callback có thể hoàn tất trước khi save xong; lỗi và cancellation không còn được truyền đúng về caller.

Đúng:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(Product.class)
                .flatMap(this::save)
)
~~~

Trả Publisher từ callback để framework và caller quản lý lifecycle.

### 6.5. Dùng block() trên event loop

Không gọi block() trong controller, service reactive hoặc callback exchangeTo*. block() chặn thread đang điều phối reactive I/O và có thể gây giảm throughput hoặc deadlock.

Trong unit test, StepVerifier là lựa chọn phù hợp để kiểm tra Mono/Flux mà không phải block thủ công.

## 7. Status đặc biệt và headers

### 7.1. 201 Created

201 thường có thể chứa resource mới và Location header. Đọc cả body và header nếu nghiệp vụ cần:

~~~java
.exchangeToMono(response -> {
    if (response.statusCode().value() == 201) {
        URI location = response.headers().asHttpHeaders().getLocation();

        return response.bodyToMono(Product.class)
                .map(product -> new CreatedProduct(location, product));
    }
    return response.createError();
})
~~~

CreatedProduct là kiểu kết quả do ứng dụng định nghĩa để giữ Location và Product. Nếu API trả 201 nhưng không có body, có thể dùng releaseBody() và tạo kết quả chỉ chứa Location.

### 7.2. 202 Accepted

202 chỉ xác nhận request đã được nhận để xử lý; không có nghĩa tác vụ đã hoàn thành. Thường nên đọc operation ID hoặc URL trạng thái nếu API cung cấp.

Không xử lý 202 như 200 nếu tầng nghiệp vụ cần chờ kết quả cuối cùng.

### 7.3. 206 Partial Content

206 biểu thị response chứa một phần representation. Nếu client yêu cầu Range, cần kiểm tra Content-Range và xử lý byte range đúng contract. Không decode một phần dữ liệu thành DTO hoàn chỉnh trừ khi API được thiết kế như vậy.

### 7.4. 304 Not Modified

304 thường xuất hiện với conditional GET. Đây không phải status 2xx nhưng cũng không nhất thiết là lỗi nghiệp vụ. Nếu client dùng cache:

~~~java
if (status == 304) {
    return response.releaseBody()
            .thenReturn(cachedProduct);
}
~~~

Chỉ dùng cachedProduct nếu cache key, ETag hoặc Last-Modified khớp với request hiện tại. Nếu không có cache representation hợp lệ, cần xử lý 304 theo contract riêng.

### 7.5. Location, ETag và Retry-After

Có thể đọc headers trước khi tiêu thụ body:

- Location: URI resource hoặc operation được tạo.
- ETag: validator cho conditional request.
- Last-Modified: thời điểm representation thay đổi.
- Retry-After: thời gian chờ trước khi retry, thường liên quan 429 hoặc 503.
- Content-Type: chọn decoder phù hợp.
- Content-Length: thông tin kích thước nếu có, không phải lúc nào cũng tồn tại.

Không giả định mọi header đều có mặt. Dùng Optional hoặc null check theo API.

## 8. Retry, timeout và lỗi mạng

exchangeToMono/Flux quyết định cách chuyển response thành kết quả. Retry và timeout thường đặt ở ngoài publisher đã xây dựng:

~~~java
return findProduct(id)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(this::isTransientFailure));
~~~

Chỉ retry các lỗi có thể phục hồi, ví dụ 502, 503, 504 hoặc lỗi kết nối tạm thời. Không retry mọi 4xx vì các lỗi như 400, 401, 403 hoặc 404 thường không thể khắc phục bằng cách gửi lại cùng request.

Với POST hoặc thao tác có side effect, chỉ retry khi API có idempotency key hoặc cơ chế bảo đảm không tạo dữ liệu trùng. GET thường phù hợp với retry hơn nhưng vẫn cần xem contract upstream.

Khi nhận 429 hoặc 503 có Retry-After, hãy tôn trọng chính sách retry của server. Không tạo retry loop dày khiến upstream quá tải.

## 9. Ví dụ Java 17+ chạy được: CatalogClient phân nhánh theo status

Ví dụ dùng Spring Boot 3.5.5, Java 17+ và WebFlux. CatalogClient có hai method:

- findProduct(): dùng exchangeToMono, trả Optional<Product>, map 404 thành empty và decode 4xx error payload.
- listProducts(): dùng exchangeToFlux, stream Product cho 2xx, trả Flux.empty() cho 404 và tạo error cho status khác.

### 9.1. Cấu trúc dự án

~~~text
webclient-status-branching/
├── pom.xml
└── src/
    ├── main/java/example/catalog/
    │   ├── DemoApplication.java
    │   ├── CatalogProperties.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── CatalogController.java
    │   ├── Product.java
    │   ├── ApiError.java
    │   └── RemoteApiException.java
    └── test/java/example/catalog/
        └── CatalogClientTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-status-branching</artifactId>
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
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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
~~~

### 9.3. Product.java

~~~java
package example.catalog;

public record Product(String id, String name) {
}
~~~

### 9.4. ApiError.java

~~~java
package example.catalog;

public record ApiError(String code, String message) {
}
~~~

### 9.5. RemoteApiException.java

~~~java
package example.catalog;

public class RemoteApiException extends RuntimeException {

    private final int statusCode;
    private final ApiError error;

    public RemoteApiException(int statusCode, ApiError error) {
        super("Catalog API returned " + statusCode + ": " + error.message());
        this.statusCode = statusCode;
        this.error = error;
    }

    public int statusCode() {
        return statusCode;
    }

    public ApiError error() {
        return error;
    }
}
~~~

### 9.6. CatalogClient.java

~~~java
package example.catalog;

import java.util.Optional;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Optional<Product>> findProduct(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    HttpStatusCode status = response.statusCode();

                    if (status.value() == 404 || status.value() == 204) {
                        return response.releaseBody()
                                .thenReturn(Optional.<Product>empty());
                    }

                    if (status.is2xxSuccessful()) {
                        return response.bodyToMono(Product.class)
                                .map(Optional::of)
                                .defaultIfEmpty(Optional.<Product>empty());
                    }

                    if (status.is4xxClientError()) {
                        return response.bodyToMono(ApiError.class)
                                .defaultIfEmpty(new ApiError(
                                        "UNKNOWN",
                                        "Remote service returned an empty error body"
                                ))
                                .flatMap(error -> Mono.<Optional<Product>>error(
                                        new RemoteApiException(status.value(), error)
                                ));
                    }

                    return response.createError();
                });
    }

    public Flux<Product> listProducts() {
        return webClient.get()
                .uri("/products")
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToFlux(response -> {
                    HttpStatusCode status = response.statusCode();

                    if (status.value() == 404) {
                        return response.releaseBody()
                                .thenMany(Flux.empty());
                    }

                    if (status.is2xxSuccessful()) {
                        return response.bodyToFlux(Product.class);
                    }

                    return response.createError().flux();
                });
    }
}
~~~

Phân tích:

- findProduct kiểm tra 404 và 204 trước khi decode DTO.
- Nhánh thành công 2xx giải mã Product; body rỗng tạo Optional.empty().
- Nhánh 4xx giải mã ApiError và tạo RemoteApiException.
- Nhánh còn lại dùng createError để giữ status/body trong WebClientResponseException.
- listProducts trả bodyToFlux trực tiếp, không gom toàn bộ danh sách.
- Nhánh 404 của listProducts giải phóng body rồi trả Flux rỗng.

### 9.7. CatalogProperties.java

~~~java
package example.catalog;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String baseUrl) {
}
~~~

### 9.8. CatalogClientConfiguration.java

~~~java
package example.catalog;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties) {
        return builder.baseUrl(properties.baseUrl()).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

### 9.9. CatalogController.java

~~~java
package example.catalog;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> find(@PathVariable String id) {
        return catalogClient.findProduct(id)
                .map(found -> {
                    if (found.isPresent()) {
                        return ResponseEntity.ok(found.get());
                    }
                    return ResponseEntity.<Product>notFound().build();
                });
    }

    @GetMapping(path = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Product> stream() {
        return catalogClient.listProducts();
    }
}
~~~

Controller minh họa cách sử dụng kết quả nghiệp vụ: Optional.empty() được ánh xạ thành HTTP 404 của API local; Flux được trả về dưới dạng NDJSON để client nhận từng Product.

### 9.10. DemoApplication.java

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.11. application.yml

~~~yaml
catalog:
  base-url: http://localhost:8081
~~~

Trong môi trường thực tế, đổi base-url thành địa chỉ upstream qua cấu hình môi trường hoặc secret/config management phù hợp. Không hardcode credential vào source code.

## 10. Kiểm thử bằng MockWebServer và StepVerifier

Spring khuyến nghị kiểm thử WebClient bằng mock web server như OkHttp MockWebServer hoặc WireMock. Mock server nhận HTTP thật từ WebClient nên kiểm tra được request, status, header và body ở ranh giới transport.

Tệp CatalogClientTest.java:

~~~java
package example.catalog;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

    private MockWebServer server;
    private CatalogClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

        client = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void decodesProductFrom200Response() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findProduct("p-1"))
                .expectNext(Optional.of(new Product("p-1", "Keyboard")))
                .verifyComplete();
    }

    @Test
    void maps204ToEmptyOptional() {
        server.enqueue(new MockResponse().setResponseCode(204));

        StepVerifier.create(client.findProduct("p-1"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void maps404ToEmptyOptionalAndIgnoresErrorBody() {
        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"code\":\"NOT_FOUND\",\"message\":\"Missing\"}"));

        StepVerifier.create(client.findProduct("missing"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void maps400ToDomainExceptionWithDecodedPayload() {
        server.enqueue(new MockResponse()
                .setResponseCode(400)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"code\":\"INVALID_ID\",\"message\":\"Bad id\"}"));

        StepVerifier.create(client.findProduct("bad"))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(RemoteApiException.class);

                    RemoteApiException remote = (RemoteApiException) error;
                    assertThat(remote.statusCode()).isEqualTo(400);
                    assertThat(remote.error().code()).isEqualTo("INVALID_ID");
                    assertThat(remote.error().message()).isEqualTo("Bad id");
                })
                .verify();
    }

    @Test
    void preserves503AsWebClientResponseException() {
        server.enqueue(new MockResponse()
                .setResponseCode(503)
                .addHeader("Content-Type", MediaType.TEXT_PLAIN_VALUE)
                .setBody("temporarily unavailable"));

        StepVerifier.create(client.findProduct("p-1"))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(WebClientResponseException.class);

                    WebClientResponseException remote =
                            (WebClientResponseException) error;

                    assertThat(remote.getStatusCode().value()).isEqualTo(503);
                    assertThat(remote.getResponseBodyAsString())
                            .contains("temporarily unavailable");
                })
                .verify();
    }

    @Test
    void streamsProductsFrom200Response() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("""
                        [
                          {"id":"p-1","name":"Keyboard"},
                          {"id":"p-2","name":"Mouse"}
                        ]
                        """));

        StepVerifier.create(client.listProducts())
                .expectNext(new Product("p-1", "Keyboard"))
                .expectNext(new Product("p-2", "Mouse"))
                .verifyComplete();
    }

    @Test
    void maps404ListResponseToEmptyFlux() {
        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .setBody("not found"));

        StepVerifier.create(client.listProducts())
                .verifyComplete();
    }
}
~~~

Các test bao phủ nhánh 200, 204, 404, 400, 503 và luồng nhiều Product. StepVerifier xác nhận onNext, onComplete và onError mà không cần block trong code ứng dụng.

### 10.1. Chạy test

Tại thư mục có pom.xml:

~~~bash
mvn test
~~~

### 10.2. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Ứng dụng local mặc định gọi upstream tại localhost:8081. Khi upstream sẵn sàng:

~~~bash
curl -i http://localhost:8080/catalog/p-1
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/catalog/stream
~~~

Endpoint đầu trả một Product hoặc HTTP 404 nếu upstream trả 404/204. Endpoint stream phát từng Product dưới dạng NDJSON.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng retrieve() nhưng cần đổi kiểu kết quả theo status | Khó biểu diễn 404 thành Optional hoặc body lỗi thành kiểu khác | Dùng exchangeToMono |
| Dùng exchangeToMono cho mọi request đơn giản | Code dài hơn retrieve() mà không có lợi ích | Dùng retrieve() nếu chỉ cần decode và onStatus |
| Chỉ kiểm tra status 200 | Bỏ sót 201, 202 hoặc status 2xx khác | Dùng is2xxSuccessful khi contract cho phép |
| Decode body 204 thành DTO | Decoder nhận body rỗng | Xử lý 204 trước và trả empty/no-content |
| Bỏ qua body 404 nhưng không release | Có nguy cơ giữ tài nguyên response | Dùng releaseBody() hoặc decode body |
| Gọi bodyToMono hai lần | Body one-shot đã bị tiêu thụ | Decode một lần rồi biến đổi giá trị |
| Trả ClientResponse ra downstream | Response có thể đã được cleanup khi callback hoàn tất | Trả DTO/domain result hoặc Flux đã decode |
| Gọi subscribe() trong callback | Tạo pipeline độc lập, mất quản lý error/cancel | Compose bằng flatMap/then/concatMap |
| Gọi block() trên event loop | Chặn I/O thread | Trả Mono/Flux và để framework subscribe |
| Gọi createError() rồi vẫn decode body | Body đã được chuyển thành error | Chọn một nhánh xử lý duy nhất |
| Dùng bodyToMono cho stream lớn | Có thể gom quá nhiều dữ liệu | Dùng bodyToFlux và backpressure |
| collectList() cho response rất lớn | Tăng memory theo toàn bộ response | Xử lý từng phần tử |
| Map mọi lỗi thành 404 | Che lỗi upstream hoặc lỗi server | Chỉ map status có ý nghĩa nghiệp vụ tương ứng |
| Retry mọi exception | Lặp lại 4xx hoặc thao tác không idempotent | Retry có điều kiện, giới hạn số lần và backoff |
| Log raw response body | Lộ token, PII hoặc dữ liệu nhạy cảm | Log status, correlation ID và metadata đã lọc |

## 12. Checklist thiết kế nhánh status

Trước khi hoàn thiện một WebClient call, trả lời các câu hỏi:

1. API có thể trả những status nào?
2. Status nào là thành công và có body?
3. Status nào thành công nhưng không có body, như 204?
4. 404 có phải lỗi hay là kết quả nghiệp vụ bình thường?
5. 400/409/422 có error DTO cần giải mã không?
6. 5xx có nên giữ WebClientResponseException để retry hoặc quan sát?
7. Response có thể là JSON array, NDJSON, SSE hay binary stream?
8. Mỗi nhánh đã tiêu thụ, giải phóng hoặc chuyển body đúng cách chưa?
9. Có gọi bodyToMono/bodyToFlux nhiều lần trên cùng response không?
10. Có đặt timeout, retry và cancellation theo contract không?
11. Có kiểm thử status biên bằng mock HTTP server không?
12. Có kiểm tra body lỗi và header mà không ghi dữ liệu nhạy cảm vào log không?

## 13. Ghi nhớ

- retrieve() là lựa chọn mặc định cho decode đơn giản; onStatus dùng để tùy chỉnh lỗi 4xx/5xx.
- exchangeToMono() cho phép rẽ nhánh theo status và trả một kết quả Mono.
- exchangeToFlux() cho phép rẽ nhánh theo status và trả luồng Flux.
- HttpStatusCode hỗ trợ kiểm tra status theo nhóm 2xx, 4xx và 5xx.
- Callback phải quyết định cách decode hoặc bỏ body; response body là one-shot.
- Nếu callback hoàn tất mà body chưa được tiêu thụ, WebClient tự release body để tránh leak.
- Dùng releaseBody() khi cố ý bỏ response content.
- Dùng createError() để tạo WebClientResponseException giữ status, headers, body và request.
- Không trả ClientResponse ra ngoài callback, không gọi subscribe() hoặc block() bên trong pipeline.
- exchange() cũ đã deprecated từ Spring Framework 5.3; dùng retrieve() hoặc exchangeTo*.
- Với stream lớn, trả Flux trực tiếp và giữ backpressure.
- Kiểm thử các nhánh 2xx, 204, 404, 4xx, 5xx và streaming bằng MockWebServer cùng StepVerifier.

**Tài liệu chính thức:**
- [Spring Framework — WebClient Exchange: exchangeToMono, exchangeToFlux và response body lifecycle](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html)
- [Spring Framework — WebClient retrieve() and onStatus](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework Javadoc — WebClient.RequestHeadersSpec](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html)
- [Spring Framework Javadoc — ClientResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html)
- [Spring Framework — Testing WebClient with MockWebServer](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
