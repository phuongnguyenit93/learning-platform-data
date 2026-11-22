# Xử lý onStatus và ánh xạ lỗi HTTP trong Spring WebClient

WebClient là HTTP client reactive của Spring WebFlux. Khi gọi một API từ xa, client có thể nhận response thành công, response lỗi HTTP như 404 hoặc 503, hoặc không nhận được response vì lỗi kết nối, timeout hay giải mã. Các trường hợp này cần được phân biệt rõ để tầng service xử lý đúng.

Với WebClient, hai API thường dùng là retrieve() và exchangeToMono()/exchangeToFlux(). Khi dùng retrieve(), ta có thể đăng ký callback **onStatus** để chuyển status HTTP thành exception của ứng dụng. Nếu không đăng ký callback, WebClient mặc định chuyển response 4xx và 5xx thành WebClientResponseException. Khi cần phân nhánh response theo status, đọc body khác nhau hoặc coi 404 là kết quả rỗng, exchangeToMono() thường dễ kiểm soát hơn.

Bài học thuộc nhóm **Đọc phản hồi WebClient**, tập trung vào onStatus, cách đọc error body, ánh xạ lỗi HTTP thành domain exception, phân biệt lỗi HTTP với lỗi transport/codec và kiểm thử hành vi client.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời request-response khi dùng WebClient.retrieve().
- Giải thích vai trò và chữ ký của ResponseSpec.onStatus().
- Hiểu hành vi mặc định của WebClient với status 4xx và 5xx.
- Ánh xạ status HTTP thành exception có ý nghĩa nghiệp vụ.
- Đọc error body an toàn và tránh tiêu thụ response body hai lần.
- Phân biệt Mono.empty() trong onStatus với việc biến response thành Mono.empty().
- Dùng onRawStatus() cho mã status không chuẩn.
- Chọn retrieve() hay exchangeToMono()/exchangeToFlux().
- Phân biệt lỗi HTTP, lỗi kết nối, timeout và lỗi decode.
- Thiết kế retry có điều kiện và tôn trọng Retry-After.
- Viết ví dụ Java 17+ với Spring Boot WebFlux và MockWebServer.

## 2. Vòng đời cơ bản của WebClient response

Một request WebClient thường được tạo bằng builder, gửi đi, rồi chuyển response thành kiểu Java:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Các bước chính:

1. WebClient xây dựng HTTP request từ method, URI, headers và body.
2. HTTP connector gửi request qua network.
3. Server trả status, headers và body.
4. retrieve() tạo ResponseSpec để cấu hình cách xử lý response.
5. bodyToMono() hoặc bodyToFlux() chọn codec để giải mã response body.
6. Publisher phát dữ liệu hoặc phát lỗi tới downstream.

Status HTTP và nội dung body là hai phần riêng. Một response 404 vẫn có thể chứa JSON mô tả lỗi; response 204 có thể không có body; response 503 có thể chứa HTML từ reverse proxy thay vì JSON của API.

Không nên chỉ nhìn vào body để quyết định request thành công. Hãy kiểm tra status bằng onStatus hoặc exchangeToMono trước khi giải mã theo kiểu thành công.

## 3. Hành vi mặc định của retrieve()

Nếu gọi retrieve() mà không đăng ký status handler, WebClient mặc định xem response có status 4xx hoặc 5xx là lỗi. Nó phát WebClientResponseException, chứa status, headers, request và response body đã đọc được.

~~~java
Mono<Product> result = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Nếu server trả 200 với JSON hợp lệ, publisher phát Product. Nếu server trả 404, publisher phát WebClientResponseException.NotFound. Nếu server trả 503, publisher phát WebClientResponseException.ServiceUnavailable.

Một số method hữu ích trên WebClientResponseException:

- getStatusCode(): status dưới dạng HttpStatusCode.
- getHeaders(): response headers.
- getResponseBodyAsString(): body đã đọc thành chuỗi.
- getResponseBodyAsByteArray(): body dạng byte array.
- getRequest(): request gây ra response lỗi.
- getMessage(): thông tin exception tổng quát.

Các subclass cụ thể có thể phản ánh status chuẩn, nhưng code ứng dụng thường nên dựa trên getStatusCode() hoặc ánh xạ sang exception nghiệp vụ riêng. Không phụ thuộc vào việc mọi status đều có subclass được đặt tên.

### Mặc định không có nghĩa mọi lỗi đều là WebClientResponseException

WebClientResponseException đại diện cho một HTTP response lỗi đã nhận được. Các lỗi sau không nhất thiết là WebClientResponseException:

| Tình huống | Nhóm lỗi thường gặp |
| --- | --- |
| Server trả 404 | WebClientResponseException.NotFound nếu dùng mặc định |
| Server trả 503 | WebClientResponseException.ServiceUnavailable nếu dùng mặc định |
| DNS không phân giải được | WebClientRequestException hoặc lỗi connector |
| TCP connection bị từ chối | WebClientRequestException hoặc lỗi connector |
| Request timeout | TimeoutException hoặc exception từ connector |
| Response body JSON sai cú pháp | DecodingException / lỗi codec |
| Downstream hủy subscription | Cancellation, không phải HTTP error |

