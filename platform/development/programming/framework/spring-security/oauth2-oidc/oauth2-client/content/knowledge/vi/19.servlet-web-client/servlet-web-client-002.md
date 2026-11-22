# 19.2. Cấu hình filter bằng authorized client manager

## 1. Vấn đề cần giải quyết trong WebClient trên Servlet

Một ứng dụng **Spring Security OAuth 2.0 OIDC Client** chạy trên **Spring MVC/Servlet** thường có hai nhu cầu đồng thời:

1. Cho người dùng đăng nhập bằng **OAuth 2.0 Authorization Code / OpenID Connect (OIDC)**.
2. Từ backend, gửi request đến một **Resource Server** khác bằng Access Token đã được cấp cho người dùng hoặc cho chính ứng dụng.

Ví dụ: một portal nội bộ cho nhân viên đăng nhập qua nhà cung cấp danh tính của doanh nghiệp, sau đó gọi Reports API để đọc báo cáo mà tài khoản đó được phép xem.

~~~text
Browser -> Spring MVC portal -> Reports API
             |
             +-- OAuth2/OIDC Login
             |      ID Token: xác thực người dùng tại portal
             |
             +-- OAuth2 Client
                    Access Token: gọi Reports API
~~~

Trong Spring Framework, `WebClient` là một HTTP client dựa trên **Reactor**, có API fluent và trả `Mono`/`Flux`. Dù tên chứa “Web”, `WebClient` cũng có thể được sử dụng từ **ứng dụng Servlet**, không bắt buộc phải chuyển toàn bộ Spring MVC sang WebFlux.

Để tránh mỗi controller tự tải token, kiểm tra thời hạn và gắn header, Spring Security cung cấp:

**`ServletOAuth2AuthorizedClientExchangeFilterFunction`**

Filter này được gắn vào `WebClient` thông qua `ExchangeFilterFunction` và có thể sử dụng **`OAuth2AuthorizedClientManager`** để lấy Access Token phù hợp cho mỗi outbound request.

Một cấu hình trung tâm:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient webClient = WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

**Ý tưởng chính:** WebClient thực hiện HTTP; filter chọn authorized client và chèn Bearer Token; manager quản lý việc tải/cấp lại token và lưu trạng thái ủy quyền. Resource Server vẫn chịu trách nhiệm kiểm tra token, scope, audience và chính sách truy cập.

Bài này làm rõ cách nối các thành phần ấy, cung cấp ví dụ **delegated user token** và **Client Credentials**, cách truyền request attributes, xử lý token không hợp lệ, giới hạn bảo mật và phương pháp kiểm thử.

## 2. Kiến trúc: filter, manager, provider và store

### 2.1. Các thành phần có trách nhiệm khác nhau

| Thành phần | Vai trò trong luồng | Điều không nên gán cho nó |
| --- | --- | --- |
| `WebClient` | Thực hiện HTTP request bất đồng bộ với API đích | Không tự biết phải xin OAuth2 token nào |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Gắn Access Token của authorized client vào outbound request, điều phối với manager | Không phải OIDC authentication provider hay Resource Server |
| `OAuth2AuthorizedClientManager` | Tải client đã được ủy quyền, cấp lại/refresh khi grant phù hợp, lưu kết quả | Không kiểm tra thay quyền nghiệp vụ của API |
| `OAuth2AuthorizedClientProvider` | Triển khai grant cụ thể: authorization_code, refresh_token, client_credentials... | Không lưu độc lập mọi token giữa các requests |
| `OAuth2AuthorizedClientRepository` | Lưu/tải/xóa authorized client có ngữ cảnh Servlet | Không tự gửi token request |
| `OAuth2AuthorizedClientService` | Lưu/tải/xóa theo registration + principal, không cần request Servlet | Không tự refresh Access Token |
| `ClientRegistrationRepository` | Chứa registration và provider configuration | Không chứa Access Token của từng principal |

### 2.2. Dữ liệu trên một OAuth2AuthorizedClient

`OAuth2AuthorizedClient` liên kết:

~~~text
OAuth2AuthorizedClient
  clientRegistration:
    registrationId = "company"
    clientId = "portal-web"
    authorizationGrantType = authorization_code
  principalName = "employee-123"
  accessToken = <credential; không log>
  refreshToken = <credential hoặc null>
~~~

Khóa logic khi dùng `OAuth2AuthorizedClientService` thường là **`(clientRegistrationId, principalName)`**. Cùng một registration có thể có token riêng của Alice và Bob; cũng có thể có nhiều registrations với scopes/audiences khác nhau dành cho cùng một principal.

**ID Token không phải Access Token.** ID Token được OIDC client xác minh để đăng nhập người dùng; filter dùng **Access Token** cho HTTP `Authorization: Bearer ...`.

### 2.3. Sơ đồ tổng thể

~~~mermaid
flowchart TD
    A["Spring MVC Controller / Service"] --> B["WebClient.get/post(...).attributes(...)"]
    B --> C["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    C --> D["Chọn authorized client hoặc registration ID"]
    D --> E["OAuth2AuthorizedClientManager.authorize(...)"]
    E --> F["Repository / Service: tìm client đã lưu"]
    F --> G{"Access Token sử dụng được?"}
    G -->|Có| H["Trả OAuth2AuthorizedClient"]
    G -->|Chưa cấp / cần refresh| I["OAuth2AuthorizedClientProvider"]
    I --> J["Authorization Server / Token Endpoint"]
    J --> K["Lưu authorized client mới"]
    K --> H
    H --> L["Thêm Authorization: Bearer access_token"]
    L --> M["Resource Server kiểm tra token và policy"]
    M --> N["WebClient nhận response / lỗi"]
~~~

Sơ đồ là mô hình logic, không phải thứ tự nội bộ cố định ở mọi Spring Security version. Đối với một token còn phù hợp, manager có thể sử dụng lại bản ghi đã lưu; **không phải mỗi request HTTP đều gọi Token Endpoint**.

## 3. WebClient trong ứng dụng Servlet có gì đặc biệt?

### 3.1. Servlet runtime vẫn dùng được WebClient

Spring MVC dùng `DispatcherServlet`, `HttpServletRequest` và `HttpServletResponse` để xử lý inbound HTTP. `WebClient` là HTTP client theo kiểu reactive, có thể được gọi từ controller/service Servlet để truy cập API bên ngoài.

Một request đồng bộ thường trông như:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Trong ví dụ, `block()` chờ kết quả trên thread của Spring MVC. Cách này có thể phù hợp khi server vốn xử lý request theo mô hình blocking, nhưng cần timeout và đánh giá hiệu năng. Không gọi `block()` trên Reactor event-loop thread vì có thể gây lỗi hoặc cản trở mô hình reactive.

**Việc dùng WebClient trong ứng dụng Servlet không biến ứng dụng thành WebFlux server.** Servlet controller, SecurityFilterChain và HTTP session vẫn hoạt động theo stack Servlet.

### 3.2. Vì sao class có chữ Servlet nhưng package chứa reactive?

Tên đầy đủ:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

Class này có tên `Servlet...` vì nó làm việc với **ngữ cảnh HTTP của Servlet**, nhưng triển khai contract `ExchangeFilterFunction` của WebClient.

**Không nhầm** với:

~~~text
ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

được thiết kế cho môi trường **Reactive WebFlux** và các thành phần reactive security tương ứng.

### 3.3. Dependency minh họa

Với Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Mang WebClient và reactive HTTP client vào ứng dụng MVC.
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Khi có cả MVC và WebFlux starters, Spring Boot thường ưu tiên **Servlet/MVC server** nếu không có cấu hình rõ ràng khác. Đây không phải lý do để sao chép Reactive `SecurityWebFilterChain` vào ứng dụng; phần server security vẫn dùng `HttpSecurity` và `SecurityFilterChain`.

Spring Boot 4.x có các starter được modular hóa khác; chọn dependency tương thích với BOM của phiên bản dự án, không trộn Spring Security 6.x/7.x một cách thủ công.

## 4. Cấu hình filter bằng OAuth2AuthorizedClientManager: phiên bản tối thiểu

### 4.1. Bean WebClient

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient oauth2WebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

`oauth2.oauth2Configuration()` cấu hình **filter** trên builder, đồng thời thêm các mặc định hữu ích cho request context trong Servlet. Nó là cách tích hợp được Spring Security hỗ trợ.

Một cấu hình cùng mục đích có thể được viết tường minh bằng:

~~~java
WebClient webClient = WebClient.builder()
    .defaultRequest(oauth2.defaultRequest())
    .filter(oauth2)
    .build();
~~~

**Chọn một trong hai cách.** Không vừa `.apply(oauth2.oauth2Configuration())` vừa tự `.filter(oauth2)` trên cùng builder, vì có thể chạy filter hai lần.

### 4.2. Vì sao chỉ tạo WebClient bean là chưa đủ?

Filter phải biết nên dùng authorized client nào. Nó cần ít nhất một trong những nguồn xác định phù hợp, chẳng hạn:

- Authorized client được truyền trực tiếp qua `oauth2AuthorizedClient(...)`.
- `clientRegistrationId(...)` để manager tìm/cấp token theo registration và principal.
- Cấu hình default client đã được chủ động bật (cần đặc biệt thận trọng).

Nếu thiếu client registration/authorized client và không có default hợp lệ, đừng kỳ vọng filter tự biết API nào cần token nào.

### 4.3. Không cần tự đặt Authorization header

Sau khi filter tìm được `OAuth2AuthorizedClient`, nó sử dụng Access Token để tạo:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Code nghiệp vụ không nên vừa dùng filter vừa đặt header Bearer thủ công:

~~~java
// PHẢN VÍ DỤ: có nguy cơ trùng header hoặc dùng token sai nguồn.
webClient.get()
    .uri("https://reports.example.net/api/reports")
    .header("Authorization", "Bearer " + manuallyLoadedToken)
    .attributes(clientRegistrationId("company"))
    .retrieve();
~~~

Chọn **một cơ chế rõ ràng** cho việc chèn credential. Với cấu hình trong bài, đó là filter và manager.

## 5. Gắn đúng clientRegistrationId cho request

Spring Security cung cấp static helper:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
~~~

Sử dụng trong request:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

`clientRegistrationId("company")` ghi một **attribute nội bộ của ClientRequest**, không phải query parameter của URL và cũng không phải scope. Manager sử dụng registration ID để tìm cấu hình client, principal và authorized client tương ứng.

### 5.1. Nhiều registrations trong một hệ thống

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, reports.read]
          billing-service:
            provider: billing-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
          billing-auth:
            token-uri: https://auth.billing.example.net/oauth2/token
