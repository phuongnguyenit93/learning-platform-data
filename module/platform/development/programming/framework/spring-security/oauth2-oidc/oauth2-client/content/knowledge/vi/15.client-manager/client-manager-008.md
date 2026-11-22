# 15.8. Authorization success handler và lưu authorized client

## 1. Đặt vấn đề: được cấp token thành công rồi ai lưu lại?

Trong một ứng dụng **Spring Security OAuth 2.0 OIDC Client**, sau khi người dùng đăng nhập hoặc một backend service xin Access Token, ứng dụng thường cần **sử dụng lại token** ở những lần gọi API tiếp theo. Nếu token gần hết hạn, client có thể cần dùng Refresh Token hoặc một grant khác để xin token mới và cập nhật bản ghi đã lưu.

Spring Security giải quyết nhu cầu này bằng ba nhóm thành phần:

- **`OAuth2AuthorizedClient`**: đại diện cho một client registration đã được ủy quyền đối với một principal, chứa Access Token và có thể có Refresh Token.
- **`OAuth2AuthorizedClientManager`**: điều phối việc tìm authorized client cũ, thực hiện grant thích hợp và xử lý kết quả cấp quyền.
- **`OAuth2AuthorizationSuccessHandler`**: callback được client manager gọi **sau khi provider đã thực hiện một lần authorization thành công**, thường để **lưu/cập nhật** `OAuth2AuthorizedClient` mới vào repository hoặc service.

Ví dụ, một hệ thống báo cáo sử dụng `client_credentials` gọi API nội bộ. Lần đầu manager xin token và lưu nó. Những lần tiếp theo có thể dùng lại token đã lưu; khi token hết hạn, manager xin token mới rồi cập nhật bản ghi. Nếu thay success handler mặc định bằng một handler chỉ ghi log, ứng dụng có thể vô tình **ngừng lưu token mới** và liên tục xin lại token.

> **Mục tiêu bài học:** phân biệt authorization success handler với login success handler, hiểu đường đi của authorized client qua manager, cấu hình cơ chế lưu mặc định và tùy biến đúng cách mà không làm mất persistence hoặc lộ token.

## 2. Hai “success handler” có tên gần giống nhưng trách nhiệm khác nhau

Đây là chỗ rất dễ nhầm khi làm việc với OAuth2 Login và OAuth2 Client:

| Tiêu chí | `OAuth2AuthorizationSuccessHandler` | `AuthenticationSuccessHandler` |
| --- | --- | --- |
| Ngữ cảnh | **OAuth2AuthorizedClientManager** thực hiện authorization/re-authorization | **Spring Security authentication filter**, ví dụ OAuth2 Login |
| Được gọi khi | `OAuth2AuthorizedClientProvider` trả về authorized client mới từ một lần cấp quyền thành công | Người dùng được xác thực thành công trong luồng login |
| Tham số trọng tâm | `OAuth2AuthorizedClient`, `Authentication`, `Map<String,Object> attributes` | `HttpServletRequest`, `HttpServletResponse`, `Authentication` |
| Mục tiêu mặc định thường gặp | Lưu/cập nhật authorized client vào kho | Điều hướng browser, chẳng hạn trở về saved request |
| Tác dụng lên HTTP response | Không nhất thiết có response; service manager có thể chạy ngoài Servlet | Thường quyết định redirect/HTTP response cho browser |
| Có thể dùng trong scheduled job? | Có, qua client manager/service phù hợp | Không phải lựa chọn cho background token authorization |
| Điểm cấu hình | `manager.setAuthorizationSuccessHandler(...)` | `http.oauth2Login(...).successHandler(...)` |

**`OAuth2AuthorizationSuccessHandler` không phải một HTTP login success handler.** Ngược lại, khi người dùng đăng nhập OIDC thành công và browser được redirect về trang chủ, việc redirect đó không tự chứng minh rằng custom authorization success handler của manager đã chạy.

### 2.1. Tên giao diện và package

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
~~~

Một application có thể dùng **cả hai**:

~~~text
OAuth2/OIDC Login thành công
  -> Spring Security tạo Authentication
  -> OAuth2 Login lưu authorized client theo luồng login
  -> AuthenticationSuccessHandler quyết định nơi browser đi tiếp

OAuth2AuthorizedClientManager cần xin/refresh Access Token
  -> OAuth2AuthorizedClientProvider thực hiện grant thành công
  -> OAuth2AuthorizationSuccessHandler lưu/cập nhật authorized client
  -> manager trả về OAuth2AuthorizedClient cho code gọi API
~~~

Không nên cấu hình `oauth2Login().successHandler(...)` với mục đích duy nhất là “lưu Refresh Token mỗi khi manager refresh”. Handler HTTP login không được gọi trong mọi lần refresh.

## 3. Authorized client chứa dữ liệu gì?

Một `OAuth2AuthorizedClient` có các thành phần chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `ClientRegistration` | Cấu hình OAuth2/OIDC client và provider, có `registrationId` |
| `principalName` | Danh tính logic dùng để liên kết bản ghi ủy quyền |
| `OAuth2AccessToken` | Token hiện tại, loại token, scopes và thời điểm phát hành/hết hạn |
| `OAuth2RefreshToken` | Refresh Token nếu được cấp và client cần lưu |

Ví dụ diễn giải:

~~~text
OAuth2AuthorizedClient
  clientRegistration.registrationId = "calendar"
  principalName = "employee-123"
  accessToken = <sensitive credential>
  refreshToken = <sensitive credential, optional>
~~~

**Bản ghi authorized client không phải ID Token của OIDC.** ID Token phục vụ xác thực danh tính OIDC; Access Token/Refresh Token phục vụ việc gọi tài nguyên và lấy token mới. Không gửi ID Token thay Access Token đến API.

### 3.1. Registration ID khác principal name

Một registration `calendar` có thể có authorized client của nhiều người:

~~~text
("calendar", "employee-123") -> token của employee-123
("calendar", "employee-456") -> token của employee-456
~~~

Không bao giờ dùng **registration ID làm khóa duy nhất** cho mọi người dùng. Với OIDC, danh tính bền vững dựa trên **issuer + subject**; trong hệ thống nhiều issuer/tenant cần thiết kế principal namespace phù hợp để tránh trùng khóa.

Với `client_credentials`, principal name thường là một định danh service cố định như `system-reports`, không có end-user. Không tự gắn token Client Credentials vào tài khoản người dùng đang đăng nhập.