onStatus chỉ được gọi khi WebClient đã nhận được một ClientResponse và cần đánh giá status. Nếu không có HTTP response, không có status để onStatus xử lý.

## 4. onStatus() là gì?

ResponseSpec.onStatus() đăng ký một status predicate và một hàm xử lý response tương ứng.

Chữ ký khái quát:

~~~java
ResponseSpec onStatus(
    Predicate<HttpStatusCode> statusPredicate,
    Function<ClientResponse, Mono<? extends Throwable>> exceptionFunction
);
~~~

Hai thành phần:

- **statusPredicate:** nhận HttpStatusCode và trả true nếu status cần được xử lý.
- **exceptionFunction:** nhận ClientResponse và trả Mono chứa exception sẽ được phát xuống downstream.

Ví dụ:

~~~java
Mono<Product> result = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.createException())
    .bodyToMono(Product.class);
~~~

Ví dụ này vẫn phát WebClientResponseException cho 404, nhưng cho thấy cách đăng ký handler riêng. Khi cần đổi sang exception nghiệp vụ, hãy map exception do createException() tạo ra.

### Callback phải trả Mono của Throwable

Hàm callback không trả trực tiếp exception:

~~~java
.onStatus(
    HttpStatusCode::is5xxServerError,
    response -> response.createException()
        .map(error -> new CatalogUnavailableException(error)))
~~~

createException() tạo Mono<WebClientResponseException>. map() chuyển nó thành Mono<CatalogUnavailableException>, tương thích với kiểu Mono<? extends Throwable> mà onStatus yêu cầu.

Không gọi block() trong callback. WebClient là reactive; hãy trả publisher để framework compose với request lifecycle.

### Nhiều status handler

Có thể đăng ký nhiều onStatus:

~~~java
.retrieve()
.onStatus(
    status -> status.value() == 404,
    response -> response.createException()
        .map(ProductNotFoundException::new))
.onStatus(
    HttpStatusCode::is4xxClientError,
    response -> response.createException()
        .map(CatalogClientException::new))
.onStatus(
    HttpStatusCode::is5xxServerError,
    response -> response.createException()
        .map(CatalogUnavailableException::new))
.bodyToMono(Product.class);
~~~

Đặt handler cụ thể trước handler tổng quát. Với các handler tùy chỉnh, WebClient áp dụng handler đầu tiên có predicate khớp. Nếu đặt 4xx tổng quát trước 404, handler 404 phía sau sẽ không nhận response đó.

Handler mặc định của retrieve() xử lý 4xx/5xx khi không có custom handler phù hợp.

## 5. onStatus() ánh xạ HTTP status sang domain exception

Không nên để mọi tầng service phụ thuộc trực tiếp vào WebClientResponseException nếu ứng dụng cần một hợp đồng lỗi ổn định. Có thể chuyển status thành exception có ngữ nghĩa của domain hoặc upstream service.

Ví dụ quy tắc:

| Status từ API từ xa | Exception ứng dụng |
| --- | --- |
| 404 Not Found | ProductNotFoundException |
| 400 Bad Request | CatalogClientException hoặc lỗi request |
| 401/403 | CatalogAuthorizationException |
| 409 Conflict | CatalogConflictException |
| 429 Too Many Requests | CatalogRateLimitedException |
| 5xx | CatalogUnavailableException |

Ví dụ mapping:

~~~java
private RuntimeException mapError(
        String productId,
        WebClientResponseException error) {

    int status = error.getStatusCode().value();

    if (status == 404) {
        return new ProductNotFoundException(productId, error);
    }

    if (status == 429) {
        String retryAfter =
            error.getHeaders().getFirst(HttpHeaders.RETRY_AFTER);

        return new CatalogRateLimitedException(retryAfter, error);
    }

    if (error.getStatusCode().is5xxServerError()) {
        return new CatalogUnavailableException(
            error.getStatusCode(), error);
    }

    return new CatalogClientException(
        error.getStatusCode(), error);
}
~~~

Tại client boundary, việc ánh xạ này tách chi tiết HTTP của nhà cung cấp khỏi service nghiệp vụ. Service có thể xử lý ProductNotFoundException mà không cần biết API từ xa đặt mã lỗi hoặc cấu trúc JSON thế nào.

Không nhất thiết phải tạo một exception class cho mọi status. Chỉ tạo kiểu riêng khi ứng dụng có cách xử lý khác nhau, ví dụ trả 404, yêu cầu người dùng xác thực lại, chờ rate limit hoặc thử lại một upstream tạm thời.

## 6. Đọc error body như thế nào?

API từ xa thường trả JSON error body:

~~~json
{
  "code": "PRODUCT_NOT_FOUND",
  "message": "No product exists with the supplied identifier"
}
~~~

