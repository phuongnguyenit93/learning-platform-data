# RestTemplate trong hệ thống hiện có và lộ trình nâng cấp phù hợp phiên bản

## 1. Vì sao không nên thay RestTemplate bằng tìm-kiếm-thay-thế?

Nhiều hệ thống Java vẫn dùng **RestTemplate** để gọi API sản phẩm, thanh toán, vận chuyển hoặc đối tác. Những lời gọi **getForObject**, **exchange**, **postForEntity** có thể đã vận hành ổn định nhiều năm. Nhưng Spring đã giới thiệu **RestClient** cho HTTP đồng bộ hiện đại, trong khi **WebClient** giải quyết nhu cầu reactive/non-blocking và streaming.

Nâng cấp client không chỉ là đổi tên method. Một lần chuyển đổi có thể thay **HTTP transport**, cách encode URI, JSON converters, error handler, cookie, redirect, timeout, connection pool, proxy và OAuth2 headers. Với thanh toán hoặc hệ thống nhiều tenant, một khác biệt nhỏ có thể gửi request trùng hoặc làm lộ credential.

Bài thuộc chương **Client Java** của module **INTEGRATION_API_REST**: học giao tiếp REST theo resource/URI, method/status HTTP, cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử Java/Spring. Trọng tâm là **duy trì RestTemplate an toàn và di trú từng phần**, không thay cả hệ thống thiếu bằng chứng.

Mục tiêu:

1. Chọn chiến lược theo **Java, Spring Framework, Spring Boot version** đang triển khai.
2. Hiểu RestTemplate với **ClientHttpRequestFactory**, interceptors, converters, error handler.
3. Kiểm kê HTTP contract, timeout, TLS, status và retry trước khi di trú.
4. Dùng **RestClient.create(restTemplate)** khi nền tảng cho phép để giữ cấu hình ban đầu.
5. So request/response **wire-level**, test 4xx/5xx, auth và hậu quả của retry.
6. Lên lộ trình rollout/rollback theo rủi ro nghiệp vụ.

## 2. Ma trận phiên bản và quyết định

| Nền tảng | Client đồng bộ khả dụng | Khuyến nghị |
| --- | --- | --- |
| **Spring Framework 5.3 / Boot 2.7** | RestTemplate; **chưa có RestClient** | Ổn định client cũ; lên kế hoạch nâng Spring/Java trước |
| **Spring Framework 6.0 / Boot 3.0–3.1** | RestTemplate; **chưa có RestClient** | Rà Java 17, Jakarta, cấu hình transport; không copy RestClient 6.1 vào nhánh này |
| **Spring Framework 6.1 / Boot 3.2** | RestTemplate và **RestClient** | Có thể di trú từng downstream bằng RestClient |
| **Spring Framework 6.2 / Boot 3.x tương thích** | RestTemplate và RestClient | Ưu tiên RestClient cho code đồng bộ mới, tiếp tục migrate legacy |
| **Spring Framework 7.0 / Boot 4.x tương thích** | RestClient; RestTemplate còn tồn tại nhưng **deprecated** | Chuẩn bị thay RestTemplate trước khi bị loại bỏ ở bản tương lai |

- **RestClient xuất hiện ở Spring Framework 6.1**, không tồn tại như một class trong dòng Framework 5.3/6.0. Không tự ép jar Spring 6.1 vào một Boot 2.7 để dùng API mới.
- **Spring 6.0 cần Java 17** và chuyển nhiều API từ **javax** sang **jakarta**. Nâng nền tảng là một nhiệm vụ riêng; không nhét thay HTTP client vào cùng change lớn nếu chưa có test.
- Tài liệu Spring 7.0 đánh dấu **RestTemplate deprecated**, nhưng deprecated **không có nghĩa lập tức không chạy**. Lịch loại bỏ cần theo thông báo và documentation phiên bản thực tế, không đoán một mốc chắc chắn.
- Spring Boot 3 và 4 có thể thay package của builder và auto-configuration. Chỉ dùng ví dụ tương ứng **BOM đang chạy**.
- RestTemplate và RestClient dùng chung nhiều hạ tầng nhưng khi tự tạo client mặc định, **transport có thể khác**, dẫn đến khác biệt TLS, redirect, PATCH, timeout hoặc connection reuse.

