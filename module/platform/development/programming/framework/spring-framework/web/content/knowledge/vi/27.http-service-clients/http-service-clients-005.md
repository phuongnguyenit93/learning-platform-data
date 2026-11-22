# HTTP Service Client: Cấu hình header, URI, chuyển đổi dữ liệu và xử lý lỗi

## 1. HTTP Service Client là gì và các lớp cấu hình nằm ở đâu?

HTTP Service Client của Spring Framework cho phép định nghĩa hợp đồng gọi HTTP bằng **Java interface**, kết hợp `@HttpExchange`, `@GetExchange`, `@PostExchange`… và các annotation trên tham số. `HttpServiceProxyFactory` tạo proxy triển khai interface và giao phần gửi request/đọc response cho HTTP client thực tế. Cơ chế này xuất hiện từ Spring Framework 6.0; `RestClientAdapter` hỗ trợ `RestClient` từ Spring Framework 6.1. Ví dụ trong bài dùng **Java 17+, Spring Boot 3.3.x (Spring Framework 6.1.x)**.

```text
Code gọi nghiệp vụ
      │
      ▼
CatalogApi interface (@HttpExchange, @GetExchange, @PostExchange)
      │  tham số method → path/query/header/body của request
      ▼
HttpServiceProxyFactory (tạo proxy)
      │
      ▼
RestClientAdapter / WebClientAdapter
      │  baseUrl, defaultHeader, request factory/connector,
      │  converters/codecs, status handlers, timeout...
      ▼
HTTP request → máy chủ → HTTP response → Java object / exception
```

Có **hai tầng cấu hình bổ sung nhau**:

- **Trên interface và method:** URL tương đối, HTTP method, `Accept`/`Content-Type`, đường dẫn, query, header theo từng lần gọi, body và kiểu dữ liệu trả về. Đây là hợp đồng API dễ đọc và kiểm tra.
- **Trên HTTP client nền:** base URL (host/service), header mặc định, xác thực, message converters/codecs, timeout/transport, quy tắc lỗi HTTP dùng chung. Proxy không tự cung cấp một bộ codec hay transport khác với adapter được gắn vào nó.

`RestClient` dùng cách gọi đồng bộ, thích hợp interface trả `T`, `List<T>` hoặc `ResponseEntity<T>`. `WebClient` là client reactive và có thể dùng interface trả `Mono<T>`, `Flux<T>`. Không khai báo `Mono<T>` trên interface dùng `RestClientAdapter` rồi kỳ vọng reactive execution.

## 2. Định nghĩa interface và tạo proxy

Ví dụ hợp đồng quản lý sản phẩm:

```java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

record Product(long id, String name, String category) {}
record CreateProduct(String name, String category) {}

@HttpExchange(url = "/api/products", accept = MediaType.APPLICATION_JSON_VALUE)
interface CatalogApi {

    @GetExchange("/{id}")
    Product findById(
        @PathVariable("id") long id,
        @RequestHeader("X-Request-Id") String requestId
    );

    @GetExchange("/search")
    List<Product> findByCategory(@RequestParam("category") String category);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Product create(@RequestBody CreateProduct request);
}
```

Đây là **mã minh họa** (chưa gồm `main`). `@HttpExchange` trên interface đặt URL chung và `Accept: application/json`. `@GetExchange`/`@PostExchange` định nghĩa HTTP method và phần URL còn lại. Header `X-Request-Id` được nhận theo từng lần gọi. Body `CreateProduct` được mã hóa thành JSON nếu có converter phù hợp, và JSON response được giải mã thành `Product`.

Cấu hình đồng bộ bằng `RestClient`:

```java
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultHeader("X-Client-App", "java-learning")
    .build();

CatalogApi catalog = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .build()
    .createClient(CatalogApi.class);

Product item = catalog.findById(7, "req-007");
```

Đây là **mã minh họa**; URL cần là service thật. Từ Spring Framework 6.1, `builderFor(RestClientAdapter.create(...))` là API thích hợp. Trong ứng dụng Spring Boot, nên đăng ký proxy một lần dưới dạng bean và inject vào các service, thay vì tạo factory cho mỗi request.

