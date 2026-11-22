# 15.11. Cấu hình oauth2Client và liên kết với manager tùy chỉnh

## 1. Bài toán: đã bật oauth2Client nhưng HTTP client chưa dùng chính sách token mới

Giả sử **Employee Portal** là một ứng dụng **Spring Boot 3, Spring Security 6, Servlet/Spring MVC**. Người dùng đăng nhập với OpenID Connect (OIDC), sau đó Portal gọi **Orders API** thay mặt người dùng. Portal còn có một tác vụ chạy định kỳ để gọi **Reports API** bằng quyền của chính ứng dụng.

Đội phát triển muốn:

- Đăng nhập người dùng qua `oauth2Login()`.
- Quản lý access token/refresh token khi gọi Orders API.
- Dùng `client_credentials` cho tác vụ nền Reports API.
- Chọn thời điểm refresh token và xử lý lỗi cấp token theo chính sách riêng.
- Sử dụng một **`OAuth2AuthorizedClientManager` tùy chỉnh**, thay vì mỗi nơi tự gọi token endpoint.

Một cấu hình có thể đã tồn tại:

~~~java
http.oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

Nhưng chỉ thêm một bean `OAuth2AuthorizedClientManager` không nhất thiết khiến **mọi HTTP client, OAuth2 login filter hoặc background job** tự động sử dụng manager đó. Cần hiểu manager được tạo từ những thành phần nào, **đối tượng nào gọi manager**, và **nơi nào phải truyền instance manager vào rõ ràng**.

**Ý chính của bài:** `oauth2Client()` cấu hình các thành phần OAuth2 Client trong **Spring Security Servlet filter chain**; `OAuth2AuthorizedClientManager` điều phối **authorization/refresh** của một authorized client; còn **RestClient, WebClient, controller hoặc service** phải được liên kết với manager theo đúng cơ chế tích hợp được dùng. Đây là các trách nhiệm có liên quan nhưng không phải một API duy nhất.

> Các ví dụ sử dụng Java 17+, Spring Boot 3 và Spring Security 6. Mẫu `OAuth2ClientHttpRequestInterceptor` dành cho `RestClient` thuộc thế hệ Spring Security **6.4+**; với phiên bản cũ hơn, sử dụng `WebClient` trong Servlet hoặc cơ chế gọi manager thích hợp phiên bản. Nội dung tập trung **Servlet**, không sao chép trực tiếp sang WebFlux.

## 2. Kiến trúc và các đối tượng tham gia

| Thành phần | Vai trò | Có giữ token không? |
|---|---|---|
| `ClientRegistrationRepository` | Chứa cấu hình client: registration ID, grant type, client ID, provider endpoints, scope | Không; là metadata/client registration |
| `OAuth2AuthorizationRequestResolver` | Tạo authorization request để browser bắt đầu Authorization Code Flow | Không lưu access token |
| `OAuth2AuthorizationRequestRedirectFilter` | Chuyển browser tới Authorization Server | Không quản lý token đã cấp |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback đăng nhập OAuth2/OIDC | Phối hợp token exchange cho login |
| `OAuth2AuthorizedClient` | Biểu diễn client đã được ủy quyền cho một principal | Có access token và refresh token nếu được cấp |
| `OAuth2AuthorizedClientRepository` | Lưu/truy xuất authorized client trong ngữ cảnh Servlet request/response | Có thể lưu hoặc chuyển tới service bên dưới |
| `OAuth2AuthorizedClientService` | Lưu/truy xuất authorized client theo registration và principal name | Có, tùy implementation |
| `OAuth2AuthorizedClientProvider` | Thực thi logic cho từng grant, như authorization_code, refresh_token, client_credentials | Sử dụng/nhận token trong quá trình authorize |
| `OAuth2AuthorizedClientManager` | Điều phối registration, token lifecycle, provider và lưu kết quả | Điều phối, không nhất thiết tự lưu vĩnh viễn |
| **HTTP client gọi API** | Gửi Bearer token tới Resource Server | Được manager/integration cung cấp token |

### 2.1. Tổng quan luồng

~~~mermaid
flowchart TD
    B["Browser đã login qua OIDC"] --> C["Controller / BFF endpoint"]
    C --> D["RestClient hoặc WebClient có OAuth2 integration"]
    D --> M["OAuth2AuthorizedClientManager tùy chỉnh"]
    M --> R["ClientRegistrationRepository"]
    M --> S["OAuth2AuthorizedClientRepository / Service"]
    M --> P["OAuth2AuthorizedClientProvider chain"]
    P --> AC["authorization_code"]
    P --> RT["refresh_token"]
    P --> CC["client_credentials"]
    RT --> AS["Authorization Server / Token endpoint"]
    CC --> AS
    AC --> AS
    AS --> M
    M --> D
    D --> API["Orders API / Reports API"]
~~~

Trong flowchart, provider `authorization_code` còn cần **browser redirect/callback** khi chưa có quyền; không có nghĩa một lời gọi RestClient trong background job có thể tự hoàn tất interactive login mà không có người dùng.

## 3. Ba cấu hình rất giống tên nhưng không thể thay thế nhau

### 3.1. oauth2Login()

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

Đây là cấu hình cho **người dùng đăng nhập** qua OAuth 2.0/OIDC: redirect đến nhà cung cấp, xử lý callback, đổi authorization code lấy token, xác minh OIDC và tạo `Authentication`/`SecurityContext`.

### 3.2. oauth2Client()

~~~java
http.oauth2Client(Customizer.withDefaults());
~~~

Đây là cấu hình hỗ trợ **OAuth2 Client authorization** của Servlet application, bao gồm luồng liên quan đến Authorization Code Grant và những thành phần cần thiết trong security filter chain. Nó không tự làm một HTTP client bất kỳ biết nên dùng registration ID và principal nào.

### 3.3. oauth2ResourceServer()

~~~java
http.oauth2ResourceServer(resourceServer ->
    resourceServer.jwt(Customizer.withDefaults()));
~~~

Đây là cấu hình để **ứng dụng nhận và xác minh Bearer token** ở vai trò Resource Server. Nó **không** giúp Portal chủ động xin token để gọi Orders API. Nếu Portal vừa là OAuth2 Client vừa bảo vệ API của chính mình, có thể cần cả hai nhóm cấu hình nhưng phải hiểu từng endpoint và security chain riêng.

