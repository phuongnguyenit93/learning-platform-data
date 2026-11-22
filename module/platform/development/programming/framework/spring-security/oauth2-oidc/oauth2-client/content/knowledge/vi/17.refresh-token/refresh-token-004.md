# 17.4. RefreshTokenReactiveOAuth2AuthorizedClientProvider trong Reactive

## 1. Bài toán: đăng nhập còn hiệu lực nhưng access token đã hết hạn

Giả sử **Employee Portal** dùng **Spring Boot, Spring Security OAuth 2.0 Client và WebFlux**. Người dùng đăng nhập qua OpenID Connect (OIDC), sau đó Portal gọi **Orders API** thay mặt họ. Authorization Server cấp:

~~~text
Access token AT-1:
  issued_at  = 09:00
  expires_at = 09:05

Refresh token RT-1:
  dùng để yêu cầu access token mới theo chính sách của Authorization Server
~~~

Đến **09:07**, HTTP session của Portal vẫn còn và người dùng vẫn có `Authentication` hợp lệ, nhưng **AT-1 đã hết hạn**. Nếu Portal gửi AT-1 đến Orders API, Resource Server có thể từ chối với `401 invalid_token`.

Hệ thống có thể sử dụng **Refresh Token Grant** để xin AT-2 mà không bắt người dùng thực hiện lại toàn bộ login tương tác:

~~~text
Access token hết hạn
       |
       v
Kiểm tra authorized client có refresh token không?
       |
       +-- Không --> Không thể refresh bằng grant này
       |
       +-- Có
             |
             v
POST token endpoint (grant_type=refresh_token)
             |
             v
Nhận AT-2, có thể nhận RT-2 nếu server rotate refresh token
             |
             v
Lưu OAuth2AuthorizedClient mới
             |
             v
Gọi Orders API bằng AT-2
~~~

Trong **Spring Security Reactive**, lớp thực hiện quyết định **có nên refresh authorized client hay không** là:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider
~~~

Đây là trọng tâm của bài. Lớp này **không tự chạy theo lịch**, không tự tạo phiên OIDC và cũng không phải HTTP client gọi Orders API. Nó là một **ReactiveOAuth2AuthorizedClientProvider** mà `ReactiveOAuth2AuthorizedClientManager` có thể sử dụng khi cần một authorized client phù hợp.

> Bối cảnh ví dụ: Java 17+, Spring Boot 3, Spring Security 6, **Spring WebFlux / Reactive** và Reactor. Các domain, token và client ID là giả lập. Phương thức cấu hình cụ thể có thể khác giữa các phiên bản Spring Security; sử dụng API do dependency đang chạy cung cấp.

## 2. Vị trí của Refresh Token Provider trong kiến trúc

Spring Security OAuth2 Client có ba loại thành phần dễ nhầm:

| Thành phần | Nhiệm vụ |
|---|---|
| **ReactiveOAuth2AuthorizedClientManager** | Điều phối việc tải, cấp mới, làm mới và lưu authorized client |
| **ReactiveOAuth2AuthorizedClientProvider** | Xác định một grant có thể dùng trong ngữ cảnh hiện tại và thực hiện grant nếu phù hợp |
| **ReactiveOAuth2AccessTokenResponseClient** | Thực hiện HTTP token request đến Authorization Server và chuyển token response thành đối tượng Java |

Với Refresh Token Grant:

~~~mermaid
flowchart TD
    A["WebFlux handler / WebClient cần access token"] --> B["ReactiveOAuth2AuthorizedClientManager"]
    B --> C["Reactive authorized-client repository/service"]
    C --> D["OAuth2AuthorizedClient hiện tại"]
    D --> E["RefreshTokenReactiveOAuth2AuthorizedClientProvider"]
    E --> F{"Có refresh token và access token cần refresh?"}
    F -->|Không| G["Mono.empty() - provider không thực hiện refresh"]
    F -->|Có| H["WebClientReactiveRefreshTokenTokenResponseClient"]
    H --> I["POST token endpoint"]
    I --> J["OAuth2AccessTokenResponse"]
    J --> K["OAuth2AuthorizedClient mới"]
    K --> B
    B --> L["Lưu authorized client và trả kết quả"]
    L --> M["WebClient gọi Orders API với access token"]
~~~

**Provider** trả kết quả qua Reactor `Mono`. Khi grant không áp dụng, provider thường trả `Mono.empty()` để manager hoặc một provider khác xử lý tiếp. Khi refresh được, nó phát một `OAuth2AuthorizedClient` mới. Khi token endpoint lỗi, nó phát **error signal** thay vì một token giả.

### 2.1. Phân biệt ba vòng đời

1. **OIDC login / Authentication**: browser và ứng dụng xác lập người dùng đã đăng nhập qua Authorization Code Flow.
2. **OAuth2AuthorizedClient**: thông tin token đã cấp cho một ClientRegistration và principal.
3. **Refresh Token Grant**: cấp access token mới từ một authorized client có refresh token hợp lệ.

Refresh token **không đồng nghĩa phiên đăng nhập còn hiệu lực**, và refresh thành công **không tự tạo Authentication mới** trong SecurityContext.

## 3. Lớp RefreshTokenReactiveOAuth2AuthorizedClientProvider làm gì?

Tên đầy đủ:

~~~java
import org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider;
~~~

Nó triển khai:

~~~java
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientProvider;
~~~

Hợp đồng khái niệm của interface:

~~~java
public interface ReactiveOAuth2AuthorizedClientProvider {
    Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizationContext context
    );
}
~~~

Khi được gọi, provider kiểm tra authorized client nằm trong context:

- **Có authorized client đã được cấp chưa?**
- **Authorized client có refresh token không?**
- **Access token đã hết hạn hoặc gần hết hạn theo clock skew chưa?**
- **Nếu đủ điều kiện, token-response client có trao đổi refresh token thành công không?**

Provider **không cần browser redirect** để thực hiện refresh token grant. HTTP request được gửi **server-to-server** đến token endpoint của Authorization Server.

### 3.1. Các trường hợp và kết quả

| Authorized client | Refresh token | Access token | Hành vi của refresh provider |
|---|---|---|---|
| Chưa tồn tại | — | — | Không có gì để refresh, trả `Mono.empty()` |
| Đã có | Không có | Hết hạn | Không thể dùng Refresh Token Grant, thường `Mono.empty()` |
| Đã có | Có | Còn đủ thời hạn ngoài clock skew | Không refresh, thường `Mono.empty()` |
| Đã có | Có | Hết hạn hoặc nằm trong khoảng clock skew | Gọi token endpoint bằng refresh token |
| Đã có | Có | Cần refresh, token endpoint trả thành công | Phát `OAuth2AuthorizedClient` mới |
| Đã có | Có | Cần refresh, token endpoint từ chối | Phát lỗi Reactor `Mono.error(...)` |

