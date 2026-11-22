# Ranh giới giữa cấu hình HTTP client của Spring Boot và tích hợp dịch vụ nghiệp vụ

## 1. Bức tranh tổng thể

Một ứng dụng Spring Boot gọi ra dịch vụ Catalog, Payment, Shipping hoặc API đối tác qua HTTP cần phân biệt **khả năng kỹ thuật để giao tiếp** và **ý nghĩa nghiệp vụ của cuộc giao tiếp**.

- **Spring Boot/HTTP infrastructure** chuẩn bị RestClient.Builder, RestTemplateBuilder hoặc WebClient.Builder; phát hiện HTTP transport; áp dụng cấu hình kết nối, TLS, message converters, codecs, customizers, observability và một số defaults.
- **Integration adapter** chọn host, API version, endpoint, request headers, wire DTO, cách xác thực partner, timeout riêng, response status mapping và quy tắc hợp đồng của một upstream.
- **Application/domain** xử lý use case: báo giá, kiểm tra tồn kho, trạng thái thanh toán, cho phép fallback hay không, quy tắc số lượng, tiền tệ, phân quyền nghiệp vụ.
- **Inbound API/controller** chuyển HTTP request của client cuối sang use case, và chuyển kết quả/domain exception sang public HTTP response. Không trả thẳng toàn bộ raw partner payload/error cho người dùng.

**Nguyên tắc:** Boot hỗ trợ cách tạo HTTP request; adapter hiểu hệ thống ngoài; domain quyết định cần làm gì với kết quả. Không có auto-configuration nào tự biết một response 404 của đối tác nghĩa là “item không tồn tại”, “đường dẫn sai” hay “giao dịch chưa được tạo”.

Bài học thuộc module **Spring Boot - web-runtime**, nhóm **HTTP client**; tập trung vào cách đặt ranh giới, không chỉ giới thiệu ba thư viện. Ví dụ đầy đủ dùng **Java 17+, Maven, Spring Boot 3.5.16 và Spring Framework 6.2.x**. Khi nâng lên Boot major mới, kiểm tra lại package và property names, đặc biệt nhóm HTTP clients.

## 2. Phân biệt ranh giới bằng một request

```text
GET /api/quotes/1?quantity=3
           |
           v
    QuoteController              -> Hợp đồng HTTP public
           |
           v
    CatalogApplicationService    -> Business rule: tồn kho, tiền
           |
           v
    CatalogGateway (port)        -> Nhu cầu: tìm mặt hàng theo ID
           ^
           |
    HttpCatalogGateway           -> API đối tác: path, DTO, 404/503
           |
           v
    catalogRestClient (bean)     -> Builder/transport của Boot
           |
           v
    GET /partner/items/1        -> Catalog service HTTP
```

Khi Catalog đổi JSON field `priceVnd` thành `amountInMinorUnits`, adapter/contract test có thể thay mà không buộc domain đổi. Khi đổi transport từ RestClient sang WebClient hoặc SDK đối tác, những quy tắc như số lượng tối đa và cách tính tiền vẫn không nên nằm trong client. Khi nghiệp vụ không cho bán hàng hết tồn, đó là quy tắc domain, không phải HTTP 409 của partner tự động.

### Bảng phân quyền trách nhiệm

| Quyết định | Boot/transport | Integration adapter | Application/domain |
| --- | --- | --- | --- |
| Dựng `RestClient.Builder` | Có | Inject rồi build | Không |
| HTTP request factory, TLS, codec | Cấu hình cơ sở | Override theo host khi cần | Không |
| Base URL của catalog | Không tự biết | Có, từ typed configuration | Không |
| URI `/partner/items/{id}` | Không | Có | Không |
| Access token dành cho catalog | Có cơ chế hỗ trợ | Sở hữu cách lấy và gắn đúng audience | Quyết định identity được phép |
| Parse `CatalogWireItem` | Converter decode JSON | Kiểm tra schema, map sang domain | Không lệ thuộc DTO |
| Status 404 từ catalog | Client ném exception | Map thành empty/not found theo contract | Xử lý thiếu item |
| Status 503 từ catalog | Client thấy lỗi | Map thành dependency unavailable | Chọn không báo giá |
| Response 409 cho người mua | Không | Không | Public API/domain policy |
| Connect/read timeout chung | Defaults | Override theo SLA dịch vụ | Total deadline phù hợp use case |
| Retry GET hay POST | Library có API | Hiểu idempotency contract | Cho phép hay cấm theo use case |
| Observability | Builders/Actuator integration | Context/partner name, status | Metrics nghiệp vụ |

Không bắt buộc tạo nhiều tầng máy móc cho project nhỏ. Nhưng **mỗi quyết định phải ở tầng có đủ ngữ cảnh để quyết định đúng**.

## 3. Boot 3.5 thực sự auto-configure gì?

### 3.1. RestClient cho ứng dụng imperative

`RestClient` là HTTP client **đồng bộ, fluent**. Spring Boot 3.5 tạo bean `RestClient.Builder` **prototype** đã được chuẩn bị với HTTP message converters, request factory và customizers theo môi trường.

```java
@Bean
RestClient catalogClient(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.internal").build();
}
```

Đây là snippet, không thuộc project hoàn chỉnh ở mục 10. Boot **không tự tạo** bean `catalogClient` cho bạn. App cung cấp URL dịch vụ và quyền sở hữu config; client đã build thường là bean singleton được dùng lại, không khởi tạo mỗi request.

### 3.2. RestTemplate trong code legacy

Boot thường **không cung cấp một bean `RestTemplate` mặc định**, mà cung cấp `RestTemplateBuilder`:

```java
@Bean
RestTemplate legacyClient(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://legacy.example.internal")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

Snippet cần imports `RestTemplateBuilder`, `RestTemplate`, `Duration`. RestTemplate là **blocking** giống RestClient; đổi sang RestClient vì API fluent và khả năng mở rộng, không vì nghĩ RestTemplate là non-blocking. Code cũ có tests và interceptors đang chạy tốt có thể được di trú từng bước.

### 3.3. WebClient trong reactive hoặc streaming

`WebClient.Builder` được chuẩn bị khi WebFlux có trên classpath. `WebClient` trả `Mono`/`Flux` và phù hợp non-blocking HTTP.

```java
@Bean
WebClient warehouseClient(WebClient.Builder builder) {
    return builder
            .baseUrl("https://warehouse.example.internal")
            .build();
}
```

Snippet này chưa là project độc lập. Khi ứng dụng WebFlux thật, không gọi blocking RestClient/RestTemplate hoặc `WebClient.block()` trên Reactor event loop. Trong app MVC cũng có thể dùng WebClient làm outbound HTTP, nhưng **điều đó không tự chuyển toàn bộ app sang WebFlux**.

### 3.4. Builders, customizers và scope

| Cơ chế | Phạm vi | Nên đặt | Không nên đặt |
| --- | --- | --- | --- |
| Boot `spring.http.client.*` | Defaults của synchronous clients | Connect/read timeout, request factory | Business 404/409 policy |
| Boot `spring.http.reactiveclient.*` | Defaults reactive connector | Connect/read timeout, connector | Business fallback |
| `RestClientCustomizer` | Additive customization toàn RestClient builders do Boot quản lý | Kỹ thuật chung không nhạy cảm | Bearer token của một partner |
| `WebClientCustomizer` | Additive customization WebClient | Technical filters, observations khi hợp lý | Token/URL riêng đối tác |
| Per-partner bean | Một HTTP upstream | Base URL, auth, SLA override, SSL trust riêng | Rule giá hàng/vận chuyển |
| Per-request headers | Một lời gọi | Item ID, idempotency key, user context có kiểm soát | Mutable global state |
| Application service | Một use case | Quantity, price, status nghiệp vụ | JSON field, TCP pool |

`RestClient.Builder` và `WebClient.Builder` là **stateful**. Khi sử dụng một builder để tạo nhiều client và liên tục thay `baseUrl`/headers, client được tạo sau mang cấu hình mới; dùng injection riêng hoặc `builder.clone()` khi cần. Client build xong là lựa chọn thích hợp để tái sử dụng.

Nếu gọi `RestClient.create()` hoặc `WebClient.create()` trực tiếp, Boot auto-customizers và một số defaults trên injected builder **không được áp dụng theo cách thông thường**. Không tự thay auto-configured builders nếu chưa hiểu tác động lên TLS, codecs, metrics, tracing và transport.

## 4. Cấu hình Boot khác cấu hình đối tác

### 4.1. Thuộc tính Boot 3.5

```properties
# Defaults cho synchronous HTTP clients:
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s
spring.http.client.redirects=dont-follow

# Defaults cho reactive HTTP connector, nếu dùng WebClient:
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

Đây là tên property **Spring Boot 3.5**. Các phiên bản Boot mới có nhóm `spring.http.clients.*`; không copy tài liệu major khác rồi kết luận config không hiệu lực.

`connect-timeout` hạn chế thời gian thiết lập kết nối; `read-timeout` giới hạn đọc/đợi response theo underlying HTTP transport. Chúng **không nhất thiết là deadline toàn use case**, đặc biệt với retries, pool wait hoặc nhiều upstream liên tiếp.

### 4.2. Thuộc tính ứng dụng tự định nghĩa

```properties
integrations.catalog.base-url=https://catalog.example.internal
integrations.catalog.api-version=v2
integrations.catalog.cache-ttl=15s
```

Nhóm `integrations.catalog.*` không phải property Boot hiểu tự động. Bạn phải khai báo `@ConfigurationProperties`/`@Value` hoặc custom config code. Chúng mang ý nghĩa hợp đồng dịch vụ; chỉ đặt giá trị vào properties không tự tạo Catalog HTTP client.

**Phân biệt:** địa chỉ/kỹ thuật kết nối có thể do platform cung cấp; nhưng tên endpoint, API version, nội dung auth headers và fallback vẫn do **owner integration** xác nhận. Cache TTL có thể được cấu hình ở adapter nhưng việc giá/stock có được stale không thuộc quyết định của business.

### 4.3. Type-safe và fail-fast

```java
@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(@NotNull URI baseUrl) {
}
```

Đây là snippet. `@NotNull` phát hiện thiếu property khi config binding/validation được bật; kiểu `URI` cho cấu trúc rõ. Nó **không** tự kiểm tra URL đã dùng HTTPS, hostname ở allowlist, DNS có an toàn hay path không chứa thông tin nhạy cảm. Với production cần security validation và egress network policy.

### 4.4. Secrets và environments

Ví dụ môi trường dev:

```properties
integrations.catalog.base-url=${CATALOG_BASE_URL:http://localhost:8080}
```

Ở production nên cấp URL có kiểm soát và service secret qua environment, secret manager hoặc SSL bundle/mTLS; **không commit API key, private key, refresh token vào Git**. Nếu dùng Kubernetes/container, `localhost` chỉ container/pod hiện tại, không tự đại diện dịch vụ catalog khác.

## 5. Hợp đồng HTTP không đồng nghĩa hợp đồng nghiệp vụ

### 5.1. Cùng một status có thể mang nhiều nghĩa

| Upstream HTTP result | Catalog item | Payment transaction | Email provider |
| --- | --- | --- | --- |
| 200 | Item tồn tại | Trạng thái hiện tại | Kết quả theo contract |
| 202 | Xử lý async | Chưa thể khẳng định đã thanh toán | Chỉ nhận vào queue |
| 204 | Không có body | Theo contract | Theo contract |
| 400 | Request adapter sai | Payload payment sai | Email data sai |
| 401/403 | Service auth sai/hết quyền | Token/audience sai | Provider auth sai |
| 404 | Item không có | ID transaction chưa có/không đủ quyền | Message resource không có |
| 409 | Conflict schema/version | Có thể duplicate idempotency key | Conflict gửi thư |
| 422 | Dữ liệu không hợp lệ | Business validation reject | Recipient invalid |
| 429 | Rate limit | Có thể cần chờ | Có thể cần chờ |
| 503 | Catalog unavailable | **Không biết payment có commit chưa** | Có thể đã gửi xong một phần |
| Network timeout | Không chắc có response | **Không chứng minh tiền chưa bị trừ** | Có thể đã gửi thành công |

