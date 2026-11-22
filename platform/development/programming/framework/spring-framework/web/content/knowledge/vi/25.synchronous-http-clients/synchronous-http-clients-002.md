# Spring Framework Web — Tạo RestClient và cấu hình base URL, header, cookie mặc định

## 1. Mục tiêu

`RestClient` là HTTP client **đồng bộ** dùng fluent API của Spring Framework. Được giới thiệu từ Spring Framework 6.1 và được mở rộng trong 6.2, RestClient giúp Spring MVC services, scheduled jobs hoặc batch applications gọi một REST API khác, decode JSON và quản lý HTTP status mà không phải tự mở socket.

Bài học này tập trung vào **một RestClient dùng lại được** với cấu hình chung:

- Tạo client bằng `RestClient.create()` hoặc `RestClient.builder()`.
- `baseUrl(String/URI)` để không lặp URL host/prefix ở từng request.
- `defaultUriVariables(...)` và quan hệ với `uriBuilderFactory(...)`.
- `defaultHeader(...)` và `defaultHeaders(...)` cho headers mặc định.
- `defaultCookie(...)` và `defaultCookies(...)` cho cookies mặc định **từ Spring Framework 6.2**.
- Ghi đè header/cookie ở mức **một request**.
- `defaultRequest(...)` khi cần thiết lập giá trị động mỗi request.
- Cách Spring Boot 3.5 auto-configure và inject `RestClient.Builder`, phân biệt builder với client đã build.
- Kiểm thử bằng `MockRestServiceServer.bindTo(builder)` và JUnit 5, không cần API ngoài Internet.
- Tránh dùng cookie/token nhạy cảm mặc định cho một singleton shared giữa nhiều người dùng.
- Cấu hình nâng cao về timeout, request factory, error handling, pooling, logging và authorization.

**Ngữ cảnh:** module cha là **HTTP client đồng bộ**. Không nhầm `RestClient` với `WebClient` (reactive) hoặc WebFlux server API. `retrieve().body(Class)` chặn thread đang thực thi tới khi nhận response/lỗi.

## 2. So sánh ba HTTP clients của Spring

| Client | Mô hình | Cách dùng chính |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent | Ứng dụng blocking/MVC, outbound REST |
| `RestTemplate` | Synchronous, template methods | Legacy applications, migration |
| `WebClient` | Non-blocking, `Mono`/`Flux` | WebFlux/reactive pipelines |

Một RestClient có thể tạo:

~~~java
RestClient client = RestClient.create();
String body = client.get()
        .uri("https://example.org/api/health")
        .retrieve()
        .body(String.class);
~~~

Đây là fragment: endpoint chỉ minh họa. Sau khi được `build()`, RestClient có thể dùng lại an toàn giữa nhiều threads theo tài liệu Spring. **Builder mutable không nên được thay đổi đồng thời ở runtime**: cấu hình một lần lúc bootstrap và inject client đã build.

### 2.1. Vì sao không tạo RestClient mới cho từng request?

Mỗi lần tạo lại RestClient và underlying HTTP request factory/connection pool có thể gây overhead, quản lý connection và observability khó hơn. Trong application, khai báo một `@Bean RestClient` theo từng upstream. Các request specs được tạo riêng bằng `client.get()`/`post()` trên client shared, chứa values riêng cho mỗi HTTP call.

### 2.2. Khi nào phải dùng WebClient?

Nếu đang chạy code trên Reactor Netty event loop, một outbound RestClient call có thể làm block event loop. Trong WebFlux/reactive pipeline, ưu tiên `WebClient`; nếu bắt buộc gọi blocking legacy API, offload và giới hạn concurrency, không gọi `block()` trong event-loop.

## 3. Các cách khởi tạo

### 3.1. Không có defaults

~~~java
RestClient client = RestClient.create();
~~~

Request thường phải dùng URL tuyệt đối:

~~~java
String body = client.get()
        .uri("https://service.example.test/info")
        .retrieve()
        .body(String.class);
~~~

URL này không phải dịch vụ thật.

### 3.2. Dùng builder

~~~java
RestClient catalog = RestClient.builder()
        .baseUrl("https://catalog.example.test/api/v1")
        .defaultHeader("X-Client-Name", "inventory-service")
        .defaultCookie("locale", "vi")
        .build();
~~~

Gọi:

~~~java
Product product = catalog.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
~~~

