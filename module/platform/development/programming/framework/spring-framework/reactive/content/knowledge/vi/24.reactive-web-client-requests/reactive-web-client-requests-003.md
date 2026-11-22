# Base URL, UriBuilder, path và query parameter khi gửi yêu cầu WebClient

## 1. Mục tiêu và các thành phần của request

`WebClient` là HTTP client reactive của Spring WebFlux. Một request HTTP thường cần các thành phần:

- **Base URL**: địa chỉ gốc của API.
- **Path**: đường dẫn tới resource.
- **Path variables**: dữ liệu động trong path segment.
- **Query parameters**: filter, pagination, sort hoặc tùy chọn.
- **Headers**: metadata như Accept, Authorization, correlation ID.
- **Body**: payload của POST, PUT hoặc PATCH.

Ví dụ:

~~~text
Base URL: https://catalog.example.test
Path:     /v1/products/{category}
Query:    ?q={term}&page={page}&sort={sort}
~~~

Với category là `books`, term là `Spring WebFlux`, page là 2, URI request có dạng:

~~~text
https://catalog.example.test/v1/products/books?q=Spring%20WebFlux&page=2&sort=newest
~~~

Tách template và dữ liệu động giúp code dễ đọc, dễ test và tránh lỗi khi input có khoảng trắng hoặc ký tự reserved.

**Nguyên tắc:** giữ cấu trúc URI trong template, truyền dữ liệu động qua URI variables và để `UriBuilder`/`UriBuilderFactory` encode. Không nối URL bằng chuỗi từ input chưa tin cậy.

## 2. Tạo WebClient và cấu hình base URL

### 2.1. Ba cách khởi tạo

Client đơn giản không có base URL:

~~~java
WebClient client = WebClient.create();
~~~

Client với base URL:

~~~java
WebClient client =
        WebClient.create("https://catalog.example.test");
~~~

Client qua builder:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
~~~

`WebClient.builder()` phù hợp khi cần cấu hình nhiều thành phần:

- `baseUrl` hoặc `uriBuilderFactory`.
- `defaultUriVariables`.
- `defaultHeader`, `defaultHeaders`, `defaultCookie`.
- `filter` cho request/response.
- `clientConnector` để chọn HTTP client.
- `codecs` để cấu hình message readers/writers.

Sau `build()`, `WebClient` là immutable và có thể dùng lại giữa các request. Khi cần biến thể, dùng `client.mutate()` để tạo builder mới.

### 2.2. Base URL chỉ áp dụng cho URI tương đối

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Mono<String> relative = client.get()
        .uri("/v1/health")
        .retrieve()
        .bodyToMono(String.class);

Mono<String> absolute = client.get()
        .uri("https://status.example.test/health")
        .retrieve()
        .bodyToMono(String.class);
~~~

Request đầu dùng host catalog. Request thứ hai gọi host status vì URI đã tuyệt đối.

| Giá trị truyền vào uri(...) | Kết quả |
| --- | --- |
| `/v1/products` | Dùng base URL |
| `v1/products` | Dùng base URL qua URI factory |
| `https://other.example.test/products` | URI tuyệt đối; base URL bị bỏ qua |
| `URI` hoàn chỉnh | Dùng URI được cung cấp |

Base URL là cấu hình định tuyến, không phải cơ chế giới hạn host. Nếu input người dùng có thể cung cấp URL tuyệt đối, URL đó có thể bỏ qua base URL. Với server-side fetch hoặc webhook, phải kiểm tra scheme, host, port, DNS và redirect theo allowlist để tránh SSRF.

### 2.3. baseUrl và uriBuilderFactory

