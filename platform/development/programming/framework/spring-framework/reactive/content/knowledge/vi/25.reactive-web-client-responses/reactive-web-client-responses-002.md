# toEntity và truy cập status, header cùng body trong Spring WebClient

## 1. Vì sao cần toEntity?

Khi gọi HTTP bằng Spring WebClient, đôi khi chỉ lấy nội dung body là chưa đủ. Ứng dụng còn cần biết server trả status nào, gửi những header nào, có ETag hoặc correlation ID hay không, và body được decode thành kiểu Java nào.

`retrieve().bodyToMono(Product.class)` trả về publisher của body đã decode. Cách này gọn khi chỉ quan tâm dữ liệu.

`retrieve().toEntity(Product.class)` trả về `Mono<ResponseEntity<Product>>`. ResponseEntity gom ba phần của HTTP response:

- **Status:** mã trạng thái HTTP, ví dụ 200, 201, 206 hoặc 404.
- **Headers:** metadata như Content-Type, ETag, Location, Cache-Control, Retry-After và X-Request-Id.
- **Body:** nội dung đã được codec decode thành kiểu Java được yêu cầu.

Ví dụ chính thức:

~~~java
Mono<ResponseEntity<Person>> result = client.get()
    .uri("/persons/{id}", id)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .toEntity(Person.class);
~~~

Đây vẫn là reactive API. Request không được thực thi chỉ vì đã gọi `retrieve()`; việc thực thi diễn ra khi publisher được subscribe. Không gọi `block()` trong controller hoặc service reactive.

**Khi nào nên dùng toEntity?** Khi quyết định nghiệp vụ cần kết hợp status, header và body trong cùng một kết quả: xử lý ETag, đọc Location sau khi tạo resource, phân tích Retry-After, ghi nhận request ID, hoặc chuyển tiếp status/header từ upstream trong một API gateway.

## 2. ResponseEntity<T> gồm những gì?

`ResponseEntity<T>` là một kiểu response có status, headers và body. Với WebClient, nó biểu diễn response nhận được từ server sau khi body đã được decode.

~~~java
ResponseEntity<Product> response = ...;

HttpStatusCode status = response.getStatusCode();
int statusValue = status.value();

HttpHeaders headers = response.getHeaders();
String requestId = headers.getFirst("X-Request-Id");
MediaType contentType = headers.getContentType();

Product body = response.getBody();
~~~

Các API quan trọng:

| API | Giá trị trả về | Mục đích |
| --- | --- | --- |
| `getStatusCode()` | `HttpStatusCode` | Lấy status theo abstraction của Spring |
| `getStatusCode().value()` | `int` | Lấy mã số HTTP |
| `getHeaders()` | `HttpHeaders` | Đọc headers của response |
| `getBody()` | `T` | Lấy body đã decode |
| `hasBody()` | `boolean` | Kiểm tra response entity có body hay không |
| `getStatusCode().is2xxSuccessful()` | `boolean` | Kiểm tra nhóm status 2xx |
| `getStatusCode().is4xxClientError()` | `boolean` | Kiểm tra nhóm status 4xx |
| `getStatusCode().is5xxServerError()` | `boolean` | Kiểm tra nhóm status 5xx |

Dùng `HttpStatusCode` thay vì giả định mọi status đều là một hằng `HttpStatus` đã biết. HTTP có thể có status code mở rộng; `value()` luôn cho phép lấy mã số.

Headers trả về từ response entity nên được xem là dữ liệu chỉ đọc. Nếu cần tạo response mới, hãy copy các header được phép sang entity mới; không dựa vào việc sửa trực tiếp header của entity nhận được.

## 3. Đọc status, headers và body trong cùng một pipeline

Ví dụ client lấy sản phẩm và ghi nhận status, ETag, request ID cùng body:

~~~java
Mono<ProductSnapshot> snapshot = webClient.get()
    .uri("/products/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .toEntity(Product.class)
    .map(response -> {
        int status = response.getStatusCode().value();
        String etag = response.getHeaders().getETag();
        String requestId =
            response.getHeaders().getFirst("X-Request-Id");

        Product product = response.getBody();

        return new ProductSnapshot(
            status,
            etag,
            requestId,
            product
        );
    });
~~~

DTO dùng cho ví dụ:

~~~java
public record Product(
    long id,
    String name,
    BigDecimal price
) {
}

public record ProductSnapshot(
    int status,
    String etag,
    String requestId,
    Product product
) {
}
~~~

`map` chỉ chuyển đổi giá trị đã có trong publisher. Nếu việc xử lý body cần gọi thêm service bất đồng bộ, dùng `flatMap`:

~~~java
Mono<ProductView> view = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .flatMap(response -> {
        Product product = response.getBody();

        if (product == null) {
            return Mono.error(
                new IllegalStateException("Product response has no body")
            );
        }

        String requestId =
            response.getHeaders().getFirst("X-Request-Id");

        return auditService.record(
                response.getStatusCode(),
                requestId
            )
            .thenReturn(new ProductView(
                response.getStatusCode().value(),
                product
            ));
    });
~~~

Không dùng `block()` để lấy ResponseEntity rồi mới xử lý. Giữ toàn bộ chuỗi trong Mono giúp WebFlux quản lý subscription, lỗi và cancellation.

## 4. Ví dụ GET với toEntity

~~~java
Mono<ResponseEntity<Product>> getProduct(long id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntity(Product.class);
}
~~~

Khi subscribe, WebClient gửi GET request. JSON response được codec decode thành `Product`, còn status và headers được đặt trong ResponseEntity.

Giả sử server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v3"
X-Request-Id: req-7f21

{"id":42,"name":"Keyboard","price":79.90}
~~~

Có thể đọc:

~~~java
response.getStatusCode().value();              // 200
response.getHeaders().getETag();                // "product-42-v3"
response.getHeaders().getFirst("X-Request-Id"); // req-7f21
response.getBody().name();                      // Keyboard
~~~

Giá trị minh họa cho thấy body là object Java sau decode, không còn là raw JSON string. Nếu cần raw body để debug, có thể đọc thành `String.class` hoặc xử lý lỗi bằng `WebClientResponseException`; không thể đọc lại cùng response body như một stream độc lập sau khi đã tiêu thụ.

## 5. Phân biệt bodyToMono và toEntity

Hai cách này đều decode response body, nhưng trả về dữ liệu khác nhau:

~~~java
Mono<Product> bodyOnly = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class);

Mono<ResponseEntity<Product>> withMetadata = webClient.get()
    .uri("/products/42")
    .retrieve()
    .toEntity(Product.class);
~~~

| Tiêu chí | `bodyToMono(Product.class)` | `toEntity(Product.class)` |
| --- | --- | --- |
| Body đã decode | Có | Có |
| Status code | Không nằm trong kết quả | Có |
| Response headers | Không nằm trong kết quả | Có |
| Kiểu publisher | `Mono<Product>` | `Mono<ResponseEntity<Product>>` |
| Phù hợp | Chỉ cần dữ liệu | Cần cả metadata HTTP và dữ liệu |

Nếu service cần kiểm tra ETag, Location, Retry-After hoặc status, `toEntity` thường rõ ràng hơn. Nếu chỉ cần Product để tính toán nghiệp vụ, `bodyToMono` giảm một lớp wrapper.

Cả hai đều tiêu thụ body response theo cách tương ứng. Không gọi `bodyToMono` sau khi đã gọi `toEntity` trên cùng một response để mong đọc body lần thứ hai.

## 6. Trạng thái 4xx/5xx: điểm dễ nhầm nhất

Mặc định, `retrieve()` chuyển response status thuộc nhóm 4xx hoặc 5xx thành lỗi `WebClientResponseException`. Điều này vẫn đúng khi terminal operation là `toEntity`.

Ví dụ:

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class);
~~~

Nếu server trả 404, publisher mặc định phát lỗi `WebClientResponseException.NotFound`; ứng dụng không nhận được ResponseEntity để gọi `getStatusCode()` trong nhánh success.

Vì vậy, nếu muốn xem 404 như một kết quả HTTP bình thường, cần tùy chỉnh status handler.

### 6.1. Giữ 404 như một ResponseEntity

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.empty()
    )
    .toEntity(Product.class);
~~~

Khi status là 404, callback trả `Mono.empty()` để không chuyển status đó thành exception. Response được chuyển tiếp cho bước xử lý tiếp theo và `toEntity` có thể trả về ResponseEntity với status 404.

Nếu response 404 không có body, `getBody()` có thể là null. Hãy kiểm tra trước khi truy cập field:

~~~java
return result.map(response -> {
    if (response.getStatusCode().value() == 404) {
        return ProductLookup.notFound();
    }

    Product product = response.getBody();
    return product == null
        ? ProductLookup.empty()
        : ProductLookup.found(product);
});
~~~

Chỉ suppress 404 khi đó là một nhánh nghiệp vụ có chủ đích. Nếu error body của 404 chứa JSON không tương thích với `Product`, decode body theo Product vẫn có thể thất bại. Khi cần đọc error representation, hãy decode thành error DTO hoặc xử lý bằng `exchangeToMono`.

### 6.2. Chuyển 4xx/5xx thành exception nghiệp vụ

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                response.statusCode().value(),
                body
            ))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                response.statusCode().value(),
                body
            ))
    )
    .toEntity(Product.class);
~~~

Exception đơn giản:

~~~java
public class RemoteApiException extends RuntimeException {
    private final int status;
    private final String responseBody;

    public RemoteApiException(int status, String responseBody) {
        super("Remote API returned HTTP " + status);
        this.status = status;
        this.responseBody = responseBody;
    }