Boot/client library chỉ biết status và bytes. **Adapter hiểu contract**, application service xử lý quyết định của use case, public API chọn status công khai. Không đặt một global exception handler biến tất cả partner 404 thành “item không tồn tại” vì dịch vụ khác có thể dùng 404 theo cách khác.

### 5.2. Ba nhóm lỗi cần phân loại

- **Transport**: DNS, TLS, connect refused, timeout, proxy connection, pool exhausted; có thể **không có HTTP response**.
- **Protocol/contract**: 404/429/503, content type sai, JSON không giải mã được, thiếu field, API version không tương thích.
- **Domain outcome**: item không tồn tại, hết hàng, hạn mức thanh toán, quy tắc tiền tệ, order conflict.

Không đẩy thẳng `HttpServerErrorException`/`WebClientResponseException` vào domain nếu domain không cần phụ thuộc thư viện HTTP. Không trả nguyên error body của upstream ra client cuối vì có thể chứa token, stacktrace hoặc PII.

### 5.3. Adapter quyết định map 404 theo contract, không theo thói quen

Nếu catalog định nghĩa `GET /items/{id}` trả 404 khi item không tồn tại, adapter có thể cung cấp `Optional.empty()` cho port `find`. Nhưng nếu partner trả 404 cho **route sai/version sai**, đó là sự cố tích hợp cần alert; hợp đồng và contract tests giúp phân biệt. Một response 200 với JSON sai cũng là contract failure, **không phải** một item hợp lệ.

## 6. Ranh giới về timeout, retry và resilience

### 6.1. Timeouts

Boot đưa default kỹ thuật; integration lựa chọn override per-upstream khi SLA khác; application đặt deadline tổng thể theo trải nghiệm client.

```text
Browser deadline 3s
  |
  +-- Catalog GET: connect 500ms, read 800ms
  +-- Pricing rules: 200ms
  +-- Optional promotions: 300ms
  +-- Dự phòng cho retry, network overhead, gateway
```

Đây là **budget minh họa**, không phải số liệu đo của hệ thống nào. Nếu cho mỗi partner timeout 30s trong khi API gateway timeout sau 3s, server có thể giữ tài nguyên vô ích. Cân nhắc connection timeout, read timeout, pool acquire timeout và total deadline riêng.

### 6.2. Retry có an toàn không?

Library có thể retry kỹ thuật, nhưng chỉ integration/business biết:

- GET catalog thường là idempotent nếu upstream tuân thủ.
- POST payment có thể đã thành công trước khi client timeout; retry thiếu idempotency key dễ tạo giao dịch trùng.
- POST email có thể đã gửi, retry gây thư trùng.
- 429 có thể có `Retry-After`; không retry không giới hạn.
- Không retry vô hạn lỗi 400, 401, 403, 404, invalid JSON hoặc contract mismatch.

Nên có max attempts, exponential backoff + jitter, total deadline và giới hạn concurrency. Không chồng retry tại gateway, service mesh, WebClient và business layer mà không tính tổng số requests.

### 6.3. Circuit breaker, bulkhead, fallback

Spring Boot auto-configures client builders, **không tự cấp cho mỗi integration một circuit breaker đúng nghiệp vụ**. Có thể thêm Resilience4j/Spring Cloud CircuitBreaker khi lựa chọn thư viện phù hợp.

- **Circuit breaker:** ngừng gọi upstream tạm thời khi lỗi dày đặc.
- **Bulkhead:** hạn chế số request/threads/connection đang xử lý một partner.
- **Rate limit:** giữ trong quota upstream.
- **Fallback:** chỉ dùng cache/default khi **business chấp nhận stale/missing**. Đừng âm thầm coi `available=true` hoặc giá bằng 0 khi catalog bị 503.

Mỗi chính sách cần owner, metrics và tests; nó không tự phát sinh chỉ vì dùng `RestClient.Builder`.

## 7. Security, observability và trace propagation

### 7.1. Credentials theo service, không global

Token Catalog chỉ được gửi tới Catalog. Không tạo một `RestClientCustomizer` global gắn `Authorization: Bearer ...` vào mọi outbound HTTP client; sẽ làm lộ token sang Shipping/Payment. Với OAuth2, xác định service credentials hay on-behalf-of user, scope và audience đúng.

Một singleton gateway **không được lưu mutable user token vào field** theo request vì concurrent requests có thể ghi đè và rò lẫn. Truyền user context có kiểm soát đến per-request header hoặc dùng integration chính thống có propagation thread-safe.

### 7.2. SSL bundles

Spring Boot 3.5 hỗ trợ `RestClientSsl`/`WebClientSsl` để áp truststore/keystore từ SSL bundle tương ứng.

```java
@Bean
RestClient secureCatalog(
        RestClient.Builder builder, RestClientSsl ssl) {
    return builder
            .baseUrl("https://catalog.example.internal")
            .apply(ssl.fromBundle("catalog"))
            .build();
}
```

**Snippet**, không chạy độc lập: cần import `org.springframework.boot.autoconfigure.web.client.RestClientSsl` và có SSL bundle tên `catalog`. Không dùng trust-all, tắt hostname verification hoặc commit certificate private key để vượt qua lỗi SSL.

### 7.3. Metrics và tracing

Dùng builders Boot-managed giúp bảo toàn integration với Micrometer/Actuator/Observation khi dependencies phù hợp được bật. Nên theo dõi latency p95/p99, status class, timeout, connection pool, retry counts và tên upstream có cardinality thấp. Domain có thể đo outcome như `quote.out_of_stock` hoặc `quote.failed.catalog` riêng với metrics HTTP.

Không log raw request/response chứa PII, access token, session IDs. Dùng correlation/trace IDs xuyên inbound → gateway → upstream, kiểm tra context propagation khi chạy async/reactive; không gắn customer ID thẳng vào metric tag độ phân giải cao.

### 7.4. SSRF

Không nhận arbitrary URL từ browser rồi để RestClient gọi dưới quyền backend. Đặt base URL cố định/allowlisted, kiểm tra scheme/domain/IP/redirects và egress policy. Trong project demo, localhost được dùng **chỉ vì tạo một upstream giả lập**, không đại diện config production.

## 8. Ví dụ kiến trúc trước và sau

### 8.1. Anti-pattern: mọi thứ ở controller/service

