# 18.2. Liên kết interceptor với OAuth2AuthorizedClientManager

## 1. Bối cảnh: RestClient gọi API cần Access Token

Trong một ứng dụng **Spring Security OAuth 2.0 OIDC Client** chạy trên **Servlet stack**, sau khi người dùng đăng nhập bằng OIDC hoặc một backend service được cấp quyền bằng Client Credentials, ứng dụng thường phải gửi HTTP request đến một **Resource Server**: lấy hồ sơ, đọc báo cáo, đồng bộ dữ liệu hoặc gọi API của đối tác.

Khi gọi API được bảo vệ bằng OAuth 2.0 Bearer Token, mỗi request cần mang **Access Token phù hợp**:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Vấn đề không dừng ở việc thêm một HTTP header. Ứng dụng phải xác định:

- Dùng **client registration** nào để xin token?
- Token thuộc **người dùng hiện tại** hay thuộc **service/application**?
- Access Token đã có trong kho lưu trữ chưa?
- Access Token có hết hạn, cần refresh hoặc xin mới không?
- Nếu Resource Server trả `401 invalid_token` hoặc `403 insufficient_scope`, có nên xóa bản ghi token cũ không?
- Làm thế nào để tránh đưa Access Token sang nhầm hostname hoặc ghi nó vào log?

Spring Security cung cấp **`OAuth2ClientHttpRequestInterceptor`** để kết nối HTTP client đồng bộ **`RestClient`** với **`OAuth2AuthorizedClientManager`**. Interceptor đảm nhiệm việc lấy authorized client thông qua manager và gắn token vào request, thay vì bắt từng controller tự xử lý Access Token.

**Mục tiêu của bài:** hiểu dòng chảy interceptor → manager → authorized client store → Bearer header; cấu hình Spring Security Servlet đúng API; chọn registration/principal; xử lý lỗi và kiểm thử hành vi an toàn.

> **Phạm vi phiên bản:** `RestClient` có trong Spring Framework 6.1 trở đi; `OAuth2ClientHttpRequestInterceptor` được giới thiệu từ **Spring Security 6.4** và tiếp tục có trong các phiên bản mới. Nếu dự án dùng nhánh Spring Security cũ hơn, không thể chỉ copy class này vào source rồi kỳ vọng biên dịch được. Ví dụ Java bên dưới theo phong cách Spring Boot 3.x/Spring Security 6.4+ và Servlet.

## 2. Phân biệt RestClient, interceptor và manager

Trước khi cấu hình, cần tách bốn vai trò:

| Thành phần | Trách nhiệm | Không có trách nhiệm |
| --- | --- | --- |
| **`RestClient`** | Thực thi HTTP request đồng bộ đến API | Không tự hiểu OAuth2 grants nếu không được tích hợp |
| **`OAuth2ClientHttpRequestInterceptor`** | Chặn outbound HTTP request, chọn registration/principal, nhờ manager lấy authorized client rồi đính Bearer Token | Không tự xác minh người dùng OIDC hay trở thành Token Endpoint |
| **`OAuth2AuthorizedClientManager`** | Tải authorized client cũ, điều phối authorization/re-authorization, xin hoặc làm mới token theo grant đã cấu hình | Không thay Resource Server authorization |
| **`OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService`** | Lưu/tải/xóa token theo ngữ cảnh và khóa tương ứng | Không tự gọi Token Endpoint để refresh |

Ngoài ra còn có:

- **`ClientRegistrationRepository`**: kho cấu hình các clients như `company-login` hay `reports-service`.
- **`OAuth2AuthorizedClientProvider`**: chiến lược grant như `authorization_code`, `refresh_token`, `client_credentials`.
- **`Resource Server`**: API đích xác minh Access Token, scope, audience và chính sách của chính nó.

### 2.1. Sơ đồ kết nối cơ bản

~~~mermaid
flowchart TD
    A["Controller hoặc service cần gọi API"] --> B["RestClient.get/post(...)"]
    B --> C["OAuth2ClientHttpRequestInterceptor"]
    C --> D["Xác định clientRegistrationId và principal"]
    D --> E["OAuth2AuthorizedClientManager.authorize(...)"]
    E --> F{"Có authorized client hợp lệ?"}
    F -->|"Có"| G["Lấy Access Token đã lưu"]
    F -->|"Chưa có/hết hạn"| H["OAuth2AuthorizedClientProvider"]
    H --> I["Token Endpoint: cấp mới/refresh theo grant"]
    I --> J["Repository/Service lưu token mới"]
    J --> G
    G --> K["Gắn Authorization: Bearer <token>"]
    K --> L["Thực thi outbound HTTP request"]
    L --> M["Resource Server kiểm tra token và policy"]
~~~

Sơ đồ mô tả **đường đi logic**. Manager/provider có thể sử dụng lại token, trả `null` hoặc yêu cầu khởi tạo authorization tùy grant và trạng thái giao dịch. Không nên coi mọi lần `RestClient.get()` đều phải thực hiện một lần gọi Token Endpoint.

### 2.2. Luồng theo thời gian

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Spring MVC Service
    participant RC as RestClient
    participant I as OAuth2ClientHttpRequestInterceptor
    participant M as OAuth2AuthorizedClientManager
    participant S as AuthorizedClient Store
    participant AS as Authorization Server
    participant RS as Resource Server
    App->>RC: get().uri("/v1/reports").attributes(...)
    RC->>I: Intercept outbound request
    I->>M: authorize(registrationId, principal)
    M->>S: Tải OAuth2AuthorizedClient
    alt Chưa có token hoặc cần cấp mới
        M->>AS: Client Credentials hoặc grant phù hợp
        AS-->>M: Access Token mới
        M->>S: Lưu/cập nhật authorized client
    else Token hiện có còn phù hợp
        S-->>M: Authorized client đã lưu
    end
    M-->>I: OAuth2AuthorizedClient
    I->>RC: Gắn Bearer Access Token
    RC->>RS: GET /v1/reports + Authorization header
    RS-->>RC: HTTP response
    RC-->>App: Response body hoặc error
~~~

Trong luồng thực, việc thêm header xảy ra bên trong interceptor khi request được xử lý. **Interceptor gửi Access Token, không gửi ID Token hay Refresh Token** tới Resource Server.

## 3. Cách Spring Security liên kết interceptor với manager

Điểm tích hợp trực tiếp là constructor:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

OAuth2ClientHttpRequestInterceptor interceptor =
    new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

RestClient restClient = RestClient.builder()
    .requestInterceptor(interceptor)
    .build();
~~~

Đoạn này giả định biến `authorizedClientManager` được cung cấp bởi Spring container hoặc ứng dụng. Không phải token được hard-code vào interceptor: **interceptor nhận manager**, còn manager biết cách tìm/cấp token.

### 3.1. Ví dụ bean RestClient tối giản

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OAuth2RestClientConfig {

    @Bean
    RestClient oauth2RestClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager);

        return RestClient.builder()
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

Đây là cấu hình **cốt lõi**. Để thực sự gọi một API, request còn cần **chọn client registration** (theo mặc định qua request attributes), có principal context hợp lệ và manager được cấu hình grant/store phù hợp.

### 3.2. Cấu hình phải thống nhất ở cả ba tầng

~~~text
spring.security.oauth2.client.registration.reports-service
   |
   | registrationId = "reports-service"
   v
RestClient request attributes
   |
   | clientRegistrationId("reports-service")
   v
OAuth2ClientHttpRequestInterceptor
   |
   v