    public int getStatus() {
        return status;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
~~~

Trong callback `onStatus`, body error được tiêu thụ thành String để tạo exception. Vì callback phát lỗi, `toEntity` không tạo ResponseEntity success. Chọn một representation lỗi ổn định thay vì trả raw body có thể chứa thông tin nhạy cảm ra API công khai.

### 6.3. Đọc WebClientResponseException

Nếu giữ cách xử lý mặc định, có thể bắt lỗi ở downstream:

~~~java
return webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .onErrorResume(
        WebClientResponseException.class,
        error -> {
            log.warn(
                "Remote status={}, body={}",
                error.getStatusCode().value(),
                error.getResponseBodyAsString()
            );
            return Mono.error(error);
        }
    );
~~~

`WebClientResponseException` cung cấp status code, response headers và response body đã lưu dưới dạng bytes. Không log toàn bộ body nếu nó có thể chứa token, dữ liệu cá nhân hoặc thông tin bí mật.

## 7. Đọc headers thường gặp

Response headers giúp ứng dụng hiểu metadata và điều khiển hành vi tiếp theo.

| Header | API đọc | Ý nghĩa |
| --- | --- | --- |
| Content-Type | `getContentType()` | Kiểu dữ liệu của response body |
| Content-Length | `getContentLength()` | Độ dài body nếu server cung cấp |
| ETag | `getETag()` | Validator cho representation |
| Last-Modified | `getLastModified()` | Thời điểm representation được sửa |
| Location | `getLocation()` | URI resource liên quan, thường dùng với 201/redirect |
| Cache-Control | `getCacheControl()` | Chính sách cache |
| Retry-After | `getFirst("Retry-After")` | Gợi ý thời gian thử lại |
| X-Request-Id | `getFirst("X-Request-Id")` | Correlation/request identifier do server cung cấp |

Ví dụ đọc Location và ETag:

~~~java
return webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Mouse", new BigDecimal("25.50")))
    .retrieve()
    .toEntity(Product.class)
    .map(response -> {
        URI location = response.getHeaders().getLocation();
        String etag = response.getHeaders().getETag();
        Product created = response.getBody();

        return new CreatedProduct(
            response.getStatusCode(),
            location,
            etag,
            created
        );
    });
~~~

Status 201 và Location thường cho biết resource mới được tạo ở đâu. Không giả định mọi server đều gửi Location; kiểm tra null trước khi dùng.

### 7.1. Header có nhiều giá trị

Một header có thể chứa nhiều giá trị. Dùng `get(name)` để lấy danh sách hoặc `getFirst(name)` khi contract quy định chỉ cần giá trị đầu tiên:

~~~java
List<String> warnings =
    response.getHeaders().get("Warning");

String requestId =
    response.getHeaders().getFirst("X-Request-Id");
~~~

Không nối tùy tiện các header nhiều giá trị thành một chuỗi nếu quy tắc của header yêu cầu xử lý từng giá trị riêng.

### 7.2. Header có thể bị giới hạn bởi CORS

Nếu WebClient chạy ở server, ứng dụng Java đọc được các response headers mà server gửi về. Nếu JavaScript trong browser gọi API trực tiếp, browser chỉ cho JavaScript truy cập một số response headers được expose qua CORS.

Với browser client cần đọc header tùy chỉnh, server phải cấu hình `Access-Control-Expose-Headers`, ví dụ:

~~~http
Access-Control-Expose-Headers: ETag, X-Request-Id, Retry-After
~~~

Đây là giới hạn của browser CORS, không phải giới hạn của `ResponseEntity` trong Java server-side WebClient.

## 8. Generic body: ParameterizedTypeReference

Java type erasure khiến `List<Product>.class` không tồn tại. Khi body có generic lồng nhau, dùng `ParameterizedTypeReference<T>` để giữ type information cho codec.

Ví dụ response:

~~~json
{
  "data": [
    {"id": 1, "name": "Keyboard", "price": 79.90},
    {"id": 2, "name": "Mouse", "price": 25.50}
  ],
  "page": 1,
  "total": 2
}
~~~

DTO:

~~~java
public record PageResult<T>(
    List<T> data,
    int page,
    int total
) {
}
~~~

WebClient:

~~~java
ParameterizedTypeReference<PageResult<Product>> type =
    new ParameterizedTypeReference<>() {};

Mono<ResponseEntity<PageResult<Product>>> result =
    webClient.get()
        .uri("/products?page=1")
        .retrieve()
        .toEntity(type);
~~~

Không dùng `PageResult.class` nếu muốn decoder biết chính xác generic argument là Product. Nếu chỉ cần một danh sách phần tử cùng kiểu, `toEntityList(Product.class)` là API tiện dụng hơn.

## 9. toEntityList: lấy ResponseEntity<List<T>>

Khi server trả một JSON array hữu hạn và ứng dụng cần cả metadata HTTP, dùng `toEntityList`:

~~~java
Mono<ResponseEntity<List<Product>>> result =
    webClient.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntityList(Product.class);
~~~

Kết quả có status code, response headers và danh sách Product đã decode.

`toEntityList` cần aggregate các phần tử thành List. Không dùng cho một feed không giới hạn hoặc response rất lớn nếu có thể xử lý từng phần tử bằng streaming.

Nếu response là wrapper như `PageResult<Product>`, dùng `toEntity(ParameterizedTypeReference)` thay vì `toEntityList`.

## 10. toBodilessEntity: chỉ cần status và headers

Một số endpoint không trả body, ví dụ DELETE thành công với 204 No Content hoặc request chỉ cần biết status và Location.

~~~java
Mono<ResponseEntity<Void>> deleteProduct(String id) {
    return webClient.delete()
        .uri("/products/{id}", id)
        .retrieve()
        .toBodilessEntity();
}
~~~

`toBodilessEntity()` trả status và headers trong ResponseEntity<Void>, đồng thời giải phóng/tiêu thụ response body theo contract của API này. Đây là lựa chọn phù hợp khi không cần decode body.

Không dùng `toEntity(String.class)` chỉ để bỏ qua body nếu mục đích là lấy metadata; `toBodilessEntity` thể hiện rõ ý định hơn.

## 11. toEntityFlux: giữ body dạng stream

Khi response body là một stream lớn hoặc không giới hạn, có thể dùng `toEntityFlux`:

~~~java
Mono<ResponseEntity<Flux<Product>>> result =
    webClient.get()
        .uri("/products/stream")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .toEntityFlux(Product.class);
~~~

Kết quả bên ngoài là Mono vì status và headers được xác định khi nhận response. Body bên trong vẫn là Flux để tiêu thụ từng Product.

Ví dụ:

~~~java
return result.flatMapMany(entity -> {
    log.info(
        "Stream status={}, requestId={}",
        entity.getStatusCode().value(),
        entity.getHeaders().getFirst("X-Request-Id")
    );

    Flux<Product> body = entity.getBody();
    return body == null ? Flux.empty() : body;
});
~~~

**Phải tiêu thụ body Flux trong thời gian phù hợp.** Response giữ tài nguyên kết nối cho tới khi body được đọc hoặc được giải phóng. Không lấy ResponseEntity<Flux<T>> rồi bỏ quên body; điều đó có thể giữ connection và tài nguyên lâu hơn dự kiến.

Khác biệt chính:

| API | Body type | Cách xử lý |
| --- | --- | --- |
| `toEntity(Product.class)` | `Product` | Decode một object |
| `toEntityList(Product.class)` | `List<Product>` | Aggregate thành list |
| `toEntityFlux(Product.class)` | `Flux<Product>` | Tiêu thụ từng phần tử |
| `toBodilessEntity()` | `Void` | Chỉ lấy status và headers |

## 12. Dùng status để điều khiển logic

Status không chỉ để log. Nó có thể quyết định nhánh nghiệp vụ tiếp theo.

~~~java
Mono<ProductLookup> lookup(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.empty()
        )
        .toEntity(Product.class)
        .map(response -> {
            if (response.getStatusCode().value() == 404) {
                return ProductLookup.notFound();
            }

            Product body = response.getBody();
            return body == null
                ? ProductLookup.empty()
                : ProductLookup.found(body);
        });
}
~~~

Ví dụ này suppress 404 có chủ đích rồi phân biệt status sau khi nhận entity. Các status 4xx khác và 5xx vẫn giữ xử lý lỗi mặc định.

Với API trả 304 Not Modified, response thường không có body mới. Client có thể dùng ETag/conditional request và xử lý status 304 riêng. Hãy xác nhận behavior của HTTP connector, cache layer và status handler trước khi thiết kế cache; không giả định 304 luôn được xử lý giống 200.

Nếu logic status phức tạp đến mức mỗi status cần một kiểu body khác nhau, cân nhắc `exchangeToMono` thay vì dồn mọi nhánh vào `onStatus`.

## 13. Khi nào dùng exchangeToMono thay cho retrieve().toEntity?

`retrieve()` phù hợp với luồng phổ biến: khai báo request, tùy chỉnh error status nếu cần, rồi decode response bằng body hoặc ResponseEntity.

`exchangeToMono` cung cấp quyền truy cập trực tiếp `ClientResponse` để chọn cách decode theo status hoặc header:

~~~java
Mono<ProductResult> result = webClient.get()
    .uri("/products/{id}", id)
    .accept(MediaType.APPLICATION_JSON)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            String requestId =
                response.headers().asHttpHeaders()
                    .getFirst("X-Request-Id");

