# 18.7. Xử lý lỗi ủy quyền và loại bỏ authorized client không còn hợp lệ

## 1. Bài toán: Portal vẫn đăng nhập nhưng API từ chối Bearer token

Giả sử một ứng dụng **Employee Portal** triển khai **Spring Boot 3, Spring Security 6, Servlet/Spring MVC**. Nhân viên đăng nhập qua **OpenID Connect (OIDC)**, sau đó backend Portal dùng **RestClient** gọi **Orders API** thay mặt người dùng.

Lần đầu, mọi việc hoạt động:

~~~text
Browser ──GET /bff/orders──> Employee Portal
                              |
                              | RestClient gửi access token AT-1
                              v
                           Orders API
                              |
                              └── 200 OK
~~~

Một lúc sau, Orders API trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="The access token is invalid"
Content-Type: application/json

{"error":"unauthorized"}
~~~

Điều này có thể xảy ra vì access token đã bị thu hồi, hết hạn theo đồng hồ của Resource Server, bị thay đổi chính sách, hoặc token không hợp lệ vì nguyên nhân khác. Trong khi đó, **HTTP session của Portal vẫn có Authentication hợp lệ**.

Giả sử Portal tiếp tục lấy cùng `OAuth2AuthorizedClient` từ kho lưu trữ và gửi lại AT-1 trên mọi request. User thấy trang tải mãi, nhiều lần nhận 401, dù token đã được API tuyên bố là không dùng được.

**Nhu cầu thực tế:** khi nhận **bằng chứng thích hợp** rằng một authorized client không còn hợp lệ, ứng dụng cần **đánh dấu/xóa bản ghi authorized client lỗi** ở đúng repository hoặc service, để lần sử dụng tiếp theo có thể đi qua một cơ chế cấp quyền hợp lệ. Đồng thời, phải tránh **xóa nhầm token** chỉ vì API trả 403 thiếu quyền hoặc lỗi mạng 500.

Trên Servlet stack, Spring Security cung cấp:

- `OAuth2ClientHttpRequestInterceptor`: tích hợp OAuth2 Client vào **RestClient** (Spring Security 6.4+).
- `OAuth2AuthorizedClientManager`: giải quyết token theo registration, principal và grant lifecycle.
- `OAuth2AuthorizationFailureHandler`: nhận các sự kiện authorization failure.
- `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`: hỗ trợ loại authorized client theo lỗi phù hợp.
- `OAuth2AuthorizedClientRepository` và `OAuth2AuthorizedClientService`: nơi lưu hoặc truy xuất authorized client.

> Phạm vi: Java 17+, Spring Boot 3, Spring Security 6 trên **Servlet**, sử dụng OAuth2/OIDC Client để gọi Resource Server. Phần mã RestClient OAuth2 interceptor yêu cầu **Spring Security 6.4+**; với phiên bản cũ hơn cần dùng integration có sẵn của phiên bản đó. Tên host, credential và token là dữ liệu minh họa.

## 2. Trước tiên: authorized client là gì?

Một `OAuth2AuthorizedClient` đại diện cho kết quả một OAuth2 Client đã được cấp quyền với một principal:

~~~text
OAuth2AuthorizedClient
├── ClientRegistration
│   ├── registrationId = company
│   ├── clientId = employee-portal
│   └── authorizationGrantType = authorization_code
├── principalName = employee-0042
├── accessToken
│   ├── tokenValue = <sensitive>
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── refreshToken (có thể null)
    ├── tokenValue = <sensitive>
    └── issuedAt
~~~

Đối tượng này **không phải** `Authentication` hoặc `SecurityContext`. Một user vẫn có thể đăng nhập Portal nhưng token dành cho Orders API không còn dùng được. Ngược lại, một bản ghi token có thể tồn tại trong persistent store sau khi session web kết thúc; bản ghi đó **không tự xác thực** browser request mới.

Khi ứng dụng “loại bỏ authorized client”, thông thường đó là thao tác **xóa bản ghi token tại phía OAuth2 Client**. Nó **không mặc nhiên**:

1. Logout user khỏi Portal.
2. Revoke token tại Authorization Server.
3. Vô hiệu access token đã sao chép ở hệ thống khác.
4. Thu hồi phiên Single Sign-On tại OpenID Provider.
5. Xóa mọi authorized client khác của cùng principal.

Đây là điểm quan trọng nhất để thiết kế xử lý lỗi theo đúng phạm vi.

## 3. Toàn cảnh RestClient, manager và failure handler

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant P as Employee Portal
    participant R as RestClient OAuth2 Interceptor
    participant M as OAuth2AuthorizedClientManager
    participant S as Authorized Client Repository
    participant AS as Authorization Server
    participant API as Orders API

    U->>P: GET /bff/orders (session hợp lệ)
    P->>R: GET Orders API, registration=company
    R->>M: authorize(company, principal)
    M->>S: Tải authorized client
    S-->>M: AT-1 / RT-1
    opt Access token cần refresh và có refresh token
        M->>AS: POST token endpoint - refresh_token grant
        AS-->>M: AT-2 / RT-2
        M->>S: Lưu authorized client mới
    end
    M-->>R: Authorized client thích hợp
    R->>API: GET /api/orders, Bearer access token
    API-->>R: 401, WWW-Authenticate: Bearer error="invalid_token"
    R->>R: Diễn giải authorization failure
    R->>S: Failure handler loại authorized client nếu lỗi phù hợp
    R-->>P: Lỗi từ downstream được xử lý theo policy
    P-->>U: Thông điệp lỗi hoặc yêu cầu cấp quyền lại
~~~

Trong luồng này có **hai nơi lỗi khác nhau**:

- **Trước khi gọi Resource Server:** manager cần refresh/cấp token và Authorization Server trả lỗi (ví dụ `invalid_grant`).
- **Sau khi gọi Resource Server:** Orders API từ chối Bearer token (ví dụ `invalid_token`).

Cả hai có thể dẫn đến việc xóa authorized client, nhưng **nguồn lỗi, cách diễn giải và nơi gắn failure handler khác nhau**.

## 4. Phân biệt lỗi token endpoint với lỗi Resource Server

| Giai đoạn | Nơi trả lỗi | Ví dụ | Ý nghĩa |
|---|---|---|---|
| Lấy access token ban đầu | Token endpoint của Authorization Server | `invalid_grant` do code đã dùng/hết hạn | Không hoàn tất token exchange |
| Refresh access token | Token endpoint | `invalid_grant` do refresh token bị thu hồi | Authorized client hiện có có thể không còn refresh được |
| Xác thực OAuth client | Token endpoint | `invalid_client` | Client secret, mTLS hoặc phương thức xác thực client không hợp lệ |
| Gọi Orders API | Resource Server | HTTP 401 / Bearer `invalid_token` | Bearer token bị từ chối |
| Gọi Orders API | Resource Server | HTTP 403 / Bearer `insufficient_scope` | Token có thể hợp lệ nhưng không có quyền cần thiết |
| Gọi Orders API | Resource Server hoặc gateway | HTTP 429 | Giới hạn tốc độ, không chứng minh token sai |
| Gọi Orders API | Resource Server hoặc gateway | HTTP 500/503, timeout | Lỗi hạ tầng, không đủ bằng chứng token không hợp lệ |