**WebClient** đã có từ Spring 5, phù hợp reactive pipeline, streaming, SSE hoặc nhiều I/O không chặn. Nếu ứng dụng chủ yếu là Spring MVC/JDBC blocking, thay RestTemplate bằng WebClient rồi gọi **block()** ở mọi nơi không tự tạo lợi ích reactive. **RestClient cũng là blocking client**; lợi ích chính là fluent API và hướng phát triển.

## 3. Cấu tạo RestTemplate và API quen thuộc

~~~mermaid
flowchart LR
    A[Service code] --> B[RestTemplate / URI template]
    B --> C[Request interceptor]
    C --> D[ClientHttpRequestFactory]
    D --> E[Transport TLS / proxy]
    E --> F[ResponseErrorHandler]
    F --> G[HttpMessageConverter]
    G --> H[DTO / ResponseEntity]
~~~

- **ClientHttpRequestFactory** chọn transport, ảnh hưởng connection pool, proxy, TLS, PATCH, redirect.
- **ClientHttpRequestInterceptor** thêm metadata, tracing, Authorization; thứ tự interceptor có thể quan trọng.
- **HttpMessageConverter** đọc/ghi JSON, XML hoặc binary theo media type và thư viện cấu hình.
- **ResponseErrorHandler** quyết định 4xx/5xx được xem là lỗi và chuyển thành exception như thế nào.

| RestTemplate API | Ý nghĩa |
| --- | --- |
| **getForObject** | GET, trả body; khó thấy status/header |
| **getForEntity** | GET, trả ResponseEntity gồm status, headers, body |
| **postForObject** | POST, lấy body |
| **postForEntity** | POST, có thể đọc Location và status |
| **postForLocation** | POST, trả URI từ header Location |
| **put / delete** | PUT/DELETE, thông thường không trả ResponseEntity |
| **exchange** | Thực hiện request tổng quát, hỗ trợ RequestEntity và generic type |
| **execute** | API callback mức thấp để tùy chỉnh request/response, cần quản lý stream |

**DefaultResponseErrorHandler** thường biến status 4xx/5xx thành exceptions trong họ **RestClientResponseException** (chẳng hạn HttpClientErrorException.NotFound). Code getForObject rồi kiểm tra null **không đồng nghĩa xử lý được 404**. Nếu dự án đã cài custom ResponseErrorHandler, trước khi migrate phải ghi nhận chính xác cách handler đó xử lý 404/409/429/5xx.

## 4. HTTP contract cụ thể: giữ nguyên trước và sau migration

Giả sử Catalog API có:

~~~http
GET /api/v1/products/prod-42 HTTP/1.1
Host: catalog.example.internal
Accept: application/json
Authorization: Bearer <access-token>
X-Request-Id: req-781
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "prod-42-v7"
Cache-Control: private, max-age=30

{"id":"prod-42","name":"Sách về REST","priceVnd":180000}
~~~

Không tìm thấy:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.internal/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "code": "PRODUCT_NOT_FOUND"
}
~~~

Một DTO Java 17+:

~~~java
public record ProductDto(
        String id, String name, long priceVnd) {}
~~~

### Legacy client với exchange

~~~java
public final class LegacyCatalogClient {
    private final RestTemplate rest;
    private final String baseUrl;

    public LegacyCatalogClient(
            RestTemplate rest, String baseUrl) {
        this.rest = rest;
        this.baseUrl = baseUrl;
    }

    public ProductDto find(String id, String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.setBearerAuth(token);

        ResponseEntity<ProductDto> reply = rest.exchange(
            baseUrl + "/api/v1/products/{id}",
            HttpMethod.GET,
            new HttpEntity<Void>(headers),
            ProductDto.class,
            id
        );

        ProductDto value = reply.getBody();
        if (value == null) {
            throw new IllegalStateException(
                "Catalog 2xx nhưng thiếu body sản phẩm");
        }
        return value;
    }
}
~~~