~~~

Với user delegated token, request có thể chọn `company`; với service-to-service token chọn `billing-service`. Nhưng **không được tự lấy registration ID từ HTTP request của browser nếu người dùng không được phép chọn**.

Một người dùng có thể đăng nhập bằng company OIDC nhưng không được dùng token Client Credentials có quyền rộng để gọi Billing API theo ý mình.

### 5.2. Registration ID phải khớp cấu hình

~~~text
Spring Boot ClientRegistration:
  registrationId = "company"

WebClient request:
  .attributes(clientRegistrationId("company"))

=> Hai tên phải khớp.
~~~

Nếu viết `clientRegistrationId("company-oidc")` trong khi registration thực tế là `company`, filter/manager không tìm được đúng client. `company-oidc` ở YAML trên chỉ là **provider ID**, không phải registration ID.

### 5.3. Nên dùng WebClient riêng cho API nhạy cảm

Một WebClient bean chung có thể gọi nhiều host. Vì OAuth2 filter có khả năng gắn token, nên thường an toàn hơn khi tạo các WebClient chuyên dụng với `baseUrl` cố định:

~~~java
WebClient reportsWebClient = WebClient.builder()
    .baseUrl("https://reports.example.net")
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

Tuy nhiên, `baseUrl` không tự ngăn mọi URL tuyệt đối được truyền vào `uri(...)`; code ứng dụng vẫn phải chỉ sử dụng path/host được duyệt và kiểm soát redirect.

## 6. Chuyển trực tiếp OAuth2AuthorizedClient qua request attributes

Không phải lúc nào filter cũng cần tự tìm token qua registration ID. Nếu controller đã có `OAuth2AuthorizedClient` hợp lệ, có thể truyền thẳng:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Ở đây `authorizedClient` đã được Spring Security cung cấp từ một nguồn server-side đáng tin cậy, ví dụ annotation:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ReportController {

    private final WebClient reportsWebClient;

    public ReportController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/current-user")
    public String myReports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsWebClient.get()
            .uri("/api/reports")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }
}
~~~

**Giải thích:** annotation resolver lấy authorized client trong ngữ cảnh Spring Security; request attribute đưa đối tượng này cho WebClient filter. WebClient không phải tự tìm registration ID nữa vì đã được cung cấp client cụ thể.

Điểm cần lưu ý: nếu application cần **token mới khi hết hạn** và yêu cầu linh hoạt về reauthorization, cách `clientRegistrationId(...)` giúp manager chủ động xử lý lifecycle. Truyền trực tiếp một đối tượng authorized client cũ không có nghĩa token sẽ luôn được làm mới trong mọi cấu hình; phải hiểu đường xử lý của manager/filter và tránh giữ một object token cũ trong singleton field.

Không đưa `OAuth2AuthorizedClient`, Access Token hoặc Refresh Token vào DTO trả về browser.

## 7. Authentication và ngữ cảnh Servlet

### 7.1. Authentication mặc định từ đâu?

Trong Servlet MVC request thông thường:

~~~text
Browser
  -> SecurityFilterChain xác thực
  -> SecurityContextHolder chứa Authentication
  -> Controller gọi WebClient
  -> WebClient defaultRequest() lấy Authentication hiện tại
  -> manager tìm authorized client theo principal
~~~

`oauth2.oauth2Configuration()` có thể cung cấp **Authentication mặc định** từ `SecurityContextHolder` và Servlet request/response từ `RequestContextHolder`. Đây là tiện ích giúp call WebClient bên trong MVC request không phải truyền mọi đối tượng theo cách thủ công.

**Không giả định SecurityContextHolder có ở mọi thread.** Trong `@Async`, scheduled tasks hoặc pipeline có `publishOn(...)`/`subscribeOn(...)`, thread thực thi có thể khác Servlet request thread, khiến ThreadLocal context không còn được nhìn thấy.

### 7.2. Đặt Authentication tường minh

Spring Security cung cấp:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
~~~

Ví dụ:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(currentAuthentication))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Biến `currentAuthentication` phải được lấy từ ngữ cảnh server-side đáng tin cậy, ví dụ controller nhận `Authentication authentication` hoặc `SecurityContextHolder` trong đúng thread.

**Không lấy user ID do browser nhập rồi tự dựng một Authentication đặc quyền để truy vấn authorized client của người khác.**

### 7.3. Truyền HttpServletRequest / HttpServletResponse khi thực sự cần

Với manager dùng `OAuth2AuthorizedClientRepository`, một số thao tác cần Servlet request/response để tải/lưu token đúng session:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletRequest;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletResponse;
~~~

Ví dụ:

~~~java
webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(currentAuthentication))
    .attributes(httpServletRequest(servletRequest))
    .attributes(httpServletResponse(servletResponse))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

`servletRequest`/`servletResponse` là các tham số `jakarta.servlet.http.HttpServletRequest` và `HttpServletResponse` mà controller/service được truyền hợp lệ.

Trong MVC flow bình thường, `defaultRequest()` đã giúp lấy context tương ứng; truyền tay chỉ khi cần kiểm soát rõ, xử lý đặc thù hoặc kiểm thử. **Không giữ HttpServletRequest/Response trong singleton để dùng lại ở request sau.**

### 7.4. WebClient subscription là điểm dễ mất context

WebClient sử dụng Reactor pipeline; lời gọi:

~~~java
Mono<String> mono = webClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

chưa nhất thiết thực thi outbound HTTP ngay lập tức. Việc subscribe/`block()` sẽ kích hoạt pipeline.

Nếu code tạo `Mono` trong MVC request rồi subscribe muộn trên thread khác, Servlet ThreadLocal và SecurityContext có thể không còn như lúc tạo request. Muốn xử lý ngoài HTTP request, cần thiết kế explicit authentication/authorized client context và chọn **service manager** nếu không có Servlet context, không dựa vào RequestContextHolder tồn tại mãi.

