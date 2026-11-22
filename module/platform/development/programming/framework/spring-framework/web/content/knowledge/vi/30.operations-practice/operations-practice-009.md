# Thực hành gọi dịch vụ: HTTP client, timeout và xử lý lỗi

## 1. Mục tiêu: gọi dịch vụ bên ngoài một cách có kiểm soát

Trong ứng dụng Spring Framework, một HTTP endpoint thường phải gọi hệ thống khác: inventory, pricing, payment, identity, shipping hoặc API của đối tác. Việc gọi được URL chỉ là bước đầu. Ở production, kết nối có thể thất bại khi DNS/TCP/TLS, upstream trả 4xx/5xx, server trả dữ liệu không hợp lệ, mạng chậm bất thường hoặc client đã hủy request. Nếu mọi tình huống được bắt bằng `catch (Exception)` rồi trả `null`, người gọi không thể phân biệt hết hàng, upstream tạm thời hỏng hay lỗi lập trình.

Mục tiêu bài thực hành:

1. Biết chọn **`RestClient`**, **`WebClient`**, khi nào gặp `RestTemplate` và HTTP Service Client.
2. Đặt **connect timeout, read/response timeout và end-to-end deadline** theo SLA thay vì tùy tiện.
3. Phân loại **HTTP status error**, **transport/network failure**, **decode error**, **timeout** và **business response**.
4. Quyết định khi nào nên retry và khi nào retry có thể gây trùng nghiệp vụ.
5. Thiết kế một client adapter gọi dịch vụ, mapping lỗi sang hợp đồng của service/API, giữ bí mật và observability.
6. Chạy chương trình Java 17+ tự mở HTTP server cục bộ, gọi bằng Spring `RestClient` và quan sát ba tình huống **200, 404, response chậm gây read timeout**.

**Phiên bản tham chiếu:** Java 17+, Spring Framework 6.1.x, Spring Boot 3.3.x. `RestClient` có từ Spring Framework 6.1. Ví dụ hoàn chỉnh dùng Java SE + module `spring-web` và một local JDK HTTP server; không cần chạy Docker, database hoặc API public.

## 2. Chọn API HTTP client phù hợp với execution model

| Client | Mô hình và API | Dùng khi | Lưu ý |
| --- | --- | --- | --- |
| **`RestClient`** | Fluent, đồng bộ; `get().uri(...).retrieve().body(...)` | Service Spring MVC, batch đồng bộ, ứng dụng imperative | Thực thi I/O khi gọi method, giữ request thread chờ response |
| **`WebClient`** | Reactive; `Mono<T>`/`Flux<T>` | Spring WebFlux, streaming, async composition, số lượng I/O concurrent lớn | Publisher thường chạy khi subscribe; tránh `block()` trên event-loop |
| **`RestTemplate`** | API đồng bộ lâu đời | Dự án đang dùng, tương thích với integration cũ | Spring hiện khuyến khích `RestClient` cho API đồng bộ mới |
| **HTTP Service Client** | Java interface `@GetExchange`/`@PostExchange` + proxy | Muốn mô tả API đối tác bằng contract interface | Bên dưới vẫn cần chọn `RestClientAdapter`/`WebClientAdapter` và cấu hình transport/timeouts |

Chọn theo môi trường thật. Một Spring MVC controller có vài outbound REST calls thường không cần đổi toàn bộ chương trình sang reactive chỉ vì muốn dùng HTTP. Ngược lại, trong WebFlux, chặn luồng Netty event-loop bằng `RestClient` hoặc `WebClient.block()` có thể khiến throughput suy giảm và bị Reactor từ chối.

**Một HTTP client không phải một TCP connection.** `RestClient`/`WebClient` có thể tái sử dụng transport, connection pool và thread resources tùy thư viện nền. Nên khai báo/reuse client như một bean; không xây client, TLS context hoặc pool mới cho từng incoming request.

### Ví dụ hai kiểu gọi

```java
// Fragment synchronous, bên trong method có sẵn RestClient inventoryClient:
String body = inventoryClient.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .body(String.class);
```

```java
// Fragment reactive, bên trong method có sẵn WebClient inventoryWebClient:
Mono<String> bodyPublisher = inventoryWebClient.get()
        .uri("/items/{id}", 42)
        .retrieve()
        .bodyToMono(String.class);
```

Với `RestClient`, thread gọi chờ cho đến khi response/exception. Với `WebClient`, `Mono` mô tả pipeline và request được thực hiện theo subscription. Cả hai mặc định biến nhiều status **4xx/5xx** thành exception khi dùng `retrieve()`, thay vì tự trả `null`. Chúng không bắt buộc dùng cùng loại connector bên dưới.

## 3. Hiểu toàn bộ hành trình một lời gọi HTTP

Một lần gọi không chỉ là khoảng thời gian server xử lý business logic:

```text
Incoming request
      │
      ▼
Application service / outbound adapter
      │
      ├─ URI resolve + DNS
      ├─ Chờ lấy connection từ pool (nếu dùng pool)
      ├─ TCP connect
      ├─ TLS handshake (HTTPS)
      ├─ Gửi request headers và body
      ├─ Chờ response headers
      ├─ Đọc response body (có thể stream lâu)
      └─ Decode JSON / mapping DTO
      │
      ▼
Thành công hoặc một lớp lỗi cụ thể
```

Các lớp lỗi:

| Giai đoạn | Tình huống lỗi | Dấu hiệu |
| --- | --- | --- |
| Tạo URI/input | URL sai, biến URI thiếu, ký tự sai | Có thể lỗi ngay tại phía client |
| DNS / TCP | Không resolve được host, refused, network unreachable | Thường I/O/transport exception, **không có HTTP status** |
| TLS | Chứng chỉ không tin cậy, hostname mismatch, handshake error | SSL/transport exception; không nên tắt xác minh TLS |
| Pool | Hết kết nối, pending acquire timeout | Phụ thuộc engine/pool, chưa nhận response |
| Đọc response | Read/response timeout, connection reset, EOF | Transport exception |
| Server đã trả response | 400, 401, 403, 404, 409, 429, 500, 503… | **HTTP status có thật**, body/headers có thể hữu ích |
| Decode | JSON sai/field sai, content type không tương thích, body quá lớn | Codec/message conversion exception |
| Nghiệp vụ | HTTP 200 nhưng JSON biểu diễn out-of-stock, denied, invalid state | Response hợp lệ về transport, cần hiểu semantics domain |

**Không đánh đồng HTTP 503 với connect timeout:** 503 nghĩa là đã nhận được một response từ một HTTP server/proxy; connect timeout xảy ra trước khi có response hợp lệ. Hai loại cần log và retry khác nhau.

**Không đánh đồng HTTP 404 upstream với HTTP 404 public:** phía inventory trả 404 nghĩa là SKU không có trên inventory; API public có thể trả 404, 422 hoặc một business outcome khác tùy use case. Không tự động “bê nguyên” mọi status của dịch vụ phụ ra ngoài.

## 4. Timeout: định nghĩa từng bộ đếm thời gian

Timeout phải được thiết kế theo ngân sách phục vụ request, không theo một con số “5 giây cho tất cả”.

| Loại timeout | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| **Connect timeout** | Thời gian tạo TCP connection tới endpoint | 300 ms |
| **Pool acquire timeout** | Thời gian chờ được cấp connection trong pool | 200 ms |
| **Read timeout** | Thời gian chờ thao tác đọc socket, thường là thời gian chờ dữ liệu kế tiếp | 900 ms |
| **Response timeout** | Timeout ở tầng HTTP engine khi chờ/nhận response theo semantics engine | 1 s |
| **Write timeout** | Thời gian ghi request body/socket, nếu engine hỗ trợ | 1 s |
| **End-to-end deadline** | Tổng ngân sách ca sử dụng, gồm gọi mạng và xử lý/tries | 2 s |

**Read timeout không đồng nghĩa total request timeout.** Chẳng hạn một stream gửi từng byte trong khoảng thời gian nhỏ hơn read timeout có thể kéo dài nhiều phút. Tương tự, chỉ cấu hình connect timeout không chặn server nhận connection nhưng treo khi gửi body.

Các bộ đếm còn phụ thuộc HTTP engine và version. DNS lookup không phải lúc nào cũng chịu connect timeout; TLS handshake, proxy và pending acquire có thể có bộ giới hạn khác. Muốn có **hạn tổng**, đặt deadline ở application/async pipeline hoặc cơ chế client hỗ trợ toàn bộ lifecycle, rồi truyền **remaining budget** tới các cuộc gọi phía dưới khi có thể.

### Ví dụ ngân sách và số lần thử

Một public endpoint có SLO 2 giây. Giả sử controller/serialization cần khoảng 250 ms, phần khác cần 150 ms, còn ~1,6 giây cho inventory call. Nếu mỗi outbound try cho phép response timeout 1,5 giây và tự retry **hai lần nữa**, bạn có nguy cơ giữ request lâu hơn ngân sách nhiều lần.

Chiến lược đúng hơn:

- Xác định **deadline tổng** cho call chain từ incoming request.
- Cấu hình connect và read/response timeout của transport để resource không treo.
- Giới hạn số lần retry và tổng thời gian retries; dùng remaining-time budget.
- Không retry khi deadline đã hết hoặc client hủy request.
- Đặt fallback chỉ khi business semantics cho phép (ví dụ cached informational data, không dùng fallback “thành công” giả cho tiền hoặc inventory reservation).

**Không có một bộ timeout duy nhất áp dụng được cho tất cả upstream.** Payment service có yêu cầu khác image metadata service; đặt cấu hình theo nhóm dependency, endpoint, kích thước payload và khả năng chống tải.

## 5. RestClient: cấu hình request factory và timeout

Trong Spring Framework 6.1, `RestClient` tạo từ `RestClient.builder()`, `RestClient.create()` hoặc `RestClient.Builder` do Spring Boot cung cấp. Timeout cụ thể nằm ở **ClientHttpRequestFactory** (thư viện HTTP nền), không có một phương thức `RestClient.timeout(...)` chung cho mọi engine.

Ví dụ dễ học: dùng `SimpleClientHttpRequestFactory` dựa trên JDK `HttpURLConnection`:

```java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();
requestFactory.setConnectTimeout(Duration.ofMillis(300));
requestFactory.setReadTimeout(Duration.ofMillis(900));

RestClient client = RestClient.builder()
        .baseUrl("https://inventory.example.org")
        .requestFactory(requestFactory)
        .defaultHeader("X-Client-Name", "catalog-api")
        .build();
```

Đây là **fragment cấu hình**, URL ví dụ không dùng để chạy thật. `setConnectTimeout` và `setReadTimeout` đều có overload `Duration` trong Spring 6.1. `0` đối với các URLConnection timeout có thể biểu diễn timeout vô hạn; không đặt 0 vì nghĩ rằng đó là “không cần chờ”.