Ví dụ bean:

```java
@Configuration
class CatalogClientConfiguration {

    @Bean
    CatalogApi catalogApi(RestClient.Builder builder) {
        RestClient client = builder
            .baseUrl("https://catalog.example.com")
            .defaultHeader("X-Client-App", "java-learning")
            .build();

        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(client))
            .build()
            .createClient(CatalogApi.class);
    }
}
```

Đoạn trên cần các import tương ứng cho `@Configuration`, `@Bean`, `RestClient`, `RestClientAdapter`, `HttpServiceProxyFactory` và `CatalogApi`. Khi sử dụng `RestClient.Builder` được Spring Boot cung cấp, bạn có thể thừa hưởng những customizer đã được cấu hình trong ứng dụng.

## 3. Header: mặc định, tĩnh theo API và động theo lời gọi

Header điều khiển metadata của request: content negotiation, định dạng body, xác thực, correlation ID, locale, v.v. Chọn nơi khai báo theo **phạm vi trách nhiệm**:

| Nguồn header | Ví dụ | Khi nên dùng |
| --- | --- | --- |
| `RestClient.Builder.defaultHeader(name, value)` | `X-Client-App: java-learning` | Giá trị mặc định áp dụng cho các method của cùng client |
| `WebClient.Builder.defaultHeader(name, value)` | `Accept-Language: vi` | Tương tự nhưng cho WebClient |
| `@HttpExchange(accept=..., contentType=...)` | `Accept: application/json` | Quy định media type trong hợp đồng HTTP interface |
| `@GetExchange(accept=...)` / `@PostExchange(contentType=...)` | `Content-Type: application/json` | Ghi đè media type ở method khi API khác nhau |
| `@RequestHeader("X-Request-Id")` | Giá trị từ tham số Java | Header thay đổi theo từng lời gọi |
| `@RequestHeader HttpHeaders` hoặc map phù hợp | Nhiều header động | Khi số lượng header thay đổi theo request |
| Interceptor/filter của client nền | Bearer token, trace propagation | Chính sách chung, đặc biệt khi token cần làm mới hoặc theo user |

Điểm hay bị hiểu sai: trong Spring Framework 6.1, `@HttpExchange` **không có thuộc tính `headers` tổng quát như `@RequestMapping`**. Sử dụng `accept`, `contentType`, `@RequestHeader` hoặc builder/filter ở client nền. `defaultHeader` chỉ bổ sung giá trị mặc định nếu header đó chưa được chỉ rõ trong request; tránh dựa vào việc chồng nhiều giá trị trùng tên mà không biết client/server diễn giải ra sao.

Ví dụ header động:

```java
@GetExchange("/{id}")
Product findById(
    @PathVariable("id") long id,
    @RequestHeader("X-Request-Id") String requestId,
    @RequestHeader("Authorization") String authorization
);

// Cách gọi:
Product p = catalog.findById(7, "req-007", "Bearer <access-token>");
```

Đoạn này là **minh họa biến thể chữ ký**; muốn chạy, cập nhật interface `CatalogApi` và truyền token hợp lệ. Không ghi access token/cookie nhạy cảm vào log và không nhúng token dài hạn vào annotation hoặc source code. Nếu auth là trách nhiệm chung, interceptor (`RestClient`) hoặc filter (`WebClient`) thường là vị trí thích hợp hơn.

**`Accept` khác `Content-Type`:** `Accept` mô tả các media type client muốn nhận; `Content-Type` mô tả kiểu body **gửi đi**. GET không có request body thường không cần `Content-Type`. Với POST JSON, cả `Content-Type: application/json` của request và `Accept: application/json` cho response đều có ích. Sai media type có thể dẫn tới HTTP 406/415 hoặc lỗi chuyển đổi nội dung.

## 4. URI: base URL, path variable, query và URI động

Với client có `baseUrl("https://catalog.example.com")`, các annotation:

```java
@HttpExchange(url = "/api/products")
interface CatalogApi {

    @GetExchange("/{id}")
    Product findById(@PathVariable("id") long id);

    @GetExchange("/search")
    List<Product> search(
        @RequestParam("category") String category,
        @RequestParam("page") int page
    );
}
```

tạo URI tương ứng (ví dụ):

```text
GET https://catalog.example.com/api/products/7
GET https://catalog.example.com/api/products/search?category=office&page=2
```

`@PathVariable` thay các placeholder trong URL template; `@RequestParam` thêm query parameter cho GET và nhiều tình huống HTTP thông thường. Với request `application/x-www-form-urlencoded`, `@RequestParam` có thể trở thành trường form tương ứng theo hợp đồng HTTP interface. `@PathVariable("id")`/`@RequestParam("page")` khai báo tên rõ ràng, giúp không phụ thuộc metadata tên tham số được compiler giữ lại.

Một số lựa chọn động:

```java
import java.net.URI;

@GetExchange
Product loadFrom(URI absoluteUri);

@GetExchange("/search")
List<Product> searchWithBase(
    UriBuilderFactory uriBuilderFactory,
    @RequestParam("category") String category
);
```

Đây là **các method minh họa**, bổ sung import `org.springframework.web.util.UriBuilderFactory`. Tham số `URI` có thể đặt URL động và thay giá trị URL từ annotation của method. `UriBuilderFactory` cung cấp cách thay base URI/factory trong khi vẫn sử dụng đường dẫn tương đối do annotation mô tả. Chọn tham số URI tuyệt đối khi thực sự cần endpoint khác; **không cho phép URL do người dùng bên ngoài cung cấp tùy ý** nếu không có allowlist host/scheme và kiểm tra SSRF.

**Encoding:** dùng template + variable resolver thay cho nối chuỗi:

```java
// Ưu tiên:
@GetExchange("/customers/{customerId}")
Customer findCustomer(@PathVariable("customerId") String customerId);

// Tránh lắp URL bằng chuỗi chứa input chưa encode:
// "https://api.example.com/customers/" + untrustedCustomerId
```

Với ký tự khoảng trắng, `&`, `?`, `/` hay Unicode, cần hiểu vị trí path/query và cấu hình URI encoding của client. Đặc biệt, ký tự `/` trong một path variable có thể thay đổi ý nghĩa segment nếu không được encode theo chính sách mong muốn. Đừng tự `URLEncoder.encode` toàn bộ URL vì công cụ này dành cho form encoding, không thay thế URI builder. Với query có nhiều giá trị cùng tên, dùng tham số collection hoặc resolver phù hợp; kiểm tra contract thực tế của upstream.

## 5. Chuyển đổi request/response: Java object, JSON, collection

HTTP Service Client ủy nhiệm chuyển đổi cho client nền:

- `RestClient` dùng các `HttpMessageConverter` của Spring Web để viết/đọc body. Trong classpath có Jackson, `MappingJackson2HttpMessageConverter` thường xử lý JSON.
- `WebClient` dùng `HttpMessageReader`/`HttpMessageWriter` và các codec reactive. Cấu hình decoder/buffer của WebClient áp dụng cho proxy dùng `WebClientAdapter`.
- Annotation `@RequestBody` chỉ xác định tham số là request body; để serialize JSON cần converter/codec phù hợp, `Content-Type` phù hợp và DTO hợp lệ.
- Kiểu return trên method xác định đối tượng/collection cần decode. Lỗi JSON/schema có thể xảy ra **ngay cả khi HTTP status là 200**.

Ví dụ DTO Java 17:

```java
public record CreateProduct(String name, String category) {}

public record Product(long id, String name, String category) {}
```

Khi gọi:

```java
Product created = catalog.create(new CreateProduct("Pen", "office"));
```

Converter JSON sẽ gửi payload có dạng:

```json
{"name":"Pen","category":"office"}
```

Giả sử response từ server:

```json
{"id":8,"name":"Pen","category":"office"}
```