`baseUrl(...)` là shortcut để cấu hình `DefaultUriBuilderFactory` với base URL. Có thể cấu hình factory trực tiếp:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory(
                "https://catalog.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient client = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

Dùng `baseUrl` và `uriBuilderFactory` như hai cách cấu hình thay thế nhau. Khi cung cấp factory trực tiếp, factory đó chi phối shortcut baseUrl.

### 2.4. Base URL có path prefix

Một API có thể đặt endpoint dưới prefix:

~~~text
https://api.example.test/platform/catalog
~~~

Có thể cấu hình base URL theo prefix và dùng URI tương đối cho endpoint con. Khi base URL có path, hãy test URI cuối cùng để xác nhận prefix, dấu slash và path template được ghép đúng ý định. Dùng một quy ước nhất quán cho slash đầu/cuối trong cả client.

Nếu các endpoint gọi nhiều host hoặc nhiều prefix khác nhau, cân nhắc tạo WebClient riêng cho từng API thay vì thay host động trên client dùng chung.

## 3. Các overload uri(...) của WebClient

| Cách gọi | Khi dùng |
| --- | --- |
| `uri(String template, Object... variables)` | Template ngắn, ít biến |
| `uri(String template, Map<String, ?> variables)` | Nhiều biến, cần ánh xạ theo tên |
| `uri(URI uri)` | Đã tạo URI hoàn chỉnh |
| `uri(Function<UriBuilder, URI>)` | Cần thêm path/query hoặc logic động |
| `uri(String template, Function<UriBuilder, URI>)` | Bắt đầu từ template rồi hoàn thiện bằng builder |

### 3.1. Positional variables

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", 42L)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Đối số thay thế theo thứ tự placeholder. Khi template dài, dễ truyền nhầm giá trị.

### 3.2. Named variables bằng Map

~~~java
Map<String, Object> variables = Map.of(
        "category", "books",
        "id", 42L);

Mono<Product> product = client.get()
        .uri("/v1/categories/{category}/products/{id}",
                variables)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Tên trong Map phải khớp chính xác placeholder. Named variables thường dễ review hơn khi template có nhiều biến.

### 3.3. URI đã tạo sẵn

~~~java
URI uri = URI.create(
        "https://catalog.example.test/v1/products/42");

Mono<Product> product = client.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Khi truyền `URI` hoàn chỉnh, caller chịu trách nhiệm parse, encode và validate. WebClient không expand template trong đối tượng URI đó. Không tạo URI từ input bằng phép nối chuỗi rồi trông chờ client tự sửa encoding.

### 3.4. UriBuilder function

Đây là cách linh hoạt khi path và query có nhiều thành phần:

~~~java
Mono<ProductPage> products = client.get()
        .uri(builder -> builder
                .path("/v1/categories/{category}/products")
                .queryParam("q", "{term}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "category", category,
                        "term", searchTerm,
                        "page", page,
                        "size", size)))
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Builder được tạo từ `UriBuilderFactory` của WebClient, vì vậy base URL và encoding mode đã cấu hình được áp dụng.

## 4. path và pathSegment

### 4.1. path(String)

`path(String)` thêm một đoạn path template:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/v1/products/{productId}")
        .build(42);
~~~

Kết quả:

~~~text
https://api.example.test/v1/products/42
~~~

Có thể nối nhiều đoạn:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/v1")
        .path("/categories/{category}")
        .path("/products/{productId}")
        .build(Map.of(
                "category", "books",
                "productId", 42));
~~~

`path` nối path template. Khi dùng nhiều đoạn, thống nhất quy ước slash đầu/cuối để tránh path thiếu slash hoặc slash kép ngoài ý muốn.

### 4.2. Không nối input trực tiếp vào path

Không nên:

~~~java
String path = "/v1/products/" + category;
Mono<Product> result = client.get()
        .uri(path)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Nếu category là `books/../../admin`, dấu slash và dot segment có thể làm thay đổi path. Giá trị có `?` hoặc `#` cũng có thể ảnh hưởng query hoặc fragment.

Nên giữ template và giá trị riêng:

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{category}", category)
        .retrieve()
        .bodyToMono(Product.class);
~~~

### 4.3. pathSegment(String...)

`pathSegment` thể hiện rõ mỗi argument là một segment:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("v1", "products", "{category}", "{id}")
        .encode()
        .buildAndExpand("books & media", 42)
        .toUri();
~~~

Kết quả có dạng:

~~~text
https://api.example.test/v1/products/books%20%26%20media/42
~~~

| API | Ý nghĩa |
| --- | --- |
| `path("/products/{id}")` | Thêm một đoạn path template |
| `pathSegment("products", "{id}")` | Thêm các segment riêng |