Tùy stack, client có thể dùng Apache HttpComponents, JDK `HttpClient`, Jetty hoặc Reactor Netty (WebClient), với các API configure timeout, pool, TLS khác nhau. **Không copy nguyên cấu hình của `SimpleClientHttpRequestFactory` sang mọi engine.** Kiểm tra dependency tree và native HTTP engine thực sự được chọn.

### Dùng Spring Boot-managed builder

Nếu là Spring Boot application, inject builder thay vì tùy tiện tạo client khác mà bỏ qua common customization:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class OutboundHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(300);
        factory.setReadTimeout(900);

        return builder
                .baseUrl("https://inventory.example.org")
                .requestFactory(factory)
                .build();
    }
}
```

Đây là Spring configuration fragment. Lưu ý cấu hình request factory tường minh có thể thay đổi transport do Boot chọn, ảnh hưởng pooling, metrics hoặc TLS mặc định; verify sau khi wiring với Boot customizers. Không dùng một `RestClient.Builder` mutable như singleton để rồi thêm header riêng của nhiều upstream vào cùng builder không kiểm soát; Spring Boot thường cung cấp builder scope prototype.

Đặt base URL ở externalized configuration theo môi trường (ví dụ `@ConfigurationProperties` với validation). Tên host, credentials, connect/read timeouts và pool size không nên là các hằng số cố định bị sao chép khắp service.

## 6. RestClient: phân biệt 4xx/5xx và lỗi I/O

### 6.1 `retrieve()` và status lỗi

Với `RestClient`, `retrieve().body(Foo.class)` mặc định xử lý các HTTP status 4xx/5xx thành `RestClientResponseException` và các subclass cụ thể như `HttpClientErrorException`/`HttpServerErrorException`. Vì đã có response, exception mang **status**, có thể có **headers và response body**. Các lỗi mạng dùng ngoại lệ khác, phổ biến `ResourceAccessException`.

```java
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

String result;

try {
    result = inventoryRestClient.get()
            .uri("/items/{id}", "SKU-42")
            .retrieve()
            .body(String.class);
} catch (RestClientResponseException responseError) {
    int code = responseError.getStatusCode().value();
    // HTTP server/proxy thực sự trả status code này.
    // Mapping 404/429/503 phải theo semantics của dependency.
    throw responseError;
} catch (ResourceAccessException transportError) {
    // DNS, TCP, TLS, read timeout hoặc lỗi I/O khác.
    throw transportError;
}
```

**Fragment:** giả định `inventoryRestClient` có sẵn. Những `catch` trên chỉ minh họa taxonomy; production cần chuyển lỗi thành domain/adapter exceptions và logging an toàn thay vì cứ ném cùng exception qua mọi tầng.

Không bắt `Exception` rồi âm thầm trả `Optional.empty()`: nó biến network outage hoặc lỗi JSON thành “không có item”. `Optional.empty` chỉ phù hợp nếu API contract quy định rõ một HTTP 404 thật sự nghĩa là kết quả không tồn tại.

### 6.2 Xử lý có chủ đích với onStatus

Nếu một dịch vụ dùng 404 như giá trị bình thường nhưng 5xx phải báo unavailable, có thể:

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.client.RestClient;

// Fragment bên trong một method đã có RestClient client.
String body = client.get()
        .uri("/inventory/{sku}", "ABC-1")
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Inventory upstream failed: "
                            + response.getStatusCode());
                })
        .body(String.class);
```

`onStatus` trong ví dụ chỉ thay đổi handling cho 5xx. Với 404, default `retrieve()` vẫn throw; nếu muốn map 404 thành empty hoặc typed “not found”, cần thêm status handling và chọn API phù hợp. Đừng dùng `onStatus(s -> true, ...)` một cách tùy tiện rồi nuốt response body, bởi có thể làm mất xử lý status bình thường.

Một số trường hợp cần đọc cả status, headers và body mà không muốn cơ chế mặc định của `retrieve()`: cân nhắc `exchange((request, response) -> ...)` của RestClient. Với `exchange()`, **status handlers không được áp dụng tự động**; caller phải tự kiểm tra status và tiêu thụ/đóng response đúng hợp đồng. Cẩn thận response stream không bị đọc hai lần hoặc không được giải phóng.

### 6.3 Mapping lỗi sang ngôn ngữ ứng dụng

Khuyến khích có adapter thay vì để controller rải `catch`:

```text
HTTP controller
    → ProductService (use case)
      → InventoryGateway interface
        → HttpInventoryGateway (RestClient)
          → remote inventory API
```

`HttpInventoryGateway` có thể map 404 thành `InventoryItemMissing`, 409 thành `InventoryConflict`, 429/503 thành `InventoryTemporarilyUnavailable`, transport timeout thành `InventoryTimeout`. Những lỗi này là abstraction của dependency, để service biết xử lý use case nhưng không bị buộc dùng kiểu exception của Spring HTTP client.

Khi public API trả 502/503/504 hay 404, quyết định dựa **public contract**. 504 Gateway Timeout thường phù hợp khi service thực sự đóng vai gateway và quá hạn chờ upstream; 503 phù hợp khi không có dependency cần thiết; 502 phù hợp với invalid/bad upstream response. Không có quy tắc phải luôn map timeout thành 504 trong mọi hệ thống.

## 7. Retry: giới hạn số lần, backoff, jitter và tính idempotent

Retry có thể hữu ích cho lỗi **tạm thời**, nhưng cũng dễ tạo thêm tải và tạo bản ghi trùng. Quyết định cần dựa vào loại operation, lỗi, timeout budget và idempotency.