**Không dùng một quy tắc chung “mọi HTTP 4xx hoặc 5xx đều xóa authorized client”.** Điều đó làm phát sinh các vòng lặp cấp token, tăng tải IdP và có thể gây gián đoạn cho user đang có quyền hợp lệ.

### 4.1. HTTP 401 chưa đủ để xác định mọi nguyên nhân

Một 401 có thể do:

- Header Bearer thiếu.
- Bearer token hỏng/hết hạn/bị thu hồi.
- Gateway chưa gửi token đến backend.
- Resource Server không chấp nhận issuer/audience.
- Một security filter/endpoint không phải OAuth2 Bearer tạo 401.

Để quyết định loại authorized client, cần quan tâm đến **Bearer challenge** theo RFC 6750, đặc biệt header:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

Một HTTP response 401 **không có** thông tin Bearer error tương ứng có thể không đủ cho handler chuẩn suy ra token cần xóa.

### 4.2. HTTP 403 thường là thiếu quyền, không phải token đã hỏng

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

Token hiện tại có thể vẫn hợp lệ cho `orders.read`, nhưng không có scope `orders.write`. **Xóa token rồi xin token mới cùng scope thường không giải quyết**.

Hướng xử lý là xem chính sách consent, scope, quyền tenant và authorization của Orders API. Đừng mặc định mọi lỗi 403 đều phải refresh hoặc logout.

## 5. OAuth2AuthorizationFailureHandler có nhiệm vụ gì?

Trên Spring Security Servlet, `OAuth2AuthorizationFailureHandler` là abstraction xử lý **authorization failure** của OAuth2 Client.

Nói ngắn gọn, handler nhận thông tin lỗi và context cần thiết để thực hiện hậu xử lý, ví dụ:

- Ghi metric hoặc audit **đã che dữ liệu nhạy cảm**.
- Loại authorized client không còn hợp lệ khỏi repository/service.
- Chuyển sự kiện cho cơ chế retry/re-authorization theo policy của ứng dụng.

Một implementation được dùng phổ biến:

~~~java
import org.springframework.security.oauth2.client
    .RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
~~~

`RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` được thiết kế để **loại authorized client theo một tập lỗi OAuth2 phù hợp**. Không nên hiểu tên lớp này là “xóa tất cả token khi bất kỳ HTTP request nào thất bại”.

### 5.1. Hai nguồn kích hoạt authorization failure

**Nguồn A — Manager/provider:** token endpoint từ chối authorization hoặc refresh. Manager có thể áp dụng failure handler để xóa authorized client đã lưu khi nhận lỗi thích hợp.

**Nguồn B — RestClient gọi Resource Server:** downstream API trả Bearer error cho biết token đang dùng không hợp lệ. Interceptor có thể gọi failure handler để **loại bản ghi authorized client**, giúp lần sau tránh tái sử dụng token đó.

Điểm khác nhau là **manager biết rõ quá trình xin token**, còn **interceptor nhìn thấy phản hồi của Resource Server**. Hai sự kiện không nên trộn thành một “user login failed”.

## 6. Chuẩn bị Spring Boot OAuth2 Client trên Servlet

### 6.1. Dependencies

Ví dụ Gradle dùng Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`RestClient` có trong Spring Framework 6.1+; **`OAuth2ClientHttpRequestInterceptor`** là tích hợp ở Spring Security 6.4+. Hãy kiểm tra dependency thực tế do Spring Boot BOM quản lý. Nếu ứng dụng đang dùng Spring Security cũ hơn, ví dụ dùng WebClient Servlet integration, cần cấu hình failure handler theo API của phiên bản đó; không copy một class chưa tồn tại.

### 6.2. OIDC Client registration

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

Các biến môi trường là **placeholder**; không đặt secret thật vào Git hoặc tài liệu. Provider phải được cấu hình với token endpoint và issuer đáng tin cậy.

### 6.3. SecurityFilterChain

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
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
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

`oauth2Login()` xử lý đăng nhập OIDC. `oauth2Client()` cung cấp hỗ trợ OAuth2 Client trong Servlet security chain. Hai lệnh này **không tự gắn một authorized-client failure handler vào mọi RestClient** mà ứng dụng tự tạo; phải cấu hình HTTP integration rõ ràng.

## 7. Tạo manager để RestClient giải quyết token

Khi gọi Orders API qua RestClient, có thể dùng `DefaultOAuth2AuthorizedClientManager` trong ngữ cảnh Servlet request/response:

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
public class AuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
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

Manager sử dụng:

1. `ClientRegistrationRepository` để xác định registration `company`.
2. `OAuth2AuthorizedClientRepository` để tải/lưu token của principal.
3. Provider chain để chọn grant tương ứng.
4. Authorization success/failure handling của manager theo cấu hình.

**Manager chỉ có thể refresh khi đã có authorized client và refresh token phù hợp.** Nó không tự mở browser để thực hiện lại toàn bộ Authorization Code Flow từ một background request.

Trong Spring Boot, các bean/integration mặc định có thể đã tồn tại. Code trên là một phương án cấu hình rõ ràng để làm ví dụ; không bắt buộc mọi dự án phải tự khai báo manager nếu không có yêu cầu tùy biến.

## 8. RestClient gửi token và xử lý invalid_token

### 8.1. OAuth2ClientHttpRequestInterceptor

Trên Spring Security 6.4+, cấu hình một RestClient tích hợp OAuth2 Client:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfig {

    @Bean
    RestClient ordersRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager
            );

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

Interceptor giải quyết authorized client qua manager, gắn access token vào Bearer header khi gọi API theo registration và principal. Không cần controller tự lấy token string rồi gọi `headers.setBearerAuth(...)` trong mọi method.

**Nhưng** đây mới là phần **đính token**; muốn xử lý Bearer error và loại authorized client lỗi, cần cấu hình thêm authorization failure handler.

### 8.2. Bổ sung authorizationFailureHandler

Một cách dùng API tiện ích của chính `OAuth2ClientHttpRequestInterceptor` trong Spring Security 6.4+:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientFailureConfig {

    @Bean
    RestClient ordersRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager,
        OAuth2AuthorizedClientRepository authorizedClientRepository
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager
            );

        oauth2.setAuthorizationFailureHandler(
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(
                    authorizedClientRepository
                )
        );

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

**Đây là phương án thay thế bean RestClient ở mục 8.1**, không giữ cả hai `@Bean RestClient ordersRestClient` trong cùng application.

Điểm mấu chốt:

~~~java
oauth2.setAuthorizationFailureHandler(
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientRepository)
);
~~~

Handler sử dụng repository để **loại authorized client đã được xác định là không còn hợp lệ** theo các Bearer/OAuth2 error được Spring Security diễn giải và chính sách handler mặc định. Cần sử dụng repository **phù hợp với manager**, tránh manager lưu token ở A nhưng failure handler cố xóa ở B.

**Không suy luận:** “cấu hình handler này thì mọi HTTP 401/403 đều xóa token”. Cơ chế phải xác định **authorization failure tương ứng**, chẳng hạn Bearer challenge có `invalid_token`; cần kiểm tra hành vi phiên bản Spring Security đang chạy và response thực tế của Resource Server.