Dùng `pathSegment` khi giá trị phải thuộc một segment, đặc biệt nếu có khoảng trắng hoặc reserved character.

### 4.4. Path variable có slash

Một URI variable thông thường đại diện cho một giá trị path, không nên được dùng để ghép nhiều segment. Strict encoding có thể mã hóa slash trong value thành `%2F`. Tuy nhiên, proxy, gateway hoặc server có thể decode encoded slash trước khi routing. Nếu identifier chứa slash, hãy integration test qua toàn bộ network path. Với ID opaque, có thể dùng Base64URL hoặc representation không chứa slash.

## 5. queryParam và queryParams

### 5.1. queryParam(name, value...)

`queryParam` thêm query parameter:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/v1/products")
        .queryParam("category", "{category}")
        .queryParam("page", "{page}")
        .queryParam("size", "{size}")
        .encode()
        .buildAndExpand("books", 2, 20)
        .toUri();
~~~

Kết quả:

~~~text
https://api.example.test/v1/products?category=books&page=2&size=20
~~~

Một số query parameter phổ biến:

| Parameter | Ý nghĩa |
| --- | --- |
| `q` / `keyword` | Từ khóa tìm kiếm |
| `page` | Trang hiện tại |
| `size` / `limit` | Số phần tử mỗi trang |
| `sort` | Trường và hướng sắp xếp |
| `filter` | Điều kiện lọc |
| `expand` | Quan hệ hoặc dữ liệu mở rộng |
| `locale` | Ngôn ngữ hoặc vùng |

Các giá trị dùng để lọc, phân trang và sắp xếp thường phù hợp với query hơn path.

### 5.2. Nhiều giá trị cùng một key

`queryParam` hỗ trợ nhiều value:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/products")
        .queryParam("tag", "spring", "reactive", "webflux")
        .build()
        .toUri();
~~~

Kết quả:

~~~text
https://api.example.test/products?tag=spring&tag=reactive&tag=webflux
~~~

Có thể thêm lặp key qua nhiều lần gọi:

~~~java
builder.queryParam("tag", "{tag1}")
       .queryParam("tag", "{tag2}");
~~~

API đích cần hỗ trợ semantics repeated query key. Một số API mong đợi `tag=a&tag=b`, một số lại mong đợi `tag=a,b`; không tự chuyển sang comma-separated nếu contract không quy định.

### 5.3. queryParamIfPresent

Dùng `queryParamIfPresent` khi parameter chỉ nên xuất hiện nếu có giá trị:

~~~java
Optional<String> status = Optional.of("ACTIVE");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/users")
        .queryParamIfPresent("status", status)
        .build()
        .toUri();
~~~

Nếu Optional rỗng, key không được thêm.

Phân biệt:

- Không có key: client không gửi parameter.
- Có key với chuỗi rỗng: `q=`.
- Có key với giá trị: `q=reactive`.

Ba trạng thái này có thể mang ý nghĩa nghiệp vụ khác nhau.

### 5.4. replaceQueryParam

Khi builder đã có key nhưng muốn thay giá trị:

~~~java
builder.queryParam("page", 1)
       .replaceQueryParam("page", "{page}");
~~~

`replaceQueryParam` thay các value hiện có của key đó. Dùng khi builder được tạo từ template có query sẵn hoặc khi URI được lắp ghép qua nhiều bước.

### 5.5. queryParams với MultiValueMap

Khi có nhiều query parameter trong cấu trúc map:

~~~java
MultiValueMap<String, String> query =
        new LinkedMultiValueMap<>();

query.add("tag", "spring");
query.add("tag", "reactive");
query.add("page", "2");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/products")
        .queryParams(query)
        .build()
        .toUri();
~~~

`MultiValueMap` phù hợp vì một query key có thể có nhiều value. `Map<String, String>` thông thường không biểu diễn tự nhiên repeated key.

## 6. Encoding của WebClient và URI variables

WebClient dùng `UriBuilderFactory` để expand và encode URI template. Mặc định `DefaultUriBuilderFactory` sử dụng `TEMPLATE_AND_VALUES`:

- Encode URI template trước.
- Khi expand, encode chặt URI variables.
- Reserved characters nằm trong value được xem là dữ liệu, không được dùng để thay đổi cấu trúc URI.