### 3.2. Dữ liệu nào được cập nhật sau refresh?

Khi refresh thành công:

- Access Token có thể được thay bằng giá trị mới, hạn dùng mới và các scopes được cấp.
- Refresh Token có thể được **xoay vòng** (provider trả token mới), hoặc không được thay thế tùy grant/response.
- Bản ghi mới cần được lưu dưới **đúng registration và principal**.

Không sửa raw token bằng thao tác chuỗi hoặc ghi Access Token từ browser vào kho. Authorized client mới phải là kết quả của flow OAuth2 hợp lệ qua provider/client đã tin cậy.

## 4. Authorization success handler được gọi trong lúc nào?

### 4.1. Luồng điều phối qua OAuth2AuthorizedClientManager

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Code gọi API
    participant M as OAuth2AuthorizedClientManager
    participant S as Authorized Client Store
    participant P as OAuth2AuthorizedClientProvider
    participant AS as Authorization Server
    participant H as OAuth2AuthorizationSuccessHandler
    App->>M: authorize(registrationId, principal)
    M->>S: load existing authorized client
    S-->>M: Client cũ hoặc null
    M->>P: authorize(context, existing client)
    alt Provider cần cấp/refresh và thành công
        P->>AS: Grant request tới Token Endpoint
        AS-->>P: Token response thành công
        P-->>M: OAuth2AuthorizedClient mới
        M->>H: onAuthorizationSuccess(client, principal, attributes)
        H->>S: save/update authorized client
        S-->>H: Lưu hoàn tất
        M-->>App: Authorized client mới
    else Không cần re-authorize
        P-->>M: Không tạo authorized client mới
        M-->>App: Client cũ, nếu có
        Note over H: Success handler thường không được gọi
    end
~~~

Đây là **mô hình logic**. Cơ chế fallback, giải quyết HTTP request context và hành vi khi chưa thể authorize phụ thuộc loại manager/provider và grant thực tế.

Một điểm cực kỳ quan trọng: **success handler không bắt buộc chạy trên mọi lần gọi `manager.authorize(...)`**. Nếu Access Token đang được sử dụng lại và provider không thực hiện re-authorization, manager có thể trả authorized client hiện có mà không gọi handler.

Đó là lý do không nên dùng success handler để thống kê **mọi lần API sử dụng token**. Handler phù hợp hơn để quan sát **sự kiện cấp/cập nhật token thành công**.

### 4.2. Giao diện OAuth2AuthorizationSuccessHandler

Giao diện có một phương thức:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

void onAuthorizationSuccess(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    Map<String, Object> attributes
);
~~~

Trong đó:

- `authorizedClient`: đối tượng vừa được provider/manager cấp quyền thành công.
- `principal`: authentication/principal context dùng để xác định sở hữu bản ghi.
- `attributes`: metadata ngữ cảnh của authorization do manager truyền vào; có thể bao gồm dữ liệu Servlet ở manager tương ứng.

**Map `attributes` không phải nơi dành cho dữ liệu tùy ý do người dùng điều khiển.** Không lấy tên principal hoặc redirect target từ query parameter chưa được xác minh để lưu token vào một account khác.

### 4.3. Authorization success khác OAuth2 Login success

Trong OAuth2 Login, `OAuth2LoginAuthenticationFilter` và repository được tích hợp để xử lý callback đăng nhập; lưu authorized client nằm trong luồng login do Spring Security quản lý. Một lần login thành công có thể đã lưu Access Token trước khi `AuthenticationSuccessHandler` điều hướng browser.

Sau đó khi code ứng dụng gọi `OAuth2AuthorizedClientManager.authorize(...)` để refresh token, đó là **một vòng đời token mới**. Khi cấp/refresh thành công, manager gọi `OAuth2AuthorizationSuccessHandler` của nó.

Không nên bắt buộc tự gọi `saveAuthorizedClient` ở cả login success handler, controller, manager success handler và client API nếu không có thiết kế rõ ràng; rất dễ ghi đè token mới bằng token cũ hoặc lưu dưới principal không khớp.

## 5. Hai manager phổ biến và success handler mặc định

Spring Security cung cấp hai manager thông dụng cho những ngữ cảnh khác nhau.

| Thành phần | Bối cảnh | Kho lưu trữ | Hành vi success mặc định |
| --- | --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | Bên trong Servlet HTTP request | `OAuth2AuthorizedClientRepository` | **Lưu authorized client** thông qua repository đã được cung cấp |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Ngoài Servlet request, ví dụ service/job | `OAuth2AuthorizedClientService` | **Lưu authorized client** thông qua service đã được cung cấp |

**Vì handler mặc định đã thực hiện lưu token, đa số ứng dụng không cần tự viết authorization success handler.** Nếu không có nhu cầu audit hoặc logic tích hợp đặc biệt, giữ mặc định thường là lựa chọn an toàn và đơn giản.

### 5.1. DefaultOAuth2AuthorizedClientManager

Constructor của manager dành cho Servlet nhận:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository
    );
~~~

Các biến trên là những dependency do ứng dụng/Spring Boot cung cấp. Manager dùng repository để load trạng thái hiện có và mặc định dùng authorization success handler để **save** kết quả khi authorization provider tạo client mới.

### 5.2. AuthorizedClientServiceOAuth2AuthorizedClientManager

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService
    );
~~~

Manager này làm việc với service, không yêu cầu `HttpServletRequest`/`HttpServletResponse`. Vì vậy nó phù hợp cho Client Credentials, scheduled tasks hoặc những workflow backend có principal context phù hợp.

### 5.3. Repository và service khác nhau ở điểm nào?

| API | Chữ ký khái niệm | Phù hợp |
| --- | --- | --- |
| `OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)` | Authorized client + Authentication + Servlet request/response | Tích hợp web, session và repository có ngữ cảnh browser |
| `OAuth2AuthorizedClientService.saveAuthorizedClient(...)` | Authorized client + principal name | Lưu ngoài Servlet request, memory hoặc JDBC |

Repository có thể được triển khai dưới dạng adapter delegate xuống service cho principal đã xác thực; ví dụ `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`. Vì vậy không nên suy luận rằng “repository thì chỉ lưu session” hoặc “service thì luôn dùng database”.

## 6. Cấu hình mẫu cho Servlet OAuth2/OIDC Client

### 6.1. Dependency