### 8.3. Gọi RestClient với registration ID rõ ràng

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
    public String listOrders() {
        return ordersRestClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .body(String.class);
    }
}
~~~

`clientRegistrationId("company")` giúp interceptor chọn đúng authorized client. Trong request đã login, Spring Security cung cấp Authentication; manager/repository sử dụng ngữ cảnh đó để tìm token.

Đây là HTTP call **server-to-server**. Browser không cần biết access token của Portal. Trong sản phẩm thật, nên cấu hình URL Orders API, timeout, trusted host, transport và error handling phù hợp; không gửi token đến URL được người dùng tùy ý nhập.

## 9. Khi nào sử dụng OAuth2AuthorizedClientService thay vì Repository?

Trên Servlet, có hai cơ chế lưu trữ hay gặp:

| Cơ chế | API điển hình | Ngữ cảnh |
|---|---|---|
| `OAuth2AuthorizedClientRepository` | `loadAuthorizedClient(registrationId, principal, request)`, `removeAuthorizedClient(registrationId, principal, request, response)` | HTTP Servlet request/response |
| `OAuth2AuthorizedClientService` | `loadAuthorizedClient(registrationId, principalName)`, `removeAuthorizedClient(registrationId, principalName)` | Dịch vụ, tác vụ không có HTTP request |

Repository có thể sử dụng service bên dưới, ví dụ `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` phân nhánh theo principal đã xác thực. Nhưng không thể mặc định mọi repository đều lưu bằng database.

Nếu manager đang dùng **HTTP request repository**, nên cấu hình failure handler để xóa qua repository tương ứng. Nếu manager đang dùng **AuthorizedClientServiceOAuth2AuthorizedClientManager** cho service/background workflow, nên chọn cách loại bỏ bằng authorized-client service tương ứng.

### 9.1. Ví dụ loại bằng service

Trong code nghiệp vụ đã xác định chắc chắn một authorized client cần bị xóa:

~~~java
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientService;

public final class AuthorizedClientCleanup {

    private final OAuth2AuthorizedClientService authorizedClients;

    public AuthorizedClientCleanup(
        OAuth2AuthorizedClientService authorizedClients
    ) {
        this.authorizedClients = authorizedClients;
    }

    public void removeKnownInvalidClient(
        String registrationId,
        String trustedPrincipalName
    ) {
        authorizedClients.removeAuthorizedClient(
            registrationId,
            trustedPrincipalName
        );
    }
}
~~~

**Đây là thao tác xóa trực tiếp khi phía server đã xác định lỗi theo một chính sách tin cậy**, không phải endpoint cho browser tự xóa token tùy ý. Không nhận `trustedPrincipalName` từ query parameter do client gửi khi thao tác đó có thể ảnh hưởng token của người khác.

### 9.2. Ví dụ loại bằng Servlet repository

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizedClientRepository;

void removeForCurrentRequest(
    OAuth2AuthorizedClientRepository repository,
    Authentication authenticatedPrincipal,
    HttpServletRequest servletRequest,
    HttpServletResponse servletResponse
) {
    repository.removeAuthorizedClient(
        "company",
        authenticatedPrincipal,
        servletRequest,
        servletResponse
    );
}
~~~

Ở đây `authenticatedPrincipal` phải đến từ ngữ cảnh bảo mật đã được xác thực. Lưu trữ theo HttpSession, database hay cơ chế tùy biến đều có contract và side effect riêng. Không gọi remove cho tất cả registrations khi chỉ token của `company` không hợp lệ.

## 10. RemoveAuthorizedClientOAuth2AuthorizationFailureHandler

Tên lớp thể hiện mục đích: xóa authorized client **khi lỗi authorization thuộc chính sách cần loại bỏ**.

Một sơ đồ:

~~~text
OAuth2AuthorizationException
    |
    +-- errorCode liên quan token/grant không còn hợp lệ
    |      |
    |      +--> RemoveAuthorizedClientOAuth2AuthorizationFailureHandler
    |               |
    |               +--> OAuth2AuthorizedClientRemover
    |                        |
    |                        +--> removeAuthorizedClient(...)
    |
    +-- lỗi không đủ căn cứ loại token
           |
           +--> Không tự xóa theo mặc định hoặc do policy của app
~~~

Spring Security cung cấp một cơ chế remover, có thể trỏ đến repository/service thích hợp. Phần cấu hình qua helper của `OAuth2ClientHttpRequestInterceptor` ở mục 8 thường thuận tiện hơn vì interceptor còn phải chuyển ngữ cảnh request/response đến handler.

### 10.1. Lỗi nào thường đáng xem xét loại authorized client?

Những lỗi như `invalid_grant` khi refresh token bị từ chối, hoặc `invalid_token` khi Resource Server chỉ rõ Bearer token không hợp lệ, là ứng viên điển hình để loại bản ghi không dùng được.

Tuy nhiên:

- `invalid_client` có thể là lỗi cấu hình credential của ứng dụng, không thể “chữa” bằng việc xóa token của mọi người.
- `insufficient_scope` nghĩa là cấp quyền hiện tại không đủ; token vẫn có thể hợp lệ cho API khác.
- HTTP 429/500/503 hoặc timeout không chứng minh token sai.
- Một HTTP 403 vì business authorization không đồng nghĩa Bearer token không hợp lệ.

**Bộ mã lỗi được handler mặc định sử dụng phải được kiểm tra theo phiên bản**, không tự mở rộng thành mọi OAuth2 error. Nếu cần chính sách riêng, hãy thiết kế whitelist lỗi và tests rõ ràng.

### 10.2. Loại authorized client không đồng nghĩa cấp token mới lập tức

Sau khi xóa bản ghi của `company`:

~~~text
Request A:
  AT-1 bị Resource Server từ chối
  -> failure handler xóa authorized client company/employee-0042
  -> Request A vẫn thất bại hoặc được xử lý theo error policy

Request B:
  manager không tìm thấy authorized client cũ
  -> cần grant phù hợp để lấy token hợp lệ
  -> có thể cần browser authorization code flow mới
~~~

Lúc này **Authorization Code Grant** có thể yêu cầu người dùng được chuyển hướng tới IdP/consent; một RestClient backend call không thể tự hoàn tất mọi bước tương tác người dùng. Không nên “tự retry Request A bằng token mới” nếu token manager chưa có grant hợp lệ và chưa xác định HTTP request an toàn để retry.

## 11. Manager tự xử lý authorization failure khi refresh token không hợp lệ

Một luồng quan trọng khác xuất hiện **trước khi RestClient gửi request đi**:

~~~mermaid
sequenceDiagram
    participant App as Orders Controller
    participant I as RestClient Interceptor
    participant M as Authorized Client Manager
    participant S as Authorized Client Store
    participant AS as Authorization Server

    App->>I: GET Orders API
    I->>M: authorize(company, principal)
    M->>S: Load AT-1 + RT-1
    S-->>M: AT-1 hết hạn, RT-1
    M->>AS: POST /token với RT-1
    AS-->>M: 400 invalid_grant
    M->>M: Authorization failure handling
    M->>S: Remove authorized client nếu đúng chính sách
    M-->>I: OAuth2 authorization failure
    I-->>App: Không lấy được Bearer token hợp lệ
~~~