## 8. Authorized client manager: hai cấu hình phổ biến

### 8.1. DefaultOAuth2AuthorizedClientManager dành cho Servlet request

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository);

manager.setAuthorizedClientProvider(provider);
~~~

Đoạn này giả định đã có `clientRegistrationRepository` và `authorizedClientRepository`. Manager sử dụng repository có ngữ cảnh HTTP, thích hợp với browser-based OAuth2/OIDC Login trong Servlet.

### 8.2. AuthorizedClientServiceOAuth2AuthorizedClientManager dành cho backend

~~~java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build());
~~~

Service manager không cần Servlet request/response. Nó phù hợp với batch jobs, scheduled jobs và Client Credentials.

### 8.3. Bảng lựa chọn

| Tiêu chí | DefaultOAuth2AuthorizedClientManager | AuthorizedClientServiceOAuth2AuthorizedClientManager |
| --- | --- | --- |
| Nguồn authorized client | Repository | Service |
| Gắn với Servlet request | Có | Không cần |
| Có thể gọi từ background job | Không nên nếu thiếu Servlet context | Có |
| Principal | Authentication/request context | Authentication/principal name do application cung cấp |
| Grant thông dụng | Authorization Code, Refresh Token | Client Credentials; các grant phù hợp khác |
| Thành phần persistence | Repository có thể delegate sang service | Service lưu memory/JDBC/custom |
| Kết nối WebClient filter | Constructor nhận `OAuth2AuthorizedClientManager` | Cùng constructor nhận manager |

**Filter không quan tâm manager cụ thể thuộc loại nào miễn contract phù hợp**. Nhưng chọn sai manager có thể gây mất Servlet context hoặc dùng nhầm token của end-user và service.

## 9. Ví dụ A: WebClient gọi API thay mặt người dùng OIDC

Đây là cấu hình nhiều thành phần dành cho **Spring Boot MVC/Servlet**. Các đoạn được chia theo file/class chức năng; không phải nhiều `SecurityFilterChain` thay thế nhau.

### 9.1. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
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

Các URL/scope là ví dụ; provider thật phải cho phép `reports.read` và Access Token phải được phát hành cho Reports API. Scope tên giống nhau ở hai providers không đảm bảo semantics hoặc audience tương đương.

### 9.2. SecurityFilterChain

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

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

`oauth2Login()` xác thực browser bằng OIDC, còn `oauth2Client()` hỗ trợ OAuth2 Client trong Servlet application. Controller chỉ gọi downstream API khi browser đã được xác thực theo security policy.

### 9.3. Bean OAuth2AuthorizedClientManager tường minh

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
public class UserAuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager userAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là cấu hình tường minh để minh họa manager. Nếu Spring Boot/Spring Security đã tạo một manager bean đúng nhu cầu thì không cần khai báo trùng. Nếu ứng dụng vừa có user manager vừa có machine manager, dùng tên bean/`@Qualifier` rõ ràng khi injection.

### 9.4. WebClient filter dùng manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean
    WebClient reportsWebClient(
            OAuth2AuthorizedClientManager userAuthorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                userAuthorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

**Lưu ý quan trọng về HTTP 401/403:** constructor nhận manager **không tự cấu hình** `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` cho những lỗi Bearer từ Resource Server. Nếu muốn token không hợp lệ bị loại khỏi cache, phải cấu hình failure handler phù hợp. Phần 12 trình bày cách thực hiện; đừng suy ra điều này tự xảy ra chỉ vì đã dùng manager.

### 9.5. Controller gọi Reports API

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@RestController
public class MyReportsController {

    private final WebClient reportsWebClient;

    public MyReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/my-reports")
    public ResponseEntity<String> myReports() {
        String body = reportsWebClient.get()
            .uri("/api/reports/me")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class)
            .block();

        return ResponseEntity.ok(body);
    }
}
~~~

Controller được Spring Security bảo vệ. Filter lấy Authentication hiện tại và authorized client của registration `company`, rồi thêm Bearer Access Token nếu có thể authorize.

**Ví dụ trả raw JSON để tập trung vào OAuth2.** Trong ứng dụng thật, nên map response vào DTO, lọc claim nhạy cảm, đặt timeout và xử lý lỗi downstream để không vô tình proxy nguyên dữ liệu ngoài ý muốn.

### 9.6. Luồng end-to-end

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant MVC as Portal Spring MVC
    participant WC as WebClient OAuth2 Filter
    participant M as Servlet AuthorizedClientManager
    participant Store as Authorized Client Repository
    participant OP as OIDC Provider / Token Endpoint
    participant API as Reports API
    Browser->>MVC: GET /my-reports (session đã login)
    MVC->>WC: GET /api/reports/me, registration=company
    WC->>M: authorize(company, current Authentication)
    M->>Store: loadAuthorizedClient(...)
    alt Token hiện có dùng được
        Store-->>M: Existing OAuth2AuthorizedClient
    else Token cần refresh, có refresh token
        M->>OP: Refresh Token grant
        OP-->>M: Token response mới
        M->>Store: saveAuthorizedClient(...)
    end
    M-->>WC: OAuth2AuthorizedClient
    WC->>API: Authorization: Bearer Access Token
    API-->>WC: JSON/HTTP error
    WC-->>MVC: Mono response
    MVC-->>Browser: HTTP response đã kiểm soát
~~~

Nếu user chưa login, flow Servlet OAuth2 Login có thể redirect tới Authorization Server. Nếu API yêu cầu scope/audience không được cấp, filter không thể tự tạo thêm quyền: Resource Server có thể trả 401/403.

## 10. Ví dụ B: WebClient + Client Credentials với service manager

Một backend worker muốn gọi Reports API theo danh tính **ứng dụng**, không có user đăng nhập.

### 10.1. Cấu hình registration Client Credentials

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: reports-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reports-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

**Không dùng scope `openid` và OIDC ID Token chỉ để lấy máy-to-máy Access Token.** Client Credentials là OAuth 2.0 grant, thường không có end-user và không cần browser redirect, `state`, PKCE hoặc OIDC `nonce`.