Với Spring Boot 3.x dùng Servlet/MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Trong Spring Boot 4.x, tên starter được modular hóa tương ứng như `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Chọn đúng dependency theo Spring Boot BOM; không trộn Spring Security version chỉ vì một ví dụ dùng API khác.

### 6.2. Cấu hình registration OIDC

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

Các URL/client IDs chỉ minh họa. Trong ứng dụng thật, issuer và redirect URI phải trùng thông tin OP đã đăng ký; bí mật lấy từ secret manager/biến môi trường, không commit vào repository.

### 6.3. Bật OAuth2 Login và OAuth2 Client

~~~java
package com.example.security;

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

Với configuration thông thường, Spring Security đã tích hợp lưu authorized client sau OAuth2 Login. Không cần viết `AuthenticationSuccessHandler` chỉ để chép Access Token vào HTTP session.

`oauth2Client()` giúp ứng dụng tích hợp cơ chế OAuth2 Client trong Servlet. Muốn refresh token hoặc xin token với grant riêng, hãy cấu hình AuthorizedClientManager và AuthorizedClientProvider đúng cách.

## 7. Ví dụ 1: manager mặc định tự lưu authorized client trong Servlet

Đây là ví dụ **cấu hình tường minh**, hữu ích khi muốn kiểm soát grant types. Không cài custom success handler vì mặc định của manager đã có hành vi lưu.

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class ServletClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        // KHÔNG gọi setAuthorizationSuccessHandler ở đây:
        // mặc định manager lưu authorized client qua repository.
        return manager;
    }
}
~~~

Khi manager thực hiện refresh thành công, authorized client mới được lưu vào repository phù hợp với Authentication và Servlet context của lời gọi. Nếu chỉ muốn dùng cơ chế mặc định của Spring Security, cũng không cần định nghĩa bean manager này trừ khi ứng dụng muốn chủ động cấu hình các provider/grants.

**Đừng bật `clientCredentials()` trong manager web chỉ vì “có token mới”**. Grant đó dành cho client/service, không phải đăng nhập người dùng. Chỉ bật nếu ứng dụng thực sự có client registrations cần Client Credentials và đã thiết kế identity namespace riêng.

### 7.1. Gọi manager từ service trong Servlet request

Ví dụ đoạn code sử dụng manager:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(request);

if (authorizedClient == null) {
    // Không có authorized client phù hợp trong ngữ cảnh hiện tại.
    // Không gọi API khi chưa có Access Token hợp lệ.
}
~~~

Biến `authentication` và `authorizedClientManager` được giả định đã inject hoặc lấy từ server-side context, không tạo từ tham số tự do của browser.

Với `DefaultOAuth2AuthorizedClientManager`, lời gọi cần **Servlet request/response context** phù hợp (hoặc attributes đã được thiết lập đúng) để repository có thể hoạt động. Đây không phải manager dành cho một scheduled job chạy không có HTTP request.

### 7.2. Đọc kết quả sau khi manager authorize

~~~java
if (authorizedClient != null) {
    String registrationId = authorizedClient.getClientRegistration()
        .getRegistrationId();
    boolean hasRefreshToken = authorizedClient.getRefreshToken() != null;
    // Chỉ dùng token ở backend để gọi API được phép.
    // Không log/getTokenValue() ra trình duyệt.
}
~~~

Không nên hiển thị giá trị token, Refresh Token hoặc toàn bộ `OAuth2AuthorizedClient` trong HTML, JSON response hay application logs.

## 8. Ví dụ 2: manager dùng service cho tác vụ không có Servlet request

Giả sử worker backend cần gọi API báo cáo bằng **Client Credentials**. Không có browser, không có HTTP login và không có người dùng cuối.

Cấu hình OAuth2 client registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-provider
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reporting-provider:
            token-uri: https://auth.example.net/oauth2/token
~~~

Tạo `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

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
public class ServiceClientManagerConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            reportingClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        // Thành công: manager mặc định save qua service.
        return manager;
    }
}
~~~

Đối với Client Credentials, manager có thể lấy Access Token và lưu nó theo principal key do application cung cấp. Lần sau manager có thể tải lại token còn phù hợp thay vì luôn xin token mới.

Ví dụ gọi:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reporting-service")
        .principal("system-reporting-job")
        .build();

OAuth2AuthorizedClient client = reportingClientManager.authorize(request);
if (client == null) {
    throw new IllegalStateException("Chưa thể cấp token cho reporting-service");
}

// API client sử dụng client.getAccessToken() ở backend.
~~~

Đoạn này minh họa mô hình sử dụng, với biến `reportingClientManager` được dependency-inject ở class gọi. Định danh `system-reporting-job` là **principal name trong kho token của service**, không phải tài khoản người dùng OIDC.

**Không dùng `AuthenticationSuccessHandler`** cho Client Credentials: không có browser login để redirect.

## 9. Khi nào cần tự định nghĩa OAuth2AuthorizationSuccessHandler?

Giữ handler mặc định là đủ cho nhu cầu lưu/cập nhật token thông thường. Custom success handler phù hợp khi application muốn bổ sung một hoặc nhiều tác vụ **sau khi authorization thành công**:

1. Ghi một audit event **không chứa token**.
2. Cập nhật metadata nghiệp vụ như trạng thái “connected” cho đúng registration/principal.
3. Đo số lần token được cấp lại, không nhầm với số lần API sử dụng token.
4. Lưu vào một kho được thiết kế riêng hoặc kiểm soát persistence/transaction.
5. Thực hiện một hook có kiểm soát cho service integration sau khi token mới đã được lưu.

**Nguy cơ lớn nhất:** `setAuthorizationSuccessHandler(...)` thường **thay thế** success handler mặc định. Nếu custom handler chỉ ghi log và không lưu authorized client, lần cấp quyền mới có thể không được persist.

### 9.1. Ví dụ không nên làm

~~~java
// PHẢN VÍ DỤ: thay handler lưu mặc định bằng handler chỉ log.
manager.setAuthorizationSuccessHandler(
    (authorizedClient, principal, attributes) -> {
        System.out.println("OAuth2 authorization succeeded");
        // Không lưu authorized client!
    });
~~~

Hậu quả:

- Access Token mới chỉ tồn tại trong kết quả của lần `authorize()` hiện tại.
- Lần request tiếp theo có thể tải lại token cũ/hết hạn, hoặc không có bản ghi.
- Với token rotation, Refresh Token mới không được lưu, khiến lần refresh sau thất bại.
- Hệ thống có thể liên tục xin Access Token mới, tạo tải không cần thiết cho Token Endpoint.