```java
// Snippet anti-pattern, không phải chương trình đầy đủ.
@GetMapping("/quote/{id}")
public Object quote(@PathVariable long id) {
    // 1. Tạo HTTP client và quyết định URL ngay trong controller.
    // 2. Gọi partner và parse raw JSON.
    // 3. Catch mọi exception rồi trả 200 hoặc 404 bất kể nguyên nhân.
    // 4. Tính tiền và xử lý hết hàng tại đây.
    // 5. Trả nguyên wire DTO của partner.
    throw new UnsupportedOperationException("Không dùng mẫu này");
}
```

Dấu hiệu nguy hiểm: business code biết endpoint URL và HTTP exception; khó test logic mà không có network; auth/timeout hay bị lặp; partner đổi schema gây ảnh hưởng mọi controller.

### 8.2. Mẫu rõ ranh giới

```java
interface CatalogGateway {
    Optional<CatalogItem> find(long itemId);
}

@Service
class QuoteService {
    private final CatalogGateway gateway;
    // Chỉ tính toán nghiệp vụ từ CatalogItem của domain.
}
```

Đây là **snippet minh họa** (chưa đầy đủ code Java). Một implementation `HttpCatalogGateway` chịu trách nhiệm HTTP. Một fake `CatalogGateway` dùng cho unit tests. Public API controller không biết details của RestClient.

## 9. Các yêu cầu để ví dụ chạy độc lập

Project bên dưới:

- **Spring Boot MVC** dùng `spring-boot-starter-web`, không dùng WebFlux starter.
- **RestClient** dựng từ builder do Boot 3.5 tự cấu hình.
- **CatalogProperties** bind một base URL từ application.properties bằng `@ConfigurationPropertiesScan`.
- **CatalogGateway** port tách domain khỏi HTTP.
- **HttpCatalogGateway** map 404 thành missing, các lỗi client còn lại thành dependency unavailable và validate response body.
- **CatalogApplicationService** kiểm tra quantity, stock, tính tiền an toàn.
- **QuoteController** trả public JSON, `PublicErrorAdvice` map domain errors ra HTTP status.
- **DemoPartnerController** mô phỏng service ngoài để chạy offline trên localhost.
- **JUnit + MockRestServiceServer** test adapter mà không gọi mạng và test domain bằng fake port.

Đây là mã Java 17+ đúng cấu trúc project Maven. Không cần database, Docker, token hoặc kết nối Internet đến một API thứ ba sau khi dependencies đã sẵn sàng.

## 10. Project đầy đủ: Spring Boot 3.5.16 + Java 17 + RestClient

### 10.1. Cấu trúc tệp

```text
client-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/clientboundary/
    │   │   ├── ClientBoundaryApplication.java
    │   │   ├── CatalogProperties.java
    │   │   ├── CatalogClientConfiguration.java
    │   │   ├── CatalogIntegration.java
    │   │   ├── CatalogApplicationService.java
    │   │   └── HttpControllers.java
    │   └── resources/application.properties
    └── test/java/com/example/clientboundary/
        ├── HttpCatalogGatewayTest.java
        └── CatalogApplicationServiceTest.java
```

Các classes trong `CatalogIntegration.java`/`HttpControllers.java` đều package-private; Java cho phép **nhiều top-level types không public trong một tệp**. Các class public còn lại nằm đúng tệp cùng tên.

### 10.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>client-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

Không cần dependency WebFlux cho RestClient đồng bộ. Boot parent quản lý phiên bản Spring, Jackson và JUnit.

### 10.3. Main class

`src/main/java/com/example/clientboundary/ClientBoundaryApplication.java`:

```java
package com.example.clientboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientBoundaryApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` đăng ký properties record ở mục 10.4. Component scan phát hiện controller, service, gateway và config cùng package.

### 10.4. Configuration record

`src/main/java/com/example/clientboundary/CatalogProperties.java`:

```java
package com.example.clientboundary;

import java.net.URI;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(@NotNull URI baseUrl) {
}
```

Đây là **config của ứng dụng**, không phải property mà Boot tự biết domain meaning.

### 10.5. Tạo RestClient bean theo đối tác

`src/main/java/com/example/clientboundary/CatalogClientConfiguration.java`:

```java
package com.example.clientboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogProperties properties) {
        return builder
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
```

Boot builder cung cấp hạ tầng, còn app cung cấp URL. Không đặt logic 404/tính tiền ở bean factory này.

### 10.6. Port, DTO, domain và adapter

`src/main/java/com/example/clientboundary/CatalogIntegration.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

record CatalogWireItem(long id, String name, long priceVnd,
                       boolean available) {
}

record CatalogItem(long id, String name, long priceVnd,
                   boolean available) {
}

interface CatalogGateway {
    Optional<CatalogItem> find(long itemId);
}

class CatalogDependencyException extends RuntimeException {
    CatalogDependencyException(String message) {
        super(message);
    }

    CatalogDependencyException(Throwable cause) {
        super("Catalog upstream failure", cause);
    }
}

class ItemNotFoundException extends RuntimeException {
    ItemNotFoundException(long id) {
        super("Item not found: " + id);
    }
}

class OutOfStockException extends RuntimeException {
    OutOfStockException(long id) {
        super("Item out of stock: " + id);
    }
}

@Component
class HttpCatalogGateway implements CatalogGateway {

    private final RestClient client;

    HttpCatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public Optional<CatalogItem> find(long itemId) {
        try {
            CatalogWireItem dto = client.get()
                    .uri("/partner/items/{id}", itemId)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(CatalogWireItem.class);

            if (dto == null
                    || dto.id() != itemId
                    || dto.name() == null
                    || dto.name().isBlank()
                    || dto.priceVnd() < 0) {
                throw new CatalogDependencyException(
                        "Catalog returned invalid data");
            }

            return Optional.of(new CatalogItem(
                    dto.id(), dto.name(),
                    dto.priceVnd(), dto.available()));
        }
        catch (HttpClientErrorException.NotFound ex) {
            // Theo contract Catalog: 404 => không tồn tại mặt hàng.
            return Optional.empty();
        }
        catch (RestClientException ex) {
            // 5xx, một số 4xx khác, I/O, timeout, decode errors.
            throw new CatalogDependencyException(ex);
        }
    }
}
```

**Đọc theo các ranh giới:**