Ví dụ:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/products/{category}")
        .queryParam("q", "{term}")
        .encode()
        .buildAndExpand(
                "books & media",
                "C++ WebFlux")
        .toUri();
~~~

Kết quả:

~~~text
/products/books%20%26%20media?q=C%2B%2B%20WebFlux
~~~

### 6.1. Các EncodingMode

| Mode | Cách hoạt động |
| --- | --- |
| `TEMPLATE_AND_VALUES` | Encode template trước và encode chặt URI variables khi expand |
| `VALUES_ONLY` | Giữ template, encode chặt variables trước khi expand |
| `URI_COMPONENT` | Expand trước rồi encode từng component |
| `NONE` | Không tự encode |

Với phần lớn request có dữ liệu động, `TEMPLATE_AND_VALUES` là lựa chọn hợp lý. Chỉ đổi mode khi contract cụ thể yêu cầu reserved character trong variable được giữ nguyên.

Cấu hình tường minh:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory(
                "https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient client = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

### 6.2. Không encode dữ liệu hai lần

Nếu input gốc là `a/b`, builder có thể tạo `a%2Fb`. Nếu truyền chuỗi đã encode `a%2Fb` như dữ liệu raw, dấu `%` có thể được encode thành `%25`, tạo `a%252Fb`.

Giữ dữ liệu raw và để một tầng builder encode. Không gọi `URLEncoder` hoặc `UriUtils.encode` trước khi truyền value vào factory đã encode.

### 6.3. Dấu cộng và khoảng trắng

- Space trong URI component thường thành `%20`.
- Literal plus thường cần thành `%2B`.
- `URLEncoder` dùng form semantics, có thể biểu diễn space bằng `+`.

Không dùng `URLEncoder` để encode toàn bộ URL. Dùng `queryParam` và URI variables cho query của WebClient.

## 7. DefaultUriVariables và biến dùng chung

`WebClient.Builder.defaultUriVariables` khai báo giá trị mặc định cho URI template variables khi dùng Map expansion:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .defaultUriVariables(Map.of(
                "version", "v1",
                "locale", "vi-VN"))
        .build();
~~~

Sau đó một template có thể dùng các biến mặc định:

~~~java
client.get()
        .uri("/api/{version}/products?locale={locale}")
        .retrieve()
        .bodyToMono(String.class);
~~~

Default variables hữu ích cho giá trị cấu hình dùng chung. Không dùng chúng để che giấu input quan trọng của một request cụ thể. Biến ảnh hưởng đến resource, tenant hoặc quyền truy cập nên được truyền tường minh và kiểm tra theo use case.

`defaultUriVariables` và `uriBuilderFactory` là hai shortcut có quan hệ loại trừ trên builder. Nếu cung cấp factory trực tiếp, hãy đặt default variables trên factory đó.

## 8. Phân biệt path, query, header và body

| Vị trí | Ví dụ | Khi dùng |
| --- | --- | --- |
| Path | `/products/{id}` | Định danh resource hoặc cấu trúc resource |
| Query | `?page=2&sort=name` | Filter, pagination, sorting và tùy chọn |
| Header | `Authorization: Bearer ...` | Authentication, metadata, content negotiation |
| Body | JSON hoặc binary | Payload của POST/PUT/PATCH |

Request tìm kiếm:

~~~java
Mono<ProductPage> result = client.get()
        .uri(builder -> builder
                .path("/v1/products")
                .queryParam("q", "{q}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "q", searchTerm,
                        "page", 0,
                        "size", 20)))
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Request tạo tài nguyên:

~~~java
Mono<Product> created = client.post()
        .uri("/v1/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateProductRequest(
                "Spring WebFlux Guide",
                "books"))
        .retrieve()
        .bodyToMono(Product.class);
~~~

Không đưa payload lớn hoặc dữ liệu bí mật vào query string. Body phù hợp hơn cho dữ liệu tạo/cập nhật; token nên dùng header hoặc security mechanism phù hợp.

## 9. Cấu trúc một request WebClient hoàn chỉnh