Trong luồng này, **Orders API chưa hề được gọi**. Nếu chỉ cấu hình failure handler cho response Resource Server mà không xử lý lỗi refresh/token endpoint, ứng dụng có thể vẫn giữ bản ghi với RT-1 hỏng.

`DefaultOAuth2AuthorizedClientManager` có các hành vi success/failure handling mặc định cho một số trường hợp, ví dụ loại authorized client khi nhận lỗi OAuth2 `invalid_grant` thích hợp. Tuy nhiên, chính sách cụ thể phụ thuộc loại manager, storage và phiên bản; không giả định mọi implementation có cùng hành vi hoặc mọi failure handler được áp dụng tự động khi dùng manager tùy chỉnh.

### 11.1. Không đánh đồng invalid_grant với invalid_token

~~~text
invalid_grant:
  Nguồn thường gặp -> Authorization Server / token endpoint
  Thường liên quan authorization code hoặc refresh token grant

invalid_token:
  Nguồn thường gặp -> Resource Server / WWW-Authenticate Bearer
  Thường liên quan Bearer access token đang được dùng
~~~

Vì phát sinh ở hai bước khác nhau, **điểm gắn handler** và **thời điểm có thể cấp lại token** có thể khác. Lỗi `invalid_grant` khi đổi code lúc đăng nhập ban đầu không có nghĩa đã tồn tại một OAuth2AuthorizedClient trong store để xóa.

## 12. Không phải mọi 401 đều cho phép tự động retry

Một anti-pattern:

~~~text
RestClient call
  -> 401
  -> remove authorized client
  -> refresh/re-authorize
  -> retry same request
  -> 401
  -> remove...
  -> lặp vô hạn
~~~

Các rủi ro:

- Nếu API thực sự từ chối do audience/issuer, cấp lại token cùng cấu hình vẫn thất bại.
- Nếu OP không cấp refresh token và cần browser consent, backend không thể tự hoàn tất.
- Nếu Resource Server phản hồi 401 vì gateway/middleware bị lỗi, xóa token không giúp gì.
- Với HTTP POST/PUT/PATCH/DELETE, retry tự động có thể **lặp một thao tác nghiệp vụ**, nhất là khi request đầu đã được server tiếp nhận một phần trước khi trả lỗi.
- Retry đồng thời từ nhiều request có thể làm Authorization Server quá tải.

### 12.1. Chính sách retry có kiểm soát

Một chính sách hợp lý có thể là:

1. Chỉ nhận dạng lỗi Bearer rõ ràng, ví dụ `invalid_token`.
2. Loại authorized client đúng registration/principal.
3. Phân biệt request có an toàn để retry không.
4. Giới hạn số lần reauthorization/retry, thường tối đa một chu kỳ có kiểm soát nếu sản phẩm cho phép.
5. Không retry một thao tác không idempotent nếu thiếu **idempotency key** hoặc cơ chế xác nhận kết quả.
6. Nếu phải chuyển browser đến IdP, trả yêu cầu tương tác phù hợp thay vì âm thầm lặp request.
7. Nếu API thiếu quyền, báo 403 hoặc yêu cầu cấp thêm scope theo chính sách, không tự coi là lỗi token expiry.

**Failure handler không phải một retry engine.** Việc nó xóa authorized client chỉ thay đổi state cho một lần authorization sau; business HTTP request và phản hồi lỗi vẫn phải được xử lý riêng.

## 13. Trạng thái đăng nhập và trạng thái token có thể lệch nhau

Ví dụ timeline:

~~~text
09:00  Browser login thành công.
       SecurityContext/Session còn hiệu lực.
       Authorized client = AT-1 + RT-1.

09:05  AT-1 hết hạn theo metadata.
       Manager có thể dùng RT-1 xin AT-2.

09:10  Orders API trả Bearer invalid_token cho AT-2.
       Failure handler loại authorized client liên quan.

09:11  Browser vẫn có session Portal.
       Người dùng vẫn authenticated tại Portal.
       Nhưng chưa có authorized client hợp lệ để gọi Orders API.

09:12  Ứng dụng có thể cần re-authorization/consent.
~~~

**Xóa authorized client không tự logout khỏi Portal.** Có thể user vẫn xem được các trang nội bộ không cần Orders API.

Ngược lại, khi user logout khỏi Portal, session bị kết thúc nhưng access token đã cấp **không nhất thiết** bị thu hồi ngay ở Authorization Server. **Token cleanup local** và **token revocation remote** là hai thao tác khác nhau.

## 14. Khi nào phải yêu cầu người dùng cấp quyền lại?

Sau khi token bị loại khỏi local store, manager không có một authorized client hiện tại cho registration đó. Tùy grant:

| Grant | Có thể lấy token mới bằng cách nào? | Cần tương tác browser? |
|---|---|---|
| `authorization_code` | Bắt đầu authorization flow mới (với state/PKCE/redirect URI phù hợp) | Thường có top-level redirect, có thể SSO tự động nếu IdP còn session |
| `refresh_token` | Chỉ dùng nếu còn RT hợp lệ thuộc authorized client | Không cần browser nếu AS cho phép |
| `client_credentials` | Client dùng credential của chính dịch vụ yêu cầu token mới | Không |

Nếu token `company` thuộc user authorization_code và refresh token không còn, một request gọi Orders API có thể cần trả lỗi để frontend khởi động **authorization flow** mới. Không tự biến `client_credentials` của ứng dụng thành token đại diện cho người dùng chỉ để tránh consent.

Nếu ứng dụng đã lưu quyền/thông tin người dùng trong database, nó vẫn cần kiểm tra account/tenant status. Đăng nhập thành công ở IdP không tự bảo đảm người dùng có role phù hợp với Orders API.

## 15. Resource Server trả insufficient_scope

Giả sử Portal gửi access token:

~~~text
token scopes = orders.read
~~~

Nhưng endpoint đòi:

~~~http
DELETE /api/orders/123 HTTP/1.1
Authorization: Bearer <token-with-orders.read>
~~~

Orders API đáp:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

Đây là **lỗi authorization tại Resource Server**, nhưng không đủ cơ sở kết luận token không dùng được cho mọi tác vụ. Token vẫn có thể hợp lệ để:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <same-token>
~~~

**Xóa token chỉ vì insufficient_scope** có thể làm mọi màn hình đọc dữ liệu cũng bị yêu cầu login/consent lại, trong khi người dùng không có quyền viết ngay từ đầu.

Ứng dụng cần xử lý quyền:

- Kiểm tra đăng ký client và scope yêu cầu.
- Xác nhận user được Authorization Server cấp scope đó hay không.
- Xem policy business/tenant/resource ownership ở Orders API.
- Nếu hỗ trợ incremental authorization, bắt đầu luồng cấp quyền theo quy định.
- Nếu user không có quyền, trả 403 và UI phù hợp.

Không tự sửa access token JWT, thêm `orders.write` vào một header hoặc bật grant khác để “vượt qua” API authorization.

## 16. Lỗi không đến từ Bearer authentication

Một số response khác cũng có HTTP 401 hoặc 403 nhưng không liên quan trực tiếp đến OAuth2 access token:

- Proxy bảo vệ bằng một lớp Basic Auth riêng.
- Endpoint yêu cầu API key hoặc mTLS mà Portal chưa cung cấp.
- WAF chặn request theo rule.
- Application business logic trả 403 vì tenant hoặc quyền sở hữu.
- CSRF protection ở một endpoint Servlet khác.
- Gateway trả 401 do route không được khai báo.