Nếu thay handler, **hãy duy trì trách nhiệm lưu trữ** hoặc delegate rõ ràng tới một handler có thực hiện lưu.

### 9.2. Mẫu custom handler cho service manager: lưu trước, audit sau

Với manager dùng `OAuth2AuthorizedClientService`, có thể viết handler rõ ràng và không cần Servlet context:

~~~java
package com.example.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuditedServiceClientManagerConfig {

    private static final Logger log =
        LoggerFactory.getLogger(AuditedServiceClientManagerConfig.class);

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            auditedServiceClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .build();
        manager.setAuthorizedClientProvider(provider);

        OAuth2AuthorizationSuccessHandler persistThenAudit =
            (authorizedClient, principal, attributes) -> {
                // Không bỏ bước persistence khi thay success handler.
                service.saveAuthorizedClient(
                    authorizedClient, principal.getName());

                // Chỉ log metadata không nhạy cảm.
                log.info(
                    "OAuth2 authorized client saved; registrationId={}",
                    authorizedClient.getClientRegistration().getRegistrationId()
                );
            };

        manager.setAuthorizationSuccessHandler(persistThenAudit);
        return manager;
    }
}
~~~

Ở đây:

- `service.saveAuthorizedClient(...)` ghi authorized client mới dưới đúng principal key.
- `log.info(...)` **không ghi** Access Token, Refresh Token, email, subject, HTTP response hoặc toàn bộ object client.
- Handler được gắn vào **service manager**; không cần đọc Servlet request/response từ `attributes`.
- Những lần không có cấp/refresh token mới có thể không đi qua handler, nên đây là log **cấp token thành công**, không phải log tất cả API calls.

Các `@Bean` ví dụ ở các phần trước là **những cấu hình thay thế**. Không copy tất cả manager beans cùng một loại vào ứng dụng rồi kỳ vọng Spring Boot tự chọn đúng bean. Nếu triển khai nhiều manager, đặt tên và `@Qualifier` hoặc inject đúng loại/bean cho từng workflow.

### 9.3. Thứ tự lưu và audit

Một thứ tự hợp lý trong ví dụ:

~~~text
Provider cấp token mới thành công
  -> validate/build OAuth2AuthorizedClient
  -> service.saveAuthorizedClient(...)
  -> audit metadata an toàn
  -> manager trả authorized client
~~~

Nếu **save thất bại**, code không nên phát sự kiện “persisted successfully”. Nếu **audit thất bại sau khi save**, cần quyết định chính sách rõ ràng:

- Với audit tùy chọn: có thể tách sang hệ thống quan sát có retry/buffering để không phá luồng cấp token.
- Với audit bắt buộc cho tuân thủ: thiết kế transactional outbox hoặc cơ chế consistency phù hợp; không giả định save token và gửi một network audit event là transaction nguyên tử.
- Không để lỗi logging vô tình khiến client manager retry nhiều lần và tạo thêm token không cần thiết.

Một handler custom không tự đảm bảo atomicity giữa database và hệ thống sự kiện bên ngoài.

## 10. Custom success handler trong Servlet: phải giữ request context

Đối với `DefaultOAuth2AuthorizedClientManager`, success handler mặc định lưu thông qua **`OAuth2AuthorizedClientRepository`**. Repository có chữ ký:

~~~java
void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

Vì cần HTTP request/response, custom handler của Servlet manager phức tạp hơn service manager:

~~~text
DefaultOAuth2AuthorizedClientManager
  -> context / attributes chứa dữ liệu phục vụ Servlet request
  -> OAuth2AuthorizationSuccessHandler
  -> authorizedClientRepository.saveAuthorizedClient(
         authorizedClient, principal, request, response
     )
~~~

Nếu cần bổ sung audit trong manager Servlet, hãy ưu tiên:

- Giữ nguyên handler mặc định và đưa audit vào một **repository decorator** có triển khai `saveAuthorizedClient(...)`, hoặc
- Tạo handler custom có khả năng lấy đúng Servlet request/response từ context manager và delegate đầy đủ hành vi lưu, theo **API chính xác của phiên bản Spring Security đang dùng**.

**Không tự tạo `HttpServletRequest`/`HttpServletResponse` giả** và không gắn token vào một session khác. Cách Spring Security truyền request context qua authorization attributes có thể cần đối chiếu Javadoc/version trước khi triển khai custom.

### 10.1. Mẫu repository decorator để giữ persistence

Mã minh họa một wrapper chỉ bổ sung audit metadata sau khi lưu, không tự quản lý token lifecycle:

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

public final class AuditingAuthorizedClientRepository
        implements OAuth2AuthorizedClientRepository {

    private static final Logger log =
        LoggerFactory.getLogger(AuditingAuthorizedClientRepository.class);

    private final OAuth2AuthorizedClientRepository delegate;

    public AuditingAuthorizedClientRepository(
            OAuth2AuthorizedClientRepository delegate) {
        this.delegate = delegate;
    }

    @Override
    public <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
            String registrationId,
            Authentication principal,
            HttpServletRequest request) {
        return delegate.loadAuthorizedClient(
            registrationId, principal, request);
    }

    @Override
    public void saveAuthorizedClient(
            OAuth2AuthorizedClient authorizedClient,
            Authentication principal,
            HttpServletRequest request,
            HttpServletResponse response) {

        delegate.saveAuthorizedClient(
            authorizedClient, principal, request, response);

        log.info("Authorized client stored; registration={}",
            authorizedClient.getClientRegistration().getRegistrationId());
    }

    @Override
    public void removeAuthorizedClient(
            String registrationId,
            Authentication principal,
            HttpServletRequest request,
            HttpServletResponse response) {
        delegate.removeAuthorizedClient(
            registrationId, principal, request, response);
    }
}
~~~

Đây là **wrapper dùng để minh họa ranh giới trách nhiệm**. Trong ứng dụng thực tế, cần cấu hình nó làm repository mà manager và login flow thực sự sử dụng, tránh vòng lặp injection/delegate bean, đồng thời bảo đảm việc log không chặn thao tác khi hệ thống log lỗi.