| Tình huống | Retry tự động? | Lý do |
| --- | --- | --- |
| GET idempotent, connect refused tạm thời | Có thể, số lần ít | Request chưa chắc đến server; quan sát lỗi mạng |
| GET 503 hoặc 429 | Có thể, theo `Retry-After` và ngân sách | Upstream báo không sẵn sàng/quá tải |
| GET 404 | Thường không | Không tìm thấy theo hợp đồng, không phải transient error |
| POST tạo order / charge payment | Không retry mù | Có thể server đã xử lý, response bị mất |
| POST có idempotency key được **server hỗ trợ và lưu bền** | Có thể theo policy | Server có cách nhận diện lần gọi trùng |
| JSON decode error / schema mismatch | Thường không | Retry không sửa được contract/schema |
| 401/403 | Thường không | Cần sửa auth/permission; không spam retry |
| Timeout sau khi đã gửi request | Chỉ khi semantics cho phép | Không biết server đã xử lý hay chưa |

### Nguyên tắc thiết kế

- Bắt đầu bằng **0 retry**, thêm retry cho lỗi đã được chứng minh là transient và an toàn.
- Tối đa 1–2 retries tùy SLA; exponential backoff + jitter để tránh mọi client đồng loạt retry.
- Đọc và kiểm tra `Retry-After` khi upstream trả 429/503: header có thể là số giây hoặc HTTP-date; không retry vượt hạn ngân sách.
- Timeout từng attempt nhỏ hơn total deadline; không cộng dồn vô hạn.
- Phân biệt các lỗi **đã có HTTP response** với **không có response**; connect timeout và read timeout có độ chắc chắn khác nhau về việc request đã đến upstream.
- Circuit breaker và bulkhead giảm cascading failures; retry không phải công cụ duy nhất.
- Giữ correlation ID, idempotency key và trace context ổn định qua các attempts, log số lần thử thay vì log secret.

**Ví dụ nghiệp vụ nguy hiểm:** POST `/payments` mất response vì mạng gián đoạn. Client thấy read timeout và gọi lại; nếu payment service không hỗ trợ idempotency, tài khoản có thể bị trừ hai lần. Timeout không chứng minh request đầu tiên đã bị hủy.

### Retry trong WebClient

`WebClient` sử dụng Reactor để composition; fragment:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

// Fragment trong method: chỉ retry GET idempotent.
// isRetryable(Throwable) phải được implement theo contract riêng.
Mono<String> response = webClient.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(500))
                .filter(this::isRetryable));
```

Đây là fragment, không phải chương trình độc lập: `webClient` và `isRetryable` chưa định nghĩa. `Retry.backoff(2, ...)` biểu diễn tối đa **hai lần retry sau lần thử đầu tiên**. Đừng lọc bằng `throwable -> true`: sẽ retry cả validation/schema errors. Retry operator trên publisher chỉ có tác dụng khi pipeline được subscribe. Nếu chỉ có tổng deadline, cân nhắc `timeout` ở phạm vi toàn pipeline và cancellation behavior của engine.

## 8. WebClient: thời gian chờ và xử lý lỗi reactive

Với Spring WebFlux, WebClient là lớp HTTP API; timeout vận chuyển nằm ở connector/native engine. Reactor Netty là một lựa chọn phổ biến:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.org")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Fragment này yêu cầu `spring-webflux` và `reactor-netty-http`. `CONNECT_TIMEOUT_MILLIS` là timeout cho connect TCP ở Netty, còn `responseTimeout` của Reactor Netty đặt timeout phản hồi theo semantics của transport. Với connection pool riêng, cấu hình thêm `pendingAcquireTimeout` và giới hạn kết nối bằng `ConnectionProvider`; không tạo pool theo từng request.

**Có thể đặt timeout ở mức publisher:**

```java
Mono<String> mono = client.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
```

`Mono.timeout` theo dõi thời gian của reactive publisher và gây timeout signal nếu không có item/signal phù hợp trong giới hạn. Đây không tự cấu hình DNS/TCP/pool/socket timeouts, và không biến một stream `Flux` dài thành timeout tổng cố định nếu áp dụng sai vị trí. Đặt transport settings và total deadline có chủ đích.

### Xử lý status trong WebClient

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

// Fragment: trả Mono<String>, không gọi block trên event-loop.
Mono<String> content = client.get()
        .uri("/catalog/{id}", 42)
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
                response -> Mono.error(new IllegalStateException(
                        "Upstream status: "
                        + response.statusCode().value())))
        .bodyToMono(String.class);
```

Theo mặc định, `retrieve()` tạo `WebClientResponseException` cho response 4xx/5xx nếu không override; các lỗi connect/transport thường được bọc thành `WebClientRequestException`; decoder failures và Reactor `TimeoutException` cần được xem xét riêng. Trong `onStatus`, nếu custom handler cần đọc body để tạo lỗi, chỉ đọc một lần và giới hạn nội dung; tránh giữ reference tới response body sau khi stream đã được tiêu thụ.

**Tránh các sai lầm:** `block()` trên WebFlux event-loop, `subscribe()` thủ công từ mỗi controller request rồi không quản lý error, tạo WebClient mới theo mỗi item, dùng infinite `retry()`, tăng `maxInMemorySize` vô hạn thay vì streaming khi body lớn.

## 9. Ví dụ độc lập chạy được: Java 17 + RestClient + HTTP server cục bộ

Ví dụ dưới đây sử dụng JDK `HttpServer` để mô phỏng upstream, rồi dùng Spring `RestClient` gọi:

- `GET /inventory/ok`: trả 200, body `item-42`.
- `GET /inventory/missing`: trả 404, body `missing`.
- `GET /inventory/slow`: cố ý giữ response lâu hơn client read timeout; gây transport timeout.

**Không gọi API ngoài Internet khi chạy demo.** Gradle có thể cần mạng để tải Spring dependencies lần đầu. Demo dùng Spring Framework `spring-web` trực tiếp; không cần chạy `SpringApplication` hay server Spring Boot.

### 9.1 Cấu trúc thư mục

```text
http-client-practice/
├── build.gradle
└── src/main/java/demo/HttpClientPractice.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework:spring-web'
}

application {
    mainClass = 'demo.HttpClientPractice'
}
```

Spring Boot BOM giữ bộ phiên bản Spring Framework đồng bộ. Project chỉ cần `spring-web` cho `RestClient` vì demo lấy text/plain chứ không dùng JSON DTO/Jackson. Phần HTTP server là API có sẵn trong JDK (module `jdk.httpserver`); cấu hình ở đây chạy trên classpath thông thường.

### 9.2 Java source đầy đủ

Tệp `src/main/java/demo/HttpClientPractice.java`:

```java
package demo;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

public final class HttpClientPractice {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/inventory", HttpClientPractice::serve);
        server.start();

        try {
            SimpleClientHttpRequestFactory transport =
                    new SimpleClientHttpRequestFactory();
            transport.setConnectTimeout(Duration.ofMillis(300));
            transport.setReadTimeout(Duration.ofMillis(150));

            RestClient client = RestClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .requestFactory(transport)
                    .build();

            System.out.println("OK: " + fetch(client, "ok"));

            try {
                fetch(client, "missing");
                throw new AssertionError("Expected HTTP 404");
            } catch (RestClientResponseException error) {
                System.out.println("MISSING: HTTP "
                        + error.getStatusCode().value());
            }

            try {
                fetch(client, "slow");
                throw new AssertionError("Expected timeout");
            } catch (ResourceAccessException error) {
                System.out.println("SLOW: I/O failure (timeout expected)");
            }
        } finally {
            server.stop(0);
        }
    }

    private static String fetch(RestClient client, String item) {
        return client.get()
                .uri("/inventory/{id}", item)
                .retrieve()
                .body(String.class);
    }

    private static void serve(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        boolean slow = path.equals("/inventory/slow");
        int status = path.equals("/inventory/missing") ? 404 : 200;
        String body = path.equals("/inventory/ok")
                ? "item-42"
                : path.equals("/inventory/missing") ? "missing" : "too-late";

        if (slow) {
            try {
                Thread.sleep(1500);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        } catch (IOException disconnected) {
            // Client đã timeout/ngắt kết nối trước khi server trả kết quả.
        } finally {
            exchange.close();
        }
    }
}
```

**Code này là chương trình đầy đủ.** Nó khởi động server trên địa chỉ loopback và port do hệ điều hành chọn, xây `RestClient` gắn request factory, rồi lần lượt gọi ba endpoint. `try/finally` đảm bảo dừng local server. Ví dụ chỉ làm việc với response text/plain; trong ứng dụng thật có thể thêm JSON converters, authentication, pool và observability.

### 9.3 Lệnh chạy và output

Trong thư mục `http-client-practice`, dùng Gradle đã cài:

```bash
gradle run
```

Nếu có Gradle Wrapper tạo sẵn: macOS/Linux `./gradlew run`; PowerShell Windows `.\gradlew.bat run`. Lưu ý thư mục được mô tả không tự chứa wrapper: hoặc cài Gradle, hoặc tạo wrapper phù hợp trước khi chạy.

**Các dòng stdout của chương trình trong điều kiện bình thường**, không tính log Gradle:

```text
OK: item-42
MISSING: HTTP 404
SLOW: I/O failure (timeout expected)
```

Case slow cố ý đợi 1.500 ms trong khi client read timeout 150 ms. Nếu môi trường chạy thay đổi đáng kể và kết quả slow không gây timeout đúng dự kiến, chương trình sẽ ném `AssertionError("Expected timeout")`; điều này giúp bài thực hành phát hiện tình huống timeout không được áp dụng thay vì âm thầm coi pass. Thông báo `I/O failure` trong `catch` là cách tóm tắt vì `ResourceAccessException` bao gồm nhiều lỗi transport; trong test production nên kiểm tra cause (ví dụ `SocketTimeoutException`) để xác nhận đó đúng là timeout.

Case 404 khác timeout: `retrieve()` đọc được HTTP response nên exception mang status code, còn slow làm request thất bại trước khi có response hợp lệ. Response body `missing` không bị tự chuyển thành `null` hoặc chuỗi rỗng.

### 9.4 Thay đổi thí nghiệm

1. Tăng `setReadTimeout` từ 150 ms lên 3.000 ms: `/inventory/slow` có thể trả `too-late` thành công, và ví dụ đang kỳ vọng timeout sẽ chủ động ném `AssertionError`. Đây là tín hiệu để sửa tiêu chí test nếu bạn chủ động đổi timeout.
2. Đổi `/inventory/missing` thành response 200 + body `not-found`: HTTP client thấy **thành công vận chuyển**; consumer phải diễn giải business response đúng contract, không thể dựa vào HTTP 404.
3. Mô phỏng server trả 503: thay status ở `serve` theo path, bắt `RestClientResponseException` và quan sát code 503, khác với `ResourceAccessException` của timeout.
4. Tắt server trước khi gọi: có thể nhận `ConnectException` được bọc trong `ResourceAccessException`. Đừng coi đó là HTTP 503.
5. Thử URL có hostname cần DNS hoặc HTTPS certificate sai trong môi trường test độc lập để phân biệt DNS/TLS failures; không tắt hostname/certificate verification để “sửa nhanh”.

