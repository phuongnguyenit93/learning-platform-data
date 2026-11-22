# 10.13. Phân biệt cấu hình token client trên Servlet và Reactive

## 1. Bài toán: cùng một token endpoint nhưng hai cách tích hợp trong Spring Security

Một ứng dụng **Spring Security OAuth 2.0/OIDC Client** thường phải liên hệ với **token endpoint** của Authorization Server để:

1. Đổi **authorization code** lấy token sau khi browser được chuyển hướng về callback.
2. Dùng **refresh token** để xin access token mới khi có quyền và điều kiện phù hợp.
3. Dùng grant **client_credentials** để lấy access token cho một dịch vụ gọi API bằng danh tính của chính client.

Trên **Spring MVC/Servlet** và **Spring WebFlux/Reactive**, yêu cầu giao thức gửi tới Authorization Server về cơ bản giống nhau: HTTP POST qua TLS, grant type, credential của client và các tham số tương ứng. Tuy nhiên, **kiểu client HTTP**, **interface token-response client**, **cách xử lý bất đồng bộ** và **điểm cấu hình vào security chain** khác nhau.

Điểm quan trọng nhất:

- **Servlet** thường dùng `OAuth2AccessTokenResponseClient<T>` để nhận kết quả trực tiếp kiểu `OAuth2AccessTokenResponse`. HTTP client hiện đại có thể dựa trên Spring `RestClient`.
- **Reactive** dùng `ReactiveOAuth2AccessTokenResponseClient<T>`, trả `Mono<OAuth2AccessTokenResponse>`; implementation thông dụng dựa trên `WebClient`.

Không thể thay một token client Servlet vào nơi đòi token client Reactive chỉ vì cả hai được gọi là “OAuth2 Client”. Bài này giải thích cơ chế, API, ví dụ cấu hình và các khác biệt khi vận hành.

> Phạm vi ví dụ: Java 17+, **Spring Security 6**, Spring Boot 3. Một số lớp dựa trên `RestClient` xuất hiện ở các nhánh **Spring Security 6.4+**; phiên bản cũ dùng lớp `Default*TokenResponseClient` dựa trên `RestOperations`. Hãy sử dụng API đúng với phiên bản Spring Security mà dự án thực sự quản lý; không sao chép package/method của hai thế hệ vào cùng ví dụ.

## 2. Token endpoint nằm ở bước nào của Authorization Code Flow?

Giả sử **Employee Portal** cho người dùng đăng nhập qua **Company IdP** và sau đó gọi **Orders API** thay mặt người dùng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant P as Employee Portal (OAuth2 Client)
    participant AS as Authorization Server / OIDC Provider
    participant API as Orders API (Resource Server)

    U->>B: Nhấn Đăng nhập công ty
    B->>P: GET /oauth2/authorization/company
    P-->>B: Redirect sang authorization endpoint
    B->>AS: Authorization request với state, redirect_uri, ...
    AS->>U: Xác thực và consent khi cần
    AS-->>B: Redirect callback với code và state
    B->>P: GET /login/oauth2/code/company?code=...&state=...
    P->>P: Xác minh callback và request tương ứng
    P->>AS: POST token endpoint, grant_type=authorization_code
    AS-->>P: access_token (+ id_token / refresh_token nếu cấp)
    P->>P: Xác thực OIDC login, lưu SecurityContext/authorized client
    B->>P: Yêu cầu trang đơn hàng qua session
    P->>API: Authorization: Bearer <access_token>
    API-->>P: Dữ liệu được cấp phép
    P-->>B: Kết quả
~~~

**Token endpoint** và **authorization endpoint** là hai endpoint khác nhau:

| Endpoint | Caller | Giao tiếp điển hình | Trách nhiệm |
|---|---|---|---|
| **Authorization endpoint** | Trình duyệt thông qua redirect từ Portal | Front-channel GET, tương tác với người dùng | Xác thực, consent và cấp authorization code |
| **Token endpoint** | Backend của Portal | Back-channel HTTPS POST | Đổi code hoặc grant khác lấy token |
| **Orders API** | Portal sau khi có token | HTTP request với Bearer header | Xác minh access token và quyền tài nguyên |

**Token client** trong bài là thành phần thực hiện **HTTP request tới token endpoint**. Nó **không phải** OAuth2 Client registration, login form, redirect resolver hoặc HTTP client dùng để gọi Orders API.

## 3. Những gì giống nhau giữa Servlet và Reactive

Dù dùng Servlet hay Reactive, cấu hình OAuth 2.0 Client cần những dữ liệu tương tự:

- **client registration ID**: tên nội bộ, ví dụ `company`.
- **client-id**, **client-secret** hoặc phương thức xác thực client khác theo đăng ký IdP.
- **authorization-grant-type**: `authorization_code`, `client_credentials`, ...
- **redirect-uri**: callback đã đăng ký với Authorization Server, khi grant cần redirect.
- **provider.issuer-uri** hoặc các endpoint được cấu hình rõ khi provider không hỗ trợ discovery.
- **scope**: các quyền ứng dụng yêu cầu.

Giao thức vẫn phải tuân thủ các điều kiện:

1. Sử dụng **TLS** phù hợp khi gửi credential, authorization code, refresh token và nhận token.
2. Gửi **client authentication** theo cách IdP chấp nhận, ví dụ `client_secret_basic`.
3. Nếu dùng PKCE, gửi **code_verifier** ở token request tương ứng với code challenge đã gửi trước đó.
4. Nếu Authorization Server yêu cầu **redirect_uri** ở token request, phải giữ giá trị nhất quán với authorization request.
5. Chỉ chấp nhận token response hợp lệ, sau đó bảo vệ access token, refresh token và ID Token.

