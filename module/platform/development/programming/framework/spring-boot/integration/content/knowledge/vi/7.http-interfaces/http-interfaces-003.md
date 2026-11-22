# Kết nối HTTP interface với RestClient hoặc WebClient adapter

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot được sử dụng để kết nối hệ thống qua HTTP client, database, cache, message broker và các adapter của Spring Integration. Một luồng tích hợp thường cần gọi dịch vụ Catalog, Inventory hoặc Payment qua HTTP. Nếu mỗi nơi đều tự ghép URL, tạo request, giải mã JSON và kiểm tra lỗi, code sẽ trùng lặp và hợp đồng với đối tác khó được kiểm soát.

**HTTP interface** của Spring Framework cho phép mô tả API phía client bằng **interface Java và các annotation** như `@HttpExchange`, `@GetExchange` hoặc `@PostExchange`. Sau đó, `HttpServiceProxyFactory` tạo một proxy thực thi lời gọi HTTP thông qua một **adapter**:

- `RestClientAdapter`: kết nối đến `RestClient` đồng bộ.
- `WebClientAdapter`: kết nối đến `WebClient`, phù hợp với các return type reactive như `Mono` và `Flux`.

Bài thuộc chương **HTTP interface**, tập trung vào **kết nối HTTP interface với RestClient hoặc WebClient adapter** và cách áp dụng trong kiến trúc tích hợp Spring Boot. Các ví dụ gắn với quản lý cấu hình, hợp đồng dữ liệu, transaction, lỗi, xử lý trùng lặp, kiểm thử và observability.

Sau bài học, bạn có thể:

1. Tạo HTTP interface bằng `@HttpExchange` và những annotation đặc tả phương thức HTTP.
2. Đăng ký một HTTP client proxy từ `RestClientAdapter` hoặc `WebClientAdapter`.
3. Tiêm các builder do Spring Boot quản lý để giữ cấu hình HTTP, codec và khả năng observation.
4. Chọn return type đồng bộ/reactive theo cách ứng dụng tiêu thụ dữ liệu.
5. Tách proxy HTTP khỏi adapter nghiệp vụ, ánh xạ lỗi 404/429/5xx và đặt timeout/retry phù hợp.
6. Kiểm thử method, URL, headers, request body, response body và tích hợp cấu hình mà không gọi hệ thống đối tác thật.

> **Ranh giới:** HTTP interface chỉ là **hợp đồng phía client** và proxy thực thi HTTP. Nó không tự tạo API server, không tự sinh transaction phân tán, không thực hiện retry/idempotency mặc định cho mọi request và không tự bảo đảm rằng downstream đã áp dụng nghiệp vụ đúng một lần.

## 1. HTTP interface giải quyết vấn đề gì?

Thay vì để nhiều service tự thao tác `RestClient`:

~~~java
// Mỗi caller tự viết lại HTTP request:
ProductDto product = restClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .body(ProductDto.class);
~~~

ta định nghĩa một interface duy nhất:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1/products", accept = "application/json")
public interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);
}
~~~

Caller sau đó chỉ gọi:

~~~java
ProductDto product = catalogHttpApi.findById("P-100");
~~~

`CatalogHttpApi` là **đặc tả HTTP**, không tự động có implementation chỉ vì thêm annotation. Một bean proxy phải được tạo bằng `HttpServiceProxyFactory` và adapter phù hợp.

~~~mermaid
flowchart LR
    A["Order / Catalog use case"] --> B["CatalogGateway"]
    B --> C["CatalogHttpApi interface"]
    C --> D["HttpServiceProxyFactory proxy"]
    D --> E{"HttpExchangeAdapter"}
    E -->|"Blocking"| F["RestClientAdapter"]
    E -->|"Reactive"| G["WebClientAdapter"]
    F --> H["RestClient"]
    G --> I["WebClient"]
    H --> J["Catalog HTTP API"]
    I --> J
~~~

Tách hai khái niệm dễ bị nhầm:

- **`RestClientAdapter` / `WebClientAdapter` của Spring Framework** là lớp nối HTTP service proxy với HTTP client.
- **Adapter nghiệp vụ `CatalogGateway`** là lớp của ứng dụng chuyển lỗi HTTP, dữ liệu DTO và kết quả kỹ thuật thành hợp đồng nghiệp vụ cho use case.

HTTP interface là một **consumer-side contract**. Server của đối tác có thể được viết bằng bất kỳ nền tảng nào miễn là tuân thủ HTTP contract này. Annotation phía client không làm server tự phát hành endpoint tương ứng.