**`Mono.empty()` không phải kết luận “người dùng đã logout”**, và cũng không phải kết luận “token hiện có không dùng được”. Nó biểu thị **provider này không thực hiện authorization mới trong context đó**.

### 3.2. Trách nhiệm nào không thuộc provider?

Provider không:

- Tự quyết định quyền tài nguyên của Orders API.
- Xác minh lại mật khẩu hoặc thực hiện OIDC login tương tác.
- Tự lưu token vĩnh viễn trong database.
- Tự hủy session người dùng khi refresh thất bại.
- Tự gọi refresh theo cron khi không có ai yêu cầu authorized client.
- Tự thu hồi refresh token ở Authorization Server khi người dùng logout.

Những hành vi đó phụ thuộc **manager**, **repository/service**, **security/session policy** và **Authorization Server**.

## 4. Mono và cơ chế non-blocking của Reactive

API Reactive mô tả một tác vụ bất đồng bộ:

~~~java
Mono<OAuth2AuthorizedClient> refreshed =
    refreshProvider.authorize(context);
~~~

Trong một pipeline Reactive, cần **compose/return Publisher** cho thành phần phía trên:

~~~java
return refreshProvider.authorize(context)
    .flatMap(client -> callOrdersApi(client.getAccessToken()))
    .switchIfEmpty(Mono.defer(() -> handleNoRefresh()));
~~~

Đoạn này minh họa ý tưởng; `callOrdersApi(...)` và `handleNoRefresh()` là hàm nghiệp vụ ví dụ. Trong ứng dụng WebFlux thông thường, **manager và WebClient OAuth2 filter** thực hiện phần lớn việc điều phối, không cần controller tự gọi refresh provider.

**Không dùng `.block()` trong request-handling event loop:**

~~~java
// Không nên làm trong reactive HTTP handler:
OAuth2AuthorizedClient value =
    refreshProvider.authorize(context).block();
~~~

Blocking trên Reactor event loop có thể gây lỗi runtime hoặc giảm thông lượng nghiêm trọng khi IdP chậm.

### 4.1. Có Mono không đồng nghĩa token được refresh ngay

Reactor Publisher thường **lazy**: xây một `Mono` không có nghĩa HTTP request lập tức được gửi. Spring Security/WebClient integration chịu trách nhiệm subscription khi request thực sự được thực thi.

Không gọi `.subscribe()` thủ công trong service chỉ để “refresh token sẵn” rồi bỏ qua kết quả; như vậy dễ mất error handling, context và kết quả token mới. Nếu cần proactive refresh, hãy xây một workflow có lifecycle và storage rõ ràng, không dùng fire-and-forget trong controller.

## 5. Access token hết hạn và clock skew

Một access token có:

~~~text
issuedAt  = 2026-11-16T02:00:00Z
expiresAt = 2026-11-16T02:05:00Z
clockSkew = 60 giây
~~~

Nếu hệ thống đánh giá token **sắp hết hạn** khi:

\[
\text{now} \geq \text{expiresAt} - \text{clockSkew}
\]

thì token có thể được làm mới ngay từ **02:04:00Z**, trước thời điểm `expiresAt`.

Mục tiêu của clock skew là giảm tình huống:

1. Client cho rằng token vẫn còn vài giây.
2. Request đi qua mạng, queue hoặc gateway.
3. Resource Server nhận token khi token đã hết hạn.

### 5.1. Tùy chỉnh clock skew

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider;

RefreshTokenReactiveOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

refreshProvider.setClockSkew(Duration.ofSeconds(90));
~~~

Ở ví dụ này, provider xem token là **cần refresh sớm** nếu thời gian còn lại nằm trong khoảng 90 giây. Giá trị thích hợp phụ thuộc latency, thời hạn token, chênh lệch đồng hồ và tải hệ thống.

**Không nên đặt clock skew lớn hơn đáng kể tuổi thọ access token** vì hệ thống có thể refresh quá thường xuyên. Cần đồng bộ đồng hồ giữa ứng dụng/Authorization Server, theo dõi latency, và không sửa `expiresAt` trong database một cách tùy tiện để “ép refresh”.

### 5.2. Clock skew không tự gia hạn session

`setClockSkew(...)` chỉ điều chỉnh **thời điểm provider quyết định access token cần refresh**. Nó không đổi:

- HTTP session timeout.
- ID Token expiry.
- OIDC `max_age` hay yêu cầu reauthentication.
- Refresh token lifetime.
- Quyền truy cập tài nguyên ở Resource Server.

## 6. Refresh Token Grant gửi những gì tới token endpoint?

Khi access token cần refresh, provider chuyển yêu cầu cho token-response client. HTTP request về mặt giao thức có thể là:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=refresh_token&refresh_token=<redacted-refresh-token>
~~~

Đây là **request minh họa** cho confidential client dùng `client_secret_basic`. Các nhà cung cấp có thể yêu cầu phương thức xác thực khác, thêm scope hoặc tham số extension được hỗ trợ. Client phải áp dụng đúng cấu hình đã đăng ký và hợp đồng của Authorization Server.

Response:

~~~json
{
  "access_token": "EXAMPLE_AT_2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_RT_2",
  "scope": "orders.read"
}
~~~

Với một số server, response **không trả refresh token mới**. Khi đó client có thể tiếp tục dùng refresh token cũ theo chính sách/token response handling của thư viện. Nếu server trả RT-2 theo **refresh token rotation**, RT-1 có thể lập tức không còn dùng được.

**Không log hoặc gửi những credential này về browser**. Refresh token là dữ liệu có khả năng xin access token mới và phải được bảo vệ tại backend.

## 7. WebClientReactiveRefreshTokenTokenResponseClient

Refresh provider cần một token-response client phù hợp grant:

~~~java
import org.springframework.security.oauth2.client.endpoint
    .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveRefreshTokenTokenResponseClient;
~~~

Hợp đồng:

~~~java
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
~~~

Client này chịu trách nhiệm **POST tới token endpoint** và chuyển kết quả thành `OAuth2AccessTokenResponse` bên trong `Mono`.

Provider chịu trách nhiệm **khi nào gọi client đó** và **tạo OAuth2AuthorizedClient mới**. Manager chịu trách nhiệm **điều phối và lưu** theo storage policy.

### 7.1. Khởi tạo provider với token response client riêng

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;

WebClientReactiveRefreshTokenTokenResponseClient tokenClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();

RefreshTokenReactiveOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

refreshProvider.setAccessTokenResponseClient(tokenClient);
refreshProvider.setClockSkew(Duration.ofSeconds(60));
~~~