Có hai cách phổ biến để lấy thông tin đó.

### Cách 1: createException() và đọc body từ exception

~~~java
.onStatus(
    HttpStatusCode::isError,
    response -> response.createException()
        .map(error -> {
            log.warn("Catalog returned HTTP {}", error.getStatusCode());
            return new CatalogClientException(
                error.getStatusCode(), error);
        }))
~~~

createException() tạo WebClientResponseException và lưu status, headers cùng response body đã đọc được. Sau đó ứng dụng có thể lấy body qua getResponseBodyAsString() hoặc getResponseBodyAsByteArray().

Ưu điểm:

- Không cần biết error body có JSON hay không.
- Vẫn có thông tin khi reverse proxy trả HTML hoặc plain text.
- Dễ ánh xạ lỗi tổng quát.

Nếu cần parse body theo schema cụ thể, có thể dùng getResponseBodyAs(RemoteError.class) với decoder phù hợp được hỗ trợ bởi exception; hoặc tự đọc body trong callback.

### Cách 2: decode body trực tiếp trong callback

~~~java
.onStatus(
    HttpStatusCode::is4xxClientError,
    response -> response.bodyToMono(RemoteError.class)
        .defaultIfEmpty(new RemoteError("UNKNOWN", "Request failed"))
        .map(body -> new RemoteApiException(
            response.statusCode(),
            body.code(),
            body.message())))
~~~

Cách này phù hợp khi API từ xa bảo đảm một schema lỗi JSON ổn định. Tuy nhiên, nếu body rỗng hoặc không đúng JSON, việc decode có thể phát lỗi codec thay cho exception nghiệp vụ dự kiến. Cần quyết định rõ cách fallback cho body rỗng, malformed hoặc content type không đúng.

### Không đọc response body hai lần

Response body là stream có thể tiêu thụ một lần. Nếu callback đã gọi bodyToMono(RemoteError.class), không thể mong bodyToMono(Product.class) phía sau đọc lại cùng body.

Tương tự, sau khi gọi createException(), body đã được thu vào exception. Đừng gọi một body reader khác trên cùng response với kỳ vọng nó còn nguyên.

Nếu cần giữ raw body và parse nhiều lần, hãy thu body một lần ở boundary, sau đó parse từ byte array/string đã lưu; cân nhắc giới hạn bộ nhớ và tránh lưu dữ liệu nhạy cảm.

## 7. Ý nghĩa đặc biệt của Mono.empty() trong onStatus()

Một điểm dễ hiểu nhầm là callback onStatus có thể trả Mono.empty().

~~~java
.retrieve()
.onStatus(
    status -> status.value() == 404,
    response -> Mono.empty())
.bodyToMono(Product.class);
~~~

Ở đây, Mono.empty() có nghĩa **không chuyển response này thành exception**. WebClient tiếp tục xử lý response như một response bình thường và chuyển body cho bước bodyToMono(Product.class).

Nó không có nghĩa:

- Bỏ qua body.
- Tự động tạo Product rỗng.
- Tự động chuyển 404 thành Optional.empty().
- Tự động bỏ qua tất cả status lỗi.
- Tự động giải phóng body mà không cần xử lý.

Nếu response 404 có body JSON lỗi, bodyToMono(Product.class) vẫn cố decode body đó thành Product. Điều này có thể thất bại hoặc tạo object thiếu dữ liệu tùy cấu trúc và decoder.

### Khi muốn 404 có nghĩa là không tồn tại

Nếu 404 phải được xem là kết quả vắng mặt, thường dùng exchangeToMono() để phân nhánh status và kiểm soát việc tiêu thụ body:

~~~java
public Mono<Optional<Product>> findOptional(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class)
                    .map(Optional::of)
                    .defaultIfEmpty(Optional.empty());
            }

            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                    .thenReturn(Optional.empty());
            }

            return response.createException()
                .flatMap(error ->
                    Mono.<Optional<Product>>error(mapError(id, error)));
        });
}
~~~

Trong nhánh 404, releaseBody() tiêu thụ/giải phóng body mà không cố decode thành Product, rồi trả Optional.empty(). Với các status khác, code tạo exception và ánh xạ theo quy tắc chung.

Đây là khác biệt quan trọng: onStatus(... -> Mono.empty()) chỉ bỏ việc chuyển status thành exception; exchangeToMono() cho phép quyết định chính xác giá trị trả về theo từng response.

## 8. onRawStatus() cho status code không chuẩn

onStatus() nhận HttpStatusCode predicate. Nếu tích hợp một upstream dùng mã status không chuẩn hoặc muốn so khớp trực tiếp số nguyên, có thể dùng onRawStatus().

~~~java
.retrieve()
.onRawStatus(
    statusCode -> statusCode == 599,
    response -> response.createException()
        .map(UpstreamNetworkException::new))
.bodyToMono(Product.class);
~~~