thì return type `Product` được deserialize thành `new Product(8, "Pen", "office")`. Với danh sách JSON `[{"id":7,...}]`, return `List<Product>` để Spring giữ thông tin phần tử generic; đừng dùng raw `List` rồi ép thủ công từng `Map` sang DTO. Khi response không có body (204), có thể dùng `void`/`ResponseEntity<Void>`; việc ép một DTO bắt buộc từ body trống thường không phù hợp với hợp đồng endpoint.

Kiểu return hay gặp:

| Return type HTTP interface | Ý nghĩa | Adapter phù hợp |
| --- | --- | --- |
| `Product`, `List<Product>` | Decode body | `RestClientAdapter` / `WebClientAdapter` |
| `ResponseEntity<Product>` | Giữ status, headers và body | Cả hai |
| `ResponseEntity<Void>` | Lấy status/headers, không cần body | Cả hai |
| `Mono<Product>` | Decode bất đồng bộ tối đa một phần tử | `WebClientAdapter` |
| `Flux<Product>` | Decode luồng 0..N phần tử | `WebClientAdapter` |
| `Mono<ResponseEntity<Flux<Product>>>` | Vừa lấy metadata vừa stream | `WebClientAdapter` |

Lưu ý: `ResponseEntity<Product>` không có nghĩa 404 sẽ tự được trả về bình thường; client mặc định có thể ném lỗi status **trước khi** tạo `ResponseEntity`. Nếu nghiệp vụ cần giữ 404 như kết quả dữ liệu, phải cấu hình chính sách status phù hợp và thiết kế DTO/body rõ ràng.

### Tùy biến conversion

`RestClient.Builder` có `messageConverters(...)` để bổ sung/sửa converters. Chỉ bổ sung converter khi có yêu cầu thực tế (format vendor-specific, media type riêng, ObjectMapper policy…). Đảm bảo thứ tự converter không vô tình thay Jackson chuẩn.

```java
RestClient custom = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .messageConverters(converters -> {
        // Thêm converter riêng tại đây nếu đã xác định rõ media type.
        // Không xóa converters mặc định chỉ để đổi một DTO.
    })
    .build();
```

Với WebClient, tùy biến tại `WebClient.Builder.codecs(configurer -> ...)`. Ví dụ tăng buffer decode hợp lý cho payload JSON lớn: `configurer.defaultCodecs().maxInMemorySize(1024 * 1024)`. Đây là hạn bộ nhớ **trong một thao tác decode cần buffering**, không giới hạn tổng bộ nhớ toàn bộ stream hay mọi collection downstream. Ưu tiên phân trang, stream hoặc giới hạn payload ở server hơn là tăng giới hạn vô tội vạ.

### Các lỗi chuyển đổi thường gặp

- `415 Unsupported Media Type`: server từ chối `Content-Type` của request. Kiểm tra method, converter và body.
- `406 Not Acceptable`: server không thể tạo nội dung khớp `Accept`; kiểm tra API negotiation.
- HTTP 200 nhưng body JSON không hợp lệ/không khớp DTO: có thể gặp `RestClientException` gắn lỗi message conversion hoặc `CodecException`/`DecodingException` với WebClient.
- Thiếu converter Jackson trong classpath hoặc cấu hình thiếu: không serialize/deserialize JSON như kỳ vọng.
- JSON object rất lớn với WebClient: có thể phát `DataBufferLimitException` do codec memory limit, khác với HTTP 413 do server trả về.

## 6. Xử lý lỗi HTTP Service Client ở tầng client nền

**Proxy không có phương thức `onStatus` để gọi nối sau một method của interface.** Định nghĩa chính sách xử lý lỗi ở `RestClient` / `WebClient` được truyền vào `HttpServiceProxyFactory`. Mặc định, cả hai thường phát exception khi nhận HTTP 4xx/5xx (RestClient thuộc họ `RestClientException`, WebClient thường là `WebClientResponseException`).

Với `RestClient` (Spring Framework 6.1):