1. `CatalogGateway` không có RestClient, URL hay Spring HTTP types.
2. `CatalogWireItem` thuộc API đối tác; `CatalogItem` là domain model ổn định.
3. Adapter xác định `GET /partner/items/{id}` và format JSON.
4. 404 trở thành `Optional.empty()` **chỉ vì contract ở ví dụ này**.
5. Lỗi khác thuộc HTTP client chuyển thành `CatalogDependencyException`; domain không nhận Spring exceptions.
6. Response 200 nhưng DTO null, tên rỗng, ID sai hoặc giá âm bị coi là **contract failure**, không trả quote sai.

**Giới hạn của ví dụ:** DTO dùng primitive `long/boolean`; dữ liệu JSON thiếu field có thể deserialize thành giá trị mặc định và cần kiểm tra schema sâu hơn trong hệ thống thật. Cần contract tests/nullable DTO/validation nếu partner gửi dữ liệu không ổn định.

### 10.7. Application service chỉ xử lý nghiệp vụ

`src/main/java/com/example/clientboundary/CatalogApplicationService.java`:

```java
package com.example.clientboundary;

import org.springframework.stereotype.Service;

record Quote(long itemId, String name, int quantity,
             long unitPriceVnd, long totalVnd) {
}

@Service
public class CatalogApplicationService {

    private final CatalogGateway catalog;

    public CatalogApplicationService(CatalogGateway catalog) {
        this.catalog = catalog;
    }

    public Quote quote(long itemId, int quantity) {
        if (itemId <= 0) {
            throw new IllegalArgumentException(
                    "itemId must be positive");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be 1..100");
        }

        CatalogItem item = catalog.find(itemId)
                .orElseThrow(
                        () -> new ItemNotFoundException(itemId));

        if (!item.available()) {
            throw new OutOfStockException(itemId);
        }

        long total;
        try {
            total = Math.multiplyExact(
                    item.priceVnd(), (long) quantity);
        }
        catch (ArithmeticException ex) {
            throw new CatalogDependencyException(
                    "Catalog price exceeds safe range");
        }

        return new Quote(item.id(), item.name(), quantity,
                item.priceVnd(), total);
    }
}
```

Logic quantity, availability và tính tổng thuộc **use case**. Không có `GET`, `RestClient`, `HttpStatus` hoặc partner URL trong class. Số tiền `long` tính theo VND nguyên chỉ để demo; hệ thống thực cần chính sách currency, tax, rounding, phân đơn vị và validation chuyên biệt.

### 10.8. Public API, error mapping và stub partner

`src/main/java/com/example/clientboundary/HttpControllers.java`:

```java
package com.example.clientboundary;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestController
class QuoteController {

    private final CatalogApplicationService service;

    QuoteController(CatalogApplicationService service) {
        this.service = service;
    }

    @GetMapping("/api/quotes/{id}")
    Quote quote(
            @PathVariable long id,
            @RequestParam(defaultValue = "1") int quantity) {
        return service.quote(id, quantity);
    }
}

// Chỉ làm partner stub cho demo local. Không deploy dạng này.
@RestController
class DemoPartnerController {

    @GetMapping("/partner/items/{id}")
    CatalogWireItem item(@PathVariable long id) {
        if (id == 1) {
            return new CatalogWireItem(
                    1, "Bút bi", 12_000L, true);
        }
        if (id == 2) {
            return new CatalogWireItem(
                    2, "Sổ tay", 35_000L, false);
        }
        if (id == 503) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "Demo outage");
        }
        throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "No such item");
    }
}

@RestControllerAdvice
class PublicErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(
            ItemNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "ITEM_NOT_FOUND",
                       "message", "Không tìm thấy mặt hàng."));
    }

    @ExceptionHandler(OutOfStockException.class)
    ResponseEntity<Map<String, String>> outOfStock(
            OutOfStockException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of("code", "OUT_OF_STOCK",
                       "message", "Mặt hàng đã hết."));
    }

    @ExceptionHandler(CatalogDependencyException.class)
    ResponseEntity<Map<String, String>> dependency(
            CatalogDependencyException ex) {
        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(
                Map.of("code", "CATALOG_UNAVAILABLE",
                       "message", "Tạm thời không lấy được hàng hóa."));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalidInput(
            IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_QUOTE_REQUEST",
                       "message", "Thông số báo giá không hợp lệ."));
    }
}
```

Các top-level classes trong `HttpControllers.java` đều package-private nên Java cho phép nằm cùng file. `QuoteController` gọi use case; `PublicErrorAdvice` quyết định public status và message. Partner stub chỉ nhằm cho example chạy offline.

### 10.9. `application.properties` hoàn chỉnh

```properties
server.port=8080
spring.application.name=client-boundary-demo

spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s
spring.http.client.redirects=dont-follow

integrations.catalog.base-url=${CATALOG_BASE_URL:http://localhost:8080}
```

Chỉ config Boot HTTP client defaults ở các key `spring.http.client.*`. Key `integrations.catalog.base-url` là custom application config; record ở mục 10.4 mới khiến nó được bind.

### 10.10. Build và chạy

Cần JDK 17+, Maven, cổng 8080 rảnh.

```bash
mvn clean package
java -jar target/client-boundary-demo-1.0.0.jar
```

Từ terminal khác:

```bash
curl -s "http://localhost:8080/api/quotes/1?quantity=3"
```

Dữ liệu JSON kỳ vọng:

```json
{"itemId":1,"name":"Bút bi","quantity":3,"unitPriceVnd":12000,"totalVnd":36000}
```

Thứ tự key có thể khác; giá trị đúng do partner stub trả đơn giá 12.000 và quantity=3, tổng 36.000.

Kiểm tra hết hàng:

```bash
curl -i "http://localhost:8080/api/quotes/2?quantity=1"
```

Kỳ vọng **HTTP 409 Conflict**, JSON có `code=OUT_OF_STOCK`.

Kiểm tra item không tồn tại:

```bash
curl -i "http://localhost:8080/api/quotes/9?quantity=1"
```

Kỳ vọng **HTTP 404 Not Found**, JSON có `code=ITEM_NOT_FOUND`. Upstream 404 → adapter empty → use case NotFound → API 404; đây là sự phân chia trách nhiệm cụ thể.