OAuth2AuthorizedClientManager
   |
   +-- ClientRegistrationRepository: tìm "reports-service"
   +-- OAuth2AuthorizedClientService/Repository: tìm token
   +-- OAuth2AuthorizedClientProvider: thực hiện grant phù hợp
~~~

Nếu request đặt `clientRegistrationId("reports-service")` nhưng YAML đăng ký tên `report-service`, manager không tìm được registration đúng. **Tên registration phải khớp chính xác** giữa code và cấu hình.

## 4. Chọn clientRegistrationId theo từng outbound request

`OAuth2ClientHttpRequestInterceptor` sử dụng một **`ClientRegistrationIdResolver`** để biết nên dùng client nào. Theo cấu hình mặc định, **`RequestAttributeClientRegistrationIdResolver`** đọc registration ID từ attributes của `RestClient` request.

Spring Security có tiện ích:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
~~~

Trong Java thật, static import nên đặt trên **một dòng**:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
~~~

Gọi API:

~~~java
String response = restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);
~~~

`clientRegistrationId(...)` ở đây thiết lập **request attribute nội bộ của RestClient**, **không phải** query parameter gửi tới Resource Server.

### 4.1. Vì sao cần request attribute?

Một ứng dụng có thể dùng nhiều client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
          billing-service:
            provider: company-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Với cùng một RestClient bean, request đến Reports API cần `reports-service`, còn Billing API cần `billing-service`:

~~~java
String reportsJson = restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);

String billingJson = restClient.get()
    .uri("https://billing.example.net/v1/invoices")
    .attributes(clientRegistrationId("billing-service"))
    .retrieve()
    .body(String.class);
~~~

Ví dụ minh họa cách chọn registration; trong production nên **tách RestClient theo API đích hoặc giới hạn hostname** để tránh token bị gửi sang URL do người dùng quyết định.

### 4.2. Không dùng registrationId từ URL người dùng mà không kiểm soát

Phản ví dụ:

~~~java
// KHÔNG DÙNG: user tự chọn registration và destination tùy ý.
restClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId(userSuppliedRegistrationId))
    .retrieve()
    .body(String.class);
~~~

Hậu quả có thể gồm:

- Gửi Access Token của registration nhạy cảm tới URL không đáng tin.
- Truy cập nhầm API/tenant.
- Dùng quyền của backend cho một request do người dùng không đủ quyền điều khiển.
- Tạo nguy cơ SSRF và lộ Bearer Token.

**Registration và Resource Server phải được chọn từ allowlist server-side** theo tính năng/tenant được phép, không phải từ các giá trị tùy ý của browser.

### 4.3. Custom ClientRegistrationIdResolver

Khi tất cả API requests của một RestClient luôn cần cùng registration, hoặc cần lấy registration từ Authentication đã được xác minh, có thể thay resolver:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;

oauth2.setClientRegistrationIdResolver(request -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    if (auth instanceof OAuth2AuthenticationToken oauth2Login) {
        return oauth2Login.getAuthorizedClientRegistrationId();
    }
    return null;
});
~~~

Đây là một **cách chọn registration dựa vào phiên đăng nhập OIDC/OAuth2**. Với Client Credentials chạy background, `SecurityContextHolder` có thể không có Authentication, nên cách này không phù hợp để chọn service registration.

Một lỗi thiết kế cần tránh: tự động suy ra registration của user login rồi dùng Access Token đó gọi **mọi** downstream API. Token login chỉ nên được gửi đến API mà nó được cấp phép/audience phù hợp.

## 5. Chọn principal: token của người dùng hay token của ứng dụng?

Đây là phần quan trọng nhất khi liên kết interceptor và manager.

`OAuth2AuthorizedClient` thường được lưu theo khóa logic:

~~~text
(clientRegistrationId, principalName)
~~~

Interceptor có **`PrincipalResolver`** để xác định principal mà manager sử dụng. Mặc định, **`SecurityContextHolderPrincipalResolver`** lấy Authentication hiện tại từ `SecurityContextHolder`.

Hai kiểu sử dụng cần được tách bạch:

| Kịch bản | Principal được chọn | Token được quản lý |
| --- | --- | --- |
| Người dùng đăng nhập qua OIDC và gọi API theo quyền của mình | Authentication của user hiện tại | Delegated user token |
| Backend/scheduled job gọi API bằng Client Credentials | Principal name cố định của service/application | Application token |
| Multi-tenant service có các client credentials khác nhau | Principal có namespace và registration phù hợp chính sách | Token tương ứng từng service/tenant đã được phê duyệt |

### 5.1. Mặc định lấy principal từ SecurityContextHolder

Trong Spring MVC request sau OIDC Login:

~~~text
Browser session
  -> Spring Security Authentication: alice
  -> SecurityContextHolderPrincipalResolver
  -> principal = alice
  -> OAuth2AuthorizedClientManager
  -> ("company-login", "alice") authorized client
~~~

Khi cấu hình interceptor như phần 3, có thể chỉ cần:

~~~java
restClient.get()
    .uri("https://api.partner.example.net/v1/me")
    .attributes(clientRegistrationId("company-login"))
    .retrieve()
    .body(String.class);
~~~

**Điều kiện:** request đang nằm trong luồng có Authentication hợp lệ, `company-login` là registration gắn với user, và Access Token được cấp cho đúng API đích. Không giả định một token từ OIDC Login có thể gọi bất kỳ API nào.

### 5.2. Dùng RequestAttributePrincipalResolver cho Client Credentials

Với **Client Credentials**, thông thường muốn mọi lần gọi của cùng một service tái sử dụng authorized client gắn với **một principal application-level**, thay vì token bị chia theo từng user đang mở browser.

Spring Security cung cấp:

~~~java
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
~~~

Khi cấu hình:

~~~java
oauth2.setPrincipalResolver(
    new RequestAttributePrincipalResolver());
~~~

thì request cần cung cấp principal qua attributes:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .attributes(principal("system-report-exporter"))
    .retrieve()
    .body(String.class);
~~~

`system-report-exporter` là **khóa định danh logic của service trong authorized client store**, không phải một tài khoản người dùng đã đăng nhập OIDC.

Đặt principal thống nhất giúp manager tải lại token đã lưu, thay vì tạo một authorized client riêng cho mỗi HTTP request hoặc mỗi user web.

### 5.3. Không trộn token application-level và delegated user token

Giả sử user Alice mở trang báo cáo. Một backend service có token Client Credentials với scope `reports.read.all`. Nếu ứng dụng cho mọi user đã đăng nhập gọi API bằng token đó, **Resource Server có thể không biết user nào yêu cầu dữ liệu**.

Điều đó chỉ an toàn nếu:

1. Backend thực thi đầy đủ authorization của user/tenant **trước khi** dùng service token.
2. Endpoint đích được thiết kế cho service-level access.
3. Service token không bị đưa cho browser.
4. Không dùng các tham số tùy ý để truy cập dữ liệu người khác.

Khi API yêu cầu **delegated user identity**, phải dùng grant và token phù hợp, không thay bằng Client Credentials để vượt qua chính sách.

## 6. Ví dụ hoàn chỉnh A: RestClient gọi API bằng Client Credentials

Ví dụ sau tách rõ **cấu hình registration**, **authorized client manager**, **RestClient interceptor** và **service gọi API**.

### 6.1. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Địa chỉ trên là ví dụ. Client Secret phải được cung cấp qua secret manager hoặc cấu hình môi trường an toàn; không hard-code trong source code.

Client Credentials **không cần `redirect-uri`, `state`, PKCE hoặc browser login** cho grant cơ bản.