```java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultStatusHandler(
        status -> status.value() == 404,
        (request, response) -> {
            throw new ProductNotFoundException(
                "Không tìm thấy sản phẩm: HTTP " + response.getStatusCode().value()
            );
        }
    )
    .build();

CatalogApi catalog = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .build()
    .createClient(CatalogApi.class);
```

`ProductNotFoundException` là class nghiệp vụ do bạn định nghĩa; đoạn này là mã minh họa. `defaultStatusHandler` cho phép map 404 thành exception nhất quán trên **mọi** method proxy dùng client đó. Handler được thử theo thứ tự đăng ký; nên đặt rule chuyên biệt trước rule 4xx/5xx tổng quát. Nếu không có handler tùy chỉnh phù hợp, mapping HTTP 4xx/5xx mặc định vẫn áp dụng.

Với `WebClient` reactive, hình thức handler khác:

```java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultStatusHandler(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("Not found")
            .map(message -> new ProductNotFoundException(message))
    )
    .build();

CatalogReactiveApi api = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(CatalogReactiveApi.class);
```

Đây cũng là **mã minh họa** (cần khai báo `CatalogReactiveApi` với return reactive và các import). Callback của `WebClient` trả publisher phát `Throwable`; callback của `RestClient` là xử lý đồng bộ, thường `throw` exception. Không trộn kiểu handler của hai API.

### Bốn nhóm lỗi cần tách riêng

1. **HTTP 4xx/5xx:** upstream thực sự trả response. Có status, headers và đôi khi body lỗi. Ví dụ 404 nghiệp vụ, 429 rate limit, 500/503 upstream.
2. **Kết nối/timeout/TLS:** chưa chắc đã nhận HTTP response; xử lý bằng cấu hình transport, retry có giới hạn và quan sát cause. Không thể dùng HTTP status predicate để bắt các lỗi này.
3. **Serialization/deserialization:** JSON sai, DTO không khớp, converter/codecs thiếu, payload quá lớn. HTTP 200 vẫn có thể thất bại ở đây.
4. **Lỗi nghiệp vụ sau decode:** đối tượng hợp lệ về mặt JSON nhưng vi phạm yêu cầu domain. Kiểm tra sau khi nhận DTO, không gộp với lỗi HTTP status.

Với response lỗi mang JSON chi tiết, handler có thể đọc body thành DTO lỗi hoặc String rồi tạo exception nghiệp vụ, nhưng body response là stream chỉ tiêu thụ một lần. Giới hạn nội dung lỗi và tránh log token/sensitive fields. Handler **mặc định** ở client áp dụng cho toàn bộ proxy dùng client; nếu hai API có quy tắc lỗi khác nhau, hãy cấu hình client/adapter riêng hoặc chọn cơ chế handler chi tiết phù hợp.

### Retry, fallback và HTTP status

`onStatus` hoặc `defaultStatusHandler` chỉ quyết định lỗi nào được phát; retry là chính sách **riêng**. Retry có thể hợp lý với lỗi kết nối tạm thời, 502/503 hoặc 429 theo hợp đồng API, nhưng phải có giới hạn, backoff, deadline và xem `Retry-After` nếu thích hợp. Không retry mù thao tác POST gây tác dụng phụ nếu không có idempotency key. Với proxy đồng bộ, dùng resilience layer ngoài client (ví dụ Spring Retry/Resilience4j theo cấu hình đã chọn); với proxy reactive, có thể đặt `retryWhen(...)` trên `Mono`/`Flux`, cùng một error taxonomy rõ ràng.

## 7. Ví dụ độc lập Java 17+: GET, query, header, JSON POST và 404

Bài thực hành dùng `com.sun.net.httpserver.HttpServer` có sẵn trong JDK để chạy HTTP server ngay trên localhost. Kết nối không phụ thuộc internet, nhưng Gradle cần tải dependencies ở lần chạy đầu nếu chưa có cache. Client dùng **`RestClientAdapter`**; mã Java minh họa tất cả nội dung chính: URL động qua server port, header global + header method, path variable, query, body JSON qua Jackson, response thành record và handler cho HTTP 404.

Cấu trúc dự án:

```text
http-service-client-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/HttpServiceClientDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'http-service-client-demo'
```