Nếu xóa authorized client dựa trên **status code trần**, ứng dụng có thể hủy token tốt vì một lỗi hoàn toàn khác.

Hãy kiểm tra cấu trúc `WWW-Authenticate` header, loại endpoint, request path, security filter và logs được phép truy cập.

## 17. Quản lý principal và registration khi xóa

Một kho authorized client có thể lưu:

~~~text
registrationId = company, principalName = employee-0042
registrationId = company, principalName = employee-0099
registrationId = reports-service, principalName = reports-worker
~~~

Khi AT của employee-0042 bị Orders API từ chối, thao tác cleanup phải **chỉ nhắm đúng bản ghi liên quan**. Không:

~~~java
// Sai: xóa mọi bản ghi registration company của mọi user.
deleteAllByRegistrationId("company");
~~~

vì sự kiện chỉ chứng minh **một authorized client** có vấn đề.

### 17.1. Không tin principalName do browser tự gửi

Ví dụ nguy hiểm:

~~~http
DELETE /internal/oauth2/token?principalName=admin HTTP/1.1
~~~

Nếu controller đọc `principalName=admin` rồi xóa token của admin mà không có quyền tương ứng, kẻ khác có thể gây gián đoạn/chiếm quyền điều phối token của người dùng khác.

Với user-authorized token, lấy principal từ `Authentication` đã được Spring Security xác thực. Với service tokens, sử dụng service principal đã được cấu hình và bảo vệ ở backend. API quản trị token phải kiểm tra authorization riêng và ghi audit thích hợp.

### 17.2. Email đổi có thể ảnh hưởng khóa lưu token

Một số implementation lưu theo `(registrationId, principalName)`. Nếu principal name được cấu hình bằng `email` và email đổi, bản ghi cũ có thể không còn tìm được bằng tên mới.

Đối với OIDC, nên hiểu identity theo **issuer + subject** và tránh dùng email làm định danh kỹ thuật bền vững. Khi thay đổi `user-name-attribute`, cần đánh giá tác động tới kho authorized client và migration.

## 18. Nhiều RestClient hoặc nhiều registrations

Employee Portal có thể gọi:

~~~text
Orders API:  registrationId = company
Reports API: registrationId = reports-service
Partner API: registrationId = partner
~~~

Khi Orders API trả `invalid_token`, không nên:

- Xóa token của Reports API.
- Xóa session của mọi user.
- Tự chuyển sang token của `reports-service`.
- Dùng token của partner để gọi Orders API.

**Nguyên tắc least privilege:** mỗi RestClient nên biết base URL, registration thích hợp và nguyên tắc chia sẻ token. Không cấu hình một HTTP interceptor phát Bearer token cho mọi hostname mà ứng dụng có thể gọi nếu các host đó không đều nằm trong phạm vi tin cậy.

Một lựa chọn là tạo RestClient chuyên biệt cho từng Resource Server:

~~~text
ordersRestClient  -> https://orders.example.test, company
reportsRestClient -> https://reports.example.test, reports-service
partnerRestClient -> https://partner.example.test, partner
~~~

Việc chọn registration cần được xác định trong backend code/configuration, không lấy tự do từ input không tin cậy.

## 19. Xử lý lỗi ở controller và tầng HTTP

Nếu RestClient gọi downstream API thất bại, ứng dụng cần quyết định **phản hồi gì cho browser**. Loại authorized client không tự giải quyết UX hoặc status code của BFF.

Một số nguyên tắc:

1. Nếu browser chưa có Authentication, Portal có thể trả 401 JSON hoặc redirect tới login tùy endpoint.
2. Nếu user đã login nhưng thiếu scope ở downstream, Portal có thể trả 403 phù hợp hoặc hướng dẫn authorization bổ sung.
3. Nếu token invalid và đã cleanup, Portal có thể trả trạng thái yêu cầu kết nối/cấp quyền lại.
4. Nếu downstream 5xx hoặc timeout, đó là lỗi phụ thuộc bên ngoài; không đổi thành “phiên đăng nhập hết hạn”.
5. Không trả raw token endpoint error body hoặc WWW-Authenticate chứa thông tin nhạy cảm không cần thiết cho browser.

### 19.1. Ví dụ REST API mapping lỗi có kiểm soát

~~~java
package com.example.portal.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

@RestControllerAdvice
public class DownstreamErrorAdvice {

    @ExceptionHandler(HttpClientErrorException.Unauthorized.class)
    ResponseEntity<ApiError> downstreamUnauthorized() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("ORDERS_AUTHORIZATION_REQUIRED"));
    }

    @ExceptionHandler(HttpClientErrorException.Forbidden.class)
    ResponseEntity<ApiError> downstreamForbidden() {
        return ResponseEntity
            .status(HttpStatus.FORBIDDEN)
            .body(new ApiError("ORDERS_ACCESS_DENIED"));
    }

    @ExceptionHandler(HttpServerErrorException.class)
    ResponseEntity<ApiError> downstreamUnavailable() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("DOWNSTREAM_UNAVAILABLE"));
    }

    record ApiError(String code) {}
}
~~~

Đây là **ví dụ đơn giản về mapping lỗi ở BFF**, không phải một chính sách chuẩn áp dụng cho mọi sản phẩm. Nếu downstream 401 do user cần reauthorization, ứng dụng có thể chọn mã/trạng thái khác theo contract frontend; cần phân biệt 401 của **Portal session** với 401 của **downstream API**.

**Không dựa vào ControllerAdvice này để cleanup token**: cleanup phải được cấu hình ở OAuth2 interceptor/manager tương ứng. Advice chỉ xử lý cách ứng dụng trả lỗi. Tùy phiên bản RestClient, exception thực tế và cơ chế intercept response có thể khác; phải dùng handler phù hợp HTTP client stack.

## 20. Xóa authorized client không phải remote token revocation

Hai thao tác:

~~~text
Local cleanup:
  authorizedClientRepository.removeAuthorizedClient(...)

Remote revocation:
  POST tới Authorization Server's revocation endpoint (nếu được hỗ trợ)
~~~

**Local cleanup** loại token khỏi kho mà Portal quản lý, nhằm tránh tiếp tục tái sử dụng trong các request tới. Nó **không gửi lệnh thu hồi** tới Authorization Server.

**Remote revocation** yêu cầu Authorization Server thu hồi token hoặc refresh token theo cơ chế OAuth2 Token Revocation (nếu provider hỗ trợ). Tùy loại token, Resource Server có thể áp dụng revocation theo cách khác nhau; không mặc định tất cả JWT đã phát lập tức bị vô hiệu khi có một thao tác local.

Khi user logout, có thể cần:

- Xóa SecurityContext và HTTP session.
- Xóa authorized client trong local store.
- Gọi revocation endpoint để thu hồi token nếu chính sách yêu cầu và provider hỗ trợ.
- Thực hiện OIDC RP-Initiated Logout hoặc cơ chế SSO logout riêng.

Những thao tác này là **bốn trách nhiệm khác nhau**. Failure handler của RestClient không thay thế toàn bộ logout/revocation flow.

## 21. Lưu trữ token trong môi trường nhiều replica