### 6.2. Cấu hình manager cho service-to-service

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class MachineClientManagerConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            machineAuthorizedClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Vì đây là **service manager**, không cần Servlet request/response. `OAuth2AuthorizedClientService` có thể lưu trong memory hoặc database tùy yêu cầu persistence và scale-out.

Nếu dự án đã có manager bean cùng mục đích, **không cần khai báo thêm bean trùng**. Hãy dùng manager hiện có hoặc cấu hình một manager riêng với qualifier rõ ràng.

### 6.3. Liên kết RestClient với manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
public class ReportsApiHttpConfig {

    @Bean
    RestClient reportsRestClient(
            RestClient.Builder builder,
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

        // Với Client Credentials, dùng principal dành riêng cho application.
        oauth2.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        // Nếu API báo Bearer Token không còn hợp lệ, cân nhắc xóa
        // authorized client cũ theo OAuth2 error code.
        OAuth2AuthorizationFailureHandler failureHandler =
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(authorizedClients);
        oauth2.setAuthorizationFailureHandler(failureHandler);

        return builder
            .baseUrl("https://api.example.net")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

Đoạn mã giả định Spring Boot cấu hình `RestClient.Builder` và dự án có một manager/service đúng mục đích. `baseUrl` cố định giúp API client không phải nhận URL hoàn chỉnh từ user.

**Hành vi failure handler phải được hiểu đúng:** helper có thể xóa authorized client theo **OAuth2 error code và điều kiện phù hợp**, không phải xóa mọi token khi thấy bất kỳ HTTP 401/403 nào. Việc xóa thường hỗ trợ **request tiếp theo** lấy token mới; không bảo đảm interceptor tự retry chính request đã lỗi.

### 6.4. Gọi API từ service

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsGateway {

    private final RestClient reportsRestClient;

    public ReportsGateway(RestClient reportsRestClient) {
        this.reportsRestClient = reportsRestClient;
    }

    public String loadReportsJson() {
        return reportsRestClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("reports-service"))
            .attributes(principal("system-report-exporter"))
            .retrieve()
            .body(String.class);
    }
}
~~~

Điều xảy ra khi gọi `loadReportsJson()`:

1. RestClient tạo outbound GET tới Reports API.
2. Interceptor lấy `clientRegistrationId=reports-service` từ request attributes.
3. `RequestAttributePrincipalResolver` lấy principal `system-report-exporter`.
4. Manager tìm `OAuth2AuthorizedClient` của cặp registration/principal.
5. Nếu chưa có hoặc cần token mới, `clientCredentials()` provider gọi Token Endpoint.
6. Manager lưu bản ghi token mới qua service.
7. Interceptor gắn `Authorization: Bearer ...`.
8. Resource Server xác minh token và trả response.

Trong demo, response là raw JSON string để tập trung vào OAuth2. Sản phẩm thật thường chuyển JSON thành DTO được xác định schema, có validation và xử lý lỗi.

### 6.5. Vì sao không truyền Authorization header ở service?

Không nên viết:

~~~java
// PHẢN VÍ DỤ khi đã dùng OAuth2 interceptor:
String token = loadSomeTokenManually();
restClient.get()
    .uri("/v1/reports")
    .header("Authorization", "Bearer " + token)
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);
~~~

Với interceptor OAuth2, code vừa tự gắn Bearer header vừa yêu cầu interceptor gắn token có thể dẫn đến **header chồng chéo hoặc nguồn token không nhất quán**. Chỉ nên có một thành phần chịu trách nhiệm cấp và đặt credential.

## 7. Ví dụ B: gọi API bằng Access Token của người dùng đã đăng nhập OIDC

Không phải mọi RestClient call đều dùng Client Credentials. Portal Spring MVC có thể đăng nhập bằng OIDC rồi gọi một API **thay mặt người dùng hiện tại**.

### 7.1. Cấu hình OIDC login

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Scope `reports.read` là ví dụ phụ thuộc provider. Việc request scope này **không tự bảo đảm** Access Token được Resource Server chấp nhận; provider phải cấu hình audience/resource phù hợp.

### 7.2. SecurityFilterChain cho Servlet

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

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

`oauth2Login()` đảm nhiệm giao dịch đăng nhập OIDC; `oauth2Client()` hỗ trợ chức năng OAuth2 Client trong Servlet application. **RestClient không tự xác thực browser** — nó sử dụng Authentication/authorized client đã được hệ thống quản lý.

### 7.3. RestClient dùng principal mặc định từ SecurityContext

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class UserApiHttpConfig {

    @Bean
    RestClient userReportsRestClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager authorizedClientManager,
            OAuth2AuthorizedClientRepository authorizedClientRepository) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager);

        // KHÔNG thay PrincipalResolver: mặc định lấy Authentication
        // hiện tại từ SecurityContextHolder.
        OAuth2AuthorizationFailureHandler failureHandler =
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(authorizedClientRepository);
        oauth2.setAuthorizationFailureHandler(failureHandler);

        return builder
            .baseUrl("https://reports.example.net")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

Ở đây dùng repository vì ứng dụng đang làm việc trong Servlet request với user Authentication. **Đừng mặc định chuyển sang service manager cho delegated user token** nếu ứng dụng đang dựa trên repository/session và không có thiết kế lưu trữ tương đương.

### 7.4. Controller hoặc service dùng API

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class MyReportsController {

    private final RestClient userReportsRestClient;

    public MyReportsController(RestClient userReportsRestClient) {
        this.userReportsRestClient = userReportsRestClient;
    }

    @GetMapping("/my-reports")
    public ResponseEntity<String> myReports() {
        String json = userReportsRestClient.get()
            .uri("/v1/my-reports")
            .attributes(clientRegistrationId("company-login"))
            .retrieve()
            .body(String.class);

        return ResponseEntity.ok(json);
    }
}
~~~

Authentication của browser đã đăng nhập được lấy theo **SecurityContext**; interceptor và manager sử dụng principal của người dùng, không dùng `principal("system-report-exporter")`.

**Lưu ý về kiến trúc:** ví dụ trả raw JSON của downstream API để đơn giản hóa phần HTTP. Trong ứng dụng thật cần kiểm soát nội dung được công bố, handling JSON, privacy và timeout. Không tự động proxy nguyên mọi response của API ngoài cho browser.

## 8. Chọn đúng OAuth2AuthorizedClientManager

Có hai manager phổ biến:

| Manager | Đầu vào/kho lưu | Dùng khi |
| --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository` | Trong Servlet HTTP request, gắn với Authentication/session |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientService` | Service, scheduled job, batch, hoặc gọi ngoài HTTP request |

### 8.1. Vì sao manager Servlet cần HTTP context?

Repository có các phương thức nhận `HttpServletRequest` và đôi khi `HttpServletResponse`. Do đó, `DefaultOAuth2AuthorizedClientManager` phải giải quyết request/response hiện tại hoặc được cung cấp ngữ cảnh phù hợp.

Nếu một background worker không có Servlet request cố dùng Default manager, quá trình load/save token có thể thất bại do thiếu context.

### 8.2. Service manager không tự đại diện cho end-user

`AuthorizedClientServiceOAuth2AuthorizedClientManager` không cần Servlet request, nhưng điều đó **không có nghĩa** có thể tùy ý truy xuất Access Token của người dùng khác. Principal name/registration phải đến từ workflow được cấp quyền và chính sách kiểm soát.

Với Client Credentials, principal service-level ổn định là lựa chọn tự nhiên. Với delegated user token ngoài HTTP request, cần cơ chế lưu trữ và sự đồng ý của người dùng phù hợp, không dùng email tự do để tìm token.