`Product` là DTO ứng dụng định nghĩa. Ví dụ `record Product(long id, String name) {}` có thể deserialize JSON body như `{"id":42,"name":"Tea"}` khi Jackson có sẵn.

### 3.3. Tạo từ RestTemplate

Spring có factory method `RestClient.create(RestTemplate)` để hỗ trợ migration:

~~~java
RestTemplate template = new RestTemplate();
RestClient client = RestClient.create(template);
~~~

Khi chuyển ứng dụng cũ, phải kiểm request factory, interceptors, status handlers, serializers và timeout thực tế. Không chỉ thấy code compile là đủ; các default policies có thể khác.

## 4. baseUrl và URI resolution

### 4.1. Một nguồn cấu hình cho host và prefix

~~~java
RestClient api = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .build();

Product p = api.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
~~~

Ý định URL cuối:

~~~text
https://catalog.example.test/v1/products/42
~~~

Cần kiểm bằng MockRestServiceServer để tránh sai path. Không đặt `/v1` cả trong baseUrl và `.uri("/v1/products/{id}")` vì sẽ có prefix lặp.

### 4.2. Absolute URI bypass baseUrl

Theo Spring Framework 6.2 Javadoc, khi request sử dụng absolute URL, cấu hình baseUrl bị bỏ qua:

~~~java
api.get()
        .uri("https://other.example.test/products/42")
        .retrieve()
        .body(String.class);
~~~

Điều này nguy hiểm nếu upstream được chọn từ input người dùng và RestClient có global Authorization/Cookie. Ngăn SSRF/credential leakage bằng allowlist trusted hosts/schemes/ports, redirect policy và client riêng cho mỗi trust boundary.

### 4.3. URI templates tốt hơn nối string

Ưu tiên:

~~~java
api.get()
        .uri("/products/{id}", userVisibleId)
        .retrieve()
        .body(String.class);
~~~

Không nên tự nối input:

~~~java
api.get().uri("/products/" + rawInput);
~~~

Một ID hoặc search term có dấu cách, `?`, `/` hay `#` có thể đổi ý nghĩa của URI. Dùng URI template và query builder để encoding được xử lý có chủ đích.

Ví dụ query:

~~~java
api.get()
        .uri(builder -> builder
                .path("/products")
                .queryParam("q", searchTerm)
                .queryParam("page", 1)
                .build())
        .retrieve()
        .body(String.class);
~~~

Fragment này cần `searchTerm`. Khi cung cấp trực tiếp `URI`, encoding behavior khác với String template; đọc Javadoc và không encode hai lần.

### 4.4. Default URI variables

Nếu nhiều API paths cần biến cố định, chẳng hạn region:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultUriVariables(Map.of("region", "vn"))
        .build();

String body = client.get()
        .uri("/regions/{region}/products/{id}",
                Map.of("id", 42))
        .retrieve()
        .body(String.class);
~~~

Default variables là shortcut của `DefaultUriBuilderFactory`; không cất tenant ID của mỗi user trong globals trên một shared client.

### 4.5. uriBuilderFactory và độ ưu tiên

`uriBuilderFactory(UriBuilderFactory)` thay thế cơ chế tạo URI mặc định. Theo Javadoc Spring 6.2, việc cung cấp factory riêng **ghi đè tác động của shortcut baseUrl/defaultUriVariables**. Nếu đã có custom factory, baseUrl bạn đặt sau/trước có thể không hiệu lực như kỳ vọng. Chỉ dùng custom factory khi có yêu cầu encoding/URI templates thật sự đặc thù.

## 5. defaultHeader và defaultHeaders

### 5.1. Default header đơn

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Client-Name", "inventory-service")
        .build();
~~~

`RestClient.Builder.defaultHeader(String, String...)` chỉ thêm header mặc định **nếu request chưa có header cùng tên**. Vì thế per-call header có thể thay default:

~~~java
client.get()
        .uri("https://catalog.example.test/products/7")
        .header("X-Client-Name", "special-job")
        .retrieve()
        .body(String.class);
~~~

Khi request đã có X-Client-Name, defaultHeader không tự thêm inventory-service. Nếu một header trước đó đã được add nhiều lần, dùng `headers(h -> h.set(...))` để thay thay vì append.

### 5.2. defaultHeaders thao tác cả nhóm

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Client-Name", "inventory-service")
        .defaultHeaders(headers -> {
            headers.set("X-API-Version", "2026-10");
            headers.setAccept(
                    List.of(MediaType.APPLICATION_JSON));
            headers.remove("X-Legacy-Feature");
        })
        .build();