### 10.2. Service manager cho Client Credentials

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
public class MachineAuthorizedClientConfig {

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
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Manager này không cần Servlet HTTP request, phù hợp khi service được gọi từ scheduler hoặc job. Authorized client được lưu theo `registrationId` và một **principal name ứng dụng** mà caller cung cấp.

### 10.3. WebClient bean dùng machine manager

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class MachineReportsWebClientConfig {

    @Bean
    WebClient machineReportsWebClient(
            @Qualifier("machineAuthorizedClientManager")
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Tên class có `Servlet` nhưng manager service cho phép hoạt động **ngoài Servlet request** nếu caller cung cấp principal context tin cậy và không phụ thuộc vào Servlet ThreadLocal.

### 10.4. Cung cấp application principal cho request

Filter dùng Authentication để xác định `principalName`. Với một scheduled job không có `SecurityContextHolder`, hãy cung cấp **Authentication nội bộ chỉ dùng làm khóa authorized client**:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class ReportingSyncClient {

    private final WebClient machineReportsWebClient;

    public ReportingSyncClient(WebClient machineReportsWebClient) {
        this.machineReportsWebClient = machineReportsWebClient;
    }

    public String loadReportsJson() {
        // Chỉ là application-level key cho authorized-client store.
        // KHÔNG đại diện cho end-user đã login.
        Authentication servicePrincipal =
            new UsernamePasswordAuthenticationToken(
                "system-report-sync", "N/A");

        return machineReportsWebClient.get()
            .uri("/api/reports")
            .attributes(clientRegistrationId("reports-service"))
            .attributes(authentication(servicePrincipal))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }
}
~~~

`UsernamePasswordAuthenticationToken` ở đây được tạo bởi server-side code chỉ để cung cấp **principal name ổn định** cho manager/service. Đừng sử dụng token này như bằng chứng “một người dùng đã đăng nhập”, cũng không cho HTTP caller tự chọn giá trị `system-report-sync`.

Nếu ứng dụng có nhiều machine identities và phải phân quyền giữa tenants, hãy đặt namespace principal và registration phù hợp chính sách, không dùng một token toàn quyền cho mọi tenant khi không cần thiết.

### 10.5. Mỗi lần gọi có xin Access Token mới không?

Không nhất thiết:

~~~text
Lần 1:
  ("reports-service", "system-report-sync")
  -> chưa có authorized client
  -> Token Endpoint cấp Access Token
  -> manager lưu authorized client

Lần 2:
  -> manager tìm cùng khóa, token còn hạn
  -> có thể tái sử dụng Access Token

Khi token hết hạn hoặc không còn phù hợp:
  -> Client Credentials grant xin Access Token mới
  -> manager cập nhật authorized client
~~~

Client Credentials thường **không cấp Refresh Token theo cách dùng chuẩn**. Khi Access Token hết hạn, manager xin token mới bằng Client Credentials grant. Không gắn `refreshToken()` chỉ vì lo token sắp hết hạn.

### 10.6. Không dùng machine token để thay danh tính user

Nếu browser user Alice gọi một endpoint portal, rồi portal dùng Client Credentials token rộng để lấy toàn bộ báo cáo của công ty, Resource Server có thể chỉ thấy **service identity**, không thấy Alice. Backend phải thực thi authorization/tenant/ownership theo nghiệp vụ trước khi dùng token machine-level, hoặc dùng delegated user token nếu API yêu cầu user context.

Đừng dùng `principal("alice")` dưới Client Credentials rồi kết luận Access Token được cấp đã đại diện cho Alice: **principal name chỉ là khóa lưu trữ ở client manager**, không biến một OAuth2 grant machine-to-machine thành delegation người dùng.

## 11. Hai constructor của filter và hệ quả quan trọng

`ServletOAuth2AuthorizedClientExchangeFilterFunction` có hai cách khởi tạo chính cần phân biệt:

~~~java
// Cách A: cung cấp manager đã được tạo/cấu hình.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);

// Cách B: cung cấp repository và client registrations.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

### 11.1. Constructor nhận authorized client manager

Ưu điểm:

- Dùng manager đã được custom grant provider.
- Thống nhất success/failure policies ở manager.
- Dễ chọn service manager cho background jobs.
- Có thể cấu hình storage độc lập qua manager.

**Lưu ý:** constructor **nhận manager không tự cấu hình** `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` cho lỗi HTTP 401/403 từ Resource Server. Nếu API báo Access Token đã bị thu hồi, filter có thể tiếp tục dùng cached token trong request sau trừ khi bạn xử lý invalidation.

### 11.2. Constructor nhận repositories

Khi dùng constructor:

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

filter có thể sử dụng cấu hình manager phù hợp được khởi tạo nội bộ, và **một `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` được cấu hình tự động** để xử lý lỗi Bearer từ Resource Server theo policy mã lỗi.

Đây không có nghĩa nó loại bỏ token với mọi HTTP 403. Handler phân loại theo OAuth2 error code; mỗi provider/Resource Server có thể trả lỗi khác nhau.

### 11.3. Bảng so sánh

| Khía cạnh | Filter(manager) | Filter(registrations, repository) |
| --- | --- | --- |
| Manager được cung cấp | Ứng dụng quyết định | Filter dùng cơ chế do constructor thiết lập |
| Linh hoạt custom provider/grant | Cao | Theo cấu hình constructor/tích hợp |
| Phù hợp service manager không có Servlet context | Có | Không phải trường hợp chính |
| Failure handler cho lỗi HTTP 401/403 | **Cần cấu hình rõ khi muốn invalidation** | **Có mặc định** theo cấu hình constructor |
| Chiến lược lưu token | Theo manager/store đã inject | Theo repository được inject |

Vì đề bài tập trung **liên kết filter với authorized client manager**, các ví dụ ưu tiên **constructor nhận manager**, đồng thời chỉ ra cách cấu hình failure handler phù hợp.

## 12. Cấu hình OAuth2AuthorizationFailureHandler cho filter(manager)

### 12.1. Vì sao cần handler cho Resource Server errors?

Authorization Server có thể đã cấp Access Token hợp lệ tại thời điểm T0. Đến T1, token bị thu hồi hoặc Resource Server phát hiện token sai issuer/audience:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nếu manager chỉ nhìn thời hạn `expiresAt`, token có thể vẫn còn hạn về mặt thời gian, nên request sau tiếp tục dùng token lỗi.

Một `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` có thể xóa authorized client tương ứng khi lỗi phù hợp, để **lần authorize tiếp theo** có thể xin một token mới.

### 12.2. Handler với AuthorizedClientService

Đối với **service manager**:

~~~java
import org.springframework.security.oauth2.client.RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

OAuth2AuthorizationFailureHandler failureHandler =
    new RemoveAuthorizedClientOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) ->
            authorizedClientService.removeAuthorizedClient(
                registrationId, principal.getName()));

ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        machineAuthorizedClientManager);

oauth2.setAuthorizationFailureHandler(failureHandler);
~~~

Code giả định `authorizedClientService` và `machineAuthorizedClientManager` là những dependency đã có. Handler cần được áp dụng với **cùng backing store/principal namespace** mà manager dùng; nếu manager lưu ở service A còn handler xóa ở service B, cached token lỗi vẫn còn trong A.

Không sử dụng đoạn này để xóa token của toàn bộ users: remover nhận `registrationId` và `principal` của giao dịch cụ thể.

### 12.3. Handler với OAuth2AuthorizedClientRepository trong Servlet

Với manager Servlet lưu qua repository, handler phải có `HttpServletRequest` và `HttpServletResponse` đúng ngữ cảnh để xóa:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

OAuth2AuthorizationFailureHandler failureHandler =
    new RemoveAuthorizedClientOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) -> {
            // Lấy servlet request/response đúng context bằng một adapter
            // đã được dự án kiểm soát và phù hợp phiên bản framework.
            HttpServletRequest request = currentServletRequest();
            HttpServletResponse response = currentServletResponse();
            authorizedClientRepository.removeAuthorizedClient(
                registrationId, principal, request, response);
        });

oauth2.setAuthorizationFailureHandler(failureHandler);
~~~

Đoạn này là **pseudocode Java định hướng tích hợp**: `currentServletRequest()`/`currentServletResponse()` là helper mà dự án phải định nghĩa; **không phải API Spring Security có sẵn**. Khi triển khai thật, ưu tiên tận dụng các Servlet request/response attributes do filter/manager cung cấp hoặc một adapter tin cậy, tránh lấy sai session từ một thread khác.

Nếu bạn chỉ cần handler mặc định cho repository và không cần custom manager, constructor `(ClientRegistrationRepository, OAuth2AuthorizedClientRepository)` là một lựa chọn đơn giản hơn.

### 12.4. Đừng tự xóa mọi token khi API trả 403

Các HTTP status liên quan:

| Status / Bearer challenge | Diễn giải | Hành vi phù hợp |
| --- | --- | --- |
| `401 invalid_token` | Token có thể hết hạn, thu hồi hoặc không hợp lệ | Có thể xóa cached authorized client theo handler/policy |
| `403 insufficient_scope` | Token được nhận diện nhưng thiếu scope cho thao tác | Không tự mở rộng scope hay quyền; xử lý authorization |
| `403` không có Bearer error | Có thể do tenant/ownership/resource state | Không mặc định xóa token |
| `429` | Rate limit | Thực hiện backoff/retry có kiểm soát |
| `500/503` | Lỗi upstream | Giám sát/retry tùy nghiệp vụ; không kết luận token sai |

`OAuth2AuthorizationFailureHandler` của filter xử lý **lỗi OAuth2 từ Resource Server**. Trong khi đó, `OAuth2AuthorizedClientManager` có failure handling riêng khi **Token Endpoint** trả lỗi như `invalid_client` hoặc `invalid_grant`. Không gộp hai nguồn lỗi chỉ vì đều liên quan OAuth2.

### 12.5. Filter có tự thử lại request vừa bị 401 không?

Không nên dựa vào giả định đó. Việc loại bỏ authorized client bị lỗi giúp **request tiếp theo** có cơ hội xin token mới; request hiện tại vẫn có thể kết thúc bằng exception hoặc response lỗi.

Nếu product yêu cầu retry:

- Chỉ retry với lỗi có khả năng khôi phục.
- Có **giới hạn số lần** và backoff hợp lý.
- Phân biệt GET/idempotent request với POST/PATCH/DELETE có tác dụng phụ.
- Không retry `insufficient_scope` bằng cách tự xin scope admin.
- Không retry khi target API URL do user điều khiển và không được allowlist.

## 13. setDefaultOAuth2AuthorizedClient và setDefaultClientRegistrationId

Filter hỗ trợ mặc định để tránh lặp request attribute, nhưng đây là những lựa chọn cần đánh giá bảo mật.

### 13.1. Dùng OAuth2AuthorizedClient hiện tại làm mặc định

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

oauth2.setDefaultOAuth2AuthorizedClient(true);
~~~

Khi bật, filter có thể tìm authorized client mặc định từ current OAuth2 Authentication. Theo tài liệu Spring Security, **mọi outbound HTTP request qua WebClient này có thể nhận Access Token** nếu filter tìm được client.

Hãy cẩn trọng: một WebClient dùng để gọi cả API tin cậy và URL bên ngoài có thể vô tình chuyển Bearer Token đến sai host.

### 13.2. Dùng client registration mặc định

~~~java
oauth2.setDefaultClientRegistrationId("company");
~~~

Điều này khiến filter chọn registration `company` khi request không chỉ định registration phù hợp. Một lần nữa, **mọi request qua bean đó có thể mang Access Token**; không nên cấu hình cho một WebClient dùng để gọi các host không cùng trust boundary.

### 13.3. Lựa chọn an toàn hơn

Trong nhiều hệ thống, nên:

- Giữ filter mặc định **không ép một token cho mọi request**.
- Chỉ định `clientRegistrationId(...)` khi call API tương ứng.
- Dùng WebClient chuyên dụng với `baseUrl`/host allowlist rõ ràng.
- Không cho user quyết định client registration/principal có quyền cao.

Nếu team chọn default registration cho một WebClient chuyên dụng, phải đảm bảo code không được phép override URL tới destination không tin cậy hoặc làm lộ token qua redirects/tracing.

## 14. SecurityContext và thread boundaries trong Servlet + WebClient

### 14.1. Vì sao WebClient gọi từ MVC khác WebClient ở WebFlux?

Trong Servlet stack, Authentication thường nằm trong `SecurityContextHolder` của thread xử lý request. WebClient xử lý HTTP trên Reactor pipeline; việc gọi asynchronous có thể chuyển công việc sang thread khác.

~~~text
Servlet request thread
  SecurityContextHolder = Alice
  RequestContextHolder = current HttpServletRequest
  -> tạo WebClient Mono
       |
       v
Reactive subscriber / other scheduler
  có thể KHÔNG có các ThreadLocal tương tự
~~~

Nếu filter cần load authorized client qua repository nhưng Servlet request không còn khả dụng, ứng dụng có thể gặp lỗi không tìm thấy context hoặc token.

### 14.2. Đưa attributes tường minh khi cần

Trong controller:

~~~java
@GetMapping("/my-data")
public String myData(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response) {

    return webClient.get()
        .uri("https://reports.example.net/api/me")
        .attributes(clientRegistrationId("company"))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                authentication))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletRequest(
                request))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletResponse(
                response))
        .retrieve()
        .bodyToMono(String.class)
        .block();
}
~~~

Đoạn này **rút gọn** để nhấn mạnh request attributes; giả định class đã có field `webClient`, imports cho Spring MVC/Servlet và endpoint được bảo vệ. Trong ứng dụng thông thường, `defaultRequest()` đã xử lý phần context nên không cần truyền thủ công; ví dụ hữu ích khi tìm hiểu cơ chế hoặc xử lý kiến trúc đặc thù.

**Không lưu servletRequest/response vào field singleton** hoặc truyền qua một background job chạy sau khi response đã kết thúc.

### 14.3. Khi nào nên dùng service manager?

Nếu API call chạy trong scheduled job, queue consumer hoặc một nhiệm vụ không có browser request, chọn:

~~~text
AuthorizedClientServiceOAuth2AuthorizedClientManager
    + OAuth2AuthorizedClientService
    + Application principal ổn định
    + Client Credentials grant (nếu mục đích là M2M)
~~~

Đừng cố cấu hình `RequestContextHolder` giả hoặc dùng global SecurityContext của một user để cho batch job hoạt động. Cần phân biệt machine token với delegated user token và xác định ai đã cấp quyền cho job.

### 14.4. Tránh blocking trong event-loop

Trong Spring MVC, `.block()` có thể thuận tiện nhưng phải cấu hình timeout, quản lý connection pool và không làm chậm request vô hạn.

Trong reactive WebFlux pipeline, gọi `.block()` trên non-blocking event-loop là sai mô hình. Bài đang nói **WebClient trong Servlet**, không khuyến nghị sao chép cách `.block()` vào mọi môi trường.

## 15. Cấu hình timeout, lỗi HTTP và khả năng vận hành

### 15.1. Thiết lập giới hạn thời gian

Một request xuống Reports API có thể chậm, mất kết nối hoặc trả 5xx. OAuth2 filter không tự thay thế timeout policy của HTTP client.

Ví dụ với Reactor Netty đã được cấu hình phù hợp:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

Đoạn này cấu hình **timeout chờ HTTP response của outbound Resource Server**; Token Endpoint client của Spring Security có HTTP client và timeout riêng. Muốn cấu hình timeout cho Token Endpoint, cần tùy biến token response client tương ứng, không cho rằng sửa Reactor Netty connector luôn ảnh hưởng đến token grant.

### 15.2. Xử lý lỗi HTTP ở tầng service

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;

public String fetchReports(WebClient webClient) {
    try {
        return webClient.get()
            .uri("https://reports.example.net/api/reports")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    } catch (WebClientResponseException.Unauthorized ex) {
        throw new IllegalStateException(
            "Reports API từ chối Access Token", ex);
    } catch (WebClientResponseException.Forbidden ex) {
        throw new IllegalStateException(
            "Không được phép truy cập Reports API", ex);
    }
}
~~~

Ví dụ phân loại HTTP 401/403; không tự retry, không chuyển raw response body vào browser. Tên exception chính xác có thể phụ thuộc cách `retrieve()/onStatus` hoặc `exchangeToMono()` được dùng.

### 15.3. Lỗi Token Endpoint và Resource Server khác nhau

~~~text
WebClient filter -> AuthorizedClientManager -> Token Endpoint
   invalid_client, invalid_scope, invalid_grant
   -> lỗi cấp/refresh Access Token

WebClient filter -> Resource Server
   401 invalid_token, 403 insufficient_scope
   -> lỗi HTTP Bearer hoặc policy tại API
~~~

Không mặc định mọi 401 trong hệ thống đều là `invalid_client`, và không mặc định mọi 403 đều do scope. Cần xem lỗi xuất hiện ở **Token Endpoint** hay API đích, mã lỗi OAuth2/Bearer và tài liệu provider.

### 15.4. Circuit breaker và retry

Khi gọi API:

- Retry có giới hạn với 429/503/timeout nếu thao tác idempotent và hợp đồng cho phép.
- Tôn trọng `Retry-After` khi được API cung cấp.
- Tránh bão token requests khi nhiều instances cùng nhận lỗi.
- Không retry Client Credentials `invalid_client` liên tục vì secret sai không tự lành.
- Không lặp authorization code callback hoặc retry Refresh Token đã bị rotate không kiểm soát.

**Interceptor không phải công cụ chung để tự khắc phục mọi lỗi tích hợp.** Token lifecycle do manager phụ trách; retry HTTP và degradation thuộc HTTP client/application policy.

## 16. Authorized client storage: interceptor dùng cùng kho với manager

### 16.1. InMemory, JDBC và session