### 8.3. Manager tự lưu token mới theo cấu hình

Thông thường, các manager có **authorization success handler** mặc định để lưu `OAuth2AuthorizedClient` sau khi cấp hoặc refresh thành công:

~~~text
Manager.authorize(...)
  -> Provider cấp/refresh token thành công
  -> OAuth2AuthorizationSuccessHandler
  -> saveAuthorizedClient qua Repository hoặc Service
~~~

**Đừng thay success handler mặc định bằng một lambda chỉ ghi log** rồi quên bước lưu, vì interceptor có thể phải xin token mới ở mọi request hoặc không lưu Refresh Token được xoay vòng.

### 8.4. Không cần tự gắn token thủ công cho manager

Để RestClient tự vận hành với manager, thường chỉ cần:

~~~java
new OAuth2ClientHttpRequestInterceptor(authorizedClientManager)
~~~

và request attributes đúng. Application không phải tự đọc Access Token từ database rồi nhét vào interceptor bằng biến mutable toàn cục.

## 9. Authorized client được tải, refresh và lưu thế nào?

`OAuth2AuthorizedClient` gồm:

~~~text
ClientRegistration registration
String principalName
OAuth2AccessToken accessToken
OAuth2RefreshToken refreshToken (có thể null)
~~~

Khi interceptor gọi manager:

1. **Load:** tìm authorized client theo registration/principal ở repository/service.
2. **Assess:** provider/grant quyết định token hiện tại có thể dùng lại hay cần cấp/refresh.
3. **Authorize:** thực hiện grant phù hợp, có thể là Refresh Token hoặc Client Credentials.
4. **Persist:** manager lưu client mới qua success handler.
5. **Apply:** interceptor gửi Access Token trong Bearer header.

### 9.1. Authorization Code/OIDC với Refresh Token

Nếu delegated user token hết hạn và provider đã cấp Refresh Token, manager có thể dùng `refresh_token` grant khi được cấu hình. Khi Authorization Server trả Refresh Token mới, manager phải lưu client mới.

Không dùng Refresh Token làm header của API. Refresh Token chỉ được gửi đến Token Endpoint theo giao thức.

### 9.2. Client Credentials không cần Refresh Token mặc định

Với Client Credentials, Authorization Server thường **không cấp Refresh Token**. Khi Access Token hết hạn, manager xin **Access Token mới bằng Client Credentials grant**, thay vì làm OIDC browser login.

Không cần thêm `openid`, `offline_access` hoặc `refresh_token` grant chỉ vì backend muốn Access Token mới.

### 9.3. Không tự suy luận Access Token còn hiệu lực vô hạn

`OAuth2AccessToken.getExpiresAt()`, khi được cung cấp, mô tả thời điểm hết hạn. Manager/provider có thể tính clock skew để chủ động cấp/refresh trước hạn.

Nếu Resource Server thu hồi token trước hạn, manager có thể vẫn coi token còn hạn theo thời gian. Đây là lý do cần xét phản hồi `401 invalid_token` của API và sử dụng failure handler đúng cách.

### 9.4. Concurrent requests và token rotation

Hai HTTP requests đồng thời có thể cùng phát hiện token hết hạn. Nếu token refresh bị xoay vòng một lần dùng:

~~~text
Request A: refresh token cũ -> nhận token mới
Request B: refresh token cũ -> invalid_grant
Request A: save authorized client mới
Request B: failure handler xử lý lỗi từ request cũ
~~~

Khi tải cao, cân nhắc đồng bộ theo `registrationId + principalName`, optimistic locking hoặc storage coordination nếu có rủi ro ghi đè/xóa nhầm. Không dùng **global lock** cho mọi authorized clients.

Interceptor giúp ứng dụng tránh tự viết phần gắn token, **không mặc nhiên giải quyết mọi bài toán concurrency giữa nhiều nodes**.

## 10. Xử lý HTTP 401/403 từ Resource Server

Một lần token exchange thành công vẫn có thể dẫn tới lỗi khi gọi API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Hoặc:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

### 10.1. Hai lỗi khác nhau

| Dấu hiệu từ API | Ý nghĩa thường gặp | Phản ứng |
| --- | --- | --- |
| `401 invalid_token` | Token hết hạn, bị thu hồi, sai issuer/audience hoặc không hợp lệ | Điều tra token/registration, có thể xóa cached authorized client và cấp token mới |
| `403 insufficient_scope` | Token được nhận diện nhưng không đủ quyền cho thao tác | Không tự cấp thêm scope; xem chính sách API, có thể cần authorization khác |
| `403` khác | Có thể do tenant/ownership/policy của API | Không quy chắc chắn là lỗi token |
| `429` | Rate limit | Retry/backoff theo hợp đồng API |
| `5xx` | Upstream lỗi | Xử lý timeout/circuit breaker/retry có giới hạn |

**Không dùng HTTP status duy nhất để xóa mọi token.** Spring Security hỗ trợ helper sử dụng mã OAuth2/Bearer để xác định có nên loại bỏ authorized client.

### 10.2. Authorization failure handler của interceptor

Một điểm mở rộng trên interceptor:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;

OAuth2AuthorizationFailureHandler failureHandler =
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientService);

interceptor.setAuthorizationFailureHandler(failureHandler);
~~~

Nếu làm việc trong Servlet context có repository:

~~~java
OAuth2AuthorizationFailureHandler failureHandler =
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientRepository);

interceptor.setAuthorizationFailureHandler(failureHandler);
~~~

`authorizedClientService` và `authorizedClientRepository` ở đây là các dependency đã được cấu hình; hai đoạn là **phương án thay thế theo manager/store**, không dùng cả hai cho cùng một interceptor.

Helper tạo failure handler kiểu **`RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`** và có thể xóa cached client khi lỗi Bearer cho thấy token không dùng được. Hành vi xóa cụ thể phụ thuộc OAuth2 error code, không phải mặc định xóa bất kỳ lỗi HTTP nào.

### 10.3. Interceptor có tự retry request vừa nhận 401 không?

Đừng mặc định. Cơ chế xóa cached authorized client chủ yếu cho phép **lần gọi tiếp theo** xin token mới. Request đang lỗi vẫn có thể được `RestClient.retrieve()` chuyển thành exception theo error handler của RestClient.

Nếu ứng dụng muốn retry API call:

- Chỉ retry khi lỗi được phân loại và grant phù hợp có thể khôi phục.
- Giới hạn số lần retry, tránh vòng lặp 401 vô tận.
- Với POST/PATCH/DELETE, đánh giá **idempotency** và nguy cơ tác dụng kép.
- Không retry `403 insufficient_scope` bằng cách tự tăng quyền.
- Không gửi token mới sang hostname khác để “thử”.

### 10.4. Một lỗi từ Token Endpoint không giống lỗi từ Resource Server

~~~text
Interceptor -> Manager -> Token Endpoint
   invalid_client / invalid_scope / invalid_grant
   => OAuth2 authorization/token-client failure.

Interceptor -> RestClient -> Resource Server
   401 invalid_token / 403 insufficient_scope
   => API bearer-token failure.
~~~

`OAuth2ClientHttpRequestInterceptor.setAuthorizationFailureHandler(...)` chủ yếu liên quan những lỗi **Resource Server** mà interceptor nhận được. Đối với lỗi Token Endpoint, manager/provider có failure-handling và exception riêng. Không gộp mọi lỗi OAuth2 vào một handler duy nhất.

## 11. Xử lý exception khi dùng RestClient

`RestClient.retrieve()` thường ném exception khi Resource Server trả HTTP lỗi theo chính sách error handling mặc định.