Điểm **khác nhau** nằm ở cách các thành phần Java thực hiện những bước trên.

## 4. Bảng so sánh nhanh

| Tiêu chí | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| HTTP request hạ tầng | `HttpServletRequest` | `ServerWebExchange` |
| Token-response interface | `OAuth2AccessTokenResponseClient<T>` | `ReactiveOAuth2AccessTokenResponseClient<T>` |
| Kết quả API token client | `OAuth2AccessTokenResponse` | `Mono<OAuth2AccessTokenResponse>` |
| Authorization Code implementation | `RestClientAuthorizationCodeTokenResponseClient` (6.4+) hoặc lớp Default đời cũ | `WebClientReactiveAuthorizationCodeTokenResponseClient` |
| Client Credentials implementation | `RestClientClientCredentialsTokenResponseClient` (6.4+) hoặc Default đời cũ | `WebClientReactiveClientCredentialsTokenResponseClient` |
| Refresh Token implementation | `RestClientRefreshTokenTokenResponseClient` (6.4+) hoặc Default đời cũ | `WebClientReactiveRefreshTokenTokenResponseClient` |
| HTTP engine thông dụng | `RestClient` / `RestOperations` | `WebClient` |
| Authorized-client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Client registrations | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Token/result processing | Đồng bộ theo lời gọi | Non-blocking theo reactive pipeline |
| Cấu hình OAuth2 Login | `http.oauth2Login(...)` | `http.oauth2Login(...)` trên ServerHttpSecurity |
| Cách phát triển | Gọi đồng bộ trong thread của ứng dụng | Trả Publisher, không `block()` trên event-loop |

**Lưu ý phiên bản:** tên những lớp `RestClient*TokenResponseClient` trong bảng phù hợp với Spring Security hiện đại; nếu một dự án đang dùng Spring Security 6.2/6.3, cần dùng các implementation có thật ở phiên bản đó (thường `DefaultAuthorizationCodeTokenResponseClient` và họ `Default*`). Không tự viết lại HTTP token exchange chỉ vì API mẫu trên mạng thuộc phiên bản khác.

## 5. Hai interface cốt lõi của token client

### 5.1. Servlet: OAuth2AccessTokenResponseClient

API cốt lõi:

~~~java
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

public interface OAuth2AccessTokenResponseClient<T> {
    OAuth2AccessTokenResponse getTokenResponse(T authorizationGrantRequest);
}
~~~

Trong thực tế, generic `T` thay bằng kiểu grant request, ví dụ:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

Phương thức `getTokenResponse(...)` trả response trực tiếp. HTTP client có thể thực hiện I/O đồng bộ trong lúc trao đổi token. Vì vậy cần quan tâm **timeout**, khả năng kết nối IdP và việc không làm cạn thread pool.

### 5.2. Reactive: ReactiveOAuth2AccessTokenResponseClient

Đối ứng Reactive:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

public interface ReactiveOAuth2AccessTokenResponseClient<T> {
    Mono<OAuth2AccessTokenResponse> getTokenResponse(T authorizationGrantRequest);
}
~~~

`Mono<OAuth2AccessTokenResponse>` là một Publisher biểu diễn việc token response được phát ra sau khi I/O và xử lý hoàn tất. Khi dùng một implementation non-blocking, pipeline có thể tiếp tục mà không giữ một thread chờ network response.

**Không gọi `.block()` trong reactive request-handling thread** để “biến” token client Reactive thành API đồng bộ. Việc chặn event loop làm mất ưu thế non-blocking, có thể gây giảm thông lượng và lỗi trong Reactor khi blocking không được phép.

### 5.3. Hai interface không thay thế cho nhau

Ví dụ sai về mặt kiểu:

~~~java
// Sai: token client đồng bộ không phải reactive token client.
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    tokenClient = new RestClientAuthorizationCodeTokenResponseClient();
~~~

Ở chiều ngược lại cũng sai: trả `Mono` không khớp contract của `OAuth2AccessTokenResponseClient`. Muốn chuyển đổi phải có adapter rõ ràng, nhưng thường **không nên làm như vậy** khi framework đã có implementation riêng cho Servlet và Reactive.

## 6. Ví dụ HTTP token exchange mà cả hai stack cùng thực hiện

Sau khi Portal đã xác minh callback và có authorization code, token request thường có dạng:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-client-credentials>

grant_type=authorization_code&code=<authorization-code>&redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=<pkce-verifier-if-used>
~~~

Phần Authorization Basic minh họa cách confidential client xác thực khi registration dùng `client_secret_basic`. Các provider có thể dùng phương thức khác; request cụ thể phải khớp cấu hình IdP.

Token response thành công có thể là:

~~~json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "id_token": "EXAMPLE_ID_TOKEN_JWT"
}
~~~

Đây chỉ là **dữ liệu minh họa**, không phải token hợp lệ. Trong OIDC, ID Token là dữ liệu riêng cho quá trình xác thực người dùng tại client; access token dùng cho Resource Server. Refresh token và ID Token phụ thuộc grant, scope và chính sách provider.

Ở Servlet, lời gọi token-response client trả về một `OAuth2AccessTokenResponse`. Ở Reactive, token-response client phát ra cùng dạng mô hình response qua `Mono`. **Nội dung HTTP không thay đổi chỉ vì ứng dụng dùng WebFlux.**

## 7. Cấu hình registration dùng chung cho Servlet và Reactive

Spring Boot sử dụng các property OAuth2 Client tương tự ở hai stack:

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
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**company** là registration ID trong ứng dụng; `OIDC_CLIENT_ID` là client ID từ Authorization Server. `OIDC_CLIENT_SECRET` phải được cấp qua nguồn bí mật được bảo vệ ở runtime, không ghi trực tiếp trong Git.