Ở đây ta chưa tạo full manager, chỉ cấu hình **refresh provider**. Nếu app đã dùng provider chain mặc định của Spring Security, việc tạo instance này mà **không gắn vào chain/manager thực sự sử dụng** sẽ không làm thay đổi hành vi.

### 7.2. Tùy chỉnh WebClient HTTP transport

Khi cần timeout cho HTTP token request:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

WebClientReactiveRefreshTokenTokenResponseClient tokenClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();

tokenClient.setWebClient(tokenWebClient);
~~~

Đây là **ví dụ điều chỉnh transport**, không phải lý do để tự thay toàn bộ OAuth2 token conversion hoặc error handling. Với hệ thống thật, cần bổ sung connection timeout, proxy egress, TLS trust/mTLS, connection pool và giới hạn tải theo kiến trúc.

Không vô hiệu TLS hostname/certificate verification để khắc phục lỗi token endpoint. Không bật HTTP wire logging chứa client secret/refresh token.

### 7.3. Tránh nhầm hai WebClient

~~~text
WebClient A:
  được WebClientReactiveRefreshTokenTokenResponseClient dùng
  -> POST https://login.example.test/oauth2/token

WebClient B:
  được ứng dụng dùng để gọi Resource Server
  -> GET https://orders.example.test/api/orders
     Authorization: Bearer <access-token>
~~~

Tùy chỉnh WebClient B **không tự thay WebClient A**. Tùy chỉnh WebClient A **không tự chèn access token vào WebClient B**. Hai phần phải được kết nối qua provider/manager/authorized-client integration đúng chỗ.

## 8. Spring Boot WebFlux và ClientRegistration

Dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Ví dụ OIDC registration:

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
~~~

Trong đó:

- `company` là **registration ID**, không phải user ID.
- `openid` bật OIDC login khi provider hỗ trợ.
- `orders.read` yêu cầu scope cho Orders API, nhưng token thực tế phải được server cấp quyền và có audience phù hợp.
- `OIDC_CLIENT_SECRET` phải đến từ secret manager/runtime, không nằm trong repository/frontend.
- **Refresh token có thể không được cấp**, tùy cấu hình provider, grant, client policy và consent. Không suy luận việc có scope `openid` luôn dẫn đến refresh token.

### 8.1. Callback và token refresh khác nhau

Authorization Code Flow có **front-channel callback**, còn Refresh Token Grant không cần browser callback:

~~~text
OIDC login:
  Browser -> OP -> /login/oauth2/code/company -> đổi code lấy token

Refresh:
  WebFlux backend -> POST token endpoint với refresh_token -> token mới
~~~

Nếu callback lỗi `invalid_state`, `redirect_uri_mismatch` hoặc mất session, sửa refresh provider không giải quyết được. Phải kiểm tra authorization request, callback URL, cookie/session và OIDC login flow riêng.

## 9. SecurityWebFilterChain và OAuth2 Login

Với ứng dụng WebFlux:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
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

`oauth2Login()` cấu hình OIDC login trên WebFlux. `oauth2Client()` hỗ trợ OAuth2 Client. Cấu hình này **không yêu cầu tạo controller callback riêng** và **không tự bảo đảm refresh token luôn tồn tại**.

**WebFlux không dùng `SecurityFilterChain(HttpSecurity)` hoặc `HttpServletRequest` cho security flow.** Reactive security dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và `ServerWebExchange`.

## 10. ReactiveOAuth2AuthorizedClientManager thực sự kích hoạt refresh

Trên WebFlux, manager điều phối providers và persistence. Một configuration phổ biến cho **HTTP request context**:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveAuthorizedClientConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Điểm quan trọng:**

1. `ReactiveClientRegistrationRepository` cung cấp client registration đã cấu hình.
2. `ServerOAuth2AuthorizedClientRepository` tải/lưu authorized client trong ngữ cảnh WebFlux request.
3. Provider chain hỗ trợ `authorization_code` và `refresh_token`.
4. Manager điều phối provider, nhận kết quả và lưu theo repository/handler.

Nếu ứng dụng chỉ có `.authorizationCode()` mà không có refresh provider, một token hết hạn **không tự được làm mới bằng refresh_token grant** qua manager đó.

### 10.1. Vì sao không gọi provider trực tiếp ở controller?

Thông thường, controller không nên:

~~~java
// Thiết kế khó bảo trì: controller tự gọi refresh provider và tự lưu token.
return refreshProvider.authorize(context)
    .flatMap(refreshed -> repository.saveAuthorizedClient(...));
~~~

Hãy để **manager** chịu trách nhiệm chọn registration, tạo context, gọi provider và lưu token. Controllers/HTTP clients sử dụng manager hoặc integration được framework cung cấp.

### 10.2. Gắn provider refresh được tùy chỉnh vào manager

Nếu yêu cầu thay clock skew/token-response client, một lựa chọn là cấu hình manager **chỉ thực hiện refresh với authorized client đã tồn tại**:

~~~java
package com.example.portal.reactive;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class RefreshOnlyManagerConfig {

    @Bean("refreshOnlyManager")
    ReactiveOAuth2AuthorizedClientManager refreshOnlyManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        RefreshTokenReactiveOAuth2AuthorizedClientProvider refresh =
            new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        refresh.setClockSkew(Duration.ofSeconds(90));

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );
        manager.setAuthorizedClientProvider(refresh);
        return manager;
    }
}
~~~

Đây là ví dụ **manager chỉ có refresh provider**, dành cho việc hiểu sự tích hợp. Nó **không thực hiện authorization_code grant để tạo authorized client mới**, vì provider chain chỉ có refresh. Khi chưa có authorized client, manager không thể tự bắt đầu một luồng cấp quyền bằng chính refresh provider.

Trong sản phẩm có cả login/authorization code và refresh, thường kết hợp các providers cần thiết hoặc dùng provider builder của Spring Security với cấu hình cho refresh tùy phiên bản. Không đặt hai bean manager cho cùng consumer mà không biết instance nào được dùng.

## 11. Dùng manager để lấy authorized client trong WebFlux

Sau khi người dùng đã OIDC login, một controller hoặc WebClient integration có thể gọi manager theo registration và principal.

Một mẫu sử dụng từ service **khi đã có Authentication hợp lệ và ngữ cảnh WebFlux phù hợp**:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> authorizeCompany(
    ReactiveOAuth2AuthorizedClientManager manager,
    Authentication authentication
) {
    OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
            .withClientRegistrationId("company")
            .principal(authentication)
            .build();

    return manager.authorize(request);
}
~~~

**Lưu ý:** `DefaultReactiveOAuth2AuthorizedClientManager` dành cho request WebFlux còn cần `ServerWebExchange` hoặc context attributes thích hợp để tương tác với `ServerOAuth2AuthorizedClientRepository`. Nếu tự gọi manager bên ngoài framework integration, phải truyền/ánh xạ HTTP exchange context theo API của phiên bản đang dùng. Chỉ có một `Authentication` Java object chưa chắc đủ ngữ cảnh cho mọi repository.