Một service có thể phân loại HTTP lỗi mà không làm lộ token:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public class SafeReportsGateway {

    private final RestClient reportsRestClient;

    public SafeReportsGateway(RestClient reportsRestClient) {
        this.reportsRestClient = reportsRestClient;
    }

    public String getReports() {
        try {
            return reportsRestClient.get()
                .uri("/v1/reports")
                .attributes(clientRegistrationId("reports-service"))
                .attributes(principal("system-report-exporter"))
                .retrieve()
                .body(String.class);
        } catch (HttpClientErrorException.Unauthorized ex) {
            throw new IllegalStateException(
                "Reports API không chấp nhận Access Token", ex);
        } catch (HttpClientErrorException.Forbidden ex) {
            throw new IllegalStateException(
                "Service không đủ quyền với Reports API", ex);
        } catch (RestClientResponseException ex) {
            throw new IllegalStateException(
                "Reports API trả HTTP lỗi", ex);
        }
    }
}
~~~

Đoạn này tập trung vào **phân loại HTTP response**, không phải cơ chế retry hoàn chỉnh. Trong production cần chọn exception hierarchy của ứng dụng, mã lỗi an toàn, timeout, circuit breaker và chính sách quan sát lỗi.

Không tự trả `ex.getResponseBodyAsString()` ra browser hoặc ghi toàn bộ exception/request headers vào log nếu hệ thống có nguy cơ chứa thông tin nhạy cảm.

### 11.1. Nếu manager không lấy được token

Lỗi `invalid_client`, `invalid_scope`, thiếu ClientRegistration hoặc không đủ authorization context xảy ra **trước khi HTTP call tới Resource Server**. Cần phân loại tại tầng OAuth2AuthorizedClientManager/token client.

Nếu một grant yêu cầu browser tương tác mà service đang chạy background, manager có thể không thể hoàn thành flow. **Không dùng Client Credentials để thay delegated-user authorization** chỉ vì muốn tránh màn hình consent.

### 11.2. Lỗi security context ở thread khác

Khi request được thực hiện trong `@Async`, scheduled job hoặc worker thread, SecurityContext từ HTTP thread **không mặc định** có ở đó.

Với delegated user:

- Phải có chiến lược truyền ngữ cảnh an toàn nếu nghiệp vụ cần gọi API thay user ngoài HTTP request.
- Không chọn principal của user cuối qua biến global.
- Không tự sao chép Access Token vào thread-local không quản lý vòng đời.

Với Client Credentials:

- Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
- Dùng principal application-level qua `RequestAttributePrincipalResolver`.
- Không phụ thuộc `SecurityContextHolder` của một browser request.

## 12. Cấu hình storage để interceptor và manager thống nhất

RestClient interceptor có thể gọi manager thành công nhưng lần request tiếp theo vẫn phải xin token mới nếu **authorized client store** không được dùng nhất quán.

### 12.1. Kho lưu trong memory

`InMemoryOAuth2AuthorizedClientService` phù hợp với demo hoặc service không yêu cầu token tồn tại qua restart. Trong nhiều instance, memory store ở node A không tự có trên node B.

### 12.2. Dùng JDBC khi cần persistence

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

Đây là cấu hình khái niệm, cần có Spring JDBC, datasource, schema migration đúng phiên bản và bảo mật database. Nếu Spring Boot đã có service bean, tránh tạo bean trùng.

### 12.3. Cùng một kho dùng cho manager và failure handler

Nếu manager lưu vào service A nhưng interceptor failure handler lại xóa ở service B, hành vi cache invalidation sẽ không đúng.

~~~text
Manager
  -> AuthorizedClientService A
      key: (reports-service, system-report-exporter)

Interceptor FailureHandler
  -> PHẢI tương thích với store A và đúng principal key
~~~

Vì vậy khi cấu hình:

~~~java
new OAuth2ClientHttpRequestInterceptor(machineManager)
~~~

và:

~~~java
OAuth2ClientHttpRequestInterceptor.authorizationFailureHandler(
    authorizedClients)
~~~

hãy đảm bảo `machineManager` và `authorizedClients` dùng chung backing store và chiến lược principal.

### 12.4. Xóa local token không phải revoke token ở Authorization Server

Failure handler có thể loại bỏ cached authorized client để request sau xin token mới. **Thao tác này không tự thu hồi token ở Authorization Server**. Nếu cần revoke theo chính sách, dùng protocol/revocation endpoint thích hợp (nếu provider hỗ trợ).

Không tuyên bố token cũ đã bị thu hồi chỉ vì một bản ghi JDBC/session được xóa.

## 13. Bảo mật khi đặt interceptor trên RestClient

### 13.1. Chỉ gửi token đến endpoint tin cậy

Một RestClient có OAuth2 interceptor nên được dùng cho **Resource Server phù hợp**. Ví dụ:

~~~java
return builder
    .baseUrl("https://api.example.net")
    .requestInterceptor(oauth2)
    .build();
~~~

Trong gateway/service, nên gọi các đường dẫn tương đối đã kiểm soát như `/v1/reports`. Tuy nhiên **`baseUrl` không tự chặn tuyệt đối mọi absolute URI** được truyền vào `.uri(...)`; code vẫn phải tránh nhận URL tùy ý từ user.

Nếu cho phép user nhập URL để “fetch dữ liệu”, **không dùng cùng RestClient có OAuth2 interceptor** mà không có allowlist host/URI; đó là nguy cơ SSRF và token exfiltration.

### 13.2. Không gắn Bearer Token của mọi request vào mọi hostname

Một `RestClient` có nhiều interceptors được cấu hình bằng builder chung có thể vô tình áp dụng OAuth2 interceptor cho requests không mong muốn. Tránh global registration của interceptor trên một builder dùng cho nhiều mục đích khác nhau khi API hosts khác nhau.

Nên tách bean:

~~~text
publicRestClient
  -> không gắn OAuth2 interceptor

reportsApiRestClient
  -> OAuth2 interceptor cho reports-service

billingApiRestClient
  -> OAuth2 interceptor cho billing-service
~~~

Nếu có nhiều RestClient beans, dùng `@Qualifier` hoặc tên bean rõ ràng để inject đúng client.

### 13.3. Authorization header rất nhạy cảm

Không log:

- `Authorization: Bearer ...`.
- Client Secret, JWT client assertion hoặc private key.
- Access Token, Refresh Token, ID Token.
- Toàn bộ HTTP request/response của token endpoint.
- `OAuth2AuthorizedClient` trong `toString()` hay analytics.

Một metric phù hợp:

~~~text
event=oauth2_resource_call
registration_id=reports-service
resource=reports-api
status=success
http_status=200
correlation_id=internal-trace-2f1a
~~~

Đây là format **minh họa**, không phải log tự động của Spring Security. Correlation ID cần độc lập với token/secret.

### 13.4. HTTPS và TLS validation

Token Endpoint và Resource Server phải được truy cập qua HTTPS với TLS certificate/hostname validation. Không tắt kiểm tra TLS chỉ để “sửa” lỗi giao tiếp. Nếu dùng enterprise proxy hoặc private CA, cấu hình trust store phù hợp.

### 13.5. Audience và scopes

Việc `OAuth2ClientHttpRequestInterceptor` gắn Bearer Token **không kiểm tra thay** Resource Server:

- Resource Server phải xác minh issuer, audience, expiration/signature hoặc introspection.
- Scope được cấp phải đủ cho thao tác API.
- Chính sách tenant/ownership/role có thể cần bổ sung.
- Access Token cho UserInfo không mặc định có audience phù hợp cho Reports API.