~~~

`defaultHeaders(Consumer<HttpHeaders>)` cho phép:

- `add(name,value)`: thêm value vào danh sách.
- `set(name,value)`: ghi đè danh sách thành một value.
- `remove(name)`: xóa default.
- `setAccept(List.of(...))`: cấu hình Accept đúng kiểu.

**Cẩn thận:** `Authorization` thường chỉ nên có một scheme/token được chọn đúng audience. Không biến `defaultHeader("Authorization",...)` thành chỗ chứa token của một người dùng trong RestClient singleton.

### 5.3. Accept và Content-Type

- `Accept` cho biết response representation bạn muốn nhận, ví dụ JSON.
- `Content-Type` mô tả media type của **request body**, nên không cần ép mặc định application/json cho mọi GET không có body.
- `User-Agent` và `X-Client-Name` hữu ích để upstream phân biệt service nếu được chính sách đồng ý.
- `X-API-Version` dùng khi upstream có hợp đồng versioning qua header.

Nếu API gọi POST JSON, có thể cấu hình per-call:

~~~java
client.post()
        .uri("/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateProductRequest("Tea"))
        .retrieve()
        .toBodilessEntity();
~~~

Đây là fragment, CreateProductRequest cần được khai báo. Khi client có base URL, path này sẽ được nối phù hợp. Có thể sử dụng media type convenience methods thay vì tự viết Content-Type string.

### 5.4. Một lỗi request ID phổ biến

Không tạo một request ID rồi gắn global:

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Request-ID",
                UUID.randomUUID().toString())
        .build();
~~~

Mọi requests của client có thể cùng một ID vì giá trị chỉ được sinh khi build. Nếu mỗi call cần ID mới, dùng `defaultRequest`/interceptor hoặc chuẩn tracing propagation.

## 6. defaultCookie và defaultCookies — Spring Framework 6.2

### 6.1. API mới có thật

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultCookie("locale", "vi")
        .build();
~~~

`RestClient.Builder.defaultCookie(String, String...)` được thêm **từ Spring Framework 6.2**. Nó cung cấp cookie mặc định cho request **nếu request chưa có cookie cùng tên**. Nếu IDE nói không có method, kiểm `spring-web` effective dependency version thay vì nghĩ RestClient không hỗ trợ cookies.

### 6.2. defaultCookies dùng MultiValueMap

~~~java
RestClient client = RestClient.builder()
        .defaultCookie("locale", "vi")
        .defaultCookies(cookies -> {
            cookies.set("theme", "light");
            cookies.remove("legacy");
        })
        .build();
~~~

`defaultCookies(Consumer<MultiValueMap<String,String>>)` mở map defaults cho phép add, replace hoặc remove cookies. Khi dùng `cookies.set`, danh sách values của cookie cùng key được thay mới.

Để đổi default locale đã khai báo:

~~~java
RestClient client = RestClient.builder()
        .defaultCookie("locale", "en")
        .defaultCookies(cookies ->
                cookies.set("locale", "vi"))
        .build();
~~~

Sau xây dựng, default locale là vi.

### 6.3. Cookie per-call có thể thay default

~~~java
client.get()
        .uri("/products/{id}", 42)
        .cookie("locale", "en")
        .retrieve()
        .body(String.class);
~~~

Spring 6.2 `RequestHeadersSpec.cookie(name,value)` và `cookies(Consumer<MultiValueMap<...>>)` thao tác request cookies. Vì defaultCookie được chèn khi tên chưa tồn tại, request cookie có thể thay default cùng tên.

Ví dụ rõ ý thay:

~~~java
client.get()
        .uri("/products/{id}", 42)
        .cookies(cookies -> cookies.set("locale", "en"))
        .retrieve()
        .body(String.class);
~~~

Khi có nhiều layers thêm Cookie header, kiểm request thực bằng mock để phát hiện duplicate values. Không tự thêm raw `Cookie` header nếu đã dùng cookie API, trừ khi có lý do tương thích đã test.

### 6.4. Request Cookie khác Set-Cookie

- Client outbound gửi **Cookie: locale=vi; theme=light**.
- Server trả **Set-Cookie** để yêu cầu user agent lưu cookie kèm Domain/Path/Expires/Secure/HttpOnly/SameSite.