Spring Boot có thể đọc metadata về token endpoint từ issuer qua OIDC/OAuth discovery nếu provider hỗ trợ. Cùng YAML nhưng cách Auto Configuration tạo repository khác theo application type:

~~~text
Servlet application:
  spring.security.oauth2.client.*
     -> ClientRegistrationRepository
     -> Servlet OAuth2 login / authorized client components

Reactive application:
  spring.security.oauth2.client.*
     -> ReactiveClientRegistrationRepository
     -> WebFlux OAuth2 login / reactive authorized client components
~~~

**File YAML không tự chọn Servlet hay Reactive.** Loại ứng dụng phụ thuộc web stack được đưa vào classpath và cách khởi tạo Spring Boot. Nếu cả Spring MVC và WebFlux đều có trên classpath, Spring Boot thông thường ưu tiên **Servlet/MVC** trừ khi được cấu hình rõ khác đi. Vì vậy, chỉ thấy dependency `spring-webflux` hoặc dùng `WebClient` không đủ để kết luận ứng dụng đang chạy reactive security chain.

## 8. Servlet: cấu hình token client cho Authorization Code Flow

### 8.1. Dependency và SecurityFilterChain

Ứng dụng Servlet dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Một OAuth2/OIDC login cơ bản:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Với cấu hình mặc định, Spring Security tự sử dụng một token response client tương thích phiên bản để đổi code lấy token. Bạn **không cần tùy biến** nếu yêu cầu của IdP đã theo chuẩn và các mặc định về HTTP client, timeout và authentication method đáp ứng nhu cầu.

### 8.2. Dùng RestClientAuthorizationCodeTokenResponseClient (Spring Security 6.4+)

Khi cần cấu hình rõ token client trên Servlet:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;

@Configuration
class ServletTokenClientConfig {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    authorizationCodeTokenResponseClient() {
        return new RestClientAuthorizationCodeTokenResponseClient();
    }
}
~~~

Để gắn vào đúng bước token exchange của **OAuth2 Login**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletLoginTokenConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            codeTokenClient
    ) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(codeTokenClient)))
            .build();
    }
}
~~~

Hai đoạn là các thành phần của **một phương án cấu hình**. Trong dự án thật, chỉ giữ **một SecurityFilterChain** áp dụng cho cùng nhóm URL, không đồng thời giữ thêm chain ở mục 8.1 với matcher trùng.

Điểm móc API trên Servlet là:

~~~java
http.oauth2Login(login -> login
    .tokenEndpoint(token -> token
        .accessTokenResponseClient(codeTokenClient))
);
~~~

**tokenEndpoint()** ở đây là DSL cấu hình **bước đổi authorization code lấy token của OAuth2 Login**, không có nghĩa chúng ta đang viết một token endpoint/Authorization Server tại Portal.

### 8.3. Tùy chỉnh RestClient để kiểm soát timeout

Khi cần giới hạn thời gian chờ IdP, có thể tạo `RestClient` với request factory:

~~~java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();
requestFactory.setConnectTimeout(Duration.ofSeconds(3));
requestFactory.setReadTimeout(Duration.ofSeconds(5));

RestClient httpClient = RestClient.builder()
    .requestFactory(requestFactory)
    .build();

RestClientAuthorizationCodeTokenResponseClient tokenClient =
    new RestClientAuthorizationCodeTokenResponseClient();
tokenClient.setRestClient(httpClient);
~~~

Đây là ví dụ cấu hình **HTTP transport**, không phải cấu hình toàn bộ SecurityFilterChain. **Nếu thay HTTP client mặc định** mà provider cần converter hoặc error handler đặc biệt, phải đảm bảo request/response token vẫn được xử lý theo OAuth2. Không tự trả về raw JSON và bỏ qua phần kiểm tra lỗi hay convert token response.

Trong hệ thống thực tế, có thể lựa chọn HTTP transport khác để có connection pooling, TLS trust, mTLS và proxy phù hợp. Cần bảo vệ client secret, authorization code, refresh token và không ghi payload token endpoint vào log.

### 8.4. Nếu dùng Spring Security phiên bản cũ

Một số dự án Spring Security 6.x cũ sử dụng:

~~~java
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;

var tokenClient = new DefaultAuthorizationCodeTokenResponseClient();
~~~

Lớp đời cũ dựa trên `RestOperations` (thường là `RestTemplate`) và cho phép cấu hình `setRestOperations(...)` theo API của phiên bản đó. **Không dùng `setRestClient(...)` trên lớp Default**, vì đó là kiểu HTTP client khác. Khi nâng cấp, đối chiếu migration guide và dependency thực tế trước khi thay đổi.

## 9. Reactive: dùng WebClientReactiveAuthorizationCodeTokenResponseClient

### 9.1. Dependency và SecurityWebFilterChain

Ứng dụng WebFlux dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Security chain của ứng dụng reactive:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Trên WebFlux, `ServerHttpSecurity` hoạt động với **WebFilter chain** và reactive types. Không khai báo `SecurityFilterChain(HttpSecurity)` để điều khiển WebFlux authorization flow.

### 9.2. Tạo token client Reactive cho authorization_code

Implementation thông dụng:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;

@Configuration
class ReactiveTokenClientConfig {

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    reactiveAuthorizationCodeTokenClient() {
        return new WebClientReactiveAuthorizationCodeTokenResponseClient();
    }
}
~~~

Kiểu `ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` có phương thức nhận grant request và trả `Mono<OAuth2AccessTokenResponse>`. Khi không tùy chỉnh HTTP transport, Spring Security có sẵn reactive token client tương thích để xử lý OIDC/OAuth2 Login.