Ưu điểm của cách delegate: thành phần đang chịu trách nhiệm lưu token **vẫn được giữ nguyên**, còn audit được đặt ở ranh giới save. Nếu ứng dụng cần audit cả việc cập nhật qua service/JDBC ngoài Servlet, phải gắn quan sát ở tầng lưu trữ tương ứng; wrapper Servlet không tự quan sát mọi lần service manager save.

### 10.2. Không dùng login success handler để ghi lại refresh token

Nếu ứng dụng có:

~~~java
.oauth2Login(login -> login
    .successHandler(myLoginSuccessHandler))
~~~

thì handler này thường phục vụ HTTP login thành công. Nó không phải hook tin cậy cho mọi lần Refresh Token grant sau đó.

Khi mục tiêu là **điều hướng sau login**, dùng `AuthenticationSuccessHandler`. Khi mục tiêu là **lưu authorized client mới do manager cấp/refresh**, dùng cơ chế success handler mặc định của manager hoặc custom `OAuth2AuthorizationSuccessHandler` có delegate lưu trữ rõ ràng.

## 11. AuthorizedClientManager quyết định lúc nào cần refresh?

Manager phối hợp với `OAuth2AuthorizedClientProvider` để xác định loại grant có thể áp dụng:

| Provider / grant | Khi nào liên quan? | Authorized client sau thành công |
| --- | --- | --- |
| `authorization_code` | Người dùng cấp quyền qua browser/redirect | Access Token và có thể Refresh Token của người dùng |
| `refresh_token` | Authorized client cũ có Refresh Token và cần xin Access Token mới | Token mới; có thể Refresh Token đã xoay vòng |
| `client_credentials` | Backend xin token dưới danh nghĩa client/service | Access Token của service |
| Các grant mở rộng | Khi được hệ thống và provider hỗ trợ, cấu hình riêng | Kết quả phụ thuộc grant và contract |

Ví dụ một trạng thái:

~~~text
Authorized client trong kho:
  registration=calendar
  principal=employee-123
  accessToken.expiresAt=10:00
  refreshToken=available

Lúc 09:55:
  manager.authorize(...)
  -> Có thể tái sử dụng client, không cần refresh.

Lúc 10:01:
  manager.authorize(...)
  -> Refresh Token provider có thể xin Access Token mới.
  -> Nếu thành công: authorization success handler lưu client mới.
~~~

Thời điểm thực tế có thể dùng **clock skew** và chính sách riêng, không phải luôn so đúng đến một giây. Không tự thiết kế refresh policy chỉ bằng `token.getExpiresAt().isBefore(now)` rồi bỏ qua manager nếu framework đã đáp ứng yêu cầu.

### 11.1. Khi manager không tạo authorized client mới

Nếu token còn phù hợp, provider có thể trả `null` để báo **không có re-authorization cần thực hiện**, manager vẫn có thể trả authorized client cũ. Trong tình huống đó, success handler thường **không được gọi**.

Nếu client chưa được authorize và không thể dùng grant trong ngữ cảnh hiện tại, manager có thể trả `null` hoặc làm phát sinh đường khởi tạo authorization phù hợp tùy provider/grant. Không kết luận rằng mọi `null` đều đồng nghĩa token bị thu hồi.

### 11.2. Refresh Token rotation

Một Token Endpoint có thể trả:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "calendar.read"
}
~~~

Nếu provider xoay Refresh Token, handler phải đảm bảo bản ghi mới được lưu. Nếu không:

1. Lần refresh đầu thành công nhưng token mới không được lưu.
2. Lần sau manager đọc bản ghi cũ với Refresh Token đã bị thay thế.
3. Token Endpoint có thể trả `invalid_grant`.
4. Ứng dụng mất khả năng tiếp tục gọi API và phải xin người dùng cấp quyền lại.

Đây là một trong những nguyên nhân quan trọng nhất khiến **custom success handler chỉ log** gây lỗi production khó nhận ra ngay lập tức.

## 12. Lưu dữ liệu ở đâu: session, memory hay JDBC?

Success handler chỉ ra lệnh lưu; dữ liệu được lưu **ở đâu** tùy repository/service.

| Implementation | Đặc điểm | Trường hợp phù hợp |
| --- | --- | --- |
| `HttpSessionOAuth2AuthorizedClientRepository` | Tổ chức lưu trữ gắn với HTTP session | Một số web flows đơn giản, trạng thái sống cùng session |
| `InMemoryOAuth2AuthorizedClientService` | Lưu trong bộ nhớ tiến trình | Demo, phát triển hoặc dịch vụ không cần sống qua restart |
| `JdbcOAuth2AuthorizedClientService` | Lưu qua JDBC vào database | Nhiều instance, yêu cầu persistence lâu dài |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegate về service cho principal đã xác thực; fallback cho anonymous | Bridge giữa Servlet repository và service |
| Custom repository/service | Lưu trong kho riêng, có quy tắc TTL/atomicity | Nhu cầu hạ tầng/tuân thủ đặc biệt |

**Lưu qua repository không mặc định nghĩa là lưu session**, vì repository có thể delegate xuống service/JDBC.

### 12.1. Ví dụ JDBC AuthorizedClientService

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

Cần có datasource, Spring JDBC và **database schema phù hợp với phiên bản Spring Security** trước khi chạy. Bean này minh họa storage; Spring Boot có thể đã auto-configure service/repository nên cần tránh khai báo trùng.

Khi `AuthorizedClientServiceOAuth2AuthorizedClientManager` sử dụng service này, handler mặc định của manager sẽ lưu bộ token mới vào JDBC sau lần cấp quyền thành công.

### 12.2. Token là dữ liệu bí mật

Một bản ghi JDBC authorized client có thể lưu:

~~~text
registration_id / principal_name
access_token_value
access_token_issued_at
access_token_expires_at
access_token_scopes
refresh_token_value
refresh_token_issued_at
~~~

Đây chỉ là mô hình dữ liệu minh họa, không thay DDL chính thức. Access Token và Refresh Token phải được bảo vệ như **credential**:

- Hạn chế quyền đọc/ghi/xóa database theo least privilege.
- Mã hóa dữ liệu nhạy cảm khi cần và quản lý khóa mã hóa an toàn.
- Không cho raw token xuất hiện trong log SQL, APM, dump hoặc backup không được bảo vệ.
- Có chính sách retention, xóa khi disconnect và quy trình phục hồi phù hợp.
- Kiểm soát cạnh tranh khi nhiều instance cùng refresh một authorized client.

**Đừng đưa toàn bộ `OAuth2AuthorizedClient` vào log để quan sát success handler.**