~~~java
Mono<ProductPage> result = client.get()
        .uri(builder -> builder
                .path("/v1/products/{category}")
                .queryParam("q", "{term}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "category", category,
                        "term", term,
                        "page", page,
                        "size", size)))
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "catalog-service")
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Các bước:

1. `get()` chọn HTTP GET.
2. `uri(...)` tạo path và query.
3. `accept(...)` yêu cầu response JSON.
4. `header(...)` thêm metadata cho request.
5. `retrieve()` xử lý response theo API retrieve.
6. `bodyToMono(ProductPage.class)` giải mã response body thành DTO.

Đây là đoạn minh họa trong service; cần khai báo client, category, term, page, DTO và dependency codec JSON tương ứng.

### 9.1. Xử lý lỗi HTTP với retrieve

Mặc định `retrieve()` chuyển response status 4xx/5xx thành `WebClientResponseException` nếu không có handler tùy chỉnh.

~~~java
Mono<ProductPage> result = client.get()
        .uri("/v1/products/{id}", productId)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.error(
                        new ProductNotFoundException(productId)))
        .bodyToMono(ProductPage.class);
~~~

Đây là ví dụ minh họa, giả định có `ProductNotFoundException`. Nếu cần đọc response body lỗi, dùng `response.bodyToMono(String.class)` trong callback và chuyển thành exception domain.

### 9.2. Khi nào dùng exchangeToMono?

`exchangeToMono` phù hợp khi response status quyết định cách đọc body:

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", productId)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createException()
                    .flatMap(Mono::error);
        });
~~~

Spring quản lý response body theo contract của exchange handler. Hãy consume body hoặc trả Publisher phù hợp; không giữ response body ngoài lifecycle rồi cố đọc lại.

## 10. Tổ chức WebClient bean trong Spring Boot

Trong Spring Boot, inject `WebClient.Builder` được auto-configure và tạo client riêng cho từng API:

~~~java
@Configuration
class PartnerClientConfig {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.test")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Service:

~~~java
@Service
class PartnerProductClient {

    private final WebClient client;

    PartnerProductClient(
            @Qualifier("partnerWebClient") WebClient client) {
        this.client = client;
    }

    Mono<Product> findById(UUID id) {
        return client.get()
                .uri("/v1/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);
    }
}
~~~

Nếu có nhiều API bên ngoài, đặt tên bean rõ ràng và tách cấu hình base URL theo từng service. Không dùng chung một base URL rồi thay host bằng dữ liệu động từ request.

Base URL, port và API prefix nên đến từ configuration:

~~~yaml
clients:
  catalog:
    base-url: https://catalog.example.test
~~~

Inject bằng `@ConfigurationProperties` hoặc `@Value` theo chuẩn cấu hình của dự án. Không hard-code production host trong business method.

## 11. Chương trình Java 17+ chạy được: WebClient, base URL, path và query

Ví dụ sau tạo một HTTP server cục bộ bằng JDK, rồi dùng WebClient gửi GET tới server đó. Server phản hồi raw request target để ta nhìn thấy path và query đã được encode.

Chương trình minh họa:

- Base URL được cấu hình một lần.
- Path template có biến category.
- Query có từ khóa, page và repeated tag.
- Giá trị có khoảng trắng, dấu cộng và ampersand được encode.
- Map expansion truyền biến theo tên.
- Assertion kiểm tra chính xác request target.

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Boot BOM quản lý Spring Framework, Reactor và Reactor Netty tương thích.

### 11.1. Cấu trúc dự án

~~~text
webclient-uri-demo/
  pom.xml
  src/main/java/example/webclient/WebClientUriDemo.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-uri-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. WebClientUriDemo.java

~~~java
package example.webclient;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

public final class WebClientUriDemo {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/v1/products", exchange -> {
            String path = exchange.getRequestURI().getRawPath();
            String query = exchange.getRequestURI().getRawQuery();

            String requestTarget = path +
                    (query == null ? "" : "?" + query);

            byte[] body = requestTarget.getBytes(
                    StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            String requestTarget = client.get()
                    .uri(builder -> builder
                            .path("/v1/products/{category}")
                            .queryParam("q", "{term}")
                            .queryParam("page", "{page}")
                            .queryParam("tag", "{tag1}")
                            .queryParam("tag", "{tag2}")
                            .build(Map.of(
                                    "category", "books & media",
                                    "term", "C++ & WebFlux",
                                    "page", 2,
                                    "tag1", "spring",
                                    "tag2", "reactive")))
                    .accept(MediaType.TEXT_PLAIN)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5));