Một request API trả 403 có thể hoàn toàn đúng dù interceptor đã hoạt động chính xác.

### 13.6. Không dùng request attribute như một lệnh cấp quyền

`.attributes(clientRegistrationId(...))` và `.attributes(principal(...))` là cấu hình **nội bộ của HTTP client**, nhưng nếu code chuyển thẳng input từ browser sang đó, vẫn có nguy cơ chọn nhầm quyền.

Chọn registration/principal theo **quy tắc server-side**. Không cho user tùy ý đặt `principal("admin")` để lấy token của principal khác trong shared service store.

## 14. Bảng troubleshooting: RestClient không gửi token hoặc API trả lỗi

| Triệu chứng | Khả năng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Outbound request không có Bearer header | Chưa đăng ký interceptor lên đúng RestClient bean | Kiểm tra `.requestInterceptor(oauth2)` và bean được inject |
| Interceptor không tìm được client registration | Không truyền `clientRegistrationId(...)`, sai tên trong YAML | Cung cấp attribute hoặc cấu hình resolver đáng tin |
| Có registration nhưng không có principal | SecurityContext vắng mặt trong background job | Với Client Credentials, cấu hình `RequestAttributePrincipalResolver` và application principal |
| Mỗi HTTP request lại xin Access Token | Principal name thay đổi, store không dùng chung hoặc token TTL quá ngắn | Ổn định registration/principal, kiểm tra manager/service |
| Token Endpoint báo `invalid_client` | Sai secret, client authentication method, token URI hoặc client bị disable | Sửa cấu hình/secret rotation; không retry vô hạn |
| Token Endpoint báo `invalid_scope` | Scope không được cấp cho client | Kiểm tra scope/grant policy, không tự tăng quyền |
| Resource Server trả `401 invalid_token` | Token hết hạn/thu hồi/sai issuer/audience | Kiểm tra token lifecycle, API config, cân nhắc failure handler |
| Resource Server trả `403 insufficient_scope` | Token thiếu scope cần thiết | Đánh giá policy và grant, không bypass quyền |
| 403 do tenant/ownership | Lỗi authorization nghiệp vụ | Sửa resource-level access control |
| Failure handler đã xóa token nhưng request vẫn 401 | Không tự retry cùng outbound call | Quyết định retry có giới hạn tại application layer |
| Interceptor dùng token của sai user | Principal resolver hoặc principal namespace sai | Kiểm tra Authentication và khóa authorized client |
| Job chạy được trong controller nhưng lỗi trong scheduler | Dùng Servlet manager thiếu HTTP context | Dùng service manager và principal application-level |
| Ở local được nhưng sau scale-out mỗi node xin token | In-memory store không chia sẻ | Shared persistence/coordination theo nhu cầu |
| Thêm tracing interceptor thì lộ Access Token | Log request headers | Redact `Authorization` và dữ liệu OAuth2 |
| API call sang URL ngoài dự kiến | URI lấy từ user input, RestClient có token interceptor | Cố định/allowlist destination host; tách client |
| Gọi RestClient thấy 404 | Sai baseUrl/path hoặc API chưa có route | Kiểm tra endpoint; không kết luận OAuth2 lỗi |

### 14.1. Một chuỗi điều tra thực tế

~~~text
RestClient gọi Resource Server thất bại
   |
   +-- Có dùng đúng RestClient bean đã gắn OAuth2 interceptor?
   |
   +-- Request có clientRegistrationId đúng YAML?
   |
   +-- PrincipalResolver lấy đúng user/service identity?
   |
   +-- Manager được cấu hình đúng grant/provider/store?
   |
   +-- Token Endpoint đã cấp token hay trả OAuth2 error?
   |
   +-- Access Token có được gửi cho đúng API/audience?
   |
   +-- API trả 401, 403, 404 hay timeout?
   |
   +-- FailureHandler có được cấu hình, dùng đúng store?
   |
   +-- Có concurrency, expired token, session mất hoặc scale-out?
~~~

Không in token để trả lời các câu hỏi trên. Có thể sử dụng flags như `has_access_token=true`, registration ID đã duyệt và HTTP status, không cần tiết lộ credential.

## 15. Tùy biến interceptor so với viết interceptor thủ công

### 15.1. Vì sao nên ưu tiên OAuth2ClientHttpRequestInterceptor?

Tự viết một `ClientHttpRequestInterceptor` theo kiểu:

~~~java
// PHẢN VÍ DỤ: thiếu quản lý token lifecycle và bảo mật.
(request, body, execution) -> {
    String token = globalTokenCache.get();
    request.getHeaders().setBearerAuth(token);
    return execution.execute(request, body);
};
~~~

Mẫu tự viết này chưa xử lý:

- Đúng registration/principal/tenant.
- Token expiration và Refresh Token.
- Token rotation và cách lưu authorized client.
- Concurrency.
- Token Endpoint error.
- HTTP 401 Bearer error invalidation.
- Bảo mật dữ liệu trong cache/log.

`OAuth2ClientHttpRequestInterceptor` là điểm tích hợp chuẩn cho RestClient; nên dùng nó trừ khi có yêu cầu hạ tầng chưa được framework hỗ trợ.

### 15.2. Khi nào cần custom resolver?

Có thể cần custom `ClientRegistrationIdResolver` hoặc `PrincipalResolver` nếu:

- Mỗi API yêu cầu một registration cụ thể và muốn bỏ việc truyền attributes thủ công.
- Ứng dụng có multi-tenant policy chọn client theo tenant đã xác thực.
- Principal key của service được ánh xạ từ cấu hình nội bộ.
- Không muốn mọi request phụ thuộc current SecurityContext.

Nhưng custom resolver **không phải** chỗ đọc user-supplied URL rồi quyết định token có quyền cao nhất. Phải kiểm soát nguồn dữ liệu và mapping.

### 15.3. Nhiều interceptors trên một RestClient

`RestClient` có thể có tracing, retry, metric và OAuth2 interceptor. Thứ tự và phạm vi interceptors cần được cân nhắc:

~~~text
RestClient
  -> Tracing/metrics (không log credential)
  -> OAuth2 token interceptor
  -> HTTP transport
~~~

Nếu interceptor logging được đặt sau khi OAuth2 gắn header, **phải redact Authorization**. Không dựa vào thứ tự để đảm bảo secret không bao giờ bị ghi log; cả logging và error handlers cần có chính sách che dữ liệu.

Retry toàn request có thể khiến interceptor được gọi lại; đảm bảo retry policy không gây double-write cho POST/PATCH/DELETE và không tạo storm cấp token.

## 16. RestClient khác WebClient và RestTemplate thế nào?

| HTTP client | Kiểu lập trình | OAuth2 integration thường dùng |
| --- | --- | --- |
| `RestClient` | Đồng bộ, fluent API trên Spring MVC/Servlet-friendly code | **`OAuth2ClientHttpRequestInterceptor`** |
| `WebClient` | Reactive API, cũng có thể dùng từ Servlet app | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| `RestTemplate` | Đồng bộ, API truyền thống | Có thể tự cấu hình bearer/interceptor hoặc dùng công cụ tương thích; không phải RestClient API |

Không dùng:

~~~java
// Không phù hợp: WebClient filter function không phải RestClient interceptor.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

như một `ClientHttpRequestInterceptor` cho RestClient. Hai loại HTTP client dùng contract khác nhau.

Nếu dự án đã dùng `WebClient`, việc chuyển sang RestClient cần cân nhắc mô hình blocking, request context, retry và thread usage. Chỉ vì cả hai đều có OAuth2AuthorizedClientManager không có nghĩa có thể copy toàn bộ cấu hình 1:1.

