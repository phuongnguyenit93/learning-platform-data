# 19.9. Tích hợp timeout, retry và phân tích response từ downstream

## 1. Bài toán: đăng nhập OIDC thành công nhưng gọi API chậm, lỗi hoặc trả dữ liệu bất thường

Một ứng dụng **Employee Portal** triển khai **Spring Boot 3, Spring Security OAuth 2.0/OIDC Client và Spring MVC/Servlet**. Người dùng đăng nhập bằng tài khoản công ty qua OIDC. Sau đó, backend dùng **WebClient** để gọi **Orders API** thay mặt người dùng với access token:

~~~text
Browser
  |
  | GET /bff/orders (JSESSIONID, HTTP session của Portal)
  v
Employee Portal (Spring MVC / Servlet)
  |
  | WebClient + Servlet OAuth2 Client filter
  | Authorization: Bearer <access-token>
  v
Orders API (Resource Server)
  |
  +-- 200 OK: danh sách đơn hàng
  +-- 401 invalid_token: access token không hợp lệ
  +-- 403 insufficient_scope: thiếu quyền
  +-- 429 Too Many Requests: giới hạn tốc độ
  +-- 502/503/504: lỗi hạ tầng
  +-- kết nối chậm, timeout hoặc phản hồi sai schema
~~~

Nếu chỉ viết:

~~~java
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class);
~~~

thì vẫn còn nhiều câu hỏi phải trả lời:

- Nếu TCP connection không thiết lập được, ứng dụng đợi bao lâu?
- Nếu server nhận request nhưng không gửi response, thời gian chờ nào được áp dụng?
- Timeout là cho **một lần gọi** hay cho toàn bộ các lần **retry**?
- Có nên retry HTTP POST tạo đơn hàng hay chỉ GET đọc dữ liệu?
- HTTP 401 có nghĩa Portal session đã hết hay access token đến Resource Server bị từ chối?
- HTTP 403 có thể sửa bằng refresh token không?
- HTTP 429 có header `Retry-After`; ứng dụng cần xử lý thế nào?
- Lấy **status, headers và body** của downstream mà không làm lộ token hoặc nuốt response body ra sao?
- Nếu dùng WebClient trong ứng dụng **Servlet**, có phải chuyển toàn bộ bảo mật sang WebFlux không?

**Mục tiêu bài:** xây dựng cách dùng **WebClient trên Servlet** có timeout rõ ràng, retry có giới hạn và chính sách phân tích phản hồi downstream chính xác, đồng thời giữ nguyên ranh giới OAuth2 token, phiên đăng nhập và authorization của Resource Server.

> Môi trường ví dụ: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC và WebClient của Spring WebFlux. Các domain, client ID, mã lỗi và token đều minh họa. Một số API khác theo phiên bản cụ thể; hãy dùng dependency đồng bộ với Spring Boot BOM của dự án.

## 2. WebClient trên Servlet: hiểu đúng mô hình thực thi

**Spring MVC** chạy trên Servlet container và thường xử lý controller bằng các worker thread. **WebClient** là HTTP client với API Reactive, thường dựa trên Reactor Netty để làm I/O bất đồng bộ, nhưng có thể sử dụng trong **ứng dụng Servlet**.

| Khía cạnh | Spring MVC + WebClient | Spring WebFlux application |
|---|---|---|
| Web server request stack | Servlet API, `HttpServletRequest` | Reactive `ServerWebExchange` |
| Security chain | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| OAuth2 Client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| WebClient OAuth2 filter | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| HTTP client response type | `Mono<T>` hoặc `Flux<T>` từ WebClient | Giống vậy |
| Cách điều phối | Có thể return Publisher qua MVC async hoặc block tại ranh giới blocking phù hợp | Không block Reactor event-loop |

**Thêm WebClient không tự biến Portal thành WebFlux.** Khi Spring Boot có cả `spring-boot-starter-web` và `spring-webflux` trên classpath, ứng dụng thông thường vẫn dùng MVC trừ khi được cấu hình loại web application khác.

### 2.1. Vì sao WebClient có ích với Servlet?

- API gọi mạng được biểu diễn qua `Mono`, thuận tiện kết hợp timeout/retry/error mapping.
- Có thể cấu hình Reactor Netty connection pool, SSL và HTTP response timeout.
- Controller có thể trả `Mono<T>` để sử dụng cơ chế async hỗ trợ bởi Spring MVC, tránh chặn Servlet thread trong toàn bộ thời gian gọi API nếu cấu hình phù hợp.
- Hữu ích khi gọi nhiều downstream services, nhưng phải kiểm soát tổng đồng thời, memory và timeout.

WebClient **không tự loại bỏ** yêu cầu quản lý thread, connection pool, backpressure hay bảo mật. Nếu controller gọi `.block()`, Servlet thread vẫn phải chờ. `.block()` có thể dùng ở một ranh giới blocking được thiết kế rõ trong ứng dụng MVC, nhưng không nên xuất hiện trong Reactor event-loop hoặc bị lạm dụng khiến hệ thống thiếu thread.

## 3. Kiến trúc đúng: OAuth2 filter, timeout, retry và response handling