RestClient.Builder.defaultCookie chỉ thiết lập **request cookie mặc định**; nó **không tự làm browser-like cookie jar** lưu/tự chọn mọi cookie server trả theo session/domain/expiry. Muốn stateful cookie store cần cấu hình HTTP client transport phù hợp và kiểm chính sách.

### 6.5. Bảo mật cookie

Không đặt per-user browser session, refresh token, CSRF token, Authorization cookie trên một RestClient singleton global. User A và B có thể vô tình dùng chung credentials. Không forward raw inbound Cookie header tới host khác. Nếu cần delegated access, thiết kế auth per-request, OAuth/token exchange, host allowlist, TLS và secret redaction.

DefaultCookie phù hợp hơn cho non-sensitive application-level locale/theme và vài service-specific metadata được phép chia sẻ.

## 7. defaultRequest và giá trị động

`defaultRequest(Consumer<RestClient.RequestHeadersSpec<?>>)` giúp tùy chỉnh mọi request được build, ví dụ sinh correlation ID khi request chưa có:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultRequest(spec -> spec.headers(headers -> {
            if (!headers.containsKey("X-Correlation-ID")) {
                headers.set("X-Correlation-ID",
                        UUID.randomUUID().toString());
            }
        }))
        .build();
~~~

Đây là fragment, cần import UUID. Khác `defaultHeader` là có thể tạo UUID **mỗi request**, không một lần duy nhất lúc bootstrap. Nếu app dùng distributed tracing, nên propagate trace IDs đáng tin cậy từ observation context; tránh sinh ID độc lập ở mỗi hop khiến trace bị đứt.

| API | Điểm áp dụng |
| --- | --- |
| `defaultHeader` | Header ổn định, khi request chưa có |
| `defaultHeaders` | Chỉnh toàn bộ default header map lúc cấu hình builder |
| `defaultCookie` | Cookie ổn định, khi request chưa có cùng tên |
| `defaultCookies` | Chỉnh default cookie map |
| `defaultRequest` | Callback thực thi với mỗi request spec |
| `get().header/cookie` | Chỉ một request |
| `requestInterceptor` | Intercept quá trình outbound execution, logging/tracing/policy |

Với dynamic Authorization, cần bảo đảm identity/token được lấy theo mỗi request từ trusted context, chứ không giữ mutable `lastToken` ở singleton. Tách clients theo trust boundary và tránh gửi token nếu URL có thể bị caller thay bằng absolute URL khác host.

## 8. Spring Boot 3.5 và RestClient.Builder injection

Spring Boot auto-configuration tạo `RestClient.Builder` bean có **prototype scope**, nghĩa là mỗi injection point có builder được cấu hình riêng. Boot có thể áp HTTP converters, observation/tracing, HTTP client factories và `RestClientCustomizer`.

Trong ứng dụng Boot:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", "inventory-service")
                .defaultCookie("locale", "vi")
                .build();
    }
}
~~~

Dùng Boot-injected builder thay vì tự gọi `RestClient.builder()` tại nhiều chỗ nếu bạn cần giữ những customizers/observation policies của ứng dụng.

### 8.1. RestClientCustomizer

Spring Boot 3.5 có `RestClientCustomizer` callback cấu hình các RestClient builders:

~~~java
@Bean
RestClientCustomizer platformCustomizer() {
    return builder -> builder.defaultHeader(
            "X-Platform", "learning-platform");
}
~~~

Đây là fragment với import `org.springframework.boot.web.client.RestClientCustomizer`. Global customizer chỉ nên thiết lập header chính sách thật sự **chung tất cả upstream**. Đừng set base URL hoặc cookie catalog trên mọi client vì billing/auth destinations có audience khác.

### 8.2. RestClientBuilderConfigurer

Spring Boot còn có `RestClientBuilderConfigurer` để áp Boot defaults lên một builder tự tạo. Nó hữu ích cho extension library hoặc custom builder factory. Ứng dụng thông thường chỉ cần inject builder từ Boot.

### 8.3. Một client cho một upstream

Nếu cần catalog và billing:

~~~java
@Bean
RestClient catalogClient(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.test").build();
}

@Bean
RestClient billingClient(RestClient.Builder builder) {
    return builder.baseUrl("https://billing.example.test").build();
}
~~~

Trên hai beans, dùng `@Qualifier` rõ ràng trong consumers nếu có nhiều RestClient beans. Prototype builder giúp tránh chia sẻ cùng mutable builder giữa hai upstreams.

### 8.4. Properties và secrets