### 16.1. Spring Security trước 6.4

Nếu ứng dụng chưa có class `OAuth2ClientHttpRequestInterceptor`:

- Kiểm tra phiên bản Spring Security thật sự được BOM quản lý.
- Có thể nâng phiên bản theo một kế hoạch tương thích.
- Nếu chưa nâng, sử dụng integration được hỗ trợ ở phiên bản hiện tại, ví dụ WebClient Servlet integration hoặc code HTTP đã được thiết kế phù hợp.
- Không sao chép source của một class Spring Security mới vào package dự án để “giả” API tương thích.

## 17. HTTP Service Clients sử dụng RestClient đã cấu hình

Với Spring Framework HTTP Interface (`@HttpExchange`), có thể xây client proxy trên một `RestClient` đã chứa OAuth2 interceptor.

Ví dụ interface:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/v1/reports")
public interface ReportsHttpApi {

    @GetMapping
    String listReports();
}
~~~

Nếu tạo proxy bằng `HttpServiceProxyFactory` và `RestClientAdapter` từ RestClient đã cấu hình, outbound HTTP vẫn đi qua interceptors của RestClient đó.

Tuy nhiên, **cách truyền request attributes `clientRegistrationId(...)`/`principal(...)` từ HTTP interface** cần được thiết kế rõ. Nếu proxy không có cách thiết lập attributes cho từng call, có thể dùng RestClient chuyên dụng với resolver cố định theo chính sách hoặc một tầng adapter được kiểm soát.

Không giả định mọi proxy method tự chọn đúng OAuth2 client registration chỉ vì RestClient đã gắn interceptor.

## 18. Kiểm thử việc liên kết interceptor với manager

Khi tự kiểm thử tích hợp, nên tách ba lớp:

1. **Unit test mapping:** resolver nhận đúng registration ID và principal cho request.
2. **HTTP client test:** một RestClient đã gắn interceptor đặt `Authorization: Bearer ...` khi manager trả authorized client hợp lệ.
3. **Authorization integration test:** Token Endpoint giả lập/trust configuration kiểm tra manager thực sự xin hoặc refresh token theo grant.

**Không dùng unit test có Access Token giả để kết luận OIDC ID Token validation hoặc Token Endpoint client authentication đã đúng.** Đây là những lớp khác nhau.

### 18.1. Các kịch bản nên có

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Client Credentials, registration và principal đúng | Interceptor lấy authorized client và gắn Bearer header |
| Request thiếu `clientRegistrationId` | Không lấy nhầm default client quyền cao |
| Principal application-level cố định | Lần gọi sau có thể tải authorized client cùng khóa |
| Principal khác | Không trả nhầm token của principal cũ |
| Access Token còn hạn | Có thể tái sử dụng authorized client |
| Access Token hết hạn | Manager cấp/refresh lại nếu grant và policy phù hợp |
| Token Endpoint trả `invalid_client` | Request API không thực hiện bằng token giả |
| Token Endpoint trả `invalid_scope` | Không tự nâng scope |
| Resource Server trả `401 invalid_token` | Failure handler xử lý token lỗi theo policy; không retry vô hạn |
| Resource Server trả `403 insufficient_scope` | Không tự xin scope admin |
| API trả 404 | Không xóa mọi token nếu OAuth2 error không chỉ ra token không hợp lệ |
| Gọi sang host không thuộc allowlist | Không gắn token, request bị chặn theo policy |
| Background job không có SecurityContext | Service principal resolver vẫn hoạt động đúng |
| Có hai client registrations | Token của Reports không bị gửi sang Billing |
| Hai instance dùng chung authorized client | Hoạt động theo storage/coordination thiết kế |
| Logging bật ở RestClient | `Authorization` header không xuất hiện trong logs |

### 18.2. Mock HTTP client và manager

Với Spring Framework, `MockRestServiceServer` có thể dùng để kiểm thử request được tạo bởi RestClient; với Spring Security, có thể đưa một manager test double trả `OAuth2AuthorizedClient` có Access Token **giả**.

Sơ đồ test:

~~~text
RestClient request
  -> OAuth2ClientHttpRequestInterceptor(testManager)
  -> HTTP Mock Server
       assert request path = /v1/reports
       assert Authorization header = Bearer TEST_ONLY_TOKEN
       return JSON giả
~~~

Một test riêng cần bảo đảm manager không dùng token sai registration/principal. Test này khác với integration test thật gọi Authorization Server.

Với các trường hợp OAuth2 error, mock Token Endpoint/Resource Server trả đúng HTTP status và OAuth2 error body theo contract; kiểm tra handler có phân loại đúng lỗi và không xóa token khi lỗi không tương ứng.

### 18.3. Kiểm thử ở runtime Servlet

Đối với delegated user token, test nên chứng minh:

- SecurityContext gắn đúng Authentication đã đăng nhập.
- Registration `company-login` được chọn đúng.
- Outbound API nhận Access Token **dành cho API đó**.
- Không lộ Access Token qua response của controller.
- User B không dùng authorized client của User A.
- Đăng xuất hoặc session hết hạn ảnh hưởng đến token store theo chính sách thực tế.

Nếu test chỉ mock `@AuthenticationPrincipal` rồi không đi qua interceptor và manager, nó chưa kiểm chứng tích hợp OAuth2 RestClient.

## 19. Tình huống thực tế

### Tình huống A — Service có Client Credentials nhưng interceptor không tìm được principal

Scheduled job dùng RestClient; code có `clientRegistrationId("reports-service")` nhưng interceptor mặc định tìm principal từ `SecurityContextHolder` đang rỗng.

**Giải pháp:** dùng service manager cùng `RequestAttributePrincipalResolver`, truyền `principal("system-report-exporter")`. Không tạo Authentication của một user giả để vượt qua thiếu context.

### Tình huống B — Cùng một RestClient gọi hai APIs

Code gọi Reports và Billing nhưng vô tình dùng `reports-service` cho cả hai.

**Giải pháp:** tách RestClient/registrations theo API boundary hoặc luôn đặt request attribute đúng bằng mapping server-side, không để caller tùy ý chọn registration có quyền cao.

### Tình huống C — Một user đăng nhập OIDC muốn xem báo cáo của mình

Ứng dụng có `company-login` và Access Token được cấp cho delegated API.

**Giải pháp:** dùng interceptor với principal mặc định từ SecurityContext, chọn `company-login`. Không dùng application-wide token `reports-service` thay user token nếu API yêu cầu user context.

### Tình huống D — RestClient gọi Token Endpoint nhiều lần

Mỗi lần `GET /reports` manager lại xin Client Credentials Access Token.

**Cách điều tra:** principal name có thay đổi không? Manager và service có đúng backing store không? Access Token TTL có đủ dài? Có nhiều pods dùng in-memory service riêng không? Không kết luận interceptor “không cache” khi vấn đề nằm ở authorized client storage.

### Tình huống E — Resource Server trả 401 dù token chưa hết hạn

API từ chối token vì issuer/audience sai hoặc token bị revoke trước hạn.

**Giải pháp:** kiểm tra Resource Server policy, registration và target audience. Có thể cấu hình authorization failure handler để xóa invalid token theo error code. Không giả định đổi Refresh Token là cách giải quyết sai audience.

### Tình huống F — Resource Server trả 403 insufficient_scope

Client có token `reports.read` nhưng gọi API cập nhật cần `reports.write`.

**Giải pháp:** không retry bằng cách tự nâng scope; phải chỉnh policy/registration qua quy trình phê duyệt nếu tính năng thật sự cần quyền ghi.