Giả sử Portal chạy trên hai node:

~~~text
                   +--> Portal A
Browser -> Gateway |
                   +--> Portal B
                          |
                          v
                 Authorized Client Store
~~~

Request A trên Node A nhận `invalid_token` và xóa authorized client. Request B trên Node B đã tải token cũ trước khi xóa, có thể vẫn gửi token đó đến Resource Server.

Điều này đặt ra vấn đề **concurrency** và **eventual consistency**:

- Storage có được chia sẻ giữa nodes không?
- Repository/service có cache riêng theo node không?
- Nếu token đã bị refresh trên B ngay trước khi A xử lý lỗi, A có thể vô tình xóa **bản ghi mới hơn** không?
- Có cơ chế version/generation hoặc compare-and-delete để bảo vệ update mới không?
- Refresh token rotation có khiến hai request đồng thời dùng cùng RT-1 không?

### 21.1. Race condition khi refresh và cleanup diễn ra đồng thời

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant Store as Token Store
    participant AS as Authorization Server
    participant API as Orders API

    A->>Store: Load old AT-1 / RT-1
    B->>Store: Load old AT-1 / RT-1
    B->>AS: Refresh RT-1
    AS-->>B: New AT-2 / RT-2
    B->>Store: Save AT-2 / RT-2
    A->>API: Send old AT-1
    API-->>A: 401 invalid_token
    A->>Store: Remove authorized client by registration/principal
    Note over Store: Nếu xóa không kiểm tra phiên bản, AT-2/RT-2 vừa lưu có thể bị mất
~~~

Với repository mặc định, thao tác remove thường nhắm theo khóa registration/principal; **nó không nhất thiết có compare-and-delete theo token generation**. Nếu sản phẩm có concurrency cao và yêu cầu không mất refresh token mới, cần thiết kế layer lưu trữ/custom handler bảo đảm tính nhất quán theo version/token generation.

Đây là **thiết kế vận hành nâng cao**, không phải lý do để bỏ qua invalid_token hoặc giữ token bị từ chối vô thời hạn.

### 21.2. Shared storage phải được bảo vệ

Access token và refresh token là credential nhạy cảm. Nếu sử dụng JDBC/Redis/shared store, cần:

1. Quyền truy cập hạn chế cho service và operator.
2. TLS đến storage khi cần.
3. Encryption-at-rest và key management theo chính sách.
4. Không đưa token vào audit log/tracing.
5. TTL/retention/backup và quy trình xóa dữ liệu phù hợp.
6. Không cho ứng dụng khác đọc token của principal nếu không có authorization riêng.

## 22. Tác động của refresh token rotation

Trong một hệ thống hỗ trợ refresh token rotation:

~~~text
AT-1 + RT-1
   |
   | POST refresh_token=RT-1
   v
AT-2 + RT-2
   |
   +--> RT-1 có thể hết hiệu lực
~~~

Nếu một request khác vẫn dùng RT-1, Authorization Server có thể trả `invalid_grant`. Một số server có cơ chế **reuse detection** và có thể thu hồi cả token family.

Khi gặp `invalid_grant`:

- Không retry vô hạn với cùng refresh token.
- Kiểm tra request đồng thời, storage và việc lưu RT-2.
- Nếu RT thực sự hết hiệu lực, cần authorization mới theo grant phù hợp.
- Không tự thay client credentials hay sử dụng token của principal khác.

Một failure handler xóa token hỏng chỉ là **một phần của giải pháp**; với tải đồng thời, cần kiểm soát việc ai refresh và cập nhật đúng bản ghi.

## 23. Đường xử lý khi không có refresh token

Một OAuth2 Authorized Client có thể chỉ có access token:

~~~text
registration = company
principal    = employee-0042
accessToken  = AT-1 (expired/revoked)
refreshToken = null
~~~

Lúc này manager **không thể dùng refresh_token grant** để sửa trạng thái. Sau khi cleanup, ứng dụng thường cần bắt đầu **Authorization Code Flow** mới nếu đó là registration có login/cấp quyền tương tác.

Không có refresh token có thể là hành vi bình thường của Authorization Server. Việc yêu cầu scope `openid` hoặc thực hiện OIDC login không bảo đảm chắc chắn sẽ được cấp refresh token.

Không tự tạo refresh token từ ID Token hoặc session cookie. Những credential đó có mục đích khác và không thể thay thế nhau.

## 24. Background job và client_credentials

Giả sử Portal có scheduled job gọi Reports API bằng grant `client_credentials`.

Nó không có browser request/HTTP session. Khi đó manager phù hợp thường là:

~~~java
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
~~~

kết hợp `OAuth2AuthorizedClientService` và provider `clientCredentials()`.

Với client credentials, access token hết hạn thường được **cấp lại bằng client_credentials grant**, không cần refresh token của người dùng.

Nếu Reports API trả invalid_token, cleanup có thể nhằm bản ghi:

~~~text
registrationId = reports-service
principalName  = reports-worker
~~~

chứ không phải `company/employee-0042`. Lỗi token của service không nên khiến browser session của mọi nhân viên logout.

Trong background job, dùng service-based remover/service storage phù hợp; không bắt buộc có Servlet request/response khi xóa authorized client.

## 25. Không làm lệch ranh giới tin cậy khi tự xử lý failure

Một custom authorization failure handler có thể gây rủi ro nếu:

- Nó tin response body từ server không tin cậy rồi xóa token bất kỳ.
- Nó để user chọn `clientRegistrationId` và `principalName` tùy ý.
- Nó nhận exception từ **một HTTP client không có OAuth2 token** rồi xóa token của registration khác.
- Nó đưa `WWW-Authenticate`, token value hoặc client secret vào log.
- Nó biến mọi 403 thành “người dùng bị logout”.
- Nó tự retry request POST gây tác dụng phụ.

Hãy duy trì invariant:

~~~text
Token bị từ chối bởi đúng Resource Server
        |
        v
Xác định authorized client mà interceptor đã thực sự dùng
        |
        v
Chỉ xử lý error code nằm trong policy loại token
        |
        v
Xóa đúng registration/principal/context và ghi sự kiện an toàn
        |
        v
Không cấp nhầm token hoặc quyền mới
~~~

**Không dùng phản hồi của một server do user tùy ý chỉ định** để ra quyết định xóa token thuộc nhiều client registrations. Base URL và allowed destinations của OAuth2-enabled RestClient nên được cấu hình/giới hạn tại backend.

## 26. Testing: xác nhận token bị loại đúng lúc

Không cần gọi IdP hoặc Orders API production để kiểm tra hành vi. Có thể dùng:

- **MockRestServiceServer** hoặc mock HTTP server để trả response 401/403 và Bearer challenge.
- **Mock OAuth2AuthorizedClientManager** để cấp authorized client test.
- **In-memory OAuth2AuthorizedClientService** hoặc fake repository ghi nhận thao tác remove.
- **Spring Security Test** để tạo Authentication của user khi cần test Servlet request context.
- Test cho manager refresh failure bằng token endpoint giả.

### 26.1. Ma trận test chính