599 không phải status HTTP chuẩn trong danh sách mã chuẩn, nhưng một số proxy hoặc hệ thống nội bộ dùng nó như mã lỗi mở rộng. Chỉ dùng onRawStatus khi hợp đồng upstream thực sự định nghĩa mã đó.

Không dùng raw status để thay thế các predicate chuẩn nếu HttpStatusCode::is4xxClientError hoặc is5xxServerError đã diễn đạt đúng ý định.

## 9. retrieve() hay exchangeToMono()/exchangeToFlux()?

Hai cách tiếp cận đều hợp lệ, nhưng phù hợp với mức kiểm soát khác nhau.

| Tiêu chí | retrieve() + onStatus() | exchangeToMono()/exchangeToFlux() |
| --- | --- | --- |
| Mục tiêu | Đọc body thành kiểu đích sau khi khai báo status handler | Tự phân nhánh toàn bộ response |
| Xử lý 4xx/5xx mặc định | Có, thành WebClientResponseException | Tự kiểm tra status |
| Ánh xạ exception | Dùng onStatus | Tự tạo exception trong callback |
| 404 thành empty | Có thể nhưng cần hiểu Mono.empty() và body | Rõ ràng, có thể releaseBody() |
| Nhiều response schema | Có thể nhưng kém trực quan hơn | Phù hợp |
| Đọc headers/status để quyết định kiểu body | Có thể qua status callback; response body vẫn do body reader phía sau xử lý | Tự do đọc status, headers và body theo nhánh |
| Độ dài code | Thường ngắn | Thường dài hơn nhưng rõ nhánh |

Dùng retrieve() khi response thành công có một schema ổn định và các lỗi có thể ánh xạ bằng onStatus.

Dùng exchangeToMono()/exchangeToFlux() khi:

- 404 có nghĩa là Optional.empty().
- 204 không có body và cần xử lý riêng.
- 202 trả về một schema khác với 200.
- Cần đọc header như Location, Retry-After hoặc ETag trước khi quyết định.
- Một số status cần parse body, một số status cần bỏ body.
- Cần trả kiểu kết quả khác nhau tùy status.

### Quy tắc giải phóng body

Với exchangeToMono()/exchangeToFlux(), callback phải xử lý body phù hợp. Nếu không đọc body, hãy release body hoặc trả publisher để framework quản lý việc giải phóng theo lifecycle API. Đừng giữ ClientResponse rồi dùng nó sau khi publisher callback đã hoàn tất; response body có thể đã được giải phóng.

## 10. Ánh xạ lỗi HTTP khác với lỗi transport và codec

onStatus không phải nơi xử lý mọi lỗi khi gọi HTTP.

### HTTP error response

Server đã trả response, ví dụ 404, 429 hoặc 503. onStatus có thể ánh xạ các status này thành exception riêng.

### Network/connectivity error

Không có response status nếu DNS thất bại, kết nối bị từ chối hoặc connection reset trước khi nhận headers. Những lỗi này thường xuất hiện dưới WebClientRequestException hoặc exception connector.

Có thể xử lý riêng:

~~~java
return catalogClient.findById(id)
    .onErrorMap(
        WebClientRequestException.class,
        error -> new CatalogConnectionException(error));
~~~

Không chuyển mọi lỗi thành ProductNotFoundException hoặc CatalogUnavailableException chỉ vì chúng phát sinh trong cùng một lời gọi.

### Timeout

Timeout có thể được đặt ở Reactor pipeline:

~~~java
return catalogClient.findById(id)
    .timeout(Duration.ofSeconds(3));
~~~

Timeout của publisher khác với HTTP 504 do server trả về. Một bên là thời gian chờ ở client; bên kia là response status từ server/proxy.

### Codec/decoding error

Nếu server trả 200 nhưng body không phải JSON hợp lệ cho Product, decoder phát lỗi. onStatus không chạy vì status không phải error. Hãy xử lý lỗi decode ở boundary nếu ứng dụng cần một exception domain riêng, nhưng giữ nguyên thông tin nguyên nhân để điều tra.

## 11. Retry có điều kiện và Retry-After

Không nên retry mọi lỗi HTTP. Một số status phản ánh lỗi vĩnh viễn hoặc request sai:

- 400: request không hợp lệ; gửi lại nguyên request thường không giúp ích.
- 401/403: cần thay đổi credential hoặc quyền.
- 404: tài nguyên không tồn tại.
- 409: cần giải quyết conflict.
- 429: có thể retry sau khoảng thời gian server yêu cầu.
- 5xx: có thể là lỗi tạm thời, nhưng không phải mọi 5xx đều an toàn để retry.

Retry còn phụ thuộc HTTP method và idempotency. GET thường an toàn hơn POST; POST có thể tạo side effect trùng nếu request đã tới server nhưng response bị mất. Chỉ retry POST khi API hỗ trợ idempotency key hoặc có semantics replay rõ ràng.

Ví dụ retry chọn lọc cho GET:

~~~java
return catalogClient.findById(id)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(CatalogUnavailableException.class::isInstance));
~~~