| Kho | Ví dụ implementation | Ưu/nhược điểm |
| --- | --- | --- |
| Memory | `InMemoryOAuth2AuthorizedClientService` | Dễ demo, mất khi restart, không chia sẻ nhiều instance |
| JDBC | `JdbcOAuth2AuthorizedClientService` | Có thể persistent/shared; cần schema, encryption và database operations |
| Servlet session | `HttpSessionOAuth2AuthorizedClientRepository` | Gắn vòng đời với browser session; cần session replication khi scale-out |
| Repository adapter | `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegate về service cho authenticated principal; có fallback cho anonymous |

Nếu manager save vào JDBC Service A còn code điều tra chỉ đọc Session Repository B, có thể kết luận sai là token bị mất.

### 16.2. Ví dụ JDBC service

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

Đây là cấu hình minh họa, chưa bao gồm Spring JDBC datasource hoặc migration schema. Không tự áp DDL của phiên bản Spring Security khác vào production nếu chưa kiểm tra contract.

**Access Token và Refresh Token trong database là credentials.** Bảo vệ truy cập, mã hóa/retention theo chính sách, tránh log SQL/backup không an toàn. Xóa local authorized client không đồng nghĩa Authorization Server đã revoke token.

### 16.3. Principal namespace

Một service manager dùng:

~~~text
("reports-service", "system-report-sync")
~~~

không được nhầm với:

~~~text
("reports-service", "employee-123")
~~~

Nếu principal key thay đổi theo từng request, manager có thể không tìm lại token đã lưu. Nếu principal key quá rộng, nhiều tenants có thể vô tình dùng chung token. Thiết kế key theo đúng security boundary và grant.

## 17. Multi-provider, multi-tenant và giới hạn quyền

### 17.1. Chỉ định đúng token cho đúng Resource Server

Ví dụ:

~~~text
company-oidc (delegated user token)
  issuer = https://id.example.com/realms/company
  audience = reports-api
  scope = reports.read

billing-service (machine token)
  issuer = https://auth.billing.example.net
  audience = billing-api
  scope = billing.read
~~~

WebClient filter **không biến Reports Token thành Billing Token**. Lựa chọn registration/principal xác định cách manager lấy token, còn Resource Server phải xác minh issuer, audience, thời hạn, scope và policy.

### 17.2. Không lấy tenant từ browser để chọn token đặc quyền

Phản ví dụ:

~~~java
webClient.get()
    .uri(userProvidedDestination)
    .attributes(clientRegistrationId(userProvidedRegistration))
    .attributes(authentication(userProvidedAuthentication))
    .retrieve();
~~~

Đây là thiết kế nguy hiểm: request đến URL tùy ý có thể mang Access Token của client quyền cao; principal không được lấy từ input không đáng tin. Phải ánh xạ destination, registration và principal từ policy server-side và Authentication đã được xác minh.

### 17.3. Scope của API không đồng nghĩa role của user

Một service token có scope `reports.read.all` không chứng minh user đang truy cập portal có quyền xem tất cả dữ liệu. Nếu backend dùng machine token, authorization theo user/tenant phải được thực thi trước hoặc tại downstream API theo thiết kế.

Ngược lại, `ROLE_ADMIN` trong portal không tự tạo thêm `reports.write` scope trên Access Token. Phải có phép cấp quyền tại Authorization Server và policy tương ứng ở Resource Server.

### 17.4. Token confidentiality

Không được:

- Đưa `access_token`, `refresh_token`, `id_token` vào JSON response của controller.
- Gắn Access Token vào query string URL để debug.
- Log `Authorization` header, Client Secret hoặc toàn bộ HTTP wire trace ở production.
- Dùng WebClient có OAuth2 filter để fetch URL do user nhập mà không có allowlist.
- Gửi delegated user token đến host bên ngoài issuer/resource trust boundary.

## 18. Bảo mật redirects, interceptors và observability

### 18.1. Redirects có thể tạo rủi ro

Một API có thể trả redirect 301/302/307/308. HTTP client có quy tắc riêng khi chuyển tiếp headers qua redirect, tùy transport/library/version.

Đừng **giả định** Bearer Token luôn được bảo vệ khi API redirect sang host khác. Với HTTP client có token interceptor:

1. Giới hạn destination host.
2. Thiết kế chính sách redirects rõ ràng, nhất là cross-host redirects.
3. Nếu API không cần redirects, cân nhắc tắt/giới hạn hành vi follow redirect theo HTTP connector.
4. Không cho attacker điều khiển Location hoặc URL đích để chiếm credential.

### 18.2. Logging filter và OAuth2 filter

Một `ExchangeFilterFunction` ghi log HTTP request có thể quan sát headers sau khi OAuth2 filter gắn token, tùy thứ tự filter. **Không dựa vào thứ tự** để bảo vệ credential.

Phải có chính sách redact ở tất cả logging/tracing layers:

~~~text
Authorization: [REDACTED]
Cookie: [REDACTED]
access_token: [REDACTED]
refresh_token: [REDACTED]
client_secret: [REDACTED]
~~~

### 18.3. Metric an toàn

Một metric/log metadata hợp lý:

~~~text
event=outbound_oauth2_api_call
registration_id=company
resource=reports-api
result=success
http_status=200
correlation_id=internal-7fa2
~~~

Format này là minh họa, không phải logging mặc định của Spring Security. Không dùng raw token, username nhạy cảm hay request IDs có cardinality cao làm metric labels không kiểm soát.

### 18.4. Client Credentials secret rotation

Nếu machine manager xin token và Token Endpoint trả `invalid_client`, kiểm tra Client Secret, auth method và provider tenant. Không sửa bằng cách thêm scopes, không tự thử nhiều secrets cũ hoặc retry vô hạn. WebClient filter không xử lý thay quy trình quản lý credentials.

## 19. WebClient filter và RestClient interceptor không giống nhau

Hai kiểu HTTP client có mô hình khác:

| Tiêu chí | WebClient | RestClient |
| --- | --- | --- |
| Mô hình | Reactive client, `Mono`/`Flux` | Đồng bộ, fluent |
| HTTP hook | `ExchangeFilterFunction` | `ClientHttpRequestInterceptor` |
| Spring Security Servlet OAuth2 integration | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `OAuth2ClientHttpRequestInterceptor` (Spring Security 6.4+) |
| Manager | `OAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Chọn registration | `Servlet...FilterFunction.clientRegistrationId(...)` | `RequestAttributeClientRegistrationIdResolver.clientRegistrationId(...)` |
| Chọn principal | `Servlet...FilterFunction.authentication(...)` | `RequestAttributePrincipalResolver.principal(...)` hoặc resolver khác |

Không copy:

~~~java
new OAuth2ClientHttpRequestInterceptor(manager)
~~~

để dùng làm WebClient filter. Nó dành cho RestClient, không triển khai `ExchangeFilterFunction`.

Ngược lại, không gắn `ServletOAuth2AuthorizedClientExchangeFilterFunction` vào `RestClient.Builder.requestInterceptor(...)`; hai HTTP hook interfaces khác nhau.

### 19.1. Vì sao không dùng reactive security filter ở Servlet?

`ServerOAuth2AuthorizedClientExchangeFilterFunction` thuộc Reactive WebFlux integration và làm việc với các thành phần reactive authorization context. Trong Servlet app, `ServletOAuth2AuthorizedClientExchangeFilterFunction` là lựa chọn phù hợp vì nó biết cách lấy Authentication/Servlet request context mặc định.

### 19.2. Dùng WebClient khi nào?

WebClient có ích khi muốn:

- API fluent cho HTTP và response processing bằng Reactor.
- Tích hợp với reactive client SDK hoặc xử lý nhiều downstream calls.
- Dùng chung các tiện ích reactive HTTP, dù inbound server vẫn là MVC.

Tuy nhiên nếu toàn bộ ứng dụng là Servlet đồng bộ và chỉ gọi một vài API đơn giản, `RestClient` cũng có thể là lựa chọn phù hợp. Lựa chọn HTTP client phải dựa trên kiến trúc và dependency/version, không chỉ tên thư viện.

## 20. Kiểm thử việc liên kết filter với manager

Một bộ kiểm thử hữu ích cần phân biệt:

1. **WebClient filter test:** filter có gắn đúng Bearer header khi manager trả client hợp lệ không?
2. **AuthorizedClientManager test:** manager có lấy/refresh token theo registration/principal không?
3. **Resource Server integration test:** API có chấp nhận token đúng audience/scope và từ chối token sai không?
4. **Servlet context test:** SecurityContext và RequestContextHolder có được truyền đúng qua MVC request không?

Mock Access Token trong WebClient unit test **không chứng minh** token được Authorization Server phát hành hay ID Token OIDC đã xác minh.