~~~properties
catalog.base-url=https://catalog.example.test/v1
catalog.client-name=inventory-service
catalog.locale=vi
~~~

Config baseURL từ environment/config management. Token/password phải ở secret manager hoặc biến môi trường bảo vệ, không hardcode Git/README. Validate scheme=https và host allowlist trước khi app dùng dynamic endpoint settings.

## 9. Dự án Maven chạy độc lập (Java 17 + Spring Boot 3.5.0)

### 9.1. Cấu trúc

~~~text
restclient-defaults-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RestClientDefaultsApplication.java
    │   └── resources/application.properties
    └── test/java/demo/CatalogGatewayTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>restclient-defaults-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

Dùng `spring-boot-starter-web` vì đây là HTTP client **đồng bộ** trong Boot MVC app; nó kéo vào `spring-web`, Jackson và các dependencies cơ bản. Demo không cần WebFlux starter.

### 9.3. application.properties

~~~properties
catalog.base-url=https://catalog.example.test/v1
catalog.client-name=inventory-service
catalog.locale=vi
~~~

URL `catalog.example.test` là example-only. App không gọi URL lúc startup; unit tests dùng mock HTTP response nên không có network.

### 9.4. RestClientDefaultsApplication.java

Lưu **toàn bộ** Java sau vào `src/main/java/demo/RestClientDefaultsApplication.java`. Chỉ một public top-level class, những class/record còn lại package-private, tương thích Java 17.

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class RestClientDefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                RestClientDefaultsApplication.class, args);
    }
}

record Product(long id, String name) {
}

@Configuration(proxyBeanMethods = false)
class CatalogConfig {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl,
            @Value("${catalog.client-name}") String clientName,
            @Value("${catalog.locale}") String locale) {
        return create(builder, baseUrl, clientName, locale);
    }

    static RestClient create(RestClient.Builder builder,
                             String baseUrl,
                             String clientName,
                             String locale) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", clientName)
                .defaultHeaders(headers -> {
                    headers.set("X-API-Version", "2026-10");
                    headers.setAccept(
                            List.of(MediaType.APPLICATION_JSON));
                })
                .defaultCookie("locale", locale)
                .defaultCookies(cookies ->
                        cookies.set("theme", "light"))
                .build();
    }
}

@Service
class CatalogGateway {
    private final RestClient client;

    CatalogGateway(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    Product getProduct(long id) {
        Product response = client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
        return Objects.requireNonNull(
                response, "Empty product response");
    }

    Product getProductWithOverrides(long id) {
        Product response = client.get()
                .uri("/products/{id}", id)
                .header("X-Client-Name", "special-job")
                .cookie("locale", "en")
                .retrieve()
                .body(Product.class);
        return Objects.requireNonNull(
                response, "Empty product response");
    }
}
~~~

**Giải thích:**

- Spring Boot quản lý RestClient.Builder bean; code build một reusable RestClient.
- `CatalogConfig.create(...)` cho phép unit test truyền mock builder để không gọi API thật.
- `baseUrl` hợp nhất upstream host và version path.
- Default headers gồm X-Client-Name, X-API-Version và Accept JSON.
- Default cookies gồm `locale=vi` và `theme=light`.
- Method có overrides thay X-Client-Name và locale chỉ trên request đó.
- `Objects.requireNonNull` minh họa xử lý response body rỗng; production nên map thành typed domain exception.
- `Product` là record immutable phù hợp JSON decoding từ Spring/Jackson.
- Không có per-user token hoặc session cookie global.
- App không khai báo inbound controller; nó chạy để minh họa DI và HTTP client bean. Tests là cách chạy demo đầy đủ mà không cần catalog server.

### 9.5. CatalogGatewayTest.java

Lưu `src/test/java/demo/CatalogGatewayTest.java`:

~~~java
package demo;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogGatewayTest {
    private MockRestServiceServer server;
    private CatalogGateway gateway;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        // Bind trước RestClient.build().
        server = MockRestServiceServer.bindTo(builder).build();
        RestClient rest = CatalogConfig.create(
                builder,
                "https://catalog.example.test/v1",
                "inventory-service",
                "vi");
        gateway = new CatalogGateway(rest);
    }