**`build.gradle`** (Gradle 8.x, JDK 17+)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
}

application {
    mainClass = 'demo.HttpServiceClientDemo'
}
```

**`src/main/java/demo/HttpServiceClientDemo.java`**

```java
package demo;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

public class HttpServiceClientDemo {
    private static final ObjectMapper JSON = new ObjectMapper();

    public record Product(long id, String name, String category) {}
    public record CreateProduct(String name, String category) {}

    @HttpExchange(url = "/api/products", accept = MediaType.APPLICATION_JSON_VALUE)
    public interface CatalogApi {
        @GetExchange("/{id}")
        Product findById(
            @PathVariable("id") long id,
            @RequestHeader("X-Request-Id") String requestId
        );

        @GetExchange("/search")
        List<Product> search(@RequestParam("category") String category);

        @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
        Product create(@RequestBody CreateProduct request);
    }

    public static class ProductNotFoundException extends RuntimeException {
        public ProductNotFoundException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/api/products", HttpServiceClientDemo::handle);
        server.start();

        try {
            RestClient underlyingClient = RestClient.builder()
                .baseUrl("http://127.0.0.1:" + server.getAddress().getPort())
                .defaultHeader("X-Client-App", "java-learning")
                .defaultStatusHandler(
                    status -> status.value() == 404,
                    (request, response) -> {
                        throw new ProductNotFoundException(
                            "HTTP " + response.getStatusCode().value()
                        );
                    }
                )
                .build();

            CatalogApi api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(underlyingClient))
                .build()
                .createClient(CatalogApi.class);

            Product item = api.findById(7, "request-007");
            System.out.println("GET: " + item);

            List<Product> results = api.search("office");
            System.out.println("SEARCH count: " + results.size());

            Product added = api.create(new CreateProduct("Pen", "office"));
            System.out.println("POST: " + added);