## 2. Thành phần và API chính

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `@HttpExchange` | Đặt metadata HTTP chung ở interface hoặc method | Base path, Accept/Content-Type |
| `@GetExchange` | Khai báo HTTP GET | Đọc sản phẩm theo ID |
| `@PostExchange` | Khai báo HTTP POST | Tạo hoặc yêu cầu xử lý |
| `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | Khai báo các method còn lại | Cập nhật, xóa tài nguyên |
| `@PathVariable` | Điền biến vào URI template | `/v1/products/{id}` |
| `@RequestParam` | Tạo query parameter | `?active=true` |
| `@RequestHeader` | Đưa header vào request | `Idempotency-Key` |
| `@RequestBody` | Serialize payload thành request body | DTO JSON |
| `@RequestPart` | Một phần của multipart request | Upload file/metadata |
| `HttpServiceProxyFactory` | Tạo dynamic proxy cho interface | `createClient(CatalogHttpApi.class)` |
| `RestClientAdapter` | Gắn proxy với RestClient | Blocking client |
| `WebClientAdapter` | Gắn proxy với WebClient | Reactive client |
| `RestClient.Builder` / `WebClient.Builder` | Cấu hình baseUrl, header, interceptor/filter và transport | Builder do Boot inject |

Cùng một URL có thể được khai báo bằng annotation ở nhiều cấp. Ví dụ `@HttpExchange(url = "/v1/products")` trên interface và `@GetExchange("/{id}")` trên method tạo đường dẫn tới `/v1/products/{id}`. URL gốc `https://catalog.example.org` được khai báo trên HTTP client builder.

### 2.1. Các kiểu tham số thường gặp

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(
        url = "/v1/products",
        accept = MediaType.APPLICATION_JSON_VALUE)
public interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);

    @GetExchange
    ProductPageDto list(
            @RequestParam("page") int page,
            @RequestParam("size") int size,
            @RequestParam("active") boolean active);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ProductDto create(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody CreateProductRequest request);
}
~~~

Khi dùng `@PathVariable` / `@RequestParam`, nên ghi rõ tên trong annotation để code không phụ thuộc tùy chọn biên dịch giữ tên tham số. Đây là interface Java: không có thân method vì proxy thực hiện lời gọi.

Ví dụ DTO Java 17+:

~~~java
public record ProductDto(
        String id,
        String name,
        boolean active) {
}

public record CreateProductRequest(String name) {
}

public record ProductPageDto(
        java.util.List<ProductDto> items,
        int page,
        long totalElements) {
}
~~~

Các record trên chỉ minh họa JSON contract. Trong thực tế, phải thỏa thuận rõ tên field, quy tắc null, version của API, ý nghĩa ID, pagination và dữ liệu trả về khi danh sách rỗng.

### 2.2. Return type quyết định cách sử dụng

| Return type HTTP interface | Phù hợp với | Lưu ý |
| --- | --- | --- |
| `ProductDto` | `RestClientAdapter` / ứng dụng đồng bộ | Caller chờ tới khi request kết thúc |
| `ResponseEntity<ProductDto>` | Blocking client | Cần status/headers ngoài body |
| `void` | Lời gọi không có payload trả về | Không có nghĩa downstream chắc chắn đã commit side effect |
| `Mono<ProductDto>` | `WebClientAdapter` | Chỉ chạy HTTP khi publisher được subscribe |
| `Flux<ProductDto>` | `WebClientAdapter` | Hợp đồng stream/JSON collection cần được xác nhận |
| `Mono<ResponseEntity<ProductDto>>` | `WebClientAdapter` | Cần cả status, headers và body trong luồng reactive |

`RestClientAdapter` phục vụ các kiểu xử lý **blocking**, nên không khai báo một method trả `Mono` chỉ vì muốn giữ interface giống WebClient. Để hỗ trợ reactive, chọn `WebClientAdapter` và khai báo return type tương ứng. Một số version cho phép WebClientAdapter xử lý method đồng bộ bằng cách block, nhưng điều đó không biến method thành non-blocking; chỉ dùng khi hiểu rõ thread và timeout.

## 3. Dependency và điều kiện phiên bản

### 3.1. RestClient

`RestClient` được giới thiệu từ **Spring Framework 6.1**, được Spring Boot hỗ trợ từ dòng **3.2**. Cấu hình Gradle thường gặp với ứng dụng Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Dòng Boot 4 có thể phân tách một số starter phục vụ web MVC theo cách đặt tên mới; dự án phải dùng starter do **phiên bản Boot đang áp dụng** hỗ trợ. Bài này tập trung vào API Spring Framework và không yêu cầu cố định một major version để hiểu cơ chế proxy.

### 3.2. WebClient

`WebClient` thuộc Spring WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Việc thêm WebFlux starter để dùng client trong ứng dụng MVC **không mặc nhiên đổi MVC server thành reactive server** khi web MVC đã hiện diện. Tuy vậy, lựa chọn return type và điểm chặn/block vẫn phải tuân thủ mô hình xử lý của caller.

Spring HTTP interface đã có từ Spring Framework 6.0. Một số API của `HttpServiceProxyFactory` và adapter đã được thay đổi tên hoặc builder giữa các bản 6.x; ví dụ bên dưới dùng cách tạo factory phổ biến trong Spring Framework **6.1+ và 7.x**:

~~~java
HttpServiceProxyFactory.builderFor(adapter)
        .build()
        .createClient(MyApi.class);
~~~

Với hướng dẫn cũ cho Spring 6.0, có thể gặp `HttpServiceProxyFactory.builder(...)` hoặc API adapter khác. Không trộn imports và API giữa các phiên bản. Nếu một ứng dụng đang dùng Spring Boot 3.0/3.1, cần đối chiếu khả năng dùng RestClient vì `RestClient` chưa có ở các dòng Spring Framework tương ứng.

## 4. Dùng RestClientAdapter cho HTTP interface đồng bộ

### 4.1. Đưa cấu hình endpoint ra ngoài mã nguồn

Ví dụ Catalog API có địa chỉ khác nhau theo môi trường:

~~~yaml
# application.yml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
~~~

`https://catalog.example.org` là địa chỉ minh họa. Ở production, dùng URL chính thức và cấp các thông tin bí mật từ secret manager hoặc môi trường. Không đưa username, token hoặc API key thật vào file theo dõi version.

Ánh xạ cấu hình bằng `@ConfigurationProperties`:

~~~java
// CatalogHttpProperties.java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogHttpProperties(URI baseUrl) {
}
~~~

`@ConfigurationProperties` cho phép kiểm soát kiểu dữ liệu và dễ kiểm thử binding. Trong production nên kiểm tra giá trị bắt buộc và scheme/host hợp lệ bằng Bean Validation hoặc validation riêng; ví dụ record giữ ngắn để tập trung vào cách nối interface với client.

### 4.2. Tạo RestClient rồi nối với HttpServiceProxyFactory

~~~java
// CatalogRestClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogHttpProperties.class)
public class CatalogRestClientConfiguration {

    @Bean
    CatalogHttpApi catalogHttpApi(
            RestClient.Builder bootRestClientBuilder,
            CatalogHttpProperties properties) {

        RestClient restClient = bootRestClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeader(
                        "Accept", MediaType.APPLICATION_JSON_VALUE)
                .build();

        RestClientAdapter adapter =
                RestClientAdapter.create(restClient);

        HttpServiceProxyFactory proxyFactory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return proxyFactory.createClient(CatalogHttpApi.class);
    }
}
~~~

Diễn giải:

1. Spring Boot inject `RestClient.Builder` đã được Boot cấu hình.
2. Builder nhận base URL riêng của Catalog.
3. `build()` tạo `RestClient` dùng lại an toàn trong các request.
4. `RestClientAdapter.create(restClient)` chuyển RestClient sang hợp đồng `HttpExchangeAdapter` mà factory chấp nhận.
5. `HttpServiceProxyFactory.builderFor(adapter).build()` cấu hình nhà máy proxy.
6. `createClient(CatalogHttpApi.class)` trả một implementation của interface, đăng ký thành bean `catalogHttpApi`.

Cần lưu ý `Accept: application/json` đã được khai báo trong `@HttpExchange(accept = ...)` ở interface; header mặc định trên builder trong ví dụ chỉ minh họa khả năng cấu hình builder. Một dự án nên thống nhất nguồn khai báo header tránh cấu hình lặp không cần thiết.

### 4.3. Gọi từ application service

~~~java
// CatalogLookupService.java
import org.springframework.stereotype.Service;

@Service
public class CatalogLookupService {

    private final CatalogHttpApi catalogApi;

    public CatalogLookupService(CatalogHttpApi catalogApi) {
        this.catalogApi = catalogApi;
    }

    public ProductDto load(String productId) {
        return catalogApi.findById(productId);
    }
}
~~~

`load(...)` là lời gọi **đồng bộ**: thread gọi đang chờ hoàn tất HTTP response hoặc một lỗi/timeout. Với Spring MVC controller, kiểu này thường dễ sử dụng; với một luồng WebFlux event loop, không đặt lời gọi blocking vào event-loop.

**Tại sao nên inject builder của Boot?** Nó có thể đã được cấu hình request factory, message converters, HTTP client observation và các customizer phù hợp phiên bản. Tạo `RestClient.create(...)` trực tiếp vẫn là API hợp lệ nhưng không mặc nhiên nhận tất cả cấu hình do Boot thiết lập trên builder được quản lý.

## 5. Dùng WebClientAdapter cho HTTP interface reactive

Reactive interface nên diễn tả kết quả bằng `Mono` / `Flux`. Để không pha trộn hai hợp đồng khác nhau, tạo interface riêng nhưng cùng API phía server:

~~~java
// CatalogReactiveHttpApi.java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange(url = "/v1/products", accept = "application/json")
public interface CatalogReactiveHttpApi {

    @GetExchange("/{id}")
    Mono<ProductDto> findById(
            @PathVariable("id") String id);
}
~~~

Spring Boot tạo và quản lý `WebClient.Builder` khi các dependency/điều kiện phù hợp. Tạo proxy:

~~~java
// CatalogWebClientConfiguration.java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogHttpProperties.class)
public class CatalogWebClientConfiguration {

    @Bean
    CatalogReactiveHttpApi catalogReactiveHttpApi(
            WebClient.Builder bootWebClientBuilder,
            CatalogHttpProperties properties) {

        WebClient webClient = bootWebClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .build();

        WebClientAdapter adapter =
                WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(
                CatalogReactiveHttpApi.class);
    }
}
~~~

Có thể đăng ký cả hai proxy trong cùng ứng dụng, nhưng khi một module dùng một kiểu gọi nhất quán, chỉ cần loại client phù hợp để tránh thêm resource và cấu hình không cần thiết.

### 5.1. Dùng proxy trong reactive service

~~~java
// CatalogReactiveGateway.java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogReactiveGateway {

    private final CatalogReactiveHttpApi catalogApi;

    public CatalogReactiveGateway(
            CatalogReactiveHttpApi catalogApi) {
        this.catalogApi = catalogApi;
    }

    public Mono<ProductDto> findProduct(String productId) {
        return catalogApi.findById(productId);
    }
}
~~~