    @Test
    void baseUrlHeadersAndCookiesAreApplied() {
        server.expect(requestTo(URI.create(
                        "https://catalog.example.test/v1/products/7")))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Client-Name", "inventory-service"))
                .andExpect(header(
                        "X-API-Version", "2026-10"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andExpect(request -> {
                    String cookie = request.getHeaders().getFirst(
                            HttpHeaders.COOKIE);
                    assertTrue(cookie != null
                            && cookie.contains("locale=vi"));
                    assertTrue(cookie != null
                            && cookie.contains("theme=light"));
                })
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Coffee\"}",
                        MediaType.APPLICATION_JSON));

        Product p = gateway.getProduct(7);
        assertEquals(7L, p.id());
        assertEquals("Coffee", p.name());
        server.verify();
    }

    @Test
    void requestHeaderAndCookieOverrideDefaults() {
        server.expect(requestTo(
                        "https://catalog.example.test/v1/products/8"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("X-Client-Name", "special-job"))
                .andExpect(request -> {
                    String cookie = request.getHeaders().getFirst(
                            HttpHeaders.COOKIE);
                    assertTrue(cookie != null
                            && cookie.contains("locale=en"));
                    assertFalse(cookie != null
                            && cookie.contains("locale=vi"));
                    assertTrue(cookie != null
                            && cookie.contains("theme=light"));
                })
                .andRespond(withSuccess(
                        "{\"id\":8,\"name\":\"Tea\"}",
                        MediaType.APPLICATION_JSON));

        Product p = gateway.getProductWithOverrides(8);
        assertEquals(8L, p.id());
        server.verify();
    }

    @Test
    void http404ThrowsByDefault() {
        server.expect(requestTo(
                        "https://catalog.example.test/v1/products/999"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.NotFound.class,
                () -> gateway.getProduct(999));
        server.verify();
    }
}
~~~

### 9.6. Chạy kiểm thử

~~~bash
mvn test
~~~

Tests dùng `MockRestServiceServer.bindTo(RestClient.Builder)` để thay outgoing HTTP request factory **trước khi build RestClient**, tránh DNS/network thật. Chúng xác minh:

1. URI gồm đúng host + `/v1/products/7`.
2. Default client header và API-version.
3. Accept JSON.
4. Cookies được gửi qua HTTP Cookie header.
5. Một request có thể override header/cookie cùng tên.
6. JSON decode thành Java record đúng.
7. `retrieve()` ném typed HttpClientErrorException khi response 404.

Cookie assertions dùng `contains` để không phụ thuộc thứ tự cookie pairs. Nếu sửa config hoặc nâng version làm test fail, đọc request thực và Javadoc version tương ứng trước khi nới test.

Chạy app riêng:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng khởi động Spring Boot MVC runtime, tạo CatalogGateway bean, **không gửi outbound HTTP call** cho tới khi bạn gọi gateway qua service/controller khác. Để gọi upstream thật, cấu hình URL an toàn, TLS/timeout/auth và contract thật. Không đưa token nhạy cảm vào README hay Git.

## 10. Tùy chỉnh nâng cao cho production

### 10.1. Timeout

`baseUrl`, header và cookie defaults **không tự cấu hình timeout**. Underlying HTTP request factory quyết định connect/read/response timeout, có thể khác giữa JDK HttpClient, Apache HttpComponents và các clients khác.

Ví dụ fragment với SimpleClientHttpRequestFactory:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofSeconds(5));

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://catalog.example.test/v1")
        .build();
~~~

Phải kiểm Javadoc exact Spring version và transport; Boot có request-factory configuration để giữ observability/SSL/pooling settings.

### 10.2. Error handling

`retrieve()` mặc định ném exceptions với HTTP 4xx/5xx, ví dụ `HttpClientErrorException.NotFound`. Có thể dùng `onStatus` per-request hoặc `defaultStatusHandler` ở builder.

~~~java
RestClient client = RestClient.builder()
        .defaultStatusHandler(
                status -> status.value() == 429,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Upstream rate-limited");
                })
        .build();
~~~

Đây là fragment. Production nên dùng typed domain exception, không trả raw upstream body có thể chứa SQL/secrets/tokens. Khi sử dụng `exchange(...)` cấp thấp, việc xử lý status/body có contract khác với `retrieve()`; đọc Javadoc trước khi thay.

### 10.3. Interceptor

~~~java
ClientHttpRequestInterceptor interceptor =
        (request, body, execution) -> {
            request.getHeaders().set(
                    "X-Platform", "spring-course");
            return execution.execute(request, body);
        };

RestClient client = RestClient.builder()
        .requestInterceptor(interceptor)
        .build();
~~~

