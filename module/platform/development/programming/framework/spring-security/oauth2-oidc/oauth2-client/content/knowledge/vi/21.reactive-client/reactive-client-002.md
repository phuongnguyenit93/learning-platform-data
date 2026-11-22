# 21.2. DefaultReactiveOAuth2AuthorizedClientManager trong ServerWebExchange

## 1. Bài toán: lấy access token trong một HTTP request WebFlux

Giả sử một cổng quản lý báo cáo được xây dựng bằng **Spring Boot WebFlux**. Người dùng đăng nhập bằng OpenID Connect (OIDC) qua nhà cung cấp danh tính của doanh nghiệp. Sau đó họ mở trang báo cáo; backend cần gọi Reports API bằng **access token được cấp cho đúng ClientRegistration và đúng người dùng**.

Các bước trong request thường là:

1. Browser gọi <code>GET /reports</code> tới ứng dụng WebFlux.
2. Spring Security phục hồi <code>Authentication</code> từ reactive security context/WebSession.
3. Ứng dụng chọn <code>ClientRegistration</code>, ví dụ <code>company</code>.
4. Ứng dụng lấy <code>OAuth2AuthorizedClient</code> đã lưu, hoặc yêu cầu refresh nếu access token sắp hết hạn và có refresh token phù hợp.
5. <code>WebClient</code> gửi access token đến Reports API đã được cấp quyền.
6. Backend xử lý dữ liệu trả về, hoặc xử lý HTTP 401/403 theo đúng nguyên nhân.

Trong Servlet, người học có thể đã biết <code>DefaultOAuth2AuthorizedClientManager</code> kết hợp <code>OAuth2AuthorizedClientRepository</code> và <code>HttpServletRequest</code>. Ở **Reactive WebFlux**, thành phần tương ứng cho HTTP request là:

**<code>DefaultReactiveOAuth2AuthorizedClientManager</code>**.

Nó phối hợp **reactive registration repository**, **server authorized-client repository**, **authorization providers** và **<code>ServerWebExchange</code>** để cấp, làm mới, lưu và trả về authorized client mà không sử dụng Servlet API.

> **Điểm cần nhớ:** <code>DefaultReactiveOAuth2AuthorizedClientManager</code> được thiết kế cho **ngữ cảnh HTTP request WebFlux**. Nó không phải một token store, không phải một OpenID Provider, không tự biết quyền nghiệp vụ của API đích và không mặc nhiên là manager phù hợp nhất cho background job không có <code>ServerWebExchange</code>.

## 2. Mục tiêu bài học

Sau bài này, người học có thể:

- Giải thích vai trò của <code>ReactiveOAuth2AuthorizedClientManager</code> và implementation mặc định dành cho <code>ServerWebExchange</code>.
- Phân biệt <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code>, <code>ReactiveOAuth2AuthorizedClientService</code> và <code>OAuth2AuthorizedClient</code>.
- Hiểu cách <code>OAuth2AuthorizeRequest</code> mang registration ID, <code>Authentication</code> và WebFlux exchange context.
- Cấu hình <code>ReactiveOAuth2AuthorizedClientProvider</code> cho Authorization Code, Refresh Token và Client Credentials.
- Sử dụng <code>manager.authorize(...)</code> với <code>Mono&lt;OAuth2AuthorizedClient&gt;</code> mà **không gọi <code>block()</code>** trong WebFlux request.
- Kết hợp authorized client với <code>WebClient</code> để gọi Resource Server đúng audience/scope.
- Chọn manager **không phụ thuộc web exchange** khi chạy scheduler/job.
- Chẩn đoán lỗi do thiếu exchange, sai registration, sai principal, token hết hạn và cấu hình storage nhiều instance.

## 3. Những thành phần liên quan

### 3.1. Bức tranh tổng thể

~~~mermaid
flowchart TD
    B["Browser request"] --> W["WebFlux ServerWebExchange"]
    W --> SEC["SecurityWebFilterChain / Authentication"]
    W --> APP["Reactive Controller / Service"]
    SEC --> APP
    APP --> M["DefaultReactiveOAuth2AuthorizedClientManager"]
    M --> REG["ReactiveClientRegistrationRepository"]
    M --> STORE["ServerOAuth2AuthorizedClientRepository"]
    M --> P["ReactiveOAuth2AuthorizedClientProvider"]
    P --> G1["authorization_code"]
    P --> G2["refresh_token"]
    P --> G3["client_credentials"]
    G2 --> AS["Authorization Server / Token Endpoint"]
    G3 --> AS
    M --> AC["Mono<OAuth2AuthorizedClient>"]
    AC --> CLIENT["WebClient / Bearer access token"]
    CLIENT --> API["Resource Server"]
~~~

Không phải mọi request sẽ đi qua mọi grant. Provider được chọn theo <code>ClientRegistration</code>, authorized client hiện có, điều kiện làm mới token và context của yêu cầu.

### 3.2. Bảng phân biệt trách nhiệm

| Thành phần | Chức năng chính | Điều không nên nhầm |
|---|---|---|
| <code>ClientRegistration</code> | Cấu hình Client ID, grant type, scopes, token endpoint, issuer | Không phải token đã được cấp |
| <code>ReactiveClientRegistrationRepository</code> | Tìm <code>ClientRegistration</code> theo registration ID bằng reactive API | Không lưu access token |
| <code>OAuth2AuthorizedClient</code> | Gắn ClientRegistration + principalName + access token + refresh token tùy chọn | Không phải <code>OidcUser</code> |
| <code>ServerOAuth2AuthorizedClientRepository</code> | Load/save/remove authorized client trong <code>ServerWebExchange</code> | Không tự refresh token |
| <code>ReactiveOAuth2AuthorizedClientService</code> | Load/save/remove authorized client reactive theo registration/principal | Không cần Servlet request |
| <code>ReactiveOAuth2AuthorizedClientProvider</code> | Thực hiện authorization/refresh grant khi phù hợp | Không tự làm storage |
| <code>DefaultReactiveOAuth2AuthorizedClientManager</code> | Điều phối các thành phần trên trong web request | Không tự mở browser login thay filter |
| <code>ServerWebExchange</code> | Bao bọc reactive request/response/session/context của một lượt HTTP | Không phải một global singleton |
| <code>WebClient</code> | Gửi HTTP request downstream bất đồng bộ | Không tự biết audience/scope nếu không cấu hình |

### 3.3. Khóa authorized client

Trong các implementation service phổ biến, authorized client được xác định theo:

~~~text
(clientRegistrationId, principalName)
~~~

Ví dụ:

~~~text
(company, user-123)  → access token của user-123 tại registration company
(company, user-456)  → access token của user-456
(partner, user-123)  → access token khác của user-123 tại partner
~~~

Các tên user ở đây chỉ minh họa. <code>principalName</code> thường lấy từ <code>Authentication.getName()</code>; với OIDC có thể dựa trên claim <code>sub</code>, nhưng cũng có thể được ứng dụng tùy biến. Không giả định principal name luôn là email hoặc luôn trùng <code>sub</code>.

Nếu nhiều issuer/tenant có cùng subject string, cần phân vùng principal key để tránh va chạm. Việc đặt lock/storage key chỉ theo subject không có issuer hoặc tenant scope có thể gây nhầm token giữa tài khoản khác nhau.