### 20.1. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| WebClient gắn OAuth2 filter, manager trả authorized client | Outbound request có `Authorization: Bearer TEST_TOKEN` |
| Không có registration và không có default | Không tự gửi một token quyền cao |
| `clientRegistrationId("company")` đúng | Manager dùng registration company |
| Registration ID sai | Không âm thầm dùng token của registration khác |
| User Alice và user Bob cùng registration | Mỗi người nhận đúng authorized client |
| Client Credentials với application principal cố định | Lưu/tải token theo cùng khóa |
| Scheduled job không có Servlet request | Service manager vẫn hoạt động với Authentication tường minh |
| Token còn hạn | Có thể dùng lại authorized client |
| Token hết hạn, có Refresh Token hợp lệ | Manager refresh và lưu token mới |
| Client Credentials token hết hạn | Manager xin token mới theo Client Credentials grant |
| Token Endpoint trả `invalid_client` | API không được gọi bằng token giả/hết hiệu lực |
| Resource Server trả `401 invalid_token` | Failure handler xử lý cached token theo policy |
| Resource Server trả `403 insufficient_scope` | Không tự nâng scope/role |
| Resource Server trả 404 | Không xóa token nếu không có lý do OAuth2 cụ thể |
| API URL không thuộc allowlist | Không gửi Bearer Token |
| Filter manager constructor chưa có failure handler | Test phản ánh việc cached client có thể vẫn còn |
| Failure handler dùng nhầm service/store | Test bắt lỗi xóa sai backing store |
| WebClient Mono subscribe trên thread khác | Không phụ thuộc giả vào ThreadLocal Servlet context |
| HTTP logging bật | Không có Authorization header/token trong logs |

### 20.2. MockWebServer hoặc WebClient ExchangeFunction test

Sơ đồ một test:

~~~text
WebClient
  -> ServletOAuth2AuthorizedClientExchangeFilterFunction(testManager)
  -> Fake ExchangeFunction / MockWebServer
       assert URI = /api/reports
       assert Authorization = Bearer TEST_ONLY_ACCESS_TOKEN
       return 200 JSON giả
~~~

Test double của manager cần trả `OAuth2AuthorizedClient` chứa Access Token test. Khi test filter, có thể không cần chạy Authorization Code flow. Trong integration test grant, dùng mock Authorization Server để xác minh token exchange và lưu trữ.

Đừng dùng production Client Secret, Access Token hoặc Refresh Token trong test fixtures.

### 20.3. Kiểm tra rằng filter không gửi token nhầm host

Trong production, nên có test/contract cho policy destination:

~~~text
https://reports.example.net/api/reports -> allowed
https://example-evil.invalid/collect   -> blocked before token transmission
~~~

Filter không mặc nhiên là hệ thống host allowlisting. Nếu application tự truyền arbitrary URL cho WebClient, phải kiểm soát ở gateway/URI policy hoặc HTTP client chuyên dụng.

### 20.4. Test default OAuth2AuthorizedClient flags

Nếu bật `setDefaultOAuth2AuthorizedClient(true)` hoặc `setDefaultClientRegistrationId(...)`, hãy test rằng **chỉ những outbound calls trong trust boundary** mới sử dụng WebClient có token. Không chỉ test “request đúng có token”, mà còn test “request không phù hợp không bị gửi credential”.

## 21. Chẩn đoán khi filter không gửi Access Token

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Request không có Bearer header | WebClient bean không áp dụng filter | `.apply(oauth2.oauth2Configuration())` hoặc `.filter(oauth2)` |
| Filter không tìm registration | Thiếu `clientRegistrationId(...)`, tên sai | Registration ID trong Spring Boot config |
| Manager trả null | Không thể authorize grant trong context | Provider chain, principal, registration, request attributes |
| Lỗi không có Servlet request | Dùng Default manager trong background job | Service manager hoặc cung cấp context đúng |
| Token của user A dùng cho user B | Principal namespace hoặc Authentication bị nhầm | SecurityContext, service store, request attributes |
| Token Endpoint `invalid_client` | Client Secret/method/tenant sai | Client registration và provider policy |
| Token Endpoint `invalid_scope` | Scope chưa được cấp | Grant policy, requested scopes |
| Resource Server `401 invalid_token` | Token hết hạn/thu hồi/sai issuer/audience | API validation, client registration, failure handler |
| Resource Server `403 insufficient_scope` | Token thiếu scope | Quyền được cấp và API policy |
| Resource Server `403` khác | Tenant/ownership/resource state | API authorization logic |
| Lỗi chỉ xuất hiện khi `@Async` | Mất SecurityContext/Servlet ThreadLocal | Subscription/thread boundaries |
| Token refresh thành công nhưng request sau dùng token cũ | Manager/store khác nhau, custom success handler không save | Authorized client persistence |
| Không có token mới sau lỗi 401 | Constructor nhận manager thiếu failure handler | Cấu hình `setAuthorizationFailureHandler(...)` |
| Handler xóa nhưng lần gọi hiện tại vẫn 401 | Không có auto-retry | Thiết kế retry giới hạn riêng |
| Mỗi request lại xin token | Principal key thay đổi, memory store phân tán | Service/Repository và persistence |
| Lộ token qua tracing | Wire log ghi Authorization header | Redaction và logging policy |
| API khác host nhận token | WebClient dùng URI do caller cung cấp | SSRF, redirects, host allowlist |

### 21.1. Một trình tự điều tra ngắn

~~~text
WebClient outbound request thất bại
   |
   +-- Có đúng WebClient bean được gắn filter?
   |
   +-- clientRegistrationId/authorizedClient có được cung cấp?
   |
   +-- Authentication/principal có đúng user/service?
   |
   +-- Manager được chọn đúng Servlet hay Service?
   |
   +-- Kho authorized client có đúng registration + principal?
   |
   +-- Token Endpoint đã cấp/refresh thành công?
   |
   +-- Access Token được gửi đến đúng Resource Server?
   |
   +-- API trả 401/403/429/5xx?
   |
   +-- Cần failure handler/invalidation hoặc policy retry?
~~~

Không log nguyên `OAuth2AuthorizedClient` để kiểm tra — object này có thể chứa token. Chỉ sử dụng metadata cần thiết, redaction và correlation ID không chứa credential.

## 22. Những sai lầm triển khai dễ gặp

### 22.1. Không truyền registration ID

~~~java
webClient.get()
    .uri("/api/reports")
    .retrieve()
    .bodyToMono(String.class);
~~~

Nếu không có authorized client/default phù hợp, filter không thể tự chọn token. Bổ sung `.attributes(clientRegistrationId("company"))` hoặc chọn rõ authorized client.

### 22.2. Bật default OAuth2 client cho WebClient công cộng

Một WebClient dùng để gọi mọi URL và bật `setDefaultOAuth2AuthorizedClient(true)` có thể gửi token không mong muốn. Tách clients theo trust boundary, đừng để token được tự động gắn vào mọi outbound call.

### 22.3. Đặt token của một user vào static field

~~~java
// PHẢN VÍ DỤ:
static String lastAccessToken;
~~~

Concurrent requests có thể làm user này sử dụng token của user khác. Dùng manager/store với khóa registration + principal và không tạo global token singleton.

### 22.4. Dùng ID Token làm Bearer cho API

ID Token dành cho xác thực OIDC client. Resource Server thông thường yêu cầu Access Token. Không dùng `oidcUser.getIdToken().getTokenValue()` thay `authorizedClient.getAccessToken()`.

### 22.5. Cho scheduled job dùng servlet manager không có request

`DefaultOAuth2AuthorizedClientManager` phụ thuộc Servlet context cho repository. Dùng service manager cho công việc ngoài HTTP request, nhất là Client Credentials.

### 22.6. Chỉ truyền clientRegistrationId, quên service principal

Với Client Credentials trong worker thread, không có SecurityContext hợp lệ để manager xác định principal name. Truyền Authentication application-level qua `authentication(...)` và không lấy principal từ browser.

### 22.7. Nghĩ filter sẽ kiểm tra audience và quyền API

Filter chủ yếu đưa Access Token vào HTTP request; Resource Server phải xác minh token và authorization. Token được gắn đúng header vẫn có thể bị API từ chối.

### 22.8. Coi cached token 401 sẽ tự biến mất khi dùng constructor(manager)