Ví dụ thực hành không test được pool acquire timeout vì `SimpleClientHttpRequestFactory` không dùng một connection pool kiểu Apache HttpClient/Reactor Netty. Để đánh giá pool, cần chọn engine tương ứng và cấu hình load test riêng.

## 10. Kiểm thử HTTP client thực tế: tránh kiểm thử chỉ một mock method

Mỗi HTTP client adapter nên có **integration/contract tests** gửi request thật tới local stub server, WireMock, MockWebServer hoặc test HTTP server có kiểm soát. Mock mỗi lời gọi Java `restClient.get()...retrieve()` có thể tạo test yếu, không phát hiện serialization, URI encoding, timeout hay status mapping sai.

### Ma trận kiểm thử tối thiểu

| Test | Upstream được stub | Mong đợi ở outbound adapter |
| --- | --- | --- |
| Success | 200 + JSON/text hợp lệ | Parse DTO, trả result đúng |
| Not found | 404 + error body | Map lỗi theo business contract, không gọi retry vô hạn |
| Validation/client error | 400/422 | Bảo toàn lỗi phù hợp, không coi là transient |
| Unauthorized | 401/403 | Không vô tình log credential; auth refresh chỉ theo policy |
| Rate limit | 429 + `Retry-After` | Retry có giới hạn và deadline hoặc báo unavailable |
| Dependency outage | 503 | Chọn retry/circuit breaker theo nhu cầu |
| Read timeout | Server chậm hoặc giữ socket | Fail trong ngân sách, không treo vô hạn |
| Connect failure | Endpoint unreachable/refused | Phân biệt transport và HTTP response |
| Invalid JSON | Response 200 nhưng body sai | Decode error, không trả kết quả giả |
| Payload lớn | Response vượt giới hạn | Chính sách memory/streaming an toàn |
| Retry POST | Server xử lý request rồi mất response | Bảo vệ chống duplicate/idempotency nếu retry |
| Cancellation | Caller hủy request trước khi có response | Reactive cancellation/resource cleanup đúng |

Trong service nhiều dependencies, đo thời gian theo từng call và tổng request budget. Với test timing, dùng stub có kiểm soát và ngưỡng đủ rộng để tránh flaky test; đừng assert độ chính xác từng mili-giây trên CI chịu tải.

### Một unit test phân loại lỗi có ích

Bạn có thể unit test class phân loại exception độc lập:

```java
import java.net.SocketTimeoutException;
import org.springframework.web.client.ResourceAccessException;

class TimeoutClassifier {
    static boolean hasSocketTimeout(Throwable error) {
        for (Throwable current = error;
                current != null; current = current.getCause()) {
            if (current instanceof SocketTimeoutException) {
                return true;
            }
        }
        return false;
    }
}

// Ví dụ assertions (bên trong JUnit test):
// assertTrue(TimeoutClassifier.hasSocketTimeout(
//       new ResourceAccessException("read",
//           new SocketTimeoutException("Read timed out"))));
```

Đây là **fragment minh họa**, không có JUnit imports/test class đầy đủ. Lưu ý không phải mọi timeout đều là `SocketTimeoutException`: JDK HttpClient có thể dùng `HttpTimeoutException`; Reactor `TimeoutException` hoặc engine-specific exceptions xuất hiện ở tầng khác. Classifier production cần hỗ trợ các dạng phù hợp đúng thư viện.

## 11. Thiết kế một outbound adapter và hợp đồng lỗi rõ ràng

Đừng để HTTP controller hay service nghiệp vụ trực tiếp xử lý tên exception của Netty/JDK/Apache ở hàng chục nơi. Có thể tách:

```text
CheckoutController (HTTP boundary)
       │
       ▼
CheckoutService (application use case)
       │
       ▼
PriceGateway (interface)
       │
       └────► HttpPriceGateway (RestClient)
                  ├─ parse PriceQuote DTO
                  ├─ upstream 404 → PriceNotFound
                  ├─ upstream 429/503 → PriceUnavailable
                  ├─ timeout → PriceTimeout
                  └─ invalid JSON → PriceProtocolError
```

Ví dụ interface:

```java
record PriceQuote(String sku, String currency, long cents) {}

interface PriceGateway {
    PriceQuote getPrice(String sku);
}
```

Fragment này không tự compile độc lập khi chưa có implementation. Application service nhận một `PriceGateway` qua constructor, không nhận trực tiếp `RestClient`. Trong `HttpPriceGateway`, map lỗi dựa trên **upstream contract**, và đặt timeout, authentication, tracing, retry ở cùng một ranh giới.

Các mapping quan trọng:

- 404 từ product registry có thể là “SKU không tồn tại”; 404 từ một URL sai cấu hình lại là lỗi triển khai, không được tự coi là business outcome.
- 401/403 có thể là credential expired, permission denied của service account hoặc dấu hiệu thay đổi policy; không biến thành “product missing”.
- 429/503 có thể tạm thời; đừng trả HTTP 500 chung cho tất cả nếu public API cần signal outage rõ ràng.
- Decode/contract mismatch nên được quan sát với metric riêng và alert; nếu 200 trả JSON sai, HTTP đã “thành công” nhưng integration đã hỏng.
- Timeout có thể khiến outcome không xác định đối với lệnh thay đổi trạng thái; trạng thái “unknown” cần reconcile hoặc idempotency key.