## 4. ServerWebExchange là gì và vì sao manager cần nó?

Trong Spring WebFlux, <code>ServerWebExchange</code> đại diện cho ngữ cảnh **một HTTP exchange**, chứa:

- <code>ServerHttpRequest</code>.
- <code>ServerHttpResponse</code>.
- Cách truy cập <code>WebSession</code> bằng reactive API.
- Attributes của exchange và các thông tin routing/request liên quan.
- Cầu nối tới các cơ chế web security, session và authorized-client repository.

Nó **không** phải <code>HttpServletRequest</code>, <code>HttpServletResponse</code>, cũng không phải một object global được phép lưu trong static field để tái sử dụng giữa request.

Một <code>ServerOAuth2AuthorizedClientRepository</code> cần biết request, authentication và exchange để quyết định lấy authorized client từ đâu và lưu lại như thế nào.

Ví dụ về interface:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);
~~~

Đây là bản trích *chữ ký phương thức minh họa*, không phải một class hoàn chỉnh để copy-paste. Chúng cho thấy điểm khác với một service chỉ nhận registration ID và principalName.

### 4.1. ServerWebExchange và Reactor Context là hai khái niệm khác nhau

<code>ServerWebExchange</code> mô tả HTTP exchange; <code>ReactiveSecurityContextHolder</code> truyền tải security context trong **Reactor Context**. Một ứng dụng không nên giả định rằng việc có exchange tự động có đúng <code>Authentication</code>, hoặc việc có Authentication tự động có thể lấy exchange từ một thread-local.

~~~text
ServerWebExchange           → HTTP request, response, WebSession
Authentication              → principal, authorities, authenticated state
Reactor Context             → ngữ cảnh reactive truyền qua pipeline
OAuth2AuthorizeRequest      → registration + principal + attributes cần cho manager
~~~

Một controller WebFlux có thể nhận <code>Authentication</code> và <code>ServerWebExchange</code> làm method parameters, sau đó truyền cả hai vào service chuyên trách.

### 4.2. Phân biệt web request với background job

Scheduled job không tự có exchange:

~~~java
@Scheduled(fixedDelay = 60_000)
public void runJob() {
    // Không có ServerWebExchange của browser tại đây.
}
~~~

Không được chế tạo một fake <code>ServerWebExchange</code> tùy tiện chỉ để dùng web manager trong job. Trong môi trường không có HTTP exchange, Spring Security có **<code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code>** làm manager dựa trên <code>ReactiveOAuth2AuthorizedClientService</code> và thường thích hợp hơn.

## 5. Cách manager xử lý authorize(...)

Abstraction:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> authorizedClient =
    manager.authorize(authorizeRequest);
~~~

<code>authorize(...)</code> là **reactive operation**. Kết quả được biểu diễn bằng <code>Mono&lt;OAuth2AuthorizedClient&gt;</code>, không phải một authorized client đồng bộ trả về ngay.

Khái niệm xử lý:

~~~mermaid
flowchart TD
    A["manager.authorize(request)"] --> B["Lấy registration ID và principal"]
    B --> C["Tìm ClientRegistration"]
    C --> D["Tìm authorized client trong repository"]
    D --> E{"Token hiện hành đủ điều kiện sử dụng?"}
    E -->|Có| F["Trả authorized client hiện hành"]
    E -->|Không / chưa có| G["Chuyển OAuth2AuthorizationContext đến providers"]
    G --> H{"Provider có xử lý được?"}
    H -->|Có| I["Token request / refresh khi phù hợp"]
    I --> J["Lưu authorized client mới bằng success handler"]
    J --> K["Trả Mono<OAuth2AuthorizedClient>"]
    H -->|Không| L["Mono.empty hoặc kết quả theo context"]
    I -->|Thất bại| M["OAuth2AuthorizationException / failure handler"]
~~~

Sơ đồ mô tả logic **khái niệm**; thứ tự chi tiết của framework, cách xử lý authorized client hiện có và quyết định trả <code>Mono.empty()</code> tùy provider/manager/version. Không nên bắt mọi <code>Mono.empty()</code> rồi tự tạo token giả.

### 5.1. Trường hợp đã có access token còn hiệu lực

Giả sử repository đang giữ:

~~~text
registrationId=company
principalName=user-123
accessToken.expiresAt=11:00
now=10:30
~~~

Nếu token còn sử dụng được theo chính sách expiry/clock-skew và không có yêu cầu reauthorize, manager thường có thể tái sử dụng authorized client hiện tại, tránh gọi Token Endpoint không cần thiết.

### 5.2. Access token gần hết hạn và có refresh token

~~~text
registrationId=company
principalName=user-123
accessToken.expiresAt=10:31
refreshToken=R0
now=10:30:30
~~~

Nếu có <code>refreshToken()</code> provider và refresh token được Authorization Server chấp nhận, manager có thể refresh:

~~~text
R0 → POST /token grant_type=refresh_token
   → access token A1
   → refresh token R1 nếu provider rotation
   → save authorized client mới
~~~

Không phải OIDC Authorization Code Flow nào cũng được cấp refresh token. Provider, scope, consent và policy quyết định liệu refresh token có tồn tại.

### 5.3. Chưa có authorized client

Nếu repository chưa có token, việc manager có thể tạo authorized client hay không phụ thuộc vào ClientRegistration và provider:

- Với Client Credentials Grant, manager có thể xin service access token nếu client authentication và provider phù hợp.
- Với Authorization Code Grant, phải có browser authorization flow phù hợp; không có authorization code thì manager không tự mở trang OP từ một service method.
- Với chỉ Refresh Token Provider, chưa có refresh token thì không thể refresh.

### 5.4. Mono.empty, lỗi và null

Với reactive API, đừng gọi:

~~~java
OAuth2AuthorizedClient result = manager.authorize(request); // sai kiểu
~~~

Thay vào đó:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No OAuth2 authorized client")));
~~~

<code>Mono.empty()</code> là trường hợp publisher không phát ra giá trị. <code>Mono.error(...)</code> biểu diễn thất bại cần xử lý. Không dùng <code>onErrorResume</code> để mặc định lấy token của user khác.

## 6. Tạo ứng dụng WebFlux OAuth2/OIDC Client tối thiểu

### 6.1. Dependencies

Ví dụ sử dụng Java 17, Spring Boot 3 và Spring Security 6:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Với ứng dụng mong muốn chạy Reactive WebFlux, cần tránh thêm <code>spring-boot-starter-web</code> vô ý. Khi cả MVC và WebFlux cùng có mặt, Spring Boot thông thường ưu tiên MVC/Servlet; lúc ấy cấu hình <code>SecurityWebFilterChain</code> có thể không được dùng như mong đợi.

### 6.2. ClientRegistration cho OIDC Authorization Code

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Các giá trị là placeholder. Scope <code>reports.read</code> chỉ có ý nghĩa nếu OP thực sự cấp quyền cho Reports API, và Reports API được thiết kế chấp nhận token có đúng audience/scope đó. Không gửi access token chỉ dành cho UserInfo tới API nghiệp vụ không phù hợp.

Secret nên nằm trong secret manager/biến môi trường. Redirect URI phải được đăng ký chính xác trên OP, và hệ thống production phải dùng HTTPS tin cậy.

### 6.3. SecurityWebFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Ở đây:

- <code>oauth2Login()</code> xử lý browser login, authorization code callback, OIDC authentication và việc tạo user principal.
- <code>oauth2Client()</code> cung cấp hỗ trợ OAuth2 Client trong WebFlux cho các use case lấy authorized client/gọi API.
- <code>SecurityWebFilterChain</code> phục vụ reactive requests; không dùng <code>HttpSecurity</code> của Servlet.
- Browser login thường có WebSession và CSRF protection theo chính sách web của Spring Security.

Nếu ứng dụng chỉ cần login, không gọi API downstream, không nhất thiết phải bật mọi tính năng OAuth2 Client ngoài nhu cầu. Ví dụ sử dụng cả hai vì bài này cần authorized-client manager.

## 7. Cấu hình DefaultReactiveOAuth2AuthorizedClientManager

Ta chủ động cấu hình manager với repository và provider:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveAuthorizedClientManagerConfig {

    @Bean("webAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
        ReactiveClientRegistrationRepository clientRegistrations,
        ServerOAuth2AuthorizedClientRepository authorizedClientRepository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(60)))
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            clientRegistrations, authorizedClientRepository);

        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Đây là cấu hình **tường minh để học cách ghép abstraction**, không có nghĩa Spring Boot không thể auto-configure những thành phần tương đương. Khi dự án đã có manager, cần tránh tạo nhiều bean cùng kiểu mà không quy định bean nào được HTTP client/service sử dụng.

### 7.1. Constructor nhận hai phụ thuộc

~~~java
new DefaultReactiveOAuth2AuthorizedClientManager(
    clientRegistrations,
    authorizedClientRepository)
~~~

**<code>clientRegistrations</code>** là <code>ReactiveClientRegistrationRepository</code>, dùng tìm cấu hình Client theo <code>registrationId</code>.

**<code>authorizedClientRepository</code>** là <code>ServerOAuth2AuthorizedClientRepository</code>, xử lý storage của authorized client trong ngữ cảnh <code>ServerWebExchange</code>.

Không truyền <code>ClientRegistrationRepository</code> kiểu Servlet hoặc <code>OAuth2AuthorizedClientService</code> đồng bộ vào constructor reactive.

### 7.2. Provider phù hợp grant đang dùng

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

Ví dụ web login dùng Authorization Code Flow, còn refresh token provider phục vụ token đã có khi cần cập nhật.

**Thêm <code>authorizationCode()</code> không tự thay thế authorization redirect/callback WebFilters.** Chặng người dùng đăng nhập ở OP vẫn do <code>oauth2Login()</code> cùng cấu hình reactive security xử lý.

Nếu một registration dùng client credentials trong chính web request và có chính sách phù hợp, có thể thêm <code>clientCredentials()</code> vào provider tổng hợp. Nhưng không dùng service token như token đại diện cho người dùng đã đăng nhập.

### 7.3. Clock skew

~~~java
.refreshToken(configurer ->
    configurer.clockSkew(Duration.ofSeconds(60)))
~~~

Token có thể được coi là cần refresh sớm hơn expiry 60 giây để giảm nguy cơ hết hạn giữa request. Giá trị 60 giây là ví dụ; cần điều chỉnh theo token lifetime, độ lệch đồng hồ và độ trễ mạng.

Clock skew không kéo dài hạn token thực, không bảo đảm refresh token còn hiệu lực và không tự xử lý refresh race giữa nhiều replica.

## 8. OAuth2AuthorizeRequest: kết nối registration, Authentication và exchange

Đây là điểm quan trọng nhất khi gọi <code>DefaultReactiveOAuth2AuthorizedClientManager</code> trực tiếp.

Một request có các thành phần:

~~~text
OAuth2AuthorizeRequest
  ├── clientRegistrationId: company
  ├── principal: Authentication của user hiện tại
  └── attributes: ServerWebExchange của HTTP request
~~~

Ví dụ trong reactive web request:

~~~java
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("company")
        .principal(authentication)
        .attribute(ServerWebExchange.class.getName(), exchange)
        .build();
~~~

Điểm khác biệt:

- <code>"company"</code> xác định ClientRegistration sẽ được tra cứu.
- <code>authentication</code> đại diện cho principal hiện tại; dùng nó thay vì một tên user do browser gửi.
- <code>exchange</code> cung cấp HTTP WebFlux request context để repository thực hiện load/save/remove.
- Key <code>ServerWebExchange.class.getName()</code> được manager/web integration nhận biết trong context theo API Spring Security tương ứng.

Nếu không có ServerWebExchange trong một flow đòi exchange, việc load/save authorized client có thể thất bại hoặc không hoạt động như kỳ vọng. **Không dùng một fake exchange ngoài HTTP request để che giấu lỗi kiến trúc**; background jobs nên dùng service manager.

### 8.1. Vì sao dùng Authentication thay vì subject string?

Với user login:

~~~java
.principal(authentication)
~~~

liên kết authorized client với <code>Authentication</code> đã được Spring Security xác thực.

Không làm:

~~~java
.principal(exchange.getRequest().getQueryParams()
    .getFirst("user"))
~~~

Đoạn sau cho phép caller chọn principal key tùy ý. Nếu storage có token của nhiều user, đây là nguy cơ truy cập nhầm hoặc lộ token của người khác.

### 8.2. principalName không phải scope

<code>principalName</code> xác định người dùng/service trong storage. Nó **không** quyết định OAuth scopes hay token audience. Muốn có scope <code>reports.read</code> phải cấu hình ClientRegistration và được Authorization Server cấp; Resource Server vẫn kiểm tra quyền khi nhận token.

### 8.3. Không lưu ServerWebExchange ở singleton

Sai:

~~~java
@Component
class BadExchangeHolder {
    private ServerWebExchange currentExchange; // nguy hiểm
}
~~~

Spring singleton có thể phục vụ nhiều request đồng thời. Giữ exchange trong một field mutable dùng chung có thể gây race và lẫn người dùng. Hãy truyền exchange qua method parameter hoặc giữ nó trong đúng reactive execution context của request.

## 9. Ví dụ hoàn chỉnh: manager trực tiếp trong reactive service

Ví dụ dưới đây sử dụng manager cấu hình ở mục 7, rồi lấy authorized client và dùng WebClient gọi Reports API.