| Case | HTTP/token result | Hành vi cần xác minh |
|---|---|---|
| 200 OK | Bearer token hợp lệ | Không loại authorized client |
| 401 + Bearer invalid_token | Token bị Resource Server từ chối | Failure handler được kích hoạt và loại bản ghi phù hợp |
| 401 không có Bearer error rõ | Lỗi có thể không thuộc token | Không mặc định xóa nếu policy thiếu bằng chứng |
| 403 + insufficient_scope | Thiếu quyền | Không tự diễn giải thành token revoked |
| 403 business permission | User không có quyền resource | Không loại token chỉ vì status 403 |
| 429 | Rate limit | Không xóa token vì rate limiting |
| 500/503 | API outage | Không xóa token |
| Timeout | Lỗi kết nối | Không xóa token vì timeout đơn thuần |
| Refresh invalid_grant | RT hỏng/hết hiệu lực | Manager failure handling loại token theo chính sách |
| Refresh timeout | Không biết RT đã được sử dụng chưa | Không retry mù quáng, không xóa mọi account |
| Hai user | Token một user invalid | Không xóa token user khác |
| Hai registrations | Token company invalid | Không xóa reports-service/partner |
| Concurrent refresh+remove | AT mới vừa được lưu | Xác minh chính sách/versioning nếu yêu cầu |

### 26.2. Fixture test

Tạo một authorized client với token giả:

~~~java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("company")
        .clientId("test-portal")
        .clientSecret("test-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationUri("https://login.example.test/authorize")
        .tokenUri("https://login.example.test/token")
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .build();

Instant now = Instant.now();
OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "TEST_TOKEN_NOT_REAL",
    now.minusSeconds(30),
    now.plusSeconds(300),
    Set.of("orders.read")
);

OAuth2AuthorizedClient authorizedClient =
    new OAuth2AuthorizedClient(
        registration,
        "employee-0042",
        accessToken
    );
~~~

Fixture này chỉ là token **giả** để mock manager/repository. Nó không cần được Authorization Server ký. Một test của RestClient interceptor nên stub manager trả authorized client này, giả lập Orders API 401 với:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

và xác minh remover đã nhắm tới `company/employee-0042`. Sau đó test 403 `insufficient_scope` và 500 để đảm bảo không xóa token sai.

### 26.3. Test wiring, không chỉ test class riêng lẻ

Một test chỉ tạo `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` và gọi thủ công có thể xác nhận chức năng remover, nhưng **chưa chứng minh RestClient đang dùng handler đó**.

Cần kiểm tra chính `RestClient` được service/controller inject:

~~~text
RestClient builder
  -> OAuth2ClientHttpRequestInterceptor(manager)
  -> setAuthorizationFailureHandler(repository-backed handler)
  -> /api/orders request với clientRegistrationId(company)
  -> Mock response 401 invalid_token
  -> Repository.removeAuthorizedClient đúng registration/principal
~~~

Nếu interceptor không được gắn đúng instance RestClient, handler không bao giờ được gọi dù bean handler có tồn tại trong Spring context.

### 26.4. Không dùng production token trong test

Không đưa client secret, refresh token, ID Token hoặc cookie thật vào fixture. Nếu cần đánh giá token endpoint integration, dùng Authorization Server giả/tách biệt, test credential riêng và hệ thống logging đã được che.

## 27. Quan sát và metric khi có lỗi authorized client

Một số metric phù hợp:

| Metric/event | Ý nghĩa |
|---|---|
| `oauth_authorized_client_resolved` | Manager tìm được authorized client |
| `oauth_refresh_attempted` | Có thử refresh token |
| `oauth_refresh_failed` | Token endpoint lỗi |
| `oauth_resource_invalid_token` | Resource Server từ chối Bearer token |
| `oauth_authorized_client_removed` | Đã cleanup bản ghi theo policy |
| `oauth_reauthorization_required` | Cần authorization mới |
| `oauth_insufficient_scope` | Thiếu scope/quyền |
| `oauth_downstream_unavailable` | Lỗi 5xx/network, không nhất thiết liên quan token |

Những metric này là **gợi ý đặt tên**, không phải Spring Security tự động phát đầy đủ. Khi instrument, cần ghi các trường không nhạy cảm như registration ID đã allowlist, error code, status, duration, trace ID và outcome.

Tránh ghi:

~~~text
access_token=<actual-token>
refresh_token=<actual-token>
client_secret=<actual-secret>
Authorization: Bearer <actual-token>
JSESSIONID=<actual-session>
~~~

Đặc biệt, **token expiry** có thể không giải thích mọi `invalid_token`; hãy quan sát response Resource Server và token lifecycle thay vì log toàn bộ JWT để tiện điều tra.

## 28. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Cách khoanh vùng |
|---|---|---|
| Orders API cứ trả 401 với cùng AT-1 | Interceptor không có failure handler, remove không đúng store | Kiểm tra RestClient bean, failure handler và repository |
| Có handler bean nhưng không bao giờ được gọi | Không gắn vào chính RestClient dùng gọi API | Xem `setAuthorizationFailureHandler(...)` trên interceptor được sử dụng |
| Token bị xóa khi API trả 500 | Custom handler xóa theo mọi lỗi | Giới hạn theo OAuth2/Bearer error thích hợp |
| Xóa token nhưng request sau vẫn dùng AT-1 | Store khác, cache stale hoặc manager/HTTP client dùng instance khác | Kiểm tra repo/service, cache, registration/principal |
| Xóa token xong không tự có token mới | Authorization Code Grant cần browser/consent | Thiết kế reauthorization flow |
| 403 insufficient_scope bị xử lý như expired token | Dùng HTTP status thay cho error code | Phân biệt scope/permission với token invalid |
| Refresh fail invalid_grant | RT hết hạn, revoked, rotation race | Kiểm tra manager failure handling và token store |
| Lỗi chỉ khi scale nhiều nodes | Storage không chia sẻ hoặc race refresh/remove | Kiểm tra shared store và versioning |
| Login thành công nhưng Orders API 401 | Token sai audience/issuer, hết hạn/revoked | Kiểm tra token dùng cho đúng API và WWW-Authenticate |
| 401 chỉ xảy ra sau proxy | Proxy không forward Authorization header hoặc có security layer khác | Kiểm tra luồng HTTP ở gateway, không xóa token mù |
| Một user bị lỗi làm user khác mất token | Cleanup keyed không đúng principal | Kiểm tra trusted Authentication, registration/principal binding |
| Reports job thất bại nhưng user bị logout | Trộn service token với user session | Tách managers và chính sách failure |
| Logout rồi RT vẫn còn | Local logout không phải remote revocation | Thiết kế cleanup/revocation endpoint |
| Token invalid nhưng UI báo sai mật khẩu | Gộp downstream error với login failure | Phân biệt entry point, token manager và Resource Server |

**Cách điều tra hiệu quả:** xác định lỗi được sinh ở **authorization request/callback**, **token endpoint**, **RestClient interceptor/manager** hay **Resource Server**. Mỗi tầng có cách xử lý khác nhau.

## 29. Các anti-pattern cần tránh

**1. Xóa token vì bất kỳ 401/403 nào.** HTTP status một mình không đủ chứng minh token invalid.

**2. Retry mọi request vô hạn sau khi cleanup.** Đặc biệt nguy hiểm với thao tác không idempotent.

**3. Logout user khi downstream API trả invalid_token.** Token của một registration có thể hỏng trong khi session Portal vẫn hợp lệ.