**Một điểm khác Servlet cần đặc biệt chú ý:** đừng sao chép nguyên cú pháp `http.oauth2Login().tokenEndpoint(...).accessTokenResponseClient(...)` sang `ServerHttpSecurity`. WebFlux DSL không phải bản sao 1:1 của Servlet DSL. Việc đưa reactive token client vào **quá trình xác thực callback** cần thông qua các thành phần **ReactiveAuthenticationManager / OIDC authentication manager** tương ứng hoặc các hook được phiên bản Spring Security của ứng dụng công bố.

Chỉ khai báo một `@Bean ReactiveOAuth2AccessTokenResponseClient` như trên **không bảo đảm** mặc nhiên thay token client mà toàn bộ OAuth2 Login filter đang dùng. Muốn chắc chắn token endpoint login được tùy biến, cần cấu hình đúng authentication manager hoặc hook tương ứng rồi gắn vào WebFlux security chain. Không tự giả định Spring tự dò bean tùy ý.

### 9.3. Tùy chỉnh WebClient dùng cho token endpoint

Ví dụ cấu hình Reactor Netty HTTP client với response timeout:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient nettyClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(nettyClient))
    .build();

WebClientReactiveAuthorizationCodeTokenResponseClient tokenClient =
    new WebClientReactiveAuthorizationCodeTokenResponseClient();
tokenClient.setWebClient(tokenWebClient);
~~~

Đây là ví dụ về **HTTP transport non-blocking**. Khi thay WebClient mặc định của token response client, cần giữ xử lý đúng các form parameter, content type và OAuth2 token response; lựa chọn HTTP connector, codec và HTTP error handling cần phù hợp phiên bản Spring Security.

Đặt timeout có chủ đích để ứng dụng không đợi vô hạn khi IdP chậm, đồng thời tránh retry mù quáng request đổi **authorization code dùng một lần**. Nếu timeout xảy ra sau khi IdP đã tiêu thụ code, việc gửi lại cùng code thường dẫn đến `invalid_grant`.

### 9.4. Không block Mono trong WebFlux

Ví dụ không nên dùng trong xử lý request reactive:

~~~java
// Không dùng kiểu này trong reactive request thread:
OAuth2AccessTokenResponse response =
    reactiveTokenClient.getTokenResponse(grantRequest).block();
~~~

Thay vào đó, cần để framework hoặc pipeline reactive **subscribe và quản lý Mono**:

~~~java
Mono<OAuth2AccessTokenResponse> responseMono =
    reactiveTokenClient.getTokenResponse(grantRequest)
        .doOnError(error -> {
            // Ghi loại lỗi an toàn, tuyệt đối không log token/secret.
        });
~~~

Đoạn trên chỉ minh họa **kiểu xử lý dữ liệu Reactive**; trong ứng dụng WebFlux bình thường, Spring Security tự điều phối token exchange bên trong authentication manager. Không nên tự gọi token client trong controller callback nếu đã sử dụng `oauth2Login()`.

## 10. Cấu hình token client theo từng grant type

Không có một “token client” mặc định duy nhất bao quát mọi grant. Tùy grant, Spring Security dùng grant request và implementation thích hợp.

| Grant | Servlet (Spring Security 6.4+) | Reactive | Bối cảnh |
|---|---|---|---|
| `authorization_code` | `RestClientAuthorizationCodeTokenResponseClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient` | Đổi code sau callback |
| `refresh_token` | `RestClientRefreshTokenTokenResponseClient` | `WebClientReactiveRefreshTokenTokenResponseClient` | Gia hạn access token khi có refresh token |
| `client_credentials` | `RestClientClientCredentialsTokenResponseClient` | `WebClientReactiveClientCredentialsTokenResponseClient` | Service-to-service, không phải login người dùng |

Ví dụ cùng lúc tạo ba token client Servolet:

~~~java
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.RestClientClientCredentialsTokenResponseClient;

var authorizationCodeClient =
    new RestClientAuthorizationCodeTokenResponseClient();
var refreshTokenClient =
    new RestClientRefreshTokenTokenResponseClient();
var clientCredentialsClient =
    new RestClientClientCredentialsTokenResponseClient();
~~~

Với Reactive:

~~~java
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveClientCredentialsTokenResponseClient;

var reactiveCodeClient =
    new WebClientReactiveAuthorizationCodeTokenResponseClient();
var reactiveRefreshClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();
var reactiveClientCredentialsClient =
    new WebClientReactiveClientCredentialsTokenResponseClient();
~~~

**Ba đoạn token client này không thay thế ClientRegistration.** Chúng là các bộ thực thi HTTP cho một loại grant. Khi phát triển ứng dụng, thường chỉ tùy chỉnh loại grant thực sự cần cơ chế HTTP riêng.

## 11. OAuth2 Login và Authorized Client Manager không phải một cơ chế

Trong ứng dụng, cần phân biệt **bước đăng nhập** và **bước lấy/duy trì access token khi gọi API**.

### 11.1. OAuth2 Login

Khi browser quay về với `code` và `state`, Spring Security cần:

1. Kiểm tra callback tương quan với authorization request trước đó.
2. Đổi authorization code lấy token qua token endpoint.
3. Kiểm tra ID Token / OIDC User theo quy định khi dùng OIDC.
4. Tạo Authentication, lưu SecurityContext và authorized client phù hợp.

Trên Servlet, `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` là hook trực tiếp được hỗ trợ cho bước token response.

Trên Reactive, OAuth2 Login sử dụng **reactive authentication manager** và reactive token client bên dưới; customization không nhất thiết có cùng method chain. Các manager phải xử lý riêng trường hợp OIDC và OAuth2 login thông thường, nên không thể chỉ cắm một raw WebClient vào login filter là xong.

### 11.2. Authorized Client Manager

