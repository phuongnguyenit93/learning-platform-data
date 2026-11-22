# Tạo builder, tái sử dụng client và mutate cấu hình

**Ngữ cảnh:** Spring Framework Reactive → **Gửi yêu cầu WebClient**.

`WebClient` là HTTP client reactive của Spring WebFlux. Nó gửi request bằng `Mono`/`Flux`, giải mã response qua codec và kết hợp outbound HTTP vào pipeline Reactor. Khi ứng dụng gọi nhiều API, hãy cấu hình client ở thời điểm khởi động, build thành một `WebClient` có thể tái sử dụng, rồi tạo biến thể có chủ đích bằng `mutate()` khi cần.

Bốn khái niệm cốt lõi:

- **Builder:** đối tượng cấu hình có thể thay đổi, dùng để thiết lập base URL, header mặc định, filter, codec, connector, timeout và các chính sách khác.
- **build():** tạo một `WebClient` từ cấu hình hiện tại của builder.
- **Reuse:** một `WebClient` đã build là immutable và thread-safe; có thể dùng đồng thời từ nhiều request.
- **mutate():** tạo builder mới được khởi tạo từ cấu hình của client hiện có; thay đổi builder mới rồi build để tạo client khác. Client gốc không bị sửa.

Điểm quan trọng là tách cấu hình dùng chung khỏi dữ liệu riêng của từng request. Base URL, codec và connection pool thường thuộc client; bearer token, tenant ID hay correlation ID của người dùng thường thuộc request hiện tại.

## 1. Vòng đời cấu hình WebClient

Một ứng dụng thường tạo client khi Spring context khởi động:

```text
Application startup
       |
       v
WebClient.Builder
       |
       +-- baseUrl / URI strategy
       +-- default headers / cookies
       +-- ExchangeFilterFunction
       +-- codecs / ExchangeStrategies
       +-- ClientHttpConnector
       +-- timeout / connection pool
       |
       v
     build()
       |
       v
Reusable WebClient
       |
       +---- request A
       +---- request B
       +---- request C
       |
       v
Reactor pipeline + HTTP transport
```

Builder là nơi tập hợp cấu hình. Sau khi gọi `build()`, client giữ cấu hình đã tạo và có thể được chia sẻ giữa nhiều thread. Mỗi request vẫn tạo request specification riêng bằng `get()`, `post()`, `put()` hoặc `method(...)`.

Không cần tạo một `WebClient` mới cho mỗi HTTP call. Việc đó lặp cấu hình, có thể tạo thêm connection provider/connection pool và làm quản lý tài nguyên khó hơn.

## 2. Tạo WebClient bằng builder

Cách cơ bản:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
```

`WebClient.builder()` tạo builder mới. `baseUrl` đặt base URI cho các URI tương đối. `defaultHeader` khai báo header mặc định nếu request cụ thể chưa cung cấp header đó. `build()` tạo client.

Có thể dùng factory ngắn hơn:

```java
WebClient client = WebClient.create(
        "https://catalog.example.com");