            return response.bodyToMono(Product.class)
                .map(product ->
                    ProductResult.success(requestId, product));
        }

        if (response.statusCode().value() == 404) {
            return response.releaseBody()
                .thenReturn(ProductResult.notFound());
        }

        return response.createError();
    });
~~~

Điểm cần nhớ:

- Callback của `exchangeToMono` chịu trách nhiệm quyết định cách tiêu thụ body.
- Có thể decode body khác nhau cho 2xx, 404 hoặc các status lỗi.
- Sau khi publisher callback hoàn tất, Spring kiểm tra và release body nếu chưa được consume.
- Không trả `ClientResponse` ra ngoài rồi mong decode body ở một pipeline khác sau khi callback đã hoàn tất.
- Nếu body đã được consume trong callback, không đọc lại.

Chọn `toEntity` khi muốn một ResponseEntity đơn giản. Chọn `exchangeToMono` khi response cần logic rẽ nhánh theo status, headers hoặc representation.

## 14. Xử lý lỗi mạng và lỗi decode

Không phải mọi lỗi WebClient đều là HTTP error status.

| Loại lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| HTTP error status | 404, 429, 500 | WebClientResponseException hoặc onStatus |
| Network/connect error | DNS, connection refused, TLS | Xử lý WebClientRequestException hoặc lỗi transport |
| Timeout | Upstream phản hồi quá chậm | Đặt timeout theo SLA và phân loại timeout |
| Decode error | JSON malformed, field sai kiểu | Xử lý codec/DecodingException |
| Application error | Validation hoặc lỗi domain | Map sang exception nghiệp vụ |