Với controller WebFlux thông thường, cách tiện lợi hơn là sử dụng **WebClient OAuth2 filter** được tích hợp với manager.

### 11.1. WebClient sử dụng đúng manager

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        ReactiveOAuth2AuthorizedClientManager manager
    ) {
        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .filter(oauth2)
            .build();
    }
}
~~~

Và khi gọi API:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

public Mono<String> listOrders(WebClient ordersWebClient) {
    return ordersWebClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Trong ngữ cảnh một request WebFlux đã xác thực, filter có thể nhờ manager tìm hoặc refresh authorized client. Manager/provider chain cần có `refreshToken()`; nếu không, token hết hạn sẽ không được làm mới bằng grant đó.

**Không cấu hình “default authorized client” cho mọi request tùy ý**. Chỉ định registration phù hợp với Resource Server và quyền của principal. Token của một client/tenant không được gửi sang một API không được phép.

### 11.2. Có cần gọi refreshToken() trực tiếp?

Không cần có method `refreshToken()` ở controller. Refresh được kích hoạt khi **manager.authorize(...)** được gọi và provider thấy đủ điều kiện. Một request dùng HTTP client OAuth2 filter có thể gián tiếp kích hoạt hành vi đó.

Nếu chỉ đọc `OAuth2AuthorizedClient` từ repository mà không gọi manager/provider, đừng giả định việc đọc sẽ thực hiện refresh qua token endpoint.

## 12. Manager dành cho background job không có ServerWebExchange

Một job định kỳ dùng `client_credentials` hoặc tác vụ có cơ chế ủy quyền hợp lệ riêng **không có HTTP request WebFlux**. Khi đó `DefaultReactiveOAuth2AuthorizedClientManager` gắn với server exchange không phải lựa chọn phù hợp.

Spring Security cung cấp:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

Ví dụ:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
class BackgroundManagerConfig {

    @Bean("backgroundAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService clientService
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là **manager riêng cho service-to-service**, không phải cùng instance dùng trong các ví dụ controller phía trên. Client credentials thường không cấp refresh token; khi access token hết hạn, manager có thể xin access token mới bằng **client_credentials grant**, thay vì refresh_token grant.

Nếu một background workflow thực sự quản lý authorized client có refresh token, provider chain có thể bao gồm `refreshToken()` theo policy. Nhưng phải xác định **nguồn principal và quyền sử dụng token thay mặt người dùng**, không lấy token tùy ý từ repository bằng principal name do job tự đoán.

## 13. RefreshTokenReactiveOAuth2AuthorizedClientProvider vs các provider khác

| Provider/Grant | Cần dữ liệu ban đầu | Kết quả | Có yêu cầu browser interaction không? |
|---|---|---|---|
| **Authorization Code** | Authorization request/callback, code và state | Authorized client đầu tiên sau authorization | Có, trong luồng authorization ban đầu |
| **Refresh Token** | Existing authorized client + refresh token | Access token mới, có thể refresh token mới | Thường không |
| **Client Credentials** | Client registration/credential | Access token cho danh tính dịch vụ | Không |

Tùy theo cấu hình, provider chain có thể bao gồm:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

**Có ba provider không đồng nghĩa một registration đồng thời dùng cả ba grant.** `authorization-grant-type` trong ClientRegistration và ngữ cảnh authorization mới quyết định grant nào phù hợp.

Một client registration OIDC với `authorization_code` không thể tự đổi thành client_credentials chỉ vì manager hỗ trợ `.clientCredentials()`. Một token của service cũng không được coi là token người dùng.

## 14. Trạng thái token sau khi refresh

Giả sử trước refresh:

~~~text
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = AT-1, expires 09:05
  refreshToken   = RT-1
~~~

Sau refresh thành công:

~~~text
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = AT-2, expires 09:10
  refreshToken   = RT-2 (nếu rotate) hoặc giá trị phù hợp response handling
~~~

**Registration và principal không bị thay thành user khác** chỉ vì token mới được cấp. Manager cần lưu bản ghi updated đúng chỗ, thường keyed theo registration ID và principal name hoặc repository context.

Một số provider có thể trả thêm scope hoặc dữ liệu khác trong token response. Ứng dụng phải dựa trên token response đã được parse theo OAuth2 specification, không tự tạo expiresAt bằng thời gian tùy ý hay giả định scope luôn được mở rộng.

### 14.1. Refresh không cập nhật OIDC Authentication một cách tự động

Nếu trong `SecurityContext` người dùng có `OidcUser`, việc refresh access token thường **không tự thay OidcUser bằng một principal đã xác thực lại** hoặc nạp lại mọi claim UserInfo.

Ví dụ:

~~~text
09:00 login: OidcUser.email = minh@example.test
09:10 email thay đổi tại IdP
09:12 refresh access token thành công
~~~

Không thể từ việc refresh thành công kết luận `OidcUser.email` trong phiên Portal đã cập nhật. Đồng bộ hồ sơ và reauthentication là các bài toán riêng với chính sách riêng.

Nếu refresh response có thông tin OIDC bổ sung trong một trường hợp cụ thể, không tự diễn giải nó như một ID Token login mới mà bỏ qua quy tắc validation OIDC.

## 15. Lỗi invalid_grant và failure handling

Token endpoint có thể từ chối refresh:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
~~~

Lý do thường gặp:

- Refresh token hết hạn theo chính sách Authorization Server.
- Refresh token đã bị revoke do logout, admin action hoặc thay đổi chính sách.
- Refresh token rotation đã vô hiệu hóa token cũ.
- Refresh token không thuộc client, không hợp lệ hoặc không được dùng với grant.
- Đồng bộ authorized-client store bị lỗi khiến client dùng lại refresh token cũ.

Lỗi của WebClient/token endpoint đi qua **Reactor error signal**. Manager có thể áp dụng authorization failure handler để loại authorized client không còn hợp lệ khỏi store, tùy implementation và cấu hình.

### 15.1. Phân biệt invalid_grant với lỗi mạng

| Trường hợp | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `invalid_grant` | Refresh token/grant bị Authorization Server từ chối | Loại token không hợp lệ theo chính sách, yêu cầu authorization lại khi cần |
| `invalid_client` | Client authentication thất bại | Kiểm tra client ID/secret, mTLS hoặc phương thức xác thực |
| `invalid_scope` | Scope request không hợp lệ | Kiểm tra registration và provider policy |
| HTTP 429 | Token endpoint giới hạn tải | Backoff/throttle phù hợp, không spam refresh |
| HTTP 500/503 | Authorization Server gặp sự cố | Trả lỗi hạ tầng; retry có kiểm soát, không tự hủy mọi user session |
| Timeout/TLS failure | Network hoặc transport lỗi | Kiểm tra proxy, DNS, CA, mTLS và timeout |

**Không xóa mọi session WebFlux khi một refresh token thất bại**. Người dùng có thể vẫn authenticated ở Portal theo chính sách phiên, nhưng không có token hợp lệ cho Resource Server liên quan. Ứng dụng cần phân loại tác động và hướng dẫn authorization lại nếu cần.

### 15.2. Không nuốt error signal

Ví dụ nguy hiểm:

~~~java
// Không trả authorized client cũ như thể refresh đã thành công:
return refreshProvider.authorize(context)
    .onErrorResume(ex -> Mono.just(oldAuthorizedClient));
~~~

Nếu token cũ đã bị từ chối, fallback này có thể khiến Portal tiếp tục gửi Bearer token sai và tạo vòng lặp lỗi. Cần xử lý exception theo loại, chính sách cleanup và yêu cầu người dùng cấp quyền lại.

### 15.3. Failure handler của manager

Với Spring Security Reactive, có các authorization success/failure handlers để lưu hoặc loại authorized client sau các trường hợp phù hợp. Kiểm tra default behavior của **manager và phiên bản Spring Security được dùng**: một số trường hợp `invalid_grant` có thể làm bản ghi authorized client bị loại bỏ, nhưng không có nghĩa **mọi lỗi** đều cần xóa token.

Không ghi nội dung raw token endpoint error response nếu nó chứa credential hoặc dữ liệu người dùng. Log mã lỗi đã che, registration ID, correlation ID và dấu thời gian đủ để hỗ trợ điều tra.

## 16. Refresh token rotation và vấn đề đồng thời

Đây là tình huống đặc biệt quan trọng trong hệ thống Reactive có nhiều request đồng thời:

~~~mermaid
sequenceDiagram
    participant A as Request A / Node A
    participant B as Request B / Node B
    participant Store as Authorized Client Store
    participant AS as Authorization Server

    A->>Store: Load AT-1 + RT-1
    B->>Store: Load AT-1 + RT-1
    A->>AS: Refresh RT-1
    AS-->>A: AT-2 + RT-2
    B->>AS: Refresh RT-1
    AS-->>B: invalid_grant (RT-1 đã dùng)
    A->>Store: Save AT-2 + RT-2
    Note over A,B: Nếu failure handler xóa bản ghi sai thời điểm, kết quả refresh thành công có thể bị ảnh hưởng
~~~

Trong một số OP, cùng refresh token được phép dùng nhiều lần; trong số khác, **rotation/reuse detection** có thể khiến cả token family bị thu hồi khi phát hiện reuse. Vì vậy không có một cơ chế retry chung đúng cho mọi nhà cung cấp.

Các hướng thiết kế:

1. Dùng **authorized-client store có tính nhất quán** giữa các replica.
2. Khi cần, phối hợp refresh theo khóa `(registrationId, principalName)` hoặc khóa thực tế của store.
3. Có chiến lược **single-flight / lock / optimistic concurrency** phù hợp với kiến trúc.
4. Lưu cả access token mới và refresh token mới **nhất quán** sau khi rotate.
5. Không retry mù quáng cùng RT-1 sau `invalid_grant`.
6. Không xóa dữ liệu token mới hơn khi một request khác gặp lỗi do token cũ, nếu có khả năng kiểm tra version/generation trong storage.

**Mono không giải quyết race condition tự động.** Non-blocking I/O không biến nhiều request thành một transaction hoặc một refresh duy nhất.

### 16.1. Refresh sớm có thể tăng số lần đụng nhau

Nếu clock skew quá lớn, nhiều request sẽ xem token còn hạn là “sắp hết hạn” sớm. Khi có tải lớn, số request cùng cố refresh có thể tăng.

Điều chỉnh clock skew dựa trên lifetime, latency và concurrency thực tế; không đặt quá lớn chỉ vì muốn “chắc chắn token luôn mới”.

## 17. Multi-instance: session và token store là hai chuyện

~~~text
                     +--> WebFlux Node A
Browser -> Gateway --|
                     +--> WebFlux Node B
                               |
                +--------------+---------------+
                |                              |
          Web Session Store             Authorized Client Store
                |                              |
          SecurityContext               AT / RT cho principal
~~~

Với OIDC login, browser cần giữ session để Spring Security có thể nhận callback và xác lập Authentication. Với authorized client, manager cần tải đúng token đã cấp/refresh.

Nếu session chia sẻ nhưng authorized client store lưu local ở mỗi node, Node B có thể không tìm thấy RT-1 của Node A. Nếu authorized client chia sẻ nhưng session mất, browser có thể không còn authenticated và không nên tự dùng token của principal do browser chỉ định.

**Các kho lưu cần được thiết kế riêng theo vai trò**:

- WebSession persistence/correlation: ví dụ Reactive session store.
- Authorized-client repository/service: lưu AT/RT, bảo vệ bằng encryption/access control/TTL/audit tùy chính sách.
- Role/tenant membership: authorization policy của ứng dụng, có thể cần nguồn dữ liệu riêng.

Không nhầm **refresh token** với **cookie đăng nhập**. Refresh token thường không cần đi tới browser trong BFF/server-side web client.

## 18. Refresh token có phải luôn được cấp trong OIDC không?

Không. Các nguyên nhân không có refresh token:

- Authorization Server không cho phép refresh token cho loại client này.
- Grant/scope/consent không đáp ứng policy.
- Thiếu điều kiện provider yêu cầu, ví dụ quyền truy cập offline trong một số hệ thống.
- Client được đăng ký theo mô hình không cho giữ long-lived refresh credentials.
- Người dùng đã thu hồi quyền hoặc policy được cập nhật.

Nếu authorized client không có refresh token:

~~~text
Existing authorized client
  accessToken = expired
  refreshToken = null
~~~

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` không thể refresh nó. Ứng dụng cần **authorization code flow mới**, một cơ chế cấp token khác theo client registration hoặc trả thông báo yêu cầu cấp quyền lại.

**Không tự tạo refresh token** từ ID Token, access token, session cookie hoặc `sub`. Refresh token phải do Authorization Server cấp và bảo vệ.

## 19. Refresh không thay thế reauthentication, consent hay authorization

Giả sử người dùng có quyền `orders.read` lúc login. Sau đó quyền của họ bị thu hồi ở Orders API.

~~~text
WebFlux session còn
Refresh token còn hợp lệ
Access token refresh thành AT-2
Orders API vẫn có thể trả 403
~~~

Refresh chỉ xin **token mới** theo grant/authorization hiện có và policy của Authorization Server, không đảm bảo Resource Server cấp lại quyền.

Ứng dụng cần phân biệt:

| Câu hỏi | Cơ chế chính |
|---|---|
| Người dùng đang đăng nhập Portal? | WebFlux Authentication / SecurityContext / session |
| Access token cần cấp lại? | Reactive authorized-client manager + refresh provider |
| Người dùng phải nhập lại mật khẩu/MFA? | OIDC authentication / reauthentication policy |
| Cần consent mới? | Authorization Code Flow/provider policy |
| Token có quyền đọc/sửa đơn hàng? | Scope/audience và Resource Server authorization |
| Người dùng còn thuộc tenant không? | Business authorization / membership |

Nếu OP yêu cầu người dùng tương tác lại, refresh token grant không thể “ép” người dùng bỏ qua yêu cầu đó.

## 20. Refresh token vs ID Token vs login session

OIDC ID Token xác thực người dùng cho client tại một thời điểm và được kiểm tra theo điều kiện OIDC khi login. Khi access token refresh thành công:

- Không tự chứng minh người dùng đã reauthenticate.
- Không tự thay Session/Authentication ở Portal.
- Không tự làm mới toàn bộ claim trong `OidcUser`.
- Không tự cập nhật `auth_time` hoặc đáp ứng `max_age` của một chính sách đăng nhập mới.

Và khi người dùng logout khỏi Portal:

- WebFlux SecurityContext/session bị kết thúc theo cấu hình.
- Access token hoặc refresh token vẫn có thể còn hiệu lực phía Authorization Server nếu chưa revoke.
- Bản ghi authorized client ở persistent store có thể còn tùy chính sách cleanup.

Nếu ứng dụng yêu cầu revoke refresh token khi logout, phải triển khai cleanup/revocation và OP logout phù hợp, không trông chờ refresh provider tự thu hồi token.

## 21. Bảo mật Refresh Token trong backend Reactive

**Refresh token là credential nhạy cảm**, cần thực hiện ít nhất những nguyên tắc sau:

1. Dùng HTTPS/TLS khi gọi token endpoint; xác minh certificate và host.
2. Không chuyển refresh token ra browser khi kiến trúc là BFF/server-side.
3. Không ghi refresh token, access token, client secret, authorization code hoặc token response nguyên văn vào log.
4. Không lưu refresh token trong cache/log/tracing có quyền đọc rộng.
5. Bảo vệ authorized-client store: encryption, access control, retention và backup phù hợp chính sách.
6. Gắn token với đúng registration/principal; không dùng `?principalName=admin` từ browser để tải token của user khác.
7. Đánh giá refresh token rotation, revocation, device/session binding và rủi ro token theft theo provider.
8. Giới hạn timeout, concurrency, retry và rate khi gọi token endpoint.
9. Thu hồi hoặc loại token khi user/account bị disable theo policy; không chờ refresh provider tự nhận biết mọi quyết định quản trị.
10. Dùng client authentication method đúng như đăng ký OP; không chuyển client secret vào URL query.

### 21.1. Logging an toàn

Thay vì:

~~~text
refresh_token=real-secret-value
access_token=real-bearer-value
client_secret=real-client-secret
~~~

hãy log có kiểm soát:

~~~text
event=oauth_refresh_failed
registration=company
error=invalid_grant
duration_ms=...
correlation_id=...
~~~

Không cần log username/email đầy đủ hoặc raw JWT. Audit và tracing phải tuân theo nguyên tắc tối thiểu dữ liệu cá nhân.

## 22. Quan sát Refresh Token Provider trong vận hành

Các số liệu hữu ích:

| Metric/event | Ý nghĩa |
|---|---|
| Refresh attempted | Bao nhiêu lần provider quyết định gửi refresh request |
| Refresh success/failure | Tỷ lệ grant thành công |
| Token endpoint latency | Độ trễ Authorization Server/back-channel |
| invalid_grant | Tín hiệu refresh token không dùng được |
| invalid_client | Sai client configuration/secret/mTLS |
| HTTP 429/503 | Rate limiting hoặc provider outage |
| Concurrent refresh conflict | Nguy cơ RT rotation reuse |
| Token expiresAt/skew | Có refresh quá sớm hoặc quá muộn không |
| Authorized client load/save failure | Lỗi persistence |
| API 401 invalid_token | Token bị Resource Server từ chối sau khi cấp |

Đừng suy luận “refresh success” chỉ vì có `Mono` được tạo. Cần quan sát **token response thực sự hoàn tất và authorized client được lưu**.

Trong logs, không đưa tokenValue, client secret hoặc những claims cá nhân không cần thiết để tính metric.

## 23. Testing RefreshTokenReactiveOAuth2AuthorizedClientProvider

Test nên kiểm tra **quy tắc quyết định** của provider mà không cần Authorization Server production:

1. Có authorized client và RT, AT đã hết hạn → gọi token client và trả authorized client mới.
2. AT còn hạn ngoài clock skew → không gọi token endpoint.
3. Không có refresh token → không gửi token request.
4. Token endpoint trả `invalid_grant` → Mono error.
5. Token response rotate RT → authorized client mới dùng RT mới.
6. Token response không có RT mới → authorized client xử lý RT theo quy tắc của library/provider.
7. Hai request concurrent → test hành vi ứng dụng và store, không kỳ vọng provider có lock toàn cục.

### 23.1. Unit test tối giản bằng StepVerifier

Một ví dụ Java/JUnit 5 mô phỏng refresh response, kiểm tra provider phát authorized client mới:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveRefreshProviderTest {

    @Test
    void expiredTokenWithRefreshTokenProducesNewAuthorizedClient() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("company")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                    "https://login.example.test/oauth2/authorize")
                .tokenUri("https://login.example.test/oauth2/token")
                .redirectUri(
                    "{baseUrl}/login/oauth2/code/{registrationId}")
                .build();

        Instant now = Instant.now();

        OAuth2AccessToken oldAccess = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-old-access",
            now.minusSeconds(600),
            now.minusSeconds(60),
            Set.of("orders.read")
        );

        OAuth2RefreshToken oldRefresh = new OAuth2RefreshToken(
            "test-old-refresh",
            now.minusSeconds(600)
        );

        OAuth2AuthorizedClient oldClient =
            new OAuth2AuthorizedClient(
                registration,
                "employee-42",
                oldAccess,
                oldRefresh
            );

        OAuth2AuthorizationContext context =
            OAuth2AuthorizationContext.withAuthorizedClient(oldClient)
                .principal(new TestingAuthenticationToken(
                    "employee-42", "ignored", "ROLE_USER"))
                .build();

        ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
            fakeTokenClient = request -> Mono.just(
                OAuth2AccessTokenResponse
                    .withToken("test-new-access")
                    .tokenType(OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(300)
                    .refreshToken("test-new-refresh")
                    .scopes(Set.of("orders.read"))
                    .build()
            );

        RefreshTokenReactiveOAuth2AuthorizedClientProvider provider =
            new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setClockSkew(Duration.ofSeconds(60));
        provider.setAccessTokenResponseClient(fakeTokenClient);

        StepVerifier.create(provider.authorize(context))
            .assertNext(refreshed -> {
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-new-access",
                    refreshed.getAccessToken().getTokenValue()
                );
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-new-refresh",
                    refreshed.getRefreshToken().getTokenValue()
                );
                org.junit.jupiter.api.Assertions.assertEquals(
                    "employee-42",
                    refreshed.getPrincipalName()
                );
            })
            .verifyComplete();
    }
}
~~~

Ví dụ này chỉ thử **provider logic**. Nó **không phải integration test OIDC login**, không kiểm tra signature ID Token, callback state hoặc token endpoint thật. Mọi token string là fixture giả, không phải credential production.

### 23.2. Test Mono.empty()

Nếu access token còn hạn lâu và có RT:

~~~java
// Dùng fixture với access token còn hạn > clockSkew.
StepVerifier.create(provider.authorize(contextWithFreshToken))
    .verifyComplete();
~~~

Một test đầy đủ cần xác nhận fake token response client **không được gọi**. Với Mockito, có thể `verifyNoInteractions(tokenClient)`; với fake tự viết, dùng counter an toàn. `contextWithFreshToken` là fixture của test, không phải biến có sẵn.

Nếu refresh token là null, behavior tương tự: provider không có grant hợp lệ để thực hiện, thường `Mono.empty()`.

### 23.3. Test lỗi token endpoint

Token response client có thể trả:

~~~java
return Mono.error(new RuntimeException(
    "Simulated token endpoint failure"));
~~~

Khi đó:

~~~java
StepVerifier.create(provider.authorize(expiredContext))
    .expectError()
    .verify();
~~~

Đây chỉ là mock lỗi kỹ thuật. Khi test `invalid_grant` theo OAuth2, nên mô phỏng loại exception/error code chính xác mà Spring Security xử lý, rồi kiểm tra manager failure handler và repository có xóa authorized client theo policy hay không.

## 24. So sánh với Servlet Refresh Token Provider

Trong ứng dụng Spring MVC/Servlet, lớp tương ứng là:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenOAuth2AuthorizedClientProvider
~~~

Còn WebFlux/Reactive:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider
~~~

| Tiêu chí | Servlet | Reactive |
|---|---|---|
| Provider | `RefreshTokenOAuth2AuthorizedClientProvider` | `RefreshTokenReactiveOAuth2AuthorizedClientProvider` |
| Interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Kết quả authorize | Authorized client hoặc không có kết quả theo contract đồng bộ | `Mono<OAuth2AuthorizedClient>` hoặc empty/error |
| Token-response client | `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | `ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` |
| HTTP engine thông dụng | `RestClient` hoặc `RestOperations` theo phiên bản | `WebClient` |
| Authorized client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Web application stack | `HttpSecurity / SecurityFilterChain` | `ServerHttpSecurity / SecurityWebFilterChain` |
| Không nên làm | Block vô hạn trên thread xử lý request | Gọi `block()` trên event loop |

**Không thể inject một provider Servlet vào Reactive manager** bằng cách đổi tên biến. Chúng có interfaces và execution semantics khác nhau. Nếu Spring Boot dùng WebFlux, chọn reactive provider và reactive client repositories.

## 25. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Cách khoanh vùng |
|---|---|---|
| Token hết hạn nhưng không có HTTP refresh | Manager/provider chain không chứa refresh provider, manager không được gọi | Xem cấu hình `ReactiveOAuth2AuthorizedClientProviderBuilder` và HTTP client integration |
| Provider trả `Mono.empty()` | Không có authorized client, không có RT hoặc AT chưa tới hạn refresh | Kiểm tra metadata, không coi đây là lỗi user session |
| `invalid_grant` khi refresh | RT hết hạn/revoked/reused, rotation race | Kiểm tra OP policy và store concurrency |
| `invalid_client` | Client secret/authentication method sai | Kiểm tra runtime secrets, mTLS, registration |
| Refresh response thành công nhưng request sau dùng AT cũ | Authorized client mới không được lưu/được tải từ store sai | Kiểm tra manager save handler, repository/service và principal key |
| Refresh nhiều lần liên tục | Clock skew quá lớn, token expiresAt không đúng hoặc store không cập nhật | Kiểm tra expiry, time sync, refresh latency và cache |
| Reactive HTTP handler bị đứng | Có `.block()` hoặc HTTP client blocking trên event loop | Kiểm tra Reactor stack, loại bỏ blocking |
| Chỉ khi scale mới lỗi refresh | RT rotation race hoặc store không chia sẻ | Kiểm tra multi-instance persistence và concurrency |
| OIDC login thành công nhưng không có refresh token | OP/client policy không cấp RT | Kiểm tra grant, consent và provider policy |
| Portal vẫn login nhưng Orders API 401 | Token hết hạn/revoked/sai audience hoặc manager chưa refresh | Phân biệt Authentication và authorized client |
| API 403 sau refresh | Scope hoặc quyền tài nguyên không đủ | Kiểm tra Resource Server policy, không coi refresh là tăng quyền |
| WebClient gọi API không tự refresh | Filter không dùng đúng manager hoặc registration ID | Kiểm tra `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| Background job báo thiếu ServerWebExchange | Dùng web manager ngoài HTTP request | Dùng service-based reactive manager |
| Thay WebClient gọi API nhưng timeout token endpoint không đổi | Token WebClient là instance khác | Tùy chỉnh WebClient của token-response client |
| Logout Portal nhưng RT vẫn còn | Local logout không tự revoke token | Thiết kế token cleanup/revocation policy |

Đừng sửa nhiều tầng cùng lúc. Trước tiên xác định lỗi thuộc **WebFlux request/session**, **authorized-client manager/provider**, **token endpoint**, **repository** hay **Resource Server**.

## 26. Những hiểu lầm phổ biến

**“Refresh provider tự làm mới token đúng mỗi 5 phút.”** Không. Nó được gọi trong luồng authorization khi consumer/manager cần token; không phải scheduler.

**“Có refresh token thì user luôn login.”** Không. Refresh token không phải web session cookie hay Authentication.

**“Mono.empty() nghĩa là refresh lỗi.”** Không. Provider thường dùng empty khi grant không áp dụng.

**“Reactive provider tự lưu token trong Redis.”** Không. Manager/repository/service phụ trách persistence.

**“WebFlux có WebClient nên tự động refresh.”** Không. WebClient phải tích hợp OAuth2 manager/filter phù hợp.

**“Refresh trả access token mới thì OidcUser claims cũng mới.”** Không mặc định; cần xử lý profile/reauthentication riêng.

**“AT còn hạn là API chắc chắn chấp nhận.”** Không. API còn kiểm tra audience, scope, revocation và resource permission.

**“Clock skew càng lớn càng an toàn.”** Không. Quá lớn có thể khiến refresh quá sớm và nhiều request cùng tranh refresh token.

**“Lỗi invalid_grant cứ retry cùng RT cũ.”** Nguy hiểm khi rotation hoặc reuse detection.

**“Không có refresh token thì tự tạo bằng ID Token.”** Không được; token phải do Authorization Server cấp.

**“Reactive không bao giờ có race condition.”** Không. Concurrent requests và multi-node stores vẫn cần đồng bộ.

## 27. Bài tập thực hành

### Bài tập 1 — Access token chưa tới hạn refresh

~~~text
expiresAt = 10:10:00Z
now       = 10:08:00Z
clockSkew = 60 giây
RT        = có
~~~

**Câu hỏi:** Provider có cần refresh ngay không?

**Hướng giải:** Chưa. Token còn 120 giây, lớn hơn clock skew 60 giây. Provider thường trả `Mono.empty()` khi được hỏi trong context này.

### Bài tập 2 — Token sắp hết hạn

~~~text
expiresAt = 10:10:00Z
now       = 10:09:30Z
clockSkew = 60 giây
RT        = có
~~~

**Câu hỏi:** Vì sao provider có thể refresh trước 10:10?

**Hướng giải:** Token còn 30 giây, nằm trong khoảng skew 60 giây; refresh sớm tránh token hết hạn trong lúc đi qua mạng.

### Bài tập 3 — Không có refresh token

~~~text
authorizedClient.accessToken = expired
authorizedClient.refreshToken = null
~~~

**Câu hỏi:** Provider làm gì?

**Hướng giải:** Không thể dùng refresh_token grant; thường trả `Mono.empty()`. Muốn xin token mới phải dùng grant/authorization flow phù hợp mà client được phép sử dụng.

### Bài tập 4 — WebFlux handler sử dụng block()

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(request).block();
~~~

**Câu hỏi:** Có vấn đề gì?

**Hướng giải:** Blocking trong reactive event-loop là chống lại execution model, có thể gây lỗi hoặc giảm throughput. Trả `Mono`, dùng `flatMap` và để framework subscribe.

### Bài tập 5 — Refresh token rotation đồng thời

Hai request cùng tải RT-1 rồi gửi hai refresh request. OP trả RT-2 cho request đầu, `invalid_grant` cho request sau.

**Câu hỏi:** Chỉ thêm `retry(3)` có giải quyết được không?

**Hướng giải:** Không. RT-1 đã bị dùng; retry có thể khiến reuse detection nghiêm trọng hơn. Cần cơ chế concurrency, token store nhất quán và xử lý token generation mới nhất.

### Bài tập 6 — WebClient không dùng manager custom

Đã tạo manager có refresh provider, nhưng code gọi API:

~~~java
WebClient.create("https://orders.example.test")
    .get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class);
~~~

**Câu hỏi:** Vì sao token không tự refresh?

**Hướng giải:** WebClient chưa có OAuth2 exchange filter dùng đúng manager. Cần xây WebClient với `ServerOAuth2AuthorizedClientExchangeFilterFunction`, chọn đúng registration ID và principal context.

### Bài tập 7 — Refresh thành công, API trả 403

AT-2 còn hạn nhưng API yêu cầu `orders.write`, token chỉ có `orders.read`.

**Câu hỏi:** Có nên refresh tiếp lần nữa ngay?

**Hướng giải:** Không nên coi refresh là phép tăng quyền. Cần xin cấp quyền/scope đúng và kiểm tra policy của Resource Server.

## 28. Checklist tích hợp Reactive Refresh Token

| Câu hỏi | Điều cần bảo đảm |
|---|---|
| Application thực sự là WebFlux? | `SecurityWebFilterChain`, `ServerHttpSecurity`, reactive repositories |
| Có ClientRegistration hợp lệ? | Grant, issuer/token endpoint, scope và client authentication đúng |
| Authorized client có refresh token? | Không giả định có, kiểm tra dữ liệu thực |
| Provider chain có refreshToken() chưa? | Có khi ứng dụng cần Refresh Token Grant |
| Clock skew có phù hợp? | Không quá lớn, time sync và latency được cân nhắc |
| Token response client dùng gì? | `WebClientReactiveRefreshTokenTokenResponseClient` phù hợp |
| Token HTTP transport đã cấu hình? | HTTPS, timeout, proxy egress, TLS trust/mTLS |
| WebClient API có dùng đúng manager? | `ServerOAuth2AuthorizedClientExchangeFilterFunction` và registration ID |
| Web context có đầy đủ? | Principal đã xác thực, ServerWebExchange khi cần |
| Background task dùng manager nào? | Service-based reactive manager, không phụ thuộc request |
| Error invalid_grant xử lý ra sao? | Failure handler/cleanup và reauthorization policy |
| RT rotation có concurrency policy? | Có store nhất quán và lock/versioning nếu cần |
| Refresh response có được lưu? | Manager/repository/service lưu authorized client mới |
| Refresh có tự login user không? | Không; Authentication/session được quản lý riêng |
| Log có lộ token/secret không? | Không lưu tokenValue/refresh token/secret vào log |
| Có test empty/success/error? | StepVerifier, fake token response client, integration test store |

## 29. Tổng kết

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` là **provider Refresh Token Grant dành cho Spring Security Reactive**. Nó kiểm tra authorized client hiện có, refresh token và thời hạn access token (có tính clock skew), rồi khi phù hợp dùng **`ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`** để gọi token endpoint. Kết quả được biểu diễn bằng **`Mono<OAuth2AuthorizedClient>`**; khi không đủ điều kiện, provider thường trả **`Mono.empty()`**.

Trong WebFlux, provider được sử dụng đúng cách thông qua **`ReactiveOAuth2AuthorizedClientManager`** và authorized-client repository/service. Với request web, `DefaultReactiveOAuth2AuthorizedClientManager` phối hợp WebFlux context; với background task không có request, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp hơn. HTTP client gọi Resource Server cần sử dụng manager đó qua **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** hoặc integration tương ứng; chỉ khai báo provider bean không làm mọi WebClient tự refresh.

Cuối cùng, **refresh token không phải HTTP session, không phải ID Token và không tự mang lại quyền truy cập mới**. Hãy thiết kế clock skew, token-response client, lưu token mới, xử lý `invalid_grant`, refresh token rotation, concurrency và security boundaries một cách rõ ràng. Đó là nền tảng để gọi API ổn định mà vẫn giữ đúng mô hình non-blocking, login và authorization của Spring Security WebFlux.