~~~mermaid
flowchart TD
    U["Browser gọi /bff/orders"] --> S["Spring MVC SecurityContext / OIDC principal"]
    S --> C["OrdersGateway dùng WebClient"]
    C --> F["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    F --> M["OAuth2AuthorizedClientManager"]
    M --> AR["Authorized Client Repository/Service"]
    M --> AS["Authorization Server token endpoint khi cần refresh"]
    F --> H["HTTP connector / Reactor Netty"]
    H --> API["Orders API"]
    API --> R{"Downstream response"}
    R -->|2xx| D["Decode dữ liệu / headers"]
    R -->|401 Bearer invalid_token| I["OAuth2 failure handling, tránh dùng token cũ"]
    R -->|403| A["Thông báo không đủ quyền"]
    R -->|429, 502, 503, 504| T["Retry có điều kiện / backoff"]
    R -->|4xx khác| B["Xử lý lỗi nghiệp vụ"]
    H -->|Network timeout| X["Timeout / cancellation / retry policy"]
~~~

Để thiết kế rõ ràng, chia thành bốn tầng:

1. **Security/OAuth2 layer:** lấy token theo registration và principal tin cậy; xử lý invalid token đúng nơi.
2. **Transport layer:** DNS, connect timeout, response timeout, TLS, connection pool.
3. **Resilience layer:** retry có chọn lọc, backoff, jitter, tổng thời gian chờ và hạn chế đồng thời.
4. **Application layer:** hiểu status/header/body của downstream và chuyển thành kết quả hoặc lỗi phù hợp cho Portal.

Nếu chỉ cấu hình retry ở cuối pipeline mà không biết lỗi thuộc tầng nào, ứng dụng dễ retry một lỗi **không thể sửa**, ví dụ 403 thiếu scope, hoặc gửi lặp một POST có side effect.

## 4. Dependencies và cấu hình OAuth2 Client mẫu

### 4.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // WebClient API và các thành phần WebFlux cần thiết.
    implementation 'org.springframework:spring-webflux'

    // Có thể dùng starter-webflux khi muốn Boot quản lý đầy đủ
    // client reactor-netty + WebClient support; không cần thêm hai lần.
    implementation 'org.springframework.boot:spring-boot-starter-reactor-netty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Với dự án dùng `spring-boot-starter-webflux`, starter đó đã kéo các phụ thuộc WebClient/HTTP client cần thiết theo cấu hình Boot, nên **không cần đồng thời thêm** các dependency WebFlux/Netty riêng trừ khi có lý do quản lý phiên bản cụ thể. Ví dụ trên minh họa lựa chọn WebClient **trong MVC** nhưng không thay đổi application type.

### 4.2. OIDC registration

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  servlet:
    session:
      timeout: 30m
~~~

`session.timeout` là timeout phiên web; **không phải** network timeout của Orders API hay thời hạn access token. `OIDC_CLIENT_SECRET` phải được cấp qua secret manager/runtime và không được ghi vào mã nguồn hay frontend.

### 4.3. SecurityFilterChain trên Servlet

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` xử lý OIDC login. `oauth2Client()` hỗ trợ OAuth2 Client authorization. Không phải cứ bật hai DSL đó thì mọi WebClient được tự động đính Bearer token: phải cấu hình **OAuth2 exchange filter** ở đúng WebClient.

## 5. Cấu hình WebClient HTTP transport với Reactor Netty

Có nhiều khái niệm được gọi chung là “timeout”. Chúng nên được phân biệt rõ.

| Loại giới hạn | Bắt đầu áp dụng khi nào? | Vấn đề giải quyết |
|---|---|---|
| **Connection acquisition timeout** | Đợi có connection từ pool | Pool cạn, request xếp hàng quá lâu |
| **TCP connect timeout** | Thiết lập kết nối TCP tới host | Host không phản hồi, network unreachable |
| **TLS handshake timeout** | Thực hiện TLS handshake | TLS server/proxy không phản hồi hoặc gặp sự cố |
| **Response/read timeout** | Đợi dữ liệu từ downstream theo chính sách HTTP connector | Server xử lý lâu hoặc response bị treo |
| **Per-attempt reactive timeout** | Một attempt của pipeline đã subscribe | Giới hạn thời gian một lần gọi theo ngữ nghĩa của pipeline |
| **Overall timeout/deadline** | Từ đầu đến cuối pipeline có thể gồm retries | Ngăn tất cả retries cộng lại vượt yêu cầu SLA |
| **HTTP session timeout** | Phiên đăng nhập Servlet không hoạt động đủ lâu | Kiểm soát vòng đời login, không liên quan latency Orders API |

### 5.1. Bean WebClient transport

~~~java
package com.example.portal.config;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class OrdersTransportConfig {

    @Bean("ordersHttpClient")
    HttpClient ordersHttpClient() {
        ConnectionProvider pool = ConnectionProvider.builder("orders-pool")
            .maxConnections(100)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .build();

        return HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(5));
    }

    @Bean("ordersBaseWebClient")
    WebClient ordersBaseWebClient(HttpClient ordersHttpClient) {
        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(ordersHttpClient)
            )
            .build();
    }
}
~~~

Các con số **2 giây, 5 giây, 100 connections** chỉ là minh họa; production cần đo latency, tải, pool contention và SLO để lựa chọn. Không chọn tùy tiện những giá trị này cho hệ thống thực.

**Lưu ý quản lý resource:** nếu tự tạo `ConnectionProvider` riêng, cần quản lý lifecycle và giải phóng connection pool khi ứng dụng dừng theo chính sách cấu hình. Trong ứng dụng Spring Boot thông thường, tận dụng `WebClient.Builder`, Reactor Netty resource management và HTTP client auto-configuration có thể giúp tránh tạo nhiều pool không cần thiết.

### 5.2. Response timeout không phải giới hạn toàn bộ nghiệp vụ

`HttpClient.responseTimeout(...)` áp dụng ở HTTP transport cho thời gian chờ response/read theo semantics Reactor Netty, nhưng không nhất thiết bao trùm toàn bộ các bước:

- Chờ lấy connection từ pool.
- Tạo token/refresh token từ OAuth2 manager.
- Retry backoff giữa các attempt.
- Parse JSON, xử lý dữ liệu nghiệp vụ.

Nếu yêu cầu là **“toàn bộ request đến Orders API phải kết thúc trong một deadline”**, cần đặt **overall timeout** ở level pipeline hoặc tầng orchestration thích hợp.

### 5.3. TLS và proxy

Một WebClient dùng OAuth2 Bearer token **phải** chỉ gọi endpoint HTTPS tin cậy. Khi doanh nghiệp có egress proxy:

- Cấu hình proxy ở HTTP connector tương ứng.
- Chọn truststore/CA phù hợp và không tắt certificate/hostname verification.
- Nếu có mTLS, đảm bảo keystore và client certificate được bảo vệ.
- Tránh proxy log `Authorization: Bearer`, client secret, refresh token hoặc body nhạy cảm.

Nếu downstream gửi redirect tới hostname khác, phải có chính sách **không chuyển tiếp Bearer token tới host ngoài allowlist**. Không dùng URL tuyệt đối từ input của user trong một WebClient đã được cấu hình tự động đính token.

## 6. Timeout ở Reactor pipeline: per-attempt và overall

Reactor cung cấp toán tử `timeout(Duration)`:

~~~java
Mono<String> result = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(6));
~~~

Đây là giới hạn cho **Mono từ lúc subscribe tới khi phát tín hiệu theo cách operator định nghĩa**. Khi timeout, Reactor phát `TimeoutException` và hủy subscription ở upstream nếu có thể.

**Cancellation không có nghĩa downstream chưa xử lý request.** Nếu request đã tới server, kết quả hoặc side effect có thể vẫn xảy ra; điều này quan trọng với các thao tác ghi dữ liệu.

### 6.1. Timeout cho mỗi attempt

~~~java
Mono<String> callOnce() {
    return ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

Khi `timeout` đặt **trước** `retryWhen`, mỗi lần retry đăng ký lại upstream có thể nhận một cửa sổ timeout mới.

### 6.2. Overall deadline cho cả retries

~~~java
Mono<String> result = callOnce()
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(8));
~~~

`timeout(Duration.ofSeconds(8))` **sau retry** giới hạn toàn bộ subscription gồm các lần attempt và backoff. Đây là deadline ở ứng dụng, không phải connection timeout ở tầng TCP.

Nếu tổng thời gian chờ không đủ cho 3 attempts/backoff, overall timeout sẽ cắt pipeline trước khi hoàn thành toàn bộ retry policy. Điều đó **đúng** nếu yêu cầu nghiệp vụ ưu tiên giới hạn thời gian.

### 6.3. Kiểm soát ngân sách timeout

Ví dụ:

~~~text
SLO của /bff/orders: 1.5 giây ở phân vị mục tiêu
Network/connect budget: vài trăm ms
Downstream response budget: dưới 1 giây
Retry budget: chỉ khi có thời gian còn lại
Overall deadline: nhỏ hơn timeout của upstream gateway
~~~

Giá trị cụ thể phải dựa trên đo đạc. Một lỗi thiết kế là đặt:

~~~text
Gateway timeout       = 5 giây
Portal overall timeout = 30 giây
3 retries x 10 giây     = có thể kéo dài quá thời hạn browser đã bỏ đi
~~~

Khi gateway đã đóng connection, Portal tiếp tục chạy nhiều retries gây tải thừa. Deadline ở các tầng nên được điều phối cùng nhau.

## 7. Retry: không phải mọi lỗi đều nên thử lại

Retry là **gửi lại một thao tác** sau khi lỗi. Một yêu cầu HTTP có thể đã tới server và tạo side effect **trước khi** Portal nhận timeout. Vì vậy retry phải được đánh giá theo:

1. **HTTP method và tính idempotent của nghiệp vụ**.
2. **Mã lỗi/loại exception**: lỗi tạm thời hay lỗi cấu hình/quyền.
3. **Giới hạn attempts và thời gian**.
4. **Backoff, jitter và Retry-After**.
5. **Tải đồng thời** trên Portal và downstream.
6. **Khả năng request body được replay an toàn**.
7. **Trạng thái token, authorization và người dùng**.

### 7.1. Ma trận lựa chọn retry

| Tình huống | Có nên retry tự động? | Giải thích |
|---|---|---|
| GET trả 502/503/504 | **Có thể**, có giới hạn | Thường là lỗi hạ tầng tạm thời |
| GET trả 429 | **Có thể**, theo rate limit/Retry-After | Cần tránh làm quá tải thêm |
| GET gặp connect timeout | **Có thể**, có giới hạn | Nếu request an toàn và deadline còn |
| GET gặp response timeout | **Cân nhắc** | Server có thể đã xử lý; GET đúng nghĩa an toàn thường ít rủi ro hơn |
| 401 Bearer `invalid_token` | **Không retry mù quáng** | Cần xử lý OAuth2 authorized client/token lifecycle |
| 403 `insufficient_scope` | **Không** | Retry không tự tạo quyền mới |
| 400 validation error | **Không** | Request sai cần sửa payload |
| 404 resource không tồn tại | **Thường không** | Phụ thuộc contract consistency nhưng không mặc định transient |
| 409 conflict | **Tùy business** | Không retry vô điều kiện; có thể cần giải quyết phiên bản dữ liệu |
| 500 | **Tùy API** | Có thể transient nhưng không chắc; cần contract và giới hạn |
| POST tạo đơn hàng | **Không mặc định** | Có nguy cơ tạo nhiều đơn |
| POST có idempotency key server hỗ trợ | **Có thể** | Chỉ khi API bảo đảm deduplication đúng contract |

**HTTP method chỉ là tín hiệu**. Một endpoint GET thực hiện side effect trái chuẩn vẫn có rủi ro; một POST có idempotency key được server xác minh có thể retry an toàn. Đánh giá dựa trên hành vi thực tế của API.

## 8. RetryWhen với backoff, jitter và giới hạn lần thử

Đối với API đọc dữ liệu, có thể chọn retry một số lỗi 502/503/504. Ví dụ:

~~~java
package com.example.portal.downstream;

import java.time.Duration;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class OrdersReadGateway {

    private final WebClient ordersWebClient;

    public OrdersReadGateway(WebClient ordersWebClient) {
        this.ordersWebClient = ordersWebClient;
    }

    public Mono<String> listOrders() {
        Retry retryPolicy = Retry.backoff(
                2,
                Duration.ofMillis(200)
            )
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.3)
            .filter(this::isRetryable)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure());

        return ordersWebClient.get()
            .uri("/api/orders")
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(6));
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int code = response.getStatusCode().value();
            return code == 502 || code == 503 || code == 504;
        }
        return error instanceof java.util.concurrent.TimeoutException;
    }
}
~~~

**Giải thích quan trọng:**

- `Retry.backoff(2, ...)` cho phép **tối đa hai lần retry sau lần thử ban đầu**, tức tối đa **ba attempts**.
- `.filter(...)` giới hạn lỗi được phép thử lại; **không** retry 401/403/400.
- `.jitter(0.3)` làm khoảng đợi có độ ngẫu nhiên để giảm “thundering herd”.
- `timeout(2s)` trước retry giới hạn mỗi attempt ở Reactor pipeline.
- `timeout(6s)` sau retry đặt deadline cho cả chuỗi attempts/backoff.
- `.onRetryExhaustedThrow(...)` giữ lỗi cuối để phân tích ở tầng gọi thay vì chỉ có lỗi “retry exhausted” khó xử lý.

Ví dụ này **chỉ dành cho GET** có semantics an toàn. Nếu client gọi API khác hoặc dùng một WebClient chung, phải giới hạn retry riêng theo request thay vì bật filter retry cho mọi phương thức trên builder.

### 8.1. Timeout có thể xảy ra sau khi token được refresh

Khi WebClient có Servlet OAuth2 filter, một attempt có thể bao gồm:

~~~text
Lấy Authentication/registration
 -> manager lấy authorized client
 -> có thể refresh tại Authorization Server
 -> kết nối Orders API
 -> nhận/parse response
~~~

`timeout()` ở vị trí nào sẽ quyết định nó giới hạn phần pipeline nào. Nếu timeout xảy ra trong giai đoạn OAuth2 manager, retry toàn pipeline có thể **lặp một token authorization attempt** thay vì chỉ lặp gọi Orders API.

Đó là lý do cần **phân loại lỗi** và sử dụng retry có giới hạn; không gom mọi Throwable vào một danh sách retry.

### 8.2. Không mở retry vô điều kiện cho WebClient toàn cục

Ví dụ nguy hiểm:

~~~java
// Không nên gắn vào mọi request một cách vô điều kiện:
return next.exchange(request)
    .retryWhen(Retry.fixedDelay(10, Duration.ofMillis(50)));
~~~

Nó có thể retry:

- 401 do token không hợp lệ.
- 403 thiếu quyền.
- POST thanh toán hoặc tạo đơn hàng.
- Error decode payload đã nhận.
- 500 mà downstream đã commit side effect.

Retry nên được áp dụng ở **operation-specific boundary**, có business policy và số lần thử rõ ràng.

## 9. HTTP 429 và Retry-After

Downstream có thể trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"rate_limited"}
~~~

Hoặc:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Mon, 16 Nov 2026 03:00:00 GMT
~~~

`Retry-After` có thể là **số giây** hoặc **HTTP-date**; không chỉ là một integer trong mọi trường hợp.

Thiết kế hợp lý:

1. Kiểm tra 429 có phải rate limit của downstream mà client được phép retry hay không.
2. Đọc `Retry-After` nếu có và parse theo contract HTTP.
3. Áp dụng **giới hạn chờ tối đa** và **overall deadline** của Portal.
4. Nếu Retry-After dài hơn ngân sách còn lại, **không giữ request chờ vô hạn**; trả lỗi có thể xử lý cho caller.
5. Có thể triển khai rate limiter/bulkhead/circuit breaker để ngăn nhiều request cùng retry.
6. Không dùng retry như cách vượt rate limit hoặc quota.

### 9.1. Khi nào không chờ Retry-After?

Ví dụ:

~~~text
Portal request budget: 5 giây
Downstream Retry-After: 120 giây
~~~

Không nên giữ WebClient Mono và servlet async request suốt 120 giây chỉ để hy vọng Retry-After qua đi. Thay vào đó, có thể:

- Trả kết quả “tạm thời không khả dụng” với mã lỗi được chuẩn hóa.
- Dời tác vụ vào hàng đợi nếu nghiệp vụ cho phép và có cơ chế idempotency.
- Để frontend retry sau một khoảng phù hợp theo API contract.

Đừng chuyển nguyên một Retry-After của API nội bộ ra frontend nếu nó chứa thông tin/quota không nên công bố; chỉ chuyển phần đã được chính sách Portal chấp nhận.

## 10. HTTP POST và idempotency key

Giả sử Portal gửi:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Authorization: Bearer <token>

{"sku":"SKU-123","quantity":1}
~~~

Orders API đã tạo đơn hàng nhưng mạng lỗi trước khi response về Portal. Nếu tự retry cùng request, có thể tạo **hai đơn hàng**.

Một cơ chế giúp giảm rủi ro là **idempotency key được Orders API hỗ trợ thật sự**:

~~~http
POST /api/orders HTTP/1.1
Idempotency-Key: 45d676e5-9895-4f59-9d9f-75f48bbc4174
Content-Type: application/json
Authorization: Bearer <token>

{"sku":"SKU-123","quantity":1}
~~~

Điều kiện an toàn:

- Key phải được tạo cho **một ý định nghiệp vụ cụ thể**, không sinh key mới cho mỗi retry.
- Downstream phải cam kết deduplicate cùng key, kiểm tra payload/tenant/user binding và thời hạn lưu key.
- Client giữ nguyên key trên tất cả retry attempts của cùng operation.
- Nếu nhận kết quả không rõ, ứng dụng có thể dùng endpoint tra trạng thái đơn hàng thay vì POST lại.
- Không nghĩ chỉ gắn header mà downstream chưa hỗ trợ là đủ để request trở thành idempotent.

**Chính sách retry cho GET không được sao chép nguyên xi sang POST/PATCH/DELETE.**

## 11. Phân tích response với retrieve()

`retrieve()` là cách ngắn gọn để đọc body và map HTTP error. Nếu không cấu hình gì thêm, response 4xx/5xx thường được chuyển thành `WebClientResponseException` khi gọi `bodyToMono(...)`.

~~~java
Mono<OrdersPage> result = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class);
~~~

Trong đó `OrdersPage` là DTO do ứng dụng định nghĩa, không phải class của Spring Security. HTTP 200 được decode thành DTO; HTTP error mặc định trở thành error signal.

### 11.1. Map mã lỗi bằng onStatus

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<OrdersPage> orders = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .onStatus(
        status -> status.value() == 429,
        response -> response.createException()
            .map(error -> new DownstreamRateLimitedException(
                "Orders API rate limit exceeded"))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException()
            .map(error -> new DownstreamUnavailableException(
                "Orders API temporarily unavailable"))
    )
    .bodyToMono(OrdersPage.class);
~~~

`DownstreamRateLimitedException` và `DownstreamUnavailableException` là **application-specific exceptions** cần tự định nghĩa; ví dụ chỉ minh họa mapping. `response.createException()` **đọc response body** để tạo exception có status/headers/body, sau đó ở ví dụ này ta tạo lỗi nghiệp vụ với thông điệp không chứa raw body để tránh rò rỉ thông tin.

**Hệ quả:** khi đã map exception tùy chỉnh, retry filter kiểm tra `WebClientResponseException` theo HTTP status sẽ **không còn thấy loại đó** ở downstream, trừ khi bạn giữ status/cause trong custom exception hoặc định nghĩa retry filter cho application-specific exception.

Đây là lý do cần thiết kế **thứ tự error mapping và retry** cùng nhau.

### 11.2. Đừng dùng onStatus trả Mono.empty() để biến 404 thành null

Trong `retrieve().onStatus(...)`, trả `Mono.empty()` từ status handler nghĩa là **không coi status đó là lỗi tại bước này**, rồi response tiếp tục được xử lý qua body decoder. Nó **không tự biến HTTP 404 thành `Mono.empty()` của nghiệp vụ**.

Nếu cần 404 tương đương “không tìm thấy tài nguyên” và không đọc body, dùng `exchangeToMono()` hoặc mapping exception có kiểm soát ở phía sau.

## 12. Phân tích status, headers và body bằng toEntity()

Khi cần đọc **status + response headers + decoded body**, `retrieve().toEntity(...)` hữu ích:

~~~java
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

Mono<ResponseEntity<OrdersPage>> response =
    ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .toEntity(OrdersPage.class);
~~~

Ví dụ:

~~~java
return response.map(entity -> {
    String etag = entity.getHeaders().getETag();
    int code = entity.getStatusCode().value();
    OrdersPage page = entity.getBody();
    return new OrdersResult(code, etag, page);
});
~~~

`OrdersResult` là DTO do ứng dụng tự định nghĩa. `toEntity(...)` cho phép lấy header như `ETag` hoặc correlation ID đã được upstream cung cấp.

**Lưu ý:** `retrieve()` vẫn chuyển phần lớn 4xx/5xx thành exception theo mặc định; `toEntity(...)` không đồng nghĩa tự động trả `ResponseEntity` cho mọi lỗi mà không cần `onStatus` hoặc chiến lược khác.

### 12.1. ETag và conditional requests

Nếu downstream hỗ trợ ETag, Portal có thể gửi `If-None-Match` cho GET nhằm giảm dữ liệu truyền:

~~~http
GET /api/orders HTTP/1.1
If-None-Match: "orders-v12"
Authorization: Bearer <token>
~~~

Khi server trả `304 Not Modified`, ứng dụng phải có cache response body tương ứng đã được bảo vệ theo **principal/tenant/authorization context**, không lấy dữ liệu cache của người dùng khác chỉ vì ETag giống nhau.

Cache token, response và authorization có các rủi ro khác nhau; phần này là tối ưu downstream HTTP, không thay thế OAuth2 authorized client manager.

## 13. exchangeToMono(): khi cần điều khiển từng status rõ ràng

`exchangeToMono()` cho phép ứng dụng xử lý `ClientResponse` và quyết định cách đọc body theo status.

Ví dụ GET chi tiết một đơn hàng:

~~~java
package com.example.portal.downstream;

import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class OrderLookupGateway {

    private final WebClient client;

    public OrderLookupGateway(WebClient client) {
        this.client = client;
    }

    public Mono<OrderDto> findOrder(String id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .exchangeToMono(response -> {
                HttpStatusCode status = response.statusCode();

                if (status.is2xxSuccessful()) {
                    return response.bodyToMono(OrderDto.class);
                }

                if (status.value() == 404) {
                    // Không có order tương ứng; giải phóng response body.
                    return response.releaseBody()
                        .then(Mono.<OrderDto>empty());
                }

                // Tạo exception có status/headers và đọc body hữu hạn
                // theo cấu hình codec, rồi truyền error signal.
                return response.createException()
                    .flatMap(error -> Mono.<OrderDto>error(error));
            });
    }
}
~~~

`OrderDto` là kiểu dữ liệu của ứng dụng.

**Điểm cần nhớ:** mỗi nhánh cần đọc, bỏ hoặc giải phóng body một cách phù hợp. `ClientResponse` không phải một object có thể giữ lại rồi tùy ý gọi `bodyToMono()` nhiều lần sau khi stream đã tiêu thụ.

### 13.1. 404 có thực sự nghĩa “không có dữ liệu” không?

Chỉ dùng `Mono.empty()` cho 404 khi **contract của downstream** định nghĩa 404 là “không tìm thấy” trong ngữ cảnh nghiệp vụ này. Một 404 do sai route/gateway có thể là lỗi cấu hình cần được ghi nhận, không nên bị chuyển thành “Danh sách trống”.

### 13.2. Khác biệt với exchange() cũ

API `exchange()` đời cũ dễ dẫn đến lỗi quản lý body/connection và đã được thay thế bởi các cách sử dụng hiện đại như `retrieve()` và `exchangeToMono()`. Không giữ `ClientResponse` ngoài thời gian xử lý mà không quản lý tài nguyên.

## 14. Phân biệt phản hồi của Resource Server với lỗi OAuth2 Client

Một request WebClient có OAuth2 filter thường có hai pha:

~~~mermaid
sequenceDiagram
    participant MVC as Spring MVC controller
    participant WC as WebClient + Servlet OAuth2 filter
    participant M as OAuth2AuthorizedClientManager
    participant AS as Authorization Server
    participant RS as Orders API

    MVC->>WC: GET /api/orders
    WC->>M: authorize(company, principal)
    opt Access token cần refresh
        M->>AS: POST /token, refresh_token grant
        AS-->>M: Token mới hoặc invalid_grant
    end
    M-->>WC: Authorized client hoặc lỗi OAuth2
    WC->>RS: Authorization: Bearer access token
    RS-->>WC: 200 / 401 / 403 / 429 / 5xx
    WC-->>MVC: Response body hoặc error signal
~~~

| Nơi lỗi | Ví dụ | Tác động |
|---|---|---|
| **Token endpoint** | `invalid_grant` khi refresh token bị thu hồi | Manager không lấy được access token mới |
| **Token endpoint** | `invalid_client` | Client authentication/configuration có vấn đề |
| **Resource Server** | `401 invalid_token` | Bearer token đã dùng bị API từ chối |
| **Resource Server** | `403 insufficient_scope` | Token có thể hợp lệ nhưng thiếu quyền |
| **Transport** | TCP connect error, TLS failure, timeout | Không chứng minh token hỏng |
| **Application decoder** | JSON không đúng schema | API response format không tương thích |

**Không retry token endpoint `invalid_grant` bằng cách gọi lại cùng refresh token vô hạn.** Nếu provider dùng refresh-token rotation, retry có thể làm tình trạng tệ hơn.

## 15. OAuth2 WebClient trên Servlet: filter và manager

Spring Security cung cấp:

~~~java
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
~~~

Tuy package có đoạn `reactive.function.client`, class này dành cho **WebClient trong Servlet stack**.

### 15.1. Bean WebClient dùng custom manager

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import reactor.netty.http.client.HttpClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        HttpClient ordersHttpClient,
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(ordersHttpClient)
            )
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Ví dụ này dùng một bean `webAuthorizedClientManager` đã được định nghĩa trước, chẳng hạn `DefaultOAuth2AuthorizedClientManager` dành cho Servlet request. `ordersHttpClient` là HTTP client có timeout từ mục 5. Chỉ có một WebClient này được gắn OAuth2 filter.

**Constructor nhận manager tùy chỉnh không mặc nhiên bảo đảm đã có authorization failure handler cho Bearer error của Resource Server.** Nếu cần dọn authorized client lỗi, phải cấu hình đúng handler/repository/service theo phiên bản Spring Security của dự án.

### 15.2. Chỉ định registration khi gọi API

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Khi gọi trong một Servlet request đã authenticated, filter/manager dùng registration `company` để lấy authorized client cho principal phù hợp. **Không dùng registration ID và principal name do browser tự ý gửi** để truy cập token của account khác.

### 15.3. WebClient HTTP retry và token manager tương tác ra sao?

Một call điển hình:

~~~text
Retry attempt 1:
  OAuth2 filter -> manager -> có thể refresh token
  HTTP GET Orders API -> 503

Retry attempt 2:
  OAuth2 filter -> manager -> tải token
  HTTP GET Orders API -> 200
~~~

Nếu `retryWhen` được đặt ở cuối `WebClient` publisher, **mỗi retry có thể đi qua lại OAuth2 filter/manager**, tùy cách compose pipeline. Điều này cần được cân nhắc khi:

- Token endpoint chậm hoặc lỗi.
- Refresh token được rotate.
- Một request bị 401 invalid_token và failure handler xóa token.
- Hệ thống chạy nhiều replica.

Không coi retry token exchange và retry downstream API là một thao tác không phân biệt được.

## 16. Xử lý 401 Bearer invalid_token đúng tầng

Resource Server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Điều này khác với việc **browser chưa đăng nhập Portal**.

~~~text
Browser -> Portal:
  JSESSIONID hợp lệ, SecurityContext có OIDC principal

Portal -> Orders API:
  Access token AT-1 bị từ chối
~~~

**Không mặc định invalid_token ở downstream nghĩa là phải hủy HTTP session của Portal.** Có thể cần:

1. Xác định token thuộc registration/principal nào.
2. Loại authorized client không còn hợp lệ nếu Bearer error đủ bằng chứng và policy cho phép.
3. Tránh tái sử dụng AT-1 cho request tiếp theo.
4. Dùng grant thích hợp để authorize lại nếu có thể; với interactive authorization code grant có thể cần browser redirect/consent.
5. Trả lỗi/CTA phù hợp cho frontend nếu không thể tự phục hồi.

### 16.1. Failure handler trong ServletOAuth2AuthorizedClientExchangeFilterFunction

Khi dùng constructor nhận:

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository
)
~~~

Spring Security có cơ chế cấu hình handler loại authorized client theo Bearer errors phù hợp với repository tương ứng. Khi dùng constructor **nhận custom manager**, bạn cần xem và cấu hình `OAuth2AuthorizationFailureHandler` rõ ràng nếu muốn đồng nhất cleanup.

Ví dụ ý tưởng tích hợp:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

// Cấu hình authorization failure handler phù hợp repository/service
// thông qua oauth2.setAuthorizationFailureHandler(...).
// Handler phải gắn với đúng authorized-client store của manager.
~~~

Các implementation như `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` có thể được dùng cho error code phù hợp; chi tiết constructor/remover phải khớp Spring Security version và storage đã chọn. Đây không phải tín hiệu để xóa **mọi token** chỉ vì HTTP status 401.

### 16.2. Không dùng retryWhen để giải quyết 401 vô hạn

~~~java
// Sai: retry tất cả Throwable, bao gồm invalid_token/401.
return ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(Retry.fixedDelay(
        10, Duration.ofMillis(100)
    ));
~~~

Nếu token cũ vẫn được gửi hoặc manager không thể authorize lại, 10 retries chỉ khiến Orders API nhận 10 request lỗi. Nếu token được cấp lại, retry phải có **giới hạn** và được tích hợp với cleanup/token lifecycle, không chỉ là lặp HTTP request.

## 17. HTTP 403: không đủ scope khác với token hết hạn

Downstream có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

Trong khi access token có:

~~~text
scope = orders.read
~~~

Ở đây **token có thể vẫn hợp lệ** để đọc danh sách đơn hàng. Retry GET hoặc refresh cùng scope không tự tạo quyền `orders.write`.

Cách xử lý:

- Kiểm tra policy tại Orders API và đúng resource.
- Kiểm tra scopes trong ClientRegistration/token đã cấp.
- Nếu cần incremental authorization, bắt đầu luồng consent phù hợp.
- Nếu người dùng không có quyền, trả 403 có ý nghĩa về nghiệp vụ.

**Không xóa token hợp lệ chỉ vì thiếu scope**, nếu handler mặc định và policy không yêu cầu. Không tự gắn authority ADMIN hoặc chỉnh JWT payload ở Client.

## 18. HTTP 5xx, gateway error và lỗi mạng

Những loại lỗi:

~~~text
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
TCP connection refused
DNS resolution failure
TLS handshake failure
Read/response timeout
~~~

cần được phân biệt vì không phải lỗi nào cũng retry được.

| Lỗi | Dấu hiệu | Hành động |
|---|---|---|
| 502 từ gateway | Upstream service thất bại | Có thể retry GET với backoff trong budget |
| 503 service unavailable | Service bảo trì/quá tải | Retry có giới hạn hoặc circuit breaker |
| 504 gateway timeout | Gateway chờ quá hạn | Cân nhắc retry idempotent operation |
| Connection refused | Host/port từ chối kết nối | Có thể retry nhưng kiểm tra routing; tránh loop |
| DNS không phân giải | Sai endpoint hoặc sự cố DNS | Không retry dày; có thể là cấu hình sai |
| TLS cert invalid | Không tin cậy server/CA | Sửa TLS trust, **không** tắt verification và retry liên tục |
| Response timeout | Server chậm hoặc treo | Deadline, pool và retry idempotent có chọn lọc |
| JSON decoding error | Response không đúng schema | Không tự retry như lỗi mạng nếu không có lý do |

**Retry làm tăng tải**, đặc biệt khi nhiều request bị 503 đồng thời. Backoff/jitter giảm đồng bộ thời gian gửi lại, nhưng không thay thế bulkhead, rate limiting và circuit breaker nếu hệ thống cần resilience nâng cao.

## 19. Đọc và chuẩn hóa response error từ downstream

Giả sử Orders API trả body:

~~~json
{
  "code": "ORDER_ALREADY_CANCELLED",
  "message": "Order cannot be cancelled twice",
  "traceId": "order-api-req-8831",
  "details": {
    "orderId": "ORD-100"
  }
}
~~~

Portal có thể cần đọc `code` để hiển thị thông điệp thân thiện, nhưng không nên trả toàn bộ body thô về browser vì có thể chứa nội dung nội bộ hoặc dữ liệu nhạy cảm.

Mô hình chuẩn hóa:

~~~java
public record DownstreamError(
    String code,
    String message,
    String traceId
) {}
~~~

Sau đó một service chuyển:

~~~text
HTTP 409 + code ORDER_ALREADY_CANCELLED
  -> AppBusinessException("Order was already cancelled")

HTTP 403 + insufficient_scope
  -> AppAuthorizationException("Not enough permission")

HTTP 503
  -> AppDependencyUnavailableException("Orders API unavailable")
~~~

**Không dựa duy nhất vào chuỗi message** của downstream để phân quyền hoặc retry. Dùng status, error code đã được API contract định nghĩa và ngữ cảnh request.

### 19.1. Kiểm soát body size khi parse lỗi

Đừng không giới hạn:

~~~java
// Nguy hiểm nếu response body quá lớn hoặc chứa dữ liệu nhạy cảm:
response.bodyToMono(String.class)
    .doOnNext(body -> log.error("Downstream body={}", body));
~~~

WebClient có giới hạn buffer/codec, có thể cấu hình:

~~~java
WebClient client = WebClient.builder()
    .codecs(codecs ->
        codecs.defaultCodecs().maxInMemorySize(256 * 1024))
    .build();
~~~

Ví dụ giới hạn **256 KiB** chỉ dành cho trường hợp cần buffer nội dung. Nếu response lớn hợp lệ, hãy dùng streaming hoặc pagination thay vì tăng buffer vô hạn. Lỗi `DataBufferLimitException` là dấu hiệu cần xét lại kích thước response/codec.

### 19.2. JSON schema có thể thay đổi

Một API có thể thêm field mới hoặc thay đổi cách biểu diễn lỗi:

~~~json
{"error":"service_unavailable"}
~~~

so với:

~~~json
{"code":"SERVICE_UNAVAILABLE","message":"Please retry later"}
~~~

Portal cần fallback khi không decode được error body. **Không biến decode exception thành HTTP 200 với danh sách trống**, vì cách đó che mất sự cố downstream và dẫn tới quyết định nghiệp vụ sai.

## 20. Xử lý response 204, 304 và body rỗng

Các endpoint khác nhau có thể trả:

- **200 OK** với JSON body.
- **201 Created** với `Location` header.
- **202 Accepted** khi request đã được nhận để xử lý bất đồng bộ.
- **204 No Content** sau thao tác không trả body.
- **304 Not Modified** cho conditional GET.
- **404 Not Found** khi một resource cụ thể không có.

Đừng mặc định mọi response thành công đều có JSON object.

Ví dụ DELETE:

~~~java
Mono<Void> result = ordersWebClient.delete()
    .uri("/api/orders/{id}", orderId)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Đây là mô hình đọc response không có body, **không có retry mặc định**. Nếu endpoint trả 202 với job ID, cần đọc header/body theo contract và theo dõi tiến trình thay vì suy rằng xóa đã hoàn tất.

### 20.1. Response body được tiêu thụ một lần

Trong `exchangeToMono()`, nếu một nhánh đọc `bodyToMono(ErrorDto.class)`, không nên cố tiếp tục đọc toàn bộ raw body lần nữa. Dữ liệu HTTP response thường là stream tiêu thụ một lần.

Nếu cần log lỗi có cấu trúc và trả lỗi nghiệp vụ, hãy parse một lần thành DTO phù hợp rồi trích **trường được phép log**. Đừng bật debug logging ghi raw token, PII và mọi response body.

## 21. Phân biệt WebClientResponseException, WebClientRequestException và TimeoutException

Ba nhóm lỗi giúp điều tra nguyên nhân:

| Exception/nhóm | Nguồn thường gặp | Có HTTP status từ downstream? |
|---|---|---|
| `WebClientResponseException` | `retrieve()` nhận 4xx/5xx và tạo error signal | **Có**, đọc `getStatusCode()`, headers |
| `WebClientRequestException` | I/O request, DNS, connect/TLS và lỗi transport | **Không nhất thiết**, request có thể chưa có response |
| `TimeoutException` từ Reactor `timeout()` | Pipeline vượt thời hạn đã đặt | **Không chắc**, có thể xảy ra ở nhiều giai đoạn |
| `DataBufferLimitException` | Body vượt giới hạn buffering codec | Có thể response đã nhận nhưng decode không được |
| `OAuth2AuthorizationException` | Client authorization/token endpoint không thành công | Có thể do token exchange trước downstream call |

Đối với `WebClientResponseException`:

~~~java
if (error instanceof WebClientResponseException e) {
    int status = e.getStatusCode().value();
    String requestId =
        e.getHeaders().getFirst("X-Request-ID");
    // Chỉ lưu các trường đã được kiểm soát.
}
~~~

Không gọi `e.getResponseBodyAsString()` rồi log nguyên văn trong production; error body có thể chứa dữ liệu cá nhân hoặc chi tiết hệ thống.

### 21.1. TimeoutException không luôn đồng nghĩa server chưa xử lý

Với một POST:

~~~text
Portal gửi POST /api/orders
Orders API tạo order và commit
Response về chậm, Portal timeout
Portal nghĩ "chưa thành công"
~~~

Nếu retry không có idempotency, có thể tạo hai đơn. Cần xử lý kết quả **không xác định** theo business contract, không tự biến timeout thành “chắc chắn thất bại”.

## 22. Thứ tự timeout, retry, error mapping ảnh hưởng trực tiếp hành vi

Xem hai pipeline:

~~~java
// Pipeline A: Retry khi còn biết status của WebClientResponseException.
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class)
    .retryWhen(retryPolicy)
    .onErrorMap(this::toDomainError);
~~~

~~~java
// Pipeline B: Map lỗi trước retry.
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class)
    .onErrorMap(this::toDomainError)
    .retryWhen(retryPolicy);
~~~

Trong A, `retryPolicy` thấy exception gốc (ví dụ `WebClientResponseException`) và có thể lọc theo HTTP code. Trong B, `retryPolicy` có thể chỉ thấy custom domain error. Muốn B hoạt động phải viết filter phù hợp với custom exception.

### 22.1. Một pipeline khuyến nghị cho GET

~~~text
WebClient GET
  -> retrieve() / decode body
  -> per-attempt timeout
  -> retryWhen(chỉ lỗi transient)
  -> overall deadline
  -> translate lỗi còn lại thành business error
  -> Spring MVC controller trả response phù hợp
~~~

Điều này giúp không biến lỗi 403 thành retryable error do mapping không rõ. Dù vậy, nếu OAuth2 filter làm token refresh, phải tính thêm authorization lifecycle vào timeout và retry policy.

### 22.2. Timeout làm mất thông tin lỗi nào?

Nếu overall deadline hết trước khi downstream trả 503, pipeline chỉ có thể biết **đã quá thời gian**, không thể suy luận HTTP status mà server chưa trả. Nếu user hủy request, cancellation cũng có thể dừng việc đọc response; cần instrument tracing an toàn để biết ở đâu hết budget.

## 23. Mapping lỗi cho Spring MVC controller

Một gateway có thể chuyển WebClient exception thành domain exception, sau đó controller/advice trả JSON phù hợp cho frontend.

Ví dụ:

~~~java
package com.example.portal.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PortalErrorAdvice {

    @ExceptionHandler(DownstreamUnavailableException.class)
    ResponseEntity<ApiError> unavailable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("ORDERS_UNAVAILABLE"));
    }

    @ExceptionHandler(DownstreamRateLimitedException.class)
    ResponseEntity<ApiError> rateLimited() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("ORDERS_RATE_LIMITED"));
    }

    @ExceptionHandler(DownstreamPermissionException.class)
    ResponseEntity<ApiError> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .body(new ApiError("ORDERS_FORBIDDEN"));
    }

    public record ApiError(String code) {}
}
~~~

Những exception tên `DownstreamUnavailableException`, `DownstreamRateLimitedException` và `DownstreamPermissionException` là **domain exceptions của ứng dụng**, không phải Spring built-ins. Các mã 502/503/403 minh họa **một API contract**, không phải mapping bắt buộc cho mọi BFF.

**Phân biệt:**

- 401 từ Portal khi browser không có session/authentication.
- 401 từ Orders API do Bearer token Portal gửi bị từ chối.
- 403 từ Orders API do scope/resource permission.

Không trả nguyên upstream OAuth2 challenge/secret/error body ra browser một cách vô điều kiện. Nếu frontend cần reauthorization, định nghĩa một error code/hành động riêng.

### 23.1. Controller trả Mono trong MVC

~~~java
package com.example.portal.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrdersReadGateway gateway;

    public OrdersController(OrdersReadGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/bff/orders")
    public Mono<String> listOrders() {
        return gateway.listOrders();
    }
}
~~~

Spring MVC có hỗ trợ reactive return types qua cơ chế async integration. Tuy nhiên việc giữ **Servlet request context / SecurityContext ThreadLocal** xuyên suốt các bước bất đồng bộ phải được cân nhắc, nhất là khi `ServletOAuth2AuthorizedClientExchangeFilterFunction` cần Authentication và Servlet request/response.

Nếu integration dựa vào request attributes/ThreadLocal tại **thời điểm subscription** mà subscription xảy ra sau khi Servlet request thread kết thúc, context có thể không còn ở vị trí đó. Khi đó cần truyền các attribute cần thiết qua **cơ chế được Spring Security hỗ trợ cho Servlet WebClient** hoặc chuẩn bị authorized client ở ranh giới Servlet đã xác thực. Không đọc `SecurityContextHolder` ở một Reactor scheduler tùy ý rồi mong context tự được truyền.

## 24. Context propagation khi WebClient chạy bất đồng bộ

Đây là điểm đặc thù của **WebClient trong ứng dụng Servlet**.

### 24.1. Vì sao dễ mất context?

~~~text
Servlet Thread:
  SecurityContextHolder có Authentication
  HttpServletRequest có session, principal
      |
      v
Tạo Mono<WebClientResponse>
      |
      v
Mono được subscribe hoặc chuyển scheduler khác
      |
      v
Thread khác:
  ThreadLocal SecurityContext có thể không hiện diện
~~~

Spring Security filter cho WebClient Servlet có thể lấy `Authentication`/Servlet request từ ngữ cảnh phù hợp theo API integration của nó. Khi chạy async hoặc trong scheduled job, phải xác định cách truyền context.

### 24.2. Không “sửa nhanh” bằng một principal name tùy ý

Sai:

~~~java
// Không lấy principal từ user input để chọn token của người khác:
.attributes(ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId(userSuppliedRegistrationId))
~~~

và không truyền `principalName=admin` chỉ để load token admin từ store.

Đối với request thay mặt người dùng, authorized client phải gắn với **Authentication đã được xác minh**. Đối với scheduled job, chọn manager dựa trên `OAuth2AuthorizedClientService` và service principal được quản lý riêng.

### 24.3. .block() trong MVC

~~~java
// Có thể dùng tại một ranh giới blocking của ứng dụng MVC
// sau khi đã thiết kế timeout, số thread và context phù hợp:
OrdersPage page = callMono.block(Duration.ofSeconds(6));
~~~

Nhưng:

- Mỗi request có thể chiếm một Servlet thread trong thời gian đợi.
- Không block trong Reactor Netty event loop.
- Không gọi `.block()` lồng nhau trong `map`/`flatMap` đang chạy trên event-loop.
- `.block(Duration)` có thể tạo một deadline riêng; tránh cấu hình deadline mâu thuẫn với `.timeout(...)`.
- Nếu cần throughput lớn, cân nhắc MVC async return types hoặc chuyển kiến trúc sang WebFlux có chủ đích, chứ không chỉ đổi tên HTTP client.

## 25. Timeout và retry khi dùng nhiều downstream services

Giả sử Portal gọi đồng thời:

~~~text
Orders API   -> lấy danh sách đơn
Inventory API -> kiểm tra tồn kho
Pricing API  -> tính giá
~~~

Nếu mỗi service có 3 attempts và timeout 5 giây, tổng thời gian/công suất có thể vượt ngân sách của HTTP request. Một số vấn đề:

- **Fan-out amplification:** một request browser tạo nhiều requests backend.
- **Retry amplification:** mỗi downstream lại retry, có thể nhân tải nhiều lần.
- **Cascade failure:** một API chậm giữ connection/thread, kéo sập các API khác.
- **Cancellation:** khi một nhánh lỗi hoặc overall timeout, các nhánh khác có thể bị hủy; server có thể vẫn đã xử lý.

Chính sách:

1. Có **overall deadline** ở request BFF và budget riêng theo downstream.
2. Giới hạn **concurrency** qua connection pool/bulkhead.
3. Retry chỉ ở một tầng được chủ đích; tránh HTTP client, gateway và service cùng retry độc lập.
4. Dùng **fallback** chỉ khi dữ liệu cũ/thiếu là hợp lệ về nghiệp vụ và được hiển thị rõ.
5. Không trả thành công giả nếu dữ liệu bắt buộc thiếu.

Ví dụ fallback **có chủ đích**:

~~~java
// Được phép nếu nội dung “gợi ý sản phẩm” là optional:
return recommendationsClient.get()
    .uri("/api/recommendations")
    .retrieve()
    .bodyToMono(RecommendationList.class)
    .onErrorReturn(RecommendationList.empty());
~~~

**Không áp dụng onErrorReturn(empty) cho dữ liệu đơn hàng/thanh toán có yêu cầu nhất quán**, vì che mất lỗi sẽ tạo quyết định sai.

## 26. Connection pool và backpressure

WebClient non-blocking không có nghĩa số kết nối tới downstream vô hạn.

~~~java
ConnectionProvider pool = ConnectionProvider.builder("orders-pool")
    .maxConnections(100)
    .pendingAcquireTimeout(Duration.ofSeconds(1))
    .build();
~~~

Ý nghĩa:

- `maxConnections(100)` giới hạn số connection đang mở theo pool policy.
- `pendingAcquireTimeout(1s)` giới hạn thời gian chờ lấy connection khi pool bận.
- Khi hệ thống quá tải, request có thể thất bại **trước khi gửi tới Orders API**.

Retry những lỗi pool exhausted với tần suất cao có thể làm nghẽn nặng hơn. Cần:

- Đo queue latency và pending acquires.
- Giới hạn caller concurrency.
- Dùng backpressure/bulkhead/rate limiting phù hợp.
- Thêm timeout cho tổng yêu cầu.
- Tránh tạo một Reactor Netty connection pool riêng cho mỗi request hoặc mỗi user.

Tăng maxConnections không phải lúc nào cũng giải quyết được vì downstream và gateway cũng có giới hạn.

## 27. Observability: biết lỗi ở đâu mà không lộ dữ liệu

Một request tới Orders API có thể có:

~~~text
Trace ID của Portal: portal-req-192
Downstream request ID: orders-req-202
Registration: company
HTTP method: GET
Route: /api/orders
Attempt: 1/3
Status: 503
Latency: 890 ms
Retry decision: yes
~~~

Các trường phù hợp để đo:

| Trường/metric | Công dụng |
|---|---|
| Downstream service name | Khoanh vùng phụ thuộc |
| Route template, không phải URL đầy query PII | Nhóm request theo API |
| HTTP status / OAuth2 error code | Phân loại lỗi |
| Connection/pool waiting time | Phát hiện nghẽn local |
| Token refresh attempted/succeeded | Phân biệt token endpoint với Resource Server |
| Retry count/backoff | Xem amplification |
| Deadline exceeded | Điều tra timeout |
| Correlation/trace ID | Nối logs ở các services |
| Registration ID đã allowlist | Xác định OAuth client được dùng |

**Không log:**

~~~text
Authorization: Bearer <real-access-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
Cookie: JSESSIONID=<real-session-id>
id_token=<real-id-token>
authorization_code=<real-code>
~~~

Không bật HTTP wiretap/log toàn bộ request/response body trong production chỉ để tìm status. Body lỗi có thể chứa email, order ID, thông tin cá nhân hoặc nội dung từ hệ thống khác.

### 27.1. Metrics nên phân biệt các nhóm lỗi

~~~text
downstream.http.errors{service=orders,status=503}
downstream.http.errors{service=orders,status=403}
downstream.http.timeout{service=orders}
oauth2.client.refresh.failures{registration=company,error=invalid_grant}
downstream.http.retries{service=orders,reason=503}
~~~

Các tên trên là ví dụ instrument tùy chỉnh, không phải mặc định tất cả đều được Spring Boot phát ra. Tránh label có cardinality quá cao như token value, user email hoặc order ID trên metric.

## 28. Testing timeout, retry và response handling

Việc test nên dùng **mock HTTP server** và fake authorized client, không gọi IdP/Orders API production.

| Test case | Mô phỏng | Kết quả mong đợi |
|---|---|---|
| GET 200 JSON hợp lệ | Trả OrdersPage | Decode đúng DTO |
| GET 204 | Không có response body | Xử lý empty theo contract |
| GET 404 | Order không có | `Mono.empty()` chỉ khi API định nghĩa như vậy |
| GET 429 | Retry-After hợp lệ | Giới hạn chờ và overall deadline |
| GET 503, sau đó 200 | Lỗi transient | Retry có giới hạn, trả kết quả thành công |
| GET 503 liên tục | Luôn lỗi | Dừng sau max retries/deadline |
| GET 403 | insufficient_scope | Không retry; giữ semantic thiếu quyền |
| GET 401 | invalid_token | OAuth2 failure handling, không retry 10 lần mù |
| POST tạo đơn timeout | Server có thể đã commit | Không tự retry nếu không có idempotency |
| Connect timeout | Host không đáp | Lỗi transport được phân loại đúng |
| Response body vượt buffer | Payload lớn | Nhận DataBufferLimitException hoặc streaming policy |
| JSON sai schema | Decoder lỗi | Không biến thành 200 empty |
| Token refresh lỗi | invalid_grant | Manager failure được xử lý riêng với downstream 503 |
| Hai principals | Token của user A và user B | Không đính nhầm token |
| Async context mất | Subscribe trên thread khác | OAuth2 filter có context đúng hoặc fail an toàn |

### 28.1. StepVerifier với fake Publisher

Ví dụ logic retry không phụ thuộc HTTP thật:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryPolicyTest {

    @Test
    void transientFailureIsRetriedThenSucceeds() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            int attempt = calls.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(
                    new TemporaryDownstreamException("temporary"));
            }
            return Mono.just("OK");
        });

        Mono<String> result = source.retryWhen(
            Retry.backoff(2, Duration.ofMillis(10))
                .filter(e -> e instanceof TemporaryDownstreamException)
        );

        StepVerifier.create(result)
            .expectNext("OK")
            .verifyComplete();

        assertEquals(3, calls.get());
    }

    static class TemporaryDownstreamException extends RuntimeException {
        TemporaryDownstreamException(String message) {
            super(message);
        }
    }
}
~~~

Ví dụ minh họa `Retry.backoff(2,...)` nghĩa là tối đa **hai retries**. Trong test thực tế nên dùng **virtual time** cho những lịch backoff dài để test nhanh và ổn định.

### 28.2. Mock HTTP server để test response

Cần kiểm tra ít nhất:

~~~text
Attempt 1: GET /api/orders -> HTTP 503
Attempt 2: GET /api/orders -> HTTP 200 với JSON
Result: OrdersPage hợp lệ
HTTP requests observed: 2
Authorization header: Bearer TEST_ACCESS_TOKEN
Token không xuất hiện trong log
~~~

Để kiểm tra OAuth2 integration, có thể stub `OAuth2AuthorizedClientManager` trả `OAuth2AuthorizedClient` giả, sau đó xác minh WebClient thực sự đính Bearer token đúng registration khi gọi mock server.

**Test riêng integration wiring và OAuth2 failure handling**, không chỉ unit test hàm retry. Có `@Bean WebClient` trong Spring context không chứng minh controller/service dùng đúng bean có OAuth2 filter và timeout đã cấu hình.

### 28.3. Test timeout không chỉ bằng sleep tùy ý

Với HTTP integration, mock server có thể cố ý giữ connection hoặc trì hoãn response để kiểm tra **response timeout** của Reactor Netty. Với Reactor operator `timeout()` và retry backoff, `StepVerifier.withVirtualTime` giúp test logic thời gian mà không chờ thật khi source/operator hỗ trợ virtual scheduler.

Đừng dùng sleep dài trong CI ở hàng chục tests vì dễ flaky và làm test suite chậm.

## 29. Vận hành khi downstream đang gặp sự cố

Khi Orders API trả 503 hàng loạt:

1. **Xác nhận lỗi downstream**, không suy ngay thành người dùng logout hay token hết hạn.
2. Xem status/latency/tracing theo route và service.
3. Kiểm tra connection pool, pending acquisitions và giới hạn concurrency.
4. Xem retry amplification; giảm retry nếu tải upstream đang quá lớn.
5. Áp dụng circuit breaker/rate limiter nếu kiến trúc đã có và được kiểm soát.
6. Trả lỗi phù hợp cho UI; nếu có cached data hợp lệ thì ghi rõ độ mới, nguồn và phạm vi quyền của người dùng.
7. Chỉ xử lý OAuth2 authorized client nếu có **bằng chứng lỗi token**.

Một service không phản hồi **không phải** lý do hợp lệ để xóa access/refresh token khỏi database. Xóa token mù sẽ khiến lượng yêu cầu tới Authorization Server tăng, có thể gây thêm một sự cố thứ hai.

## 30. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Cách khoanh vùng |
|---|---|---|
| MVC endpoint đứng lâu | Chưa có timeout, nhiều retries hoặc `block()` trên Servlet thread | Kiểm tra per-attempt/overall deadline, thread pool |
| Connect timeout | DNS/firewall/routing/host chậm | Kiểm tra egress, connection pool và TCP timeout |
| Response timeout | API quá chậm hoặc stream bị treo | Kiểm tra downstream latency và responseTimeout |
| 503 vẫn retry nhiều lần rồi chậm hơn | Retry vượt ngân sách, không có jitter | Giới hạn attempts, backoff và overall timeout |
| 401 liên tục dù user login | Access token invalid hoặc lỗi gateway | Kiểm tra Bearer challenge và authorized-client lifecycle |
| 403 sau refresh | Token thiếu scope/quyền | Xem Resource Server policy, không retry mù |
| 429 vẫn tăng tải | Retry không tôn trọng rate limit | Điều phối Retry-After/backoff/budget |
| POST tạo hai orders | Retry non-idempotent mà không có idempotency key | Sửa API contract và deduplication |
| JSON decode fail | Schema thay đổi hoặc content type sai | Kiểm tra response có giới hạn, fallback error mapping |
| 404 bị trả về 200 với empty list | Mapping `onStatus(Mono.empty())` sai ngữ nghĩa | Dùng exchangeToMono theo contract |
| DataBufferLimitException | Body quá lớn so với codec buffer | Pagination/streaming hoặc giới hạn phù hợp |
| Token không được đính ở async thread | Servlet SecurityContext/request context không được truyền | Kiểm tra OAuth2 filter attributes và context |
| Token gửi tới hostname khác | WebClient cho phép absolute URL/redirect không kiểm soát | Restrict destination/registration |
| Retry policy không bắt 503 nữa | `onStatus` đổi exception thành custom type | Đảm bảo retry filter hiểu type mới |
| HTTP transport timeout không hiệu lực | Cấu hình nhầm WebClient hoặc Netty connector | Xác nhận bean thực sự được inject |
| Token endpoint timeout không đổi | Đang cấu hình Orders WebClient, không phải token WebClient | Cấu hình transport của token-response client riêng |
| API lỗi 500 nhưng authorized client bị xóa | Failure handler xóa theo mọi response | Chỉ cleanup lỗi Bearer/OAuth2 phù hợp |

**Lộ trình điều tra:** xác định lần lượt **Servlet session → OAuth2 manager/token endpoint → HTTP connector → Resource Server response → decoder → retry policy → BFF error mapping**.

## 31. Những anti-pattern cần tránh

**1. Gọi `retryWhen(...)` cho mọi HTTP request** mà không xét HTTP method, idempotency và loại lỗi.

**2. Dùng `onErrorReturn(emptyList)` cho dữ liệu bắt buộc.** Điều này biến service outage thành dữ liệu “không có đơn hàng”, gây quyết định nghiệp vụ sai.

**3. Chỉ đặt connect timeout.** Server có thể kết nối thành công nhưng treo ở response; cần response/overall timeout.

**4. Đặt timeout 30 giây trong khi gateway chỉ đợi 5 giây.** Nhiều request sẽ tiếp tục chạy sau khi caller đã bỏ đi.

**5. Retry 401 invalid_token như 503.** Cần xử lý authorized client, refresh hoặc reauthorization thay vì phát lại cùng token nhiều lần.

**6. Xóa authorized client vì 403 insufficient_scope.** Token vẫn có thể hợp lệ cho thao tác khác.

**7. Dùng WebClient OAuth2 filter của WebFlux trong ứng dụng Servlet sai manager.** Servlet cần integration tương ứng và principal/session context phù hợp.

**8. Gọi `.block()` bên trong Reactor event-loop.** Có thể làm giảm thông lượng hoặc phát sinh lỗi blocking không cho phép.

**9. Log toàn bộ request/response hoặc Bearer header.** Nguy cơ lộ token và dữ liệu cá nhân.

**10. Dùng raw error message từ API như thông báo gửi browser.** Error body không phải lúc nào cũng được phép công bố.

**11. Retry POST sau timeout mà không có idempotency contract.** Có thể lặp giao dịch.

**12. Chỉ test HTTP status mà không test thứ tự retry/timeout/error mapping.** Pipeline operator order có thể thay đổi kết quả.

## 32. Bài tập áp dụng

### Bài tập 1 — Chọn timeout

Một WebClient chỉ được cấu hình:

~~~java
HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

**Câu hỏi:** Vì sao API vẫn có thể chờ lâu sau khi TCP connection đã thiết lập?

**Hướng giải:** Connect timeout chỉ giới hạn thời gian tạo TCP connection; cần response timeout và/hoặc overall reactive deadline để giới hạn giai đoạn server trả dữ liệu.

### Bài tập 2 — Kiểm tra retry attempts

~~~java
Retry.backoff(2, Duration.ofMillis(200))
~~~

**Câu hỏi:** Số attempts tối đa là bao nhiêu?

**Hướng giải:** Một lần đầu và **tối đa hai retries**, tổng cộng **ba attempts** nếu luôn gặp lỗi được phép retry và deadline cho phép.

### Bài tập 3 — 401 và 403

~~~text
GET /api/orders -> 401 Bearer invalid_token
DELETE /api/orders/42 -> 403 Bearer insufficient_scope
~~~

**Câu hỏi:** Có nên retry hoặc xóa authorized client giống nhau cho hai lỗi?

**Hướng giải:** Không. `invalid_token` có thể cần cleanup/re-authorization, còn `insufficient_scope` là thiếu quyền; token vẫn có thể dùng cho API khác.

### Bài tập 4 — Retry POST sau network timeout

Portal gửi POST tạo đơn hàng. Downstream đã commit nhưng Portal không nhận response.

**Câu hỏi:** Chỉ thêm `retryWhen(3)` có an toàn không?

**Hướng giải:** Không. Cần idempotency key/operation ID và downstream deduplication hoặc API kiểm tra trạng thái giao dịch. Timeout không xác nhận request chưa được xử lý.

### Bài tập 5 — Mapping 404 sai

~~~java
.retrieve()
.onStatus(status -> status.value() == 404, response -> Mono.empty())
.bodyToMono(OrderDto.class)
~~~

**Câu hỏi:** 404 có tự trở thành `Mono.empty()` ở cuối không?

**Hướng giải:** Không được đảm bảo; `onStatus(..., Mono.empty())` nghĩa không xử lý 404 là lỗi, rồi decoder vẫn xử lý response. Sử dụng `exchangeToMono()` để trả `Mono.empty()` đúng nghiệp vụ.

### Bài tập 6 — Retry không còn hoạt động sau onStatus

Gateway map mọi 503 thành `DownstreamUnavailableException` rồi retry policy chỉ lọc `WebClientResponseException`.

**Câu hỏi:** Vì sao không retry?

**Hướng giải:** Exception đã đổi loại trước retry. Đặt retry trước error mapping hoặc cho retry filter nhận đúng custom exception, giữ nguyên ngữ nghĩa và status cần thiết.

### Bài tập 7 — ThreadLocal và WebClient Servlet

Spring MVC controller trả `Mono<OrdersPage>`, nhưng subscription thực hiện ở thread khác và OAuth2 filter không lấy được principal.

**Câu hỏi:** Có nên đặt `principalName="admin"` để giải quyết?

**Hướng giải:** Không. Cần cấu hình truyền context WebClient Servlet đúng API hoặc resolve authorized client tại một ranh giới request đã authenticated, không tự dùng principal tùy ý hoặc token của user khác.

### Bài tập 8 — 429 với Retry-After lớn

Orders API trả `429 Retry-After: 120`, nhưng Portal chỉ có tổng deadline 5 giây.

**Câu hỏi:** Có nên giữ request chờ 120 giây?

**Hướng giải:** Không. Nên dừng trong budget, trả lỗi thích hợp hoặc chuyển tác vụ sang workflow bất đồng bộ nếu business cho phép; không làm quá tải server.

## 33. Checklist triển khai WebClient trên Servlet

| Câu hỏi | Điểm cần đảm bảo |
|---|---|
| Web application thực sự là Servlet? | Dùng `SecurityFilterChain/HttpSecurity` |
| OAuth2 integration phù hợp stack? | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| WebClient có dùng đúng manager? | Được truyền vào constructor/filter, không chỉ khai báo bean |
| Registration ID có rõ ràng không? | Chỉ định theo Orders API, không lấy tùy ý từ user input |
| Access token được bảo vệ không? | Không trả về browser, không log Bearer/refresh token |
| URL/redirect có allowlist không? | Không gửi token sang host ngoài phạm vi |
| TCP connect timeout có không? | Có, phù hợp môi trường |
| Response timeout có không? | Có, khác connect timeout |
| Overall deadline có không? | Có, bao trùm retries và latency budget |
| Retry lỗi gì? | Chỉ transient theo whitelist; không retry 401/403 mù |
| Retry mấy lần? | Giới hạn attempts, backoff, jitter |
| Có tôn trọng 429/Retry-After không? | Có budget/rate limit policy |
| POST có idempotency contract không? | Không retry tùy ý |
| Có phân tích status/header/body? | `retrieve/onStatus/toEntity/exchangeToMono` đúng ngữ nghĩa |
| Body rỗng/204/404/304 xử lý thế nào? | Theo API contract |
| Body lớn có được kiểm soát? | Buffer limit, pagination/streaming |
| Error mapping có giữ status/reason không? | Retry filter nhận đúng loại exception |
| MVC async có giữ principal/context không? | Có integration/context propagation phù hợp |
| Có connection pool và giới hạn tải? | Có max connections/pending acquire/metrics |
| Logs/metrics có an toàn? | Không raw token, cookie, PII |
| Có tests 401/403/429/503/timeout/retry không? | Có, kể cả idempotency và OAuth2 wiring |

## 34. Tổng kết

Khi sử dụng **WebClient trên Spring MVC/Servlet** trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, cần phân biệt **session đăng nhập**, **authorized client/token**, **HTTP transport**, **retry policy** và **response của Resource Server**. `ServletOAuth2AuthorizedClientExchangeFilterFunction` giúp WebClient lấy Bearer token qua `OAuth2AuthorizedClientManager`, nhưng không tự chọn timeout hoặc retry an toàn cho từng nghiệp vụ.

**Timeout** nên được thiết kế theo nhiều tầng: connection pool acquisition, TCP connect, response timeout, per-attempt timeout và overall deadline. **Retry** chỉ phù hợp với lỗi transient, thao tác được phép replay và ngân sách thời gian còn lại; luôn có max attempts, backoff/jitter và chú ý `Retry-After`. Đặc biệt, không retry POST tạo tác dụng phụ nếu không có cơ chế idempotency được downstream bảo đảm.

Để **phân tích response**, sử dụng `retrieve()` cho trường hợp thông thường, `onStatus()` để ánh xạ lỗi, `toEntity()` khi cần headers/status và `exchangeToMono()` khi phải kiểm soát từng nhánh response/body. Cần phân biệt **401 invalid_token**, **403 insufficient_scope**, **429 rate limit** và **5xx/network failure**, tránh xóa token hoặc logout user vì lỗi không liên quan đến OAuth2.

Một cấu hình bền vững không chỉ “thử lại khi lỗi”, mà phải bảo đảm **đúng principal/registration**, **không lộ token**, **đủ ngữ cảnh Servlet**, **không vượt thời gian cho phép**, **không nhân đôi tác vụ nghiệp vụ** và **có thông tin chẩn đoán an toàn**. Đó là nền tảng để Portal gọi downstream ổn định và bảo mật dù sử dụng HTTP client Reactive bên trong một ứng dụng Servlet.