Kiểm tra partner outage:

```bash
curl -i "http://localhost:8080/api/quotes/503?quantity=1"
```

Kỳ vọng **HTTP 503 Service Unavailable**, JSON có `code=CATALOG_UNAVAILABLE`. Upstream 503 không được trả nguyên raw body ra frontend.

Kiểm tra input lỗi:

```bash
curl -i "http://localhost:8080/api/quotes/1?quantity=0"
```

Kỳ vọng **HTTP 400 Bad Request**, JSON có `code=INVALID_QUOTE_REQUEST`. Lỗi quantity được chặn trước outbound call.

Xem wire DTO upstream:

```bash
curl -s http://localhost:8080/partner/items/1
```

Dữ liệu JSON:

```json
{"id":1,"name":"Bút bi","priceVnd":12000,"available":true}
```

So với `Quote`, public API không giữ nguyên field `priceVnd` của partner; contract của app dùng `unitPriceVnd` và `totalVnd`.

**Chú ý khi triển khai:** cấu hình loopback tự gọi app chỉ phù hợp demo. Với nhiều nodes hoặc servlet thread pool quá nhỏ, tự gọi lại cùng process có thể gây cạn threads. Trong production phải gọi service ngoài qua DNS/HTTPS và quản lý connection pool đúng cách.

## 11. Kiểm thử adapter bằng mock HTTP, nghiệp vụ bằng fake port

### 11.1. Adapter test: không gọi mạng

Tệp `src/test/java/com/example/clientboundary/HttpCatalogGatewayTest.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class HttpCatalogGatewayTest {

    private static final String BASE =
            "http://catalog.example.test";

    @Test
    void mapsDtoToDomain() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/1"))
                .andRespond(withSuccess(
                        "{\"id\":1,\"name\":\"Pen\","
                        + "\"priceVnd\":12000,\"available\":true}",
                        MediaType.APPLICATION_JSON));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertEquals(Optional.of(
                new CatalogItem(1, "Pen", 12000, true)),
                gateway.find(1));
        server.verify();
    }

    @Test
    void maps404ToMissing() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/9"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertTrue(gateway.find(9).isEmpty());
        server.verify();
    }

    @Test
    void maps503ToDependencyFailure() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/503"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertThrows(CatalogDependencyException.class,
                () -> gateway.find(503));
        server.verify();
    }

    @Test
    void rejectsInvalidPayload() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        server.expect(requestTo(BASE + "/partner/items/1"))
                .andRespond(withSuccess(
                        "{\"id\":2,\"name\":\"wrong-id\","
                        + "\"priceVnd\":12000,\"available\":true}",
                        MediaType.APPLICATION_JSON));

        HttpCatalogGateway gateway =
                new HttpCatalogGateway(builder.build());

        assertThrows(CatalogDependencyException.class,
                () -> gateway.find(1));
        server.verify();
    }
}
```

`MockRestServiceServer.bindTo(RestClient.Builder)` gắn mock request factory cho builder đó; request kỳ vọng không đi ra mạng thật. Các tests kiểm tra **partner HTTP contract và adapter mapping**, không kiểm tra Boot auto-config/TLS/connection pooling. Muốn kiểm tra wiring, cần integration test riêng.

### 11.2. Business test: không cần HTTP library

Tệp `src/test/java/com/example/clientboundary/CatalogApplicationServiceTest.java`:

```java
package com.example.clientboundary;

import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogApplicationServiceTest {

    private final CatalogGateway fake = id -> {
        if (id == 1) {
            return Optional.of(
                    new CatalogItem(1, "Pen", 12000, true));
        }
        if (id == 2) {
            return Optional.of(
                    new CatalogItem(2, "Notebook", 35000, false));
        }
        return Optional.empty();
    };

    private final CatalogApplicationService service =
            new CatalogApplicationService(fake);

    @Test
    void calculatesQuote() {
        assertEquals(
                new Quote(1, "Pen", 3, 12000, 36000),
                service.quote(1, 3));
    }

    @Test
    void rejectsUnavailableItem() {
        assertThrows(OutOfStockException.class,
                () -> service.quote(2, 1));
    }

    @Test
    void rejectsMissingItem() {
        assertThrows(ItemNotFoundException.class,
                () -> service.quote(9, 1));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(1, 0));
    }
}
```

Dù adapter chuyển từ RestClient sang WebClient/gRPC/SDK, những tests business này không cần sửa nếu port semantics giữ nguyên.

Chạy:

```bash
mvn test
```

Các tests dùng JUnit Jupiter từ `spring-boot-starter-test`; không cần chạy application server. Khi muốn kiểm thử controller/Boot wiring ở random port, phải inject dynamic base URL tương ứng hoặc dùng upstream mock server riêng; **random port không tự làm custom `integrations.catalog.base-url` đổi theo**.

### 11.3. Ma trận test nên có

| Lớp | Kiểm tra | Gợi ý |
| --- | --- | --- |
| Domain/application | quantity, stock, total, overflow | JUnit fake `CatalogGateway` |
| Adapter | URI, headers, 200/404/429/503, invalid JSON | `MockRestServiceServer`/WireMock |
| Bean/config | Properties bind, TLS/SSL bundles, timeouts | `ApplicationContextRunner` hoặc `@SpringBootTest` |
| Network/integration | DNS, proxy, certificate, source IP, retry | Staging partner/test container |
| Contract | Schema, version, enum values, date/currency | Consumer/provider contract tests |
| Security | Host allowlist, token audience, logging secrets | Static/security/egress tests |
| Resilience | Circuit breaker, backoff, timeouts, load | Fault injection |
| Performance | Pool saturation, p95, retry storm | Controlled load test |

## 12. Mở rộng sang nhiều đối tác

### 12.1. Mỗi upstream một bean có tên rõ

```java
@Bean("catalogRestClient")
RestClient catalog(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.internal")
            .build();
}

@Bean("shippingRestClient")
RestClient shipping(RestClient.Builder builder) {
    return builder.baseUrl("https://shipping.example.internal")
            .build();
}
```

Đây là **snippet thay thế**, không thêm cùng lúc với bean `catalogRestClient` ở project demo. Khi inject dùng `@Qualifier` hoặc wrapper typed clients; nếu có nhiều beans cùng `RestClient` mà không chỉ định rõ, DI có thể mơ hồ.