### 9.1. WebClient dành riêng cho Reports API

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
        WebClient.Builder builder,
        @Value("${app.reports-api.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Thuộc tính:

~~~yaml
app:
  reports-api:
    base-url: https://api.example.org
~~~

Đây là **Resource Server**, không phải Token Endpoint của OP. Base URL lấy từ cấu hình tin cậy, không để browser cung cấp URL tùy ý để tránh SSRF hoặc rò rỉ bearer token.

### 9.2. Reactive service lấy authorized client

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportsService {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient reportsWebClient;

    public ReactiveReportsService(
        @Qualifier("webAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager,
        @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.manager = manager;
        this.reportsWebClient = reportsWebClient;
    }

    public Mono<String> loadReports(
        Authentication authentication,
        ServerWebExchange exchange) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("company")
                .principal(authentication)
                .attribute(ServerWebExchange.class.getName(), exchange)
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "No authorized client for company")))
            .flatMap(client -> callReportsApi(client));
    }

    private Mono<String> callReportsApi(
        OAuth2AuthorizedClient client) {

        String token = client.getAccessToken().getTokenValue();

        return reportsWebClient.get()
            .uri("/v1/reports")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

**Điểm quan trọng:**

1. <code>manager.authorize(request)</code> trả một <code>Mono</code>.
2. <code>switchIfEmpty(...)</code> xử lý trường hợp không có authorized client.
3. <code>flatMap</code> chỉ gọi Reports API sau khi đã có token.
4. WebClient gửi Bearer token **server-to-server**; không trả access token cho browser.
5. Code không gọi <code>block()</code>/<code>subscribe()</code> thủ công.
6. Mỗi request truyền đúng <code>Authentication</code> và <code>ServerWebExchange</code>.

Trong production, nên dùng DTO, timeouts, validation response, hạn chế kích thước payload và xử lý lỗi HTTP. Code trả <code>String</code> chỉ để tập trung vào lifecycle của manager.

### 9.3. Controller gọi service

~~~java
package example.reports;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    private final ReactiveReportsService reports;

    public ReportsController(ReactiveReportsService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports")
    public Mono<String> loadReports(
        Authentication authentication,
        ServerWebExchange exchange) {
        return reports.loadReports(authentication, exchange);
    }
}
~~~

Controller này được bảo vệ bởi <code>anyExchange().authenticated()</code> từ cấu hình web. Nếu ứng dụng có nhiều loại Authentication hoặc nhiều login providers, service cần kiểm tra principal có phù hợp với registration <code>company</code> trước khi authorize.

**Không mặc định dùng registration của user A để lấy token cho user B**. Một <code>Authentication</code> có thể thuộc service/tenant/issuer khác; kiểm tra registration và principal theo chính sách tích hợp.

### 9.4. Không block() để giải quyết Mono

Sai trong WebFlux handler:

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(request).block();
~~~

Blocking có thể chiếm event-loop thread, gây latency, cạn thread hoặc lỗi runtime. Dùng <code>flatMap</code>, <code>map</code>, <code>switchIfEmpty</code> và <code>onErrorResume</code> khi thực sự cần recovery.

Đừng gọi <code>subscribe()</code> thủ công trong controller rồi trả response trước khi token request/API call hoàn thành; như vậy mất error propagation, cancellation và reactive context.

## 10. Cách dùng WebClient OAuth2 filter thay vì tự gắn Bearer

Spring Security cung cấp:

**<code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>**.

Filter này phối hợp OAuth2 authorized client với <code>WebClient</code> và có thể dùng <code>ReactiveOAuth2AuthorizedClientManager</code> để authorize/refresh.

### 10.1. Cấu hình filter với manager đã tạo

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OAuth2ReportsWebClientConfig {

    @Bean("oauth2ReportsWebClient")
    WebClient oauth2ReportsWebClient(
        @Qualifier("webAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

        var oauth2Filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://api.example.org")
            .filter(oauth2Filter)
            .build();
    }
}
~~~

Đây là một **phương án thay thế** cho <code>reportsWebClient</code> gắn token thủ công ở mục 9. Không bắt buộc vừa tự đặt Bearer header vừa để OAuth2 filter đặt lại header.

### 10.2. Chọn registration cho mỗi request

Ví dụ trong reactive web handler có authentication/exchange context:

~~~java
return oauth2ReportsWebClient.get()
    .uri("/v1/reports")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Trong web exchange đang được Spring Security xử lý, filter có thể resolve principal và exchange phù hợp để gọi manager. Nếu sử dụng WebClient ở **ngoài** request context, không nên giả định những thông tin đó vẫn có sẵn.

Đối với các tình huống cần truyền rõ ngữ cảnh, API của filter cho phép cung cấp <code>Authentication</code>, <code>ServerWebExchange</code> hoặc authorized client qua request attributes theo phiên bản Spring Security đang dùng. Việc dùng helper nào nên tham chiếu API chính xác của version triển khai.

### 10.3. Gắn sẵn authorized client tường minh

Khi đã resolve <code>OAuth2AuthorizedClient</code>:

~~~java
return oauth2ReportsWebClient.get()
    .uri("/v1/reports")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

Trong ví dụ, <code>authorizedClient</code> là biến đã được resolve, không phải object người dùng tự tạo từ input browser.

Ưu điểm: code cho thấy token thuộc registration/principal nào. Nhược điểm: caller phải quản lý việc authorized client được lấy/làm mới đúng thời điểm; không dùng một instance đã hết hạn được cache trong singleton.

### 10.4. Cẩn trọng với default OAuth2 authorized client

Filter có thể hỗ trợ một chế độ chọn authorized client mặc định. Nếu bật không kiểm soát rồi dùng cùng WebClient gọi nhiều host, có nguy cơ vô tình gửi Bearer token tới URL không tin cậy.

An toàn hơn:

- WebClient dành riêng cho downstream API đáng tin.
- Registration ID được chọn rõ ràng bằng cấu hình/backend policy.
- Không truyền request URL tùy ý từ browser để WebClient tự gắn token.
- Tránh dùng token từ UserInfo/API A cho API B nếu audience/scope không hợp lệ.
- Đặt timeout, giới hạn redirect và xử lý HTTP failures thích hợp.

## 11. ServerOAuth2AuthorizedClientRepository: lưu vào đâu?

Trong reactive HTTP exchange, authorized-client repository có thể sử dụng WebSession hoặc delegate cho reactive service.

Những class cần biết:

- <code>WebSessionServerOAuth2AuthorizedClientRepository</code>.
- <code>AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository</code>.
- <code>ReactiveOAuth2AuthorizedClientService</code> và một implementation như <code>InMemoryReactiveOAuth2AuthorizedClientService</code>.

### 11.1. WebSessionServerOAuth2AuthorizedClientRepository

Repository này lưu authorized client theo WebSession, thích hợp cho những trường hợp muốn giữ token trong ngữ cảnh phiên web.

~~~text
Browser → Session Cookie
             └── WebSession
                   └── authorized client state
~~~

Nếu browser mất session hoặc callback quay về node khác không tìm được session, authorized-client lookup có thể không trả được token đã lưu.

### 11.2. AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository

Một repository phổ biến khác có thể dựa trên trạng thái authentication:

~~~text
Authenticated principal
    → lưu/đọc bằng ReactiveOAuth2AuthorizedClientService

Trường hợp chưa authenticated
    → fallback repository dựa trên WebSession theo cấu hình
~~~

Hành vi cụ thể phụ thuộc implementation và cấu hình. Điểm quan trọng là **repository web có thể được hậu thuẫn bởi service**, không phải mọi authorized client đều nằm trong cùng WebSession.

### 11.3. ReactiveOAuth2AuthorizedClientService

Interface có các phương thức như:

~~~java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

Mono<Void> removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

Đây là một **hợp đồng reactive**, không phải interface đồng bộ <code>OAuth2AuthorizedClientService</code>. Chỉ implement API bằng các operation blocking trên event-loop có thể phá vỡ lợi ích của WebFlux.

### 11.4. Session repository khác authorization request repository

Đừng nhầm:

| Repository | Dữ liệu | Vòng đời |
|---|---|---|
| <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> | Authorization request chứa state/PKCE trước callback | Từ redirect đến callback |
| <code>ServerOAuth2AuthorizedClientRepository</code> | Access/refresh tokens đã được cấp trong web context | Sau khi authorize/token exchange |
| <code>ServerSecurityContextRepository</code> | Authentication/SecurityContext người dùng | Các request thuộc phiên đăng nhập |

Trong Spring WebFlux, ba kho trạng thái này có mục đích khác nhau; không dùng authorization request repository để giữ refresh token lâu dài.

## 12. ReactiveOAuth2AuthorizedClientProvider: cấu hình grant phù hợp

Manager điều phối provider, nhưng provider mới thực hiện grant khi đủ điều kiện:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

Đây là ví dụ ghép provider, **không phải khuyến nghị bật tất cả grant cho mọi ứng dụng**.

| Provider | Khi nào dùng | Những giới hạn cần nhớ |
|---|---|---|
| <code>authorizationCode()</code> | OAuth2/OIDC browser authorization đã được khởi tạo theo flow hợp lệ | Không tự render OP login từ một job |
| <code>refreshToken()</code> | Có authorized client và refresh token còn dùng được | Không tự nâng scope |
| <code>clientCredentials()</code> | Service-to-service dùng Client credentials | Không tạo End-User Authentication |

### 12.1. Authorization code và login

<code>oauth2Login()</code> của WebFlux xử lý authorization initiation/callback. <code>DefaultReactiveOAuth2AuthorizedClientManager</code> hỗ trợ vòng đời authorized client nhưng không thay thế WebFilters, state/correlation, OIDC nonce, PKCE hoặc ID Token validation.

### 12.2. Refresh token

<code>refreshToken()</code> thường làm mới access token khi token cũ hết hạn/sắp hết hạn và có refresh token.

Nếu refresh thất bại với <code>invalid_grant</code>, có thể refresh token đã hết hạn, bị thu hồi hoặc một node khác đã sử dụng token đó khi provider bật rotation. Không giả định mọi lỗi chỉ do người dùng logout.

### 12.3. Client credentials

Nếu user web request cần gọi một **API service độc lập** bằng quyền của backend, có thể cấu hình một registration client credentials khác với OIDC login. Nhưng phải phân biệt:

~~~text
company-login   → user token / authorization_code
reports-service → service token / client_credentials
~~~

Không dùng service token để giả làm user, cũng không dùng OIDC access token dành cho UserInfo để gọi service API bất kỳ.

Trong background job không có exchange, chọn service reactive manager để xử lý client credentials.

## 13. Khi nào dùng AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager?

Tên hai manager gần giống nhau nhưng ngữ cảnh khác:

| Tiêu chí | DefaultReactiveOAuth2AuthorizedClientManager | AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager |
|---|---|---|
| Ngữ cảnh chính | HTTP request WebFlux | Service/background |
| Cần ServerWebExchange | Thường có trong flow web | Không |
| Storage | ServerOAuth2AuthorizedClientRepository | ReactiveOAuth2AuthorizedClientService |
| Ví dụ | WebFlux controller gọi Reports API thay user | Scheduled job dùng client credentials |
| Có thể dùng providers tùy biến | Có | Có |

### 13.1. Ví dụ manager cho job

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class BackgroundOAuth2ManagerConfig {

    @Bean("jobAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager jobAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService service) {

        var provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Job gọi:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-worker-runtime")
        .build();

Mono<OAuth2AuthorizedClient> client =
    jobAuthorizedClientManager.authorize(request);
~~~

Trong trường hợp này không truyền <code>ServerWebExchange</code>. <code>reports-worker-runtime</code> là **principal tổng hợp** dùng phân vùng storage của service manager, không làm access token biến thành token của một End-User.

Ví dụ registration tương ứng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token
~~~

Nếu dự án vừa có web manager vừa có job manager, sử dụng bean names và <code>@Qualifier</code> nhất quán; không inject ngẫu nhiên manager chỉ vì có cùng interface.

### 13.2. Scheduler và blocking

Một <code>@Scheduled</code> method của Spring thường có cơ chế lifecycle khác HTTP request. Có thể điều phối reactive pipeline từ job runner phù hợp với framework/version; không được <code>subscribe()</code> bừa bãi rồi đánh dấu job đã thành công trước khi pipeline kết thúc.

Nếu một scheduling framework cần phương thức đồng bộ, cần thiết kế ranh giới thread và completion/error handling rõ ràng thay vì gọi <code>block()</code> trên Netty event-loop. Không có WebFlux exchange trong scheduler vẫn là lý do chính để chọn service manager.

## 14. Authorization success/failure handler

<code>DefaultReactiveOAuth2AuthorizedClientManager</code> có các hook xử lý thành công/thất bại khi provider thực hiện authorization.

Khái niệm:

~~~text
manager.authorize(request)
    ├── load authorized client từ repository
    ├── provider cấp/refresh token
    ├── success handler: save authorized client
    └── failure handler: xử lý token/authorization failure theo policy
~~~

### 14.1. Mặc định lưu kết quả

Manager được thiết kế để lưu authorized client sau khi cấp token hoặc refresh thành công bằng cơ chế phù hợp với repository. Nếu ứng dụng thay thế success handler chỉ để ghi log:

~~~text
authorize → token mới A1
custom success handler → log only
next request → repository vẫn chứa A0
~~~

thì token mới có thể không được lưu. Nếu tùy biến success handler, cần duy trì save/persistence đúng ngữ cảnh.

### 14.2. Failure handler và invalid_grant

Nếu OP trả <code>invalid_grant</code> trong refresh flow, có thể refresh token không còn hợp lệ. Một số handler có thể loại bỏ authorized client khỏi storage để tránh retry mãi token cũ.

Nhưng **không phải mọi lỗi đều có nghĩa token phải bị xóa**:

- Timeout/HTTP 503 có thể là outage, không xác nhận token bị thu hồi.
- HTTP 401 từ API downstream có thể do token sai audience, Resource Server config hoặc token hết hạn.
- HTTP 403 có thể chỉ là thiếu scope/role; refresh không tự nâng quyền.
- Storage có thể vừa được instance khác cập nhật; xóa không điều kiện có thể xóa token mới.

Chính sách failure cần phân loại theo **Token Endpoint vs Resource Server**, mã lỗi OAuth2 và ngữ cảnh concurrency.

### 14.3. WebClient filter không luôn tự xử lý mọi API failure

Nếu tự đặt Bearer header trong <code>WebClient</code> như mục 9, manager **không tự thấy** downstream API trả 401/403. Khi dùng <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>, có thể cấu hình failure handler phù hợp; hành vi mặc định phụ thuộc constructor và Spring Security version.

Đừng giả định gọi <code>manager.authorize()</code> lần nữa luôn sinh token khác. Manager có thể trả token còn hạn theo metadata, ngay cả khi một Resource Server vừa từ chối nó vì audience sai hoặc bị revoke ngoài luồng.

## 15. Xử lý lỗi HTTP 401/403 từ Resource Server

| Phản hồi | Ý nghĩa thường gặp | Cách xử lý ở Client |
|---|---|---|
| <code>401</code> + Bearer <code>invalid_token</code> | Token không được chấp nhận (expiry/revoked/issuer/audience...) | Xác định nguyên nhân, refresh/reauthorize khi phù hợp |
| <code>401</code> không có Bearer error | Có thể thiếu credential hoặc cơ chế auth khác | Kiểm tra Authorization header và gateway |
| <code>403</code> + Bearer <code>insufficient_scope</code> | Token thiếu scope được yêu cầu | Kiểm tra grant/scopes/consent, không refresh mù |
| <code>403</code> khác | Role, tenant, ownership, WAF, gateway | Điều tra policy và nguồn response |
| <code>429</code> | Rate limit | Backoff/retry có giới hạn |
| <code>5xx</code> | Lỗi downstream | Có thể retry request an toàn theo policy |

**Cần phân biệt ID Token với access token.** OIDC Login thành công chứng minh danh tính user đối với Client, nhưng không tự cấp quyền gọi bất kỳ API nào. Resource Server vẫn kiểm tra access token.

Ví dụ WebClient phân loại:

~~~java
return webClient.get()
    .uri("/v1/reports")
    .retrieve()
    .onStatus(
        status -> status.value() == 403,
        response -> Mono.error(
            new IllegalStateException("Reports permission denied")))
    .onStatus(
        status -> status.value() == 401,
        response -> Mono.error(
            new IllegalStateException("Reports token rejected")))
    .bodyToMono(String.class);
~~~

Trong production nên dùng exception/DTO nghiệp vụ riêng và không trả raw error descriptions từ upstream cho browser. Cần xem <code>WWW-Authenticate</code> cùng API contract khi cần phân biệt <code>invalid_token</code> với <code>insufficient_scope</code>.

Không tự động retry POST/PUT có side effect nếu không có idempotency/recovery policy.

## 16. Multi-instance: WebSession và authorized-client storage

Khi có hai instance WebFlux:

~~~text
Browser → Load Balancer
            ├── Instance A
            └── Instance B
~~~

Một người dùng khởi tạo OAuth2 Login ở A nhưng callback được điều phối đến B. Nếu WebSession chỉ lưu tại A và không có session affinity, B có thể không tìm được authorization request/state.

Sau login, authorized client có thể nằm trong <code>WebSession</code> hoặc một reactive service riêng, tùy repository. Nếu storage không chia sẻ, request ở B cũng có thể không tìm được token dù session đã được phục hồi.

### 16.1. Không nhập nhằng ba trạng thái

~~~text
Authorization request repository:
    state, nonce/PKCE data trước callback

SecurityContext repository:
    Authentication của user đã đăng nhập

ServerOAuth2AuthorizedClientRepository:
    access token và refresh token đã được cấp
~~~

Ba nơi này có thể đều liên quan WebSession nhưng khác nhau về chức năng. Chuyển session sang Redis không mặc định biến mọi authorized-client service độc lập thành distributed storage.

### 16.2. Refresh token rotation và race

Giả sử A và B cùng lấy refresh token R0:

~~~text
A: POST /token với R0 → nhận access A1, refresh R1
B: POST /token với R0 → invalid_grant hoặc token reuse detection
~~~

Nếu OP bật refresh token rotation nghiêm ngặt, B có thể khiến token family bị ảnh hưởng. Shared storage **không tự khóa** toàn bộ refresh operation.

Chiến lược:

1. Dùng một coordinator/lock theo khóa authorized client.
2. Sau khi lấy lock, đọc lại authorized client mới nhất.
3. Nếu token đã được A cập nhật và còn dùng được, B không refresh lại.
4. Atomic save cả access và refresh token khi OP cấp token mới.
5. Bảo vệ stale update/delete bằng version/CAS/fencing nếu hệ thống cần.
6. Không xóa không điều kiện một authorized client mới chỉ vì request cũ báo <code>invalid_grant</code>.

Các cơ chế trên cần thiết kế riêng ở ứng dụng/token store; <code>DefaultReactiveOAuth2AuthorizedClientManager</code> không mặc định cung cấp distributed single-flight refresh.

### 16.3. WebSession, cookie và state

Session cookie có thể mất do sai domain, path, Secure/SameSite flag, reverse proxy hoặc chính sách browser. Callback <code>/login/oauth2/code/company</code> sẽ thất bại nếu không tìm được authorization request/state.

Không chữa bằng cách bỏ state validation. Kiểm tra trusted proxy, HTTPS, session store và cookie trước.

## 17. Reactive context propagation và giới hạn event-loop

Trong WebFlux, security context gắn với reactive pipeline:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Không nên dựa vào một static ThreadLocal để xác định người dùng trong mọi <code>flatMap</code>. Request có thể được xử lý trên nhiều thread và Reactor Context không giống Servlet request thread.

### 17.1. Không dùng blocking token store trên event-loop

Một <code>ReactiveOAuth2AuthorizedClientService</code> không nên thực hiện JDBC đồng bộ trực tiếp trên Netty event-loop, dù bề ngoài trả về <code>Mono</code>.

Nếu phải dùng thư viện blocking, cô lập nó trên scheduler phù hợp, ví dụ:

~~~java
return Mono.fromCallable(() ->
        blockingTokenRepository.load(registrationId, principalName))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Đây là bridge khi chưa có alternative reactive, không làm I/O trở thành non-blocking. Cần giới hạn thread/connection pool và theo dõi latency. Với hệ thống reactive thực sự, cân nhắc data access hỗ trợ non-blocking phù hợp.

### 17.2. Tránh subscribe thủ công

Sai:

~~~java
manager.authorize(request)
    .subscribe(client -> doSomething(client));

return Mono.just("done");
~~~

Kết quả request có thể trả về trước khi authorization và API call hoàn thành; lỗi bị tách khỏi response, mất cancellation hoặc context propagation.

Đúng hơn là:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Client not authorized")))
    .flatMap(client -> callApi(client));
~~~

Để Spring WebFlux subscribe publisher của handler đúng vòng đời request.

## 18. Nhiều SecurityWebFilterChain và ServerWebExchange

Một ứng dụng có thể vừa:

- Dùng OIDC browser login cho <code>/app/**</code>.
- Dùng JWT Resource Server authentication cho <code>/api/**</code>.

Khi đó phải bảo đảm:

1. Browser authorization initiation và callback thuộc web chain có <code>oauth2Login()</code>.
2. Web request có Authentication và WebSession đúng loại.
3. API chain không vô tình match callback trước web chain.
4. Các route API stateless không bị web login redirect không mong muốn.
5. WebClient gọi API đúng token và đúng audience.

Ví dụ hai chain:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SplitReactiveChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **phương án thay thế** cho chain ở mục 6.3, không ghép tất cả các cấu hình ví dụ vào cùng một dự án rồi tạo nhiều chain không chủ đích.

API chain có JWT Resource Server cần dependency và issuer/audience validation phù hợp. Chỉ tắt CSRF ở API bearer stateless khi mô hình bảo mật cho phép; không tắt CSRF toàn web chain dùng cookie/session.

### 18.1. Matcher và rule truy cập khác nhau

<code>securityMatcher(...)</code> chọn chain.

<code>authorizeExchange(...).pathMatchers(...)</code> đặt quyền trong chain đã chọn.

Một route <code>permitAll()</code> ở chain thứ hai không giúp callback nếu chain thứ nhất đã match đường dẫn đó.

## 19. Testing: kiểm tra reactive manager trong web request

Với <code>WebTestClient</code> và Spring Security Test, có thể mô phỏng OAuth2/OIDC principal để kiểm tra code xử lý authorized client mà không cần OP thật cho mọi unit test.

### 19.1. Dependencies test

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 19.2. Kiểm tra security route bằng mock OIDC Login

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class ReportsSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedUserCanEnterProtectedRoute() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .get()
            .uri("/reports")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

Đây là **khung kiểm tra route security**, cần mock/stub <code>ReactiveReportsService</code> và các dependency bên ngoài để assertion 2xx chỉ phản ánh authorization policy, không bị Reports API thật làm thất bại. Nếu muốn chỉ kiểm tra security rule, nên dùng một endpoint nội bộ không gọi downstream hoặc mock service tương ứng.

<code>mockOidcLogin()</code> tạo authentication thử trong WebFlux, **không kiểm tra thật** token endpoint, chữ ký ID Token, issuer, state/nonce/PKCE hay UserInfo. Phải có integration tests riêng cho những khía cạnh giao thức khi dự án yêu cầu.

### 19.3. Unit test manager/coordinator bằng StepVerifier

Một service sử dụng manager reactive có thể được test với một manager stub:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ManagerCallerTest {

    @Test
    void propagatesAuthorizationFailure() {
        var manager =
            Mockito.mock(ReactiveOAuth2AuthorizedClientManager.class);

        when(manager.authorize(any())).thenReturn(Mono.empty());

        // Publisher minh họa cho phần handling Mono.empty():
        Mono<OAuth2AuthorizedClient> pipeline =
            manager.authorize(
                org.springframework.security.oauth2.client.OAuth2AuthorizeRequest
                    .withClientRegistrationId("company")
                    .principal("test-principal")
                    .build())
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Not authorized")));

        StepVerifier.create(pipeline)
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Nếu dùng <code>StepVerifier</code>, cần test dependency <code>reactor-test</code> khi dependency management hiện tại chưa cung cấp:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

Đây là ví dụ về **xử lý reactive result**, không phải kiểm thử integration manager thật với ServerWebExchange. Để test exchange, có thể dùng <code>MockServerWebExchange</code>, mock repository và kiểm tra manager nhận đúng registration/principal/exchange context.

### 19.4. Những trường hợp cần kiểm tra

| Tình huống | Điều cần xác minh |
|---|---|
| User đã OIDC Login và có authorized client | API được gọi bằng token đúng registration/principal |
| Manager không tìm được registration | Có lỗi/empty được xử lý, không dùng token mặc định của user khác |
| Manager không có exchange cần thiết | Không fallback sang context giả không tin cậy |
| Access token còn hạn | Tái sử dụng authorized client khi hợp lệ |
| Access token gần hết hạn, có refresh token | Refresh flow đúng theo provider |
| Token endpoint trả <code>invalid_grant</code> | Failure handling không loop vô hạn |
| API trả 403 thiếu scope | Không auto refresh/reauthorize tùy tiện |
| Hai user dùng cùng registration | Token của user A không xuất hiện trong request của B |
| Multi-instance refresh rotation | Có điều phối/conditional update theo policy |
| Controller reactive | Không gọi <code>block()</code> trên request event-loop |

## 20. Troubleshooting: lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có bean <code>ReactiveClientRegistrationRepository</code> | Thiếu starter, properties, ứng dụng chạy MVC/Servlet | Kiểm tra dependencies, application type, registration |
| Không tạo được manager bean | Thiếu <code>ServerOAuth2AuthorizedClientRepository</code> | Kiểm tra WebFlux Security auto-configuration hoặc bean |
| <code>manager.authorize(...)</code> không trả client | Sai registration, grant/provider không phù hợp, chưa authorize | Kiểm tra <code>OAuth2AuthorizeRequest</code> và storage |
| Manager báo thiếu exchange | Không truyền ServerWebExchange context | Truyền exchange cho web manager hoặc dùng service manager ngoài request |
| User A dùng token user B | Principal lấy từ query parameter/static cache | Lấy từ Authentication tin cậy, phân vùng storage đúng |
| Login thành công nhưng service không tìm thấy token | Storage/repository khác nhau hoặc principal name mismatch | Kiểm tra wiring và principal key |
| <code>block()</code> gây lỗi trên event-loop | Dùng reactive publisher như đồng bộ | Compose <code>flatMap</code>, tránh blocking |
| WebClient không gửi Authorization | Chưa đặt token hoặc chưa cấu hình filter/attributes | Kiểm tra WebClient filter và authorized client selection |
| Downstream API trả 401 | Token expired, sai issuer/audience, bị revoke | Kiểm tra Token Endpoint và Resource Server |
| Downstream API trả 403 | Thiếu scope/role/tenant/ownership | Điều tra authorization, không retry refresh mù |
| Không refresh dù access token hết hạn | Thiếu refresh token/provider hoặc không gọi đúng manager | Kiểm tra grant, refresh setup và repository |
| Refresh liên tục | Clock skew quá lớn, token lifetime ngắn hoặc kết quả không lưu | Kiểm tra success handler và storage |
| Callback state mismatch | WebSession cookie/session store/chain sai | Kiểm tra authorization request repo và proxy |
| Chỉ node A có token | In-memory authorized client service hoặc WebSession local | Thiết kế shared storage/affinity theo nhu cầu |
| Nhiều node cùng refresh R0 | Không có distributed single-flight | Khóa theo key, reread, CAS/conditional delete |
| Scheduler không authorize được | Dùng web manager thiếu ServerWebExchange | Dùng AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager |
| Bean ambiguity | Nhiều ReactiveOAuth2AuthorizedClientManager bean | Dùng @Qualifier hoặc kiến trúc bean rõ ràng |
| Callback bị API chain nhận trước | SecurityWebFilterChain order/matcher sai | Giới hạn matcher API và route callback về web chain |

### 20.1. Trình tự chẩn đoán

~~~text
Ứng dụng có chạy WebFlux reactive?
   |
   v
ReactiveClientRegistration "company" tồn tại?
   |
   v
Request đã được OIDC Login / Authentication?
   |
   v
Đúng ServerWebExchange và principal?
   |
   v
DefaultReactiveOAuth2AuthorizedClientManager đúng bean?
   |
   v
ServerOAuth2AuthorizedClientRepository đúng storage?
   |
   v
Grant provider có hỗ trợ registration/context?
   |
   v
Access token còn hạn hay cần refresh?
   |
   v
Authorized client được lưu và trả trong Mono?
   |
   v
WebClient gắn đúng Bearer access token?
   |
   v
Resource Server có chấp nhận audience/scope/policy?
~~~

Không log raw access token, refresh token, ID Token, authorization code, PKCE verifier, session cookie hoặc client secret để chẩn đoán. Chỉ ghi registration ID, HTTP status, error code đã làm sạch, route template, correlation ID và token metadata cho phép.

## 21. Các tình huống và bài tập thực hành

### Bài 1 — Chọn đúng manager

Một WebFlux controller cần lấy access token của user đang đăng nhập qua OIDC và sử dụng <code>ServerWebExchange</code>.

**Hỏi:** Chọn manager nào?

**Đáp án:** <code>DefaultReactiveOAuth2AuthorizedClientManager</code> với <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code> và provider phù hợp.

### Bài 2 — Background job không có exchange

Một job chạy định kỳ cần access token client credentials nhưng không có HTTP request.

**Hỏi:** Có nên tự tạo <code>MockServerWebExchange</code> trong production?

**Đáp án:** Không. Dùng <code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code> với <code>ReactiveOAuth2AuthorizedClientService</code> và <code>clientCredentials()</code>.

### Bài 3 — OAuth2AuthorizeRequest

Đoạn code:

~~~java
OAuth2AuthorizeRequest.withClientRegistrationId("company")
    .principal(authentication)
    .attribute(ServerWebExchange.class.getName(), exchange)
    .build();
~~~

**Hỏi:** Ba thành phần giúp manager biết điều gì?

**Đáp án:** Registration ID chọn ClientRegistration; Authentication xác định principal; exchange cung cấp HTTP context cho repository web.

### Bài 4 — Principal đến từ browser

Một developer lấy:

~~~java
.principal(exchange.getRequest().getQueryParams().getFirst("user"))
~~~

**Hỏi:** Rủi ro?

**Đáp án:** Browser có thể chọn principalName của người khác, dẫn đến lookup/token leakage sai quyền. Lấy principal từ Authentication đã xác thực.

### Bài 5 — Mono.empty()

Một manager không thể authorize và trả <code>Mono.empty()</code>.

**Hỏi:** Có thể cast kết quả <code>authorize(...)</code> thành <code>OAuth2AuthorizedClient</code> không?

**Đáp án:** Không. Phải compose reactive pipeline và xử lý empty/error bằng <code>switchIfEmpty</code>, không dùng token của người khác làm fallback.

### Bài 6 — Refresh token không có

User login OIDC hợp lệ nhưng authorized client có <code>refreshToken=null</code>, access token hết hạn.

**Hỏi:** Manager có thể refresh token bằng <code>refreshToken()</code> không?

**Đáp án:** Không nếu chưa có refresh token hợp lệ. Tùy grant/provider, có thể phải thực hiện authorization code flow mới hoặc cơ chế cấp token phù hợp khác.

### Bài 7 — Browser login không tự cấp quyền Reports API

ID Token hợp lệ, nhưng access token chỉ được cấp cho UserInfo Endpoint. WebClient gửi token sang Reports API.

**Hỏi:** Manager có đảm bảo API nhận token không?

**Đáp án:** Không. Manager quản lý token; Resource Server vẫn kiểm tra audience/scope và policy riêng.

### Bài 8 — Logout và storage

Người dùng logout khỏi WebFlux session. Authorized client được lưu trong reactive service persistent.

**Hỏi:** Có thể chắc chắn access/refresh token đã bị thu hồi tại OP?

**Đáp án:** Không. Session logout, xóa local authorized client và token revocation là các thao tác khác nhau; phải thiết kế cleanup/revocation khi cần.

### Bài 9 — Nhiều instance và refresh race

Instance A/B cùng giữ refresh token R0. A refresh thành công, B nhận <code>invalid_grant</code>.

**Hỏi:** Shared database tự giải quyết race chưa?

**Đáp án:** Chưa. Cần điều phối trước token refresh, reread authorized client sau lock và bảo vệ conditional save/remove.

### Bài 10 — Controller blocking

~~~java
return Mono.just(manager.authorize(request).block());
~~~

**Hỏi:** Vì sao không nên làm như vậy?

**Đáp án:** Block event-loop và phá reactive flow. Trả trực tiếp Mono hoặc compose <code>flatMap</code>.

### Bài 11 — Thực hành cấu hình dự án

1. Tạo Spring Boot WebFlux app với OAuth2 Client starter.
2. Cấu hình OIDC registration <code>company</code> qua issuer của OP thử nghiệm.
3. Tạo <code>SecurityWebFilterChain</code> dùng <code>oauth2Login()</code>/<code>oauth2Client()</code>.
4. Tạo <code>DefaultReactiveOAuth2AuthorizedClientManager</code> với Authorization Code và Refresh Token providers.
5. Xây <code>OAuth2AuthorizeRequest</code> từ registration ID, Authentication và ServerWebExchange.
6. Gọi <code>manager.authorize()</code> và xử lý Mono theo chuẩn reactive, không <code>block()</code>.
7. Gắn authorized client vào WebClient để gọi API thử **đúng audience/scope**.
8. Kiểm tra missing registration, missing authorized client, token expiry, HTTP 401 và 403.
9. Thử deploy hai instance, đánh giá WebSession và authorized client storage.
10. Kiểm tra access token không xuất hiện trong browser response hoặc application log.

## 22. Ghi nhớ

- **<code>DefaultReactiveOAuth2AuthorizedClientManager</code>** là implementation của <code>ReactiveOAuth2AuthorizedClientManager</code> thích hợp cho **HTTP request WebFlux có <code>ServerWebExchange</code>**.
- Manager kết hợp <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code> và <code>ReactiveOAuth2AuthorizedClientProvider</code> để quản lý authorized client.
- <code>OAuth2AuthorizeRequest</code> cần registration ID, **principal tin cậy** và exchange context phù hợp. Không lấy principalName tùy ý từ browser.
- <code>authorize(...)</code> trả <code>Mono&lt;OAuth2AuthorizedClient&gt;</code>; dùng <code>flatMap</code>/<code>switchIfEmpty</code>, không <code>block()</code> hoặc <code>subscribe()</code> tùy tiện trong request handler.
- <code>OAuth2AuthorizedClient</code> chứa access token/refresh token đã được cấp; nó khác <code>ClientRegistration</code> và <code>OidcUser</code>.
- <code>ServerOAuth2AuthorizedClientRepository</code> lưu token trong web context; <code>ReactiveOAuth2AuthorizedClientService</code> có thể được dùng làm storage backend tùy cấu hình.
- Với **background job không có exchange**, thường chọn **<code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code>**.
- <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> có thể tích hợp manager vào WebClient, nhưng phải chỉ định đúng registration/principal và tránh gửi Bearer token tới host không được tin cậy.
- Access token hợp lệ không mặc nhiên có quyền truy cập mọi Resource Server. Cần audience, scope, role/tenant/ownership và authorization đúng.
- Khi chạy nhiều instance, cần tính tới WebSession sharing, token persistence, refresh token rotation và race conditions; manager mặc định không tự cung cấp distributed locking.
- Bảo vệ client secret, access/refresh token và session cookies; giữ HTTPS, CSRF/state/nonce/PKCE theo giao thức và không log credential.

### Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code>, providers và authorized client repositories.
- **Spring Security Java API — DefaultReactiveOAuth2AuthorizedClientManager:** constructor, <code>authorize</code>, provider, context attributes và success/failure handlers.
- **Spring Security Java API — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager:** quản lý authorized client bên ngoài ServerWebExchange.
- **Spring Security Java API — ServerOAuth2AuthorizedClientRepository:** load/save/remove authorized client trong HTTP exchange.
- **Spring Security Java API — ServerOAuth2AuthorizedClientExchangeFilterFunction:** WebClient integration, request attributes và failure handling.
- **Spring Security Reference — Reactive OAuth2 Login:** SecurityWebFilterChain, Authorization Code callback, OIDC authentication.
- **Spring Framework Reference — WebFlux/WebClient:** ServerWebExchange, Reactor Context, non-blocking HTTP.
- **Spring Security Test — WebTestClient:** mock OIDC authentication và reactive security tests.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Client Credentials và Refresh Token grants.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE cho Authorization Code Flow.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token protection/rotation.
- **OpenID Connect Core 1.0:** ID Token, subject/issuer, authentication flow và UserInfo.