Ví dụ này chỉ retry lỗi đã được ánh xạ thành CatalogUnavailableException. Không retry ProductNotFoundException hoặc lỗi 4xx khác.

Với 429, hãy đọc Retry-After từ headers. Header có thể biểu diễn số giây hoặc một HTTP-date. Client nên tôn trọng thời điểm retry do server cung cấp, áp dụng giới hạn retry tối đa và jitter phù hợp. Không dùng backoff ngắn cố định để bỏ qua Retry-After.

Ngoài ra, cần đặt timeout tổng cho request và giới hạn số lần retry. Retry không giới hạn có thể làm tăng tải lên một upstream vốn đang gặp sự cố.

## 12. Ánh xạ exception ở client boundary và API boundary

Một WebClient client thường nằm trong service gọi hệ thống từ xa. Nó ánh xạ lỗi HTTP thành exception nội bộ:

~~~text
Remote HTTP response
        |
        v
WebClient onStatus()
        |
        v
Domain / integration exception
        |
        v
Application service
        |
        v
Controller / API boundary
        |
        v
HTTP response của ứng dụng hiện tại
~~~

Ví dụ upstream trả 404 ProductNotFound. Ứng dụng hiện tại có thể:

- Trả 404 nếu API của mình cũng mô hình hóa tài nguyên đó.
- Trả 502 nếu lỗi có nghĩa một dependency bên ngoài không đáp ứng hợp đồng.
- Trả một kết quả nghiệp vụ khác nếu domain quy định product không tồn tại là một trạng thái bình thường.

Không tự động sao chép status từ upstream sang client cuối. Status của API hiện tại phải phản ánh hợp đồng và trách nhiệm của API hiện tại.

Có thể dùng @RestControllerAdvice để ánh xạ domain exception thành response của ứng dụng. Hãy giữ chi tiết raw upstream response trong log có kiểm soát, không trả stack trace hoặc body nhạy cảm cho client cuối.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này xây dựng CatalogClient gọi một catalog service từ xa. Nó:

- Trả Product khi upstream trả 200.
- Ánh xạ 404 thành ProductNotFoundException.
- Ánh xạ 429 thành CatalogRateLimitedException và giữ Retry-After.
- Ánh xạ 5xx thành CatalogUnavailableException.
- Ánh xạ 4xx còn lại thành CatalogClientException.
- Cung cấp findOptional() để 404 trở thành Optional.empty() bằng exchangeToMono().

### Cấu trúc project

~~~text
webclient-status-demo/
├── pom.xml
└── src
    ├── main/java/com/example/catalog
    │   ├── CatalogDemoApplication.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── Product.java
    │   └── CatalogExceptions.java
    └── test/java/com/example/catalog
        └── CatalogClientTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webclient-status-demo</artifactId>
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

Spring Boot 3.3.5 quản lý phiên bản Spring Framework và Reactor tương thích. MockWebServer 4.12.0 chỉ dùng trong test để mô phỏng HTTP server từ xa.

### Product.java

~~~java
package com.example.catalog;

public record Product(String id, String name) {
}
~~~

### CatalogExceptions.java

~~~java
package com.example.catalog;

import org.springframework.http.HttpStatusCode;

class ProductNotFoundException extends RuntimeException {
    private final String productId;

    ProductNotFoundException(String productId, Throwable cause) {
        super("Product not found: " + productId, cause);
        this.productId = productId;
    }

    String getProductId() {
        return productId;
    }
}

class CatalogRateLimitedException extends RuntimeException {
    private final String retryAfter;

    CatalogRateLimitedException(String retryAfter, Throwable cause) {
        super("Catalog rate limit exceeded", cause);
        this.retryAfter = retryAfter;
    }

    String getRetryAfter() {
        return retryAfter;
    }
}

class CatalogUnavailableException extends RuntimeException {
    private final HttpStatusCode statusCode;

    CatalogUnavailableException(
            HttpStatusCode statusCode,
            Throwable cause) {
        super("Catalog service is unavailable", cause);
        this.statusCode = statusCode;
    }

    HttpStatusCode getStatusCode() {
        return statusCode;
    }
}

class CatalogClientException extends RuntimeException {
    private final HttpStatusCode statusCode;

    CatalogClientException(
            HttpStatusCode statusCode,
            Throwable cause) {
        super("Catalog rejected the request", cause);
        this.statusCode = statusCode;
    }

    HttpStatusCode getStatusCode() {
        return statusCode;
    }
}
~~~

Các exception giữ cause là WebClientResponseException để có thể điều tra status, headers và body gốc ở tầng tích hợp. Không trả nguyên cause cho API caller.

### CatalogClient.java

~~~java
package com.example.catalog;