`Mono<ProductDto>` là publisher mô tả quá trình xử lý. HTTP request thường bắt đầu khi **subscriber** subscribe, chẳng hạn khi WebFlux framework nhận `Mono` từ controller và quản lý subscription.

Không gọi `subscribe()` tùy tiện trong gateway chỉ để “kích hoạt” request, vì lỗi và kết quả khó được truyền về luồng nghiệp vụ. Tránh `block()` trên Reactor event loop; nếu cần bước blocking vì gọi database JDBC, phải cô lập đúng scheduler/thread hoặc chọn kiến trúc imperative nhất quán.

### 5.2. WebClientAdapter không mặc định thay đổi hợp đồng server

Cả hai client đều gửi HTTP đến Catalog API, nhưng có khác biệt:

| Điểm | RestClientAdapter | WebClientAdapter |
| --- | --- | --- |
| Thư viện client | `RestClient` | `WebClient` |
| Mô hình chủ đạo | Blocking | Reactive/non-blocking với transport phù hợp |
| Kiểu trả về khuyên dùng | DTO, `ResponseEntity<DTO>` | `Mono<DTO>`, `Flux<DTO>` |
| Đường đi lỗi | Thường ném exception trực tiếp | Error signal trong publisher |
| Timeout | HTTP request factory + chính sách application | Connector/transport + timeout operator khi phù hợp |
| Spring MVC | Tự nhiên | Có thể dùng nhưng cần chủ động quản lý reactive boundary |
| Spring WebFlux | Không phù hợp nếu gọi trực tiếp trên event-loop | Tự nhiên |
| Observation | Builder do Boot quản lý | Builder do Boot quản lý |

Chọn theo **mô hình tiêu thụ thực tế**, không chọn `WebClient` chỉ vì cần gọi HTTP, hoặc ép `RestClient` trả `Mono` bằng cách wrap một lời gọi blocking trong `Mono.just(...)`.

## 6. Hợp đồng HTTP: URL, headers, body, status và lỗi

### 6.1. Đặt base URL và đường dẫn đúng phạm vi

Nếu base URL là `https://catalog.example.org` và interface có:

~~~java
@HttpExchange(url = "/v1/products")
public interface CatalogHttpApi {
    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") String id);
}
~~~

lời gọi `findById("P-100")` tạo HTTP request tới `https://catalog.example.org/v1/products/P-100` theo cấu hình adapter và URI template.

Đặt path variable vào `@PathVariable` để framework thực hiện mở rộng/mã hóa URI; đừng tự nối URL từ chuỗi người dùng. Với đường dẫn đã chứa base path, cần kiểm tra dấu `/` và khả năng ghi đè đường dẫn khi kết hợp baseUrl, nhất là khi ứng dụng có proxy prefix.

Không dùng một HTTP interface chấp nhận **full URL không kiểm soát từ người dùng** rồi gửi tới hostname bất kỳ: đó là nguy cơ SSRF. Chỉ cho phép các downstream được cấu hình và xác thực.

### 6.2. Headers và phương thức POST

Một số thao tác cần header theo từng request, đặc biệt khi token hoặc idempotency key thay đổi theo caller:

~~~java
@PostExchange(contentType = "application/json")
ProductDto create(
        @RequestHeader("Idempotency-Key") String idempotencyKey,
        @RequestBody CreateProductRequest request);
~~~

Đặt `Idempotency-Key` tại call site (do ứng dụng tạo theo hợp đồng nghiệp vụ) giúp mỗi lần retry cùng tác động giữ **cùng một khóa**, trong khi tác động nghiệp vụ khác phải có khóa khác. Server đối tác cũng phải hỗ trợ xử lý idempotency key; header tự nó không bảo đảm chống trùng.

Với `Authorization`, tránh đặt token của người dùng A trong `defaultHeader(...)` của một singleton client dùng chung cho nhiều người. Hãy dùng đúng cơ chế auth của transport/filter/interceptor, hoặc truyền header cho từng request sau khi xác thực và phân quyền. Đảm bảo không forward nhầm credential giữa các downstream.

### 6.3. Cần response headers/status thì chọn return type phù hợp

Nếu adapter cần HTTP status, ETag hoặc header phân trang, có thể chọn `ResponseEntity<ProductDto>`:

~~~java
@GetExchange("/{id}")
org.springframework.http.ResponseEntity<ProductDto> findWithMetadata(
        @PathVariable("id") String id);
~~~

Ở phía reactive, dùng `Mono<ResponseEntity<ProductDto>>`. Không gán mặc định “HTTP 200 và body hợp lệ” cho mọi response: API có thể trả 204, 206, 304 hoặc 404 với những ý nghĩa khác nhau. Việc giải mã body rỗng và chuyển lỗi phải bám đúng hợp đồng server.

### 6.4. Phân loại lỗi