Khi ứng dụng **đã có một authorized client** hoặc cần token cho service-to-service, authorized client manager giúp chọn grant và quản lý token lifecycle:

- **Servlet**: `OAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientProvider`.
- **Reactive**: `ReactiveOAuth2AuthorizedClientManager` và `ReactiveOAuth2AuthorizedClientProvider`.

Một authorized client provider có thể hỗ trợ `authorization_code`, `refresh_token` và `client_credentials` tùy vào cấu hình. **Refresh token response client** và **client credentials response client** của manager có thể được tùy biến độc lập với token client của bước login.

Việc cấu hình token client cho **OAuth2 Login** không có nghĩa mọi luồng refresh/client credentials sau đó tự động dùng chính HTTP client đó. Phải xác định **đúng điểm hook cho từng luồng**.

## 12. Ví dụ Servlet: custom token client cho client_credentials trong AuthorizedClientManager

Giả sử Portal gọi một API nội bộ bằng danh tính dịch vụ (không phải token người dùng) qua grant `client_credentials`.

Cấu hình registration riêng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          service-api:
            provider: company
            client-id: ${SERVICE_CLIENT_ID}
            client-secret: ${SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Đây là **ví dụ cấu hình registration thay thế/bổ sung có chủ đích**, không copy đè cả khối YAML nếu dự án đã có provider `company`. Phần này không dùng `openid` hay redirect URI vì không có login người dùng.

Một ví dụ Servlet **AuthorizedClientManager cho tác vụ không gắn với HTTP request**:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.endpoint.RestClientClientCredentialsTokenResponseClient;

@Configuration
class ServletMachineTokenConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clientService
    ) {
        ClientCredentialsOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(
            new RestClientClientCredentialsTokenResponseClient());

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Ý nghĩa:

- `ClientRegistrationRepository` chọn registration `service-api`.
- `OAuth2AuthorizedClientService` lưu authorized client theo ngữ cảnh phù hợp.
- `ClientCredentialsOAuth2AuthorizedClientProvider` xử lý grant `client_credentials`.
- `RestClientClientCredentialsTokenResponseClient` thực hiện HTTP token exchange đồng bộ.

Chú ý `AuthorizedClientServiceOAuth2AuthorizedClientManager` thường phù hợp với **service/background workload**, không phụ thuộc request/response Servlet hiện tại. Trong web request có principal, `DefaultOAuth2AuthorizedClientManager` cùng authorized-client repository thường được dùng để quản lý authorized client liên kết request/người dùng.

## 13. Ví dụ Reactive: custom token client cho client_credentials

Với WebFlux, đối ứng là **reactive client credentials provider** và reactive manager:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ClientCredentialsReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class ReactiveMachineTokenConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(
            new WebClientReactiveClientCredentialsTokenResponseClient());

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đoạn này minh họa **ReactiveOAuth2AuthorizedClientManager** dùng khi có `ServerWebExchange` hoặc ngữ cảnh server request thích hợp. Với **scheduled job/background task không có ServerWebExchange**, cần loại manager phù hợp như `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` kết hợp `ReactiveOAuth2AuthorizedClientService`. Không mặc định tái sử dụng một manager gắn với web exchange cho mọi tác vụ nền.

Khác biệt so với Servlet:

| Servlet | Reactive |
|---|---|
| `ClientCredentialsOAuth2AuthorizedClientProvider` | `ClientCredentialsReactiveOAuth2AuthorizedClientProvider` |
| `RestClientClientCredentialsTokenResponseClient` | `WebClientReactiveClientCredentialsTokenResponseClient` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Đồng bộ | Trả Publisher; không block reactive pipeline |

Nếu muốn hỗ trợ nhiều grant, có thể dùng các **authorized client provider builders** phù hợp với Servlet/Reactive để kết hợp client credentials, refresh token và các loại grant khác thay vì chỉ dùng một provider như hai ví dụ trên. Khi kết hợp, kiểm tra token client của từng provider độc lập.

## 14. WebClient để gọi API khác WebClient dùng trao đổi token

Trong ứng dụng Reactive, tên **WebClient** thường xuất hiện tại hai chỗ:

1. **Token WebClient**: được dùng bên trong `WebClientReactive*TokenResponseClient` để gửi request đến token endpoint của Authorization Server.
2. **Resource WebClient**: được dùng sau khi có access token để gọi Orders API với Bearer header.

Hai thành phần **không giống nhau**, dù có thể chia sẻ một số cấu hình mạng được kiểm soát.

~~~text
Reactive OAuth2AuthorizedClientManager
     |
     +--> WebClientReactiveClientCredentialsTokenResponseClient
     |       |
     |       +--> POST https://login.example.test/oauth2/token
     |              (client credential / grant parameters)
     |
     +--> Authorized client / access token
             |
             +--> WebClient có OAuth2 filter
                     |
                     +--> GET https://orders.example.test/api/orders
                            Authorization: Bearer <access_token>
~~~

Một WebClient gọi API có thể dùng **ServerOAuth2AuthorizedClientExchangeFilterFunction** để lấy và đính kèm access token từ reactive authorized client manager:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

WebClient ordersApi = WebClient.builder()
    .baseUrl("https://orders.example.test")
    .filter(oauth2)
    .build();
~~~

Đây là **đoạn mô tả cách tích hợp**, trong đó `manager` phải là reactive authorized client manager được tạo/cung cấp trước. Khi gọi API phải chỉ định authorized client/registration phù hợp trong request context, hoặc cấu hình default đúng với chính sách; đừng giả định mọi request tự dùng đúng user token.

Một WebClient dùng OAuth2 filter cho Resource Server **không mặc nhiên thay HTTP client dùng token endpoint**. Muốn thay token HTTP transport, phải cấu hình token-response client và gắn đúng vào authorized client provider hoặc login authentication manager.

## 15. Khi dùng WebClient trong ứng dụng Servlet thì sao?

Một Spring MVC/Servlet application **có thể sử dụng WebClient** để gọi API, kể cả khi SecurityFilterChain vẫn là Servlet. Ngược lại, một WebFlux application có thể gọi thư viện đồng bộ ở các tác vụ nền, nhưng điều đó không biến security stack thành Servlet.

Chọn token client dựa trên **authentication/authorized client infrastructure** của ứng dụng, không chỉ dựa trên HTTP client mà một controller đang sử dụng:

~~~text
Spring MVC + HttpSecurity + ClientRegistrationRepository
    -> OAuth2AccessTokenResponseClient (Servlet)

Spring WebFlux + ServerHttpSecurity + ReactiveClientRegistrationRepository
    -> ReactiveOAuth2AccessTokenResponseClient (Reactive)
~~~

Nếu dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, cần kiểm tra **web application type** thực tế của Spring Boot. Chỉ nhìn vào Maven/Gradle hoặc chỉ thấy bean `WebClient` chưa đủ để xác định DSL phải dùng.

**Không ép Mono về giá trị đồng bộ** bằng `block()` trong event-loop chỉ để tái dùng cấu hình của MVC. Nếu cần tích hợp thư viện blocking bên trong ứng dụng WebFlux, đó là bài toán chọn scheduler/boundary và kiến trúc cần thiết kế rõ, không phải tính năng mặc định của token client.

## 16. Timeout, proxy, TLS và tài nguyên hệ thống

Token endpoint là một phụ thuộc quan trọng của login và refresh. Nếu chậm hoặc không khả dụng, ứng dụng có thể không hoàn tất đăng nhập hoặc không lấy được token mới.

### 16.1. Servlet

Với token client đồng bộ, request tới IdP có thể **chiếm thread** cho đến khi trả response hoặc timeout. Các điều kiện cần xác định:

- **Connection timeout**: thời gian tối đa để thiết lập kết nối đến IdP.
- **Read/response timeout**: thời gian chờ token response.
- **Connection pool** và giới hạn kết nối nếu có tải lớn.
- **Proxy** dành cho egress từ server đến Authorization Server.
- **TLS trust/certificate** và mTLS nếu phương thức client authentication yêu cầu.

Lựa chọn `RestClient` và underlying request factory giúp cấu hình HTTP transport. Không tắt TLS certificate/hostname verification để “sửa nhanh” lỗi kết nối.

### 16.2. Reactive

Với `WebClient` và Reactor Netty, I/O thường được xử lý non-blocking. Điều này không có nghĩa kết nối vô hạn hoặc không cần timeout:

- Cần **response timeout**, connection timeout/pool policy và TLS thích hợp.
- Cần theo dõi số request đồng thời, tỷ lệ lỗi và độ trễ token endpoint.
- Tránh blocking call trên Reactor event-loop.
- Nếu dùng reactive timeout/operator retry, phải cân nhắc **grant có thể dùng lại hay không**.

Đặc biệt, authorization code thường **dùng một lần**. Khi POST đổi code gặp timeout, client không biết chắc IdP đã nhận và tiêu thụ code chưa. **Không tự động retry vô điều kiện** request đổi code.

### 16.3. Reverse proxy của browser và network egress của token client

Hai loại đường đi có thể hoàn toàn khác:

~~~text
Browser -> HTTPS public ingress -> Portal callback
Portal  -> HTTPS egress / corporate proxy -> Token endpoint của IdP
~~~

Nếu callback `redirect_uri` sai do ingress scheme/host, đó là lỗi front-channel/public URL. Nếu Portal gọi token endpoint bị timeout vì egress proxy/firewall, đó là lỗi back-channel/network. Không sửa `redirectionEndpoint.baseUri` để giải quyết vấn đề TCP/TLS của token request.

## 17. Bảo vệ credential và token ở cả hai stack

Token endpoint có thể nhận:

- **Client secret** hoặc client assertion chữ ký theo registration.
- **Authorization code** và PKCE `code_verifier`.
- **Refresh token** khi dùng refresh grant.
- **Grant type** và các tham số khác theo thỏa thuận.

Vì vậy:

1. **Không ghi client secret vào `application.yml` đã commit**, JavaScript frontend, URL query hoặc exception output.
2. **Không log raw request/response** của token endpoint: Authorization header, form body và token response đều có dữ liệu nhạy cảm.
3. **Không gửi token response cho browser** nếu kiến trúc BFF chỉ cần session cookie.
4. **Không dùng HTTP** cho token endpoint trong production; phải xác minh certificate/TLS theo chính sách tin cậy.
5. **Không tự sửa issuer/token-uri từ dữ liệu client gửi vào**; endpoint phải thuộc provider đã được cấu hình tin cậy.
6. **Giới hạn scope/audience** và quyền truy cập của client registration.

Ví dụ quản lý secret theo runtime:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
~~~

Trong môi trường production, Kubernetes Secret, cloud secret manager hoặc mounted secret là các nguồn có thể cân nhắc theo chính sách tổ chức. **Environment variable là kênh đưa secret vào tiến trình**, không tự thay thế cơ chế bảo vệ secret manager, RBAC hoặc hạn chế process diagnostics.

## 18. Cấu hình bất thường của token response

Trong thực tế, đôi khi provider có yêu cầu khác chuẩn hoặc mở rộng như:

- Thêm một **form parameter** được IdP công bố khi trao đổi token.
- Dùng một phương thức **client authentication** khác, ví dụ `client_secret_post` hoặc `private_key_jwt`.
- Dùng egress proxy, mTLS hoặc cấu hình truststore riêng.
- Trả thêm tham số mở rộng trong token response.

Nguyên tắc xử lý:

1. **Đọc hợp đồng/token endpoint specification của provider** để xác định yêu cầu thực tế.
2. Cố gắng dùng **API extension points của token-response client** tương ứng phiên bản Spring Security.
3. Chỉ viết custom converter/HTTP client khi cần thiết; không thay toàn bộ security flow.
4. Không làm mất tham số chuẩn như `grant_type`, `code`, `redirect_uri`, PKCE verifier hoặc phương thức xác thực client.
5. Bảo đảm error response được chuyển thành lỗi OAuth2 đúng thay vì nuốt exception rồi cho login thành công giả.

Với Servlet hiện đại, nhiều `RestClient*TokenResponseClient` cung cấp khả năng cấu hình parameter converter/customizer và HTTP client. Với Reactive, các lớp `WebClientReactive*TokenResponseClient` có extension points tương ứng theo phiên bản. **Tên method cụ thể phải khớp class và phiên bản**; không giả định mọi lớp có cùng API chỉ vì tên class gần giống.

### 18.1. Vì sao không nên tự POST bằng controller?

Ví dụ tránh tự viết:

~~~java
@GetMapping("/login/oauth2/code/company")
public String callback(@RequestParam String code) {
    // Tự gửi POST, tự phân tích JWT, tự quyết định đăng nhập...
    return "home";
}
~~~

Đoạn này bỏ qua các thành phần chuẩn của Spring Security dành cho correlation, state, PKCE, token validation và SecurityContext. Đăng nhập OIDC không chỉ là nhận một access token. Nên dùng OAuth2 Login filter và tùy biến **đúng token-response client/hook** nếu chỉ cần đổi cách gửi token request.

## 19. So sánh xử lý lỗi token endpoint

Token endpoint có thể trả lỗi OAuth2:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant","error_description":"Authorization code invalid or expired"}
~~~

Các lỗi thường gặp:

| Mã/tình huống | Nguyên nhân có thể | Liên quan stack nào? |
|---|---|---|
| `invalid_client` | Sai client secret, client-authentication method, khóa/certificate | Cả Servlet và Reactive |
| `invalid_grant` | Code hết hạn/đã dùng, redirect_uri hoặc PKCE không khớp | Cả hai |
| `invalid_scope` | Scope không được chấp nhận | Cả hai |
| HTTP 429/503 | Authorization Server giới hạn tải/không sẵn sàng | Cả hai |
| TLS handshake failure | Sai truststore/certificate/mTLS | Cả hai |
| Timeout | Token endpoint hoặc network/proxy chậm | Cả hai |
| Blocking event-loop | Code reactive vô tình gọi blocking API hoặc `block()` | Chủ yếu Reactive |
| Thread pool bị chiếm khi IdP chậm | Nhiều request đồng bộ đang đợi HTTP response | Chủ yếu Servlet |
| Reactive bean không được dùng | Chỉ khai báo bean mà không gắn đúng manager/hook | Chủ yếu khi custom Reactive |

Trong Servlet, lỗi token client thường được ném ra và xử lý theo cơ chế exception/filter tương ứng. Trong Reactive, lỗi thường đi qua **error signal của Mono** rồi được reactive authentication infrastructure xử lý. Nếu tự viết `onErrorResume`, không biến `invalid_grant` thành một token response rỗng nhưng được coi là hợp lệ.

**Không dựa chỉ trên một mã HTTP** để kết luận nguyên nhân. Hãy phân biệt login callback không match, state mismatch, lỗi HTTP token endpoint, lỗi xác minh ID Token và lỗi Resource Server từ chối access token.

## 20. Testing token client trong hai stack

### 20.1. Test Servlet token-response client

Ý tưởng:

- Dùng mock HTTP server hoặc HTTP request factory có thể kiểm soát để mô phỏng token endpoint.
- Gửi một `OAuth2AuthorizationCodeGrantRequest` hợp lệ trong môi trường test.
- Kiểm tra client tạo form request, client authentication, redirect URI và PKCE theo cấu hình.
- Trả JSON token response thành công và OAuth2 error response để kiểm tra đường xử lý.

Không sử dụng secret hoặc authorization code thật của production cho test. Trong integration test OIDC, cần có client registration và provider metadata phù hợp nếu khởi tạo toàn bộ Spring context.

### 20.2. Test Reactive token-response client

Ý tưởng:

- Stub WebClient/ExchangeFunction hoặc dùng mock HTTP server để trả token response và lỗi theo ngữ cảnh Reactor.
- Dùng **StepVerifier** để quan sát emission/error của `Mono<OAuth2AccessTokenResponse>`.
- Kiểm tra timeout, lỗi kết nối, cancel subscription và không block khi chạy trong reactive flow.
- Với OIDC login end-to-end, cần xác minh thêm callback state/session và ID Token, không chỉ một JSON token response.

Ví dụ mô tả cách kiểm tra một Mono (không đại diện cho full login test):

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

Mono<OAuth2AccessTokenResponse> response =
    reactiveTokenClient.getTokenResponse(grantRequest);

StepVerifier.create(response)
    .assertNext(token -> {
        // Kiểm tra những thuộc tính cần thiết trong test.
    })
    .verifyComplete();
~~~

Để dùng `reactor.test.StepVerifier`, test cần dependency `reactor-test`. Trong ví dụ trên, `reactiveTokenClient` và `grantRequest` là fixture đã được tạo sẵn; không phải đoạn test đầy đủ có thể chạy độc lập.

## 21. Checklist lựa chọn và tích hợp token client

| Câu hỏi | Servlet | Reactive |
|---|---|---|
| Security chain đang dùng là gì? | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Token-response API cần dùng? | `OAuth2AccessTokenResponseClient` | `ReactiveOAuth2AccessTokenResponseClient` |
| HTTP transport phù hợp? | `RestClient` hoặc `RestOperations` ở phiên bản cũ | `WebClient` |
| Grant thực tế là gì? | Code, refresh hoặc client credentials | Code, refresh hoặc client credentials |
| Cấu hình cho bước login hay cho gọi API? | Hook `oauth2Login().tokenEndpoint()` hoặc authorized-client provider | Reactive authentication manager/hook hoặc reactive authorized-client provider |
| Có cần custom token HTTP client không? | Chỉ khi provider/network yêu cầu | Chỉ khi provider/network yêu cầu |
| Xử lý request thế nào? | Đồng bộ, cần timeout/thread capacity | Reactive pipeline, không block |
| Bí mật/token được bảo vệ? | TLS, secret manager, redaction, đúng issuer | Cùng các yêu cầu bảo mật |
| Có đang dùng đúng phiên bản API? | Kiểm tra RestClient 6.4+ vs Default đời cũ | Kiểm tra WebClient reactive token client của phiên bản |
| Test các nhánh thành công/lỗi? | Mock token endpoint, không cần IdP production | Mock WebClient/HTTP + StepVerifier, không cần IdP production |

Một quyết định tốt không phải “dùng Reactive vì nghe hiện đại”, mà là **chọn token client đúng với web stack và authorized-client infrastructure của ứng dụng**, sau đó tùy biến đúng phần cần thiết.

## 22. Bài tập áp dụng

### Bài tập 1: nhận diện sai kiểu interface

Cho đoạn code:

~~~java
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    tokenClient = new RestClientAuthorizationCodeTokenResponseClient();
~~~

**Câu hỏi:** Vì sao lỗi?

**Gợi ý:** Bên trái yêu cầu contract Reactive trả `Mono`, bên phải là token client Servlet đồng bộ. Trên WebFlux, dùng `WebClientReactiveAuthorizationCodeTokenResponseClient`. Trên Servlet, đổi kiểu biến sang `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>`.

### Bài tập 2: chọn nơi cấu hình

Ứng dụng Spring MVC cần đổi timeout của HTTP request **đổi authorization code**. Nhà phát triển sửa `RestClient` dùng để gọi Orders API nhưng login vẫn timeout.

**Câu hỏi:** Vì sao?

**Gợi ý:** Client gọi Resource Server và token response client là hai điểm tích hợp khác nhau. Cần thay HTTP transport của `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` và gắn vào token endpoint của `oauth2Login()`.

### Bài tập 3: reactive nhưng block

Ứng dụng WebFlux dùng:

~~~java
OAuth2AccessTokenResponse response =
    reactiveTokenClient.getTokenResponse(grantRequest).block();
~~~

**Câu hỏi:** Điều gì không phù hợp?

**Gợi ý:** Blocking trên event loop có thể làm giảm thông lượng và phát sinh lỗi. Để framework/ReactiveAuthenticationManager điều phối `Mono` hoặc kết hợp pipeline reactive bằng operator phù hợp.

### Bài tập 4: refresh token

Ứng dụng đã login thành công và có refresh token. Khi access token hết hạn, developer chỉ tùy biến authorization-code token client, nhưng refresh request vẫn dùng cấu hình HTTP mặc định.

**Câu hỏi:** Vì sao?

**Gợi ý:** Authorization code và refresh token là **hai grant khác nhau**. Cần cấu hình refresh-token response client trong authorized-client provider/manager tương ứng nếu muốn thay HTTP transport hoặc tham số của refresh request.

### Bài tập 5: lỗi không do token client

IdP báo `redirect_uri_mismatch` ngay khi browser được chuyển sang authorization endpoint.

**Câu hỏi:** Có nên thay RestClient/WebClient token response client?

**Gợi ý:** Không. Đây là lỗi **authorization request / registered redirect URI**, xảy ra trước khi Portal gọi token endpoint. Cần kiểm tra public URL, proxy/forwarded headers, ClientRegistration.redirectUri và cấu hình tại IdP.

## 23. Ghi nhớ

Trong Spring Security OAuth 2.0/OIDC Client, **Servlet và Reactive có cùng mục tiêu giao thức khi gọi token endpoint nhưng không dùng chung API thực thi**:

1. **Servlet** dùng `OAuth2AccessTokenResponseClient<T>` và thường là HTTP client đồng bộ; với Spring Security 6.4+ có họ `RestClient*TokenResponseClient`.
2. **Reactive** dùng `ReactiveOAuth2AccessTokenResponseClient<T>`, trả `Mono<OAuth2AccessTokenResponse>` và thường có họ `WebClientReactive*TokenResponseClient`.
3. **Mỗi grant có token client tương ứng**: authorization code, refresh token và client credentials không phải một request giống hệt nhau.
4. **OAuth2 Login** và **authorized-client management** là hai điểm tích hợp khác nhau; cần nối custom token client vào đúng bộ phận thực sự xử lý request.
5. **WebClient gọi API không tự trở thành WebClient của token endpoint**; web stack được quyết định bởi Servlet/WebFlux security infrastructure, không phải tên HTTP client trong code.
6. **Bảo vệ credential, token và kết nối IdP** là yêu cầu chung: TLS, timeout, không log secret/token, kiểm soát network egress và không retry bừa bãi code grant dùng một lần.

Khi thiết kế từ đầu, ưu tiên dùng **token client mặc định của Spring Security đúng stack và đúng phiên bản**. Chỉ thêm cấu hình khi có yêu cầu cụ thể về timeout, TLS, proxy, tham số của provider hoặc grant lifecycle. Cách này giữ luồng Authorization Code/OIDC login an toàn, dễ nâng cấp và nhất quán giữa Servlet và Reactive.