            try {
                api.findById(99, "request-099");
            } catch (ProductNotFoundException error) {
                System.out.println("ERROR: " + error.getMessage());
            }
        } finally {
            server.stop(0);
        }
    }

    private static void handle(HttpExchange request) throws IOException {
        String method = request.getRequestMethod();
        String path = request.getRequestURI().getPath();

        int status = 200;
        String response;

        if (!"java-learning".equals(
                request.getRequestHeaders().getFirst("X-Client-App"))) {
            status = 401;
            response = "{\"error\":\"missing app header\"}";
        } else if (method.equals("GET")
                && path.equals("/api/products/7")
                && "request-007".equals(
                    request.getRequestHeaders().getFirst("X-Request-Id"))) {
            response = "{\"id\":7,\"name\":\"Notebook\",\"category\":\"office\"}";
        } else if (method.equals("GET")
                && path.equals("/api/products/search")
                && "category=office".equals(request.getRequestURI().getRawQuery())) {
            response = "[{\"id\":7,\"name\":\"Notebook\",\"category\":\"office\"}]";
        } else if (method.equals("POST") && path.equals("/api/products")) {
            CreateProduct input = JSON.readValue(
                request.getRequestBody(), CreateProduct.class
            );

            if ("Pen".equals(input.name()) && "office".equals(input.category())) {
                response = "{\"id\":8,\"name\":\"Pen\",\"category\":\"office\"}";
            } else {
                status = 400;
                response = "{\"error\":\"invalid product\"}";
            }
        } else {
            status = 404;
            response = "{\"error\":\"not found\"}";
        }

        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
        request.getResponseHeaders().set("Content-Type", "application/json");
        request.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = request.getResponseBody()) {
            stream.write(bytes);
        }
    }
}
```

Chạy tại thư mục dự án (sử dụng Gradle đã cài; nếu có wrapper, thay `gradle` bằng `./gradlew` trên Unix/macOS hoặc `gradlew.bat` trên Windows):

```bash
gradle run --quiet
```

**Các dòng chương trình dự kiến in ra:**

```text
GET: Product[id=7, name=Notebook, category=office]
SEARCH count: 1
POST: Product[id=8, name=Pen, category=office]
ERROR: HTTP 404
```

Giải thích luồng thực thi:

1. `HttpServer` bind cổng tự chọn (`0`), client lấy địa chỉ base URL động.
2. `findById(7, "request-007")` tạo GET `/api/products/7` cùng header global `X-Client-App` và header động `X-Request-Id`. Server kiểm tra cả hai, rồi trả JSON object được chuyển thành `Product`.
3. `search("office")` tạo query `category=office`; response JSON array được giải mã thành `List<Product>`.
4. `create(new CreateProduct(...))` tạo POST body JSON, server dùng Jackson đọc thành `CreateProduct`, rồi trả `Product` mới.
5. `findById(99, ...)` nhận 404; `RestClient.defaultStatusHandler` chuyển nó thành `ProductNotFoundException`. Caller bắt exception và in `ERROR: HTTP 404`.

Ở ví dụ này, server là HTTP local phục vụ mục đích học. Với môi trường thật, dùng HTTPS, chính sách credentials/trace, timeout và monitoring tương ứng. Mã ví dụ tập trung vào chức năng cần học; không triển khai authentication, pagination thực tế hay retry production.

## 8. So sánh RestClientAdapter và WebClientAdapter

| Tiêu chí | `RestClientAdapter` | `WebClientAdapter` |
| --- | --- | --- |
| Nền tảng thực thi | `RestClient` đồng bộ | `WebClient` reactive/non-blocking |
| Kiểu return thường dùng | `Product`, `List<Product>`, `ResponseEntity<Product>` | `Mono<Product>`, `Flux<Product>`, `Mono<ResponseEntity<T>>` |
| Header mặc định | `RestClient.Builder.defaultHeader` | `WebClient.Builder.defaultHeader` |
| JSON conversion | Spring `HttpMessageConverter` | Spring reactive codecs |
| Xử lý HTTP 4xx/5xx | `RestClient.Builder.defaultStatusHandler` | `WebClient.Builder.defaultStatusHandler` |
| Cấu hình transport | Client request factory, HTTP engine | Client connector (thường Reactor Netty) |
| Phù hợp | Ứng dụng đồng bộ/MVC, script, API nhỏ | WebFlux pipeline, streaming, nhiều I/O đồng thời |

Interface chia sẻ contract có thể được thiết kế chung nếu return type tương thích; không phải mọi method synchronous trả object đều nên mang nguyên sang luồng reactive. Đặt tên API rõ ràng và tránh gọi `block()` trên event-loop chỉ để tái sử dụng chữ ký đồng bộ.

Cấu hình reactive minh họa:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;

@HttpExchange(url = "/api/products", accept = "application/json")
interface ReactiveCatalogApi {
    @GetExchange("/{id}")
    Mono<Product> findById(@PathVariable("id") long id);
}

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com")
    .defaultHeader("X-Client-App", "java-learning")
    .build();

ReactiveCatalogApi api = HttpServiceProxyFactory
    .builderFor(WebClientAdapter.create(webClient))
    .build()
    .createClient(ReactiveCatalogApi.class);
```

Đây là minh họa (không phải file Java độc lập); cần `spring-boot-starter-webflux`, các import annotation/`Product`/`HttpServiceProxyFactory` và môi trường reactive tương ứng.

## 9. Lỗi thường gặp và cách kiểm tra