Constructor manager **không tự cài RemoveAuthorizedClient failure handler cho Resource Server**. Phải cấu hình khi cần invalidation hoặc dùng constructor repository có hành vi mặc định khác.

### 22.9. Xóa mọi authorized client sau một lỗi HTTP

Không xóa token của mọi user vì một 404/503 hoặc 403 thiếu quyền. Dựa trên mã OAuth2/Bearer và policy, không tự động xóa toàn bộ store.

### 22.10. Vừa gắn OAuth2 filter vừa tự thêm Bearer header

Hai nguồn credentials dễ xung đột, tạo lỗi không ổn định hoặc rò rỉ dữ liệu. Ưu tiên filter + manager duy nhất cho request sử dụng OAuth2.

### 22.11. Dùng cùng WebClient cho API nội bộ và arbitrary URL

Điều này mở đường cho SSRF/token exfiltration. Thiết kế WebClient chuyên dụng, cố định host/path hoặc có allowlist nghiêm ngặt.

### 22.12. Dùng logging filter làm “điểm kiểm tra token”

Logging/tracing không được ghi raw Bearer Token. Dùng test token trong môi trường test hoặc metadata không nhạy cảm khi điều tra production.

### 22.13. Tạo Mono trong request nhưng subscribe sau khi session context mất

Không dựa vào ThreadLocal Servlet/SecurityContext khi pipeline thực thi muộn hoặc trên scheduler khác; truyền context rõ ràng, chọn service manager hoặc thiết kế phù hợp.

### 22.14. Đặt success handler của manager chỉ để log

Nếu thay `OAuth2AuthorizationSuccessHandler` mặc định mà không lưu client mới, token có thể không được persist. Khi custom cần giữ việc save token vào store chính xác.

## 23. Bài tập tình huống thực tế

### Tình huống A — Portal OIDC gọi API của chính người dùng

User đăng nhập `company`, portal muốn gọi Reports API cho user đó.

**Thiết kế:** `DefaultOAuth2AuthorizedClientManager` với Servlet repository, WebClient filter nhận manager, request attributes dùng `clientRegistrationId("company")`, principal từ SecurityContext. Chỉ gửi token đã được provider cấp cho Reports API đúng audience/scope.

### Tình huống B — Worker đồng bộ báo cáo không có browser

Scheduled job gọi Reports API bằng Client Credentials.

**Thiết kế:** `AuthorizedClientServiceOAuth2AuthorizedClientManager`, `clientCredentials()` provider, application principal ổn định truyền qua `authentication(...)`, WebClient chuyên dụng. Không mượn authenticated user token.

### Tình huống C — Filter có token nhưng API trả 403

Token chứa `reports.read`, nhưng job gọi endpoint cần `reports.write`.

**Thiết kế:** dừng thao tác, kiểm tra API contract và xin quyền qua governance nếu cần. Không tự tăng scope hay sửa filter để bypass Resource Server.

### Tình huống D — API trả 401 cho token còn hạn

Resource Server đã thu hồi token hoặc API không chấp nhận audience. Manager vẫn thấy `expiresAt` còn tương lai.

**Thiết kế:** phân loại `invalid_token`, cấu hình failure handler để loại bỏ cached authorized client khi thích hợp, điều tra issuer/audience nếu token mới vẫn sai. Không retry vô hạn.

### Tình huống E — WebClient dùng chung để gọi API và URL user nhập

Một chức năng import dữ liệu nhận URL từ browser và gọi cùng WebClient đang có OAuth2 filter.

**Thiết kế:** tách WebClient không có token cho chức năng public fetch, giới hạn hosts/IPs/redirects và chặn SSRF. Không để Bearer Token của portal bị gửi ra Internet tùy ý.

### Tình huống F — MVC controller dùng block, background subscription không thấy Authentication

Ứng dụng tạo Mono trong controller nhưng đưa sang queue rồi subscribe sau.

**Thiết kế:** không phụ thuộc SecurityContextHolder/RequestContextHolder của HTTP request đã kết thúc. Thiết kế delegated authorization có lưu trữ và quyền rõ ràng hoặc chuyển sang service manager cho machine flow.

### Tình huống G — Hai client registrations cùng provider

Ứng dụng có `reports-read` và `reports-write`, cùng token endpoint nhưng quyền khác nhau.

**Thiết kế:** đặt request attributes đúng registration theo tính năng, không cho user chọn `reports-write` qua query string. Có thể tách hai WebClients và thêm policy ở service.

### Tình huống H — Token mới không được lưu

Manager xin Access Token thành công, nhưng lần gọi kế tiếp lại xin mới vì custom success handler chỉ ghi log.

**Thiết kế:** khôi phục default persistence hoặc delegate save vào authorized client service/repository; kiểm tra đúng principal key, tránh thêm save tự phát ở nhiều nơi.

### Tình huống I — 401 bị invalidated nhưng current request vẫn lỗi

Failure handler đã xóa cached client; `WebClient.retrieve()` vẫn ném unauthorized exception.

**Thiết kế:** hiểu invalidation giúp lần request sau; nếu cần retry, thực hiện ở application layer với giới hạn và kiểm tra idempotency. Không giả định handler tự replay request.

### Tình huống J — Multi-node đọc token không nhất quán

Node A lưu in-memory authorized client, node B dùng memory riêng và không tìm thấy token; nhiều calls cùng xin lại.

**Thiết kế:** dùng shared authorized client service khi cần, như JDBC, và đồng bộ theo registration/principal đối với refresh rotation. Không coi đây là lỗi scope.

## 24. Tài liệu tham khảo

- Spring Security — OAuth2 Client trên Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Client Features, WebClient Integration: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — `ServletOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `OAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — `DefaultOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — `AuthorizedClientServiceOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700

## 25. Tổng kết: một filter, một manager, đúng registration và principal

~~~text
Spring MVC Controller / backend service
    |
    v
WebClient
    .attributes(clientRegistrationId("company" | "reports-service"))
    .attributes(authentication(...))  // khi cần chỉ định principal
    |
    v
ServletOAuth2AuthorizedClientExchangeFilterFunction
    |
    +-- dùng OAuth2AuthorizedClient trực tiếp nếu được truyền
    |
    +-- hoặc gọi OAuth2AuthorizedClientManager.authorize(...)
           |
           +-- Servlet user flow: repository + Authorization Code/Refresh Token
           |
           +-- Service flow: service + Client Credentials
           |
           +-- Tải / cấp mới / refresh / lưu authorized client
    |
    v
Authorization: Bearer <access_token>
    |
    v
Resource Server
    |
    +-- 2xx: xử lý dữ liệu
    +-- 401 invalid_token: failure handler/invalidation phù hợp
    +-- 403 insufficient_scope: chính sách API/quyền
    +-- 429/5xx: retry/backoff có kiểm soát
~~~

**Bốn điểm cần ghi nhớ:**

1. **`ServletOAuth2AuthorizedClientExchangeFilterFunction` là cầu nối giữa WebClient và `OAuth2AuthorizedClientManager` trên Servlet stack.** Dùng `new ...FilterFunction(manager)` rồi `WebClient.builder().apply(oauth2.oauth2Configuration())` để gắn filter và default Servlet context.
2. **Chọn đúng client và principal.** `clientRegistrationId(...)` chọn registration; `authentication(...)` hoặc SecurityContext xác định principal, qua đó xác định authorized client và token được dùng.
3. **Filter(manager) không tự cấu hình removal handler cho Resource Server 401/403.** Khi cần invalidation, cấu hình `setAuthorizationFailureHandler(...)` với store và policy đúng; không xóa mọi token hoặc retry mọi HTTP request.
4. **Bảo vệ ranh giới quyền và credential.** Chỉ gửi Access Token tới API được phép; tránh WebClient gắn token mặc định cho URL tùy ý; giữ secret khỏi logs/redirects; phân biệt delegated user token, machine token, ID Token và quyền của Resource Server.

Khi các tầng được cấu hình nhất quán, WebClient trong Spring MVC có thể gọi API được bảo vệ bằng OAuth2 mà code nghiệp vụ không phải tự quản lý Bearer Token, đồng thời giữ rõ trách nhiệm **OIDC login**, **OAuth2 authorization**, **authorized client lifecycle** và **HTTP client security**.