            String expected =
                    "/v1/products/books%20%26%20media"
                    + "?q=C%2B%2B%20%26%20WebFlux"
                    + "&page=2&tag=spring&tag=reactive";

            if (!expected.equals(requestTarget)) {
                throw new AssertionError(
                        "Expected " + expected
                        + " but received " + requestTarget);
            }

            System.out.println("requestTarget=" + requestTarget);
        }
        finally {
            server.stop(0);
        }
    }
}
~~~

`block(Duration)` ở đây chỉ dùng tại `main` của chương trình demo để chờ request hoàn tất. Trong controller hoặc service reactive chạy trên event-loop, không gọi block; hãy trả Mono/Flux cho caller.

### 11.4. Chạy chương trình

Tại thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.webclient.WebClientUriDemo
~~~

**Stdout chính xác:**

~~~text
requestTarget=/v1/products/books%20%26%20media?q=C%2B%2B%20%26%20WebFlux&page=2&tag=spring&tag=reactive
~~~

Giải thích:

- Base URL chứa host và port cục bộ.
- `path` tạo segment category.
- `queryParam` thêm q, page và hai giá trị tag.
- `build(Map)` expand placeholder theo tên.
- `TEMPLATE_AND_VALUES` encode khoảng trắng thành `%20`, dấu cộng thành `%2B` và ampersand trong value thành `%26`.
- Server trả raw path và raw query; assertion xác nhận đúng chuỗi request target.

Chương trình không gọi internet hoặc API bên ngoài; server và client đều chạy trên máy local.

## 12. Kiểm thử URI và request WebClient

URI là một phần của API contract. Nên test các giá trị thông thường và giá trị biên.

### 12.1. Kiểm tra các trường hợp quan trọng

| Input | Điều cần xác nhận |
| --- | --- |
| ID số hoặc UUID | Placeholder được expand đúng |
| Category có khoảng trắng | Space được encode đúng |
| Giá trị có `+` | Literal plus không biến thành space |
| Query value có `&` hoặc `=` | Không tạo thêm parameter ngoài ý muốn |
| Unicode tiếng Việt | UTF-8 percent-encoding đúng |
| Optional rỗng | Query key được bỏ hoặc giữ rỗng theo contract |
| Repeated key | Tất cả giá trị xuất hiện theo đúng thứ tự |
| URI tuyệt đối | Base URL không ghi đè host tuyệt đối |
| Base URL có path prefix | Path cuối có prefix đúng |
| Encoded slash | Proxy/gateway/server xử lý nhất quán |

### 12.2. Test qua MockWebServer hoặc HTTP server local

Có thể dùng MockWebServer, WireMock hoặc server local để ghi nhận request thật. Xác nhận:

- HTTP method.
- Raw path và raw query.
- Headers.
- Request body.
- Response status và body.
- Số lần request được gửi.
- Timeout, error và cancellation nếu cần.

Không chỉ assert object URI trước khi gửi; connector hoặc network layer có thể xử lý URI theo cách cần được kiểm tra ở boundary.

### 12.3. Tránh test phụ thuộc thứ tự Map