### Tình huống G — Thêm interceptor logging để debug

HTTP tracing ghi cả request headers, bao gồm Bearer Token do OAuth2 interceptor gắn.

**Giải pháp:** redact `Authorization` và token request credentials ở mọi lớp logging/observability. Không chỉ thay thứ tự interceptor để hy vọng token không bị log.

### Tình huống H — Một endpoint nhận URL tùy ý từ user

Backend gọi `restClient.get().uri(userUrl)` bằng một RestClient đã gắn OAuth2 interceptor.

**Giải pháp:** chặn URL không thuộc allowlist, tách HTTP client dành cho public fetch khỏi client có credentials. Không gửi Bearer token đến destination do browser chọn.

### Tình huống I — Worker ngoài HTTP request dùng DefaultOAuth2AuthorizedClientManager

Token manager được cấu hình bằng repository Servlet và worker không có request/response.

**Giải pháp:** dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientService`. Với Client Credentials, truyền principal app-level ổn định.

### Tình huống J — Interceptor failure handler không giải quyết ngay request 401

Resource Server trả 401; authorized client bị xóa theo chính sách nhưng REST call vẫn ném exception.

**Giải pháp:** hiểu rằng invalidation chủ yếu ảnh hưởng lần gọi tiếp theo. Nếu retry là yêu cầu nghiệp vụ, triển khai policy retry giới hạn, idempotency và phản hồi lỗi rõ ràng.

## 20. Những sai lầm phổ biến

### 20.1. Tự hard-code Bearer Token vào RestClient bean

Một Access Token có vòng đời hạn chế. Đưa token vào `defaultHeader("Authorization", ...)` khi tạo bean khiến token cũ có thể được tái sử dụng mãi và bị dùng cho sai principal.

### 20.2. Nhầm `clientRegistrationId` với `principal`

Registration xác định cấu hình client/provider; principal xác định authorized client thuộc ai. Hai giá trị khác nhau và đều cần thiết để chọn token đúng.

### 20.3. Dùng Client Credentials thay Authorization Code của user

Client Credentials cấp token cho service; không tự đại diện cho user. Một backend có token service quyền rộng phải tự thực thi user authorization nếu truy cập thay user theo kiến trúc đã phê duyệt.

### 20.4. Không xử lý stale token trong Resource Server response

Token còn hạn ở client vẫn có thể bị API từ chối. Cần phân biệt invalid token với insufficient scope và policy nghiệp vụ.

### 20.5. Xóa mọi token khi gặp một HTTP 403

403 có thể do tenant hoặc quyền dữ liệu. Không xóa authorized client của mọi user/registrations vì một API call không đủ quyền.

### 20.6. Gắn interceptor cho RestClient dùng mọi mục đích

Một Bean RestClient có OAuth2 interceptor rồi gọi bất kỳ hostname/URI có thể làm lộ Access Token. Tách client theo API host và cố định/allowlist destination.

### 20.7. Dùng service manager nhưng principal lấy từ browser

Nếu code cho user tự chỉ định principal name của service, có thể đọc/ghi nhầm authorized client trong shared store. Principal phải đến từ server-side policy.

### 20.8. Giả định interceptor tự cung cấp ID Token

Interceptor gắn **Access Token** để gọi API. ID Token của OIDC Login dùng để xác thực user tại client, không phải Bearer Token dành cho API.

### 20.9. Không thống nhất storage và failure handler

Manager lưu vào JDBC service A nhưng failure handler xóa ở session/repository B khiến token lỗi vẫn tồn tại trong A. Cần dùng đúng backing store và principal key.

### 20.10. Coi authorization success handler là HTTP request logger

Manager có thể sử dụng lại token mà không tạo token mới. Không nên dùng số lần cấp token thành công để đo số lần API được gọi; quan sát HTTP traffic ở client layer.

## 21. Checklist thiết kế trước khi dùng production

| Câu hỏi | Quyết định cần rõ |
| --- | --- |
| Đang dùng Spring Security version nào? | Có hỗ trợ `OAuth2ClientHttpRequestInterceptor` (6.4+) |
| RestClient này gọi API nào? | Host/path được kiểm soát, TLS hợp lệ |
| Registration được chọn thế nào? | Request attribute hoặc resolver có allowlist |
| Token thuộc user hay service? | PrincipalResolver phù hợp, không nhầm delegated/application identity |
| Manager nào được dùng? | DefaultServlet manager hay AuthorizedClientService manager |
| Authorized client lưu ở đâu? | Repository/service cùng backing store, TTL/persistence phù hợp |
| Grant nào được phép? | Authorization Code/Refresh Token hoặc Client Credentials đúng nhu cầu |
| Scope/audience đủ cho API? | Provider cấp đúng; Resource Server xác minh |
| HTTP 401/403 xử lý thế nào? | Có failure handler thích hợp, retry có giới hạn |
| Có multi-instance/concurrency không? | Storage coordination, token rotation policy |
| Có log Bearer token không? | Redact credential ở logging, tracing, APM |
| URL API có bị user điều khiển không? | Chặn SSRF, cố định/allowlist destination |
| Có yêu cầu logout/disconnect/revocation? | Phân biệt xóa local token và revoke ở provider |
| Có test đúng manager/interceptor không? | Test principal/registration, Bearer header, API 401/403, Token Endpoint lỗi |

## 22. Tài liệu tham khảo

- Spring Security — OAuth 2.0 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Client Features, RestClient Integration: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2ClientHttpRequestInterceptor Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Framework — RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 23. Kết luận: interceptor và manager phối hợp, mỗi tầng giữ một trách nhiệm

~~~text
RestClient outbound request
  |
  +-- .attributes(clientRegistrationId("reports-service"))
  +-- .attributes(principal("system-report-exporter"))
  |
  v
OAuth2ClientHttpRequestInterceptor
  |
  +-- ClientRegistrationIdResolver -> chọn registration
  +-- PrincipalResolver -> chọn principal
  |
  v
OAuth2AuthorizedClientManager
  |
  +-- Load authorized client từ store
  +-- Cấp/refresh token qua grant phù hợp khi cần
  +-- Lưu authorized client mới
  |
  v
Interceptor gắn Authorization: Bearer <access_token>
  |
  v
Resource Server xác minh token + scope + audience + policy
  |
  +-- 2xx -> xử lý response
  +-- 401/403 -> failure handling theo OAuth2 error code
  +-- timeout/5xx -> chính sách retry/circuit breaker
~~~

**Ba ý quan trọng nhất:**

1. **`OAuth2ClientHttpRequestInterceptor` là cầu nối giữa RestClient và `OAuth2AuthorizedClientManager`**, giúp gắn Bearer Access Token mà không tự viết logic token ở từng controller.
2. **`clientRegistrationId` và `principal` quyết định token được chọn.** Với user delegated flow, principal thường đến từ SecurityContext; với Client Credentials, nên dùng principal application-level được kiểm soát.
3. **Interceptor không thay Resource Server authorization hay chính sách bảo mật API.** Phải bảo vệ Access Token khỏi logging/SSRF, dùng đúng audience/scope, xử lý HTTP 401/403 theo error code và không retry/nâng quyền tùy tiện.

Khi cấu hình đúng manager, store và resolver, ứng dụng Servlet có thể sử dụng RestClient nhất quán cho cả API theo user lẫn API machine-to-machine, đồng thời giữ tách biệt trách nhiệm **xác thực OIDC**, **ủy quyền OAuth2**, **vòng đời authorized client** và **gửi HTTP request an toàn**.