Đây là fragment, cần imports. Interceptor gần thời điểm I/O và có thể thay request/response. Không log Authorization, Cookie, Set-Cookie hoặc raw request body. Nếu Spring Boot đã cấu hình Micrometer tracing, tránh tự tạo duplicate spans.

### 10.4. Pooling và thread usage

RestClient bản thân là API abstraction; pooling/keepalive thuộc underlying HTTP client. Reuse client bean, cấu hình max connections/pending acquire/idle evict/response timeouts phù hợp và đo latency. RestClient synchronous giữ caller thread trong suốt HTTP call: gọi 100 remote endpoints song song bằng 100 threads vẫn có resource cost thực.

### 10.5. Retry và idempotency

Không retry mọi `POST /payments` nếu thiếu idempotency key/deduplication. Với GET idempotent và transient failures, có thể dùng resilience library/circuit breaker với bounded retries, backoff, jitter, overall deadline và metrics. Cookie/Authorization của một upstream không được gửi đến redirect destination ngoài allowlist.

## 11. An toàn của header/cookie mặc định

### 11.1. Sai lầm chia sẻ user session

Sai trong multi-user service:

~~~java
@Bean
RestClient client() {
    return RestClient.builder()
            .defaultCookie("session", "user-a-session")
            .build();
}
~~~

Mọi request qua singleton có thể mang credential của user A. Không chuyển nguyên inbound Cookie header sang downstream host khác. Tách service credentials và user-delegated tokens; dùng token exchange/per-request authorization thay vì mutable user session ở bean scope.

### 11.2. Nhầm request cookie với browser cookie store

`defaultCookie("locale","vi")` tạo request Cookie header cho các calls phù hợp. Nó không tự nhận Set-Cookie, lưu expires/domain/path/SameSite và chọn cookies cho hosts như browser; muốn session cookie management thực cần request factory/HTTP client cookie store cụ thể. Không giả định auto-login.

### 11.3. SSRF và absolute URI

Một malicious caller có thể cung cấp `http://169.254.169.254/...` hoặc private-network URL nếu bạn cho phép absolute destination tùy ý. Nếu RestClient có default Authorization/Cookie thì rủi ro tăng. Hạn chế outgoing hosts, vô hiệu/chặn redirects tùy policy, xác thực DNS/IP trước connect theo kiến trúc, không trộn trusted và untrusted destinations.

### 11.4. Redaction/observability

Logs nên có method, route template, upstream service name, HTTP status và latency. Không log raw Authorization/Cookie/Set-Cookie, không đưa raw query strings chứa token vào trace tags, và không dùng requestId/userId làm metric label high-cardinality. Tracing context là nguồn correlation đáng tin hơn tự gắn ID ở mọi lớp.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `defaultCookie` không compile | Spring Framework < 6.2 | Kiểm effective `spring-web` version |
| HTTP URL bỏ baseUrl | Request dùng absolute URL | Kiểm URI cuối bằng mock |
| Path `/v1/v1` | Prefix lặp | Chọn một owner path prefix |
| defaultUriVariables không hoạt động | Custom `uriBuilderFactory` override | Kiểm URI builder setup |
| Header mặc định bị bỏ qua | Request đã có header tên đó | Kiểm per-call specs |
| Header nhiều values ngoài ý muốn | Dùng add thay set | Dùng headers(h -> h.set(...)) |
| Cookie locale mặc định không xuất hiện | Request cookie locale khác | Điều kiện defaultCookie |
| Duplicate Cookie | Thêm raw Cookie header và cookie API | Dùng một nguồn |
| Cookie có nhưng upstream vẫn 401 | Session token invalid hoặc sai audience | Auth protocol riêng |
| User A session sang user B | Global cookie nhạy cảm | Chuyển sang per-request auth |
| Boot observability mất | Raw builder thay Boot-injected builder | Inject RestClient.Builder |
| 404 ném exception | Retrieve defaults | Handle typed error |
| Mock test vẫn gọi Internet | Bind mock vào builder khác/đã build | bindTo(builder) trước build |
| Cookie test sai vì thứ tự fields | Serializing/order khác | Assert contents semantics |
| Requests treo | Chưa đặt timeout underlying HTTP client | Connect/read timeouts |
| Throughput kém | Nhiều blocking calls/không pooling | Reuse client, optimize threads |
| Credential hiện trong logs | Logging raw headers | Redact sensitive headers |

## 13. Bài tập