| Tình huống | RestClient | WebClient | Phản ứng ở adapter nghiệp vụ |
| --- | --- | --- | --- |
| 2xx + JSON hợp lệ | DTO/ResponseEntity | `Mono`/`Flux` có kết quả | Map thành model/port result |
| 204/no body | Có thể không có body | Có thể hoàn tất rỗng | Quy định rõ kết quả rỗng |
| 404 | Thường `RestClientResponseException` phù hợp status | `WebClientResponseException.NotFound` | Phân biệt “không tồn tại” và lỗi |
| 400/422 | HTTP client error | HTTP error signal | Không retry mù quáng; sửa contract/data |
| 401/403 | Lỗi xác thực/phân quyền | Lỗi xác thực/phân quyền | Kiểm tra secret/permissions |
| 429/503 | Lỗi rate limit/downstream | Error signal | Retry giới hạn, backoff theo contract |
| Network/DNS/timeout | Exception ở tầng I/O/client | Thường `WebClientRequestException` hoặc timeout signal | Phân loại connection vs deadline |
| JSON không hợp schema | Deserialization error | Decoding error signal | Tương thích version/contract test |

Một HTTP interface **không tự chuyển 404 thành `Optional.empty()` theo nghiệp vụ**. Nên đặt chính sách ở gateway để controller/use case không biết chi tiết HTTP status.

## 7. Đặt adapter nghiệp vụ trước HTTP interface

`CatalogHttpApi` biết URL/method/body; ứng dụng muốn biết “có tìm thấy sản phẩm không”. Hai trách nhiệm này khác nhau.

Ví dụ port nghiệp vụ:

~~~java
// ProductCatalogPort.java
import java.util.Optional;

public interface ProductCatalogPort {
    Optional<ProductDto> findById(String productId);
}
~~~

Triển khai port qua HTTP interface đồng bộ:

~~~java
// HttpProductCatalogAdapter.java
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpProductCatalogAdapter
        implements ProductCatalogPort {

    private final CatalogHttpApi api;

    public HttpProductCatalogAdapter(CatalogHttpApi api) {
        this.api = api;
    }

    @Override
    public Optional<ProductDto> findById(String productId) {
        try {
            return Optional.ofNullable(api.findById(productId));
        } catch (RestClientResponseException exception) {
            if (exception.getStatusCode().value() == 404) {
                return Optional.empty();
            }
            throw new CatalogUnavailableException(
                    "Không thể đọc dữ liệu Catalog",
                    exception);
        }
    }
}
~~~

Exception nghiệp vụ/adapter:

~~~java
public class CatalogUnavailableException extends RuntimeException {
    public CatalogUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ở ví dụ, 404 được diễn giải là không tìm thấy; các HTTP status khác được chuyển thành lỗi adapter. Trong production nên phân biệt lỗi **tạm thời** (để retry) và lỗi **vĩnh viễn** (400/403/schema) bằng các exception/kiểu kết quả cụ thể hơn. Không ghi raw response body chứa PII hoặc token vào log.

Tương tự, với WebClient proxy:

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

public Mono<ProductDto> findOptional(String productId) {
    return catalogReactiveApi.findById(productId)
            .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    ignored -> Mono.empty());
}
~~~

Nhánh `onErrorResume` chỉ áp dụng cho 404; lỗi kết nối hoặc 5xx vẫn lan ra, để tầng orchestration thực hiện policy phù hợp. Đừng dùng `onErrorResume(ignored -> Mono.empty())` cho mọi exception vì điều đó có thể che outage thành “không có sản phẩm”.

### 7.1. Hợp đồng API phải được version hóa

Nếu đối tác đổi field `active` từ boolean sang string, một HTTP proxy vẫn có thể gửi request thành công nhưng deserialization thất bại. Vì vậy:

- Định nghĩa API path/version, DTO, enum, định dạng ngày/giờ, giá trị null và cấu trúc lỗi.
- Phân biệt DTO của downstream và domain model nội bộ; dùng mapper khi chúng có lifecycle khác nhau.
- Không bắt mọi lỗi JSON rồi trả object mặc định có vẻ hợp lệ.
- Tổ chức contract test với phản hồi thật hoặc fixture được thống nhất với đối tác.
- Tránh phát tán `RestClientResponseException`/`WebClientResponseException` ra domain/use case không cần biết HTTP.

## 8. Timeout, retry và tránh xử lý trùng

HTTP interface giúp khai báo request; timeout và retry cần được cấu hình cho **transport và operation** tương ứng.

### 8.1. Ba loại timeout thường bị lẫn

1. **Connect timeout**: thời gian thiết lập kết nối TCP/TLS tới downstream.
2. **Read/response timeout**: thời gian chờ dữ liệu phản hồi ở HTTP transport.
3. **Application deadline**: thời gian tối đa cho luồng nghiệp vụ tổng thể, có thể bao gồm queue, nhiều request, retry và chuyển đổi dữ liệu.

Ví dụ với một WebClient reactive flow:

~~~java
public Mono<ProductDto> findWithDeadline(String id) {
    return catalogReactiveApi.findById(id)
            .timeout(java.time.Duration.ofSeconds(5));
}
~~~

`timeout(...)` là giới hạn của Reactor pipeline tại vị trí đặt toán tử, **không thay thế hoàn toàn** connect timeout và response timeout của HTTP client. Nếu gọi nhiều downstream nối tiếp, application deadline cần phản ánh tổng thời gian, không chỉ từng request.

Với RestClient, cấu hình timeout ở request factory/HTTP client được Boot chọn và qua extension point tương ứng của version. Spring Boot 3.x/4.x khác nhau ở các thuộc tính HTTP client chung, nên không chép nguyên cấu hình một version sang version khác. Nếu thay request factory hoặc WebClient connector thủ công, cần kiểm tra xem mình có bỏ qua connection pooling, shared resources hoặc observation mà Boot đã cấu hình hay không.