```

`WebClient.create(baseUrl)` tiện cho client đơn giản. Khi cần filter, codec, connector, timeout hoặc nhiều default, builder linh hoạt hơn.

Một cấu hình tách thành bean:

```java
@Configuration
class OutboundClientConfiguration {

    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.com")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

Đây là snippet Spring Boot cần imports và component scan phù hợp. Khi inject builder do Spring Boot auto-configure cung cấp, builder đã được Boot cấu hình theo các customizer và codec settings của ứng dụng.

Nếu không dùng Spring Boot, có thể tự tạo `WebClient.builder()` và đăng ký connector/codec cần thiết. Đừng giả định một builder tự tạo có mọi customizer mà Boot cung cấp.

## 3. baseUrl và cách giải quyết URI

`baseUrl` thuận tiện khi nhiều endpoint cùng một host:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com/v1")
        .build();

Mono<Item> item = client.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .bodyToMono(Item.class);
```

URI được tạo từ template và biến truyền vào. Có thể dùng lambda để cấu hình URI builder:

```java
Mono<Item> item = client.get()
        .uri(builder -> builder
                .path("/items/{id}")
                .queryParam("include", "details")
                .build(42))
        .retrieve()
        .bodyToMono(Item.class);
```

Một số quy tắc:

- URI tương đối được giải quyết dựa trên base URI.
- URI tuyệt đối trong lời gọi request có thể chỉ định host khác và không dùng base URL làm host.
- Nếu cấu hình `uriBuilderFactory`, đó là chiến lược tạo URI chủ đạo; không nên đồng thời mong `baseUrl` điều khiển cùng cấu hình.
- `defaultUriVariables` cung cấp giá trị mặc định cho URI template variables khi phù hợp.
- Với nhiều host hoặc tenant, có thể truyền URI tuyệt đối theo request hoặc tạo client riêng cho từng upstream có policy khác nhau.

Không nối chuỗi URL bằng cách cộng path và query tùy tiện. Dùng URI template hoặc URI builder để encode path segment, query parameter và ký tự đặc biệt đúng cách.

## 4. Header và cookie mặc định

Builder hỗ trợ `defaultHeader`, `defaultHeaders`, `defaultCookie` và `defaultCookies`.

```java
WebClient client = WebClient.builder()
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Application", "order-service")
        .defaultCookie("client-version", "2")
        .build();
```

Default header được áp dụng khi request chưa có header cùng tên. Request có thể cung cấp giá trị riêng cho chính request đó:

```java
Mono<Item> result = client.get()
        .uri("/items/42")
        .header("X-Request-Source", "mobile")
        .retrieve()
        .bodyToMono(Item.class);
```

Dùng `defaultHeaders(Consumer<HttpHeaders>)` khi muốn chỉnh sửa tập header mặc định như một nhóm:

```java
WebClient client = WebClient.builder()
        .defaultHeaders(headers -> {
            headers.setAccept(
                    List.of(MediaType.APPLICATION_JSON));
            headers.set("X-Application", "inventory");
        })
        .build();
```

Tương tự, `defaultCookies` cho phép thêm hoặc thay đổi cookie mặc định. Cookie mặc định không nên chứa session hoặc thông tin nhận diện người dùng thay đổi theo từng request.

### 4.1. Header mặc định không phải header bắt buộc

Default header là giá trị dự phòng. Request specification có thể đặt header riêng. Điều này hữu ích khi một client gọi nhiều endpoint nhưng mỗi request có correlation ID, locale hoặc tenant khác nhau.

Không đặt token của user A vào default header của một singleton client rồi dùng client đó cho user B. Hãy gắn credential theo request:

```java
Mono<Account> account = client.get()
        .uri("/accounts/me")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Account.class);
```

`accessToken` ở đây phải thuộc request hiện tại và được lấy từ security context phù hợp. Không giữ token người dùng trong field mutable của bean `WebClient`.

Nếu mỗi client đại diện một service account cố định, credential service-level có thể nằm trong cấu hình client riêng; vẫn phải bảo vệ secret trong configuration/secret manager và xoay vòng theo policy.

## 5. WebClient có thể tái sử dụng giữa nhiều request

`WebClient` được thiết kế immutable sau khi build và thread-safe. Một bean singleton có thể được inject vào nhiều service:

```java
@Service
class CatalogService {

    private final WebClient catalogClient;