| Nhu cầu | Cấu hình / thành phần phù hợp |
|---|---|
| Đăng nhập bằng OIDC | `oauth2Login()` |
| OAuth2 client authorization qua Servlet filters | `oauth2Client()` |
| Giải quyết token khi gọi API | `OAuth2AuthorizedClientManager` cùng HTTP client integration |
| Nhận Bearer token và kiểm tra JWT | `oauth2ResourceServer()` |
| Tùy biến HTTP POST đổi code trong login | Token response client của `oauth2Login().tokenEndpoint()` |
| Tùy biến refresh/client_credentials khi gọi API | Authorized-client provider/manager tương ứng |

**Không mặc định một manager tùy chỉnh sẽ thay toàn bộ token exchange của `oauth2Login()`.** Chúng là những integration point khác nhau.

## 4. OAuth2AuthorizedClientManager thực hiện công việc gì?

Interface trên Servlet:

~~~java
package org.springframework.security.oauth2.client;

public interface OAuth2AuthorizedClientManager {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizeRequest authorizeRequest
    );
}
~~~

Một `OAuth2AuthorizeRequest` cung cấp ngữ cảnh như:

- **clientRegistrationId** hoặc authorized client hiện có.
- **principal** liên quan.
- Các attributes cần thiết cho grant và HTTP request context.

Manager thường:

1. Xác định `ClientRegistration`.
2. Tải `OAuth2AuthorizedClient` đã lưu nếu có.
3. Tạo `OAuth2AuthorizationContext` để provider xem xét.
4. Gọi `OAuth2AuthorizedClientProvider.authorize(context)`.
5. Lưu authorized client khi cấp mới/làm mới thành công theo handler.
6. Xử lý lỗi và loại token không hợp lệ theo failure handler/chính sách phù hợp.
7. Trả authorized client cho thành phần gọi.

### 4.1. Giá trị trả về null không có nghĩa principal đã logout

Nếu `authorize(...)` trả `null`, điều đó thường có nghĩa **manager không cấp/trả được một authorized client phù hợp với request và provider đã cấu hình**, chứ không tự kết luận HTTP session không còn authenticated.

Ngược lại, có `OAuth2AuthorizedClient` cũng không có nghĩa token chắc chắn được Resource Server chấp nhận: token có thể bị thu hồi, thiếu scope hoặc sai audience.

### 4.2. Manager không phải nơi ghi đè quyền người dùng

Manager quản lý token/authorization grant, không tự quyết định người dùng có quyền xóa đơn hàng nào. Portal và Orders API vẫn phải áp dụng **authorization** theo principal, tenant, resource và scope phù hợp.

## 5. Hai manager phổ biến trên Servlet

| Tiêu chí | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Ngữ cảnh thiết kế chính | Servlet **HttpServletRequest/HttpServletResponse** | Tác vụ ngoài request, ví dụ scheduled job, service worker |
| Phụ thuộc | `ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientService` |
| Token storage | Qua authorized-client repository | Qua authorized-client service |
| Principal | Authentication của user hoặc principal phù hợp được truyền | Principal string/Authentication theo service/task |
| Phù hợp | User-authorized API call trong Portal web | Machine-to-machine `client_credentials`, batch |
| Ví dụ | Orders API thay mặt user đăng nhập | Reports API của scheduled job |

Hai class đều thực thi `OAuth2AuthorizedClientManager`, nhưng **không thể thay tùy tiện**:

- `DefaultOAuth2AuthorizedClientManager` cần ngữ cảnh Servlet request/response để phối hợp repository. Dùng nó trong job chạy ngoài HTTP request thường không phù hợp.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` không yêu cầu Servlet request; thích hợp cho tác vụ nền hoặc xử lý sự kiện.

Không dùng một singleton manager với principal “admin” mặc định để tất cả request web gửi token thay mặt admin. **Principal identity phải đến từ ngữ cảnh xác thực phù hợp.**

## 6. ClientRegistration dùng chung cho các grant

Ví dụ Portal có hai OAuth2 client registrations:

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
          reports-service:
            provider: company
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Giải thích:

- `company` dùng `authorization_code` để liên kết với **user** và cho phép Portal gọi Orders API nếu provider cấp scope tương ứng.
- `reports-service` dùng `client_credentials` cho **dịch vụ**; không cần người dùng login và không cần redirect URI.
- Cả hai được quản lý bởi một issuer/provider `company`, nhưng là **hai registrations khác nhau**, có client credentials và quyền riêng.
- Các biến `OIDC_CLIENT_SECRET` và `REPORTS_CLIENT_SECRET` phải được cung cấp ở runtime qua secret manager/cơ chế bảo mật phù hợp, không commit vào Git.

Nếu OP cấp access token có audience riêng cho Orders API/Reports API, cần đảm bảo registration/scopes và cấu hình Authorization Server phát token đúng API đích. Đừng giả định cùng issuer là token nào cũng dùng được cho mọi Resource Server.

### 6.1. Phân biệt registrationId, principalName và scope

~~~text
registrationId = company
principalName  = employee-0042
scopes         = openid profile orders.read

registrationId = reports-service
principalName  = reports-worker
scopes         = reports.read
~~~

`registrationId` chỉ ra **OAuth Client configuration**. `principalName` là tên principal dùng khi quản lý authorized client. **Scope** mô tả quyền yêu cầu/cấp cho token. Chúng không thể thay thế nhau.

## 7. Dependencies và Servlet SecurityFilterChain

### 7.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Chỉ cần nếu chọn WebClient làm HTTP client trong ứng dụng Servlet:
    implementation 'org.springframework:spring-webflux'
}
~~~

Khi ứng dụng đã có `spring-boot-starter-web`, việc thêm `WebClient` không tự biến ứng dụng thành WebFlux. Spring Boot thường ưu tiên loại web application **Servlet** nếu cả Spring MVC và WebFlux cùng có trên classpath, trừ khi cấu hình application type khác.

### 7.2. SecurityFilterChain

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
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đoạn này bật cả **login** lẫn **OAuth2 Client support** trên Servlet. Nếu các API cần trả 401 JSON thay vì redirect trang HTML tới IdP, nên có exception handling/security matcher tương ứng.

**Chưa có manager tùy chỉnh nào được nối vào RestClient/WebClient ở đây.** Phần tiếp theo tạo manager rồi truyền nó vào HTTP client mà service thực sự sử dụng.

## 8. Tạo manager tùy chỉnh cho Servlet request

Ví dụ tạo `DefaultOAuth2AuthorizedClientManager` với provider chain có `authorization_code`, `refresh_token` và `client_credentials`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientConfig {

    @Bean("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Các điểm quan trọng của code:**

1. `ClientRegistrationRepository` được Spring Boot xây dựng từ cấu hình `spring.security.oauth2.client.*`.
2. `OAuth2AuthorizedClientRepository` hỗ trợ lấy/lưu authorized client trong ngữ cảnh HTTP Servlet.
3. `OAuth2AuthorizedClientProviderBuilder` xác định **grant nào manager được phép điều phối**.
4. `manager.setAuthorizedClientProvider(provider)` liên kết provider chain với manager.
5. Bean name `webAuthorizedClientManager` giúp phân biệt manager dành cho request web với manager của background job.

Đây là **manager tùy chỉnh** vì bạn chủ động quyết định provider chain và có thể bổ sung chính sách lưu/xử lý token sau này. Nó vẫn dựa trên các implementation chuẩn của Spring Security; không cần tự viết HTTP POST tới token endpoint.

### 8.1. Có cần bật tất cả ba grant không?

Không. Nếu manager chỉ dùng cho user-authorized API call, có thể chỉ cần:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

Nếu manager chỉ dùng cho service-to-service, có thể dùng:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

**Grant được hỗ trợ bởi provider chain không làm thay đổi `authorization-grant-type` của từng `ClientRegistration`.** Registration nào dùng grant nào vẫn do cấu hình và ngữ cảnh grant quyết định.

Không mở rộng grant/scope một cách tùy tiện chỉ để “đảm bảo có token”. Grant là một phần của chính sách ủy quyền.

## 9. Liên kết manager tùy chỉnh với RestClient (Spring Security 6.4+)

Từ Spring Security 6.4, có integration cho Spring Framework `RestClient` thông qua:

~~~java
org.springframework.security.oauth2.client.web.client
    .OAuth2ClientHttpRequestInterceptor
~~~

HTTP interceptor này có thể gọi `OAuth2AuthorizedClientManager` để tìm/cấp/làm mới authorized client và đặt access token vào Bearer header của request đi tới Resource Server.

### 9.1. Bean RestClient nhận đúng manager

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfig {

    @Bean("ordersRestClient")
    RestClient ordersRestClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

Trong production, nên lấy `https://orders.example.test` từ application property được kiểm soát và đặt timeout/TLS/proxy phù hợp. Ví dụ chỉ tập trung vào chỗ **truyền manager**.