**baseUrl** đến từ cấu hình tin cậy, ví dụ https://catalog.example.internal. **id** phải là một resource ID hợp lệ và được truyền như URI template variable; không cho caller cung cấp URL bất kỳ. **token** đến từ cơ chế auth đáng tin và có audience/scope đúng Catalog API. Với codebase Java 8/11, DTO có thể là POJO; record chỉ là ví dụ, không yêu cầu thay DTO khi sửa RestTemplate.

**Chưa đủ để migrate:** phải biết 404 có bị default handler ném exception không, API có chấp nhận **304 không body** không, interceptor có gắn tenant/correlation ID không, có dùng **custom ObjectMapper** không và TLS/mTLS đang ở request factory nào. Cần so cả status, header, body và exception mapping.

## 5. Giữ RestTemplate an toàn trong giai đoạn chưa nâng nền tảng

Không có RestClient trong Spring 5.3 hay 6.0 **không phải lý do** để giữ một RestTemplate được cấu hình tùy tiện. Bước đầu tiên có thể là khóa timeout, security, connection reuse và test mà chưa đổi public API client.

### Cấu hình transport tường minh

Mẫu Framework dùng **SimpleClientHttpRequestFactory**, không phụ thuộc API RestTemplateBuilder theo phiên bản Boot:

~~~java
@Configuration
public class LegacyHttpConfiguration {

    @Bean
    RestTemplate catalogRestTemplate() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(5_000);

        RestTemplate rest = new RestTemplate(factory);
        // Cài interceptor / error handler đã kiểm chứng,
        // không tự bỏ cấu hình cũ khi thay bean.
        return rest;
    }
}
~~~

**SimpleClientHttpRequestFactory dùng HttpURLConnection** và có hạn chế như hỗ trợ PATCH tùy transport. Nếu hệ thống cần mTLS, connection pooling, proxy phức tạp hoặc PATCH, hãy chọn request factory phù hợp (ví dụ Apache HttpComponents) và **đúng phiên bản thư viện tương thích Spring**; HttpComponents 4 của cấu hình cũ không được mặc định thay bằng phiên bản 5 mà không test.

Ở Spring Boot, **RestTemplateBuilder** hỗ trợ cấu hình thống nhất nhưng các method/package có thể khác giữa Boot 2/3/4. Không thay bean được tùy biến bằng **new RestTemplate()** rồi mất auto-customizers, converter hoặc SSL settings.

**RestTemplate có thể dùng chung sau khi cấu hình xong; không mutate interceptors/message converters/request factory trong lúc nhiều thread đang gọi.** Cấu hình từng downstream thành bean tách biệt khi auth, proxy và timeout khác nhau.

### Timeout và connection pool

- **Connect timeout** bảo vệ bước thiết lập kết nối.
- **Read/response timeout** bảo vệ khi đã kết nối nhưng downstream phản hồi chậm.
- **Pool-acquire timeout** ngăn chờ socket quá lâu nếu connection pool đầy.
- **Overall deadline** bao trùm mọi attempt/retry và workflow; connect timeout **không thay thế** nó.

Một transport khác có thể thay hành vi **redirect, PATCH, DNS, TLS handshake, cookie và keep-alive**, ngay cả khi Java API call giống hệt. Chạy test timeout, redirect, mTLS, proxy và concurrency trên chính transport sẽ dùng ở production.

## 6. Lộ trình hai bước với RestClient.create(restTemplate)

Khi đã dùng **Spring Framework 6.1+**, Spring cung cấp cầu nối:

~~~java
RestClient migrated = RestClient.create(existingRestTemplate);
~~~

Cách này khởi tạo RestClient từ **cấu hình của một RestTemplate hiện có**, giúp **giảm thay đổi cùng lúc**: các lớp request factory, interceptors, message converters và URI setup có thể được tái sử dụng theo cơ chế của Spring. Không cần viết lại mọi interceptor trước khi đổi câu lệnh gọi.

Cấu hình bean minh họa:

~~~java
@Configuration
public class CatalogClientConfiguration {

    @Bean
    RestTemplate legacyCatalogRestTemplate() {
        // Trong hệ thống thật, đây là bean legacy đã kiểm chứng.
        return new RestTemplate();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("legacyCatalogRestTemplate")
            RestTemplate legacy) {
        return RestClient.create(legacy);
    }
}
~~~