### Ví dụ exception translation sang ProblemDetail

Trong HTTP service public, `@RestControllerAdvice` có thể map exception từ adapter sang payload chuẩn:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class DownstreamErrorAdvice {

    @ExceptionHandler(PriceTimeout.class)
    ProblemDetail timeout(PriceTimeout ex) {
        ProblemDetail result = ProblemDetail.forStatus(
                HttpStatus.GATEWAY_TIMEOUT);
        result.setTitle("Upstream timeout");
        result.setDetail("Pricing service did not respond in time");
        return result;
    }

    @ExceptionHandler(PriceUnavailable.class)
    ProblemDetail unavailable(PriceUnavailable ex) {
        ProblemDetail result = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        result.setTitle("Pricing unavailable");
        result.setDetail("Please retry later");
        return result;
    }
}
```

Đây là **Spring fragment**, `PriceTimeout` và `PriceUnavailable` cần tự định nghĩa như domain/adapter exceptions; không phải chương trình chạy độc lập. Phần detail chỉ là thông tin đã được kiểm soát, không tiết lộ internal hostnames, raw exception message, stack trace hoặc token. Có thể gắn `errorCode` và trace ID cho client chẩn đoán; giữ payload tương thích với OpenAPI contract.

## 12. Vận hành: an toàn, hiệu năng và quan sát

### 12.1 Đừng biến HTTP client thành SSRF proxy

Nếu một API chấp nhận URL hoặc hostname từ request của người dùng rồi gọi bằng `RestClient`/`WebClient`, có nguy cơ SSRF tới metadata endpoints, localhost, private network hay service nội bộ. Hãy dùng **base URLs cấu hình sẵn**, allowlist schemes/hosts/ports/IP ranges theo policy, kiểm soát redirects và DNS rebinding, tránh log URL chứa credentials. Không dùng token/header của service account cho host động không tin cậy.

Trên HTTPS, kiểm tra certificate chain và hostname. Đừng bật “trust all certificates” hoặc vô hiệu hóa TLS validation để khắc phục production connectivity. Proxy/firewall và service mesh có thể làm thay đổi timeout, headers và retry; biết lớp nào sở hữu retry để tránh retry multiplication.

### 12.2 Connection pooling, thread và tài nguyên

Một production HTTP client thường nên dùng connection pooling. Tối ưu các giới hạn:

- Max connections tổng và per-route/per-host.
- Pending acquire timeout, queue length, connection max idle/lifetime.
- TLS reuse, DNS caching, connection validation/eviction theo engine.
- Lifecycle shutdown pool, event-loop và client resources.
- Tổng số inbound requests đồng thời nhân fan-out outbound calls, tránh mỗi request tạo quá nhiều calls.

**Ví dụ:** nếu 300 concurrent requests mỗi request gọi 4 dịch vụ cùng lúc, hệ thống có thể tạo lượng concurrent outbound operations vượt tổng 300 nhiều lần. Không chỉ tăng pool vô hạn để “chữa timeout”; cần quan sát upstream capacity, concurrency limiter và kiểm soát bulkhead.

Với Reactor Netty, tài nguyên event-loop và connection pool thường được dùng chung; tách `ConnectionProvider` khi một upstream cần isolation, nhưng phải quản lý lifecycle. Với Apache HttpClient, pool và `RequestConfig` có các timeout riêng; tham số và hành vi không nhất thiết trùng JDK `HttpURLConnection`.

### 12.3 Observability và bảo mật dữ liệu

Metric/trace đáng theo dõi:

| Metric | Dùng để trả lời |
| --- | --- |
| Outbound requests/sec theo dependency, route template | Lưu lượng tới upstream nào tăng? |
| Latency p50/p95/p99, connect/read/total nếu có | Nghẽn ở connect hay response? |
| HTTP statuses 2xx/4xx/5xx và decode failures | Upstream trả lỗi hay payload không tương thích? |
| Timeout count, connect errors, pool acquire wait | Có dấu hiệu nghẽn transport/capacity? |
| Retry attempts, success after retry, circuit state | Retry có cứu request hay khuếch đại outage? |
| Concurrent requests, pool active/idle/pending | Có vượt khả năng của pool hoặc upstream không? |
| Tracing/correlation ID xuyên HTTP hops | Một request bị chậm ở hệ thống nào? |

Ghi log **route template**, dependency identifier, status, latency, trace ID, retry count; không ghi raw `Authorization`, session cookies, payload thanh toán, token, URL query chứa secret hay toàn bộ response body lỗi. Khi cần xem body để debug, áp giới hạn bytes, masking và access control. Đừng để interceptor log response body khiến body bị consume mất hoặc DataBuffer không được release.

### 12.4 Bộ quy tắc production thực tế

1. Định nghĩa outbound client theo dependency và tái sử dụng nó như bean.
2. Mỗi dependency có connect/read/response timeouts, concurrency và circuit policy đã đo.
3. Không chờ vô hạn; còn lại bao nhiêu deadline thì truyền xuống bấy nhiêu khi khả thi.
4. Retry chỉ những lỗi transient phù hợp với idempotency, có max attempts, backoff và jitter.
5. Dịch transport/status/decode errors sang các loại lỗi nghiệp vụ/gateway rõ ràng.
6. Kiểm tra JSON contract, payload size, encoding, response content type.
7. Thêm test với 200, 4xx, 5xx, timeout, connect failure, malformed body và duplicate POST.
8. Dùng TLS đúng, protect credentials, chặn SSRF và bảo vệ sensitive log data.
9. Có cơ chế fallback/resync hợp lệ; không phát sinh response “thành công giả” để giấu outage.
10. Quan sát P95/P99 latency, rate limit, pool pressure, retries và alerts theo upstream.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Không cấu hình timeout | Thread/resource bị treo lâu khi upstream chậm | Đặt timeout transport + deadline tổng |
| Bắt mọi `Exception` rồi trả `null` | “Không có dữ liệu” che khuất outage/bug | Phân loại status, I/O, decode, business error |
| Mặc định HTTP 404 upstream = HTTP 404 public | Lộ topology và sai business semantics | Adapter map theo hợp đồng từng dependency |
| Retry mọi POST timeout | Tạo order/payment trùng | Idempotency key, reconcile, giới hạn retry |
| Retry ngay nhiều lần khi 503 | Khuếch đại sự cố upstream | Backoff+jitter, circuit breaker, budget |
| Chỉ đặt connect timeout | Server nhận kết nối rồi treo vẫn giữ request | Thêm read/response + deadline |
| Coi `ReadTimeout` là tổng request duration | Stream dữ liệu liên tục có thể kéo dài | Dùng deadline hợp lý |
| Recreate client/pool cho mỗi request | Connection churn, thread/resource leak | Inject shared client/managed lifecycle |
| Gọi `block()` trong WebFlux event-loop | Nghẽn event-loop và lỗi Reactor | Compose reactive và trả `Mono/Flux` |
| Log full headers/body | Lộ token, PII và log quá tải | Mask/limit, log metadata cần thiết |
| Tắt TLS certificate validation | Mất khả năng xác minh server | Cấu hình truststore/PKI chính xác |
| Test chỉ mock fluent API chain | Không bắt URI/timeout/status/serialization sai | Gọi local stub HTTP server và assert contract |
| Ngộ nhận `convertAndSend`/HTTP client return là downstream đã xử lý business | Không biết kết quả không xác định | API semantics, confirmations, idempotency |

## 14. Câu hỏi tự kiểm tra và thực hành mở rộng

**Câu 1.** Một RestClient gọi `/inventory` nhận HTTP 503 sau 20 ms. Đây có phải connect timeout không?

**Trả lời:** Không. Đã nhận HTTP response 503, nên đây là lỗi status/protocol/service; connect timeout là lỗi kết nối trước response.

**Câu 2.** Một POST payment bị read timeout sau khi client gửi JSON; có thể retry ngay để chắc chắn không thất bại?

**Trả lời:** Không. Server có thể đã charge thành công và chỉ mất response. Cần idempotency key được upstream hỗ trợ hoặc cơ chế inquiry/reconciliation.

**Câu 3.** Vì sao có connect timeout và read timeout vẫn cần total deadline?

**Trả lời:** Chúng giới hạn các giai đoạn hoặc các thao tác I/O, chưa chắc giới hạn thời gian tổng từ đầu đến cuối, đặc biệt khi có pool wait, DNS, TLS, retries và streaming.

**Câu 4.** Có nên dịch mọi upstream 404 thành public 404?

**Trả lời:** Không. Cần hiểu contract và ý nghĩa thiếu dữ liệu ở dependency. Public 404 chỉ phù hợp nếu resource mà API public hứa cung cấp thật sự không tồn tại.

**Câu 5.** `WebClient.get().retrieve().bodyToMono(String.class)` đã gửi request chưa?

**Trả lời:** Đó là một publisher, thông thường request được kích hoạt khi subscribe. Trong WebFlux controller, trả publisher cho runtime, không tự `block()`.

**Câu 6.** `Retry.backoff(2, ...)` là tổng cộng hai attempts hay hai retries?

**Trả lời:** Tối đa hai **retries**, tức một lần đầu và thêm tối đa hai lần thử lại, nếu filter/policy cho phép.

**Câu 7.** Tại sao `ResourceAccessException` chưa đủ để kết luận “Read timed out”?

**Trả lời:** Lỗi này còn có thể do DNS, connect refused, TLS, reset/EOF và các loại I/O khác. Cần xem cause hoặc mã lỗi của engine để phân loại chính xác.

**Câu 8.** Khi tăng pool, latency vẫn cao và upstream bị 429, hướng giải quyết hợp lý là gì?

**Trả lời:** Giảm concurrency, tôn trọng rate limit/Retry-After, tối ưu fan-out và dùng bulkhead/circuit breaker. Tăng pool đơn thuần có thể làm upstream quá tải hơn.

**Bài tập 1:** Thay local server `/inventory/slow` bằng endpoint trả response text theo nhiều đoạn với khoảng cách giữa các đoạn dưới read timeout; quan sát vì sao read timeout không giới hạn toàn bộ stream. Thử thêm timeout tổng trong một pipeline phù hợp để so sánh.

**Bài tập 2:** Thêm endpoint trả 429 và `Retry-After: 1`; viết retry policy chỉ cho GET, không retry 404 và không vượt deadline. Đo số attempts bằng log có correlation ID.

**Bài tập 3:** Dùng `@RestControllerAdvice` trả ProblemDetail an toàn khi inventory timeout. Phân biệt response 503 từ upstream với trạng thái mất kết nối và decode error; thêm HTTP integration tests cho từng case.

## Tài liệu chính thức

- [Spring Framework — REST Clients, RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework — WebClient Configuration/Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebClient Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework 6.1 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html)
- [Spring Framework 6.1 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Boot — REST Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