**Dòng mấu chốt:**

~~~java
new OAuth2ClientHttpRequestInterceptor(manager)
~~~

Chính đối tượng interceptor này **dùng manager đã truyền vào**. Việc `http.oauth2Client()` có mặt trong SecurityFilterChain không tự gắn interceptor vào mọi instance `RestClient`.

### 9.2. Chỉ định clientRegistrationId khi gọi API

Một controller có thể sử dụng `ordersRestClient`:

~~~java
package com.example.portal.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

@RestController
public class OrdersController {

    private final RestClient ordersRestClient;

    public OrdersController(
        @Qualifier("ordersRestClient") RestClient ordersRestClient
    ) {
        this.ordersRestClient = ordersRestClient;
    }

    @GetMapping("/bff/orders")
    public String orders() {
        return ordersRestClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .body(String.class);
    }
}
~~~

`clientRegistrationId("company")` chỉ rõ **registration mà HTTP client phải dùng để giải quyết token**. Trong một HTTP request đã được xác thực, interceptor/manager cần lấy đúng principal và Servlet request context; vì vậy integration web nên được dùng trong đúng ngữ cảnh mà nó hỗ trợ.

**Không dùng registration `reports-service` để gọi Orders API thay mặt người dùng** chỉ vì reports-service cũng có access token. Token của service và token được cấp cho user khác nhau về subject, scope/audience và chính sách.

### 9.3. Có nên đặt registration mặc định cho mọi request?

Một số integration cho phép cấu hình default registration/authorized client. Nếu ứng dụng có nhiều Resource Servers hoặc nhiều loại principal, **không nên** dùng một Bearer token mặc định cho tất cả request HTTP.

Ưu tiên chỉ định registration **rõ ràng tại nơi gọi API**, hoặc gắn một HTTP client chuyên biệt với registration đã kiểm soát. Điều này tránh gửi token của user hoặc dịch vụ đến một hostname không dự kiến.

### 9.4. Tùy chỉnh failure handling

Nếu Orders API trả `401 invalid_token`, integration có thể cần **authorized-client failure handler** phù hợp để loại bỏ authorized client/token không hợp lệ khỏi repository/service hoặc yêu cầu cấp quyền lại. Chính sách cụ thể phụ thuộc phiên bản Spring Security, HTTP client và cách xây dựng manager.

Không tự động xóa HTTP session của người dùng khi token của một API bị từ chối; cũng không retry vô hạn bằng đúng token đã bị Resource Server bác bỏ. Ở phần vận hành, cần phân biệt `invalid_token` với `insufficient_scope` và lỗi dịch vụ 5xx.

## 10. Liên kết manager với WebClient trong ứng dụng Servlet

Nếu ứng dụng Spring MVC cần sử dụng `WebClient` để gọi API, Spring Security cung cấp:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

**Tên package chứa `reactive` không có nghĩa application này phải dùng SecurityWebFilterChain.** Class này hỗ trợ `WebClient` khi chạy trong môi trường Servlet, với manager **đồng bộ** `OAuth2AuthorizedClientManager`.

### 10.1. Bean WebClient

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Spring Security tự cung cấp nhiều tiện ích cho Authorization Header và authorized-client handling. Điểm cần quan sát vẫn là **constructor nhận chính manager mà ta đã cấu hình**.

### 10.2. Gọi API bằng WebClient

~~~java
package com.example.portal.service;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function
    .client.ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId;

@Service
public class OrdersGateway {

    private final WebClient client;

    public OrdersGateway(
        @Qualifier("ordersWebClient") WebClient client
    ) {
        this.client = client;
    }