**Bài 1.** Xây RestClient với baseUrl, default X-Client-Name và locale cookie. GET /products/{id}, decode JSON thành record.

**Bài 2.** Dùng defaultHeaders set Accept JSON, X-API-Version và remove X-Legacy. So sánh add/set/remove.

**Bài 3.** Dùng defaultCookies thiết lập theme=light, thay locale=en thành vi và xóa unused cookie.

**Bài 4.** Ghi đè X-Client-Name và locale chỉ trong một GET, chứng minh request sau vẫn có defaults.

**Bài 5.** Dùng URI template path variable và URI query builder; kiểm ký tự đặc biệt được encode đúng.

**Bài 6.** Kiểm absolute URI bỏ qua baseUrl. Phân tích cách chặn host không được phép.

**Bài 7.** Dùng defaultRequest tạo correlation ID theo request thay vì một UUID tạo lúc build.

**Bài 8.** Khai báo hai RestClient beans dùng Boot prototype builder injection, một cho catalog và một cho billing, không lẫn cookies.

**Bài 9.** Viết MockRestServiceServer tests kiểm URL, method, Accept, header, cookie, JSON decoding, 404 exception.

**Bài 10.** Thử thiếu defaultCookie khi dùng Spring 6.1; nâng Framework 6.2 và phân tích API mới.

**Bài 11.** Cấu hình HTTP timeout, kiểm response chậm và phân biệt network timeout với HTTP 504.

**Bài 12.** Thiết kế safe per-user delegated auth thay vì defaultCookie session trên singleton.

**Bài 13.** Viết interceptor chỉ log status/latency; bảo đảm Cookie/Authorization bị redact.

**Bài 14.** So sánh RestClient và WebClient khi dùng trong ứng dụng WebFlux event loop.

**Bài 15.** Thêm retry có giới hạn cho GET idempotent, giải thích vì sao POST payment khác.

## 14. Checklist

- [ ] Dùng Spring Framework 6.2+ khi gọi `RestClient.Builder.defaultCookie(s)`.
- [ ] Base URL đến từ trusted config và được validate.
- [ ] Header defaults chỉ là application-wide settings, không mang per-user credentials.
- [ ] Cookie defaults an toàn cho tất cả calls qua RestClient shared.
- [ ] URL không nhận arbitrary user-controlled absolute destination.
- [ ] Không chèn path/version prefix hai lần.
- [ ] URI path/query variables dùng builder/template đúng encoding.
- [ ] Per-call overrides được test thực tế.
- [ ] Dùng Boot-injected RestClient.Builder nếu cần Boot customizations.
- [ ] Không mutate builder/client internals concurrent khi app chạy.
- [ ] Có connect/read timeout, TLS, connection pool metrics.
- [ ] 4xx/5xx được map an toàn khi cần.
- [ ] Retries chỉ cho transient/idempotent operations.
- [ ] Không log Cookie/Set-Cookie/Authorization/raw PII.
- [ ] MockRestServiceServer được gắn trước RestClient.build().
- [ ] Không gọi synchronous RestClient trực tiếp trên WebFlux event loop.

## 15. Ghi nhớ

- **RestClient là synchronous**: request chặn caller thread trong lúc chờ HTTP I/O.
- `RestClient.Builder.baseUrl` thiết lập URL cho relative URI; absolute request URI có thể override base.
- `defaultHeader/defaultCookie` chỉ áp khi request chưa có field/cookie cùng tên.
- `defaultHeaders/defaultCookies` cho phép chỉnh map defaults.
- **Spring Framework 6.2 mới có RestClient.Builder.defaultCookie/defaultCookies**; kiểm BOM version.
- `defaultRequest` thích hợp cho custom metadata động theo request.
- Spring Boot 3.5 có auto-configured `RestClient.Builder` prototype; inject builder để giữ customizers/observations.
- Một RestClient shared không được chứa per-user auth/cookie secrets.
- Test outbound behavior bằng `MockRestServiceServer.bindTo(builder)` trước `build()`.
- Base URL và defaults không thay timeout, TLS, authentication hoặc retry policy.

## 16. Tài liệu chính thức

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html).
- [RestClient.Builder 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html).
- [RestClient.RequestHeadersSpec 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html).
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html).
- [Spring Boot 3.5 RestClientAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html).
- [Spring Boot 3.5 RestClientCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html).
- [MockRestServiceServer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 6265 — HTTP Cookies](https://www.rfc-editor.org/rfc/rfc6265).