1. **Nhầm annotation của controller với HTTP interface.** `@GetMapping`/`@RequestMapping` là lựa chọn phổ biến cho server controller; ở HTTP Service Client dùng `@GetExchange`/`@HttpExchange` để proxy hiểu outbound request.
2. **Đặt header bằng thuộc tính `headers` trên `@HttpExchange`.** Spring 6.1 không định nghĩa thuộc tính này. Sử dụng `accept`/`contentType`, `@RequestHeader` hoặc builder.
3. **Sai vị trí header động:** correlation ID hoặc Authorization cố định tại startup dù chúng thuộc request/user khác nhau. Dùng tham số method, filter hoặc interceptor có scope đúng.
4. **Lắp URL bằng cách nối chuỗi input.** Có nguy cơ encode sai và injection/SSRF. Dùng `@PathVariable`, `@RequestParam` và URI builder; chỉ cho phép host/scheme hợp lệ khi URL động.
5. **Nhầm `Accept` và `Content-Type`.** GET JSON cần yêu cầu server trả JSON, còn POST JSON cần mô tả request body đúng kiểu; header sai có thể gây 406/415.
6. **Tưởng `@RequestBody` tự chuyển JSON khi thiếu Jackson/converter.** Chuyển đổi phụ thuộc classpath và cấu hình client nền.
7. **Dùng `List` raw type thay vì `List<Product>`.** Mất thông tin kiểu phần tử, dễ nhận `Map` rồi gặp ép kiểu sai.
8. **Cho rằng `ResponseEntity<T>` vô hiệu hóa 404 exception.** Status handlers của client có thể chạy trước; phải xử lý theo hợp đồng lỗi.
9. **Gọi `onStatus` ngay trên method proxy.** Proxy trả `Product` hoặc `Mono<Product>`, không phải `ResponseSpec`; cấu hình lỗi tại `RestClient.Builder`/`WebClient.Builder`.
10. **Retry HTTP 400/401/403 hoặc POST mọi trường hợp.** Phân biệt lỗi có thể phục hồi, bảo vệ idempotency và giới hạn retry.
11. **Nuốt mất body lỗi hoặc đọc nó nhiều lần.** Handler chỉ nên tiêu thụ body cần thiết một lần, giới hạn size và giữ status/headers quan trọng trong exception.
12. **Thử request bằng mock có HTTP 200 mà cho rằng production sẽ giống hệt.** Cần integration test riêng cho path encoding, headers, 4xx/5xx, network failures, media types, codec limits và schema biến động.

Để kiểm thử client, có thể dùng `MockRestServiceServer` (với RestClient) hoặc mock HTTP server như WireMock/MockWebServer; kiểm tra cả HTTP method, URI, headers, body và mapping lỗi. Kiểm thử hợp đồng nên thực hiện từ **hành vi HTTP thực tế** (request/response), thay vì chỉ gọi mock implementation của interface.

## 10. Tự kiểm tra

1. **Tại sao khai báo `@RequestHeader("Authorization") String token` hữu ích hơn hard-code bearer token tại interface?** Vì token có thể thay đổi theo user/request và cần được bảo vệ, làm mới.
2. **Khi gọi `search("office")`, `category` nên nằm ở đâu?** Với GET thông thường, `@RequestParam` đưa nó vào query string; `@PathVariable` thì dùng cho một placeholder trong path.
3. **Nếu return `List<Product>` mà HTTP 200 trả JSON object, điều gì xảy ra?** Decoder có thể thất bại do body shape không khớp; HTTP status thành công không bảo đảm Java conversion thành công.
4. **Nếu muốn 404 map sang `ProductNotFoundException` ở tất cả method proxy `RestClient`, cấu hình ở đâu?** Ở `RestClient.Builder.defaultStatusHandler` trước khi tạo `RestClientAdapter`/proxy.
5. **Nếu một method cần streaming response, chọn loại interface/adapter nào?** Dùng `WebClientAdapter` với return type `Flux<T>` và upstream/codec hỗ trợ streaming; không chuyển `List<T>` đồng bộ thành streaming chỉ bằng thay tên kiểu.
6. **Nếu upstream trả JSON lỗi có thêm mã domain, nên xử lý thế nào?** Đọc body lỗi đúng một lần trong status handler, giải mã schema có giới hạn và tạo exception giàu ngữ cảnh, tách khỏi lỗi kết nối/codec.

## 11. Tài liệu tham khảo

- Spring Framework Reference — REST Clients và HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework 6.1 Javadoc — `@HttpExchange` (method arguments, URL, media types): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
- Spring Framework 6.1 Javadoc — `HttpServiceProxyFactory`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 Javadoc — `RestClient.Builder`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html
- Spring Framework Reference — URI links and encoding: https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html