Ví dụ timeout:

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .timeout(Duration.ofSeconds(3))
    .onErrorMap(
        TimeoutException.class,
        error -> new UpstreamTimeoutException("Catalog timed out", error)
    );
~~~

Timeout ở đây áp dụng cho toàn bộ Mono. Nếu cần giới hạn thời gian kết nối, response hoặc từng giai đoạn riêng, cấu hình connector/client phù hợp; Reactor timeout trên Mono không thay thế mọi timeout transport.

Không bắt mọi Throwable rồi chuyển thành `Mono.empty()`. Cách đó làm mất thông tin về lỗi HTTP, lỗi mạng, timeout và lỗi decode.

## 15. Tránh block và quản lý response body đúng cách

`toEntity` là reactive. Trong controller/service WebFlux, hãy compose publisher:

~~~java
Mono<ProductView> view =
    productClient.getProduct(id)
        .map(response -> new ProductView(
            response.getStatusCode().value(),
            response.getHeaders().getETag(),
            response.getBody()
        ));
~~~

Tránh:

~~~java
Product product = productClient.getProduct(id)
    .block()
    .getBody();
~~~

`block()` có thể chặn event-loop và làm giảm khả năng mở rộng của WebFlux. Nếu cần dùng API đồng bộ trong ứng dụng khác, hãy đặt ranh giới blocking có chủ đích; không gọi nó trong reactive request path.

Body HTTP là stream được tiêu thụ theo contract của response. `toEntity` đã decode body thành một object; không có một response stream thứ hai để đọc lại. Với `toEntityFlux`, phải subscribe/consume Flux body và để cancellation truyền về transport khi downstream dừng.

Khi cần đọc response error body, hãy dùng `onStatus` callback hoặc `WebClientResponseException`; không cố đọc cùng body ở nhiều nhánh độc lập.

## 16. Chuyển tiếp status và headers từ upstream

Một API gateway có thể muốn chuyển tiếp một phần response từ upstream:

~~~java
Mono<ResponseEntity<Product>> upstream =
    productClient.getProduct(id);
~~~

Controller có thể trả ResponseEntity để Spring ghi status, headers và body ra HTTP response của chính ứng dụng. Tuy nhiên, không nên chuyển tiếp tất cả headers một cách mù quáng.

Cần chọn header phù hợp:

- Có thể chuyển tiếp ETag, Last-Modified, Cache-Control hoặc Location khi semantics phù hợp.
- Không tùy tiện chuyển Content-Length, Transfer-Encoding, Connection hoặc các hop-by-hop headers.
- Không để lộ Set-Cookie, Server, internal trace metadata hoặc header nhạy cảm của upstream.
- Kiểm tra CORS, authentication và cache policy của API gateway.

Ví dụ tạo response mới chỉ với header được phép:

~~~java
return productClient.getProduct(id)
    .map(remote -> {
        HttpHeaders headers = new HttpHeaders();

        String etag = remote.getHeaders().getETag();
        if (etag != null) {
            headers.setETag(etag);
        }

        String requestId =
            remote.getHeaders().getFirst("X-Request-Id");
        if (requestId != null) {
            headers.set("X-Request-Id", requestId);
        }

        return new ResponseEntity<>(
            remote.getBody(),
            headers,
            remote.getStatusCode()
        );
    });
~~~