Nếu dùng `Map.of`, không dựa vào thứ tự iteration của map để quyết định thứ tự query parameter. Hãy thêm query parameter theo thứ tự rõ ràng trong builder, rồi dùng map chỉ để expand placeholder đã khai báo. Nếu API ký request, tuân thủ canonicalization chính thức của API.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng URI tuyệt đối rồi kỳ vọng baseUrl được thêm vào | Host/base path không được áp dụng | Dùng URI tương đối hoặc template |
| Cấu hình cả baseUrl và uriBuilderFactory | Factory trực tiếp chi phối, baseUrl shortcut bị bỏ qua | Chọn một cơ chế cấu hình |
| Nối category vào path bằng chuỗi | Input có thể thêm segment hoặc query | Dùng path template và URI variable |
| Dùng query string nối thủ công | `&`, `#` hoặc `=` có thể đổi cấu trúc | Dùng queryParam |
| Dùng positional variables cho template dài | Dễ truyền nhầm đối số | Dùng Map theo tên |
| Dùng path thay cho pathSegment khi value là một segment opaque | Dữ liệu có slash có thể đổi cấu trúc path | Dùng pathSegment và strict encoding |
| Dùng URLEncoder cho cả URI | Các dấu cấu trúc bị encode như dữ liệu | Dùng UriBuilder theo component |
| Encode input trước khi truyền vào WebClient | Có thể double encode thành `%25` | Truyền raw value |
| Đổi EncodingMode sang NONE để sửa URL | Dữ liệu có thể trở thành cú pháp URI | Tìm đúng tầng đã encode trước |
| Dùng queryParam cho payload lớn | URL dài, lộ dữ liệu và có thể vượt giới hạn | Dùng request body |
| Đặt token trong query | Token xuất hiện trong access log/history | Dùng Authorization header |
| Nhận absolute URL do user kiểm soát | Có thể SSRF hoặc gọi host ngoài policy | Validate destination và redirect |
| Dùng một WebClient cho nhiều host rồi thay host theo input | Khó kiểm soát routing và security | Tạo client riêng theo service |
| Gọi block trong reactive request flow | Chặn event-loop | Compose Mono/Flux |
| Không xử lý 4xx/5xx | Exception không phản ánh domain error rõ | Dùng onStatus hoặc exchangeToMono |
| Dựa vào thứ tự Map để ký URI | Chữ ký có thể sai giữa các lần chạy | Canonicalize theo contract |
| Chỉ test URI string, không test request thực | Bỏ sót connector/proxy behavior | Test bằng local server hoặc mock server |

## 14. Bảo mật khi tạo URI cho WebClient

### 14.1. SSRF và URL tuyệt đối

Nếu ứng dụng nhận URL từ người dùng rồi gọi bằng WebClient, attacker có thể thử truy cập localhost, địa chỉ private trong mạng nội bộ, metadata service của cloud hoặc endpoint quản trị.

Biện pháp:

- Ưu tiên nhận service ID hoặc resource ID thay vì full URL.
- Dùng base URL lấy từ cấu hình tin cậy.
- Allowlist scheme, host và port.
- Kiểm tra DNS resolution và địa chỉ IP sau resolve.
- Kiểm soát redirect để không vượt destination policy.
- Cân nhắc proxy, retry và DNS rebinding trong threat model.

### 14.2. Path và query không phải nơi chứa secret

Không đưa password, API key, bearer token hoặc dữ liệu nhạy cảm vào URI. URL thường được ghi vào access log, trace, browser history và hệ thống monitoring. Dùng header hoặc body theo API contract.

### 14.3. Không tin dữ liệu path/query chỉ vì đã encode

Encoding bảo vệ cấu trúc URI, không xác nhận dữ liệu có hợp lệ về nghiệp vụ. Vẫn phải validate:

- ID có tồn tại không.
- User có quyền truy cập resource không.
- Query filter có được phép không.
- Page/size có nằm trong giới hạn không.
- Sort field có nằm trong allowlist không.
- Category có thuộc tập giá trị hợp lệ không.

## 15. Checklist trước khi đưa WebClient URI vào production

- [ ] Base URL đến từ cấu hình đáng tin cậy.
- [ ] Một client được tổ chức theo từng external API hoặc service boundary.
- [ ] Dùng URI tương đối khi muốn áp dụng base URL.
- [ ] Biết URI tuyệt đối sẽ bỏ qua base URL.
- [ ] Chọn một trong baseUrl hoặc uriBuilderFactory.
- [ ] Path template không được tạo bằng input chưa tin cậy.
- [ ] Dùng pathSegment khi value phải thuộc một segment.
- [ ] Dùng queryParam/queryParams cho query.
- [ ] Dùng Map để expand nhiều URI variables theo tên.
- [ ] Encoding mode rõ ràng; ưu tiên TEMPLATE_AND_VALUES cho opaque values.
- [ ] Không encode dữ liệu hai lần.
- [ ] Repeated, absent và empty query parameter đúng contract.
- [ ] Headers, query và body được dùng đúng mục đích.
- [ ] Có timeout và error handling phù hợp.
- [ ] Không block trong reactive request path.
- [ ] Có SSRF protection nếu destination có thể bị input ảnh hưởng.
- [ ] Không đưa secret vào URI.
- [ ] Test raw path/query, method, headers, body, status và redirect.
- [ ] Test Unicode, reserved characters và encoded slash qua network path thực tế.