    CatalogService(WebClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    Mono<Item> findItem(String id) {
        return catalogClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

Nhiều lời gọi `findItem` có thể diễn ra đồng thời. Request specification được tạo mới cho mỗi lần gọi; cấu hình client không bị thay đổi bởi request.

Lợi ích của reuse:

- Tái sử dụng connection pool và cấu hình HTTP connector.
- Tập trung base URL, codec, TLS, timeout và filter.
- Giảm việc tạo object cấu hình lặp lại.
- Dễ kiểm thử bằng cách thay bean hoặc cấu hình connector.
- Có một nơi rõ ràng để quản lý observability và chính sách outbound.

**Reuse client không có nghĩa là reuse một request builder.** Không lưu `RequestHeadersSpec`, `RequestBodySpec` hoặc request-specific mutable object vào field singleton. Hãy tạo request mới từ client cho mỗi lần gọi.

## 6. WebClient.Builder trong Spring Boot

Spring Boot auto-configure `WebClient.Builder` với các customizer và codec phù hợp dependency hiện có. Có thể inject builder vào bean factory method để tạo các client chuyên biệt:

```java
@Configuration
class ApiClients {

    @Bean
    WebClient inventoryClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.com")
                .defaultHeader("X-Client", "inventory-adapter")
                .build();
    }

    @Bean
    WebClient pricingClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://pricing.example.com")
                .defaultHeader("X-Client", "pricing-adapter")
                .build();
    }
}
```

Trong Spring Boot, builder auto-configured có scope prototype: mỗi lần inject có thể nhận một builder riêng đã được customizer của Boot áp dụng. Điều này giúp các bean client cấu hình riêng mà không vô tình chia sẻ cùng một builder mutable. Hãy kiểm tra tài liệu đúng phiên bản Boot nếu thay đổi scope hoặc tự định nghĩa builder bean.

Nếu tự khai báo một builder singleton dùng chung, việc gọi các method cấu hình trên builder có thể ảnh hưởng lần build tiếp theo. Không sửa builder dùng chung đồng thời từ nhiều thread hoặc từ mỗi request.

### 6.1. Nhiều client, một bộ cấu hình chung

Nếu nhiều client cần cùng một chính sách, tạo customizer dùng chung hoặc method factory:

```java
private WebClient.Builder configureCommon(
        WebClient.Builder builder) {

    return builder
            .defaultHeader(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE);
}
```

Sau đó mỗi bean áp dụng phần chung và thêm cấu hình riêng. Với Boot, có thể dùng `WebClientCustomizer` để cấu hình builder auto-configured ở cấp ứng dụng. Hãy giới hạn customizer ở những chính sách thực sự dùng chung; không đưa base URL hay credential riêng của một upstream vào customizer toàn cục.

## 7. mutate(): tạo biến thể từ một client đã build

`WebClient.mutate()` trả về một builder được khởi tạo từ cấu hình hiện tại của client. Bạn có thể thay đổi base URL, default headers, filter, connector hoặc các thiết lập builder khác rồi build client mới.

Ví dụ:

```java
WebClient publicClient = WebClient.builder()
        .baseUrl("https://api.example.com")
        .defaultHeader("X-Client", "public")
        .build();

WebClient adminClient = publicClient.mutate()
        .defaultHeaders(headers ->
                headers.set("X-Client", "admin"))
        .build();
```

Kết quả:

- `publicClient` vẫn giữ header mặc định `X-Client: public`.
- `adminClient` là client mới với default header `X-Client: admin`.
- Cấu hình chung đã có trong public client được mang sang builder mới, trừ phần bạn thay đổi.
- `mutate()` không sửa client gốc tại chỗ.

Đây là cách phù hợp để tạo client cho các biến thể có chung connector, codec hoặc filter nhưng khác base URL, default header hay policy.

### 7.1. mutate không phải đổi cấu hình singleton hiện tại

Ví dụ sau không làm thay đổi client ban đầu:

```java
WebClient original = WebClient.builder()
        .baseUrl("https://api.example.com")
        .build();

WebClient regional = original.mutate()
        .baseUrl("https://eu-api.example.com")
        .build();
```

`original` vẫn trỏ tới host cũ. `regional` dùng host mới. Nếu service tiếp tục gọi `original`, nó không tự chuyển sang cấu hình regional.

Hãy lưu client mới vào bean/field phù hợp hoặc trả nó từ factory. Không mong `mutate()` cập nhật mọi nơi đang tham chiếu client cũ.

### 7.2. Khi nào nên dùng mutate?

- Cùng một upstream nhưng có client public/admin với default header khác.
- Cùng codec và connector nhưng base URL khác theo region.
- Tạo client chuyên dụng cho một integration test hoặc một nhóm API.
- Thêm filter/observation riêng cho một client dẫn xuất.
- Giữ cấu hình chung và chỉ thay một vài policy.

Nếu hai client khác biệt nhiều về TLS, credential, timeout, proxy hoặc connection pool, hãy cân nhắc tạo builder độc lập. Dùng mutate chỉ vì tiện có thể mang theo filter hoặc default header không phù hợp.

## 8. Builder cấu hình filter

`ExchangeFilterFunction` cho phép chặn request/response ở client side. Filter thường dùng cho correlation ID, metrics, tracing, logging có chọn lọc, authentication service-level hoặc chuyển đổi lỗi.

Ví dụ thêm filter ghi nhận method và URL:

```java
ExchangeFilterFunction requestMetric =
        ExchangeFilterFunction.ofRequestProcessor(request -> {
            metrics.recordRequest(
                    request.method().name(),
                    request.url().getHost());

            return Mono.just(request);
        });

WebClient client = WebClient.builder()
        .filter(requestMetric)
        .build();
```

Đây là snippet cần metrics implementation và imports. Filter nhận request trước khi gửi đi, rồi trả request cho exchange chain. Có thể dùng `ofResponseProcessor` để quan sát status response:

```java
ExchangeFilterFunction responseMetric =
        ExchangeFilterFunction.ofResponseProcessor(response -> {
            metrics.recordStatus(
                    response.statusCode().value());

            return Mono.just(response);
        });
```

Không đọc body response trong filter chỉ để log nếu không có chủ đích. Body là stream có ownership; đọc nó có thể tiêu thụ dữ liệu mà caller cần. Nếu cần inspect body, phải thiết kế cách buffer/rebuild đúng và đặt giới hạn kích thước.

### 8.1. filter và filters

- `filter(filter)` thêm một filter vào chuỗi.
- `filters(consumer)` cho phép xem và chỉnh sửa danh sách filter hiện có.
- `mutate()` có thể mang theo các filter từ client gốc; thêm cùng filter lần nữa có thể khiến logic chạy lặp.

Khi tạo client dẫn xuất, hãy biết filter nào đã tồn tại. Nếu cần thay thế hoặc loại một filter, dùng `filters(...)` với predicate rõ ràng và test chuỗi thực tế.

Không log Authorization, cookie, password, query chứa token hoặc response body nhạy cảm. Correlation ID và method/path thường đủ cho quan sát request ở mức cơ bản.

## 9. Codec và giới hạn bộ nhớ

Builder cho phép tùy chỉnh codec thông qua `codecs`:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
        .build();
```

Ví dụ đặt giới hạn 512 KiB cho các thao tác codec aggregate có áp dụng giới hạn này. Chọn con số theo payload thực tế; không coi đây là giới hạn tổng RAM của client hoặc giới hạn mọi buffer.

Có thể đăng ký codec custom khi ứng dụng cần media type hoặc serialization đặc thù. Ưu tiên cấu hình default codec khi chỉ cần thay một thuộc tính; chỉ thay toàn bộ `ExchangeStrategies` khi thực sự cần kiểm soát danh sách reader/writer.

Các lưu ý:

- Body lớn có thể cần streaming thay vì aggregate thành một object.
- `bodyToMono(String.class)` có thể gom body thành một String; đặt giới hạn phù hợp.
- `bodyToFlux(DataBuffer.class)` đưa byte buffer thô cho ứng dụng; phải quản lý ownership/release.
- Không tăng `maxInMemorySize` vô hạn chỉ để che lỗi payload quá lớn.
- Request/response body cần đúng Content-Type và Accept để codec chọn representation thích hợp.

## 10. ClientHttpConnector và transport

`ClientHttpConnector` nối WebClient với HTTP runtime. WebClient không tự thực hiện socket I/O; connector chuyển request thành thao tác trên client implementation như Reactor Netty.

Có thể chỉ định connector:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

Snippet cần dependency Reactor Netty, `HttpClient`, `ReactorClientHttpConnector` và imports. `responseTimeout` là timeout cho response read theo semantics của connector; nó không thay thế connect timeout, pool acquisition timeout hoặc timeout nghiệp vụ toàn request.

Khi cần connection pool riêng:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("catalog-pool")
                .maxConnections(50)
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

Đây là snippet minh họa. `ConnectionProvider` là resource có lifecycle; nếu ứng dụng tự tạo provider, phải dispose khi ứng dụng shutdown. Không tạo pool mới cho mỗi request hoặc mỗi lần gọi `mutate()` nếu không có lý do rõ ràng.

Các cấu hình transport khác có thể gồm proxy, TLS, connect timeout, response timeout, wiretap và giới hạn connection. Hãy đặt timeout ở từng tầng phù hợp; timeout pool acquisition, connect, response read và toàn bộ workflow có ý nghĩa khác nhau.

## 11. defaultStatusHandler và chính sách lỗi chung

Builder hỗ trợ `defaultStatusHandler` để ánh xạ response status thành exception cho các request dùng `retrieve()`:

```java
WebClient client = WebClient.builder()
        .defaultStatusHandler(
                HttpStatusCode::isError,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new RemoteApiException(
                                response.statusCode(), body)))
        .build();
```

Đây là snippet cần `RemoteApiException` và imports. Handler đọc body lỗi một lần để tạo exception. Không log toàn bộ body nếu nó có thể chứa dữ liệu nhạy cảm; có thể chỉ lấy error code đã chuẩn hóa hoặc giới hạn nội dung.

Nếu chỉ một request có policy lỗi riêng, dùng `retrieve().onStatus(...)` tại request đó. Với `exchangeToMono`/`exchangeToFlux`, ứng dụng tự quyết định cách xử lý status và body trong callback; cần consume hoặc release body đúng lifecycle.

Không nhầm lỗi HTTP 4xx/5xx với lỗi kết nối. `defaultStatusHandler` xử lý status response; DNS failure, connection reset, TLS failure hoặc timeout là lỗi transport và cần error mapping riêng.

## 12. Cấu hình dùng chung và cấu hình theo request

Hãy đặt mỗi loại dữ liệu ở đúng scope:

| Cấu hình | Scope phù hợp | Ví dụ |
|---|---|---|
| Base URL của upstream | Client | `https://catalog.example.com` |
| Accept mặc định | Client | `application/json` |
| Codec và max in-memory size | Client | JSON, NDJSON, 512 KiB |
| Connection pool/TLS/proxy | Connector/client | Catalog pool |
| Filter metrics/tracing | Client | Request timing |
| Service account cố định | Client riêng có bảo vệ secret | Credential của integration |
| Bearer token của user hiện tại | Request | `headers.setBearerAuth(token)` |
| Tenant ID theo request | Request | `X-Tenant-Id` |
| Correlation ID theo request | Request/context | `X-Request-Id` |
| Query/path variables | Request | `uri("/items/{id}", id)` |

Không thay đổi default header của một client singleton theo từng request. Nếu code gọi `client.mutate()` rồi build client mới cho từng người dùng, sẽ tạo nhiều client/configuration không cần thiết. Thay vào đó, giữ client dùng chung và đặt dữ liệu cá nhân trên request specification.

## 13. Ví dụ Java 17+ chạy được: build, reuse và mutate

Ví dụ này khởi động một HTTP server Reactor Netty trên port động, tạo một WebClient cơ sở, tạo một client dẫn xuất bằng `mutate()` và gửi nhiều request. Server trả lại ID item cùng header `X-Client` để quan sát cấu hình nào đã được dùng.

Cấu trúc:

```text
webclient-builder-demo/
├── pom.xml
└── src/main/java/demo/WebClientBuilderDemo.java
```

### 13.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webclient-builder-demo</artifactId>
    <version>1.0.0</version>

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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.2. WebClientBuilderDemo.java

```java
package demo;

import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public class WebClientBuilderDemo {

    public static void main(String[] args) {
        DisposableServer server = HttpServer.create()
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes.get(
                        "/items/{id}",
                        (request, response) -> response.sendString(
                                Mono.just(
                                        "item=" + request.param("id")
                                        + ";client="
                                        + request.requestHeaders()
                                                .get("X-Client")))))
                .bindNow();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            WebClient baseClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .defaultHeader("X-Client", "base")
                    .build();

            WebClient adminClient = baseClient.mutate()
                    .defaultHeaders(headers ->
                            headers.set("X-Client", "admin"))
                    .build();

            String baseResult = baseClient.get()
                    .uri("/items/{id}", 42)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String adminResult = adminClient.get()
                    .uri("/items/{id}", 43)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String requestOverride = baseClient.get()
                    .uri("/items/{id}", 44)
                    .headers(headers ->
                            headers.set("X-Client", "request"))
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String baseAgain = baseClient.get()
                    .uri("/items/{id}", 45)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            System.out.println("base: " + baseResult);
            System.out.println("admin: " + adminResult);
            System.out.println("request override: " + requestOverride);
            System.out.println("base again: " + baseAgain);
        }
        finally {
            server.disposeNow();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebClientBuilderDemo
```

**Standard output dự kiến:**

```text
base: item=42;client=base
admin: item=43;client=admin
request override: item=44;client=request
base again: item=45;client=base
```

Giải thích:

1. Server bind port 0 để hệ điều hành chọn một port trống; chương trình đọc port thực tế từ `server.port()`.
2. `baseClient` được build với base URL và default header.
3. `baseClient.mutate()` tạo builder mới mang theo cấu hình base; `adminClient` thay default header thành admin.
4. Request thứ ba ghi đè header ở request scope; không cần tạo client mới cho mỗi giá trị header.
5. Request cuối chứng minh `baseClient` vẫn giữ default header ban đầu sau khi tạo `adminClient`.
6. `block()` chỉ xuất hiện trong `main` của chương trình demo để chờ HTTP response; không gọi `block()` trong WebFlux handler hoặc reactive service.

Ví dụ này minh họa builder/client lifecycle bằng server local. Ứng dụng thực tế thường inject `WebClient` bean và compose `Mono`/`Flux` thay vì gọi `block()`.

## 14. Kiểm thử cấu hình client

Nên kiểm thử hành vi HTTP thực tế, không chỉ kiểm tra rằng bean tồn tại.

Các lựa chọn:

- Dùng `MockWebServer` hoặc HTTP stub server để kiểm tra method, path, query, headers và body request.
- Dùng WireMock hoặc mock HTTP server tương đương để mô phỏng timeout, 4xx/5xx, malformed body và slow response.
- Dùng `ExchangeFunction` giả lập khi chỉ cần unit test logic tạo request và mapping response.
- Dùng integration test với server local khi cần xác nhận connector, codec và connection lifecycle.

Ví dụ dùng mock `ExchangeFunction`:

```java
ExchangeFunction exchange = request -> {
    assertEquals("https://catalog.example.com/items/42",
            request.url().toString());

    return Mono.just(
            ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.APPLICATION_JSON_VALUE)
                    .body("{\"id\":42,\"name\":\"Reactive\"}")
                    .build());
};

WebClient client = WebClient.builder()
        .exchangeFunction(exchange)
        .baseUrl("https://catalog.example.com")
        .build();
```

Đây là snippet test cần JUnit/AssertJ và imports. Một fake ExchangeFunction giúp kiểm tra URI và mapping mà không mở socket; nó không kiểm tra DNS, TLS, pool hoặc transport thật.

Với `mutate()`, hãy test cả hai client:

- Client gốc giữ base URL/default header cũ.
- Client dẫn xuất nhận cấu hình mới.
- Request-level header ghi đè default header đúng cách.
- Filter không bị thêm lặp ngoài ý muốn.
- Cả hai client có codec/connector đúng dự kiến.

## 15. Lỗi thường gặp

1. **Tạo WebClient mới cho mọi request.** Có thể tạo nhiều cấu hình/pool và lặp logic; hãy reuse client đã build.
2. **Nghĩ mutate sửa client gốc.** mutate tạo builder mới; build tạo client khác.
3. **Dùng chung builder mutable giữa nhiều thread.** Cấu hình builder ở startup và không thay đổi đồng thời lúc phục vụ request.
4. **Lưu RequestHeadersSpec trong field singleton.** Request state có thể rò giữa các lời gọi; tạo request spec mới mỗi lần.
5. **Đặt bearer token người dùng vào defaultHeader của client chung.** Có thể gửi nhầm credential giữa user; gắn token theo request.
6. **Cho rằng defaultHeader luôn ghi đè header request.** Default chỉ áp dụng khi request chưa cung cấp giá trị cùng tên.
7. **Dùng baseUrl cho mọi host.** URI tuyệt đối có thể chỉ định host khác; tạo client riêng nếu upstream có policy khác.
8. **Cấu hình baseUrl cùng uriBuilderFactory mà không hiểu precedence.** uriBuilderFactory là chiến lược URI; tránh cấu hình trùng mục đích.
9. **Thêm filter lặp khi mutate.** Filter từ client gốc có thể được mang sang client dẫn xuất; kiểm tra danh sách trước khi thêm.
10. **Đọc response body trong logging filter.** Body có thể bị consume; nếu cần inspect phải buffer/rebuild đúng lifecycle và giới hạn kích thước.
11. **Log Authorization hoặc cookie.** Có thể lộ secret và session; mask hoặc bỏ khỏi log.
12. **Tăng maxInMemorySize vô hạn.** Có thể che payload không hợp lệ và gây áp lực bộ nhớ; chọn limit có chủ đích.
13. **Coi responseTimeout là timeout toàn workflow.** Connect, pool acquire, response read và nghiệp vụ có timeout khác nhau.
14. **Tạo ConnectionProvider riêng nhưng không dispose.** Pool có resource lifecycle; giải phóng khi ứng dụng shutdown.
15. **Coi defaultStatusHandler là handler cho mọi lỗi.** Nó xử lý HTTP status response; lỗi DNS/TLS/timeout cần policy riêng.
16. **Dùng retry tự động cho mọi request.** POST hoặc thao tác không idempotent có thể tạo side effect trùng; thiết kế idempotency và retry policy.
17. **Dùng block trong service reactive.** Chặn thread và phá composition; chỉ dùng ở chương trình main hoặc ranh giới imperative có chủ đích.
18. **Tự subscribe trong service để gửi request.** Caller mất quyền quản lý error/cancel; trả publisher để caller compose.
19. **Thay connector khi mutate mà quên lifecycle cũ.** Xác định client nào sở hữu pool/connector và ai dispose.
20. **Cho rằng WebClient bean tự có base URL đúng.** Cấu hình từng upstream rõ ràng; không phụ thuộc URI tình cờ từ môi trường.

## 16. Checklist cấu hình production

Trước khi đưa WebClient vào production, hãy xác nhận:

- **Client scope:** một client cho upstream hay nhiều client theo policy?
- **Builder:** Boot auto-configured builder hay builder tự tạo? Customizer nào đã được áp dụng?
- **URI:** base URL, URI template, absolute URI và query encoding có đúng?
- **Defaults:** Accept, Content-Type, default headers và cookies có thực sự dùng chung?
- **Credentials:** token user/tenant/correlation ID có nằm ở request scope?
- **Reuse:** client được tạo ở startup và reuse; request specification được tạo mới mỗi call?
- **mutate:** client dẫn xuất có giữ filter/codec/connector cần thiết và thay đúng cấu hình?
- **Filters:** thứ tự filter, duplicate, logging và response body ownership đã rõ?
- **Codecs:** max in-memory size, streaming và media type đã phù hợp?
- **Transport:** connection pool, TLS, proxy, connect/response timeout và shutdown lifecycle đã cấu hình?
- **Errors:** HTTP status, transport failure, retry và idempotency có policy riêng?
- **Observability:** metrics/tracing có request ID nhưng không lộ secret?
- **Tests:** URI/header/body, mutate isolation, 4xx/5xx, timeout và transport đã được kiểm thử?

**Ghi nhớ:** tạo cấu hình bằng `WebClient.builder()`, gọi `build()` để có client immutable có thể tái sử dụng, và dùng `mutate()` để tạo biến thể mới mà không làm đổi client gốc. Giữ base URL, codec, filter và transport ở client scope; giữ token, tenant và correlation ID ở request scope. Khi dùng Spring Boot, tận dụng builder auto-configured; với client custom, quản lý connector/pool, timeout và cleanup theo lifecycle ứng dụng.

## Tài liệu tham khảo

- Spring Framework — [WebClient: Configuration and Builder](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [WebClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html).
- Spring Framework — [WebClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html).
- Spring Framework — [ExchangeFilterFunction Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html).
- Spring Boot — [Calling REST Services with WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html).
- Reactor Netty — [HTTP Client Reference: Connection Pool and Timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html).