Đây là allowlist header minh họa. API gateway thực tế cần xác định header contract và xử lý body null/status không có body một cách nhất quán.

## 17. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Demo dùng Spring Boot 3.5.6, Java 17 và WebClient. Một MockWebServer trong test giả lập upstream để kiểm tra response status, headers và body mà không cần phụ thuộc API công khai.

### 17.1. Cấu trúc dự án

~~~text
webclient-to-entity-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Product.java
      ProductClient.java
    main/resources/
      application.properties
    test/java/demo/
      ProductClientTest.java
~~~

### 17.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 17.3. application.properties

~~~properties
spring.application.name=webclient-to-entity-demo
catalog.base-url=http://localhost:9090
~~~

Khi chạy test, DynamicPropertySource thay base URL bằng URL của MockWebServer.

### 17.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 17.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 17.6. ProductClient.java

~~~java
package demo;

import java.util.List;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ProductClient {
    private final WebClient webClient;

    public ProductClient(
            WebClient.Builder builder,
            Environment environment) {
        String baseUrl = environment.getRequiredProperty("catalog.base-url");
        this.webClient = builder.baseUrl(baseUrl).build();
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Product.class);
    }

    public Mono<ResponseEntity<Product>> getProductAllowing404(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> Mono.empty()
            )
            .toEntity(Product.class);
    }

    public Mono<ResponseEntity<List<Product>>> getProducts() {
        return webClient.get()
            .uri("/products")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntityList(Product.class);
    }

    public Mono<ResponseEntity<Void>> deleteProduct(String id) {
        return webClient.delete()
            .uri("/products/{id}", id)
            .retrieve()
            .toBodilessEntity();
    }

    public Mono<ResponseEntity<ProductEnvelope<List<Product>>>> getEnvelope() {
        ParameterizedTypeReference<ProductEnvelope<List<Product>>> type =
            new ParameterizedTypeReference<>() {};

        return webClient.get()
            .uri("/products/envelope")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(type);
    }

    public record ProductEnvelope<T>(
        T data,
        int total
    ) {
    }
}
~~~

Method `getProduct` là ví dụ trọng tâm: kết quả giữ status, headers và Product. `getProductAllowing404` cho thấy cách suppress riêng 404. `getProducts` minh họa list; `deleteProduct` chỉ lấy metadata; `getEnvelope` giữ generic type bằng ParameterizedTypeReference.

### 17.7. ProductClientTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductClientTest {
    private static final MockWebServer UPSTREAM = startServer();

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> UPSTREAM.url("/").toString()
        );
    }

    @AfterAll
    static void stopServer() throws IOException {
        UPSTREAM.shutdown();
    }

    @Autowired
    ProductClient client;

    @Test
    void toEntityExposesStatusHeadersAndDecodedBody() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(206)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"product-7-v2\"")
            .addHeader("X-Request-Id", "req-7")
            .setBody("""
                {"id":7,"name":"Monitor","price":199.90}
                """));

        ResponseEntity<Product> response =
            client.getProduct("7").block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(HttpStatus.PARTIAL_CONTENT, response.getStatusCode());
        assertEquals("\"product-7-v2\"", response.getHeaders().getETag());
        assertEquals("req-7",
            response.getHeaders().getFirst("X-Request-Id"));
        assertEquals(
            new Product(7, "Monitor", new BigDecimal("199.90")),
            response.getBody()
        );

        RecordedRequest request =
            UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/products/7", request.getPath());
        assertEquals(
            "application/json",
            request.getHeader("Accept")
        );
    }

    @Test
    void defaultRetrieveTreats404AsException() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "text/plain")
            .setBody("product not found"));

        StepVerifier.create(client.getProduct("missing"))
            .expectErrorSatisfies(error -> {
                WebClientResponseException responseError =
                    assertInstanceOf(
                        WebClientResponseException.class,
                        error
                    );

                assertEquals(404,
                    responseError.getStatusCode().value());
                assertEquals(
                    "product not found",
                    responseError.getResponseBodyAsString()
                );
            })
            .verify();
    }

    @Test
    void onStatusCanKeep404AsResponseEntity() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("X-Request-Id", "req-missing"));

        ResponseEntity<Product> response =
            client.getProductAllowing404("missing")
                .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("req-missing",
            response.getHeaders().getFirst("X-Request-Id"));
        assertNull(response.getBody());
    }

    @Test
    void toEntityListKeepsResponseMetadata() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("X-Page", "1")
            .setBody("""
                [
                  {"id":1,"name":"Keyboard","price":79.90},
                  {"id":2,"name":"Mouse","price":25.50}
                ]
                """));

        ResponseEntity<List<Product>> response =
            client.getProducts().block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(200, response.getStatusCode().value());
        assertEquals("1", response.getHeaders().getFirst("X-Page"));
        assertEquals(2, response.getBody().size());
    }

    @Test
    void toBodilessEntityReturnsStatusAndHeaders() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(204)
            .addHeader("X-Request-Id", "delete-7"));

        ResponseEntity<Void> response =
            client.deleteProduct("7").block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(204, response.getStatusCode().value());
        assertEquals("delete-7",
            response.getHeaders().getFirst("X-Request-Id"));
        assertNull(response.getBody());
    }
}
~~~