### 8.2. Retry theo HTTP method và side effect

| Method và nghiệp vụ | Có thể retry? | Điều kiện |
| --- | --- | --- |
| GET tra cứu thuần đọc | Thường có thể | Giới hạn số lần, chỉ lỗi tạm thời, backoff |
| PUT đặt trạng thái đã xác định | Có thể nếu server thực sự thực hiện idempotent | Theo hợp đồng của API và trạng thái |
| POST tạo đơn hàng/thanh toán | Chỉ khi có cơ chế chống trùng | Giữ cùng `Idempotency-Key` khi retry |
| DELETE | Có thể tùy hợp đồng | Phải rõ 404 khi resource đã bị xóa là thành công hay lỗi |
| HTTP timeout sau request ghi | Kết quả **không xác định** | Đối soát trạng thái trước khi gửi lại hoặc dùng idempotency key |

Ví dụ pipeline reactive retry **chỉ một loại lỗi tạm thời**, có giới hạn:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import org.springframework.web.reactive.function.client.WebClientResponseException;

public Mono<ProductDto> findWithRetry(String id) {
    return catalogReactiveApi.findById(id)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(200))
                            .filter(error ->
                                    error instanceof
                                            WebClientResponseException.ServiceUnavailable));
}
~~~

Đây là ví dụ tối giản: retry tối đa **hai lần sau lần gọi đầu** khi HTTP 503. Trong thực tế có thể cần thêm 429, lỗi mạng phù hợp, jitter, deadline tổng, circuit breaker và phân loại exception theo chính sách. Không retry mọi 4xx/5xx, và không thêm nhiều tầng retry (HTTP client, service, broker consumer) mà không giới hạn tổng số request.

### 8.3. Transaction và outbox

Giả sử use case cập nhật SQL rồi gọi HTTP interface để gửi đơn hàng:

~~~text
DB COMMIT thành công
    |
    +-- POST /orders gặp timeout
           |
           +-- Không chắc đối tác đã tạo đơn hay chưa
~~~

`@Transactional` của SQL không biến HTTP request thành một thành viên ACID trong cùng transaction. Một thiết kế bền vững có thể ghi **business row và outbox row cùng transaction DB**, sau đó worker/broker consumer gửi HTTP bằng idempotency key và lưu kết quả đối soát.

Khi nhận một message broker có thể bị redelivery, adapter HTTP cũng phải giữ idempotency key ổn định từ event/business identity, không dùng traceId hoặc message-id được tạo lại cho mỗi attempt.

## 9. Tùy chỉnh client: cấu hình riêng và cấu hình toàn cục

Một ứng dụng có thể gọi Catalog API, Payment API và Inventory API với base URL, timeout, auth và header khác nhau. Tránh giữ một mutable builder rồi liên tục thay baseUrl/header cho các hệ thống đó.

| Nhu cầu | Cách thực hiện |
| --- | --- |
| URL và header riêng của Catalog | Tùy chỉnh builder khi tạo bean Catalog proxy |
| URL và auth riêng của Payment | Tạo bean Payment RestClient/WebClient khác |
| Các HTTP client cùng chính sách chung | Dùng customizer do Boot hỗ trợ, theo version |
| Cùng builder được giữ lại để tạo nhiều client | Dùng `builder.clone()` trước mỗi nhánh hoặc injection riêng |
| Thêm client từ client có sẵn | `restClient.mutate()` hoặc `webClient.mutate()` rồi `build()` |
| Instrumentation metrics/tracing | Ưu tiên builder do Boot inject, kiểm tra dependency Actuator/tracing |

Mỗi interface nên mô tả một downstream contract rõ ràng. Không tạo một interface khổng lồ chứa các method cho nhiều host khác nhau nếu chúng có auth, SLA, retry và versioning độc lập.

**Client builder có trạng thái.** Gọi `baseUrl(...)` hoặc `defaultHeader(...)` làm thay đổi builder; nếu tự dùng cùng builder object cho nhiều client, header/filter cũ có thể bị mang sang client mới. Builder của Boot thường có scope prototype cho từng injection point, nhưng không tự giúp bạn nếu bạn lưu và tái sử dụng **cùng một instance** trong code.

## 10. Bảo mật và truyền trace context

Một proxy HTTP dễ dùng cũng làm lỗi cấu hình dễ lan rộng. Cần kiểm soát:

- **Secret management:** password, API key, bearer token lấy từ secret manager hoặc token provider; không hard-code trong annotation.
- **Token theo caller:** truyền trong request scope/filter/interceptor thích hợp, không đặt token của một người lên singleton client.
- **TLS:** kết nối HTTPS, kiểm tra chứng chỉ và hostname; không tắt xác thực chứng chỉ chỉ để khắc phục lỗi.
- **SSRF:** cấu hình base URL hợp lệ, tránh tạo absolute request URI từ input không đáng tin cậy.
- **Data minimization:** không forward toàn bộ headers của inbound request đến downstream khi không cần.
- **Logging:** không ghi authorization, cookie, raw customer payload hoặc response nhạy cảm vào logs.
- **Rate limiting:** giới hạn request/concurrency để bảo vệ API đối tác khi có tải hoặc retry dồn.
- **Trace propagation:** client do Boot quản lý thường là điểm tích hợp Micrometer Observation/tracing khi đủ dependency và active context; cần kiểm chứng qua HTTP và asynchronous boundaries.