## 13. Authorization failure handler và xóa authorized client

Manager có một điểm mở rộng song song:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
~~~

Trong một số tình huống refresh thất bại, handler mặc định có thể xóa authorized client không còn dùng được, tùy mã lỗi và manager đang sử dụng. Ví dụ Refresh Token bị thu hồi có thể làm Token Endpoint trả `invalid_grant`.

Phân biệt:

| Sự kiện | Xử lý chính |
| --- | --- |
| Cấp/refresh token thành công | `OAuth2AuthorizationSuccessHandler` lưu authorized client mới |
| Cấp/refresh token thất bại | `OAuth2AuthorizationFailureHandler` và chính sách lỗi của manager |
| Người dùng chủ động disconnect | Ứng dụng xóa authorized client và có thể gọi token revocation |
| User logout ứng dụng | Kết thúc session/SecurityContext; không mặc nhiên xóa mọi persistent token |

**Không viết failure handler luôn xóa authorized client cho mọi exception.** Ví dụ mạng tạm mất, timeout hay lỗi 5xx từ provider không nhất thiết có nghĩa Refresh Token đã bị thu hồi. Việc xóa token hợp lệ khi gặp lỗi tạm thời có thể khiến người dùng phải chấp thuận lại không cần thiết.

Nếu thay failure handler, cần xem kỹ hành vi mặc định và chính sách token invalidation của phiên bản Spring Security.

### 13.1. Xóa local record khác revocation

~~~java
authorizedClientService.removeAuthorizedClient(
    "calendar", "employee-123"
);
~~~

Lời gọi này xóa **bản ghi tại client**. Nó không tự gửi revocation request tới Authorization Server và không tự kết thúc session SSO của người dùng tại IdP.

Nếu sản phẩm yêu cầu ngắt quyền thật sự, có thể cần OAuth 2.0 Token Revocation (RFC 7009) khi provider hỗ trợ. Cần xử lý token còn hiệu lực, Refresh Token, Access Token và phản hồi theo hợp đồng OP. Không gọi `removeAuthorizedClient(...)` rồi tuyên bố provider đã thu hồi token khi chưa có bằng chứng.

## 14. Multi-user, multi-provider và khóa lưu an toàn

Đối với OAuth2AuthorizedClientService, khóa logic là:

~~~text
(clientRegistrationId, principalName)
~~~

Ví dụ:

| Registration ID | Principal name | Loại quyền |
| --- | --- | --- |
| `company` | `employee-123` | Access Token sau OIDC user login |
| `calendar` | `employee-123` | Quyền đọc lịch của user này |
| `calendar` | `employee-456` | Quyền đọc lịch của user khác |
| `reporting-service` | `system-reporting-job` | Client Credentials của backend |

Handler không nên lấy principal name từ query parameter rồi lưu token vào user được chỉ định tùy ý. Principal phải xuất phát từ **ngữ cảnh authorization đã được quản lý server-side**.

### 14.1. Registration ID không hoàn toàn thay thế issuer

Với OIDC, danh tính người dùng dùng cặp **`iss + sub`**. Nếu ứng dụng sử dụng nhiều issuer nhưng principal names không có namespace đủ mạnh, có thể xảy ra collision. Khi tích hợp nhiều IdP và tenant, cần thiết kế registration/principal identity để token không bị liên kết sang account khác.

### 14.2. Scheduled job có thể truy cập token của end-user không?

Một service manager có thể làm việc ngoài HTTP request, nhưng việc dùng authorized client của **một end-user** trong scheduled job chỉ phù hợp khi:

- User đã cấp quyền cho mục đích đó, và chính sách sản phẩm cho phép thực hiện không có mặt user.
- Kho token dùng principal namespace ổn định và đã xác minh.
- Refresh Token được bảo vệ, retention được kiểm soát, có khả năng disconnect/revoke.
- Job không tùy ý mượn token của user khác.

Không dùng Client Credentials token thay cho delegated user token khi downstream API yêu cầu quyền người dùng, hoặc ngược lại.

## 15. Hai request cùng refresh: success handler có thể bị race condition

Một trường hợp thực tế:

~~~mermaid
sequenceDiagram
    autonumber
    participant R1 as Request A
    participant R2 as Request B
    participant S as AuthorizedClientService
    participant AS as Token Endpoint
    R1->>S: load token cũ của principal X
    R2->>S: load cùng token cũ
    R1->>AS: refresh bằng Refresh Token cũ
    R2->>AS: refresh bằng Refresh Token cũ
    AS-->>R1: Token mới + rotated Refresh Token
    AS-->>R2: Có thể invalid_grant nếu token đã bị dùng
    R1->>S: Success handler lưu token mới
    Note over S: Cần tránh một luồng cũ xóa/ghi đè kết quả mới
~~~

Khi nhiều request hoặc nhiều instance cùng dùng một authorized client, **lưu token thành công không tự đảm bảo cập nhật nguyên tử theo đúng phiên bản token mới nhất**.

Những biện pháp cần cân nhắc:

1. Một cơ chế **single-flight/lock theo `registrationId + principalName`** cho refresh khi thực sự cần.
2. Optimistic locking/version hoặc compare-and-swap nếu dùng custom JDBC storage.
3. Tránh một lần refresh thất bại của request B xóa token mới mà request A vừa lưu.
4. Không retry Refresh Token cũ không giới hạn khi provider dùng token rotation.
5. Giảm quyền ghi đồng thời vào cùng bản ghi token ở những workflows nhạy cảm.

Không tạo **global lock cho mọi authorized clients** vì sẽ làm các người dùng khác nhau bị ảnh hưởng hiệu năng; cơ chế đồng bộ phải theo đúng phạm vi bản ghi.

### 15.1. Custom success handler và transaction

Nếu success handler phải cập nhật đồng thời:

~~~text
oauth2_authorized_client:
  Access Token/Refresh Token mới

integration_connection:
  connected=true, lastAuthorizedAt=...
~~~

thì cần một thiết kế consistency rõ ràng. Với cùng database và transaction manager phù hợp, có thể tổ chức transaction; với event bus/network service, dùng outbox hoặc cơ chế idempotency thay vì giả định hai bước save là nguyên tử.

**Handler được gọi thành công không có nghĩa dữ liệu đã commit vào mọi hệ thống downstream.** Bước quan sát/audit cần phân biệt “authorization succeeded” với “persistence succeeded”.