**Đoạn trên chỉ mô tả cách bọc**: phần tạo RestTemplate phải giữ request factory, token interceptors, SSL, timeout, converters và monitoring thực tế của dự án. Không áp một RestTemplate trắng thay bean cũ đang có mTLS.

### Bước A: đổi từng lời gọi, giữ hạ tầng

~~~java
public final class ModernCatalogClient {
    private final RestClient rest;
    private final String baseUrl;

    public ModernCatalogClient(
            RestClient rest, String baseUrl) {
        this.rest = rest;
        this.baseUrl = baseUrl;
    }

    public ProductDto find(String id, String token) {
        ProductDto product = rest.get()
            .uri(baseUrl + "/api/v1/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .onStatus(s -> s.value() == 404,
                (req, res) -> {
                    throw new ProductNotFoundException(id);
                })
            .body(ProductDto.class);

        if (product == null) {
            throw new IllegalStateException(
                "Catalog 2xx nhưng thiếu body sản phẩm");
        }
        return product;
    }
}
~~~

**ProductNotFoundException** là exception của ứng dụng cần định nghĩa. **onStatus** ở RestClient dùng handler với request và response; chỉ dùng predicate/exception tương ứng phiên bản Framework. Đặc biệt, **chính sách của ResponseErrorHandler custom ở RestTemplate không nên được giả định là hoàn toàn tương đương với status handlers của RestClient**: hãy xác nhận bằng test 404, 409, 429, 500 và cả response body lỗi.

Sau mỗi endpoint được thay, kiểm tra **request method, URI encoding, query, headers, byte payload, status, exception và latency**. Không đồng thời thay API client, mTLS, JSON format và retry policy trên một luồng nghiệp vụ khó rollback.

### Bước B: chuyển hẳn cấu hình sang RestClient.Builder

Khi các lời gọi đã dùng RestClient và contract test ổn định, tạo **RestClient.Builder** độc lập với RestTemplate. Lúc đó mới chuyển từng interceptor, request factory, observation và converters vào cấu hình mới; giữ transport giống legacy trước, sau đó thử nâng riêng.

~~~java
@Bean
RestClient catalogClient(
        ClientHttpRequestFactory testedFactory) {
    return RestClient.builder()
        .baseUrl("https://catalog.example.internal")
        .requestFactory(testedFactory)
        .defaultHeader(
            HttpHeaders.ACCEPT,
            MediaType.APPLICATION_JSON_VALUE)
        .build();
}
~~~

Ví dụ này **chưa thêm lại** authentication/tracing interceptors, nên chỉ là skeleton. Production phải mang đủ bảo mật, timeout, TLS/proxy và observability, không build xong rồi sử dụng ngay nếu thiếu chính sách đó. **Tránh gắn token user cố định trong defaultHeader trên singleton client**; cấp token đúng từng request.

### Vì sao phải giữ transport?

Spring documentation lưu ý khi dùng client mặc định mà không có thư viện khác: **RestTemplate** có thể dùng **SimpleClientHttpRequestFactory / HttpURLConnection**, trong khi **RestClient** chọn **JdkClientHttpRequestFactory / java.net.http.HttpClient**. Sự thay đổi HTTP library có thể làm khác redirect, PATCH, timeout hoặc wire behavior. Migration qua RestClient.create(existing) giúp tách thay đổi **API sử dụng** khỏi thay đổi **HTTP transport**, rồi mới quyết định transport có cần nâng không.

## 7. Bảng đổi API method có kiểm soát