HTTP proxy chạy trên thread/reactive context của caller. Nếu caller là scheduler, broker consumer hoặc Spring Integration endpoint, trace context có thể bắt đầu mới hoặc phải được truyền qua executor/transport. `HttpServiceProxyFactory` không thay thế cấu hình propagation xuyên nhiều process.

## 11. Kiểm thử đúng hợp đồng HTTP và proxy wiring

Cần kiểm thử ít nhất hai lớp: **HTTP contract** và **Spring Boot wiring**. Không đủ nếu chỉ mock `CatalogHttpApi` rồi assert service có gọi phương thức — bài test đó chưa cho biết proxy sinh request đúng hay không.

### 11.1. Test RestClientAdapter bằng MockRestServiceServer

Spring Test cho phép gắn mock HTTP server vào builder của `RestClient`. Ví dụ tối giản xác minh path và JSON:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogHttpApiTest {

    @Test
    void mapsFindByIdToHttpGet() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        CatalogHttpApi api =
                HttpServiceProxyFactory.builderFor(
                                RestClientAdapter.create(
                                        builder.build()))
                        .build()
                        .createClient(CatalogHttpApi.class);

        server.expect(requestTo(
                        "https://catalog.test/v1/products/P-100"))
                .andRespond(withSuccess(
                        "{\"id\":\"P-100\",\"name\":\"Keyboard\",\"active\":true}",
                        MediaType.APPLICATION_JSON));

        ProductDto product = api.findById("P-100");

        assertEquals("P-100", product.id());
        assertEquals("Keyboard", product.name());
        server.verify();
    }
}
~~~

Đây là contract test của **interface + proxy + RestClientAdapter**; nó cố ý tạo builder trực tiếp để cô lập. Nó **chưa kiểm chứng builder của Spring Boot** hoặc cấu hình externalized configuration; cần một Spring context test riêng.

Trong test thực tế bổ sung expectation cho HTTP method GET, Accept header, query parameter, request body POST và request-specific header `Idempotency-Key`. Một test lỗi có thể cho mock server trả 404/503 và xác minh adapter nghiệp vụ chuyển lỗi đúng.

### 11.2. Test Spring Boot wiring

Dùng `@SpringBootTest` hoặc test context đủ bean cần thiết, và đưa `integrations.catalog.base-url` về HTTP stub server bằng `@DynamicPropertySource` hay cấu hình test. Kiểm tra:

1. Spring inject được bean `CatalogHttpApi` hoặc `CatalogReactiveHttpApi`.
2. Base URL lấy từ properties của môi trường test.
3. HTTP client dùng builder do Boot quản lý.
4. Proxy gửi đúng headers, timeout và auth filter/interceptor theo cấu hình.
5. Một server trả 404, 429, 500, response rỗng hoặc JSON sai cấu trúc được xử lý theo policy.
6. Nếu instrumentation bật, trace/metric chính phát sinh đúng và không chứa ID người dùng trong tag.

Có thể dùng WireMock, MockWebServer hoặc HTTP test server tương đương. Với WebClientAdapter và `Mono`, sử dụng `StepVerifier` để kiểm tra completion/error thay vì `block()` trong code production:

~~~java
StepVerifier.create(reactiveApi.findById("P-100"))
        .assertNext(product ->
                assertEquals("P-100", product.id()))
        .verifyComplete();
~~~

Snippet trên giả định đã có HTTP stub server, `reactiveApi` được inject, import Reactor Test/JUnit và fixture JSON. Không tự coi nó là bài test đầy đủ khi chưa chuẩn bị server.

### 11.3. Các tình huống test có giá trị cao

| Kịch bản | Cần xác minh |
| --- | --- |
| GET product | Method, base URL, URI template và decode JSON đúng |
| GET với ID chứa ký tự cần encode | Path variable được mở rộng/mã hóa đúng |
| Query pagination | `page`, `size`, `active` thành query parameter |
| POST tạo sản phẩm | Content-Type, request body, idempotency header |
| 404 | Adapter trả `Optional.empty()` hoặc lỗi nghiệp vụ đúng contract |
| 401/403 | Không retry vô hạn; không log token |
| 429/503 | Retry giới hạn/backoff; đủ thông tin quan sát |
| Timeout | Tách transport timeout và total deadline |
| JSON schema thay đổi | Decoding fail rõ, không trả dữ liệu mặc định sai |
| Hai downstream | Không rò auth/base URL/header giữa client |
| WebClient reactive | Chỉ request khi subscribe, lỗi tới error signal |
| Database + outbound HTTP | Không giả định transaction SQL rollback HTTP side effect |
| Retry POST | Một business operation giữ cùng Idempotency-Key |

## 12. Quan sát và vận hành

Khi ứng dụng có Actuator và Micrometer, các client do Spring Boot quản lý có thể được gắn observation để thu số liệu cho HTTP client và propagate trace headers, tùy version/transport/tracer config.