## 16. Quan sát handler mà không làm lộ token

Một log có ích:

~~~text
event=oauth2_authorization_persisted
registration_id=reporting-service
principal_type=service
grant_family=client_credentials
outcome=success
correlation_id=internal-5f92
~~~

Đây là format được đề xuất, **không phải log mặc định của Spring Security**. Không suy luận grant type chỉ từ có/không có Refresh Token; muốn log grant cần lấy nguồn context phù hợp và đã xác minh.

Không ghi:

- `access_token`, `refresh_token`, `id_token`.
- `client_secret` hoặc token endpoint authorization header.
- Toàn bộ `OAuth2AuthorizedClient` hoặc token response JSON.
- Query callback chứa `authorization_code`, `state` hoặc PKCE verifier.
- Danh tính người dùng quá chi tiết khi không cần cho vận hành.

Khi đo metric, nên dùng số lượng tổng hợp theo registration/grant/outcome và mã lỗi an toàn. Nếu ghi subject hoặc principal, áp dụng chính sách dữ liệu cá nhân và khả năng truy cập phù hợp.

### 16.1. Success handler không phải hook cho mọi HTTP call

Nếu ứng dụng gọi downstream API 500 lần trong khi Access Token chưa hết hạn:

~~~text
authorize() lần 1 -> cần token mới -> success handler lưu
authorize() lần 2..500 -> có thể tái sử dụng token -> handler không chạy
~~~

Không dùng số lần success handler chạy để tính request volume hoặc API success rate. Đo API traffic ở HTTP client/Resource Server layer.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Token được cấp nhưng lần gọi sau không thấy bản ghi | Custom success handler chỉ log, không save | Delegate/persist authorized client trước khi trả thành công |
| Mỗi request lại gọi Token Endpoint | Manager không lưu token hoặc luôn đổi principal/registration | Kiểm tra handler, store, principal key và token expiry |
| Refresh lần đầu thành công, lần sau `invalid_grant` | Refresh Token rotation nhưng token mới không được lưu | Lưu đầy đủ authorized client mới, xử lý concurrency |
| Có bean service manager nhưng web login không dùng nó | Login flow sử dụng repository khác | Kiểm tra OAuth2 Login config và repository/service wiring |
| Handler tự viết không thấy chạy khi token còn hạn | Provider không thực hiện re-authorization | Bình thường; success handler không chạy cho mọi lần load |
| Dùng AuthenticationSuccessHandler mà refresh vẫn không lưu | Login success handler không phải manager hook | Dùng authorization success handler của manager/repository đúng |
| JDBC không thấy token dù login thành công | Kho thực tế là session/in-memory hoặc bean không được dùng | Kiểm tra implementation và wiring, tránh bean trùng |
| Ứng dụng chạy nhiều pods, token biến mất | Lưu memory cục bộ không chia sẻ | Shared JDBC/service hoặc session store phù hợp |
| Token của user A bị dùng cho user B | Principal key/namespace sai | Ràng buộc registration + principal đã xác minh |
| Token mới bị xóa sau refresh đồng thời | Race giữa success/failure handler | Đồng bộ per-client/optimistic concurrency |
| Audit báo “saved” nhưng DB lỗi | Log/audit trước thao tác lưu hoặc transaction chưa commit | Sắp xếp thứ tự và thiết kế audit consistency |
| Handler log làm lộ token | Ghi nguyên authorizedClient/attributes | Chỉ log metadata không nhạy cảm |
| API trả 403 dù manager có token | Token thiếu scope/role/resource policy | Kiểm tra Resource Server; client role không thay quyền API |
| Logout nhưng authorized client vẫn tồn tại | JDBC service lưu độc lập với HTTP session | Thiết kế logout, disconnect và token revocation riêng |

### 17.1. Cách điều tra khi token không được lưu

~~~text
Manager.authorize(...) đã được gọi chưa?
   |
   +-- Có đúng registrationId và principalName không?
   |
   +-- AuthorizedClientProvider có thực hiện grant thành công không?
   |
   +-- Provider có trả authorized client mới hay chỉ trả null?
   |
   +-- Có custom AuthorizationSuccessHandler không?
   |       |
   |       +-- Có thực hiện save/delegate không?
   |
   +-- Store dùng repository hay service? Có đúng instance/bean không?
   |
   +-- Sau save, load bằng cùng khóa có thấy record không?
   |
   +-- Có race condition, rollback hoặc cleanup sớm không?
~~~

Khi debug ở production, tránh in token thật. Có thể dùng môi trường thử nghiệm với token giả và log registration name, loại event, cờ token tồn tại, không cần giá trị bí mật.

## 18. Bài tập tình huống

### Tình huống A — Dùng mặc định, không cần custom handler

Một ứng dụng Spring MVC đăng nhập OIDC và đôi lúc refresh Access Token để gọi API. Manager mặc định đã gắn repository phù hợp.

**Giải pháp:** giữ authorization success handler mặc định. Tập trung cấu hình đúng client registration, grant, lưu trữ và quyền API.

### Tình huống B — Thay handler chỉ để ghi audit

Một lập trình viên gọi `manager.setAuthorizationSuccessHandler((client,principal,attrs) -> log.info("done"))`.

**Vấn đề:** đã thay thế logic persistence của handler mặc định. **Giải pháp:** trong handler mới, gọi save qua repository/service đúng context, hoặc đưa audit vào wrapper/decorator của persistence mà không bỏ hành vi lưu.

### Tình huống C — Client Credentials ngoài Servlet

Scheduled job gọi API báo cáo và không có user/browser session.