## 16. Tự kiểm tra

**Câu 1.** `baseUrl` được áp dụng cho mọi request của WebClient không?

Không. Nó được dùng cho URI tương đối. URI tuyệt đối hoặc `URI` hoàn chỉnh được truyền trực tiếp sẽ dùng địa chỉ của chính URI đó.

**Câu 2.** `WebClient.Builder.baseUrl` và `uriBuilderFactory` có thể dùng đồng thời để cộng dồn cấu hình không?

Không. `uriBuilderFactory` là cơ chế cấu hình trực tiếp và chi phối shortcut `baseUrl`.

**Câu 3.** Khi nào dùng `uri(builder -> ...)`?

Khi cần xây path, query, optional values hoặc nhiều thành phần URI một cách linh hoạt trong một request.

**Câu 4.** `path` và `pathSegment` khác nhau thế nào?

`path` thêm một đoạn path template; `pathSegment` thêm từng segment riêng và thể hiện rõ ranh giới segment.

**Câu 5.** Làm sao thêm nhiều value cùng một query key?

Dùng `queryParam("tag", "a", "b")` hoặc gọi queryParam nhiều lần với cùng key.

**Câu 6.** Khi nào dùng `queryParamIfPresent`?

Khi parameter chỉ nên xuất hiện nếu Optional có giá trị; Optional rỗng thì không thêm key.

**Câu 7.** Vì sao Map hữu ích khi expand URI variables?

Map liên kết value theo tên placeholder, giảm nguy cơ truyền nhầm positional arguments khi template có nhiều biến.

**Câu 8.** WebClient mặc định encode URI variables theo mode nào trong Spring Framework hiện tại?

`TEMPLATE_AND_VALUES`. Nó encode template trước và encode chặt URI variables khi expand.

**Câu 9.** Có nên truyền URI đã percent-encode vào WebClient template variables không?

Thông thường không. Truyền raw value và để factory encode một lần; nếu truyền giá trị đã encode, dấu `%` có thể bị encode tiếp.

**Câu 10.** `block()` có luôn bị cấm khi dùng WebClient không?

Không. Có thể dùng ở boundary đồng bộ như chương trình command-line hoặc test. Không gọi block trên event-loop hoặc trong reactive request path.

**Câu 11.** Nếu query key bị lặp, WebClient có tự gộp thành một value không?

Không. Builder có thể tạo repeated key; server nhận và diễn giải theo contract API.

**Câu 12.** Base URL có tự bảo vệ ứng dụng khỏi SSRF không?

Không. URI tuyệt đối có thể bỏ qua base URL; ứng dụng cần validate destination và redirect theo security policy.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient reactive API, gửi request và xử lý response.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): create, builder, base URL, uriBuilderFactory, default headers, filters và connector.
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriBuilder, UriComponentsBuilder, UriBuilderFactory, path/query và URI encoding.
- [WebClient.Builder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html): baseUrl, defaultUriVariables và uriBuilderFactory.
- [WebClient.UriSpec JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.UriSpec.html): các overload uri(String), uri(URI) và uri(Function).
- [UriBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriBuilder.html): path, pathSegment, queryParam, queryParams, build và URI variables.
- [DefaultUriBuilderFactory JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html): base URI, default variables và EncodingMode.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): URI components, reserved/unreserved characters và percent-encoding.

**Ghi nhớ:** Cấu hình base URL một lần cho từng API, dùng `uri(builder -> ...)` để ghép path và query, truyền dữ liệu qua URI variables theo tên và để factory encode đúng một lần. `pathSegment` biểu diễn ranh giới segment; `queryParam` biểu diễn query values. URI tuyệt đối có thể bỏ qua base URL, còn việc kiểm tra host, quyền truy cập và dữ liệu nghiệp vụ vẫn thuộc trách nhiệm của ứng dụng.