Các test dùng `block(Duration)` ở ranh giới test để lấy kết quả đồng bộ cho assertion; code production vẫn trả Mono. `StepVerifier` kiểm tra nhánh lỗi mà không chặn thread.

### 17.8. Chạy kiểm thử

Tại thư mục dự án:

~~~bash
./gradlew test
~~~

Hoặc:

~~~bash
gradle test
~~~

Test đầu xác minh status 206, ETag, request ID, body Product và request Accept. Test thứ hai xác minh mặc định 404 là WebClientResponseException. Test thứ ba xác minh onStatus có thể giữ 404 thành ResponseEntity. Hai test cuối kiểm tra toEntityList và toBodilessEntity.

MockWebServer giả lập upstream cục bộ nên test không phụ thuộc mạng Internet hoặc dịch vụ bên ngoài.

## 18. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ toEntity luôn trả ResponseEntity kể cả 404/500 | Nhánh lỗi mặc định bị bỏ sót | Dùng onStatus để map hoặc suppress status cụ thể |
| Chỉ gọi retrieve() rồi mong request chạy | Chưa có terminal extraction operation | Gọi toEntity, bodyToMono, toBodilessEntity hoặc operation tương ứng |
| Dùng bodyToMono khi cần ETag/Location | Mất status/header trong kết quả | Dùng toEntity |
| Dùng toEntity khi chỉ cần body | Wrapper không cần thiết | Dùng bodyToMono |
| Đọc getBody() mà không kiểm tra null | NullPointerException với response không có body | Kiểm tra body trước khi dùng |
| Dùng List.class cho generic JSON | Mất type của phần tử | Dùng toEntityList hoặc ParameterizedTypeReference |
| Dùng toEntityList cho stream vô hạn | Aggregate dữ liệu và tăng bộ nhớ | Dùng toEntityFlux hoặc bodyToFlux |
| Gọi block trong controller/service WebFlux | Chặn event-loop | Compose Mono/Flux bằng map/flatMap |
| Gọi onStatus trả Mono.empty cho mọi lỗi | Vô tình coi 4xx/5xx là response bình thường | Suppress đúng status có nghiệp vụ xử lý |
| Đọc error body nhiều lần | Body đã được tiêu thụ hoặc không còn khả dụng | Decode một lần trong onStatus hoặc dùng WebClientResponseException |
| Log mọi response body | Có thể lộ PII, token hoặc dữ liệu bí mật | Log status, request ID và metadata đã cho phép |
| Chuyển tiếp tất cả upstream headers | Có thể lộ hop-by-hop hoặc header nội bộ | Dùng allowlist header |
| Dùng toEntityFlux nhưng bỏ body Flux | Giữ connection/tài nguyên chưa cần thiết | Tiêu thụ hoặc hủy body theo lifecycle |
| Bắt mọi lỗi thành Mono.empty | Che giấu HTTP, network, timeout và decode error | Phân loại exception và giữ nguyên nguyên nhân |
| Giả định mọi status đều là enum HttpStatus | Không linh hoạt với status code mở rộng | Dùng HttpStatusCode và value() |

## 19. Checklist khi dùng toEntity

Trước khi dùng trong service, hãy xác định:

1. Có thực sự cần status và headers cùng body không?
2. Body target type có đúng với Content-Type response không?
3. Status 4xx/5xx mặc định cần thành exception hay cần giữ thành ResponseEntity?
4. Nếu suppress 404, error body có tương thích với target type không?
5. Response có thể không có body không?
6. Có cần đọc ETag, Location, Retry-After hoặc correlation ID không?
7. Body là object, list, generic envelope hay stream?
8. Có nên dùng toEntityList, toEntityFlux hoặc toBodilessEntity không?
9. Có timeout, retry hoặc error mapping theo SLA upstream không?
10. Có đang block trong reactive request path không?
11. Nếu chuyển tiếp headers, đã dùng allowlist chưa?
12. Đã test status, headers, body, empty body và error status chưa?

| Nhu cầu | API phù hợp |
| --- | --- |
| Lấy object và metadata HTTP | `retrieve().toEntity(Type.class)` |
| Lấy body đơn | `retrieve().bodyToMono(Type.class)` |
| Lấy list và metadata | `retrieve().toEntityList(Type.class)` |
| Lấy generic wrapper | `toEntity(new ParameterizedTypeReference<...>() {})` |
| Chỉ lấy status và headers | `retrieve().toBodilessEntity()` |
| Giữ body stream trong ResponseEntity | `retrieve().toEntityFlux(Type.class)` |
| Rẽ nhánh decode theo status | `exchangeToMono` / `exchangeToFlux` |
| Map lỗi HTTP | `retrieve().onStatus(...)` |