| RestTemplate | RestClient 6.1+ | Điều phải kiểm chứng |
| --- | --- | --- |
| **getForObject(url, Type.class)** | **get().uri(url).retrieve().body(Type.class)** | 200/body rỗng, 404 exception |
| **getForEntity** | **get().uri(...).retrieve().toEntity(Type.class)** | HTTP headers, ETag, Content-Type |
| **postForObject** | **post().uri(...).body(dto).retrieve().body(Type.class)** | Content-Type, 201/202, side effect |
| **postForEntity** | **post().uri(...).body(dto).retrieve().toEntity(Type.class)** | Location và status |
| **postForLocation** | **post().uri(...).body(dto).retrieve().toBodilessEntity().getHeaders().getLocation()** | Header Location có thật |
| **put** | **put().uri(...).body(dto).retrieve().toBodilessEntity()** | Nếu 200 có body, contract riêng |
| **delete** | **delete().uri(...).retrieve().toBodilessEntity()** | 204, 404 và idempotency |
| **exchange(RequestEntity, ...)** | **method(...).uri(...).headers(...).body(...).retrieve().toEntity(...)** hoặc **exchange(...)** | Không mất method/headers/generic type |
| **ParameterizedTypeReference** | **retrieve().body(new ParameterizedTypeReference<...>() {})** | Kiểu generic không bị xóa |

Mọi row trong bảng là **mapping ý tưởng**, không phải thao tác thay thế AST tự động. **getForObject** cũ có thể nhận URI template variables, interceptor bổ sung header, request factory custom và error handler khác; RestClient phải giữ hợp đồng đó.

Nếu dùng **RestClient.exchange((request, response) -> ...)** ở mức thấp, hãy nhớ **status handlers của retrieve không được tự chạy trong exchange**; code callback phải chủ động kiểm tra status, content type, response body và đóng tài nguyên theo contract. Nếu chỉ cần body/status/headers thường, **retrieve** đơn giản và an toàn hơn.

Khi lấy collection kiểu generic:

~~~java
List<ProductDto> products = rest.get()
    .uri("/api/v1/products")
    .retrieve()
    .body(new ParameterizedTypeReference<List<ProductDto>>() {});
~~~

Không dùng **List.class** nếu client cần giữ type ProductDto chính xác; Jackson có thể deserialize danh sách phần tử thành Map thay vì DTO.

## 8. Xử lý status, error body và các phản hồi không có body

Không thể coi một phép đổi client là tương đương nếu cách phân loại lỗi đã khác. Giả sử API trả lỗi dưới dạng **application/problem+json**:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.internal/problems/duplicate-order",
  "title": "Order already exists",
  "status": 409,
  "code": "DUPLICATE_ORDER"
}
~~~

**RestTemplate.getForObject** với error handler mặc định thường ném exception trước khi map body sang DTO thành công. **RestClient.retrieve** cũng thường biến 4xx/5xx thành exception, nhưng cần kiểm tra chính sách custom, body lỗi và headers, không dựa vào tên method.

Một adapter nên chuyển lỗi downstream về **lỗi domain ổn định**:

~~~java
public ProductDto load(String id) {
    try {
        return rest.get()
            .uri("/api/v1/products/{id}", id)
            .retrieve()
            .body(ProductDto.class);
    } catch (HttpClientErrorException.NotFound ex) {
        throw new ProductNotFoundException(id);
    } catch (RestClientResponseException ex) {
        throw new CatalogUnavailableException(
            "Catalog HTTP " + ex.getStatusCode().value(), ex);
    } catch (ResourceAccessException ex) {
        throw new CatalogUnavailableException(
            "Catalog transport failure", ex);
    }
}
~~~

**Không trả message raw của ex cho client bên ngoài**; body lỗi có thể chứa PII, access tokens hoặc nội dung không đáng tin. Chính sách ví dụ cũng còn cần phân biệt **400/401/403/409/429/5xx** chi tiết hơn theo contract, chứ không nên mặc định mọi non-404 là “unavailable”.

Một bảng hành vi cần đối chiếu:

| HTTP downstream | Ứng xử client cần giữ |
| --- | --- |
| **200 OK** | Đọc đúng DTO và Content-Type |
| **201 Created** | Kiểm tra Location và representation nếu API cam kết |
| **202 Accepted** | Chỉ công việc được nhận; tra operation status |
| **204 No Content** | **Không parse JSON**; trả void hoặc response rỗng |
| **304 Not Modified** | **Không body**; dùng cache local đúng validator/variant |
| **400/422** | Mapping validation/semantic errors, không retry mù |
| **401/403** | Phân biệt thiếu auth và thiếu quyền; không tự tăng quyền |
| **404** | Not found hoặc che resource, theo hợp đồng upstream |
| **409/412** | Business conflict so với HTTP precondition |
| **429/503** | Có thể retry có giới hạn với Retry-After hợp lệ |
| **Timeout/reset** | Không có status đáng tin; kết quả POST có thể chưa rõ |