import java.util.Optional;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Product> findById(String productId) {
        return webClient.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                HttpStatusCode::is4xxClientError,
                response -> response.createException()
                    .map(error -> mapError(productId, error)))
            .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> response.createException()
                    .map(error -> mapError(productId, error)))
            .bodyToMono(Product.class);
    }

    public Mono<Optional<Product>> findOptional(String productId) {
        return webClient.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty());
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                        .thenReturn(Optional.empty());
                }

                return response.createException()
                    .flatMap(error ->
                        Mono.<Optional<Product>>error(
                            mapError(productId, error)));
            });
    }

    private RuntimeException mapError(
            String productId,
            WebClientResponseException error) {

        int status = error.getStatusCode().value();

        if (status == 404) {
            return new ProductNotFoundException(productId, error);
        }

        if (status == 429) {
            String retryAfter =
                error.getHeaders().getFirst(HttpHeaders.RETRY_AFTER);

            return new CatalogRateLimitedException(retryAfter, error);
        }

        if (error.getStatusCode().is5xxServerError()) {
            return new CatalogUnavailableException(
                error.getStatusCode(), error);
        }

        return new CatalogClientException(
            error.getStatusCode(), error);
    }
}
~~~

Điểm quan trọng:

1. findById() dùng retrieve() và hai onStatus handler để phân biệt 4xx với 5xx.
2. createException() thu status, headers và raw body vào WebClientResponseException trước khi map sang exception riêng.
3. mapError() phân loại 404, 429, 5xx và các 4xx khác.
4. findOptional() dùng exchangeToMono() để xử lý 404 thành Optional.empty(); releaseBody() bảo đảm body lỗi không bị cố decode thành Product.
5. Body thành công chỉ được decode sau khi status handler không chuyển response thành exception.

### CatalogClientConfiguration.java

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        String baseUrl = System.getProperty(
            "catalog.base-url", "http://localhost:8081");
        return builder.baseUrl(baseUrl).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

Base URL có thể được truyền qua system property khi khởi động, ví dụ -Dcatalog.base-url=https://catalog.example. Trong production, cấu hình endpoint và credential bằng cơ chế quản lý cấu hình/secret phù hợp; không hardcode credential trong source code.

### CatalogDemoApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }
}
~~~

### CatalogClientTests.java

~~~java
package com.example.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

class CatalogClientTests {

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
    void returnsProductForSuccessfulResponse() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectNext(new Product("p-1", "Keyboard"))
            .verifyComplete();

        RecordedRequest request = server.takeRequest();
        assertEquals("GET", request.getMethod());
        assertEquals("/products/p-1", request.getPath());
    }

    @Test
    void maps404ToProductNotFound() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"NOT_FOUND\"}"));

        StepVerifier.create(client.findById("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }

    @Test
    void maps5xxToCatalogUnavailable() {
        server.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"temporarily unavailable\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectErrorSatisfies(error -> {
                CatalogUnavailableException mapped =
                    assertInstanceOf(
                        CatalogUnavailableException.class, error);
                assertEquals(503, mapped.getStatusCode().value());
            })
            .verify();
    }

    @Test
    void maps429AndPreservesRetryAfter() {
        server.enqueue(new MockResponse()
            .setResponseCode(429)
            .addHeader("Retry-After", "5")
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"RATE_LIMITED\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectErrorSatisfies(error -> {
                CatalogRateLimitedException mapped =
                    assertInstanceOf(
                        CatalogRateLimitedException.class, error);
                assertEquals("5", mapped.getRetryAfter());
            })
            .verify();
    }

    @Test
    void mapsOther4xxToCatalogClientException() {
        server.enqueue(new MockResponse()
            .setResponseCode(400)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"INVALID_QUERY\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectError(CatalogClientException.class)
            .verify();
    }

    @Test
    void treats404AsEmptyWhenUsingOptionalContract() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"NOT_FOUND\"}"));

        StepVerifier.create(client.findOptional("missing"))
            .expectNext(Optional.empty())
            .verifyComplete();
    }
}
~~~

Chạy test tại thư mục có pom.xml:

~~~bash
mvn -q test
~~~

Nếu sáu test pass, Maven kết thúc với exit code 0. MockWebServer cho phép kiểm tra request thật mà WebClient gửi và mô phỏng status/body của upstream mà không cần chạy một dịch vụ catalog riêng.

## 14. Kiểm tra body lỗi và giới hạn bộ nhớ

createException() phải thu response body để tạo WebClientResponseException. Vì vậy, error body cũng chịu giới hạn bộ nhớ của codec. Nếu upstream trả một body lỗi quá lớn, quá trình đọc có thể phát DataBufferLimitException trước khi hoàn thành exception mapping.

Có thể cấu hình giới hạn cho WebClient:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("https://catalog.example")
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(256 * 1024))
    .build();
~~~

256 KiB chỉ là ví dụ. Chọn giới hạn dựa trên kích thước response/error body hợp lệ và mức concurrency. Không tăng giới hạn vô hạn chỉ để tránh lỗi; một upstream lỗi có thể trả payload rất lớn và làm cạn bộ nhớ client.