Các metric hữu ích:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Outbound request rate theo `client`/`uri template` | Gọi downstream nào nhiều nhất? |
| Latency p95/p99 | API nào đang chậm? |
| HTTP 4xx/5xx | Lỗi contract, auth hay downstream outage? |
| Timeout và connection errors | Mạng, server hay connection pool gây lỗi? |
| Retry attempts per operation | Một sự kiện đang tạo bao nhiêu request? |
| Circuit breaker/rate-limit events | Downstream có bị bảo vệ đúng không? |
| Queue/outbox lag | HTTP proxy xử lý chậm có làm backlog không? |

`uri` metric nên sử dụng **URI template** (ví dụ `/v1/products/{id}`), không đưa từng product ID vào label. Không đặt `eventId`, bearer token, email, user ID hoặc query string nhạy cảm vào metric label. Với tracing, cần kiểm soát cả span attributes và việc log headers.

Một **HTTP 200** từ đối tác chỉ cho thấy HTTP request được chấp nhận/hoàn tất theo server contract. Nếu server trả 202 Accepted, việc xử lý nghiệp vụ có thể còn ở hàng đợi. Vì vậy cần phân biệt metric **HTTP attempt outcome** và **business final outcome**, nhất là khi tích hợp với broker, outbox và scheduler.

## 13. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `CatalogHttpApi` không có bean | Chỉ khai báo interface, chưa tạo proxy bean | Tạo `HttpServiceProxyFactory` và đăng ký `@Bean` |
| `RestClient` class không tồn tại | Spring Framework/Boot quá cũ | Kiểm tra hỗ trợ Spring Framework 6.1+/Boot 3.2+ |
| `RestClientAdapter` không resolve | Sai dependency hoặc import theo version | Kiểm tra `spring-web` và imports |
| `WebClientAdapter` không resolve | Thiếu WebFlux dependency | Thêm WebClient/WebFlux phù hợp |
| Lỗi builder method `builderFor` | Trộn ví dụ API của Spring 6.0 và 6.1+/7 | Đối chiếu phiên bản HttpServiceProxyFactory |
| `No qualifying bean of type RestClient.Builder` | Thiếu Boot auto-config/dependency hoặc đã exclude | Kiểm tra điều kiện Boot và classpath |
| Gọi proxy nhưng không thấy HTTP request | Dùng reactive `Mono` chưa subscribe | Trả publisher cho framework/consumer subscribe |
| Gọi `block()` gây lỗi event-loop | Blocking trong WebFlux thread | Dùng reactive xuyên suốt hoặc cách ly blocking |
| Base URL sai | Property/profile/env override không đúng | Kiểm tra binding và URI path |
| Có RestClientAdapter nhưng 401 | Thiếu token hoặc không đúng auth scheme | Kiểm tra filter/interceptor/secret, tránh log token |
| Lỗi JSON sau khi server nâng version | DTO khác schema | Contract test và versioning |
| Retry làm tạo hai đơn hàng | POST không có idempotency contract | Dùng Idempotency-Key và đối soát |
| Không có metrics/traces | Builder tự tạo, thiếu Actuator/tracing/exporter | Dùng builder do Boot quản lý và kiểm tra instrumentation |
| Mỗi request gọi nhầm service khác | Dùng lại mutable builder với header/baseURL | Tạo client bean riêng/clone builder |

## 14. Checklist hoàn thành HTTP interface adapter

- [ ] Đã định nghĩa rõ HTTP API client bằng `@HttpExchange` và các method annotation tương ứng.
- [ ] Đã chọn RestClientAdapter hoặc WebClientAdapter theo mô hình blocking/reactive thực tế.
- [ ] HTTP proxy được đăng ký làm Spring bean qua `HttpServiceProxyFactory` (hoặc cơ chế đăng ký tương đương của version dùng trong dự án).
- [ ] Builder được Boot quản lý để giữ cấu hình client, codecs và observability khi có.
- [ ] Base URL, timeout, auth và API version được tách theo downstream và môi trường.
- [ ] DTO, headers, status, response rỗng và lỗi đã được xác định thành hợp đồng dữ liệu.
- [ ] Adapter nghiệp vụ chuyển HTTP result/error thành port/domain result đúng chính sách.
- [ ] GET/POST retry có giới hạn; request ghi có idempotency key hoặc cơ chế đối soát.
- [ ] SQL transaction được tách khỏi HTTP side effect; outbox/inbox khi cần độ tin cậy.
- [ ] Đã kiểm thử HTTP path/method/body/headers, 404/503, timeout và reactive subscription.
- [ ] Có metrics/traces/logs đúng ranh giới, không lộ secret hay gây high-cardinality tags.

**Ghi nhớ:** HTTP interface khai báo hợp đồng phía client; `HttpServiceProxyFactory` tạo proxy; `RestClientAdapter` và `WebClientAdapter` quyết định cơ chế thực thi request. Spring Boot cung cấp builder và cấu hình nền; tầng tích hợp chịu trách nhiệm ràng buộc downstream, phân loại lỗi, timeout, retry/idempotency, transaction và quan sát. Giữ đúng các ranh giới này giúp nhiều HTTP API dễ kiểm thử, thay đổi và vận hành.

## Tài liệu tham khảo

- [Spring Framework — HTTP Interface](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface): `@HttpExchange`, proxy và kết nối HTTP client.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, error handling và HTTP interface.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive request, handling responses và client configuration.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): builder được Boot quản lý và cấu hình client.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics/tracing và ObservationRegistry.
- [Spring Framework API — HttpServiceProxyFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html): tạo HTTP interface proxies.