Nếu client gửi **If-None-Match**, phải đọc **ETag/Cache-Control/Vary** của 304, không chỉ dựa vào body null. Caching ở consumer là một quyết định riêng; không dùng ETag của downstream làm ETag của API tổng hợp mà chưa xác định representation/quyền.

### Lỗi khi dùng exchange mức thấp

Đối với **RestClient.exchange(...)**, callback chịu trách nhiệm kiểm tra mã lỗi và deserialize; **default status handlers của retrieve không được áp vào exchange**. Với các luồng đặc biệt như tải file lớn, streaming hoặc 304, có thể dùng exchange chủ động, nhưng phải đóng response và xử lý body đúng cách.

Một migration đáng tin phải có **bảng status mapping được ký duyệt** và test từng dòng, không đơn giản xem compile xanh là thành công.

## 9. Timeout, connection pool và retry là hợp đồng vận hành

Thay RestTemplate bằng RestClient không tự thêm **connect/read timeout, bulkhead, circuit breaker** hay idempotency. Mỗi thành phần có mục đích khác:

- **Connect timeout:** giới hạn thiết lập connection.
- **Read/response timeout:** giới hạn chờ dữ liệu sau khi đã kết nối.
- **Pool acquire timeout:** giới hạn chờ socket rảnh; đặc biệt quan trọng với Apache/Jetty client.
- **Overall deadline:** ngân sách cho toàn lời gọi và retry, không chỉ một attempt.
- **Concurrency limit:** bảo vệ upstream và downstream khỏi quá nhiều cuộc gọi chờ.

RestTemplate và RestClient đều có thể dùng **cùng một ClientHttpRequestFactory** để giảm thay đổi transport. Khi đổi factory từ Simple sang JDK/Apache, cần đo riêng connection reuse, TLS, proxy và timeout. **Tự tạo một client/request factory cho mỗi call** có thể làm mất connection reuse và gây cạn socket.

### Retry phải xét HTTP semantics

| Thao tác | Có nên retry tự động? |
| --- | --- |
| **GET** | Thường có thể retry lỗi tạm thời nếu giới hạn attempts/deadline |
| **PUT/DELETE** | Có ngữ nghĩa idempotent, nhưng vẫn cần kiểm tra side effects và hợp đồng |
| **POST tạo đơn/thanh toán** | Chỉ khi có **Idempotency-Key**/business key và cơ chế xử lý trùng được công bố |
| **401/403/400** | Không retry vô điều kiện |
| **429/503** | Có thể dùng backoff/jitter, tôn trọng Retry-After trong giới hạn |

Ví dụ:

~~~http
POST /api/v1/payment-intents HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: ord-501-charge-v1

{"orderId":"ord-501","amountMinor":180000,"currency":"VND"}
~~~

Nếu network reset **sau khi payment server commit**, consumer có thể không thấy 201. Retry **cùng key và cùng payload** trong cửa sổ phía server hỗ trợ, hoặc GET trạng thái/đối soát theo business reference; không tạo key mới cho mỗi attempt. Retry chồng tại SDK, service và gateway có thể nhân tải theo cấp số; cấu hình tại một điểm rõ ràng, có **backoff + jitter** và **tổng deadline**.

**Retry-After** có thể là delta-seconds hoặc HTTP-date, cần parse đúng. Chỉ retry nếu thời gian còn lại đủ; cancellation của request gốc cần dừng những attempt không còn cần thiết. Đối với operation có kết quả không rõ, **không suy luận timeout = chắc chắn rollback**.

## 10. Bảo mật trong giai đoạn hai client cùng tồn tại

### Authentication và tenant isolation

Một client bean dùng chung **không được giữ access token người dùng trong mutable field**. Token cần gắn cho **đúng request**; nếu có OAuth2 client credentials, xác nhận **audience/scope** của downstream. Không forward raw user token sang dịch vụ không cùng audience.

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(tokenForThisRequest);
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
~~~