Nếu chỉ cần status và headers, cân nhắc bỏ qua body hoặc dùng exchangeToMono() với releaseBody(). Nếu cần ghi log body, giới hạn độ dài và loại bỏ thông tin nhạy cảm.

## 15. Logging và bảo mật khi ánh xạ lỗi

Error body của upstream có thể chứa:

- Thông tin nội bộ về database hoặc stack trace.
- Token, query hoặc dữ liệu người dùng.
- HTML từ proxy/gateway.
- Nội dung không đúng schema mà ứng dụng kỳ vọng.

Không trả nguyên getResponseBodyAsString() cho client cuối. Hãy log có kiểm soát:

- Tên upstream và route.
- Status HTTP.
- Correlation ID hoặc trace ID.
- Mã lỗi nghiệp vụ đã parse được.
- Request ID từ upstream nếu có.
- Một đoạn body đã được redact và giới hạn độ dài nếu thật sự cần.

Không ghi Authorization, Cookie, API key, raw request body hoặc response body nhạy cảm. Exception nội bộ có thể giữ cause để debug, nhưng serializer không nên tự động biến toàn bộ cause thành response JSON.

## 16. Lỗi thường gặp và cách khắc phục

1. **Cho rằng retrieve() tự trả exception nghiệp vụ.** Mặc định nó trả WebClientResponseException cho 4xx/5xx; dùng onStatus để ánh xạ.
2. **Chỉ kiểm tra status trong bodyToMono().** Khi status lỗi, body reader có thể không chạy vì retrieve đã chuyển response thành exception. Đăng ký handler trước bodyToMono.
3. **Callback onStatus trả exception trực tiếp.** Callback cần trả Mono<? extends Throwable>; dùng Mono.error(...) hoặc createException().map(...).
4. **Gọi block() trong onStatus.** Điều này chặn reactive pipeline. Compose publisher bằng map/flatMap.
5. **Đặt handler 4xx tổng quát trước 404.** Handler cụ thể phía sau có thể không được gọi. Đặt predicate cụ thể trước predicate rộng.
6. **Nghĩ Mono.empty() nghĩa là bỏ body.** Nó chỉ ngăn response bị chuyển thành exception; body vẫn được xử lý bởi bodyToMono/bodyToFlux phía sau.
7. **Nghĩ Mono.empty() tự tạo Optional.empty().** Muốn 404 thành empty, dùng exchangeToMono(), releaseBody() rồi trả Optional.empty().
8. **Đọc response body hai lần.** Body là stream một lần đọc. Chọn createException() hoặc bodyToMono(ErrorDto.class), không tiêu thụ cả hai trên cùng body.
9. **Giả định error body luôn là JSON.** Proxy có thể trả HTML hoặc text; createException() giữ raw body an toàn hơn khi schema không chắc chắn.
10. **Ánh xạ mọi 4xx thành lỗi giống nhau.** 404, 409, 429 và 401/403 có semantics khác nhau; chỉ tạo exception riêng khi cách xử lý khác.
11. **Dùng onStatus để xử lý DNS hoặc connection refused.** Không có ClientResponse khi request không nhận được HTTP response. Xử lý WebClientRequestException riêng.
12. **Dùng onStatus để xử lý JSON sai cú pháp trong response 200.** Đây là lỗi codec/decode, không phải status error.
13. **Retry mọi exception.** Có thể retry lỗi vĩnh viễn hoặc tạo side effect trùng. Chỉ retry lỗi tạm thời và thao tác idempotent.
14. **Bỏ qua Retry-After.** Với 429, hãy đọc và tôn trọng khoảng chờ server yêu cầu.
15. **Trả raw upstream body cho caller.** Có thể làm lộ thông tin nội bộ; trả error code/message đã chuẩn hóa.
16. **Không đặt giới hạn error body.** Body lỗi lớn có thể tiêu thụ nhiều bộ nhớ; cấu hình maxInMemorySize phù hợp.
17. **Dùng exchangeToMono() nhưng quên xử lý body.** Hãy decode hoặc release body theo từng nhánh.
18. **Giữ ClientResponse để dùng sau khi callback kết thúc.** Response/body có lifecycle giới hạn; hãy chuyển thành domain value hoặc exception ngay trong callback.
19. **Đồng nhất status upstream với status API của mình.** API boundary phải áp dụng hợp đồng của chính ứng dụng.
20. **Chỉ unit test hàm mapError.** Nên kiểm thử cả HTTP response, body, status handler và request thực tế bằng MockWebServer.

## 17. Checklist thiết kế WebClient error mapping

Trước khi phát hành một HTTP client, hãy xác định:

- **Success schema:** response 2xx được decode thành kiểu nào?
- **Default behavior:** 4xx/5xx chưa có handler sẽ trở thành exception nào?
- **Status mapping:** status nào có exception nghiệp vụ riêng?
- **Handler order:** predicate cụ thể có đứng trước predicate tổng quát?
- **Error body:** schema có ổn định không, có thể rỗng hoặc HTML không?
- **Body ownership:** callback có tiêu thụ body đúng một lần không?
- **Empty semantics:** 404 là lỗi, Optional.empty() hay một kết quả domain khác?
- **Alternative API:** retrieve() đủ dùng hay cần exchangeToMono()/exchangeToFlux()?
- **Raw status:** upstream có status mở rộng cần onRawStatus() không?
- **Transport errors:** DNS, connection, timeout được xử lý riêng chưa?
- **Codec errors:** malformed JSON và DataBufferLimitException có được quan sát không?
- **Retry:** chỉ retry lỗi tạm thời và thao tác có idempotency?
- **Rate limit:** có đọc Retry-After và giới hạn số lần retry?
- **Security:** log/response đã loại bỏ token, PII và stack trace?
- **Testing:** MockWebServer xác minh 2xx, 404, 429, 5xx, 4xx khác và optional 404?

## 18. Bài tập tự kiểm tra

**Bài 1.** retrieve() nhận status 404 và không có onStatus handler. Exception mặc định thường là gì?  
**Đáp án:** WebClientResponseException.NotFound, là subclass của WebClientResponseException.

**Bài 2.** onStatus nhận tham số nào?  
**Đáp án:** Một Predicate<HttpStatusCode> để chọn status và một Function<ClientResponse, Mono<? extends Throwable>> để tạo exception.

**Bài 3.** Vì sao callback onStatus trả Mono của exception?  
**Đáp án:** Vì việc đọc response body là bất đồng bộ và cần được compose vào reactive pipeline.

**Bài 4.** onStatus handler trả Mono.empty() có nghĩa gì?  
**Đáp án:** Response không bị chuyển thành exception; body tiếp tục được xử lý bởi bodyToMono/bodyToFlux phía sau.

**Bài 5.** Muốn 404 thành Optional.empty(), nên dùng cách nào?  
**Đáp án:** Dùng exchangeToMono(), kiểm tra status 404, releaseBody() rồi trả Optional.empty().

**Bài 6.** createException() có lợi ích gì?  
**Đáp án:** Nó tạo WebClientResponseException chứa status, headers, request và raw response body, kể cả khi body không phải JSON chuẩn.

**Bài 7.** onStatus có xử lý DNS failure không?  
**Đáp án:** Không. Không có HTTP response nên không có status; xử lý WebClientRequestException hoặc lỗi connector.

**Bài 8.** Response trả 200 nhưng JSON sai cú pháp thì sao?  
**Đáp án:** Codec phát lỗi decode; onStatus không chạy vì status không phải lỗi HTTP.

**Bài 9.** Vì sao handler 404 nên đặt trước handler 4xx tổng quát?  
**Đáp án:** Handler đầu tiên có predicate khớp được áp dụng; predicate tổng quát đặt trước sẽ bắt cả 404.

**Bài 10.** Có nên retry 404 không?  
**Đáp án:** Thông thường không; tài nguyên không tồn tại là lỗi không tạm thời. Chỉ retry nếu domain có semantics đặc biệt.

**Bài 11.** 429 thường cung cấp header nào để hướng dẫn retry?  
**Đáp án:** Retry-After; giá trị có thể là số giây hoặc HTTP-date.

**Bài 12.** Vì sao không trả raw response body của upstream cho người dùng?  
**Đáp án:** Body có thể chứa thông tin nội bộ, dữ liệu nhạy cảm hoặc stack trace; hãy chuẩn hóa thành mã lỗi an toàn.

## 19. Ghi nhớ

retrieve() mặc định chuyển response 4xx/5xx thành WebClientResponseException. onStatus() cho phép chọn status bằng Predicate<HttpStatusCode> và ánh xạ ClientResponse thành Mono exception. createException() là lựa chọn tổng quát khi cần giữ status, headers và raw body; bodyToMono(ErrorDto.class) phù hợp khi upstream có schema lỗi ổn định.

Mono.empty() từ onStatus chỉ bỏ việc chuyển response thành exception; nó không tự bỏ body hoặc tạo Optional.empty(). Khi cần coi 404 là kết quả vắng mặt, exchangeToMono() giúp phân nhánh status, release body và trả giá trị phù hợp.

onStatus chỉ xử lý HTTP response status. DNS, connection, timeout và decode errors thuộc các nhóm khác. Retry cần dựa trên loại lỗi, idempotency và Retry-After. Cuối cùng, ánh xạ lỗi upstream thành domain exception ở client boundary, rồi để API boundary quyết định status và message phù hợp với hợp đồng của ứng dụng.

### Tài liệu tham khảo

- Spring Framework, [WebClient – retrieve() and exchangeToMono()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
- Spring Framework, [WebClient – Request and Response Body](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html).
- Spring Framework Javadoc, [WebClient.ResponseSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Framework Javadoc, [ClientResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html).
- Spring Framework Javadoc, [WebClientResponseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html).
- Spring Framework, [WebClient Configuration and Codecs](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- OkHttp, [MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/okhttp3.mockwebserver/).