## 20. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `toEntity(Product.class)` trả kiểu gì?

**Đáp án:** `Mono<ResponseEntity<Product>>`. Khi publisher phát kết quả, ResponseEntity chứa status, headers và Product đã decode.

**Câu 2.** Muốn lấy status code thì gọi API nào?

**Đáp án:** `response.getStatusCode()`; dùng `value()` nếu cần số nguyên.

**Câu 3.** Muốn lấy ETag và request ID thì đọc ở đâu?

**Đáp án:** `response.getHeaders().getETag()` và `getFirst("X-Request-Id")`.

**Câu 4.** `toEntity` có mặc định biến 404 thành ResponseEntity không?

**Đáp án:** Không. `retrieve()` mặc định map 4xx/5xx thành WebClientResponseException. Dùng `onStatus` để suppress hoặc map status cụ thể.

**Câu 5.** Làm thế nào giữ 404 thành response bình thường?

**Đáp án:** Thêm `onStatus(status -> status.value() == 404, response -> Mono.empty())` trước `toEntity`. Sau đó kiểm tra status và body có thể null.

**Câu 6.** Khi nào dùng `bodyToMono` thay cho `toEntity`?

**Đáp án:** Khi chỉ cần body và không cần status/header trong kết quả.

**Câu 7.** Vì sao dùng `ParameterizedTypeReference`?

**Đáp án:** Để giữ generic type information, ví dụ PageResult<Product> hoặc ApiEnvelope<List<Product>>, cho codec decode đúng kiểu.

**Câu 8.** `toEntityList` khác `toEntityFlux` thế nào?

**Đáp án:** toEntityList aggregate body thành List; toEntityFlux giữ body dưới dạng Flux để xử lý streaming.

**Câu 9.** Khi DELETE trả 204 và chỉ cần metadata, dùng gì?

**Đáp án:** `retrieve().toBodilessEntity()` trả `Mono<ResponseEntity<Void>>`.

**Câu 10.** Có nên gọi `block()` trong service WebFlux để đọc ResponseEntity không?

**Đáp án:** Không. Hãy trả Mono và compose; chỉ dùng block ở ranh giới đồng bộ có chủ đích như test hoặc CLI.

**Câu 11.** `exchangeToMono` khác `retrieve().toEntity` ở điểm nào?

**Đáp án:** exchangeToMono cho phép truy cập ClientResponse và quyết định cách decode theo status/header; retrieve().toEntity là đường đi ngắn cho response entity thông thường.

**Câu 12.** Vì sao không nên bỏ qua body Flux trong ResponseEntity<Flux<T>>?

**Đáp án:** Body chưa được tiêu thụ có thể giữ connection và tài nguyên. Hãy tiêu thụ hoặc cancel publisher đúng lifecycle.

## 21. Ghi nhớ và tài liệu chính thức

- `retrieve().toEntity(Type.class)` trả `Mono<ResponseEntity<T>>`.
- ResponseEntity cung cấp status code, response headers và body đã decode.
- `getStatusCode()` trả `HttpStatusCode`; `getHeaders()` đọc metadata; `getBody()` lấy object.
- Mặc định 4xx/5xx từ retrieve() là WebClientResponseException, kể cả khi terminal operation là toEntity.
- Dùng `onStatus` để map lỗi hoặc suppress status cụ thể bằng Mono.empty().
- Kiểm tra body null khi response không có nội dung.
- Dùng `ParameterizedTypeReference` cho generic type.
- Dùng `toEntityList` cho list hữu hạn, `toEntityFlux` cho stream, `toBodilessEntity` khi không cần body.
- Dùng `exchangeToMono` khi cần kiểm soát decode theo status và headers.
- Không block trong reactive request path; tiêu thụ body đúng một lần và quản lý publisher lifecycle.
- Chỉ chuyển tiếp response headers theo allowlist trong API gateway.

Tài liệu chính thức:

1. [Spring Framework Reference — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): toEntity, bodyToMono, bodyToFlux và mặc định xử lý 4xx/5xx.
2. [Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): truy cập ClientResponse và quản lý response body.
3. [Spring Framework Javadoc — WebClient.ResponseSpec](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html): toEntity, toEntityList, toEntityFlux, toBodilessEntity và onStatus.
4. [Spring Framework Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): status, headers và body.
5. [Spring Framework Javadoc — HttpStatusCode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpStatusCode.html): status abstraction và kiểm tra status family.
6. [Spring Framework Javadoc — WebClientResponseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html): status, headers và error response body.
7. [Spring Framework Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình WebClient, connector và codecs.
8. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP client/server exchange.