### 12.2. Global customizer chỉ cho điều thật sự chung

```java
@Bean
RestClientCustomizer technicalCustomizer() {
    return builder -> builder
            .defaultHeader("X-App-Client", "my-spring-app");
}
```

Snippet cần import `org.springframework.boot.web.client.RestClientCustomizer`; header chỉ là ví dụ nếu partner cho phép. Không biến global customizer thành nơi chứa Catalog API key, URL hoặc quy tắc retry/payment. Customizations của Boot có phạm vi rộng; một thay đổi có thể ảnh hưởng tất cả upstream cùng loại.

### 12.3. @HttpExchange là HTTP interface, không tự là business port

```java
@HttpExchange("/partner/items")
interface CatalogHttpApi {
    @GetExchange("/{id}")
    CatalogWireItem get(@PathVariable long id);
}
```

Đây là **snippet** cần adapter `RestClientAdapter`/`WebClientAdapter` và `HttpServiceProxyFactory`, không chạy độc lập. Interface này vẫn nói bằng ngôn ngữ HTTP của partner, còn `CatalogGateway` nói bằng ngôn ngữ của application. Dù dùng generated proxy, bạn vẫn cần mapper DTO, kiểm tra contract, lỗi nghiệp vụ và tests.

### 12.4. Khi partner đổi API version

Nếu `/partner/items/{id}` chuyển thành `/v2/products/{id}` và đổi JSON, cập nhật adapter/HTTP tests, **không sửa business service chỉ để đổi URL**. Nếu partner đổi luôn semantics giá/tồn kho, domain có thể cần thay — đây là thay đổi nghiệp vụ hợp lệ, không phải thất bại kiến trúc.

## 13. WebFlux: giữ ranh giới nhưng thay execution model

Ứng dụng reactive có thể định nghĩa port:

```java
interface ReactiveCatalogGateway {
    Mono<CatalogItem> find(long itemId);
}
```

Trong thiết kế này phải định nghĩa rõ **`Mono.empty()` nghĩa là not found hay không có dữ liệu**, và `Mono.error(...)` nghĩa là dependency failure. Đừng tạo một port synchronous nhưng trả lỗi reactive bất chợt hoặc gọi `block()` trên event loop.

Ví dụ WebClient adapter **snippet minh họa**:

```java
Mono<CatalogItem> find(long id) {
    return webClient.get()
            .uri("/partner/items/{id}", id)
            .retrieve()
            .bodyToMono(CatalogWireItem.class)
            .map(dto -> new CatalogItem(
                    dto.id(), dto.name(),
                    dto.priceVnd(), dto.available()))
            .onErrorMap(WebClientRequestException.class,
                    CatalogDependencyException::new);
}
```

Đây chưa phải adapter đầy đủ: cần map `404` theo hợp đồng đã thống nhất, validate DTO, xử lý 5xx và các loại decode errors. Nó làm rõ rằng **WebClient không tự đóng vai business adapter** chỉ nhờ dùng Mono.

Trong WebFlux:

- Không gọi RestTemplate/RestClient blocking trực tiếp trong event loop.
- Không gọi `WebClient.block()` tại reactive request thread.
- Không tự `subscribe()` trong service rồi trả response trước khi xử lý xong.
- Nếu bắt buộc gọi thư viện blocking, cô lập bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` có giới hạn.
- Thiết kế cancellation, context propagation, connection pool và backpressure rõ ràng.

Một MVC service vẫn có thể dùng WebClient outbound, nhưng đó không phải phép biến toàn bộ JPA/JDBC business code thành non-blocking.

## 14. Checklist phát hiện ranh giới sai và cách khắc phục

| Dấu hiệu | Vấn đề | Bước sửa |
| --- | --- | --- |
| Controller inject RestClient và tính tiền trong cùng method | Trộn HTTP adapter với domain | Tách `CatalogGateway` + use case |
| `NoSuchBeanDefinitionException: RestTemplate` | Tưởng Boot tự tạo RestTemplate bean | Tạo bean qua `RestTemplateBuilder` |
| Metrics HTTP client mất sau refactor | Dựng `RestClient.create()` ngoài Boot customizations | Inject Boot-managed builder |
| Client Catalog gửi bearer token của Shipping | Auth header đặt global | Đưa token về per-partner bean/request |
| All 404 map thành empty | Không hiểu contract | Mapping riêng từng adapter |
| Upstream 503 được coi là item không tồn tại | Lỗi dependency bị nuốt | Có `CatalogDependencyException` riêng |
| Response 200 nhưng DTO thiếu price | Chưa validate schema | Contract validation/test |
| 429 retry vô hạn | Retry policy không có budget | Limited backoff, Retry-After, circuit breaker |
| Payment POST retry tạo duplicate | HTTP policy không biết idempotency | Idempotency key/business policy |
| Bean của partner A dùng base URL partner B | Builder mutable/shared | Separate injection/clone, qualifiers |
| WebFlux request bị treo | Blocking HTTP/database trên event loop | WebClient hoặc boundedElastic chuyển tiếp |
| Global timeout tăng lên 30s vì một partner | Lẫn default với SLA riêng | Per-service override |
| Domain test cần network thật | Domain phụ thuộc client HTTP | Fake port, adapter test riêng |
| Public API trả raw partner error | Rò thông tin/contract leak | Domain exception + controller advice |
| 403 upstream được trả thành 403 cho end user | Lẫn service credentials với user rights | Phân tích auth upstream và public semantics |
| Logs chứa bearer token | Logging interceptor không redact | Xóa/che headers nhạy cảm |
| Config có base URL localhost ở production | Environment override sai | Require real URL/allowlist, fail startup |
| Request tới 169.254... theo input user | SSRF | Allowlist, egress, redirect/DNS policy |
| Connection pool hết | Không kiểm soát concurrency/đóng response | Reuse clients, pool metrics, bulkhead |
| Stale price vẫn được dùng lúc checkout | Fallback kỹ thuật trái business | Rule freshness tại use case |

## 15. Quy trình điều tra sự cố theo tầng

Giả sử `GET /api/quotes/1` trả 503:

1. **Controller:** status/code public là gì? Request có đúng path/method không?
2. **Application:** input đã validate chưa? CatalogGateway có được gọi không?
3. **Adapter:** URI gửi ra partner có đúng? HTTP 404/503/JSON được map thế nào?
4. **Client bean:** `catalogRestClient` lấy đúng base URL và Boot builder không? Có global header lạ không?
5. **Transport:** DNS, TLS, proxy, connection pool, connect/read timeouts có phù hợp không?
6. **Partner contract:** response schema, status, API version, rate limit có thay đổi không?
7. **Gateway/mesh:** có retry/timeout/redirect rewrite ở hạ tầng không?
8. **Observability:** trace IDs xuyên các hops có đầy đủ? Có log secret vô ý không?
9. **Tests:** thêm một adapter regression test cho đúng lỗi; nếu ảnh hưởng business policy, thêm domain unit test.
10. **Deploy:** kiểm tra config/profiles/secrets ở môi trường thật, không dùng kết quả curl từ laptop làm bằng chứng rằng pod kết nối được.

Tránh “chữa” bằng cách tắt TLS verification, tăng global timeout vô hạn hoặc map mọi lỗi thành HTTP 200; những cách đó che sai sót và gây sự cố lớn hơn.

## 16. Bài tập và câu hỏi tự đánh giá

1. **Boot có tự tạo RestClient riêng cho Catalog không?** Không. Boot chuẩn bị builder; ứng dụng build client theo partner.
2. **Boot có sẵn RestTemplate bean bất kỳ cho injection không?** Thông thường không; có `RestTemplateBuilder`.
3. **404 của Catalog có luôn là lỗi routing?** Không. Trong hợp đồng demo, đó là item không tồn tại; adapter dịch đúng.
4. **Vì sao domain không nên biết `ResponseEntity` của partner?** Nó buộc business model phụ thuộc transport và contract ngoài.
5. **Khi partner 503, có nên trả price=0 không?** Không nếu business chưa chấp nhận stale/default; dễ làm sai giao dịch.
6. **Có được đặt Catalog API key trong global customizer không?** Không, vì có thể rò sang client khác.
7. **Timeout global 3 giây có đủ cho mọi upstream không?** Không chắc. Cần SLA/deadline riêng và đo đạc.
8. **Retry POST thanh toán có an toàn khi timeout không?** Chỉ với idempotency contract và chính sách đúng.
9. **`@ConfigurationProperties` có tự gửi request HTTP không?** Không, nó chỉ bind config.
10. **Vì sao dùng fake `CatalogGateway` trong domain unit test?** Không cần Spring, HTTP hay server.
11. **WebClient có làm toàn bộ MVC app thành reactive không?** Không.
12. **Khi đổi API JSON partner, sửa lớp nào đầu tiên?** Wire DTO + integration adapter + contract tests.
13. **Một `@HttpExchange` interface thay business gateway không?** Không; nó mô tả HTTP contract.
14. **Tại sao nên tái sử dụng client bean?** Giữ pool, TLS, customizers, observability và tránh overhead.
15. **Backend gọi partner có bị browser CORS policy chặn không?** Không; đó là server-to-server call.

### Bài tập áp dụng

**A. Partner đổi `priceVnd` sang `amount`:** thay wire DTO/mapper, thêm contract test, giữ `CatalogApplicationService.quote` nếu semantics giá không đổi.

**B. Thêm Shipping:** tạo `ShippingProperties`, `shippingRestClient`, `HttpShippingGateway` với own auth/deadline; không dùng Catalog token.

**C. Đối tác trả 429:** map thành lỗi rate-limit rõ, cân nhắc `Retry-After`/budget, không retry mọi request tự động.

**D. Thêm mTLS:** áp SSL bundle vào **catalogRestClient** qua `RestClientSsl`, không thay TLS của mọi client.

**E. Chuyển sang reactive:** giữ ý nghĩa domain, định nghĩa reactive port, map errors/empty rõ; không gọi blocking HTTP trên event loop.

**F. Catalog trả 200 với ID khác request:** adapter fail contract validation; không tính quote theo item khác.

## 17. Checklist thiết kế và vận hành

- [ ] Xác định kiểu ứng dụng: MVC synchronous hay WebFlux reactive.
- [ ] Dùng Boot-configured builders để giữ converters, transport và observability.
- [ ] Mỗi upstream có typed config, base URL và bean client riêng.
- [ ] Không đưa partner secret, URL và business error mapping vào global customizer.
- [ ] Wire DTO khác domain/public DTO; validate hợp đồng upstream.
- [ ] Application dùng gateway port, không import HTTP client exceptions.
- [ ] Controller chỉ xử lý public HTTP contract và domain outcomes.
- [ ] Có per-service SLA, connection/read/total timeout, pooling và concurrency limits.
- [ ] Retry có idempotency, max attempts, backoff, budget và metrics.
- [ ] Fallback/circuit breaker chỉ khi business cho phép.
- [ ] TLS đúng CA/hostname; API keys/tokens trong secret manager.
- [ ] Không cho user input tùy ý quyết định outbound URL/SSRF.
- [ ] Unit tests domain, adapter contract tests, integration wiring/SSL tests.
- [ ] Quan sát status/latency/pool/retry và phân biệt errors upstream/domain.
- [ ] Khi đổi Boot major, xác minh property names, builder/customizer semantics.
- [ ] Mọi team biết ai sở hữu transport defaults, partner contracts và business rules.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): Boot builders, HTTP factories, customizers, WebClient và RestTemplate.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.client.*` và `spring.http.reactiveclient.*`.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient, HTTP interfaces, status semantics.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): Publisher, status handling, non-blocking operations.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): `@ConfigurationProperties` và binding.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer/Tracing.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test infrastructure.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): mock HTTP contract tests.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): service credentials.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods/status/headers.

**Ghi nhớ:** **Boot biết cách kết nối HTTP an toàn và nhất quán; adapter hiểu dịch vụ bên ngoài; application/domain hiểu ý nghĩa kết quả; controller hiểu public API.** Khi các trách nhiệm này không trộn lẫn, có thể thay transport, nâng Boot, đổi partner contract và kiểm thử nghiệp vụ mà không đánh đổi tính đúng đắn.