**4. Giữ token đã bị từ chối và tiếp tục gửi mãi.** Dẫn đến lỗi lặp và che mất nhu cầu reauthorization.

**5. Dùng access token của service thay cho user.** `client_credentials` không thay Authorization Code Flow của người dùng.

**6. Coi local cleanup là remote revocation.** Xóa database không đồng nghĩa Access Token hết hiệu lực tại mọi API.

**7. Xóa authorized client bằng principalName từ query parameter.** Có thể ảnh hưởng dữ liệu/token của người khác.

**8. Tự parse JWT rồi sửa expiration.** Không thể biến token cũ thành token mới bằng cách sửa claims tại client.

**9. Không xét race giữa refresh và remove.** Xóa theo key có thể làm mất bản ghi token mới hơn.

**10. Chỉ gắn handler cho manager nhưng bỏ qua Resource Server Bearer error.** Hai nguồn failure cần điểm tích hợp phù hợp.

**11. Bật wire logging chứa token để debug.** Access/refresh token và client secret phải được bảo vệ.

## 30. Bài tập tình huống

### Bài tập 1 — 401 invalid_token

Orders API trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Câu hỏi:** Nên làm gì với authorized client đã dùng để gọi API?

**Gợi ý:** Sử dụng failure handler tương ứng để loại authorized client `company` của đúng principal nếu policy xác định token không còn hợp lệ. Sau đó trả lỗi/điều phối reauthorization phù hợp, không tự logout toàn bộ Portal.

### Bài tập 2 — 403 insufficient_scope

Token có `orders.read`, Orders API yêu cầu `orders.write` và trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

**Câu hỏi:** Xóa token rồi refresh cùng scope có giải quyết được không?

**Gợi ý:** Thường không. Token có thể hợp lệ nhưng thiếu quyền; cần xem scope/consent và authorization của API.

### Bài tập 3 — Manager có token mới, handler vẫn xóa bản ghi cũ

Hai request concurrent: B vừa lưu AT-2 sau refresh, A nhận 401 cho AT-1 rồi xóa theo registration/principal.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** A có thể xóa AT-2 vừa được lưu nếu storage không kiểm tra version. Cân nhắc token generation/versioned removal trong môi trường concurrency cao.

### Bài tập 4 — HTTP 500

Orders API trả 503 khi backend đang bảo trì.

**Câu hỏi:** Có nên tự xóa authorized client?

**Gợi ý:** Không; 503 không chứng minh token invalid. Xử lý lỗi hạ tầng, backoff/retry có kiểm soát và thông báo phù hợp.

### Bài tập 5 — Logout Portal

User logout, session Portal bị hủy nhưng RT-1 còn trong persistent authorized-client service.

**Câu hỏi:** Có thể kết luận RT-1 đã bị revoke tại IdP chưa?

**Gợi ý:** Không. Local session, local token cleanup và remote revocation là những cơ chế khác nhau.

### Bài tập 6 — Chưa gắn handler

Ứng dụng đã khai báo `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` như một bean nhưng interceptor RestClient chỉ nhận manager.

**Câu hỏi:** Vì sao API vẫn gửi token invalid lặp lại?

**Gợi ý:** Bean tồn tại không có nghĩa interceptor đã sử dụng nó. Cần gắn handler bằng `setAuthorizationFailureHandler(...)` trên chính OAuth2 interceptor dùng trong RestClient bean.

### Bài tập 7 — Token endpoint invalid_grant

Manager cố refresh RT-1 nhưng Authorization Server trả `invalid_grant`. Orders API chưa được gọi.

**Câu hỏi:** Failure handler của Resource Server có xử lý trường hợp này không?

**Gợi ý:** Không trực tiếp. Lỗi phát sinh trong manager/token provider; cần xử lý authorization failure tại manager và cleanup authorized client đúng chính sách.

## 31. Checklist triển khai

| Câu hỏi | Điều cần xác định |
|---|---|
| Dùng Spring Security 6.4+ chưa? | Nếu dùng RestClient OAuth2 interceptor, class/API phải tồn tại |
| Ứng dụng dùng Servlet hay WebFlux? | Bài này dùng `HttpSecurity`, Servlet repository và RestClient |
| RestClient đã nhận manager đúng chưa? | Có `OAuth2ClientHttpRequestInterceptor(manager)` |
| Đã gắn failure handler vào interceptor chưa? | Có `setAuthorizationFailureHandler(...)` phù hợp |
| Handler xóa ở đâu? | Cùng repository/service nơi manager đã lưu authorized client |
| Registration và principal có đúng không? | Được lấy từ trusted request/service context |
| Resource Server trả Bearer error gì? | Phân biệt invalid_token, insufficient_scope và status không có challenge |
| Manager xử lý refresh invalid_grant ra sao? | Failure handler/cleanup ở token endpoint path |
| Sau cleanup, cơ chế reauthorization là gì? | Có user interaction, consent hay client_credentials hợp lệ? |
| Retry đã giới hạn chưa? | Không retry vô hạn, chú ý method không idempotent |
| Có multi-replica không? | Shared store, cache, race refresh/remove và versioning |
| Logout cần revoke từ xa không? | Có chính sách rõ, không nhầm với local cleanup |
| Có dùng đúng access token cho Resource Server không? | Audience, scope, issuer, registration phù hợp |
| Có test 401/403/500/refresh failure không? | Test loại đúng bản ghi, không xóa nhầm |
| Có phân biệt login và token state không? | Không logout user vô điều kiện vì API error |
| Logging có tránh credential không? | Không log AT/RT, client secret, code hoặc cookie |

## 32. Tổng kết

Trong **Spring Security OAuth 2.0/OIDC Client trên Servlet**, xử lý lỗi ủy quyền không chỉ là bắt HTTP 401 rồi retry. Một request qua **RestClient** có thể thất bại ở hai nơi: **Authorization Server/token endpoint** khi cấp hoặc refresh token, và **Resource Server** khi kiểm tra Bearer token. Cần phân biệt các lỗi như `invalid_grant`, `invalid_token` và `insufficient_scope`, cùng với HTTP 5xx, timeout và lỗi nghiệp vụ.

Với **Spring Security 6.4+**, `OAuth2ClientHttpRequestInterceptor` liên kết RestClient với `OAuth2AuthorizedClientManager`. Cấu hình thêm `OAuth2AuthorizationFailureHandler`, thường thông qua `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` và repository/service phù hợp, giúp **loại authorized client đã được xác định không còn hợp lệ**, tránh tiếp tục tái sử dụng token cũ. Nhưng thao tác này **không tự logout user, không tự revoke token ở IdP và không tự cấp token mới cho mọi grant**.

Thiết kế đáng tin cậy cần **xóa đúng registration/principal**, chỉ xử lý lỗi có đủ bằng chứng, giữ **retry có giới hạn**, không làm mất quyền hợp lệ vì `insufficient_scope` hay 5xx, và kiểm soát concurrency khi token được refresh hoặc rotate đồng thời. Kết hợp **manager + RestClient interceptor + failure handler + authorized-client store + chính sách reauthorization** đúng trách nhiệm sẽ giúp Portal phục hồi có kiểm soát trước lỗi token mà vẫn bảo vệ phiên đăng nhập và dữ liệu người dùng.