**Giải pháp:** dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`, cung cấp principal service-level cố định, cho phép `clientCredentials()`, dùng success handler mặc định lưu token vào service.

### Tình huống D — API cần delegated token của người dùng

Ứng dụng đã có authenticated user và cần gọi API lịch của chính người đó.

**Giải pháp:** chọn đúng registration, principal và authorized client lưu từ flow cấp quyền của user; dùng Servlet manager/repository hoặc workflow ngoài HTTP có được ủy quyền hợp lệ. Không mượn Client Credentials token để thay user token.

### Tình huống E — Token đã lưu nhưng manager không refresh

Access Token hết hạn, Refresh Token có sẵn, nhưng provider/manager không được cấu hình grant `refresh_token`.

**Giải pháp:** xác minh provider hỗ trợ Refresh Token, cách cấp token và bật `refreshToken()` trong authorized client provider của manager tương ứng. Success handler chỉ lưu khi token mới được cấp, không tự chủ động refresh.

### Tình huống F — Token rotation và ghi đồng thời

Hai request cùng refresh, request A nhận Refresh Token mới và lưu; B gặp `invalid_grant` với token cũ.

**Giải pháp:** xử lý concurrency theo authorized client, không để failure handler của B xóa bản ghi mới của A; cần transaction/locking phù hợp nếu triển khai ở quy mô lớn.

### Tình huống G — Người dùng ngắt kết nối tích hợp

Authorized client đã được lưu trong JDBC. Người dùng yêu cầu dừng đồng bộ.

**Giải pháp:** tìm đúng principal và registration, xử lý token revocation nếu provider hỗ trợ, sau đó remove local record. Đây không phải nhiệm vụ của authorization success handler.

### Tình huống H — Login success handler hoạt động nhưng token không lưu ở kho mong muốn

Browser được redirect đúng sau login; ứng dụng kiểm tra JDBC lại không thấy authorized client.

**Giải pháp:** điều tra repository/service được OAuth2 Login sử dụng. `AuthenticationSuccessHandler` có thể hoạt động đúng trong khi token đang lưu ở HTTP session hoặc một in-memory service khác.

### Tình huống I — Handler đã lưu token nhưng audit thất bại

DB có token mới, nhưng hệ thống message broker để gửi audit đang ngừng.

**Giải pháp:** xác định audit là bắt buộc hay tùy chọn và xử lý consistency/idempotency. Không retry cấp token vô hạn vì lỗi ở một hệ thống theo dõi không liên quan trực tiếp tới OAuth2 grant.

## 19. Gợi ý kiểm thử theo từng lớp

Đây là các kịch bản **để người học tự áp dụng**, không phải kết quả chạy test hay QA cho file bài học.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Lần đầu Client Credentials xin Access Token | Manager nhận client mới; success handler lưu bản ghi |
| Gọi lại khi token còn dùng được | Tận dụng authorized client; không cần handler chạy lại |
| Token hết hạn và grant phù hợp | Provider cấp token mới; handler lưu client mới |
| Refresh Token được xoay vòng | Bản ghi chứa Refresh Token mới, không phải token cũ |
| Success handler custom chỉ audit | Lộ ra lỗi không persist nếu không delegate |
| Handler custom có save | Sau authorize, service.loadAuthorizedClient trả client mới |
| DB save lỗi | Không ghi audit “persisted success” trước khi lưu hoàn tất |
| User A và user B dùng cùng registration | Store trả token theo đúng principal, không trộn |
| Logout với JDBC store | Hành vi xóa/giữ token đúng theo chính sách, không dựa vào giả định |
| Token endpoint trả invalid_grant | Đi vào failure handling; không gọi success handler |
| Hai request cùng refresh | Không bị xóa nhầm token mới sau lỗi request cũ |
| Không có browser Servlet request | Dùng service manager, không ép DefaultServlet manager hoạt động ngoài context |

### 19.1. Một unit test mẫu cho custom service success handler

Nếu đã có `OAuth2AuthorizedClientService` và một `OAuth2AuthorizedClient` được tạo từ **test fixture**, có thể kiểm tra logic lưu bằng một handler riêng:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

class AuthorizationSuccessHandlerTest {

    @Test
    void savesAuthorizedClientUnderPrincipalName() {
        OAuth2AuthorizedClientService service = /* test in-memory service */;
        OAuth2AuthorizedClient testClient = /* fixture with TEST token */;

        OAuth2AuthorizationSuccessHandler handler =
            (authorizedClient, principal, attributes) ->
                service.saveAuthorizedClient(
                    authorizedClient, principal.getName());

        var principal = new UsernamePasswordAuthenticationToken(
            "test-service-principal", "N/A");

        handler.onAuthorizationSuccess(testClient, principal, Map.of());

        assertNotNull(service.loadAuthorizedClient(
            testClient.getClientRegistration().getRegistrationId(),
            "test-service-principal"));
    }
}
~~~

Đây là **test skeleton minh họa API**, cố ý để placeholder cho in-memory service và test fixture; muốn chạy cần triển khai hai fixture thực tế. Kiểm thử trực tiếp handler chỉ chứng minh thao tác save, **không tự chứng minh OAuth2 token exchange hoặc OIDC ID Token validation**.

## 20. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Client Core Interfaces: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — OAuth2AuthorizationSuccessHandler Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizationSuccessHandler.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — OAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — OAuth2AuthorizedClientRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 21. Tổng kết: giữ nguyên trách nhiệm lưu khi tùy biến success handler

~~~text
OAuth2AuthorizedClientManager.authorize(...)
  |
  +-- load authorized client cũ từ repository/service
  |
  +-- OAuth2AuthorizedClientProvider
  |     |
  |     +-- Không cần re-authorization
  |     |      -> có thể trả client cũ
  |     |      -> không nhất thiết gọi success handler
  |     |
  |     +-- Grant thành công, có client mới
  |            |
  |            v
  |     OAuth2AuthorizationSuccessHandler
  |            |
  |            +-- DefaultServlet manager: save qua repository
  |            +-- Service manager: save qua service
  |            +-- Custom handler: PHẢI giữ bước save/delegate
  |
  +-- Grant thất bại
        -> OAuth2AuthorizationFailureHandler / error policy

AuthenticationSuccessHandler (login browser)
  -> một hook khác, phục vụ sau khi user login thành công
  -> không thay thế persistence của AuthorizedClientManager
~~~

**Ba điều cần nhớ:**

1. **`OAuth2AuthorizationSuccessHandler` là hook của client manager sau khi cấp/refresh token thành công**, không phải handler điều hướng browser sau đăng nhập.
2. **Manager mặc định đã lưu authorized client.** Nếu chỉ cần lưu và dùng lại Access Token/Refresh Token, không cần custom handler; nếu thay handler, phải giữ logic persistence.
3. **Token phải được lưu đúng registration và principal, trong kho phù hợp vòng đời ứng dụng.** Bảo vệ token như credential, xử lý Refresh Token rotation/concurrency và phân biệt xóa local record với revocation tại provider.

Khi đặt đúng success handler ở đúng tầng, Spring Security có thể tái sử dụng token, refresh và cập nhật authorized client ổn định mà không trộn lẫn trách nhiệm đăng nhập OIDC, lưu token và phân quyền API.