    public Mono<String> fetchOrders() {
        return client.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Đây là **ứng dụng Servlet sử dụng WebClient**; `Mono` là kiểu kết quả của WebClient, nhưng **authentication và manager vẫn là Servlet**. Nếu gọi WebClient ngoài request thread, cần cẩn trọng việc truyền `SecurityContext`/Servlet request context đúng chỗ. Không tự giả định ThreadLocal của Spring MVC được truyền qua mọi reactive scheduler.

Không dùng `ReactiveOAuth2AuthorizedClientManager` hoặc `ServerHttpSecurity` chỉ vì ứng dụng MVC có một bean `WebClient`.

## 11. So sánh RestClient và WebClient khi dùng manager tùy chỉnh

| Tiêu chí | RestClient trên Servlet | WebClient trên Servlet |
|---|---|---|
| HTTP abstraction | Đồng bộ | API reactive/non-blocking |
| OAuth2 integration | `OAuth2ClientHttpRequestInterceptor` (6.4+) | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| Manager sử dụng | `OAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Security chain | `HttpSecurity` | **Vẫn** là `HttpSecurity` |
| Cách chọn registration | Request attributes/clientRegistrationId resolver | Exchange attributes `clientRegistrationId(...)` |
| Lưu/refresh token | Theo manager/provider/repository | Theo manager/provider/repository |
| Cần chú ý | Timeout, pool, không lộ Bearer token | Context propagation, reactive pipeline, không lộ token |

**Tùy biến manager** là một việc; **truyền manager vào HTTP integration** là việc thứ hai. Đừng chỉ tạo bean rồi mong mọi `RestClient.create(...)` hoặc `WebClient.create(...)` đều tự sử dụng token của manager.

## 12. Manager riêng cho scheduled job dùng client_credentials

Một tác vụ định kỳ không có browser, HTTP session hoặc `HttpServletRequest`. Thay vì dùng `DefaultOAuth2AuthorizedClientManager` cho web request, tạo `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 12.1. Cấu hình manager cho job

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class JobAuthorizedClientConfig {

    @Bean("jobAuthorizedClientManager")
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clientService
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Manager này:

- Chỉ hỗ trợ `client_credentials`, vì job không cần interactive OIDC login.
- Lưu/tải authorized client qua `OAuth2AuthorizedClientService`.
- Không cần Servlet request/response.
- Dùng registration riêng `reports-service` với scopes tối thiểu.

### 12.2. Dùng manager trong job

~~~java
package com.example.portal.jobs;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsJob {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportsApi =
        RestClient.create("https://reports.example.test");

    public ReportsJob(
        @Qualifier("jobAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        this.manager = manager;
    }

    public String fetchDailySummary() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("reports-worker")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for reports-service"
            );
        }

        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        return reportsApi.get()
            .uri("/api/reports/daily")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

Ở đây `principal("reports-worker")` là **tên ổn định của service principal trong cơ chế lưu authorized client**, không phải một user OIDC được Portal xác thực. Vì token thuộc grant `client_credentials`, việc gọi API dựa trên quyền được cấp cho **service client**.

Ví dụ dùng `RestClient` thủ công để làm rõ quá trình manager trả token. Với ứng dụng thực tế, HTTP client cần được inject/configure đúng timeout, TLS, proxy, logging và error handling.

**Không dùng mẫu `.principal("admin")` với registration user authorization_code để truy cập token của người dùng khác.** Principal string không phải bằng chứng đăng nhập người dùng.

## 13. Tại sao cần hai bean manager có tên rõ ràng?

Ứng dụng vừa có web request vừa có background job có thể khai báo:

~~~text
webAuthorizedClientManager -> DefaultOAuth2AuthorizedClientManager
jobAuthorizedClientManager -> AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

Khi cùng có hai bean thực thi `OAuth2AuthorizedClientManager`, việc injection không chỉ rõ tên có thể mơ hồ. Dùng `@Qualifier`:

~~~java
public MyService(
    @Qualifier("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager manager
) {
    this.manager = manager;
}
~~~

hoặc đặt các bean specialized theo type/configuration phù hợp và xác định primary khi thực sự cần.

Không chọn bean bằng cách phụ thuộc vào thứ tự tạo bean, tên class hay giả định một bean luôn được Spring Boot ưu tiên. Khi có nhiều managers, **mỗi consumer phải biết mình cần manager nào**.

### 13.1. Có nên gom mọi grant vào một manager?

Có thể, nhưng không phải lúc nào cũng hợp lý:

- **Web manager** xử lý context request/principal và có thể bao gồm authorization code + refresh token.
- **Job manager** xử lý service principal và client credentials, thường dùng store khác.
- Quản lý riêng giúp giới hạn grant mà từng thành phần có thể sử dụng và giảm khả năng vô tình lấy sai token.

Chỉ hợp nhất nếu có lý do rõ, kiểm soát được principal, storage và context để mọi caller không vượt ranh giới tin cậy.

## 14. Có cần gắn manager vào oauth2Client() DSL không?

Đây là điểm dễ nhầm nhất của đề bài.

Khi viết:

~~~java
http.oauth2Client(Customizer.withDefaults());
~~~

ta đang cấu hình **Spring Security Servlet OAuth2 Client integration** ở tầng filter. Trong DSL này có các tùy biến như **client registration repository**, **authorized client repository**, **authorized client service** hoặc chi tiết **Authorization Code Grant** theo phiên bản.

Nhưng ở nhiều phiên bản Spring Security, không có một lệnh duy nhất dạng:

~~~java
// Mã minh họa một cách nghĩ SAI; không phải API được bảo đảm:
http.oauth2Client(oauth2 -> oauth2
    .authorizedClientManager(myManager));
~~~

Không nên sao chép đoạn giả lập đó vào dự án. **Manager là integration point riêng** cho các thành phần dùng authorized client:

~~~text
SecurityFilterChain:
    http.oauth2Client(...)

Manager bean:
    DefaultOAuth2AuthorizedClientManager(...)

HTTP client gọi Resource Server:
    new OAuth2ClientHttpRequestInterceptor(manager)
    hoặc
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

Nếu yêu cầu là **tùy biến provider chain/refresh/client credentials khi gọi API**, hãy cấu hình manager rồi **truyền vào HTTP client**.

Nếu yêu cầu là **tùy biến authorization request hoặc bước đổi code trong Servlet filter**, hãy sử dụng hook của **`oauth2Client().authorizationCodeGrant(...)`** hoặc **`oauth2Login()`** đúng luồng.

### 14.1. Ví dụ tùy biến Authorization Code Grant qua oauth2Client DSL

Spring Security Servlet cho phép thay những thành phần của authorization-code flow:

~~~java
http.oauth2Client(oauth2 -> oauth2
    .authorizationCodeGrant(authorizationCode -> authorizationCode
        .authorizationRequestResolver(customAuthorizationRequestResolver)
        .authorizationRequestRepository(customAuthorizationRequestRepository)
    )
);
~~~

Đây là **đoạn minh họa về hook**, trong đó `customAuthorizationRequestResolver` và `customAuthorizationRequestRepository` là các instance phải được cấu hình phù hợp trong ứng dụng. Hook này xử lý **authorization request ban đầu**, không đồng nghĩa thay provider chain dùng cho refresh token.

Trường hợp dùng **OAuth2 Login**, hook tương ứng thường nằm dưới:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(customAuthorizationRequestResolver)
    )
);
~~~

Nếu cấu hình cả `oauth2Login()` và `oauth2Client()`, cần kiểm tra filter, base URI, repository và luồng thực tế để tránh tạo các cơ chế authorization request chồng chéo. Không mặc định cùng một bean resolver sẽ được mọi flow sử dụng nếu không được gắn vào đúng DSL.

## 15. Tùy biến token exchange của login khác với manager gọi API

Spring Security OAuth2 Login có bước đổi authorization code lấy token sau callback. Nếu yêu cầu là HTTP client/proxy/TLS riêng tại **token endpoint của login**, trên Servlet có hook:

~~~java
http.oauth2Login(login -> login
    .tokenEndpoint(tokenEndpoint -> tokenEndpoint
        .accessTokenResponseClient(customCodeTokenClient)
    )
);
~~~

Ở đây `customCodeTokenClient` phải là:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

với implementation tương thích phiên bản Spring Security (ví dụ `RestClientAuthorizationCodeTokenResponseClient` ở Spring Security hiện đại, hoặc implementation `DefaultAuthorizationCodeTokenResponseClient` ở các nhánh cũ hơn).

**Điểm phân biệt:**

- `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)`: HTTP request **đổi authorization code lấy token để hoàn tất login**.
- `DefaultOAuth2AuthorizedClientManager` + provider chain: **ủy quyền/cấp lại token cho authorized client khi được các consumer gọi**.
- `RestClient/WebClient interceptor/filter`: **gắn access token vào request đi tới Resource Server**.

Manager tùy chỉnh cho Orders API không tự thay HTTP token client dùng trong callback OIDC Login. Nếu yêu cầu phải thống nhất timeout/CA/proxy giữa nhiều bước, cần cấu hình đúng từng HTTP transport/hook liên quan.

## 16. Authorized-client repository và service liên kết thế nào với manager?

Trong Servlet, hai abstraction có vai trò khác:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
~~~

### 16.1. Repository trong request web

`OAuth2AuthorizedClientRepository` cung cấp các thao tác như:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);
~~~

và các thao tác lưu/xóa trong ngữ cảnh Servlet.

`DefaultOAuth2AuthorizedClientManager` thường sử dụng repository này, nhờ đó token có thể liên kết với principal và HTTP request hiện tại.

### 16.2. Service ngoài request

`OAuth2AuthorizedClientService` cung cấp các thao tác lưu/tải dựa trên registration ID và principal name, không nhất thiết phải có `HttpServletRequest`:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

Do đó, `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp với scheduled job hoặc service workload.

### 16.3. Một số implementation

| Implementation | Đặc điểm | Lưu ý |
|---|---|---|
| `HttpSessionOAuth2AuthorizedClientRepository` | Lưu authorized client trong session | Token gắn với vòng đời session; cần bảo vệ session store |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Có thể ủy quyền lưu cho service với principal đã xác thực | Cần hiểu rõ phân nhánh theo Authentication |
| `InMemoryOAuth2AuthorizedClientService` | Lưu trong tiến trình ứng dụng | Không bền khi restart/scale, có rủi ro mất token |
| `JdbcOAuth2AuthorizedClientService` | Lưu bằng JDBC | Cần kiểm soát schema, mã hóa/bảo vệ token và truy cập database |

**Không chọn repository chỉ vì chạy được local.** Ở production nhiều replica, cần xét session persistence, authorized-client store chia sẻ, token encryption, retention và cleanup.

## 17. Refresh token được kích hoạt khi nào?

Một hiểu lầm phổ biến: `OAuth2AuthorizedClientRepository.loadAuthorizedClient(...)` sẽ tự refresh token nếu hết hạn. Không nên giả định như vậy.

Repository chủ yếu **đọc/ghi token**. Manager/provider khi được gọi mới có thể quyết định thực hiện **refresh_token grant**.

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant C as OrdersController
    participant Http as RestClient OAuth2 Interceptor
    participant M as Custom AuthorizedClientManager
    participant Repo as Authorized Client Repository
    participant AS as Authorization Server
    participant API as Orders API

    Browser->>C: GET /bff/orders
    C->>Http: RestClient GET /api/orders, registration=company
    Http->>M: authorize(company, authenticated principal)
    M->>Repo: Load authorized client
    Repo-->>M: Access token AT1 sắp hết hạn, refresh token RT1
    M->>AS: POST token endpoint (refresh_token=RT1)
    AS-->>M: AT2 (+ RT2 nếu rotation)
    M->>Repo: Save authorized client mới
    M-->>Http: Authorized client với AT2
    Http->>API: Authorization: Bearer AT2
    API-->>Http: 200 dữ liệu
    Http-->>C: Response
    C-->>Browser: Kết quả
~~~

Luồng trên giả định **manager có refresh provider**, authorized client có refresh token và Authorization Server chấp nhận refresh. Không phải mọi grant đều cấp refresh token.

### 17.1. Đồng hồ và clock skew

Token có `expiresAt` và manager/provider có thể tính thời điểm refresh sớm hơn một khoảng để tránh token hết hạn trong lúc request đang bay tới API.

Khi tùy biến provider, có thể cấu hình clock skew ở những provider hỗ trợ. Đừng tự nhân đôi cơ chế bằng cách vừa sửa expiresAt trong repository vừa thêm một cron refresh không đồng bộ nếu chưa thiết kế rõ.

### 17.2. Refresh token rotation và concurrency

Một số OP rotate refresh token:

~~~text
AT1 + RT1
   refresh RT1
   -> AT2 + RT2
   RT1 có thể bị vô hiệu
~~~

Nếu hai request đến hai replica cùng lấy RT1 và đồng thời refresh, một request có thể thất bại `invalid_grant`. Khi triển khai nhiều node, cần xử lý race condition, lưu update nhất quán và chính sách retry phù hợp. Không retry vô hạn cùng refresh token đã bị rotate.

## 18. Khác nhau giữa token lỗi và user logout

Một OAuth2 Authorized Client có thể không dùng được mặc dù người dùng vẫn đang đăng nhập Portal:

| Trạng thái | Hành vi hợp lý |
|---|---|
| Access token hết hạn, refresh thành công | Tiếp tục gọi API, không bắt user login lại |
| Refresh token không còn hợp lệ | Yêu cầu cấp quyền/authorization lại tùy chính sách |
| Token sai audience/scope | Kiểm tra cấu hình registration/API; refresh cùng scope có thể không giải quyết |
| Resource Server 403 | Xử lý không đủ quyền, không tự logout |
| Orders API 5xx/timeout | Xử lý lỗi hạ tầng và retry có kiểm soát |
| Portal HTTP session hết hạn | Yêu cầu đăng nhập Portal, dù token còn trong store |
| Token của reports-service bị lỗi | Không bắt user của company logout vì đó là service registration |

Không dùng một flag `tokenValid` đại diện cho toàn bộ phiên đăng nhập. OAuth2 token state và SecurityContext có vòng đời độc lập; điều kiện để gọi API cần xét cả Authentication, authorized client và authorization policy của Resource Server.

## 19. Xử lý lỗi cấp token trong manager tùy chỉnh

Các lỗi token endpoint thường gặp:

- `invalid_client`: client credential hoặc phương thức xác thực client sai.
- `invalid_grant`: authorization code/refresh token không hợp lệ, đã dùng, hết hạn, PKCE không khớp hoặc bị thu hồi.
- `invalid_scope`: phạm vi quyền không được chấp nhận.
- TLS handshake, timeout, DNS/proxy failure: network/transport lỗi.

Spring Security có **authorization success/failure handlers** để điều phối lưu hoặc xóa authorized client sau các kết quả phù hợp. Nếu thay handler mặc định bằng handler riêng, phải đảm bảo:

1. Authorized client mới/được refresh **được lưu** khi thành công.
2. Token không hợp lệ **được loại khỏi store** khi chính sách yêu cầu.
3. Không xóa authorized client hợp lệ chỉ vì lỗi mạng tạm thời.
4. Không log client secret, access token, refresh token hoặc authorization code.
5. Không nuốt lỗi rồi trả một authorized client giả “thành công”.

Ví dụ sai:

~~~java
// Không làm như sau:
try {
    return manager.authorize(request);
} catch (Exception ex) {
    return oldAuthorizedClient; // Có thể chứa token đã bị từ chối.
}
~~~

Nếu token endpoint bị gián đoạn, ứng dụng nên trả lỗi phù hợp và xử lý theo SLO/circuit breaker của phụ thuộc bên ngoài, không tự giả định token cũ vẫn đáng tin.

### 19.1. Token của user và token của service không nên dùng chung error policy

Với user authorization_code, failure có thể dẫn đến **yêu cầu tương tác lại với người dùng**. Với client_credentials của background job, failure nên là **service error/alert/retry có kiểm soát**, không chuyển hướng sang màn hình login trong một tác vụ không có browser.

Đây là lý do tách manager web và job có thể làm chính sách lỗi rõ ràng hơn.

## 20. Tùy biến context của manager

Ngoài registration và principal, manager cần **context attributes** khi một grant đòi dữ liệu bổ sung. Trong `DefaultOAuth2AuthorizedClientManager`, có khả năng cấu hình context attributes mapper để ánh xạ thông tin từ `OAuth2AuthorizeRequest` sang `OAuth2AuthorizationContext`.

Các tình huống có thể cần mapper:

- Authorization Server yêu cầu tham số extension đã được thỏa thuận.
- Tùy chỉnh grant cần một thuộc tính thuộc ngữ cảnh request mà provider hiểu.
- Dữ liệu policy từ backend đã được xác minh cần đi vào authorization provider.

Nhưng:

- Không chép nguyên query parameters từ browser vào token request.
- Không cho client đổi token-uri, client-id, client-secret hoặc redirect-uri tùy ý.
- Không đặt credential vào attributes dễ bị log hoặc trả ra frontend.
- Không nghĩ mapper sẽ tự biến một grant `authorization_code` thành grant mới khi chưa có provider tương ứng.

Với nhu cầu đơn giản chỉ muốn thêm scope hoặc thông số provider, trước tiên cân nhắc **ClientRegistration** và extension points chuẩn của token-response client/provider thay vì viết manager từ đầu.

## 21. Kiểm soát principal trong manager

Manager thường định danh authorized client bằng registration và principal. Trong ứng dụng đa user:

~~~text
company + employee-0042 -> token của employee-0042
company + employee-0177 -> token của employee-0177
~~~

**Không sử dụng principalName do browser tự gửi**:

~~~http
GET /bff/orders?principalName=admin HTTP/1.1
~~~

rồi truyền nguyên chuỗi vào `OAuth2AuthorizeRequest.principal(...)` để lấy token được lưu dưới tên admin. Đây có thể là **confused deputy** và dẫn đến sử dụng token của người khác.

Với user-authorized flow, principal phải được lấy từ `Authentication` đã xác thực của request. Với service `client_credentials`, dùng principal riêng cố định thuộc service context đã kiểm soát, không ánh xạ sang danh tính user để vượt quyền.

### 21.1. Khi user đổi email

Một số token stores lưu theo `(registrationId, principalName)`. Nếu `Authentication.getName()` được cấu hình từ email và email thay đổi, application có thể không tìm thấy authorized client cũ.

Với OIDC, nên thiết kế identity mapping dựa trên `(iss,sub)` và hiểu các ảnh hưởng khi đổi `user-name-attribute`. Không tự fallback tìm token của người có cùng email ở client registration khác.

## 22. Client Manager không thay thế authorization ở API

Giả sử Orders API yêu cầu `orders.write` để xóa đơn:

~~~text
Principal đang login Portal
    |
    v
Manager lấy token có scope orders.read
    |
    v
DELETE /api/orders/123
    |
    v
Orders API trả 403 insufficient_scope
~~~

Manager không thể cấp thêm permission chỉ vì người dùng đã login. Token mới phải được Authorization Server cấp theo registration/policy, và Resource Server vẫn có quyền từ chối.

Trong hệ thống multi-tenant, một token có scope `orders.read` cũng không đủ để xem mọi đơn hàng; Orders API cần kiểm tra tenant/ownership và các điều kiện resource-specific. **Token lifecycle** khác với **business authorization**.

## 23. Khi nào cần OAuth2AuthorizedClientManager tự viết?

Đa số dự án **không cần implement interface** `OAuth2AuthorizedClientManager` từ đầu. Có thể tùy biến bằng:

1. Chọn class manager thích hợp: web hoặc service.
2. Dùng `OAuth2AuthorizedClientProviderBuilder` tạo provider chain.
3. Cấu hình token response clients (timeouts, TLS, client authentication) cho từng grant nếu cần.
4. Chọn authorized client repository/service.
5. Cấu hình context mapper và success/failure handler khi có yêu cầu.
6. Truyền manager vào RestClient/WebClient integration hoặc consumer cụ thể.

Tự viết manager có thể phù hợp khi có **kiến trúc multi-tenant/phân tách chính sách phức tạp**, nhưng phải bảo toàn validation, concurrency, token lifecycle và lỗi OAuth2. Tránh tự thực hiện refresh token qua raw HTTP chỉ vì muốn đổi timeout.

## 24. Triển khai nhiều replica và lưu token

Một mô hình production có:

~~~text
             ┌─────────────────┐
Browser ───► │ Load Balancer   │
             └──────┬──────────┘
                 ┌──┴──┐
                 v     v
             Portal A  Portal B
                 |     |
                 └──┬──┘
                    v
              Session Store
                    |
              Authorized Client Store
                    |
                    v
              Authorization Server
~~~

Những điểm cần thiết kế:

- **Authorization request correlation**: khi browser callback, Portal tìm lại state đã lưu. Đây là trách nhiệm của session/authorization request repository.
- **Authentication/session**: user request ở node B vẫn tìm được SecurityContext của phiên hợp lệ.
- **Authorized client storage**: node B tìm được token mà node A đã lưu, nếu ứng dụng yêu cầu chia sẻ.
- **Refresh token rotation**: tránh hai node cùng dùng một refresh token cũ mà không đồng bộ.
- **Secret/token protection**: encrypt-at-rest nếu chính sách yêu cầu, RBAC và TTL; không ghi token vào log.

Shared session không mặc nhiên là shared authorized-client store, và ngược lại. Chọn kho lưu nhất quán với loại manager/repository đang dùng.

## 25. Testing: làm sao biết HTTP client thật sự dùng manager mới?

**Không cần gọi Authorization Server production để kiểm tra integration.** Một vài mục tiêu test quan trọng:

| Tình huống test | Điều cần xác nhận |
|---|---|
| Bean manager được tạo | Provider chain và dependencies đúng, không có ambiguity giữa web/job managers |
| RestClient gọi Orders API | Interceptor sử dụng `webAuthorizedClientManager` |
| Chọn registration | Orders call dùng `company`, không dùng `reports-service` |
| Token còn hạn | Manager trả authorized client hiện tại mà không gọi token endpoint không cần thiết |
| Token hết hạn, có refresh token | Refresh provider được gọi theo chính sách |
| Refresh trả `invalid_grant` | Failure handling phù hợp; không trả token cũ như hợp lệ |
| Job không có Servlet request | `jobAuthorizedClientManager` có thể dùng client_credentials |
| Hai user đồng thời | Không lấy nhầm token của principal khác |
| Resource Server 403 | Không logout session vô điều kiện |
| Multi-node token rotation | Lưu state/token mới nhất nhất quán khi refresh |

### 25.1. Unit test với manager mock

Trong unit test HTTP integration, có thể stub `OAuth2AuthorizedClientManager.authorize(...)` để trả `OAuth2AuthorizedClient` với access token test, rồi dùng mock HTTP server để kiểm tra request gửi **Bearer token đúng**, không gọi IdP thực.

Ví dụ ý tưởng:

~~~text
Given:
  manager.authorize(registration=company, principal=employee-0042)
  -> AuthorizedClient(accessToken=TEST_AT)

When:
  ordersRestClient.get(/api/orders)
    attributes(clientRegistrationId(company))

Then:
  outbound request có Authorization: Bearer TEST_AT
  không lộ refresh token
~~~

Đây là **mô tả test fixture**, không phải kết quả test đã chạy. Kiểm tra grant provider và refresh có thể dùng fake token endpoint/MockWebServer để mô phỏng JSON success/error response theo OAuth2.

### 25.2. Integration test với Spring Security Test

Trong Servlet test có thể dùng `spring-security-test` và `oidcLogin()` để tạo một principal giả, sau đó gọi controller có RestClient mock. Test đó kiểm tra **wiring của principal và manager**, nhưng **không thay thế** test OIDC callback/ID Token signature validation ở một môi trường tích hợp phù hợp.

Không dùng client secret thật hoặc access token production làm test fixture.

## 26. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Đã khai báo custom manager nhưng call API vẫn dùng cấu hình cũ | HTTP client không được inject manager mới | Kiểm tra RestClient interceptor/WebClient filter constructor |
| Inject `OAuth2AuthorizedClientManager` báo nhiều bean | Có web và job managers | Dùng `@Qualifier` hoặc cấu trúc bean rõ ràng |
| Token request không refresh | Provider chain thiếu `refreshToken()`, không gọi manager, không có refresh token | Kiểm tra registration, provider và entry point |
| Job báo thiếu Servlet request | Dùng `DefaultOAuth2AuthorizedClientManager` ngoài HTTP request | Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| User login thành công nhưng Orders API 401 | Token hết hạn, sai audience hoặc bị revoke | Phân biệt session với token; xem error response đã che |
| API 403 dù refresh thành công | Thiếu scope/permission | Kiểm tra authorization policy, không coi refresh là tăng quyền |
| Client credentials token bị dùng cho request user | Chọn sai registration hoặc principal mapping | Giới hạn manager/registration theo consumer |
| Khi đổi email không tìm thấy authorized client | Principal name lưu token thay đổi | Kiểm tra `user-name-attribute` và storage key |
| OAuth2 Login token POST vẫn dùng timeout cũ | Chỉ thay manager gọi API, chưa thay login token client | Kiểm tra `oauth2Login().tokenEndpoint()` |
| Background job gặp `invalid_grant` | Sai grant/provider hoặc refresh token rotation | Kiểm tra registration, concurrency và chính sách AS |
| Có token trong database nhưng browser chưa login | Authorized client lưu bền hơn session | Không dùng token tồn tại để xác thực request browser |
| RestClient gửi Bearer đến domain lạ | HTTP client dùng default token cho mọi URI | Chỉ định base URL/registration và ranh giới tin cậy |
| Gặp redirect loop ở bước authorization | Resolver/filter/repository không đồng bộ, callback không match | Kiểm tra authorization URI, state, callback, session |

**Cách khoanh vùng:** xác định request đã dừng ở **authorization redirect**, **callback**, **token endpoint**, **authorized-client manager** hay **Resource Server**. Cùng một lỗi 401/403 tại browser có thể bắt nguồn từ nhiều tầng khác nhau.

## 27. Các lỗi thiết kế thường gặp

**1. Bật oauth2Client rồi cho rằng mọi RestClient tự có token.** Không. Chỉ những HTTP client có OAuth2 integration và manager thích hợp mới tự giải quyết token.

**2. Chỉ tạo manager bean mà không đưa vào consumer.** Có bean trong Spring context không đủ chứng minh một HTTP client đang sử dụng bean đó.

**3. Đổi token client của OAuth2 Login để sửa refresh trong Orders API.** Đây là hai điểm tích hợp khác nhau.

**4. Dùng web manager cho scheduled job không có HttpServletRequest.** Hãy dùng service manager.

**5. Dùng principal string do browser gửi vào.** Có nguy cơ truy xuất token của user khác.

**6. Xem token của client_credentials là token người dùng.** Grant dịch vụ không thay thế OIDC user login.

**7. Cấu hình default authorized client cho mọi request tùy ý.** Có thể gửi Bearer token tới sai host/resource.

**8. Tự retry vô hạn refresh token đã bị rotate.** Cần kiểm soát concurrency và trạng thái cập nhật.

**9. Chỉ kiểm tra expiresAt rồi khẳng định API sẽ chấp nhận token.** API còn kiểm tra issuer, audience, scopes, revocation và resource permissions.

**10. Log token/secret để debug.** Access token, refresh token, authorization code và client secret đều cần bảo vệ.

## 28. Bài tập thực hành

### Bài 1 — Manager custom nhưng không được sử dụng

Portal đã khai báo:

~~~java
@Bean
OAuth2AuthorizedClientManager myManager(...) {
    // ...
}
~~~

Nhưng Orders API vẫn được gọi bằng:

~~~java
RestClient restClient = RestClient.create();
~~~

**Câu hỏi:** Vì sao custom manager không điều phối token?

**Hướng giải:** Instance RestClient không có `OAuth2ClientHttpRequestInterceptor` hoặc integration OAuth2 tương ứng. Cần inject manager vào interceptor và dùng RestClient đã cấu hình đó khi gọi API.

### Bài 2 — Scheduled job dùng manager sai

Job chạy mỗi sáng, không có user login, dùng `DefaultOAuth2AuthorizedClientManager` với repository yêu cầu Servlet request.

**Câu hỏi:** Manager nào phù hợp hơn?

**Hướng giải:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientService` và provider `clientCredentials()`.

### Bài 3 — Token hết hạn nhưng session vẫn còn

User đã đăng nhập company, access token hết hạn và có refresh token.

**Câu hỏi:** Có nhất thiết yêu cầu login lại?

**Hướng giải:** Không. Manager có `refreshToken()` và token hợp lệ có thể làm mới. Nếu refresh thất bại, cần authorization lại theo policy.

### Bài 4 — Không đủ scope

Orders API cần `orders.write`, registration company chỉ có `orders.read`.

**Câu hỏi:** Bật thêm `clientCredentials()` trong manager có giúp quyền của user được tăng không?

**Hướng giải:** Không. Grant client credentials không cấp quyền thay mặt người dùng và không thay scope của registration hiện có. Cần quyền/scope đúng từ Authorization Server và authorization của API.

### Bài 5 — Đổi HTTP transport token endpoint login

Nhóm cần cấu hình mTLS hoặc proxy khi đổi authorization code sau OIDC callback. Họ đã sửa RestClient cho Orders API nhưng lỗi token endpoint login vẫn xảy ra.

**Câu hỏi:** Nên kiểm tra hook nào?

**Hướng giải:** Token-response client gắn vào `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` và HTTP transport của nó; không chỉ HTTP client gọi Orders API.

### Bài 6 — Hai managers trong Spring context

Web application có cả `webAuthorizedClientManager` và `jobAuthorizedClientManager`. Một service inject `OAuth2AuthorizedClientManager` nhưng không chỉ định bean.

**Câu hỏi:** Sửa như thế nào?

**Hướng giải:** Inject rõ bằng `@Qualifier` hoặc tách cấu hình theo interface/type phù hợp. Mỗi consumer dùng đúng manager theo ngữ cảnh và grant.

## 29. Checklist kết nối manager tùy chỉnh

| Câu hỏi | Điều cần xác định |
|---|---|
| Đây là Servlet hay Reactive application? | Với Servlet dùng `HttpSecurity` và `OAuth2AuthorizedClientManager` |
| Có cần login người dùng không? | `oauth2Login()` cho OIDC login |
| Có cần OAuth2 Client authorization qua filter không? | `oauth2Client()` theo luồng cần hỗ trợ |
| Grant nào thực sự dùng? | Authorization code, refresh token, client credentials |
| Manager class nào phù hợp? | Web request manager hay service/background manager |
| Repository/service nào lưu token? | Phù hợp session, persistence, HA và security |
| Provider chain đã cấu hình chưa? | Chỉ bật grant cần thiết, không mở rộng tùy ý |
| HTTP client có dùng manager không? | RestClient interceptor hoặc Servlet WebClient OAuth2 filter |
| Registration ID chọn ở đâu? | Rõ ràng theo API/consumer, không lấy từ input không tin cậy |
| Principal đến từ đâu? | Authentication của user hoặc danh tính service được kiểm soát |
| Token refresh xảy ra ở đâu? | Khi manager/provider được gọi, không tự xảy ra chỉ do repository |
| Token endpoint login có cần customization riêng? | Có thể cần hook trong `oauth2Login().tokenEndpoint()` |
| Có quản lý invalid_grant/revocation không? | Failure handler, cleanup và user action phù hợp |
| Multi-replica có đua refresh token không? | Shared store, concurrency và refresh token rotation |
| API có authorization riêng không? | Scope, audience, tenant/ownership và quyền resource |
| Log có lộ credential không? | Không ghi Bearer token, secret, code hoặc refresh token |

## 30. Tổng kết

Trong Spring Security OAuth 2.0/OIDC Client trên Servlet, **`oauth2Client()`** cấu hình cơ chế OAuth2 Client trong `SecurityFilterChain`, nhưng **không tự biến mọi HTTP client thành một client có khả năng quản lý token**. Muốn áp dụng chính sách token tùy chỉnh, cần tạo `OAuth2AuthorizedClientManager` với **registration repository, authorized-client repository/service và provider chain** phù hợp, rồi **liên kết manager vào consumer thực sự gọi API**.

Với request của người dùng, `DefaultOAuth2AuthorizedClientManager` phối hợp ngữ cảnh Servlet và authorized-client repository. Với scheduled job hoặc service-to-service không có HTTP request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp hơn. Đối với HTTP client, `OAuth2ClientHttpRequestInterceptor` cho RestClient (Spring Security 6.4+) hoặc `ServletOAuth2AuthorizedClientExchangeFilterFunction` cho WebClient trên Servlet giúp giải quyết token thông qua manager được chỉ định.

Cuối cùng, cần giữ ranh giới giữa **OIDC login**, **OAuth2 authorized-client lifecycle**, **token exchange**, **Bearer token sử dụng tại Resource Server** và **authorization của nghiệp vụ**. Việc kết nối đúng manager không chỉ giúp refresh/token storage hoạt động nhất quán, mà còn tránh dùng nhầm principal, registration hoặc credential khi Portal đồng thời phục vụ user login và background jobs.