Khi migrate, kiểm tra interceptor từng gửi **Authorization, X-Tenant-Id, X-Request-Id** và quy tắc sinh/kiểm tra chúng. Không tin X-Tenant-Id do client tự khai nếu downstream dựa vào đó để phân quyền; tenant thực phải lấy từ principal/context đáng tin.

### TLS, endpoint và redirect

- Base URL phải từ **config tin cậy**, không cho request người dùng chuyển full URL tùy ý.
- Chỉ cho phép HTTPS trừ giao thức nội bộ có thiết kế bảo mật riêng; xác minh certificate, hostname và mTLS.
- Khi endpoint cho phép redirect, không tự động gửi Authorization sang origin khác. Test redirect từ host nội bộ sang host không có trong allowlist.
- Phòng **SSRF** khi endpoint có thể được cấu hình động: kiểm soát DNS, host/port, private/loopback/link-local/metadata IP, redirect, IPv4/IPv6 và egress policy.
- Không nhét token, secret hoặc PII vào URI, query string hoặc log.
- Giới hạn request/response size và JSON nesting; đừng log body lỗi thô khi downstream lỗi.

### Interceptors và quan sát

Các **ClientHttpRequestInterceptor** cho tracing và auth có thể được dùng lại ở RestClient, nhưng phải kiểm tra **thứ tự, khả năng chạy đồng thời, ghi log header và replay request body**. Logging interceptor ghi raw Authorization hoặc response body có PII là một lỗ hổng dù request vẫn trả 200.

Trên migration nên duy trì **latency p95/p99, error rate 4xx/5xx, timeout, connection pool wait, retry attempts, correlation ID**. Đừng dùng raw URL chứa ID riêng tư hoặc exception detail làm metric label có cardinality vô hạn.

## 11. HTTP Interface hay WebClient?

Trong Spring 6.1+, **@HttpExchange** có thể chạy qua proxy **HttpServiceProxyFactory + RestClientAdapter**; nó giảm code HTTP mapping nhưng **không tự thiết lập TLS, token, timeout hoặc xử lý lỗi**.

~~~java
@HttpExchange("/api/v1/products")
interface CatalogApi {
    @GetExchange("/{id}")
    ProductDto find(@PathVariable String id);
}
~~~

**WebClient** phù hợp khi cần reactive/non-blocking hoặc SSE/NDJSON. Spring MVC thuần blocking không cần đổi cả stack. Java 21 virtual threads giảm chi phí thread chờ I/O nhưng **không tăng capacity downstream**.

## 12. Kiểm thử hợp đồng trước và sau migration

Dùng **cùng test matrix** cho RestTemplate và RestClient. **MockRestServiceServer** kiểm tra request/response ở tầng Spring; WireMock hoặc MockWebServer giúp kiểm tra transport, timeout, redirect và kết nối thật.

Ví dụ kiểm chứng RestClient được bọc từ RestTemplate:

~~~java
@Test
void migratedClientPreservesGetContract() {
    RestTemplate legacy = new RestTemplate();
    MockRestServiceServer server =
        MockRestServiceServer.createServer(legacy);
    RestClient modern = RestClient.create(legacy);

    server.expect(requestTo(
            "https://catalog.example.internal/products/prod-42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header(HttpHeaders.ACCEPT, "application/json"))
        .andRespond(withSuccess(
            "{\"id\":\"prod-42\",\"name\":\"Sách REST\","
                + "\"priceVnd\":180000}",
            MediaType.APPLICATION_JSON));

    ProductDto value = modern.get()
        .uri("https://catalog.example.internal/products/{id}",
            "prod-42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve().body(ProductDto.class);

    assertEquals("prod-42", value.id());
    server.verify();
}
~~~

Chỉ dùng ví dụ này ở **Spring 6.1+**, với imports Spring Test/JUnit. Production test cần bean legacy có **interceptors, request factory, Jackson và SSL** thực tế; test này chưa chứng minh behavior của transport vì server giả lập thay thế HTTP I/O.

| Trường hợp | Bất biến |
| --- | --- |
| 200/201/202/204/304 | Body, Location, ETag, status đúng |
| 400/404/409/429/503 | Error mapping và Problem Details không đổi ngoài chủ đích |
| URI encoding/headers | Method, path/query, Accept, Content-Type đúng |
| Timeout, proxy, mTLS | Hành vi được đo trên HTTP transport thực |
| POST retry | Giữ Idempotency-Key và payload, không tạo trùng |
| Hai tenant đồng thời | Token không bị dùng chéo hoặc log lộ |
| Redirect sang host lạ | Không forward Authorization |
| Nhiều kết nối | Giới hạn pool, queue, p95/p99 không suy giảm vượt ngưỡng |

**Không shadow POST thanh toán để so sánh hai client**: đó là hai giao dịch có thể tạo tác dụng phụ. Shadow GET chỉ khi API an toàn và đủ quyền truy cập.

## 13. Rollout và rollback theo từng chặng

1. **Baseline:** ghi nhận phiên bản, transport, headers/status, latency, timeout, error rate; thêm tests cho RestTemplate.
2. **Nâng nền tảng riêng:** giải quyết Java 17/Jakarta/BOM nếu đang ở Boot 2.x hoặc Framework 6.0.
3. **Bridge:** tạo RestClient từ RestTemplate hiện có; chuyển từng integration, giữ request factory và auth.
4. **Canary:** dùng feature flag cho traffic ít rủi ro, so HTTP contract và metrics trước–sau.
5. **Tách cấu hình:** chuyển sang RestClient.Builder, rồi mới thử đổi transport/pool nếu có lý do.
6. **Thu hồi legacy:** xóa đường RestTemplate sau khi qua test, tải và security checks.

**Rollback** bằng feature flag/client adapter phải giữ các request POST đã commit và key chống trùng; rollback code không đảo ngược giao dịch kinh doanh. Đặt ngưỡng dừng rollout cho 5xx, timeout, p99 và lỗi auth tăng.

## 14. Bài tập: nâng cấp Catalog và Payment

Dự án đang ở **Boot 2.7/RestTemplate**; mục tiêu là **Boot 3.2+ / RestClient**.

1. Viết bảng Java/Spring/Boot version, Jakarta changes và transport tương thích.
2. Kiểm kê interceptors, error handlers, JSON converters, proxy, mTLS, timeout.
3. Chuyển **Catalog GET** sang RestClient, chứng minh giữ 200/404, ETag và URI encoding.
4. Chuyển **Payment POST** có Idempotency-Key, xử lý 201/202/409/429/timeout và đối soát kết quả chưa rõ.
5. Viết ít nhất **8 tests**: auth hai tenant, redirect, 404, 409, 429, timeout, POST retry, Location.
6. Đề xuất canary/feature flag và cách đo latency, pool, error rate, rollback an toàn.

**Sản phẩm:** bảng phiên bản, hai client, HTTP transcript, test matrix và kế hoạch migration có tiêu chí chấp nhận.

## 15. Checklist và kết luận

- Không dùng **RestClient** trên Spring chưa có API này.
- Giữ nguyên **HTTP method, URI, headers, body/status/error semantics**.
- Giữ hoặc kiểm chứng lại **TLS/mTLS, proxy, pool, timeout, interceptors**.
- Token đúng **audience/tenant theo request**, không SSRF/redirect lộ secret.
- Retry POST chỉ có **idempotency và khả năng đối soát**.
- Có test old/new cùng hợp đồng, cộng test transport thực.
- Rollout có **canary, quan sát và rollback** không phát sinh side effects mới.

**Kết luận:** RestTemplate vẫn có thể được duy trì an toàn trên phiên bản cũ. Với **Spring Framework 6.1+**, hướng dài hạn cho HTTP đồng bộ là **RestClient**, di trú tăng dần bằng **RestClient.create(restTemplate)** rồi cấu hình mới. **WebClient** chỉ cần khi yêu cầu reactive/streaming phù hợp. Thước đo thành công là **tính đúng đắn HTTP, bảo mật, độ trễ và dữ liệu**, không phải số lời gọi được đổi tên.

### Tài liệu chính thức

- Spring 6.2 REST Clients: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring REST Clients và migration: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Engineering, 30/09/2025: https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/







